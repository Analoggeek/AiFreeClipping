"""Performance policies and transactional export, not cross-device speed claims."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from clipos.core import hardware
from clipos.core.hardware import HardwareProfile,GPUInfo
from clipos.video.renderer import _atomic_render,RenderResult


def test_amf_and_hybrid_qsv_are_runtime_probed_not_display_vendor_assumed():
    profile=HardwareProfile(gpu=GPUInfo(vendor='nvidia'),ffmpeg_encoders={'h264_amf':True,'h264_qsv':True})
    with patch.object(hardware,'detect_hardware',return_value=profile),patch.object(hardware,'encoder_works',return_value=True):
        assert hardware.choose_encoder('amd').hw_accel=='amf'
        assert hardware.choose_encoder('intel').hw_accel=='qsv'
    with patch.object(hardware,'detect_hardware',return_value=profile),patch.object(hardware,'encoder_works',return_value=False):
        assert not hardware.choose_encoder('amd').is_hardware


@pytest.mark.parametrize('outcome',['failure','cancel','success'])
def test_transactional_export_retains_old_file_until_verified_completion(tmp_path,outcome):
    source=tmp_path/'input.mp4';source.write_bytes(b'source')
    output=tmp_path/'output.mp4';output.write_bytes(b'previous good render')
    class Renderer:
        @_atomic_render
        def render(self,source,output):
            assert Path(output).parent==tmp_path
            assert Path(output).name!='output.mp4'
            Path(output).write_bytes(b'new bytes')
            if outcome=='failure':raise RuntimeError('encoder/device failed')
            return RenderResult(output_path=str(output),cancelled=outcome=='cancel',duration=1.,width=160,height=90)
    if outcome=='failure':
        with pytest.raises(RuntimeError):Renderer().render(source,output)
    else:
        result=Renderer().render(source,output)
        assert result.output_path==str(output)
    assert output.read_bytes()==(b'new bytes' if outcome=='success' else b'previous good render')
    assert source.read_bytes()==b'source'
    assert not list(tmp_path.glob('.clipos-render-*'))
    with pytest.raises(ValueError):Renderer().render(source,source)


def test_busy_remains_true_until_queued_gui_completion_is_handled():
    from clipos.ui.pages.workflow import WorkflowPage
    page=SimpleNamespace(task=SimpleNamespace(isRunning=lambda:False),_task_pending=True)
    assert WorkflowPage._busy(page)
    page._task_pending=False
    assert not WorkflowPage._busy(page)


def test_startup_is_lazy_and_workspace_is_removed_without_deleting_projects(tmp_path):
    from PySide6.QtWidgets import QApplication
    from clipos.ui.main_window import MainWindow
    from clipos.db.database import Database
    app=QApplication.instance() or QApplication([])
    window=MainWindow(Database(tmp_path/'ui.db'))
    try:
        assert set(window.pages)=={'workflow'}
        assert 'multitrack' not in window.nav_buttons and 'multitrack' in window._page_classes
        window.navigate('templates')
        assert 'templates' in window.pages  # restored at user request for 3.5
        assert 'longform' not in window._page_classes
        window.navigate('settings')
        assert window.pages['settings']._hardware_worker is not None
    finally:
        window.close();app.processEvents()


def test_longform_device_failure_restarts_every_part_on_cpu(tmp_path):
    from tests.test_longform_preferences import fixture_video
    from clipos.video import longform
    from clipos.core.ffmpeg import FFmpegRunner,FFmpegError,probe
    from clipos.core.hardware import EncoderChoice
    source=fixture_video(tmp_path);plan=tmp_path/'plan.json';longform.analyse(source,plan)
    native=FFmpegRunner.run;hardware_parts=[];cpu_parts=[]
    def run(self,args,*a,**kw):
        args=list(args)
        if '-c:v' in args:
            idx=args.index('-c:v')+1
            if args[idx]=='h264_nvenc':
                hardware_parts.append(args[-1])
                if len(hardware_parts)==2:raise FFmpegError(args,1,'device lost')
                # Exercise real assembly, but never pretend this machine has a GPU.
                args[idx]='libx264';args[args.index('-preset')+1]='veryfast'
            else:cpu_parts.append(args[-1])
        return native(self,args,*a,**kw)
    with patch.object(hardware,'choose_encoder',side_effect=[EncoderChoice(video_encoder='h264_nvenc',hw_accel='nvenc'),EncoderChoice()]),patch.object(FFmpegRunner,'run',run):
        result=longform.export(plan,tmp_path/'out.mp4',width=160,height=90)
    assert len(hardware_parts)==2 and len(cpu_parts)==2
    assert Path(cpu_parts[0]).name==Path(hardware_parts[0]).name
    assert result['warnings'] and probe(tmp_path/'out.mp4').has_audio


def test_speech_cuda_initialization_failure_retries_local_cpu(tmp_path):
    import sys
    from clipos.ai import transcription as stt
    source=tmp_path/'source.wav';source.write_bytes(b'fixture')
    calls=[]
    class Model:
        def __init__(self,*args,**kwargs):
            calls.append(kwargs['device'])
            if kwargs['device']=='cuda':raise RuntimeError('missing GPU runtime library')
        def transcribe(self,*args,**kwargs):
            return iter([]),SimpleNamespace(duration=1.,language='en')
    with patch.object(stt,'faster_whisper_available',return_value=True),patch.object(stt,'local_model_path',return_value=tmp_path),patch.object(stt,'_resolve_device',side_effect=lambda dev:('cpu','int8') if dev=='cpu' else ('cuda','float16')),patch.dict(sys.modules,{'faster_whisper':SimpleNamespace(WhisperModel=Model)}):
        result=stt.transcribe(source)
    assert calls==['cuda','cpu'] and result.text==''

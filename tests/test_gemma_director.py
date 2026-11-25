"""Safety/GUI contracts; injected inference here is not a trained-model acceptance claim."""
import json
from unittest.mock import patch
import pytest
from clipos.ai.gemma_runtime import GemmaRuntime
from clipos.core.local_ai import LocalAIError
from clipos.db.database import Database

@pytest.mark.parametrize('host',['https://example.org','http://192.168.1.1:11434','http://localhost:11434/redirect'])
def test_manager_has_same_loopback_boundary(host):
    with pytest.raises(LocalAIError):GemmaRuntime(host)

def test_download_never_starts_without_consent():
    runtime=GemmaRuntime()
    with patch.object(runtime.client.opener,'open') as request:
        with pytest.raises(LocalAIError):runtime.pull('gemma:7b')
        request.assert_not_called()

def test_download_rejects_arbitrary_remote_or_unverified_tags():
    with pytest.raises(LocalAIError):GemmaRuntime().pull('someone/unknown:cloud',consent=True)

def test_unload_requires_local_weights_first():
    runtime=GemmaRuntime()
    with patch.object(runtime.client,'require_local_model',side_effect=LocalAIError('missing')),patch.object(runtime.client,'request') as request:
        with pytest.raises(LocalAIError):runtime.unload('gemma:7b')
        request.assert_not_called()










@pytest.mark.parametrize('key',['gaming','podcast','talking_head','educational','reaction','cinematic'])
def test_quick_styles_reach_actual_captioned_export(tmp_path,key):
    from clipos.core.ffmpeg import run_ffmpeg,probe,ffmpeg_available
    from clipos.video.renderer import ClipRenderer,RenderSettings
    from clipos.video.presets import apply_preset
    from clipos.captions.caption_engine import CaptionCue
    if not ffmpeg_available():pytest.skip('Requires real FFmpeg')
    source=tmp_path/'style.mp4'
    run_ffmpeg(['-f','lavfi','-i','testsrc2=size=160x90:rate=15:duration=1','-c:v','libx264','-threads','1',str(source)])
    settings=apply_preset(RenderSettings(width=180,height=320,fps=15,threads=1,encoder_preference='cpu'),key)
    settings.auto_facecam=False;settings.facecam_rect=None
    output=tmp_path/'out.mp4'
    ClipRenderer(tmp_path/'work').render(source,output,0,1,settings,cues=[CaptionCue(0,1,'Actual style export',[])])
    assert probe(output).video.height==320 and output.stat().st_size>1000

def test_native_audio_underrun_refills_real_pcm_instead_of_fatal_error():
    import queue,time
    from types import SimpleNamespace
    from unittest.mock import Mock
    QAudio=pytest.importorskip("PySide6.QtMultimedia",exc_type=ImportError).QAudio
    from clipos.ui.multitrack_audio import AudioClockPlayer
    pcm=b'\x01\x00\x02\x00'*10
    fake=SimpleNamespace(sink=Mock(),timer=Mock(),failed=Mock(),ended=Mock(),device=Mock(),queue=queue.Queue(),pending=pcm,finished=False,error=None,_last_audio_activity=time.monotonic())
    fake.sink.error.return_value=QAudio.Error.UnderrunError
    fake.sink.bytesFree.return_value=len(pcm);fake.device.write.return_value=len(pcm)
    AudioClockPlayer._pump(fake)
    fake.device.write.assert_called_once_with(pcm);fake.failed.emit.assert_not_called()
    fake.sink.error.return_value=QAudio.Error.IOError
    AudioClockPlayer._pump(fake);fake.failed.emit.assert_called_once()

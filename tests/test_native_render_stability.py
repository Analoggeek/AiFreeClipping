"""Native fault recovery contracts + actual scalar/caption rendering.

Faults are injected; the user's original Mac/source crash is not reproduced.
"""
import gzip
import hashlib
import json
from pathlib import Path
import platform
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from clipos.core.ffmpeg import FFmpegRunner,FFmpegError,FFmpegCancelled,require_ffmpeg,probe
from clipos.core.render_recovery import compatibility_args


@pytest.fixture(autouse=True)
def clear_session_compatibility():
    FFmpegRunner._compatibility_binaries.clear()
    yield
    FFmpegRunner._compatibility_binaries.clear()


def test_compatibility_command_keeps_exact_edit_and_disables_parallel_simd():
    args=['-threads','14','-i','source.mp4','-filter_complex','[0:v]scale=1080:1920,ass=caption.ass[v]',
          '-map','[v]','-map','0:a','-c:v','libx264','-threads','14','out.mp4']
    fixed=compatibility_args(args)
    assert args[1]=='14'  # caller command remains intact
    assert fixed[fixed.index('-filter_complex')+1]==args[args.index('-filter_complex')+1]
    assert fixed.count('-map')==2 and fixed[-1]=='out.mp4'
    assert fixed[fixed.index('-cpuflags')+1]=='0'
    assert fixed[fixed.index('-x264-params')+1]=='asm=0:threads=1:lookahead_threads=1'
    for i,value in enumerate(fixed[:-1]):
        if value in ('-threads','-filter_threads','-filter_complex_threads'):assert fixed[i+1]=='1'


@pytest.mark.parametrize('code',[-11,-10,-7,-6,-4,139,-1073741819,3221225477])
def test_native_fault_retries_once_and_records_local_diagnostic(code,tmp_path):
    from clipos.core import render_recovery
    runner=FFmpegRunner(recover_native_crash=True)
    fault=FFmpegError(['ffmpeg','output.mp4'],code,'Using font provider coretext\nframe=0')
    with patch.object(runner,'_run_once',side_effect=[fault,'completed']) as run,patch.object(render_recovery,'save_crash') as record:
        assert runner.run(['-c:v','libx264','output.mp4'])=='completed'
    assert runner.recovery_used and run.call_count==2
    assert record.call_count==2


@pytest.mark.parametrize('code',[1,-9,137])
def test_bad_media_cli_or_oom_is_not_mislabelled_as_recoverable_native_fault(code):
    runner=FFmpegRunner(recover_native_crash=True)
    with patch.object(runner,'_run_once',side_effect=FFmpegError([],code,'failure')) as run:
        with pytest.raises(FFmpegError):runner.run(['out.mp4'])
    assert run.call_count==1 and not runner.recovery_used


def test_failed_compatibility_attempt_and_cancellation_are_bounded():
    from clipos.core import render_recovery
    fault=FFmpegError([],-11,'SIGSEGV')
    runner=FFmpegRunner(recover_native_crash=True)
    with patch.object(runner,'_run_once',side_effect=fault) as run,patch.object(render_recovery,'save_crash'):
        with pytest.raises(FFmpegError):runner.run(['out.mp4'])
        assert run.call_count==2
    runner=FFmpegRunner(recover_native_crash=True,cancel_cb=iter([False,True]).__next__)
    with patch.object(runner,'_run_once',side_effect=fault) as run:
        with pytest.raises(FFmpegCancelled):runner.run(['out.mp4'])
        assert run.call_count==1


def test_isolated_fonts_do_not_import_supplemental_directory(tmp_path,monkeypatch):
    from clipos.core import fonts
    real=fonts.find_font_file()
    assert real and real.is_file()
    source=tmp_path/'System'/'Library'/'Fonts'/'Supplemental'
    source.mkdir(parents=True)
    chosen=source/'Arial.ttf';chosen.write_bytes(real.read_bytes())
    (source/'NISC18030.ttf').write_bytes(b'malformed unrelated collection')
    monkeypatch.setattr(fonts,'find_font_file',lambda:chosen)
    monkeypatch.setattr(fonts,'_resolved_dir',None)
    monkeypatch.setattr('clipos.core.config.PATHS',SimpleNamespace(cache=tmp_path/'Application Support'/'cache'))
    directory=fonts.font_dir()
    assert directory!=source and len(list(directory.iterdir()))==1
    assert next(directory.iterdir()).read_bytes()==chosen.read_bytes()
    assert 'Supplemental' not in fonts.fontsdir_arg()
    assert "fontsdir='" in fonts.fontsdir_arg()  # space-bearing user paths stay quoted


@pytest.mark.parametrize('codec',['libx264','libaom-av1'])
def test_actual_captioned_1080_render_survives_injected_initial_native_fault(tmp_path,codec):
    from clipos.video.renderer import _ass_filter
    from clipos.captions.caption_engine import CaptionCue,write_ass,get_style
    from clipos.core import render_recovery
    source=tmp_path/'source.mp4';caption=tmp_path/'caption with spaces.ass';output=tmp_path/'out.mp4'
    extra=['-cpu-used','8','-strict','experimental'] if codec=='libaom-av1' else []
    subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i','color=blue:s=160x90:r=30:d=1',
        '-f','lavfi','-i','sine=frequency=440:duration=1','-c:v',codec,*extra,'-threads','1','-c:a','aac',str(source)],check=True,capture_output=True,timeout=60)
    write_ass(caption,[CaptionCue(0,1,'Stable captions')],get_style('clean_professional'),width=1080,height=1920)
    args=['-i',str(source),'-vf','scale=1080:1920,'+_ass_filter(caption),'-c:v','libx264',
          '-preset','veryfast','-crf','23','-threads','14','-c:a','aac',str(output)]
    runner=FFmpegRunner(recover_native_crash=True);native=runner._run_once;calls=[]
    def invoke(args,total=None):
        calls.append(args)
        if len(calls)==1:raise FFmpegError([require_ffmpeg(),*args],-11,'injected CoreText/scaler/native fault')
        return native(args,total)
    with patch.object(runner,'_run_once',side_effect=invoke),patch.object(render_recovery,'save_crash'):
        runner.run(args)
    info=probe(output)
    assert len(calls)==2 and info.has_video and info.has_audio
    assert info.video.width==1080 and info.video.height==1920 and info.duration>.9
    assert '-vf' in calls[1] and _ass_filter(caption) in calls[1][calls[1].index('-vf')+1]
    import numpy as np
    raw=subprocess.run([require_ffmpeg(),'-v','error','-ss','0.5','-i',str(output),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],check=True,capture_output=True).stdout
    pixels=np.frombuffer(raw,dtype=np.uint8).reshape(-1,3)
    assert ((pixels[:,0]>200)&(pixels[:,1]>200)&(pixels[:,2]>200)).sum()>20  # actual caption pixels


def test_native_intel_release_requires_refreshed_redistributable_engine():
    if platform.system()!='Darwin' or platform.machine() not in ('x86_64','AMD64'):
        pytest.skip('Mandatory on the isolated native Intel release runner')
    text=subprocess.run([require_ffmpeg(),'-version'],capture_output=True,text=True,check=True,timeout=30).stdout
    import re
    version=re.search(r'version (?:n)?(\d+)\.(\d+)',text)
    assert version and tuple(map(int,version.groups()))>=(6,0),text
    assert '--enable-nonfree' not in text,'Do not redistribute a nonfree build'
    filters=subprocess.run([require_ffmpeg(),'-filters'],capture_output=True,text=True,check=True,timeout=30).stdout
    assert ' ass ' in filters and ' drawtext ' in filters


def test_pinned_vendor_rejects_unverified_archive(tmp_path,monkeypatch):
    from scripts import vendor_ffmpeg as vendor
    monkeypatch.setattr(vendor,'ROOT',tmp_path)
    monkeypatch.setattr(vendor,'DEST',tmp_path/'resources'/'ffmpeg')
    def download(url,dest):
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b'not pinned data')
    monkeypatch.setattr(vendor,'_download',download)
    with pytest.raises(RuntimeError,match='checksum'):vendor.fetch_intel_ffmpeg()
    assert not (vendor.DEST/'darwin-x64'/'ffmpeg').exists()


def test_native_fault_keeps_remaining_session_renders_in_compatibility_mode():
    from clipos.core import render_recovery
    first=FFmpegRunner(recover_native_crash=True)
    with patch.object(first,'_run_once',side_effect=[FFmpegError([],-11,'fault'),'done']),patch.object(render_recovery,'save_crash'):
        first.run(['-c:v','libx264','out.mp4'])
    second=FFmpegRunner(recover_native_crash=True)
    with patch.object(second,'_run_once',return_value='done') as run:
        second.run(['-c:v','libx264','out2.mp4'])
    assert second.recovery_used and '-cpuflags' in run.call_args.args[0]
    assert run.call_count==1


def test_bundle_exec_verification_distinguishes_metadata_from_real_binaries(tmp_path):
    from scripts.verify_bundle import media_executables
    folder=tmp_path/'ffmpeg'/'darwin-x64';folder.mkdir(parents=True)
    for name in ('ffmpeg','ffprobe'):
        path=folder/name;path.write_bytes(b'binary');path.chmod(0o755)
    for name in ('ffmpeg-provenance.json','darwin-x64.LICENSE','darwin-x64.README'):
        (folder/name).write_text('data')
    assert {p.name for p in media_executables(tmp_path)}=={'ffmpeg','ffprobe'}

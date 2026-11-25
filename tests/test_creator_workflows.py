"""Regression coverage for real creator workflows and opt-in networking."""
from pathlib import Path
from unittest.mock import patch, Mock
import subprocess
import pytest

from clipos.video.presets import apply_preset, gaming_filter
from clipos.video.renderer import ClipRenderer, RenderSettings, segment_video_filter
from clipos.video.timeline import Timeline
from clipos.core.updates import check_update, version_tuple


def test_presets_are_deterministic_and_not_random_effects():
    s = apply_preset(RenderSettings(), "gaming")
    assert s.editing_preset == "gaming"
    assert not s.sound_effects and not s.smart_reframe
    assert s.caption_style == "clean_professional"


def test_facecam_must_be_inside_source():
    with pytest.raises(ValueError):
        gaming_filter(270, 480, 640, 360, (.9, 0, .3, .3))


def test_crop_is_applied_before_discarding_source_edges():
    tl = Timeline.from_clip(0, 2)
    tl.segments[0].zoom = 1.5
    tl.segments[0].crop_x = .9
    vf = segment_video_filter(tl.segments[0], 270, 480)
    assert 'scale=406:720' in vf
    assert '(iw-ow)*0.90000' in vf
    assert 'zoompan' not in vf


def test_update_ignores_current_and_prereleases():
    response = Mock()
    response.json.return_value = {'tag_name': 'v1.0.0', 'assets': []}
    with patch('clipos.core.updates.requests.get', return_value=response):
        assert check_update('1.0.0') is None
    assert version_tuple('v1.10.0') > version_tuple('1.9.0')


def test_update_selects_intel_installer_not_arm():
    response = Mock()
    response.json.return_value = {'tag_name': 'v1.1.0', 'assets': [
        {'name': 'CLIPOS.dmg', 'browser_download_url': 'https://github.com/Analoggeek/AiFreeClipping/releases/download/v1.1.0/CLIPOS.dmg'},
        {'name': 'CLIPOS-intel.dmg', 'browser_download_url': 'https://github.com/Analoggeek/AiFreeClipping/releases/download/v1.1.0/CLIPOS-intel.dmg'}]}
    with patch('clipos.core.updates.requests.get', return_value=response), patch('clipos.core.updates.platform.system', return_value='Darwin'), patch('clipos.core.updates.platform.machine', return_value='x86_64'):
        assert check_update('1.0.0')['name'] == 'CLIPOS-intel.dmg'


def test_youtube_uses_downloader_not_direct_html_download(tmp_path):
    from clipos.video.importer import import_url
    with patch('clipos.video.youtube.download_youtube', return_value='imported') as download:
        assert import_url('https://www.youtube.com/watch?v=abcdefghijk', tmp_path) == 'imported'
        download.assert_called_once()


@pytest.fixture
def video(tmp_path):
    from clipos.core.ffmpeg import require_ffmpeg
    try:
        ffmpeg = require_ffmpeg()
    except Exception:
        pytest.skip('FFmpeg not installed')
    source = tmp_path / 'source.mp4'
    subprocess.run([ffmpeg, '-y', '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=15:duration=2',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)], check=True, capture_output=True)
    return source


def test_real_gaming_render_has_selected_layout(video, tmp_path):
    s = apply_preset(RenderSettings(width=270, height=480, fps=15, encoder_preference='cpu', show_captions=False), 'gaming')
    s.auto_facecam = False  # This fixture tests manual composition, not detection.
    result = ClipRenderer(tmp_path/'work').render(video, tmp_path/'game.mp4', 0, 1.5, s)
    assert result.width == 270 and result.height == 480
    assert result.duration > 1
    assert not result.warnings


def test_timeline_edits_survive_save_and_render(video, tmp_path):
    timeline = Timeline.from_clip(0, 2)
    timeline.segments[0].zoom = 1.5
    timeline.segments[0].crop_x = .9
    timeline.segments[0].muted = True
    timeline.save(tmp_path/'edit.json')
    restored = Timeline.load(tmp_path/'edit.json')
    result = ClipRenderer(tmp_path/'work').render_timeline(video, tmp_path/'edited.mp4', restored,
        RenderSettings(width=270, height=480, fps=15, encoder_preference='cpu', show_captions=False))
    assert result.width == 270 and result.duration > 1
    assert not result.warnings
    from clipos.core.ffmpeg import require_ffmpeg
    out = subprocess.run([require_ffmpeg(), '-i', str(tmp_path/'edited.mp4'), '-af', 'volumedetect', '-f', 'null', '-'], capture_output=True, text=True)
    assert 'max_volume: -91' in out.stderr or 'max_volume: -inf' in out.stderr


def test_captions_retime_after_trim_and_speed():
    from clipos.captions.caption_engine import CaptionCue, retime_cues
    cues = [CaptionCue(100, 102, 'hello', [{'w': 'hello', 's': 100, 'e': 102}])]
    result = retime_cues(cues, [(100, 104, 2)])
    assert result[0].start == 0 and result[0].end == 1
    assert result[0].words[0]['e'] == 1


@pytest.mark.parametrize('encoder,accel', [('h264_nvenc','nvenc'),
    ('h264_videotoolbox','videotoolbox'),('h264_qsv','qsv')])
def test_hardware_failure_retries_with_cpu(video, tmp_path, encoder, accel):
    from clipos.core.ffmpeg import FFmpegRunner
    from clipos.core.hardware import EncoderChoice
    original_run = FFmpegRunner.run
    calls = []
    def run(runner, args, **kwargs):
        calls.append(list(args))
        if len(calls) == 1:
            raise RuntimeError('Device driver unavailable')
        return original_run(runner, args, **kwargs)
    with patch('clipos.video.renderer.choose_encoder', side_effect=[
        EncoderChoice(video_encoder=encoder, hw_accel=accel), EncoderChoice()]), patch.object(FFmpegRunner, 'run', run):
        result = ClipRenderer(tmp_path/'work').render(video, tmp_path/'fallback.mp4', 0, 1,
            RenderSettings(width=270, height=480, fps=15, show_captions=False, sound_effects=False))
    assert len(calls) == 2
    assert 'libx264' in calls[1] and encoder not in calls[1]
    if accel=='videotoolbox':
        assert calls[0][calls[0].index('-allow_sw')+1]=='0'
    assert result.size_bytes > 0


def test_intel_build_uses_isolated_environment():
    root = Path(__file__).resolve().parents[1]
    shell = (root/'scripts/setup_intel_python.sh').read_text()
    assert 'arch -x86_64 "$base" -m venv .venv-intel' in shell
    assert 'exec arch -x86_64' in shell
    assert 'sys.prefix != sys.base_prefix' in shell
    for name in ('build-installers.yml', 'release.yml'):
        text = (root/'.github/workflows'/name).read_text()
        assert 'bash scripts/setup_intel_python.sh' in text
        assert 'CLIPOS_BUILD_PYTHON="$CLIPOS_INTEL_PYTHON"' in text
    release = (root/'.github/workflows/release.yml').read_text()
    assert "if: always() && needs.build.result == 'success'" in release


def test_release_archives_apps_before_artifact_upload():
    root = Path(__file__).resolve().parents[1]
    release = (root/'.github/workflows/release.yml').read_text()
    assert 'tar -czf dist/CLIPOS-arm64.app.tar.gz -C dist CLIPOS-arm64.app' in release
    assert release.index('Archive native app permissions') < release.index('Upload the build artifacts')


def test_recovered_timeline_reopens_and_really_renders(video,tmp_path):
    from clipos.core.ffmpeg import probe
    path=tmp_path/'edit.json'
    timeline=Timeline.from_clip(0,2,source_duration=2)
    timeline.set_speed(timeline.segments[0].id,2)
    timeline.save(path)
    timeline.split_at(1)
    timeline.save(path)
    path.write_text('{broken')
    restored=Timeline.load(path)
    assert restored.recovered_from and restored.duration==pytest.approx(1)
    result=ClipRenderer(tmp_path/'work').render_timeline(video,tmp_path/'restored.mp4',restored,
        RenderSettings(width=270,height=480,fps=15,show_captions=False,sound_effects=False,
                       encoder_preference='cpu'))
    assert result.size_bytes>0
    info=probe(tmp_path/'restored.mp4')
    assert (info.video.width,info.video.height)==(270,480)
    assert info.duration==pytest.approx(1,abs=.2)


def test_reopened_undo_redo_changes_real_export_duration(video,tmp_path):
    from clipos.core.ffmpeg import probe
    path=tmp_path/'history.json'
    timeline=Timeline.from_clip(0,2,source_duration=2)
    timeline.set_speed(timeline.segments[0].id,2)
    timeline.save(path)
    restored=Timeline.load(path)
    settings=RenderSettings(width=270,height=480,fps=15,show_captions=False,
                            sound_effects=False,encoder_preference='cpu')
    renderer=ClipRenderer(tmp_path/'work')
    assert restored.undo()
    renderer.render_timeline(video,tmp_path/'undone.mp4',restored,settings)
    assert probe(tmp_path/'undone.mp4').duration==pytest.approx(2,abs=.2)
    restored.save(path)
    restored=Timeline.load(path)
    assert restored.redo()
    renderer.render_timeline(video,tmp_path/'redone.mp4',restored,settings)
    assert probe(tmp_path/'redone.mp4').duration==pytest.approx(1,abs=.2)


@pytest.mark.parametrize('style',['studio_word_pop','impact_slide_up','arcade_word_reveal'])
def test_new_animated_caption_styles_reach_real_clip_export(video,tmp_path,style):
    from clipos.captions.caption_engine import CaptionCue
    from clipos.core.ffmpeg import probe
    cue=CaptionCue(0,1,'Real captions',[
        {'w':'Real','s':0,'e':.45},{'w':'captions','s':.5,'e':1}])
    result=ClipRenderer(tmp_path/'work').render(video,tmp_path/'animated.mp4',0,1,
        RenderSettings(width=270,height=480,fps=15,show_captions=True,
                       caption_style=style,caption_size=28,caption_position='middle',
                       sound_effects=False,encoder_preference='cpu'),cues=[cue])
    assert result.size_bytes>0
    info=probe(tmp_path/'animated.mp4')
    assert info.has_video and info.has_audio
    assert (info.video.width,info.video.height)==(270,480)
    ass=list((tmp_path/'work').rglob('*.ass'))
    assert ass
    content=ass[0].read_text()
    if 'slide' in style:
        assert '\\move(' in content
    else:
        assert '\\t(' in content or '\\fad(' in content


@pytest.mark.parametrize('timeline_mode',[False,True])
@pytest.mark.parametrize('ducking',[False,True])
def test_music_is_mixed_into_actual_range_and_timeline_exports(video,tmp_path,timeline_mode,ducking,monkeypatch):
    import numpy as np
    from clipos.core.ffmpeg import require_ffmpeg,probe
    ffmpeg=require_ffmpeg()
    music=tmp_path/'music.wav'
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i',
        'sine=frequency=1000:sample_rate=48000:duration=0.7','-y',str(music)],
        check=True,capture_output=True,timeout=15)
    settings=RenderSettings(width=270,height=480,fps=15,show_captions=False,
        normalize_audio=False,noise_reduction=False,sound_effects=False,encoder_preference='cpu',
        background_music=str(music),bgm_volume=.5,bgm_ducking=ducking)
    output=tmp_path/'mixed.mp4'
    from clipos.core.ffmpeg import FFmpegRunner
    original_run=FFmpegRunner.run
    def bounded_music_run(self,args,*a,**kw):
        loop=args.index('-stream_loop')
        assert args[loop+1]=='2'  # ceil(edited duration / 0.7)-1, never infinite
        # Bound the demuxed input itself, not only atrim downstream: FFmpeg6
        # otherwise keeps reading an infinite music source after filter EOF.
        assert args[loop+2]=='-t'
        assert float(args[loop+3])==pytest.approx(1.5 if timeline_mode else 2)
        assert args[loop+4]=='-i' and args[loop+5]==str(music)
        return original_run(self,args,*a,**kw)
    monkeypatch.setattr(FFmpegRunner,'run',bounded_music_run)
    renderer=ClipRenderer(tmp_path/'work')
    if timeline_mode:
        timeline=Timeline.from_clip(0,2,source_duration=2)
        timeline.split_at(1)
        timeline.set_speed(timeline.segments[0].id,2)
        result=renderer.render_timeline(video,output,timeline,settings)
        expected_duration=1.5
    else:
        result=renderer.render(video,output,0,2,settings)
        expected_duration=2
    assert result.size_bytes>0
    assert any('Background music:' in step for step in result.steps)
    assert probe(output).duration==pytest.approx(expected_duration,abs=.2)
    decoded=subprocess.run([ffmpeg,'-v','error','-i',str(output),'-vn','-ac','1',
        '-ar','48000','-f','f32le','-'],check=True,capture_output=True,timeout=15)
    samples=np.frombuffer(decoded.stdout,dtype='<f4')
    segment=samples[round(.9*48000):round(1.3*48000)]
    # Music remains measurable beyond its 0.7 s source: looping really executes.
    t=np.arange(len(segment))/48000
    amplitude=2*abs(np.mean(segment*np.exp(-2j*np.pi*1000*t)))
    assert amplitude>.001


@pytest.mark.parametrize('speed',[.25,4])
def test_extreme_editor_speeds_really_export_with_pitch_preserved(video,tmp_path,speed):
    import numpy as np
    from clipos.core.ffmpeg import require_ffmpeg,probe
    timeline=Timeline.from_clip(0,2,source_duration=2)
    timeline.set_speed(timeline.segments[0].id,speed)
    settings=RenderSettings(width=180,height=320,fps=15,show_captions=False,
        normalize_audio=False,noise_reduction=False,sound_effects=False,encoder_preference='cpu')
    output=tmp_path/'speed.mp4'
    result=ClipRenderer(tmp_path/'work').render_timeline(video,output,timeline,settings)
    assert result.size_bytes>0
    assert probe(output).duration==pytest.approx(2/speed,abs=.2)
    decoded=subprocess.run([require_ffmpeg(),'-v','error','-i',str(output),'-vn',
        '-ar','16000','-ac','1','-f','f32le','-'],check=True,capture_output=True,timeout=15)
    samples=np.frombuffer(decoded.stdout,dtype='<f4')
    segment=samples[len(samples)//4:3*len(samples)//4]
    frequencies=np.fft.rfftfreq(len(segment),d=1/16000)
    peak=frequencies[np.argmax(abs(np.fft.rfft(segment)))]
    assert peak==pytest.approx(440,abs=12)  # Tempo edit, not pitch shifting.

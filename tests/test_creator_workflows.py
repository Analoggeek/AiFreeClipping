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
    assert s.caption_style == "neon_gaming"


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


def test_hardware_failure_retries_with_cpu(video, tmp_path):
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
        EncoderChoice(video_encoder='h264_nvenc', hw_accel='nvenc'), EncoderChoice()]), patch.object(FFmpegRunner, 'run', run):
        result = ClipRenderer(tmp_path/'work').render(video, tmp_path/'fallback.mp4', 0, 1,
            RenderSettings(width=270, height=480, fps=15, show_captions=False, sound_effects=False))
    assert len(calls) == 2
    assert 'libx264' in calls[1] and 'h264_nvenc' not in calls[1]
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

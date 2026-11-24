"""Facecam and offline inference regressions retained from v2."""
from pathlib import Path
from unittest.mock import patch, Mock
import json
import sys
import pytest
import numpy as np

from clipos.ai.gaming_layout import infer_layout, GamingLayout
from clipos.ai.visual_analysis import Face
from clipos.video.presets import gaming_filter


def observations(cx=.12, cy=.18):
    return [Face(cx-.03, cy-.04, .06, .08, timestamp=float(t)) for t in range(12)]


def test_persistent_corner_face_produces_nonoverlapping_panels():
    layout = infer_layout(observations(), list(range(12)))
    assert layout and layout.confidence >= .8
    x,y,w,h = layout.facecam
    a,b,c,d = layout.gameplay
    assert 0 <= x < x+w <= 1 and 0 <= y < y+h <= 1
    assert x+w <= a+.001 or a+c <= x+.001 or y+h <= b+.001 or b+d <= y+.001


def test_missing_or_centre_character_is_not_invented_as_facecam():
    assert infer_layout([], list(range(12))) is None
    assert infer_layout(observations(.5,.5), list(range(12))) is None
    assert infer_layout(observations()[:2], list(range(12))) is None


def test_transient_faces_do_not_become_player_panel():
    assert infer_layout(observations()[:3], list(range(30))) is None


def test_gameplay_is_crop_fill_not_letterboxed():
    graph = gaming_filter(270,480,640,360,(0,0,.2,.3),(.2,0,.8,1))
    assert 'pad=' not in graph and 'force_original_aspect_ratio=increase' in graph
    assert 'vstack=inputs=2' in graph
    assert 'split=' not in gaming_filter(270,480,640,360,None)


def test_no_mps_is_returned_for_ctranslate2():
    from clipos.ai.transcription import _resolve_device
    with patch('ctranslate2.get_cuda_device_count', return_value=0):
        assert _resolve_device() == ('cpu','int8')


def test_sampling_is_bounded_in_memory_and_covers_long_sources():
    from clipos.ai.visual_analysis import sample_frames
    fake = Mock()
    fake.CAP_PROP_FPS, fake.CAP_PROP_FRAME_WIDTH, fake.CAP_PROP_FRAME_HEIGHT, fake.CAP_PROP_FRAME_COUNT = range(4)
    cap = fake.VideoCapture.return_value
    cap.isOpened.return_value = True
    cap.get.side_effect = lambda key: {0:60,1:3840,2:2160,3:432000}[key]
    cap.read.return_value = (True,np.zeros((1080,1920,3),dtype=np.uint8))
    fake.resize.side_effect = lambda frame, size: np.zeros((size[1],size[0],3),dtype=np.uint8)
    with patch('clipos.ai.visual_analysis.cv2_module',return_value=fake):
        frames,times,w,h = sample_frames('long.mp4')
    assert len(frames) <= 180 and max(f.shape[1] for f in frames) <= 768
    assert times[-1] > 7000
    cap.release.assert_called_once()


def test_database_instances_do_not_share_same_thread_connection(tmp_path):
    from clipos.db.database import Database
    a,b = Database(tmp_path/'a.db'),Database(tmp_path/'b.db')
    try:
        a.set_setting('different', 'one')
        b.set_setting('different', 'two')
        assert a.get_setting('different') == 'one'
        assert b.get_setting('different') == 'two'
    finally:
        a.close();b.close()


def test_real_face_detection_and_automatic_composition(tmp_path):
    """Real YuNet, real decoded frames, real FFmpeg; not a mocked AI result."""
    import cv2
    import subprocess
    from clipos.core.ffmpeg import require_ffmpeg
    from clipos.ai.gaming_layout import detect_layout
    from clipos.video.renderer import ClipRenderer, RenderSettings
    from clipos.video.presets import apply_preset
    frame = np.zeros((540,960,3),dtype=np.uint8)
    frame[:]=[35,120,35]
    portrait = cv2.imread(str(Path(__file__).parent/'assets'/'facecam_sample.jpg'))
    frame[:200,:200] = portrait
    image = tmp_path/'frame.png';cv2.imwrite(str(image),frame)
    video = tmp_path/'fixture.mp4'
    subprocess.run([require_ffmpeg(),'-y','-loop','1','-i',str(image),'-t','2',
        '-r','15','-c:v','libx264','-pix_fmt','yuv420p',str(video)],capture_output=True,check=True)
    layout = detect_layout(video,0,2)
    assert layout is not None and layout.confidence > .6
    settings = apply_preset(RenderSettings(width=270,height=480,fps=15,
        encoder_preference='cpu',show_captions=False),'gaming')
    result = ClipRenderer(tmp_path/'work').render(video,tmp_path/'edited.mp4',0,2,settings)
    assert result.width == 270 and result.height == 480
    assert not result.warnings
    assert any('Facecam confidence' in step for step in result.steps)
    cap = cv2.VideoCapture(str(tmp_path/'edited.mp4'))
    ok, output = cap.read();cap.release()
    assert ok
    # Gameplay above is green; the photograph has actually moved below.
    assert output[80,:,1].mean() > output[80,:,2].mean()+40
    assert output[400:,:,2].std() > 5


def test_partial_model_cache_is_not_reported_installed(tmp_path):
    from clipos.ai.transcription import model_installed, local_model_path
    fake_paths = Mock(models=tmp_path)
    folder = tmp_path/'whisper'/'Systran--faster-whisper-base'
    folder.mkdir(parents=True)
    (folder/'config.json').write_text('{}')
    with patch('clipos.ai.transcription.PATHS',fake_paths), patch.dict('os.environ', {'HF_HOME':str(tmp_path/'hf')}):
        assert not model_installed('base')
        (folder/'model.bin').write_bytes(b'model fixture, not used for inference')
        (folder/'tokenizer.json').write_text('{}')
        assert local_model_path('base') == folder


def test_split_captions_avoid_covering_player_face():
    from clipos.captions.caption_engine import render_ass, get_style
    text = render_ass([],get_style('clean_professional'),height=1920,position_override='split')
    assert ',2,60,60,672,1' in text

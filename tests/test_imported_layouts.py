"""Actual offline rendering for every adapted layout, not just graph snapshots."""
from pathlib import Path
from unittest.mock import patch
import pytest
from clipos.video.layouts import CATALOG,geometry
from clipos.video.presets import gaming_filter
from clipos.video.renderer import ClipRenderer,RenderSettings
from clipos.core.ffmpeg import ffmpeg_available,run_ffmpeg,probe


@pytest.fixture(scope='module')
def source(tmp_path_factory):
    if not ffmpeg_available():pytest.skip('FFmpeg unavailable')
    path=tmp_path_factory.mktemp('layouts')/'source.mp4'
    run_ffmpeg(['-f','lavfi','-i','testsrc2=size=320x180:rate=10:duration=1','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(path)])
    return path


@pytest.mark.parametrize('layout',[item[0] for item in CATALOG])
def test_every_layout_really_renders(source,tmp_path,layout):
    settings=RenderSettings(width=180,height=320,fps=10,editing_preset='gaming',studio_layout=layout,camera_size=.32,auto_facecam=False,facecam_rect=(0.,0.,.25,.4),gameplay_rect=(.25,0.,.75,1.),encoder_preference='cpu',threads=1,show_captions=False,remove_silence=False,sound_effects=False)
    out=tmp_path/(layout+'.mp4')
    ClipRenderer(tmp_path/'work').render(source,out,0,1,settings)
    info=probe(out)
    assert info.video.width==180 and info.video.height==320 and info.duration>.8


@pytest.mark.parametrize('layout',[item[0] for item in CATALOG])
def test_camera_layout_without_camera_never_invents_one(layout):
    graph=gaming_filter(180,320,320,180,None,layout=layout,camera_size=.32)
    if layout not in ('blur','fill','game'):
        assert 'overlay' not in graph and 'split' not in graph


@pytest.mark.parametrize('size',[float('nan'),float('inf'),.19,.51])
def test_invalid_camera_size_rejected(size):
    with pytest.raises(ValueError):gaming_filter(180,320,320,180,None,camera_size=size)


@pytest.mark.parametrize('layout',['pip_br','circle','blur','side'])
def test_layouts_work_on_multisegment_timeline_with_captions(source,tmp_path,layout):
    from clipos.video.timeline import Timeline
    from clipos.captions.caption_engine import CaptionCue
    timeline=Timeline.from_clip(0,1)
    assert timeline.split_at(.5)
    settings=RenderSettings(width=180,height=320,fps=10,editing_preset='gaming',studio_layout=layout,camera_size=.3,auto_facecam=False,facecam_rect=(0.,0.,.25,.4),gameplay_rect=(.25,0.,.75,1.),encoder_preference='cpu',threads=1,show_captions=True,caption_size=24,sound_effects=False)
    out=tmp_path/'timeline.mp4'
    ClipRenderer(tmp_path/'work').render_timeline(source,out,timeline,settings,cues=[CaptionCue(.1,.9,'Real layout caption',[])])
    info=probe(out)
    assert info.video.width==180 and info.has_audio and info.duration>.8


def test_shared_settings_and_old_defaults_are_preserved(tmp_path):
    from clipos.db.database import Database
    from clipos.core.editing import render_settings
    db=Database(tmp_path/'settings.db')
    try:
        assert render_settings(db).studio_layout=='bottom'
        db.set_settings({'studio_layout':'pip_br','camera_size':.4})
        settings=render_settings(db)
        assert settings.studio_layout=='pip_br' and settings.camera_size==.4
        assert RenderSettings.from_dict(settings.to_dict()).studio_layout=='pip_br'
    finally:db.close()

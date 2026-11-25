"""Actual decoded-pixel crop regressions; no mocked encoder or model evidence."""
import json
import subprocess
from unittest.mock import patch

import numpy as np
import pytest

from clipos.core.ffmpeg import require_ffmpeg
from clipos.db.database import Database
from clipos.video.crop_config import CropConfig, save_crop, load_crop
from clipos.video.renderer import ClipRenderer, RenderSettings
from clipos.video.pipeline import ClipOSPipeline, AnalysisResult


def source(tmp_path,w,h):
    path=tmp_path/f'split-{w}-{h}.mp4'
    subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i',
        f'color=red:s={w}x{h}:r=10:d=2,drawbox=x=iw/2:y=0:w=iw/2:h=ih:color=blue:t=fill',
        '-c:v','libx264','-pix_fmt','yuv420p','-y',str(path)],check=True,capture_output=True)
    return path


def decode(path):
    from clipos.ai.visual_analysis import cv2_module
    cv2=cv2_module();cap=cv2.VideoCapture(str(path))
    try:
        ok,image=cap.read();assert ok
        return image
    finally:cap.release()


def settings(crop):
    return RenderSettings(crop_config=crop.to_dict(),editing_preset='gaming',
        auto_facecam=True,smart_reframe=True,show_captions=False,remove_silence=False,
        color_correct=False,sound_effects=False,transitions=False,normalize_audio=False,
        noise_reduction=False,encoder_preference='cpu',threads=2)


@pytest.mark.parametrize('dimensions',[(320,180),(180,320),(240,240)])
@pytest.mark.parametrize('aspect,output',[('9:16',(90,160)),('1:1',(128,128)),('16:9',(160,90))])
def test_selected_region_matches_all_encoded_pixels_across_sources(tmp_path,dimensions,aspect,output):
    w,h=dimensions;path=source(tmp_path,w,h)
    crop=CropConfig.from_selection((.5,0,.5,1),w,h,aspect,output)
    with patch('clipos.ai.gaming_layout.detect_layout',side_effect=AssertionError('AI may not change user framing')):
        result=ClipRenderer(tmp_path/'work').render(path,tmp_path/'clip.mp4',0,1,settings(crop))
    image=decode(tmp_path/'clip.mp4')
    assert (result.width,result.height)==output
    assert (image.shape[1],image.shape[0])==output
    assert np.mean(image[:,:,0])>230 and np.mean(image[:,:,2])<15  # blue, no black bars/red
    assert result.encoder
    assert CropConfig.from_dict(json.loads(json.dumps(crop.to_dict())))==crop


def test_project_crop_persists_across_clips_and_changed_selection(tmp_path):
    path=source(tmp_path,320,180);db=Database(tmp_path/'library.db')
    try:
        pid=db.create_project(name='Crop regression',source_path=str(path),width=320,height=180,duration=2)
        pipe=ClipOSPipeline(db,pid)
        crop=CropConfig.from_selection((.5,0,.5,1),320,180,'1:1',(128,128));save_crop(db,pid,crop)
        for i,(start,end) in enumerate([(0,.7),(.8,1.5)]):
            cid=db.create_clip(project_id=pid,title='Clip',start_time=start,end_time=end,duration=end-start)
            result=pipe.render_clip(cid,tmp_path/f'clip-{i}.mp4',settings(crop),AnalysisResult(duration=2),make_thumbnails=False)
            assert (result['width'],result['height'])==(128,128)
            assert decode(tmp_path/f'clip-{i}.mp4')[:,:,0].mean()>230
        db.close();db=Database(tmp_path/'library.db');assert load_crop(db,pid)==crop
        changed=CropConfig.from_selection((0,0,.5,1),320,180,'1:1',(128,128));save_crop(db,pid,changed)
        pipe=ClipOSPipeline(db,pid)
        pipe.render_clip(cid,tmp_path/'changed.mp4',settings(crop),AnalysisResult(duration=2),make_thumbnails=False)
        assert decode(tmp_path/'changed.mp4')[:,:,2].mean()>230  # saved project crop overrides stale caller
    finally:db.close()


@pytest.mark.parametrize('selection',[(0,0,0,1),(-.1,0,.5,1),(0,0,2,1),(float('nan'),0,.5,1),(0,0,.00001,.00001)])
def test_invalid_selection_never_falls_back(selection):
    with pytest.raises(ValueError):CropConfig.from_selection(selection,320,180,'9:16')


def test_changed_source_fails_and_preserves_previous_output(tmp_path):
    path=source(tmp_path,320,180)
    crop=CropConfig.from_selection((0,0,1,1),640,360,'9:16')
    output=tmp_path/'keep.mp4';output.write_bytes(b'previous completed output')
    with pytest.raises(ValueError,match='Source dimensions changed'):
        ClipRenderer(tmp_path/'work').render(path,output,0,1,settings(crop))
    assert output.read_bytes()==b'previous completed output'
    assert not list(tmp_path.glob('.clipos-render-*'))

"""Real independent caption/effect/dissolve lanes, not metadata-only buttons."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from clipos.video.multitrack import MultitrackProject
from clipos.video.multitrack_preview import FrameCompositor
from clipos.video.multitrack_render import export_project
from tests.test_multitrack import media


def frame(project,time):
    compositor=FrameCompositor()
    try:return compositor.frame(project,time)
    finally:compositor.close()


def decoded(path,time):
    from clipos.ai.visual_analysis import cv2_module
    cv2=cv2_module();capture=cv2.VideoCapture(str(path))
    try:
        capture.set(cv2.CAP_PROP_POS_MSEC,time*1000);ok,image=capture.read()
        assert ok
        return image
    finally:capture.release()


def test_caption_lane_renders_real_text_preview_and_mp4_and_roundtrips(tmp_path):
    project=MultitrackProject(width=320,height=180,fps=10)
    lane,item=project.add_caption('REAL CAPTION',.2,1.2,'bold_viral',{'primary_override':'#00FF00'})
    assert not frame(project,.1).any()
    visible=frame(project,.5)
    assert np.count_nonzero(visible[:,:,1]>100)>80
    assert not frame(project,1.4).any()
    path=tmp_path/'caption.clipos-mt.json';project.save(path)
    reopened=MultitrackProject.load(path)
    assert reopened.find(lane,item)[1].text=='REAL CAPTION'
    project.change_item(lane,item,text='EDITED CAPTION')
    assert project.undo() and project.find(lane,item)[1].text=='REAL CAPTION'
    assert project.redo() and project.find(lane,item)[1].text=='EDITED CAPTION'
    result=export_project(reopened,tmp_path/'caption.mp4',tmp_path/'work',encoder='cpu')
    assert result.size_bytes>0
    actual=decoded(tmp_path/'caption.mp4',.5)
    assert np.count_nonzero(actual[:,:,1]>100)>50
    assert np.mean(decoded(tmp_path/'caption.mp4',.1))<3
    reopened.split(lane,item,.7)
    assert len(reopened.lanes[0].items)==2 and reopened.lanes[0].items[1].source_in==0


def test_effect_lane_is_time_bounded_and_changes_preview_and_real_export(media,tmp_path):
    project=MultitrackProject(width=160,height=90,fps=10);project.import_media(media[0])
    lane,item=project.add_effect(.5,.8,saturation=0.)
    before=frame(project,.2).mean(axis=(0,1));during=frame(project,.8).mean(axis=(0,1));after=frame(project,1.6).mean(axis=(0,1))
    assert before[2]>before[0]+100 and np.ptp(during)<8 and after[2]>after[0]+100
    result=export_project(project,tmp_path/'effect.mp4',tmp_path/'work',encoder='cpu')
    assert result.size_bytes>0
    actual=decoded(tmp_path/'effect.mp4',.8).mean(axis=(0,1))
    assert np.ptp(actual)<8
    project.lane_state(lane,enabled=False)
    assert np.ptp(frame(project,.8).mean(axis=(0,1)))>100


def dissolve_project(media):
    project=MultitrackProject(width=160,height=90,fps=10)
    project.import_media(media[0]);project.import_media(media[1])
    outgoing=project.lanes[0];incoming=project.lanes[2]
    project.change_item(outgoing.id,outgoing.items[0].id,length=1.5)
    project.change_item(incoming.id,incoming.items[0].id,at=1.)
    selected=project.add_dissolve(incoming.id,incoming.items[0].id,.5)
    return project,selected,incoming.id,incoming.items[0].id


def test_dissolve_is_actual_blended_pixels_with_validated_references(media,tmp_path):
    project,selected,lane,item=dissolve_project(media)
    before=frame(project,.8).mean(axis=(0,1));middle=frame(project,1.2).mean(axis=(0,1));after=frame(project,1.7).mean(axis=(0,1))
    assert before[2]>200 and before[0]<20
    assert middle[0]>50 and middle[2]>50
    assert after[0]>200 and after[2]<20
    export_project(project,tmp_path/'dissolve.mp4',tmp_path/'work',encoder='cpu')
    actual=decoded(tmp_path/'dissolve.mp4',1.2).mean(axis=(0,1))
    assert actual[0]>50 and actual[2]>50
    unchanged=project.to_dict()
    with pytest.raises(ValueError):project.change_item(lane,item,at=0.)
    assert project.to_dict()==unchanged
    with pytest.raises(ValueError):project.remove(lane,item)
    project.remove(*selected)
    project.remove(lane,item)
    assert project.undo()


@pytest.mark.parametrize('values',[
    {'media_id':'missing'},{'source_in':True},{'speed':2.}, {'text':''},
    {'caption_style':'nonexistent'},{'caption_options':{'font_file':'/etc/passwd'}},
    {'caption_options':{'font_override':'bad\nfont'}}, {'caption_options':{'primary_override':'red'}},
    {'caption_options':{'size_override':True}}, {'length':float('nan')},
])
def test_overlay_validation_rejects_forged_state(values):
    project=MultitrackProject();project.add_caption('Actual text',0.,1.)
    data=project.to_dict();data['lanes'][0]['items'][0].update(values)
    with pytest.raises(ValueError):MultitrackProject.from_dict(data)


def test_caption_timing_offset_is_clipped_to_actual_lane_boundaries(tmp_path):
    project=MultitrackProject(width=320,height=180,fps=10)
    project.add_caption('OFFSET',.2,1.,options={'timing_offset':.3})
    assert not frame(project,.3).any()
    assert frame(project,.8).any()
    assert not frame(project,1.2).any()





def test_caption_preview_preserves_video_below_its_transparent_pixels(media):
    project=MultitrackProject(width=320,height=180,fps=10);project.import_media(media[0])
    project.add_caption('TEXT OVER VIDEO',0.,1.)
    image=frame(project,.5)
    assert image[10:30,10:30,2].mean()>200
    assert image[10:30,10:30,0].mean()<20
    assert np.count_nonzero(np.min(image,axis=2)>150)>30

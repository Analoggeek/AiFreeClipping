"""Real caption customization and persisted per-layer visual controls."""
from dataclasses import asdict
from unittest.mock import patch

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect

from clipos.captions.caption_engine import CaptionCue, get_style, render_ass
from clipos.captions.customization import categories_for, customize_style, offset_cues
from clipos.db.database import Database
from clipos.ui.main_window import MainWindow
from clipos.video.multitrack import MultitrackProject
from clipos.video.multitrack_preview import FrameCompositor
from clipos.video.multitrack_render import export_project, video_effects
from tests.test_multitrack import media, layered


def test_caption_overrides_are_real_ass_and_do_not_mutate_presets():
    style = get_style('bold_viral')
    before = asdict(style)
    cues = [CaptionCue(1, 2, 'REAL WORDS', [{'w':'REAL','s':1,'e':1.4}, {'w':'WORDS','s':1.5,'e':2}])]
    ass = render_ass(cues, style, primary_override='#123456', highlight_override='#ABCDEF',
                     outline_override='#234567', animation_override='slide_left',
                     position_override='top', alignment_override='right', timing_offset=.25)
    assert '&H00563412' in ass and '&H00EFCDAB' in ass and '&H00674523' in ass
    assert '\\move(' in ass and ',9,60,60,' in ass
    assert '0:00:01.25,0:00:02.25' in ass
    assert asdict(style) == before and cues[0].start == 1
    shifted = offset_cues(cues, .25)
    assert shifted[0].words[0]['s'] == 1.25 and cues[0].words[0]['s'] == 1


@pytest.mark.parametrize('kwargs', [dict(primary='red'), dict(primary='#12'),
    dict(animation='shell'), dict(alignment='bottom;anything')])
def test_caption_override_validation(kwargs):
    with pytest.raises(ValueError):customize_style(get_style('bold_viral'), **kwargs)


@pytest.mark.parametrize('offset', [float('nan'), float('inf'), 11, True])
def test_timing_validation(offset):
    with pytest.raises(ValueError):offset_cues([], offset)


def test_categories_cover_real_presets():
    assert 'Gaming' in categories_for('neon_gaming')
    assert 'Podcast' in categories_for('modern_podcast')
    assert 'Cinematic' in categories_for('cinematic')
    assert 'Reaction' in categories_for('arcade_pop')




def test_per_layer_color_rotation_undo_reopen_and_real_export(media,tmp_path):
    project=layered(media);lane=project.lanes[0];item=lane.items[0]
    compositor=FrameCompositor()
    try:before=compositor.frame(project,.2)
    finally:compositor.close()
    project.change_item(lane.id,item.id,brightness=.15,saturation=0.,rotation=12.,contrast=.8)
    selected=project.find(lane.id,item.id)[1]
    assert 'rotate=' in video_effects(selected) and 'saturation=0.' in video_effects(selected)
    path=tmp_path/'color.clipos-mt.json';project.save(path)
    reopened=MultitrackProject.load(path)
    assert reopened.find(lane.id,item.id)[1].rotation==12.
    assert project.undo() and project.find(lane.id,item.id)[1].rotation==0
    assert project.redo() and project.find(lane.id,item.id)[1].rotation==12
    compositor=FrameCompositor()
    try:after=compositor.frame(reopened,.2)
    finally:compositor.close()
    assert np.mean(np.abs(before.astype(float)-after.astype(float)))>10
    result=export_project(reopened,tmp_path/'color.mp4',tmp_path/'render',encoder='cpu')
    assert result.size_bytes>0
    audio_lane=reopened.lanes[1]
    with pytest.raises(ValueError):reopened.change_item(audio_lane.id,audio_lane.items[0].id,rotation=1.)


def test_wrapping_toolbar_fits_narrow_workspace():
    from PySide6.QtWidgets import QWidget,QPushButton
    from clipos.ui.widgets.flow_layout import FlowLayout
    app=QApplication.instance() or QApplication([])
    widget=QWidget();layout=FlowLayout(widget)
    for index in range(8):layout.addWidget(QPushButton('Editing action '+str(index)))
    widget.show()
    try:
        wide=layout.heightForWidth(1200);narrow=layout.heightForWidth(350)
        assert narrow>wide
        layout.setGeometry(QRect(0,0,350,narrow))
        assert all(layout.itemAt(i).geometry().right()<350 for i in range(layout.count()))
    finally:widget.close()

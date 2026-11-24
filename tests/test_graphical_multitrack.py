"""Native gestures driving real validated project transactions; no fake media playback."""
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from clipos.video.multitrack import MultitrackProject,Media,Lane,Item
from clipos.ui.widgets.multitrack_timeline import MultitrackTimeline


@pytest.fixture
def widget(tmp_path):
    app=QApplication.instance() or QApplication([])
    project=MultitrackProject(width=160,height=90,fps=30,
        media=[Media('m',str(tmp_path/'authorized.mp4'),20,True,True)],
        lanes=[Lane('v','Video','video',[Item('a','m',1,2,4),Item('b','m',8,0,2)])])
    timeline=MultitrackTimeline();timeline.set_project(project)
    timeline.resize(1000,160);timeline.show();app.processEvents()
    yield timeline,project,app
    timeline.close()


def test_move_trim_snap_limits_and_locked(widget):
    timeline,project,_=widget
    assert timeline.gesture_values('v','a','move',-5)=={'at':0}
    # End of clip B is at 10 seconds.
    assert timeline.gesture_values('v','a','move',9.04)=={'at':10}
    assert timeline.gesture_values('v','a','move',9.04,True)['at']==pytest.approx(10.04)
    values=timeline.gesture_values('v','a','left',-5,True)
    assert values=={'at':0,'source_in':1,'length':5}
    values=timeline.gesture_values('v','a','right',100,True)
    assert values['length']==18
    project.lane_state('v',locked=True)
    with pytest.raises(ValueError,match='locked'):timeline.gesture_values('v','a','move',2)


def test_actual_drag_commits_once_and_can_undo_save_reopen(widget,tmp_path):
    timeline,project,app=widget
    commits=[]
    def commit(lane,item,values):
        project.change_item(lane,item,**values);commits.append(values)
    timeline.editRequested.connect(commit)
    rect=timeline.item_rect(0,project.lanes[0].items[0])
    start=rect.center().toPoint();end=start+QPoint(60,0)
    QTest.mousePress(timeline,Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(timeline,end)
    QTest.mouseRelease(timeline,Qt.MouseButton.LeftButton,pos=end)
    app.processEvents()
    assert len(commits)==1
    assert project.lanes[0].items[0].at==2
    path=tmp_path/'project.json';project.save(path)
    assert MultitrackProject.load(path).lanes[0].items[0].at==2
    project.undo();assert project.lanes[0].items[0].at==1


def test_ruler_seek_and_locked_drag(widget):
    timeline,project,app=widget
    seeks=[];edits=[]
    timeline.seekRequested.connect(seeks.append);timeline.editRequested.connect(lambda *args:edits.append(args))
    QTest.mouseClick(timeline,Qt.MouseButton.LeftButton,pos=QPoint(260,10))
    assert seeks==[2.]
    project.lane_state('v',locked=True)
    start=timeline.item_rect(0,project.lanes[0].items[0]).center().toPoint()
    QTest.mousePress(timeline,Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(timeline,start+QPoint(90,0))
    QTest.mouseRelease(timeline,Qt.MouseButton.LeftButton,pos=start+QPoint(90,0))
    app.processEvents();assert edits==[]


@pytest.mark.parametrize('side',['left','right'])
def test_actual_edge_trim_has_no_live_partial_edits(widget,side):
    timeline,project,app=widget
    rect=timeline.item_rect(0,project.lanes[0].items[0])
    start=QPoint(round(rect.left()+2 if side=='left' else rect.right()-2),round(rect.center().y()))
    end=start+QPoint(60 if side=='left' else -60,0)
    edits=[]
    timeline.editRequested.connect(lambda lane,item,values:(project.change_item(lane,item,**values),edits.append(values)))
    QTest.mousePress(timeline,Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(timeline,end)
    assert project.lanes[0].items[0].length==4  # ghost only during movement
    QTest.mouseRelease(timeline,Qt.MouseButton.LeftButton,pos=end)
    app.processEvents()
    assert len(edits)==1 and project.lanes[0].items[0].length==3
    assert project.lanes[0].items[0].source_in==(3 if side=='left' else 2)

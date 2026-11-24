"""Regressions for user-reported crop, preset reset and blocked delivery issues."""
from pathlib import Path
from unittest.mock import patch
import hashlib
import time
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage,QColor,QPixmap
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from clipos.db.database import Database
from clipos.core.ffmpeg import ffmpeg_available,run_ffmpeg,probe,extract_thumbnail


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app,tmp_path):
    from clipos.ui.main_window import MainWindow
    db=Database(tmp_path/'settings.db')
    db.set_settings({'auto_caption':False,'restore_on_launch':False,'use_gpu':'cpu','processing_threads':1})
    win=MainWindow(db)
    yield win
    with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):win.close()
    app.processEvents();db.close()


@pytest.fixture
def video(tmp_path):
    if not ffmpeg_available():pytest.skip('FFmpeg unavailable')
    source=tmp_path/'source.mp4'
    run_ffmpeg(['-f','lavfi','-i','color=c=cyan:size=320x180:rate=10:duration=2,drawbox=x=0:y=0:w=80:h=60:color=red:t=fill','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(source)])
    return source


def wait(app,predicate,page,timeout=90):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.processEvents();QTest.qWait(20)
        if predicate():return
    raise AssertionError(page.status.text()+'\n'+page.errors.toPlainText())


def load(window,video):
    pid=window.db.create_project(name='Dual region test',source_path=str(video),duration=2,width=320,height=180,has_audio=0)
    page=window.pages['workflow'];window.open_project(pid);page.go(1)
    image=QImage(320,180,QImage.Format.Format_RGB32);image.fill(QColor('cyan'))
    for x in range(80):
        for y in range(60):image.setPixelColor(x,y,QColor('red'))
    page.crop.set_frame(image)
    return page,pid


def drag(canvas,rect):
    bounds=canvas.display_rect();x,y,w,h=rect
    a=QPoint(round(bounds.x()+x*bounds.width()),round(bounds.y()+y*bounds.height()))
    b=QPoint(round(bounds.x()+(x+w)*bounds.width()),round(bounds.y()+(y+h)*bounds.height()))
    QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=a)
    QTest.mouseMove(canvas,b)
    QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=b)


def test_dragging_player_then_gameplay_preserves_both_live_overlays(window,video,app):
    page,pid=load(window,video)
    canvas=page.crop;canvas.resize(640,360)
    drag(canvas,(.01,.01,.23,.31))
    player=page.facecam
    page.crop_target.setCurrentIndex(1)
    drag(canvas,(.26,.01,.73,.98))
    assert page.facecam==player and page.gameplay[0]>.25
    assert canvas.regions['player']==player and canvas.regions['gameplay']==page.gameplay
    assert page.composition.facecam==player
    assert page.composition.gameplay==page.gameplay
    assert 'PLAYER (pink)' in page.crop_label.text() and 'GAMEPLAY (cyan)' in page.crop_label.text()
    page.crop_target.setCurrentIndex(0)
    assert canvas.rect==player
    # Loading a new live video frame does not clear either selection.
    page.crop.set_frame(QImage(640,360,QImage.Format.Format_RGB32))
    assert canvas.regions['player']==player
    page.load_project(pid)
    assert tuple(page.facecam)==player


def test_layout_and_caption_preferences_survive_refresh_and_navigation(window,video,app):
    page,pid=load(window,video)
    page.presets.setCurrentRow(0)  # Clean recipe would previously ignore layout silently.
    page.studio_layout.setCurrentIndex(page.studio_layout.findData('pip_br'))
    page.camera_size.setValue(42)
    page.caption.setCurrentIndex(page.caption.findData('karaoke'))
    page.cap_size.setValue(37);page.caption_on.setChecked(False)
    page.count.setValue(3);page.duration.setCurrentText('15-30')
    window.navigate('projects');window.navigate('workflow');page.refresh()
    settings=page._settings()
    assert settings.editing_preset=='gaming' and settings.studio_layout=='pip_br'
    assert settings.camera_size==.42 and settings.caption_style=='karaoke'
    assert settings.caption_size==37 and not settings.show_captions
    assert page.count.value()==3 and page.duration.currentText()=='15-30'


def test_camera_source_preset_updates_both_regions_and_real_preview(window,video,app,tmp_path):
    from clipos.core.config import AppPaths
    paths=AppPaths(tmp_path/'app');paths.ensure()
    page,pid=load(window,video)
    page.camera_preset.setCurrentIndex(page.camera_preset.findData('tl'))
    assert page.facecam==(0.,0.,.24,.32) and page.gameplay==(.24,0.,.76,1.)
    assert page._settings().editing_preset=='gaming' and not page._settings().auto_facecam
    # Source preset, layout and recipe preview all consume the same real regions.
    with patch('clipos.ui.pages.workflow.PATHS',paths):
        page._recipe_preview()
        wait(app,lambda:not page._busy(),page)
    out=paths.projects/str(pid)/'recipe-preview.mp4'
    assert out.is_file() and probe(out).video.height==640
    image=tmp_path/'frame.jpg';assert extract_thumbnail(out,image,.5)
    from PIL import Image
    picture=Image.open(image).convert('RGB');w,h=picture.size
    top=picture.getpixel((w//2,h//4));bottom=picture.getpixel((w//2,5*h//6))
    assert top[1]>150 and top[2]>150 and top[0]<80
    assert bottom[0]>150 and bottom[1]<80 and bottom[2]<80


def test_export_existing_render_is_not_blocked_by_changed_recipe_or_invalid_crop(window,video,app,tmp_path):
    page,pid=load(window,video)
    cid=window.db.create_clip(project_id=pid,title='Ready clip',start_time=0,end_time=2,duration=2,output_path=str(video),status='rendered')
    window.db.set_setting(f'edited_signature:{pid}','old-version-signature')
    page._reload_review();page.caption_on.setChecked(True)
    page.framing.setCurrentIndex(page.framing.findData('manual'));page.facecam=None
    page.destination.setText(str(tmp_path/'delivery'));page.go(3);page._export()
    wait(app,lambda:not page._busy(),page)
    assert page._last_folder, page.status.text()
    exports=list(Path(page._last_folder).glob('*.mp4'));assert len(exports)==1
    assert probe(exports[0]).duration>1.8
    assert hashlib.sha256(exports[0].read_bytes()).digest()==hashlib.sha256(video.read_bytes()).digest()
    assert window.db.get_clip(cid)['status']=='exported'


def test_source_video_sink_updates_canvas_from_real_playback(window,video,app):
    page,pid=load(window,video)
    if page.player is None or page.source_sink is None:
        import sys
        if sys.platform in ('win32','darwin'):pytest.fail('Native build must provide Qt multimedia playback')
        pytest.skip('Minimal Linux container lacks libpulse; native playback is a mandatory CI test')
    frames=[];page.source_sink.videoFrameChanged.connect(lambda f:frames.append(f.isValid()))
    page.go(1);page.player.play()
    wait(app,lambda:any(frames) and page.source_clock.text()!='0:00 / 0:00',page,30)
    assert not page.crop.image.isNull()
    assert page.source_clock.text()!='0:00 / 0:00'
    page.player.stop()


def test_drag_updates_composition_before_mouse_release_and_small_click_rolls_back(window,video,app):
    page,pid=load(window,video);canvas=page.crop;canvas.resize(640,360)
    bounds=canvas.display_rect()
    a=QPoint(round(bounds.x()+10),round(bounds.y()+10));b=a+QPoint(100,75)
    QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=a);QTest.mouseMove(canvas,b)
    assert page.composition.facecam is not None and page.facecam is None
    QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=b)
    previous=page.facecam
    QTest.mouseClick(canvas,Qt.MouseButton.LeftButton,pos=a)
    assert canvas.regions['player']==previous


def test_delivery_rejects_a_clip_from_a_different_project(window,video,tmp_path):
    from clipos.video.delivery import deliver_clips
    page,pid=load(window,video)
    other=window.db.create_project(name='Other recording',source_path=str(video))
    cid=window.db.create_clip(project_id=other,title='Other',output_path=str(video),status='rendered')
    result=deliver_clips(window.db,pid,[cid],tmp_path/'exports')
    assert result['results'][0]['error']=='Clip belongs to a different project'
    assert not list(Path(result['output_dir']).glob('*.mp4'))

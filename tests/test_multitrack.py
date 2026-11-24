"""Actual multi-source composition/mix tests, not professional live A/V acceptance."""
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import numpy as np
import pytest

from clipos.core.ffmpeg import require_ffmpeg, probe, FFmpegCancelled
from clipos.video.multitrack import MultitrackProject
from clipos.video.multitrack_render import export_project
from clipos.video.multitrack_preview import FrameCompositor


@pytest.fixture
def media(tmp_path):
    result=[]
    for name,color,frequency in [('red','red',440),('blue','blue',1000)]:
        output=tmp_path/(name+'.mp4')
        subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i',f'color={color}:s=160x90:r=10:d=2',
            '-f','lavfi','-i',f'sine=frequency={frequency}:sample_rate=48000:duration=2',
            '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(output)],
            check=True,capture_output=True,timeout=20)
        result.append(output)
    return result


def layered(media):
    project=MultitrackProject(width=160,height=90,fps=10)
    for path in media:project.import_media(path)
    # Each import created truly independent video and audio tracks.
    blue=project.lanes[2];item=blue.items[0]
    project.change_item(blue.id,item.id,at=.5,length=1,x=.5,w=.5)
    return project


def test_multisource_layers_and_independent_audio_really_export(media,tmp_path):
    project=layered(media)
    assert len(project.lanes)==4 and {lane.kind for lane in project.lanes}=={'video','audio'}
    output=tmp_path/'mixed.mp4'
    result=export_project(project,output,tmp_path/'work',encoder='cpu')
    assert result.size_bytes>0
    info=probe(output)
    assert info.duration==pytest.approx(2,abs=.2) and info.has_audio
    decoded=subprocess.run([require_ffmpeg(),'-v','error','-ss','0.8','-i',str(output),
        '-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True,timeout=20)
    frame=np.frombuffer(decoded.stdout,np.uint8).reshape(90,160,3)
    assert frame[45,20,0]>200 and frame[45,20,2]<30
    assert frame[45,130,2]>200 and frame[45,130,0]<30
    pcm=subprocess.run([require_ffmpeg(),'-v','error','-i',str(output),'-vn','-ac','1','-ar','48000',
        '-f','f32le','-'],capture_output=True,check=True,timeout=20)
    samples=np.frombuffer(pcm.stdout,dtype='<f4')[48000:72000]
    t=np.arange(len(samples))/48000
    for frequency in (440,1000):
        assert 2*abs(np.mean(samples*np.exp(-2j*np.pi*frequency*t)))>.02


def test_decoded_preview_uses_same_temporal_layer_order(media):
    project=layered(media)
    compositor=FrameCompositor()
    try:
        before=compositor.frame(project,.2)
        during=compositor.frame(project,.8)
        after=compositor.frame(project,1.8)
        assert before[45,130,2]>200  # BGR red
        assert during[45,20,2]>200 and during[45,130,0]>200
        assert after[45,130,2]>200
        project.lane_state(project.lanes[2].id,enabled=False)
        assert compositor.frame(project,.8)[45,130,2]>200
    finally:compositor.close()
    assert not compositor.decoders


def test_split_trim_move_lock_ripple_and_transactional_undo(media):
    project=layered(media)
    lane=project.lanes[0];item=lane.items[0]
    project.change_item(lane.id,item.id,speed=2)
    project.split(lane.id,item.id,.5)
    assert len(project.lanes[0].items)==2
    left,right=project.lanes[0].items
    assert left.length==1 and right.source_in==1 and right.at==.5
    snapshot=project.to_dict()
    with pytest.raises(ValueError):project.change_item(lane.id,left.id,length=10)
    assert project.to_dict()==snapshot
    project.lane_state(lane.id,locked=True)
    with pytest.raises(ValueError,match='locked'):project.remove(lane.id,left.id)
    project.lane_state(lane.id,locked=False)
    project.remove(lane.id,left.id,ripple=True)
    assert project.lanes[0].items[0].at==0
    assert project.undo() and len(project.lanes[0].items)==2
    assert project.redo() and len(project.lanes[0].items)==1
    project.move_lane(project.lanes[2].id,-1)
    assert project.lanes[1].kind=='video'


def test_atomic_reopen_recovery_and_reject_bad_data(media,tmp_path):
    project=layered(media)
    path=tmp_path/'project.clipos-mt.json'
    project.save(path)
    project.lane_state(project.lanes[0].id,enabled=False)
    project.save(path)
    reopened=MultitrackProject.load(path)
    assert reopened.to_dict()==project.to_dict()
    path.write_text('{truncated')
    recovered=MultitrackProject.load(path)
    assert recovered.recovered_from and recovered.lanes[0].enabled
    with pytest.raises(ValueError,match='overwrite media'):project.save(media[0])
    data=project.to_dict();data['lanes'][0]['items'][0]['speed']=float('nan')
    with pytest.raises(ValueError):MultitrackProject.from_dict(data)


def test_missing_media_and_cancel_never_destroy_existing_output(media,tmp_path):
    project=layered(media)
    output=tmp_path/'old.mp4';output.write_bytes(b'previous successful export')
    with pytest.raises(FFmpegCancelled):
        export_project(project,output,tmp_path/'work',encoder='cpu',cancel_cb=lambda:True)
    assert output.read_bytes()==b'previous successful export'
    assert not list(tmp_path.glob('.multitrack-*.mp4'))
    media[0].unlink()
    with pytest.raises(FileNotFoundError):export_project(project,output,tmp_path/'work',encoder='cpu')


def test_native_widget_actions_edit_save_reopen_and_decode_real_frames(media,tmp_path,monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication,QFileDialog
    from PySide6.QtTest import QSignalSpy
    from clipos.db.database import Database
    from clipos.ui.pages import multitrack as ui
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui,'PATHS',SimpleNamespace(projects=tmp_path/'projects',cache=tmp_path/'cache'))
    window=SimpleNamespace(db=Database(tmp_path/'ui.db'))
    page=ui.MultitrackPage(window)
    page.project=layered(media)
    spy=QSignalSpy(page.frames.ready)
    try:
        page._changed()
        from PySide6.QtCore import QEventLoop,QTimer
        loop=QEventLoop()
        page.frames.ready.connect(loop.quit)
        QTimer.singleShot(3000,loop.quit)
        loop.exec()
        assert spy.count()>0, page.status.text()
        assert page.table.rowCount()==4
        page.table.item(0,3).setText('0.25')
        assert page.project.lanes[0].items[0].at==.25
        path=tmp_path/'saved.clipos-mt.json'
        monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**k:(str(path),''))
        page._save()
        assert path.exists()
        page.project.change_item(page.project.lanes[0].id,page.project.lanes[0].items[0].id,at=.5)
        monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a,**k:(str(path),''))
        page._open()
        assert page.project.lanes[0].items[0].at==.25
        assert 'Opened' in page.status.text()
        page._undo()  # Reopened projects deliberately have no persisted history yet.
    finally:
        page.shutdown();page.deleteLater();app.processEvents()


def test_opacity_and_track_mute_change_export_and_preview(media,tmp_path):
    project=layered(media)
    lane=project.lanes[2]
    project.change_item(lane.id,lane.items[0].id,opacity=.5)
    project.lane_state(project.lanes[3].id,enabled=False)
    output=tmp_path/'opacity.mp4'
    export_project(project,output,tmp_path/'work',encoder='cpu')
    decoded=subprocess.run([require_ffmpeg(),'-v','error','-ss','0.8','-i',str(output),
        '-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True,timeout=20)
    pixel=np.frombuffer(decoded.stdout,np.uint8).reshape(90,160,3)[45,130]
    assert 90<pixel[0]<160 and 90<pixel[2]<160
    compositor=FrameCompositor()
    try:
        sample=compositor.frame(project,.8)[45,130]
        assert 90<sample[0]<160 and 90<sample[2]<160
    finally:compositor.close()
    pcm=subprocess.run([require_ffmpeg(),'-v','error','-i',str(output),'-vn','-ac','1','-ar','48000',
        '-f','f32le','-'],capture_output=True,check=True,timeout=20)
    samples=np.frombuffer(pcm.stdout,dtype='<f4')[48000:72000];t=np.arange(len(samples))/48000
    assert 2*abs(np.mean(samples*np.exp(-2j*np.pi*440*t)))>.03
    assert 2*abs(np.mean(samples*np.exp(-2j*np.pi*1000*t)))<.005


def test_relink_missing_media_and_canvas_undo(media,tmp_path):
    project=layered(media)
    source=project.media[0]
    replacement=tmp_path/'relinked.mp4'
    media[0].rename(replacement)
    project.relink(source.id,replacement)
    assert project.media[0].path==str(replacement.resolve())
    compositor=FrameCompositor()
    try:assert compositor.frame(project,.2).max()>200
    finally:compositor.close()
    project.edit(lambda draft:setattr(draft,'width',320))
    assert project.width==320
    assert project.undo() and project.width==160
    assert project.redo() and project.width==320


@pytest.mark.parametrize('field,value',[
    ('at',-1),('speed',0),('gain',float('nan')),('opacity',1.1),('w',2),('source_in',99),
])
def test_invalid_changes_do_not_mutate_project(media,field,value):
    project=layered(media)
    before=project.to_dict()
    with pytest.raises(ValueError):project.change_item(project.lanes[0].id,project.lanes[0].items[0].id,**{field:value})
    assert project.to_dict()==before


def test_live_audio_mix_seek_produces_correct_pcm_not_rendered_video(media):
    from clipos.video.multitrack_render import audio_preview_command
    project=layered(media)
    lane=project.lanes[3]
    project.change_item(lane.id,lane.items[0].id,at=1,length=1)
    command=audio_preview_command(project,.5)
    assert '-c:v' not in command and 's16le' in command
    proc=subprocess.run(command,check=True,capture_output=True,timeout=20)
    samples=np.frombuffer(proc.stdout,dtype='<i2').reshape(-1,2).mean(axis=1)/32768
    assert len(samples)/48000==pytest.approx(1.5,abs=.03)
    def amplitude(frequency,a,b):
        segment=samples[round(a*48000):round(b*48000)];t=np.arange(len(segment))/48000
        return 2*abs(np.mean(segment*np.exp(-2j*np.pi*frequency*t)))
    assert amplitude(440,.1,.3)>.03
    assert amplitude(1000,.1,.3)<.005
    assert amplitude(1000,.8,1.0)>.03


def test_real_native_audio_sink_when_device_exists(media):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QEventLoop,QTimer
    from clipos.ui.multitrack_audio import AudioClockPlayer,AudioDeviceUnavailable
    app=QApplication.instance() or QApplication([])
    try:player=AudioClockPlayer(layered(media),0)
    except AudioDeviceUnavailable as exc:
        import os
        if os.environ.get('CLIPOS_REQUIRE_NATIVE_AUDIO')=='1':pytest.fail(str(exc))
        pytest.skip(str(exc))
    errors=[];player.failed.connect(errors.append)
    try:
        loop=QEventLoop();QTimer.singleShot(600,loop.quit);loop.exec()
        assert not errors,errors
        assert player.position>0  # Actual processed device frames, no elapsed-time fake.
    finally:player.stop();player.deleteLater();app.processEvents()


def test_fades_export_preview_audio_seek_and_save(media,tmp_path):
    from clipos.video.multitrack_render import audio_preview_command
    project=MultitrackProject(width=160,height=90,fps=10)
    project.import_media(media[0])
    for lane in project.lanes:
        project.change_item(lane.id,lane.items[0].id,fade_in=1.,fade_out=.5)
    path=tmp_path/'fades.json';project.save(path)
    project=MultitrackProject.load(path)
    compositor=FrameCompositor()
    try:
        early=compositor.frame(project,.2)[45,80,2]
        late=compositor.frame(project,1.2)[45,80,2]
        assert 30<early<75 and late>220
    finally:compositor.close()
    output=tmp_path/'fades.mp4'
    export_project(project,output,tmp_path/'work',encoder='cpu')
    raw=subprocess.run([require_ffmpeg(),'-v','error','-ss','0.2','-i',str(output),'-frames:v','1',
        '-f','rawvideo','-pix_fmt','rgb24','-'],check=True,capture_output=True).stdout
    assert 25<np.frombuffer(raw,np.uint8).reshape(90,160,3)[45,80,0]<85
    def rms_at(start):
        raw=subprocess.run(audio_preview_command(project,start),check=True,capture_output=True).stdout
        pcm=np.frombuffer(raw,dtype='<i2').reshape(-1,2).mean(axis=1)/32768
        return np.sqrt(np.mean(pcm[2400:7200]**2))
    assert rms_at(.1)<rms_at(1.)*.4
    assert rms_at(1.8)<rms_at(1.)*.5


def test_fades_validate_undo_and_safe_split(media):
    project=layered(media);lane=project.lanes[0];item=lane.items[0]
    project.change_item(lane.id,item.id,fade_in=.4,fade_out=.4)
    before=project.to_dict()
    with pytest.raises(ValueError):project.change_item(lane.id,item.id,fade_in=2.)
    with pytest.raises(ValueError,match='inside fade'):project.split(lane.id,item.id,.2)
    assert project.to_dict()==before
    project.split(lane.id,item.id,1.)
    a,b=project.lanes[0].items
    assert (a.fade_in,a.fade_out,b.fade_in,b.fade_out)==(.4,0,0,.4)
    project.undo();assert project.to_dict()==before

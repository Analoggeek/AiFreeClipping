"""Actual local long-form media assembly and bounded export-derived preferences."""
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from clipos.video import longform
from clipos.video.timeline import Timeline
from clipos.core.ffmpeg import require_ffmpeg,FFmpegCancelled,probe
from clipos.ai.preferences import learn,adjustment,reset
from clipos.db.database import Database


def test_preferences_use_unique_successful_exports_are_bounded_and_resettable(tmp_path):
    db=Database(tmp_path/'prefs.db');project=db.create_project(name='test')
    ids=[]
    for index in range(20):
        clip=db.create_clip(project_id=project,settings=json.dumps({'selection_features':{'motion':1. if index<8 else 0.},'other':'preserved'}))
        ids.append(clip)
        if index<8:
            for _ in range(2):db.create_export(clip_id=clip,project_id=project,status='done',size_bytes=20,output_path='fixture.mp4')
    profile=learn(db)
    assert profile['status']=='active' and profile['samples']==8
    assert 0<profile['bias']['motion']<=.15
    assert 0<adjustment({'motion':1},profile)<=4
    assert adjustment({'motion':0},profile)<0
    reset(db);assert learn(db)['status']=='insufficient_exports'
    assert json.loads(db.get_clip(ids[0])['settings'])=={'other':'preserved'}


def test_failed_exports_and_invented_features_never_train(tmp_path):
    db=Database(tmp_path/'prefs.db');project=db.create_project(name='test')
    for _ in range(12):
        clip=db.create_clip(project_id=project,settings=json.dumps({'selection_features':{'motion':2.,'hook':True}}))
        db.create_export(project_id=project,clip_id=clip,status='failed',size_bytes=10,output_path='fixture.mp4')
    assert learn(db)['samples']==0


def fixture_video(tmp_path):
    path=tmp_path/'quiet.mp4'
    subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i','color=red:s=160x90:r=10:d=12',
        '-f','lavfi','-i',"aevalsrc=if(between(t\\,1\\,11)\\,0\\,0.2*sin(2*PI*440*t)):s=48000:d=12",
        '-c:v','libx264','-c:a','aac','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True,timeout=20)
    return path


def test_real_longform_downtime_plan_export_duration_and_source_protection(tmp_path):
    source=fixture_video(tmp_path);plan=tmp_path/'plan.json'
    data=longform.analyse(source,plan)
    assert 7.<data['removed_seconds']<10.
    assert len(data['timeline']['segments'])==2
    output=tmp_path/'edited.mp4'
    result=longform.export(plan,output,width=160,height=90)
    assert result['segments']==2 and result['size_bytes']>0
    info=probe(output);assert 2.<info.duration<5. and info.has_audio and info.has_video
    with pytest.raises(ValueError):longform.export(plan,source)
    source.write_bytes(source.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='stale'):longform.load(plan)


def test_longform_requires_both_channels_and_cancellation_preserves_old_output(tmp_path):
    assert longform.downtime_keeps(20,[(0,20)],[])==[(0,20)]
    assert longform.downtime_keeps(20,[],[(0,20)])==[(0,20)]
    source=fixture_video(tmp_path);plan=tmp_path/'plan.json';longform.analyse(source,plan)
    output=tmp_path/'existing.mp4';output.write_bytes(b'previous export')
    with pytest.raises(FFmpegCancelled):longform.export(plan,output,cancel_cb=lambda:True,width=160,height=90)
    assert output.read_bytes()==b'previous export'
    assert not list(tmp_path.glob('.longform-*'))


def test_native_longform_plan_edit_save_reopen(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication
    from clipos.ui.pages.longform import LongformPage
    app=QApplication.instance() or QApplication([])
    source=fixture_video(tmp_path);plan=tmp_path/'plan.json';data=longform.analyse(source,plan)
    page=LongformPage(SimpleNamespace(db=Database(tmp_path/'ui.db')))
    try:
        page._loaded(plan,data);page.table.item(0,0).setText('0.1')
        saved=tmp_path/'edited-plan.json';page._write(saved)
        _,timeline=longform.load(saved);assert timeline.segments[0].start==.1
        page.table.item(0,1).setText('99')
        before=saved.read_bytes()
        with pytest.raises(ValueError):page._write(saved)
        assert saved.read_bytes()==before
    finally:page.shutdown();page.deleteLater();app.processEvents()


def test_longform_concat_list_uses_forward_slash_path_for_windows(tmp_path):
    from pathlib import PureWindowsPath
    # FFmpeg's concat demuxer resolves relative entries against the slash-based
    # dirname of its input URL, not Windows native backslashes.
    assert PureWindowsPath(r'C:\Users\name\export\parts.txt').as_posix()=='C:/Users/name/export/parts.txt'
    source=fixture_video(tmp_path);plan=tmp_path/'plan.json';longform.analyse(source,plan)
    from clipos.core.ffmpeg import FFmpegRunner
    original=FFmpegRunner.run;concat=[]
    def run(self,args,*a,**kw):
        if 'concat' in args:
            listing=args[args.index('-i')+1];concat.append(listing)
            assert '\\' not in listing
        return original(self,args,*a,**kw)
    with patch.object(FFmpegRunner,'run',run):
        longform.export(plan,tmp_path/'fixed.mp4',width=160,height=90)
    assert len(concat)==1

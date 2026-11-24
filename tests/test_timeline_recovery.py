import json
from unittest.mock import patch

import pytest

from clipos.video.timeline import Timeline


def test_legacy_load_and_sparse_ids_do_not_collide(tmp_path):
    path=tmp_path/'edit.json'
    path.write_text(json.dumps({'source_duration':20,'segments':[
        {'id':'seg0001','start':0,'end':5}, {'id':'seg0003','start':10,'end':20}]}))
    timeline=Timeline.load(path)
    assert timeline.split_at(15)
    assert len({s.id for s in timeline.segments})==3
    assert timeline.segments[-1].id=='seg0004'


def test_previous_revision_recovers_and_survives_corrupt_primary_save(tmp_path):
    path=tmp_path/'edit.json'
    timeline=Timeline.from_clip(0,20)
    timeline.save(path)
    timeline.split_at(10)
    timeline.save(path)
    path.write_text('{truncated')
    restored=Timeline.load(path)
    assert restored.recovered_from==str(Timeline.backup_path(path))
    assert len(restored.segments)==1
    restored.set_speed(restored.segments[0].id,2)
    restored.save(path)
    assert Timeline.load(path).segments[0].speed==2
    assert len(Timeline._read(Timeline.backup_path(path)).segments)==1
    assert restored.recovered_from is None


def test_missing_primary_recovers_backup(tmp_path):
    path=tmp_path/'edit.json'
    timeline=Timeline.from_clip(0,10)
    timeline.save(path)
    timeline.save(path)
    path.unlink()
    assert Timeline.load(path).recovered_from


@pytest.mark.parametrize('failure_point',['write','replace'])
def test_interrupted_save_preserves_primary_and_cleans_temporary(tmp_path,failure_point):
    path=tmp_path/'edit.json'
    timeline=Timeline.from_clip(0,20)
    timeline.save(path)
    original=path.read_bytes()
    timeline.split_at(10)
    if failure_point=='write':
        target='clipos.video.timeline.os.fsync'
        effect=OSError('disk full')
    else:
        target='clipos.video.timeline.os.replace'
        import os
        real=os.replace
        def effect(src,dst):
            if dst==path:raise OSError('replace denied')
            return real(src,dst)
    with patch(target,side_effect=effect):
        with pytest.raises(OSError):timeline.save(path)
    assert path.read_bytes()==original
    assert not list(tmp_path.glob('*.tmp'))
    assert len(Timeline.load(path).segments)==1


@pytest.mark.parametrize('change',[
    {'speed':0},{'speed':float('nan')},{'start':-1},{'end':50},
    {'start':True},{'zoom':4},{'crop_x':2},{'muted':'false'},
])
def test_bad_segments_fail_without_overwriting_good_file(tmp_path,change):
    path=tmp_path/'edit.json'
    timeline=Timeline.from_clip(0,20)
    timeline.save(path)
    original=path.read_bytes()
    for key,value in change.items():setattr(timeline.segments[0],key,value)
    with pytest.raises(ValueError):timeline.save(path)
    assert path.read_bytes()==original


def test_duplicate_ids_unsupported_version_and_both_corrupt_fail(tmp_path):
    path=tmp_path/'edit.json'
    for data in [[],{'version':2,'segments':[]}, {'segments':[
        {'id':'a','start':0,'end':1},{'id':'a','start':2,'end':3}]}]:
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError):Timeline.load(path)
    Timeline.backup_path(path).write_text('bad')
    with pytest.raises(ValueError):Timeline.load(path)


def test_atomic_save_has_version_and_no_temporary_files(tmp_path):
    path=tmp_path/'folder'/'edit.json'
    timeline=Timeline.from_clip(0,20)
    timeline.save(path)
    assert json.loads(path.read_text())['version']==1
    assert list(path.parent.iterdir())==[path]

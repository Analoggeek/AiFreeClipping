"""Persisted undo/redo exercises the actual segment model used by the editor."""
import json

import pytest

from clipos.video.timeline import HISTORY_LIMIT, Timeline


def state(timeline):
    return [s.to_dict() for s in timeline.segments]


def test_save_reopen_undo_redo_exact_states(tmp_path):
    timeline=Timeline.from_clip(0,20)
    original=state(timeline)
    timeline.split_at(10)
    split=state(timeline)
    timeline.set_speed(timeline.segments[0].id,2)
    sped=state(timeline)
    timeline.set_crop(timeline.segments[1].id,.3,.7)
    cropped=state(timeline)
    timeline.undo()
    path=tmp_path/'edit.json'
    timeline.save(path)
    restored=Timeline.load(path)
    assert state(restored)==sped
    assert restored.can_undo() and restored.can_redo()
    assert restored.redo()=='Crop'
    assert state(restored)==cropped
    assert restored.undo()=='Crop'
    restored.undo()
    assert state(restored)==split
    restored.undo()
    assert state(restored)==original
    assert not restored.can_undo()
    restored.save(path)
    reopened=Timeline.load(path)
    assert reopened.can_redo() and not reopened.can_undo()
    for expected in (split,sped,cropped):
        assert reopened.redo()
        assert state(reopened)==expected


def test_reopen_new_edit_discards_redo_branch_without_id_reuse(tmp_path):
    path=tmp_path/'edit.json'
    timeline=Timeline.from_clip(0,20)
    timeline.split_at(10)
    old_id=timeline.segments[1].id
    timeline.undo()
    timeline.save(path)
    restored=Timeline.load(path)
    assert restored.split_at(5)
    assert restored.segments[1].id!=old_id
    assert not restored.can_redo()
    restored.save(path)
    assert not Timeline.load(path).can_redo()


def test_bounded_history_retains_most_recent_edits(tmp_path):
    path=tmp_path/'edit.json'
    timeline=Timeline.from_clip(0,20)
    for i in range(HISTORY_LIMIT+12):
        timeline.set_speed(timeline.segments[0].id,1+(i%3)*.25)
    assert len(timeline.history_labels())==HISTORY_LIMIT
    timeline.save(path)
    restored=Timeline.load(path)
    for _ in range(HISTORY_LIMIT):assert restored.undo()
    assert restored.undo() is None
    restored.save(path)
    assert len(Timeline.load(path)._redo)==HISTORY_LIMIT


def test_backup_restores_history_not_just_segments(tmp_path):
    path=tmp_path/'edit.json'
    timeline=Timeline.from_clip(0,20)
    timeline.split_at(10)
    timeline.save(path)
    timeline.set_speed(timeline.segments[0].id,2)
    timeline.save(path)
    path.write_text('{bad')
    restored=Timeline.load(path)
    assert restored.recovered_from
    assert restored.undo()=='Split at 10.00s'
    assert len(restored.segments)==1
    assert restored.redo()
    assert len(restored.segments)==2


@pytest.mark.parametrize('corruption',[
    'disconnected_undo','disconnected_redo','invalid_snapshot','too_many',
    'invalid_label','invalid_kind','not_object','not_stack',
])
def test_invalid_history_rejected_without_applying_it(tmp_path,corruption):
    path=tmp_path/'edit.json'
    timeline=Timeline.from_clip(0,20)
    timeline.split_at(10)
    data=timeline._save_data()
    op=data['history']['undo'][0]
    if corruption=='disconnected_undo':op['after'][0]['speed']=3
    elif corruption=='disconnected_redo':
        data['history']={'undo':[],'redo':[op]}
    elif corruption=='invalid_snapshot':op['before'][0]['end']=-1
    elif corruption=='too_many':data['history']['undo']=[op]*(HISTORY_LIMIT+1)
    elif corruption=='invalid_label':op['label']='x'*257
    elif corruption=='invalid_kind':op['kind']=12
    elif corruption=='not_object':data['history']=[]
    elif corruption=='not_stack':data['history']['undo']={}
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):Timeline.load(path)


def test_legacy_files_still_load_without_history(tmp_path):
    path=tmp_path/'edit.json'
    path.write_text(json.dumps({'source_duration':20,'segments':[
        {'id':'seg0001','start':0,'end':20}]}))
    restored=Timeline.load(path)
    assert not restored.can_undo() and not restored.can_redo()
    restored.split_at(10)
    restored.save(path)
    assert Timeline.load(path).can_undo()


def test_invalid_live_history_never_replaces_a_good_save(tmp_path):
    path=tmp_path/'edit.json'
    timeline=Timeline.from_clip(0,20)
    timeline.split_at(10)
    timeline.save(path)
    saved=path.read_bytes()
    timeline._undo[-1].after[0]['speed']=4
    with pytest.raises(ValueError):timeline.save(path)
    assert path.read_bytes()==saved

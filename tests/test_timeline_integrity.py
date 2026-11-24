import math

import pytest

from clipos.video.renderer import tempo_filter
from clipos.video.timeline import Timeline


@pytest.mark.parametrize('speed',[.05,.1,.25,.5,1,1.5,2,3,4,8,16])
def test_portable_tempo_chain_preserves_requested_rate(speed):
    factors=[float(stage.split('=')[1]) for stage in tempo_filter(speed).split(',')]
    assert all(.5<=factor<=2 for factor in factors)
    assert math.prod(factors)==pytest.approx(speed,rel=1e-7)


@pytest.mark.parametrize('speed',[0,-1,17,float('nan'),float('inf'),True,'4'])
def test_invalid_tempo_fails_explicitly(speed):
    with pytest.raises(ValueError):tempo_filter(speed)


@pytest.mark.parametrize('field,value',[
    ('speed',2),('zoom',1.5),('crop_x',.3),('crop_y',.7),('muted',True),
])
def test_merge_never_discards_different_transforms(field,value,tmp_path):
    timeline=Timeline.from_clip(0,20)
    timeline.split_at(10)
    # Use the real operation interface so history remains valid too.
    segment=timeline.segments[1]
    if field=='speed':timeline.set_speed(segment.id,value)
    elif field=='zoom':timeline.set_zoom(segment.id,value)
    elif field=='muted':timeline.set_muted(segment.id,value)
    elif field=='crop_x':timeline.set_crop(segment.id,value,.5)
    else:timeline.set_crop(segment.id,.5,value)
    before=timeline._save_data()
    assert not timeline.merge_with_next(0)
    assert timeline._save_data()==before
    path=tmp_path/'edit.json'
    timeline.save(path)
    assert getattr(Timeline.load(path).segments[1],field)==value


def test_merge_with_matching_edits_preserves_duration_and_undo():
    timeline=Timeline.from_clip(0,20)
    timeline.set_all_speed(2)
    timeline.split_at(10)
    duration=timeline.duration
    assert timeline.merge_with_next(0)
    assert timeline.duration==duration
    assert timeline.undo()=='Merge segments'
    assert len(timeline.segments)==2
    assert timeline.redo()=='Merge segments'


def test_merge_does_not_insert_hidden_source_gap():
    timeline=Timeline.from_clip(0,20)
    timeline.split_at(10)
    timeline.trim(timeline.segments[1].id,new_start=10.02)
    assert not timeline.merge_with_next(0)

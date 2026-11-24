import json
from types import SimpleNamespace

import pytest

from clipos.ai.tightening import propose,apply_to_timeline
from clipos.ai.transcription import Word
from clipos.video.timeline import Timeline


def test_measured_silence_breaths_and_word_protection():
    result=propose(10,20,[(12,14),(16,18)],[Word(word='important',start=16.5,end=17.)])
    assert result['keep']==[[10,12.18],[13.82,20]]
    assert result['removed_seconds']==pytest.approx(1.64)
    assert propose(0,10,[(0,10)])['keep']==[[0,10]]  # all quiet => abstain
    assert propose(0,10,[])['removed_seconds']==0


def test_cleanup_preserves_crop_speed_and_one_persisted_undo(tmp_path):
    timeline=Timeline.from_clip(10,20,30);segment=timeline.segments[0]
    timeline.set_speed(segment.id,2.)
    timeline.set_crop(segment.id,.3,.6)
    before=timeline._save_data()
    proposal=propose(10,20,[(12,14)])
    assert apply_to_timeline(timeline,proposal)
    assert len(timeline.segments)==2
    assert all(s.speed==2. and s.crop_x==.3 for s in timeline.segments)
    assert timeline.duration==pytest.approx((10-1.64)/2)
    path=tmp_path/'edits.json';timeline.save(path);timeline=Timeline.load(path)
    assert timeline.undo()=='Apply reviewed silence cleanup'
    assert timeline._save_data()['segments']==before['segments']


def test_invalid_proposals_and_outside_existing_edits_are_atomic():
    timeline=Timeline.from_clip(0,10,10);before=timeline._save_data()
    for proposal in ({'start':0,'end':10,'keep':[[3,2]]},
                     {'start':0,'end':10,'keep':[[0,float('nan')]]},
                     {'start':2,'end':10,'keep':[[2,10]]}):
        with pytest.raises(ValueError):apply_to_timeline(timeline,proposal)
        assert timeline._save_data()==before


def test_editor_review_applies_only_after_confirmation_and_checks_source(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QMessageBox
    from clipos.core import config
    from clipos.ui.pages.editor import EditorPage
    from clipos.video.waveform import source_signature
    app=QApplication.instance() or QApplication([])
    source=tmp_path/'source.mp4';source.write_bytes(b'local fixture, not decoded by this decision test')
    artifact=tmp_path/'projects'/'1'/'analysis'/'tightening.json';artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({'schema':'clipos.tightening.v1','source_signature':source_signature(source),
        'proposals':[propose(0,10,[(3,5)])]}))
    monkeypatch.setattr(config,'PATHS',SimpleNamespace(projects=tmp_path/'projects'))
    notifications=[];changes=[]
    page=SimpleNamespace(clip_id=1,project_id=1,source=source,timeline=Timeline.from_clip(0,10,10),
        window=SimpleNamespace(db=SimpleNamespace(get_clip=lambda _:dict(start_time=0,end_time=10)),
                               notify=lambda *args:notifications.append(args)),_after_edit=lambda:changes.append(True))
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Cancel)
    EditorPage._review_cleanup(page);assert page.timeline.duration==10 and not changes
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Apply)
    EditorPage._review_cleanup(page);assert page.timeline.duration<10 and changes==[True]
    source.write_bytes(b'changed source')
    EditorPage._review_cleanup(page);assert 'stale' in notifications[-1][0]


def test_actual_decoded_audio_silence_generates_cleanup_without_transcript_gaps(tmp_path):
    import wave
    import numpy as np
    from clipos.ai.audio_analysis import analyze_audio
    rate=16000
    tone=(np.sin(2*np.pi*440*np.arange(rate*2)/rate)*10000).astype('<i2')
    samples=np.concatenate([tone,np.zeros(rate*2,dtype='<i2'),tone])
    path=tmp_path/'measured.wav'
    with wave.open(str(path),'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(rate);stream.writeframes(samples.tobytes())
    audio=analyze_audio(path)
    result=propose(0,6,audio.silence_ranges)
    assert 1.<result['removed_seconds']<2.2
    timeline=Timeline.from_clip(0,6,6)
    assert apply_to_timeline(timeline,result) and 3.8<timeline.duration<5.

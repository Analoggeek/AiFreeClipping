"""Selection decision tests; local-model stubs do not prove trained-model quality."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from clipos.ai.automatic_selection import SelectionPolicy,select,local_order
from clipos.ai.clip_detector import ClipCandidate,detect_clips
from clipos.ai.audio_analysis import AudioAnalysis
from clipos.ai.visual_analysis import VisualAnalysis
from clipos.core.ffmpeg import FFmpegCancelled


def candidate(start,end,score=50,text=''):
    return ClipCandidate(start=start,end=end,virality_score=score,transcript_text=text)


def test_strict_diversity_never_refills_duplicates_to_hit_count():
    a=candidate(0,20,90);b=candidate(1,21,80);c=candidate(40,60,70)
    clips,report=select([a,b,c],60,3,SelectionPolicy())
    assert clips==[a,c] and report['selected_count']==2
    assert report['rejection_counts']['temporal_overlap']==1 and report['warnings']


def test_explicit_phrases_match_words_not_substrings_and_exclusions_win():
    a=candidate(0,10,40,'great skill now')
    b=candidate(20,30,40,'a clean kill now')
    c=candidate(40,50,80,'a clean kill during sponsor segment')
    clips,report=select([a,b,c],60,1,SelectionPolicy(include=('kill',),exclude=('sponsor',)))
    assert clips==[b] and report['selected'][0]['phrase_matches']==['kill']
    assert report['rejection_counts']['explicit_transcript_exclusion']==1


def test_transcript_duplicate_story_not_repeated_in_different_time_ranges():
    text='This is the complete same explanation of how the important event happened yesterday'
    clips,report=select([candidate(0,10,90,text),candidate(20,30,80,text)],40,2,SelectionPolicy())
    assert len(clips)==1 and report['rejection_counts']['transcript_repetition']==1


def test_late_peaks_survive_bounded_source_wide_shortlist():
    rows=[candidate(i*10,i*10+5,10) for i in range(300)]
    rows[-1].virality_score=95
    clips,report=select(rows,3000,1,SelectionPolicy())
    assert clips==[rows[-1]]
    assert report['rejection_counts']['bounded_shortlist_budget']>0


def test_local_reranking_uses_ids_not_position_or_fabricated_scores():
    rows=[candidate(0,10,90),candidate(20,30,80)]
    def rank(data,*args):return [row['id'] for row in reversed(data)]
    clips,report=select(rows,30,1,SelectionPolicy(local_rerank=True),ranker=rank)
    assert clips==[rows[1]] and report['rerank']['status']=='applied'
    assert rows[1].virality_score==80


@pytest.mark.parametrize('answer',[['new'],['c0000000','c0000000'],[0,1],None])
def test_invalid_ranking_retains_measured_order_and_reports_fallback(answer):
    rows=[candidate(0,10,90),candidate(20,30,80)]
    clips,report=select(rows,30,1,SelectionPolicy(direction='prefer complete story',local_rerank=True),ranker=lambda *args:answer)
    assert clips==[rows[0]] and report['rerank']['status']=='fallback'
    assert any('not interpreted' in warning for warning in report['warnings'])


def test_local_transport_refuses_extra_fields_and_uninstalled_model_errors():
    with patch('clipos.ai.automatic_selection.LocalOllama') as runtime:
        runtime.return_value.generate.return_value=json.dumps({'order':['a'],'start':0})
        with pytest.raises(ValueError):local_order([{'id':'a'}],'','http://127.0.0.1:11434','model')


def test_invalid_policy_and_cancellation():
    with pytest.raises(ValueError):select([],10,1,SelectionPolicy(include=(' ',)))
    with pytest.raises(FFmpegCancelled):select([],10,1,SelectionPolicy(),cancel_cb=lambda:True)


def test_detector_new_path_uses_selected_source_ranges_and_report():
    report={}
    clips=detect_clips(duration=100,audio=AudioAnalysis(),visual=VisualAnalysis(),transcript=None,
        min_duration=10,max_duration=20,target_count=4,selected_ranges=[(70,90)],
        selection_policy=SelectionPolicy(),selection_report=report)
    assert clips and all(70<=clip.start<clip.end<=90 for clip in clips)
    assert report['candidate_count']>0 and report['selected_count']==len(clips)


def test_pipeline_persists_selection_artifact_and_records_actual_count(tmp_path,monkeypatch):
    from clipos.db.database import Database
    from clipos.video import pipeline
    db=Database(tmp_path/'project.db')
    project_id=db.create_project(title='Fixture',file_path=str(tmp_path/'sample.mp4'),duration=100)
    monkeypatch.setattr(pipeline,'PATHS',SimpleNamespace(projects=tmp_path/'projects'))
    worker=pipeline.ClipOSPipeline(db,project_id)
    analysis=pipeline.AnalysisResult(duration=100)
    clips=worker.detect_clips(analysis,min_duration=10,max_duration=20,target_count=3,selected_ranges=[(70,90)])
    artifact=tmp_path/'projects'/str(project_id)/'analysis'/'selection.json'
    stored=json.loads(artifact.read_text())
    assert stored['selected_count']==len(clips) and analysis.selection==stored
    assert stored['selected_source_ranges']==[[70,90]]

import numpy as np
import pytest
from clipos.ai.visual_analysis import Face, VisualAnalysis, build_tracks, cv2_module
from clipos.ai.audio_analysis import AudioAnalysis
from clipos.ai.activity import flow_activity, loudness_jumps, activity_anchors
from clipos.ai.clip_detector import _candidate_windows, _score_signals, _engagement_score, SIGNAL_WEIGHTS
from clipos.ai.gaming_layout import infer_layout
from clipos.ai.panel_edges import refine_panel


def face(t,x=.1,y=.2):
    return Face(x=x,y=y,w=.08,h=.12,confidence=.95,timestamp=t)


def test_one_face_per_timestamp_and_cut_retirement():
    faces=[face(0),face(1,.11),face(1,.14),face(2,.12)]
    tracks=build_tracks(faces)
    assert len(tracks)==2
    assert all(len({f.timestamp for f in tr.faces})==len(tr.faces) for tr in tracks)
    cut=build_tracks([face(0),face(1)],scene_cuts=[.5])
    assert len(cut)==2
    assert build_tracks([face(0),face(10)],max_gap=2)[0].total_time==0


def test_loudness_and_ranking_are_measured():
    audio=AudioAnalysis(rms_db=[-40.]*500+[-10.]*50)
    jumps=loudness_jumps(audio)
    assert max(jumps[:10])==0 and jumps[10]>0.9
    v=VisualAnalysis(keyframe_times=[0,12],motion=[0,.8])
    assert activity_anchors(v,None)==[12]
    windows=_candidate_windows(60,10,20,None,v,None)
    assert any(s==8 for s,e in windows)
    scores,reasons,_=_score_signals(10,15,'',audio,v,None,None)
    quiet,_,_=_score_signals(0,4,'',audio,VisualAnalysis(),None,None)
    assert scores['motion']==.8 and scores['loudness_jump']>0
    assert _engagement_score(scores)>_engagement_score(quiet)
    assert sum(SIGNAL_WEIGHTS.values())==pytest.approx(1)


def test_flow_static_pan_cut_and_sparse_samples():
    cv2=cv2_module()
    if cv2 is None:pytest.skip('OpenCV unavailable')
    rng=np.random.default_rng(31)
    base=rng.integers(0,256,(90,160),dtype=np.uint8)
    base=cv2.GaussianBlur(base,(5,5),0)
    static,_=flow_activity(base,base,.5)
    pan=cv2.warpAffine(base,np.float32([[1,0,4],[0,1,0]]),(160,90))
    pan_score,_=flow_activity(base,pan,.5)
    moving=base.copy();moving[20:60,50:100]=np.roll(base[20:60,50:100],8,axis=1)
    subject,_=flow_activity(base,moving,.5)
    assert static<.001 and pan_score<.1 and subject>pan_score
    assert flow_activity(base,moving,5)==(0.,False)
    assert flow_activity(np.zeros_like(base),np.full_like(base,255),.5)==(0.,True)


def test_static_panel_requires_temporal_face_evidence():
    cv2=cv2_module()
    if cv2 is None:pytest.skip('OpenCV unavailable')
    frames=[]
    rng=np.random.default_rng(5)
    for _ in range(6):
        frame=rng.integers(0,100,(180,320,3),dtype=np.uint8)
        cv2.rectangle(frame,(15,15),(95,85),(255,255,255),2)
        frames.append(frame)
    faces=[face(t,.12,.15) for t in range(6)]
    seed=infer_layout(faces,list(range(6)))
    assert seed is not None
    refined=refine_panel(frames,faces,list(range(6)),seed)
    assert refined is not None and refined.method=='static-edge+temporal-face'
    x,y,w,h=refined.facecam
    assert x==pytest.approx(15/320,abs=.02)
    assert w==pytest.approx(80/320,abs=.03)
    assert refine_panel(frames,[],list(range(6)),seed) is None
    assert refine_panel(frames,faces[:2],list(range(6)),seed) is None

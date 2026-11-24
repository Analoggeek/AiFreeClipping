"""Raw-head math and actual ByteTrack runtime with synthetic detections.

These fixtures are NOT real YOLO model/quality or disconnected acceptance proof.
"""
import json
import subprocess

import numpy as np
import pytest

from clipos.ai.person_tracking import decode_people, LocalYOLOX, TrackingUnavailable, track_video, write_tracks
from clipos.core.ffmpeg import require_ffmpeg, FFmpegCancelled


def test_decode_person_only_and_duplicate_nms():
    output=np.zeros((1,3549,85),np.float32)
    # Adjacent stride-8 cells predict identical bodies.
    for index in (530,531):
        gx=index%52;gy=index//52
        output[0,index,:4]=[(120/8)-gx,(120/8)-gy,np.log(60/8),np.log(100/8)]
        output[0,index,4:6]=[.9,.8]
    output[0,800,:4]=[1,1,2,2]
    output[0,800,4]=.9
    output[0,800,6]=.99  # Non-person class must not be called a player.
    boxes,scores=decode_people(output,416,1,416,416)
    assert boxes.shape==(1,4)
    assert boxes[0]==pytest.approx([90,70,150,170])
    assert scores[0]==pytest.approx(.72)
    with pytest.raises(TrackingUnavailable):decode_people(output[:,:5],416,1,416,416)


def test_missing_or_url_model_never_downloads(tmp_path,monkeypatch):
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k:pytest.fail('Network requested'))
    for path in (tmp_path/'missing.onnx','https://example.com/model.onnx'):
        with pytest.raises(TrackingUnavailable,match='no automatic download'):LocalYOLOX(path)


@pytest.fixture
def source(tmp_path):
    output=tmp_path/'source.mp4'
    subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i',
        'color=black:s=320x180:r=10:d=1','-c:v','libx264','-pix_fmt','yuv420p',str(output)],
        check=True,capture_output=True,timeout=20)
    return output


class FixtureDetector:
    def __init__(self):self.calls=0
    def detect(self,frame):
        i=self.calls;self.calls+=1
        # Weak detection on one frame exercises real second-pass association.
        score=.15 if i==4 else .9
        return np.array([[20+i,20,70+i,150],[200-i,15,245-i,140]],np.float32),np.array([score,.9],np.float32)


def test_actual_bytetrack_is_continuous_one_to_one_and_streamed(source):
    pytest.importorskip('supervision')
    detector=FixtureDetector();observations=[]
    summary=track_video(source,None,detector=detector,emit=observations.append)
    assert summary['frames']==10 and detector.calls==10
    assert summary['track_count']==2
    assert summary['observations']>=16
    assert any(obs.frame==4 and obs.confidence<.25 for obs in observations)
    for frame in range(10):
        group=[obs for obs in observations if obs.frame==frame]
        assert len({obs.track_id for obs in group})==len(group)
        assert all(obs.timestamp==pytest.approx(frame/10) for obs in group)
        assert all(0<=obs.x<=1 and 0<obs.w<=1 for obs in group)


def test_cut_resets_ids_without_reuse_and_cancel_preserves_old_output(source,tmp_path):
    pytest.importorskip('supervision')
    observations=[]
    summary=track_video(source,None,detector=FixtureDetector(),scene_cuts=[.5],emit=observations.append)
    before={obs.track_id for obs in observations if obs.timestamp<.5}
    after={obs.track_id for obs in observations if obs.timestamp>=.5}
    assert before and after and before.isdisjoint(after)
    assert summary['track_count']==4
    output=tmp_path/'tracks.jsonl';output.write_text('previous')
    detector=FixtureDetector()
    with pytest.raises(FFmpegCancelled):
        write_tracks(source,None,output,detector=detector,cancel_cb=lambda:detector.calls>=3)
    assert output.read_text()=='previous'
    assert not list(tmp_path.glob('.tracking-*.tmp'))


def test_atomic_artifact_has_terminal_summary_and_marks_test_detector(source,tmp_path):
    pytest.importorskip('supervision')
    output=tmp_path/'tracks.jsonl'
    summary=write_tracks(source,None,output,detector=FixtureDetector())
    records=[json.loads(line) for line in output.read_text().splitlines()]
    assert records[-1]['type']=='summary'
    assert records[-1]['test_detector_injected'] is True
    assert len(records)==summary['observations']+1
    with pytest.raises(ValueError,match='overwrite source'):write_tracks(source,None,source)


def test_empty_detections_are_a_real_zero_result_not_an_invented_subject(source):
    pytest.importorskip('supervision')
    class NoPeople:
        def detect(self,frame):
            return np.empty((0,4),np.float32),np.empty(0,np.float32)
    summary=track_video(source,None,detector=NoPeople())
    assert summary['frames']==10 and summary['track_count']==summary['observations']==0


def test_limit_is_explicitly_reported_not_full_video_acceptance(source):
    pytest.importorskip('supervision')
    summary=track_video(source,None,detector=FixtureDetector(),max_frames=3)
    assert summary['frames']==3 and summary['frame_limit_reached']

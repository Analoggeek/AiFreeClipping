"""Actual caption pixels/decoded frames; mocked model responses test contracts, not AI quality."""
import base64
import json
import subprocess
from unittest.mock import patch

import numpy as np
import pytest

from clipos.ai.clip_intent import validate,clock_values,intersect_ranges
from clipos.ai.automatic_selection import select,SelectionPolicy
from clipos.ai.clip_detector import ClipCandidate
from clipos.captions.caption_engine import CaptionCue,apply_speaker_labels,retime_cues,speaker_color,write_ass,get_style
from clipos.core.ffmpeg import require_ffmpeg
from clipos.core.local_ai import LocalOllama,LocalAIError


def test_intent_grounded_phrases_explicit_clocks_and_hard_range_intersection():
    instruction='boss fight prefer karo, sponsor exclude; 1:20 se 2:00'
    data={'prefer':['boss fight'],'exclude':['sponsor'],'ranges':[[80,120]],'unapplied':[]}
    assert validate(data,instruction,200)==data
    assert clock_values('00:01:20 to 02:00')=={80.,120.}
    assert intersect_ranges([[100,150]],data['ranges'])==[[100,120]]
    with pytest.raises(ValueError):intersect_ranges([[150,180]],data['ranges'])
    for invalid in ({**data,'prefer':['invented kill']},{**data,'ranges':[[1,2]]}):
        with pytest.raises(ValueError):validate(invalid,instruction,200)


def test_speaker_colours_preserve_words_and_labels_through_cuts_speed_unknown_overlap():
    cue=CaptionCue(0,3,'one two three',[{'w':'one','s':0.,'e':.5},{'w':'two','s':1.,'e':1.5},{'w':'three','s':2.,'e':2.5}])
    turns=[{'start':0.,'end':.8,'speaker':'Speaker A'},{'start':1.,'end':2.7,'speaker':'Speaker B'},
           {'start':2.,'end':2.7,'speaker':'Speaker A'}]
    labelled=apply_speaker_labels([cue],turns)
    assert [c.speaker for c in labelled]==['Speaker A','Speaker B',None]
    output=retime_cues(labelled,[(1,3,2)])
    assert [c.speaker for c in output]==['Speaker B',None]
    assert output[0].start==0 and output[1].start==.5
    cue.text='manually corrected text'
    result=apply_speaker_labels([cue],turns)
    assert result[0].text==cue.text and result[0].speaker is None
    assert speaker_color('{injected tag}') is None


def test_real_libass_pixels_change_with_speaker_palette(tmp_path):
    cues=[CaptionCue(0,1,'SPEAKER',speaker='Speaker A'),CaptionCue(1,2,'SPEAKER',speaker='Speaker B')]
    write_ass(tmp_path/'captions.ass',cues,get_style('bold_viral'),360,640,size_override=40)
    raw=subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i','color=black:s=360x640:r=2:d=2',
        '-vf','ass=captions.ass','-f','rawvideo','-pix_fmt','rgb24','-'],cwd=tmp_path,check=True,capture_output=True).stdout
    frames=np.frombuffer(raw,np.uint8).reshape(4,640,360,3)
    assert np.count_nonzero(frames[1]!=frames[3])>100
    assert frames[1].max()>100 and frames[3].max()>100


def test_vision_transport_requires_local_capability_and_bounded_actual_image_header():
    runtime=LocalOllama()
    with patch.object(runtime,'require_local_model',return_value={'capabilities':[]}),patch.object(runtime,'request') as request:
        with pytest.raises(LocalAIError,match='vision'):runtime.generate('p','m',images=['abc'])
        request.assert_not_called()
    with patch.object(runtime,'require_local_model',return_value={'capabilities':['vision']}),patch.object(runtime,'request',return_value={'response':'ok'}) as request:
        image=base64.b64encode(b'\xff\xd8\xff test transport header only').decode()
        assert runtime.generate('p','m',images=[image])=='ok'
        assert request.call_args.args[1]['images']==[image]
        with pytest.raises(LocalAIError):runtime.generate('p','m',images=['not base64'])


def test_actual_source_frame_sampling_calls_local_vision_and_releases_decoder(tmp_path):
    from clipos.ai.game_vision import review
    source=tmp_path/'red.mp4'
    subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i','color=red:s=160x90:r=10:d=2',
        '-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True,capture_output=True)
    with patch('clipos.ai.game_vision.LocalOllama') as local:
        local.return_value.generate.return_value=json.dumps({'scene':'ordinary','description':'red test frame'})
        result=review(source,[{'id':'c1','start':0,'end':2}],'http://127.0.0.1:11434','installed-vision')
        frames=local.return_value.generate.call_args.kwargs['images']
        assert len(frames)==3 and all(base64.b64decode(f).startswith(b'\xff\xd8') for f in frames)
        assert result[0]['id']=='c1' and result[0]['scene']=='ordinary'


def test_visual_review_bounded_bonus_and_malformed_noop_without_inventing_scores():
    a=ClipCandidate(0,10,virality_score=50);b=ClipCandidate(20,30,virality_score=49)
    def review(rows):return [{'id':r['id'],'scene':'action' if r['start']==20 else 'loading'} for r in rows]
    clips,report=select([a,b],30,1,SelectionPolicy(),evidence_reviewer=review)
    assert clips==[b] and b.virality_score==49 and report['visual_review']['maximum_adjustment']==3
    clips,report=select([a,b],30,1,SelectionPolicy(),evidence_reviewer=lambda rows:[])
    assert clips==[a] and report['visual_review']['status']=='unavailable'


def test_shot_held_crop_has_instant_cut_and_retimes_through_keeps(tmp_path):
    from clipos.ai.visual_analysis import Face,FaceTrack,VisualAnalysis,SceneCuts
    from clipos.video.shot_reframe import shot_centers,crop_filter
    visual=VisualAnalysis(scenes=SceneCuts(times=[1.]))
    visual.tracks=[FaceTrack(1,[Face(.15,.3,.2,.4,timestamp=t) for t in (0,.3,.6)]),
                   FaceTrack(2,[Face(.65,.3,.2,.4,timestamp=t) for t in (1.,1.3,1.6)])]
    centers=shot_centers(visual,0,2)
    assert centers[0][2]==.25 and centers[1][2]==.75
    graph=crop_filter(visual,0,2,[(0,.5),(1.5,2)],160,90,80,90)
    # Feed static two-colour imagery: a crop that drifts/averages across the
    # boundary instead of switching cannot satisfy these temporal pixel checks.
    raw=subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i',
        'color=red:s=160x90:r=10:d=1,drawbox=x=80:y=0:w=80:h=90:color=blue:t=fill',
        '-vf',graph,'-f','rawvideo','-pix_fmt','rgb24','-'],check=True,capture_output=True).stdout
    frames=np.frombuffer(raw,np.uint8).reshape(10,90,80,3)
    assert frames[4,45,40,0]>200 and frames[4,45,40,2]<30
    assert frames[5,45,40,2]>200 and frames[5,45,40,0]<30
    # A shot with no local observations must not inherit the previous identity.
    visual.tracks=visual.tracks[:1]
    assert shot_centers(visual,0,2)[1][2:]==(.5,.5)


def test_caption_artifact_binding_rejects_stale_and_invalid_anonymous_labels(tmp_path):
    from clipos.ai.diarization import caption_turns
    path=tmp_path/'diarization.json'
    data={'schema':'clipos.diarization.v1','duration':2.,'turns':[{'start':0.,'end':1.,'speaker':'Speaker A'}]}
    path.write_text(json.dumps(data));summary={'artifact':str(path),'source_signature':'fresh'}
    assert caption_turns(summary,2.,'fresh')==data['turns']
    with pytest.raises(ValueError):caption_turns(summary,2.,'different')
    data['turns'][0]['speaker']='{ASS command}'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):caption_turns(summary,2.,'fresh')


def test_real_trained_ocr_reads_generated_video_text_without_network_or_stub(tmp_path):
    pytest.importorskip('rapidocr_onnxruntime')
    from clipos.ai.game_ocr import review
    import cv2
    image=np.zeros((240,960,3),np.uint8)
    cv2.putText(image,'VICTORY',(70,160),cv2.FONT_HERSHEY_SIMPLEX,3,(255,255,255),5)
    frame=tmp_path/'frame.png';assert cv2.imwrite(str(frame),image)
    source=tmp_path/'banner.mp4'
    subprocess.run([require_ffmpeg(),'-v','error','-loop','1','-i',str(frame),'-t','1','-r','10',
        '-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True,capture_output=True)
    with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('OCR must not fetch models')):
        result=review(source,[{'id':'real','start':0.,'end':1.}])
    observations=result[0]['ocr']
    assert any('VICTORY' in row['text'].upper() and row['confidence']>=.8 for row in observations)
    assert result[0]['scene']=='unknown'  # text is not a verified game outcome
    assert len(result[0]['model_hashes'])==3

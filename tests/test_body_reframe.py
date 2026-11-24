"""Body export integration uses known synthetic body boxes, not detector accuracy evidence."""
import json
import subprocess

import numpy as np
import pytest

from clipos.ai.visual_analysis import VisualAnalysis
from clipos.core.ffmpeg import require_ffmpeg, probe
from clipos.video.body_reframe import body_keys, retime_body_keys
from clipos.video.renderer import ClipRenderer, RenderSettings
from clipos.video.timeline import Timeline


@pytest.fixture
def scene(tmp_path):
    ffmpeg=require_ffmpeg()
    source=tmp_path/'moving.mp4'
    frames=np.zeros((20,180,320,3),np.uint8)
    rows=[]
    for index in range(21):
        center=30+index*13
        if index<20:frames[index,40:140,center-10:center+10]=255
        rows.append({'type':'person','timestamp':index/10,'track_id':7,
                     'x':(center-10)/320,'y':40/180,'w':20/320,'h':100/180,'confidence':.9})
    subprocess.run([ffmpeg,'-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','320x180',
        '-r','10','-i','-','-c:v','libx264','-pix_fmt','yuv420p',str(source)],
        input=frames.tobytes(),capture_output=True,check=True,timeout=20)
    artifact=tmp_path/'body.jsonl'
    summary={'type':'summary','schema_version':1,'source':str(source.resolve()),'test_detector_injected':True,
             'source_size':source.stat().st_size,'source_mtime_ns':source.stat().st_mtime_ns}
    artifact.write_text('\n'.join(json.dumps(row) for row in rows+[summary]))
    return source,artifact,rows,summary


def settings():
    return RenderSettings(width=180,height=320,fps=10,editing_preset='clean',show_captions=False,
        remove_silence=False,color_correct=False,normalize_audio=False,noise_reduction=False,
        sound_effects=False,auto_zoom=False,encoder_preference='cpu')


def test_keys_keep_one_id_and_validate_source(scene,tmp_path):
    source,artifact,rows,summary=scene
    keys,chosen=body_keys(artifact,source,0,2)
    assert chosen==7 and len(keys)<=122
    assert keys[0][0]<keys[-1][0]
    assert body_keys(artifact,source,0,2,track_id=99)==([],None)
    with pytest.raises(ValueError,match='mismatched'):body_keys(artifact,tmp_path/'different.mp4',0,2)
    artifact.write_text('\n'.join(json.dumps(row) for row in rows[:2]+[summary]))
    assert body_keys(artifact,source,0,2)==([],None)


@pytest.mark.parametrize('bad',['missing_summary','nan','oversize','duplicate_summary'])
def test_bad_artifact_not_promoted_to_tracking(scene,bad):
    source,artifact,rows,summary=scene
    if bad=='missing_summary':artifact.write_text(json.dumps(rows[0]))
    elif bad=='nan':
        rows[0]['x']=float('nan');artifact.write_text('\n'.join(json.dumps(row) for row in rows+[summary]))
    elif bad=='oversize':artifact.write_text('x'*65537)
    else:artifact.write_text(json.dumps(summary)+'\n'+json.dumps(summary))
    with pytest.raises(ValueError):body_keys(artifact,source,0,2)


def test_silence_cut_remapping_uses_kept_source_times():
    keys,duration=retime_body_keys([(.1,.5),(.9,.5)],10,[(0,2),(8,10)])
    assert duration==4 and keys[0][0]==pytest.approx(.1) and keys[-1][0]==pytest.approx(.9)
    assert keys[len(keys)//2][0]>=.73


@pytest.mark.parametrize('timeline_mode',[False,True])
def test_body_evidence_controls_actual_export_pixels(scene,tmp_path,timeline_mode):
    source,artifact,_,_=scene
    visual=VisualAnalysis(person_tracking={'artifact':str(artifact)})
    renderer=ClipRenderer(tmp_path/'work')
    output=tmp_path/'follow.mp4'
    if timeline_mode:
        timeline=Timeline.from_clip(0,2,source_duration=2)
        timeline.split_at(1)
        timeline.move_segment(0,1)
        timeline.set_speed(timeline.segments[0].id,2)
        result=renderer.render_timeline(source,output,timeline,settings(),visual=visual)
        expected=1.5
    else:
        result=renderer.render(source,output,0,2,settings(),visual=visual)
        expected=2
    assert any('person track 7' in step for step in result.steps)
    assert probe(output).duration==pytest.approx(expected,abs=.2)
    proc=subprocess.run([require_ffmpeg(),'-v','error','-i',str(output),'-vf','fps=5',
        '-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True,timeout=20)
    frames=np.frombuffer(proc.stdout,np.uint8).reshape(-1,320,180,3)
    # Known white body remains in both early and late reframed output.
    assert (frames[1].mean(axis=2)>160).sum()>500
    assert (frames[-2].mean(axis=2)>160).sum()>500


def test_explicit_segment_crop_overrides_body_evidence(scene,tmp_path):
    source,artifact,_,_=scene
    timeline=Timeline.from_clip(0,1,source_duration=2)
    timeline.set_crop(timeline.segments[0].id,.2,.5)
    result=ClipRenderer(tmp_path/'work').render_timeline(source,tmp_path/'manual.mp4',timeline,
        settings(),visual=VisualAnalysis(person_tracking={'artifact':str(artifact)}))
    assert not any('Body reframe' in step for step in result.steps)


def test_stale_or_frame_limited_artifact_rejected(scene):
    source,artifact,rows,summary=scene
    summary['source_size']+=1
    artifact.write_text('\n'.join(json.dumps(row) for row in rows+[summary]))
    with pytest.raises(ValueError,match='Stale'):body_keys(artifact,source,0,2)
    summary['source_size']=source.stat().st_size
    summary['frame_limit_reached']=True
    artifact.write_text('\n'.join(json.dumps(row) for row in rows+[summary]))
    with pytest.raises(ValueError,match='Incomplete'):body_keys(artifact,source,0,2)

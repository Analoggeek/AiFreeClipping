"""Safety/GUI contracts; injected inference here is not a trained-model acceptance claim."""
import json
from unittest.mock import patch
import pytest
from clipos.ai.gemma_runtime import GemmaRuntime
from clipos.core.local_ai import LocalAIError
from clipos.ai.editing_agent import validate_plan,apply_plan,step_history,InvalidEditPlan,propose_plan
from clipos.db.database import Database

@pytest.mark.parametrize('host',['https://example.org','http://192.168.1.1:11434','http://localhost:11434/redirect'])
def test_manager_has_same_loopback_boundary(host):
    with pytest.raises(LocalAIError):GemmaRuntime(host)

def test_download_never_starts_without_consent():
    runtime=GemmaRuntime()
    with patch.object(runtime.client.opener,'open') as request:
        with pytest.raises(LocalAIError):runtime.pull('gemma:7b')
        request.assert_not_called()

def test_download_rejects_arbitrary_remote_or_unverified_tags():
    with pytest.raises(LocalAIError):GemmaRuntime().pull('someone/unknown:cloud',consent=True)

def test_unload_requires_local_weights_first():
    runtime=GemmaRuntime()
    with patch.object(runtime.client,'require_local_model',side_effect=LocalAIError('missing')),patch.object(runtime.client,'request') as request:
        with pytest.raises(LocalAIError):runtime.unload('gemma:7b')
        request.assert_not_called()

def test_plan_repair_is_bounded_and_does_not_execute_bad_output():
    with patch('clipos.ai.editing_agent.LocalOllama.generate',side_effect=['bad','{"version":1,"settings":{"default_clip_count":10}}']) as generate:
        plan=propose_plan('make ten clips',100)
        assert plan.settings['default_clip_count']==10 and generate.call_count==2
    with patch('clipos.ai.editing_agent.LocalOllama.generate',return_value='{"shell":"rm -rf /"}') as generate:
        with pytest.raises(InvalidEditPlan):propose_plan('make ten clips',100)
        assert generate.call_count==2

def test_director_history_survives_reopen_and_protects_newer_manual_settings(tmp_path):
    path=tmp_path/'project.db';db=Database(path);pid=db.create_project(name='Recording',duration=100)
    db.set_setting('caption_size',32)
    plan=validate_plan({'version':1,'settings':{'caption_size':55},'ranges':[[2,30]]},100)
    apply_plan(db,pid,plan);db.close();db=Database(path)
    assert db.get_setting('caption_size')==55
    step_history(db,pid);assert db.get_setting('caption_size')==32
    step_history(db,pid,redo=True);assert db.get_setting('caption_size')==55
    db.set_setting('caption_size',60)
    with pytest.raises(InvalidEditPlan):step_history(db,pid)
    assert db.get_setting('caption_size')==60
    db.close()

def test_context_marks_missing_analysis_and_bounds_candidates(tmp_path):
    from clipos.ai.director import project_context
    db=Database(tmp_path/'context.db');pid=db.create_project(name='Actual',duration=100,width=1920,height=1080)
    for n in range(35):db.create_clip(project_id=pid,start_time=n,end_time=n+2,reason='measured')
    summary,text=project_context(db,pid)
    assert len(summary['candidate_clips'])==24 and not text
    assert 'missing' in summary['transcription'] and 'No verified' in summary['visual_analysis']
    assert 'source_path' not in summary['source'];db.close()

def test_retired_pages_and_dashboard_share_real_workflow(tmp_path):
    from PySide6.QtWidgets import QApplication
    from clipos.ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([]);db=Database(tmp_path/'ui.db');w=MainWindow(db)
    try:
        assert not {'longform','captions','templates'} & w._page_classes.keys()
        page=w.pages['workflow'];page._quick_style('podcast')
        assert db.get_setting('editing_preset')=='podcast'
        page._propose_agent_plan();assert 'Import or open' in page.status.text()
        w.navigate('models');assert w.pages['models'].gemma.model.currentText()=='gemma:7b'
    finally:w.close();app.processEvents();db.close()

@pytest.mark.parametrize('operation,fields',[('speed',{'value':1.5}),('zoom',{'value':1.25}),('crop',{'x':.3,'y':.7}),('trim',{'start':1,'end':4}),('mute',{'value':True})])
def test_typed_timeline_commands_are_real_undoable_and_persist(tmp_path,operation,fields):
    from clipos.video.timeline import Timeline
    from clipos.ai.timeline_director import fingerprint,apply_commands
    tl=Timeline.from_clip(0,5,source_duration=5);before=fingerprint(tl)
    raw={'commands':[{'operation':operation,'segment':tl.segments[0].id,**fields}]}
    apply_commands(tl,raw,before);after=fingerprint(tl);assert after!=before
    path=tmp_path/'edit.json';tl.save(path);tl=Timeline.load(path)
    tl.undo();assert fingerprint(tl)==before
    tl.redo();assert fingerprint(tl)==after

@pytest.mark.parametrize('bad',[{'operation':'shell','command':'anything'}, {'operation':'zoom','value':float('nan')}, {'operation':'zoom','value':4}, {'operation':'mute','value':1}, {'operation':'crop','x':-1,'y':.5}])
def test_invalid_timeline_plans_never_partially_apply(bad):
    from clipos.video.timeline import Timeline
    from clipos.ai.timeline_director import fingerprint,apply_commands
    tl=Timeline.from_clip(0,5,source_duration=5);before=fingerprint(tl)
    bad=dict(bad,segment=tl.segments[0].id)
    with pytest.raises(InvalidEditPlan):apply_commands(tl,{'commands':[{'operation':'zoom','segment':tl.segments[0].id,'value':1.2},bad]},before)
    assert fingerprint(tl)==before and not tl.can_undo()

def test_stale_or_destructive_director_plan_refused():
    from clipos.video.timeline import Timeline
    from clipos.ai.timeline_director import fingerprint,apply_commands
    tl=Timeline.from_clip(0,5,source_duration=5);digest=fingerprint(tl)
    raw={'commands':[{'operation':'delete','segment':tl.segments[0].id}]}
    with pytest.raises(InvalidEditPlan):apply_commands(tl,raw,digest)
    tl.set_zoom(tl.segments[0].id,1.2)
    with pytest.raises(InvalidEditPlan):apply_commands(tl,raw,digest)

def test_approved_timeline_commands_really_render_captioned_output(tmp_path):
    from clipos.core.ffmpeg import run_ffmpeg,probe,ffmpeg_available
    from clipos.video.timeline import Timeline
    from clipos.video.renderer import ClipRenderer,RenderSettings
    from clipos.ai.timeline_director import fingerprint,apply_commands
    from clipos.captions.caption_engine import CaptionCue
    if not ffmpeg_available():pytest.skip('Requires real FFmpeg')
    source=tmp_path/'recording.mp4'
    run_ffmpeg(['-f','lavfi','-i','testsrc2=size=320x180:rate=15:duration=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-threads','1','-c:a','aac',str(source)])
    tl=Timeline.from_clip(0,2,source_duration=2);sid=tl.segments[0].id
    apply_commands(tl,{'commands':[{'operation':'trim','segment':sid,'start':.2,'end':1.8},{'operation':'zoom','segment':sid,'value':1.2},{'operation':'speed','segment':sid,'value':2},{'operation':'split','segment':sid,'time':1}]},fingerprint(tl))
    output=tmp_path/'approved.mp4'
    ClipRenderer(tmp_path/'work').render_timeline(source,output,tl,RenderSettings(width=180,height=320,fps=15,threads=1,encoder_preference='cpu',show_captions=True,sound_effects=False),cues=[CaptionCue(.2,1.8,'Approved local edit',[])])
    info=probe(output)
    assert output.stat().st_size>1000 and info.has_audio
    assert info.duration==pytest.approx(.8,abs=.2)
    assert (info.video.width,info.video.height)==(180,320)

def test_dashboard_director_history_updates_actual_controls(tmp_path):
    from PySide6.QtWidgets import QApplication
    from clipos.ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([]);db=Database(tmp_path/'history-ui.db')
    db.set_settings({'restore_on_launch':False,'caption_size':32});w=MainWindow(db)
    try:
        pid=db.create_project(name='Recording',source_path='local.mp4',duration=100)
        w.open_project(pid);page=w.pages['workflow']
        page._pending_agent_plan=(pid,'local.mp4',validate_plan({'version':1,'settings':{'caption_size':60},'ranges':[[2,30]]},100))
        assert page._apply_agent_plan();assert page.cap_size.value()==60
        page._director_history(False);assert page.cap_size.value()==32,page.status.text()
        page._director_history(True);assert page.cap_size.value()==60,page.status.text()
    finally:w.close();app.processEvents();db.close()

@pytest.mark.parametrize('key',['gaming','podcast','talking_head','educational','reaction','cinematic'])
def test_quick_styles_reach_actual_captioned_export(tmp_path,key):
    from clipos.core.ffmpeg import run_ffmpeg,probe,ffmpeg_available
    from clipos.video.renderer import ClipRenderer,RenderSettings
    from clipos.video.presets import apply_preset
    from clipos.captions.caption_engine import CaptionCue
    if not ffmpeg_available():pytest.skip('Requires real FFmpeg')
    source=tmp_path/'style.mp4'
    run_ffmpeg(['-f','lavfi','-i','testsrc2=size=160x90:rate=15:duration=1','-c:v','libx264','-threads','1',str(source)])
    settings=apply_preset(RenderSettings(width=180,height=320,fps=15,threads=1,encoder_preference='cpu'),key)
    settings.auto_facecam=False;settings.facecam_rect=None
    output=tmp_path/'out.mp4'
    ClipRenderer(tmp_path/'work').render(source,output,0,1,settings,cues=[CaptionCue(0,1,'Actual style export',[])])
    assert probe(output).video.height==320 and output.stat().st_size>1000

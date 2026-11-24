"""Real v2.5 regressions: shared preferences, bounded audio, range/crop and batches."""
from pathlib import Path
import json
from unittest.mock import patch
import numpy as np
import pytest

from clipos.db.database import Database
from clipos.core.editing import render_settings
from clipos.video.pipeline import ClipOSPipeline,AnalysisResult,_safe_folder
from clipos.video.renderer import RenderSettings,ClipRenderer
from clipos.video.delivery import deliver_clips
from clipos.ai.audio_analysis import AudioAnalysis,_frames
from clipos.ai.visual_analysis import VisualAnalysis
from clipos.ai.clip_detector import detect_clips


@pytest.fixture
def db(tmp_path):
    db=Database(tmp_path/'projects.sqlite');yield db;db.close()


def test_preferences_honor_custom_output_and_real_boolean_types(db,tmp_path):
    db.set_settings({'output_dir':str(tmp_path/'my videos'),'auto_caption':False,'low_memory_mode':True,'processing_threads':1,'use_gpu':'cpu','min_silence_duration':.65})
    assert db.get_settings()['output_dir']==str(tmp_path/'my videos')
    rs=render_settings(db)
    assert not rs.show_captions and rs.low_memory and rs.threads==1
    assert rs.encoder_preference=='cpu' and rs.min_silence_duration==.65


def test_caption_choice_not_overwritten_by_recipe(db):
    db.set_settings({'editing_preset':'gaming','caption_style':'karaoke','caption_size':38})
    rs=render_settings(db)
    assert rs.caption_style=='karaoke' and rs.caption_size==38 and rs.caption_position=='split'


def test_manual_player_excludes_camera_from_default_gameplay(db):
    rs=render_settings(db,{'framing_mode':'manual','facecam_rect':(.0,.0,.2,.3)})
    assert not rs.auto_facecam and rs.gameplay_rect != (0.,0.,1.,1.)
    x,y,w,h=rs.gameplay_rect
    assert x>=.2 or y>=.3


def test_gameplay_only_respects_selected_crop(db):
    from clipos.video.presets import gaming_filter
    rs=render_settings(db,{'framing_mode':'gameplay','gameplay_rect':(.2,.0,.8,1.)})
    assert rs.facecam_rect is None
    graph=gaming_filter(270,480,640,360,None,rs.gameplay_rect)
    assert graph.startswith('crop=512:360:128:0')


def test_audio_windows_share_memory_instead_of_copying_hour_long_matrix():
    source=np.zeros(16000*30,dtype=np.float32);frames=_frames(source,16000)
    assert np.shares_memory(source,frames)
    assert not frames.flags.writeable


def test_user_selected_ranges_are_never_crossed():
    clips=detect_clips(200,AudioAnalysis(),VisualAnalysis(),None,min_duration=15,max_duration=30,target_count=8,selected_ranges=[(11,34),(108,125)])
    assert clips
    for c in clips:
        assert any(c.start>=a and c.end<=b for a,b in [(11,34),(108,125)])


def test_invalid_source_ranges_rejected():
    with pytest.raises(ValueError):detect_clips(100,AudioAnalysis(),VisualAnalysis(),None,selected_ranges=[(40,10)])


def test_batch_uses_one_date_video_folder_and_continues_errors(db,tmp_path):
    pid=db.create_project(name='My recording',source_path='recording.mp4')
    ids=[db.create_clip(project_id=pid,title=f'moment {i}',start_time=i,end_time=i+1) for i in range(3)]
    pipe=ClipOSPipeline(db,pid)
    def render(cid,target,*a,**kw):
        if cid==ids[1]:raise RuntimeError('real tool error fixture')
        Path(target).write_bytes(b'test fixture, not claimed as playable')
        return {'size_bytes':10,'duration':1,'width':270,'height':480}
    with patch.object(pipe,'render_clip',side_effect=render):results=pipe.export_clips(ids,tmp_path/'exports',RenderSettings(),AnalysisResult())
    assert len(results)==3 and results[1]['error']=='real tool error fixture'
    paths=[Path(r['output_path']) for r in results]
    assert len({p.parent for p in paths})==1
    folder=paths[0].parent
    assert folder.name=='My recording' and len(folder.parent.name)==10
    manifest=json.loads((folder/'export-results.json').read_text())
    assert manifest[1]['error'] and db.get_clip(ids[1])['status']=='error'


def test_delivery_collects_all_edited_clips_without_rerender(db,tmp_path):
    pid=db.create_project(name='CON',source_path='recording.mp4');ids=[]
    for i in range(2):
        path=tmp_path/f'edited{i}.mp4';path.write_bytes(b'file-copy fixture')
        ids.append(db.create_clip(project_id=pid,title=f'Clip {i}',output_path=str(path),status='rendered'))
    result=deliver_clips(db,pid,ids,tmp_path/'delivery')
    folder=Path(result['output_dir']);assert folder.name=='_CON'
    assert len(list(folder.glob('*.mp4')))==2 and not list(folder.glob('*.partial.mp4'))
    assert all(not r['error'] for r in result['results'])


def test_cancellation_does_not_mark_clip_success(db,tmp_path):
    from clipos.video.renderer import RenderResult
    from clipos.video.pipeline import PipelineCancelled
    source=tmp_path/'source.mp4';source.write_bytes(b'not decoded by mock')
    pid=db.create_project(name='cancelled',source_path=str(source));cid=db.create_clip(project_id=pid,start_time=0,end_time=1)
    with patch('clipos.video.pipeline.ClipRenderer.render',return_value=RenderResult(cancelled=True)):
        with pytest.raises(PipelineCancelled):ClipOSPipeline(db,pid).render_clip(cid,tmp_path/'out.mp4',RenderSettings(),AnalysisResult())
    assert db.get_clip(cid)['status']!='rendered'


def test_real_multicut_manual_split_captions_and_audio_use_single_decoder(tmp_path):
    from clipos.core.ffmpeg import ffmpeg_available,run_ffmpeg,probe,FFmpegRunner
    from clipos.captions.caption_engine import CaptionCue
    if not ffmpeg_available():pytest.skip('native FFmpeg unavailable')
    source=tmp_path/'input recording.mp4'
    run_ffmpeg(['-f','lavfi','-i','testsrc2=size=640x360:rate=15:duration=4','-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=4','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)])
    settings=RenderSettings(width=270,height=480,fps=15,editing_preset='gaming',auto_facecam=False,facecam_rect=(0.,0.,.25,.4),gameplay_rect=(.25,0.,.75,1.),encoder_preference='cpu',threads=1,caption_style='clean_professional',caption_size=30,sound_effects=False,caption_position='split')
    audio=AudioAnalysis(silence_ranges=[(.8,1.5),(2.3,3.)])
    commands=[];real_run=FFmpegRunner.run
    def execute(self,args,**kw):commands.append(args);return real_run(self,args,**kw)
    output=tmp_path/'finished.mp4'
    with patch.object(FFmpegRunner,'run',execute):
        result=ClipRenderer(tmp_path/'work folder').render(source,output,0,4,settings,audio=audio,cues=[CaptionCue(.1,.7,'Real edited caption',[])])
    assert commands and commands[0].count('-i')==1
    assert result.size_bytes>1000 and result.width==270 and result.height==480
    info=probe(output);assert info.has_audio and 2.2<info.duration<3.2
    assert any('Captions:' in step for step in result.steps)


def test_wizard_replaces_gaming_navigation_and_upload_controls(db,tmp_path):
    from PySide6.QtWidgets import QApplication,QPushButton
    from clipos.ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow(db)
    try:
        assert window.current_key=='workflow' and 'gaming' not in window.nav_buttons
        page=window.pages['workflow'];assert page.stack.count()==4
        assert not any('upload' in b.text().lower() or 'youtube account' in b.text().lower() for b in page.findChildren(QPushButton))
        source=tmp_path/'file.mp4';source.write_bytes(b'not decoded')
        pid=db.create_project(name='Shared project',source_path=str(source),duration=60,width=640,height=360)
        window.open_project(pid)
        assert page.project_id==window.active_project==pid
        assert page.presets.item(0).icon().isNull() is False
        page.facecam=(0.,0.,.2,.3);page._save_state();assert 'facecam' in db.get_setting(f'workflow:{pid}')
    finally:window.close();app.processEvents()


def test_actual_batch_exports_every_captioned_clip_together(db,tmp_path):
    from clipos.core.ffmpeg import ffmpeg_available,run_ffmpeg,probe
    from clipos.core.config import AppPaths
    from clipos.ai.transcription import Transcript,Segment,Word
    if not ffmpeg_available():pytest.skip('native FFmpeg unavailable')
    source=tmp_path/'recording.mp4'
    run_ffmpeg(['-f','lavfi','-i','testsrc2=size=320x180:rate=10:duration=4','-f','lavfi','-i','sine=sample_rate=16000:duration=4','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)])
    pid=db.create_project(name='Gaming recording',source_path=str(source),duration=4,has_audio=1)
    ids=[db.create_clip(project_id=pid,title=f'Moment {i}',start_time=i*.5,end_time=i*.5+1.5,duration=1.5) for i in range(5)]
    transcript=Transcript(segments=[Segment(0,4,'These are real timed captions',[Word('These',0,.6),Word('are',.6,1.2),Word('real',1.2,1.8),Word('timed',1.8,2.5),Word('captions',2.5,3.5)])])
    analysis=AnalysisResult(duration=4,transcript=transcript)
    settings=RenderSettings(width=180,height=320,fps=10,encoder_preference='cpu',threads=1,caption_style='clean_professional',caption_size=24,sound_effects=False,smart_reframe=False,remove_silence=False)
    paths=AppPaths(tmp_path/'App data with spaces');paths.ensure()
    with patch('clipos.video.pipeline.PATHS',paths):
        results=ClipOSPipeline(db,pid).export_clips(ids,tmp_path/'out',settings,analysis)
    assert len(results)==5
    assert not [r for r in results if r.get('error')]
    assert len({Path(r['output_path']).parent for r in results})==1
    assert all(probe(r['output_path']).has_audio for r in results)
    assert all(Path(db.get_clip(cid)['thumbnail_path']).is_file() for cid in ids)


def test_real_one_click_import_edit_review_export_flow(db,tmp_path):
    from clipos.core.ffmpeg import ffmpeg_available,run_ffmpeg
    from clipos.core.config import AppPaths
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from clipos.ui.main_window import MainWindow
    import time
    if not ffmpeg_available():pytest.skip('native FFmpeg unavailable')
    source=tmp_path/'wizard recording.mp4'
    run_ffmpeg(['-f','lavfi','-i','testsrc2=size=320x180:rate=10:duration=4','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(source)])
    paths=AppPaths(tmp_path/'app');paths.ensure()
    db.set_settings({'auto_caption':False,'default_clip_count':1,'use_gpu':'cpu','output_dir':str(tmp_path/'delivery'),'restore_on_launch':False})
    app=QApplication.instance() or QApplication([])
    window=MainWindow(db);page=window.pages['workflow']
    def wait_until(predicate,seconds=20):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            app.processEvents();QTest.qWait(20)
            if predicate():return
        raise AssertionError(page.status.text()+'\n'+page.errors.toPlainText())
    try:
        with patch('clipos.ui.pages.workflow.PATHS',paths),patch('clipos.video.pipeline.PATHS',paths),patch('clipos.video.importer.PATHS',paths):
            page.source.setText(str(source));page._import(True)
            wait_until(lambda:page.review.count()==1 and not page._busy())
            assert page.project_id==window.active_project
            assert Path(page._review_rows[0]['output_path']).is_file()
            page.go(3);page._export()
            wait_until(lambda:bool(page._last_folder) and not page._busy())
            assert len(list(Path(page._last_folder).glob('*.mp4')))==1
            assert page._last_folder.startswith(str(tmp_path/'delivery'))
    finally:window.close();app.processEvents()


def test_actual_advanced_timeline_split_layout_captions_and_thread_budget(tmp_path):
    from clipos.core.ffmpeg import ffmpeg_available,run_ffmpeg,probe,FFmpegRunner
    from clipos.captions.caption_engine import CaptionCue
    from clipos.video.timeline import Timeline
    if not ffmpeg_available():pytest.skip('native FFmpeg unavailable')
    source=tmp_path/'timeline source.mp4'
    run_ffmpeg(['-f','lavfi','-i','testsrc2=size=320x180:rate=10:duration=3','-f','lavfi','-i','sine=sample_rate=16000:duration=3','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)])
    timeline=Timeline.from_clip(0,2)
    assert timeline.split_at(1.)
    settings=RenderSettings(width=270,height=480,fps=10,editing_preset='gaming',auto_facecam=False,facecam_rect=(0.,0.,.25,.4),gameplay_rect=(.25,0.,.75,1.),encoder_preference='cpu',threads=1,caption_size=30,sound_effects=False)
    commands=[];real_run=FFmpegRunner.run
    def execute(self,args,**kw):commands.append(args);return real_run(self,args,**kw)
    output=tmp_path/'timeline edited.mp4'
    with patch.object(FFmpegRunner,'run',execute):
        ClipRenderer(tmp_path/'timeline work').render_timeline(source,output,timeline,settings,cues=[CaptionCue(.1,1.5,'Timeline caption',[])])
    info=probe(output)
    assert info.has_audio and info.video.width==270 and info.video.height==480 and 1.8<info.duration<2.3
    assert commands and '-filter_complex_threads' in commands[0]

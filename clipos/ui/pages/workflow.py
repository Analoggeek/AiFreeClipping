"""CLIPOS 2.5: one local project, four connected steps, no publishing controls."""
from pathlib import Path
import json
import threading

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSize
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox,
    QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QProgressBar, QSlider, QSpinBox,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget)
from .base import BasePage
from ..widgets.common import Card, SectionHeader
from ..widgets.crop_selector import CropSelector
from ..widgets.preset_preview import preset_thumbnail
from ...core.config import PATHS
from ...video.presets import PRESETS
from ...captions.caption_engine import CAPTION_STYLES


class Task(QThread):
    progress = Signal(float, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self,function,parent=None):
        super().__init__(parent); self.function=function; self.cancelled=threading.Event()

    def run(self):
        try:self.done.emit(self.function(self))
        except Exception as exc:self.failed.emit(str(exc))


class WorkflowPage(BasePage):
    page_title='Create clips'
    page_subtitle='Import → Select & style → Edit & review → Export. One project, one connected workflow.'

    def build(self):
        self.project_id=None;self.task=None;self.ranges=[];self.facecam=None;self.gameplay=(0.,0.,1.,1.)
        self._loading=False;self.player=None;self._last_folder='';self._review_rows=[]
        steps=QHBoxLayout();self.step_buttons=[];self.group=QButtonGroup(self)
        for i,label in enumerate(('1  Import','2  Select & style','3  Edit & review','4  Export')):
            b=QPushButton(label);b.setCheckable(True);self.group.addButton(b);b.clicked.connect(lambda _=False,n=i:self.go(n));steps.addWidget(b);self.step_buttons.append(b)
        self.content_layout.addLayout(steps)
        self.stack=QStackedWidget();self.content_layout.addWidget(self.stack)
        for build in (self._import_ui,self._select_ui,self._review_ui,self._export_ui):
            page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(0,0,0,0);build(layout);layout.addStretch();self.stack.addWidget(page)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.content_layout.addWidget(self.progress)
        self.status=QLabel('Choose a recording. Your videos are not uploaded.');self.status.setWordWrap(True);self.content_layout.addWidget(self.status)
        self.errors=QTextEdit();self.errors.setReadOnly(True);self.errors.setMaximumHeight(150);self.errors.setPlaceholderText('Per-clip warnings and real export errors appear here.');self.errors.hide();self.content_layout.addWidget(self.errors)
        self.cancel=QPushButton('Cancel current task');self.cancel.setEnabled(False);self.cancel.clicked.connect(self._cancel);self.content_layout.addWidget(self.cancel)
        self.window.project_changed.connect(self._project_changed)
        self.window.settings_changed.connect(self.refresh)
        self.go(0);self._load_preferences()

    def _button(self,text,handler,layout,primary=False):
        b=QPushButton(text);b.clicked.connect(handler)
        if primary:b.setObjectName('Primary')
        layout.addWidget(b);return b

    def _import_ui(self,layout):
        card=Card();card.add(SectionHeader('Import a recording','Local video, or an authorised public video link. No account or publishing step.'))
        self.source=QLineEdit();self.source.setPlaceholderText('Paste a video link or choose a file');card.add(self.source)
        row=QHBoxLayout();self._button('Choose local video',self._choose_file,row);self._button('Import / Download',lambda:self._import(False),row,True);card.add_layout(row)
        b=QPushButton('One-click: import, auto-select & edit');b.setObjectName('Primary');b.clicked.connect(lambda:self._import(True));card.add(b)
        note=QLabel('One-click uses the styles/settings from step 2. If automatic player detection is uncertain, review the output or draw a manual crop and re-edit. Speech models may need a one-time download.');note.setWordWrap(True);card.add(note);layout.addWidget(card)

    def _select_ui(self,layout):
        card=Card();self.project_label=QLabel('No recording selected');self.project_label.setWordWrap(True);card.add(self.project_label)
        card.add(SectionHeader('Choose moments','Use seconds or preview playback. Add multiple ranges, or leave empty for the whole recording.'))
        self.source_video = None
        try:
            from PySide6.QtMultimediaWidgets import QVideoWidget
            self.source_video=QVideoWidget();self.source_video.setMinimumHeight(220);self.source_video.setMaximumHeight(320);card.add(self.source_video)
            source_controls=QHBoxLayout();self._button('Play / pause source',self._play,source_controls)
            self.source_seek=QSlider(Qt.Orientation.Horizontal);self.source_seek.sliderMoved.connect(lambda p:self.player.setPosition(p) if self.player else None);source_controls.addWidget(self.source_seek,1);card.add_layout(source_controls)
        except (ImportError,OSError):pass
        self.crop=CropSelector();self.crop.selected.connect(self._crop_selected);card.add(self.crop)
        row=QHBoxLayout();self.crop_target=QComboBox();self.crop_target.addItems(['Player / facecam region','Gameplay region']);row.addWidget(self.crop_target)
        self._button('Use playhead frame',self._snapshot,row);self._button('Clear crops',self._clear_crops,row);card.add_layout(row)
        self.framing=QComboBox();self.framing.addItem('Automatic player detection (review results)','auto');self.framing.addItem('Manual: gameplay above + selected player below','manual');self.framing.addItem('Gameplay only (no player camera)','gameplay');card.add(self.framing)
        from ...video.layouts import CATALOG
        from ..widgets.preset_preview import layout_thumbnail
        row=QHBoxLayout();row.addWidget(QLabel('Studio layout (Gameplay preset)'))
        self.studio_layout=QComboBox();self.studio_layout.setIconSize(QSize(64,80))
        for key,title,description in CATALOG:
            self.studio_layout.addItem(QIcon(layout_thumbnail(key)),title,key)
            self.studio_layout.setItemData(self.studio_layout.count()-1,description,Qt.ItemDataRole.ToolTipRole)
        row.addWidget(self.studio_layout,1)
        self.camera_size=QDoubleSpinBox();self.camera_size.setRange(20,50);self.camera_size.setDecimals(1);self.camera_size.setSuffix(' % camera');self.camera_size.setValue(100/3);row.addWidget(self.camera_size);card.add_layout(row)
        self.crop_label=QLabel('No manual player region. Draw on the source image to select.');self.crop_label.setWordWrap(True);card.add(self.crop_label)
        row=QHBoxLayout();self.range_start=QDoubleSpinBox();self.range_end=QDoubleSpinBox()
        for spin in (self.range_start,self.range_end):spin.setRange(0,999999);spin.setDecimals(2);spin.setSuffix(' s');row.addWidget(spin)
        self._button('Add range',self._add_range,row);card.add_layout(row)
        row=QHBoxLayout()
        self._button('Start at playhead',lambda:self.range_start.setValue(self._position()),row)
        self._button('End at playhead',lambda:self.range_end.setValue(self._position()),row);card.add_layout(row)
        self.range_list=QListWidget();self.range_list.setMaximumHeight(90);card.add(self.range_list)
        b=QPushButton('Remove selected range');b.clicked.connect(self._remove_range);card.add(b)
        card.add(SectionHeader('Editing presets','Visual recipe thumbnails. Use Preview recipe to render your actual recording.'))
        self.presets=QListWidget();self.presets.setViewMode(QListWidget.ViewMode.IconMode);self.presets.setResizeMode(QListWidget.ResizeMode.Adjust);self.presets.setIconSize(QSize(164,120));self.presets.setMaximumHeight(165)
        for key,(name,desc) in PRESETS.items():
            item=QListWidgetItem(QIcon(preset_thumbnail(key,name)),name);item.setData(Qt.ItemDataRole.UserRole,key);item.setToolTip(desc);self.presets.addItem(item)
        self.presets.currentRowChanged.connect(self._preset_changed);card.add(self.presets)
        row=QHBoxLayout();self.caption=QComboBox()
        for key,style in CAPTION_STYLES.items():self.caption.addItem(QIcon(preset_thumbnail(key,style.name)),style.name,key)
        row.addWidget(QLabel('Captions'));row.addWidget(self.caption,1)
        self.caption_on=QCheckBox('Burn in captions');row.addWidget(self.caption_on)
        self.cap_size=QSpinBox();self.cap_size.setRange(20,100);self.cap_size.setValue(48);row.addWidget(self.cap_size);card.add_layout(row)
        row=QHBoxLayout();self.count=QSpinBox();self.count.setRange(1,30);self.count.setValue(5);row.addWidget(QLabel('Clips'));row.addWidget(self.count)
        self.duration=QComboBox();self.duration.addItems(['15-30','30-45','45-60','60-90']);row.addWidget(self.duration)
        self.enhance=QCheckBox('SDR colour + clarity');row.addWidget(self.enhance)
        self._button('Preview recipe (4 seconds)',self._recipe_preview,row);card.add_layout(row)
        self._button('Edit all clips →',self._edit,layout,True);layout.addWidget(card)

    def _review_ui(self,layout):
        card=Card();card.add(SectionHeader('Review edited videos','Actual rendered outputs, not an unedited source-frame simulation. Check clips to export.'))
        try:
            from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget
            self.video=QVideoWidget();self.video.setMinimumHeight(300);self.video.setMaximumHeight(480)
            self.player=QMediaPlayer(self);self.audio=QAudioOutput(self);self.player.setAudioOutput(self.audio);self.player.setVideoOutput(self.video)
            self.player.errorOccurred.connect(lambda *_:self.status.setText('Embedded decoder could not play this file. Use Open in player; rendered files are preserved.'))
            card.add(self.video);row=QHBoxLayout();self._button('Play / Pause',self._play,row)
            self.seek=QSlider(Qt.Orientation.Horizontal);self.player.durationChanged.connect(self._duration_changed);self.player.positionChanged.connect(self._playhead);self.seek.sliderMoved.connect(self.player.setPosition);row.addWidget(self.seek,1)
            self.clock=QLabel('0:00');row.addWidget(self.clock);card.add_layout(row)
        except (ImportError,OSError):card.add(QLabel('Embedded player unavailable. Use your system player.'))
        self.review=QListWidget();self.review.setIconSize(QSize(64,96));self.review.setMinimumHeight(160);self.review.currentRowChanged.connect(self._review_clip);card.add(self.review)
        row=QHBoxLayout();self._button('Preview original recording',self._preview_source,row);self._button('Open selected clip in player',self._external_clip,row);self._button('Advanced trim',self._advanced,row);card.add_layout(row)
        self._button('Continue to export →',lambda:self.go(3),layout,True);layout.addWidget(card)

    def _export_ui(self,layout):
        card=Card();card.add(SectionHeader('Export checked edited clips','One batch folder: chosen folder / YYYY-MM-DD / recording name / all clips.'))
        self.destination=QLineEdit();card.add(self.destination)
        row=QHBoxLayout();self._button('Choose folder',self._choose_folder,row);self._button('Export checked clips',self._export,row,True);self._button('Open batch folder',self._open_folder,row);card.add_layout(row)
        self.export_summary=QLabel('Edit clips in step 3, then export them together.');self.export_summary.setWordWrap(True);card.add(self.export_summary);layout.addWidget(card)

    def go(self,index):
        if index>0 and not self.project_id:
            self.status.setText('Import or open a project first.') if hasattr(self,'status') else None
            return
        self.stack.setCurrentIndex(index);self.step_buttons[index].setChecked(True)
        if self.player:
            self.player.pause()
            if index==1 and self.source_video is not None:
                self.player.setVideoOutput(self.source_video)
                source=QUrl.fromLocalFile(self.db.get_project(self.project_id)['source_path'])
                if self.player.source()!=source:self.player.setSource(source)
            elif index==2:
                self.player.setVideoOutput(self.video)
        self.scroll.verticalScrollBar().setValue(0)

    def _busy(self):return bool(self.task and self.task.isRunning())

    def _start(self,function,completed):
        if self._busy():return
        self.stack.setEnabled(False);self.cancel.setEnabled(True);self.window.set_busy(True,'Processing local video…');self.errors.clear();self.errors.hide()
        task=Task(function,self);self.task=task
        task.progress.connect(lambda p,m:(self.progress.setValue(int(p)),self.status.setText(m)))
        task.failed.connect(self._failed);task.done.connect(completed);task.finished.connect(self._idle);task.start()

    def _failed(self,message):
        self.status.setText('Operation failed. See details below; no successful export was claimed.');self.errors.setPlainText(message);self.errors.show()

    def _idle(self):
        self.stack.setEnabled(True);self.cancel.setEnabled(False);self.window.set_busy(False)
        self.window.data_changed.emit()
        if getattr(self, '_pending_edit', False):
            self._pending_edit = False
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._edit)

    def _cancel(self):
        if self.task:self.task.cancelled.set();self.status.setText('Cancellation requested. Waiting for the active tool to stop safely…')

    def _choose_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose a recording','','Video (*.mp4 *.mkv *.mov *.avi *.webm *.m4v)')
        if path:self.source.setText(path)

    def _import(self,automatic=False):
        value=self.source.text().strip()
        if not value:self.status.setText('Choose a recording or paste a link.');return
        remote=value.startswith(('http://','https://'))
        if remote and QMessageBox.question(self,'Authorised download','Do you own this recording or have permission to download and edit it? Access restrictions are not bypassed.')!=QMessageBox.StandardButton.Yes:return
        dbpath=self.db.path
        def job(task):
            from ...video.importer import import_local,import_url
            from ...db.database import Database
            def progress(p,m):
                if task.cancelled.is_set():raise RuntimeError('Cancelled')
                task.progress.emit(p,m)
            media=import_url(value,progress_cb=progress) if remote else import_local(value,progress_cb=progress)
            db=Database(dbpath)
            try:
                pid=db.create_project(name=media.title,source_path=media.path,source_type=media.source_type,source_url=media.source_url,thumbnail=media.thumbnail,duration=media.duration,width=media.width,height=media.height,fps=media.fps,has_audio=int(media.has_audio),size_bytes=media.size_bytes)
                return pid
            finally:db.close()
        def imported(pid):
            self.load_project(pid);self.go(1);self.status.setText('Imported. Select moments, composition and style, or edit the whole recording.')
            if automatic:
                # Schedule after QThread.finished so a second task is never lost.
                self._pending_edit = True
        self._start(job,imported)

    def load_project(self,pid):
        if self._busy() and self.project_id and self.project_id!=pid:return
        self.project_id=int(pid);self.db.set_setting('active_project',pid)
        project=self.db.get_project(pid)
        if not project:return
        self.project_label.setText(f"{project['name']} · {project['width']}×{project['height']} · {project['duration']:.1f} seconds")
        self.source.setText(project['source_path']);self.range_start.setMaximum(project['duration']);self.range_end.setMaximum(project['duration']);self.range_end.setValue(project['duration'])
        self.crop.set_image(project['thumbnail'])
        from PySide6.QtGui import QPixmap
        source_image=QPixmap(project['thumbnail'])
        for index,(key,(name,desc)) in enumerate(PRESETS.items()):
            self.presets.item(index).setIcon(QIcon(preset_thumbnail(key,name,source_image)))
        state=json.loads(self.db.get_setting(f'workflow:{pid}','{}') or '{}');self.ranges=state.get('ranges',[]);self.facecam=state.get('facecam');self.gameplay=state.get('gameplay',(0.,0.,1.,1.));self._draw_ranges();self._crop_text()
        self._reload_review();self.window.set_active_project(pid)
        saved_mode=state.get('framing_mode','manual' if self.facecam else 'auto')
        self.framing.setCurrentIndex(max(0,self.framing.findData(saved_mode)))

    def _project_changed(self,pid):
        if pid!=self.project_id:self.load_project(pid)

    def _save_state(self):
        if self.project_id:self.db.set_setting(f'workflow:{self.project_id}',json.dumps({'ranges':self.ranges,'facecam':self.facecam,'gameplay':self.gameplay,'framing_mode':self.framing.currentData()}))

    def _draw_ranges(self):
        self.range_list.clear()
        for a,b in self.ranges:self.range_list.addItem(f'{a:.2f} s → {b:.2f} s')

    def _add_range(self):
        a,b=self.range_start.value(),self.range_end.value()
        if b-a<1:self.status.setText('Select at least one second with end after start.');return
        self.ranges.append((a,b));self._draw_ranges();self._save_state()

    def _remove_range(self):
        n=self.range_list.currentRow()
        if n>=0:self.ranges.pop(n);self._draw_ranges();self._save_state()

    def _crop_selected(self,rect):
        if self.crop_target.currentIndex()==0:self.facecam=rect;self.framing.setCurrentIndex(1)
        else:
            self.gameplay=rect
            if not self.facecam:self.framing.setCurrentIndex(2)
        self._crop_text();self._save_state()

    def _crop_text(self):self.crop_label.setText(f'Player: {self.facecam or "automatic / not selected"}   •   Gameplay: {self.gameplay}')
    def _clear_crops(self):self.facecam=None;self.gameplay=(0.,0.,1.,1.);self.crop.rect=None;self.crop.update();self.framing.setCurrentIndex(0);self._crop_text();self._save_state()

    def _preferences(self):
        return {'editing_preset':self.presets.currentItem().data(Qt.ItemDataRole.UserRole) if self.presets.currentItem() else 'gaming','caption_style':self.caption.currentData(),'auto_caption':self.caption_on.isChecked(),'caption_size':self.cap_size.value(),'default_clip_count':self.count.value(),'default_clip_duration':self.duration.currentText(),'gaming_enhance':self.enhance.isChecked(),'framing_mode':self.framing.currentData(),'studio_layout':self.studio_layout.currentData(),'camera_size':(1/3 if self.camera_size.value()==33.3 else self.camera_size.value()/100)}

    def _load_preferences(self):
        if self._busy():return
        self._loading=True;s=self.db.get_settings()
        self.studio_layout.setCurrentIndex(max(0,self.studio_layout.findData(s.get('studio_layout','bottom'))));self.camera_size.setValue(float(s.get('camera_size',1/3))*100)
        key=s.get('editing_preset','gaming');self.presets.setCurrentRow(list(PRESETS).index(key) if key in PRESETS else 0)
        self.caption.setCurrentIndex(max(0,self.caption.findData(s.get('caption_style','clean_professional'))));self.caption_on.setChecked(bool(s.get('auto_caption',True)));self.cap_size.setValue(int(s.get('caption_size',48)));self.count.setValue(int(s.get('default_clip_count',5)));self.duration.setCurrentText(s.get('default_clip_duration','30-45'));self.enhance.setChecked(bool(s.get('gaming_enhance',False)));self.destination.setText(s.get('output_dir',str(PATHS.exports)));self._loading=False

    def _preset_changed(self,index):
        if index<0 or self._loading:return
        from ...video.renderer import RenderSettings
        from ...video.presets import apply_preset
        key=self.presets.item(index).data(Qt.ItemDataRole.UserRole);style=apply_preset(RenderSettings(),key).caption_style
        self.caption.setCurrentIndex(max(0,self.caption.findData(style)))
        self.db.set_settings({**self._preferences(),'editing_preset':key,'caption_style':style});self.window.settings_changed.emit()

    def _settings(self):
        from ...core.editing import render_settings
        preferences=self._preferences();self.db.set_settings(preferences)
        if self.framing.currentData()=='manual' and not self.facecam:raise ValueError('Draw the actual player region first, or choose automatic/gameplay-only framing.')
        overrides={**preferences,'gameplay_rect':self.gameplay}
        if self.facecam:overrides['facecam_rect']=self.facecam
        return render_settings(self.db,overrides)

    def _edit(self):
        if not self.project_id:return
        try:settings=self._settings()
        except ValueError as exc:self.status.setText(str(exc));return
        pid=self.project_id;dbpath=self.db.path;ranges=list(self.ranges);prefs=self._preferences();self.go(2)
        def job(task):
            from ...db.database import Database
            from ...video.pipeline import ClipOSPipeline,run_full_analysis
            from ...ai.transcription import model_installed,download_whisper_model
            db=Database(dbpath)
            try:
                model=db.get_setting('stt_model','base');project=db.get_project(pid)
                if settings.show_captions and project['has_audio'] and not model_installed(model):
                    if not db.get_settings().get('auto_download_models',True):raise RuntimeError('Download the selected speech model in AI Models before requesting captions.')
                    if not download_whisper_model(model,lambda p,m:task.progress.emit(p*.1,m)):raise RuntimeError('Speech model download failed; no captioned render was claimed.')
                analysis=run_full_analysis(db,pid,clip_count=prefs['default_clip_count'],duration_range=prefs['default_clip_duration'],stt_model=model,language=db.get_setting('stt_language',''),selected_ranges=ranges or None,progress_cb=lambda p:task.progress.emit(p.percent*.35,p.message),cancel_cb=task.cancelled.is_set)
                if settings.show_captions and project['has_audio'] and not analysis.transcript:raise RuntimeError('Transcription failed: '+analysis.transcription_error)
                pipe=ClipOSPipeline(db,pid);pipe.external_cancel=task.cancelled.is_set
                rows=db.list_clips(pid)
                results=pipe.export_clips([c['id'] for c in rows],PATHS.projects/str(pid)/'edited',settings,analysis,progress_cb=lambda i,n,m,p:task.progress.emit(35+(i+p/100)/max(1,n)*65,m),cancel_cb=task.cancelled.is_set)
                if results and all(not r.get('error') for r in results):
                    db.set_setting(f'edited_signature:{pid}',json.dumps({'preferences':prefs,'ranges':ranges,'settings':settings.to_dict()},sort_keys=True))
                return results
            finally:db.close()
        def completed(results):
            self._reload_review();errors=[f"Clip {r['clip_id']}: {r['error']}" for r in results if r.get('error')];warnings=[w for r in results for w in r.get('warnings',[])];self.progress.setValue(100)
            self.status.setText(f'{len(results)-len(errors)} edited; {len(errors)} failed. Review the actual clips, then export.')
            if errors or warnings:self.errors.setPlainText('\n\n'.join(errors+warnings));self.errors.show()
        self._start(job,completed)

    def _reload_review(self):
        self.review.clear();self._review_rows=[]
        if not self.project_id:return
        for c in self.db.list_clips(self.project_id):
            c=dict(c)
            if c['status'] not in ('rendered','exported') or not c['output_path'] or not Path(c['output_path']).is_file():continue
            self._review_rows.append(c);item=QListWidgetItem(QIcon(c['thumbnail_path']),f"{c['title']} · {c['duration']:.1f}s");item.setData(Qt.ItemDataRole.UserRole,c['id']);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked);self.review.addItem(item)
        if self.review.count():self.review.setCurrentRow(0)

    def _review_clip(self,index):
        if 0<=index<len(self._review_rows) and self.player:self.player.setSource(QUrl.fromLocalFile(self._review_rows[index]['output_path']))
    def _play(self):
        if self.player:
            if self.player.playbackState()==self.player.PlaybackState.PlayingState:self.player.pause()
            else:self.player.play()
    def _duration_changed(self,duration):
        self.seek.setRange(0,int(duration))
        if hasattr(self,'source_seek'):self.source_seek.setRange(0,int(duration))
    def _playhead(self,pos):
        if hasattr(self,'source_seek') and not self.source_seek.isSliderDown():self.source_seek.setValue(pos)
        if not self.seek.isSliderDown():self.seek.setValue(pos)
        self.clock.setText(f'{pos//60000}:{pos//1000%60:02d}')
    def _position(self):return self.player.position()/1000 if self.player else self.range_start.value()
    def _preview_source(self):
        if self.project_id and self.player:self.player.setSource(QUrl.fromLocalFile(self.db.get_project(self.project_id)['source_path']));self.go(2);self.status.setText('Original recording preview. Set the playhead, then return to Select & style to mark ranges/crops.')
    def _external_clip(self):
        index=self.review.currentRow()
        if 0<=index<len(self._review_rows):QDesktopServices.openUrl(QUrl.fromLocalFile(self._review_rows[index]['output_path']))
    def _advanced(self):
        index=self.review.currentRow()
        if 0<=index<len(self._review_rows):self.window.open_in_editor(self.project_id,self._review_rows[index]['id'])

    def _snapshot(self):
        if not self.project_id:return
        project=dict(self.db.get_project(self.project_id));position=self._position();out=PATHS.projects/str(self.project_id)/'crop-frame.jpg'
        def job(task):
            from ...core.ffmpeg import extract_thumbnail
            out.parent.mkdir(parents=True,exist_ok=True)
            if not extract_thumbnail(project['source_path'],out,position):raise RuntimeError('Could not decode this source frame')
            return str(out)
        self._start(job,lambda path:self.crop.set_image(path))

    def _recipe_preview(self):
        if not self.project_id:return
        try:settings=self._settings()
        except ValueError as exc:self.status.setText(str(exc));return
        project=dict(self.db.get_project(self.project_id));start=self.ranges[0][0] if self.ranges else self.range_start.value();out=PATHS.projects/str(self.project_id)/'recipe-preview.mp4'
        settings.width,settings.height=360,640;settings.encoder_preference='cpu';settings.show_captions=False
        def job(task):
            from ...video.renderer import ClipRenderer
            result=ClipRenderer(out.parent/'preview-work').render(project['source_path'],out,start,min(project['duration'],start+4),settings,cancel_cb=task.cancelled.is_set)
            if result.cancelled:raise RuntimeError('Cancelled')
            return str(out)
        def completed(path):
            self.go(2)
            if self.player:self.player.setSource(QUrl.fromLocalFile(path));self.player.play()
            else:QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            self.status.setText('Actual 4-second composition/colour preview. Captions are added after transcription in Edit.')
        self._start(job,completed)

    def _choose_folder(self):
        value=QFileDialog.getExistingDirectory(self,'Export destination',self.destination.text())
        if value:self.destination.setText(value);self.db.set_setting('output_dir',value)
    def _export(self):
        selected=[self.review.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.review.count()) if self.review.item(i).checkState()==Qt.CheckState.Checked]
        if not selected:self.status.setText('Edit clips and check at least one clip in step 3.');return
        root=self.destination.text().strip()
        if not root:self.status.setText('Choose an export folder.');return
        try:settings=self._settings()
        except ValueError as exc:self.status.setText(str(exc));return
        expected=json.dumps({'preferences':self._preferences(),'ranges':self.ranges,'settings':settings.to_dict()},sort_keys=True)
        saved=self.db.get_setting(f'edited_signature:{self.project_id}','')
        if saved and saved!=expected:
            self.status.setText('Style, ranges or settings changed after editing. Run Edit all clips again before exporting.');return
        self.db.set_setting('output_dir',root);pid=self.project_id;dbpath=self.db.path
        def job(task):
            from ...db.database import Database
            from ...video.delivery import deliver_clips
            db=Database(dbpath)
            try:return deliver_clips(db,pid,selected,root,task.cancelled.is_set)
            finally:db.close()
        def completed(result):
            self._last_folder=result['output_dir'];errors=[r['error'] for r in result['results'] if r.get('error')];ok=len(result['results'])-len(errors)
            self.export_summary.setText(f'{ok} clips exported together to:\n{self._last_folder}');self.status.setText(f'{ok} exported; {len(errors)} failed.');self.progress.setValue(100 if ok else 0)
            if errors:self.errors.setPlainText('\n'.join(errors));self.errors.show()
        self._start(job,completed)
    def _open_folder(self):
        if self._last_folder:QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_folder))

    def refresh(self):
        self._load_preferences()
        if not self.project_id and self.db.get_settings().get('restore_on_launch',True):
            pid=self.db.get_setting('active_project','')
            if str(pid).isdigit():self.load_project(int(pid))
        elif self.project_id and not self._busy():self._reload_review()

    def shutdown(self):
        if self.player:self.player.stop()
        if self._busy():self.task.cancelled.set();self.task.wait()

"""Multi-source edits, decoded video, native audio-clock playback path and export.

Silent mode is labelled separately. Native A/V accuracy/performance acceptance
remains separate from headless widget/PCM tests.
"""
from pathlib import Path
import queue
import threading
import time

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,QDoubleSpinBox,QFileDialog,QHBoxLayout,QLabel,QPushButton,
    QProgressBar,QTableWidget,QTableWidgetItem,QScrollArea,
)

from ...core.config import PATHS
from ...core.ffmpeg import FFmpegCancelled
from ...video.multitrack import MultitrackProject
from ...video.multitrack_preview import FrameCompositor
from ...video.multitrack_render import export_project
from .base import BasePage
from ..widgets.multitrack_timeline import MultitrackTimeline


class FrameWorker(QThread):
    ready=Signal(int,float,object)
    failed=Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.requests=queue.Queue(maxsize=1)
        self.stopping=threading.Event()

    def request(self,project,position,generation):
        try:self.requests.get_nowait()
        except queue.Empty:pass
        self.requests.put_nowait((project.to_dict(),position,generation))
        if not self.isRunning():self.start()

    def run(self):
        compositor=FrameCompositor()
        try:
            while not self.stopping.is_set():
                try:data,position,generation=self.requests.get(timeout=.1)
                except queue.Empty:continue
                try:
                    frame=compositor.frame(MultitrackProject.from_dict(data),position)
                    h,w=frame.shape[:2]
                    rgb=frame[:,:,::-1].copy()
                    image=QImage(rgb.data,w,h,rgb.strides[0],QImage.Format.Format_RGB888).copy()
                    self.ready.emit(generation,position,image)
                except Exception as exc:self.failed.emit(str(exc))
        finally:compositor.close()


class WaveformWorker(QThread):
    ready=Signal(str,object)
    failed=Signal(str)

    def __init__(self,media,parent=None):
        super().__init__(parent)
        self.media_id=media.id;self.path=media.path;self.cancelled=threading.Event()

    def run(self):
        from ...video.waveform import build_waveform
        try:
            data=build_waveform(self.path,PATHS.cache/'waveforms',cancel_cb=self.cancelled.is_set)
            self.ready.emit(self.media_id,data)
        except FFmpegCancelled:self.failed.emit('Waveform analysis cancelled')
        except Exception as exc:self.failed.emit(str(exc))


class ExportWorker(QThread):
    progress=Signal(float,str)
    done=Signal(str)
    failed=Signal(str)

    def __init__(self,project,path,parent=None):
        super().__init__(parent)
        self.project=MultitrackProject.from_dict(project.to_dict())
        self.path=path;self.cancelled=threading.Event()

    def run(self):
        try:
            result=export_project(self.project,self.path,PATHS.cache/'multitrack',
                progress_cb=lambda pct,seconds:self.progress.emit(pct,f'Encoding {pct:.0f}%'),
                cancel_cb=self.cancelled.is_set)
            self.done.emit(result.output_path)
        except FFmpegCancelled:self.failed.emit('Export cancelled; previous output preserved')
        except Exception as exc:self.failed.emit(str(exc))


class MultitrackPage(BasePage):
    page_title='Multitrack workspace'
    page_subtitle='Independent overlapping sources · decoded preview + native audio-clock path · audiovisual export'
    fields=['at','source_in','length','speed','gain','x','y','w','h','opacity']

    def __init__(self,window):
        self.project=MultitrackProject();self.path=None;self.exporter=None;self.generation=0
        self.playing=False;self._building=False;self.audio=None;self._clock_update=False;self.waveform_worker=None
        super().__init__(window)

    def build(self):
        self.frames=FrameWorker(self)
        self.frames.ready.connect(self._frame_ready)
        self.frames.failed.connect(self._error)
        row=QHBoxLayout()
        for text,handler in [('New',self._new),('Import media…',self._import),('Open project…',self._open),
                             ('Save project…',self._save),('Recover workspace',self._recover),
                             ('Export MP4…',self._export),('Cancel export',self._cancel_export)]:
            button=QPushButton(text);button.clicked.connect(handler);row.addWidget(button)
        self.content_layout.addLayout(row)
        self.preview=QLabel('Import local media to preview. No example video is loaded.')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.setMinimumHeight(250)
        self.content_layout.addWidget(self.preview)
        transport=QHBoxLayout()
        self.play=QPushButton('Play silent preview');self.play.clicked.connect(self._toggle_play)
        transport.addWidget(self.play)
        self.play_audio=QPushButton('Play with audio')
        self.play_audio.clicked.connect(self._play_audio)
        transport.addWidget(self.play_audio)
        self.cursor=QDoubleSpinBox();self.cursor.setRange(0,0);self.cursor.setDecimals(3);self.cursor.setSuffix(' s')
        self.cursor.valueChanged.connect(self._seek)
        for text,delta in [('Previous frame',-1),('Next frame',1)]:
            button=QPushButton(text);button.clicked.connect(lambda checked=False,d=delta:self._step_frame(d))
            transport.addWidget(button)
        transport.addWidget(self.cursor)
        self.preview_status=QLabel('Silent decoded preview — no audio clock; not final effects playback')
        transport.addWidget(self.preview_status,1)
        self.content_layout.addLayout(transport)
        timeline_controls=QHBoxLayout()
        snap=QCheckBox('Snap to edges / playhead / frames');snap.setChecked(True)
        snap.toggled.connect(lambda enabled:setattr(self.timeline,'snap',enabled))
        timeline_controls.addWidget(snap)
        zoom=QDoubleSpinBox();zoom.setRange(5,240);zoom.setValue(60);zoom.setSuffix(' px/s')
        zoom.valueChanged.connect(lambda value:self.timeline.set_scale(value))
        timeline_controls.addWidget(zoom)
        for text,handler in [('Analyze selected source waveform',self._waveform),('Cancel waveform',self._cancel_waveform)]:
            button=QPushButton(text);button.clicked.connect(handler);timeline_controls.addWidget(button)
        timeline_controls.addStretch()
        self.content_layout.addLayout(timeline_controls)
        self.timeline=MultitrackTimeline()
        self.timeline.seekRequested.connect(self.cursor.setValue)
        self.timeline.selected.connect(self._timeline_selected)
        self.timeline.editRequested.connect(self._timeline_edit)
        timeline_scroll=QScrollArea();timeline_scroll.setWidget(self.timeline)
        timeline_scroll.setMinimumHeight(200);timeline_scroll.setMaximumHeight(340)
        self.content_layout.addWidget(timeline_scroll)
        self.table=QTableWidget(0,17)
        self.table.setHorizontalHeaderLabels(['Track (later rows on top)','Type','Source','Start','Source in',
            'Source length','Speed','Gain','X','Y','Width','Height','Opacity','Enabled','Locked','Fade in (s)','Fade out (s)'])
        self.table.setMinimumHeight(240)
        self.table.itemChanged.connect(self._cell_changed)
        self.table.itemSelectionChanged.connect(self._table_selection_changed)
        self.content_layout.addWidget(self.table)
        edits=QHBoxLayout()
        self.ripple=QCheckBox('Ripple delete on affected tracks');edits.addWidget(self.ripple)
        self.linked=QCheckBox('Linked A/V timing edits');self.linked.setChecked(True);edits.addWidget(self.linked)
        for text,handler in [('Split at cursor',self._split),('Relink source…',self._relink),('Delete item',self._delete),('Layer earlier',lambda:self._move(-1)),
                             ('Layer later',lambda:self._move(1)),('Undo',self._undo),('Redo',self._redo)]:
            button=QPushButton(text);button.clicked.connect(handler);edits.addWidget(button)
        self.content_layout.addLayout(edits)
        automation=QHBoxLayout()
        automation.addWidget(QLabel('Opacity (video) / gain (audio):'))
        self.key_value=QDoubleSpinBox();self.key_value.setRange(0,4);self.key_value.setDecimals(3);self.key_value.setValue(1.)
        automation.addWidget(self.key_value)
        for text,handler in [('Set key at cursor',lambda:self._keyframe('set')),
                             ('Remove key at cursor',lambda:self._keyframe('remove')),
                             ('Clear selected curve',lambda:self._keyframe('clear'))]:
            button=QPushButton(text);button.clicked.connect(handler);automation.addWidget(button)
        self.content_layout.addLayout(automation)
        self.key_status=QLabel('Select a clip to inspect its linear automation. Times are relative to clip start.')
        self.key_status.setWordWrap(True);self.content_layout.addWidget(self.key_status)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.content_layout.addWidget(self.progress)
        self.status=QLabel('No project exported. Imported video/audio tracks are linked for timing edits by default; uncheck Linked A/V for independent edits.')
        self.status.setWordWrap(True);self.content_layout.addWidget(self.status)
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self._tick)
        self._rows=[]
        self.shortcuts=[]
        for key,handler in [('Ctrl+Z',self._undo),('Ctrl+Shift+Z',self._redo),
                            ('Alt+Left',lambda:self._step_frame(-1)),('Alt+Right',lambda:self._step_frame(1))]:
            shortcut=QShortcut(QKeySequence(key),self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler);self.shortcuts.append(shortcut)

    def _step_frame(self,delta):
        self._stop()
        frame=round(self.cursor.value()*self.project.fps)+delta
        self.cursor.setValue(max(0,min(self.project.duration,frame/self.project.fps)))

    def _error(self,message):
        self._stop()
        self.status.setText(str(message))

    def _stop(self):
        self.playing=False;self.timer.stop();self.play.setText('Play silent preview')
        self.play_audio.setText('Play with audio')
        if self.audio:
            self.audio.stop();self.audio.deleteLater();self.audio=None

    def _new(self):
        self._stop();self.project=MultitrackProject();self.path=None;self._changed()

    def _import(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Import authorized local video/audio','','Media files (*)')
        for path in paths:
            try:self.project.import_media(path,at=self.cursor.value())
            except Exception as exc:self._error(str(exc));break
        if paths:self._changed()

    def _open(self):
        path,_=QFileDialog.getOpenFileName(self,'Open multitrack project','','CLIPOS multitrack (*.clipos-mt.json);;JSON (*.json)')
        if path:self._load(path)

    def _load(self,path):
        try:
            project=MultitrackProject.load(path)
            self._stop();self.project=project;self.path=Path(path);self.generation+=1
            self._rebuild()
            self.status.setText('Recovered previous project revision; latest edits may be missing' if project.recovered_from else f'Opened {path}')
        except Exception as exc:self._error(str(exc))

    def _save(self):
        path,_=QFileDialog.getSaveFileName(self,'Save multitrack project',str(self.path or 'Project.clipos-mt.json'),'JSON (*.json)')
        if path:
            try:self.project.save(path);self.path=Path(path);self.status.setText(f'Saved {path}')
            except Exception as exc:self._error(str(exc))

    def _recover(self):
        self._load(PATHS.projects/'multitrack-workspace'/'recovery.json')

    def _changed(self):
        self._stop();self.generation+=1
        try:self.project.save(PATHS.projects/'multitrack-workspace'/'recovery.json')
        except Exception as exc:self.status.setText(f'Workspace autosave failed: {exc}')
        self._rebuild()

    def _rebuild(self):
        current=self.table.currentRow()
        selected=self._rows[current] if 0<=current<len(self._rows) else None
        column=max(0,self.table.currentColumn())
        self._building=True;self._rows=[]
        sources={media.id:media for media in self.project.media}
        self.table.setRowCount(sum(len(lane.items) for lane in self.project.lanes))
        row=0
        for lane in self.project.lanes:
            for item in lane.items:
                self._rows.append((lane.id,item.id))
                values=[lane.name,lane.kind,Path(sources[item.media_id].path).name]+[getattr(item,field) for field in self.fields]
                for col,value in enumerate(values):
                    cell=QTableWidgetItem(str(value))
                    inactive=(lane.kind=='video' and col==7) or (lane.kind=='audio' and 8<=col<=12)
                    if inactive:cell.setText('—')
                    if col in (1,2) or inactive:cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row,col,cell)
                for col,field in [(15,'fade_in'),(16,'fade_out')]:
                    self.table.setItem(row,col,QTableWidgetItem(str(getattr(item,field))))
                for col,checked in [(13,lane.enabled),(14,lane.locked)]:
                    cell=QTableWidgetItem();cell.setFlags(Qt.ItemFlag.ItemIsUserCheckable|Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
                    cell.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                    self.table.setItem(row,col,cell)
                row+=1
        if selected in self._rows:self.table.setCurrentCell(self._rows.index(selected),column)
        else:self.table.setCurrentCell(-1,-1)
        self._building=False
        self.timeline.set_project(self.project)
        self._refresh_keys()
        self.cursor.setMaximum(self.project.duration)
        if self.project.duration<=0:
            self.preview.clear();self.preview.setText('Import local media to preview. No example video is loaded.')
            self.preview_status.setText('No active media')
        self._seek(self.cursor.value())

    def _waveform(self):
        if self.waveform_worker and self.waveform_worker.isRunning():
            self.status.setText('Waveform analysis already running');return
        try:
            _,item=self.project.find(*self._selected())
            source=next(m for m in self.project.media if m.id==item.media_id)
            if not source.has_audio:raise ValueError('Selected source has no audio')
            if self.waveform_worker:self.waveform_worker.deleteLater()
            self.waveform_worker=WaveformWorker(source,self)
            self.waveform_worker.ready.connect(self._waveform_ready)
            self.waveform_worker.failed.connect(self.status.setText)
            self.status.setText('Analyzing real source audio in background (up to 30 minutes/source)…')
            self.waveform_worker.start()
        except Exception as exc:self._error(str(exc))

    def _waveform_ready(self,media_id,data):
        from ...video.waveform import source_signature
        source=next((m for m in self.project.media if m.id==media_id),None)
        try:
            if source is None or source_signature(source.path)!=data['source_signature']:return
        except OSError:return
        self.timeline.waveforms[media_id]=data;self.timeline.update()
        self.status.setText('Source waveform ready: decoded 8 kHz mono peak overview, before gain/fades/mix.')

    def _cancel_waveform(self):
        if self.waveform_worker:self.waveform_worker.cancelled.set()

    def _table_selection_changed(self):
        if self._building:return
        row=self.table.currentRow()
        self.timeline.selection=self._rows[row] if 0<=row<len(self._rows) else None
        self.timeline.update()
        self._refresh_keys()

    def _refresh_keys(self):
        if not hasattr(self,'key_status'):return
        try:
            lane,item=self.project.find(*self._selected())
            keys=item.opacity_keys if lane.kind=='video' else item.gain_keys
            self.key_value.setMaximum(1 if lane.kind=='video' else 4)
            self.key_status.setText(('Opacity' if lane.kind=='video' else 'Gain')+' keys (clip seconds): '+
                (', '.join(f'{t:.3f}s → {v:.3f}' for t,v in keys) if keys else 'none; constant inspector value applies'))
        except ValueError:self.key_status.setText('Select a clip to inspect linear automation.')

    def _keyframe(self,action):
        try:
            lane,item=self.project.find(*self._selected())
            moment=0. if action=='clear' else self.cursor.value()-item.at
            keys=item.opacity_keys if lane.kind=='video' else item.gain_keys
            if action=='remove':
                nearest=min(keys,key=lambda key:abs(key[0]-moment),default=None)
                if nearest is None or abs(nearest[0]-moment)>.51/self.project.fps:
                    raise ValueError('No keyframe within half a project frame of cursor')
                moment=nearest[0]
            self.project.keyframe(lane.id,item.id,moment,
                self.key_value.value() if action=='set' else None,clear=action=='clear')
            self._changed()
        except Exception as exc:self._error(str(exc))

    def _timeline_selected(self,lane,item):
        if (lane,item) in self._rows:
            self.table.setCurrentCell(self._rows.index((lane,item)),3)

    def _timeline_edit(self,lane,item,values):
        try:
            self.project.change_item(lane,item,linked=self.linked.isChecked(),**values)
            self._changed()
        except Exception as exc:
            self._error(str(exc));self._rebuild()

    def _selected(self):
        row=self.table.currentRow()
        if not 0<=row<len(self._rows):raise ValueError('Select an item first')
        return self._rows[row]

    def _cell_changed(self,cell):
        if self._building:return
        try:
            lane,item=self._rows[cell.row()];column=cell.column()
            if column==0:self.project.lane_state(lane,name=cell.text())
            elif column in (13,14):self.project.lane_state(lane,**{('enabled' if column==13 else 'locked'):cell.checkState()==Qt.CheckState.Checked})
            elif column in (15,16):self.project.change_item(lane,item,**{('fade_in' if column==15 else 'fade_out'):float(cell.text())})
            elif 3<=column<=12:self.project.change_item(lane,item,linked=self.linked.isChecked(),**{self.fields[column-3]:float(cell.text())})
            self._changed()
        except Exception as exc:self._error(str(exc));self._rebuild()

    def _split(self):
        try:self.project.split(*self._selected(),self.cursor.value(),linked=self.linked.isChecked());self._changed()
        except Exception as exc:self._error(str(exc))

    def _relink(self):
        try:
            _,item=self.project.find(*self._selected())
            path,_=QFileDialog.getOpenFileName(self,'Relink selected source for all its items','','Media files (*)')
            if path:self.project.relink(item.media_id,path);self._changed()
        except Exception as exc:self._error(str(exc))

    def _delete(self):
        try:self.project.remove(*self._selected(),ripple=self.ripple.isChecked(),linked=self.linked.isChecked());self._changed()
        except Exception as exc:self._error(str(exc))

    def _move(self,direction):
        try:self.project.move_lane(self._selected()[0],direction);self._changed()
        except Exception as exc:self._error(str(exc))

    def _undo(self):
        if self.project.undo():self._changed()

    def _redo(self):
        if self.project.redo():self._changed()

    def _seek(self,position):
        self.timeline.set_position(position)
        if self.playing and not self._clock_update:self._stop()
        if self.project.duration>0:self.frames.request(self.project,position,self.generation)

    def _toggle_play(self):
        if self.playing:self._stop();return
        if self.project.duration<=0:return
        if self.cursor.value()>=self.project.duration:self.cursor.setValue(0)
        self.clock=time.monotonic();self.origin=self.cursor.value();self.playing=True
        self.play.setText('Pause silent preview');self.timer.start()

    def _play_audio(self):
        if self.audio:self._stop();return
        self._stop()
        if self.project.duration<=0:return
        if self.cursor.value()>=self.project.duration:self.cursor.setValue(0)
        try:
            from ..multitrack_audio import AudioClockPlayer
            self.audio=AudioClockPlayer(self.project,self.cursor.value(),self)
            self.audio.failed.connect(self._error)
            self.audio.ended.connect(self._stop)
            self.playing=True;self.play_audio.setText('Pause audio playback');self.timer.start()
        except Exception as exc:self._error(str(exc))

    def _tick(self):
        position=self.audio.position if self.audio else min(self.project.duration,self.origin+time.monotonic()-self.clock)
        self._clock_update=True
        self.cursor.setValue(position)
        self._clock_update=False
        if position>=self.project.duration:self._stop()

    def _frame_ready(self,generation,position,image):
        if generation!=self.generation:return
        pixmap=QPixmap.fromImage(image)
        self.preview.setPixmap(pixmap.scaled(640,300,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        self.preview_status.setText(f'Decoded frame {position:.3f}s · '+('native audio clock / best-effort video' if self.audio else 'SILENT / best-effort preview'))

    def _export(self):
        if self.exporter and self.exporter.isRunning():self._error('Export already running');return
        path,_=QFileDialog.getSaveFileName(self,'Export multitrack MP4','','MP4 (*.mp4)')
        if not path:return
        self._stop();self.progress.setValue(0)
        self.exporter=ExportWorker(self.project,path,self)
        self.exporter.progress.connect(lambda pct,message:(self.progress.setValue(round(pct)),self.status.setText(message)))
        self.exporter.done.connect(self._export_done)
        self.exporter.failed.connect(self._export_failed)
        self.window.set_busy(True,'Exporting multitrack snapshot…')
        self.exporter.start()

    def _export_done(self,path):
        self.window.set_busy(False)
        self.progress.setValue(100);self.status.setText(f'Exported {path}')

    def _export_failed(self,message):
        self.window.set_busy(False)
        self._error(message)

    def _cancel_export(self):
        if self.exporter and self.exporter.isRunning():self.exporter.cancelled.set()

    def hideEvent(self,event):
        self._stop()
        super().hideEvent(event)

    def shutdown(self):
        self._stop();self.frames.stopping.set();self.frames.wait()
        if self.waveform_worker and self.waveform_worker.isRunning():
            self.waveform_worker.cancelled.set();self.waveform_worker.wait()
        if self.exporter and self.exporter.isRunning():self.exporter.cancelled.set();self.exporter.wait()

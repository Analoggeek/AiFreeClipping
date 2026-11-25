"""Native opt-in long-form automatic downtime editor and actual FFmpeg export."""
import json
import threading
import uuid
from pathlib import Path

from PySide6.QtCore import QThread,Signal
from PySide6.QtWidgets import QFileDialog,QHBoxLayout,QLabel,QPushButton,QProgressBar,QTableWidget,QTableWidgetItem

from .base import BasePage
from ...core.config import PATHS
from ...video import longform
from ...video.timeline import Timeline


class LongformWorker(QThread):
    done=Signal(object)
    failed=Signal(str)
    progress=Signal(float,str)

    def __init__(self,action,args,parent=None):
        super().__init__(parent);self.action=action;self.args=args;self.cancelled=threading.Event()

    def run(self):
        try:self.done.emit(self.action(*self.args,cancel_cb=self.cancelled.is_set,progress_cb=self.progress.emit))
        except Exception as exc:self.failed.emit(str(exc) or 'Long-form operation cancelled')


class LongformPage(BasePage):
    page_title='Automatic long-form editor'
    page_subtitle='Local quiet + frozen-picture evidence · editable chronological keeps · hardware-probed MP4 assembly'

    def __init__(self,window):
        self.path=None;self.data=None;self.worker=None
        super().__init__(window)

    def build(self):
        row=QHBoxLayout()
        for label,handler in [('Analyze local video…',self._analyse),('Open plan…',self._open),
                              ('Save edited plan…',self._save),('Export long-form MP4…',self._export),('Cancel',self._cancel)]:
            button=QPushButton(label);button.clicked.connect(handler);row.addWidget(button)
        self.content_layout.addLayout(row)
        self.status=QLabel('No source analysed. Removes only sustained quiet AND frozen picture; no transcript-gap cuts. Review keeps before export.')
        self.status.setWordWrap(True);self.content_layout.addWidget(self.status)
        self.table=QTableWidget(0,2);self.table.setHorizontalHeaderLabels(['Source start (seconds)','Source end (seconds)'])
        self.table.setMinimumHeight(280);self.content_layout.addWidget(self.table)
        self.progress=QProgressBar();self.content_layout.addWidget(self.progress)

    def _busy(self):return self.worker is not None and self.worker.isRunning()

    def _start(self,action,args,callback):
        if self._busy():self.status.setText('Operation already running');return
        if self.worker:self.worker.deleteLater()
        self.worker=LongformWorker(action,args,self)
        self.worker.progress.connect(lambda p,m:(self.progress.setValue(round(p)),self.status.setText(m)))
        self.worker.done.connect(lambda data:(self.window.set_busy(False),callback(data)))
        self.worker.failed.connect(lambda message:(self.window.set_busy(False),self.status.setText(message)))
        self.window.set_busy(True,'Long-form processing');self.progress.setValue(0);self.worker.start()

    def _analyse(self):
        if self._busy():return
        source,_=QFileDialog.getOpenFileName(self,'Select authorized local video','','Video files (*)')
        if not source:return
        path=PATHS.projects/'longform'/f'{uuid.uuid4().hex}.json'
        self._start(longform.analyse,(source,path),lambda data:self._loaded(path,data))

    def _loaded(self,path,data):
        self.path=Path(path);self.data=data
        segments=data['timeline']['segments'];self.table.setRowCount(len(segments))
        for row,segment in enumerate(segments):
            for col,key in enumerate(('start','end')):self.table.setItem(row,col,QTableWidgetItem(str(segment[key])))
        self.progress.setValue(100)
        self.status.setText(f"Plan ready: {len(segments)} keep segments; measured downtime {data['removed_seconds']:.2f}s. Edit boundaries, save, or export. Whole source shown when no safe downtime evidence exists.")

    def _open(self):
        if self._busy():return
        path,_=QFileDialog.getOpenFileName(self,'Open long-form plan','','JSON (*.json)')
        if path:
            try:data,_=longform.load(path);self._loaded(path,data)
            except Exception as exc:self.status.setText(str(exc))

    def _snapshot(self):
        if not self.data:raise ValueError('Analyze or open a plan first')
        data=json.loads(json.dumps(self.data))
        for row,segment in enumerate(data['timeline']['segments']):
            segment['start']=float(self.table.item(row,0).text());segment['end']=float(self.table.item(row,1).text())
        timeline=Timeline._from_data(data['timeline']);data['removed_seconds']=timeline.source_duration-timeline.duration
        if any(a.end>b.start for a,b in zip(timeline.segments,timeline.segments[1:])):raise ValueError('Keeps must remain chronological and non-overlapping')
        return data

    def _write(self,path):
        data=self._snapshot()
        if Path(path).resolve()==Path(data['source']).resolve() or Path(path).suffix.lower()!='.json':raise ValueError('Save plan as JSON, never over source media')
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        Timeline._atomic_write(Path(path),json.dumps(data,allow_nan=False).encode())
        self.path=Path(path);self.data=data

    def _save(self):
        if self._busy():return
        path,_=QFileDialog.getSaveFileName(self,'Save long-form plan',str(self.path or 'longform.json'),'JSON (*.json)')
        if path:
            try:self._write(path);self.status.setText(f'Saved {path}')
            except Exception as exc:self.status.setText(str(exc))

    def _export(self):
        if self._busy():return
        try:
            if not self.path:raise ValueError('Analyze or open a plan first')
            self._write(self.path)
            output,_=QFileDialog.getSaveFileName(self,'Export chronological long-form video','','MP4 (*.mp4)')
            if output:
                from functools import partial
                from ...core.editing import render_settings
                settings=render_settings(self.db)
                action=partial(longform.export,encoder=settings.encoder_preference,threads=settings.threads)
                self._start(action,(self.path,output),lambda data:self.status.setText(f"Exported {data['output_path']} · {data['duration']:.2f}s · {data['segments']} parts · {data['encoder']}"))
        except Exception as exc:self.status.setText(str(exc))

    def _cancel(self):
        if self.worker:self.worker.cancelled.set()

    def shutdown(self):
        self._cancel()
        if self._busy():self.worker.wait()

"""Review-before-apply local director for actual editor segments."""
from copy import deepcopy
import json
from PySide6.QtWidgets import QHBoxLayout,QLineEdit,QPushButton,QLabel,QMessageBox
from .common import Card
from .gemma_manager import RuntimeJob

class TimelineDirector(Card):
    def __init__(self,editor):
        super().__init__();self.editor=editor;self.worker=None
        self.add(QLabel('AI Director · existing timeline (split, trim, speed, zoom, crop, mute, reorder, delete)'))
        row=QHBoxLayout();self.instruction=QLineEdit();self.instruction.setMaxLength(2000)
        self.instruction.setPlaceholderText('Slow the first segment to 0.75x and zoom to 1.2x…');row.addWidget(self.instruction)
        self.propose=QPushButton('Propose timeline edits');self.propose.clicked.connect(self.request);row.addWidget(self.propose);self.add_layout(row)
        self.status=QLabel('Uses verified local weights; every operation is validated and requires approval.');self.status.setWordWrap(True);self.add(self.status)
    def request(self):
        from ...ai.timeline_director import propose_commands,fingerprint
        editor=self.editor
        if not editor.clip_id or not editor.timeline.segments:self.status.setText('Open a clip timeline first.');return
        if getattr(editor,'_render_worker',None) and editor._render_worker.isRunning():self.status.setText('Wait for the current render before proposing edits.');return
        if self.worker and self.worker.isRunning():return
        timeline=deepcopy(editor.timeline);identity=(editor.project_id,editor.clip_id);digest=fingerprint(timeline)
        instruction=self.instruction.text();db=editor.window.db;host=db.get_setting('ollama_host','http://127.0.0.1:11434');model=db.get_setting('llm_model','gemma:7b')
        self.worker=RuntimeJob(lambda _:propose_commands(instruction,timeline,host,model),self)
        self.worker.error.connect(self.status.setText);self.worker.result.connect(lambda raw:self.review(raw,identity,digest))
        self.worker.finished.connect(lambda:self.propose.setEnabled(True));self.propose.setEnabled(False);self.status.setText('Generating local typed commands; timeline is unchanged…');self.worker.start()
    def review(self,raw,identity,digest):
        from ...ai.timeline_director import apply_commands,fingerprint
        editor=self.editor
        if identity!=(editor.project_id,editor.clip_id) or fingerprint(editor.timeline)!=digest:self.status.setText('Project/timeline changed. Request a fresh plan.');return
        dialog=QMessageBox(self);dialog.setWindowTitle('Review proposed timeline changes')
        dialog.setText('Apply these validated operations as one undoable edit? Preview updates after approval; no final video is rendered automatically.')
        dialog.setDetailedText(json.dumps(raw,indent=2));dialog.setStandardButtons(QMessageBox.StandardButton.Apply|QMessageBox.StandardButton.Cancel);dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if dialog.exec()!=QMessageBox.StandardButton.Apply:self.status.setText('Plan discarded; timeline unchanged.');return
        try:
            if identity!=(editor.project_id,editor.clip_id):raise ValueError('Clip changed; request a new plan')
            if getattr(editor,'_render_worker',None) and editor._render_worker.isRunning():raise ValueError('Render started; wait before applying')
            apply_commands(editor.timeline,raw,digest);editor._after_edit()
            self.status.setText('Approved edits applied. Actual preview/cache and autosaved timeline updated. Use editor Undo/Redo or Render to export.')
        except Exception as exc:self.status.setText(str(exc))
    def shutdown(self):
        if self.worker and self.worker.isRunning():self.worker.wait()

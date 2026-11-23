"""Gaming-first v2 workflow. Local edits never trigger uploads implicitly."""
from pathlib import Path
import json
import threading
import hashlib

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QProgressBar, QTextEdit)
from .base import BasePage
from ..widgets.common import Card, SectionHeader
from ...core.config import PATHS


class Task(QThread):
    progress = Signal(float, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function
        self.cancelled = threading.Event()

    def run(self):
        try:
            self.done.emit(self.function(self))
        except Exception as exc:
            self.failed.emit(str(exc))


class GamingStudioPage(BasePage):
    page_title = 'Gaming Studio 2.0'
    page_subtitle = 'One recording. Player below. Gameplay above. Review before you publish.'

    def build(self):
        self.task = None
        self.clips = []
        self.current = -1
        self.player = None
        source = Card()
        source.add(SectionHeader('01 / Add a recording', 'Your own or authorised public video only.'))
        row = QHBoxLayout()
        self.source = QLineEdit()
        self.source.setPlaceholderText('Paste a YouTube link or choose a local gameplay recording')
        row.addWidget(self.source, 1)
        local = QPushButton('Local video')
        local.clicked.connect(self._local)
        row.addWidget(local)
        source.add_layout(row)
        self.enhance = QCheckBox('Subtle SDR clarity + colour enhancement (not HDR)')
        source.add(self.enhance)
        source.add(QLabel('First run downloads the selected speech model if missing; later edits can run offline.'))
        self.edit = QPushButton('One-click · Find moments, edit & render')
        self.edit.setObjectName('Primary')
        self.edit.clicked.connect(self._edit)
        source.add(self.edit)
        self.progress = QProgressBar()
        source.add(self.progress)
        self.status = QLabel('Ready · no automatic uploads')
        self.status.setWordWrap(True)
        source.add(self.status)
        self.stop = QPushButton('Cancel current task')
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self._cancel)
        source.add(self.stop)
        self.content_layout.addWidget(source)

        review = Card()
        review.add(SectionHeader('02 / Review your finished clips', 'Play the actual rendered MP4 with edits and captions; select clips to upload.'))
        self.list = QListWidget()
        self.list.setMinimumHeight(150)
        self.list.currentRowChanged.connect(self._select)
        review.add(self.list)
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget
            video = QVideoWidget()
            video.setMinimumHeight(360)
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(video)
            self.player.errorOccurred.connect(lambda *_: self.status.setText('Preview decoder unavailable. Use Open in player.'))
            review.add(video)
            controls = QHBoxLayout()
            play = QPushButton('Play / Pause')
            play.clicked.connect(self._play)
            controls.addWidget(play)
            from PySide6.QtWidgets import QSlider
            self.seek = QSlider(Qt.Orientation.Horizontal)
            self.player.durationChanged.connect(lambda d: self.seek.setRange(0, d))
            self.player.positionChanged.connect(self.seek.setValue)
            self.seek.sliderMoved.connect(self.player.setPosition)
            controls.addWidget(self.seek, 1)
            review.add_layout(controls)
        except (ImportError, OSError):
            self.player = None
            review.add(QLabel('Embedded playback is unavailable on this system. Open the rendered MP4 in your player.'))
        external = QPushButton('Open selected clip in player')
        external.clicked.connect(self._open_clip)
        review.add(external)
        self.title = QLineEdit()
        self.title.setMaxLength(100)
        self.title.setPlaceholderText('Review title (max 100 characters)')
        review.add(self.title)
        self.description = QTextEdit()
        self.description.setPlaceholderText('Review description; CLIPOS disclaimer and source attribution are appended on upload.')
        self.description.setMaximumHeight(110)
        review.add(self.description)
        self.tags = QLineEdit()
        self.tags.setPlaceholderText('Relevant tags / keywords, separated by commas')
        review.add(self.tags)
        self.content_layout.addWidget(review)

        upload = Card()
        upload.add(SectionHeader('03 / Publish to YouTube', 'Requires your own Google OAuth Desktop client and YouTube Data API enabled. No views or virality guaranteed.'))
        connect_row = QHBoxLayout()
        self.connect_button = QPushButton('Connect YouTube account')
        self.connect_button.clicked.connect(self._connect)
        connect_row.addWidget(self.connect_button)
        self.disconnect_button = QPushButton('Disconnect stored account')
        self.disconnect_button.clicked.connect(self._disconnect)
        connect_row.addWidget(self.disconnect_button)
        upload.add_layout(connect_row)
        self.privacy = QComboBox()
        self.privacy.addItems(['private', 'unlisted', 'public'])
        upload.add(self.privacy)
        self.kids = QComboBox()
        self.kids.addItem('Required: choose audience', None)
        self.kids.addItem('Not made for kids', False)
        self.kids.addItem('Made for kids', True)
        upload.add(self.kids)
        self.synthetic = QCheckBox('Contains realistic altered or synthetic content requiring disclosure')
        upload.add(self.synthetic)
        self.consent = QCheckBox('I reviewed the selected rendered clips, have reuse rights, and approve the metadata and audience declarations.')
        upload.add(self.consent)
        self.publish_button = QPushButton('One-click · Upload checked clips')
        self.publish_button.setObjectName('Primary')
        self.publish_button.clicked.connect(self._publish)
        upload.add(self.publish_button)
        self.content_layout.addWidget(upload)

    def refresh(self):
        if self.clips or (self.task and self.task.isRunning()):
            return
        pid = self.db.get_setting('last_gaming_project', '')
        if not str(pid).isdigit():
            return
        for row in self.db.list_clips(int(pid)):
            if row['output_path'] and Path(row['output_path']).is_file():
                self.clips.append(dict(row))
                item = QListWidgetItem(row['title'])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.list.addItem(item)
        if self.clips:
            self.list.setCurrentRow(0)
            self.status.setText('Restored rendered clips. Review before upload; nothing is uploaded automatically.')

    def _local(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Gameplay recording', '', 'Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v)')
        if path:
            self.source.setText(path)

    def _start(self, function, completed):
        if self.task and self.task.isRunning():
            return
        self.edit.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(False)
        self.publish_button.setEnabled(False)
        self.stop.setEnabled(True)
        self.progress.setRange(0, 100)
        task = Task(function, self)
        self.task = task
        task.progress.connect(self._progress)
        task.failed.connect(lambda message: self.status.setText('Failed: '+message))
        task.done.connect(completed)
        task.finished.connect(self._idle)
        task.start()

    def _progress(self, pct, message):
        self.progress.setValue(int(pct))
        self.status.setText(message)

    def _idle(self):
        self.edit.setEnabled(True)
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(True)
        self.publish_button.setEnabled(True)
        self.stop.setEnabled(False)

    def _cancel(self):
        if self.task:
            self.task.cancelled.set()
            self.status.setText('Cancellation requested; active OAuth consent may take up to three minutes to time out.')

    def _edit(self):
        value = self.source.text().strip()
        if not value:
            self.status.setText('Paste a link or choose a recording first.')
            return
        if value.startswith(('http://', 'https://')) and QMessageBox.question(self, 'Permission to download', 'Do you own this video or have permission to download and reuse it? DRM and sign-in restrictions are not bypassed.') != QMessageBox.StandardButton.Yes:
            return
        enhance = self.enhance.isChecked()
        def job(task):
            from ...video.importer import import_url, import_local
            from ...video.pipeline import run_one_click
            from ...db.database import Database
            def progress(pct, message):
                if task.cancelled.is_set():
                    raise RuntimeError('Cancelled')
                task.progress.emit(pct, message)
            result = import_url(value, progress_cb=progress) if value.startswith(('https://','http://')) else import_local(value, progress_cb=progress)
            if task.cancelled.is_set():
                raise RuntimeError('Cancelled')
            db = Database(self.db.path)
            try:
                from ...ai.transcription import model_installed, download_whisper_model
                model = db.get_setting('stt_model', 'base')
                if result.has_audio and not model_installed(model):
                    if not download_whisper_model(model, progress):
                        raise RuntimeError('Speech model download failed. Open AI Models and retry; no captioned edit was claimed.')
                pid = db.create_project(name=result.title, source_path=result.path,
                    source_type=result.source_type, source_url=result.source_url,
                    duration=result.duration, width=result.width, height=result.height,
                    fps=result.fps, has_audio=int(result.has_audio), size_bytes=result.size_bytes)
                task.progress.emit(0, 'Import complete. Analysing gameplay…')
                summary = run_one_click(db, pid, PATHS.exports / str(pid), clip_count=5,
                    stt_model=db.get_setting('stt_model', 'base'), recipe='gaming', gaming_enhance=enhance,
                    progress_cb=lambda p: progress(p.percent, p.message), cancel_cb=task.cancelled.is_set)
                return {'project_id': pid, 'summary': summary}
            finally:
                db.close()
        self._start(job, self._edited)

    def _edited(self, result):
        self.current = -1
        self.clips = []
        self.list.clear()
        self.db.set_setting('last_gaming_project', result['project_id'])
        summary = result['summary']
        successful = {e['clip_id']: e for e in summary['exports'] if not e.get('error')}
        for row in self.db.list_clips(result['project_id']):
            if row['id'] not in successful:
                continue
            clip = dict(row)
            self.clips.append(clip)
            item = QListWidgetItem(clip['title'])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list.addItem(item)
        warnings = [w for info in successful.values() for w in info.get('warnings', [])]
        missing = summary['analysis'].transcription_error
        self.status.setText(f"{len(self.clips)} clips rendered; {len(summary['errors'])} failed. Review and check clips before uploading. " + (missing or '') + (' Warnings: '+'; '.join(dict.fromkeys(warnings)) if warnings else ''))
        self.consent.setChecked(False)
        if self.clips:
            self.list.setCurrentRow(0)

    def _save_current(self):
        if 0 <= self.current < len(self.clips):
            clip = self.clips[self.current]
            clip['title'], clip['description'] = self.title.text(), self.description.toPlainText()
            clip['keywords'] = json.dumps([t.strip() for t in self.tags.text().split(',') if t.strip()])
            self.db.update_clip(clip['id'], title=clip['title'], description=clip['description'], keywords=clip['keywords'])

    def _select(self, row):
        self._save_current()
        self.current = row
        if not 0 <= row < len(self.clips):
            return
        clip = self.clips[row]
        self.title.setText(clip['title'])
        self.description.setPlainText(clip['description'])
        self.tags.setText(', '.join(json.loads(clip['keywords'] or '[]')))
        self.consent.setChecked(False)
        if self.player:
            self.player.setSource(QUrl.fromLocalFile(clip['output_path']))

    def _play(self):
        if self.player:
            if self.player.playbackState() == self.player.PlaybackState.PlayingState:
                self.player.pause()
            else:
                self.player.play()

    def _open_clip(self):
        if 0 <= self.current < len(self.clips):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.clips[self.current]['output_path']))

    def _connect(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Google OAuth Desktop client JSON', '', 'JSON (*.json)')
        if filename:
            from ...core.youtube_publish import connect
            self.status.setText('Complete Google account consent in your browser. Tokens are stored only in the OS keychain.')
            self._start(lambda task: connect(filename), lambda _: self.status.setText('YouTube authorization saved securely. Review clips before uploading.'))

    def _disconnect(self):
        try:
            from ...core.youtube_publish import disconnect
            disconnect()
            self.status.setText('Local YouTube token removed. You can also revoke access in your Google account settings.')
        except Exception as exc:
            self.status.setText(str(exc))

    def _publish(self):
        self._save_current()
        selected = [dict(c) for i,c in enumerate(self.clips) if self.list.item(i).checkState() == Qt.CheckState.Checked]
        if not selected or not self.consent.isChecked() or self.kids.currentData() is None:
            self.status.setText('Check rendered clips, declare audience, and confirm review/reuse rights first.')
            return
        from ...core.youtube_publish import upload_metadata
        privacy = self.privacy.currentText()
        try:
            for clip in selected:
                project = self.db.get_project(clip['project_id'])
                clip['upload_body'] = upload_metadata(clip['title'], clip['description'],
                    json.loads(clip['keywords'] or '[]'), project['source_url'], privacy,
                    self.kids.currentData(), self.synthetic.isChecked())
        except Exception as exc:
            self.status.setText(str(exc))
            return
        if QMessageBox.question(self, 'Confirm YouTube upload', f'Upload {len(selected)} rendered clips as {privacy.upper()}? This sends video and approved metadata to Google/YouTube. API quota or verification restrictions may apply.') != QMessageBox.StandardButton.Yes:
            return
        def job(task):
            from ...core.youtube_publish import publish
            from ...db.database import Database
            db = Database(self.db.path)
            results = []
            try:
                for clip in selected:
                    if task.cancelled.is_set():
                        break
                    digest = hashlib.sha256()
                    with open(clip['output_path'], 'rb') as stream:
                        for chunk in iter(lambda: stream.read(1024*1024), b''):
                            if task.cancelled.is_set():
                                raise RuntimeError('Cancelled before upload')
                            digest.update(chunk)
                    key = 'youtube_uploaded_' + digest.hexdigest()
                    previous = db.get_setting(key, '')
                    if previous:
                        results.append(previous + ' (already recorded; not uploaded again)')
                        continue
                    info = publish(clip['output_path'], clip['upload_body'], task.progress.emit, task.cancelled.is_set)
                    db.set_setting(key, info['url'])
                    db.log_activity(clip['project_id'], 'youtube', 'Uploaded clip: '+info['url'])
                    results.append(info['url'])
                return results
            finally:
                db.close()
        self.consent.setChecked(False)
        self._start(job, lambda urls: self.status.setText('Uploaded: '+' | '.join(urls) if urls else 'No uploads completed.'))

    def shutdown(self):
        if self.player:
            self.player.stop()
        if self.task and self.task.isRunning():
            self.task.cancelled.set()
            # Never terminate a thread while it writes an MP4 or uploads data.
            self.task.wait()

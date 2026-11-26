"""Bounded audio-device-clocked composited timeline playback.

Qt multimedia/device availability and actual realtime throughput are runtime
conditions. Late video frames drop; audio is not intentionally discarded.
"""

from collections import deque
import queue
import threading

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

from ...video.multitrack import MultitrackProject
from ...video.live_playback import stream_frames


class StreamWorker(QThread):
    def __init__(self, project, start, parent=None):
        super().__init__(parent)
        self.project = project
        self.start_at = start
        self.cancelled = threading.Event()
        self.frames = queue.Queue(maxsize=24)
        self.process = None
        self.failure = ""

    def publish_process(self, process):
        self.process = process
        if self.cancelled.is_set():
            process.terminate()

    def run(self):
        try:
            for frame in stream_frames(
                self.project,
                start=self.start_at,
                cancelled=self.cancelled.is_set,
                process_ready=self.publish_process,
            ):
                while not self.cancelled.is_set():
                    try:
                        self.frames.put(frame, timeout=0.1)
                        break
                    except queue.Full:
                        pass
                if self.cancelled.is_set():
                    break
        except Exception as exc:
            if not self.cancelled.is_set():
                self.failure = str(exc)

    def stop(self):
        self.cancelled.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()


class LivePlayer(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.worker = None
        self.sink = None
        self.timer = QTimer(self)
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.tick)
        self.running = False
        self.paused = False
        self.audio_pending = bytearray()
        self.video_pending = deque()
        self.received_audio = 0
        layout = QVBoxLayout(self)
        self.image = QLabel(
            "Composited playback · uses the same FFmpeg graph as export"
        )
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumHeight(180)
        layout.addWidget(self.image)
        self.status = QLabel(
            "Start from timeline cursor. Stop playback before editing. Heavy projects may buffer/drop late video frames."
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        for title, fn in [
            ("Play composite from cursor", self.play),
            ("Pause / resume composite", self.pause),
            ("Stop composite", self.stop),
        ]:
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, action=fn: action())
            layout.addWidget(button)

    def play(self):
        if self.studio.worker and self.studio.worker.isRunning():
            self.status.setText("Wait for background work to finish.")
            return
        if not self.stop():
            return
        try:
            from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

            device = QMediaDevices.defaultAudioOutput()
            if device.isNull():
                raise RuntimeError(
                    "No physical audio output device; use rendered timeline preview instead"
                )
            format = QAudioFormat()
            format.setSampleRate(48000)
            format.setChannelCount(2)
            format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            if not device.isFormatSupported(format):
                raise RuntimeError(
                    "Audio output does not support 48 kHz stereo S16; use rendered preview"
                )
            project = MultitrackProject.from_dict(self.studio.project.to_dict())
            start = self.studio.split_time.value()
            if not 0 <= start < project.duration:
                raise ValueError("Move cursor inside the timeline")
            self.sink = QAudioSink(device, format, self)
            self.sink.setBufferSize(48000)
            self.output = self.sink.start()
            if self.output is None:
                raise RuntimeError("Audio device could not start")
            self.audio_pending.clear()
            self.video_pending.clear()
            self.received_audio = 0
            self.start_at = start
            self.worker = StreamWorker(project, start, self)
            self.running = True
            self.paused = False
            self.dropped = 0
            if self.studio.player:
                self.studio.player.pause()
            self.studio.window.set_busy(True, "Composited timeline playback…")
            self.worker.start()
            self.timer.start()
            self.status.setText(
                "Audio-clocked shared-graph playback. Rendering speed depends on project/hardware."
            )
        except Exception as exc:
            self.stop()
            self.status.setText("Composite unavailable: " + str(exc))

    def pause(self):
        if not self.running or not self.sink:
            return
        self.paused = not self.paused
        self.sink.suspend() if self.paused else self.sink.resume()
        self.status.setText("Paused" if self.paused else "Playing composite")

    def tick(self):
        if not self.running or self.paused:
            return
        try:
            # Bound decoded data outside the worker queue as well. Backpressure
            # reaches FFmpeg rather than accumulating multi-hour raw frames.
            while len(self.video_pending) < 12 and len(self.audio_pending) < 192000:
                try:
                    kind, moment, payload = self.worker.frames.get_nowait()
                except queue.Empty:
                    break
                if kind == "audio":
                    self.audio_pending.extend(payload)
                    self.received_audio += len(payload)
                else:
                    self.video_pending.append((moment, payload))
            if self.audio_pending:
                capacity = max(0, self.sink.bytesFree())
                if capacity:
                    written = self.output.write(bytes(self.audio_pending[:capacity]))
                    if written < 0:
                        raise RuntimeError("Audio device write failed")
                    del self.audio_pending[:written]
            clock = self.sink.processedUSecs() / 1_000_000
            frame = None
            while self.video_pending and self.video_pending[0][0] <= clock + 0.01:
                if frame is not None:
                    self.dropped += 1
                _, frame = self.video_pending.popleft()
            if frame is not None:
                height, width, _ = frame.shape
                image = QImage(
                    frame.data,
                    width,
                    height,
                    frame.strides[0],
                    QImage.Format.Format_RGB888,
                ).copy()
                self.image.setPixmap(
                    QPixmap.fromImage(image).scaled(
                        self.image.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            self.studio.graph.set_position(self.start_at + clock)
            if self.worker.failure:
                raise RuntimeError(self.worker.failure)
            if (
                not self.worker.isRunning()
                and self.worker.frames.empty()
                and not self.audio_pending
                and clock >= self.received_audio / 192000 - 0.02
            ):
                dropped = self.dropped
                self.stop()
                self.status.setText(
                    f"Playback ended. Dropped late video frames: {dropped}."
                )
        except Exception as exc:
            self.stop()
            self.status.setText("Playback failed: " + str(exc))

    def stop(self):
        self.timer.stop()
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            if not self.worker.wait(3000):
                self.status.setText("Stopping compositor; retry shortly.")
                return False
        if self.worker:
            while True:
                try:
                    self.worker.frames.get_nowait()
                except queue.Empty:
                    break
            self.worker.deleteLater()
            self.worker = None
        was_running = self.running
        self.running = False
        self.paused = False
        if self.sink:
            self.sink.stop()
            self.sink.deleteLater()
            self.sink = None
        self.audio_pending.clear()
        self.video_pending.clear()
        if was_running:
            self.studio.window.set_busy(False)
        return True

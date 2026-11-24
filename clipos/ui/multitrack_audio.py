"""Bounded PCM delivery to a real Qt audio device; processed audio is the clock.

No device or QtMultimedia backend => explicit failure, not a simulated clock.
"""
from __future__ import annotations

import queue
import subprocess
import sys
import tempfile
import threading

from PySide6.QtCore import QObject,QTimer,Signal
from ..video.multitrack_render import audio_preview_command


class AudioDeviceUnavailable(RuntimeError):pass


class AudioClockPlayer(QObject):
    failed=Signal(str)
    ended=Signal()

    def __init__(self,project,start,parent=None):
        super().__init__(parent)
        try:
            from PySide6.QtMultimedia import QAudioFormat,QAudioSink,QMediaDevices
        except ImportError as exc:
            raise AudioDeviceUnavailable('Qt multimedia backend unavailable; choose silent preview explicitly') from exc
        device=QMediaDevices.defaultAudioOutput()
        if device.isNull():raise AudioDeviceUnavailable('No native audio output device; choose silent preview explicitly')
        fmt=QAudioFormat();fmt.setSampleRate(48000);fmt.setChannelCount(2);fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):raise AudioDeviceUnavailable('Native device does not support 48 kHz stereo PCM preview')
        self.start_time=start;self.end_time=project.duration
        self.queue=queue.Queue(maxsize=8);self.pending=b'';self.finished=False;self.error=None
        self.stop_event=threading.Event()
        self.stderr=tempfile.TemporaryFile()
        self.process=None;self.reader=None;self.sink=None
        try:
            self.process=subprocess.Popen(audio_preview_command(project,start),stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=self.stderr,creationflags=0x08000000 if sys.platform=='win32' else 0)
            self.sink=QAudioSink(device,fmt,self);self.sink.setBufferSize(48000//5*4)
            self.device=self.sink.start()
            if self.device is None:raise AudioDeviceUnavailable('Native audio output could not start')
            self.reader=threading.Thread(target=self._read,daemon=True);self.reader.start()
            self.timer=QTimer(self);self.timer.setInterval(10);self.timer.timeout.connect(self._pump);self.timer.start()
        except Exception:
            self.stop()
            raise

    @property
    def position(self):
        return min(self.end_time,self.start_time+self.sink.processedUSecs()/1000000) if self.sink else self.start_time

    def _read(self):
        try:
            while not self.stop_event.is_set():
                data=self.process.stdout.read(16384)
                if not data:break
                while not self.stop_event.is_set():
                    try:self.queue.put(data,timeout=.1);break
                    except queue.Full:continue
            code=self.process.wait()
            if code and not self.stop_event.is_set():
                self.stderr.seek(0,2);size=self.stderr.tell();self.stderr.seek(max(0,size-4096))
                self.error=self.stderr.read(4096).decode(errors='replace')
        except Exception as exc:
            if not self.stop_event.is_set():self.error=str(exc)
        finally:self.finished=True

    def _pump(self):
        from PySide6.QtMultimedia import QAudio
        if self.sink.error()!=QAudio.Error.NoError:
            self.timer.stop();self.failed.emit(f'Native audio output error: {self.sink.error()}');return
        if self.error:
            self.timer.stop();self.failed.emit(self.error);return
        if not self.pending:
            try:self.pending=self.queue.get_nowait()
            except queue.Empty:pass
        if self.pending:
            available=self.sink.bytesFree()
            # Four bytes/frame; do not submit partial stereo samples.
            count=min(len(self.pending),available)//4*4
            if count:
                written=self.device.write(self.pending[:count])
                if written<0:self.failed.emit('Native audio write failed');self.timer.stop();return
                self.pending=self.pending[written:]
        if self.finished and self.queue.empty() and not self.pending and self.sink.state()==QAudio.State.IdleState:
            self.timer.stop();self.ended.emit()

    def stop(self):
        if hasattr(self,'timer'):self.timer.stop()
        self.stop_event.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        if self.reader and self.reader.is_alive():self.reader.join(timeout=3)
        if self.process and self.process.stdout:self.process.stdout.close()
        if self.sink:self.sink.stop()
        if not self.reader or not self.reader.is_alive():self.stderr.close()

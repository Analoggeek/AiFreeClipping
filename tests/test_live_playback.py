"""Actual shared-graph NUT streaming; no physical audio-device certification."""

from tests.test_multitrack import media
from clipos.video.multitrack import MultitrackProject
from clipos.video.live_playback import stream_frames


def test_actual_stream_composites_audio_and_video_from_seek(media):
    p = MultitrackProject(width=160, height=90, fps=10)
    p.import_media(media[0])
    p.import_media(media[1], at=2)
    p.add_caption("Shared caption graph", 2, 0.8)
    video = []
    audio = []
    for kind, time, payload in stream_frames(p, start=2, max_size=160):
        if kind == "video":
            video.append((time, payload))
        else:
            audio.append((time, payload))
    assert 19 <= len(video) <= 21
    assert video[0][0] == 0
    # RGB output must be blue from the second timeline item, not red source 1.
    pixel = video[0][1][5, 5]
    assert pixel[2] > pixel[0] + 100
    assert abs(sum(len(data) for _, data in audio) / 192000 - 2) < 0.05
    assert max(t for t, _ in audio) < 2.1
    assert video[-1][0] >= 1.8


def test_cancel_before_start_opens_no_process(media):
    p = MultitrackProject(width=160, height=90)
    p.import_media(media[0])
    opened = []
    assert (
        list(stream_frames(p, cancelled=lambda: True, process_ready=opened.append))
        == []
    )
    assert not opened


def test_native_stream_worker_cancels_under_backpressure(media):
    from clipos.ui.widgets.live_player import StreamWorker

    p = MultitrackProject(width=160, height=90, fps=30)
    p.import_media(media[0])
    worker = StreamWorker(p, 0.0)
    worker.start()
    frame = worker.frames.get(timeout=10)
    assert frame[0] in ("audio", "video")
    worker.stop()
    assert worker.wait(5000)
    assert worker.frames.maxsize == 24


def test_pipe_adapter_never_exposes_windows_invalid_seek_callbacks():
    import io
    from clipos.video.live_playback import ReadOnlyPipe

    class WindowsPipe(io.BytesIO):
        def seek(self, *args):
            raise OSError(22, "Invalid argument")

        def tell(self):
            raise OSError(22, "Invalid argument")

    pipe = ReadOnlyPipe(WindowsPipe(b"actual stream bytes"))
    assert pipe.readable() and not pipe.seekable()
    assert not hasattr(pipe, "seek") and not hasattr(pipe, "tell")
    assert pipe.read(6) == b"actual"

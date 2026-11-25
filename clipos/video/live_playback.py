"""Streaming FFmpeg compositor using the same graph as final export.

Produces bounded RGB frames and interleaved stereo PCM, not a cached video file.
Audio-device scheduling lives in the native playback widget. Render speed depends
on effects/hardware; this module does not promise every project plays in realtime.
"""

from pathlib import Path
import math
import subprocess
import tempfile

from ..core.ffmpeg import require_ffmpeg, _CREATE_NO_WINDOW
from .multitrack_render import graph
from .renderer import _filter_args


def stream_command(project, work_dir, *, start=0.0, max_size=960):
    if (
        type(start) not in (float, int)
        or not math.isfinite(start)
        or not 0 <= start < project.duration
    ):
        raise ValueError("Playback start must be inside timeline")
    if type(max_size) is not int or not 64 <= max_size <= 1920:
        raise ValueError("Invalid preview size")
    inputs, filters, video, audio = graph(
        project, work_dir, window=(start, project.duration - start)
    )
    scale = min(1.0, max_size / max(project.width, project.height))
    width = max(2, int(project.width * scale) // 2 * 2)
    height = max(2, int(project.height * scale) // 2 * 2)
    filters += f";{video}trim=start={start:.8f},setpts=PTS-STARTPTS,scale={width}:{height},format=rgb24[livevideo]"
    filters += f";{audio}atrim=start={start:.8f},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=s16:channel_layouts=stereo[liveaudio]"
    return [
        require_ffmpeg(),
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-filter_complex_threads",
        "2",
        *inputs,
        *_filter_args(filters, Path(work_dir), "live"),
        "-map",
        "[livevideo]",
        "-map",
        "[liveaudio]",
        "-c:v",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-c:a",
        "pcm_s16le",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-threads",
        "2",
        "-t",
        str(project.duration - start),
        "-f",
        "nut",
        "pipe:1",
    ]


class ReadOnlyPipe:
    """Expose only read callbacks to PyAV; a live pipe has no seek/tell API.

    Windows file objects have seek/tell methods which raise EINVAL for pipes.
    Passing them directly lets some PyAV builds install an invalid seek callback.
    Do not inherit IOBase (it would reintroduce those methods).
    """

    def __init__(self, pipe):
        self._pipe = pipe

    def read(self, size=-1):
        return self._pipe.read(size)

    def readable(self):
        return True

    def seekable(self):
        return False


def stream_frames(
    project, *, start=0.0, max_size=960, cancelled=None, process_ready=None
):
    """Yield (kind, relative PTS seconds, payload) without unbounded accumulation.

    Video payload is an RGB ndarray; audio payload is packed S16LE stereo bytes.
    Caller must terminate the published process to interrupt a blocked pipe read.
    """
    import av

    with tempfile.TemporaryDirectory(prefix="clipos-live-") as directory:
        with tempfile.TemporaryFile() as errors:
            if cancelled and cancelled():
                return
            process = subprocess.Popen(
                stream_command(project, directory, start=start, max_size=max_size),
                stdout=subprocess.PIPE,
                stderr=errors,
                stdin=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
            )
            if process_ready:
                process_ready(process)
            try:
                with av.open(ReadOnlyPipe(process.stdout), format="nut") as container:
                    for frame in container.decode():
                        if cancelled and cancelled():
                            return
                        moment = (
                            float(frame.pts * frame.time_base)
                            if frame.pts is not None
                            else 0.0
                        )
                        if isinstance(frame, av.VideoFrame):
                            yield "video", moment, frame.to_ndarray(format="rgb24")
                        else:
                            yield "audio", moment, frame.to_ndarray().tobytes()
                if process.wait(timeout=15):
                    errors.seek(0)
                    raise RuntimeError(
                        "Live compositor failed: "
                        + errors.read().decode(errors="replace")[-2000:]
                    )
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                if process.stdout:
                    process.stdout.close()

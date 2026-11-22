"""Visual analysis: scene cuts, face detection, and speaker-aware tracking.

Uses OpenCV for real frame decoding and Haar cascade face detection.  If PySceneDetect
is installed it is used for precise shot-boundary detection; otherwise a built-in
histogram-difference detector provides the same information.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from ..core.logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class Face:
    """A detected face in normalised coordinates (0..1 of frame width/height)."""
    x: float
    y: float
    w: float
    h: float
    confidence: float = 1.0
    timestamp: float = 0.0

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)

    @property
    def area(self) -> float:
        return self.w * self.h

    def to_dict(self) -> dict:
        return {"x": round(self.x, 4), "y": round(self.y, 4),
                "w": round(self.w, 4), "h": round(self.h, 4),
                "c": round(self.confidence, 3), "t": round(self.timestamp, 2)}


@dataclass
class FaceTrack:
    """A temporally contiguous track of faces (a persistent speaker/subject)."""
    track_id: int
    faces: list[Face] = field(default_factory=list)
    label: str = ""
    total_time: float = 0.0

    @property
    def first_seen(self) -> float:
        return self.faces[0].timestamp if self.faces else 0.0

    @property
    def last_seen(self) -> float:
        return self.faces[-1].timestamp if self.faces else 0.0

    @property
    def mean_area(self) -> float:
        if not self.faces:
            return 0.0
        return sum(f.area for f in self.faces) / len(self.faces)

    @property
    def mean_center(self) -> tuple[float, float]:
        if not self.faces:
            return (0.5, 0.5)
        cx = sum(f.center[0] for f in self.faces) / len(self.faces)
        cy = sum(f.center[1] for f in self.faces) / len(self.faces)
        return (cx, cy)

    def faces_between(self, start: float, end: float) -> list[Face]:
        return [f for f in self.faces if start <= f.timestamp <= end]

    def dominant_face(self, start: float, end: float) -> Face | None:
        """Largest face in the window -- the likely current speaker."""
        cands = self.faces_between(start, end)
        if not cands:
            return None
        return max(cands, key=lambda f: f.area)

    def to_dict(self) -> dict:
        return {
            "id": self.track_id,
            "label": self.label,
            "faces": [f.to_dict() for f in self.faces],
            "total_time": round(self.total_time, 2),
            "mean_area": round(self.mean_area, 4),
        }


@dataclass
class SceneCuts:
    times: list[float] = field(default_factory=list)
    method: str = "none"
    count: int = 0

    def nearest(self, t: float, window: float = 3.0) -> float:
        best = 0.0
        best_d = window
        for cut in self.times:
            d = abs(cut - t)
            if d < best_d:
                best_d = d
                best = cut
        return best


@dataclass
class VisualAnalysis:
    width: int = 0
    height: int = 0
    fps: float = 0.0
    duration: float = 0.0
    scenes: SceneCuts = field(default_factory=SceneCuts)
    tracks: list[FaceTrack] = field(default_factory=list)
    brightness: list[float] = field(default_factory=list)
    colorfulness: list[float] = field(default_factory=list)
    motion: list[float] = field(default_factory=list)
    keyframe_times: list[float] = field(default_factory=list)

    def track_for(self, t: float) -> FaceTrack | None:
        """Best track covering time t, weighted by face size."""
        best: FaceTrack | None = None
        best_score = 0.0
        for tr in self.tracks:
            faces = tr.faces_between(t - 0.5, t + 0.5)
            if not faces:
                continue
            score = max(f.area for f in faces)
            if score > best_score:
                best_score = score
                best = tr
        return best

    def face_at(self, t: float) -> Face | None:
        tr = self.track_for(t)
        if tr:
            f = tr.dominant_face(max(0.0, t - 0.5), t + 0.5)
            if f:
                return f
        # Fall back to any track with a nearby face
        for tr in self.tracks:
            f = tr.dominant_face(t - 1.0, t + 1.0)
            if f:
                return f
        return None

    def subject_center(self, t: float) -> tuple[float, float]:
        f = self.face_at(t)
        if f:
            return f.center
        return (0.5, 0.42)


# --------------------------------------------------------------------------------------
# OpenCV loading (optional dependency)
# --------------------------------------------------------------------------------------


def cv2_module():
    """Import OpenCV lazily so the app still runs (with reduced features) without it."""
    try:
        import cv2  # type: ignore
        return cv2
    except Exception as exc:
        log.warning("OpenCV unavailable: %s", exc)
        return None


def scene_detect_available() -> bool:
    try:
        import scenedetect  # noqa: F401
        return True
    except Exception:
        return False


_FACE_CASCADE: dict = {}

_CASCADE_FILES = {
    "frontal": "haarcascade_frontalface_default.xml",
    "profile": "haarcascade_profileface.xml",
    "alt": "haarcascade_frontalface_alt2.xml",
    "upperbody": "haarcascade_upperbody.xml",
}


def _cascade_search_paths() -> list[Path]:
    """Directories that may contain the Haar cascade XML files."""
    from ..core.resources import resource_dir

    paths: list[Path] = []
    bundled = resource_dir("cascades")
    if bundled.exists():
        paths.append(bundled)
    try:
        import cv2  # type: ignore

        paths.append(Path(cv2.data.haarcascades))
    except Exception:
        pass
    return paths


def _get_cascade(cv2, kind: str = "frontal"):
    if kind in _FACE_CASCADE:
        return _FACE_CASCADE[kind]
    fname = _CASCADE_FILES.get(kind, _CASCADE_FILES["frontal"])
    cascade = None
    for base in _cascade_search_paths():
        path = base / fname
        if path.exists():
            c = cv2.CascadeClassifier(str(path))
            if not c.empty():
                cascade = c
                break
    if cascade is None:
        log.warning("Haar cascade '%s' not found; face detection disabled", fname)
    _FACE_CASCADE[kind] = cascade
    return cascade


def cascade_available() -> bool:
    """True when at least one cascade file is present on disk."""
    for base in _cascade_search_paths():
        for fname in _CASCADE_FILES.values():
            if (base / fname).exists():
                return True
    return False


# --------------------------------------------------------------------------------------
# YuNet DNN face detector (preferred -- far more accurate than Haar)
# --------------------------------------------------------------------------------------

_YUNET_FILES = (
    "face_detection_yunet_2023mar.onnx",
    "face_detection_yunet_2023mar_int8.onnx",
)
_yunet_detector = None
_yunet_loaded = False


def _model_search_paths() -> list[Path]:
    from ..core.resources import resource_dir

    paths: list[Path] = []
    bundled = resource_dir("models")
    if bundled.exists():
        paths.append(bundled)
    return paths


def yunet_available() -> bool:
    return any((b / f).exists() for b in _model_search_paths() for f in _YUNET_FILES)


def _get_yunet(cv2):
    """Lazily construct the YuNet detector. Returns None when unavailable."""
    global _yunet_detector, _yunet_loaded
    if _yunet_loaded:
        return _yunet_detector
    _yunet_loaded = True
    if not hasattr(cv2, "FaceDetectorYN_create"):
        log.info("YuNet not supported by this OpenCV build; using Haar cascades")
        _yunet_detector = None
        return None
    for base in _model_search_paths():
        for fname in _YUNET_FILES:
            path = base / fname
            if not path.exists():
                continue
            try:
                det = cv2.FaceDetectorYN_create(
                    str(path), "", (320, 320), 0.6, 0.3, 5000
                )
                _yunet_detector = det
                log.info("YuNet face detector loaded from %s", path.name)
                return det
            except Exception as exc:
                log.warning("YuNet load failed (%s): %s", path.name, exc)
    log.info("YuNet model not found; falling back to Haar cascades")
    _yunet_detector = None
    return None


def _detect_faces_yunet(cv2, frame: np.ndarray) -> list[tuple[float, float, float, float, float]]:
    """Run YuNet on a BGR frame. Returns (x, y, w, h, score) in pixels."""
    det = _get_yunet(cv2)
    if det is None:
        return []
    h, w = frame.shape[:2]
    # YuNet needs the input size set to the frame size for correct coordinates
    try:
        det.setInputSize((w, h))
    except Exception:
        return []
    try:
        _, faces = det.detect(frame)
    except Exception as exc:
        log.debug("YuNet detect failed: %s", exc)
        return []
    out: list[tuple[float, float, float, float, float]] = []
    if faces is None:
        return out
    for f in faces:
        try:
            x, y, fw, fh = float(f[0]), float(f[1]), float(f[2]), float(f[3])
            score = float(f[-1]) if len(f) > 4 else 1.0
        except (TypeError, ValueError, IndexError):
            continue
        if fw <= 0 or fh <= 0:
            continue
        out.append((x, y, fw, fh, score))
    return out


# --------------------------------------------------------------------------------------
# Scene detection
# --------------------------------------------------------------------------------------


def detect_scenes(video_path: str | Path, progress_cb: Callable[[float, str], None] | None = None) -> SceneCuts:
    """Detect shot boundaries. Uses PySceneDetect when present, else histogram diff."""
    video_path = Path(video_path)
    result = SceneCuts()

    if scene_detect_available():
        try:
            from scenedetect import open_video, SceneManager  # type: ignore
            from scenedetect.detectors import ContentDetector  # type: ignore

            video = open_video(str(video_path))
            sm = SceneManager()
            sm.add_detector(ContentDetector(threshold=27.0, min_scene_len=15))
            sm.detect_scenes(video, show_progress=False)
            scenes = sm.get_scene_list(start_in_scene=True)
            result.times = [float(s[0].get_seconds()) for s in scenes[1:]]
            result.method = "pyscenedetect/content"
            result.count = len(result.times)
            return result
        except Exception as exc:
            log.warning("PySceneDetect failed, falling back to histogram: %s", exc)

    cv2 = cv2_module()
    if cv2 is None:
        result.method = "unavailable"
        return result

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        result.method = "unavailable"
        return result

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    prev_hist = None
    cuts: list[float] = []
    frame_idx = 0
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    sample_every = max(1, int(fps / 2))  # 2 samples per second is plenty for cuts

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % sample_every == 0:
            small = cv2.resize(frame, (160, 90))
            hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
            cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
            if prev_hist is not None:
                # Correlation-based similarity; low correlation => a cut.
                corr = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                if corr < 0.55:
                    cuts.append(frame_idx / fps)
            prev_hist = hist
        frame_idx += 1
        if progress_cb and total_frames and frame_idx % 120 == 0:
            progress_cb((frame_idx / total_frames) * 100.0, "Detecting scenes")

    cap.release()
    # Merge cuts that are very close together.
    merged: list[float] = []
    for c in cuts:
        if not merged or c - merged[-1] > 0.8:
            merged.append(c)
    result.times = merged
    result.method = "opencv/histogram"
    result.count = len(merged)
    return result


# --------------------------------------------------------------------------------------
# Frame sampling & faces
# --------------------------------------------------------------------------------------


def sample_frames(
    video_path: str | Path,
    fps_sample: float = 2.0,
    progress_cb: Callable[[float, str], None] | None = None,
) -> tuple[list[np.ndarray], list[float], int, int]:
    """Sample frames at a fixed rate. Returns (frames, timestamps, width, height)."""
    cv2 = cv2_module()
    if cv2 is None:
        return [], [], 0, 0
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return [], [], 0, 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    step = max(1, int(fps / max(0.1, fps_sample)))
    frames: list[np.ndarray] = []
    times: list[float] = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            frames.append(frame)
            times.append(idx / fps)
        idx += 1
        if progress_cb and total and idx % 150 == 0:
            progress_cb((idx / total) * 100.0, "Sampling frames")
    cap.release()
    return frames, times, width, height


def detect_faces_in_frames(
    frames: list[np.ndarray], times: list[float], sample_scale: float = 0.5
) -> list[Face]:
    """Detect faces over sampled frames.

    Uses the YuNet DNN detector when the model is available (accurate on real
    footage, returns a confidence score), otherwise falls back to Haar cascades.
    """
    cv2 = cv2_module()
    if cv2 is None or not frames:
        return []

    out: list[Face] = []
    use_yunet = yunet_available()

    for frame, t in zip(frames, times):
        h, w = frame.shape[:2]
        if use_yunet:
            for (x, y, fw, fh, score) in _detect_faces_yunet(cv2, frame):
                out.append(
                    Face(
                        x=float(x) / w,
                        y=float(y) / h,
                        w=float(fw) / w,
                        h=float(fh) / h,
                        confidence=score,
                        timestamp=float(t),
                    )
                )
            continue

        # Haar fallback
        cascade = _get_cascade(cv2, "frontal")
        if cascade is None or cascade.empty():
            continue
        small = cv2.resize(frame, (int(w * sample_scale), int(h * sample_scale)))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        rects = cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=4,
                                         minSize=(24, 24))
        for (x, y, fw, fh) in rects:
            out.append(
                Face(
                    x=float(x) / small.shape[1],
                    y=float(y) / small.shape[0],
                    w=float(fw) / small.shape[1],
                    h=float(fh) / small.shape[0],
                    confidence=1.0,
                    timestamp=float(t),
                )
            )
    return out


def build_tracks(faces: list[Face], max_gap: float = 2.0) -> list[FaceTrack]:
    """Group faces into persistent tracks by proximity in time and space."""
    if not faces:
        return []
    faces = sorted(faces, key=lambda f: f.timestamp)
    tracks: list[FaceTrack] = []
    for face in faces:
        best: FaceTrack | None = None
        best_dist = 1e9
        for tr in tracks:
            if face.timestamp - tr.last_seen > max_gap:
                continue
            prev = tr.faces[-1]
            cx, cy = face.center
            pcx, pcy = prev.center
            dist = math.hypot(cx - pcx, cy - pcy)
            if dist < best_dist and dist < 0.28:
                best_dist = dist
                best = tr
        if best is None:
            tr = FaceTrack(track_id=len(tracks))
            tr.faces.append(face)
            tracks.append(tr)
        else:
            best.faces.append(face)
    # Compute total visible time per track
    for tr in tracks:
        tr.total_time = sum(
            min(max_gap, f.timestamp - tr.faces[i - 1].timestamp)
            for i, f in enumerate(tr.faces)
            if i > 0
        )
    # Sort by prominence
    tracks.sort(key=lambda t: (t.total_time, t.mean_area), reverse=True)
    for i, tr in enumerate(tracks):
        tr.track_id = i
    return tracks


def analyze_visual(
    video_path: str | Path,
    fps_sample: float = 2.0,
    progress_cb: Callable[[float, str], None] | None = None,
) -> VisualAnalysis:
    """Full visual analysis: scenes, faces, tracks, brightness, colour, motion."""
    result = VisualAnalysis()
    cv2 = cv2_module()
    if cv2 is None:
        return result

    if progress_cb:
        progress_cb(5.0, "Detecting scene changes")
    result.scenes = detect_scenes(video_path, progress_cb)

    if progress_cb:
        progress_cb(35.0, "Sampling frames")
    frames, times, w, h = sample_frames(video_path, fps_sample, progress_cb)
    result.width, result.height = w, h
    if times:
        result.fps = fps_sample
        result.duration = times[-1] + 1.0 / fps_sample
    result.keyframe_times = times

    # Brightness / colourfulness / motion from the sampled frames
    prev_small = None
    brightness: list[float] = []
    colorfulness: list[float] = []
    motion: list[float] = []
    for frame in frames:
        small = cv2.resize(frame, (80, 45))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        brightness.append(float(gray.mean()) / 255.0)
        b, g, r = cv2.split(small.astype(np.float32))
        rg = r - g
        yb = 0.5 * (r + g) - b
        std = math.sqrt(float(np.std(rg)) ** 2 + float(np.std(yb)) ** 2)
        mean = math.sqrt(float(np.mean(rg)) ** 2 + float(np.mean(yb)) ** 2)
        colorfulness.append(float((std + 0.3 * mean) / 255.0))
        if prev_small is not None:
            diff = cv2.absdiff(gray, prev_small)
            motion.append(float(diff.mean()) / 255.0)
        prev_small = gray
    result.brightness = brightness
    result.colorfulness = colorfulness
    result.motion = motion

    if progress_cb:
        progress_cb(70.0, "Detecting faces")
    faces = detect_faces_in_frames(frames, times)
    result.tracks = build_tracks(faces)

    if progress_cb:
        progress_cb(100.0, f"Visual analysis complete ({len(result.tracks)} subject tracks)")
    return result

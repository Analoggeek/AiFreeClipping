"""Local video understanding: YOLOX / YOLO detection, ByteTrack tracking, motion energy.

Heavy libraries are optional. If none are installed the analyser still produces a
useful activity timeline from ffmpeg scene-change detection, so clipping never stalls.
"""
from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..config import CACHE, ffmpeg_binary
from .tracking import ByteTrackLite
from .utils import run_command

_scene_pattern = re.compile(r"pts_time:([0-9.]+).*?scene_score=([0-9.]+)")


def _scene_cuts(path: str, threshold: float = 0.25) -> list[tuple[float, float]]:
    cmd = [
        ffmpeg_binary(), "-hide_banner", "-i", path, "-an", "-vf",
        f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-",
    ]
    proc = run_command(cmd, timeout=300)
    return [
        (float(match.group(1)), float(match.group(2)))
        for match in _scene_pattern.finditer(proc.stderr or "")
    ]


def _frame_sampler(path: str, fps: float, region: dict[str, float] | None, max_frames: int = 900):
    try:
        import cv2  # type: ignore
    except ImportError:
        return None
    capture = cv2.VideoCapture(path)
    source_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(source_fps / max(fps, 0.1))))
    index = 0
    previous = None
    width = capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 1
    height = capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1
    while True:
        ok, frame = capture.read()
        if not ok or index >= max_frames:
            break
        if index % step == 0:
            crop = frame
            if region:
                x1 = int(max(0, region.get("x", 0)) * width)
                y1 = int(max(0, region.get("y", 0)) * height)
                x2 = int(min(1, region.get("x", 0) + region.get("w", 1)) * width)
                y2 = int(min(1, region.get("y", 0) + region.get("h", 1)) * height)
                if x2 > x1 + 10 and y2 > y1 + 10:
                    crop = frame[y1:y2, x1:x2]
            small = cv2.resize(crop, (160, 90))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            motion = 0.0
            if previous is not None:
                motion = float(cv2.absdiff(gray, previous).mean()) / 255.0
            previous = gray
            yield index / source_fps, small, motion, crop
        index += 1
    capture.release()


def _onnx_detector():
    """YOLOX Nano ONNX detector — no Torch needed, works inside packaged builds."""
    weights = CACHE / "yolo" / "yolox_nano.onnx"
    if not weights.exists():
        return None
    try:
        import cv2  # type: ignore
    except ImportError:
        return None
    net = cv2.dnn.readNetFromONNX(str(weights))
    if hasattr(net, "setPreferableBackend"):
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)

    def detect(frame):
        height, width = frame.shape[:2]
        size = 416
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (size, size), swapRB=True, crop=False)
        net.setInput(blob)
        output = net.forward()
        features = output[0] if output.ndim == 3 else output
        boxes: list[tuple[list[float], float]] = []
        classes = [0, 1, 2, 3, 5, 7]
        for row in features:
            confidence = float(row[4])
            if confidence < 0.3:
                continue
            class_scores = row[5:]
            class_id = int(class_scores.argmax())
            if class_id not in classes:
                continue
            score = confidence * float(class_scores[class_id])
            if score < 0.3:
                continue
            cx, cy, bw, bh = (float(value) for value in row[:4])
            x1 = (cx - bw / 2) / size * width
            y1 = (cy - bh / 2) / size * height
            x2 = (cx + bw / 2) / size * width
            y2 = (cy + bh / 2) / size * height
            boxes.append(([x1, y1, x2, y2], score))
        if not boxes:
            return []
        kept = cv2.dnn.NMSBoxes([b for b, _ in boxes], [s for _, s in boxes], 0.3, 0.45)
        indices = [int(i) for i in kept.flatten()] if hasattr(kept, "flatten") else []
        return [boxes[i] for i in indices]

    return detect


def _detector(engine: str):
    """Return a callable(frame) -> [(box, confidence)] using local weights."""
    if engine == "motion":
        return None
    if engine != "ultralytics":
        onnx = _onnx_detector()
        if onnx:
            return onnx
    if engine == "yolox":
        return None
    try:
        from ultralytics import YOLO  # type: ignore

        name = "yolo11n.pt"
        model = YOLO(name)
        classes = [0, 1, 2, 3, 5, 7]  # person, bicycle, car, motorcycle, bus, truck

        def detect(frame):
            results = model.predict(frame, conf=0.3, classes=classes, verbose=False)
            boxes = []
            for result in results:
                for box in result.boxes:
                    xyxy = box.xyxy[0].tolist()
                    boxes.append(([float(v) for v in xyxy], float(box.conf[0])))
            return boxes

        return detect
    except Exception:
        return None


def analyze_sync(
    path: str,
    region: dict[str, float] | None = None,
    fps: float = 2.0,
    engine: str = "auto",
    on_progress=None,
) -> dict[str, Any]:
    sampler = _frame_sampler(path, fps, region)
    tracker = ByteTrackLite()
    samples: list[dict[str, Any]] = []
    detect = _detector(engine)
    used_engine = "motion"
    if on_progress:
        on_progress(10, "Sampling frames…")

    if sampler is not None:
        if detect:
            used_engine = "yolox-onnx + ByteTrack" if (CACHE / "yolo" / "yolox_nano.onnx").exists() else "ultralytics + ByteTrack"
        else:
            used_engine = "opencv-motion + ByteTrack"
        for t, frame, motion, full_frame in sampler:
            detections = detect(full_frame) if detect else []
            tracks = tracker.update(detections) if detections else []
            samples.append(
                {
                    "t": round(t, 3),
                    "activity": round(motion, 4),
                    "people": len({track.track_id for track in tracks}),
                    "detections": len(detections),
                }
            )
    else:
        used_engine = "ffmpeg-scene"
        cuts = _scene_cuts(path)
        if on_progress:
            on_progress(50, "Detecting scene changes…")
        samples = [{"t": t, "activity": min(1.0, score * 2.5), "people": 0, "detections": 0} for t, score in cuts]

    if on_progress:
        on_progress(80, "Building activity timeline…")
    # Normalise and smooth activity to a 0..1 timeline.
    if samples:
        peak = max((s["activity"] for s in samples), default=0) or 1.0
        for sample in samples:
            sample["activity"] = round(min(1.0, sample["activity"] / peak), 3)
    return {
        "engine": used_engine,
        "region": region,
        "fps": fps,
        "timeline": samples,
        "track_count": tracker._next_id - 1,
    }


async def analyze(path: str, region=None, fps: float = 2.0, engine: str = "auto", on_progress=None):
    return await asyncio.to_thread(analyze_sync, path, region, fps, engine, on_progress)

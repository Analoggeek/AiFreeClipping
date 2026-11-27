"""Local video understanding: YOLOX / YOLO detection, ByteTrack tracking, motion energy.

Heavy libraries are optional. If none are installed the analyser still produces a
useful activity timeline from ffmpeg scene-change detection, so clipping never stalls.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..config import CACHE, ffmpeg_binary
from ..db import db
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


def _crop_region(frame, region: dict[str, float] | None, width: float, height: float):
    if not region:
        return frame
    x1 = int(max(0, region.get("x", 0)) * width)
    y1 = int(max(0, region.get("y", 0)) * height)
    x2 = int(min(1, region.get("x", 0) + region.get("w", 1)) * width)
    y2 = int(min(1, region.get("y", 0) + region.get("h", 1)) * height)
    return frame[y1:y2, x1:x2] if x2 > x1 + 10 and y2 > y1 + 10 else frame


REFRAME_VERSION = 1
_MAX_ANALYSIS_SAMPLES = 900


def _sampling_step(source_fps: float, target_fps: float, frame_count: float, max_samples: int) -> int:
    """Choose a useful stride while spreading a bounded sample budget over the whole video."""
    desired = max(1, int(round(source_fps / max(target_fps, 0.1))))
    try:
        total = int(frame_count)
    except (TypeError, ValueError, OverflowError):
        total = 0
    budget_step = math.ceil(total / max(1, max_samples)) if total > 0 else 1
    return max(desired, budget_step)


def _multi_sampler(path: str, fps: float, regions: list[dict[str, float]], max_samples: int = _MAX_ANALYSIS_SAMPLES):
    """Decode the video once and yield one crop/motion pair per focus region."""
    try:
        import cv2  # type: ignore
    except ImportError:
        return None
    capture = cv2.VideoCapture(path)
    source_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    max_samples = max(1, max_samples)
    step = _sampling_step(source_fps, fps, capture.get(cv2.CAP_PROP_FRAME_COUNT), max_samples)
    width = capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 1
    height = capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1
    previous: list[Any] = [None] * len(regions)
    index = 0
    sample_count = 0
    try:
        while sample_count < max_samples:
            ok, frame = capture.read()
            if not ok:
                break
            if index % step == 0:
                crops = []
                motions = []
                for position, region in enumerate(regions):
                    crop = _crop_region(frame, region, width, height)
                    small = cv2.resize(crop, (160, 90))
                    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    motion = float(cv2.absdiff(gray, previous[position]).mean()) / 255.0 if previous[position] is not None else 0.0
                    previous[position] = gray
                    crops.append((small, crop))
                    motions.append(motion)
                sample_count += 1
                yield index / source_fps, crops, motions
            index += 1
    finally:
        capture.release()


def _frame_sampler(path: str, fps: float, region: dict[str, float] | None, max_samples: int = _MAX_ANALYSIS_SAMPLES):
    try:
        import cv2  # type: ignore
    except ImportError:
        return None
    capture = cv2.VideoCapture(path)
    source_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    max_samples = max(1, max_samples)
    step = _sampling_step(source_fps, fps, capture.get(cv2.CAP_PROP_FRAME_COUNT), max_samples)
    index = 0
    sample_count = 0
    previous = None
    width = capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 1
    height = capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1
    try:
        while sample_count < max_samples:
            ok, frame = capture.read()
            if not ok:
                break
            if index % step == 0:
                crop = _crop_region(frame, region, width, height)
                small = cv2.resize(crop, (160, 90))
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                motion = 0.0
                if previous is not None:
                    motion = float(cv2.absdiff(gray, previous).mean()) / 255.0
                previous = gray
                sample_count += 1
                yield index / source_fps, small, motion, crop
            index += 1
    finally:
        capture.release()


def _weights_dir() -> Path:
    configured = db.get_setting("models_folder", "")
    return (Path(configured).expanduser() if configured else CACHE) / "yolo"


def _onnx_detector():
    """YOLOX Nano ONNX detector — no Torch needed, works inside packaged builds."""
    weights = _weights_dir() / "yolox_nano.onnx"
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


def _selected_engine(engine: str) -> str:
    """Resolve the persisted Vision model choice for auto requests."""
    if engine != "auto":
        return engine
    configured = db.get_setting("vision_engine", "auto")
    return configured if configured in {"yolox", "ultralytics", "motion"} else "auto"


def _detector(engine: str):
    """Return a callable(frame) -> [(box, confidence)] using local weights."""
    engine = _selected_engine(engine)
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

        local_weights = _weights_dir() / "yolo11n.pt"
        name = str(local_weights) if local_weights.is_file() else "yolo11n.pt"
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


def _follow_crop_path(
    observations: list[dict[str, Any]], scene_cuts: list[float],
) -> list[list[float]]:
    """Build a calm portrait crop path from tracked subjects, snapping at scene changes.

    Each observation contains normalized track centers and their relative prominence.
    A single subject is committed to at a time; small detector movement is held, while
    sustained subject changes and hard cuts can move the crop deliberately.
    """
    if not observations or not any(sample.get("tracks") for sample in observations):
        return []
    first = observations[0]
    width = float(first.get("width") or 0)
    height = float(first.get("height") or 0)
    if width <= 0 or height <= 0 or width / height <= 9 / 16 + 1e-4:
        return []

    crop_fraction = min(1.0, height * (9 / 16) / width)
    left_limit, right_limit = crop_fraction / 2, 1 - crop_fraction / 2
    cuts = sorted({float(value) for value in scene_cuts if math.isfinite(float(value)) and float(value) >= 0})
    path: list[list[float]] = []
    active_id: int | None = None
    active_score = 0.0
    active_last_seen = float("-inf")
    challenger_id: int | None = None
    challenger_since = 0.0
    crop_x: float | None = None
    moving = False
    previous_t: float | None = None
    cut_index = 0

    def clamp_x(value: float) -> float:
        return max(left_limit, min(right_limit, value))

    def append_key(time_value: float, center: float) -> None:
        if not math.isfinite(time_value) or time_value < 0:
            return
        key = [round(time_value, 6), round(clamp_x(center), 6)]
        if path and abs(path[-1][0] - key[0]) <= 1e-7:
            path[-1] = key
        elif not path or key[0] > path[-1][0]:
            path.append(key)

    for sample in observations:
        t = float(sample.get("t", 0))
        visible: dict[int, dict[str, float]] = {}
        for track in sample.get("tracks") or []:
            try:
                track_id = int(track["id"])
                center = float(track["x"])
                prominence = max(0.0, float(track["prominence"]))
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(center) and math.isfinite(prominence):
                visible[track_id] = {"x": center, "prominence": prominence}
        winner = max(
            visible.items(),
            key=lambda item: (item[1]["prominence"], -item[0]),
            default=None,
        )

        crossed: list[float] = []
        while cut_index < len(cuts) and cuts[cut_index] <= t:
            cut = cuts[cut_index]
            cut_index += 1
            if previous_t is None or cut > previous_t + 1e-6:
                crossed.append(cut)

        if crossed:
            old_x = crop_x if crop_x is not None else 0.5
            for position, cut in enumerate(crossed):
                before_x = old_x if position == 0 else 0.5
                after_x = clamp_x(winner[1]["x"]) if position == len(crossed) - 1 and winner else 0.5
                append_key(max(0.0, cut - 0.0001), before_x)
                append_key(cut, after_x)
            active_id = winner[0] if winner else None
            active_score = winner[1]["prominence"] if winner else 0.0
            active_last_seen = t if winner else float("-inf")
            challenger_id = None
            crop_x = clamp_x(winner[1]["x"]) if winner else 0.5
            moving = False
            append_key(t, crop_x)
            previous_t = t
            continue

        if active_id is None or t - active_last_seen > 1.0:
            if winner:
                active_id, active_score = winner[0], winner[1]["prominence"]
                active_last_seen = t
            challenger_id = None
        elif active_id in visible:
            active_score = visible[active_id]["prominence"]
            active_last_seen = t
            if winner and winner[0] != active_id and winner[1]["prominence"] > max(active_score, 1e-6) * 1.4:
                if challenger_id == winner[0] and t - challenger_since >= 0.8:
                    active_id, active_score = winner[0], winner[1]["prominence"]
                    challenger_id = None
                elif challenger_id != winner[0]:
                    challenger_id, challenger_since = winner[0], t
            else:
                challenger_id = None
        elif winner and t - active_last_seen > 1.0:
            active_id, active_score = winner[0], winner[1]["prominence"]
            active_last_seen = t
            challenger_id = None

        selected = visible.get(active_id) if active_id is not None else None
        target = clamp_x(selected["x"]) if selected else (crop_x if crop_x is not None else 0.5)
        if crop_x is None:
            crop_x = target
        else:
            dt = max(1e-3, t - (previous_t if previous_t is not None else t))
            if not moving and abs(target - crop_x) > 0.05:
                moving = True
            if moving:
                proposed = 0.45 * (target - crop_x)
                maximum = 0.25 * dt
                crop_x += max(-maximum, min(maximum, proposed))
                if abs(target - crop_x) <= 0.012:
                    moving = False
        append_key(t, crop_x)
        previous_t = t

    return path


def _analyze_one(
    path: str, region: dict[str, float] | None, fps: float, engine: str, on_progress,
    lo: float = 0.0, hi: float = 100.0, track_reframe: bool = False,
) -> dict[str, Any]:
    def report(pct: float, message: str) -> None:
        if on_progress:
            on_progress(lo + pct / 100 * (hi - lo), message)

    sampler = _frame_sampler(path, fps, region)
    should_track_reframe = bool(track_reframe and region is None)
    detect = _detector(engine)
    scene_changes: list[tuple[float, float]] | None = None
    if should_track_reframe and detect:
        try:
            scene_changes = _scene_cuts(path)
        except Exception:
            scene_changes = []
    scene_cut_times = [time_value for time_value, _score in (scene_changes or [])]

    tracker = ByteTrackLite()
    samples: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    used_engine = "motion"
    report(10, "Sampling frames…")

    if sampler is not None:
        if detect:
            used_engine = "yolox-onnx + ByteTrack" if _weights_dir().joinpath("yolox_nano.onnx").exists() else "ultralytics + ByteTrack"
        else:
            used_engine = "opencv-motion + ByteTrack"
        cut_index = 0
        previous_sample_t: float | None = None
        tracks_created = 0
        for t, _frame, motion, full_frame in sampler:
            if should_track_reframe:
                while cut_index < len(scene_cut_times) and scene_cut_times[cut_index] <= t:
                    cut_time = scene_cut_times[cut_index]
                    cut_index += 1
                    if previous_sample_t is None or cut_time > previous_sample_t + 1e-6:
                        tracks_created += tracker._next_id - 1
                        tracker = ByteTrackLite()
            detections = detect(full_frame) if detect else []
            tracks = tracker.update(detections)
            samples.append(
                {
                    "t": round(t, 3),
                    "activity": round(motion, 4),
                    "people": len({track.track_id for track in tracks}),
                    "detections": len(detections),
                }
            )
            if should_track_reframe and detect:
                frame_height, frame_width = full_frame.shape[:2]
                # Include newly initialized tracks for framing: ByteTrack's
                # public result intentionally waits for a second hit, but a
                # shot-cut snap cannot wait another analysis interval.
                framing_tracks = [track for track in tracker.tracks if track.last_seen == tracker.frame]
                observations.append({
                    "t": t,
                    "width": frame_width,
                    "height": frame_height,
                    "tracks": [
                        {
                            "id": track.track_id,
                            "x": ((track.box[0] + track.box[2]) / 2) / frame_width,
                            "prominence": (
                                max(0.0, track.box[2] - track.box[0])
                                * max(0.0, track.box[3] - track.box[1])
                                / (frame_width * frame_height)
                                * max(0.05, track.confidence)
                            ),
                        }
                        for track in framing_tracks
                    ],
                })
            previous_sample_t = t
    else:
        used_engine = "ffmpeg-scene"
        cuts = scene_changes if scene_changes is not None else _scene_cuts(path)
        report(50, "Detecting scene changes…")
        samples = [{"t": t, "activity": min(1.0, score * 2.5), "people": 0, "detections": 0} for t, score in cuts]
        tracks_created = 0

    report(80, "Building activity timeline…")
    if samples:
        peak = max((s["activity"] for s in samples), default=0) or 1.0
        for sample in samples:
            sample["activity"] = round(min(1.0, sample["activity"] / peak), 3)
    result = {
        "engine": used_engine,
        "region": region,
        "fps": fps,
        "timeline": samples,
        "track_count": tracks_created + tracker._next_id - 1,
    }
    if should_track_reframe:
        result["crop_path"] = _follow_crop_path(observations, scene_cut_times)
        result["reframe_version"] = REFRAME_VERSION
    return result


def analyze_sync(
    path: str,
    region: dict[str, float] | None = None,
    fps: float = 2.0,
    engine: str = "auto",
    on_progress=None,
    regions: list[dict[str, float]] | None = None,
    track_reframe: bool = False,
) -> dict[str, Any]:
    """Analyse one or several focus regions and fuse them into one activity timeline."""
    selected = [box for box in (regions or []) if box]
    if region and not selected:
        selected = [region]
    if len(selected) <= 1:
        result = _analyze_one(
            path, selected[0] if selected else None, fps, engine, on_progress,
            track_reframe=track_reframe,
        )
        result["regions"] = selected
        result["region_key"] = json.dumps(selected, sort_keys=True)
        return result

    if on_progress:
        on_progress(10, f"Sampling {len(selected)} focus regions in one pass…")
    sampler = _multi_sampler(path, fps, selected)
    detect = _detector(engine)
    trackers = [ByteTrackLite() for _ in selected]
    per_region: list[list[dict[str, Any]]] = [[] for _ in selected]
    used_engine = "motion"
    if sampler is not None:
        if detect:
            used_engine = "yolox-onnx + ByteTrack" if _weights_dir().joinpath("yolox_nano.onnx").exists() else "ultralytics + ByteTrack"
        else:
            used_engine = "opencv-motion + ByteTrack"
        for t, crops, motions in sampler:
            for position, ((_small, crop), motion) in enumerate(zip(crops, motions)):
                detections = detect(crop) if detect else []
                tracks = trackers[position].update(detections)
                per_region[position].append({
                    "t": round(t, 3),
                    "activity": round(motion, 4),
                    "people": len({track.track_id for track in tracks}),
                    "detections": len(detections),
                })
    else:
        used_engine = "ffmpeg-scene"
        cuts = _scene_cuts(path)
        samples = [{"t": t, "activity": min(1.0, score * 2.5), "people": 0, "detections": 0} for t, score in cuts]
        per_region = [list(samples) for _ in selected]

    for samples in per_region:
        if samples:
            peak = max((sample["activity"] for sample in samples), default=0) or 1.0
            for sample in samples:
                sample["activity"] = round(min(1.0, sample["activity"] / peak), 3)

    merged: dict[float, dict[str, Any]] = {}
    for samples in per_region:
        for sample in samples:
            current = merged.setdefault(sample["t"], {"t": sample["t"], "activity": 0.0, "people": 0, "detections": 0})
            current["activity"] = max(current["activity"], sample["activity"])
            current["people"] = max(current["people"], sample.get("people", 0))
            current["detections"] += sample.get("detections", 0)
    timeline = [merged[key] for key in sorted(merged)]
    if on_progress:
        on_progress(94, f"Fused {len(selected)} focus regions…")
    return {
        "engine": used_engine,
        "region": selected[0],
        "regions": selected,
        "region_key": json.dumps(selected, sort_keys=True),
        "fps": fps,
        "timeline": timeline,
        "track_count": max(tracker._next_id - 1 for tracker in trackers),
    }


async def analyze(
    path: str, region=None, fps: float = 2.0, engine: str = "auto", on_progress=None,
    regions=None, track_reframe: bool = False,
):
    return await asyncio.to_thread(
        analyze_sync, path, region, fps, engine, on_progress, regions, track_reframe,
    )

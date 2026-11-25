"""Local YOLOX (YOLO-family) ONNX person detection + supervision ByteTrack.

Continuous decoded frames, not sampled face association. No implicit downloads.
Boxes are body observations, NOT face identity, diarization or speaker labels.
Only official raw-head COCO YOLOX exports with strides 8/16/32 are supported.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import math

import numpy as np


class TrackingUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class PersonObservation:
    frame: int
    timestamp: float
    track_id: int
    x: float
    y: float
    w: float
    h: float
    confidence: float

    def to_dict(self):
        return asdict(self)


def decode_people(output, size, ratio, image_width, image_height, threshold=.1):
    """Decode raw YOLOX heads, retain COCO class 0, and perform person-only NMS."""
    from .visual_analysis import cv2_module
    cv2 = cv2_module()
    if cv2 is None:
        raise TrackingUnavailable('OpenCV is required for person detection')
    if not math.isfinite(threshold) or not 0 < threshold < 1:
        raise ValueError('Invalid detection threshold')
    grids, scales = [], []
    for stride in (8, 16, 32):
        y, x = np.meshgrid(np.arange(size//stride), np.arange(size//stride), indexing='ij')
        grid = np.stack((x, y), axis=-1).reshape(-1, 2)
        grids.append(grid)
        scales.append(np.full((len(grid), 1), stride))
    grid, scale = np.concatenate(grids), np.concatenate(scales)
    raw = np.asarray(output)
    if raw.shape != (1, len(grid), 85):
        raise TrackingUnavailable(f'Unsupported YOLOX output shape: {raw.shape}')
    raw = raw[0].astype(np.float32)
    finite = np.isfinite(raw).all(axis=1)
    # Person must be the strongest COCO class; keep low-confidence observations
    # for ByteTrack's second association pass (not just high-score detections).
    scores = raw[:, 4] * raw[:, 5]
    selected = finite & (scores >= threshold) & (np.argmax(raw[:, 5:], axis=1) == 0)
    centers = (raw[selected, :2] + grid[selected]) * scale[selected]
    sizes = np.exp(np.clip(raw[selected, 2:4], -15, 15)) * scale[selected]
    xyxy = np.concatenate((centers-sizes/2, centers+sizes/2), axis=1) / ratio
    xyxy[:, [0, 2]] = np.clip(xyxy[:, [0, 2]], 0, image_width)
    xyxy[:, [1, 3]] = np.clip(xyxy[:, [1, 3]], 0, image_height)
    scores = scores[selected]
    valid = (xyxy[:, 2] > xyxy[:, 0]) & (xyxy[:, 3] > xyxy[:, 1])
    xyxy, scores = xyxy[valid], scores[valid]
    if not len(xyxy):
        return np.empty((0, 4), np.float32), np.empty(0, np.float32)
    boxes = xyxy.copy()
    boxes[:, 2:] -= boxes[:, :2]
    keep = np.asarray(cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), threshold, .45)).reshape(-1).astype(int)
    return xyxy[keep].astype(np.float32), scores[keep].astype(np.float32)


class LocalYOLOX:
    def __init__(self, model_path):
        path = Path(model_path).expanduser()
        if not path.is_file() or path.suffix.lower() != '.onnx':
            raise TrackingUnavailable('Install/select a trusted local YOLOX raw-head COCO .onnx model first; no automatic download')
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise TrackingUnavailable('Install optional tracking dependencies first') from exc
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        try:
            # CPU is explicit and portable; do not claim unsupported GPU inference.
            self.session = ort.InferenceSession(str(path.resolve()), sess_options=options,
                                                 providers=['CPUExecutionProvider'])
        except Exception as exc:
            raise TrackingUnavailable(f'Cannot load local YOLOX model: {exc}') from exc
        inputs = self.session.get_inputs()
        if len(inputs) != 1:
            raise TrackingUnavailable('YOLOX requires one image input')
        shape = inputs[0].shape
        if len(shape) != 4 or shape[0] != 1 or shape[1] != 3 or shape[2] != shape[3] or shape[2] not in (320, 416, 640):
            raise TrackingUnavailable('Supported YOLOX input: float32 [1,3,S,S], S=320/416/640')
        if inputs[0].type != 'tensor(float)':
            raise TrackingUnavailable('YOLOX image input must be float32')
        self.input_name, self.size = inputs[0].name, shape[2]

    def detect(self, frame):
        from .visual_analysis import cv2_module
        cv2 = cv2_module()
        h, w = frame.shape[:2]
        ratio = min(self.size/h, self.size/w)
        resized = cv2.resize(frame, (max(1, int(w*ratio)), max(1, int(h*ratio))))
        canvas = np.full((self.size, self.size, 3), 114, np.uint8)
        canvas[:resized.shape[0], :resized.shape[1]] = resized
        # YOLOX demo preprocessing is BGR, 0..255 float32, top-left padding.
        tensor = np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], dtype=np.float32)
        try:
            result = self.session.run(None, {self.input_name: tensor})
        except Exception as exc:
            raise TrackingUnavailable(f'Local YOLOX inference failed: {exc}') from exc
        if len(result) != 1:
            raise TrackingUnavailable('Expected one raw YOLOX head output')
        return decode_people(result[0], self.size, ratio, w, h)


def track_video(video_path, model_path, *, cancel_cb=None, progress_cb=None, emit=None,
                scene_cuts=(), detector=None, max_frames=None):
    """Decode every frame and stream confirmed observations to ``emit``.

    Return only metadata/counts; no unbounded observation/frame accumulation.
    Output is media-time (frame/fps), CPU/offline, not a real-time speed claim.
    Scene cuts reset ByteTrack with globally unique IDs in this invocation.
    ``detector`` is a dependency-injection seam, not real-model test evidence.
    """
    from .visual_analysis import cv2_module
    from ..core.ffmpeg import FFmpegCancelled
    cv2 = cv2_module()
    if cv2 is None:
        raise TrackingUnavailable('OpenCV is required for tracking')
    try:
        import os
        os.environ.setdefault("MPLBACKEND","Agg")
        import supervision as sv
    except ImportError as exc:
        raise TrackingUnavailable('Install supervision==0.27.0 using tracking setup; no automatic installation') from exc
    if max_frames is not None and (type(max_frames) is not int or max_frames <= 0):
        raise ValueError('max_frames must be a positive integer')
    detector = detector if detector is not None else LocalYOLOX(model_path)
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise TrackingUnavailable(f'Cannot decode source video: {video_path}')
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or not 0 < fps <= 240:
            raise TrackingUnavailable('Unsupported/unknown source frame rate')
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        def make_tracker():
            return sv.ByteTrack(frame_rate=max(1, round(fps)), lost_track_buffer=30,
                track_activation_threshold=.25, minimum_consecutive_frames=2)
        tracker = make_tracker()
        cuts = iter(sorted(t for t in scene_cuts if math.isfinite(t) and t > 0))
        next_cut = next(cuts, math.inf)
        mapping, next_id = {}, 1
        index, observations = 0, 0
        while max_frames is None or index < max_frames:
            if cancel_cb and cancel_cb():
                raise FFmpegCancelled('Person tracking cancelled')
            ok, frame = capture.read()
            if not ok:
                break
            t = index/fps
            while t >= next_cut:
                tracker, mapping = make_tracker(), {}
                next_cut = next(cuts, math.inf)
            boxes, confidence = detector.detect(frame)
            detections = sv.Detections(xyxy=boxes, confidence=confidence,
                                      class_id=np.zeros(len(boxes), dtype=int))
            tracked = tracker.update_with_detections(detections)
            h, w = frame.shape[:2]
            for box, score, raw_id in zip(tracked.xyxy, tracked.confidence, tracked.tracker_id):
                raw_id = int(raw_id)
                if raw_id not in mapping:
                    mapping[raw_id] = next_id
                    next_id += 1
                x1, y1, x2, y2 = box
                observation = PersonObservation(index, t, mapping[raw_id],
                    float(x1/w), float(y1/h), float((x2-x1)/w), float((y2-y1)/h), float(score))
                if emit:
                    emit(observation)
                observations += 1
            index += 1
            if progress_cb and (index % max(1, round(fps)) == 0):
                progress_cb(min(99., 100*index/max(total, index+1)), 'Tracking people: YOLOX + ByteTrack (CPU)')
        if index == 0:
            raise TrackingUnavailable('Source contains no decodable video frames')
        if total > 0 and index < total-1 and (max_frames is None or index < max_frames):
            raise TrackingUnavailable('Video decode ended before reported frame count; tracking is incomplete')
        if progress_cb:
            progress_cb(100., 'Person tracking complete')
        return {'engine':'YOLOX + supervision ByteTrack', 'frames':index, 'fps':fps,
                'observations':observations, 'track_count':next_id-1, 'provider':'CPUExecutionProvider',
                'frame_limit_reached':max_frames is not None and index >= max_frames,
                'timing':'frame index / nominal fps; variable-frame-rate timing not certified'}
    finally:
        capture.release()


def write_tracks(video_path, model_path, output_path, **kwargs):
    """Atomically stream observations + a terminal summary, preserving old output on error."""
    import hashlib
    import json
    import os
    import tempfile
    output = Path(output_path)
    if output.resolve() == Path(video_path).resolve():
        raise ValueError('Tracking output cannot overwrite source media')
    if model_path and output.resolve() == Path(model_path).expanduser().resolve():
        raise ValueError('Tracking output cannot overwrite model weights')
    source_stat = Path(video_path).stat()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.tracking-', suffix='.tmp', dir=output.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            def emit(observation):
                stream.write(json.dumps({'type':'person', **observation.to_dict()}, allow_nan=False)+'\n')
            summary = track_video(video_path, model_path, emit=emit, **kwargs)
            finished_stat = Path(video_path).stat()
            if (finished_stat.st_size, finished_stat.st_mtime_ns) != (source_stat.st_size, source_stat.st_mtime_ns):
                raise TrackingUnavailable('Source changed during tracking; previous artifact preserved')
            summary['source'] = str(Path(video_path).resolve())
            summary['source_size'] = source_stat.st_size
            summary['source_mtime_ns'] = source_stat.st_mtime_ns
            summary['schema_version'] = 1
            if model_path:
                digest = hashlib.sha256()
                with Path(model_path).expanduser().open('rb') as model:
                    for chunk in iter(lambda:model.read(1024*1024), b''):
                        digest.update(chunk)
                summary['model_sha256'] = digest.hexdigest()
            summary['test_detector_injected'] = kwargs.get('detector') is not None
            stream.write(json.dumps({'type':'summary', **summary}, allow_nan=False)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
        return summary
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

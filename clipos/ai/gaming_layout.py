"""Conservative facecam inference from repeated real face observations.

This is a temporal/position heuristic, not a human-vs-game-character classifier.
Low-confidence detections return None instead of inventing a player rectangle.
"""
from dataclasses import dataclass
from statistics import median
import math


@dataclass(frozen=True)
class GamingLayout:
    facecam: tuple[float, float, float, float]
    gameplay: tuple[float, float, float, float]
    confidence: float
    observations: int
    method: str = 'temporal-face'
    border_confidence: float = 0.0

    def to_dict(self):
        return {"facecam": self.facecam, "gameplay": self.gameplay,
                "confidence": self.confidence, "observations": self.observations,
                "method":self.method,"border_confidence":self.border_confidence}


def infer_layout(faces, timestamps):
    """Prefer small, stationary, peripheral faces recurring across frames."""
    times = sorted(set(timestamps))
    if len(times) < 3:
        return None
    clusters = []
    for face in faces:
        if not (.001 < face.area < .12):
            continue
        cx, cy = face.center
        if .3 < cx < .7 and .25 < cy < .75:
            continue  # Avoid most game characters in the centre of gameplay.
        match = next((c for c in clusters if math.dist(c[0].center, face.center) < .09), None)
        if match is None:
            clusters.append([face])
        else:
            match.append(face)
    candidates = []
    for group in clusters:
        coverage = len({f.timestamp for f in group}) / len(times)
        if len({f.timestamp for f in group}) < 3 or coverage < .45:
            continue
        cx, cy = median(f.center[0] for f in group), median(f.center[1] for f in group)
        drift = median(math.dist(f.center, (cx, cy)) for f in group)
        if drift > .035:
            continue
        fw, fh = median(f.w for f in group), median(f.h for f in group)
        # Include hair, shoulders and some of the original facecam context.
        w, h = min(.48, fw * 2.5), min(.55, fh * 2.7)
        x, y = max(0., min(1-w, cx-w/2)), max(0., min(1-h, cy-h*.42))
        confidence = min(.95, coverage * (1-drift*8))
        candidates.append((confidence, (x,y,w,h), len(group)))
    if not candidates:
        return None
    confidence, cam, count = max(candidates, key=lambda item: item[0])
    x,y,w,h = cam
    # Largest remaining rectangle: don't duplicate the facecam in gameplay.
    regions = [(0.,0.,x,1.), (x+w,0.,1-x-w,1.), (0.,0.,1.,y), (0.,y+h,1.,1-y-h)]
    regions = [r for r in regions if r[2] > .25 and r[3] > .25]
    if not regions:
        return None
    game = max(regions, key=lambda r: r[2]*r[3])
    return GamingLayout(cam, game, confidence, count)


def detect_layout(source, start, end, cancel_cb=None, samples=24):
    """Decode at most 24 downscaled frames for this clip, not the entire source."""
    from .visual_analysis import cv2_module, detect_faces_in_frames
    cv2 = cv2_module()
    if not all(math.isfinite(t) for t in (start,end)) or end<=start:return None
    samples=max(3,min(24,int(samples)))
    if cv2 is None:
        return None
    cap = cv2.VideoCapture(str(source))
    frames, times = [], []
    try:
        if not cap.isOpened():
            return None
        for i in range(samples):
            if cancel_cb and cancel_cb():
                from ..core.ffmpeg import FFmpegCancelled
                raise FFmpegCancelled("Facecam analysis cancelled")
            t = start + (end-start) * (i+.5)/samples
            cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
            ok, frame = cap.read()
            if not ok:
                continue
            h,w = frame.shape[:2]
            if w > 960:
                frame = cv2.resize(frame, (960, max(2, round(h*960/w))))
            frames.append(frame)
            times.append(t)
    finally:
        cap.release()
    faces=detect_faces_in_frames(frames,times)
    seed=infer_layout(faces,times)
    from .panel_edges import refine_panel
    return refine_panel(frames,faces,times,seed,cancel_cb) or seed

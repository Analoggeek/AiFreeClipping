"""Speaker tracking: work out who is talking and keep their face framed.

Strategy
--------
1.  Segment the audio into short frames and compute per-frame energy.
2.  Cluster the *face* tracks by spatial position into "persons" (left/right/centre).
3.  For each face, measure how often it is the largest/most-central face while the
    speaker is actively talking -- that is the person whose voice is driving.
4.  Produce a per-timeline "active subject" so the reframer can follow them.

This works fully offline with no diarisation model: the audio energy envelope is
correlated with face prominence over time, which is a robust signal for podcasts and
talking-head footage.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .audio_analysis import AudioAnalysis, HOP_SECONDS
from .visual_analysis import FaceTrack, VisualAnalysis


@dataclass
class SubjectWindow:
    """Which subject is active over a window of the timeline."""
    start: float
    end: float
    person_id: int
    confidence: float = 0.0
    # Normalised centre of the active subject during this window
    center_x: float = 0.5
    center_y: float = 0.42
    scale: float = 1.0
    talking: bool = True

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 2), "end": round(self.end, 2),
            "person": self.person_id, "confidence": round(self.confidence, 3),
            "cx": round(self.center_x, 4), "cy": round(self.center_y, 4),
            "scale": round(self.scale, 4), "talking": self.talking,
        }


@dataclass
class Person:
    """A cluster of face tracks believed to be the same person."""
    person_id: int
    label: str = ""
    face_tracks: list[int] = field(default_factory=list)
    center_x: float = 0.5
    center_y: float = 0.42
    mean_area: float = 0.0
    speaking_time: float = 0.0
    total_time: float = 0.0
    detected_faces: int = 0

    @property
    def share(self) -> float:
        return self.speaking_time / self.total_time if self.total_time else 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.person_id, "label": self.label,
            "cx": round(self.center_x, 4), "cy": round(self.center_y, 4),
            "area": round(self.mean_area, 4),
            "speaking_time": round(self.speaking_time, 2),
            "total_time": round(self.total_time, 2),
            "share": round(self.share, 3),
        }


@dataclass
class SpeakerTrack:
    persons: list[Person] = field(default_factory=list)
    windows: list[SubjectWindow] = field(default_factory=list)
    primary_person: int = 0
    has_multiple_speakers: bool = False
    speaking_ratio: float = 0.0

    def person_at(self, t: float) -> Person | None:
        for w in self.windows:
            if w.start <= t < w.end:
                for p in self.persons:
                    if p.person_id == w.person_id:
                        return p
        return self.persons[0] if self.persons else None

    def window_at(self, t: float) -> SubjectWindow | None:
        for w in self.windows:
            if w.start <= t < w.end:
                return w
        return None

    def to_dict(self) -> dict:
        return {
            "persons": [p.to_dict() for p in self.persons],
            "windows": [w.to_dict() for w in self.windows],
            "primary": self.primary_person,
            "multi": self.has_multiple_speakers,
            "speaking_ratio": round(self.speaking_ratio, 3),
        }


def _cluster_persons(tracks: list[FaceTrack], gap_x: float = 0.20) -> list[list[int]]:
    """Group face tracks that likely belong to the same person (by x position)."""
    if not tracks:
        return []
    items = []
    for tr in tracks:
        if tr.faces:
            items.append((tr.mean_center[0], tr.mean_area, tr.track_id))
    items.sort()
    clusters: list[list[tuple[float, float, int]]] = [[items[0]]]
    for x, area, tid in items[1:]:
        prev_x = clusters[-1][-1][0]
        if abs(x - prev_x) <= gap_x:
            clusters[-1].append((x, area, tid))
        else:
            clusters.append([(x, area, tid)])
    return [[tid for _, _, tid in c] for c in clusters]


def _talking_mask(audio: AudioAnalysis, start: float, end: float) -> list[float]:
    """Per-frame speaking activity (0..1) in a time range."""
    i0 = max(0, int(start / HOP_SECONDS))
    i1 = min(len(audio.energy), int(end / HOP_SECONDS) + 1)
    if i1 <= i0:
        return []
    return audio.energy[i0:i1]


def analyze_speakers(
    visual: VisualAnalysis,
    audio: AudioAnalysis,
    window_seconds: float = 1.0,
    min_confidence: float = 0.15,
) -> SpeakerTrack:
    """Build the speaker/subject timeline from visual tracks + audio energy."""
    track = SpeakerTrack()

    if not visual.tracks:
        # No faces at all -- the whole timeline belongs to a single implicit subject.
        track.persons = [Person(person_id=0, label="Subject", center_x=0.5, center_y=0.42)]
        track.windows = [SubjectWindow(0.0, max(0.1, visual.duration), 0, 1.0, 0.5, 0.42, 1.0)]
        track.primary_person = 0
        return track

    clusters = _cluster_persons(visual.tracks)
    by_id = {t.track_id: t for t in visual.tracks}

    # Build persons
    for idx, tids in enumerate(clusters):
        faces_all = [f for tid in tids for f in by_id[tid].faces]
        if not faces_all:
            continue
        cx = sum(f.center[0] for f in faces_all) / len(faces_all)
        cy = sum(f.center[1] for f in faces_all) / len(faces_all)
        area = sum(f.area for f in faces_all) / len(faces_all)
        p = Person(
            person_id=idx,
            label=f"Speaker {idx + 1}",
            face_tracks=list(tids),
            center_x=cx,
            center_y=cy,
            mean_area=area,
            total_time=sum(by_id[tid].total_time for tid in tids),
            detected_faces=len(faces_all),
        )
        track.persons.append(p)

    if not track.persons:
        track.persons = [Person(person_id=0, label="Subject")]
        track.windows = [SubjectWindow(0.0, max(0.1, visual.duration), 0, 1.0)]
        return track

    # Sort persons left-to-right for stable labelling
    track.persons.sort(key=lambda p: p.center_x)
    for i, p in enumerate(track.persons):
        p.person_id = i

    # --- score each person across the timeline -------------------------------------
    duration = max(visual.duration, audio.duration, 0.1)
    n_windows = max(1, int(duration / window_seconds))
    win_scores: list[dict[int, float]] = []

    for wi in range(n_windows):
        ws = wi * window_seconds
        we = min(duration, ws + window_seconds)
        energy = _talking_mask(audio, ws, we)
        talking = (sum(energy) / len(energy)) if energy else 0.0

        scores: dict[int, float] = {}
        for p in track.persons:
            # Prominence: how large and how central is this person's face right now?
            prominence = 0.0
            hits = 0
            for tid in p.face_tracks:
                for f in by_id[tid].faces_between(ws, we):
                    # Prefer larger faces; the talking head tends to be bigger.
                    prominence += f.area
                    hits += 1
            if hits:
                prominence /= hits
                # Centrality bonus -- a solo speaker is usually centred.
                centrality = 1.0 - min(1.0, abs(p.center_x - 0.5) / 0.5)
                scores[p.person_id] = prominence * (0.65 + 0.35 * centrality)
            else:
                scores[p.person_id] = 0.0

        total = sum(scores.values())
        if total > 1e-6:
            for k in scores:
                scores[k] /= total
        win_scores.append(scores)

        # Attribute speaking time to the leading person
        if scores:
            lead = max(scores, key=lambda k: scores[k])
            if talking > 0.25:
                track.persons[lead].speaking_time += (we - ws)

    # --- produce subject windows ---------------------------------------------------
    current: SubjectWindow | None = None
    for wi, scores in enumerate(win_scores):
        ws = wi * window_seconds
        we = min(duration, ws + window_seconds)
        if not scores:
            continue
        best_id = max(scores, key=lambda k: scores[k])
        best_score = scores[best_id]
        if best_score < min_confidence:
            best_id = max(scores, key=lambda k: scores[k])
        energy = _talking_mask(audio, ws, we)
        talking = (sum(energy) / len(energy)) if energy else 0.0

        person = next((p for p in track.persons if p.person_id == best_id), None)
        cx = person.center_x if person else 0.5
        cy = person.center_y if person else 0.42

        if current is not None and current.person_id == best_id and abs(current.end - ws) < 0.01:
            current.end = we
            current.confidence = (current.confidence + best_score) / 2
            current.center_x = (current.center_x + cx) / 2
            current.center_y = (current.center_y + cy) / 2
        else:
            if current is not None:
                track.windows.append(current)
            current = SubjectWindow(
                start=ws, end=we, person_id=best_id,
                confidence=best_score, center_x=cx, center_y=cy,
                scale=person.mean_area if person else 0.0,
                talking=talking > 0.2,
            )
    if current is not None:
        track.windows.append(current)

    # Primary speaker = most speaking time
    if track.persons:
        primary = max(track.persons, key=lambda p: p.speaking_time)
        track.primary_person = primary.person_id
        track.has_multiple_speakers = len(track.persons) > 1
        total_speaking = sum(p.speaking_time for p in track.persons)
        if total_speaking > 0:
            track.speaking_ratio = primary.speaking_time / total_speaking
    return track


def subject_center_at(
    speaker: SpeakerTrack, visual: VisualAnalysis, t: float
) -> tuple[float, float, float]:
    """Return (center_x, center_y, scale) for the subject at time t.

    Uses the exact detected face when available (fresher than the windowed average),
    falling back to the speaker window's smoothed centre.
    """
    win = speaker.window_at(t)
    if win:
        face = visual.face_at(t)
        if face:
            return face.center[0], face.center[1], face.area
        return win.center_x, win.center_y, win.scale
    face = visual.face_at(t)
    if face:
        return face.center[0], face.center[1], face.area
    return 0.5, 0.42, 0.0

"""Dependency-free two-stage (ByteTrack-style) IoU tracker used as a safe fallback.

High-confidence detections are associated first; low-confidence detections are then
used to recover tracks that would otherwise disappear during brief occlusion.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .utils import iou

Box = list[float]  # x1, y1, x2, y2


@dataclass
class Track:
    track_id: int
    box: Box
    hits: int = 1
    misses: int = 0
    age: int = 0
    last_seen: int = 0
    history: list[Box] = field(default_factory=list)

    @property
    def centroid(self) -> tuple[float, float]:
        return ((self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2)


class ByteTrackLite:
    def __init__(self, high_threshold: float = 0.5, match_threshold: float = 0.25, max_misses: int = 20):
        self.high_threshold = high_threshold
        self.match_threshold = match_threshold
        self.max_misses = max_misses
        self.tracks: list[Track] = []
        self._next_id = 1
        self.frame = 0

    def _associate(
        self, candidates: list[int], detections: list[tuple[Box, float]]
    ) -> tuple[set[int], set[int]]:
        """Greedy IoU matching, highest overlap first. Updates matched tracks."""
        pairs: list[tuple[int, int, float]] = []
        for ti in candidates:
            track = self.tracks[ti]
            for di, (box, _score) in enumerate(detections):
                score = iou(track.box, box)
                if score >= self.match_threshold:
                    pairs.append((ti, di, score))
        pairs.sort(key=lambda item: item[2], reverse=True)
        used_tracks: set[int] = set()
        used_dets: set[int] = set()
        for ti, di, _ in pairs:
            if ti in used_tracks or di in used_dets:
                continue
            used_tracks.add(ti)
            used_dets.add(di)
            box, _ = detections[di]
            track = self.tracks[ti]
            track.box = list(box)
            track.hits += 1
            track.misses = 0
            track.last_seen = self.frame
            track.history.append(list(box))
        return used_tracks, used_dets

    def update(self, detections: list[tuple[Box, float]], recover_low: bool = True) -> list[Track]:
        """Accept [(bbox, confidence)] per frame; return stable tracks for this frame."""
        self.frame += 1
        high = [d for d in detections if d[1] >= self.high_threshold]
        low = [d for d in detections if d[1] < self.high_threshold]

        all_indices = list(range(len(self.tracks)))
        used_tracks, used_dets = self._associate(all_indices, high)

        # New identities start only from confident detections.
        for det_index, (box, _score) in enumerate(high):
            if det_index not in used_dets:
                track = Track(self._next_id, list(box), last_seen=self.frame)
                track.history.append(list(box))
                self._next_id += 1
                self.tracks.append(track)

        # Second stage: recover tracks missed in stage one using low-confidence detections.
        if recover_low and low:
            unmatched = [i for i in range(len(self.tracks)) if self.tracks[i].last_seen != self.frame]
            self._associate(unmatched, low)

        alive: list[Track] = []
        for track in self.tracks:
            track.age += 1
            if track.last_seen == self.frame:
                alive.append(track)
            elif track.misses < self.max_misses:
                track.misses += 1
                alive.append(track)
        self.tracks = alive
        return [t for t in alive if t.last_seen == self.frame and t.hits >= 2]

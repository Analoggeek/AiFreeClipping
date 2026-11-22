"""Editable timeline model for the preview editor.

A :class:`Timeline` holds the ordered list of segments that make up a clip, plus
the edit operations that change them (trim, split, merge, reorder, speed, crop,
zoom).  Every mutation goes through :meth:`Timeline.apply`, which records an undo
entry so the editor can support undo/redo.

The model is deliberately free of any Qt dependency so it can be unit tested and
reused by the headless one-click pipeline.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable


@dataclass
class Segment:
    """One continuous piece of source footage inside the timeline."""

    id: str
    start: float          # seconds into the source video
    end: float            # seconds into the source video
    speed: float = 1.0    # playback rate multiplier
    zoom: float = 1.0     # extra zoom applied on top of the reframer
    crop_x: float = 0.5   # crop centre as a fraction of the frame (0..1)
    crop_y: float = 0.5
    muted: bool = False

    @property
    def source_duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def duration(self) -> float:
        """Length of this segment on the output timeline."""
        return self.source_duration / max(0.05, self.speed)

    @property
    def mid(self) -> float:
        return (self.start + self.end) / 2.0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "start": round(self.start, 3), "end": round(self.end, 3),
            "speed": round(self.speed, 4), "zoom": round(self.zoom, 4),
            "crop_x": round(self.crop_x, 4), "crop_y": round(self.crop_y, 4),
            "muted": self.muted,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Segment":
        return cls(
            id=data["id"], start=float(data["start"]), end=float(data["end"]),
            speed=float(data.get("speed", 1.0)), zoom=float(data.get("zoom", 1.0)),
            crop_x=float(data.get("crop_x", 0.5)), crop_y=float(data.get("crop_y", 0.5)),
            muted=bool(data.get("muted", False)),
        )


@dataclass
class EditOperation:
    """One reversible edit."""

    kind: str
    label: str
    before: list[dict]
    after: list[dict]


@dataclass
class Timeline:
    """An ordered list of segments plus the undo/redo history."""

    segments: list[Segment] = field(default_factory=list)
    source_duration: float = 0.0
    _undo: list[EditOperation] = field(default_factory=list)
    _redo: list[EditOperation] = field(default_factory=list)
    _counter: int = 0

    # -- construction ----------------------------------------------------------
    @classmethod
    def from_clip(cls, start: float, end: float, source_duration: float = 0.0) -> "Timeline":
        tl = cls(source_duration=source_duration or end)
        tl.segments = [Segment(id=tl._new_id(), start=start, end=end)]
        return tl

    @classmethod
    def load(cls, path: str | Path) -> "Timeline":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        tl = cls(source_duration=float(data.get("source_duration", 0.0)))
        tl.segments = [Segment.from_dict(s) for s in data.get("segments", [])]
        tl._counter = len(tl.segments)
        return tl

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "source_duration": self.source_duration,
            "segments": [s.to_dict() for s in self.segments],
        }, indent=2), encoding="utf-8")
        return path

    def _new_id(self) -> str:
        self._counter += 1
        return f"seg{self._counter:04d}"

    # -- state -----------------------------------------------------------------
    @property
    def duration(self) -> float:
        return sum(s.duration for s in self.segments)

    @property
    def is_empty(self) -> bool:
        return not self.segments

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def segment_at(self, timeline_time: float) -> Segment | None:
        """Return the segment playing at ``timeline_time`` on the output."""
        acc = 0.0
        for seg in self.segments:
            if timeline_time < acc + seg.duration:
                return seg
            acc += seg.duration
        return self.segments[-1] if self.segments else None

    def source_time_at(self, timeline_time: float) -> float:
        """Map an output-timeline position back to a source-video position."""
        acc = 0.0
        for seg in self.segments:
            if timeline_time < acc + seg.duration:
                return seg.start + (timeline_time - acc) * seg.speed
            acc += seg.duration
        return self.segments[-1].end if self.segments else 0.0

    def output_time_at(self, source_time: float) -> float:
        """Map a source-video position onto the output timeline."""
        acc = 0.0
        for seg in self.segments:
            if seg.start <= source_time <= seg.end:
                return acc + (source_time - seg.start) / max(0.05, seg.speed)
            acc += seg.duration
        return acc

    # -- editing ---------------------------------------------------------------
    def apply(self, kind: str, label: str, new_segments: list[Segment]) -> None:
        """Commit a new segment list, recording an undo entry."""
        before = [s.to_dict() for s in self.segments]
        after = [s.to_dict() for s in new_segments]
        self.segments = new_segments
        self._undo.append(EditOperation(kind=kind, label=label, before=before, after=after))
        self._redo.clear()

    def _snapshot(self) -> list[Segment]:
        return [replace(s) for s in self.segments]

    def split_at(self, source_time: float) -> bool:
        """Split the segment containing ``source_time`` into two."""
        for i, seg in enumerate(self.segments):
            if seg.start < source_time < seg.end:
                left = replace(seg, end=source_time)
                right = replace(seg, id=self._new_id(), start=source_time)
                new = self._snapshot()
                new[i:i + 1] = [left, right]
                self.apply("split", f"Split at {source_time:.2f}s", new)
                return True
        return False

    def trim(self, segment_id: str, new_start: float | None = None,
             new_end: float | None = None) -> bool:
        """Trim one segment's in/out points."""
        for i, seg in enumerate(self.segments):
            if seg.id != segment_id:
                continue
            start = seg.start if new_start is None else max(seg.start, new_start)
            end = seg.end if new_end is None else min(seg.end, new_end)
            if end - start < 0.05:
                return False
            new = self._snapshot()
            new[i] = replace(seg, start=start, end=end)
            self.apply("trim", f"Trim {segment_id}", new)
            return True
        return False

    def delete_segment(self, segment_id: str) -> bool:
        new = [s for s in self._snapshot() if s.id != segment_id]
        if len(new) == len(self.segments):
            return False
        self.apply("delete", f"Delete {segment_id}", new)
        return True

    def merge_with_next(self, index: int) -> bool:
        """Merge the segment at ``index`` with the one after it."""
        if index < 0 or index + 1 >= len(self.segments):
            return False
        a, b = self.segments[index], self.segments[index + 1]
        # Merging only makes sense for contiguous source ranges.
        if abs(a.end - b.start) > 0.05:
            return False
        merged = replace(a, end=max(a.end, b.end))
        new = self._snapshot()
        new[index:index + 2] = [merged]
        self.apply("merge", "Merge segments", new)
        return True

    def move_segment(self, index: int, delta: int) -> bool:
        """Move a segment up (-1) or down (+1) in the order."""
        target = index + delta
        if index < 0 or index >= len(self.segments) or target < 0 or target >= len(self.segments):
            return False
        new = self._snapshot()
        new[index], new[target] = new[target], new[index]
        self.apply("reorder", "Reorder segments", new)
        return True

    def set_speed(self, segment_id: str, speed: float) -> bool:
        speed = max(0.25, min(4.0, float(speed)))
        for i, seg in enumerate(self.segments):
            if seg.id == segment_id:
                new = self._snapshot()
                new[i] = replace(seg, speed=speed)
                self.apply("speed", f"Speed {speed:.2f}x", new)
                return True
        return False

    def set_zoom(self, segment_id: str, zoom: float) -> bool:
        zoom = max(1.0, min(3.0, float(zoom)))
        for i, seg in enumerate(self.segments):
            if seg.id == segment_id:
                new = self._snapshot()
                new[i] = replace(seg, zoom=zoom)
                self.apply("zoom", f"Zoom {zoom:.2f}x", new)
                return True
        return False

    def set_crop(self, segment_id: str, crop_x: float, crop_y: float) -> bool:
        for i, seg in enumerate(self.segments):
            if seg.id == segment_id:
                new = self._snapshot()
                new[i] = replace(seg,
                                 crop_x=max(0.0, min(1.0, crop_x)),
                                 crop_y=max(0.0, min(1.0, crop_y)))
                self.apply("crop", "Crop", new)
                return True
        return False

    def set_muted(self, segment_id: str, muted: bool) -> bool:
        for i, seg in enumerate(self.segments):
            if seg.id == segment_id:
                new = self._snapshot()
                new[i] = replace(seg, muted=muted)
                self.apply("mute", "Mute" if muted else "Unmute", new)
                return True
        return False

    def set_all_speed(self, speed: float) -> None:
        speed = max(0.25, min(4.0, float(speed)))
        new = [replace(s, speed=speed) for s in self._snapshot()]
        self.apply("speed", f"Speed {speed:.2f}x", new)

    # -- history ---------------------------------------------------------------
    def undo(self) -> str | None:
        if not self._undo:
            return None
        op = self._undo.pop()
        self.segments = [Segment.from_dict(d) for d in op.before]
        self._redo.append(op)
        return op.label

    def redo(self) -> str | None:
        if not self._redo:
            return None
        op = self._redo.pop()
        self.segments = [Segment.from_dict(d) for d in op.after]
        self._undo.append(op)
        return op.label

    def history_labels(self) -> list[str]:
        return [op.label for op in self._undo]


def build_from_ranges(ranges: Iterable[tuple[float, float]]) -> Timeline:
    """Build a timeline from a list of (start, end) source ranges."""
    tl = Timeline()
    tl.segments = [Segment(id=tl._new_id(), start=s, end=e) for s, e in ranges]
    return tl

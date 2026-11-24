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
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable


HISTORY_LIMIT = 50


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
    recovered_from: str | None = None

    # -- construction ----------------------------------------------------------
    @classmethod
    def from_clip(cls, start: float, end: float, source_duration: float = 0.0) -> "Timeline":
        tl = cls(source_duration=source_duration or end)
        tl.segments = [Segment(id=tl._new_id(), start=start, end=end)]
        return tl

    @staticmethod
    def backup_path(path: str | Path) -> Path:
        return Path(str(path) + ".bak")

    @classmethod
    def _read(cls, path: Path) -> "Timeline":
        # Bound allocation and refuse malformed data before it reaches FFmpeg.
        with path.open("rb") as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError("Timeline exceeds 8 MiB")
        return cls._from_data(json.loads(raw))

    @classmethod
    def _from_data(cls, data: dict, *, read_history: bool = True) -> "Timeline":
        if not isinstance(data, dict):
            raise ValueError("Timeline must be an object")
        if type(data.get("version", 1)) is not int or data.get("version", 1) != 1:
            raise ValueError("Unsupported timeline version")

        def number(value, name, lo, hi):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Invalid {name}")
            if not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError(f"Invalid {name}")
            return float(value)

        duration = number(data.get("source_duration", 0.), "source duration", 0, 1e9)
        items = data.get("segments")
        if not isinstance(items, list) or len(items) > 10000:
            raise ValueError("Invalid timeline segments")
        tl = cls(source_duration=duration)
        ids = set()
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Invalid segment")
            sid = item.get("id")
            if not isinstance(sid, str) or not sid or len(sid) > 128 or sid in ids:
                raise ValueError("Invalid or duplicate segment ID")
            ids.add(sid)
            start = number(item.get("start"), "start", 0, duration or 1e9)
            end = number(item.get("end"), "end", 0, duration or 1e9)
            if end <= start:
                raise ValueError("Segment must have positive duration")
            if type(item.get("muted", False)) is not bool:
                raise ValueError("Invalid mute flag")
            tl.segments.append(Segment(
                id=sid, start=start, end=end,
                speed=number(item.get("speed", 1.), "speed", .05, 16),
                zoom=number(item.get("zoom", 1.), "zoom", 1, 3),
                crop_x=number(item.get("crop_x", .5), "crop x", 0, 1),
                crop_y=number(item.get("crop_y", .5), "crop y", 0, 1),
                muted=item.get("muted", False),
            ))
        tl._counter = max([int(sid[3:]) for sid in ids
                           if sid.startswith("seg") and sid[3:].isascii()
                           and sid[3:].isdigit()] + [0])
        if read_history:
            history = data.get("history", {})
            if not isinstance(history, dict):
                raise ValueError("Invalid timeline history")
            stacks = [history.get("undo", []), history.get("redo", [])]
            if any(not isinstance(stack, list) for stack in stacks):
                raise ValueError("Invalid timeline history stacks")
            if sum(map(len, stacks)) > HISTORY_LIMIT:
                raise ValueError("Timeline history limit exceeded")
            parsed = []
            for stack in stacks:
                operations = []
                for op in stack:
                    if not isinstance(op, dict):
                        raise ValueError("Invalid edit operation")
                    kind, label = op.get("kind"), op.get("label")
                    if not isinstance(kind, str) or not 1 <= len(kind) <= 64:
                        raise ValueError("Invalid edit kind")
                    if not isinstance(label, str) or not 1 <= len(label) <= 256:
                        raise ValueError("Invalid edit label")
                    snapshots = []
                    for key in ("before", "after"):
                        snapshot = cls._from_data({"source_duration": duration,
                            "segments": op.get(key)}, read_history=False)
                        tl._counter = max(tl._counter, snapshot._counter)
                        snapshots.append([s.to_dict() for s in snapshot.segments])
                    operations.append(EditOperation(kind, label, *snapshots))
                parsed.append(operations)
            tl._undo, tl._redo = parsed
            # Undo stack is oldest->newest, redo is popped from its end. Each
            # recorded step must connect to the current saved state exactly.
            state = [s.to_dict() for s in tl.segments]
            for op in reversed(tl._undo):
                if op.after != state:
                    raise ValueError("Disconnected undo history")
                state = op.before
            state = [s.to_dict() for s in tl.segments]
            for op in reversed(tl._redo):
                if op.before != state:
                    raise ValueError("Disconnected redo history")
                state = op.after
        return tl

    def _save_data(self) -> dict:
        return {"version": 1, "source_duration": self.source_duration,
                "segments": [s.to_dict() for s in self.segments],
                "history": {"undo": [asdict(op) for op in self._undo],
                            "redo": [asdict(op) for op in self._redo]}}

    @classmethod
    def load(cls, path: str | Path) -> "Timeline":
        path = Path(path)
        try:
            return cls._read(path)
        except (ValueError, OSError) as primary_error:
            try:
                tl = cls._read(cls.backup_path(path))
            except (ValueError, OSError):
                raise ValueError(f"Cannot restore timeline {path.name}: {primary_error}") from primary_error
            tl.recovered_from = str(cls.backup_path(path))
            return tl

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        # Same-directory replace is atomic on supported local filesystems. A
        # failed write/replace leaves the previous file intact, not truncated.
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            if os.name != "nt":
                try:
                    directory = os.open(path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                except OSError:
                    pass  # Some filesystems do not support directory fsync.
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        self._from_data({"source_duration": self.source_duration,
                         "segments": [asdict(s) for s in self.segments]})
        data = self._save_data()
        self._from_data(data)  # Do not overwrite valid edits with invalid state.
        payload = json.dumps(data, indent=2, allow_nan=False).encode("utf-8")
        if len(payload) > 8 * 1024 * 1024:
            raise ValueError("Timeline exceeds 8 MiB")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            try:
                previous = self._read(path)
            except (ValueError, OSError):
                previous = None  # Never rotate corrupt data over a valid backup.
            if previous is not None:
                backup = json.dumps(previous._save_data(), allow_nan=False).encode("utf-8")
                self._atomic_write(self.backup_path(path), backup)
        self._atomic_write(path, payload)
        self.recovered_from = None
        return path

    def _new_id(self) -> str:
        occupied = {s.id for s in self.segments}
        while True:
            self._counter += 1
            candidate = f"seg{self._counter:04d}"
            if candidate not in occupied:
                return candidate

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
        del self._undo[:-HISTORY_LIMIT]
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

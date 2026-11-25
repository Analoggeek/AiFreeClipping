"""Versioned, selective and atomic editing configuration for the native studio.

Only parameters executed by the retained preview/export engines are accepted.
Timing-dependent fades are fractions of each target's output duration. Source
trims, media files, caption text/timing and unchecked categories are never copied.
"""

from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
from pathlib import Path

from .overlay_tracks import validate_caption_options

FIELDS = {
    "color": {"brightness", "contrast", "saturation"},
    "transform": {"x", "y", "w", "h", "opacity", "rotation"},
    "audio": {"gain", "fade_in_fraction", "fade_out_fraction"},
    "captions": {"caption_style", "caption_options"},
}
DEFAULTS = {
    "color": {"brightness": 0.0, "contrast": 1.0, "saturation": 1.0},
    "transform": {
        "x": 0.0,
        "y": 0.0,
        "w": 1.0,
        "h": 1.0,
        "opacity": 1.0,
        "rotation": 0.0,
    },
    "audio": {"gain": 1.0, "fade_in_fraction": 0.0, "fade_out_fraction": 0.0},
    "captions": {"caption_style": "bold_viral", "caption_options": {}},
}


@dataclass
class EditingPreset:
    name: str = "Studio style"
    categories: dict = field(default_factory=dict)

    def validate(self):
        if not isinstance(self.name, str) or not 1 <= len(self.name.strip()) <= 100:
            raise ValueError("Preset name must contain 1–100 characters")
        if (
            not isinstance(self.categories, dict)
            or not self.categories
            or not self.categories.keys() <= FIELDS.keys()
        ):
            raise ValueError("Choose supported editing categories")
        from ..captions.caption_engine import CAPTION_STYLES

        limits = {
            "brightness": (-1, 1),
            "contrast": (0, 3),
            "saturation": (0, 3),
            "x": (0, 1),
            "y": (0, 1),
            "w": (0.01, 1),
            "h": (0.01, 1),
            "opacity": (0, 1),
            "rotation": (-180, 180),
            "gain": (0, 4),
            "fade_in_fraction": (0, 1),
            "fade_out_fraction": (0, 1),
        }
        for category, values in self.categories.items():
            if not isinstance(values, dict) or set(values) != FIELDS[category]:
                raise ValueError("Incomplete or unsupported parameters: " + category)
            for key, value in values.items():
                if key in limits:
                    lo, hi = limits[key]
                    if (
                        type(value) not in (int, float)
                        or not math.isfinite(value)
                        or not lo <= value <= hi
                    ):
                        raise ValueError("Invalid preset parameter: " + key)
            if category == "transform" and (
                values["x"] + values["w"] > 1.000001
                or values["y"] + values["h"] > 1.000001
            ):
                raise ValueError("Transform exceeds canvas")
            if (
                category == "audio"
                and values["fade_in_fraction"] + values["fade_out_fraction"] > 1
            ):
                raise ValueError("Audio fades overlap")
            if category == "captions":
                if values["caption_style"] not in CAPTION_STYLES:
                    raise ValueError("Unknown caption style")
                validate_caption_options(values["caption_options"])
        return self

    def to_dict(self):
        self.validate()
        return {
            "schema": "clipos.editing-preset.v1",
            "name": self.name,
            "categories": deepcopy(self.categories),
        }

    @classmethod
    def from_dict(cls, data):
        if (
            not isinstance(data, dict)
            or set(data) != {"schema", "name", "categories"}
            or data["schema"] != "clipos.editing-preset.v1"
        ):
            raise ValueError("Unsupported editing preset")
        return cls(data["name"], deepcopy(data["categories"])).validate()

    def save(self, path):
        if Path(path).suffix.lower() != ".json":
            raise ValueError("Editing presets require a .json path")
        from .timeline import Timeline

        Timeline._atomic_write(
            Path(path), json.dumps(self.to_dict(), allow_nan=False, indent=2).encode()
        )

    @classmethod
    def load(cls, path):
        with Path(path).open("rb") as stream:
            raw = stream.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            raise ValueError("Preset exceeds 256 KiB")
        return cls.from_dict(json.loads(raw))


def apply_editing_preset(project, preset, media_ids):
    """One undoable transaction across all targeted media and contained captions.

    Captions qualify only when wholly inside a targeted video's time span. An
    unrelated/straddling overlay is not modified. Locked affected tracks reject
    the entire transaction; zero compatible targets is an error, not success.
    Existing gain automation is preserved and multiplies the new static gain.
    """
    preset.validate()
    selected = set(media_ids)
    known = {media.id for media in project.media}
    if not selected or not selected <= known:
        raise ValueError("Select existing timeline media")
    windows = [
        (item.at, item.at + item.duration)
        for lane in project.lanes
        if lane.kind == "video"
        for item in lane.items
        if item.media_id in selected
    ]
    count = [0]

    def operation(draft):
        for lane in draft.lanes:
            for item in lane.items:
                updates = {}
                for category, values in preset.categories.items():
                    if category == "captions":
                        if lane.kind == "caption" and any(
                            start <= item.at + 1e-6
                            and item.at + item.duration <= end + 1e-6
                            for start, end in windows
                        ):
                            updates.update(deepcopy(values))
                    elif item.media_id in selected:
                        if category in ("color", "transform") and lane.kind == "video":
                            updates.update(values)
                        elif category == "audio" and lane.kind == "audio":
                            updates.update(
                                gain=values["gain"],
                                fade_in=values["fade_in_fraction"] * item.duration,
                                fade_out=values["fade_out_fraction"] * item.duration,
                            )
                if updates:
                    if lane.locked:
                        raise ValueError("Affected track is locked: " + lane.name)
                    for key, value in updates.items():
                        setattr(item, key, deepcopy(value))
                    count[0] += 1
        if not count[0]:
            raise ValueError("No compatible timeline items for selected categories")

    project.edit(operation)
    return count[0]

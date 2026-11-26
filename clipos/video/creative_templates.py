"""Fifty asset-free original editing recipe templates using implemented settings.

These are color/audio/caption compositions, not motion-graphics asset packs.
They never replace dialogue, source crop, media references or timeline structure.
"""

from copy import deepcopy
from .editing_preset import EditingPreset, DEFAULTS
from ..captions.original_styles import FAMILIES, TREATMENTS


def templates():
    result = {}
    for family_index, (family, name, *_) in enumerate(FAMILIES):
        for variant, (treatment, title, *_) in enumerate(TREATMENTS):
            categories = deepcopy(DEFAULTS)
            categories.pop(
                "audio_routing", None
            )  # Never relabel background music as dialogue through a visual recipe.
            # Restrained, deterministic looks; retain canvas-filling geometry.
            categories["color"].update(
                brightness=[0.0, 0.015, 0.025, -0.01, 0.005][variant],
                contrast=[1.0, 1.04, 1.08, 1.02, 1.06][variant],
                saturation=[1.0, 0.96, 1.06, 0.9, 1.02][variant],
            )
            categories["audio"].update(
                gain=[1.0, 0.95, 1.0, 0.9, 0.98][variant],
                fade_in_fraction=[0.0, 0.02, 0.01, 0.03, 0.02][variant],
                fade_out_fraction=[0.0, 0.03, 0.02, 0.04, 0.02][variant],
            )
            categories["captions"]["caption_style"] = f"original_{family}_{treatment}"
            key = f"{family}_{treatment}"
            result[key] = {
                "key": key,
                "category": family,
                "name": f"{name} / {title}",
                "description": "Original offline color, dialogue-audio and caption-style recipe. No media assets or transitions are inserted.",
                "aspect_ratio": "Keeps current canvas",
                "duration": "Adapts fades to target clip duration",
                "required_assets": [],
                "preset": EditingPreset(f"{name} / {title}", categories).to_dict(),
            }
    return result

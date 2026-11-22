"""Original, deterministic offline edit recipes (not trained model weights)."""
PRESETS = {
    "clean": ("Clean Studio", "Restrained colour, readable captions, original framing"),
    "podcast": ("Podcast Focus", "Active-speaker framing and clean lower-third captions"),
    "gaming": ("Gameplay + Facecam", "Gameplay above; selected facecam region below. No middle cutout."),
    "story": ("Story Highlight", "High-contrast captions and a concise opening hook"),
}


def apply_preset(settings, key):
    settings.editing_preset = key if key in PRESETS else "clean"
    settings.sound_effects = False  # Avoid an unrelated whoosh on every short.
    settings.caption_style = {"podcast": "modern_podcast", "gaming": "neon_gaming",
                              "story": "bold_viral"}.get(key, "minimal_white")
    settings.smart_reframe = key == "podcast"
    settings.auto_zoom = False
    settings.contrast = 1.03 if key == "story" else 1.0
    settings.saturation = 1.04 if key == "gaming" else 1.0
    return settings


def gaming_filter(width, height, source_w, source_h, facecam):
    """Facecam is a normalised source rectangle, manually adjustable by user."""
    x, y, w, h = facecam
    if not (0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0 and x+w <= 1.001 and y+h <= 1.001):
        raise ValueError("Facecam rectangle must fit inside the source")
    bottom = (height // 3) // 2 * 2
    top = height - bottom
    cw, ch = max(2, int(w*source_w)//2*2), max(2, int(h*source_h)//2*2)
    cx, cy = int(x*source_w)//2*2, int(y*source_h)//2*2
    # Fit gameplay rather than arbitrarily cutting the middle of the recording.
    return (f"split=2[game][cam];[game]scale={width}:{top}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{top}:(ow-iw)/2:(oh-ih)/2,setsar=1[upper];"
            f"[cam]crop={cw}:{ch}:{cx}:{cy},scale={width}:{bottom}:force_original_aspect_ratio=increase,"
            f"crop={width}:{bottom},setsar=1[lower];[upper][lower]vstack=inputs=2")

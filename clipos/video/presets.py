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
    settings.caption_style = {"podcast": "modern_podcast", "gaming": "clean_professional",
                              "story": "bold_viral"}.get(key, "minimal_white")
    settings.smart_reframe = key == "podcast"
    settings.auto_zoom = False
    settings.contrast = 1.03 if key == "story" else 1.0
    settings.saturation = 1.04 if key == "gaming" else 1.0
    return settings


def _crop(rect, source_w, source_h):
    x,y,w,h = rect
    if not (0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0 and x+w <= 1.001 and y+h <= 1.001):
        raise ValueError("Crop rectangle must fit inside the source")
    cw = min(source_w, max(2, int(w*source_w)//2*2))
    ch = min(source_h, max(2, int(h*source_h)//2*2))
    cx = min(source_w-cw, int(x*source_w)//2*2)
    cy = min(source_h-ch, int(y*source_h)//2*2)
    return f"crop={cw}:{ch}:{cx}:{cy}"


def gaming_filter(width, height, source_w, source_h, facecam, gameplay=(0.,0.,1.,1.)):
    """Fill the top gameplay panel; crop the actual facecam into the bottom."""
    if facecam is None:
        return (f"{_crop(gameplay, source_w, source_h)},scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1")
    bottom = (height // 3) // 2 * 2
    top = height - bottom
    game = _crop(gameplay, source_w, source_h)
    cam = _crop(facecam, source_w, source_h)
    return (f"split=2[game][cam];[game]{game},scale={width}:{top}:force_original_aspect_ratio=increase,"
            f"crop={width}:{top},setsar=1[upper];"
            f"[cam]{cam},scale={width}:{bottom}:force_original_aspect_ratio=increase,"
            f"crop={width}:{bottom},setsar=1[lower];[upper][lower]vstack=inputs=2")


def gameplay_outside(facecam):
    x,y,w,h = facecam
    regions=[(0.,0.,x,1.),(x+w,0.,1-x-w,1.),(0.,0.,1.,y),(0.,y+h,1.,1-y-h)]
    regions=[r for r in regions if r[2]>.05 and r[3]>.05]
    if not regions: raise ValueError("Player region leaves no gameplay. Select a smaller camera region.")
    return max(regions,key=lambda r:r[2]*r[3])

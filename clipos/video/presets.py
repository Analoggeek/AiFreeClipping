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


def gaming_filter(width, height, source_w, source_h, facecam, gameplay=(0.,0.,1.,1.), layout="bottom", camera_size=1/3):
    """Fill the top gameplay panel; crop the actual facecam into the bottom."""
    from .layouts import CATALOG, render_graph
    import math
    if layout not in {item[0] for item in CATALOG}:
        raise ValueError("Choose a valid studio layout")
    if not math.isfinite(camera_size) or not .2 <= camera_size <= .5:
        raise ValueError("Camera size must be between 20% and 50%")
    if layout != "bottom" or camera_size != 1/3:
        # No invented camera region: missing detection falls back to gameplay.
        effective = layout
        if facecam is None and layout not in ("blur", "fill", "game"):
            effective = "game"
        rects=[]
        for rect in (facecam or (0.,0.,1.,1.), gameplay):
            crop = _crop(rect,source_w,source_h).split("=",1)[1]
            w,h,x,y = map(int,crop.split(":"))
            rects.append((x,y,w,h))
        graph=render_graph(effective,rects,camera_size,width,height)
        # Renderer supplies its own input label and appends more filters.
        return graph.replace("[0:v]", "", 1).removesuffix("[base]")
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


# Adapted source-placement presets from DigiRG Cloud app.js (MIT), revision
# 0987925fa4e99c5d90c68239dc8071421c56d121. See THIRD_PARTY_NOTICES.md.
# These are editable starting regions, never a claim that a camera was detected.
CAMERA_SOURCE_PRESETS = {
    'tl': ((0.,0.,.24,.32),(.24,0.,.76,1.)),
    'tr': ((.76,0.,.24,.32),(0.,0.,.76,1.)),
    'bl': ((0.,.68,.24,.32),(.24,0.,.76,1.)),
    'br': ((.76,.68,.24,.32),(0.,0.,.76,1.)),
    'bc': ((.37,.68,.26,.32),(0.,0.,1.,.68)),
}

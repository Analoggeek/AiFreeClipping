"""Bounded, executable local FFmpeg effects, with original recipe combinations.

No arbitrary filter strings, scripts, URLs, models or external assets accepted.
"""

import math

EFFECTS = {
    "blur": ("Gaussian softness", 0.0, 20.0, 2.0),
    "sharpen": ("Detail contrast", 0.0, 2.0, 0.5),
    "vignette": ("Edge focus", 0.0, 1.0, 0.5),
    "grain": ("Seeded film texture", 0.0, 50.0, 10.0),
    "monochrome": ("Silver desaturation", 0.0, 1.0, 1.0),
    "hue": ("Hue orbit", -180.0, 180.0, 20.0),
    "rgb_swap": ("Red / blue separation", 0.0, 1.0, 0.5),
    "invert": ("Negative exposure", 0.0, 1.0, 1.0),
}


def validate_effects(effects):
    if not isinstance(effects, list) or len(effects) > 8:
        raise ValueError("At most eight video effects per layer")
    for effect in effects:
        if (
            not isinstance(effect, dict)
            or set(effect) != {"kind", "amount"}
            or not isinstance(effect["kind"], str)
            or effect["kind"] not in EFFECTS
        ):
            raise ValueError("Unsupported video effect")
        _, lo, hi, _ = EFFECTS[effect["kind"]]
        amount = effect["amount"]
        if (
            type(amount) not in (int, float)
            or not math.isfinite(amount)
            or not lo <= amount <= hi
        ):
            raise ValueError("Video effect amount out of range")
    return effects


def effect_filters(effects):
    validate_effects(effects)
    filters = []
    for effect in effects:
        kind = effect["kind"]
        a = effect["amount"]
        if kind == "blur" and a:
            filters.append(f"gblur=sigma={a:.6f}")
        elif kind == "sharpen" and a:
            filters.append(f"unsharp=5:5:{a:.6f}:5:5:0")
        elif kind == "vignette" and a:
            filters.append(f"vignette=angle={a * 0.7853981634:.8f}")
        elif kind == "grain" and a:
            filters.append(f"noise=alls={round(a)}:allf=t+u:all_seed=37")
        elif kind == "monochrome":
            filters.append(f"hue=s={1 - a:.6f}")
        elif kind == "hue":
            filters.append(f"hue=h={a:.6f}")
        elif kind == "rgb_swap":
            filters.append(
                f"colorchannelmixer=rr={1 - a:.6f}:rb={a:.6f}:br={a:.6f}:bb={1 - a:.6f}"
            )
        elif kind == "invert" and a:
            filters.append(f"negate=enable=1") if a == 1 else filters.append(
                f"lutrgb=r=val*{1 - 2 * a:.6f}+{255 * a:.6f}:g=val*{1 - 2 * a:.6f}+{255 * a:.6f}:b=val*{1 - 2 * a:.6f}+{255 * a:.6f}"
            )
    return filters


def effect_recipes():
    """Twenty original combinations of eight implemented filter primitives."""
    return {
        "Clean detail": [{"kind": "sharpen", "amount": 0.35}],
        "Soft interview": [
            {"kind": "blur", "amount": 0.35},
            {"kind": "vignette", "amount": 0.2},
        ],
        "Silver journal": [
            {"kind": "monochrome", "amount": 1.0},
            {"kind": "grain", "amount": 8.0},
        ],
        "Night edge": [
            {"kind": "vignette", "amount": 0.8},
            {"kind": "sharpen", "amount": 0.4},
        ],
        "Coral orbit": [{"kind": "hue", "amount": 12.0}],
        "Blue orbit": [{"kind": "hue", "amount": -18.0}],
        "Grain diary": [
            {"kind": "grain", "amount": 15.0},
            {"kind": "vignette", "amount": 0.3},
        ],
        "Soft paper": [
            {"kind": "monochrome", "amount": 0.4},
            {"kind": "blur", "amount": 0.4},
        ],
        "Split spectrum": [{"kind": "rgb_swap", "amount": 0.65}],
        "Negative study": [{"kind": "invert", "amount": 1.0}],
        "Muted texture": [
            {"kind": "monochrome", "amount": 0.6},
            {"kind": "grain", "amount": 5.0},
        ],
        "Crisp frame": [
            {"kind": "sharpen", "amount": 0.7},
            {"kind": "vignette", "amount": 0.35},
        ],
        "Soft border": [
            {"kind": "blur", "amount": 0.7},
            {"kind": "vignette", "amount": 0.65},
        ],
        "Analog edge": [
            {"kind": "grain", "amount": 22.0},
            {"kind": "sharpen", "amount": 0.3},
        ],
        "Chrome tint": [
            {"kind": "rgb_swap", "amount": 0.3},
            {"kind": "hue", "amount": 8.0},
        ],
        "Quiet grayscale": [
            {"kind": "monochrome", "amount": 1.0},
            {"kind": "vignette", "amount": 0.2},
        ],
        "Pastel separation": [
            {"kind": "rgb_swap", "amount": 0.2},
            {"kind": "blur", "amount": 0.25},
        ],
        "Violet signal": [
            {"kind": "hue", "amount": 35.0},
            {"kind": "sharpen", "amount": 0.2},
        ],
        "Retro field": [
            {"kind": "grain", "amount": 12.0},
            {"kind": "hue", "amount": -8.0},
        ],
        "Dream journal": [
            {"kind": "blur", "amount": 1.2},
            {"kind": "monochrome", "amount": 0.25},
        ],
    }

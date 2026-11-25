"""Forty original transition recipes: ten alpha-mask families × four curves.

Incoming video composites over a genuinely overlapping outgoing video. These are
40 parameterized compositions, not 40 unrelated transition algorithms.
"""

FAMILIES = {
    "dissolve": "Cross dissolve",
    "left": "Left reveal",
    "right": "Right reveal",
    "up": "Up reveal",
    "down": "Down reveal",
    "circle": "Iris reveal",
    "diamond": "Diamond reveal",
    "horizontal": "Horizontal aperture",
    "vertical": "Vertical aperture",
    "diagonal": "Diagonal reveal",
}
CURVES = {"linear": "Linear", "smooth": "Smooth", "in": "Ease in", "out": "Ease out"}


def transition_recipes():
    return {
        f"{family}_{curve}": f"{name} · {curve_name}"
        for family, name in FAMILIES.items()
        for curve, curve_name in CURVES.items()
    }


def alpha_filter(mode, duration):
    if mode not in transition_recipes():
        raise ValueError("Unsupported transition recipe")
    family, curve = mode.rsplit("_", 1)
    p = f"clip(T/{duration:.8f},0,1)"
    if curve == "smooth":
        p = f"(({p})*({p})*(3-2*({p})))"
    elif curve == "in":
        p = f"pow({p},2)"
    elif curve == "out":
        p = f"(1-pow(1-({p}),2))"
    masks = {
        "dissolve": p,
        "left": f"lte(X/W,{p})",
        "right": f"gte(X/W,1-({p}))",
        "up": f"gte(Y/H,1-({p}))",
        "down": f"lte(Y/H,{p})",
        "circle": f"lte(sqrt(pow((X-W/2)/(W/2),2)+pow((Y-H/2)/(H/2),2))/sqrt(2),{p})",
        "diamond": f"lte(abs(X-W/2)/W+abs(Y-H/2)/H,{p})",
        "horizontal": f"lte(abs(X-W/2)/(W/2),{p})",
        "vertical": f"lte(abs(Y-H/2)/(H/2),{p})",
        "diagonal": f"lte((X/W+Y/H)/2,{p})",
    }
    if mode == "dissolve_linear":
        return f"fade=t=in:st=0:d={duration:.8f}:alpha=1,"
    return f"format=gbrap,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({masks[family]})',"

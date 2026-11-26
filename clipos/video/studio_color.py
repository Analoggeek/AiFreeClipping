"""Finite color-balance controls and checksum-bound local .cube LUT assets."""

from pathlib import Path
import hashlib
import math

GRADE_DEFAULTS = {
    "gamma": 1.0,
    "exposure": 0.0,
    "rs": 0.0,
    "gs": 0.0,
    "bs": 0.0,
    "rm": 0.0,
    "gm": 0.0,
    "bm": 0.0,
    "rh": 0.0,
    "gh": 0.0,
    "bh": 0.0,
    "lut_path": "",
    "lut_sha256": "",
    "lut_strength": 1.0,
}


LEGACY_GRADE_KEYS = set(GRADE_DEFAULTS)
GRADE_DEFAULTS.update(curves={}, hsl={}, secondary={})


def validate_curves(curves):
    if not isinstance(curves, dict) or not set(curves) <= {
        "master",
        "red",
        "green",
        "blue",
    }:
        raise ValueError("Choose master/red/green/blue curves")
    for points in curves.values():
        if not isinstance(points, list) or not 2 <= len(points) <= 16:
            raise ValueError("Curves require 2–16 normalized points")
        previous = -1.0
        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError("Invalid curve point")
            if any(
                type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1
                for v in point
            ):
                raise ValueError("Curve points must be finite and normalized")
            if point[0] - previous < 0.000001:
                raise ValueError("Curve input coordinates must increase")
            previous = point[0]
        if points[0][0] != 0 or points[-1][0] != 1:
            raise ValueError("Curves must include input endpoints 0 and 1")
    return curves


def validate_hsl(hsl):
    if not isinstance(hsl, dict):
        raise ValueError("Global HSL must be an object")
    if not hsl:
        return hsl
    if set(hsl) != {"hue", "saturation", "lightness"}:
        raise ValueError("Incomplete global HSL controls")
    for key, value in hsl.items():
        bound = 180 if key == "hue" else 1
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not -bound <= value <= bound
        ):
            raise ValueError("HSL out of range: " + key)
    return hsl


HUE_CENTERS = {
    "red": 0.0,
    "yellow": 60.0,
    "green": 120.0,
    "cyan": 180.0,
    "blue": 240.0,
    "magenta": 300.0,
}


def validate_secondary(secondary):
    if not isinstance(secondary, dict) or not set(secondary) <= set(HUE_CENTERS):
        raise ValueError(
            "Secondary HSL requires named red/yellow/green/cyan/blue/magenta ranges"
        )
    for controls in secondary.values():
        validate_hsl(controls)
        if not controls:
            raise ValueError("Secondary HSL controls cannot be empty")
    return secondary


def adjust_hsl(rgb, hsl, secondary):
    import colorsys

    h, l, s = colorsys.rgb_to_hls(*rgb)
    hue_shift = sat_shift = light_shift = 0.0
    # Overlapping triangular masks use the original hue; all are zero on gray.
    for name, controls in secondary.items():
        distance = abs((h * 360 - HUE_CENTERS[name] + 180) % 360 - 180)
        weight = max(0.0, 1 - distance / 60) * min(1.0, s / 0.1)
        hue_shift += weight * controls["hue"]
        sat_shift += weight * controls["saturation"]
        light_shift += weight * controls["lightness"]
    return colorsys.hls_to_rgb(
        (h + (hsl.get("hue", 0) + hue_shift) / 360) % 1,
        max(0.0, min(1.0, l + hsl.get("lightness", 0) + light_shift)),
        max(0.0, min(1.0, s * (1 + hsl.get("saturation", 0)) * (1 + sat_shift))),
    )


def hsl_filter(hsl, work_dir, secondary=None):

    if work_dir is None:
        raise ValueError("HSL rendering requires an isolated work directory")
    secondary = secondary or {}
    size = 33
    import json

    signature = hashlib.sha256(
        json.dumps([hsl, secondary], sort_keys=True).encode()
    ).hexdigest()
    path = Path(work_dir) / ("hsl-" + signature + ".cube")
    if not path.exists():
        lines = [f"LUT_3D_SIZE {size}"]
        for blue in range(size):
            for green in range(size):
                for red in range(size):
                    rgb = adjust_hsl(
                        (red / (size - 1), green / (size - 1), blue / (size - 1)),
                        hsl,
                        secondary,
                    )
                    lines.append(" ".join(f"{v:.9f}" for v in rgb))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    from .renderer import _escape_ass_path

    return f"lut3d=file='{_escape_ass_path(path)}':interp=tetrahedral"


def read_cube(path):
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() != ".cube" or not path.is_file():
        raise ValueError("Choose a local .cube LUT file")
    with path.open("rb") as stream:
        raw = stream.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("LUT exceeds 16 MiB")
    text = raw.decode("utf-8-sig")
    size = None
    rows = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if parts[0] == "TITLE":
            continue
        if parts[0] == "LUT_3D_SIZE":
            if size is not None or len(parts) != 2:
                raise ValueError("Invalid LUT dimension header")
            size = int(parts[1])
            if not 2 <= size <= 65:
                raise ValueError("3D LUT size must be 2–65")
            continue
        if parts[0] in ("DOMAIN_MIN", "DOMAIN_MAX"):
            expected = [0.0, 0.0, 0.0] if parts[0] == "DOMAIN_MIN" else [1.0, 1.0, 1.0]
            if len(parts) != 4 or [float(v) for v in parts[1:]] != expected:
                raise ValueError("Only normalized 0–1 LUT domains are supported")
            continue
        if size is None or len(parts) != 3:
            raise ValueError("Unsupported LUT format or metadata")
        row = [float(v) for v in parts]
        if not all(math.isfinite(v) and -8 <= v <= 8 for v in row):
            raise ValueError("Invalid LUT sample")
        rows.append(row)
        if len(rows) > size**3:
            raise ValueError("Too many LUT samples")
    if size is None or len(rows) != size**3:
        raise ValueError("Incomplete 3D LUT samples")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size": size,
        "rows": rows,
    }


def validate_grade(grade):
    if not isinstance(grade, dict):
        raise ValueError("Color grade must be an object")
    if not grade:
        return grade
    if not LEGACY_GRADE_KEYS <= set(grade) or not set(grade) <= set(GRADE_DEFAULTS):
        raise ValueError("Incomplete or unsupported color grading parameters")
    validate_curves(grade.get("curves", {}))
    validate_hsl(grade.get("hsl", {}))
    validate_secondary(grade.get("secondary", {}))
    for key in LEGACY_GRADE_KEYS:
        if key in ("lut_path", "lut_sha256"):
            continue
        value = grade[key]
        lo, hi = (
            (0.1, 4.0)
            if key == "gamma"
            else (-3.0, 3.0)
            if key == "exposure"
            else (0.0, 1.0)
            if key == "lut_strength"
            else (-1.0, 1.0)
        )
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not lo <= value <= hi
        ):
            raise ValueError("Color grade out of range: " + key)
    path = grade["lut_path"]
    digest = grade["lut_sha256"]
    if not isinstance(path, str) or not isinstance(digest, str):
        raise ValueError("Invalid LUT asset reference")
    if path:
        if (
            "://" in path
            or len(path) > 4096
            or not Path(path).is_absolute()
            or Path(path).suffix.lower() != ".cube"
        ):
            raise ValueError("LUT must reference a local absolute .cube path")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("LUT requires verified SHA256")
    elif digest:
        raise ValueError("LUT checksum requires a file reference")
    return grade


def grade_filters(grade, work_dir=None):
    validate_grade(grade)
    if not grade:
        return []
    filters = []
    if grade["exposure"]:
        factor = 2 ** grade["exposure"]
        value = f"'clip(val*{factor:.8f},0,255)'"
        filters.append(f"lutrgb=r={value}:g={value}:b={value}")
    if grade["gamma"] != 1:
        filters.append(f"eq=gamma={grade['gamma']:.8f}")
    balances = [
        f"{key}={grade[key]:.8f}"
        for key in ("rs", "gs", "bs", "rm", "gm", "bm", "rh", "gh", "bh")
        if grade[key]
    ]
    if balances:
        filters.append("colorbalance=" + ":".join(balances))
    curves = grade.get("curves", {})
    if curves:
        definitions = []
        for channel, points in curves.items():
            definitions.append(
                channel + "='" + " ".join(f"{x:.8f}/{y:.8f}" for x, y in points) + "'"
            )
        filters.append("curves=" + ":".join(definitions))
    if grade.get("hsl") or grade.get("secondary"):
        filters.append(
            hsl_filter(grade.get("hsl", {}), work_dir, grade.get("secondary", {}))
        )
    if grade["lut_path"]:
        if work_dir is None:
            raise ValueError("LUT rendering requires an isolated work directory")
        cube = read_cube(grade["lut_path"])
        if cube["sha256"] != grade["lut_sha256"]:
            raise ValueError(
                "LUT file changed since verification; import it again explicitly"
            )
        amount = grade["lut_strength"]
        size = cube["size"]
        target = Path(work_dir) / f"lut-{cube['sha256']}-{round(amount * 1000000)}.cube"
        if target.resolve() == Path(cube["path"]):
            raise ValueError("LUT work file cannot overwrite source LUT")
        lines = [f"LUT_3D_SIZE {size}", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
        for index, row in enumerate(cube["rows"]):
            identity = [
                index % size / (size - 1),
                (index // size) % size / (size - 1),
                (index // (size * size)) / (size - 1),
            ]
            lines.append(
                " ".join(
                    f"{base * (1 - amount) + value * amount:.9f}"
                    for base, value in zip(identity, row)
                )
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        from .renderer import _escape_ass_path

        filters.append(f"lut3d=file='{_escape_ass_path(target)}':interp=tetrahedral")
    return filters

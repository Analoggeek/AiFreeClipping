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
    if set(grade) != set(GRADE_DEFAULTS):
        raise ValueError("Incomplete or unsupported color grading parameters")
    for key in GRADE_DEFAULTS:
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

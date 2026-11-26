"""Original asset-based editable title/logo graphics rendered as alpha media."""

from pathlib import Path
import hashlib
import json
import math
import tempfile
import uuid

from ..core.resources import resource_dir
from ..core.ffmpeg import FFmpegRunner


def graphic_catalog():
    path = resource_dir("templates") / "motion/catalog.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate_graphic(spec):
    if not isinstance(spec, dict):
        raise ValueError("Graphic configuration must be an object")
    if not spec:
        return spec
    if set(spec) != {
        "template",
        "title",
        "subtitle",
        "logo_path",
        "logo_sha256",
        "duration",
        "animation",
        "width",
        "height",
        "fps",
    }:
        raise ValueError("Unsupported graphic configuration")
    if (
        not isinstance(spec["template"], str)
        or spec["template"] not in graphic_catalog()
    ):
        raise ValueError("Unknown graphic template")
    for key in ("title", "subtitle"):
        if not isinstance(spec[key], str) or len(spec[key]) > 200 or "\n" in spec[key]:
            raise ValueError(
                "Graphic text must be a single line of at most 200 characters"
            )
    if not spec["title"].strip():
        raise ValueError("Graphic title is required")
    for key in ("width", "height"):
        if type(spec[key]) is not int or spec[key] % 2 or not 16 <= spec[key] <= 4096:
            raise ValueError("Graphic canvas must be even and 16–4096 pixels")
    if type(spec["fps"]) is not int or not 1 <= spec["fps"] <= 60:
        raise ValueError("Graphic frame rate must be 1–60")
    if (
        type(spec["duration"]) not in (int, float)
        or not math.isfinite(spec["duration"])
        or not 0.2 <= spec["duration"] <= 30
    ):
        raise ValueError("Graphic duration must be 0.2–30 seconds")
    if (
        abs(spec["duration"] * spec["fps"] - round(spec["duration"] * spec["fps"]))
        > 1e-6
    ):
        raise ValueError("Graphic duration must align to the project frame grid")
    if spec["animation"] not in ("fade", "slide"):
        raise ValueError("Unsupported graphic animation")
    path = spec["logo_path"]
    digest = spec["logo_sha256"]
    if not isinstance(path, str) or not isinstance(digest, str):
        raise ValueError("Invalid graphic logo reference")
    if path and (
        "://" in path
        or not Path(path).is_absolute()
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise ValueError("Logo requires a local absolute path and SHA256")
    if not path and digest:
        raise ValueError("Logo hash requires a file")
    return spec


def inspect_logo(path):
    from PIL import Image

    path = Path(path).resolve()
    with path.open("rb") as stream:
        data = stream.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("Logo exceeds 16 MiB")
    from io import BytesIO

    with Image.open(BytesIO(data)) as image:
        if (
            image.format not in ("PNG", "JPEG", "WEBP")
            or image.width * image.height > 16_000_000
        ):
            raise ValueError("Use a PNG/JPEG/WebP logo up to 16 megapixels")
        image.verify()
    return str(path), hashlib.sha256(data).hexdigest()


def render_graphic(spec, output_dir, *, cancelled=None, progress=None):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    from ..core.fonts import find_font_file

    validate_graphic(spec)
    catalog = graphic_catalog()
    template = catalog[spec["template"]]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / ("graphic-" + uuid.uuid4().hex + ".mov")
    with tempfile.TemporaryDirectory(prefix="graphic-", dir=output_dir) as work:
        with Image.open(
            resource_dir("templates") / "motion" / template["asset"]
        ) as plate:
            image = plate.convert("RGBA")
        draw = ImageDraw.Draw(image)
        font_path = find_font_file()
        if not font_path:
            raise RuntimeError("No installed font file for graphic text")
        for key, box_key, color_key in [
            ("title", "title_box", "title_color"),
            ("subtitle", "subtitle_box", "subtitle_color"),
        ]:
            x, y, width, height = template[box_key]
            text = spec[key]
            size = 44 if key == "title" else 27
            font = ImageFont.truetype(str(font_path), size)
            while size > 10 and draw.textbbox((0, 0), text, font=font)[2] > width:
                size -= 1
                font = ImageFont.truetype(str(font_path), size)
            if draw.textbbox((0, 0), text, font=font)[2] > width:
                raise ValueError(
                    "Graphic text is too long for this template; shorten it"
                )
            draw.text((x, y), text, font=font, fill=template[color_key])
        if spec["logo_path"]:
            path, digest = inspect_logo(spec["logo_path"])
            if digest != spec["logo_sha256"]:
                raise ValueError("Logo changed since selection; select it again")
            with Image.open(path) as logo:
                x, y, w, h = template["logo_box"]
                logo = ImageOps.contain(logo.convert("RGBA"), (w, h))
                image.alpha_composite(
                    logo, (x + (w - logo.width) // 2, y + (h - logo.height) // 2)
                )
        image = image.resize((spec["width"], spec["height"]), Image.Resampling.LANCZOS)
        png = Path(work) / "plate.png"
        image.save(png)
        duration = spec["duration"]
        fade = min(0.3, duration / 3)
        filters = f"format=argb,fade=t=in:st=0:d={fade:.8f}:alpha=1,fade=t=out:st={duration - fade:.8f}:d={fade:.8f}:alpha=1"
        if spec["animation"] == "slide":
            filters = (
                f"[0:v]{filters}[plate];color=c=black@0:s={spec['width']}x{spec['height']}:r={spec['fps']}:d={duration},format=rgba[clear];"
                f"[clear][plate]overlay=x='if(lt(t,{fade}),-w*(1-t/{fade}),0)':y=0:format=auto,format=argb[out]"
            )
            args = ["-filter_complex", filters, "-map", "[out]"]
        else:
            args = ["-vf", filters]
        try:
            FFmpegRunner(
                total_duration=duration, cancel_cb=cancelled, progress_cb=progress
            ).run(
                [
                    "-hide_banner",
                    "-nostdin",
                    "-loop",
                    "1",
                    "-framerate",
                    str(spec["fps"]),
                    "-i",
                    str(png),
                    *args,
                    "-t",
                    str(duration),
                    "-c:v",
                    "qtrle",
                    "-pix_fmt",
                    "argb",
                    "-an",
                    "-threads",
                    "2",
                    str(output),
                ]
            )
        except Exception:
            output.unlink(missing_ok=True)
            raise
    # Carry freely licensed artwork provenance into the generated derivative.
    from .free_assets import asset_catalog, blob_hash

    provenance = {
        "original_template": spec["template"],
        "template_license": "CC0-1.0",
        "modifications": "Composited editable text/logo; resized and animated.",
        "third_party_artwork": None,
    }
    if spec["logo_path"]:
        raw = Path(spec["logo_path"]).read_bytes()
        identity = blob_hash(raw)
        artwork = next(
            (entry for entry in asset_catalog() if entry["blob_sha"] == identity), None
        )
        if artwork:
            provenance["third_party_artwork"] = artwork
    metadata = output.with_suffix(".source.json")
    license_path = output.with_suffix(".LICENSE.txt")
    try:
        metadata.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        if provenance["third_party_artwork"]:
            license_path.write_text(
                "Noto Emoji artwork: Copyright Google LLC. Composited, resized and animated.\n"
                + (
                    resource_dir("templates") / "free_library/Noto-Apache-2.0.txt"
                ).read_text(),
                encoding="utf-8",
            )
    except Exception:
        output.unlink(missing_ok=True)
        metadata.unlink(missing_ok=True)
        license_path.unlink(missing_ok=True)
        raise
    return output


def export_graphic_pack(template_id, output):
    """Package an original offline design and editable recipe without overwriting."""
    import os
    import zipfile

    catalog = graphic_catalog()
    if template_id not in catalog:
        raise ValueError("Unknown graphic template")
    root = resource_dir("templates") / "motion"
    design = catalog[template_id]
    manifest = json.loads((root / (template_id + ".pack.json")).read_text())
    if manifest["design"] != design or manifest["license"] != "CC0-1.0":
        raise ValueError("Invalid original pack manifest")
    files = [design["asset"]] + [
        design[key] for key in ("artwork", "panel") if key in design
    ]
    output = Path(output)
    if output.suffix.lower() != ".zip":
        raise ValueError("Choose a new .zip output")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(
        prefix=".graphic-pack-", suffix=".zip", dir=output.parent
    )
    os.close(fd)
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in files:
                if Path(name).name != name or not name.endswith(".png"):
                    raise ValueError("Invalid pack asset path")
                archive.write(root / name, name)
            archive.writestr("pack.json", json.dumps(manifest, indent=2) + "\n")
            archive.writestr(
                "LICENSE.txt",
                "Original artwork dedicated under CC0-1.0 to the extent permitted by law. No third-party art, user logos or fonts included.\nhttps://creativecommons.org/publicdomain/zero/1.0/\n",
            )
            archive.writestr(
                "README.txt",
                "Original offline title-scene design. pack.json records editable title/subtitle/logo slots, default timing and supported fade/slide animations. PNG art uses a 720x1280 transparent canvas. Render through Ai clipping PRO Motion graphics; ZIP is a design handoff, not an arbitrary third-party motion-project format. User logo and installed fonts are not redistributed.\n",
            )
        os.link(temp, output)
    finally:
        Path(temp).unlink(missing_ok=True)
    return str(output)

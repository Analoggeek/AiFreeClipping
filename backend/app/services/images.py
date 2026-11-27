"""On-the-spot visuals: Nano Banana (optional cloud key) with fully local ComfyUI fallback."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .net import urlopen as https_open

from ..config import ASSETS, env
from ..db import db

WORKFLOW = Path(__file__).parent.parent / "assets" / "comfy_sdxl.json"


def _comfy_url() -> str:
    return env("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")


def comfy_reachable() -> bool:
    try:
        with https_open(f"{_comfy_url()}/system_stats", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def _save(data: bytes, prefix: str) -> str:
    folder = ASSETS / "generated"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:5]}.png"
    path.write_bytes(data)
    return str(path)


def nano_banana(
    prompt: str,
    aspect: str = "9:16",
    reference_path: str | None = None,
    api_key: str | None = None,
) -> str:
    key = api_key or db.get_setting("gemini_api_key", env("GEMINI_API_KEY"))
    if not key:
        raise RuntimeError("Nano Banana needs a Gemini API key. Add it in Settings, or choose the local ComfyUI provider.")
    parts: list[dict[str, Any]] = [{"text": prompt}]
    if reference_path and Path(reference_path).exists():
        raw = Path(reference_path).read_bytes()
        mime = "image/png" if str(reference_path).lower().endswith(".png") else "image/jpeg"
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode()}})
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {"aspectRatio": aspect}},
    }
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    with https_open(request, timeout=180) as response:
        data = json.loads(response.read())
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return _save(base64.b64decode(inline["data"]), "nano_banana")
    raise RuntimeError("Nano Banana returned no image. Try a different prompt or provider.")


def comfyui(
    prompt: str,
    aspect: str = "9:16",
    negative: str = "text, watermark, blurry, low quality",
    reference_path: str | None = None,
) -> str:
    """Queue an SDXL workflow on a locally running ComfyUI server."""
    if not comfy_reachable():
        raise RuntimeError("ComfyUI is not running at " + _comfy_url())
    workflow = json.loads(WORKFLOW.read_text())
    workflow["6"]["inputs"]["text"] = prompt
    workflow["7"]["inputs"]["text"] = negative
    workflow["4"]["inputs"]["ckpt_name"] = db.get_setting("comfy_checkpoint", env("COMFY_CHECKPOINT", "sd_xl_base_1.0.safetensors"))
    sizes = {"16:9": (1344, 768), "1:1": (1024, 1024), "9:16": (768, 1344)}
    width, height = sizes.get(aspect, (768, 1344))
    workflow["5"]["inputs"].update({"width": width, "height": height})
    workflow["3"]["inputs"]["seed"] = secrets.randbelow(2**32)
    client_id = str(uuid.uuid4())
    request = urllib.request.Request(
        f"{_comfy_url()}/prompt",
        data=json.dumps({"prompt": workflow, "client_id": client_id}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with https_open(request, timeout=30) as response:
        prompt_id = json.loads(response.read())["prompt_id"]
    deadline = time.time() + 600
    while time.time() < deadline:
        with https_open(f"{_comfy_url()}/history/{prompt_id}", timeout=10) as response:
            history = json.loads(response.read())
        if prompt_id in history:
            outputs = history[prompt_id].get("outputs", {})
            for node in outputs.values():
                for image in node.get("images", []):
                    query = urllib.parse.urlencode(
                        {k: image.get(k, "") for k in ("filename", "subfolder", "type")}
                    )
                    with https_open(f"{_comfy_url()}/view?{query}", timeout=60) as response:
                        return _save(response.read(), "comfyui")
            raise RuntimeError("ComfyUI finished but produced no image")
        time.sleep(1)
    raise TimeoutError("ComfyUI image generation timed out")


def local_art(prompt: str, aspect: str = "9:16", variation: int = 0) -> str:
    """Create a decorative offline graphic; this is not a prompt-to-image model."""
    from PIL import Image, ImageDraw, ImageFilter

    sizes = {"16:9": (1344, 768), "1:1": (1024, 1024), "9:16": (768, 1344)}
    width, height = sizes.get(aspect, (768, 1344))
    seed_text = f"{prompt}\0{variation}\0{uuid.uuid4().hex}"
    seed = int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], "big")
    rand = __import__("random").Random(seed)
    hue = seed % 360
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(1, height - 1)
        draw.line(
            [(0, y), (width, y)],
            fill=(int(28 + 42 * t + hue % 20), int(18 + 28 * t), int(60 + 70 * t)),
        )
    # Keep the offline renderer deliberately decorative rather than pretending
    # its abstract graphic is the output of an AI image model.
    for _ in range(10):
        cx, cy = rand.randint(0, width), rand.randint(0, height)
        radius = rand.randint(width // 18, width // 5)
        color = (rand.randint(80, 210), rand.randint(60, 175), rand.randint(145, 245))
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=color, width=rand.randint(3, 10))
    image = image.filter(ImageFilter.GaussianBlur(1.0))
    return _save_image(image, "local")


def _save_image(image, prefix: str) -> str:
    folder = ASSETS / "generated"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:5]}.png"
    image.save(path, "PNG")
    return str(path)


_VARIATION_DIRECTIONS = (
    "Use a dramatic close-up and strong rim lighting.",
    "Use an environmental wide composition with clear foreground depth.",
    "Use a polished editorial illustration with a clean, uncluttered silhouette.",
    "Use a bold low-angle composition with a distinct color palette.",
)


def generate(
    prompt: str,
    provider: str = "auto",
    aspect: str = "9:16",
    reference: str | None = None,
    negative: str = "text, watermark, blurry, low quality",
    *,
    variation: int = 0,
    variation_count: int = 1,
) -> dict[str, Any]:
    has_key = bool(db.get_setting("gemini_api_key", env("GEMINI_API_KEY")))
    if provider == "auto":
        if has_key and env("DISABLE_CLOUD_FEATURES") != "1":
            provider = "nano-banana"
        elif comfy_reachable():
            provider = "comfyui"
        else:
            raise RuntimeError(
                "No AI image model is ready. Add a Gemini API key in Settings or start ComfyUI with an SDXL checkpoint. "
                "Offline decorative art is available, but it is not prompt-generated AI art."
            )

    prompt_for_variant = prompt.strip()
    if variation_count > 1:
        direction = _VARIATION_DIRECTIONS[variation % len(_VARIATION_DIRECTIONS)]
        prompt_for_variant += (
            f"\n\nCreate alternative {variation + 1} of {variation_count}: {direction} "
            "Keep the requested subject and style, but make the composition visibly different from other options."
        )

    if provider == "nano-banana":
        path = nano_banana(prompt_for_variant, aspect, reference)
    elif provider == "comfyui":
        path = comfyui(prompt_for_variant, aspect, negative, reference)
    elif provider == "local":
        path = local_art(prompt, aspect, variation)
    else:
        raise RuntimeError(f"Unknown image provider: {provider}")
    return {"path": path, "url": "/api/assets/file?path=" + urllib.parse.quote(path), "provider": provider}


def generate_variations(
    prompt: str,
    provider: str = "auto",
    aspect: str = "9:16",
    reference: str | None = None,
    negative: str = "text, watermark, blurry, low quality",
    count: int = 3,
    on_progress=None,
) -> dict[str, Any]:
    """Generate several independent options and retain partial success on failure."""
    count = max(1, min(4, int(count)))
    results: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index in range(count):
        try:
            result = generate(
                prompt, provider, aspect, reference, negative,
                variation=index, variation_count=count,
            )
            results.append(result)
        except Exception as exc:
            warnings.append(f"Option {index + 1} failed: {exc}")
        if on_progress:
            on_progress(round((index + 1) / count * 95), f"Generated {len(results)} of {count} image options…")
    if not results:
        details = " ".join(warnings)
        raise RuntimeError(f"Image generation produced no usable options. {details}".strip())
    return {"images": results, "path": results[0]["path"], "url": results[0]["url"], "provider": results[0]["provider"], "warnings": warnings}

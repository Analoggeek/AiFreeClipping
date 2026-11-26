"""On-the-spot visuals: Nano Banana (optional cloud key) with fully local ComfyUI fallback."""
from __future__ import annotations

import base64
import json
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from ..config import ASSETS, env
from ..db import db

WORKFLOW = Path(__file__).parent.parent / "assets" / "comfy_sdxl.json"


def _comfy_url() -> str:
    return env("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")


def comfy_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{_comfy_url()}/system_stats", timeout=2) as response:
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
    with urllib.request.urlopen(request, timeout=180) as response:
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
    workflow["3"]["inputs"]["seed"] = int(time.time())
    client_id = str(uuid.uuid4())
    request = urllib.request.Request(
        f"{_comfy_url()}/prompt",
        data=json.dumps({"prompt": workflow, "client_id": client_id}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        prompt_id = json.loads(response.read())["prompt_id"]
    deadline = time.time() + 600
    while time.time() < deadline:
        with urllib.request.urlopen(f"{_comfy_url()}/history/{prompt_id}", timeout=10) as response:
            history = json.loads(response.read())
        if prompt_id in history:
            outputs = history[prompt_id].get("outputs", {})
            for node in outputs.values():
                for image in node.get("images", []):
                    query = urllib.parse.urlencode(
                        {k: image.get(k, "") for k in ("filename", "subfolder", "type")}
                    )
                    with urllib.request.urlopen(f"{_comfy_url()}/view?{query}", timeout=60) as response:
                        return _save(response.read(), "comfyui")
            raise RuntimeError("ComfyUI finished but produced no image")
        time.sleep(1)
    raise TimeoutError("ComfyUI image generation timed out")


def generate(prompt: str, provider: str = "auto", aspect: str = "9:16", reference: str | None = None, negative: str = "text, watermark, blurry, low quality") -> dict[str, Any]:
    has_key = bool(db.get_setting("gemini_api_key", env("GEMINI_API_KEY")))
    if provider == "auto":
        provider = "nano-banana" if has_key and env("DISABLE_CLOUD_FEATURES") != "1" else "comfyui"
    if provider == "nano-banana":
        path = nano_banana(prompt, aspect, reference)
    else:
        path = comfyui(prompt, aspect, negative, reference)
    return {"path": path, "url": "/api/assets/file?path=" + urllib.parse.quote(path), "provider": provider}

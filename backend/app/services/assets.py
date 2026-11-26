"""Copyright-friendly stock media search (Pexels / Pixabay / Openverse) with local download."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..config import ASSETS, env
from ..db import db
from .utils import safe_name

HEADERS = {"User-Agent": "AI-Clipper-Pro/1.0 (+https://github.com/Analoggeek/AiFreeClipping)"}


def _get(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={**HEADERS, **(headers or {})})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read())


def search(query: str, source: str = "pexels", kind: str = "image", per_page: int = 12) -> list[dict[str, Any]]:
    q = urllib.parse.quote(query)
    if source == "pexels":
        key = db.get_setting("pexels_api_key", env("PEXELS_API_KEY"))
        if not key:
            raise RuntimeError("Add a free Pexels API key in Settings to search stock media.")
        endpoint = "https://api.pexels.com/videos/search" if kind == "video" else "https://api.pexels.com/v1/search"
        url = f"{endpoint}?query={q}&per_page={per_page}"
        data = _get(url, {"Authorization": key})
        items = data.get("videos", data.get("photos", []))
        return [
            {
                "id": str(item.get("id", "")),
                "title": item.get("title") or item.get("alt") or "Stock media",
                "url": (item.get("video_files") or [{}])[0].get("link") or item.get("src", {}).get("original", ""),
                "preview": item.get("image") or item.get("src", {}).get("medium", ""),
                "source": "Pexels",
                "license": "Pexels License — free commercial use",
                "creator": item.get("user", {}).get("name", "Pexels contributor"),
            }
            for item in items
        ]
    if source == "pixabay":
        key = db.get_setting("pixabay_api_key", env("PIXABAY_API_KEY"))
        if not key:
            raise RuntimeError("Add a free Pixabay API key in Settings to search stock media.")
        media_type = "videos" if kind == "video" else "photo"
        url = f"https://pixabay.com/api/?key={key}&q={q}&image_type={media_type}&per_page={per_page}"
        data = _get(url)
        return [
            {
                "id": str(item.get("id", "")),
                "title": item.get("title") or item.get("tags", "Stock media"),
                "url": (item.get("videos") or {}).get("large", {}).get("url") or item.get("largeImageURL", ""),
                "preview": item.get("previewURL") or item.get("webformatURL", ""),
                "source": "Pixabay",
                "license": "Pixabay Content License — free commercial use (credit shown in app)",
                "creator": item.get("user", "Pixabay contributor"),
            }
            for item in data.get("hits", [])
        ]
    url = f"https://api.openverse.org/v1/images/?q={q}&page_size={per_page}"
    data = _get(url)
    return [
        {
            "id": str(item.get("id", "")),
            "title": item.get("title") or "Openverse image",
            "url": item.get("url", ""),
            "preview": item.get("thumbnail", ""),
            "source": "Openverse",
            "license": item.get("license", "CC"),
            "creator": item.get("creator") or "Openverse contributor",
        }
        for item in data.get("results", [])
    ]


def download(url: str, name: str | None = None, source: str = "stock") -> dict[str, Any]:
    folder = ASSETS / safe_name(source or "stock")
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".gif", ".mp3", ".wav"}:
        suffix = ".jpg"
    path = folder / f"{safe_name(name or 'asset')}_{int(__import__('time').time())}{suffix}"
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=120) as response, path.open("wb") as handle:
        total = 0
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            total += len(chunk)
            if total > 300 * 1024 * 1024:
                raise RuntimeError("Asset is larger than 300 MB")
            handle.write(chunk)
    return {
        "path": str(path),
        "url": "/api/assets/file?path=" + urllib.parse.quote(str(path)),
        "size": path.stat().st_size,
    }

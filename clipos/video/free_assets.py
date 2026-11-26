"""Opt-in, pinned Apache-2.0 PNG library; no account, key or background fetch."""

import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request

from ..core.resources import resource_dir

REPOSITORY = "googlefonts/noto-emoji"
COMMIT = "e8073ab740292f8d5f19b5de144087ac58044d06"


def asset_catalog():
    entries = json.loads(
        (resource_dir("templates") / "free_library/catalog.json").read_text()
    )
    for entry in entries:
        if (
            entry["repository"] != REPOSITORY
            or entry["commit"] != COMMIT
            or entry["license"] != "Apache-2.0"
        ):
            raise ValueError("Unsupported library origin or license")
        if len(entry["blob_sha"]) != 40 or any(
            c not in "0123456789abcdef" for c in entry["blob_sha"]
        ):
            raise ValueError("Invalid asset identity")
        if not 0 < entry["size"] < 1024 * 1024:
            raise ValueError("Invalid asset size")
    return entries


def blob_hash(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def download_asset(asset_id, directory, *, cancelled=None, progress=None):
    """Retrieve one pinned blob, validate bytes and image, then atomically publish.

    Existing files are verified before offline reuse, never silently overwritten.
    License/provenance is written before publishing new media.
    """
    from PIL import Image
    from io import BytesIO

    def check():
        if cancelled and cancelled():
            raise RuntimeError("Asset download cancelled")

    check()
    entries = {a["id"]: a for a in asset_catalog()}
    if asset_id not in entries:
        raise ValueError("Unknown free-library asset")
    entry = entries[asset_id]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (entry["blob_sha"] + ".png")
    if target.exists():
        with target.open("rb") as stream:
            data = stream.read(entry["size"] + 1)
        if len(data) != entry["size"] or blob_hash(data) != entry["blob_sha"]:
            raise ValueError(
                "Cached asset is corrupt; remove it explicitly before retrying"
            )
    else:
        url = f"https://api.github.com/repos/{REPOSITORY}/git/blobs/{entry['blob_sha']}"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Ai-clipping-PRO-free-library",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read(2 * 1024 * 1024 + 1)
        except Exception as exc:
            raise RuntimeError(
                "Asset download failed (check network / GitHub API rate limit); retry later. "
                + str(exc)
            ) from exc
        check()
        if len(payload) > 2 * 1024 * 1024:
            raise ValueError("Asset response exceeds limit")
        body = json.loads(payload)
        if body.get("encoding") != "base64":
            raise ValueError("Unexpected asset response encoding")
        data = base64.b64decode("".join(body["content"].split()), validate=True)
        if len(data) != entry["size"] or blob_hash(data) != entry["blob_sha"]:
            raise ValueError("Downloaded asset failed pinned Git blob verification")
    with Image.open(BytesIO(data)) as image:
        if image.format != "PNG" or image.size != (128, 128):
            raise ValueError("Invalid library PNG")
        image.verify()
    check()
    license_text = (
        resource_dir("templates") / "free_library/Noto-Apache-2.0.txt"
    ).read_text()
    provenance = dict(
        entry,
        sha256=hashlib.sha256(data).hexdigest(),
        modified=False,
        copyright="Copyright Google LLC. Original Noto Emoji artwork. Apache License 2.0; no trademark endorsement.",
    )

    # Atomic metadata replacement is safe: deterministic and never a user media path.
    def atomic(path, content):
        fd, temp = tempfile.mkstemp(prefix=".asset-", dir=directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
            check()
            os.replace(temp, path)
        finally:
            Path(temp).unlink(missing_ok=True)

    atomic(directory / (entry["blob_sha"] + ".LICENSE.txt"), license_text.encode())
    atomic(
        directory / (entry["blob_sha"] + ".source.json"),
        (json.dumps(provenance, indent=2) + "\n").encode(),
    )
    if not target.exists():
        fd, temp = tempfile.mkstemp(prefix=".asset-", dir=directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            check()
            # Link publishes without overwriting a concurrent or user-created file.
            try:
                os.link(temp, target)
            except FileExistsError:
                if target.read_bytes() != data:
                    raise ValueError("Asset destination changed during download")
        finally:
            Path(temp).unlink(missing_ok=True)
    if progress:
        progress(100, "Verified local asset ready")
    return str(target)


def cached_asset(asset_id, directory):
    """Return verified cached media only; never access the network from preview."""
    entries = {a["id"]: a for a in asset_catalog()}
    if asset_id not in entries:
        raise ValueError("Unknown free-library asset")
    entry = entries[asset_id]
    path = Path(directory) / (entry["blob_sha"] + ".png")
    if not path.exists():
        return None
    with path.open("rb") as stream:
        data = stream.read(entry["size"] + 1)
    if len(data) != entry["size"] or blob_hash(data) != entry["blob_sha"]:
        raise ValueError("Cached artwork failed integrity check")
    return str(path)


def download_library(directory, *, cancelled=None, progress=None):
    """Explicit full-library download with per-file failure isolation and retry.

    Valid cached assets are reverified without network. A retry resumes naturally
    by reusing them. Never claim all ready when any file failed.
    """
    entries = asset_catalog()
    ready = []
    failures = []
    for index, entry in enumerate(entries):
        if cancelled and cancelled():
            raise RuntimeError(
                f"Library download cancelled; {len(ready)} verified files retained for retry"
            )
        try:
            path = download_asset(entry["id"], directory, cancelled=cancelled)
            ready.append({"id": entry["id"], "path": path})
        except Exception as exc:
            if cancelled and cancelled():
                raise RuntimeError(
                    f"Library download cancelled; {len(ready)} verified files retained for retry"
                ) from exc
            failures.append({"id": entry["id"], "error": str(exc)})
        if progress:
            progress(
                100 * (index + 1) / len(entries),
                f"{index + 1}/{len(entries)} checked; {len(ready)} ready, {len(failures)} failed",
            )
    return {"ready": ready, "failures": failures, "total": len(entries)}

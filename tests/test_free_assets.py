"""Pinned library integrity, offline cache and failure behavior. Network is opt-in."""

import base64
import io
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from clipos.video.free_assets import asset_catalog, blob_hash, download_asset


def fixture():
    stream = io.BytesIO()
    Image.new("RGBA", (128, 128), "red").save(stream, format="PNG")
    data = stream.getvalue()
    entry = dict(asset_catalog()[0], blob_sha=blob_hash(data), size=len(data))
    payload = json.dumps(
        {"encoding": "base64", "content": base64.b64encode(data).decode()}
    ).encode()
    return entry, data, payload


def test_download_integrity_license_offline_cache_and_no_overwrite(tmp_path):
    entry, data, payload = fixture()
    with (
        patch("clipos.video.free_assets.asset_catalog", return_value=[entry]),
        patch("urllib.request.urlopen", return_value=io.BytesIO(payload)) as request,
    ):
        result = Path(download_asset(entry["id"], tmp_path))
        assert result.read_bytes() == data
        assert request.call_count == 1
        assert result.with_suffix(".LICENSE.txt").exists()
        assert (
            json.loads(result.with_suffix(".source.json").read_text())["license"]
            == "Apache-2.0"
        )
        assert download_asset(entry["id"], tmp_path) == str(result)
        assert request.call_count == 1
        result.write_bytes(b"changed")
        with pytest.raises(ValueError, match="corrupt"):
            download_asset(entry["id"], tmp_path)
        assert result.read_bytes() == b"changed"


def test_corrupt_download_and_cancellation_publish_no_media(tmp_path):
    entry, data, payload = fixture()
    with (
        patch("clipos.video.free_assets.asset_catalog", return_value=[entry]),
        patch(
            "urllib.request.urlopen",
            return_value=io.BytesIO(
                payload.replace(base64.b64encode(data), base64.b64encode(b"bad"))
            ),
        ),
    ):
        with pytest.raises(ValueError):
            download_asset(entry["id"], tmp_path)
    assert not list(tmp_path.glob("*.png"))
    with pytest.raises(RuntimeError, match="cancelled"):
        download_asset(entry["id"], tmp_path, cancelled=lambda: True)
    assert not list(tmp_path.glob(".asset-*"))


def test_catalog_fifty_pinned_assets_and_bundled_license():
    entries = asset_catalog()
    assert len(entries) == 50
    assert len({a["id"] for a in entries}) == 50
    assert all(
        a["license"] == "Apache-2.0"
        and a["source"].startswith("https://github.com/googlefonts/noto-emoji/blob/")
        for a in entries
    )

"""v5.1.6 regression coverage for crops, safe cleanup and QuickTime-ready exports."""
from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import ffmpeg_binary
from app.db import db, dumps, now
from app.jobs import JobManager
import app.main as main_module
from app.main import _region_boxes, app
from app.schemas import RegionSelection
from app.services import models, render
from app.services.utils import probe

client = TestClient(app)
HEADERS = {"X-AI-Clipper-Token": "aifreeclip-test-token"}


def test_legacy_box_and_multi_region_list_do_not_duplicate_the_first_focus_area():
    first = {"x": 0, "y": 0, "w": 1, "h": 0.5}
    second = {"x": 0, "y": 0.5, "w": 1, "h": 0.5}
    region = RegionSelection(media_id="m1", kind="custom", box=first, boxes=[first, second])
    assert _region_boxes(region) == [first, second]
    assert _region_boxes(RegionSelection(media_id="m1", kind="custom", box=first)) == [first]


def test_region_crop_is_in_the_render_filter_and_mp4_is_portable():
    options = {
        "aspect": "9:16", "resolution": "1080p", "captions": [],
        "caption_style": {"preset": "none"}, "blur_background": True,
        "region": {"x": 0.25, "y": 0.1, "w": 0.4, "h": 0.7},
    }
    args = render.build_clip_args("/tmp/source.mp4", 4, 12, "/tmp/crop.mp4", options, has_audio=True)
    joined = " ".join(args)
    assert "trim=start=4.000:end=12.000,crop=" in joined
    assert "contrast=1.000" in joined
    assert args[args.index("-profile:v") + 1] == "high"
    assert args[args.index("-pix_fmt") + 1] == "yuv420p"
    assert args[args.index("-tag:v") + 1] == "avc1"
    assert args[args.index("-color_primaries") + 1] == "bt709"
    assert args[args.index("-color_trc") + 1] == "bt709"


def test_legacy_neutral_contrast_values_are_corrected_for_ffmpeg_eq():
    assert render._normalise_contrast(0) == 1.0
    assert render._normalise_contrast(0.05) == 1.05
    assert render._normalise_contrast(1.2) == 1.2
    assert render._normalise_contrast(None) == 1.0


def test_watermark_is_opt_in_and_only_uses_a_custom_image(tmp_path):
    base_options = {
        "aspect": "9:16", "resolution": "720p", "captions": [],
        "caption_style": {"preset": "none"}, "sfx": [],
    }
    plain = " ".join(render.build_clip_args("/tmp/source.mp4", 0, 1, "/tmp/plain.mp4", base_options, has_audio=False))
    assert "[wm]" not in plain and "[branded]" not in plain

    logo = tmp_path / "channel-logo.png"
    logo.write_bytes(b"test image")
    branded = " ".join(render.build_clip_args(
        "/tmp/source.mp4", 0, 1, "/tmp/branded.mp4",
        {**base_options, "watermark_path": str(logo)}, has_audio=False,
    ))
    assert str(logo) in branded
    assert "colorchannelmixer=aa=0.85" in branded and "[branded]" in branded


def test_actual_crop_render_is_quicktime_friendly_h264_mp4(tmp_path):
    source = tmp_path / "source.mp4"
    output = tmp_path / "cropped.mp4"
    command = [
        ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000",
        "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
    ]
    available = subprocess.run([ffmpeg_binary(), "-hide_banner", "-encoders"], capture_output=True, text=True)
    if "libx264" not in available.stdout:
        import pytest
        pytest.skip("Local FFmpeg does not include the libx264 encoder")
    subprocess.run(command, check=True, capture_output=True)
    asyncio.run(render.render_clip(
        str(source), 0, 1, str(output), {
            "aspect": "9:16", "resolution": "720p",
            "region": {"x": 0.2, "y": 0.1, "w": 0.5, "h": 0.8},
            "outline_style": "neon", "blur_background": True,
            "caption_style": {"preset": "none"}, "sfx": [],
        },
    ))
    info = probe(output)
    assert output.stat().st_size > 1000
    assert (info["video_codec"], info["audio_codec"]) == ("h264", "aac")
    assert (info["width"], info["height"]) == (720, 1280)
    assert (info["color_range"], info["color_primaries"], info["color_transfer"], info["color_space"]) == (
        "tv", "bt709", "bt709", "bt709",
    )


def test_timeline_renderer_applies_selected_region(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    logo = tmp_path / "channel.png"
    logo.write_bytes(b"logo")
    captured = {}

    async def capture_encode(args, duration, on_progress=None):
        captured["args"] = args
        captured["duration"] = duration
        return Path(args[-1])

    monkeypatch.setattr(render, "probe", lambda _path: {"video_codec": "h264", "audio_codec": "", "width": 640, "height": 360})
    monkeypatch.setattr(render, "encode", capture_encode)
    monkeypatch.setattr(render, "_validate_mp4", lambda _path: None)
    asyncio.run(render.render_timeline({
        "aspect": "9:16", "resolution": "720p",
        "tracks": {"video": [{
            "path": str(source), "sourceStart": 2, "duration": 8,
            "region": {"x": 0.2, "y": 0.1, "w": 0.5, "h": 0.8},
            "outline_style": "double",
        }], "captions": [], "stickers": [], "audio": []},
    }, str(tmp_path / "timeline.mp4"), watermark_path=str(logo)))
    filter_graph = captured["args"][captured["args"].index("-filter_complex") + 1]
    assert "crop=iw*0.5000:ih*0.8000:iw*0.2000:ih*0.1000" in filter_graph
    assert "scale=720:1280" in filter_graph
    assert "drawbox=" in filter_graph and "white@0.96" in filter_graph
    assert "[1:v]scale=100:-1,format=rgba,colorchannelmixer=aa=0.85[wm]" in filter_graph


def test_cancelled_ffmpeg_render_removes_partial_mp4(tmp_path, monkeypatch):
    import pytest

    output = tmp_path / "partial.mp4"
    output.write_bytes(b"partial output")

    class FakeStream:
        async def readline(self):
            await asyncio.Future()

    class FakeProcess:
        stdout = FakeStream()
        stderr = FakeStream()
        returncode = None
        terminated = False

        def terminate(self):
            self.terminated = True
            self.returncode = -15

        async def communicate(self):
            return b"", b""

        def kill(self):
            self.returncode = -9

    process = FakeProcess()

    async def create_process(*_args, **_kwargs):
        return process

    monkeypatch.setattr(render.asyncio, "create_subprocess_exec", create_process)

    async def scenario():
        task = asyncio.create_task(render.encode(["ffmpeg", str(output)], 1))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert process.terminated
    assert not output.exists()


def test_timeline_video_items_keep_and_apply_focus_crop():
    item = {
        "path": "/tmp/source.mp4", "sourceStart": 2, "duration": 8,
        "region": {"x": 0.2, "y": 0.15, "w": 0.5, "h": 0.7},
    }
    crop = render._crop_filter(item["region"])
    assert crop is not None and "crop=iw*0.5000:ih*0.7000" in crop
    assert render._crop_filter(None) is None


def test_media_file_download_uses_real_mp4_filename(tmp_path):
    target = tmp_path / "Creator edit auto_edited.mp4"
    target.write_bytes(b"fake mp4 bytes")
    response = client.get(
        "/media/file", headers=HEADERS,
        params={"path": str(target), "download": "true"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("video/mp4")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "auto_edited.mp4" in disposition
    assert response.content == b"fake mp4 bytes"


def test_media_stream_supports_suffix_ranges_for_safari_seeking(tmp_path):
    target = tmp_path / "video.mp4"
    target.write_bytes(b"0123456789")
    response = client.get(
        "/media/file", headers={**HEADERS, "Range": "bytes=-4"}, params={"path": str(target)},
    )
    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 6-9/10"
    assert response.content == b"6789"


def test_saved_clip_metadata_is_flattened_for_ui_and_preserved_in_editor_project(tmp_path):
    source = tmp_path / "candidate-source.mp4"
    source.write_bytes(b"source")
    media_id, clip_id, legacy_id = "testmedia515candidate", "testclip515candidate", "testclip515legacy"
    region = {"x": 0.2, "y": 0.1, "w": 0.5, "h": 0.8}
    second_region = {"x": 0.5, "y": 0.1, "w": 0.5, "h": 0.8}
    candidate = {
        "media_id": media_id, "start": 2, "end": 8, "score": 77,
        "title": "Focused moment", "reasons": ["high activity"], "hook": "",
        "hashtags": [], "transcript": "", "region": region, "regions": [region],
        "crop_path": [[2.0, 0.3], [5.0, 0.5], [8.0, 0.7]],
    }
    db.insert("media", {
        "id": media_id, "title": "Source", "path": str(source), "source_url": None,
        "duration": 10, "width": 640, "height": 360, "thumbnail": None,
        "playlist_id": None, "metadata": "{}", "created_at": now(),
    })
    for identifier, document in (
        (clip_id, candidate),
        (legacy_id, {
            "id": legacy_id, "metadata": candidate,
            "effects": {
                "aspect": "9:16", "region": region, "regions": [region, second_region],
                "region_layout": "side-by-side", "split_ratio": 0.71, "outline_style": "neon",
            },
        }),
    ):
        db.insert("clips", {
            "id": identifier, "project_id": None, "media_id": media_id,
            "start": 2, "end": 8, "score": 77, "title": "Focused moment", "reason": "high activity",
            "status": "proposed", "output": None, "metadata": dumps(document), "created_at": now(),
        })
    project_ids: list[str] = []
    try:
        response = client.get("/api/clips", headers=HEADERS)
        assert response.status_code == 200
        clips = {clip["id"]: clip for clip in response.json()["clips"]}
        assert clips[clip_id]["region"] == region
        assert clips[clip_id]["regions"] == [region]
        assert clips[clip_id]["crop_path"] == [[2.0, 0.3], [5.0, 0.5], [8.0, 0.7]]
        assert clips[clip_id]["reasons"] == ["high activity"]
        assert clips[legacy_id]["region"] == region
        assert clips[legacy_id]["effects"]["aspect"] == "9:16"
        assert clips[legacy_id]["regions"] == [region, second_region]
        assert clips[legacy_id]["region_layout"] == "side-by-side"
        assert clips[legacy_id]["split_ratio"] == 0.71
        assert clips[legacy_id]["outline_style"] == "neon"

        response = client.post("/api/projects", headers=HEADERS, json={"name": "Crop project", "clip_id": clip_id})
        assert response.status_code == 200
        project = response.json()["project"]
        project_ids.append(project["id"])
        item = project["timeline"]["tracks"]["video"][0]
        assert item["region"] == region and item["regions"] == [region]
        assert item["crop_path"] == [[2.0, 0.3], [5.0, 0.5], [8.0, 0.7]]

        response = client.post("/api/projects", headers=HEADERS, json={"name": "Effects project", "clip_id": legacy_id})
        assert response.status_code == 200
        project = response.json()["project"]
        project_ids.append(project["id"])
        legacy_item = project["timeline"]["tracks"]["video"][0]
        assert legacy_item["regions"] == [region, second_region]
        assert legacy_item["region_layout"] == "side-by-side"
        assert legacy_item["split_ratio"] == 0.71 and legacy_item["outline_style"] == "neon"
    finally:
        for project_id in project_ids:
            db.delete("projects", "id", project_id)
        db.delete("clips", "id", clip_id)
        db.delete("clips", "id", legacy_id)
        db.delete("media", "id", media_id)


def test_apply_effects_does_not_nest_or_drop_candidate_regions():
    clip_id = "testclip515effects"
    region = {"x": 0.1, "y": 0.2, "w": 0.6, "h": 0.7}
    db.insert("clips", {
        "id": clip_id, "project_id": None, "media_id": "missing-source",
        "start": 0, "end": 1, "score": 1, "title": "Effects", "reason": "",
        "status": "proposed", "output": None,
        "metadata": dumps({"region": region, "regions": [region], "reasons": []}), "created_at": now(),
    })
    try:
        response = client.post(
            "/api/clips/apply-effects", headers=HEADERS,
            json={
                "clip_ids": [clip_id], "effects": {"brightness": 0.1},
                "effects_by_clip": {clip_id: {"aspect": "16:9", "split_ratio": 0.7}},
            },
        )
        assert response.status_code == 200 and response.json()["changed"] == 1
        stored = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata")["metadata"]
        assert stored["region"] == region and stored["regions"] == [region]
        assert stored["effects"] == {"brightness": 0.1, "aspect": "16:9", "split_ratio": 0.7}
        assert "metadata" not in stored
    finally:
        db.delete("clips", "id", clip_id)


def test_patch_clip_persists_editable_social_caption():
    clip_id = "testclip515caption"
    db.insert("clips", {
        "id": clip_id, "project_id": None, "media_id": "missing-caption-source",
        "start": 0, "end": 1, "score": 1, "title": "Caption", "reason": "",
        "status": "proposed", "output": None,
        "metadata": dumps({"caption": "Initial copy", "transcript": "Original words."}),
        "created_at": now(),
    })
    try:
        response = client.patch(
            f"/api/clips/{clip_id}", headers=HEADERS,
            json={"caption": "  Revised social copy  "},
        )
        assert response.status_code == 200
        assert response.json()["clip"]["caption"] == "Revised social copy"
        stored = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata")
        assert stored["metadata"]["caption"] == "Revised social copy"
        assert stored["metadata"]["transcript"] == "Original words."
    finally:
        db.delete("clips", "id", clip_id)


def test_render_endpoint_uses_the_candidate_saved_crop_by_default(tmp_path, monkeypatch):
    source = tmp_path / "render-source.mp4"
    source.write_bytes(b"source")
    media_id, clip_id = "testmedia515render", "testclip515render"
    region = {"x": 0.15, "y": 0.1, "w": 0.55, "h": 0.75}
    db.insert("media", {
        "id": media_id, "title": "Render source", "path": str(source), "source_url": None,
        "duration": 10, "width": 640, "height": 360, "thumbnail": None,
        "playlist_id": None, "metadata": "{}", "created_at": now(),
    })
    db.insert("clips", {
        "id": clip_id, "project_id": None, "media_id": media_id,
        "start": 1, "end": 3, "score": 1, "title": "Render crop", "reason": "",
        "status": "proposed", "output": None,
        "metadata": dumps({
            "region": region, "regions": [region], "reasons": [],
            "crop_path": [[1.0, 0.3], [3.0, 0.7]],
        }), "created_at": now(),
    })
    captured = {}

    async def fake_render(_media, _start, _end, output, options, on_progress=None):
        captured["options"] = options
        return output

    monkeypatch.setattr(render, "render_clip", fake_render)
    monkeypatch.setattr(render, "export_path", lambda name: str(tmp_path / f"{name}.mp4"))
    monkeypatch.setattr(main_module, "hardware_info", lambda: {"encoder": "test"})
    previous_watermark = db.get_setting("watermark_path", "")
    db.set_setting("watermark_path", "")
    job_id = None
    try:
        response = client.post(
            f"/api/clips/{clip_id}/render", headers=HEADERS,
            json={"caption_style": {"preset": "none"}, "sfx": []},
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        job = None
        for _ in range(100):
            job = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
            if job["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.01)
        assert job and job["status"] == "done", job
        assert captured["options"]["region"] == region
        assert captured["options"]["crop_path"] == [[1.0, 0.3], [3.0, 0.7]]
        assert captured["options"]["contrast"] == 1.0
        assert captured["options"]["watermark_path"] is None
        saved = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata")["metadata"]
        assert saved["region"] == region and saved["hardware"]["encoder"] == "test"
        assert "metadata" not in saved
    finally:
        if job_id:
            db.delete("jobs", "id", job_id)
        db.delete("clips", "id", clip_id)
        db.delete("media", "id", media_id)
        db.set_setting("watermark_path", previous_watermark)


def test_render_endpoint_passes_the_saved_custom_watermark_to_new_exports(tmp_path, monkeypatch):
    source = tmp_path / "logo-render-source.mp4"
    source.write_bytes(b"source")
    logo = tmp_path / "channel-logo.png"
    logo.write_bytes(b"logo")
    media_id, clip_id = "testmedia515logo", "testclip515logo"
    db.insert("media", {
        "id": media_id, "title": "Logo source", "path": str(source), "source_url": None,
        "duration": 10, "width": 640, "height": 360, "thumbnail": None,
        "playlist_id": None, "metadata": "{}", "created_at": now(),
    })
    db.insert("clips", {
        "id": clip_id, "project_id": None, "media_id": media_id,
        "start": 1, "end": 3, "score": 1, "title": "Logo render", "reason": "",
        "status": "proposed", "output": None, "metadata": dumps({}), "created_at": now(),
    })
    captured = {}

    async def fake_render(_media, _start, _end, output, options, on_progress=None):
        captured["options"] = options
        return output

    monkeypatch.setattr(render, "render_clip", fake_render)
    monkeypatch.setattr(render, "export_path", lambda name: str(tmp_path / f"{name}.mp4"))
    monkeypatch.setattr(main_module, "hardware_info", lambda: {"encoder": "test"})
    previous_watermark = db.get_setting("watermark_path", "")
    db.set_setting("watermark_path", str(logo))
    job_id = None
    try:
        response = client.post(
            f"/api/clips/{clip_id}/render", headers=HEADERS,
            json={"caption_style": {"preset": "none"}, "sfx": []},
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        job = None
        for _ in range(100):
            job = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
            if job["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.01)
        assert job and job["status"] == "done", job
        assert captured["options"]["watermark_path"] == str(logo.resolve())
    finally:
        if job_id:
            db.delete("jobs", "id", job_id)
        db.delete("clips", "id", clip_id)
        db.delete("media", "id", media_id)
        db.set_setting("watermark_path", previous_watermark)


def test_publish_batch_render_uses_saved_crop_and_clip_effects(tmp_path, monkeypatch):
    source = tmp_path / "batch-source.mp4"
    source.write_bytes(b"source")
    media_id, clip_id = "testmedia515batch", "testclip515batch"
    region = {"x": 0.2, "y": 0.15, "w": 0.5, "h": 0.7}
    db.insert("media", {
        "id": media_id, "title": "Batch source", "path": str(source), "source_url": None,
        "duration": 10, "width": 640, "height": 360, "thumbnail": None,
        "playlist_id": None, "metadata": "{}", "created_at": now(),
    })
    db.insert("clips", {
        "id": clip_id, "project_id": None, "media_id": media_id,
        "start": 1, "end": 3, "score": 1, "title": "Batch crop", "reason": "",
        "status": "proposed", "output": None,
        "metadata": dumps({"region": region, "regions": [region], "reasons": [], "effects": {"aspect": "16:9", "brightness": 0.1, "contrast": 0.05}}),
        "created_at": now(),
    })
    captured = {}

    async def fake_render(_media, _start, _end, output, options, on_progress=None):
        captured["options"] = options
        return output

    monkeypatch.setattr(render, "render_clip", fake_render)
    monkeypatch.setattr(render, "export_path", lambda name: str(tmp_path / f"{name}.mp4"))
    monkeypatch.setattr(main_module, "hardware_info", lambda: {"workers": 1, "encoder": "test"})
    previous_watermark = db.get_setting("watermark_path", "")
    db.set_setting("watermark_path", "")
    job_id = None
    try:
        response = client.post("/api/exports/batch", headers=HEADERS, json={"clip_ids": [clip_id]})
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        job = None
        for _ in range(100):
            job = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
            if job["status"] in {"done", "error", "cancelled"}:
                break
            time.sleep(0.01)
        assert job and job["status"] == "done", job
        assert captured["options"]["region"] == region
        assert captured["options"]["aspect"] == "16:9"
        assert captured["options"]["brightness"] == 0.1
        assert captured["options"]["contrast"] == 1.05
        assert captured["options"]["watermark_path"] is None
    finally:
        if job_id:
            db.delete("jobs", "id", job_id)
        db.delete("clips", "id", clip_id)
        db.delete("media", "id", media_id)
        db.set_setting("watermark_path", previous_watermark)


def test_delete_media_removes_download_but_preserves_imported_source(tmp_path):
    downloaded = tmp_path / "downloaded.mp4"
    imported = tmp_path / "imported.mp4"
    downloaded.write_bytes(b"download")
    imported.write_bytes(b"import")
    download_id, import_id = "testmedia515dl", "testmedia515im"
    for media_id, path, source in (
        (download_id, downloaded, "https://example.test/video"),
        (import_id, imported, None),
    ):
        db.insert("media", {
            "id": media_id, "title": media_id, "path": str(path), "source_url": source,
            "duration": 1, "width": 16, "height": 9, "thumbnail": None,
            "playlist_id": None, "metadata": "{}", "created_at": now(),
        })
    try:
        response = client.delete(f"/api/media/{download_id}?delete_file=true", headers=HEADERS)
        assert response.status_code == 200 and response.json()["file_deleted"] is True
        assert not downloaded.exists()
        response = client.delete(f"/api/media/{import_id}?delete_file=true", headers=HEADERS)
        assert response.status_code == 200 and response.json()["file_deleted"] is False
        assert imported.exists()
    finally:
        db.delete("media", "id", download_id)
        db.delete("media", "id", import_id)


def test_delete_media_keeps_source_that_another_library_item_uses(tmp_path):
    source = tmp_path / "shared-download.mp4"
    source.write_bytes(b"shared media")
    download_id, alias_id = "testmedia515shared", "testmedia515alias"
    for media_id, source_url in ((download_id, "https://example.test/shared"), (alias_id, None)):
        db.insert("media", {
            "id": media_id, "title": media_id, "path": str(source), "source_url": source_url,
            "duration": 1, "width": 16, "height": 9, "thumbnail": None,
            "playlist_id": None, "metadata": "{}", "created_at": now(),
        })
    try:
        response = client.delete(f"/api/media/{download_id}?delete_file=true", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["file_deleted"] is False
        assert response.json()["file_kept_shared"] is True
        assert source.exists()
    finally:
        db.delete("media", "id", download_id)
        db.delete("media", "id", alias_id)


def test_delete_media_keeps_source_still_used_by_saved_project(tmp_path):
    source = tmp_path / "project-source.mp4"
    source.write_bytes(b"project media")
    media_id, project_id = "testmedia515project", "testproject515source"
    db.insert("media", {
        "id": media_id, "title": media_id, "path": str(source), "source_url": "https://example.test/project",
        "duration": 1, "width": 16, "height": 9, "thumbnail": None,
        "playlist_id": None, "metadata": "{}", "created_at": now(),
    })
    db.insert("projects", {
        "id": project_id, "name": project_id,
        "data": dumps({"timeline": {"tracks": {"video": [{"path": str(source)}]}}}),
        "created_at": now(), "updated_at": now(),
    })
    try:
        response = client.delete(f"/api/media/{media_id}?delete_file=true", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["file_kept_shared"] is True
        assert source.exists()
    finally:
        db.delete("media", "id", media_id)
        db.delete("projects", "id", project_id)


def test_delete_media_keeps_source_still_used_by_rendered_clip(tmp_path):
    source = tmp_path / "rendered-clip-source.mp4"
    source.write_bytes(b"clip source")
    media_id, clip_id = "testmedia515clipref", "testclip515sourceref"
    db.insert("media", {
        "id": media_id, "title": media_id, "path": str(source), "source_url": "https://example.test/clip-source",
        "duration": 1, "width": 16, "height": 9, "thumbnail": None,
        "playlist_id": None, "metadata": "{}", "created_at": now(),
    })
    db.insert("clips", {
        "id": clip_id, "project_id": None, "media_id": media_id,
        "start": 0, "end": 1, "score": 1, "title": "Rendered clip", "reason": "",
        "status": "rendered", "output": str(tmp_path / "rendered-output.mp4"),
        "metadata": dumps({}), "created_at": now(),
    })
    try:
        response = client.delete(f"/api/media/{media_id}?delete_file=true", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["file_deleted"] is False
        assert response.json()["file_kept_shared"] is True
        assert source.exists()
        assert db.one("SELECT id FROM clips WHERE id=?", (clip_id,)) is not None
    finally:
        db.delete("clips", "id", clip_id)
        db.delete("media", "id", media_id)


def test_publish_bulk_delete_removes_records_and_owned_mp4(tmp_path):
    previous = db.get_setting("clips_folder", "")
    db.set_setting("clips_folder", str(tmp_path))
    output = tmp_path / "generated_clip.mp4"
    output.write_bytes(b"fake mp4")
    clip_id = "testclip515bulk"
    db.insert("clips", {
        "id": clip_id, "project_id": None, "media_id": "missing-source",
        "start": 0, "end": 1, "score": 1, "title": "Test clip", "reason": "",
        "status": "rendered", "output": str(output), "metadata": dumps({}), "created_at": now(),
    })
    try:
        response = client.request("DELETE", "/api/clips/bulk-delete", headers=HEADERS, json={"clip_ids": [clip_id]})
        assert response.status_code == 200
        assert response.json()["deleted"] == 1
        assert response.json()["files_deleted"] == 1
        assert not output.exists()
        assert db.one("SELECT id FROM clips WHERE id=?", (clip_id,)) is None
    finally:
        db.delete("clips", "id", clip_id)
        db.set_setting("clips_folder", previous)


def test_clip_delete_keeps_shared_output_until_last_clip_is_removed(tmp_path):
    previous = db.get_setting("clips_folder", "")
    db.set_setting("clips_folder", str(tmp_path))
    output = tmp_path / "shared-export.mp4"
    output.write_bytes(b"shared export")
    first_id, second_id = "testclip515first", "testclip515second"
    for clip_id in (first_id, second_id):
        db.insert("clips", {
            "id": clip_id, "project_id": None, "media_id": "missing-source",
            "start": 0, "end": 1, "score": 1, "title": clip_id, "reason": "",
            "status": "rendered", "output": str(output), "metadata": dumps({}), "created_at": now(),
        })
    try:
        response = client.delete(f"/api/clips/{first_id}", headers=HEADERS)
        assert response.status_code == 200 and response.json()["file_deleted"] is False
        assert output.exists()
        response = client.delete(f"/api/clips/{second_id}", headers=HEADERS)
        assert response.status_code == 200 and response.json()["file_deleted"] is True
        assert not output.exists()
    finally:
        db.delete("clips", "id", first_id)
        db.delete("clips", "id", second_id)
        db.set_setting("clips_folder", previous)


def test_select_existing_sdxl_checkpoint_without_redownloading(tmp_path, monkeypatch):
    checkpoint_dir = tmp_path / "ComfyUI" / "models" / "checkpoints"
    monkeypatch.setattr(models, "_comfy_checkpoints_dir", lambda: checkpoint_dir)
    source = tmp_path / "Downloads" / "custom-sdxl.safetensors"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"weights" * 100)
    keys = ("comfy_checkpoint", "comfy_checkpoint_path", "installed_models", "image_provider")
    previous = {key: db.get_setting(key, "") for key in keys}
    try:
        result = models.configure_comfy_checkpoint(str(source))
        target = checkpoint_dir / source.name
        assert result["filename"] == source.name
        assert target.exists()
        assert target.samefile(source)
        assert db.get_setting("comfy_checkpoint") == source.name
        assert db.get_setting("comfy_checkpoint_path") == str(target)
    finally:
        for key, value in previous.items():
            db.set_setting(key, value)
        (checkpoint_dir / source.name).unlink(missing_ok=True)


def test_new_operation_routes_are_registered():
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/jobs/{job_id}/cancel" in paths
    assert "/api/clips/bulk-delete" in paths
    assert "/api/models/comfyui-checkpoint" in paths


def test_custom_watermark_setting_is_optional_and_checks_the_selected_file(tmp_path):
    previous = db.get_setting("watermark_path", "")
    logo = tmp_path / "channel.png"
    logo.write_bytes(b"logo")
    try:
        db.set_setting("watermark_path", "")
        assert main_module.configured_watermark_path() is None
        db.set_setting("watermark_path", str(logo))
        assert main_module.configured_watermark_path() == str(logo.resolve())
        db.set_setting("watermark_path", str(tmp_path / "missing.png"))
        assert main_module.configured_watermark_path() is None
        db.set_setting("watermark_path", str(tmp_path / "not-an-image.exe"))
        assert main_module.configured_watermark_path() is None
    finally:
        db.set_setting("watermark_path", previous)


def test_job_cancel_from_worker_thread_stops_async_work():
    manager = JobManager()

    async def scenario():
        started = asyncio.Event()
        stopped = asyncio.Event()

        async def work(_job_id, _payload):
            started.set()
            try:
                await asyncio.Future()
            finally:
                stopped.set()

        job_id = manager.run("test-cancel", work)
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            assert await asyncio.to_thread(manager.cancel, job_id)
            await asyncio.wait_for(stopped.wait(), timeout=2)
            await asyncio.sleep(0)
            assert manager.get(job_id)["status"] == "cancelled"
        finally:
            if manager.get(job_id) and manager.get(job_id)["status"] in {"queued", "running"}:
                manager.cancel(job_id)
            db.delete("jobs", "id", job_id)

    asyncio.run(scenario())

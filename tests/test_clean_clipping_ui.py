"""Real four-destination native UI and automatic clipping acceptance."""

from pathlib import Path
import time
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest

from clipos.core.config import AppPaths
from clipos.db.database import Database
from clipos.ui.main_window import MainWindow
from clipos.ui.pages.video_clipper import clipping_settings
from clipos.video.crop_config import CropConfig, load_crop
from clipos.video.clean_clipping import generate_clips
from tests.test_crop_config import source, decode


def wait(app, page):
    deadline = time.monotonic() + 15
    while page._pending and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(5)
    app.processEvents()
    assert not page._pending, page.status.text()


@pytest.fixture
def native(tmp_path, monkeypatch):
    from clipos.core import config

    paths = AppPaths(tmp_path / "data")
    paths.ensure()
    # Existing modules share this object in production. Override module references
    # in tests so decoding/exports never touch the developer's real library.
    for module in (
        "clipos.ui.main_window",
        "clipos.ui.pages.video_clipper",
        "clipos.ui.pages.essential_settings",
        "clipos.ui.pages.models",
        "clipos.ai.model_manager",
        "clipos.video.pipeline",
        "clipos.video.importer",
        "clipos.ai.transcription",
    ):
        monkeypatch.setattr(module + ".PATHS", paths)
    app = QApplication.instance() or QApplication([])
    db = Database(tmp_path / "ui.db")
    db.set_setting("restore_on_launch", False)
    window = MainWindow(db)
    window.show()
    app.processEvents()
    try:
        yield app, db, window, paths
    finally:
        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ):
            window.close()
        app.processEvents()
        db.close()


def test_core_routes_and_integrated_studio_without_retired_feature_construction(native):
    app, db, window, _ = native
    assert set(window.pages) == {"clipper"}
    assert set(window.nav_buttons) == {
        "clipper",
        "library",
        "models",
        "settings",
        "studio",
    }
    for key in (
        "home",
        "workflow",
        "editor",
        "multitrack",
        "captions",
        "templates",
        "export",
        "projects",
    ):
        window.navigate(key)
        assert window.current_key == "clipper"
    for key in window.nav_buttons:
        window.navigate(key)
        app.processEvents()
        assert window.current_key == key
    assert not hasattr(window, "open_in_editor")
    window._toggle_sidebar()
    assert db.get_setting("sidebar_collapsed") is True


def test_crop_is_saved_and_aspect_changes_do_not_compound_or_inherit_old_recipes(
    native, tmp_path
):
    app, db, window, _ = native
    page = window.pages["clipper"]
    video = source(tmp_path, 320, 180)
    pid = db.create_project(
        name="Source", source_path=str(video), width=320, height=180, duration=2
    )
    page.load_project(pid)
    wait(app, page)
    page.aspect.setCurrentText("1:1")
    page._selection((0.5, 0, 0.5, 1))
    original = page.config
    assert original == load_crop(db, pid)
    page.aspect.setCurrentText("16:9")
    page.aspect.setCurrentText("1:1")
    assert page.config == original
    db.set_settings(
        {
            "editing_preset": "gaming",
            "auto_caption": True,
            "body_reframe": True,
            "background_music": "missing.mp3",
        }
    )
    settings = clipping_settings(original, db)
    assert (
        not settings.smart_reframe
        and not settings.show_captions
        and not settings.background_music
    )
    assert settings.crop_config == original.to_dict()
    page.load_project(pid)
    wait(app, page)
    assert page.config == original
    assert page.canvas.regions["crop"] == original.normalized


def test_real_clean_analysis_to_crop_export_and_library_preserves_previous_runs(
    native, tmp_path
):
    app, db, window, paths = native
    video = source(tmp_path, 320, 180)
    pid = db.create_project(
        name="Real clean crop",
        source_path=str(video),
        width=320,
        height=180,
        duration=2,
    )
    crop = CropConfig.from_selection((0.5, 0, 0.5, 1), 320, 180, "1:1", (128, 128))
    settings = clipping_settings(crop, db)
    settings.encoder_preference = "cpu"
    settings.threads = 2
    for run in range(2):
        result = generate_clips(
            db, pid, crop, paths.exports, count=1, duration="15-30", settings=settings
        )
        assert len(result) == 1 and not result[0].get("error"), result
        assert decode(result[0]["output_path"])[:, :, 0].mean() > 230
    assert len(db.list_clips(pid)) == 2
    assert len({row["output_path"] for row in db.list_clips(pid)}) == 2
    window.navigate("library")
    assert window.pages["library"].grid.count() == 2


def test_explicit_speech_model_missing_stops_without_download_or_silent_fallback(
    native, tmp_path
):
    app, db, window, paths = native
    video = source(tmp_path, 320, 180)
    pid = db.create_project(
        name="Missing model", source_path=str(video), width=320, height=180, duration=2
    )
    crop = CropConfig.from_selection((0, 0, 1, 1), 320, 180, "9:16")
    with (
        patch("clipos.ai.transcription.model_installed", return_value=False),
        patch("clipos.ai.transcription.download_whisper_model") as download,
    ):
        with pytest.raises(ValueError, match="no silent"):
            generate_clips(db, pid, crop, paths.exports, speech=True)
        download.assert_not_called()
    assert not db.list_clips(pid)


def test_studio_twenty_queue_entries_real_media_import_split_and_reopen(
    native, tmp_path
):
    """20 DB queue entries reference real fixture media; not 20 AI-generated clips."""
    from clipos.video.multitrack import MultitrackProject

    app, db, window, paths = native
    video = source(tmp_path, 320, 180)
    pid = db.create_project(name="Queue acceptance", source_path=str(video), duration=2)
    window.navigate("studio")
    page = window.pages["studio"]
    assert page.queue.rowCount() == 0
    for index in range(20):
        db.create_clip(
            project_id=pid,
            title=f"Clip {index + 1}",
            output_path=str(video),
            duration=2,
        )
    window.data_changed.emit()
    assert page.queue.rowCount() == 20
    page.queue.selectAll()
    page.add_selected()
    deadline = time.monotonic() + 15
    while page.worker.isRunning() and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(5)
    app.processEvents()
    assert len(page.project.media) == 20
    assert page.project.duration == pytest.approx(40)
    lane = page.project.lanes[0]
    item = lane.items[0]
    page.project.split(lane.id, item.id, 1, linked=True)
    page.draw_timeline()
    assert len(page.project.lanes[0].items) == 2
    saved = tmp_path / "assembly.json"
    page.project.save(saved)
    assert MultitrackProject.load(saved).to_dict() == page.project.to_dict()
    assert video.is_file()


def test_studio_track_controls_waveforms_and_actual_timeline_preview(native, tmp_path):
    from clipos.core.ffmpeg import probe
    from clipos.video.multitrack import MultitrackProject

    app, db, window, paths = native
    video = source(tmp_path, 320, 180)
    window.navigate("studio")
    page = window.pages["studio"]
    page.project = MultitrackProject(width=160, height=90, fps=10)
    page.project.import_media(video)
    page.draw_timeline()
    node = page.timeline.topLevelItem(0)
    page.timeline.setCurrentItem(node)
    page.toggle_track("locked")
    assert page.project.lanes[0].locked
    page.toggle_track("locked")
    page.toggle_track("enabled")
    assert not page.project.lanes[0].enabled
    page.toggle_track("enabled")
    captured = []
    with patch(
        "PySide6.QtGui.QDesktopServices.openUrl",
        side_effect=lambda url: captured.append(url.toLocalFile()),
    ):
        page.render_preview()
        deadline = time.monotonic() + 20
        while page.worker.isRunning() and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(5)
        app.processEvents()
    assert not page.worker.isRunning()
    assert "Rendered timeline snapshot" in page.status.text(), page.status.text()
    # Headless runner uses system-player fallback; on multimedia-capable hosts
    # inspect the source actually loaded by QMediaPlayer instead.
    output = page.player.source().toLocalFile() if page.player else captured[-1]
    info = probe(output)
    assert (info.video.width, info.video.height) == (160, 90)
    assert info.has_audio
    from clipos.video.waveform import build_waveform

    waveform = build_waveform(output, tmp_path / "waveforms")
    assert waveform["duration"] > 0
    assert len(waveform["peaks"]) > 0
    Path(output).unlink(missing_ok=True)


def test_studio_selective_batch_group_and_future_import_settings(native, tmp_path):
    from clipos.video.multitrack import MultitrackProject
    from clipos.video.editing_preset import EditingPreset

    app, db, window, paths = native
    video = source(tmp_path, 320, 180)
    pid = db.create_project(name="Selective edits", source_path=str(video), duration=2)
    first = db.create_clip(
        project_id=pid, title="A", output_path=str(video), duration=2
    )
    second = db.create_clip(
        project_id=pid, title="B", output_path=str(video), duration=2
    )
    window.navigate("studio")
    page = window.pages["studio"]
    page.project = MultitrackProject(width=160, height=90, fps=10)
    page.project.import_media(video, queue_clip_id=first)
    page.project.import_media(video, at=2, queue_clip_id=second)
    page.queue_manager.group([first], "Interview")
    page.draw_timeline()
    page.refresh()
    panel = page.editing
    panel.scope.setCurrentIndex(panel.scope.findData("group"))
    panel.group.setText("Interview")
    panel.fields["brightness"].setValue(0.2)
    panel.apply()
    video_items = [
        i for lane in page.project.lanes if lane.kind == "video" for i in lane.items
    ]
    assert video_items[0].brightness == 0.2 and video_items[1].brightness == 0
    panel.scope.setCurrentIndex(panel.scope.findData("all"))
    panel.apply()
    assert all(
        i.brightness == 0.2
        for lane in page.project.lanes
        if lane.kind == "video"
        for i in lane.items
    )
    panel.set_future()
    incoming = MultitrackProject.from_dict(page.project.to_dict())
    new_id = incoming.import_media(video, at=4, queue_clip_id=second)
    panel.fields["brightness"].setValue(0.4)  # saved future preset remains .2
    page._imported(incoming.to_dict())
    assert (
        page.project.find(
            page.project.lanes[-1].id, page.project.lanes[-1].items[0].id
        )[1].brightness
        == 0.2
    )
    assert page.project.media[-1].id == new_id
    panel.clear_future()


def test_native_caption_correction_keeps_word_timing_and_is_undoable(native):
    app, db, window, paths = native
    window.navigate("studio")
    page = window.pages["studio"]
    lane_id, item_id = page.project.add_caption("hello world", 0, 2)
    page.project.change_item(
        lane_id,
        item_id,
        caption_words=[
            {"w": "hello", "s": 0.0, "e": 0.8},
            {"w": "world", "s": 1.0, "e": 1.8},
        ],
    )
    page.draw_timeline()
    page.timeline.setCurrentItem(page.timeline.topLevelItem(0).child(0))
    panel = page.captions
    panel.read()
    assert panel.words.rowCount() == 2
    panel.words.item(0, 0).setText("namaste")
    panel.text.setText("namaste world")
    panel.start.setValue(1)
    panel.apply()
    item = page.project.find(lane_id, item_id)[1]
    assert item.text == "namaste world" and item.at == 1
    assert item.caption_words[0]["w"] == "namaste"
    assert page.project.undo()
    assert page.project.find(lane_id, item_id)[1].text == "hello world"


def test_native_batch_dashboard_renders_actual_queue_item(native, tmp_path):
    from clipos.video.multitrack import MultitrackProject
    from clipos.core.ffmpeg import probe

    app, db, window, paths = native
    video = source(tmp_path, 160, 90)
    pid = db.create_project(name="Batch", source_path=str(video), duration=2)
    cid = db.create_clip(
        project_id=pid, title="Clip", output_path=str(video), duration=2
    )
    window.navigate("studio")
    page = window.pages["studio"]
    page.project = MultitrackProject(width=160, height=90, fps=10)
    page.project.import_media(video, queue_clip_id=cid)
    page.draw_timeline()
    panel = page.batch
    panel.folder.setText(str(tmp_path))
    panel.encoder.setCurrentIndex(panel.encoder.findData("cpu"))
    panel.start(True)
    deadline = time.monotonic() + 20
    while page.worker.isRunning() and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(5)
    app.processEvents()
    assert panel.jobs[0].status == "completed", page.status.text()
    assert panel.table.item(0, 1).text() == "completed"
    assert "Completed 1" in panel.summary.text()
    assert probe(panel.jobs[0].output).has_audio
    assert panel.manifest.is_file()

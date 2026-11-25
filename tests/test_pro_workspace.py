"""3.5 native navigation and real-render regression coverage."""
from pathlib import Path

from PySide6.QtWidgets import QApplication

from clipos.db.database import Database
from clipos.ui.main_window import MainWindow


def test_all_destinations_and_sidebar_persistence(tmp_path):
    app = QApplication.instance() or QApplication([])
    db = Database(tmp_path / 'navigation.db')
    db.create_project(name='Local project', duration=12, width=1920, height=1080)
    window = MainWindow(db)
    try:
        assert len(window.nav_buttons) == 10
        for destination in window._page_classes:
            window.navigate(destination)
            assert window.current_key == destination
        window._toggle_sidebar()
        assert window.sidebar.width() == 68
        assert db.get_setting('sidebar_collapsed') is True
        window._toggle_sidebar()
        assert db.get_setting('sidebar_collapsed') is False
        window.navigate('projects')
        page = window.pages['projects']
        page.search.setText('Local')
        page.sort.setCurrentIndex(1)
        assert page._list_layout.count() == 1
        page.filter.setCurrentIndex(2)
        assert page._list_layout.count() == 1  # genuine empty-state label
        assert page._list_layout.itemAt(0).widget().text() == 'No projects match your search.'
        window.navigate('home')
        page = window.pages['home']
        page.instruction.setText('Create 10 clips')
        page._director()
        assert window.pages['workflow'].agent_instruction.text() == 'Create 10 clips'
        assert 'Import or open' in window.pages['workflow'].status.text()
    finally:
        window.close()
        app.processEvents()
        db.close()


def test_caption_preview_is_a_real_ffmpeg_frame():
    from clipos.ui.pages.caption_studio import CaptionRenderWorker
    from clipos.core.ffmpeg import ffmpeg_available
    import pytest
    if not ffmpeg_available():
        pytest.skip('FFmpeg unavailable')
    result, errors = [], []
    worker = CaptionRenderWorker('bold_viral', {})
    worker.ready.connect(result.append)
    worker.failed.connect(errors.append)
    worker.run()
    assert not errors, errors
    assert result and result[0].startswith(b'\x89PNG\r\n\x1a\n')


def test_system_theme_resolves_and_preserves_preference(tmp_path):
    from clipos.ui.theme import apply_theme
    app = QApplication.instance() or QApplication([])
    db = Database(tmp_path / 'theme.db')
    window = MainWindow(db)
    try:
        db.set_setting('theme', 'system')
        apply_theme(window, 'system')
        assert db.get_setting('theme') == 'system'
        assert window.styleSheet()
    finally:
        window.close()
        app.processEvents()
        db.close()

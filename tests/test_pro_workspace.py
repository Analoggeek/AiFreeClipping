"""3.5 native navigation and real-render regression coverage."""
from pathlib import Path

from PySide6.QtWidgets import QApplication

from clipos.db.database import Database
from clipos.ui.main_window import MainWindow






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

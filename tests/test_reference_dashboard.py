"""Native reference layout uses existing data/actions, never invented readiness."""
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QBoxLayout

from clipos.db.database import Database
from clipos.ui.main_window import MainWindow
from tests.test_multitrack import media


@pytest.fixture
def native(tmp_path):
    app=QApplication.instance() or QApplication([])
    db=Database(tmp_path/'reference.db');window=MainWindow(db)
    window.resize(1568,1100);window.show();app.processEvents()
    try:yield app,db,window
    finally:window.close();app.processEvents();db.close()

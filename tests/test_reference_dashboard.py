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


def test_dashboard_styles_sync_settings_and_preserve_explicit_import(native):
    app,db,window=native;page=window.pages['workflow']
    assert page.stack.currentIndex()==0 and not page.steps_bar.isVisible()
    page.quick_style_buttons['Podcast'][0].click()
    assert db.get_setting('editing_preset')=='podcast'
    assert page.quick_style_buttons['Podcast'][0].isChecked()
    db.set_setting('editing_preset','cinematic');page.refresh()
    assert page.quick_style_buttons['Cinematic'][0].isChecked()
    assert not page.quick_style_buttons['Podcast'][0].isChecked()
    app.clipboard().setText('https://example.com/authorised.mp4')
    with patch.object(page,'_import') as importer:
        page._paste_link()
        assert page.source.text()=='https://example.com/authorised.mp4'
        importer.assert_not_called()
    assert 'not checked' in page.director_status.text()
    assert 'Inference quality requires' in page.model_summary.text()


def test_dashboard_stacks_at_narrow_width_and_guards_project_steps(native):
    app,db,window=native;page=window.pages['workflow']
    page.resize(950,900);app.processEvents()
    assert page.dashboard_columns.direction()==QBoxLayout.Direction.TopToBottom
    page.go(2)
    assert page.stack.currentIndex()==0
    assert 'Import or open a project first' in page.status.text()
    page.resize(1400,900);app.processEvents()
    assert page.dashboard_columns.direction()==QBoxLayout.Direction.LeftToRight


def test_media_bin_uses_real_metadata_and_selects_existing_item(native,media):
    app,db,window=native;window.navigate('multitrack');page=window.pages['multitrack']
    assert page.media_bin.count()==0
    page.project.import_media(media[0],at=1);page._rebuild()
    assert page.media_bin.count()==1
    entry=page.media_bin.item(0)
    assert entry.data(Qt.ItemDataRole.UserRole)==page.project.media[0].id
    assert entry.toolTip()==page.project.media[0].path
    with patch.object(page,'_seek') as seek:
        page._activate_media(entry)
        seek.assert_called_with(1)
    assert page._selected() in page._rows
    page._new();assert page.media_bin.count()==0


def test_settings_section_navigation_preserves_preferences(native):
    app,db,window=native;window.navigate('settings');page=window.pages['settings']
    before=db.get_settings()
    assert len(page.section_links)==9
    for button in page.section_links.values():button.click()
    assert db.get_settings()==before

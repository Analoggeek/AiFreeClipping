"""Regressions for user-reported crop, preset reset and blocked delivery issues."""
from pathlib import Path
from unittest.mock import patch
import hashlib
import time
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage,QColor,QPixmap
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from clipos.db.database import Database
from clipos.core.ffmpeg import ffmpeg_available,run_ffmpeg,probe,extract_thumbnail


def test_delivery_rejects_a_clip_from_a_different_project(tmp_path,video):
    from clipos.video.delivery import deliver_clips
    db=Database(tmp_path/'delivery.db')
    try:
        pid=db.create_project(name='Current',source_path=str(video))
        other=db.create_project(name='Other',source_path=str(video))
        cid=db.create_clip(project_id=other,title='Other',output_path=str(video),status='rendered')
        result=deliver_clips(db,pid,[cid],tmp_path/'exports')
        assert result['results'][0]['error']=='Clip belongs to a different project'
        assert not list(Path(result['output_dir']).glob('*.mp4'))
    finally:db.close()

@pytest.fixture
def video(tmp_path):
    source=tmp_path/'source.mp4';source.write_bytes(b'not decoded by delivery ownership check');return source

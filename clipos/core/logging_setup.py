"""Logging configuration for CLIPOS.

Rotating file logs in the app data dir plus a readable console stream. Errors are also
mirrored into the ``app_errors`` SQLite table so the UI can surface them.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from .config import PATHS

_CONFIGURED = False
_FMT = "%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s"


def setup_logging(level: int = logging.INFO) -> Path:
    global _CONFIGURED
    PATHS.ensure()
    log_file = PATHS.logs / "clipos.log"
    root = logging.getLogger()
    if _CONFIGURED:
        return log_file

    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)

    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=4 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FMT))
    root.addHandler(fh)

    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(level)
    sh.setFormatter(logging.Formatter(_FMT))
    root.addHandler(sh)

    # Third party noise control
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    _CONFIGURED = True
    return log_file


def get_logger(name: str) -> logging.Logger:
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)

"""Choose an available native macOS media backend before Qt multimedia loads.

Rosetta Intel builds can fail to initialize Qt's FFmpeg video decoder even when
all wheel slices match. AVFoundation is Qt's supported native macOS backend.
An explicit user QT_MEDIA_BACKEND override always wins. Other OSes are unchanged.
"""
import os
import sys


def configure():
    if sys.platform=='darwin':
        os.environ.setdefault('QT_MEDIA_BACKEND','darwin')
    return os.environ.get('QT_MEDIA_BACKEND','')

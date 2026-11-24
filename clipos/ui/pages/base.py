"""Base class shared by every CLIPOS page."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from ...core.logging_setup import get_logger
from ..theme import Metrics

log = get_logger(__name__)


class BasePage(QWidget):
    """A scrollable page with a title header.

    Subclasses set ``page_title`` / ``page_subtitle`` and implement ``build()``
    and optionally ``refresh()``.
    """

    navigated = Signal(str)
    page_title = "Page"
    page_subtitle = ""
    subtitle_text = ""

    def __init__(self, window) -> None:
        super().__init__()
        self.window = window
        self.db = window.db
        self._built = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)

        self.container = QWidget()
        self.container.setObjectName("PageSurface")
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(Metrics.xl, Metrics.xl, Metrics.xl, Metrics.xxl)
        self.layout.setSpacing(Metrics.lg)
        self.scroll.setWidget(self.container)

        self.header = self._build_header()
        self.layout.addWidget(self.header)

        self.content = QWidget()
        self.content.setObjectName("PageContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(Metrics.lg)
        self.layout.addWidget(self.content)

        self.layout.addStretch(1)
        self.build()
        self._built = True

    def _build_header(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self.title_label = self._label(self.page_title, "PageTitle")
        lay.addWidget(self.title_label)

        self.subtitle_label = self._label(self.page_subtitle, "PageSubtitle")
        self.subtitle_label.setWordWrap(True)
        lay.addWidget(self.subtitle_label)

        self.subtitle_text = self.page_subtitle
        return w

    @staticmethod
    def _label(text: str, object_name: str) -> "QWidget":
        from PySide6.QtWidgets import QLabel

        lbl = QLabel(text)
        lbl.setObjectName(object_name)
        return lbl

    def build(self) -> None:
        """Construct the page contents. Overridden by subclasses."""

    def refresh(self) -> None:
        """Reload data from the database. Overridden by subclasses."""

    def navigate(self, key: str) -> None:
        self.navigated.emit(key)

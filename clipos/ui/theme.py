"""CLIPOS design system: colour palettes, metrics and the Qt stylesheet.

Two themes (dark / light) built around a macOS-inspired desktop aesthetic:
translucent sidebar, soft elevation, rounded corners and restrained accent colour.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QFontDatabase


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    bg_elevated: str
    bg_panel: str
    bg_sidebar: str
    bg_input: str
    bg_hover: str
    bg_active: str
    text: str
    text_dim: str
    text_faint: str
    border: str
    border_strong: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    warning: str
    danger: str
    info: str
    shadow: str
    gradient_a: str
    gradient_b: str


DARK = Palette(
    name="dark",
    bg="#0e121a",
    bg_elevated="#181d26",
    bg_panel="#1b2432",
    bg_sidebar="#111925",
    bg_input="#131821",
    bg_hover="#29313e",
    bg_active="#243a42",
    text="#f2f2f5",
    text_dim="#b3bfd1",
    text_faint="#8993a5",
    border="#29313e",
    border_strong="#3c495b",
    accent="#6ee7ce",
    accent_hover="#83e6d1",
    accent_text="#102820",
    success="#32d74b",
    warning="#ff9f0a",
    danger="#ff453a",
    info="#5e5ce6",
    shadow="rgba(0, 0, 0, 160)",
    gradient_a="#101319",
    gradient_b="#0c1016",
)

LIGHT = Palette(
    name="light",
    bg="#f2f2f5",
    bg_elevated="#ffffff",
    bg_panel="#ffffff",
    bg_sidebar="#ececed",
    bg_input="#ffffff",
    bg_hover="#e6e6ea",
    bg_active="#dcdce2",
    text="#101319",
    text_dim="#5b5b63",
    text_faint="#707783",
    border="#dcdce0",
    border_strong="#c4c4cb",
    accent="#007aff",
    accent_hover="#3395ff",
    accent_text="#ffffff",
    success="#248a3d",
    warning="#c93400",
    danger="#d70015",
    info="#5e5ce6",
    shadow="rgba(0, 0, 0, 60)",
    gradient_a="#f6f6f8",
    gradient_b="#ececee",
)


PALETTES = {"dark": DARK, "light": LIGHT}


class Metrics:
    """Spacing / radius scale."""
    xs, sm, md, lg, xl, xxl = 4, 8, 12, 16, 24, 32
    radius_sm, radius, radius_lg, radius_xl = 6, 10, 14, 20
    sidebar_width = 236
    titlebar_height = 38
    row_height = 30


def ui_font(size: int = 13, weight: int = 400, family: str = "") -> QFont:
    """Build a UI font using a system font stack that exists on macOS/Windows."""
    families = [family] if family else []
    families += [
        ".AppleSystemUIFont", "SF Pro Text", "Segoe UI Variable Text", "Segoe UI",
        "Helvetica Neue", "Inter", "DejaVu Sans", "Arial",
    ]
    f = QFont()
    f.setFamilies([x for x in families if x])
    f.setPointSize(size)
    f.setWeight(QFont.Weight(weight) if isinstance(weight, int) else weight)
    f.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return f


def mono_font(size: int = 12) -> QFont:
    f = QFont()
    f.setFamilies(["SF Mono", "JetBrains Mono", "Cascadia Mono", "Menlo",
                   "Consolas", "DejaVu Sans Mono", "monospace"])
    f.setPointSize(size)
    return f


def qcolor(hex_str: str, alpha: int = 255) -> QColor:
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


def stylesheet(p: Palette) -> str:
    """The full application stylesheet for a palette."""
    m = Metrics
    return f"""
/* ---------- base ---------- */
QWidget {{
    background-color: {p.bg};
    color: {p.text};
    font-family: ".AppleSystemUIFont", "Segoe UI", "Helvetica Neue", "DejaVu Sans";
    font-size: 13px;
}}
QLabel {{ background: transparent; }}
#PageSurface {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {p.bg},stop:0.55 {p.bg_elevated},stop:1 {p.bg});
}}
#PageContent {{ background: transparent; }}
QToolTip {{
    background-color: {p.bg_elevated};
    color: {p.text};
    border: 1px solid {p.border_strong};
    border-radius: {m.radius_sm}px;
    padding: 5px 8px;
}}

/* ---------- title bar ---------- */
#TitleBar {{
    background-color: {p.bg_elevated};
    border-bottom: 1px solid {p.border};
}}
#TitleBar QLabel {{
    background: transparent;
    color: {p.text};
}}
#TitleBarTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {p.text};
}}
#TitleBarSubtitle {{
    font-size: 11px;
    color: {p.text_faint};
}}

/* ---------- sidebar ---------- */
#Sidebar {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {p.bg_sidebar},stop:1 {p.bg_elevated});
    border-right: 1px solid {p.border};
}}
#SidebarBrand {{
    font-size: 19px;
    font-weight: 800;
    color: {p.text};
}}
#SidebarBrandAccent {{
    color: {p.accent};
}}
#SidebarSection {{
    font-size: 10px;
    font-weight: 700;
    color: {p.text_faint};
    letter-spacing: 1px;
    padding: 10px 12px 4px 12px;
}}
QPushButton#NavButton {{
    background: transparent;
    border: none;
    border-radius: {m.radius}px;
    color: {p.text_dim};
    padding: 8px 12px;
    text-align: left;
    font-size: 13px;
}}
QPushButton#NavButton:hover {{
    background-color: {p.bg_hover};
    color: {p.text};
}}
QPushButton#NavButton:checked {{
    background-color: {p.accent};
    color: {p.accent_text};
    font-weight: 600;
}}

/* ---------- cards ---------- */
#Card {{
    background: qlineargradient(x1:0,y1:0,x2:0.7,y2:1,stop:0 {p.bg_panel},stop:0.05 {p.bg_elevated},stop:1 {p.bg_sidebar});
    border: 1px solid {p.border_strong};
    border-top: 1px solid {p.border_strong};
    border-radius: {m.radius_lg}px;
}}
#CardTitle {{
    font-size: 14px;
    font-weight: 650;
    color: {p.text};
}}
#CardSubtitle {{
    font-size: 11px;
    color: {p.text_faint};
}}
#StatValue {{
    font-size: 27px;
    font-weight: 750;
    color: {p.text};
}}
#StatLabel {{
    font-size: 11px;
    color: {p.text_dim};
    letter-spacing: 0.4px;
}}
#StatIcon {{
    font-size: 19px;
}}
#PageTitle {{
    font-size: 25px;
    font-weight: 750;
    color: {p.text};
}}
#PageSubtitle {{
    font-size: 13px;
    color: {p.text_dim};
}}
#SectionTitle {{
    font-size: 16px;
    font-weight: 680;
    color: {p.text};
}}

/* ---------- buttons ---------- */
QPushButton {{
    background-color: {p.bg_input};
    border: 1px solid {p.border_strong};
    border-radius: {m.radius}px;
    padding: 7px 14px;
    color: {p.text};
    font-size: 13px;
    min-height: 18px;
}}
QPushButton:hover {{ background-color: {p.bg_hover}; }}
QPushButton:pressed {{ background-color: {p.bg_active}; }}
QPushButton:disabled {{ color: {p.text_faint}; border-color: {p.border}; }}
QPushButton#Primary {{
    background-color: {p.accent};
    border: 1px solid {p.accent};
    color: {p.accent_text};
    font-weight: 620;
}}
QPushButton#Primary:hover {{ background-color: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton#Primary:disabled {{ background-color: {p.bg_input}; color: {p.text_faint}; border-color: {p.border}; }}
QPushButton#Danger {{
    background-color: transparent;
    border: 1px solid {p.danger};
    color: {p.danger};
}}
QPushButton#Danger:hover {{ background-color: {p.danger}; color: #ffffff; }}
QPushButton#Ghost {{
    background: transparent;
    border: none;
    color: {p.accent};
    padding: 4px 8px;
}}
QPushButton#Ghost:hover {{ background-color: {p.bg_hover}; border-radius: {m.radius_sm}px; }}
QPushButton#BigAction {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {p.accent}, stop:1 {p.info});
    border: none;
    border-radius: {m.radius_lg}px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 650;
    padding: 13px 20px;
}}
QPushButton#BigAction:hover {{ background-color: {p.accent_hover}; }}
QPushButton#BigAction:disabled {{ background-color: {p.bg_input}; color: {p.text_faint}; }}

/* ---------- inputs ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {p.bg_input};
    border: 1px solid {p.border_strong};
    border-radius: {m.radius}px;
    padding: 7px 10px;
    color: {p.text};
    selection-background-color: {p.accent};
    selection-color: #ffffff;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {p.accent};
}}
QLineEdit::placeholder {{ color: {p.text_faint}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {p.bg_elevated};
    border: 1px solid {p.border_strong};
    border-radius: {m.radius}px;
    selection-background-color: {p.accent};
    selection-color: #ffffff;
    padding: 4px;
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {p.bg_hover};
    border: none;
    width: 17px;
}}
QCheckBox {{ color: {p.text}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid {p.border_strong};
    background: {p.bg_input};
}}
QCheckBox::indicator:checked {{
    background-color: {p.accent};
    border-color: {p.accent};
    image: none;
}}

/* ---------- lists / tables ---------- */
QListWidget, QTreeWidget, QTableWidget {{
    background-color: {p.bg_elevated};
    border: 1px solid {p.border};
    border-radius: {m.radius_lg}px;
    outline: none;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 7px;
    border-radius: {m.radius_sm}px;
}}
QListWidget::item:hover, QTreeWidget::item:hover {{ background-color: {p.bg_hover}; }}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background-color: {p.accent}; color: {p.accent_text};
}}
QHeaderView::section {{
    background-color: {p.bg_panel};
    color: {p.text_dim};
    border: none;
    border-bottom: 1px solid {p.border};
    padding: 7px 8px;
    font-size: 11px;
    font-weight: 650;
}}

/* ---------- scrollbars ---------- */
QScrollBar:vertical {{
    background: transparent; width: 11px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {p.border_strong}; border-radius: 5px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {p.text_faint}; }}
QScrollBar:horizontal {{
    background: transparent; height: 11px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {p.border_strong}; border-radius: 5px; min-width: 28px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- progress ---------- */
QProgressBar {{
    background-color: {p.bg_input};
    border: none;
    border-radius: 5px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {p.accent}, stop:1 {p.info});
    border-radius: 5px;
}}

/* ---------- tabs ---------- */
QTabWidget::pane {{
    border: 1px solid {p.border};
    border-radius: {m.radius_lg}px;
    background: {p.bg_elevated};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {p.text_dim};
    padding: 8px 16px;
    margin-right: 2px;
    border-radius: {m.radius}px;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    background: {p.bg_elevated};
    color: {p.text};
    font-weight: 620;
}}
QTabBar::tab:hover:!selected {{ color: {p.text}; }}

/* ---------- misc ---------- */
QSplitter::handle {{ background: {p.border}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QGroupBox {{
    border: 1px solid {p.border};
    border-radius: {m.radius_lg}px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: 620;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px; padding: 0 5px;
    color: {p.text_dim};
}}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
#Divider {{ background: {p.border}; max-height: 1px; min-height: 1px; border: none; }}
#Badge {{
    background-color: {p.accent};
    color: {p.accent_text};
    border-radius: 8px;
    padding: 1px 7px;
    font-size: 10px;
    font-weight: 700;
}}
"""


def apply_theme(app, theme_name: str = "dark") -> Palette:
    """Apply a theme to a QApplication and return the palette used."""
    p = PALETTES.get(theme_name, DARK)
    app.setStyleSheet(stylesheet(p))
    _ACTIVE["name"] = p.name
    return p


# The palette currently applied to the running application.  Widgets that paint
# themselves (the timeline, the preview) need it to match the stylesheet.
_ACTIVE: dict[str, str] = {"name": "dark"}


def palette() -> Palette:
    """Return the palette currently in use."""
    return PALETTES.get(_ACTIVE.get("name", "dark"), DARK)


def available_font_families() -> list[str]:
    """List installed font families (for the caption font picker)."""
    try:
        return sorted(QFontDatabase.families())
    except Exception:
        return []

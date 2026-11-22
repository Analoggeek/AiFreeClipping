"""Caption generation and styling.

Builds word-level caption cues from a transcript and renders them with ASS (Advanced
SubStation Alpha) subtitles, which FFmpeg renders natively -- giving real animated,
word-by-word highlighted captions without needing a separate rendering engine.

All 8 caption styles are real, distinct ASS styles.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..ai.transcription import Transcript, Word
from ..core.logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class CaptionCue:
    start: float
    end: float
    text: str
    words: list[dict] = field(default_factory=list)  # [{w, s, e}]

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
            "words": self.words,
        }


# Caption fonts, in order of preference.  The first one that is actually
# installed is used, so the subtitles are never rendered with a font the
# system does not have.
FONT_CANDIDATES = [
    "DejaVu Sans",
    "Arial",
    "Helvetica",
    "Helvetica Neue",
    "SF Pro Display",
    "Segoe UI",
    "Roboto",
    "Liberation Sans",
    "Noto Sans",
    "Verdana",
]

_resolved_font: str | None = None


def system_font() -> str:
    """The name of a caption font that is installed on this machine.

    ``DejaVu Sans`` is the first choice because it is what the styles are
    designed around, but it is not present on macOS or Windows, where
    the subtitle filter would then fall back to something unreadable.
    """
    global _resolved_font
    if _resolved_font is not None:
        return _resolved_font
    families: set[str] = set()
    try:
        from PySide6.QtGui import QFontDatabase, QGuiApplication

        # The font database needs a running application.  There is none
        # when this module is imported, and that is not an error: the
        # styles are written out much later, when there is one.
        if QGuiApplication.instance() is not None:
            families = set(QFontDatabase.families())
    except Exception:
        families = set()
    if families:
        for name in FONT_CANDIDATES:
            if name in families:
                _resolved_font = name
                return _resolved_font
        # Nothing preferred is there; any family will do.
        _resolved_font = sorted(families)[0]
        return _resolved_font
    # No font service: fall back to the font file we can at least find.
    _resolved_font = FONT_CANDIDATES[0]
    return _resolved_font


def resolve_style_fonts() -> None:
    """Fill in the real font name on every caption style.

    The styles are built at import time, before there is a running
    application, so the font they carry is only a guess.  Once the
    application exists the guess is replaced with a font that is really
    installed, which is what keeps the subtitles legible on macOS and
    Windows.
    """
    name = system_font()
    for style in list(CAPTION_STYLES.values()):
        style.font = name


def _caption_font() -> str:
    """The caption font, resolved as late as possible.

    The styles are built when this module is imported, which happens
    before there is a running application, so the name that is stored is
    only a guess.  :func:`resolve_style_fonts` corrects it once the
    application exists.
    """
    return system_font()


@dataclass
class CaptionStyle:
    """A complete visual definition of a caption style."""
    key: str
    name: str
    description: str
    font: str = ""
    size: int = 58
    primary_color: str = "&H00FFFFFF"      # ASS is &HAABBGGRR
    outline_color: str = "&H00000000"
    back_color: str = "&H80000000"
    bold: bool = True
    uppercase: bool = True
    stroke_width: float = 4.0
    shadow: float = 2.0
    border_style: int = 1
    alignment: int = 2          # 2 = bottom centre
    margin_v: int = 240
    margin_h: int = 90
    highlight_color: str = "&H0000FFFF"
    karaoke: bool = False
    background_opacity: float = 0.0
    scale_with_video: bool = True

    def to_dict(self) -> dict:
        return {
            "key": self.key, "name": self.name, "description": self.description,
            "font": self.font, "size": self.size,
            "primary_color": self.primary_color, "highlight_color": self.highlight_color,
            "stroke_width": self.stroke_width, "shadow": self.shadow,
            "alignment": self.alignment, "karaoke": self.karaoke,
            "uppercase": self.uppercase,
        }


CAPTION_STYLES: dict[str, CaptionStyle] = {}


def _register(style: CaptionStyle) -> None:
    CAPTION_STYLES[style.key] = style


_register(CaptionStyle(
    key="mrbeast",
    name="MrBeast Style",
    description="Huge bold white text, thick black outline, punchy and loud",
    font=_caption_font(), size=64, primary_color="&H00FFFFFF", outline_color="&H00000000",
    bold=True, uppercase=True, stroke_width=6.0, shadow=3.0, alignment=2, margin_v=260,
    highlight_color="&H0000FFFF",
))
_register(CaptionStyle(
    key="minimal_white",
    name="Minimal White",
    description="Clean white text on the image, thin outline, quiet and elegant",
    font=_caption_font(), size=50, primary_color="&H00FFFFFF", outline_color="&H64000000",
    bold=False, uppercase=False, stroke_width=2.0, shadow=1.0, alignment=2, margin_v=180,
))
_register(CaptionStyle(
    key="neon_gaming",
    name="Neon Gaming",
    description="Cyan neon glow with magenta highlights",
    font=_caption_font(), size=56, primary_color="&H00F0F0FF", outline_color="&H00A000C0",
    bold=True, uppercase=True, stroke_width=3.5, shadow=4.0, alignment=2, margin_v=240,
    highlight_color="&H00E060FF", border_style=1,
))
_register(CaptionStyle(
    key="modern_podcast",
    name="Modern Podcast",
    description="Medium-weight text in a soft box, ideal for talking-head clips",
    font=_caption_font(), size=52, primary_color="&H00FFFFFF", outline_color="&H30000000",
    bold=False, uppercase=False, stroke_width=1.5, shadow=0.0, alignment=2, margin_v=200,
    background_opacity=0.55,
))
_register(CaptionStyle(
    key="bold_viral",
    name="Bold Viral",
    description="Extra-bold uppercase with a thick stroke -- highest readability",
    font=_caption_font(), size=62, primary_color="&H00FFFFFF", outline_color="&H00000000",
    bold=True, uppercase=True, stroke_width=7.0, shadow=3.0, alignment=2, margin_v=250,
    highlight_color="&H0000FFFF",
))
_register(CaptionStyle(
    key="cinematic",
    name="Cinematic",
    description="Letter-spaced serif-like caps, wide margins, understated",
    font=_caption_font(), size=48, primary_color="&H00F0F0F0", outline_color="&H20000000",
    bold=False, uppercase=True, stroke_width=2.0, shadow=2.0, alignment=2, margin_v=280,
))
_register(CaptionStyle(
    key="karaoke",
    name="Karaoke",
    description="Word-by-word colour fill, like a sing-along",
    font=_caption_font(), size=56, primary_color="&H00FFFFFF", outline_color="&H00000000",
    bold=True, uppercase=False, stroke_width=4.0, shadow=2.0, alignment=2, margin_v=230,
    highlight_color="&H0000D7FF", karaoke=True,
))
_register(CaptionStyle(
    key="clean_professional",
    name="Clean Professional",
    description="Corporate-friendly, sentence case, light shadow",
    font=_caption_font(), size=50, primary_color="&H00FFFFFF", outline_color="&H40000000",
    bold=False, uppercase=False, stroke_width=2.5, shadow=1.5, alignment=2, margin_v=210,
))


def get_style(key: str) -> CaptionStyle:
    return CAPTION_STYLES.get(key, CAPTION_STYLES["bold_viral"])


def list_styles() -> list[dict]:
    return [s.to_dict() for s in CAPTION_STYLES.values()]


# --------------------------------------------------------------------------------------
# Cue building
# --------------------------------------------------------------------------------------

MAX_CHARS_PER_LINE = 26
MAX_LINES = 2
MAX_WORDS_PER_CUE = 7
MIN_CUE_DURATION = 0.7
MAX_CUE_DURATION = 4.0


def _split_long_word(word: str) -> list[str]:
    return [word[i:i + 12] for i in range(0, len(word), 12)]


def _wrap(words: list[str]) -> list[list[str]]:
    """Greedy word wrap into at most MAX_LINES lines of MAX_CHARS_PER_LINE."""
    lines: list[list[str]] = []
    current: list[str] = []
    length = 0
    for w in words:
        wl = len(w)
        if length and length + 1 + wl > MAX_CHARS_PER_LINE:
            lines.append(current)
            current = []
            length = 0
            if len(lines) >= MAX_LINES:
                break
        if current:
            length += 1
        current.append(w)
        length += wl
    if current and len(lines) < MAX_LINES:
        lines.append(current)
    return lines or [[""]]


def build_cues(
    transcript: Transcript,
    start: float,
    end: float,
    words_per_cue: int = MAX_WORDS_PER_CUE,
) -> list[CaptionCue]:
    """Build sentence-based caption cues with word timings for a time range."""
    words: list[Word] = [
        w for w in transcript.words_between(start, end) if w.word.strip()
    ]
    if not words:
        # Fall back to segment-level cues without word timings
        cues: list[CaptionCue] = []
        for seg in transcript.segments:
            if seg.end <= start or seg.start >= end:
                continue
            s = max(start, seg.start)
            e = min(end, seg.end)
            text = seg.text.strip()
            if text:
                cues.append(CaptionCue(s, e, text, []))
        return cues

    cues: list[CaptionCue] = []
    i = 0
    while i < len(words):
        group = words[i:i + words_per_cue]
        if not group:
            break
        g_start = group[0].start
        g_end = group[-1].end
        # Extend the cue to the next word's start so text does not flash off early
        if i + words_per_cue < len(words):
            g_end = max(g_end, words[i + words_per_cue].start - 0.01)
        if g_end - g_start < MIN_CUE_DURATION:
            g_end = g_start + MIN_CUE_DURATION
        g_end = min(g_end, end)
        text = " ".join(w.word for w in group).strip()
        cues.append(
            CaptionCue(
                start=g_start,
                end=g_end,
                text=text,
                words=[
                    {"w": w.word, "s": round(w.start, 3), "e": round(w.end, 3)}
                    for w in group
                ],
            )
        )
        i += words_per_cue
    return cues


def cues_from_transcript_text(
    text: str, start: float, end: float, words_per_cue: int = MAX_WORDS_PER_CUE
) -> list[CaptionCue]:
    """Build cues from plain text when word timings are unavailable."""
    tokens = text.split()
    if not tokens:
        return []
    per = max(1.0, (end - start) / max(1, len(tokens)))
    cues: list[CaptionCue] = []
    i = 0
    while i < len(tokens):
        group = tokens[i:i + words_per_cue]
        s = start + i * per
        e = start + (i + len(group)) * per
        cues.append(CaptionCue(s, e, " ".join(group), []))
        i += words_per_cue
    return cues


# --------------------------------------------------------------------------------------
# ASS rendering
# --------------------------------------------------------------------------------------


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _ass_color(hex_color: str) -> str:
    """Convert '#RRGGBB' to ASS '&HAABBGGRR'."""
    c = hex_color.strip().lstrip("#")
    if len(c) == 6:
        r, g, b = c[0:2], c[2:4], c[4:6]
        return f"&H00{b}{g}{r}".upper()
    return hex_color.upper()


def _escape(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "(").replace("}", ")")
    text = text.replace("\n", "\\N")
    return text


def render_ass(
    cues: list[CaptionCue],
    style: CaptionStyle,
    width: int = 1080,
    height: int = 1920,
    font_override: str = "",
    size_override: int = 0,
    position_override: str = "",
    stroke_override: int = -1,
    shadow_override: bool | None = None,
    background_override: bool | None = None,
    highlight_words: list[str] | None = None,
    font_file: str | Path | None = None,
) -> str:
    """Render cues to an ASS subtitle document.

    ``highlight_words`` are emphasised (colour + scale) inside every cue.
    """
    st = style
    font = font_override or st.font
    size = size_override or st.size
    position = position_override or _position_to_alignment(st, position_override)
    stroke = st.stroke_width if stroke_override < 0 else float(stroke_override)
    shadow = st.shadow if shadow_override is None else (2.0 if shadow_override else 0.0)
    bg = st.background_opacity
    if background_override is not None:
        bg = 0.6 if background_override else 0.0

    align_map = {"bottom": 2, "middle": 5, "top": 8}
    if position in align_map:
        align = align_map[position]
        margin_v = st.margin_v
    else:
        align = st.alignment
        margin_v = st.margin_v

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font},{size},{st.primary_color},{st.highlight_color},{st.outline_color},{_ass_color('#000000') if bg <= 0 else _bg_color(bg)},{int(st.bold)},0,0,0,100,100,0,0,1,{stroke:.1f},{shadow:.1f},{align},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines_out: list[str] = []
    hl = {w.lower().strip(".,!?") for w in (highlight_words or [])}

    for cue in cues:
        text = cue.text
        if st.uppercase:
            text = text.upper()
        lines = _wrap(text.split())
        rendered_lines: list[str] = []
        for ln in lines:
            parts = []
            for w in ln:
                core = w.strip(".,!?;:").lower()
                if hl and core in hl:
                    parts.append(
                        f"{{\\c{st.highlight_color}&\\fscx118\\fscy118\\b1}}{_escape(w)}"
                        f"{{\\c{st.primary_color}&\\fscx100\\fscy100\\b{int(st.bold)}}}"
                    )
                else:
                    parts.append(_escape(w))
            rendered_lines.append(" ".join(parts))
        body = "\\N".join(rendered_lines)
        lines_out.append(
            f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},Main,,0,0,0,,{body}"
        )

    return header + "\n".join(lines_out) + "\n"


def _bg_color(opacity: float) -> str:
    """ASS background colour with the given opacity (0..1 -> alpha byte)."""
    alpha = int(max(0.0, min(1.0, 1.0 - opacity)) * 255)
    return f"&H{alpha:02X}000000".upper()


def _position_to_alignment(style: CaptionStyle, override: str) -> int:
    if not override:
        return style.alignment
    return {"bottom": 2, "middle": 5, "top": 8}.get(override, style.alignment)


def write_ass(
    path: str | Path,
    cues: list[CaptionCue],
    style: CaptionStyle,
    width: int = 1080,
    height: int = 1920,
    **kwargs,
) -> Path:
    """Write an ASS file to disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The style may still carry the font that was guessed before the
    # application existed; a font that is really installed is better.
    if not style.font:
        style.font = system_font()
    content = render_ass(cues, style, width, height, **kwargs)
    path.write_text(content, encoding="utf-8")
    return path


def build_cues_for_clip(
    transcript: Transcript | None,
    text: str,
    start: float,
    end: float,
    words_per_cue: int = MAX_WORDS_PER_CUE,
) -> list[CaptionCue]:
    """Convenience wrapper: prefer word timings, fall back to plain text."""
    if transcript:
        cues = build_cues(transcript, start, end, words_per_cue)
        if cues:
            return cues
    return cues_from_transcript_text(text, start, end, words_per_cue)


def pick_highlight_words(text: str, top_n: int = 3) -> list[str]:
    """Choose words worth emphasising inside captions."""
    from ..ai.clip_detector import IMPORTANT_KEYWORDS, _content_words

    words = _content_words(text)
    if not words:
        return []
    scored: dict[str, int] = {}
    for w in words:
        score = 2 if w in IMPORTANT_KEYWORDS else 0
        score += min(3, words.count(w))
        scored[w] = score
    ranked = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:top_n]]


def retime_cues(cues, ranges):
    """Map absolute source cues through ordered (start, end, speed) edits."""
    output, offset = [], 0.0
    for start, end, speed in ranges:
        for cue in cues:
            left, right = max(start, cue.start), min(end, cue.end)
            if right <= left:
                continue
            words = [{**word, "s": offset + (max(start, word["s"])-start)/speed,
                      "e": offset + (min(end, word["e"])-start)/speed}
                     for word in cue.words if word["e"] > start and word["s"] < end]
            text = " ".join(word["w"] for word in words) if words else cue.text
            output.append(CaptionCue(offset+(left-start)/speed, offset+(right-start)/speed, text, words))
        offset += (end-start)/speed
    return output

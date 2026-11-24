"""AI title / description / hashtag generation.

Uses a local Ollama LLM when one is running.  When it is not available the module
falls back to a deterministic rule-based generator that produces genuinely useful
output from the clip's transcript and keywords -- never a placeholder.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..core.logging_setup import get_logger
from .clip_detector import (
    HOOK_PHRASES, IMPORTANT_KEYWORDS, QUESTION_MARKERS, SENTENCE_SPLIT,
    SURPRISE_MARKERS, _content_words, _tokens,
)

log = get_logger(__name__)

BASE_HASHTAGS = [
    "shorts", "reels", "tiktok", "viral", "fyp", "foryou", "trending",
    "foryoupage", "explore", "learnontiktok",
]

TOPIC_HASHTAG_MAP = {
    "money": "moneytok", "business": "businesstips", "tech": "techtok",
    "technology": "techtok", "science": "scitok", "psychology": "psychology",
    "health": "healthtok", "fitness": "fitness", "food": "foodtok",
    "travel": "travel", "music": "musictok", "gaming": "gaming",
    "ai": "aitools", "motivation": "motivation", "funny": "comedy",
    "story": "storytime", "facts": "didyouknow", "news": "news",
    "crypto": "crypto", "investing": "investing", "marketing": "marketing",
    "productivity": "productivity", "coding": "programming",
    "relationship": "relationships", "self": "selfimprovement",
    "career": "careeradvice", "education": "learnontiktok",
}


@dataclass
class ClipMetadata:
    titles: list[str] = field(default_factory=list)
    description: str = ""
    hashtags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    thumbnail_text: str = ""
    generator: str = "rule-based"

    def to_dict(self) -> dict:
        return {
            "titles": self.titles,
            "description": self.description,
            "hashtags": self.hashtags,
            "keywords": self.keywords,
            "thumbnail_text": self.thumbnail_text,
            "generator": self.generator,
        }


# --------------------------------------------------------------------------------------
# Ollama (optional local LLM)
# --------------------------------------------------------------------------------------


def ollama_available(host: str = "http://127.0.0.1:11434", timeout: float = 2.0) -> bool:
    """Check if a local Ollama server is running."""
    from ..core.local_ai import LocalOllama
    try:
        LocalOllama(host,timeout).request('/api/tags')
        return True
    except Exception:return False


def ollama_models(host: str = "http://127.0.0.1:11434", timeout: float = 2.0) -> list[str]:
    from ..core.local_ai import LocalOllama
    try:
        result=LocalOllama(host,timeout).request('/api/tags')
        return [item['name'] for item in result.get('models',[]) if isinstance(item,dict)
                and isinstance(item.get('name'),str) and 'cloud' not in item['name'].lower()]
    except Exception:return []


def _ollama_generate(prompt: str, model: str, host: str, timeout: float = 120.0) -> str | None:
    from ..core.local_ai import LocalOllama,LocalAIError
    try:return LocalOllama(host,timeout).generate(prompt,model)
    except LocalAIError as exc:
        log.warning('Local metadata inference unavailable: %s',exc)
        return None


def _parse_json_block(text: str) -> dict | None:
    """Extract the first JSON object from an LLM response."""
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


# --------------------------------------------------------------------------------------
# Rule-based generator
# --------------------------------------------------------------------------------------


def _pick_title_patterns(text: str, keywords: list[str]) -> list[str]:
    """Generate title candidates from several distinct patterns."""
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
    lower = text.lower()
    titles: list[str] = []

    def clean(s: str, limit: int = 70) -> str:
        s = s.strip().rstrip(".!?").strip()
        if len(s) > limit:
            s = s[:limit].rsplit(" ", 1)[0] + "…"
        return s

    # 1. Question re-framed
    for s in sentences:
        if "?" in s:
            titles.append(clean(s))
            break
    if not titles and "?" in lower:
        titles.append(clean(text))

    # 2. "The truth about X"
    truth_hit = next((p for p in HOOK_PHRASES if p in lower), None)
    kw = keywords[0] if keywords else ""
    if kw:
        titles.append(f"The Truth About {kw.capitalize()}")
        titles.append(f"{kw.capitalize()}: What Nobody Tells You")
    if truth_hit:
        titles.append(f"{truth_hit.capitalize()}… Here's Why")

    # 3. Surprising statement
    surprise = next((m for m in SURPRISE_MARKERS if m in lower), None)
    if surprise:
        titles.append(f"This Part Changed My Mind ({surprise})")

    # 4. Number / listicle style from a strong sentence
    strong = ""
    for s in sentences:
        cw = _content_words(s)
        if len(cw) >= 5 and sum(1 for w in cw if w in IMPORTANT_KEYWORDS) >= 1:
            strong = s
            break
    if strong:
        titles.append(clean(strong))
        titles.append(f"3 Things About {kw.capitalize()}" if kw else "3 Things Worth Knowing")

    # 5. Direct quote style
    if sentences:
        titles.append(f"“{clean(sentences[0], 60)}”")

    # 6. Question-driven
    if kw:
        titles.append(f"Why {kw.capitalize()} Actually Works")

    # Fallback
    if not titles:
        base = clean(text if text else (kw or f"Highlight {len(titles) + 1}"))
        titles.append(base or "Untitled Highlight")

    # De-duplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in titles:
        key = t.lower()
        if key not in seen and t:
            seen.add(key)
            out.append(t)
    return out[:5]


def _pick_hashtags(text: str, keywords: list[str]) -> list[str]:
    tags: list[str] = []
    lower = text.lower()
    for topic, tag in TOPIC_HASHTAG_MAP.items():
        if topic in lower and tag not in tags:
            tags.append(tag)
    for k in keywords[:4]:
        tag = re.sub(r"[^a-z0-9]", "", k.lower())
        if tag and len(tag) > 2 and tag not in tags:
            tags.append(tag)
    for tag in BASE_HASHTAGS:
        if len(tags) >= 12:
            break
        if tag not in tags:
            tags.append(tag)
    return tags[:12]


def _make_description(text: str, title: str, keywords: list[str]) -> str:
    """Write a short description that fits YouTube Shorts / Reels."""
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
    body = " ".join(sentences[:2]) if sentences else ""
    if len(body) > 260:
        body = body[:257] + "…"
    parts = [title]
    if body and body != title:
        parts.append(body)
    if keywords:
        parts.append(" · ".join(keywords[:5]))
    return "\n\n".join(p for p in parts if p)


def _make_thumbnail_text(text: str, keywords: list[str], title: str) -> str:
    """Short punchy text for a thumbnail (max ~4 words)."""
    lower = text.lower()
    for phrase in ("nobody tells you", "the truth about", "i was wrong",
                   "here's why", "it turns out", "stop doing this"):
        if phrase in lower:
            return phrase.upper()
    if keywords:
        return " ".join(k.upper() for k in keywords[:3])[:32]
    words = title.split()[:3]
    return " ".join(words).upper()[:32]


def generate_metadata_rule_based(
    text: str, keywords: list[str], title_hint: str = ""
) -> ClipMetadata:
    """Deterministic, genuinely useful metadata without any LLM."""
    titles = _pick_title_patterns(text, keywords)
    if title_hint and title_hint not in titles:
        titles = [title_hint] + titles
    titles = titles[:5]
    if len(titles) < 5:
        base = titles[-1] if titles else "Highlight"
        suffix = ["", " (Explained)", " — You Won't Believe This", " in 60 Seconds",
                  " (Must Watch)"]
        i = 1
        while len(titles) < 5 and i < len(suffix):
            variant = f"{base}{suffix[i]}"
            if variant not in titles:
                titles.append(variant)
            i += 1
    return ClipMetadata(
        titles=titles,
        description=_make_description(text, titles[0] if titles else "", keywords),
        hashtags=_pick_hashtags(text, keywords),
        keywords=keywords[:10],
        thumbnail_text=_make_thumbnail_text(text, keywords, titles[0] if titles else ""),
        generator="rule-based",
    )


# --------------------------------------------------------------------------------------
# Combined entry point
# --------------------------------------------------------------------------------------


def generate_metadata(
    text: str,
    keywords: list[str],
    title_hint: str = "",
    use_llm: bool = True,
    llm_model: str = "llama3.1:8b",
    ollama_host: str = "http://127.0.0.1:11434",
    timeout: float = 120.0,
) -> ClipMetadata:
    """Generate clip metadata, preferring a local LLM and falling back to rules."""
    fallback = generate_metadata_rule_based(text, keywords, title_hint)

    if not use_llm:
        return fallback
    if not ollama_available(ollama_host):
        fallback.generator = "rule-based (no local LLM)"
        return fallback

    excerpt = text.strip()[:2600]
    prompt = f"""You are a short-form video strategist. Based on this clip transcript, write:
1. "titles": exactly 5 punchy titles (max 62 chars each) optimised for YouTube Shorts / Instagram Reels.
2. "description": 2 short sentences (max 240 chars) describing the clip and why it hooks.
3. "hashtags": 8-12 relevant hashtags WITHOUT the "#" symbol.
4. "thumbnail_text": 2-4 words, ALL CAPS, that would work as thumbnail overlay text.

Clip transcript:
---
{excerpt}
---

Reply with ONLY a JSON object with keys: titles, description, hashtags, thumbnail_text."""

    raw = _ollama_generate(prompt, llm_model, ollama_host, timeout)
    parsed = _parse_json_block(raw or "")
    if not parsed:
        fallback.generator = "rule-based (LLM output unparseable)"
        return fallback

    titles = [str(t).strip() for t in (parsed.get("titles") or []) if str(t).strip()][:5]
    description = str(parsed.get("description") or "").strip()
    hashtags = [
        re.sub(r"[^A-Za-z0-9_]", "", str(h).lstrip("#")).lower()
        for h in (parsed.get("hashtags") or [])
    ]
    hashtags = [h for h in hashtags if h][:12]
    thumb = str(parsed.get("thumbnail_text") or "").strip().upper()

    if not titles:
        fallback.generator = "rule-based (LLM returned no titles)"
        return fallback

    return ClipMetadata(
        titles=titles,
        description=description or fallback.description,
        hashtags=hashtags or fallback.hashtags,
        keywords=fallback.keywords,
        thumbnail_text=thumb or fallback.thumbnail_text,
        generator=f"ollama:{llm_model}",
    )

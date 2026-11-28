"""Deterministic engagement scoring + local-LLM refinement for viral moment discovery."""
from __future__ import annotations

import math
import re
from typing import Any, Callable

from pydantic import BaseModel, Field

HOOK_WORDS = [
    "wait", "stop", "watch", "crazy", "insane", "unbelievable", "secret", "hack",
    "finally", "best", "worst", "never", "everyone", "surprise", "shocked", " epic",
    "win", "goal", "fail", "love", "wow", "omg", "bro", "dekho", "dude", "kya",
    "जबर्दस्त", "देखो", "वाह", "शानदार", "क्या", "गजब", "बेस्ट",
]


class Suggestion(BaseModel):
    index: int = Field(ge=0)
    score: int = Field(ge=0, le=100)
    title: str
    reason: str


class RerankResult(BaseModel):
    suggestions: list[Suggestion] = Field(default_factory=list)


class Candidate(BaseModel):
    media_id: str
    start: float
    end: float
    score: float
    reasons: list[str] = Field(default_factory=list)
    title: str
    transcript: str = ""
    region: dict[str, float] | None = None
    regions: list[dict[str, float]] = Field(default_factory=list)
    region_layout: str | None = None
    split_ratio: float | None = Field(default=None, ge=0.25, le=0.75)
    outline_style: str = "clean"
    crop_path: list[list[float]] = Field(default_factory=list)


def _crop_path_window(vision: dict[str, Any] | None, start: float, end: float) -> list[list[float]]:
    """Keep a clip-local slice of the source's subject path, including exact clip edges."""
    raw = (vision or {}).get("crop_path") or []
    points: list[tuple[float, float]] = []
    for item in raw:
        try:
            t, x = float(item[0]), float(item[1])
        except (IndexError, TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(t) and math.isfinite(x):
            points.append((t, max(0.0, min(1.0, x))))
    points.sort(key=lambda item: item[0])
    if not points or end <= start:
        return []
    compact: list[tuple[float, float]] = []
    for point in points:
        if compact and point[0] <= compact[-1][0]:
            compact[-1] = point
        else:
            compact.append(point)
    points = compact

    def at(t: float) -> float:
        if t <= points[0][0]:
            return points[0][1]
        if t >= points[-1][0]:
            return points[-1][1]
        for (t0, x0), (t1, x1) in zip(points, points[1:]):
            if t0 <= t <= t1:
                return x0 if t1 <= t0 else x0 + (x1 - x0) * (t - t0) / (t1 - t0)
        return points[-1][1]

    window = [[round(start, 6), round(at(start), 6)]]
    window.extend(
        [round(t, 6), round(x, 6)]
        for t, x in points if start < t < end
    )
    window.append([round(end, 6), round(at(end), 6)])
    return window


def _bins(duration: float, step: float = 0.5) -> list[float]:
    if duration <= 0:
        return []
    return [round(i * step, 3) for i in range(int(math.ceil(duration / step)) + 1)]


def _index(times: list[float], t: float) -> int:
    if not times:
        return 0
    return min(len(times) - 1, max(0, int(t / (times[1] - times[0]) if len(times) > 1 else 0.5)))


def build_features(
    transcript: dict[str, Any] | None,
    vision: dict[str, Any] | None,
    duration: float,
    step: float = 0.5,
) -> tuple[list[float], list[float], list[float]]:
    """Return aligned lists of speech, keyword, and visual-energy features."""
    times = _bins(duration, step)
    speech = [0.0] * len(times)
    keywords = [0.0] * len(times)
    for segment in (transcript or {}).get("segments", []):
        words = segment.get("words") or []
        for word in words:
            start = float(word.get("start", 0))
            end = float(word.get("end", start + 0.3))
            weight = float(word.get("probability", 0.8)) or 0.8
            for i in range(_index(times, start), min(len(times), _index(times, end) + 1)):
                speech[i] += weight
            token = re.sub(r"\W+", "", str(word.get("word", "")).lower())
            if any(hook.strip().lower() in token for hook in HOOK_WORDS if hook.strip()):
                keywords[_index(times, start)] += 1.5
    visual = [0.0] * len(times)
    for sample in (vision or {}).get("timeline", []):
        idx = _index(times, float(sample.get("t", 0)))
        if idx < len(visual):
            visual[idx] = max(visual[idx], float(sample.get("activity", 0)))
    return speech, keywords, visual


def window_score(
    speech: list[float], keywords: list[float], visual: list[float], start_idx: int, end_idx: int
) -> tuple[float, list[str]]:
    if end_idx <= start_idx:
        return 0.0, []
    span = speech[start_idx:end_idx] or [0.0]
    kw = keywords[start_idx:end_idx] or [0.0]
    vis = visual[start_idx:end_idx] or [0.0]
    density = sum(span) / len(span)
    keyword = sum(kw) / len(span)
    action = sum(vis) / len(span)
    peaks = max(vis) if vis else 0
    hook = max(kw[: min(8, len(kw))]) if kw else 0
    score = 18 + min(density, 2.5) * 16 + min(keyword, 2.0) * 13 + min(action, 1.0) * 22 + peaks * 8 + hook * 6
    reasons: list[str] = []
    if density > 1.2:
        reasons.append("dense speech / fast pacing")
    if keyword > 0.2:
        reasons.append("hook keyword detected")
    if action > 0.25:
        reasons.append("high visual activity")
    if peaks > 0.7:
        reasons.append("scene-change peak")
    return min(100.0, round(score, 2)), reasons


def make_title(text: str, fallback: str = "Video moment") -> str:
    """Return a concise factual label, without platform-specific or promotional copy."""
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    sentence = re.split(r"(?<=[.!?।])\s+", cleaned, maxsplit=1)[0] if cleaned else ""
    title = sentence or str(fallback or "").strip() or "Video moment"
    return title[:100].rstrip()



def _composition_ratio(layout: str | None, value: float | None) -> float:
    defaults = {
        "top-game-bottom-player": 0.58,
        "top-player-bottom-game": 0.42,
        "side-by-side": 0.62,
    }
    try:
        parsed = float(value) if value is not None else defaults.get(layout or "", 0.58)
    except (TypeError, ValueError, OverflowError):
        parsed = defaults.get(layout or "", 0.58)
    return max(0.25, min(0.75, parsed)) if math.isfinite(parsed) else defaults.get(layout or "", 0.58)


def propose(
    media_rows: list[dict[str, Any]],
    transcripts: dict[str, dict[str, Any]],
    visions: dict[str, dict[str, Any]],
    count: int = 5,
    min_duration: float = 15,
    max_duration: float = 60,
    platform: str = "shorts",
    regions: dict[str, list[dict[str, float]]] | None = None,
    layouts: dict[str, str] | None = None,
    focus_regions: dict[str, dict[str, float]] | None = None,
    split_ratios: dict[str, float] | None = None,
    outline_styles: dict[str, str] | None = None,
) -> list[Candidate]:
    """Rank high-signal, non-overlapping moments independently for each source."""
    target_count = max(1, min(50, int(count)))
    minimum = max(1.0, float(min_duration))
    maximum = max(minimum, float(max_duration))
    step = 0.5
    selected: list[Candidate] = []

    for media in media_rows:
        media_id = str(media["id"])
        duration = max(0.0, float(media.get("duration") or 0))
        if duration < minimum:
            continue
        transcript = transcripts.get(media_id) or {}
        vision_data = visions.get(media_id) or {}
        speech, keywords, visual = build_features(transcript, vision_data, duration, step)
        focus_boxes = (regions or {}).get(media_id) or []
        layout_name = (layouts or {}).get(media_id)
        split_ratio = _composition_ratio(layout_name, (split_ratios or {}).get(media_id))
        requested_outline = (outline_styles or {}).get(media_id, "clean")
        outline_style = requested_outline if requested_outline in {"none", "clean", "neon", "double"} else "clean"
        if focus_boxes:
            visual = [min(1.0, value * 1.12) for value in visual]
        has_signals = any(speech) or any(keywords) or any(visual)

        lengths = sorted({
            minimum,
            minimum + (maximum - minimum) / 3,
            minimum + (maximum - minimum) / 2,
            minimum + (maximum - minimum) * 2 / 3,
            maximum,
            30.0,
        })
        pool: list[Candidate] = []
        transcript_segments = transcript.get("segments", []) if isinstance(transcript, dict) else []
        for length in lengths:
            if length < minimum or length > maximum or length > duration:
                continue
            width = max(1, round(length / step))
            if width > len(speech):
                continue
            for start_idx in range(0, len(speech) - width + 1):
                end_idx = start_idx + width
                score, reasons = window_score(speech, keywords, visual, start_idx, end_idx)
                if has_signals and score < 18:
                    continue
                begin = start_idx * step
                stop = min(duration, end_idx * step)
                transcript_text = " ".join(
                    str(segment.get("text") or "")
                    for segment in transcript_segments if isinstance(segment, dict)
                    and float(segment.get("start", 0) or 0) <= stop
                    and float(segment.get("end", 0) or 0) >= begin
                ).strip()
                title = make_title(transcript_text, str(media.get("title") or ""))
                display_reasons = list(reasons) or ["steady engagement"]
                if focus_boxes:
                    display_reasons.append("focused on your player/gameplay regions")
                crop_path = (
                    _crop_path_window(vision_data, begin, stop)
                    if platform != "landscape" and not focus_boxes else []
                )
                if crop_path:
                    display_reasons.append("portrait framing follows a tracked subject")
                score_bonus = min(sum(1 for reason in display_reasons if reason not in {
                    "focused on your player/gameplay regions", "portrait framing follows a tracked subject",
                }), 3) * 0.02
                pool.append(Candidate(
                    media_id=media_id,
                    start=round(begin, 2),
                    end=round(stop, 2),
                    score=round(score * (1 + score_bonus), 2),
                    reasons=display_reasons,
                    title=title,
                    transcript=transcript_text[:600],
                    region=(focus_regions or {}).get(media_id) or (focus_boxes[0] if focus_boxes else None),
                    regions=focus_boxes,
                    region_layout=layout_name,
                    split_ratio=split_ratio,
                    outline_style=outline_style,
                    crop_path=crop_path,
                ))

        # Choose a mix of durations and scores, while keeping every proposed cut
        # at least two seconds clear of another cut from the same source. Clips
        # from different source files may naturally share the same time range.
        pool.sort(key=lambda item: (-item.score, item.start, item.end))
        source_picks: list[Candidate] = []
        for candidate in pool:
            if any(
                candidate.start < picked.end + 2 and candidate.end > picked.start - 2
                for picked in source_picks
            ):
                continue
            source_picks.append(candidate)
            if len(source_picks) >= target_count:
                break
        selected.extend(source_picks)

    selected.sort(key=lambda item: (-item.score, item.media_id, item.start))
    return selected[:target_count]


async def refine_with_llm(
    candidates: list[Candidate],
    llm: Callable,
    model: str | None = None,
) -> list[Candidate]:
    """Use one compact structured call to improve moment ranking and factual titles.

    Candidate timing and crop metadata remain source-of-truth; the model only
    returns an index, an adjusted score, and concise title/reason text.
    """
    if not candidates:
        return candidates
    limited = candidates[:8]
    summary = "\n".join(
        f"{index}. {candidate.start:.1f}-{candidate.end:.1f}s | "
        f"title: {candidate.title[:90]} | transcript: {candidate.transcript[:180]}"
        for index, candidate in enumerate(limited)
    )
    prompt = (
        "Review these video moments and rank them by engagement potential. "
        "Return one suggestion per input using its zero-based index. Keep every clip's timing unchanged. "
        "Write a concise, plain factual title under 100 characters, using only facts supported by the transcript. "
        "Do not use platform names, hashtags, promotional hooks, calls to action, or generic clickbait. "
        "Preserve the transcript's language and keep explanations short.\n"
        f"Moments:\n{summary}"
    )
    result = await llm(
        prompt,
        RerankResult,
        system="Return only schema-valid JSON. Do not invent events or alter clip timings.",
        model=model,
        temperature=0.15,
        timeout=90,
    )
    if not result or not result.suggestions:
        return candidates
    for suggestion in result.suggestions:
        if 0 <= suggestion.index < len(limited):
            candidate = limited[suggestion.index]
            candidate.score = (candidate.score + float(suggestion.score)) / 2
            if suggestion.title.strip():
                candidate.title = suggestion.title.strip()[:100]
            if suggestion.reason.strip():
                candidate.reasons = [suggestion.reason.strip()[:120]] + candidate.reasons[:1]
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates

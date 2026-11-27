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
HASHTAGS = {
    "shorts": ["#Shorts", "#Viral", "#AIClipperPro"],
    "reels": ["#Reels", "#Viral", "#AIClipperPro"],
    "tiktok": ["#FYP", "#Viral", "#AIClipperPro"],
    "landscape": ["#Viral", "#AIClipperPro"],
}


class Suggestion(BaseModel):
    start: float
    end: float
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
    hook: str = ""
    hashtags: list[str] = Field(default_factory=list)
    transcript: str = ""
    region: dict[str, float] | None = None
    regions: list[dict[str, float]] = Field(default_factory=list)
    region_layout: str | None = None
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


def make_title(text: str, platform: str, fallback: str = "You won't believe this") -> tuple[str, str]:
    words = [w.strip() for w in re.split(r"[.!?]", text) if len(w.strip()) > 12]
    hook = (words[0] if words else text.strip()).strip()[:110]
    title = hook or fallback
    if len(title) < 12:
        title = f"{title} — you need to see this"
    title = title[:97]
    if platform in HASHTAGS and "#Shorts" not in title:
        suffix = " #Shorts" if platform == "shorts" else ""
        title = (title[: 100 - len(suffix)] + suffix).strip()
    return title, hook


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
) -> list[Candidate]:
    """Greedy non-overlapping window search over fused audio/visual features."""
    candidates: list[Candidate] = []
    step = 0.5
    for media in media_rows:
        media_id = media["id"]
        duration = float(media.get("duration") or 0)
        if duration < min_duration:
            continue
        speech, keywords, visual = build_features(
            transcripts.get(media_id), visions.get(media_id), duration, step
        )
        focus_boxes = (regions or {}).get(media_id) or []
        if focus_boxes:
            # Region-focused visual activity is already fused into `visual`; mark
            # the bias so the reason list and the editor keep the same context.
            visual = [min(1.0, value * 1.12) for value in visual]
        seen: list[tuple[float, float]] = []
        lengths = sorted(
            {min_duration, (min_duration + max_duration) / 3, (min_duration + max_duration) / 2,
             (min_duration + max_duration) * 2 / 3, max_duration, 30.0}
        )
        lengths = [length for length in lengths if min_duration <= length <= max_duration and length <= duration]
        fallback_scores: list[tuple[float, int, int, list[str], str]] = []
        for length in lengths:
            width = max(1, int(length / step))
            scored = []
            has_signals = any(speech) or any(keywords) or any(visual)
            for start in range(0, max(1, len(speech) - width + 1)):
                end = start + width
                score, reasons = window_score(speech, keywords, visual, start, end)
                fallback_scores.append((score, start, end, reasons, media_id))
                if has_signals and score < 18:
                    continue
                if any(not (start * step >= stop + 2 or end * step <= begin - 2) for begin, stop in seen):
                    continue
                scored.append((score, start, end, reasons))
            scored.sort(reverse=True)
            for score, start, end, reasons in scored[: max(count * 2, 4)]:
                begin, stop = start * step, min(duration, end * step)
                if any(not (begin >= b + 2 or stop <= a - 2) for a, b in seen):
                    continue
                seen.append((begin, stop))
                transcript_text = " ".join(
                    seg.get("text", "")
                    for seg in transcripts.get(media_id, {}).get("segments", [])
                    if seg.get("start", 0) <= stop and seg.get("end", 0) >= begin
                ).strip()
                title, hook = make_title(transcript_text, platform, media.get("title", ""))
                reasons = list(reasons) or ["steady engagement"]
                if focus_boxes:
                    reasons.append("focused on your player/gameplay regions")
                crop_path = (
                    _crop_path_window(visions.get(media_id), begin, stop)
                    if platform != "landscape" and not focus_boxes else []
                )
                display_reasons = reasons + (["portrait framing follows a tracked subject"] if crop_path else [])
                candidates.append(
                    Candidate(
                        media_id=media_id,
                        start=round(begin, 2),
                        end=round(stop, 2),
                        score=round(score * (1 + min(len(reasons), 3) * 0.02), 2),
                        reasons=display_reasons,
                        title=title,
                        hook=hook[:140],
                        hashtags=HASHTAGS.get(platform, HASHTAGS["shorts"]),
                        transcript=transcript_text[:600],
                        region=(focus_regions or {}).get(media_id) or (focus_boxes[0] if focus_boxes else None),
                        regions=focus_boxes,
                        region_layout=(layouts or {}).get(media_id),
                        crop_path=crop_path,
                    )
                )
                if len(candidates) >= count * 4:
                    break
            if len(candidates) >= count * 4:
                break
    if len(candidates) < count:
        claimed = [(item.start, item.end) for item in candidates]
        for score, start, end, reasons, media_id in sorted(fallback_scores, key=lambda item: item[0], reverse=True):
            media = next((item for item in media_rows if item["id"] == media_id), {"id": media_id, "title": ""})
            duration = float(media.get("duration") or 0)
            begin, stop = start * step, min(duration, end * step)
            if any(begin < b and stop > a for a, b in claimed):
                continue
            claimed.append((begin, stop))
            transcript_text = " ".join(
                seg.get("text", "")
                for seg in transcripts.get(media_id, {}).get("segments", [])
                if seg.get("start", 0) <= stop and seg.get("end", 0) >= begin
            ).strip()
            title, hook = make_title(transcript_text, platform, media.get("title", ""))
            chosen_reasons = list(reasons) or ["steady engagement"]
            focus_boxes = (regions or {}).get(media_id) or []
            if focus_boxes:
                chosen_reasons.append("focused on your player/gameplay regions")
            crop_path = (
                _crop_path_window(visions.get(media_id), begin, stop)
                if platform != "landscape" and not focus_boxes else []
            )
            if crop_path:
                chosen_reasons.append("portrait framing follows a tracked subject")
            candidates.append(Candidate(
                media_id=media_id, start=round(begin, 2), end=round(stop, 2),
                score=round(score, 2), reasons=chosen_reasons, title=title,
                hook=hook[:140], hashtags=HASHTAGS.get(platform, HASHTAGS["shorts"]),
                transcript=transcript_text[:600],
                region=(focus_regions or {}).get(media_id) or (focus_boxes[0] if focus_boxes else None),
                regions=focus_boxes, region_layout=(layouts or {}).get(media_id),
                crop_path=crop_path,
            ))
            if len(candidates) >= count:
                break
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[: max(count, 1)]


async def refine_with_llm(
    candidates: list[Candidate],
    llm: Callable,
    model: str | None = None,
) -> list[Candidate]:
    """Optional local-LLM rerank; falls back untouched when Ollama is unavailable."""
    if not candidates:
        return candidates
    summary = "\n".join(
        f"{i}. {c.start}-{c.end}s | {c.transcript[:240]}" for i, c in enumerate(candidates[:12])
    )
    prompt = (
        "You are a viral short-form video editor. Rank these moments by viral potential. "
        "Keep the same indices and timings. Rewrite each title under 100 chars with #Shorts. "
        f"Moments:\n{summary}"
    )
    result = await llm(
        prompt,
        RerankResult,
        system="Return JSON only. Do not change start/end times.",
        model=model,
    )
    if not result or not result.suggestions:
        return candidates
    for suggestion in result.suggestions:
        if 0 <= suggestion.start < len(candidates):
            candidate = candidates[int(suggestion.start)]
            candidate.score = (candidate.score + float(suggestion.score)) / 2
            if suggestion.title:
                candidate.title = suggestion.title[:100]
            if suggestion.reason:
                candidate.reasons = [suggestion.reason] + candidate.reasons[:1]
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates

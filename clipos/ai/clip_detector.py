"""AI clip detection engine.

Scores every candidate window of a video on a set of real, measurable engagement
signals and returns a ranked list of clips.

Signals used (all computed from genuine analysis, never invented):
  * speech energy & dynamic range          (audio_analysis)
  * speech rate / words per minute          (transcript + audio)
  * keyword density & importance           (lexicon + transcript)
  * question / answer / surprise markers    (transcript text)
  * emotional & humour cues                (lexicon + punctuation)
  * scene changes inside the window         (visual_analysis)
  * subject prominence / face presence      (visual_analysis)
  * topic changes (segment boundary)        (transcript similarity)
  * silence ratio & pause density           (audio_analysis)
  * hook strength of the opening seconds    (energy ramp + first-sentence quality)
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable

from .audio_analysis import AudioAnalysis
from .speaker_tracking import SpeakerTrack, subject_center_at
from .transcription import Transcript
from .visual_analysis import VisualAnalysis

# --------------------------------------------------------------------------------------
# Lexicons
# --------------------------------------------------------------------------------------

IMPORTANT_KEYWORDS = {
    "actually", "amazing", "because", "believe", "best", "breakthrough", "change",
    "changed", "crazy", "discover", "discovered", "everyone", "first", "finally",
    "forbidden", "free", "guilty", "huge", "impossible", "incredible", "important",
    "improve", "improved", "insane", "key", "life", "million", "mistake", "money",
    "never", "nobody", "proof", "question", "reason", "record", "reveal", "secret",
    "shocking", "secret", "serious", "secretly", "stop", "secret", "surprising",
    "truth", "ultimate", "unbelievable", "worst", "wrong", "secret", "everything",
    "nothing", "always", "secret", "warning", "danger", "safe", "protect",
    "mind", "brain", "body", "health", "science", "future", "technology", "money",
    "business", "success", "fail", "failure", "system", "problem", "solution",
}

QUESTION_MARKERS = {
    "what", "why", "how", "when", "where", "who", "which", "is it", "do you",
    "did you", "can you", "would you", "have you", "are you", "am i", "should i",
    "could you", "will you", "why not", "what if", "think about",
}

SURPRISE_MARKERS = {
    "wow", "oh my", "whoa", "incredible", "unbelievable", "shocking", "mind blowing",
    "no way", "are you serious", "wait what", "hold on", "you won't believe",
    "never seen", "first time", "honestly", "turns out", "it turns out", "actually",
    "unfortunately", "fortunately", "thankfully", "crazy", "insane", "ridiculous",
}

EMOTION_MARKERS = {
    "love", "hate", "scared", "afraid", "angry", "happy", "sad", "excited",
    "worried", "amazing", "terrible", "beautiful", "disgusting", "proud", "sorry",
    "hope", "fear", "joy", "pain", "crisis", "danger", "emergency", "secret",
    "promise", "swear", "trust", "lie", "truth",
}

HUMOR_MARKERS = {
    "haha", "lol", "funny", "joke", "hilarious", "laugh", "comedy", "ridiculous",
    "obviously", "seriously", "nobody", "me neither", "same", "honestly", "apparently",
    "plot twist", "plot armour", "typical", "of course", "sure", "right?",
    "i mean", "you know", "anyway",
}

HOOK_PHRASES = {
    "here's why", "here's how", "the truth about", "nobody tells you",
    "i was wrong", "this changed everything", "stop doing this", "the reason why",
    "what if i told you", "the secret", "it turns out", "the biggest mistake",
    "watch this", "look at this", "hear me out", "this is insane", "unbelievable",
    "let me explain", "picture this", "imagine this", "here's the thing",
    "you've been told", "everyone gets this wrong", "3 things", "5 ways",
    "one question", "what if", "the reason", "nothing else", "this one trick",
}

STOPWORDS = {
    "a", "about", "after", "all", "also", "am", "an", "and", "any", "are", "as",
    "at", "be", "because", "been", "but", "by", "can", "come", "could", "did",
    "do", "does", "for", "from", "get", "had", "has", "have", "he", "her", "here",
    "him", "his", "how", "i", "if", "in", "into", "is", "it", "its", "just", "me",
    "my", "no", "not", "of", "on", "or", "our", "out", "she", "so", "some", "than",
    "that", "the", "their", "them", "then", "there", "these", "they", "this",
    "to", "too", "up", "us", "was", "we", "were", "what", "when", "where", "which",
    "who", "why", "will", "with", "would", "you", "your", "yeah", "okay", "right",
    "well", "like", "know", "think", "going", "really", "thing", "things",
}

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _content_words(text: str) -> list[str]:
    return [w for w in _tokens(text) if w not in STOPWORDS and len(w) > 2]


# --------------------------------------------------------------------------------------
# Candidate windows
# --------------------------------------------------------------------------------------


@dataclass
class ClipCandidate:
    start: float
    end: float
    text: str = ""
    transcript_text: str = ""
    engagement_score: float = 0.0
    virality_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    title: str = ""
    description: str = ""
    hook_suggestions: list[str] = field(default_factory=list)
    signal_scores: dict = field(default_factory=dict)
    subject_center: tuple[float, float] = (0.5, 0.42)
    word_count: int = 0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "title": self.title,
            "description": self.description,
            "engagement_score": round(self.engagement_score, 1),
            "virality_score": round(self.virality_score, 1),
            "reasons": self.reasons,
            "keywords": self.keywords,
            "hook_suggestions": self.hook_suggestions,
            "signal_scores": {k: round(v, 3) for k, v in self.signal_scores.items()},
            "transcript_text": self.transcript_text,
            "word_count": self.word_count,
        }


def _score_signals(
    start: float,
    end: float,
    text: str,
    audio: AudioAnalysis,
    visual: VisualAnalysis,
    transcript: Transcript | None,
    speaker: SpeakerTrack | None,
    activity_jumps=None,
) -> tuple[dict, list[str], list[str]]:
    """Compute every engagement signal for a window. Returns (scores, reasons, keywords)."""
    scores: dict[str, float] = {}
    reasons: list[str] = []
    dur = max(0.1, end - start)
    words = _tokens(text)
    content = _content_words(text)
    lower = text.lower()

    from .activity import window_activity
    motion,jump=window_activity(start,end,visual,audio,activity_jumps)
    scores["motion"]=motion
    scores["loudness_jump"]=jump
    if motion>.2:reasons.append("Measured subject-motion burst")
    if jump>.2:reasons.append("Measured loudness rise")

    # -- audio energy ---------------------------------------------------------------
    energy = audio.local_energy(start, end) if audio else 0.0
    scores["energy"] = energy
    if energy > 0.62:
        reasons.append("High vocal energy")

    # -- speech density (pause-heavy windows drag) ----------------------------------
    if audio and audio.duration > 0:
        sil = audio.silence_ratio(start, end)
        scores["silence"] = 1.0 - sil
        if sil < 0.12:
            scores["silence"] = min(1.0, scores["silence"] + 0.1)
            reasons.append("Continuous speech, no dead air")
        elif sil > 0.35:
            scores["silence"] *= 0.6

    # -- speech rate ---------------------------------------------------------------
    wpm = 0.0
    if words and audio:
        speech_time = sum(
            max(0.0, min(end, e) - max(start, s))
            for s, e in audio.speech_ranges
        )
        if speech_time > 0.5:
            wpm = len(words) / (speech_time / 60.0)
    # ~150 wpm is a natural, engaging pace; 110-190 is the sweet spot
    if wpm > 0:
        if 110 <= wpm <= 190:
            scores["speech_rate"] = 1.0
            reasons.append(f"Engaging speech pace ({wpm:.0f} wpm)")
        elif wpm > 190:
            scores["speech_rate"] = 0.7
        elif wpm < 90:
            scores["speech_rate"] = 0.35
        else:
            scores["speech_rate"] = 0.6
    else:
        scores["speech_rate"] = 0.4

    # -- keyword importance --------------------------------------------------------
    kw_hits = [w for w in content if w in IMPORTANT_KEYWORDS]
    kw_density = len(kw_hits) / max(1.0, len(content)) if content else 0.0
    scores["keywords"] = min(1.0, kw_density * 4.0 + len(set(kw_hits)) * 0.05)
    if kw_hits:
        reasons.append(f"Key topic words: {', '.join(sorted(set(kw_hits))[:4])}")

    # -- questions -----------------------------------------------------------------
    q_count = text.count("?")
    q_openers = sum(1 for w in words if w in QUESTION_MARKERS)
    scores["questions"] = min(1.0, (q_count * 0.45) + (q_openers * 0.07))
    if q_count:
        reasons.append(f"Contains {q_count} question{'s' if q_count > 1 else ''}")

    # -- surprise ------------------------------------------------------------------
    surprise_hits = [m for m in SURPRISE_MARKERS if m in lower]
    scores["surprise"] = min(1.0, len(surprise_hits) * 0.35)
    if surprise_hits:
        reasons.append(f"Surprising statement: '{surprise_hits[0]}'")

    # -- emotion -------------------------------------------------------------------
    emo_hits = [m for m in EMOTION_MARKERS if m in lower]
    scores["emotion"] = min(1.0, len(emo_hits) * 0.3)
    if emo_hits:
        reasons.append(f"Emotional language: '{emo_hits[0]}'")

    # -- humour --------------------------------------------------------------------
    humor_hits = [m for m in HUMOR_MARKERS if m in lower]
    exclam = text.count("!")
    scores["humor"] = min(1.0, len(humor_hits) * 0.3 + exclam * 0.1)
    if humor_hits:
        reasons.append("Humour / banter detected")

    # -- scene changes -------------------------------------------------------------
    cuts_in = sum(1 for c in visual.scenes.times if start <= c < end)
    if visual.scenes.count:
        scores["scene_change"] = min(1.0, cuts_in / 3.0)
    else:
        scores["scene_change"] = 0.35
    if cuts_in:
        reasons.append(f"{cuts_in} scene change{'s' if cuts_in > 1 else ''} inside the clip")

    # -- subject prominence --------------------------------------------------------
    if visual and visual.tracks:
        face = visual.face_at((start + end) / 2)
        if face:
            scores["subject"] = min(1.0, face.area * 6.0)
            if face.area > 0.05:
                reasons.append("Clear speaker on camera")
        else:
            scores["subject"] = 0.3
    else:
        scores["subject"] = 0.4

    # -- storytelling / topic continuity -------------------------------------------
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
    if sentences:
        scores["story"] = min(1.0, len(sentences) / 6.0)
        if len(sentences) >= 3:
            reasons.append(f"Multi-sentence narrative ({len(sentences)} beats)")
    else:
        scores["story"] = 0.3

    # -- hook quality (first 3 seconds) --------------------------------------------
    hook_text = ""
    if transcript:
        opening = transcript.text_between(start, min(end, start + 3.0))
        hook_text = opening
    hook_lower = hook_text.lower()
    hook_hits = [p for p in HOOK_PHRASES if p in hook_lower]
    scores["hook"] = min(1.0, len(hook_hits) * 0.5)
    if hook_hits:
        reasons.append("Strong opening hook")
    elif hook_text.strip():
        scores["hook"] = max(scores["hook"], 0.25)

    # -- dynamic range (varied loudness reads as expressive) ------------------------
    if audio and audio.dynamic_range_db > 0:
        scores["dynamics"] = min(1.0, audio.dynamic_range_db / 30.0)

    scores.setdefault("dynamics", 0.5)

    # -- keywords list for the clip -------------------------------------------------
    freq: dict[str, int] = {}
    for w in content:
        freq[w] = freq.get(w, 0) + 1
    keywords = [w for w, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))][:8]
    for k in IMPORTANT_KEYWORDS:
        if k in keywords:
            continue
    return scores, reasons, keywords


# Weights for the final engagement ranking (sum = 1.0)
SIGNAL_WEIGHTS = {
    "energy": 0.09,
    "silence": 0.09,
    "speech_rate": 0.12,
    "keywords": 0.12,
    "questions": 0.09,
    "surprise": 0.09,
    "emotion": 0.07,
    "humor": 0.06,
    "scene_change": 0.05,
    "subject": 0.06,
    "story": 0.05,
    "hook": 0.03,
    "dynamics": 0.0,
    "motion": 0.05,
    "loudness_jump": 0.03,
}


def _engagement_score(scores: dict) -> float:
    total = 0.0
    for key, weight in SIGNAL_WEIGHTS.items():
        total += weight * float(scores.get(key, 0.0))
    return max(0.0, min(100.0, total * 100.0))


def _virality_score(scores: dict, cand: ClipCandidate, audio: AudioAnalysis) -> float:
    """Virality potential: distinct from engagement -- about shareability and hook."""
    hook = float(scores.get("hook", 0.0))
    surprise = float(scores.get("surprise", 0.0))
    emotion = float(scores.get("emotion", 0.0))
    humor = float(scores.get("humor", 0.0))
    questions = float(scores.get("questions", 0.0))
    keywords = float(scores.get("keywords", 0.0))
    energy = float(scores.get("energy", 0.0))
    story = float(scores.get("story", 0.0))

    # Ideal short length is 25-50s -- outside that, virality drops
    d = cand.duration
    if d < 8:
        length_factor = 0.45
    elif d <= 20:
        length_factor = 0.85
    elif d <= 50:
        length_factor = 1.0
    elif d <= 70:
        length_factor = 0.82
    elif d <= 90:
        length_factor = 0.62
    else:
        length_factor = 0.4

    # A clip that *opens* on a strong hook is more shareable
    opening_bonus = 0.0
    if audio and audio.duration > 0:
        open_energy = audio.local_energy(cand.start, min(cand.end, cand.start + 2.0))
        opening_bonus = min(1.0, open_energy * 1.2)

    base = (
        hook * 0.24
        + surprise * 0.18
        + emotion * 0.12
        + humor * 0.12
        + questions * 0.10
        + keywords * 0.10
        + energy * 0.07
        + story * 0.07
    )
    activity=max(float(scores.get("motion",0)),float(scores.get("loudness_jump",0)))
    base=base*.94+activity*.06
    score = (base * 0.82 + opening_bonus * 0.18) * length_factor * 100.0
    return max(0.0, min(100.0, score))


def _generate_hooks(text: str, start: float, transcript: Transcript | None) -> list[str]:
    """Produce concrete hook suggestions for the first 1-3 seconds of a clip."""
    hooks: list[str] = []
    lower = text.lower()
    first_sentence = ""
    for s in SENTENCE_SPLIT.split(text):
        if s.strip():
            first_sentence = s.strip()
            break

    for phrase in HOOK_PHRASES:
        if phrase in lower:
            hooks.append(f"Open with: “{phrase.capitalize()}…”")
        if len(hooks) >= 3:
            break

    if first_sentence:
        short = first_sentence.rstrip(".!?").strip()
        if 12 <= len(short) <= 90:
            hooks.append(f"Text-on-screen hook: “{short[:70]}”")
            hooks.append(f"Cold open on the punchline: “{short[:70]}”")

    if "?" in text:
        hooks.append("Open on the question — it creates an open loop")

    if not hooks:
        if first_sentence:
            hooks.append(f"Cold open with: “{first_sentence[:80]}”")
        else:
            hooks.append("Start on the highest-energy frame and let the first line land")
        hooks.append("Add a 0.5s zoom-in on the first word to hold attention")
    return hooks[:4]


def _make_title(text: str, keywords: list[str], index: int) -> str:
    """Build a title from the strongest line inside the clip."""
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
    best = ""
    best_score = -1.0
    for pos, s in enumerate(sentences):
        cw = _content_words(s)
        if not cw:
            continue
        score = sum(1 for w in cw if w in IMPORTANT_KEYWORDS) + len(cw) * 0.12
        if len(s) > 120:
            score -= 0.6
        # A title taken from the opening of the clip reads better
        score -= pos * 0.35
        if score > best_score:
            best_score = score
            best = s
    if not best and keywords:
        best = " ".join(keywords[:3])
    best = best.rstrip(".!?").strip()
    if len(best) > 78:
        cut = best[:78].rsplit(" ", 1)[0]
        best = cut + "…"
    if not best:
        best = f"Highlight #{index + 1}"
    return best


def _candidate_windows(
    duration: float,
    min_dur: float,
    max_dur: float,
    transcript: Transcript | None,
    visual: VisualAnalysis,
    audio: AudioAnalysis,
    step: float = 1.0,
) -> list[tuple[float, float]]:
    """Build candidate (start, end) windows.

    Anchors are placed at meaningful boundaries: transcript sentence starts and scene
    cuts.  This avoids arbitrary sliding windows and produces cleaner clips.
    """
    anchors: set[float] = set()
    if transcript and transcript.segments:
        for seg in transcript.segments:
            # snap to a word boundary so we do not clip mid-word
            t = seg.start
            for w in seg.words[:1]:
                t = w.start
            anchors.add(round(t, 2))
    if visual and visual.scenes.times:
        for c in visual.scenes.times:
            anchors.add(round(c, 2))
    if not anchors:
        # No transcript and no scene cuts: fall back to evenly spaced
        # anchors across the whole source.
        step_back = max(1, int(max_dur))
        anchors = {round(x, 2) for x in [0.0] + list(range(int(duration), 0, -step_back))}
    from .activity import activity_anchors
    for t in activity_anchors(visual,audio):
        anchors.add(round(max(0.,t-min_dur*.4),2))
    anchors.add(0.0)
    # An anchor is usable when a full-length clip can still start there.
    latest = max(0.0, duration - min_dur)
    anchors = {a for a in anchors if 0 <= a <= latest}

    windows: list[tuple[float, float]] = []
    for a in sorted(anchors):
        for length in (min_dur, (min_dur + max_dur) / 2, max_dur):
            s = a
            e = min(duration, a + length)
            if e - s >= min_dur - 0.01:
                windows.append((s, e))

    # The source may be shorter than the shortest requested clip.  Rather
    # than returning nothing, offer the whole source as one clip so the
    # user still gets a usable result.
    if not windows and duration > 1.0:
        windows.append((0.0, duration))
    # Deduplicate
    seen = set()
    out = []
    for w in windows:
        key = (round(w[0], 1), round(w[1], 1))
        if key not in seen:
            seen.add(key)
            out.append(w)
    return out


def detect_clips(
    duration: float,
    audio: AudioAnalysis,
    visual: VisualAnalysis,
    transcript: Transcript | None,
    speaker: SpeakerTrack | None = None,
    min_duration: float = 30.0,
    max_duration: float = 45.0,
    target_count: int = 10,
    progress_cb: Callable[[float, str], None] | None = None,
    selected_ranges: list[tuple[float, float]] | None = None,
    selection_policy=None, selection_report=None, selection_host='http://127.0.0.1:11434',
    selection_model='llama3.1:8b', cancel_cb=None,
) -> list[ClipCandidate]:
    """Rank candidate windows and return the best ``target_count`` distinct clips."""
    if duration <= 0:
        return []

    min_dur = max(5.0, float(min_duration))
    max_dur = max(min_dur + 1.0, float(max_duration))

    windows = _candidate_windows(duration, min_dur, max_dur, transcript, visual, audio)
    if selected_ranges:
        limited = set()
        for left, right in selected_ranges:
            left, right = max(0., float(left)), min(duration, float(right))
            if right <= left:
                raise ValueError("Selected source ranges must have a positive duration")
            # Add windows inside each user selection, even if the full-video
            # candidate generator had no speech/scene boundary in that region.
            span = min(max_dur, right-left)
            cursor = left
            while cursor < right - min(5., span) + 0.001:
                limited.add((round(cursor,3), round(min(right,cursor+span),3)))
                cursor += max(5., span*.65)
            for s,e in windows:
                s,e = max(left,s), min(right,e)
                if e-s >= min(min_dur,right-left): limited.add((s,e))
        windows = sorted(limited)
    if progress_cb:
        progress_cb(20.0, f"Scoring {len(windows)} candidate windows")

    from .activity import loudness_jumps
    activity_jumps=loudness_jumps(audio)
    scored: list[ClipCandidate] = []
    for i, (s, e) in enumerate(windows):
        if cancel_cb and cancel_cb():
            from ..core.ffmpeg import FFmpegCancelled
            raise FFmpegCancelled()
        if progress_cb and i % 20 == 0:
            progress_cb(
                20.0 + (i / max(1, len(windows))) * 60.0,
                f"Scoring window {i + 1}/{len(windows)}",
            )
        text = ""
        if transcript:
            text = transcript.text_between(s, e)
        scores, reasons, keywords = _score_signals(
            s, e, text, audio, visual, transcript, speaker, activity_jumps
        )
        cand = ClipCandidate(
            start=s, end=e,
            text=text,
            transcript_text=text,
            reasons=reasons,
            keywords=keywords,
            signal_scores=scores,
        )
        cand.engagement_score = _engagement_score(scores)
        cand.virality_score = _virality_score(scores, cand, audio)
        cand.word_count = len(_tokens(text))
        cand.hook_suggestions = _generate_hooks(text, s, transcript)
        cand.title = _make_title(text, keywords, i)
        if speaker:
            cx, cy, _ = subject_center_at(speaker, visual, (s + e) / 2)
            cand.subject_center = (cx, cy)
        scored.append(cand)

    if progress_cb:
        progress_cb(82.0, "Ranking and de-duplicating clips")

    if selection_policy is not None:
        from .automatic_selection import select
        chosen,report=select(scored,duration,target_count,selection_policy,
            host=selection_host,model=selection_model,cancel_cb=cancel_cb)
        if selection_report is not None:selection_report.update(report)
        for candidate in chosen:candidate.description=_make_description(candidate)
        if progress_cb:progress_cb(100.,f'Selected {len(chosen)} distinct eligible clips')
        return chosen

    # --- de-duplicate: reject windows that overlap heavily with a better clip ------
    scored.sort(key=lambda c: c.virality_score, reverse=True)
    chosen: list[ClipCandidate] = []
    for cand in scored:
        if len(chosen) >= target_count:
            break
        # Reject if this window overlaps an existing clip on more than 25% of its
        # duration -- short-form clips need to feel genuinely different.
        overlap = False
        for other in chosen:
            lo = max(cand.start, other.start)
            hi = min(cand.end, other.end)
            shorter = min(cand.duration, other.duration)
            if shorter > 0 and (hi - lo) / shorter > 0.25:
                overlap = True
                break
        if not overlap:
            chosen.append(cand)

    # If we could not fill the target with distinct windows, relax the overlap rule.
    if len(chosen) < target_count:
        for cand in scored:
            if len(chosen) >= target_count:
                break
            if cand not in chosen:
                chosen.append(cand)

    chosen.sort(key=lambda c: c.start)
    for i, c in enumerate(chosen):
        c.description = _make_description(c)
    if progress_cb:
        progress_cb(100.0, f"Selected {len(chosen)} clips")
    return chosen


def _make_description(cand: ClipCandidate) -> str:
    """Short human description of why this clip was chosen."""
    text = cand.transcript_text.strip()
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
    if sentences:
        body = " ".join(sentences[:2])
        if len(body) > 200:
            body = body[:197] + "…"
        return body
    if cand.reasons:
        return " · ".join(cand.reasons[:3])
    return "A visually and vocally energetic segment."

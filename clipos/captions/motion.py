"""Local ASS caption motion; no generated timing or external assets."""
from __future__ import annotations

import math


def motion_tags(mode: str, duration: int, width: int, height: int,
                alignment: int, margin: int) -> str:
    if mode == 'none':
        return ''
    duration = max(1, duration)
    enter = min(240, max(1, duration // 3))
    settle = min(duration, enter * 2)
    exit_ms = min(140, max(0, duration // 5))
    x = 60 if alignment % 3 == 1 else width-60 if alignment % 3 == 0 else width//2
    y = height-margin if alignment <= 3 else height//2 if alignment <= 6 else margin
    distance = max(8, round(height * .025))
    fade = f'\\fad({min(90, enter)},{exit_ms})'
    if mode == 'fade':
        tags = f'\\fad({enter},{exit_ms})'
    elif mode == 'pop':
        tags = (f'\\fscx72\\fscy72\\t(0,{enter},\\fscx110\\fscy110)'
                f'\\t({enter},{settle},\\fscx100\\fscy100){fade}')
    elif mode == 'slide_up':
        tags = f'\\move({x},{y+distance},{x},{y},0,{enter}){fade}'
    elif mode == 'slide_left':
        tags = f'\\move({x+distance},{y},{x},{y},0,{enter}){fade}'
    elif mode == 'zoom_out':
        tags = f'\\fscx135\\fscy135\\t(0,{settle},\\fscx100\\fscy100){fade}'
    elif mode == 'tilt':
        tags = f'\\frz-9\\t(0,{settle},\\frz0){fade}'
    elif mode == 'blur_reveal':
        tags = (f'\\blur8\\fscx94\\fscy94'
                f'\\t(0,{settle},\\blur0\\fscx100\\fscy100){fade}')
    elif mode == 'pulse':
        middle = max(1, duration//2)
        tags = (f'\\fscx100\\fscy100\\t(0,{middle},\\fscx108\\fscy108)'
                f'\\t({middle},{duration},\\fscx100\\fscy100){fade}')
    else:
        raise ValueError(f'Unknown caption animation: {mode}')
    return '{' + tags + '}'


def timed_words(cue, mode: str, uppercase: bool):
    """Return events only when existing word timing matches edited cue text.

    Reject malformed, unordered, overlapping or out-of-cue words. A caption with
    unavailable word evidence is still rendered with a cue-level fallback.
    """
    if mode not in ('word_pop', 'word_reveal') or not cue.words:
        return []
    if len(cue.words) > 200:
        return []
    words = []
    previous_end = cue.start
    for word in cue.words:
        if not isinstance(word, dict):
            return []
        text, start, end = word.get('w'), word.get('s'), word.get('e')
        if not isinstance(text, str) or not text.strip():
            return []
        if any(isinstance(t, bool) or not isinstance(t, (int, float))
               or not math.isfinite(t) for t in (start, end)):
            return []
        if not cue.start <= start < end <= cue.end or start < previous_end:
            return []
        words.append((text.strip(), start, end))
        previous_end = end
    if ' '.join(cue.text.split()) != ' '.join(text for text, _, _ in words):
        return []
    events = []
    for index, (text, start, end) in enumerate(words):
        # Hold through inter-word gaps, never beyond the cue's real boundary.
        end = words[index+1][1] if index+1 < len(words) else cue.end
        if mode == 'word_reveal':
            text = ' '.join(w[0] for w in words[:index+1])
        events.append((start, end, text.upper() if uppercase else text))
    return events

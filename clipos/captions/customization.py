"""Validated caption overrides shared by Studio preview and both export paths.

Empty values inherit the preset. Never mutate the registered preset or source cues.
"""
from __future__ import annotations

import math
import re
from dataclasses import replace

ANIMATIONS = ('none', 'fade', 'pop', 'slide_up', 'slide_left', 'zoom_out',
              'tilt', 'blur_reveal', 'pulse', 'word_pop', 'word_reveal')
CATEGORIES = ('All', 'Gaming', 'Viral', 'Podcast', 'Minimal', 'Cinematic',
              'Educational', 'Reaction', 'Custom')


def ass_color(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Caption colors must be #RRGGBB')
    return '&H00' + value[5:7].upper() + value[3:5].upper() + value[1:3].upper()


def customize_style(style, primary='', highlight='', outline='', animation='', alignment=''):
    overrides = {}
    for key, value in [('primary_color', primary), ('highlight_color', highlight),
                       ('outline_color', outline)]:
        if value:
            overrides[key] = ass_color(value)
    if animation:
        if animation not in ANIMATIONS:
            raise ValueError('Unsupported caption animation')
        overrides['animation'] = animation
    if alignment:
        if alignment not in ('left', 'center', 'right'):
            raise ValueError('Unsupported caption alignment')
        overrides['alignment'] = ((style.alignment - 1) // 3) * 3 + ('left', 'center', 'right').index(alignment) + 1
    return replace(style, **overrides)


def offset_cues(cues, offset):
    if isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset) or abs(offset) > 10:
        raise ValueError('Caption offset must be between -10 and 10 seconds')
    if offset == 0:
        return cues
    shifted = []
    for cue in cues:
        start, end = max(0., cue.start + offset), cue.end + offset
        if end <= start:
            continue
        words = []
        for word in cue.words:
            if (not isinstance(word, dict) or any(isinstance(word.get(k), bool)
                    or not isinstance(word.get(k), (int, float))
                    or not math.isfinite(word[k]) for k in ('s', 'e'))):
                words = [];break
            shifted_word = {**word, 's': max(start, word['s'] + offset),
                            'e': min(end, word['e'] + offset)}
            if shifted_word['e'] <= shifted_word['s']:
                words = [];break
            words.append(shifted_word)
        shifted.append(replace(cue, start=start, end=end, words=words))
    return shifted


def categories_for(key):
    """Curated browsing groups; a preset may belong to multiple uses."""
    groups = {'All'}
    if key.startswith('arcade_') or key in ('neon_gaming',):
        groups.update(('Gaming', 'Reaction'))
    if key.startswith('impact_') or key in ('mrbeast', 'bold_viral'):
        groups.update(('Viral', 'Reaction'))
    if key.startswith('studio_'):
        groups.update(('Podcast', 'Educational', 'Minimal'))
    if key in ('minimal_white', 'clean_professional', 'modern_podcast'):
        groups.update(('Podcast', 'Educational', 'Minimal'))
    if key in ('clean_professional', 'cinematic', 'karaoke'):
        groups.update(('Cinematic', 'Minimal', 'Educational'))
    return groups

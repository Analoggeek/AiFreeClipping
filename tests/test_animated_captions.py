"""Thirty presets must generate and actually rasterize changing ASS content."""
import subprocess

import numpy as np
import pytest

from clipos.captions.caption_engine import (
    CAPTION_STYLES, CaptionCue, get_style, list_styles, render_ass, write_ass,
)
from clipos.captions.motion import timed_words
from clipos.core.ffmpeg import require_ffmpeg

ANIMATED = [key for key, style in CAPTION_STYLES.items() if style.animation != 'none']


def sample():
    return CaptionCue(0, 1, 'Real captions', [
        {'w':'Real','s':0,'e':.45}, {'w':'captions','s':.5,'e':1},
    ])


def test_thirty_distinct_combinations_are_exposed_through_existing_registry():
    assert len(ANIMATED) == 30
    assert len(CAPTION_STYLES) == 38
    assert len({render_ass([sample()],get_style(key)) for key in ANIMATED}) == 30
    assert all(item['animation'] != 'none' for item in list_styles() if item['key'] in ANIMATED)
    assert get_style('bold_viral').animation == 'none'  # Legacy appearance retained.


@pytest.mark.parametrize('key',ANIMATED)
@pytest.mark.parametrize('word_timing',[True,False])
def test_every_animated_preset_renders_visible_temporally_changing_pixels(key,word_timing,tmp_path):
    try:
        ffmpeg=require_ffmpeg()
    except Exception:
        pytest.skip('FFmpeg not installed')
    # Relative simple path avoids platform-specific filter-path quoting here.
    cue=sample()
    if not word_timing:cue.words=[]
    write_ass(tmp_path/'captions.ass',[cue],get_style(key),360,640,size_override=32)
    proc=subprocess.run([ffmpeg,'-v','error','-nostdin','-f','lavfi','-i',
        'color=black:s=360x640:r=5:d=1','-vf','ass=captions.ass,scale=160:284',
        '-frames:v','5','-pix_fmt','rgb24','-f','rawvideo','-'],
        cwd=tmp_path,capture_output=True,timeout=20)
    assert proc.returncode==0,proc.stderr.decode(errors='replace')
    frames=np.frombuffer(proc.stdout,dtype=np.uint8).reshape(5,284,160,3)
    assert frames[1].max()>100, f'{key}: invisible at 0.2 s'
    assert np.count_nonzero(frames[1]!=frames[3])>20, f'{key}: no visible motion/change'


def test_timed_words_use_real_timestamps_and_never_render_stale_text():
    cue=sample()
    assert timed_words(cue,'word_pop',False)==[(0,.5,'Real'),(.5,1,'captions')]
    assert timed_words(cue,'word_reveal',True)==[(0,.5,'REAL'),(.5,1,'REAL CAPTIONS')]
    cue.text='Edited replacement'
    assert timed_words(cue,'word_pop',False)==[]
    document=render_ass([cue],get_style('studio_word_pop'))
    assert 'Edited replacement' in document
    assert 'Real captions' not in document
    assert '\\t(' in document  # Functional cue-pop fallback, no fake word timings.


@pytest.mark.parametrize('words',[
    [], [{'w':'Real','s':0,'e':float('nan')}],
    [{'w':'Real','s':-.1,'e':.4}], [{'w':'Real','s':0,'e':2}],
    [{'w':'Real','s':True,'e':.4}],
    [{'w':'Real','s':0,'e':.6},{'w':'captions','s':.5,'e':1}],
])
def test_missing_or_invalid_timing_falls_back_without_inventing_words(words):
    cue=sample();cue.words=words
    assert timed_words(cue,'word_reveal',False)==[]
    document=render_ass([cue],get_style('studio_word_reveal'))
    assert document.count('Dialogue:')==1 and '\\fad(' in document


def test_ass_text_is_escaped_and_position_override_honored():
    cue=CaptionCue(0,1,'{\\pos(0,0)} safe',[])
    document=render_ass([cue],get_style('studio_slide_up'),position_override='top')
    assert '{\\pos(0,0)}' not in document
    assert '\\move(540,288,540,240,0,240)' in document

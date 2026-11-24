"""Actual decoded waveform envelope, cancellation, cache and invalidation tests."""
import subprocess
from unittest.mock import patch

import pytest

from clipos.core.ffmpeg import require_ffmpeg,FFmpegCancelled
from clipos.video.waveform import build_waveform,source_signature


def test_real_source_waveform_has_silence_and_tone_and_reuses_cache(tmp_path):
    source=tmp_path/'pulses.wav'
    subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i',
        "aevalsrc=if(lt(t\\,0.5)\\,0\\,0.5*sin(2*PI*440*t)):s=8000:d=1",str(source)],
        check=True,capture_output=True)
    cache=tmp_path/'cache';data=build_waveform(source,cache)
    assert max(data['peaks'][:3000])==0
    assert max(data['peaks'][4500:])==pytest.approx(.5,abs=.005)
    assert len(data['peaks'])<=60000 and data['sample_rate']==8000
    with patch('clipos.video.waveform.probe',side_effect=AssertionError('should use cache')):
        assert build_waveform(source,cache)==data
    old=source_signature(source);source.write_bytes(source.read_bytes()+b'changed')
    assert source_signature(source)!=old


def test_waveform_cancellation_preserves_cache_and_cleans_pcm(tmp_path):
    source=tmp_path/'source.wav'
    subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i','sine=duration=1',str(source)],check=True,capture_output=True)
    cache=tmp_path/'cache';build_waveform(source,cache)
    old={p.name:p.read_bytes() for p in cache.glob('*.json')}
    with pytest.raises(FFmpegCancelled):build_waveform(source,cache,cancel_cb=lambda:True)
    assert {p.name:p.read_bytes() for p in cache.glob('*.json')}==old
    assert not list(cache.glob('.waveform-*'))


def test_malformed_waveform_cache_is_rebuilt_from_real_audio(tmp_path):
    source=tmp_path/'source.wav'
    subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i','sine=duration=0.2',str(source)],check=True,capture_output=True)
    cache=tmp_path/'cache';cache.mkdir()
    (cache/(source_signature(source)+'.json')).write_text('{invalid')
    assert build_waveform(source,cache)['peaks']

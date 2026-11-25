"""Real FFmpeg PCM tests: measured ducking, not just graph substring checks."""
import subprocess

import numpy as np
import pytest

from clipos.core.ffmpeg import require_ffmpeg
from clipos.video.audio_mix import music_mix_parts
from clipos.video.renderer import RenderSettings, _build_audio_filter


def render_pcm(ducking, has_voice=True, volume=.5):
    ffmpeg=require_ffmpeg()
    parts, output=music_mix_parts('[0:a]',1,4,volume,ducking,has_voice)
    proc=subprocess.run([ffmpeg,'-v','error','-nostdin','-f','lavfi','-i',
        "aevalsrc='if(between(t,1,2),0.4*sin(2*PI*440*t),0)':s=48000:d=4",
        '-f','lavfi','-i','sine=frequency=1000:sample_rate=48000:duration=4,volume=2',
        '-filter_complex',';'.join(parts),'-map',output,'-ar','48000','-ac','1',
        '-f','f32le','-'],capture_output=True,timeout=20)
    assert proc.returncode==0,proc.stderr.decode(errors='replace')
    return np.frombuffer(proc.stdout,dtype='<f4')


def amplitude(samples,frequency,start,end):
    segment=samples[round(start*48000):round(end*48000)]
    t=np.arange(len(segment))/48000
    return 2*abs(np.mean(segment*np.exp(-2j*np.pi*frequency*t)))


def test_source_signal_reduces_music_and_recovers_without_lowering_voice():
    fixed=render_pcm(False)
    ducked=render_pcm(True)
    assert len(ducked)/48000==pytest.approx(4,abs=.05)
    assert amplitude(ducked,1000,1.4,1.8)<amplitude(fixed,1000,1.4,1.8)*.6
    assert amplitude(ducked,1000,3.2,3.6)>amplitude(ducked,1000,1.4,1.8)*1.5
    assert amplitude(ducked,440,1.4,1.8)==pytest.approx(amplitude(fixed,440,1.4,1.8),rel=.05)
    assert np.max(np.abs(ducked))<=.951


def test_fixed_mix_preserves_foreground_gain_and_music_volume_is_separate():
    quiet=render_pcm(False,volume=.1)
    loud=render_pcm(False,volume=.8)
    assert amplitude(quiet,440,1.4,1.8)==pytest.approx(.4,rel=.05)
    assert amplitude(loud,440,1.4,1.8)==pytest.approx(.4,rel=.05)
    assert amplitude(loud,1000,3.2,3.6)>amplitude(quiet,1000,3.2,3.6)*7
    assert _build_audio_filter(RenderSettings(normalize_audio=False,noise_reduction=False),'existing.wav')==''


@pytest.mark.parametrize('volume',[float('nan'),float('inf'),-.1,1.1,True])
def test_invalid_level_rejected(volume):
    with pytest.raises(ValueError):music_mix_parts('[a]',1,4,volume,True,True)


def test_silent_sources_do_not_add_sidechain_branch():
    parts,_=music_mix_parts('[a]',1,4,.1,True,False)
    assert 'sidechaincompress' not in ';'.join(parts)


def test_shared_persisted_settings_reach_both_render_modes(tmp_path):
    from clipos.db.database import Database
    from clipos.core.editing import render_settings
    db=Database(tmp_path/'prefs.db')
    db.set_settings({'background_music':'/local/music.wav','bgm_volume':.22,'bgm_ducking':False})
    settings=render_settings(db)
    assert settings.background_music=='/local/music.wav'
    assert settings.bgm_volume==.22 and not settings.bgm_ducking
    assert RenderSettings.from_dict(settings.to_dict()).bgm_ducking is False
    db.close()


@pytest.mark.parametrize('timeline_mode',[False,True])
def test_missing_selected_music_fails_actionably_before_export(tmp_path,timeline_mode):
    from clipos.video.renderer import ClipRenderer
    from clipos.video.timeline import Timeline
    renderer=ClipRenderer(tmp_path/'work')
    settings=RenderSettings(background_music=str(tmp_path/'missing.wav'))
    with pytest.raises(FileNotFoundError,match='Background music is missing'):
        if timeline_mode:
            renderer.render_timeline(tmp_path/'source.mp4',tmp_path/'out.mp4',Timeline.from_clip(0,2),settings)
        else:
            renderer.render(tmp_path/'source.mp4',tmp_path/'out.mp4',0,2,settings)

"""Diarization boundary and actual worker isolation, NOT real trained-model acceptance."""
import json
from pathlib import Path
import wave
from unittest.mock import patch

import numpy as np
import pytest

from clipos.ai.diarization import diarize,normalize_turns,word_speaker,DiarizationUnavailable
from clipos.core.ffmpeg import FFmpegCancelled


def test_neural_turn_normalization_preserves_overlap_and_anonymous_labels():
    turns=normalize_turns([{'start':1.,'end':2.,'speaker':99},
        {'start':0.,'end':1.5,'speaker':5}],2)
    assert turns[0]['speaker']=='Speaker A' and turns[1]['speaker']=='Speaker B'
    assert word_speaker(.1,.5,turns)=='Speaker A'
    assert word_speaker(1.1,1.4,turns) is None
    assert word_speaker(1.6,1.9,turns)=='Speaker B'
    assert word_speaker(2,3,turns) is None


@pytest.mark.parametrize('row',[
    {'start':float('nan'),'end':1.,'speaker':0},
    {'start':-1,'end':1.,'speaker':0},
    {'start':0.,'end':3.,'speaker':0},
    {'start':0.,'end':1.,'speaker':True},
])
def test_invalid_model_output_rejected(row):
    with pytest.raises(ValueError):normalize_turns([row],2)


def files(tmp_path):
    wav=tmp_path/'audio.wav'
    with wave.open(str(wav),'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(16000)
        stream.writeframes(np.zeros(1600,dtype='<i2').tobytes())
    seg=tmp_path/'seg.onnx';emb=tmp_path/'embed.onnx'
    # Deliberately invalid: exercise isolation, never claim detector/voice inference.
    seg.write_bytes(b'not a model');emb.write_bytes(b'not a model')
    return wav,seg,emb


def test_missing_weights_never_spawn_or_download(tmp_path):
    with patch('clipos.ai.diarization.subprocess.Popen') as popen:
        with pytest.raises(DiarizationUnavailable,match='no automatic download'):
            diarize(tmp_path/'none.wav',tmp_path/'seg.onnx',tmp_path/'embed.onnx',tmp_path/'out.json')
        popen.assert_not_called()


def test_invalid_native_weights_are_isolated_and_preserve_previous_output(tmp_path):
    pytest.importorskip('sherpa_onnx')
    wav,seg,emb=files(tmp_path)
    output=tmp_path/'diarization.json';output.write_text('previous result')
    with pytest.raises(DiarizationUnavailable,match='worker failed'):
        diarize(wav,seg,emb,output)
    assert output.read_text()=='previous result'
    assert not list(tmp_path.glob('.diarization-*'))


def test_cancellation_kills_worker_without_replacing_result(tmp_path):
    wav,seg,emb=files(tmp_path)
    output=tmp_path/'diarization.json';output.write_text('previous result')
    with pytest.raises(FFmpegCancelled):diarize(wav,seg,emb,output,cancel_cb=lambda:True)
    assert output.read_text()=='previous result'
    assert not list(tmp_path.glob('.diarization-*'))


def test_duplicate_turns_do_not_inflate_word_speaker_evidence():
    turns=[{'start':0,'end':.4,'speaker':'Speaker A'}]*3
    assert word_speaker(0,1,turns) is None


def test_packaged_worker_entry_routes_before_gui_startup(monkeypatch):
    import sys
    from clipos import app
    import clipos.ai.diarization as engine
    calls=[]
    monkeypatch.setattr(sys,'argv',['CLIPOS','--diarize-worker','local-request.json'])
    monkeypatch.setattr(app,'_prepare_environment',lambda:None)
    monkeypatch.setattr(engine,'worker_main',lambda args:calls.append(args) or 17)
    assert app.main()==17 and calls==[['local-request.json']]

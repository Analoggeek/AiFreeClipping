"""Source decode/association contracts; fake logits are not trained model accuracy."""
from contextlib import nullcontext
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from clipos.ai.visual_analysis import Face,FaceTrack,VisualAnalysis,SceneCuts
from clipos.core.ffmpeg import FFmpegCancelled,require_ffmpeg


def test_talknet_shot_schedule_and_crop_are_bounded_and_local():
    from clipos.ai.active_speaker import shot_windows,face_crop
    import cv2
    visual=VisualAnalysis(duration=20,scenes=SceneCuts(times=[8]))
    assert shot_windows(visual)==[(0.,8.,3.,2.),(8.,20,13.,2.)]
    frame=np.full((90,160,3),255,np.uint8)
    crop=face_crop(frame,Face(.1,.2,.2,.3),cv2)
    assert crop.shape==(112,112) and crop.dtype==np.uint8
    with pytest.raises(ValueError):face_crop(frame,Face(-1,0,.2,.3),cv2)
    visual.scenes.times=list(range(1,98));visual.duration=100
    with pytest.raises(ValueError):shot_windows(visual)


def test_active_face_evidence_overrides_prominence_but_not_other_shots(tmp_path):
    from clipos.video.shot_reframe import shot_centers,validate_binding
    from clipos.video.waveform import source_signature
    source=tmp_path/'source';source.write_bytes(b'original')
    visual=VisualAnalysis(duration=2,scenes=SceneCuts(times=[1]),tracks=[
        FaceTrack(1,[Face(.1,.2,.4,.4,timestamp=t) for t in (0,.3,1.,1.3)]),
        FaceTrack(2,[Face(.7,.2,.1,.2,timestamp=t) for t in (0,.3,1.,1.3)])])
    visual.active_speaker={'status':'available','source_signature':source_signature(source),
        'shots':[{'start':0,'end':1,'track_id':2}]}
    validate_binding(visual,source)
    centers=shot_centers(visual,0,2)
    assert centers[0][2]==pytest.approx(.75)
    assert centers[1][2]==pytest.approx(.3)
    source.write_bytes(b'changed length')
    with pytest.raises(ValueError):validate_binding(visual,source)


def test_model_paths_never_trigger_hub_fetch(tmp_path):
    from clipos.ai.active_speaker import load_model
    from clipos.ai.game_sound import load_model as sound_model
    with pytest.raises(ValueError):load_model('')
    with pytest.raises(ValueError):sound_model('')
    (tmp_path/'config.json').write_text(json.dumps({'model_type':'arbitrary_remote_code'}))
    with pytest.raises(ValueError):sound_model(str(tmp_path))
    (tmp_path/'config.json').write_text(json.dumps({'model_type':'audio-spectrogram-transformer'}))
    (tmp_path/'pytorch_model.bin').write_bytes(b'pickle must not be loaded')
    with pytest.raises(ValueError,match='safetensors'):sound_model(str(tmp_path))


def test_sound_decodes_real_pcm_and_preserves_labelled_model_scores(tmp_path):
    from clipos.ai.game_sound import review
    source=tmp_path/'sound.wav'
    subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i',
        'sine=frequency=440:duration=1','-ar','48000',str(source)],check=True,capture_output=True)
    samples=[]
    def extract(audio,**kwargs):
        samples.append(audio)
        assert kwargs=={'sampling_rate':16000,'return_tensors':'pt'}
        return {'input_values':audio}
    class Scores:
        def __getitem__(self,key):return self
        def cpu(self):return self
        def numpy(self):return np.array([.2,.8])
    model=SimpleNamespace(config=SimpleNamespace(id2label={0:'Speech',1:'Music'}))
    class Model:
        config=model.config
        def __call__(self,**kwargs):return SimpleNamespace(logits='fake logits')
    fake_torch=SimpleNamespace(inference_mode=nullcontext,sigmoid=lambda logits:Scores())
    with patch('clipos.ai.game_sound.load_model',return_value=(extract,Model(),'a'*64)),patch.dict(sys.modules,torch=fake_torch):
        result=review(source,[{'id':'a','start':0.,'end':1.}],'local')
        assert len(samples)==1 and len(samples[0])==16000
        assert np.max(abs(samples[0]))>.05
        assert result[0]['sound'][0]['labels'][0]=={'label':'Music','score':.8}
        assert result[0]['scene']=='unknown'
        with pytest.raises(FFmpegCancelled):review(source,[{'id':'a','start':0.,'end':1.}],'local',cancel_cb=lambda:True)


def test_provider_cancellation_is_not_downgraded_to_unavailable(tmp_path):
    from clipos.ai.game_evidence import review
    from clipos.video.waveform import source_signature
    source=tmp_path/'source';source.write_bytes(b'source')
    with patch('clipos.ai.game_sound.review',side_effect=FFmpegCancelled()):
        with pytest.raises(FFmpegCancelled):
            review(source,[{'id':'x','start':0.,'end':1.}],signature=source_signature(source),sound=True)


def test_sound_provider_failures_do_not_discard_ocr(tmp_path):
    from clipos.ai.game_evidence import review
    from clipos.video.waveform import source_signature
    source=tmp_path/'source';source.write_bytes(b'source')
    with patch('clipos.ai.game_sound.review',side_effect=ValueError('model missing')),patch('clipos.ai.game_ocr.review',
        return_value=[{'id':'x','ocr':[{'text':'VICTORY'}],'model_hashes':{}}]):
        result=review(source,[{'id':'x','start':0.,'end':1.}],signature=source_signature(source),sound=True,ocr=True)
    assert result[0]['providers']['sound'].startswith('unavailable:')
    assert result[0]['ocr'][0]['text']=='VICTORY'


def test_optional_talknet_architecture_safe_checkpoint_and_cpu_forward(tmp_path):
    torch=pytest.importorskip('torch')
    from clipos.ai._talknet.talkNetModel import talkNetModel
    from clipos.ai.active_speaker import load_model
    torch.set_num_threads(2)
    model=talkNetModel().eval();head=torch.nn.Linear(256,2).eval()
    state={'model.'+key:value for key,value in model.state_dict().items()}
    state.update({'lossAV.FC.'+key:value for key,value in head.state_dict().items()})
    path=tmp_path/'random-state.pt';torch.save(state,path)
    loaded,classifier,digest=load_model(str(path))
    assert len(digest)==64
    # Random weights only test compatibility, never active-speaker quality.
    with torch.inference_mode():
        audio=loaded.forward_audio_frontend(torch.zeros(1,100,13))
        video=loaded.forward_visual_frontend(torch.zeros(1,25,112,112))
        audio,video=loaded.forward_cross_attention(audio,video)
        scores=classifier(loaded.forward_audio_visual_backend(audio,video))
    assert scores.shape==(25,2) and torch.isfinite(scores).all()
    del state['lossAV.FC.bias'];torch.save(state,path)
    with pytest.raises(RuntimeError):load_model(str(path))


def test_optional_ast_real_runtime_local_safetensors_and_audio_forward(tmp_path):
    torch=pytest.importorskip('torch')
    pytest.importorskip('transformers')
    pytest.importorskip('torchaudio')
    from transformers import ASTConfig,ASTFeatureExtractor,ASTForAudioClassification
    from clipos.ai.game_sound import review
    torch.set_num_threads(2)
    model_dir=tmp_path/'ast';model_dir.mkdir()
    config=ASTConfig(hidden_size=24,num_hidden_layers=1,num_attention_heads=3,
        intermediate_size=48,num_labels=2,id2label={0:'Synthetic class A',1:'Synthetic class B'})
    # Random weights establish local loading/runtime compatibility ONLY.
    ASTForAudioClassification(config).save_pretrained(model_dir,safe_serialization=True)
    ASTFeatureExtractor().save_pretrained(model_dir)
    source=tmp_path/'sine.wav'
    subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i',
        'sine=frequency=440:duration=1','-ar','16000',str(source)],check=True,capture_output=True)
    with patch('socket.socket.connect',side_effect=AssertionError('No network allowed for local AST inference')):
        result=review(source,[{'id':'actual-runtime','start':0.,'end':1.}],str(model_dir))
    assert len(result[0]['sound'][0]['labels'])==2
    assert all(0<=item['score']<=1 for item in result[0]['sound'][0]['labels'])
    assert len(result[0]['model_sha256'])==64


def test_acceptance_runner_rejects_absent_models_and_input_overwrite(tmp_path):
    from scripts import accept_real_models
    source=tmp_path/'source.mp4';source.write_bytes(b'do not overwrite')
    model=tmp_path/'checkpoint.model';model.write_bytes(b'checkpoint')
    with patch.object(sys,'argv',['accept','--video',str(source),'--talknet',str(model),'--report',str(model)]):
        with pytest.raises(SystemExit) as error:accept_real_models.main()
        assert error.value.code==2
    assert model.read_bytes()==b'checkpoint'
    with patch.object(sys,'argv',['accept','--video',str(source),'--report',str(tmp_path/'report.json')]):
        with pytest.raises(SystemExit) as error:accept_real_models.main()
        assert error.value.code==2

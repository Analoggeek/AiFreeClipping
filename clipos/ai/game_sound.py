"""Offline AudioSet AST inference on bounded candidate audio, never outcome detection.

User supplies a local Transformers AST checkpoint with safetensors. No remote
code, pickle weights, model hub lookup, or automatic model downloads are allowed.
"""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import wave

import numpy as np

from ..core.ffmpeg import FFmpegRunner, FFmpegCancelled
from ..video.waveform import source_signature


def load_model(directory):
    root=Path(directory).expanduser()
    if not directory or not root.is_dir():raise ValueError('Choose an explicitly downloaded local AST model directory')
    config=json.loads((root/'config.json').read_text())
    if config.get('model_type')!='audio-spectrogram-transformer':raise ValueError('Sound model must be an AST audio classifier')
    weights=root/'model.safetensors'
    if not weights.is_file() or weights.stat().st_size>2_000_000_000:raise ValueError('Local AST model.safetensors required (maximum 2GB)')
    if not (root/'preprocessor_config.json').is_file():raise ValueError('Local AST preprocessor config missing')
    from transformers import ASTFeatureExtractor, ASTForAudioClassification
    extractor=ASTFeatureExtractor.from_pretrained(str(root),local_files_only=True)
    model=ASTForAudioClassification.from_pretrained(str(root),local_files_only=True,use_safetensors=True).cpu().eval()
    if extractor.sampling_rate!=16000:raise ValueError('Sound model must accept 16kHz audio')
    digest=hashlib.sha256()
    with weights.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
    return extractor,model,digest.hexdigest()


def review(source,rows,directory,*,cancel_cb=None):
    if not 1<=len(rows)<=4:raise ValueError('Sound review supports one to four finalists')
    for row in rows:
        if any(type(row[k]) not in (int,float) or not math.isfinite(row[k]) for k in ('start','end')) or not 0<=row['start']<row['end']:
            raise ValueError('Invalid sound candidate range')
    if cancel_cb and cancel_cb():raise FFmpegCancelled()
    signature=source_signature(source)
    extractor,model,digest=load_model(directory)
    import torch
    output=[]
    with tempfile.TemporaryDirectory(prefix='clipos-sound-') as temp:
        for row in rows:
            events=[]
            # Three non-overlapping short windows at most; long clips cannot
            # allocate unbounded PCM/features. Short clips are evaluated once.
            start,end=row['start'],row['end'];length=min(10.,end-start)
            times=sorted(set([start] if end-start<=10 else [start,start+(end-start-length)/2,end-length]))
            for timestamp in times:
                if cancel_cb and cancel_cb():raise FFmpegCancelled()
                path=Path(temp)/'window.wav'
                FFmpegRunner(cancel_cb=cancel_cb).run(['-y','-ss',str(timestamp),'-i',str(source),'-t',str(length),
                    '-map','0:a:0','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(path)])
                with wave.open(str(path),'rb') as wav:
                    if wav.getnframes()>160_001 or wav.getsampwidth()!=2 or wav.getnchannels()!=1:raise ValueError('Unexpected sound PCM format')
                    audio=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(np.float32)/32768.
                if not len(audio):raise ValueError('No audio samples for sound review')
                inputs=extractor(audio,sampling_rate=16000,return_tensors='pt')
                with torch.inference_mode():scores=torch.sigmoid(model(**inputs).logits)[0].cpu().numpy()
                if scores.ndim!=1 or not np.isfinite(scores).all():raise ValueError('Invalid sound model logits')
                labels=[]
                for index in np.argsort(scores)[-5:][::-1]:
                    label=model.config.id2label.get(int(index))
                    if not isinstance(label,str) or len(label)>160:raise ValueError('Invalid sound model label map')
                    labels.append({'label':label,'score':float(scores[index])})
                events.append({'start':timestamp,'end':timestamp+length,'labels':labels})
            output.append({'id':row['id'],'sound':events,'model_sha256':digest,'scene':'unknown'})
    if cancel_cb and cancel_cb():raise FFmpegCancelled()
    if source_signature(source)!=signature:raise ValueError('Source changed during sound review')
    return output

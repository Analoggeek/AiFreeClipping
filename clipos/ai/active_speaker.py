"""Local TalkNet audiovisual face-track evidence; raw logits, not probabilities.

Architecture provenance: _talknet/__init__.py. Explicit user-supplied trusted
checkpoint only, safe tensor-only load, CPU inference. Never downloads weights.
Anonymous face track IDs are not named people or diarization speaker identities.
"""
import hashlib
import math
from pathlib import Path
import wave

import numpy as np

from ..core.ffmpeg import FFmpegCancelled
from ..video.waveform import source_signature
from .visual_analysis import cv2_module


def load_model(checkpoint):
    path=Path(checkpoint).expanduser()
    if not checkpoint or not path.is_file() or not 0<path.stat().st_size<=500_000_000:
        raise ValueError('Choose a trusted local TalkNet checkpoint (maximum 500MB)')
    try:
        import torch
    except ImportError as exc:raise ValueError('Install optional TalkNet runtime with scripts/install_deps.py --talknet') from exc
    from importlib.metadata import version
    from packaging.version import Version
    if Version(version('torch').split('+')[0])<Version('2.6'):
        raise ValueError('TalkNet checkpoint loading requires PyTorch 2.6 or newer for safe tensor-only loading')
    from ._talknet.talkNetModel import talkNetModel
    network=talkNetModel().cpu().eval();head=torch.nn.Linear(256,2).cpu().eval()
    state=torch.load(str(path),map_location='cpu',weights_only=True)
    if not isinstance(state,dict):raise ValueError('Invalid TalkNet checkpoint state')
    state={k.removeprefix('module.'):v for k,v in state.items() if isinstance(k,str)}
    network.load_state_dict({k[6:]:v for k,v in state.items() if k.startswith('model.')},strict=True)
    head.load_state_dict({k[10:]:v for k,v in state.items() if k.startswith('lossAV.FC.')},strict=True)
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
    return network,head,digest.hexdigest()


def shot_windows(visual):
    duration=visual.duration
    if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid active-speaker duration')
    cuts=sorted({float(t) for t in visual.scenes.times if math.isfinite(t) and 0<t<duration})
    if len(cuts)>95:raise ValueError('Active-speaker review supports at most 96 source shots')
    edges=[0.,*cuts,duration]
    return [(a,b,(a+b)/2-min(2.,b-a)/2,min(2.,b-a)) for a,b in zip(edges,edges[1:]) if b-a>=.5]


def face_crop(frame,face,cv2):
    values=(face.x,face.y,face.w,face.h)
    if not all(math.isfinite(v) for v in values) or min(face.w,face.h)<=0 or face.x<0 or face.y<0 or face.x+face.w>1.001 or face.y+face.h>1.001:
        raise ValueError('Invalid active-speaker face box')
    h,w=frame.shape[:2];cx,cy=face.center
    # TalkNet demo's context expansion and central 112px grayscale crop.
    half=max(face.w*w,face.h*h)/2;pad=int(math.ceil(half*1.8))
    padded=cv2.copyMakeBorder(frame,pad,pad,pad,pad,cv2.BORDER_CONSTANT,value=(110,110,110))
    x,y=cx*w+pad,cy*h+pad
    region=padded[int(y-half):int(y+half*1.8),int(x-half*1.4):int(x+half*1.4)]
    if not region.size:raise ValueError('Empty active-speaker crop')
    return cv2.cvtColor(cv2.resize(region,(224,224)),cv2.COLOR_BGR2GRAY)[56:168,56:168]


def analyze(source,wav_path,visual,checkpoint,*,cancel_cb=None):
    if cancel_cb and cancel_cb():raise FFmpegCancelled()
    signature=source_signature(source);windows=shot_windows(visual)
    network,head,digest=load_model(checkpoint)
    import torch
    from python_speech_features import mfcc
    cv2=cv2_module()
    if cv2 is None:raise ValueError('OpenCV unavailable for audiovisual review')
    capture=cv2.VideoCapture(str(source));observations=[]
    try:
        if not capture.isOpened():raise ValueError('Cannot decode active-speaker source')
        with wave.open(str(wav_path),'rb') as wav:
            if (wav.getframerate(),wav.getnchannels(),wav.getsampwidth())!=(16000,1,2):raise ValueError('TalkNet requires 16kHz mono PCM16 source audio')
            for left,right,start,length in windows:
                if cancel_cb and cancel_cb():raise FFmpegCancelled()
                count=int(length*25)
                eligible=[]
                for track in visual.tracks:
                    faces=[f for f in track.faces if left<=f.timestamp<right]
                    if faces and all(min(abs(f.timestamp-(start+i/25)) for f in faces)<=.6 for i in range(count)):
                        eligible.append((track,faces))
                # Bounded and explicit: don't silently omit additional people.
                if len(eligible)>4:raise ValueError('Active-speaker window has more than four eligible face tracks')
                if not eligible:continue
                wav.setpos(min(wav.getnframes(),int(start*16000)))
                audio=np.frombuffer(wav.readframes(int(length*16000)),dtype='<i2')
                if len(audio)<8000:continue
                features=mfcc(audio,16000,numcep=13,winlen=.025,winstep=.010)
                count=min(count,len(features)//4)
                if count<12:continue
                crops={track.track_id:[] for track,_ in eligible}
                for i in range(count):
                    if cancel_cb and cancel_cb():raise FFmpegCancelled()
                    t=start+i/25;capture.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=capture.read()
                    if not ok:raise ValueError('Cannot decode aligned TalkNet frame')
                    for track,faces in eligible:
                        face=min(faces,key=lambda f:abs(f.timestamp-t))
                        crops[track.track_id].append(face_crop(frame,face,cv2))
                scores=[]
                with torch.inference_mode():
                    audio_input=torch.from_numpy(features[:count*4].astype(np.float32)).unsqueeze(0)
                    audio_embed=network.forward_audio_frontend(audio_input)
                    for track,_ in eligible:
                        if cancel_cb and cancel_cb():raise FFmpegCancelled()
                        video=torch.from_numpy(np.asarray(crops[track.track_id],dtype=np.float32)).unsqueeze(0)
                        visual_embed=network.forward_visual_frontend(video)
                        a,v=network.forward_cross_attention(audio_embed,visual_embed)
                        logits=head(network.forward_audio_visual_backend(a,v))[:,1].cpu().numpy()
                        if not np.isfinite(logits).all():raise ValueError('Non-finite TalkNet output')
                        scores.append({'track_id':track.track_id,'raw_logit':float(np.mean(logits))})
                scores.sort(key=lambda item:-item['raw_logit'])
                # Conservative evidence threshold, not calibrated confidence.
                winner=scores[0]['track_id'] if scores[0]['raw_logit']>0 and (len(scores)==1 or scores[0]['raw_logit']-scores[1]['raw_logit']>=.5) else None
                observations.append({'start':left,'end':right,'sample_start':start,'sample_end':start+count/25,
                    'scores':scores,'track_id':winner})
        if source_signature(source)!=signature:raise ValueError('Source changed during active-speaker inference')
        return {'status':'available','source_signature':signature,'model_sha256':digest,
                'method':'TalkNet CPU audiovisual raw logits; sampled shot evidence','shots':observations}
    except cv2.error as exc:raise ValueError('Active-speaker frame preprocessing failed') from exc
    finally:capture.release()

"""Measured local activity, not semantic excitement or a virality prediction.

Independent Farneback residual-flow / preceding-baseline loudness measurements.
Bounded images, no extra decoders, cloud inference, downloads or FFT of whole audio.
"""
from __future__ import annotations
import math
import numpy as np


def flow_activity(previous,current,dt=1.,scene_cut=False):
    """Return normalized subject-motion activity and a hard-cut flag.

    Subtract median optical flow so a coherent camera pan is not treated as a
    moving subject. Sparse >2 s samples cannot support flow; return no evidence.
    """
    from .visual_analysis import cv2_module
    cv2=cv2_module()
    if cv2 is None or previous is None or not 0<dt<=2:return 0.,bool(scene_cut)
    prev=cv2.resize(previous,(160,90));cur=cv2.resize(current,(160,90))
    if prev.ndim==3:prev=cv2.cvtColor(prev,cv2.COLOR_BGR2GRAY)
    if cur.ndim==3:cur=cv2.cvtColor(cur,cv2.COLOR_BGR2GRAY)
    difference=float(cv2.absdiff(prev,cur).mean())/255
    hp=cv2.calcHist([prev],[0],None,[16],[0,256]);hc=cv2.calcHist([cur],[0],None,[16],[0,256])
    hist_distance=cv2.compareHist(hp,hc,cv2.HISTCMP_BHATTACHARYYA)
    cut=bool(scene_cut or difference>.4 or (difference>.15 and hist_distance>.6))
    if cut:return 0.,True
    flow=cv2.calcOpticalFlowFarneback(prev,cur,None,.5,3,15,3,5,1.2,0)
    interior=flow[8:-8,8:-8]
    residual=interior-np.median(interior,axis=(0,1))
    magnitude=np.linalg.norm(residual,axis=2)
    # Fixed physical scale: no per-video normalization inflating tiny noise to 1.
    value=float(np.percentile(magnitude,95))/max(.01,dt)/12
    return max(0.,min(1.,value)),False


def loudness_jumps(audio):
    """One dB-rise score/second vs previous 15 s, never a future-padded baseline."""
    from .audio_analysis import HOP_SECONDS
    if not audio or not audio.rms_db:return []
    size=max(1,round(1/HOP_SECONDS))
    values=np.asarray(audio.rms_db,dtype=np.float32)
    seconds=[float(values[i:i+size].mean()) for i in range(0,len(values),size)]
    result=[]
    for i,value in enumerate(seconds):
        if i<3:result.append(0.);continue
        baseline=float(np.median(seconds[max(0,i-15):i]))
        # 6 dB noise margin, 18 dB meaningful rise; constant music isn't a spike.
        result.append(max(0.,min(1.,(value-baseline-6)/18)))
    return result


def window_activity(start,end,visual,audio,jumps=None):
    motion=[value for t,value in zip(getattr(visual,'keyframe_times',[]),getattr(visual,'motion',[])) if start<=t<end]
    if jumps is None:jumps=loudness_jumps(audio)
    selected=jumps[max(0,int(start)):max(0,math.ceil(end))]
    # Max measures a physical burst, not whether the moment is funny/interesting.
    return max(motion,default=0.),max(selected,default=0.)


def activity_anchors(visual,audio,limit=12):
    pairs=[(value,t) for t,value in zip(getattr(visual,'keyframe_times',[]),getattr(visual,'motion',[]))]
    pairs.extend((value,float(i)) for i,value in enumerate(loudness_jumps(audio)))
    selected=[]
    for value,t in sorted(pairs,reverse=True):
        if value<.12:break
        if all(abs(t-other)>3 for other in selected):selected.append(t)
        if len(selected)>=limit:break
    return sorted(selected)

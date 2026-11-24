"""Static facecam-panel localization supported by repeated face observations.

Independent native-pipeline implementation inspired by DigiRG's static-edge +
face-confirmation approach. No upstream server/decoder code is copied. Static
HUD borders alone are never evidence of a facecam. Results are heuristics, not
human-vs-game-character classification or segmentation.
"""
from __future__ import annotations
import math
import numpy as np


def refine_panel(frames,faces,timestamps,seed,cancel_cb=None):
    from .visual_analysis import cv2_module
    cv2=cv2_module()
    if cv2 is None or seed is None or len(frames)<3:return None
    x,y,w,h=seed.facecam
    support=[f for f in faces if x<=f.center[0]<=x+w and y<=f.center[1]<=y+h]
    if len({f.timestamp for f in support})<3:return None
    width=320;height=max(32,min(320,round(frames[0].shape[0]*width/frames[0].shape[1])))
    counts=np.zeros((height,width),np.float32)
    used=0
    for frame in frames:
        if cancel_cb and cancel_cb():
            from ..core.ffmpeg import FFmpegCancelled
            raise FFmpegCancelled('Panel analysis cancelled')
        gray=cv2.cvtColor(cv2.resize(frame,(width,height)),cv2.COLOR_BGR2GRAY)
        edge=cv2.Canny(cv2.GaussianBlur(gray,(3,3),0),50,130)
        counts+=(cv2.dilate(edge,np.ones((3,3),np.uint8))>0);used+=1
    stable=cv2.dilate((counts/max(1,used)>=.75).astype(np.uint8),np.ones((3,3),np.uint8))
    fx=float(np.median([f.x for f in support]));fy=float(np.median([f.y for f in support]))
    fr=float(np.median([f.x+f.w for f in support]));fb=float(np.median([f.y+f.h for f in support]))
    x0,x1=max(0,int(fx*width)),min(width-1,math.ceil(fr*width))
    y0,y1=max(0,int(fy*height)),min(height-1,math.ceil(fb*height))
    if x1<=x0 or y1<=y0:return None
    vertical=stable[y0:y1+1].mean(axis=0);horizontal=stable[:,x0:x1+1].mean(axis=1)

    def peaks(values,lo,hi,boundary):
        # A bounded set of separated strong edges, plus the true frame boundary.
        choices=[i for i in range(max(0,lo),min(len(values),hi)) if values[i]>=.75]
        choices.sort(key=lambda i:float(values[i]),reverse=True)
        picked=[boundary]
        for i in choices:
            if all(abs(i-j)>3 for j in picked):picked.append(i)
            if len(picked)>=6:break
        return picked
    left=peaks(vertical,round((fr-.50)*width),x0,0)
    right=peaks(vertical,x1+1,round((fx+.50)*width),width-1)
    top=peaks(horizontal,round((fb-.65)*height),y0,0)
    bottom=peaks(horizontal,y1+1,round((fy+.65)*height),height-1)
    best=None
    total=len(set(timestamps))
    for a in left:
        if cancel_cb and cancel_cb():
            from ..core.ffmpeg import FFmpegCancelled
            raise FFmpegCancelled('Panel analysis cancelled')
        for b in right:
            for c in top:
                for d in bottom:
                    pw,ph=(b-a)/width,(d-c)/height
                    if not (.10<=pw<=.5 and .12<=ph<=.65 and .015<=pw*ph<=.30):continue
                    if not .45<=(b-a)/max(1,d-c)<=2.5:continue
                    if not (a<=x0<x1<=b and c<=y0<y1<=d):continue
                    border=min(1. if a==0 else float(stable[c:d+1,a].mean()),
                               1. if b==width-1 else float(stable[c:d+1,b].mean()),
                               1. if c==0 else float(stable[c,a:b+1].mean()),
                               1. if d==height-1 else float(stable[d,a:b+1].mean()))
                    if border<.72:continue
                    observed={f.timestamp for f in support if a/width<=f.x and f.x+f.w<=b/width and c/height<=f.y and f.y+f.h<=d/height}
                    coverage=len(observed)/max(1,total)
                    if coverage<.6:continue
                    # Similar border quality: favour camera context, not eye/mouth boxes.
                    score=.55*coverage+.35*border+.10*min(1,pw*ph/.12)
                    if best is None or score>best[0]:best=(score,(a/width,c/height,pw,ph),border,len(observed))
    if best is None:return None
    from .gaming_layout import GamingLayout
    from ..video.presets import gameplay_outside
    score,box,border,count=best
    try:gameplay=gameplay_outside(box)
    except ValueError:return None
    return GamingLayout(box,gameplay,min(.98,score),count,'static-edge+temporal-face',border)

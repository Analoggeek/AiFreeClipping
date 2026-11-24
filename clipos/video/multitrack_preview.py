"""On-demand decoded multi-source frame compositor. No rendered-video intermediary.

This is a silent, best-effort preview. It is not an audio-clocked playback engine.
"""
from collections import OrderedDict
import math

import numpy as np

from ..ai.visual_analysis import cv2_module
from .multitrack import fade_gain


class FrameCompositor:
    def __init__(self,max_decoders=8):
        self.max_decoders=max_decoders
        self.decoders=OrderedDict()

    def close(self):
        for capture in self.decoders.values():capture.release()
        self.decoders.clear()

    def frame(self,project,time,max_size=640):
        project.validate()
        if not math.isfinite(time) or not 0<=time<=project.duration:raise ValueError('Preview time outside project')
        cv2=cv2_module()
        if cv2 is None:raise RuntimeError('OpenCV unavailable')
        scale=min(1,max_size/max(project.width,project.height))
        width=max(2,round(project.width*scale));height=max(2,round(project.height*scale))
        output=np.zeros((height,width,3),np.uint8)
        sources={media.id:media for media in project.media}
        active=[item for lane in project.lanes if lane.enabled and lane.kind=='video'
                for item in lane.items if item.at<=time<item.at+item.duration]
        if len({item.media_id for item in active})>self.max_decoders:
            raise ValueError('Silent preview supports at most eight simultaneous video sources')
        for item in active:
            path=sources[item.media_id].path
            if path not in self.decoders:
                while len(self.decoders)>=self.max_decoders:
                    _,old=self.decoders.popitem(last=False);old.release()
                capture=cv2.VideoCapture(path)
                if not capture.isOpened():capture.release();raise ValueError(f'Cannot preview media: {path}')
                self.decoders[path]=capture
            capture=self.decoders[path];self.decoders.move_to_end(path)
            fps=capture.get(cv2.CAP_PROP_FPS)
            if not math.isfinite(fps) or fps<=0:raise ValueError('Unknown preview frame rate')
            frame_index=math.floor((item.source_in+(time-item.at)*item.speed)*fps+1e-6)
            if round(capture.get(cv2.CAP_PROP_POS_FRAMES))!=frame_index:
                capture.set(cv2.CAP_PROP_POS_FRAMES,frame_index)
            ok,frame=capture.read()
            if not ok:raise ValueError(f'Cannot decode requested frame: {path}')
            # Match export's even output rectangle before scaling to preview size.
            full_w=max(2,int(item.w*project.width)//2*2);full_h=max(2,int(item.h*project.height)//2*2)
            w=max(1,round(full_w*scale));h=max(1,round(full_h*scale))
            x=round(round(item.x*project.width)*scale);y=round(round(item.y*project.height)*scale)
            w=min(w,width-x);h=min(h,height-y)
            if w<=0 or h<=0:continue
            ratio=max(w/frame.shape[1],h/frame.shape[0])
            resized=cv2.resize(frame,(max(w,math.ceil(frame.shape[1]*ratio)),max(h,math.ceil(frame.shape[0]*ratio))))
            left=(resized.shape[1]-w)//2;top=(resized.shape[0]-h)//2
            layer=resized[top:top+h,left:left+w]
            opacity=item.opacity*fade_gain(item,time-item.at)
            output[y:y+h,x:x+w]=np.round(layer.astype(np.float32)*opacity+
                output[y:y+h,x:x+w].astype(np.float32)*(1-opacity)).astype(np.uint8)
        return output

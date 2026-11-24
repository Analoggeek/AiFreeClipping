"""Body-evidence reframing from streamed person artifacts, not speaker identity."""
from __future__ import annotations

import json
import math
from pathlib import Path


def body_keys(artifact, source, start, end, track_id=0):
    """Read twice with bounded per-track/per-time-bin memory. Never switch IDs.

    Auto chooses the longest-supported ID in this interval (area breaks ties).
    Coverage must exceed 60%; missing evidence bins use neutral framing rather than
    interpolate a person through an occlusion. Returns fixed crop centers.
    """
    if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end:
        raise ValueError('Invalid body-reframe interval')
    if type(track_id) is not int or track_id < 0:
        raise ValueError('Invalid person track ID')
    path=Path(artifact)
    step=max(.25,(end-start)/120)
    count=math.ceil((end-start)/step)+1
    step=(end-start)/(count-1)
    scores={}
    summary=None

    def rows():
        with path.open('rb') as stream:
            while True:
                line=stream.readline(65537)
                if not line:break
                if len(line)>65536:raise ValueError('Oversized person artifact row')
                row=json.loads(line)
                if not isinstance(row,dict):raise ValueError('Invalid person artifact row')
                yield row

    def observation(row):
        if row.get('type')!='person':return None
        values=[row.get(k) for k in ('timestamp','x','y','w','h','confidence')]
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
            raise ValueError('Invalid body observation')
        t,x,y,w,h,confidence=values
        tid=row.get('track_id')
        if type(tid) is not int or tid<1 or not (0<=x<=1 and 0<=y<=1 and 0<w<=1 and 0<h<=1 and x+w<=1.00001 and y+h<=1.00001 and 0<=confidence<=1):
            raise ValueError('Invalid body box/ID')
        if start<=t<=end and confidence>=.1:
            return tid,t,x+w/2,y+h/2,w*h
        return None

    for row in rows():
        if summary is not None:raise ValueError('Person summary must be terminal')
        if row.get('type')=='summary':summary=row;continue
        value=observation(row)
        if value is None:continue
        tid,t,cx,cy,area=value
        if tid not in scores:
            if len(scores)>=256:raise ValueError('Too many body tracks in interval')
            scores[tid]={}
        index=min(count-1,round((t-start)/step))
        scores[tid][index]=max(area,scores[tid].get(index,0))
    if not summary or summary.get('schema_version')!=1 or summary.get('source')!=str(Path(source).resolve()):
        raise ValueError('Missing or mismatched person artifact summary')
    source_stat=Path(source).stat()
    if summary.get('source_size')!=source_stat.st_size or summary.get('source_mtime_ns')!=source_stat.st_mtime_ns:
        raise ValueError('Stale body artifact: re-run tracking for current source media')
    if summary.get('frame_limit_reached'):
        raise ValueError('Incomplete body artifact: frame-limited tracking cannot drive export')
    if not scores:return [],None
    chosen=track_id or max(scores,key=lambda tid:(len(scores[tid]),sum(scores[tid].values()),-tid))
    if chosen not in scores or len(scores[chosen])/count<.6:return [],None
    nearest={}
    for row in rows():
        value=observation(row)
        if value is None or value[0]!=chosen:continue
        _,t,cx,cy,_=value
        index=min(count-1,round((t-start)/step))
        error=abs(t-(start+index*step))
        if index not in nearest or error<nearest[index][0]:nearest[index]=(error,cx,cy)
    keys=[]
    for i in range(count):
        # Do not follow another person or extrapolate across missing evidence.
        if i in nearest:keys.append((nearest[i][1],nearest[i][2]))
        else:keys.append((.5,.5))
    # Suppress sub-pixel-like jitter, but never average a gap into a subject.
    for i in range(1,len(keys)-1):
        if all(j in nearest for j in (i-1,i,i+1)):
            keys[i]=(sum(nearest[j][1] for j in (i-1,i,i+1))/3,
                     sum(nearest[j][2] for j in (i-1,i,i+1))/3)
    return keys,chosen


def body_crop_filter(source_w,source_h,out_w,out_h,keys,duration):
    """Fixed even crop dimensions; only x/y are per-frame FFmpeg expressions."""
    if not keys or duration<=0:raise ValueError('Body crop needs observed keys')
    if source_w/source_h>out_w/out_h:
        height=source_h//2*2;width=max(2,int(height*out_w/out_h)//2*2)
    else:
        width=source_w//2*2;height=max(2,int(width*out_h/out_w)//2*2)
    step=duration/max(1,len(keys)-1)
    def expression(axis):
        if len(keys)==1:return f'{keys[0][axis]:.6f}'
        terms=[]
        for i in range(len(keys)-1):
            a,b=i*step,(i+1)*step
            first,last=keys[i][axis],keys[i+1][axis]
            terms.append(f'if(gte(t,{a:.6f})*lt(t,{b:.6f}),{first:.6f}+({last-first:.6f})*(t-{a:.6f})/{step:.6f},0)')
        terms.append(f'if(gte(t,{duration:.6f}),{keys[-1][axis]:.6f},0)')
        return '+'.join(terms)
    x=f'max(0,min(iw-ow,iw*({expression(0)})-ow/2))'
    y=f'max(0,min(ih-oh,ih*({expression(1)})-oh/2))'
    return f"crop={width}:{height}:x='{x}':y='{y}',scale={out_w}:{out_h}:flags=lanczos,setsar=1"

def retime_body_keys(keys, source_duration, keeps):
    """Map source-relative tracking centers onto the actual silence-cut output."""
    duration=sum(end-start for start,end in keeps)
    if duration<=0 or source_duration<=0:raise ValueError('Invalid body reframe keeps')
    count=max(2,min(121,math.ceil(duration/.25)+1))
    def center(t):
        position=max(0,min(len(keys)-1,t/source_duration*(len(keys)-1)))
        left=int(position);right=min(len(keys)-1,left+1);fraction=position-left
        return tuple(keys[left][i]*(1-fraction)+keys[right][i]*fraction for i in (0,1))
    result=[]
    for i in range(count):
        output_t=i*duration/(count-1)
        offset=0
        for start,end in keeps:
            if output_t<offset+end-start:
                result.append(center(start+output_t-offset));break
            offset+=end-start
        else:result.append(center(keeps[-1][1]))
    return result,duration

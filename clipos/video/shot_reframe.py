"""Shot-held face framing: never smooth identities/positions across camera cuts.

Subject choice is explicitly face-coverage/prominence, NOT audiovisual speaking
identity. Manual/gaming/body policies retain their own priority at the caller.
"""
import math
import statistics


def shot_centers(visual,start,end):
    cuts=sorted({float(t) for t in visual.scenes.times if math.isfinite(t) and start<t<end})
    if not cuts:return []
    if len(cuts)>95:raise ValueError('Shot-held reframing supports at most 96 shots per segment')
    edges=[start,*cuts,end];output=[]
    for left,right in zip(edges,edges[1:]):
        candidates=[]
        for track in visual.tracks:
            faces=[f for f in track.faces if left<=f.timestamp<right and
                   all(math.isfinite(v) and 0<=v<=1 for v in (*f.center,f.area))]
            if faces:candidates.append((len(faces),statistics.median(f.area for f in faces),track.track_id,faces))
        if candidates:
            # Stable tie break; choose ONE track, not the mean position of two people.
            _,_,_,faces=max(candidates,key=lambda row:(row[0],row[1],-row[2]))
            cx=statistics.median(f.center[0] for f in faces);cy=statistics.median(f.center[1] for f in faces)
        else:cx,cy=.5,.5  # no evidence from another shot is carried forward
        output.append((left,right,cx,cy))
    return output


def crop_filter(visual,start,end,keeps,source_w,source_h,width,height):
    shots=shot_centers(visual,start,end)
    if not shots:return None
    crop_w=min(source_w,source_h*width/height);crop_h=min(source_h,source_w*height/width)
    crop_w=max(2,int(crop_w)//2*2);crop_h=max(2,int(crop_h)//2*2)
    intervals=[];offset=0.
    for a,b in keeps:
        for left,right,cx,cy in shots:
            l,r=max(start+a,left),min(start+b,right)
            if r>l:
                x=max(0,min(source_w-crop_w,cx*source_w-crop_w/2))
                y=max(0,min(source_h-crop_h,cy*source_h-crop_h/2))
                intervals.append((offset+l-start-a,offset+r-start-a,x,y))
        offset+=b-a
    def expression(axis):
        return '+'.join(f"{row[axis]:.6f}*gte(t,{row[0]:.8f})*lt(t,{row[1]:.8f})" for row in intervals) or '0'
    return f"crop={crop_w}:{crop_h}:x='{expression(2)}':y='{expression(3)}',scale={width}:{height},setsar=1"

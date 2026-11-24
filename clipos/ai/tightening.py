"""Independent conservative cleanup proposals from measured silence, never ASR gaps.

Source-time keeps remain reviewable; no silent automatic mutation. Speech/word
protection avoids treating apparent silence as permission to remove known words.
"""
from __future__ import annotations

from dataclasses import replace
import math
import uuid


def propose(start,end,silences,words=()):
    if not all(type(v) in (int,float) and math.isfinite(v) for v in (start,end)) or not 0<=start<end:
        raise ValueError('Invalid cleanup source interval')
    cuts=[]
    for row in silences:
        if len(row)!=2:raise ValueError('Invalid measured silence')
        a,b=row
        if not all(type(v) in (int,float) and math.isfinite(v) for v in (a,b)) or b<=a:
            raise ValueError('Invalid measured silence')
        a,b=max(start,a),min(end,b)
        if b-a<.65:continue
        left=a if a<=start+.001 else a+.18
        right=b if b>=end-.001 else b-.18
        if right-left<.25:continue
        # If the transcript puts a word in the proposed cut, abstain on that gap.
        if any(w.start<right+.08 and w.end>left-.08 for w in words):continue
        cuts.append([left,right])
    merged=[]
    for a,b in sorted(cuts):
        if merged and a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
        else:merged.append([a,b])
    keeps=[];cursor=start
    for a,b in merged:
        if a-cursor>=.25:keeps.append([cursor,a])
        elif a>cursor:
            # Do not silently absorb tiny potentially meaningful islands.
            return {'start':start,'end':end,'keep':[[start,end]],'removed_seconds':0.,'reason':'Tiny keep island; proposal withheld'}
        cursor=b
    if end-cursor>=.25:keeps.append([cursor,end])
    elif end>cursor:
        return {'start':start,'end':end,'keep':[[start,end]],'removed_seconds':0.,'reason':'Tiny end island; proposal withheld'}
    if not keeps or len(keeps)>2000:keeps=[[start,end]]
    return {'start':start,'end':end,'keep':keeps,'removed_seconds':max(0.,end-start-sum(b-a for a,b in keeps)),
            'reason':'Audio-measured silence only; word protection + breath padding; no filler removal'}


def apply_to_timeline(timeline,proposal):
    """Intersect existing edits with reviewed source-time keeps, preserving their order/properties."""
    start,end=proposal['start'],proposal['end'];keeps=proposal['keep']
    if not all(type(v) in (int,float) and math.isfinite(v) for v in (start,end)) or not 0<=start<end:
        raise ValueError('Invalid proposal bounds')
    if not isinstance(keeps,list) or not 1<=len(keeps)<=2000:raise ValueError('Invalid keep list')
    previous=start
    for pair in keeps:
        if not isinstance(pair,list) or len(pair)!=2:raise ValueError('Invalid keep interval')
        a,b=pair
        if not all(type(v) in (int,float) and math.isfinite(v) for v in (a,b)) or not start<=a<b<=end or a<previous:
            raise ValueError('Invalid keep interval')
        previous=b
    segments=[]
    for segment in timeline.segments:
        if segment.start<start-.001 or segment.end>end+.001:
            raise ValueError('Current timeline extends outside proposal; rerun analysis for this range')
        for a,b in keeps:
            left,right=max(segment.start,a),min(segment.end,b)
            if right>left:
                if right-left<.25:raise ValueError('Cleanup would create a tiny existing edit; adjust manually')
                if len(segments)>=10000:raise ValueError('Cleanup would exceed timeline segment limit')
                segments.append(replace(segment,id=uuid.uuid4().hex,start=left,end=right))
    if not segments:raise ValueError('Cleanup cannot remove the entire timeline')
    before=sum(s.duration for s in timeline.segments);after=sum(s.duration for s in segments)
    if abs(before-after)<.001:return False
    timeline.apply('automatic_cleanup','Apply reviewed silence cleanup',segments)
    return True

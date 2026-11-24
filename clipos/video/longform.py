"""Opt-in long-form downtime planning and bounded chronological FFmpeg assembly.

Cuts require BOTH measured sustained silence and a frozen picture, not low speech
or missing transcript. No downloaded models, source uploads or hidden publishing.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import tempfile

from ..core.ffmpeg import FFmpegRunner,FFmpegCancelled,probe
from .timeline import Timeline,Segment
from .waveform import source_signature


def _intervals(log,prefix,duration):
    result=[];start=None
    for kind,value in re.findall(r'\b'+prefix+r'_(start|end):\s*(-?\d+(?:\.\d+)?)',log):
        value=max(0.,min(duration,float(value)))
        if kind=='start':start=value
        elif start is not None:
            if value>start:result.append((start,value))
            start=None
    if start is not None and start<duration:result.append((start,duration))
    return result


def downtime_keeps(duration,quiet,frozen,minimum=8.,padding=.6):
    if type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=21600:
        raise ValueError('Long-form source must be within 6 hours')
    cuts=[]
    for a,b in quiet:
        for c,d in frozen:
            left,right=max(a,c),min(b,d)
            if right-left>=minimum:
                left+=padding;right-=padding
                if right>left:cuts.append((left,right))
    merged=[]
    for a,b in sorted(cuts):
        if not 0<=a<b<=duration:raise ValueError('Invalid downtime evidence')
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(merged[-1][1],b))
        else:merged.append((a,b))
    keeps=[];cursor=0.
    for a,b in merged:
        if a-cursor>=.25:keeps.append((cursor,a))
        else:return [(0.,duration)]
        cursor=b
    if duration-cursor>=.25:keeps.append((cursor,duration))
    elif cursor<duration:return [(0.,duration)]
    return keeps or [(0.,duration)]


def analyse(source,plan_path,*,cancel_cb=None,progress_cb=None):
    source=Path(source).resolve();plan_path=Path(plan_path)
    if plan_path.resolve()==source:raise ValueError('Plan cannot overwrite source')
    signature=source_signature(source);info=probe(source)
    if not info.has_video or not 0<info.duration<=21600:raise ValueError('Select video up to six hours')
    quiet=[];frozen=[]
    if info.has_audio:
        # At most 120 seconds per decoder and log. Minimum detected gaps of 8s
        # keep evidence well inside the FFmpegRunner bounded log buffer.
        for offset in range(0,math.ceil(info.duration),120):
            if cancel_cb and cancel_cb():raise FFmpegCancelled()
            span=min(120.,info.duration-offset)
            log=FFmpegRunner(total_duration=span,cancel_cb=cancel_cb,
                progress_cb=lambda pct,t,o=offset:progress_cb((o+t)/info.duration*100,'Measuring frozen + quiet intervals') if progress_cb else None).run([
                '-threads','2','-ss',str(offset),'-t',str(span),'-i',str(source),
                '-vf','scale=160:90,freezedetect=n=-45dB:d=8',
                '-af','silencedetect=noise=-45dB:d=8','-f','null','-'])
            quiet.extend((a+offset,b+offset) for a,b in _intervals(log,'silence',span))
            frozen.extend((a+offset,b+offset) for a,b in _intervals(log,'freeze',span))
    keeps=downtime_keeps(info.duration,quiet,frozen)
    timeline=Timeline(source_duration=info.duration,segments=[Segment(f'seg{i+1}',a,b) for i,(a,b) in enumerate(keeps)])
    payload={'schema':'clipos.longform.v1','source':str(source),'source_signature':signature,
             'policy':'quiet <= -45 dBFS AND frozen picture >=8s; 0.6s padding',
             'quiet':quiet,'frozen':frozen,'timeline':timeline._save_data(),
             'removed_seconds':info.duration-timeline.duration}
    if source_signature(source)!=signature:raise ValueError('Source changed during long-form analysis')
    if cancel_cb and cancel_cb():raise FFmpegCancelled()
    plan_path.parent.mkdir(parents=True,exist_ok=True)
    Timeline._atomic_write(plan_path,json.dumps(payload,allow_nan=False).encode())
    return payload


def load(path):
    path=Path(path)
    if path.stat().st_size>8*1024*1024:raise ValueError('Plan exceeds 8 MiB')
    data=json.loads(path.read_text())
    if data.get('schema')!='clipos.longform.v1':raise ValueError('Unsupported long-form plan')
    source=Path(data['source'])
    if not source.is_absolute() or source_signature(source)!=data['source_signature']:raise ValueError('Plan source is missing/stale')
    timeline=Timeline._from_data(data['timeline'])
    if timeline.is_empty or len(timeline.segments)>2000:raise ValueError('Plan must have 1–2000 keep segments')
    if any(s.speed!=1 or s.zoom!=1 or s.muted for s in timeline.segments):raise ValueError('Long-form assembler accepts unchanged-speed source keeps only')
    if any(a.end>b.start for a,b in zip(timeline.segments,timeline.segments[1:])):raise ValueError('Long-form keeps must be chronological')
    return data,timeline


def export(plan_path,output,*,cancel_cb=None,progress_cb=None,width=1920,height=1080):
    data,timeline=load(plan_path);source=Path(data['source']);output=Path(output)
    if output.suffix.lower()!='.mp4' or output.resolve() in (source.resolve(),Path(plan_path).resolve()):
        raise ValueError('Select MP4 output separate from source and plan')
    if any(type(v) is not int or v%2 or not 16<=v<=3840 for v in (width,height)):raise ValueError('Invalid output canvas')
    info=probe(source)
    if abs(info.duration-timeline.source_duration)>.2 or not info.has_video:raise ValueError('Long-form plan duration does not match source')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.longform-',dir=output.parent) as temporary:
        root=Path(temporary);parts=[]
        for index,segment in enumerate(timeline.segments):
            if cancel_cb and cancel_cb():raise FFmpegCancelled()
            part=root/f'part-{index:05d}.mp4';parts.append(part)
            audio=[] if info.has_audio else ['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
            FFmpegRunner(total_duration=segment.duration,cancel_cb=cancel_cb,
                progress_cb=lambda p,t,i=index:progress_cb((i+p/100)/len(timeline.segments)*95,'Encoding chronological keep segments') if progress_cb else None).run([
                '-threads','2','-ss',str(segment.start),'-t',str(segment.source_duration),'-i',str(source),*audio,
                '-map','0:v:0','-map','0:a:0' if info.has_audio else '1:a:0',
                '-vf',f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30',
                '-c:v','libx264','-preset','fast','-crf','21','-pix_fmt','yuv420p','-threads','2',
                '-c:a','aac','-ar','48000','-ac','2','-b:a','160k','-t',str(segment.duration),str(part)])
        listing=root/'parts.txt';listing.write_text(''.join(f"file '{part.name}'\n" for part in parts))
        target=root/'complete.mp4'
        FFmpegRunner(total_duration=timeline.duration,cancel_cb=cancel_cb).run([
            '-f','concat','-safe','1','-i',listing.as_posix(),'-c','copy','-movflags','+faststart',str(target)])
        result=probe(target)
        if not result.has_video or not result.has_audio or abs(result.duration-timeline.duration)>max(.25,len(parts)*.07):
            raise ValueError('Long-form output duration/streams do not match plan')
        if source_signature(source)!=data['source_signature']:raise ValueError('Source changed during long-form export')
        if cancel_cb and cancel_cb():raise FFmpegCancelled()
        os.replace(target,output)
    if progress_cb:progress_cb(100,'Long-form MP4 exported')
    return {'output_path':str(output),'duration':result.duration,'segments':len(parts),'size_bytes':output.stat().st_size,'encoder':'libx264 CPU'}

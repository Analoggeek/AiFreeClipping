"""Actual overlapping multi-source export, not a flattened single-source timeline."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time

from ..core.ffmpeg import FFmpegRunner, probe
from ..core.hardware import choose_encoder
from .renderer import RenderResult, tempo_filter, _filter_args


def graph(project,work_dir=None,window=None):
    """Return inputs/filter graph for enabled video layers and independent audio lanes."""
    project.validate()
    duration=project.duration
    if not 0<duration<=21600:raise ValueError('Export duration must be within 0–6 hours')
    media={source.id:source for source in project.media}
    active=[(lane,item) for lane in project.lanes if lane.enabled for item in lane.items
            if window is None or (item.at < window[0]+window[1] and item.at+item.duration > window[0])]
    if len(active)>64:raise ValueError('Current export supports at most 64 active items')
    for source_id in {item.media_id for lane,item in active if lane.kind in ('video','audio')}:
        source=media[source_id]
        if not Path(source.path).is_file():raise FileNotFoundError(f'Missing media: {source.path}')
        info=probe(source.path)
        if abs(info.duration-source.duration)>.2 or info.has_video!=source.has_video or info.has_audio!=source.has_audio:
            raise ValueError(f'Media changed: reimport/relink {source.path}')
    inputs=[]
    parts=[f'color=c=black:s={project.width}x{project.height}:r={project.fps}:d={duration:.6f}[canvas]',
           f'anullsrc=r=48000:cl=stereo,atrim=duration={duration:.6f}[silence]']
    base='[canvas]';audio=['[silence]'];input_index=0
    for index,(lane,item) in enumerate(active):
        if lane.kind=='transition':continue
        if lane.kind=='effect':
            parts.append(f"{base}eq=brightness={item.brightness:.8f}:contrast={item.contrast:.8f}:saturation={item.saturation:.8f}:enable='gte(t,{item.at:.6f})*lt(t,{item.at+item.duration:.6f})'[effect{index}]")
            base=f'[effect{index}]';continue
        if lane.kind=='caption':
            if work_dir is None:raise ValueError('Caption export requires a work directory')
            from hashlib import sha256
            from .overlay_tracks import write_caption
            from .renderer import _ass_filter
            caption_path=Path(work_dir)/('lane-'+sha256(item.id.encode()).hexdigest()[:24]+'.ass')
            write_caption(caption_path,item,project.width,project.height)
            parts.append(f'{base}{_ass_filter(caption_path)}[caption{index}]')
            base=f'[caption{index}]';continue
        source=media[item.media_id]
        stream=input_index;input_index+=1
        inputs+=['-threads','2','-ss',f'{item.source_in:.6f}','-t',f'{item.length:.6f}','-i',source.path]
        if lane.kind=='video':
            width=max(2,int(item.w*project.width)//2*2)
            height=max(2,int(item.h*project.height)//2*2)
            x=round(item.x*project.width);y=round(item.y*project.height)
            parts.append(f'[{stream}:v]setpts=(PTS-STARTPTS)/{item.speed:.8f},fps={project.fps},'
                f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},'
                f'setsar=1,' + video_effects(item) + 'format=rgba,' + video_opacity(item) +
                video_fades(item) + dissolve_filter(project,item) +
                f'setpts=PTS+{item.at:.6f}/TB[layer{index}]')
            parts.append(f'{base}[layer{index}]overlay=x={x}:y={y}:eof_action=pass:repeatlast=0:'
                f"enable='gte(t,{item.at:.6f})*lt(t,{item.at+item.duration:.6f})'[composite{index}]")
            base=f'[composite{index}]'
        else:
            delay=round(item.at*1000)
            parts.append(f'[{stream}:a]asetpts=PTS-STARTPTS,{tempo_filter(item.speed)},'
                f'aresample=48000,aformat=channel_layouts=stereo,' + audio_gain(item) +
                f'atrim=duration={item.duration:.6f},' + audio_envelope(item) + f'adelay={delay}|{delay}[audio{index}]')
            audio.append(f'[audio{index}]')
    # Compensate amix averaging; limit peaks without auto loudness boosting.
    parts.append(''.join(audio)+f'amix=inputs={len(audio)}:duration=first:dropout_transition=0,'
        f'volume={len(audio)},alimiter=limit=0.95:level=0[aout]')
    return inputs,';'.join(parts),base,'[aout]'


def export_project(project,output,work_dir,*,encoder='auto',progress_cb=None,cancel_cb=None,window=None):
    output=Path(output)
    if output.suffix.lower()!='.mp4':raise ValueError('Multitrack export requires an .mp4 path')
    if output.resolve() in {Path(media.path).resolve() for media in project.media}:
        raise ValueError('Export cannot overwrite source media')
    work_dir=Path(work_dir);work_dir.mkdir(parents=True,exist_ok=True)
    import math
    if window is not None:
        if (not isinstance(window,(tuple,list)) or len(window)!=2 or
            any(type(v) not in (int,float) or not math.isfinite(v) for v in window) or
            window[0]<0 or window[1]<=0 or window[0]+window[1]>project.duration+1e-6):
            raise ValueError('Invalid timeline export window')
    duration=window[1] if window is not None else project.duration
    inputs,filters,video,audio=graph(project,work_dir,window=window)
    if window is not None:
        start,end=window[0],window[0]+window[1]
        filters+=f';{video}trim=start={start:.8f}:end={end:.8f},setpts=PTS-STARTPTS[windowvideo]'
        filters+=f';{audio}atrim=start={start:.8f}:end={end:.8f},asetpts=PTS-STARTPTS[windowaudio]'
        video,audio='[windowvideo]','[windowaudio]'
    output.parent.mkdir(parents=True,exist_ok=True)
    work_dir=Path(work_dir);work_dir.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.multitrack-',suffix='.mp4',dir=output.parent)
    os.close(fd)
    result=RenderResult(output_path=str(output),width=project.width,height=project.height)
    started=time.monotonic()
    def command(choice):
        codec=['-c:v',choice.video_encoder]
        if not choice.is_hardware:codec+=['-preset','fast','-crf','21']
        else:
            codec+=['-b:v','8M']
            if choice.hw_accel=='videotoolbox':codec+=['-allow_sw','0']
        return ['-hide_banner','-nostdin','-y','-filter_complex_threads','2',*inputs,
            *_filter_args(filters,work_dir,Path(temp).stem),'-map',video,'-map',audio,*codec,
            '-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-t',f'{duration:.6f}',
            '-movflags','+faststart','-threads','2',temp]
    try:
        choice=choose_encoder(encoder)
        try:
            FFmpegRunner(total_duration=duration,progress_cb=progress_cb,cancel_cb=cancel_cb).run(command(choice))
        except Exception as exc:
            from ..core.ffmpeg import FFmpegCancelled
            if isinstance(exc,FFmpegCancelled) or not choice.is_hardware:raise
            result.warnings.append(f'Hardware encoding failed; CPU retry: {exc}')
            choice=choose_encoder('cpu')
            FFmpegRunner(total_duration=duration,progress_cb=progress_cb,cancel_cb=cancel_cb).run(command(choice))
        info=probe(temp)
        if not info.has_video or not info.has_audio or info.duration<=0:raise ValueError('Invalid multitrack export')
        if (info.video.width,info.video.height)!=(project.width,project.height) or abs(info.duration-duration)>max(.25,2/project.fps):
            raise ValueError('Encoded dimensions/duration differ from timeline export configuration')
        os.replace(temp,output)
        result.encoder=choice.description;result.duration=info.duration;result.size_bytes=output.stat().st_size
        result.elapsed=time.monotonic()-started
        result.steps.append('Rendered independent multi-source video layers and audio tracks')
        return result
    finally:
        if os.path.exists(temp):os.unlink(temp)


def audio_preview_command(project,start):
    """Raw stereo PCM from the requested timeline position, no video rendering."""
    from ..core.ffmpeg import require_ffmpeg
    import math
    project.validate()
    if not math.isfinite(start) or not 0<=start<project.duration:raise ValueError('Audio seek outside project')
    duration=project.duration-start
    sources={source.id:source for source in project.media}
    inputs=[];labels=['[silence]']
    parts=[f'anullsrc=r=48000:cl=stereo,atrim=duration={duration:.6f}[silence]']
    index=0
    for lane in project.lanes:
        if not lane.enabled or lane.kind!='audio':continue
        for item in lane.items:
            if item.at+item.duration<=start:continue
            source=sources[item.media_id]
            if not Path(source.path).is_file():raise FileNotFoundError(f'Missing audio: {source.path}')
            offset=max(0,start-item.at)
            source_in=item.source_in+offset*item.speed
            length=item.length-offset*item.speed
            delay=round(max(0,item.at-start)*1000)
            inputs+=['-threads','2','-ss',f'{source_in:.6f}','-t',f'{length:.6f}','-i',source.path]
            parts.append(f'[{index}:a]asetpts=PTS-STARTPTS,{tempo_filter(item.speed)},aresample=48000,'
                f'aformat=channel_layouts=stereo,' + audio_gain(item,offset) + audio_envelope(item,offset) + f'adelay={delay}|{delay}[p{index}]')
            labels.append(f'[p{index}]');index+=1
    if index>64:raise ValueError('Audio preview supports at most 64 items')
    parts.append(''.join(labels)+f'amix=inputs={len(labels)}:duration=first:dropout_transition=0,'
        f'volume={len(labels)},alimiter=limit=0.95:level=0[pcm]')
    return [require_ffmpeg(),'-hide_banner','-nostdin','-v','error','-filter_complex_threads','2',*inputs,
            '-filter_complex',';'.join(parts),'-map','[pcm]','-t',f'{duration:.6f}',
            '-ac','2','-ar','48000','-f','s16le','-']


def video_fades(item):
    result=''
    if item.fade_in:result+=f'fade=t=in:st=0:d={item.fade_in:.8f}:alpha=1,'
    if item.fade_out:result+=f'fade=t=out:st={item.duration-item.fade_out:.8f}:d={item.fade_out:.8f}:alpha=1,'
    return result


def audio_envelope(item,offset=0.):
    # Evaluate in output seconds BEFORE timeline delay, including preview seek.
    terms=['1']
    if item.fade_in:terms.append(f'max(0,(t+{offset:.8f})/{item.fade_in:.8f})')
    if item.fade_out:terms.append(f'max(0,({item.duration:.8f}-t-{offset:.8f})/{item.fade_out:.8f})')
    expression=terms[0]
    for term in terms[1:]:expression=f'min({expression},{term})'
    return f"volume='{expression}':eval=frame," if len(terms)>1 else ''


def curve_expression(keys,clock):
    expression=f'{keys[-1][1]:.10f}'
    for (a,x),(b,y) in reversed(list(zip(keys,keys[1:]))):
        segment=f'({x:.10f}+({y-x:.10f})*({clock}-{a:.10f})/{b-a:.10f})'
        expression=f'if(lt({clock},{b:.10f}),{segment},{expression})'
    return f'if(lte({clock},{keys[0][0]:.10f}),{keys[0][1]:.10f},{expression})'


def audio_gain(item,offset=0.):
    expression=curve_expression(item.gain_keys,f'(t+{offset:.10f})') if item.gain_keys else f'{item.gain:.10f}'
    return f"volume='{expression}':eval=frame,"


def video_opacity(item):
    if not item.opacity_keys:return f'colorchannelmixer=aa={item.opacity:.10f},'
    expression=curve_expression(item.opacity_keys,'T')
    return f"format=gbrap,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({expression})',"


def video_effects(item):
    """Per-layer actual color and rotation filters, before alpha automation."""
    filters=[]
    if (item.brightness,item.contrast,item.saturation)!=(0.,1.,1.):
        filters.append(f'eq=brightness={item.brightness:.8f}:contrast={item.contrast:.8f}:saturation={item.saturation:.8f}')
    if item.rotation:
        filters.append(f'rotate={item.rotation:.8f}*PI/180:ow=iw:oh=ih:c=black')
    return ','.join(filters)+(',' if filters else '')


def dissolve_filter(project,item):
    from .overlay_tracks import dissolve_duration
    duration=dissolve_duration(project,item.id)
    return f'fade=t=in:st=0:d={duration:.8f}:alpha=1,' if duration else ''

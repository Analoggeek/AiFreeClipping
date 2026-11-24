"""Explicit local source-amplitude overview, bounded disk/array use, no fake peaks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np

from ..core.ffmpeg import FFmpegRunner,probe,FFmpegCancelled
from .timeline import Timeline


def source_signature(path):
    path=Path(path).resolve();stat=path.stat()
    return hashlib.sha256(f'{path}\0{stat.st_size}\0{stat.st_mtime_ns}'.encode()).hexdigest()


def build_waveform(path,cache_dir,*,cancel_cb=None,progress_cb=None):
    """8-kHz mono amplitude envelope, max 30 min, <=60k source-time peak bins.

    This is an overview of decoded/downsampled source audio, not a loudness meter,
    sample-accurate editor or the final mixed/automated output waveform.
    """
    if cancel_cb and cancel_cb():raise FFmpegCancelled()
    path=Path(path).resolve();signature=source_signature(path)
    cache=Path(cache_dir);cache.mkdir(parents=True,exist_ok=True)
    output=cache/(signature+'.json')
    if output.is_file() and output.stat().st_size<=3*1024*1024:
        try:
            data=json.loads(output.read_text())
            peaks=data['peaks'];duration=data['duration'];step=data['bin_seconds']
            if (data['schema']=='clipos.waveform.v1' and data['source_signature']==signature
                and type(duration) in (int,float) and 0<duration<=1800
                and data['sample_rate']==8000 and type(step) in (int,float) and 0<step<=1800
                and isinstance(peaks,list) and 0<len(peaks)<=60000
                and 0<=len(peaks)*step-duration<step+.001
                and all(type(p) in (int,float) and 0<=p<=1 for p in peaks)):
                return data
        except (ValueError,KeyError,TypeError):pass
    info=probe(path)
    if not info.has_audio:raise ValueError('Selected source has no audio stream')
    if not 0<info.duration<=1800:raise ValueError('Source waveform currently supports up to 30 minutes')
    with tempfile.TemporaryDirectory(prefix='.waveform-',dir=cache) as temporary:
        pcm=Path(temporary)/'source.pcm'
        FFmpegRunner(total_duration=info.duration,cancel_cb=cancel_cb,progress_cb=progress_cb).run([
            '-hide_banner','-nostdin','-y','-threads','2','-i',str(path),'-vn','-map','0:a:0',
            '-t',f'{info.duration:.6f}','-ac','1','-ar','8000','-fs',str(1800*8000*2+32000),'-f','s16le',str(pcm)])
        if not pcm.exists() or not 0<pcm.stat().st_size<=1800*8000*2+32000:
            raise ValueError('Waveform PCM output missing or exceeds analysis bound')
        samples=np.fromfile(pcm,dtype='<i2').astype(np.int32)
        stride=max(1,(len(samples)+59999)//60000)
        # Reduce directly over variable last bin, avoiding padded multi-hour arrays.
        peaks=np.maximum.reduceat(np.abs(samples),np.arange(0,len(samples),stride))/32768.
        if source_signature(path)!=signature:raise ValueError('Source changed during waveform analysis')
        data={'schema':'clipos.waveform.v1','source_signature':signature,
              'duration':len(samples)/8000,'sample_rate':8000,'bin_seconds':stride/8000,
              'peaks':np.round(peaks,5).tolist()}
        if cancel_cb and cancel_cb():raise FFmpegCancelled()
        Timeline._atomic_write(output,json.dumps(data,allow_nan=False).encode())
        return data

"""Local neural diarization through sherpa-onnx segmentation/embedding/clustering.

Runs trusted installed models in an isolated child process. No download, named
voice identity or automatic mapping of speakers to visible people is performed.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import wave

from ..core.ffmpeg import FFmpegCancelled
from ..video.timeline import Timeline


class DiarizationUnavailable(RuntimeError):pass


def speaker_label(index):
    label='';index+=1
    while index:
        index,remainder=divmod(index-1,26);label=chr(65+remainder)+label
    return 'Speaker '+label


def normalize_turns(raw,duration):
    """Stable anonymous labels by first onset; preserve overlap, no confidence invention."""
    if len(raw)>100000:raise ValueError('Too many diarization turns')
    labels={};turns=[]
    for row in sorted(raw,key=lambda row:row['start']):
        start,end,speaker=row['start'],row['end'],row['speaker']
        if any(isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) for value in (start,end)):
            raise ValueError('Invalid neural turn timing')
        if not 0<=start<end<=duration+.05 or type(speaker) is not int or not 0<=speaker<10000:
            raise ValueError('Invalid neural diarization result')
        if speaker not in labels:labels[speaker]=speaker_label(len(labels))
        turns.append({'start':start,'end':min(end,duration),'speaker':labels[speaker]})
    return turns


def word_speaker(start,end,turns):
    """Unknown for silence/overlap/ambiguous coverage, never assign by face prominence."""
    if end<=start:return None
    intervals={}
    for turn in turns:
        left,right=max(start,turn['start']),min(end,turn['end'])
        if right>left:intervals.setdefault(turn['speaker'],[]).append((left,right))
    overlaps={}
    for speaker,spans in intervals.items():
        total=0.;last=start
        for left,right in sorted(spans):
            total+=max(0,right-max(last,left));last=max(last,right)
        overlaps[speaker]=total
    ranked=sorted(overlaps.items(),key=lambda item:item[1],reverse=True)
    if not ranked or ranked[0][1]<(end-start)*.6:return None
    if len(ranked)>1 and ranked[1][1]>(end-start)*.2:return None
    return ranked[0][0]


def _digest(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def diarize(wav,segmentation,embedding,output,*,cancel_cb=None,progress_cb=None,transcript=None):
    paths=[Path(path).expanduser().resolve() for path in (wav,segmentation,embedding)]
    for path in paths:
        if not path.is_file():raise DiarizationUnavailable(f'Install/select trusted local model/audio file first: {path}; no automatic download')
    wav,segmentation,embedding=paths
    if segmentation.suffix.lower()!='.onnx' or embedding.suffix.lower()!='.onnx':
        raise DiarizationUnavailable('Select sherpa-compatible segmentation and embedding ONNX files')
    with wave.open(str(wav),'rb') as source:
        if source.getframerate()!=16000 or source.getnchannels()!=1 or source.getsampwidth()!=2:
            raise DiarizationUnavailable('Diarization requires mono 16 kHz signed 16-bit PCM WAV')
        duration=source.getnframes()/16000
    if not 0<duration<=1800:raise DiarizationUnavailable('Current diarization supports audio up to 30 minutes; long-file global clustering is pending')
    output=Path(output)
    if output.resolve() in paths:raise ValueError('Diarization output cannot overwrite input/model')
    output.parent.mkdir(parents=True,exist_ok=True)
    model_hashes=(_digest(segmentation),_digest(embedding));audio_hash=_digest(wav)
    with tempfile.TemporaryDirectory(prefix='.diarization-',dir=output.parent) as temporary:
        temporary=Path(temporary);config=temporary/'request.json';result=temporary/'result.json'
        config.write_text(json.dumps({'wav':str(wav),'segmentation':str(segmentation),'embedding':str(embedding),'result':str(result),'progress':str(temporary/'progress.log'),'error':str(temporary/'error.log')}))
        command=[sys.executable,'--diarize-worker',str(config)] if getattr(sys,'frozen',False) else [sys.executable,'-m','clipos.ai.diarization',str(config)]
        environment=os.environ.copy()
        if not getattr(sys,'frozen',False):
            environment['PYTHONPATH']=str(Path(__file__).resolve().parents[2])+os.pathsep+environment.get('PYTHONPATH','')
        with (temporary/'progress.log').open('w+b') as stdout,(temporary/'error.log').open('w+b') as stderr:
            process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,env=environment,
                creationflags=0x08000000 if sys.platform=='win32' else 0)
            reader=(temporary/'progress.log').open('rb')
            started=time.monotonic();offset=0
            try:
                while True:
                    if cancel_cb and cancel_cb():raise FFmpegCancelled()
                    if time.monotonic()-started>3600:raise DiarizationUnavailable('Local diarization exceeded one-hour processing limit')
                    try:process.wait(timeout=.2)
                    except subprocess.TimeoutExpired:pass
                    reader.seek(offset)
                    for line in reader.read(65536).splitlines():
                        try:
                            record=json.loads(line)
                            if progress_cb:progress_cb(record['progress'],'Neural speaker diarization (local CPU)')
                        except (ValueError,KeyError,TypeError):pass
                    offset=reader.tell()
                    if process.poll() is not None:break
                if process.returncode:
                    stderr.seek(0,2);size=stderr.tell();stderr.seek(max(0,size-4096))
                    raise DiarizationUnavailable('Local diarization worker failed: '+stderr.read(4096).decode(errors='replace'))
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=3)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                reader.close()
        if not result.exists() or result.stat().st_size>8*1024*1024:raise DiarizationUnavailable('Missing/oversized neural result')
        raw=json.loads(result.read_text())
        turns=normalize_turns(raw,duration)
        words=[]
        if transcript:
            for word in transcript.words_between(0,duration):
                words.append({'start':word.start,'end':word.end,'text':word.word,
                              'speaker':word_speaker(word.start,word.end,turns)})
        if (_digest(segmentation),_digest(embedding))!=model_hashes or _digest(wav)!=audio_hash:
            raise DiarizationUnavailable('Diarization inputs changed while processing; previous artifact preserved')
        payload={'schema':'clipos.diarization.v1','engine':'sherpa-onnx neural segmentation + embeddings + clustering',
            'duration':duration,'provider':'cpu','turns':turns,'word_speakers':words,
            'segmentation_sha256':model_hashes[0],'embedding_sha256':model_hashes[1],
            'audio_sha256':audio_hash,'identity':'anonymous, file-local; no visual-person mapping'}
        encoded=json.dumps(payload,allow_nan=False).encode()
        if len(encoded)>8*1024*1024:raise DiarizationUnavailable('Diarization artifact exceeds 8 MiB')
        Timeline._atomic_write(output,encoded)
        return {'artifact':str(output),'speakers':len({turn['speaker'] for turn in turns}),
                'turns':len(turns),'engine':payload['engine']}


def caption_turns(summary,duration,signature):
    """Read only current-source validated anonymous turns, not arbitrary caption tags."""
    import re
    if summary.get('source_signature')!=signature:raise ValueError('Diarization source binding mismatch')
    path=Path(summary['artifact'])
    if path.stat().st_size>8*1024*1024:raise ValueError('Diarization artifact exceeds caption bound')
    data=json.loads(path.read_text())
    if data.get('schema')!='clipos.diarization.v1' or abs(data.get('duration',-1)-duration)>.05:
        raise ValueError('Diarization artifact incompatible with source')
    turns=data.get('turns')
    if not isinstance(turns,list) or len(turns)>100000:raise ValueError('Invalid speaker turns')
    previous=-1.
    for row in turns:
        a,b=row['start'],row['end'];label=row['speaker']
        if (any(type(v) not in (int,float) or not math.isfinite(v) for v in (a,b)) or
            not 0<=a<b<=duration+.05 or a<previous or not isinstance(label,str) or not re.fullmatch(r'Speaker [A-Z]{1,3}',label)):
            raise ValueError('Invalid speaker caption evidence')
        previous=a
    return turns


def worker_main(args):
    """Child-only native model loading. A native abort cannot terminate the desktop process."""
    config={}
    try:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        except ImportError:pass
        if len(args)!=1:raise ValueError('Worker requires one local configuration')
        config=json.loads(Path(args[0]).read_text())
        import sherpa_onnx as sherpa
        from .audio_analysis import read_wav_mono
        model=sherpa.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa.OfflineSpeakerSegmentationPyannoteModelConfig(model=config['segmentation']),num_threads=2,provider='cpu'),
            embedding=sherpa.SpeakerEmbeddingExtractorConfig(model=config['embedding'],num_threads=2,provider='cpu'),
            clustering=sherpa.FastClusteringConfig(num_clusters=-1,threshold=.5),min_duration_on=.3,min_duration_off=.5)
        if not model.validate():raise ValueError('Invalid installed segmentation/embedding configuration')
        engine=sherpa.OfflineSpeakerDiarization(model)
        samples,rate=read_wav_mono(config['wav'])
        if rate!=engine.sample_rate:raise ValueError('Unsupported diarization model sample rate')
        def progress(done,total):
            with Path(config['progress']).open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'progress':100*done/max(1,total)})+'\n')
            return 0
        result=engine.process(samples,callback=progress).sort_by_start_time()
        Path(config['result']).write_text(json.dumps([{'start':float(turn.start),'end':float(turn.end),'speaker':int(turn.speaker)} for turn in result],allow_nan=False))
        return 0
    except Exception as exc:
        message=f'Local neural diarization failed: {exc}'
        if config.get('error'):
            with Path(config['error']).open('a',encoding='utf-8') as stream:stream.write(message+'\n')
        elif sys.stderr is not None:print(message,file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(worker_main(sys.argv[1:]))

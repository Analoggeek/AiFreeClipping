"""Explicit real-model smoke acceptance; never downloads weights or certifies OS isolation.

Run in an externally disconnected target machine with authorized sample media.
A successful result proves this invocation's inference, not diarization accuracy,
physical A/V output, audiovisual identity, or Windows/macOS certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('video','report'):
        parser.add_argument('--'+name,type=Path,required=True)
    for name in ('wav','yolo','segmentation','embedding','talknet','sound-model'):
        parser.add_argument('--'+name,type=Path)
    args=parser.parse_args()
    legacy=[args.wav,args.yolo,args.segmentation,args.embedding]
    if any(legacy) and not all(legacy):parser.error('Legacy tracking/diarization checks require --wav --yolo --segmentation --embedding together')
    if not any(legacy) and not args.talknet and not args.sound_model:
        parser.error('Select tracking/diarization inputs, --talknet, or --sound-model')
    inputs=[args.video,*[p for p in legacy if p],*[p for p in (args.talknet,) if p]]
    if args.sound_model:
        for name in ('config.json','preprocessor_config.json','model.safetensors'):
            inputs.append(args.sound_model/name)
    if args.report.resolve() in {p.resolve() for p in inputs}:parser.error('Report cannot overwrite input')
    for path in inputs:
        if not path.is_file():parser.error(f'Missing explicit local input: {path}')
    report={'schema':'clipos.real-model-smoke.v1','platform':platform.platform(),
        'machine':platform.machine(),'python':platform.python_version(),
        'os_network_isolation':'not established by this script; must be verified externally',
        'physical_av_sync':'not tested','speaker_accuracy':'not measured',
        'inputs':{name:{'sha256':digest(getattr(args,name))} for name in ('video','wav','yolo','segmentation','embedding','talknet') if getattr(args,name)},
        'trained_weight_provenance':'not established by this script; independently verify model origin and license',
        'semantic_accuracy':'not measured',
        'passed':False}
    from importlib.metadata import version,PackageNotFoundError
    report['runtime_versions']={}
    for package in ('torch','torchaudio','transformers','python_speech_features'):
        try:report['runtime_versions'][package]=version(package)
        except PackageNotFoundError:report['runtime_versions'][package]='not installed'
    if args.sound_model:
        report['sound_model_inputs']={name:{'sha256':digest(args.sound_model/name)}
            for name in ('config.json','preprocessor_config.json','model.safetensors')}
    report['av_inference_device']='cpu'
    started=time.monotonic()
    try:
        from clipos.ai.person_tracking import write_tracks
        from clipos.ai.diarization import diarize
        with tempfile.TemporaryDirectory(prefix='clipos-real-acceptance-') as temporary:
            root=Path(temporary)
            if all(legacy):
                tracking=write_tracks(args.video,args.yolo,root/'people.jsonl')
                report['tracking']=tracking
                if tracking.get('observations',0)<=0:raise RuntimeError('No confirmed people detected in the provided person-video fixture')
                report['diarization']=diarize(args.wav,args.segmentation,args.embedding,root/'speakers.json')
                turns=json.loads((root/'speakers.json').read_text())['turns']
                if not turns:raise RuntimeError('No speech turns detected in the provided speech fixture')
                # Retain a portable result, not temporary paths that disappear.
                report['diarization'].pop('artifact',None)
                report['diarization']['turns_detail']=turns
                if isinstance(tracking,dict):
                    tracking.pop('artifact',None)
            if args.talknet:
                from clipos.ai.visual_analysis import analyze_visual
                from clipos.ai.active_speaker import analyze as active_speaker
                from clipos.core.ffmpeg import FFmpegRunner
                pcm=root/'source-audio.wav'
                FFmpegRunner().run(['-y','-i',str(args.video),'-map','0:a:0','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(pcm)])
                visual=analyze_visual(args.video)
                result=active_speaker(args.video,pcm,visual,args.talknet)
                report['active_speaker']=result
                if not any(shot.get('scores') for shot in result['shots']):
                    raise RuntimeError('No eligible audiovisual face tracks were scored; inference acceptance fails')
            if args.sound_model:
                from clipos.ai.game_sound import review as sound_review
                from clipos.core.ffmpeg import probe
                duration=probe(args.video).duration
                result=sound_review(args.video,[{'id':'acceptance','start':0.,'end':min(30.,duration)}],str(args.sound_model))
                report['sound']=result
                if not result or not result[0]['sound'] or not result[0]['sound'][0]['labels']:
                    raise RuntimeError('No sound labels returned; inference acceptance fails')
            report['passed']=True
    except Exception as exc:
        report['error']=f'{type(exc).__name__}: {exc}'
    report['elapsed_seconds']=round(time.monotonic()-started,3)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    from clipos.video.timeline import Timeline
    Timeline._atomic_write(args.report,json.dumps(report,indent=2,allow_nan=False).encode())
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

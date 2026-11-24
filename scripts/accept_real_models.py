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
    for name in ('video','wav','yolo','segmentation','embedding','report'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    inputs=[args.video,args.wav,args.yolo,args.segmentation,args.embedding]
    if args.report.resolve() in {p.resolve() for p in inputs}:parser.error('Report cannot overwrite input')
    for path in inputs:
        if not path.is_file():parser.error(f'Missing explicit local input: {path}')
    report={'schema':'clipos.real-model-smoke.v1','platform':platform.platform(),
        'machine':platform.machine(),'python':platform.python_version(),
        'os_network_isolation':'not established by this script; must be verified externally',
        'physical_av_sync':'not tested','speaker_accuracy':'not measured',
        'inputs':{name:{'sha256':digest(getattr(args,name))} for name in ('video','wav','yolo','segmentation','embedding')},
        'passed':False}
    started=time.monotonic()
    try:
        from clipos.ai.person_tracking import write_tracks
        from clipos.ai.diarization import diarize
        with tempfile.TemporaryDirectory(prefix='clipos-real-acceptance-') as temporary:
            root=Path(temporary)
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

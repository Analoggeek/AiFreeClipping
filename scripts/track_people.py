#!/usr/bin/env python3
"""Explicit local model tracking: python scripts/track_people.py SOURCE MODEL OUTPUT.jsonl."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from clipos.ai.person_tracking import write_tracks


def main():
    parser=argparse.ArgumentParser(description='Continuous local YOLOX + ByteTrack person observations (CPU)')
    parser.add_argument('source',type=Path)
    parser.add_argument('model',type=Path,help='Installed raw-head COCO YOLOX ONNX model; never downloaded here')
    parser.add_argument('output',type=Path,help='Atomic JSONL observations + final summary')
    args=parser.parse_args()
    try:
        summary=write_tracks(args.source,args.model,args.output,
            progress_cb=lambda p,m:print(f'{p:.0f}% {m}',file=sys.stderr))
    except KeyboardInterrupt:
        print('Tracking interrupted; previous output preserved',file=sys.stderr)
        return 130
    except (RuntimeError,ValueError,OSError) as exc:
        print(f'Tracking failed: {exc}',file=sys.stderr)
        return 1
    print(json.dumps(summary,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())

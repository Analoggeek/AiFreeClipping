"""Bounded compatibility retry for a native renderer fault, not bad CLI/media.

Never removes captions/effects, alters selection times, or claims successful
output without the caller's verification. No retry for cancellation/OOM/exit 1.
"""
import json
import os
from pathlib import Path
import platform
import tempfile

NATIVE_CRASH_CODES={-11,-10,-7,-6,-4,139,134,-1073741819,3221225477}


def compatibility_args(args):
    result=list(args)
    for index,value in enumerate(result[:-1]):
        if value in ('-threads','-filter_threads','-filter_complex_threads'):
            result[index+1]='1'
    for option in ('-filter_threads','-filter_complex_threads'):
        if option not in result:result[0:0]=[option,'1']
    # Apply output worker limit even when a caller had only input -threads.
    result[-1:-1]=['-threads','1']
    if '-c:v' in result:
        encoder=result[result.index('-c:v')+1]
        if encoder=='libx264':
            result[-1:-1]=['-x264-params','asm=0:threads=1:lookahead_threads=1']
        elif encoder=='libx265':
            result[-1:-1]=['-x265-params','asm=0:pools=none:frame-threads=1']
    # Affect CPU codec/scaler dispatch as well as x264's separate ASM switch.
    result[0:0]=['-cpuflags','0']
    return result


def save_crash(error,status,*,recovery_error=None):
    """Best-effort bounded LOCAL diagnostic, never uploaded automatically."""
    from .config import PATHS
    data={'schema':'clipos.ffmpeg-native-crash.v1','platform':platform.platform(),
          'status':status,'returncode':error.returncode,
          'command':[str(arg)[:2000] for arg in error.cmd[:150]],
          'stderr':error.stderr[-60000:],
          'recovery_error':str(recovery_error)[-12000:] if recovery_error else '',
          'accuracy_note':'Native fault recovered only if output subsequently verifies; cause not proven.'}
    path=PATHS.logs/'ffmpeg-native-crash-last.json';name=None
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.crash-',dir=path.parent)
        with os.fdopen(fd,'w',encoding='utf8') as stream:json.dump(data,stream,indent=2)
        os.replace(name,path)
        return path
    except OSError:return None
    finally:
        if name:Path(name).unlink(missing_ok=True)

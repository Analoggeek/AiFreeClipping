"""Bounded real-libass RGBA frames for the decoded multitrack draft preview."""
from collections import OrderedDict
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from PIL import Image

from ..core.ffmpeg import require_ffmpeg, _CREATE_NO_WINDOW
from .overlay_tracks import write_caption


class CaptionRaster:
    def __init__(self):
        self.directory=tempfile.TemporaryDirectory(prefix='clipos-lane-preview-')
        self.cache=OrderedDict()

    def close(self):
        self.cache.clear();self.directory.cleanup()

    def frame(self,project,item,time,width,height):
        import json
        from dataclasses import asdict
        # Match the project frame grid. Cache is bounded, not an on-disk video render.
        moment=round(time*project.fps)/project.fps
        key=(json.dumps(asdict(item),sort_keys=True),moment,project.width,project.height,width,height)
        if key in self.cache:
            self.cache.move_to_end(key);return self.cache[key]
        folder=Path(self.directory.name)
        write_caption(folder/'caption.ass',item,project.width,project.height)
        from .renderer import _ass_filter
        subtitle_filter=_ass_filter(folder/'caption.ass')
        filters=(f'format=rgba,setpts=PTS+{moment:.8f}/TB,{subtitle_filter}:alpha=1,'
                 f'scale={width}:{height},format=rgba')
        result=subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i',
            f'color=c=black@0:s={project.width}x{project.height}:r={project.fps}:d=0.1,format=rgba',
            '-vf',filters,'-frames:v','1','-threads','1','-f','image2pipe','-vcodec','png','-'],
            cwd=folder,capture_output=True,timeout=15,creationflags=_CREATE_NO_WINDOW)
        if result.returncode or not result.stdout:
            raise RuntimeError('Caption preview failed: '+result.stderr.decode(errors='replace')[-1000:])
        rgba=np.asarray(Image.open(BytesIO(result.stdout)).convert('RGBA')).copy()
        self.cache[key]=rgba
        while len(self.cache)>48:self.cache.popitem(last=False)
        return rgba

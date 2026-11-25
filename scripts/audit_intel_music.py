"""Bounded native-only diagnostic for FFmpeg 6 range/music scheduling."""
import json
import subprocess
import tempfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from clipos.core.ffmpeg import FFmpegRunner,require_ffmpeg,run_ffmpeg
from clipos.core.render_recovery import compatibility_args
from clipos.video.renderer import ClipRenderer,RenderSettings

with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);source=root/'source.mp4';music=root/'music.wav'
    run_ffmpeg(['-f','lavfi','-i','testsrc2=size=320x180:rate=15:duration=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-threads','1','-c:a','aac',str(source)])
    run_ffmpeg(['-f','lavfi','-i','sine=frequency=1000:sample_rate=48000:duration=0.7',str(music)])
    def audit(self,args,*a,**kw):
        args=list(args);print('COMMAND',json.dumps(args),flush=True)
        variants={}
        for name,count in [('finite-loop', '2'),('no-loop','0')]:
            command=args.copy();command[command.index('-stream_loop')+1]=count
            variants[name]=command
        loop_filter=args.copy();i=loop_filter.index('-stream_loop');del loop_filter[i:i+2]
        j=loop_filter.index('-filter_complex')+1
        loop_filter[j]=loop_filter[j].replace('[1:a]aresample=48000,','[1:a]aresample=48000,aloop=loop=-1:size=33600,')
        variants['audio-filter-loop']=loop_filter
        for name,command in variants.items():
            try:
                result=subprocess.run([require_ffmpeg(),'-hide_banner','-nostdin','-y',*command],capture_output=True,text=True,timeout=20)
                print(name,result.returncode,result.stderr[-4000:],flush=True)
            except subprocess.TimeoutExpired as error:print(name,'TIMEOUT',str(error.stderr)[-4000:],flush=True)
        raise RuntimeError('Diagnostic complete; no output certified')
    FFmpegRunner.run=audit
    try:ClipRenderer(root/'work').render(source,root/'out.mp4',0,2,RenderSettings(width=270,height=480,fps=15,show_captions=False,normalize_audio=False,noise_reduction=False,sound_effects=False,encoder_preference='cpu',background_music=str(music),bgm_volume=.5,bgm_ducking=False))
    except RuntimeError as e:print(e)

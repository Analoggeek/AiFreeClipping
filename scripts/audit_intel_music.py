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
        variants={'baseline':args,'scalar':compatibility_args(args),'output-duration':args[:-1]+['-t','2',args[-1]],'filter-one':args.copy(),'queued-inputs':args.copy()}
        variants['filter-one'][args.index('-filter_complex_threads')+1]='1'
        queued=[]
        for arg in args:
            if arg=='-i':queued+=['-thread_queue_size','1024']
            queued.append(arg)
        variants['queued-inputs']=queued
        for name,command in variants.items():
            try:
                result=subprocess.run([require_ffmpeg(),'-hide_banner','-nostdin','-y',*command],capture_output=True,text=True,timeout=20)
                print(name,result.returncode,result.stderr[-4000:],flush=True)
            except subprocess.TimeoutExpired as error:print(name,'TIMEOUT',str(error.stderr)[-4000:],flush=True)
        raise RuntimeError('Diagnostic complete; no output certified')
    FFmpegRunner.run=audit
    try:ClipRenderer(root/'work').render(source,root/'out.mp4',0,2,RenderSettings(width=270,height=480,fps=15,show_captions=False,normalize_audio=False,noise_reduction=False,sound_effects=False,encoder_preference='cpu',background_music=str(music),bgm_volume=.5,bgm_ducking=False))
    except RuntimeError as e:print(e)

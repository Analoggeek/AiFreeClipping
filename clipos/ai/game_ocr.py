"""Explicitly installed RapidOCR/PaddleOCR ONNX models, local source frames only.

Reads visible text, not kills/wins/sound or complete scene semantics. No network
fetches or accounts; 1.4.4 wheels carry the model files installed during setup.
"""
import hashlib
from pathlib import Path

from ..core.ffmpeg import FFmpegCancelled
from ..video.waveform import source_signature
from .visual_analysis import cv2_module


def installed_engine():
    try:
        import rapidocr_onnxruntime as package
        from rapidocr_onnxruntime import RapidOCR
        import onnxruntime
        onnxruntime.disable_telemetry_events()
    except ImportError as exc:raise ValueError('Install optional OCR runtime explicitly: python scripts/install_deps.py --ocr') from exc
    root=Path(package.__file__).parent/'models'
    names=['ch_PP-OCRv4_det_infer.onnx','ch_PP-OCRv4_rec_infer.onnx','ch_ppocr_mobile_v2.0_cls_infer.onnx']
    paths=[root/name for name in names]
    if not all(path.is_file() for path in paths):raise ValueError('Installed OCR wheel is missing bundled local models; no automatic download')
    hashes={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    engine=RapidOCR(det_model_path=str(paths[0]),rec_model_path=str(paths[1]),cls_model_path=str(paths[2]),
                    intra_op_num_threads=2,inter_op_num_threads=1)
    return engine,hashes


def review(source,rows,*,cancel_cb=None):
    if len(rows)>4:raise ValueError('OCR supports at most four finalist clips')
    signature=source_signature(source);cv2=cv2_module()
    if cv2 is None:raise ValueError('OpenCV unavailable for source OCR')
    engine,hashes=installed_engine()
    capture=cv2.VideoCapture(str(source));output=[]
    try:
        if not capture.isOpened():raise ValueError('Cannot decode OCR source')
        for row in rows:
            observations=[]
            for fraction in (.2,.5,.8):
                if cancel_cb and cancel_cb():raise FFmpegCancelled()
                timestamp=row['start']+(row['end']-row['start'])*fraction
                capture.set(cv2.CAP_PROP_POS_MSEC,timestamp*1000);ok,frame=capture.read()
                if not ok:raise ValueError('Cannot decode requested OCR frame')
                scale=min(1.,1280/max(frame.shape[:2]))
                frame=cv2.resize(frame,(max(1,round(frame.shape[1]*scale)),max(1,round(frame.shape[0]*scale))))
                result,_=engine(frame,use_cls=False)
                for box,text,confidence in (result or [])[:100]:
                    if confidence>=.8 and isinstance(text,str) and text.strip():
                        observations.append({'timestamp':timestamp,'text':text[:200],'confidence':float(confidence),
                            'box':[[round(x/frame.shape[1],5),round(y/frame.shape[0],5)] for x,y in box]})
            output.append({'id':row['id'],'scene':'unknown','description':'OCR text only; no semantic scene verdict',
                'ocr':observations,'model_hashes':hashes,'kind':'local trained OCR observations'})
        if source_signature(source)!=signature:raise ValueError('Source changed during OCR')
        if cancel_cb and cancel_cb():raise FFmpegCancelled()
        return output
    except cv2.error as exc:raise ValueError('OCR source-frame processing failed') from exc
    finally:capture.release()

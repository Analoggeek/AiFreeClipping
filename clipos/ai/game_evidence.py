"""Compose independently available local OCR and local visual-model providers."""
from ..core.local_ai import LocalAIError
from ..video.waveform import source_signature


def review(source,rows,*,signature,ocr=False,vision=False,host='',model='',cancel_cb=None):
    if not signature or source_signature(source)!=signature:raise ValueError('Game evidence source binding missing/stale')
    combined={row['id']:{'id':row['id'],'scene':'unknown','description':'','providers':{}} for row in rows}
    available=False
    for name,enabled in (('ocr',ocr),('vision',vision)):
        if not enabled:continue
        try:
            if name=='ocr':
                from .game_ocr import review as run
                result=run(source,rows,cancel_cb=cancel_cb)
            else:
                from .game_vision import review as run
                result=run(source,rows,host,model,cancel_cb=cancel_cb)
            for item in result:
                target=combined[item['id']]
                target['providers'][name]='available'
                if name=='ocr':
                    target['ocr']=item['ocr'];target['ocr_model_hashes']=item['model_hashes']
                else:
                    target.update({key:item[key] for key in ('scene','description','sample_times','model','kind')})
            available=True
        except (LocalAIError,ValueError,TypeError,KeyError,OSError,RuntimeError,ImportError) as exc:
            for item in combined.values():item['providers'][name]='unavailable: '+str(exc)[:200]
    if not available:raise ValueError('No configured game evidence provider completed; install/check local models')
    return list(combined.values())

"""Copy only verified edited outputs into a single date/video batch folder."""
from pathlib import Path
from datetime import datetime
import json
import shutil
from .pipeline import _safe_folder


def deliver_clips(db, project_id, clip_ids, root, cancel_cb=None):
    project = db.get_project(project_id)
    folder = Path(root) / datetime.now().strftime('%Y-%m-%d') / _safe_folder(project['name'])
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    for cid in clip_ids:
        if cancel_cb and cancel_cb(): break
        clip = db.get_clip(cid)
        source = Path(clip['output_path']) if clip else Path('')
        item = {'clip_id':cid,'error':''}
        try:
            if not clip or not clip['output_path'] or not source.is_file() or source.stat().st_size == 0:
                raise RuntimeError('This clip has no finished edit. Run Edit before exporting.')
            target = folder / f'clip_{cid:03d}_{_safe_folder(clip["title"])}.mp4'
            if source.resolve() != target.resolve():
                partial = target.with_suffix('.partial.mp4')
                try:
                    shutil.copy2(source, partial)
                    partial.replace(target)
                finally:
                    partial.unlink(missing_ok=True)
            item.update(output_path=str(target),size_bytes=target.stat().st_size)
            db.create_export(project_id=project_id,clip_id=cid,output_path=str(target),status='done',size_bytes=target.stat().st_size)
        except Exception as exc:
            item['error']=str(exc)
        results.append(item)
    (folder/'export-results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')
    return {'output_dir':str(folder),'results':results}

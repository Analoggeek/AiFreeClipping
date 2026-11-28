import { useCallback, useEffect, useState } from 'react';
import { Download, FolderOpen, LoaderCircle, PackageCheck, Trash2 } from 'lucide-react';
import { api, mediaUrl, pollJob } from '../api';
import { EmptyState, formatClock, JobTracker, Panel, Pill } from '../components/common';
import type { Candidate } from '../types';
import type { PageProps } from '../App';

type Props = PageProps & { clipSelection: string[]; setClipSelection: (ids: string[]) => void };

export default function ExportPage({ notify, openEditor, clipSelection, setClipSelection }: Props) {
  const [clips, setClips] = useState<Candidate[]>([]);
  const [batchJob, setBatchJob] = useState<string | null>(null);
  const [batchLabel, setBatchLabel] = useState('Batch export');
  const [folder, setFolder] = useState('');

  const refresh = useCallback(() => {
    api.clips().then((result) => setClips(result.clips)).catch(() => undefined);
    api.folders().then((result) => setFolder(result.folders.clips || result.folders.exports)).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);
  useEffect(() => {
    if (!batchJob) return;
    return pollJob(batchJob, (job) => {
      if (job.status === 'done') {
        refresh();
        notify(batchLabel === 'Batch export' ? 'Selected clips exported at high quality.' : 'Rendered MP4 is ready to download.');
      }
      if (job.status === 'error') notify(job.error || job.message);
      if (job.status === 'cancelled') notify(`${batchLabel} cancelled.`);
    });
  }, [batchJob, batchLabel, notify, refresh]);

  const rendered = clips.filter((clip) => clip.output);
  const readyIds = clipSelection.filter((id) => clips.some((clip) => clip.id === id));
  const chosen = clips.filter((clip) => readyIds.includes(clip.id || ''));

  const selectAll = () => setClipSelection(clips.map((clip) => clip.id || '').filter(Boolean));
  const selectRendered = () => setClipSelection(rendered.map((clip) => clip.id || '').filter(Boolean));
  const clearSelection = () => setClipSelection([]);

  const exportSelected = async () => {
    if (!readyIds.length) { notify('Select at least one clip to export.'); return; }
    setBatchLabel('Batch export');
    try { setBatchJob((await api.exportBatch(readyIds)).job_id); }
    catch (error) { notify(String(error)); }
  };

  const renderClip = async (clipId: string) => {
    setBatchLabel('Rendering clip');
    try {
      const result = await api.renderClip(clipId, { aspect: '9:16', resolution: '1080p', sfx: ['whoosh', 'pop'] });
      setBatchJob(result.job_id);
    } catch (error) { notify(String(error)); }
  };

  const deleteSelected = async () => {
    if (!readyIds.length) { notify('Select one or more clips to delete.'); return; }
    if (!window.confirm(`Delete ${readyIds.length} selected clip(s)?\n\nRendered MP4 files inside the app’s export folder will also be deleted. This cannot be undone.`)) return;
    try {
      const result = await api.deleteClips(readyIds);
      setClipSelection([]);
      refresh();
      notify(`Deleted ${result.deleted} clip(s) and ${result.files_deleted} rendered MP4 file(s).`);
    } catch (error) { notify(String(error)); }
  };

  return (
    <div className="stack">
      <Panel title="One-click export" subtitle="Select, render, download or delete clips in one place — compatible H.264 MP4 exports" action={
        <div className="export-selection-actions">
          <span>{chosen.length} selected</span>
          <button className="chip-btn" disabled={!clips.length} onClick={selectAll}>Select all</button>
          <button className="chip-btn" disabled={!rendered.length} onClick={selectRendered}>Rendered</button>
          <button className="chip-btn" disabled={!readyIds.length} onClick={clearSelection}>Clear</button>
          <button className="chip-btn danger-action" disabled={!readyIds.length} onClick={() => void deleteSelected()}><Trash2 size={14} /> Delete selected</button>
          <button className="primary" disabled={!readyIds.length} onClick={() => void exportSelected()}><PackageCheck size={16} /> Export selected ({readyIds.length})</button>
        </div>
      }>
        {clips.length === 0 ? <EmptyState icon={<PackageCheck size={30} />} title="No clips yet" detail="Generate clips in AI Clipper, then come back here to render and download." /> : (
          <div className="export-grid">
            {clips.map((clip) => {
              const clipId = clip.id || '';
              const active = readyIds.includes(clipId);
              return (
                <article key={clipId} className={`export-card ${active ? 'active' : ''}`}>
                  <div className="export-row">
                    <input type="checkbox" checked={active} onChange={() => setClipSelection(active ? readyIds.filter((id) => id !== clipId) : [...readyIds, clipId])} />
                    <div><strong>{clip.title}</strong><small>{formatClock(clip.start)} → {formatClock(clip.end)} · score {Math.round(clip.score)}</small></div>
                    {clip.output ? <Pill tone="green">Rendered</Pill> : <Pill tone="amber">Needs render</Pill>}
                  </div>
                  <div className="export-actions">
                    {clip.output ? <a className="chip-btn" href={mediaUrl('/media/file?path=' + encodeURIComponent(clip.output) + '&download=true')} download><Download size={14} /> Download MP4</a> : <button className="chip-btn" onClick={() => void renderClip(clipId)}><LoaderCircle size={14} /> Render</button>}
                    <button className="chip-btn" onClick={() => openEditor(clipId)}>Open in editor</button>
                    <button className="chip-btn" onClick={() => window.desktop?.revealPath(clip.output || '')}>Reveal file</button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
        {batchJob && <JobTracker jobId={batchJob} label={batchLabel} />}
        <div className="panel-actions"><button className="ghost-btn" onClick={() => folder && window.desktop?.openPath(folder)}><FolderOpen size={15} /> Open rendered-clips folder</button></div>
      </Panel>

    </div>
  );
}

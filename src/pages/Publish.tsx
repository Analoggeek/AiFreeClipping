import { useCallback, useEffect, useState } from 'react';
import { Check, Download, ExternalLink, FolderOpen, LoaderCircle, PackageCheck, Send, Trash2, UploadCloud, Youtube } from 'lucide-react';
import { api, mediaUrl, pollJob } from '../api';
import { EmptyState, formatClock, JobTracker, Panel, Pill } from '../components/common';
import type { Candidate } from '../types';
import type { PageProps } from '../App';

type Props = PageProps & { clipSelection: string[]; setClipSelection: (ids: string[]) => void };

export default function Publish({ notify, openEditor, clipSelection, setClipSelection }: Props) {
  const [clips, setClips] = useState<Candidate[]>([]);
  const [batchJob, setBatchJob] = useState<string | null>(null);
  const [batchLabel, setBatchLabel] = useState('Batch export');
  const [yt, setYt] = useState<{ authorized: boolean; available: boolean; clientSecretConfigured: boolean } | null>(null);
  const [authJob, setAuthJob] = useState<string | null>(null);
  const [uploadJob, setUploadJob] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('#Shorts\nMade locally with AI Clipper Pro — made by analoggeek');
  const [privacy, setPrivacy] = useState('private');
  const [schedule, setSchedule] = useState('');
  const [folder, setFolder] = useState('');

  const refresh = useCallback(() => {
    api.clips().then((result) => setClips(result.clips)).catch(() => undefined);
    api.youtubeStatus().then(setYt).catch(() => undefined);
    api.folders().then((result) => setFolder(result.folders.clips || result.folders.exports)).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);
  useEffect(() => {
    if (clipSelection.length && !title) {
      const first = clips.find((clip) => clip.id === clipSelection[0]);
      if (first) setTitle(first.title);
    }
  }, [clipSelection, clips, title]);

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

  useEffect(() => {
    if (!authJob) return;
    return pollJob(authJob, (job) => {
      if (job.status === 'done') { refresh(); notify('YouTube channel connected.'); }
      if (job.status === 'error') { setAuthJob(null); notify(job.error || job.message); }
      if (job.status === 'cancelled') { setAuthJob(null); notify('YouTube authorization cancelled.'); }
    });
  }, [authJob, refresh, notify]);

  useEffect(() => {
    if (!uploadJob) return;
    return pollJob(uploadJob, (job) => {
      if (job.status === 'done' && job.result?.url) { setUploaded(String(job.result.url)); notify('Upload complete.'); }
      if (job.status === 'error') { setUploadJob(null); notify(job.error || job.message); }
      if (job.status === 'cancelled') { setUploadJob(null); notify('YouTube upload cancelled.'); }
    });
  }, [uploadJob, notify]);

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
      const result = await api.renderClip(clipId, { aspect: '9:16', resolution: '1080p', caption_style: { preset: 'hype' }, sfx: ['whoosh', 'pop'] });
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

  const upload = async () => {
    const target = chosen.find((clip) => clip.output);
    if (!target) { notify('Render a clip first — YouTube needs an exported MP4.'); return; }
    if (!yt?.authorized) { notify('Connect your channel first.'); return; }
    try {
      const result = await api.youtubeUpload({
        clip_id: target.id, title: title || target.title, description, privacy,
        publish_at: schedule ? new Date(schedule).toISOString() : undefined,
      });
      setUploadJob(result.job_id);
    } catch (error) { notify(String(error)); }
  };

  return (
    <div className="stack">
      <Panel title="One-click export" subtitle="Select, render, download or delete clips in one place — compatible H.264 MP4 exports" action={
        <div className="publish-selection-actions">
          <span>{chosen.length} selected</span>
          <button className="chip-btn" disabled={!clips.length} onClick={selectAll}>Select all</button>
          <button className="chip-btn" disabled={!rendered.length} onClick={selectRendered}>Rendered</button>
          <button className="chip-btn" disabled={!readyIds.length} onClick={clearSelection}>Clear</button>
          <button className="chip-btn danger-action" disabled={!readyIds.length} onClick={() => void deleteSelected()}><Trash2 size={14} /> Delete selected</button>
          <button className="primary" disabled={!readyIds.length} onClick={() => void exportSelected()}><PackageCheck size={16} /> Export selected ({readyIds.length})</button>
        </div>
      }>
        {clips.length === 0 ? <EmptyState icon={<Send size={30} />} title="Nothing to publish yet" detail="Generate clips in AI Clipper, then come back here to export and upload." /> : (
          <div className="publish-grid">
            {clips.map((clip) => {
              const clipId = clip.id || '';
              const active = readyIds.includes(clipId);
              return (
                <article key={clipId} className={`publish-card ${active ? 'active' : ''}`}>
                  <div className="publish-row">
                    <input type="checkbox" checked={active} onChange={() => setClipSelection(active ? readyIds.filter((id) => id !== clipId) : [...readyIds, clipId])} />
                    <div><strong>{clip.title}</strong><small>{formatClock(clip.start)} → {formatClock(clip.end)} · score {Math.round(clip.score)}</small></div>
                    {clip.output ? <Pill tone="green">Rendered</Pill> : <Pill tone="amber">Needs render</Pill>}
                  </div>
                  <div className="publish-actions">
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

      <Panel title="Publish to YouTube" subtitle="Uses your own OAuth app — uploads are resumable and default to private until Google audits the app">
        <div className="youtube-status">
          <div className="yt-icon"><Youtube size={24} /></div>
          <div><strong>{yt?.authorized ? 'Channel connected' : 'Channel not connected'}</strong><p>{yt?.authorized ? 'Ready to upload Shorts directly from your machine.' : 'Put client_secret.json in your data folder, then authorize with your own Google account.'}</p></div>
          {!yt?.authorized && <button className="primary" onClick={async () => { try { setAuthJob((await api.youtubeAuthorize()).job_id); } catch (error) { notify(String(error)); } }}><UploadCloud size={16} /> Connect channel</button>}
        </div>
        {authJob && <JobTracker jobId={authJob} label="YouTube authorization" />}
        <div className="form-grid">
          <label className="field wide"><span>Title</span><input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={100} /></label>
          <label className="field wide"><span>Description</span><textarea rows={3} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          <label className="field"><span>Privacy</span><select value={privacy} onChange={(event) => setPrivacy(event.target.value)}><option value="private">Private</option><option value="unlisted">Unlisted</option><option value="public">Public</option></select></label>
          <label className="field"><span>Schedule (optional)</span><input type="datetime-local" value={schedule} onChange={(event) => setSchedule(event.target.value)} /></label>
        </div>
        <div className="panel-actions">
          <button className="primary" disabled={!yt?.authorized || !chosen.some((clip) => clip.output)} onClick={upload}><Send size={16} /> Upload selected clip</button>
          {uploaded && <a className="chip-btn" href={uploaded} target="_blank" rel="noreferrer"><ExternalLink size={14} /> {uploaded} <Check size={13} /></a>}
        </div>
        {uploadJob && <JobTracker jobId={uploadJob} label="YouTube upload" />}
      </Panel>
    </div>
  );
}

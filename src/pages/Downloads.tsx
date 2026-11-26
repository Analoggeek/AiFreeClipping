import { useCallback, useEffect, useState } from 'react';
import { Check, Download, ExternalLink, FileVideo, FolderPlus, Link2, LoaderCircle, Scissors, Trash2 } from 'lucide-react';
import { api, mediaUrl, pollJob } from '../api';
import { EmptyState, formatClock, JobTracker, Panel, Pill } from '../components/common';
import type { Media } from '../types';
import type { PageProps } from '../App';

export default function Downloads({ notify, openClipper }: PageProps) {
  const [mode, setMode] = useState<'auto' | 'single' | 'playlist'>('auto');
  const [quality, setQuality] = useState('max');
  const [url, setUrl] = useState('');
  const [folder, setFolder] = useState('');
  const [subtitles, setSubtitles] = useState(false);
  const [info, setInfo] = useState<Record<string, unknown> | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [media, setMedia] = useState<Media[]>([]);

  const refresh = useCallback(() => {
    api.media().then((result) => setMedia(result.media)).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);
  useEffect(() => {
    api.folders().then((result) => {
      if (result.folders?.downloads) setFolder(result.folders.downloads);
    }).catch(() => undefined);
  }, []);

  const inspect = async () => {
    if (!url.trim()) return;
    setBusy(true);
    try {
      const result = await api.inspect(url.trim(), mode);
      setInfo(result.info);
    } catch (error) {
      notify(String(error));
    } finally { setBusy(false); }
  };

  const start = async () => {
    if (!url.trim()) { notify('Paste a video or playlist URL first.'); return; }
    setBusy(true);
    try {
      const result = await api.download({ url: url.trim(), mode, quality, folder: folder || undefined, subtitles });
      setJobId(result.job_id);
      notify('Download started. You can keep working while it runs.');
    } catch (error) { notify(String(error)); } finally { setBusy(false); }
  };

  const pickFolder = async () => {
    if (!window.desktop) { notify('Folder picker is available in the desktop app.'); return; }
    const selected = await window.desktop.selectDirectory();
    if (selected) {
      setFolder(selected);
      try { await api.setFolder('downloads', selected); notify('Download folder saved.'); } catch { /* keep working */ }
    }
  };

  useEffect(() => {
    if (!jobId) return;
    return pollJob(jobId, (job) => {
      if (job.status === 'done') { refresh(); setInfo(null); }
      if (job.status === 'error') notify(job.error || job.message);
    });
  }, [jobId, notify, refresh]);

  return (
    <div className="stack">
      <Panel title="Download from any link" subtitle="YouTube, Instagram, TikTok, Twitch and 1000+ sites via yt-dlp — max quality with audio merged">
        <div className="form-grid">
          <label className="field wide">
            <span>Video or playlist URL</span>
            <div className="input-row">
              <Link2 size={17} />
              <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://youtube.com/watch?v=… or playlist URL" />
              <button className="ghost-btn" disabled={busy} onClick={inspect}>{busy ? <LoaderCircle size={15} className="spin" /> : <Check size={15} />} Inspect</button>
            </div>
          </label>
          <label className="field"><span>Mode</span>
            <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
              <option value="auto">Auto detect</option><option value="single">Single video</option><option value="playlist">Full playlist</option>
            </select>
          </label>
          <label className="field"><span>Quality</span>
            <select value={quality} onChange={(event) => setQuality(event.target.value)}>
              <option value="max">Maximum available (4K/8K if offered)</option>
              <option value="1080p">Up to 1080p</option><option value="720p">Up to 720p</option><option value="audio">Audio only</option>
            </select>
          </label>
          <label className="field wide"><span>Save folder</span>
            <div className="input-row">
              <input value={folder} onChange={(event) => setFolder(event.target.value)} placeholder="Default: ~/.AiFreeClipping/downloads" />
              <button className="ghost-btn" onClick={pickFolder}><FolderPlus size={15} /> Browse</button>
            </div>
          </label>
          <label className="check"><input type="checkbox" checked={subtitles} onChange={(event) => setSubtitles(event.target.checked)} /> Save subtitles when available</label>
        </div>
        {info && (
          <div className="info-card">
            <strong>{String(info.title || 'Resolved media')}</strong>
            <div>{Object.entries(info || {}).filter(([, value]) => typeof value !== 'object').slice(0, 6).map(([key, value]) => <Pill key={key}>{key}: {String(value)}</Pill>)}</div>
          </div>
        )}
        <div className="panel-actions">
          <button className="primary" disabled={busy} onClick={start}><Download size={17} /> Download {mode === 'playlist' ? 'playlist' : 'video'}</button>
          {jobId && <JobTracker jobId={jobId} label="Download" onDone={(job) => { if (job.status === 'done') notify('Saved to your local library.'); }} />}
        </div>
      </Panel>

      <Panel title={`Video library · ${media.length}`} subtitle="Click a video to send it to the AI Clipper" action={<button className="ghost-btn" onClick={refresh}>Refresh</button>}>
        {media.length === 0 ? (
          <EmptyState icon={<FileVideo size={30} />} title="No videos yet" detail="Download a link above or import a local file to build your library." />
        ) : (
          <div className="media-grid">
            {media.map((item) => (
              <article className="media-card" key={item.id} onClick={() => openClipper([item.id])}>
                <div className="thumb">
                  {item.thumbnail ? <img src={mediaUrl(item.thumbnail)} alt="" /> : <FileVideo size={28} />}
                  <span>{formatClock(item.duration)}</span>
                </div>
                <div className="media-info"><strong title={item.title}>{item.title}</strong><small>{item.width}×{item.height}{item.playlist_id ? ' · playlist' : ''}</small></div>
                <div className="media-actions">
                  <button className="chip-btn" onClick={(event) => { event.stopPropagation(); openClipper([item.id]); }}><Scissors size={14} /> Clip</button>
                  <button className="icon-btn" title="Open file" onClick={(event) => { event.stopPropagation(); window.desktop?.openPath(item.path); }}><ExternalLink size={15} /></button>
                  <button className="icon-btn danger" title="Remove from library" onClick={(event) => { event.stopPropagation(); api.deleteMedia(item.id).then(refresh).catch((error) => notify(String(error))); }}><Trash2 size={15} /></button>
                </div>
              </article>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

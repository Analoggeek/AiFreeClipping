import { useCallback, useEffect, useState } from 'react';
import { Download, ListVideo, LoaderCircle, Play, RefreshCw } from 'lucide-react';
import { api, pollJob } from '../api';
import { EmptyState, JobTracker, Panel, Pill } from '../components/common';
import type { PageProps } from '../App';

type Playlist = { id: string; title: string; url: string; items: Array<{ index: number; title: string; id?: string }>; created_at?: string };

export default function Playlists({ notify, openClipper }: PageProps) {
  const [items, setItems] = useState<Playlist[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ playlist: Record<string, unknown>; media: Array<{ id: string; title: string; duration: number }> } | null>(null);
  const [url, setUrl] = useState('');
  const [range, setRange] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    api.playlists().then((result) => {
      setItems(result.playlists as Playlist[]);
      if (!selected && result.playlists.length) setSelected(result.playlists[0].id);
    }).catch(() => undefined);
  }, [selected]);
  useEffect(refresh, [refresh]);

  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    api.playlist(selected).then(setDetail).catch(() => setDetail(null));
  }, [selected]);

  useEffect(() => {
    if (!jobId) return;
    return pollJob(jobId, (job) => {
      if (job.status === 'done') { refresh(); notify('Playlist download finished.'); }
      if (job.status === 'error') notify(job.error || job.message);
      if (job.status === 'cancelled') notify('Playlist download cancelled.');
    });
  }, [jobId, notify, refresh]);

  const download = async (target: string, playlistItems: string) => {
    setBusy(true);
    try {
      const result = await api.download({ url: target, mode: 'playlist', quality: 'max', playlist_items: playlistItems || undefined });
      setJobId(result.job_id);
    } catch (error) { notify(String(error)); } finally { setBusy(false); }
  };

  return (
    <div className="stack">
      <Panel title="Add a playlist" subtitle="Download an entire channel playlist or only selected items — every video keeps its original quality">
        <div className="form-grid">
          <label className="field wide"><span>Playlist URL</span>
            <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://youtube.com/playlist?list=…" />
          </label>
          <label className="field"><span>Items (optional)</span>
            <input value={range} onChange={(event) => setRange(event.target.value)} placeholder="1:10, 15, 22" />
          </label>
          <div className="field"><span>&nbsp;</span>
            <button className="primary" disabled={busy || !url.trim()} onClick={() => download(url.trim(), range)}>
              {busy ? <LoaderCircle size={16} className="spin" /> : <Download size={17} />} Download playlist
            </button>
          </div>
        </div>
        {jobId && <JobTracker jobId={jobId} label="Playlist download" />}
      </Panel>

      <Panel title="Saved playlists" subtitle="Pick a playlist to browse its videos and send them straight to the AI Clipper" action={<button className="ghost-btn" onClick={refresh}><RefreshCw size={15} /> Refresh</button>}>
        {items.length === 0 ? (
          <EmptyState icon={<ListVideo size={30} />} title="No playlists downloaded yet" detail="Add a playlist URL above and all items will appear here." />
        ) : (
          <div className="playlist-layout">
            <div className="playlist-list">
              {items.map((playlist) => (
                <button key={playlist.id} className={`playlist-row ${selected === playlist.id ? 'active' : ''}`} onClick={() => setSelected(playlist.id)}>
                  <ListVideo size={16} />
                  <div><strong>{playlist.title}</strong><small>{playlist.items?.length || 0} videos</small></div>
                </button>
              ))}
            </div>
            <div className="playlist-detail">
              {detail ? (
                <>
                  <div className="detail-head">
                    <div><strong>{String(detail.playlist.title || 'Playlist')}</strong><Pill>{detail.media.length} downloaded</Pill></div>
                    <button className="ghost-btn" onClick={() => { const playlist = items.find((item) => item.id === selected); if (playlist) download(playlist.url, ''); }}><Download size={15} /> Download all again</button>
                  </div>
                  <div className="playlist-items">
                    {(detail.media.length ? detail.media : (detail.playlist.items as Array<{ title: string }>) || []).map((item, index) => (
                      <div className="playlist-item" key={(item as { id?: string }).id || index}>
                        <span className="rank">{String(index + 1).padStart(2, '0')}</span>
                        <div><strong>{item.title}</strong>{'duration' in item && <small>{Math.round((item as { duration: number }).duration)}s</small>}</div>
                        {'id' in item && <button className="chip-btn" onClick={() => openClipper([(item as { id: string }).id])}><Play size={13} /> Clip</button>}
                      </div>
                    ))}
                  </div>
                </>
              ) : <EmptyState icon={<ListVideo size={26} />} title="Select a playlist" detail="Choose a playlist on the left to inspect its items." />}
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}

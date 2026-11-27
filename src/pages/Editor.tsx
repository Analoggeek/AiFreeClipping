import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Captions, Check, Clapperboard, Download, Film, Image as ImageIcon, ImagePlus, Layers3, LoaderCircle,
  Mic2, Music2, Pause, Play, Plus, Save, Search, SkipBack, SkipForward, Sparkles,
  Split, Trash2, Volume2, WandSparkles,
} from 'lucide-react';
import { api, mediaUrl, pollJob } from '../api';
import { JobTracker, Pill, formatClock } from '../components/common';
import type { Candidate, Media, Timeline } from '../types';
import type { PageProps } from '../App';

type TrackKey = 'video' | 'captions' | 'stickers' | 'audio';
type AnyItem = {
  id?: string; clip_id?: string; path?: string; text?: string; sourceStart?: number; duration?: number;
  start?: number; end?: number; volume?: number; x?: number; y?: number; label?: string;
  region?: Candidate['region']; regions?: Candidate['regions'];
};
type Selection = { track: TrackKey; index: number } | null;

const emptyTimeline = (): Timeline => ({
  tracks: { video: [], captions: [], stickers: [], audio: [] },
  aspect: '9:16', resolution: '1080p', caption_style: { preset: 'hype' },
});

export default function Editor({ notify, clipSelection }: PageProps & { clipSelection: string[] }) {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState('Untitled project');
  const [timeline, setTimeline] = useState<Timeline>(emptyTimeline());
  const [selected, setSelected] = useState<Selection>(null);
  const [playhead, setPlayhead] = useState(0);
  const [zoom, setZoom] = useState(24);
  const [playing, setPlaying] = useState(false);
  const [media, setMedia] = useState<Media[]>([]);
  const [newMedia, setNewMedia] = useState('');
  const [tab, setTab] = useState<'media' | 'clips' | 'stock' | 'art' | 'sfx'>('media');
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('pexels');
  const [stock, setStock] = useState<Array<Record<string, string>>>([]);
  const [prompt, setPrompt] = useState('');
  const [provider, setProvider] = useState('auto');
  const [sfxList, setSfxList] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [exportJob, setExportJob] = useState<string | null>(null);
  const [exportOutput, setExportOutput] = useState('');
  const [clips, setClips] = useState<Candidate[]>([]);
  const [autoJob, setAutoJob] = useState<string | null>(null);
  const [autoStyle, setAutoStyle] = useState<'hype' | 'minimal' | 'premium'>('hype');
  const [imageResult, setImageResult] = useState('');
  const videoRef = useRef<HTMLVideoElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const scrubbingRef = useRef(false);

  const total = useMemo(() => Math.max(6, timeline.tracks.video.reduce((sum, item) => sum + item.duration, 0)), [timeline.tracks.video]);

  const loadProject = useCallback(async (id: string) => {
    try {
      const result = await api.project(id);
      setProjectId(id);
      setProjectName(result.project.name);
      setTimeline(result.project.timeline || emptyTimeline());
      setPlayhead(0);
    } catch (error) { notify(String(error)); }
  }, [notify]);

  const refreshClips = useCallback(async () => {
    try { setClips((await api.clips()).clips || []); } catch { /* keep editor usable offline */ }
  }, []);

  useEffect(() => {
    api.media().then((result) => {
      setMedia(result.media);
      return api.projects();
    }).then((projects) => {
      if (clipSelection[0]) {
        void api.createProject({ name: 'Clip edit', clip_id: clipSelection[0] }).then((created) => loadProject(created.project.id));
      } else if (projects.projects.length) {
        void loadProject(projects.projects[0].id);
      }
    }).catch(() => undefined);
    api.sfx().then((result) => setSfxList(result.sfx)).catch(() => undefined);
  }, [clipSelection, loadProject]);

  useEffect(() => {
    if (!jobId) return;
    return pollJob(jobId, async (job) => {
      if (job.status === 'done') {
        if (job.result?.path && tab === 'art') {
          setImageResult(String(job.result.path));
          addItem('stickers', { path: String(job.result.path), start: playhead, end: playhead + 3, x: 0.7, y: 0.15, label: 'AI art' });
        }
        const transcript = (job.result?.segments || job.result?.transcript) as { segments?: Array<{ start: number; end: number; text: string }> } | undefined;
        if (transcript) {
          const segments = Array.isArray(transcript) ? transcript : (transcript.segments || []);
          addItem('captions', segments.slice(0, 40).map((segment) => ({ text: segment.text, start: segment.start, end: segment.end })) as AnyItem, true);
          notify(`Added ${Math.min(segments.length, 40)} captions.`);
        }
        setBusy(false);
      }
      if (job.status === 'error') { notify(job.error || job.message); setBusy(false); }
      if (job.status === 'cancelled') { notify('Operation cancelled.'); setBusy(false); }
    });
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!exportJob) return;
    return pollJob(exportJob, (job) => {
      if (job.status === 'done' && job.result?.output) { setExportOutput(String(job.result.output)); notify('Export ready — download it from here.'); }
      if (job.status === 'error') notify(job.error || job.message);
      if (job.status === 'cancelled') notify('Export cancelled.');
    });
  }, [exportJob, notify]);

  useEffect(() => {
    void refreshClips();
    const timer = window.setInterval(() => { void refreshClips(); }, 4000);
    return () => window.clearInterval(timer);
  }, [refreshClips]);

  useEffect(() => {
    if (!autoJob) return;
    return pollJob(autoJob, (job) => {
      if (job.status === 'done') {
        void refreshClips();
        setAutoJob(null);
        notify('Automatic editing and rendering finished.');
      }
      if (job.status === 'error') { setAutoJob(null); notify(job.error || job.message); }
      if (job.status === 'cancelled') { setAutoJob(null); notify('Automatic editing cancelled.'); }
    });
  }, [autoJob, notify, refreshClips]);

  const runAutoEdit = async () => {
    const ids = clips.map((clip) => clip.id || '').filter(Boolean);
    if (!ids.length) { notify('Generate clips with AI Clipper first.'); return; }
    try {
      const result = await api.autoEdit(ids, autoStyle, timeline.aspect === '16:9' ? '16:9' : timeline.aspect === '1:1' ? '1:1' : '9:16');
      setAutoJob(result.job_id);
      notify(`Auto-editing ${ids.length} clip(s) with captions, images, motion and SFX…`);
    } catch (error) { notify(String(error)); }
  };

  const renderAutoClip = async (clip: Candidate) => {
    if (!clip.id) return;
    try {
      const result = await api.renderClip(clip.id, {
        aspect: timeline.aspect, resolution: '1080p',
        caption_style: { preset: autoStyle },
        sfx: ['whoosh', 'pop'], speed: 1.04, brightness: 0.02,
        contrast: 1.05, saturation: 1.08, blur_background: true,
        region: clip.region, regions: clip.regions,
      });
      setExportJob(result.job_id);
      notify('Rendering this clip with the same automatic edit stack.');
    } catch (error) { notify(String(error)); }
  };

  const mutate = (fn: (draft: Timeline) => void) => {
    setTimeline((current) => {
      const next = structuredClone(current);
      fn(next);
      return next;
    });
  };

  const addItem = (track: TrackKey, item: AnyItem | AnyItem[], replace = false) => {
    mutate((draft) => {
      const list = draft.tracks[track] as unknown as AnyItem[];
      if (replace) list.splice(0, list.length, ...(Array.isArray(item) ? item : [item]));
      else if (Array.isArray(item)) list.push(...item);
      else list.push(item);
    });
  };

  const removeSelected = () => {
    if (!selected) return;
    mutate((draft) => { (draft.tracks[selected.track] as unknown as AnyItem[]).splice(selected.index, 1); });
    setSelected(null);
  };

  const splitSelected = () => {
    if (!selected || selected.track !== 'video') { notify('Select a video clip on the timeline to split it.'); return; }
    const item = timeline.tracks.video[selected.index];
    const itemStart = timeline.tracks.video.slice(0, selected.index).reduce((sum, part) => sum + part.duration, 0);
    const offset = playhead - itemStart;
    if (offset <= 0.2 || offset >= item.duration - 0.2) { notify('Move the playhead inside the selected clip before splitting.'); return; }
    mutate((draft) => {
      const first = draft.tracks.video[selected.index];
      const second = { ...first, id: undefined, sourceStart: first.sourceStart + offset, duration: first.duration - offset, label: `${first.label || 'Clip'} B` };
      first.duration = offset;
      draft.tracks.video.splice(selected.index + 1, 0, second);
    });
    notify('Clip split at playhead.');
  };

  const seekTo = (seconds: number) => {
    const next = Math.max(0, Math.min(total, seconds));
    setPlayhead(next);
    if (videoRef.current && Number.isFinite(next)) {
      const offset = Math.max(0, next - activeVideoStart);
      videoRef.current.currentTime = Math.max(0, Math.min(videoRef.current.duration || offset, offset + (activeVideo?.sourceStart || 0)));
    }
  };

  const scrub = (event: React.PointerEvent<HTMLDivElement>) => {
    const bounds = timelineRef.current?.getBoundingClientRect();
    if (!bounds) return;
    seekTo((event.clientX - bounds.left + timelineRef.current!.scrollLeft) / zoom);
  };

  useEffect(() => {
    const node = timelineRef.current;
    if (!node) return;
    const x = playhead * zoom;
    if (x < node.scrollLeft || x > node.scrollLeft + node.clientWidth - 40) {
      node.scrollLeft = Math.max(0, x - node.clientWidth * 0.35);
    }
  }, [playhead, zoom]);

  const selectedItem = selected ? (timeline.tracks[selected.track] as unknown as AnyItem[])[selected.index] : null;
  const updateSelected = (patch: Partial<AnyItem>) => {
    if (!selected) return;
    mutate((draft) => {
      const item = (draft.tracks[selected.track] as unknown as AnyItem[])[selected.index];
      if (item) Object.assign(item, patch);
    });
  };

  const createProject = async () => {
    const chosen = media.find((item) => item.id === newMedia);
    if (!chosen) { notify('Choose a source video first.'); return; }
    try {
      const result = await api.createProject({ name: chosen.title, media_id: chosen.id });
      setNewMedia('');
      await loadProject(result.project.id);
    } catch (error) { notify(String(error)); }
  };

  const save = async () => {
    if (!projectId) { notify('Create a project first.'); return; }
    try { await api.saveProject(projectId, timeline, projectName); notify('Project saved locally.'); }
    catch (error) { notify(String(error)); }
  };

  const exportVideo = async () => {
    if (!projectId || !timeline.tracks.video.length) { notify('Add a video clip to the timeline first.'); return; }
    try {
      await save();
      const result = await api.exportProject(projectId);
      setExportJob(result.job_id);
    } catch (error) { notify(String(error)); }
  };

  const autoCaptions = async () => {
    const first = timeline.tracks.video[0]?.path;
    const source = media.find((item) => item.path === first);
    if (!source) { notify('Add a library video to the timeline first.'); return; }
    setBusy(true);
    setTab('media');
    try {
      const result = await api.transcribe(source.id);
      setJobId(result.job_id);
      notify('Generating word-timed captions with Whisper…');
    } catch (error) { notify(String(error)); setBusy(false); }
  };

  const searchStock = async () => {
    if (!query.trim()) return;
    setBusy(true);
    try { setStock((await api.searchAssets(query, source, tab === 'stock' ? 'image' : 'video')).results); }
    catch (error) { notify(String(error)); } finally { setBusy(false); }
  };

  const downloadStock = async (asset: Record<string, string>) => {
    try {
      const result = await api.downloadAsset(asset.url, asset.title || 'stock-asset', asset.source || source);
      addItem('stickers', { path: result.asset.path, start: playhead, end: playhead + 4, x: 0.6, y: 0.15, label: asset.title });
      notify('Asset added to the sticker track.');
    } catch (error) { notify(String(error)); }
  };

  const generateArt = async () => {
    if (!prompt.trim()) { notify('Describe the sticker or image you want.'); return; }
    setBusy(true);
    try { setJobId((await api.generateImage(prompt, provider, '1:1')).job_id); }
    catch (error) { notify(String(error)); setBusy(false); }
  };

  const addSfx = async (name: string) => {
    try {
      const result = await api.sfxPath(name);
      addItem('audio', { path: result.path, start: playhead, end: playhead + 1.2, volume: 0.8, label: name });
      notify(`${name} added at ${formatClock(playhead)}.`);
    } catch (error) { notify(String(error)); }
  };

  const addMediaToTimeline = async (item: Media) => {
    if (!projectId) {
      try {
        const created = await api.createProject({ name: item.title, media_id: item.id });
        setProjectId(created.project.id);
        setProjectName(created.project.name);
        setTimeline(created.project.timeline || emptyTimeline());
      } catch (error) { notify(String(error)); return; }
    } else {
      addItem('video', { path: item.path, sourceStart: 0, duration: Math.min(30, Math.max(3, item.duration || 10)), label: item.title });
    }
    notify(`${item.title} added to the timeline.`);
  };

  const addClipToTimeline = async (clip: Candidate) => {
    if (!clip.id) { notify('This AI clip has no saved clip ID yet.'); return; }
    const sourceMedia = media.find((item) => item.id === clip.media_id);
    if (!sourceMedia) { notify('The source video for this clip is no longer in your library.'); return; }
    if (!projectId) {
      try {
        const created = await api.createProject({ name: clip.title.slice(0, 60), clip_id: clip.id });
        setProjectId(created.project.id);
        setProjectName(created.project.name);
        setTimeline(created.project.timeline || emptyTimeline());
      } catch (error) { notify(String(error)); return; }
    } else {
      addItem('video', {
        id: clip.id, clip_id: clip.id, path: sourceMedia.path,
        sourceStart: clip.start, duration: Math.max(0.2, clip.end - clip.start),
        label: clip.title, region: clip.region, regions: clip.regions,
      });
    }
    notify(`“${clip.title}” added to the timeline.`);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
      if (event.code === 'Space') {
        event.preventDefault();
        if (videoRef.current) {
          if (videoRef.current.paused) { void videoRef.current.play(); setPlaying(true); }
          else { videoRef.current.pause(); setPlaying(false); }
        }
      }
      if (event.key.toLowerCase() === 's') splitSelected();
      if (event.key === 'Delete' || event.key === 'Backspace') removeSelected();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const activeVideoIndex = useMemo(() => {
    let cursor = 0;
    for (let index = 0; index < timeline.tracks.video.length; index++) {
      if (playhead >= cursor && playhead < cursor + timeline.tracks.video[index].duration) return index;
      cursor += timeline.tracks.video[index].duration;
    }
    return timeline.tracks.video.length ? timeline.tracks.video.length - 1 : -1;
  }, [playhead, timeline.tracks.video]);
  const activeVideo = activeVideoIndex >= 0 ? timeline.tracks.video[activeVideoIndex] : null;
  const activeVideoStart = useMemo(() => timeline.tracks.video.slice(0, Math.max(0, activeVideoIndex)).reduce((sum, item) => sum + item.duration, 0), [activeVideoIndex, timeline.tracks.video]);
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !activeVideo) return;
    const target = activeVideo.sourceStart + playhead - activeVideoStart;
    if (Math.abs(video.currentTime - target) > 0.45 && Number.isFinite(target)) video.currentTime = Math.max(0, target);
  }, [playhead, activeVideo, activeVideoStart]);

  const visibleCaptions = timeline.tracks.captions.filter((caption) => playhead >= caption.start && playhead <= caption.end);
  const visibleStickers = timeline.tracks.stickers.filter((sticker) => playhead >= sticker.start && playhead <= sticker.end);

  return (
    <div className="editor">
      <header className="editor-toolbar">
        <div className="project-title">
          <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
          {projectId && <Pill tone="muted">Saved locally</Pill>}
        </div>
        <Pill tone="violet">Timeline editor</Pill>
      </header>

      <div className="editor-body">
        <aside className="asset-panel">
          <div className="asset-tabs">
            {([['media', Film, 'Media'], ['clips', Clapperboard, 'Clips'], ['stock', Search, 'Stock'], ['art', WandSparkles, 'AI Art'], ['sfx', Music2, 'SFX']] as const).map(([id, Icon, label]) => (
              <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}><Icon size={15} />{label}</button>
            ))}
          </div>
          <div className="asset-content">
            {tab === 'media' && (
              <>
                {!projectId && (
                  <div className="new-project">
                    <h3>Start a project</h3>
                    <select value={newMedia} onChange={(event) => setNewMedia(event.target.value)}>
                      <option value="">Choose a video from your library…</option>
                      {media.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
                    </select>
                    <button className="primary" onClick={createProject}><Plus size={15} /> Create project</button>
                  </div>
                )}
                <div className="asset-list">
                  {media.map((item) => (
                    <button key={item.id} className="asset-row" onClick={() => addMediaToTimeline(item)}>
                      {item.thumbnail ? <img src={mediaUrl(item.thumbnail)} alt="" /> : <Film size={20} />}
                      <span><strong>{item.title}</strong><small>{formatClock(item.duration)} · click to add</small></span>
                    </button>
                  ))}
                </div>
              </>
            )}
            {tab === 'clips' && (
              <div className="asset-list">
                <p className="hint">Your AI-picked clips refresh here automatically. Click one to add its source cut and focus crop to the timeline.</p>
                {clips.length === 0 && <p className="hint">No AI clips yet. Run AI Clipper first; you can keep editing here while it works.</p>}
                {clips.map((clip, index) => {
                  const sourceMedia = media.find((item) => item.id === clip.media_id);
                  return (
                    <button key={clip.id || `${clip.media_id}-${index}`} className="asset-row" disabled={!sourceMedia || !clip.id} onClick={() => void addClipToTimeline(clip)}>
                      {sourceMedia?.thumbnail ? <img src={mediaUrl(sourceMedia.thumbnail)} alt="" /> : <Clapperboard size={20} />}
                      <span><strong>{clip.title}</strong><small>{formatClock(clip.start)} → {formatClock(clip.end)} · {Math.round(clip.score)}/100</small><small>{clip.output ? 'Rendered MP4 · click to add source cut' : 'Click to add to timeline'}</small></span>
                    </button>
                  );
                })}
              </div>
            )}
            {tab === 'stock' && (
              <>
                <div className="stock-search">
                  <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="whoosh, neon city, crowd…" onKeyDown={(event) => event.key === 'Enter' && searchStock()} />
                  <select value={source} onChange={(event) => setSource(event.target.value)}>
                    <option value="pexels">Pexels</option><option value="pixabay">Pixabay</option><option value="openverse">Openverse</option>
                  </select>
                  <button className="chip-btn" disabled={busy} onClick={searchStock}><Search size={15} /> Search</button>
                </div>
                <div className="asset-list">
                  {stock.map((asset, index) => (
                    <button key={asset.id || index} className="asset-row" onClick={() => downloadStock(asset)}>
                      {asset.preview ? <img src={asset.preview} alt="" /> : <ImageIcon size={20} />}
                      <span><strong>{asset.title}</strong><small>{asset.license || asset.source}</small></span>
                    </button>
                  ))}
                  {!stock.length && <p className="hint">Stock assets are copyright-friendly. Add your free API key in Settings.</p>}
                </div>
              </>
            )}
            {tab === 'art' && (
              <div className="art-panel">
                <h3>Generate on the spot</h3>
                <p>Nano Banana (Gemini key) or local SDXL via ComfyUI — no watermark.</p>
                <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={4} placeholder="A glowing neon sticker that says EPIC, transparent background, cartoon style" />
                <select value={provider} onChange={(event) => setProvider(event.target.value)}>
                  <option value="auto">Auto (best available)</option><option value="nano-banana">Nano Banana</option><option value="comfyui">Local ComfyUI (SDXL)</option><option value="local">Offline instant art</option>
                </select>
                <button className="primary" disabled={busy} onClick={generateArt}><Sparkles size={15} /> Generate image</button>
                {imageResult && <img className="generated-preview" src={mediaUrl('/api/assets/file?path=' + encodeURIComponent(imageResult))} alt="Generated asset" />}
                {jobId && <JobTracker jobId={jobId} label="Image generation" />}
              </div>
            )}
            {tab === 'sfx' && (
              <div className="asset-list">
                <p className="hint">Procedural, royalty-free effects generated on your machine.</p>
                {sfxList.map((name) => (
                  <button key={name} className="asset-row" onClick={() => addSfx(name)}><Volume2 size={18} /><span><strong>{name}</strong><small>Insert at playhead</small></span></button>
                ))}
              </div>
            )}
          </div>
        </aside>

        <div className="stage-area">
          <div className="stage-toolbar">
            <div className="aspect-switch">
              {(['9:16', '1:1', '16:9'] as const).map((aspect) => (
                <button key={aspect} className={timeline.aspect === aspect ? 'active' : ''} onClick={() => mutate((draft) => { draft.aspect = aspect; })}>{aspect}</button>
              ))}
            </div>
            <span className="stage-time">{formatClock(playhead)} / {formatClock(total)}</span>
          </div>
          <div className={`stage-frame aspect-${timeline.aspect.replace(':', '-')}`}>
            {activeVideo ? (
              <video
                ref={videoRef}
                src={mediaUrl(`/media/file?path=${encodeURIComponent(activeVideo.path)}`)}
                onTimeUpdate={(event) => {
                  const video = event.currentTarget;
                  setPlayhead(Math.max(0, Math.min(total, activeVideoStart + video.currentTime - activeVideo.sourceStart)));
                }}
                onEnded={() => setPlaying(false)}
              />
            ) : <div className="stage-empty"><Film size={38} /><p>Add a video from the media panel to start editing</p></div>}
            {visibleCaptions.map((caption, index) => (
              <div className="stage-caption" key={index}>{caption.text}</div>
            ))}
            {visibleStickers.map((sticker, index) => sticker.path && (
              <img
                className="stage-sticker"
                key={index}
                src={mediaUrl(`/media/file?path=${encodeURIComponent(sticker.path)}`)}
                style={{ left: `${(sticker.x ?? 0.7) * 100}%`, top: `${(sticker.y ?? 0.15) * 100}%` }}
                alt="sticker"
              />
            ))}
          </div>
          <div className="stage-controls">
            <button className="icon-btn" title="Jump to start" aria-label="Jump to start" onClick={() => seekTo(0)}><SkipBack size={17} /></button>
            <button className="icon-btn" title="Back 5 seconds" aria-label="Back 5 seconds" onClick={() => seekTo(playhead - 5)}><SkipBack size={17} /></button>
            <button
              className={`play-btn ${playing ? 'is-playing' : ''}`}
              title={playing ? 'Pause' : 'Play'}
              aria-label={playing ? 'Pause' : 'Play'}
              onClick={() => {
                if (!videoRef.current) return;
                if (videoRef.current.paused) { void videoRef.current.play(); setPlaying(true); }
                else { videoRef.current.pause(); setPlaying(false); }
              }}
            >{playing ? <Pause size={19} fill="currentColor" /> : <Play size={19} fill="currentColor" />}</button>
            <button className="icon-btn" title="Forward 5 seconds" aria-label="Forward 5 seconds" onClick={() => seekTo(playhead + 5)}><SkipForward size={17} /></button>
            <button className="icon-btn" title="Jump to end" aria-label="Jump to end" onClick={() => seekTo(total)}><SkipForward size={17} /></button>
            <span className="stage-time">{formatClock(playhead)} / {formatClock(total)}</span>
          </div>
          <p className="stage-hint">Shortcuts: Space play/pause · S split · Delete remove selected</p>
        </div>

        <aside className="inspector">
          <h3><Layers3 size={16} /> Inspector</h3>
          {!selectedItem ? <p className="hint">Select a block on the timeline to edit its properties.</p> : (
            <div className="inspector-fields">
              <Pill>{selected?.track}</Pill>
              {'text' in selectedItem && <label className="field"><span>Caption text</span><textarea rows={3} value={selectedItem.text || ''} onChange={(event) => updateSelected({ text: event.target.value })} /></label>}
              {'path' in selectedItem && <label className="field"><span>Source</span><input readOnly value={selectedItem.path || ''} /></label>}
              {'sourceStart' in selectedItem && <label className="field"><span>Source in (s)</span><input type="number" step="0.1" value={selectedItem.sourceStart || 0} onChange={(event) => updateSelected({ sourceStart: Number(event.target.value) })} /></label>}
              {'duration' in selectedItem && <label className="field"><span>Duration (s)</span><input type="number" step="0.1" value={selectedItem.duration || 0} onChange={(event) => updateSelected({ duration: Number(event.target.value) })} /></label>}
              {'start' in selectedItem && <label className="field"><span>Start (s)</span><input type="number" step="0.1" value={selectedItem.start || 0} onChange={(event) => updateSelected({ start: Number(event.target.value) })} /></label>}
              {'end' in selectedItem && <label className="field"><span>End (s)</span><input type="number" step="0.1" value={selectedItem.end || 0} onChange={(event) => updateSelected({ end: Number(event.target.value) })} /></label>}
              {'volume' in selectedItem && <label className="field"><span>Volume</span><input type="range" min="0" max="1" step="0.05" value={selectedItem.volume ?? 0.5} onChange={(event) => updateSelected({ volume: Number(event.target.value) })} /></label>}
              {'x' in selectedItem && <><label className="field"><span>Position X</span><input type="range" min="0" max="1" step="0.01" value={selectedItem.x ?? 0.7} onChange={(event) => updateSelected({ x: Number(event.target.value) })} /></label><label className="field"><span>Position Y</span><input type="range" min="0" max="1" step="0.01" value={selectedItem.y ?? 0.15} onChange={(event) => updateSelected({ y: Number(event.target.value) })} /></label></>}
              <button className="ghost-btn" onClick={removeSelected}><Trash2 size={15} /> Remove item</button>
            </div>
          )}
          {exportOutput && <a className="primary block" href={mediaUrl('/media/file?path=' + encodeURIComponent(exportOutput) + '&download=true')} download><Download size={16} /> Download exported MP4</a>}
          {exportJob && <JobTracker jobId={exportJob} label="Rendering project" />}
        </aside>
      </div>

      <div className="auto-edit-strip">
        <div className="auto-edit-head">
          <strong><Sparkles size={14} /> Auto edit</strong>
          <span>{clips.length} AI clip(s) ready</span>
          <select value={autoStyle} onChange={(event) => setAutoStyle(event.target.value as typeof autoStyle)}>
            <option value="hype">High energy</option><option value="minimal">Minimal</option><option value="premium">Premium</option>
          </select>
          <button className="primary" disabled={!clips.length || Boolean(autoJob)} onClick={() => void runAutoEdit()}>
            {autoJob ? <LoaderCircle size={14} className="spin" /> : <WandSparkles size={14} />} Auto edit &amp; render all
          </button>
        </div>
        {autoJob && <JobTracker jobId={autoJob} label="Automatic editing" />}
        <div className="auto-edit-clips">
          {clips.length === 0 && <span className="hint">Generate clips in AI Clipper — they will appear here automatically.</span>}
          {clips.map((clip) => (
            <div className="auto-edit-clip" key={clip.id}>
              <div><strong>{clip.title}</strong><small>{formatClock(clip.start)} → {formatClock(clip.end)} · {Math.round(clip.score)}/100</small></div>
              <button className="icon-btn" title="Render with auto edit" aria-label="Render with auto edit" onClick={() => void renderAutoClip(clip)}><Download size={14} /></button>
              {clip.output && <a className="icon-btn" title="Download rendered MP4" aria-label="Download rendered MP4" href={mediaUrl('/media/file?path=' + encodeURIComponent(clip.output) + '&download=true')} download><Check size={14} /></a>}
            </div>
          ))}
        </div>
      </div>

      <div className="timeline-panel">
        <div className="timeline-toolbar">
          <div><strong>Timeline</strong> <Pill tone="muted">{formatClock(total)}</Pill></div>
          <div className="timeline-actions">
            <div className="timeline-tools">
              <button className="icon-btn" title="Auto captions with Whisper" aria-label="Auto captions" onClick={autoCaptions}><Captions size={15} /></button>
              <button className="icon-btn" title="Generate AI art" aria-label="Generate AI art" onClick={() => setTab('art')}><ImagePlus size={15} /></button>
              <button className="icon-btn" title="Sound effects" aria-label="Sound effects" onClick={() => setTab('sfx')}><Volume2 size={15} /></button>
              <button className="icon-btn" title="Split clip at playhead" aria-label="Split clip" onClick={splitSelected}><Split size={15} /></button>
              <button className="icon-btn" title="Delete selected item" aria-label="Delete selected item" onClick={removeSelected}><Trash2 size={15} /></button>
              <button className="icon-btn" title="Save project" aria-label="Save project" onClick={() => void save()}><Save size={15} /></button>
              <button className="icon-btn primary-icon" title="Export video" aria-label="Export video" onClick={() => void exportVideo()}><Download size={15} /></button>
            </div>
            <label>Zoom <input type="range" min="8" max="90" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} /></label>
          </div>
        </div>
        <div className="timeline-body">
          <div className="track-labels">
            <div className="ruler-spacer" />
            {(['video', 'captions', 'stickers', 'audio'] as TrackKey[]).map((track) => (
              <div className="track-label" key={track}>
                {track === 'video' ? <Film size={14} /> : track === 'captions' ? <Captions size={14} /> : track === 'stickers' ? <ImagePlus size={14} /> : <Mic2 size={14} />}
                <span>{track}</span>
              </div>
            ))}
          </div>
          <div
            className="timeline-scroll"
            ref={timelineRef}
            onPointerDown={(event) => { scrubbingRef.current = true; scrub(event); }}
            onPointerMove={(event) => { if (scrubbingRef.current) scrub(event); }}
            onPointerUp={() => { scrubbingRef.current = false; }}
            onPointerLeave={() => { scrubbingRef.current = false; }}
          >
            <div className="timeline-content" style={{ width: Math.max(600, total * zoom + 120) }}>
              <div className="ruler">
                {Array.from({ length: Math.floor(total / 5) + 2 }, (_, index) => (
                  <span key={index} style={{ left: index * 5 * zoom }}>{formatClock(index * 5)}</span>
                ))}
              </div>
              {(['video', 'captions', 'stickers', 'audio'] as TrackKey[]).map((track) => (
                <div className="track" key={track}>
                  <div className="track-lane">
                    {(timeline.tracks[track] as unknown as AnyItem[]).map((item, index) => {
                      const start = track === 'video'
                        ? timeline.tracks.video.slice(0, index).reduce((sum, part) => sum + part.duration, 0)
                        : (item.start || 0);
                      const duration = track === 'video' ? item.duration || 1 : Math.max(0.6, (item.end || item.start || 0) - (item.start || 0));
                      return (
                        <button
                          key={`${track}-${index}`}
                          className={`clip-block block-${track} ${selected?.track === track && selected.index === index ? 'selected' : ''}`}
                          style={{ left: start * zoom, width: Math.max(18, duration * zoom) }}
                          onClick={() => { setSelected({ track, index }); setPlayhead(start + 0.05); }}
                          title={item.label || item.text || item.path}
                        >
                          {item.text || item.label || (item.path || 'clip').split(/[\\/]/).pop()}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
              <div className="playhead" style={{ left: playhead * zoom }} />
            </div>
          </div>
        </div>
      </div>
      {busy && <div className="busy-badge"><LoaderCircle size={15} className="spin" /> Working…</div>}
    </div>
  );
}

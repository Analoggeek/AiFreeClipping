import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowLeft, ArrowRight, BoxSelect, Check, Clapperboard, Copy, Cpu, Download, Film, ImagePlus,
  LoaderCircle, WandSparkles, Pause, Play, Plus, Scissors, Send, Sparkles, Volume2,
} from 'lucide-react';
import { api, mediaUrl, pollJob } from '../api';
import { EmptyState, formatClock, JobTracker, Panel, Pill } from '../components/common';
import type { Candidate, Media } from '../types';
import type { PageProps } from '../App';

type Box = { x: number; y: number; w: number; h: number };
type RegionItem = { id: string; label: string; box: Box; color: string };
type RegionLayout = { preset: string; boxes: RegionItem[] };
type Props = PageProps & { mediaSelection: string[]; setMediaSelection: (ids: string[]) => void };

const STEPS = ['Select videos', 'Mark region', 'Viral settings', 'AI results'];

const FULL: Box = { x: 0, y: 0, w: 1, h: 1 };
const REGION_PRESETS: Array<{ id: string; label: string; icon: string; boxes: Array<{ id: string; label: string; box: Box }> }> = [
  { id: 'full', label: 'Full frame', icon: '▣', boxes: [] },
  {
    id: 'top-game-bottom-player', label: 'Gameplay top · player bottom', icon: '▤▣',
    boxes: [
      { id: 'gameplay', label: 'Gameplay', box: { x: 0, y: 0, w: 1, h: 0.58 } },
      { id: 'player', label: 'Player', box: { x: 0, y: 0.58, w: 1, h: 0.42 } },
    ],
  },
  {
    id: 'top-player-bottom-game', label: 'Player top · gameplay bottom', icon: '◉▤',
    boxes: [
      { id: 'player', label: 'Player', box: { x: 0, y: 0, w: 1, h: 0.42 } },
      { id: 'gameplay', label: 'Gameplay', box: { x: 0, y: 0.42, w: 1, h: 0.58 } },
    ],
  },
  {
    id: 'square-player-full-game', label: 'Square player · full gameplay', icon: '◱',
    boxes: [
      { id: 'gameplay', label: 'Gameplay', box: FULL },
      { id: 'player', label: 'Player (square)', box: { x: 0.03, y: 0.03, w: 0.34, h: 0.34 } },
    ],
  },
  {
    id: 'side-by-side', label: 'Player side · gameplay side', icon: '◫',
    boxes: [
      { id: 'gameplay', label: 'Gameplay', box: { x: 0, y: 0, w: 0.62, h: 1 } },
      { id: 'player', label: 'Player', box: { x: 0.62, y: 0, w: 0.38, h: 1 } },
    ],
  },
];

const COLORS = ['#22d3ee', '#a78bfa', '#34d399', '#fbbf24'];

export default function Clipper({ notify, openEditor, openPublish, mediaSelection, setMediaSelection }: Props) {
  const [media, setMedia] = useState<Media[]>([]);
  const [step, setStep] = useState(0);
  const [regions, setRegions] = useState<Record<string, RegionLayout>>({});
  const [activeRegionId, setActiveRegionId] = useState('gameplay');
  const [settings, setSettings] = useState({
    count: 5, min_duration: 15, max_duration: 60, platform: 'shorts', style: 'hype',
    captions: true, sound_effects: true, stickers: true, use_llm: true, music: '',
  });
  const [jobId, setJobId] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [checked, setChecked] = useState<string[]>([]);
  const [renderJobs, setRenderJobs] = useState<Record<string, string>>({});
  const [batchJob, setBatchJob] = useState<string | null>(null);
  const [hardwareByClip, setHardwareByClip] = useState<Record<string, Record<string, unknown>>>({});
  const [busy, setBusy] = useState(false);
  const [previewTime, setPreviewTime] = useState(0);
  const [previewPlaying, setPreviewPlaying] = useState(false);
  const regionVideoRef = useRef<HTMLVideoElement>(null);
  const cropCanvasRef = useRef<HTMLCanvasElement>(null);

  const refresh = useCallback(() => {
    api.media().then((result) => setMedia(result.media)).catch(() => undefined);
    api.clips().then((result) => setCandidates(result.clips)).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);

  const selectedMedia = media.filter((item) => mediaSelection.includes(item.id));
  const preview = selectedMedia[0];
  const layout: RegionLayout = preview ? regions[preview.id] || { preset: 'full', boxes: [] } : { preset: 'full', boxes: [] };
  const activeRegion = layout.boxes.find((item) => item.id === activeRegionId) || layout.boxes[0] || null;

  const applyPreset = (preset: typeof REGION_PRESETS[number]) => {
    if (!preview) return;
    const boxes = preset.boxes.map((item, index) => ({ ...item, color: COLORS[index % COLORS.length] }));
    setRegions((current) => ({ ...current, [preview.id]: { preset: preset.id, boxes } }));
    if (boxes[0]) setActiveRegionId(boxes[0].id);
  };

  const updateBox = (regionId: string, box: Box) => {
    if (!preview) return;
    setRegions((current) => {
      const existing = current[preview.id] || { preset: 'custom', boxes: [] };
      const boxes = existing.boxes.some((item) => item.id === regionId)
        ? existing.boxes.map((item) => item.id === regionId ? { ...item, box } : item)
        : [...existing.boxes, { id: regionId, label: regionId, box, color: COLORS[existing.boxes.length % COLORS.length] }];
      return { ...current, [preview.id]: { preset: 'custom', boxes } };
    });
  };

  const removeBox = (regionId: string) => {
    if (!preview) return;
    setRegions((current) => {
      const existing = current[preview.id] || { preset: 'full', boxes: [] };
      const boxes = existing.boxes.filter((item) => item.id !== regionId);
      return { ...current, [preview.id]: { preset: boxes.length ? 'custom' : 'full', boxes } };
    });
  };

  const addCustomRegion = () => {
    if (!preview) return;
    const index = layout.boxes.length + 1;
    const region: RegionItem = {
      id: `custom-${Date.now()}`, label: `Custom focus ${index}`,
      box: { x: 0.2, y: 0.2, w: 0.6, h: 0.6 }, color: COLORS[(index - 1) % COLORS.length],
    };
    setRegions((current) => ({ ...current, [preview.id]: { preset: 'custom', boxes: [...layout.boxes, region] } }));
    setActiveRegionId(region.id);
  };

  const copyRegionToSelected = () => {
    if (!preview || selectedMedia.length < 2) return;
    setRegions((current) => {
      const selectedLayout = current[preview.id] || { preset: 'full', boxes: [] };
      const next = { ...current };
      for (const item of selectedMedia) {
        if (item.id !== preview.id) {
          next[item.id] = {
            preset: selectedLayout.preset,
            boxes: selectedLayout.boxes.map((box) => ({ ...box, box: { ...box.box } })),
          };
        }
      }
      return next;
    });
    notify(`Region layout copied to ${selectedMedia.length - 1} other selected video(s).`);
  };

  const cropBox = activeRegion?.box || FULL;
  const cropAspect = settings.platform === 'landscape' ? 16 / 9 : 9 / 16;
  useEffect(() => {
    const video = regionVideoRef.current;
    const canvas = cropCanvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext('2d');
    canvas.width = 480;
    canvas.height = Math.round(480 / cropAspect);
    if (!video || !context) return;
    const draw = () => {
      const frameWidth = video.videoWidth;
      const frameHeight = video.videoHeight;
      if (!frameWidth || !frameHeight) return;
      let x = Math.max(0, Math.min(0.95, cropBox.x));
      let y = Math.max(0, Math.min(0.95, cropBox.y));
      let width = Math.max(0.05, Math.min(1 - x, cropBox.w));
      let height = Math.max(0.05, Math.min(1 - y, cropBox.h));
      if (width * height < 0.25) {
        const scale = Math.min(Math.sqrt(0.25 / Math.max(1e-6, width * height)), 1 / Math.max(width, height));
        const expandedWidth = Math.min(1, width * scale);
        const expandedHeight = Math.min(1, height * scale);
        x = Math.max(0, Math.min(x - (expandedWidth - width) / 2, 1 - expandedWidth));
        y = Math.max(0, Math.min(y - (expandedHeight - height) / 2, 1 - expandedHeight));
        width = expandedWidth;
        height = expandedHeight;
      }
      const sx = x * frameWidth;
      const sy = y * frameHeight;
      const sw = Math.max(1, width * frameWidth);
      const sh = Math.max(1, height * frameHeight);
      const outWidth = canvas.width;
      const outHeight = canvas.height;
      context.clearRect(0, 0, outWidth, outHeight);
      context.fillStyle = '#05070e';
      context.fillRect(0, 0, outWidth, outHeight);
      const cover = Math.max(outWidth / sw, outHeight / sh);
      const bgWidth = sw * cover;
      const bgHeight = sh * cover;
      context.save();
      context.filter = 'blur(18px)';
      context.drawImage(video, sx, sy, sw, sh, (outWidth - bgWidth) / 2, (outHeight - bgHeight) / 2, bgWidth, bgHeight);
      context.restore();
      const contain = Math.min(outWidth / sw, outHeight / sh);
      const fgWidth = sw * contain;
      const fgHeight = sh * contain;
      context.drawImage(video, sx, sy, sw, sh, (outWidth - fgWidth) / 2, (outHeight - fgHeight) / 2, fgWidth, fgHeight);
    };
    let animation = 0;
    const tick = () => {
      draw();
      if (!video.paused && !video.ended) animation = window.requestAnimationFrame(tick);
    };
    const start = () => { draw(); if (!video.paused) animation = window.requestAnimationFrame(tick); };
    video.addEventListener('loadeddata', start);
    video.addEventListener('seeked', draw);
    video.addEventListener('timeupdate', draw);
    video.addEventListener('play', start);
    draw();
    return () => {
      video.removeEventListener('loadeddata', start);
      video.removeEventListener('seeked', draw);
      video.removeEventListener('timeupdate', draw);
      video.removeEventListener('play', start);
      if (animation) window.cancelAnimationFrame(animation);
    };
  }, [preview?.id, cropBox.x, cropBox.y, cropBox.w, cropBox.h, cropAspect]);

  const importFiles = async () => {
    if (!window.desktop) { notify('Local file picker works inside the desktop app.'); return; }
    const paths = await window.desktop.selectFiles();
    if (!paths.length) return;
    try {
      const result = await api.importMedia(paths);
      setMedia((current) => [...result.media, ...current]);
      setMediaSelection([...new Set([...mediaSelection, ...result.media.map((item) => item.id)])]);
      notify(`Imported ${result.media.length} local file(s).`);
    } catch (error) { notify(String(error)); }
  };

  const findMoments = async () => {
    if (!mediaSelection.length) { notify('Select at least one video first.'); return; }
    setBusy(true);
    try {
      const result = await api.propose({
        media_ids: mediaSelection,
        regions: mediaSelection.map((id) => {
          const selection = regions[id] || { preset: 'full', boxes: [] };
          return {
            media_id: id,
            kind: selection.boxes.length ? 'custom' : 'full',
            box: selection.boxes[0]?.box,
            boxes: selection.boxes.map((item) => item.box),
            layout: selection.preset,
          };
        }),
        ...settings,
      });
      setJobId(result.job_id);
    } catch (error) { notify(String(error)); } finally { setBusy(false); }
  };

  useEffect(() => {
    if (!jobId) return;
    return pollJob(jobId, (job) => {
      if (job.status === 'done') {
        void api.clips().then((result) => setCandidates(result.clips));
        notify('Viral moments are ready for review.');
      }
      if (job.status === 'error') notify(job.error || job.message);
      if (job.status === 'cancelled') notify('AI analysis cancelled.');
    });
  }, [jobId, notify]);

  const effectPayload = (clip?: Candidate) => {
    const preset = ({ hype: 'hype', story: 'minimal', clean: 'minimal', cinematic: 'premium' } as const)[settings.style as 'hype' | 'story' | 'clean' | 'cinematic'] || 'hype';
    return {
      aspect: settings.platform === 'landscape' ? '16:9' : '9:16',
      resolution: '1080p',
      caption_style: { preset: settings.captions ? preset : 'none' },
      sfx: settings.sound_effects ? ['whoosh', 'pop'] : [],
      speed: 1, brightness: 0, contrast: 1, saturation: 1,
      blur_background: true, watermark: true,
      // A candidate keeps the exact region chosen when it was analyzed; never
      // let the currently previewed source silently override that saved crop.
      region: clip ? clip.region || null : null,
      regions: clip ? clip.regions || [] : [],
    };
  };

  const copyEffectsToAll = async () => {
    const ids = candidates.map((clip) => clip.id || '').filter(Boolean);
    if (!ids.length) { notify('Generate clips first.'); return; }
    try {
      const result = await api.applyEffects(ids, effectPayload());
      notify(`Copied this clip's effects to ${result.changed} clip(s).`);
    } catch (error) { notify(String(error)); }
  };

  const renderOne = async (clip: Candidate) => {
    const clipId = clip.id || '';
    if (!clipId) return;
    try {
      const result = await api.renderClip(clipId, effectPayload(clip));
      setRenderJobs((current) => ({ ...current, [clipId]: result.job_id }));
    } catch (error) { notify(String(error)); }
  };

  const exportAll = async () => {
    const ids = checked.length ? checked : candidates.map((clip) => clip.id || '').filter(Boolean);
    if (!ids.length) { notify('No clips to export yet.'); return; }
    try {
      const result = await api.exportBatch(ids);
      setBatchJob(result.job_id);
    } catch (error) { notify(String(error)); }
  };

  return (
    <div className="stack">
      <div className="stepper">
        {STEPS.map((label, index) => (
          <button key={label} className={`step ${index === step ? 'active' : ''} ${index < step ? 'done' : ''}`} onClick={() => setStep(index)}>
            <span>{index < step ? <Check size={14} /> : index + 1}</span>{label}
          </button>
        ))}
      </div>

      {step === 0 && (
        <Panel title="Select source videos" subtitle="Clip one video or combine several — imported local files work too" action={<button className="ghost-btn" onClick={importFiles}><Plus size={15} /> Import local files</button>}>
          {media.length === 0 ? <EmptyState icon={<Film size={30} />} title="Your library is empty" detail="Download videos first, or import a file from your computer." /> : (
            <div className="select-grid">
              {media.map((item) => {
                const active = mediaSelection.includes(item.id);
                return (
                  <button key={item.id} className={`select-card ${active ? 'active' : ''}`} onClick={() => setMediaSelection(active ? mediaSelection.filter((id) => id !== item.id) : [...mediaSelection, item.id])}>
                    <div className="thumb">{item.thumbnail ? <img src={mediaUrl(item.thumbnail)} alt="" /> : <Film size={24} />}<span>{formatClock(item.duration)}</span></div>
                    <strong>{item.title}</strong>
                    <small>{active ? 'Selected' : 'Click to select'}</small>
                  </button>
                );
              })}
            </div>
          )}
          <div className="panel-actions"><button className="primary" disabled={!mediaSelection.length} onClick={() => setStep(1)}>Continue to region <ArrowRight size={16} /></button></div>
        </Panel>
      )}

      {step === 1 && (
        <Panel title="Choose what the AI should watch" subtitle="Mark several areas in the same clip — player, gameplay, HUD or anything else. The AI scores every selected area.">
          <div className="region-layout">
            <div className="region-preview">
              {preview ? (
                <>
                  <div className="video-stage">
                    <video
                      ref={regionVideoRef}
                      src={mediaUrl(`/api/media/${preview.id}/stream`)}
                      playsInline
                      preload="metadata"
                      onTimeUpdate={(event) => setPreviewTime(event.currentTarget.currentTime)}
                      onPlay={() => setPreviewPlaying(true)}
                      onPause={() => setPreviewPlaying(false)}
                      onEnded={() => setPreviewPlaying(false)}
                    />
                    <RegionOverlay
                      boxes={layout.boxes}
                      activeId={activeRegion?.id || ''}
                      sourceAspect={preview.width && preview.height ? preview.width / preview.height : 16 / 9}
                      onChange={(box) => activeRegion && updateBox(activeRegion.id, box)}
                    />
                  </div>
                  <div className="region-transport">
                    <button className="icon-btn" title={previewPlaying ? 'Pause source preview' : 'Play source preview'} onClick={() => {
                      const video = regionVideoRef.current;
                      if (!video) return;
                      if (video.paused) void video.play().catch((error) => notify(String(error)));
                      else video.pause();
                    }}>{previewPlaying ? <Pause size={15} /> : <Play size={15} />}</button>
                    <input
                      aria-label="Source video preview position"
                      type="range" min="0" max={Math.max(0.1, preview.duration || 0.1)} step="0.1"
                      value={Math.min(previewTime, preview.duration || 0)}
                      onChange={(event) => {
                        const value = Number(event.target.value);
                        setPreviewTime(value);
                        if (regionVideoRef.current) regionVideoRef.current.currentTime = value;
                      }}
                    />
                    <span>{previewTime.toFixed(1)}s / {(preview.duration || 0).toFixed(1)}s</span>
                  </div>
                </>
              ) : <EmptyState icon={<BoxSelect size={28} />} title="No video selected" detail="Go back and select a video." />}
            </div>
            <div className="region-side">
              <h3>Layout presets</h3>
              {REGION_PRESETS.map((preset) => (
                <button key={preset.id} className={`preset ${layout.preset === preset.id ? 'active' : ''}`} onClick={() => applyPreset(preset)}>
                  <b>{preset.icon}</b>{preset.label}
                </button>
              ))}
              <button className="chip-btn add-region" disabled={!preview} onClick={addCustomRegion}><Plus size={14} /> Add custom region</button>
              <h3 className="region-subhead">Areas in this clip</h3>
              {layout.boxes.length === 0 && <p className="hint">Full frame is selected. Add a custom region, choose an area, then drag on the video to crop to it.</p>}
              {layout.boxes.map((item) => (
                <div key={item.id} className={`region-chip ${activeRegion?.id === item.id ? 'active' : ''}`}>
                  <button onClick={() => setActiveRegionId(item.id)}><i style={{ background: item.color }} />{item.label} · {Math.round(item.box.w * 100)}×{Math.round(item.box.h * 100)}%</button>
                  <button className="region-remove" title={`Remove ${item.label}`} onClick={() => removeBox(item.id)}>×</button>
                </div>
              ))}
              <p className="hint">Choose an area above, then drag on the source video to redraw it. The rendered MP4 and the preview at right use the same crop.</p>
              {selectedMedia.length > 1 && (
                <div className="region-copy-row">
                  <Pill tone="amber">{selectedMedia.length} videos selected</Pill>
                  <button className="chip-btn" onClick={copyRegionToSelected}>Use this region for all</button>
                </div>
              )}
              <div className="panel-actions"><button className="ghost-btn" onClick={() => setStep(0)}><ArrowLeft size={15} /> Back</button><button className="primary" onClick={() => setStep(2)}>Next <ArrowRight size={16} /></button></div>
            </div>
            <div className="crop-preview-card">
              <h3>Live crop preview</h3>
              <p className="hint">This is the current frame after the selected crop and platform framing.</p>
              <div className={`crop-preview-frame ${settings.platform === 'landscape' ? 'landscape' : 'portrait'}`}>
                <canvas ref={cropCanvasRef} aria-label="Live preview of the selected crop" />
              </div>
              <Pill tone={activeRegion ? 'green' : 'muted'}>{activeRegion ? `${activeRegion.label} · ${Math.round(activeRegion.box.w * 100)}×${Math.round(activeRegion.box.h * 100)}%` : 'Full frame'}</Pill>
              <small className="crop-preview-time">Preview frame: {previewTime.toFixed(1)}s</small>
            </div>
          </div>
        </Panel>
      )}

      {step === 2 && (
        <Panel title="Viral clip settings" subtitle="Tune the AI to your channel style — every setting flows into the editor and export">
          <div className="form-grid four">
            <label className="field"><span>Number of clips</span><input type="number" min={1} max={30} value={settings.count} onChange={(event) => setSettings({ ...settings, count: Number(event.target.value) })} /></label>
            <label className="field"><span>Minimum seconds</span><input type="number" min={5} max={120} value={settings.min_duration} onChange={(event) => setSettings({ ...settings, min_duration: Number(event.target.value) })} /></label>
            <label className="field"><span>Maximum seconds</span><input type="number" min={10} max={180} value={settings.max_duration} onChange={(event) => setSettings({ ...settings, max_duration: Number(event.target.value) })} /></label>
            <label className="field"><span>Platform</span>
              <select value={settings.platform} onChange={(event) => setSettings({ ...settings, platform: event.target.value })}>
                <option value="shorts">YouTube Shorts</option><option value="reels">Instagram Reels</option><option value="tiktok">TikTok</option><option value="landscape">Landscape video</option>
              </select>
            </label>
            <label className="field"><span>Editing style</span>
              <select value={settings.style} onChange={(event) => setSettings({ ...settings, style: event.target.value })}>
                <option value="hype">High energy</option><option value="story">Storytelling</option><option value="clean">Clean / minimal</option><option value="cinematic">Cinematic</option>
              </select>
            </label>
            <label className="field"><span>Background music path (optional)</span><input value={settings.music} onChange={(event) => setSettings({ ...settings, music: event.target.value })} placeholder="~/.AiFreeClipping/assets/music/track.mp3" /></label>
          </div>
          <div className="toggle-grid">
            {([
              ['captions', 'Auto captions', <Sparkles size={16} />],
              ['sound_effects', 'Sound effects', <Volume2 size={16} />],
              ['stickers', 'AI stickers / images', <ImagePlus size={16} />],
              ['use_llm', 'Gemma title & rerank', <WandSparkles size={16} />],
            ] as const).map(([key, label, icon]) => (
              <label className="toggle" key={key}>
                <input type="checkbox" checked={settings[key]} onChange={(event) => setSettings({ ...settings, [key]: event.target.checked })} />
                <span>{icon}</span>{label}
              </label>
            ))}
          </div>
          <div className="panel-actions">
            <button className="ghost-btn" onClick={() => setStep(1)}><ArrowLeft size={15} /> Back</button>
            <button className="primary" disabled={busy || !mediaSelection.length} onClick={findMoments}>
              {busy ? <LoaderCircle size={16} className="spin" /> : <Scissors size={17} />} Find viral moments
            </button>
          </div>
          {jobId && <JobTracker jobId={jobId} label="AI analysis pipeline" />}
        </Panel>
      )}

      {step === 3 && (
        <Panel title="AI-picked clips" subtitle={`${candidates.length} candidates — review, tweak, render or open in the editor`} action={
          <div className="panel-actions compact">
            <button className="ghost-btn" onClick={() => void copyEffectsToAll()}><Copy size={15} /> Copy effects to all</button>
            <button className="primary" onClick={exportAll}><Download size={16} /> Export selected ({checked.length || candidates.length})</button>
          </div>
        }>
          {candidates.length === 0 ? <EmptyState icon={<Clapperboard size={30} />} title="No clips yet" detail="Run the AI analysis in step 3 to discover engaging moments." /> : (
            <>
              <div className="candidate-list">
                {candidates.map((clip, index) => {
                  const source = media.find((item) => item.id === clip.media_id);
                  const clipId = clip.id || '';
                  return (
                    <article className="candidate" key={clipId || index}>
                      <div className="candidate-preview">
                        {source?.thumbnail ? <img src={mediaUrl(source.thumbnail)} alt="" /> : <Film size={26} />}
                        <button className="play-overlay" onClick={() => window.open(mediaUrl(`/api/media/${clip.media_id}/stream`) + `#t=${clip.start}`, '_blank')}><Play size={18} /></button>
                      </div>
                      <div className="candidate-body">
                        <div className="candidate-head">
                          <input type="checkbox" checked={checked.includes(clipId)} onChange={() => setChecked((current) => current.includes(clipId) ? current.filter((id) => id !== clipId) : [...current, clipId])} />
                          <strong>{clip.title}</strong>
                        </div>
                        <div className="candidate-meta">
                          <Pill tone={clip.score >= 75 ? 'green' : clip.score >= 55 ? 'amber' : 'muted'}>{Math.round(clip.score)} / 100</Pill>
                          <span>{formatClock(clip.start)} → {formatClock(clip.end)}</span>
                          <span>{Math.round(clip.end - clip.start)}s</span>
                          <span>{source?.title || clip.media_id}</span>
                        </div>
                        <div className="reasons">{clip.reasons.map((reason) => <Pill key={reason} tone="violet">{reason}</Pill>)}</div>
                        {clip.transcript && <p className="transcript">“{clip.transcript.slice(0, 180)}…”</p>}
                        <div className="candidate-actions">
                          <button className="chip-btn" onClick={() => { void api.createProject({ name: clip.title.slice(0, 40), clip_id: clipId }).then(() => openEditor(clipId)); }}><Scissors size={14} /> Edit</button>
                          <button className="chip-btn" onClick={() => renderOne(clip)}><Download size={14} /> Render</button>
                          <button className="chip-btn" onClick={() => openPublish([clipId])}><Send size={14} /> Publish</button>
                          {clip.output && <a className="chip-btn" href={mediaUrl('/media/file?path=' + encodeURIComponent(clip.output) + '&download=true')} download><Check size={14} /> Download MP4</a>}
                        </div>
                        {renderJobs[clipId] && <JobTracker jobId={renderJobs[clipId]} label="Rendering clip" onDone={(job) => {
                          if (job.status === 'done') {
                            notify('Clip rendered — find it in Publish.');
                            if (job.result?.hardware) setHardwareByClip((current) => ({ ...current, [clipId]: job.result!.hardware as Record<string, unknown> }));
                            refresh();
                          }
                        }} />}
                        {hardwareByClip[clipId] && (
                          <div className="hardware-line">
                            <Cpu size={13} />
                            <span>{String((hardwareByClip[clipId].gpu as { name?: string })?.name || 'Hardware')} · CPU {String(hardwareByClip[clipId].cpu_percent ?? '—')}% · RAM {String(hardwareByClip[clipId].ram_used_gb ?? '—')} GB · {String(hardwareByClip[clipId].workers ?? 1)} workers</span>
                            <button className="chip-btn" onClick={() => void navigator.clipboard?.writeText(JSON.stringify(hardwareByClip[clipId], null, 2))}>Copy stats</button>
                          </div>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
              {batchJob && <JobTracker jobId={batchJob} label="Batch export" />}
            </>
          )}
          <div className="panel-actions"><button className="ghost-btn" onClick={() => setStep(2)}><ArrowLeft size={15} /> Back</button></div>
        </Panel>
      )}
      {step < 3 && <div className="hint-bar">Tip: the pipeline uses Gemma 2 7B, faster-whisper and YOLOX/ByteTrack locally — no footage leaves your machine.</div>}
    </div>
  );
}

function RegionOverlay({ boxes, activeId, sourceAspect, onChange }: {
  boxes: RegionItem[]; activeId: string; sourceAspect: number; onChange: (box: Box) => void;
}) {
  const outerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [contentRect, setContentRect] = useState({ left: 0, top: 0, width: 100, height: 100 });
  const [drawing, setDrawing] = useState(false);
  const [start, setStart] = useState({ x: 0, y: 0 });
  const [draft, setDraft] = useState<Box | null>(null);

  useEffect(() => {
    const element = outerRef.current;
    if (!element) return;
    const update = () => {
      const bounds = element.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return;
      const aspect = Number.isFinite(sourceAspect) && sourceAspect > 0 ? sourceAspect : 16 / 9;
      const containerAspect = bounds.width / bounds.height;
      const width = containerAspect > aspect ? bounds.height * aspect : bounds.width;
      const height = containerAspect > aspect ? bounds.height : bounds.width / aspect;
      setContentRect({ left: (bounds.width - width) / 2, top: (bounds.height - height) / 2, width, height });
    };
    update();
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(update) : null;
    observer?.observe(element);
    window.addEventListener('resize', update);
    return () => { observer?.disconnect(); window.removeEventListener('resize', update); };
  }, [sourceAspect]);

  const point = (event: React.PointerEvent) => {
    const rect = contentRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
    };
  };
  const normalise = (a: { x: number; y: number }, b: { x: number; y: number }): Box => ({
    x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y),
  });
  const rectStyle = (box: Box) => ({
    left: `${box.x * 100}%`, top: `${box.y * 100}%`, width: `${box.w * 100}%`, height: `${box.h * 100}%`,
  });

  return (
    <div className="region-overlay" ref={outerRef}>
      <div
        className="region-content"
        ref={contentRef}
        style={{ left: contentRect.left, top: contentRect.top, width: contentRect.width, height: contentRect.height }}
        onPointerDown={(event) => {
          if (!activeId || event.button !== 0) return;
          event.preventDefault();
          setDrawing(true);
          const p = point(event);
          setStart(p);
          setDraft({ ...p, w: 0, h: 0 });
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => { if (drawing) setDraft(normalise(start, point(event))); }}
        onPointerUp={() => {
          setDrawing(false);
          if (draft && draft.w > 0.03 && draft.h > 0.03) onChange(draft);
          setDraft(null);
        }}
        onPointerCancel={() => { setDrawing(false); setDraft(null); }}
      >
        {boxes.map((item) => (
          <div key={item.id} className={`region-box ${item.id === activeId ? 'active' : ''}`} style={{ ...rectStyle(item.box), borderColor: item.color }}>
            <span style={{ background: item.color }}>{item.label} · {Math.round(item.box.w * 100)}×{Math.round(item.box.h * 100)}%</span>
          </div>
        ))}
        {draft && draft.w > 0 && <div className="region-box draft" style={rectStyle(draft)}><span>Drawing…</span></div>}
      </div>
    </div>
  );
}

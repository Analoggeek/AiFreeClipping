import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowLeft, ArrowRight, BoxSelect, Check, Clapperboard, Copy, Cpu, Download, Film, ImagePlus,
  LoaderCircle, WandSparkles, Play, Plus, Scissors, Send, Sparkles, Volume2,
} from 'lucide-react';
import { api, mediaUrl, pollJob } from '../api';
import { EmptyState, formatClock, JobTracker, Panel, Pill } from '../components/common';
import type { Candidate, Media } from '../types';
import type { PageProps } from '../App';

type Box = { x: number; y: number; w: number; h: number };
type Props = PageProps & { mediaSelection: string[]; setMediaSelection: (ids: string[]) => void };

const STEPS = ['Select videos', 'Mark region', 'Viral settings', 'AI results'];

export default function Clipper({ notify, openEditor, openPublish, mediaSelection, setMediaSelection }: Props) {
  const [media, setMedia] = useState<Media[]>([]);
  const [step, setStep] = useState(0);
  const [regions, setRegions] = useState<Record<string, Box | null>>({});
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

  const refresh = useCallback(() => {
    api.media().then((result) => setMedia(result.media)).catch(() => undefined);
    api.clips().then((result) => setCandidates(result.clips)).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);

  const selectedMedia = media.filter((item) => mediaSelection.includes(item.id));
  const preview = selectedMedia[0];
  const activeBox = preview ? regions[preview.id] || null : null;

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
        regions: mediaSelection.map((id) => ({
          media_id: id,
          kind: regions[id] ? 'custom' : 'full',
          box: regions[id] || undefined,
        })),
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
    });
  }, [jobId, notify]);

  const effectPayload = () => {
    const preset = ({ hype: 'hype', story: 'minimal', clean: 'minimal', cinematic: 'premium' } as const)[settings.style as 'hype' | 'story' | 'clean' | 'cinematic'] || 'hype';
    return {
      aspect: settings.platform === 'landscape' ? '16:9' : '9:16',
      resolution: '1080p',
      caption_style: { preset: settings.captions ? preset : 'none' },
      sfx: settings.sound_effects ? ['whoosh', 'pop'] : [],
      speed: 1, brightness: 0, contrast: 0, saturation: 1,
      blur_background: true, watermark: true,
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
      const result = await api.renderClip(clipId, effectPayload());
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
        <Panel title="Choose the area that matters" subtitle="Draw a box over the player or gameplay region — the AI will focus its visual scoring there">
          <div className="region-layout">
            <div className="region-preview">
              {preview ? (
                <div className="video-stage">
                  <video src={mediaUrl(`/api/media/${preview.id}/stream`)} controls playsInline />
                  <RegionOverlay box={activeBox} onChange={(box) => setRegions((current) => ({ ...current, [preview.id]: box }))} />
                </div>
              ) : <EmptyState icon={<BoxSelect size={28} />} title="No video selected" detail="Go back and select a video." />}
            </div>
            <div className="region-side">
              <h3>Region presets</h3>
              {[
                { name: 'Full frame', box: null as Box | null, icon: '▣' },
                { name: 'Player / subject', box: { x: 0.15, y: 0.1, w: 0.7, h: 0.7 } as Box, icon: '◉' },
                { name: 'Gameplay HUD', box: { x: 0.05, y: 0.35, w: 0.9, h: 0.55 } as Box, icon: '▤' },
              ].map((preset) => (
                <button key={preset.name} className={`preset ${activeBox === preset.box ? 'active' : ''}`} onClick={() => preview && setRegions((current) => ({ ...current, [preview.id]: preset.box }))}>
                  <b>{preset.icon}</b>{preset.name}
                </button>
              ))}
              <p className="hint">Drag directly on the video to draw a custom area. Press “Full frame” to clear the selection.</p>
              {selectedMedia.length > 1 && <Pill tone="amber">{selectedMedia.length} videos selected — first one shown</Pill>}
              <div className="panel-actions"><button className="ghost-btn" onClick={() => setStep(0)}><ArrowLeft size={15} /> Back</button><button className="primary" onClick={() => setStep(2)}>Next <ArrowRight size={16} /></button></div>
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
                          {clip.output && <a className="chip-btn" href={mediaUrl('/media/file?path=' + encodeURIComponent(clip.output))} download><Check size={14} /> Download</a>}
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

function RegionOverlay({ box, onChange }: { box: Box | null; onChange: (box: Box) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [drawing, setDrawing] = useState(false);
  const [start, setStart] = useState({ x: 0, y: 0 });
  const [current, setCurrent] = useState<Box | null>(box);

  useEffect(() => setCurrent(box), [box]);
  const point = (event: React.PointerEvent) => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
    };
  };
  const normalise = (a: { x: number; y: number }, b: { x: number; y: number }): Box => ({
    x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y),
  });

  return (
    <div
      className="region-overlay"
      ref={ref}
      onPointerDown={(event) => { setDrawing(true); const p = point(event); setStart(p); setCurrent({ ...p, w: 0, h: 0 }); (event.target as HTMLElement).setPointerCapture(event.pointerId); }}
      onPointerMove={(event) => { if (drawing) setCurrent(normalise(start, point(event))); }}
      onPointerUp={() => { setDrawing(false); if (current && current.w > 0.03 && current.h > 0.03) onChange(current); }}
    >
      {current && current.w > 0 && <div className="region-box" style={{ left: `${current.x * 100}%`, top: `${current.y * 100}%`, width: `${current.w * 100}%`, height: `${current.h * 100}%` }}><span>{Math.round(current.w * 100)}% × {Math.round(current.h * 100)}%</span></div>}
    </div>
  );
}

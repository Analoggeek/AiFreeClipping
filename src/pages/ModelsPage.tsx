import { useCallback, useEffect, useState } from 'react';
import { Boxes, CheckCircle2, Cpu, Download, Gauge, LoaderCircle, Package, RefreshCw, Sparkles } from 'lucide-react';
import { api, pollJob } from '../api';
import { JobTracker, Panel, Pill } from '../components/common';
import type { Capabilities, ModelInfo } from '../types';

export default function ModelsPage({ notify }: { notify: (message: string) => void }) {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [caps, setCaps] = useState<Capabilities>({});
  const [jobs, setJobs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [modelResult, capResult] = await Promise.all([api.models(), api.capabilities()]);
      setModels(modelResult.models);
      setCaps(capResult);
    } catch { /* offline */ }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  const install = async (id: string) => {
    setBusy(id);
    try {
      const result = await api.installModel(id);
      setJobs((current) => ({ ...current, [id]: result.job_id }));
    }
    catch (error) { notify(String(error)); setBusy(null); }
  };

  useEffect(() => {
    Object.entries(jobs).forEach(([id, jobId]) => {
      pollJob(jobId, (job) => {
        if (job.status === 'done') { void refresh(); setBusy(null); notify(`${id} installed — everything runs offline from now on.`); }
        if (job.status === 'error') { setBusy(null); notify(job.error || job.message); }
      });
    });
  }, [jobs, refresh, notify]);

  const grouped = ['LLM', 'ASR', 'Vision', 'TTS', 'Image'].map((kind) => ({ kind, items: models.filter((model) => model.kind === kind) })).filter((group) => group.items.length);

  return (
    <div className="stack">
      <Panel title="Local AI models" subtitle="Download once while online — after installation, every feature works fully offline" action={<button className="ghost-btn" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh status</button>}>
        <div className="hardware-bar">
          <Pill tone="green"><Cpu size={13} /> {caps.gpu?.cuda ? 'CUDA GPU detected' : caps.gpu?.metal ? 'Apple Metal available' : 'CPU / auto fallback'}</Pill>
          <Pill>{caps.ffmpeg ? 'FFmpeg ready' : 'FFmpeg missing'}</Pill>
          <Pill>{caps.fasterWhisper ? 'Whisper engine ready' : 'Whisper engine optional'}</Pill>
          <Pill>{caps.ultralytics ? 'YOLO engine ready' : 'YOLO engine optional'}</Pill>
          <Pill><Gauge size={13} /> {models.filter((model) => model.installed).length}/{models.length} installed</Pill>
        </div>
        <div className="model-groups">
          {grouped.map((group) => (
            <div key={group.kind} className="model-group">
              <h3><Boxes size={16} /> {group.kind}</h3>
              <div className="model-grid">
                {group.items.map((model) => (
                  <article className="model-card" key={model.id}>
                    <div className="model-head"><div><strong>{model.name}</strong><small>{model.provider} · {model.size}</small></div>{model.recommended && <Pill tone="violet"><Sparkles size={12} /> Recommended</Pill>}</div>
                    <p>{model.use}</p>
                    <div className="model-foot">
                      {model.installed ? <Pill tone="green"><CheckCircle2 size={13} /> Installed</Pill> : <Pill tone="muted">Not installed</Pill>}
                      <button className="chip-btn" disabled={model.installed || busy === model.id} onClick={() => install(model.id)}>
                        {busy === model.id ? <LoaderCircle size={14} className="spin" /> : <Download size={14} />} {model.installed ? 'Ready' : 'Install'}
                      </button>
                    </div>
                    {jobs[model.id] && <JobTracker jobId={jobs[model.id]} label="Installing model" />}
                  </article>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Offline setup order" subtitle="Recommended installation sequence for a smooth first run">
        <ol className="howto">
          <li><Package size={16} /><div><strong>1. Whisper Small (or Medium for Hindi)</strong><p>Word-level captions and transcript-driven moment detection.</p></div></li>
          <li><Sparkles size={16} /><div><strong>2. Gemma 2 7B (or Gemma 3 4B on smaller machines)</strong><p>Viral titles, hashtags and LLM reranking. Ollama must be running.</p></div></li>
          <li><Cpu size={16} /><div><strong>3. YOLO11 Nano / YOLOX Nano</strong><p>Player and gameplay activity tracking with ByteTrack IDs.</p></div></li>
          <li><Boxes size={16} /><div><strong>4. Optional: SDXL checkpoint for ComfyUI</strong><p>Fully offline image/sticker generation. Nano Banana only needs a cloud key when you choose it.</p></div></li>
        </ol>
      </Panel>
    </div>
  );
}

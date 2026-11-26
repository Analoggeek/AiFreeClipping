import { useCallback, useEffect, useState } from 'react';
import {
  Activity, CheckCircle2, Cpu, Download, ExternalLink, Gauge, HardDrive,
  KeyRound, LoaderCircle, Package, RefreshCw, Sparkles, Zap,
} from 'lucide-react';
import { api, pollJob } from '../api';
import { JobTracker, Panel, Pill } from '../components/common';
import type { Capabilities, HardwareInfo, ModelInfo } from '../types';

const GROUPS = ['LLM', 'ASR', 'Vision', 'TTS', 'Image', 'Cloud'];

export default function ModelsPage({ notify }: { notify: (message: string) => void }) {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [caps, setCaps] = useState<Capabilities>({});
  const [hardware, setHardware] = useState<HardwareInfo | null>(null);
  const [jobs, setJobs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [modelResult, capResult, hwResult] = await Promise.all([
        api.models(), api.capabilities(), api.hardware(),
      ]);
      setModels(modelResult.models);
      setCaps(capResult);
      setHardware(hwResult);
    } catch { /* offline */ }
  }, []);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => { void api.hardware().then(setHardware).catch(() => undefined); }, 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const openLink = (url?: string) => {
    if (!url) return;
    if (window.desktop?.openPath) void window.desktop.openPath(url);
    else window.open(url, '_blank', 'noopener,noreferrer');
  };

  const install = async (id: string) => {
    setBusy(id);
    try {
      const result = await api.installModel(id);
      setJobs((current) => ({ ...current, [id]: result.job_id }));
    } catch (error) { notify(String(error)); setBusy(null); }
  };

  useEffect(() => {
    Object.entries(jobs).forEach(([id, jobId]) => {
      pollJob(jobId, (job) => {
        if (job.status === 'done') {
          void refresh();
          setBusy(null);
          notify(`${models.find((model) => model.id === id)?.name || id} installed — ready to use offline.`);
        }
        if (job.status === 'error') { setBusy(null); notify(job.error || job.message); }
      });
    });
  }, [jobs, refresh, notify, models]);

  const grouped = GROUPS.map((kind) => ({
    kind, items: models.filter((model) => model.kind === kind),
  })).filter((group) => group.items.length);
  const installedCount = models.filter((model) => model.installed).length;

  return (
    <div className="stack">
      <Panel
        title="AI models & hardware"
        subtitle="One click downloads into your own folder. Cloud models link straight to their API key page."
        action={<button className="ghost-btn" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</button>}
      >
        <div className="hardware-bar">
          <Pill tone="green"><Cpu size={13} /> {hardware?.gpu?.name || (caps.gpu?.cuda ? 'CUDA GPU' : caps.gpu?.metal ? 'Apple Metal' : 'CPU fallback')}</Pill>
          <Pill><Activity size={13} /> CPU {hardware?.cpu_percent ?? '—'}%</Pill>
          <Pill><Gauge size={13} /> RAM {hardware?.ram_used_gb ?? '—'} / {hardware?.ram_total_gb ?? '—'} GB</Pill>
          <Pill><HardDrive size={13} /> Free {hardware?.disk_free_gb ?? '—'} GB</Pill>
          <Pill>{hardware?.workers ?? 1} parallel workers</Pill>
          <Pill tone="violet">{installedCount}/{models.length} ready</Pill>
        </div>
        <p className="hint">
          Rendering auto-selects {hardware?.gpu?.cuda ? 'NVENC' : hardware?.gpu?.metal ? 'VideoToolbox' : 'libx264'} and uses all {hardware?.cpu_count ?? 4} cores.
          Set <code>RENDER_WORKERS</code> to tune parallel exports.
        </p>
      </Panel>

      <div className="model-groups">
        {grouped.map((group) => {
          return (
            <Panel key={group.kind} title={`${group.kind} models`} subtitle={`${group.items.filter((item) => item.installed).length} of ${group.items.length} ready`}>
              <div className="model-grid">
                {group.items.map((model) => (
                  <article className={`model-card ${model.installed ? 'is-installed' : ''}`} key={model.id}>
                    <div className="model-head">
                      <div><strong>{model.name}</strong><small>{model.provider} · {model.size}</small></div>
                      {model.recommended && <Pill tone="violet"><Sparkles size={12} /> Recommended</Pill>}
                    </div>
                    <p>{model.use}</p>
                    {model.setupNote && <p className="model-note">{model.setupNote}</p>}
                    <div className="model-foot">
                      {model.installed
                        ? <Pill tone="green"><CheckCircle2 size={13} /> Ready</Pill>
                        : <Pill tone="muted">Not installed</Pill>}
                      {model.needsApi ? (
                        <button className="chip-btn accent" onClick={() => openLink(model.apiUrl || model.downloadUrl)}>
                          <KeyRound size={14} /> Get API key <ExternalLink size={12} />
                        </button>
                      ) : (
                        <>
                          {model.autoInstall && !model.installed && (
                            <button className="chip-btn primary" disabled={busy === model.id} onClick={() => install(model.id)}>
                              {busy === model.id ? <LoaderCircle size={14} className="spin" /> : <Download size={14} />} 1-click install
                            </button>
                          )}
                          {model.downloadUrl && (
                            <button className="chip-btn" onClick={() => openLink(model.downloadUrl)}>
                              <ExternalLink size={14} /> Download
                            </button>
                          )}
                        </>
                      )}
                      {model.providerUrl && <button className="chip-btn" onClick={() => openLink(model.providerUrl)}>Get runtime</button>}
                      {model.docsUrl && <button className="chip-btn ghost" onClick={() => openLink(model.docsUrl)}>Docs</button>}
                    </div>
                    {jobs[model.id] && <JobTracker jobId={jobs[model.id]} label="Installing model" />}
                  </article>
                ))}
              </div>
            </Panel>
          );
        })}
      </div>

      <Panel title="Recommended order" subtitle="Install these first for the fastest complete offline workflow">
        <ol className="howto">
          <li><Package size={16} /><div><strong>1. Whisper Small (Medium for Hindi)</strong><p>Word-level captions and transcript-driven moment detection.</p></div></li>
          <li><Zap size={16} /><div><strong>2. YOLOX Nano ONNX + ByteTrack</strong><p>Player/gameplay tracking inside the packaged app — no Torch needed.</p></div></li>
          <li><Sparkles size={16} /><div><strong>3. Gemma 2 7B via Ollama</strong><p>Viral titles and reranking. Install Ollama with the “Get runtime” button above.</p></div></li>
          <li><KeyRound size={16} /><div><strong>4. Optional cloud APIs</strong><p>Nano Banana, YouTube, Pexels and Pixabay links open their key pages directly.</p></div></li>
        </ol>
      </Panel>
    </div>
  );
}

import { useCallback, useEffect, useState } from 'react';
import {
  CheckCircle2, Cpu, Download, ExternalLink, FolderOpen, KeyRound, LoaderCircle, Package, RefreshCw, Sparkles, Zap,
} from 'lucide-react';
import { api, pollJob } from '../api';
import { JobTracker, Panel, Pill } from '../components/common';
import type { Capabilities, ModelInfo } from '../types';

const GROUPS = ['LLM', 'ASR', 'Vision', 'TTS', 'Image', 'Cloud'];

export default function ModelsPage({ notify }: { notify: (message: string) => void }) {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [caps, setCaps] = useState<Capabilities>({});
  const [jobs, setJobs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [recommendedJob, setRecommendedJob] = useState<string | null>(null);
  const [modelFolder, setModelFolder] = useState('');

  const refresh = useCallback(async () => {
    try {
      const [modelResult, capResult] = await Promise.all([
        api.models(), api.capabilities(),
      ]);
      setModels(modelResult.models);
      setCaps(capResult);
    } catch { /* offline */ }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    api.folders().then((result) => setModelFolder(result.folders?.models || '')).catch(() => undefined);
  }, []);

  const openLink = (url?: string) => {
    if (!url) return;
    if (window.desktop?.openExternal) void window.desktop.openExternal(url);
    else window.open(url, '_blank', 'noopener,noreferrer');
  };

  const install = async (id: string) => {
    setBusy(id);
    try {
      const result = await api.installModel(id);
      setJobs((current) => ({ ...current, [id]: result.job_id }));
    } catch (error) { notify(String(error)); setBusy(null); }
  };

  const installAll = async () => {
    try {
      const result = await api.installRecommendedModels();
      setRecommendedJob(result.job_id);
      notify('Downloading, installing, activating and saving the recommended models…');
    } catch (error) { notify(String(error)); }
  };

  useEffect(() => {
    if (!recommendedJob) return;
    return pollJob(recommendedJob, (job) => {
      if (job.status === 'done') { void refresh(); setRecommendedJob(null); notify('All recommended models are ready and saved.'); }
      if (job.status === 'error') { setRecommendedJob(null); notify(job.error || job.message); }
    });
  }, [recommendedJob, refresh, notify]);

  const autoSetup = async () => {
    try {
      const result = await api.autoSetupModels();
      if (!result.job_id) { notify(result.message || 'Offline setup was attempted recently; retry again later.'); return; }
      setRecommendedJob(result.job_id);
      notify('Detecting your hardware and downloading the complete offline model pack…');
    } catch (error) { notify(String(error)); }
  };

  const pickModelFolder = async () => {
    if (!window.desktop?.selectDirectory) { notify('Folder picker works in the desktop app.'); return; }
    const selected = await window.desktop.selectDirectory();
    if (!selected) return;
    try {
      await api.setFolder('models', selected);
      setModelFolder(selected);
      notify('Models will download into this folder.');
    } catch (error) { notify(String(error)); }
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
        subtitle="One click downloads, installs, activates and saves everything locally. Cloud models link straight to their API key page."
        action={
          <div className="panel-actions compact">
            <button className="ghost-btn" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</button>
            <button className="chip-btn" onClick={() => void pickModelFolder()}><FolderOpen size={14} /> Model folder</button>
            <button className="chip-btn" disabled={Boolean(recommendedJob)} onClick={() => void autoSetup()}><Cpu size={14} /> Auto setup</button>
            <button className="primary" disabled={Boolean(recommendedJob)} onClick={() => void installAll()}>
              {recommendedJob ? <LoaderCircle size={15} className="spin" /> : <Zap size={15} />} Install all
            </button>
          </div>
        }
      >
        <div className="hardware-bar">
          <Pill tone="green">{caps.gpu?.cuda ? 'CUDA GPU detected' : caps.gpu?.metal ? 'Apple Metal available' : 'CPU fallback'}</Pill>
          <Pill tone="violet">{installedCount}/{models.length} models ready</Pill>
          {modelFolder && <Pill tone="muted">{modelFolder}</Pill>}
        </div>
        {recommendedJob && <JobTracker jobId={recommendedJob} label="Automatic model setup" />}
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
                              {busy === model.id ? <LoaderCircle size={14} className="spin" /> : <Download size={14} />} Download &amp; install
                            </button>
                          )}
                          {model.downloadUrl && (
                            <button className="chip-btn" title="Open the official download page" onClick={() => openLink(model.downloadUrl)}>
                              <ExternalLink size={14} /> {model.autoInstall ? 'Open page' : 'Download'}
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
          <li><Sparkles size={16} /><div><strong>3. Gemma 2 7B via Ollama</strong><p>Viral titles and reranking. The runtime is downloaded and started automatically — no manual setup.</p></div></li>
          <li><KeyRound size={16} /><div><strong>4. Optional cloud APIs</strong><p>Nano Banana, YouTube, Pexels and Pixabay links open their key pages directly.</p></div></li>
        </ol>
      </Panel>
    </div>
  );
}

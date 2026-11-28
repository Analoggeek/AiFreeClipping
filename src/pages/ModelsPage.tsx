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
  const [checkpointFolder, setCheckpointFolder] = useState('');
  const [checkpointPath, setCheckpointPath] = useState('');
  const [checkpointBusy, setCheckpointBusy] = useState(false);

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
    api.settings().then((result) => {
      setCheckpointFolder(result.values?.comfy_checkpoint_folder || '');
      setCheckpointPath(result.values?.comfy_checkpoint_path || '');
    }).catch(() => undefined);
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

  const installRecommended = async () => {
    try {
      const result = await api.installRecommendedModels();
      setRecommendedJob(result.job_id);
      notify('Downloading, installing, activating and saving the models recommended for this hardware…');
    } catch (error) { notify(String(error)); }
  };

  useEffect(() => {
    if (!recommendedJob) return;
    return pollJob(recommendedJob, (job) => {
      if (job.status === 'done') { void refresh(); setRecommendedJob(null); notify('All recommended models are ready and saved.'); }
      if (job.status === 'error') { setRecommendedJob(null); notify(job.error || job.message); }
      if (job.status === 'cancelled') { setRecommendedJob(null); notify('Recommended model setup cancelled.'); }
    });
  }, [recommendedJob, refresh, notify]);

  const autoSetup = async () => {
    try {
      const result = await api.autoSetupModels();
      if (!result.job_id) { notify(result.message || 'Offline setup was attempted recently; retry again later.'); return; }
      setRecommendedJob(result.job_id);
      notify('Detecting your hardware and installing the recommended offline model set…');
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

  const pickCheckpointFolder = async () => {
    if (!window.desktop?.selectDirectory) { notify('Choose the ComfyUI models/checkpoints folder in the desktop app.'); return; }
    const selected = await window.desktop.selectDirectory();
    if (!selected) return;
    try {
      await api.saveSettings({ comfy_checkpoint_folder: selected });
      setCheckpointFolder(selected);
      if (checkpointPath) {
        const result = await api.selectComfyCheckpoint(checkpointPath);
        setCheckpointPath(result.checkpoint.path);
        notify('ComfyUI folder saved and the selected checkpoint registered there.');
      } else {
        notify('ComfyUI checkpoint folder saved. Select an existing checkpoint file next.');
      }
      await refresh();
    } catch (error) { notify(String(error)); }
  };

  const selectCheckpoint = async () => {
    if (!window.desktop?.selectFiles) { notify('Checkpoint file picker works in the desktop app.'); return; }
    const paths = await window.desktop.selectFiles([{ name: 'SDXL checkpoint', extensions: ['safetensors', 'ckpt'] }]);
    if (!paths.length) return;
    setCheckpointBusy(true);
    try {
      const result = await api.selectComfyCheckpoint(paths[0]);
      setCheckpointPath(result.checkpoint.path);
      await refresh();
      notify(`SDXL checkpoint ready: ${result.checkpoint.filename}`);
    } catch (error) { notify(String(error)); }
    finally { setCheckpointBusy(false); }
  };

  useEffect(() => {
    const stops = Object.entries(jobs).map(([id, jobId]) => pollJob(jobId, (job) => {
      const forget = () => setJobs((current) => {
        if (current[id] !== jobId) return current;
        const next = { ...current };
        delete next[id];
        return next;
      });
      if (job.status === 'done') {
        void refresh();
        setBusy(null);
        forget();
        notify(`${models.find((model) => model.id === id)?.name || id} installed — ready to use offline.`);
      }
      if (job.status === 'error') { setBusy(null); forget(); notify(job.error || job.message); }
      if (job.status === 'cancelled') { setBusy(null); forget(); notify('Model installation cancelled.'); }
    }));
    return () => stops.forEach((stop) => stop());
  }, [jobs, refresh, notify, models]);

  const grouped = GROUPS.map((kind) => ({
    kind, items: models.filter((model) => model.kind === kind),
  })).filter((group) => group.items.length);
  const installedCount = models.filter((model) => model.installed).length;
  const recommendedCount = models.filter((model) => model.recommended && model.autoInstall).length;

  return (
    <div className="stack">
      <Panel
        title="AI models & hardware"
        subtitle="One click installs a balanced model set picked for your memory and GPU. Cloud models link straight to their API key page."
        action={
          <div className="panel-actions compact">
            <button className="ghost-btn" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</button>
            <button className="chip-btn" onClick={() => void pickModelFolder()}><FolderOpen size={14} /> Model folder</button>
            <button className="chip-btn" disabled={Boolean(recommendedJob)} onClick={() => void autoSetup()}><Cpu size={14} /> Auto setup</button>
            <button className="primary" disabled={Boolean(recommendedJob)} onClick={() => void installRecommended()}>
              {recommendedJob ? <LoaderCircle size={15} className="spin" /> : <Zap size={15} />} Install recommended
            </button>
          </div>
        }
      >
        <div className="hardware-bar">
          <Pill tone="green">{caps.gpu?.cuda ? 'CUDA GPU detected' : caps.gpu?.metal ? 'Apple Metal available' : 'CPU fallback'}</Pill>
          <Pill tone="violet">{installedCount}/{models.length} models ready</Pill>
          <Pill tone="amber">{recommendedCount} local models matched to this hardware</Pill>
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
                    {model.recommended && model.recommendedReason && <p className="model-recommendation"><Sparkles size={12} /> {model.recommendedReason}</p>}
                    {model.setupNote && <p className="model-note">{model.setupNote}</p>}
                    {model.id === 'sdxl-1.0' && checkpointPath && <p className="model-checkpoint-path" title={checkpointPath}>Selected SDXL checkpoint: {checkpointPath}</p>}
                    {model.id === 'sdxl-1.0' && checkpointFolder && <p className="model-checkpoint-path" title={checkpointFolder}>ComfyUI checkpoints folder: {checkpointFolder}</p>}
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
                          {model.id === 'sdxl-1.0' && !model.installed && (
                            <button className="chip-btn primary" disabled={busy === model.id} onClick={() => install(model.id)}>
                              {busy === model.id ? <LoaderCircle size={14} className="spin" /> : <Download size={14} />} Download &amp; install SDXL
                            </button>
                          )}
                          {model.id === 'sdxl-1.0' && <>
                            <button className="chip-btn" onClick={() => void pickCheckpointFolder()} title="Select ComfyUI/models/checkpoints"><FolderOpen size={14} /> Set checkpoints folder</button>
                            <button className="chip-btn" disabled={checkpointBusy} onClick={() => void selectCheckpoint()}>{checkpointBusy ? <LoaderCircle size={14} className="spin" /> : <FolderOpen size={14} />} {checkpointBusy ? 'Registering checkpoint…' : 'Select downloaded file'}</button>
                          </>}
                          {model.downloadUrl && (
                            <button className="chip-btn" title="Open the official download page" onClick={() => openLink(model.downloadUrl)}>
                              <ExternalLink size={14} /> {model.autoInstall ? 'Open page' : 'Official download'}
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

      <Panel title="Hardware-matched setup" subtitle="The recommended set adjusts to available memory and GPU acceleration">
        <ol className="howto">
          <li><Package size={16} /><div><strong>1. Whisper Small or Medium</strong><p>Small is lighter on low-memory machines; Medium is recommended from 16 GB RAM for improved multilingual accuracy.</p></div></li>
          <li><Zap size={16} /><div><strong>2. YOLOX Nano ONNX + ByteTrack</strong><p>A compact 4 MB detector for player/gameplay tracking, including inside packaged builds.</p></div></li>
          <li><Sparkles size={16} /><div><strong>3. Gemma sized for your system</strong><p>Choose a compact 4B model for entry hardware, 7B for balanced acceleration, or 12B on high-memory GPUs and Apple Silicon.</p></div></li>
          <li><KeyRound size={16} /><div><strong>4. Optional image and cloud services</strong><p>SDXL, Nano Banana, Pexels and Pixabay stay optional so setup avoids large downloads you may not need.</p></div></li>
        </ol>
      </Panel>
    </div>
  );
}

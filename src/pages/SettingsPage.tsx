import { useEffect, useState } from 'react';
import { Cpu, ExternalLink, FolderOpen, HardDrive, KeyRound, ShieldCheck, Sparkles, Youtube } from 'lucide-react';
import { api } from '../api';
import { Panel } from '../components/common';
import logo from '../../brand/logo.svg';

const FIELDS = [
  { key: 'gemini_api_key', label: 'Gemini API key (Nano Banana)', icon: KeyRound, placeholder: 'Optional — leave empty for fully local SDXL', secret: true },
  { key: 'pexels_api_key', label: 'Pexels API key', icon: KeyRound, placeholder: 'Free key from pexels.com/api' },
  { key: 'pixabay_api_key', label: 'Pixabay API key', icon: KeyRound, placeholder: 'Free key from pixabay.com/api/docs' },
  { key: 'youtube_client_secret', label: 'YouTube OAuth client_secret.json path', icon: Youtube, placeholder: '~/.AiFreeClipping/client_secret.json' },
  { key: 'ollama_model', label: 'Ollama model', icon: Cpu, placeholder: 'gemma2:7b' },
  { key: 'whisper_model', label: 'Whisper model', icon: Sparkles, placeholder: 'small / medium / large-v3' },
  { key: 'comfy_checkpoint', label: 'ComfyUI SDXL checkpoint', icon: HardDrive, placeholder: 'sd_xl_base_1.0.safetensors' },
];

export default function SettingsPage({ notify }: { notify: (message: string) => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [folders, setFolders] = useState<Record<string, string>>({});

  useEffect(() => {
    api.settings().then((result) => setValues(result.values)).catch(() => undefined);
    api.folders().then((result) => setFolders(result.folders)).catch(() => undefined);
  }, []);

  const save = async () => {
    try { await api.saveSettings(values); notify('Settings saved.'); }
    catch (error) { notify(String(error)); }
  };

  return (
    <div className="stack">
      <Panel title="Settings" subtitle="Keys are stored only in your local SQLite database — never sent anywhere except the provider you choose" action={<button className="primary" onClick={save}>Save settings</button>}>
        <div className="form-grid two">
          {FIELDS.map((field) => {
            const Icon = field.icon;
            return (
              <label className="field" key={field.key}>
                <span>{field.label}</span>
                <div className="input-row"><Icon size={15} /><input type={field.secret ? 'password' : 'text'} value={values[field.key] || ''} placeholder={field.placeholder} onChange={(event) => setValues({ ...values, [field.key]: event.target.value })} /></div>
              </label>
            );
          })}
        </div>
      </Panel>

      <Panel title="Local folders" subtitle="All media, projects and models live on this machine">
        <div className="folder-grid">
          {Object.entries(folders).map(([key, value]) => (
            <div className="folder-card" key={key}>
              <FolderOpen size={17} /><div><strong>{key}</strong><small>{value}</small></div>
              <button className="chip-btn" onClick={() => window.desktop?.openPath(value)}>Open</button>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Privacy & runtime" subtitle="Managed automatically in the sidebar hardware panel">
        <div className="notice"><ShieldCheck size={18} /><div><strong>Privacy by design</strong><p>The local API binds to 127.0.0.1 and requires a token generated on each launch. Cloud features (Nano Banana, stock search, YouTube upload) are opt-in and only run when you supply your own key. Live CPU, RAM, disk and GPU usage is shown in the sidebar.</p></div></div>
      </Panel>

      <Panel title="About" subtitle="Built for creators who want speed without leaving their machine">
        <div className="about">
          <img src={logo} alt="AI Clipper Pro logo" />
          <div>
            <h3>AI Clipper Pro</h3>
            <p>A local-first AI video clipping and editing studio. Download, discover viral moments, polish and publish — with Gemma, Whisper, YOLOX + ByteTrack, FFmpeg and optional Nano Banana / ComfyUI.</p>
            <a className="chip-btn" href="https://github.com/Analoggeek/AiFreeClipping" target="_blank" rel="noreferrer"><ExternalLink size={14} /> Source & documentation</a>
          </div>
        </div>
      </Panel>
    </div>
  );
}

import { useEffect, useState } from 'react';
import { Cpu, ExternalLink, FolderOpen, HardDrive, ImagePlus, KeyRound, ShieldCheck, Sparkles, Trash2, Volume2, Youtube } from 'lucide-react';
import { api } from '../api';
import type { AutoEditOptions } from '../types';
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

const AUTO_EDIT_DEFAULTS: AutoEditOptions = {
  style: 'hype', aspect: '9:16', resolution: 'source',
  captions: true, sound_effects: true, stickers: true, blur_background: true,
  music: '', music_volume: 0.18,
};

export default function SettingsPage({ notify }: { notify: (message: string) => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [folders, setFolders] = useState<Record<string, string>>({});
  const [autoEdit, setAutoEdit] = useState<AutoEditOptions>(AUTO_EDIT_DEFAULTS);

  useEffect(() => {
    api.settings().then((result) => {
      const saved = result.values || {};
      setValues(saved);
      const numericVolume = Number(saved.auto_edit_music_volume ?? AUTO_EDIT_DEFAULTS.music_volume);
      setAutoEdit({
        style: ['hype', 'minimal', 'premium'].includes(saved.auto_edit_style) ? saved.auto_edit_style as AutoEditOptions['style'] : AUTO_EDIT_DEFAULTS.style,
        aspect: ['9:16', '1:1', '16:9'].includes(saved.auto_edit_aspect) ? saved.auto_edit_aspect as AutoEditOptions['aspect'] : AUTO_EDIT_DEFAULTS.aspect,
        resolution: ['source', '720p', '1080p'].includes(saved.auto_edit_resolution) ? saved.auto_edit_resolution as AutoEditOptions['resolution'] : AUTO_EDIT_DEFAULTS.resolution,
        captions: saved.auto_edit_captions === undefined ? true : !['0', 'false'].includes(saved.auto_edit_captions.toLowerCase()),
        sound_effects: saved.auto_edit_sound_effects === undefined ? true : !['0', 'false'].includes(saved.auto_edit_sound_effects.toLowerCase()),
        stickers: saved.auto_edit_stickers === undefined ? true : !['0', 'false'].includes(saved.auto_edit_stickers.toLowerCase()),
        blur_background: saved.auto_edit_blur_background === undefined ? true : !['0', 'false'].includes(saved.auto_edit_blur_background.toLowerCase()),
        music: saved.auto_edit_music || '',
        music_volume: Number.isFinite(numericVolume) ? Math.max(0, Math.min(1, numericVolume)) : AUTO_EDIT_DEFAULTS.music_volume,
      });
    }).catch(() => undefined);
    api.folders().then((result) => setFolders(result.folders)).catch(() => undefined);
  }, []);

  const save = async () => {
    try {
      const result = await api.saveSettings({
        ...values,
        auto_edit_style: autoEdit.style,
        auto_edit_aspect: autoEdit.aspect,
        auto_edit_resolution: autoEdit.resolution,
        auto_edit_captions: String(autoEdit.captions),
        auto_edit_sound_effects: String(autoEdit.sound_effects),
        auto_edit_stickers: String(autoEdit.stickers),
        auto_edit_blur_background: String(autoEdit.blur_background),
        auto_edit_music: autoEdit.music || '',
        auto_edit_music_volume: String(autoEdit.music_volume),
      });
      setValues(result.values);
      notify('Settings saved.');
    } catch (error) { notify(String(error)); }
  };

  const chooseWatermark = async () => {
    if (!window.desktop?.selectFiles) { notify('Choose a watermark image in the desktop app.'); return; }
    const paths = await window.desktop.selectFiles([{ name: 'Channel logo', extensions: ['png', 'jpg', 'jpeg', 'webp'] }]);
    if (!paths.length) return;
    setValues((current) => ({ ...current, watermark_path: paths[0] }));
    notify('Logo selected. Save settings to use it on new exports.');
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
        <div className="watermark-settings">
          <div className="watermark-settings-copy">
            <strong>Optional channel watermark</strong>
            <small>No logo is added by default. Choose a transparent PNG or another image to brand future clip, batch and timeline exports.</small>
          </div>
          <div className="watermark-settings-controls">
            <div className="input-row watermark-path" title={values.watermark_path || 'No watermark selected'}>
              <ImagePlus size={15} />
              <input readOnly value={values.watermark_path || ''} placeholder="No watermark — exports stay unbranded" aria-label="Selected watermark image path" />
            </div>
            <button className="chip-btn" onClick={() => void chooseWatermark()}><ImagePlus size={14} /> Choose logo</button>
            <button className="chip-btn" disabled={!values.watermark_path} onClick={() => setValues((current) => ({ ...current, watermark_path: '' }))}><Trash2 size={14} /> Remove</button>
          </div>
        </div>
      </Panel>

      <Panel title="Auto Edit" subtitle="These saved preferences control the Auto Edit button in the Video Editor">
        <div className="form-grid four">
          <label className="field"><span>Editing style</span>
            <select value={autoEdit.style} onChange={(event) => setAutoEdit((current) => ({ ...current, style: event.target.value as AutoEditOptions['style'] }))}>
              <option value="hype">High energy</option><option value="minimal">Minimal</option><option value="premium">Premium</option>
            </select>
          </label>
          <label className="field"><span>Output format</span>
            <select value={autoEdit.aspect} onChange={(event) => setAutoEdit((current) => ({ ...current, aspect: event.target.value as AutoEditOptions['aspect'] }))}>
              <option value="9:16">Vertical · 9:16</option><option value="1:1">Square · 1:1</option><option value="16:9">Landscape · 16:9</option>
            </select>
          </label>
          <label className="field"><span>Export quality</span>
            <select value={autoEdit.resolution} onChange={(event) => setAutoEdit((current) => ({ ...current, resolution: event.target.value as AutoEditOptions['resolution'] }))}>
              <option value="source">Source quality</option><option value="1080p">1080p</option><option value="720p">720p</option>
            </select>
          </label>
          <label className="field"><span>Music file (optional)</span>
            <input value={autoEdit.music || ''} onChange={(event) => setAutoEdit((current) => ({ ...current, music: event.target.value }))} placeholder="/path/to/music.mp3" />
          </label>
          <label className="field"><span>Music volume · {Math.round(autoEdit.music_volume * 100)}%</span>
            <input type="range" min="0" max="1" step="0.05" value={autoEdit.music_volume} onChange={(event) => setAutoEdit((current) => ({ ...current, music_volume: Number(event.target.value) }))} />
          </label>
        </div>
        <div className="toggle-grid">
          <label className="toggle"><input type="checkbox" checked={autoEdit.captions} onChange={(event) => setAutoEdit((current) => ({ ...current, captions: event.target.checked }))} /><span><Sparkles size={16} /></span>Generate captions</label>
          <label className="toggle"><input type="checkbox" checked={autoEdit.sound_effects} onChange={(event) => setAutoEdit((current) => ({ ...current, sound_effects: event.target.checked }))} /><span><Volume2 size={16} /></span>Add sound effects</label>
          <label className="toggle"><input type="checkbox" checked={autoEdit.stickers} onChange={(event) => setAutoEdit((current) => ({ ...current, stickers: event.target.checked }))} /><span><ImagePlus size={16} /></span>Use saved stickers</label>
          <label className="toggle"><input type="checkbox" checked={autoEdit.blur_background} onChange={(event) => setAutoEdit((current) => ({ ...current, blur_background: event.target.checked }))} /><span><HardDrive size={16} /></span>Blur-fill unused frame</label>
        </div>
        <p className="hint">Click Save settings to keep these choices. Auto Edit will build editable video, caption, sticker, and audio tracks in the timeline as well as render each finished clip.</p>
      </Panel>

      <Panel title="Local folders" subtitle="All media, projects and models live on this machine">
        <div className="folder-grid">
          {Object.entries(folders || {}).map(([key, value]) => (
            <div className="folder-card" key={key}>
              <FolderOpen size={17} /><div><strong>{key}</strong><small>{value}</small></div>
              <button className="chip-btn" onClick={() => window.desktop?.openPath(value)}>Open</button>
              <button
                className="chip-btn"
                onClick={async () => {
                  if (!window.desktop?.selectDirectory) { notify('Folder picker works in the desktop app.'); return; }
                  const selected = await window.desktop.selectDirectory();
                  if (!selected) return;
                  try { await api.setFolder(key, selected); setFolders((await api.folders()).folders); notify(`${key} folder saved.`); }
                  catch (error) { notify(String(error)); }
                }}
              >Change</button>
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

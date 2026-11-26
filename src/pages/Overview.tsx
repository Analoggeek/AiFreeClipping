import { useEffect, useState } from 'react';
import {
  Activity, ArrowRight, Captions, Clapperboard, Cpu, Download, Film, FolderDown, Gauge,
  HardDrive, ImagePlus, Layers3, ListVideo, Mic2, ScanEye, Sparkles, UploadCloud, Zap,
} from 'lucide-react';
import { api } from '../api';
import { Panel, Pill } from '../components/common';
import logo from '../../brand/logo-3d.png';
import type { PageId } from '../App';
import type { HardwareInfo } from '../types';

const PIPELINE = [
  { icon: Download, title: 'Download', detail: 'Any video or full playlist, max available quality', page: 'downloads' as PageId },
  { icon: ScanEye, title: 'Understand', detail: 'Whisper words + YOLOX/ByteTrack activity, scored locally', page: 'clipper' as PageId },
  { icon: Clapperboard, title: 'Clip', detail: 'Multiple viral moments from one or many videos', page: 'clipper' as PageId },
  { icon: Layers3, title: 'Edit', detail: 'Timeline, captions, stickers, SFX, stock & AI art', page: 'editor' as PageId },
  { icon: UploadCloud, title: 'Publish', detail: 'One-click high-quality export and YouTube upload', page: 'publish' as PageId },
];

const FEATURES = [
  { icon: Captions, title: 'Word-timed captions', text: 'Whisper caption tracks with hype, karaoke, minimal and premium presets.' },
  { icon: Mic2, title: 'Sound design', text: 'Procedural whooshes, risers, pops and impacts — royalty-free and offline.' },
  { icon: ImagePlus, title: 'Nano Banana / SDXL', text: 'Generate stickers on the spot with a cloud key or fully local ComfyUI.' },
  { icon: Film, title: 'Region lock', text: 'Mark only the player or gameplay area so the AI scores what matters.' },
  { icon: FolderDown, title: 'Local library', text: 'Everything lives in your own folder. No telemetry, no cloud dependency.' },
  { icon: ListVideo, title: 'Batch exports', text: 'Render every selected clip in one pass at 1080p, ready for Shorts.' },
];

export default function Overview({ onNavigate, openClipper }: { onNavigate: (page: PageId) => void; openClipper: (ids: string[]) => void }) {
  const [stats, setStats] = useState({ media: 0, clips: 0, rendered: 0, running: 0 });
  const [hardware, setHardware] = useState<HardwareInfo | null>(null);
  useEffect(() => {
    Promise.all([api.media(), api.clips(), api.jobs()]).then(([media, clips, jobs]) => {
      setStats({
        media: media.media.length,
        clips: clips.clips.length,
        rendered: clips.clips.filter((clip) => clip.output).length,
        running: jobs.jobs.filter((job) => job.status === 'running').length,
      });
    }).catch(() => undefined);
    const load = () => api.hardware().then(setHardware).catch(() => undefined);
    void load();
    const timer = window.setInterval(load, 4000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="stack">
      <section className="hero">
        <div>
          <Pill tone="violet"><Sparkles size={13} /> 100% LOCAL AI STUDIO</Pill>
          <h1>Turn any video into<br /><span>viral-ready clips.</span></h1>
          <p>Paste a link, let your local AI find the engaging moments, polish them in a full editor, and publish — all on your own hardware.</p>
          <div className="hero-actions">
            <button className="primary" onClick={() => onNavigate('downloads')}>Start with a link <ArrowRight size={17} /></button>
            <button className="ghost-btn" onClick={() => openClipper([])}>Open AI Clipper</button>
          </div>
        </div>
        <div className="hero-art">
          <img src={logo} alt="AI Clipper Pro" />
          <div className="hero-chip chip-a">Gemma 2 7B</div>
          <div className="hero-chip chip-b">Whisper</div>
          <div className="hero-chip chip-c">YOLOX + ByteTrack</div>
        </div>
      </section>

      <div className="stat-grid">
        {[
          { label: 'Videos in library', value: stats.media, icon: Film },
          { label: 'AI clip candidates', value: stats.clips, icon: Clapperboard },
          { label: 'Rendered exports', value: stats.rendered, icon: FolderDown },
          { label: 'Active jobs', value: stats.running, icon: Sparkles },
        ].map((item) => {
          const Icon = item.icon;
          return <div className="stat-card" key={item.label}><Icon size={20} /><strong>{item.value}</strong><span>{item.label}</span></div>;
        })}
      </div>

      <Panel title="Hardware engine" subtitle="Live usage and the encoder chosen for this machine" action={<button className="ghost-btn" onClick={() => onNavigate('models')}><Cpu size={15} /> Model setup</button>}>
        <div className="hardware-bar">
          <Pill tone="green"><Zap size={13} /> {hardware?.gpu?.name || 'Detecting GPU…'}</Pill>
          <Pill><Activity size={13} /> CPU {hardware?.cpu_percent ?? '—'}%</Pill>
          <Pill><Gauge size={13} /> RAM {hardware?.ram_percent ?? '—'}%</Pill>
          <Pill><HardDrive size={13} /> {hardware?.disk_free_gb ?? '—'} GB free</Pill>
          <Pill tone="violet">{hardware?.workers ?? 1} parallel renders</Pill>
        </div>
        <div className="hardware-meters">
          <div><span>CPU</span><div className="meter"><i style={{ width: `${hardware?.cpu_percent ?? 0}%` }} /></div></div>
          <div><span>RAM</span><div className="meter"><i style={{ width: `${hardware?.ram_percent ?? 0}%` }} /></div></div>
          <div><span>Render workers</span><div className="meter"><i style={{ width: `${Math.min(100, (hardware?.workers ?? 1) / 8 * 100)}%` }} /></div></div>
        </div>
      </Panel>

      <Panel title="Your creation pipeline" subtitle="Every stage is connected — one workflow from source link to published Short">
        <div className="pipeline">
          {PIPELINE.map((step, index) => {
            const Icon = step.icon;
            return (
              <button className="pipeline-step" key={step.title} onClick={() => onNavigate(step.page)}>
                <span className="step-no">0{index + 1}</span>
                <span className="step-icon"><Icon size={22} /></span>
                <strong>{step.title}</strong>
                <p>{step.detail}</p>
                <ArrowRight size={16} className="step-arrow" />
              </button>
            );
          })}
        </div>
      </Panel>

      <Panel title="Everything you need to go viral" subtitle="Bundled, local and stitched together">
        <div className="feature-grid">
          {FEATURES.map((item) => {
            const Icon = item.icon;
            return <div className="feature-card" key={item.title}><span><Icon size={20} /></span><div><strong>{item.title}</strong><p>{item.text}</p></div></div>;
          })}
        </div>
      </Panel>
    </div>
  );
}

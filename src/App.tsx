import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import {
  Clapperboard, CloudDownload, Download, FolderOpen, LayoutDashboard, Library,
  ListVideo, LoaderCircle, Moon, MonitorPlay, Package, PlugZap, Settings, Sparkles, Sun, UploadCloud, WifiOff,
} from 'lucide-react';
import logo from '../brand/logo-mark-3d.svg';
import { api, apiBase } from './api';
import type { HardwareInfo } from './types';
import { JobProgressList, Toast, useJobs } from './components/common';
import ErrorBoundary from './components/ErrorBoundary';
// Route-level splitting keeps the first paint fast while the engine starts.
const Clipper = lazy(() => import('./pages/Clipper'));
const Downloads = lazy(() => import('./pages/Downloads'));
const Editor = lazy(() => import('./pages/Editor'));
const ModelsPage = lazy(() => import('./pages/ModelsPage'));
const Overview = lazy(() => import('./pages/Overview'));
const Playlists = lazy(() => import('./pages/Playlists'));
const Publish = lazy(() => import('./pages/Publish'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));

export type PageId = 'overview' | 'downloads' | 'playlists' | 'clipper' | 'editor' | 'publish' | 'models' | 'settings';

const NAV: Array<{ id: PageId; label: string; icon: typeof LayoutDashboard; group: string }> = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, group: 'Workspace' },
  { id: 'downloads', label: 'Downloader', icon: Download, group: 'Workspace' },
  { id: 'playlists', label: 'Playlists', icon: ListVideo, group: 'Workspace' },
  { id: 'clipper', label: 'AI Clipper', icon: Clapperboard, group: 'Create' },
  { id: 'editor', label: 'Video Editor', icon: MonitorPlay, group: 'Create' },
  { id: 'publish', label: 'Publish', icon: UploadCloud, group: 'Create' },
  { id: 'models', label: 'Local Models', icon: Package, group: 'System' },
  { id: 'settings', label: 'Settings', icon: Settings, group: 'System' },
];

export default function App() {
  const [page, setPage] = useState<PageId>('overview');
  const [toast, setToast] = useState('');
  const [online, setOnline] = useState(false);
  const [theme, setTheme] = useState<'dark' | 'light'>(() => localStorage.getItem('aifreeclip.theme') === 'light' ? 'light' : 'dark');
  const [version, setVersion] = useState('5.2.3');
  const [mediaSelection, setMediaSelection] = useState<string[]>([]);
  const [clipSelection, setClipSelection] = useState<string[]>([]);
  const [folder, setFolder] = useState('');
  const [hardware, setHardware] = useState<HardwareInfo | null>(null);
  const autoSetupStarted = useRef(false);
  const { jobs } = useJobs();
  const notify = useCallback((message: string) => setToast(message), []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('aifreeclip.theme', theme);
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'light' ? '#f4f6fb' : '#090b14');
  }, [theme]);

  useEffect(() => {
    api.health().then((result) => { setOnline(true); setVersion(result.version); }).catch(() => setOnline(false));
    api.folders().then((result) => setFolder(result.folders.exports)).catch(() => undefined);
    if (window.desktop?.appInfo) {
      void window.desktop.appInfo().then((info) => { if (info?.version) setVersion(info.version); }).catch(() => undefined);
    }
    const loadHardware = () => { void api.hardware().then(setHardware).catch(() => undefined); };
    loadHardware();
    const timer = window.setInterval(loadHardware, 4000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!online || autoSetupStarted.current) return;
    autoSetupStarted.current = true;
    void api.settings().then((result) => {
      if (result.values?.auto_setup_complete === '1') return;
      void api.autoSetupModels()
        .then((result) => {
          if (result.job_id) notify('Hardware detected — installing the recommended offline models in the background.');
        })
        .catch(() => undefined);
    }).catch(() => undefined);
  }, [online, notify]);

  const openClipper = (ids: string[]) => {
    setMediaSelection(ids);
    setPage('clipper');
  };
  const openEditor = (clipId?: string) => {
    if (clipId) setClipSelection([clipId]);
    setPage('editor');
  };
  const openPublish = (ids: string[]) => {
    setClipSelection(ids);
    setPage('publish');
  };
  const common = { notify, openClipper, openEditor, openPublish };
  const activeJobs = jobs.filter((job) => job.status === 'running' || job.status === 'queued').length;

  let content: React.ReactNode;
  switch (page) {
    case 'downloads': content = <Downloads {...common} />; break;
    case 'playlists': content = <Playlists {...common} />; break;
    case 'clipper': content = <Clipper {...common} mediaSelection={mediaSelection} setMediaSelection={setMediaSelection} />; break;
    case 'editor': content = <Editor {...common} clipSelection={clipSelection} setMediaSelection={setMediaSelection} />; break;
    case 'publish': content = <Publish {...common} clipSelection={clipSelection} setClipSelection={setClipSelection} />; break;
    case 'models': content = <ModelsPage notify={notify} />; break;
    case 'settings': content = <SettingsPage notify={notify} />; break;
    default: content = <Overview onNavigate={setPage} openClipper={openClipper} />;
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => setPage('overview')}>
          <img src={logo} alt="AI Clipper Pro" />
          <small>MADE BY ANALOGGEEK</small>
        </button>
        <nav>
          {['Workspace', 'Create', 'System'].map((group) => (
            <div className="nav-group" key={group}>
              <span className="nav-label">{group}</span>
              {NAV.filter((item) => item.group === group).map((item) => {
                const Icon = item.icon;
                return (
                  <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`} onClick={() => setPage(item.id)}>
                    <Icon size={18} /><span>{item.label}</span>
                    {item.id === 'publish' && activeJobs > 0 && <em>{activeJobs}</em>}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
        <JobProgressList jobs={jobs} />
        <div className="sidebar-hardware">
          <span className="nav-label">Hardware</span>
          <strong>{hardware?.gpu?.name || 'Detecting…'}</strong>
          <div className="mini-meter"><i style={{ width: `${hardware?.cpu_percent ?? 0}%` }} /><small>CPU {hardware?.cpu_percent ?? '—'}%</small></div>
          <div className="mini-meter"><i style={{ width: `${hardware?.ram_percent ?? 0}%` }} /><small>RAM {hardware?.ram_percent ?? '—'}%</small></div>
          <small className="hardware-foot">{hardware?.workers ?? 1} workers · {hardware?.disk_free_gb ?? '—'} GB free</small>
          <small className="hardware-foot">App data: {hardware?.app_usage_gb ?? '—'} GB used</small>
        </div>
        <div className="sidebar-foot">
          <PlugZap size={15} className={online ? 'ok' : 'bad'} />
          <div><strong>{online ? 'Local engine online' : 'Engine offline'}</strong><small>v{version} · {apiBase || 'browser mode'}</small></div>
        </div>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <div className="crumb"><Library size={16} /><span>AI Clipper Pro</span><b>/</b><strong>{NAV.find((item) => item.id === page)?.label}</strong></div>
          <div className="topbar-actions">
            {!online && <span className="offline"><WifiOff size={14} /> Start the local engine</span>}
            <button
              className="theme-toggle"
              onClick={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')}
              title={`Switch to ${theme === 'dark' ? 'day' : 'night'} theme`}
              aria-label={`Switch to ${theme === 'dark' ? 'day' : 'night'} theme`}
            >{theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}<span>{theme === 'dark' ? 'Day' : 'Night'}</span></button>
            <button className="ghost-btn" onClick={() => folder && window.desktop?.revealPath(folder)} title="Open exports folder">
              <FolderOpen size={16} /> Exports
            </button>
            <button className="ghost-btn" onClick={() => window.desktop?.openExternal ? void window.desktop.openExternal('https://github.com/Analoggeek/AiFreeClipping') : window.open('https://github.com/Analoggeek/AiFreeClipping', '_blank')}>
              <CloudDownload size={16} /> GitHub
            </button>
            <div className="avatar"><Sparkles size={16} /></div>
          </div>
        </header>
        <main className="page"><ErrorBoundary><Suspense fallback={<div className="page-loading"><LoaderCircle size={22} className="spin" /> Loading workspace…</div>}>{content}</Suspense></ErrorBoundary></main>
      </div>
      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  );
}

export type PageProps = {
  notify: (message: string) => void;
  openClipper: (ids: string[]) => void;
  openEditor: (clipId?: string) => void;
  openPublish: (ids: string[]) => void;
};

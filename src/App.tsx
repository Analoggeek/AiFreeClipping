import { useCallback, useEffect, useState } from 'react';
import {
  Clapperboard, CloudDownload, Download, FolderOpen, LayoutDashboard, Library,
  ListVideo, MonitorPlay, Package, PlugZap, Settings, Sparkles, UploadCloud, WifiOff,
} from 'lucide-react';
import logo from '../brand/logo.svg';
import { api, apiBase } from './api';
import { Toast, useJobs } from './components/common';
import Clipper from './pages/Clipper';
import Downloads from './pages/Downloads';
import Editor from './pages/Editor';
import ModelsPage from './pages/ModelsPage';
import Overview from './pages/Overview';
import Playlists from './pages/Playlists';
import Publish from './pages/Publish';
import SettingsPage from './pages/SettingsPage';

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
  const [version, setVersion] = useState('1.0.0');
  const [mediaSelection, setMediaSelection] = useState<string[]>([]);
  const [clipSelection, setClipSelection] = useState<string[]>([]);
  const [folder, setFolder] = useState('');
  const { jobs } = useJobs();
  const notify = useCallback((message: string) => setToast(message), []);

  useEffect(() => {
    api.health().then((result) => { setOnline(true); setVersion(result.version); }).catch(() => setOnline(false));
    api.folders().then((result) => setFolder(result.folders.exports)).catch(() => undefined);
  }, []);

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
    case 'editor': content = <Editor {...common} clipSelection={clipSelection} />; break;
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
            <button className="ghost-btn" onClick={() => folder && window.desktop?.revealPath(folder)} title="Open exports folder">
              <FolderOpen size={16} /> Exports
            </button>
            <button className="ghost-btn" onClick={() => window.desktop?.openPath('https://github.com/Analoggeek/AiFreeClipping')}>
              <CloudDownload size={16} /> GitHub
            </button>
            <div className="avatar"><Sparkles size={16} /></div>
          </div>
        </header>
        <main className="page">{content}</main>
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

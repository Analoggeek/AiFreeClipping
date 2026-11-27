import type { Capabilities, Candidate, HardwareInfo, Job, Media, ModelInfo, Project, Timeline } from './types';

const query = new URLSearchParams(window.location.search);
const token = window.desktop?.token?.() || query.get('token') || localStorage.getItem('aifreeclip.token') || '';
const base = (window.desktop?.apiBase?.() || query.get('api') || '').replace(/\/$/, '');
if (token) localStorage.setItem('aifreeclip.token', token);

export const hasDesktop = Boolean(window.desktop);
export const apiBase = base;

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-AI-Clipper-Token': token,
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown = {}) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body) });

export const api = {
  health: () => request<{ ok: boolean; version: string }>('/api/health'),
  capabilities: () => request<{ ok: boolean } & Capabilities>('/api/system/capabilities'),
  hardware: () => request<{ ok: boolean } & HardwareInfo>('/api/system/hardware'),
  jobs: () => request<{ jobs: Job[] }>('/api/jobs'),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => request<{ ok: boolean; cancelled: boolean }>(`/api/jobs/${id}/cancel`, { method: 'POST' }),
  folders: () => request<{ folders: Record<string, string> }>('/api/folders'),

  inspect: (url: string, mode = 'auto') => post<{ info: Record<string, unknown> }>('/api/downloads/inspect', { url, mode }),
  download: (payload: Record<string, unknown>) => post<{ job_id: string }>('/api/downloads', payload),
  media: () => request<{ media: Media[] }>('/api/media'),
  importMedia: (paths: string[]) => post<{ media: Media[] }>('/api/media/import', { paths }),
  deleteMedia: (id: string, deleteFile = true) => request<{ ok: boolean; file_deleted: boolean; file_error?: string | null; file_kept_shared?: boolean }>(`/api/media/${id}?delete_file=${deleteFile}`, { method: 'DELETE' }),
  playlists: () => request<{ playlists: Array<{ id: string; title: string; url: string; items: unknown[] }> }>('/api/playlists'),
  playlist: (id: string) => request<{ playlist: Record<string, unknown>; media: Media[] }>(`/api/playlists/${id}`),

  transcribe: (media_id: string) => post<{ job_id: string }>('/api/analysis/transcribe', { media_id }),
  transcript: (media_id: string) => request<{ transcript: { segments?: Array<{ start: number; end: number; text: string }> } }>(`/api/analysis/${media_id}/transcript`),
  propose: (payload: Record<string, unknown>) => post<{ job_id: string }>('/api/clips/propose', payload),
  clips: () => request<{ clips: Candidate[] }>('/api/clips'),
  patchClip: (id: string, patch: Partial<Candidate>) => request<{ clip: Candidate }>(`/api/clips/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  applyEffects: (clip_ids: string[], effects: Record<string, unknown>) =>
    post<{ ok: boolean; changed: number }>('/api/clips/apply-effects', { clip_ids, effects }),
  deleteClip: (id: string) => request<{ ok: boolean; file_deleted: boolean }>(`/api/clips/${id}`, { method: 'DELETE' }),
  deleteClips: (clip_ids: string[]) => request<{ ok: boolean; deleted: number; files_deleted: number }>('/api/clips/bulk-delete', { method: 'DELETE', body: JSON.stringify({ clip_ids }) }),
  renderClip: (id: string, payload: Record<string, unknown>) => post<{ job_id: string }>(`/api/clips/${id}/render`, payload),
  exportBatch: (clip_ids: string[], aspect = '9:16', resolution = 'source') =>
    post<{ job_id: string }>('/api/exports/batch', { clip_ids, aspect, resolution }),

  projects: () => request<{ projects: Project[] }>('/api/projects'),
  createProject: (payload: Record<string, unknown>) => post<{ project: Project }>('/api/projects', payload),
  project: (id: string) => request<{ project: Project }>(`/api/projects/${id}`),
  saveProject: (id: string, timeline: Timeline, name?: string) =>
    request<{ project: Project }>(`/api/projects/${id}`, { method: 'PUT', body: JSON.stringify({ timeline, name }) }),
  exportProject: (id: string, aspect: string, resolution: string) => post<{ job_id: string }>(`/api/projects/${id}/export`, { aspect, resolution }),

  searchAssets: (query: string, source: string, kind: string) =>
    post<{ results: Array<Record<string, string>> }>('/api/assets/search', { query, source, kind }),
  downloadAsset: (url: string, name: string, source: string) =>
    post<{ asset: { path: string; url: string } }>('/api/assets/download', { url, name, source }),
  generateImage: (prompt: string, provider: string, aspect: string) =>
    post<{ job_id: string }>('/api/images/generate', { prompt, provider, aspect }),
  sfx: () => request<{ sfx: string[] }>('/api/sfx'),
  sfxPath: (name: string) => request<{ path: string }>(`/api/sfx/${name}/path`),

  models: () => request<{ models: ModelInfo[] }>('/api/models'),
  selectComfyCheckpoint: (path: string) => post<{ checkpoint: { filename: string; path: string; installed: boolean } }>('/api/models/comfyui-checkpoint', { path }),
  installModel: (model_id: string) => post<{ job_id: string }>('/api/models/install', { model_id }),
  installRecommendedModels: () => post<{ job_id: string }>('/api/models/install-recommended', {}),
  autoSetupModels: () => post<{ job_id: string; skipped?: boolean; message?: string }>('/api/models/auto-setup', {}),
  setFolder: (key: string, path: string) => request<{ folders: Record<string, string> }>('/api/folders', { method: 'PUT', body: JSON.stringify({ key, path }) }),
  autoEdit: (clip_ids: string[], style = 'hype', aspect = '9:16', resolution = 'source') => post<{ job_id: string }>('/api/auto-edit', { clip_ids, style, aspect, resolution }),

  youtubeStatus: () => request<{ authorized: boolean; available: boolean; clientSecretConfigured: boolean }>('/api/youtube/status'),
  youtubeAuthorize: () => post<{ job_id: string }>('/api/youtube/authorize'),
  youtubeUpload: (payload: Record<string, unknown>) => post<{ job_id: string }>('/api/youtube/upload', payload),

  settings: () => request<{ values: Record<string, string>; capabilities: Record<string, unknown> }>('/api/settings'),
  saveSettings: (values: Record<string, string>) => request<{ values: Record<string, string> }>('/api/settings', { method: 'PUT', body: JSON.stringify({ values }) }),
};

export function mediaUrl(path?: string | null): string {
  if (!path) return '';
  return `${base}${path}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`;
}

export function pollJob(id: string, onUpdate: (job: Job) => void, interval = 900): () => void {
  let active = true;
  const tick = async () => {
    if (!active) return;
    try {
      const job = await api.job(id);
      onUpdate(job);
      if (['done', 'error', 'cancelled'].includes(job.status)) active = false;
    } catch {
      active = false;
    }
    if (active) window.setTimeout(tick, interval);
  };
  void tick();
  return () => { active = false; };
}

export type Media = {
  id: string;
  title: string;
  path: string;
  source_url?: string | null;
  duration: number;
  width: number;
  height: number;
  thumbnail?: string | null;
  playlist_id?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string;
};

export type Job = {
  id: string;
  kind: string;
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled';
  progress: number;
  message: string;
  result?: Record<string, unknown> | null;
  error?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type Candidate = {
  media_id: string;
  start: number;
  end: number;
  score: number;
  reasons: string[];
  title: string;
  hook: string;
  hashtags: string[];
  transcript: string;
  region?: { x: number; y: number; w: number; h: number } | null;
  regions?: Array<{ x: number; y: number; w: number; h: number }>;
  region_layout?: string | null;
  id?: string;
  output?: string | null;
  effects?: Record<string, unknown>;
  hardware?: HardwareInfo;
};

export type ModelInfo = {
  id: string;
  kind: string;
  name: string;
  provider: string;
  size: string;
  use: string;
  installed: boolean;
  recommended?: boolean;
  downloadUrl?: string;
  docsUrl?: string;
  apiUrl?: string;
  providerUrl?: string;
  autoInstall?: boolean;
  needsApi?: boolean;
  setupNote?: string;
};

export type HardwareInfo = {
  cpu_count: number;
  cpu_percent: number | null;
  ram_percent: number | null;
  ram_used_gb: number | null;
  ram_total_gb: number | null;
  disk_free_gb: number | null;
  app_usage_gb?: number;
  gpu: { cuda: boolean; metal: boolean; name?: string; note?: string };
  workers: number;
  encoder: string;
  platform: string;
};

export type Capabilities = {
  ffmpeg?: string | null;
  ffprobe?: string | null;
  ytDlp?: boolean;
  fasterWhisper?: boolean;
  opencv?: boolean;
  ultralytics?: boolean;
  gpu?: { cuda: boolean; metal: boolean; note?: string };
  paths?: Record<string, string>;
  ollamaModel?: string;
  whisperModel?: string;
};

export type VideoItem = {
  id?: string; clip_id?: string; path: string; sourceStart: number; duration: number;
  label?: string; region?: { x: number; y: number; w: number; h: number } | null;
  regions?: Array<{ x: number; y: number; w: number; h: number }>;
};
export type CaptionItem = { text: string; start: number; end: number };
export type StickerItem = { path: string; start: number; end: number; x: number; y: number; label?: string };
export type AudioItem = { path: string; start: number; end: number; volume: number; label?: string };

export type Timeline = {
  tracks: {
    video: VideoItem[];
    captions: CaptionItem[];
    stickers: StickerItem[];
    audio: AudioItem[];
  };
  aspect: '9:16' | '1:1' | '16:9';
  resolution: '720p' | '1080p';
  caption_style?: { preset: string };
};

export type Project = { id: string; name: string; timeline: Timeline; updated_at?: string };

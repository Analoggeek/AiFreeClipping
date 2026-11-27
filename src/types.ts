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
  id?: string; clip_id?: string; path: string; sourceStart: number; duration: number; sourceDuration?: number;
  label?: string; region?: { x: number; y: number; w: number; h: number } | null;
  regions?: Array<{ x: number; y: number; w: number; h: number }>;
  region_layout?: string | null; effects?: Record<string, unknown>; auto_edit?: boolean;
};
export type CaptionItem = {
  text: string; start: number; end: number; kind?: 'title' | 'caption'; auto_edit_clip_id?: string;
};
export type StickerItem = {
  path: string; start: number; end: number; x: number; y: number; scale?: number; label?: string; auto_edit_clip_id?: string;
};
export type AudioItem = {
  path: string; start: number; end: number; volume: number; label?: string;
  kind?: 'music' | 'sfx'; auto_edit_clip_id?: string;
};

export type AutoEditOptions = {
  style: 'hype' | 'minimal' | 'premium';
  aspect: '9:16' | '1:1' | '16:9';
  resolution: 'source' | '720p' | '1080p';
  captions: boolean;
  sound_effects: boolean;
  stickers: boolean;
  blur_background: boolean;
  music?: string;
  music_volume: number;
};

export type AutoEditTimelineEdit = {
  clip_id: string;
  media_id: string;
  source_path: string;
  source_start: number;
  source_duration: number;
  duration: number;
  title: string;
  aspect: '9:16' | '1:1' | '16:9';
  resolution: 'source' | '720p' | '1080p';
  region?: VideoItem['region'];
  regions?: VideoItem['regions'];
  region_layout?: string | null;
  captions: Array<{ text?: string; word?: string; start: number; end: number; kind?: 'title' | 'caption' }>;
  audio: AudioItem[];
  stickers: StickerItem[];
  effects: Record<string, unknown>;
};

export type Timeline = {
  tracks: {
    video: VideoItem[];
    captions: CaptionItem[];
    stickers: StickerItem[];
    audio: AudioItem[];
  };
  aspect: '9:16' | '1:1' | '16:9';
  resolution: 'source' | '720p' | '1080p';
  caption_style?: { preset: string };
};

export type Project = { id: string; name: string; timeline: Timeline; updated_at?: string };

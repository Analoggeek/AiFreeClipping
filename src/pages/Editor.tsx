import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type Dispatch, type DragEvent as ReactDragEvent, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type SetStateAction } from 'react';
import {
  Clapperboard, Download, Film, ImagePlus, Layers3, LoaderCircle,
  Mic2, Pause, Play, Plus, RotateCcw, Save, SkipBack, SkipForward, Split, Trash2,
  Upload, WandSparkles,
} from 'lucide-react';
import { api, mediaUrl, pollJob } from '../api';
import { JobTracker, Pill, formatClock } from '../components/common';
import type { AutoEditOptions, AutoEditTimelineEdit, Candidate, Media, Timeline, VideoItem } from '../types';
import { appendAutoEditTimeline } from '../lib/autoEdit';
import { insertionBoundaryAtTime, insertVideoAtTime, moveVideoToTime, removeVideoAtIndex } from '../lib/timelinePlacement';
import { drawVideoComposition } from '../lib/composition';
import type { PageProps } from '../App';

type TrackKey = 'video' | 'stickers' | 'audio';
type AssetTab = 'media' | 'clips';
type AnyItem = {
  id?: string; clip_id?: string; path?: string; sourceStart?: number; sourceDuration?: number; duration?: number;
  start?: number; end?: number; volume?: number; x?: number; y?: number; scale?: number; label?: string;
  region?: Candidate['region']; regions?: Candidate['regions']; region_layout?: string | null;
  split_ratio?: number | null; outline_style?: Candidate['outline_style'];
  crop_path?: Candidate['crop_path']; effects?: Record<string, unknown>;
  auto_edit?: boolean; auto_edit_clip_id?: string; kind?: string;
};
type Selection = { track: TrackKey; index: number } | null;
type TimelineDragPayload =
  | { kind: 'media'; id: string }
  | { kind: 'clip'; id: string }
  | { kind: 'timeline'; track: TrackKey; index: number };
type TimelineDropMarker = { track: TrackKey; time: number };

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

type EditorLayout = {
  assetWidth: number;
  inspectorWidth: number;
  timelineHeight: number;
  assetHeight: number;
  stageHeight: number;
  inspectorHeight: number;
  playerScale: number;
};
type LayoutResizeTarget =
  | 'asset-width' | 'inspector-width' | 'timeline-height' | 'player-size'
  | 'tablet-inspector' | 'mobile-asset-stage' | 'mobile-stage-inspector';
type ActiveLayoutResize = {
  target: LayoutResizeTarget;
  pointerId: number;
  x: number;
  y: number;
  start: EditorLayout;
};

const EDITOR_LAYOUT_STORAGE_KEY = 'aifreeclip.editor.layout.v1';
const DEFAULT_EDITOR_LAYOUT: EditorLayout = {
  assetWidth: 262, inspectorWidth: 264, timelineHeight: 228,
  assetHeight: 190, stageHeight: 400, inspectorHeight: 320, playerScale: 0.85,
};
const DEFAULT_TIMELINE_ZOOM = 24;

function normalizeTimeline(value: unknown): Timeline {
  const raw = value && typeof value === 'object'
    ? structuredClone(value as Record<string, unknown>)
    : {};
  const sourceTracks = raw.tracks && typeof raw.tracks === 'object'
    ? raw.tracks as Record<string, unknown>
    : {};
  delete raw.caption_style;
  delete sourceTracks.captions;
  const aspect = ['9:16', '1:1', '16:9'].includes(String(raw.aspect))
    ? raw.aspect as Timeline['aspect']
    : '9:16';
  const resolution = ['source', '720p', '1080p'].includes(String(raw.resolution))
    ? raw.resolution as Timeline['resolution']
    : 'source';
  return {
    ...raw,
    tracks: {
      video: Array.isArray(sourceTracks.video) ? sourceTracks.video as VideoItem[] : [],
      stickers: Array.isArray(sourceTracks.stickers) ? sourceTracks.stickers as Timeline['tracks']['stickers'] : [],
      audio: Array.isArray(sourceTracks.audio) ? sourceTracks.audio as Timeline['tracks']['audio'] : [],
    },
    aspect,
    resolution,
  } as Timeline;
}

function boundedLayoutValue(value: unknown, fallback: number, min: number, max: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.round(clamp(parsed, min, max) * 100) / 100 : fallback;
}

function readEditorLayout(): EditorLayout {
  try {
    const stored = localStorage.getItem(EDITOR_LAYOUT_STORAGE_KEY);
    if (!stored) return { ...DEFAULT_EDITOR_LAYOUT };
    const saved = JSON.parse(stored) as Partial<EditorLayout>;
    return {
      assetWidth: boundedLayoutValue(saved.assetWidth, DEFAULT_EDITOR_LAYOUT.assetWidth, 170, 420),
      inspectorWidth: boundedLayoutValue(saved.inspectorWidth, DEFAULT_EDITOR_LAYOUT.inspectorWidth, 190, 420),
      timelineHeight: boundedLayoutValue(saved.timelineHeight, DEFAULT_EDITOR_LAYOUT.timelineHeight, 150, 540),
      assetHeight: boundedLayoutValue(saved.assetHeight, DEFAULT_EDITOR_LAYOUT.assetHeight, 140, 520),
      stageHeight: boundedLayoutValue(saved.stageHeight, DEFAULT_EDITOR_LAYOUT.stageHeight, 300, 900),
      inspectorHeight: boundedLayoutValue(saved.inspectorHeight, DEFAULT_EDITOR_LAYOUT.inspectorHeight, 220, 700),
      playerScale: boundedLayoutValue(saved.playerScale, DEFAULT_EDITOR_LAYOUT.playerScale, 0.4, 1),
    };
  } catch {
    return { ...DEFAULT_EDITOR_LAYOUT };
  }
}

function resizedEditorLayout(
  start: EditorLayout, target: LayoutResizeTarget, deltaX: number, deltaY: number,
): EditorLayout {
  const next = { ...start };
  if (target === 'asset-width') next.assetWidth = clamp(start.assetWidth + deltaX, 170, 420);
  if (target === 'inspector-width') next.inspectorWidth = clamp(start.inspectorWidth - deltaX, 190, 420);
  if (target === 'timeline-height') next.timelineHeight = clamp(start.timelineHeight - deltaY, 150, 540);
  if (target === 'player-size') next.playerScale = clamp(start.playerScale - deltaY / 250, 0.4, 1);
  if (target === 'tablet-inspector') next.inspectorHeight = clamp(start.inspectorHeight - deltaY, 220, 700);
  if (target === 'mobile-asset-stage') {
    next.assetHeight = clamp(start.assetHeight + deltaY, 140, 520);
    next.stageHeight = clamp(start.stageHeight - (next.assetHeight - start.assetHeight), 300, 900);
  }
  if (target === 'mobile-stage-inspector') {
    next.stageHeight = clamp(start.stageHeight + deltaY, 300, 900);
    next.inspectorHeight = clamp(start.inspectorHeight - (next.stageHeight - start.stageHeight), 220, 700);
  }
  return next;
}

const emptyTimeline = (): Timeline => ({
  tracks: { video: [], stickers: [], audio: [] },
  aspect: '9:16', resolution: 'source',
});
const DEFAULT_AUTO_EDIT: AutoEditOptions = {
  style: 'hype', aspect: '9:16', resolution: 'source',
  sound_effects: true, stickers: true, blur_background: true, music: '', music_volume: 0.18,
};

export default function Editor({ notify, clipSelection, setMediaSelection }: PageProps & {
  clipSelection: string[]; setMediaSelection: Dispatch<SetStateAction<string[]>>;
}) {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState('Untitled project');
  const [timeline, setTimeline] = useState<Timeline>(emptyTimeline());
  const [selected, setSelected] = useState<Selection>(null);
  const [playhead, setPlayhead] = useState(0);
  const [zoom, setZoom] = useState(DEFAULT_TIMELINE_ZOOM);
  const [editorLayout, setEditorLayout] = useState<EditorLayout>(readEditorLayout);
  const [stageAreaSize, setStageAreaSize] = useState({ width: 0, height: 0 });
  const [playing, setPlaying] = useState(false);
  const [media, setMedia] = useState<Media[]>([]);
  const [newMedia, setNewMedia] = useState('');
  const [tab, setTab] = useState<AssetTab>('media');
  const [importingMedia, setImportingMedia] = useState(false);
  const [exportJob, setExportJob] = useState<string | null>(null);
  const [exportOutput, setExportOutput] = useState('');
  const [clips, setClips] = useState<Candidate[]>([]);
  const [autoJob, setAutoJob] = useState<string | null>(null);
  const [autoEditOptions, setAutoEditOptions] = useState<AutoEditOptions>(DEFAULT_AUTO_EDIT);
  const [autoEditSettingsLoaded, setAutoEditSettingsLoaded] = useState(false);
  const [deletingMediaId, setDeletingMediaId] = useState<string | null>(null);
  const [dropMarker, setDropMarker] = useState<TimelineDropMarker | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const stageCanvasRef = useRef<HTMLCanvasElement>(null);
  const stageAreaRef = useRef<HTMLDivElement>(null);
  const stageFrameRef = useRef<HTMLDivElement>(null);
  const layoutResizeRef = useRef<ActiveLayoutResize | null>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const timelineDragRef = useRef<TimelineDragPayload | null>(null);
  const timelineStateRef = useRef(timeline);
  const projectStateRef = useRef({ id: projectId, name: projectName });
  const scrubbingRef = useRef(false);

  const total = useMemo(() => Math.max(6, timeline.tracks.video.reduce((sum, item) => sum + item.duration, 0)), [timeline.tracks.video]);

  useEffect(() => { timelineStateRef.current = timeline; }, [timeline]);
  useEffect(() => { projectStateRef.current = { id: projectId, name: projectName }; }, [projectId, projectName]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      try { localStorage.setItem(EDITOR_LAYOUT_STORAGE_KEY, JSON.stringify(editorLayout)); }
      catch { /* keep editor layout usable when browser storage is unavailable */ }
    }, 120);
    return () => window.clearTimeout(timer);
  }, [editorLayout]);
  useEffect(() => {
    const node = stageAreaRef.current;
    if (!node) return;
    const measure = () => {
      const rect = node.getBoundingClientRect();
      const next = { width: Math.max(0, rect.width), height: Math.max(0, rect.height) };
      setStageAreaSize((current) => current.width === next.width && current.height === next.height ? current : next);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure);
      return () => window.removeEventListener('resize', measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    api.settings().then(({ values }) => {
      const volume = Number(values.auto_edit_music_volume ?? DEFAULT_AUTO_EDIT.music_volume);
      setAutoEditOptions({
        style: ['hype', 'minimal', 'premium'].includes(values.auto_edit_style) ? values.auto_edit_style as AutoEditOptions['style'] : DEFAULT_AUTO_EDIT.style,
        aspect: ['9:16', '1:1', '16:9'].includes(values.auto_edit_aspect) ? values.auto_edit_aspect as AutoEditOptions['aspect'] : DEFAULT_AUTO_EDIT.aspect,
        resolution: ['source', '720p', '1080p'].includes(values.auto_edit_resolution) ? values.auto_edit_resolution as AutoEditOptions['resolution'] : DEFAULT_AUTO_EDIT.resolution,
        sound_effects: values.auto_edit_sound_effects === undefined ? true : !['0', 'false'].includes(values.auto_edit_sound_effects.toLowerCase()),
        stickers: values.auto_edit_stickers === undefined ? true : !['0', 'false'].includes(values.auto_edit_stickers.toLowerCase()),
        blur_background: values.auto_edit_blur_background === undefined ? true : !['0', 'false'].includes(values.auto_edit_blur_background.toLowerCase()),
        music: values.auto_edit_music || '',
        music_volume: Number.isFinite(volume) ? Math.max(0, Math.min(1, volume)) : DEFAULT_AUTO_EDIT.music_volume,
      });
      setAutoEditSettingsLoaded(true);
    }).catch(() => setAutoEditSettingsLoaded(true));
  }, []);

  const loadProject = useCallback(async (id: string) => {
    try {
      const result = await api.project(id);
      const loadedTimeline = normalizeTimeline(result.project.timeline);
      projectStateRef.current = { id, name: result.project.name };
      timelineStateRef.current = loadedTimeline;
      setProjectId(id);
      setProjectName(result.project.name);
      setTimeline(loadedTimeline);
      setSelected(loadedTimeline.tracks.video.length ? { track: 'video', index: 0 } : null);
      setPlayhead(0);
      setPlaying(false);
    } catch (error) { notify(String(error)); }
  }, [notify]);

  const refreshClips = useCallback(async () => {
    try { setClips((await api.clips()).clips || []); } catch { /* keep editor usable offline */ }
  }, []);

  useEffect(() => {
    api.media().then((result) => {
      setMedia(result.media);
      return api.projects();
    }).then((projects) => {
      if (clipSelection[0]) {
        setTab('clips');
        void api.createProject({ name: 'Auto Edit project', clip_id: clipSelection[0] }).then((created) => loadProject(created.project.id));
      } else if (projects.projects.length) {
        void loadProject(projects.projects[0].id);
      }
    }).catch(() => undefined);
  }, [clipSelection, loadProject]);


  useEffect(() => {
    if (!exportJob) return;
    return pollJob(exportJob, (job) => {
      if (job.status === 'done') {
        if (job.result?.output) { setExportOutput(String(job.result.output)); notify('Export ready — download it from here.'); }
        setExportJob(null);
      }
      if (job.status === 'error') { notify(job.error || job.message); setExportJob(null); }
      if (job.status === 'cancelled') { notify('Export cancelled.'); setExportJob(null); }
    });
  }, [exportJob, notify]);

  useEffect(() => {
    void refreshClips();
    const timer = window.setInterval(() => { void refreshClips(); }, 4000);
    return () => window.clearInterval(timer);
  }, [refreshClips]);

  useEffect(() => {
    if (!autoJob) return;
    return pollJob(autoJob, (job) => {
      if (job.status === 'done') {
        void refreshClips();
        const outputs = Array.isArray(job.result?.outputs) ? job.result.outputs.length : 0;
        const edits = Array.isArray(job.result?.edits) ? job.result.edits as AutoEditTimelineEdit[] : [];
        const warnings = Array.isArray(job.result?.warnings) ? job.result.warnings as string[] : [];
        const warningSummary = warnings.length
          ? ` ${warnings.length} warning(s): ${warnings[0]}${warnings.length > 1 ? ` (+${warnings.length - 1} more)` : ''}`
          : '';
        if (edits.length) {
          void applyAutoEditEdits(edits).then(() => {
            notify(`Auto Edit applied to ${edits.length} clip(s): editable video, stickers and audio are now on the timeline; ${outputs} MP4(s) rendered.${warningSummary}`);
          }).catch((error) => notify(`MP4s rendered, but the editable timeline could not be saved: ${String(error)}${warningSummary}`))
            .finally(() => setAutoJob(null));
        } else {
          setAutoJob(null);
          notify(`Auto Edit finished with no clips to add to the timeline.${warningSummary}`);
        }
      }
      if (job.status === 'error') { setAutoJob(null); notify(job.error || job.message); }
      if (job.status === 'cancelled') { setAutoJob(null); notify('Automatic editing cancelled.'); }
    });
  }, [autoJob, notify, refreshClips]);

  async function applyAutoEditEdits(edits: AutoEditTimelineEdit[]) {
    const current = timelineStateRef.current;
    const { timeline: next, start } = appendAutoEditTimeline(current, edits);
    const project = projectStateRef.current;
    let projectId = project.id;
    let projectName = project.name || 'Auto Edit';
    if (projectId) {
      await api.saveProject(projectId, next, projectName);
    } else {
      const created = await api.createProject({ name: 'Auto Edit', template: next });
      projectId = created.project.id;
      projectName = created.project.name;
    }
    projectStateRef.current = { id: projectId, name: projectName };
    timelineStateRef.current = next;
    setProjectId(projectId);
    setProjectName(projectName);
    setTimeline(next);
    setPlayhead(start);
    setExportOutput('');
    const firstAutoClip = next.tracks.video.findIndex((item) => item.auto_edit && edits.some((edit) => edit.clip_id === item.clip_id));
    if (firstAutoClip >= 0) setSelected({ track: 'video', index: firstAutoClip });
  }

  const runAutoEdit = async () => {
    const ids = clips.map((clip) => clip.id || '').filter(Boolean);
    if (!ids.length) { notify('Generate clips with AI Clipper first.'); return; }
    try {
      const result = await api.autoEdit(ids, autoEditOptions);
      setAutoJob(result.job_id);
      notify(`Applying Auto Edit to ${ids.length} clip(s); finished videos will be added as editable timeline tracks.`);
    } catch (error) { notify(String(error)); }
  };

  const mutate = (fn: (draft: Timeline) => void) => {
    setExportOutput('');
    setTimeline((current) => {
      const next = structuredClone(current);
      fn(next);
      return next;
    });
  };

  const commitTimeline = (next: Timeline) => {
    timelineStateRef.current = next;
    setTimeline(next);
    setExportOutput('');
  };

  const focusVideoItem = (index: number, start: number) => {
    setSelected({ track: 'video', index });
    setPlayhead(start);
    setPlaying(false);
  };

  const removeSelected = () => {
    if (!selected) return;
    const item = (timelineStateRef.current.tracks[selected.track] as unknown as AnyItem[])[selected.index];
    if (selected.track === 'video') {
      const next = removeVideoAtIndex(timelineStateRef.current, selected.index).timeline;
      if (item?.auto_edit && item.clip_id && !next.tracks.video.some((entry) => entry.clip_id === item.clip_id)) {
        next.tracks.stickers = next.tracks.stickers.filter((entry) => entry.auto_edit_clip_id !== item.clip_id);
        next.tracks.audio = next.tracks.audio.filter((entry) => entry.auto_edit_clip_id !== item.clip_id);
      }
      commitTimeline(next);
      if (next.tracks.video.length) {
        const index = Math.min(selected.index, next.tracks.video.length - 1);
        const start = next.tracks.video.slice(0, index).reduce((sum, clip) => sum + clip.duration, 0);
        focusVideoItem(index, start);
      } else setSelected(null);
      return;
    }
    mutate((draft) => { (draft.tracks[selected.track] as unknown as AnyItem[]).splice(selected.index, 1); });
    setSelected(null);
  };

  const splitSelected = () => {
    if (!selected || selected.track !== 'video') { notify('Select a video clip on the timeline to split it.'); return; }
    const item = timeline.tracks.video[selected.index];
    const itemStart = timeline.tracks.video.slice(0, selected.index).reduce((sum, part) => sum + part.duration, 0);
    const offset = playhead - itemStart;
    if (offset <= 0.2 || offset >= item.duration - 0.2) { notify('Move the playhead inside the selected clip before splitting.'); return; }
    mutate((draft) => {
      const first = draft.tracks.video[selected.index];
      const speed = Math.max(0.25, Math.min(4, Number(first.effects?.speed || 1)));
      const originalSourceDuration = Math.max(0.05, Number(first.sourceDuration ?? first.duration * speed));
      const minimumSourceSlice = Math.min(0.2 * speed, originalSourceDuration / 2);
      const sourceOffset = Math.max(
        minimumSourceSlice,
        Math.min(originalSourceDuration - minimumSourceSlice, offset * speed),
      );
      const firstDuration = sourceOffset / speed;
      const second = {
        ...first, id: `split-${first.id || first.clip_id || 'video'}-${Date.now()}`, sourceStart: Number(first.sourceStart || 0) + sourceOffset,
        sourceDuration: originalSourceDuration - sourceOffset, duration: first.duration - firstDuration,
        label: `${first.label || 'Clip'} B`,
      };
      first.duration = firstDuration;
      first.sourceDuration = sourceOffset;
      draft.tracks.video.splice(selected.index + 1, 0, second);
    });
    notify('Clip split at playhead.');
  };

  const seekTo = (seconds: number) => {
    const next = Math.max(0, Math.min(total, seconds));
    setPlayhead(next);
    if (videoRef.current && activeVideo && Number.isFinite(next)) {
      const offset = Math.max(0, next - activeVideoStart);
      const speed = Math.max(0.25, Math.min(4, Number(activeVideo.effects?.speed || 1)));
      const sourceStart = Number(activeVideo.sourceStart || 0);
      const sourceEnd = sourceStart + (activeVideo.sourceDuration || activeVideo.duration * speed);
      const target = sourceStart + offset * speed;
      videoRef.current.currentTime = Math.max(0, Math.min(videoRef.current.duration || sourceEnd, Math.min(sourceEnd, target)));
    }
  };

  const scrub = (event: React.PointerEvent<HTMLDivElement>) => {
    const bounds = timelineRef.current?.getBoundingClientRect();
    if (!bounds) return;
    seekTo((event.clientX - bounds.left + timelineRef.current!.scrollLeft) / zoom);
  };

  useEffect(() => {
    const node = timelineRef.current;
    if (!node) return;
    const x = playhead * zoom;
    if (x < node.scrollLeft || x > node.scrollLeft + node.clientWidth - 40) {
      node.scrollLeft = Math.max(0, x - node.clientWidth * 0.35);
    }
  }, [playhead, zoom]);

  const selectedItem = selected ? (timeline.tracks[selected.track] as unknown as AnyItem[])[selected.index] : null;
  const updateSelected = (patch: Partial<AnyItem>) => {
    if (!selected) return;
    mutate((draft) => {
      const item = (draft.tracks[selected.track] as unknown as AnyItem[])[selected.index];
      if (item) Object.assign(item, patch);
    });
  };

  const beginLayoutResize = (target: LayoutResizeTarget, event: ReactPointerEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    layoutResizeRef.current = {
      target, pointerId: event.pointerId, x: event.clientX, y: event.clientY,
      start: { ...editorLayout },
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const moveLayoutResize = (target: LayoutResizeTarget, event: ReactPointerEvent<HTMLElement>) => {
    const active = layoutResizeRef.current;
    if (!active || active.target !== target || active.pointerId !== event.pointerId) return;
    setEditorLayout(resizedEditorLayout(
      active.start, target, event.clientX - active.x, event.clientY - active.y,
    ));
  };

  const endLayoutResize = (event: ReactPointerEvent<HTMLElement>) => {
    if (layoutResizeRef.current?.pointerId === event.pointerId) layoutResizeRef.current = null;
  };

  const keyboardResize = (target: LayoutResizeTarget, event: ReactKeyboardEvent<HTMLElement>) => {
    const step = event.shiftKey ? 32 : 12;
    let deltaX = 0;
    let deltaY = 0;
    if (target === 'asset-width') {
      if (event.key === 'ArrowRight') deltaX = step;
      else if (event.key === 'ArrowLeft') deltaX = -step;
    } else if (target === 'inspector-width') {
      if (event.key === 'ArrowLeft') deltaX = -step;
      else if (event.key === 'ArrowRight') deltaX = step;
    } else if (target === 'timeline-height' || target === 'player-size' || target === 'tablet-inspector') {
      if (event.key === 'ArrowUp') deltaY = -step;
      else if (event.key === 'ArrowDown') deltaY = step;
    } else {
      if (event.key === 'ArrowDown') deltaY = step;
      else if (event.key === 'ArrowUp') deltaY = -step;
    }
    if (!deltaX && !deltaY) return;
    event.preventDefault();
    setEditorLayout((current) => resizedEditorLayout(current, target, deltaX, deltaY));
  };

  const resetEditorLayout = () => {
    setEditorLayout({ ...DEFAULT_EDITOR_LAYOUT });
    setZoom(DEFAULT_TIMELINE_ZOOM);
    notify('Editor panel sizes, Shorts player and timeline zoom reset to defaults.');
  };

  const importLocalMedia = async () => {
    if (!window.desktop?.selectFiles) {
      notify('Local video imports are available in the desktop app.');
      return;
    }
    setImportingMedia(true);
    try {
      const paths = await window.desktop.selectFiles([{
        name: 'Video files',
        extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi', 'm4v', 'mpeg', 'mpg', '3gp', 'mts'],
      }]);
      if (!paths.length) return;
      const result = await api.importMedia(paths);
      const imported = result.media || [];
      if (!imported.length) {
        notify('No supported video files were imported.');
        return;
      }
      setMedia((current) => {
        const existing = new Set(current.map((item) => item.id));
        return [...imported.filter((item) => !existing.has(item.id)), ...current];
      });
      notify(`Imported ${imported.length} local video(s). Select one from Media to add it to the timeline.`);
    } catch (error) { notify(String(error)); }
    finally { setImportingMedia(false); }
  };

  const createProject = async () => {
    const chosen = media.find((item) => item.id === newMedia);
    if (!chosen) { notify('Choose a source video first.'); return; }
    try {
      const result = await api.createProject({ name: chosen.title, media_id: chosen.id });
      setNewMedia('');
      await loadProject(result.project.id);
    } catch (error) { notify(String(error)); }
  };

  const save = async () => {
    if (!projectId) { notify('Create a project first.'); return; }
    try { await api.saveProject(projectId, timeline, projectName); notify('Project saved.'); }
    catch (error) { notify(String(error)); }
  };

  const exportVideo = async () => {
    if (!projectId || !timeline.tracks.video.length) { notify('Add a video clip to the timeline first.'); return; }
    try {
      setExportOutput('');
      await save();
      const result = await api.exportProject(projectId, timeline.aspect, timeline.resolution);
      setExportJob(result.job_id);
    } catch (error) { notify(String(error)); }
  };

  const addMediaToTimeline = async (item: Media, atTime = playhead): Promise<boolean> => {
    const video: VideoItem = {
      id: `media-${item.id}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      media_id: item.id,
      path: item.path,
      sourceStart: 0,
      duration: Math.min(30, Math.max(3, item.duration || 10)),
      label: item.title,
    };
    let current = timelineStateRef.current;
    if (!projectStateRef.current.id) {
      try {
        const created = await api.createProject({ name: item.title });
        current = normalizeTimeline(created.project.timeline);
        projectStateRef.current = { id: created.project.id, name: created.project.name };
        setProjectId(created.project.id);
        setProjectName(created.project.name);
      } catch (error) { notify(String(error)); return false; }
    }
    const placed = insertVideoAtTime(current, video, atTime);
    commitTimeline(placed.timeline);
    focusVideoItem(placed.index, placed.start);
    notify(`Added “${item.title}” at ${formatClock(placed.start)}. Drag clips on the video track to reorder them.`);
    return true;
  };

  const removeMediaFromLibrary = async (item: Media) => {
    const fileNote = item.source_url
      ? 'If no saved clip, project, or library item uses this download, its file may also be deleted.'
      : 'The original imported file will remain on disk.';
    if (!window.confirm(`Remove “${item.title}” from the media library? ${fileNote}`)) return;
    setDeletingMediaId(item.id);
    try {
      const result = await api.deleteMedia(item.id, true);
      setMedia((current) => current.filter((entry) => entry.id !== item.id));
      setMediaSelection((current) => current.filter((id) => id !== item.id));
      setNewMedia((current) => current === item.id ? '' : current);
      if (result.file_error) notify(`Removed from the library, but the source file could not be deleted: ${result.file_error}`);
      else if (result.file_deleted) notify('Video removed from the library and downloaded file deleted.');
      else if (result.file_kept_shared) notify('Video removed from the library; its source is kept because another clip or project uses it.');
      else notify('Video removed from the library. The original file was kept.');
    } catch (error) { notify(String(error)); }
    finally { setDeletingMediaId(null); }
  };

  const addClipToTimeline = async (clip: Candidate, atTime = playhead): Promise<boolean> => {
    if (!clip.id) { notify('This AI clip has no saved clip ID yet.'); return false; }
    const sourceMedia = media.find((item) => item.id === clip.media_id);
    if (!sourceMedia) { notify('The source video for this clip is no longer in your library.'); return false; }
    const video: VideoItem = {
      id: `clip-${clip.id}-${Date.now()}`,
      clip_id: clip.id,
      media_id: clip.media_id,
      path: sourceMedia.path,
      sourceStart: clip.start,
      duration: Math.max(0.2, clip.end - clip.start),
      label: clip.title,
      region: clip.region,
      regions: clip.regions,
      region_layout: clip.region_layout,
      split_ratio: clip.split_ratio,
      outline_style: clip.outline_style,
      crop_path: clip.crop_path || [],
    };
    let current = timelineStateRef.current;
    if (!projectStateRef.current.id) {
      try {
        const created = await api.createProject({ name: clip.title.slice(0, 60) });
        current = normalizeTimeline(created.project.timeline);
        projectStateRef.current = { id: created.project.id, name: created.project.name };
        setProjectId(created.project.id);
        setProjectName(created.project.name);
      } catch (error) { notify(String(error)); return false; }
    }
    const placed = insertVideoAtTime(current, video, atTime);
    commitTimeline(placed.timeline);
    focusVideoItem(placed.index, placed.start);
    notify(`Added “${clip.title}” at ${formatClock(placed.start)} without replacing the other clips.`);
    return true;
  };

  const startAssetDrag = (event: ReactDragEvent<HTMLButtonElement>, payload: Extract<TimelineDragPayload, { kind: 'media' | 'clip' }>) => {
    timelineDragRef.current = payload;
    event.dataTransfer.effectAllowed = 'copy';
    event.dataTransfer.setData('text/plain', `${payload.kind}:${payload.id}`);
  };

  const startTimelineItemDrag = (event: ReactDragEvent<HTMLButtonElement>, track: TrackKey, index: number) => {
    timelineDragRef.current = { kind: 'timeline', track, index };
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', `timeline:${track}:${index}`);
  };

  const endTimelineDrag = () => {
    timelineDragRef.current = null;
    setDropMarker(null);
  };

  const canDropTimelineItem = (payload: TimelineDragPayload, track: TrackKey) => {
    if (payload.kind === 'media' || payload.kind === 'clip') return track === 'video';
    return payload.track === track;
  };

  const timelineTimeFromDrop = (event: ReactDragEvent<HTMLDivElement>) => {
    const node = timelineRef.current;
    if (!node) return 0;
    const raw = (event.clientX - node.getBoundingClientRect().left + node.scrollLeft) / zoom;
    const duration = timelineStateRef.current.tracks.video.reduce((sum, item) => sum + Math.max(0, item.duration || 0), 0);
    return clamp(raw, 0, duration);
  };

  const handleTimelineDragOver = (track: TrackKey, event: ReactDragEvent<HTMLDivElement>) => {
    const payload = timelineDragRef.current;
    if (!payload || !canDropTimelineItem(payload, track)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = payload.kind === 'timeline' ? 'move' : 'copy';
    const time = timelineTimeFromDrop(event);
    const markerTime = payload.kind === 'timeline' && payload.track === 'video'
      ? insertionBoundaryAtTime(timelineStateRef.current.tracks.video, time).time
      : time;
    setDropMarker({ track, time: markerTime });
  };

  const handleTimelineDrop = async (track: TrackKey, event: ReactDragEvent<HTMLDivElement>) => {
    const payload = timelineDragRef.current;
    if (!payload || !canDropTimelineItem(payload, track)) return;
    event.preventDefault();
    event.stopPropagation();
    const time = timelineTimeFromDrop(event);
    try {
      if (payload.kind === 'media') {
        const item = media.find((entry) => entry.id === payload.id);
        if (item) await addMediaToTimeline(item, time);
        else notify('That media item is no longer in the library.');
      } else if (payload.kind === 'clip') {
        const clip = clips.find((entry) => entry.id === payload.id);
        if (clip) await addClipToTimeline(clip, time);
        else notify('That AI clip is no longer available.');
      } else if (payload.track === 'video') {
        const placement = moveVideoToTime(timelineStateRef.current, payload.index, time);
        if (placement.changed) {
          commitTimeline(placement.timeline);
          focusVideoItem(placement.index, placement.start);
          notify(`Video clip moved to ${formatClock(placement.start)}.`);
        }
      } else {
        const current = timelineStateRef.current;
        const currentItem = (current.tracks[payload.track] as unknown as AnyItem[])[payload.index];
        if (!currentItem || currentItem.start === undefined || currentItem.end === undefined) return;
        const duration = Math.max(0.05, currentItem.end - currentItem.start);
        const timelineDuration = current.tracks.video.reduce((sum, item) => sum + Math.max(0, item.duration || 0), 0);
        const start = clamp(time, 0, Math.max(0, timelineDuration - duration));
        const next = structuredClone(current);
        const moved = (next.tracks[payload.track] as unknown as AnyItem[])[payload.index];
        moved.start = start;
        moved.end = start + duration;
        commitTimeline(next);
        setSelected({ track: payload.track, index: payload.index });
        setPlayhead(start);
        notify(`${payload.track.slice(0, 1).toUpperCase()}${payload.track.slice(1)} item moved to ${formatClock(start)}.`);
      }
    } catch (error) { notify(String(error)); }
    finally { endTimelineDrag(); }
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
      if (event.code === 'Space') {
        event.preventDefault();
        if (videoRef.current) {
          if (videoRef.current.paused) { void videoRef.current.play().catch(() => setPlaying(false)); setPlaying(true); }
          else { videoRef.current.pause(); setPlaying(false); }
        }
      }
      if (event.key.toLowerCase() === 's') splitSelected();
      if (event.key === 'Delete' || event.key === 'Backspace') removeSelected();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const activeVideoIndex = useMemo(() => {
    let cursor = 0;
    for (let index = 0; index < timeline.tracks.video.length; index++) {
      if (playhead >= cursor && playhead < cursor + timeline.tracks.video[index].duration) return index;
      cursor += timeline.tracks.video[index].duration;
    }
    return timeline.tracks.video.length ? timeline.tracks.video.length - 1 : -1;
  }, [playhead, timeline.tracks.video]);
  const activeVideo = activeVideoIndex >= 0 ? timeline.tracks.video[activeVideoIndex] : null;
  const activeVideoStart = useMemo(() => timeline.tracks.video.slice(0, Math.max(0, activeVideoIndex)).reduce((sum, item) => sum + item.duration, 0), [activeVideoIndex, timeline.tracks.video]);
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !activeVideo) return;
    const speed = Math.max(0.25, Math.min(4, Number(activeVideo.effects?.speed || 1)));
    const sourceStart = Number(activeVideo.sourceStart || 0);
    const sourceEnd = sourceStart + Math.max(0.05, Number(activeVideo.sourceDuration ?? activeVideo.duration * speed));
    const clipOffset = Math.max(0, Math.min(activeVideo.duration, playhead - activeVideoStart));
    const target = Math.max(sourceStart, Math.min(sourceEnd, sourceStart + clipOffset * speed));
    if (video.playbackRate !== speed) video.playbackRate = speed;
    const activeSource = video.getAttribute('src');
    const expectedSource = mediaUrl(`/media/file?path=${encodeURIComponent(activeVideo.path)}`);
    if (activeSource !== expectedSource) return;
    if (Math.abs(video.currentTime - target) > 0.45 && Number.isFinite(target)) {
      video.currentTime = Math.max(0, Math.min(video.duration || sourceEnd, Math.min(sourceEnd, target)));
    }
  }, [playhead, activeVideo, activeVideoStart]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (!playing || !activeVideo) {
      if (!video.paused) video.pause();
      if (!activeVideo && playing) setPlaying(false);
      return;
    }
    if (video.paused) void video.play().catch(() => setPlaying(false));
  }, [activeVideo, activeVideoStart, playing]);

  useEffect(() => {
    const video = videoRef.current;
    const canvas = stageCanvasRef.current;
    if (!canvas) return;
    const draw = () => {
      if (!video || !activeVideo) {
        const context = canvas.getContext('2d');
        if (context) { context.fillStyle = '#05070e'; context.fillRect(0, 0, canvas.width, canvas.height); }
        return;
      }
      drawVideoComposition(video, canvas, {
        aspect: timeline.aspect,
        region: activeVideo.region,
        regions: activeVideo.regions,
        layout: activeVideo.region_layout,
        splitRatio: activeVideo.split_ratio ?? Number(activeVideo.effects?.split_ratio),
        outlineStyle: activeVideo.outline_style || String(activeVideo.effects?.outline_style || 'clean') as 'none' | 'clean' | 'neon' | 'double',
        cropPath: activeVideo.crop_path,
        fit: 'cover',
        brightness: Number(activeVideo.effects?.brightness ?? 0),
        contrast: Number(activeVideo.effects?.contrast ?? 1),
        saturation: Number(activeVideo.effects?.saturation ?? 1),
      });
    };
    if (!video || !activeVideo) { draw(); return; }
    let animation = 0;
    const tick = () => {
      draw();
      if (!video.paused && !video.ended) animation = window.requestAnimationFrame(tick);
    };
    const start = () => { draw(); if (!video.paused) animation = window.requestAnimationFrame(tick); };
    video.addEventListener('loadeddata', start);
    video.addEventListener('seeked', draw);
    video.addEventListener('timeupdate', draw);
    video.addEventListener('play', start);
    draw();
    return () => {
      video.removeEventListener('loadeddata', start);
      video.removeEventListener('seeked', draw);
      video.removeEventListener('timeupdate', draw);
      video.removeEventListener('play', start);
      if (animation) window.cancelAnimationFrame(animation);
    };
  }, [activeVideo, timeline.aspect]);

  const visibleStickers = timeline.tracks.stickers.filter((sticker) => playhead >= sticker.start && playhead <= sticker.end);
  const playerFrameSize = useMemo(() => {
    if (!stageAreaSize.width || !stageAreaSize.height) return undefined;
    const aspect = timeline.aspect === '9:16' ? 9 / 16 : timeline.aspect === '1:1' ? 1 : 16 / 9;
    const maxWidth = Math.max(0, stageAreaSize.width - 22);
    const maxHeight = Math.max(0, Math.min(560, stageAreaSize.height - 142));
    const width = Math.min(maxWidth, maxHeight * aspect);
    if (!width) return undefined;
    return {
      width: Math.round(width * editorLayout.playerScale),
      height: Math.round((width / aspect) * editorLayout.playerScale),
    };
  }, [editorLayout.playerScale, stageAreaSize, timeline.aspect]);
  const editorLayoutStyle = {
    '--editor-asset-width': `${editorLayout.assetWidth}px`,
    '--editor-inspector-width': `${editorLayout.inspectorWidth}px`,
    '--editor-timeline-height': `${editorLayout.timelineHeight}px`,
    '--editor-asset-height': `${editorLayout.assetHeight}px`,
    '--editor-stage-height': `${editorLayout.stageHeight}px`,
    '--editor-inspector-height': `${editorLayout.inspectorHeight}px`,
  } as CSSProperties;

  return (
    <div className="editor" style={editorLayoutStyle}>
      <header className="editor-toolbar">
        <div className="editor-toolbar-actions">
          <button className="ghost-btn layout-reset-button" title="Reset panel sizes, Shorts player and timeline zoom to defaults" onClick={resetEditorLayout}><RotateCcw size={14} /> Reset layout</button>
          <button className="primary" disabled={!clips.length || !autoEditSettingsLoaded || Boolean(autoJob)} title={!autoEditSettingsLoaded ? 'Loading Auto Edit settings' : clips.length ? 'Apply edits to all saved AI clips and add them to the timeline' : 'Run AI Clipper first'} onClick={() => void runAutoEdit()}>
            {autoJob ? <LoaderCircle size={15} className="spin" /> : <WandSparkles size={15} />} Auto Edit
          </button>
          <button className="ghost-btn" disabled={!projectId || !timeline.tracks.video.length || Boolean(exportJob) || Boolean(autoJob)} onClick={() => void exportVideo()}>
            {exportJob ? <LoaderCircle size={15} className="spin" /> : <Download size={15} />} Export MP4
          </button>
          <button className="icon-btn" title="Save project" aria-label="Save project" disabled={!projectId} onClick={() => void save()}><Save size={15} /></button>
        </div>
      </header>

      <div className="editor-body">
        <aside className="asset-panel">
          <div className="asset-tabs">
            {([['media', Film, 'Media'], ['clips', Clapperboard, 'Clips']] as const).map(([id, Icon, label]) => (
              <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}><Icon size={15} />{label}</button>
            ))}
          </div>
          <div className="asset-content">
            {tab === 'media' && (
              <>
                <button className="ghost-btn asset-import-button" disabled={importingMedia} onClick={() => void importLocalMedia()}>
                  {importingMedia ? <LoaderCircle size={15} className="spin" /> : <Upload size={15} />}
                  {importingMedia ? 'Importing videos…' : 'Import local videos'}
                </button>
                {!projectId && (
                  <div className="new-project">
                    <h3>Start a project</h3>
                    <select value={newMedia} onChange={(event) => setNewMedia(event.target.value)}>
                      <option value="">Choose a video from your library…</option>
                      {media.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
                    </select>
                    <button className="primary" onClick={createProject}><Plus size={15} /> Create project</button>
                  </div>
                )}
                <div className="asset-list">
                  {media.map((item) => (
                    <div key={item.id} className="asset-row-group">
                      <button
                        className="asset-row" draggable
                        onDragStart={(event) => startAssetDrag(event, { kind: 'media', id: item.id })}
                        onDragEnd={endTimelineDrag}
                        onClick={() => void addMediaToTimeline(item)}
                        aria-label={`Add ${item.title} at the playhead or drag it to the video track`}
                        title="Click to add at the playhead, or drag onto the video track to choose a position"
                      >
                        {item.thumbnail ? <img src={mediaUrl(item.thumbnail)} alt="" /> : <Film size={20} />}
                        <span><strong>{item.title}</strong><small>{formatClock(item.duration)} · Add at playhead or drag to place</small></span>
                      </button>
                      <button
                        className="icon-btn asset-row-remove"
                        title="Remove from media library"
                        aria-label={`Remove ${item.title} from the media library`}
                        disabled={deletingMediaId === item.id}
                        onClick={() => void removeMediaFromLibrary(item)}
                      >{deletingMediaId === item.id ? <LoaderCircle size={14} className="spin" /> : <Trash2 size={14} />}</button>
                    </div>
                  ))}
                  {!media.length && <p className="hint">No videos in the library yet. Import a local video or add one from Downloads.</p>}
                </div>
              </>
            )}
            {tab === 'clips' && (
              <div className="asset-list">
                <p className="hint">Click to add an AI clip at the playhead, or drag it onto the video track to choose a position. Existing clips stay in place.</p>
                {clips.length === 0 && <p className="hint">No AI clips yet. Run AI Clipper first; you can keep editing here while it works.</p>}
                {clips.map((clip, index) => {
                  const sourceMedia = media.find((item) => item.id === clip.media_id);
                  const isSelected = selected?.track === 'video' && timeline.tracks.video[selected.index]?.clip_id === clip.id;
                  return (
                    <div key={clip.id || `${clip.media_id}-${index}`} className="asset-row-group">
                      <button
                        className={`asset-row ${isSelected ? 'is-selected' : ''}`} aria-pressed={isSelected}
                        draggable={!sourceMedia ? undefined : true}
                        onDragStart={(event) => { if (clip.id) startAssetDrag(event, { kind: 'clip', id: clip.id }); }}
                        onDragEnd={endTimelineDrag}
                        disabled={!sourceMedia || !clip.id}
                        onClick={() => void addClipToTimeline(clip)}
                        title="Click to add at the playhead, or drag onto the video track to choose a position"
                      >
                        {sourceMedia?.thumbnail ? <img src={mediaUrl(sourceMedia.thumbnail)} alt="" /> : <Clapperboard size={20} />}
                        <span><strong>{clip.title}</strong><small>{formatClock(clip.start)} → {formatClock(clip.end)} · {Math.round(clip.score)}/100</small><small>{clip.output ? 'Rendered MP4 · add at playhead or drag to place' : 'Add at playhead or drag to place'}</small></span>
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </aside>

        <div
          className="editor-resizer editor-resizer-vertical editor-resizer-assets"
          role="separator" aria-orientation="vertical" aria-label="Resize Media and Shorts player panels"
          title="Drag to resize the Media panel" aria-valuemin={170} aria-valuemax={420} aria-valuenow={Math.round(editorLayout.assetWidth)} tabIndex={0}
          onPointerDown={(event) => beginLayoutResize('asset-width', event)}
          onPointerMove={(event) => moveLayoutResize('asset-width', event)}
          onPointerUp={endLayoutResize} onPointerCancel={endLayoutResize}
          onKeyDown={(event) => keyboardResize('asset-width', event)}
        />

        <div className="stage-area" ref={stageAreaRef}>
          <div className="stage-toolbar">
            <div className="stage-format-controls">
              <div className="aspect-switch">
                {(['9:16', '1:1', '16:9'] as const).map((aspect) => (
                  <button key={aspect} className={timeline.aspect === aspect ? 'active' : ''} onClick={() => mutate((draft) => { draft.aspect = aspect; })}>{aspect}</button>
                ))}
              </div>
              <select className="stage-resolution-select" aria-label="Export resolution" value={timeline.resolution} onChange={(event) => mutate((draft) => { draft.resolution = event.target.value as Timeline['resolution']; })}>
                <option value="source">Source quality</option><option value="1080p">1080p</option><option value="720p">720p</option>
              </select>
            </div>
          </div>
          <div
            ref={stageFrameRef}
            className={`stage-frame aspect-${timeline.aspect.replace(':', '-')}`}
            style={playerFrameSize ? { width: playerFrameSize.width, height: playerFrameSize.height, flex: '0 0 auto' } : undefined}
          >
            <canvas ref={stageCanvasRef} className="stage-video-canvas" aria-label="Rendered composition preview" />
            {activeVideo ? (
              <video
                className="stage-source-video"
                ref={videoRef}
                src={mediaUrl(`/media/file?path=${encodeURIComponent(activeVideo.path)}`)}
                playsInline
                preload="auto"
                onLoadStart={(event) => { event.currentTarget.pause(); }}
                onCanPlay={(event) => {
                  const video = event.currentTarget;
                  if (video.getAttribute('src') !== mediaUrl(`/media/file?path=${encodeURIComponent(activeVideo.path)}`)) return;
                  if (playing && video.paused) void video.play().catch(() => setPlaying(false));
                }}
                onPlay={() => setPlaying(true)}
                onTimeUpdate={(event) => {
                  const video = event.currentTarget;
                  const speed = Math.max(0.25, Math.min(4, Number(activeVideo.effects?.speed || 1)));
                  const sourceStart = Number(activeVideo.sourceStart || 0);
                  const elapsed = Math.max(0, (video.currentTime - sourceStart) / speed);
                  const clipPosition = Math.min(activeVideo.duration, elapsed);
                  const next = Math.max(0, Math.min(total, activeVideoStart + clipPosition));
                  const sourceDuration = Math.max(0.05, Number(activeVideo.sourceDuration ?? activeVideo.duration * speed));
                  if (elapsed >= activeVideo.duration - 0.04 || video.currentTime >= sourceStart + sourceDuration - 0.04) {
                    video.pause();
                    setPlayhead(activeVideoStart + activeVideo.duration);
                    if (activeVideoIndex >= timeline.tracks.video.length - 1) setPlaying(false);
                    return;
                  }
                  setPlayhead(next);
                }}
                onEnded={() => {
                  const next = Math.min(total, activeVideoStart + activeVideo.duration);
                  setPlayhead(next);
                  if (activeVideoIndex >= timeline.tracks.video.length - 1) setPlaying(false);
                }}
              />
            ) : <div className="stage-empty"><Film size={38} /><p>Add a video from the media panel to start editing</p></div>}
            {visibleStickers.map((sticker, index) => sticker.path && (
              <img
                className="stage-sticker"
                key={index}
                src={mediaUrl(`/media/file?path=${encodeURIComponent(sticker.path)}`)}
                style={{ left: `${(sticker.x ?? 0.7) * 100}%`, top: `${(sticker.y ?? 0.15) * 100}%` }}
                alt="sticker"
              />
            ))}
            <div className="stage-overlay-time" aria-label={`Playhead ${formatClock(playhead)} of ${formatClock(total)}`}>
              <span>{formatClock(playhead)}</span><i>/</i><span>{formatClock(total)}</span>
            </div>
            <button
              type="button" className="stage-player-resize-handle"
              aria-label={`Resize Shorts player, current size ${Math.round(editorLayout.playerScale * 100)} percent`}
              title="Drag to resize Shorts player"
              onPointerDown={(event) => beginLayoutResize('player-size', event)}
              onPointerMove={(event) => moveLayoutResize('player-size', event)}
              onPointerUp={endLayoutResize} onPointerCancel={endLayoutResize}
              onKeyDown={(event) => keyboardResize('player-size', event)}
            />
          </div>
          <div className="stage-controls">
            <button className="icon-btn" title="Jump to start" aria-label="Jump to start" onClick={() => seekTo(0)}><SkipBack size={17} /></button>
            <button className="icon-btn" title="Back 5 seconds" aria-label="Back 5 seconds" onClick={() => seekTo(playhead - 5)}><SkipBack size={17} /></button>
            <button
              className={`play-btn ${playing ? 'is-playing' : ''}`}
              title={playing ? 'Pause' : 'Play'}
              aria-label={playing ? 'Pause' : 'Play'}
              onClick={() => {
                if (!videoRef.current) return;
                if (videoRef.current.paused) { void videoRef.current.play().catch(() => setPlaying(false)); setPlaying(true); }
                else { videoRef.current.pause(); setPlaying(false); }
              }}
            >{playing ? <Pause size={19} fill="currentColor" /> : <Play size={19} fill="currentColor" />}</button>
            <button className="icon-btn" title="Forward 5 seconds" aria-label="Forward 5 seconds" onClick={() => seekTo(playhead + 5)}><SkipForward size={17} /></button>
            <button className="icon-btn" title="Jump to end" aria-label="Jump to end" onClick={() => seekTo(total)}><SkipForward size={17} /></button>
          </div>
          <p className="stage-hint">Shortcuts: Space play/pause · S split · Delete remove selected</p>
        </div>

        <div
          className="editor-resizer editor-resizer-vertical editor-resizer-inspector"
          role="separator" aria-orientation="vertical" aria-label="Resize Inspector and Shorts player panels"
          title="Drag to resize the Inspector" aria-valuemin={190} aria-valuemax={420} aria-valuenow={Math.round(editorLayout.inspectorWidth)} tabIndex={0}
          onPointerDown={(event) => beginLayoutResize('inspector-width', event)}
          onPointerMove={(event) => moveLayoutResize('inspector-width', event)}
          onPointerUp={endLayoutResize} onPointerCancel={endLayoutResize}
          onKeyDown={(event) => keyboardResize('inspector-width', event)}
        />

        <aside className="inspector">
          <h3><Layers3 size={16} /> Inspector</h3>
          {!selectedItem ? <p className="hint">Select a block on the timeline to edit its properties.</p> : (
            <div className="inspector-fields">
              <Pill>{selected?.track}</Pill>
              {'path' in selectedItem && <label className="field"><span>Source</span><input readOnly value={selectedItem.path || ''} /></label>}
              {'sourceStart' in selectedItem && <label className="field"><span>Source in (s)</span><input type="number" step="0.1" value={selectedItem.sourceStart || 0} onChange={(event) => updateSelected({ sourceStart: Number(event.target.value) })} /></label>}
              {'duration' in selectedItem && <label className="field"><span>Duration (s)</span><input type="number" step="0.1" value={selectedItem.duration || 0} onChange={(event) => updateSelected({ duration: Number(event.target.value) })} /></label>}
              {'start' in selectedItem && <label className="field"><span>Start (s)</span><input type="number" step="0.1" value={selectedItem.start || 0} onChange={(event) => updateSelected({ start: Number(event.target.value) })} /></label>}
              {'end' in selectedItem && <label className="field"><span>End (s)</span><input type="number" step="0.1" value={selectedItem.end || 0} onChange={(event) => updateSelected({ end: Number(event.target.value) })} /></label>}
              {'volume' in selectedItem && <label className="field"><span>Volume</span><input type="range" min="0" max="1" step="0.05" value={selectedItem.volume ?? 0.5} onChange={(event) => updateSelected({ volume: Number(event.target.value) })} /></label>}
              {'x' in selectedItem && <><label className="field"><span>Position X</span><input type="range" min="0" max="1" step="0.01" value={selectedItem.x ?? 0.7} onChange={(event) => updateSelected({ x: Number(event.target.value) })} /></label><label className="field"><span>Position Y</span><input type="range" min="0" max="1" step="0.01" value={selectedItem.y ?? 0.15} onChange={(event) => updateSelected({ y: Number(event.target.value) })} /></label></>}
              <button className="ghost-btn" onClick={removeSelected}><Trash2 size={15} /> Remove item</button>
            </div>
          )}
          {exportOutput && <a className="primary block" href={mediaUrl('/media/file?path=' + encodeURIComponent(exportOutput) + '&download=true')} download><Download size={16} /> Download exported MP4</a>}
          {exportJob && <JobTracker jobId={exportJob} label="Rendering project" />}
        </aside>

        <div
          className="editor-resizer editor-resizer-horizontal editor-resizer-tablet"
          role="separator" aria-orientation="horizontal" aria-label="Resize Inspector height"
          title="Drag to resize the Inspector" aria-valuemin={220} aria-valuemax={700} aria-valuenow={Math.round(editorLayout.inspectorHeight)} tabIndex={0}
          onPointerDown={(event) => beginLayoutResize('tablet-inspector', event)}
          onPointerMove={(event) => moveLayoutResize('tablet-inspector', event)}
          onPointerUp={endLayoutResize} onPointerCancel={endLayoutResize}
          onKeyDown={(event) => keyboardResize('tablet-inspector', event)}
        />
        <div
          className="editor-resizer editor-resizer-horizontal editor-resizer-mobile-assets"
          role="separator" aria-orientation="horizontal" aria-label="Resize Media panel and Shorts player"
          title="Drag to resize the Media panel" aria-valuemin={140} aria-valuemax={520} aria-valuenow={Math.round(editorLayout.assetHeight)} tabIndex={0}
          onPointerDown={(event) => beginLayoutResize('mobile-asset-stage', event)}
          onPointerMove={(event) => moveLayoutResize('mobile-asset-stage', event)}
          onPointerUp={endLayoutResize} onPointerCancel={endLayoutResize}
          onKeyDown={(event) => keyboardResize('mobile-asset-stage', event)}
        />
        <div
          className="editor-resizer editor-resizer-horizontal editor-resizer-mobile-inspector"
          role="separator" aria-orientation="horizontal" aria-label="Resize Shorts player and Inspector panels"
          title="Drag to resize the Shorts player and Inspector" aria-valuemin={220} aria-valuemax={700} aria-valuenow={Math.round(editorLayout.inspectorHeight)} tabIndex={0}
          onPointerDown={(event) => beginLayoutResize('mobile-stage-inspector', event)}
          onPointerMove={(event) => moveLayoutResize('mobile-stage-inspector', event)}
          onPointerUp={endLayoutResize} onPointerCancel={endLayoutResize}
          onKeyDown={(event) => keyboardResize('mobile-stage-inspector', event)}
        />
      </div>
      <div
        className="editor-resizer editor-resizer-horizontal editor-resizer-timeline"
        role="separator" aria-orientation="horizontal" aria-label="Resize timeline height"
        title="Drag to resize the timeline" aria-valuemin={150} aria-valuemax={540} aria-valuenow={Math.round(editorLayout.timelineHeight)} tabIndex={0}
        onPointerDown={(event) => beginLayoutResize('timeline-height', event)}
        onPointerMove={(event) => moveLayoutResize('timeline-height', event)}
        onPointerUp={endLayoutResize} onPointerCancel={endLayoutResize}
        onKeyDown={(event) => keyboardResize('timeline-height', event)}
      />
      <div className="timeline-panel">
        <div className="timeline-toolbar">
          <div className="timeline-title"><strong>Timeline</strong> <Pill tone="muted">{formatClock(total)}</Pill><small>Move the playhead, click an asset to insert, or drag clips and overlays to position them.</small></div>
          <div className="timeline-actions">
            <div className="timeline-tools">
              <button className="icon-btn" title="Split clip at playhead" aria-label="Split clip" onClick={splitSelected}><Split size={15} /></button>
              <button className="icon-btn" title="Delete selected item" aria-label="Delete selected item" onClick={removeSelected}><Trash2 size={15} /></button>
            </div>
            <label>Zoom <input type="range" min="8" max="90" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} /></label>
          </div>
        </div>
        <div className="timeline-body">
          <div className="track-labels">
            <div className="ruler-spacer" />
            {(['video', 'stickers', 'audio'] as TrackKey[]).map((track) => (
              <div className="track-label" key={track}>
                {track === 'video' ? <Film size={14} /> : track === 'stickers' ? <ImagePlus size={14} /> : <Mic2 size={14} />}
                <span>{track}</span>
              </div>
            ))}
          </div>
          <div
            className="timeline-scroll"
            ref={timelineRef}
            onPointerDown={(event) => { scrubbingRef.current = true; scrub(event); }}
            onPointerMove={(event) => { if (scrubbingRef.current) scrub(event); }}
            onPointerUp={() => { scrubbingRef.current = false; }}
            onPointerLeave={() => { scrubbingRef.current = false; }}
          >
            <div className="timeline-content" style={{ width: Math.max(600, total * zoom + 120) }}>
              <div className="ruler">
                {Array.from({ length: Math.floor(total / 5) + 2 }, (_, index) => (
                  <span key={index} style={{ left: index * 5 * zoom }}>{formatClock(index * 5)}</span>
                ))}
              </div>
              {(['video', 'stickers', 'audio'] as TrackKey[]).map((track) => (
                <div className="track" key={track}>
                  <div
                    className="track-lane"
                    onDragOver={(event) => handleTimelineDragOver(track, event)}
                    onDrop={(event) => void handleTimelineDrop(track, event)}
                  >
                    {(timeline.tracks[track] as unknown as AnyItem[]).map((item, index) => {
                      const start = track === 'video'
                        ? timeline.tracks.video.slice(0, index).reduce((sum, part) => sum + part.duration, 0)
                        : (item.start || 0);
                      const duration = track === 'video' ? item.duration || 1 : Math.max(0.6, (item.end || item.start || 0) - (item.start || 0));
                      return (
                        <button
                          key={`${track}-${index}`}
                          className={`clip-block block-${track} ${selected?.track === track && selected.index === index ? 'selected' : ''}`}
                          style={{ left: start * zoom, width: Math.max(18, duration * zoom) }}
                          draggable
                          onPointerDown={(event) => event.stopPropagation()}
                          onDragStart={(event) => startTimelineItemDrag(event, track, index)}
                          onDragEnd={endTimelineDrag}
                          onClick={() => {
                            setSelected({ track, index });
                            setPlayhead(start + 0.05);
                          }}
                          title={`${item.label || item.path || 'Timeline item'} · drag to reposition`}
                        >
                          {item.label || (item.path || 'clip').split(/[\\/]/).pop()}
                        </button>
                      );
                    })}
                    {dropMarker?.track === track && <div className="timeline-drop-marker" style={{ left: dropMarker.time * zoom }} aria-hidden="true" />}
                  </div>
                </div>
              ))}
              <div className="playhead" style={{ left: playhead * zoom }} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

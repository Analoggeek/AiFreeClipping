import type { Timeline, VideoItem } from '../types';

type TimedItem = {
  start: number;
  end: number;
  auto_edit_clip_id?: string;
};

type VideoPlacement = { timeline: Timeline; index: number; start: number; changed: boolean };

const MIN_CLIP_DURATION = 0.2;
const MIN_SPLIT_OFFSET = 0.2;
const EPSILON = 1e-6;

function finite(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function durationOf(video: VideoItem): number {
  return Math.max(MIN_CLIP_DURATION, finite(video.duration, MIN_CLIP_DURATION));
}

function totalDuration(videos: VideoItem[]): number {
  return videos.reduce((sum, video) => sum + durationOf(video), 0);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function newVideoId(video: VideoItem): string {
  const token = globalThis.crypto?.randomUUID?.()
    || `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return `split-${video.id || video.clip_id || 'video'}-${token}`;
}

function shiftTimedTrack(items: TimedItem[], at: number, amount: number): void {
  for (const item of items) {
    const start = finite(item.start, 0);
    const end = finite(item.end, start);
    if (start >= at - EPSILON) {
      item.start = start + amount;
      item.end = end + amount;
    } else if (end > at + EPSILON) {
      item.end = end + amount;
    }
  }
}

/** Return the nearest cut boundary for a drag/drop position on the video track. */
export function insertionBoundaryAtTime(videos: VideoItem[], requestedTime: number): { index: number; time: number } {
  const time = clamp(finite(requestedTime, 0), 0, totalDuration(videos));
  let cursor = 0;
  for (let index = 0; index < videos.length; index++) {
    const duration = durationOf(videos[index]);
    if (time <= cursor + duration / 2) return { index, time: cursor };
    cursor += duration;
  }
  return { index: videos.length, time: cursor };
}

/** Insert a video at the playhead; split an existing clip when the playhead is inside it. */
export function insertVideoAtTime(current: Timeline, item: VideoItem, requestedTime: number): VideoPlacement {
  const next = structuredClone(current);
  const videos = next.tracks.video;
  const position = clamp(finite(requestedTime, 0), 0, totalDuration(videos));
  let cursor = 0;
  let index = videos.length;
  let start = cursor;
  let resolvedPosition = false;

  for (let videoIndex = 0; videoIndex < videos.length; videoIndex++) {
    const first = videos[videoIndex];
    const duration = durationOf(first);
    const end = cursor + duration;
    if (position <= cursor + EPSILON) {
      index = videoIndex;
      start = cursor;
      resolvedPosition = true;
      break;
    }
    if (position >= end - EPSILON) {
      cursor = end;
      continue;
    }

    const offset = position - cursor;
    if (offset <= MIN_SPLIT_OFFSET) {
      index = videoIndex;
      start = cursor;
      resolvedPosition = true;
      break;
    }
    if (duration - offset <= MIN_SPLIT_OFFSET) {
      index = videoIndex + 1;
      start = end;
      resolvedPosition = true;
      break;
    }

    const speedValue = finite(first.effects?.speed, 1);
    const speed = clamp(speedValue || 1, 0.25, 4);
    const sourceDuration = Math.max(0.05, finite(first.sourceDuration, duration * speed));
    const minSourceSlice = Math.min(MIN_SPLIT_OFFSET * speed, sourceDuration / 2);
    const sourceOffset = clamp(offset * speed, minSourceSlice, sourceDuration - minSourceSlice);
    const firstDuration = sourceOffset / speed;
    const second: VideoItem = {
      ...first,
      id: newVideoId(first),
      sourceStart: finite(first.sourceStart, 0) + sourceOffset,
      sourceDuration: sourceDuration - sourceOffset,
      duration: duration - firstDuration,
      label: `${first.label || 'Clip'} B`,
    };
    first.duration = firstDuration;
    first.sourceDuration = sourceOffset;
    videos.splice(videoIndex + 1, 0, second);
    index = videoIndex + 1;
    start = cursor + firstDuration;
    resolvedPosition = true;
    break;
  }

  if (!resolvedPosition) {
    index = videos.length;
    start = cursor;
  }
  videos.splice(index, 0, item);
  shiftTimedTrack(next.tracks.stickers, start, durationOf(item));
  shiftTimedTrack(next.tracks.audio, start, durationOf(item));
  return { timeline: next, index, start, changed: true };
}

function linkedVideoIndex(item: TimedItem, videos: VideoItem[], starts: number[]): number {
  if (item.auto_edit_clip_id) {
    const candidates = videos
      .map((video, index) => ({ video, index }))
      .filter(({ video }) => video.clip_id === item.auto_edit_clip_id);
    const time = finite(item.start, 0);
    const containing = candidates.find(({ video, index }) =>
      time >= starts[index] - EPSILON && time <= starts[index] + durationOf(video) + EPSILON,
    );
    return containing?.index ?? candidates[0]?.index ?? -1;
  }
  return -1;
}

/** Ripple-delete one video item and carry its linked overlays with the remaining clips. */
export function removeVideoAtIndex(current: Timeline, removedIndex: number): VideoPlacement {
  const videos = current.tracks.video;
  if (removedIndex < 0 || removedIndex >= videos.length) {
    return { timeline: current, index: removedIndex, start: 0, changed: false };
  }

  const oldStarts: number[] = [];
  let cursor = 0;
  videos.forEach((video) => { oldStarts.push(cursor); cursor += durationOf(video); });
  const newStarts = new Array<number>(videos.length);
  cursor = 0;
  videos.forEach((video, index) => {
    if (index === removedIndex) return;
    newStarts[index] = cursor;
    cursor += durationOf(video);
  });

  const next = structuredClone(current);
  next.tracks.video.splice(removedIndex, 1);
  const timedTracks: TimedItem[][] = [next.tracks.stickers, next.tracks.audio];
  for (const track of timedTracks) {
    for (const item of track) {
      const oldIndex = linkedVideoIndex(item, videos, oldStarts);
      if (oldIndex < 0 || oldIndex === removedIndex) continue;
      const shift = newStarts[oldIndex] - oldStarts[oldIndex];
      if (shift !== 0) {
        item.start += shift;
        item.end += shift;
      }
    }
  }
  const index = Math.min(removedIndex, next.tracks.video.length - 1);
  const start = index >= 0
    ? next.tracks.video.slice(0, index).reduce((sum, video) => sum + durationOf(video), 0)
    : 0;
  return { timeline: next, index, start, changed: true };
}

/** Reorder a video by dropping it near a cut; linked Auto Edit overlays follow their clip. */
export function moveVideoToTime(current: Timeline, fromIndex: number, requestedTime: number): VideoPlacement {
  const videos = current.tracks.video;
  if (fromIndex < 0 || fromIndex >= videos.length) {
    return { timeline: current, index: fromIndex, start: 0, changed: false };
  }
  const boundary = insertionBoundaryAtTime(videos, requestedTime);
  const adjustedIndex = boundary.index > fromIndex ? boundary.index - 1 : boundary.index;
  if (adjustedIndex === fromIndex) {
    const start = videos.slice(0, fromIndex).reduce((sum, video) => sum + durationOf(video), 0);
    return { timeline: current, index: fromIndex, start, changed: false };
  }

  const oldStarts: number[] = [];
  let cursor = 0;
  videos.forEach((video) => { oldStarts.push(cursor); cursor += durationOf(video); });
  const order = videos.map((_video, index) => index);
  const [moved] = order.splice(fromIndex, 1);
  order.splice(adjustedIndex, 0, moved);
  const newStarts = new Array<number>(videos.length);
  cursor = 0;
  order.forEach((oldIndex) => {
    newStarts[oldIndex] = cursor;
    cursor += durationOf(videos[oldIndex]);
  });

  const next = structuredClone(current);
  next.tracks.video = order.map((oldIndex) => next.tracks.video[oldIndex]);
  const timedTracks: TimedItem[][] = [next.tracks.stickers, next.tracks.audio];
  for (const track of timedTracks) {
    for (const item of track) {
      const oldIndex = linkedVideoIndex(item, videos, oldStarts);
      if (oldIndex < 0) continue;
      const shift = newStarts[oldIndex] - oldStarts[oldIndex];
      if (shift !== 0) {
        item.start += shift;
        item.end += shift;
      }
    }
  }
  const start = newStarts[moved];
  return { timeline: next, index: adjustedIndex, start, changed: true };
}

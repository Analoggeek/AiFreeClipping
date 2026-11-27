import type { AutoEditTimelineEdit, Timeline, VideoItem } from '../types';

function numberOr(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/** Append the Auto Edit recipe as editable timeline tracks, replacing any prior
 * Auto Edit for the same saved clip instead of duplicating it on every run. */
export function appendAutoEditTimeline(
  current: Timeline,
  edits: AutoEditTimelineEdit[],
): { timeline: Timeline; start: number } {
  const next = structuredClone(current);
  const editIds = new Set(edits.map((edit) => edit.clip_id));
  next.tracks.video = next.tracks.video.filter((item) => !item.clip_id || !editIds.has(item.clip_id));
  next.tracks.captions = next.tracks.captions.filter((item) => !item.auto_edit_clip_id || !editIds.has(item.auto_edit_clip_id));
  next.tracks.stickers = next.tracks.stickers.filter((item) => !item.auto_edit_clip_id || !editIds.has(item.auto_edit_clip_id));
  next.tracks.audio = next.tracks.audio.filter((item) => !item.auto_edit_clip_id || !editIds.has(item.auto_edit_clip_id));

  let cursor = next.tracks.video.reduce((sum, item) => sum + Math.max(0, item.duration || 0), 0);
  const firstStart = cursor;
  for (const edit of edits) {
    const sourceStart = numberOr(edit.source_start, 0);
    const sourceDuration = Math.max(0.05, numberOr(edit.source_duration, edit.duration));
    const effects = edit.effects || {};
    const speed = Math.max(0.25, Math.min(4, numberOr(effects.speed, 1)));
    const duration = Math.max(0.2, numberOr(edit.duration, sourceDuration / speed));
    const regions = edit.regions || [];
    const video: VideoItem = {
      id: `auto-${edit.clip_id}`,
      clip_id: edit.clip_id,
      path: edit.source_path,
      sourceStart,
      sourceDuration,
      duration,
      label: edit.title,
      region: edit.region || regions[0] || null,
      regions,
      region_layout: edit.region_layout || null,
      crop_path: edit.crop_path || [],
      effects,
      auto_edit: true,
    };
    next.tracks.video.push(video);

    for (const caption of edit.captions || []) {
      const text = String(caption.text ?? caption.word ?? '').trim();
      const start = Math.max(sourceStart, numberOr(caption.start, sourceStart));
      const end = Math.min(sourceStart + sourceDuration, numberOr(caption.end, start));
      if (!text || end <= start) continue;
      next.tracks.captions.push({
        text,
        start: cursor + (start - sourceStart) / speed,
        end: cursor + (end - sourceStart) / speed,
        kind: caption.kind || 'caption',
        auto_edit_clip_id: edit.clip_id,
      });
    }

    for (const audio of edit.audio || []) {
      const start = Math.max(0, numberOr(audio.start, 0));
      const end = Math.max(start + 0.05, numberOr(audio.end, start + 0.5));
      next.tracks.audio.push({
        ...audio,
        start: cursor + start,
        end: cursor + end,
        auto_edit_clip_id: edit.clip_id,
      });
    }

    for (const sticker of edit.stickers || []) {
      const start = Math.max(0, numberOr(sticker.start, 0));
      const end = Math.max(start + 0.05, numberOr(sticker.end, start + 1));
      next.tracks.stickers.push({
        ...sticker,
        start: cursor + start,
        end: cursor + end,
        auto_edit_clip_id: edit.clip_id,
      });
    }

    next.aspect = edit.aspect;
    next.resolution = edit.resolution;
    next.caption_style = (effects.caption_style as { preset: string } | undefined) || next.caption_style;
    cursor += duration;
  }
  return { timeline: next, start: firstStart };
}

import assert from 'node:assert/strict';
import test from 'node:test';
import { insertVideoAtTime, moveVideoToTime, removeVideoAtIndex } from '../src/lib/timelinePlacement.ts';

function timeline(video = []) {
  return {
    tracks: { video, captions: [], stickers: [], audio: [] },
    aspect: '9:16', resolution: 'source',
  };
}

const video = (id, duration, extra = {}) => ({
  id, path: `${id}.mp4`, sourceStart: 0, duration, label: id, ...extra,
});

test('inserting at the playhead splits a source and shifts later timed tracks', () => {
  const current = timeline([video('source', 10, { sourceDuration: 20, effects: { speed: 2 } })]);
  current.tracks.captions = [
    { text: 'before', start: 1, end: 1.3, auto_caption_video_id: 'source' },
    { text: 'after', start: 7, end: 7.4, auto_caption_video_id: 'source' },
  ];
  current.tracks.stickers = [{ path: 'sticker.png', start: 8, end: 12, x: 0.5, y: 0.5 }];
  current.tracks.audio = [{ path: 'music.wav', start: 0, end: 10, volume: 0.2 }];
  const added = video('inserted', 2);

  const result = insertVideoAtTime(current, added, 5);

  assert.deepEqual(result.timeline.tracks.video.map((item) => item.id), [
    'source', 'inserted', result.timeline.tracks.video[2].id,
  ]);
  assert.equal(result.index, 1);
  assert.equal(result.start, 5);
  assert.equal(result.timeline.tracks.video[0].duration, 5);
  assert.equal(result.timeline.tracks.video[2].sourceStart, 10);
  assert.equal(result.timeline.tracks.video[2].duration, 5);
  assert.equal(result.timeline.tracks.captions[0].start, 1);
  assert.equal(result.timeline.tracks.captions[1].start, 9);
  assert.equal(result.timeline.tracks.captions[1].auto_caption_video_id, result.timeline.tracks.video[2].id);
  assert.deepEqual(result.timeline.tracks.stickers[0], { path: 'sticker.png', start: 10, end: 14, x: 0.5, y: 0.5 });
  assert.deepEqual(result.timeline.tracks.audio[0], { path: 'music.wav', start: 0, end: 12, volume: 0.2 });
  assert.equal(current.tracks.video.length, 1, 'the original project is not mutated');
});

test('inserting at a cut adds one clip without splitting either neighbor', () => {
  const current = timeline([video('first', 2), video('second', 3)]);
  const result = insertVideoAtTime(current, video('new', 1), 2);

  assert.deepEqual(result.timeline.tracks.video.map((item) => item.id), ['first', 'new', 'second']);
  assert.deepEqual(result.timeline.tracks.video.map((item) => item.duration), [2, 1, 3]);
  assert.equal(result.start, 2);
});

test('ripple-deleting a video moves later linked overlays and keeps manual timing', () => {
  const current = timeline([video('first', 4), video('second', 3), video('third', 2)]);
  current.tracks.captions = [
    { text: 'third caption', start: 7.2, end: 7.8, auto_caption_video_id: 'third' },
    { text: 'manual', start: 6, end: 6.5 },
  ];

  const result = removeVideoAtIndex(current, 0);

  assert.deepEqual(result.timeline.tracks.video.map((item) => item.id), ['second', 'third']);
  assert.equal(result.timeline.tracks.captions[0].start, 3.2);
  assert.equal(result.timeline.tracks.captions[0].end, 3.8);
  assert.equal(result.timeline.tracks.captions[1].start, 6);
  assert.equal(current.tracks.video.length, 3, 'the original project is not mutated');
});

test('reordering moves clip-linked captions and Auto Edit overlays with their video', () => {
  const current = timeline([
    video('first', 4),
    video('second', 3, { clip_id: 'edit-2', auto_edit: true }),
    video('third', 2),
  ]);
  current.tracks.captions = [
    { text: 'third caption', start: 7.2, end: 7.8, auto_caption_video_id: 'third' },
    { text: 'second caption', start: 4.2, end: 4.8, auto_edit_clip_id: 'edit-2' },
    { text: 'manual', start: 4, end: 4.5 },
  ];
  current.tracks.audio = [{ path: 'sfx.wav', start: 6, end: 6.4, volume: 0.5, auto_edit_clip_id: 'edit-2' }];

  const result = moveVideoToTime(current, 2, 0);

  assert.deepEqual(result.timeline.tracks.video.map((item) => item.id), ['third', 'first', 'second']);
  assert.equal(result.index, 0);
  assert.equal(result.start, 0);
  const captions = result.timeline.tracks.captions;
  assert.ok(Math.abs(captions[0].start - 0.2) < 1e-9);
  assert.ok(Math.abs(captions[0].end - 0.8) < 1e-9);
  assert.equal(captions[1].start, 6.2);
  assert.equal(captions[1].end, 6.8);
  assert.equal(captions[2].start, 4);
  assert.equal(captions[2].end, 4.5);
  assert.equal(result.timeline.tracks.audio[0].start, 8);
  assert.ok(Math.abs(result.timeline.tracks.audio[0].end - 8.4) < 1e-9);
  assert.deepEqual(current.tracks.video.map((item) => item.id), ['first', 'second', 'third']);
});

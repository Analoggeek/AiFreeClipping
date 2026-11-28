import type { CaptionItem, Media, Timeline, VideoItem } from '../types';

export type TranscriptWord = { word: string; start: number; end: number; probability?: number };
export type TranscriptSegment = { start: number; end: number; text: string; words?: TranscriptWord[] };

const finite = (value: unknown, fallback: number) => {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
};

export function wordsFromTranscript(segments: TranscriptSegment[]): Array<TranscriptWord & { timing_source: 'whisper' | 'estimated' }> {
  const words: Array<TranscriptWord & { timing_source: 'whisper' | 'estimated' }> = [];
  for (const segment of segments) {
    const aligned = (segment.words || [])
      .map((word) => ({
        word: String(word.word || '').trim(),
        start: finite(word.start, finite(segment.start, 0)),
        end: finite(word.end, finite(segment.end, 0)),
        probability: word.probability,
      }))
      .filter((word) => word.word && word.end > word.start);
    if (aligned.length) {
      words.push(...aligned.map((word) => ({ ...word, timing_source: 'whisper' as const })));
      continue;
    }

    const tokens = String(segment.text || '').match(/\S+/g) || [];
    if (!tokens.length) continue;
    const start = finite(segment.start, 0);
    const end = Math.max(start + 0.12, finite(segment.end, start + tokens.length * 0.28));
    const weights = tokens.map((token) => Math.max(1, token.length));
    const totalWeight = weights.reduce((sum, weight) => sum + weight, 0);
    let consumed = 0;
    tokens.forEach((token, index) => {
      const wordStart = start + (end - start) * consumed / totalWeight;
      consumed += weights[index];
      const wordEnd = start + (end - start) * consumed / totalWeight;
      words.push({ word: token, start: wordStart, end: Math.max(wordStart + 0.08, wordEnd), timing_source: 'estimated' });
    });
  }
  return words.sort((left, right) => left.start - right.start || left.end - right.end);
}

function videoIdentity(video: VideoItem, index: number): string {
  return video.id || video.clip_id || `${video.media_id || video.path}@${finite(video.sourceStart, 0).toFixed(3)}:${index}`;
}

export function captionsForMedia(
  timeline: Timeline,
  source: Pick<Media, 'id' | 'path'>,
  segments: TranscriptSegment[],
): { captions: CaptionItem[]; videoIds: string[] } {
  const words = wordsFromTranscript(segments);
  const captions: CaptionItem[] = [];
  const videoIds: string[] = [];
  let timelineStart = 0;

  timeline.tracks.video.forEach((video, index) => {
    const matchesMedia = video.media_id === source.id || video.path === source.path;
    if (matchesMedia) {
      const videoId = videoIdentity(video, index);
      const speed = Math.max(0.25, Math.min(4, finite(video.effects?.speed, 1)));
      const sourceStart = Math.max(0, finite(video.sourceStart, 0));
      const sourceDuration = Math.max(0.05, finite(video.sourceDuration, finite(video.duration, 1) * speed));
      const sourceEnd = sourceStart + sourceDuration;
      let addedForVideo = false;

      for (const word of words) {
        const wordStart = Math.max(sourceStart, word.start);
        const wordEnd = Math.min(sourceEnd, word.end);
        if (!word.word || wordEnd <= wordStart) continue;
        captions.push({
          text: word.word,
          start: timelineStart + (wordStart - sourceStart) / speed,
          end: timelineStart + (wordEnd - sourceStart) / speed,
          kind: 'caption',
          auto_caption_video_id: videoId,
          timing_source: word.timing_source,
        });
        addedForVideo = true;
      }
      if (addedForVideo) videoIds.push(videoId);
    }
    timelineStart += Math.max(0, finite(video.duration, 0));
  });

  return { captions, videoIds };
}

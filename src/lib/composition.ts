export type NormalizedBox = { x: number; y: number; w: number; h: number };
export type CompositionAspect = '9:16' | '1:1' | '16:9' | 'source';

const STACK_LAYOUTS: Record<string, { axis: 'vertical' | 'horizontal'; first: number }> = {
  'top-game-bottom-player': { axis: 'vertical', first: 0.58 },
  'top-player-bottom-game': { axis: 'vertical', first: 0.42 },
  'side-by-side': { axis: 'horizontal', first: 0.62 },
};

function normalizedBox(input?: NormalizedBox | null, expandSmall = true): NormalizedBox {
  let x = Math.max(0, Math.min(0.95, Number(input?.x ?? 0)));
  let y = Math.max(0, Math.min(0.95, Number(input?.y ?? 0)));
  let w = Math.max(0.05, Math.min(1 - x, Number(input?.w ?? 1)));
  let h = Math.max(0.05, Math.min(1 - y, Number(input?.h ?? 1)));
  if (expandSmall && w * h < 0.25) {
    const scale = Math.min(Math.sqrt(0.25 / Math.max(1e-6, w * h)), 1 / Math.max(w, h));
    const nextW = Math.min(1, w * scale);
    const nextH = Math.min(1, h * scale);
    x = Math.max(0, Math.min(x - (nextW - w) / 2, 1 - nextW));
    y = Math.max(0, Math.min(y - (nextH - h) / 2, 1 - nextH));
    w = nextW;
    h = nextH;
  }
  return { x, y, w, h };
}

function frameRatio(video: HTMLVideoElement, aspect: CompositionAspect): number {
  if (aspect === '9:16') return 9 / 16;
  if (aspect === '1:1') return 1;
  if (aspect === '16:9') return 16 / 9;
  return video.videoWidth && video.videoHeight ? video.videoWidth / video.videoHeight : 9 / 16;
}

function drawCover(
  context: CanvasRenderingContext2D,
  video: HTMLVideoElement,
  box: NormalizedBox,
  x: number,
  y: number,
  width: number,
  height: number,
  expandSmall: boolean,
) {
  const crop = normalizedBox(box, expandSmall);
  const sourceX = crop.x * video.videoWidth;
  const sourceY = crop.y * video.videoHeight;
  const sourceWidth = Math.max(1, crop.w * video.videoWidth);
  const sourceHeight = Math.max(1, crop.h * video.videoHeight);
  const scale = Math.max(width / sourceWidth, height / sourceHeight);
  const drawWidth = sourceWidth * scale;
  const drawHeight = sourceHeight * scale;
  context.save();
  context.beginPath();
  context.rect(x, y, width, height);
  context.clip();
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = 'high';
  context.drawImage(
    video, sourceX, sourceY, sourceWidth, sourceHeight,
    x + (width - drawWidth) / 2, y + (height - drawHeight) / 2, drawWidth, drawHeight,
  );
  context.restore();
}

function drawFullFrame(
  context: CanvasRenderingContext2D,
  video: HTMLVideoElement,
  width: number,
  height: number,
  fit: 'blur-contain' | 'cover',
) {
  const contain = Math.min(width / video.videoWidth, height / video.videoHeight);
  const fitWidth = video.videoWidth * contain;
  const fitHeight = video.videoHeight * contain;
  const cover = Math.max(width / video.videoWidth, height / video.videoHeight);
  const coverWidth = video.videoWidth * cover;
  const coverHeight = video.videoHeight * cover;

  if (fit === 'cover') {
    context.save();
    context.beginPath();
    context.rect(0, 0, width, height);
    context.clip();
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = 'high';
    context.drawImage(video, (width - coverWidth) / 2, (height - coverHeight) / 2, coverWidth, coverHeight);
    context.restore();
    return;
  }

  context.save();
  context.beginPath();
  context.rect(0, 0, width, height);
  context.clip();
  context.filter = 'blur(18px)';
  context.drawImage(video, (width - coverWidth) / 2, (height - coverHeight) / 2, coverWidth, coverHeight);
  context.restore();

  context.save();
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = 'high';
  context.drawImage(video, (width - fitWidth) / 2, (height - fitHeight) / 2, fitWidth, fitHeight);
  context.restore();
}

/** Draw the same focus crop or multi-region arrangement that the FFmpeg renderer exports. */
export function drawVideoComposition(
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
  options: {
    aspect?: CompositionAspect;
    region?: NormalizedBox | null;
    regions?: NormalizedBox[];
    layout?: string | null;
    fit?: 'blur-contain' | 'cover';
  } = {},
) {
  const context = canvas.getContext('2d');
  if (!context) return;
  const ratio = frameRatio(video, options.aspect || '9:16');
  const width = 480;
  const height = Math.max(2, Math.round(width / ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  context.fillStyle = '#05070e';
  context.fillRect(0, 0, width, height);
  if (!video.videoWidth || !video.videoHeight || video.readyState < 2) return;

  const regions = (options.regions || []).filter(Boolean);
  const layout = options.layout || '';
  const fit = options.fit || 'blur-contain';
  const split = STACK_LAYOUTS[layout];
  if (split && regions.length >= 2) {
    if (split.axis === 'vertical') {
      const firstHeight = Math.max(2, Math.round(height * split.first / 2) * 2);
      const secondHeight = height - firstHeight;
      drawCover(context, video, regions[0], 0, 0, width, firstHeight, false);
      drawCover(context, video, regions[1], 0, firstHeight, width, secondHeight, false);
    } else {
      const firstWidth = Math.max(2, Math.round(width * split.first / 2) * 2);
      const secondWidth = width - firstWidth;
      drawCover(context, video, regions[0], 0, 0, firstWidth, height, false);
      drawCover(context, video, regions[1], firstWidth, 0, secondWidth, height, false);
    }
    return;
  }

  if (layout === 'square-player-full-game' && regions.length >= 2) {
    drawFullFrame(context, video, width, height, 'blur-contain');
    const size = Math.max(2, Math.round(Math.min(width, height) * 0.34 / 2) * 2);
    const inset = Math.max(2, Math.round(Math.min(width, height) * 0.04 / 2) * 2);
    drawCover(context, video, regions[1], inset, inset, size, size, false);
    context.save();
    context.strokeStyle = 'rgba(255,255,255,.92)';
    context.lineWidth = Math.max(2, width / 120);
    context.strokeRect(inset, inset, size, size);
    context.restore();
    return;
  }

  const focus = options.region || regions[0];
  if (focus && (focus.x !== 0 || focus.y !== 0 || focus.w !== 1 || focus.h !== 1)) {
    if (fit === 'cover') {
      drawCover(context, video, focus, 0, 0, width, height, true);
      return;
    }
    const crop = normalizedBox(focus);
    const sourceX = crop.x * video.videoWidth;
    const sourceY = crop.y * video.videoHeight;
    const sourceWidth = Math.max(1, crop.w * video.videoWidth);
    const sourceHeight = Math.max(1, crop.h * video.videoHeight);
    const cover = Math.max(width / sourceWidth, height / sourceHeight);
    const coverWidth = sourceWidth * cover;
    const coverHeight = sourceHeight * cover;
    context.save();
    context.beginPath();
    context.rect(0, 0, width, height);
    context.clip();
    context.filter = 'blur(18px)';
    context.drawImage(video, sourceX, sourceY, sourceWidth, sourceHeight,
      (width - coverWidth) / 2, (height - coverHeight) / 2, coverWidth, coverHeight);
    context.restore();
    const contain = Math.min(width / sourceWidth, height / sourceHeight);
    const fitWidth = sourceWidth * contain;
    const fitHeight = sourceHeight * contain;
    context.drawImage(video, sourceX, sourceY, sourceWidth, sourceHeight,
      (width - fitWidth) / 2, (height - fitHeight) / 2, fitWidth, fitHeight);
    return;
  }
  drawFullFrame(context, video, width, height, fit);
}

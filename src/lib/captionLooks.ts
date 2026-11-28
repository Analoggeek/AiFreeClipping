import type { CaptionStyleSettings } from '../types';

export const CAPTION_FONT_FAMILIES = [
  'Arial', 'Arial Black', 'Arial Narrow', 'Arial Rounded MT Bold', 'Avenir', 'Avenir Next',
  'Baskerville', 'Bebas Neue', 'Bookman Old Style', 'Calibri', 'Cambria', 'Candara',
  'Century Gothic', 'Comic Sans MS', 'Consolas', 'Constantia', 'Courier New', 'DejaVu Sans',
  'DejaVu Serif', 'Futura', 'Garamond', 'Georgia', 'Gill Sans', 'Helvetica', 'Helvetica Neue',
  'Impact', 'Inter', 'Lato', 'Liberation Sans', 'Lucida Console', 'Lucida Sans', 'Montserrat',
  'Noto Sans', 'Open Sans', 'Oswald', 'Palatino Linotype', 'Poppins', 'Roboto', 'Segoe UI',
  'Tahoma', 'Times New Roman', 'Trebuchet MS', 'Ubuntu', 'Verdana',
] as const;

const PALETTES = [
  { id: 'ice', name: 'Ice', primary: '#F4FCFF', outline: '#0B3142', background: '#082B3B' },
  { id: 'sun', name: 'Solar', primary: '#FFE66D', outline: '#522400', background: '#2B1605' },
  { id: 'electric', name: 'Electric', primary: '#69F3FF', outline: '#19103E', background: '#15112D' },
  { id: 'rose', name: 'Rose', primary: '#FFF0F7', outline: '#65143D', background: '#351023' },
  { id: 'lime', name: 'Lime', primary: '#E8FF69', outline: '#283600', background: '#182203' },
  { id: 'violet', name: 'Violet', primary: '#E8D6FF', outline: '#35145A', background: '#1F1033' },
  { id: 'ember', name: 'Ember', primary: '#FFF1E7', outline: '#651D17', background: '#350D0A' },
  { id: 'mono', name: 'Mono', primary: '#FFFFFF', outline: '#080808', background: '#080808' },
] as const;

type LookDesign = {
  id: string;
  name: string;
  category: string;
  preset: string;
  font_family: string;
  font_size: number;
  bold: boolean;
  italic?: boolean;
  uppercase?: boolean;
  outline: number;
  shadow: number;
  background_opacity: number;
  spacing?: number;
};

const DESIGNS: LookDesign[] = [
  { id: 'punch-pop', name: 'Punch Pop', category: 'Bold', preset: 'hype', font_family: 'Arial Black', font_size: 72, bold: true, uppercase: true, outline: 5, shadow: 2, background_opacity: 0 },
  { id: 'neon-edge', name: 'Neon Edge', category: 'Neon', preset: 'hype', font_family: 'Impact', font_size: 76, bold: true, uppercase: true, outline: 3, shadow: 5, background_opacity: 0 },
  { id: 'karaoke-beat', name: 'Karaoke Beat', category: 'Karaoke', preset: 'karaoke', font_family: 'Arial Black', font_size: 68, bold: true, uppercase: true, outline: 4, shadow: 1, background_opacity: 0 },
  { id: 'clean-serif', name: 'Clean Serif', category: 'Minimal', preset: 'minimal', font_family: 'Georgia', font_size: 59, bold: true, outline: 1, shadow: 1, background_opacity: 0 },
  { id: 'pill-box', name: 'Pill Box', category: 'Box', preset: 'premium', font_family: 'Montserrat', font_size: 58, bold: true, outline: 0, shadow: 1, background_opacity: 0.72 },
  { id: 'subtitle-bar', name: 'Subtitle Bar', category: 'Box', preset: 'minimal', font_family: 'Arial', font_size: 54, bold: false, outline: 0, shadow: 0, background_opacity: 0.78 },
  { id: 'block-shadow', name: 'Block Shadow', category: 'Bold', preset: 'hype', font_family: 'Impact', font_size: 76, bold: true, uppercase: true, outline: 2, shadow: 6, background_opacity: 0 },
  { id: 'editorial-italic', name: 'Editorial Italic', category: 'Editorial', preset: 'premium', font_family: 'Georgia', font_size: 62, bold: false, italic: true, outline: 1, shadow: 2, background_opacity: 0 },
  { id: 'retro-arcade', name: 'Retro Arcade', category: 'Retro', preset: 'karaoke', font_family: 'Courier New', font_size: 61, bold: true, uppercase: true, outline: 4, shadow: 3, background_opacity: 0 },
  { id: 'comic-burst', name: 'Comic Burst', category: 'Playful', preset: 'hype', font_family: 'Comic Sans MS', font_size: 68, bold: true, uppercase: true, outline: 5, shadow: 3, background_opacity: 0 },
  { id: 'sport-heavy', name: 'Sport Heavy', category: 'Bold', preset: 'hype', font_family: 'Oswald', font_size: 73, bold: true, uppercase: true, outline: 4, shadow: 2, background_opacity: 0, spacing: 1 },
  { id: 'marker-strip', name: 'Marker Strip', category: 'Box', preset: 'minimal', font_family: 'Arial Black', font_size: 58, bold: true, outline: 0, shadow: 1, background_opacity: 0.82 },
  { id: 'clean-outline', name: 'Clean Outline', category: 'Minimal', preset: 'minimal', font_family: 'Helvetica Neue', font_size: 58, bold: true, outline: 2, shadow: 0, background_opacity: 0 },
  { id: 'cinematic', name: 'Cinematic', category: 'Editorial', preset: 'premium', font_family: 'Garamond', font_size: 62, bold: false, italic: true, outline: 2, shadow: 3, background_opacity: 0.22 },
  { id: 'sticker-caption', name: 'Sticker Caption', category: 'Playful', preset: 'hype', font_family: 'Arial Rounded MT Bold', font_size: 64, bold: true, outline: 2, shadow: 2, background_opacity: 0.48 },
  { id: 'condensed', name: 'Condensed', category: 'Bold', preset: 'hype', font_family: 'Arial Narrow', font_size: 78, bold: true, uppercase: true, outline: 4, shadow: 1, background_opacity: 0, spacing: 0.5 },
  { id: 'mono-tech', name: 'Mono Tech', category: 'Retro', preset: 'minimal', font_family: 'Consolas', font_size: 56, bold: true, outline: 2, shadow: 2, background_opacity: 0.28, spacing: 0.8 },
];

export type CaptionLook = {
  id: string;
  name: string;
  category: string;
  palette: string;
  style: Partial<CaptionStyleSettings>;
};

export const CAPTION_LOOKS: CaptionLook[] = DESIGNS.flatMap((design) => PALETTES.map((palette) => ({
  id: `${design.id}-${palette.id}`,
  name: `${design.name} · ${palette.name}`,
  category: design.category,
  palette: palette.name,
  style: {
    preset: design.preset,
    template_id: `${design.id}-${palette.id}`,
    font_family: design.font_family,
    font_size: design.font_size,
    primary_color: palette.primary,
    outline_color: palette.outline,
    background_color: palette.background,
    background_opacity: design.background_opacity,
    bold: design.bold,
    italic: Boolean(design.italic),
    uppercase: Boolean(design.uppercase),
    outline: design.outline,
    shadow: design.shadow,
    spacing: design.spacing || 0,
  },
})));

export const CAPTION_LOOK_CATEGORIES = ['All', ...new Set(CAPTION_LOOKS.map((look) => look.category))];

if (CAPTION_LOOKS.length !== 136 || CAPTION_FONT_FAMILIES.length !== 44) {
  throw new Error('Caption look and font catalogue sizes must remain 136 looks and 44 font families.');
}

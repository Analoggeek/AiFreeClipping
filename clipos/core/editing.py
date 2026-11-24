"""Shared v2.5 editing preferences: one source for wizard and advanced exports."""
from __future__ import annotations
import json
import platform
from ..video.renderer import RenderSettings
from ..video.presets import apply_preset


def enabled(value):
    return str(value).lower() not in ('0', 'false', '', 'none', 'off')


def render_settings(db, overrides=None):
    data = db.get_settings()
    data.update(overrides or {})
    aspect = data.get('aspect_ratio', data.get('default_aspect', '9:16'))
    rs = apply_preset(RenderSettings.for_aspect(aspect), data.get('editing_preset','gaming'))
    rs.caption_style = data.get('caption_style',rs.caption_style)
    rs.caption_size = int(data.get('caption_size',48))
    rs.caption_font = data.get('caption_font','')
    rs.caption_position = 'split' if rs.editing_preset == 'gaming' else data.get('caption_position','bottom')
    rs.show_captions = enabled(data.get('auto_caption',True))
    for field in ('caption_stroke','fps','bitrate_kbps'):
        if field in data: setattr(rs,field,int(data[field]))
    for field in ('caption_shadow','caption_background','remove_silence','normalize_audio','noise_reduction','gaming_enhance'):
        if field in data: setattr(rs,field,enabled(data[field]))
    for field in ('silence_threshold_db','min_silence_duration','bgm_volume'):
        if field in data: setattr(rs,field,float(data[field]))
    rs.codec = data.get('codec','h264')
    rs.threads = int(data.get('processing_threads',0))
    rs.low_memory = enabled(data.get('low_memory_mode',False))
    rs.encoder_preference = data.get('encoder',data.get('use_gpu','auto'))
    if str(rs.encoder_preference).lower() in ('false','0'): rs.encoder_preference='cpu'
    # OS-specific native encoder selection remains capability-probed at render.
    rs.platform_profile = 'macOS / VideoToolbox' if platform.system()=='Darwin' else ('Windows / NVENC · QSV · CPU' if platform.system()=='Windows' else 'Linux / detected hardware')
    rs.cpu_preset = 'veryfast' if rs.low_memory else 'fast'
    mode = data.get('framing_mode','auto')
    rs.auto_facecam = mode == 'auto'
    if mode == 'gameplay': rs.facecam_rect = None
    for key in ('facecam_rect','gameplay_rect'):
        if key in data:
            value = data[key]
            setattr(rs,key,tuple(json.loads(value) if isinstance(value,str) else value) if value is not None else None)
    if not rs.auto_facecam and rs.facecam_rect and tuple(rs.gameplay_rect)==(0.,0.,1.,1.):
        from ..video.presets import gameplay_outside
        rs.gameplay_rect = gameplay_outside(rs.facecam_rect)
    return rs

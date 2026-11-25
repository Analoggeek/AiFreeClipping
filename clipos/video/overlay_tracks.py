"""Validated dedicated caption, color-effect and cross-dissolve timeline lanes."""
from __future__ import annotations

from ..captions.caption_engine import CAPTION_STYLES
from ..captions.customization import customize_style, offset_cues

KINDS = ('caption', 'effect', 'transition')


def validate_overlay(lane, item, number):
    number(item.at, 0, 21600); number(item.length, .001, 21600)
    if item.at + item.length > 21600:
        raise ValueError('Overlay exceeds the six-hour timeline limit')
    for value in (item.source_in,item.speed,item.gain,item.opacity,item.fade_in,item.fade_out,item.rotation,
                  item.x,item.y,item.w,item.h):number(value,-180,21600)
    if (item.media_id != '' or item.group_id != '' or item.source_in != 0 or item.speed != 1
            or item.gain != 1 or item.opacity != 1 or item.opacity_keys != [] or item.gain_keys != []
            or item.fade_in or item.fade_out or item.rotation
            or (item.x,item.y,item.w,item.h) != (0.,0.,1.,1.)):
        raise ValueError('Overlay lanes use timeline start/length and their dedicated controls, not media geometry or automation')
    number(item.brightness, -1, 1); number(item.contrast, 0, 3); number(item.saturation, 0, 3)
    if lane.kind != 'effect' and (item.brightness,item.contrast,item.saturation) != (0.,1.,1.):
        raise ValueError('Color effects belong on the effect lane')
    if not isinstance(item.text,str) or len(item.text)>1000:
        raise ValueError('Caption text is limited to 1000 characters')
    if lane.kind == 'caption':
        if not item.text.strip() or not isinstance(item.caption_style,str) or item.caption_style not in CAPTION_STYLES:
            raise ValueError('Choose caption text and a registered caption preset')
    elif item.text or item.caption_options:
        raise ValueError('Text and caption options require a caption lane')
    validate_caption_options(item.caption_options)
    for value in (item.incoming_id,item.outgoing_id):
        if not isinstance(value,str) or len(value)>128:
            raise ValueError('Invalid transition reference')
    if lane.kind != 'transition' and (item.incoming_id or item.outgoing_id):
        raise ValueError('Video references require a transition lane')


def validate_caption_options(options):
    if not isinstance(options,dict):raise ValueError('Caption options must be an object')
    allowed={'primary_override','highlight_override','outline_override','animation_override',
             'alignment_override','timing_offset','font_override','size_override',
             'position_override','stroke_override','shadow_override','background_override'}
    if not options.keys()<=allowed:raise ValueError('Unsupported caption option')
    customize_style(CAPTION_STYLES['bold_viral'], **{
        key:options.get(source,'') for key,source in [('primary','primary_override'),('highlight','highlight_override'),
        ('outline','outline_override'),('animation','animation_override'),('alignment','alignment_override')]})
    offset_cues([],options.get('timing_offset',0.))
    font=options.get('font_override','')
    if not isinstance(font,str) or len(font)>128 or any(c in font for c in '\r\n,{}\\'):
        raise ValueError('Invalid caption font family')
    for key,low,high in [('size_override',12,160),('stroke_override',0,12)]:
        if key in options and (type(options[key]) is not int or not low<=options[key]<=high):
            raise ValueError('Caption size/stroke out of range')
    if options.get('position_override','') not in ('','top','middle','bottom','split'):
        raise ValueError('Invalid caption position')
    for key in ('shadow_override','background_override'):
        if key in options and type(options[key]) is not bool:raise ValueError('Caption toggles must be boolean')


def validate_transitions(project):
    videos={item.id:((row,index),lane,item) for row,lane in enumerate(project.lanes) if lane.kind=='video'
            for index,item in enumerate(lane.items)}
    incoming_ids=set()
    for lane in project.lanes:
        if lane.kind!='transition':continue
        for transition in lane.items:
            if transition.incoming_id not in videos or transition.outgoing_id not in videos:
                raise ValueError('Dissolve requires existing incoming/outgoing video items; remove its transition before removing a referenced video')
            incoming_order,_,incoming=videos[transition.incoming_id]
            outgoing_order,_,outgoing=videos[transition.outgoing_id]
            if incoming_order<=outgoing_order or incoming.at<=outgoing.at:
                raise ValueError('Incoming video must start later and composite above the outgoing video')
            overlap=min(incoming.at+incoming.duration,outgoing.at+outgoing.duration)-incoming.at
            if abs(transition.at-incoming.at)>1e-6 or transition.duration>overlap+1e-6:
                raise ValueError('Dissolve must begin at the incoming video start and fit the actual overlap; update/remove the transition before changing these boundaries')
            if transition.incoming_id in incoming_ids:
                raise ValueError('Only one dissolve per incoming video is supported')
            incoming_ids.add(transition.incoming_id)


def dissolve_duration(project, item_id):
    enabled_video={item.id for lane in project.lanes if lane.enabled and lane.kind=='video' for item in lane.items}
    for lane in project.lanes:
        if lane.kind=='transition' and lane.enabled:
            for item in lane.items:
                if item.incoming_id==item_id and item.outgoing_id in enabled_video:
                    return item.duration
    return 0.


def write_caption(path,item,width,height):
    """One lane item, clipped to its actual timeline range; no fabricated word times."""
    from dataclasses import replace
    from ..captions.caption_engine import CaptionCue, write_ass
    style=CAPTION_STYLES[item.caption_style]
    options=dict(item.caption_options)
    cues=offset_cues([CaptionCue(item.at,item.at+item.duration,item.text)],options.pop('timing_offset',0.))
    cues=[replace(c,start=max(item.at,c.start),end=min(item.at+item.duration,c.end)) for c in cues
          if max(item.at,c.start)<min(item.at+item.duration,c.end)]
    style=replace(style,size=max(8,round(style.size*width/1080)),margin_v=max(4,round(style.margin_v*height/1920)))
    if options.get('size_override'):options['size_override']=max(8,round(options['size_override']*width/1080))
    return write_ass(path,cues,style,width,height,**options)

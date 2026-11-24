"""Multi-source, overlapping video/audio project model, separate from legacy Timeline.

This is an additive editing engine. It does not claim professional automation,
transitions, caption lanes or real-time multitrack A/V playback.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import uuid

from ..core.ffmpeg import probe
from .timeline import Timeline


def uid():
    return uuid.uuid4().hex


@dataclass
class Media:
    id: str
    path: str
    duration: float
    has_video: bool
    has_audio: bool


@dataclass
class Item:
    id: str
    media_id: str
    at: float
    source_in: float
    length: float  # source seconds; output length = length/speed
    speed: float = 1.
    gain: float = 1.
    x: float = 0.
    y: float = 0.
    w: float = 1.
    h: float = 1.
    opacity: float = 1.
    fade_in: float = 0.  # output/timeline seconds
    fade_out: float = 0.
    opacity_keys: list = field(default_factory=list)
    gain_keys: list = field(default_factory=list)
    group_id: str = ""

    @property
    def duration(self):
        return self.length/self.speed


@dataclass
class Lane:
    id: str
    name: str
    kind: str  # video or audio
    items: list[Item] = field(default_factory=list)
    enabled: bool = True
    locked: bool = False


@dataclass
class MultitrackProject:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    media: list[Media] = field(default_factory=list)
    lanes: list[Lane] = field(default_factory=list)
    recovered_from: str | None = None
    _undo: list[dict] = field(default_factory=list, repr=False)
    _redo: list[dict] = field(default_factory=list, repr=False)

    @property
    def duration(self):
        return max((item.at+item.duration for lane in self.lanes if lane.enabled for item in lane.items), default=0.)

    def to_dict(self):
        return {'schema':'clipos.multitrack.v1','width':self.width,'height':self.height,'fps':self.fps,
                'media':[asdict(m) for m in self.media], 'lanes':[asdict(lane) for lane in self.lanes]}

    def validate(self):
        def number(value,lo,hi):
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:
                raise ValueError('Invalid multitrack numeric value')
        for value in (self.width,self.height):
            if type(value) is not int or value%2 or not 16<=value<=7680:raise ValueError('Invalid canvas size')
        if type(self.fps) is not int or not 1<=self.fps<=120:raise ValueError('Invalid project fps')
        if len(self.media)>64 or len(self.lanes)>64 or sum(len(l.items) for l in self.lanes)>256:
            raise ValueError('Project exceeds supported lane/media/item limits')
        ids=set()
        def identity(value):
            if not isinstance(value,str) or not 1<=len(value)<=128 or value in ids:raise ValueError('Invalid/duplicate project ID')
            ids.add(value)
        sources={}
        for media in self.media:
            identity(media.id)
            if not isinstance(media.path,str) or not media.path or len(media.path)>4096 or '://' in media.path or not Path(media.path).is_absolute():
                raise ValueError('Media must be a local file path')
            number(media.duration,.001,1e7)
            if type(media.has_video) is not bool or type(media.has_audio) is not bool:raise ValueError('Invalid source type')
            sources[media.id]=media
        groups={}
        for lane in self.lanes:
            identity(lane.id)
            if lane.kind not in ('video','audio'):raise ValueError('Unsupported track kind')
            if not isinstance(lane.name,str) or not 1<=len(lane.name)<=128:raise ValueError('Invalid track name')
            if type(lane.enabled) is not bool or type(lane.locked) is not bool:raise ValueError('Invalid track state')
            for item in lane.items:
                identity(item.id)
                if item.media_id not in sources:raise ValueError('Missing media reference')
                if not isinstance(item.group_id,str) or len(item.group_id)>128:raise ValueError('Invalid link group')
                if item.group_id:
                    source,lanes=groups.setdefault(item.group_id,(item.media_id,set()))
                    if source!=item.media_id or lane.id in lanes:raise ValueError('Link group must contain same-source items on separate tracks')
                    lanes.add(lane.id)
                media=sources[item.media_id]
                if not (media.has_video if lane.kind=='video' else media.has_audio):raise ValueError('Media has no required stream')
                number(item.at,0,1e7);number(item.source_in,0,media.duration)
                number(item.length,.001,media.duration);number(item.speed,.25,4);number(item.gain,0,4)
                number(item.fade_in,0,item.duration);number(item.fade_out,0,item.duration)
                if item.fade_in+item.fade_out>item.duration+1e-6:raise ValueError('Fades exceed item duration')
                for name,limit,kind in [('opacity_keys',1,'video'),('gain_keys',4,'audio')]:
                    keys=getattr(item,name)
                    if not isinstance(keys,list) or len(keys)>64:raise ValueError('At most 64 keyframes per curve')
                    if keys and lane.kind!=kind:raise ValueError('Keyframe property incompatible with track')
                    previous=-1.
                    for key in keys:
                        if not isinstance(key,(list,tuple)) or len(key)!=2:raise ValueError('Invalid keyframe')
                        moment,value=key;number(moment,0,item.duration);number(value,0,limit)
                        if moment<=previous or (previous>=0 and moment-previous<1e-6):raise ValueError('Keyframes must be ordered at least one microsecond apart')
                        previous=moment
                if lane.kind=='video' and item.gain!=1:raise ValueError('Set gain on the independent audio track, not video')
                if lane.kind=='audio' and (item.x,item.y,item.w,item.h,item.opacity)!=(0.,0.,1.,1.,1.):
                    raise ValueError('Audio tracks do not have video geometry/opacity')
                if item.source_in+item.length>media.duration+1e-6:raise ValueError('Trim exceeds media duration')
                for value in (item.x,item.y,item.opacity):number(value,0,1)
                for value in (item.w,item.h):number(value,.01,1)
                if item.x+item.w>1.000001 or item.y+item.h>1.000001:raise ValueError('Layer exceeds canvas')
        return self

    @classmethod
    def from_dict(cls,data):
        if not isinstance(data,dict) or data.get('schema')!='clipos.multitrack.v1':raise ValueError('Unsupported multitrack schema')
        try:
            if not isinstance(data.get('media'),list) or not isinstance(data.get('lanes'),list):raise ValueError('Invalid project lists')
            project=cls(width=data['width'],height=data['height'],fps=data['fps'],
                media=[Media(**m) for m in data['media']],
                lanes=[Lane(**{**lane,'items':[Item(**item) for item in lane['items']]}) for lane in data['lanes']])
            return project.validate()
        except (TypeError,KeyError,AttributeError) as exc:
            raise ValueError('Malformed multitrack project') from exc

    @classmethod
    def _read(cls,path):
        with Path(path).open('rb') as stream:raw=stream.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise ValueError('Project exceeds 8 MiB')
        return cls.from_dict(json.loads(raw))

    @classmethod
    def load(cls,path):
        try:return cls._read(path)
        except (ValueError,OSError) as primary:
            try:project=cls._read(Timeline.backup_path(path))
            except (ValueError,OSError):raise ValueError(f'Cannot restore multitrack project: {primary}') from primary
            project.recovered_from=str(Timeline.backup_path(path))
            return project

    def save(self,path):
        self.validate()
        path=Path(path)
        # Never replace source media with a project file.
        reserved={Path(m.path).resolve() for m in self.media}
        if path.resolve() in reserved or Timeline.backup_path(path).resolve() in reserved:
            raise ValueError('Project path cannot overwrite media')
        payload=json.dumps(self.to_dict(),indent=2,allow_nan=False).encode()
        if len(payload)>8*1024*1024:raise ValueError('Project exceeds 8 MiB')
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            try:previous=self._read(path)
            except (ValueError,OSError):previous=None
            if previous:Timeline._atomic_write(Timeline.backup_path(path),json.dumps(previous.to_dict()).encode())
        Timeline._atomic_write(path,payload)
        self.recovered_from=None
        return path

    def edit(self,operation):
        """Validate changes on a copy; exceptions leave live state/history intact."""
        before=self.to_dict()
        draft=self.from_dict(before)
        result=operation(draft)
        draft.validate()
        self.width,self.height,self.fps=draft.width,draft.height,draft.fps
        self.media,self.lanes=draft.media,draft.lanes
        self._undo.append(before);del self._undo[:-50];self._redo.clear()
        return result

    def undo(self):
        if not self._undo:return False
        self._redo.append(self.to_dict())
        previous=self.from_dict(self._undo.pop())
        self.width,self.height,self.fps=previous.width,previous.height,previous.fps
        self.media,self.lanes=previous.media,previous.lanes
        return True

    def redo(self):
        if not self._redo:return False
        self._undo.append(self.to_dict())
        following=self.from_dict(self._redo.pop())
        self.width,self.height,self.fps=following.width,following.height,following.fps
        self.media,self.lanes=following.media,following.lanes
        return True

    def import_media(self,path,at=0.):
        path=Path(path).expanduser().resolve()
        if not path.is_file():raise FileNotFoundError(f'Media file not found: {path}')
        info=probe(path)
        media=Media(uid(),str(path),info.duration,info.has_video,info.has_audio)
        group=uid() if info.has_video and info.has_audio else ''
        def operation(project):
            project.media.append(media)
            for kind,available in [('video',media.has_video),('audio',media.has_audio)]:
                if available:project.lanes.append(Lane(uid(),path.stem+' · '+kind,kind,
                    [Item(uid(),media.id,at,0,media.duration,group_id=group)]))
        self.edit(operation)
        return media.id

    def _linked_targets(self,lane_id,item_id):
        _,selected=self.find(lane_id,item_id)
        targets=[(lane,item) for lane in self.lanes for item in lane.items
                 if item.id==item_id or (selected.group_id and item.group_id==selected.group_id)]
        if any(lane.locked for lane,item in targets):raise ValueError('A linked track is locked; no items changed')
        return targets

    def change_item(self,lane_id,item_id,*,linked=False,**values):
        allowed={'at','source_in','length','speed','gain','x','y','w','h','opacity','fade_in','fade_out'}
        if not values.keys()<=allowed:raise ValueError('Unsupported item properties')
        def operation(project):
            lane,item=project.find(lane_id,item_id)
            if lane.locked:raise ValueError('Track is locked')
            timing={'at','source_in','length','speed'} & values.keys()
            targets=project._linked_targets(lane_id,item_id) if linked and timing else [(lane,item)]
            # Source trims/speed require aligned siblings; never pretend an already
            # independently edited pair is in sync. Pure moves preserve offsets.
            if timing-{'at'}:
                for _,other in targets:
                    if any(abs(getattr(other,key)-getattr(item,key))>1e-6 for key in ('at','source_in','length','speed')):
                        raise ValueError('Linked items are not aligned; edit independently or undo earlier unlinked changes')
            offsets={key:values[key]-getattr(item,key) for key in timing}
            for _,other in targets:
                for key,delta in offsets.items():setattr(other,key,getattr(other,key)+delta)
            for key,value in values.items():
                if key not in timing:setattr(item,key,value)
        self.edit(operation)

    def find(self,lane_id,item_id):
        for lane in self.lanes:
            if lane.id==lane_id:
                for item in lane.items:
                    if item.id==item_id:return lane,item
        raise ValueError('Track/item not found')

    def keyframe(self,lane_id,item_id,time,value=None,*,clear=False):
        """File-local output-time linear opacity/video or gain/audio automation."""
        def operation(project):
            lane,item=project.find(lane_id,item_id)
            if lane.locked:raise ValueError('Track is locked')
            field='opacity_keys' if lane.kind=='video' else 'gain_keys'
            if isinstance(time,bool) or not isinstance(time,(int,float)) or not math.isfinite(time) or not 0<=time<=item.duration:
                raise ValueError('Keyframe cursor must be inside selected item')
            keys=getattr(item,field)
            if clear:keys=[]
            else:
                keys=[key for key in keys if abs(key[0]-time)>1e-6]
                if value is not None:keys.append([time,value])
                keys.sort(key=lambda key:key[0])
            setattr(item,field,keys)
        self.edit(operation)

    def split(self,lane_id,item_id,time,*,linked=False):
        if linked:
            def grouped(project):
                targets=[(lane.id,item.id) for lane,item in project._linked_targets(lane_id,item_id)]
                selected=project.find(lane_id,item_id)[1]
                for lane_key,item_key in targets:
                    other=project.find(lane_key,item_key)[1]
                    if any(abs(getattr(other,key)-getattr(selected,key))>1e-6 for key in ('at','source_in','length','speed')):
                        raise ValueError('Linked items are not aligned; split independently or restore alignment first')
                right_ids=[]
                for lane_key,item_key in targets:
                    project.split(lane_key,item_key,time)
                    lane,item=project.find(lane_key,item_key)
                    right_ids.append((lane_key,lane.items[lane.items.index(item)+1].id))
                group=uid() if len(right_ids)>1 else ''
                for lane_key,item_key in right_ids:project.find(lane_key,item_key)[1].group_id=group
            return self.edit(grouped)
        def operation(project):
            lane,item=project.find(lane_id,item_id)
            if lane.locked:raise ValueError('Track is locked')
            if not item.at<time<item.at+item.duration:raise ValueError('Split must be inside item')
            elapsed=time-item.at
            if elapsed<item.fade_in or elapsed>item.duration-item.fade_out:
                raise ValueError('Split inside fade is not supported; move cursor or remove fade first')
            used=elapsed*item.speed
            right=Item(**{**asdict(item),'id':uid(),'at':time,'source_in':item.source_in+used,'length':item.length-used,'fade_in':0.,'group_id':''})
            for field in ('opacity_keys','gain_keys'):
                keys=getattr(item,field)
                if keys:
                    midpoint=curve_value(keys,elapsed,1.)
                    setattr(right,field,[[0.,midpoint]]+[[t-elapsed,v] for t,v in keys if t>elapsed])
                    setattr(item,field,[[t,v] for t,v in keys if t<elapsed]+[[elapsed,midpoint]])
            item.length=used;item.fade_out=0.
            lane.items.insert(lane.items.index(item)+1,right)
        self.edit(operation)

    def remove(self,lane_id,item_id,ripple=False,*,linked=False):
        if linked:
            def grouped(project):
                targets=[(lane.id,item.id) for lane,item in project._linked_targets(lane_id,item_id)]
                if ripple:
                    selected=project.find(lane_id,item_id)[1]
                    if any(abs(project.find(a,b)[1].at-selected.at)>1e-6 or
                           abs(project.find(a,b)[1].duration-selected.duration)>1e-6 for a,b in targets):
                        raise ValueError('Linked ripple requires aligned start/duration; no items changed')
                for lane_key,item_key in targets:project.remove(lane_key,item_key,ripple=ripple)
            return self.edit(grouped)
        def operation(project):
            lane,item=project.find(lane_id,item_id)
            if lane.locked:raise ValueError('Track is locked')
            end,removed=item.at+item.duration,item.duration
            lane.items.remove(item)
            if ripple:
                for other in lane.items:
                    if other.at>=end:other.at-=removed
        self.edit(operation)

    def lane_state(self,lane_id,**values):
        if not values.keys()<={'enabled','locked','name'}:raise ValueError('Unsupported track state')
        def operation(project):
            lane=next((lane for lane in project.lanes if lane.id==lane_id),None)
            if lane is None:raise ValueError('Track not found')
            for key,value in values.items():setattr(lane,key,value)
        self.edit(operation)

    def move_lane(self,lane_id,delta):
        if delta not in (-1,1):raise ValueError('Layer move must be one step')
        def operation(project):
            index=next((i for i,lane in enumerate(project.lanes) if lane.id==lane_id),-1)
            target=index+delta
            if index<0 or not 0<=target<len(project.lanes):raise ValueError('No lane in that direction')
            if project.lanes[index].locked:raise ValueError('Track is locked')
            project.lanes[index],project.lanes[target]=project.lanes[target],project.lanes[index]
        self.edit(operation)

    def relink(self,media_id,path):
        path=Path(path).expanduser().resolve()
        if not path.is_file():raise FileNotFoundError(f'Media not found: {path}')
        info=probe(path)
        def operation(project):
            media=next((m for m in project.media if m.id==media_id),None)
            if media is None:raise ValueError('Media reference not found')
            media.path=str(path);media.duration=info.duration
            media.has_video=info.has_video;media.has_audio=info.has_audio
        self.edit(operation)


def fade_gain(item,elapsed):
    """Linear timeline-time envelope shared by decoded preview and export."""
    value=1.
    if item.fade_in:value=min(value,max(0.,elapsed/item.fade_in))
    if item.fade_out:value=min(value,max(0.,(item.duration-elapsed)/item.fade_out))
    return value


def curve_value(keys,time,default):
    """Piecewise linear, held outside first/last key. Keys already validated."""
    if not keys:return default
    if time<=keys[0][0]:return keys[0][1]
    for (a,x),(b,y) in zip(keys,keys[1:]):
        if time<=b:return x+(y-x)*(time-a)/(b-a)
    return keys[-1][1]

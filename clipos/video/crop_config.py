"""Authoritative, persisted source crop shared by preview and every encoded clip.

Coordinates refer to FFmpeg's display-oriented decoded source, never widget pixels.
YUV420 coordinates are aligned once, to even source pixels. No subject/scene model
may change this configuration. Aspect fitting happens explicitly before saving.
"""
from dataclasses import asdict, dataclass
import math

ASPECTS = {'9:16': (720,1280), '1:1': (1080,1080), '16:9': (1280,720)}


@dataclass(frozen=True)
class CropConfig:
    x: int
    y: int
    width: int
    height: int
    aspect_ratio: str
    output_width: int
    output_height: int
    source_width: int
    source_height: int

    def validate(self):
        for name in ('x','y','width','height','output_width','output_height','source_width','source_height'):
            if type(getattr(self,name)) is not int:raise ValueError('Crop coordinates and dimensions must be integer source pixels')
        if min(self.width,self.height,self.source_width,self.source_height)<2:raise ValueError('Crop/source is too small')
        if self.x<0 or self.y<0 or self.x+self.width>self.source_width or self.y+self.height>self.source_height:
            raise ValueError('Selected crop is outside the decoded source')
        if any(v%2 for v in (self.x,self.y,self.width,self.height,self.output_width,self.output_height)):
            raise ValueError('Crop and output coordinates must use even pixels for YUV420')
        if not 2<=self.output_width<=7680 or not 2<=self.output_height<=7680:raise ValueError('Unsupported output resolution')
        if self.aspect_ratio not in ASPECTS:raise ValueError('Choose 9:16, 1:1 or 16:9')
        aw,ah=ASPECTS[self.aspect_ratio]
        if self.output_width*ah!=self.output_height*aw:raise ValueError('Output dimensions do not match selected aspect ratio')
        if self.width*ah!=self.height*aw:raise ValueError('Crop does not match output aspect; select/fill the crop explicitly')
        return self

    @classmethod
    def from_dict(cls,data):
        if not isinstance(data,dict):raise ValueError('Expected saved crop configuration')
        try:return cls(**data).validate()
        except TypeError as exc:raise ValueError('Invalid saved crop configuration') from exc

    @classmethod
    def from_selection(cls,selection,source_width,source_height,aspect_ratio,output=None):
        """Fit aspect *inside* a normalized drag rectangle, then expose exact pixels.

        Callers must show the returned effective rectangle; it is the selection,
        not a hidden export-time crop. Rounding never expands beyond the drag.
        """
        if type(source_width) is not int or type(source_height) is not int or min(source_width,source_height)<2:
            raise ValueError('Read original video dimensions before selecting a crop')
        if aspect_ratio not in ASPECTS:raise ValueError('Unsupported crop aspect ratio')
        if len(selection)!=4 or any(type(v) not in (float,int) or not math.isfinite(v) for v in selection):raise ValueError('Invalid crop selection')
        x,y,w,h=selection
        if x<0 or y<0 or w<=0 or h<=0 or x+w>1.00000001 or y+h>1.00000001:raise ValueError('Crop selection must fit source boundaries')
        left=math.ceil(x*source_width/2)*2;top=math.ceil(y*source_height/2)*2
        right=math.floor(min(source_width,(x+w)*source_width)/2)*2
        bottom=math.floor(min(source_height,(y+h)*source_height)/2)*2
        if right-left<2 or bottom-top<2:raise ValueError("Selected crop is smaller than two source pixels")
        aw,ah=ASPECTS[aspect_ratio];ratio=aw/ah
        divisor=math.gcd(aw,ah);unit_w=2*aw//divisor;unit_h=2*ah//divisor
        count=min((right-left)//unit_w,(bottom-top)//unit_h)
        if count<1:raise ValueError('Selection too small for the chosen aspect and even-pixel encoding')
        cw=count*unit_w;ch=count*unit_h
        left+=((right-left-cw)//4)*2;top+=((bottom-top-ch)//4)*2
        ow,oh=output or ASPECTS[aspect_ratio]
        return cls(left,top,cw,ch,aspect_ratio,ow,oh,source_width,source_height).validate()

    def to_dict(self):return asdict(self.validate())

    @property
    def normalized(self):
        return (self.x/self.source_width,self.y/self.source_height,self.width/self.source_width,self.height/self.source_height)

    def filter(self,source_width,source_height):
        self.validate()
        if (source_width,source_height)!=(self.source_width,self.source_height):
            raise ValueError('Source dimensions changed; select the crop again instead of using a default')
        return f'crop={self.width}:{self.height}:{self.x}:{self.y},scale={self.output_width}:{self.output_height}:flags=lanczos,setsar=1'


def save_crop(db,project_id,config):
    import json
    config.validate()
    if db.get_project(project_id) is None:raise ValueError('Project does not exist')
    db.set_setting(f'crop_config:{project_id}',json.dumps(config.to_dict(),sort_keys=True))


def load_crop(db,project_id):
    import json
    value=db.get_setting(f'crop_config:{project_id}','')
    return CropConfig.from_dict(json.loads(value)) if value else None

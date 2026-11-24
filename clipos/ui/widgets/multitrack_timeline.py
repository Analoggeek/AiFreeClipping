"""Native graphical track editor; gestures commit validated model transactions.

No rendered thumbnails or waveforms are fabricated. Horizontal scale is explicit
pixels/second; the containing editor controls linked timing transactions.
"""
from __future__ import annotations

from PySide6.QtCore import Qt,QRectF,Signal
from PySide6.QtGui import QColor,QPainter,QPen
from PySide6.QtWidgets import QWidget


class MultitrackTimeline(QWidget):
    seekRequested=Signal(float)
    selected=Signal(str,str)
    editRequested=Signal(str,str,object)
    LABEL=140
    RULER=28
    ROW=46

    def __init__(self,parent=None):
        super().__init__(parent)
        self.project=None;self.position=0.;self.scale=60.;self.snap=True
        self.selection=None;self.drag=None;self.waveforms={}
        self.setMinimumHeight(150);self.setMouseTracking(True)
        self.setToolTip('Drag clip to move; drag left/right edge to trim. Shift bypasses snapping. Linked A/V setting controls paired timing edits.')

    def set_project(self,project):
        self.project=project;self.drag=None
        from ...video.waveform import source_signature
        retained={}
        for media in project.media:
            if media.id not in self.waveforms:continue
            try:
                data=self.waveforms[media.id]
                if data['source_signature']==source_signature(media.path):retained[media.id]=data
            except OSError:pass
        self.waveforms=retained
        self.setMinimumSize(max(700,round(self.LABEL+(project.duration+2)*self.scale)),
                            max(150,self.RULER+len(project.lanes)*self.ROW))
        self.update()

    def set_scale(self,scale):
        self.scale=max(5.,min(240.,float(scale)))
        if self.project:self.set_project(self.project)

    def set_position(self,position):
        self.position=position;self.update()

    def item_rect(self,row,item):
        return QRectF(self.LABEL+item.at*self.scale,self.RULER+row*self.ROW+5,
                      max(2,item.duration*self.scale),self.ROW-10)

    def _hit(self,point):
        if not self.project:return None
        row=int((point.y()-self.RULER)//self.ROW)
        if not 0<=row<len(self.project.lanes):return None
        lane=self.project.lanes[row]
        for item in reversed(lane.items):
            rect=self.item_rect(row,item)
            if rect.contains(point):return lane,item,rect
        return None

    def _snap(self,value,exclude,disabled=False):
        value=max(0.,value)
        if not self.snap or disabled:return value
        candidates=[0.,self.position,round(value*self.project.fps)/self.project.fps]
        # Prefer nearby clip boundaries over frame-grid quantization.
        boundaries=[0.,self.position]
        for lane in self.project.lanes:
            for item in lane.items:
                if item.id!=exclude:boundaries.extend([item.at,item.at+item.duration])
        near=min(boundaries,key=lambda t:abs(t-value))
        if abs(near-value)*self.scale<=8:return near
        return candidates[-1]

    def gesture_values(self,lane_id,item_id,mode,delta,disabled=False):
        """Pure gesture calculation; model validation remains the transaction boundary."""
        lane,item=self.project.find(lane_id,item_id)
        if lane.locked:raise ValueError('Track is locked')
        if mode=='move':return {'at':self._snap(item.at+delta,item.id,disabled)}
        minimum=1/self.project.fps
        if mode=='left':
            boundary=self._snap(item.at+delta,item.id,disabled)
            change=max(-item.source_in/item.speed,min(boundary-item.at,item.duration-minimum))
            change=max(-item.at,change)
            return {'at':item.at+change,'source_in':item.source_in+change*item.speed,
                    'length':item.length-change*item.speed}
        if mode=='right':
            media=next(m for m in self.project.media if m.id==item.media_id)
            end=self._snap(item.at+item.duration+delta,item.id,disabled)
            duration=max(minimum,min(end-item.at,(media.duration-item.source_in)/item.speed))
            return {'length':duration*item.speed}
        raise ValueError('Unknown timeline gesture')

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or not self.project:return
        point=event.position()
        if point.x()<self.LABEL:return
        if point.y()<self.RULER:
            self.seekRequested.emit(max(0,min(self.project.duration,(point.x()-self.LABEL)/self.scale)));return
        hit=self._hit(point)
        if not hit:return
        lane,item,rect=hit
        self.selection=(lane.id,item.id);self.selected.emit(lane.id,item.id)
        if lane.locked:self.update();return
        mode='left' if point.x()-rect.left()<6 else 'right' if rect.right()-point.x()<6 else 'move'
        self.drag={'lane':lane.id,'item':item.id,'mode':mode,'x':point.x(),'values':{}}
        self.update()

    def mouseMoveEvent(self,event):
        if not self.drag:return
        d=self.drag
        disabled=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        d['values']=self.gesture_values(d['lane'],d['item'],d['mode'],(event.position().x()-d['x'])/self.scale,disabled)
        self.update()

    def mouseReleaseEvent(self,event):
        if not self.drag or event.button()!=Qt.MouseButton.LeftButton:return
        d=self.drag;self.drag=None
        if d['values']:self.editRequested.emit(d['lane'],d['item'],d['values'])
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#171b27'))
        if not self.project:return
        painter.setPen(QColor('#a4adc1'))
        # Only paint visible ruler marks, even for six-hour projects.
        clip=event.rect();step=max(1,round(60/self.scale))
        start=max(0,int((clip.left()-self.LABEL)/self.scale)//step*step)
        end=max(start,int((clip.right()-self.LABEL)/self.scale)+step)
        for second in range(start,end+1,step):
            x=self.LABEL+second*self.scale
            painter.drawLine(round(x),18,round(x),self.height())
            painter.drawText(QRectF(x+3,0,70,18),str(second)+'s')
        for row,lane in enumerate(self.project.lanes):
            y=self.RULER+row*self.ROW
            painter.fillRect(QRectF(0,y,self.LABEL,self.ROW),QColor('#242a39'))
            painter.setPen(QColor('#d4dbea'))
            painter.drawText(QRectF(6,y+4,self.LABEL-10,self.ROW-8),Qt.TextFlag.TextWordWrap,
                             ('[locked] ' if lane.locked else '')+lane.name)
            for item in lane.items:
                rect=self.item_rect(row,item)
                if not rect.intersects(QRectF(clip)):continue
                color=QColor('#4d63b2' if lane.kind=='video' else '#267c70')
                if not lane.enabled:color=QColor('#444752')
                painter.setBrush(color)
                painter.setPen(QPen(QColor('#f1d58b' if self.selection==(lane.id,item.id) else '#69758d'),2))
                painter.drawRoundedRect(rect,5,5)
                waveform=self.waveforms.get(item.media_id) if lane.kind=='audio' else None
                if waveform:
                    peaks=waveform['peaks'];step=waveform['bin_seconds']
                    painter.save();painter.setClipRect(rect)
                    painter.setPen(QColor('#85d1be'))
                    left=max(round(rect.left()),clip.left());right=min(round(rect.right()),clip.right())
                    for px in range(left,right+1,2):
                        start=item.source_in+max(0,(px-rect.left())/self.scale)*item.speed
                        if start>=waveform['duration']:continue
                        stop=min(item.source_in+item.length,start+2/self.scale*item.speed)
                        a=max(0,min(len(peaks)-1,int(start/step)))
                        b=max(a+1,min(len(peaks),int(stop/step)+1))
                        amplitude=max(peaks[a:b],default=0)*(rect.height()/2-3)
                        mid=rect.center().y()
                        painter.drawLine(px,round(mid-amplitude),px,round(mid+amplitude))
                    painter.restore()
                painter.setPen(QColor('white'))
                painter.save();painter.setClipRect(rect.adjusted(5,0,-5,0))
                painter.drawText(rect.adjusted(7,0,-5,0),Qt.AlignmentFlag.AlignVCenter,f'{item.at:.2f}s · {item.duration:.2f}s')
                painter.restore()
                keys=item.opacity_keys if lane.kind=='video' else item.gain_keys
                if keys:
                    maximum=1. if lane.kind=='video' else 4.
                    painter.save();painter.setClipRect(rect)
                    painter.setPen(QPen(QColor('#f5dd8a'),1))
                    previous=None
                    for moment,value in keys:
                        px=self.LABEL+(item.at+moment)*self.scale
                        py=rect.bottom()-3-value/maximum*(rect.height()-6)
                        if previous:painter.drawLine(previous[0],previous[1],round(px),round(py))
                        painter.setBrush(QColor('#f5dd8a'));painter.drawEllipse(QRectF(px-3,py-3,6,6))
                        previous=(round(px),round(py))
                    painter.restore()
                if self.drag and self.drag['item']==item.id and self.drag['values']:
                    values=self.drag['values'];at=values.get('at',item.at);length=values.get('length',item.length)
                    ghost=QRectF(self.LABEL+at*self.scale,rect.y(),length/item.speed*self.scale,rect.height())
                    painter.setBrush(QColor(255,255,255,60));painter.drawRoundedRect(ghost,5,5)
        x=self.LABEL+self.position*self.scale
        painter.setPen(QPen(QColor('#ff827b'),2));painter.drawLine(round(x),0,round(x),self.height())

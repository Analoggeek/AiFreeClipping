"""Live source canvas with independent labelled gameplay/player regions.

Qt implementation of dual-region interaction; geometry is normalized to the video,
not widget padding. Both committed regions survive active-target changes/frames.
"""
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class CropSelector(QWidget):
    selected = Signal(tuple)
    changing = Signal(tuple)
    frame_changed = Signal()
    COLORS = {'player':'#ff67b7', 'gameplay':'#58dbef'}

    def __init__(self,parent=None):
        super().__init__(parent)
        self.image=QPixmap();self.rect=None;self.anchor=None
        self.regions={'player':None,'gameplay':(0.,0.,1.,1.)}
        self.active='player';self._before=None
        self.setMinimumSize(280,200);self.setMaximumHeight(380)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_image(self,path):
        self.set_frame(QPixmap(str(path)))

    def set_frame(self,frame):
        self.image=frame if isinstance(frame,QPixmap) else QPixmap.fromImage(frame)
        self.update();self.frame_changed.emit()

    def set_regions(self,player,gameplay):
        self.regions={'player':tuple(player) if player else None,
                      'gameplay':tuple(gameplay) if gameplay else (0.,0.,1.,1.)}
        self.rect=self.regions[self.active];self.update()

    def set_active(self,target):
        if target not in self.regions:raise ValueError('Unknown crop target')
        self.active=target;self.anchor=None;self.rect=self.regions[target];self.update()

    def display_rect(self):
        if self.image.isNull(): return QRectF()
        size=self.image.size().scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())

    def point(self,event):
        r=self.display_rect()
        if r.isEmpty(): return None
        return (max(0.,min(1.,(event.position().x()-r.x())/r.width())),max(0.,min(1.,(event.position().y()-r.y())/r.height())))

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.display_rect().contains(event.position()):
            self.anchor=self.point(event);self._before=self.regions[self.active]

    def mouseMoveEvent(self,event):
        if self.anchor is not None:
            q=self.point(event)
            if q is None:return
            x,y=self.anchor
            self.rect=(min(x,q[0]),min(y,q[1]),abs(x-q[0]),abs(y-q[1]))
            self.regions[self.active]=self.rect
            self.update();self.changing.emit(self.rect)

    def mouseReleaseEvent(self,event):
        if self.anchor is not None:
            self.mouseMoveEvent(event);self.anchor=None
            if self.rect and min(self.rect[2:])>.015:self.selected.emit(self.rect)
            else:
                self.regions[self.active]=self._before;self.rect=self._before
                self.frame_changed.emit();self.update()

    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.contentsRect(),QColor('#090f17'))
        r=self.display_rect()
        if not self.image.isNull():p.drawPixmap(r.toRect(),self.image)
        else:
            p.setPen(QColor('#aabacc'));p.drawText(self.contentsRect(),Qt.AlignmentFlag.AlignCenter,getattr(self,'empty_text','Import a recording to select gameplay / player regions'))
        # Draw active last so even overlapping source regions remain identifiable.
        for key in [k for k in self.regions if k!=self.active]+[self.active]:
            rect=self.regions[key]
            if not rect:continue
            x,y,w,h=rect;color=QColor(self.COLORS[key]);fill=QColor(color);fill.setAlpha(22)
            box=QRectF(r.x()+x*r.width(),r.y()+y*r.height(),w*r.width(),h*r.height())
            p.setPen(QPen(color,3 if key==self.active else 2));p.setBrush(fill);p.drawRect(box)
            label=f'{key.upper()} {w*100:.0f}% × {h*100:.0f}%'
            label_width=min(max(110,p.fontMetrics().horizontalAdvance(label)+12),max(110,r.width()))
            label_box=QRectF(min(box.x(),max(r.x(),r.right()-label_width)),min(box.y(),r.bottom()-24),label_width,24)
            p.fillRect(label_box,QColor('#09121ddd'));p.setPen(color)
            p.drawText(label_box.adjusted(4,0,-2,0),Qt.AlignmentFlag.AlignVCenter,label)
        p.end()

"""Source-pixel-aware drag selection; padding is never treated as video."""
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class CropSelector(QWidget):
    selected = Signal(tuple)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.image=QPixmap();self.rect=None;self.anchor=None
        self.setMinimumSize(340,200)
        self.setMaximumHeight(320)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_image(self,path):
        self.image=QPixmap(str(path));self.update()

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
            self.anchor=self.point(event)

    def mouseMoveEvent(self,event):
        if self.anchor:
            q=self.point(event); x,y=self.anchor
            self.rect=(min(x,q[0]),min(y,q[1]),abs(x-q[0]),abs(y-q[1]));self.update()

    def mouseReleaseEvent(self,event):
        if self.anchor:
            self.mouseMoveEvent(event);self.anchor=None
            if self.rect and min(self.rect[2:])>.015:self.selected.emit(self.rect)

    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.contentsRect(),QColor('#090f17'))
        r=self.display_rect()
        if not self.image.isNull():p.drawPixmap(r.toRect(),self.image)
        else:
            p.setPen(QColor('#aabacc'));p.drawText(self.contentsRect(),Qt.AlignmentFlag.AlignCenter,'Import a recording to select gameplay / player regions')
        if self.rect:
            x,y,w,h=self.rect;p.setPen(QPen(QColor('#28d9be'),2));p.setBrush(QColor(25,220,190,35))
            p.drawRect(QRectF(r.x()+x*r.width(),r.y()+y*r.height(),w*r.width(),h*r.height()))
        p.end()

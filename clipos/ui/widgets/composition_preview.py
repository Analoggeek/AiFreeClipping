"""Low-cost live composition view of decoded source frames, not a finished render.

Uses the same adapted layout geometry as FFmpeg. Colour, speech caption timing,
silence removal and AI tracking are verified in the rendered recipe/final output.
"""
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont
from PySide6.QtWidgets import QWidget
from ...video.layouts import geometry


class CompositionPreview(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.source=None;self.facecam=None;self.gameplay=(0.,0.,1.,1.)
        self.caption=None;self.caption_size=48
        self.layout_key='bottom';self.camera_size=1/3;self.output_size=(1080,1920)
        self.setMinimumSize(160,240);self.setMaximumWidth(330);self.setMaximumHeight(420)

    def configure(self,source,facecam,gameplay,layout_key,camera_size,output_size,caption=None,caption_size=48):
        self.caption=caption;self.caption_size=caption_size
        self.source=source;self.facecam=facecam;self.gameplay=gameplay
        self.layout_key=layout_key;self.camera_size=camera_size;self.output_size=output_size
        self.update()

    def sizeHint(self):return QSize(230,360)

    @staticmethod
    def cover(painter,image,rect,destination):
        x,y,w,h=rect
        if w<=0 or h<=0:return
        sw,sh=w*image.width(),h*image.height()
        ratio=max(destination.width()/sw,destination.height()/sh)
        cw,ch=destination.width()/ratio,destination.height()/ratio
        crop=QRectF(x*image.width()+(sw-cw)/2,y*image.height()+(sh-ch)/2,cw,ch)
        painter.drawPixmap(destination,image,crop)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform);p.fillRect(self.rect(),QColor('#090f17'))
        if self.source is None or self.source.isNull():
            p.setPen(QColor('#9eb4ca'));p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Live composition\nImport a recording');p.end();return
        ow,oh=self.output_size
        effective=self.layout_key
        if not self.facecam and effective not in ('blur','fill','game'):effective='game'
        spec=geometry(effective,self.camera_size,ow,oh)
        fit=QSize(ow,oh).scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio)
        x=(self.width()-fit.width())/2;y=(self.height()-fit.height())/2
        p.translate(x,y);p.scale(fit.width()/ow,fit.height()/oh)
        p.fillRect(QRectF(0,0,ow,oh),Qt.GlobalColor.black)
        if spec['mode']=='blur':
            # Deliberately low-res blur approximation, not a second FFmpeg job.
            small=self.source.scaled(24,24,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self.cover(p,small,(0,0,1,1),QRectF(0,0,ow,oh))
            size=self.source.size().scaled(QSize(ow,oh),Qt.AspectRatioMode.KeepAspectRatio)
            p.drawPixmap(QRectF((ow-size.width())/2,(oh-size.height())/2,size.width(),size.height()),self.source,QRectF(self.source.rect()))
        else:
            for layer in spec['layers']:
                dst=QRectF(layer['x'],layer['y'],layer['w'],layer['h'])
                p.save()
                if layer.get('circle'):
                    path=QPainterPath();path.addEllipse(dst);p.setClipPath(path)
                rect=(0,0,1,1) if layer['source']=='full' else (self.facecam if layer['source']=='cam' else self.gameplay)
                self.cover(p,self.source,rect,dst);p.restore()
        if self.caption:
            from ...captions.caption_engine import get_style
            style=get_style(self.caption)
            text='CAPTION STYLE SAMPLE' if style.uppercase else 'Caption style sample'
            font=QFont(style.font);font.setPixelSize(max(12,round(self.caption_size*ow/1080)));font.setBold(style.bold)
            p.setFont(font)
            raw=style.primary_color.replace('&H','').zfill(8)
            color=QColor('#'+raw[-2:]+raw[-4:-2]+raw[-6:-4])
            metrics=p.fontMetrics();x=(ow-metrics.horizontalAdvance(text))/2;y=oh*.64
            path=QPainterPath();path.addText(x,y,font,text)
            p.setPen(QPen(QColor('black'),max(1,style.stroke_width*ow/1080)));p.setBrush(color);p.drawPath(path)
        p.end()

"""Small consistent vector navigation icons, visible on both native themes."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtCore import QPointF


def navigation_icon(key):
    pm=QPixmap(24,24);pm.fill(Qt.GlobalColor.transparent)
    p=QPainter(pm);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setPen(QPen(QColor('#13c7b2'),1.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    if key=='workflow':
        p.drawRoundedRect(QRectF(3,3,18,18),5,5);p.drawPolygon(QPolygonF([QPointF(10,7),QPointF(17,12),QPointF(10,17)]))
    elif key=='projects':
        p.drawRoundedRect(QRectF(3,7,18,14),2,2);p.drawPolyline(QPolygonF([QPointF(3,8),QPointF(3,4),QPointF(10,4),QPointF(13,7)]))
    elif key in ('editor','multitrack','longform'):
        p.drawLine(4,6,20,6);p.drawLine(4,12,20,12);p.drawLine(4,18,20,18)
        p.drawEllipse(QRectF(7,4,4,4));p.drawEllipse(QRectF(14,10,4,4));p.drawEllipse(QRectF(6,16,4,4))
    elif key in ('templates','library'):
        for x in (3,13):
            for y in (3,13):p.drawRoundedRect(QRectF(x,y,8,8),2,2)
    elif key=='models':
        p.drawRoundedRect(QRectF(6,6,12,12),3,3)
        for n in (8,12,16):p.drawLine(n,2,n,5);p.drawLine(n,19,n,22);p.drawLine(2,n,5,n);p.drawLine(19,n,22,n)
    else:
        p.drawEllipse(QRectF(4,4,16,16));p.drawEllipse(QRectF(9,9,6,6))
    p.end();return QIcon(pm)

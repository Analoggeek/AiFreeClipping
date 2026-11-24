"""Fast local visual previews of composition/caption recipes (not sample renders)."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap, QPen


def preset_thumbnail(key, title='', source=None, width=180, height=144):
    image = QPixmap(width,height)
    image.fill(QColor('#111a28'))
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if source and not source.isNull():
        p.drawPixmap(0,0,source.scaled(width,height,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation))
    else:
        gradient=QLinearGradient(0,0,width,height)
        gradient.setColorAt(0,QColor('#183b53')); gradient.setColorAt(1,QColor('#474069'))
        p.fillRect(image.rect(),gradient)
        p.setPen(QPen(QColor('#547d94'),1))
        for x in range(0,width,24): p.drawLine(x,0,x,height)
        p.setPen(QColor('#aac4d1'));p.drawText(QRectF(0,12,width,25),Qt.AlignmentFlag.AlignCenter,'COMPOSITION')
    if key=='gaming':
        p.fillRect(0,height*2//3,width,height//3+1,QColor('#254b55'))
        p.setBrush(QColor('#6ac4bc'));p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(width*.44,height*.70,width*.12,height*.16))
        p.drawRoundedRect(QRectF(width*.35,height*.85,width*.3,height*.2),8,8)
    from ...captions.caption_engine import CAPTION_STYLES
    style=CAPTION_STYLES.get(key)
    if style:
        raw=style.primary_color.replace('&H','').zfill(8)
        color=QColor('#'+raw[-2:]+raw[-4:-2]+raw[-6:-4])
        p.setPen(QPen(QColor('#080b12'),2));p.setFont(QFont('Arial',13,QFont.Weight.Bold if style.bold else QFont.Weight.Normal))
        text='YOUR MOMENT' if style.uppercase else 'Your moment'
        p.setPen(color);p.drawText(QRectF(4,height*.4,width-8,30),Qt.AlignmentFlag.AlignCenter,text)
    p.fillRect(0,height-27,width,27,QColor('#09121ddd'))
    p.setPen(QColor('#ffffff'));p.setFont(QFont('Arial',10,QFont.Weight.Bold))
    p.drawText(QRectF(5,height-27,width-10,27),Qt.AlignmentFlag.AlignCenter,title or key.replace('_',' ').title())
    p.end()
    return image


def layout_thumbnail(key, width=64, height=80):
    """Geometry illustration, not a claim of a rendered source preview."""
    from ...video.layouts import geometry
    spec=geometry(key,width=width,height=height)
    pix=QPixmap(width,height);pix.fill(QColor('#182431'))
    painter=QPainter(pix)
    if spec['mode']=='blur':
        painter.fillRect(10,20,width-20,height-40,QColor('#52718d'))
    for layer in spec['layers']:
        rect=QRectF(layer['x'],layer['y'],layer['w'],layer['h'])
        painter.setBrush(QColor('#62cdb9' if layer['source']=='cam' else '#375674'))
        painter.setPen(QPen(QColor('#101923'),1))
        if layer.get('circle'):painter.drawEllipse(rect)
        else:painter.drawRect(rect)
    painter.end();return pix

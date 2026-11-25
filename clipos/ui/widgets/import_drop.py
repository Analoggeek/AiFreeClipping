"""Real file drop target, sharing the existing import pipeline."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame
class ImportDrop(QFrame):
    file_dropped=Signal(str)
    def __init__(self):
        super().__init__();self.setObjectName('ImportDrop');self.setAcceptDrops(True)
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()):event.acceptProposedAction()
    def dropEvent(self,event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.file_dropped.emit(url.toLocalFile());event.acceptProposedAction();return

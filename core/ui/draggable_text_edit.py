from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtCore import Qt, QPoint

class DraggableTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_offset = QPoint()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            window = self.window()
            if window is not None:
                self._drag_offset = event.globalPos() - window.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_offset is not None:
            window = self.window()
            if window is not None:
                window.move(event.globalPos() - self._drag_offset)
                event.accept()
                return
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

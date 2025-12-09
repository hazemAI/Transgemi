from PyQt5.QtWidgets import QDialog, QRubberBand, QApplication
from PyQt5.QtCore import Qt, QRect, QPoint, QSize
from PyQt5.QtGui import QPainter, QColor


class RegionSelector(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.showFullScreen()
        self.grabKeyboard()
        self.grabMouse()

        self._selected_region = None
        self._origin = QPoint()
        self._rubber_band = QRubberBand(QRubberBand.Rectangle, self)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._origin = event.pos()
            self._rubber_band.setGeometry(QRect(self._origin, QSize()))
            self._rubber_band.show()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._rubber_band.isVisible():
            self._rubber_band.setGeometry(QRect(self._origin, event.pos()).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            rect = self._rubber_band.geometry()
            self._rubber_band.hide()
            if rect.width() > 10 and rect.height() > 10:
                self._selected_region = (rect.x(), rect.y(), rect.width(), rect.height())
                self.accept()
            else:
                self.reject()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape or (event.key() == Qt.Key_X and event.modifiers() & Qt.AltModifier):
            self.reject()
            return
        super().keyPressEvent(event)

    def get_selection(self):
        return self._selected_region

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

    def closeEvent(self, event):
        try:
            self.releaseKeyboard()
            self.releaseMouse()
        except Exception:
            pass
        super().closeEvent(event)


def select_screen_region(parent=None):
    selector = RegionSelector(parent)
    if parent is not None:
        setattr(parent, "active_region_selector", selector)
    selector.show()
    selector.raise_()
    selector.activateWindow()
    QApplication.setActiveWindow(selector)

    try:
        accepted = selector.exec_() == QDialog.Accepted
        if accepted:
            return selector.get_selection()
        return None
    finally:
        if parent is not None and getattr(parent, "active_region_selector", None) is selector:
            parent.active_region_selector = None

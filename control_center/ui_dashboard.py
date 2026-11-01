import html
import math
import os
import random
import time
from collections import deque
from urllib.parse import urlsplit

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QThread,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QTextOption,
)
from PyQt6.QtWidgets import (
    QDialog,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

# Project Hardware & Vision Modules
from gesture_controller import GestureController
from hand_detector import HandDetector
from serial_sender import SerialSender
from stream_manager import CameraThread


# ---------------------------------------------------------------------------
# Design tokens (Apple dark-mode palette)
# ---------------------------------------------------------------------------
BLUE = '#0A84FF'
GREEN = '#30D158'
ORANGE = '#FF9F0A'
YELLOW = '#FFD60A'
RED = '#FF453A'
TEAL = '#64D2FF'
TEXT = '#F5F5F7'
TEXT_DIM = '#9C9CA6'

UI_FAMILIES = ['SF Pro Display', 'SF Pro Text', 'Segoe UI Variable Display', 'Segoe UI', 'Helvetica Neue', 'Arial']
MONO_FAMILIES = ['SF Mono', 'Cascadia Mono', 'Consolas', 'Menlo']

QWIDGETSIZE_MAX = 16777215
GESTURE_RES = (1280, 720)   # operator camera
ROVER_RES = (2712, 1220)    # rover camera
RADAR_ALERT_CM = 20  # an echo this close lights the radar card red


def ui_font(point_size=10.0, weight=QFont.Weight.Normal, mono=False):
    """Font that prefers SF Pro on Apple systems and falls back to Segoe UI Variable on Windows."""
    font = QFont()
    font.setFamilies(MONO_FAMILIES if mono else UI_FAMILIES)
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    if mono:
        font.setStyleHint(QFont.StyleHint.Monospace)
    return font


APPLE_QSS = """
QDialog { background-color: #17181B; }

QLabel { color: #F5F5F7; font-size: 13px; background: transparent; }
QLabel[role="title"]   { font-size: 26px; font-weight: 700; }
QLabel[role="field"]   { font-size: 13px; font-weight: 600; }
QLabel[role="caption"] { color: #9C9CA6; font-size: 11px; font-weight: 400; }
QLabel[role="section"] { color: #9C9CA6; font-size: 11px; font-weight: 600; }
QLabel[role="metric"]  { font-size: 44px; font-weight: 600; }

/* Liquid glass card: translucent fill, faint edge; GlassBox paints the specular rim on top. */
QGroupBox {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 30), stop:1 rgba(255, 255, 255, 10));
    border: 1px solid rgba(255, 255, 255, 22);
    border-radius: 20px;
    margin-top: 24px;
    padding: 14px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    color: #A8A8B2;
    font-size: 12px;
    font-weight: 600;
}

QPushButton {
    background-color: rgba(255, 255, 255, 28);
    color: #F5F5F7;
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 11px;
    padding: 9px 16px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover    { background-color: rgba(255, 255, 255, 48); }
QPushButton:pressed  { background-color: rgba(255, 255, 255, 70); }
QPushButton:disabled { background-color: rgba(255, 255, 255, 10); color: #66666E; border-color: rgba(255, 255, 255, 12); }

QPushButton[role="primary"] {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3D9BFF, stop:1 #0A6FE0);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 70);
}
QPushButton[role="primary"]:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5CAEFF, stop:1 #1E82F0);
}
QPushButton[role="primary"]:pressed { background-color: #0A5FC4; }
QPushButton[role="primary"]:disabled {
    background-color: rgba(10, 132, 255, 50); color: #7E9BC4; border-color: rgba(255, 255, 255, 18);
}

QPushButton[role="pill"] {
    color: #EBEBF5;
    border-radius: 13px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: 500;
}
QPushButton[role="pill"]:checked {
    background-color: rgba(10, 132, 255, 95);
    border: 1px solid rgba(100, 180, 255, 140);
    color: #FFFFFF;
}

QLineEdit {
    background-color: rgba(0, 0, 0, 90);
    color: #F5F5F7;
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 11px;
    padding: 9px 12px;
    font-size: 13px;
    selection-background-color: #0A84FF;
}
QLineEdit:focus { border: 1px solid #0A84FF; background-color: rgba(0, 0, 0, 130); }

QSlider::groove:horizontal { background: rgba(255, 255, 255, 50); height: 4px; border-radius: 2px; }
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5E5CE6, stop:1 #0A84FF);
    border-radius: 2px;
}
QSlider::add-page:horizontal { background: rgba(255, 255, 255, 50); border-radius: 2px; }
QSlider::handle:horizontal {
    background: #FFFFFF;
    width: 22px;
    height: 22px;
    margin: -9px 0;
    border-radius: 11px;
}
QSlider::handle:horizontal:hover { background: #E5E5EA; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 2px 4px 2px; }
QScrollBar::handle:vertical { background: rgba(255, 255, 255, 60); border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 100); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QToolTip {
    background-color: #26282C;
    color: #F5F5F7;
    border: 1px solid rgba(255, 255, 255, 40);
    border-radius: 6px;
    padding: 4px 8px;
}
"""

def build_backdrop(width, height, dpr):
    """Dark grey gradient with a network of white dots joined by thin lines.

    The point layout is seeded, so it looks the same on every launch and simply
    scales with the window. It is painted once per window size and then cached.
    """
    pixmap = QPixmap(max(1, int(width * dpr)), max(1, int(height * dpr)))
    pixmap.setDevicePixelRatio(dpr)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    base = QLinearGradient(0, 0, width, height * 0.35)
    base.setColorAt(0.0, QColor('#0B0C0E'))
    base.setColorAt(0.55, QColor('#17181B'))
    base.setColorAt(1.0, QColor('#26282C'))
    painter.fillRect(0, 0, width, height, QBrush(base))

    # Jittered grid with a few gaps gives the clustered, uneven look of a plexus.
    rng = random.Random(7)
    cols, rows = 12, 8
    points = []
    for row in range(rows):
        for col in range(cols):
            if rng.random() < 0.18:
                continue
            nx = (col + 0.1 + rng.random() * 0.8) / cols
            ny = (row + 0.1 + rng.random() * 0.8) / rows
            points.append((nx * width, ny * height, rng.random()))

    if points:
        spacing = math.sqrt(width * height / len(points))
        limit = spacing * 1.55
        links = {}
        for i, (x1, y1, _) in enumerate(points):
            nearest = sorted(
                ((x1 - x2) ** 2 + (y1 - y2) ** 2, j)
                for j, (x2, y2, _) in enumerate(points)
                if j != i
            )[:3]
            for dist_sq, j in nearest:
                if dist_sq <= limit * limit:
                    links[(min(i, j), max(i, j))] = math.sqrt(dist_sq)

        for (i, j), dist in links.items():
            closeness = 1.0 - dist / limit
            painter.setPen(QPen(QColor(255, 255, 255, int(24 + 60 * closeness)), 0.8))
            painter.drawLine(
                QPointF(points[i][0], points[i][1]),
                QPointF(points[j][0], points[j][1]),
            )

        painter.setPen(Qt.PenStyle.NoPen)
        for x, y, t in points:
            dot = QColor(255, 255, 255, int(150 + 100 * t))
            painter.setBrush(QBrush(dot))
            painter.drawEllipse(QPointF(x, y), 1.0 + t * 1.1, 1.0 + t * 1.1)

    painter.end()
    return pixmap


class BackdropMixin:
    """Paints the dot-network backdrop behind a window; the cache is rebuilt only on resize."""

    _backdrop_pixmap = None
    _backdrop_key = None

    def paintEvent(self, event):
        del event
        key = (self.width(), self.height(), self.devicePixelRatioF())
        if self._backdrop_key != key or self._backdrop_pixmap is None:
            self._backdrop_pixmap = build_backdrop(*key)
            self._backdrop_key = key
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._backdrop_pixmap)


class GlassBox(QGroupBox):
    """QGroupBox with a liquid-glass finish.

    Besides the static sheen and rim it can glow: softly on hover, blue while it is
    "active" (a live camera) and red as an alert (something close on the radar).
    """

    RADIUS = 20.0

    def __init__(self, title='', margins=(0, 24, 0, 0), parent=None):
        super().__init__(title, parent)
        self._margins = margins  # left, top, right, bottom outside the card (matches the QSS margin)
        self._levels = {'hover': 0.0, 'active': 0.0, 'alert': 0.0}
        self._targets = {}
        self._anims = {}

    def _fade(self, name, target, duration=220):
        if self._targets.get(name) == target:
            return
        self._targets[name] = target
        anim = self._anims.get(name)
        if anim is None:
            anim = QVariantAnimation(self)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.valueChanged.connect(lambda value, key=name: self._set_level(key, value))
            self._anims[name] = anim
        anim.stop()
        anim.setDuration(duration)
        anim.setStartValue(float(self._levels[name]))
        anim.setEndValue(float(target))
        anim.start()

    def _set_level(self, name, value):
        self._levels[name] = float(value)
        self.update()

    def set_active(self, active):
        self._fade('active', 1.0 if active else 0.0, 350)

    def set_alert(self, alert):
        self._fade('alert', 1.0 if alert else 0.0, 180)

    def enterEvent(self, event):
        super().enterEvent(event)
        self._fade('hover', 1.0, 200)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._fade('hover', 0.0, 320)

    def paintEvent(self, event):
        super().paintEvent(event)
        left, top, right, bottom = self._margins
        rect = QRectF(self.rect()).adjusted(left + 0.5, top + 0.5, -right - 0.5, -bottom - 0.5)
        if rect.width() < 8 or rect.height() < 8:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QPainterPath()
        card.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        sheen = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + rect.height() * 0.45))
        sheen.setColorAt(0.0, QColor(255, 255, 255, 26))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(card, QBrush(sheen))

        rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
        rim.setColorAt(0.0, QColor(255, 255, 255, 120))
        rim.setColorAt(0.35, QColor(255, 255, 255, 28))
        rim.setColorAt(0.65, QColor(255, 255, 255, 18))
        rim.setColorAt(1.0, QColor(255, 255, 255, 70))
        painter.setPen(QPen(QBrush(rim), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(card)

        # (level, fill rgba, stroke rgb, stroke alpha, stroke width)
        glows = (
            (self._levels['hover'], (255, 255, 255, 16), (255, 255, 255), 80, 1.2),
            (self._levels['active'], (10, 132, 255, 12), (10, 132, 255), 120, 1.4),
            (self._levels['alert'], (255, 69, 58, 34), (255, 69, 58), 235, 2.0),
        )
        for level, fill, stroke, stroke_alpha, width in glows:
            if level <= 0.004:
                continue
            painter.fillPath(card, QBrush(QColor(fill[0], fill[1], fill[2], int(fill[3] * level))))
            painter.setPen(QPen(QColor(stroke[0], stroke[1], stroke[2], int(stroke_alpha * level)), width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(card)


def make_button(text, role='', checkable=False, focusable=True):
    button = QPushButton(text)
    if role:
        button.setProperty('role', role)
    button.setCheckable(checkable)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if not focusable:
        # Keeps WASD / Space from being swallowed by a focused button.
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return button


def make_label(text, role='', alignment=None, wrap=False):
    label = QLabel(text)
    if role:
        label.setProperty('role', role)
    if alignment is not None:
        label.setAlignment(alignment)
    label.setWordWrap(wrap)
    return label


class SerialConnectWorker(QThread):
    """Keep serial discovery and the ESP32 reboot wait off the GUI thread."""

    connection_finished = pyqtSignal(bool, str)

    def __init__(self, sender, parent=None):
        super().__init__(parent)
        self.sender = sender

    def run(self):
        try:
            connected = self.sender.connect()
            detail = self.sender.port or ''
        except Exception as exc:
            connected = False
            detail = str(exc)
        self.connection_finished.emit(connected, detail)


class SourceControlDialog(BackdropMixin, QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Source Control Configuration")
        self.setFixedSize(500, 400)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setFont(ui_font(10))
        self.setStyleSheet(APPLE_QSS)

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(28, 26, 28, 24)

        heading = make_label("Source Control", 'title', Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        layout.addSpacing(10)

        # 1. Gesture Cam Input
        gesture_label = make_label("Gesture camera: index or stream URL", 'field')
        self.gesture_input = QLineEdit("0")
        layout.addWidget(gesture_label)
        layout.addWidget(self.gesture_input)

        layout.addSpacing(8)

        # 2. Rover Cam Input
        rover_label = make_label("Rover stream: http(s) or RTSP URL, leave blank to skip", 'field', wrap=True)
        self.rover_input = QLineEdit()
        self.rover_input.setPlaceholderText("http://192.168.1.20:8080")
        layout.addWidget(rover_label)
        layout.addWidget(self.rover_input)

        layout.addStretch()

        # Connect / Confirm Button
        self.submit_btn = make_button("Connect Streams", 'primary')
        self.submit_btn.setMinimumHeight(44)
        self.submit_btn.setDefault(True)
        self.submit_btn.clicked.connect(self.validate_and_accept)
        layout.addWidget(self.submit_btn)

        self.setLayout(layout)

    @staticmethod
    def _is_stream_url(value):
        try:
            parsed = urlsplit(value)
            parsed.port  # Validate a provided port instead of accepting malformed URLs.
            return parsed.scheme.lower() in {"http", "https", "rtsp", "rtsps"} and bool(parsed.hostname)
        except ValueError:
            return False

    def validate_and_accept(self):
        gesture_val = self.gesture_input.text().strip()
        rover_val = self.rover_input.text().strip()

        if gesture_val and not (gesture_val.isdigit() or self._is_stream_url(gesture_val)):
            QMessageBox.warning(
                self,
                "Invalid gesture source",
                "Enter a non-negative camera index or a valid http(s)/rtsp stream URL, or leave it blank.",
            )
            return

        if rover_val and not self._is_stream_url(rover_val):
            QMessageBox.warning(
                self,
                "Invalid rover stream URL",
                "Enter a URL with a host, such as http://192.168.1.20:8080, or leave it blank.",
            )
            return
        self.accept()

    def get_sources(self):
        gesture_val = self.gesture_input.text().strip()
        if not gesture_val:
            gesture_source = None
        elif gesture_val.isdigit():
            gesture_source = int(gesture_val)
        else:
            gesture_source = gesture_val

        rover_source = self.rover_input.text().strip()
        if not rover_source:
            rover_source = None

        return gesture_source, rover_source


class VideoLabel(QLabel):
    """QLabel that paints camera frames itself: rounded corners, aspect-fit, no QPixmap churn."""

    def __init__(self, text='', radius=14, mode='ambient', parent=None):
        super().__init__(text, parent)
        self._mode = mode  # 'ambient' = fit + soft blurred glow in the gaps, 'cover' = fill and crop
        self._image = None
        self._overlay = None  # (text, colour) chip shown in fullscreen mode
        self._radius = radius
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_frame(self, image):
        self._image = image
        self.update()

    def clear_frame(self, text=''):
        self._image = None
        self.setText(text)
        self.update()

    @staticmethod
    def _ambient_image(image):
        """Two-step downscale to a 12x7 thumbnail; stretched over the gaps it reads as a soft glow."""
        small = QImage(96, 54, QImage.Format.Format_ARGB32_Premultiplied)
        tiny = QImage(12, 7, QImage.Format.Format_ARGB32_Premultiplied)
        for source, target in ((image, small), (small, tiny)):
            target.fill(Qt.GlobalColor.black)
            painter = QPainter(target)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(QRectF(target.rect()), source)
            painter.end()
        return tiny

    def set_overlay(self, text, color=None):
        self._overlay = (text, color or TEXT) if text else None
        self.update()

    def _draw_overlay(self, painter, rect):
        if not self._overlay:
            return
        text, color = self._overlay
        font = ui_font(12, QFont.Weight.DemiBold)
        painter.setFont(font)
        width = QFontMetrics(font).horizontalAdvance(text) + 46
        height = 34.0
        chip = QRectF(rect.left() + 14, rect.top() + 14, width, height)
        painter.setPen(QPen(QColor(255, 255, 255, 55), 1))
        painter.setBrush(QBrush(QColor(0, 0, 0, 150)))
        painter.drawRoundedRect(chip, height / 2, height / 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(color)))
        painter.drawEllipse(QPointF(chip.left() + 17, chip.center().y()), 4.5, 4.5)
        painter.setPen(QColor(TEXT))
        painter.drawText(
            QRectF(chip.left() + 30, chip.top(), width - 36, height),
            text,
            QTextOption(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
        )

    def _draw_rim(self, painter, rect):
        painter.setClipping(False)
        painter.setPen(QPen(QColor(255, 255, 255, 45), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), self._radius, self._radius)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(rect, self._radius, self._radius)
        painter.setClipPath(clip)
        painter.fillRect(rect, QColor('#000000'))

        image = self._image
        if image is None or image.isNull():
            painter.setPen(QColor(TEXT_DIM))
            painter.setFont(ui_font(10.5))
            painter.drawText(
                rect.adjusted(16, 16, -16, -16),
                self.text(),
                QTextOption(Qt.AlignmentFlag.AlignCenter),
            )
            self._draw_overlay(painter, rect)
            self._draw_rim(painter, rect)
            return

        fit = min(rect.width() / image.width(), rect.height() / image.height())
        cover = max(rect.width() / image.width(), rect.height() / image.height())
        scale = cover if self._mode == 'cover' else fit
        width, height = image.width() * scale, image.height() * scale
        target = QRectF((rect.width() - width) / 2.0, (rect.height() - height) / 2.0, width, height)
        if self._mode == 'ambient' and (target.width() < rect.width() - 1 or target.height() < rect.height() - 1):
            # Instead of black bars, stretch a tiny blurred copy of the frame behind it.
            painter.drawImage(rect, self._ambient_image(image))
            painter.fillRect(rect, QColor(0, 0, 0, 120))
        painter.drawImage(target, image)
        self._draw_overlay(painter, rect)
        self._draw_rim(painter, rect)


class HeaderBar(QWidget):
    """Slim top bar: wordmark, at-a-glance status chips and a live clock."""

    HEIGHT = 52
    CHIP_ORDER = ('esp', 'gesture', 'rover')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self._chips = {}
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self.update)
        self._clock.start()

    def set_chip(self, key, label, color):
        value = (label, QColor(color).name())
        if self._chips.get(key) != value:
            self._chips[key] = value
            self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        mid = height / 2.0
        left_center = QTextOption(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        # Brand mark: glowing blue core inside a thin ring
        center = QPointF(38, mid)
        glow = QRadialGradient(center, 15)
        glow_in = QColor(BLUE)
        glow_in.setAlpha(150)
        glow_out = QColor(BLUE)
        glow_out.setAlpha(0)
        glow.setColorAt(0.0, glow_in)
        glow.setColorAt(1.0, glow_out)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(center, 15, 15)
        painter.setBrush(QBrush(QColor(BLUE)))
        painter.drawEllipse(center, 4.5, 4.5)
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, 9, 9)

        # Wordmark: bold MANUS + light AD LUNAM, letter-spaced
        bold = ui_font(13, QFont.Weight.Bold)
        bold.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.0)
        light = ui_font(13, QFont.Weight.Light)
        light.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.0)
        x = 62.0
        advance = QFontMetrics(bold).horizontalAdvance('MANUS')
        painter.setFont(bold)
        painter.setPen(QColor(TEXT))
        painter.drawText(QRectF(x, 0, advance + 16, height), 'MANUS', left_center)
        x += advance + 14
        advance = QFontMetrics(light).horizontalAdvance('AD LUNAM')
        painter.setFont(light)
        painter.setPen(QColor('#C7C7D1'))
        painter.drawText(QRectF(x, 0, advance + 16, height), 'AD LUNAM', left_center)
        x += advance + 20
        if width > 1100:
            painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
            painter.drawLine(QPointF(x, mid - 9), QPointF(x, mid + 9))
            painter.setFont(ui_font(9.5))
            painter.setPen(QColor(TEXT_DIM))
            painter.drawText(QRectF(x + 16, 0, 220, height), 'Command & Control', left_center)

        # Live clock
        clock_text = time.strftime('%H:%M:%S')
        clock_font = ui_font(10, mono=True)
        clock_width = QFontMetrics(clock_font).horizontalAdvance(clock_text)
        right = width - 24.0
        painter.setFont(clock_font)
        painter.setPen(QColor(TEXT_DIM))
        painter.drawText(
            QRectF(right - clock_width - 6, 0, clock_width + 12, height),
            clock_text,
            QTextOption(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
        )
        right -= clock_width + 28

        # Status chips, right-aligned left of the clock
        chip_font = ui_font(9.5, QFont.Weight.DemiBold)
        metrics = QFontMetrics(chip_font)
        chips = [(key,) + self._chips[key] for key in self.CHIP_ORDER if key in self._chips]
        if chips:
            widths = [metrics.horizontalAdvance(label) + 42 for _, label, _ in chips]
            x = right - (sum(widths) + 10 * (len(chips) - 1))
            painter.setFont(chip_font)
            for (_, label, color), chip_width in zip(chips, widths):
                pill = QRectF(x, mid - 14, chip_width, 28)
                painter.setPen(QPen(QColor(255, 255, 255, 46), 1))
                painter.setBrush(QBrush(QColor(255, 255, 255, 20)))
                painter.drawRoundedRect(pill, 14, 14)
                dot = QPointF(x + 16, mid)
                dot_glow = QColor(color)
                dot_glow.setAlpha(65)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(dot_glow))
                painter.drawEllipse(dot, 7.5, 7.5)
                painter.setBrush(QBrush(QColor(color)))
                painter.drawEllipse(dot, 4, 4)
                painter.setPen(QColor(TEXT))
                painter.drawText(QRectF(x + 29, mid - 14, chip_width - 34, 28), label, left_center)
                x += chip_width + 10

        # Hairline that fades out toward both edges
        line = QLinearGradient(0, 0, width, 0)
        line.setColorAt(0.0, QColor(255, 255, 255, 0))
        line.setColorAt(0.5, QColor(255, 255, 255, 40))
        line.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(QPen(QBrush(line), 1))
        painter.drawLine(QPointF(0, height - 0.5), QPointF(width, height - 0.5))


class SpeedDial(QLabel):
    """270-degree gauge for the speed readout. It reads its value from the label text ("80%")."""

    def __init__(self, text='100%', parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _fraction(self):
        try:
            return max(0.0, min(1.0, int(self.text().strip().rstrip('%')) / 100.0))
        except ValueError:
            return 0.0

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = max(40.0, min(self.width(), self.height()) - 16.0)
        rect = QRectF((self.width() - side) / 2.0, (self.height() - side) / 2.0, side, side)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        def arc_pen(color, thickness):
            pen = QPen(color, thickness)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            return pen

        start = 225 * 16  # bottom-left, sweeping clockwise over the top
        painter.setPen(arc_pen(QColor(255, 255, 255, 38), 8))
        painter.drawArc(rect, start, -270 * 16)

        fraction = self._fraction()
        if fraction > 0.002:
            span = int(-270 * fraction * 16)
            painter.setPen(arc_pen(QColor(10, 132, 255, 55), 15))
            painter.drawArc(rect, start, span)
            painter.setPen(arc_pen(QColor(BLUE), 8))
            painter.drawArc(rect, start, span)
            angle = math.radians(225 - 270 * fraction)
            knob = QPointF(
                rect.center().x() + side / 2.0 * math.cos(angle),
                rect.center().y() - side / 2.0 * math.sin(angle),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor('#FFFFFF')))
            painter.drawEllipse(knob, 4.5, 4.5)

        font = ui_font(10, QFont.Weight.DemiBold)
        font.setPixelSize(max(16, int(side * 0.28)))
        painter.setFont(font)
        painter.setPen(QColor(TEXT))
        painter.drawText(rect, self.text(), QTextOption(Qt.AlignmentFlag.AlignCenter))


class RetryButton(QPushButton):
    """Small round glass button with a circular-arrow icon; the arrow spins while connecting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip('Reconnect serial')
        self._hover = False
        self._angle = 0.0
        self._spin = QTimer(self)
        self._spin.setInterval(30)
        self._spin.timeout.connect(self._advance)

    def set_busy(self, busy):
        if busy:
            if not self._spin.isActive():
                self._spin.start()
        else:
            self._spin.stop()
            self._angle = 0.0
        self.update()

    def _advance(self):
        self._angle = (self._angle + 14.0) % 360.0
        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hover = False
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.isDown():
            alpha = 72
        elif self._hover and self.isEnabled():
            alpha = 50
        else:
            alpha = 28
        painter.setPen(QPen(QColor(255, 255, 255, 56), 1))
        painter.setBrush(QBrush(QColor(255, 255, 255, alpha)))
        painter.drawEllipse(rect)

        busy = self._spin.isActive()
        color = QColor(BLUE if busy else (TEXT if self.isEnabled() else TEXT_DIM))
        pen = QPen(color, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.translate(rect.center())
        painter.rotate(self._angle)

        # Open circle (clockwise from the top) with an arrowhead on its end
        radius = 7.5
        painter.drawArc(QRectF(-radius, -radius, radius * 2, radius * 2), 90 * 16, -290 * 16)
        end = math.radians(90 - 290)
        tip = QPointF(radius * math.cos(end), -radius * math.sin(end))
        back = math.atan2(-math.cos(end), -math.sin(end))  # opposite to the direction of travel
        head = QPainterPath()
        head.moveTo(QPointF(tip.x() + 4.6 * math.cos(back + 0.7), tip.y() + 4.6 * math.sin(back + 0.7)))
        head.lineTo(tip)
        head.lineTo(QPointF(tip.x() + 4.6 * math.cos(back - 0.7), tip.y() + 4.6 * math.sin(back - 0.7)))
        painter.drawPath(head)


class TelemetryGraph(QWidget):
    """Smooth rolling line graph of one value over the last 30 seconds.

    Samples are bucketed (0.25 s) so the curve stays readable: 'min' keeps the closest
    reading of each bucket, 'avg' the mean. Gaps in the data break the line.
    """

    WINDOW = 30.0
    BUCKET = 0.25
    GAP = 1.2

    def __init__(self, title, unit, color, min_span=100.0, cap=None, threshold=None, mode='avg', parent=None):
        super().__init__(parent)
        self.setMinimumSize(210, 56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._title = title
        self._unit = unit
        self._color = QColor(color)
        self._min_span = float(min_span)
        self._cap = float(cap) if cap else None   # fixed ceiling; readings above it are clamped
        self._threshold = threshold
        self._mode = mode
        self._samples = deque()                   # (time, value)
        self._bucket = []
        self._bucket_start = None
        self._top = float(cap) if cap else float(min_span)
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    def add(self, value):
        now = time.monotonic()
        value = float(value)
        if self._cap:
            value = min(value, self._cap)
        if self._bucket_start is None or now - self._bucket_start > self.BUCKET * 2:
            self._bucket = []
            self._bucket_start = now
        self._bucket.append(value)
        if now - self._bucket_start >= self.BUCKET:
            result = min(self._bucket) if self._mode == 'min' else sum(self._bucket) / len(self._bucket)
            self._samples.append((now, result))
            self._bucket = []
            self._bucket_start = now
            cutoff = now - self.WINDOW - 2.0
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.popleft()

    @staticmethod
    def _smooth_path(points):
        """Catmull-Rom spline through the points, as cubic Beziers."""
        path = QPainterPath(points[0])
        count = len(points)
        for i in range(count - 1):
            p0 = points[i - 1] if i > 0 else points[i]
            p1, p2 = points[i], points[i + 1]
            p3 = points[i + 2] if i + 2 < count else p2
            c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6.0, p1.y() + (p2.y() - p0.y()) / 6.0)
            c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6.0, p2.y() - (p3.y() - p1.y()) / 6.0)
            path.cubicTo(c1, c2, p2)
        return path

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        width, height = float(self.width()), float(self.height())
        window_start = now - self.WINDOW
        visible = [(t, v) for t, v in self._samples if t >= window_start - 1.0]

        # The vertical range eases toward what the data needs (fixed when a cap is set).
        if self._cap:
            top = self._cap
        else:
            peak = max((v for _, v in visible), default=0.0)
            self._top += (max(self._min_span, peak * 1.2) - self._top) * 0.2
            top = max(self._top, 1.0)

        header_height = 20.0
        plot = QRectF(0, header_height + 4, width, max(10.0, height - header_height - 4))

        def x_of(t):
            return plot.left() + (t - window_start) / self.WINDOW * plot.width()

        def y_of(v):
            return plot.bottom() - min(max(v / top, 0.0), 1.0) * plot.height()

        # Header: title on the left, latest value on the right
        latest = visible[-1] if visible else None
        live = latest is not None and now - latest[0] < 1.5
        if not live:
            value_text = '--'
        elif self._cap and latest[1] >= self._cap:
            value_text = f'>{int(self._cap)} {self._unit}'
        else:
            value_text = f'{int(round(latest[1]))} {self._unit}'
        painter.setFont(ui_font(9, QFont.Weight.DemiBold))
        painter.setPen(QColor(TEXT_DIM))
        painter.drawText(
            QRectF(0, 0, width * 0.62, header_height),
            self._title,
            QTextOption(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
        )
        painter.setFont(ui_font(11, QFont.Weight.Bold))
        painter.setPen(self._color if live else QColor(TEXT_DIM))
        painter.drawText(
            QRectF(0, 0, width, header_height),
            value_text,
            QTextOption(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
        )

        # Faint grid
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
        for i in range(4):
            y = plot.top() + plot.height() * i / 3.0
            painter.drawLine(QPointF(0, y), QPointF(width, y))

        painter.save()
        painter.setClipRect(plot.adjusted(0, -3, 0, 3))

        # Warning threshold (dashed red)
        if self._threshold is not None and self._threshold < top:
            painter.setPen(QPen(QColor(255, 69, 58, 140), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(0, y_of(self._threshold)), QPointF(width, y_of(self._threshold)))

        # Split into segments wherever the data had a gap
        segments, current, previous_t = [], [], None
        for t, v in visible:
            if previous_t is not None and t - previous_t > self.GAP:
                segments.append(current)
                current = []
            current.append(QPointF(x_of(t), y_of(v)))
            previous_t = t
        if current:
            segments.append(current)

        fill = QLinearGradient(0, plot.top(), 0, plot.bottom())
        fill_top = QColor(self._color)
        fill_top.setAlpha(85)
        fill_bottom = QColor(self._color)
        fill_bottom.setAlpha(0)
        fill.setColorAt(0.0, fill_top)
        fill.setColorAt(1.0, fill_bottom)

        line_pen = QPen(self._color, 2)
        line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        for points in segments:
            if len(points) < 2:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(self._color))
                painter.drawEllipse(points[0], 2.0, 2.0)
                continue
            line = self._smooth_path(points)
            area = QPainterPath(line)
            area.lineTo(points[-1].x(), plot.bottom())
            area.lineTo(points[0].x(), plot.bottom())
            area.closeSubpath()
            painter.fillPath(area, QBrush(fill))
            painter.setPen(line_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(line)

        # Glowing dot on the newest point
        if live and segments:
            end = segments[-1][-1]
            glow = QColor(self._color)
            glow.setAlpha(70)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(end, 6.0, 6.0)
            painter.setBrush(QBrush(QColor(TEXT)))
            painter.drawEllipse(end, 2.6, 2.6)
        painter.restore()


class PayloadLabel(QLabel):
    """Big command letter on a frosted tile; its colour cross-fades when the command changes."""

    def __init__(self, text='S', parent=None):
        super().__init__(text, parent)
        self._color = QColor(RED)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_color)

    def _on_color(self, value):
        self._color = QColor(value)
        self.update()

    def set_command(self, text, color):
        self.setText(text)
        self._anim.stop()
        self._anim.setStartValue(QColor(self._color))
        self._anim.setEndValue(QColor(color))
        self._anim.start()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(255, 255, 255, 28), 1))
        painter.setBrush(QBrush(QColor(0, 0, 0, 100)))
        painter.drawRoundedRect(rect, 16, 16)

        # Soft glow behind the letter, in the current command colour
        card = QPainterPath()
        card.addRoundedRect(rect, 16, 16)
        glow = QRadialGradient(rect.center(), min(rect.width(), rect.height()) * 0.95)
        glow_in = QColor(self._color)
        glow_in.setAlpha(62)
        glow_out = QColor(self._color)
        glow_out.setAlpha(0)
        glow.setColorAt(0.0, glow_in)
        glow.setColorAt(1.0, glow_out)
        painter.save()
        painter.setClipPath(card)
        painter.fillRect(rect, QBrush(glow))
        painter.restore()

        font = ui_font(10, QFont.Weight.Bold)
        font.setPixelSize(52)
        painter.setFont(font)
        painter.setPen(self._color)
        painter.drawText(rect, self.text(), QTextOption(Qt.AlignmentFlag.AlignCenter))


class KeyHintsWidget(QWidget):
    """W / A S D keycaps that light up (and press down slightly) for the active command."""

    KEYS = ('W', 'A', 'S', 'D')
    GRID = {'W': (1, 0), 'A': (0, 1), 'S': (1, 1), 'D': (2, 1)}
    COMMAND_KEYS = {
        'F': ('W',), 'B': ('S',),
        'FL': ('W', 'A'), 'FR': ('W', 'D'),
        'BL': ('S', 'A'), 'BR': ('S', 'D'),
    }
    CAP = 34
    GAP = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(3 * self.CAP + 2 * self.GAP, 2 * self.CAP + self.GAP + 2)
        self._levels = {key: 0.0 for key in self.KEYS}
        self._targets = {key: 0.0 for key in self.KEYS}
        self._color = QColor(GREEN)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._step)

    def set_command(self, command, color):
        keys = self.COMMAND_KEYS.get(command, ())
        if keys:
            self._color = QColor(color)  # keep the old colour while keys fade out on stop
        for key in self.KEYS:
            self._targets[key] = 1.0 if key in keys else 0.0
        if not self._timer.isActive():
            self._timer.start()

    def _step(self):
        settled = True
        for key in self.KEYS:
            diff = self._targets[key] - self._levels[key]
            if abs(diff) > 0.01:
                self._levels[key] += diff * 0.35
                settled = False
            else:
                self._levels[key] = self._targets[key]
        self.update()
        if settled:
            self._timer.stop()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(ui_font(10.5, QFont.Weight.Bold))
        for key in self.KEYS:
            col, row = self.GRID[key]
            level = self._levels[key]
            rect = QRectF(
                col * (self.CAP + self.GAP) + 0.5,
                row * (self.CAP + self.GAP) + 0.5 + level * 2.0,  # lit keys sink a little
                self.CAP - 1,
                self.CAP - 1,
            )
            painter.setPen(QPen(QColor(255, 255, 255, 46), 1))
            painter.setBrush(QBrush(QColor(255, 255, 255, 22)))
            painter.drawRoundedRect(rect, 9, 9)
            if level > 0.01:
                lit = QColor(self._color)
                lit.setAlpha(int(175 * level))
                edge = QColor(self._color).lighter(150)
                edge.setAlpha(int(230 * level))
                painter.setPen(QPen(edge, 1))
                painter.setBrush(QBrush(lit))
                painter.drawRoundedRect(rect, 9, 9)
            painter.setPen(QColor(TEXT if level > 0.5 else TEXT_DIM))
            painter.drawText(rect, key, QTextOption(Qt.AlignmentFlag.AlignCenter))


class Toast(QWidget):
    """Small glass notification that slides in at the top, then fades away by itself."""

    LEVEL_COLORS = {'info': BLUE, 'warning': ORANGE, 'error': RED}

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFont(ui_font(10.5, QFont.Weight.DemiBold))
        self._text = ''
        self._color = QColor(ORANGE)
        self._level = 0.0
        self._target = 0.0

        self._anim = QVariantAnimation(self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_level)
        self._anim.finished.connect(self._on_finished)

        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.timeout.connect(lambda: self._glide(0.0, 340, QEasingCurve.Type.InCubic))
        self.hide()

    def show_message(self, text, level='warning', hold_ms=3000):
        self._text = text
        self._color = QColor(self.LEVEL_COLORS.get(level, ORANGE))
        parent_width = self.parentWidget().width() if self.parentWidget() else 800
        width = min(parent_width - 40, self.fontMetrics().horizontalAdvance(text) + 70)
        self.resize(max(180, width), 44)
        self.reposition()
        self._hold.stop()
        self.show()
        self.raise_()
        self._glide(1.0, 240, QEasingCurve.Type.OutCubic)
        self._hold.start(hold_ms)

    def reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        x = (parent.width() - self.width()) // 2
        y = 16 - int((1.0 - self._level) * 14)  # slides down into place
        self.move(x, y)

    def _glide(self, target, duration, curve):
        self._target = target
        self._anim.stop()
        self._anim.setDuration(duration)
        self._anim.setEasingCurve(curve)
        self._anim.setStartValue(float(self._level))
        self._anim.setEndValue(float(target))
        self._anim.start()

    def _on_level(self, value):
        self._level = float(value)
        self.reposition()
        self.update()

    def _on_finished(self):
        if self._target == 0.0 and self._level <= 0.01:
            self.hide()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._level)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = rect.height() / 2
        pill = QPainterPath()
        pill.addRoundedRect(rect, radius, radius)
        painter.fillPath(pill, QBrush(QColor(28, 30, 34, 238)))
        painter.setPen(QPen(QColor(255, 255, 255, 75), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(pill)

        center = QPointF(rect.left() + 24, rect.center().y())
        glow = QColor(self._color)
        glow.setAlpha(70)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(center, 9, 9)
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(center, 5, 5)

        painter.setPen(QColor(TEXT))
        painter.setFont(self.font())
        painter.drawText(
            QRectF(rect.left() + 44, rect.top(), rect.width() - 56, rect.height()),
            self._text,
            QTextOption(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
        )


class UltrasonicRadarWidget(QWidget):
    """Compact semicircular radar display for the ultrasonic telemetry card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setMinimumWidth(230)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._readings = []
        self._angle = None
        self._distance = None
        self._status = 'WAITING FOR RADAR DATA'
        self._display_angle = 90.0
        self._sweep_dir = 1.0

        # A faint ring expands from the sensor every couple of seconds.
        self._ping = 0.0
        self._ping_timer = QTimer(self)
        self._ping_timer.setInterval(40)
        self._ping_timer.timeout.connect(self._tick_ping)
        self._ping_timer.start()

        # The sweep line glides to each new reading instead of snapping.
        self._sweep_anim = QVariantAnimation(self)
        self._sweep_anim.setDuration(160)
        self._sweep_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._sweep_anim.valueChanged.connect(self._on_sweep_value)

    def _tick_ping(self):
        self._ping = (self._ping + 0.018) % 1.0
        self.update()

    def _on_sweep_value(self, value):
        value = float(value)
        if abs(value - self._display_angle) > 0.01:
            self._sweep_dir = 1.0 if value > self._display_angle else -1.0
        self._display_angle = value
        self.update()

    def update_reading(self, angle, distance_cm):
        self._angle = angle
        self._distance = distance_cm
        self._readings.append((float(angle), float(distance_cm)))
        self._readings = self._readings[-45:]
        self._status = 'NO ECHO / OUT OF RANGE' if distance_cm > 35 else 'RADAR LIVE'

        self._sweep_anim.stop()
        self._sweep_anim.setStartValue(float(self._display_angle))
        self._sweep_anim.setEndValue(float(angle))
        self._sweep_anim.start()
        self.update()

    def set_status(self, status):
        if status != self._status:
            self._status = status
            self.update()

    def reset_reading(self, status):
        self._angle = None
        self._distance = None
        self._readings.clear()
        self._status = status
        self.update()

    @staticmethod
    def _endpoint(center_x, center_y, radius, angle):
        radians = math.radians(angle)
        return QPointF(
            center_x + radius * math.cos(radians),
            center_y - radius * math.sin(radians),
        )

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        panel = self.rect().adjusted(6, 6, -6, -4)
        footer_height = 36
        center_x = float(panel.center().x())
        center_y = float(panel.bottom() - footer_height)
        radius = max(20.0, min(panel.width() / 2.0 - 6.0, panel.height() - footer_height - 8.0))
        bounds = QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)

        # Dial face
        face = QPainterPath()
        face.moveTo(center_x, center_y)
        face.arcTo(bounds, 0, 180)
        face.closeSubpath()
        painter.fillPath(face, QBrush(QColor(0, 0, 0, 120)))

        # Range rings
        for fraction in (0.33, 0.66, 1.0):
            ring_radius = radius * fraction
            ring_pen = QPen(QColor(255, 255, 255, 70 if fraction == 1.0 else 34), 1)
            ring_pen.setCosmetic(True)
            painter.setPen(ring_pen)
            painter.drawArc(
                QRectF(center_x - ring_radius, center_y - ring_radius, ring_radius * 2, ring_radius * 2),
                0,
                180 * 16,
            )

        # Ping ring
        ping_radius = radius * self._ping
        painter.setPen(QPen(QColor(10, 132, 255, int(75 * (1.0 - self._ping))), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(
            QRectF(center_x - ping_radius, center_y - ping_radius, ping_radius * 2, ping_radius * 2),
            0,
            180 * 16,
        )

        # Spokes
        spoke_pen = QPen(QColor(255, 255, 255, 24), 1)
        spoke_pen.setCosmetic(True)
        painter.setPen(spoke_pen)
        for spoke_angle in (0, 45, 90, 135, 180):
            painter.drawLine(
                QPointF(center_x, center_y),
                self._endpoint(center_x, center_y, radius, spoke_angle),
            )

        # Ring labels
        painter.setFont(ui_font(7.5))
        painter.setPen(QColor(TEXT_DIM))
        for fraction, label in ((0.33, '12'), (0.66, '23'), (1.0, '35 cm')):
            ring_radius = radius * fraction
            painter.drawText(QPointF(center_x + ring_radius - 26, center_y - 5), label)

        # Detected objects as fading dots
        painter.setPen(Qt.PenStyle.NoPen)
        for index, (reading_angle, distance_cm) in enumerate(self._readings):
            if distance_cm > 35:
                continue
            distance_ratio = min(max(distance_cm, 0.0), 35.0) / 35.0
            endpoint = self._endpoint(center_x, center_y, radius * distance_ratio, reading_angle)
            color = QColor(RED if distance_cm <= 20 else TEAL)
            color.setAlpha(min(235, 50 + index * 4))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(endpoint, 3.5, 3.5)

        # Soft fan trailing the sweep line
        has_data = self._angle is not None
        if has_data:
            trail, steps = 26.0, 8
            direction = -self._sweep_dir
            for step in range(steps):
                start = self._display_angle + direction * trail * step / steps
                end = self._display_angle + direction * trail * (step + 1) / steps
                low, high = max(0.0, min(start, end)), min(180.0, max(start, end))
                if high <= low:
                    continue
                wedge = QPainterPath()
                wedge.moveTo(center_x, center_y)
                wedge.arcTo(bounds, low, high - low)
                wedge.closeSubpath()
                fan_color = QColor(BLUE)
                fan_color.setAlpha(int(70 * (1.0 - step / steps)))
                painter.fillPath(wedge, QBrush(fan_color))

        sweep_color = QColor(BLUE if has_data else '#6E6E78')
        sweep_pen = QPen(sweep_color, 2)
        sweep_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(sweep_pen)
        painter.drawLine(
            QPointF(center_x, center_y),
            self._endpoint(center_x, center_y, radius, self._display_angle),
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(TEXT)))
        painter.drawEllipse(QPointF(center_x, center_y), 3.5, 3.5)

        # Footer
        footer_top = panel.bottom() - footer_height + 8
        detected = not (self._distance is None or self._distance > 35)
        object_text = 'OBJECT DETECTED' if detected else 'NO ECHO / OUT OF RANGE'

        painter.setFont(ui_font(8.5, QFont.Weight.DemiBold))
        painter.setPen(QColor(TEXT if detected else TEXT_DIM))
        painter.drawText(
            QRectF(panel.left(), footer_top, panel.width(), 14),
            Qt.AlignmentFlag.AlignLeft,
            object_text.capitalize(),
        )

        distance_text = '--' if self._distance is None else str(int(self._distance))
        angle_text = '--' if self._angle is None else str(int(self._angle))
        painter.setFont(ui_font(8.5))
        painter.setPen(QColor(TEXT_DIM))
        painter.drawText(
            QRectF(panel.left(), footer_top + 15, panel.width(), 14),
            Qt.AlignmentFlag.AlignLeft,
            f'Angle {angle_text}°    Distance {distance_text} cm',
        )

        if self._status.upper() != object_text:
            status_color = GREEN
            if 'OUT' in self._status or 'WAITING' in self._status:
                status_color = YELLOW
            if 'OFFLINE' in self._status or 'NO RADAR' in self._status:
                status_color = RED
            painter.setPen(QColor(status_color))
            painter.setFont(ui_font(8.5, QFont.Weight.DemiBold))
            painter.drawText(
                QRectF(panel.left(), footer_top, panel.width(), 14),
                Qt.AlignmentFlag.AlignRight,
                self._status.capitalize(),
            )


class MADDashboard(BackdropMixin, QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Project MANUS AD LUNAM - Command & Control Center')
        # 1440x950 (with the header bar) gives the ultra-wide rover feed (2712x1220) almost exactly its own shape;
        # the window is clamped to the screen and centred.
        width, height = 1440, 950
        screen = self.screen()
        if screen is not None:
            avail = screen.availableGeometry()
            width = min(width, avail.width() - 40)
            height = min(height, avail.height() - 40)
            self.setGeometry(
                avail.x() + (avail.width() - width) // 2,
                avail.y() + (avail.height() - height) // 2,
                width,
                height,
            )
        else:
            self.setGeometry(100, 100, width, height)
        self.setFont(ui_font(10))

        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, 'icon.png')

        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 1. Core Modules
        self.detector = HandDetector()
        self.controller = GestureController()
        self.sender = SerialSender()
        self.is_serial_connected = False
        self.serial_connect_worker = None

        # Telemetry & Input Tracking
        self.last_frame_time = time.monotonic()
        self._interval_ms = None        # smoothed frame interval
        self._latency_ui_time = 0.0     # throttles the label repaint
        self.current_payload = 'S'
        self.pressed_keys = set()  # Tracks held WASD keys
        self.last_radar_update_time = None
        self._intro_played = False
        self._rover_focus = False         # rover fullscreen view
        self._was_maximized = False
        self._notify_times = {}
        self._event_log = deque(maxlen=500)  # kept in memory and echoed to the console
        self._radar_alert_until = 0.0
        self.toast = None                 # created in init_ui

        # The link dot pulses while connecting.
        self._link_state = 'disconnected'
        self._link_detail = ''
        self._link_phase = 0.0
        self._link_pulse = QTimer(self)
        self._link_pulse.setInterval(60)
        self._link_pulse.timeout.connect(self._pulse_link)

        # The speed readout counts smoothly toward the slider value.
        self._speed_shown = 100.0
        self._speed_anim = QVariantAnimation(self)
        self._speed_anim.setDuration(200)
        self._speed_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._speed_anim.valueChanged.connect(self._on_speed_anim)

        # Camera Flip Controls
        self.gesture_flip_horz = False
        self.gesture_flip_180 = True
        self.rover_flip_horz = False
        self.rover_flip_180 = True

        # Default Camera Sources
        self.GESTURE_CAM_INDEX = 0
        self.ROVER_CAM_INDEX = None

        # Threads are created below; flip handlers only touch them after startup.
        self.gesture_thread = None
        self.rover_thread = None

        # Prompt Modal Dialog for Sources
        self.prompt_source_control()

        # 2. Build User Interface Layout
        self.init_ui()

        # Serial open/reboot wait runs in a worker; the dashboard remains responsive.
        self.reconnect_serial()

        # Poll the existing serial connection without blocking the GUI thread.
        self.radar_timer = QTimer(self)
        self.radar_timer.timeout.connect(self.poll_radar_telemetry)
        self.radar_timer.start(50)

        # 3. Initialize Camera Threads
        if self.GESTURE_CAM_INDEX is not None:
            self.gesture_thread = CameraThread(source=self.GESTURE_CAM_INDEX, flip=-1, detector=self.detector)
            self.gesture_thread.frame_processed.connect(self.update_gesture_feed)
            self.gesture_thread.status_changed.connect(self.update_gesture_camera_status)
            self.gesture_thread.start()
        else:
            self.update_gesture_camera_status('Not configured')

        if self.ROVER_CAM_INDEX is not None:
            self.rover_thread = CameraThread(source=self.ROVER_CAM_INDEX, flip=-1, detector=None)
            self.rover_thread.frame_processed.connect(self.update_rover_feed)
            self.rover_thread.status_changed.connect(self.update_rover_camera_status)
            self.rover_thread.start()
        else:
            self.update_rover_camera_status('Not configured')

        # Window fades in on first show.
        self.setWindowOpacity(0.0)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._intro_played:
            self._intro_played = True
            self._intro_anim = QPropertyAnimation(self, b'windowOpacity', self)
            self._intro_anim.setDuration(260)
            self._intro_anim.setStartValue(0.0)
            self._intro_anim.setEndValue(1.0)
            self._intro_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._intro_anim.start()
            self._run_intro()

    def _run_intro(self):
        """Fade the header and cards in one after another, then drop the effects (they cost speed)."""
        self._intro_anims = []
        for index, widget in enumerate(self._intro_boxes):
            effect = widget.graphicsEffect()
            if effect is None:
                continue
            anim = QPropertyAnimation(effect, b'opacity', self)
            anim.setDuration(420)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(
                lambda w=widget: QTimer.singleShot(0, lambda: w.setGraphicsEffect(None))
            )
            QTimer.singleShot(90 + index * 75, anim.start)
            self._intro_anims.append(anim)
        QTimer.singleShot(2500, self._clear_intro_effects)  # failsafe: never leave anything invisible

    def _clear_intro_effects(self):
        for widget in self._intro_boxes:
            if widget.graphicsEffect() is not None:
                widget.setGraphicsEffect(None)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.toast is not None and self.toast.isVisible():
            self.toast.reposition()

    def prompt_source_control(self):
        dialog = SourceControlDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            g_src, r_src = dialog.get_sources()
            self.GESTURE_CAM_INDEX = g_src
            self.ROVER_CAM_INDEX = r_src

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _camera_controls(self, flip_180_on, flip_horz_on):
        """Status text on the left, Rotate / Mirror pills on the right."""
        status_label = QLabel()
        self._style_status(status_label, 'Waiting for source')

        btn_180 = make_button('Rotate 180°', 'pill', checkable=True, focusable=False)
        btn_180.setChecked(flip_180_on)
        btn_horz = make_button('Mirror', 'pill', checkable=True, focusable=False)
        btn_horz.setChecked(flip_horz_on)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(status_label)
        row.addStretch()
        row.addWidget(btn_180)
        row.addWidget(btn_horz)
        return row, status_label, btn_180, btn_horz

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.setStyleSheet(APPLE_QSS)

        self.header = HeaderBar()
        self.header.set_chip('esp', 'ESP32 · offline', RED)
        self.header.set_chip('gesture', 'Gesture · waiting', YELLOW)
        self.header.set_chip('rover', 'Rover · waiting', YELLOW)

        # --- Rover camera (hero) ---
        self.rover_box = GlassBox('Rover Camera')
        rover_vbox = QVBoxLayout(self.rover_box)
        rover_vbox.setContentsMargins(0, 0, 0, 0)
        rover_vbox.setSpacing(10)
        self.rover_feed_label = VideoLabel('Connecting to Camera Stream...', radius=14)
        self.rover_feed_label.setMinimumSize(480, round(480 * ROVER_RES[1] / ROVER_RES[0]))
        rover_vbox.addWidget(self.rover_feed_label, stretch=1)
        (rover_controls, self.rover_status_label,
         self.rover_flip_btn_180, self.rover_flip_btn_horz) = self._camera_controls(
            self.rover_flip_180, self.rover_flip_horz
        )
        self.rover_flip_btn_180.clicked.connect(self.flip_rover_180)
        self.rover_flip_btn_horz.clicked.connect(self.flip_rover_horz)
        self.rover_fullscreen_btn = make_button('Fullscreen', 'pill', focusable=False)
        self.rover_fullscreen_btn.setToolTip('Fullscreen rover view (F11, Esc to exit)')
        self.rover_fullscreen_btn.clicked.connect(self.toggle_rover_fullscreen)
        rover_controls.addWidget(self.rover_fullscreen_btn)
        rover_vbox.addLayout(rover_controls)

        # --- Operator gesture camera ---
        self.gesture_box = GlassBox('Operator Gesture Feed')
        gesture_vbox = QVBoxLayout(self.gesture_box)
        gesture_vbox.setContentsMargins(0, 0, 0, 0)
        gesture_vbox.setSpacing(10)
        self.gesture_feed_label = VideoLabel('Initializing Video Stream...', radius=12)
        self.gesture_feed_label.setMinimumSize(288, round(288 * GESTURE_RES[1] / GESTURE_RES[0]))
        gesture_vbox.addWidget(self.gesture_feed_label, stretch=1)
        (gesture_controls, self.gesture_status_label,
         self.gesture_flip_btn_180, self.gesture_flip_btn_horz) = self._camera_controls(
            self.gesture_flip_180, self.gesture_flip_horz
        )
        self.gesture_flip_btn_180.clicked.connect(self.flip_gesture_180)
        self.gesture_flip_btn_horz.clicked.connect(self.flip_gesture_horz)
        gesture_vbox.addLayout(gesture_controls)

        # --- Ultrasonic radar ---
        self.radar_box = GlassBox('Ultrasonic Range')
        radar_vbox = QVBoxLayout(self.radar_box)
        radar_vbox.setContentsMargins(0, 0, 0, 0)
        self.radar_visual = UltrasonicRadarWidget()
        radar_vbox.addWidget(self.radar_visual)

        # --- Live telemetry ---
        self.telemetry_box = GlassBox('Live Telemetry')
        telemetry_vbox = QVBoxLayout(self.telemetry_box)
        telemetry_vbox.setContentsMargins(0, 0, 0, 0)
        telemetry_vbox.setSpacing(10)
        self.radar_graph = TelemetryGraph(
            'Radar distance (closest)', 'cm', TEAL, cap=100, threshold=RADAR_ALERT_CM, mode='min'
        )
        self.latency_graph = TelemetryGraph('Gesture frame interval', 'ms', BLUE, min_span=60.0, mode='avg')
        telemetry_vbox.addWidget(self.radar_graph, stretch=1)
        telemetry_vbox.addWidget(self.latency_graph, stretch=1)

        # --- System link ---
        self.link_box = GlassBox('System Link')
        link_vbox = QVBoxLayout(self.link_box)
        link_vbox.setContentsMargins(0, 0, 0, 0)
        link_vbox.setSpacing(8)
        self.port_label = QLabel()
        self.port_label.setTextFormat(Qt.TextFormat.RichText)
        self._set_link_status(
            'connected' if self.is_serial_connected else 'disconnected',
            self.sender.port or '',
        )
        self.latency_label = QLabel("Gesture frame interval  <b>-- ms</b>")
        self.latency_label.setTextFormat(Qt.TextFormat.RichText)
        self.latency_label.setStyleSheet(f'color: {TEXT_DIM}; font-size: 12px;')
        self.reconnect_btn = RetryButton()
        self.reconnect_btn.clicked.connect(self.reconnect_serial)
        self.port_label.setWordWrap(True)
        link_top = QHBoxLayout()
        link_top.setSpacing(8)
        link_top.addWidget(self.port_label, stretch=1)
        link_top.addWidget(self.reconnect_btn)
        link_vbox.addLayout(link_top)
        link_vbox.addWidget(self.latency_label)
        link_vbox.addStretch()

        # --- Payload ---
        self.payload_box = GlassBox('Payload')
        payload_vbox = QVBoxLayout(self.payload_box)
        payload_vbox.setContentsMargins(0, 0, 0, 0)
        payload_vbox.setSpacing(10)
        self.payload_sub = make_label('Active transmission command', 'caption', Qt.AlignmentFlag.AlignCenter)
        self.key_hints = KeyHintsWidget()
        self.payload_label = PayloadLabel('S')
        self.payload_label.setMinimumHeight(84)
        self._style_payload('S')
        payload_row = QHBoxLayout()
        payload_row.setSpacing(12)
        payload_row.addWidget(self.key_hints, alignment=Qt.AlignmentFlag.AlignVCenter)
        payload_row.addWidget(self.payload_label, stretch=1)
        payload_vbox.addWidget(self.payload_sub)
        payload_vbox.addLayout(payload_row, stretch=1)

        # --- Rover speed ---
        self.speed_box = GlassBox('Rover Speed')
        speed_vbox = QVBoxLayout(self.speed_box)
        speed_vbox.setContentsMargins(0, 0, 0, 0)
        speed_vbox.setSpacing(6)

        self.speed_sub = make_label('Drive speed limit', 'caption', Qt.AlignmentFlag.AlignCenter)
        self.speed_value_label = SpeedDial('100%')

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(0, 100)
        self.speed_slider.setValue(100)
        self.speed_pwm = round(100 * 255 / 100)
        self.speed_slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self.speed_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.speed_slider.setMinimumHeight(26)
        self.speed_slider.valueChanged.connect(self.update_speed_display)

        speed_scale_hbox = QHBoxLayout()
        speed_scale_hbox.setContentsMargins(0, 0, 0, 0)
        speed_slow_label = make_label('Slow', 'caption')
        speed_fast_label = make_label('Fast', 'caption', Qt.AlignmentFlag.AlignRight)
        speed_scale_hbox.addWidget(speed_slow_label)
        speed_scale_hbox.addStretch()
        speed_scale_hbox.addWidget(speed_fast_label)

        self.speed_status_label = make_label('Ready for input', 'caption', Qt.AlignmentFlag.AlignCenter)

        speed_vbox.addWidget(self.speed_sub)
        speed_vbox.addWidget(self.speed_value_label, stretch=1)
        speed_vbox.addWidget(self.speed_slider)
        speed_vbox.addLayout(speed_scale_hbox)
        speed_vbox.addWidget(self.speed_status_label)

        self.append_log('[SYS] Project MANUS AD LUNAM Control Hub Active.')

        # --- Layout -----------------------------------------------------
        #   ┌───────────────────────────┬──────────┐
        #   │   Rover camera (hero)     │ System   │
        #   │                           │ link     │
        #   ├────────────┬──────────────┤ Payload  │
        #   │ Gesture    │ Ultrasonic   │ Rover    │
        #   │ feed       │ range        │ speed    │
        #   └────────────┴──────────────┴──────────┘
        side_col = QVBoxLayout()
        side_col.setSpacing(4)
        side_col.addWidget(self.link_box, stretch=2)
        side_col.addWidget(self.payload_box, stretch=3)
        side_col.addWidget(self.speed_box, stretch=3)

        root = QVBoxLayout(central_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.header)
        grid = self.grid = QGridLayout()
        root.addLayout(grid, stretch=1)
        grid.setContentsMargins(20, 12, 20, 20)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)  # each card already reserves room for its title
        grid.addWidget(self.rover_box, 0, 0, 1, 3)
        grid.addWidget(self.gesture_box, 1, 0)
        grid.addWidget(self.radar_box, 1, 1)
        grid.addWidget(self.telemetry_box, 1, 2)
        grid.addLayout(side_col, 0, 3, 2, 1)
        grid.setColumnStretch(0, 5)  # gesture feed
        grid.setColumnStretch(1, 4)  # radar
        grid.setColumnStretch(2, 5)  # telemetry
        grid.setColumnStretch(3, 0)  # side column
        grid.setColumnMinimumWidth(3, 290)
        grid.setRowStretch(0, 8)  # rover feed is wide and gets nearly all spare height
        grid.setRowStretch(1, 1)

        # Hidden in the rover fullscreen view so the camera gets the whole window.
        self._focus_hidden = [
            self.header, self.gesture_box, self.radar_box, self.telemetry_box,
            self.link_box, self.payload_box, self.speed_box,
        ]
        self.toast = Toast(self)

        # Cards start invisible and fade in one after another (see _run_intro).
        self._intro_boxes = [
            self.header, self.rover_box, self.gesture_box, self.radar_box,
            self.link_box, self.payload_box, self.speed_box, self.telemetry_box,
        ]
        for widget in self._intro_boxes:
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)

    # ------------------------------------------------------------------
    # Small UI helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _style_status(label, status):
        color = GREEN if status == 'Online' else YELLOW
        if status in {'Stopped', 'Not configured'}:
            color = TEXT_DIM
        label.setText(f'●  {status}')
        label.setStyleSheet(f'color: {color}; font-size: 12px; font-weight: 500;')

    @staticmethod
    def _status_color(status):
        if status == 'Online':
            return GREEN
        if status in {'Stopped', 'Not configured'}:
            return TEXT_DIM
        return YELLOW

    def _update_cam_chip(self, key, name, status):
        if status == 'Online':
            short = 'live'
        elif status.startswith('Connecting'):
            short = 'connecting'
        elif status in {'Stopped', 'Not configured'}:
            short = 'off'
        else:
            short = 'retrying'
        self.header.set_chip(key, f'{name} · {short}', self._status_color(status))

    def _set_link_status(self, state, detail=''):
        self._link_state = state
        self._link_detail = detail
        if state == 'connecting':
            self._link_phase = 0.0
            if not self._link_pulse.isActive():
                self._link_pulse.start()
        else:
            self._link_pulse.stop()
        self._render_link()

    def _pulse_link(self):
        self._link_phase += 0.18
        self._render_link()

    def _render_link(self):
        colors = {'connected': GREEN, 'connecting': YELLOW, 'disconnected': RED}
        detail = self._link_detail
        labels = {
            'connected': f'Connected ({detail})' if detail else 'Connected',
            'connecting': 'Connecting...',
            'disconnected': 'Disconnected',
        }
        color = QColor(colors[self._link_state])
        dot = QColor(color)
        if self._link_state == 'connecting':
            # Breathe between a dim grey and the full colour.
            t = 0.5 + 0.5 * math.sin(self._link_phase)
            base = QColor('#3A3A42')
            dot = QColor(
                int(base.red() + (color.red() - base.red()) * t),
                int(base.green() + (color.green() - base.green()) * t),
                int(base.blue() + (color.blue() - base.blue()) * t),
            )
        self.port_label.setText(
            f"<span style='color: {dot.name()}; font-size: 15px;'>&#9679;</span>&nbsp;&nbsp;"
            f"ESP32 Link&nbsp;&nbsp;<span style='color: {color.name()}; font-weight: 600;'>"
            f"{html.escape(labels[self._link_state])}</span>"
        )
        chip_labels = {
            'connected': f'ESP32 · {detail}' if detail else 'ESP32 · online',
            'connecting': 'ESP32 · connecting',
            'disconnected': 'ESP32 · offline',
        }
        self.header.set_chip('esp', chip_labels[self._link_state], colors[self._link_state])

    @staticmethod
    def _command_color(command):
        if command.startswith('F'):
            return GREEN
        if command.startswith('B'):
            return ORANGE
        return RED  # stop

    def _style_payload(self, command):
        color = self._command_color(command)
        self.payload_label.set_command(command, color)
        self.key_hints.set_command(command, color)

    def _refresh_overlay(self):
        """In fullscreen the hidden payload / speed cards are summarised in a chip on the video."""
        if self._rover_focus:
            self.rover_feed_label.set_overlay(
                f'{self.current_payload}    {self.speed_slider.value()}%',
                self._command_color(self.current_payload),
            )
        else:
            self.rover_feed_label.set_overlay(None)

    def notify(self, key, text, level='warning', cooldown=4.0):
        """Show a toast that dismisses itself after ~3 s; `cooldown` stops repeats from spamming."""
        if self.toast is None:
            return
        now = time.monotonic()
        if now - self._notify_times.get(key, -1e9) < cooldown:
            return
        self._notify_times[key] = now
        self.toast.show_message(text, level)

    def toggle_rover_fullscreen(self):
        entering = not self._rover_focus
        self._rover_focus = entering
        for widget in self._focus_hidden:
            widget.setVisible(not entering)
        self.grid.setColumnMinimumWidth(3, 0 if entering else 290)
        self.grid.setRowStretch(0, 1 if entering else 8)
        self.grid.setRowStretch(1, 0 if entering else 1)
        self.rover_fullscreen_btn.setText('Exit Fullscreen' if entering else 'Fullscreen')
        if entering:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()
        elif self._was_maximized:
            self.showMaximized()
        else:
            self.showNormal()
        self._refresh_overlay()

    def append_log(self, message):
        """Events no longer have a sidebar: they are kept in memory and echoed to the console."""
        self._event_log.append(message)
        try:
            print(message)
        except UnicodeEncodeError:
            pass

    # --- KEYBOARD CONTROLS ---
    def keyPressEvent(self, event):
        """Processes W, A, S, D key presses."""
        if event.isAutoRepeat():
            return  # Prevent OS key repeat flooding

        key = event.key()
        if key == Qt.Key.Key_F11 or (key == Qt.Key.Key_Escape and self._rover_focus):
            self.toggle_rover_fullscreen()
            return
        if key in (Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D):
            self.pressed_keys.add(key)
            self.process_keyboard_input()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Processes key release events."""
        if event.isAutoRepeat():
            return

        key = event.key()
        if key in self.pressed_keys:
            self.pressed_keys.remove(key)
            self.process_keyboard_input()
        else:
            super().keyReleaseEvent(event)

    def process_keyboard_input(self):
        """Evaluates active held WASD keys into rover commands."""
        has_w = Qt.Key.Key_W in self.pressed_keys
        has_s = Qt.Key.Key_S in self.pressed_keys
        has_a = Qt.Key.Key_A in self.pressed_keys
        has_d = Qt.Key.Key_D in self.pressed_keys

        cmd = "S"
        if has_w:
            if has_a:
                cmd = "FL"
            elif has_d:
                cmd = "FR"
            else:
                cmd = "F"
        elif has_s:
            if has_a:
                cmd = "BL"
            elif has_d:
                cmd = "BR"
            else:
                cmd = "B"

        self.dispatch_command(cmd)

    def dispatch_command(self, command):
        """Sends payload down serial line and updates UI if command changed."""
        if command != self.current_payload:
            self.current_payload = command
            self._style_payload(command)
            self._refresh_overlay()

            if self.is_serial_connected:
                if self.sender.send_command(command, self.speed_pwm):
                    self.append_log(f"[TX] Command Sent: '{command}'")
                else:
                    self.mark_serial_disconnected('Command write failed')
            else:
                self.append_log(f"[LOCAL] Command Evaluated: '{command}' (Serial Offline)")

    def update_speed_display(self, value):
        """Update the display and resend the active command at the new PWM speed."""
        self.speed_pwm = round(value * 255 / 100)
        self._speed_anim.stop()
        self._speed_anim.setStartValue(float(self._speed_shown))
        self._speed_anim.setEndValue(float(value))
        self._speed_anim.start()
        self._refresh_overlay()
        if self.is_serial_connected:
            if not self.sender.send_command(self.current_payload, self.speed_pwm):
                self.mark_serial_disconnected('Speed update write failed')

    def _on_speed_anim(self, value):
        self._speed_shown = float(value)
        self.speed_value_label.setText(f'{int(round(self._speed_shown))}%')

    def poll_radar_telemetry(self):
        """Read tagged distance samples from the transmitter's USB serial stream."""
        if self._radar_alert_until and time.monotonic() > self._radar_alert_until:
            self._radar_alert_until = 0.0
            self.radar_box.set_alert(False)

        if not self.is_serial_connected:
            return

        for angle, distance_cm in self.sender.read_radar_telemetry():
            self.last_radar_update_time = time.monotonic()
            if distance_cm > 35:
                status = 'NO ECHO / OUT OF RANGE'
            else:
                status = 'RADAR LIVE'
            self.radar_visual.update_reading(angle, distance_cm)
            self.radar_visual.set_status(status)
            if distance_cm > 0:
                self.radar_graph.add(distance_cm)
            if 0 < distance_cm <= RADAR_ALERT_CM:
                self._radar_alert_until = time.monotonic() + 1.0
                self.radar_box.set_alert(True)
                self.notify('obstacle', f'Obstacle within {RADAR_ALERT_CM} cm', 'warning', cooldown=4.0)

        if self.is_serial_connected and (
            self.sender.ser is None or not self.sender.ser.is_open
        ):
            self.mark_serial_disconnected('Telemetry read failed')

        if self.last_radar_update_time is None:
            if not self.is_serial_connected:
                self.radar_visual.set_status('SERIAL LINK OFFLINE')
            return

        if time.monotonic() - self.last_radar_update_time > 1.5:
            self.last_radar_update_time = None
            self.radar_visual.reset_reading('NO RADAR DATA')
            self._radar_alert_until = 0.0
            self.radar_box.set_alert(False)

    def update_gesture_feed(self, qt_image, raw_frame):
        now = time.monotonic()
        interval_ms = (now - self.last_frame_time) * 1000.0
        self.last_frame_time = now

        # Smooth the number and repaint the label at ~4 Hz instead of every frame.
        if self._interval_ms is None:
            self._interval_ms = interval_ms
        else:
            self._interval_ms = self._interval_ms * 0.8 + interval_ms * 0.2
        if now - self._latency_ui_time >= 0.25:
            self._latency_ui_time = now
            self.latency_label.setText(f"Gesture frame interval  <b>{int(self._interval_ms)} ms</b>")

        self.latency_graph.add(self._interval_ms)
        self.gesture_feed_label.set_frame(qt_image)

        # Only evaluate gestures if NO keyboard keys are being pressed
        if not self.pressed_keys:
            hands_data = self.detector.get_hand_info(raw_frame)
            command = self.controller.get_command(hands_data)
            self.dispatch_command(command)

    def update_rover_feed(self, qt_image, raw_frame):
        self.rover_feed_label.set_frame(qt_image)

    def update_gesture_camera_status(self, status):
        self._style_status(self.gesture_status_label, status)
        self._update_cam_chip('gesture', 'Gesture', status)
        self.gesture_box.set_active(status == 'Online')
        if status != 'Online':
            self.gesture_feed_label.clear_frame(status)
        if status.startswith(('Feed lost', 'Unavailable')):
            self.notify('cam-gesture', 'Gesture camera feed lost', 'warning', cooldown=10.0)

    def update_rover_camera_status(self, status):
        self._style_status(self.rover_status_label, status)
        self._update_cam_chip('rover', 'Rover', status)
        self.rover_box.set_active(status == 'Online')
        if status != 'Online':
            self.rover_feed_label.clear_frame(status)
        if status.startswith(('Feed lost', 'Unavailable')):
            self.notify('cam-rover', 'Rover camera feed lost', 'warning', cooldown=10.0)

    # --- Camera flip controls ---
    def _toggle_flip(self, camera, kind):
        """One flip mode at a time (cv2.flip takes a single code): none / mirror (1) / 180° (-1)."""
        horz = getattr(self, f'{camera}_flip_horz')
        rot = getattr(self, f'{camera}_flip_180')
        if kind == 'horz':
            horz = not horz
            if horz:
                rot = False
        else:
            rot = not rot
            if rot:
                horz = False
        setattr(self, f'{camera}_flip_horz', horz)
        setattr(self, f'{camera}_flip_180', rot)
        getattr(self, f'{camera}_flip_btn_horz').setChecked(horz)
        getattr(self, f'{camera}_flip_btn_180').setChecked(rot)

        thread = getattr(self, f'{camera}_thread')
        if thread and thread.isRunning():
            thread.flip = 1 if horz else (-1 if rot else 0)
            mode = 'FLIP HORZ' if horz else ('FLIP 180°' if rot else 'NO FLIP')
            self.append_log(f'[CAM] {camera.capitalize()} camera set to {mode} flip')

    def flip_gesture_horz(self):
        """Toggle horizontal flip for gesture camera"""
        self._toggle_flip('gesture', 'horz')

    def flip_gesture_180(self):
        """Toggle 180° flip for gesture camera"""
        self._toggle_flip('gesture', '180')

    def flip_rover_horz(self):
        """Toggle horizontal flip for rover camera"""
        self._toggle_flip('rover', 'horz')

    def flip_rover_180(self):
        """Toggle 180° flip for rover camera"""
        self._toggle_flip('rover', '180')

    # --- Serial link ---
    def reconnect_serial(self):
        if self.serial_connect_worker is not None and self.serial_connect_worker.isRunning():
            return

        self.is_serial_connected = False
        self.reconnect_btn.setEnabled(False)
        self.reconnect_btn.set_busy(True)
        self._set_link_status('connecting')
        self.append_log('[SYS] Attempting ESP32 re-connection...')
        self.serial_connect_worker = SerialConnectWorker(self.sender, self)
        self.serial_connect_worker.connection_finished.connect(self.on_serial_connect_finished)
        self.serial_connect_worker.start()

    def mark_serial_disconnected(self, reason):
        self.is_serial_connected = False
        self._set_link_status('disconnected')
        self.radar_visual.set_status('SERIAL LINK OFFLINE')
        self.append_log(f'[SYS] Serial connection lost: {reason}.')
        self._radar_alert_until = 0.0
        self.radar_box.set_alert(False)
        self.notify('serial', f'ESP32 link lost: {reason}', 'error', cooldown=1.0)

    def on_serial_connect_finished(self, connected, detail):
        self.is_serial_connected = connected
        self.reconnect_btn.setEnabled(True)
        self.reconnect_btn.set_busy(False)
        if connected:
            self._set_link_status('connected', detail)
            self.append_log(f'[SYS] Linked to ESP32 on port {detail}')
            if not self.sender.send_command(self.current_payload, self.speed_pwm):
                self.mark_serial_disconnected('Telemetry handshake failed')
        else:
            self._set_link_status('disconnected')
            self.append_log('[SYS] Search failed. No active ESP32 COM port.')
            self.notify('serial-connect', 'No ESP32 found. Plug it in, then reconnect', 'warning', cooldown=2.0)
            if detail:
                self.append_log(f'[SYS] Connection detail: {detail}')

    def closeEvent(self, event):
        if self.serial_connect_worker is not None and self.serial_connect_worker.isRunning():
            self.serial_connect_worker.wait(3000)
        if self.gesture_thread is not None:
            self.gesture_thread.stop()
        if self.rover_thread is not None:
            self.rover_thread.stop()
        self.sender.close()
        event.accept()

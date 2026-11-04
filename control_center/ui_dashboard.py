"""Control Center UI for Project MANUS AD LUNAM.

Single window, two pages over a shared lunar backdrop:
  * Mission Connect -- a compact card for stream sources and mobile-app pairing.
  * Command Center  -- the flight deck. The hero feed (rover by default) with
    drive command, speed and system link beneath it; the swappable laptop
    camera, radar and live telemetry in the right rail.

Sadiq's layout and glass design, with Hanoon's pieces merged in: the MANUS /
AD LUNAM brand mark, the plexus backdrop, live telemetry graphs, the system
link status list, keyboard key caps, fullscreen view, flip-mode fix and card
glow.

All hardware behaviour (serial, camera threads, gesture dispatch, radar polling)
is unchanged; this module only owns presentation. Visual tokens and the shared
widget vocabulary live in ui_theme.py.
"""

import math
import os
import time
from urllib.parse import urlsplit

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QConicalGradient,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# Project Hardware & Vision Modules
from gesture_controller import GestureController
from hand_detector import HandDetector
from serial_sender import SerialSender
from stream_manager import CameraThread

from ui_theme import (
    ACCENT,
    ACCENT_LIGHT,
    APP_STYLESHEET,
    BAD,
    CMD_STOP,
    INK,
    PAD_FEED,
    WARN,
    BrandMark,
    CommandLabel,
    DirectionIndicator,
    EventLogView,
    GlassCapsule,
    GlassCard,
    KeyCaps,
    NumeralLabel,
    PillButton,
    SpeedSlider,
    StarfieldBackground,
    StatusPill,
    StatusRow,
    TelemetryGraph,
    VideoSurface,
    app_font,
    caption_label,
    command_color,
    css,
    micro_font,
    numeral_font,
    tint,
    title_label,
)

RADAR_RANGE_CM = 35.0        # outer ring of the ultrasonic sweep
RADAR_DANGER_CM = 20.0       # inside this, echoes turn red and the radar card alerts
PAGE_FADE_MS = 300
KEYBOARD_MODE_HOLD_MS = 1500  # stay in keyboard mode briefly after the last key is released


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


class MissionConnectPage(QWidget):
    """Page 1: stream sources, in one compact card.

    Holds the authoritative source-validation logic. Field errors appear as
    inline captions rather than modal dialogs; the accepted values are exactly
    those the original SourceControlDialog accepted.
    """

    connect_requested = pyqtSignal()
    CARD_WIDTH = 480

    def __init__(self, parent=None, icon_path=None):
        super().__init__(parent)
        self.setObjectName('page')

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 28, 40, 28)
        outer.addStretch(1)

        column = QVBoxLayout()
        column.setSpacing(20)
        column.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        column.addLayout(self._build_header(icon_path))
        self.card = self._build_card()
        self.card.setFixedWidth(self.CARD_WIDTH)
        column.addWidget(self.card, alignment=Qt.AlignmentFlag.AlignHCenter)

        outer.addLayout(column)
        outer.addStretch(1)

    # -- construction -------------------------------------------------------
    def _build_header(self, icon_path):
        header = QVBoxLayout()
        header.setSpacing(6)
        header.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        if icon_path and os.path.exists(icon_path):
            mark = QLabel()
            mark.setPixmap(
                QPixmap(icon_path).scaled(
                    40, 40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.addWidget(mark, alignment=Qt.AlignmentFlag.AlignHCenter)

        title = QLabel('Manus Ad Lunam')
        title.setObjectName('appTitle')
        title.setFont(app_font(30, QFont.Weight.Bold, spacing=0.2))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(title)

        subtitle = QLabel('Source Control')
        subtitle.setObjectName('appSubtitle')
        subtitle.setFont(app_font(15, QFont.Weight.Normal))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(subtitle)
        return header

    def _build_card(self):
        card = GlassCard(parent=self, radius=30, padding=26, spacing=8)

        card.body.addWidget(caption_label('Laptop Camera'))
        self.gesture_input = QLineEdit('0')
        self.gesture_input.setPlaceholderText('0')
        self.gesture_input.returnPressed.connect(self.validate_and_accept)
        self.gesture_input.textChanged.connect(
            lambda: self._clear_error(self.gesture_input, self.gesture_error)
        )
        card.body.addWidget(self.gesture_input)
        gesture_help = QLabel('Gesture control. Camera index (0, 1, …) or a stream URL.')
        gesture_help.setObjectName('helper')
        card.body.addWidget(gesture_help)
        self.gesture_error = self._error_label()
        card.body.addWidget(self.gesture_error)

        card.body.addSpacing(6)
        card.body.addWidget(caption_label('Rover Stream'))
        self.rover_input = QLineEdit()
        self.rover_input.setPlaceholderText('http://192.168.1.20:8080')
        self.rover_input.returnPressed.connect(self.validate_and_accept)
        self.rover_input.textChanged.connect(
            lambda: self._clear_error(self.rover_input, self.rover_error)
        )
        card.body.addWidget(self.rover_input)
        rover_help = QLabel('http(s) or RTSP URL with a host. Leave blank to skip.')
        rover_help.setObjectName('helper')
        card.body.addWidget(rover_help)
        self.rover_error = self._error_label()
        card.body.addWidget(self.rover_error)

        card.body.addSpacing(10)

        self.submit_btn = PillButton('Connect Streams', variant='primary',
                                     glyph='arrow-right', height=48)
        self.submit_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.submit_btn.clicked.connect(self.validate_and_accept)
        card.body.addWidget(self.submit_btn)
        return card

    @staticmethod
    def _error_label():
        label = QLabel('')
        label.setObjectName('error')
        label.setWordWrap(True)
        label.hide()
        return label

    @staticmethod
    def _hairline():
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet(f'background-color: {css(INK, 0.10)};')
        return line

    # -- validation ---------------------------------------------------------
    @staticmethod
    def _is_stream_url(value):
        try:
            parsed = urlsplit(value)
            parsed.port  # Validate a provided port instead of accepting malformed URLs.
            return parsed.scheme.lower() in {"http", "https", "rtsp", "rtsps"} and bool(parsed.hostname)
        except ValueError:
            return False

    def _show_error(self, field, label, message):
        label.setText(message)
        label.show()
        field.setProperty('invalid', True)
        field.style().unpolish(field)
        field.style().polish(field)

    def _clear_error(self, field, label):
        if label.isVisible():
            label.hide()
            label.clear()
        if field.property('invalid'):
            field.setProperty('invalid', False)
            field.style().unpolish(field)
            field.style().polish(field)

    def validate_and_accept(self):
        gesture_val = self.gesture_input.text().strip()
        rover_val = self.rover_input.text().strip()

        self._clear_error(self.gesture_input, self.gesture_error)
        self._clear_error(self.rover_input, self.rover_error)
        valid = True

        if gesture_val and not (gesture_val.isdigit() or self._is_stream_url(gesture_val)):
            self._show_error(
                self.gesture_input,
                self.gesture_error,
                'Enter a non-negative camera index or a valid http(s)/rtsp stream URL, or leave it blank.',
            )
            valid = False

        if rover_val and not self._is_stream_url(rover_val):
            self._show_error(
                self.rover_input,
                self.rover_error,
                'Enter a URL with a host, such as http://192.168.1.20:8080, or leave it blank.',
            )
            valid = False

        if not valid:
            return
        self.connect_requested.emit()

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


class SourceControlDialog(QDialog):
    """Modal wrapper around MissionConnectPage.

    The dashboard hosts the source form as its first page, but this dialog is
    kept so the original entry point (and its validation API) still works for
    anything that reaches for it.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Source Control Configuration")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setStyleSheet(APP_STYLESHEET)
        self.setFont(app_font(14))

        self.page = MissionConnectPage(self)
        self.page.connect_requested.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.page)

        # Mirror the page's fields so existing attribute access keeps working.
        self.gesture_input = self.page.gesture_input
        self.rover_input = self.page.rover_input

    _is_stream_url = staticmethod(MissionConnectPage._is_stream_url)

    def validate_and_accept(self):
        self.page.validate_and_accept()

    def get_sources(self):
        return self.page.get_sources()


class UltrasonicRadarWidget(QWidget):
    """Semicircular ultrasonic scope with phosphor-style echo persistence.

    Each echo is stamped when it arrives and decays over TRAIL_SECONDS, like the
    afterglow on a real sweep display, so the trail fades on its own even when
    no new samples come in. The sweep fan glows only on its trailing side. On a
    short card the readout switches to a compact one-line footer.

    Public API is unchanged: update_reading / set_status / reset_reading, a
    35 cm range and rings at 12 / 23 / 35 cm.
    """

    FAN_DEGREES = 34.0
    FOOTER_HEIGHT = 80
    FOOTER_COMPACT = 48
    COMPACT_BELOW = 230     # widget height at which the footer compacts
    TRAIL_SECONDS = 2.6     # echo afterglow
    DECAY_FRAME_MS = 40     # repaint cadence while echoes are fading

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._readings = []           # (angle, distance_cm, monotonic stamp)
        self._angle = None
        self._distance = None
        self._status = 'WAITING FOR RADAR DATA'
        self._sweep_angle = 90.0
        self._sweep_dir = 1.0         # +1 counter-clockwise, -1 clockwise

        # Only runs while there is something fading; stops itself when clear.
        self._decay = QTimer(self)
        self._decay.setInterval(self.DECAY_FRAME_MS)
        self._decay.timeout.connect(self._decay_tick)

    # -- public API ---------------------------------------------------------
    def update_reading(self, angle, distance_cm):
        angle = float(angle)
        if angle != self._sweep_angle:
            self._sweep_dir = 1.0 if angle > self._sweep_angle else -1.0
        self._angle = angle
        self._distance = distance_cm
        self._sweep_angle = angle
        self._readings.append((angle, float(distance_cm), time.monotonic()))
        self._readings = self._readings[-180:]
        self._status = 'NO ECHO / OUT OF RANGE' if distance_cm > RADAR_RANGE_CM else 'RADAR LIVE'
        if not self._decay.isActive():
            self._decay.start()
        self.update()

    def set_status(self, status):
        if status != self._status:
            self._status = status
            self.update()

    def reset_reading(self, status):
        self._angle = None
        self._distance = None
        self._readings.clear()
        self._decay.stop()
        self._status = status
        self.update()

    def _decay_tick(self):
        cutoff = time.monotonic() - self.TRAIL_SECONDS
        self._readings = [reading for reading in self._readings if reading[2] >= cutoff]
        if not self._readings:
            self._decay.stop()
        self.update()

    # -- painting -----------------------------------------------------------
    @staticmethod
    def _endpoint(center_x, center_y, radius, angle):
        radians = math.radians(angle)
        return QPointF(
            center_x + radius * math.cos(radians),
            center_y - radius * math.sin(radians),
        )

    def _status_token(self):
        status = self._status.upper()
        if 'OFFLINE' in status or 'NO RADAR' in status:
            return BAD
        if 'OUT' in status or 'WAITING' in status:
            return WARN
        return ACCENT_LIGHT

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        bounds = QRectF(self.rect()).adjusted(4, 2, -4, -2)
        compact = bounds.height() < self.COMPACT_BELOW
        footer = self.FOOTER_COMPACT if compact else self.FOOTER_HEIGHT
        # Increase the multipliers to fill empty space while keeping the layout intact
        radius = max(24.0, min(bounds.width() / 2.0 - 4.0, bounds.height() - footer - 12.0))
        # Centre the scope + readout block vertically, so a tall card does not
        # leave all its spare room above the arc.
        block = radius + 12.0 + footer
        top = bounds.top() + max(0.0, (bounds.height() - block) / 2.0)
        panel = QRectF(bounds.left(), top, bounds.width(), block)
        center = QPointF(panel.center().x(), panel.bottom() - footer)

        self._paint_scope(painter, center, radius)
        self._paint_rings(painter, center, radius)
        self._paint_fan(painter, center, radius)
        self._paint_echoes(painter, center, radius)
        self._paint_hub(painter, center)
        self._paint_readout(painter, panel, footer, compact)

    def _paint_scope(self, painter, center, radius):
        """Dark backing for the arc, so the backdrop never competes with data."""
        scope = QPainterPath(center)
        scope.arcTo(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2),
                    0.0, 180.0)
        scope.closeSubpath()
        shade = QRadialGradient(center, radius)
        shade.setColorAt(0.0, tint('#000000', 0.42))
        shade.setColorAt(1.0, tint('#000000', 0.26))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shade))
        painter.drawPath(scope)

    def _paint_rings(self, painter, center, radius):
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for fraction in (0.34, 0.67, 1.0):
            ring = radius * fraction
            pen = QPen(tint(INK, 0.13 if fraction < 1.0 else 0.20), 1.0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawArc(
                QRectF(center.x() - ring, center.y() - ring, ring * 2, ring * 2),
                0, 180 * 16,
            )

        spoke = QPen(tint(INK, 0.07), 1.0)
        spoke.setCosmetic(True)
        painter.setPen(spoke)
        for angle in (0, 45, 90, 135, 180):
            painter.drawLine(center, self._endpoint(center.x(), center.y(), radius, angle))

        painter.setFont(micro_font(9))
        painter.setPen(QPen(tint(INK, 0.36)))
        for fraction, label in ((0.34, '12'), (0.67, '23'), (1.0, '35')):  # cm
            ring = radius * fraction
            painter.drawText(
                QRectF(center.x() + ring - 46, center.y() - 17, 42, 14),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                label,
            )

    def _paint_fan(self, painter, center, radius):
        """Afterglow wedge that trails the beam, the way a phosphor sweep does."""
        sweep = QPainterPath(center)
        sweep.arcTo(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2),
                    0.0, 180.0)
        sweep.closeSubpath()

        span = self.FAN_DEGREES / 360.0
        crisp = 0.004  # hard leading edge
        beam = tint(ACCENT_LIGHT, 0.36)
        clear = tint(ACCENT_LIGHT, 0.0)
        gradient = QConicalGradient(center, self._sweep_angle)
        # Conical gradients run counter-clockwise from the beam. The glow sits
        # on whichever side the beam has just come from.
        if self._sweep_dir > 0:
            gradient.setColorAt(0.0, beam)
            gradient.setColorAt(crisp, clear)
            gradient.setColorAt(1.0 - span, clear)
            gradient.setColorAt(1.0 - span * 0.35, tint(ACCENT_LIGHT, 0.10))
            gradient.setColorAt(1.0, beam)
        else:
            gradient.setColorAt(0.0, beam)
            gradient.setColorAt(span * 0.35, tint(ACCENT_LIGHT, 0.10))
            gradient.setColorAt(span, clear)
            gradient.setColorAt(1.0 - crisp, clear)
            gradient.setColorAt(1.0, beam)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPath(sweep)

        leading = QPen(tint(ACCENT_LIGHT, 0.60), 1.4)
        leading.setCosmetic(True)
        painter.setPen(leading)
        painter.drawLine(center, self._endpoint(center.x(), center.y(), radius, self._sweep_angle))

    def _paint_echoes(self, painter, center, radius):
        """Echoes as short arc blips whose brightness decays with age."""
        now = time.monotonic()
        newest = None
        for angle, distance_cm, stamp in self._readings:
            if distance_cm > RADAR_RANGE_CM:
                continue
            life = 1.0 - (now - stamp) / self.TRAIL_SECONDS
            if life <= 0.0:
                continue
            fade = life ** 1.7  # quick initial dim, long soft tail
            ring = radius * min(max(distance_cm, 0.0), RADAR_RANGE_CM) / RADAR_RANGE_CM
            token = BAD if distance_cm <= RADAR_DANGER_CM else ACCENT_LIGHT
            pen = QPen(tint(token, 0.90 * fade), 1.6 + 2.0 * fade)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(
                QRectF(center.x() - ring, center.y() - ring, ring * 2, ring * 2),
                int((angle - 2.4) * 16), int(4.8 * 16),
            )
            newest = (angle, ring, token, fade)

        if newest is not None and newest[3] > 0.6:
            angle, ring, token, fade = newest
            point = self._endpoint(center.x(), center.y(), ring, angle)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(tint(token, 0.20 * fade)))
            painter.drawEllipse(point, 9.0, 9.0)
            painter.setBrush(QBrush(tint(INK, 0.95 * fade)))
            painter.drawEllipse(point, 2.2, 2.2)

    def _paint_hub(self, painter, center):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(tint(ACCENT_LIGHT, 0.16)))
        painter.drawEllipse(center, 7.0, 7.0)
        painter.setBrush(QBrush(tint(ACCENT_LIGHT, 0.95)))
        painter.drawEllipse(center, 2.6, 2.6)

    def _paint_readout(self, painter, panel, footer, compact):
        """Thin oversized numerals over tiny upper-case captions."""
        top = panel.bottom() - footer + (6 if compact else 10)
        in_range = self._distance is not None and self._distance <= RADAR_RANGE_CM
        token = BAD if (in_range and self._distance <= RADAR_DANGER_CM) else ACCENT_LIGHT
        left, right = panel.left() + 2, panel.right() - 2

        if compact:
            number_base = top + 24
            big, bearing_size = 28, 20
        else:
            painter.setFont(micro_font())
            painter.setPen(QPen(tint(INK, 0.46)))
            caption_base = top + 9
            painter.drawText(QPointF(left, caption_base), 'DISTANCE')
            painter.drawText(
                QPointF(right - painter.fontMetrics().horizontalAdvance('BEARING'), caption_base),
                'BEARING',
            )
            number_base = caption_base + 44
            big, bearing_size = 46, 30

        distance_text = '--' if not in_range else str(int(self._distance))
        painter.setFont(numeral_font(big))
        painter.setPen(QPen(tint(INK, 0.97) if in_range else tint(INK, 0.36)))
        painter.drawText(QPointF(left - 2, number_base), distance_text)
        unit_x = left + painter.fontMetrics().horizontalAdvance(distance_text) + 3
        painter.setFont(micro_font())
        painter.setPen(QPen(tint(INK, 0.50)))
        painter.drawText(QPointF(unit_x, number_base), 'CM')

        angle_text = '--' if self._angle is None else f'{int(self._angle)}°'
        painter.setFont(numeral_font(bearing_size))
        painter.setPen(QPen(tint(INK, 0.92) if self._angle is not None else tint(INK, 0.36)))
        painter.drawText(
            QPointF(right - painter.fontMetrics().horizontalAdvance(angle_text), number_base),
            angle_text,
        )

        painter.setFont(micro_font())
        status_base = panel.bottom() - 2
        painter.setPen(QPen(tint(self._status_token(), 0.95)))
        status = painter.fontMetrics().elidedText(
            self._status.upper(), Qt.TextElideMode.ElideRight, int(panel.width() * 0.68)
        )
        painter.drawText(QPointF(left, status_base), status)
        if in_range:
            flag = 'OBSTACLE' if self._distance <= RADAR_DANGER_CM else 'CONTACT'
            painter.setPen(QPen(tint(token, 0.95)))
            painter.drawText(
                QPointF(right - painter.fontMetrics().horizontalAdvance(flag), status_base), flag
            )


class MADDashboard(QMainWindow):

    DEFAULT_SIZE = (1360, 820)
    MIN_SIZE = (1100, 680)
    # The right rail scales with the window but stays a supporting column.
    RAIL_MIN = 300
    RAIL_MAX = 400
    RAIL_SHARE = 0.26
    FEED_HEADER = 32  # height of a feed panel's title row
    TOP_BAR_COMPACT_BELOW = 1080  # header width under which it drops to icons
    TOP_BAR_TAGLINE_FROM = 1320   # header width from which the tagline shows

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Project MANUS AD LUNAM - Command & Control Center')

        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.icon_path = os.path.join(script_dir, 'icon.png')

        if os.path.exists(self.icon_path):
            self.setWindowIcon(QIcon(self.icon_path))
        self._place_window()

        # 1. Core Modules
        self.detector = HandDetector()
        self.controller = GestureController()
        self.sender = SerialSender()
        self.is_serial_connected = False
        self.serial_connect_worker = None

        # Telemetry & Input Tracking
        self.last_frame_time = time.monotonic()
        self._interval_ms = None       # smoothed gesture frame interval ("ping")
        self._ping_ui_time = 0.0       # throttles the header readout
        self.current_payload = 'S'
        self.pressed_keys = set()  # Tracks held WASD keys
        self.last_radar_update_time = None
        self._radar_alert_until = 0.0

        # Live state behind the System Link card
        self._camera_status = {'gesture': 'Waiting for source', 'rover': 'Waiting for source'}
        self._link_state = 'disconnected'
        self._link_detail = ''
        self._control_mode = 'gesture'
        self._mode_timer = QTimer(self)
        self._mode_timer.setSingleShot(True)
        self._mode_timer.timeout.connect(self._end_keyboard_mode)

        # Camera Flip Controls
        self.gesture_flip_horz = False
        self.gesture_flip_180 = True
        self.rover_flip_horz = False
        self.rover_flip_180 = True

        # Default Camera Sources
        self.GESTURE_CAM_INDEX = 0
        self.ROVER_CAM_INDEX = None

        # Camera threads start only once the operator confirms the sources.
        self.gesture_thread = None
        self.rover_thread = None
        self._page_anim = None
        self._hero = 'rover'
        self._rover_focus = False      # fullscreen hero view
        self._was_maximized = False
        self._log_was_open = False

        # Poll the serial connection without blocking the GUI thread.
        self.radar_timer = QTimer(self)
        self.radar_timer.timeout.connect(self.poll_radar_telemetry)

        # 2. Build User Interface Layout
        self.init_ui()

    def _place_window(self):
        """Default size, clamped to the screen and centred (as in Hanoon's)."""
        width, height = self.DEFAULT_SIZE
        min_width, min_height = self.MIN_SIZE
        screen = self.screen()
        if screen is None:
            self.setMinimumSize(min_width, min_height)
            self.resize(width, height)
            return
        avail = screen.availableGeometry()
        width = min(width, avail.width() - 40)
        height = min(height, avail.height() - 40)
        self.setMinimumSize(min(min_width, avail.width() - 40), min(min_height, avail.height() - 40))
        self.setGeometry(
            avail.x() + (avail.width() - width) // 2,
            avail.y() + (avail.height() - height) // 2,
            width,
            height,
        )

    # ------------------------------------------------------------------ UI --
    def init_ui(self):
        self.setStyleSheet(APP_STYLESHEET)
        self.setFont(app_font(14))

        self.background = StarfieldBackground(self)
        self.setCentralWidget(self.background)
        root = QVBoxLayout(self.background)
        root.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget(self.background)
        root.addWidget(self.stack)

        self.connect_page = MissionConnectPage(icon_path=self.icon_path)
        self.connect_page.connect_requested.connect(self.start_mission)
        self.stack.addWidget(self.connect_page)

        self.command_page = self._build_command_page()
        self.stack.addWidget(self.command_page)

        self._build_log_dock()
        self.stack.setCurrentWidget(self.connect_page)
        self._lock_command_focus()

    def _build_command_page(self):
        page = QWidget()
        page.setObjectName('page')
        page.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        page.installEventFilter(self)  # rail sizing, see eventFilter

        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 16, 20, 18)
        outer.setSpacing(16)
        outer.addWidget(self._build_header())

        deck = QHBoxLayout()
        deck.setSpacing(16)

        # Hero column: the main feed, with the driving controls beneath it.
        hero_column = QVBoxLayout()
        hero_column.setSpacing(16)
        self.hero_card = GlassCard(padding=PAD_FEED, spacing=0)
        hero_column.addWidget(self.hero_card, 1)
        self.control_strip = self._build_control_strip()
        hero_column.addWidget(self.control_strip)
        deck.addLayout(hero_column, 1)

        # Right rail: the inset feed, the radar, then live telemetry.
        self.rail = QWidget()
        rail_layout = QVBoxLayout(self.rail)
        rail_layout.setContentsMargins(0, 0, 0, 0)
        rail_layout.setSpacing(16)
        self.inset_card = GlassCard(padding=PAD_FEED, spacing=0)
        rail_layout.addWidget(self.inset_card)
        self.radar_box = GlassCard('Ultrasonic Radar', spacing=6)
        self.radar_visual = UltrasonicRadarWidget()
        self.radar_box.body.addWidget(self.radar_visual, 1)
        # Radar and telemetry share the spare height, so the graphs stay legible.
        rail_layout.addWidget(self.radar_box, 3)
        rail_layout.addWidget(self._build_telemetry_card(), 2)
        deck.addWidget(self.rail)
        outer.addLayout(deck, 1)

        self.rover_panel = self._build_rover_feed()
        self.gesture_panel = self._build_laptop_feed()
        self.hero_card.body.addWidget(self.rover_panel)
        self.inset_card.body.addWidget(self.gesture_panel)
        self._sync_feed_roles()
        self._refresh_mode_row()
        self._fit_rail(self.width())
        return page

    # -- header: three floating glass capsules -----------------------------
    def _build_header(self):
        """Identity, live status and actions, each in its own glass capsule."""
        header = QWidget()
        header.setFixedHeight(52)
        header.installEventFilter(self)  # density switch, see eventFilter
        self.top_bar = header
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        brand = GlassCapsule()
        brand_row = QHBoxLayout(brand)
        brand_row.setContentsMargins(8, 0, 20, 0)
        self.brand_mark = BrandMark()
        brand_row.addWidget(self.brand_mark)
        row.addWidget(brand)
        row.addStretch(1)

        status = GlassCapsule()
        status_row = QHBoxLayout(status)
        status_row.setContentsMargins(18, 0, 18, 0)
        status_row.setSpacing(14)
        self.link_pill = StatusPill('ESP32 · offline', 'bad', min_width=136, flat=True)
        self.link_pill.setMinimumWidth(136)
        self.link_pill.setToolTip('ESP32 transmitter link')
        self.top_rover_pill = StatusPill('Rover', 'idle', flat=True)
        self.top_rover_pill.setToolTip('Rover camera link')
        self.top_gesture_pill = StatusPill('Laptop', 'idle', flat=True)
        self.top_gesture_pill.setToolTip('Laptop (gesture) camera link')
        for pill in (self.top_rover_pill, self.top_gesture_pill):
            pill.setMinimumWidth(pill.sizeHint().width())
        for index, pill in enumerate((self.link_pill, self.top_rover_pill, self.top_gesture_pill)):
            if index:
                status_row.addWidget(self._hairline())
            status_row.addWidget(pill)
        row.addWidget(status)
        row.addStretch(1)

        actions = GlassCapsule()
        action_row = QHBoxLayout(actions)
        action_row.setContentsMargins(16, 0, 7, 0)
        action_row.setSpacing(2)
        self.latency_label = QLabel("Ping <b>-- ms</b>")
        self.latency_label.setObjectName('metric')
        self.latency_label.setTextFormat(Qt.TextFormat.RichText)
        self.latency_label.setFont(app_font(13, QFont.Weight.Medium))
        self.latency_label.setToolTip('Gesture camera frame interval (smoothed)')
        action_row.addWidget(self.latency_label)
        action_row.addSpacing(8)

        self.toggle_log_btn = PillButton('Show Log', variant='ghost', glyph='log',
                                         compact=True, height=38)
        self.toggle_log_btn.setFixedWidth(116)
        self.toggle_log_btn.setToolTip('Show or hide the event log')
        self.toggle_log_btn.clicked.connect(self.toggle_log_sidebar)
        action_row.addWidget(self.toggle_log_btn)

        self.sources_btn = PillButton('Sources', variant='ghost', glyph='sources',
                                      compact=True, height=38)
        self.sources_btn.setToolTip('Stop the feeds and change the stream sources')
        self.sources_btn.clicked.connect(self.prompt_source_control)
        action_row.addWidget(self.sources_btn)
        row.addWidget(actions)
        return header

    @staticmethod
    def _hairline():
        line = QWidget()
        line.setFixedSize(1, 18)
        line.setStyleSheet(f'background-color: {css(INK, 0.16)};')
        return line

    # -- camera feeds -------------------------------------------------------
    def _icon_button(self, glyph, tooltip):
        button = PillButton('', glyph=glyph, compact=True, height=30)
        button.setToolTip(tooltip)
        return button

    def _build_feed_panel(self, title, surface, status_pill, flip_buttons):
        """Title, status and controls above a rounded video.

        A panel is self-contained so swapping hero and inset just moves panels
        between the two glass cards.
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(PAD_FEED)

        header = QHBoxLayout()
        header.setContentsMargins(10, 2, 0, 0)
        header.setSpacing(6)
        name = title_label(title)
        header.addWidget(name)
        header.addSpacing(4)
        status_pill.setMinimumWidth(30)  # may shrink to its dot in the inset
        header.addWidget(status_pill)
        header.addStretch(1)
        for button in flip_buttons:
            header.addWidget(button)
        fullscreen = self._icon_button('expand', 'Fullscreen (F11 · Esc to exit)')
        fullscreen.clicked.connect(self.toggle_rover_fullscreen)
        header.addWidget(fullscreen)
        swap = self._icon_button('swap', 'Make this the main view')
        swap.clicked.connect(self.swap_feeds)
        header.addWidget(swap)
        layout.addLayout(header)
        layout.addWidget(surface, 1)

        surface.clicked.connect(lambda: self._on_feed_clicked(surface))
        return panel, name, swap, fullscreen

    def _build_rover_feed(self):
        self.rover_feed_label = VideoSurface('Connecting to Camera Stream…')
        self.rover_status_label = StatusPill('Waiting for source', 'warn')
        self.rover_flip_btn_180 = self._icon_button('flip-v', 'Rotate 180°')
        self.rover_flip_btn_180.clicked.connect(self.flip_rover_180)
        self.rover_flip_btn_180.set_active(self.rover_flip_180)
        self.rover_flip_btn_horz = self._icon_button('flip-h', 'Mirror')
        self.rover_flip_btn_horz.clicked.connect(self.flip_rover_horz)
        panel, self.rover_title, self.rover_swap_btn, self.rover_fullscreen_btn = \
            self._build_feed_panel(
                'Rover Camera', self.rover_feed_label, self.rover_status_label,
                (self.rover_flip_btn_180, self.rover_flip_btn_horz),
            )
        return panel

    def _build_laptop_feed(self):
        self.gesture_feed_label = VideoSurface('Initializing Video Stream…')
        self.gesture_status_label = StatusPill('Waiting for source', 'warn')
        self.gesture_flip_btn_180 = self._icon_button('flip-v', 'Rotate 180°')
        self.gesture_flip_btn_180.clicked.connect(self.flip_gesture_180)
        self.gesture_flip_btn_180.set_active(self.gesture_flip_180)
        self.gesture_flip_btn_horz = self._icon_button('flip-h', 'Mirror')
        self.gesture_flip_btn_horz.clicked.connect(self.flip_gesture_horz)
        panel, self.gesture_title, self.gesture_swap_btn, self.gesture_fullscreen_btn = \
            self._build_feed_panel(
                'Laptop Camera', self.gesture_feed_label, self.gesture_status_label,
                (self.gesture_flip_btn_180, self.gesture_flip_btn_horz),
            )
        return panel

    def _fit_rail(self, page_width):
        """Size the rail to the window and keep the inset video at 16:9."""
        rail = int(max(self.RAIL_MIN, min(self.RAIL_MAX, page_width * self.RAIL_SHARE)))
        self.rail.setFixedWidth(rail)
        video_height = (rail - 2 * PAD_FEED) * 9 / 16
        self.inset_card.setFixedHeight(int(video_height + self.FEED_HEADER + 3 * PAD_FEED))

    def _hero_surface(self):
        return self.rover_feed_label if self._hero == 'rover' else self.gesture_feed_label

    def _sync_feed_roles(self):
        """Swap belongs on the inset; fullscreen on the hero."""
        hero_is_rover = self._hero == 'rover'
        for is_hero, swap, fullscreen, surface in (
            (hero_is_rover, self.rover_swap_btn, self.rover_fullscreen_btn, self.rover_feed_label),
            (not hero_is_rover, self.gesture_swap_btn, self.gesture_fullscreen_btn, self.gesture_feed_label),
        ):
            swap.setVisible(not is_hero)
            fullscreen.setVisible(is_hero)
            surface.setCursor(
                Qt.CursorShape.ArrowCursor if is_hero else Qt.CursorShape.PointingHandCursor
            )
            surface.setToolTip('' if is_hero else 'Click to make this the main view')
        self._sync_card_glow()

    def _sync_card_glow(self):
        """The card holding a live camera glows blue (Hanoon's active state)."""
        hero, inset = ('rover', 'gesture') if self._hero == 'rover' else ('gesture', 'rover')
        self.hero_card.set_active(self._camera_status[hero] == 'Online')
        self.inset_card.set_active(self._camera_status[inset] == 'Online')

    def _on_feed_clicked(self, surface):
        if surface is not self._hero_surface():
            self.swap_feeds()

    def swap_feeds(self):
        """Promote the inset feed to the hero card.

        Only the panels move; the camera threads and their signal wiring are
        untouched, so each feed keeps writing to its own surface.
        """
        hero_item = self.hero_card.body.takeAt(0)
        inset_item = self.inset_card.body.takeAt(0)
        if hero_item is None or inset_item is None:
            return
        hero_panel, inset_panel = hero_item.widget(), inset_item.widget()
        self.hero_card.body.addWidget(inset_panel)
        self.inset_card.body.addWidget(hero_panel)
        inset_panel.show()
        hero_panel.show()

        self._hero = 'gesture' if inset_panel is self.gesture_panel else 'rover'
        self._sync_feed_roles()
        self._refresh_overlay()
        camera = 'laptop' if self._hero == 'gesture' else 'rover'
        self.log_box.append(f'[CAM] Main view switched to the {camera} camera')

    # -- control strip ------------------------------------------------------
    def _build_control_strip(self):
        """Drive command | speed limit | system link, under the hero feed."""
        strip = QWidget()
        strip.setFixedHeight(186)
        row = QHBoxLayout(strip)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        row.addWidget(self._build_drive_card(), 1)
        row.addWidget(self._build_speed_card(), 1)
        row.addWidget(self._build_link_card(), 1)
        return strip

    def _build_drive_card(self):
        """Active command, with key caps in keyboard mode and the compass in gesture mode."""
        drive_card = GlassCard('Drive Command', spacing=8)
        drive_card.body.addStretch(1)
        drive_row = QHBoxLayout()
        drive_row.setSpacing(10)
        self.payload_label = CommandLabel('S', size=58, color=CMD_STOP)
        drive_row.addWidget(self.payload_label, 1, Qt.AlignmentFlag.AlignVCenter)

        self.direction_indicator = DirectionIndicator()
        self.key_caps = KeyCaps()
        self.drive_visual = QStackedWidget()
        for widget in (self.direction_indicator, self.key_caps):
            page = QWidget()
            page_layout = QHBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignCenter)
            self.drive_visual.addWidget(page)
        self.drive_visual.setFixedSize(
            max(self.key_caps.width(), self.direction_indicator.width()),
            max(self.key_caps.height(), self.direction_indicator.height()),
        )
        drive_row.addWidget(self.drive_visual, 0, Qt.AlignmentFlag.AlignVCenter)
        drive_card.body.addLayout(drive_row)

        self.payload_sub = caption_label('Gesture command')
        drive_card.body.addWidget(self.payload_sub)
        drive_card.body.addStretch(1)
        return drive_card

    def _build_speed_card(self):
        """Speed limit: oversized thin percentage over an iOS slider."""
        speed_card = GlassCard(spacing=8)
        # Transmit state shares the header row, leaving the numeral room to breathe.
        header = QHBoxLayout()
        header.addWidget(caption_label('Speed Limit'))
        header.addStretch(1)
        self.speed_status_label = caption_label('Ready')
        header.addWidget(self.speed_status_label)
        speed_card.body.addLayout(header)
        speed_card.body.addStretch(1)

        self.speed_value_label = NumeralLabel('100%', size=64)
        speed_card.body.addWidget(self.speed_value_label)

        self.speed_slider = SpeedSlider()
        self.speed_slider.setRange(0, 100)
        self.speed_slider.setValue(100)
        self.speed_pwm = round(100 * 255 / 100)
        self.speed_slider.valueChanged.connect(self.update_speed_display)
        speed_card.body.addWidget(self.speed_slider)

        scale_row = QHBoxLayout()
        scale_row.addWidget(caption_label('Slow'))
        scale_row.addStretch(1)
        scale_row.addWidget(caption_label('Fast'))
        speed_card.body.addLayout(scale_row)
        speed_card.body.addStretch(1)
        return speed_card

    def _build_link_card(self):
        """Hanoon's system link, as a status list with a 'check again' icon."""
        card = GlassCard(spacing=4)
        header = QHBoxLayout()
        header.addWidget(caption_label('System Link'))
        header.addStretch(1)
        self.reconnect_btn = PillButton('', glyph='refresh', compact=True, height=30)
        self.reconnect_btn.setToolTip('Check for the ESP32 again')
        self.reconnect_btn.clicked.connect(self.reconnect_serial)
        header.addWidget(self.reconnect_btn)
        card.body.addLayout(header)
        card.body.addStretch(1)

        self.rover_link_row = StatusRow('Rover', 'Offline', 'bad')
        # port_label keeps its name: it is the transmitter (ESP32 serial) status.
        self.port_label = StatusRow('Transmitter', 'Offline', 'bad')
        self.mode_row = StatusRow('Control', 'Gesture', 'warn')
        for status_row in (self.rover_link_row, self.port_label, self.mode_row):
            card.body.addWidget(status_row)
            card.body.addSpacing(4)
        card.body.addStretch(1)
        return card

    def _build_telemetry_card(self):
        """Hanoon's live telemetry: closest radar echo and ping over 30 s."""
        card = GlassCard('Live Telemetry', padding=16, spacing=6)
        self.radar_graph = TelemetryGraph(
            'Radar distance', 'cm', ACCENT_LIGHT, cap=100, threshold=RADAR_DANGER_CM, mode='min'
        )
        self.latency_graph = TelemetryGraph('Ping', 'ms', ACCENT, min_span=60.0, mode='avg')
        card.body.addWidget(self.radar_graph, 1)
        card.body.addWidget(self.latency_graph, 1)
        return card

    def _build_log_dock(self):
        self.log_box = EventLogView()
        # Keep the log selectable with the mouse but never let it eat WASD.
        self.log_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.log_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.log_box.append('[SYS] Project MANUS AD LUNAM Control Hub Active.')

        self.log_box_group = GlassCard('Event Stream', radius=24, padding=16, spacing=10)
        self.log_box_group.body.addWidget(self.log_box, 1)

        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(10, 4, 12, 18)
        holder_layout.addWidget(self.log_box_group)

        self.logs_dock = QDockWidget('Event Log', self)
        self.logs_dock.setObjectName('SystemLogsDock')
        self.logs_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.logs_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.logs_dock.setMinimumWidth(300)
        self.logs_dock.setWidget(holder)
        self.logs_dock.visibilityChanged.connect(self.update_log_sidebar_button)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.logs_dock)
        self.logs_dock.hide()

    def eventFilter(self, watched, event):
        if event.type() == event.Type.Resize:
            if watched is getattr(self, 'top_bar', None):
                self._apply_top_bar_density(watched.width())
            elif watched is getattr(self, 'command_page', None):
                self._fit_rail(watched.width())
        return super().eventFilter(watched, event)

    def _apply_top_bar_density(self, width):
        """Narrow window or open log: mark only, icon-only actions."""
        compact = width < self.TOP_BAR_COMPACT_BELOW
        self.brand_mark.set_density(0 if compact else (2 if width >= self.TOP_BAR_TAGLINE_FROM else 1))
        self.sources_btn.setText('' if compact else 'Sources')

    def _lock_command_focus(self):
        """Stop page-2 controls from stealing focus, so WASD always reaches us."""
        for widget in self.command_page.findChildren(QWidget):
            widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.command_page.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------- page switching --
    def _goto_page(self, page):
        """Cross-fade between the two pages."""
        if self.stack.currentWidget() is page:
            return
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        self.stack.setCurrentWidget(page)

        animation = QPropertyAnimation(effect, b'opacity', self)
        animation.setDuration(PAGE_FADE_MS)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        # Drop the effect once we land: it renders the page offscreen, which is
        # not something we want sitting over live video.
        animation.finished.connect(lambda: page.setGraphicsEffect(None))
        self._page_anim = animation
        animation.start()

    def start_mission(self):
        """Accept the configured sources and bring the command center up."""
        g_src, r_src = self.connect_page.get_sources()
        self.GESTURE_CAM_INDEX = g_src
        self.ROVER_CAM_INDEX = r_src

        # Serial open/reboot wait runs in a worker; the dashboard stays responsive.
        self.reconnect_serial()
        self.radar_timer.start(50)
        self._start_streams()

        self._goto_page(self.command_page)
        self.command_page.setFocus()

    def prompt_source_control(self):
        """Return to Mission Connect, stopping the feeds on the way out."""
        if self._rover_focus:
            self.toggle_rover_fullscreen()
        self._stop_streams()
        self.radar_timer.stop()
        self.radar_visual.reset_reading('STANDBY')
        self.log_box.append('[SYS] Returned to source configuration; feeds stopped.')
        self._goto_page(self.connect_page)
        self.connect_page.gesture_input.setFocus()

    # ------------------------------------------------------- camera threads --
    def _start_streams(self):
        if self.GESTURE_CAM_INDEX is not None:
            self.gesture_thread = CameraThread(
                source=self.GESTURE_CAM_INDEX, flip=-1, detector=self.detector
            )
            self.gesture_thread.frame_processed.connect(self.update_gesture_feed)
            self.gesture_thread.status_changed.connect(self.update_gesture_camera_status)
            self.gesture_thread.start()
        else:
            self.update_gesture_camera_status('Not configured')

        if self.ROVER_CAM_INDEX is not None:
            self.rover_thread = CameraThread(
                source=self.ROVER_CAM_INDEX, flip=-1, detector=None
            )
            self.rover_thread.frame_processed.connect(self.update_rover_feed)
            self.rover_thread.status_changed.connect(self.update_rover_camera_status)
            self.rover_thread.start()
        else:
            self.update_rover_camera_status('Not configured')

        self.rover_title.setToolTip(f'Source: {self.ROVER_CAM_INDEX}')
        self.gesture_title.setToolTip(f'Source: {self.GESTURE_CAM_INDEX}')

    def _stop_streams(self):
        for attribute in ('gesture_thread', 'rover_thread'):
            thread = getattr(self, attribute)
            if thread is not None:
                thread.stop()
                setattr(self, attribute, None)
        self.gesture_feed_label.setPixmap(QPixmap())
        self.rover_feed_label.setPixmap(QPixmap())
        self.update_gesture_camera_status('Stopped')
        self.update_rover_camera_status('Stopped')

    # ------------------------------------------------------------ fullscreen --
    def toggle_rover_fullscreen(self):
        """Hanoon's fullscreen: the hero feed takes the whole screen; its command
        and speed ride along as a chip on the video."""
        if self.stack.currentWidget() is not self.command_page:
            return
        entering = not self._rover_focus
        self._rover_focus = entering
        for widget in (self.top_bar, self.rail, self.control_strip):
            widget.setVisible(not entering)
        if entering:
            self._log_was_open = self.logs_dock.isVisible()
            self.logs_dock.hide()
            self._was_maximized = self.isMaximized()
            self.showFullScreen()
        else:
            if self._was_maximized:
                self.showMaximized()
            else:
                self.showNormal()
            if self._log_was_open:
                self.logs_dock.show()
        for button in (self.rover_fullscreen_btn, self.gesture_fullscreen_btn):
            button.set_glyph('collapse' if entering else 'expand')
            button.setToolTip('Exit fullscreen (Esc)' if entering else 'Fullscreen (F11 · Esc to exit)')
        self._refresh_overlay()

    def _refresh_overlay(self):
        """In fullscreen the hidden drive and speed cards are summarised on the video."""
        for surface in (self.rover_feed_label, self.gesture_feed_label):
            surface.set_overlay(None)
        if self._rover_focus:
            self._hero_surface().set_overlay(
                f'{self.current_payload}    {self.speed_slider.value()}%',
                command_color(self.current_payload),
            )

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
        held = [letter for letter, down in (('W', has_w), ('A', has_a), ('S', has_s), ('D', has_d))
                if down]
        self.key_caps.set_pressed(held)
        if held:
            self._mode_timer.stop()
            self._set_control_mode('keyboard')
        else:
            self._mode_timer.start(KEYBOARD_MODE_HOLD_MS)

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

    def _end_keyboard_mode(self):
        if not self.pressed_keys:
            self._set_control_mode('gesture')

    def _set_control_mode(self, mode):
        if mode == self._control_mode:
            return
        self._control_mode = mode
        keyboard = mode == 'keyboard'
        self.drive_visual.setCurrentIndex(1 if keyboard else 0)
        self.payload_sub.setText('KEYBOARD COMMAND' if keyboard else 'GESTURE COMMAND')
        self._refresh_mode_row()

    def _refresh_mode_row(self):
        if self._control_mode == 'keyboard':
            self.mode_row.set_state('accent', 'Keyboard')
        elif self._camera_status['gesture'] == 'Online':
            self.mode_row.set_state('ok', 'Gesture')
        else:
            self.mode_row.set_state('warn', 'Gesture · no camera')

    def dispatch_command(self, command):
        """Sends payload down serial line and updates UI if command changed."""
        if command != self.current_payload:
            self.current_payload = command
            self.payload_label.setText(command)
            color = command_color(command)
            self.payload_label.set_color(color)
            self.direction_indicator.set_command(command, color)
            self.key_caps.set_color(color)
            self.speed_status_label.setText('TRANSMITTING' if command != 'S' else 'HOLDING')
            self._refresh_overlay()

            if self.is_serial_connected:
                if self.sender.send_command(command, self.speed_pwm):
                    self.log_box.append(f"[TX] Command Sent: '{command}'")
                else:
                    self.mark_serial_disconnected('Command write failed')
            else:
                self.log_box.append(f"[LOCAL] Command Evaluated: '{command}' (Serial Offline)")

    def toggle_log_sidebar(self):
        """Show or hide the dock; QMainWindow resizes the dashboard beside it."""
        self.logs_dock.setVisible(not self.logs_dock.isVisible())

    def update_log_sidebar_button(self, visible):
        self.toggle_log_btn.setText('Hide Log' if visible else 'Show Log')
        self.toggle_log_btn.set_active(visible)

    def update_speed_display(self, value):
        """Update the display and resend the active command at the new PWM speed."""
        self.speed_pwm = round(value * 255 / 100)
        self.speed_value_label.setText(f'{value}%')
        self._refresh_overlay()
        if self.is_serial_connected:
            if not self.sender.send_command(self.current_payload, self.speed_pwm):
                self.mark_serial_disconnected('Speed update write failed')

    def poll_radar_telemetry(self):
        """Read tagged distance samples from the transmitter's USB serial stream."""
        radar_was_live = self.last_radar_update_time is not None
        self._read_radar_telemetry()
        if (self.last_radar_update_time is not None) != radar_was_live:
            self._refresh_rover_row()

    def _read_radar_telemetry(self):
        if self._radar_alert_until and time.monotonic() > self._radar_alert_until:
            self._radar_alert_until = 0.0
            self.radar_box.set_alert(False)

        if not self.is_serial_connected:
            return

        for angle, distance_cm in self.sender.read_radar_telemetry():
            self.last_radar_update_time = time.monotonic()
            if distance_cm > RADAR_RANGE_CM:
                status = 'NO ECHO / OUT OF RANGE'
            else:
                status = 'RADAR LIVE'
            self.radar_visual.update_reading(angle, distance_cm)
            self.radar_visual.set_status(status)
            if distance_cm > 0:
                self.radar_graph.add(distance_cm)
            if 0 < distance_cm <= RADAR_DANGER_CM:
                # Hanoon's alert: the radar card glows red for a second.
                self._radar_alert_until = time.monotonic() + 1.0
                self.radar_box.set_alert(True)

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

    # ------------------------------------------------------------- feeds ----
    def update_gesture_feed(self, qt_image, raw_frame):
        now = time.monotonic()
        interval_ms = (now - self.last_frame_time) * 1000.0
        self.last_frame_time = now

        # Smooth the number and repaint the header at ~4 Hz instead of every frame.
        if self._interval_ms is None:
            self._interval_ms = interval_ms
        else:
            self._interval_ms = self._interval_ms * 0.8 + interval_ms * 0.2
        if now - self._ping_ui_time >= 0.25:
            self._ping_ui_time = now
            self.latency_label.setText(
                f"<span style='color: {css(INK, 0.45)};'>Ping</span> "
                f"<b style='color: {ACCENT_LIGHT};'>{int(self._interval_ms)} ms</b>"
            )
        self.latency_graph.add(self._interval_ms)

        label_size = self.gesture_feed_label.size()
        if label_size.width() > 0 and label_size.height() > 0:
            pixmap = QPixmap.fromImage(qt_image)
            self.gesture_feed_label.setPixmap(
                pixmap.scaled(
                    label_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        # Only evaluate gestures if NO keyboard keys are being pressed
        if not self.pressed_keys:
            hands_data = self.detector.get_hand_info(raw_frame)
            command = self.controller.get_command(hands_data)
            self.dispatch_command(command)

    def update_rover_feed(self, qt_image, raw_frame):
        del raw_frame
        label_size = self.rover_feed_label.size()
        if label_size.width() > 0 and label_size.height() > 0:
            pixmap = QPixmap.fromImage(qt_image)
            self.rover_feed_label.setPixmap(
                pixmap.scaled(
                    label_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    @staticmethod
    def _camera_state(status):
        if status == 'Online':
            return 'ok'
        if status in {'Stopped', 'Not configured'}:
            return 'idle'
        return 'warn'

    def update_gesture_camera_status(self, status):
        state = self._camera_state(status)
        self.gesture_status_label.set_state(state, status)
        self.top_gesture_pill.set_state(state)
        self._camera_status['gesture'] = status
        self._sync_card_glow()
        self._refresh_mode_row()

    def update_rover_camera_status(self, status):
        state = self._camera_state(status)
        self.rover_status_label.set_state(state, status)
        self.top_rover_pill.set_state(state)
        self._camera_status['rover'] = status
        self._sync_card_glow()
        self._refresh_rover_row()

    # ------------------------------------------------------ flip controls ---
    def _toggle_flip(self, camera, kind):
        """Hanoon's fix: one flip mode at a time, because cv2.flip takes a single
        code -- none (0), mirror (1) or 180° (-1) -- so the buttons always show
        what the camera is actually doing."""
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
        getattr(self, f'{camera}_flip_btn_horz').set_active(horz)
        getattr(self, f'{camera}_flip_btn_180').set_active(rot)

        thread = getattr(self, f'{camera}_thread')
        if thread and thread.isRunning():
            thread.flip = 1 if horz else (-1 if rot else 0)
            mode = 'FLIP HORZ' if horz else ('FLIP 180°' if rot else 'NO FLIP')
            self.log_box.append(f'[CAM] {camera.capitalize()} camera set to {mode} flip')

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

    # ---------------------------------------------------------- system link --
    def _set_transmitter(self, state, detail=''):
        """ESP32 serial link: System Link row and header pill."""
        self._link_state = state
        self._link_detail = detail
        value, token = {
            'connected': (f'Online · {detail}' if detail else 'Online', 'ok'),
            'connecting': ('Connecting…', 'warn'),
            'disconnected': ('Offline', 'bad'),
        }[state]
        self.port_label.set_state(token, value)
        pill = {
            'connected': f'ESP32 · {detail}' if detail else 'ESP32 · online',
            'connecting': 'ESP32 · connecting',
            'disconnected': 'ESP32 · offline',
        }[state]
        self.link_pill.set_state(token, pill)

    def _refresh_rover_row(self):
        """The rover counts as online while its camera or its radar is live."""
        camera = self._camera_status['rover'] == 'Online'
        radar = self.last_radar_update_time is not None
        if camera or radar:
            via = ' and '.join(name for name, live in (('camera', camera), ('radar', radar)) if live)
            self.rover_link_row.set_state('ok', 'Online')
            self.rover_link_row.setToolTip(f'Rover reachable: {via} live')
        else:
            self.rover_link_row.set_state('bad', 'Offline')
            self.rover_link_row.setToolTip('No rover camera feed and no radar telemetry')

    # ------------------------------------------------------------- serial ---
    def reconnect_serial(self):
        if self.serial_connect_worker is not None and self.serial_connect_worker.isRunning():
            return

        self.is_serial_connected = False
        self.reconnect_btn.setEnabled(False)
        self.reconnect_btn.set_busy(True)
        self._set_transmitter('connecting')
        self.log_box.append('[SYS] Attempting ESP32 re-connection...')
        self.serial_connect_worker = SerialConnectWorker(self.sender, self)
        self.serial_connect_worker.connection_finished.connect(self.on_serial_connect_finished)
        self.serial_connect_worker.start()

    def mark_serial_disconnected(self, reason):
        self.is_serial_connected = False
        self._set_transmitter('disconnected')
        self.radar_visual.set_status('SERIAL LINK OFFLINE')
        self._radar_alert_until = 0.0
        self.radar_box.set_alert(False)
        self.log_box.append(f'[SYS] Serial connection lost: {reason}.')

    def on_serial_connect_finished(self, connected, detail):
        self.is_serial_connected = connected
        self.reconnect_btn.setEnabled(True)
        self.reconnect_btn.set_busy(False)
        if connected:
            self._set_transmitter('connected', detail)
            self.log_box.append(f'[SYS] Linked to ESP32 on port {detail}')
            if not self.sender.send_command(self.current_payload, self.speed_pwm):
                self.mark_serial_disconnected('Telemetry handshake failed')
        else:
            self._set_transmitter('disconnected')
            self.log_box.append('[SYS] Search failed. No active ESP32 COM port.')
            if detail:
                self.log_box.append(f'[SYS] Connection detail: {detail}')

    # ------------------------------------------------------------ window ----
    def changeEvent(self, event):
        """Park the backdrop animation while the window is minimised."""
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self.background.set_animating(not self.isMinimized())

    def closeEvent(self, event):
        if self.serial_connect_worker is not None and self.serial_connect_worker.isRunning():
            self.serial_connect_worker.wait(3000)
        if self.gesture_thread is not None:
            self.gesture_thread.stop()
        if self.rover_thread is not None:
            self.rover_thread.stop()
        self.sender.close()
        event.accept()

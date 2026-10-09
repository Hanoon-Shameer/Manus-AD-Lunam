import os
import sys
import time
import math
import cv2
from PyQt6.QtCore import QEasingCurve, Qt, QTimer, QVariantAnimation
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QImage
from PyQt6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Project Hardware & Vision Modules
from gesture_controller import GestureController
from hand_detector import HandDetector
from serial_sender import SerialSender
from stream_manager import CameraThread


class SourceControlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Source Control Configuration")
        self.setFixedSize(450, 500)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.setStyleSheet("""
            QDialog {
                background-color: #0B0D12;
            }
            QLabel {
                color: #C3CEE0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #131722;
                color: #00E5FF;
                border: 1px solid #2A2F3D;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
                font-family: 'Consolas', monospace;
            }
            QLineEdit:focus {
                border: 1px solid #00E5FF;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A2638, stop:1 #0F1724);
                color: #00E5FF;
                border: 1px solid #00E5FF;
                border-radius: 8px;
                padding: 12px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #00E5FF;
                color: #0B0D12;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)

        heading = QLabel("Source Control")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setFont(QFont('Segoe UI', 22, QFont.Weight.Bold))
        heading.setStyleSheet("color: #00E5FF; margin-bottom: 10px;")
        layout.addWidget(heading)

        # 1. Gesture Cam Input
        gesture_label = QLabel("Gesture Camera Index / Source:")
        self.gesture_input = QLineEdit("0")
        layout.addWidget(gesture_label)
        layout.addWidget(self.gesture_input)

        layout.addSpacing(10)

        # 2. Rover Cam Input
        rover_label = QLabel("Please enter the IP and Port as given in the LRS android app.")
        rover_label.setWordWrap(True)
        self.rover_input = QLineEdit()
        
        # Pre-fill with http://xxx.xx.xx.xxx:xxxx
        self.rover_input.setText("http://xxx.xx.xx.xxx:xxxx")
        self.rover_input.textChanged.connect(self._enforce_http_prefix)
        
        layout.addWidget(rover_label)
        layout.addWidget(self.rover_input)

        layout.addStretch()

        # Connect / Confirm Button
        self.submit_btn = QPushButton("CONNECT STREAMS")
        self.submit_btn.clicked.connect(self.accept)
        layout.addWidget(self.submit_btn)

        self.setLayout(layout)

    def _enforce_http_prefix(self, text):
        if not text.startswith("http://"):
            self.rover_input.blockSignals(True)
            self.rover_input.setText("http://")
            self.rover_input.setCursorPosition(len("http://"))
            self.rover_input.blockSignals(False)

    def get_sources(self):
        gesture_val = self.gesture_input.text().strip()
        if gesture_val.isdigit():
            gesture_source = int(gesture_val)
        else:
            gesture_source = gesture_val

        rover_source = self.rover_input.text().strip()

        return gesture_source, rover_source


class RadarDisplayWidget(QWidget):
    """Paint a live 180-degree radar with short-lived object returns."""

    MAX_RANGE_CM = 400
    RETURN_HOLD_SECONDS = 3.2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 190)
        self.current_angle = 90
        self.current_distance_cm = None
        self.status_text = 'WAITING FOR RADAR DATA'
        self.status_color = '#FFCC00'
        self.return_points = {}

    @staticmethod
    def _point_at(center_x, baseline_y, radius, angle_degrees, distance_ratio=1.0):
        angle = math.radians(angle_degrees)
        scaled_radius = radius * distance_ratio
        return QPointF(
            center_x + scaled_radius * math.cos(angle),
            baseline_y - scaled_radius * math.sin(angle),
        )

    def add_reading(self, angle, distance_cm):
        now = time.monotonic()
        self.current_angle = max(0, min(180, int(angle)))
        self.current_distance_cm = max(0, min(self.MAX_RANGE_CM, int(distance_cm)))

        if 0 < self.current_distance_cm < self.MAX_RANGE_CM:
            # One stored return per servo angle; fade it until a later sweep refreshes it.
            self.return_points[self.current_angle] = (self.current_distance_cm, now)

        self.set_status(
            'NO ECHO / OUT OF RANGE' if self.current_distance_cm >= self.MAX_RANGE_CM else 'RADAR LIVE',
            '#FFCC00' if self.current_distance_cm >= self.MAX_RANGE_CM else '#00E676',
        )
        self.update()

    def set_status(self, text, color):
        if self.status_text != text or self.status_color != color:
            self.status_text = text
            self.status_color = color
            self.update()

    def mark_stale(self):
        self.current_distance_cm = None
        self.set_status('NO RADAR DATA', '#FF1744')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor('#0B0D12'))

        width = self.width()
        height = self.height()
        center_x = width / 2.0
        baseline_y = height - 27.0
        radius = max(20.0, min((width - 52.0) / 2.0, height - 78.0))

        painter.setFont(QFont('Consolas', 9, QFont.Weight.Bold))
        painter.setPen(QColor('#C3CEE0'))
        painter.drawText(12, 16, f'ANGLE {self.current_angle:03d}°')
        if self.current_distance_cm is None:
            range_text = 'RANGE --'
        elif self.current_distance_cm >= self.MAX_RANGE_CM:
            range_text = 'RANGE NO ECHO'
        else:
            range_text = f'RANGE {self.current_distance_cm} cm'
        painter.drawText(max(12, width - 150), 16, range_text)
        painter.setPen(QColor(self.status_color))
        painter.drawText(12, 34, self.status_text)

        # Reference-style semicircular range arcs and angle spokes.
        painter.setPen(QPen(QColor(0, 229, 255, 85), 1))
        for range_cm in range(100, self.MAX_RANGE_CM + 1, 100):
            ring_radius = radius * range_cm / self.MAX_RANGE_CM
            path = QPainterPath()
            for degree in range(181):
                point = self._point_at(center_x, baseline_y, ring_radius, degree)
                if degree == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            painter.drawPath(path)
            painter.setPen(QColor('#57AFA8'))
            painter.drawText(int(center_x + 7), int(baseline_y - ring_radius - 3), f'{range_cm}')
            painter.setPen(QPen(QColor(0, 229, 255, 85), 1))

        for degree in range(0, 181, 30):
            endpoint = self._point_at(center_x, baseline_y, radius, degree)
            painter.drawLine(QPointF(center_x, baseline_y), endpoint)
            label_point = self._point_at(center_x, baseline_y, radius + 13, degree)
            painter.setPen(QColor('#8A9AB8'))
            painter.drawText(int(label_point.x() - 12), int(label_point.y() + 4), f'{degree}°')
            painter.setPen(QPen(QColor(0, 229, 255, 85), 1))

        painter.drawLine(
            QPointF(center_x - radius, baseline_y),
            QPointF(center_x + radius, baseline_y),
        )

        # Remove expired echoes and paint the remaining points with a fading red return trail.
        now = time.monotonic()
        for angle, (distance_cm, seen_at) in list(self.return_points.items()):
            age = now - seen_at
            if age >= self.RETURN_HOLD_SECONDS:
                del self.return_points[angle]
                continue
            opacity = max(35, int(230 * (1.0 - age / self.RETURN_HOLD_SECONDS)))
            point = self._point_at(
                center_x,
                baseline_y,
                radius,
                angle,
                distance_cm / self.MAX_RANGE_CM,
            )
            color = QColor(255, 66, 72, opacity)
            painter.setPen(QPen(color, 1))
            painter.setBrush(color)
            painter.drawEllipse(point, 5.0, 5.0)

        # Current servo direction is the bright moving scan line.
        sweep_endpoint = self._point_at(center_x, baseline_y, radius, self.current_angle)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 229, 255, 75), 5))
        painter.drawLine(QPointF(center_x, baseline_y), sweep_endpoint)
        painter.setPen(QPen(QColor('#00E5FF'), 2))
        painter.drawLine(QPointF(center_x, baseline_y), sweep_endpoint)


class MADDashboard(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Project MANUS AD LUNAM - Command & Control Center')
        self.setGeometry(100, 100, 1280, 750)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, 'icon.png')

        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 1. Core Modules
        self.detector = HandDetector()
        self.controller = GestureController()
        self.sender = SerialSender()
        self.is_serial_connected = self.sender.connect()

        # Telemetry & Input Tracking
        self.last_frame_time = time.time()
        self.current_payload = 'S'
        self.pressed_keys = set()  # Tracks held WASD keys
        self.last_radar_update_time = None

        # Default Camera Sources
        self.GESTURE_CAM_INDEX = 0
        self.ROVER_CAM_INDEX = "http://100.91.87.88:8080"

        # Prompt Modal Dialog for Sources
        self.prompt_source_control()

        # 2. Build User Interface Layout
        self.init_ui()

        # Poll the existing serial connection without blocking the GUI thread.
        self.radar_timer = QTimer(self)
        self.radar_timer.timeout.connect(self.poll_radar_telemetry)
        self.radar_timer.start(50)

        # 3. Initialize Camera Threads
        self.gesture_thread = CameraThread(source=self.GESTURE_CAM_INDEX, flip=True, detector=self.detector)
        self.gesture_thread.frame_processed.connect(self.update_gesture_feed)
        self.gesture_thread.start()

        self.rover_thread = CameraThread(source=self.ROVER_CAM_INDEX, flip=True, detector=None)
        self.rover_thread.frame_processed.connect(self.update_rover_feed)
        self.rover_thread.start()

    def prompt_source_control(self):
        dialog = SourceControlDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            g_src, r_src = dialog.get_sources()
            self.GESTURE_CAM_INDEX = g_src
            self.ROVER_CAM_INDEX = r_src

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        self.setStyleSheet("""
            QMainWindow { background-color: #0B0D12; }
            QGroupBox { 
                color: #00E5FF; font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px; font-weight: bold; letter-spacing: 1px;
                border: 1px solid #2A2F3D; border-radius: 12px; 
                margin-top: 20px; padding-top: 15px; background-color: #131722;
            }
            QGroupBox::title { 
                subcontrol-origin: margin; subcontrol-position: top left;
                left: 15px; padding: 2px 10px; background-color: #1A2130;
                border: 1px solid #00E5FF; border-radius: 5px; color: #00E5FF;
            }
            QLabel { color: #C3CEE0; font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A2638, stop:1 #0F1724);
                color: #00E5FF; border: 1px solid #00E5FF; border-radius: 8px;
                padding: 10px 14px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background: #00E5FF; color: #0B0D12; }
            QTextEdit { 
                background-color: #07090D; color: #00FF66; border: 1px solid #2A2F3D;
                border-radius: 8px; font-family: 'Consolas', monospace; font-size: 12px;
            }
        """)

        main_vbox = QVBoxLayout()
        main_vbox.setSpacing(15)
        main_vbox.setContentsMargins(15, 15, 15, 15)
        central_widget.setLayout(main_vbox)

        cameras_hbox = QHBoxLayout()
        cameras_hbox.setSpacing(15)

        self.gesture_box = QGroupBox('OPERATOR GESTURE FEED')
        gesture_vbox = QVBoxLayout()
        self.gesture_feed_label = QLabel('Initializing Video Stream...')
        self.gesture_feed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gesture_feed_label.setMinimumSize(480, 320)
        gesture_vbox.addWidget(self.gesture_feed_label)
        self.gesture_box.setLayout(gesture_vbox)

        self.rover_box = QGroupBox('ROVER CAMERA FEED')
        rover_vbox = QVBoxLayout()
        self.rover_feed_label = QLabel('Connecting to Camera Stream...')
        self.rover_feed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rover_feed_label.setMinimumSize(480, 320)
        rover_vbox.addWidget(self.rover_feed_label)
        self.rover_box.setLayout(rover_vbox)

        cameras_hbox.addWidget(self.gesture_box, stretch=1)
        cameras_hbox.addWidget(self.rover_box, stretch=1)

        self.telemetry_hbox = QHBoxLayout()
        self.telemetry_hbox.setSpacing(15)

        self.link_box = QGroupBox('SYSTEM LINK')
        link_vbox = QVBoxLayout()
        status_text = (
            f"ESP32 Link: <span style='color: #00E676; font-weight: bold;'>CONNECTED ({self.sender.port})</span>"
            if self.is_serial_connected
            else "ESP32 Link: <span style='color: #FF1744; font-weight: bold;'>DISCONNECTED</span>"
        )
        self.port_label = QLabel(status_text)
        self.port_label.setTextFormat(Qt.TextFormat.RichText)
        self.latency_label = QLabel("Frame Latency: <b style='color: #00E5FF;'>0 ms</b>")
        self.latency_label.setTextFormat(Qt.TextFormat.RichText)
        self.reconnect_btn = QPushButton('🔄 RECONNECT SERIAL')
        self.reconnect_btn.clicked.connect(self.reconnect_serial)
        link_vbox.addWidget(self.port_label)
        link_vbox.addWidget(self.latency_label)
        link_vbox.addWidget(self.reconnect_btn)
        link_vbox.addStretch()
        self.link_box.setLayout(link_vbox)

        self.payload_box = QGroupBox('PAYLOAD')
        payload_vbox = QVBoxLayout()
        self.payload_sub = QLabel('ACTIVE TRANSMISSION COMMAND')
        self.payload_sub.setFont(QFont('Segoe UI', 9))
        self.payload_sub.setStyleSheet('color: #6C7A9C;')
        self.payload_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.payload_label = QLabel('S')
        self.payload_label.setFont(QFont('Segoe UI', 36, QFont.Weight.Bold))
        self.payload_label.setStyleSheet(
            'color: #FFCC00; background-color: #0B0D12; border: 1px solid #2A2F3D; border-radius: 10px;'
        )
        self.payload_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        payload_vbox.addWidget(self.payload_sub)
        payload_vbox.addWidget(self.payload_label)
        self.payload_box.setLayout(payload_vbox)

        self.radar_box = QGroupBox('ULTRASONIC RADAR • 0–400 CM')
        radar_vbox = QVBoxLayout()
        radar_vbox.setContentsMargins(8, 12, 8, 8)
        self.radar_widget = RadarDisplayWidget()
        radar_vbox.addWidget(self.radar_widget, stretch=1)
        self.radar_box.setLayout(radar_vbox)

        self.status_card_box = QGroupBox('FEED STATUS')
        status_card_vbox = QVBoxLayout()
        self.status_card_label = QLabel(
            'VIDEO STREAM<br><b style="font-size: 18px; color: #00E5FF;">ONLINE</b>'
        )
        self.status_card_label.setTextFormat(Qt.TextFormat.RichText)
        self.status_card_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_card_vbox.addStretch()
        status_card_vbox.addWidget(self.status_card_label)
        status_card_vbox.addStretch()
        self.status_card_box.setLayout(status_card_vbox)

        self.log_box_group = QGroupBox('SYS LOGS')
        log_vbox = QVBoxLayout()
        self.toggle_log_btn = QPushButton('📜 TOGGLE LOGS ⮞')
        self.toggle_log_btn.clicked.connect(self.toggle_logs)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.append('[SYS] Project MANUS AD LUNAM Control Hub Active.')
        log_vbox.addWidget(self.toggle_log_btn)
        log_vbox.addWidget(self.log_box)
        self.log_box_group.setLayout(log_vbox)

        self.telemetry_hbox.addWidget(self.link_box, stretch=100)
        self.telemetry_hbox.addWidget(self.payload_box, stretch=100)
        self.telemetry_hbox.addWidget(self.radar_box, stretch=100)
        self.telemetry_hbox.addWidget(self.status_card_box, stretch=100)
        self.telemetry_hbox.addWidget(self.log_box_group, stretch=100)

        self.log_box.setVisible(False)
        self.update_bottom_row_stretches(100)

        main_vbox.addLayout(cameras_hbox, stretch=2)
        main_vbox.addLayout(self.telemetry_hbox, stretch=1)

    # --- KEYBOARD CONTROLS ---
    def keyPressEvent(self, event):
        """Processes W, A, S, D key presses."""
        if event.isAutoRepeat():
            return  # Prevent OS key repeat flooding

        key = event.key()
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
            self.payload_label.setText(command)

            if self.is_serial_connected:
                self.sender.send_command(command)
                self.log_box.append(f"[TX] Command Sent: '{command}'")
            else:
                self.log_box.append(f"[LOCAL] Command Evaluated: '{command}' (Serial Offline)")

    def toggle_logs(self):
        is_expanded = self.log_box.isVisible()
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(300)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        if is_expanded:
            self.toggle_log_btn.setText('📜 TOGGLE LOGS ⮞')
            self.anim.setStartValue(250)
            self.anim.setEndValue(100)
            self.anim.finished.connect(lambda: self.log_box.setVisible(False))
        else:
            self.log_box.setVisible(True)
            self.toggle_log_btn.setText('📜 HIDE LOGS ⮟')
            self.anim.setStartValue(100)
            self.anim.setEndValue(250)

        self.anim.valueChanged.connect(self.update_bottom_row_stretches)
        self.anim.start()

    def update_bottom_row_stretches(self, log_stretch_val):
        log_stretch = int(log_stretch_val)
        card_stretch = max(40, int((620 - log_stretch) / 5.2))
        self.telemetry_hbox.setStretch(0, card_stretch)
        self.telemetry_hbox.setStretch(1, card_stretch)
        self.telemetry_hbox.setStretch(2, int(card_stretch * 2.2))
        self.telemetry_hbox.setStretch(3, card_stretch)
        self.telemetry_hbox.setStretch(4, log_stretch)

    def poll_radar_telemetry(self):
        """Feed tagged angle/distance samples into the radar display."""
        for angle, distance_cm in self.sender.read_radar_telemetry():
            self.last_radar_update_time = time.monotonic()
            self.radar_widget.add_reading(angle, distance_cm)

        if self.last_radar_update_time is None:
            if not self.is_serial_connected:
                self.radar_widget.set_status('SERIAL LINK OFFLINE', '#FF1744')
            elif self.radar_widget.status_text == 'SERIAL LINK OFFLINE':
                self.radar_widget.set_status('WAITING FOR RADAR DATA', '#FFCC00')
        elif time.monotonic() - self.last_radar_update_time > 1.5:
            self.last_radar_update_time = None
            self.radar_widget.mark_stale()

        # Keep the fading return trail animated between serial packets.
        self.radar_widget.update()

    def update_gesture_feed(self, qt_image, raw_frame):
        now = time.time()
        latency_ms = int((now - self.last_frame_time) * 1000)
        self.last_frame_time = now
        self.latency_label.setText(f"Frame Latency: <b style='color: #00E5FF;'>{latency_ms} ms</b>")

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

    def reconnect_serial(self):
        self.log_box.append('[SYS] Attempting ESP32 re-connection...')
        self.is_serial_connected = self.sender.connect()
        if self.is_serial_connected:
            self.port_label.setText(
                f"ESP32 Link: <span style='color: #00E676; font-weight: bold;'>CONNECTED ({self.sender.port})</span>"
            )
            self.log_box.append(f'[SYS] Linked to ESP32 on port {self.sender.port}')
        else:
            self.port_label.setText(
                "ESP32 Link: <span style='color: #FF1744; font-weight: bold;'>DISCONNECTED</span>"
            )
            self.log_box.append('[SYS] Search failed. No active ESP32 COM port.')

    def closeEvent(self, event):
        self.gesture_thread.stop()
        self.rover_thread.stop()
        self.sender.close()
        event.accept()

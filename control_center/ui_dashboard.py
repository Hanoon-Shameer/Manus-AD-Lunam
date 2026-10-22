import os
import sys
import time
from urllib.parse import urlsplit
import cv2
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QFont, QIcon, QPixmap, QImage
from PyQt6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSlider,
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


class SourceControlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Source Control Configuration")
        self.setFixedSize(520, 710)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.qr_settings = QSettings("Manus", "ManusADLunam")

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
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

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
        rover_label = QLabel(
            "Gesture source: camera index or stream URL. Rover stream: http(s) or RTSP URL; leave blank to skip."
        )
        rover_label.setWordWrap(True)
        self.rover_input = QLineEdit()
        self.rover_input.setPlaceholderText("http://192.168.1.20:8080")

        layout.addWidget(rover_label)
        layout.addWidget(self.rover_input)

        qr_heading = QLabel("MOBILE APP CONNECTION QR")
        qr_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_heading.setStyleSheet("color: #00E5FF; font-weight: bold; margin-top: 4px;")
        layout.addWidget(qr_heading)

        self.qr_preview = QLabel("No static QR image loaded")
        self.qr_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_preview.setWordWrap(True)
        self.qr_preview.setFixedSize(200, 200)
        self.qr_preview.setStyleSheet(
            "background-color: #FFFFFF; color: #5B6475; border: 2px solid #2A2F3D; border-radius: 8px;"
        )
        layout.addWidget(self.qr_preview, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.qr_path_label = QLabel("Choose the static QR image supplied for the mobile app.")
        self.qr_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_path_label.setWordWrap(True)
        self.qr_path_label.setStyleSheet("color: #8A9AB8; font-size: 10px;")
        layout.addWidget(self.qr_path_label)

        self.load_qr_btn = QPushButton("LOAD STATIC QR IMAGE")
        self.load_qr_btn.clicked.connect(self.choose_qr_image)
        layout.addWidget(self.load_qr_btn)

        qr_note = QLabel("Displays the image only; it does not generate or verify the QR contents.")
        qr_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_note.setWordWrap(True)
        qr_note.setStyleSheet("color: #6C7A9C; font-size: 10px;")
        layout.addWidget(qr_note)

        saved_qr_path = self.qr_settings.value("mobile_app_qr_path", "") or ""
        if saved_qr_path and os.path.isfile(saved_qr_path):
            self.set_qr_image(saved_qr_path, persist=False)

        layout.addStretch()

        # Connect / Confirm Button
        self.submit_btn = QPushButton("CONNECT STREAMS")
        self.submit_btn.clicked.connect(self.validate_and_accept)
        layout.addWidget(self.submit_btn)

        self.setLayout(layout)

    def choose_qr_image(self):
        """Select and preview a user-created static QR image."""
        initial_path = self.qr_settings.value("mobile_app_qr_path", "") or ""
        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select the mobile app QR image",
            initial_path if os.path.isfile(initial_path) else "",
            "Image files (*.png *.jpg *.jpeg *.bmp)",
        )
        if image_path:
            self.set_qr_image(image_path)

    def set_qr_image(self, image_path, persist=True):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Invalid image", "The selected file could not be loaded as an image.")
            return

        self.qr_preview.setPixmap(
            pixmap.scaled(
                self.qr_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        )
        self.qr_path_label.setText(os.path.basename(image_path))
        self.qr_path_label.setToolTip(image_path)
        if persist:
            self.qr_settings.setValue("mobile_app_qr_path", image_path)

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
        self.is_serial_connected = False
        self.serial_connect_worker = None

        # Telemetry & Input Tracking
        self.last_frame_time = time.monotonic()
        self.current_payload = 'S'
        self.pressed_keys = set()  # Tracks held WASD keys
        self.last_radar_update_time = None

        # Camera Flip Controls
        self.gesture_flip_horz = False
        self.gesture_flip_180 = True
        self.rover_flip_horz = False
        self.rover_flip_180 = True

        # Default Camera Sources
        self.GESTURE_CAM_INDEX = 0
        self.ROVER_CAM_INDEX = None

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
        self.gesture_thread = None
        if self.GESTURE_CAM_INDEX is not None:
            self.gesture_thread = CameraThread(source=self.GESTURE_CAM_INDEX, flip=-1, detector=self.detector)
            self.gesture_thread.frame_processed.connect(self.update_gesture_feed)
            self.gesture_thread.status_changed.connect(self.update_gesture_camera_status)
            self.gesture_thread.start()
        else:
            self.gesture_status_label.setText('Not configured')

        self.rover_thread = None
        if self.ROVER_CAM_INDEX is not None:
            self.rover_thread = CameraThread(source=self.ROVER_CAM_INDEX, flip=-1, detector=None)
            self.rover_thread.frame_processed.connect(self.update_rover_feed)
            self.rover_thread.status_changed.connect(self.update_rover_camera_status)
            self.rover_thread.start()
        else:
            self.rover_status_label.setText('Not configured')

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
            QDockWidget { color: #00E5FF; font-weight: bold; }
            QDockWidget::title { background-color: #1A2130; padding: 8px; border: 1px solid #2A2F3D; }
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
        self.gesture_feed_label.setMinimumSize(700, 400)
        gesture_vbox.addWidget(self.gesture_feed_label)

        gesture_flip_hbox = QHBoxLayout()
        gesture_flip_hbox.setSpacing(10)

        self.gesture_flip_btn_180 = QPushButton('🔄 FLIP 180°')
        self.gesture_flip_btn_180.clicked.connect(self.flip_gesture_180)
        self.gesture_flip_btn_180.setStyleSheet('background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A2638, stop:1 #0F1724); color: #00E5FF; border: 1px solid #00E5FF; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: bold;')
        gesture_flip_hbox.addWidget(self.gesture_flip_btn_180)

        self.gesture_flip_btn_horz = QPushButton('🔄 FLIP HORZ')
        self.gesture_flip_btn_horz.clicked.connect(self.flip_gesture_horz)
        self.gesture_flip_btn_horz.setStyleSheet('background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A2638, stop:1 #0F1724); color: #00E5FF; border: 1px solid #00E5FF; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: bold;')
        gesture_flip_hbox.addWidget(self.gesture_flip_btn_horz)

        gesture_vbox.addLayout(gesture_flip_hbox)
        self.gesture_status_label = QLabel('Waiting for source')
        self.gesture_status_label.setStyleSheet('color: #FFCC00; font-size: 10px;')
        gesture_vbox.addWidget(self.gesture_status_label)
        self.gesture_box.setLayout(gesture_vbox)

        self.rover_box = QGroupBox('ROVER CAMERA FEED')
        rover_vbox = QVBoxLayout()
        self.rover_feed_label = QLabel('Connecting to Camera Stream...')
        self.rover_feed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rover_feed_label.setMinimumSize(700, 400)
        rover_vbox.addWidget(self.rover_feed_label)

        rover_flip_hbox = QHBoxLayout()
        rover_flip_hbox.setSpacing(10)

        self.rover_flip_btn_180 = QPushButton('🔄 FLIP 180°')
        self.rover_flip_btn_180.clicked.connect(self.flip_rover_180)
        self.rover_flip_btn_180.setStyleSheet('background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A2638, stop:1 #0F1724); color: #00E5FF; border: 1px solid #00E5FF; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: bold;')
        rover_flip_hbox.addWidget(self.rover_flip_btn_180)

        self.rover_flip_btn_horz = QPushButton('🔄 FLIP HORZ')
        self.rover_flip_btn_horz.clicked.connect(self.flip_rover_horz)
        self.rover_flip_btn_horz.setStyleSheet('background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A2638, stop:1 #0F1724); color: #00E5FF; border: 1px solid #00E5FF; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: bold;')
        rover_flip_hbox.addWidget(self.rover_flip_btn_horz)

        rover_vbox.addLayout(rover_flip_hbox)
        self.rover_status_label = QLabel('Waiting for source')
        self.rover_status_label.setStyleSheet('color: #FFCC00; font-size: 10px;')
        rover_vbox.addWidget(self.rover_status_label)
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
        self.latency_label = QLabel("Gesture Frame Interval: <b style='color: #00E5FF;'>-- ms</b>")
        self.latency_label.setTextFormat(Qt.TextFormat.RichText)
        self.reconnect_btn = QPushButton('🔄 RECONNECT SERIAL')
        self.reconnect_btn.clicked.connect(self.reconnect_serial)
        self.toggle_log_btn = QPushButton('📜 OPEN LOG SIDEBAR ⮞')
        self.toggle_log_btn.setMinimumHeight(36)
        self.toggle_log_btn.clicked.connect(self.toggle_log_sidebar)
        link_vbox.addWidget(self.port_label)
        link_vbox.addWidget(self.latency_label)
        link_vbox.addWidget(self.reconnect_btn)
        link_vbox.addWidget(self.toggle_log_btn)
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

        self.radar_box = QGroupBox('ULTRASONIC RANGE')
        radar_vbox = QVBoxLayout()
        radar_vbox.setSpacing(6)
        radar_vbox.setContentsMargins(12, 16, 12, 10)

        self.radar_distance_label = QLabel('-- cm')
        self.radar_distance_label.setFont(QFont('Segoe UI', 30, QFont.Weight.Bold))
        self.radar_distance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.radar_distance_label.setStyleSheet(
            'color: #00E5FF; background-color: #0B0D12; border: 1px solid #2A2F3D; border-radius: 10px;'
        )

        self.radar_angle_label = QLabel('SWEEP ANGLE: --°')
        self.radar_angle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.radar_angle_label.setStyleSheet('color: #8A9AB8; font-size: 10px;')

        self.radar_range_bar = QProgressBar()
        self.radar_range_bar.setRange(0, 400)
        self.radar_range_bar.setValue(0)
        self.radar_range_bar.setTextVisible(False)
        self.radar_range_bar.setFixedHeight(9)
        self.radar_range_bar.setStyleSheet(
            'QProgressBar { background: #07090D; border: 1px solid #2A2F3D; border-radius: 4px; }'
            'QProgressBar::chunk { background: #00E5FF; border-radius: 3px; }'
        )

        self.radar_status_label = QLabel('WAITING FOR RADAR DATA')
        self.radar_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.radar_status_label.setStyleSheet('color: #FFCC00; font-size: 10px; font-weight: bold;')

        radar_vbox.addWidget(self.radar_distance_label, stretch=2)
        radar_vbox.addWidget(self.radar_angle_label)
        radar_vbox.addWidget(self.radar_range_bar)
        radar_vbox.addWidget(self.radar_status_label)
        self.radar_box.setLayout(radar_vbox)

        self.speed_box = QGroupBox('ROVER SPEED')
        speed_vbox = QVBoxLayout()
        speed_vbox.setSpacing(6)
        speed_vbox.setContentsMargins(12, 16, 12, 10)

        self.speed_sub = QLabel('DRIVE SPEED LIMIT')
        self.speed_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_sub.setStyleSheet('color: #6C7A9C; font-size: 10px;')

        self.speed_value_label = QLabel('68%')
        self.speed_value_label.setFont(QFont('Segoe UI', 30, QFont.Weight.Bold))
        self.speed_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_value_label.setStyleSheet(
            'color: #00E5FF; background-color: #0B0D12; border: 1px solid #2A2F3D; border-radius: 10px;'
        )

        speed_scale_hbox = QHBoxLayout()
        speed_scale_hbox.setContentsMargins(0, 0, 0, 0)
        speed_slow_label = QLabel('SLOW')
        speed_slow_label.setStyleSheet('color: #8A9AB8; font-size: 10px;')
        speed_fast_label = QLabel('FAST')
        speed_fast_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        speed_fast_label.setStyleSheet('color: #8A9AB8; font-size: 10px;')
        speed_scale_hbox.addWidget(speed_slow_label)
        speed_scale_hbox.addStretch()
        speed_scale_hbox.addWidget(speed_fast_label)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(0, 100)
        self.speed_slider.setValue(68)
        self.speed_pwm = round(68 * 255 / 100)
        self.speed_slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self.speed_slider.setStyleSheet(
            'QSlider::groove:horizontal { background: #07090D; border: 1px solid #2A2F3D; height: 8px; border-radius: 4px; }'
            'QSlider::sub-page:horizontal { background: #00E5FF; border-radius: 4px; }'
            'QSlider::add-page:horizontal { background: #07090D; border-radius: 4px; }'
            'QSlider::handle:horizontal { background: #00E5FF; border: 3px solid #0B0D12; min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px; margin: -6px 0; border-radius: 12px; }'
            'QSlider::handle:horizontal:hover { background: #66F2FF; border-radius: 12px; }'
        )
        self.speed_slider.valueChanged.connect(self.update_speed_display)

        self.speed_status_label = QLabel('READY FOR INPUT')
        self.speed_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_status_label.setStyleSheet('color: #FFCC00; font-size: 10px; font-weight: bold;')

        speed_vbox.addWidget(self.speed_sub)
        speed_vbox.addWidget(self.speed_value_label)
        speed_vbox.addLayout(speed_scale_hbox)
        speed_vbox.addWidget(self.speed_slider)
        speed_vbox.addWidget(self.speed_status_label)
        self.speed_box.setLayout(speed_vbox)

        self.log_box_group = QGroupBox('EVENT STREAM')
        log_vbox = QVBoxLayout()
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.append('[SYS] Project MANUS AD LUNAM Control Hub Active.')
        log_vbox.addWidget(self.log_box)
        self.log_box_group.setLayout(log_vbox)

        self.logs_dock = QDockWidget('SYS LOGS', self)
        self.logs_dock.setObjectName('SystemLogsDock')
        self.logs_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.logs_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.logs_dock.setMinimumWidth(280)
        self.logs_dock.setWidget(self.log_box_group)
        self.logs_dock.visibilityChanged.connect(self.update_log_sidebar_button)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.logs_dock)
        self.logs_dock.hide()

        self.telemetry_hbox.addWidget(self.link_box, stretch=100)
        self.telemetry_hbox.addWidget(self.payload_box, stretch=100)
        self.telemetry_hbox.addWidget(self.radar_box, stretch=100)
        self.telemetry_hbox.addWidget(self.speed_box, stretch=100)

        # Give the telemetry cards a little more vertical room; opening the dock
        # reduces the central area and naturally pushes both rows left.
        main_vbox.addLayout(cameras_hbox, stretch=5)
        main_vbox.addLayout(self.telemetry_hbox, stretch=2)

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
        self.toggle_log_btn.setText(
            '📜 CLOSE LOG SIDEBAR ◂' if visible else '📜 OPEN LOG SIDEBAR ⮞'
        )

    def update_speed_display(self, value):
        """Update the display and resend the active command at the new PWM speed."""
        self.speed_pwm = round(value * 255 / 100)
        self.speed_value_label.setText(f'{value}%')
        if self.is_serial_connected:
            if not self.sender.send_command(self.current_payload, self.speed_pwm):
                self.mark_serial_disconnected('Speed update write failed')

    def poll_radar_telemetry(self):
        """Read tagged distance samples from the transmitter's USB serial stream."""
        if not self.is_serial_connected:
            return

        for angle, distance_cm in self.sender.read_radar_telemetry():
            self.last_radar_update_time = time.monotonic()
            self.radar_distance_label.setText(f'{distance_cm} cm')
            self.radar_angle_label.setText(f'SWEEP ANGLE: {angle}°')
            self.radar_range_bar.setValue(distance_cm)

            if distance_cm >= 400:
                status = 'NO ECHO / OUT OF RANGE'
                color = '#FFCC00'
            else:
                status = 'RADAR LIVE'
                color = '#00E676'
            self.radar_status_label.setText(status)
            self.radar_status_label.setStyleSheet(
                f'color: {color}; font-size: 10px; font-weight: bold;'
            )

        if self.is_serial_connected and (
            self.sender.ser is None or not self.sender.ser.is_open
        ):
            self.mark_serial_disconnected('Telemetry read failed')

        if self.last_radar_update_time is None:
            if not self.is_serial_connected:
                self.radar_status_label.setText('SERIAL LINK OFFLINE')
            return

        if time.monotonic() - self.last_radar_update_time > 1.5:
            self.last_radar_update_time = None
            self.radar_distance_label.setText('-- cm')
            self.radar_angle_label.setText('SWEEP ANGLE: --°')
            self.radar_range_bar.setValue(0)
            self.radar_status_label.setText('NO RADAR DATA')
            self.radar_status_label.setStyleSheet(
                'color: #FF1744; font-size: 10px; font-weight: bold;'
            )

    def update_gesture_feed(self, qt_image, raw_frame):
        now = time.monotonic()
        interval_ms = int((now - self.last_frame_time) * 1000)
        self.last_frame_time = now
        self.latency_label.setText(
            f"Gesture Frame Interval: <b style='color: #00E5FF;'>{interval_ms} ms</b>"
        )

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

    def update_gesture_camera_status(self, status):
        self.gesture_status_label.setText(status)
        color = '#00E676' if status == 'Online' else '#FFCC00'
        if status in {'Stopped', 'Not configured'}:
            color = '#8A9AB8'
        self.gesture_status_label.setStyleSheet(f'color: {color}; font-size: 10px;')

    def flip_gesture_horz(self):
        """Toggle horizontal flip for gesture camera"""
        self.gesture_flip_horz = not self.gesture_flip_horz

        if self.gesture_thread and self.gesture_thread.isRunning():
            flip_mode = 1 if self.gesture_flip_horz else 0
            self.gesture_thread.flip = flip_mode
            mode = "FLIP HORZ" if self.gesture_flip_horz else "NO FLIP"
            self.gesture_flip_btn_horz.setText(f'🔄 {mode}')

            log_msg = f'[CAM] Gesture camera set to {mode} flip'
            self.log_box.append(log_msg)

    def flip_gesture_180(self):
        """Toggle 180° flip for gesture camera"""
        self.gesture_flip_180 = not self.gesture_flip_180

        if self.gesture_thread and self.gesture_thread.isRunning():
            flip_mode = -1 if self.gesture_flip_180 else 0
            self.gesture_thread.flip = flip_mode
            mode = "FLIP 180°" if self.gesture_flip_180 else "NO FLIP"
            self.gesture_flip_btn_180.setText(f'🔄 {mode}')

            log_msg = f'[CAM] Gesture camera set to {mode} flip'
            self.log_box.append(log_msg)

    def update_rover_camera_status(self, status):
        self.rover_status_label.setText(status)
        color = '#00E676' if status == 'Online' else '#FFCC00'
        if status in {'Stopped', 'Not configured'}:
            color = '#8A9AB8'
        self.rover_status_label.setStyleSheet(f'color: {color}; font-size: 10px;')

    def flip_rover_horz(self):
        """Toggle horizontal flip for rover camera"""
        self.rover_flip_horz = not self.rover_flip_horz

        if self.rover_thread and self.rover_thread.isRunning():
            flip_mode = 1 if self.rover_flip_horz else 0
            self.rover_thread.flip = flip_mode
            mode = "FLIP HORZ" if self.rover_flip_horz else "NO FLIP"
            self.rover_flip_btn_horz.setText(f'🔄 {mode}')

            log_msg = f'[CAM] Rover camera set to {mode} flip'
            self.log_box.append(log_msg)

    def flip_rover_180(self):
        """Toggle 180° flip for rover camera"""
        self.rover_flip_180 = not self.rover_flip_180

        if self.rover_thread and self.rover_thread.isRunning():
            flip_mode = -1 if self.rover_flip_180 else 0
            self.rover_thread.flip = flip_mode
            mode = "FLIP 180°" if self.rover_flip_180 else "NO FLIP"
            self.rover_flip_btn_180.setText(f'🔄 {mode}')

            log_msg = f'[CAM] Rover camera set to {mode} flip'
            self.log_box.append(log_msg)

    def reconnect_serial(self):
        if self.serial_connect_worker is not None and self.serial_connect_worker.isRunning():
            return

        self.is_serial_connected = False
        self.reconnect_btn.setEnabled(False)
        self.port_label.setText(
            "ESP32 Link: <span style='color: #FFCC00; font-weight: bold;'>CONNECTING...</span>"
        )
        self.log_box.append('[SYS] Attempting ESP32 re-connection...')
        self.serial_connect_worker = SerialConnectWorker(self.sender, self)
        self.serial_connect_worker.connection_finished.connect(self.on_serial_connect_finished)
        self.serial_connect_worker.start()

    def mark_serial_disconnected(self, reason):
        self.is_serial_connected = False
        self.port_label.setText(
            "ESP32 Link: <span style='color: #FF1744; font-weight: bold;'>DISCONNECTED</span>"
        )
        self.radar_status_label.setText('SERIAL LINK OFFLINE')
        self.radar_status_label.setStyleSheet(
            'color: #FF1744; font-size: 10px; font-weight: bold;'
        )
        self.log_box.append(f'[SYS] Serial connection lost: {reason}.')

    def on_serial_connect_finished(self, connected, detail):
        self.is_serial_connected = connected
        self.reconnect_btn.setEnabled(True)
        if connected:
            self.port_label.setText(
                f"ESP32 Link: <span style='color: #00E676; font-weight: bold;'>CONNECTED ({detail})</span>"
            )
            self.log_box.append(f'[SYS] Linked to ESP32 on port {detail}')
        else:
            self.port_label.setText(
                "ESP32 Link: <span style='color: #FF1744; font-weight: bold;'>DISCONNECTED</span>"
            )
            self.log_box.append('[SYS] Search failed. No active ESP32 COM port.')
            if detail:
                self.log_box.append(f'[SYS] Connection detail: {detail}')

    def closeEvent(self, event):
        if self.serial_connect_worker is not None and self.serial_connect_worker.isRunning():
            self.serial_connect_worker.wait(3000)
        if self.gesture_thread is not None:
            self.gesture_thread.stop()
        if self.rover_thread is not None:
            self.rover_thread.stop()
        self.sender.close()
        event.accept()

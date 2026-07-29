import os
import sys
import time
import cv2
from PyQt6.QtCore import QEasingCurve, Qt, QVariantAnimation
from PyQt6.QtGui import QFont, QIcon, QPixmap, QImage
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
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

        # Telemetry
        self.last_frame_time = time.time()
        self.current_payload = 'S'

        # Camera Sources (Change index/URL here for DroidCam, Wi-Fi stream, or USB devices)
        self.GESTURE_CAM_INDEX = 0  # Operator webcam
        self.ROVER_CAM_INDEX = 1    # Rover stream index / IP Camera URL / DroidCam index

        # 2. Build User Interface Layout
        self.init_ui()

        # 3. Initialize Camera Threads
        self.gesture_thread = CameraThread(source=self.GESTURE_CAM_INDEX, flip=True, detector=self.detector)
        self.gesture_thread.frame_processed.connect(self.update_gesture_feed)
        self.gesture_thread.start()

        self.rover_thread = CameraThread(source=self.ROVER_CAM_INDEX, flip=False, detector=None)
        self.rover_thread.frame_processed.connect(self.update_rover_feed)
        self.rover_thread.start()

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
        self.telemetry_hbox.addWidget(self.status_card_box, stretch=100)
        self.telemetry_hbox.addWidget(self.log_box_group, stretch=100)

        self.log_box.setVisible(False)

        main_vbox.addLayout(cameras_hbox, stretch=3)
        main_vbox.addLayout(self.telemetry_hbox, stretch=1)

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
        card_stretch = max(50, int((400 - log_stretch) / 3))
        self.telemetry_hbox.setStretch(0, card_stretch)
        self.telemetry_hbox.setStretch(1, card_stretch)
        self.telemetry_hbox.setStretch(2, card_stretch)
        self.telemetry_hbox.setStretch(3, log_stretch)

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

        hands_data = self.detector.get_hand_info(raw_frame)
        command = self.controller.get_command(hands_data)

        if command != self.current_payload:
            self.current_payload = command
            self.payload_label.setText(command)

            if self.is_serial_connected:
                self.sender.send_command(command)
                self.log_box.append(f"[TX] Command Sent: '{command}'")
            else:
                self.log_box.append(f"[LOCAL] Command Evaluated: '{command}' (Serial Offline)")

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
import sys
import time
import cv2
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, 
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QTextEdit
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QFont

from stream_manager import CameraThread
from hand_detector import HandDetector
from gesture_controller import GestureController
from serial_sender import SerialSender


class MADDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Project MANUS AD LUNAM - Command & Control Center")
        self.setGeometry(100, 100, 1280, 750)

        # 1. Hardware & Computer Vision Modules
        self.detector = HandDetector()
        self.controller = GestureController()
        self.sender = SerialSender()
        self.is_serial_connected = self.sender.connect()

        # Telemetry state
        self.last_frame_time = time.time()
        self.current_payload = "S"

        # 2. Build User Interface Layout
        self.init_ui()

        # 3. Initialize Camera Threads
        # Gesture Camera (Laptop Cam index 0)
        self.gesture_thread = CameraThread(source=0, flip=True, detector=self.detector)
        self.gesture_thread.frame_processed.connect(self.update_gesture_feed)
        self.gesture_thread.start()

        # Rover Camera (Set source to DroidCam IP URL when ready, e.g. "http://192.168.137.45:4747/video")
        self.rover_thread = CameraThread(source=1, flip=False, detector=None)
        self.rover_thread.frame_processed.connect(self.update_rover_feed)
        self.rover_thread.start()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # CustomTkinter Dark Aesthetic Styling with Boosted Font Sizes
        self.setStyleSheet("""
            QMainWindow { background-color: #121212; }
            
            QGroupBox { 
                color: #1F6AA5; 
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 15px;
                font-weight: bold; 
                border: 2px solid #2B2B2B; 
                border-radius: 10px; 
                margin-top: 12px; 
                background-color: #1E1E1E;
            }
            QGroupBox::title { 
                subcontrol-origin: margin; 
                left: 15px; 
                padding: 0 8px; 
                background-color: #1E1E1E;
            }
            
            QLabel { 
                color: #E0E0E0; 
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 16px;
                font-weight: 500;
            }
            
            QPushButton {
                background-color: #1F6AA5;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 10px 14px;
                font-weight: bold;
                font-size: 14px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton:hover { background-color: #144870; }
            QPushButton:pressed { background-color: #0F3552; }
            
            QTextEdit { 
                background-color: #0A0A0A; 
                color: #2CC985; 
                border: 1px solid #2B2B2B;
                border-radius: 6px;
                font-family: 'Consolas', 'Cascadia Code', monospace; 
                font-size: 13px;
            }
        """)

        main_vbox = QVBoxLayout()
        central_widget.setLayout(main_vbox)

        # =========================================================================
        # TOP ROW: Dual Camera Stream Widgets (Side-by-Side)
        # =========================================================================
        cameras_hbox = QHBoxLayout()

        # Left: Operator Gesture Feed
        self.gesture_box = QGroupBox("OPERATOR GESTURE FEED")
        gesture_vbox = QVBoxLayout()
        self.gesture_feed_label = QLabel("Initializing Video Stream...")
        self.gesture_feed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gesture_feed_label.setMinimumSize(480, 320)
        gesture_vbox.addWidget(self.gesture_feed_label)
        self.gesture_box.setLayout(gesture_vbox)

        # Right: Rover Terrain Feed
        self.rover_box = QGroupBox("ROVER TERRAIN FEED")
        rover_vbox = QVBoxLayout()
        self.rover_feed_label = QLabel("Connecting to DroidCam Stream...")
        self.rover_feed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rover_feed_label.setMinimumSize(480, 320)
        rover_vbox.addWidget(self.rover_feed_label)
        self.rover_box.setLayout(rover_vbox)

        cameras_hbox.addWidget(self.gesture_box, stretch=1)
        cameras_hbox.addWidget(self.rover_box, stretch=1)

        # =========================================================================
        # BOTTOM ROW: Hardware Link & Latency | Payload | Coords | Collapsible Log
        # =========================================================================
        telemetry_hbox = QHBoxLayout()

        # 1. System Link & Latency Card
        link_box = QGroupBox("HARDWARE LINK & LATENCY")
        link_vbox = QVBoxLayout()
        
        self.port_label = QLabel(f"ESP32 Link: {'CONNECTED (' + str(self.sender.port) + ')' if self.is_serial_connected else 'DISCONNECTED'}")
        self.latency_label = QLabel("Frame Latency: 0 ms")
        self.reconnect_btn = QPushButton("🔄 RECONNECT SERIAL")
        self.reconnect_btn.clicked.connect(self.reconnect_serial)

        link_vbox.addWidget(self.port_label)
        link_vbox.addWidget(self.latency_label)
        link_vbox.addWidget(self.reconnect_btn)
        link_box.setLayout(link_vbox)

        # 2. Command Payload Status Card
        payload_box = QGroupBox("COMMAND PAYLOAD")
        payload_vbox = QVBoxLayout()
        self.payload_label = QLabel("S")
        self.payload_label.setFont(QFont("Segoe UI", 36, QFont.Weight.Bold))
        self.payload_label.setStyleSheet("color: #FFCC00;")
        self.payload_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        payload_vbox.addWidget(self.payload_label)
        payload_box.setLayout(payload_vbox)

        # 3. Tile Coordinates & Logs Toggle Card
        coords_box = QGroupBox("TERRAIN & CONTROLS")
        coords_vbox = QVBoxLayout()
        self.coord_label = QLabel("Tile Coordinates:\n[X: 00 | Y: 00]")
        self.coord_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.coord_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Toggle Button for Collapsible Console Logs
        self.toggle_log_btn = QPushButton("CONSOLE LOGS ⮞")
        self.toggle_log_btn.clicked.connect(self.toggle_logs)

        coords_vbox.addWidget(self.coord_label)
        coords_vbox.addWidget(self.toggle_log_btn)
        coords_box.setLayout(coords_vbox)

        # 4. Collapsible Log Console Widget (Initially Hidden)
        self.log_box_group = QGroupBox("SYSTEM CONSOLE LOGS")
        log_vbox = QVBoxLayout()
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.append("[SYS] Project MANUS AD LUNAM Control Hub Active.")
        log_vbox.addWidget(self.log_box)
        self.log_box_group.setLayout(log_vbox)
        self.log_box_group.setVisible(False)  # Hidden by default

        # Assemble Bottom Row
        telemetry_hbox.addWidget(link_box, stretch=1)
        telemetry_hbox.addWidget(payload_box, stretch=1)
        telemetry_hbox.addWidget(coords_box, stretch=1)
        telemetry_hbox.addWidget(self.log_box_group, stretch=2)

        # Add Top and Bottom sections to Main Layout
        main_vbox.addLayout(cameras_hbox, stretch=3)
        main_vbox.addLayout(telemetry_hbox, stretch=1)

    def toggle_logs(self):
        """Shows or hides the console log group panel dynamically."""
        is_visible = self.log_box_group.isVisible()
        self.log_box_group.setVisible(not is_visible)
        if not is_visible:
            self.toggle_log_btn.setText("HIDE LOGS ⮟")
        else:
            self.toggle_log_btn.setText("CONSOLE LOGS ⮞")

    def update_gesture_feed(self, qt_image, raw_frame):
        """Processes live camera frames, updates FPS latency, and evaluates gestures."""
        now = time.time()
        latency_ms = int((now - self.last_frame_time) * 1000)
        self.last_frame_time = now
        self.latency_label.setText(f"Frame Latency: {latency_ms} ms")

        # Display image on UI Label
        pixmap = QPixmap.fromImage(qt_image)
        self.gesture_feed_label.setPixmap(pixmap.scaled(
            self.gesture_feed_label.size(), 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        ))

        # Evaluate Gesture
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
        """Renders the rover terrain camera feed."""
        pixmap = QPixmap.fromImage(qt_image)
        self.rover_feed_label.setPixmap(pixmap.scaled(
            self.rover_feed_label.size(), 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        ))

    def reconnect_serial(self):
        """Attempts to re-establish connection with the ESP32 COM port."""
        self.log_box.append("[SYS] Attempting ESP32 re-connection...")
        self.is_serial_connected = self.sender.connect()
        if self.is_serial_connected:
            self.port_label.setText(f"ESP32 Link: CONNECTED ({self.sender.port})")
            self.log_box.append(f"[SYS] Linked to ESP32 on port {self.sender.port}")
        else:
            self.port_label.setText("ESP32 Link: DISCONNECTED")
            self.log_box.append("[SYS] Search failed. No active ESP32 COM port.")

    def closeEvent(self, event):
        """Cleanup hardware threads on window close."""
        self.gesture_thread.stop()
        self.rover_thread.stop()
        self.sender.close()
        event.accept()
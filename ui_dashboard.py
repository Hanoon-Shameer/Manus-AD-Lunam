import sys
import time
import cv2
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, 
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QFont

from stream_manager import CameraThread
from hand_detector import HandDetector
from gesture_controller import GestureController
from serial_sender import SerialSender


class MADDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Project MANUS AD LUNAM - Command & Control Center")
        self.setGeometry(100, 100, 1280, 720)

        # 1. Initialize Computer Vision & Hardware Pipelines
        self.detector = HandDetector()
        self.controller = GestureController()
        self.sender = SerialSender()
        self.is_serial_connected = self.sender.connect()

        # Telemetry tracking variables
        self.last_frame_time = time.time()
        self.current_payload = "S"

        # 2. Build Dashboard Layout & Styling
        self.init_ui()

        # 3. Initialize Camera Threads (Stream Manager)
        # Gesture Cam: Uses Laptop Webcam (index 0) or local video
        self.gesture_thread = CameraThread(source=0, flip=True, detector=self.detector)
        self.gesture_thread.frame_processed.connect(self.update_gesture_feed)
        self.gesture_thread.start()

        # Rover Cam: Replace source string with DroidCam IP URL when active
        # e.g., "http://192.168.137.45:4747/video" or index 1 for second webcam
        self.rover_thread = CameraThread(source=0, flip=False, detector=None)
        self.rover_thread.frame_processed.connect(self.update_rover_feed)
        self.rover_thread.start()

    def init_ui(self):
        """Builds the main window layout grid, side panels, and styling."""
        # Main central widget & dark futuristic theme
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.setStyleSheet("""
            QMainWindow { background-color: #0F111A; }
            QGroupBox { 
                color: #00E5FF; 
                font-weight: bold; 
                border: 1px solid #1E2640; 
                border-radius: 8px; 
                margin-top: 10px; 
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLabel { color: #E0E6ED; font-size: 14px; }
            QPushButton {
                background-color: #1E2640;
                color: #00E5FF;
                border: 1px solid #00E5FF;
                border-radius: 5px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #00E5FF; color: #0F111A; }
            QTextEdit { background-color: #05070A; color: #00FF66; font-family: Consolas; }
        """)

        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)

        # --- LEFT PANEL: Dual Video Feeds (2/3 width) ---
        video_layout = QGridLayout()

        # Feed 1: Gesture Control Stream
        self.gesture_box = QGroupBox("OPERATOR GESTURE FEED (PC CAM)")
        box_layout1 = QVBoxLayout()
        self.gesture_feed_label = QLabel("Initializing Video Stream...")
        self.gesture_feed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gesture_feed_label.setMinimumSize(480, 320)
        box_layout1.addWidget(self.gesture_feed_label)
        self.gesture_box.setLayout(box_layout1)

        # Feed 2: Rover Terrain Stream
        self.rover_box = QGroupBox("ROVER TERRAIN FEED (DROIDCAM)")
        box_layout2 = QVBoxLayout()
        self.rover_feed_label = QLabel("Connecting to DroidCam Stream...")
        self.rover_feed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rover_feed_label.setMinimumSize(480, 320)
        box_layout2.addWidget(self.rover_feed_label)
        self.rover_box.setLayout(box_layout2)

        video_layout.addWidget(self.gesture_box, 0, 0)
        video_layout.addWidget(self.rover_box, 0, 1)

        # --- RIGHT PANEL: Telemetry & Status Logs (1/3 width) ---
        side_panel = QVBoxLayout()

        # Group 1: Hardware Connection & Latency Status
        status_group = QGroupBox("SYSTEM TELEMETRY")
        status_layout = QVBoxLayout()
        
        self.port_label = QLabel(f"ESP32 Link: {'CONNECTED (' + str(self.sender.port) + ')' if self.is_serial_connected else 'DISCONNECTED'}")
        self.latency_label = QLabel("Frame Latency: 0 ms")
        self.payload_label = QLabel("Current Payload: S (STOP)")
        self.payload_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.payload_label.setStyleSheet("color: #FFCC00;")

        status_layout.addWidget(self.port_label)
        status_layout.addWidget(self.latency_label)
        status_layout.addWidget(self.payload_label)
        status_group.setLayout(status_layout)

        # Group 2: Tile Coordinates & 3D Terrain Placeholder
        tile_group = QGroupBox("TERRAIN COORDINATES")
        tile_layout = QVBoxLayout()
        self.coord_label = QLabel("Tile Coordinates: [X: 00 | Y: 00]")
        tile_layout.addWidget(self.coord_label)
        tile_group.setLayout(tile_layout)

        # Group 3: Serial Communication Console Output Log
        log_group = QGroupBox("SYSTEM LOGS")
        log_layout = QVBoxLayout()
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.append("[SYS] Project MANUS AD LUNAM Dashboard Initialized.")
        log_layout.addWidget(self.log_box)
        log_group.setLayout(log_layout)

        # Reconnect Serial Button
        self.reconnect_btn = QPushButton("RECONNECT SERIAL LINK")
        self.reconnect_btn.clicked.connect(self.reconnect_serial)

        # Assemble Right Panel
        side_panel.addWidget(status_group)
        side_panel.addWidget(tile_group)
        side_panel.addWidget(log_group)
        side_panel.addWidget(self.reconnect_btn)

        # Add left and right sections to main layout
        main_layout.addLayout(video_layout, stretch=2)
        main_layout.addLayout(side_panel, stretch=1)

    def update_gesture_feed(self, qt_image, raw_frame):
        """Triggered whenever CameraThread emits a new frame for the gesture feed."""
        # Compute real-time pipeline frame processing latency
        now = time.time()
        latency_ms = int((now - self.last_frame_time) * 1000)
        self.last_frame_time = now
        self.latency_label.setText(f"Frame Latency: {latency_ms} ms")

        # Convert QImage to QPixmap and render on UI label
        pixmap = QPixmap.fromImage(qt_image)
        self.gesture_feed_label.setPixmap(pixmap.scaled(
            self.gesture_feed_label.size(), 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        ))

        # Run Hand Detection & Gesture Mapping pipeline on raw frame
        hands_data = self.detector.get_hand_info(raw_frame)
        command = self.controller.get_command(hands_data)

        # Send packet down serial if new gesture detected
        if command != self.current_payload:
            self.current_payload = command
            self.payload_label.setText(f"Current Payload: {command}")
            
            if self.is_serial_connected:
                self.sender.send_command(command)
                self.log_box.append(f"[TX] Payload sent: '{command}'")
            else:
                self.log_box.append(f"[LOCAL] Command evaluated: '{command}' (Serial offline)")

    def update_rover_feed(self, qt_image, raw_frame):
        """Triggered whenever CameraThread emits a new frame for the DroidCam feed."""
        pixmap = QPixmap.fromImage(qt_image)
        self.rover_feed_label.setPixmap(pixmap.scaled(
            self.rover_feed_label.size(), 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        ))

    def reconnect_serial(self):
        """Manual trigger to attempt auto-reconnect to the ESP32 COM port."""
        self.log_box.append("[SYS] Attempting ESP32 re-connection...")
        self.is_serial_connected = self.sender.connect()
        if self.is_serial_connected:
            self.port_label.setText(f"ESP32 Link: CONNECTED ({self.sender.port})")
            self.log_box.append(f"[SYS] Re-connected to port {self.sender.port}")
        else:
            self.port_label.setText("ESP32 Link: DISCONNECTED")
            self.log_box.append("[SYS] Failed to locate active ESP32 COM port.")

    def closeEvent(self, event):
        """Gracefully shuts down camera threads when the window is closed."""
        self.gesture_thread.stop()
        self.rover_thread.stop()
        self.sender.close()
        event.accept()
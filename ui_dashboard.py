import sys
import os
import time
import cv2
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, 
    QVBoxLayout, QHBoxLayout, QGroupBox, QTextEdit,
    QSizePolicy
)
from PyQt6.QtCore import Qt, QVariantAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QFont, QIcon

from stream_manager import CameraThread
from hand_detector import HandDetector
from gesture_controller import GestureController
from serial_sender import SerialSender


class MADDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Project MANUS AD LUNAM - Command & Control Center")
        self.setGeometry(100, 100, 1280, 750)

        # Build path to icon.png in the same directory as this file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "icon.png")

        print(f"Checking icon path: {icon_path}")
        print(f"Icon exists? {os.path.exists(icon_path)}")
        
        # Set window title bar and taskbar icon
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

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

        # Rover Camera (Set flip=False if DroidCam text is mirrored)
        self.rover_thread = CameraThread(source="http://100.75.236.124:4747/video", flip=False, detector=None)
        self.rover_thread.frame_processed.connect(self.update_rover_feed)
        self.rover_thread.start()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # High-Tech Command Center Styling
        self.setStyleSheet("""
            QMainWindow { 
                background-color: #0B0D12; 
            }
            
            /* Modernized Group Containers */
            QGroupBox { 
                color: #00E5FF; 
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
                font-weight: bold; 
                letter-spacing: 1px;
                border: 1px solid #2A2F3D; 
                border-radius: 12px; 
                margin-top: 20px; 
                padding-top: 15px;
                background-color: #131722;
            }
            
            QGroupBox::title { 
                subcontrol-origin: margin; 
                subcontrol-position: top left;
                left: 15px; 
                padding: 2px 10px; 
                background-color: #1A2130;
                border: 1px solid #00E5FF;
                border-radius: 5px;
                color: #00E5FF;
            }
            
            QLabel { 
                color: #C3CEE0; 
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
            }
            
            /* Sleek Action Buttons */
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A2638, stop:1 #0F1724);
                color: #00E5FF;
                border: 1px solid #00E5FF;
                border-radius: 8px;
                padding: 10px 14px;
                font-weight: bold;
                font-size: 13px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton:hover { 
                background: #00E5FF; 
                color: #0B0D12;
            }
            QPushButton:pressed { 
                background: #00B2CC; 
                color: #0B0D12;
            }
            
            /* Console Output */
            QTextEdit { 
                background-color: #07090D; 
                color: #00FF66; 
                border: 1px solid #2A2F3D;
                border-radius: 8px;
                font-family: 'Consolas', 'Cascadia Code', monospace; 
                font-size: 12px;
                padding: 5px;
            }
        """)

        main_vbox = QVBoxLayout()
        main_vbox.setSpacing(15)
        main_vbox.setContentsMargins(15, 15, 15, 15)
        central_widget.setLayout(main_vbox)

        # =========================================================================
        # TOP ROW: Dual Camera Stream Widgets (STATIONARY)
        # =========================================================================
        cameras_hbox = QHBoxLayout()
        cameras_hbox.setSpacing(15)

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
        # BOTTOM ROW: Link | Payload | Coords | Console Log Drawer
        # =========================================================================
        self.telemetry_hbox = QHBoxLayout()
        self.telemetry_hbox.setSpacing(15)

        # 1. System Link & Latency Card (Shortened Title)
        self.link_box = QGroupBox("SYSTEM LINK")
        link_vbox = QVBoxLayout()
        link_vbox.setSpacing(8)
        
        status_text = f"ESP32 Link: <span style='color: #00E676; font-weight: bold;'>CONNECTED ({self.sender.port})</span>" if self.is_serial_connected else "ESP32 Link: <span style='color: #FF1744; font-weight: bold;'>DISCONNECTED</span>"
        
        self.port_label = QLabel(status_text)
        self.port_label.setTextFormat(Qt.TextFormat.RichText)
        
        self.latency_label = QLabel("Frame Latency: <b style='color: #00E5FF;'>0 ms</b>")
        self.latency_label.setTextFormat(Qt.TextFormat.RichText)

        self.reconnect_btn = QPushButton("🔄 RECONNECT SERIAL")
        self.reconnect_btn.clicked.connect(self.reconnect_serial)

        link_vbox.addWidget(self.port_label)
        link_vbox.addWidget(self.latency_label)
        link_vbox.addWidget(self.reconnect_btn)
        link_vbox.addStretch()
        self.link_box.setLayout(link_vbox)

        # 2. Command Payload Status Card (Shortened Title)
        self.payload_box = QGroupBox("PAYLOAD")
        payload_vbox = QVBoxLayout()
        
        self.payload_sub = QLabel("ACTIVE TRANSMISSION COMMAND")
        self.payload_sub.setFont(QFont("Segoe UI", 9))
        self.payload_sub.setStyleSheet("color: #6C7A9C;")
        self.payload_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.payload_label = QLabel("S")
        self.payload_label.setFont(QFont("Segoe UI", 36, QFont.Weight.Bold))
        self.payload_label.setStyleSheet("color: #FFCC00; background-color: #0B0D12; border: 1px solid #2A2F3D; border-radius: 10px;")
        self.payload_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        payload_vbox.addWidget(self.payload_sub)
        payload_vbox.addWidget(self.payload_label)
        self.payload_box.setLayout(payload_vbox)

        # 3. Terrain Coordinates Card (Shortened Title)
        self.coords_box = QGroupBox("GRID POS")
        coords_vbox = QVBoxLayout()
        coords_vbox.setSpacing(10)
        
        self.coord_label = QLabel("GRID POSITION<br><b style='font-size: 18px; color: #00E5FF;'>[ X: 00 | Y: 00 ]</b>")
        self.coord_label.setTextFormat(Qt.TextFormat.RichText)
        self.coord_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        coords_vbox.addStretch()
        coords_vbox.addWidget(self.coord_label)
        coords_vbox.addStretch()
        self.coords_box.setLayout(coords_vbox)

        # 4. System Console Logs Drawer Widget (Shortened Title)
        self.log_box_group = QGroupBox("SYS LOGS")
        log_vbox = QVBoxLayout()
        
        self.toggle_log_btn = QPushButton("📜 TOGGLE LOGS ⮞")
        self.toggle_log_btn.clicked.connect(self.toggle_logs)
        
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.append("[SYS] Project MANUS AD LUNAM Control Hub Active.")
        
        log_vbox.addWidget(self.toggle_log_btn)
        log_vbox.addWidget(self.log_box)
        self.log_box_group.setLayout(log_vbox)

        # Add components to bottom telemetry layout
        self.telemetry_hbox.addWidget(self.link_box, stretch=100)
        self.telemetry_hbox.addWidget(self.payload_box, stretch=100)
        self.telemetry_hbox.addWidget(self.coords_box, stretch=100)
        self.telemetry_hbox.addWidget(self.log_box_group, stretch=100)

        # Set initial collapsed state for log text box
        self.log_box.setVisible(False)

        # Add top and bottom rows to main container
        main_vbox.addLayout(cameras_hbox, stretch=3)
        main_vbox.addLayout(self.telemetry_hbox, stretch=1)

    def toggle_logs(self):
        """Animates bottom row stretch factors to shrink cards 1-3 to the left and expand logs."""
        is_expanded = self.log_box.isVisible()

        self.anim = QVariantAnimation(self)
        self.anim.setDuration(300)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        if is_expanded:
            self.toggle_log_btn.setText("📜 TOGGLE LOGS ⮞")
            self.anim.setStartValue(250)
            self.anim.setEndValue(100)
            self.anim.finished.connect(lambda: self.log_box.setVisible(False))
        else:
            self.log_box.setVisible(True)
            self.toggle_log_btn.setText("📜 HIDE LOGS ⮟")
            self.anim.setStartValue(100)
            self.anim.setEndValue(250)

        self.anim.valueChanged.connect(self.update_bottom_row_stretches)
        self.anim.start()

    def update_bottom_row_stretches(self, log_stretch_val):
        """Dynamically adjusts stretch factors of the bottom row widgets."""
        log_stretch = int(log_stretch_val)
        card_stretch = max(50, int((400 - log_stretch) / 3))

        self.telemetry_hbox.setStretch(0, card_stretch) # Link box
        self.telemetry_hbox.setStretch(1, card_stretch) # Payload box
        self.telemetry_hbox.setStretch(2, card_stretch) # Coords box
        self.telemetry_hbox.setStretch(3, log_stretch)  # Log Box Group

    def update_gesture_feed(self, qt_image, raw_frame):
        """Processes live camera frames, updates FPS latency, and evaluates gestures."""
        now = time.time()
        latency_ms = int((now - self.last_frame_time) * 1000)
        self.last_frame_time = now
        self.latency_label.setText(f"Frame Latency: <b style='color: #00E5FF;'>{latency_ms} ms</b>")

        label_size = self.gesture_feed_label.size()
        if label_size.width() > 0 and label_size.height() > 0:
            pixmap = QPixmap.fromImage(qt_image)
            self.gesture_feed_label.setPixmap(pixmap.scaled(
                label_size, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            ))

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
        label_size = self.rover_feed_label.size()
        if label_size.width() > 0 and label_size.height() > 0:
            pixmap = QPixmap.fromImage(qt_image)
            self.rover_feed_label.setPixmap(pixmap.scaled(
                label_size, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            ))

    def reconnect_serial(self):
        """Attempts to re-establish connection with the ESP32 COM port."""
        self.log_box.append("[SYS] Attempting ESP32 re-connection...")
        self.is_serial_connected = self.sender.connect()
        if self.is_serial_connected:
            self.port_label.setText(f"ESP32 Link: <span style='color: #00E676; font-weight: bold;'>CONNECTED ({self.sender.port})</span>")
            self.log_box.append(f"[SYS] Linked to ESP32 on port {self.sender.port}")
        else:
            self.port_label.setText("ESP32 Link: <span style='color: #FF1744; font-weight: bold;'>DISCONNECTED</span>")
            self.log_box.append("[SYS] Search failed. No active ESP32 COM port.")

    def closeEvent(self, event):
        """Cleanup hardware threads on window close."""
        self.gesture_thread.stop()
        self.rover_thread.stop()
        self.sender.close()
        event.accept()
import cv2
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

class CameraThread(QThread):
    # Custom PyQt Signal emitting: (QImage for rendering, raw BGR frame for CV processing)
    frame_processed = pyqtSignal(QImage, object)

    def __init__(self, source=0, flip=False, detector=None):
        super().__init__()
        self.source = source
        self.flip = flip
        self.detector = detector
        self.running = True

    def run(self):
        """Main loop executed when the thread starts."""
        cap = cv2.VideoCapture(self.source)

        while self.running:
            success, frame = cap.read()
            if not success:
                continue

            # Mirror horizontally if requested (useful for webcams)
            if self.flip:
                frame = cv2.flip(frame, 1)

            # Pass frame through HandDetector if attached
            if self.detector is not None:
                frame = self.detector.find_hands(frame)

            # Keep a copy of the raw BGR numpy array for downstream processing
            raw_frame = frame.copy()

            # Convert BGR (OpenCV) -> RGB (PyQt)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w

            # Create a PyQt-compatible image object
            qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

            # Send data back to the main UI thread via signal
            self.frame_processed.emit(qt_image, raw_frame)

        cap.release()

    def stop(self):
        """Safely terminates the video capture loop."""
        self.running = False
        self.wait()
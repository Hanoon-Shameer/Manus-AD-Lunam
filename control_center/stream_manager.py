import threading

import cv2
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

class CameraThread(QThread):
    # Signals: rendered image + raw BGR frame; human-readable connection status.
    frame_processed = pyqtSignal(QImage, object)
    status_changed = pyqtSignal(str)

    def __init__(self, source=0, flip=0, detector=None):
        super().__init__()
        self.source = source
        self.flip = flip  # Can be 0 (no flip), 1 (horizontal), -1 (180°)
        self.detector = detector
        self._stop_event = threading.Event()
        self._capture = None

    def _open_capture(self):
        """Open a camera or request bounded FFmpeg timeouts for network URLs."""
        is_network_url = (
            isinstance(self.source, str)
            and self.source.lower().startswith(("http://", "https://", "rtsp://", "rtsps://"))
        )
        if not is_network_url:
            return cv2.VideoCapture(self.source)

        capture = cv2.VideoCapture()
        backend = getattr(cv2, "CAP_FFMPEG", 0)
        open_timeout = getattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC", None)
        read_timeout = getattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC", None)
        parameters = []
        if open_timeout is not None:
            parameters.extend([open_timeout, 3000])
        if read_timeout is not None:
            parameters.extend([read_timeout, 3000])

        try:
            if parameters:
                opened = capture.open(self.source, backend, parameters)
            else:
                opened = capture.open(self.source, backend)
        except (TypeError, cv2.error):
            opened = False

        if opened:
            return capture

        capture.release()
        # Compatibility fallback for OpenCV builds that reject timeout parameters.
        return cv2.VideoCapture(self.source)

    def run(self):
        """Capture frames and retry disconnected sources with capped exponential backoff."""
        if self.source is None:
            self.status_changed.emit("Not configured")
            return

        retry_delay = 0.5
        try:
            while not self._stop_event.is_set():
                self.status_changed.emit("Connecting…")
                capture = None
                try:
                    capture = self._open_capture()
                    self._capture = capture
                except (cv2.error, TypeError, ValueError) as exc:
                    self.status_changed.emit(f"Open failed ({exc}); retrying")

                if capture is None or not capture.isOpened():
                    if capture is not None:
                        capture.release()
                    self._capture = None
                    self.status_changed.emit(f"Unavailable — retrying in {retry_delay:.1f}s")
                    if self._stop_event.wait(retry_delay):
                        break
                    retry_delay = min(retry_delay * 2, 8.0)
                    continue

                self.status_changed.emit("Online")
                stream_failed = False
                received_frame = False

                while not self._stop_event.is_set():
                    try:
                        success, frame = capture.read()
                    except cv2.error:
                        success, frame = False, None

                    if not success or frame is None:
                        stream_failed = True
                        break
                    received_frame = True

                    if self.flip:
                        frame = cv2.flip(frame, self.flip)
                    if self.detector is not None:
                        frame = self.detector.find_hands(frame)

                    raw_frame = frame.copy()
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    height, width, channels = rgb_frame.shape
                    bytes_per_line = channels * width
                    qt_image = QImage(
                        rgb_frame.data,
                        width,
                        height,
                        bytes_per_line,
                        QImage.Format.Format_RGB888,
                    ).copy()
                    self.frame_processed.emit(qt_image, raw_frame)

                capture.release()
                self._capture = None

                if stream_failed and not self._stop_event.is_set():
                    if received_frame:
                        retry_delay = 0.5
                    self.status_changed.emit(f"Feed lost — retrying in {retry_delay:.1f}s")
                    if self._stop_event.wait(retry_delay):
                        break
                    retry_delay = min(retry_delay * 2, 8.0)
        finally:
            if self._capture is not None:
                self._capture.release()
                self._capture = None
            self.status_changed.emit("Stopped")

    def stop(self):
        """Request a cooperative stop and wait briefly for a network-read timeout."""
        self._stop_event.set()
        self.requestInterruption()
        self.wait(4000)

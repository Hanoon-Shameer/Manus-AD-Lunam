import cv2
from hand_detector import HandDetector

def initialize_system():
    """Initializes the webcam and the hand detector."""
    cap = cv2.VideoCapture(0)  # Use the second camera (index 1)
    detector = HandDetector()
    return cap, detector

def process_frame(cap, detector):
    """Captures a single frame, processes landmarks, and returns it."""
    success, frame = cap.read()
    if not success:
        return False, None
    
    # Draw the lines on the hand
    frame = detector.find_hands(frame)
    return True, frame
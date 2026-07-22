import cv2
from hand_detector import HandDetector

# Global variable to track if the current camera requires mirror correction
should_flip = False

def initialize_system(cam_index=0):
    """Initializes the webcam based on index and configures the hand detector."""
    global should_flip
    cap = cv2.VideoCapture(cam_index)
    detector = HandDetector()
    
    # Only flip if using the default built-in laptop camera (index 0)
    should_flip = (cam_index == 0)
    
    return cap, detector

def process_frame(cap, detector):
    """Captures a single frame, conditionally flips it, and extracts landmarks."""
    global should_flip
    success, frame = cap.read()
    if not success:
        return False, None
    
    # Mirror the image horizontally ONLY if running on camera index 0
    if should_flip:
        frame = cv2.flip(frame, 1)
    
    # Draw the lines on the hand
    frame = detector.find_hands(frame)
    return True, frame  
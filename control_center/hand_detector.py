import cv2
import mediapipe as mp

class HandDetector:
    def __init__(self, mode=False, max_hands=2, detection_con=0.5, track_con=0.5):
        self.mode = mode
        self.max_hands = max_hands
        self.detection_con = detection_con
        self.track_con = track_con
        
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=self.mode,
            max_num_hands=self.max_hands,
            min_detection_confidence=self.detection_con,
            min_tracking_confidence=self.track_con
        )
        self.mp_draw = mp.solutions.drawing_utils

        # OpenCV uses (Blue, Green, Red) format:
        # Dark Blue dots: (180, 50, 0)
        self.landmark_style = self.mp_draw.DrawingSpec(
            color=(180, 50, 0), thickness=2, circle_radius=4
        )
        # Light Blue / Cyan connections (matches dashboard #00E5FF): (255, 229, 0)
        self.connection_style = self.mp_draw.DrawingSpec(
            color=(255, 229, 0), thickness=2
        )

    def find_hands(self, img, draw=True):
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self.results = self.hands.process(img_rgb)
        
        if self.results.multi_hand_landmarks:
            for hand_lms in self.results.multi_hand_landmarks:
                if draw:
                    self.mp_draw.draw_landmarks(
                        img, 
                        hand_lms, 
                        self.mp_hands.HAND_CONNECTIONS,
                        landmark_drawing_spec=self.landmark_style,
                        connection_drawing_spec=self.connection_style
                    )
        return img

    def get_hand_info(self, img):
        """
        Returns a dictionary containing data for both hands with flipped labels 
        to account for webcam mirroring.
        """
        hands_data = {}
        
        if self.results.multi_hand_landmarks:
            for hand_lms, hand_handedness in zip(self.results.multi_hand_landmarks, self.results.multi_handedness):
                # Grab the raw label from MediaPipe ('Left' or 'Right')
                mp_label = hand_handedness.classification[0].label
                
                # INVERSION LOGIC: Force the opposite label
                if mp_label == "Left":
                    label = "Right"
                else:
                    label = "Left"
                
                lm_list = []
                for lm in hand_lms.landmark:
                    h, w, c = img.shape
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    lm_list.append((cx, cy))
                
                hands_data[label] = lm_list
                
        return hands_data
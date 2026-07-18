class GestureController:
    def __init__(self):
        pass

    def is_finger_open(self, lm_list, tip_id, pip_id):
        """Returns True if the finger tip is higher up (smaller y) than the knuckle."""
        return lm_list[tip_id][1] < lm_list[pip_id][1]

    def get_active_fingers(self, lm_list):
        """
        Maps out exactly which fingers are open.
        """
        fingers = {
            'index': self.is_finger_open(lm_list, 8, 6),
            'middle': self.is_finger_open(lm_list, 12, 10),
            'ring': self.is_finger_open(lm_list, 16, 14),
            'pinky': self.is_finger_open(lm_list, 20, 18)
        }
        
        # Thumb check: True if thumb tip is far away from the palm base horizontally
        fingers['thumb'] = abs(lm_list[4][0] - lm_list[0][0]) > abs(lm_list[2][0] - lm_list[0][0])
        return fingers

    def get_command(self, hands_data):
        detected_hands = list(hands_data.values())
        
        # Safety fallback if hands drop out of frame
        if len(detected_hands) == 0:
            return "NO HANDS DETECTED"
        if len(detected_hands) == 1:
            return "STOP" # Default to stop for safety if one hand vanishes

        # Sort hands by screen position so your left side is always screen_left
        sorted_hands = sorted(detected_hands, key=lambda lm: lm[0][0])
        left_f = self.get_active_fingers(sorted_hands[0])
        right_f = self.get_active_fingers(sorted_hands[1])

        left_open_count = sum(left_f.values())
        right_open_count = sum(right_f.values())

        # --- STEP 1: DECODE LEFT HAND (PEDALS) ---
        is_accelerator = (left_open_count == 5)
        is_reverse = (left_f['index'] and left_f['pinky'] and not (left_f['thumb'] or left_f['middle'] or left_f['ring']))

        # --- STEP 2: DECODE RIGHT HAND (STEERING) ---
        # Left Turn: Only thumb open
        is_steer_left = (right_f['thumb'] and not (right_f['index'] or right_f['middle'] or right_f['ring'] or right_f['pinky']))
        # Right Turn: Only pinky open
        is_steer_right = (right_f['pinky'] and not (right_f['thumb'] or right_f['index'] or right_f['middle'] or right_f['ring']))
        # Straight: All fingers closed (fist)
        is_steer_straight = (right_open_count == 0)

        # --- STEP 3: PAIR GESTURES TO GENERATE COMMANDS ---
        if is_accelerator:
            if is_steer_straight:
                return "FORWARD"
            elif is_steer_left:
                return "FORWARD LEFT"
            elif is_steer_right:
                return "FORWARD RIGHT"

        if is_reverse:
            if is_steer_straight:
                return "REVERSE"
            elif is_steer_left:
                return "REVERSE LEFT"
            elif is_steer_right:
                return "REVERSE RIGHT"

        # If hands are up but don't match our specific combinations, halt the vehicle
        return "STOP"
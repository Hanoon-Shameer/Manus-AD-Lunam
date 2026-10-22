class GestureController:
    def __init__(self, debounce_threshold=2):
        self.last_stable_command = "S"
        self.pending_command = "S"
        self.frame_counter = 0
        self.debounce_threshold = debounce_threshold  # Must hold new gesture for 2 consecutive frames

    def is_finger_open(self, lm_list, tip_id, pip_id):
        """Returns True if the finger tip is higher up (smaller y) than the knuckle."""
        return lm_list[tip_id][1] < lm_list[pip_id][1]

    def get_active_fingers(self, lm_list):
        """Maps out exactly which fingers are open."""
        fingers = {
            'index': self.is_finger_open(lm_list, 8, 6),
            'middle': self.is_finger_open(lm_list, 12, 10),
            'ring': self.is_finger_open(lm_list, 16, 14),
            'pinky': self.is_finger_open(lm_list, 20, 18)
        }
        
        # Improved Thumb check: Distance between Thumb Tip (4) and Index MCP Knuckle (5)
        # Compare against distance between Index MCP (5) and Wrist (0)
        thumb_tip_to_index = abs(lm_list[4][0] - lm_list[5][0])
        wrist_to_index = abs(lm_list[5][1] - lm_list[0][1])
        fingers['thumb'] = thumb_tip_to_index > (wrist_to_index * 0.35)
        
        return fingers

    def evaluate_raw_command(self, hands_data):
        """Evaluates raw gesture data from MediaPipe landmarks."""
        detected_hands = list(hands_data.values())
        
        # Safety fallback if no hands in frame
        if len(detected_hands) == 0:
            return "S"

        # If 1 hand is present (Single hand mode: Left hand = Pedals)
        if len(detected_hands) == 1:
            left_f = self.get_active_fingers(detected_hands[0])
            open_count = sum(left_f.values())
            
            # Open palm = Forward
            if open_count >= 4:
                return "F"
            # Fist = Stop
            elif open_count <= 1:
                return "S"
            # Index + Pinky = Reverse
            elif left_f['index'] and left_f['pinky'] and not left_f['middle']:
                return "B"
            return "S"

        # Dual Hand Mode (Hand 0 = Left / Pedals, Hand 1 = Right / Steering)
        sorted_hands = sorted(hands_data.values(), key=lambda h: h[0][0])
        left_f = self.get_active_fingers(sorted_hands[0])
        right_f = self.get_active_fingers(sorted_hands[1])

        left_open_count = sum(left_f.values())
        right_open_count = sum(right_f.values())

        # Step 1: Decode Left Hand (Pedals)
        is_accelerator = (left_open_count >= 4)
        is_reverse = (left_f['index'] and left_f['pinky'] and not left_f['middle'])

        # Step 2: Decode Right Hand (Steering)
        is_steer_left = right_f['thumb'] and not right_f['pinky']
        is_steer_right = right_f['pinky'] and not right_f['thumb']
        is_steer_straight = (right_open_count <= 1) or (not is_steer_left and not is_steer_right)

        # Step 3: Combine Commands
        if is_accelerator:
            if is_steer_left:
                return "FL"
            elif is_steer_right:
                return "FR"
            else:
                return "F"
        elif is_reverse:
            if is_steer_left:
                return "BL"
            elif is_steer_right:
                return "BR"
            else:
                return "B"

        return "S"

    def get_command(self, hands_data):
        """Debounces commands to eliminate single-frame flickering."""
        raw_cmd = self.evaluate_raw_command(hands_data)

        if raw_cmd == self.pending_command:
            self.frame_counter += 1
            if self.frame_counter >= self.debounce_threshold:
                self.last_stable_command = raw_cmd
        else:
            self.pending_command = raw_cmd
            self.frame_counter = 0

        return self.last_stable_command
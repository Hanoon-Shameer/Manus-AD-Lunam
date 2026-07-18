import cv2
import camera_stream
from gesture_controller import GestureController

def main():
    # Grab our pre-configured camera and detector from the other file
    cap, detector = camera_stream.initialize_system()
    controller = GestureController()    
    
    print("M.A.L. Rover Gesture System Active.")
    
    while True:
        # Get the processed frame using our camera tool
        success, frame = camera_stream.process_frame(cap, detector)
        if not success:
            break
            
        # Get hand positions and translate to commands
        hands_data = detector.get_hand_info(frame)
        command = controller.get_command(hands_data)
        
        # Display the command on screen
        cv2.putText(frame, f"Command: {command}", (10, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.imshow("M.A.L. Rover Hand Tracking Test", frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
import cv2
import camera_stream
from gesture_controller import GestureController
from serial_sender import SerialSender

def main():
    # Setup camera stream and hand detection pipeline
    cap, detector = camera_stream.initialize_system()
    controller = GestureController()    
    
    # Initialize the automated serial connection manager
    sender = SerialSender()
    is_connected = sender.connect()
    
    print("M.A.L. Rover Gesture System Active.")
    
    while True:
        success, frame = camera_stream.process_frame(cap, detector)
        if not success:
            break
            
        # Extract landmark lists and evaluate gesture mapping
        hands_data = detector.get_hand_info(frame)
        command = controller.get_command(hands_data)

        # ADD THIS DIAGNOSTIC LINE HERE:
        print(f"Tracking Status -> Gestures evaluated to payload: '{command}'")
        
        # Fire off code over serial if pipeline is up
        if is_connected:
            sender.send_command(command)
        
        # UI overlays for the diagnostic display window
        cv2.putText(frame, f"TX Payload: {command}", (10, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.imshow("M.A.L. Rover Hand Tracking Test", frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    # Cleanup pipelines and drop the hardware connection port gracefully
    sender.close()
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
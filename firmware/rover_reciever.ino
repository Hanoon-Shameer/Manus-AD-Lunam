/*
 * Project: MANUS AD LUNAM - Motor Control Receiver 
 * Board: ESP32 Dev Module
 * Driver: L298N Dual H-Bridge Motor Driver
 */

// --- MOTOR A (LEFT MOTOR) PINS ---
const int IN1 = 12;
const int IN2 = 13;

// --- MOTOR B (RIGHT MOTOR) PINS ---
const int IN3 = 14;
const int IN4 = 27;

void setup() {
  // Initialize High-Speed Hardware Serial Connection
  Serial.begin(115200);

  // Configure Motor Output GPIOs
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  // Default to stop state on boot
  stopMotors();
}

void loop() {
  // Process Incoming Serial Telemetry Packets
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim(); // Clean extra whitespace / newline characters

    if (command.length() > 0) {
      executeCommand(command);
    }
  }
}

void executeCommand(String cmd) {
  if (cmd == "F") {
    // Forward (Both motors forward)
    setLeftMotor(true, false);
    setRightMotor(true, false);
  } 
  else if (cmd == "B") {
    // Reverse (Both motors reverse)
    setLeftMotor(false, true);
    setRightMotor(false, true);
  } 
  else if (cmd == "L") {
    // Pivot Left (Left motor back, Right motor forward)
    setLeftMotor(false, true);
    setRightMotor(true, false);
  } 
  else if (cmd == "R") {
    // Pivot Right (Left motor forward, Right motor back)
    setLeftMotor(true, false);
    setRightMotor(false, true);
  } 
  else if (cmd == "FL") {
    // Forward-Left Soft Arc (Right motor drives, Left motor stops)
    setLeftMotor(false, false);
    setRightMotor(true, false);
  } 
  else if (cmd == "FR") {
    // Forward-Right Soft Arc (Left motor drives, Right motor stops)
    setLeftMotor(true, false);
    setRightMotor(false, false);
  } 
  else if (cmd == "BL") {
    // Reverse-Left Soft Arc (Right motor reverses, Left motor stops)
    setLeftMotor(false, false);
    setRightMotor(false, true);
  } 
  else if (cmd == "BR") {
    // Reverse-Right Soft Arc (Left motor reverses, Right motor stops)
    setLeftMotor(false, true);
    setRightMotor(false, false);
  } 
  else if (cmd == "S") {
    // Emergency Brake / Stop
    stopMotors();
  }
}

void setLeftMotor(bool fwd, bool rev) {
  digitalWrite(IN1, fwd ? HIGH : LOW);
  digitalWrite(IN2, rev ? HIGH : LOW);
}

void setRightMotor(bool fwd, bool rev) {
  digitalWrite(IN3, fwd ? HIGH : LOW);
  digitalWrite(IN4, rev ? HIGH : LOW);
}

void stopMotors() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

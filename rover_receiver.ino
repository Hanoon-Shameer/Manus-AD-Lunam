// --- VIRTUAL ROVER CONTROL CODE ---

// We assign digital pins on the ESP32 chip to control the motors
const int leftMotorForward = 12;   // Pin to move left wheel forward
const int leftMotorBackward = 13;  // Pin to move left wheel backward
const int rightMotorForward = 25;  // Pin to move right wheel forward
const int rightMotorBackward = 26; // Pin to move right wheel backward

void setup() {
  // Start the serial communication so Abhay's Python code can talk to us
  Serial.begin(115200);
  Serial.println("Manus-Ad-Lunam Rover is Online!");

  // Tell the ESP32 that these pins will send electrical signals OUT to motors
  pinMode(leftMotorForward, OUTPUT);
  pinMode(leftMotorBackward, OUTPUT);
  pinMode(rightMotorForward, OUTPUT);
  pinMode(rightMotorBackward, OUTPUT);
  
  stopRover(); // Start in a safe, stopped position
}

void loop() {
  // Check if Abhay's Python script just sent a command text over the wire
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n'); // Read the command line
    command.trim(); // Clean up any invisible spaces
    
    // Print what we received to the test screen
    Serial.print("Received Command: ");
    Serial.println(command);
    
    // Deciding what to do based on what Abhay's code sent
    if (command == "FORWARD") {
      moveForward();
    } else if (command == "BACKWARD") {
      moveBackward();
    } else if (command == "LEFT") {
      turnLeft();
    } else if (command == "RIGHT") {
      turnRight();
    } else if (command == "STOP") {
      stopRover();
    }
  }
}

// --- HOW THE WHEELS SPIN ---
void moveForward() {
  digitalWrite(leftMotorForward, HIGH);   // Turn on left forward
  digitalWrite(leftMotorBackward, LOW);
  digitalWrite(rightMotorForward, HIGH);  // Turn on right forward
  digitalWrite(rightMotorBackward, LOW);
}

void moveBackward() {
  digitalWrite(leftMotorForward, LOW);
  digitalWrite(leftMotorBackward, HIGH);  // Turn on left backward
  digitalWrite(rightMotorForward, LOW);
  digitalWrite(rightMotorBackward, HIGH); // Turn on right backward
}

void turnLeft() {
  digitalWrite(leftMotorForward, LOW);
  digitalWrite(leftMotorBackward, HIGH);
  digitalWrite(rightMotorForward, HIGH);
  digitalWrite(rightMotorBackward, LOW);
}

void turnRight() {
  digitalWrite(leftMotorForward, HIGH);
  digitalWrite(leftMotorBackward, LOW);
  digitalWrite(rightMotorForward, LOW);
  digitalWrite(rightMotorBackward, HIGH);
}

void stopRover() {
  digitalWrite(leftMotorForward, LOW);
  digitalWrite(leftMotorBackward, LOW);
  digitalWrite(rightMotorForward, LOW);
  digitalWrite(rightMotorBackward, LOW);
}
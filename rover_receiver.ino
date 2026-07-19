// --- VIRTUAL ROVER CONTROL CODE ---

const int leftMotorForward = 12;   // Pin to move left wheel forward[cite: 1]
const int leftMotorBackward = 13;  // Pin to move left wheel backward[cite: 1]
const int rightMotorForward = 25;  // Pin to move right wheel forward[cite: 1]
const int rightMotorBackward = 26; // Pin to move right wheel backward[cite: 1]

void setup() {
  Serial.begin(115200); //[cite: 1]
  Serial.println("Manus-Ad-Lunam Rover is Online!"); //[cite: 1]

  pinMode(leftMotorForward, OUTPUT); //[cite: 1]
  pinMode(leftMotorBackward, OUTPUT); //[cite: 1]
  pinMode(rightMotorForward, OUTPUT); //[cite: 1]
  pinMode(rightMotorBackward, OUTPUT); //[cite: 1]
  
  stopRover(); // Start in a safe, stopped position[cite: 1]
}

void loop() {
  if (Serial.available() > 0) { //[cite: 1]
    String command = Serial.readStringUntil('\n'); //[cite: 1]
    command.trim(); //[cite: 1]
    
    Serial.print("Received Command: "); //[cite: 1]
    Serial.println(command); //[cite: 1]
    
    // Deciding what to do based on Abhay's new token layout
    if (command == "F") {
      moveForward();
    } else if (command == "FL") {
      moveForwardLeft();
    } else if (command == "FR") {
      moveForwardRight();
    } else if (command == "B") {
      moveBackward();
    } else if (command == "BL") {
      moveBackwardLeft();
    } else if (command == "BR") {
      moveBackwardRight();
    } else if (command == "S") {
      stopRover();
    }
  }
}

// --- HOW THE WHEELS SPIN ---
void moveForward() { //[cite: 1]
  digitalWrite(leftMotorForward, HIGH);   //[cite: 1]
  digitalWrite(leftMotorBackward, LOW); //[cite: 1]
  digitalWrite(rightMotorForward, HIGH);  //[cite: 1]
  digitalWrite(rightMotorBackward, LOW); //[cite: 1]
} //[cite: 1]

void moveBackward() { //[cite: 1]
  digitalWrite(leftMotorForward, LOW); //[cite: 1]
  digitalWrite(leftMotorBackward, HIGH);  //[cite: 1]
  digitalWrite(rightMotorForward, LOW); //[cite: 1]
  digitalWrite(rightMotorBackward, HIGH); //[cite: 1]
} //[cite: 1]

void moveForwardLeft() {
  digitalWrite(leftMotorForward, LOW);    // Left side stops
  digitalWrite(leftMotorBackward, LOW);
  digitalWrite(rightMotorForward, HIGH);  // Right side drives forward
  digitalWrite(rightMotorBackward, LOW);
}

void moveForwardRight() {
  digitalWrite(leftMotorForward, HIGH);   // Left side drives forward
  digitalWrite(leftMotorBackward, LOW);
  digitalWrite(rightMotorForward, LOW);   // Right side stops
  digitalWrite(rightMotorBackward, LOW);
}

void moveBackwardLeft() {
  digitalWrite(leftMotorForward, LOW);    // Left side stops
  digitalWrite(leftMotorBackward, LOW);
  digitalWrite(rightMotorForward, LOW);
  digitalWrite(rightMotorBackward, HIGH); // Right side drives backward
}

void moveBackwardRight() {
  digitalWrite(leftMotorForward, LOW);
  digitalWrite(leftMotorBackward, HIGH);  // Left side drives backward
  digitalWrite(rightMotorForward, LOW);    // Right side stops
  digitalWrite(rightMotorBackward, LOW);
}

void stopRover() { //[cite: 1]
  digitalWrite(leftMotorForward, LOW); //[cite: 1]
  digitalWrite(leftMotorBackward, LOW); //[cite: 1]
  digitalWrite(rightMotorForward, LOW); //[cite: 1]
  digitalWrite(rightMotorBackward, LOW); //[cite: 1]
} //[cite: 1]
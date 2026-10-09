#include <esp_now.h>
#include <WiFi.h>
#include <ESP32Servo.h>
#include <esp_arduino_version.h>

// --- L298N MOTOR PINS ---
#define IN1 12
#define IN2 13
#define IN3 14
#define IN4 27

// --- SENSOR & SERVO PINS ---
#define TRIG_PIN  5    // ESP32 Direct Output to HC-SR04 Trig
#define ECHO_PIN  18   // ESP32 Input from Level Shifter (LV1)
#define SERVO_PIN 19   // ESP32 PWM Control to Servo Signal

// Hardware Objects
Servo radarServo;

// Telemetry & Radar Variables
long duration;
int distance;
int servoAngle = 90;
int sweepDirection = 5; // Sweeps back and forth in steps of 5 degrees
unsigned long lastRadarScan = 0;

typedef struct GestureMessage {
  char command[4];
} GestureMessage;

GestureMessage incomingData;

// --- MOTOR DIRECTION LOGIC ---
void moveForward()    { digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);  }
void moveBackward()   { digitalWrite(IN1, LOW);  digitalWrite(IN2, HIGH); digitalWrite(IN3, LOW);  digitalWrite(IN4, HIGH); }

// Swapped steering polarity (FL/L = Left, FR/R = Right)
void turnLeft()       { digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);  digitalWrite(IN3, LOW);  digitalWrite(IN4, HIGH); }
void turnRight()      { digitalWrite(IN1, LOW);  digitalWrite(IN2, HIGH); digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);  }

void stopMotors()     { digitalWrite(IN1, LOW);  digitalWrite(IN2, LOW);  digitalWrite(IN3, LOW);  digitalWrite(IN4, LOW);  }

// --- ULTRASONIC DISTANCE SENSING ---
int getDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  // Read pulse through Level Shifter (timeout at 25000us ~400cm max)
  duration = pulseIn(ECHO_PIN, HIGH, 25000); 
  if (duration == 0) return 400; // Out of range or no echo
  
  return duration * 0.0343 / 2; // Convert echo travel time to centimeters
}

// --- NON-BLOCKING RADAR SWEEP ---
void updateRadar() {
  if (millis() - lastRadarScan >= 50) { // Scan every 50ms
    lastRadarScan = millis();

    radarServo.write(servoAngle);
    distance = getDistance();

    // Print radar readings to Serial Monitor for visual debugging
    Serial.printf("[RADAR] Angle: %d deg | Distance: %d cm\n", servoAngle, distance);

    // Update sweep bounds (30 to 150 degrees)
    servoAngle += sweepDirection;
    if (servoAngle <= 30 || servoAngle >= 150) {
      sweepDirection = -sweepDirection; // Reverse direction
    }
  }
}

// --- ESP-NOW RECEIVE CALLBACK ---
#if ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 0)
void OnDataRecv(const esp_now_recv_info *info, const uint8_t *incomingDataBytes, int len) {
#else
void OnDataRecv(const uint8_t *mac, const uint8_t *incomingDataBytes, int len) {
#endif
  memcpy(&incomingData, incomingDataBytes, sizeof(incomingData));
  String cmd = String(incomingData.command);

  Serial.printf("Receiver got command: %s\n", cmd.c_str());

  if (cmd == "F") moveForward();
  else if (cmd == "B") moveBackward();
  else if (cmd == "L" || cmd == "FL" || cmd == "BL") turnLeft();
  else if (cmd == "R" || cmd == "FR" || cmd == "BR") turnRight();
  else stopMotors();
}

void setup() {
  Serial.begin(115200);

  // Initialize Motor Pins
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  stopMotors();

  // Initialize Radar Pins & Servo
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  
  ESP32PWM::allocateTimer(0);
  radarServo.setPeriodHertz(50); // Standard 50Hz Servo Frequency
  radarServo.attach(SERVO_PIN, 500, 2400); // 500us - 2400us pulse bounds for SG90
  radarServo.write(90); // Center servo at start

  // Initialize ESP-NOW
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != ESP_OK) {
    Serial.println("Error initializing ESP-NOW on Receiver");
    return;
  }

  esp_now_register_recv_cb(OnDataRecv);
  Serial.println("Receiver ESP32 Ready with Radar Active!");
}

void loop() {
  // Continuously sweep servo & sample distance asynchronously
  updateRadar();
}

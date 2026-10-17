#include <esp_now.h>
#include <WiFi.h>
#include <ESP32Servo.h>
#include <esp_arduino_version.h>

// --- L298N MOTOR PINS ---
// OUT1 & OUT2 = Right Motors
// OUT3 & OUT4 = Left Motors
#define IN1 12 // Right Motors Control Pin A
#define IN2 13 // Right Motors Control Pin B
#define IN3 14 // Left Motors Control Pin A
#define IN4 27 // Left Motors Control Pin B

// --- HC-SR04 SENSOR & SG90 SERVO PINS ---
#define TRIG_PIN  5    // ESP32 Direct Output to HC-SR04 Trig
#define ECHO_PIN  18   // ESP32 Input from Level Shifter (LV1)
#define SERVO_PIN 19   // ESP32 PWM Control to SG90 Servo Signal

// Hardware Objects
Servo radarServo;

// Telemetry & Radar Variables
long duration;
int distance;
int servoAngle = 90;
int sweepDirection = 5; // Sweeps back and forth in steps of 5 degrees
unsigned long lastRadarScan = 0;

uint8_t transmitterAddress[6] = {0};
volatile bool transmitterAddressKnown = false;
bool telemetryPeerRegistered = false;

static const uint8_t RADAR_PACKET_MARKER = 0xA7;

typedef struct GestureMessage {
  char command[4];
} GestureMessage;

typedef struct __attribute__((packed)) RadarTelemetry {
  uint8_t marker;
  int16_t angleDeg;
  uint16_t distanceCm;
} RadarTelemetry;

GestureMessage incomingData;

// --- DIGITAL MOTOR DRIVE LOGIC ---
// Apply state directly to IN1, IN2 (Right Side) & IN3, IN4 (Left Side)
void applyMotorPower(int in1, int in2, int in3, int in4) {
  digitalWrite(IN1, in1 ? HIGH : LOW);
  digitalWrite(IN2, in2 ? HIGH : LOW);
  digitalWrite(IN3, in3 ? HIGH : LOW);
  digitalWrite(IN4, in4 ? HIGH : LOW);
}

// Fixed-speed 4WD tank movement mappings (Correction Applied):
// Forward & Backward swapped
void moveForward()      { applyMotorPower(0, 1, 0, 1); } // F (Both sides drive forward)
void moveBackward()     { applyMotorPower(1, 0, 1, 0); } // B (Both sides drive backward)

// Left & Right swapped + Full 4-wheel counter-rotation
void turnLeft()         { applyMotorPower(0, 1, 1, 0); } // L (Right forward, Left backward)
void turnRight()        { applyMotorPower(1, 0, 0, 1); } // R (Right backward, Left forward)

// Diagonal turns with active counter-rotation
void moveForwardLeft()  { applyMotorPower(0, 1, 1, 0); } // FL
void moveForwardRight() { applyMotorPower(1, 0, 0, 1); } // FR
void moveBackLeft()     { applyMotorPower(1, 0, 0, 1); } // BL
void moveBackRight()    { applyMotorPower(0, 1, 1, 0); } // BR

void stopMotors()       { applyMotorPower(0, 0, 0, 0); } // S

// --- HC-SR04 ULTRASONIC SENSOR READING ---
int getDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  duration = pulseIn(ECHO_PIN, HIGH, 25000); // 25ms timeout (~400cm max)
  if (duration == 0) return 400;             // Out of range

  return duration * 0.0343 / 2;             // Distance in cm
}

void registerTransmitterForTelemetry() {
  if (!transmitterAddressKnown || telemetryPeerRegistered) return;

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, transmitterAddress, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  const esp_err_t result = esp_now_add_peer(&peerInfo);
  if (result == ESP_OK || result == ESP_ERR_ESPNOW_EXIST) {
    telemetryPeerRegistered = true;
    Serial.println("Radar telemetry link established.");
  }
}

void sendRadarTelemetry(int angle, int distanceCm) {
  if (!telemetryPeerRegistered) return;

  RadarTelemetry packet;
  packet.marker = RADAR_PACKET_MARKER;
  packet.angleDeg = (int16_t)angle;
  packet.distanceCm = (uint16_t)distanceCm;

  esp_now_send(transmitterAddress, (const uint8_t *)&packet, sizeof(packet));
}

// --- SG90 RADAR SWEEP ---
void updateRadar() {
  if (millis() - lastRadarScan >= 50) { // Step every 50ms
    lastRadarScan = millis();

    radarServo.write(servoAngle);
    distance = getDistance();

    Serial.printf("[RADAR] Angle: %d deg | Distance: %d cm\n", servoAngle, distance);
    sendRadarTelemetry(servoAngle, distance);

    servoAngle += sweepDirection;
    if (servoAngle <= 30 || servoAngle >= 150) {
      sweepDirection = -sweepDirection; // Reverse direction
    }
  }
}

// --- ESP-NOW RECEIVE CALLBACK ---
#if ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 0)
void OnDataRecv(const esp_now_recv_info *info, const uint8_t *incomingDataBytes, int len) {
  const uint8_t *sourceMac = info ? info->src_addr : nullptr;
#else
void OnDataRecv(const uint8_t *mac, const uint8_t *incomingDataBytes, int len) {
  const uint8_t *sourceMac = mac;
#endif
  if (!incomingDataBytes || len < (int)sizeof(incomingData)) return;

  memcpy(&incomingData, incomingDataBytes, sizeof(incomingData));
  if (sourceMac) {
    memcpy(transmitterAddress, sourceMac, 6);
    transmitterAddressKnown = true;
  }

  String cmd = String(incomingData.command);
  Serial.printf("Receiver got command: %s\n", cmd.c_str());

  if (cmd == "F")        moveForward();
  else if (cmd == "FL")  moveForwardLeft();
  else if (cmd == "FR")  moveForwardRight();
  else if (cmd == "B")   moveBackward();
  else if (cmd == "BL")  moveBackLeft();
  else if (cmd == "BR")  moveBackRight();
  else if (cmd == "L")   turnLeft();
  else if (cmd == "R")   turnRight();
  else                   stopMotors(); // Handles "S" or unknown commands
}

void setup() {
  Serial.begin(115200);

  // Motor Pins
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  stopMotors();

  // Radar Pins
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // SG90 Servo Setup
  ESP32PWM::allocateTimer(0);
  radarServo.setPeriodHertz(50);
  radarServo.attach(SERVO_PIN, 500, 2400);
  radarServo.write(90);

  // ESP-NOW Setup
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
  registerTransmitterForTelemetry();
  updateRadar();
}

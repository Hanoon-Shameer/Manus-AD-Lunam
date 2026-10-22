#include <esp_now.h>
#include <WiFi.h>
#include <ESP32Servo.h>
#include <esp_arduino_version.h>

// --- L298N DIRECTION PINS ---
#define IN1 12 // Right Motors Dir A
#define IN2 13 // Right Motors Dir B
#define IN3 14 // Left Motors Dir A
#define IN4 27 // Left Motors Dir B

// --- L298N ENA / ENB PWM SPEED PINS ---
#define ENA_PIN 25 // Speed PWM Right Motors (Jumpers Removed)
#define ENB_PIN 26 // Speed PWM Left Motors (Jumpers Removed)

// --- SENSOR & SERVO PINS ---
#define TRIG_PIN  5    // Direct Output to HC-SR04 Trig
#define ECHO_PIN  18   // Input from Level Shifter (LV1)
#define SERVO_PIN 19   // PWM Control to SG90 Servo

Servo radarServo;

long duration;
int distance;
int servoAngle = 90;
int sweepDirection = 5; 
unsigned long lastRadarScan = 0;

uint8_t transmitterAddress[6] = {0};
volatile bool transmitterAddressKnown = false;
bool telemetryPeerRegistered = false;

static const uint8_t RADAR_PACKET_MARKER = 0xA7;

typedef struct GestureMessage {
  char command[4];
  uint8_t speed; // PWM duty cycle (0-255) sent from UI slider
} GestureMessage;

typedef struct __attribute__((packed)) RadarTelemetry {
  uint8_t marker;
  int16_t angleDeg;
  uint16_t distanceCm;
} RadarTelemetry;

GestureMessage incomingData;

// Drive direction pins HIGH/LOW and drive ENA/ENB with PWM speed
void setMotorSpeedAndDirection(int in1, int in2, int in3, int in4, uint8_t speed) {
  // Enforce a minimum speed floor (110 PWM) when non-zero to overcome L298N internal drop
  uint8_t effectiveSpeed = 0;
  if (speed > 0) {
    effectiveSpeed = (speed < 110) ? 110 : speed;
  }

  digitalWrite(IN1, in1 ? HIGH : LOW);
  digitalWrite(IN2, in2 ? HIGH : LOW);
  digitalWrite(IN3, in3 ? HIGH : LOW);
  digitalWrite(IN4, in4 ? HIGH : LOW);

  analogWrite(ENA_PIN, effectiveSpeed);
  analogWrite(ENB_PIN, effectiveSpeed);
}

// 4WD tank steering directional mappings
void moveForward(uint8_t spd)      { setMotorSpeedAndDirection(0, 1, 0, 1, spd); } 
void moveBackward(uint8_t spd)     { setMotorSpeedAndDirection(1, 0, 1, 0, spd); } 
void turnLeft(uint8_t spd)         { setMotorSpeedAndDirection(0, 1, 1, 0, spd); } 
void turnRight(uint8_t spd)        { setMotorSpeedAndDirection(1, 0, 0, 1, spd); } 
void moveForwardLeft(uint8_t spd)  { setMotorSpeedAndDirection(0, 1, 1, 0, spd); } 
void moveForwardRight(uint8_t spd) { setMotorSpeedAndDirection(1, 0, 0, 1, spd); } 
void moveBackLeft(uint8_t spd)     { setMotorSpeedAndDirection(1, 0, 0, 1, spd); } 
void moveBackRight(uint8_t spd)    { setMotorSpeedAndDirection(0, 1, 1, 0, spd); } 
void stopMotors()                  { setMotorSpeedAndDirection(0, 0, 0, 0, 0); } 

// --- ULTRASONIC SENSING ---
int getDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  duration = pulseIn(ECHO_PIN, HIGH, 25000); 
  if (duration == 0) return 400;             

  return duration * 0.0343 / 2;             
}

void registerTransmitterForTelemetry() {
  if (!transmitterAddressKnown || telemetryPeerRegistered) return;

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, transmitterAddress, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) == ESP_OK) {
    telemetryPeerRegistered = true;
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

// --- RADAR SWEEP ---
void updateRadar() {
  if (millis() - lastRadarScan >= 50) { 
    lastRadarScan = millis();

    radarServo.write(servoAngle);
    distance = getDistance();

    sendRadarTelemetry(servoAngle, distance);

    servoAngle += sweepDirection;
    if (servoAngle <= 30 || servoAngle >= 150) {
      sweepDirection = -sweepDirection; 
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
  uint8_t spd = incomingData.speed;

  if (cmd == "F")        moveForward(spd);
  else if (cmd == "FL")  moveForwardLeft(spd);
  else if (cmd == "FR")  moveForwardRight(spd);
  else if (cmd == "B")   moveBackward(spd);
  else if (cmd == "BL")  moveBackLeft(spd);
  else if (cmd == "BR")  moveBackRight(spd);
  else if (cmd == "L")   turnLeft(spd);
  else if (cmd == "R")   turnRight(spd);
  else                   stopMotors(); 
}

void setup() {
  Serial.begin(115200);

  // 1. ALLOCATE TIMER 3 & ATTACH SERVO FIRST (Before any analogWrite calls)
  ESP32PWM::allocateTimer(3);
  radarServo.setPeriodHertz(50);
  radarServo.attach(SERVO_PIN, 500, 2400);
  radarServo.write(90);

  // 2. Motor Pins & Initial State
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  pinMode(ENA_PIN, OUTPUT);
  pinMode(ENB_PIN, OUTPUT);
  stopMotors();

  // 3. Radar Sensor Pins
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // 4. ESP-NOW Setup
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != ESP_OK) return;

  esp_now_register_recv_cb(OnDataRecv);
  Serial.println("Receiver Ready!");
}

void loop() {
  registerTransmitterForTelemetry();
  updateRadar();
}
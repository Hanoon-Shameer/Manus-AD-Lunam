#include <esp_now.h>
#include <WiFi.h>
#include <esp_arduino_version.h>

// Set to 1 for readable Serial Monitor debug text; set to 0 for clean binary UI telemetry
#define DEBUG_SERIAL 1

// Rover (Receiver) ESP32 MAC address: 28:05:A5:32:DD:D0
uint8_t receiverAddress[] = {0x28, 0x05, 0xA5, 0x32, 0xDD, 0xD0};

static const uint8_t RADAR_PACKET_MARKER = 0xA7;

typedef struct GestureMessage {
  char command[4];
  uint8_t speed; // PWM duty cycle (0-255)
} GestureMessage;

typedef struct __attribute__((packed)) RadarTelemetry {
  uint8_t marker;
  int16_t angleDeg;
  uint16_t distanceCm;
} RadarTelemetry;

GestureMessage outgoingData;
RadarTelemetry incomingTelemetry;

volatile bool telemetryReady = false;
char serialLineBuffer[32];
size_t serialLineIndex = 0;

// --- ESP-NOW SEND CALLBACK ---
#if ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 0)
void OnDataSent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
#else
void OnDataSent(const uint8_t *mac_addr, esp_now_send_status_t status) {
#endif
#if DEBUG_SERIAL
  Serial.print("TX Status: ");
  Serial.println(status == ESP_NOW_SEND_SUCCESS ? "Delivered" : "Failed");
#endif
}

// --- ESP-NOW RECEIVE CALLBACK (RADAR TELEMETRY) ---
#if ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 0)
void OnDataRecv(const esp_now_recv_info *info, const uint8_t *incomingDataBytes, int len) {
#else
void OnDataRecv(const uint8_t *mac, const uint8_t *incomingDataBytes, int len) {
#endif
  if (!incomingDataBytes || len < (int)sizeof(RadarTelemetry)) return;

  RadarTelemetry temp;
  memcpy(&temp, incomingDataBytes, sizeof(RadarTelemetry));

  if (temp.marker == RADAR_PACKET_MARKER) {
    memcpy(&incomingTelemetry, &temp, sizeof(RadarTelemetry));
    telemetryReady = true;
  }
}

void sendCommand(const char *cmd, uint8_t spd) {
  memset(&outgoingData, 0, sizeof(outgoingData));
  strncpy(outgoingData.command, cmd, sizeof(outgoingData.command) - 1);
  outgoingData.speed = spd;

  esp_err_t result = esp_now_send(receiverAddress, (const uint8_t *)&outgoingData, sizeof(outgoingData));

#if DEBUG_SERIAL
  Serial.print("Sent CMD=");
  Serial.print(outgoingData.command);
  Serial.print(" SPD=");
  Serial.print(outgoingData.speed);
  Serial.print(" | esp_now_send=");
  Serial.println(result == ESP_OK ? "OK" : "ERR");
#endif
}

// Parses lines like "F,180" or "STOP,0" or "F" from Serial
void handleSerialLine(char *line) {
  while (*line == ' ' || *line == '\t' || *line == '\r' || *line == '\n') line++;
  if (*line == '\0') return;

  char *comma = strchr(line, ',');
  uint8_t speed = 180;

  if (comma != nullptr) {
    *comma = '\0';
    int parsedSpeed = atoi(comma + 1);
    if (parsedSpeed < 0) parsedSpeed = 0;
    if (parsedSpeed > 255) parsedSpeed = 255;
    speed = (uint8_t)parsedSpeed;
  }

  for (char *p = line; *p; ++p) {
    *p = toupper((unsigned char)*p);
  }

  sendCommand(line, speed);
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialLineIndex > 0) {
        serialLineBuffer[serialLineIndex] = '\0';
        handleSerialLine(serialLineBuffer);
        serialLineIndex = 0;
      }
    } else if (serialLineIndex < sizeof(serialLineBuffer) - 1) {
      serialLineBuffer[serialLineIndex++] = c;
    }
  }
}

void forwardTelemetryToSerial() {
  if (!telemetryReady) return;

  noInterrupts();
  RadarTelemetry pkt = incomingTelemetry;
  telemetryReady = false;
  interrupts();

#if DEBUG_SERIAL
  Serial.print("RADAR -> Angle: ");
  Serial.print(pkt.angleDeg);
  Serial.print(" deg | Dist: ");
  Serial.print(pkt.distanceCm);
  Serial.println(" cm");
#else
  Serial.write((const uint8_t *)&pkt, sizeof(pkt));
#endif
}

void setup() {
  Serial.begin(115200);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW Init Failed");
    return;
  }

  esp_now_register_send_cb(OnDataSent);
  esp_now_register_recv_cb(OnDataRecv);

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, receiverAddress, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("Failed to add receiver peer");
    return;
  }

  Serial.println("Transmitter Ready!");
}

void loop() {
  readSerialCommands();
  forwardTelemetryToSerial();
}
#include <esp_now.h>
#include <WiFi.h>
#include <esp_arduino_version.h>

// Receiver MAC Address
uint8_t receiverAddress[] = {0x1C, 0xC3, 0xAB, 0xB3, 0xC6, 0x48};

// --- COMMAND & TELEMETRY STRUCTS ---
typedef struct GestureMessage {
  char command[4]; // Movement command ("F", "FL", "S", etc.)
  uint8_t speed;   // Speed value from UI slider (0 - 255)
} GestureMessage;

static const uint8_t RADAR_PACKET_MARKER = 0xA7;

typedef struct __attribute__((packed)) RadarTelemetry {
  uint8_t marker;
  int16_t angleDeg;
  uint16_t distanceCm;
} RadarTelemetry;

GestureMessage outgoingData;
esp_now_peer_info_t peerInfo;

#if ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 0)
void OnDataSent(const wifi_tx_info_t *tx_info, esp_now_send_status_t status) {}
void OnDataRecv(const esp_now_recv_info *info, const uint8_t *incomingDataBytes, int len) {
#else
void OnDataSent(const uint8_t *mac_addr, esp_now_send_status_t status) {}
void OnDataRecv(const uint8_t *mac, const uint8_t *incomingDataBytes, int len) {
#endif
  if (!incomingDataBytes || len != (int)sizeof(RadarTelemetry)) return;

  RadarTelemetry telemetry;
  memcpy(&telemetry, incomingDataBytes, sizeof(telemetry));
  if (telemetry.marker != RADAR_PACKET_MARKER) return;

  // Print radar telemetry for Python UI
  Serial.printf("RADAR:%d:%u\n", (int)telemetry.angleDeg, (unsigned int)telemetry.distanceCm);
}

void setup() {
  Serial.begin(115200);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != ESP_OK) {
    Serial.println("Error initializing ESP-NOW on Transmitter");
    return;
  }

  esp_now_register_send_cb(OnDataSent);
  esp_now_register_recv_cb(OnDataRecv);

  memcpy(peerInfo.peer_addr, receiverAddress, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("Failed to add Receiver peer");
    return;
  }

  Serial.println("Transmitter Ready!");
}

void loop() {
  // Parses "COMMAND:SPEED" sent by Python UI (e.g. "F:148")
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();

    int colonIndex = input.indexOf(':');
    if (colonIndex != -1) {
      String cmd = input.substring(0, colonIndex);
      int spd = input.substring(colonIndex + 1).toInt();

      cmd.toCharArray(outgoingData.command, sizeof(outgoingData.command));
      outgoingData.speed = (uint8_t)constrain(spd, 0, 255);

      esp_now_send(receiverAddress, (uint8_t *)&outgoingData, sizeof(outgoingData));
    }
  }
}
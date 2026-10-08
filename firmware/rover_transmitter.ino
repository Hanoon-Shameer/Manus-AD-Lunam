#include <esp_now.h>
#include <WiFi.h>
#include <esp_arduino_version.h>

// --- TARGET ROVER MAC ADDRESS ---
uint8_t roverMacAddress[] = {0x1C, 0xC3, 0xAB, 0xB3, 0xC6, 0x48};

// Command payload structure supporting multi-char commands (e.g. "FL", "FR")
typedef struct GestureMessage {
  char command[4];
} GestureMessage;

GestureMessage gestureData;
esp_now_peer_info_t peerInfo;

// Cross-version callback compatibility
#if ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 0)
void OnDataSent(const wifi_tx_info_t *tx_info, esp_now_send_status_t status) {
}
#else
void OnDataSent(const uint8_t *mac_addr, esp_now_send_status_t status) {
}
#endif

void setup() {
  Serial.begin(115200);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != ESP_OK) {
    Serial.println("Error initializing ESP-NOW on Transmitter");
    return;
  }

  esp_now_register_send_cb(OnDataSent);

  memcpy(peerInfo.peer_addr, roverMacAddress, 6);
  peerInfo.channel = 0;  
  peerInfo.encrypt = false;
  
  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("Failed to add Rover peer");
    return;
  }

  Serial.println("Transmitter Ready! Awaiting Commands from Python...");
}

void loop() {
  if (Serial.available() > 0) {
    String incomingStr = Serial.readStringUntil('\n');
    incomingStr.trim(); // Remove whitespace and trailing newlines

    if (incomingStr.length() > 0) {
      memset(gestureData.command, 0, sizeof(gestureData.command));
      incomingStr.toCharArray(gestureData.command, sizeof(gestureData.command));

      esp_err_t result = esp_now_send(roverMacAddress, (uint8_t *) &gestureData, sizeof(gestureData));
      
      if (result == ESP_OK) {
        Serial.printf("Sent command '%s' to Rover!\n", gestureData.command);
      } else {
        Serial.println("Error sending ESP-NOW packet");
      }
    }
  }
}
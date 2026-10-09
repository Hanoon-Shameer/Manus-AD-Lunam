#include <esp_now.h>
#include <WiFi.h>
#include <esp_arduino_version.h>

// --- PIN DEFINITION ---
#define POT_PIN 34 // Pin labeled 'VP' on your 30-pin board

// Receiver MAC Address
uint8_t receiverAddress[] = {0x1C, 0xC3, 0xAB, 0xB3, 0xC6, 0x48};

// --- TELEMETRY STRUCT ---
typedef struct GestureMessage {
  char command[4];  // Movement command (e.g., "F", "BL", "S")
  uint8_t speed;    // Motor speed (100 - 255 PWM)
} GestureMessage;

GestureMessage outgoingData;
esp_now_peer_info_t peerInfo;

// --- ESP-NOW SEND CALLBACK (ESP32 CORE 3.X COMPATIBLE) ---
#if ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 0)
void OnDataSent(const wifi_tx_info_t *tx_info, esp_now_send_status_t status) {
#else
void OnDataSent(const uint8_t *mac_addr, esp_now_send_status_t status) {
#endif
  // Status check if needed: status == ESP_NOW_SEND_SUCCESS
}

void setup() {
  Serial.begin(115200);
  pinMode(POT_PIN, INPUT);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != ESP_OK) {
    Serial.println("Error initializing ESP-NOW on Transmitter");
    return;
  }

  esp_now_register_send_cb(OnDataSent);

  // Register peer (Receiver)
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
  // 1. Read Potentiometer on 'VP' (GPIO 34) and map to PWM Speed Range (100-255)
  int rawPot = analogRead(POT_PIN);
  outgoingData.speed = map(rawPot, 0, 4095, 100, 255);

  // --- DEBUG PRINT: Shows reading in Serial Monitor continuously ---
  Serial.printf("Raw ADC (VP): %d | Speed: %d\n", rawPot, outgoingData.speed);
  delay(150);

  // 2. Process incoming Serial command from Python
  if (Serial.available() > 0) {
    String inputCommand = Serial.readStringUntil('\n');
    inputCommand.trim();

    if (inputCommand.length() > 0 && inputCommand.length() < 4) {
      inputCommand.toCharArray(outgoingData.command, sizeof(outgoingData.command));

      // Send structured payload via ESP-NOW
      esp_err_t result = esp_now_send(receiverAddress, (uint8_t *) &outgoingData, sizeof(outgoingData));
      
      if (result == ESP_OK) {
        Serial.printf("[TX] Sent: %s | Speed: %d\n", outgoingData.command, outgoingData.speed);
      }
    }
  }
}

#include <esp_now.h>
#include <WiFi.h>
#include <esp_arduino_version.h>

// --- L298N MOTOR PINS ---
#define IN1 12
#define IN2 13
#define IN3 14
#define IN4 27

typedef struct GestureMessage {
  char command[4];
} GestureMessage;

GestureMessage incomingData;

// --- MOTOR DIRECTION LOGIC ---
void moveForward()    { digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);  }
void moveBackward()   { digitalWrite(IN1, LOW);  digitalWrite(IN2, HIGH); digitalWrite(IN3, LOW);  digitalWrite(IN4, HIGH); }

// Swapped steering polarity so FL/L turns Left and FR/R turns Right
void turnLeft()       { digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);  digitalWrite(IN3, LOW);  digitalWrite(IN4, HIGH); }
void turnRight()      { digitalWrite(IN1, LOW);  digitalWrite(IN2, HIGH); digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);  }

void stopMotors()     { digitalWrite(IN1, LOW);  digitalWrite(IN2, LOW);  digitalWrite(IN3, LOW);  digitalWrite(IN4, LOW);  }

// Cross-version callback compatibility
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

  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  stopMotors();

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != ESP_OK) {
    Serial.println("Error initializing ESP-NOW on Receiver");
    return;
  }

  esp_now_register_recv_cb(OnDataRecv);
  Serial.println("Receiver ESP32 Ready and Listening!");
}

void loop() {
  // Asynchronous ESP-NOW execution
}
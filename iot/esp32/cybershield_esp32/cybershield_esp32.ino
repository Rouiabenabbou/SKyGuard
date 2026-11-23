/*
 * CyberShield SatCom 3D - ESP32 + DHT22 field device (Phase 11)
 *
 * What it does
 *  - connects to Wi-Fi and to the Mosquitto broker on your computer
 *  - every 5 s reads the DHT22 and publishes
 *        cybershield/iot/ESP32-001/telemetry
 *        {"device_id":"ESP32-001","temperature":24.3,"humidity":51.0,"battery":100,"source":"esp32"}
 *  - publishes "online" on cybershield/iot/ESP32-001/status, and registers a
 *    "last will" so the broker announces "offline" if the board loses power
 *  - listens on cybershield/iot/ESP32-001/command:
 *        {"action":"quarantine"}  stop sending readings, LED blinks fast
 *        {"action":"release"}     resume normal operation
 *        {"action":"identify"}    blink the LED 10 times
 *        {"action":"ping"}        answer with "online" on the status topic
 *
 * Libraries (Arduino IDE -> Tools -> Manage Libraries):
 *  - PubSubClient by Nick O'Leary
 *  - DHT sensor library by Adafruit (also installs "Adafruit Unified Sensor")
 *  - ArduinoJson by Benoit Blanchon (version 7)
 * v2.2: USE_IOTDA 1 in config.h sends the readings to Huawei Cloud IoTDA instead
 *       ($oc/devices/<id>/sys/properties/report) and takes commands from IoTDA.
 *
 * Board: "ESP32 Dev Module" (Boards Manager: "esp32" by Espressif Systems)
 *
 * Wiring (DHT22 / AM2302):
 *    DHT22 VCC (+)  -> ESP32 3V3
 *    DHT22 DATA     -> ESP32 GPIO 4   (+ 10 kOhm resistor from DATA to 3V3 if
 *                                      your DHT22 is a bare sensor, not a module)
 *    DHT22 GND (-)  -> ESP32 GND
 */
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>
#include <time.h>
#include "mbedtls/md.h"
#include "config.h"

DHT dht(DHT_PIN, DHT_TYPE);  // DHT22 or DHT11, set in config.h
#if MQTT_USE_TLS || USE_IOTDA
WiFiClientSecure wifiClient;  // v1.1: encrypted MQTT, broker checked against our CA
#else
WiFiClient wifiClient;
#endif
PubSubClient mqtt(wifiClient);

// v1.1: PIR motion sensor. Any movement since the last reading is reported.
volatile bool motionSeen = false;
bool lastPir = false;

String topicTelemetry = String(TOPIC_PREFIX) + "/iot/" + DEVICE_ID + "/telemetry";
String topicStatus    = String(TOPIC_PREFIX) + "/iot/" + DEVICE_ID + "/status";
String topicCommand   = String(TOPIC_PREFIX) + "/iot/" + DEVICE_ID + "/command";
#if USE_IOTDA
String iotdaBase = String("$oc/devices/") + IOTDA_DEVICE_ID + "/sys/";
#endif

bool quarantined = false;          // set by the backend's quarantine command
unsigned long lastSend = 0;
unsigned long lastBlink = 0;
int identifyBlinks = 0;
unsigned long sentCount = 0;

// ---------------------------------------------------------------- helpers
void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.printf("[wifi] connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[wifi] connected, IP %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[wifi] FAILED - check WIFI_SSID / WIFI_PASSWORD (2.4 GHz only). Retrying...");
  }
}

float readBattery() {
  if (BATTERY_PIN < 0) return 100.0;  // USB powered
  // Example for a 1:2 voltage divider on a LiPo (4.2 V full, 3.3 V empty)
  float volts = analogReadMilliVolts(BATTERY_PIN) * 2 / 1000.0;
  float pct = (volts - 3.3) / (4.2 - 3.3) * 100.0;
  return constrain(pct, 0, 100);
}

void onCommand(char* topic, byte* payload, unsigned int length) {
  JsonDocument doc;
  if (deserializeJson(doc, payload, length)) {
    Serial.println("[cmd] ignored: not valid JSON");
    return;
  }
#if USE_IOTDA
  // IoTDA command: {"command_name":"quarantine","paras":{}} on .../sys/commands/request_id=<id>
  String action = doc["command_name"] | "";
  String t = String(topic);
  int rid = t.indexOf("request_id=");
  if (rid >= 0) {  // IoTDA waits for an answer
    String resp = iotdaBase + "commands/response/" + t.substring(rid);
    mqtt.publish(resp.c_str(), "{\"result_code\":0}");
  }
#else
  String action = doc["action"] | "";
#endif
  Serial.printf("[cmd] %s\n", action.c_str());
  if (action == "quarantine") {
    quarantined = true;
    Serial.println("[cmd] QUARANTINED by the CyberShield backend: readings stopped");
  } else if (action == "release") {
    quarantined = false;
    digitalWrite(LED_PIN, LOW);
    Serial.println("[cmd] released: back to normal");
  } else if (action == "identify") {
    identifyBlinks = 20;  // 10 on/off cycles
  } else if (action == "ping") {
#if !USE_IOTDA
    mqtt.publish(topicStatus.c_str(), "online", true);
#endif
  }
}

#if USE_IOTDA
// IoTDA login: client ID <device id>_0_0_<YYYYMMDDHH>, password = HMAC-SHA256(secret, key = that timestamp)
bool connectIotda() {
  time_t now = time(nullptr);
  struct tm utc;
  gmtime_r(&now, &utc);
  char ts[11];
  strftime(ts, sizeof(ts), "%Y%m%d%H", &utc);
  unsigned char mac[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char*)ts, strlen(ts));
  mbedtls_md_hmac_update(&ctx, (const unsigned char*)IOTDA_SECRET, strlen(IOTDA_SECRET));
  mbedtls_md_hmac_finish(&ctx, mac);
  mbedtls_md_free(&ctx);
  char password[65];
  for (int i = 0; i < 32; i++) sprintf(password + 2 * i, "%02x", mac[i]);
  String clientId = String(IOTDA_DEVICE_ID) + "_0_0_" + ts;
  Serial.printf("[iotda] connecting to %s as %s ... ", IOTDA_HOST, IOTDA_DEVICE_ID);
  return mqtt.connect(clientId.c_str(), IOTDA_DEVICE_ID, password);
}
#endif

void connectMqtt() {
  while (!mqtt.connected()) {
    connectWifi();
    if (WiFi.status() != WL_CONNECTED) { delay(2000); continue; }
#if USE_IOTDA
    if (connectIotda()) {
      Serial.println("connected");
      mqtt.subscribe((iotdaBase + "commands/#").c_str(), 1);
    } else {
      Serial.printf("failed (state %d: 4/5 = wrong device ID or secret, or clock not set), retry in 5 s\n", mqtt.state());
      delay(5000);
    }
    continue;
#endif
    Serial.printf("[mqtt] connecting to %s:%d as %s ... ", MQTT_HOST, MQTT_PORT, DEVICE_ID);
    String clientId = String("cybershield-") + DEVICE_ID;
    bool ok;
    // last will: the broker publishes "offline" for us if we disappear
    if (strlen(MQTT_USER) > 0) {
      ok = mqtt.connect(clientId.c_str(), MQTT_USER, MQTT_PASS, topicStatus.c_str(), 1, true, "offline");
    } else {
      ok = mqtt.connect(clientId.c_str(), topicStatus.c_str(), 1, true, "offline");
    }
    if (ok) {
      Serial.println("connected");
      mqtt.publish(topicStatus.c_str(), "online", true);
      mqtt.subscribe(topicCommand.c_str(), 1);
    } else {
      // -2 = cannot reach the broker: wrong MQTT_HOST, Mosquitto only on localhost, or firewall
      Serial.printf("failed (state %d), retry in 5 s\n", mqtt.state());
      delay(5000);
    }
  }
}

void sendReading() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (isnan(t) || isnan(h)) {
    Serial.println("[dht22] read failed - check wiring (DATA on GPIO 4, 3V3, GND)");
    return;  // never send garbage: the backend would reject it as malformed
  }
  JsonDocument doc;
#if USE_IOTDA
  // IoTDA property report; the backend gets it through the data forwarding rule
  JsonObject svc = doc["services"].add<JsonObject>();
  svc["service_id"] = IOTDA_SERVICE_ID;
  JsonObject props = svc["properties"].to<JsonObject>();
  props["temperature"] = roundf(t * 10) / 10.0;
  props["humidity"] = roundf(h * 10) / 10.0;
  props["battery"] = roundf(readBattery() * 10) / 10.0;
  if (PIR_PIN >= 0) {
    props["motion"] = motionSeen;
    motionSeen = false;
  }
  char buffer[256];
  size_t n = serializeJson(doc, buffer);
  String topicReport = iotdaBase + "properties/report";
  bool ok = mqtt.publish(topicReport.c_str(), (const uint8_t*)buffer, n, false);
#else
  doc["device_id"] = DEVICE_ID;
  doc["temperature"] = roundf(t * 10) / 10.0;
  doc["humidity"] = roundf(h * 10) / 10.0;
  doc["battery"] = roundf(readBattery() * 10) / 10.0;
  doc["source"] = "esp32";
  if (PIR_PIN >= 0) {
    doc["motion"] = motionSeen;  // true = movement since the last reading
    motionSeen = false;
  }
  char buffer[192];
  size_t n = serializeJson(doc, buffer);
  bool ok = mqtt.publish(topicTelemetry.c_str(), (const uint8_t*)buffer, n, false);
#endif
  sentCount++;
  Serial.printf("[send #%lu] %s %s\n", sentCount, buffer, ok ? "" : "(publish FAILED)");
  // short LED flash = a reading was sent
  digitalWrite(LED_PIN, HIGH);
  delay(30);
  digitalWrite(LED_PIN, LOW);
}

// ---------------------------------------------------------------- main
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n=== CyberShield SatCom 3D - ESP32 field device ===");
  pinMode(LED_PIN, OUTPUT);
  dht.begin();
  if (PIR_PIN >= 0) pinMode(PIR_PIN, INPUT);
#if USE_IOTDA
  connectWifi();
  configTime(0, 0, "pool.ntp.org", "time.google.com");  // the IoTDA password needs the current UTC hour
  Serial.print("[time] waiting for NTP");
  while (time(nullptr) < 1700000000) { delay(300); Serial.print("."); }
  Serial.println(" ok");
  if (strstr(IOTDA_CA_CERT, "paste") == nullptr) wifiClient.setCACert(IOTDA_CA_CERT);
  else wifiClient.setInsecure();  // lab test only: server certificate not checked
  mqtt.setBufferSize(512);
  mqtt.setServer(IOTDA_HOST, IOTDA_PORT);
#else
#if MQTT_USE_TLS
  if (strstr(MQTT_CA_CERT, "paste") == nullptr) wifiClient.setCACert(MQTT_CA_CERT);
  else wifiClient.setInsecure();  // v2.4, lab test only: server certificate not checked
#endif
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
#endif
  mqtt.setCallback(onCommand);
  mqtt.setKeepAlive(30);
  connectMqtt();
}

void loop() {
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();
  unsigned long now = millis();

  if (identifyBlinks > 0 && now - lastBlink > 150) {
    lastBlink = now;
    digitalWrite(LED_PIN, identifyBlinks % 2);
    identifyBlinks--;
  } else if (quarantined && identifyBlinks == 0 && now - lastBlink > 100) {
    lastBlink = now;  // fast blink = isolated
    digitalWrite(LED_PIN, !digitalRead(LED_PIN));
  }

  // PIR: send at once when movement starts, so a night intrusion is seen immediately.
  if (PIR_PIN >= 0) {
    bool pir = digitalRead(PIR_PIN) == HIGH;
    if (pir && !lastPir) {
      motionSeen = true;
      Serial.println("[pir] movement detected");
      if (!quarantined && now - lastSend > 1000) {
        lastSend = now;
        sendReading();
      }
    }
    lastPir = pir;
  }

  if (!quarantined && now - lastSend >= SEND_EVERY_MS) {
    lastSend = now;
    sendReading();
  }
}

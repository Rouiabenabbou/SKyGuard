// ============================================================================
//  CyberShield SatCom 3D - ESP32 settings
//  Change these 4 lines before uploading. Nothing else needs editing.
// ============================================================================
#pragma once

// Your Wi-Fi (2.4 GHz only: the ESP32 cannot use 5 GHz networks)
#define WIFI_SSID      "YOUR_WIFI_NAME"
#define WIFI_PASSWORD  "YOUR_WIFI_PASSWORD"

// IP address of the computer running Mosquitto (run `ipconfig` on Windows,
// look for "IPv4 Address", e.g. 192.168.1.23). NOT "localhost".
#define MQTT_HOST      "192.168.1.23"
#define MQTT_PORT      1883

// Must match ESP32_DEVICE_ID in the project's .env file
#define DEVICE_ID      "ESP32-001"

// ----------------------------------------------------------------------------
// Optional settings
// ----------------------------------------------------------------------------
// Secure broker (v1.1, docs/SECURE_MQTT.md): user = the device ID, password from
// iot/mosquitto/credentials.txt. Leave empty for the open lab broker.
#define MQTT_USER      ""
#define MQTT_PASS      ""
#define TOPIC_PREFIX   "cybershield"
#define DHT_PIN        4           // GPIO connected to the DHT data pin
#define DHT_TYPE       DHT22       // DHT22 or DHT11 (v2.5.1)
#define LED_PIN        2           // on-board LED of most ESP32 dev boards
#define SEND_EVERY_MS  5000        // one reading every 5 s, like the simulated devices
#define BATTERY_PIN    -1          // -1 = powered by USB (reports 100 %). Or an ADC pin with a divider

// ----------------------------------------------------------------------------
// v1.1 additions
// ----------------------------------------------------------------------------
// PIR motion sensor HC-SR501: OUT -> this GPIO, VCC -> 5V (VIN), GND -> GND.
// -1 = no motion sensor connected (an unconnected pin would give false alarms).
#define PIR_PIN        -1          // e.g. 27 when the HC-SR501 is wired

// Encrypted MQTT (TLS, port 8883). 1 = on: set MQTT_PORT to 8883 and paste the
// content of iot/mosquitto/certs/ca.crt between the R"( and )" below.
// v2.4 cloud broker (HiveMQ Cloud, EMQX Cloud): MQTT_HOST = the cluster URL,
// MQTT_PORT 8883, MQTT_USER/MQTT_PASS = the broker login, and paste the broker's
// root CA here (HiveMQ Cloud: "ISRG Root X1"). See docs/CLOUD_MQTT.md.
#define MQTT_USE_TLS   0
static const char MQTT_CA_CERT[] = R"(
-----BEGIN CERTIFICATE-----
paste iot/mosquitto/certs/ca.crt here
-----END CERTIFICATE-----
)";

// ----------------------------------------------------------------------------
// v2.2: Huawei Cloud IoTDA instead of the local Mosquitto broker
// ----------------------------------------------------------------------------
// 1 = connect to Huawei IoTDA (docs/HUAWEI_INNOVATION.md, step 2). MQTT_HOST /
// MQTT_PORT / MQTT_USER above are then not used.
#define USE_IOTDA          0
// IoTDA console -> Overview -> Access Details -> MQTTS address (port 8883)
#define IOTDA_HOST         "xxxxxxxxxx.st1.iotda-device.cn-north-4.myhuaweicloud.com"
#define IOTDA_PORT         8883
// IoTDA console -> Devices -> your device: "Device ID" (looks like <product id>_ESP32-001) and its secret
#define IOTDA_DEVICE_ID    "YOUR_PRODUCT_ID_ESP32-001"
#define IOTDA_SECRET       "YOUR_DEVICE_SECRET"
// Service ID of the product model (create a service "Sensor" with properties temperature, humidity, battery, motion)
#define IOTDA_SERVICE_ID   "Sensor"
// IoTDA console -> Overview -> Access Details -> download the device CA certificate and paste it below.
// Leave the placeholder to skip the server check (lab test only, not for a real deployment).
static const char IOTDA_CA_CERT[] = R"(
-----BEGIN CERTIFICATE-----
paste the IoTDA device CA certificate here
-----END CERTIFICATE-----
)";

"""
ESP32 emulator (Phase 11).

Behaves exactly like the real ESP32 firmware in iot/esp32/, so you can test
Phase 11 without hardware:
  * same topics, same JSON payload ("source": "esp32"), one reading every 5 s
  * "online" on the status topic, and an "offline" last will
  * obeys commands: quarantine (stops sending), release, identify, ping

Run (with the backend started with ESP32_ENABLED=true):
  python iot/simulator/esp32_emulator.py
  python iot/simulator/esp32_emulator.py --host 192.168.1.23 --device ESP32-001
Stop with Ctrl+C.
"""
import argparse
import json
import math
import random
import time

import paho.mqtt.client as mqtt


def main():
    parser = argparse.ArgumentParser(description="Emulate the CyberShield ESP32 + DHT22 board")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device", default="ESP32-001")
    parser.add_argument("--prefix", default="cybershield")
    parser.add_argument("--interval", type=float, default=5.0)
    # v1.1: secure MQTT and the PIR motion sensor
    parser.add_argument("--username", default=None, help="MQTT user (secure broker: the device ID)")
    parser.add_argument("--password", default=None, help="MQTT password of this device")
    parser.add_argument("--tls", action="store_true", help="encrypted connection (use --port 8883)")
    parser.add_argument("--cafile", default=None, help="CA certificate of the broker (iot/mosquitto/certs/ca.crt)")
    parser.add_argument("--motion", action="store_true", help="also emulate a PIR motion sensor (HC-SR501)")
    args = parser.parse_args()

    t_topic = f"{args.prefix}/iot/{args.device}/telemetry"
    s_topic = f"{args.prefix}/iot/{args.device}/status"
    c_topic = f"{args.prefix}/iot/{args.device}/command"
    state = {"quarantined": False, "sent": 0}

    def on_connect(client, userdata, flags, reason_code, properties):
        print(f"[mqtt] connected to {args.host}:{args.port} as {args.device}")
        client.publish(s_topic, "online", qos=1, retain=True)
        client.subscribe(c_topic, qos=1)

    def on_message(client, userdata, msg):
        try:
            action = json.loads(msg.payload).get("action", "")
        except (ValueError, AttributeError):
            print("[cmd] ignored: not valid JSON")
            return
        print(f"[cmd] {action}")
        if action == "quarantine":
            state["quarantined"] = True
            print("[cmd] QUARANTINED by the CyberShield backend: readings stopped (LED would blink fast)")
        elif action == "release":
            state["quarantined"] = False
            print("[cmd] released: back to normal")
        elif action == "identify":
            print("[cmd] identify: LED blinks 10 times *blink* *blink*")
        elif action == "ping":
            client.publish(s_topic, "online", qos=1, retain=True)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"cybershield-{args.device}")
    client.will_set(s_topic, "offline", qos=1, retain=True)
    if args.username:
        client.username_pw_set(args.username, args.password)
    if args.tls:
        import ssl
        client.tls_set(ca_certs=args.cafile, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()

    start = time.time()
    try:
        while True:
            time.sleep(args.interval)
            if state["quarantined"]:
                continue
            minutes = (time.time() - start) / 60
            reading = {
                "device_id": args.device,
                "temperature": round(24 + 1.5 * math.sin(minutes) + random.gauss(0, 0.2), 1),
                "humidity": round(50 + 4 * math.cos(minutes / 2) + random.gauss(0, 0.5), 1),
                "battery": 100.0,
                "source": "esp32",
            }
            if args.motion:  # PIR: someone walks past now and then
                reading["motion"] = random.random() < 0.15
            client.publish(t_topic, json.dumps(reading), qos=0)
            state["sent"] += 1
            print(f"[send #{state['sent']}] {reading}")
    except KeyboardInterrupt:
        print("\nstopping (clean disconnect: status offline)")
        client.publish(s_topic, "offline", qos=1, retain=True).wait_for_publish(2)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()

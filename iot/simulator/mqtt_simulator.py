"""
CyberShield SatCom 3D - standalone MQTT IoT simulator.

Acts like real IoT devices: each simulated device opens its own MQTT
connection, publishes JSON readings to cybershield/iot/<id>/telemetry and
"online"/"offline" to cybershield/iot/<id>/status.

All scenarios run only against YOUR local broker. They are simulations for
testing the detection engine, not tools for attacking real systems.

Scenarios
  normal        3 devices, one reading every 5 s each               (default)
  flood         one device sends many messages per second           (Scenario A)
  unauthorized  an unregistered device "IOT-999" sends data         (Scenario B)
  abnormal      one device reports out-of-range values              (Scenario C)
  connstorm     one device connects and disconnects rapidly         (Scenario D)
  disconnect    one device goes silent without saying goodbye; the broker
                announces it offline using its "last will" message

Examples (run from the project root with the backend venv active)
  python iot/simulator/mqtt_simulator.py
  python iot/simulator/mqtt_simulator.py --scenario flood --device IOT-002 --rate 20
  python iot/simulator/mqtt_simulator.py --scenario abnormal --device IOT-001
  python iot/simulator/mqtt_simulator.py --scenario disconnect --device IOT-003
"""
import argparse
import json
import math
import random
import sys
import time

import paho.mqtt.client as mqtt

PREFIX = "cybershield"

# Same climates as the backend's built-in simulator.
PROFILES = {
    "IOT-001": {"temp": 34.0, "temp_swing": 6.0, "hum": 22.0, "hum_swing": 8.0},
    "IOT-002": {"temp": 23.0, "temp_swing": 1.5, "hum": 45.0, "hum_swing": 5.0},
    "IOT-003": {"temp": 19.0, "temp_swing": 5.0, "hum": 68.0, "hum_swing": 12.0},
}
DEFAULT_PROFILE = {"temp": 25.0, "temp_swing": 3.0, "hum": 50.0, "hum_swing": 8.0}


def telemetry_topic(device_id):
    return f"{PREFIX}/iot/{device_id}/telemetry"


def status_topic(device_id):
    return f"{PREFIX}/iot/{device_id}/status"


class VirtualDevice:
    """One simulated IoT device with its own MQTT connection."""

    # v1.1: secure MQTT. Set once from the command line (see main()).
    USERNAME = None      # None = use the device ID as user name (secure broker ACL: %u = device)
    PASSWORDS = {}       # device ID -> password, from --credentials
    TLS = False
    SHARED_LOGIN = None  # v2.4: (user, password) for a cloud broker
    CAFILE = None

    def __init__(self, device_id, host, port, keepalive=30):
        self.device_id = device_id
        self.profile = PROFILES.get(device_id, DEFAULT_PROFILE)
        self.battery = random.uniform(70, 100)
        self.phase = random.uniform(0, 2 * math.pi)
        self.host, self.port, self.keepalive = host, port, keepalive
        self.client = None

    # -- connection -----------------------------------------------------
    def connect(self):
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{self.device_id}-{random.randint(1000, 9999)}",
        )
        # "Last will": if we vanish without disconnecting, the broker publishes this for us.
        self.client.will_set(status_topic(self.device_id), "offline", qos=1)
        password = self.PASSWORDS.get(self.device_id)
        if self.SHARED_LOGIN:  # v2.4: cloud broker, one account for every device
            self.client.username_pw_set(*self.SHARED_LOGIN)
        elif password is not None:
            self.client.username_pw_set(self.USERNAME or self.device_id, password)
        if self.TLS:
            import ssl
            self.client.tls_set(ca_certs=self.CAFILE, tls_version=ssl.PROTOCOL_TLS_CLIENT)
        self.client.connect(self.host, self.port, keepalive=self.keepalive)
        self.client.loop_start()
        self.client.publish(status_topic(self.device_id), "online", qos=1)

    def disconnect(self, clean=True):
        if clean:
            self.client.publish(status_topic(self.device_id), "offline", qos=1).wait_for_publish(2)
            self.client.disconnect()
        self.client.loop_stop()

    # -- readings -------------------------------------------------------
    def reading(self, abnormal=False):
        p = self.profile
        wave = math.sin(2 * math.pi * time.time() / 300 + self.phase)
        temperature = p["temp"] + p["temp_swing"] * wave + random.gauss(0, 0.3)
        humidity = min(100, max(0, p["hum"] - p["hum_swing"] * wave + random.gauss(0, 0.8)))
        if abnormal:
            # e.g. sensor tampering or a fire: far outside the allowed range
            temperature = random.uniform(75, 95)
            humidity = random.uniform(1, 4)
        self.battery = max(5, self.battery - random.uniform(0.01, 0.05))
        self.seq = getattr(self, "seq", 0) + 1  # v2.7: for delivery rate and latency
        return {
            "device_id": self.device_id,
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
            "battery": round(self.battery, 1),
            "source": "simulator",
            "seq": self.seq,
            "ts_sent": int(time.time() * 1000),
        }

    def send(self, abnormal=False):
        data = self.reading(abnormal)
        self.client.publish(telemetry_topic(self.device_id), json.dumps(data))
        return data


def log(device_id, data):
    print(f"[{time.strftime('%H:%M:%S')}] {device_id} -> T={data['temperature']}C "
          f"H={data['humidity']}% B={data['battery']}%")


# ---------------------------------------------------------------- scenarios
def run_normal(args):
    devices = [VirtualDevice(d, args.host, args.port) for d in args.devices.split(",")]
    for d in devices:
        d.connect()
    print(f"Normal traffic from {', '.join(d.device_id for d in devices)} every {args.interval}s. Ctrl+C to stop.")
    try:
        while True:
            for d in devices:
                log(d.device_id, d.send())
                time.sleep(args.interval / len(devices))
    finally:
        for d in devices:
            d.disconnect()


def run_flood(args):
    d = VirtualDevice(args.device, args.host, args.port)
    d.connect()
    total = int(args.rate * args.duration)
    print(f"FLOOD: {d.device_id} sends {args.rate} msg/s for {args.duration}s ({total} messages)")
    for i in range(total):
        d.send()
        if i % args.rate == 0:
            print(f"  sent {i}/{total}")
        time.sleep(1 / args.rate)
    d.disconnect()
    print("Flood finished.")


def run_unauthorized(args):
    device_id = args.device if args.device not in PROFILES else "IOT-999"
    d = VirtualDevice(device_id, args.host, args.port)
    d.connect()
    print(f"UNAUTHORIZED: unregistered device {device_id} publishing for {args.duration}s")
    end = time.time() + args.duration
    while time.time() < end:
        log(device_id, d.send())
        time.sleep(2)
    d.disconnect()


def run_abnormal(args):
    d = VirtualDevice(args.device, args.host, args.port)
    d.connect()
    print(f"ABNORMAL: {d.device_id} reports out-of-range values for {args.duration}s")
    end = time.time() + args.duration
    while time.time() < end:
        log(d.device_id, d.send(abnormal=True))
        time.sleep(2)
    d.disconnect()


def run_connstorm(args):
    print(f"CONNECTION STORM: {args.device} reconnects {args.count} times")
    for i in range(args.count):
        d = VirtualDevice(args.device, args.host, args.port)
        d.connect()
        time.sleep(0.15)
        d.disconnect()
        print(f"  connection {i + 1}/{args.count}")
        time.sleep(0.15)
    print("Connection storm finished.")


def run_disconnect(args):
    # Short keepalive so the broker notices the silence within ~8 seconds.
    d = VirtualDevice(args.device, args.host, args.port, keepalive=5)
    d.connect()
    print(f"DISCONNECT: {d.device_id} sends normally for {args.duration}s, then goes silent")
    end = time.time() + args.duration
    while time.time() < end:
        log(d.device_id, d.send())
        time.sleep(args.interval)
    print("Device goes silent now (no goodbye). The broker should publish its last will "
          "'offline' within ~8 s.")
    d.disconnect(clean=False)
    time.sleep(10)


SCENARIOS = {
    "normal": run_normal,
    "flood": run_flood,
    "unauthorized": run_unauthorized,
    "abnormal": run_abnormal,
    "connstorm": run_connstorm,
    "disconnect": run_disconnect,
}


def main():
    parser = argparse.ArgumentParser(description="CyberShield MQTT IoT simulator (local testing only)")
    parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    parser.add_argument("--host", default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--devices", default="IOT-001,IOT-002,IOT-003", help="normal: comma-separated IDs")
    parser.add_argument("--device", default="IOT-002", help="device used by the other scenarios")
    parser.add_argument("--interval", type=float, default=5, help="seconds between readings per device")
    parser.add_argument("--rate", type=int, default=20, help="flood: messages per second")
    parser.add_argument("--duration", type=float, default=15, help="seconds the scenario runs")
    parser.add_argument("--count", type=int, default=20, help="connstorm: number of reconnects")
    # v1.1: secure MQTT
    parser.add_argument("--credentials", default=None,
                        help="file with 'DEVICE-ID:password' lines (made by iot/mosquitto/setup_secure_mqtt.py)")
    parser.add_argument("--tls", action="store_true", help="encrypted connection (use --port 8883)")
    parser.add_argument("--cafile", default=None, help="CA certificate of the broker (empty = system CAs, for cloud brokers)")
    # v2.4: cloud broker (HiveMQ Cloud, EMQX Cloud): one login for all devices, see docs/CLOUD_MQTT.md
    parser.add_argument("--username", default=None, help="cloud broker user (same for every device)")
    parser.add_argument("--password", default=None, help="cloud broker password")
    parser.add_argument("--prefix", default=None, help="topic prefix (must match MQTT_TOPIC_PREFIX of the backend)")
    args = parser.parse_args()
    if args.username:
        VirtualDevice.SHARED_LOGIN = (args.username, args.password)
    if args.prefix:
        global PREFIX
        PREFIX = args.prefix
    if args.credentials:
        with open(args.credentials, encoding="utf-8") as f:
            for line in f:
                if ":" in line and not line.startswith("#"):
                    user, pw = line.strip().split(":", 1)
                    VirtualDevice.PASSWORDS[user] = pw
    VirtualDevice.TLS, VirtualDevice.CAFILE = args.tls, args.cafile

    if args.scenario == "unauthorized" and args.device == "IOT-002":
        args.device = "IOT-999"
    try:
        SCENARIOS[args.scenario](args)
    except ConnectionRefusedError:
        sys.exit(f"Cannot connect to the MQTT broker at {args.host}:{args.port}. Is Mosquitto running?")
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()

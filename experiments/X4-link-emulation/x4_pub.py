"""X4 device side: 5 QoS-0 and 5 QoS-1 devices publish 1 reading/s each through the
emulated link (same run, same link => paired QoS comparison). Logs every attempt and
every connect/disconnect."""
import argparse, csv, json, threading, time
import paho.mqtt.client as mqtt
ap = argparse.ArgumentParser()
ap.add_argument("--host", default="10.9.0.1"); ap.add_argument("--duration", type=float, default=120)
ap.add_argument("--drain", type=float, default=45); ap.add_argument("--keepalive", type=int, default=30)
ap.add_argument("--tag", required=True)
a = ap.parse_args()
devs = [(f"Q0-{i}", 0) for i in range(5)] + [(f"Q1-{i}", 1) for i in range(5)]
ev = open(f"x4_out/{a.tag}_events.csv", "w"); evl = threading.Lock()
def log_ev(d, e):
    with evl: ev.write(f"{d},{e},{time.time():.3f}\n"); ev.flush()
cl = {}
for d, q in devs:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"x4-{a.tag}-{d}")
    c.reconnect_delay_set(1, 10)
    c.on_connect = (lambda d: lambda *x: log_ev(d, "connect"))(d)
    c.on_disconnect = (lambda d: lambda *x: log_ev(d, "disconnect"))(d)
    c.connect_async(a.host, 1883, a.keepalive); c.loop_start(); cl[d] = c
time.sleep(3)
f = open(f"x4_out/{a.tag}_sent.csv", "w", newline=""); w = csv.writer(f); w.writerow(["device_id", "qos", "seq", "ts_sent_ms", "rc"])
seq = {d: 0 for d, _ in devs}
t_end = time.time() + a.duration; k = 0
while time.time() < t_end:
    d, q = devs[k % len(devs)]; k += 1; seq[d] += 1
    ts = int(time.time() * 1000)
    m = {"device_id": d, "temperature": 22.0, "humidity": 45.0, "battery": 90.0, "seq": seq[d], "ts_sent": ts, "qos": q}
    info = cl[d].publish(f"cybershield/iot/{d}/telemetry", json.dumps(m), qos=q)
    w.writerow([d, q, seq[d], ts, info.rc])
    time.sleep(1.0 / len(devs))
f.close(); time.sleep(a.drain)
for c in cl.values(): c.loop_stop(); c.disconnect()

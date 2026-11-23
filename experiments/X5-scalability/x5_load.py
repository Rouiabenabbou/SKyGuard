"""X5 load generator: one MQTT connection per device, each device publishes one reading
every INTERVAL s (random phase), values inside the device's allowed range."""
import json, random, sys, time, csv, heapq, math
import paho.mqtt.client as mqtt
ids = sys.argv[1].split(","); interval = float(sys.argv[2]); dur = float(sys.argv[3]); out = sys.argv[4]
cl = {}
for d in ids:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"x5-{d}"); c.connect("127.0.0.1", 1883, 60); c.loop_start(); cl[d] = c
time.sleep(2)
w = csv.writer(open(out, "w", newline=""))
h = [(time.time() + random.uniform(0, interval), d) for d in ids]; heapq.heapify(h); seq = {d: 0 for d in ids}
end = time.time() + dur
while time.time() < end:
    t, d = heapq.heappop(h); time.sleep(max(0, t - time.time())); seq[d] += 1; ts = int(time.time() * 1000)
    m = {"device_id": d, "temperature": round(23 + random.gauss(0, 0.5), 2), "humidity": round(45 + random.gauss(0, 1), 2),
         "battery": 90.0, "source": "x5", "seq": seq[d], "ts_sent": ts}
    cl[d].publish(f"cybershield/iot/{d}/telemetry", json.dumps(m)); w.writerow([d, seq[d], ts])
    heapq.heappush(h, (t + interval, d))
time.sleep(3)
for c in cl.values(): c.loop_stop(); c.disconnect()

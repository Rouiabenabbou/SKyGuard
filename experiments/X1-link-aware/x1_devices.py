"""X1 benign devices (run inside devns, reach the broker through emulated link sat2).
Groups: 1 Hz QoS1, 1 Hz QoS0, 0.2 Hz QoS1, 0.2 Hz QoS0 (assigned round-robin).
Values from the platform's own simulator formula (always inside the allowed range).
paho defaults: keepalive 60 s, auto-reconnect 1-10 s, max 20 in-flight QoS 1."""
import json, math, random, sqlite3, sys, threading, time, heapq, csv
import paho.mqtt.client as mqtt
sys.path.insert(0, "../e1"); from e1_detection import BUILTIN, DEFAULT, profile_for, CYCLE
db = sqlite3.connect(sys.argv[1]); dur = float(sys.argv[2]); random.seed(int(sys.argv[3]))
rows = db.execute("select device_id,temp_min,temp_max,humidity_min,humidity_max from devices order by device_id").fetchall()
ops = {r[0] for r in db.execute("select device_id from device_settings")}
G = [(1.0, 1), (1.0, 0), (5.0, 1), (5.0, 0)]
out = csv.writer(open("x1_out/sent.csv", "w", newline="")); out.writerow(["device_id", "seq", "ts_sent_ms", "interval", "qos", "rc"])
evf = open("x1_out/dev_events.csv", "w"); lk = threading.Lock()
devs = []
for i, r in enumerate(rows):
    iv, q = G[i % 4]
    prof = profile_for(*r[1:]) if r[0] in ops else BUILTIN.get(r[0], DEFAULT)
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"x1-{r[0]}")
    did = r[0]
    def oc(c, u, f, rc, p, did=did):
        with lk: evf.write(f"{did},connect,{time.time():.3f}\n"); evf.flush()
        c.publish(f"cybershield/iot/{did}/status", "online", qos=1)
    def od(c, u, f, rc, p, did=did):
        with lk: evf.write(f"{did},disconnect,{time.time():.3f}\n"); evf.flush()
    c.on_connect, c.on_disconnect = oc, od
    c.will_set(f"cybershield/iot/{did}/status", "offline", qos=1)
    c.reconnect_delay_set(1, 10); c.connect_async("10.7.0.1", 1883, 60); c.loop_start()
    devs.append({"id": did, "iv": iv, "q": q, "p": prof, "ph": random.uniform(0, 6.28), "seq": 0, "c": c})
time.sleep(3)
h = [(time.time() + random.uniform(0, d["iv"]), k) for k, d in enumerate(devs)]; heapq.heapify(h)
t_end = time.time() + dur
while time.time() < t_end:
    t, k = heapq.heappop(h); time.sleep(max(0, t - time.time())); d = devs[k]; p = d["p"]
    w = math.sin(2 * math.pi * time.time() / CYCLE + d["ph"])
    d["seq"] += 1; ts = int(time.time() * 1000)
    m = {"device_id": d["id"], "temperature": round(p["temp"] + p["temp_swing"] * w + random.gauss(0, 0.3), 2),
         "humidity": round(max(0, min(100, p["hum"] - p["hum_swing"] * w + random.gauss(0, 0.8))), 2),
         "battery": 90.0, "source": "x1-benign", "seq": d["seq"], "ts_sent": ts}
    info = d["c"].publish(f"cybershield/iot/{d['id']}/telemetry", json.dumps(m), qos=d["q"])
    out.writerow([d["id"], d["seq"], ts, d["iv"], d["q"], info.rc])
    heapq.heappush(h, (t + d["iv"], k))
time.sleep(30)
for d in devs: d["c"].loop_stop(); d["c"].disconnect()

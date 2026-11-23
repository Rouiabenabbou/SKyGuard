"""X3 device-side agent with four path-handling modes (run side by side in one outage).

  off       one primary session; recovery left to MQTT/TCP (paho auto-reconnect, QoS 1 queue)
  reconnect standard client-side failover: keepalive 5 s; when the client declares the
            session lost (no PINGRESP/PUBACK within keepalive) it opens a session to the
            backup host and re-sends unacknowledged readings; no failback (stays on backup)
  fixed     CyberShield v2.7 failover: PUBACK missing > 2 s => switch to backup, re-send
            unacknowledged readings; failback after 10 s of good probes, make-before-break
  rtt       as fixed, but the timeout is scaled to the measured PUBACK round-trip time:
            timeout = max(1 s, 4 * srtt) (srtt = EWMA, alpha 1/8, as in TCP)
"""
import argparse, csv, json, socket, threading, time
import paho.mqtt.client as mqtt

ap = argparse.ArgumentParser()
ap.add_argument("--primary", default="10.9.0.1"); ap.add_argument("--backup", default="10.8.0.1")
ap.add_argument("--device", required=True); ap.add_argument("--mode", choices=["off", "reconnect", "fixed", "rtt"], required=True)
ap.add_argument("--interval", type=float, default=1.0); ap.add_argument("--failback", type=float, default=10.0)
ap.add_argument("--duration", type=float, default=100); ap.add_argument("--out", required=True)
a = ap.parse_args()
KEEP = 5 if a.mode == "reconnect" else 30
ev = open(a.out + "_events.csv", "w", newline=""); evw = csv.writer(ev); evw.writerow(["t", "event", "detail"])
def event(e, d=""): evw.writerow([f"{time.time():.3f}", e, d]); ev.flush()

class Session:
    def __init__(self, host, name):
        self.host, self.name, self.unacked, self.lock = host, name, {}, threading.Lock()
        self.connected, self.lost = threading.Event(), threading.Event()
        self.srtt = None
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"x3-{a.device}-{name}-{int(time.time()*1000)%100000}")
        self.c.reconnect_delay_set(1, 10)
        self.c.on_connect = lambda c, u, f, rc, p: self.connected.set()
        self.c.on_disconnect = self._disc
        self.c.on_publish = self._acked
        self.c.connect_async(host, 1883, KEEP); self.c.loop_start()
    def _disc(self, c, u, f, rc, p):
        self.connected.clear(); self.lost.set()
    def _acked(self, c, u, mid, rc, p):
        with self.lock:
            v = self.unacked.pop(mid, None)
        if v:
            r = time.time() - v[0]
            self.srtt = r if self.srtt is None else 0.875 * self.srtt + 0.125 * r
    def publish(self, seq, payload):
        info = self.c.publish(f"cybershield/iot/{a.device}/telemetry", payload, qos=1)
        with self.lock: self.unacked[info.mid] = (time.time(), seq, payload)
    def oldest(self):
        with self.lock: return min((v[0] for v in self.unacked.values()), default=None)
    def pending(self):
        with self.lock: return sorted((v[1], v[2]) for v in self.unacked.values())
    def close(self, clean=True):
        self.c.loop_stop()
        if clean: self.c.disconnect()

def probe(host):
    try: s = socket.create_connection((host, 1883), timeout=1.0); s.close(); return True
    except OSError: return False

def timeout(sess):
    if a.mode == "fixed": return 2.0
    return max(1.0, 4 * sess.srtt) if sess.srtt else 2.0

def switch(active):
    event("state", "switching")
    pend = active.pending(); dead = active
    threading.Thread(target=dead.close, args=(False,), daemon=True).start()
    b = Session(a.backup, "backup")
    if b.connected.wait(5):
        for s_, p_ in pend: b.publish(s_, p_)
        event("state", "backup"); event("resent", str(len(pend))); return b
    event("error", "backup connect failed"); return None

state, active = "primary", Session(a.primary, "primary")
active.connected.wait(10); event("state", "primary")
ok_since, last_probe = None, 0.0
send = open(a.out + "_send.csv", "w", newline=""); sw = csv.writer(send); sw.writerow(["seq", "ts_sent_ms", "path"])
seq, t_end, next_t = 0, time.time() + a.duration, time.time()
while time.time() < t_end:
    now = time.time()
    if now >= next_t:
        seq += 1; ts = int(now * 1000)
        payload = json.dumps({"device_id": a.device, "temperature": 23.0, "humidity": 45.0, "battery": 90.0,
                              "source": f"x3-{a.mode}", "seq": seq, "ts_sent": ts})
        active.publish(seq, payload); sw.writerow([seq, ts, active.name]); send.flush()
        next_t += a.interval
    if a.mode in ("fixed", "rtt"):
        if state == "primary":
            o = active.oldest()
            if o is not None and now - o > timeout(active):
                event("timeout", f"{timeout(active):.3f}")
                b = switch(active)
                if b: active, state, ok_since = b, "backup", None
        elif state == "backup" and now - last_probe >= 1.0:
            last_probe = now
            if probe(a.primary):
                ok_since = ok_since or now
                if now - ok_since >= a.failback:
                    newp = Session(a.primary, "primary")
                    if newp.connected.wait(5):
                        old, active, state = active, newp, "primary"
                        event("state", "primary(failback)"); time.sleep(0.5); old.close()
            else:
                ok_since = None
    elif a.mode == "reconnect" and state == "primary" and active.lost.is_set():
        b = switch(active)
        if b: active, state = b, "backup"
    time.sleep(0.02)
time.sleep(8)
event("end"); active.close()

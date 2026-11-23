"""X1 orchestrator (root namespace): drives the emulated link sat2 through a schedule of
outages (10/30/60/120/300 s), degraded periods (GEO-like, burst loss, random loss) and a
flapping period, while an attacker on a separate path (directly at the broker) injects
attacks at random times. Two backends (link-unaware and link-aware) see the same traffic."""
import csv, json, random, sqlite3, sys, threading, time
import paho.mqtt.client as mqtt
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 1
random.seed(SEED)
DBP = sys.argv[1]
LEO = {"delay_ms": 35, "jitter_ms": 6, "loss": 0.003, "down": False, "ge": None, "rate_kbps": 0}
GE5 = {"p_gb": 0.2 * 0.05 / 0.95, "p_bg": 0.2}
state = {"ctx": "normal", "outages": []}  # outages: [t_cut, t_restore]
def setlink(cfg, ctx):
    json.dump(cfg, open("sat2.json", "w")); state["ctx"] = ctx
    lg.write(f"{time.time():.3f},{ctx},{json.dumps(cfg)}\n"); lg.flush()
lg = open("x1_out/link_schedule.csv", "w")
blocks = [("outage", d) for d in (10, 30, 60, 120) for _ in range(3)] + [("outage", 300)] * 2 + \
         [("geo", 600), ("burst", 600), ("random", 300), ("flap", 300)]
random.shuffle(blocks)
db = sqlite3.connect(DBP); devs = [r[0] for r in db.execute("select device_id from devices order by device_id")]
rng_rows = {r[0]: r[1:] for r in db.execute("select device_id,temp_min,temp_max from devices")}; db.close()
inj = csv.writer(open("x1_out/injections.csv", "w", newline="")); inj.writerow(["i", "type", "targets", "t_start", "t_end", "ctx_start", "ctx_end"])
stop = threading.Event()

def client(cid):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid); c.connect("127.0.0.1", 1883, 30); c.loop_start(); return c
def done(c): time.sleep(0.3); c.loop_stop(); c.disconnect()
def reading(d, ts=None, **kw):
    m = {"device_id": d, "temperature": 22.0, "humidity": 45.0, "battery": 90.0, "source": "x1-attack",
         "ts_sent": ts if ts is not None else int(time.time() * 1000)}; m.update(kw); return m
def flood(d, rate=20, secs=6, forged=None):
    c = client(f"atk-{random.randint(0, 10**6)}")
    for _ in range(int(rate * secs)):
        ts = int(random.uniform(*forged) * 1000) if forged else None
        c.publish(f"cybershield/iot/{d}/telemetry", json.dumps(reading(d, ts))); time.sleep(1 / rate)
    done(c)
def distributed(ds, rate=4, secs=15):
    cs = [client(f"atk-d-{random.randint(0, 10**6)}") for _ in ds]
    for _ in range(int(rate * secs)):
        for c, d in zip(cs, ds): c.publish(f"cybershield/iot/{d}/telemetry", json.dumps(reading(d)))
        time.sleep(1 / rate)
    for c in cs: done(c)
def connstorm(d):
    for _ in range(8):
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"atk-s-{random.randint(0, 10**6)}")
        c.connect("127.0.0.1", 1883, 30); c.loop_start(); c.publish(f"cybershield/iot/{d}/status", "online", qos=1)
        time.sleep(0.3); c.loop_stop(); c.disconnect(); time.sleep(0.3)
def abnormal(d):
    c = client(f"atk-a-{random.randint(0, 10**6)}"); tmax = rng_rows[d][1]
    for _ in range(3): c.publish(f"cybershield/iot/{d}/telemetry", json.dumps(reading(d, temperature=tmax + random.uniform(5, 20)))); time.sleep(2)
    done(c)

W = {"flood": 25, "lowslow": 10, "distributed": 10, "forged": 15, "connstorm": 15, "abnormal": 10, "concurrent": 15}
def attacker():
    i, last = 0, {}
    time.sleep(90)
    while not stop.is_set():
        typ = random.choices(list(W), weights=list(W.values()))[0]
        free = lambda t: [d for d in devs if time.time() - last.get((d, t), 0) > 70]
        ctx0, t0 = state["ctx"], time.time()
        if typ == "flood": tg = [random.choice(free("flood"))]; flood(tg[0])
        elif typ == "lowslow": tg = [random.choice(free("flood"))]; flood(tg[0], rate=8, secs=30)
        elif typ == "distributed": tg = random.sample(free("flood"), 8); distributed(tg)
        elif typ == "forged":
            tg = [random.choice(free("flood"))]
            iv = state["outages"][-1] if state["outages"] else [time.time() - 70, time.time() - 60]
            flood(tg[0], forged=(iv[0] + 0.5, (iv[1] or time.time()) - 0.5))
        elif typ == "connstorm": tg = [random.choice(free("connstorm"))]; connstorm(tg[0])
        elif typ == "abnormal": tg = [random.choice(free("abnormal"))]; abnormal(tg[0])
        else:
            a_, b_, c_ = random.sample(devs, 3); tg = [a_, b_, c_]
            th = [threading.Thread(target=f, args=(x,)) for f, x in ((flood, a_), (abnormal, b_), (connstorm, c_))]
            [t.start() for t in th]; [t.join() for t in th]
        t1 = time.time()
        for d in tg: last[(d, "flood" if typ in ("flood", "lowslow", "distributed", "forged") else typ)] = t1
        if typ == "concurrent": last[(tg[0], "flood")] = last[(tg[1], "abnormal")] = last[(tg[2], "connstorm")] = t1
        inj.writerow([i, typ, "|".join(tg), f"{t0:.3f}", f"{t1:.3f}", ctx0, state["ctx"]]); i += 1
        print(f"[atk {i}] {typ} {tg[:3]} ctx={ctx0}", flush=True)
        time.sleep(random.uniform(20, 40))

setlink(LEO, "normal"); threading.Thread(target=attacker, daemon=True).start()
time.sleep(120)
for kind, d in blocks:
    if kind == "outage":
        c = dict(LEO); c["down"] = True; t = time.time(); state["outages"].append([t, None]); setlink(c, f"outage{d}")
        time.sleep(d); state["outages"][-1][1] = time.time(); setlink(LEO, "recovery")
        time.sleep(25); setlink(LEO, "normal"); time.sleep(75)
    elif kind == "flap":
        end = time.time() + d
        while time.time() < end:
            c = dict(LEO); c["down"] = True; t = time.time(); state["outages"].append([t, None]); setlink(c, "flap")
            time.sleep(8); state["outages"][-1][1] = time.time(); setlink(LEO, "flap"); time.sleep(4)
        setlink(LEO, "normal"); time.sleep(60)
    else:
        c = dict(LEO)
        if kind == "geo": c.update(delay_ms=280, jitter_ms=0)
        if kind == "burst": c["ge"] = GE5
        if kind == "random": c["loss"] = 0.05
        setlink(c, kind); time.sleep(d); setlink(LEO, "normal"); time.sleep(60)
time.sleep(60); stop.set(); time.sleep(40)
json.dump({"seed": SEED, "outages": state["outages"], "blocks": blocks}, open("x1_out/meta.json", "w"))
print("done", flush=True)

"""X5 orchestrator: fleet sizes 26-1000 at one reading per 5 s (+ a 1 Hz stress level),
3 runs each in random order, fresh database per run. Backend pinned to CPUs 0-1,
broker to CPU 2, load generators to CPU 3."""
import csv, json, os, random, shutil, sqlite3, subprocess, sys, threading, time, urllib.request
import psutil
BK = "/tmp/claude-0/exp/cs/backend"; PY = "/tmp/claude-0/exp/venv/bin/python"; OUT = "/tmp/claude-0/exp/x5/out"
os.makedirs(OUT, exist_ok=True)
LEVELS = [(n, 5.0) for n in (26, 100, 250, 500, 1000)] + [(250, 1.0), (500, 1.0)]
plan = [(n, iv, r) for r in range(3) for n, iv in LEVELS]; random.seed(5); random.shuffle(plan)
WARM, MEAS = 30, 120
def start_backend(db, tag):
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db}", MQTT_CLIENT_ID=f"x5-{tag}", PROC_LOG=f"{OUT}/{tag}_proc.csv",
               MEASURE_LOG=f"{OUT}/{tag}_measure.csv")
    p = subprocess.Popen(["taskset", "-c", "0,1", PY, "-m", "uvicorn", "app.main:app", "--port", "8005"], cwd=BK, env=env,
                         stdout=open(f"{OUT}/{tag}_backend.log", "w"), stderr=subprocess.STDOUT)
    for _ in range(60):
        try: urllib.request.urlopen("http://127.0.0.1:8005/metrics", timeout=1); return p
        except Exception: time.sleep(1)
    return p
def api_token():
    req = urllib.request.Request("http://127.0.0.1:8005/api/auth/login", data=json.dumps({"username": "admin", "password": "Admin@2026"}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read()).get("token")
# template DB with the seeded 26 devices
tmpl = f"{OUT}/template.db"
if not os.path.exists(tmpl):
    p = start_backend(tmpl, "template"); time.sleep(3); p.terminate(); p.wait()
seed_ids = [r[0] for r in sqlite3.connect(tmpl).execute("select device_id from devices order by device_id")]
mosq = [x for x in psutil.process_iter(["name"]) if x.info["name"] == "mosquitto"][0]
subprocess.run(["taskset", "-cp", "2", str(mosq.pid)], stdout=subprocess.DEVNULL)
log = open(f"{OUT}/runs.jsonl", "a")
for n, iv, r in plan:
    tag = f"n{n}_i{int(iv)}_r{r}"; db = f"{OUT}/{tag}.db"; shutil.copy(tmpl, db)
    c = sqlite3.connect(db)
    for k in range(max(0, n - len(seed_ids))):
        c.execute("insert into devices select ?, 'Scale node '||?, device_type, location, connection_type, 'offline', 'normal', null, null, null, 0, null, temp_min, temp_max, humidity_min, humidity_max from devices where device_id='IOT-002'", (f"SC-{k:04d}", k))
    c.commit(); c.close()
    ids = (seed_ids + [f"SC-{k:04d}" for k in range(max(0, n - len(seed_ids)))])[:n]
    p = start_backend(db, tag); bp = psutil.Process(p.pid)
    try: tok = api_token()
    except Exception as e: tok = None; print("login failed", e)
    samples, apis, stop = [], [], threading.Event()
    def sampler():
        bp.cpu_percent(); mosq.cpu_percent()
        while not stop.is_set():
            time.sleep(1)
            try:
                kids = bp.children(recursive=True)
                samples.append((time.time(), bp.cpu_percent() + sum(k.cpu_percent() for k in kids), bp.memory_info().rss / 2**20, mosq.cpu_percent(), mosq.memory_info().rss / 2**20))
            except Exception: pass
    def api():
        while not stop.is_set():
            t0 = time.time()
            try:
                rq = urllib.request.Request("http://127.0.0.1:8005/api/devices", headers={"Authorization": f"Bearer {tok}"} if tok else {})
                urllib.request.urlopen(rq, timeout=10).read(); apis.append((t0, time.time() - t0, 1))
            except Exception: apis.append((t0, time.time() - t0, 0))
            time.sleep(2)
    groups = [ids[i::4] for i in range(4)]
    loads = [subprocess.Popen(["taskset", "-c", "3", PY, "x5_load.py", ",".join(g), str(iv), str(WARM + MEAS), f"{OUT}/{tag}_sent{i}.csv"])
             for i, g in enumerate(groups) if g]
    time.sleep(WARM); t_meas = time.time()
    th = [threading.Thread(target=sampler, daemon=True), threading.Thread(target=api, daemon=True)]; [t.start() for t in th]
    for l in loads: l.wait()
    t_end = time.time(); time.sleep(10); stop.set(); time.sleep(2.5)
    p.terminate(); p.wait()
    json.dump({"samples": samples, "api": apis}, open(f"{OUT}/{tag}_res.json", "w"))
    log.write(json.dumps({"tag": tag, "n": n, "interval": iv, "run": r, "t_meas": t_meas, "t_end": t_end, "db_bytes": os.path.getsize(db)}) + "\n"); log.flush()
    print(tag, "done", flush=True)

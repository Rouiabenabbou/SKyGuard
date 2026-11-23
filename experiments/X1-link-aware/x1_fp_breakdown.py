"""Which outages and device groups produced post-outage flood alerts (link-unaware engine)?
Prediction: the flood rule (>10 msg/s over 5 s, i.e. >50 messages) fires when the backlog
delivered at recovery exceeds 50 readings: rate x held time > 50."""
import csv, json, sqlite3, sys
from collections import defaultdict, Counter
from datetime import datetime, timezone
d = sys.argv[1]; eng = sys.argv[2] if len(sys.argv) > 2 else "unaware"
meta = json.load(open(f"{d}/meta.json")); outs = [o for o in meta["outages"] if o[1]]
grp = {}
for r in csv.DictReader(open(f"{d}/sent.csv")): grp[r["device_id"]] = (float(r["interval"]), int(r["qos"]))
db = sqlite3.connect(f"{d}/{eng}.db"); res = defaultdict(Counter); tot = defaultdict(Counter)
al = [(dev, datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).timestamp()) for dev, ts in
      db.execute("select device_id,timestamp from security_alerts where alert_type='excessive_message_rate'") if dev in grp]
for a, b in outs:
    L = round(b - a); L = 8 if L < 9 else L  # flap cycles are 8 s
    for dev, g in grp.items():
        tot[L][g] += 1
        if any(dev == x and b <= t <= b + 30 for x, t in al): res[L][g] += 1
print("outage_s, group(interval_s,qos): alerts/outages")
for L in sorted(tot):
    print(L, {f"{g[0]:g}s/q{g[1]}": f"{res[L][g]}/{tot[L][g]}" for g in sorted(tot[L])})

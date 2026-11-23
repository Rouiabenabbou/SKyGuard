import json, statistics as st, math
from collections import defaultdict
R = [json.loads(l) for l in open("x2_results.jsonl")]
g = defaultdict(list)
for r in R: g[(r["scenario"], r["features"], r["norm"], r["model"])].append(r)
TYPES = ["stuck", "drift", "replay", "jump", "noise", "spike"]
def ms(v): return f"{st.mean(v):.3f}±{(1.96*st.stdev(v)/math.sqrt(len(v))) if len(v)>1 else 0:.3f}"
print("scenario,features,norm,model,n_seeds,roc_auc,pr_auc,fp_per_dev_h,precision," + ",".join(f"rec_{t}" for t in TYPES) + ",unique_beyond_rules,inrange_recall")
rows = []
for k in sorted(g):
    v = g[k]
    roc = [x["roc_auc"] for x in v if x["roc_auc"] is not None]; pr = [x["pr_auc"] for x in v if x["pr_auc"] is not None]
    rec = {t: sum(x["episodes"][t]["det"] for x in v) / sum(x["episodes"][t]["n"] for x in v) for t in TYPES}
    uniq = sum(sum(x["episodes"][t]["unique"] for t in TYPES) for x in v) / len(v)
    inr = sum(sum(x["episodes"][t]["det"] for t in TYPES[:-1]) for x in v) / sum(sum(x["episodes"][t]["n"] for t in TYPES[:-1]) for x in v)
    row = [*k, len(v), ms(roc) if roc else "-", ms(pr) if pr else "-", ms([x["fp_per_dev_h"] for x in v]), ms([x["precision"] for x in v])] + \
          [f"{rec[t]:.2f}" for t in TYPES] + [f"{uniq:.1f}", f"{inr:.3f}"]
    rows.append(row); print(",".join(map(str, row)))
json.dump(rows, open("x2_summary.json", "w"), indent=1)

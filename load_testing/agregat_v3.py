import csv, sys, statistics as st
ref, src, dst, ddof = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
hdr = next(csv.reader(open(ref)))
ids = ["algo", "users", "runtime", "n"]
assert hdr[:4] == ids, hdr[:4]
metrics = []
for c in hdr[4:]:
    m = c.rsplit("_", 1)[0]
    if m not in metrics: metrics.append(m)
rows = list(csv.DictReader(open(src)))
miss = [m for m in metrics if m not in rows[0]]
assert not miss, f"brak w runs: {miss}"
def num(x):
    try:
        v = float(x); return v if v == v else None
    except: return None
groups = {}
for r in rows:
    groups.setdefault((r["algo"], r["users"], r["runtime"]), []).append(r)
def sd(v):
    if len(v) < 2: return 0.0
    return st.stdev(v) if ddof == "sample" else st.pstdev(v)
with open(dst, "w", newline="") as f:
    w = csv.writer(f); w.writerow(hdr)
    for g, rs in groups.items():
        out = list(g) + [len(rs)]
        for m in metrics:
            v = [x for x in (num(r[m]) for r in rs) if x is not None]
            out += [st.mean(v), sd(v), min(v), max(v)] if v else ["", "", "", ""]
        w.writerow(out)
print("kolumn:", len(hdr), "| metryk:", len(metrics), "| wierszy:", len(groups))

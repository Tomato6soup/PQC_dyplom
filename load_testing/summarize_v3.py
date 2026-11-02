#!/usr/bin/env python3
import argparse
import csv
import glob
import json
import math
import os
import re
import statistics

TX_WEIGHT = 645787000          # weight jednej transakcji liczony przez runtime
NORMAL_MAX_WEIGHT = {"default": 1.5e12, "raised": 1.5e14}


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, math.ceil(p / 100.0 * len(s)) - 1))
    return s[k]


def mean(values):
    return sum(values) / len(values) if values else None


def norm_hash(h):
    h = h.strip().lower()
    return h[2:] if h.startswith("0x") else h


def err_class(e):
    el = e.lower()
    if "priority is too low" in el:
        return "priority_too_low"
    if "outdated" in el:
        return "nonce_outdated"
    if "pool" in el and ("full" in el or "limit" in el or "too many" in el):
        return "pool_full"
    if "temporarily banned" in el:
        return "tx_banned"
    if "immediately dropped" in el:
        return "immediately_dropped"
    if "timed out" in el or "timeout" in el:
        return "timeout"
    if "connection" in el or "socket" in el or "broken pipe" in el:
        return "connection"
    return "other:" + e[:40]


def load_submits(logdir, tag):
    ok = {}
    attempts = []
    for fn in glob.glob(os.path.join(logdir, f"submits_{tag}_*.csv")):
        with open(fn) as f:
            next(f, None)
            for line in f:
                p = line.rstrip("\n").split(",", 3)
                if len(p) < 3:
                    continue
                try:
                    ts = float(p[0])
                except ValueError:
                    continue
                is_ok = p[2] == "ok"
                err = p[3] if len(p) > 3 else ""
                attempts.append((ts, is_ok, err))
                if is_ok and p[1]:
                    ok[norm_hash(p[1])] = ts
    return ok, attempts


def load_blocks(path):
    blocks = []
    if not os.path.exists(path):
        return blocks
    with open(path) as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") == "block":
                blocks.append(d)
    blocks.sort(key=lambda b: b["number"])
    return blocks


def load_res(path, t_from, t_to):
    cpu, ram = [], []
    if not os.path.exists(path):
        return None, None
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                ts = float(row["timestamp"])
            except Exception:
                continue
            if not (t_from <= ts <= t_to):
                continue
            try:
                cpu.append(float(row["cpu_pct"]))
            except Exception:
                pass
            try:
                ram.append(float(row["ram_mb"]))
            except Exception:
                pass
    return mean(cpu), mean(ram)


POOL_LIMIT_TX = 100000
POOL_LIMIT_BYTES = 2097152 * 1024
TX_BYTES = {"ecdsa": 237, "dilithium2": 3872, "sphincs": 17263}


def parse_pool(logdir, tag, algo, t_from, t_to):
    path = os.path.join(logdir, f"pool_{tag}.log")
    all_ready, win_ready, all_future = [], [], []
    if os.path.exists(path):
        pat = re.compile(r"^(\S+)\s+(substrate_[A-Za-z0-9_]+)(?:\{[^}]*\})?\s+(\S+)\s*$")
        with open(path, errors="replace") as f:
            for line in f:
                m = pat.match(line)
                if not m:
                    continue
                try:
                    ts = float(m.group(1))
                    val = float(m.group(3))
                except ValueError:
                    continue
                name = m.group(2)
                if "ready_transactions" in name:
                    all_ready.append(val)
                    if t_from <= ts <= t_to:
                        win_ready.append(val)
                elif "future_transactions" in name:
                    all_future.append(val)
    ready_max = max(all_ready) if all_ready else None
    est = ready_max * TX_BYTES.get(algo, 0) if ready_max is not None else None
    return {
        "pool_samples": len(all_ready),
        "pool_ready_max": ready_max,
        "pool_ready_mean_window": mean(win_ready),
        "pool_ready_end": all_ready[-1] if all_ready else None,
        "pool_future_max": max(all_future) if all_future else None,
        "pool_bytes_est_max": est,
        "pool_count_frac_max": (ready_max / POOL_LIMIT_TX) if ready_max is not None else None,
        "pool_bytes_frac_max": (est / POOL_LIMIT_BYTES) if est is not None else None,
    }


def parse_node_log(logdir, tag):
    res = {}
    path = os.path.join(logdir, f"node_{tag}.log")
    if not os.path.exists(path):
        return res
    pat = re.compile(r"Prepared block for proposing at (\d+) \((\d+) ms\).*?end: (\w+)")
    with open(path, errors="replace") as f:
        for line in f:
            m = pat.search(line)
            if m:
                res[int(m.group(1))] = (int(m.group(2)), m.group(3))
    return res


def summarize_run(logdir, meta, block_rows):
    tag = meta["tag"]
    dur = float(meta["duration_s"])
    ok, attempts = load_submits(logdir, tag)
    blocks = load_blocks(os.path.join(logdir, f"blocks_{tag}.jsonl"))
    node_blocks = parse_node_log(logdir, tag)

    if attempts:
        ls = min(a[0] for a in attempts)
    else:
        ls = float(meta["locust_start"])
    warm = ls + float(meta["warmup_s"])
    le = warm + dur

    incl = {}
    pb = []
    for b in blocks:
        ts = b["ts_ms"] / 1000.0 if b.get("ts_ms") else b["t_detect"]
        ours = [h for h in b["hashes"] if h in ok]
        for h in ours:
            incl[h] = (b["t_detect"], ts)
        rec = {
            "tag": tag, "runtime": meta["runtime"], "algo": meta["algo"],
            "users": meta["users"], "run": meta["run"],
            "number": b["number"], "ts": ts, "t_detect": b["t_detect"],
            "n_ours": len(ours), "n_signed": b["n_signed"], "n_total": b["n_total"],
            "ext_bytes": b["ext_bytes"], "alllen": b.get("alllen"),
            "weight_ref_time": b.get("weight_ref_time"),
            "post_warmup": warm <= ts <= le,
            "build_ms": node_blocks.get(b["number"], (None, None))[0],
            "end_reason": node_blocks.get(b["number"], (None, None))[1],
        }
        pb.append(rec)
        block_rows.append(rec)

    diffs = [pb[i + 1]["ts"] - pb[i]["ts"] for i in range(len(pb) - 1)]
    interval = statistics.median(diffs) if diffs else 6.0
    pw = [x for x in pb if x["post_warmup"]]
    pw_ours = [x["n_ours"] for x in pw]
    tps_pw = (sum(pw_ours) / (len(pw) * interval)) if pw else None
    tps_span = None
    if len(pw) >= 2 and pw[-1]["ts"] > pw[0]["ts"]:
        tps_span = sum(pw_ours) / (pw[-1]["ts"] - pw[0]["ts"])

    win_att = [a for a in attempts if warm <= a[0] <= le]
    win_len = max(le - warm, 1e-9)
    fails = [a for a in win_att if not a[1]]
    err_counts = {}
    for a in fails:
        c = err_class(a[2])
        err_counts[c] = err_counts.get(c, 0) + 1

    win_ok = [(h, t) for h, t in ok.items() if warm <= t <= le]
    included = [(h, t) for h, t in win_ok if h in incl]
    lat_d = [incl[h][0] - t for h, t in included]
    lat_b = [incl[h][1] - t for h, t in included]

    cpu, ram = load_res(os.path.join(logdir, f"res_{tag}.log"), warm, le)
    pool = parse_pool(logdir, tag, meta["algo"], warm, le)

    ext_pw = [x["ext_bytes"] for x in pw]
    wmeas = [x["weight_ref_time"] for x in pw if x["weight_ref_time"] is not None]
    ours_mean = mean(pw_ours)
    west = ours_mean * TX_WEIGHT if ours_mean is not None else None
    normal_len = float(meta["block_len_normal"])

    bm = [(x["build_ms"], x["n_ours"], x["end_reason"]) for x in pw if x.get("build_ms") is not None]
    busy = [(ms, n) for ms, n, _ in bm if n > 0]
    busy_tx = sum(n for _, n in busy)
    ms_per_tx = (sum(ms for ms, _ in busy) / busy_tx) if busy_tx > 0 else None
    reasons = {}
    for _, _, r in bm:
        reasons[r] = reasons.get(r, 0) + 1
    hit = reasons.get("HitDeadline", 0)

    return {
        "tag": tag, "runtime": meta["runtime"], "algo": meta["algo"],
        "users": meta["users"], "run": meta["run"],
        "tps_post_warmup": tps_pw, "tps_span_first_last": tps_span,
        "request_rate": len(win_att) / win_len,
        "fail_rate": (len(fails) / len(win_att)) if win_att else None,
        "error_types": ";".join(f"{k}:{v}" for k, v in sorted(err_counts.items())),
        "inclusion_ratio": (len(included) / len(win_ok)) if win_ok else None,
        "not_included": len(win_ok) - len(included),
        "lat_mean_s": mean(lat_d), "lat_median_s": pct(lat_d, 50), "lat_p95_s": pct(lat_d, 95),
        "latblk_mean_s": mean(lat_b), "latblk_median_s": pct(lat_b, 50), "latblk_p95_s": pct(lat_b, 95),
        "cpu_pct": cpu, "ram_mb": ram,
        "blocks_total": len(pb), "blocks_post_warmup": len(pw),
        "ours_per_block_post_warmup": ";".join(str(n) for n in pw_ours),
        "ours_per_block_mean": ours_mean,
        "ext_bytes_mean": mean(ext_pw), "ext_bytes_max": max(ext_pw) if ext_pw else None,
        "len_used_pct_of_normal": (100.0 * mean(ext_pw) / normal_len) if ext_pw else None,
        "weight_measured_mean": mean(wmeas),
        "weight_est_mean": west,
        "weight_est_pct_of_normal": (100.0 * west / NORMAL_MAX_WEIGHT[meta["runtime"]]) if west is not None else None,
        "pool_ok_before": meta.get("pool_ok"), "pending_before": meta.get("pending_before"),
        "build_ms_mean": mean([ms for ms, _, _ in bm]),
        "build_ms_per_tx": ms_per_tx,
        "end_reasons": ";".join(f"{k}:{v}" for k, v in sorted(reasons.items())),
        "blocks_hit_deadline_frac": (hit / len(bm)) if bm else None,
        **pool,
    }


SUMMARY_METRICS = [
    "tps_post_warmup", "request_rate", "fail_rate", "inclusion_ratio",
    "lat_mean_s", "lat_median_s", "lat_p95_s", "cpu_pct", "ram_mb",
    "blocks_total", "ours_per_block_mean", "ext_bytes_mean", "len_used_pct_of_normal",
    "weight_est_pct_of_normal", "build_ms_per_tx", "blocks_hit_deadline_frac",
    "pool_ready_max", "pool_bytes_frac_max",
]


def write_csv(path, rows, fields=None):
    if not rows:
        return
    if fields is None:
        fields = []
        for r in rows:
            for k in r:
                if k not in fields:
                    fields.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logdir", required=True)
    ap.add_argument("--out-prefix", default="wyniki_v3")
    args = ap.parse_args()

    metas = []
    for fn in sorted(glob.glob(os.path.join(args.logdir, "meta_*.json"))):
        with open(fn) as f:
            metas.append(json.load(f))

    runs, block_rows = [], []
    for m in metas:
        runs.append(summarize_run(args.logdir, m, block_rows))

    write_csv(f"{args.out_prefix}_runs.csv", runs)
    write_csv(f"{args.out_prefix}_blocks.csv", block_rows)

    groups = {}
    for r in runs:
        groups.setdefault((r["runtime"], r["algo"], r["users"]), []).append(r)
    summary = []
    for (runtime, algo, users), rs in sorted(groups.items()):
        row = {"runtime": runtime, "algo": algo, "users": users, "n_runs": len(rs)}
        for k in SUMMARY_METRICS:
            vals = [r[k] for r in rs if r[k] is not None]
            row[k + "_mean"] = mean(vals)
            row[k + "_sd"] = statistics.stdev(vals) if len(vals) >= 2 else 0.0 if vals else None
        summary.append(row)
    write_csv(f"{args.out_prefix}_summary.csv", summary)

    print(f"runow: {len(runs)}, wiersze blokow: {len(block_rows)}")
    for r in runs:
        print(f"{r['tag']}: TPS={r['tps_post_warmup']} req/s={r['request_rate']:.1f} "
              f"fail={r['fail_rate']} lat_med={r['lat_median_s']} inkl={r['inclusion_ratio']}")


if __name__ == "__main__":
    main()

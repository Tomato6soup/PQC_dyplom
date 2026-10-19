#!/usr/bin/env python3
"""
summarize_duration_to_csv.py - zbiera wyniki z logs_duration_sweep_v2/ w jeden CSV.
Parsuje sweep_{algo}_u{U}_d{dur}_run{run}.log (aggregated stats + error report),
tps_{algo}_u{U}_d{dur}_run{run}.log (TPS cale okno / po rozgrzewce),
res_{algo}_u{U}_d{dur}_run{run}.log (CPU/RAM mean).
"""
import csv
import glob
import os
import re
import statistics

LOGDIR = "logs_duration_sweep_v2"
OUT = os.path.join(LOGDIR, "wyniki_duration_sweep.csv")

name_re = re.compile(r"sweep_([a-z0-9]+)_u(\d+)_d(\d+)_run(\d+)\.log")

error_line_pattern = re.compile(
    r"^\s*(\d+)\s+RPC\s+\S+:\s*SubstrateRequestException\(\{.*?'message':\s*'([^']+)'.*?'data':\s*[\"']([^\"']+)[\"']"
)

def classify(msg, data):
    combined = f"{msg} {data}"
    if "Priority is too low" in msg:
        return "priority_too_low"
    if "couldn't enter the pool because of the limit" in data or msg == "Immediately Dropped":
        return "immediately_dropped"
    if "outdated" in combined.lower():
        return "outdated"
    return "other"

def parse_sweep_log(path):
    with open(path, errors="replace") as f:
        text = f.read()

    stats_line = None
    for line in text.splitlines():
        if "Response time percentiles" in line:
            break
        if "Aggregated" in line:
            stats_line = line

    reqs = fails = fail_pct = resp_avg = resp_median = None
    if stats_line:
        parts = stats_line.split("|")
        left = parts[0].split()
        reqs = int(left[-2])
        fails_match = re.match(r"(\d+)\(([\d.]+)%\)", left[-1])
        fails = int(fails_match.group(1))
        fail_pct = float(fails_match.group(2))
        mid = parts[1].split()
        resp_avg, _min, _max, resp_median = [int(x) for x in mid]

    err_counts = {"priority_too_low": 0, "immediately_dropped": 0, "outdated": 0, "other": 0}
    in_error_report = False
    for line in text.splitlines():
        if "Error report" in line:
            in_error_report = True
            continue
        if in_error_report:
            if line.strip().startswith("Type") or line.strip().startswith("#"):
                continue
            m = error_line_pattern.match(line)
            if m:
                count, msg, data = int(m.group(1)), m.group(2), m.group(3)
                cat = classify(msg, data)
                err_counts[cat] += count
            elif line.strip() == "" or line.strip().startswith("---"):
                if line.strip() == "":
                    in_error_report = False

    return reqs, fails, fail_pct, resp_avg, resp_median, err_counts

def parse_tps_log(path):
    tps_cale = tps_pw = None
    if not os.path.exists(path):
        return None, None
    with open(path, errors="replace") as f:
        for line in f:
            m1 = re.search(r"TPS \(nasze / czas trwania, CAŁE okno\):\s+([\d.]+)", line)
            if m1:
                tps_cale = float(m1.group(1))
            m2 = re.search(r"TPS \(nasze / rozpiętość PO rozgrzewce.*?:\s+([\d.]+)", line)
            if m2:
                tps_pw = float(m2.group(1))
    return tps_cale, tps_pw

def parse_res_log(path):
    if not os.path.exists(path):
        return None, None
    cpu_vals, ram_vals = [], []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                cpu_vals.append(float(row["cpu_pct"]))
            except (ValueError, KeyError):
                pass
            try:
                ram_vals.append(float(row["ram_mb"]))
            except (ValueError, KeyError):
                pass
    cpu_mean = round(statistics.mean(cpu_vals), 2) if cpu_vals else None
    ram_mean = round(statistics.mean(ram_vals), 1) if ram_vals else None
    return cpu_mean, ram_mean

rows_out = []
other_total = 0
mismatch_total = 0

for path in sorted(glob.glob(os.path.join(LOGDIR, "sweep_*.log"))):
    base = os.path.basename(path)
    m = name_re.match(base)
    if not m:
        print(f"UWAGA: nie rozpoznano nazwy pliku: {base}")
        continue
    algo, u, dur, run = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))

    reqs, fails, fail_pct, resp_avg, resp_median, err_counts = parse_sweep_log(path)

    tps_path = os.path.join(LOGDIR, f"tps_{algo}_u{u}_d{dur}_run{run}.log")
    tps_cale, tps_pw = parse_tps_log(tps_path)

    res_path = os.path.join(LOGDIR, f"res_{algo}_u{u}_d{dur}_run{run}.log")
    cpu_mean, ram_mean = parse_res_log(res_path)

    err_sum = sum(err_counts.values())
    if fails is not None and err_sum != fails:
        mismatch_total += 1
        print(f"UWAGA: {base} - suma rozbicia bledow ({err_sum}) != fails ({fails})")
    other_total += err_counts["other"]

    rows_out.append({
        "algo": algo, "U": u, "duration_s": dur, "run": run,
        "reqs": reqs, "fails": fails, "fail_pct": fail_pct,
        "resp_avg_ms": resp_avg, "resp_median_ms": resp_median,
        "fails_priority_too_low": err_counts["priority_too_low"],
        "fails_immediately_dropped": err_counts["immediately_dropped"],
        "fails_outdated": err_counts["outdated"],
        "fails_other": err_counts["other"],
        "tps_cale_okno": tps_cale, "tps_po_rozgrzewce": tps_pw,
        "cpu_mean_pct": cpu_mean, "ram_mean_mb": ram_mean,
    })

rows_out.sort(key=lambda r: (r["algo"], r["U"], r["duration_s"], r["run"]))

fieldnames = ["algo","U","duration_s","run","reqs","fails","fail_pct","resp_avg_ms","resp_median_ms",
              "fails_priority_too_low","fails_immediately_dropped","fails_outdated","fails_other",
              "tps_cale_okno","tps_po_rozgrzewce","cpu_mean_pct","ram_mean_mb"]

with open(OUT, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows_out)

print(f"\nZapisano {len(rows_out)} wierszy do {os.path.abspath(OUT)}")
if other_total == 0:
    print("Brak bledow w kategorii 'other' - wszystko sklasyfikowane.")
else:
    print(f"UWAGA: {other_total} bledow w kategorii 'other' - sprawdz recznie.")
if mismatch_total == 0:
    print("Weryfikacja OK: suma rozbicia bledow zgadza sie z 'fails' w kazdym wierszu.")
else:
    print(f"UWAGA: {mismatch_total} wierszy z niezgodna suma rozbicia bledow.")

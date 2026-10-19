#!/usr/bin/env python3
"""Zbiera wyniki ze wszystkich logow w logs/ do jednej tabeli CSV.
v2: dodatkowo rozbija bledy na typy (Priority is too low / Immediately Dropped /
Transaction is outdated / inne), parsujac sekcje 'Error report' z logu locusta.
Klasyfikacja patrzy na POLA 'message' ORAZ 'data' - np. kod 1010 ma
message='Invalid Transaction' ale prawdziwa przyczyna jest w data='Transaction is outdated'."""
import re
import glob
import os
import csv

base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
pattern = re.compile(
    r"^\s*Aggregated\s+(\d+)\s+(\d+)\(([\d.]+)%\)\s*\|\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\|\s*([\d.]+)\s+([\d.]+)"
)
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


def parse_error_report(lines, start_idx):
    counts = {"priority_too_low": 0, "immediately_dropped": 0, "outdated": 0, "other": 0}
    other_messages = []
    for line in lines[start_idx:]:
        if line.strip().startswith("---"):
            continue
        if line.strip().startswith("#") or not line.strip():
            continue
        m = error_line_pattern.match(line)
        if not m:
            break
        occurrences, msg, data = m.groups()
        cat = classify(msg, data)
        counts[cat] += int(occurrences)
        if cat == "other":
            other_messages.append((int(occurrences), msg, data))
    return counts, other_messages


rows = []
all_other_messages = []
for f in sorted(glob.glob(os.path.join(base, "sweep_*_u*_run*.log"))):
    name = os.path.basename(f)
    m = re.match(r"sweep_(\w+)_u(\d+)_run(\d+)\.log", name)
    if not m:
        continue
    algo, u, run = m.group(1), int(m.group(2)), int(m.group(3))

    with open(f, errors="replace") as fh:
        lines = fh.readlines()

    last = None
    error_counts = {"priority_too_low": 0, "immediately_dropped": 0, "outdated": 0, "other": 0}
    for i, line in enumerate(lines):
        mm = pattern.match(line)
        if mm:
            last = mm
        if line.strip() == "Error report":
            error_counts, other_msgs = parse_error_report(lines, i + 1)
            for occ, msg, data in other_msgs:
                all_other_messages.append((algo, u, run, occ, msg, data))

    if last is None:
        rows.append((algo, u, run, "", "", "", "", "", 0, 0, 0, 0, "", ""))
        continue
    reqs, fails, failpct, avg, mn, mx, med, reqs_s, fails_s = last.groups()

    tpsfile = os.path.join(base, f"tps_{algo}_u{u}_run{run}.log")
    tps_whole, tps_post = "", ""
    if os.path.exists(tpsfile):
        content = open(tpsfile, errors="replace").read()
        mw = re.search(r"CAŁE okno\):\s*([\d.]+)", content)
        mp = re.search(r"PO rozgrzewce.*?:\s*([\d.]+)", content)
        if mw: tps_whole = mw.group(1)
        if mp: tps_post = mp.group(1)

    rows.append((
        algo, u, run, reqs, fails, failpct, avg, med,
        error_counts["priority_too_low"], error_counts["immediately_dropped"],
        error_counts["outdated"], error_counts["other"],
        tps_whole, tps_post,
    ))

out_path = os.path.join(base, "wyniki_sweep_v2.csv")
with open(out_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["algo", "U", "run", "reqs", "fails", "fail_pct",
                "resp_avg_ms", "resp_median_ms",
                "fails_priority_too_low", "fails_immediately_dropped",
                "fails_outdated", "fails_other",
                "tps_cale_okno", "tps_po_rozgrzewce"])
    for r in rows:
        w.writerow(r)

print(f"Zapisano {len(rows)} wierszy do {out_path}")

if all_other_messages:
    print("\nSzczegoly bledow sklasyfikowanych jako 'other':")
    for algo, u, run, occ, msg, data in all_other_messages:
        print(f"  {algo} U={u} run={run}: {occ}x message='{msg}' data='{data}'")
else:
    print("\nBrak bledow w kategorii 'other' - wszystko sklasyfikowane.")

mismatches = 0
for algo, u, run, reqs, fails, failpct, avg, med, ptl, idp, out, oth, tw, tp in rows:
    if fails == "":
        continue
    total_classified = ptl + idp + out + oth
    if int(fails) != total_classified:
        mismatches += 1
        print(f"  UWAGA: {algo} U={u} run={run}: fails={fails} ale suma rozbicia={total_classified}")
if mismatches == 0:
    print("\nWeryfikacja OK: suma rozbicia bledow zgadza sie z 'fails' w kazdym wierszu.")
else:
    print(f"\nWeryfikacja: {mismatches} wiersz(y) z niezgodnoscia - zobacz uwagi wyzej.")

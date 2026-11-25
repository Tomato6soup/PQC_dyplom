import csv, os, subprocess, sys

UZYTKOWNICY = [1, 10, 100]
ROZMIARY = [1, 2, 5, 10, 20, 50]
ALGO = ["ecdsa", "dilithium2", "sphincs"]
FOLDER = "batch_size_v2"
SZCZEGOLY = os.path.join(FOLDER, "szczegoly")
os.makedirs(SZCZEGOLY, exist_ok=True)

for u in UZYTKOWNICY:
    for b in ROZMIARY:
        katalog = "logs_batchc_U" + str(u) + "_B" + str(b)
        n = len([f for f in os.listdir(katalog) if f.startswith("meta_")])
        if n != 3:
            sys.exit("BLAD: " + katalog + " ma " + str(n) + " przebiegow zamiast 3")
        subprocess.run([sys.executable, "summarize_v3.py", "--logdir", katalog,
                        "--out-prefix", "wyniki_batchc_U" + str(u) + "_B" + str(b)],
                       check=True, stdout=subprocess.DEVNULL)
print("katalogow z logami: 18, w kazdym 3 przebiegi, OK")

def polacz(typ):
    wiersze = []
    pola = None
    for u in UZYTKOWNICY:
        for b in ROZMIARY:
            plik = "wyniki_batchc_U" + str(u) + "_B" + str(b) + "_" + typ + ".csv"
            with open(plik, newline="") as f:
                r = csv.DictReader(f)
                pola = r.fieldnames
                for x in r:
                    x["batch_size"] = b
                    x["pauza"] = "stala_0.05s"
                    wiersze.append(x)
    wiersze.sort(key=lambda x: (ALGO.index(x["algo"]), int(x["users"]), x["batch_size"], int(x.get("run", 0) or 0)))
    wyj = os.path.join(FOLDER, "wyniki_batchc_" + ("przebiegi" if typ == "runs" else "podsumowanie") + ".csv")
    with open(wyj, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["pauza", "batch_size"] + pola)
        w.writeheader()
        w.writerows(wiersze)
    print(wyj, len(wiersze), "wierszy")
    return wiersze

runs = polacz("runs")
summ = polacz("summary")

for u in UZYTKOWNICY:
    for b in ROZMIARY:
        for typ in ["runs", "summary", "blocks"]:
            nazwa = "wyniki_batchc_U" + str(u) + "_B" + str(b) + "_" + typ + ".csv"
            os.replace(nazwa, os.path.join(SZCZEGOLY, nazwa))

print("fail_rate max:", max(float(x["fail_rate"]) for x in runs))
print("powtorzen w podsumowaniu:", sorted(set(x["n_runs"] for x in summ)))

def liczba(x, k):
    return round(float(x[k]), 2) if x[k] not in ("", None) else "n/d"

print()
print("podpis      U   B    tps     tx/s    inkl   lat_med  przeciazenie")
for x in summ:
    tps = float(x["tps_post_warmup_mean"])
    wys = float(x["request_rate_mean"])
    print(x["algo"].ljust(10), x["users"].rjust(3), str(x["batch_size"]).rjust(3), liczba(x, "tps_post_warmup_mean"),
          liczba(x, "request_rate_mean"), liczba(x, "inclusion_ratio_mean"),
          liczba(x, "lat_median_s_mean"), "TAK" if tps / wys < 0.95 else "nie")

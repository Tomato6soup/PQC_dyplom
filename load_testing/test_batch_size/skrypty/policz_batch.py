# Liczy wyniki serii batch_size (6 rozmiarow) i laczy je w dwa pliki w folderze test_batch_size
import csv, os, subprocess, sys

ROZMIARY = [1, 2, 5, 10, 20, 50]
ALGO = ["ecdsa", "dilithium2", "sphincs"]
FOLDER = "test_batch_size"
os.makedirs(FOLDER, exist_ok=True)

for b in ROZMIARY:
    katalog = "logs_batch_B" + str(b)
    n = len([f for f in os.listdir(katalog) if f.startswith("meta_")])
    print("batch", b, ": gotowych przebiegow", n, "(powinno byc 15)")
    if n != 15:
        sys.exit("BLAD: niepelny katalog " + katalog)
    subprocess.run([sys.executable, "summarize_v3.py", "--logdir", katalog,
                    "--out-prefix", "wyniki_batch_B" + str(b)],
                   check=True, stdout=subprocess.DEVNULL)

def polacz(typ):
    wiersze = []
    pola = None
    for b in ROZMIARY:
        plik = "wyniki_batch_B" + str(b) + "_" + typ + ".csv"
        with open(plik, newline="") as f:
            r = csv.DictReader(f)
            pola = r.fieldnames
            for x in r:
                x["batch_size"] = b
                wiersze.append(x)
    wiersze.sort(key=lambda x: (ALGO.index(x["algo"]), x["batch_size"], int(x.get("run", 0) or 0)))
    wyj = os.path.join(FOLDER, "wyniki_batch_" + ("przebiegi" if typ == "runs" else "podsumowanie") + ".csv")
    with open(wyj, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["batch_size"] + pola)
        w.writeheader()
        w.writerows(wiersze)
    print(wyj, len(wiersze), "wierszy")
    return wiersze

runs = polacz("runs")
summ = polacz("summary")

for b in ROZMIARY:
    for typ in ["runs", "summary", "blocks"]:
        os.replace("wyniki_batch_B" + str(b) + "_" + typ + ".csv",
                   os.path.join(FOLDER, "wyniki_batch_B" + str(b) + "_" + typ + ".csv"))

print("fail_rate max (powinno byc 0):", max(float(x["fail_rate"]) for x in runs))
print("powtorzen w podsumowaniu (powinno byc 5):", sorted(set(x["n_runs"] for x in summ)))

def liczba(x, k):
    return round(float(x[k]), 3) if x[k] != "" else "n/d"

print()
print("podpis      B   tps    req/s  inkl   lat_med  p95")
for x in summ:
    print(x["algo"].ljust(10), str(x["batch_size"]).rjust(3), liczba(x, "tps_post_warmup_mean"),
          liczba(x, "request_rate_mean"), liczba(x, "inclusion_ratio_mean"),
          liczba(x, "lat_median_s_mean"), liczba(x, "lat_p95_s_mean"))

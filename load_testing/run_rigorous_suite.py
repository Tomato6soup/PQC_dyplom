import subprocess
import time
import requests
import pandas as pd
import numpy as np
import os
import csv
import math
import matplotlib.pyplot as plt

RESULTS_DIR = os.path.expanduser("~/PQC_dyplom/load_testing/results")
CHARTS_DIR = os.path.expanduser("~/PQC_dyplom/Wykresy")
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(CHARTS_DIR, exist_ok=True)

PROMETHEUS_URL = "http://localhost:9090/api/v1/query"
RPC_URL = "http://127.0.0.1:9944"

scenarios = [
    {"users": 10, "rate": 2, "label": "Niski"},
    {"users": 50, "rate": 10, "label": "Sredni-1"},
    {"users": 100, "rate": 20, "label": "Sredni-2"},
    {"users": 150, "rate": 25, "label": "Szczyt"},
    {"users": 200, "rate": 35, "label": "Przejsciowy"},
    {"users": 300, "rate": 50, "label": "Nasycenie"},
    {"users": 400, "rate": 55, "label": "Przeciazenie-1"},
    {"users": 500, "rate": 65, "label": "Przeciazenie-2"},
    {"users": 600, "rate": 75, "label": "Przeciazenie-3"}
]

algorithms = ["ecdsa", "dilithium2", "sphincs"]
tx_crypto_size = {"ecdsa": 96, "dilithium2": 3732, "sphincs": 17120}
crypto_verify_time_ms = {"ecdsa": 0.06, "dilithium2": 0.04, "sphincs": 1.25}

DURATION_CONFIGS = [
    {"duration": "30s", "duration_s": 30, "repeats": 5},
    {"duration": "60s", "duration_s": 60, "repeats": 5},
    {"duration": "90s", "duration_s": 90, "repeats": 5},
]
PRIMARY_DURATION_S = 60

NETWORK_SCALING_COEFF = 0.08


def get_metric(query):
    try:
        r = requests.get(PROMETHEUS_URL, params={"query": query}, timeout=5)
        data = r.json()
        if data["status"] == "success" and data["data"]["result"]:
            return float(data["data"]["result"][0]["value"][1])
    except Exception:
        pass
    return 0.0


def rpc_call(method, params=None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
    try:
        r = requests.post(RPC_URL, json=payload, timeout=5)
        result = r.json()
        return result.get("result")
    except Exception:
        return None


def get_finalized_block_number():
    finalized_hash = rpc_call("chain_getFinalizedHead")
    if not finalized_hash:
        return None
    header = rpc_call("chain_getHeader", [finalized_hash])
    if not header or "number" not in header:
        return None
    try:
        return int(header["number"], 16)
    except (TypeError, ValueError):
        return None


def get_best_block_number():
    best_hash = rpc_call("chain_getBlockHash")
    if not best_hash:
        header = rpc_call("chain_getHeader")
    else:
        header = rpc_call("chain_getHeader", [best_hash])
    if not header or "number" not in header:
        return None
    try:
        return int(header["number"], 16)
    except (TypeError, ValueError):
        return None


def count_extrinsics_in_block(block_number, exclude_inherents=True):
    block_hash = rpc_call("chain_getBlockHash", [block_number])
    if not block_hash:
        return 0
    block = rpc_call("chain_getBlock", [block_hash])
    if not block:
        return 0
    extrinsics = block.get("block", {}).get("extrinsics", [])
    if not exclude_inherents:
        return len(extrinsics)
    return max(0, len(extrinsics) - 1)  # -1: pomija obowiazkowy inherent Timestamp.set


def wait_for_pool_drain(max_wait_s=30, poll_interval_s=1.0, stable_checks=3):
    stable = 0
    waited = 0.0
    while waited < max_wait_s:
        pending = rpc_call("author_pendingExtrinsics", [])
        if pending is not None and len(pending) == 0:
            stable += 1
            if stable >= stable_checks:
                return True
        else:
            stable = 0
        time.sleep(poll_interval_s)
        waited += poll_interval_s
    return False


def wait_for_finality_catchup(max_wait_s=90, poll_interval_s=0.5):
    waited = 0.0
    while waited < max_wait_s:
        best_num = get_best_block_number()
        finalized = get_finalized_block_number()
        if best_num is not None and finalized is not None:
            if best_num - finalized <= 1:
                return True
        time.sleep(poll_interval_s)
        waited += poll_interval_s
    return False


def measure_chain_tps(start_block, end_block, elapsed_s):
    if start_block is None or end_block is None:
        return 0.0
    if end_block <= start_block or elapsed_s <= 0:
        return 0.0
    total_extrinsics = 0
    for b in range(start_block + 1, end_block + 1):
        total_extrinsics += count_extrinsics_in_block(b)
    return total_extrinsics / elapsed_s


RAW_CSV_PATH = os.path.join(RESULTS_DIR, "surowe_proby_pelne.csv")
RAW_CSV_FIELDS = [
    "Algorytm", "Uzytkownicy", "Poziom", "Czas_testu_s", "Powtorzenie",
    "RPS", "TPS", "Mediana_ms", "P95_ms", "P99_ms", "CPU_%", "RAM_MB", "Failures"
]

if os.path.exists(RAW_CSV_PATH):
    print(f"UWAGA: {RAW_CSV_PATH} juz istnieje - nowe wyniki beda DOPISYWANE do niego.")
    print("Jesli chcesz zaczac zupelnie od zera, usun ten plik przed uruchomieniem skryptu.")


def append_raw_record(record):
    file_exists = os.path.exists(RAW_CSV_PATH)
    with open(RAW_CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(record)
        f.flush()
        os.fsync(f.fileno())


raw_records = []

total_runs = sum(
    len(algorithms) * len(scenarios) * dc["repeats"] for dc in DURATION_CONFIGS
)
print(f"=== ETAP 1: TESTY OBCIAZENIOWE WEZLA RPC ({total_runs} PRZEBIEGOW LACZNIE) ===")
print("Warianty czasu trwania: " + ", ".join(
    f"{dc['duration']} (k={dc['repeats']})" for dc in DURATION_CONFIGS
))
print(f"Wyniki kazdego przebiegu beda dopisywane na biezaco do: {RAW_CSV_PATH}")
current_run = 0

for algo in algorithms:
    for sc in scenarios:
        u = sc["users"]
        r = sc["rate"]
        lbl = sc["label"]

        for dc in DURATION_CONFIGS:
            test_duration = dc["duration"]
            test_duration_s = dc["duration_s"]
            repeats = dc["repeats"]

            for rep in range(1, repeats + 1):
                current_run += 1
                prefix = os.path.join(
                    RESULTS_DIR, f"tmp_{algo}_u{u}_t{test_duration_s}_rep{rep}"
                )
                print(f"[{current_run}/{total_runs}] Algo: {algo:10s} | U={u:3d} ({lbl}) | "
                      f"T={test_duration:4s} | Proba {rep}/{repeats}")

                cmd = [
                    "locust", "-f", "locustfile.py",
                    "--headless", "-u", str(u), "-r", str(r),
                    "-t", test_duration, "--host", RPC_URL,
                    f"--csv={prefix}"
                ]
                env = os.environ.copy()
                env["TEST_ALGO"] = algo

                start_block = get_finalized_block_number()
                t_start = time.time()

                subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                t_end = time.time()

                wait_for_pool_drain()
                wait_for_finality_catchup()

                end_block = get_finalized_block_number()
                chain_tps = measure_chain_tps(start_block, end_block, t_end - t_start)

                time.sleep(1)
                cpu = get_metric('100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[60s])) * 100)')
                ram = get_metric('(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / (1024 * 1024)')

                stats_file = f"{prefix}_stats.csv"
                if os.path.exists(stats_file):
                    df_stat = pd.read_csv(stats_file)
                    agg = df_stat[df_stat["Name"] == "Aggregated"].iloc[0]
                    record = {
                        "Algorytm": algo,
                        "Uzytkownicy": u,
                        "Poziom": lbl,
                        "Czas_testu_s": test_duration_s,
                        "Powtorzenie": rep,
                        "RPS": float(agg["Requests/s"]),
                        "TPS": chain_tps,
                        "Mediana_ms": float(agg["50%"]),
                        "P95_ms": float(agg["95%"]),
                        "P99_ms": float(agg["99%"]),
                        "CPU_%": cpu,
                        "RAM_MB": ram,
                        "Failures": int(agg["Failure Count"])
                    }
                    raw_records.append(record)
                    append_raw_record(record)
                time.sleep(2)

df_raw = pd.read_csv(RAW_CSV_PATH)

summary_rows = []
for (algo, u, t_s), grp in df_raw.groupby(["Algorytm", "Uzytkownicy", "Czas_testu_s"], sort=False):
    summary_rows.append({
        "Algorytm": algo,
        "Uzytkownicy": u,
        "Czas_testu_s": t_s,
        "Liczba_probek": len(grp),
        "RPS_mean": grp["RPS"].mean(),
        "RPS_std": grp["RPS"].std(),
        "RPS_median": grp["RPS"].median(),
        "TPS_mean": grp["TPS"].mean(),
        "TPS_std": grp["TPS"].std(),
        "TPS_median": grp["TPS"].median(),
        "Mediana_ms_mean": grp["Mediana_ms"].mean(),
        "Mediana_ms_std": grp["Mediana_ms"].std(),
        "P95_ms_mean": grp["P95_ms"].mean(),
        "P95_ms_std": grp["P95_ms"].std(),
        "P99_ms_mean": grp["P99_ms"].mean(),
        "P99_ms_std": grp["P99_ms"].std(),
        "CPU_mean": grp["CPU_%"].mean(),
        "CPU_std": grp["CPU_%"].std(),
        "RAM_mean": grp["RAM_MB"].mean(),
        "RAM_std": grp["RAM_MB"].std(),
        "Failures_total": grp["Failures"].sum()
    })

df_summary = pd.DataFrame(summary_rows)
summary_csv = os.path.join(RESULTS_DIR, "obciazenie_statystyka_pelna.csv")
df_summary.to_csv(summary_csv, index=False)
print(f"\nZapisano zagregowane wyniki (wszystkie warianty czasu trwania) do: {summary_csv}")

df_summary_primary = df_summary[df_summary["Czas_testu_s"] == PRIMARY_DURATION_S]

print("\n=== ETAP 2: MODEL SKALOWALNOSCI P2P DLA DUZYCH SIECI ===")
node_counts = [500, 1000, 1500, 2000, 3000, 4000]
sim_rows = []

df_u150 = df_summary_primary[df_summary_primary["Uzytkownicy"] == 150]

for _, row in df_u150.iterrows():
    algo = row["Algorytm"]
    base_tps = row["TPS_mean"]
    base_lat_sec = row["Mediana_ms_mean"] / 1000.0
    msg_size = 200 + tx_crypto_size[algo]
    t_verify_s = crypto_verify_time_ms[algo] / 1000.0

    for n in node_counts:
        path_length = math.log(n, 8)
        hop_latency = (msg_size / (50 * 1024 * 1024 / 8)) + 0.050 + t_verify_s
        contention_factor = 1.0 + (0.015 * math.sqrt(n) * (msg_size / 4000.0))
        network_scaling_factor = 1.0 + NETWORK_SCALING_COEFF * math.log2(n / node_counts[0])

        total_p2p_lat_sec = path_length * hop_latency * contention_factor * network_scaling_factor
        total_e2e_lat_ms = (base_lat_sec + total_p2p_lat_sec) * 1000.0

        tps_degradation = 1.0 / (
            1.0
            + path_length * (msg_size / 75000.0)
            + 0.0002 * n * t_verify_s * 1000
            + (network_scaling_factor - 1.0) * 2.0
        )
        effective_tps = base_tps * tps_degradation

        sim_rows.append({
            "Algorytm": algo,
            "Wezly": n,
            "Base_TPS": round(base_tps, 4),
            "Efektywny_TPS": round(effective_tps, 4),
            "Calkowite_Opoznienie_ms": round(total_e2e_lat_ms, 2)
        })

df_sim = pd.DataFrame(sim_rows)
sim_csv = os.path.join(RESULTS_DIR, "symulacja_duzej_sieci.csv")
df_sim.to_csv(sim_csv, index=False)

print("\n=== ETAP 3: GENEROWANIE WYKRESOW PUBLIKACYJNYCH ===")
algo_meta = {
    "ecdsa": {"name": "ECDSA (secp256k1)", "color": "#2ca02c", "marker": "o"},
    "dilithium2": {"name": "Dilithium2 (ML-DSA-44)", "color": "#1f77b4", "marker": "s"},
    "sphincs": {"name": "SPHINCS+-128f (SLH-DSA)", "color": "#d62728", "marker": "^"}
}
all_users = [sc["users"] for sc in scenarios]

plt.figure(figsize=(9, 5.5))
for a in algorithms:
    sub = df_summary_primary[df_summary_primary["Algorytm"] == a]
    plt.errorbar(sub["Uzytkownicy"], sub["RPS_mean"], yerr=sub["RPS_std"],
                 label=algo_meta[a]["name"], color=algo_meta[a]["color"],
                 marker=algo_meta[a]["marker"], capsize=4, lw=2, markersize=6)
plt.title(f"Przepustowosc zadan RPC (RPS) w funkcji obciazenia (T={PRIMARY_DURATION_S}s, $\\pm 1\\sigma$)", fontsize=11, pad=10)
plt.xlabel("Liczba wspolbieznych uzytkownikow (Locust)", fontsize=10)
plt.ylabel("Przepustowosc zadan HTTP (RPS)", fontsize=10)
plt.xticks(all_users)
plt.grid(True, ls="--", alpha=0.5)
plt.legend(frameon=True)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, "wykres_rps_zagesszczony.png"), dpi=300)
plt.close()

plt.figure(figsize=(9, 5.5))
for a in algorithms:
    sub = df_summary_primary[df_summary_primary["Algorytm"] == a]
    plt.errorbar(sub["Uzytkownicy"], sub["TPS_mean"], yerr=sub["TPS_std"],
                 label=algo_meta[a]["name"], color=algo_meta[a]["color"],
                 marker=algo_meta[a]["marker"], capsize=4, lw=2, markersize=6)
plt.title(f"Przepustowosc potwierdzonych transakcji (TPS) w funkcji obciazenia (T={PRIMARY_DURATION_S}s, $\\pm 1\\sigma$)", fontsize=11, pad=10)
plt.xlabel("Liczba wspolbieznych uzytkownikow (Locust)", fontsize=10)
plt.ylabel("Przepustowosc lancucha (TPS)", fontsize=10)
plt.xticks(all_users)
plt.grid(True, ls="--", alpha=0.5)
plt.legend(frameon=True)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, "wykres_tps_zagesszczony.png"), dpi=300)
plt.close()

plt.figure(figsize=(9, 5.5))
for a in algorithms:
    sub = df_summary_primary[df_summary_primary["Algorytm"] == a]
    plt.plot(sub["Uzytkownicy"], sub["Mediana_ms_mean"], color=algo_meta[a]["color"],
              marker=algo_meta[a]["marker"], lw=2, label=f"{algo_meta[a]['name']} (Mediana)")
    plt.plot(sub["Uzytkownicy"], sub["P95_ms_mean"], color=algo_meta[a]["color"],
              ls="--", lw=1.5, alpha=0.8, label=f"{algo_meta[a]['name']} (P95)")
    plt.plot(sub["Uzytkownicy"], sub["P99_ms_mean"], color=algo_meta[a]["color"],
              ls=":", lw=1.5, alpha=0.7, label=f"{algo_meta[a]['name']} (P99)")
plt.title(f"Opoznienia odpowiedzi RPC (Mediana vs P95 vs P99) w funkcji obciazenia (T={PRIMARY_DURATION_S}s)", fontsize=11, pad=10)
plt.xlabel("Liczba wspolbieznych uzytkownikow", fontsize=10)
plt.ylabel("Czas odpowiedzi (ms)", fontsize=10)
plt.xticks(all_users)
plt.grid(True, ls="--", alpha=0.5)
plt.legend(fontsize=7, frameon=True, ncol=1)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, "wykres_opoznienia_zagesszczony.png"), dpi=300)
plt.close()

fig, ax1 = plt.subplots(figsize=(9, 5.5))
ax2 = ax1.twinx()
for a in algorithms:
    sub = df_summary_primary[df_summary_primary["Algorytm"] == a]
    ax1.plot(sub["Uzytkownicy"], sub["CPU_mean"], color=algo_meta[a]["color"],
              marker=algo_meta[a]["marker"], lw=2, label=f"CPU - {algo_meta[a]['name']}")
    ax2.plot(sub["Uzytkownicy"], sub["RAM_mean"], color=algo_meta[a]["color"],
              marker=algo_meta[a]["marker"], ls="--", lw=1.5, alpha=0.7)

ax1.set_xlabel("Liczba wspolbieznych uzytkownikow", fontsize=10)
ax1.set_ylabel("Utylizacja CPU (%) [Linie ciagle]", fontsize=10)
ax2.set_ylabel("Alokacja RAM (MB) [Linie przerywane]", fontsize=10)
ax1.set_xticks(all_users)
ax1.grid(True, ls="--", alpha=0.5)
ax1.set_title(f"Utylizacja CPU i RAM w funkcji obciazenia (T={PRIMARY_DURATION_S}s)", fontsize=11, pad=10)
ax1.legend(loc="upper left", fontsize=8)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, "wykres_zasoby_cpu_ram.png"), dpi=300)
plt.close()

plt.figure(figsize=(9, 5.5))
for a in algorithms:
    sub = df_sim[df_sim["Algorytm"] == a]
    plt.plot(sub["Wezly"], sub["Efektywny_TPS"], color=algo_meta[a]["color"],
              marker=algo_meta[a]["marker"], lw=2, label=algo_meta[a]["name"])
plt.title("Efektywny TPS w funkcji skali sieci P2P (500-4000 wezlow, U=150)", fontsize=11, pad=10)
plt.xlabel("Liczba aktywnych wezlow w sieci", fontsize=10)
plt.ylabel("Efektywny TPS", fontsize=10)
plt.xticks(node_counts)
plt.grid(True, ls="--", alpha=0.5)
plt.legend(frameon=True)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, "wykres_tps_vs_wezly_poprawiony.png"), dpi=300)
plt.close()

plt.figure(figsize=(9, 5.5))
for a in algorithms:
    sub = df_sim[df_sim["Algorytm"] == a]
    plt.plot(sub["Wezly"], sub["Calkowite_Opoznienie_ms"], color=algo_meta[a]["color"],
              marker=algo_meta[a]["marker"], lw=2, label=algo_meta[a]["name"])
plt.title("Calkowite opoznienie propagacji P2P vs Liczba wezlow (U=150)", fontsize=11, pad=10)
plt.xlabel("Liczba aktywnych wezlow w sieci", fontsize=10)
plt.ylabel("Opoznienie dotarcia i weryfikacji (ms)", fontsize=10)
plt.xticks(node_counts)
plt.grid(True, ls="--", alpha=0.5)
plt.legend(frameon=True)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, "wykres_opoznienie_vs_wezly_poprawiony.png"), dpi=300)
plt.close()

duration_values = sorted(df_summary["Czas_testu_s"].unique())
for ref_u in [150, 600]:
    if ref_u not in all_users:
        continue

    plt.figure(figsize=(9, 5.5))
    for a in algorithms:
        sub = df_summary[(df_summary["Algorytm"] == a) & (df_summary["Uzytkownicy"] == ref_u)]
        sub = sub.sort_values("Czas_testu_s")
        if sub.empty:
            continue
        plt.errorbar(sub["Czas_testu_s"], sub["TPS_mean"], yerr=sub["TPS_std"],
                     label=algo_meta[a]["name"], color=algo_meta[a]["color"],
                     marker=algo_meta[a]["marker"], capsize=4, lw=2, markersize=6)
    plt.title(f"Wplyw czasu trwania testu na TPS (U={ref_u}, $\\pm 1\\sigma$)", fontsize=11, pad=10)
    plt.xlabel("Czas trwania pojedynczego testu (s)", fontsize=10)
    plt.ylabel("Przepustowosc lancucha (TPS)", fontsize=10)
    plt.xticks(duration_values)
    plt.grid(True, ls="--", alpha=0.5)
    plt.legend(frameon=True)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, f"wykres_tps_vs_czas_trwania_u{ref_u}.png"), dpi=300)
    plt.close()

    plt.figure(figsize=(9, 5.5))
    for a in algorithms:
        sub = df_summary[(df_summary["Algorytm"] == a) & (df_summary["Uzytkownicy"] == ref_u)]
        sub = sub.sort_values("Czas_testu_s")
        if sub.empty:
            continue
        plt.errorbar(sub["Czas_testu_s"], sub["Mediana_ms_mean"], yerr=sub["Mediana_ms_std"],
                     label=algo_meta[a]["name"], color=algo_meta[a]["color"],
                     marker=algo_meta[a]["marker"], capsize=4, lw=2, markersize=6)
    plt.title(f"Wplyw czasu trwania testu na mediane opoznienia (U={ref_u}, $\\pm 1\\sigma$)", fontsize=11, pad=10)
    plt.xlabel("Czas trwania pojedynczego testu (s)", fontsize=10)
    plt.ylabel("Mediana czasu odpowiedzi (ms)", fontsize=10)
    plt.xticks(duration_values)
    plt.grid(True, ls="--", alpha=0.5)
    plt.legend(frameon=True)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, f"wykres_opoznienia_vs_czas_trwania_u{ref_u}.png"), dpi=300)
    plt.close()

print("\nWSZYSTKIE TESTY ZAKONCZONE. WYKRESY I STATYSTYKI ZAKTUALIZOWANE.")

import pandas as pd
import math
import os
import matplotlib.pyplot as plt

RESULTS_DIR = os.path.expanduser("~/PQC_dyplom/load_testing/results")
CHARTS_DIR = os.path.expanduser("~/PQC_dyplom/Wykresy")
os.makedirs(CHARTS_DIR, exist_ok=True)

RAW_CSV_PATH = os.path.join(RESULTS_DIR, "surowe_proby_pelne.csv")

scenarios = [
    {"users": 10, "rate": 2, "label": "Niski"},
    {"users": 50, "rate": 10, "label": "Sredni-1"},
    {"users": 100, "rate": 20, "label": "Sredni-2"},
    {"users": 200, "rate": 35, "label": "Przejsciowy"},
    {"users": 300, "rate": 50, "label": "Nasycenie"},
    {"users": 400, "rate": 55, "label": "Przeciazenie-1"},
    {"users": 500, "rate": 65, "label": "Przeciazenie-2"},
    {"users": 600, "rate": 75, "label": "Przeciazenie-3"}
]
algorithms = ["ecdsa", "dilithium2", "sphincs"]
tx_crypto_size = {"ecdsa": 96, "dilithium2": 3732, "sphincs": 17120}
crypto_verify_time_ms = {"ecdsa": 0.06, "dilithium2": 0.04, "sphincs": 1.25}
PRIMARY_DURATION_S = 60
NETWORK_SCALING_COEFF = 0.08
SIM_BASE_USERS = 100

if not os.path.exists(RAW_CSV_PATH):
    print(f"BLAD: nie znaleziono {RAW_CSV_PATH}")
    raise SystemExit(1)

df_raw = pd.read_csv(RAW_CSV_PATH)

print("=== SPRAWDZENIE KOMPLETNOSCI DANYCH ===")
expected = len(algorithms) * len(scenarios) * 3 * 5
print(f"Oczekiwane wiersze: {expected}, faktyczne: {len(df_raw)}")
for algo in algorithms:
    n = len(df_raw[df_raw["Algorytm"] == algo])
    print(f"  {algo}: {n} wierszy")
failures = df_raw[df_raw["Failures"] > 0]
if len(failures) > 0:
    print(f"\nUWAGA: {len(failures)} wierszy z Failures > 0:")
    print(failures[["Algorytm", "Uzytkownicy", "Czas_testu_s", "Powtorzenie", "Failures"]].to_string(index=False))

summary_rows = []
for (algo, u, t_s), grp in df_raw.groupby(["Algorytm", "Uzytkownicy", "Czas_testu_s"], sort=False):
    summary_rows.append({
        "Algorytm": algo, "Uzytkownicy": u, "Czas_testu_s": t_s,
        "Liczba_probek": len(grp),
        "RPS_mean": grp["RPS"].mean(), "RPS_std": grp["RPS"].std(), "RPS_median": grp["RPS"].median(),
        "TPS_mean": grp["TPS"].mean(), "TPS_std": grp["TPS"].std(), "TPS_median": grp["TPS"].median(),
        "Mediana_ms_mean": grp["Mediana_ms"].mean(), "Mediana_ms_std": grp["Mediana_ms"].std(),
        "P95_ms_mean": grp["P95_ms"].mean(), "P95_ms_std": grp["P95_ms"].std(),
        "P99_ms_mean": grp["P99_ms"].mean(), "P99_ms_std": grp["P99_ms"].std(),
        "CPU_mean": grp["CPU_%"].mean(), "CPU_std": grp["CPU_%"].std(),
        "RAM_mean": grp["RAM_MB"].mean(), "RAM_std": grp["RAM_MB"].std(),
        "Failures_total": grp["Failures"].sum()
    })

df_summary = pd.DataFrame(summary_rows)
summary_csv = os.path.join(RESULTS_DIR, "obciazenie_statystyka_pelna.csv")
df_summary.to_csv(summary_csv, index=False)
print(f"\nZapisano: {summary_csv}")

df_summary_primary = df_summary[df_summary["Czas_testu_s"] == PRIMARY_DURATION_S]

node_counts = [500, 1000, 1500, 2000, 3000, 4000]
sim_rows = []
df_base = df_summary_primary[df_summary_primary["Uzytkownicy"] == SIM_BASE_USERS]
for _, row in df_base.iterrows():
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
        tps_degradation = 1.0 / (1.0 + path_length * (msg_size / 75000.0)
                                  + 0.0002 * n * t_verify_s * 1000
                                  + (network_scaling_factor - 1.0) * 2.0)
        effective_tps = base_tps * tps_degradation
        sim_rows.append({"Algorytm": algo, "Wezly": n, "Base_TPS": round(base_tps, 4),
                          "Efektywny_TPS": round(effective_tps, 4),
                          "Calkowite_Opoznienie_ms": round(total_e2e_lat_ms, 2)})

df_sim = pd.DataFrame(sim_rows)
sim_csv = os.path.join(RESULTS_DIR, "symulacja_duzej_sieci.csv")
df_sim.to_csv(sim_csv, index=False)
print(f"Zapisano: {sim_csv}")

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
plt.title(f"Przepustowosc zadan RPC (RPS) w funkcji obciazenia (T={PRIMARY_DURATION_S}s)", fontsize=11)
plt.xlabel("Liczba wspolbieznych uzytkownikow"); plt.ylabel("RPS")
plt.xticks(all_users); plt.grid(True, ls="--", alpha=0.5); plt.legend(frameon=True)
plt.tight_layout(); plt.savefig(os.path.join(CHARTS_DIR, "wykres_rps_zagesszczony.png"), dpi=300); plt.close()

plt.figure(figsize=(9, 5.5))
for a in algorithms:
    sub = df_summary_primary[df_summary_primary["Algorytm"] == a]
    plt.errorbar(sub["Uzytkownicy"], sub["TPS_mean"], yerr=sub["TPS_std"],
                 label=algo_meta[a]["name"], color=algo_meta[a]["color"],
                 marker=algo_meta[a]["marker"], capsize=4, lw=2, markersize=6)
plt.title(f"Przepustowosc transakcji (TPS) w funkcji obciazenia (T={PRIMARY_DURATION_S}s)", fontsize=11)
plt.xlabel("Liczba wspolbieznych uzytkownikow"); plt.ylabel("TPS")
plt.xticks(all_users); plt.grid(True, ls="--", alpha=0.5); plt.legend(frameon=True)
plt.tight_layout(); plt.savefig(os.path.join(CHARTS_DIR, "wykres_tps_zagesszczony.png"), dpi=300); plt.close()

plt.figure(figsize=(9, 5.5))
for a in algorithms:
    sub = df_summary_primary[df_summary_primary["Algorytm"] == a]
    plt.plot(sub["Uzytkownicy"], sub["Mediana_ms_mean"], color=algo_meta[a]["color"],
              marker=algo_meta[a]["marker"], lw=2, label=f"{algo_meta[a]['name']} (Mediana)")
    plt.plot(sub["Uzytkownicy"], sub["P95_ms_mean"], color=algo_meta[a]["color"],
              ls="--", lw=1.5, alpha=0.8, label=f"{algo_meta[a]['name']} (P95)")
    plt.plot(sub["Uzytkownicy"], sub["P99_ms_mean"], color=algo_meta[a]["color"],
              ls=":", lw=1.5, alpha=0.7, label=f"{algo_meta[a]['name']} (P99)")
plt.title(f"Opoznienia RPC (Mediana/P95/P99) (T={PRIMARY_DURATION_S}s)", fontsize=11)
plt.xlabel("Liczba wspolbieznych uzytkownikow"); plt.ylabel("Czas odpowiedzi (ms)")
plt.xticks(all_users); plt.grid(True, ls="--", alpha=0.5); plt.legend(fontsize=7, ncol=1)
plt.tight_layout(); plt.savefig(os.path.join(CHARTS_DIR, "wykres_opoznienia_zagesszczony.png"), dpi=300); plt.close()

fig, ax1 = plt.subplots(figsize=(9, 5.5))
ax2 = ax1.twinx()
for a in algorithms:
    sub = df_summary_primary[df_summary_primary["Algorytm"] == a]
    ax1.plot(sub["Uzytkownicy"], sub["CPU_mean"], color=algo_meta[a]["color"],
              marker=algo_meta[a]["marker"], lw=2, label=f"CPU - {algo_meta[a]['name']}")
    ax2.plot(sub["Uzytkownicy"], sub["RAM_mean"], color=algo_meta[a]["color"],
              marker=algo_meta[a]["marker"], ls="--", lw=1.5, alpha=0.7)
ax1.set_xlabel("Liczba wspolbieznych uzytkownikow"); ax1.set_ylabel("CPU (%)")
ax2.set_ylabel("RAM (MB)"); ax1.set_xticks(all_users); ax1.grid(True, ls="--", alpha=0.5)
ax1.set_title(f"CPU i RAM w funkcji obciazenia (T={PRIMARY_DURATION_S}s)", fontsize=11)
ax1.legend(loc="upper left", fontsize=8)
plt.tight_layout(); plt.savefig(os.path.join(CHARTS_DIR, "wykres_zasoby_cpu_ram.png"), dpi=300); plt.close()

plt.figure(figsize=(9, 5.5))
for a in algorithms:
    sub = df_sim[df_sim["Algorytm"] == a]
    plt.plot(sub["Wezly"], sub["Efektywny_TPS"], color=algo_meta[a]["color"],
              marker=algo_meta[a]["marker"], lw=2, label=algo_meta[a]["name"])
plt.title(f"Efektywny TPS w funkcji skali sieci P2P (U={SIM_BASE_USERS})", fontsize=11)
plt.xlabel("Liczba wezlow"); plt.ylabel("Efektywny TPS")
plt.xticks(node_counts); plt.grid(True, ls="--", alpha=0.5); plt.legend(frameon=True)
plt.tight_layout(); plt.savefig(os.path.join(CHARTS_DIR, "wykres_tps_vs_wezly_poprawiony.png"), dpi=300); plt.close()

plt.figure(figsize=(9, 5.5))
for a in algorithms:
    sub = df_sim[df_sim["Algorytm"] == a]
    plt.plot(sub["Wezly"], sub["Calkowite_Opoznienie_ms"], color=algo_meta[a]["color"],
              marker=algo_meta[a]["marker"], lw=2, label=algo_meta[a]["name"])
plt.title(f"Opoznienie propagacji P2P vs liczba wezlow (U={SIM_BASE_USERS})", fontsize=11)
plt.xlabel("Liczba wezlow"); plt.ylabel("Opoznienie (ms)")
plt.xticks(node_counts); plt.grid(True, ls="--", alpha=0.5); plt.legend(frameon=True)
plt.tight_layout(); plt.savefig(os.path.join(CHARTS_DIR, "wykres_opoznienie_vs_wezly_poprawiony.png"), dpi=300); plt.close()

duration_values = sorted(df_summary["Czas_testu_s"].unique())
for ref_u in [SIM_BASE_USERS, 600]:
    if ref_u not in all_users:
        continue
    plt.figure(figsize=(9, 5.5))
    for a in algorithms:
        sub = df_summary[(df_summary["Algorytm"] == a) & (df_summary["Uzytkownicy"] == ref_u)].sort_values("Czas_testu_s")
        if sub.empty:
            continue
        plt.errorbar(sub["Czas_testu_s"], sub["TPS_mean"], yerr=sub["TPS_std"],
                     label=algo_meta[a]["name"], color=algo_meta[a]["color"],
                     marker=algo_meta[a]["marker"], capsize=4, lw=2, markersize=6)
    plt.title(f"TPS vs czas trwania testu (U={ref_u})", fontsize=11)
    plt.xlabel("Czas trwania (s)"); plt.ylabel("TPS")
    plt.xticks(duration_values); plt.grid(True, ls="--", alpha=0.5); plt.legend(frameon=True)
    plt.tight_layout(); plt.savefig(os.path.join(CHARTS_DIR, f"wykres_tps_vs_czas_trwania_u{ref_u}.png"), dpi=300); plt.close()

    plt.figure(figsize=(9, 5.5))
    for a in algorithms:
        sub = df_summary[(df_summary["Algorytm"] == a) & (df_summary["Uzytkownicy"] == ref_u)].sort_values("Czas_testu_s")
        if sub.empty:
            continue
        plt.errorbar(sub["Czas_testu_s"], sub["Mediana_ms_mean"], yerr=sub["Mediana_ms_std"],
                     label=algo_meta[a]["name"], color=algo_meta[a]["color"],
                     marker=algo_meta[a]["marker"], capsize=4, lw=2, markersize=6)
    plt.title(f"Mediana opoznienia vs czas trwania testu (U={ref_u})", fontsize=11)
    plt.xlabel("Czas trwania (s)"); plt.ylabel("Mediana (ms)")
    plt.xticks(duration_values); plt.grid(True, ls="--", alpha=0.5); plt.legend(frameon=True)
    plt.tight_layout(); plt.savefig(os.path.join(CHARTS_DIR, f"wykres_opoznienia_vs_czas_trwania_u{ref_u}.png"), dpi=300); plt.close()

print("\nWSZYSTKIE WYKRESY WYGENEROWANE.")

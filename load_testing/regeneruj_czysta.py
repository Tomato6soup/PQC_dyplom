import pandas as pd
import os

RESULTS_DIR = os.path.expanduser("~/PQC_dyplom/load_testing/results")
raw = pd.read_csv(os.path.join(RESULTS_DIR, "surowe_proby_pelne.csv"))

# Usuń dwa przebiegi zepsute przez restart węzła w trakcie testu
mask_bad = (
    ((raw["Algorytm"] == "dilithium2") & (raw["Uzytkownicy"] == 50)  & (raw["Czas_testu_s"] == 90) & (raw["Powtorzenie"] == 5)) |
    ((raw["Algorytm"] == "dilithium2") & (raw["Uzytkownicy"] == 500) & (raw["Czas_testu_s"] == 90) & (raw["Powtorzenie"] == 5))
)
print(f"Usuwam {mask_bad.sum()} zepsute wiersze (restart wezla).")
df_clean = raw[~mask_bad].copy()

summary_rows = []
for (algo, u, t_s), grp in df_clean.groupby(["Algorytm", "Uzytkownicy", "Czas_testu_s"], sort=False):
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
        "Failures_total": grp["Failures"].sum(),
    })

df_summary_clean = pd.DataFrame(summary_rows)
out_path = os.path.join(RESULTS_DIR, "obciazenie_statystyka_pelna_CZYSTA.csv")
df_summary_clean.to_csv(out_path, index=False)
print(f"Zapisano czyste statystyki do: {out_path}")

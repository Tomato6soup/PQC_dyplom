import pandas as pd
import os

RESULTS_DIR = os.path.expanduser("~/PQC_dyplom/load_testing/results")
raw = pd.read_csv(os.path.join(RESULTS_DIR, "surowe_proby_pelne.csv"))

summary_rows = []
for (algo, u, t_s), grp in raw.groupby(["Algorytm", "Uzytkownicy", "Czas_testu_s"], sort=False):
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

df_summary = pd.DataFrame(summary_rows)
out_path = os.path.join(RESULTS_DIR, "obciazenie_statystyka_pelna_FINALNA.csv")
df_summary.to_csv(out_path, index=False)
print(f"Zapisano finalne statystyki do: {out_path}")
print(f"Liczba grup: {len(df_summary)}, wszystkie z Liczba_probek=5: {(df_summary['Liczba_probek']==5).all()}")

import os
import pandas as pd
import matplotlib.pyplot as plt

RESULTS_DIR = os.path.expanduser("~/PQC_dyplom/load_testing/results")
OUTPUT_DIR = os.path.expanduser("~/PQC_dyplom/Wykresy")
os.makedirs(OUTPUT_DIR, exist_ok=True)

algos = ["ecdsa", "dilithium2", "sphincs"]
labels = ["ECDSA (Klasyczny)", "Dilithium2 (PQC)", "SPHINCS+-128f (PQC)"]
rps_values = []
median_latencies = []
p95_latencies = []
p99_latencies = []

for algo in algos:
    stats_file = os.path.join(RESULTS_DIR, f"run_{algo}_u50_stats.csv")
    if os.path.exists(stats_file):
        df = pd.read_csv(stats_file)
        row = df[df["Name"] == "Aggregated"].iloc[0]
        rps_values.append(row["Requests/s"])
        median_latencies.append(row["50%"])
        p95_latencies.append(row["95%"])
        p99_latencies.append(row["99%"])
    else:
        print(f"Brak pliku: {stats_file}")

# 1. Wykres Przepustowości (RPS / TPS)
plt.figure(figsize=(9, 5))
bars = plt.bar(labels, rps_values, color=['#2ca02c', '#1f77b4', '#d62728'], width=0.55)
plt.title("Porównanie przepustowości RPC węzła (Requests/sec)", fontsize=13, pad=15)
plt.ylabel("RPS (Transakcje na sekundę)", fontsize=11)
plt.grid(axis='y', linestyle='--', alpha=0.7)

for bar in bars:
    yval = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2.0, yval + (max(rps_values)*0.01), f"{yval:.1f}", ha='center', va='bottom', fontweight='bold')

plt.tight_layout()
chart_path_rps = os.path.join(OUTPUT_DIR, "porownanie_przepustowosci_pqc.png")
plt.savefig(chart_path_rps, dpi=300)
plt.close()

# 2. Wykres Latencji (Mediana vs 95% vs 99%)
df_lat = pd.DataFrame({
    'Mediana (50%)': median_latencies,
    '95. percentyl': p95_latencies,
    '99. percentyl': p99_latencies
}, index=labels)

ax = df_lat.plot(kind='bar', figsize=(10, 6), colormap='viridis', width=0.7)
plt.title("Opóźnienia odpowiedzi RPC dla różnych sygnatur PQC (ms)", fontsize=13, pad=15)
plt.ylabel("Czas odpowiedzi (ms)", fontsize=11)
plt.xlabel("Kryptosystem", fontsize=11)
plt.xticks(rotation=0)
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.legend(title="Percentyle")

for p in ax.patches:
    ax.annotate(f"{p.get_height():.0f}", (p.get_x() + p.get_width() / 2., p.get_height()),
                ha='center', va='center', xytext=(0, 5), textcoords='offset points', fontsize=9)

plt.tight_layout()
chart_path_lat = os.path.join(OUTPUT_DIR, "porownanie_opoznien_pqc.png")
plt.savefig(chart_path_lat, dpi=300)
plt.close()

print("\n--- PODSUMOWANIE DANYCH ---")
summary_df = pd.DataFrame({
    "Algorytm": labels,
    "RPS": rps_values,
    "Mediana (ms)": median_latencies,
    "P95 (ms)": p95_latencies,
    "P99 (ms)": p99_latencies
})
print(summary_df.to_string(index=False))
print(f"\nWykresy zapisane w katalogu: {OUTPUT_DIR}")

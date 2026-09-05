import os
import pandas as pd
import matplotlib.pyplot as plt

RESULTS_FILE = os.path.expanduser("~/PQC_dyplom/load_testing/results/pelne_wyniki_obciazenia.csv")
OUTPUT_DIR = os.path.expanduser("~/PQC_dyplom/Wykresy")
os.makedirs(OUTPUT_DIR, exist_ok=True)

df = pd.read_csv(RESULTS_FILE)

algos = ["ecdsa", "dilithium2", "sphincs"]
algo_labels = {
    "ecdsa": "ECDSA (Klasyczny)",
    "dilithium2": "Dilithium2 (PQC)",
    "sphincs": "SPHINCS+-128f (PQC)"
}
colors = {"ecdsa": "#2ca02c", "dilithium2": "#1f77b4", "sphincs": "#d62728"}
markers = {"ecdsa": "o", "dilithium2": "s", "sphincs": "^"}

# 1. Wykres: Przepustowość (RPS) vs Obciążenie (Liczba użytkowników)
plt.figure(figsize=(9, 5))
for algo in algos:
    sub = df[df["Algorytm"] == algo]
    plt.plot(sub["Uzytkownicy"], sub["RPS"], marker=markers[algo], color=colors[algo], 
             label=algo_labels[algo], linewidth=2, markersize=8)

plt.title("Przepustowość węzła RPC w funkcji obciążenia (RPS vs Użytkownicy)", fontsize=13, pad=15)
plt.xlabel("Liczba współbieżnych użytkowników", fontsize=11)
plt.ylabel("Przepustowość (RPS)", fontsize=11)
plt.xticks([10, 50, 150, 300])
plt.grid(True, linestyle="--", alpha=0.6)
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "wykres_rps_vs_uzytkownicy.png"), dpi=300)
plt.close()

# 2. Wykres: Mediana opóźnień (Latency) vs Obciążenie
plt.figure(figsize=(9, 5))
for algo in algos:
    sub = df[df["Algorytm"] == algo]
    plt.plot(sub["Uzytkownicy"], sub["Mediana_ms"], marker=markers[algo], color=colors[algo], 
             label=algo_labels[algo], linewidth=2, markersize=8)

plt.title("Mediana opóźnień odpowiedzi RPC (ms) w funkcji obciążenia", fontsize=13, pad=15)
plt.xlabel("Liczba współbieżnych użytkowników", fontsize=11)
plt.ylabel("Czas odpowiedzi (ms)", fontsize=11)
plt.xticks([10, 50, 150, 300])
plt.grid(True, linestyle="--", alpha=0.6)
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "wykres_opoznienia_vs_uzytkownicy.png"), dpi=300)
plt.close()

# 3. Wykres: Zużycie pamięci RAM (MB)
plt.figure(figsize=(9, 5))
for algo in algos:
    sub = df[df["Algorytm"] == algo]
    plt.plot(sub["Uzytkownicy"], sub["Used_RAM_MB"], marker=markers[algo], color=colors[algo], 
             label=algo_labels[algo], linewidth=2, markersize=8)

plt.title("Alokacja pamięci RAM węzła podczas testów obciążeniowych (MB)", fontsize=13, pad=15)
plt.xlabel("Liczba współbieżnych użytkowników", fontsize=11)
plt.ylabel("Użycie RAM (MB)", fontsize=11)
plt.xticks([10, 50, 150, 300])
plt.grid(True, linestyle="--", alpha=0.6)
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "wykres_ram_vs_uzytkownicy.png"), dpi=300)
plt.close()

print(f"Wygenerowano 3 nowe wykresy w {OUTPUT_DIR}")

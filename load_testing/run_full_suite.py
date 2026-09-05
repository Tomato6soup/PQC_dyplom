import subprocess
import time
import requests
import pandas as pd
import os

PROMETHEUS_URL = "http://localhost:9090/api/v1/query"
RESULTS_DIR = os.path.expanduser("~/PQC_dyplom/load_testing/results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# Kompletny zestaw 4 poziomów obciążenia
scenarios = [
    {"users": 10, "rate": 2, "label": "low"},
    {"users": 50, "rate": 10, "label": "medium"},
    {"users": 150, "rate": 25, "label": "high"},
    {"users": 300, "rate": 50, "label": "saturation"}
]

algorithms = ["ecdsa", "dilithium2", "sphincs"]
duration = "60s"

def get_metric(query):
    try:
        r = requests.get(PROMETHEUS_URL, params={"query": query})
        data = r.json()
        if data["status"] == "success" and data["data"]["result"]:
            return float(data["data"]["result"][0]["value"][1])
    except Exception as e:
        print(f"Błąd metryki: {e}")
    return 0.0

summary_data = []

for algo in algorithms:
    for sc in scenarios:
        u = sc["users"]
        r = sc["rate"]
        csv_prefix = os.path.join(RESULTS_DIR, f"run_{algo}_u{u}")
        print(f"\n==========================================")
        print(f"Uruchamianie: Algo={algo} | Users={u} | Czas={duration}")
        print(f"==========================================")
        
        start_time = time.time()
        
        cmd = [
            "locust", "-f", "locustfile.py",
            "--headless",
            "-u", str(u),
            "-r", str(r),
            "-t", duration,
            "--host", "http://127.0.0.1:9944",
            f"--csv={csv_prefix}"
        ]
        
        env = os.environ.copy()
        env["TEST_ALGO"] = algo
        subprocess.run(cmd, env=env)
        
        time.sleep(2) # czas na zebranie próbek przez Prometheus
        
        # Pobieranie zużycia CPU i zużytej pamięci RAM z Prometheusa
        cpu_usage = get_metric('100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)')
        ram_used = get_metric('(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / (1024 * 1024)')
        
        stats_file = f"{csv_prefix}_stats.csv"
        if os.path.exists(stats_file):
            df = pd.read_csv(stats_file)
            agg = df[df["Name"] == "Aggregated"].iloc[0]
            summary_data.append({
                "Algorytm": algo,
                "Uzytkownicy": u,
                "RPS": agg["Requests/s"],
                "Failures": agg["Failure Count"],
                "Mediana_ms": agg["50%"],
                "P95_ms": agg["95%"],
                "P99_ms": agg["99%"],
                "Avg_CPU_%": round(cpu_usage, 2),
                "Used_RAM_MB": round(ram_used, 2)
            })
            
        print("Przerwa 10s na ochłodzenie węzła...")
        time.sleep(10)

summary_df = pd.DataFrame(summary_data)
summary_df.to_csv(os.path.join(RESULTS_DIR, "pelne_wyniki_obciazenia.csv"), index=False)
print("\nKONIEC WSZYSTKICH POMIARÓW. Podsumowanie:")
print(summary_df.to_string(index=False))

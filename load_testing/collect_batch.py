import subprocess
import time
import requests
import pandas as pd
import os
import csv
import sys

RESULTS_DIR = os.path.expanduser("~/PQC_dyplom/load_testing/results")
os.makedirs(RESULTS_DIR, exist_ok=True)

PROMETHEUS_URL = "http://localhost:9090/api/v1/query"
RPC_URL = "http://127.0.0.1:9944"

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

if len(sys.argv) < 2 or sys.argv[1] not in ["ecdsa", "dilithium2", "sphincs"]:
    print("Uzycie: python3 collect_batch.py <ecdsa|dilithium2|sphincs>")
    sys.exit(1)

algorithms = [sys.argv[1]]

DURATION_CONFIGS = [
    {"duration": "30s", "duration_s": 30, "repeats": 5},
    {"duration": "60s", "duration_s": 60, "repeats": 5},
    {"duration": "90s", "duration_s": 90, "repeats": 5},
]


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
    return max(0, len(extrinsics) - 1)


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


def wait_for_finality_catchup(max_wait_s=15, poll_interval_s=0.5):
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


def append_raw_record(record):
    file_exists = os.path.exists(RAW_CSV_PATH)
    with open(RAW_CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(record)
        f.flush()
        os.fsync(f.fileno())


total_runs = len(algorithms) * len(scenarios) * sum(dc["repeats"] for dc in DURATION_CONFIGS)
print(f"=== PARTIA: {algorithms[0]} ({total_runs} przebiegow) ===")
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
                      f"T={test_duration:4s} | Proba {rep}/{repeats}", flush=True)

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

                cpu = get_metric(f'100 - (avg(rate(node_cpu_seconds_total{{mode="idle"}}[{test_duration}])) * 100)')
                ram = get_metric('(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / (1024 * 1024)')

                wait_for_pool_drain()
                wait_for_finality_catchup()

                end_block = get_finalized_block_number()
                chain_tps = measure_chain_tps(start_block, end_block, t_end - t_start)

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
                    append_raw_record(record)
                else:
                    print(f"  UWAGA: brak {stats_file}", flush=True)
                time.sleep(2)

print(f"\nPARTIA {algorithms[0]} ZAKONCZONA.")

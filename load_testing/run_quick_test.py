import subprocess
import time
import requests
import pandas as pd
import numpy as np
import os
import math
import matplotlib.pyplot as plt

RESULTS_DIR = os.path.expanduser("~/PQC_dyplom/load_testing/results")
CHARTS_DIR = os.path.expanduser("~/PQC_dyplom/Wykresy")
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(CHARTS_DIR, exist_ok=True)

PROMETHEUS_URL = "http://localhost:9090/api/v1/query"
RPC_URL = "http://127.0.0.1:9944"

scenarios = [
    {"users": 450, "rate": 60, "label": "Przeciazenie"}
]

algorithms = ["sphincs"]
tx_crypto_size = {"ecdsa": 96, "dilithium2": 3732, "sphincs": 17120}
crypto_verify_time_ms = {"ecdsa": 0.06, "dilithium2": 0.04, "sphincs": 1.25}

TEST_DURATION = "15s"
TEST_DURATION_S = 15
REPEATS = 1

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


def wait_for_finality_catchup(max_wait_s=30, poll_interval_s=0.5):
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


raw_records = []

print(f"=== ETAP 1: TESTY OBCIAZENIOWE WEZLA RPC (k={REPEATS} POWTORZEN) ===")
total_runs = len(algorithms) * len(scenarios) * REPEATS
current_run = 0

for algo in algorithms:
    for sc in scenarios:
        u = sc["users"]
        r = sc["rate"]
        lbl = sc["label"]

        for rep in range(1, REPEATS + 1):
            current_run += 1
            prefix = os.path.join(RESULTS_DIR, f"tmp_{algo}_u{u}_rep{rep}")
            print(f"[{current_run}/{total_runs}] Algo: {algo:10s} | U={u:3d} ({lbl}) | Proba {rep}/{REPEATS}")

            cmd = [
                "locust", "-f", "locustfile.py",
                "--headless", "-u", str(u), "-r", str(r),
                "-t", TEST_DURATION, "--host", RPC_URL,
                f"--csv={prefix}"
            ]
            env = os.environ.copy()
            env["TEST_ALGO"] = algo

            start_block = get_finalized_block_number()
            t_start = time.time()
            print("Start bloku:", start_block, flush=True)

            subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            t_end = time.time()
            print("Test locust zakonczony, czekam na drain puli...", flush=True)

            drained = wait_for_pool_drain()
            print("Pula oprozniona:", drained, flush=True)
            caught_up = wait_for_finality_catchup()
            print("Finalizacja dogonila:", caught_up, flush=True)

            end_block = get_finalized_block_number()
            print("Koniec bloku:", end_block, flush=True)
            chain_tps = measure_chain_tps(start_block, end_block, t_end - t_start)
            print("Chain TPS:", chain_tps, flush=True)

            time.sleep(1)
            cpu = get_metric('100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[60s])) * 100)')
            ram = get_metric('(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / (1024 * 1024)')

            stats_file = f"{prefix}_stats.csv"
            if os.path.exists(stats_file):
                df_stat = pd.read_csv(stats_file)
                agg = df_stat[df_stat["Name"] == "Aggregated"].iloc[0]
                raw_records.append({
                    "Algorytm": algo,
                    "Uzytkownicy": u,
                    "Poziom": lbl,
                    "Powtorzenie": rep,
                    "RPS": float(agg["Requests/s"]),
                    "TPS": chain_tps,
                    "Mediana_ms": float(agg["50%"]),
                    "P95_ms": float(agg["95%"]),
                    "P99_ms": float(agg["99%"]),
                    "CPU_%": cpu,
                    "RAM_MB": ram,
                    "Failures": int(agg["Failure Count"])
                })
            time.sleep(2)

df_raw = pd.DataFrame(raw_records)
print(df_raw)
print("\nSZYBKI TEST ZAKONCZONY.")

#!/usr/bin/env python3
"""
sample_pool.py — próbkuje liczbę transakcji czekających w puli (pending pool)
przez wywołania RPC author_pendingExtrinsics, w regularnych odstępach czasu.
Używane do punktu 3 (kontrolowany test rate-throttle) - zebranie dowodu na to,
jak zapełnienie puli zmienia się w zależności od tempa wysyłki transakcji.

Uzycie:
    python3 sample_pool.py --duration 70 --interval 1 --out pool_ecdsa_u100_silny_run1.csv
"""

import argparse
import json
import time
import urllib.request


def get_pending_count(host):
    req = urllib.request.Request(
        host,
        data=json.dumps({"id": 1, "jsonrpc": "2.0", "method": "author_pendingExtrinsics", "params": []}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return len(data.get("result", []))
    except Exception as e:
        print(f"[sample_pool] blad odpytania: {e}")
        return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://127.0.0.1:9944")
    parser.add_argument("--duration", type=int, default=70, help="Czas trwania próbkowania w sekundach")
    parser.add_argument("--interval", type=float, default=1.0, help="Odstęp między próbkami w sekundach")
    parser.add_argument("--out", required=True, help="Plik CSV wynikowy")
    args = parser.parse_args()

    end_time = time.time() + args.duration
    with open(args.out, "w") as f:
        f.write("timestamp,pending_count\n")
        while time.time() < end_time:
            count = get_pending_count(args.host)
            f.write(f"{time.time():.1f},{count}\n")
            f.flush()
            time.sleep(args.interval)

    print(f"[sample_pool] Zapisano próbkowanie do {args.out}")


if __name__ == "__main__":
    main()

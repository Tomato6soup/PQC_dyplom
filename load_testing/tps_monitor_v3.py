#!/usr/bin/env python3
"""Monitor blokow v3: dla kazdego bloku zapisuje numer, czas wykrycia,
timestamp bloku, liczbe extrinsics, rozmiar, hashe podpisanych extrinsics
i (jesli sie da) wykorzystany weight. Wynik: plik JSONL."""
import argparse
import hashlib
import json
import time

from substrateinterface import SubstrateInterface


def rpc(substrate, method, params=None):
    r = substrate.rpc_request(method, params or [])
    if "error" in r:
        raise RuntimeError(str(r["error"]))
    return r["result"]


def head_number(substrate):
    return int(rpc(substrate, "chain_getHeader")["number"], 16)


def prefix_len(raw):
    m = raw[0] & 0b11
    if m == 0:
        return 1
    if m == 1:
        return 2
    if m == 2:
        return 4
    return 1 + (raw[0] >> 2) + 4


def query_value(substrate, module, item, block_hash):
    try:
        return substrate.query(module, item, block_hash=block_hash).value
    except Exception:
        return None


def process_block(substrate, number, t_detect):
    bh = rpc(substrate, "chain_getBlockHash", [number])
    blk = rpc(substrate, "chain_getBlock", [bh])
    exts = blk["block"]["extrinsics"]
    t_fetched = time.time()

    hashes = []
    ext_bytes = 0
    for hx in exts:
        raw = bytes.fromhex(hx[2:])
        ext_bytes += len(raw)
        ver = raw[prefix_len(raw)]
        if ver & 0x80:  # podpisany extrinsic (inherenty maja 0x04)
            hashes.append(hashlib.blake2b(raw, digest_size=32).hexdigest())

    ts_ms = query_value(substrate, "Timestamp", "Now", bh)
    alllen = query_value(substrate, "System", "AllExtrinsicsLen", bh)
    weight_ref = None
    bw = query_value(substrate, "System", "BlockWeight", bh)
    if isinstance(bw, dict):
        try:
            weight_ref = sum(int(bw[c]["ref_time"]) for c in ("normal", "operational", "mandatory"))
        except Exception:
            weight_ref = None

    return {
        "type": "block",
        "number": number,
        "hash": bh,
        "t_detect": t_detect,
        "t_fetched": t_fetched,
        "ts_ms": ts_ms,
        "n_total": len(exts),
        "n_signed": len(hashes),
        "ext_bytes": ext_bytes,
        "alllen": alllen,
        "weight_ref_time": weight_ref,
        "hashes": hashes,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="ws://127.0.0.1:9944")
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--poll", type=float, default=0.1)
    args = ap.parse_args()

    substrate = SubstrateInterface(url=args.host)
    t0 = time.time()
    end = t0 + args.duration
    last = head_number(substrate)

    out = open(args.out, "w", buffering=1)
    out.write(json.dumps({"type": "meta", "t_start": t0, "start_number": last}) + "\n")
    print(f"[monitor] start, head=#{last}, czas={args.duration}s")

    n_blocks = 0
    while time.time() < end:
        try:
            num = head_number(substrate)
            if num > last:
                t_detect = time.time()
                for n in range(last + 1, num + 1):
                    rec = process_block(substrate, n, t_detect)
                    out.write(json.dumps(rec) + "\n")
                    last = n
                    n_blocks += 1
                    print(f"[monitor] blok #{n}: ext={rec['n_total']} podpisanych={rec['n_signed']} bajtow={rec['ext_bytes']}")
            time.sleep(args.poll)
        except Exception as e:
            print(f"[monitor] blad: {e} - probuje dalej")
            time.sleep(1)

    out.write(json.dumps({"type": "end", "t_end": time.time(), "blocks": n_blocks}) + "\n")
    out.close()
    print(f"[monitor] koniec, bloki: {n_blocks}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
tps_monitor.py — mierzy prawdziwe TPS blockchaina (substrate) na podstawie
liczby ekstrinsiców faktycznie zaincludowanych w nowych blokach,
NIEZALEŻNIE od tego, co raportuje locust (który mierzy tylko RPC req/s,
a nie finalizację na chainie).

Użycie:
    python3 tps_monitor.py --duration 60
    python3 tps_monitor.py --duration 60 --host ws://127.0.0.1:9944

Uruchom ten skrypt W TYM SAMYM MOMENCIE, w którym startujesz test locust
(np. w drugim terminalu), z tym samym --duration co -t w locuście (lub kilka
sekund dłużej, żeby złapać "ogon" transakcji, które weszły do puli pod
koniec testu, ale zostały zaincludowane w bloku chwilę później).

Na końcu wypisuje:
  - liczbę bloków wyprodukowanych w czasie trwania pomiaru
  - łączną liczbę ekstrinsiców (z rozbiciem na "nasze" wywołania submit_pqc_*
    vs inherenty/inne)
  - realne TPS = (nasze ekstrinsyki) / (czas trwania pomiaru w sekundach)
  - dla porównania: TPS liczone też po czasie między pierwszym i ostatnim
    złapanym blokiem (bardziej odporne na czas startu/zamykania skryptu)
"""

import argparse
import time
from collections import Counter

from substrateinterface import SubstrateInterface


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="ws://127.0.0.1:9944",
                         help="WS endpoint node'a (domyślnie ws://127.0.0.1:9944)")
    parser.add_argument("--duration", type=int, default=60,
                         help="Czas trwania pomiaru w sekundach (dopasuj do -t w locuście)")
    parser.add_argument("--call-filter", default=None,
                         help="Opcjonalnie: fragment nazwy funkcji do filtrowania "
                              "(np. 'submit_pqc'). Jeśli nie podasz, skrypt wypisze "
                              "na końcu wszystkie napotkane nazwy calli, żebyś mogła "
                              "dobrać filtr i odpalić ponownie / przeliczyć ręcznie.")
    parser.add_argument("--warmup-s", type=float, default=0.0,
                         help="Czas rozgrzewki (sekundy) odrzucany z pomiaru TPS od "
                              "startu skryptu — bloki z tego okna są liczone do "
                              "'total/matched' ale NIE wliczane do TPS (dopasuj do "
                              "U/SPAWN_RATE locusta, żeby nie liczyć fazy rampowania).")
    args = parser.parse_args()

    substrate = SubstrateInterface(url=args.host)

    print(f"[tps_monitor] Łączę się z {args.host} ...")
    chain_info = substrate.get_chain_head()
    print(f"[tps_monitor] Połączono. Aktualny head: {chain_info}")

    print(f"[tps_monitor] Startuję pomiar na {args.duration}s. "
          f"Odpal teraz test locust w drugim terminalu (jeśli jeszcze nie działa).")

    start_time = time.time()
    end_time = start_time + args.duration

    all_call_names = Counter()
    matched_extrinsics = 0
    total_extrinsics = 0
    blocks_seen = []

    last_block_hash = substrate.get_chain_head()
    last_block = substrate.get_block(block_hash=last_block_hash)
    current_number = last_block["header"]["number"]

    while time.time() < end_time:
        try:
            block_hash = substrate.get_chain_head()
            block = substrate.get_block(block_hash=block_hash)
            number = block["header"]["number"]

            if number > current_number:
                # mogło powstać kilka bloków między odpytaniami — przejdźmy po wszystkich
                for n in range(current_number + 1, number + 1):
                    bh = substrate.get_block_hash(n)
                    b = substrate.get_block(block_hash=bh)
                    extrinsics = b["extrinsics"]
                    block_extr_count = 0
                    for ex in extrinsics:
                        call = ex.value.get("call", {})
                        module = call.get("call_module", "?")
                        function = call.get("call_function", "?")
                        name = f"{module}.{function}"
                        all_call_names[name] += 1
                        total_extrinsics += 1
                        if args.call_filter:
                            if args.call_filter.lower() in function.lower():
                                matched_extrinsics += 1
                                block_extr_count += 1
                        else:
                            # bez filtra: liczymy wszystko poza inherentem Timestamp.set
                            if name != "Timestamp.set":
                                matched_extrinsics += 1
                                block_extr_count += 1
                    block_ts = time.time()
                    is_warmup = (block_ts - start_time) < args.warmup_s
                    blocks_seen.append((n, block_extr_count, block_ts, is_warmup))
                    tag = " [warmup]" if is_warmup else ""
                    print(f"[tps_monitor] blok #{n}: {len(extrinsics)} ekstrinsiców "
                          f"(policzone jako nasze: {block_extr_count}){tag}")
                current_number = number

            time.sleep(0.5)
        except Exception as e:
            print(f"[tps_monitor] błąd odpytania: {e} — próbuję dalej...")
            time.sleep(1)

    actual_elapsed = time.time() - start_time

    post_warmup_blocks = [b for b in blocks_seen if not b[3]]
    post_warmup_matched = sum(b[1] for b in post_warmup_blocks)

    print("\n" + "=" * 70)
    print("WYNIK POMIARU TPS")
    print("=" * 70)
    print(f"Czas trwania pomiaru:         {actual_elapsed:.1f}s")
    print(f"Rozgrzewka odrzucona:         {args.warmup_s:.1f}s "
          f"({len(blocks_seen) - len(post_warmup_blocks)} blok(ów) odrzuconych)")
    print(f"Bloków zaobserwowanych:       {len(blocks_seen)} "
          f"(po rozgrzewce: {len(post_warmup_blocks)})")
    print(f"Ekstrinsiców razem:           {total_extrinsics}")
    print(f"Ekstrinsiców 'naszych':       {matched_extrinsics} "
          f"(po rozgrzewce: {post_warmup_matched})")
    print(f"TPS (nasze / czas trwania, CAŁE okno):         "
          f"{matched_extrinsics / actual_elapsed:.2f}")

    if len(post_warmup_blocks) >= 2:
        span_pw = post_warmup_blocks[-1][2] - post_warmup_blocks[0][2]
        if span_pw > 0:
            print(f"TPS (nasze / rozpiętość PO rozgrzewce = {span_pw:.1f}s):  "
                  f"{post_warmup_matched / span_pw:.2f}")
    elif args.warmup_s > 0:
        print("TPS po rozgrzewce: niewystarczająco bloków po odrzuceniu rozgrzewki.")

    if len(blocks_seen) >= 2:
        span = blocks_seen[-1][2] - blocks_seen[0][2]
        if span > 0:
            print(f"TPS (nasze / rozpiętość blocks[0]->blocks[-1] = {span:.1f}s): "
                  f"{matched_extrinsics / span:.2f}")

    if not args.call_filter:
        print("\nNapotkane nazwy calli (module.function) i ich liczba:")
        for name, count in all_call_names.most_common():
            print(f"  {name}: {count}")
        print("\n(Jeśli chcesz policzyć TPS tylko dla konkretnego calla, "
              "odpal skrypt ponownie z --call-filter <fragment_nazwy>, "
              "np. --call-filter submit_pqc)")

    print("=" * 70)


if __name__ == "__main__":
    main()

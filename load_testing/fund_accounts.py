#!/usr/bin/env python3
"""
fund_accounts.py — dofinansowuje konta testowe z //Alice po restarcie noda.

W tym chain specu (--dev) genesis finansuje TYLKO Alice, Bob, AliceStash,
BobStash (patrz runtime/src/genesis_config_presets.rs) — Charlie/Dave/Eve/
Ferdie startuja z saldem 0. Ten skrypt przelewa z Alice odpowiednia kwote na
kazde konto z batch_accounts.json (poza Alice/Bob, ktore juz sa finansowane)
i czeka na zaincludowanie przelewow w bloku, zanim test ruszy.

Uzycie:
    python3 fund_accounts.py --host ws://127.0.0.1:9944 --amount 1000000000000000000
"""

import argparse
import json
import os
import time

from substrateinterface import SubstrateInterface, Keypair


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="ws://127.0.0.1:9944")
    parser.add_argument("--amount", type=int, default=10**14,
                         help="Kwota do przelania na kazde nie-finansowane konto "
                              "(Alice ma ~1.15e18 w genesis --dev - zostaw duzy margines)")
    parser.add_argument("--accounts-file", default=None,
                         help="Domyslnie batch_accounts.json w tym samym katalogu")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    accounts_path = args.accounts_file or os.path.join(base_dir, "batch_accounts.json")
    with open(accounts_path) as f:
        uris = json.load(f)

    substrate = SubstrateInterface(url=args.host)
    alice = Keypair.create_from_uri("//Alice")

    # Konta juz finansowane w genesis (--dev): Alice, Bob, AliceStash, BobStash.
    already_funded = {"//Alice", "//Bob", "//Alice//stash", "//Bob//stash"}

    to_fund = [u for u in uris if u not in already_funded]
    if not to_fund:
        print("[fund_accounts] Nic do dofinansowania (wszystkie konta juz finansowane w genesis).")
        return

    print(f"[fund_accounts] Dofinansowuje {len(to_fund)} kont z //Alice "
          f"(kwota/konto: {args.amount})...")

    nonce = substrate.get_account_nonce(alice.ss58_address)
    start_nonce = nonce
    for uri in to_fund:
        dest = Keypair.create_from_uri(uri)
        call = substrate.compose_call(
            call_module="Balances",
            call_function="transfer_keep_alive",
            call_params={"dest": dest.ss58_address, "value": args.amount},
        )
        extrinsic = substrate.create_signed_extrinsic(call=call, keypair=alice, nonce=nonce)
        substrate.submit_extrinsic(extrinsic, wait_for_inclusion=False)
        nonce += 1

    # Nonce'y z Alice sa sekwencyjne i (przy jednym nodzie bez forkow) wchodza
    # do blokow w tej samej kolejnosci, w ktorej zostaly zlozone - sprawdzamy
    # tylko OSTATNIE konto (i nonce Alice), zamiast odpytywac wszystkie N kont
    # w kazdej iteracji (zbyt kosztowne przy setkach kont).
    last_uri = to_fund[-1]
    last_dest = Keypair.create_from_uri(last_uri)
    deadline = time.time() + max(30, len(to_fund) // 20)
    funded = False
    while time.time() < deadline:
        time.sleep(1)
        acc = substrate.query("System", "Account", [last_dest.ss58_address])
        alice_nonce_now = substrate.get_account_nonce(alice.ss58_address)
        if acc.value["data"]["free"] > 0 and alice_nonce_now >= nonce:
            funded = True
            break

    if not funded:
        current_nonce = substrate.get_account_nonce(alice.ss58_address)
        print(f"[fund_accounts] UWAGA: ostatnie konto ({last_uri}) nie doczekalo sie "
              f"salda / nonce Alice nie dogonil {nonce} (jest: {current_nonce})")
    else:
        print(f"[fund_accounts] Wszystkie {len(to_fund)} kont dofinansowane "
              f"(nonce Alice {start_nonce}->{nonce}, potwierdzone na chainie).")


if __name__ == "__main__":
    main()

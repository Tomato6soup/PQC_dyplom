import json
import os
import time
import requests
from substrateinterface import SubstrateInterface, Keypair

N_ACCOUNTS = 600
FUNDING_AMOUNT = 10**14
CHUNK_SIZE = 40
RPC_URL = "http://127.0.0.1:9944"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_PATH = os.path.join(BASE_DIR, "batch_accounts.json")

substrate = SubstrateInterface(url="ws://127.0.0.1:9944")
alice = Keypair.create_from_uri("//Alice")


def rpc_call(method, params=None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
    r = requests.post(RPC_URL, json=payload, timeout=5)
    return r.json().get("result")


def wait_for_pool_drain(max_wait_s=60, poll_s=1.5, stable_needed=2):
    stable, waited = 0, 0.0
    while waited < max_wait_s:
        pending = rpc_call("author_pendingExtrinsics", [])
        if pending is not None and len(pending) == 0:
            stable += 1
            if stable >= stable_needed:
                return True
        else:
            stable = 0
        time.sleep(poll_s)
        waited += poll_s
    return False


accounts = [f"//BatchUser{i}" for i in range(N_ACCOUNTS)]

print(f"Zasilanie {N_ACCOUNTS} kont w paczkach po {CHUNK_SIZE}...")
for start in range(0, N_ACCOUNTS, CHUNK_SIZE):
    chunk = accounts[start:start + CHUNK_SIZE]
    nonce = substrate.get_account_nonce(alice.ss58_address)
    for uri in chunk:
        kp = Keypair.create_from_uri(uri)
        call = substrate.compose_call(
            call_module="Balances",
            call_function="transfer_allow_death",
            call_params={"dest": kp.ss58_address, "value": FUNDING_AMOUNT}
        )
        extrinsic = substrate.create_signed_extrinsic(call=call, keypair=alice, nonce=nonce)
        substrate.submit_extrinsic(extrinsic, wait_for_inclusion=False)
        nonce += 1
    ok = wait_for_pool_drain()
    done = min(start + CHUNK_SIZE, N_ACCOUNTS)
    print(f"  paczka {start}-{done-1} wyslana, pula oprozniona: {ok} ({done}/{N_ACCOUNTS})")

with open(ACCOUNTS_PATH, "w") as f:
    json.dump(accounts, f, indent=2)

print("\nWeryfikacja salda na probce 10 kont:")
all_ok = True
for i in [0, 50, 100, 200, 300, 400, 499, 550, 590, 599]:
    kp = Keypair.create_from_uri(accounts[i])
    balance = substrate.query("System", "Account", [kp.ss58_address])
    free = balance.value['data']['free']
    status = "OK" if free > FUNDING_AMOUNT // 2 else "BRAK SRODKOW!"
    if free <= FUNDING_AMOUNT // 2:
        all_ok = False
    print(f"  [{i}] {accounts[i]}: {free}  -> {status}")

if all_ok:
    print(f"\nWszystkie sprawdzone konta poprawnie zasilone. Zapisano {N_ACCOUNTS} kont do {ACCOUNTS_PATH}")
else:
    print("\nUWAGA: niektore konta NIE zostaly zasilone poprawnie!")

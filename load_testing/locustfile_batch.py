import os
import json
import time
import threading
import fcntl

from locust import User, task, between, events
from substrateinterface import SubstrateInterface, Keypair

ALGO_MAP = {"ecdsa": 0, "dilithium2": 1, "sphincs": 2}
ALGO = os.getenv("TEST_ALGO", "dilithium2").lower()
ALGO_ID = ALGO_MAP.get(ALGO, 1)
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VECTORS_PATH = os.path.join(BASE_DIR, "pqc_test_vectors.json")
with open(VECTORS_PATH) as f:
    VECTORS = json.load(f)

VEC = VECTORS[ALGO]
MESSAGE_HEX = "0x" + VECTORS["message"]
SIGNATURE_HEX = "0x" + VEC["signature"]
PUBLIC_KEY_HEX = "0x" + VEC["public_key"]

ACCOUNTS_PATH = os.path.join(BASE_DIR, "batch_accounts.json")
with open(ACCOUNTS_PATH) as f:
    ACCOUNT_URIS = json.load(f)

# Licznik wyboru konta musi byc bezpieczny MIEDZY procesami (--processes),
# nie tylko miedzy watkami/greenletami w jednym procesie. Uzywamy pliku
# z blokada (fcntl.flock), ktory dziala poprawnie w obu przypadkach.
COUNTER_FILE = os.path.join(BASE_DIR, ".account_counter")
_thread_lock = threading.Lock()

# Upewnij sie, ze plik licznika istnieje
if not os.path.exists(COUNTER_FILE):
    with open(COUNTER_FILE, "w") as f:
        f.write("0")


def _pick_account_uri():
    with _thread_lock:
        with open(COUNTER_FILE, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                content = f.read().strip()
                idx = int(content) if content else 0
                f.seek(0)
                f.truncate()
                f.write(str(idx + 1))
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    return ACCOUNT_URIS[idx % len(ACCOUNT_URIS)]


class SubstrateLoadUser(User):
    wait_time = between(0.001, 0.005)

    def on_start(self):
        self.substrate = SubstrateInterface(url="ws://127.0.0.1:9944")
        uri = _pick_account_uri()
        self.keypair = Keypair.create_from_uri(uri)
        self.nonce = self.substrate.rpc_request("system_accountNextIndex", [self.keypair.ss58_address])["result"]
        # compose_call jest stale (algo/message/signature/public_key sie nie zmieniaja),
        # wiec liczymy je raz, nie przy kazdym requescie.
        self.call = self.substrate.compose_call(
            call_module="PqcBench",
            call_function="submit_pqc_signature",
            call_params={
                "algo": ALGO_ID,
                "message": MESSAGE_HEX,
                "signature": SIGNATURE_HEX,
                "public_key": PUBLIC_KEY_HEX,
            }
        )

    @task
    def submit_pqc_signature_batch(self):
        start = time.time()
        last_exc = None
        sent = 0
        for _ in range(BATCH_SIZE):
            try:
                extrinsic = self.substrate.create_signed_extrinsic(
                    call=self.call, keypair=self.keypair, nonce=self.nonce
                )
                self.substrate.submit_extrinsic(extrinsic, wait_for_inclusion=False)
                self.nonce += 1
                time.sleep(0.05)
                sent += 1
            except Exception as e:
                last_exc = e
                msg = str(e)
                if "outdated" in msg.lower():
                    # lokalny nonce zostal w tyle za chainem - zresynchronizuj
                    self.nonce = self.substrate.rpc_request("system_accountNextIndex", [self.keypair.ss58_address])["result"]
                elif "Priority is too low" in msg:
                    # to byl literalny duplikat - poprzednia proba faktycznie
                    # weszla do puli, wiec przesuwamy nonce do przodu
                    self.nonce += 1

        elapsed_ms = (time.time() - start) * 1000
        events.request.fire(
            request_type="RPC",
            name=f"submit_pqc_signature_batch{BATCH_SIZE}_{ALGO}",
            response_time=elapsed_ms,
            response_length=len(SIGNATURE_HEX) * sent,
            exception=last_exc if sent < BATCH_SIZE else None,
        )

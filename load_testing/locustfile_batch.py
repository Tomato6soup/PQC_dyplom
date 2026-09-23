import os
import json
import time
import threading

from locust import User, task, between, events
from substrateinterface import SubstrateInterface, Keypair

ALGO_MAP = {"ecdsa": 0, "dilithium2": 1, "sphincs": 2}
ALGO = os.getenv("TEST_ALGO", "dilithium2").lower()
ALGO_ID = ALGO_MAP.get(ALGO, 1)
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))

VECTORS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pqc_test_vectors.json")
with open(VECTORS_PATH) as f:
    VECTORS = json.load(f)

VEC = VECTORS[ALGO]
MESSAGE_HEX = "0x" + VECTORS["message"]
SIGNATURE_HEX = "0x" + VEC["signature"]
PUBLIC_KEY_HEX = "0x" + VEC["public_key"]

substrate = SubstrateInterface(url="ws://127.0.0.1:9944")
keypair = Keypair.create_from_uri("//Alice")

_nonce_lock = threading.Lock()
_current_nonce = substrate.get_account_nonce(keypair.ss58_address)

def _next_nonce():
    global _current_nonce
    with _nonce_lock:
        n = _current_nonce
        _current_nonce += 1
        return n

class SubstrateLoadUser(User):
    wait_time = between(0.001, 0.005)

    @task
    def submit_pqc_signature_batch(self):
        start = time.time()
        last_exc = None
        sent = 0
        for _ in range(BATCH_SIZE):
            nonce = _next_nonce()
            try:
                call = substrate.compose_call(
                    call_module="PqcBench",
                    call_function="submit_pqc_signature",
                    call_params={
                        "algo": ALGO_ID,
                        "message": MESSAGE_HEX,
                        "signature": SIGNATURE_HEX,
                        "public_key": PUBLIC_KEY_HEX,
                    }
                )
                extrinsic = substrate.create_signed_extrinsic(call=call, keypair=keypair, nonce=nonce)
                substrate.submit_extrinsic(extrinsic, wait_for_inclusion=False)
                time.sleep(0.05)
                sent += 1
            except Exception as e:
                last_exc = e

        elapsed_ms = (time.time() - start) * 1000
        events.request.fire(
            request_type="RPC",
            name=f"submit_pqc_signature_batch{BATCH_SIZE}_{ALGO}",
            response_time=elapsed_ms,
            response_length=len(SIGNATURE_HEX) * sent,
            exception=last_exc if sent < BATCH_SIZE else None,
        )

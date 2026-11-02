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
PACING_S = float(os.getenv("PACING_S", "0.05"))
SUBMIT_LOG_PREFIX = os.getenv("SUBMIT_LOG_PREFIX", "")

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

COUNTER_FILE = os.path.join(BASE_DIR, ".account_counter")
_thread_lock = threading.Lock()

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
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    return ACCOUNT_URIS[idx % len(ACCOUNT_URIS)]


_log_lock = threading.Lock()
_log_files = {}


def _get_log():
    # jeden plik na proces locusta (bez rywalizacji o zapis)
    if not SUBMIT_LOG_PREFIX:
        return None
    pid = os.getpid()
    f = _log_files.get(pid)
    if f is None:
        with _log_lock:
            f = _log_files.get(pid)
            if f is None:
                f = open(f"{SUBMIT_LOG_PREFIX}_{pid}.csv", "w", buffering=1)
                f.write("t_send,tx_hash,status,error\n")
                _log_files[pid] = f
    return f


def _hash_hex(receipt):
    h = getattr(receipt, "extrinsic_hash", None)
    if isinstance(h, (bytes, bytearray)):
        h = "0x" + bytes(h).hex()
    return str(h) if h else ""


class SubstrateLoadUser(User):
    wait_time = between(0.001, 0.005)

    def on_start(self):
        self.substrate = SubstrateInterface(url="ws://127.0.0.1:9944")
        uri = _pick_account_uri()
        self.keypair = Keypair.create_from_uri(uri)
        self.nonce = self.substrate.rpc_request("system_accountNextIndex", [self.keypair.ss58_address])["result"]
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
        log = _get_log()
        last_exc = None
        sent = 0
        measured_s = 0.0
        for _ in range(BATCH_SIZE):
            t0 = time.time()
            t_send = t0
            tx_hash = ""
            err = ""
            ok = False
            try:
                extrinsic = self.substrate.create_signed_extrinsic(
                    call=self.call, keypair=self.keypair, nonce=self.nonce
                )
                t_send = time.time()
                receipt = self.substrate.submit_extrinsic(extrinsic, wait_for_inclusion=False)
                tx_hash = _hash_hex(receipt)
                self.nonce += 1
                sent += 1
                ok = True
            except Exception as e:
                last_exc = e
                msg = str(e)
                err = msg.replace("\n", " ").replace(",", ";")[:120]
                if "outdated" in msg.lower():
                    self.nonce = self.substrate.rpc_request("system_accountNextIndex", [self.keypair.ss58_address])["result"]
                elif "Priority is too low" in msg:
                    self.nonce += 1
            measured_s += time.time() - t0
            if log is not None:
                log.write(f"{t_send:.6f},{tx_hash},{'ok' if ok else 'err'},{err}\n")
            if ok and PACING_S > 0:
                time.sleep(PACING_S)

        events.request.fire(
            request_type="RPC",
            name=f"submit_pqc_signature_batch{BATCH_SIZE}_{ALGO}",
            response_time=measured_s * 1000,
            response_length=len(SIGNATURE_HEX) * sent,
            exception=last_exc if sent < BATCH_SIZE else None,
        )

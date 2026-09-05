import time
import os
import json
from locust import HttpUser, task, between, events
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ECDSA: overhead ~96 B
# Dilithium2: overhead ~3732 B (2420 B podpis + 1312 B klucz)
# SPHINCS+-128f: overhead ~17120 B (17088 B podpis + 32 B klucz)
ALGO = os.getenv("TEST_ALGO", "dilithium2").lower()

PAYLOAD_SIZES = {
    "ecdsa": 96,
    "dilithium2": 3732,
    "sphincs": 17120
}

DATA_CHUNK = b"X" * PAYLOAD_SIZES.get(ALGO, 3732)

class SubstrateLoadUser(HttpUser):
    wait_time = between(0.001, 0.005)  

    @task
    def submit_extrinsic(self):
        # Symulacja wysyłania transakcji/ekstrinsiku do węzła przez RPC JSON-RPC
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "author_submitExtrinsic",
            "params": [DATA_CHUNK.hex()]
        }
        headers = {"Content-Type": "application/json"}
        self.client.post("/", json=payload, headers=headers, name=f"submit_tx_{ALGO}")


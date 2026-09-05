# Wyniki testów obciążeniowych RPC (Locust)

Warunki testowe: 50 współbieżnych użytkowników, ramp-up 10/s, czas trwania 60s, węzeł Substrate w trybie deweloperskim.

| Algorytm kryptograficzny | Typ | Narzut danych (B) | Przepustowość (RPS) | Mediana (ms) | 95. percentyl (ms) | 99. percentyl (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ECDSA** | Klasyczny | 96 | 2203.22 | 14 | 19 | 22 |
| **Dilithium2** | PQC (Kraty) | 3732 | 1952.46 | 16 | 23 | 30 |
| **SPHINCS+-128f** | PQC (Hashe) | 17120 | 1897.10 | 17 | 23 | 26 |

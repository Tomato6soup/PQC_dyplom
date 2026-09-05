# Wyniki pełnej serii eksperymentów obciążeniowych (Locust + Prometheus)

| Algorytm | Użytkownicy | Poziom | RPS | Mediana (ms) | P95 (ms) | P99 (ms) | Średnie CPU (%) | RAM (MB) | Failures |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ECDSA** | 10 | Niski | 1573.68 | 2 | 4 | 8 | 14.38 | 1958.19 | 0 |
| **ECDSA** | 50 | Średni | 2097.58 | 15 | 20 | 24 | 14.88 | 1908.76 | 0 |
| **ECDSA** | 150 | Wysoki | 2144.76 | 54 | 66 | 74 | 15.03 | 1978.98 | 0 |
| **ECDSA** | 300 | Nasycenie | 2126.29 | 110 | 130 | 140 | 14.74 | 1942.44 | 0 |
| **Dilithium2** | 10 | Niski | 1586.44 | 2 | 4 | 5 | 14.45 | 2006.05 | 0 |
| **Dilithium2** | 50 | Średni | 2037.45 | 16 | 22 | 24 | 14.97 | 1953.07 | 0 |
| **Dilithium2** | 150 | Wysoki | 2074.17 | 57 | 67 | 74 | 15.22 | 2016.79 | 0 |
| **Dilithium2** | 300 | Nasycenie | 2068.80 | 110 | 130 | 140 | 14.79 | 1959.35 | 0 |
| **SPHINCS+-128f** | 10 | Niski | 1463.69 | 3 | 4 | 6 | 15.20 | 2073.61 | 0 |
| **SPHINCS+-128f** | 50 | Średni | 1835.73 | 18 | 24 | 27 | 16.11 | 1963.31 | 0 |
| **SPHINCS+-128f** | 150 | Wysoki | 1867.71 | 63 | 76 | 88 | 16.14 | 2046.03 | 0 |
| **SPHINCS+-128f** | 300 | Nasycenie | 1841.41 | 130 | 150 | 160 | 15.52 | 1974.82 | 0 |

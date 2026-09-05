# Analiza skalowalności protokołów PQC w systemach blockchain

Praca inżynierska poświęcona wpływowi **postkwantowych algorytmów podpisu
cyfrowego** (Dilithium2 / ML-DSA, SPHINCS+ / SLH-DSA) na wydajność i
skalowalność sieci blockchain typu peer-to-peer, w porównaniu z klasycznym
algorytmem ECDSA.

> **Autor:** Anna Tkach
> **Uczelnia:** Uniwersytet Bielsko-Bialski, Wydział Budowy Maszyn i Informatyki
> **Kierunek:** Informatyka (Sieci komputerowe i bezpieczeństwo sieciowe)
> **Rok akademicki:** 2025/2026

---

## O czym jest ta praca

Rozwój komputerów kwantowych zagraża klasycznej kryptografii asymetrycznej,
na której opiera się bezpieczeństwo systemów blockchain. Odpowiedzią są
algorytmy postkwantowe (PQC), które jednak wiążą się z **znacznie większymi
podpisami i kluczami**. Praca bada, jak ta zmiana rozmiaru danych przekłada
się na realną skalowalność rozproszonej sieci blockchain.

**Cel pracy:** ilościowe rozdzielenie dwóch źródeł narzutu przy migracji na
PQC — kosztu obliczeniowego (weryfikacja podpisu przez procesor) od kosztu
sieciowego (propagacja większych bloków w sieci).

## Jak przebiegało badanie

Zaprojektowano dwuetapowe środowisko badawcze:

| Etap | Skala | Co mierzy |
|------|-------|-----------|
| **Mikro** | pojedynczy węzeł | rzeczywisty czas weryfikacji kryptograficznej podpisów |
| **Makro** | sieć P2P (500–4000 węzłów) | czas propagacji bloku w sieci i liczbę bloków osieroconych |

Wynik z etapu mikro (czas weryfikacji) zasila etap makro, dzięki czemu oba
tworzą jeden, spójny zestaw danych. Każdy scenariusz uruchamiano wielokrotnie
dla różnych ziaren losowości, a wyniki uśredniano.

Porównano trzy schematy podpisu:

- **ECDSA** — klasyczny algorytm referencyjny (podpis ~64 B),
- **Dilithium2 (ML-DSA-44)** — standard PQC oparty na kratach (podpis ~2,4 KB),
- **SPHINCS+ (SLH-DSA)** — schemat oparty na funkcjach skrótu (podpis >7,8 KB).

## Najważniejsze wyniki

Dla największego badanego obciążenia (2000 transakcji, sieć 4000 węzłów):

| Algorytm | Śr. czas propagacji | Bloki osierocone |
|----------|--------------------:|-----------------:|
| ECDSA | ~11 s | ~150 |
| Dilithium2 (ML-DSA-44) | ~86 s | ~63 800 |
| SPHINCS+ (SLH-DSA) | ~180 s | ~569 000 |

**Wnioski:**

- Głównym czynnikiem ograniczającym skalowalność jest **przepustowość sieci**,
  a nie moc obliczeniowa — udział czasu weryfikacji CPU w całkowitym opóźnieniu
  nie przekracza kilku procent.
- **ECDSA** ma najniższy narzut, lecz przy większych obciążeniach również
  przekracza przyjęty próg bezpiecznej propagacji (6 s).
- **Dilithium2** jest praktyczny tylko przy niskich obciążeniach lub wymaga
  dodatkowych mechanizmów (kompresja, agregacja transakcji).
- **SPHINCS+**, ze względu na rozmiar podpisu, w żadnym scenariuszu nie
  utrzymuje bezpiecznej propagacji i prowadzi do masowego powstawania bloków
  osieroconych (załamanie sieci — *congestion collapse*).

## Wykorzystane narzędzia

- **Rust** (biblioteki `pqcrypto-dilithium`, `pqcrypto-sphincsplus`, `secp256k1`)
  — pomiar narzutu kryptograficznego,
- **SimBlock** (Java) — symulator propagacji bloków w sieci blockchain,
- **Python** (`pandas`, `numpy`, `matplotlib`) — analiza danych i wizualizacja.

## Terminologia

Nazwy robocze nie są w pełni tożsame ze standardami NIST:

| Nazwa robocza | Standard NIST | Badany wariant |
|---------------|---------------|----------------|
| Dilithium2 | ML-DSA (FIPS 204) | ML-DSA-44 |
| SPHINCS+ | SLH-DSA (FIPS 205) | SLH-DSA-SHA2-128s |

## Licencja

Do uzupełnienia przez autora. Symulator SimBlock rozwijany jest na osobnej
licencji — zob. [repozytorium SimBlock](https://github.com/dsg-titech/simblock).

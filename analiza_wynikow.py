#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analiza_wynikow.py

Przetwarza wszystkie pliki wynikowe z katalogu wyniki/ (wygenerowane
skryptem run_all.sh: pliki typu  dilithium_2000_N4000_seed50.txt ),
a następnie:

  1. liczy dla każdego (algorytm, tx, N) uśrednione po seedach:
     liczbę bloków, Mean, Std, Min, Max czasu propagacji [s],
  2. buduje tabele skalowalności (jak w PQC_v2.docx) -> tabele_skalowalnosc.csv,
  3. buduje tabele udziału weryfikacji CPU (%) -> tabele_udzial_cpu.csv,
  4. rysuje wykresy propagacji (z etykietami: algorytm, block_size,
     opóźnienie, liczba seedów) -> wykresy/propagacja_*.png,
  5. rysuje wykresy bloków osieroconych (stale/orphan) -> wykresy/osierocone_*.png.

URUCHOMIENIE:
    python3 analiza_wynikow.py

WYMAGANIA:
    pip install pandas numpy matplotlib

FORMAT LOGÓW (dopasowany do Twoich plików):
    Skrypt czyta rzeczywisty format wyjścia SimBlock z Twoich plików, np.:
        simblock.block.ProofOfWorkBlock@70177ecd:0   <- nagłówek bloku (":H" = wysokość)
        123,59                                        <- id_węzła,czas_odbioru_ms
        169,274
        ...
    Czas propagacji bloku = (max czas odbioru - min czas odbioru) wśród
    jego odbiorców. Bloki osierocone (orphan/stale) = bloki na powtórzonej
    wysokości łańcucha (forki). Jeśli kiedyś zmienisz format logów,
    modyfikujesz WYŁĄCZNIE funkcję `wczytaj_bloki_z_pliku()` — reszta
    skryptu jest od formatu niezależna.
"""

import glob
import os
import re
import sys
import statistics
import csv

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# KONFIGURACJA
# ---------------------------------------------------------------------------

KATALOG_WYNIKI = "wyniki"          # gdzie leżą pliki .txt z run_all.sh
KATALOG_WYKRESY = "wykresy"        # gdzie zapisać wykresy
PROG_SEKUNDY = 6.0                 # próg bezpiecznej propagacji [s]

# Parametry scenariuszy (te same, których używałaś). Klucz: (algorytm, tx).
# Wartości: BLOCK_SIZE [B], czas weryfikacji CPU [ms] (z etapu mikro w Rust).
SCENARIUSZE = {
    ("ecdsa", 500):      {"block_size": 125000,   "verif_ms": 33},
    ("ecdsa", 1000):     {"block_size": 250000,   "verif_ms": 65},
    ("ecdsa", 1500):     {"block_size": 375000,   "verif_ms": 110},
    ("ecdsa", 2000):     {"block_size": 500000,   "verif_ms": 161},
    ("dilithium", 500):  {"block_size": 1941000,  "verif_ms": 40},
    ("dilithium", 1000): {"block_size": 3882000,  "verif_ms": 75},
    ("dilithium", 1500): {"block_size": 5823000,  "verif_ms": 129},
    ("dilithium", 2000): {"block_size": 7764000,  "verif_ms": 135},
    ("sphincs", 500):    {"block_size": 4019000,  "verif_ms": 1141},
    ("sphincs", 1000):   {"block_size": 8038000,  "verif_ms": 2282},
    ("sphincs", 1500):   {"block_size": 12057000, "verif_ms": 3410},
    ("sphincs", 2000):   {"block_size": 16076000, "verif_ms": 4938},
}

# Ładne nazwy algorytmów do tytułów wykresów/tabel
NAZWA_ALGO = {"ecdsa": "ECDSA", "dilithium": "Dilithium2 (ML-DSA-44)",
              "sphincs": "SPHINCS+ (SLH-DSA)"}

# ---------------------------------------------------------------------------
# 1. PARSOWANIE POJEDYNCZEGO PLIKU LOGÓW  (jedyne miejsce zależne od formatu)
# ---------------------------------------------------------------------------
#
# RZECZYWISTY FORMAT (dopasowany do Twoich plików, np. ecdsa_500_N500_seed10.txt):
#
#   simblock.block.ProofOfWorkBlock@70177ecd:0     <- nagłówek bloku, po ":" jest
#   123,59                                            WYSOKOŚĆ bloku (height)
#   169,274                                        <- kolejne linie: id_węzła,czas_ms
#   480,356                                           = węzeł 480 odebrał ten blok
#   ...                                                w chwili 356 ms
#   simblock.block.ProofOfWorkBlock@3534651a:1     <- następny blok (height 1)
#   ...
#
# Czyli: każdy nagłówek "simblock.block...:H" zaczyna nowy blok o wysokości H,
# a następujące po nim linie "node,timestamp" to kolejne odbiory tego bloku
# przez węzły sieci. Czas propagacji bloku = (max timestamp - min timestamp)
# wśród jego odbiorców (czas dotarcia do ostatniego węzła od pierwszego).
#
# Bloki osierocone (orphan/stale): jeśli ta sama WYSOKOŚĆ pojawia się w pliku
# więcej niż raz, to znaczy, że powstało kilka konkurencyjnych bloków na tym
# samym poziomie łańcucha — nadmiarowe z nich to forki/orphany.


def wczytaj_bloki_z_pliku(sciezka):
    """
    Parsuje jeden plik i zwraca listę bloków:
        [{"height": H, "recv": [(node_id, czas_ms), ...]}, ...]
    """
    bloki = []
    biezacy = None
    with open(sciezka, encoding="utf-8", errors="ignore") as f:
        for linia in f:
            linia = linia.strip()
            if not linia:
                continue
            if linia.startswith("simblock.block"):
                # nagłówek bloku: ...@hash:HEIGHT
                try:
                    height = int(linia.rsplit(":", 1)[-1])
                except ValueError:
                    height = None
                biezacy = {"height": height, "recv": []}
                bloki.append(biezacy)
            else:
                # linia odbioru: "node_id,timestamp_ms"
                czesci = linia.split(",")
                if len(czesci) == 2 and biezacy is not None:
                    try:
                        node = int(czesci[0])
                        t = int(czesci[1])
                    except ValueError:
                        continue
                    biezacy["recv"].append((node, t))
    return bloki


def statystyki_z_pliku(sciezka):
    """
    Z jednego pliku liczy statystyki propagacji [w SEKUNDACH]:
        liczba_blokow, mean, std, min, max, orphan
    gdzie:
        - czas propagacji bloku = (max t - min t) wśród odbiorców tego bloku,
        - mean/std/min/max liczone po wszystkich blokach (w sekundach),
        - liczba_blokow = liczba zarejestrowanych bloków,
        - orphan = liczba bloków osieroconych = ile bloków powstało PONAD
          liczbę odrębnych wysokości (czyli ile było forków na powtórzonych
          wysokościach).
    Zwraca None, jeśli plik nie zawiera poprawnych danych.
    """
    bloki = wczytaj_bloki_z_pliku(sciezka)
    if not bloki:
        return None

    czasy_prop_s = []      # czas propagacji każdego bloku [s]
    wysokosci = []
    for b in bloki:
        ts = [t for _, t in b["recv"]]
        if len(ts) >= 2:
            czasy_prop_s.append((max(ts) - min(ts)) / 1000.0)
        if b["height"] is not None:
            wysokosci.append(b["height"])

    if not czasy_prop_s:
        return None

    liczba_blokow = len(bloki)
    liczba_wysokosci = len(set(wysokosci)) if wysokosci else liczba_blokow
    orphan = max(0, liczba_blokow - liczba_wysokosci)

    return {
        "liczba_blokow": liczba_blokow,
        "mean": float(np.mean(czasy_prop_s)),
        "std": float(np.std(czasy_prop_s)),
        "min": float(np.min(czasy_prop_s)),
        "max": float(np.max(czasy_prop_s)),
        "orphan": orphan,
    }


# ---------------------------------------------------------------------------
# 2. ZBIERANIE WSZYSTKICH PLIKÓW
# ---------------------------------------------------------------------------
#
# Skrypt rozpoznaje nazwę pliku na kilka sposobów, więc zadziała zarówno dla
# nazw z run_all.sh (algo_tx_N{n}_seed{s}.txt), jak i dla Twoich starszych
# nazw (np. standard_ecdsa_500.txt, dilithium_500.txt, anomalia_sphincs_2000.txt).
#
# Z nazwy pliku odczytujemy: algorytm, liczbę tx, (opcjonalnie) N i seed.
# Jeśli w nazwie NIE MA N, rozmiar sieci jest wykrywany z zawartości pliku
# (liczba różnych węzłów-odbiorców). Jeśli nie ma seeda, plik traktowany jest
# jako pojedyncze uruchomienie (seed nieznany).

# Mapa słów kluczowych w nazwie -> nazwa algorytmu używana w skrypcie.
SLOWA_ALGO = {
    "ecdsa": "ecdsa", "standard": "ecdsa", "secp256k1": "ecdsa",
    "dilithium": "dilithium", "mldsa": "dilithium", "ml-dsa": "dilithium",
    "sphincs": "sphincs", "slhdsa": "sphincs", "slh-dsa": "sphincs",
    "anomalia": "sphincs",   # Twoje pliki anomalia_sphincs_* to SPHINCS+
}


def rozpoznaj_z_nazwy(nazwa):
    """
    Zwraca (algo, tx, N_or_None, seed_or_None) na podstawie nazwy pliku.
    Zwraca None, jeśli nie da się rozpoznać algorytmu i liczby tx.

    Obsługiwane nazwy (przykłady):
        dilithium_500_N500_seed10.txt   -> (dilithium, 500, 500, 10)
        dilithium_500_N1000_seed30.txt  -> (dilithium, 500, 1000, 30)
        ecdsa_2000_N4000_seed100.txt    -> (ecdsa, 2000, 4000, 100)
        standard_ecdsa_500.txt          -> (ecdsa, 500, None, None)
    """
    low = nazwa.lower()

    # algorytm: znajdź pierwsze pasujące słowo kluczowe oraz jego pozycję
    algo = None
    pozycja_algo = -1
    for slowo, a in SLOWA_ALGO.items():
        idx = low.find(slowo)
        if idx != -1:
            algo = a
            pozycja_algo = idx + len(slowo)
            break
    if algo is None:
        return None

    # N: "N<liczba>" (wielka lub mała litera). Zapamiętaj pozycję, by nie
    # pomylić tej liczby z tx.
    mN = re.search(r"[nN](\d{3,5})", nazwa)
    N = int(mN.group(1)) if mN else None
    pozycja_N = mN.start() if mN else None

    # seed
    mS = re.search(r"seed(\d+)", low)
    seed = int(mS.group(1)) if mS else None
    pozycja_seed = mS.start() if mS else None

    # tx: PIERWSZA liczba występująca PO nazwie algorytmu, ale PRZED "N..."
    # i przed "seed..." (bo tx w nazwie stoi zaraz za algorytmem).
    tx = None
    for mm in re.finditer(r"\d+", low):
        poz = mm.start()
        if poz < pozycja_algo:
            continue                      # liczba przed nazwą algorytmu — pomiń
        if pozycja_N is not None and poz >= pozycja_N:
            continue                      # to już liczba N — pomiń
        if pozycja_seed is not None and poz >= pozycja_seed:
            continue                      # to już seed — pomiń
        tx = int(mm.group())
        break
    # awaryjnie: jeśli powyższe nic nie dało, weź pierwszą z typowych wartości
    if tx is None:
        for kand in re.findall(r"\d+", low):
            if int(kand) in (500, 1000, 1500, 2000):
                tx = int(kand)
                break
    if tx is None:
        return None

    return algo, tx, N, seed


def wykryj_N_z_pliku(sciezka):
    """Wykrywa rozmiar sieci = liczba różnych węzłów-odbiorców w pliku."""
    wezly = set()
    with open(sciezka, encoding="utf-8", errors="ignore") as f:
        for linia in f:
            linia = linia.strip()
            if not linia or linia.startswith("simblock.block"):
                continue
            czesci = linia.split(",")
            if len(czesci) == 2:
                try:
                    wezly.add(int(czesci[0]))
                except ValueError:
                    pass
    return len(wezly) if wezly else None


def zbierz_wszystko():
    """
    Przechodzi po wszystkich plikach wyniki/*.txt i grupuje statystyki
    po (algorytm, tx, N), zbierając listy wartości z kolejnych seedów.
    """
    zebrane = {}   # (algo, tx, N) -> {"mean":[...], "std":[...], ...}
    pliki = sorted(glob.glob(os.path.join(KATALOG_WYNIKI, "*.txt")))
    if not pliki:
        print(f"BŁĄD: brak plików w katalogu '{KATALOG_WYNIKI}/'.")
        sys.exit(1)

    rozpoznane = 0
    pominiete = 0
    for sciezka in pliki:
        nazwa = os.path.basename(sciezka)
        rozp = rozpoznaj_z_nazwy(nazwa)
        if rozp is None:
            print(f"  POMIJAM (nie rozpoznano algorytmu/tx w nazwie): {nazwa}")
            pominiete += 1
            continue
        algo, tx, N, seed = rozp

        st = statystyki_z_pliku(sciezka)
        if st is None:
            print(f"  UWAGA: brak danych w {nazwa}")
            pominiete += 1
            continue

        # jeśli N nie było w nazwie — wykryj z treści
        if N is None:
            N = wykryj_N_z_pliku(sciezka)
            if N is None:
                print(f"  UWAGA: nie udało się ustalić N dla {nazwa}")
                pominiete += 1
                continue

        klucz = (algo, tx, N)
        wpis = zebrane.setdefault(klucz, {"liczba_blokow": [], "mean": [],
                                          "std": [], "min": [], "max": [],
                                          "orphan": []})
        for pole in ("liczba_blokow", "mean", "std", "min", "max", "orphan"):
            wpis[pole].append(st[pole])
        rozpoznane += 1

    print(f"     rozpoznano {rozpoznane} plików, pominięto {pominiete}")
    if not zebrane:
        print("BŁĄD: żaden plik nie został rozpoznany. Sprawdź nazwy plików "
              "(oczekiwane np. ecdsa_500_N500_seed10.txt) lub format logów.")
        sys.exit(1)
    return zebrane


def usrednij(zebrane):
    """
    Uśrednia po seedach. Zwraca słownik:
        (algo, tx, N) -> {liczba_blokow, mean, std, min, max, orphan,
                          mean_std_seedy, n_seedow}
    gdzie mean_std_seedy to odchylenie samego Mean między seedami
    (miara wpływu losowej topologii).
    """
    wynik = {}
    for klucz, d in zebrane.items():
        n_seedow = len(d["mean"])
        wynik[klucz] = {
            "liczba_blokow": int(round(np.mean(d["liczba_blokow"]))),
            "mean": float(np.mean(d["mean"])),
            "std": float(np.mean(d["std"])),   # średnia z wewn. Std
            "min": float(np.min(d["min"])),
            "max": float(np.max(d["max"])),
            "orphan": int(round(np.mean(d["orphan"]))),
            "mean_std_seedy": float(np.std(d["mean"])) if n_seedow > 1 else 0.0,
            "n_seedow": n_seedow,
        }
    return wynik


# ---------------------------------------------------------------------------
# 3. TABELE CSV
# ---------------------------------------------------------------------------

ROZMIARY_N = [500, 1000, 1500, 2000, 4000]
LICZBY_TX = [500, 1000, 1500, 2000]
ALGORYTMY = ["ecdsa", "dilithium", "sphincs"]


def zapisz_tabele_skalowalnosc(dane):
    """
    Tabela jak w PQC_v2.docx: dla każdego (algorytm, tx) wiersze po N
    z kolumnami: N, Liczba bloków, Bloki osierocone, Mean, Std, Min, Max [s].
    """
    sciezka = "tabele_skalowalnosc.csv"
    with open(sciezka, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for algo in ALGORYTMY:
            for tx in LICZBY_TX:
                w.writerow([f"{NAZWA_ALGO[algo]} — {tx} tx"])
                w.writerow(["N", "Liczba bloków", "Bloki osierocone",
                            "Mean [s]", "Std [s]", "Min [s]", "Max [s]",
                            "Odchyl. Mean między seedami [s]"])
                for N in ROZMIARY_N:
                    d = dane.get((algo, tx, N))
                    if not d:
                        w.writerow([N, "brak", "brak", "brak", "brak",
                                    "brak", "brak", "brak"])
                        continue
                    w.writerow([
                        N, d["liczba_blokow"], d["orphan"],
                        f'{d["mean"]:.3f}', f'{d["std"]:.3f}',
                        f'{d["min"]:.3f}', f'{d["max"]:.3f}',
                        f'{d["mean_std_seedy"]:.3f}',
                    ])
                w.writerow([])   # pusty wiersz między blokami
    print(f"  zapisano {sciezka}")


def zapisz_tabele_udzial_cpu(dane):
    """
    Tabela udziału weryfikacji CPU w całkowitej propagacji [%]:
    dla każdego (algorytm, tx) wiersze po N z kolumnami:
    N, Czas weryfikacji CPU [s], Mean propagacji [s], Udział [%].
    """
    sciezka = "tabele_udzial_cpu.csv"
    with open(sciezka, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for algo in ALGORYTMY:
            for tx in LICZBY_TX:
                verif_s = SCENARIUSZE[(algo, tx)]["verif_ms"] / 1000.0
                w.writerow([f"{NAZWA_ALGO[algo]} — {tx} tx  "
                            f"(weryfikacja CPU = {verif_s:.3f} s)"])
                w.writerow(["N", "Czas weryfikacji CPU [s]",
                            "Średni czas propagacji (Mean) [s]",
                            "Udział weryfikacji w propagacji [%]"])
                for N in ROZMIARY_N:
                    d = dane.get((algo, tx, N))
                    if not d:
                        w.writerow([N, f"{verif_s:.3f}", "brak", "brak"])
                        continue
                    udzial = 100.0 * verif_s / d["mean"] if d["mean"] > 0 else 0.0
                    w.writerow([
                        N, f"{verif_s:.3f}", f'{d["mean"]:.3f}', f'{udzial:.2f}',
                    ])
                w.writerow([])
    print(f"  zapisano {sciezka}")


# ---------------------------------------------------------------------------
# 4. WYKRESY PROPAGACJI  (jeden na algorytm, 4 serie tx, z pełnym opisem)
# ---------------------------------------------------------------------------

STYLE = {500: ("o", "-"), 1000: ("s", "--"), 1500: ("^", "-."), 2000: ("D", ":")}


def opis_scenariuszy(algo):
    """Buduje wielolinijkowy podpis: block_size i opóźnienie dla każdego tx."""
    linie = []
    for tx in LICZBY_TX:
        s = SCENARIUSZE[(algo, tx)]
        bs_mb = s["block_size"] / 1_000_000
        linie.append(f"{tx} tx: blok ≈ {bs_mb:.2f} MB, weryf. {s['verif_ms']} ms")
    return "\n".join(linie)


def rysuj_propagacje(dane):
    os.makedirs(KATALOG_WYKRESY, exist_ok=True)
    for algo in ALGORYTMY:
        # liczba seedów (bierzemy z dowolnego dostępnego wpisu)
        n_seedow = next((dane[k]["n_seedow"] for k in dane if k[0] == algo), 0)

        fig, ax = plt.subplots(figsize=(9, 5.4))
        for tx in LICZBY_TX:
            xs, ys, errs = [], [], []
            for i, N in enumerate(ROZMIARY_N):
                d = dane.get((algo, tx, N))
                if d:
                    xs.append(i)
                    ys.append(d["mean"])
                    errs.append(d["mean_std_seedy"])
            if not xs:
                continue
            mk, ls = STYLE[tx]
            ax.errorbar(xs, ys, yerr=errs, marker=mk, linestyle=ls,
                        linewidth=1.8, markersize=7, capsize=4, label=f"{tx} tx")

        ax.axhline(PROG_SEKUNDY, color="black", linewidth=1.0,
                   linestyle=(0, (4, 3)))
        ax.text(len(ROZMIARY_N) - 1, PROG_SEKUNDY, f"  próg {PROG_SEKUNDY:.0f} s",
                ha="right", va="bottom", fontsize=9)

        ax.set_xticks(range(len(ROZMIARY_N)))
        ax.set_xticklabels([str(n) for n in ROZMIARY_N])
        ax.set_xlabel("Rozmiar sieci N [liczba węzłów]")
        ax.set_ylabel("Średni czas propagacji (Mean) [s]")
        ax.set_title(f"Średni czas propagacji bloku — {NAZWA_ALGO[algo]}\n"
                     f"(uśrednione z {n_seedow} ziaren losowości; "
                     f"słupki błędów = odchylenie między seedami)")
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(title="Obciążenie bloku", fontsize=9)
        ax.set_ylim(bottom=0)

        # ramka z opisem scenariuszy (block_size + opóźnienie)
        ax.text(0.02, 0.98, opis_scenariuszy(algo), transform=ax.transAxes,
                fontsize=8, va="top", ha="left",
                bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

        fig.tight_layout()
        nazwa = os.path.join(KATALOG_WYKRESY, f"propagacja_{algo}.png")
        fig.savefig(nazwa, dpi=150)
        plt.close(fig)
        print(f"  zapisano {nazwa}")


# ---------------------------------------------------------------------------
# 5. WYKRESY BLOKÓW OSIEROCONYCH (stale/orphan)
# ---------------------------------------------------------------------------
# Liczba bloków osieroconych jest liczona BEZPOŚREDNIO z logów: to liczba
# bloków, które powstały na już zajętej wysokości łańcucha (forki). W parserze
# (funkcja statystyki_z_pliku) jest to pole "orphan" = liczba_bloków - liczba
# odrębnych wysokości. Nie trzeba już nic szacować.


def liczba_osieroconych(d):
    """Liczba bloków osieroconych — bezpośrednio z logów (pole 'orphan')."""
    return d.get("orphan", 0)


def rysuj_osierocone(dane):
    os.makedirs(KATALOG_WYKRESY, exist_ok=True)
    for algo in ALGORYTMY:
        n_seedow = next((dane[k]["n_seedow"] for k in dane if k[0] == algo), 0)
        fig, ax = plt.subplots(figsize=(9, 5.4))
        for tx in LICZBY_TX:
            xs, ys = [], []
            for i, N in enumerate(ROZMIARY_N):
                d = dane.get((algo, tx, N))
                if d:
                    xs.append(i)
                    ys.append(liczba_osieroconych(d))
            if not xs:
                continue
            mk, ls = STYLE[tx]
            ax.plot(xs, ys, marker=mk, linestyle=ls, linewidth=1.8,
                    markersize=7, label=f"{tx} tx")

        ax.set_xticks(range(len(ROZMIARY_N)))
        ax.set_xticklabels([str(n) for n in ROZMIARY_N])
        ax.set_xlabel("Rozmiar sieci N [liczba węzłów]")
        ax.set_ylabel("Liczba bloków osieroconych (stale/orphan)")
        ax.set_title(f"Liczba bloków osieroconych — {NAZWA_ALGO[algo]}\n"
                     f"(uśrednione z {n_seedow} ziaren losowości)")
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(title="Obciążenie bloku", fontsize=9)
        ax.set_ylim(bottom=0)
        fig.tight_layout()
        nazwa = os.path.join(KATALOG_WYKRESY, f"osierocone_{algo}.png")
        fig.savefig(nazwa, dpi=150)
        plt.close(fig)
        print(f"  zapisano {nazwa}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

WERSJA_SKRYPTU = "2024-v3 (parser SimBlock + wykrywanie N + diagnostyka)"


def diagnostyka(zebrane, dane):
    """
    Wypisuje przejrzysty raport: ile plików trafiło do każdej kombinacji
    (algorytm, tx, N) oraz ostrzega, jeśli wszystkie wartości Mean są takie
    same (typowy objaw: wszystkie pliki mają identyczną treść albo trafiły
    do jednej kombinacji).
    """
    print("\n--- DIAGNOSTYKA WCZYTANYCH DANYCH ---")
    print(f"    wersja skryptu: {WERSJA_SKRYPTU}")
    # ile plików na każdą kombinację
    puste = 0
    for algo in ALGORYTMY:
        for tx in LICZBY_TX:
            for N in ROZMIARY_N:
                d = dane.get((algo, tx, N))
                liczba_plikow = len(zebrane.get((algo, tx, N), {}).get("mean", []))
                if liczba_plikow == 0:
                    puste += 1
    wypelnione = len(dane)
    print(f"    kombinacji z danymi: {wypelnione} / 60   (pustych: {puste})")

    # sprawdź, czy wszystkie Mean są identyczne
    wszystkie_mean = [round(d["mean"], 3) for d in dane.values()]
    if len(wszystkie_mean) > 1 and len(set(wszystkie_mean)) == 1:
        print("    !!! OSTRZEŻENIE: wszystkie wartości Mean są IDENTYCZNE.")
        print("        Najczęstsze przyczyny:")
        print("        1) wszystkie pliki .txt mają tę samą treść (np. skopiowane),")
        print("        2) uruchomiono STARĄ wersję skryptu.")
        print("        Sprawdź, czy pliki różnią się zawartością oraz czy używasz")
        print(f"        tej wersji: {WERSJA_SKRYPTU}")
    elif wypelnione <= 1:
        print("    UWAGA: znaleziono dane tylko dla jednej kombinacji.")
        print("        Pozostałe scenariusze będą oznaczone jako 'brak'.")
        print("        Wgraj komplet plików (3 algorytmy × 4 tx × 5 N × seedy).")
    print("-------------------------------------\n")


def main():
    print(f"=== analiza_wynikow.py  [{WERSJA_SKRYPTU}] ===")
    print("1/5  Zbieranie plików wynikowych...")
    zebrane = zbierz_wszystko()
    print(f"     znaleziono {len(zebrane)} kombinacji (algorytm, tx, N)")

    print("2/5  Uśrednianie po seedach...")
    dane = usrednij(zebrane)

    diagnostyka(zebrane, dane)

    print("3/5  Tabela skalowalności (N, liczba bloków, Mean, Std, Min, Max)...")
    zapisz_tabele_skalowalnosc(dane)

    print("4/5  Tabela udziału weryfikacji CPU [%]...")
    zapisz_tabele_udzial_cpu(dane)

    print("5/5  Wykresy propagacji i bloków osieroconych...")
    rysuj_propagacje(dane)
    rysuj_osierocone(dane)

    print("\nGOTOWE.")
    print("  Tabele:  tabele_skalowalnosc.csv, tabele_udzial_cpu.csv")
    print(f"  Wykresy: {KATALOG_WYKRESY}/propagacja_*.png, {KATALOG_WYKRESY}/osierocone_*.png")


if __name__ == "__main__":
    main()

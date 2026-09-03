#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
statystyki_mikro.py

Liczy statystyki (mediana, srednia, odchylenie standardowe, min, max)
z powtorzonych mikrotestow Rust. Wczytuje pliki:
    wyniki_ecdsa.csv, wyniki_dilithium.csv, wyniki_sphincs.csv
(kazdy: algorytm,tx_count,powtorzenie,czas_ms) i tworzy:
    - mikrotesty_statystyki.csv  (tabela zbiorcza do pracy)
    - w konsoli: wartosci verifms do wpisania do SimBlock (mediana zaokraglona)

URUCHOMIENIE:
    python3 statystyki_mikro.py

WYMAGANIA:
    pip install pandas numpy
"""

import glob
import csv
import statistics

import numpy as np


PLIKI = ["wyniki_ecdsa.csv", "wyniki_dilithium.csv", "wyniki_sphincs.csv"]

# tx_count, ktore trafiaja do pracy jako glowne scenariusze (500..2000)
GLOWNE_TX = [500, 1000, 1500, 2000]


def wczytaj_csv(sciezka):
    """Zwraca dict: (algo, tx_count) -> lista czasow [ms] ze wszystkich powtorzen."""
    dane = {}
    try:
        with open(sciezka, encoding="utf-8") as f:
            czytnik = csv.DictReader(f)
            for wiersz in czytnik:
                algo = wiersz["algorytm"].strip()
                tx = int(wiersz["tx_count"])
                czas = float(wiersz["czas_ms"])
                dane.setdefault((algo, tx), []).append(czas)
    except FileNotFoundError:
        print(f"  UWAGA: brak pliku {sciezka} - pomijam")
    return dane


def main():
    wszystko = {}
    for p in PLIKI:
        wszystko.update(wczytaj_csv(p))

    if not wszystko:
        print("BLAD: nie znaleziono zadnych plikow CSV z mikrotestow.")
        print("Uruchom najpierw benchmarki Rust (cargo run --release).")
        return

    # posortuj klucze wg algorytmu i tx
    klucze = sorted(wszystko.keys(), key=lambda k: (k[0], k[1]))

    # zapisz tabele zbiorcza
    with open("mikrotesty_statystyki.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Algorytm", "Liczba tx", "Liczba powtorzen",
                    "Mediana [ms]", "Srednia [ms]", "Odchylenie std [ms]",
                    "Min [ms]", "Max [ms]"])
        for (algo, tx) in klucze:
            czasy = wszystko[(algo, tx)]
            mediana = statistics.median(czasy)
            srednia = statistics.mean(czasy)
            odchyl = statistics.stdev(czasy) if len(czasy) > 1 else 0.0
            w.writerow([
                algo, tx, len(czasy),
                f"{mediana:.3f}", f"{srednia:.3f}", f"{odchyl:.3f}",
                f"{min(czasy):.3f}", f"{max(czasy):.3f}",
            ])

    print("Zapisano tabele: mikrotesty_statystyki.csv\n")

    # wypisz wartosci verifms do SimBlock (mediana zaokraglona do calosci)
    print("=== WARTOSCI blockVerificationTimeMs DO SIMBLOCK (mediana, ms) ===")
    print("   (uzyj tych liczb jako -Dverifms=... dla kazdego scenariusza)\n")
    print(f"{'Algorytm':12s} {'tx':>5s} {'mediana[ms]':>12s} {'verifms':>8s}")
    for (algo, tx) in klucze:
        if tx not in GLOWNE_TX:
            continue
        mediana = statistics.median(wszystko[(algo, tx)])
        print(f"{algo:12s} {tx:5d} {mediana:12.3f} {round(mediana):8d}")

    print("\n=== SPRAWDZENIE ANOMALII (czy czas rosnie z liczba tx) ===")
    for algo in sorted({k[0] for k in klucze}):
        pary = [(tx, statistics.median(wszystko[(algo, tx)]))
                for (a, tx) in klucze if a == algo]
        pary.sort()
        print(f"\n{algo}:")
        poprzednia = None
        for tx, med in pary:
            znak = ""
            if poprzednia is not None and med < poprzednia:
                znak = "  <-- SPADEK (sprawdz, czy to nie szum)"
            print(f"   {tx:5d} tx -> mediana {med:8.3f} ms{znak}")
            poprzednia = med


if __name__ == "__main__":
    main()

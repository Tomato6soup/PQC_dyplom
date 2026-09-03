#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sprawdz_pliki.py

Szybka diagnostyka: sprawdza, czy pliki w katalogu wyniki/ RÓŻNIĄ SIĘ
zawartością, czy są identyczne. Uruchom, jeśli w tabelach wychodzą
wszędzie te same liczby.

    python3 sprawdz_pliki.py
"""

import glob
import hashlib
import os

KATALOG = "wyniki"

pliki = sorted(glob.glob(os.path.join(KATALOG, "*.txt")))
if not pliki:
    print(f"Brak plików w '{KATALOG}/'.")
    raise SystemExit(1)

print(f"Znaleziono {len(pliki)} plików w '{KATALOG}/'.\n")

# policz skrót (hash) treści każdego pliku
skroty = {}
for p in pliki:
    tresc = open(p, "rb").read()
    h = hashlib.md5(tresc).hexdigest()
    skroty.setdefault(h, []).append(os.path.basename(p))

print(f"Liczba RÓŻNYCH (unikalnych) treści: {len(skroty)} / {len(pliki)}\n")

if len(skroty) == 1:
    print("!!! WSZYSTKIE pliki mają IDENTYCZNĄ treść.")
    print("    To jest przyczyna tych samych liczb w tabelach.")
    print("    Musisz wygenerować pliki na nowo — każdy scenariusz osobno")
    print("    (różne BLOCK_SIZE / verifms / N / seed dają różną treść).")
elif len(skroty) < len(pliki):
    grupy_dup = {h: n for h, n in skroty.items() if len(n) > 1}
    liczba_dup_plikow = sum(len(n) for n in grupy_dup.values())
    print(f"UWAGA: {liczba_dup_plikow} plików ma identyczną treść "
          f"({len(grupy_dup)} grup duplikatów).\n")
    print("Każda grupa to pliki, które SimBlock policzył identycznie mimo")
    print("różnych nazw — w tych uruchomieniach parametr (seed / N / tx) NIE")
    print("zadziałał (najczęściej: brak przebudowy ./gradlew build -x test po")
    print("zmianie, albo System.getProperty nie jest czytane w kodzie).\n")

    print("--- PLIKI DO WYGENEROWANIA NA NOWO ---")
    # z każdej grupy zostaw pierwszy, resztę oznacz do regeneracji
    do_regeneracji = []
    for h, nazwy in grupy_dup.items():
        for n in sorted(nazwy)[1:]:   # wszystkie oprócz pierwszego
            do_regeneracji.append(n)
    for n in sorted(do_regeneracji):
        print(f"  {n}")
    print(f"\nRazem do ponownego wygenerowania: {len(do_regeneracji)} plików.")
    print("Wygeneruj je ponownie (najlepiej skryptem run_all.sh, który")
    print("automatycznie ustawia właściwe parametry dla każdego scenariusza).")

    # zapisz listę do pliku, by łatwo było jej użyć
    with open("do_regeneracji.txt", "w") as f:
        for n in sorted(do_regeneracji):
            f.write(n + "\n")
    print("\nLista zapisana też w pliku: do_regeneracji.txt")
else:
    print("OK: wszystkie pliki mają różną treść.")
    print("    Jeśli mimo to tabele pokazują te same liczby, znaczy to, że")
    print("    uruchomiono STARĄ wersję analiza_wynikow.py. Użyj wersji")
    print("    oznaczonej jako '2024-v3' (widać ją w nagłówku po uruchomieniu).")

# pokaż też, ile plików przypada na każdą parę (algorytm, tx) wg nazwy
print("\n--- Rozkład plików wg nazwy (algorytm_tx) ---")
from collections import Counter
licznik = Counter()
for p in pliki:
    nazwa = os.path.basename(p).lower()
    # zgrubny podział po pierwszych dwóch członach nazwy
    czlony = nazwa.replace(".txt", "").split("_")
    if len(czlony) >= 2:
        licznik[f"{czlony[0]}_{czlony[1]}"] += 1
    else:
        licznik[nazwa] += 1
for klucz, ile in sorted(licznik.items()):
    print(f"  {klucz:25s}: {ile} plików")

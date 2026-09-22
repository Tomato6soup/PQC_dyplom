#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
etap3_wykresy.py
Generuje wykresy z pliku obciazenie_statystyka_pelna_FINALNA.csv
dla pracy inzynierskiej (PQC w blockchainie): ecdsa vs dilithium2 vs sphincs.

Uzycie:
    python etap3_wykresy.py [sciezka_do_csv] [folder_wyjsciowy]

Domyslnie:
    CSV:  ./obciazenie_statystyka_pelna_FINALNA.csv
    Wyjscie: ./wykresy/
"""

import sys
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ---------- Konfiguracja ----------

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "obciazenie_statystyka_pelna_FINALNA.csv"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "wykresy"

ALGO_ORDER = ["ecdsa", "dilithium2", "sphincs"]
ALGO_LABELS = {"ecdsa": "ECDSA (klasyczny)", "dilithium2": "Dilithium2 (PQC)", "sphincs": "SPHINCS+ (PQC)"}
ALGO_COLORS = {"ecdsa": "#1f77b4", "dilithium2": "#2ca02c", "sphincs": "#d62728"}
ALGO_MARKERS = {"ecdsa": "o", "dilithium2": "s", "sphincs": "^"}

plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 150,
    "font.size": 11,
    "axes.grid": True,
    "grid.alpha": 0.3,
})

os.makedirs(OUT_DIR, exist_ok=True)


def load_data(path):
    df = pd.read_csv(path)
    expected = {
        "Algorytm", "Uzytkownicy", "Czas_testu_s", "Liczba_probek",
        "RPS_mean", "RPS_std", "TPS_mean", "TPS_std",
        "Mediana_ms_mean", "P95_ms_mean", "P99_ms_mean",
        "CPU_mean", "RAM_mean", "Failures_total",
    }
    missing = expected - set(df.columns)
    if missing:
        print(f"UWAGA: brakuje kolumn w CSV: {missing}")
    df["Algorytm"] = pd.Categorical(df["Algorytm"], categories=ALGO_ORDER, ordered=True)
    df = df.sort_values(["Algorytm", "Uzytkownicy", "Czas_testu_s"])
    return df


def savefig(fig, name):
    path = os.path.join(OUT_DIR, name)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  zapisano: {path}")


# ---------- Wykresy ----------

def plot_metric_vs_users_by_T(df, metric_mean, metric_std, ylabel, title, filename, T_values=(30, 60, 90)):
    """Osobny subplot dla kazdego czasu testu T, X=Uzytkownicy, linie=algorytmy."""
    fig, axes = plt.subplots(1, len(T_values), figsize=(5.5 * len(T_values), 4.5), sharey=True)
    if len(T_values) == 1:
        axes = [axes]
    for ax, T in zip(axes, T_values):
        sub = df[df["Czas_testu_s"] == T]
        for algo in ALGO_ORDER:
            s = sub[sub["Algorytm"] == algo].sort_values("Uzytkownicy")
            if s.empty:
                continue
            yerr = s[metric_std] if metric_std in s.columns else None
            ax.errorbar(
                s["Uzytkownicy"], s[metric_mean], yerr=yerr,
                label=ALGO_LABELS[algo], color=ALGO_COLORS[algo],
                marker=ALGO_MARKERS[algo], capsize=3, linewidth=1.8, markersize=6,
            )
        ax.set_title(f"T = {T}s")
        ax.set_xlabel("Liczba uzytkownikow")
    axes[0].set_ylabel(ylabel)
    axes[0].legend(loc="best", fontsize=9)
    fig.suptitle(title)
    savefig(fig, filename)


def plot_metric_vs_users_avgT(df, metric_mean, ylabel, title, filename):
    """Jeden wykres, usrednione po T, X=Uzytkownicy, linie=algorytmy."""
    fig, ax = plt.subplots(figsize=(7, 5))
    grouped = df.groupby(["Algorytm", "Uzytkownicy"], observed=True)[metric_mean].mean().reset_index()
    for algo in ALGO_ORDER:
        s = grouped[grouped["Algorytm"] == algo].sort_values("Uzytkownicy")
        if s.empty:
            continue
        ax.plot(
            s["Uzytkownicy"], s[metric_mean],
            label=ALGO_LABELS[algo], color=ALGO_COLORS[algo],
            marker=ALGO_MARKERS[algo], linewidth=2, markersize=7,
        )
    ax.set_xlabel("Liczba uzytkownikow")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(loc="best")
    savefig(fig, filename)


def plot_latency_percentiles(df, T=90):
    """3 subploty: Mediana / P95 / P99, X=Uzytkownicy, linie=algorytmy, dla wybranego T."""
    sub = df[df["Czas_testu_s"] == T]
    metrics = [
        ("Mediana_ms_mean", "Mediana [ms]"),
        ("P95_ms_mean", "P95 [ms]"),
        ("P99_ms_mean", "P99 [ms]"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharex=True)
    for ax, (col, label) in zip(axes, metrics):
        for algo in ALGO_ORDER:
            s = sub[sub["Algorytm"] == algo].sort_values("Uzytkownicy")
            if s.empty:
                continue
            ax.plot(
                s["Uzytkownicy"], s[col],
                label=ALGO_LABELS[algo], color=ALGO_COLORS[algo],
                marker=ALGO_MARKERS[algo], linewidth=1.8, markersize=6,
            )
        ax.set_xlabel("Liczba uzytkownikow")
        ax.set_ylabel(label)
        ax.set_title(label)
    axes[0].legend(loc="best", fontsize=9)
    fig.suptitle(f"Opoznienia w funkcji obciazenia (T = {T}s)")
    savefig(fig, f"04_latencje_percentyle_T{T}.png")


def plot_failures(df):
    """Failures_total vs Uzytkownicy, osobne subploty per T, slupki grupowane po algorytmie."""
    T_values = sorted(df["Czas_testu_s"].unique())
    fig, axes = plt.subplots(1, len(T_values), figsize=(5.5 * len(T_values), 4.5), sharey=True)
    if len(T_values) == 1:
        axes = [axes]
    users = sorted(df["Uzytkownicy"].unique())
    width = 0.25
    for ax, T in zip(axes, T_values):
        sub = df[df["Czas_testu_s"] == T]
        for i, algo in enumerate(ALGO_ORDER):
            s = sub[sub["Algorytm"] == algo].set_index("Uzytkownicy").reindex(users)
            xpos = [u + (i - 1) * width for u in range(len(users))]
            ax.bar(xpos, s["Failures_total"].fillna(0), width=width,
                   label=ALGO_LABELS[algo], color=ALGO_COLORS[algo])
        ax.set_xticks(range(len(users)))
        ax.set_xticklabels(users)
        ax.set_xlabel("Liczba uzytkownikow")
        ax.set_title(f"T = {T}s")
        ax.set_yscale("symlog")
    axes[0].set_ylabel("Liczba bledow (Failures_total, skala symlog)")
    axes[0].legend(loc="best", fontsize=9)
    fig.suptitle("Liczba bledow w funkcji obciazenia")
    savefig(fig, "06_failures.png")


def main():
    print(f"Wczytuje: {CSV_PATH}")
    df = load_data(CSV_PATH)
    print(f"Wczytano {len(df)} wierszy, algorytmy: {df['Algorytm'].unique().tolist()}")

    print("Generuje wykresy...")

    plot_metric_vs_users_by_T(
        df, "RPS_mean", "RPS_std", "RPS (zapytania/s)",
        "Przepustowosc (RPS) w funkcji liczby uzytkownikow", "01_rps_vs_users_by_T.png",
    )
    plot_metric_vs_users_by_T(
        df, "TPS_mean", "TPS_std", "TPS (transakcje/s)",
        "Przepustowosc udanych transakcji (TPS) w funkcji liczby uzytkownikow", "02_tps_vs_users_by_T.png",
    )
    plot_metric_vs_users_avgT(
        df, "RPS_mean", "RPS (zapytania/s), srednia po T",
        "Porownanie algorytmow: RPS (usrednione po czasie testu)", "03_rps_avg_comparison.png",
    )
    plot_latency_percentiles(df, T=90)
    plot_metric_vs_users_by_T(
        df, "CPU_mean", "CPU_std", "CPU [%]",
        "Zuzycie CPU w funkcji liczby uzytkownikow", "05_cpu_vs_users_by_T.png",
    )
    plot_metric_vs_users_by_T(
        df, "RAM_mean", "RAM_std", "RAM [MB]",
        "Zuzycie RAM w funkcji liczby uzytkownikow", "05b_ram_vs_users_by_T.png",
    )
    plot_failures(df)

    print(f"\nGotowe. Wszystkie wykresy zapisane w: {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()

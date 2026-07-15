"""Runner backtest Mean Reversion sesi Asia: baseline + grid 18 varian
→ results/mr_report.md + mr_equity_ideal.png.

Pakai: PYTHONIOENCODING=utf-8 py -m backtest.run_mr_backtest
"""
import itertools
import os
import time
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from backtest.loader import load_m1_csv
from backtest.mr_params import MRParams, MR_BASELINE
from backtest.mr_simulator import simulate_mr
from backtest.metrics import (trade_stats, equity_ideal, equity_real,
                              max_drawdown_pct, status_counts, monthly_r)

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data", "xauusd_m1.csv")
RESULTS = os.path.join(HERE, "results")

K_ENTRIES = [2.0, 2.5, 3.0]
K_SLS = [1.0, 1.5, 2.0]
WINDOWS = [30, 60]

# Styling (dataviz skill) — disalin dari run_backtest.py agar kedua report
# konsisten: single-series line di surface terang, seri = slot kategorikal 1
# (biru), chrome (ink/grid/axis) pakai token teks, bukan default matplotlib.
CHART_SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE_AXIS = "#c3c2b7"
SERIES_1 = "#2a78d6"
SANS_FONT = ["Segoe UI", "DejaVu Sans", "Arial", "sans-serif"]


def run_variant(df, p: MRParams) -> dict:
    days = simulate_mr(df, p)
    trades = [d.trade for d in days if d.trade is not None]
    stats = trade_stats(trades)
    eq_ideal = equity_ideal(trades)
    return {
        "params": p, "days": days, "trades": trades, "stats": stats,
        "eq_ideal": eq_ideal, "max_dd": max_drawdown_pct(eq_ideal),
        "statuses": status_counts(days),
    }


def fmt_row(v: dict) -> str:
    p, s = v["params"], v["stats"]
    star = " ★" if p == MR_BASELINE else ""
    return (f"| {p.window} | {p.k_entry} | {p.k_sl} | "
            f"{s['n']} | {s['winrate']:.1f}% | "
            f"{s['profit_factor']:.2f} | {s['expectancy_r']:+.3f} | "
            f"{v['max_dd']:.1f}% |{star}")


def write_report(variants: list[dict], base: dict, eq_real: list, df) -> str:
    trades, s = base["trades"], base["stats"]
    sc = base["statuses"]
    exits = Counter(t.exit_reason for t in trades)
    holds = sorted(t.hold_minutes for t in trades)
    median_hold = holds[len(holds) // 2] if holds else 0.0

    lines = [
        "# Hasil Backtest Mean Reversion Sesi Asia XAUUSD",
        "",
        f"Data: HistData.com M1 bid, {df.index[0]:%Y-%m-%d} s/d {df.index[-1]:%Y-%m-%d} "
        f"({len(df):,} bar). Spread tetap ${MR_BASELINE.spread:.2f}. "
        "Sesi Asia 07:00–14:00 WIB; sinyal di close bar (SMA ± k×std rolling, "
        "hanya bar sesi hari itu), entry di open bar berikutnya, maksimal satu "
        "trade per hari, tutup paksa 14:00. Asumsi worst-case: SL menang di bar yang sama.",
        "",
        f"## Baseline ({MR_BASELINE.label()})",
        "",
        f"- Trade: **{s['n']}** | Winrate: **{s['winrate']:.1f}%** | "
        f"Profit factor: **{s['profit_factor']:.2f}** | "
        f"Expectancy: **{s['expectancy_r']:+.3f}R** | Max DD (ideal 1%): **{base['max_dd']:.1f}%**",
        f"- Hari: traded {sc.get('traded', 0)}, no_signal {sc.get('no_signal', 0)}, "
        f"tanpa data {sc.get('no_data', 0)}",
        f"- Exit: tp {exits.get('tp', 0)}, sl {exits.get('sl', 0)}, "
        f"session_end {exits.get('session_end', 0)}, end_of_data {exits.get('end_of_data', 0)}",
        f"- Median hold: {median_hold:.0f} menit",
        "",
        "### Simulasi akun",
        "",
        f"1. **Ideal** (risk 1%, lot fraksional, mulai $10.000): "
        f"akhir **${base['eq_ideal'][-1]:,.2f}**, max DD {base['max_dd']:.1f}%",
        f"2. **Riil $100 + floor MIN_LOT 0.01** (replikasi bot): "
        f"akhir **${eq_real[-1]:,.2f}** setelah {len(eq_real) - 1} trade"
        + (" — **AKUN HABIS**" if eq_real[-1] <= 0 else "")
        + f", max DD {max_drawdown_pct(eq_real):.1f}%",
        "",
        "### R bulanan (baseline)",
        "",
        "| Bulan | R |", "|---|---|",
    ]
    lines += [f"| {m} | {r:+.2f} |" for m, r in monthly_r(trades).items()]
    lines += [
        "",
        f"## Grid {len(variants)} varian (urut expectancy)",
        "",
        "| Window | k_entry | k_sl | N | Winrate | PF | Exp (R) | MaxDD | |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    ranked = sorted(variants, key=lambda v: v["stats"]["expectancy_r"], reverse=True)
    lines += [fmt_row(v) for v in ranked]
    lines += ["", "★ = baseline (MR_BASELINE)", ""]
    return "\n".join(lines)


def plot_equity(eq: list, path: str) -> None:
    # Styling per skill `dataviz`: satu seri → tanpa kotak legend (judul
    # menamai serinya); garis 2px slot kategorikal 1 (biru); gridline hairline
    # recessive; teks chrome pakai ink muted/secondary, bukan warna seri;
    # direct label di ujung garis (satu-satunya titik yang jadi cerita).
    fig, ax = plt.subplots(figsize=(9, 4.5))
    fig.patch.set_facecolor(CHART_SURFACE)
    ax.set_facecolor(CHART_SURFACE)

    x = range(len(eq))
    ax.plot(x, eq, color=SERIES_1, linewidth=2, solid_capstyle="round",
            solid_joinstyle="round")
    ax.scatter([x[-1]], [eq[-1]], s=64, color=SERIES_1,
               edgecolors=CHART_SURFACE, linewidths=2, zorder=3)
    ax.annotate(f"${eq[-1]:,.0f}", xy=(x[-1], eq[-1]),
                xytext=(6, 0), textcoords="offset points",
                va="center", ha="left", fontsize=10, color=INK_PRIMARY,
                fontfamily=SANS_FONT)

    ax.set_title("Equity — MR sesi Asia, risk 1% ideal (mulai $10.000)",
                 fontsize=13, color=INK_PRIMARY, fontfamily=SANS_FONT,
                 pad=12, loc="left")
    ax.set_xlabel("Trade #", fontsize=10, color=INK_SECONDARY, fontfamily=SANS_FONT)
    ax.set_ylabel("Balance (USD)", fontsize=10, color=INK_SECONDARY, fontfamily=SANS_FONT)

    ax.grid(True, axis="y", color=GRIDLINE, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)
    for spine_name, spine in ax.spines.items():
        if spine_name == "bottom":
            spine.set_color(BASELINE_AXIS)
            spine.set_linewidth(1)
        else:
            spine.set_visible(False)
    ax.tick_params(colors=INK_MUTED, labelsize=9, length=0)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontfamily(SANS_FONT)

    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=CHART_SURFACE)
    plt.close(fig)


def main():
    print("Memuat data...")
    df = load_m1_csv(DATA)
    print(f"{len(df):,} bar, {df.index[0]} → {df.index[-1]}")

    os.makedirs(RESULTS, exist_ok=True)
    variants = []
    combos = list(itertools.product(WINDOWS, K_ENTRIES, K_SLS))
    start = time.time()
    for i, (w, ke, ks) in enumerate(combos, 1):
        p = MRParams(window=w, k_entry=ke, k_sl=ks)
        print(f"[{i}/{len(combos)}] {p.label()} (elapsed {time.time() - start:.0f}s)")
        try:
            variants.append(run_variant(df, p))
        except Exception as exc:
            print(f"GAGAL {p.label()}: {exc!r}")

    if not variants:
        raise RuntimeError(
            f"Semua {len(combos)} varian gagal — tidak ada hasil untuk dilaporkan.")

    base = next((v for v in variants if v["params"] == MR_BASELINE), None)
    if base is None:
        raise RuntimeError("Varian baseline gagal — mr_report.md butuh baseline.")

    eq_real = equity_real(base["trades"])
    report = write_report(variants, base, eq_real, df)
    report_path = os.path.join(RESULTS, "mr_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    plot_equity(base["eq_ideal"], os.path.join(RESULTS, "mr_equity_ideal.png"))
    n_failed = len(combos) - len(variants)
    if n_failed:
        print(f"Peringatan: {n_failed}/{len(combos)} varian gagal, dilewati.")
    print(f"Selesai → {report_path}")


if __name__ == "__main__":
    main()

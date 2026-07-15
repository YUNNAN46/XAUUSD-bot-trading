"""Runner backtest: baseline + grid 36 varian → results/report.md + PNG.

Pakai: py backtest/run_backtest.py            # full run
       py backtest/run_backtest.py --audit 2025-03-04   # detail satu hari (baseline)
"""
import argparse
import itertools
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from backtest.loader import load_m1_csv
from backtest.params import Params, BASELINE
from backtest.simulator import simulate
from backtest.metrics import (trade_stats, equity_ideal, equity_real,
                              max_drawdown_pct, status_counts, monthly_r)

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data", "xauusd_m1.csv")
RESULTS = os.path.join(HERE, "results")

SL_MODES = ["opposite", "mid"]
TP_RRS = [1.5, 2.0, 3.0]
RANGE_MAXES = [25.0, 35.0, 50.0]
TP1_OPTIONS = [True, False]

# Styling (dataviz skill): single-series line chart on the light chart surface.
# Series color = categorical slot 1 (blue); chrome (ink/grid/axis) uses the
# skill's text/gridline tokens rather than matplotlib defaults.
CHART_SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE_AXIS = "#c3c2b7"
SERIES_1 = "#2a78d6"
SANS_FONT = ["Segoe UI", "DejaVu Sans", "Arial", "sans-serif"]


def run_variant(df, p: Params) -> dict:
    days = simulate(df, p)
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
    star = " ★" if p == BASELINE else ""
    return (f"| {p.sl_mode} | {p.tp_rr} | {p.range_max:.0f} | "
            f"{'on' if p.tp1_enabled else 'off'} | {s['n']} | {s['winrate']:.1f}% | "
            f"{s['profit_factor']:.2f} | {s['expectancy_r']:+.3f} | "
            f"{v['max_dd']:.1f}% |{star}")


def write_report(variants: list[dict], df) -> str:
    base = next(v for v in variants if v["params"] == BASELINE)
    trades, s, days = base["trades"], base["stats"], base["days"]
    sc = base["statuses"]
    eq_real = equity_real(trades)
    n_cross_mid = sum(1 for t in trades if t.crossed_midnight)
    n_cross_wk = sum(1 for t in trades if t.crossed_weekend)
    n_whipsaw = sum(1 for d in days if d.whipsaw)
    holds = sorted(t.hold_minutes for t in trades)
    median_hold = holds[len(holds) // 2] / 60 if holds else 0.0

    lines = [
        "# Hasil Backtest London Breakout XAUUSD",
        "",
        f"Data: Dukascopy M1 bid, {df.index[0]:%Y-%m-%d} s/d {df.index[-1]:%Y-%m-%d} "
        f"({len(df):,} bar). Spread tetap ${BASELINE.spread:.2f}. "
        "Asumsi worst-case: SL menang di bar yang sama.",
        "",
        "## Baseline (konfigurasi bot saat ini)",
        "",
        f"- Trade: **{s['n']}** | Winrate: **{s['winrate']:.1f}%** | "
        f"Profit factor: **{s['profit_factor']:.2f}** | "
        f"Expectancy: **{s['expectancy_r']:+.3f}R** | Max DD (ideal 1%): **{base['max_dd']:.1f}%**",
        f"- Hari: traded {sc.get('traded', 0)}, no_breakout {sc.get('no_breakout', 0)}, "
        f"range sempit {sc.get('range_invalid_narrow', 0)}, range lebar {sc.get('range_invalid_wide', 0)}, "
        f"pre-broken {sc.get('pre_broken', 0)}, tanpa data {sc.get('no_data', 0)}",
        f"- Whipsaw (dua sisi tersentuh di menit yang sama): {n_whipsaw} hari",
        f"- Median hold: {median_hold:.1f} jam | Menginap: {n_cross_mid} trade | "
        f"Lewat weekend: {n_cross_wk} trade",
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
        "## Grid 36 varian (urut expectancy)",
        "",
        "| SL | TP_RR | RangeMax | TP1 | N | Winrate | PF | Exp (R) | MaxDD | |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    ranked = sorted(variants, key=lambda v: v["stats"]["expectancy_r"], reverse=True)
    lines += [fmt_row(v) for v in ranked]
    lines += ["", "★ = baseline (konfigurasi bot saat ini)", ""]
    return "\n".join(lines)


def plot_equity(base: dict, path_ideal: str, path_real: str) -> None:
    # Styling per skill `dataviz`: single series → no legend box (the title
    # names the series); 2px line in categorical slot 1 (blue); recessive
    # hairline gridlines one step off the chart surface; chrome text in
    # muted/secondary ink, never the series color; direct label at the line's
    # end (the one point the story is about) instead of labeling every point.
    for eq, path, title in [
        (base["eq_ideal"], path_ideal, "Equity — risk 1% ideal (mulai $10.000)"),
        (equity_real(base["trades"]), path_real, "Equity — akun riil $100, floor MIN_LOT 0.01"),
    ]:
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

        ax.set_title(title, fontsize=13, color=INK_PRIMARY, fontfamily=SANS_FONT,
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


def audit_day(df, date_str: str) -> None:
    import pandas as pd
    day_df = df[df.index.date == pd.Timestamp(date_str).date()]
    results = simulate(day_df, BASELINE)
    for r in results:
        print(f"{r.date} status={r.status} range={r.range_size} whipsaw={r.whipsaw}")
        if r.trade:
            t = r.trade
            print(f"  {t.direction.upper()} entry={t.entry} @ {t.entry_time} "
                  f"SL={t.sl} TP1={t.tp1} TP2={t.tp2}")
            print(f"  exit={t.exit_reason} @ {t.exit_time} r={t.r_multiple:+.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", metavar="YYYY-MM-DD")
    args = ap.parse_args()

    print("Memuat data...")
    df = load_m1_csv(DATA)
    print(f"{len(df):,} bar, {df.index[0]} → {df.index[-1]}")

    if args.audit:
        audit_day(df, args.audit)
        return

    os.makedirs(RESULTS, exist_ok=True)
    variants = []
    combos = list(itertools.product(SL_MODES, TP_RRS, RANGE_MAXES, TP1_OPTIONS))
    for i, (sl, rr, rmax, tp1) in enumerate(combos, 1):
        p = Params(sl_mode=sl, tp_rr=rr, range_max=rmax, tp1_enabled=tp1)
        print(f"[{i}/{len(combos)}] {p.label()}")
        variants.append(run_variant(df, p))

    report = write_report(variants, df)
    report_path = os.path.join(RESULTS, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    base = next(v for v in variants if v["params"] == BASELINE)
    plot_equity(base,
                os.path.join(RESULTS, "equity_ideal.png"),
                os.path.join(RESULTS, "equity_real_100usd.png"))
    print(f"Selesai → {report_path}")


if __name__ == "__main__":
    main()

# Backtest London Breakout XAUUSD — Design

**Tanggal:** 2026-07-15
**Status:** Disetujui user
**Tujuan:** Membuktikan secara statistik apakah strategi London Breakout di bot (commit `1d38295` dst.) layak dijalankan live, dan parameter mana yang lebih baik — sebelum memperbaiki isu lain (sizing MIN_LOT, breakeven, time-exit).

## 1. Data

- **Sumber:** Dukascopy, XAUUSD M1, periode **Juli 2023 – Juli 2026** (3 tahun).
- **Downloader:** `dukascopy-node` via `npx` (utama); fallback downloader Python langsung ke API bi5 Dukascopy jika Node tidak tersedia di mesin ini.
- **Timezone:** timestamp Dukascopy UTC → dikonversi ke WIB (Asia/Jakarta, UTC+7) untuk seluruh logika sesi.
- **Penyimpanan:** hasil unduhan disimpan sekali sebagai CSV/Parquet di `backtest/data/` (di-gitignore) supaya unduhan tidak diulang tiap run.

## 2. Engine

Script Python di folder `backtest/` (terpisah dari `bot/`, tidak menyentuh kode bot). Memproses bar M1 hari per hari, mereplikasi aturan bot persis:

- **Range Asia:** high/low dari bar M1 07:00–13:59 WIB. Valid jika `RANGE_MIN (5.0) <= range <= RANGE_MAX (35.0)` USD.
- **Penempatan order (14:50 WIB):**
  - Buy Stop = `asian_high + 0.5`, SL = `asian_low − 0.3`
  - Sell Stop = `asian_low − 0.5`, SL = `asian_high + 0.3`
  - TP = `1.5 × range` dari harga entry masing-masing sisi.
- **OCO:** sisi pertama yang ter-trigger membatalkan sisi lain.
- **Expiry:** pending yang tidak ter-trigger dibatalkan pukul 17:00 WIB.
- **Manajemen posisi:** TP1 = midpoint(entry, TP2) → tutup 50% posisi + SL pindah ke breakeven (entry). Sisa 50% jalan ke TP2 atau SL. Tanpa time-exit (sesuai bot saat ini).
- **Statistik tambahan:** durasi hold per trade, jumlah posisi yang menginap (melewati 00:00 WIB) dan yang melewati weekend.

## 3. Asumsi Eksekusi

Semua konservatif dan configurable via konstanta di script:

| Asumsi | Nilai | Alasan |
|---|---|---|
| Spread | $0.30 tetap, ditambahkan ke sisi ask | Data Dukascopy = bid |
| SL & TP tersentuh di bar yang sama | **SL duluan** | Worst case, tidak menggelembungkan hasil |
| Satu bar menembus kedua stop (whipsaw <1 menit) | Sisi yang lebih dekat ke open bar trigger duluan, sisi lain batal; dihitung sebagai statistik whipsaw | Meniru OCO bot yang polling 2 detik |
| Harga di 14:50 sudah melewati level stop | Hari dicatat "pre-broken, skip" | Meniru kegagalan pending order bot asli (retcode 10015) |
| Slippage | 0 (baseline), parameter tersedia | Bisa diuji sensitivitasnya belakangan |

## 4. Variasi Parameter

Baseline = konfigurasi bot saat ini. Variasi:

| Dimensi | Nilai |
|---|---|
| Posisi SL | Seberang range (baseline) vs **tengah range** (RR efektif ~3:1) |
| TP_RR | **1.5** (baseline), 2.0, 3.0 |
| RANGE_MAX | 25, **35** (baseline), 50 |
| TP1 partial + breakeven | **On** (baseline) vs off |

Grid penuh 36 kombinasi (2×3×3×2) dilaporkan, tapi pembacaan difokuskan pada variasi satu-dimensi dari baseline untuk menghindari overfitting.

> **Update 2026-07-16:** grid diperluas ke 72 kombinasi dengan dimensi kelima `trend_filter` (none | d1_ema — hanya pasang sisi searah tren EMA10/EMA30 harian, dihitung dari data s/d H-1). Lihat commit `8fc997c`/`bfaf63e`.

## 5. Output & Metrik

Laporan markdown + grafik equity curve (PNG) di `backtest/results/`:

- **Per varian:** jumlah trade, winrate, profit factor, expectancy (dalam R), max drawdown, breakdown bulanan, breakdown hari skip (range invalid / tidak ada breakout / pre-broken / whipsaw).
- **Dua simulasi akun:**
  1. Risk 1% compounding ideal (lot fraksional) — mengukur kualitas murni strategi.
  2. Akun riil $100 dengan floor MIN_LOT 0.01 — mengukur dampak masalah sizing yang ditemukan saat penilaian (risiko riil 15–35% per trade).

## 6. Verifikasi

- Unit test untuk logika fill dengan bar buatan tangan: TP+SL di bar sama, whipsaw dua sisi, expiry tanpa trigger, alur TP1 → breakeven → TP2/BE.
- Audit manual 2–3 hari sampel: bandingkan hasil simulator dengan hitungan tangan dari data mentah.

## Batasan yang Disadari

- Granularitas M1 (bukan tick): urutan pergerakan intra-bar tidak diketahui — ditangani dengan asumsi worst-case di atas.
- Spread tetap $0.30 tidak menangkap pelebaran spread saat London open / berita; hasil nyata bisa sedikit lebih buruk.
- Harga Dukascopy ≠ harga broker user; level breakout bisa berbeda beberapa puluh sen.
- News blackout filter TIDAK disimulasikan (butuh kalender historis 3 tahun); dampaknya kecil karena blackout hanya mencegah penempatan di 14:50, dan berita besar USD umumnya jatuh setelah expiry 17:00 WIB.

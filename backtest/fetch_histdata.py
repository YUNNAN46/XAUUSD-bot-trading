"""Unduh XAUUSD M1 dari HistData.com ke backtest/data/xauusd_m1.csv.

Alternatif untuk backtest/download_data.py (Dukascopy) — dipakai karena
datafeed.dukascopy.com diblokir oleh ISP/jaringan user, sedangkan
histdata.com bisa diakses dari environment ini.

Perbedaan format sumber vs backtest/loader.py (Dukascopy-oriented):
- HistData generic ASCII: "YYYYMMDD HHMMSS;open;high;low;close;volume",
  tanpa header, delimiter titik-koma, timestamp fixed EST (UTC-5, TANPA DST).
- volume HistData SELALU 0 (data volume tidak tersedia di format ini) —
  beda dengan Dukascopy, di mana volume==0 menandai bar flat sintetis
  (pasar tutup) yang harus dibuang oleh load_m1_csv(). Karena sumber
  HistData sudah otomatis mengecualikan periode market tutup, setiap baris
  adalah bar trading asli, jadi volume TIDAK dipakai sebagai filter di sini.
  Untuk menghindari load_m1_csv() salah membuang baris ini (karena filter
  df["volume"] > 0), volume di-set ke placeholder nonzero (1) saat menulis
  output.
"""
import glob
import os
import shutil
import sys
import zipfile
from datetime import datetime, timedelta, timezone

from histdata import download_hist_data as dl
from histdata.api import Platform, TimeFrame

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TARGET = os.path.join(DATA_DIR, "xauusd_m1.csv")
PAIR = "xauusd"

# Rentang data: 2023-07-01 s.d. bulan lengkap terakhir sebelum bulan berjalan.
# Hari ini 2026-07-16 → Juli 2026 belum lengkap, jadi berhenti di Juni 2026.
FULL_YEARS = [2023, 2024, 2025]
CURRENT_YEAR = 2026
CURRENT_YEAR_MONTHS = list(range(1, 7))  # Jan..Jun 2026 (bulan lengkap)

HEADER = "timestamp,open,high,low,close,volume\n"
EST_FIXED_OFFSET = timezone(timedelta(hours=-5))


def parse_histdata_timestamp(raw: str) -> int:
    """Parse 'YYYYMMDD HHMMSS' (fixed EST/UTC-5, tanpa DST) → epoch ms UTC."""
    dt_naive = datetime.strptime(raw, "%Y%m%d %H%M%S")
    dt_est = dt_naive.replace(tzinfo=EST_FIXED_OFFSET)
    dt_utc = dt_est.astimezone(timezone.utc)
    return int(dt_utc.timestamp() * 1000)


def convert_histdata_line(line: str) -> str:
    """Konversi satu baris HistData (';'-delimited) → baris CSV format load_m1_csv().

    Volume di-set ke 1 (placeholder) — lihat penjelasan di docstring modul:
    load_m1_csv() membuang baris volume==0 untuk mendeteksi bar flat sintetis
    Dukascopy, tapi HistData selalu melaporkan volume=0 untuk SEMUA baris
    (termasuk bar trading asli), jadi filter itu tidak relevan di sini dan
    placeholder nonzero mencegah baris asli ikut terbuang.
    """
    ts_raw, o, h, l, c, _vol = line.strip().split(";")
    ts_ms = parse_histdata_timestamp(ts_raw)
    return f"{ts_ms},{o},{h},{l},{c},1"


def _download_all(tmp_dir: str) -> list:
    """Unduh semua zip tahun/bulan yang dibutuhkan, return list path zip."""
    zip_paths = []
    for year in FULL_YEARS:
        path = dl(year=str(year), pair=PAIR, platform=Platform.GENERIC_ASCII,
                  time_frame=TimeFrame.ONE_MINUTE, output_directory=tmp_dir)
        zip_paths.append(path)
    for month in CURRENT_YEAR_MONTHS:
        path = dl(year=str(CURRENT_YEAR), month=str(month), pair=PAIR,
                  platform=Platform.GENERIC_ASCII, time_frame=TimeFrame.ONE_MINUTE,
                  output_directory=tmp_dir)
        zip_paths.append(path)
    return zip_paths


def _extract_and_convert(zip_path: str, tmp_dir: str) -> list:
    """Ekstrak satu zip, konversi tiap baris CSV di dalamnya → list baris output."""
    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            sys.exit(f"Tidak ada CSV di dalam {zip_path}")
        zf.extractall(tmp_dir)

    rows = []
    for csv_name in csv_names:
        csv_path = os.path.join(tmp_dir, csv_name)
        with open(csv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(convert_histdata_line(line))
        os.remove(csv_path)
    return rows


def main():
    if os.path.exists(TARGET):
        print(f"{TARGET} sudah ada — skip download. Hapus file untuk mengunduh ulang.")
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    tmp_dir = os.path.join(DATA_DIR, "_tmp_histdata")
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        zip_paths = _download_all(tmp_dir)

        all_rows = []
        for zip_path in zip_paths:
            all_rows.extend(_extract_and_convert(zip_path, tmp_dir))
            os.remove(zip_path)

        if not all_rows:
            sys.exit("Tidak ada data yang terunduh/terkonversi.")

        # Dedup berdasarkan timestamp (jaga-jaga kalau ada overlap batas tahun/bulan),
        # lalu urutkan kronologis.
        seen = {}
        for row in all_rows:
            ts_ms = row.split(",", 1)[0]
            seen[ts_ms] = row
        sorted_rows = [seen[k] for k in sorted(seen, key=int)]

        with open(TARGET, "w", encoding="utf-8") as f:
            f.write(HEADER)
            for row in sorted_rows:
                f.write(row + "\n")

        size_mb = os.path.getsize(TARGET) / 1e6
        print(f"OK: {TARGET} ({size_mb:.1f} MB, {len(sorted_rows)} baris)")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        # Bersihkan sisa zip/csv HistData yang mungkin ter-download langsung
        # ke DATA_DIR (bukan tmp_dir) di versi library lain.
        for pattern in ("DAT_ASCII_XAUUSD_*.zip", "DAT_ASCII_XAUUSD_*.csv"):
            for leftover in glob.glob(os.path.join(DATA_DIR, pattern)):
                os.remove(leftover)


if __name__ == "__main__":
    main()

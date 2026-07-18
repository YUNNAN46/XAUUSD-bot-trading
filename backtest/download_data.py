"""Unduh XAUUSD M1 (bid) dari Dukascopy via dukascopy-node ke backtest/data/xauusd_m1.csv."""
import glob
import os
import shutil
import subprocess
import sys

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TARGET = os.path.join(DATA_DIR, "xauusd_m1.csv")
DATE_FROM = "2023-07-01"
DATE_TO = "2026-07-15"


def main():
    if os.path.exists(TARGET):
        print(f"{TARGET} sudah ada — skip download. Hapus file untuk mengunduh ulang.")
        return
    cmd = [
        "npx", "dukascopy-node",
        "--instrument", "xauusd",
        "--date-from", DATE_FROM,
        "--date-to", DATE_TO,
        "--timeframe", "m1",
        "--format", "csv",
        "--volumes",
        "--directory", DATA_DIR,
        "--retries", "5",
    ]
    print("Menjalankan:", " ".join(cmd))
    subprocess.run(cmd, check=True, shell=(os.name == "nt"))
    produced = glob.glob(os.path.join(DATA_DIR, "xauusd-m1-*.csv"))
    if not produced:
        sys.exit("Download selesai tapi tidak ada file xauusd-m1-*.csv di backtest/data/")
    shutil.move(max(produced, key=os.path.getmtime), TARGET)
    size_mb = os.path.getsize(TARGET) / 1e6
    print(f"OK: {TARGET} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

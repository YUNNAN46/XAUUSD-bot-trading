import pandas as pd

WIB = "Asia/Jakarta"


def load_m1_csv(path_or_buf) -> pd.DataFrame:
    """CSV dukascopy-node (timestamp ms UTC, bid OHLCV) → DataFrame OHLC index WIB.

    Bar dengan volume 0 (bar flat sintetis saat pasar tutup) dibuang.
    """
    df = pd.read_csv(path_or_buf)
    df = df[df["volume"] > 0]
    idx = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert(WIB)
    out = df[["open", "high", "low", "close"]].copy()
    out.index = idx
    out.index.name = "time"
    return out.sort_index()

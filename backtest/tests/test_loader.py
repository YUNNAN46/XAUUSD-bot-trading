import io
import pandas as pd
from backtest.loader import load_m1_csv

CSV = """timestamp,open,high,low,close,volume
1704067200000,2062.5,2063.0,2062.0,2062.8,120.5
1704067260000,2062.8,2064.0,2062.5,2063.5,98.0
1704067320000,2063.5,2063.5,2063.5,2063.5,0
"""


def test_load_converts_to_wib_and_drops_zero_volume():
    df = load_m1_csv(io.StringIO(CSV))
    # 1704067200000 ms = 2024-01-01 00:00 UTC = 07:00 WIB
    assert str(df.index.tz) == "Asia/Jakarta"
    assert df.index[0].hour == 7 and df.index[0].minute == 0
    assert list(df.columns) == ["open", "high", "low", "close"]
    assert len(df) == 2  # baris volume 0 (bar sintetis flat) dibuang
    assert df.iloc[1]["high"] == 2064.0

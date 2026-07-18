import pandas as pd

WIB = "Asia/Jakarta"

# Bar Asia standar: menghasilkan high 2005 / low 1995 (range 10.30 dgn spread 0.30)
ASIAN_BARS = [
    ("07:00", 2000.0, 2005.0, 1995.0, 2001.0),
    ("13:00", 2001.0, 2004.0, 1996.0, 2000.0),
]


def make_bars(date_str: str, bars: list[tuple]) -> pd.DataFrame:
    """bars: list of ('HH:MM', open, high, low, close) → DataFrame index WIB."""
    idx = pd.DatetimeIndex(
        [f"{date_str} {hhmm}" for hhmm, *_ in bars]
    ).tz_localize(WIB)
    df = pd.DataFrame(
        [list(vals) for _, *vals in bars],
        columns=["open", "high", "low", "close"],
        index=idx,
    )
    df.index.name = "time"
    return df


def make_day(date_str: str, window_bars: list[tuple],
             asian_bars: list[tuple] = None) -> pd.DataFrame:
    return make_bars(date_str, (asian_bars or ASIAN_BARS) + window_bars)

from dataclasses import dataclass


@dataclass(frozen=True)
class Params:
    range_min: float = 5.0       # USD — skip jika range Asia < ini
    range_max: float = 35.0      # USD — skip jika range Asia > ini
    entry_buffer: float = 0.5    # USD di luar tepi range
    sl_buffer: float = 0.3       # USD di luar tepi seberang (mode 'opposite')
    tp_rr: float = 1.5           # TP = tp_rr × range dari entry
    sl_mode: str = "opposite"    # 'opposite' (baseline bot) | 'mid' (tengah range)
    tp1_enabled: bool = True     # TP1 midpoint + partial 50% + SL→BE
    spread: float = 0.30         # USD — data bid, ask = bid + spread
    slippage: float = 0.0        # USD — memperburuk harga entry stop order
    trend_filter: str = "none"   # 'none' (straddle dua sisi) | 'd1_ema' (satu sisi searah tren D1)

    def label(self) -> str:
        return (f"sl={self.sl_mode} tp_rr={self.tp_rr} "
                f"range_max={self.range_max} tp1={'on' if self.tp1_enabled else 'off'} "
                f"trend={self.trend_filter}")


BASELINE = Params()

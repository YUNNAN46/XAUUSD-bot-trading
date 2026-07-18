from dataclasses import dataclass


@dataclass(frozen=True)
class MRParams:
    window: int = 60        # jendela rolling (bar M1 sesi) untuk mean & volatilitas
    k_entry: float = 2.5    # ambang entry dalam satuan std rolling
    k_sl: float = 1.5       # jarak SL di luar entry, dalam satuan std rolling
    spread: float = 0.30    # USD — data bid, ask = bid + spread (konvensi sama dgn LB)

    def label(self) -> str:
        return f"window={self.window} k_entry={self.k_entry} k_sl={self.k_sl}"


MR_BASELINE = MRParams()

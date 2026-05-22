# Design Doc: Signal Strategy V2 — EMA Channel 4-Phase State Machine

**Tanggal:** 2026-05-22
**Status:** Approved — siap implementasi
**Bahasa komunikasi:** Bahasa Indonesia

---

## 1. Latar Belakang & Masalah

Strategi sinyal V1 (`signal_generator.py`) tidak menghasilkan trade selama 3 hari karena terlalu ketat:

- **RSI exact cross 50** — hanya memicu di candle tepat saat RSI menyeberangi 50. Jika RSI sudah di atas 50 saat trend berubah, sinyal tidak pernah muncul.
- **Price < BB midline untuk BUY** — saat trend bullish kuat, harga justru sering berada di atas BB midline, sehingga kondisi ini hampir tidak pernah terpenuhi bersamaan.
- Ketiga kondisi (RSI cross + BB midline + pullback) harus terpenuhi **sekaligus pada candle yang sama**.

---

## 2. Solusi

Ganti logika entry M15 dengan **4-phase state machine berbasis EMA channel breakout**, terinspirasi dari repo [backtrader-pullback-window-xauusd](https://github.com/ilahuerta-IA/backtrader-pullback-window-xauusd) (WR 55.43%, PF 1.64, +44.75% return 5 tahun).

H1 trend filter (EMA20/50) dipertahankan karena sudah terbukti.

---

## 3. Target Performa

| Metrik | Target |
|---|---|
| Frekuensi trade | 1–2 per hari |
| Win rate | ≥ 55% |
| Risk/Reward TP1 | 1.5:1 |
| Risk/Reward TP2 | 4:1 |
| Max drawdown | < 15% |

---

## 4. Arsitektur Perubahan

Hanya 2 file yang berubah:

| File | Perubahan |
|---|---|
| `bot/signal_generator.py` | Ganti `get_signal()` dengan class `SignalStateMachine` |
| `bot/signal_watcher.py` | Ganti pemanggilan `get_signal()` → `state_machine.tick()` |
| `/app/state.json` | File baru — state persistence (dibuat otomatis) |

File lain (`trade_filter.py`, `money_management.py`, `telegram_alert.py`, `mt5_connector.py`) **tidak berubah**.

---

## 5. Indikator yang Digunakan

| Indikator | Timeframe | Parameter | Fungsi |
|---|---|---|---|
| EMA 20 | H1 | window=20 | Trend filter (tetap dari V1) |
| EMA 50 | H1 | window=50 | Trend filter (tetap dari V1) |
| EMA 14 | M15 | window=14 | Fast EMA untuk crossover |
| EMA 24 | M15 | window=24 | Slow EMA untuk crossover |
| ATR 14 | M15 | window=14 | SL dinamis + volatility filter |

---

## 6. Filter Baru

### 6.1 ATR Extreme Volatility Filter

Mencegah entry saat volatilitas ekstrem (news tidak terjadwal, spike mendadak):

```python
atr_current = ATR(14).iloc[-1]
atr_avg     = ATR(14).rolling(20).mean().iloc[-1]

if atr_current > atr_avg * ATR_EXTREME_MULTIPLIER:  # default 1.8
    return 'NONE', None
```

Melengkapi news blackout filter yang sudah ada (ForexFactory). News filter menangkap event terjadwal, ATR filter menangkap spike tidak terjadwal.

### 6.2 EMA Slope Filter

Mencegah entry saat pasar sideways (EMA terlalu datar):

```python
slope = ema14.iloc[-1] - ema14.iloc[-4]  # perubahan EMA14 dalam 3 candle

if abs(slope) < EMA_MIN_SLOPE:  # default 0.5 (tunable)
    return  # skip crossover — momentum tidak cukup
```

---

## 7. 4-Phase State Machine

### 7.1 Diagram Fase

```
[SCANNING] ──EMA crossover──→ [ARMED] ──pullback terdeteksi──→ [WINDOW_OPEN] ──breakout──→ [ENTRY]
    ↑                              │                                   │
    └──────timeout / invalidasi────┘───────────timeout / invalidasi────┘
```

### 7.2 Detail Setiap Fase

#### PHASE 1: SCANNING

Bot memantau crossover EMA14 vs EMA24 di M15, selaras dengan trend H1.

**Kondisi masuk ke ARMED:**
- Trend H1 BULLISH + EMA14 cross **di atas** EMA24: `prev_ema14 < prev_ema24` dan `curr_ema14 >= curr_ema24` → direction = BUY
- Trend H1 BEARISH + EMA14 cross **di bawah** EMA24: `prev_ema14 > prev_ema24` dan `curr_ema14 <= curr_ema24` → direction = SELL
- EMA slope `abs(slope) >= EMA_MIN_SLOPE` (filter sideways)

**Tetap SCANNING jika:**
- H1 trend tidak jelas (EMA20 == EMA50)
- ATR ekstrem (ATR_current > ATR_avg × 1.8)
- EMA slope terlalu datar

#### PHASE 2: ARMED

Bot menunggu pullback counter-trend setelah crossover.

**Kondisi masuk ke WINDOW_OPEN:**
- BUY setup: minimal 1 candle bearish (close < open) dalam `PULLBACK_MAX_CANDLES` candle
- SELL setup: minimal 1 candle bullish (close > open) dalam `PULLBACK_MAX_CANDLES` candle

**Reset ke SCANNING jika:**
- Sudah `ARMED_TIMEOUT_CANDLES` (default 5) candle berlalu tanpa pullback
- EMA crossover berbalik arah (EMA14 kembali melewati EMA24 berlawanan)
- H1 trend berubah arah

#### PHASE 3: WINDOW_OPEN

Bot menetapkan level breakout dan memantau apakah harga menembus level tersebut.

**Set breakout level:**
- BUY:  `breakout_level = max(HIGH dari candle-candle pullback)`
- SELL: `breakout_level = min(LOW dari candle-candle pullback)`

**Kondisi masuk ke ENTRY:**
- BUY:  `close_M15 > breakout_level`
- SELL: `close_M15 < breakout_level`

**Reset ke SCANNING jika:**
- Sudah `ENTRY_WINDOW_CANDLES` (default 2) candle berlalu tanpa breakout
- H1 trend berubah arah

#### PHASE 4: ENTRY

Return sinyal dan reset ke SCANNING.

```
signal = direction  ('BUY' atau 'SELL')
sl     = price ± (SL_ATR_MULTIPLIER × ATR)   # 2.0x ATR
```

---

## 8. Money Management — Adjustment dari V1

| Parameter | V1 (Sekarang) | V2 (Baru) | Alasan |
|---|---|---|---|
| SL multiplier | 1.5x ATR | **2.0x ATR** | Beri ruang lebih untuk spike Gold |
| TP1 RR | 1:1 | **1.5:1** | Lock profit lebih jauh sebelum breakeven |
| TP2 RR | 3:1 | **4:1** | Lebih ambisius, sesuai karakter Gold trending |
| Lot sizing | 1% risk | 1% risk | Tidak berubah |
| Partial close TP1 | 50% | 50% | Tidak berubah |

TP1/TP2 dihitung dari SL distance seperti sebelumnya di `money_management.py`.

---

## 9. State Persistence

State disimpan di `/app/state.json`, auto-recover saat Docker container restart.

**Format:**
```json
{
  "phase": "ARMED",
  "direction": "BUY",
  "crossover_candle_time": 1716300000,
  "pullback_count": 1,
  "pullback_high": 3245.80,
  "pullback_low": 3243.10,
  "breakout_level": null,
  "armed_candles_elapsed": 2,
  "window_candles_elapsed": 0
}
```

- `pullback_high` / `pullback_low` — high/low tertinggi/terendah dari candle pullback, dipakai untuk set `breakout_level` di fase WINDOW_OPEN.

State di-save setiap kali fase berubah. Saat SCANNING, file dihapus atau di-reset.

---

## 10. Konstanta Konfigurasi Baru (`signal_generator.py`)

```python
# EMA periods
EMA_FAST_PERIOD   = 14
EMA_SLOW_PERIOD   = 24

# State machine timeouts
PULLBACK_MAX_CANDLES    = 3   # max candle pullback di fase ARMED
ARMED_TIMEOUT_CANDLES   = 5   # timeout fase ARMED
ENTRY_WINDOW_CANDLES    = 2   # window breakout di fase WINDOW_OPEN

# Filters
ATR_EXTREME_MULTIPLIER  = 1.8   # ATR current > avg × nilai ini → skip
EMA_MIN_SLOPE           = 0.5   # minimum slope EMA14 per 3 candle ($)

# Money management
SL_ATR_MULTIPLIER       = 2.0   # SL = 2.0x ATR (naik dari 1.5x)
```

`TARGET_RR` di `config.py` diubah dari 3.0 → 4.0 untuk TP2.
`TP1_RR` ditambahkan sebagai konstanta baru di `config.py` (default 1.5) — dipakai oleh `money_management.py` untuk menghitung harga TP1. Saat ini TP1 di-hardcode sebagai 1:1 di `money_management.py`, perlu diganti menggunakan `config.TP1_RR`.

---

## 11. Referensi

- [ilahuerta-IA/backtrader-pullback-window-xauusd](https://github.com/ilahuerta-IA/backtrader-pullback-window-xauusd) — WR 55.43%, PF 1.64, +44.75% return 5 tahun di M5 XAUUSD
- Strategi V1: `docs/superpowers/specs/2026-05-19-trading-bot-design.md`

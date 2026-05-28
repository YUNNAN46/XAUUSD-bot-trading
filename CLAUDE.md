# CLAUDE.md — XAU/USD Trading Bot

## Project Overview

Automated trading bot untuk XAU/USD (Gold) menggunakan MetaTrader 5 (MT5), dijalankan via Docker. Bot mengeksekusi sinyal secara otomatis dan mengirim notifikasi lewat Telegram.

## Architecture

```
main.py (TradingBot)
├── MT5Connector       — koneksi & order ke MT5 via gRPC/socket
├── SignalWatcher      — loop utama: cek sinyal, kelola trade, TP1/breakeven
│   ├── signal_generator.py  — H1 trend + M15 entry signal
│   ├── trade_filter.py      — filter jam, news blackout, spread, drawdown
│   ├── news_filter.py       — ForexFactory kalender High-Impact USD
│   └── money_management.py  — lot size, TP price, drawdown check
└── TelegramAlert      — notifikasi & command handler (/status, /pause, dll)
```

## Signal Strategy (V2 — EMA Channel 4-Phase State Machine)

**Trend (H1):** EMA 20 vs EMA 50
- EMA20 > EMA50 → BULLISH
- EMA20 < EMA50 → BEARISH

**Entry (M15):** 4-phase state machine via `SignalStateMachine` di `signal_generator.py`

1. **SCANNING** — deteksi EMA14 cross EMA24, selaras trend H1. Syarat: `abs(slope) >= 0.5`
2. **ARMED** — tunggu pullback (candle counter-trend). Timeout **75 menit** (5 × 15 menit M15).
3. **WINDOW_OPEN** — set breakout level (high pullback untuk BUY, low untuk SELL). Timeout **30 menit** (2 × 15 menit M15).
4. **ENTRY** — harga tembus breakout level → sinyal BUY/SELL + SL

Timeout menggunakan **wall-clock timestamp** (`armed_at`, `window_opened_at`) bukan counter tick — penting karena tick berjalan setiap 2 detik sehingga counter candle tidak akurat.

State disimpan di `/app/state.json` untuk recovery saat Docker restart.

**Filter tambahan:**
- ATR extreme: `atr_current > atr_avg * 1.8` → skip entry (spike tidak terjadwal)
- EMA slope: `abs(slope) < 0.5` → skip crossover (pasar sideways)

**Stop Loss:** Dinamis = 2.0x ATR(14) dari entry price
**TP1:** 1.5:1 RR — close 50% posisi + SL pindah ke breakeven
**TP2:** Target RR dari config (default 4.0x) — sisa 50% posisi

## Trade Filters (`trade_filter.py`)

Order hanya dibuka jika semua filter lolos:
1. **Jam aktif** — 15:00–19:00 WIB (London) atau 20:00–23:59 WIB (NY overlap)
2. **News blackout** — blokir N menit sebelum/sesudah High-Impact USD news
3. **Max open trades** — default 2 posisi simultan
4. **Spread filter** — max 80 points
5. **Daily loss** — stop jika loss harian >= MAX_LOSS_PER_DAY %

## News Filter (`news_filter.py`)

- Sumber: ForexFactory JSON API (`ff_calendar_thisweek.json`)
- Hanya filter event **High** impact, currency **USD**
- Cache per hari (fetch ulang tiap hari baru)
- **Fail-open**: jika API gagal, trading tetap diizinkan (tidak blokir)
- Window: `NEWS_BLACKOUT_BEFORE` menit sebelum + `NEWS_BLACKOUT_AFTER` menit sesudah

## Key Config (`bot/config.py`)

| Variable | Default | Keterangan |
|---|---|---|
| `BALANCE_AWAL` | 100 | Balance awal USD |
| `RISK_PER_TRADE` | 1.0% | Risk per trade |
| `TARGET_RR` | 4.0 | Risk/Reward untuk TP2 |
| `TP1_RR` | 1.5 | Risk/Reward untuk TP1 |
| `MAX_LOSS_PER_DAY` | 3.0% | Max daily loss |
| `MAX_DRAWDOWN` | 15.0% | Max total drawdown |
| `MAX_OPEN_TRADES` | 2 | Max posisi terbuka |
| `SPREAD_FILTER` | 80 | Max spread (points) |
| `NEWS_BLACKOUT_BEFORE` | 30 | Menit sebelum berita |
| `NEWS_BLACKOUT_AFTER` | 15 | Menit setelah berita |
| `POLL_INTERVAL_SECONDS` | 2 | Frekuensi tick loop |

Semua config bisa di-override via environment variable atau `.env` file.

## Telegram Commands

| Command | Fungsi |
|---|---|
| `/status` | Balance, equity, open trades, status bot |
| `/trades` | Detail semua posisi aktif |
| `/laporan` | Ringkasan P&L hari ini |
| `/pause` | Pause bot (tidak buka trade baru) |
| `/resume` | Lanjutkan bot |
| `/help` | Daftar command |

**Notifikasi otomatis:** trade buka/tutup, TP1 hit + breakeven, news blackout on/off, daily loss, drawdown limit, heartbeat jam 08:00 WIB, laporan harian jam 23:59 WIB.

## Module Map

| File | Tanggung Jawab |
|---|---|
| `main.py` | Entry point, orchestrator, daily reset, heartbeat |
| `signal_watcher.py` | Tick loop, TP1/breakeven manager, drawdown check |
| `signal_generator.py` | Kalkulasi sinyal BUY/SELL/NONE |
| `trade_filter.py` | Gate untuk open order |
| `news_filter.py` | ForexFactory kalender, blackout window |
| `money_management.py` | Lot size, TP price, drawdown check |
| `mt5_connector.py` | Koneksi MT5, open/close/modify order |
| `telegram_alert.py` | Bot Telegram, format pesan, command handler |
| `config.py` | Semua konfigurasi dari env var |
| `logger.py` | Setup logging |

## Running Tests

```bash
cd bot
pytest tests/
```

Test coverage ada untuk: `news_filter`, `signal_generator`, `signal_watcher`, `trade_filter`, `money_management`, `mt5_connector`.

## Docker

Proyek dijalankan via Docker Compose. MT5 berjalan di container terpisah (Wine + MT5 terminal), bot Python di container lain. Lihat `Dockerfile` dan `docker-compose.yml` di root.

## Development Notes

- Timezone WIB (Asia/Jakarta / UTC+7) digunakan untuk jam trading dan daily reset
- `SIGNAL_COOLDOWN_SECONDS = 900` — cooldown 15 menit antar sinyal (1 M15 candle)
- Heartbeat log setiap ~5 menit (60 tick × 2 detik)
- TP1 partial close skip jika `half_vol < MIN_LOT` — biarkan TP2 close semua
- `is_news_blackout()` fail-open: jika API ForexFactory tidak bisa diakses, trading tetap jalan
- **Jangan gunakan counter tick untuk timeout M15** — tick berjalan setiap 2 detik, bukan per candle. Selalu gunakan `time.time()` timestamp untuk timeout berbasis durasi waktu.
- Setiap tick log menampilkan `Phase: SCANNING/ARMED/WINDOW_OPEN` beserta direction dan pullback count untuk monitoring.

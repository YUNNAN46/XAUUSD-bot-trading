# CLAUDE.md — XAU/USD Trading Bot

## Project Overview

Automated trading bot untuk XAU/USD (Gold) menggunakan MetaTrader 5 (MT5), dijalankan via Docker. Bot mengeksekusi sinyal secara otomatis dan mengirim notifikasi lewat Telegram.

## Architecture

```
main.py (TradingBot)
├── MT5Connector       — koneksi & order ke MT5 via gRPC/socket
├── SignalWatcher      — loop utama: London Breakout state machine, kelola trade, TP1/breakeven
│   ├── signal_generator.py  — LondonBreakoutStrategy: Asian range + pending order calc
│   ├── trade_filter.py      — filter jam, news blackout, spread, drawdown
│   ├── news_filter.py       — ForexFactory kalender High-Impact USD
│   └── money_management.py  — lot size, TP price, drawdown check
└── TelegramAlert      — notifikasi & command handler (/status, /pause, dll)
```

## Signal Strategy (V3 — London Breakout, time-based state machine)

Strategi berbasis **waktu**, bukan indikator EMA. Logika di `LondonBreakoutStrategy` (`signal_generator.py`) untuk kalkulasi, dan state machine di `SignalWatcher._update_london_breakout()`.

**Fase (`_london_state`): IDLE → COLLECTING → ORDERS_SET → EXPIRED**

1. **COLLECTING (07:00–14:00 WIB)** — rekam Asian range (high/low) dari live tick tiap loop.
2. **ORDERS_SET (pasang @ 14:50 WIB)** — pasang **2 pending stop order sekaligus** (OCO):
   - Buy Stop = `asian_high + BREAKOUT_BUFFER_USD`, SL = `asian_low - SL_BUFFER_USD`
   - Sell Stop = `asian_low - BREAKOUT_BUFFER_USD`, SL = `asian_high + SL_BUFFER_USD`
   - TP = `range × TP_RR_BREAKOUT` (default 1.5) dari entry
3. **OCO monitoring (14:50–17:00 WIB)** — jika satu order tereksekusi (hilang dari pending), order satunya dibatalkan. Jika **keduanya** tereksekusi (whipsaw <2 dtk), kirim alert peringatan hedged double-risk.
4. **EXPIRED (@ 17:00 WIB)** — pending order yang belum kena dibatalkan.

**Validitas range:** order hanya dipasang jika `RANGE_MIN_USD ≤ range ≤ RANGE_MAX_USD` ($5–$25). Di luar itu → skip hari itu.

**Recovery restart:** state dipulihkan dari **jam saat ini + pending order di MT5** (bukan file) — lihat `SignalWatcher.initialize()`. Tidak lagi memakai `state.json`.

**TP1:** midpoint antara entry dan TP2 — close 50% posisi + SL pindah ke breakeven.
**TP2:** target dari pending order (sisa 50% posisi).

## Trade Filters (`trade_filter.py`)

Order hanya dibuka jika semua filter lolos:
1. **Jam aktif** — 14:50–17:00 WIB (window London Breakout, `ACTIVE_HOURS`)
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
| `BALANCE_AWAL` | 300 | Balance awal USD (nominal; runtime pakai balance live MT5) |
| `RISK_PER_TRADE` | 1.0% | Target risk per trade (% balance live → compounding) |
| `MAX_RISK_PER_TRADE` | 2.0% | Ceiling risiko aktual; skip order jika MIN_LOT melebihi ini |
| `TARGET_RR` | 4.0 | Risk/Reward (legacy, dipakai money_management) |
| `MAX_LOSS_PER_DAY` | 3.0% | Max daily loss |
| `MAX_DRAWDOWN` | 15.0% | Max total drawdown |
| `MAX_OPEN_TRADES` | 2 | Max posisi terbuka |
| `MAX_LOT` | 0.50 | Cap maksimum lot size |
| `SPREAD_FILTER` | 80 | Max spread (points) |
| `NEWS_BLACKOUT_BEFORE` | 30 | Menit sebelum berita |
| `NEWS_BLACKOUT_AFTER` | 15 | Menit setelah berita |
| `POLL_INTERVAL_SECONDS` | 2 | Frekuensi tick loop |
| `RANGE_MIN_USD` | 5.0 | Range Asian minimum (skip jika lebih sempit) |
| `RANGE_MAX_USD` | 25.0 | Range Asian maksimum (skip jika lebih lebar) |
| `BREAKOUT_BUFFER_USD` | 0.5 | Jarak entry dari tepi range |
| `SL_BUFFER_USD` | 0.3 | Jarak SL dari tepi range berlawanan |
| `TP_RR_BREAKOUT` | 1.5 | TP = range × RR dari entry |

Semua config bisa di-override via environment variable atau `.env` file. Tabel di atas adalah **default kode**; nilai aktif runtime di-inject `docker-compose` via `env_file: .env`. **Profil aktif `.env` (agak agresif, modal $300):** `RISK_PER_TRADE=1.5`, `MAX_RISK_PER_TRADE=2.5`, `MAX_LOSS_PER_DAY=3.0`, `MAX_LOT=0.50`.

## Telegram Commands

| Command | Fungsi |
|---|---|
| `/status` | Balance, equity, open trades, status bot |
| `/trades` | Detail semua posisi aktif |
| `/laporan` | Ringkasan P&L hari ini |
| `/pause` | Pause bot (tidak buka trade baru) |
| `/resume` | Lanjutkan bot |
| `/help` | Daftar command |

**Notifikasi otomatis:**
- London Breakout: window aktif/standby, Asian range terkunci + pending order dipasang, range invalid (skip), OCO whipsaw, expired @ 17:00, recovery setelah restart
- Trade: buka/tutup, TP1 hit + breakeven
- Sistem: news blackout on/off, daily loss, drawdown limit, AutoTrading on/off, heartbeat jam 08:00 WIB, laporan harian jam 23:59 WIB

## Module Map

| File | Tanggung Jawab |
|---|---|
| `main.py` | Entry point, orchestrator, daily reset, heartbeat |
| `signal_watcher.py` | Tick loop, London Breakout state machine, OCO, TP1/breakeven, drawdown check |
| `signal_generator.py` | `LondonBreakoutStrategy`: akumulasi Asian range + kalkulasi pending order |
| `trade_filter.py` | Gate untuk open order |
| `news_filter.py` | ForexFactory kalender, blackout window |
| `money_management.py` | Lot size, TP price, drawdown check |
| `mt5_connector.py` | Koneksi MT5, open/close/modify order, pending stop order (place/cancel/list) |
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

Log rotation dikonfigurasi di `docker-compose.yml` untuk `bot-service`: max 10MB per file, simpan 5 file (total max 50MB). Kode bot mount via `./bot:/app`, jadi setelah `git pull` perlu **restart container** agar kode baru terbaca (lihat skill `docker-post-pull`). London Breakout **tidak lagi** memakai `state.json` — recovery dilakukan dari jam + pending order MT5 saat startup.

## Development Notes

- Timezone WIB (Asia/Jakarta / UTC+7) digunakan untuk semua jam strategi dan daily reset. Fase London Breakout pakai `datetime.now(WIB).time()`.
- Heartbeat log setiap ~5 menit (60 tick × 2 detik), menampilkan `london_state`.
- TP1 partial close skip jika `half_vol < MIN_LOT` — biarkan TP2 close semua.
- **Compounding inheren** — lot di-size dari `mt5.get_balance()` live tiap hari (`_place_london_orders`), jadi saat balance bertumbuh, dollar risk (`balance × RISK_PER_TRADE%`) ikut naik dan lot membesar otomatis. `BALANCE_AWAL` hanya nominal, tidak dipakai sizing.
- **Guard akun kecil** — karena lot dibulatkan ke `MIN_LOT` (0.01), SL selebar range Asian ($5–$25) bisa membuat risiko aktual jauh di atas `RISK_PER_TRADE`. `position_risk_pct()` menghitung risiko nyata; jika > `MAX_RISK_PER_TRADE` (2%), `_place_london_orders` **skip + alert**, bukan trading oversized. Efeknya: di modal kecil hanya range sempit yang di-trade; range lebar otomatis lolos saat balance compounding naik. Contoh @ $300: range ≤ ~$5 lolos; @ ~$580+ range $5 = 1% murni.
- `is_news_blackout()` fail-open: jika API ForexFactory tidak bisa diakses, trading tetap jalan.
- **OCO bukan native** — dua stop order dipasang manual; pembatalan order lawan dilakukan tiap tick (2 dtk). Window race <2 dtk bisa membuat kedua order tereksekusi (hedged double-risk) → bot kirim alert, tutup manual.
- **Risk per order** — `_place_london_orders` menghitung lot tiap sisi (buy & sell) secara independen via `calculate_lot_size`. Bila keduanya kena, risiko bisa ~2× — pertimbangan saat set `MAX_OPEN_TRADES`/`MAX_LOT`.
- Order placement di-gate `can_open_trade()` saat 14:50; jika tidak lolos (jam/news/spread/loss) → state EXPIRED, tidak ada order hari itu.
- Recovery startup (`initialize()`): saat 07:00–14:00 → COLLECTING (range mulai dari 0 lagi); saat 14:00–14:50 → EXPIRED + alert (data range hari itu hilang bersama proses lama, hari itu pasti skip); saat 14:50–17:00 & ada buy+sell stop di MT5 → ORDERS_SET. Selain itu IDLE. Restart paling aman dilakukan sebelum 07:00 atau setelah 17:00 WIB.

# Design Doc: XAU/USD Copy Trading Bot

**Tanggal:** 2026-05-19
**Status:** Approved — siap implementasi
**Bahasa komunikasi:** Bahasa Indonesia

---

## 1. Ringkasan Proyek

Bot trading otomatis yang **meng-copy trade dari trader profesional** di MT5 Signal Service, khusus pair **XAUUSD (Gold)**, dengan money management ketat dan notifikasi Telegram real-time. Bot jalan 24/5 di VPS Linux tanpa perlu PC pengguna menyala.

---

## 2. Stack Teknologi

| Komponen | Pilihan |
|---|---|
| Broker | Exness (MT5) |
| Pair | XAUUSD (Gold/USD) |
| Signal source | MT5 Signal Service (trader profesional terverifikasi) |
| Bahasa | Python 3.11+ |
| MT5 bridge | `mt5linux` library (RPyC) |
| Infrastruktur | Docker Compose |
| VPS | IDCloudHost Ubuntu Linux |
| Alert | Telegram Bot |

---

## 3. Arsitektur Sistem

```
IDCloudHost Ubuntu VPS
└── Docker Compose
    ├── Container: mt5-service
    │   ├── Wine (Windows emulator)
    │   ├── MT5 Terminal (login Exness)
    │   └── RPyC Server :8001 (bridge ke Python)
    │
    └── Container: bot-service
        ├── main.py              ← entry point
        ├── config.py            ← semua setting
        ├── mt5_connector.py     ← koneksi MT5 via mt5linux
        ├── signal_watcher.py    ← pantau trade trader pro
        ├── money_management.py  ← hitung lot & proteksi
        ├── trade_filter.py      ← filter trade layak/tidak
        ├── telegram_alert.py    ← notifikasi HP
        └── logger.py            ← simpan log aktivitas
```

### Docker Compose Preview

```yaml
services:
  mt5-service:
    image: gmag11/metatrader5
    ports:
      - "8001:8001"   # RPyC bridge
      - "3000:3000"   # VNC web monitor MT5

  bot-service:
    build: ./bot
    depends_on:
      - mt5-service
    env_file: .env
```

### Struktur Folder Project

```
bot-trading/
├── docker-compose.yml
├── .env
├── mt5/
│   ├── Dockerfile
│   └── config/
│       └── exness_login.ini
└── bot/
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py
    ├── config.py
    ├── mt5_connector.py
    ├── signal_watcher.py
    ├── money_management.py
    ├── trade_filter.py
    ├── telegram_alert.py
    └── logger.py
```

---

## 4. Spesifikasi VPS

| Komponen | Spesifikasi |
|---|---|
| Provider | IDCloudHost |
| OS | Ubuntu Linux |
| CPU | 2 vCPU (minimum) |
| RAM | 2 GB (minimum) |
| Storage | 20 GB NVMe |
| Estimasi biaya | Rp 100.000–150.000/bulan |

---

## 5. Money Management

### Konfigurasi (config.py)

```python
BALANCE_AWAL       = 100     # USD — modal awal
RISK_PER_TRADE     = 1.0     # % balance per trade
TARGET_RR          = 2.0     # Risk 1 : Target 2
MAX_LOSS_PER_DAY   = 3.0     # % — bot pause jika tercapai
MAX_DRAWDOWN       = 15.0    # % — bot berhenti total
MAX_OPEN_TRADES    = 2       # maksimal trade bersamaan
MIN_LOT            = 0.01    # minimum lot Exness
MAX_LOT            = 0.05    # batas atas lot (keamanan)
SPREAD_FILTER      = 80      # skip jika spread > 80 points
```

### Kalkulasi Lot Size Otomatis

```
Risk $ = Balance × RISK_PER_TRADE / 100
Lot    = Risk $ ÷ (SL_points × nilai_per_point)

Contoh (Balance $100, Risk 1%, SL 150 pts):
→ Risk $ = $1
→ Lot    = $1 ÷ ($1.50) = 0.0067 → dibulatkan 0.01 lot
```

### Sistem Proteksi Berlapis

```
Layer 1 — Per Trade  : Lot disesuaikan balance otomatis
Layer 2 — Per Hari   : Loss > 3% → bot pause sampai besok
Layer 3 — Total Akun : Drawdown > 15% → bot berhenti total + alert
Layer 4 — Spread     : Spread > 80 pts → skip trade
```

---

## 6. Trade Filter

### Alur Filter

```
Signal masuk dari trader pro
        ↓
✅ Jam aktif? (14:00–17:00 WIB atau 19:00–23:00 WIB)
        ↓
✅ Bukan waktu berita besar? (NFP, FOMC, CPI, GDP)
        ↓
✅ Spread < 80 points?
        ↓
✅ Trade punya SL terpasang?
        ↓
✅ Open trades < 2?
        ↓
✅ Loss hari ini < 3%?
        ↓
   EKSEKUSI TRADE ✅
```

### Jam Trading Aktif (WIB)

```python
JAM_TRADING_AKTIF = [
    ("14:00", "17:00"),   # London session open
    ("19:00", "23:00"),   # New York session
]
```

### Berita yang Di-skip

```python
BERITA_BERBAHAYA = ["NFP", "FOMC", "CPI", "GDP"]
PAUSE_SEBELUM_BERITA = 30   # menit
PAUSE_SESUDAH_BERITA = 15   # menit
```

---

## 7. Telegram Alert & Monitoring

### Notifikasi Otomatis

| Event | Pesan |
|---|---|
| Trade masuk | Pair, arah, lot, entry, SL, TP, RR |
| Trade selesai profit | Hasil $, %, balance terbaru |
| Trade selesai loss | Hasil $, %, balance terbaru |
| Laporan harian 23:59 | Total trade, P&L, win rate, balance |
| Loss harian tercapai | Alert bot pause |
| Drawdown tercapai | Alert bot berhenti total |
| Koneksi MT5 putus | Alert gangguan |

### Perintah Bot

```
/status   → cek status bot & balance
/pause    → pause bot sementara
/resume   → aktifkan bot kembali
/laporan  → statistik hari ini
/trades   → trade yang sedang terbuka
```

---

## 8. Target Kinerja

| Metrik | Target |
|---|---|
| Win rate | 60–70% |
| Risk/Reward | 1:2 minimum |
| Profit per bulan | 5–10% (konservatif) |
| Max drawdown | < 15% |
| Modal awal | $100 |

### Proyeksi Compounding (target 7%/bulan)

```
Bulan 1  : $107
Bulan 6  : $150
Bulan 12 : $226
Bulan 24 : $511
```

---

## 9. Cara Pilih Trader Pro di MT5 Signal Service

Filter saat memilih trader untuk dicopy:

| Metrik | Minimum | Ideal |
|---|---|---|
| Win Rate | > 55% | 60–75% |
| Profit Factor | > 1.3 | > 1.8 |
| Max Drawdown | < 25% | < 15% |
| Umur Akun | > 3 bulan | > 12 bulan |
| Jumlah Trade | > 100 | > 300 |
| Instrument | XAUUSD | XAUUSD only |

**Hindari trader dengan:** win rate > 85% (kemungkinan martingale), history < 3 bulan, drawdown > 30%.

---

## 10. Referensi

- [gmag11/MetaTrader5-Docker](https://github.com/gmag11/MetaTrader5-Docker)
- [mt5linux Python Library](https://github.com/lucas-campagna/mt5linux)
- [ejtraderLabs Metatrader5-Docker](https://github.com/ejtraderLabs/Metatrader5-Docker)
- [IDCloudHost Cloud VPS](https://idcloudhost.com/en/cloud-vps/)

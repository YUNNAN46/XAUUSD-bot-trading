# London Breakout Strategy — Design Spec
**Date:** 2026-06-28
**Replaces:** EMA Channel 4-Phase State Machine (`SignalStateMachine`)

## Latar Belakang

Setelah ~2 bulan berjalan, strategi EMA 4-fase hanya menghasilkan 1 posisi (loss). Root cause: terlalu banyak kondisi yang harus selaras secara bersamaan (crossover + slope ≥ 0.5 + pullback + breakout + ATR filter + jam trading). Sinyal hampir tidak pernah terpenuhi penuh.

**Solusi:** Ganti dengan London Session Breakout — strategi paling banyak diotomasi di komunitas MT5 dengan live track record 15–35% per tahun dan win rate 58–65% pada XAUUSD.

---

## Konsep Strategi

XAU/USD cenderung konsolidasi semalam (Asian session) membentuk range sempit. Saat London buka, volatilitas naik tajam dan harga sering breakout dari range tersebut dengan momentum kuat.

```
Asian Session (07:00–14:00 WIB)
  ┌─────────────────────────────┐  ← Asian High
  │       KONSOLIDASI           │
  └─────────────────────────────┘  ← Asian Low

London Open (15:00 WIB)
  ↑ Breakout atas → BUY Stop ter-trigger
  ↓ Breakout bawah → SELL Stop ter-trigger
```

---

## Alur Kerja

```
07:00–14:00 WIB   Rekam High & Low setiap candle M15
14:50 WIB         Validasi range → pasang Buy Stop & Sell Stop
15:00–17:00 WIB   Monitor order yang ter-trigger
17:00 WIB         Cancel semua pending order yang belum ter-trigger
23:59 WIB         Reset harian
```

---

## Parameter

| Parameter | Nilai | Keterangan |
|-----------|-------|------------|
| Asian range window | 07:00–14:00 WIB | Periode konsolidasi sebelum London |
| Entry buffer | 10 poin | Di atas High (Buy) / di bawah Low (Sell) — hindari false trigger |
| SL Buy | Asian Low − 5 poin | Ujung berlawanan range |
| SL Sell | Asian High + 5 poin | Ujung berlawanan range |
| TP Buy | entry + (range × 1.5) | Dihitung dari harga entry, bukan dari Asian High |
| TP Sell | entry − (range × 1.5) | Dihitung dari harga entry, bukan dari Asian Low |
| Range minimum | 10 poin | Skip hari ini jika range terlalu sempit |
| Range maksimum | 50 poin | Skip hari ini jika SL terlalu besar |
| Order expiry | 17:00 WIB | Cancel pending jika 2 jam tidak ter-trigger |
| OCO behavior | Ya | Jika Buy Stop ter-trigger → Sell Stop di-cancel, dan sebaliknya |

> **Poin** = satuan MT5 untuk XAUUSD (1 pip = 10 poin pada XAUUSD 5-digit)
>
> **Contoh:** Asian High=2330, Low=2310 → range=20 poin. Buy Stop=2340, SL=2305, TP=2370 (2340+30). Sell Stop=2300, SL=2335, TP=2270 (2300−30).

---

## Perubahan Kode

### Hapus
- Seluruh class `SignalStateMachine` di `bot/signal_generator.py`
- State file `state.json` (tidak dibutuhkan lagi)
- Semua referensi ke `phase`, `armed_at`, `window_opened_at` di `signal_watcher.py`

### Buat Baru — `LondonBreakoutStrategy` di `bot/signal_generator.py`

```python
class LondonBreakoutStrategy:
    def update_asian_range(self, high: float, low: float) -> None
        # Dipanggil tiap tick selama 07:00–14:00 WIB
        # Simpan running High & Low

    def is_range_valid(self) -> bool
        # True jika range antara RANGE_MIN dan RANGE_MAX poin

    def get_pending_orders(self) -> dict | None
        # Return: {buy_stop, sell_stop, sl_buy, sl_sell, tp_buy, tp_sell}
        # Return None jika range tidak valid

    def reset(self) -> None
        # Reset High/Low untuk hari berikutnya
```

### Modifikasi — `bot/signal_watcher.py`

Ganti logika tick 4-fase dengan state sederhana berbasis jam:

```
STATE: COLLECTING  → jam 07:00–14:49 WIB, panggil update_asian_range()
STATE: ORDERS_SET  → jam 14:50 WIB, pasang pending orders via mt5_connector
STATE: MONITORING  → jam 15:00–17:00 WIB, cek apakah order ter-trigger
STATE: EXPIRED     → jam 17:00 WIB, cancel semua pending
STATE: IDLE        → jam 17:01–06:59 WIB besok, tidak ada aksi
```

### Tidak Berubah
- `trade_filter.py` — filter tetap aktif (spread, daily loss, max positions)
- `money_management.py` — lot size calculation tetap sama
- `telegram_alert.py` — hanya tambah format notifikasi baru
- `mt5_connector.py` — tambah method `place_stop_order()` dan `cancel_order()`

---

## Notifikasi Telegram

| Waktu | Pesan |
|-------|-------|
| 14:50 WIB | "📊 Asian range terkunci: High=X Low=Y (range=Z poin). Buy Stop=A, Sell Stop=B dipasang." |
| Ter-trigger | "📈/📉 Buy/Sell Stop ter-trigger di X. SL=Y TP=Z" |
| 17:00 WIB | "⏱ Pending orders dihapus — tidak ada breakout hari ini." |
| Range invalid | "⚠️ Skip hari ini — range Asian terlalu sempit/lebar (Z poin)." |

---

## Filter yang Tetap Berlaku

- **Spread filter** — tidak pasang order jika spread > 80 poin
- **Daily loss limit** — tidak pasang order jika loss harian ≥ 3%
- **Max open trades** — tidak pasang order baru jika sudah ada 2 posisi terbuka
- **News blackout** — tidak pasang order jika ada berita high-impact dalam 30 menit

---

## Hal yang Tidak Termasuk Scope

- Backtest otomatis (dilakukan manual via MT5 Strategy Tester)
- Trailing stop (bisa ditambah di iterasi berikutnya)
- Multiple pair (hanya XAUUSD)

---

## Kriteria Sukses

- Bot menghasilkan **1–3 pending order per minggu** yang ter-trigger
- Win rate **≥ 55%** setelah 20 trade pertama
- Tidak ada trade terbuka tanpa SL

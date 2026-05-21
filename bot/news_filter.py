import logging
from datetime import datetime, timedelta
import pytz
import httpx
import config

logger = logging.getLogger(__name__)

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

_cached_events: list = []
_cache_date = None


def _fetch_events() -> list:
    """Ambil event High-Impact USD dari ForexFactory. Cache per hari."""
    global _cached_events, _cache_date
    today = datetime.now(pytz.UTC).date()
    if _cache_date == today:
        return _cached_events
    try:
        resp = httpx.get(FF_CALENDAR_URL, timeout=10)
        resp.raise_for_status()
        all_events = resp.json()
        high_usd = [
            e for e in all_events
            if e.get('impact') == 'High' and e.get('country') == 'USD'
        ]
        _cached_events = high_usd
        _cache_date = today
        logger.info(f"Kalender berita: {len(high_usd)} event High-Impact USD minggu ini")
    except Exception as exc:
        logger.warning(f"Gagal ambil kalender berita: {exc} — filter berita nonaktif sementara")
    return _cached_events


def is_news_blackout(now: datetime = None) -> tuple[bool, str]:
    """
    Cek apakah sekarang dalam blackout window berita High-Impact USD.
      - Blackout mulai NEWS_BLACKOUT_BEFORE menit sebelum berita
      - Blackout selesai NEWS_BLACKOUT_AFTER menit setelah berita
    Gagal-terbuka: jika API tidak tersedia, trading tetap diizinkan.
    """
    if now is None:
        now = datetime.now(pytz.UTC)
    elif now.tzinfo is None:
        now = pytz.UTC.localize(now)
    else:
        now = now.astimezone(pytz.UTC)

    for event in _fetch_events():
        try:
            event_time = datetime.fromisoformat(event['date']).astimezone(pytz.UTC)
            blackout_start = event_time - timedelta(minutes=config.NEWS_BLACKOUT_BEFORE)
            blackout_end = event_time + timedelta(minutes=config.NEWS_BLACKOUT_AFTER)
            if blackout_start <= now <= blackout_end:
                title = event.get('title', 'High-Impact News')
                logger.info(f"News blackout aktif: {title} @ {event_time.strftime('%H:%M')} UTC")
                return True, title
        except Exception:
            continue
    return False, ""

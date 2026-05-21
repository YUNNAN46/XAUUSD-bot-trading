import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytz


def make_event(title, minutes_from_now, impact="High", country="USD"):
    """Buat fake event berita relatif dari sekarang (UTC)."""
    event_time = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    return {
        "title": title,
        "country": country,
        "impact": impact,
        "date": event_time.isoformat(),
    }


def mock_fetch(events):
    """Patch _fetch_events agar return list event tanpa HTTP call."""
    return patch('news_filter._fetch_events', return_value=events)


# --- is_news_blackout ---

def test_no_blackout_when_no_events():
    from news_filter import is_news_blackout
    with mock_fetch([]):
        result, name = is_news_blackout()
    assert result is False
    assert name == ""


def test_blackout_active_before_event():
    """Blackout aktif saat event 20 menit lagi (< 30 menit sebelum)."""
    from news_filter import is_news_blackout
    events = [make_event("Non-Farm Payrolls", minutes_from_now=20)]
    with mock_fetch(events):
        result, name = is_news_blackout()
    assert result is True
    assert "Non-Farm Payrolls" in name


def test_blackout_active_after_event():
    """Blackout aktif saat event baru saja lewat 10 menit lalu (< 15 menit sesudah)."""
    from news_filter import is_news_blackout
    events = [make_event("CPI", minutes_from_now=-10)]
    with mock_fetch(events):
        result, name = is_news_blackout()
    assert result is True
    assert "CPI" in name


def test_no_blackout_far_before_event():
    """Tidak blackout saat event masih 60 menit lagi (> 30 menit sebelum)."""
    from news_filter import is_news_blackout
    events = [make_event("GDP", minutes_from_now=60)]
    with mock_fetch(events):
        result, name = is_news_blackout()
    assert result is False


def test_no_blackout_long_after_event():
    """Tidak blackout saat event sudah lewat 30 menit lalu (> 15 menit sesudah)."""
    from news_filter import is_news_blackout
    events = [make_event("FOMC", minutes_from_now=-30)]
    with mock_fetch(events):
        result, name = is_news_blackout()
    assert result is False


def test_no_blackout_for_medium_impact():
    """Event Medium-Impact difilter oleh _fetch_events → tidak memicu blackout."""
    import news_filter
    import httpx
    news_filter._cache_date = None
    news_filter._cached_events = []

    event_time = datetime.now(timezone.utc) + timedelta(minutes=10)
    fake_data = [{"title": "Building Permits", "country": "USD", "impact": "Medium", "date": event_time.isoformat()}]
    mock_resp = MagicMock()
    mock_resp.json.return_value = fake_data
    mock_resp.raise_for_status.return_value = None

    with patch('news_filter.httpx.get', return_value=mock_resp):
        from news_filter import is_news_blackout
        result, name = is_news_blackout()
    assert result is False


def test_no_blackout_for_non_usd():
    """Event non-USD difilter oleh _fetch_events → tidak memicu blackout."""
    import news_filter
    news_filter._cache_date = None
    news_filter._cached_events = []

    event_time = datetime.now(timezone.utc) + timedelta(minutes=10)
    fake_data = [{"title": "ECB Rate Decision", "country": "EUR", "impact": "High", "date": event_time.isoformat()}]
    mock_resp = MagicMock()
    mock_resp.json.return_value = fake_data
    mock_resp.raise_for_status.return_value = None

    with patch('news_filter.httpx.get', return_value=mock_resp):
        from news_filter import is_news_blackout
        result, name = is_news_blackout()
    assert result is False


# --- _fetch_events: fail-open ---

def test_fail_open_when_api_down():
    """Jika API gagal, trading tetap diizinkan (fail-open)."""
    import news_filter
    news_filter._cached_events = []
    news_filter._cache_date = None

    import httpx
    with patch('news_filter.httpx.get', side_effect=httpx.ConnectError("timeout")):
        from news_filter import is_news_blackout
        result, name = is_news_blackout()

    assert result is False  # fail-open: tidak blokir trading


def test_cache_used_on_same_day():
    """_fetch_events tidak HTTP call kedua kali di hari yang sama."""
    import news_filter
    from datetime import date
    news_filter._cached_events = [make_event("NFP", minutes_from_now=20)]
    news_filter._cache_date = datetime.now(pytz.UTC).date()

    with patch('news_filter.httpx.get') as mock_get:
        news_filter._fetch_events()
        mock_get.assert_not_called()

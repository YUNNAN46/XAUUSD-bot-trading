import importlib
from datetime import datetime

import pytest
import pytz


@pytest.fixture(autouse=True)
def isolate_news_cache():
    """Reset cache global news_filter tiap test.

    Cache di-set 'hangat tapi kosong' (bukan None) supaya test yang memanggil
    can_open_trade asli tidak HTTP call sungguhan dan tidak kena blackout dari
    event yang bocor dari test lain (flaky tergantung jam).
    """
    import news_filter
    news_filter._cached_events = []
    news_filter._cache_date = datetime.now(pytz.UTC).date()
    yield


@pytest.fixture(autouse=True)
def set_test_env(monkeypatch):
    monkeypatch.setenv("MT5_HOST", "localhost")
    monkeypatch.setenv("MT5_PORT", "8001")
    monkeypatch.setenv("BALANCE_AWAL", "100")
    monkeypatch.setenv("RISK_PER_TRADE", "1.0")
    monkeypatch.setenv("MAX_RISK_PER_TRADE", "2.0")
    monkeypatch.setenv("TARGET_RR", "4.0")
    monkeypatch.setenv("MAX_LOSS_PER_DAY", "3.0")
    monkeypatch.setenv("MAX_DRAWDOWN", "15.0")
    monkeypatch.setenv("MAX_OPEN_TRADES", "2")
    monkeypatch.setenv("MIN_LOT", "0.01")
    monkeypatch.setenv("MAX_LOT", "0.05")
    monkeypatch.setenv("SPREAD_FILTER", "80")
    monkeypatch.setenv("TELEGRAM_TOKEN", "test_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    import config
    importlib.reload(config)

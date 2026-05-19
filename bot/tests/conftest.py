import importlib
import pytest


@pytest.fixture(autouse=True)
def set_test_env(monkeypatch):
    monkeypatch.setenv("MT5_HOST", "localhost")
    monkeypatch.setenv("MT5_PORT", "8001")
    monkeypatch.setenv("BALANCE_AWAL", "100")
    monkeypatch.setenv("RISK_PER_TRADE", "1.0")
    monkeypatch.setenv("TARGET_RR", "2.0")
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

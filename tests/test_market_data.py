from datetime import datetime, timezone, timedelta
import pytest
from trading_system.market_data.models import Candle
from trading_system.market_data.service import MarketDataService


class FakeProvider:
    def __init__(self, candles):
        self.data = candles
    def fetch_candles(self, symbol, timeframe="1h", limit=100):
        return self.data[:limit]


def candle(offset=0):
    return Candle("crypto", "BTC/USDT", "1h",
        datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=offset),
        100, 110, 90, 105, 12)


def test_service_returns_chronological_candles():
    service = MarketDataService(crypto=FakeProvider([candle(0), candle(1)]))
    result = service.candles("crypto", "BTC/USDT")
    assert [item.timestamp for item in result] == sorted(item.timestamp for item in result)


def test_service_rejects_unordered_provider_data():
    service = MarketDataService(crypto=FakeProvider([candle(1), candle(0)]))
    with pytest.raises(ValueError, match="unordered"):
        service.candles("crypto", "BTC/USDT")


def test_unknown_market_has_clear_error():
    with pytest.raises(ValueError, match="No provider"):
        MarketDataService().candles("commodities", "GOLD")


def test_candle_rejects_invalid_ohlc():
    with pytest.raises(ValueError, match="high is inconsistent"):
        Candle("crypto", "BTC/USDT", "1h", datetime.now(timezone.utc),
               100, 99, 90, 105, 1)

from datetime import datetime, timezone, timedelta

from trading_system.market_data.collector import MarketDataCollector
from trading_system.market_data.models import Candle
from trading_system.market_data.service import MarketDataService
from trading_system.market_data.storage import CandleStore


class Provider:
    def __init__(self, candles):
        self.candles = candles

    def fetch_candles(self, symbol, timeframe="1h", limit=100):
        return self.candles[:limit]


def make_candle(hour, close=105):
    return Candle("crypto", "BTC/USDT", "1h",
                  datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=hour),
                  100, 110, 90, close, 10)


def test_store_upsert_is_idempotent_and_ordered(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    first = make_candle(0)
    second = make_candle(1)
    assert store.upsert([first, second]) == 2
    assert store.upsert([first, second]) == 2
    rows = store.get("crypto", "BTC/USDT", "1h")
    assert len(rows) == 2
    assert rows[0].timestamp < rows[1].timestamp


def test_store_updates_existing_candle(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    store.upsert([make_candle(0, 105)])
    store.upsert([make_candle(0, 107)])
    rows = store.get("crypto", "BTC/USDT", "1h")
    assert len(rows) == 1
    assert rows[0].close == 107


def test_collector_fetches_and_persists(tmp_path):
    candles = [make_candle(0), make_candle(1)]
    collector = MarketDataCollector(
        MarketDataService(crypto=Provider(candles)),
        CandleStore(str(tmp_path / "candles.db")),
    )
    assert collector.collect_once(market="crypto", symbol="BTC/USDT") == 2
    assert len(collector.store.get("crypto", "BTC/USDT", "1h")) == 2

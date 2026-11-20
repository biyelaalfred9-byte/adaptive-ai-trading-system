from datetime import datetime, timedelta, timezone

import pytest

from trading_system.market_data.historical import (
    HistoricalDataBackfiller, timeframe_duration,
)
from trading_system.market_data.models import Candle
from trading_system.market_data.storage import CandleStore


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_candles(count=7):
    return [
        Candle("crypto", "BTC/USDT", "1h", START + timedelta(hours=i),
               100 + i, 102 + i, 98 + i, 101 + i, 10)
        for i in range(count)
    ]


class PagedProvider:
    def __init__(self, candles):
        self.candles = candles
        self.calls = []

    def fetch_candles_since(self, symbol, timeframe, since, limit=100):
        self.calls.append(since)
        rows = [c for c in self.candles if c.timestamp >= since]
        return rows[:limit]


def test_backfill_pages_and_persists_completed_candles(tmp_path):
    provider = PagedProvider(make_candles())
    store = CandleStore(str(tmp_path / "history.db"))
    backfiller = HistoricalDataBackfiller(provider, store)

    count = backfiller.backfill(
        market="crypto", symbol="BTC/USDT", timeframe="1h",
        start=START, end=START + timedelta(hours=7), page_limit=2,
    )

    assert count == 7
    assert len(provider.calls) >= 3
    rows = store.get("crypto", "BTC/USDT", "1h", limit=20)
    assert len(rows) == 7
    assert rows[0].timestamp == START
    assert rows[-1].timestamp == START + timedelta(hours=6)


def test_backfill_is_idempotent(tmp_path):
    store = CandleStore(str(tmp_path / "history.db"))
    backfiller = HistoricalDataBackfiller(PagedProvider(make_candles()), store)
    args = dict(market="crypto", symbol="BTC/USDT", timeframe="1h",
                start=START, end=START + timedelta(hours=7), page_limit=3)
    assert backfiller.backfill(**args) == 7
    assert backfiller.backfill(**args) == 7
    assert len(store.get("crypto", "BTC/USDT", "1h", limit=20)) == 7


def test_backfill_rejects_naive_or_reversed_dates(tmp_path):
    backfiller = HistoricalDataBackfiller(PagedProvider([]), CandleStore(str(tmp_path / "x.db")))
    with pytest.raises(ValueError, match="timezone-aware"):
        backfiller.backfill(market="crypto", symbol="BTC/USDT", timeframe="1h",
                            start=datetime(2026, 1, 1), end=START + timedelta(hours=1))
    with pytest.raises(ValueError, match="earlier"):
        backfiller.backfill(market="crypto", symbol="BTC/USDT", timeframe="1h",
                            start=START + timedelta(hours=1), end=START)


def test_timeframe_supports_ccxt_and_oanda_notation():
    assert timeframe_duration("1h") == timedelta(hours=1)
    assert timeframe_duration("H1") == timedelta(hours=1)
    assert timeframe_duration("M15") == timedelta(minutes=15)
    with pytest.raises(ValueError, match="Unsupported"):
        timeframe_duration("hourly")

from datetime import datetime, timedelta, timezone
import json

import pytest

from trading_system.backfill_runner import (
    BackfillJob, HistoricalBackfillRunner, load_config,
)
from trading_system.market_data.models import Candle
from trading_system.market_data.storage import CandleStore


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeProvider:
    def fetch_candles_since(self, symbol, timeframe, since, limit=100):
        return [
            Candle("crypto", symbol, timeframe, START + timedelta(hours=i),
                   100 + i, 102 + i, 98 + i, 101 + i, 10)
            for i in range(3)
            if START + timedelta(hours=i) >= since
        ][:limit]


def job(**overrides):
    values = dict(
        market="crypto", symbol="BTC/USDT", timeframe="1h",
        start=START, end=START + timedelta(hours=3),
        page_limit=2, max_pages=10,
    )
    values.update(overrides)
    return BackfillJob(**values)


def test_runner_persists_data_and_returns_summary(tmp_path):
    store = CandleStore(str(tmp_path / "market.db"))
    runner = HistoricalBackfillRunner(store, provider_factory=lambda _: FakeProvider())

    report = runner.run([job()])

    assert report["live_trading_enabled"] is False
    assert report["summary"] == {
        "jobs_total": 1, "jobs_completed": 1, "jobs_failed": 0,
        "candles_upserted": 3,
    }
    assert len(store.get("crypto", "BTC/USDT", "1h", limit=10)) == 3


def test_runner_continues_after_a_job_fails(tmp_path):
    store = CandleStore(str(tmp_path / "market.db"))

    def provider_factory(config):
        if config.symbol == "BAD/PAIR":
            raise RuntimeError("provider unavailable")
        return FakeProvider()

    report = HistoricalBackfillRunner(store, provider_factory).run([
        job(symbol="BAD/PAIR"), job(),
    ])

    assert report["summary"]["jobs_failed"] == 1
    assert report["summary"]["jobs_completed"] == 1


def test_load_config_parses_timezone_and_defaults(tmp_path):
    config = tmp_path / "backfill.json"
    config.write_text(json.dumps({
        "database": "history.sqlite3",
        "jobs": [{
            "market": "crypto", "symbol": "BTC/USDT", "timeframe": "1h",
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-02T00:00:00+00:00",
        }],
    }))
    database, jobs = load_config(config)
    assert database == "history.sqlite3"
    assert jobs[0].start == START
    assert jobs[0].page_limit == 500


def test_config_rejects_naive_dates_and_invalid_page_size(tmp_path):
    config = tmp_path / "bad.json"
    config.write_text(json.dumps({
        "jobs": [{
            "market": "crypto", "symbol": "BTC/USDT", "timeframe": "1h",
            "start": "2026-01-01T00:00:00",
            "end": "2026-01-02T00:00:00Z",
        }],
    }))
    with pytest.raises(ValueError, match="timezone"):
        load_config(config)
    with pytest.raises(ValueError, match="cannot exceed 1000"):
        job(page_limit=1001)

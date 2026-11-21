import json
from datetime import datetime, timedelta, timezone

from trading_system.market_data.models import Candle
from trading_system.market_data.storage import CandleStore
from trading_system.research_runner import ResearchJob, ResearchRunner


class AlwaysNoSignal:
    name = "no_signal"

    def generate(self, candles):
        return None


def seed_store(store, count=80):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = []
    for i in range(count):
        price = 100 + i * 0.1
        candles.append(Candle(
            "crypto", "BTC/USDT", "1h", start + timedelta(hours=i),
            price, price + 1, price - 1, price + 0.2, 10,
        ))
    store.upsert(candles)


def test_runner_evaluates_and_returns_machine_readable_report(tmp_path):
    store = CandleStore(str(tmp_path / "candles.sqlite3"))
    seed_store(store)
    runner = ResearchRunner(store, strategies=[AlwaysNoSignal()])
    report = runner.run([
        ResearchJob("crypto", "BTC/USDT", "1h", train_size=40, test_size=20)
    ])

    assert report["mode"] == "historical_research_only"
    assert report["live_trading_enabled"] is False
    assert report["summary"]["jobs_evaluated"] == 1
    result = report["jobs"][0]
    assert result["status"] == "evaluated"
    assert result["strategies"][0]["strategy"] == "no_signal"
    assert result["strategies"][0]["oos_trade_count"] == 0
    json.dumps(report, allow_nan=False)


def test_runner_reports_insufficient_data_without_crashing(tmp_path):
    store = CandleStore(str(tmp_path / "candles.sqlite3"))
    seed_store(store, count=10)
    report = ResearchRunner(store, strategies=[AlwaysNoSignal()]).run([
        ResearchJob("crypto", "BTC/USDT", "1h", train_size=40, test_size=20)
    ])

    assert report["jobs"][0]["status"] == "insufficient_data"
    assert report["summary"]["jobs_with_insufficient_data"] == 1


def test_research_job_validates_fold_and_history_sizes():
    import pytest

    with pytest.raises(ValueError):
        ResearchJob("crypto", "BTC/USDT", "1h", train_size=40, test_size=20,
                    candle_limit=50)


def test_runner_adds_cost_sensitivity_exit_and_benchmark_diagnostics(tmp_path):
    store = CandleStore(str(tmp_path / "diagnostics.sqlite3"))
    seed_store(store)
    report = ResearchRunner(store, strategies=[AlwaysNoSignal()]).run([
        ResearchJob("crypto", "BTC/USDT", "1h", train_size=40, test_size=20)
    ])

    strategy = report["jobs"][0]["strategies"][0]
    diagnostics = strategy["diagnostics"]
    assert report["report_version"] == 2
    assert diagnostics["pnl_and_exits"]["trade_count"] == 0
    assert diagnostics["pnl_and_exits"]["exit_reasons"] == {}
    assert set(diagnostics["cost_sensitivity"]) == {
        "zero_cost", "half_configured_cost", "configured_cost"
    }
    assert diagnostics["buy_hold_benchmark"]["method"].startswith("long_only")
    assert len(diagnostics["buy_hold_benchmark"]["fold_returns_pct"]) == len(
        strategy["folds"]
    )
    json.dumps(report, allow_nan=False)

from datetime import datetime, timedelta, timezone

import pytest

from trading_system.backtesting import BacktestConfig, Backtester
from trading_system.domain import Market, Side, Signal
from trading_system.execution.paper import PaperCostModel
from trading_system.market_data.models import Candle
from trading_system.walk_forward import SelectionPolicy, WalkForwardEvaluator


def make_candles(count=12):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle("crypto", "BTC/USDT", "1h", start + timedelta(hours=i),
               100 + i, 102 + i, 98 + i, 101 + i, 100)
        for i in range(count)
    ]


class TestWindowSignal:
    name = "test_window_signal"

    def generate(self, history):
        if len(history) not in (4, 5):
            return None
        last = history[-1]
        return Signal(
            Market.CRYPTO, "BTC/USDT", Side.BUY, 0.8,
            last.close - 50, last.close + 50,
            "first eligible test candle", last.timestamp,
        )


def test_backtester_does_not_generate_signals_before_start_index():
    data = make_candles(8)
    result = Backtester(
        BacktestConfig(costs=PaperCostModel(0, 0, 0))
    ).run(data, TestWindowSignal(), start_index=4)

    assert result.trades
    assert all(trade.signal_time >= data[4].timestamp for trade in result.trades)


def test_start_index_must_be_in_range():
    data = make_candles(4)
    with pytest.raises(ValueError, match="start_index"):
        Backtester().run(data, TestWindowSignal(), start_index=4)


def test_walk_forward_reports_only_test_window_trades():
    data = make_candles(12)
    evaluator = WalkForwardEvaluator(
        Backtester(BacktestConfig(costs=PaperCostModel(0, 0, 0))),
        SelectionPolicy(min_oos_trades=99),
    )
    report, = evaluator.evaluate(data, [TestWindowSignal()], train_size=3, test_size=3)

    assert len(report.folds) == 3
    assert report.oos_trade_count == 3
    for fold in report.folds:
        assert fold.result.trades
        assert all(
            fold.test_start <= trade.signal_time <= fold.test_end
            for trade in fold.result.trades
        )
        assert all(
            trade.entry_time >= fold.test_start
            for trade in fold.result.trades
        )


def test_selection_policy_explains_insufficient_evidence():
    data = make_candles(12)
    evaluator = WalkForwardEvaluator(
        Backtester(BacktestConfig(costs=PaperCostModel(0, 0, 0))),
        SelectionPolicy(min_oos_trades=10),
    )
    report, = evaluator.evaluate(data, [TestWindowSignal()], train_size=3, test_size=3)

    assert not report.eligible_for_paper_testing
    assert any("out-of-sample trades" in reason for reason in report.reasons)


def test_rejects_duplicate_strategy_names_and_missing_folds():
    data = make_candles(12)
    evaluator = WalkForwardEvaluator()
    with pytest.raises(ValueError, match="unique"):
        evaluator.evaluate(data, [TestWindowSignal(), TestWindowSignal()], 3, 3)
    with pytest.raises(ValueError, match="not enough"):
        evaluator.evaluate(data[:5], [TestWindowSignal()], 4, 3)

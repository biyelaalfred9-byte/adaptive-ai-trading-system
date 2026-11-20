from datetime import datetime, timedelta, timezone

import pytest

from trading_system.domain import Market, Side, Signal
from trading_system.market_data.models import Candle
from trading_system.research.backtesting import BacktestConfig, Backtester
from trading_system.execution.paper import PaperCostModel


def candles(rows):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [Candle("crypto", "BTC/USDT", "1h", start + timedelta(hours=i),
                   o, h, l, c, 100) for i, (o, h, l, c) in enumerate(rows)]


class OneSignal:
    name = "one_signal"

    def __init__(self, candidate):
        self.candidate = candidate

    def generate(self, history):
        return self.candidate if len(history) == 2 else None


def make_signal(timestamp, side=Side.BUY, stop=95, target=110):
    return Signal(Market.CRYPTO, "BTC/USDT", side, 0.8, stop, target,
                  "test setup", timestamp)


def test_entry_occurs_on_next_candle_not_signal_candle():
    data = candles([(100, 101, 99, 100), (100, 102, 99, 101),
                    (105, 108, 104, 107), (107, 108, 106, 107)])
    result = Backtester(BacktestConfig(costs=PaperCostModel(0, 0, 0))).run(
        data, OneSignal(make_signal(data[1].timestamp, target=120)))
    assert result.trades[0].entry_time == data[2].timestamp
    assert result.trades[0].entry_price == 105
    assert result.trades[0].strategy == "one_signal"


def test_stop_wins_if_stop_and_target_hit_in_same_candle():
    data = candles([(100, 101, 99, 100), (100, 102, 99, 101),
                    (100, 111, 94, 100), (100, 101, 99, 100)])
    result = Backtester(BacktestConfig(costs=PaperCostModel(0, 0, 0))).run(
        data, OneSignal(make_signal(data[1].timestamp, stop=95, target=110)))
    assert result.trades[0].exit_reason == "stop_loss"
    assert result.trades[0].exit_price == 95


def test_costs_are_deducted_and_metrics_reported():
    data = candles([(100, 101, 99, 100), (100, 102, 99, 101),
                    (100, 111, 99, 109), (109, 110, 108, 109)])
    result = Backtester(BacktestConfig(costs=PaperCostModel(2, 1, 10))).run(
        data, OneSignal(make_signal(data[1].timestamp, stop=95, target=105)))
    trade = result.trades[0]
    assert trade.gross_pnl > 0
    assert trade.costs > 0
    assert trade.net_pnl < trade.gross_pnl
    assert result.metrics.trade_count == 1
    assert result.metrics.total_costs == pytest.approx(trade.costs)
    assert result.metrics.wins == 1


def test_no_signal_produces_zero_trade_metrics():
    class NoSignal:
        name = "none"
        def generate(self, history):
            return None
    result = Backtester().run(candles([(100, 101, 99, 100)] * 5), NoSignal())
    assert result.metrics.trade_count == 0
    assert result.metrics.win_rate == 0
    assert result.metrics.profit_factor == 0


def test_backtester_rejects_unordered_data():
    data = candles([(100, 101, 99, 100), (101, 102, 100, 101)])
    with pytest.raises(ValueError, match="chronological"):
        Backtester().run(data[::-1], OneSignal(make_signal(data[0].timestamp)))


def test_short_trade_is_supported():
    data = candles([(100, 101, 99, 100), (100, 102, 99, 101),
                    (100, 101, 89, 91), (91, 92, 90, 91)])
    result = Backtester(BacktestConfig(costs=PaperCostModel(0, 0, 0))).run(
        data, OneSignal(make_signal(data[1].timestamp, Side.SELL, stop=105, target=95)))
    assert result.trades[0].side is Side.SELL
    assert result.trades[0].exit_reason == "take_profit"

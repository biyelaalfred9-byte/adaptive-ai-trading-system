from datetime import datetime, timedelta, timezone

import pytest

from trading_system.domain import Side
from trading_system.market_data.models import Candle
from trading_system.strategies import (
    MeanReversionStrategy, MomentumStrategy, StrategyEngine,
    TrendFollowingStrategy,
)


def make_candles(closes):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [Candle("crypto", "BTC/USDT", "1h", start + timedelta(hours=i),
                   close, close * 1.002, close * 0.998, close, 10)
            for i, close in enumerate(closes)]


def test_trend_strategy_generates_explainable_long_signal():
    candles = make_candles([100 + i * 0.8 for i in range(50)])
    signal = TrendFollowingStrategy().generate(candles)
    assert signal is not None
    assert signal.side is Side.BUY
    assert "EMA" in signal.rationale
    assert signal.stop_loss < candles[-1].close < signal.take_profit


def test_momentum_strategy_generates_short_signal():
    candles = make_candles([150 - i * 1.0 for i in range(30)])
    signal = MomentumStrategy().generate(candles)
    assert signal is not None
    assert signal.side is Side.SELL
    assert "return" in signal.rationale


def test_mean_reversion_strategy_detects_oversold_market():
    candles = make_candles([100 - i * 0.8 for i in range(30)])
    signal = MeanReversionStrategy().generate(candles)
    assert signal is not None
    assert signal.side is Side.BUY
    assert "RSI" in signal.rationale


def test_engine_runs_all_baselines_and_returns_signals():
    candles = make_candles([100 + i * 0.8 for i in range(50)])
    signals = StrategyEngine().generate(candles)
    assert signals
    assert all(signal.symbol == "BTC/USDT" for signal in signals)


def test_strategy_rejects_mixed_or_unordered_candles():
    candles = make_candles([100 + i for i in range(40)])
    with pytest.raises(ValueError, match="chronological"):
        TrendFollowingStrategy().generate([candles[1], candles[0]])
    other = Candle("forex", "EUR_USD", "1h", candles[-1].timestamp,
                   1, 1.1, 0.9, 1.05, 0)
    with pytest.raises(ValueError, match="one market"):
        MomentumStrategy().generate([candles[0], other])

"""Deterministic, explainable baseline strategies. No broker or order access."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from trading_system.domain import Market, Side, Signal
from trading_system.market_data.models import Candle


class Strategy(Protocol):
    name: str

    def generate(self, candles: Sequence[Candle]) -> Signal | None: ...


@dataclass(frozen=True)
class StrategyConfig:
    fast_ema: int = 12
    slow_ema: int = 26
    momentum_lookback: int = 10
    momentum_threshold: float = 0.01
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    atr_period: int = 14
    stop_atr_multiple: float = 1.5
    reward_risk: float = 2.0

    def __post_init__(self) -> None:
        if min(self.fast_ema, self.slow_ema, self.momentum_lookback,
               self.rsi_period, self.atr_period) <= 0:
            raise ValueError("indicator periods must be positive")
        if self.fast_ema >= self.slow_ema:
            raise ValueError("fast_ema must be less than slow_ema")
        if not 0 < self.momentum_threshold:
            raise ValueError("momentum_threshold must be positive")
        if not 0 < self.rsi_oversold < self.rsi_overbought < 100:
            raise ValueError("RSI thresholds must be ordered within (0, 100)")
        if self.stop_atr_multiple <= 0 or self.reward_risk <= 0:
            raise ValueError("stop and reward/risk multipliers must be positive")


def _ema(values: Sequence[float], period: int) -> float:
    alpha = 2 / (period + 1)
    value = sum(values[:period]) / period
    for item in values[period:]:
        value = alpha * item + (1 - alpha) * value
    return value


def _rsi(values: Sequence[float], period: int) -> float:
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    window = changes[-period:]
    gains = sum(max(change, 0.0) for change in window) / period
    losses = sum(max(-change, 0.0) for change in window) / period
    if losses == 0:
        return 100.0 if gains else 50.0
    return 100 - (100 / (1 + gains / losses))


def _atr(candles: Sequence[Candle], period: int) -> float:
    ranges = []
    for previous, current in zip(candles[-period - 1:-1], candles[-period:]):
        ranges.append(max(current.high - current.low,
                          abs(current.high - previous.close),
                          abs(current.low - previous.close)))
    return sum(ranges) / len(ranges)


class BaseStrategy:
    name = "base"

    def __init__(self, config: StrategyConfig | None = None):
        self.config = config or StrategyConfig()

    def _signal(self, candles: Sequence[Candle], side: Side, confidence: float,
                reason: str) -> Signal:
        last = candles[-1]
        distance = max(_atr(candles, self.config.atr_period)
                       * self.config.stop_atr_multiple, last.close * 0.001)
        if side is Side.BUY:
            stop, target = last.close - distance, last.close + distance * self.config.reward_risk
        else:
            stop, target = last.close + distance, last.close - distance * self.config.reward_risk
        return Signal(
            market=Market(last.market), symbol=last.symbol, side=side,
            confidence=min(0.95, max(0.70, confidence)),
            stop_loss=stop, take_profit=target,
            rationale=f"{self.name}: {reason}; ATR-based stop, "
                      f"{self.config.reward_risk:.1f}:1 target",
            created_at=last.timestamp,
        )

    @staticmethod
    def _validate(candles: Sequence[Candle]) -> None:
        if len(candles) < 2:
            raise ValueError("at least two candles are required")
        first = candles[0]
        if any((c.market, c.symbol, c.timeframe) !=
               (first.market, first.symbol, first.timeframe) for c in candles):
            raise ValueError("candles must belong to one market, symbol and timeframe")
        if any(a.timestamp >= b.timestamp for a, b in zip(candles, candles[1:])):
            raise ValueError("candles must be strictly chronological")


class TrendFollowingStrategy(BaseStrategy):
    name = "trend_following"

    def generate(self, candles: Sequence[Candle]) -> Signal | None:
        self._validate(candles)
        cfg = self.config
        if len(candles) < cfg.slow_ema + cfg.atr_period + 1:
            return None
        closes = [c.close for c in candles]
        fast = _ema(closes[-(cfg.slow_ema + cfg.atr_period):], cfg.fast_ema)
        slow = _ema(closes[-(cfg.slow_ema + cfg.atr_period):], cfg.slow_ema)
        gap = (fast - slow) / slow
        if gap > 0 and closes[-1] > fast:
            return self._signal(candles, Side.BUY, 0.70 + min(abs(gap) * 8, 0.20),
                                f"fast EMA ({fast:.5f}) above slow EMA ({slow:.5f})")
        if gap < 0 and closes[-1] < fast:
            return self._signal(candles, Side.SELL, 0.70 + min(abs(gap) * 8, 0.20),
                                f"fast EMA ({fast:.5f}) below slow EMA ({slow:.5f})")
        return None


class MomentumStrategy(BaseStrategy):
    name = "momentum"

    def generate(self, candles: Sequence[Candle]) -> Signal | None:
        self._validate(candles)
        cfg = self.config
        needed = cfg.momentum_lookback + cfg.atr_period + 1
        if len(candles) < needed:
            return None
        closes = [c.close for c in candles]
        prior = closes[-cfg.momentum_lookback - 1]
        change = closes[-1] / prior - 1
        if change >= cfg.momentum_threshold:
            return self._signal(candles, Side.BUY,
                                0.70 + min(abs(change) / cfg.momentum_threshold * 0.05, 0.20),
                                f"{cfg.momentum_lookback}-candle return {change:.2%}")
        if change <= -cfg.momentum_threshold:
            return self._signal(candles, Side.SELL,
                                0.70 + min(abs(change) / cfg.momentum_threshold * 0.05, 0.20),
                                f"{cfg.momentum_lookback}-candle return {change:.2%}")
        return None


class MeanReversionStrategy(BaseStrategy):
    name = "mean_reversion"

    def generate(self, candles: Sequence[Candle]) -> Signal | None:
        self._validate(candles)
        cfg = self.config
        if len(candles) < cfg.rsi_period + cfg.atr_period + 1:
            return None
        value = _rsi([c.close for c in candles], cfg.rsi_period)
        if value <= cfg.rsi_oversold:
            return self._signal(candles, Side.BUY, 0.70 + (cfg.rsi_oversold - value) / 100,
                                f"RSI {value:.1f} at/below oversold threshold")
        if value >= cfg.rsi_overbought:
            return self._signal(candles, Side.SELL, 0.70 + (value - cfg.rsi_overbought) / 100,
                                f"RSI {value:.1f} at/above overbought threshold")
        return None


class StrategyEngine:
    """Runs independent strategies and returns every signal for downstream risk checks."""

    def __init__(self, strategies: Sequence[Strategy] | None = None):
        self.strategies = tuple(strategies or (
            TrendFollowingStrategy(), MomentumStrategy(), MeanReversionStrategy()
        ))
        names = [strategy.name for strategy in self.strategies]
        if len(names) != len(set(names)):
            raise ValueError("strategy names must be unique")

    def generate(self, candles: Sequence[Candle]) -> list[Signal]:
        signals = []
        for strategy in self.strategies:
            signal = strategy.generate(candles)
            if signal is not None:
                signals.append(signal)
        return signals

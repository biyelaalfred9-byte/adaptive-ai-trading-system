"""Deterministic trailing-stop state transitions for paper/research use.

Independent implementation informed by common stop-management patterns
reviewed in Jesse (MIT). No Jesse source code is copied. Stops are updated
after a completed candle and therefore become effective on the NEXT candle;
this avoids using the candle's high/low to claim an intrabar stop fill.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from trading_system.domain import Side


@dataclass(frozen=True)
class TrailingStopConfig:
    activation_pct: float = 0.02
    trail_distance_pct: float = 0.01
    breakeven_activation_pct: float = 0.01

    def __post_init__(self) -> None:
        for name, value in (
            ("activation_pct", self.activation_pct),
            ("trail_distance_pct", self.trail_distance_pct),
            ("breakeven_activation_pct", self.breakeven_activation_pct),
        ):
            if not isfinite(value) or value <= 0 or value >= 1:
                raise ValueError(f"{name} must be finite and between 0 and 1")


@dataclass(frozen=True)
class TrailingStopState:
    side: Side
    entry_price: float
    initial_stop: float
    stop_price: float
    best_price: float
    trailing_active: bool = False
    breakeven_active: bool = False

    @classmethod
    def create(cls, side: Side, entry_price: float, initial_stop: float) -> "TrailingStopState":
        if not isfinite(entry_price) or entry_price <= 0:
            raise ValueError("entry_price must be positive and finite")
        if not isfinite(initial_stop) or initial_stop <= 0:
            raise ValueError("initial_stop must be positive and finite")
        if side is Side.BUY and initial_stop >= entry_price:
            raise ValueError("long initial stop must be below entry")
        if side is Side.SELL and initial_stop <= entry_price:
            raise ValueError("short initial stop must be above entry")
        return cls(side, entry_price, initial_stop, initial_stop, entry_price)


def update_trailing_stop(
    state: TrailingStopState,
    candle_high: float,
    candle_low: float,
    config: TrailingStopConfig | None = None,
) -> TrailingStopState:
    """Update a stop from one completed OHLC candle; never loosen the stop."""
    config = config or TrailingStopConfig()
    if (not isfinite(candle_high) or not isfinite(candle_low)
            or candle_high <= 0 or candle_low <= 0 or candle_low > candle_high):
        raise ValueError("candle high/low must be finite, positive and correctly ordered")

    if state.side is Side.BUY:
        best = max(state.best_price, candle_high)
        profit = best / state.entry_price - 1.0
        be_active = state.breakeven_active or profit >= config.breakeven_activation_pct
        trail_active = state.trailing_active or profit >= config.activation_pct
        candidate = state.initial_stop
        if be_active:
            candidate = max(candidate, state.entry_price)
        if trail_active:
            candidate = max(candidate, best * (1.0 - config.trail_distance_pct))
        stop = max(state.stop_price, candidate)
    else:
        best = min(state.best_price, candle_low)
        profit = state.entry_price / best - 1.0
        be_active = state.breakeven_active or profit >= config.breakeven_activation_pct
        trail_active = state.trailing_active or profit >= config.activation_pct
        candidate = state.initial_stop
        if be_active:
            candidate = min(candidate, state.entry_price)
        if trail_active:
            candidate = min(candidate, best * (1.0 + config.trail_distance_pct))
        stop = min(state.stop_price, candidate)

    return replace(
        state,
        stop_price=stop,
        best_price=best,
        trailing_active=trail_active,
        breakeven_active=be_active,
    )

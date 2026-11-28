"""Entry-protection primitives inspired by Freqtrade protections.

Independent implementation; no Freqtrade source code is copied. These are
pure functions over supplied closed-trade/equity records and are not wired into
the paper engine yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import Iterable


@dataclass(frozen=True)
class ClosedTrade:
    symbol: str
    closed_at: datetime
    net_profit_pct: float
    exit_reason: str


@dataclass(frozen=True)
class ProtectionConfig:
    lookback: timedelta = timedelta(hours=24)
    stoploss_limit: int = 3
    lockout: timedelta = timedelta(hours=6)
    max_drawdown: float = 0.05

    def __post_init__(self) -> None:
        if self.lookback.total_seconds() <= 0 or self.lockout.total_seconds() <= 0:
            raise ValueError("lookback and lockout must be positive")
        if self.stoploss_limit < 1:
            raise ValueError("stoploss_limit must be at least one")
        if not isfinite(self.max_drawdown) or not 0 < self.max_drawdown < 1:
            raise ValueError("max_drawdown must be between zero and one")


@dataclass(frozen=True)
class ProtectionDecision:
    blocked: bool
    reason: str
    locked_until: datetime | None = None


def stoploss_cooldown(
    trades: Iterable[ClosedTrade],
    now: datetime,
    config: ProtectionConfig | None = None,
    *,
    symbol: str | None = None,
) -> ProtectionDecision:
    """Block new entries after N stop-loss exits inside a rolling time window."""
    config = config or ProtectionConfig()
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(now.tzinfo)
    start = now - config.lookback
    stop_reasons = {"stop_loss", "trailing_stop_loss", "liquidation", "stoploss"}
    recent = [
        trade for trade in trades
        if trade.closed_at.tzinfo is not None
        and start < trade.closed_at <= now
        and trade.exit_reason.lower() in stop_reasons
        and trade.net_profit_pct < 0
        and (symbol is None or trade.symbol == symbol)
    ]
    if len(recent) < config.stoploss_limit:
        return ProtectionDecision(False, "stop-loss threshold not reached")
    latest = max(trade.closed_at for trade in recent)
    return ProtectionDecision(
        True,
        f"{len(recent)} stop-loss exits inside lookback window",
        latest + config.lockout,
    )


def maximum_drawdown(equity_curve: Iterable[float]) -> float:
    """Return peak-to-trough fractional drawdown for a chronological equity curve."""
    values = list(equity_curve)
    if not values:
        raise ValueError("equity_curve cannot be empty")
    if any(not isfinite(v) or v <= 0 for v in values):
        raise ValueError("equity values must be positive and finite")
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = max(worst, (peak - value) / peak)
    return worst


def drawdown_protection(
    equity_curve: Iterable[float],
    threshold: float = 0.05,
) -> ProtectionDecision:
    """Block new entries when observed peak-to-trough drawdown reaches threshold."""
    if not isfinite(threshold) or not 0 < threshold < 1:
        raise ValueError("threshold must be between zero and one")
    drawdown = maximum_drawdown(equity_curve)
    if drawdown >= threshold:
        return ProtectionDecision(True, f"maximum drawdown reached: {drawdown:.2%}")
    return ProtectionDecision(False, f"drawdown within limit: {drawdown:.2%}")

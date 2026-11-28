"""Risk-budgeted position sizing, independently implemented from Jesse's sizing concepts.

No Jesse source code is copied. Quantities are capped by available capital and
include estimated entry+stop exit fees in the per-unit risk budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from trading_system.domain import Side


@dataclass(frozen=True)
class PositionSize:
    quantity: float
    risk_budget: float
    estimated_loss_at_stop: float
    notional: float
    capped_by_capital: bool


def risk_to_quantity(
    *,
    equity: float,
    risk_fraction: float,
    entry_price: float,
    stop_price: float,
    side: Side,
    fee_rate: float = 0.0,
    available_capital: float | None = None,
) -> PositionSize:
    """Size a position so stop-distance loss plus estimated fees fits risk budget.

    `available_capital` is the maximum permitted entry notional (spot, 1x).
    Leverage is intentionally not modeled.
    """
    values = (equity, risk_fraction, entry_price, stop_price, fee_rate)
    if any(not isfinite(v) for v in values):
        raise ValueError("sizing inputs must be finite")
    if equity <= 0 or not 0 < risk_fraction <= 1:
        raise ValueError("equity must be positive and risk_fraction in (0, 1]")
    if entry_price <= 0 or stop_price <= 0 or fee_rate < 0:
        raise ValueError("prices must be positive and fee_rate non-negative")
    if side is Side.BUY and stop_price >= entry_price:
        raise ValueError("long stop must be below entry")
    if side is Side.SELL and stop_price <= entry_price:
        raise ValueError("short stop must be above entry")
    if available_capital is not None and (not isfinite(available_capital) or available_capital <= 0):
        raise ValueError("available_capital must be positive and finite")

    risk_budget = equity * risk_fraction
    price_risk = abs(entry_price - stop_price)
    fee_per_unit = fee_rate * (entry_price + stop_price)
    unit_risk = price_risk + fee_per_unit
    if unit_risk <= 0:
        raise ValueError("per-unit risk must be positive")

    risk_quantity = risk_budget / unit_risk
    capital_limit = float("inf") if available_capital is None else available_capital / entry_price
    quantity = min(risk_quantity, capital_limit)
    notional = quantity * entry_price
    estimated_loss = quantity * unit_risk
    return PositionSize(
        quantity=quantity,
        risk_budget=risk_budget,
        estimated_loss_at_stop=estimated_loss,
        notional=notional,
        capped_by_capital=capital_limit < risk_quantity,
    )

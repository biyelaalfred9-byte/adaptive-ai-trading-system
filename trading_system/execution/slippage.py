"""Order-book slippage estimation and hard execution guard.

This is an independent implementation of a common market-impact control
pattern used by execution systems. It is not copied from Hummingbot. The
Hummingbot project informed the component boundary and the need to size fills
against available depth; see docs/COMPONENT_EXTRACTIONS.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

from trading_system.domain import Side


@dataclass(frozen=True)
class BookLevel:
    price: float
    quantity: float


@dataclass(frozen=True)
class SlippageEstimate:
    accepted: bool
    requested_quantity: float
    filled_quantity: float
    vwap: float | None
    slippage_bps: float | None
    reason: str


class SlippageGuard:
    """Estimate depth-weighted execution price and enforce a bps ceiling."""

    def __init__(self, max_slippage_bps: float = 15.0) -> None:
        if not isfinite(max_slippage_bps) or max_slippage_bps < 0:
            raise ValueError("max_slippage_bps must be finite and non-negative")
        self.max_slippage_bps = float(max_slippage_bps)

    @staticmethod
    def _validated(levels: Iterable[BookLevel], *, asks: bool) -> list[BookLevel]:
        result = list(levels)
        for level in result:
            if (not isfinite(level.price) or not isfinite(level.quantity)
                    or level.price <= 0 or level.quantity <= 0):
                raise ValueError("book levels require finite positive price and quantity")
        return sorted(result, key=lambda item: item.price, reverse=not asks)

    def estimate(
        self,
        side: Side,
        quantity: float,
        reference_price: float,
        bids: Iterable[BookLevel],
        asks: Iterable[BookLevel],
    ) -> SlippageEstimate:
        if not isfinite(quantity) or quantity <= 0:
            raise ValueError("quantity must be finite and positive")
        if not isfinite(reference_price) or reference_price <= 0:
            raise ValueError("reference_price must be finite and positive")

        book = self._validated(asks if side is Side.BUY else bids,
                               asks=(side is Side.BUY))
        remaining = quantity
        notional = 0.0
        filled = 0.0
        for level in book:
            take = min(remaining, level.quantity)
            notional += take * level.price
            filled += take
            remaining -= take
            if remaining <= 1e-12:
                break

        if remaining > 1e-12:
            return SlippageEstimate(
                False, quantity, filled, None, None,
                "insufficient order-book depth for requested quantity",
            )

        vwap = notional / filled
        adverse_move = (vwap - reference_price) if side is Side.BUY else (reference_price - vwap)
        slippage_bps = max(0.0, adverse_move / reference_price * 10_000)
        accepted = slippage_bps <= self.max_slippage_bps
        return SlippageEstimate(
            accepted, quantity, filled, vwap, slippage_bps,
            "within slippage limit" if accepted else "slippage limit exceeded",
        )

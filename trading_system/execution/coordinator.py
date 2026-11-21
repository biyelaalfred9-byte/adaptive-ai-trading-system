"""Risk-gated paper trading coordinator.

This is the only orchestration path from strategy signals to an execution
adapter. It sizes orders from stop distance, applies immutable risk checks,
and accepts simulated fills only.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Sequence

from trading_system.config import RiskConfig
from trading_system.domain import ExecutionResult, OrderRequest, Side, Signal
from trading_system.execution.base import ExecutionAdapter
from trading_system.journal import TradeJournal
from trading_system.risk import RiskGate, RiskSnapshot


@dataclass(frozen=True)
class CandidateResult:
    signal: Signal
    approved: bool
    reason: str
    order: OrderRequest | None = None
    execution: ExecutionResult | None = None


class PaperTradingCoordinator:
    """Coordinates signal -> risk gate -> sized paper order -> journal."""

    def __init__(
        self,
        executor: ExecutionAdapter,
        journal: TradeJournal | None = None,
        risk_config: RiskConfig | None = None,
        risk_gate: RiskGate | None = None,
    ) -> None:
        self.executor = executor
        self.journal = journal
        self.risk_config = risk_config or RiskConfig()
        self.risk_gate = risk_gate or RiskGate(self.risk_config)

    def process(
        self,
        signals: Sequence[Signal],
        reference_prices: dict[str, float],
        snapshot: RiskSnapshot,
    ) -> list[CandidateResult]:
        """Process candidates in order; each accepted fill consumes one position slot."""
        results: list[CandidateResult] = []
        current_snapshot = snapshot

        for signal in signals:
            reference_price = reference_prices.get(signal.symbol)
            if reference_price is None or not isfinite(reference_price) or reference_price <= 0:
                results.append(CandidateResult(
                    signal, False, "missing or invalid reference price"
                ))
                continue

            if signal.side is Side.BUY:
                valid_levels = signal.stop_loss < reference_price < signal.take_profit
            else:
                valid_levels = signal.take_profit < reference_price < signal.stop_loss
            if not valid_levels:
                results.append(CandidateResult(
                    signal, False, "stop-loss and take-profit must bracket price in trade direction"
                ))
                continue

            decision = self.risk_gate.evaluate(signal, current_snapshot)
            if not decision.approved:
                results.append(CandidateResult(signal, False, decision.reason))
                continue

            risk_fraction = min(
                self.risk_config.risk_per_trade,
                self.risk_config.hard_risk_cap,
            )
            risk_budget = current_snapshot.equity * risk_fraction
            stop_distance = abs(reference_price - signal.stop_loss)
            risk_quantity = risk_budget / stop_distance
            max_notional = current_snapshot.equity * self.risk_config.max_leverage
            notional_quantity = max_notional / reference_price
            quantity = min(risk_quantity, notional_quantity)
            if not isfinite(quantity) or quantity <= 0:
                results.append(CandidateResult(signal, False, "calculated order quantity is invalid"))
                continue

            order = OrderRequest(
                symbol=signal.symbol,
                side=signal.side,
                quantity=quantity,
                reference_price=reference_price,
            )
            execution = self.executor.execute(order)
            if not execution.simulated:
                raise RuntimeError("paper coordinator rejected a non-simulated execution result")
            if execution.status != "filled" or execution.filled_quantity <= 0:
                results.append(CandidateResult(
                    signal, False, f"paper execution did not fill: {execution.status}",
                    order=order, execution=execution,
                ))
                continue
            if self.journal is not None:
                self.journal.record(order, execution)

            results.append(CandidateResult(
                signal, True, "approved and filled in paper mode",
                order=order, execution=execution,
            ))
            current_snapshot = replace(
                current_snapshot,
                open_positions=current_snapshot.open_positions + 1,
            )

        return results

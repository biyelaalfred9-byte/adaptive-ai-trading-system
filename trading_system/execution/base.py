"""Execution boundary shared by paper and future venue adapters.

Strategy code must never depend on an execution adapter. A caller must apply
RiskGate before constructing and submitting an OrderRequest. The only
implemented adapter remains PaperExecutor; this protocol does not enable live
trading.
"""
from typing import Protocol, runtime_checkable

from trading_system.domain import ExecutionResult, OrderRequest


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Minimal structural contract for an order execution implementation."""

    def execute(self, order: OrderRequest) -> ExecutionResult:
        """Execute or simulate an order and return its fill details."""
        ...

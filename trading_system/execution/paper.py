from uuid import uuid4
from ..domain import ExecutionResult, OrderRequest


class PaperExecutor:
    """Simple marketable paper fill at the supplied reference price.

    This is a development stub: it does not model spread, slippage, latency,
    partial fills, order-book depth or fees. Do not use its results as evidence
    of a profitable strategy.
    """

    def execute(self, order: OrderRequest) -> ExecutionResult:
        return ExecutionResult(
            order_id=str(uuid4()),
            status="filled",
            filled_quantity=order.quantity,
            average_price=order.reference_price,
            simulated=True,
        )

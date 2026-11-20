from dataclasses import dataclass
from uuid import uuid4

from ..domain import ExecutionResult, OrderRequest, Side


@dataclass(frozen=True)
class PaperCostModel:
    """Configurable one-way costs expressed in basis points."""
    spread_bps: float = 2.0
    slippage_bps: float = 1.0
    fee_bps: float = 10.0

    def __post_init__(self) -> None:
        if min(self.spread_bps, self.slippage_bps, self.fee_bps) < 0:
            raise ValueError("paper trading costs cannot be negative")


class PaperExecutor:
    """Deterministic market-fill simulator with configurable transaction costs.

    Costs are estimates, not a substitute for order-book replay or venue-specific
    execution modelling. A buy pays above the reference price; a sell receives
    below it. Fees are reported separately from the execution price.
    """

    def __init__(self, costs: PaperCostModel | None = None):
        self.costs = costs or PaperCostModel()

    def execute(self, order: OrderRequest) -> ExecutionResult:
        direction = 1.0 if order.side == Side.BUY else -1.0
        spread = order.reference_price * self.costs.spread_bps / 20_000
        slippage = order.reference_price * self.costs.slippage_bps / 10_000
        fill_price = order.reference_price + direction * (spread + slippage)
        notional = order.quantity * fill_price
        fee = notional * self.costs.fee_bps / 10_000
        return ExecutionResult(
            order_id=str(uuid4()),
            status="filled",
            filled_quantity=order.quantity,
            average_price=fill_price,
            simulated=True,
            fee_paid=fee,
            spread_cost=spread * order.quantity,
            slippage_cost=slippage * order.quantity,
        )

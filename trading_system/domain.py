from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class Market(str, Enum):
    CRYPTO = "crypto"
    FOREX = "forex"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Signal:
    market: Market
    symbol: str
    side: Side
    confidence: float
    stop_loss: float
    take_profit: float
    rationale: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.stop_loss <= 0 or self.take_profit <= 0:
            raise ValueError("stop-loss and take-profit must be positive")


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    quantity: float
    reference_price: float

    def __post_init__(self) -> None:
        if self.quantity <= 0 or self.reference_price <= 0:
            raise ValueError("quantity and reference price must be positive")


@dataclass(frozen=True)
class ExecutionResult:
    order_id: str
    status: str
    filled_quantity: float
    average_price: float
    simulated: bool = True


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

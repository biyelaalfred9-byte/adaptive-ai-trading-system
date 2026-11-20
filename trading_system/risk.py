from dataclasses import dataclass
from .config import RiskConfig
from .domain import Signal


@dataclass(frozen=True)
class RiskSnapshot:
    equity: float
    daily_pnl: float
    current_drawdown: float
    open_positions: int


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str


class RiskGate:
    """Deterministic risk checks. Signal text/AI cannot override these rules."""

    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()

    def evaluate(self, signal: Signal, snapshot: RiskSnapshot) -> RiskDecision:
        if snapshot.equity <= 0:
            return RiskDecision(False, "equity must be positive")
        if signal.confidence < self.config.min_confidence:
            return RiskDecision(False, "signal confidence below threshold")
        if snapshot.daily_pnl <= -(snapshot.equity * self.config.daily_loss_limit):
            return RiskDecision(False, "daily loss limit reached")
        if snapshot.current_drawdown >= self.config.max_drawdown:
            return RiskDecision(False, "maximum drawdown reached")
        if snapshot.open_positions >= self.config.max_open_positions:
            return RiskDecision(False, "maximum open positions reached")
        return RiskDecision(True, "approved for paper execution only")

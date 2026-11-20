from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: float = 0.005
    hard_risk_cap: float = 0.01
    daily_loss_limit: float = 0.02
    max_drawdown: float = 0.05
    max_open_positions: int = 2
    min_confidence: float = 0.70
    max_leverage: float = 1.0

    def __post_init__(self) -> None:
        if not 0 < self.risk_per_trade <= self.hard_risk_cap <= 0.01:
            raise ValueError("risk per trade must be positive and capped at 1%")
        if not 0 < self.daily_loss_limit <= 0.02:
            raise ValueError("daily loss limit must be in (0, 2%]")
        if not 0 < self.max_drawdown <= 0.05:
            raise ValueError("max drawdown must be in (0, 5%]")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be at least 1")
        if not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")
        if self.max_leverage != 1.0:
            raise ValueError("leverage is disabled in the initial release")

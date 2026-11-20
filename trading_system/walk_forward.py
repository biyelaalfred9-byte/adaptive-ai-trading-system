"""Chronological walk-forward evaluation for strategy research.

Training candles provide indicator warm-up only. All reported trades come from
the immediately following out-of-sample test window.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Sequence

from trading_system.backtesting import BacktestResult, Backtester, SignalGenerator
from trading_system.market_data.models import Candle
from trading_system.research import walk_forward_splits


@dataclass(frozen=True)
class SelectionPolicy:
    min_oos_trades: int = 30
    min_profitable_fold_ratio: float = 0.60
    max_worst_fold_drawdown_pct: float = 5.0
    min_profit_factor: float = 1.10

    def __post_init__(self) -> None:
        if self.min_oos_trades < 1:
            raise ValueError("min_oos_trades must be at least 1")
        if not 0 <= self.min_profitable_fold_ratio <= 1:
            raise ValueError("min_profitable_fold_ratio must be within [0, 1]")
        if self.max_worst_fold_drawdown_pct < 0:
            raise ValueError("max_worst_fold_drawdown_pct cannot be negative")
        if self.min_profit_factor < 0:
            raise ValueError("min_profit_factor cannot be negative")


@dataclass(frozen=True)
class FoldEvaluation:
    fold_number: int
    train_start: object
    train_end: object
    test_start: object
    test_end: object
    result: BacktestResult


@dataclass(frozen=True)
class StrategyEvaluation:
    strategy: str
    folds: tuple[FoldEvaluation, ...]
    oos_trade_count: int
    oos_win_rate: float
    pooled_profit_factor: float
    average_fold_return_pct: float
    profitable_fold_ratio: float
    worst_fold_drawdown_pct: float
    eligible_for_paper_testing: bool
    reasons: tuple[str, ...]


class WalkForwardEvaluator:
    """Evaluate strategies on rolling test windows without training-period PnL."""

    def __init__(self, backtester: Backtester | None = None,
                 policy: SelectionPolicy | None = None):
        self.backtester = backtester or Backtester()
        self.policy = policy or SelectionPolicy()

    def evaluate(self, candles: Sequence[Candle],
                 strategies: Sequence[SignalGenerator],
                 train_size: int, test_size: int) -> tuple[StrategyEvaluation, ...]:
        if not strategies:
            raise ValueError("at least one strategy is required")
        names = [strategy.name for strategy in strategies]
        if len(names) != len(set(names)):
            raise ValueError("strategy names must be unique")
        folds = list(walk_forward_splits(candles, train_size, test_size))
        if not folds:
            raise ValueError("not enough candles for one train/test fold")

        reports = []
        for strategy in strategies:
            fold_reports = []
            all_trades = []
            for fold_number, (train, test) in enumerate(folds, start=1):
                combined = list(train) + list(test)
                # The backtester sees train candles for indicator warm-up, but
                # cannot generate signals or open positions until test begins.
                result = self.backtester.run(
                    combined, strategy, start_index=len(train)
                )
                all_trades.extend(result.trades)
                fold_reports.append(FoldEvaluation(
                    fold_number=fold_number,
                    train_start=train[0].timestamp,
                    train_end=train[-1].timestamp,
                    test_start=test[0].timestamp,
                    test_end=test[-1].timestamp,
                    result=result,
                ))

            count = len(all_trades)
            wins = sum(trade.net_pnl > 0 for trade in all_trades)
            winning_pnl = sum(trade.net_pnl for trade in all_trades
                              if trade.net_pnl > 0)
            losing_pnl = sum(trade.net_pnl for trade in all_trades
                             if trade.net_pnl < 0)
            profit_factor = (winning_pnl / abs(losing_pnl) if losing_pnl
                             else (inf if winning_pnl else 0.0))
            fold_returns = [fold.result.metrics.total_return_pct
                            for fold in fold_reports]
            profitable_ratio = sum(value > 0 for value in fold_returns) / len(fold_returns)
            worst_drawdown = max(
                fold.result.metrics.max_drawdown_pct for fold in fold_reports
            )
            average_return = sum(fold_returns) / len(fold_returns)

            reasons = []
            policy = self.policy
            if count < policy.min_oos_trades:
                reasons.append(
                    f"only {count} out-of-sample trades; requires {policy.min_oos_trades}"
                )
            if profitable_ratio < policy.min_profitable_fold_ratio:
                reasons.append(
                    f"profitable fold ratio {profitable_ratio:.1%} is below "
                    f"{policy.min_profitable_fold_ratio:.1%}"
                )
            if worst_drawdown > policy.max_worst_fold_drawdown_pct:
                reasons.append(
                    f"worst fold drawdown {worst_drawdown:.2f}% exceeds "
                    f"{policy.max_worst_fold_drawdown_pct:.2f}%"
                )
            if profit_factor < policy.min_profit_factor:
                reasons.append(
                    f"pooled profit factor {profit_factor:.2f} is below "
                    f"{policy.min_profit_factor:.2f}"
                )

            reports.append(StrategyEvaluation(
                strategy=strategy.name,
                folds=tuple(fold_reports),
                oos_trade_count=count,
                oos_win_rate=wins / count if count else 0.0,
                pooled_profit_factor=profit_factor,
                average_fold_return_pct=average_return,
                profitable_fold_ratio=profitable_ratio,
                worst_fold_drawdown_pct=worst_drawdown,
                eligible_for_paper_testing=not reasons,
                reasons=tuple(reasons),
            ))
        return tuple(reports)

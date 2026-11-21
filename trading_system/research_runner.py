"""Config-driven, read-only multi-market strategy research runner.

Run with: python -m trading_system.research_runner research.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from trading_system.backtesting import Backtester, BacktestConfig
from trading_system.execution.paper import PaperCostModel
from trading_system.market_data.storage import CandleStore
from trading_system.strategies import (
    MeanReversionStrategy, MomentumStrategy, Strategy, TrendFollowingStrategy,
)
from trading_system.walk_forward import SelectionPolicy, WalkForwardEvaluator


@dataclass(frozen=True)
class ResearchJob:
    market: str
    symbol: str
    timeframe: str
    train_size: int
    test_size: int
    candle_limit: int = 20_000

    def __post_init__(self) -> None:
        if not all((self.market, self.symbol, self.timeframe)):
            raise ValueError("market, symbol and timeframe are required")
        if self.train_size < 1 or self.test_size < 1:
            raise ValueError("train_size and test_size must be positive")
        if self.candle_limit < self.train_size + self.test_size:
            raise ValueError("candle_limit must cover at least one train/test fold")


def default_strategies() -> tuple[Strategy, ...]:
    return (TrendFollowingStrategy(), MomentumStrategy(), MeanReversionStrategy())


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        if value == float("inf"):
            return "Infinity"
        if value == float("-inf"):
            return "-Infinity"
        if value != value:
            return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _evaluation_summary(evaluation: Any) -> dict[str, Any]:
    trades = [trade for fold in evaluation.folds for trade in fold.result.trades]
    gross = sum(trade.gross_pnl for trade in trades)
    costs = sum(trade.costs for trade in trades)
    net = sum(trade.net_pnl for trade in trades)
    winners = sum(trade.net_pnl for trade in trades if trade.net_pnl > 0)
    losers = sum(trade.net_pnl for trade in trades if trade.net_pnl < 0)
    profit_factor = winners / abs(losers) if losers else (float("inf") if winners else 0.0)
    fold_returns = [fold.result.metrics.total_return_pct for fold in evaluation.folds]
    return {
        "trade_count": len(trades),
        "gross_pnl": gross,
        "estimated_costs": costs,
        "net_pnl": net,
        "costs_as_pct_of_positive_gross": (
            costs / gross * 100 if gross > 0 else None
        ),
        "net_profit_factor": profit_factor,
        "average_fold_return_pct": (
            sum(fold_returns) / len(fold_returns) if fold_returns else 0.0
        ),
        "profitable_fold_ratio": (
            sum(value > 0 for value in fold_returns) / len(fold_returns)
            if fold_returns else 0.0
        ),
        "exit_reasons": dict(sorted(Counter(t.exit_reason for t in trades).items())),
    }


def _buy_hold_benchmark(candles: Sequence[Any], evaluation: Any) -> dict[str, Any]:
    index_by_time = {candle.timestamp: index for index, candle in enumerate(candles)}
    returns = []
    for fold in evaluation.folds:
        start = index_by_time[fold.test_start]
        end = index_by_time[fold.test_end]
        first = candles[start]
        last = candles[end]
        returns.append((last.close / first.open - 1) * 100)
    return {
        "method": "long_only_first_test_open_to_last_test_close",
        "fold_returns_pct": returns,
        "average_fold_return_pct": sum(returns) / len(returns) if returns else 0.0,
        "profitable_fold_ratio": (
            sum(value > 0 for value in returns) / len(returns) if returns else 0.0
        ),
    }


class ResearchRunner:
    """Evaluate configured market series from a local CandleStore."""

    def __init__(
        self,
        store: CandleStore,
        evaluator: WalkForwardEvaluator | None = None,
        strategies: Sequence[Strategy] | None = None,
    ):
        self.store = store
        self.evaluator = evaluator or WalkForwardEvaluator(
            Backtester(BacktestConfig())
        )
        self.strategies = tuple(strategies or default_strategies())
        names = [strategy.name for strategy in self.strategies]
        if not names or len(names) != len(set(names)):
            raise ValueError("strategies must be non-empty and uniquely named")

    def _diagnostics(self, candles: Sequence[Any], job: ResearchJob,
                     strategy: Strategy, evaluation: Any) -> dict[str, Any]:
        base_config = self.evaluator.backtester.config
        current_costs = base_config.costs
        zero_costs = PaperCostModel(0, 0, 0)
        half_costs = PaperCostModel(
            current_costs.spread_bps / 2,
            current_costs.slippage_bps / 2,
            current_costs.fee_bps / 2,
        )
        scenarios = {
            "zero_cost": zero_costs,
            "half_configured_cost": half_costs,
            "configured_cost": current_costs,
        }
        sensitivity = {}
        for name, costs in scenarios.items():
            if name == "configured_cost":
                scenario_evaluation = evaluation
            else:
                config = BacktestConfig(
                    initial_equity=base_config.initial_equity,
                    position_fraction=base_config.position_fraction,
                    costs=costs,
                    allow_short=base_config.allow_short,
                )
                evaluator = WalkForwardEvaluator(
                    Backtester(config), policy=self.evaluator.policy
                )
                scenario_evaluation, = evaluator.evaluate(
                    candles, [strategy], job.train_size, job.test_size
                )
            sensitivity[name] = _evaluation_summary(scenario_evaluation)

        return {
            "pnl_and_exits": _evaluation_summary(evaluation),
            "cost_sensitivity": sensitivity,
            "buy_hold_benchmark": _buy_hold_benchmark(candles, evaluation),
        }

    def run(self, jobs: Sequence[ResearchJob]) -> dict[str, Any]:
        if not jobs:
            raise ValueError("at least one research job is required")
        results = []
        for job in jobs:
            candles = self.store.get(
                job.market, job.symbol, job.timeframe, limit=job.candle_limit
            )
            entry: dict[str, Any] = {
                "market": job.market,
                "symbol": job.symbol,
                "timeframe": job.timeframe,
                "candles_loaded": len(candles),
                "strategies": [],
            }
            if len(candles) < job.train_size + job.test_size:
                entry["status"] = "insufficient_data"
                entry["message"] = (
                    f"Need at least {job.train_size + job.test_size} candles "
                    "for one complete fold."
                )
            else:
                try:
                    evaluations = self.evaluator.evaluate(
                        candles, self.strategies, job.train_size, job.test_size
                    )
                    entry["status"] = "evaluated"
                    entry["strategies"] = []
                    for strategy, evaluation in zip(self.strategies, evaluations):
                        strategy_report = asdict(evaluation)
                        strategy_report["diagnostics"] = self._diagnostics(
                            candles, job, strategy, evaluation
                        )
                        entry["strategies"].append(_json_safe(strategy_report))
                except ValueError as exc:
                    entry["status"] = "evaluation_error"
                    entry["message"] = str(exc)
            results.append(entry)

        return {
            "report_version": 2,
            "mode": "historical_research_only",
            "live_trading_enabled": False,
            "strategy_activation": "manual_paper_testing_only",
            "jobs": results,
            "summary": {
                "jobs_total": len(results),
                "jobs_evaluated": sum(r["status"] == "evaluated" for r in results),
                "jobs_with_insufficient_data": sum(
                    r["status"] == "insufficient_data" for r in results
                ),
                "jobs_with_errors": sum(
                    r["status"] == "evaluation_error" for r in results
                ),
                "paper_testing_candidates": [
                    {
                        "market": r["market"],
                        "symbol": r["symbol"],
                        "timeframe": r["timeframe"],
                        "strategy": s["strategy"],
                    }
                    for r in results if r["status"] == "evaluated"
                    for s in r["strategies"]
                    if s["eligible_for_paper_testing"]
                ],
            },
        }


def load_config(path: str | Path) -> tuple[str, list[ResearchJob], SelectionPolicy]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    store_path = payload.get("database", "market_data.sqlite3")
    policy = SelectionPolicy(**payload.get("selection_policy", {}))
    jobs = [ResearchJob(**item) for item in payload.get("jobs", [])]
    if not jobs:
        raise ValueError("config must contain at least one job")
    return store_path, jobs, policy


def main() -> None:
    parser = argparse.ArgumentParser(description="Run historical strategy research.")
    parser.add_argument("config", help="Path to research JSON configuration")
    parser.add_argument("--output", default="research_report.json",
                        help="Output JSON report path")
    args = parser.parse_args()

    store_path, jobs, policy = load_config(args.config)
    report = ResearchRunner(
        CandleStore(store_path),
        evaluator=WalkForwardEvaluator(policy=policy),
    ).run(jobs)
    Path(args.output).write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(f"Research report written to {args.output}")
    print(json.dumps(report["summary"], indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

"""Continuous, candle-driven paper trading orchestration.

Signals are computed from the candle before the entry candle and simulated at
the next candle open. Only completed candles are processed. No live adapter is
constructed or accepted by this engine.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from trading_system.execution.coordinator import CandidateResult, PaperTradingCoordinator
from trading_system.market_data.collector import MarketDataCollector
from trading_system.market_data.models import Candle
from trading_system.market_data.storage import CandleStore
from trading_system.portfolio import ExitEvent, PaperPortfolio
from trading_system.strategies import StrategyEngine

logger = logging.getLogger(__name__)


def candle_duration(timeframe: str) -> timedelta:
    """Convert common CCXT/OANDA timeframe labels to a duration."""
    if timeframe in {"M", "1M"}:
        return timedelta(days=30)
    value = timeframe.upper()
    aliases = {"D": "1D", "W": "1W"}
    value = aliases.get(value, value)
    match = re.fullmatch(r"(\d+)([SMHDW])", value)
    if not match:
        raise ValueError(f"unsupported candle timeframe: {timeframe}")
    amount, unit = int(match.group(1)), match.group(2)
    units = {
        "S": timedelta(seconds=amount),
        "M": timedelta(minutes=amount),
        "H": timedelta(hours=amount),
        "D": timedelta(days=amount),
        "W": timedelta(weeks=amount),
    }
    return units[unit]


@dataclass(frozen=True)
class PaperCycleReport:
    market: str
    symbol: str
    timeframe: str
    candles_processed: int
    signals_generated: int
    entries_filled: int
    exits: tuple[ExitEvent, ...]
    candidates: tuple[CandidateResult, ...]


class PaperTradingEngine:
    """Poll, evaluate, risk-check, paper-fill, exit and mark positions."""

    def __init__(
        self,
        collector: MarketDataCollector,
        candle_store: CandleStore,
        portfolio: PaperPortfolio,
        coordinator: PaperTradingCoordinator,
        strategies: StrategyEngine | None = None,
        state_path: str = "paper_engine_state.sqlite3",
        history_limit: int = 500,
        process_existing_history: bool = False,
    ) -> None:
        if history_limit < 50:
            raise ValueError("history_limit must be at least 50 candles")
        if coordinator.portfolio is not portfolio:
            raise ValueError("coordinator must use the engine's PaperPortfolio")
        if not getattr(coordinator.executor, "costs", None):
            raise ValueError("paper engine requires the configured PaperExecutor")
        self.collector = collector
        self.candle_store = candle_store
        self.portfolio = portfolio
        self.coordinator = coordinator
        self.strategies = strategies or StrategyEngine()
        self.history_limit = history_limit
        self.process_existing_history = process_existing_history
        self.state_path = str(Path(state_path))
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS engine_cursors (
                    market TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    last_timestamp TEXT NOT NULL,
                    PRIMARY KEY (market, symbol, timeframe)
                )
            """)

    def _connect(self):
        return sqlite3.connect(self.state_path)

    def _cursor(self, market: str, symbol: str, timeframe: str) -> datetime | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT last_timestamp FROM engine_cursors
                   WHERE market=? AND symbol=? AND timeframe=?""",
                (market, symbol, timeframe),
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def _save_cursor(self, candle: Candle) -> None:
        with self._connect() as db:
            db.execute("""
                INSERT INTO engine_cursors VALUES (?, ?, ?, ?)
                ON CONFLICT(market, symbol, timeframe)
                DO UPDATE SET last_timestamp=excluded.last_timestamp
            """, (candle.market, candle.symbol, candle.timeframe,
                  candle.timestamp.astimezone(timezone.utc).isoformat()))

    def _marks(self, market: str, symbol: str, timeframe: str,
               current: Candle, at_open: bool) -> dict[str, float]:
        marks: dict[str, float] = {
            symbol: current.open if at_open else current.close
        }
        for position in self.portfolio.open_positions():
            if position.symbol in marks:
                continue
            latest = []
            for candidate_market in dict.fromkeys((market, "crypto", "forex")):
                latest = self.candle_store.get(
                    candidate_market, position.symbol, timeframe, limit=1
                )
                if latest:
                    break
            if latest:
                marks[position.symbol] = latest[-1].close
        missing = [p.symbol for p in self.portfolio.open_positions()
                   if p.symbol not in marks]
        if missing:
            raise RuntimeError(
                "cannot safely evaluate portfolio risk without marks for: "
                + ", ".join(sorted(set(missing)))
            )
        return marks

    def process_subscription(
        self, *, market: str, symbol: str, timeframe: str = "1h",
        limit: int = 100, now: datetime | None = None,
    ) -> PaperCycleReport:
        """Collect once and process every newly completed candle in order."""
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        now = now.astimezone(timezone.utc)
        self.collector.collect_once(
            market=market, symbol=symbol, timeframe=timeframe, limit=limit
        )
        candles = self.candle_store.get(
            market, symbol, timeframe, limit=self.history_limit
        )
        duration = candle_duration(timeframe)
        completed = [
            candle for candle in candles
            if candle.timestamp.astimezone(timezone.utc) + duration <= now
        ]
        cursor = self._cursor(market, symbol, timeframe)
        if cursor is None and completed and not self.process_existing_history:
            # Never turn a historical backfill into hundreds of accidental
            # paper trades on first launch. Start from the newest closed bar.
            self._save_cursor(completed[-1])
            return PaperCycleReport(market, symbol, timeframe, 0, 0, 0, (), ())
        if cursor is not None and completed and cursor < completed[0].timestamp:
            raise RuntimeError(
                "engine cursor is older than retained candle history; "
                "restore missing candles or explicitly reset the engine state"
            )
        pending = [c for c in completed if cursor is None or c.timestamp > cursor]
        all_candidates: list[CandidateResult] = []
        all_exits: list[ExitEvent] = []
        signals_count = 0
        entries_count = 0

        for candle in pending:
            history = [item for item in completed if item.timestamp < candle.timestamp]
            signals = self.strategies.generate(history) if len(history) >= 2 else []
            signals_count += len(signals)

            # One position per symbol: avoid stacking correlated baseline signals.
            already_open = any(
                position.symbol == symbol for position in self.portfolio.open_positions()
            )
            if signals and not already_open:
                # A single strongest candidate prevents the three baselines from
                # opening duplicate positions on the same market candle.
                selected = max(signals, key=lambda signal: signal.confidence)
                selected = replace(selected, created_at=candle.timestamp)
                marks = self._marks(market, symbol, timeframe, candle, at_open=True)
                snapshot = self.portfolio.risk_snapshot(marks, at=candle.timestamp)
                results = self.coordinator.process(
                    [selected], {symbol: candle.open}, snapshot
                )
                all_candidates.extend(results)
                entries_count += sum(
                    result.approved and result.execution is not None
                    for result in results
                )

            costs = self.coordinator.executor.costs
            all_exits.extend(self.portfolio.process_candle_exits(
                symbol, candle.open, candle.high, candle.low, candle.close,
                at=candle.timestamp, fee_bps=costs.fee_bps,
                spread_bps=costs.spread_bps, slippage_bps=costs.slippage_bps,
            ))
            marks = self._marks(market, symbol, timeframe, candle, at_open=False)
            self.portfolio.state(marks, at=candle.timestamp)
            self._save_cursor(candle)

        return PaperCycleReport(
            market, symbol, timeframe, len(pending), signals_count,
            entries_count, tuple(all_exits), tuple(all_candidates),
        )

    def run_once(self, subscriptions: Sequence[dict],
                 now: datetime | None = None) -> list[PaperCycleReport]:
        if not subscriptions:
            raise ValueError("at least one market subscription is required")
        reports = []
        for subscription in subscriptions:
            reports.append(self.process_subscription(**subscription, now=now))
        return reports

    def run_forever(self, subscriptions: Sequence[dict], interval_seconds: int = 60,
                    stop_event: threading.Event | None = None) -> None:
        if interval_seconds < 1:
            raise ValueError("interval_seconds must be at least 1")
        if not subscriptions:
            raise ValueError("at least one market subscription is required")
        stop = stop_event or threading.Event()
        logger.info("Paper trading engine started with %d subscriptions", len(subscriptions))
        while not stop.is_set():
            for subscription in subscriptions:
                if stop.is_set():
                    break
                try:
                    report = self.process_subscription(**subscription)
                    logger.info(
                        "%s %s %s: candles=%d signals=%d entries=%d exits=%d",
                        report.market, report.symbol, report.timeframe,
                        report.candles_processed, report.signals_generated,
                        report.entries_filled, len(report.exits),
                    )
                except Exception:
                    logger.exception("Paper engine cycle failed for %s", subscription)
            stop.wait(interval_seconds)

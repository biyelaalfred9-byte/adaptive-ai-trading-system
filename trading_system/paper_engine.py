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
    oanda_prefix = re.fullmatch(r"([SMHDW])(\d+)", value)
    if oanda_prefix:
        value = oanda_prefix.group(2) + oanda_prefix.group(1)
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
    skipped_existing_position: bool = False
    candles_stored: int = 0
    candles_available: int = 0
    candles_completed: int = 0
    latest_candle_at: datetime | None = None
    latest_completed_at: datetime | None = None
    cursor_at: datetime | None = None
    cursor_seeded: bool = False


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
        max_holding_period_hours: float = 12.0,
    ) -> None:
        if history_limit < 50:
            raise ValueError("history_limit must be at least 50 candles")
        if max_holding_period_hours <= 0:
            raise ValueError("max_holding_period_hours must be positive")
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
        self.max_holding_period = timedelta(hours=max_holding_period_hours)
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
        _deferred_entries: list | None = None,
    ) -> PaperCycleReport:
        """Collect once and process every newly completed candle in order."""
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        now = now.astimezone(timezone.utc)
        stored_count = self.collector.collect_once(
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
        latest_candle = candles[-1].timestamp if candles else None
        latest_completed = completed[-1].timestamp if completed else None
        cursor_seeded = False
        if cursor is None and completed and not self.process_existing_history:
            # Never turn a historical backfill into hundreds of accidental
            # paper trades on first launch. Start from the newest closed bar.
            self._save_cursor(completed[-1])
            cursor = completed[-1].timestamp
            cursor_seeded = True
            logger.info(
                "PAPER ENGINE INITIALIZED %s %s %s: stored=%d available=%d "
                "completed=%d latest=%s cursor_seeded_at=%s; historical bars skipped",
                market, symbol, timeframe, stored_count, len(candles), len(completed),
                latest_candle, cursor,
            )
            return PaperCycleReport(
                market=market, symbol=symbol, timeframe=timeframe,
                candles_processed=0, signals_generated=0, entries_filled=0,
                exits=(), candidates=(), candles_stored=stored_count,
                candles_available=len(candles), candles_completed=len(completed),
                latest_candle_at=latest_candle, latest_completed_at=latest_completed,
                cursor_at=cursor, cursor_seeded=cursor_seeded,
            )
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
        skipped_existing_position = False

        for candle in pending:
            history = [item for item in completed if item.timestamp < candle.timestamp]
            signals = self.strategies.generate(history) if len(history) >= 2 else []
            signals_count += len(signals)

            # Queue entries when run_once is coordinating several markets.
            # This lets every market process its exits before any market takes
            # a newly freed portfolio slot.
            if signals and _deferred_entries is not None:
                marks = self._marks(market, symbol, timeframe, candle, at_open=True)
                _deferred_entries.append({
                    "market": market, "symbol": symbol, "candle": candle,
                    "signals": signals, "marks": marks,
                })
            elif signals:
                already_open = any(
                    position.symbol == symbol for position in self.portfolio.open_positions()
                )
                if already_open:
                    skipped_existing_position = True
                else:
                    marks = self._marks(market, symbol, timeframe, candle, at_open=True)
                    snapshot = self.portfolio.risk_snapshot(marks, at=candle.timestamp)
                    for candidate in sorted(signals, key=lambda item: item.confidence, reverse=True):
                        selected = replace(candidate, created_at=candle.timestamp)
                        results = self.coordinator.process(
                            [selected], {symbol: candle.open}, snapshot
                        )
                        all_candidates.extend(results)
                        if results and results[0].approved and results[0].execution is not None:
                            entries_count += 1
                            break

            costs = self.coordinator.executor.costs
            all_exits.extend(self.portfolio.process_candle_exits(
                symbol, candle.open, candle.high, candle.low, candle.close,
                at=candle.timestamp, fee_bps=costs.fee_bps,
                spread_bps=costs.spread_bps, slippage_bps=costs.slippage_bps,
                max_holding_period=self.max_holding_period,
            ))
            marks = self._marks(market, symbol, timeframe, candle, at_open=False)
            self.portfolio.state(marks, at=candle.timestamp)
            self._save_cursor(candle)

        final_cursor = self._cursor(market, symbol, timeframe)
        report = PaperCycleReport(
            market=market, symbol=symbol, timeframe=timeframe,
            candles_processed=len(pending), signals_generated=signals_count,
            entries_filled=entries_count, exits=tuple(all_exits),
            candidates=tuple(all_candidates),
            skipped_existing_position=skipped_existing_position,
            candles_stored=stored_count, candles_available=len(candles),
            candles_completed=len(completed), latest_candle_at=latest_candle,
            latest_completed_at=latest_completed, cursor_at=final_cursor,
        )
        logger.info(
            "PAPER ENGINE DATA %s %s %s: stored=%d available=%d completed=%d "
            "pending_processed=%d latest=%s latest_completed=%s cursor=%s",
            market, symbol, timeframe, report.candles_stored,
            report.candles_available, report.candles_completed,
            report.candles_processed, report.latest_candle_at,
            report.latest_completed_at, report.cursor_at,
        )
        return report

    def run_once(self, subscriptions: Sequence[dict],
                 now: datetime | None = None) -> list[PaperCycleReport]:
        """Process all market exits first, then allocate free slots globally."""
        if not subscriptions:
            raise ValueError("at least one market subscription is required")
        deferred: list[dict] = []
        reports = [
            self.process_subscription(
                **subscription, now=now, _deferred_entries=deferred
            )
            for subscription in subscriptions
        ]

        # Replay the candidate queue in candle-time order; within the same
        # candle, strongest confidence gets first access to the shared slots.
        deferred.sort(key=lambda item: (
            item["candle"].timestamp,
            -max(signal.confidence for signal in item["signals"]),
            item["symbol"],
        ))
        candidates_by_report: dict[int, list[CandidateResult]] = {}
        entries_by_report: dict[int, int] = {}
        skipped_by_report: dict[int, bool] = {}
        for item in deferred:
            symbol = item["symbol"]
            report_index = next(
                (i for i, report in enumerate(reports)
                 if report.market == item["market"] and report.symbol == symbol),
                None,
            )
            if report_index is None:
                continue
            if any(position.symbol == symbol for position in self.portfolio.open_positions()):
                skipped_by_report[report_index] = True
                continue

            candle = item["candle"]
            snapshot = self.portfolio.risk_snapshot(
                item["marks"], at=candle.timestamp
            )
            for candidate in sorted(
                item["signals"], key=lambda signal: signal.confidence, reverse=True
            ):
                selected = replace(candidate, created_at=candle.timestamp)
                results = self.coordinator.process(
                    [selected], {symbol: candle.open}, snapshot
                )
                candidates_by_report.setdefault(report_index, []).extend(results)
                if results and results[0].approved and results[0].execution is not None:
                    entries_by_report[report_index] = entries_by_report.get(report_index, 0) + 1
                    break

        for index, report in enumerate(reports):
            reports[index] = replace(
                report,
                entries_filled=report.entries_filled + entries_by_report.get(index, 0),
                candidates=report.candidates + tuple(candidates_by_report.get(index, [])),
                skipped_existing_position=(
                    report.skipped_existing_position or skipped_by_report.get(index, False)
                ),
            )
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
                        "%s %s %s: candles=%d signals=%d entries=%d exits=%d skipped_open_position=%s",
                        report.market, report.symbol, report.timeframe,
                        report.candles_processed, report.signals_generated,
                        report.entries_filled, len(report.exits),
                        report.skipped_existing_position,
                    )
                    for candidate in report.candidates:
                        logger.info(
                            "PAPER CANDIDATE %s %s confidence=%.3f approved=%s reason=%s | %s",
                            candidate.signal.symbol, candidate.signal.side.value,
                            candidate.signal.confidence, candidate.approved,
                            candidate.reason, candidate.signal.rationale,
                        )
                    for event in report.exits:
                        logger.info(
                            "PAPER EXIT %s reason=%s price=%.8f realized_pnl=%.4f",
                            event.symbol, event.reason, event.exit_price, event.realized_pnl,
                        )
                except Exception:
                    logger.exception("Paper engine cycle failed for %s", subscription)
            stop.wait(interval_seconds)

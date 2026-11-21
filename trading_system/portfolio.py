"""Persistent paper portfolio ledger: positions, equity and risk snapshots."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from uuid import uuid4

from .domain import ExecutionResult, OrderRequest, Side
from .risk import RiskSnapshot


@dataclass(frozen=True)
class Position:
    position_id: str
    symbol: str
    side: Side
    quantity: float
    entry_price: float
    entry_fee: float
    opened_at: datetime


@dataclass(frozen=True)
class PortfolioState:
    starting_equity: float
    realized_pnl: float
    unrealized_pnl: float
    equity: float
    daily_pnl: float
    peak_equity: float
    current_drawdown: float
    open_positions: int


class PaperPortfolio:
    """SQLite-backed ledger for simulated positions only.

    Entry/exit spread and slippage are reflected in execution average prices;
    fees are deducted separately. Funding, borrow, swap and taxes are not modeled.
    """

    def __init__(self, path: str = "paper_portfolio.sqlite3", starting_equity: float = 1000.0):
        if not isfinite(starting_equity) or starting_equity <= 0:
            raise ValueError("starting_equity must be positive and finite")
        self.path = str(Path(path))
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS portfolio_meta (
                key TEXT PRIMARY KEY, value REAL NOT NULL
            )""")
            db.execute("INSERT OR IGNORE INTO portfolio_meta(key,value) VALUES('starting_equity',?)",
                       (starting_equity,))
            db.execute("INSERT OR IGNORE INTO portfolio_meta(key,value) VALUES('peak_equity',?)",
                       (starting_equity,))
            db.execute("""CREATE TABLE IF NOT EXISTS positions (
                position_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL,
                quantity REAL NOT NULL, entry_price REAL NOT NULL, entry_fee REAL NOT NULL,
                opened_at TEXT NOT NULL, status TEXT NOT NULL, exit_price REAL,
                exit_fee REAL, closed_at TEXT, realized_pnl REAL
            )""")
            db.execute("""CREATE INDEX IF NOT EXISTS idx_positions_status
                          ON positions(status, opened_at)""")

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _utc(value: datetime | None = None) -> datetime:
        value = value or datetime.now(timezone.utc)
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    def open_position(self, order: OrderRequest, execution: ExecutionResult,
                      opened_at: datetime | None = None) -> Position:
        if not execution.simulated:
            raise ValueError("portfolio accepts simulated fills only")
        if execution.status != "filled" or execution.filled_quantity <= 0:
            raise ValueError("a positive filled paper execution is required")
        if execution.filled_quantity > order.quantity + 1e-12:
            raise ValueError("filled quantity cannot exceed requested quantity")
        if not isfinite(execution.average_price) or execution.average_price <= 0:
            raise ValueError("execution average price must be positive and finite")
        if not isfinite(execution.fee_paid) or execution.fee_paid < 0:
            raise ValueError("execution fee must be finite and non-negative")
        timestamp = self._utc(opened_at)
        position = Position(str(uuid4()), order.symbol, order.side,
                            execution.filled_quantity, execution.average_price,
                            execution.fee_paid, timestamp)
        with self._connect() as db:
            db.execute("""INSERT INTO positions
                (position_id,symbol,side,quantity,entry_price,entry_fee,opened_at,status)
                VALUES(?,?,?,?,?,?,?,'open')""",
                (position.position_id, position.symbol, position.side.value,
                 position.quantity, position.entry_price, position.entry_fee,
                 timestamp.isoformat()))
        return position

    def close_position(self, position_id: str, exit_price: float,
                       exit_fee: float = 0.0,
                       closed_at: datetime | None = None) -> float:
        if not isfinite(exit_price) or exit_price <= 0:
            raise ValueError("exit_price must be positive and finite")
        if not isfinite(exit_fee) or exit_fee < 0:
            raise ValueError("exit_fee must be finite and non-negative")
        timestamp = self._utc(closed_at)
        with self._connect() as db:
            row = db.execute("SELECT * FROM positions WHERE position_id=? AND status='open'",
                             (position_id,)).fetchone()
            if row is None:
                raise ValueError("open position not found")
            direction = 1.0 if row["side"] == Side.BUY.value else -1.0
            pnl = ((exit_price - row["entry_price"]) * row["quantity"] * direction
                   - row["entry_fee"] - exit_fee)
            db.execute("""UPDATE positions SET status='closed',exit_price=?,exit_fee=?,
                closed_at=?,realized_pnl=? WHERE position_id=?""",
                (exit_price, exit_fee, timestamp.isoformat(), pnl, position_id))
        return pnl

    def state(self, marks: dict[str, float] | None = None,
              at: datetime | None = None) -> PortfolioState:
        marks = marks or {}
        timestamp = self._utc(at)
        with self._connect() as db:
            starting = float(db.execute(
                "SELECT value FROM portfolio_meta WHERE key='starting_equity'").fetchone()[0])
            peak = float(db.execute(
                "SELECT value FROM portfolio_meta WHERE key='peak_equity'").fetchone()[0])
            closed = db.execute(
                "SELECT COALESCE(SUM(realized_pnl),0) FROM positions WHERE status='closed'"
            ).fetchone()[0]
            daily = db.execute("""SELECT COALESCE(SUM(realized_pnl),0) FROM positions
                WHERE status='closed' AND closed_at>=?""",
                (timestamp.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),)
            ).fetchone()[0]
            open_rows = db.execute("SELECT * FROM positions WHERE status='open'").fetchall()

        unrealized = 0.0
        for row in open_rows:
            mark = marks.get(row["symbol"])
            if mark is None:
                continue
            if not isfinite(mark) or mark <= 0:
                raise ValueError(f"invalid mark price for {row['symbol']}")
            direction = 1.0 if row["side"] == Side.BUY.value else -1.0
            unrealized += ((mark - row["entry_price"]) * row["quantity"] * direction
                           - row["entry_fee"])

        realized = float(closed)
        equity = starting + realized + unrealized
        peak = max(peak, equity)
        with self._connect() as db:
            db.execute("UPDATE portfolio_meta SET value=? WHERE key='peak_equity'", (peak,))
        drawdown = max(0.0, (peak - equity) / peak) if peak > 0 else 1.0
        # Conservative daily stop input: realized PnL closed today plus the full
        # mark-to-market PnL (including entry fees) on every currently open trade.
        daily_pnl = float(daily) + unrealized
        return PortfolioState(starting, realized, unrealized, equity, daily_pnl,
                              peak, drawdown, len(open_rows))

    def risk_snapshot(self, marks: dict[str, float] | None = None,
                      at: datetime | None = None) -> RiskSnapshot:
        state = self.state(marks, at)
        return RiskSnapshot(state.equity, state.daily_pnl,
                            state.current_drawdown, state.open_positions)

    def open_positions(self) -> list[Position]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM positions WHERE status='open' ORDER BY opened_at").fetchall()
        return [Position(row["position_id"], row["symbol"], Side(row["side"]),
                         row["quantity"], row["entry_price"], row["entry_fee"],
                         datetime.fromisoformat(row["opened_at"])) for row in rows]

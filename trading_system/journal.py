import sqlite3
from pathlib import Path

from .domain import ExecutionResult, OrderRequest


class TradeJournal:
    def __init__(self, path: str = "trading_journal.sqlite3"):
        self.path = str(Path(path))
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    reference_price REAL NOT NULL,
                    filled_quantity REAL NOT NULL,
                    average_price REAL NOT NULL,
                    status TEXT NOT NULL,
                    simulated INTEGER NOT NULL,
                    fee_paid REAL NOT NULL DEFAULT 0,
                    spread_cost REAL NOT NULL DEFAULT 0,
                    slippage_cost REAL NOT NULL DEFAULT 0
                )
            """)
            # Migrate databases created by the earlier nine-column schema.
            columns = {row[1] for row in db.execute("PRAGMA table_info(paper_trades)")}
            for name in ("fee_paid", "spread_cost", "slippage_cost"):
                if name not in columns:
                    db.execute(f"ALTER TABLE paper_trades ADD COLUMN {name} REAL NOT NULL DEFAULT 0")

    def _connect(self):
        return sqlite3.connect(self.path)

    def record(self, order: OrderRequest, result: ExecutionResult) -> None:
        if not result.simulated:
            raise ValueError("initial journal accepts paper fills only")
        with self._connect() as db:
            db.execute("""
                INSERT INTO paper_trades (
                    order_id, symbol, side, quantity, reference_price,
                    filled_quantity, average_price, status, simulated,
                    fee_paid, spread_cost, slippage_cost
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.order_id, order.symbol, order.side.value, order.quantity,
                order.reference_price, result.filled_quantity, result.average_price,
                result.status, 1, result.fee_paid, result.spread_cost,
                result.slippage_cost
            ))

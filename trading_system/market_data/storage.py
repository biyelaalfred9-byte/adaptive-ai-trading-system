import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Candle


class CandleStore:
    """SQLite OHLCV store. Repeated writes replace the same market candle."""

    def __init__(self, path: str = "market_data.sqlite3"):
        self.path = str(Path(path))
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    market TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    PRIMARY KEY (market, symbol, timeframe, timestamp)
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_candles_lookup
                ON candles(market, symbol, timeframe, timestamp)
            """)

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def upsert(self, candles: list[Candle]) -> int:
        if not candles:
            return 0
        rows = [
            (c.market, c.symbol, c.timeframe, c.timestamp.astimezone(timezone.utc).isoformat(),
             c.open, c.high, c.low, c.close, c.volume)
            for c in candles
        ]
        with self._connect() as db:
            db.executemany("""
                INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(market, symbol, timeframe, timestamp) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume
            """, rows)
        return len(rows)

    def get(self, market: str, symbol: str, timeframe: str,
            limit: int = 500) -> list[Candle]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        with self._connect() as db:
            rows = db.execute("""
                SELECT market, symbol, timeframe, timestamp, open, high, low, close, volume
                FROM candles WHERE market=? AND symbol=? AND timeframe=?
                ORDER BY timestamp DESC LIMIT ?
            """, (market, symbol, timeframe, limit)).fetchall()
        rows.reverse()
        return [
            Candle(m, s, tf, datetime.fromisoformat(ts), o, h, low, c, v)
            for m, s, tf, ts, o, h, low, c, v in rows
        ]

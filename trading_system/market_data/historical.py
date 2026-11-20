"""Bounded, paginated historical OHLCV backfills for research datasets."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Protocol

from .models import Candle
from .storage import CandleStore


class HistoricalProvider(Protocol):
    def fetch_candles_since(self, symbol: str, timeframe: str,
                            since: datetime | None, limit: int = 100) -> list[Candle]:
        """Return ascending candles beginning at since, or latest if None."""


def timeframe_duration(timeframe: str) -> timedelta:
    """Convert CCXT (1h) or OANDA (H1) timeframe notation to a duration."""
    value = timeframe.strip()
    match = re.fullmatch(r"([1-9][0-9]*)([mhdwMHDW])", value)
    if not match:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    amount, unit = int(match.group(1)), match.group(2).lower()
    seconds = {"m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
    return timedelta(seconds=amount * seconds)


class HistoricalDataBackfiller:
    """Download completed candles over [start, end) and persist them in SQLite."""

    def __init__(self, provider: HistoricalProvider, store: CandleStore):
        self.provider = provider
        self.store = store

    def backfill(self, *, market: str, symbol: str, timeframe: str,
                 start: datetime, end: datetime, page_limit: int = 500,
                 max_pages: int = 1000) -> int:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        if start >= end:
            raise ValueError("start must be earlier than end")
        if page_limit < 1 or max_pages < 1:
            raise ValueError("page_limit and max_pages must be positive")
        interval = timeframe_duration(timeframe)
        cursor = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)
        persisted = 0

        for _ in range(max_pages):
            page = self.provider.fetch_candles_since(
                symbol, timeframe, cursor, page_limit
            )
            if not page:
                return persisted
            page = sorted(page, key=lambda candle: candle.timestamp)
            if any(page[i].timestamp >= page[i + 1].timestamp
                   for i in range(len(page) - 1)):
                raise ValueError("provider returned duplicate candle timestamps")
            eligible = [
                candle for candle in page
                if candle.timestamp >= cursor
                and candle.timestamp + interval <= end_utc
            ]
            if eligible:
                if any(c.market != market or c.symbol != symbol or c.timeframe != timeframe
                       for c in eligible):
                    raise ValueError("provider returned candles for a different series")
                persisted += self.store.upsert(eligible)

            last_timestamp = page[-1].timestamp.astimezone(timezone.utc)
            next_cursor = last_timestamp + interval
            if next_cursor <= cursor:
                raise ValueError("provider pagination did not advance")
            if last_timestamp + interval >= end_utc:
                return persisted
            cursor = next_cursor
            if len(page) < page_limit:
                return persisted

        raise RuntimeError(
            f"historical backfill reached max_pages={max_pages}; "
            "increase the limit to continue"
        )

"""Config-driven historical market-data backfill CLI.

Downloads read-only candles and persists them in SQLite; never places orders.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_system.market_data.historical import HistoricalDataBackfiller
from trading_system.market_data.storage import CandleStore


@dataclass(frozen=True)
class BackfillJob:
    market: str
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    page_limit: int = 500
    max_pages: int = 1000
    exchange: str = "binance"

    def __post_init__(self) -> None:
        if self.market not in {"crypto", "forex"}:
            raise ValueError("market must be 'crypto' or 'forex'")
        if not all((self.symbol, self.timeframe)):
            raise ValueError("symbol and timeframe are required")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("start and end must include a timezone")
        if self.start >= self.end:
            raise ValueError("start must be earlier than end")
        if self.page_limit < 1 or self.max_pages < 1:
            raise ValueError("page_limit and max_pages must be positive")
        if self.market == "crypto" and self.page_limit > 1000:
            raise ValueError("crypto page_limit cannot exceed 1000")
        if self.market == "forex" and self.page_limit > 5000:
            raise ValueError("forex page_limit cannot exceed 5000")


def _parse_datetime(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("start and end must be ISO-8601 datetime strings")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 datetime: {value}") from exc
    if parsed.tzinfo is None:
        raise ValueError("start and end must include a timezone")
    return parsed.astimezone(timezone.utc)


def load_config(path: str | Path) -> tuple[str, list[BackfillJob]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    database = payload.get("database", "market_data.sqlite3")
    if not isinstance(database, str) or not database.strip():
        raise ValueError("database must be a non-empty path")
    jobs = []
    for item in payload.get("jobs", []):
        values = dict(item)
        values["start"] = _parse_datetime(values["start"])
        values["end"] = _parse_datetime(values["end"])
        jobs.append(BackfillJob(**values))
    if not jobs:
        raise ValueError("config must contain at least one job")
    return database, jobs


def _provider_for(job: BackfillJob):
    if job.market == "crypto":
        from trading_system.market_data.crypto_ccxt import CCXTMarketData
        return CCXTMarketData(exchange_id=job.exchange)
    from trading_system.market_data.forex_oanda import OandaPracticeMarketData
    return OandaPracticeMarketData()


class HistoricalBackfillRunner:
    """Run independent bounded backfill jobs and return a JSON-safe report."""

    def __init__(self, store: CandleStore, provider_factory: Any = _provider_for):
        self.store = store
        self.provider_factory = provider_factory

    def run(self, jobs: list[BackfillJob]) -> dict[str, Any]:
        if not jobs:
            raise ValueError("at least one backfill job is required")
        results = []
        for job in jobs:
            entry = {
                "market": job.market,
                "symbol": job.symbol,
                "timeframe": job.timeframe,
                "start": job.start.astimezone(timezone.utc).isoformat(),
                "end": job.end.astimezone(timezone.utc).isoformat(),
            }
            try:
                provider = self.provider_factory(job)
                count = HistoricalDataBackfiller(provider, self.store).backfill(
                    market=job.market,
                    symbol=job.symbol,
                    timeframe=job.timeframe,
                    start=job.start,
                    end=job.end,
                    page_limit=job.page_limit,
                    max_pages=job.max_pages,
                )
                entry.update(status="completed", candles_upserted=count)
            except Exception as exc:
                entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            results.append(entry)
        return {
            "report_version": 1,
            "mode": "historical_data_ingestion",
            "live_trading_enabled": False,
            "jobs": results,
            "summary": {
                "jobs_total": len(results),
                "jobs_completed": sum(r["status"] == "completed" for r in results),
                "jobs_failed": sum(r["status"] == "failed" for r in results),
                "candles_upserted": sum(r.get("candles_upserted", 0) for r in results),
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill read-only historical candles into SQLite."
    )
    parser.add_argument("config", help="Path to backfill JSON configuration")
    parser.add_argument("--output", default="backfill_report.json",
                        help="Output JSON report path")
    args = parser.parse_args()

    database, jobs = load_config(args.config)
    report = HistoricalBackfillRunner(CandleStore(database)).run(jobs)
    Path(args.output).write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(f"Backfill report written to {args.output}")
    print(json.dumps(report["summary"], indent=2))
    if report["summary"]["jobs_failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

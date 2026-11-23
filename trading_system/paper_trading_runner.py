"""Continuous paper-trading CLI. Market data is read-only; orders are simulated."""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

from trading_system.execution.coordinator import PaperTradingCoordinator
from trading_system.execution.paper import PaperCostModel, PaperExecutor
from trading_system.journal import TradeJournal
from trading_system.market_data.collector import MarketDataCollector
from trading_system.market_data.service import MarketDataService
from trading_system.market_data.storage import CandleStore
from trading_system.paper_engine import PaperTradingEngine
from trading_system.portfolio import PaperPortfolio


def load_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    subscriptions = config.get("subscriptions")
    if not isinstance(subscriptions, list) or not subscriptions:
        raise ValueError("config must contain a non-empty subscriptions list")
    for item in subscriptions:
        if item.get("market") not in {"crypto", "forex"}:
            raise ValueError("subscription market must be crypto or forex")
        if not item.get("symbol") or not item.get("timeframe"):
            raise ValueError("each subscription needs symbol and timeframe")
        item.setdefault("limit", 100)
    interval = int(config.get("interval_seconds", 60))
    if interval < 1:
        raise ValueError("interval_seconds must be positive")
    return config


def build_engine(config: dict[str, Any]) -> PaperTradingEngine:
    needs_crypto = any(item["market"] == "crypto" for item in config["subscriptions"])
    needs_forex = any(item["market"] == "forex" for item in config["subscriptions"])
    crypto = None
    forex = None
    if needs_crypto:
        from trading_system.market_data.crypto_ccxt import CCXTMarketData
        crypto = CCXTMarketData(exchange_id=config.get("crypto_exchange", "binance"))
    if needs_forex:
        from trading_system.market_data.forex_oanda import OandaPracticeMarketData
        forex = OandaPracticeMarketData(token=os.getenv("OANDA_API_TOKEN"))
    service = MarketDataService(crypto=crypto, forex=forex)
    candle_store = CandleStore(config.get("market_database", "market_data.sqlite3"))
    portfolio = PaperPortfolio(
        config.get("portfolio_database", "paper_portfolio.sqlite3"),
        starting_equity=float(config.get("starting_equity", 1000.0)),
    )
    journal = TradeJournal(config.get("journal_database", "trading_journal.sqlite3"))
    costs = PaperCostModel(
        spread_bps=float(config.get("spread_bps", 2.0)),
        slippage_bps=float(config.get("slippage_bps", 1.0)),
        fee_bps=float(config.get("fee_bps", 10.0)),
    )
    executor = PaperExecutor(costs)
    coordinator = PaperTradingCoordinator(executor, journal=journal, portfolio=portfolio)
    collector = MarketDataCollector(service, candle_store)
    return PaperTradingEngine(
        collector, candle_store, portfolio, coordinator,
        state_path=config.get("engine_state_database", "paper_engine_state.sqlite3"),
        history_limit=int(config.get("history_limit", 500)),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the read-only market-data and simulated paper-trading engine."
    )
    parser.add_argument("config", help="Path to paper trading JSON configuration")
    parser.add_argument("--once", action="store_true",
                        help="Collect and process one cycle, then exit")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config(args.config)
    engine = build_engine(config)
    if args.once:
        reports = engine.run_once(config["subscriptions"])
        for report in reports:
            logging.info(
                "%s %s %s candles=%d signals=%d entries=%d exits=%d skipped_open_position=%s",
                report.market, report.symbol, report.timeframe,
                report.candles_processed, report.signals_generated,
                report.entries_filled, len(report.exits), report.skipped_existing_position,
            )
            for candidate in report.candidates:
                logging.info(
                    "PAPER CANDIDATE %s %s confidence=%.3f approved=%s reason=%s | %s",
                    candidate.signal.symbol, candidate.signal.side.value,
                    candidate.signal.confidence, candidate.approved,
                    candidate.reason, candidate.signal.rationale,
                )
            for event in report.exits:
                logging.info(
                    "PAPER EXIT %s reason=%s price=%.8f realized_pnl=%.4f",
                    event.symbol, event.reason, event.exit_price, event.realized_pnl,
                )
        return
    logging.info("Starting paper-only engine. Press Ctrl+C to stop.")
    try:
        engine.run_forever(
            config["subscriptions"],
            interval_seconds=int(config.get("interval_seconds", 60)),
        )
    except KeyboardInterrupt:
        logging.info("Paper trading engine stopped by user.")


if __name__ == "__main__":
    main()

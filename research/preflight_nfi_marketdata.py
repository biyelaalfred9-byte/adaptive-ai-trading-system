#!/usr/bin/env python3
"""Verify CCXT can load authoritative Binance spot market metadata without api.binance.com."""
from __future__ import annotations

import asyncio
import ccxt.pro as ccxt

PUBLIC_API = "https://data-api.binance.vision/api/v3"
REQUIRED_PAIRS = ("BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT")


async def main() -> None:
    exchange = ccxt.binance(
        {
            "enableRateLimit": True,
            "urls": {"api": {"public": PUBLIC_API}},
            "options": {"fetchCurrencies": False, "fetchMarkets": {"types": ["spot"]}},
        }
    )
    try:
        markets = await exchange.load_markets()
        missing = [pair for pair in REQUIRED_PAIRS if pair not in markets]
        if missing:
            raise RuntimeError(f"Required Binance spot markets missing: {missing}")

        for pair in REQUIRED_PAIRS:
            market = markets[pair]
            if market.get("spot") is not True or market.get("quote") != "USDT":
                raise RuntimeError(f"Unexpected market type for {pair}: {market}")
            if market.get("active") is not True:
                raise RuntimeError(f"Market is not active: {pair}")
            if not market.get("precision") or not market.get("limits"):
                raise RuntimeError(f"Incomplete precision/limits metadata for {pair}")
            print(
                "{}: active={}, precision={}, limits={}".format(
                    pair,
                    market.get("active"),
                    market.get("precision"),
                    market.get("limits"),
                )
            )

        print(
            "PASS: CCXT loaded {} markets from Binance's official "
            "market-data-only endpoint.".format(len(markets))
        )
    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(main())

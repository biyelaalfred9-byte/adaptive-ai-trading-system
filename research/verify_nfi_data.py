#!/usr/bin/env python3
"""Verify all twelve 5m and 1h datasets cover the requested 2023-2025 period."""
from pathlib import Path
import pandas as pd

PAIRS = "BTC_USDT ETH_USDT BNB_USDT SOL_USDT XRP_USDT ADA_USDT DOGE_USDT LINK_USDT LTC_USDT AVAX_USDT DOT_USDT TRX_USDT".split()
root = Path("user_data/data/binance")
cutoff = pd.Timestamp("2025-12-30", tz="UTC")
for timeframe in ("5m", "1h"):
    files = sorted(root.glob(f"*-{timeframe}.feather"))
    expected = {f"{pair}-{timeframe}.feather" for pair in PAIRS}
    actual = {path.name for path in files}
    if actual != expected:
        raise SystemExit(f"{timeframe}: expected {len(expected)} files; missing={sorted(expected-actual)}; unexpected={sorted(actual-expected)}")
    for path in files:
        frame = pd.read_feather(path, columns=["date"])
        dates = pd.to_datetime(frame["date"], utc=True)
        first, last = dates.min(), dates.max()
        print(f"{path.name}: {len(frame):,} candles; {first} -> {last}", flush=True)
        if first > pd.Timestamp("2023-01-02", tz="UTC") or last < cutoff:
            raise SystemExit(f"{path.name} does not cover the full required 2023-2025 period")
print("PASS: all 24 datasets cover the required period and timestamps are normalized.", flush=True)

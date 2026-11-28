#!/usr/bin/env python3
"""Verify all four five-minute Feather datasets reach the requested end date."""
from pathlib import Path
import pandas as pd

root = Path("user_data/data/binance")
files = sorted(root.glob("*-5m.feather"))
if len(files) != 4:
    raise SystemExit(f"Expected 4 five-minute files, found {len(files)}")
cutoff = pd.Timestamp("2025-12-30", tz="UTC")
for path in files:
    frame = pd.read_feather(path, columns=["date"])
    last = pd.to_datetime(frame["date"], utc=True).max()
    print(f"{path.name}: {len(frame):,} candles; {frame['date'].min()} -> {last}", flush=True)
    if last < cutoff:
        raise SystemExit(f"{path.name} ends before {cutoff}")
print("PASS: all four five-minute datasets reach the required coverage.", flush=True)

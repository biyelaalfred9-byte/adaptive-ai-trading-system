#!/usr/bin/env python3
"""Download public Binance Vision spot klines concurrently and write Freqtrade Feather files.

No API keys, exchange endpoints, or order endpoints are used.
"""
from __future__ import annotations

import csv
import io
import os
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

PAIRS = os.getenv("PAIRS", "BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT").split(",")
TIMEFRAMES = ("5m", "1h")
START_YEAR, START_MONTH = 2023, 1
END_YEAR, END_MONTH = 2026, 1  # exclusive
WORKERS = int(os.getenv("DOWNLOAD_WORKERS", "8"))
OUT = Path("user_data/data/binance")
CACHE = Path(".cache/binance-vision")


def months():
    y, m = START_YEAR, START_MONTH
    while (y, m) < (END_YEAR, END_MONTH):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def download(args):
    symbol, timeframe, year, month = args
    name = f"{symbol}-{timeframe}-{year}-{month:02d}.zip"
    url = f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/{timeframe}/{name}"
    path = CACHE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                payload = response.read()
            temporary = path.with_suffix(".zip.tmp")
            temporary.write_bytes(payload)
            temporary.replace(path)
        except Exception as exc:
            if "404" in str(exc):
                return []
            raise
    with zipfile.ZipFile(path) as zf:
        with zf.open(zf.namelist()[0]) as raw:
            rows = csv.reader(io.TextIOWrapper(raw, encoding="utf-8"))
            return [
                (int(row[0]), *map(float, row[1:6]))
                for row in rows
                if row and row[0].isdigit()
            ]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [
        (pair.replace("/", ""), tf, year, month)
        for pair in PAIRS
        for tf in TIMEFRAMES
        for year, month in months()
    ]
    print(f"Fetching {len(jobs)} monthly archives with {WORKERS} workers (cache: {CACHE}).")
    # Process one pair/timeframe at a time to bound memory, but download its months concurrently.
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for pair in PAIRS:
            symbol = pair.replace("/", "")
            for tf in TIMEFRAMES:
                tasks = [(symbol, tf, year, month) for year, month in months()]
                by_ts = {}
                for monthly_rows in pool.map(download, tasks):
                    for row in monthly_rows:
                        by_ts[row[0]] = row
                if not by_ts:
                    raise RuntimeError(f"No Binance Vision data for {pair} {tf}")
                rows = [by_ts[k] for k in sorted(by_ts)]
                frame = pd.DataFrame(
                    rows,
                    columns=["date_ms", "open", "high", "low", "close", "volume"],
                )
                frame["date"] = pd.to_datetime(frame.pop("date_ms"), unit="ms", utc=True)
                frame = frame[["date", "open", "high", "low", "close", "volume"]]
                target = OUT / f"{pair.replace('/', '_')}-{tf}.feather"
                frame.to_feather(target)
                print(f"{pair} {tf}: {len(frame)} candles -> {target}", flush=True)


if __name__ == "__main__":
    main()

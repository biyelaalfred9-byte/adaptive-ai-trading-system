#!/usr/bin/env python3
"""Reproduce ReinforcedAverageStrategy without CCXT/Freqtrade market discovery.

Downloads Binance Vision public monthly spot klines, then runs a conservative,
close-signal/next-open backtest. No credentials and no order endpoints.
"""
from __future__ import annotations

import csv
import io
import json
import math
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PAIRS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]
START = (2023, 5)
END = (2025, 6)  # exclusive
FEE = 0.001
INITIAL = 1000.0
STAKE = 200.0
MAX_OPEN = 5
OUT = Path("research/results")
CACHE = Path("research/market-data")


def months():
    y, m = START
    while (y, m) < END:
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def download_month(symbol: str, year: int, month: int) -> list[list[float]]:
    name = f"{symbol}-4h-{year}-{month:02d}.zip"
    url = f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/4h/{name}"
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return []
            raise RuntimeError(f"Download failed {url}: HTTP {exc.code}") from exc
        path.write_bytes(payload)
    with zipfile.ZipFile(path) as archive:
        csv_name = archive.namelist()[0]
        rows = csv.reader(io.TextIOWrapper(archive.open(csv_name), encoding="utf-8"))
        output = []
        for row in rows:
            if not row or not row[0].isdigit():
                continue
            output.append([int(row[0]), *[float(x) for x in row[1:6]]])
        return output


def load_data(symbol):
    by_ts = {}
    for year, month in months():
        for row in download_month(symbol, year, month):
            by_ts[row[0]] = row
    data = [by_ts[k] for k in sorted(by_ts)]
    if len(data) < 500:
        raise RuntimeError(f"{symbol}: only {len(data)} candles downloaded")
    return data


def ema(values, period):
    alpha = 2.0 / (period + 1)
    result = [None] * len(values)
    if len(values) < period:
        return result
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * alpha + prev * (1 - alpha)
        result[i] = prev
    return result


def sma(values, period):
    result = [None] * len(values)
    running = 0.0
    for i, value in enumerate(values):
        running += value
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            result[i] = running / period
    return result


def indicators(data):
    close = [r[4] for r in data]
    fast, slow = ema(close, 8), ema(close, 21)
    # Original strategy resamples 4h bars to 48h and applies SMA(50).
    # Only expose a 48h SMA after that 48h candle has fully closed.
    buckets = defaultdict(list)
    for i, row in enumerate(data):
        bucket = row[0] // (48 * 60 * 60 * 1000)
        buckets[bucket].append(i)
    two_day = []
    for bucket in sorted(buckets):
        inds = buckets[bucket]
        if len(inds) == 12:
            two_day.append((data[inds[-1]][0] + 4 * 60 * 60 * 1000, close[inds[-1]]))
    two_day_sma = sma([x[1] for x in two_day], 50)
    trend_at = {}
    for j, (end_ts, _) in enumerate(two_day):
        if two_day_sma[j] is not None:
            trend_at[end_ts] = two_day_sma[j]
    trend = [None] * len(data)
    current = None
    k = 0
    completed = sorted(trend_at.items())
    for i, row in enumerate(data):
        candle_close_ts = row[0] + 4 * 60 * 60 * 1000
        while k < len(completed) and completed[k][0] <= candle_close_ts:
            current = completed[k][1]
            k += 1
        trend[i] = current
    return fast, slow, trend


def run():
    markets = {}
    for symbol in PAIRS:
        data = load_data(symbol)
        markets[symbol] = (data, indicators(data))
        print(f"DATA {symbol}: {len(data)} candles")

    events = []
    for symbol, (data, ind) in markets.items():
        for i, row in enumerate(data):
            events.append((row[0], symbol, i))
    events.sort()

    cash = INITIAL
    positions = {}
    trades = []
    equity_peak = INITIAL
    max_dd = 0.0
    equity_curve = []
    last_signal = {}

    for ts, symbol, i in events:
        data, (fast, slow, trend) = markets[symbol]
        if i == 0 or i + 1 >= len(data):
            continue
        row = data[i]
        next_open = data[i + 1][1]
        close = row[4]
        pos = positions.get(symbol)

        # Stop loss and ROI are checked against candle extremes; stop takes priority.
        if pos:
            exit_price = None
            reason = None
            if row[3] <= pos["entry"] * 0.80:
                exit_price, reason = pos["entry"] * 0.80, "stop_loss"
            elif row[2] >= pos["entry"] * 1.50:
                exit_price, reason = pos["entry"] * 1.50, "roi_50"
            elif fast[i] is not None and slow[i] is not None and fast[i-1] is not None and slow[i-1] is not None and slow[i] > fast[i] and slow[i-1] <= fast[i-1]:
                exit_price, reason = next_open, "ema_exit_next_open"
            if exit_price is not None:
                gross = STAKE * (exit_price / pos["entry"] - 1)
                fees = STAKE * FEE + (STAKE + gross) * FEE
                pnl = gross - fees
                cash += STAKE + pnl
                trades.append({"symbol": symbol, "opened": pos["opened"], "closed": ts,
                               "entry": pos["entry"], "exit": exit_price, "reason": reason,
                               "gross_pnl": gross, "fees": fees, "net_pnl": pnl})
                del positions[symbol]

        # Entry signal on candle close, fill at next candle open.
        if symbol not in positions and fast[i] is not None and slow[i] is not None and trend[i] is not None:
            crossed = fast[i-1] is not None and slow[i-1] is not None and fast[i] > slow[i] and fast[i-1] <= slow[i-1]
            if crossed and close > trend[i] and row[5] > 0 and len(positions) < MAX_OPEN and cash >= STAKE:
                positions[symbol] = {"entry": next_open, "opened": ts, "entry_fee": STAKE * FEE}
                cash -= STAKE
        marked = cash
        for sym, p in positions.items():
            current_close = markets[sym][0][i if sym == symbol else min(i, len(markets[sym][0])-1)][4] if sym == symbol else p["entry"]
            marked += STAKE * current_close / p["entry"]
        equity_peak = max(equity_peak, marked)
        if equity_peak:
            max_dd = max(max_dd, (equity_peak - marked) / equity_peak)
        equity_curve.append(marked)

    # Liquidate remaining positions at last available close, with fees.
    for symbol, pos in list(positions.items()):
        data = markets[symbol][0]
        exit_price = data[-1][4]
        gross = STAKE * (exit_price / pos["entry"] - 1)
        fees = STAKE * FEE + (STAKE + gross) * FEE
        pnl = gross - fees
        cash += STAKE + pnl
        trades.append({"symbol": symbol, "opened": pos["opened"], "closed": data[-1][0],
                       "entry": pos["entry"], "exit": exit_price, "reason": "end_of_test",
                       "gross_pnl": gross, "fees": fees, "net_pnl": pnl})
    net = sum(t["net_pnl"] for t in trades)
    wins = sum(t["net_pnl"] > 0 for t in trades)
    gross_profit = sum(t["net_pnl"] for t in trades if t["net_pnl"] > 0)
    gross_loss = -sum(t["net_pnl"] for t in trades if t["net_pnl"] < 0)
    pf = gross_profit / gross_loss if gross_loss else (math.inf if gross_profit else 0)
    report = {
        "strategy": "ReinforcedAverageStrategy (independent reproduction)",
        "period": "2023-05 through 2025-05",
        "markets": PAIRS, "timeframe": "4h", "trend_filter": "completed 48h SMA(50)",
        "initial_balance": INITIAL, "stake_per_trade": STAKE, "max_open_positions": MAX_OPEN,
        "fee_per_side": FEE, "trades": len(trades), "wins": wins,
        "win_rate_pct": round(100*wins/len(trades), 2) if trades else 0,
        "net_pnl_usdt": round(net, 4), "return_pct": round(100*net/INITIAL, 2),
        "profit_factor": round(pf, 4) if math.isfinite(pf) else "infinite",
        "max_drawdown_pct_approx": round(100*max_dd, 2),
        "trade_reasons": dict((r, sum(t["reason"] == r for t in trades)) for r in sorted({t["reason"] for t in trades})),
        "warning": "Independent reproduction; conservative next-open signals, simplified portfolio mark-to-market. Not a live result."
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "reinforced_average_report.json").write_text(json.dumps(report, indent=2) + "\n")
    with (OUT / "reinforced_average_trades.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(trades[0]) if trades else ["symbol"])
        writer.writeheader()
        writer.writerows(trades)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run()

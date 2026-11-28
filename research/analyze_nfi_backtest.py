#!/usr/bin/env python3
"""Extract and audit Freqtrade trade exports; fail if only metadata is present."""
from __future__ import annotations
import argparse, json, math, zipfile
from collections import defaultdict
from pathlib import Path

def walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v)
    elif isinstance(obj, list):
        yield obj
        for v in obj:
            yield from walk(v)

def is_trade_list(value):
    if not value or not isinstance(value, list) or not all(isinstance(x, dict) for x in value):
        return False
    sample = value[:min(5, len(value))]
    return any(
        ("pair" in x or "symbol" in x)
        and any(k in x for k in ("profit_abs", "profit_ratio", "profit", "close_profit_abs"))
        for x in sample
    )

def load_trade_payload(directory: Path):
    metas = sorted(directory.glob("*.meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not metas:
        raise RuntimeError(f"No Freqtrade metadata JSON found in {directory}")
    meta = json.loads(metas[0].read_text())
    zip_name = meta.get("latest_backtest")
    if not zip_name:
        raise RuntimeError(f"Metadata {metas[0]} has no latest_backtest pointer")
    archive = directory / zip_name
    if not archive.is_file():
        raise RuntimeError(f"Backtest archive referenced by metadata is missing: {archive}")
    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if n.endswith(".json") and not n.endswith(".meta.json")]
        if not names:
            raise RuntimeError(f"No result JSON inside {archive}")
        # Prefer the canonical backtest result file, not ancillary data.
        name = sorted(names, key=lambda n: ("backtest-result" not in n, n))[0]
        payload = json.loads(zf.read(name))
    candidates = [x for x in walk(payload) if is_trade_list(x)]
    if not candidates:
        raise RuntimeError(f"No machine-readable trade list found in {archive}; keys={list(payload)[:20]}")
    trades = max(candidates, key=len)
    if len(trades) < 1:
        raise RuntimeError("Trade export contains no trades")
    return archive, payload, trades

def number(trade, keys):
    for key in keys:
        value = trade.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--directory", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    archive, payload, trades = load_trade_payload(Path(args.directory))
    profits = [number(t, ("profit_abs", "close_profit_abs", "profit")) for t in trades]
    profits = [p for p in profits if p is not None]
    if len(profits) != len(trades):
        raise RuntimeError(f"Only {len(profits)}/{len(trades)} trades expose an absolute profit field")
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    per_pair = defaultdict(lambda: {"trades": 0, "wins": 0, "net_profit_abs": 0.0})
    per_exit = defaultdict(lambda: {"trades": 0, "wins": 0, "net_profit_abs": 0.0})
    monthly = defaultdict(lambda: {"trades": 0, "wins": 0, "net_profit_abs": 0.0})
    for t, p in zip(trades, profits):
        pair = t.get("pair", t.get("symbol", "UNKNOWN"))
        reason = t.get("exit_reason", t.get("sell_reason", "UNKNOWN"))
        date = str(t.get("close_date", t.get("date", t.get("open_date", "UNKNOWN"))))[:7]
        for bucket, key in ((per_pair, pair), (per_exit, reason), (monthly, date)):
            bucket[key]["trades"] += 1
            bucket[key]["wins"] += int(p > 0)
            bucket[key]["net_profit_abs"] += p
    report = {
        "label": args.label,
        "source_archive": archive.name,
        "trade_count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(trades), 3),
        "net_profit_abs": round(sum(profits), 8),
        "gross_profit_abs": round(gross_win, 8),
        "gross_loss_abs": round(gross_loss, 8),
        "trade_profit_factor": round(gross_win / gross_loss, 6) if gross_loss else None,
        "average_trade_profit_abs": round(sum(profits) / len(profits), 8),
        "worst_trade_abs": round(min(profits), 8),
        "best_trade_abs": round(max(profits), 8),
        "per_pair": dict(per_pair),
        "per_exit_reason": dict(per_exit),
        "per_month": dict(monthly),
        "worst_10_trades": sorted(
            [{"pair": t.get("pair", t.get("symbol", "UNKNOWN")),
              "exit_reason": t.get("exit_reason", t.get("sell_reason", "UNKNOWN")),
              "profit_abs": p, "open_date": t.get("open_date"), "close_date": t.get("close_date")}
             for t, p in zip(trades, profits)],
            key=lambda x: x["profit_abs"]
        )[:10],
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str) + "\\n")
    print(json.dumps({k: report[k] for k in ("label", "trade_count", "wins", "losses", "win_rate_pct", "net_profit_abs", "trade_profit_factor", "worst_trade_abs")}, indent=2))
    print(f"PASS: extracted {len(trades)} individual trades from {archive}")

if __name__ == "__main__":
    main()

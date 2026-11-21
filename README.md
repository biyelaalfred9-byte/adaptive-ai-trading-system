# Adaptive AI Trading System

A cloud-first, multi-market research and paper-trading platform for crypto and Forex.

## Safety-first development stages

1. Foundation: domain models, deterministic risk gate, paper execution, SQLite journal and API.
2. Market data: read-only Binance/CCXT crypto candles and OANDA practice Forex candles.
3. Data operations: polling collector, persistent SQLite OHLCV history and paginated historical backfills.
4. Strategy engine: explainable trend-following, momentum and mean-reversion baselines.
5. **Backtesting:** next-candle entries, conservative stop/target handling, transaction costs and performance metrics.
6. **Walk-forward evaluation:** rolling out-of-sample strategy comparison with explicit qualification thresholds.
7. Dashboard and cloud deployment: planned, not yet deployed.
8. Live trading: disabled; no live order-submission adapter exists.

AI may propose and explain signals. It cannot change risk limits or bypass the deterministic risk gate. Market-data adapters are read-only. Backtests are research simulations, not broker execution.

## Risk defaults

- Risk per trade: 0.5% of equity; hard maximum: 1%.
- Daily loss stop: 2%; maximum drawdown stop: 5%.
- Maximum open positions: 2; minimum signal confidence: 0.70.
- Leverage: 1x (disabled).
- Stop-loss required; no martingale or uncontrolled averaging down.

## Install and test

Python 3.11+

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
pip install -e ".[dev,crypto,forex]"
pytest -q
```

## Market data and collection

Crypto OHLCV uses public Binance/CCXT endpoints. Forex OHLCV uses the read-only OANDA practice adapter; access from Zambia must be verified. Neither submits orders. `CandleStore` persists OHLCV in SQLite and `MarketDataCollector` polls providers. `HistoricalDataBackfiller` pages through a requested UTC date range, stores completed candles and safely upserts repeated downloads. CCXT timeframes (for example `1h`) and OANDA timeframes (for example `H1`) are supported. Backfills are bounded by a maximum page count and must be run separately for each market/symbol/timeframe. It is not yet a deployed always-on worker or websocket feed.

## Strategies

`StrategyEngine` runs three deterministic candidates: EMA trend-following, lookback momentum and RSI mean-reversion. Signals include rationale, confidence, ATR-based stop and reward/risk target. Signals never place orders.

## Backtesting

```python
from trading_system.backtesting import Backtester, BacktestConfig
from trading_system.strategies import TrendFollowingStrategy

result = Backtester(BacktestConfig(initial_equity=10_000)).run(
    candles, TrendFollowingStrategy()
)
print(result.metrics)
```

The backtester creates signals using data available through a candle close and enters no earlier than the next candle open. It holds at most one position, applies estimated spread/slippage/fees at both entry and exit, and reports win rate, profit factor, net PnL, return and maximum drawdown. Open positions are marked to market for drawdown measurement and closed at the final candle close. If a candle touches both stop and target, it assumes the stop was hit first. These conservative OHLC assumptions are not order-book replay and cannot model all gaps, liquidity, funding, swap or market impact.

Use `WalkForwardEvaluator` to compare strategies over rolling chronological folds. Training candles are used only for indicator warm-up; signals and trades are restricted to each test window. The default `SelectionPolicy` requires at least 30 out-of-sample trades, 60% profitable folds, pooled profit factor of at least 1.10 and worst-fold drawdown no greater than 5%. These thresholds are configurable. A qualifying strategy is only eligible for further paper testing; this module does not activate or select a live strategy. Run the evaluation across multiple instruments and market regimes. Backtests do not prove future profitability.

## Execution costs

Paper execution defaults are 2 bps spread, 1 bp slippage and 10 bps fee. Backtests charge these estimated costs at entry and exit. Replace defaults with realistic venue/instrument assumptions before interpreting results.

## Limitations

No dashboard, cloud deployment, websocket ingestion, order-book replay, funding/swap model, latency/partial-fill model or live execution is implemented. Keep all trading in paper mode; never commit API keys.


## Automated research runner

The config-driven runner evaluates the configured market/symbol/timeframe series already stored in SQLite and writes a JSON report. It compares all three baseline strategies over rolling out-of-sample folds and lists any strategy meeting the configured paper-testing eligibility thresholds. Insufficient history is reported per job instead of stopping the whole batch.

Create a file such as `research.json`:

```json
{
  "database": "market_data.sqlite3",
  "selection_policy": {
    "min_oos_trades": 30,
    "min_profitable_fold_ratio": 0.6,
    "max_worst_fold_drawdown_pct": 5.0,
    "min_profit_factor": 1.1
  },
  "jobs": [
    {
      "market": "crypto",
      "symbol": "BTC/USDT",
      "timeframe": "1h",
      "train_size": 1000,
      "test_size": 250,
      "candle_limit": 20000
    },
    {
      "market": "crypto",
      "symbol": "ETH/USDT",
      "timeframe": "1h",
      "train_size": 1000,
      "test_size": 250,
      "candle_limit": 20000
    }
  ]
}
```

Run it with:

```bash
python -m trading_system.research_runner research.json --output research_report.json
```

The database must first contain historical candles for each configured series. Backfill each series using `HistoricalDataBackfiller` before running research. Forex jobs can be added when OANDA practice data access is available; credentials are not embedded in the research config. The report is research-only: qualification means eligible for additional paper testing, never automatic strategy activation or live trading. JSON output labels infinite profit factor as the string `"Infinity"` so the report remains standards-compliant.


## Historical backfill command

Use `trading_system.backfill_runner` to populate the SQLite candle database from read-only market-data providers. Supply explicit timezone-aware UTC date bounds; the command never submits orders.

Create `backfill.json`:

```json
{
  "database": "market_data.sqlite3",
  "jobs": [
    {
      "market": "crypto",
      "exchange": "binance",
      "symbol": "BTC/USDT",
      "timeframe": "1h",
      "start": "2024-01-01T00:00:00Z",
      "end": "2026-01-01T00:00:00Z",
      "page_limit": 500,
      "max_pages": 1000
    },
    {
      "market": "crypto",
      "exchange": "binance",
      "symbol": "ETH/USDT",
      "timeframe": "1h",
      "start": "2024-01-01T00:00:00Z",
      "end": "2026-01-01T00:00:00Z"
    }
  ]
}
```

Install the crypto extra and run:

```bash
pip install -e ".[crypto,dev]"
python -m trading_system.backfill_runner backfill.json --output backfill_report.json
```

The runner reports per-series success/failure and candle counts, continues to later jobs after a job fails, and exits non-zero if any job failed. Backfill jobs are bounded by explicit dates, page size and maximum pages. OANDA Forex jobs use `market: "forex"`, an OANDA instrument such as `EUR_USD`, and OANDA granularity such as `H1`; set `OANDA_API_TOKEN` in the environment first. Do not put tokens in JSON or commit credentials. Re-running a range is safe because SQLite upserts existing candle timestamps.

### Research diagnostics and cost sensitivity

Research report version 2 adds per-market/per-strategy diagnostics without changing strategy signals, risk limits or qualification thresholds. It reports aggregate gross PnL, estimated costs, net PnL, costs relative to positive gross PnL, net profit factor and exit-reason counts. It also reruns each strategy on the same chronological folds with zero, half-configured and configured transaction costs, then compares the results with a simple long-only buy-and-hold return over each test fold.

Cost scenarios are diagnostic counterfactuals, not executable fee quotes. The zero-cost result is an upper-bound diagnostic, not a tradable result. The buy-and-hold benchmark does not include fees, funding or risk adjustment and is not directly equivalent to a strategy that can short or hold cash. All diagnostics remain historical research; they do not activate strategies or enable live trading.


## Execution adapter boundary

The internal `ExecutionAdapter` protocol defines the narrow interface for order execution implementations. The existing `PaperExecutor` satisfies this contract and remains the only implemented adapter. Strategy modules do not receive an execution adapter and cannot submit orders.

Any future execution coordinator must evaluate every candidate through the deterministic `RiskGate` before creating an `OrderRequest`. A live adapter is not implemented, enabled, or authorized by adding this interface. Live trading remains disabled.


## Risk-gated paper coordinator

`PaperTradingCoordinator` is the orchestration boundary for candidate signals. It validates that the stop and target are on the correct side of the reference price, asks the deterministic `RiskGate` for approval, sizes quantity from the configured risk fraction and stop distance, and caps notional exposure at 1x equity. Successful simulated fills can be recorded in `TradeJournal`. When processing a batch, each filled position consumes an available position slot before the next candidate is evaluated.

Example:

```python
from trading_system.execution.coordinator import PaperTradingCoordinator
from trading_system.execution.paper import PaperExecutor
from trading_system.risk import RiskSnapshot

coordinator = PaperTradingCoordinator(PaperExecutor())
results = coordinator.process(
    signals,
    reference_prices={"BTC/USDT": 60_000},
    snapshot=RiskSnapshot(
        equity=10_000,
        daily_pnl=0,
        current_drawdown=0,
        open_positions=0,
    ),
)
```

The coordinator only accepts simulated execution results. It is not a live-trading engine, does not manage open positions after entry, and does not calculate realized daily PnL or portfolio drawdown; those remain portfolio-state responsibilities before any live-capable system could be considered.


## Paper portfolio ledger

`PaperPortfolio` is a persistent SQLite ledger for simulated positions. It records paper fills, tracks open positions, closes positions at supplied simulated exit prices, and calculates realized PnL, mark-to-market unrealized PnL, equity, peak equity, drawdown and open-position count. Entry and exit fees are deducted; spread and slippage are reflected in the execution average prices supplied by the paper executor.

Use `risk_snapshot(marks)` to produce the current `RiskSnapshot` for the risk gate. Supply fresh mark prices for open symbols so unrealized PnL and drawdown are not stale. Its daily-loss input is deliberately conservative: realized PnL from trades closed on the current UTC day plus the full mark-to-market PnL on all open positions. This can include PnL accrued before today for positions held overnight. It is a protective approximation, not an exchange-grade daily accounting boundary.

The ledger is paper-only. It does not yet automatically reconcile coordinator fills, discover stop/target exits, model funding/borrow/swap, or stream live prices. No live execution is enabled.

# Adaptive AI Trading System

A cloud-first, multi-market research and paper-trading platform for crypto and Forex.

## Safety-first development stages

1. Foundation: domain models, deterministic risk gate, paper execution, SQLite journal and API.
2. Market data: read-only Binance/CCXT crypto candles and OANDA practice Forex candles.
3. Data operations: polling collector, persistent SQLite OHLCV history and paginated historical backfills.
4. Strategy engine: explainable trend-following, momentum and mean-reversion baselines.
5. **Backtesting:** next-candle entries, conservative stop/target handling, transaction costs and performance metrics.
6. **Walk-forward evaluation:** rolling out-of-sample strategy comparison with explicit qualification thresholds.
7. **Continuous paper engine:** local polling, next-candle-open simulated entries, deterministic risk checks, portfolio valuation and automatic candle-based exits.
8. Dashboard and cloud deployment: planned, not yet deployed.
9. Live trading: disabled; no live order-submission adapter exists.

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

Crypto OHLCV uses public Binance/CCXT endpoints. Forex OHLCV uses the read-only OANDA practice adapter; access from Zambia must be verified. Neither submits orders. `CandleStore` persists OHLCV in SQLite and `MarketDataCollector` polls providers. The continuous paper engine runs this polling locally as a worker; it is not yet deployed as a cloud service or websocket feed. `HistoricalDataBackfiller` pages through a requested UTC date range, stores completed candles and safely upserts repeated downloads. CCXT timeframes (for example `1h`) and OANDA timeframes (for example `H1`) are supported. Backfills are bounded by a maximum page count and must be run separately for each market/symbol/timeframe. Historical collection and the paper engine remain local processes unless you deploy them yourself.

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

The coordinator only accepts simulated execution results. It is not a live-trading engine. Open-position valuation, daily PnL and drawdown are maintained by the paper portfolio.


## Paper portfolio ledger

`PaperPortfolio` is a persistent SQLite ledger for simulated positions. It records paper fills, tracks open positions, closes positions at supplied simulated exit prices, and calculates realized PnL, mark-to-market unrealized PnL, equity, peak equity, drawdown and open-position count. Entry and exit fees are deducted; spread and slippage are reflected in the execution average prices supplied by the paper executor.

Use `risk_snapshot(marks)` to produce the current `RiskSnapshot` for the risk gate. Supply fresh mark prices for open symbols so unrealized PnL and drawdown are not stale. Its daily-loss input is deliberately conservative: realized PnL from trades closed on the current UTC day plus the full mark-to-market PnL on all open positions. This can include PnL accrued before today for positions held overnight. It is a protective approximation, not an exchange-grade daily accounting boundary.

The ledger is paper-only. Funding/borrow/swap, order-book replay and exchange-grade daily accounting are not modeled. No live execution is enabled.


When constructed with `portfolio=PaperPortfolio(...)`, the paper coordinator automatically records each successful simulated fill as an open portfolio position. The portfolio then supplies updated risk snapshots through `portfolio.risk_snapshot(marks)`; callers must provide current mark prices and handle exit conditions/close fills explicitly.


### Automatic paper exits

Positions opened through `PaperTradingCoordinator` now persist their strategy stop-loss and take-profit levels. After each completed candle, call `portfolio.process_candle_exits(...)` with that symbol's OHLC values. The monitor closes triggered positions, charges estimated exit spread, slippage and fees, and records realized PnL. If a candle touches both stop and target, the conservative assumption is that the stop executes first. Gap-through stops are filled at the candle open before adverse estimated costs.

This is a candle-driven simulation, not a real-time stop order. Completed candles must be supplied chronologically; the continuous paper engine now handles polling and portfolio marks locally.


### Continuous paper-trading runner

The continuous engine connects the read-only market-data collector, strategy engine, deterministic risk gate, paper executor, SQLite portfolio and automatic exits. It processes completed candles only. A signal is calculated from the previous candle history and, if approved, is simulated at the next candle's open. The strongest baseline candidate is selected per symbol and the engine avoids stacking multiple positions in the same symbol. Stop/target checks then use the entry candle's OHLC with stop-first handling when both levels are touched.

**Important startup behavior:** on first launch, the engine records the latest completed candle as its starting cursor and does not replay historical backfill as if it were live. It begins processing newly completed candles after that point. The cursor is persisted in `paper_engine_state.sqlite3`; if the cursor falls behind the retained candle history, the engine stops that subscription rather than silently skipping missing candles. Keep the market, portfolio, journal and engine-state SQLite files between restarts.

Install and start on Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m trading_system.paper_trading_runner configs/paper-trading.crypto.example.json
```

Run one polling cycle (useful for checking connectivity/configuration):

```powershell
.\.venv\Scripts\python.exe -m trading_system.paper_trading_runner configs/paper-trading.crypto.example.json --once
```

Stop the continuous worker with `Ctrl+C`. The example config monitors BTC/USDT, ETH/USDT, BNB/USDT and SOL/USDT on the 1-hour timeframe. It uses the existing local `market_data.sqlite3` file and paper portfolio/journal databases. Do not delete the engine-state database while retaining the portfolio, as that would reset the candle cursor. The initial cycle will only establish cursors; the engine will wait for the next completed 1-hour candles before processing new entries.

The worker is paper-only and has no live order adapter. It does not guarantee profitability or emulate exchange order books, partial fills, funding, spread changes, latency or market impact. Use realistic cost assumptions and inspect the journal and portfolio throughout an extended paper run before considering any later stage. Forex subscriptions require the read-only OANDA practice token in `OANDA_API_TOKEN`; OANDA access from Zambia still needs to be verified.

## Docker cloud deployment (paper trading only)

The repository includes a Docker image and Compose service for running the paper-trading worker on a single Linux VPS or cloud VM. The worker is deliberately not exposed as a public web service; it polls public Binance market data and writes its SQLite state to a persistent Docker volume.

Build and start:

```bash
docker compose up -d --build
```

Follow logs:

```bash
docker compose logs -f paper-trader
```

Stop the worker without deleting its persistent data:

```bash
docker compose down
```

Restart after a host reboot: Docker Compose sets `restart: unless-stopped`. Host directory `./cloud-data` is bind-mounted at `/data` and stores market candles, portfolio, journal and engine cursors. This makes backups and migration straightforward. Before the first cloud start, stop the local worker and copy its four SQLite files (`market_data.sqlite3`, `paper_portfolio.sqlite3`, `trading_journal.sqlite3` and `paper_engine_state.sqlite3`) into `cloud-data/` on the server if you want to preserve the existing paper positions and candle cursors. Create the directory and set ownership for container UID 10001 (`sudo mkdir -p cloud-data && sudo chown 10001:10001 cloud-data`). Do not start the cloud worker against an empty data directory if you intend to continue the existing paper portfolio. Do not run multiple replicas against the same SQLite files. Back up `cloud-data/` before upgrades or maintenance; replacing the container image does not back up or migrate data.

The container runs as an unprivileged user, has a read-only root filesystem, drops Linux capabilities and does not publish inbound ports. It remains paper-only and has no live order adapter. The Docker image installs the crypto extra only. Forex is not enabled in the cloud example; if added later, inject the OANDA practice token through the host environment rather than committing it.

Before deploying to a paid host, build and run the image locally, verify that logs show successful market polling, and confirm that the SQLite files persist across container recreation. Cloud hosting is not yet provisioned by this repository: a cloud VM, Docker Engine/Compose, firewall policy, SSH access and a backup plan must be set up separately. Never put exchange secrets in the image, Compose file, or Git.



## Zero-cost scheduled paper trading (GitHub Actions)

The public repository includes an optional hourly GitHub Actions runner. It wakes shortly after each UTC hour, fetches public Binance candles, runs one paper-trading cycle, and exits. It does not need your laptop to stay on and it never submits live orders.

Enable it from the repository's **Actions** tab if GitHub asks you to enable workflows. Select **Scheduled Paper Trading** and use **Run workflow** for the first manual test. The schedule then runs at minute 17 of each hour (UTC). GitHub may delay scheduled workflows, so this is not a real-time or always-on trading service.

The four SQLite files are restored and saved using GitHub Actions cache under `state/`. Cache persistence is best-effort, not a durable database: caches can be evicted or unavailable. If state is lost, the engine's first run safely sets a fresh candle cursor instead of replaying the historical backfill, but the previous paper positions and journal will not be recovered. Download/export state regularly if you need durable records.

This workflow is intended for this public repository, where standard GitHub-hosted runner usage is free. Keep it public to retain that free runner allowance; private-repository usage can consume the account's included Actions compute quota. Check GitHub's current [Actions billing documentation](https://docs.github.com/en/actions/concepts/billing-and-usage). No API keys or payment details are required for public Binance candle collection.

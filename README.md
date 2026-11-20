# Adaptive AI Trading System

A cloud-first, multi-market research and paper-trading platform for crypto and Forex.

## Safety-first development stages

1. Foundation: domain models, deterministic risk gate, paper execution, SQLite journal and API.
2. Market data: read-only Binance/CCXT crypto candles and OANDA practice Forex candles.
3. Data operations: polling collector and persistent SQLite OHLCV history.
4. Strategy engine: explainable trend-following, momentum and mean-reversion baselines.
5. **Backtesting:** next-candle entries, conservative stop/target handling, transaction costs and performance metrics.
6. Dashboard and cloud deployment: planned, not yet deployed.
7. Live trading: disabled; no live order-submission adapter exists.

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

Crypto OHLCV uses public Binance/CCXT endpoints. Forex OHLCV uses the read-only OANDA practice adapter; access from Zambia must be verified. Neither submits orders. `CandleStore` persists OHLCV in SQLite and `MarketDataCollector` polls providers. It is not yet a deployed always-on worker or websocket feed.

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

Use `walk_forward_splits` to keep chronological training and test periods separate. Compare strategies across multiple instruments and market regimes; do not select a strategy on training-period results alone. Require sufficient out-of-sample trades before automated selection. Backtests do not prove future profitability.

## Execution costs

Paper execution defaults are 2 bps spread, 1 bp slippage and 10 bps fee. Backtests charge these estimated costs at entry and exit. Replace defaults with realistic venue/instrument assumptions before interpreting results.

## Limitations

No dashboard, cloud deployment, websocket ingestion, order-book replay, funding/swap model, latency/partial-fill model or live execution is implemented. Keep all trading in paper mode; never commit API keys.

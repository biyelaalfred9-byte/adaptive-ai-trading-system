# Adaptive AI Trading System

A cloud-first, multi-market research and paper-trading platform for crypto and Forex.

## Safety-first development stages

1. **Foundation:** domain models, deterministic risk gate, paper execution, SQLite trade journal and API.
2. **Market data:** read-only Binance/CCXT crypto candles and OANDA practice Forex candles.
3. **Data operations:** polling collector and persistent SQLite OHLCV history.
4. **Strategy engine:** explainable trend-following, momentum and mean-reversion baselines.
5. **Research and paper trading:** configurable spread, slippage and fee assumptions; walk-forward evaluation.
6. **Dashboard and cloud deployment:** planned, not yet deployed.
7. **Live trading:** disabled; no live order-submission adapter exists.

AI may propose and explain signals. It cannot change risk limits or bypass the deterministic risk gate. Market-data adapters are read-only. Strategy signals are candidates only; they must pass the independent risk gate before paper execution.

## Risk defaults

- Risk per trade: 0.5% of equity; hard maximum: 1%.
- Daily loss stop: 2%; maximum drawdown stop: 5%.
- Maximum open positions: 2; minimum signal confidence: 0.70.
- Leverage: 1x (disabled).
- Stop-loss required; no martingale or uncontrolled averaging down.

These are guardrails, not a guarantee against loss. Validate in simulation before considering real capital.

## Install and test

Python 3.11+

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,crypto,forex]"
pytest -q
uvicorn trading_system.api:app --reload
```

Health endpoint: `GET /health`; configuration: `GET /system`.

## Market data

### Crypto (public data)

```python
from trading_system.market_data.crypto_ccxt import CCXTMarketData
provider = CCXTMarketData("binance")
candles = provider.fetch_candles("BTC/USDT", timeframe="1h", limit=100)
```

No exchange API key is required for public OHLCV candles. Install the crypto extra with `pip install -e ".[crypto]"`.

### Forex (OANDA practice data)

Set `OANDA_API_TOKEN` locally (never commit it), then:

```python
from trading_system.market_data.forex_oanda import OandaPracticeMarketData
provider = OandaPracticeMarketData()
candles = provider.fetch_candles("EUR_USD", timeframe="H1", limit=100)
```

This adapter reads completed midpoint candles from the OANDA practice host and does not submit orders. OANDA access and product availability vary by country; verify access from Zambia before relying on it.

## Historical storage and collection

`CandleStore` stores OHLCV candles in SQLite. Its composite key (market, symbol, timeframe, timestamp) makes repeated collection idempotent; a corrected candle updates the existing row.

```python
from trading_system.market_data.collector import MarketDataCollector
from trading_system.market_data.storage import CandleStore
from trading_system.market_data.service import MarketDataService
from trading_system.market_data.crypto_ccxt import CCXTMarketData

service = MarketDataService(crypto=CCXTMarketData("binance"))
store = CandleStore("market_data.sqlite3")
collector = MarketDataCollector(service, store)
collector.collect_once(market="crypto", symbol="BTC/USDT", timeframe="1h", limit=200)
```

The collector polls on a schedule; it is not a websocket feed or a deployed always-on cloud worker yet.

## Strategy engine

The initial deterministic strategies are intentionally simple and inspectable:

- **Trend-following:** fast/slow EMA alignment and price confirmation.
- **Momentum:** lookback-period percentage return against a configurable threshold.
- **Mean reversion:** RSI oversold/overbought thresholds.

Each emitted signal includes a confidence score, a human-readable reason, an ATR-based stop and a configurable reward/risk target. Strategies only analyze supplied candles and never place orders. Insufficient history or no qualifying setup returns no signal. The engine returns candidates independently; it does not silently choose a winner or alter risk settings.

```python
from trading_system.strategies import StrategyEngine
signals = StrategyEngine().generate(candles)
for signal in signals:
    print(signal.side, signal.confidence, signal.rationale)
```

Signals are not proof of an edge. Next, the strategies need out-of-sample walk-forward evaluation with realistic costs before any automated selection.

## Paper execution costs

`PaperExecutor` uses configurable one-way basis-point assumptions. Defaults are 2 bps spread, 1 bp slippage and 10 bps fee. Buys fill above and sells below the reference price; fees, spread cost and slippage cost are stored separately in the trade journal. These are configurable approximations, not exchange-specific quotes, order-book simulation or a profitability guarantee.

## Remaining limitations

No dashboard, cloud deployment, websocket ingestion, order-book replay, latency/partial-fill model or live execution is implemented. The OANDA adapter has not been validated with a user's account. Automated tests are configured in GitHub Actions; check the Actions tab for the latest run result.

Never put API keys in source control. Keep `TRADING_MODE=paper`.

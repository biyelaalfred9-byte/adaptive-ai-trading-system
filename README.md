# Adaptive AI Trading System

A cloud-first, multi-market research and paper-trading platform for crypto and Forex.

## Safety-first development stages

1. **Foundation:** domain models, deterministic risk gate, paper execution, SQLite trade journal and API.
2. **Market data:** read-only Binance/CCXT crypto candles and OANDA practice Forex candles.
3. **Data operations:** polling collector and persistent SQLite OHLCV history.
4. **Research and paper trading:** configurable spread, slippage and fee assumptions; walk-forward evaluation.
5. **Dashboard and cloud deployment:** planned, not yet deployed.
6. **Live trading:** disabled; no live order-submission adapter exists.

AI may propose and explain signals. It cannot change risk limits or bypass the deterministic risk gate. Market-data adapters are read-only.

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

# Run one collection cycle:
collector.collect_once(market="crypto", symbol="BTC/USDT", timeframe="1h", limit=200)

# Or run a polling worker; stop it by setting the threading.Event:
# collector.run_forever([{"market": "crypto", "symbol": "BTC/USDT"}], 60, stop_event)
```

The collector polls on a schedule; it is not a websocket feed or a deployed always-on cloud worker yet.

## Paper execution costs

`PaperExecutor` uses configurable one-way basis-point assumptions. Defaults are 2 bps spread, 1 bp slippage and 10 bps fee. Buys fill above and sells below the reference price; fees, spread cost and slippage cost are stored separately in the trade journal. These are configurable approximations, not exchange-specific quotes, order-book simulation or a profitability guarantee.

```python
from trading_system.execution.paper import PaperExecutor, PaperCostModel
executor = PaperExecutor(PaperCostModel(spread_bps=2, slippage_bps=1, fee_bps=10))
```

## Remaining limitations

No signal-generation/strategy engine, dashboard, cloud deployment, websocket ingestion, order-book replay, latency/partial-fill model or live execution is implemented. The OANDA adapter has not been validated with a user's account. Automated tests are configured in GitHub Actions; check the Actions tab for the latest run result.

Never put API keys in source control. Keep `TRADING_MODE=paper`.

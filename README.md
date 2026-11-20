# Adaptive AI Trading System

A cloud-first, multi-market research and paper-trading platform for crypto and Forex.

## Safety-first development stages

1. **Foundation:** domain models, immutable risk configuration, paper execution, SQLite journal and API.
2. **Market data:** read-only Binance/CCXT crypto candles and OANDA practice Forex candles.
3. **Research:** realistic fees/spread/slippage, walk-forward and out-of-sample evaluation.
4. **Paper trading:** continuous simulation and strategy comparison before any live consideration.
5. **Live trading:** disabled by default; only after explicit approval, broker eligibility checks and operational review.

AI may propose and explain signals. It cannot change risk limits or bypass the deterministic risk gate. Market-data adapters are read-only; no live order submission is implemented.

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

Set `OANDA_API_TOKEN` in your local environment (never commit it), then:

```python
from trading_system.market_data.forex_oanda import OandaPracticeMarketData
provider = OandaPracticeMarketData()
candles = provider.fetch_candles("EUR_USD", timeframe="H1", limit=100)
```

This adapter calls the OANDA practice host and reads completed midpoint candles only. It does not submit orders. OANDA access and product availability vary by country; verify that you can open and use a practice account from Zambia before relying on it. If not, we will add another eligible broker adapter.

## Current limitations

The CCXT and OANDA adapters retrieve historical candles on demand; there is not yet a continuous streaming collector, persistent candle store, dashboard, cloud deployment, strategy engine or live execution. Paper fills are simplified and do not yet model spread, slippage, fees, latency or partial fills. Do not interpret early backtest/paper results as proof of profitability.

Never put API keys in source control. Keep `TRADING_MODE=paper`.

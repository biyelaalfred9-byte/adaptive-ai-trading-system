# Adaptive AI Trading System

A cloud-first, multi-market research and paper-trading platform for crypto and Forex.

## Safety-first development stages

1. **Scaffold:** domain models, immutable risk configuration, paper execution, SQLite journal, API and tests.
2. **Market data:** add exchange/broker adapters with timestamped, validated data.
3. **Research:** realistic fees/spread/slippage, walk-forward and out-of-sample evaluation.
4. **Paper trading:** run continuously and compare strategy results before any live consideration.
5. **Live trading:** disabled by default; only after explicit approval, broker eligibility checks and operational review.

AI may propose and explain signals. It cannot change risk limits or bypass the deterministic risk gate. No live order adapter or API credentials are included in this starter.

## Initial risk defaults

- Risk per trade: 0.5% of equity; hard maximum: 1%.
- Daily loss stop: 2%; maximum drawdown stop: 5%.
- Maximum open positions: 2.
- Minimum signal confidence: 0.70.
- Leverage: 1x (no leverage).
- Stop-loss required; no martingale or uncontrolled averaging down.

These are conservative software defaults, not a guarantee against loss. Validate and tune in simulation before any real capital is considered.

## Run locally

Python 3.11+

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn trading_system.api:app --reload
```

Health endpoint: `GET /health`. System/risk configuration: `GET /system`.

## Current scope

This is an initial paper-trading foundation, not a finished autonomous trading bot. Exchange connectivity, Forex broker selection, live execution, dashboard, authentication, cloud deployment and strategy models remain future work. Never put API keys in source control.

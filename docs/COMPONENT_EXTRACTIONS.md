# Reusable component extraction register

## Trailing-stop and break-even state machine — implemented locally

- **Reference:** [Jesse](https://github.com/jesse-ai/jesse), upstream MIT license.
- **Approach:** independently implemented deterministic long/short stop transitions; no Jesse source code copied.
- **Behavior:** break-even activation, trailing activation, favorable-extreme tracking, and monotonic stop tightening. The stop never moves away from price.
- **Timing safety:** update only after a completed candle; the new stop applies to the next candle. This avoids look-ahead bias from using a candle's high/low to claim a stop was already active within that candle.
- **Integration status:** standalone module with unit tests. Not wired into the live paper portfolio yet. Existing fixed stop-loss, take-profit, and 12-hour maximum holding period remain unchanged.

## Execution slippage guard — implemented locally

- **Reference:** [Hummingbot](https://github.com/hummingbot/hummingbot), Apache-2.0.
- **Approach:** independent depth-weighted VWAP estimator with insufficient-depth and maximum-adverse-slippage rejection.
- **Integration status:** standalone module only; current paper feed is candle-based and does not provide synchronized order-book snapshots.

## Risk-budgeted position sizing — implemented locally

- **Reference:** [Jesse position-risk guidance](https://github.com/jesse-ai/jesse/blob/570e983de5fb303b88793f1d1ad25e218ed19dea/jesse/mcp/resources/position_risk.md), MIT project.
- **Approach:** independent risk-budget sizing; quantity accounts for stop distance, estimated entry/exit fees, and an available-capital cap. No Jesse source code copied.
- **Safety:** spot/1x notional cap only; leverage is not modeled. This module does not override the existing risk gate.
- **Integration status:** standalone with unit tests; not connected to order sizing.

## Stop-loss cooldown and drawdown protection — implemented locally

- **Reference:** [Freqtrade StoplossGuard](https://github.com/freqtrade/freqtrade/blob/e7408a6d17cd8ef4d96165540d14f7fe90d07bca/freqtrade/plugins/protections/stoploss_guard.py) and [MaxDrawdown](https://github.com/freqtrade/freqtrade/blob/e7408a6d17cd8ef4d96165540d14f7fe90d07bca/freqtrade/plugins/protections/max_drawdown_protection.py), GPL-3.0 project.
- **Approach:** independently implemented pure protection functions over supplied trade outcomes/equity points; no Freqtrade source code copied.
- **Behavior:** rolling stop-loss count triggers a configurable entry lockout; peak-to-trough drawdown calculation can block new entries at a threshold.
- **Integration status:** standalone with unit tests; not connected to the paper engine.

## Research / architecture references

| Project | License checked | Treatment |
|---|---|---|
| [QuantConnect Lean](https://github.com/QuantConnect/Lean) | Apache-2.0 | Study portfolio construction and risk-model boundaries; no code copied |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | Apache-2.0 | Study multi-agent research workflow; deterministic risk gate remains authoritative |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | LGPL-3.0 | Architecture reference only pending linking/copying review |
| [Jesse](https://github.com/jesse-ai/jesse) | MIT | Risk-management reference; preserve notices if source is ever copied |
| [Hummingbot](https://github.com/hummingbot/hummingbot) | Apache-2.0 | Execution/slippage design reference |

## Isolated strategy research

Freqtrade / NostalgiaForInfinity V5 remains isolated due to GPL-3.0 lineage.
Do not merge its strategy source into the core without an explicit licensing
decision and independently reproduced results.

All extraction work is paper/research-only. No live broker adapter, exchange
credentials, or live-order path is enabled by these components.

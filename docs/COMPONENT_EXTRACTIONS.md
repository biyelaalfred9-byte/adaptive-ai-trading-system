# Reusable component extraction register

This register separates source-code reuse from independently implemented
design adaptations. No third-party strategy is enabled for paper or live
execution merely because its source has been reviewed.

## 1. Execution slippage guard — implemented locally

- **Reference project:** [Hummingbot](https://github.com/hummingbot/hummingbot)
- **Upstream license checked:** Apache-2.0 ([LICENSE](https://github.com/hummingbot/hummingbot/blob/master/LICENSE)).
- **What we adopted:** the execution-system principle that an order must be
  evaluated against available order-book depth, not only the best quote.
- **What we wrote:** `trading_system/execution/slippage.py` is an independent
  implementation. No Hummingbot source file or code block was copied.
- **Behavior:** depth-weighted VWAP for buy/sell orders, explicit insufficient
  depth rejection, and a configurable maximum adverse slippage in basis points.
- **Integration status:** unit-tested standalone component. It is not yet wired
  into the paper coordinator because the current market-data contract supplies
  candles, not synchronized order-book snapshots. Do not treat its guard as
  active protection until an order-book feed is connected and tested.

## 2. Risk and position-management review — next extraction

- **Reference project:** [Jesse](https://github.com/jesse-ai/jesse)
- **Upstream license checked:** MIT ([LICENSE](https://github.com/jesse-ai/jesse/blob/master/LICENSE)).
- **Current local coverage:** deterministic risk gate, risk-based sizing,
  stop-loss/take-profit exits, and a 12-hour maximum paper holding period
  already exist in this repository.
- **Next review:** compare trailing-stop and break-even transition semantics
  against Jesse, then add only missing behavior with tests. Preserve MIT
  notices if any Jesse source is copied; no Jesse code has been copied in this
  change.

## 3. Research and event-driven architecture references

| Project | License checked | Planned treatment |
|---|---|---|
| [QuantConnect Lean](https://github.com/QuantConnect/Lean) | Apache-2.0 | Study portfolio construction and risk-model boundaries; no code copied yet |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | Apache-2.0 | Study multi-agent research workflow; keep AI advisory, never able to bypass deterministic risk |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | LGPL-3.0 | Architecture reference only until linking/copying implications are reviewed |

## 4. Excluded from direct integration for now

- **Freqtrade / NostalgiaForInfinity V5:** GPL-3.0 strategy lineage. Keep the
  strategy in an isolated research workspace; do not merge its source into the
  core system without an explicit licensing decision and a reproducible
  independent validation.
- A reported backtest metric is not a verified edge. Any candidate still needs
  individual-trade export, realistic costs, conservative exposure, and a
  separate-period test.

## Safety boundary

All changes in this extraction workstream are research/paper-only. No live
broker adapter, exchange credentials, or live-order path is enabled by this
work.

# Open-Source Trading Bot Audit

Audit date: 2026-11-21

This document records an initial source and license review before integrating third-party trading code. The project remains an independent research and paper-trading system. No third-party source code has been copied into this repository.

## Findings

| Project | Current repository license | Relevant strengths | Decision |
|---|---|---|---|
| [Freqtrade](https://github.com/freqtrade/freqtrade) | GPL-3.0 | Strategy interface, backtesting, hyperparameter optimization, exchange support and protections | Study its strategy lifecycle and validation ideas. Do not copy or link its implementation into this project unless we deliberately accept GPL-3.0 obligations for a derivative/distributed combined work. |
| [Hummingbot](https://github.com/hummingbot/hummingbot) | Apache-2.0 | Exchange connector architecture, order tracking, execution lifecycle and market-making infrastructure | Best reference for a future execution-adapter boundary. Reuse/adaptation may be possible subject to Apache-2.0 notice, attribution and patent terms. Do not import the full framework yet. |
| [Jesse](https://github.com/jesse-ai/jesse) | MIT | Strategy interface, multi-timeframe research, backtesting and performance metrics | Useful reference for strategy lifecycle and research ergonomics. Code reuse is comparatively permissive, but preserve copyright and license notices for copied portions. Do not add the full framework as a dependency yet. |

## Source files inspected

- Freqtrade: `freqtrade/strategy/interface.py` on the `develop` branch. It defines an abstract strategy interface and exposes strategy-level timeframe, stop-loss, ROI, order-type and position-adjustment settings.
- Hummingbot: repository README and Apache-2.0 license. Its connector framework is the strongest architectural reference for exchange-specific execution and order tracking.
- Jesse: `jesse/strategies/Strategy.py` on the `master` branch. It defines an abstract strategy base class and strategy state for orders, stops, take-profits and trade lifecycle.

License files reviewed directly in each repository. This is an engineering screening, not legal advice; verify the exact upstream version and all applicable notices before distributing derivative code.

## Integration plan

1. Keep this project's domain models, deterministic risk gate, journal and paper executor as the core. Third-party strategy or execution code must never bypass the risk gate.
2. Define a small internal strategy contract: receive validated candles and portfolio context; return a typed signal with direction, confidence, rationale, stop and target. Strategy code must not submit orders.
3. Add an execution-adapter interface separately from strategy logic. The first implementation remains paper-only; a future exchange adapter must support order state, partial fills, cancellation, precision, minimum sizes, fees and failure recovery.
4. Add execution-cost and fill-model tests before treating any backtest as realistic. Current results show that all 12 baseline strategies lose after configured costs, and most remain below break-even even at zero cost.
5. Evaluate any borrowed component in isolation with tests and attribution before integrating it. Do not add an entire external bot as a dependency just to obtain one feature.

## Explicit non-goals

- No live trading or live order submission.
- No exchange secrets or API keys.
- No automatic changes to risk limits.
- No copying of GPL-3.0 Freqtrade implementation code into this repository at this stage.
- No claim that third-party components have already been integrated.

# External Strategy Discovery — First Candidate Audit

Date: 2026-11-25
Status: research only; no strategy activated; live trading remains disabled.

## Objective

Stop spending time inventing elementary indicators. Identify public, reproducible crypto strategies with substantial backtest evidence, inspect their actual implementation and assumptions, then reproduce them independently before considering paper deployment.

## Discovery source

Freqle (https://freqle.org/) indexes public Freqtrade strategies and runs sandboxed checks/backtests. It currently reports 15,874 strategies from 1,705 repositories and 10,043 sandboxed backtests. These are useful screening signals, not proof of live profitability.

## Candidate A — NostalgiaForInfinityV5

- Strategy page: https://freqle.org/strategy/fde70f61e88d42d6
- Source repository: https://github.com/remiotore/ccxt-freqtrade/blob/4586a4c30611106117494c6518bca1840047f818/strategies/NostalgiaForInfinityV5.py
- Reported Freqle backtest: 33 spot pairs, 2021-01-01 to 2026-01-01, 5-minute timeframe, 0.1% fee per side, 10 open-trade slots.
- Reported: +204.65% net return, profit factor 3.65, max drawdown 3.06%, 1,448 trades, 84.3% win rate, Sharpe 6.059, CAGR 24.9%.
- Freqle reports a live-signal/lookahead consistency check on a sampled window: 1,499 checked signals, no late/never-live signals in that check.

These are third-party sandboxed historical results, not audited exchange statements or verified live returns. The reported return also lagged the 33-pair buy-and-hold market change (+451.55%) over that period, so absolute profitability is not the same as benchmark outperformance.

### Code and implementation findings

The publicly indexed source identifies:
- 5-minute primary timeframe and 1-hour informative timeframe.
- 400-candle startup warm-up.
- 21 buy-condition switches and 8 sell-condition switches.
- Bollinger Bands, EMA, MFI, RSI, SMA and custom exit/trailing logic.
- Limit entry/exit order types.
- A nominal stoploss of -99% and a custom exit/trailing approach.

This is a complex, highly parameterized mean-reversion/dip-buying system with higher-timeframe filters, not a simple indicator recipe. A -99% nominal stoploss is not acceptable for our risk model. We must reproduce its entry/exit logic inside a bounded risk envelope or reject it; we must not copy its risk settings blindly.

### Major reproduction risks

1. The result depends on 5-minute data across 33 pairs. Our current validated dataset is hourly and only covers BTC, ETH, BNB and SOL. Hourly candles cannot reproduce this strategy.
2. The Freqle page notes that its broad backtests do not use 1-minute detail replay for every trailing/custom-exit test. Intrabar execution assumptions can materially change results.
3. The backtest uses limit orders. A candle-touch assumption is not proof that an order would fill; fill probability, queue position, spread and adverse selection matter.
4. The strategy has 179 hyperopt parameters / condition switches. That creates substantial overfitting and multiple-testing risk.
5. The public source repository path was inspected, but a repository-level LICENSE file was not found at the expected root path. Do not copy source code into our project until licence terms are confirmed. We can independently reimplement documented logic while preserving attribution and legal review.

## Candidate B — NotAnotherSMAOffsetStrategyHOv3

- Strategy source project: https://github.com/Audris-M/Data-science-trading-project
- Freqle public leaderboard result: 33 pairs, 2022–2024; +76.7%, PF 2.51, 489 trades, 64.6% win rate, 5.08% max drawdown.
- Source uses a 5-minute timeframe, Elliott Wave Oscillator, EMA offsets, RSI and trailing exits.
- Its own project README says its three-week cloud live/dry-run experiment did not meet backtest expectations.

This is a secondary candidate, not a validated production edge. The short live/dry-run mismatch is a direct warning against trusting optimized backtests.

## Decision

NostalgiaForInfinityV5 is the first candidate to reproduce because it has the strongest current public sandbox result among the inspected candidates and a multi-year, multi-pair report. It is **not approved for live trading or even assumed profitable**.

## Next research work

1. Obtain 5-minute OHLCV for the 33-pair universe if public data access and free compute/storage permit. Begin with BTC, ETH, BNB and SOL for a smaller reproducibility pilot.
2. Pin the exact strategy source commit, configuration, parameter file, pairlist, date range, fee assumptions and Freqtrade version.
3. Run Freqtrade's own backtester with 1-minute detail candles for trailing/custom exits where feasible.
4. Model limit-order fills conservatively; if realistic fill replay is unavailable, clearly label the result as an optimistic candle backtest.
5. Keep our independent hard risk gate: 0.5% risk/trade, 1% hard cap, 2% daily stop, 5% max drawdown, max 2 simultaneous positions, 1x/no leverage. Do not import the candidate's 10-slot/unbounded stake configuration.
6. Split by time chronologically: development, validation and untouched final holdout. Do not retune against the holdout.
7. Compare net returns against buy-and-hold and cash, across assets and market regimes. Require positive after-cost performance across multiple holdout windows, a robust parameter neighborhood, and realistic drawdown before paper testing.
8. If the source licence is not confirmed, do not copy code. Treat the source as a research reference and implement independently.

## Current conclusion

We have found a serious candidate worth testing, not a proven money-making bot. The public metrics justify reproduction work; the timeframe mismatch, hyperparameter count, limit-order assumptions and trailing-stop realism are the reasons not to deploy it blindly.

No code from this strategy has been copied into the trading system. No live execution has been added or enabled.

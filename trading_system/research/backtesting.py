"""Cost-aware historical backtesting with conservative candle execution assumptions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import inf
from typing import Protocol, Sequence

from trading_system.domain import Side, Signal
from trading_system.execution.paper import PaperCostModel
from trading_system.market_data.models import Candle


class SignalGenerator(Protocol):
    name: str

    def generate(self, candles: Sequence[Candle]) -> Signal | None: ...


@dataclass(frozen=True)
class BacktestConfig:
    initial_equity: float = 10_000.0
    position_fraction: float = 0.10
    costs: PaperCostModel = PaperCostModel()
    allow_short: bool = True

    def __post_init__(self) -> None:
        if self.initial_equity <= 0:
            raise ValueError("initial_equity must be positive")
        if not 0 < self.position_fraction <= 1:
            raise ValueError("position_fraction must be in (0, 1]")


@dataclass(frozen=True)
class BacktestTrade:
    strategy: str
    side: Side
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    quantity: float
    gross_pnl: float
    costs: float
    net_pnl: float
    exit_reason: str
    rationale: str


@dataclass(frozen=True)
class BacktestMetrics:
    trade_count: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    gross_pnl: float
    total_costs: float
    net_pnl: float
    total_return_pct: float
    max_drawdown_pct: float
    average_trade_pnl: float
    expectancy: float


@dataclass(frozen=True)
class BacktestResult:
    strategy: str
    metrics: BacktestMetrics
    trades: tuple[BacktestTrade, ...]
    equity_curve: tuple[float, ...]


@dataclass
class _Position:
    signal: Signal
    signal_index: int
    entry_index: int
    entry_price: float
    quantity: float


class Backtester:
    """One-position-at-a-time backtest; signal at close, entry next candle open.

    If stop and target are both touched within one candle, stop is assumed first.
    Costs are approximated at both entry and exit; this is not order-book replay.
    """

    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()

    def run(self, candles: Sequence[Candle], strategy: SignalGenerator) -> BacktestResult:
        self._validate(candles)
        equity = self.config.initial_equity
        peak = equity
        max_drawdown = 0.0
        equity_curve = [equity]
        trades: list[BacktestTrade] = []
        position: _Position | None = None
        pending: tuple[Signal, int] | None = None

        for index, candle in enumerate(candles):
            if position is not None:
                exit_data = self._exit_on_candle(position, candle)
                if exit_data is not None:
                    exit_price, reason = exit_data
                    trade = self._close(position, candles, index, exit_price, reason, strategy.name)
                    trades.append(trade)
                    equity += trade.net_pnl
                    position = None

            if position is None and pending is not None and pending[1] == index - 1:
                signal, signal_index = pending
                if signal.side is Side.BUY or self.config.allow_short:
                    quantity = equity * self.config.position_fraction / candle.open
                    position = _Position(signal, signal_index, index, candle.open, quantity)
                    exit_data = self._exit_on_candle(position, candle)
                    if exit_data is not None:
                        exit_price, reason = exit_data
                        trade = self._close(position, candles, index, exit_price, reason, strategy.name)
                        trades.append(trade)
                        equity += trade.net_pnl
                        position = None
                pending = None

            if position is None and index < len(candles) - 1:
                signal = strategy.generate(candles[:index + 1])
                if (signal is not None and signal.symbol == candle.symbol
                        and signal.market.value == candle.market
                        and signal.created_at <= candle.timestamp):
                    pending = (signal, index)

            marked_equity = equity
            if position is not None:
                direction = 1.0 if position.signal.side is Side.BUY else -1.0
                gross_unrealized = position.quantity * (candle.close - position.entry_price) * direction
                cost_rate = ((self.config.costs.spread_bps / 2
                              + self.config.costs.slippage_bps
                              + self.config.costs.fee_bps) / 10_000) * 2
                estimated_costs = position.quantity * position.entry_price * cost_rate
                marked_equity += gross_unrealized - estimated_costs
            peak = max(peak, marked_equity)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - marked_equity) / peak)
            equity_curve.append(marked_equity)

        if position is not None:
            last_index = len(candles) - 1
            trade = self._close(position, candles, last_index, candles[-1].close,
                                "end_of_data", strategy.name)
            trades.append(trade)
            equity += trade.net_pnl
            equity_curve[-1] = equity
            peak = max(peak, equity)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - equity) / peak)

        metrics = self._metrics(trades, self.config.initial_equity, equity, max_drawdown)
        return BacktestResult(strategy.name, metrics, tuple(trades), tuple(equity_curve))

    @staticmethod
    def _validate(candles: Sequence[Candle]) -> None:
        if len(candles) < 2:
            raise ValueError("at least two candles are required")
        first = candles[0]
        if any((c.market, c.symbol, c.timeframe) !=
               (first.market, first.symbol, first.timeframe) for c in candles):
            raise ValueError("candles must share market, symbol and timeframe")
        if any(a.timestamp >= b.timestamp for a, b in zip(candles, candles[1:])):
            raise ValueError("candles must be strictly chronological")

    @staticmethod
    def _exit_on_candle(position: _Position, candle: Candle) -> tuple[float, str] | None:
        signal = position.signal
        if signal.side is Side.BUY:
            if candle.low <= signal.stop_loss:
                return min(candle.open, signal.stop_loss), "stop_loss"
            if candle.high >= signal.take_profit:
                return max(candle.open, signal.take_profit), "take_profit"
        else:
            if candle.high >= signal.stop_loss:
                return max(candle.open, signal.stop_loss), "stop_loss"
            if candle.low <= signal.take_profit:
                return min(candle.open, signal.take_profit), "take_profit"
        return None

    def _close(self, position: _Position, candles: Sequence[Candle], exit_index: int,
               exit_price: float, reason: str, strategy_name: str) -> BacktestTrade:
        signal = position.signal
        direction = 1.0 if signal.side is Side.BUY else -1.0
        gross_pnl = position.quantity * (exit_price - position.entry_price) * direction
        cost_rate = ((self.config.costs.spread_bps / 2
                      + self.config.costs.slippage_bps
                      + self.config.costs.fee_bps) / 10_000) * 2
        costs = position.quantity * position.entry_price * cost_rate
        return BacktestTrade(
            strategy=strategy_name, side=signal.side,
            signal_time=candles[position.signal_index].timestamp,
            entry_time=candles[position.entry_index].timestamp,
            exit_time=candles[exit_index].timestamp,
            entry_price=position.entry_price, exit_price=exit_price,
            stop_loss=signal.stop_loss, take_profit=signal.take_profit,
            quantity=position.quantity, gross_pnl=gross_pnl, costs=costs,
            net_pnl=gross_pnl - costs, exit_reason=reason, rationale=signal.rationale,
        )

    @staticmethod
    def _metrics(trades: Sequence[BacktestTrade], initial: float, final: float,
                 max_drawdown: float) -> BacktestMetrics:
        wins = [t.net_pnl for t in trades if t.net_pnl > 0]
        losses = [t.net_pnl for t in trades if t.net_pnl < 0]
        gross = sum(t.gross_pnl for t in trades)
        costs = sum(t.costs for t in trades)
        net = sum(t.net_pnl for t in trades)
        count = len(trades)
        win_count = len(wins)
        average = net / count if count else 0.0
        profit_factor = sum(wins) / abs(sum(losses)) if losses else (inf if wins else 0.0)
        return BacktestMetrics(
            trade_count=count, wins=win_count, losses=len(losses),
            win_rate=win_count / count if count else 0.0,
            profit_factor=profit_factor, gross_pnl=gross, total_costs=costs,
            net_pnl=net, total_return_pct=(final / initial - 1) * 100,
            max_drawdown_pct=max_drawdown * 100,
            average_trade_pnl=average, expectancy=average,
        )

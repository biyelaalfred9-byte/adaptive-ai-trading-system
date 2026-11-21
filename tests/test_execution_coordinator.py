from datetime import datetime, timezone

import pytest

from trading_system.config import RiskConfig
from trading_system.domain import ExecutionResult, Market, OrderRequest, Side, Signal
from trading_system.execution.coordinator import PaperTradingCoordinator
from trading_system.execution.paper import PaperExecutor
from trading_system.risk import RiskSnapshot
from trading_system.portfolio import PaperPortfolio


def make_signal(side=Side.BUY, confidence=0.9):
    if side is Side.BUY:
        stop, target = 99.0, 102.0
    else:
        stop, target = 101.0, 98.0
    return Signal(Market.CRYPTO, "BTC/USDT", side, confidence, stop, target,
                  "unit test", datetime.now(timezone.utc))


def make_snapshot(**overrides):
    values = dict(equity=10_000, daily_pnl=0, current_drawdown=0, open_positions=0)
    values.update(overrides)
    return RiskSnapshot(**values)


class RecordingExecutor:
    def __init__(self):
        self.orders = []

    def execute(self, order: OrderRequest):
        self.orders.append(order)
        return ExecutionResult("paper-1", "filled", order.quantity,
                               order.reference_price, simulated=True)


def test_coordinator_sizes_by_risk_and_caps_notional():
    executor = RecordingExecutor()
    coordinator = PaperTradingCoordinator(executor)
    result = coordinator.process([make_signal()], {"BTC/USDT": 100},
                                 make_snapshot())[0]

    assert result.approved
    assert result.order.quantity == pytest.approx(50.0)
    assert result.order.quantity * 100 <= 10_000


def test_coordinator_rejects_low_confidence_without_execution():
    executor = RecordingExecutor()
    result = PaperTradingCoordinator(executor).process(
        [make_signal(confidence=0.4)], {"BTC/USDT": 100}, make_snapshot()
    )[0]

    assert not result.approved
    assert "confidence" in result.reason
    assert executor.orders == []


def test_coordinator_rejects_invalid_stop_levels_and_price():
    executor = RecordingExecutor()
    invalid = Signal(Market.CRYPTO, "BTC/USDT", Side.BUY, 0.9, 101, 102,
                     "bad stop", datetime.now(timezone.utc))
    results = PaperTradingCoordinator(executor).process(
        [invalid, make_signal()], {"BTC/USDT": 0}, make_snapshot()
    )

    assert all(not item.approved for item in results)
    assert executor.orders == []


def test_coordinator_never_exceeds_position_limit_for_batch():
    executor = RecordingExecutor()
    coordinator = PaperTradingCoordinator(executor)
    signals = [make_signal(), make_signal()]
    results = coordinator.process(
        signals, {"BTC/USDT": 100}, make_snapshot(open_positions=1)
    )

    assert [item.approved for item in results] == [True, False]
    assert len(executor.orders) == 1
    assert "open positions" in results[1].reason


def test_coordinator_supports_short_position_sizing():
    executor = RecordingExecutor()
    result = PaperTradingCoordinator(executor).process(
        [make_signal(Side.SELL)], {"BTC/USDT": 100}, make_snapshot()
    )[0]

    assert result.approved
    assert result.order.side is Side.SELL
    assert result.order.quantity == pytest.approx(50.0)


def test_coordinator_refuses_non_simulated_result():
    class UnsafeExecutor:
        def execute(self, order):
            return ExecutionResult("live", "filled", order.quantity, order.reference_price,
                                   simulated=False)

    with pytest.raises(RuntimeError, match="non-simulated"):
        PaperTradingCoordinator(UnsafeExecutor()).process(
            [make_signal()], {"BTC/USDT": 100}, make_snapshot()
        )


def test_risk_sizing_respects_configured_fraction():
    config = RiskConfig(risk_per_trade=0.0025)
    executor = RecordingExecutor()
    result = PaperTradingCoordinator(executor, risk_config=config).process(
        [make_signal()], {"BTC/USDT": 100}, make_snapshot()
    )[0]

    assert result.approved
    assert result.order.quantity == pytest.approx(25.0)



def test_coordinator_persists_filled_position_to_portfolio(tmp_path):
    portfolio = PaperPortfolio(tmp_path / "portfolio.db", starting_equity=10_000)
    coordinator = PaperTradingCoordinator(RecordingExecutor(), portfolio=portfolio)
    result = coordinator.process(
        [make_signal()], {"BTC/USDT": 100}, make_snapshot()
    )[0]

    assert result.approved
    state = portfolio.state({"BTC/USDT": 100})
    assert state.open_positions == 1
    assert portfolio.open_positions()[0].symbol == "BTC/USDT"

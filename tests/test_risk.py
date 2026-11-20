from datetime import datetime, timezone
from trading_system.domain import Market, Side, Signal
from trading_system.risk import RiskGate, RiskSnapshot


def signal(confidence=0.9):
    return Signal(Market.CRYPTO, "BTC/USDT", Side.BUY, confidence,
                  60000, 66000, "test signal", datetime.now(timezone.utc))


def snapshot(**overrides):
    values = dict(equity=1000, daily_pnl=0, current_drawdown=0, open_positions=0)
    values.update(overrides)
    return RiskSnapshot(**values)


def test_approves_valid_signal_for_paper_only():
    decision = RiskGate().evaluate(signal(), snapshot())
    assert decision.approved
    assert "paper" in decision.reason


def test_rejects_low_confidence():
    assert not RiskGate().evaluate(signal(0.5), snapshot()).approved


def test_rejects_daily_loss_limit():
    assert not RiskGate().evaluate(signal(), snapshot(daily_pnl=-20)).approved


def test_rejects_drawdown_limit():
    assert not RiskGate().evaluate(signal(), snapshot(current_drawdown=0.05)).approved


def test_rejects_too_many_positions():
    assert not RiskGate().evaluate(signal(), snapshot(open_positions=2)).approved

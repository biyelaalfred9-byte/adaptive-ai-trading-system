import pytest

from trading_system.domain import Side
from trading_system.risk_sizing import risk_to_quantity


def test_long_risk_sizing_includes_round_trip_fees():
    sized = risk_to_quantity(
        equity=1000, risk_fraction=0.005, entry_price=100,
        stop_price=95, side=Side.BUY, fee_rate=0.001,
    )
    assert sized.estimated_loss_at_stop == pytest.approx(5)
    assert sized.quantity == pytest.approx(5 / 5.195)


def test_short_risk_sizing_and_capital_limit():
    sized = risk_to_quantity(
        equity=1000, risk_fraction=0.01, entry_price=100,
        stop_price=105, side=Side.SELL, available_capital=200,
    )
    assert sized.quantity == pytest.approx(2)
    assert sized.notional == pytest.approx(200)
    assert sized.capped_by_capital
    assert sized.estimated_loss_at_stop == pytest.approx(10)


def test_invalid_stop_side_rejected():
    with pytest.raises(ValueError, match="long stop"):
        risk_to_quantity(equity=1000, risk_fraction=.01, entry_price=100,
                         stop_price=101, side=Side.BUY)


def test_invalid_risk_fraction_rejected():
    with pytest.raises(ValueError):
        risk_to_quantity(equity=1000, risk_fraction=0, entry_price=100,
                         stop_price=95, side=Side.BUY)

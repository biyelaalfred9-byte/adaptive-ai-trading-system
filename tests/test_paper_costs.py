import pytest

from trading_system.domain import OrderRequest, Side
from trading_system.execution.paper import PaperCostModel, PaperExecutor


def test_buy_fill_includes_spread_slippage_and_fee():
    order = OrderRequest("BTC/USDT", Side.BUY, 1, 100)
    result = PaperExecutor(PaperCostModel(spread_bps=2, slippage_bps=1, fee_bps=10)).execute(order)
    assert result.average_price == pytest.approx(100.02)
    assert result.spread_cost == pytest.approx(0.01)
    assert result.slippage_cost == pytest.approx(0.01)
    assert result.fee_paid == pytest.approx(0.10002)
    assert result.simulated is True


def test_sell_fill_is_below_reference_price():
    order = OrderRequest("BTC/USDT", Side.SELL, 2, 100)
    result = PaperExecutor(PaperCostModel(2, 1, 10)).execute(order)
    assert result.average_price == pytest.approx(99.98)
    assert result.fee_paid > 0


def test_cost_model_rejects_negative_costs():
    with pytest.raises(ValueError):
        PaperCostModel(fee_bps=-1)

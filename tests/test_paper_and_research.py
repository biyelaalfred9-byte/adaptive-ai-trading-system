from trading_system.domain import OrderRequest, Side
from trading_system.execution.paper import PaperExecutor
from trading_system.research import walk_forward_splits


def test_paper_executor_marks_fill_simulated_and_applies_default_costs():
    order = OrderRequest("BTC/USDT", Side.BUY, 0.01, 50000)
    result = PaperExecutor().execute(order)
    assert result.status == "filled"
    assert result.simulated is True
    assert result.average_price > 50000
    assert result.fee_paid > 0
    assert result.spread_cost > 0
    assert result.slippage_cost > 0


def test_walk_forward_splits_are_ordered_and_non_overlapping():
    data = list(range(10))
    splits = list(walk_forward_splits(data, train_size=4, test_size=2))
    assert splits == [([0, 1, 2, 3], [4, 5]),
                      ([2, 3, 4, 5], [6, 7]),
                      ([4, 5, 6, 7], [8, 9])]

import pytest

from trading_system.domain import Side
from trading_system.execution.slippage import BookLevel, SlippageGuard


def test_buy_estimates_depth_weighted_vwap_and_accepts_within_limit():
    guard = SlippageGuard(max_slippage_bps=20)
    result = guard.estimate(
        Side.BUY, 3, 100,
        bids=[BookLevel(99.9, 5)],
        asks=[BookLevel(100.05, 1), BookLevel(100.10, 2)],
    )
    assert result.accepted
    assert result.vwap == pytest.approx((100.05 + 2 * 100.10) / 3)
    assert result.slippage_bps == pytest.approx((result.vwap - 100) / 100 * 10_000)


def test_buy_rejects_excessive_market_impact():
    result = SlippageGuard(max_slippage_bps=5).estimate(
        Side.BUY, 2, 100,
        bids=[BookLevel(99.9, 10)],
        asks=[BookLevel(100.0, 1), BookLevel(100.2, 1)],
    )
    assert not result.accepted
    assert result.reason == "slippage limit exceeded"


def test_sell_walks_bids_from_best_to_worst():
    result = SlippageGuard(max_slippage_bps=30).estimate(
        Side.SELL, 2, 100,
        bids=[BookLevel(99.8, 1), BookLevel(100.0, 1)],
        asks=[BookLevel(100.1, 5)],
    )
    assert result.accepted
    assert result.vwap == pytest.approx(99.9)


def test_rejects_insufficient_depth_without_fabricating_vwap():
    result = SlippageGuard().estimate(
        Side.BUY, 3, 100,
        bids=[BookLevel(99.9, 10)],
        asks=[BookLevel(100.0, 2)],
    )
    assert not result.accepted
    assert result.filled_quantity == 2
    assert result.vwap is None


@pytest.mark.parametrize("quantity,reference", [(0, 100), (-1, 100), (1, 0)])
def test_rejects_invalid_request(quantity, reference):
    with pytest.raises(ValueError):
        SlippageGuard().estimate(
            Side.BUY, quantity, reference,
            bids=[BookLevel(99, 10)], asks=[BookLevel(101, 10)],
        )


def test_rejects_invalid_book_level():
    with pytest.raises(ValueError):
        SlippageGuard().estimate(
            Side.BUY, 1, 100,
            bids=[BookLevel(99, 10)], asks=[BookLevel(101, 0)],
        )

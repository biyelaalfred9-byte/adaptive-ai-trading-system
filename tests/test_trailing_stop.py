import pytest

from trading_system.domain import Side
from trading_system.trailing_stop import (
    TrailingStopConfig, TrailingStopState, update_trailing_stop,
)


def test_long_stop_moves_to_breakeven_then_trails_without_loosen():
    state = TrailingStopState.create(Side.BUY, 100, 95)
    config = TrailingStopConfig(
        activation_pct=0.04, trail_distance_pct=0.02,
        breakeven_activation_pct=0.02,
    )
    state = update_trailing_stop(state, 103, 99, config)
    assert state.breakeven_active
    assert state.stop_price == 100
    state = update_trailing_stop(state, 110, 102, config)
    assert state.trailing_active
    assert state.stop_price == pytest.approx(107.8)
    state = update_trailing_stop(state, 108, 101, config)
    assert state.stop_price == pytest.approx(107.8)


def test_short_stop_moves_down_and_never_loosens():
    state = TrailingStopState.create(Side.SELL, 100, 105)
    config = TrailingStopConfig(
        activation_pct=0.04, trail_distance_pct=0.02,
        breakeven_activation_pct=0.02,
    )
    state = update_trailing_stop(state, 101, 97, config)
    assert state.breakeven_active
    assert state.stop_price == 100
    state = update_trailing_stop(state, 98, 90, config)
    assert state.trailing_active
    assert state.stop_price == pytest.approx(91.8)
    state = update_trailing_stop(state, 99, 95, config)
    assert state.stop_price == pytest.approx(91.8)


def test_does_not_activate_before_threshold():
    state = TrailingStopState.create(Side.BUY, 100, 95)
    updated = update_trailing_stop(
        state, 101, 99,
        TrailingStopConfig(0.04, 0.02, 0.03),
    )
    assert updated.stop_price == 95
    assert not updated.trailing_active
    assert not updated.breakeven_active


@pytest.mark.parametrize("side,entry,stop", [
    (Side.BUY, 100, 100), (Side.BUY, 100, 101),
    (Side.SELL, 100, 100), (Side.SELL, 100, 99),
])
def test_initial_stop_must_be_on_loss_side(side, entry, stop):
    with pytest.raises(ValueError):
        TrailingStopState.create(side, entry, stop)


def test_rejects_invalid_candle_range():
    state = TrailingStopState.create(Side.BUY, 100, 95)
    with pytest.raises(ValueError):
        update_trailing_stop(state, 98, 99)

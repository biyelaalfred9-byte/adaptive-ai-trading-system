from datetime import datetime, timezone

import pytest

from trading_system.domain import ExecutionResult, OrderRequest, Side
from trading_system.portfolio import PaperPortfolio


T0 = datetime(2026, 11, 21, 10, tzinfo=timezone.utc)


def make_fill(side=Side.BUY, quantity=2, price=100, fee=1):
    order = OrderRequest("BTC/USDT", side, quantity, 100)
    result = ExecutionResult("paper-order", "filled", quantity, price,
                             simulated=True, fee_paid=fee)
    return order, result


def test_portfolio_tracks_open_position_and_unrealized_pnl(tmp_path):
    book = PaperPortfolio(tmp_path / "portfolio.db", starting_equity=1000)
    order, fill = make_fill()
    position = book.open_position(order, fill, T0)

    state = book.state({"BTC/USDT": 110}, T0)
    assert state.open_positions == 1
    assert state.unrealized_pnl == pytest.approx(19)
    assert state.equity == pytest.approx(1019)
    assert book.open_positions()[0].position_id == position.position_id


def test_close_records_realized_pnl_and_fees(tmp_path):
    book = PaperPortfolio(tmp_path / "portfolio.db", starting_equity=1000)
    order, fill = make_fill(quantity=2, price=101, fee=1)
    position = book.open_position(order, fill, T0)

    pnl = book.close_position(position.position_id, 111, exit_fee=1,
                              closed_at=datetime(2026, 11, 21, 12, tzinfo=timezone.utc))
    state = book.state(at=datetime(2026, 11, 21, 13, tzinfo=timezone.utc))

    assert pnl == pytest.approx(18)
    assert state.realized_pnl == pytest.approx(18)
    assert state.daily_pnl == pytest.approx(18)
    assert state.equity == pytest.approx(1018)
    assert state.open_positions == 0


def test_short_position_profit_and_loss(tmp_path):
    book = PaperPortfolio(tmp_path / "portfolio.db", starting_equity=1000)
    order, fill = make_fill(Side.SELL, quantity=1, price=100, fee=0)
    position = book.open_position(order, fill, T0)

    assert book.close_position(position.position_id, 90) == pytest.approx(10)


def test_rejects_non_simulated_and_duplicate_close(tmp_path):
    book = PaperPortfolio(tmp_path / "portfolio.db")
    order, fill = make_fill()
    with pytest.raises(ValueError, match="simulated"):
        book.open_position(order, ExecutionResult("live", "filled", 2, 100, simulated=False))
    position = book.open_position(order, fill, T0)
    book.close_position(position.position_id, 100)
    with pytest.raises(ValueError, match="not found"):
        book.close_position(position.position_id, 100)


def test_drawdown_and_persistent_peak_equity(tmp_path):
    path = tmp_path / "portfolio.db"
    book = PaperPortfolio(path, starting_equity=1000)
    order, fill = make_fill(quantity=1, price=100, fee=0)
    position = book.open_position(order, fill, T0)
    high = book.state({"BTC/USDT": 120}, T0)
    low = book.state({"BTC/USDT": 110}, T0)

    assert high.peak_equity == pytest.approx(1020)
    assert low.current_drawdown == pytest.approx(10 / 1020)
    reopened = PaperPortfolio(path)
    assert reopened.state({"BTC/USDT": 110}, T0).peak_equity == pytest.approx(1020)


def test_daily_pnl_only_counts_closed_trades_from_utc_day(tmp_path):
    book = PaperPortfolio(tmp_path / "portfolio.db", starting_equity=1000)
    order, fill = make_fill(quantity=1, price=100, fee=0)
    position = book.open_position(order, fill, T0)
    book.close_position(position.position_id, 105, closed_at=T0)
    next_day = datetime(2026, 11, 22, 1, tzinfo=timezone.utc)

    assert book.state(at=next_day).daily_pnl == 0



def test_long_stop_loss_exit_uses_gap_aware_fill_and_costs(tmp_path):
    book = PaperPortfolio(tmp_path / "portfolio.db", starting_equity=1000)
    order, fill = make_fill(quantity=1, price=100, fee=0)
    position = book.open_position(order, fill, T0, stop_loss=95, take_profit=110)

    exits = book.process_candle_exits(
        "BTC/USDT", open_price=93, high=96, low=92, close=94, at=T0
    )

    assert len(exits) == 1
    assert exits[0].reason == "stop_loss"
    assert exits[0].exit_price < 93
    assert book.open_positions() == []


def test_take_profit_exit_and_stop_first_when_both_touched(tmp_path):
    book = PaperPortfolio(tmp_path / "portfolio.db", starting_equity=1000)
    order, fill = make_fill(quantity=1, price=100, fee=0)
    book.open_position(order, fill, T0, stop_loss=95, take_profit=105)

    exits = book.process_candle_exits(
        "BTC/USDT", open_price=100, high=106, low=94, close=101, at=T0
    )

    assert len(exits) == 1
    assert exits[0].reason == "stop_loss"
    assert exits[0].realized_pnl < 0


def test_short_take_profit_exit(tmp_path):
    book = PaperPortfolio(tmp_path / "portfolio.db", starting_equity=1000)
    order, fill = make_fill(Side.SELL, quantity=1, price=100, fee=0)
    book.open_position(order, fill, T0, stop_loss=105, take_profit=95)

    exits = book.process_candle_exits(
        "BTC/USDT", open_price=100, high=102, low=94, close=96, at=T0
    )

    assert len(exits) == 1
    assert exits[0].reason == "take_profit"
    assert exits[0].realized_pnl > 0


def test_position_without_exit_levels_is_not_auto_closed(tmp_path):
    book = PaperPortfolio(tmp_path / "portfolio.db", starting_equity=1000)
    order, fill = make_fill(quantity=1, price=100, fee=0)
    book.open_position(order, fill, T0)

    assert book.process_candle_exits(
        "BTC/USDT", open_price=100, high=120, low=80, close=100, at=T0
    ) == []
    assert len(book.open_positions()) == 1


def test_rejects_invalid_candle_geometry(tmp_path):
    book = PaperPortfolio(tmp_path / "portfolio.db")
    with pytest.raises(ValueError, match="geometry"):
        book.process_candle_exits("BTC/USDT", 100, 99, 95, 98)

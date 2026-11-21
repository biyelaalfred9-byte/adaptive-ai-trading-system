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

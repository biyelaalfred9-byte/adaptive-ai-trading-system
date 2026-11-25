from datetime import datetime, timedelta, timezone

from trading_system.domain import ExecutionResult, Market, OrderRequest, Side, Signal
from trading_system.execution.coordinator import PaperTradingCoordinator
from trading_system.execution.paper import PaperExecutor
from trading_system.market_data.collector import MarketDataCollector
from trading_system.market_data.models import Candle
from trading_system.market_data.service import MarketDataService
from trading_system.market_data.storage import CandleStore
from trading_system.paper_engine import PaperTradingEngine, candle_duration
from trading_system.portfolio import PaperPortfolio


T0 = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(self, candles):
        self.candles = candles

    def fetch_candles(self, symbol, timeframe="1h", limit=100):
        return self.candles[-limit:]


class FixedStrategy:
    name = "fixed_test"

    def generate(self, candles):
        if len(candles) < 2:
            return None
        last = candles[-1]
        return Signal(
            Market.CRYPTO, last.symbol, Side.BUY, 0.9, 95.0, 110.0,
            "test signal", last.timestamp,
        )


class FixedStrategyEngine:
    def generate(self, candles):
        signal = FixedStrategy().generate(candles)
        return [signal] if signal else []


def candle(timestamp, open_price=100, high=103, low=98, close=102):
    return Candle("crypto", "BTC/USDT", "1h", timestamp,
                  open_price, high, low, close, 10)


def make_engine(tmp_path, candles):
    store = CandleStore(tmp_path / "candles.db")
    collector = MarketDataCollector(
        MarketDataService(crypto=FakeProvider(candles)), store
    )
    portfolio = PaperPortfolio(tmp_path / "portfolio.db", starting_equity=10_000)
    coordinator = PaperTradingCoordinator(PaperExecutor(), portfolio=portfolio)
    engine = PaperTradingEngine(
        collector, store, portfolio, coordinator,
        strategies=FixedStrategyEngine(),
        state_path=str(tmp_path / "engine.db"),
        process_existing_history=True,
    )
    return engine, portfolio


def test_engine_enters_on_next_candle_open_and_persists_position(tmp_path):
    candles = [
        candle(T0),
        candle(T0 + timedelta(hours=1)),
        candle(T0 + timedelta(hours=2)),
    ]
    engine, portfolio = make_engine(tmp_path, candles)

    report = engine.process_subscription(
        market="crypto", symbol="BTC/USDT", timeframe="1h",
        now=T0 + timedelta(hours=4),
    )

    assert report.candles_processed == 3
    assert report.entries_filled == 1
    position = portfolio.open_positions()[0]
    assert position.opened_at == T0 + timedelta(hours=2)
    assert position.stop_loss == 95
    assert position.take_profit == 110


def test_engine_deduplicates_already_processed_candles(tmp_path):
    candles = [
        candle(T0),
        candle(T0 + timedelta(hours=1)),
        candle(T0 + timedelta(hours=2)),
    ]
    engine, _ = make_engine(tmp_path, candles)
    now = T0 + timedelta(hours=4)

    first = engine.process_subscription(
        market="crypto", symbol="BTC/USDT", timeframe="1h", now=now
    )
    second = engine.process_subscription(
        market="crypto", symbol="BTC/USDT", timeframe="1h", now=now
    )

    assert first.candles_processed == 3
    assert second.candles_processed == 0


def test_engine_does_not_process_an_incomplete_candle(tmp_path):
    candles = [candle(T0), candle(T0 + timedelta(hours=1))]
    engine, _ = make_engine(tmp_path, candles)

    report = engine.process_subscription(
        market="crypto", symbol="BTC/USDT", timeframe="1h",
        now=T0 + timedelta(hours=1, minutes=30),
    )

    assert report.candles_processed == 1
    assert report.entries_filled == 0


def test_timeframe_duration_supports_ccxt_and_oanda_labels():
    assert candle_duration("1h") == timedelta(hours=1)
    assert candle_duration("M5") == timedelta(minutes=5)
    assert candle_duration("H4") == timedelta(hours=4)
    assert candle_duration("D") == timedelta(days=1)
    assert candle_duration("1M") == timedelta(days=30)



def test_first_launch_does_not_replay_backfilled_history(tmp_path):
    candles = [
        candle(T0),
        candle(T0 + timedelta(hours=1)),
        candle(T0 + timedelta(hours=2)),
    ]
    engine, portfolio = make_engine(tmp_path, candles)
    engine.process_existing_history = False

    report = engine.process_subscription(
        market="crypto", symbol="BTC/USDT", timeframe="1h",
        now=T0 + timedelta(hours=4),
    )

    assert report.candles_processed == 0
    assert report.entries_filled == 0
    assert report.candles_stored == 3
    assert report.candles_available == 3
    assert report.candles_completed == 3
    assert report.latest_candle_at == T0 + timedelta(hours=2)
    assert report.latest_completed_at == T0 + timedelta(hours=2)
    assert report.cursor_at == T0 + timedelta(hours=2)
    assert report.cursor_seeded is True
    assert portfolio.open_positions() == []



def test_engine_tries_next_candidate_if_best_signal_is_invalid_at_next_open(tmp_path):
    from trading_system.domain import Market, Side, Signal

    class TwoCandidateEngine:
        def generate(self, candles):
            if len(candles) < 2:
                return []
            timestamp = candles[-1].timestamp
            return [
                Signal(Market.CRYPTO, "BTC/USDT", Side.BUY, 0.95,
                       101.0, 120.0, "gap-invalid candidate", timestamp),
                Signal(Market.CRYPTO, "BTC/USDT", Side.BUY, 0.80,
                       90.0, 120.0, "valid fallback candidate", timestamp),
            ]

    candles = [
        candle(T0, close=102),
        candle(T0 + timedelta(hours=1), open_price=100),
        candle(T0 + timedelta(hours=2), open_price=100),
    ]
    engine, portfolio = make_engine(tmp_path, candles)
    engine.strategies = TwoCandidateEngine()

    report = engine.process_subscription(
        market="crypto", symbol="BTC/USDT", timeframe="1h",
        now=T0 + timedelta(hours=4),
    )

    assert report.entries_filled == 1
    assert len(report.candidates) == 2
    assert report.candidates[0].approved is False
    assert "bracket price" in report.candidates[0].reason
    assert report.candidates[1].approved is True
    assert len(portfolio.open_positions()) == 1



def test_engine_closes_open_position_after_configured_12_hours(tmp_path):
    candles = [
        candle(T0 + timedelta(hours=hour))
        for hour in range(13)
    ]
    engine, portfolio = make_engine(tmp_path, candles)
    order = OrderRequest("BTC/USDT", Side.BUY, 1, 100)
    fill = ExecutionResult(
        "existing-paper-position", "filled", 1, 100,
        simulated=True, fee_paid=0,
    )
    position = portfolio.open_position(order, fill, opened_at=T0)

    report = engine.process_subscription(
        market="crypto", symbol="BTC/USDT", timeframe="1h",
        now=T0 + timedelta(hours=14),
    )

    assert any(
        event.position_id == position.position_id
        and event.reason == "max_holding_period"
        for event in report.exits
    )
    assert all(item.position_id != position.position_id
               for item in portfolio.open_positions())


def test_run_once_processes_all_exits_before_globally_ranking_entries(tmp_path):
    symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT"]
    confidence = {
        "BTC/USDT": 0.71, "ETH/USDT": 0.72,
        "BNB/USDT": 0.91, "SOL/USDT": 0.88,
    }

    class MultiSymbolProvider:
        def fetch_candles(self, symbol, timeframe="1h", limit=100):
            return [
                Candle("crypto", symbol, timeframe, T0 + timedelta(hours=h),
                       100, 103, 98, 102, 10)
                for h in range(14)
            ]

    class MultiSymbolStrategies:
        def generate(self, candles):
            if len(candles) < 2:
                return []
            symbol = candles[-1].symbol
            return [Signal(
                Market.CRYPTO, symbol, Side.BUY, confidence[symbol],
                90, 120, "ranked test signal", candles[-1].timestamp,
            )]

    store = CandleStore(tmp_path / "multi-candles.db")
    service = MarketDataService(crypto=MultiSymbolProvider())
    collector = MarketDataCollector(service, store)
    portfolio = PaperPortfolio(tmp_path / "multi-portfolio.db", starting_equity=10_000)
    coordinator = PaperTradingCoordinator(PaperExecutor(), portfolio=portfolio)
    engine = PaperTradingEngine(
        collector, store, portfolio, coordinator,
        strategies=MultiSymbolStrategies(),
        state_path=str(tmp_path / "multi-engine.db"),
        process_existing_history=True,
        max_holding_period_hours=12,
    )

    # Fill both slots with aged positions that must expire during this cycle.
    for symbol in symbols[:2]:
        order = OrderRequest(symbol, Side.BUY, 1, 100)
        fill = ExecutionResult(
            f"old-{symbol}", "filled", 1, 100, simulated=True, fee_paid=0,
        )
        portfolio.open_position(order, fill, T0, 90, 120)

    subscriptions = [
        {"market": "crypto", "symbol": symbol, "timeframe": "1h", "limit": 100}
        for symbol in symbols
    ]
    reports = engine.run_once(subscriptions, now=T0 + timedelta(hours=15))

    # Old positions must close before any new market is allowed to consume a slot.
    exited = {event.symbol for report in reports for event in report.exits}
    assert exited == set(symbols[:2])
    opened = {position.symbol for position in portfolio.open_positions()}
    assert opened == {"BNB/USDT", "SOL/USDT"}
    assert sum(report.entries_filled for report in reports) == 2

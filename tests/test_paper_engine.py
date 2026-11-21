from datetime import datetime, timedelta, timezone

from trading_system.domain import Market, Side, Signal
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
    assert portfolio.open_positions() == []

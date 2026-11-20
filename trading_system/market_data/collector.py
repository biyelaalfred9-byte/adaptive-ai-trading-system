import logging
import threading
from collections.abc import Sequence

from .service import MarketDataService
from .storage import CandleStore

logger = logging.getLogger(__name__)


class MarketDataCollector:
    """Collect closed candles into SQLite; safe to call repeatedly."""

    def __init__(self, service: MarketDataService, store: CandleStore):
        self.service = service
        self.store = store

    def collect_once(self, *, market: str, symbol: str, timeframe: str = "1h",
                     limit: int = 100) -> int:
        candles = self.service.candles(market, symbol, timeframe, limit)
        return self.store.upsert(candles)

    def run_forever(self, subscriptions: Sequence[dict], interval_seconds: int = 60,
                    stop_event: threading.Event | None = None) -> None:
        """Poll subscriptions until stop_event is set. Intended for a worker process."""
        if interval_seconds < 1:
            raise ValueError("interval_seconds must be at least 1")
        stop = stop_event or threading.Event()
        while not stop.is_set():
            for item in subscriptions:
                if stop.is_set():
                    break
                try:
                    self.collect_once(**item)
                except Exception:
                    logger.exception("Market data collection failed for %s", item)
            stop.wait(interval_seconds)

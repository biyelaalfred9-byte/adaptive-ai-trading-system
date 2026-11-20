from typing import Protocol
from .models import Candle


class MarketDataProvider(Protocol):
    def fetch_candles(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> list[Candle]:
        """Return candles in ascending timestamp order."""

from .base import MarketDataProvider
from .models import Candle


class MarketDataService:
    def __init__(self, crypto: MarketDataProvider | None = None,
                 forex: MarketDataProvider | None = None):
        self.providers = {"crypto": crypto, "forex": forex}

    def candles(self, market: str, symbol: str, timeframe: str = "1h",
                limit: int = 100) -> list[Candle]:
        provider = self.providers.get(market.lower())
        if provider is None:
            raise ValueError(f"No provider configured for market: {market}")
        candles = provider.fetch_candles(symbol, timeframe, limit)
        if any(candles[i].timestamp >= candles[i + 1].timestamp
               for i in range(len(candles) - 1)):
            raise ValueError("provider returned duplicate or unordered candle timestamps")
        return candles

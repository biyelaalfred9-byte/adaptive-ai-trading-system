from .models import Candle


class CCXTMarketData:
    """Public, read-only OHLCV adapter. No exchange keys or order methods."""

    def __init__(self, exchange_id: str = "binance"):
        try:
            import ccxt
        except ImportError as exc:
            raise RuntimeError("Install crypto extras with: pip install -e '.[crypto]'") from exc
        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Unsupported CCXT exchange: {exchange_id}")
        self.exchange = exchange_class({"enableRateLimit": True})
        self.exchange.load_markets()

    def fetch_candles(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> list[Candle]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        candles = [Candle.from_epoch_ms(market="crypto", symbol=symbol,
                    timeframe=timeframe, timestamp_ms=row[0], open=row[1],
                    high=row[2], low=row[3], close=row[4], volume=row[5])
                   for row in rows]
        return sorted(candles, key=lambda candle: candle.timestamp)

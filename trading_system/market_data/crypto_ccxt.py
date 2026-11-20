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
        return self.fetch_candles_since(symbol, timeframe, None, limit)

    def fetch_candles_since(self, symbol: str, timeframe: str,
                            since, limit: int = 100) -> list[Candle]:
        """Fetch a page beginning at a timezone-aware UTC timestamp (or latest)."""
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        if since is not None and since.tzinfo is None:
            raise ValueError("since must be timezone-aware")
        since_ms = int(since.timestamp() * 1000) if since is not None else None
        rows = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
        candles = [Candle.from_epoch_ms(market="crypto", symbol=symbol,
                    timeframe=timeframe, timestamp_ms=row[0], open=row[1],
                    high=row[2], low=row[3], close=row[4], volume=row[5])
                   for row in rows]
        return sorted(candles, key=lambda candle: candle.timestamp)

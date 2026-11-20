from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Candle:
    market: str
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("candle timestamp must be timezone-aware")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("candle high is inconsistent")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("candle low is inconsistent")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")

    @classmethod
    def from_epoch_ms(cls, *, market: str, symbol: str, timeframe: str,
                      timestamp_ms: int, open: float, high: float, low: float,
                      close: float, volume: float) -> "Candle":
        return cls(market, symbol, timeframe,
                   datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
                   float(open), float(high), float(low), float(close), float(volume))

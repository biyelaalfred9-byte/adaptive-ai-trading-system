import os
import httpx
from .models import Candle


class OandaPracticeMarketData:
    """Read-only OANDA practice pricing candles; never submits orders."""

    def __init__(self, token: str | None = None, account_id: str | None = None,
                 base_url: str = "https://api-fxpractice.oanda.com"):
        self.token = token or os.getenv("OANDA_API_TOKEN")
        self.account_id = account_id or os.getenv("OANDA_ACCOUNT_ID")
        if not self.token:
            raise ValueError("OANDA_API_TOKEN is required for Forex practice data")
        self.base_url = base_url.rstrip("/")

    def fetch_candles(self, symbol: str, timeframe: str = "H1", limit: int = 100) -> list[Candle]:
        if limit < 1 or limit > 5000:
            raise ValueError("limit must be between 1 and 5000")
        instrument = symbol.upper().replace("/", "_")
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.base_url}/v3/instruments/{instrument}/candles"
        response = httpx.get(url, params={"granularity": timeframe, "count": limit,
                                          "price": "M"}, headers=headers, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
        candles = []
        for item in payload.get("candles", []):
            if not item.get("complete", False):
                continue
            mid = item["mid"]
            from datetime import datetime
            timestamp = datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
            candles.append(Candle("forex", instrument, timeframe, timestamp,
                float(mid["o"]), float(mid["h"]), float(mid["l"]),
                float(mid["c"]), float(item.get("volume", 0))))
        return sorted(candles, key=lambda candle: candle.timestamp)

from fastapi import FastAPI
from .config import RiskConfig

app = FastAPI(title="Adaptive AI Trading System", version="0.2.0")
risk_config = RiskConfig()


@app.get("/health")
def health():
    return {"status": "ok", "mode": "paper"}


@app.get("/system")
def system_info():
    return {
        "name": "Adaptive AI Trading System",
        "version": "0.2.0",
        "mode": "paper",
        "live_trading_enabled": False,
        "market_data": {
            "crypto": "read-only CCXT adapter available (optional dependency)",
            "forex": "read-only OANDA practice adapter available (token required)",
        },
        "risk": {
            "risk_per_trade": risk_config.risk_per_trade,
            "hard_risk_cap": risk_config.hard_risk_cap,
            "daily_loss_limit": risk_config.daily_loss_limit,
            "max_drawdown": risk_config.max_drawdown,
            "max_open_positions": risk_config.max_open_positions,
            "min_confidence": risk_config.min_confidence,
            "max_leverage": risk_config.max_leverage,
        },
    }

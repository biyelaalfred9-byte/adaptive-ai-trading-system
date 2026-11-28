from datetime import datetime, timedelta, timezone

import pytest

from trading_system.protections import (
    ClosedTrade, ProtectionConfig, drawdown_protection,
    maximum_drawdown, stoploss_cooldown,
)

NOW = datetime(2026, 11, 28, 12, tzinfo=timezone.utc)


def test_stoploss_guard_locks_after_configured_losses():
    trades = [
        ClosedTrade("BTC/USDT", NOW - timedelta(hours=i + 1), -0.01, "stop_loss")
        for i in range(3)
    ]
    decision = stoploss_cooldown(
        trades, NOW, ProtectionConfig(stoploss_limit=3, lockout=timedelta(hours=6))
    )
    assert decision.blocked
    assert decision.locked_until == NOW - timedelta(hours=1) + timedelta(hours=6)


def test_stoploss_guard_can_be_pair_specific_and_ignores_old_trades():
    trades = [
        ClosedTrade("BTC/USDT", NOW - timedelta(hours=1), -.01, "stop_loss"),
        ClosedTrade("ETH/USDT", NOW - timedelta(hours=2), -.01, "stop_loss"),
        ClosedTrade("BTC/USDT", NOW - timedelta(days=2), -.01, "stop_loss"),
    ]
    decision = stoploss_cooldown(
        trades, NOW, ProtectionConfig(stoploss_limit=2), symbol="BTC/USDT"
    )
    assert not decision.blocked


def test_maximum_drawdown_and_protection():
    assert maximum_drawdown([1000, 1100, 990, 1050]) == pytest.approx(0.1)
    assert drawdown_protection([1000, 1100, 990], .1).blocked


def test_drawdown_rejects_invalid_equity():
    with pytest.raises(ValueError):
        maximum_drawdown([1000, 0])

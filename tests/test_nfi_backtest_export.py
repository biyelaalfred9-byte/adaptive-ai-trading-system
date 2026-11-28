import importlib.util
import json
import zipfile
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "research" / "analyze_nfi_backtest.py"
SPEC = importlib.util.spec_from_file_location("analyze_nfi_backtest", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_extracts_actual_trade_records_from_freqtrade_archive(tmp_path):
    result_dir = tmp_path / "backtest"
    result_dir.mkdir()
    archive_name = "backtest-result-2026-11-28_12-00-00.zip"
    payload = {
        "strategy": {
            "NostalgiaForInfinityV5": {
                "trades": [
                    {"pair": "BTC/USDT", "profit_abs": 12.5, "exit_reason": "roi"},
                    {"pair": "ETH/USDT", "profit_abs": -3.0, "exit_reason": "stop_loss"},
                ]
            }
        }
    }
    (result_dir / "backtest-result-2026-11-28_12-00-00.meta.json").write_text(
        json.dumps({"latest_backtest": archive_name})
    )
    with zipfile.ZipFile(result_dir / archive_name, "w") as archive:
        archive.writestr("backtest-result-2026-11-28_12-00-00.json", json.dumps(payload))

    archive_path, loaded, trades = MODULE.load_trade_payload(result_dir)
    assert archive_path.name == archive_name
    assert len(trades) == 2
    assert trades[0]["pair"] == "BTC/USDT"


def test_rejects_metadata_without_real_archive(tmp_path):
    result_dir = tmp_path / "backtest"
    result_dir.mkdir()
    (result_dir / "result.meta.json").write_text(
        json.dumps({"latest_backtest": "missing.zip"})
    )
    try:
        MODULE.load_trade_payload(result_dir)
    except RuntimeError as exc:
        assert "archive" in str(exc).lower()
    else:
        raise AssertionError("Expected missing archive to be rejected")

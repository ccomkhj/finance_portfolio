from datetime import date
from portfolio.accounts import save_snapshot, load_snapshot, load_all, list_sources
from portfolio.snapshot import Holding, Snapshot


def _snap(source: str) -> Snapshot:
    return Snapshot(source, date(2026, 6, 19), "1", "EUR", 100.0,
                    (Holding("IE00B4ND3602", "Gold", 1.0, 70.0, 70.0),),
                    70.0, 170.0)


def test_save_and_load(tmp_path):
    save_snapshot(tmp_path, _snap("trade_republic"))
    restored = load_snapshot(tmp_path, "trade_republic")
    assert restored == _snap("trade_republic")


def test_load_all_sorted(tmp_path):
    save_snapshot(tmp_path, _snap("trade_republic"))
    save_snapshot(tmp_path, _snap("trading_212"))
    assert [s.source for s in load_all(tmp_path)] == ["trade_republic", "trading_212"]


def test_load_all_missing_dir(tmp_path):
    assert load_all(tmp_path / "nope") == []


def test_list_sources(tmp_path):
    save_snapshot(tmp_path, _snap("trade_republic"))
    assert list_sources(tmp_path) == ["trade_republic"]

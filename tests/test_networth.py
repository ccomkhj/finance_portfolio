from datetime import date
from portfolio.config import Config, Category
from portfolio.networth import aggregate
from portfolio.snapshot import Holding, Snapshot


def _config() -> Config:
    return Config("EUR", {
        "gold": Category("gold", 0.5, ("IE00B4ND3602",)),
        "cash": Category("cash", 0.5, ()),
    })


def _snap() -> Snapshot:
    return Snapshot("trade_republic", date(2026, 6, 19), "1", "EUR", 100.0,
                    (Holding("IE00B4ND3602", "Gold", 1.0, 100.0, 100.0),),
                    100.0, 200.0)


def test_total_and_by_account():
    nw = aggregate([_snap()], _config())
    assert nw.total_eur == 200.0
    assert nw.by_account == {"trade_republic": 200.0}


def test_category_weights_and_delta():
    nw = aggregate([_snap()], _config())
    cats = {c.name: c for c in nw.categories}
    assert cats["gold"].current_eur == 100.0
    assert cats["cash"].current_eur == 100.0
    assert abs(cats["gold"].current_weight - 0.5) < 1e-9
    assert abs(cats["gold"].delta_eur) < 1e-9


def test_uncategorized_isin_flagged():
    snap = Snapshot("trade_republic", date(2026, 6, 19), "1", "EUR", 0.0,
                    (Holding("XX0000000000", "Mystery", 1.0, 50.0, 50.0),),
                    50.0, 50.0)
    nw = aggregate([snap], _config())
    assert nw.uncategorized_isins == ["XX0000000000"]
    assert any(c.name == "uncategorized" and c.current_eur == 50.0 for c in nw.categories)


def test_multi_account_sum():
    nw = aggregate([_snap(), _snap()], _config())
    assert nw.total_eur == 400.0

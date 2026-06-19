from __future__ import annotations

# tests/test_app.py
from datetime import date
import app
from portfolio.config import Config, Category
from portfolio.networth import aggregate
from portfolio.snapshot import Holding, Snapshot


def test_category_rows_shapes():
    cfg = Config("EUR", {
        "gold": Category("gold", 0.5, ("IE00B4ND3602",)),
        "cash": Category("cash", 0.5, ()),
    })
    snap = Snapshot("trade_republic", date(2026, 6, 19), "1", "EUR", 100.0,
                    (Holding("IE00B4ND3602", "Gold", 1.0, 100.0, 100.0),), 100.0, 200.0)
    nw = aggregate([snap], cfg)
    rows = app.category_rows(nw)
    names = {r["category"] for r in rows}
    assert {"gold", "cash"} <= names
    gold = next(r for r in rows if r["category"] == "gold")
    assert gold["current_eur"] == 100.0


def test_read_only_env(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_READ_ONLY", "1")
    assert app.is_read_only_mode() is True
    monkeypatch.delenv("PORTFOLIO_READ_ONLY")
    assert app.is_read_only_mode() is False


def test_rows_without_cash_drops_cash():
    cfg = Config("EUR", {
        "gold": Category("gold", 0.5, ("IE00B4ND3602",)),
        "cash": Category("cash", 0.5, ()),
    })
    snap = Snapshot("trade_republic", date(2026, 6, 19), "1", "EUR", 100.0,
                    (Holding("IE00B4ND3602", "Gold", 1.0, 100.0, 100.0),), 100.0, 200.0)
    rows = app.category_rows(aggregate([snap], cfg))
    no_cash = app.rows_without_cash(rows)
    cats = {r["category"] for r in no_cash}
    assert "cash" not in cats
    assert "gold" in cats


def test_account_holdings_rows_categorizes_and_sorts():
    cfg = Config("EUR", {"gold": Category("gold", 1.0, ("IE00B4ND3602",))})
    snap = Snapshot("trade_republic", date(2026, 6, 19), "1", "EUR", 0.0,
                    (Holding("XX0000000000", "Mystery", 1.0, 5.0, 50.0),
                     Holding("IE00B4ND3602", "Gold", 1.0, 70.0, 400.0)), 450.0, 450.0)
    rows = app._account_holdings_rows(cfg, snap)
    assert rows[0]["isin"] == "IE00B4ND3602"  # sorted by value desc
    assert rows[0]["category"] == "gold"
    assert rows[1]["category"] == "uncategorized"


def test_removable_categories():
    cfg = Config("EUR", {
        "gold": Category("gold", 0.5, ("IE00B4ND3602",)),   # has isins → not removable
        "cash": Category("cash", 0.5, ()),                   # 50% weight → not removable
        "spare": Category("spare", 0.0, ()),                 # empty + 0% → removable
    })
    assert app.removable_categories(cfg) == ["spare"]


def test_holding_options_labels_with_category():
    cfg = Config("EUR", {
        "gold": Category("gold", 1.0, ("IE00B4ND3602",)),
    })
    snap = Snapshot("trade_republic", date(2026, 6, 19), "1", "EUR", 0.0,
                    (Holding("IE00B4ND3602", "Gold", 1.0, 70.0, 70.0),
                     Holding("XX0000000000", "Mystery", 1.0, 5.0, 5.0)), 75.0, 75.0)
    opts = app.holding_options(cfg, [snap])
    by_isin = {isin: label for label, isin in opts}
    assert "gold" in by_isin["IE00B4ND3602"]
    assert "uncategorized" in by_isin["XX0000000000"]

from __future__ import annotations

import pytest

from app import SENTINEL, build_income_rows, resolve_buy_ticker
from portfolio.income import HoldingIncome, IncomeReport, TaxConfig, compute_net
from portfolio.mutations import ValidationError


def test_build_income_rows_includes_holdings_cash_and_flags_unresolved():
    report = IncomeReport(
        holdings=[
            HoldingIncome("VOW.DE", 1000.0, 5.0, 50.0, 50.0, True, "native"),
            HoldingIncome("WEBG.DE", 2000.0, None, 0.0, 0.0, False, "unresolved"),
        ],
        cash_balance_eur=10000.0,
        cash_interest_pct=2.0,
        cash_annual_eur=200.0,
    )
    names = {"VOW.DE": "Volkswagen AG", "WEBG.DE": "Amundi Prime All World"}
    rows = build_income_rows(report, names)
    by_ticker = {r["Ticker"]: r for r in rows}

    assert by_ticker["VOW.DE"]["Name"] == "Volkswagen AG"
    assert by_ticker["VOW.DE"]["Economic €/yr"] == pytest.approx(50.0)
    assert by_ticker["VOW.DE"]["Cash €/yr"] == pytest.approx(50.0)
    assert by_ticker["WEBG.DE"]["Yield %"] == "n/a"
    assert by_ticker["WEBG.DE"]["Source"] == "unresolved"
    assert by_ticker["cash"]["Cash €/yr"] == pytest.approx(200.0)


def test_build_income_rows_net_uses_after_tax_figures():
    report = IncomeReport(
        holdings=[HoldingIncome("VOW.DE", 1000.0, 5.0, 50.0, 50.0, True, "native")],
        cash_balance_eur=0.0, cash_interest_pct=0.0, cash_annual_eur=0.0,
    )
    tax = TaxConfig(rate_pct=26.375, default_teilfreistellung="none", teilfreistellung={})
    net = compute_net(report, tax)

    rows = build_income_rows(report, {"VOW.DE": "Volkswagen AG"}, net=net)
    vow = next(r for r in rows if r["Ticker"] == "VOW.DE")
    assert vow["Economic €/yr"] == pytest.approx(50 * (1 - 0.26375))
    assert vow["Cash €/yr"] == pytest.approx(50 * (1 - 0.26375))


def test_resolve_existing_ticker_is_not_new():
    assert resolve_buy_ticker("WEBG.DE", "", SENTINEL) == ("WEBG.DE", False)


def test_resolve_sentinel_with_text_is_new_and_stripped():
    assert resolve_buy_ticker(SENTINEL, "  SXR8.DE  ", SENTINEL) == ("SXR8.DE", True)


def test_resolve_sentinel_without_text_raises():
    with pytest.raises(ValidationError):
        resolve_buy_ticker(SENTINEL, "   ", SENTINEL)


def test_app_renders_with_edit_tab(monkeypatch):
    """The app runs without exception, exposes an Edit tab, and the buy
    selectbox offers known tickers + the new-ticker sentinel."""
    from streamlit.testing.v1 import AppTest

    import app as app_module

    # Avoid live yfinance calls during the headless run.
    app_module._cached_prices.clear()
    app_module._cached_fx.clear()
    app_module._cached_names.clear()
    app_module._cached_yields.clear()
    monkeypatch.setattr(app_module, "fetch_prices", lambda tickers: {t: 1.0 for t in tickers})
    monkeypatch.setattr(app_module, "fetch_fx_eur", lambda currencies: {c: 1.0 for c in currencies})
    monkeypatch.setattr(app_module, "fetch_names", lambda tickers: {t: t for t in tickers})
    monkeypatch.setattr(app_module, "fetch_historical_fx_eur", lambda currency, d: 1.0)
    monkeypatch.setattr(app_module, "fetch_dividend_yields", lambda tickers: {t: 0.02 for t in tickers})

    at = AppTest.from_file("app.py").run(timeout=30)
    assert not at.exception

    tab_labels = [t.label for t in at.tabs]
    assert "Edit" in tab_labels and "Overview" in tab_labels

    subheaders = [s.value for s in at.subheader]
    assert any("Income estimate" in s for s in subheaders)

    ticker_box = next(s for s in at.selectbox if s.label == "Ticker")
    assert app_module.SENTINEL in ticker_box.options
    assert any(opt != app_module.SENTINEL for opt in ticker_box.options)

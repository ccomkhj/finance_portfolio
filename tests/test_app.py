from __future__ import annotations

import pytest

from app import SENTINEL, resolve_buy_ticker
from portfolio.mutations import ValidationError


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
    monkeypatch.setattr(app_module, "fetch_prices", lambda tickers: {t: 1.0 for t in tickers})
    monkeypatch.setattr(app_module, "fetch_fx_eur", lambda currencies: {c: 1.0 for c in currencies})
    monkeypatch.setattr(app_module, "fetch_names", lambda tickers: {t: t for t in tickers})
    monkeypatch.setattr(app_module, "fetch_historical_fx_eur", lambda currency, d: 1.0)

    at = AppTest.from_file("app.py").run(timeout=30)
    assert not at.exception

    tab_labels = [t.label for t in at.tabs]
    assert "Edit" in tab_labels and "Overview" in tab_labels

    ticker_box = next(s for s in at.selectbox if s.label == "Ticker")
    assert app_module.SENTINEL in ticker_box.options
    assert any(opt != app_module.SENTINEL for opt in ticker_box.options)

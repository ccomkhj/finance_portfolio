from __future__ import annotations

from datetime import date

import pytest

from portfolio.accounts import load_snapshot
from portfolio.manual import (
    account_label, create_account, delete_account, remove_holding,
    set_cash, slugify_source, upsert_holding,
)
from portfolio.mutations import ValidationError

AS_OF = date(2026, 6, 19)


def test_slugify_source():
    assert slugify_source("Trading 212") == "trading_212"
    assert slugify_source("  Commerzbank  ") == "commerzbank"
    assert slugify_source("Scalable Capital!") == "scalable_capital"


def test_account_label():
    assert account_label("trading_212") == "Trading 212"


def test_create_account_empty(tmp_path):
    snap = create_account(tmp_path, "Trading 212", as_of=AS_OF)
    assert snap.source == "trading_212"
    assert snap.cash_eur == 0.0
    assert snap.holdings == ()
    assert load_snapshot(tmp_path, "trading_212").as_of == AS_OF


def test_create_account_rejects_duplicate(tmp_path):
    create_account(tmp_path, "Trading 212", as_of=AS_OF)
    with pytest.raises(ValidationError, match="already exists"):
        create_account(tmp_path, "trading 212", as_of=AS_OF)


def test_create_account_rejects_blank(tmp_path):
    with pytest.raises(ValidationError, match="required"):
        create_account(tmp_path, "  !  ", as_of=AS_OF)


def test_set_cash_and_total(tmp_path):
    create_account(tmp_path, "Commerzbank", as_of=AS_OF)
    snap = set_cash(tmp_path, "commerzbank", 5000.0, as_of=AS_OF)
    assert snap.cash_eur == 5000.0
    assert snap.total_eur == 5000.0


def test_set_cash_negative_rejected(tmp_path):
    create_account(tmp_path, "Commerzbank", as_of=AS_OF)
    with pytest.raises(ValidationError, match=">= 0"):
        set_cash(tmp_path, "commerzbank", -1.0, as_of=AS_OF)


def test_upsert_holding_add_then_update(tmp_path):
    create_account(tmp_path, "Trading 212", as_of=AS_OF)
    upsert_holding(tmp_path, "trading_212", "US0378331005", "Apple", 1000.0, as_of=AS_OF)
    snap = upsert_holding(tmp_path, "trading_212", "US0378331005", "Apple Inc", 1200.0, as_of=AS_OF)
    assert len(snap.holdings) == 1  # updated in place, not duplicated
    h = snap.holdings[0]
    assert h.name == "Apple Inc"
    assert h.value_eur == 1200.0
    assert snap.brokerage_total_eur == 1200.0
    assert snap.total_eur == 1200.0  # cash 0


def test_upsert_holding_negative_value_rejected(tmp_path):
    create_account(tmp_path, "Trading 212", as_of=AS_OF)
    with pytest.raises(ValidationError, match=">= 0"):
        upsert_holding(tmp_path, "trading_212", "US0378331005", "Apple", -5.0, as_of=AS_OF)


def test_total_combines_cash_and_holdings(tmp_path):
    create_account(tmp_path, "Trading 212", as_of=AS_OF)
    set_cash(tmp_path, "trading_212", 500.0, as_of=AS_OF)
    snap = upsert_holding(tmp_path, "trading_212", "US0378331005", "Apple", 1000.0, as_of=AS_OF)
    assert snap.cash_eur == 500.0
    assert snap.brokerage_total_eur == 1000.0
    assert snap.total_eur == 1500.0


def test_remove_holding(tmp_path):
    create_account(tmp_path, "Trading 212", as_of=AS_OF)
    upsert_holding(tmp_path, "trading_212", "US0378331005", "Apple", 1000.0, as_of=AS_OF)
    snap = remove_holding(tmp_path, "trading_212", "US0378331005", as_of=AS_OF)
    assert snap.holdings == ()
    assert snap.total_eur == 0.0


def test_remove_missing_holding_rejected(tmp_path):
    create_account(tmp_path, "Trading 212", as_of=AS_OF)
    with pytest.raises(ValidationError, match="not found"):
        remove_holding(tmp_path, "trading_212", "XX0000000000", as_of=AS_OF)


def test_edit_missing_account_rejected(tmp_path):
    with pytest.raises(ValidationError, match="not found"):
        set_cash(tmp_path, "nope", 1.0, as_of=AS_OF)


def test_delete_account(tmp_path):
    create_account(tmp_path, "Trading 212", as_of=AS_OF)
    delete_account(tmp_path, "trading_212")
    with pytest.raises(ValidationError, match="not found"):
        set_cash(tmp_path, "trading_212", 1.0, as_of=AS_OF)

from __future__ import annotations

from datetime import date

import pytest

from portfolio.importer import normalize_action, normalize_date, normalize_number


def test_normalize_number_comma():
    assert normalize_number("1.234,56", "comma") == 1234.56
    assert normalize_number("12,5", "comma") == 12.5
    assert normalize_number("1000", "comma") == 1000.0


def test_normalize_number_dot():
    assert normalize_number("1,234.56", "dot") == 1234.56
    assert normalize_number("1234.56", "dot") == 1234.56


def test_normalize_number_bad_raises():
    with pytest.raises(ValueError):
        normalize_number("abc", "comma")
    with pytest.raises(ValueError):
        normalize_number("", "comma")
    with pytest.raises(ValueError):
        normalize_number("1.0", "klingon")


def test_normalize_date_formats():
    assert normalize_date("2026-04-19", "%Y-%m-%d") == date(2026, 4, 19)
    assert normalize_date("19.04.2026", "%d.%m.%Y") == date(2026, 4, 19)


def test_normalize_date_auto():
    assert normalize_date("2026-04-19", "auto") == date(2026, 4, 19)
    assert normalize_date("19.04.2026", "auto") == date(2026, 4, 19)
    with pytest.raises(ValueError):
        normalize_date("not-a-date", "auto")


def test_normalize_action():
    actions = {"kauf": "buy", "verkauf": "sell"}
    assert normalize_action("Kauf", actions) == "buy"
    assert normalize_action(" VERKAUF ", actions) == "sell"
    assert normalize_action("dividend", actions) is None

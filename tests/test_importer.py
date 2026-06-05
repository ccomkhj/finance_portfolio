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


from portfolio.importer import ImportProfile, ParsedRow, parse_rows


def _profile(**over):
    base = dict(
        columns={"date": "Datum", "isin": "ISIN", "action": "Typ",
                 "quantity": "Anzahl", "price": "Kurs", "currency": "Waehrung"},
        decimal="comma",
        date_format="%d.%m.%Y",
        actions={"kauf": "buy", "verkauf": "sell"},
    )
    base.update(over)
    return ImportProfile.from_dict(base)


def test_import_profile_roundtrip():
    p = _profile()
    d = p.to_dict()
    assert ImportProfile.from_dict(d) == p
    assert d["actions"] == {"kauf": "buy", "verkauf": "sell"}


def test_parse_rows_happy():
    recs = [{"Datum": "19.04.2026", "ISIN": "IE00X", "Typ": "Kauf",
             "Anzahl": "2,5", "Kurs": "1.234,56", "Waehrung": "EUR"}]
    rows, errors = parse_rows(recs, _profile())
    assert errors == []
    assert rows == [ParsedRow(0, __import__("datetime").date(2026, 4, 19),
                              "IE00X", "buy", 2.5, 1234.56, "EUR")]


def test_parse_rows_currency_defaults_eur_when_unmapped():
    p = _profile(columns={"date": "Datum", "isin": "ISIN", "action": "Typ",
                          "quantity": "Anzahl", "price": "Kurs"})
    recs = [{"Datum": "19.04.2026", "ISIN": "IE00X", "Typ": "Kauf",
             "Anzahl": "1", "Kurs": "10,0"}]
    rows, errors = parse_rows(recs, p)
    assert errors == []
    assert rows[0].currency == "EUR"


def test_parse_rows_collects_errors_with_row_numbers():
    recs = [
        {"Datum": "bad", "ISIN": "IE00X", "Typ": "Kauf", "Anzahl": "1", "Kurs": "10,0", "Waehrung": "EUR"},
        {"Datum": "19.04.2026", "ISIN": "IE00Y", "Typ": "Dividende", "Anzahl": "1", "Kurs": "10,0", "Waehrung": "EUR"},
        {"Datum": "19.04.2026", "ISIN": "", "Typ": "Kauf", "Anzahl": "1", "Kurs": "10,0", "Waehrung": "EUR"},
        {"Datum": "19.04.2026", "ISIN": "IE00Z", "Typ": "Kauf", "Anzahl": "0", "Kurs": "10,0", "Waehrung": "EUR"},
    ]
    rows, errors = parse_rows(recs, _profile())
    assert rows == []
    assert len(errors) == 4
    assert errors[0].startswith("row 1:")
    assert "unknown action" in errors[1]
    assert "ISIN" in errors[2]
    assert "quantity" in errors[3]

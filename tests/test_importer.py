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
    assert rows == [ParsedRow(0, date(2026, 4, 19),
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


from datetime import date as _date

from portfolio.importer import ResolvedRow, dedupe_key, resolve_tickers, split_new


def _parsed(i, isin, action="buy", qty=1.0, price=10.0):
    return ParsedRow(i, _date(2026, 4, 19), isin, action, qty, price, "EUR")


def test_resolve_tickers_maps_and_collects_unknowns_in_order():
    rows = [_parsed(0, "IE00A"), _parsed(1, "IE00B"), _parsed(2, "IE00A"), _parsed(3, "IE00C")]
    resolved, unknown = resolve_tickers(rows, {"IE00A": "AAA.DE"})
    assert unknown == ["IE00B", "IE00C"]
    assert [r.ticker for r in resolved] == ["AAA.DE", "AAA.DE"]
    assert resolved[0].isin == "IE00A"


def test_split_new_skips_existing_and_within_batch_dups():
    r1 = ResolvedRow(0, _date(2026, 4, 19), "IE00A", "AAA.DE", "buy", 1.0, 10.0, "EUR")
    r2 = ResolvedRow(1, _date(2026, 4, 19), "IE00A", "AAA.DE", "buy", 1.0, 10.0, "EUR")  # dup of r1
    r3 = ResolvedRow(2, _date(2026, 4, 20), "IE00A", "AAA.DE", "buy", 2.0, 10.0, "EUR")
    existing = {dedupe_key(_date(2026, 4, 18), "AAA.DE", "buy", 5.0, 9.0)}
    new, dups = split_new([r1, r2, r3], existing)
    assert [r.source_index for r in new] == [0, 2]
    assert [r.source_index for r in dups] == [1]


def test_split_new_detects_existing_match():
    r = ResolvedRow(0, _date(2026, 4, 18), "AAA.DE", "AAA.DE", "buy", 5.0, 9.0, "EUR")
    existing = {dedupe_key(_date(2026, 4, 18), "AAA.DE", "buy", 5.0, 9.0)}
    new, dups = split_new([r], existing)
    assert new == []
    assert dups == [r]


def test_normalize_number_thousands_only_is_locale_assumption():
    # In comma mode a dot is always thousands; in dot mode a comma is always thousands.
    assert normalize_number("1.234", "comma") == 1234.0
    assert normalize_number("1,234", "dot") == 1234.0


def test_parse_rows_rejects_nonpositive_price():
    recs = [{"Datum": "19.04.2026", "ISIN": "IE00X", "Typ": "Kauf",
             "Anzahl": "1", "Kurs": "0,0", "Waehrung": "EUR"}]
    rows, errors = parse_rows(recs, _profile())
    assert rows == []
    assert len(errors) == 1 and "price" in errors[0]

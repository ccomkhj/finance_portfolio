# tests/test_trade_republic.py
from pathlib import Path
import pytest
from portfolio.sources.trade_republic import ParseError, parse_lines, parse

FIXTURE = Path(__file__).parent / "fixtures" / "trade_republic_networth.txt"
REAL_PDF = Path(__file__).parent / "fixtures" / "trade_republic_networth.pdf"


def _lines() -> list[str]:
    return [ln for ln in FIXTURE.read_text().splitlines() if ln.strip()]


def test_parses_header():
    s = parse_lines(_lines())
    assert s.source == "trade_republic"
    assert s.as_of.isoformat() == "2026-01-15"
    assert s.account_ref == "1234567890"
    assert s.currency == "EUR"


def test_parses_totals_and_cash():
    s = parse_lines(_lines())
    assert s.cash_eur == 3000.00
    assert s.brokerage_total_eur == 2000.00
    assert s.total_eur == 5000.00


def test_parses_holdings():
    s = parse_lines(_lines())
    assert len(s.holdings) == 3
    by_isin = {h.isin: h for h in s.holdings}
    gold = by_isin["IE00B4ND3602"]
    assert gold.name == "iShares Physical Gold"
    assert gold.quantity == 5.0
    assert gold.price == 60.00
    assert gold.value_eur == 300.00
    world = by_isin["IE00B4L5Y983"]
    assert world.quantity == 10.0
    assert world.value_eur == 900.00


def test_integrity_count_mismatch():
    lines = _lines()
    patched = ["ANZAHL POSITIONEN: 8" if "ANZAHL POSITIONEN" in ln else ln for ln in lines]
    with pytest.raises(ParseError, match="position count"):
        parse_lines(patched)


def test_integrity_total_mismatch():
    lines = [ln.replace("5.000,00", "9.999,99") for ln in _lines()]
    with pytest.raises(ParseError, match="total"):
        parse_lines(lines)


def test_not_a_tr_document():
    with pytest.raises(ParseError):
        parse_lines(["Some random invoice", "Total: 5,00 EUR"])


@pytest.mark.skipif(not REAL_PDF.exists(), reason="real PDF not present (gitignored)")
def test_real_pdf_end_to_end():
    s = parse(REAL_PDF)
    assert len(s.holdings) == 9
    assert s.total_eur > 0

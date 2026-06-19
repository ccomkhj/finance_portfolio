from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pdfplumber

from portfolio.numbers import normalize_number
from portfolio.snapshot import Holding, Snapshot

SOURCE = "trade_republic"
TOLERANCE_PER_HOLDING = 0.05

_NUM = r"[\d.]+,\d+"            # German amount, always has a comma-decimal
_QTY = r"[\d.]*,?\d+"           # quantity: "5,506607" or "42"

_DATUM = re.compile(r"DATUM\s+(\d{2}\.\d{2}\.\d{4})")
_DEPOT = re.compile(r"DEPOT\s+(\d+)")
_BROKERAGE = re.compile(rf"^Brokerage\s+(?P<v>{_NUM})$")
_GESAMT = re.compile(rf"^GESAMT\s+(?P<v>{_NUM})\s*EUR$")
_CASHKONTO = re.compile(rf"^Cashkonto\s+(?P<v>{_NUM})\s*EUR$")
_COUNT = re.compile(r"ANZAHL POSITIONEN:\s*(\d+)")
_ISIN = re.compile(r"ISIN:\s*([A-Z]{2}[A-Z0-9]{9}\d)")
_HOLDING = re.compile(
    rf"^(?P<qty>{_QTY})\s+Stk\.\s+(?P<name>.+?)\s+(?P<price>{_NUM})\s+(?P<value>{_NUM})$"
)


class ParseError(ValueError):
    """Raised when a PDF is not a parseable TR net-worth statement, or fails an
    integrity check."""


def extract_lines(pdf_source: Any) -> list[str]:
    lines: list[str] = []
    with pdfplumber.open(pdf_source) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for ln in text.splitlines():
                stripped = ln.strip()
                if stripped:
                    lines.append(stripped)
    return lines


def _search(lines: list[str], pattern: re.Pattern[str], label: str) -> re.Match[str]:
    for ln in lines:
        m = pattern.search(ln)
        if m:
            return m
    raise ParseError(f"could not find {label}")


def parse_lines(lines: list[str]) -> Snapshot:
    if not any("VERMÖGENSÜBERSICHT" in ln or "DEPOT" in ln for ln in lines):
        raise ParseError("not a Trade Republic net-worth statement")

    as_of = datetime.strptime(
        _search(lines, _DATUM, "DATUM").group(1), "%d.%m.%Y"
    ).date()
    account_ref = _search(lines, _DEPOT, "DEPOT").group(1)

    brokerage = normalize_number(_search(lines, _BROKERAGE, "Brokerage total").group("v"))
    total = normalize_number(_search(lines, _GESAMT, "GESAMT total").group("v"))
    cash = normalize_number(_search(lines, _CASHKONTO, "Cashkonto").group("v"))

    count_m = _COUNT.search("\n".join(lines))
    if not count_m:
        raise ParseError("could not find ANZAHL POSITIONEN")
    declared_count = int(count_m.group(1))

    holdings = _parse_holdings(lines)

    # --- integrity checks ---
    if len(holdings) != declared_count:
        raise ParseError(
            f"position count mismatch: parsed {len(holdings)}, declared {declared_count}"
        )
    if not holdings:
        raise ParseError("no holdings parsed")
    hv = sum(h.value_eur for h in holdings)
    if abs(hv - brokerage) > TOLERANCE_PER_HOLDING * max(len(holdings), 1):
        raise ParseError(
            f"brokerage subtotal mismatch: holdings sum {hv:.2f} vs reported {brokerage:.2f}"
        )
    if abs(brokerage + cash - total) > TOLERANCE_PER_HOLDING:
        raise ParseError(
            f"total mismatch: brokerage {brokerage:.2f} + cash {cash:.2f} != GESAMT {total:.2f}"
        )

    return Snapshot(
        source=SOURCE,
        as_of=as_of,
        account_ref=account_ref,
        currency="EUR",
        cash_eur=cash,
        holdings=tuple(holdings),
        brokerage_total_eur=brokerage,
        total_eur=total,
    )


def _parse_holdings(lines: list[str]) -> list[Holding]:
    holdings: list[Holding] = []
    pending: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal pending
        if pending is not None:
            if "isin" not in pending:
                raise ParseError(f"holding {pending['name']!r} has no ISIN")
            holdings.append(Holding(
                isin=pending["isin"], name=pending["name"],
                quantity=pending["quantity"], price=pending["price"],
                value_eur=pending["value_eur"],
            ))
            pending = None

    for ln in lines:
        m = _HOLDING.match(ln)
        if m:
            flush()
            pending = {
                "quantity": normalize_number(m.group("qty")),
                "name": m.group("name").strip(),
                "price": normalize_number(m.group("price")),
                "value_eur": normalize_number(m.group("value")),
            }
            continue
        if pending is not None and "isin" not in pending:
            im = _ISIN.search(ln)
            if im:
                pending["isin"] = im.group(1)
    flush()
    return holdings


def parse(pdf_source: Any) -> Snapshot:
    return parse_lines(extract_lines(pdf_source))

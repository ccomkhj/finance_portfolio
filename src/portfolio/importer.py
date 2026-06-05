from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


def normalize_number(raw: str, decimal: str) -> float:
    s = str(raw).strip().replace(" ", "")
    if not s:
        raise ValueError("empty number")
    if decimal == "comma":
        s = s.replace(".", "").replace(",", ".")
    elif decimal == "dot":
        s = s.replace(",", "")
    else:
        raise ValueError(f"unknown decimal style {decimal!r}")
    return float(s)


_AUTO_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y")


def normalize_date(raw: str, fmt: str) -> date:
    s = str(raw).strip()
    if fmt == "auto":
        for f in _AUTO_DATE_FORMATS:
            try:
                return datetime.strptime(s, f).date()
            except ValueError:
                continue
        raise ValueError(f"unrecognized date {raw!r}")
    return datetime.strptime(s, fmt).date()


def normalize_action(raw: str, actions: dict[str, str]) -> str | None:
    return actions.get(str(raw).strip().lower())


VALID_CURRENCIES = {"EUR", "USD"}


@dataclass(frozen=True)
class ImportProfile:
    columns: dict[str, str]
    decimal: str
    date_format: str
    actions: dict[str, str]

    @classmethod
    def from_dict(cls, d: dict) -> "ImportProfile":
        return cls(
            columns=dict(d["columns"]),
            decimal=d["decimal"],
            date_format=d["date_format"],
            actions={str(k).lower(): v for k, v in (d.get("actions") or {}).items()},
        )

    def to_dict(self) -> dict:
        return {
            "columns": dict(self.columns),
            "decimal": self.decimal,
            "date_format": self.date_format,
            "actions": dict(self.actions),
        }


@dataclass(frozen=True)
class ParsedRow:
    source_index: int
    date: date
    isin: str
    action: str
    quantity: float
    price: float
    currency: str


def parse_rows(
    records: list[dict[str, str]], profile: ImportProfile
) -> tuple[list[ParsedRow], list[str]]:
    rows: list[ParsedRow] = []
    errors: list[str] = []
    cols = profile.columns
    for i, rec in enumerate(records):
        try:
            isin = str(rec.get(cols["isin"], "")).strip()
            if not isin:
                raise ValueError("missing ISIN")
            d = normalize_date(rec.get(cols["date"], ""), profile.date_format)
            action = normalize_action(rec.get(cols["action"], ""), profile.actions)
            if action is None:
                raise ValueError(f"unknown action {rec.get(cols['action'], '')!r}")
            qty = normalize_number(rec.get(cols["quantity"], ""), profile.decimal)
            price = normalize_number(rec.get(cols["price"], ""), profile.decimal)
            ccol = cols.get("currency")
            cval = str(rec.get(ccol, "")).strip() if ccol else ""
            currency = cval.upper() if cval else "EUR"
            if currency not in VALID_CURRENCIES:
                raise ValueError(f"invalid currency {currency!r}")
            if qty <= 0:
                raise ValueError(f"quantity must be > 0, got {qty}")
            if price <= 0:
                raise ValueError(f"price must be > 0, got {price}")
            rows.append(ParsedRow(i, d, isin, action, qty, price, currency))
        except (ValueError, KeyError) as e:
            errors.append(f"row {i + 1}: {e}")
    return rows, errors


@dataclass(frozen=True)
class ResolvedRow:
    source_index: int
    date: date
    isin: str
    ticker: str
    action: str
    quantity: float
    price: float
    currency: str


def resolve_tickers(
    rows: list[ParsedRow], isin_map: dict[str, str]
) -> tuple[list[ResolvedRow], list[str]]:
    resolved: list[ResolvedRow] = []
    unknown: list[str] = []
    seen_unknown: set[str] = set()
    for r in rows:
        ticker = isin_map.get(r.isin)
        if ticker is None:
            if r.isin not in seen_unknown:
                seen_unknown.add(r.isin)
                unknown.append(r.isin)
            continue
        resolved.append(
            ResolvedRow(r.source_index, r.date, r.isin, ticker,
                        r.action, r.quantity, r.price, r.currency)
        )
    return resolved, unknown


def dedupe_key(
    d: date, ticker: str, action: str, quantity: float, price: float
) -> tuple:
    return (d.isoformat(), ticker, action, round(quantity, 8), round(price, 8))


def split_new(
    rows: list[ResolvedRow], existing_keys: set[tuple]
) -> tuple[list[ResolvedRow], list[ResolvedRow]]:
    new: list[ResolvedRow] = []
    duplicates: list[ResolvedRow] = []
    seen = set(existing_keys)
    for r in rows:
        k = dedupe_key(r.date, r.ticker, r.action, r.quantity, r.price)
        if k in seen:
            duplicates.append(r)
        else:
            seen.add(k)
            new.append(r)
    return new, duplicates

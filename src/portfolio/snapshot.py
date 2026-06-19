from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Holding:
    isin: str
    name: str
    quantity: float
    price: float
    value_eur: float


@dataclass(frozen=True)
class Snapshot:
    source: str
    as_of: date
    account_ref: str
    currency: str
    cash_eur: float
    holdings: tuple[Holding, ...]
    brokerage_total_eur: float
    total_eur: float

    @property
    def holdings_total_eur(self) -> float:
        return sum(h.value_eur for h in self.holdings)


def snapshot_to_dict(s: Snapshot) -> dict[str, Any]:
    return {
        "source": s.source,
        "as_of": s.as_of.isoformat(),
        "account_ref": s.account_ref,
        "currency": s.currency,
        "cash_eur": s.cash_eur,
        "holdings": [
            {"isin": h.isin, "name": h.name, "quantity": h.quantity,
             "price": h.price, "value_eur": h.value_eur}
            for h in s.holdings
        ],
        "brokerage_total_eur": s.brokerage_total_eur,
        "total_eur": s.total_eur,
    }


def snapshot_from_dict(d: dict[str, Any]) -> Snapshot:
    return Snapshot(
        source=d["source"],
        as_of=date.fromisoformat(d["as_of"]),
        account_ref=d["account_ref"],
        currency=d["currency"],
        cash_eur=float(d["cash_eur"]),
        holdings=tuple(
            Holding(h["isin"], h["name"], float(h["quantity"]),
                    float(h["price"]), float(h["value_eur"]))
            for h in d["holdings"]
        ),
        brokerage_total_eur=float(d["brokerage_total_eur"]),
        total_eur=float(d["total_eur"]),
    )

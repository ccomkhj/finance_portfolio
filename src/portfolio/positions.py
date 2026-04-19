from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date as Date

import pandas as pd


@dataclass(frozen=True)
class Position:
    ticker: str
    quantity: float
    avg_cost_eur: float
    currency: str


def enrich_transactions_with_eur(
    df: pd.DataFrame,
    historical_fx: Callable[[str, Date], float],
) -> pd.DataFrame:
    """Add a `cost_eur` column = quantity * price * FX(date).

    For EUR rows, FX = 1.0. For USD rows, `historical_fx("USD", date)` is called to
    obtain USD->EUR (i.e., how many EUR per 1 USD on that date).
    """
    def row_cost(row: pd.Series) -> float:
        if row["currency"] == "EUR":
            rate = 1.0
        else:
            rate = historical_fx(row["currency"], row["date"].date())
        return row["quantity"] * row["price"] * rate

    out = df.copy()
    out["cost_eur"] = out.apply(row_cost, axis=1)
    return out


def compute_positions(transactions: pd.DataFrame) -> list[Position]:
    """Collapse buy/sell transactions into current positions using avg-cost basis."""
    if "cost_eur" not in transactions.columns:
        raise ValueError("transactions DataFrame must include a 'cost_eur' column")

    state: dict[str, dict] = {}
    for _, row in transactions.sort_values("date").iterrows():
        ticker = row["ticker"]
        s = state.setdefault(ticker, {
            "quantity": 0.0, "cost_eur": 0.0, "currency": row["currency"]
        })

        if row["action"] == "buy":
            s["quantity"] += row["quantity"]
            s["cost_eur"] += row["cost_eur"]
        elif row["action"] == "sell":
            if row["quantity"] > s["quantity"] + 1e-9:
                raise ValueError(
                    f"sell of {row['quantity']} {ticker} exceeds held {s['quantity']}"
                )
            avg = s["cost_eur"] / s["quantity"] if s["quantity"] else 0.0
            s["quantity"] -= row["quantity"]
            s["cost_eur"] -= avg * row["quantity"]
        else:
            raise ValueError(f"unknown action {row['action']!r}")

    positions: list[Position] = []
    for ticker, s in state.items():
        if s["quantity"] <= 1e-9:
            continue
        avg_cost = s["cost_eur"] / s["quantity"]
        positions.append(Position(
            ticker=ticker,
            quantity=s["quantity"],
            avg_cost_eur=avg_cost,
            currency=s["currency"],
        ))
    return positions

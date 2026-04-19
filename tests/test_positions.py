from datetime import date as Date

import pandas as pd
import pytest

from portfolio.positions import (
    Position,
    compute_positions,
    enrich_transactions_with_eur,
)


def tx_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_compute_positions_single_buy() -> None:
    df = tx_df([
        {"date": "2026-01-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 10.0, "price": 98.50, "currency": "EUR", "cost_eur": 985.0},
    ])

    positions = compute_positions(df)

    assert positions == [
        Position(ticker="VWCE.DE", quantity=10.0, avg_cost_eur=98.50, currency="EUR")
    ]


def test_compute_positions_multiple_buys_weighted_average() -> None:
    df = tx_df([
        {"date": "2026-01-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 10.0, "price": 98.50, "currency": "EUR", "cost_eur": 985.0},
        {"date": "2026-02-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 10.0, "price": 101.50, "currency": "EUR", "cost_eur": 1015.0},
    ])

    [pos] = compute_positions(df)

    assert pos.quantity == 20.0
    assert pos.avg_cost_eur == pytest.approx(100.0)


def test_compute_positions_partial_sell_keeps_avg_cost() -> None:
    df = tx_df([
        {"date": "2026-01-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 10.0, "price": 100.0, "currency": "EUR", "cost_eur": 1000.0},
        {"date": "2026-02-15", "ticker": "VWCE.DE", "action": "sell",
         "quantity": 3.0, "price": 120.0, "currency": "EUR", "cost_eur": 360.0},
    ])

    [pos] = compute_positions(df)

    assert pos.quantity == 7.0
    assert pos.avg_cost_eur == pytest.approx(100.0)


def test_compute_positions_full_sell_removes_position() -> None:
    df = tx_df([
        {"date": "2026-01-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 10.0, "price": 100.0, "currency": "EUR", "cost_eur": 1000.0},
        {"date": "2026-02-15", "ticker": "VWCE.DE", "action": "sell",
         "quantity": 10.0, "price": 120.0, "currency": "EUR", "cost_eur": 1200.0},
    ])

    assert compute_positions(df) == []


def test_compute_positions_rejects_oversell() -> None:
    df = tx_df([
        {"date": "2026-01-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 5.0, "price": 100.0, "currency": "EUR", "cost_eur": 500.0},
        {"date": "2026-02-15", "ticker": "VWCE.DE", "action": "sell",
         "quantity": 10.0, "price": 120.0, "currency": "EUR", "cost_eur": 1200.0},
    ])

    with pytest.raises(ValueError, match="exceeds held"):
        compute_positions(df)


def test_enrich_transactions_with_eur_uses_fx_for_usd() -> None:
    df = tx_df([
        {"date": "2026-01-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 10.0, "price": 100.0, "currency": "EUR"},
        {"date": "2026-02-03", "ticker": "AAPL", "action": "buy",
         "quantity": 5.0, "price": 200.0, "currency": "USD"},
    ])
    fx_table = {("USD", Date(2026, 2, 3)): 0.92}
    out = enrich_transactions_with_eur(df, lambda c, d: fx_table[(c, d)])

    assert out.loc[0, "cost_eur"] == pytest.approx(1000.0)
    assert out.loc[1, "cost_eur"] == pytest.approx(5 * 200 * 0.92)

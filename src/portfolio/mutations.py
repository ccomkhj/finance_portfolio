from __future__ import annotations

from datetime import date as Date
from pathlib import Path

import yaml

from portfolio.config import load_config
from portfolio.positions import compute_positions, enrich_transactions_with_eur
from portfolio.transactions import Transaction, append_transaction, load_transactions


class ValidationError(ValueError):
    """Raised when a mutation is rejected before any file is written."""


def record_transaction(
    *,
    tx_path: Path,
    config_path: Path,
    tx_date: Date,
    ticker: str,
    action: str,
    quantity: float,
    price: float,
    currency: str,
) -> None:
    config = load_config(config_path)
    if ticker not in config.all_tickers():
        raise ValidationError(
            f"ticker {ticker!r} not in config. Add it to a category first."
        )
    if action == "sell":
        _assert_sell_within_holding(tx_path, ticker, quantity)

    tx = Transaction(
        date=tx_date,
        ticker=ticker,
        action=action,
        quantity=quantity,
        price=price,
        currency=currency,
    )
    try:
        append_transaction(tx_path, tx)
    except ValueError as e:
        raise ValidationError(str(e)) from e


def _assert_sell_within_holding(tx_path: Path, ticker: str, quantity: float) -> None:
    tx_df = load_transactions(tx_path)
    enriched = enrich_transactions_with_eur(tx_df, lambda _c, _d: 1.0)
    positions = compute_positions(enriched)
    held = next((p.quantity for p in positions if p.ticker == ticker), 0.0)
    if quantity > held + 1e-9:
        raise ValidationError(
            f"sell of {quantity} {ticker} exceeds held {held}"
        )


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


def set_cash(config_path: Path, amount_eur: float) -> None:
    if amount_eur < 0:
        raise ValidationError(f"cash_balance_eur must be >= 0, got {amount_eur}")
    data = _read_yaml(config_path)
    data["cash_balance_eur"] = float(amount_eur)
    _write_yaml(config_path, data)

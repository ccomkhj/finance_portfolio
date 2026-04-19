from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = ["date", "ticker", "action", "quantity", "price", "currency"]
VALID_ACTIONS = {"buy", "sell"}
VALID_CURRENCIES = {"EUR", "USD"}


@dataclass(frozen=True)
class Transaction:
    date: date
    ticker: str
    action: str
    quantity: float
    price: float
    currency: str


def load_transactions(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"ticker": str, "action": str, "currency": str})

    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"transactions.csv missing columns: {sorted(missing)}")

    df = df[REQUIRED_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="raise").astype("datetime64[ns]")
    df["quantity"] = df["quantity"].astype(float)
    df["price"] = df["price"].astype(float)

    _validate_rows(df)
    return df


def _validate_rows(df: pd.DataFrame) -> None:
    bad_actions = df.loc[~df["action"].isin(VALID_ACTIONS)]
    if not bad_actions.empty:
        row = bad_actions.iloc[0]
        raise ValueError(f"row {row.name}: invalid action {row['action']!r}")

    bad_currencies = df.loc[~df["currency"].isin(VALID_CURRENCIES)]
    if not bad_currencies.empty:
        row = bad_currencies.iloc[0]
        raise ValueError(f"row {row.name}: invalid currency {row['currency']!r}")

    bad_qty = df.loc[df["quantity"] <= 0]
    if not bad_qty.empty:
        row = bad_qty.iloc[0]
        raise ValueError(f"row {row.name}: quantity must be > 0, got {row['quantity']}")

    bad_price = df.loc[df["price"] <= 0]
    if not bad_price.empty:
        row = bad_price.iloc[0]
        raise ValueError(f"row {row.name}: price must be > 0, got {row['price']}")


def append_transaction(path: Path, tx: Transaction) -> None:
    """Append a transaction row atomically (write temp file, fsync, rename)."""
    if tx.action not in VALID_ACTIONS:
        raise ValueError(f"invalid action {tx.action!r}")
    if tx.currency not in VALID_CURRENCIES:
        raise ValueError(f"invalid currency {tx.currency!r}")
    if tx.quantity <= 0 or tx.price <= 0:
        raise ValueError("quantity and price must be > 0")

    existing = path.read_text() if path.exists() else "date,ticker,action,quantity,price,currency\n"
    new_row = (
        f"{tx.date.isoformat()},{tx.ticker},{tx.action},"
        f"{tx.quantity},{tx.price},{tx.currency}\n"
    )

    dir_ = path.parent
    dir_.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dir_, prefix=".transactions.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as tmp:
            tmp.write(existing + new_row)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    except Exception:
        if Path(tmp_name).exists():
            os.unlink(tmp_name)
        raise

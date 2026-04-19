from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from portfolio.transactions import Transaction, append_transaction, load_transactions

CSV_HEADER = "date,ticker,action,quantity,price,currency\n"


def write_csv(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "transactions.csv"
    path.write_text(CSV_HEADER + rows)
    return path


def test_load_transactions_parses_types(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        "2026-01-15,VWCE.DE,buy,10,98.50,EUR\n"
        "2026-02-03,AAPL,buy,5.5,185.20,USD\n",
    )

    df = load_transactions(path)

    assert list(df.columns) == ["date", "ticker", "action", "quantity", "price", "currency"]
    assert df["date"].dtype == "datetime64[ns]"
    assert df.loc[0, "date"] == pd.Timestamp("2026-01-15")
    assert df.loc[1, "quantity"] == 5.5
    assert df.loc[1, "currency"] == "USD"


def test_load_transactions_rejects_bad_action(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "2026-01-15,VWCE.DE,hold,10,98.50,EUR\n")
    with pytest.raises(ValueError, match="invalid action 'hold'"):
        load_transactions(path)


def test_load_transactions_rejects_bad_currency(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "2026-01-15,VWCE.DE,buy,10,98.50,GBP\n")
    with pytest.raises(ValueError, match="invalid currency 'GBP'"):
        load_transactions(path)


def test_load_transactions_rejects_nonpositive_quantity(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "2026-01-15,VWCE.DE,buy,0,98.50,EUR\n")
    with pytest.raises(ValueError, match="quantity must be > 0"):
        load_transactions(path)


def test_append_transaction_creates_file_with_header(tmp_path: Path) -> None:
    path = tmp_path / "transactions.csv"
    tx = Transaction(
        date=date(2026, 1, 15),
        ticker="VWCE.DE",
        action="buy",
        quantity=10.0,
        price=98.50,
        currency="EUR",
    )
    append_transaction(path, tx)

    content = path.read_text()
    assert content == (
        "date,ticker,action,quantity,price,currency\n"
        "2026-01-15,VWCE.DE,buy,10.0,98.5,EUR\n"
    )


def test_append_transaction_preserves_existing_rows(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "2026-01-15,VWCE.DE,buy,10,98.50,EUR\n")
    tx = Transaction(
        date=date(2026, 2, 3),
        ticker="AAPL",
        action="buy",
        quantity=5.0,
        price=185.20,
        currency="USD",
    )
    append_transaction(path, tx)

    df = load_transactions(path)
    assert len(df) == 2
    assert df.iloc[1]["ticker"] == "AAPL"

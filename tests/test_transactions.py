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


def test_load_transactions_rejects_nonpositive_price(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "2026-01-15,VWCE.DE,buy,10,0,EUR\n")
    with pytest.raises(ValueError, match="price must be > 0"):
        load_transactions(path)


def test_load_transactions_rejects_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "transactions.csv"
    path.write_text("date,ticker,action,quantity,price\n2026-01-15,VWCE.DE,buy,10,98.50\n")
    with pytest.raises(ValueError, match="missing columns: \\['currency'\\]"):
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


def _tx(**overrides) -> Transaction:
    base = dict(
        date=date(2026, 1, 15),
        ticker="VWCE.DE",
        action="buy",
        quantity=10.0,
        price=98.50,
        currency="EUR",
    )
    base.update(overrides)
    return Transaction(**base)


def test_append_transaction_rejects_bad_action(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid action 'hold'"):
        append_transaction(tmp_path / "transactions.csv", _tx(action="hold"))


def test_append_transaction_rejects_bad_currency(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid currency 'GBP'"):
        append_transaction(tmp_path / "transactions.csv", _tx(currency="GBP"))


def test_append_transaction_rejects_nonpositive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="quantity and price must be > 0"):
        append_transaction(tmp_path / "transactions.csv", _tx(quantity=0.0))


def test_append_transaction_cleans_up_temp_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "transactions.csv"

    def boom(_src: str, _dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("portfolio.transactions.os.replace", boom)

    with pytest.raises(OSError, match="disk full"):
        append_transaction(path, _tx())

    # The destination was never written and no stray temp file is left behind.
    assert not path.exists()
    assert list(tmp_path.glob(".transactions.*.tmp")) == []


def test_append_transactions_writes_all_rows(tmp_path):
    from datetime import date
    from portfolio.transactions import Transaction, append_transactions, load_transactions

    path = tmp_path / "tx.csv"
    txs = [
        Transaction(date(2026, 4, 19), "AAA.DE", "buy", 1.0, 10.0, "EUR"),
        Transaction(date(2026, 4, 20), "BBB.DE", "sell", 2.0, 20.0, "EUR"),
    ]
    append_transactions(path, txs)
    df = load_transactions(path)
    assert list(df["ticker"]) == ["AAA.DE", "BBB.DE"]
    assert list(df["action"]) == ["buy", "sell"]


def test_append_transactions_empty_is_noop(tmp_path):
    from portfolio.transactions import append_transactions

    path = tmp_path / "tx.csv"
    append_transactions(path, [])
    assert not path.exists()


def test_append_transactions_rejects_invalid_before_writing(tmp_path):
    from datetime import date
    import pytest
    from portfolio.transactions import Transaction, append_transactions

    path = tmp_path / "tx.csv"
    txs = [
        Transaction(date(2026, 4, 19), "AAA.DE", "buy", 1.0, 10.0, "EUR"),
        Transaction(date(2026, 4, 20), "BBB.DE", "buy", -2.0, 20.0, "EUR"),  # invalid qty
    ]
    with pytest.raises(ValueError):
        append_transactions(path, txs)
    assert not path.exists()  # nothing written

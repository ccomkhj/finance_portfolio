from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from portfolio.mutations import (
    ValidationError,
    record_transaction,
    set_cash,
)
from portfolio.config import load_config


CONFIG_YAML = """\
base_currency: EUR
categories:
  core-etf:
    target_weight: 0.6
    tickers:
      - WEBG.DE
  bonds:
    target_weight: 0.3
    tickers:
      - EUNA.DE
  cash:
    target_weight: 0.1
    tickers: []
cash_balance_eur: 1000.0
"""

TX_CSV = "date,ticker,action,quantity,price,currency\n"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    (tmp_path / "config.yaml").write_text(CONFIG_YAML)
    (tmp_path / "transactions.csv").write_text(TX_CSV)
    return tmp_path


def test_record_transaction_buy_appends_row(data_dir: Path) -> None:
    record_transaction(
        tx_path=data_dir / "transactions.csv",
        config_path=data_dir / "config.yaml",
        tx_date=date(2026, 4, 19),
        ticker="WEBG.DE",
        action="buy",
        quantity=10.0,
        price=12.5,
        currency="EUR",
    )
    df = pd.read_csv(data_dir / "transactions.csv")
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "WEBG.DE"
    assert df.iloc[0]["action"] == "buy"


def test_record_transaction_rejects_unknown_ticker(data_dir: Path) -> None:
    with pytest.raises(ValidationError, match="not in config"):
        record_transaction(
            tx_path=data_dir / "transactions.csv",
            config_path=data_dir / "config.yaml",
            tx_date=date(2026, 4, 19),
            ticker="NOPE.DE",
            action="buy",
            quantity=1.0,
            price=1.0,
            currency="EUR",
        )


def test_record_transaction_rejects_sell_exceeding_held(data_dir: Path) -> None:
    record_transaction(
        tx_path=data_dir / "transactions.csv",
        config_path=data_dir / "config.yaml",
        tx_date=date(2026, 4, 19),
        ticker="WEBG.DE",
        action="buy",
        quantity=5.0,
        price=10.0,
        currency="EUR",
    )
    with pytest.raises(ValidationError, match="exceeds held"):
        record_transaction(
            tx_path=data_dir / "transactions.csv",
            config_path=data_dir / "config.yaml",
            tx_date=date(2026, 4, 19),
            ticker="WEBG.DE",
            action="sell",
            quantity=10.0,
            price=11.0,
            currency="EUR",
        )


def test_set_cash_updates_config(data_dir: Path) -> None:
    set_cash(data_dir / "config.yaml", 2500.0)
    assert load_config(data_dir / "config.yaml").cash_balance_eur == 2500.0


def test_set_cash_rejects_negative(data_dir: Path) -> None:
    with pytest.raises(ValidationError, match=">= 0"):
        set_cash(data_dir / "config.yaml", -1.0)


def test_set_cash_preserves_other_fields(data_dir: Path) -> None:
    set_cash(data_dir / "config.yaml", 42.0)
    cfg = load_config(data_dir / "config.yaml")
    assert "core-etf" in cfg.categories
    assert cfg.base_currency == "EUR"

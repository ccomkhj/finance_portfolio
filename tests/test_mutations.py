from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from portfolio.mutations import (
    ValidationError,
    add_category_ticker,
    record_transaction,
    set_cash,
    set_category_tickers,
    set_target_weights,
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


def test_set_target_weights_happy(data_dir: Path) -> None:
    set_target_weights(
        data_dir / "config.yaml",
        {"core-etf": 0.5, "bonds": 0.4, "cash": 0.1},
    )
    cfg = load_config(data_dir / "config.yaml")
    assert cfg.categories["core-etf"].target_weight == 0.5
    assert cfg.categories["bonds"].target_weight == 0.4


def test_set_target_weights_rejects_bad_sum(data_dir: Path) -> None:
    with pytest.raises(ValidationError, match="sum"):
        set_target_weights(
            data_dir / "config.yaml",
            {"core-etf": 0.5, "bonds": 0.4, "cash": 0.2},
        )


def test_set_target_weights_rejects_missing_category(data_dir: Path) -> None:
    with pytest.raises(ValidationError, match="categor"):
        set_target_weights(
            data_dir / "config.yaml",
            {"core-etf": 0.6, "bonds": 0.4},
        )


def test_set_target_weights_preserves_tickers(data_dir: Path) -> None:
    set_target_weights(
        data_dir / "config.yaml",
        {"core-etf": 0.5, "bonds": 0.4, "cash": 0.1},
    )
    cfg = load_config(data_dir / "config.yaml")
    assert "WEBG.DE" in cfg.categories["core-etf"].tickers


def test_set_category_tickers_replaces_list(data_dir: Path) -> None:
    set_category_tickers(data_dir / "config.yaml", "core-etf", ["WEBG.DE", "SXR8.DE"])
    cfg = load_config(data_dir / "config.yaml")
    assert cfg.categories["core-etf"].tickers == ("WEBG.DE", "SXR8.DE")


def test_set_category_tickers_rejects_cross_category_duplicate(data_dir: Path) -> None:
    with pytest.raises(ValidationError, match="already in"):
        set_category_tickers(data_dir / "config.yaml", "core-etf", ["EUNA.DE"])


def test_set_category_tickers_rejects_unknown_category(data_dir: Path) -> None:
    with pytest.raises(ValidationError, match="unknown category"):
        set_category_tickers(data_dir / "config.yaml", "nope", ["X.DE"])


def test_add_category_ticker_appends(data_dir: Path) -> None:
    add_category_ticker(data_dir / "config.yaml", "core-etf", "SXR8.DE")
    cfg = load_config(data_dir / "config.yaml")
    assert "SXR8.DE" in cfg.categories["core-etf"].tickers
    assert "WEBG.DE" in cfg.categories["core-etf"].tickers


def test_add_category_ticker_rejects_duplicate(data_dir: Path) -> None:
    with pytest.raises(ValidationError, match="already"):
        add_category_ticker(data_dir / "config.yaml", "bonds", "WEBG.DE")


def test_add_category_ticker_rejects_unknown_category(data_dir: Path) -> None:
    with pytest.raises(ValidationError, match="unknown category"):
        add_category_ticker(data_dir / "config.yaml", "nope", "X.DE")


def test_record_transaction_wraps_append_valueerror(data_dir: Path) -> None:
    # 'hold' passes the config/ticker checks but append_transaction rejects it;
    # the raw ValueError must surface as a ValidationError.
    with pytest.raises(ValidationError, match="invalid action 'hold'"):
        record_transaction(
            tx_path=data_dir / "transactions.csv",
            config_path=data_dir / "config.yaml",
            tx_date=date(2026, 4, 19),
            ticker="WEBG.DE",
            action="hold",
            quantity=1.0,
            price=1.0,
            currency="EUR",
        )


def test_record_transaction_sell_within_holding_succeeds(data_dir: Path) -> None:
    tx_path = data_dir / "transactions.csv"
    cfg_path = data_dir / "config.yaml"
    record_transaction(
        tx_path=tx_path, config_path=cfg_path, tx_date=date(2026, 4, 19),
        ticker="WEBG.DE", action="buy", quantity=10.0, price=10.0, currency="EUR",
    )
    record_transaction(
        tx_path=tx_path, config_path=cfg_path, tx_date=date(2026, 4, 20),
        ticker="WEBG.DE", action="sell", quantity=4.0, price=12.0, currency="EUR",
    )
    df = pd.read_csv(tx_path)
    assert len(df) == 2
    assert df.iloc[1]["action"] == "sell"


def test_set_target_weights_rejects_out_of_range_weight(data_dir: Path) -> None:
    # Sums to 1.0 so it clears the sum check, but a negative weight is invalid.
    with pytest.raises(ValidationError, match="out of range"):
        set_target_weights(
            data_dir / "config.yaml",
            {"core-etf": -0.1, "bonds": 0.6, "cash": 0.5},
        )


def test_import_profile_roundtrip(tmp_path):
    from portfolio.mutations import read_import_profile, set_import_profile

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "base_currency: EUR\n"
        "categories:\n  core:\n    target_weight: 1.0\n    tickers: []\n"
        "cash_balance_eur: 0.0\n"
    )
    assert read_import_profile(cfg) is None
    profile = {"columns": {"date": "Datum"}, "decimal": "comma",
               "date_format": "auto", "actions": {"kauf": "buy"}}
    set_import_profile(cfg, profile)
    assert read_import_profile(cfg) == profile
    # other keys preserved
    import yaml
    data = yaml.safe_load(cfg.read_text())
    assert data["base_currency"] == "EUR"
    assert "core" in data["categories"]


def test_isin_map_roundtrip(tmp_path):
    from portfolio.mutations import read_isin_map, set_isin_map_entry

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "base_currency: EUR\n"
        "categories:\n  core:\n    target_weight: 1.0\n    tickers: []\n"
        "cash_balance_eur: 0.0\n"
    )
    assert read_isin_map(cfg) == {}
    set_isin_map_entry(cfg, "IE00A", "AAA.DE")
    set_isin_map_entry(cfg, "IE00B", "BBB.DE")
    assert read_isin_map(cfg) == {"IE00A": "AAA.DE", "IE00B": "BBB.DE"}

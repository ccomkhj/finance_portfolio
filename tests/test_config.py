from pathlib import Path

import pytest
import yaml

from portfolio.config import Category, Config, load_config


def write_yaml(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_load_config_happy_path(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        {
            "base_currency": "EUR",
            "categories": {
                "equity": {"target_weight": 0.8, "tickers": ["VWCE.DE"]},
                "cash": {"target_weight": 0.2, "tickers": []},
            },
            "cash_balance_eur": 1000.0,
        },
    )
    config = load_config(path)

    assert isinstance(config, Config)
    assert config.base_currency == "EUR"
    assert config.cash_balance_eur == 1000.0
    assert set(config.categories) == {"equity", "cash"}
    assert config.categories["equity"] == Category(
        name="equity", target_weight=0.8, tickers=("VWCE.DE",)
    )
    assert config.ticker_to_category("VWCE.DE") == "equity"


def test_load_config_weights_must_sum_to_one(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        {
            "base_currency": "EUR",
            "categories": {
                "equity": {"target_weight": 0.7, "tickers": ["VWCE.DE"]},
                "cash": {"target_weight": 0.2, "tickers": []},
            },
            "cash_balance_eur": 0.0,
        },
    )
    with pytest.raises(ValueError, match="sum to 0.900000"):
        load_config(path)


def test_load_config_rejects_duplicate_tickers(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        {
            "base_currency": "EUR",
            "categories": {
                "a": {"target_weight": 0.5, "tickers": ["VWCE.DE"]},
                "b": {"target_weight": 0.5, "tickers": ["VWCE.DE"]},
            },
            "cash_balance_eur": 0.0,
        },
    )
    with pytest.raises(ValueError, match="appears in both"):
        load_config(path)


def test_ticker_to_category_raises_for_unknown(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        {
            "base_currency": "EUR",
            "categories": {
                "equity": {"target_weight": 1.0, "tickers": ["VWCE.DE"]},
            },
            "cash_balance_eur": 0.0,
        },
    )
    config = load_config(path)
    with pytest.raises(KeyError, match="AAPL"):
        config.ticker_to_category("AAPL")

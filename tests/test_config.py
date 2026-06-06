from pathlib import Path

import pytest
import yaml

from portfolio.config import Category, Config, load_config
from portfolio.income import IncomeSpec, TaxConfig


def write_yaml(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def _base(extra: dict) -> dict:
    data = {
        "base_currency": "EUR",
        "categories": {
            "equity": {"target_weight": 0.8, "tickers": ["WEBG.DE", "VOW.DE"]},
            "cash": {"target_weight": 0.2, "tickers": []},
        },
        "cash_balance_eur": 1000.0,
    }
    data.update(extra)
    return data


def test_income_block_absent_defaults(tmp_path: Path) -> None:
    config = load_config(write_yaml(tmp_path, _base({})))
    assert config.income == {}
    assert config.cash_interest_pct == 0.0


def test_income_block_parses_proxy_and_manual(tmp_path: Path) -> None:
    config = load_config(write_yaml(tmp_path, _base({
        "cash_interest_pct": 2.0,
        "income": {
            "WEBG.DE": {"proxy": "VWRL.DE"},
            "VOW.DE": {"yield_pct": 4.5},
        },
    })))
    assert config.cash_interest_pct == 2.0
    assert config.income == {
        "WEBG.DE": IncomeSpec(proxy="VWRL.DE"),
        "VOW.DE": IncomeSpec(yield_pct=4.5),
    }


def test_income_entry_rejects_both_proxy_and_yield(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, _base({
        "income": {"WEBG.DE": {"proxy": "VWRL.DE", "yield_pct": 1.7}},
    }))
    with pytest.raises(ValueError, match="WEBG.DE"):
        load_config(path)


def test_income_entry_rejects_empty(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, _base({"income": {"WEBG.DE": {}}}))
    with pytest.raises(ValueError, match="WEBG.DE"):
        load_config(path)


def test_income_entry_rejects_unknown_ticker(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, _base({"income": {"NOPE.DE": {"yield_pct": 1.0}}}))
    with pytest.raises(ValueError, match="NOPE.DE"):
        load_config(path)


def test_tax_block_absent_defaults_to_german_rate(tmp_path: Path) -> None:
    config = load_config(write_yaml(tmp_path, _base({})))
    assert config.tax == TaxConfig(rate_pct=26.375, default_teilfreistellung="equity",
                                   teilfreistellung={})


def test_tax_block_parses(tmp_path: Path) -> None:
    config = load_config(write_yaml(tmp_path, _base({
        "tax": {
            "rate_pct": 27.82,
            "default_teilfreistellung": "equity",
            "teilfreistellung": {"VOW.DE": "none"},
        },
    })))
    assert config.tax.rate_pct == 27.82
    assert config.tax.teilfreistellung == {"VOW.DE": "none"}


def test_tax_rejects_unknown_teilfreistellung_class(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, _base({
        "tax": {"teilfreistellung": {"VOW.DE": "bogus"}},
    }))
    with pytest.raises(ValueError, match="bogus"):
        load_config(path)


def test_tax_rejects_unknown_ticker(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, _base({
        "tax": {"teilfreistellung": {"NOPE.DE": "none"}},
    }))
    with pytest.raises(ValueError, match="NOPE.DE"):
        load_config(path)


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

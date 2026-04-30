from __future__ import annotations

from pathlib import Path

import pytest

from portfolio.config import load_config
from portfolio.mutations import ValidationError, init_config


HEADER = "date,ticker,action,quantity,price,currency\n"


def _seed_existing(tmp_path: Path, with_categories: bool, with_tx_rows: bool) -> tuple[Path, Path]:
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    if with_categories:
        cfg.write_text(
            "base_currency: EUR\n"
            "categories:\n"
            "  old:\n"
            "    target_weight: 1.0\n"
            "    tickers: []\n"
            "cash_balance_eur: 0.0\n"
        )
    else:
        cfg.write_text(
            "base_currency: EUR\n"
            "categories: {}\n"
            "cash_balance_eur: 0.0\n"
        )
    if with_tx_rows:
        tx.write_text(HEADER + "2026-04-01,X.DE,buy,1,1,EUR\n")
    else:
        tx.write_text(HEADER)
    return cfg, tx


def test_init_config_happy_path(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=False, with_tx_rows=False)
    init_config(
        config_path=cfg,
        tx_path=tx,
        cash_balance_eur=1500.0,
        categories=[("global-equity", 0.7), ("us-equity", 0.15), ("bonds", 0.1), ("cash", 0.05)],
    )
    loaded = load_config(cfg)
    assert loaded.cash_balance_eur == 1500.0
    assert set(loaded.categories.keys()) == {"global-equity", "us-equity", "bonds", "cash"}
    assert loaded.categories["global-equity"].target_weight == pytest.approx(0.7)
    for c in loaded.categories.values():
        assert c.tickers == ()
    assert tx.read_text() == HEADER


def test_init_config_refuses_when_config_has_categories_without_force(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=True, with_tx_rows=False)
    with pytest.raises(ValidationError, match="config"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=0.0,
            categories=[("a", 1.0)],
        )


def test_init_config_refuses_when_csv_has_rows_without_force(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=False, with_tx_rows=True)
    with pytest.raises(ValidationError, match="transactions"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=0.0,
            categories=[("a", 1.0)],
        )


def test_init_config_force_writes_bak_files(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=True, with_tx_rows=True)
    original_cfg = cfg.read_text()
    original_tx = tx.read_text()

    init_config(
        config_path=cfg,
        tx_path=tx,
        cash_balance_eur=42.0,
        categories=[("a", 1.0)],
        force=True,
    )

    assert (cfg.parent / "config.yaml.bak").read_text() == original_cfg
    assert (tx.parent / "transactions.csv.bak").read_text() == original_tx
    loaded = load_config(cfg)
    assert loaded.cash_balance_eur == 42.0
    assert tx.read_text() == HEADER


def test_init_config_validates_weight_sum(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=False, with_tx_rows=False)
    with pytest.raises(ValidationError, match="sum"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=0.0,
            categories=[("a", 0.5), ("b", 0.4)],
        )


def test_init_config_rejects_negative_cash(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=False, with_tx_rows=False)
    with pytest.raises(ValidationError, match="cash"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=-1.0,
            categories=[("a", 1.0)],
        )


def test_init_config_rejects_duplicate_categories(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=False, with_tx_rows=False)
    with pytest.raises(ValidationError, match="duplicate"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=0.0,
            categories=[("a", 0.5), ("a", 0.5)],
        )


def test_init_config_rejects_empty_categories(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=False, with_tx_rows=False)
    with pytest.raises(ValidationError, match="at least one"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=0.0,
            categories=[],
        )


def test_init_config_handles_missing_files(tmp_path: Path) -> None:
    """Truly fresh repo: no config.yaml or transactions.csv exists yet."""
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    init_config(
        config_path=cfg,
        tx_path=tx,
        cash_balance_eur=100.0,
        categories=[("only", 1.0)],
    )
    assert load_config(cfg).cash_balance_eur == 100.0
    assert tx.read_text() == HEADER


def test_init_config_refuses_config_without_categories_key(tmp_path: Path) -> None:
    """A user-edited config that lost its 'categories' key must require --force."""
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    cfg.write_text("base_currency: EUR\ncash_balance_eur: 999.0\n")  # no categories key
    tx.write_text(HEADER)

    with pytest.raises(ValidationError, match="categories"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=0.0,
            categories=[("a", 1.0)],
        )

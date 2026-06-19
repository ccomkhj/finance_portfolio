from __future__ import annotations

import pytest
from portfolio.mutations import init_config, ValidationError
from portfolio.config import load_config


def test_init_writes_starter(tmp_path):
    cfg = tmp_path / "config.yaml"
    acc = tmp_path / "accounts"
    init_config(config_path=cfg, accounts_dir=acc,
                categories=[("equity", 0.6), ("cash", 0.4)])
    loaded = load_config(cfg)
    assert set(loaded.categories) == {"equity", "cash"}
    assert acc.is_dir()


def test_init_refuses_clobber(tmp_path):
    cfg = tmp_path / "config.yaml"
    acc = tmp_path / "accounts"
    init_config(config_path=cfg, accounts_dir=acc, categories=[("cash", 1.0)])
    with pytest.raises(ValidationError, match="overwrite|categor"):
        init_config(config_path=cfg, accounts_dir=acc, categories=[("cash", 1.0)])


def test_init_force_backs_up(tmp_path):
    cfg = tmp_path / "config.yaml"
    acc = tmp_path / "accounts"
    init_config(config_path=cfg, accounts_dir=acc, categories=[("cash", 1.0)])
    init_config(config_path=cfg, accounts_dir=acc, categories=[("cash", 1.0)], force=True)
    assert (tmp_path / "config.yaml.bak").exists()

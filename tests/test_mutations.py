from __future__ import annotations

import pytest
from portfolio.mutations import (
    ValidationError, set_target_weights, set_category_isins,
    add_category_isin, set_isin_name, add_category, move_isin,
    rename_category, remove_category,
)
from portfolio.config import load_config

BASE = """
base_currency: EUR
categories:
  gold: {target_weight: 0.5, isins: [IE00B4ND3602]}
  cash: {target_weight: 0.5, isins: []}
"""


def _cfg(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(BASE)
    return p


def test_set_target_weights(tmp_path):
    p = _cfg(tmp_path)
    set_target_weights(p, {"gold": 0.3, "cash": 0.7})
    assert load_config(p).categories["gold"].target_weight == 0.3


def test_weights_must_sum_to_one(tmp_path):
    p = _cfg(tmp_path)
    with pytest.raises(ValidationError, match="sum"):
        set_target_weights(p, {"gold": 0.3, "cash": 0.3})


def test_add_isin_rejects_duplicate(tmp_path):
    p = _cfg(tmp_path)
    with pytest.raises(ValidationError, match="already"):
        add_category_isin(p, "cash", "IE00B4ND3602")


def test_set_category_isins(tmp_path):
    p = _cfg(tmp_path)
    set_category_isins(p, "cash", ["LU0000000099"])
    assert "LU0000000099" in load_config(p).categories["cash"].isins


def test_set_isin_name(tmp_path):
    p = _cfg(tmp_path)
    set_isin_name(p, "IE00B4ND3602", "Gold ETC")
    assert load_config(p).isin_names["IE00B4ND3602"] == "Gold ETC"


def test_add_category_at_zero_weight(tmp_path):
    p = _cfg(tmp_path)
    add_category(p, "us-etf")
    cfg = load_config(p)  # still loads → weights still sum to 1.0
    assert cfg.categories["us-etf"].target_weight == 0.0
    assert cfg.categories["us-etf"].isins == ()


def test_add_category_rejects_duplicate(tmp_path):
    p = _cfg(tmp_path)
    with pytest.raises(ValidationError, match="already exists"):
        add_category(p, "gold")


def test_add_category_rejects_blank(tmp_path):
    p = _cfg(tmp_path)
    with pytest.raises(ValidationError, match="required"):
        add_category(p, "   ")


def test_move_isin_from_uncategorized(tmp_path):
    p = _cfg(tmp_path)
    move_isin(p, "LU0000000099", "cash")
    assert "LU0000000099" in load_config(p).categories["cash"].isins


def test_move_isin_reassigns_across_categories(tmp_path):
    p = _cfg(tmp_path)
    move_isin(p, "IE00B4ND3602", "cash")  # was in gold
    cfg = load_config(p)
    assert "IE00B4ND3602" in cfg.categories["cash"].isins
    assert "IE00B4ND3602" not in cfg.categories["gold"].isins


def test_move_isin_unknown_category(tmp_path):
    p = _cfg(tmp_path)
    with pytest.raises(ValidationError, match="unknown category"):
        move_isin(p, "IE00B4ND3602", "nope")


def test_rename_category_carries_isins_and_weight(tmp_path):
    p = _cfg(tmp_path)
    rename_category(p, "gold", "precious-metals")
    cfg = load_config(p)
    assert "gold" not in cfg.categories
    assert cfg.categories["precious-metals"].target_weight == 0.5
    assert cfg.categories["precious-metals"].isins == ("IE00B4ND3602",)


def test_rename_category_rejects_existing_name(tmp_path):
    p = _cfg(tmp_path)
    with pytest.raises(ValidationError, match="already exists"):
        rename_category(p, "gold", "cash")


def test_remove_category_when_empty_and_zero(tmp_path):
    p = _cfg(tmp_path)
    add_category(p, "spare")  # empty, 0%
    remove_category(p, "spare")
    assert "spare" not in load_config(p).categories


def test_remove_category_rejects_non_empty(tmp_path):
    p = _cfg(tmp_path)
    with pytest.raises(ValidationError, match="not empty"):
        remove_category(p, "gold")


def test_remove_category_rejects_non_zero_weight(tmp_path):
    p = _cfg(tmp_path)
    move_isin(p, "IE00B4ND3602", "cash")  # gold now empty but still 0.5 weight
    with pytest.raises(ValidationError, match="non-zero weight"):
        remove_category(p, "gold")

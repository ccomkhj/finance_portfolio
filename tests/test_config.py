import pytest
from portfolio.config import load_config


def _write(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(text)
    return p


GOOD = """
base_currency: EUR
categories:
  gold:
    target_weight: 0.4
    isins: [IE00B4ND3602]
  cash:
    target_weight: 0.6
    isins: []
isin_names:
  IE00B4ND3602: Physical Gold USD (Acc)
"""


def test_loads_isin_categories(tmp_path):
    cfg = load_config(_write(tmp_path, GOOD))
    assert cfg.isin_to_category("IE00B4ND3602") == "gold"
    assert cfg.all_isins() == {"IE00B4ND3602"}
    assert cfg.isin_names["IE00B4ND3602"] == "Physical Gold USD (Acc)"


def test_weights_must_sum_to_one(tmp_path):
    bad = GOOD.replace("0.6", "0.7")
    with pytest.raises(ValueError, match="sum"):
        load_config(_write(tmp_path, bad))


def test_isin_in_two_categories_rejected(tmp_path):
    bad = """
base_currency: EUR
categories:
  a: {target_weight: 0.5, isins: [IE00B4ND3602]}
  b: {target_weight: 0.5, isins: [IE00B4ND3602]}
"""
    with pytest.raises(ValueError, match="both|appears"):
        load_config(_write(tmp_path, bad))

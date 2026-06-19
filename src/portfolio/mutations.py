from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from portfolio.config import WEIGHT_SUM_TOLERANCE


class ValidationError(ValueError):
    """Raised when a mutation is rejected before any file is written."""


def _read_yaml(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", yaml.safe_load(path.read_text()))


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


def set_target_weights(config_path: Path, weights: dict[str, float]) -> None:
    data = _read_yaml(config_path)
    existing = set(data["categories"].keys())
    given = set(weights.keys())
    if existing != given:
        raise ValidationError(
            f"weights must cover exactly these categories: "
            f"missing={sorted(existing - given)}, extra={sorted(given - existing)}"
        )
    total = sum(weights.values())
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValidationError(f"weights sum to {total:.6f}, expected 1.0")
    for name, w in weights.items():
        if w < 0 or w > 1:
            raise ValidationError(f"weight for {name!r} out of range: {w}")
        data["categories"][name]["target_weight"] = float(w)
    _write_yaml(config_path, data)


def set_category_isins(config_path: Path, category: str, isins: list[str]) -> None:
    data = _read_yaml(config_path)
    if category not in data["categories"]:
        raise ValidationError(f"unknown category {category!r}")
    for other_name, other in data["categories"].items():
        if other_name == category:
            continue
        conflict = set(isins) & set(other.get("isins") or [])
        if conflict:
            raise ValidationError(
                f"ISINs {sorted(conflict)} already in category {other_name!r}"
            )
    data["categories"][category]["isins"] = list(isins)
    _write_yaml(config_path, data)


def add_category_isin(config_path: Path, category: str, isin: str) -> None:
    data = _read_yaml(config_path)
    if category not in data["categories"]:
        raise ValidationError(f"unknown category {category!r}")
    for name, body in data["categories"].items():
        if isin in (body.get("isins") or []):
            raise ValidationError(f"ISIN {isin!r} already in category {name!r}")
    current = list(data["categories"][category].get("isins") or [])
    current.append(isin)
    data["categories"][category]["isins"] = current
    _write_yaml(config_path, data)


def set_isin_name(config_path: Path, isin: str, name: str) -> None:
    data = _read_yaml(config_path)
    names = dict(data.get("isin_names") or {})
    names[isin] = name
    data["isin_names"] = names
    _write_yaml(config_path, data)


def add_category(config_path: Path, name: str) -> None:
    """Add a new, empty category at 0% target weight.

    0% keeps the weight sum at 1.0 (load_config's invariant); redistribute with
    set_target_weights afterwards.
    """
    name = name.strip()
    if not name:
        raise ValidationError("category name is required")
    data = _read_yaml(config_path)
    if name in data["categories"]:
        raise ValidationError(f"category {name!r} already exists")
    data["categories"][name] = {"target_weight": 0.0, "isins": []}
    _write_yaml(config_path, data)


def move_isin(config_path: Path, isin: str, to_category: str) -> None:
    """Move an ISIN to `to_category`, removing it from any category that holds it.

    Works for both uncategorized ISINs and ones already assigned elsewhere.
    Touches no weights, so the sum-to-1.0 invariant is preserved.
    """
    isin = isin.strip()
    if not isin:
        raise ValidationError("ISIN is required")
    data = _read_yaml(config_path)
    cats = data["categories"]
    if to_category not in cats:
        raise ValidationError(f"unknown category {to_category!r}")
    for body in cats.values():
        current = list(body.get("isins") or [])
        if isin in current:
            current.remove(isin)
            body["isins"] = current
    target = list(cats[to_category].get("isins") or [])
    if isin not in target:
        target.append(isin)
    cats[to_category]["isins"] = target
    _write_yaml(config_path, data)


def rename_category(config_path: Path, old: str, new: str) -> None:
    """Rename a category, carrying its ISINs and target weight."""
    new = new.strip()
    if not new:
        raise ValidationError("new category name is required")
    data = _read_yaml(config_path)
    cats = data["categories"]
    if old not in cats:
        raise ValidationError(f"unknown category {old!r}")
    if new == old:
        return
    if new in cats:
        raise ValidationError(f"category {new!r} already exists")
    data["categories"] = {(new if k == old else k): v for k, v in cats.items()}
    _write_yaml(config_path, data)


def remove_category(config_path: Path, name: str) -> None:
    """Delete a category. Only allowed when it is empty and at 0% weight, so the
    weight sum stays 1.0."""
    data = _read_yaml(config_path)
    cats = data["categories"]
    if name not in cats:
        raise ValidationError(f"unknown category {name!r}")
    body = cats[name]
    if body.get("isins"):
        raise ValidationError(
            f"category {name!r} is not empty; move its holdings out first"
        )
    if abs(float(body.get("target_weight", 0.0))) > WEIGHT_SUM_TOLERANCE:
        raise ValidationError(
            f"category {name!r} has non-zero weight; set it to 0% first"
        )
    del cats[name]
    _write_yaml(config_path, data)


def _detect_clobber(config_path: Path) -> str | None:
    if config_path.exists():
        try:
            raw = _read_yaml(config_path)
        except Exception:
            return f"config {config_path} is non-empty/unparseable"
        if isinstance(raw, dict) and (raw.get("categories") or {}):
            n = len(raw["categories"])
            return f"config {config_path} has {n} categor{'y' if n == 1 else 'ies'}"
    return None


def init_config(
    *,
    config_path: Path,
    accounts_dir: Path,
    categories: list[tuple[str, float]],
    force: bool = False,
) -> None:
    if not categories:
        raise ValidationError("must provide at least one category")
    names = [n for n, _ in categories]
    if len(names) != len(set(names)):
        raise ValidationError(f"duplicate category names: {names}")
    for name, w in categories:
        if w < 0 or w > 1:
            raise ValidationError(f"weight for {name!r} out of range: {w}")
    total = sum(w for _, w in categories)
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValidationError(f"weights sum to {total:.6f}, expected 1.0")

    if not force:
        msg = _detect_clobber(config_path)
        if msg:
            raise ValidationError(
                f"{msg}; pass force=True to overwrite (backed up to .bak)"
            )
    if force and config_path.exists():
        (config_path.parent / (config_path.name + ".bak")).write_text(config_path.read_text())

    config_path.parent.mkdir(parents=True, exist_ok=True)
    _write_yaml(config_path, {
        "base_currency": "EUR",
        "categories": {
            name: {"target_weight": float(w), "isins": []} for name, w in categories
        },
        "isin_names": {},
    })
    accounts_dir.mkdir(parents=True, exist_ok=True)

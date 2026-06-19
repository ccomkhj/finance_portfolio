from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

WEIGHT_SUM_TOLERANCE = 0.001


@dataclass(frozen=True)
class Category:
    name: str
    target_weight: float
    isins: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    base_currency: str
    categories: dict[str, Category]
    isin_names: dict[str, str] = field(default_factory=dict)

    def isin_to_category(self, isin: str) -> str:
        for cat in self.categories.values():
            if isin in cat.isins:
                return cat.name
        raise KeyError(f"ISIN {isin!r} is not assigned to any category")

    def all_isins(self) -> set[str]:
        return {i for cat in self.categories.values() for i in cat.isins}


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text())
    categories = {
        name: Category(
            name=name,
            target_weight=float(body["target_weight"]),
            isins=tuple(body.get("isins", []) or []),
        )
        for name, body in raw["categories"].items()
    }
    _validate_weights(categories)
    _validate_unique_isins(categories)
    return Config(
        base_currency=raw["base_currency"],
        categories=categories,
        isin_names=dict(raw.get("isin_names", {}) or {}),
    )


def _validate_weights(categories: dict[str, Category]) -> None:
    total = sum(c.target_weight for c in categories.values())
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValueError(f"target_weight values sum to {total:.6f}, expected 1.0")


def _validate_unique_isins(categories: dict[str, Category]) -> None:
    seen: dict[str, str] = {}
    for cat in categories.values():
        for isin in cat.isins:
            if isin in seen:
                raise ValueError(
                    f"ISIN {isin!r} appears in both {seen[isin]!r} and {cat.name!r}"
                )
            seen[isin] = cat.name

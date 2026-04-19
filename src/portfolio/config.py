from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

WEIGHT_SUM_TOLERANCE = 0.001


@dataclass(frozen=True)
class Category:
    name: str
    target_weight: float
    tickers: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    base_currency: str
    categories: dict[str, Category]
    cash_balance_eur: float

    def ticker_to_category(self, ticker: str) -> str:
        for cat in self.categories.values():
            if ticker in cat.tickers:
                return cat.name
        raise KeyError(f"Ticker {ticker!r} is not assigned to any category")

    def all_tickers(self) -> set[str]:
        return {t for cat in self.categories.values() for t in cat.tickers}


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text())
    categories = {
        name: Category(
            name=name,
            target_weight=float(body["target_weight"]),
            tickers=tuple(body.get("tickers", [])),
        )
        for name, body in raw["categories"].items()
    }

    _validate_weights(categories)
    _validate_unique_tickers(categories)

    return Config(
        base_currency=raw["base_currency"],
        categories=categories,
        cash_balance_eur=float(raw["cash_balance_eur"]),
    )


def _validate_weights(categories: dict[str, Category]) -> None:
    total = sum(c.target_weight for c in categories.values())
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValueError(f"target_weight values sum to {total:.6f}, expected 1.0")


def _validate_unique_tickers(categories: dict[str, Category]) -> None:
    seen: dict[str, str] = {}
    for cat in categories.values():
        for ticker in cat.tickers:
            if ticker in seen:
                raise ValueError(
                    f"Ticker {ticker!r} appears in both {seen[ticker]!r} and {cat.name!r}"
                )
            seen[ticker] = cat.name

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from portfolio.income import TEILFREISTELLUNG_FRACTIONS, IncomeSpec, TaxConfig

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
    income: dict[str, IncomeSpec] = field(default_factory=dict)
    cash_interest_pct: float = 0.0
    tax: TaxConfig = field(default_factory=TaxConfig)

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

    known_tickers = {t for cat in categories.values() for t in cat.tickers}
    income = _parse_income(raw.get("income", {}) or {}, known_tickers)
    tax = _parse_tax(raw.get("tax", {}) or {}, known_tickers)

    return Config(
        base_currency=raw["base_currency"],
        categories=categories,
        cash_balance_eur=float(raw["cash_balance_eur"]),
        income=income,
        cash_interest_pct=float(raw.get("cash_interest_pct", 0.0)),
        tax=tax,
    )


def _parse_tax(raw: dict[str, Any], known_tickers: set[str]) -> TaxConfig:
    defaults = TaxConfig()
    classes = raw.get("teilfreistellung", {}) or {}
    valid = set(TEILFREISTELLUNG_FRACTIONS)

    default_tf = raw.get("default_teilfreistellung", defaults.default_teilfreistellung)
    if default_tf not in valid:
        raise ValueError(
            f"default_teilfreistellung {default_tf!r} must be one of {sorted(valid)}"
        )

    for ticker, cls in classes.items():
        if ticker not in known_tickers:
            raise ValueError(f"tax teilfreistellung {ticker!r} is not a configured ticker")
        if cls not in valid:
            raise ValueError(
                f"teilfreistellung for {ticker!r} is {cls!r}; must be one of {sorted(valid)}"
            )

    return TaxConfig(
        rate_pct=float(raw.get("rate_pct", defaults.rate_pct)),
        default_teilfreistellung=default_tf,
        teilfreistellung=dict(classes),
    )


def _parse_income(raw: dict[str, Any], known_tickers: set[str]) -> dict[str, IncomeSpec]:
    income: dict[str, IncomeSpec] = {}
    for ticker, body in raw.items():
        if ticker not in known_tickers:
            raise ValueError(
                f"income entry {ticker!r} is not a configured ticker"
            )
        body = body or {}
        proxy = body.get("proxy")
        yield_pct = body.get("yield_pct")
        if (proxy is None) == (yield_pct is None):
            raise ValueError(
                f"income entry {ticker!r} must set exactly one of proxy / yield_pct"
            )
        income[ticker] = IncomeSpec(
            proxy=proxy,
            yield_pct=None if yield_pct is None else float(yield_pct),
        )
    return income


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

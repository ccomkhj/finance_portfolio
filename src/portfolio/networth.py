from __future__ import annotations

from dataclasses import dataclass

from portfolio.config import Config
from portfolio.snapshot import Snapshot

UNCATEGORIZED = "uncategorized"


@dataclass(frozen=True)
class CategoryLine:
    name: str
    current_eur: float
    current_weight: float
    target_weight: float
    delta_eur: float


@dataclass(frozen=True)
class NetWorth:
    total_eur: float
    by_account: dict[str, float]
    categories: list[CategoryLine]
    uncategorized_isins: list[str]


def aggregate(snapshots: list[Snapshot], config: Config) -> NetWorth:
    cat_value: dict[str, float] = {name: 0.0 for name in config.categories}
    by_account: dict[str, float] = {}
    uncategorized: list[str] = []
    uncat_value = 0.0

    has_cash_cat = "cash" in config.categories

    for snap in snapshots:
        account_total = snap.cash_eur
        for h in snap.holdings:
            account_total += h.value_eur
            try:
                cat_name = config.isin_to_category(h.isin)
            except KeyError:
                uncat_value += h.value_eur
                if h.isin not in uncategorized:
                    uncategorized.append(h.isin)
                continue
            cat_value[cat_name] += h.value_eur
        if has_cash_cat:
            cat_value["cash"] += snap.cash_eur
        else:
            uncat_value += snap.cash_eur
        by_account[snap.source] = by_account.get(snap.source, 0.0) + account_total

    total = sum(by_account.values())

    lines: list[CategoryLine] = []
    for name, cat in config.categories.items():
        current = cat_value[name]
        lines.append(CategoryLine(
            name=name,
            current_eur=current,
            current_weight=current / total if total else 0.0,
            target_weight=cat.target_weight,
            delta_eur=cat.target_weight * total - current,
        ))
    if uncat_value or uncategorized:
        lines.append(CategoryLine(
            name=UNCATEGORIZED,
            current_eur=uncat_value,
            current_weight=uncat_value / total if total else 0.0,
            target_weight=0.0,
            delta_eur=-uncat_value,
        ))

    return NetWorth(
        total_eur=total,
        by_account=by_account,
        categories=lines,
        uncategorized_isins=uncategorized,
    )

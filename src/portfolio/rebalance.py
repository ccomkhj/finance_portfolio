from __future__ import annotations

from dataclasses import dataclass

from portfolio.config import Config
from portfolio.valuation import ValuedPosition


@dataclass(frozen=True)
class RebalanceAction:
    category: str
    current_weight: float
    target_weight: float
    delta_eur: float   # positive = buy more, negative = sell


def compute_rebalance(
    valued: list[ValuedPosition],
    config: Config,
    cash_eur: float,
) -> list[RebalanceAction]:
    equity_total = sum(v.market_value_eur for v in valued)
    total = equity_total + cash_eur

    category_value: dict[str, float] = {name: 0.0 for name in config.categories}

    for v in valued:
        try:
            cat = config.ticker_to_category(v.position.ticker)
        except KeyError:
            continue
        category_value[cat] += v.market_value_eur

    if "cash" in category_value:
        category_value["cash"] += cash_eur

    actions: list[RebalanceAction] = []
    for name, cat in config.categories.items():
        current = category_value[name]
        current_weight = current / total if total else 0.0
        target_value = cat.target_weight * total
        delta = target_value - current
        actions.append(RebalanceAction(
            category=name,
            current_weight=current_weight,
            target_weight=cat.target_weight,
            delta_eur=delta,
        ))
    return actions

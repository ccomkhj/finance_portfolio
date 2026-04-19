from __future__ import annotations

import math
from dataclasses import dataclass

from portfolio.positions import Position


@dataclass(frozen=True)
class ValuedPosition:
    position: Position
    current_price: float
    market_value_eur: float
    pnl_eur: float
    pnl_pct: float


def value_positions(
    positions: list[Position],
    prices: dict[str, float],
    fx_rates: dict[str, float],
) -> list[ValuedPosition]:
    out: list[ValuedPosition] = []
    for pos in positions:
        price = prices.get(pos.ticker, float("nan"))
        if math.isnan(price):
            continue
        fx = fx_rates.get(pos.currency, float("nan"))
        if math.isnan(fx):
            raise KeyError(f"missing FX rate for {pos.currency}")

        market_value_eur = pos.quantity * price * fx
        cost_basis_eur = pos.quantity * pos.avg_cost_eur
        pnl_eur = market_value_eur - cost_basis_eur
        pnl_pct = pnl_eur / cost_basis_eur if cost_basis_eur else 0.0

        out.append(ValuedPosition(
            position=pos,
            current_price=price,
            market_value_eur=market_value_eur,
            pnl_eur=pnl_eur,
            pnl_pct=pnl_pct,
        ))
    return out

import pytest

from portfolio.config import Category, Config
from portfolio.positions import Position
from portfolio.rebalance import RebalanceAction, compute_rebalance
from portfolio.valuation import ValuedPosition


def vp(ticker: str, currency: str, market_value_eur: float) -> ValuedPosition:
    pos = Position(ticker=ticker, quantity=1.0, avg_cost_eur=0.0, currency=currency)
    return ValuedPosition(
        position=pos,
        current_price=market_value_eur,
        market_value_eur=market_value_eur,
        pnl_eur=0.0,
        pnl_pct=0.0,
    )


def make_config(weights: dict[str, tuple[float, tuple[str, ...]]], cash: float = 0.0) -> Config:
    return Config(
        base_currency="EUR",
        categories={
            name: Category(name=name, target_weight=w, tickers=tickers)
            for name, (w, tickers) in weights.items()
        },
        cash_balance_eur=cash,
    )


def test_compute_rebalance_perfect_allocation() -> None:
    config = make_config({
        "equity": (0.8, ("VWCE.DE",)),
        "cash": (0.2, ()),
    })
    actions = compute_rebalance([vp("VWCE.DE", "EUR", 800.0)], config, cash_eur=200.0)

    by_cat = {a.category: a for a in actions}
    assert by_cat["equity"].current_weight == pytest.approx(0.8)
    assert by_cat["equity"].delta_eur == pytest.approx(0.0)
    assert by_cat["cash"].current_weight == pytest.approx(0.2)
    assert by_cat["cash"].delta_eur == pytest.approx(0.0)


def test_compute_rebalance_underweight_gives_positive_delta() -> None:
    config = make_config({
        "equity": (0.8, ("VWCE.DE",)),
        "cash": (0.2, ()),
    })
    # Total = 700 + 300 = 1000. Equity target 800, has 700 -> buy 100.
    actions = compute_rebalance([vp("VWCE.DE", "EUR", 700.0)], config, cash_eur=300.0)

    by_cat = {a.category: a for a in actions}
    assert by_cat["equity"].delta_eur == pytest.approx(100.0)
    assert by_cat["cash"].delta_eur == pytest.approx(-100.0)


def test_compute_rebalance_overweight_gives_negative_delta() -> None:
    config = make_config({
        "equity": (0.5, ("VWCE.DE",)),
        "cash": (0.5, ()),
    })
    # Total = 800 + 200 = 1000. Equity target 500, has 800 -> sell 300.
    actions = compute_rebalance([vp("VWCE.DE", "EUR", 800.0)], config, cash_eur=200.0)

    by_cat = {a.category: a for a in actions}
    assert by_cat["equity"].delta_eur == pytest.approx(-300.0)


def test_compute_rebalance_all_categories_emitted_even_if_empty() -> None:
    config = make_config({
        "equity": (0.8, ("VWCE.DE",)),
        "bonds": (0.1, ()),
        "cash": (0.1, ()),
    })
    actions = compute_rebalance([vp("VWCE.DE", "EUR", 800.0)], config, cash_eur=200.0)

    assert {a.category for a in actions} == {"equity", "bonds", "cash"}


def test_compute_rebalance_empty_portfolio_returns_zero_deltas() -> None:
    config = make_config({"equity": (1.0, ("VWCE.DE",))}, cash=0.0)
    actions = compute_rebalance([], config, cash_eur=0.0)
    [action] = actions
    assert action.current_weight == 0.0
    assert action.delta_eur == 0.0

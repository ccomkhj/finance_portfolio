import pytest

from portfolio.positions import Position
from portfolio.valuation import ValuedPosition, value_positions


def test_value_positions_eur_asset_profit() -> None:
    positions = [Position(ticker="VWCE.DE", quantity=10.0, avg_cost_eur=100.0, currency="EUR")]
    prices = {"VWCE.DE": 110.0}
    fx = {"EUR": 1.0}

    [vp] = value_positions(positions, prices, fx)

    assert vp.current_price == 110.0
    assert vp.market_value_eur == pytest.approx(1100.0)
    assert vp.pnl_eur == pytest.approx(100.0)
    assert vp.pnl_pct == pytest.approx(0.10)


def test_value_positions_usd_asset_with_fx_move() -> None:
    positions = [Position(ticker="AAPL", quantity=5.0, avg_cost_eur=180.0, currency="USD")]
    prices = {"AAPL": 200.0}
    fx = {"USD": 0.90}

    [vp] = value_positions(positions, prices, fx)

    assert vp.market_value_eur == pytest.approx(5 * 200 * 0.90)
    assert vp.pnl_eur == pytest.approx(5 * 200 * 0.90 - 5 * 180.0)


def test_value_positions_skips_nan_price() -> None:
    positions = [
        Position(ticker="VWCE.DE", quantity=10.0, avg_cost_eur=100.0, currency="EUR"),
        Position(ticker="UNKNOWN", quantity=5.0, avg_cost_eur=50.0, currency="EUR"),
    ]
    prices = {"VWCE.DE": 110.0, "UNKNOWN": float("nan")}
    fx = {"EUR": 1.0}

    vps = value_positions(positions, prices, fx)

    assert len(vps) == 1
    assert vps[0].position.ticker == "VWCE.DE"


def test_value_positions_empty_input() -> None:
    assert value_positions([], {}, {"EUR": 1.0}) == []

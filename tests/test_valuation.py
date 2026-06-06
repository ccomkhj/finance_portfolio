import pytest

from portfolio.positions import Position
from portfolio.valuation import value_positions


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


def test_value_positions_missing_fx_raises() -> None:
    positions = [Position(ticker="AAPL", quantity=5.0, avg_cost_eur=180.0, currency="USD")]
    prices = {"AAPL": 200.0}
    with pytest.raises(KeyError, match="missing FX rate for USD"):
        value_positions(positions, prices, fx_rates={"EUR": 1.0})


def test_value_positions_zero_cost_basis_gives_zero_pct() -> None:
    # A position with zero cost basis must not divide-by-zero on pnl_pct.
    positions = [Position(ticker="FREE.DE", quantity=10.0, avg_cost_eur=0.0, currency="EUR")]
    [vp] = value_positions(positions, {"FREE.DE": 5.0}, {"EUR": 1.0})
    assert vp.pnl_eur == pytest.approx(50.0)
    assert vp.pnl_pct == 0.0

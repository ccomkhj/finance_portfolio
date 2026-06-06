import pytest

from portfolio.income import (
    IncomeSpec,
    TaxConfig,
    compute_income,
    compute_net,
    net_factor,
    yield_tickers_needed,
)
from portfolio.positions import Position
from portfolio.valuation import ValuedPosition


def _valued(ticker: str, market_value_eur: float) -> ValuedPosition:
    pos = Position(ticker=ticker, quantity=1.0, avg_cost_eur=0.0, currency="EUR")
    return ValuedPosition(
        position=pos,
        current_price=market_value_eur,
        market_value_eur=market_value_eur,
        pnl_eur=0.0,
        pnl_pct=0.0,
    )


def test_distributing_holding_uses_native_yield_economic_equals_cash() -> None:
    valued = [_valued("VOW.DE", 1000.0)]
    yields = {"VOW.DE": 0.05}  # 5% trailing-12m

    report = compute_income(
        valued,
        yields=yields,
        income_config={},
        cash_balance_eur=0.0,
        cash_interest_pct=0.0,
    )

    [h] = report.holdings
    assert h.ticker == "VOW.DE"
    assert h.resolved is True
    assert h.source == "native"
    assert h.economic_annual_eur == pytest.approx(50.0)
    assert h.cash_annual_eur == pytest.approx(50.0)  # distributing → pays out


def test_manual_yield_is_accumulating_no_cash_distribution() -> None:
    valued = [_valued("EUNA.DE", 2000.0)]
    cfg = {"EUNA.DE": IncomeSpec(yield_pct=2.4)}

    report = compute_income(
        valued, yields={}, income_config=cfg,
        cash_balance_eur=0.0, cash_interest_pct=0.0,
    )

    [h] = report.holdings
    assert h.source == "manual"
    assert h.resolved is True
    assert h.economic_annual_eur == pytest.approx(48.0)  # 2000 * 2.4%
    assert h.cash_annual_eur == 0.0  # accumulating → no payout


def test_proxy_ticker_yield_is_accumulating_no_cash_distribution() -> None:
    valued = [_valued("WEBG.DE", 1000.0)]
    cfg = {"WEBG.DE": IncomeSpec(proxy="VWRL.DE")}
    yields = {"VWRL.DE": 0.017}  # proxy twin's trailing yield

    report = compute_income(
        valued, yields=yields, income_config=cfg,
        cash_balance_eur=0.0, cash_interest_pct=0.0,
    )

    [h] = report.holdings
    assert h.source == "proxy:VWRL.DE"
    assert h.economic_annual_eur == pytest.approx(17.0)
    assert h.cash_annual_eur == 0.0


def test_unresolved_proxy_is_flagged_and_contributes_zero() -> None:
    valued = [_valued("WEBG.DE", 1000.0)]
    cfg = {"WEBG.DE": IncomeSpec(proxy="DEAD.DE")}

    report = compute_income(
        valued, yields={"DEAD.DE": float("nan")}, income_config=cfg,
        cash_balance_eur=0.0, cash_interest_pct=0.0,
    )

    [h] = report.holdings
    assert h.resolved is False
    assert h.source == "unresolved"
    assert h.yield_pct is None
    assert h.economic_annual_eur == 0.0
    assert h.cash_annual_eur == 0.0


def test_cash_interest_line() -> None:
    report = compute_income(
        [], yields={}, income_config={},
        cash_balance_eur=10000.0, cash_interest_pct=2.0,
    )
    assert report.cash_annual_eur == pytest.approx(200.0)


def test_net_factor_equity_fund_gets_teilfreistellung() -> None:
    tax = TaxConfig(rate_pct=26.375, default_teilfreistellung="equity", teilfreistellung={})
    # equity fund: 30% of income is tax-free → only 70% taxed at 26.375%
    assert net_factor(tax, "WEBG.DE") == pytest.approx(1 - 0.26375 * 0.70)


def test_net_factor_stock_and_cash_pay_full_rate() -> None:
    tax = TaxConfig(rate_pct=26.375, default_teilfreistellung="equity",
                    teilfreistellung={"VOW.DE": "none"})
    assert net_factor(tax, "VOW.DE") == pytest.approx(1 - 0.26375)
    assert net_factor(tax, None) == pytest.approx(1 - 0.26375)  # cash interest


def test_net_factor_mixed_fund() -> None:
    tax = TaxConfig(rate_pct=26.375, default_teilfreistellung="mixed", teilfreistellung={})
    assert net_factor(tax, "X.DE") == pytest.approx(1 - 0.26375 * 0.85)


def test_compute_net_applies_per_holding_teilfreistellung() -> None:
    valued = [_valued("WEBG.DE", 1000.0), _valued("VOW.DE", 1000.0)]
    cfg = {"WEBG.DE": IncomeSpec(yield_pct=2.0)}  # equity acc fund: econ 20, cash 0
    yields = {"VOW.DE": 0.05}                      # stock: econ 50, cash 50
    report = compute_income(
        valued, yields, cfg, cash_balance_eur=10000.0, cash_interest_pct=2.0,
    )
    tax = TaxConfig(rate_pct=26.375, default_teilfreistellung="equity",
                    teilfreistellung={"VOW.DE": "none"})

    net = compute_net(report, tax)

    equity_f = 1 - 0.26375 * 0.70
    full_f = 1 - 0.26375
    assert net.total_economic_annual_eur == pytest.approx(
        20 * equity_f + 50 * full_f + 200 * full_f
    )
    assert net.total_cash_annual_eur == pytest.approx(50 * full_f + 200 * full_f)
    assert net.total_economic_monthly_eur == pytest.approx(net.total_economic_annual_eur / 12)


def test_yield_tickers_needed_picks_native_and_proxy_not_manual() -> None:
    valued = [_valued("VOW.DE", 1.0), _valued("WEBG.DE", 1.0), _valued("EUNA.DE", 1.0)]
    cfg = {
        "WEBG.DE": IncomeSpec(proxy="VWRL.DE"),  # fetch the proxy
        "EUNA.DE": IncomeSpec(yield_pct=2.4),     # manual → fetch nothing
    }
    # VOW.DE has no spec → fetch its own native yield
    assert sorted(yield_tickers_needed(valued, cfg)) == ["VOW.DE", "VWRL.DE"]


def test_report_totals_and_monthly() -> None:
    valued = [_valued("VOW.DE", 1000.0), _valued("WEBG.DE", 1000.0)]
    cfg = {"WEBG.DE": IncomeSpec(yield_pct=1.7)}
    yields = {"VOW.DE": 0.05}

    report = compute_income(
        valued, yields=yields, income_config=cfg,
        cash_balance_eur=10000.0, cash_interest_pct=2.0,
    )

    # economic: 50 (VOW) + 17 (WEBG) + 200 (cash) = 267
    assert report.total_economic_annual_eur == pytest.approx(267.0)
    # cash distributed: 50 (VOW pays) + 0 (WEBG acc) + 200 (cash) = 250
    assert report.total_cash_annual_eur == pytest.approx(250.0)
    assert report.total_economic_monthly_eur == pytest.approx(267.0 / 12)
    assert report.total_cash_monthly_eur == pytest.approx(250.0 / 12)

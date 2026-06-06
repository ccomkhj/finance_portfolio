from __future__ import annotations

import math
from dataclasses import dataclass, field

from portfolio.valuation import ValuedPosition


@dataclass(frozen=True)
class IncomeSpec:
    """Per-ticker income override: a distributing-twin `proxy` ticker XOR a `yield_pct`."""
    proxy: str | None = None
    yield_pct: float | None = None


# German Teilfreistellung: the share of fund income exempt from tax by fund type.
# Equity funds (≥51% equity) exempt 30%, mixed funds (≥25%) 15%; bond funds and
# individual stocks get none. Real-estate funds (60/80%) are out of scope.
TEILFREISTELLUNG_FRACTIONS = {"equity": 0.30, "mixed": 0.15, "none": 0.0}


@dataclass(frozen=True)
class TaxConfig:
    """Flat capital-income tax with per-holding Teilfreistellung (German model)."""
    rate_pct: float = 26.375           # Kapitalertragsteuer 25% + Soli 5.5% of that
    default_teilfreistellung: str = "equity"   # applied to holdings not listed
    teilfreistellung: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class HoldingIncome:
    ticker: str
    market_value_eur: float
    yield_pct: float | None          # None when unresolved
    economic_annual_eur: float       # market value × yield (what it earns)
    cash_annual_eur: float           # what is actually paid out (0 for accumulating)
    resolved: bool                   # False → yield could not be sourced
    source: str                      # "native" | "proxy:<ticker>" | "manual" | "unresolved"


@dataclass(frozen=True)
class IncomeReport:
    holdings: list[HoldingIncome]
    cash_balance_eur: float
    cash_interest_pct: float
    cash_annual_eur: float           # cash interest — both economic and distributed

    @property
    def total_economic_annual_eur(self) -> float:
        return sum(h.economic_annual_eur for h in self.holdings) + self.cash_annual_eur

    @property
    def total_cash_annual_eur(self) -> float:
        return sum(h.cash_annual_eur for h in self.holdings) + self.cash_annual_eur

    @property
    def total_economic_monthly_eur(self) -> float:
        return self.total_economic_annual_eur / 12.0

    @property
    def total_cash_monthly_eur(self) -> float:
        return self.total_cash_annual_eur / 12.0


def yield_tickers_needed(
    valued: list[ValuedPosition],
    income_config: dict[str, IncomeSpec],
) -> list[str]:
    """Tickers whose live yield must be fetched: proxies, or the holding itself
    when it has no override. Manual (`yield_pct`) holdings need no fetch."""
    needed: list[str] = []
    for v in valued:
        ticker = v.position.ticker
        spec = income_config.get(ticker)
        if spec is None:
            needed.append(ticker)
        elif spec.proxy is not None:
            needed.append(spec.proxy)
    return needed


def compute_income(
    valued: list[ValuedPosition],
    yields: dict[str, float],
    income_config: dict[str, IncomeSpec],
    cash_balance_eur: float,
    cash_interest_pct: float,
) -> IncomeReport:
    """Estimate annual income per holding (pure).

    `yields` maps a ticker -> trailing-12-month yield as a fraction (0.05 == 5%),
    keyed by whichever ticker should be queried (the holding itself for distributing
    holdings, or its proxy twin). Resolution order per holding:
      manual yield_pct → proxy ticker's yield → the holding's own native yield.
    A holding with an income_config entry is treated as accumulating (cash = 0);
    one without is treated as distributing (cash = economic).
    """
    holdings = [
        _holding_income(v.position.ticker, v.market_value_eur, yields, income_config)
        for v in valued
    ]

    cash_annual = cash_balance_eur * cash_interest_pct / 100.0
    return IncomeReport(
        holdings=holdings,
        cash_balance_eur=cash_balance_eur,
        cash_interest_pct=cash_interest_pct,
        cash_annual_eur=cash_annual,
    )


def _holding_income(
    ticker: str,
    market_value_eur: float,
    yields: dict[str, float],
    income_config: dict[str, IncomeSpec],
) -> HoldingIncome:
    spec = income_config.get(ticker)
    yld, source, distributing = _resolve_yield(ticker, spec, yields)

    if yld is None or math.isnan(yld):
        return HoldingIncome(
            ticker=ticker,
            market_value_eur=market_value_eur,
            yield_pct=None,
            economic_annual_eur=0.0,
            cash_annual_eur=0.0,
            resolved=False,
            source="unresolved",
        )

    economic = market_value_eur * yld
    return HoldingIncome(
        ticker=ticker,
        market_value_eur=market_value_eur,
        yield_pct=yld * 100.0,
        economic_annual_eur=economic,
        cash_annual_eur=economic if distributing else 0.0,
        resolved=True,
        source=source,
    )


@dataclass(frozen=True)
class NetHolding:
    ticker: str
    economic_annual_eur: float       # after tax
    cash_annual_eur: float           # after tax
    net_factor: float                # fraction of gross kept (1 - effective rate)


@dataclass(frozen=True)
class NetReport:
    holdings: list[NetHolding]
    cash_annual_eur: float           # cash interest after tax
    cash_net_factor: float

    @property
    def total_economic_annual_eur(self) -> float:
        return sum(h.economic_annual_eur for h in self.holdings) + self.cash_annual_eur

    @property
    def total_cash_annual_eur(self) -> float:
        return sum(h.cash_annual_eur for h in self.holdings) + self.cash_annual_eur

    @property
    def total_economic_monthly_eur(self) -> float:
        return self.total_economic_annual_eur / 12.0

    @property
    def total_cash_monthly_eur(self) -> float:
        return self.total_cash_annual_eur / 12.0


def net_factor(tax: TaxConfig, ticker: str | None) -> float:
    """Fraction of gross income kept after tax. `ticker=None` is cash interest,
    which gets no Teilfreistellung. Unlisted holdings use the configured default."""
    if ticker is None:
        cls = "none"
    else:
        cls = tax.teilfreistellung.get(ticker, tax.default_teilfreistellung)
    exemption = TEILFREISTELLUNG_FRACTIONS[cls]
    return 1.0 - (tax.rate_pct / 100.0) * (1.0 - exemption)


def compute_net(report: IncomeReport, tax: TaxConfig) -> NetReport:
    """Apply tax to a gross IncomeReport, per-holding Teilfreistellung-aware (pure)."""
    holdings = []
    for h in report.holdings:
        f = net_factor(tax, h.ticker)
        holdings.append(NetHolding(
            ticker=h.ticker,
            economic_annual_eur=h.economic_annual_eur * f,
            cash_annual_eur=h.cash_annual_eur * f,
            net_factor=f,
        ))
    cash_f = net_factor(tax, None)
    return NetReport(
        holdings=holdings,
        cash_annual_eur=report.cash_annual_eur * cash_f,
        cash_net_factor=cash_f,
    )


def _resolve_yield(
    ticker: str,
    spec: IncomeSpec | None,
    yields: dict[str, float],
) -> tuple[float | None, str, bool]:
    """Return (yield_fraction, source_label, is_distributing).

    A holding with an income_config entry is an accumulating override → not
    distributing. A holding without one uses its own live yield → distributing.
    """
    if spec is None:
        return yields.get(ticker, float("nan")), "native", True
    if spec.yield_pct is not None:
        return spec.yield_pct / 100.0, "manual", False
    if spec.proxy is not None:
        return yields.get(spec.proxy, float("nan")), f"proxy:{spec.proxy}", False
    return float("nan"), "unresolved", False

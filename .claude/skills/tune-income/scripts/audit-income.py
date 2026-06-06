"""Audit the income config and emit findings as JSON.

Runs the same pipeline as `portfolio income`, then layers on the checks a human
would otherwise do by eye: which holdings resolve a yield, which look like
accumulating funds that silently report ~0 (and should get a proxy), whether
every configured proxy ticker actually resolves on yfinance (the delisted-twin
trap), whether cash interest is set, and whether each holding's Teilfreistellung
class is set explicitly (the default-equity trap that overstates the net of
stocks and bond funds). Prefer this over reading the `portfolio income` table
when reasoning about *what to change*.

Output shape:
  {
    "timestamp": "...",
    "cash": {"balance_eur": ..., "cash_interest_pct": ..., "annual_eur": ..., "flags": [...]},
    "holdings": [
      {"ticker": ..., "market_value_eur": ..., "source": "native|proxy:X|manual",
       "resolved": bool, "yield_pct": ... | null,
       "economic_annual_eur": ..., "cash_annual_eur": ...,
       "teilfreistellung": "equity|mixed|none", "teilfreistellung_explicit": bool,
       "flags": [...]}
    ],
    "proxy_checks": [
      {"holding": ..., "proxy": ..., "resolves": bool, "proxy_yield_pct": ... | null, "flags": [...]}
    ],
    "manual_yields": [{"holding": ..., "yield_pct": ...}],
    "tax": {"rate_pct": ..., "default_teilfreistellung": ...,
            "gross_economic_annual_eur": ..., "net_economic_annual_eur": ...,
            "gross_cash_annual_eur": ..., "net_cash_annual_eur": ...},
    "summary": {"holdings": n, "unresolved": n, "zero_yield_native": n,
                "configured": n, "broken_proxies": n, "teilfreistellung_default": n}
  }

Flags worth acting on:
  - "unresolved"        — no yield could be sourced; counted as EUR 0. Add a proxy or yield_pct.
  - "zero_yield_native" — distributing-by-default but ~0% yield; almost always an
                          accumulating fund that needs a proxy (distributing twin) or manual yield.
  - "broken_proxy"      — a configured proxy ticker returns no yield (delisted/wrong symbol).
  - "cash_interest_unset" — cash balance > 0 but cash_interest_pct is 0.
  - "teilfreistellung_default" — the holding inherits the default class instead of an
                          explicit one. Fine for an equity ETF, but an individual stock or a
                          bond fund left on the equity default gets a 30% exemption it isn't
                          owed, overstating its net income. Set such holdings to `none`.

Run from the repo root:
  uv run python .claude/skills/tune-income/scripts/audit-income.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

# A native holding whose trailing yield is below this is almost certainly an
# accumulating fund (it earns income but distributes ~nothing), not a genuine
# zero-payer — worth surfacing as a proxy candidate.
ACCUMULATING_YIELD_THRESHOLD_PCT = 0.10


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the income config; emit JSON findings")
    parser.add_argument("--config", type=Path, default=Path("data/config.yaml"))
    parser.add_argument("--transactions", type=Path, default=Path("data/transactions.csv"))
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args()

    from portfolio.config import load_config
    from portfolio.income import compute_income, compute_net, yield_tickers_needed
    from portfolio.positions import compute_positions, enrich_transactions_with_eur
    from portfolio.prices import (
        fetch_dividend_yields,
        fetch_fx_eur,
        fetch_historical_fx_eur,
        fetch_prices,
    )
    from portfolio.transactions import load_transactions
    from portfolio.valuation import value_positions

    config = load_config(args.config)
    tx_df = load_transactions(args.transactions)

    orphans = sorted(set(tx_df["ticker"]) - config.all_tickers())
    if orphans:
        print(f"error: orphan tickers {orphans} — run `portfolio check`", file=sys.stderr)
        return 1

    enriched = enrich_transactions_with_eur(tx_df, fetch_historical_fx_eur)
    positions = compute_positions(enriched)

    prices = fetch_prices([p.ticker for p in positions])
    currencies = sorted({p.currency for p in positions} | {"EUR"})
    fx = fetch_fx_eur(currencies)
    valued = value_positions(positions, prices, fx)

    yields = fetch_dividend_yields(yield_tickers_needed(valued, config.income))
    report = compute_income(
        valued, yields, config.income,
        config.cash_balance_eur, config.cash_interest_pct,
    )

    net = compute_net(report, config.tax)
    tf_map = config.tax.teilfreistellung

    holdings = []
    zero_native = 0
    tf_default = 0
    for h in report.holdings:
        flags = []
        if not h.resolved:
            flags.append("unresolved")
        elif (
            h.source == "native"
            and h.yield_pct is not None
            and h.yield_pct < ACCUMULATING_YIELD_THRESHOLD_PCT
        ):
            flags.append("zero_yield_native")
            zero_native += 1

        tf_explicit = h.ticker in tf_map
        if not tf_explicit:
            flags.append("teilfreistellung_default")
            tf_default += 1

        holdings.append({
            "ticker": h.ticker,
            "market_value_eur": h.market_value_eur,
            "source": h.source,
            "resolved": h.resolved,
            "yield_pct": h.yield_pct,
            "economic_annual_eur": h.economic_annual_eur,
            "cash_annual_eur": h.cash_annual_eur,
            "teilfreistellung": tf_map.get(h.ticker, config.tax.default_teilfreistellung),
            "teilfreistellung_explicit": tf_explicit,
            "flags": flags,
        })

    proxy_checks = []
    manual_yields = []
    broken = 0
    for ticker, spec in config.income.items():
        if spec.proxy is not None:
            y = yields.get(spec.proxy, float("nan"))
            resolves = not math.isnan(y)
            flags = [] if resolves else ["broken_proxy"]
            if not resolves:
                broken += 1
            proxy_checks.append({
                "holding": ticker,
                "proxy": spec.proxy,
                "resolves": resolves,
                "proxy_yield_pct": None if not resolves else y * 100.0,
                "flags": flags,
            })
        elif spec.yield_pct is not None:
            manual_yields.append({"holding": ticker, "yield_pct": spec.yield_pct})

    cash_flags = []
    if config.cash_balance_eur > 0 and config.cash_interest_pct == 0:
        cash_flags.append("cash_interest_unset")

    out = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "cash": {
            "balance_eur": report.cash_balance_eur,
            "cash_interest_pct": report.cash_interest_pct,
            "annual_eur": report.cash_annual_eur,
            "flags": cash_flags,
        },
        "holdings": holdings,
        "proxy_checks": proxy_checks,
        "manual_yields": manual_yields,
        "tax": {
            "rate_pct": config.tax.rate_pct,
            "default_teilfreistellung": config.tax.default_teilfreistellung,
            "gross_economic_annual_eur": report.total_economic_annual_eur,
            "net_economic_annual_eur": net.total_economic_annual_eur,
            "gross_cash_annual_eur": report.total_cash_annual_eur,
            "net_cash_annual_eur": net.total_cash_annual_eur,
        },
        "summary": {
            "holdings": len(holdings),
            "unresolved": sum(1 for h in holdings if "unresolved" in h["flags"]),
            "zero_yield_native": zero_native,
            "configured": len(config.income),
            "broken_proxies": broken,
            "teilfreistellung_default": tf_default,
        },
    }

    json.dump(out, sys.stdout, indent=args.indent, default=float)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Run the portfolio pipeline end-to-end and emit a single JSON document.

Use this instead of parsing the space-padded `portfolio show` output —
it returns structured data directly from the library modules.

Output shape:
  {
    "timestamp": "2026-04-19T10:42:13",
    "base_currency": "EUR",
    "totals": {"market_value_eur": ..., "cost_basis_eur": ..., "pnl_eur": ..., "pnl_pct": ...,
               "cash_eur": ..., "grand_total_eur": ...},
    "positions": [{"ticker": ..., "category": ..., "quantity": ..., "avg_cost_eur": ...,
                   "current_price": ..., "currency": ...,
                   "market_value_eur": ..., "pnl_eur": ..., "pnl_pct": ..., "weight": ...}, ...],
    "unpriced_tickers": [...],
    "rebalance": [{"category": ..., "current_weight": ..., "target_weight": ...,
                   "drift_pp": ..., "delta_eur": ...}, ...]
  }

Run from the repo root:
  uv run python .claude/skills/assess-portfolio/scripts/snapshot.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit a portfolio snapshot as JSON")
    parser.add_argument("--config", type=Path, default=Path("data/config.yaml"))
    parser.add_argument("--transactions", type=Path, default=Path("data/transactions.csv"))
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args()

    from portfolio.config import load_config
    from portfolio.positions import compute_positions, enrich_transactions_with_eur
    from portfolio.prices import fetch_fx_eur, fetch_historical_fx_eur, fetch_prices
    from portfolio.rebalance import compute_rebalance
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

    tickers = [p.ticker for p in positions]
    prices = fetch_prices(tickers)
    currencies = sorted({p.currency for p in positions} | {"EUR"})
    fx = fetch_fx_eur(currencies)
    valued = value_positions(positions, prices, fx)

    priced_tickers = {v.position.ticker for v in valued}
    unpriced = [p.ticker for p in positions if p.ticker not in priced_tickers]

    total_market = sum(v.market_value_eur for v in valued)
    total_cost = sum(v.position.quantity * v.position.avg_cost_eur for v in valued)
    pnl = total_market - total_cost
    grand_total = total_market + config.cash_balance_eur

    pos_rows = []
    for v in valued:
        p = v.position
        pos_rows.append({
            "ticker": p.ticker,
            "category": config.ticker_to_category(p.ticker),
            "quantity": p.quantity,
            "avg_cost_eur": p.avg_cost_eur,
            "current_price": v.current_price,
            "currency": p.currency,
            "market_value_eur": v.market_value_eur,
            "pnl_eur": v.pnl_eur,
            "pnl_pct": v.pnl_pct,
            "weight": v.market_value_eur / grand_total if grand_total else 0.0,
        })

    rebalance = [
        {
            "category": a.category,
            "current_weight": a.current_weight,
            "target_weight": a.target_weight,
            "drift_pp": (a.current_weight - a.target_weight) * 100,
            "delta_eur": a.delta_eur,
        }
        for a in compute_rebalance(valued, config, config.cash_balance_eur)
    ]

    snapshot = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "base_currency": config.base_currency,
        "totals": {
            "market_value_eur": total_market,
            "cost_basis_eur": total_cost,
            "pnl_eur": pnl,
            "pnl_pct": (pnl / total_cost) if total_cost else 0.0,
            "cash_eur": config.cash_balance_eur,
            "grand_total_eur": grand_total,
        },
        "positions": pos_rows,
        "unpriced_tickers": unpriced,
        "rebalance": rebalance,
    }

    json.dump(snapshot, sys.stdout, indent=args.indent, default=float)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

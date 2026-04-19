from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from portfolio.config import load_config
from portfolio.positions import compute_positions, enrich_transactions_with_eur
from portfolio.prices import fetch_fx_eur, fetch_historical_fx_eur, fetch_prices
from portfolio.rebalance import compute_rebalance
from portfolio.transactions import load_transactions
from portfolio.valuation import value_positions

DEFAULT_TX_PATH = Path("data/transactions.csv")
DEFAULT_CONFIG_PATH = Path("data/config.yaml")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="portfolio")
    parser.add_argument("--transactions", type=Path, default=DEFAULT_TX_PATH)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    sub = parser.add_subparsers(dest="command", required=True)

    for action in ("add-buy", "add-sell"):
        sp = sub.add_parser(action)
        sp.add_argument("ticker")
        sp.add_argument("quantity", type=float)
        sp.add_argument("price", type=float)
        sp.add_argument("--currency", default="EUR", choices=["EUR", "USD"])
        sp.add_argument("--date", dest="tx_date", type=date.fromisoformat, default=None)

    sub.add_parser("show")
    sub.add_parser("check")

    args = parser.parse_args(argv)

    if args.command in ("add-buy", "add-sell"):
        return _cmd_add(args)
    if args.command == "show":
        return _cmd_show(args)
    if args.command == "check":
        return _cmd_check(args)
    parser.error(f"unknown command {args.command}")
    return 2


def _cmd_add(args: argparse.Namespace) -> int:
    from portfolio.mutations import ValidationError, record_transaction

    try:
        record_transaction(
            tx_path=args.transactions,
            config_path=args.config,
            tx_date=args.tx_date or date.today(),
            ticker=args.ticker,
            action="buy" if args.command == "add-buy" else "sell",
            quantity=args.quantity,
            price=args.price,
            currency=args.currency,
        )
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"appended: {args.ticker} {args.quantity}@{args.price} {args.currency}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    tx_df = load_transactions(args.transactions)
    orphans = sorted(set(tx_df["ticker"]) - config.all_tickers())
    if orphans:
        print(f"error: transaction tickers not in config: {orphans}", file=sys.stderr)
        return 1
    enriched = enrich_transactions_with_eur(tx_df, fetch_historical_fx_eur)
    positions = compute_positions(enriched)

    tickers = [p.ticker for p in positions]
    prices = fetch_prices(tickers)
    currencies = sorted({p.currency for p in positions} | {"EUR"})
    fx = fetch_fx_eur(currencies)
    valued = value_positions(positions, prices, fx)

    print(f"{'TICKER':<10} {'QTY':>10} {'AVG EUR':>10} {'PRICE':>10} {'VALUE EUR':>12} {'P&L EUR':>10} {'P&L %':>8}")
    for v in valued:
        p = v.position
        print(
            f"{p.ticker:<10} {p.quantity:>10.4f} {p.avg_cost_eur:>10.2f} "
            f"{v.current_price:>10.2f} {v.market_value_eur:>12.2f} "
            f"{v.pnl_eur:>10.2f} {v.pnl_pct*100:>7.2f}%"
        )

    print()
    actions = compute_rebalance(valued, config, config.cash_balance_eur)
    print(f"{'CATEGORY':<15} {'CURRENT %':>10} {'TARGET %':>10} {'DELTA EUR':>12}")
    for a in actions:
        print(
            f"{a.category:<15} {a.current_weight*100:>9.2f}% "
            f"{a.target_weight*100:>9.2f}% {a.delta_eur:>12.2f}"
        )
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    tx_df = load_transactions(args.transactions)

    known = config.all_tickers()
    orphans = sorted(set(tx_df["ticker"]) - known)
    if orphans:
        print(f"error: transaction tickers not in config: {orphans}", file=sys.stderr)
        return 1

    print(f"ok: {len(config.categories)} categories, {len(known)} configured tickers, "
          f"{len(tx_df)} transactions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

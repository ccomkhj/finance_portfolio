from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

from portfolio.config import load_config
from portfolio.positions import compute_positions, enrich_transactions_with_eur
from portfolio.prices import fetch_fx_eur, fetch_historical_fx_eur, fetch_prices
from portfolio.rebalance import compute_rebalance
from portfolio.transactions import load_transactions
from portfolio.valuation import value_positions
from portfolio.mutations import ValidationError, init_config

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
    sp_init = sub.add_parser("init")
    sp_init.add_argument("--force", action="store_true", help="overwrite non-empty data files (backed up to .bak)")

    sub.add_parser("dashboard", help="launch the streamlit dashboard (extra args forwarded)")

    args, unknown = parser.parse_known_args(argv)
    if args.command != "dashboard" and unknown:
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")

    if args.command in ("add-buy", "add-sell"):
        return _cmd_add(args)
    if args.command == "show":
        return _cmd_show(args)
    if args.command == "check":
        return _cmd_check(args)
    if args.command == "init":
        return _cmd_init(args)
    if args.command == "dashboard":
        return _cmd_dashboard(args, unknown)
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


def _prompt_init_inputs() -> tuple[float, list[tuple[str, float]]]:
    """Drive the interactive `init` prompts. Returns (cash_eur, [(name, fraction)])."""
    cash = _prompt_cash()
    names = _prompt_categories()
    while True:
        weights_pct = _prompt_weights(names)
        total = sum(weights_pct.values())
        if abs(total - 100.0) <= 0.1:
            break
        print(
            f"target weights sum to {total:.1f}%, expected 100.0%. Try again.",
            file=sys.stderr,
        )
    return cash, [(n, weights_pct[n] / 100.0) for n in names]


def _prompt_cash() -> float:
    while True:
        raw = input("Cash balance in EUR: ").strip()
        try:
            v = float(raw)
        except ValueError:
            print(f"  not a number: {raw!r}", file=sys.stderr)
            continue
        if v < 0:
            print(f"  must be >= 0, got {v}", file=sys.stderr)
            continue
        return v


def _prompt_categories() -> list[str]:
    print("Category names (one per line, blank to finish):")
    names: list[str] = []
    while True:
        raw = input("  ").strip()
        if not raw:
            if not names:
                print("  must enter at least one category", file=sys.stderr)
                continue
            return names
        if raw in names:
            print(f"  duplicate {raw!r}, ignored", file=sys.stderr)
            continue
        names.append(raw)


def _prompt_weights(names: list[str]) -> dict[str, float]:
    weights: dict[str, float] = {}
    width = max(len(n) for n in names)
    for n in names:
        while True:
            raw = input(f"Target weight for {n.ljust(width)} (%): ").strip()
            try:
                v = float(raw)
            except ValueError:
                print(f"  not a number: {raw!r}", file=sys.stderr)
                continue
            if v < 0:
                print(f"  must be >= 0, got {v}", file=sys.stderr)
                continue
            weights[n] = v
            break
    return weights


def _cmd_init(args: argparse.Namespace) -> int:
    cfg_path: Path = args.config
    tx_path: Path = args.transactions
    print(
        f"This will overwrite {cfg_path} and clear {tx_path}.",
        file=sys.stderr,
    )
    confirm = input("Continue? [y/N]: ").strip()
    if confirm.lower() != "y":
        print("aborted.", file=sys.stderr)
        return 0

    # Pre-flight clobber check: refuse early so the user (or a piped script)
    # doesn't waste effort filling in prompts only to be told to use --force.
    if not args.force:
        from portfolio.mutations import _detect_clobber
        msg = _detect_clobber(cfg_path, tx_path)
        if msg:
            print(f"error: {msg}", file=sys.stderr)
            print(
                "hint: pass --force to overwrite existing files (a .bak copy is kept).",
                file=sys.stderr,
            )
            return 1

    # Pre-flight clobber check above bails before prompting; init_config also
    # enforces the same check at write time. Both go through _detect_clobber.
    cash, categories = _prompt_init_inputs()

    try:
        init_config(
            config_path=cfg_path,
            tx_path=tx_path,
            cash_balance_eur=cash,
            categories=categories,
            force=args.force,
        )
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        print(
            "hint: pass --force to overwrite existing files (a .bak copy is kept).",
            file=sys.stderr,
        )
        return 1

    print(
        f"wrote {cfg_path} ({len(categories)} categor"
        f"{'y' if len(categories) == 1 else 'ies'}) and cleared {tx_path}."
    )
    return 0


def _cmd_dashboard(args: argparse.Namespace, extras: list[str]) -> int:
    app_path = _find_app_py()
    if app_path is None:
        print(
            "error: app.py not found. Run from the repo root, "
            "or check that pyproject.toml is alongside app.py.",
            file=sys.stderr,
        )
        return 1
    cmd = [sys.executable, "-m", "streamlit", "run", *extras, str(app_path)]
    return subprocess.call(cmd)


def _find_app_py() -> Path | None:
    cwd_app = Path("app.py")
    if cwd_app.exists():
        return cwd_app.resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "app.py"
        if candidate.exists() and (parent / "pyproject.toml").exists():
            return candidate
    return None


if __name__ == "__main__":
    sys.exit(main())

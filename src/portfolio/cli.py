# src/portfolio/cli.py
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from portfolio.accounts import list_sources, load_all, save_snapshot
from portfolio.config import load_config
from portfolio.networth import aggregate

# Data directory: override with PORTFOLIO_DATA_DIR (e.g. data/private for real
# holdings, kept out of git); defaults to the committed synthetic demo in data/.
_DATA = Path(os.environ.get("PORTFOLIO_DATA_DIR", "data"))
DEFAULT_CONFIG_PATH = _DATA / "config.yaml"
DEFAULT_ACCOUNTS_DIR = _DATA / "accounts"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="portfolio")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--accounts-dir", type=Path, default=DEFAULT_ACCOUNTS_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    sp_ingest = sub.add_parser("ingest", help="parse a broker net-worth PDF into an account snapshot")
    sp_ingest.add_argument("file", type=Path)
    sp_ingest.add_argument("--source", default="trade_republic")
    sp_ingest.add_argument("--yes", action="store_true", help="skip confirmation")
    sp_ingest.add_argument("--dry-run", action="store_true", help="preview only; write nothing")

    sub.add_parser("accounts", help="list stored account snapshots")
    sub.add_parser("show", help="show net worth across all accounts")
    sub.add_parser("check", help="validate config + flag uncategorized ISINs")

    sp_init = sub.add_parser("init")
    sp_init.add_argument("--force", action="store_true")

    sp_addcat = sub.add_parser("add-category", help="add a new empty category at 0% weight")
    sp_addcat.add_argument("name")
    sp_rencat = sub.add_parser("rename-category", help="rename a category (keeps its holdings + weight)")
    sp_rencat.add_argument("old")
    sp_rencat.add_argument("new")
    sp_rmcat = sub.add_parser("remove-category", help="delete a category (must be empty and at 0%)")
    sp_rmcat.add_argument("name")
    sp_move = sub.add_parser("move-isin", help="move an ISIN into a category")
    sp_move.add_argument("isin")
    sp_move.add_argument("category")

    sub.add_parser("dashboard", help="launch the streamlit dashboard")

    args, unknown = parser.parse_known_args(argv)
    if args.command != "dashboard" and unknown:
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")

    try:
        if args.command == "ingest":
            return _cmd_ingest(args)
        if args.command == "accounts":
            return _cmd_accounts(args)
        if args.command == "show":
            return _cmd_show(args)
        if args.command == "check":
            return _cmd_check(args)
        if args.command == "init":
            return _cmd_init(args)
        if args.command == "add-category":
            return _cmd_add_category(args)
        if args.command == "rename-category":
            return _cmd_rename_category(args)
        if args.command == "remove-category":
            return _cmd_remove_category(args)
        if args.command == "move-isin":
            return _cmd_move_isin(args)
        if args.command == "dashboard":
            return _cmd_dashboard(args, unknown)
    except (EOFError, KeyboardInterrupt):
        print("aborted.", file=sys.stderr)
        return 1
    parser.error(f"unknown command {args.command}")
    return 2


def _cmd_ingest(args: argparse.Namespace) -> int:
    from portfolio.sources import parse_pdf, supported_sources
    from portfolio.sources.trade_republic import ParseError

    if not args.file.exists():
        print(f"error: file not found: {args.file}", file=sys.stderr)
        return 1
    try:
        snap = parse_pdf(args.file, args.source)
    except NotImplementedError as e:
        print(f"error: {e} (supported: {supported_sources()})", file=sys.stderr)
        return 1
    except ParseError as e:
        print(f"error: could not parse {args.file}: {e}", file=sys.stderr)
        return 1

    print(f"source={snap.source} as_of={snap.as_of} depot={snap.account_ref}")
    print(f"{'ISIN':<14}{'QTY':>14}{'PRICE':>12}{'VALUE EUR':>14}  NAME")
    for h in snap.holdings:
        print(f"{h.isin:<14}{h.quantity:>14.6f}{h.price:>12.2f}{h.value_eur:>14.2f}  {h.name}")
    print(f"cash={snap.cash_eur:,.2f}  brokerage={snap.brokerage_total_eur:,.2f}  total={snap.total_eur:,.2f}")

    config = load_config(args.config)
    uncategorized = [h.isin for h in snap.holdings if h.isin not in config.all_isins()]
    if uncategorized:
        print(f"uncategorized ISINs (assign in config.yaml): {uncategorized}")

    if args.dry_run:
        print("dry-run: nothing written.")
        return 0
    if not args.yes:
        if input(f"Save snapshot to {args.accounts_dir}/{snap.source}.json? [y/N]: ").strip().lower() != "y":
            print("aborted.")
            return 0
    path = save_snapshot(args.accounts_dir, snap)
    print(f"saved {path}")
    return 0


def _cmd_accounts(args: argparse.Namespace) -> int:
    snaps = load_all(args.accounts_dir)
    if not snaps:
        print("no accounts. Run `portfolio ingest <pdf>`.")
        return 0
    print(f"{'SOURCE':<18}{'AS OF':<12}{'TOTAL EUR':>16}")
    for s in snaps:
        total = s.cash_eur + s.holdings_total_eur
        print(f"{s.source:<18}{s.as_of.isoformat():<12}{total:>16,.2f}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    snaps = load_all(args.accounts_dir)
    if not snaps:
        print("no accounts. Run `portfolio ingest <pdf>`.")
        return 0
    nw = aggregate(snaps, config)

    print(f"NET WORTH: {nw.total_eur:,.2f} EUR\n")
    print(f"{'ACCOUNT':<18}{'AS OF':<12}{'TOTAL EUR':>16}")
    by_date = {s.source: s.as_of for s in snaps}
    for source, total in nw.by_account.items():
        print(f"{source:<18}{by_date[source].isoformat():<12}{total:>16,.2f}")

    print(f"\n{'CATEGORY':<18}{'CURRENT %':>11}{'TARGET %':>10}{'DELTA EUR':>14}")
    for c in nw.categories:
        print(f"{c.name:<18}{c.current_weight*100:>10.2f}%{c.target_weight*100:>9.2f}%{c.delta_eur:>14,.2f}")

    if nw.uncategorized_isins:
        print(f"\nuncategorized ISINs: {nw.uncategorized_isins}")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except (ValueError, KeyError, FileNotFoundError) as e:
        print(f"config error: {e}", file=sys.stderr)
        return 1
    snaps = load_all(args.accounts_dir)
    all_isins = {h.isin for s in snaps for h in s.holdings}
    uncategorized = sorted(all_isins - config.all_isins())
    print(f"config OK: {len(config.categories)} categories, weights sum to 1.0")
    print(f"accounts: {list_sources(args.accounts_dir) or 'none'}")
    if uncategorized:
        print(f"uncategorized ISINs across snapshots: {uncategorized}")
        return 1
    print("all snapshot ISINs are categorized.")
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    from portfolio.mutations import ValidationError, init_config

    default_categories = [
        ("global-equity", 0.30), ("individual-stocks", 0.05),
        ("bonds", 0.35), ("gold", 0.10), ("cash", 0.20),
    ]
    try:
        init_config(
            config_path=args.config, accounts_dir=args.accounts_dir,
            categories=default_categories, force=args.force,
        )
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"wrote {args.config} and created {args.accounts_dir}/")
    return 0


def _cmd_add_category(args: argparse.Namespace) -> int:
    from portfolio.mutations import ValidationError, add_category

    try:
        add_category(args.config, args.name)
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"added category {args.name!r} at 0% — set its weight in the dashboard or config.yaml")
    return 0


def _cmd_rename_category(args: argparse.Namespace) -> int:
    from portfolio.mutations import ValidationError, rename_category

    try:
        rename_category(args.config, args.old, args.new)
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"renamed category {args.old!r} -> {args.new!r}")
    return 0


def _cmd_remove_category(args: argparse.Namespace) -> int:
    from portfolio.mutations import ValidationError, remove_category

    try:
        remove_category(args.config, args.name)
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"removed category {args.name!r}")
    return 0


def _cmd_move_isin(args: argparse.Namespace) -> int:
    from portfolio.mutations import ValidationError, move_isin

    try:
        move_isin(args.config, args.isin, args.category)
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"moved {args.isin} -> {args.category}")
    return 0


def _find_app_py() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "app.py"
        if candidate.exists():
            return candidate
    cwd_app = Path("app.py")
    return cwd_app if cwd_app.exists() else None


def _cmd_dashboard(args: argparse.Namespace, extras: list[str]) -> int:
    app_path = _find_app_py()
    if app_path is None:
        print("error: app.py not found. Run from the repo root.", file=sys.stderr)
        return 1
    return subprocess.call([sys.executable, "-m", "streamlit", "run", *extras, str(app_path)])


if __name__ == "__main__":
    raise SystemExit(main())

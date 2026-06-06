from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

from portfolio.config import load_config
from portfolio.income import compute_income, compute_net, yield_tickers_needed
from portfolio.positions import compute_positions, enrich_transactions_with_eur
from portfolio.prices import (
    fetch_dividend_yields,
    fetch_fx_eur,
    fetch_historical_fx_eur,
    fetch_names,
    fetch_prices,
)
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
    sp_income = sub.add_parser("income", help="estimate monthly/annual income (economic vs cash)")
    sp_income.add_argument(
        "--net", action="store_true",
        help="show after-tax figures (German flat rate + Teilfreistellung from config)",
    )
    sub.add_parser("check")
    sp_init = sub.add_parser("init")
    sp_init.add_argument("--force", action="store_true", help="overwrite non-empty data files (backed up to .bak)")

    sp_import = sub.add_parser("import", help="bulk-import transactions from a CSV")
    sp_import.add_argument("file", type=Path)
    sp_import.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    sp_import.add_argument("--dry-run", action="store_true", help="preview only; append no transactions (column profile and ISIN mappings are still saved)")
    sp_import.add_argument("--remap", action="store_true", help="re-run interactive profile setup")

    sub.add_parser("dashboard", help="launch the streamlit dashboard (extra args forwarded)")

    args, unknown = parser.parse_known_args(argv)
    if args.command != "dashboard" and unknown:
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")

    try:
        if args.command in ("add-buy", "add-sell"):
            return _cmd_add(args)
        if args.command == "show":
            return _cmd_show(args)
        if args.command == "income":
            return _cmd_income(args)
        if args.command == "check":
            return _cmd_check(args)
        if args.command == "init":
            return _cmd_init(args)
        if args.command == "import":
            return _cmd_import(args)
        if args.command == "dashboard":
            return _cmd_dashboard(args, unknown)
    except (EOFError, KeyboardInterrupt):
        print("aborted.", file=sys.stderr)
        return 1
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

    yields = fetch_dividend_yields(yield_tickers_needed(valued, config.income))
    report = compute_income(
        valued, yields, config.income,
        config.cash_balance_eur, config.cash_interest_pct,
    )
    print()
    print(
        f"INCOME (gross)  economic ~{report.total_economic_monthly_eur:,.2f}/mo "
        f"({report.total_economic_annual_eur:,.2f}/yr) · "
        f"cash ~{report.total_cash_monthly_eur:,.2f}/mo "
        f"({report.total_cash_annual_eur:,.2f}/yr)   [portfolio income for detail]"
    )
    return 0


def _cmd_income(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    tx_df = load_transactions(args.transactions)
    orphans = sorted(set(tx_df["ticker"]) - config.all_tickers())
    if orphans:
        print(f"error: transaction tickers not in config: {orphans}", file=sys.stderr)
        return 1
    enriched = enrich_transactions_with_eur(tx_df, fetch_historical_fx_eur)
    positions = compute_positions(enriched)

    prices = fetch_prices([p.ticker for p in positions])
    currencies = sorted({p.currency for p in positions} | {"EUR"})
    fx = fetch_fx_eur(currencies)
    valued = value_positions(positions, prices, fx)

    yields = fetch_dividend_yields(yield_tickers_needed(valued, config.income))
    names = fetch_names([h.position.ticker for h in valued])
    report = compute_income(
        valued, yields, config.income,
        config.cash_balance_eur, config.cash_interest_pct,
    )

    def _name(ticker: str) -> str:
        return names.get(ticker, ticker)[:28]

    # In --net mode every income figure is shown after tax; the per-holding net
    # holdings are parallel to report.holdings, so we zip them and the cash line
    # and totals come from the net report.
    net = compute_net(report, config.tax) if args.net else None
    net_holdings = net.holdings if net else [None] * len(report.holdings)
    if net:
        print(
            f"Income estimate — net (after ~{config.tax.rate_pct:.3f}% tax, "
            "Teilfreistellung-aware), annualised"
        )
    else:
        print("Income estimate — gross (pre-tax), annualised")

    print(
        f"{'TICKER':<10} {'NAME':<28} {'VALUE EUR':>12} {'YIELD%':>8} "
        f"{'ECON/MO':>10} {'ECON/YR':>10} {'CASH/MO':>10} {'CASH/YR':>10}  SOURCE"
    )
    for h, nh in zip(report.holdings, net_holdings):
        if not h.resolved:
            print(
                f"{h.ticker:<10} {_name(h.ticker):<28} {h.market_value_eur:>12.2f} {'n/a':>8} "
                f"{'n/a':>10} {'n/a':>10} {'n/a':>10} {'n/a':>10}  unresolved"
            )
            continue
        econ = nh.economic_annual_eur if nh else h.economic_annual_eur
        cash = nh.cash_annual_eur if nh else h.cash_annual_eur
        print(
            f"{h.ticker:<10} {_name(h.ticker):<28} {h.market_value_eur:>12.2f} {h.yield_pct:>7.2f}% "
            f"{econ/12:>10.2f} {econ:>10.2f} {cash/12:>10.2f} {cash:>10.2f}  {h.source}"
        )

    cash_annual = net.cash_annual_eur if net else report.cash_annual_eur
    print(
        f"{'cash':<10} {'Cash':<28} {report.cash_balance_eur:>12.2f} {report.cash_interest_pct:>7.2f}% "
        f"{cash_annual/12:>10.2f} {cash_annual:>10.2f} "
        f"{cash_annual/12:>10.2f} {cash_annual:>10.2f}  cash"
    )

    totals = net if net else report
    print(
        f"{'TOTAL':<10} {'':<28} {'':>12} {'':>8} "
        f"{totals.total_economic_monthly_eur:>10.2f} {totals.total_economic_annual_eur:>10.2f} "
        f"{totals.total_cash_monthly_eur:>10.2f} {totals.total_cash_annual_eur:>10.2f}"
    )

    unresolved = [h.ticker for h in report.holdings if not h.resolved]
    if unresolved:
        print(
            f"warning: no yield for {unresolved}; counted as 0 — "
            "set a proxy or yield_pct in config income:",
            file=sys.stderr,
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


_FIELD_ALIASES = {
    "date": ["date", "datum", "valuta", "datetime"],
    "isin": ["isin", "wkn", "instrument"],
    "action": ["action", "typ", "type", "art", "richtung", "side"],
    "quantity": ["quantity", "anzahl", "menge", "shares", "stück", "stueck", "qty"],
    "price": ["price", "kurs", "preis"],
    "currency": ["currency", "währung", "waehrung", "ccy"],
}


def _pick_column(field: str, headers: list[str]) -> str | None:
    aliases = _FIELD_ALIASES.get(field, [])
    suggestion: int | None = None
    for i, h in enumerate(headers):
        if h.strip().lower() in aliases:
            suggestion = i
            break
    print(f"\nWhich column is the {field}?")
    for i, h in enumerate(headers):
        mark = " (suggested)" if i == suggestion else ""
        print(f"  [{i}] {h}{mark}")
    if field == "currency":
        print("  [n] none (default EUR)")
    while True:
        default = "" if suggestion is None else str(suggestion)
        prompt = f"  choose [{default}]: " if default else "  choose: "
        raw = input(prompt).strip()
        if not raw and default:
            return headers[suggestion]  # type: ignore[index]
        if field == "currency" and raw.lower() == "n":
            return None
        if raw.isdigit() and 0 <= int(raw) < len(headers):
            return headers[int(raw)]
        print("  invalid choice.")


def _setup_profile(headers: list[str], records: list[dict]) -> dict:
    columns: dict[str, str] = {}
    for field in ("date", "isin", "action", "quantity", "price"):
        col = _pick_column(field, headers)
        columns[field] = col  # type: ignore[assignment]
    currency_col = _pick_column("currency", headers)
    if currency_col is not None:
        columns["currency"] = currency_col

    sample = str(records[0].get(columns["price"], "")) if records else ""
    suggested = "comma" if ("," in sample and sample.rfind(",") > sample.rfind(".")) else "dot"
    raw = input(f"\nDecimal style — comma (1.234,56) or dot (1,234.56)? [{suggested}]: ").strip().lower()
    decimal = raw if raw in ("comma", "dot") else suggested

    raw = input("Date format (strptime pattern, or 'auto') [auto]: ").strip()
    date_format = raw or "auto"

    distinct: list[str] = []
    for rec in records:
        v = str(rec.get(columns["action"], "")).strip()
        if v and v.lower() not in [d.lower() for d in distinct]:
            distinct.append(v)
    actions: dict[str, str] = {}
    print("\nClassify each action value:")
    for v in distinct:
        while True:
            raw = input(f"  {v!r} -> [buy/sell]: ").strip().lower()
            if raw in ("buy", "sell"):
                actions[v.lower()] = raw
                break
            print("  enter 'buy' or 'sell'.")

    return {"columns": columns, "decimal": decimal, "date_format": date_format, "actions": actions}


def _prompt_isin(isin: str, categories: list[str]) -> tuple[str, str]:
    print(f"\nUnmapped ISIN {isin} — assign a yfinance ticker (EUR listing, e.g. WEBG.DE).")
    ticker = ""
    while not ticker:
        ticker = input("  ticker: ").strip()
    print("  category:")
    for i, c in enumerate(categories):
        print(f"    [{i}] {c}")
    while True:
        raw = input("  choose category: ").strip()
        if raw.isdigit() and 0 <= int(raw) < len(categories):
            return ticker, categories[int(raw)]
        print("  invalid choice.")


def _check_no_negative_holdings(tx_df, new_rows) -> str | None:
    from collections import defaultdict

    # (date, rank, ticker, signed_qty) — rank 0 = buy, 1 = sell, so a same-day
    # buy is always applied before a same-day sell.
    events: list[tuple] = []
    for d, t, a, q in zip(tx_df["date"], tx_df["ticker"], tx_df["action"], tx_df["quantity"]):
        dd = d.date() if hasattr(d, "date") else d
        events.append((dd, 0 if a == "buy" else 1, t, float(q) if a == "buy" else -float(q)))
    for r in new_rows:
        events.append((r.date, 0 if r.action == "buy" else 1, r.ticker,
                       r.quantity if r.action == "buy" else -r.quantity))
    events.sort(key=lambda e: (e[0], e[1]))
    holdings: dict[str, float] = defaultdict(float)
    for d, _rank, t, signed in events:
        holdings[t] += signed
        if holdings[t] < -1e-9:
            return f"sell exceeds holdings: {t} goes negative on {d.isoformat()}"
    return None


def _cmd_import(args: argparse.Namespace) -> int:
    import pandas as pd

    from portfolio.importer import (
        ImportProfile, dedupe_key, parse_rows, resolve_tickers, split_new,
    )
    from portfolio.mutations import (
        ValidationError, add_category_ticker, read_import_profile, read_isin_map,
        set_import_profile, set_isin_map_entry,
    )
    from portfolio.transactions import Transaction, append_transactions

    path: Path = args.file
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    try:
        raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return 1
    records = raw.to_dict("records")
    headers = list(raw.columns)
    if not records:
        print(f"error: {path} has no data rows", file=sys.stderr)
        return 1

    profile_dict = read_import_profile(args.config)
    if profile_dict is None or args.remap:
        profile_dict = _setup_profile(headers, records)
        set_import_profile(args.config, profile_dict)
        print("saved import profile to config.")
    profile = ImportProfile.from_dict(profile_dict)

    rows, errors = parse_rows(records, profile)
    if errors:
        print(f"error: {len(errors)} row(s) failed to parse:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        print("hint: fix the source file, or re-run with --remap to redo the mapping.", file=sys.stderr)
        return 1

    isin_map = read_isin_map(args.config)
    resolved, unknown = resolve_tickers(rows, isin_map)
    newly_mapped = 0
    if unknown:
        if args.yes:
            print(f"error: {len(unknown)} unmapped ISIN(s) and --yes given: {unknown}", file=sys.stderr)
            return 1
        config = load_config(args.config)
        categories = sorted(config.categories.keys())
        for isin in unknown:
            ticker, category = _prompt_isin(isin, categories)
            try:
                add_category_ticker(args.config, category, ticker)
            except ValidationError as e:
                if "already in category" not in str(e):
                    print(f"error: {e}", file=sys.stderr)
                    return 1
            set_isin_map_entry(args.config, isin, ticker)
            newly_mapped += 1
        isin_map = read_isin_map(args.config)
        resolved, unknown = resolve_tickers(rows, isin_map)
        if unknown:
            print(f"error: still unmapped: {unknown}", file=sys.stderr)
            return 1

    tx_df = load_transactions(args.transactions)
    existing_keys = {
        dedupe_key(d.date(), t, a, float(q), float(p))
        for d, t, a, q, p in zip(
            tx_df["date"], tx_df["ticker"], tx_df["action"],
            tx_df["quantity"], tx_df["price"],
        )
    }
    new_rows, duplicates = split_new(resolved, existing_keys)

    print(
        f"parsed {len(resolved)} · {len(new_rows)} new · "
        f"{len(duplicates)} duplicate(s) skipped · {newly_mapped} ISIN(s) newly mapped"
    )
    if new_rows:
        print(f"{'DATE':<12}{'TICKER':<10}{'ACTION':<6}{'QTY':>12}{'PRICE':>12}{'CCY':>5}")
        for r in sorted(new_rows, key=lambda r: r.date):
            print(
                f"{r.date.isoformat():<12}{r.ticker:<10}{r.action:<6}"
                f"{r.quantity:>12.4f}{r.price:>12.2f}{r.currency:>5}"
            )

    if args.dry_run:
        print("dry-run: nothing appended.")
        return 0
    if not new_rows:
        print("nothing to import.")
        return 0
    if not args.yes:
        confirm = input(f"Append {len(new_rows)} new transaction(s)? [y/N]: ").strip().lower()
        if confirm != "y":
            print("aborted.")
            return 0

    msg = _check_no_negative_holdings(tx_df, new_rows)
    if msg:
        print(f"error: {msg}", file=sys.stderr)
        return 1

    txs = [
        Transaction(date=r.date, ticker=r.ticker, action=r.action,
                    quantity=r.quantity, price=r.price, currency=r.currency)
        for r in sorted(new_rows, key=lambda r: r.date)
    ]
    append_transactions(args.transactions, txs)
    print(f"imported {len(txs)}, skipped {len(duplicates)} duplicate(s).")
    print("run `portfolio check` to verify.")
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

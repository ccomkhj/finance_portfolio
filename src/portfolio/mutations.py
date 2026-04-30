from __future__ import annotations

from datetime import date as Date
from pathlib import Path

import yaml

from portfolio.config import load_config, WEIGHT_SUM_TOLERANCE
from portfolio.positions import compute_positions, enrich_transactions_with_eur
from portfolio.transactions import REQUIRED_COLUMNS, Transaction, append_transaction, load_transactions


class ValidationError(ValueError):
    """Raised when a mutation is rejected before any file is written."""


def record_transaction(
    *,
    tx_path: Path,
    config_path: Path,
    tx_date: Date,
    ticker: str,
    action: str,
    quantity: float,
    price: float,
    currency: str,
) -> None:
    config = load_config(config_path)
    if ticker not in config.all_tickers():
        raise ValidationError(
            f"ticker {ticker!r} not in config. Add it to a category first."
        )
    if action == "sell":
        _assert_sell_within_holding(tx_path, ticker, quantity)

    tx = Transaction(
        date=tx_date,
        ticker=ticker,
        action=action,
        quantity=quantity,
        price=price,
        currency=currency,
    )
    try:
        append_transaction(tx_path, tx)
    except ValueError as e:
        raise ValidationError(str(e)) from e


def _assert_sell_within_holding(tx_path: Path, ticker: str, quantity: float) -> None:
    tx_df = load_transactions(tx_path)
    enriched = enrich_transactions_with_eur(tx_df, lambda _c, _d: 1.0)
    positions = compute_positions(enriched)
    held = next((p.quantity for p in positions if p.ticker == ticker), 0.0)
    if quantity > held + 1e-9:
        raise ValidationError(
            f"sell of {quantity} {ticker} exceeds held {held}"
        )


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


def set_cash(config_path: Path, amount_eur: float) -> None:
    if amount_eur < 0:
        raise ValidationError(f"cash_balance_eur must be >= 0, got {amount_eur}")
    data = _read_yaml(config_path)
    data["cash_balance_eur"] = float(amount_eur)
    _write_yaml(config_path, data)


def set_target_weights(config_path: Path, weights: dict[str, float]) -> None:
    data = _read_yaml(config_path)
    existing = set(data["categories"].keys())
    given = set(weights.keys())
    if existing != given:
        missing = existing - given
        extra = given - existing
        raise ValidationError(
            f"weights must cover exactly these categories: "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )
    total = sum(weights.values())
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValidationError(f"weights sum to {total:.6f}, expected 1.0")
    for name, w in weights.items():
        if w < 0 or w > 1:
            raise ValidationError(f"weight for {name!r} out of range: {w}")
        data["categories"][name]["target_weight"] = float(w)
    _write_yaml(config_path, data)


def set_category_tickers(config_path: Path, category: str, tickers: list[str]) -> None:
    data = _read_yaml(config_path)
    if category not in data["categories"]:
        raise ValidationError(f"unknown category {category!r}")
    for other_name, other in data["categories"].items():
        if other_name == category:
            continue
        conflict = set(tickers) & set(other.get("tickers") or [])
        if conflict:
            raise ValidationError(
                f"tickers {sorted(conflict)} already in category {other_name!r}"
            )
    data["categories"][category]["tickers"] = list(tickers)
    _write_yaml(config_path, data)


def add_category_ticker(config_path: Path, category: str, ticker: str) -> None:
    data = _read_yaml(config_path)
    if category not in data["categories"]:
        raise ValidationError(f"unknown category {category!r}")
    for name, body in data["categories"].items():
        if ticker in (body.get("tickers") or []):
            raise ValidationError(f"ticker {ticker!r} already in category {name!r}")
    current = list(data["categories"][category].get("tickers") or [])
    current.append(ticker)
    data["categories"][category]["tickers"] = current
    _write_yaml(config_path, data)


def _detect_clobber(config_path: Path, tx_path: Path) -> str | None:
    """Return a human-readable error message if init_config would refuse
    without force, or None if it's safe to proceed.

    Used both by init_config (to enforce) and by the CLI (to pre-flight
    before prompting the user)."""
    if config_path.exists():
        try:
            raw = _read_yaml(config_path)
        except Exception:
            return f"config {config_path} is non-empty/unparseable"
        if not isinstance(raw, dict):
            return f"config {config_path} is non-empty/unparseable"
        if "categories" not in raw:
            return f"config {config_path} is non-empty (no 'categories' key)"
        existing = raw.get("categories") or {}
        if existing:
            n = len(existing)
            return f"config {config_path} has {n} categor{'y' if n == 1 else 'ies'}"
    if tx_path.exists():
        non_header = [ln for ln in tx_path.read_text().splitlines()[1:] if ln.strip()]
        if non_header:
            return f"transactions {tx_path} has {len(non_header)} row(s)"
    return None


def init_config(
    *,
    config_path: Path,
    tx_path: Path,
    cash_balance_eur: float,
    categories: list[tuple[str, float]],
    force: bool = False,
) -> None:
    """Wipe and re-initialise config.yaml and transactions.csv.

    Validates inputs, refuses to clobber non-empty existing files unless force=True
    (in which case existing files are renamed to <name>.bak), then writes a fresh
    config.yaml and a header-only transactions.csv.

    `categories` is a list of (name, weight_fraction) in display order. Weights
    must be in [0, 1] and sum to 1.0 ± WEIGHT_SUM_TOLERANCE.
    """
    # --- Input validation ---
    if cash_balance_eur < 0:
        raise ValidationError(f"cash_balance_eur must be >= 0, got {cash_balance_eur}")
    if not categories:
        raise ValidationError("must provide at least one category")
    names = [n for n, _ in categories]
    if len(names) != len(set(names)):
        raise ValidationError(f"duplicate category names: {names}")
    for name, w in categories:
        if w < 0 or w > 1:
            raise ValidationError(f"weight for {name!r} out of range: {w}")
    total = sum(w for _, w in categories)
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValidationError(f"weights sum to {total:.6f}, expected 1.0")

    # --- Clobber check ---
    if not force:
        msg = _detect_clobber(config_path, tx_path)
        if msg:
            raise ValidationError(
                f"{msg}; pass force=True to overwrite (existing file will be backed up to .bak)"
            )

    # --- Backup on force ---
    if force:
        if config_path.exists():
            (config_path.parent / (config_path.name + ".bak")).write_text(config_path.read_text())
        if tx_path.exists():
            (tx_path.parent / (tx_path.name + ".bak")).write_text(tx_path.read_text())

    # --- Write new files ---
    config_path.parent.mkdir(parents=True, exist_ok=True)
    new_config = {
        "base_currency": "EUR",
        "categories": {
            name: {"target_weight": float(w), "tickers": []}
            for name, w in categories
        },
        "cash_balance_eur": float(cash_balance_eur),
    }
    _write_yaml(config_path, new_config)

    tx_path.parent.mkdir(parents=True, exist_ok=True)
    tx_path.write_text(",".join(REQUIRED_COLUMNS) + "\n")

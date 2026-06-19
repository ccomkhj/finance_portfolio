"""Manual account editing.

Lets the user maintain account snapshots by hand (e.g. Trading 212, Commerzbank)
without a broker PDF. Reuses the Snapshot/Holding model; manual holdings carry an
EUR value only (quantity/price are 0). Totals and as_of are recomputed on every
edit. `accounts.py` stays pure storage; this module holds the edit logic.
"""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from pathlib import Path

from portfolio.accounts import load_snapshot, save_snapshot
from portfolio.mutations import ValidationError
from portfolio.snapshot import Holding, Snapshot


def slugify_source(name: str) -> str:
    """'Trading 212' -> 'trading_212'. Lowercase, non-alphanumerics to '_'."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def account_label(source: str) -> str:
    """'trading_212' -> 'Trading 212' for display."""
    return source.replace("_", " ").title()


def _path(accounts_dir: Path, source: str) -> Path:
    return accounts_dir / f"{source}.json"


def _load(accounts_dir: Path, source: str) -> Snapshot:
    if not _path(accounts_dir, source).exists():
        raise ValidationError(f"account {source!r} not found")
    return load_snapshot(accounts_dir, source)


def _save_recomputed(accounts_dir: Path, snap: Snapshot, as_of: date | None) -> Snapshot:
    brokerage = sum(h.value_eur for h in snap.holdings)
    new = replace(
        snap,
        brokerage_total_eur=brokerage,
        total_eur=brokerage + snap.cash_eur,
        as_of=as_of or date.today(),
    )
    save_snapshot(accounts_dir, new)
    return new


def create_account(
    accounts_dir: Path, name: str, *, as_of: date | None = None
) -> Snapshot:
    """Create a new empty manual account. `name` is slugified into the source key."""
    source = slugify_source(name)
    if not source:
        raise ValidationError("account name is required")
    if _path(accounts_dir, source).exists():
        raise ValidationError(f"account {source!r} already exists")
    snap = Snapshot(
        source=source, as_of=as_of or date.today(), account_ref="manual",
        currency="EUR", cash_eur=0.0, holdings=(),
        brokerage_total_eur=0.0, total_eur=0.0,
    )
    save_snapshot(accounts_dir, snap)
    return snap


def delete_account(accounts_dir: Path, source: str) -> None:
    path = _path(accounts_dir, source)
    if not path.exists():
        raise ValidationError(f"account {source!r} not found")
    path.unlink()


def set_cash(
    accounts_dir: Path, source: str, cash_eur: float, *, as_of: date | None = None
) -> Snapshot:
    if cash_eur < 0:
        raise ValidationError(f"cash must be >= 0, got {cash_eur}")
    snap = _load(accounts_dir, source)
    return _save_recomputed(accounts_dir, replace(snap, cash_eur=float(cash_eur)), as_of)


def upsert_holding(
    accounts_dir: Path, source: str, isin: str, name: str, value_eur: float,
    *, as_of: date | None = None,
) -> Snapshot:
    """Add a holding, or update it in place if the ISIN already exists."""
    isin = isin.strip()
    if not isin:
        raise ValidationError("ISIN is required")
    if value_eur < 0:
        raise ValidationError(f"value must be >= 0, got {value_eur}")
    snap = _load(accounts_dir, source)
    kept = [h for h in snap.holdings if h.isin != isin]
    kept.append(Holding(
        isin=isin, name=name.strip() or isin, quantity=0.0, price=0.0,
        value_eur=float(value_eur),
    ))
    return _save_recomputed(accounts_dir, replace(snap, holdings=tuple(kept)), as_of)


def remove_holding(
    accounts_dir: Path, source: str, isin: str, *, as_of: date | None = None
) -> Snapshot:
    snap = _load(accounts_dir, source)
    kept = tuple(h for h in snap.holdings if h.isin != isin)
    if len(kept) == len(snap.holdings):
        raise ValidationError(f"holding {isin!r} not found in {source!r}")
    return _save_recomputed(accounts_dir, replace(snap, holdings=kept), as_of)

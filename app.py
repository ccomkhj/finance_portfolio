# app.py
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from portfolio.accounts import load_all, load_snapshot, save_snapshot
from portfolio.config import Config, load_config
from portfolio.manual import (
    account_label, create_account, delete_account, remove_holding,
    set_cash, upsert_holding,
)
from portfolio.mutations import (
    ValidationError, add_category, move_isin, remove_category,
    rename_category, set_target_weights,
)
from portfolio.networth import NetWorth, aggregate
from portfolio.snapshot import Snapshot
from portfolio.sources import parse_pdf, supported_sources
from portfolio.sources.trade_republic import ParseError

DATA = Path(os.environ.get("PORTFOLIO_DATA_DIR", "data"))
CONFIG_PATH = DATA / "config.yaml"
ACCOUNTS_DIR = DATA / "accounts"
READ_ONLY_ENV = "PORTFOLIO_READ_ONLY"


def is_read_only_mode() -> bool:
    return os.environ.get(READ_ONLY_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def category_rows(nw: NetWorth) -> list[dict]:
    return [
        {
            "category": c.name,
            "current_eur": c.current_eur,
            "current_pct": c.current_weight * 100,
            "target_pct": c.target_weight * 100,
            "delta_eur": c.delta_eur,
        }
        for c in nw.categories
    ]


def rows_without_cash(rows: list[dict]) -> list[dict]:
    """Allocation rows with the 'cash' category dropped (for the ex-cash chart)."""
    return [r for r in rows if r["category"] != "cash"]


def removable_categories(config: Config) -> list[str]:
    """Categories that can be deleted: empty (no ISINs) and at 0% target weight,
    so removing them keeps the weight sum at 100%."""
    return [
        name for name, cat in config.categories.items()
        if not cat.isins and abs(cat.target_weight) < 1e-9
    ]


def holding_options(config: Config, snaps: list[Snapshot]) -> list[tuple[str, str]]:
    """(label, isin) for every ISIN seen in snapshots or in config, labelled with
    name and current category. Sorted by label."""
    names = dict(config.isin_names)
    isins = set(config.all_isins())
    for s in snaps:
        for h in s.holdings:
            isins.add(h.isin)
            names.setdefault(h.isin, h.name)

    def cat_of(isin: str) -> str:
        try:
            return config.isin_to_category(isin)
        except KeyError:
            return "uncategorized"

    return sorted(
        ((f"{names.get(i, i)} ({i}) — {cat_of(i)}", i) for i in isins),
        key=lambda t: t[0],
    )


def main() -> None:
    st.set_page_config(page_title="Net worth", layout="wide")
    st.title("Net worth")

    read_only = is_read_only_mode()
    if read_only:
        st.info("**Read-only demo** — synthetic data. Not financial advice.", icon="ℹ️")

    config = load_config(CONFIG_PATH)
    snaps = load_all(ACCOUNTS_DIR)

    if not read_only:
        _render_upload(config)

    sources = [s.source for s in snaps]
    nw = aggregate(snaps, config) if snaps else None

    tab_names = ["🌍 Global"] + [account_label(s) for s in sources]
    if not read_only:
        tab_names.append("⚙ Settings")
    tabs = st.tabs(tab_names)

    with tabs[0]:
        if nw is None:
            st.warning("No accounts yet. Upload a PDF, or add an account in Settings.")
        else:
            _render_global(nw, snaps)

    for offset, source in enumerate(sources, start=1):
        with tabs[offset]:
            _render_account(config, source, read_only)

    if not read_only:
        with tabs[-1]:
            _render_settings(config, snaps)

    st.sidebar.caption(f"Last refresh: {datetime.now():%H:%M:%S}")


def _render_global(nw: NetWorth, snaps: list[Snapshot]) -> None:
    by_date = {s.source: s.as_of for s in snaps}

    c1, c2 = st.columns(2)
    c1.metric("Total net worth (EUR)", f"€{nw.total_eur:,.2f}")
    c2.metric("Accounts", str(len(snaps)))

    st.subheader("By account")
    st.dataframe(pd.DataFrame([
        {"account": src, "as of": by_date[src].isoformat(), "total EUR": total}
        for src, total in nw.by_account.items()
    ]), width="stretch", hide_index=True)

    st.subheader("Allocation vs target")
    rows = category_rows(nw)
    no_cash = rows_without_cash(rows)
    c1, c2 = st.columns(2)
    with c1:
        st.caption("Including cash")
        st.plotly_chart(
            px.pie(pd.DataFrame(rows), names="category", values="current_eur", hole=0.4),
            width="stretch", key="pie_with_cash",
        )
    with c2:
        st.caption("Excluding cash")
        if no_cash:
            st.plotly_chart(
                px.pie(pd.DataFrame(no_cash), names="category", values="current_eur", hole=0.4),
                width="stretch", key="pie_no_cash",
            )
        else:
            st.info("No non-cash holdings to chart.")
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if nw.uncategorized_isins:
        st.warning(
            f"Uncategorized ISINs: {nw.uncategorized_isins} — assign them in Settings → Move holding."
        )


def _account_holdings_rows(config: Config, snap: Snapshot) -> list[dict]:
    def cat_of(isin: str) -> str:
        try:
            return config.isin_to_category(isin)
        except KeyError:
            return "uncategorized"

    return [
        {"name": h.name, "isin": h.isin, "value EUR": h.value_eur, "category": cat_of(h.isin)}
        for h in sorted(snap.holdings, key=lambda h: -h.value_eur)
    ]


def _render_account(config: Config, source: str, read_only: bool) -> None:
    snap = load_snapshot(ACCOUNTS_DIR, source)
    holdings_total = snap.holdings_total_eur
    total = snap.cash_eur + holdings_total

    c1, c2, c3 = st.columns(3)
    c1.metric("Total (EUR)", f"€{total:,.2f}")
    c2.metric("Cash (EUR)", f"€{snap.cash_eur:,.2f}")
    c3.metric("Holdings (EUR)", f"€{holdings_total:,.2f}")
    st.caption(f"as of {snap.as_of.isoformat()} · account ref: {snap.account_ref}")

    if snap.holdings:
        st.dataframe(
            pd.DataFrame(_account_holdings_rows(config, snap)),
            width="stretch", hide_index=True,
        )
    else:
        st.info("No holdings yet.")

    if read_only:
        return

    st.divider()
    st.subheader("Edit this account")

    new_cash = st.number_input(
        "Cash (EUR)", min_value=0.0, value=float(snap.cash_eur), step=100.0,
        key=f"cash_{source}",
    )
    if st.button("Save cash", key=f"savecash_{source}"):
        try:
            set_cash(ACCOUNTS_DIR, source, new_cash)
            st.success("Cash saved.")
            st.rerun()
        except ValidationError as e:
            st.error(str(e))

    st.caption("Add or update a holding (matched by ISIN)")
    hc1, hc2, hc3 = st.columns(3)
    isin = hc1.text_input("ISIN", key=f"hisin_{source}")
    name = hc2.text_input("Name", key=f"hname_{source}")
    value = hc3.number_input("Value (EUR)", min_value=0.0, step=100.0, key=f"hval_{source}")
    if st.button("Add / update holding", key=f"hadd_{source}"):
        try:
            upsert_holding(ACCOUNTS_DIR, source, isin, name, value)
            st.success(f"Saved {isin}.")
            st.rerun()
        except ValidationError as e:
            st.error(str(e))

    if snap.holdings:
        options = {f"{h.name} ({h.isin})": h.isin for h in snap.holdings}
        chosen = st.selectbox("Remove holding", list(options), key=f"rm_{source}")
        if st.button("Remove holding", key=f"rmbtn_{source}"):
            try:
                remove_holding(ACCOUNTS_DIR, source, options[chosen])
                st.success("Removed.")
                st.rerun()
            except ValidationError as e:
                st.error(str(e))


def _render_upload(config: Config) -> None:
    with st.sidebar:
        st.subheader("Upload statement")
        source = st.selectbox("Source", supported_sources(), index=0)
        uploaded = st.file_uploader("Net Worth PDF", type=["pdf"])
        if uploaded is not None and st.button("Ingest"):
            try:
                snap = parse_pdf(uploaded, source)
            except (ParseError, NotImplementedError) as e:
                st.error(f"Could not parse: {e}")
                return
            save_snapshot(ACCOUNTS_DIR, snap)
            st.success(f"Imported {len(snap.holdings)} holdings from {source} ({snap.as_of}).")
            st.rerun()


def _render_settings(config: Config, snaps: list[Snapshot]) -> None:
    st.subheader("Accounts")
    a_add, a_del = st.columns(2)
    with a_add:
        new_account = st.text_input("New account name", key="add_acct_name")
        if st.button("➕ Add account", key="add_acct_btn"):
            try:
                snap = create_account(ACCOUNTS_DIR, new_account)
                st.success(f"Added account {snap.source!r}. Fill it in on its tab.")
                st.rerun()
            except ValidationError as e:
                st.error(str(e))
    with a_del:
        sources = [s.source for s in snaps]
        if sources:
            target = st.selectbox("Delete account", sources, key="del_acct")
            if st.button("Delete account", key="del_acct_btn"):
                try:
                    delete_account(ACCOUNTS_DIR, target)
                    st.success(f"Deleted account {target!r}.")
                    st.rerun()
                except ValidationError as e:
                    st.error(str(e))
        else:
            st.caption("No accounts to delete.")

    st.divider()
    st.subheader("Categories")
    c_add, c_ren, c_del = st.columns(3)

    with c_add:
        new_name = st.text_input("New category name", key="add_cat_name")
        if st.button("➕ Add category", key="add_cat_btn"):
            try:
                add_category(CONFIG_PATH, new_name)
                st.success(f"Added {new_name!r} at 0%. Set its weight below.")
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    with c_ren:
        old = st.selectbox("Rename", list(config.categories), key="ren_old")
        renamed = st.text_input("New name", key="ren_new")
        if st.button("Rename", key="ren_btn"):
            try:
                rename_category(CONFIG_PATH, old, renamed)
                st.success(f"Renamed {old!r} → {renamed!r}.")
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    with c_del:
        removable = removable_categories(config)
        if removable:
            target = st.selectbox("Delete (empty, 0% only)", removable, key="del_cat")
            if st.button("Delete", key="del_btn"):
                try:
                    remove_category(CONFIG_PATH, target)
                    st.success(f"Deleted {target!r}.")
                    st.rerun()
                except ValidationError as e:
                    st.error(str(e))
        else:
            st.caption("Delete: none eligible (must be empty and at 0%).")

    st.divider()
    st.subheader("Move holding")
    options = holding_options(config, snaps)
    if options:
        labels = [label for label, _ in options]
        chosen = st.selectbox("Holding", labels, key="move_holding")
        isin = dict((label, i) for label, i in options)[chosen]
        to_cat = st.selectbox("Move to", list(config.categories), key="move_to")
        if st.button("Move", key="move_btn"):
            try:
                move_isin(CONFIG_PATH, isin, to_cat)
                st.success(f"Moved {isin} → {to_cat}.")
                st.rerun()
            except ValidationError as e:
                st.error(str(e))
    else:
        st.caption("No holdings to move yet.")

    st.divider()
    st.subheader("Target weights (must sum to 100%)")
    weights = {}
    cols = st.columns(min(len(config.categories), 4) or 1)
    for idx, (name, cat) in enumerate(config.categories.items()):
        with cols[idx % len(cols)]:
            weights[name] = st.number_input(
                name, min_value=0.0, max_value=1.0, value=float(cat.target_weight),
                step=0.01, key=f"w_{name}",
            )
    st.caption(f"Current sum: {sum(weights.values()) * 100:.1f}%")
    if st.button("Save weights", key="save_weights_btn"):
        try:
            set_target_weights(CONFIG_PATH, weights)
            st.success("Saved.")
            st.rerun()
        except ValidationError as e:
            st.error(str(e))


if __name__ == "__main__":
    main()

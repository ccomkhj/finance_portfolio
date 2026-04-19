from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from portfolio.config import load_config
from portfolio.mutations import (
    ValidationError,
    add_category_ticker,
    record_transaction,
    set_cash,
    set_category_tickers,
    set_target_weights,
)
from portfolio.positions import compute_positions, enrich_transactions_with_eur
from portfolio.prices import fetch_fx_eur, fetch_historical_fx_eur, fetch_names, fetch_prices
from portfolio.rebalance import compute_rebalance
from portfolio.transactions import load_transactions
from portfolio.valuation import value_positions

DATA = Path("data")
CONFIG_PATH = DATA / "config.yaml"
TX_PATH = DATA / "transactions.csv"


@st.cache_data(ttl=60)
def _cached_prices(tickers: tuple[str, ...]) -> dict[str, float]:
    return fetch_prices(list(tickers))


@st.cache_data(ttl=60)
def _cached_fx(currencies: tuple[str, ...]) -> dict[str, float]:
    return fetch_fx_eur(list(currencies))


@st.cache_data(ttl=24 * 3600)
def _cached_names(tickers: tuple[str, ...]) -> dict[str, str]:
    return fetch_names(list(tickers))


def _after_write() -> None:
    _cached_prices.clear()
    _cached_fx.clear()
    st.toast("Saved", icon="✅")
    st.rerun()


def main() -> None:
    st.set_page_config(page_title="Portfolio", layout="wide")
    st.title("Portfolio")

    if st.sidebar.button("Refresh prices"):
        _cached_prices.clear()
        _cached_fx.clear()

    drift_threshold = st.sidebar.slider(
        "Drift threshold (%)", min_value=0.0, max_value=5.0, value=1.0, step=0.1
    )

    config = load_config(CONFIG_PATH)
    tx_df = load_transactions(TX_PATH)
    orphans = sorted(set(tx_df["ticker"]) - config.all_tickers())
    if orphans:
        st.error(f"Transaction tickers not in config: {orphans}. Run `portfolio check`.")
        st.stop()
    enriched = enrich_transactions_with_eur(tx_df, fetch_historical_fx_eur)
    positions = compute_positions(enriched)

    with st.sidebar.expander("Edit", expanded=False):
        _render_edit_forms(config, positions)

    tickers = tuple(sorted(p.ticker for p in positions))
    currencies = tuple(sorted({p.currency for p in positions} | {"EUR"}))

    with st.spinner("Fetching prices..."):
        prices = _cached_prices(tickers)
        fx = _cached_fx(currencies)
        names = _cached_names(tickers)

    valued = value_positions(positions, prices, fx)
    missing = [p.ticker for p in positions if p.ticker not in {v.position.ticker for v in valued}]
    if missing:
        st.warning(f"No price available for: {', '.join(missing)} (excluded from valuation).")

    _render_summary(valued, config.cash_balance_eur)
    st.divider()
    _render_allocation(valued, config, names)
    st.divider()
    _render_pnl_and_rebalance(valued, config, drift_threshold, names)

    st.sidebar.caption(f"Last refresh: {datetime.now():%H:%M:%S}")


def _render_summary(valued, cash_eur: float) -> None:
    total_value = sum(v.market_value_eur for v in valued)
    total_cost = sum(v.position.quantity * v.position.avg_cost_eur for v in valued)
    pnl = total_value - total_cost
    pnl_pct = (pnl / total_cost) if total_cost else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Market value (EUR)", f"€{total_value + cash_eur:,.2f}")
    c2.metric("Cost basis (EUR)", f"€{total_cost:,.2f}")
    c3.metric("P&L (EUR)", f"€{pnl:,.2f}", f"{pnl_pct*100:+.2f}%")
    c4.metric("Cash (EUR)", f"€{cash_eur:,.2f}")


def _render_allocation(valued, config, names: dict[str, str]) -> None:
    if not valued:
        st.info("No positions to display.")
        return

    rows = []
    for v in valued:
        ticker = v.position.ticker
        try:
            cat = config.ticker_to_category(ticker)
        except KeyError:
            cat = "unassigned"
        rows.append({
            "category": cat,
            "ticker": ticker,
            "name": names.get(ticker, ticker),
            "value_eur": v.market_value_eur,
        })
    if config.cash_balance_eur > 0:
        rows.append({"category": "cash", "ticker": "cash", "name": "Cash",
                     "value_eur": config.cash_balance_eur})
    df = pd.DataFrame(rows)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("By category")
        by_cat = df.groupby("category", as_index=False)["value_eur"].sum()
        fig = px.pie(by_cat, names="category", values="value_eur", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("By ticker")
        fig = px.treemap(
            df, path=["category", "ticker"], values="value_eur", color="category",
            custom_data=["name"],
        )
        fig.update_traces(
            hovertemplate="<b>%{customdata[0]}</b><br>%{label}<br>€%{value:,.0f}<extra></extra>",
        )
        st.plotly_chart(fig, use_container_width=True)


def _render_pnl_and_rebalance(valued, config, drift_threshold_pct: float, names: dict[str, str]) -> None:
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("P&L by position")
        if not valued:
            st.info("No positions.")
        else:
            rows = [
                {
                    "ticker": v.position.ticker,
                    "name": names.get(v.position.ticker, v.position.ticker),
                    "pnl_eur": v.pnl_eur,
                }
                for v in sorted(valued, key=lambda v: abs(v.pnl_eur), reverse=True)
            ]
            df = pd.DataFrame(rows)
            df["color"] = df["pnl_eur"].apply(lambda x: "green" if x >= 0 else "red")
            fig = px.bar(df, x="pnl_eur", y="ticker", orientation="h", color="color",
                         color_discrete_map={"green": "#2ca02c", "red": "#d62728"},
                         custom_data=["name"])
            fig.update_traces(
                hovertemplate="<b>%{customdata[0]}</b><br>%{y}<br>€%{x:,.0f}<extra></extra>",
            )
            fig.update_layout(showlegend=False, yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Target vs actual")
        actions = compute_rebalance(valued, config, config.cash_balance_eur)
        rows = []
        for a in actions:
            drift_pct = (a.current_weight - a.target_weight) * 100
            if abs(drift_pct) < drift_threshold_pct:
                action_text = "Hold"
            elif a.delta_eur > 0:
                action_text = f"Buy €{a.delta_eur:,.0f}"
            else:
                action_text = f"Sell €{abs(a.delta_eur):,.0f}"
            rows.append({
                "Category": a.category,
                "Current %": f"{a.current_weight*100:.1f}%",
                "Target %": f"{a.target_weight*100:.1f}%",
                "Drift %": f"{drift_pct:+.1f}%",
                "Action": action_text,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_edit_forms(config, positions) -> None:
    _render_buy_form(config)
    st.divider()
    _render_sell_form(positions)
    st.divider()
    _render_cash_form(config)
    st.divider()
    _render_targets_form(config)
    st.divider()
    _render_tickers_form(config)


def _render_buy_form(config) -> None:
    st.caption("Record buy")
    known = config.all_tickers()
    categories = sorted(config.categories.keys())
    with st.form("buy_form", clear_on_submit=True):
        tx_date = st.date_input("Date", value=datetime.now().date(), key="buy_date")
        ticker = st.text_input("Ticker", key="buy_ticker", placeholder="e.g. WEBG.DE").strip()
        category = st.selectbox(
            "Category (used only if ticker is new)", categories, key="buy_category"
        )
        quantity = st.number_input("Quantity", min_value=0.0, step=1.0, key="buy_qty")
        price = st.number_input("Price", min_value=0.0, step=0.01, key="buy_price")
        currency = st.selectbox("Currency", ["EUR", "USD"], key="buy_currency")
        submitted = st.form_submit_button("Record buy")

    if not submitted:
        return
    try:
        if not ticker:
            raise ValidationError("ticker is required")
        if ticker not in known:
            add_category_ticker(CONFIG_PATH, category, ticker)
        record_transaction(
            tx_path=TX_PATH,
            config_path=CONFIG_PATH,
            tx_date=tx_date,
            ticker=ticker,
            action="buy",
            quantity=quantity,
            price=price,
            currency=currency,
        )
    except ValidationError as e:
        st.error(str(e))
        return
    _after_write()


def _render_sell_form(positions) -> None:
    st.caption("Record sell")
    held = [p for p in positions if p.quantity > 0]
    if not held:
        st.info("No positions to sell.")
        return
    ticker_to_pos = {p.ticker: p for p in held}
    with st.form("sell_form", clear_on_submit=True):
        tx_date = st.date_input("Date", value=datetime.now().date(), key="sell_date")
        ticker = st.selectbox("Ticker", sorted(ticker_to_pos), key="sell_ticker")
        max_qty = ticker_to_pos[ticker].quantity
        quantity = st.number_input(
            f"Quantity (held: {max_qty:.4f})",
            min_value=0.0, max_value=float(max_qty), step=1.0, key="sell_qty",
        )
        price = st.number_input("Price", min_value=0.0, step=0.01, key="sell_price")
        currency = st.selectbox(
            "Currency", ["EUR", "USD"],
            index=0 if ticker_to_pos[ticker].currency == "EUR" else 1,
            key="sell_currency",
        )
        submitted = st.form_submit_button("Record sell")

    if not submitted:
        return
    try:
        record_transaction(
            tx_path=TX_PATH,
            config_path=CONFIG_PATH,
            tx_date=tx_date,
            ticker=ticker,
            action="sell",
            quantity=quantity,
            price=price,
            currency=currency,
        )
    except ValidationError as e:
        st.error(str(e))
        return
    _after_write()


def _render_cash_form(config) -> None:
    st.caption("Edit cash")
    with st.form("cash_form"):
        amount = st.number_input(
            "Cash balance (EUR)",
            min_value=0.0, value=float(config.cash_balance_eur), step=100.0,
            key="cash_amount",
        )
        submitted = st.form_submit_button("Save cash")

    if not submitted:
        return
    try:
        set_cash(CONFIG_PATH, amount)
    except ValidationError as e:
        st.error(str(e))
        return
    _after_write()


def _render_targets_form(config) -> None:
    st.caption("Edit target weights")
    new_weights: dict[str, float] = {}
    with st.form("targets_form"):
        for name, cat in config.categories.items():
            new_weights[name] = st.number_input(
                name, min_value=0.0, max_value=1.0, step=0.01,
                value=float(cat.target_weight), key=f"target_{name}",
            )
        total = sum(new_weights.values())
        if abs(total - 1.0) > 1e-3:
            st.warning(f"sum = {total:.3f} (must be 1.000)")
        submitted = st.form_submit_button("Save targets")

    if not submitted:
        return
    try:
        set_target_weights(CONFIG_PATH, new_weights)
    except ValidationError as e:
        st.error(str(e))
        return
    _after_write()


def _render_tickers_form(config) -> None:
    st.caption("Edit tickers per category")
    tx_df = load_transactions(TX_PATH)
    tickers_with_tx = set(tx_df["ticker"])

    for name, cat in config.categories.items():
        with st.form(f"tickers_form_{name}"):
            st.write(f"**{name}**")
            selected = st.multiselect(
                "Tickers", list(cat.tickers), default=list(cat.tickers),
                key=f"tickers_ms_{name}",
            )
            removed = set(cat.tickers) - set(selected)
            risky = removed & tickers_with_tx
            if risky:
                st.warning(f"Removing tickers with transactions: {sorted(risky)}")
            new_ticker = st.text_input(
                "Add ticker", key=f"tickers_add_{name}", placeholder="e.g. SXR8.DE",
            )
            submitted = st.form_submit_button(f"Save {name}")

        if not submitted:
            continue
        try:
            final = list(selected)
            if new_ticker.strip():
                add_category_ticker(CONFIG_PATH, name, new_ticker.strip())
                final.append(new_ticker.strip())
            set_category_tickers(CONFIG_PATH, name, final)
        except ValidationError as e:
            st.error(str(e))
            continue
        _after_write()


if __name__ == "__main__":
    main()

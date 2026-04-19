from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from portfolio.config import load_config
from portfolio.positions import compute_positions, enrich_transactions_with_eur
from portfolio.prices import fetch_fx_eur, fetch_historical_fx_eur, fetch_prices
from portfolio.rebalance import compute_rebalance
from portfolio.transactions import load_transactions
from portfolio.valuation import value_positions

DATA = Path("data")


@st.cache_data(ttl=60)
def _cached_prices(tickers: tuple[str, ...]) -> dict[str, float]:
    return fetch_prices(list(tickers))


@st.cache_data(ttl=60)
def _cached_fx(currencies: tuple[str, ...]) -> dict[str, float]:
    return fetch_fx_eur(list(currencies))


def main() -> None:
    st.set_page_config(page_title="Portfolio", layout="wide")
    st.title("Portfolio")

    if st.sidebar.button("Refresh prices"):
        _cached_prices.clear()
        _cached_fx.clear()

    drift_threshold = st.sidebar.slider(
        "Drift threshold (%)", min_value=0.0, max_value=5.0, value=1.0, step=0.1
    )

    config = load_config(DATA / "config.yaml")
    tx_df = load_transactions(DATA / "transactions.csv")
    orphans = sorted(set(tx_df["ticker"]) - config.all_tickers())
    if orphans:
        st.error(f"Transaction tickers not in config: {orphans}. Run `portfolio check`.")
        st.stop()
    enriched = enrich_transactions_with_eur(tx_df, fetch_historical_fx_eur)
    positions = compute_positions(enriched)

    tickers = tuple(sorted(p.ticker for p in positions))
    currencies = tuple(sorted({p.currency for p in positions} | {"EUR"}))

    with st.spinner("Fetching prices..."):
        prices = _cached_prices(tickers)
        fx = _cached_fx(currencies)

    valued = value_positions(positions, prices, fx)
    missing = [p.ticker for p in positions if p.ticker not in {v.position.ticker for v in valued}]
    if missing:
        st.warning(f"No price available for: {', '.join(missing)} (excluded from valuation).")

    _render_summary(valued, config.cash_balance_eur)
    st.divider()
    _render_allocation(valued, config)
    st.divider()
    _render_pnl_and_rebalance(valued, config, drift_threshold)

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


def _render_allocation(valued, config) -> None:
    if not valued:
        st.info("No positions to display.")
        return

    rows = []
    for v in valued:
        try:
            cat = config.ticker_to_category(v.position.ticker)
        except KeyError:
            cat = "unassigned"
        rows.append({
            "category": cat,
            "ticker": v.position.ticker,
            "value_eur": v.market_value_eur,
        })
    if config.cash_balance_eur > 0:
        rows.append({"category": "cash", "ticker": "cash", "value_eur": config.cash_balance_eur})
    df = pd.DataFrame(rows)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("By category")
        by_cat = df.groupby("category", as_index=False)["value_eur"].sum()
        fig = px.pie(by_cat, names="category", values="value_eur", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("By ticker")
        fig = px.treemap(df, path=["category", "ticker"], values="value_eur", color="category")
        st.plotly_chart(fig, use_container_width=True)


def _render_pnl_and_rebalance(valued, config, drift_threshold_pct: float) -> None:
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("P&L by position")
        if not valued:
            st.info("No positions.")
        else:
            rows = [
                {"ticker": v.position.ticker, "pnl_eur": v.pnl_eur}
                for v in sorted(valued, key=lambda v: abs(v.pnl_eur), reverse=True)
            ]
            df = pd.DataFrame(rows)
            df["color"] = df["pnl_eur"].apply(lambda x: "green" if x >= 0 else "red")
            fig = px.bar(df, x="pnl_eur", y="ticker", orientation="h", color="color",
                         color_discrete_map={"green": "#2ca02c", "red": "#d62728"})
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


if __name__ == "__main__":
    main()

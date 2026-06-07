from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from portfolio.config import load_config
from portfolio.income import (
    IncomeReport,
    NetReport,
    TaxConfig,
    compute_income,
    compute_net,
    yield_tickers_needed,
)
from portfolio.importer import (
    ImportProfile,
    dedupe_key,
    parse_rows,
    resolve_tickers,
    split_new,
)
from portfolio.mutations import (
    ValidationError,
    add_category_ticker,
    read_import_profile,
    read_isin_map,
    record_transaction,
    set_cash,
    set_category_tickers,
    set_target_weights,
)
from portfolio.positions import compute_positions, enrich_transactions_with_eur
from portfolio.prices import (
    fetch_dividend_yields,
    fetch_fx_eur,
    fetch_historical_fx_eur,
    fetch_names,
    fetch_prices,
    resolve_prices,
)
from portfolio.rebalance import compute_rebalance
from portfolio.transactions import Transaction, append_transactions, load_transactions
from portfolio.valuation import value_positions

DATA = Path("data")
CONFIG_PATH = DATA / "config.yaml"
TX_PATH = DATA / "transactions.csv"

SENTINEL = "➕ New ticker…"
READ_ONLY_ENV = "PORTFOLIO_READ_ONLY"


def is_read_only_mode() -> bool:
    return os.environ.get(READ_ONLY_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def demo_price_note(source: str) -> str:
    """One-line price-status note for the read-only demo banner."""
    if source == "snapshot":
        return "⚠️ Showing **sample** prices — live data is temporarily unavailable."
    return "Prices are **live** via Yahoo Finance (yfinance)."


def resolve_buy_ticker(selection: str, new_text: str, sentinel: str) -> tuple[str, bool]:
    """Resolve the buy form's ticker selection into (ticker, is_new).

    Raises ValidationError when the "new ticker" sentinel is chosen but no
    ticker text was entered."""
    if selection != sentinel:
        return selection, False
    ticker = new_text.strip()
    if not ticker:
        raise ValidationError("ticker is required")
    return ticker, True


@st.cache_data(ttl=60)
def _cached_prices(tickers: tuple[str, ...]) -> dict[str, float]:
    return fetch_prices(list(tickers))


@st.cache_data(ttl=60)
def _cached_fx(currencies: tuple[str, ...]) -> dict[str, float]:
    return fetch_fx_eur(list(currencies))


@st.cache_data(ttl=24 * 3600)
def _cached_names(tickers: tuple[str, ...]) -> dict[str, str]:
    return fetch_names(list(tickers))


@st.cache_data(ttl=24 * 3600)
def _cached_yields(tickers: tuple[str, ...]) -> dict[str, float]:
    return fetch_dividend_yields(list(tickers))


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

    if st.sidebar.button("📋 Export status (Markdown)"):
        st.session_state["show_export"] = True

    read_only = is_read_only_mode()
    if read_only:
        _render_demo_banner()

    config = load_config(CONFIG_PATH)
    if not read_only:
        _render_import_sidebar()
    tx_df = load_transactions(TX_PATH)
    orphans = sorted(set(tx_df["ticker"]) - config.all_tickers())
    if orphans:
        st.error(f"Transaction tickers not in config: {orphans}. Run `portfolio check`.")
        st.stop()
    enriched = enrich_transactions_with_eur(tx_df, fetch_historical_fx_eur)
    positions = compute_positions(enriched)

    tickers = tuple(sorted(p.ticker for p in positions))
    currencies = tuple(sorted({p.currency for p in positions} | {"EUR"}))

    with st.spinner("Fetching prices..."):
        # Keep the cached fetcher exception-truthful; resolve_prices adds the
        # read-only demo's offline snapshot fallback only at this boundary.
        prices, price_source = resolve_prices(
            list(tickers),
            fetch=lambda t: _cached_prices(tuple(t)),
            read_only=read_only,
        )
        fx = _cached_fx(currencies)
        names = _cached_names(tickers)
    if read_only:
        st.caption(demo_price_note(price_source))

    valued = value_positions(positions, prices, fx)
    missing = [p.ticker for p in positions if p.ticker not in {v.position.ticker for v in valued}]
    if missing:
        st.warning(f"No price available for: {', '.join(missing)} (excluded from valuation).")

    income_yields = _cached_yields(tuple(yield_tickers_needed(valued, config.income)))
    income = compute_income(
        valued, income_yields, config.income,
        config.cash_balance_eur, config.cash_interest_pct,
    )

    if read_only:
        st.sidebar.caption("Read-only demo")
    tabs = st.tabs(["Overview"] if read_only else ["Overview", "Edit"])
    overview = tabs[0]
    with overview:
        if st.session_state.get("show_export"):
            status_md = build_status_markdown(
                valued, config, income, names, drift_threshold,
                tax=config.tax, price_source=price_source if read_only else None,
            )
            _render_export(status_md)
            st.divider()
        _render_summary(valued, config.cash_balance_eur)
        st.divider()
        _render_income(income, names, config.tax)
        st.divider()
        _render_allocation(valued, config, names)
        st.divider()
        _render_pnl_and_rebalance(valued, config, drift_threshold, names)
    if not read_only:
        with tabs[1]:
            _render_edit_forms(config, positions)

    st.sidebar.caption(f"Last refresh: {datetime.now():%H:%M:%S}")


def _render_demo_banner() -> None:
    st.info(
        "**Synthetic demo · read-only.** Sample portfolio data, not real holdings. "
        "Prices are fetched live and fall back to a stored sample if unavailable. "
        "Not financial advice — see the "
        "[disclaimer](https://github.com/ccomkhj/finance_portfolio/blob/main/DISCLAIMER.md). "
        "Run it locally with your own data: "
        "[ccomkhj/finance_portfolio](https://github.com/ccomkhj/finance_portfolio).",
        icon="ℹ️",
    )


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


def build_income_rows(
    report: IncomeReport, names: dict[str, str], net: NetReport | None = None,
) -> list[dict]:
    """Per-holding + cash display rows. Unresolved holdings show 'n/a'. When a
    NetReport is passed, the income columns are shown after tax."""
    net_holdings = net.holdings if net else [None] * len(report.holdings)
    rows: list[dict] = []
    for h, nh in zip(report.holdings, net_holdings):
        if not h.resolved:
            rows.append({
                "Ticker": h.ticker,
                "Name": names.get(h.ticker, h.ticker),
                "Value EUR": h.market_value_eur,
                "Yield %": "n/a",
                "Economic €/mo": "n/a",
                "Economic €/yr": "n/a",
                "Cash €/mo": "n/a",
                "Cash €/yr": "n/a",
                "Source": "unresolved",
            })
            continue
        econ = nh.economic_annual_eur if nh else h.economic_annual_eur
        cash = nh.cash_annual_eur if nh else h.cash_annual_eur
        rows.append({
            "Ticker": h.ticker,
            "Name": names.get(h.ticker, h.ticker),
            "Value EUR": h.market_value_eur,
            "Yield %": h.yield_pct,
            "Economic €/mo": econ / 12,
            "Economic €/yr": econ,
            "Cash €/mo": cash / 12,
            "Cash €/yr": cash,
            "Source": h.source,
        })
    cash_annual = net.cash_annual_eur if net else report.cash_annual_eur
    rows.append({
        "Ticker": "cash",
        "Name": "Cash",
        "Value EUR": report.cash_balance_eur,
        "Yield %": report.cash_interest_pct,
        "Economic €/mo": cash_annual / 12,
        "Economic €/yr": cash_annual,
        "Cash €/mo": cash_annual / 12,
        "Cash €/yr": cash_annual,
        "Source": "cash",
    })
    return rows


def _fmt_eur(value: float) -> str:
    return f"€{value:,.2f}"


def build_status_markdown(
    valued,
    config,
    income: IncomeReport,
    names: dict[str, str],
    drift_threshold_pct: float,
    *,
    tax: TaxConfig | None = None,
    price_source: str | None = None,
    as_of: datetime | None = None,
) -> str:
    """Render the current portfolio status as a self-contained Markdown report.

    Pure (no Streamlit / network) so it can be unit-tested and pasted into an
    external AI tool for further analysis. Mirrors the dashboard's Overview tab:
    summary, holdings, allocation vs target, P&L, and income estimate.
    """
    as_of = as_of or datetime.now()
    cash_eur = config.cash_balance_eur

    total_value = sum(v.market_value_eur for v in valued)
    total_cost = sum(v.position.quantity * v.position.avg_cost_eur for v in valued)
    pnl = total_value - total_cost
    pnl_pct = (pnl / total_cost) if total_cost else 0.0

    lines: list[str] = []
    lines.append(f"# Portfolio status — {as_of:%Y-%m-%d %H:%M}")
    lines.append("")
    if price_source == "snapshot":
        lines.append("> ⚠️ Prices are **sample** data (live feed unavailable).")
        lines.append("")

    # Summary -----------------------------------------------------------------
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    lines.append(f"| Total value (incl. cash) | {_fmt_eur(total_value + cash_eur)} |")
    lines.append(f"| Invested value | {_fmt_eur(total_value)} |")
    lines.append(f"| Cost basis | {_fmt_eur(total_cost)} |")
    lines.append(f"| P&L | {_fmt_eur(pnl)} ({pnl_pct * 100:+.2f}%) |")
    lines.append(f"| Cash | {_fmt_eur(cash_eur)} |")
    lines.append("")

    # Holdings ----------------------------------------------------------------
    lines.append("## Holdings")
    lines.append("")
    if not valued:
        lines.append("_No positions._")
    else:
        lines.append("| Ticker | Name | Category | Qty | Avg cost (EUR) | Price | Value (EUR) | P&L (EUR) | P&L % |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for v in sorted(valued, key=lambda x: x.market_value_eur, reverse=True):
            t = v.position.ticker
            try:
                cat = config.ticker_to_category(t)
            except KeyError:
                cat = "unassigned"
            lines.append(
                f"| {t} | {names.get(t, t)} | {cat} | {v.position.quantity:,.4f} | "
                f"{v.position.avg_cost_eur:,.2f} | {v.current_price:,.2f} | "
                f"{v.market_value_eur:,.2f} | {v.pnl_eur:+,.2f} | {v.pnl_pct * 100:+.2f}% |"
            )
    lines.append("")

    # Allocation vs target ----------------------------------------------------
    lines.append("## Allocation vs target")
    lines.append("")
    lines.append(f"_Drift threshold: {drift_threshold_pct:.1f}%_")
    lines.append("")
    lines.append("| Category | Current % | Target % | Drift % | Suggested action |")
    lines.append("| --- | ---: | ---: | ---: | --- |")
    for a in compute_rebalance(valued, config, cash_eur):
        drift_pct = (a.current_weight - a.target_weight) * 100
        if abs(drift_pct) < drift_threshold_pct:
            action = "Hold"
        elif a.delta_eur > 0:
            action = f"Buy {_fmt_eur(a.delta_eur)}"
        else:
            action = f"Sell {_fmt_eur(abs(a.delta_eur))}"
        lines.append(
            f"| {a.category} | {a.current_weight * 100:.1f}% | "
            f"{a.target_weight * 100:.1f}% | {drift_pct:+.1f}% | {action} |"
        )
    lines.append("")

    # Income ------------------------------------------------------------------
    net = compute_net(income, tax) if tax else None
    lines.append("## Income estimate (annualised)")
    lines.append("")
    lines.append(
        f"- **Economic income:** {_fmt_eur(income.total_economic_monthly_eur)}/mo "
        f"({_fmt_eur(income.total_economic_annual_eur)}/yr)"
    )
    lines.append(
        f"- **Cash distributions:** {_fmt_eur(income.total_cash_monthly_eur)}/mo "
        f"({_fmt_eur(income.total_cash_annual_eur)}/yr)"
    )
    if net:
        lines.append(
            f"- **Net of tax** (~{tax.rate_pct:.3f}%, Teilfreistellung-aware): "
            f"economic {_fmt_eur(net.total_economic_annual_eur)}/yr · "
            f"cash {_fmt_eur(net.total_cash_annual_eur)}/yr"
        )
    unresolved = [h.ticker for h in income.holdings if not h.resolved]
    if unresolved:
        lines.append(
            f"- ⚠️ No yield for {', '.join(unresolved)} — counted as €0."
        )
    lines.append("")

    lines.append(
        "_Generated by the portfolio dashboard. Estimates only — not financial advice._"
    )
    return "\n".join(lines)


def _render_export(status_md: str) -> None:
    with st.expander("📋 Portfolio status (Markdown)", expanded=True):
        st.caption(
            "Copy this and paste it into ChatGPT or another AI tool for further "
            "analysis. Use the copy icon in the top-right of the block, or download."
        )
        st.code(status_md, language="markdown")
        st.download_button(
            "Download portfolio_status.md",
            data=status_md,
            file_name=f"portfolio_status_{datetime.now():%Y%m%d_%H%M}.md",
            mime="text/markdown",
            key="export_download",
        )


def prepare_import(records, profile: ImportProfile, isin_map, existing_keys):
    """Run the CLI import pipeline (pure): parse → resolve ISINs → dedupe.

    Returns (new_rows, duplicates, unknown_isins, errors). Same building blocks
    as `portfolio import`, so the dashboard and CLI behave identically."""
    rows, errors = parse_rows(records, profile)
    resolved, unknown = resolve_tickers(rows, isin_map)
    new_rows, duplicates = split_new(resolved, existing_keys)
    return new_rows, duplicates, unknown, errors


def _render_import_sidebar() -> None:
    st.sidebar.divider()
    st.sidebar.subheader("Import broker CSV")

    profile_dict = read_import_profile(CONFIG_PATH)
    if profile_dict is None:
        st.sidebar.caption(
            "No import profile yet. Set up the column mapping once via the CLI — "
            "`portfolio import <file.csv>` — then upload here."
        )
        return

    uploaded = st.sidebar.file_uploader(
        "Trade Republic / broker CSV", type=["csv"], key="import_csv",
    )
    if uploaded is None:
        return

    try:
        raw = pd.read_csv(uploaded, dtype=str, keep_default_na=False)
    except Exception as e:  # noqa: BLE001 — surface any parse failure to the user
        st.sidebar.error(f"Cannot read CSV: {e}")
        return
    records = [{str(k): str(v) for k, v in row.items()} for row in raw.to_dict("records")]
    if not records:
        st.sidebar.warning("CSV has no data rows.")
        return

    profile = ImportProfile.from_dict(profile_dict)
    isin_map = read_isin_map(CONFIG_PATH)
    tx_df = load_transactions(TX_PATH)
    existing_keys = {
        dedupe_key(d.date(), t, a, float(q), float(p))
        for d, t, a, q, p in zip(
            tx_df["date"], tx_df["ticker"], tx_df["action"],
            tx_df["quantity"], tx_df["price"],
        )
    }
    new_rows, duplicates, unknown, errors = prepare_import(
        records, profile, isin_map, existing_keys,
    )

    if errors:
        st.sidebar.error(f"{len(errors)} row(s) failed to parse.")
        with st.sidebar.expander("Parse errors"):
            for err in errors:
                st.write(err)
        st.sidebar.caption("Fix the file, or re-run `portfolio import --remap` in the CLI.")
        return
    if unknown:
        st.sidebar.warning(
            f"{len(unknown)} unmapped ISIN(s): {', '.join(unknown)}. "
            "Map them once via the CLI (`portfolio import <file>`), then re-upload."
        )
        return

    st.sidebar.caption(f"{len(new_rows)} new · {len(duplicates)} duplicate(s) skipped")
    if not new_rows:
        st.sidebar.info("Nothing new to import.")
        return

    st.sidebar.dataframe(
        pd.DataFrame([
            {"date": r.date.isoformat(), "ticker": r.ticker, "action": r.action,
             "qty": r.quantity, "price": r.price, "ccy": r.currency}
            for r in sorted(new_rows, key=lambda r: r.date)
        ]),
        use_container_width=True, hide_index=True,
    )
    if not st.sidebar.button(f"Import {len(new_rows)} transaction(s)", key="import_submit"):
        return

    # Same pre-flight guard as the CLI: never append a sell that oversells.
    from portfolio.cli import _check_no_negative_holdings

    msg = _check_no_negative_holdings(tx_df, new_rows)
    if msg:
        st.sidebar.error(msg)
        return
    txs = [
        Transaction(date=r.date, ticker=r.ticker, action=r.action,
                    quantity=r.quantity, price=r.price, currency=r.currency)
        for r in sorted(new_rows, key=lambda r: r.date)
    ]
    append_transactions(TX_PATH, txs)
    _after_write()


def _render_income(report: IncomeReport, names: dict[str, str], tax: TaxConfig) -> None:
    c1, c2 = st.columns([3, 1])
    c1.subheader("Income estimate (annualised)")
    net_mode = c2.toggle("Net of tax", value=False, key="income_net")

    net = compute_net(report, tax) if net_mode else None
    totals = net if net else report
    if net_mode:
        st.caption(
            f"After ~{tax.rate_pct:.3f}% tax, Teilfreistellung-aware "
            "(equity funds 30% exempt). A rough estimate — ignores the Sparer-Pauschbetrag."
        )

    c1, c2 = st.columns(2)
    c1.metric(
        "Economic income",
        f"€{totals.total_economic_monthly_eur:,.2f}/mo",
        f"€{totals.total_economic_annual_eur:,.2f}/yr",
    )
    c2.metric(
        "Cash distributions",
        f"€{totals.total_cash_monthly_eur:,.2f}/mo",
        f"€{totals.total_cash_annual_eur:,.2f}/yr",
    )
    unresolved = [h.ticker for h in report.holdings if not h.resolved]
    if unresolved:
        st.warning(
            f"No yield for {unresolved} — counted as €0. "
            "Set a `proxy` or `yield_pct` under `income:` in config.yaml."
        )
    st.dataframe(
        pd.DataFrame(build_income_rows(report, names, net=net)),
        use_container_width=True, hide_index=True,
    )


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
    st.subheader("Trades")
    c1, c2 = st.columns(2)
    with c1:
        _render_buy_form(config)
    with c2:
        _render_sell_form(positions)
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        _render_cash_form(config)
    with c2:
        _render_targets_form(config)
    st.divider()
    st.subheader("Tickers")
    _render_tickers_form(config)


def _render_buy_form(config) -> None:
    st.caption("Record buy")
    known = sorted(config.all_tickers())
    categories = sorted(config.categories.keys())
    options = known + [SENTINEL]

    selection = st.selectbox("Ticker", options, key="buy_ticker_sel")
    new_text = ""
    category = categories[0] if categories else ""
    if selection == SENTINEL:
        new_text = st.text_input(
            "New ticker", key="buy_new_ticker", placeholder="e.g. WEBG.DE"
        )
        category = st.selectbox("Category", categories, key="buy_category")

    tx_date = st.date_input("Date", value=datetime.now().date(), key="buy_date")
    quantity = st.number_input("Quantity", min_value=0.0, step=1.0, key="buy_qty")
    price = st.number_input("Price", min_value=0.0, step=0.01, key="buy_price")
    currency = st.selectbox("Currency", ["EUR", "USD"], key="buy_currency")

    if not st.button("Record buy", key="buy_submit"):
        return
    try:
        ticker, is_new = resolve_buy_ticker(selection, new_text, SENTINEL)
        if is_new:
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
    # Safe only because _after_write() immediately calls st.rerun(): the pops
    # take effect on the next run, never mutating an active widget key this run.
    _clear_buy_state()
    _after_write()


def _clear_buy_state() -> None:
    for k in (
        # keep in sync with the buy_* widget keys above
        "buy_ticker_sel", "buy_new_ticker", "buy_category",
        "buy_date", "buy_qty", "buy_price", "buy_currency",
    ):
        st.session_state.pop(k, None)


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

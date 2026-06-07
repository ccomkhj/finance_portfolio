# portfolio

> Local-first portfolio tracking for EU self-directed investors. Plain-text
> data, git history, CLI, and Streamlit dashboard. No account, no broker login,
> no hosted personal data.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-pytest-brightgreen.svg)](#develop)
[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://financeportfolio.streamlit.app)

**Live demo:** [financeportfolio.streamlit.app](https://financeportfolio.streamlit.app) — read-only, synthetic data.

![Dashboard](docs/dashboard.png)

## What it does

- Tracks buys and sells from `data/transactions.csv`.
- Reads target weights, cash, ticker categories, income, and tax assumptions from
  `data/config.yaml`.
- Fetches prices, FX, names, and dividend yields through `yfinance`.
- Shows market value, P&L, allocation drift, rebalance amounts, and income
  estimates.
- Runs locally, so your real holdings stay on your machine.

The bundled `data/` files are synthetic demo data. See [DISCLAIMER.md](DISCLAIMER.md)
before using this with real portfolio records.

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ccomkhj/finance_portfolio.git
cd finance_portfolio
uv sync --extra dev
uv run portfolio check
uv run portfolio show
```

Open the editable dashboard:

```bash
uv run portfolio dashboard
```

## Real scenario

The demo portfolio has five synthetic trades, EUR cash, and targets shaped to
the [bubble-aware balanced baseline](docs/STRATEGY.md):

| Category | Target | Purpose |
| --- | ---: | --- |
| bonds | 35% | Stability, income, recession protection |
| global-equity (ETFs) | 30% | Long-term diversified growth |
| cash | 20% | Dry powder for drawdowns |
| gold | 10% | Crisis and currency hedge |
| individual-stocks | 5% | Optional high-conviction names |

Running `uv run portfolio show` on the demo data produced:

```text
TICKER            QTY    AVG EUR      PRICE    VALUE EUR    P&L EUR    P&L %
VWCE.DE       10.0000      98.50     162.36      1623.60     638.60   64.83%
IWDA.AS       12.0000      82.10     123.33      1479.96     494.76   50.22%
IUSA.AS       15.0000      55.80      64.73       970.95     133.95   16.00%
4GLD.DE        3.0000      72.00     121.12       363.36     147.36   68.22%
VUSA.AS        5.0000     105.40     123.14       615.71      88.71   16.83%
EUNA.DE       30.0000       4.80       4.91       147.30       3.30    2.29%

CATEGORY         CURRENT %   TARGET %    DELTA EUR
global-equity       72.71%     30.00%     -2754.96
individual-stocks    0.00%      5.00%       322.54
bonds                2.28%     35.00%      2110.51
gold                 5.63%     10.00%       281.73
cash                19.38%     20.00%        40.18

INCOME (gross)  economic ~6.27/mo (75.21/yr) · cash ~3.22/mo (38.67/yr)   [portfolio income for detail]
```

`DELTA EUR` is the category-level rebalance amount: positive means buy more of
that category, negative means reduce it. Prices and yields are live, so your
numbers will change.

## Use your own portfolio

1. Start fresh:

   ```bash
   uv run portfolio init --force
   ```

2. Add tickers to categories in the dashboard's **Edit** tab, or edit
   `data/config.yaml`.

3. Add trades:

   ```bash
   uv run portfolio add-buy VWCE.DE 10 98.50
   uv run portfolio add-sell VWCE.DE 2 120.00
   ```

4. Or import a broker CSV (e.g. a Trade Republic export):

   ```bash
   uv run portfolio import path/to/trades.csv
   ```

   The first import is interactive: it asks how to map your CSV columns,
   decimal/date style, and each ISIN → yfinance ticker, then saves that
   profile to `config.yaml`. You can do the same entirely in the dashboard:
   drag a CSV into the **Import broker CSV** uploader in the left sidebar and
   it walks you through column mapping and any unknown ISINs the first time,
   then reuses that saved profile on later uploads — with the same parsing,
   de-duplication, and oversell checks, a preview of the new rows, and append
   on confirmation.

5. Validate and inspect:

   ```bash
   uv run portfolio check
   uv run portfolio show
   uv run portfolio income --net
   ```

Keep real broker exports and portfolio data out of public repos. `.gitignore`
already excludes `data/private/`, `data/*.bak`, and `broker_exports/`.

## Public demo

The [live demo](https://financeportfolio.streamlit.app) runs on
[Streamlit Community Cloud](https://share.streamlit.io/). To deploy your own,
point a new app at your fork:

- **Main file path:** `streamlit_app.py`
- **Branch:** `main`
- **Python version:** set **3.12** in *Advanced settings* (Streamlit Cloud does
  not read a `runtime.txt`; the app requires 3.12+).
- **Sharing:** set to **Public** so logged-out visitors can open it.

The entrypoint sets `PORTFOLIO_READ_ONLY=1`, so the demo uses the bundled
synthetic data and hides the Edit tab — no writes are exposed. Streamlit Cloud
installs the pinned dependencies from `requirements.txt` (it does not read
`pyproject.toml`). When live prices are unavailable (e.g. Yahoo throttling the
shared cloud IP), the demo falls back to `data/demo_snapshot.json` and labels the
prices as sample data, so the dashboard always renders.

For public launch and revenue notes, see [docs/PUBLIC_LAUNCH.md](docs/PUBLIC_LAUNCH.md).

## Data files

- `data/transactions.csv`: date, ticker, buy/sell, quantity, price, currency.
- `data/config.yaml`: target weights, ticker categories, cash, income proxies,
  and tax assumptions.
- `data/.price_cache.json`: local price cache, ignored by git.

## Develop

```bash
uv run pytest
```

## License

MIT. See [LICENSE](LICENSE).

# portfolio

> Local-first portfolio tracking for EU self-directed investors. Plain-text
> data, git history, CLI, and Streamlit dashboard. No account, no broker login,
> no hosted personal data.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-pytest-brightgreen.svg)](#develop)

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

The demo portfolio has five synthetic trades, EUR cash, and these targets:

| Category | Target |
| --- | ---: |
| global-equity | 70% |
| us-equity | 15% |
| bonds | 10% |
| cash | 5% |

Running `uv run portfolio show` on the demo data produced:

```text
TICKER            QTY    AVG EUR      PRICE    VALUE EUR    P&L EUR    P&L %
VWCE.DE       10.0000      98.50     162.36      1623.60     638.60   64.83%
IWDA.AS       12.0000      82.10     123.33      1479.96     494.76   50.22%
IUSA.AS       15.0000      55.80      64.73       970.95     133.95   16.00%
VUSA.AS        5.0000     105.40     123.14       615.71      88.71   16.83%
EUNA.DE       30.0000       4.80       4.91       147.30       3.30    2.29%

CATEGORY         CURRENT %   TARGET %    DELTA EUR
global-equity       50.98%     70.00%      1157.70
us-equity           26.06%     15.00%      -673.53
bonds                2.42%     10.00%       461.45
cash                20.53%      5.00%      -945.62

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

4. Or import a broker CSV:

   ```bash
   uv run portfolio import path/to/trades.csv
   ```

5. Validate and inspect:

   ```bash
   uv run portfolio check
   uv run portfolio show
   uv run portfolio income --net
   ```

Keep real broker exports and portfolio data out of public repos. `.gitignore`
already excludes `data/private/`, `data/*.bak`, and `broker_exports/`.

## Public demo

Deploy on [Streamlit Community Cloud](https://share.streamlit.io/) for a safe
public demo. Point a new app at your fork with:

- **Main file path:** `streamlit_app.py`
- **Python version:** 3.12+
- **Branch:** `main`

The entrypoint sets `PORTFOLIO_READ_ONLY=1`, so the demo uses the bundled
synthetic data and hides the Edit tab — no writes are exposed. Streamlit Cloud
installs dependencies from `requirements.txt` (it does not read `pyproject.toml`).

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

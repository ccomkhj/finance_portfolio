# Portfolio Tracker — Design

**Date:** 2026-04-19
**Status:** Approved for implementation planning

## Goal

A private, local-only Python tool to track a Trade Republic investment portfolio (EU + US equities/ETFs), compute P&L and category-level rebalancing hints, and visualize the result in a Streamlit dashboard.

## Scope (v1)

**In scope:**

- Log buys and sells via CSV + CLI helper
- Current market valuation via live yfinance fetch (on every dashboard reload)
- Per-position cost basis, P&L in EUR (handling USD positions with transaction-time and current FX)
- Category-level target allocation with rebalancing deltas (buy/sell amounts in EUR)
- Streamlit dashboard: allocation charts, per-position P&L, target vs actual table

**Explicit non-goals:**

- No dividends, fees, splits tracking (cost basis uses buy/sell only, average-cost method)
- No historical portfolio-value time series (no snapshot storage)
- No tax/lot tracking (FIFO, specific-ID)
- No multi-account support (single Trade Republic portfolio)
- No automated Trade Republic statement import (manual entry only)
- No alerts or notifications

## Architecture

Standard `src/` Python package managed with `uv`. Data files in a sibling `data/` directory, committed to git. Pure-function math modules separated from I/O modules.

```
finance/
├── pyproject.toml                  # uv deps: pandas, yfinance, streamlit, pytest, pyyaml
├── data/
│   ├── transactions.csv            # source of truth (committed)
│   └── config.yaml                 # categories, ticker→category, target weights
├── src/portfolio/
│   ├── __init__.py
│   ├── transactions.py             # read/append CSV, schema validation
│   ├── prices.py                   # yfinance: ticker prices + EUR FX rates
│   ├── positions.py                # pure: transactions → positions (qty + avg cost EUR)
│   ├── valuation.py                # pure: positions + prices → market value, P&L
│   ├── rebalance.py                # pure: valued positions + config → category deltas
│   └── cli.py                      # argparse: add-buy, add-sell, show, check
├── app.py                          # streamlit dashboard
└── tests/
    ├── test_positions.py
    ├── test_valuation.py
    └── test_rebalance.py
```

## Data schemas

### `data/transactions.csv`

```csv
date,ticker,action,quantity,price,currency
2026-01-15,VWCE.DE,buy,10,98.50,EUR
2026-02-03,AAPL,buy,5,185.20,USD
2026-03-10,VWCE.DE,sell,2,102.10,EUR
```

| Column | Type | Notes |
|--------|------|-------|
| `date` | ISO `YYYY-MM-DD` | Transaction date |
| `ticker` | string | yfinance symbol (EU with suffix: `.DE`, `.PA`, `.AS`, `.MI`, `.L`; US plain) |
| `action` | `buy` \| `sell` | Only these two values |
| `quantity` | float | Fractional shares allowed |
| `price` | float | Per-share price in `currency` |
| `currency` | `EUR` \| `USD` | Currency of the `price` column |

**Recommended entry style for Trade Republic:** TR settles every trade in EUR (including US stocks — TR converts internally). Enter the EUR price you actually paid (`EUR_amount_charged / quantity`) with `currency: EUR`. This makes cost basis exact (no FX reconstruction needed) and avoids historical FX lookups entirely.

USD entry is still supported for completeness (e.g., if another broker is ever added): `currency: USD` triggers a historical FX lookup for that transaction's date.

### `data/config.yaml`

```yaml
base_currency: EUR

categories:
  global-equity:
    target_weight: 0.70
    tickers: [VWCE.DE, IWDA.AS]
  us-equity:
    target_weight: 0.15
    tickers: [AAPL, MSFT]
  bonds:
    target_weight: 0.10
    tickers: [AGGH.DE]
  cash:
    target_weight: 0.05
    tickers: []

cash_balance_eur: 1250.00
```

Validation at load:

- `target_weight` values sum to `1.0` (±0.001)
- Every ticker in `transactions.csv` is in exactly one category
- Unknown ticker in a CLI append → fail fast

Cash is a manually maintained EUR balance (v1 simplification — Trade Republic cash flows are not in `transactions.csv`).

## Module interfaces

### `transactions.py` (I/O)

```python
def load_transactions(path: Path) -> pd.DataFrame
def append_transaction(path: Path, tx: Transaction) -> None   # atomic: tmp + rename
```

### `prices.py` (I/O)

```python
def fetch_prices(tickers: list[str]) -> dict[str, float]
def fetch_fx_eur(currencies: list[str]) -> dict[str, float]   # e.g. {"USD": 0.92}
def fetch_historical_fx_eur(currency: str, date: date) -> float
```

### `positions.py` (pure)

```python
@dataclass
class Position:
    ticker: str
    quantity: float
    avg_cost_eur: float       # converted at transaction-date FX if USD
    currency: str             # native currency of the transactions

def compute_positions(transactions: pd.DataFrame) -> list[Position]
```

**Cost basis method:** weighted average cost. Sells reduce quantity at the current avg cost (do not change `avg_cost_eur`). A full sell removes the position. USD transactions contribute to `avg_cost_eur` at the **transaction-date FX rate** (fetched via `prices.fetch_historical_fx_eur`).

### `valuation.py` (pure)

```python
@dataclass
class ValuedPosition:
    position: Position
    current_price: float            # in native currency
    market_value_eur: float          # current_price * qty * current_fx
    pnl_eur: float                   # market_value_eur - (avg_cost_eur * qty)
    pnl_pct: float

def value_positions(
    positions: list[Position],
    prices: dict[str, float],
    fx_rates: dict[str, float],
) -> list[ValuedPosition]
```

USD positions: current market value uses the **current** FX rate. P&L therefore includes both asset return and FX movement — the real experienced return.

### `rebalance.py` (pure)

```python
@dataclass
class RebalanceAction:
    category: str
    current_weight: float
    target_weight: float
    delta_eur: float                 # positive = buy, negative = sell

def compute_rebalance(
    valued_positions: list[ValuedPosition],
    config: Config,
    cash_eur: float,
) -> list[RebalanceAction]
```

Totals include cash. Deltas are at the **category level** (not per-ticker) — the user decides which ticker within a category to adjust.

### `cli.py`

`argparse` console script, registered via `pyproject.toml` `[project.scripts]`:

```bash
portfolio add-buy  <TICKER> <QTY> <PRICE> [--currency USD] [--date YYYY-MM-DD]
portfolio add-sell <TICKER> <QTY> <PRICE> [--currency USD] [--date YYYY-MM-DD]
portfolio show                  # positions table + category drift in terminal
portfolio check                 # validate CSV schema + config coverage
```

Defaults: today's date, `EUR` currency. Appends are atomic (tmp file + rename). Unknown ticker → fail before append.

## Streamlit dashboard (`app.py`)

Single page, live yfinance fetch on each reload.

**Top — Summary bar (4 KPI tiles):** Total market value (EUR), Total cost basis (EUR), Total P&L (EUR + %), Cash (EUR).

**Middle — Allocation (2 charts side-by-side):**
- Pie/donut by category
- Treemap by ticker, colored by category

**Bottom — P&L and Rebalance (2 charts side-by-side):**
- Horizontal bar chart: per-position P&L, green/red, sorted by absolute P&L
- Target vs actual table: category, current %, target %, drift %, action (`Buy €X` / `Sell €X` / `Hold`)
  - `Hold` shown when `|drift| < threshold` (sidebar slider, default 1%)

**Sidebar:** last refresh timestamp, "Refresh prices" button (bypass any Streamlit cache), drift threshold slider (0–5%).

## Error handling

Fail fast at boundaries, trust internal data.

| Boundary | Failure | Response |
|----------|---------|----------|
| Config load | Target weights don't sum to 1.0 | Raise with actual sum |
| Config load | Transaction ticker not in any category | Raise listing orphan tickers |
| CSV load | Missing column / bad date / negative qty | Raise pointing to the row |
| Price fetch | yfinance returns NaN for a ticker | Streamlit warning banner; that position omitted from valuation (not silently zeroed) |
| FX fetch | Rate fetch fails | Hard fail with clear message |

## Testing

`pytest` on pure math modules only. Fixtures are inline DataFrames — no network, no external files.

- `test_positions.py` — single buy; multiple buys (weighted avg); partial sell; full sell removes position; USD buy with FX conversion
- `test_valuation.py` — EUR asset P&L; USD asset P&L with FX move; empty portfolio
- `test_rebalance.py` — drift calc; buy/sell sign convention; weights summing to 1.0 (with cash)

No tests for `prices.py` (thin yfinance wrapper), `cli.py` (thin argparse), or `app.py` (visual).

## Dependencies

Managed by `uv` via `pyproject.toml`:

- `pandas` — DataFrame operations
- `yfinance` — price + FX data
- `streamlit` — dashboard
- `plotly` — charts (pie, treemap, bars) — better than matplotlib for Streamlit
- `pyyaml` — config parsing
- `pytest` (dev) — tests

Python 3.12+.

## Open items for the implementation plan

- Decide Streamlit caching strategy (`@st.cache_data` TTL vs plain live fetch) — design says "live on every reload" but `st.cache_data` with a short TTL is idiomatic and avoids hammering yfinance on rapid reloads
- Confirm yfinance rate-limiting behavior with a batch of ~10–20 tickers
- Decide on a simple logging convention (stdlib `logging` to stderr, probably)

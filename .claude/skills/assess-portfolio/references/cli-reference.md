# `portfolio` CLI reference

Installed as a `uv` console script via `pyproject.toml`. Run all commands from the repo root (`/Users/huijokim/personal/finance`) so the default paths to `data/config.yaml` and `data/transactions.csv` resolve.

All commands accept two global flags:

| Flag | Default | Purpose |
|---|---|---|
| `--config PATH` | `data/config.yaml` | Override the config file path (useful for alternate scenarios / dry-run sandboxes) |
| `--transactions PATH` | `data/transactions.csv` | Override the transactions file path |

Place global flags **before** the subcommand: `uv run portfolio --config other.yaml show`.

## `portfolio check`

Validates `transactions.csv` against `config.yaml` — verifies every ticker in transactions belongs to exactly one configured category.

```
uv run portfolio check
```

**Success output (exit 0):**
```
ok: 4 categories, 5 configured tickers, 5 transactions.
```

**Failure output (exit 1):**
```
error: transaction tickers not in config: ['TSLA']
```

Run this whenever you've edited `config.yaml` or `transactions.csv` by hand. It's the canonical safety check.

## `portfolio show`

Loads data, fetches live prices + FX from yfinance, prints a positions table followed by a category drift table. Requires network.

```
uv run portfolio show
```

**Output:**
```
TICKER            QTY    AVG EUR      PRICE    VALUE EUR    P&L EUR    P&L %
VWCE.DE       10.0000      98.50     153.66      1536.60     551.60   56.00%
...

CATEGORY         CURRENT %   TARGET %    DELTA EUR
global-equity       50.54%     70.00%      1130.79
us-equity           25.40%     15.00%      -604.04
...
```

**Prefer the JSON snapshot** (`scripts/snapshot.sh`) over parsing this output — the columns are space-padded, the widths are fixed by f-string format specifiers, and tiny changes in `cli.py` can break table-parsing ad hoc.

`portfolio show` silently drops positions whose live price came back NaN (usually delisted tickers). The Streamlit app shows a warning banner for those; the CLI does not.

Positions with NaN FX rate (not currently possible since `fetch_fx_eur` raises instead) would raise from `valuation.value_positions`.

## `portfolio add-buy`

Appends a buy transaction atomically (tmp file + fsync + rename — Ctrl-C mid-append cannot corrupt the CSV).

```
uv run portfolio add-buy <TICKER> <QTY> <PRICE> [--currency USD] [--date YYYY-MM-DD]
```

**Arguments:**

| Arg | Type | Notes |
|---|---|---|
| `TICKER` | string | Must already exist in `config.yaml`. The CLI validates this before appending and fails loudly if unknown. |
| `QTY` | float | Fractional shares allowed (Trade Republic supports them) |
| `PRICE` | float | Per-share price in `--currency` |
| `--currency` | `EUR` \| `USD` | Default `EUR`. For Trade Republic, almost always `EUR` — enter the EUR amount charged divided by quantity. |
| `--date` | ISO date | Default today. Use for back-filling historical trades. |

**Examples:**
```bash
uv run portfolio add-buy VWCE.DE 10 98.50                          # today, EUR
uv run portfolio add-buy VWCE.DE 2.5 101.20 --date 2026-04-10      # back-dated
uv run portfolio add-buy AAPL 5 185.00 --currency USD              # USD entry (triggers historical FX)
```

**Unknown ticker error:**
```
error: ticker 'TSLA' is not in config. Known: AAPL, IUSA.AS, IWDA.AS, VWCE.DE, ...
```
Exit code 1. No append occurred — safe to retry.

## `portfolio add-sell`

Identical to `add-buy` but records a sell. Same flags, same atomicity, same pre-append validation.

```
uv run portfolio add-sell VWCE.DE 2 102.10
```

A sell that exceeds held quantity is NOT caught at append time — it's caught later by `compute_positions` when `portfolio show` runs. The error is `ValueError: sell of X TICKER exceeds held Y`. If you hit this, edit `data/transactions.csv` directly to remove the bogus row (git is your audit trail).

## Direct file editing

Both data files are plain text and hand-editable. Editing `data/transactions.csv` directly is the supported way to:

- Fix a typo in a past transaction
- Remove a mistakenly-added sell
- Back-fill a batch of historical trades (faster than calling `add-buy` N times)

After manual edits, always run `portfolio check` to validate.

Editing `data/config.yaml` is the supported way to:

- Add a new category
- Change a target weight (remember: all weights must sum to 1.0 ±0.001)
- Add a new ticker to a category (must not already exist in another category)
- Update `cash_balance_eur` when you deposit or withdraw cash at Trade Republic

After config edits, run `portfolio check` again.

## Streamlit app

Not a CLI subcommand — launched separately:

```
uv run streamlit run app.py
```

The app reads the same `data/config.yaml` and `data/transactions.csv`. Live prices cached for 60s via `@st.cache_data(ttl=60)` — the sidebar "Refresh prices" button clears the cache manually.

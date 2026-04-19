# Data file schemas

Both files live in `data/` and are the source of truth for the tool. Both are hand-editable plain text, committed to git. The tool trusts what's on disk — there is no database, no cache, no second source.

## `data/transactions.csv`

Append-only log of buy and sell events. Order of rows does not matter (sort is applied at load time on the `date` column); historical rows can be inserted anywhere.

### Columns

| Column | Type | Required | Notes |
|---|---|---|---|
| `date` | ISO date (`YYYY-MM-DD`) | yes | Transaction / trade date. Drives historical FX lookup when `currency=USD`. |
| `ticker` | string | yes | Must be a yfinance-quoted symbol AND exist in exactly one `config.yaml` category. |
| `action` | `buy` \| `sell` | yes | Anything else raises `ValueError` at load. |
| `quantity` | float > 0 | yes | Fractional shares allowed (Trade Republic supports them). |
| `price` | float > 0 | yes | Per-share price in `currency`. |
| `currency` | `EUR` \| `USD` | yes | Anything else raises. For Trade Republic, always use `EUR`. |

### Valid example

```csv
date,ticker,action,quantity,price,currency
2026-01-15,VWCE.DE,buy,10,98.50,EUR
2026-02-03,IWDA.AS,buy,12,82.10,EUR
2026-03-10,VWCE.DE,sell,2,102.10,EUR
```

### The `EUR` vs `USD` decision

Trade Republic settles every trade in EUR internally — even US stocks. TR deducts an EUR amount from your account and credits you fractional shares. The **recommended entry style** is therefore:

- `currency: EUR`
- `price: <EUR amount charged> / <quantity>`

This means **cost basis is exact**, with no historical FX reconstruction needed, and no reliance on yfinance's historical FX data (which is fine, but one less moving part).

**Only use `currency: USD` if:**
- You're using a broker other than Trade Republic that denominates in USD, OR
- You have reason to split the currency exposure for reporting (rare — the tool currently doesn't do anything different with USD positions beyond applying historical+current FX).

### Ticker selection

The ticker must be:
1. In exactly one category in `config.yaml`.
2. Quoted by yfinance (verify with `uv run python -c "from portfolio.prices import fetch_prices; print(fetch_prices(['YOUR.TICKER']))"` — NaN means delisted / unavailable).
3. Denominated in the same currency you're recording (`EUR` rows need EUR-denominated listings; `USD` rows need USD-denominated listings). If you enter an EUR-cost for a USD-listed ticker, live valuation silently multiplies by `fx[EUR]=1.0` and produces ~15% wrong market values. The tool cannot detect this mismatch.

Practical EUR-denominated tickers that work on yfinance:

| Asset | Ticker | Exchange |
|---|---|---|
| FTSE All-World (acc) | `VWCE.DE` | Xetra |
| MSCI World (acc) | `IWDA.AS` | Amsterdam |
| S&P 500 (dist) | `IUSA.AS`, `VUSA.AS` | Amsterdam |
| S&P 500 (acc) | `SXR8.DE`, `CSPX.AS` | Xetra / AMS |
| Global aggregate bonds | `EUNA.DE` | Xetra |

## `data/config.yaml`

The targets-and-categories declaration. Every ticker appearing in any transaction **must** appear in exactly one category.

### Shape

```yaml
base_currency: EUR

categories:
  <category-name>:
    target_weight: <float 0..1>
    tickers: [<ticker>, ...]
  # ... more categories

cash_balance_eur: <float>
```

### Validation rules

Enforced by `load_config` on every CLI invocation:

1. **Target weights sum to 1.0** (±0.001). If your weights don't add up, the tool refuses to start. The error message includes the actual sum.
2. **No ticker appears in more than one category.** Violation → `ValueError` naming both categories.
3. **`base_currency`, `categories`, and `cash_balance_eur` keys must be present.** (Missing keys produce a raw `KeyError` from PyYAML — not friendly, but a hand-edit typo will be obvious from the traceback.)

### The `cash` category convention

Cash is modeled as a single EUR balance (`cash_balance_eur`) that flows into the category literally named `"cash"`. If you rename the cash category, the Streamlit app's pie chart loses the cash slice label (hardcoded string — see `app.py:_render_allocation`). Keep the name `cash` unless you also patch `app.py`.

The `cash` category's `tickers` list should be `[]` (empty). Adding tickers to it mixes live-priced positions with the static cash balance and corrupts the category weight calculation.

### `base_currency`

Currently only `EUR` is supported throughout the code. Setting it to anything else doesn't break the loader but will produce nonsense valuations since `value_positions` hard-codes EUR as the report currency.

### `cash_balance_eur`

Maintained by hand. The CLI has no `add-cash` command — when you deposit or withdraw cash at Trade Republic, edit this number directly. `git log data/config.yaml` is your cash-balance audit trail.

## Relationship between the two files

```
transactions.csv tickers  ⊆  config.yaml all_tickers()
```

Every transaction ticker must be known to the config. The CLI `check` command verifies this exact invariant. `portfolio show` and `app.py` also check at startup and refuse to run if orphan tickers exist.

A ticker can exist in config with zero transactions (a planned position that hasn't been purchased yet) — harmless; it just shows 0% current weight and a Buy delta equal to its share of the target allocation.

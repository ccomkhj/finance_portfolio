# Troubleshooting

Error dictionary for the `portfolio` CLI and supporting scripts. Each entry: exact error text, what it means, and the fix.

## From `portfolio check` / `show` / `add-buy`

### `error: transaction tickers not in config: ['X', 'Y']`

**Meaning:** `transactions.csv` contains tickers that aren't in any `config.yaml` category. Usually a typo (`AAPL` vs `AAPL.DE`) or a ticker that was added to transactions but never registered in config.

**Fix:**
- Correct spelling: edit `data/transactions.csv` to fix the typo.
- Intentional new ticker: add it to the appropriate category's `tickers:` list in `data/config.yaml`.
- Run `portfolio check` to re-verify.

### `error: ticker 'X' is not in config. Known: ...`

**Meaning:** `add-buy` / `add-sell` tried to append a ticker that isn't registered in `config.yaml`. The list of known tickers is printed for convenience.

**Fix:** Add the ticker to the right category in `config.yaml` first, then retry the `add-buy`.

### `ValueError: target_weight values sum to 0.900000, expected 1.0`

**Meaning:** `config.yaml` weights don't sum to 1.0 (±0.001). Actual sum is shown — here it's 0.9, so you're 10pp short.

**Fix:** Adjust one or more `target_weight` values to close the gap. The arithmetic: `sum(all weights) == 1.0`. Rounding to 0.05 increments usually works.

### `ValueError: Ticker 'X' appears in both 'a' and 'b'`

**Meaning:** `config.yaml` has the same ticker in two category `tickers:` lists. A ticker can only be in one category.

**Fix:** Remove it from one of the two lists. If the ticker is genuinely split across intent (e.g., you want half as global-equity, half as us-equity), the tool doesn't model that — pick the category that better represents its primary purpose.

### `ValueError: row <N>: invalid action 'hold'`

**Meaning:** `transactions.csv` has a row with an `action` that isn't `buy` or `sell`. Row index in the error is 0-based.

**Fix:** Edit the row. v1 only supports buy/sell — if you're trying to record a dividend, split, or fee, the tool doesn't model those (explicit non-goals in the spec).

### `ValueError: row <N>: invalid currency 'GBP'`

**Meaning:** Currency must be `EUR` or `USD`. Row <N> (0-indexed) is wrong.

**Fix:** Change to `EUR` (Trade Republic default) or `USD` (US broker) in `data/transactions.csv`.

### `ValueError: row <N>: quantity must be > 0, got -3`

**Meaning:** Negative or zero quantity on row N. The tool uses `action=sell` (not negative quantity) to represent sells.

**Fix:** Change `action=buy` + `quantity=-3` → `action=sell` + `quantity=3`.

### `ValueError: sell of 10 VWCE.DE exceeds held 7`

**Meaning:** A `sell` row reduces quantity below zero. Caught at `compute_positions` time, not at append time.

**Fix:**
- If it's a typo: edit `data/transactions.csv`, correct the quantity.
- If you added the sell by mistake: delete that row from `data/transactions.csv`.
- If you legitimately oversold (shouldn't be possible at TR without margin): this is a data model limitation; record a matching buy first or consolidate rows.

### `KeyError: Ticker 'X' is not assigned to any category`

**Meaning:** `ticker_to_category()` was called for a ticker that's not in any category. Usually thrown from `compute_rebalance` or a Streamlit allocation chart when the orphan check was bypassed.

**Fix:** Shouldn't happen during normal use — `check` / `show` / the app all validate coverage first. If it occurs, someone edited data files between the pre-check and the usage. Re-run the command from scratch.

## From yfinance

### `$VWCE.DE: possibly delisted; no price data found (period=5d)`

**Meaning:** Yahoo has no quote for this ticker over the last 5 days. Could be a genuine delisting, a temporary Yahoo data gap, or a wrong symbol.

**Fix:**
1. Verify the ticker actually still trades (Google the ISIN).
2. Try the ticker on a different exchange suffix (`.DE` → `.AS`, `.L`, `.MI`).
3. If genuinely delisted on Yahoo only: swap for an equivalent listing using the recipe in `recipes.md` → "Swap a ticker that went delisted".

The position silently falls out of `portfolio show`'s valuation table and bonds/us-equity/etc. show artificially low current weight. `app.py` shows a warning banner; the CLI does not.

### `RuntimeError: failed to fetch FX rate for USDEUR=X`

**Meaning:** `fetch_fx_eur` couldn't get a rate for that currency. Almost always a transient yfinance outage — the USD/EUR pair doesn't go away.

**Fix:**
- Retry after 10–30s.
- If persistent, check yfinance status (GitHub issues on `ranaroussi/yfinance`).
- As a last resort, the code raises instead of falling back — intentional, since silently wrong FX would corrupt every valuation.

### `RuntimeError: no FX data for USDEUR=X near 2026-01-15`

**Meaning:** Historical FX for a USD transaction's date isn't available. The code searches 7 days before through 1 day after — if no trading day has a close in that window, it gives up.

**Fix:**
- For a TR user, this shouldn't arise — you should be entering rows with `currency=EUR` and the historical FX function is never called.
- If you have USD rows: verify the date isn't a weekend/holiday with no preceding data in a 7-day window (extremely rare); otherwise re-run, likely a transient fetch failure.

### `yfinance` returns a price that doesn't match your broker

**Meaning:** Yahoo's "Close" is the last official close, which for EU listings is yesterday's close during European market hours. Cross-listed tickers can also show different prices between exchanges.

**Fix:** Usually nothing to do — just be aware the "live" price in the app is end-of-day close, not real-time. If the difference is large (>1%), you may be comparing two different listings (e.g., Yahoo's US price vs TR's EU price for the same underlying stock).

## From Streamlit

### App starts but shows a red error about orphan tickers

**Meaning:** `app.py` ran its orphan-check and refused to render. Same root cause as the CLI `error: transaction tickers not in config` message.

**Fix:** Run `uv run portfolio check`, fix per the error above, reload the app.

### App shows "No price available for: X" warning banner

**Meaning:** yfinance returned NaN for ticker X. The position is excluded from the valuation table, allocation charts, and P&L — but still contributes to `cost_basis`. The rebalance table will show that category underweight by the missing position's expected share.

**Fix:** Apply the delisted-ticker recipe or accept that that slice of the portfolio will be invisible until the ticker is swapped.

### App is slow on reload

**Meaning:** yfinance calls are live — can take 2–5 seconds for 5 tickers plus an FX call. `@st.cache_data(ttl=60)` caches for 60s.

**Fix:** Use the sidebar "Refresh prices" button only when you actually want fresh data. Otherwise rapid reloads hit the cache.

## From the snapshot script

### `error: orphan tickers [...]`

Same root cause as the CLI orphan error. Fix in `config.yaml` or `transactions.csv`.

### Script hangs for >30s

yfinance is rate-limited or the connection is flaky. Ctrl-C and retry. No cache to clear — this script does not use Streamlit's cache.

## Generic environment

### `ModuleNotFoundError: No module named 'portfolio'`

**Meaning:** Running Python outside `uv`'s venv, or the package wasn't installed.

**Fix:** Prefix commands with `uv run`. If that still fails, `uv sync --extra dev` to reinstall.

### `command not found: portfolio`

**Meaning:** Console script entry point not registered. Usually means the venv isn't active or `uv sync` hasn't been run since `pyproject.toml` was last edited.

**Fix:** `uv sync --extra dev`, then `uv run portfolio check` to verify.

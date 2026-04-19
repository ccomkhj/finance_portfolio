# portfolio

Private tracker for a Trade Republic portfolio. Transactions live in CSV, targets live in YAML, git is the audit trail.

## Setup

```bash
uv sync --extra dev
```

## How it works

1. You record each trade with `add-buy` / `add-sell` (or edit `data/transactions.csv` by hand).
2. `show` fetches live prices via yfinance and prints positions + drift vs. target weights.
3. The Streamlit dashboard (`app.py`) is the same data, visual.

For Trade Republic trades, enter the EUR price you actually paid (`EUR_charged / quantity`) — no FX lookup needed.

## Daily use

```bash
# Record a buy (defaults to today, EUR)
uv run portfolio add-buy VWCE.DE 10 98.50

# Record a sell
uv run portfolio add-sell VWCE.DE 2 120.00 --date 2026-04-18

# Validate data files (CSV schema, ticker→category mapping, target weights sum to 1)
uv run portfolio check

# Terminal snapshot
uv run portfolio show

# Dashboard
uv run streamlit run app.py
```

### Sample `show` output

```
TICKER            QTY    AVG EUR      PRICE    VALUE EUR    P&L EUR    P&L %
VWCE.DE       10.0000      98.50     153.66      1536.60     551.60   56.00%
IWDA.AS       12.0000      82.10     116.68      1400.10     414.90   42.11%
IUSA.AS       15.0000      55.80      60.20       903.06      66.06    7.89%
VUSA.AS        5.0000     105.40     114.52       572.58      45.58    8.65%
EUNA.DE       30.0000       4.80       4.95       148.36       4.36    3.03%

CATEGORY         CURRENT %   TARGET %    DELTA EUR
global-equity       50.54%     70.00%      1130.79
us-equity           25.40%     15.00%      -604.04
bonds                2.55%     10.00%       432.71
cash                21.51%      5.00%      -959.47
```

`DELTA EUR` is how much to buy (+) or sell (−) to hit the target weight.

## Editing data

- `data/transactions.csv` — buys and sells, source of truth
- `data/config.yaml` — categories, ticker→category mapping, target weights, cash balance

Both are hand-editable; run `portfolio check` after manual edits.

## Tests

```bash
uv run pytest
```

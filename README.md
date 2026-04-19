# portfolio

Private tracker for a Trade Republic portfolio.

## Setup

```bash
uv sync --extra dev
```

## Daily use

```bash
# Record a buy (defaults to today, EUR)
uv run portfolio add-buy VWCE.DE 10 98.50

# Validate the data files
uv run portfolio check

# Terminal snapshot
uv run portfolio show

# Dashboard
uv run streamlit run app.py
```

## Editing data

- `data/transactions.csv` — buys and sells, source of truth
- `data/config.yaml` — categories, ticker-to-category mapping, target weights, cash balance

Both files are hand-editable; git is the audit trail. For Trade Republic trades, enter the EUR price you actually paid (`EUR_charged / quantity`) so no historical FX lookup is needed.

## Tests

```bash
uv run pytest
```

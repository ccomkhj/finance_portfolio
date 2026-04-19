# Portfolio Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only Python tool that tracks a Trade Republic portfolio from a CSV transaction log, computes EUR-denominated P&L against live yfinance prices, produces category-level rebalancing hints, and surfaces everything in a Streamlit dashboard.

**Architecture:** `src/` layout Python package managed with `uv`. Pure-function math modules (`positions`, `valuation`, `rebalance`) separated from I/O modules (`transactions`, `prices`, `config`). Data files (`data/transactions.csv`, `data/config.yaml`) are the source of truth, committed to git. CLI helper (`cli.py`) appends transactions atomically. Streamlit app (`app.py`) is the only UI.

**Tech Stack:** Python 3.12, `uv`, `pandas`, `yfinance`, `streamlit`, `plotly`, `pyyaml`, `pytest`.

**Reference spec:** `docs/superpowers/specs/2026-04-19-portfolio-tracker-design.md`

**Implementation note:** The spec lists six modules (`transactions`, `prices`, `positions`, `valuation`, `rebalance`, `cli`). This plan introduces a seventh, `config.py`, to host the YAML load + validation logic — `config.yaml` is read by `transactions`, `cli`, and `rebalance`, so a shared module is cleaner than duplicating load/validation.

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/portfolio/__init__.py`
- Create: `tests/__init__.py`
- Create directories: `data/`, `reports/`

- [ ] **Step 1: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.venv/
.DS_Store
/dist/
/build/
*.egg-info/
/reports/*.png
/reports/*.html
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "portfolio"
version = "0.1.0"
description = "Private portfolio tracker for Trade Republic"
requires-python = ">=3.12"
dependencies = [
    "pandas>=2.2",
    "yfinance>=0.2.40",
    "streamlit>=1.35",
    "plotly>=5.22",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.5",
]

[project.scripts]
portfolio = "portfolio.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/portfolio"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 3: Create package init files**

```bash
mkdir -p src/portfolio tests data reports
touch src/portfolio/__init__.py tests/__init__.py
```

Contents of `src/portfolio/__init__.py`:
```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Install dependencies with uv**

Run: `uv sync --extra dev`
Expected: Creates `.venv/`, resolves and installs all deps, writes `uv.lock`.

- [ ] **Step 5: Smoke test the install**

Run: `uv run python -c "import portfolio; import pandas; import yfinance; import streamlit; import plotly; import yaml; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore uv.lock src/portfolio/__init__.py tests/__init__.py
git commit -m "chore: scaffold portfolio package with uv"
```

---

## Task 2: Config module (`config.py`)

**Files:**
- Create: `src/portfolio/config.py`
- Test: `tests/test_config.py`

This module loads and validates `data/config.yaml`. Validation rules: `target_weight` values across all categories must sum to 1.0 (±0.001); every ticker must appear in exactly one category.

- [ ] **Step 1: Write failing test for happy path**

`tests/test_config.py`:
```python
from pathlib import Path

import pytest
import yaml

from portfolio.config import Category, Config, load_config


def write_yaml(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_load_config_happy_path(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        {
            "base_currency": "EUR",
            "categories": {
                "equity": {"target_weight": 0.8, "tickers": ["VWCE.DE"]},
                "cash": {"target_weight": 0.2, "tickers": []},
            },
            "cash_balance_eur": 1000.0,
        },
    )
    config = load_config(path)

    assert isinstance(config, Config)
    assert config.base_currency == "EUR"
    assert config.cash_balance_eur == 1000.0
    assert set(config.categories) == {"equity", "cash"}
    assert config.categories["equity"] == Category(
        name="equity", target_weight=0.8, tickers=("VWCE.DE",)
    )
    assert config.ticker_to_category("VWCE.DE") == "equity"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio.config'`.

- [ ] **Step 3: Implement `config.py`**

`src/portfolio/config.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

WEIGHT_SUM_TOLERANCE = 0.001


@dataclass(frozen=True)
class Category:
    name: str
    target_weight: float
    tickers: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    base_currency: str
    categories: dict[str, Category]
    cash_balance_eur: float

    def ticker_to_category(self, ticker: str) -> str:
        for cat in self.categories.values():
            if ticker in cat.tickers:
                return cat.name
        raise KeyError(f"Ticker {ticker!r} is not assigned to any category")

    def all_tickers(self) -> set[str]:
        return {t for cat in self.categories.values() for t in cat.tickers}


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text())
    categories = {
        name: Category(
            name=name,
            target_weight=float(body["target_weight"]),
            tickers=tuple(body.get("tickers", [])),
        )
        for name, body in raw["categories"].items()
    }

    _validate_weights(categories)
    _validate_unique_tickers(categories)

    return Config(
        base_currency=raw["base_currency"],
        categories=categories,
        cash_balance_eur=float(raw["cash_balance_eur"]),
    )


def _validate_weights(categories: dict[str, Category]) -> None:
    total = sum(c.target_weight for c in categories.values())
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValueError(f"target_weight values sum to {total:.6f}, expected 1.0")


def _validate_unique_tickers(categories: dict[str, Category]) -> None:
    seen: dict[str, str] = {}
    for cat in categories.values():
        for ticker in cat.tickers:
            if ticker in seen:
                raise ValueError(
                    f"Ticker {ticker!r} appears in both {seen[ticker]!r} and {cat.name!r}"
                )
            seen[ticker] = cat.name
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Add failing tests for validation errors**

Append to `tests/test_config.py`:
```python
def test_load_config_weights_must_sum_to_one(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        {
            "base_currency": "EUR",
            "categories": {
                "equity": {"target_weight": 0.7, "tickers": ["VWCE.DE"]},
                "cash": {"target_weight": 0.2, "tickers": []},
            },
            "cash_balance_eur": 0.0,
        },
    )
    with pytest.raises(ValueError, match="sum to 0.900000"):
        load_config(path)


def test_load_config_rejects_duplicate_tickers(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        {
            "base_currency": "EUR",
            "categories": {
                "a": {"target_weight": 0.5, "tickers": ["VWCE.DE"]},
                "b": {"target_weight": 0.5, "tickers": ["VWCE.DE"]},
            },
            "cash_balance_eur": 0.0,
        },
    )
    with pytest.raises(ValueError, match="appears in both"):
        load_config(path)


def test_ticker_to_category_raises_for_unknown(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        {
            "base_currency": "EUR",
            "categories": {
                "equity": {"target_weight": 1.0, "tickers": ["VWCE.DE"]},
            },
            "cash_balance_eur": 0.0,
        },
    )
    config = load_config(path)
    with pytest.raises(KeyError, match="AAPL"):
        config.ticker_to_category("AAPL")
```

- [ ] **Step 6: Run all config tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: 4 PASS.

- [ ] **Step 7: Commit**

```bash
git add src/portfolio/config.py tests/test_config.py
git commit -m "feat(config): load and validate portfolio config"
```

---

## Task 3: Transactions module (`transactions.py`)

**Files:**
- Create: `src/portfolio/transactions.py`
- Test: `tests/test_transactions.py`

This module reads `transactions.csv` into a validated DataFrame and atomically appends new rows. Schema: `date, ticker, action, quantity, price, currency`.

- [ ] **Step 1: Write failing test for load**

`tests/test_transactions.py`:
```python
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from portfolio.transactions import Transaction, append_transaction, load_transactions

CSV_HEADER = "date,ticker,action,quantity,price,currency\n"


def write_csv(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "transactions.csv"
    path.write_text(CSV_HEADER + rows)
    return path


def test_load_transactions_parses_types(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        "2026-01-15,VWCE.DE,buy,10,98.50,EUR\n"
        "2026-02-03,AAPL,buy,5.5,185.20,USD\n",
    )

    df = load_transactions(path)

    assert list(df.columns) == ["date", "ticker", "action", "quantity", "price", "currency"]
    assert df["date"].dtype == "datetime64[ns]"
    assert df.loc[0, "date"] == pd.Timestamp("2026-01-15")
    assert df.loc[1, "quantity"] == 5.5
    assert df.loc[1, "currency"] == "USD"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_transactions.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement load + validation**

`src/portfolio/transactions.py`:
```python
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = ["date", "ticker", "action", "quantity", "price", "currency"]
VALID_ACTIONS = {"buy", "sell"}
VALID_CURRENCIES = {"EUR", "USD"}


@dataclass(frozen=True)
class Transaction:
    date: date
    ticker: str
    action: str
    quantity: float
    price: float
    currency: str


def load_transactions(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"ticker": str, "action": str, "currency": str})

    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"transactions.csv missing columns: {sorted(missing)}")

    df = df[REQUIRED_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="raise")
    df["quantity"] = df["quantity"].astype(float)
    df["price"] = df["price"].astype(float)

    _validate_rows(df)
    return df


def _validate_rows(df: pd.DataFrame) -> None:
    bad_actions = df.loc[~df["action"].isin(VALID_ACTIONS)]
    if not bad_actions.empty:
        row = bad_actions.iloc[0]
        raise ValueError(f"row {row.name}: invalid action {row['action']!r}")

    bad_currencies = df.loc[~df["currency"].isin(VALID_CURRENCIES)]
    if not bad_currencies.empty:
        row = bad_currencies.iloc[0]
        raise ValueError(f"row {row.name}: invalid currency {row['currency']!r}")

    bad_qty = df.loc[df["quantity"] <= 0]
    if not bad_qty.empty:
        row = bad_qty.iloc[0]
        raise ValueError(f"row {row.name}: quantity must be > 0, got {row['quantity']}")

    bad_price = df.loc[df["price"] <= 0]
    if not bad_price.empty:
        row = bad_price.iloc[0]
        raise ValueError(f"row {row.name}: price must be > 0, got {row['price']}")


def append_transaction(path: Path, tx: Transaction) -> None:
    """Append a transaction row atomically (write temp file, fsync, rename)."""
    if tx.action not in VALID_ACTIONS:
        raise ValueError(f"invalid action {tx.action!r}")
    if tx.currency not in VALID_CURRENCIES:
        raise ValueError(f"invalid currency {tx.currency!r}")
    if tx.quantity <= 0 or tx.price <= 0:
        raise ValueError("quantity and price must be > 0")

    existing = path.read_text() if path.exists() else "date,ticker,action,quantity,price,currency\n"
    new_row = (
        f"{tx.date.isoformat()},{tx.ticker},{tx.action},"
        f"{tx.quantity},{tx.price},{tx.currency}\n"
    )

    dir_ = path.parent
    dir_.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dir_, prefix=".transactions.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as tmp:
            tmp.write(existing + new_row)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    except Exception:
        if Path(tmp_name).exists():
            os.unlink(tmp_name)
        raise
```

- [ ] **Step 4: Run the first test to verify it passes**

Run: `uv run pytest tests/test_transactions.py::test_load_transactions_parses_types -v`
Expected: PASS.

- [ ] **Step 5: Add validation + append tests**

Append to `tests/test_transactions.py`:
```python
def test_load_transactions_rejects_bad_action(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "2026-01-15,VWCE.DE,hold,10,98.50,EUR\n")
    with pytest.raises(ValueError, match="invalid action 'hold'"):
        load_transactions(path)


def test_load_transactions_rejects_bad_currency(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "2026-01-15,VWCE.DE,buy,10,98.50,GBP\n")
    with pytest.raises(ValueError, match="invalid currency 'GBP'"):
        load_transactions(path)


def test_load_transactions_rejects_nonpositive_quantity(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "2026-01-15,VWCE.DE,buy,0,98.50,EUR\n")
    with pytest.raises(ValueError, match="quantity must be > 0"):
        load_transactions(path)


def test_append_transaction_creates_file_with_header(tmp_path: Path) -> None:
    path = tmp_path / "transactions.csv"
    tx = Transaction(
        date=date(2026, 1, 15),
        ticker="VWCE.DE",
        action="buy",
        quantity=10.0,
        price=98.50,
        currency="EUR",
    )
    append_transaction(path, tx)

    content = path.read_text()
    assert content == (
        "date,ticker,action,quantity,price,currency\n"
        "2026-01-15,VWCE.DE,buy,10.0,98.5,EUR\n"
    )


def test_append_transaction_preserves_existing_rows(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "2026-01-15,VWCE.DE,buy,10,98.50,EUR\n")
    tx = Transaction(
        date=date(2026, 2, 3),
        ticker="AAPL",
        action="buy",
        quantity=5.0,
        price=185.20,
        currency="USD",
    )
    append_transaction(path, tx)

    df = load_transactions(path)
    assert len(df) == 2
    assert df.iloc[1]["ticker"] == "AAPL"
```

- [ ] **Step 6: Run all transaction tests**

Run: `uv run pytest tests/test_transactions.py -v`
Expected: 5 PASS.

- [ ] **Step 7: Commit**

```bash
git add src/portfolio/transactions.py tests/test_transactions.py
git commit -m "feat(transactions): load, validate, and atomically append"
```

---

## Task 4: Sample data files

**Files:**
- Create: `data/config.yaml`
- Create: `data/transactions.csv`

Seed data so the rest of the modules can be exercised end-to-end. Small but realistic.

- [ ] **Step 1: Create `data/config.yaml`**

```yaml
base_currency: EUR

categories:
  global-equity:
    target_weight: 0.70
    tickers:
      - VWCE.DE
      - IWDA.AS
  us-equity:
    target_weight: 0.15
    tickers:
      - AAPL
      - MSFT
  bonds:
    target_weight: 0.10
    tickers:
      - AGGH.DE
  cash:
    target_weight: 0.05
    tickers: []

cash_balance_eur: 1250.00
```

- [ ] **Step 2: Create `data/transactions.csv`**

```csv
date,ticker,action,quantity,price,currency
2026-01-15,VWCE.DE,buy,10,98.50,EUR
2026-02-03,IWDA.AS,buy,12,82.10,EUR
2026-02-10,AAPL,buy,3,172.40,EUR
2026-03-01,MSFT,buy,2,380.00,EUR
2026-03-15,AGGH.DE,buy,50,5.20,EUR
```

Note: prices are the **EUR amount Trade Republic actually charged per share** (see spec's "Recommended entry style for Trade Republic" note). `currency=EUR` throughout.

- [ ] **Step 3: Verify load works end-to-end**

Run:
```bash
uv run python -c "
from pathlib import Path
from portfolio.config import load_config
from portfolio.transactions import load_transactions

config = load_config(Path('data/config.yaml'))
tx = load_transactions(Path('data/transactions.csv'))
print(f'Config: {len(config.categories)} categories, {len(config.all_tickers())} tickers')
print(f'Transactions: {len(tx)} rows')
for t in sorted(set(tx['ticker'])):
    assert t in config.all_tickers(), f'{t} not in config'
print('All transaction tickers are known to config.')
"
```
Expected: Prints 4 categories, 5 tickers, 5 rows, and the "known to config" line.

- [ ] **Step 4: Commit**

```bash
git add data/config.yaml data/transactions.csv
git commit -m "chore: seed sample config and transactions"
```

---

## Task 5: Positions module (`positions.py`)

**Files:**
- Create: `src/portfolio/positions.py`
- Test: `tests/test_positions.py`

Pure function — takes a DataFrame with a `cost_eur` column (already FX-converted) and returns `list[Position]` using weighted-average cost. Sells reduce quantity; a fully-sold position is dropped.

Upstream I/O (historical FX for USD rows) is handled by a separate `enrich_transactions_with_eur` helper in this same module, which accepts an injectable `historical_fx` callable so tests stay pure.

- [ ] **Step 1: Write failing test — single buy**

`tests/test_positions.py`:
```python
from datetime import date

import pandas as pd
import pytest

from portfolio.positions import (
    Position,
    compute_positions,
    enrich_transactions_with_eur,
)


def tx_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_compute_positions_single_buy() -> None:
    df = tx_df([
        {"date": "2026-01-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 10.0, "price": 98.50, "currency": "EUR", "cost_eur": 985.0},
    ])

    positions = compute_positions(df)

    assert positions == [
        Position(ticker="VWCE.DE", quantity=10.0, avg_cost_eur=98.50, currency="EUR")
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_positions.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement minimal `positions.py`**

`src/portfolio/positions.py`:
```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date as Date

import pandas as pd


@dataclass(frozen=True)
class Position:
    ticker: str
    quantity: float
    avg_cost_eur: float
    currency: str


def enrich_transactions_with_eur(
    df: pd.DataFrame,
    historical_fx: Callable[[str, Date], float],
) -> pd.DataFrame:
    """Add a `cost_eur` column = quantity * price * FX(date).

    For EUR rows, FX = 1.0. For USD rows, `historical_fx("USD", date)` is called to
    obtain USD->EUR (i.e., how many EUR per 1 USD on that date).
    """
    def row_cost(row: pd.Series) -> float:
        if row["currency"] == "EUR":
            rate = 1.0
        else:
            rate = historical_fx(row["currency"], row["date"].date())
        return row["quantity"] * row["price"] * rate

    out = df.copy()
    out["cost_eur"] = out.apply(row_cost, axis=1)
    return out


def compute_positions(transactions: pd.DataFrame) -> list[Position]:
    """Collapse buy/sell transactions into current positions using avg-cost basis."""
    if "cost_eur" not in transactions.columns:
        raise ValueError("transactions DataFrame must include a 'cost_eur' column")

    state: dict[str, dict] = {}
    for _, row in transactions.sort_values("date").iterrows():
        ticker = row["ticker"]
        s = state.setdefault(ticker, {
            "quantity": 0.0, "cost_eur": 0.0, "currency": row["currency"]
        })

        if row["action"] == "buy":
            s["quantity"] += row["quantity"]
            s["cost_eur"] += row["cost_eur"]
        elif row["action"] == "sell":
            if row["quantity"] > s["quantity"] + 1e-9:
                raise ValueError(
                    f"sell of {row['quantity']} {ticker} exceeds held {s['quantity']}"
                )
            avg = s["cost_eur"] / s["quantity"] if s["quantity"] else 0.0
            s["quantity"] -= row["quantity"]
            s["cost_eur"] -= avg * row["quantity"]
        else:
            raise ValueError(f"unknown action {row['action']!r}")

    positions: list[Position] = []
    for ticker, s in state.items():
        if s["quantity"] <= 1e-9:
            continue
        avg_cost = s["cost_eur"] / s["quantity"]
        positions.append(Position(
            ticker=ticker,
            quantity=s["quantity"],
            avg_cost_eur=avg_cost,
            currency=s["currency"],
        ))
    return positions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_positions.py::test_compute_positions_single_buy -v`
Expected: PASS.

- [ ] **Step 5: Add remaining pure-math tests**

Append to `tests/test_positions.py`:
```python
def test_compute_positions_multiple_buys_weighted_average() -> None:
    df = tx_df([
        {"date": "2026-01-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 10.0, "price": 98.50, "currency": "EUR", "cost_eur": 985.0},
        {"date": "2026-02-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 10.0, "price": 101.50, "currency": "EUR", "cost_eur": 1015.0},
    ])

    [pos] = compute_positions(df)

    assert pos.quantity == 20.0
    assert pos.avg_cost_eur == pytest.approx(100.0)


def test_compute_positions_partial_sell_keeps_avg_cost() -> None:
    df = tx_df([
        {"date": "2026-01-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 10.0, "price": 100.0, "currency": "EUR", "cost_eur": 1000.0},
        {"date": "2026-02-15", "ticker": "VWCE.DE", "action": "sell",
         "quantity": 3.0, "price": 120.0, "currency": "EUR", "cost_eur": 360.0},
    ])

    [pos] = compute_positions(df)

    assert pos.quantity == 7.0
    assert pos.avg_cost_eur == pytest.approx(100.0)


def test_compute_positions_full_sell_removes_position() -> None:
    df = tx_df([
        {"date": "2026-01-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 10.0, "price": 100.0, "currency": "EUR", "cost_eur": 1000.0},
        {"date": "2026-02-15", "ticker": "VWCE.DE", "action": "sell",
         "quantity": 10.0, "price": 120.0, "currency": "EUR", "cost_eur": 1200.0},
    ])

    assert compute_positions(df) == []


def test_compute_positions_rejects_oversell() -> None:
    df = tx_df([
        {"date": "2026-01-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 5.0, "price": 100.0, "currency": "EUR", "cost_eur": 500.0},
        {"date": "2026-02-15", "ticker": "VWCE.DE", "action": "sell",
         "quantity": 10.0, "price": 120.0, "currency": "EUR", "cost_eur": 1200.0},
    ])

    with pytest.raises(ValueError, match="exceeds held"):
        compute_positions(df)


def test_enrich_transactions_with_eur_uses_fx_for_usd() -> None:
    df = tx_df([
        {"date": "2026-01-15", "ticker": "VWCE.DE", "action": "buy",
         "quantity": 10.0, "price": 100.0, "currency": "EUR"},
        {"date": "2026-02-03", "ticker": "AAPL", "action": "buy",
         "quantity": 5.0, "price": 200.0, "currency": "USD"},
    ])
    fx_table = {("USD", Date(2026, 2, 3)): 0.92}
    out = enrich_transactions_with_eur(df, lambda c, d: fx_table[(c, d)])

    assert out.loc[0, "cost_eur"] == pytest.approx(1000.0)
    assert out.loc[1, "cost_eur"] == pytest.approx(5 * 200 * 0.92)
```

Note: add `from datetime import date as Date` at the top of `tests/test_positions.py` if not already present.

- [ ] **Step 6: Run all positions tests**

Run: `uv run pytest tests/test_positions.py -v`
Expected: 6 PASS.

- [ ] **Step 7: Commit**

```bash
git add src/portfolio/positions.py tests/test_positions.py
git commit -m "feat(positions): avg-cost basis with injectable FX enrichment"
```

---

## Task 6: Prices module (`prices.py`)

**Files:**
- Create: `src/portfolio/prices.py`

Thin wrappers around `yfinance`. No unit tests (network-dependent; would need mocking that obscures the thin wrapper). A manual smoke test at the end validates it.

- [ ] **Step 1: Implement `prices.py`**

`src/portfolio/prices.py`:
```python
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import yfinance as yf


def fetch_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch latest closing price for each ticker. NaN prices are included."""
    if not tickers:
        return {}
    data = yf.download(
        tickers=tickers,
        period="5d",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
    )

    prices: dict[str, float] = {}
    for ticker in tickers:
        try:
            closes = data[ticker]["Close"] if len(tickers) > 1 else data["Close"]
        except KeyError:
            prices[ticker] = float("nan")
            continue
        closes = closes.dropna()
        prices[ticker] = float(closes.iloc[-1]) if len(closes) else float("nan")
    return prices


def fetch_fx_eur(currencies: list[str]) -> dict[str, float]:
    """Return currency->EUR rate (i.e., how many EUR 1 unit of `currency` buys).

    EUR is always 1.0. For others, uses yfinance `<CUR>EUR=X` pair.
    """
    rates: dict[str, float] = {}
    for cur in currencies:
        if cur == "EUR":
            rates[cur] = 1.0
            continue
        pair = f"{cur}EUR=X"
        data = yf.Ticker(pair).history(period="5d", interval="1d", auto_adjust=False)
        closes = data["Close"].dropna()
        if len(closes) == 0:
            raise RuntimeError(f"failed to fetch FX rate for {pair}")
        rates[cur] = float(closes.iloc[-1])
    return rates


def fetch_historical_fx_eur(currency: str, target_date: date) -> float:
    """Return currency->EUR rate on `target_date` (uses nearest prior trading day)."""
    if currency == "EUR":
        return 1.0
    pair = f"{currency}EUR=X"
    start = target_date - timedelta(days=7)
    end = target_date + timedelta(days=1)
    data = yf.Ticker(pair).history(
        start=start.isoformat(), end=end.isoformat(), interval="1d", auto_adjust=False
    )
    closes = data["Close"].dropna()
    if len(closes) == 0:
        raise RuntimeError(f"no FX data for {pair} near {target_date}")
    return float(closes.iloc[-1])
```

- [ ] **Step 2: Manual network smoke test**

Run:
```bash
uv run python -c "
from portfolio.prices import fetch_prices, fetch_fx_eur
p = fetch_prices(['VWCE.DE', 'AAPL'])
print('prices:', p)
fx = fetch_fx_eur(['EUR', 'USD'])
print('fx:', fx)
assert p['VWCE.DE'] > 0
assert p['AAPL'] > 0
assert fx['EUR'] == 1.0
assert 0.5 < fx['USD'] < 1.5
print('ok')
"
```
Expected: Prints prices (positive floats) and FX (USD around 0.8–1.0), then `ok`. If this fails due to network/yfinance issues, retry; do not silently mask failures in the code.

- [ ] **Step 3: Commit**

```bash
git add src/portfolio/prices.py
git commit -m "feat(prices): yfinance wrappers for prices and FX"
```

---

## Task 7: Valuation module (`valuation.py`)

**Files:**
- Create: `src/portfolio/valuation.py`
- Test: `tests/test_valuation.py`

Pure function. `value_positions(positions, prices, fx_rates) -> list[ValuedPosition]`. USD positions convert market value to EUR at the current FX rate; P&L therefore includes both asset return and FX move.

- [ ] **Step 1: Write failing tests**

`tests/test_valuation.py`:
```python
import pytest

from portfolio.positions import Position
from portfolio.valuation import ValuedPosition, value_positions


def test_value_positions_eur_asset_profit() -> None:
    positions = [Position(ticker="VWCE.DE", quantity=10.0, avg_cost_eur=100.0, currency="EUR")]
    prices = {"VWCE.DE": 110.0}
    fx = {"EUR": 1.0}

    [vp] = value_positions(positions, prices, fx)

    assert vp.current_price == 110.0
    assert vp.market_value_eur == pytest.approx(1100.0)
    assert vp.pnl_eur == pytest.approx(100.0)
    assert vp.pnl_pct == pytest.approx(0.10)


def test_value_positions_usd_asset_with_fx_move() -> None:
    positions = [Position(ticker="AAPL", quantity=5.0, avg_cost_eur=180.0, currency="USD")]
    prices = {"AAPL": 200.0}
    fx = {"USD": 0.90}

    [vp] = value_positions(positions, prices, fx)

    assert vp.market_value_eur == pytest.approx(5 * 200 * 0.90)
    assert vp.pnl_eur == pytest.approx(5 * 200 * 0.90 - 5 * 180.0)


def test_value_positions_skips_nan_price() -> None:
    positions = [
        Position(ticker="VWCE.DE", quantity=10.0, avg_cost_eur=100.0, currency="EUR"),
        Position(ticker="UNKNOWN", quantity=5.0, avg_cost_eur=50.0, currency="EUR"),
    ]
    prices = {"VWCE.DE": 110.0, "UNKNOWN": float("nan")}
    fx = {"EUR": 1.0}

    vps = value_positions(positions, prices, fx)

    assert len(vps) == 1
    assert vps[0].position.ticker == "VWCE.DE"


def test_value_positions_empty_input() -> None:
    assert value_positions([], {}, {"EUR": 1.0}) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_valuation.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `valuation.py`**

`src/portfolio/valuation.py`:
```python
from __future__ import annotations

import math
from dataclasses import dataclass

from portfolio.positions import Position


@dataclass(frozen=True)
class ValuedPosition:
    position: Position
    current_price: float
    market_value_eur: float
    pnl_eur: float
    pnl_pct: float


def value_positions(
    positions: list[Position],
    prices: dict[str, float],
    fx_rates: dict[str, float],
) -> list[ValuedPosition]:
    out: list[ValuedPosition] = []
    for pos in positions:
        price = prices.get(pos.ticker, float("nan"))
        if math.isnan(price):
            continue
        fx = fx_rates.get(pos.currency, float("nan"))
        if math.isnan(fx):
            raise KeyError(f"missing FX rate for {pos.currency}")

        market_value_eur = pos.quantity * price * fx
        cost_basis_eur = pos.quantity * pos.avg_cost_eur
        pnl_eur = market_value_eur - cost_basis_eur
        pnl_pct = pnl_eur / cost_basis_eur if cost_basis_eur else 0.0

        out.append(ValuedPosition(
            position=pos,
            current_price=price,
            market_value_eur=market_value_eur,
            pnl_eur=pnl_eur,
            pnl_pct=pnl_pct,
        ))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_valuation.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/valuation.py tests/test_valuation.py
git commit -m "feat(valuation): EUR-denominated P&L with live FX"
```

---

## Task 8: Rebalance module (`rebalance.py`)

**Files:**
- Create: `src/portfolio/rebalance.py`
- Test: `tests/test_rebalance.py`

Pure function. Aggregates valued positions by category, compares to target weights, emits `RebalanceAction` per category with a signed EUR delta. Total portfolio value = sum(valued market values) + cash.

- [ ] **Step 1: Write failing tests**

`tests/test_rebalance.py`:
```python
import pytest

from portfolio.config import Category, Config
from portfolio.positions import Position
from portfolio.rebalance import RebalanceAction, compute_rebalance
from portfolio.valuation import ValuedPosition


def vp(ticker: str, currency: str, market_value_eur: float) -> ValuedPosition:
    pos = Position(ticker=ticker, quantity=1.0, avg_cost_eur=0.0, currency=currency)
    return ValuedPosition(
        position=pos,
        current_price=market_value_eur,
        market_value_eur=market_value_eur,
        pnl_eur=0.0,
        pnl_pct=0.0,
    )


def make_config(weights: dict[str, tuple[float, tuple[str, ...]]], cash: float = 0.0) -> Config:
    return Config(
        base_currency="EUR",
        categories={
            name: Category(name=name, target_weight=w, tickers=tickers)
            for name, (w, tickers) in weights.items()
        },
        cash_balance_eur=cash,
    )


def test_compute_rebalance_perfect_allocation() -> None:
    config = make_config({
        "equity": (0.8, ("VWCE.DE",)),
        "cash": (0.2, ()),
    })
    actions = compute_rebalance([vp("VWCE.DE", "EUR", 800.0)], config, cash_eur=200.0)

    by_cat = {a.category: a for a in actions}
    assert by_cat["equity"].current_weight == pytest.approx(0.8)
    assert by_cat["equity"].delta_eur == pytest.approx(0.0)
    assert by_cat["cash"].current_weight == pytest.approx(0.2)
    assert by_cat["cash"].delta_eur == pytest.approx(0.0)


def test_compute_rebalance_underweight_gives_positive_delta() -> None:
    config = make_config({
        "equity": (0.8, ("VWCE.DE",)),
        "cash": (0.2, ()),
    })
    # Total = 700 + 300 = 1000. Equity target 800, has 700 -> buy 100.
    actions = compute_rebalance([vp("VWCE.DE", "EUR", 700.0)], config, cash_eur=300.0)

    by_cat = {a.category: a for a in actions}
    assert by_cat["equity"].delta_eur == pytest.approx(100.0)
    assert by_cat["cash"].delta_eur == pytest.approx(-100.0)


def test_compute_rebalance_overweight_gives_negative_delta() -> None:
    config = make_config({
        "equity": (0.5, ("VWCE.DE",)),
        "cash": (0.5, ()),
    })
    # Total = 800 + 200 = 1000. Equity target 500, has 800 -> sell 300.
    actions = compute_rebalance([vp("VWCE.DE", "EUR", 800.0)], config, cash_eur=200.0)

    by_cat = {a.category: a for a in actions}
    assert by_cat["equity"].delta_eur == pytest.approx(-300.0)


def test_compute_rebalance_all_categories_emitted_even_if_empty() -> None:
    config = make_config({
        "equity": (0.8, ("VWCE.DE",)),
        "bonds": (0.1, ()),
        "cash": (0.1, ()),
    })
    actions = compute_rebalance([vp("VWCE.DE", "EUR", 800.0)], config, cash_eur=200.0)

    assert {a.category for a in actions} == {"equity", "bonds", "cash"}


def test_compute_rebalance_empty_portfolio_returns_zero_deltas() -> None:
    config = make_config({"equity": (1.0, ("VWCE.DE",))}, cash=0.0)
    actions = compute_rebalance([], config, cash_eur=0.0)
    [action] = actions
    assert action.current_weight == 0.0
    assert action.delta_eur == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rebalance.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `rebalance.py`**

`src/portfolio/rebalance.py`:
```python
from __future__ import annotations

from dataclasses import dataclass

from portfolio.config import Config
from portfolio.valuation import ValuedPosition


@dataclass(frozen=True)
class RebalanceAction:
    category: str
    current_weight: float
    target_weight: float
    delta_eur: float   # positive = buy more, negative = sell


def compute_rebalance(
    valued: list[ValuedPosition],
    config: Config,
    cash_eur: float,
) -> list[RebalanceAction]:
    equity_total = sum(v.market_value_eur for v in valued)
    total = equity_total + cash_eur

    category_value: dict[str, float] = {name: 0.0 for name in config.categories}

    for v in valued:
        try:
            cat = config.ticker_to_category(v.position.ticker)
        except KeyError:
            continue
        category_value[cat] += v.market_value_eur

    if "cash" in category_value:
        category_value["cash"] += cash_eur

    actions: list[RebalanceAction] = []
    for name, cat in config.categories.items():
        current = category_value[name]
        current_weight = current / total if total else 0.0
        target_value = cat.target_weight * total
        delta = target_value - current
        actions.append(RebalanceAction(
            category=name,
            current_weight=current_weight,
            target_weight=cat.target_weight,
            delta_eur=delta,
        ))
    return actions
```

Note on cash modeling: if the config has a `cash` category, its `tickers` list is empty by convention, and `cash_balance_eur` flows into that category. If no `cash` category exists, `cash_eur` contributes to `total` but isn't attributed to any category — the math still works, but users should add a `cash` category if they want to see cash drift.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rebalance.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/rebalance.py tests/test_rebalance.py
git commit -m "feat(rebalance): category-level drift and deltas"
```

---

## Task 9: CLI (`cli.py`)

**Files:**
- Create: `src/portfolio/cli.py`

Thin argparse wrapper. No unit tests (tested via manual smoke). Registered as `portfolio` console script via `pyproject.toml` (already set up in Task 1).

Commands:
- `portfolio add-buy <TICKER> <QTY> <PRICE> [--currency USD] [--date YYYY-MM-DD]`
- `portfolio add-sell <TICKER> <QTY> <PRICE> [--currency USD] [--date YYYY-MM-DD]`
- `portfolio show` — load data, fetch prices, print positions + drift
- `portfolio check` — validate CSV + config coverage

- [ ] **Step 1: Implement `cli.py`**

`src/portfolio/cli.py`:
```python
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from portfolio.config import load_config
from portfolio.positions import compute_positions, enrich_transactions_with_eur
from portfolio.prices import fetch_fx_eur, fetch_historical_fx_eur, fetch_prices
from portfolio.rebalance import compute_rebalance
from portfolio.transactions import Transaction, append_transaction, load_transactions
from portfolio.valuation import value_positions

DEFAULT_TX_PATH = Path("data/transactions.csv")
DEFAULT_CONFIG_PATH = Path("data/config.yaml")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="portfolio")
    parser.add_argument("--transactions", type=Path, default=DEFAULT_TX_PATH)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    sub = parser.add_subparsers(dest="command", required=True)

    for action in ("add-buy", "add-sell"):
        sp = sub.add_parser(action)
        sp.add_argument("ticker")
        sp.add_argument("quantity", type=float)
        sp.add_argument("price", type=float)
        sp.add_argument("--currency", default="EUR", choices=["EUR", "USD"])
        sp.add_argument("--date", dest="tx_date", type=date.fromisoformat, default=None)

    sub.add_parser("show")
    sub.add_parser("check")

    args = parser.parse_args(argv)

    if args.command in ("add-buy", "add-sell"):
        return _cmd_add(args)
    if args.command == "show":
        return _cmd_show(args)
    if args.command == "check":
        return _cmd_check(args)
    parser.error(f"unknown command {args.command}")
    return 2


def _cmd_add(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.ticker not in config.all_tickers():
        known = ", ".join(sorted(config.all_tickers()))
        print(f"error: ticker {args.ticker!r} is not in config. Known: {known}", file=sys.stderr)
        return 1

    tx = Transaction(
        date=args.tx_date or date.today(),
        ticker=args.ticker,
        action="buy" if args.command == "add-buy" else "sell",
        quantity=args.quantity,
        price=args.price,
        currency=args.currency,
    )
    append_transaction(args.transactions, tx)
    print(f"appended: {tx}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    tx_df = load_transactions(args.transactions)
    orphans = sorted(set(tx_df["ticker"]) - config.all_tickers())
    if orphans:
        print(f"error: transaction tickers not in config: {orphans}", file=sys.stderr)
        return 1
    enriched = enrich_transactions_with_eur(tx_df, fetch_historical_fx_eur)
    positions = compute_positions(enriched)

    tickers = [p.ticker for p in positions]
    prices = fetch_prices(tickers)
    currencies = sorted({p.currency for p in positions} | {"EUR"})
    fx = fetch_fx_eur(currencies)
    valued = value_positions(positions, prices, fx)

    print(f"{'TICKER':<10} {'QTY':>10} {'AVG EUR':>10} {'PRICE':>10} {'VALUE EUR':>12} {'P&L EUR':>10} {'P&L %':>8}")
    for v in valued:
        p = v.position
        print(
            f"{p.ticker:<10} {p.quantity:>10.4f} {p.avg_cost_eur:>10.2f} "
            f"{v.current_price:>10.2f} {v.market_value_eur:>12.2f} "
            f"{v.pnl_eur:>10.2f} {v.pnl_pct*100:>7.2f}%"
        )

    print()
    actions = compute_rebalance(valued, config, config.cash_balance_eur)
    print(f"{'CATEGORY':<15} {'CURRENT %':>10} {'TARGET %':>10} {'DELTA EUR':>12}")
    for a in actions:
        print(
            f"{a.category:<15} {a.current_weight*100:>9.2f}% "
            f"{a.target_weight*100:>9.2f}% {a.delta_eur:>12.2f}"
        )
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    tx_df = load_transactions(args.transactions)

    known = config.all_tickers()
    orphans = sorted(set(tx_df["ticker"]) - known)
    if orphans:
        print(f"error: transaction tickers not in config: {orphans}", file=sys.stderr)
        return 1

    print(f"ok: {len(config.categories)} categories, {len(known)} configured tickers, "
          f"{len(tx_df)} transactions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Reinstall the package so the console script is registered**

Run: `uv sync --extra dev`
Expected: Completes silently or shows minor reconcile.

- [ ] **Step 3: Smoke test `check` and `show`**

Run:
```bash
uv run portfolio check
```
Expected: `ok: 4 categories, 5 configured tickers, 5 transactions.`

Run:
```bash
uv run portfolio show
```
Expected: Table of positions with live prices + category drift table. (Requires network.)

- [ ] **Step 4: Smoke test `add-buy` and rollback**

```bash
cp data/transactions.csv data/transactions.csv.bak
uv run portfolio add-buy VWCE.DE 1 99.00
tail -1 data/transactions.csv   # verify new row appended
mv data/transactions.csv.bak data/transactions.csv
```
Expected: A new row is printed, then restoration succeeds.

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/cli.py
git commit -m "feat(cli): add-buy, add-sell, show, check commands"
```

---

## Task 10: Streamlit dashboard (`app.py`)

**Files:**
- Create: `app.py`

Single-page dashboard. Live yfinance fetch each reload, wrapped in `st.cache_data(ttl=60)` so rapid reloads within a minute don't hammer yfinance. Sidebar "Refresh prices" button clears the cache.

- [ ] **Step 1: Implement `app.py`**

`app.py`:
```python
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
```

- [ ] **Step 2: Launch the app and inspect**

Run: `uv run streamlit run app.py`
Expected: Browser opens. Verify:
- 4 KPI tiles populate (market value, cost, P&L, cash)
- Pie and treemap render with category colors
- P&L bar chart shows positions sorted by absolute P&L
- Target vs actual table shows drift and Buy/Sell/Hold
- Sidebar "Refresh prices" button reloads prices
- Drift threshold slider changes which rows say "Hold"

Stop the server with Ctrl-C once verified.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat(app): Streamlit dashboard with allocation, P&L, rebalance"
```

---

## Task 11: README quickstart + final smoke

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
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
```

- [ ] **Step 2: Final test sweep**

Run: `uv run pytest -v`
Expected: All tests PASS (config: 4, transactions: 5, positions: 6, valuation: 4, rebalance: 5 = **24 tests**).

- [ ] **Step 3: Final CLI + app smoke**

Run: `uv run portfolio check`
Expected: ok line.

Run: `uv run portfolio show`
Expected: Tables print.

Run: `uv run streamlit run app.py` — spot-check the dashboard, Ctrl-C to stop.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add quickstart README"
```

- [ ] **Step 5: Tag v0.1.0**

```bash
git tag v0.1.0
git log --oneline
```
Expected: Tag applied to the latest commit. Full history visible.

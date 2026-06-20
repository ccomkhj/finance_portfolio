# portfolio

> Local-first net-worth tracker for EU self-directed investors. Plain-text
> data, git history, CLI, and Streamlit dashboard. No account, no broker login,
> no hosted personal data.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-pytest-brightgreen.svg)](#develop)
[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://financeportfolio.streamlit.app)

**Live demo:** [financeportfolio.streamlit.app](https://financeportfolio.streamlit.app) — read-only, synthetic data.

![Dashboard](docs/dashboard.png)

## What it does

- Tracks net worth across **multiple accounts** (e.g. Trade Republic, Trading
  212, Commerzbank). Each account is one snapshot in `data/accounts/*.json`.
- Ingests Trade Republic Net Worth PDFs (`portfolio ingest`), and lets you
  **add other accounts by hand** in the dashboard (EUR value per holding).
- Reads target weights and ISIN categories from `data/config.yaml`; edit
  categories/weights and move holdings between categories in the dashboard.
- Computes net worth from the EUR values you provide — no live prices, no
  external API.
- A **Global** view aggregates every account and shows allocation vs. your
  target ratios; a per-account tab shows each broker on its own.
- Runs locally, so your real holdings stay on your machine.

The bundled `data/` files are **synthetic demo data**. Your real data lives in
a gitignored `data/private/` directory (see
[Keep your data private](#keep-your-data-private)). See
[DISCLAIMER.md](DISCLAIMER.md) before using this with real portfolio records.

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ccomkhj/finance_portfolio.git
cd finance_portfolio
uv sync --extra dev
uv run portfolio check
uv run portfolio show
```

Open the dashboard (synthetic demo data):

```bash
uv run portfolio dashboard
```

For your **own** data, use the helper script instead (see
[Keep your data private](#keep-your-data-private)):

```bash
./dashboard.bash
```

## Example

`uv run portfolio show` on the bundled synthetic demo (two accounts):

```text
NET WORTH: 5,000.00 EUR

ACCOUNT           AS OF              TOTAL EUR
trade_republic    2026-01-15          3,200.00
trading_212       2026-01-15          1,800.00

CATEGORY            CURRENT %  TARGET %     DELTA EUR
global-equity          34.00%    50.00%        800.00
bonds                  10.00%    20.00%        500.00
gold                    6.00%    10.00%        200.00
cash                   50.00%    20.00%     -1,500.00
```

`DELTA EUR` is the category-level rebalance amount: positive means buy more of
that category, negative means reduce it.

## Keep your data private

The repo is public, so **never put real holdings in the committed `data/`
directory.** Instead keep them in `data/private/`, which is gitignored, and
point the tools at it with the `PORTFOLIO_DATA_DIR` environment variable:

```bash
# one-time: create your private data dir from the demo as a starting point
mkdir -p data/private/accounts
cp data/config.yaml data/private/config.yaml

# then run everything against it — nothing here is ever tracked by git
export PORTFOLIO_DATA_DIR=data/private
uv run portfolio show
uv run portfolio dashboard
```

`PORTFOLIO_DATA_DIR` resolves the data directory for both the CLI and the
dashboard (default: `data/`, the synthetic demo). Because `data/private/` is in
`.gitignore`, your real `config.yaml` and `accounts/*.json` stay on your
machine. `.gitignore` also excludes `data/*.bak` and `broker_exports/`.

The bundled **`./dashboard.bash`** wraps this — it sets
`PORTFOLIO_DATA_DIR=data/private` and launches the dashboard, so you don't have
to remember the env var:

```bash
./dashboard.bash
```

> Tip: or add `export PORTFOLIO_DATA_DIR=data/private` to your shell profile.

## Password-protect the dashboard

If you host the dashboard somewhere reachable (Streamlit Community Cloud, a
private server, a tunnel) and want it for your eyes only, set a password. When a
password is configured the app shows a login prompt before anything else; when
none is set it stays open (so the public read-only demo is unaffected).

Pick whichever is convenient:

- **Environment variable** (local runs / `dashboard.bash`):

  ```bash
  export PORTFOLIO_PASSWORD='my-secret'
  ./dashboard.bash
  ```

- **Streamlit secrets** (works locally and on Streamlit Cloud). Copy
  `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` (gitignored) and
  set:

  ```toml
  password = "my-secret"
  ```

  On Streamlit Community Cloud, paste that same line into the app's **Secrets**
  box instead of committing a file.

The entered password is compared in constant time and never stored in session
state. This is a lightweight access gate — for a sensitive deployment also keep
the app's **Sharing** private and serve it over HTTPS.

### Self-host on your own server

To run the full editable dashboard against your real data on a server you
control (recommended over a public cloud demo for real holdings), see
[docs/DEPLOY_ORACLE.md](docs/DEPLOY_ORACLE.md) — a step-by-step guide for
Oracle Cloud's Always Free tier with HTTPS via Caddy/Let's Encrypt. The
`deploy/` directory has a ready-made systemd unit and Caddyfile.

## Use your own portfolio

With `PORTFOLIO_DATA_DIR` set to your private dir (above):

1. Initialise a fresh config (writes into your private dir):

   ```bash
   uv run portfolio init --force
   ```

2. Add an account — upload a Trade Republic Net Worth PDF in the dashboard
   sidebar (or `uv run portfolio ingest path/to/networth.pdf`), or add a manual
   account in **Settings → Add account** and enter its cash + holdings on its
   tab.

3. Assign ISIN categories and target weights in the dashboard's **Settings**
   tab (or edit `config.yaml`).

4. Validate and inspect:

   ```bash
   uv run portfolio check
   uv run portfolio show
   ```

## Public demo

The [live demo](https://financeportfolio.streamlit.app) runs on
[Streamlit Community Cloud](https://share.streamlit.io/). To deploy your own,
point a new app at your fork:

- **Main file path:** `streamlit_app.py`
- **Branch:** `main`
- **Python version:** set **3.12** in *Advanced settings* (Streamlit Cloud does
  not read a `runtime.txt`; the app requires 3.12+).
- **Sharing:** set to **Public** so logged-out visitors can open it.

The entrypoint sets `PORTFOLIO_READ_ONLY=1` (and does **not** set
`PORTFOLIO_DATA_DIR`), so the demo uses the committed synthetic `data/` and hides
all account-editing and Settings controls — no writes are exposed and no real
data ships. Streamlit Cloud installs the pinned dependencies from
`requirements.txt`.

For public launch and revenue notes, see [docs/PUBLIC_LAUNCH.md](docs/PUBLIC_LAUNCH.md).

## Data files

- `data/accounts/*.json`: per-broker snapshots created by `portfolio ingest`.
  Each file contains one snapshot with holdings (ISIN, name, quantity, EUR
  value) and cash balance.
- `data/config.yaml`: target weights, ISIN-to-category mapping, and optional
  ISIN display names.
- `data/private/`: **your** real `config.yaml` + `accounts/*.json`, gitignored.
  Selected via `PORTFOLIO_DATA_DIR=data/private` (see
  [Keep your data private](#keep-your-data-private)).

## Develop

```bash
uv run pytest
```

## License

MIT. See [LICENSE](LICENSE).

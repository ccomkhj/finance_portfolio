---
name: assess-portfolio
description: Use when the user asks about their portfolio — state, drift, rebalancing, P&L, adding/selling positions, editing targets or cash balance, swapping tickers, or troubleshooting CLI errors. Wraps the `portfolio` CLI of this repo with a structured assessment template and reference docs for every common task.
---

# Assess Portfolio

## When to use

Trigger on any of:

- "How's my portfolio doing?" / "Any drift from my targets?" / "Should I rebalance?"
- "Add a buy for X" / "Record that I sold Y" / "I deposited €500"
- "Change my target weight for bonds" / "Add a new category"
- "My ticker shows no price" / "CLI gave me this error"
- Explicit `/assess-portfolio` invocation

## What this skill does NOT do

**No open-ended investment advice.** This skill does not recommend specific stocks, predict prices, or second-guess the user's strategy. It strictly interprets the user's own `data/config.yaml` (the targets they set) against `portfolio show` (their current state) and reports what it finds.

If the user asks for actual financial judgment ("should I buy Nvidia?", "is now a good time to sell bonds?"), decline politely and suggest a licensed financial advisor.

## Resources

### Scripts (in `scripts/`)
- `snapshot.sh` — emits a structured JSON snapshot (positions, totals, rebalance). **Prefer this over parsing `portfolio show` text** for agent reasoning. Usage: `./.claude/skills/assess-portfolio/scripts/snapshot.sh`
- `snapshot.py` — the Python source behind `snapshot.sh`, with the JSON shape documented at the top
- `add-transaction.sh` — thin wrapper for `add-buy` / `add-sell` with action-argument convenience. Usage: `./.claude/skills/assess-portfolio/scripts/add-transaction.sh buy VWCE.DE 10 98.50`

### References (in `references/`) — read on-demand based on the user's request
- `cli-reference.md` — exhaustive docs for every `portfolio` subcommand, flags, exit codes, examples. Load when the user asks about a specific command.
- `data-schema.md` — `transactions.csv` and `config.yaml` schemas, validation rules, ticker selection guidance. Load when the user is editing data files or picking tickers.
- `recipes.md` — step-by-step recipes for common tasks (add ticker, rename category, swap delisted ticker, update cash balance, scenario dry-runs). Load when the user wants to make a change.
- `troubleshooting.md` — error dictionary with meaning + fix for every validation error, yfinance error, and Streamlit issue. Load when the user pastes an error.

## Process: assessment requests

For any "how's it going / should I rebalance" question:

### Step 1 — Get structured data

Run from the repo root (`/Users/huijokim/personal/finance`):

```bash
./.claude/skills/assess-portfolio/scripts/snapshot.sh
```

This returns a JSON object with `totals`, `positions`, `unpriced_tickers`, and `rebalance` — all numbers pre-computed, no text parsing.

If the script fails, `cat` the stderr and consult `references/troubleshooting.md` for the fix, then either fix and retry or explain to the user what's broken.

### Step 2 — Read the config

`cat data/config.yaml` to understand the target structure. You need it for context — the snapshot has the numbers but not the user's intent (e.g., why three separate equity categories).

### Step 3 — Produce the assessment

Structure the response as **four short sections**, in this order. 3–5 lines per section.

**A. Snapshot (one paragraph)**

- Total market value (EUR, including cash)
- Total P&L (EUR + %)
- Cash weight vs. target
- Number of priced vs. unpriced positions (warn if `unpriced_tickers` is non-empty)

**B. Concentration observations**

- Largest single position as % of total (flag if >15% and the ticker is not itself a diversified ETF)
- Any category with drift >5pp or less than half its target
- Currency exposure (EUR vs. USD)
- **Look-through overlap:** if the user holds both a global-equity ETF (VWCE / IWDA) AND a US-equity bucket, note that their effective US weight is higher than the category table shows (MSCI World is ~70% US)

**C. Drift vs. target (per category)**

Use the `rebalance` array from the snapshot directly — don't recompute. For each entry:

- `|drift_pp| < 1`: report as on-target
- `1 ≤ |drift_pp| < 3`: note the drift, no action needed yet
- `|drift_pp| ≥ 3`: recommend the action, quoting the exact `delta_eur` ("Buy €X" if positive, "Sell €X" if negative)

**D. Process suggestions (optional, ≤2 bullets)**

Concrete, interpretive observations — not predictions. Examples:
- "IUSA.AS and VUSA.AS are both distributing S&P 500 ETFs — consolidating saves you per-order fees"
- "EUNA.DE has no live price — swap to a ticker yfinance quotes (see `recipes.md` → swap a delisted ticker)"

Never speculate about market direction, macro, or specific stock picks.

End with one short disclosure: "Numbers above are from a live yfinance fetch at {timestamp} and reflect your config as of this reading."

## Process: mutation requests

For "add a buy", "change a target", "rename a category", etc.:

1. Load `references/recipes.md` and follow the matching recipe.
2. If the user's request doesn't match any recipe exactly, load `references/cli-reference.md` and/or `references/data-schema.md` as appropriate.
3. Always run `uv run portfolio check` after the mutation and report the result.
4. If they asked for a change that affects valuation (new ticker, new weights), consider offering to also run the snapshot and show how the change affected drift.

## Process: error troubleshooting

If the user pastes a CLI error:

1. Load `references/troubleshooting.md`.
2. Match the error text to an entry.
3. Apply the listed fix (either directly, or by guiding the user through the edit).
4. Verify with `uv run portfolio check` and confirm success.

## Output style

- Terse, quantitative, scannable
- Cite concrete EUR amounts from the snapshot, not percentages alone
- Do not re-print data the user has already seen in a tool result
- No per-section disclaimers; one closing line is enough

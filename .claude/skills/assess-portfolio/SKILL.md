---
name: assess-portfolio
description: Use when the user asks about their portfolio state, whether to rebalance, how their holdings are doing, whether their allocation has drifted, or wants a financial snapshot of their Trade Republic portfolio. Runs the repo's `portfolio` CLI and produces a structured assessment against the user's own target weights.
---

# Assess Portfolio

## When to use

Trigger on any of:

- "How's my portfolio doing?"
- "Should I rebalance?"
- "What's my current allocation?"
- "Any drift from my targets?"
- "Assess my portfolio"
- Explicit `/assess-portfolio` invocation

## What this skill does NOT do

This skill **does not give open-ended investment advice**. It does not recommend buying a specific stock, predict prices, or second-guess the user's strategy. It strictly *interprets* the user's own `data/config.yaml` (the targets they set) against `portfolio show` (their current state) and reports what it finds.

If the user asks questions that require actual financial judgment ("should I buy Nvidia?", "is now a good time to sell bonds?"), decline politely and suggest they consult a licensed financial advisor. Run this skill only for the assessment itself.

## Process

### Step 1 — Run the CLI

From the repo root (`/Users/huijokim/personal/finance`):

```bash
uv run portfolio show
```

This prints two tables: current positions (ticker, qty, avg cost, live price, value, P&L) and category drift (current %, target %, delta EUR).

If `portfolio show` fails (network, yfinance, missing data), first run `uv run portfolio check` to rule out config/transaction issues, then report the error to the user clearly — don't fabricate numbers.

### Step 2 — Read the config

Read `data/config.yaml` to understand the user's target structure (categories, target weights, cash balance). You need this for context, especially to know whether any category has no target (shouldn't happen after `check` passes).

### Step 3 — Produce the assessment

Structure the response as **four short sections**, in this order. Keep each section to 3–5 lines maximum.

#### A. Snapshot (one paragraph)

- Total market value (EUR, including cash)
- Total P&L (EUR + %)
- Cash weight vs. target
- Number of priced vs. unpriced positions (warn if any position's price came back NaN)

#### B. Concentration observations

- Largest single position as % of total (flag if >15% — common personal-investing heuristic)
- Any category whose weight exceeds target by more than 5pp or is less than half its target
- Currency exposure (EUR vs. USD weight) — flag if user's cost basis is in one currency but market value has drifted materially into another

#### C. Drift vs. target (per category)

For each category in the drift table:

- If `|current − target| < 1pp`: report as on-target
- If `1pp ≤ |drift| < 3pp`: note the drift, no action needed yet
- If `|drift| ≥ 3pp`: recommend the rebalancing action already printed by the CLI (Buy €X / Sell €X), calling out which direction

Use the `delta_eur` values from `portfolio show` directly — do not recompute.

#### D. Process suggestions (optional, only if relevant)

At most two bullets. Examples:

- "AGGH.DE has no live price from yfinance — you may want to swap it for a ticker Yahoo actually quotes (iShares Core Global Aggregate Bond UCITS alternatives: AGGG.L, EUNA.DE)."
- "Your cash weight is 2x the target — consider deploying it into the underweight `global-equity` category."

Do NOT speculate about market direction, macroeconomic conditions, or specific stock picks.

## Output style

- Terse, quantitative, scannable
- Include concrete EUR amounts from the CLI output, not percentages alone
- Do not re-print the full position table — the user has just seen it (or will see it in the tool output)
- Do not add disclaimers to every section; one closing sentence is enough: "Numbers above are from a live yfinance fetch at {timestamp} and reflect your config as of this reading."

## Example response shape

> **Snapshot.** €5,842 total value (€1,250 cash). P&L +€1,346 (+30.1%) on €4,476 cost basis. 4 of 5 positions priced; `AGGH.DE` had no quote.
>
> **Concentration.** Largest position: VWCE.DE at 26% of total — within the 15% single-name flag threshold when measured against a category-diversified ETF, so not worth flagging. US-equity sitting at 28% vs 15% target is the main concentration issue.
>
> **Drift vs. target.**
> - global-equity: 50% (target 70%) — **underweight by 20pp**, CLI suggests Buy €1,153
> - us-equity: 28% (target 15%) — **overweight by 13pp**, CLI suggests Sell €780
> - bonds: 0% (target 10%) — missing entirely (see unpriced ticker below), Buy €584 once ticker is fixed
> - cash: 21% (target 5%) — **overweight by 16pp**, deploy into global-equity
>
> **Process suggestions.**
> - `AGGH.DE` is delisted on yfinance; swap for a bond ETF Yahoo quotes (e.g. `AGGG.L`) so the dashboard and rebalance math stop excluding it.
> - Sizable drift on 3 of 4 categories — if no rebalance has happened since setup, a one-time buy-to-target may be simpler than incremental nudges.
>
> Numbers above are from a live yfinance fetch and reflect your config as of this reading.

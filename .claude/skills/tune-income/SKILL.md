---
name: tune-income
description: Use whenever the user wants to set up, enhance, or double-check the income estimate of this portfolio repo — the `income:`, `cash_interest_pct`, and `tax:` blocks in data/config.yaml that drive `portfolio income` (gross) and `portfolio income --net` (after-tax). Trigger on "estimate my dividends/interest", "my income shows 0 / n/a", "add a proxy", "set the cash interest rate", "show income net of tax", "set up Teilfreistellung", "is my income/tax config right?", "which distributing twin for <ETF>", or any request to verify/fix why an accumulating ETF reports no income or why the net figure looks off. Use this even when the user just says "check my income config" without naming the fields.
---

> ⚠️ **Outdated.** The portfolio repo moved to a snapshot-based net-worth model (multiple institutions, ISIN categories, PDF ingest). This skill references the removed transaction/income CLI (`add-buy`, `add-sell`, `import`, `income`) and needs a rewrite. See `docs/superpowers/plans/2026-06-19-multi-source-networth.md`.

# Tune income config

The `portfolio income` command estimates portfolio income as two figures —
**economic income** (what holdings earn, market value × yield) and **cash
distribution** (what's actually paid out) — gross by default, or after-tax with
`--net` (a dashboard toggle does the same). It reads optional config:

```yaml
cash_interest_pct: 2.0          # broker's annual interest rate on the cash balance
income:                          # per-ticker overrides; omit a ticker → use its own live yield
  WEBG.DE: { proxy: VWRL.DE }    # accumulating → borrow a distributing twin's live yield
  EUNA.DE: { yield_pct: 2.4 }    # no live twin → manual annual yield %
tax:                             # only used by `--net`; sensible German defaults if omitted
  rate_pct: 26.375               # Kapitalertragsteuer 25% + Soli (church tax → ~27.8–28%)
  default_teilfreistellung: equity   # class for holdings not listed below
  teilfreistellung:              # German partial exemption by fund type
    VOW.DE: none                 # individual stock — no exemption
    EUNA.DE: none                # bond fund — no exemption
```

Each `income` entry sets **exactly one** of `proxy` or `yield_pct`. Two things are
silently wrong unless configured: accumulating ETFs (common in EU/Trade Republic
portfolios) distribute ~nothing, so yfinance reports ~0% and the economic line
needs a proxy or manual yield; and in `--net` mode every holding inherits
`default_teilfreistellung` (equity → 30% tax-free) unless listed, so individual
stocks and bond funds left on the default get an exemption they aren't owed and
their net is overstated. This skill helps set both up and verify they're right.

## What this skill does NOT do

**No fabricated numbers.** Never invent a yield, a cash interest rate, or assert a
proxy ticker is correct without verifying it resolves. The cash rate is something
only the user knows (their broker's current rate); proxy tickers must be
confirmed against yfinance via the audit script, not pasted from memory. When you
genuinely don't know, say so and ask or point at the factsheet — a confidently
wrong financial number is worse than an admitted gap.

**General config edits** (categories, target weights, tickers, cash *balance*,
adding/selling positions) belong to the `assess-portfolio` skill, not this one.
This skill is only about the income fields.

## Resources

- `scripts/audit-income.sh` — runs the income pipeline and emits JSON findings
  with actionable flags. **Prefer this over reading the `portfolio income` table**
  when deciding what to change. Usage from repo root:
  `./.claude/skills/tune-income/scripts/audit-income.sh`
- `references/proxy-map.md` — how to choose a distributing-twin proxy, a starting
  table of twins for common accumulating UCITS ETFs, and when to use a manual
  yield instead. Read it whenever picking or verifying a proxy.
- `references/tax.md` — the German net-of-tax model: rate, Teilfreistellung
  classes per fund type, church-tax rates, and the default-equity trap. Read it
  whenever setting up or checking the `tax:` block.

## Process: double-check the config

This is the default for "is my income config right?" / "why is my income 0?".

### Step 1 — Run the audit

```bash
./.claude/skills/tune-income/scripts/audit-income.sh
```

It returns JSON: `cash`, `holdings[]`, `proxy_checks[]`, `manual_yields[]`, and a
`summary`. Each holding and proxy carries a `flags` array. If it errors, the
config or data is broken first — run `uv run portfolio check` and fix that.

### Step 2 — Interpret the flags

Walk the findings and translate each flag into a concrete recommendation:

- **`zero_yield_native`** — a holding using its own yield reports ~0%. For an
  **ETF** this almost always means it's *accumulating* → recommend a proxy (see
  `references/proxy-map.md`) or a manual `yield_pct`. For a **single stock** it
  may just mean no dividend was paid in the last 12 months (annual/suspended
  payer) → likely a genuine zero, no action. Distinguish by whether the ticker is
  a fund or a stock, and say which you think it is.
- **`unresolved`** — no yield at all (not even 0). Either no override and yfinance
  has no data, or a configured proxy/source failed. Needs a proxy or `yield_pct`.
- **`broken_proxy`** — a configured proxy ticker returns no yield: delisted or
  mis-typed (the `AGGH` bond-twin trap). Pick another listing from the proxy map,
  or fall back to a manual `yield_pct`.
- **`cash_interest_unset`** — there's a cash balance but `cash_interest_pct` is 0,
  so cash income reads €0. Ask the user for their broker's current rate; don't
  guess it.
- **`teilfreistellung_default`** — the holding has no explicit Teilfreistellung
  class, so `--net` taxes it as the default (usually `equity`, 30% exempt). That's
  right for an equity ETF but wrong for an **individual stock** or a **bond fund**,
  which get no exemption → recommend setting those to `none` so their net isn't
  overstated. The `tax` block in the audit shows the gross-vs-net totals so you can
  quote the impact. Only relevant if the user cares about the net figure.

### Step 3 — Report

Lead with whether the estimate is trustworthy as-is, then a short bulleted list of
gaps, each with the exact config edit that would fix it. Quote EUR figures from
the audit (e.g. "SXR8.DE holds €2,058 but reports €0 income — add a proxy"). End
by offering to apply the fixes.

## Process: enhance / set up the config

For "set up income", "add a proxy for X", "make my income estimate accurate":

1. **Audit first** (Step 1 above) to see what's actually missing — don't add
   overrides a holding doesn't need.
2. **For each flagged holding**, pick the fix using `references/proxy-map.md`:
   prefer a live **proxy** twin; use a manual **`yield_pct`** only where no twin
   resolves (typically bond ETFs and cash).
3. **Verify before committing.** After adding a `proxy`, re-run the audit and
   confirm it now `resolves` with a *plausible* yield (a broad-equity proxy
   showing 8% means you grabbed the wrong fund). This verify-the-proxy loop is the
   whole point — a proxy that doesn't resolve silently understates income.
4. **Set `cash_interest_pct`** from the rate the user gives you.
5. **If the user wants net-of-tax**, set up the `tax:` block — read
   `references/tax.md`. The key move: list every `teilfreistellung_default`
   holding that is an individual stock or bond fund as `none`; leave equity ETFs
   on the default. Ask whether they pay church tax (it changes `rate_pct`); don't
   assume it.
6. **Validate**: `uv run portfolio check` (structural) then re-run the audit until
   the `summary` shows 0 unresolved / 0 broken proxies (and, if net matters, no
   stray `teilfreistellung_default` on stocks/bond funds).
7. Offer to show the before/after with `uv run portfolio income` (add `--net` if
   tax was configured).

## Editing notes

- The config loader rejects an `income` entry that sets both `proxy` and
  `yield_pct`, or neither, or names a ticker not in any category — so a failed
  `portfolio check`/load after your edit usually means one of those.
- Keep edits minimal and idiomatic: only add `income` entries for holdings that
  need them; leave distributing stocks out entirely.
- Changes write to `data/config.yaml`; `git restore data/config.yaml` undoes them.

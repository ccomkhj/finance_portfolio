---
name: review-portfolio
description: Use when the user wants a holistic, conversational review of their portfolio — "walk me through my portfolio", "how am I doing overall", "give me an overview and some advice", "what should I be thinking about", a periodic check-in, or a goal/risk gut-check. Runs a short guided Q&A (horizon, drawdown comfort, goal) every session, then synthesizes the live snapshot and income audit into a plain-language overview with prioritized, interpretive advice — and journals each review with a date so it can recall what you expected last time and flag what changed. Use this even when the user just says "review my portfolio" or "let's do a check-in" without naming metrics. NOT for one-off mutations (add/sell, edit targets), structured drift tables, or income/tax config — those belong to assess-portfolio and tune-income.
---

> ⚠️ **Outdated.** The portfolio repo moved to a snapshot-based net-worth model (multiple institutions, ISIN categories, PDF ingest). This skill references the removed transaction/income CLI (`add-buy`, `add-sell`, `import`, `income`) and needs a rewrite. See `docs/superpowers/plans/2026-06-19-multi-source-networth.md`.

# Review Portfolio

A guided, conversational portfolio review. Where `assess-portfolio` answers pointed
questions with a structured table, this skill is the **sit-down check-in**: a short Q&A
about where the user's head is, then a narrative overview, then prioritized advice framed
as options — and it **remembers**, journaling each session so the next one can pick up the
thread ("last time you expected to move cash into bonds; here's what actually happened").

## When to use

- "Walk me through my portfolio" / "How am I doing overall?" / "Give me an overview"
- "What should I be thinking about?" / "Any advice?" / "Let's do a check-in"
- A periodic review ("it's been a quarter, review it") or a goal/risk gut-check
- Explicit `/review-portfolio`

## What this skill does NOT do

- **No mutations.** Adding buys/sells, editing targets, cash, or tickers → **assess-portfolio**.
- **No income/tax config.** The `income:`, `cash_interest_pct`, `tax:` blocks → **tune-income**.
- **No regulated advice.** This skill inherits the same hard line as `assess-portfolio`: it
  does **not** recommend specific securities, predict prices, or time the market. Its "advice"
  is *interpretive* — drift vs the user's own targets, concentration, overlap, cash drag,
  goal-fit. If asked to pick a stock or call the market, decline and suggest a licensed advisor.

It is a **read-only consumer** of the two sibling skills' scripts plus its own review journal.

## Resources

### Scripts
- **`scripts/review-log.sh`** — the review journal (the memory). `last` emits the most recent
  saved review, `list` shows all dates, `save` appends a record from stdin (stamps today's
  date). Data lives in `data/reviews.jsonl`.
- Reused (call directly, don't reinvent):
  - `.claude/skills/assess-portfolio/scripts/snapshot.sh` — valuation, P&L, weights, `rebalance`.
  - `.claude/skills/tune-income/scripts/audit-income.sh` — yields, cash income, tax flags.

### References — load on-demand
- **`references/advice-guide.md`** — risk-tier mapping, the prioritized advice taxonomy with
  thresholds, and EU tax nudges + framing rules. **Load it before the fit/advice steps** (5–6).
- Sibling references, only if a question drifts into their territory: assess-portfolio's
  `references/{recipes,cli-reference,troubleshooting}.md`; tune-income's `references/{proxy-map,tax}.md`.

## The review session

Run these in order. It's a conversation, not a report dump — but lead with data so the user
isn't asked to re-state what the tracker already knows. Numbers come from the scripts; never
fabricate a figure.

### Step 1 — Recall the last review

```bash
./.claude/skills/review-portfolio/scripts/review-log.sh last
```

`{}` means this is the first review — skip the comparisons later. Otherwise note the prior
`date`, `profile`, and especially `expectations` — you'll check those against reality in Step 4.

### Step 2 — Pull the live data

Run both (compact is fine), from repo root:

```bash
./.claude/skills/assess-portfolio/scripts/snapshot.sh --compact
./.claude/skills/tune-income/scripts/audit-income.sh --compact
```

If a script errors, read its stderr and consult `assess-portfolio/references/troubleshooting.md`;
fix or explain rather than guessing numbers.

### Step 3 — The Q&A (always, every session)

Ask the **three questions one at a time** as multiple-choice (use the `AskUserQuestion` tool —
the user prefers selecting over typing). Ask them fresh each session even if a prior profile
exists; people's circumstances move, and capturing it each time is the point of the journal.
If a prior profile exists, you may show last time's answer as context ("last review: 10y+").

1. **Horizon** — "When do you expect to need most of this money?" → `<3y` / `3–10y` / `10y+`
2. **Drawdown comfort** — "If this dropped 30% in a year, you'd…" → `sell` / `hold` / `buy more`
3. **Goal** — "What's this portfolio for?" → `retirement` / `FIRE` / `house` / `general growth`

Then derive the **risk tier** per `references/advice-guide.md` (more-conservative-of rule).
Acknowledge the answers briefly before moving on — don't interrogate further.

### Step 4 — Synthesize the overview

Plain-language, scannable, short labelled sections (3–5 lines each):

**A. Snapshot** — grand total (incl. cash), total P&L (€ + %), cash weight vs target, headline
allocation (equity / bonds / cash). Warn if `unpriced_tickers` is non-empty.

**B. Since last review** *(only if Step 1 returned a record)* — change in grand total and cash
weight, and a candid check on the prior `expectations`: did they happen? "Last review (DATE)
you expected to move cash into bonds — cash is still 60%, so that hasn't happened yet." This
honest continuity is the skill's main value-add; don't skip it when a prior record exists.

**C. Risk & goal fit** — current equity share vs the tier's band; the one-line mismatch
sentence (either direction) if the gap is real, else one line confirming it's in range. Use
the goal for context (e.g. 4%-rule orientation for FIRE if a spending number comes up).

### Step 5 — Prioritized advice (load `references/advice-guide.md` first)

Walk the taxonomy in impact order — drift/rebalance → concentration → overlap → cash drag →
fees → at most one EU tax nudge — and surface only what actually fires. Give **2–3 options**,
each tied to a concrete EUR figure from the snapshot and framed as a choice, not an order.
Sequence them (deploying idle cash into the most-underweight category is usually step one).
Route any *fix* that's a mutation to assess-portfolio, any income/tax config to tune-income.

Close with the single standing disclaimer from the advice guide — once, not per bullet.

### Step 6 — Save the review, then offer to go deeper

Persist this session so the next one can recall it. Build a record and pipe it to `save`:

```bash
echo '{
  "profile": {"horizon": "10y+", "drawdown": "hold", "goal": "FIRE", "risk_tier": "Balanced"},
  "status": {"grand_total_eur": 18699, "pnl_pct": -2.75, "cash_pct": 59.9,
             "top_position": {"ticker": "VOW.DE", "weight_pct": 14.4},
             "largest_drift": {"category": "cash", "drift_pp": 52.4}},
  "expectations": ["deploy idle cash into core-etf and bonds toward target"],
  "advice": ["rebalance ~€6.6k cash into core-etf", "trim single-stocks ~€2.4k"]
}' | ./.claude/skills/review-portfolio/scripts/review-log.sh save
```

Fill `expectations` with the plain-language things that *should* have moved by next review —
that's what Step 4B checks against. Then end by leaving the user in control: "Want me to go
deeper on any of these, or actually make one of the changes (I'd hand that to assess-portfolio)?"

## Output style

- Terse, quantitative, scannable — cite concrete EUR amounts, not percentages alone.
- Don't re-print a full table the user just saw in a tool result; synthesize it.
- One closing disclaimer, never per-section hedging.
- The Q&A is multiple-choice and one question at a time; the overview is prose. Match the
  user's terse, YAGNI register — a clean portfolio gets a short review, not padding.

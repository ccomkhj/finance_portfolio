# Advice guide

Load this when you reach the **risk/goal fit** and **prioritized actions** parts of a
review. It holds the risk-tier mapping, the advice taxonomy with concrete thresholds,
and the EU-specific tax nudges — kept out of SKILL.md so the flow stays readable.

Everything here is *interpretive*: it reads the user's own config targets and the live
snapshot. None of it recommends a specific security, predicts a price, or times the
market. If a finding can't be tied to a number from the snapshot or income audit, don't
raise it.

---

## Risk tier from the three questions

The Q&A asks horizon, drawdown reaction, and goal. Map to one of three tiers, then take
the **more conservative** of the horizon-implied and drawdown-implied tier — that single
rule captures the willingness-vs-capacity idea without a scoring engine.

| Question | Answer → implied tier |
|---|---|
| Horizon | `<3y` → Conservative · `3–10y` → Balanced · `10y+` → Aggressive-ok |
| Drawdown (−30% in a year, you'd…) | `sell` → Conservative · `hold` → Balanced · `buy more` → Aggressive-ok |
| Goal | context only (see below), doesn't set the tier |

Rough equity bands per tier (a sanity range, not a prescription):
- **Conservative** ≈ 20–40% equity
- **Balanced** ≈ 40–70% equity
- **Aggressive-ok** ≈ 70–90% equity

"Equity" here = `core-etf` + `single-stocks` weight from the snapshot's `rebalance` array
(or sum the equity positions' `weight`). Compare the *current* equity share to the band.

### The mismatch sentence (one line, both directions)

- **Too aggressive for the tier/horizon:** "You're ~85% equity but your 4-year house goal
  and 'I'd sell' answer point to a Conservative range (~20–40%) — a bad year could land
  right before you need the money."
- **Too conservative for the tier/horizon:** "You're ~60% cash with a 10y+ FIRE goal — that's
  a lot of growth drag and inflation risk for money you won't touch for a decade."

Only raise it when the gap is real (current equity share clearly outside the tier band).
If it's inside the band, say so in one line and move on.

### Goal context (no Monte Carlo)

- **FIRE / retirement:** a back-of-envelope "target ≈ annual spend × 25" (the 4% rule) is
  enough orientation if the user mentions a spending number. Don't model longevity.
- **House / car / near-term:** the horizon *is* the constraint — fold it into the mismatch
  check above.
- **General growth:** no special tie-in; just report fit vs tier.

---

## Advice taxonomy — prioritized, most-impactful first

Walk these in order. Surface only the ones that actually fire; a clean portfolio might
only trip one or two. Each item must carry a number and be framed as an *option*, never an
order ("rebalancing would move you toward your target" — not "sell X").

1. **Allocation drift → rebalancing.** From the snapshot's `rebalance` array. Threshold:
   `|drift_pp| ≥ 3` is worth an action; quote the exact `delta_eur` ("Buy €X" / "Sell €X").
   This is the single highest-signal section — lead with it. Sequence the moves: deploying
   idle cash into the most-underweight category is usually the cheapest first step.

2. **Concentration risk.** Largest single `position.weight`. Flag if a *single stock* (not a
   diversified ETF) exceeds ~10–15% of the grand total. Name the ticker and its %.

3. **Look-through overlap.** If the user holds a global-equity ETF (WEBG/VWCE/IWDA) **and** a
   US or single-stock bucket, note the effective US/overlap weight is higher than the
   category table shows (MSCI World is ~70% US). Purely interpretive, no action required.

4. **Cash drag.** From the income audit's `cash` block and the snapshot's `cash_eur` vs the
   `cash` target weight. If cash sits far above target and earns below `cash_interest_pct`'s
   opportunity (or the user's horizon is long), note the annual drag in EUR. Deploying it
   ties back to item 1.

5. **Fees / yield gaps.** If the income audit shows a `zero_yield_native` flag on a fund you'd
   expect to distribute, or a proxy mismatch, mention it — but route any *fix* to tune-income.

6. **EU tax nudge (pick at most one, only if relevant).**
   - **Teilfreistellung:** equity ETFs keep a 30% partial exemption; individual stocks and
     bond funds don't. If the config's `teilfreistellung` looks miscategorised, flag it and
     point to tune-income.
   - **Acc vs dist:** accumulating funds (WEBG, SXR8, EUNA here) pay no cash — fine for a
     long-horizon growth goal, worth noting if the user wants income now.
   - **Vorabpauschale:** German accumulating-fund holders owe a small advance-tax in January;
     keeping a little cash buffer for it is sensible. One sentence, then stop.

   Tax points are *general rules*, not a personal computation — for the actual numbers and
   config, defer to **tune-income**.

Drop entirely (overkill for a single-user tracker): Sharpe/mean-variance optimization,
backtests, tax-loss harvesting, factor tilts, withdrawal-sequencing, stress tests.

---

## Framing rules (responsible, non-licensed)

- One standing line: **"Educational, not personalized investment advice — investing involves
  risk."** Say it once, at the end. Don't hedge every sentence.
- Describe observations against the user's *own* targets; never recommend a specific security
  to buy/sell, never predict prices or time the market.
- Keep the user as decision-maker: present trade-offs and options, then ask what they want.
- State assumptions (region = Germany/EU, numbers from a live yfinance fetch at the snapshot
  timestamp, targets from their config).

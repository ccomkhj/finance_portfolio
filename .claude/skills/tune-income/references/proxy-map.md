# Finding income proxies for accumulating funds

An accumulating ETF reinvests its income internally, so it distributes ~nothing
and yfinance reports a trailing yield near 0%. To estimate what it *earns*
(economic income), point it at a **distributing sibling** that tracks the same
index — the sibling pays out, so its live yield is a good stand-in. That sibling
ticker goes in `config.yaml` as `income: { <holding>: { proxy: <sibling> } }`.

## How to pick a proxy

1. **Same index, distributing share class.** Find the same fund family's (or any
   provider's) *Distributing* version of the same underlying index. "Acc" / "C"
   share classes accumulate; "Dist" / "Dis" / "D" distribute.
2. **Prefer an EUR listing** (`.DE` Xetra, `.AS` Amsterdam) or `.L` London. The
   proxy's yield is a *percentage*, so its listing currency doesn't matter to the
   math — but a EUR/EU listing is most likely to be quoted on yfinance.
3. **Verify it resolves.** Run the audit script (see SKILL.md). A proxy that
   returns no yield (`broken_proxy`) is delisted or mis-spelled — pick another
   listing or fall back to a manual `yield_pct`.
4. **Sanity-check the number.** The proxy yield should be in a plausible range for
   the index (broad world equity ≈ 1.5–2%, S&P 500 ≈ 1.2–1.5%, aggregate bonds ≈
   2–3%). A wildly off number means you grabbed the wrong fund (e.g. a sector or
   high-dividend variant, not the plain index).

## Starting candidates (verify each with the audit before trusting it)

These are common Trade Republic accumulating holdings and a distributing twin on
the same index. The yfinance symbol is a *candidate* — listings get delisted and
renamed, so always confirm it resolves rather than pasting it in blind.

| Accumulating holding | Index | Distributing twin (ISIN) | Candidate yfinance symbol |
|---|---|---|---|
| `SXR8.DE` / `CSPX` (iShares Core S&P 500 Acc) | S&P 500 | Vanguard S&P 500 Dist (IE00B3XXRP09) | `VUSA.DE`, `VUSA.AS`, `VUSA.L` |
| ″ | S&P 500 | iShares Core S&P 500 Dist (IE0031442068) | `IUSA.AS`, `IUSA.L` |
| `WEBG.DE` (Amundi Prime All World Acc) | FTSE All-World | Vanguard FTSE All-World Dist (IE00B3RBWM25) | `VWRL.AS`, `VWRL.L`, `VWRL.DE` |
| `VWCE.DE` (Vanguard FTSE All-World Acc) | FTSE All-World | Vanguard FTSE All-World Dist (IE00B3RBWM25) | `VWRL.AS`, `VWRL.L` |
| `IWDA.AS` (iShares Core MSCI World Acc) | MSCI World | iShares MSCI World Dist (IE00B0M62Q58) | `IWRD.L`, `IWRD.AS` |
| `EUNA.DE` (iShares Core Global Agg Bond EUR-H Acc) | Global Aggregate (EUR-hedged) | distributing twin **delisted on yfinance** | — use manual `yield_pct` |

## When to use a manual yield instead of a proxy

Some funds have no cleanly-quoted distributing twin — bond ETFs especially (the
`EUNA.DE` twin `AGGH` is delisted on yfinance, which is exactly the kind of trap
the audit's `broken_proxy` flag catches). In those cases read the **distribution
yield** off the fund's official factsheet/KID and set it directly:

```yaml
income:
  EUNA.DE: { yield_pct: 2.4 }   # from the iShares factsheet, "distribution yield"
```

Manual yields are static — they drift as rates move, so re-check them against the
factsheet a couple of times a year. A proxy ticker, by contrast, updates itself
on every fetch, which is why it's preferred whenever a live twin exists.

## Distributing single stocks need nothing

Ordinary dividend-paying stocks (e.g. `VOW.DE`, `SHL.DE`) already distribute, so
their own yfinance trailing yield is correct — leave them out of the `income:`
block entirely. Note the audit may flag such a stock as `zero_yield_native` if it
simply hasn't paid in the last 12 months (e.g. a suspended or annual-only
dividend just outside the window); that's a genuine zero, not an accumulating
fund, so no proxy is needed — confirm by checking whether the holding is a fund
or a stock.

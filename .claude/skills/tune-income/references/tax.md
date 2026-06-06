# Net-of-tax (German) model

`portfolio income --net` (and the dashboard's "Net of tax" toggle) applies a flat
German capital-income tax with per-holding **Teilfreistellung** (partial
exemption). It's a deliberate approximation — accurate enough to compare holdings
and gauge take-home, but it does **not** model the Sparer-Pauschbetrag allowance,
the Vorabpauschale on accumulating funds, or loss offsetting. Keep that framing
when reporting net numbers: call them "rough after-tax", not "what you'll owe".

## The formula

For each holding, `net = gross × (1 − rate_pct/100 × (1 − exemption))`.

- `rate_pct` defaults to **26.375%** = Kapitalertragsteuer (25%) + Solidaritäts­zuschlag
  (5.5% of that). With church tax it rises:
  - Bavaria/Baden-Württemberg (8%): ≈ **27.82%**
  - rest of Germany (9%): ≈ **27.99%**
- `exemption` comes from the holding's Teilfreistellung class.

Cash interest gets **no** Teilfreistellung — it's always taxed at the full rate.

## Teilfreistellung classes

| Class | Exemption | What it covers | Effective rate at 26.375% |
|---|---|---|---|
| `equity` | 30% | Equity funds — UCITS ETFs/funds holding ≥51% stocks | ~18.46% |
| `mixed` | 15% | Mixed funds holding ≥25% (but <51%) stocks | ~22.42% |
| `none` | 0% | Individual stocks, bond funds, money-market funds, cash | 26.375% |

Teilfreistellung is a **fund** rule. An individual share (e.g. `VOW.DE`,
`SHL.DE`) is not a fund, so it gets **`none`** — the full rate. Bond ETFs (e.g.
`EUNA.DE`) hold <25% equity, so they're **`none`** too. Only genuine equity/mixed
*funds* get an exemption.

## The default-equity trap

`default_teilfreistellung` (itself defaulting to `equity`) is applied to every
holding you don't list explicitly. That's convenient for an ETF-heavy portfolio,
but it silently hands the 30% equity exemption to any **stock or bond fund** you
forgot to mark — overstating their net income. The audit script flags these as
`teilfreistellung_default`; resolve each by deciding its real class and, for
stocks and bond funds, setting `none`:

```yaml
tax:
  rate_pct: 26.375           # bump to ~27.8–28 if the user pays church tax
  default_teilfreistellung: equity
  teilfreistellung:
    VOW.DE: none             # individual stock
    SHL.DE: none             # individual stock
    EUNA.DE: none            # bond fund
    # equity ETFs (SXR8.DE, WEBG.DE) inherit the equity default — leave them out
```

## Don't guess the user's situation

Two inputs are personal and must come from the user, not a default:

- **Church tax** — changes `rate_pct`. Ask; many people don't pay it.
- **Fund classification** when genuinely unclear (a thematic or commodity ETF may
  not be an equity fund for Teilfreistellung purposes) — point them at the fund's
  KID/factsheet ("Teilfreistellungssatz") rather than assuming.

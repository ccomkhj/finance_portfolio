# Baseline strategy: bubble-aware balanced portfolio

The bundled demo (`data/config.yaml`) ships with these target weights. They are
a starting point, not advice — edit them for your own situation. See
[DISCLAIMER.md](../DISCLAIMER.md).

## Target allocation

| Asset                              | Allocation | Purpose                                 |
| ---------------------------------- | ---------: | --------------------------------------- |
| **Bond ETFs / high-quality bonds** |    **35%** | Stability, income, recession protection |
| **Global equity ETFs**             |    **30%** | Long-term growth, diversified exposure  |
| **Cash / T-bills / money market**  |    **20%** | Dry powder for market crashes           |
| **Gold**                           |    **10%** | Crisis and currency hedge               |
| **Individual stocks**              |     **5%** | Optional high-conviction positions only |

**Core idea:** 35% equities (30% ETFs + 5% individual stocks), 35% bonds,
20% cash, 10% gold. This protects against a bubble crash without the dangerous
bet of going fully to cash.

## Simple implementation

**Equity ETFs — 30%**

- 15% global broad-market ETF
- 10% developed markets ex-U.S. ETF
- 5% value / quality ETF

**Bonds — 35%**

- 15% short-term government bonds or T-bills
- 10% intermediate government bonds
- 5% investment-grade bond ETF
- 5% inflation-linked bonds

**Cash — 20%**

- Keep part as an emergency reserve
- Use the rest to buy during drawdowns

**Gold — 10%**

- Hold as insurance
- Do not chase if it spikes

**Individual stocks — 5%**

- Only profitable, low-debt, high-quality companies
- No single stock above 2% of the portfolio

> The bundled demo keeps a flat category model (`global-equity`,
> `individual-stocks`, `bonds`, `gold`, `cash`). Split a category into the
> sub-buckets above if you want finer-grained drift tracking.

## Crash-buying rule

| Market decline                   | Action                                        |
| -------------------------------- | --------------------------------------------- |
| **-10%**                         | Invest 3–5% cash into equity ETFs             |
| **-20%**                         | Invest another 5%                             |
| **-30% or more**                 | Buy more aggressively, still using broad ETFs |
| **Equities exceed target by 5%** | Rebalance and trim                            |

`portfolio show` surfaces the category drift and per-category `DELTA EUR` that
this rule acts on: positive means buy that category, negative means trim it.

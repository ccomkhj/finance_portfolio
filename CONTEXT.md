# Portfolio Tracker

A private, single-user net-worth tracker for a Trade Republic portfolio:
snapshot-based EUR valuation, ISIN categorization, and category-level
rebalancing hints, sourced from broker Net Worth PDFs parsed into
`data/accounts/*.json` + `data/config.yaml`.

## Language

**Snapshot**:
A parsed representation of one broker statement at a specific date. Contains
one or more Holdings plus a cash balance, all in EUR.

**Holding**:
One ISIN line from a broker snapshot: ISIN, display name, quantity, per-unit
price, and EUR market value as reported in the statement.

**Category**:
A named bucket (e.g. `global-equity`, `bonds`) with a target weight and a
list of ISINs assigned to it. Defined in `data/config.yaml`.

**Net worth**:
Total EUR across all snapshots (holdings + cash). Computed from PDF-reported
EUR values — no live prices are fetched.

**Uncategorized ISIN**:
An ISIN present in a snapshot that is not yet assigned to any category. Shown
as a warning in the CLI and dashboard until the user assigns it.

## Relationships

- A **Snapshot** contains one or more **Holdings** and a cash balance.
- A **Category** aggregates the EUR values of all Holdings whose ISIN is in
  that category's ISIN list.
- **Net worth** is the sum of all category totals plus any uncategorized
  holding values and cash balances.

## Boundaries

- All EUR values come from the broker PDF — no live price fetching, no yfinance,
  no external APIs. Values reflect the date on the statement.
- No cost-basis tracking, no P&L, no tax modelling.
- Income estimates are an explicit non-goal in this version.

## Flagged ambiguities

- "Cash" appears both as a category target (the allocation % the user wants in
  liquid cash) and as a per-snapshot field (the actual cash balance reported by
  the broker). These are kept distinct: the snapshot's `cash_eur` field flows
  into the `cash` category aggregate.

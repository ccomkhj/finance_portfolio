# Common task recipes

Use these when the user asks for a specific mutation ("add Tesla", "change my target", "I deposited €500"). Each recipe lists the exact steps and which files to touch.

## Record a new buy or sell

**Preferred (CLI):**
```bash
uv run portfolio add-buy <TICKER> <QTY> <PRICE>
uv run portfolio add-sell <TICKER> <QTY> <PRICE>
```

Defaults: today's date, `EUR`. Atomic append (safe to Ctrl-C). The CLI validates the ticker is known to `config.yaml` before writing — unknown ticker fails without mutating the file.

**Manual (editor):** append a row to `data/transactions.csv`. Then run `uv run portfolio check` to validate. Manual is faster when back-filling many historical trades.

See `cli-reference.md` for full flag details.

## Add a new ticker to an existing category

1. Edit `data/config.yaml`, add the ticker to the `tickers:` list of the right category.
2. Verify the ticker is live on yfinance:
   ```bash
   uv run python -c "from portfolio.prices import fetch_prices; print(fetch_prices(['NEW.TICKER']))"
   ```
   NaN → skip, pick a different listing (see `data-schema.md` for known-working ETFs).
3. `uv run portfolio check` — should still pass.
4. Now `add-buy` will accept it.

No transactions are needed yet — the ticker can sit in config with zero holdings. `portfolio show` just won't list it until there's a position.

## Create a new category

1. Edit `data/config.yaml`, add the category block under `categories:`.
2. **Rebalance the target weights so they sum to 1.0.** Decide where the weight comes from (shrink an existing category).
3. Move any tickers that belong to the new category from their old category's `tickers:` list to the new one.
4. `uv run portfolio check` — if it fails with a sum message, adjust the weights.
5. `uv run portfolio show` — new category appears in the drift table, even with zero holdings (shows a Buy delta equal to its share of the portfolio).

## Rename a category

1. Edit `data/config.yaml` — change the category's key.
2. No transaction changes needed (the ticker-to-category mapping is derived from config at read time).
3. **If renaming `cash`**, also patch `app.py:_render_allocation` — the string `"cash"` is hardcoded as the category label for the cash balance. Without that patch the pie chart will show a `cash` slice while the rebalance table shows your new name.
4. `portfolio check` to confirm.

## Change target weights

1. Edit `data/config.yaml`, adjust `target_weight` values.
2. Weights must still sum to 1.0 (±0.001) across all categories.
3. `portfolio check`. If weights don't sum, the error message tells you the actual sum — adjust one category to close the gap.
4. `portfolio show` — drift table now reflects the new targets.

## Swap a ticker that went delisted on yfinance

Yahoo occasionally drops EU listings. Symptom: `portfolio show` prints a `possibly delisted` warning, and the position silently falls out of the positions table.

1. Find a replacement ticker for the same underlying fund. Common swaps:
   - `AGGH.DE` → `EUNA.DE` (iShares Core Global Aggregate Bond, Xetra)
   - Any Xetra ticker that's dropped → try the Amsterdam (`.AS`) listing, or the London (`.L`) listing
   - Verify with the `fetch_prices` one-liner above.
2. Edit `data/config.yaml`: replace the old ticker in its category's `tickers:` list with the new one.
3. Edit `data/transactions.csv`: rewrite the old ticker to the new one on every row that references it.
   - Safe because you're renaming the same real-world holding; cost basis is unaffected.
   - If the user actually sold the old and bought the new (not a symbol change, an actual trade), record a `sell` of old + `buy` of new instead.
4. `portfolio check`.
5. `portfolio show` — position reappears with a live price.

## Update the cash balance after a deposit / withdrawal

The tool has no `add-cash` command. Edit `data/config.yaml`:

```yaml
cash_balance_eur: 1500.00   # was 1250.00; deposited €250
```

Commit with a clear message (`chore(data): record €250 deposit`). `git log data/config.yaml` is the audit trail.

## Get a structured snapshot for analysis

Prefer this over parsing `portfolio show` output:

```bash
./.claude/skills/assess-portfolio/scripts/snapshot.sh > /tmp/snap.json
# or compact JSON for pipelining
./.claude/skills/assess-portfolio/scripts/snapshot.sh --compact | jq '.totals'
```

The JSON shape is documented at the top of `scripts/snapshot.py`. Use for:
- Feeding into another tool (e.g., a spreadsheet sync)
- Programmatic assessments in this skill
- Computing metrics the CLI doesn't print (e.g., weight-standardized rebalance deltas, per-currency exposure)

## Run a dry-run scenario without touching real data

Use the global `--config` and `--transactions` flags:

```bash
uv run portfolio --config scenarios/my-plan.yaml --transactions scenarios/my-plan.csv show
```

Copy `data/` → `scenarios/my-plan/`, edit freely, run `show` or `check` against the scenario files. Your real data is untouched.

## Start over on a specific position

Rare but sometimes needed after a data-entry mistake found months later:

1. Edit `data/transactions.csv`, delete all rows for that ticker.
2. Append fresh buy rows with the correct history.
3. `portfolio check`, then `portfolio show` — verify the avg cost matches your records.

Direct CSV edit is always safe as long as the resulting file passes `portfolio check`.

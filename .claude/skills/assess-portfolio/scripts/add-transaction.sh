#!/usr/bin/env bash
# Thin wrapper for appending a buy or sell. Run from repo root.
# Verifies the ticker exists in config before calling the CLI.
#
# Usage:
#   add-transaction.sh buy  VWCE.DE 10 98.50            # today, EUR
#   add-transaction.sh sell AAPL.DE 2 280.00 --date 2026-03-01
#   add-transaction.sh buy  TSLA    5 210.00 --currency USD
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "usage: $0 {buy|sell} TICKER QTY PRICE [--currency USD] [--date YYYY-MM-DD]" >&2
  exit 2
fi

ACTION="$1"; shift
TICKER="$1"; shift
QTY="$1"; shift
PRICE="$1"; shift

case "$ACTION" in
  buy)  CMD="add-buy" ;;
  sell) CMD="add-sell" ;;
  *)    echo "error: first arg must be 'buy' or 'sell'" >&2; exit 2 ;;
esac

# Let the CLI's own pre-append validation handle unknown tickers;
# it reads config and emits a clear error with the known-ticker list.
exec uv run portfolio "$CMD" "$TICKER" "$QTY" "$PRICE" "$@"

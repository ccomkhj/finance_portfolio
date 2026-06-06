#!/usr/bin/env bash
# Audit the income config and emit JSON findings. Run from the repo root.
# Usage:
#   .claude/skills/tune-income/scripts/audit-income.sh           # pretty JSON
#   .claude/skills/tune-income/scripts/audit-income.sh --compact # single-line JSON
set -euo pipefail

INDENT=2
if [[ "${1:-}" == "--compact" ]]; then
  INDENT=0
fi

uv run python .claude/skills/tune-income/scripts/audit-income.py --indent "$INDENT"

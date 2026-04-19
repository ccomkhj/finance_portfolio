#!/usr/bin/env bash
# Run a full portfolio snapshot and emit JSON. Run from repo root.
# Usage:
#   .claude/skills/assess-portfolio/scripts/snapshot.sh           # pretty JSON to stdout
#   .claude/skills/assess-portfolio/scripts/snapshot.sh --compact # single-line JSON
set -euo pipefail

INDENT=2
if [[ "${1:-}" == "--compact" ]]; then
  INDENT=0
fi

uv run python .claude/skills/assess-portfolio/scripts/snapshot.py --indent "$INDENT"

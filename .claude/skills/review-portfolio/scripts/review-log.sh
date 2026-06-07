#!/usr/bin/env bash
# Thin wrapper around review-log.py — the portfolio-review journal. Run from repo root.
# Usage:
#   .claude/skills/review-portfolio/scripts/review-log.sh last        # most recent review (JSON)
#   .claude/skills/review-portfolio/scripts/review-log.sh list        # all review dates (JSON array)
#   echo '<json>' | .claude/skills/review-portfolio/scripts/review-log.sh save   # append a review
set -euo pipefail

uv run python .claude/skills/review-portfolio/scripts/review-log.py "$@"

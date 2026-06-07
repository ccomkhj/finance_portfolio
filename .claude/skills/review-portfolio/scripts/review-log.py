#!/usr/bin/env python3
"""Append-only journal for portfolio reviews — the skill's memory across sessions.

Each review is one JSON object on its own line in data/reviews.jsonl (JSONL).
A record captures the Q&A profile the user gave, a few headline status numbers,
and the *expectations* set that session — so the next review can recall what was
expected last time and check whether it played out.

Commands:
  last            Emit the most recent saved review as pretty JSON ({} if none).
  list            Emit a compact array of {date, goal, risk_tier} for every review.
  save            Read a JSON record from stdin, stamp `date` (today, if absent),
                  append it to the journal, and echo the saved record back.

Usage (run from repo root):
  .claude/skills/review-portfolio/scripts/review-log.py last
  .claude/skills/review-portfolio/scripts/review-log.py list
  echo '{"profile":{...},"status":{...},"expectations":[...]}' \
      | .claude/skills/review-portfolio/scripts/review-log.py save

Record shape (fields are advisory, not enforced — store what's useful):
  {
    "date": "YYYY-MM-DD",
    "profile":      {"horizon": "...", "drawdown": "...", "goal": "...", "risk_tier": "..."},
    "status":       {"grand_total_eur": ..., "pnl_pct": ..., "cash_pct": ...,
                     "top_position": {"ticker": "...", "weight_pct": ...},
                     "largest_drift": {"category": "...", "drift_pp": ...}},
    "expectations": ["plain-language things expected to happen before next review"],
    "advice":       ["the prioritized actions surfaced this session"],
    "notes":        "free text"
  }
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

# Journal lives beside the other hand-edited data files. Override with
# REVIEW_JOURNAL to redirect (used by tests, or to keep history elsewhere).
JOURNAL = Path(os.environ.get("REVIEW_JOURNAL", "data/reviews.jsonl"))


def _read_all() -> list[dict]:
    if not JOURNAL.exists():
        return []
    records = []
    for line in JOURNAL.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            # A corrupt line shouldn't sink the whole history; skip and warn.
            print(f"warning: skipping unparseable journal line: {line[:80]}",
                  file=sys.stderr)
    return records


def cmd_last() -> int:
    records = _read_all()
    print(json.dumps(records[-1] if records else {}, indent=2, ensure_ascii=False))
    return 0


def cmd_list() -> int:
    summary = [
        {
            "date": r.get("date"),
            "goal": r.get("profile", {}).get("goal"),
            "risk_tier": r.get("profile", {}).get("risk_tier"),
        }
        for r in _read_all()
    ]
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_save() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print("error: no JSON on stdin to save", file=sys.stderr)
        return 1
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: stdin is not valid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(record, dict):
        print("error: review record must be a JSON object", file=sys.stderr)
        return 1

    record.setdefault("date", date.today().isoformat())

    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(json.dumps(record, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["last", "list", "save"])
    args = parser.parse_args()
    return {"last": cmd_last, "list": cmd_list, "save": cmd_save}[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())

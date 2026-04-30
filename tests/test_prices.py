from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from portfolio import prices


def test_load_cache_missing_file_returns_empty(tmp_path: Path) -> None:
    assert prices._load_cache(tmp_path / "nope.json") == {}


def test_load_cache_corrupt_json_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "cache.json"
    p.write_text("{not json")
    assert prices._load_cache(p) == {}


def test_load_cache_reads_valid_json(tmp_path: Path) -> None:
    p = tmp_path / "cache.json"
    p.write_text('{"VWCE.DE": {"price": 153.66, "fetched_at": "2026-04-29T10:00:00Z"}}')
    cache = prices._load_cache(p)
    assert cache["VWCE.DE"]["price"] == 153.66


def test_save_cache_writes_atomically(tmp_path: Path) -> None:
    p = tmp_path / "subdir" / "cache.json"
    cache = {"X": {"price": 1.0, "fetched_at": "2026-04-29T10:00:00Z"}}
    prices._save_cache(p, cache)
    assert json.loads(p.read_text()) == cache
    # No leftover .tmp sibling
    assert not list(p.parent.glob("*.tmp"))


def test_ttl_constant_is_600() -> None:
    assert prices.PRICE_CACHE_TTL_SECONDS == 600

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


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def test_fetch_prices_cache_miss_calls_yf_and_writes_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "cache.json"
    calls: list[list[str]] = []

    def fake_yf(tickers: list[str]) -> dict[str, float]:
        calls.append(list(tickers))
        return {t: 100.0 for t in tickers}

    monkeypatch.setattr(prices, "_fetch_prices_yf", fake_yf)
    now = datetime(2026, 4, 29, 10, 0, 0, tzinfo=timezone.utc)

    result = prices.fetch_prices(["VWCE.DE"], cache_path=cache_path, now=now)

    assert result == {"VWCE.DE": 100.0}
    assert calls == [["VWCE.DE"]]
    cache = json.loads(cache_path.read_text())
    assert cache["VWCE.DE"]["price"] == 100.0


def test_fetch_prices_cache_hit_skips_yf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "cache.json"
    fetched_at = datetime(2026, 4, 29, 10, 0, 0, tzinfo=timezone.utc)
    cache_path.write_text(json.dumps({
        "VWCE.DE": {"price": 153.66, "fetched_at": _iso(fetched_at)}
    }))

    def fail_yf(tickers: list[str]) -> dict[str, float]:
        raise AssertionError("yfinance should not be called")

    monkeypatch.setattr(prices, "_fetch_prices_yf", fail_yf)
    now = fetched_at  # 0 seconds elapsed

    result = prices.fetch_prices(["VWCE.DE"], cache_path=cache_path, now=now)
    assert result == {"VWCE.DE": 153.66}


def test_fetch_prices_stale_entry_refetches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "cache.json"
    fetched_at = datetime(2026, 4, 29, 10, 0, 0, tzinfo=timezone.utc)
    cache_path.write_text(json.dumps({
        "VWCE.DE": {"price": 100.0, "fetched_at": _iso(fetched_at)}
    }))

    def fake_yf(tickers: list[str]) -> dict[str, float]:
        return {"VWCE.DE": 200.0}

    monkeypatch.setattr(prices, "_fetch_prices_yf", fake_yf)
    now = fetched_at.replace(hour=11)  # 1 hour later, well past 600s TTL

    result = prices.fetch_prices(["VWCE.DE"], cache_path=cache_path, now=now)
    assert result == {"VWCE.DE": 200.0}
    cache = json.loads(cache_path.read_text())
    assert cache["VWCE.DE"]["price"] == 200.0


def test_fetch_prices_partial_hit_only_fetches_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "cache.json"
    fetched_at = datetime(2026, 4, 29, 10, 0, 0, tzinfo=timezone.utc)
    cache_path.write_text(json.dumps({
        "A.DE": {"price": 1.0, "fetched_at": _iso(fetched_at)}
    }))
    calls: list[list[str]] = []

    def fake_yf(tickers: list[str]) -> dict[str, float]:
        calls.append(list(tickers))
        return {t: 9.0 for t in tickers}

    monkeypatch.setattr(prices, "_fetch_prices_yf", fake_yf)
    now = fetched_at

    result = prices.fetch_prices(["A.DE", "B.DE"], cache_path=cache_path, now=now)
    assert result == {"A.DE": 1.0, "B.DE": 9.0}
    assert calls == [["B.DE"]]


def test_fetch_prices_empty_tickers_returns_empty(tmp_path: Path) -> None:
    assert prices.fetch_prices([], cache_path=tmp_path / "cache.json") == {}

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
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


def test_yf_error_with_stale_cache_returns_stale_with_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    cache_path = tmp_path / "cache.json"
    old = datetime(2026, 4, 28, 10, 0, 0, tzinfo=timezone.utc)
    cache_path.write_text(json.dumps({
        "VWCE.DE": {"price": 150.0, "fetched_at": _iso(old)}
    }))

    def boom(tickers: list[str]) -> dict[str, float]:
        raise RuntimeError("yfinance down")

    monkeypatch.setattr(prices, "_fetch_prices_yf", boom)
    now = datetime(2026, 4, 29, 10, 0, 0, tzinfo=timezone.utc)

    result = prices.fetch_prices(["VWCE.DE"], cache_path=cache_path, now=now)
    assert result == {"VWCE.DE": 150.0}

    err = capsys.readouterr().err
    assert "warning" in err.lower()
    assert "yfinance" in err.lower()


def test_yf_error_no_cache_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "cache.json"

    def boom(tickers: list[str]) -> dict[str, float]:
        raise RuntimeError("yfinance down")

    monkeypatch.setattr(prices, "_fetch_prices_yf", boom)
    now = datetime(2026, 4, 29, 10, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(RuntimeError, match="yfinance down"):
        prices.fetch_prices(["VWCE.DE"], cache_path=cache_path, now=now)


def test_yf_error_partial_cache_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One ticker has stale cache, the other has none — must propagate."""
    cache_path = tmp_path / "cache.json"
    old = datetime(2026, 4, 28, 10, 0, 0, tzinfo=timezone.utc)
    cache_path.write_text(json.dumps({
        "A.DE": {"price": 1.0, "fetched_at": _iso(old)}
    }))

    def boom(tickers: list[str]) -> dict[str, float]:
        raise RuntimeError("yfinance down")

    monkeypatch.setattr(prices, "_fetch_prices_yf", boom)
    now = datetime(2026, 4, 29, 10, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(RuntimeError):
        prices.fetch_prices(["A.DE", "B.DE"], cache_path=cache_path, now=now)


# --- _is_fresh edge cases -----------------------------------------------------

def test_is_fresh_rejects_malformed_or_missing_timestamp() -> None:
    now = datetime(2026, 4, 29, 10, 0, 0, tzinfo=timezone.utc)
    assert prices._is_fresh({"price": 1.0, "fetched_at": "not-a-date"}, now) is False  # type: ignore[typeddict-item]
    assert prices._is_fresh({"price": 1.0}, now) is False  # type: ignore[typeddict-item]


# --- _save_cache failure cleanup ---------------------------------------------

def test_save_cache_cleans_temp_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "cache.json"

    def boom(_src: str, _dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(prices.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        prices._save_cache(p, {"X": {"price": 1.0, "fetched_at": "2026-04-29T10:00:00Z"}})

    assert not p.exists()
    assert not list(tmp_path.glob(".price_cache.*.tmp"))


# --- yfinance adapters (yf stubbed) ------------------------------------------

class _FakeTicker:
    """Minimal stand-in for yfinance.Ticker."""

    def __init__(self, *, info: dict | None = None, closes: list[float] | None = None):
        self._info = info
        self._closes = closes if closes is not None else []

    @property
    def info(self) -> dict:
        if self._info is None:
            raise RuntimeError("info unavailable")
        return self._info

    def history(self, **_kwargs: object) -> pd.DataFrame:
        return pd.DataFrame({"Close": self._closes})


def test_fetch_prices_yf_extracts_last_valid_close(monkeypatch: pytest.MonkeyPatch) -> None:
    df = pd.DataFrame({
        ("VWCE.DE", "Close"): [100.0, 102.5],
        ("ALLNAN.DE", "Close"): [float("nan"), float("nan")],
    })
    monkeypatch.setattr(prices.yf, "download", lambda **_kw: df)

    out = prices._fetch_prices_yf(["VWCE.DE", "ALLNAN.DE", "MISSING.DE"])

    assert out["VWCE.DE"] == 102.5          # last non-NaN close
    assert out["ALLNAN.DE"] != out["ALLNAN.DE"]   # NaN: no usable close
    assert out["MISSING.DE"] != out["MISSING.DE"]  # NaN: ticker absent from frame


def test_fetch_prices_yf_empty_tickers_returns_empty() -> None:
    assert prices._fetch_prices_yf([]) == {}


def test_fetch_names_uses_long_then_short_then_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    table = {
        "A": _FakeTicker(info={"longName": "Alpha ETF"}),
        "B": _FakeTicker(info={"shortName": "Beta"}),
        "C": _FakeTicker(info={}),       # no names → ticker itself
        "D": _FakeTicker(info=None),     # lookup raises → ticker itself
    }
    monkeypatch.setattr(prices.yf, "Ticker", lambda t: table[t])

    assert prices.fetch_names(["A", "B", "C", "D"]) == {
        "A": "Alpha ETF", "B": "Beta", "C": "C", "D": "D",
    }


def test_fetch_fx_eur_eur_is_one_others_from_yf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prices.yf, "Ticker", lambda pair: _FakeTicker(closes=[1.07, 1.09]))
    rates = prices.fetch_fx_eur(["EUR", "USD"])
    assert rates["EUR"] == 1.0
    assert rates["USD"] == 1.09


def test_fetch_fx_eur_empty_series_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prices.yf, "Ticker", lambda pair: _FakeTicker(closes=[]))
    with pytest.raises(RuntimeError, match="failed to fetch FX rate"):
        prices.fetch_fx_eur(["USD"])


def test_fetch_historical_fx_eur(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date

    monkeypatch.setattr(prices.yf, "Ticker", lambda pair: _FakeTicker(closes=[0.90, 0.92]))
    assert prices.fetch_historical_fx_eur("EUR", date(2026, 3, 10)) == 1.0
    assert prices.fetch_historical_fx_eur("USD", date(2026, 3, 10)) == 0.92


def test_fetch_historical_fx_eur_no_data_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date

    monkeypatch.setattr(prices.yf, "Ticker", lambda pair: _FakeTicker(closes=[]))
    with pytest.raises(RuntimeError, match="no FX data"):
        prices.fetch_historical_fx_eur("USD", date(2026, 3, 10))


# --- trailing-12-month dividend yield ----------------------------------------

def test_trailing_yield_sums_only_last_12_months() -> None:
    from datetime import date

    divs = [
        (date(2025, 6, 1), 1.0),
        (date(2025, 12, 1), 1.0),
        (date(2024, 6, 1), 5.0),  # older than 12 months → excluded
    ]
    y = prices._trailing_yield(divs, price=100.0, asof=date(2026, 3, 1))
    assert y == pytest.approx(0.02)


def test_trailing_yield_no_dividends_is_zero() -> None:
    from datetime import date

    assert prices._trailing_yield([], price=100.0, asof=date(2026, 1, 1)) == 0.0


def test_trailing_yield_annual_payer_in_dead_zone_annualizes_latest() -> None:
    from datetime import date

    # Volkswagen-style: pays once a year in May. Latest payment 2025-05-19 has
    # just aged out of the trailing-365 window (asof 2026-06-06), next not yet
    # posted. Should annualize the most recent payment, not report 0%.
    divs = [(date(2024, 5, 30), 9.00), (date(2025, 5, 19), 6.30)]
    y = prices._trailing_yield(divs, price=89.45, asof=date(2026, 6, 6))
    assert y == pytest.approx(6.30 / 89.45)


def test_trailing_yield_lapsed_dividend_beyond_grace_is_zero() -> None:
    from datetime import date

    # Last paid >15 months ago and nothing since → treat as genuinely stopped.
    divs = [(date(2024, 1, 1), 5.0)]
    assert prices._trailing_yield(divs, price=100.0, asof=date(2026, 6, 6)) == 0.0


def test_trailing_yield_nonpositive_price_is_nan() -> None:
    from datetime import date

    nan_price = prices._trailing_yield([(date(2026, 1, 1), 1.0)], price=float("nan"), asof=date(2026, 2, 1))
    zero_price = prices._trailing_yield([(date(2026, 1, 1), 1.0)], price=0.0, asof=date(2026, 2, 1))
    assert nan_price != nan_price
    assert zero_price != zero_price


class _FakeDivTicker:
    """Stand-in exposing yfinance's `.dividends` Series and `.history`."""

    def __init__(self, dividends: pd.Series, closes: list[float]):
        self._dividends = dividends
        self._closes = closes

    @property
    def dividends(self) -> pd.Series:
        return self._dividends

    def history(self, **_kwargs: object) -> pd.DataFrame:
        return pd.DataFrame({"Close": self._closes})


def test_fetch_dividend_yields_computes_trailing(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date

    idx = pd.to_datetime(["2024-06-01", "2025-06-01", "2025-12-01"])
    series = pd.Series([5.0, 1.0, 1.0], index=idx)
    table = {"VOW.DE": _FakeDivTicker(series, [100.0, 110.0])}
    monkeypatch.setattr(prices.yf, "Ticker", lambda t: table[t])

    out = prices.fetch_dividend_yields(["VOW.DE"], now=date(2026, 3, 1))
    assert out["VOW.DE"] == pytest.approx(2.0 / 110.0)


def test_fetch_dividend_yields_no_price_is_nan(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date

    table = {"X.DE": _FakeDivTicker(pd.Series([], dtype=float), [])}
    monkeypatch.setattr(prices.yf, "Ticker", lambda t: table[t])

    out = prices.fetch_dividend_yields(["X.DE"], now=date(2026, 1, 1))
    assert out["X.DE"] != out["X.DE"]


def test_fetch_dividend_yields_handles_ticker_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date

    def boom(_t: str) -> object:
        raise RuntimeError("yfinance dead")

    monkeypatch.setattr(prices.yf, "Ticker", boom)
    out = prices.fetch_dividend_yields(["DEAD.DE"], now=date(2026, 1, 1))
    assert out["DEAD.DE"] != out["DEAD.DE"]

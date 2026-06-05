from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

PRICE_CACHE_PATH = Path("data/.price_cache.json")
PRICE_CACHE_TTL_SECONDS = 600


def _load_cache(path: Path) -> dict[str, dict]:
    """Read the cache file. Missing or corrupt → empty dict."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(path: Path, cache: dict[str, dict]) -> None:
    """Atomic write: tmp file in same dir, fsync, rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".price_cache.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as tmp:
            tmp.write(json.dumps(cache, indent=2))
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    except Exception:
        if Path(tmp_name).exists():
            os.unlink(tmp_name)
        raise


def fetch_prices(
    tickers: list[str],
    *,
    cache_path: Path = PRICE_CACHE_PATH,
    now: datetime | None = None,
) -> dict[str, float]:
    """Fetch latest close prices, with a 10-minute disk cache.

    Cached values <PRICE_CACHE_TTL_SECONDS old are returned without hitting
    yfinance. Stale or missing tickers are refetched and the cache is updated.
    """
    if not tickers:
        return {}

    now = now or datetime.now(timezone.utc)
    cache = _load_cache(cache_path)

    fresh: dict[str, float] = {}
    stale_or_missing: list[str] = []
    for t in tickers:
        entry = cache.get(t)
        if entry and _is_fresh(entry, now):
            fresh[t] = entry["price"]
        else:
            stale_or_missing.append(t)

    if not stale_or_missing:
        return fresh

    try:
        new_prices = _fetch_prices_yf(stale_or_missing)
    except Exception as e:
        if all(t in cache for t in stale_or_missing):
            print(
                f"warning: yfinance error ({e}); using stale cached prices",
                file=sys.stderr,
            )
            for t in stale_or_missing:
                fresh[t] = cache[t]["price"]
            return fresh
        raise

    iso_now = now.isoformat().replace("+00:00", "Z")
    for t, p in new_prices.items():
        cache[t] = {"price": p, "fetched_at": iso_now}
    _save_cache(cache_path, cache)

    fresh.update(new_prices)
    return fresh


def _is_fresh(entry: dict, now: datetime) -> bool:
    try:
        fetched_at = datetime.fromisoformat(entry["fetched_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return False
    age = (now - fetched_at).total_seconds()
    return 0 <= age < PRICE_CACHE_TTL_SECONDS


def _fetch_prices_yf(tickers: list[str]) -> dict[str, float]:
    """Direct yfinance call. Returns ticker -> latest close (NaN on failure)."""
    if not tickers:
        return {}
    data = yf.download(
        tickers=tickers,
        period="5d",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
    )

    prices: dict[str, float] = {}
    for ticker in tickers:
        try:
            closes = data[ticker]["Close"]
        except KeyError:
            prices[ticker] = float("nan")
            continue
        closes = closes.dropna()
        prices[ticker] = float(closes.iloc[-1]) if len(closes) else float("nan")
    return prices


def fetch_names(tickers: list[str]) -> dict[str, str]:
    """Return ticker->company name. Falls back to the ticker itself on failure."""
    names: dict[str, str] = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            name = info.get("longName") or info.get("shortName") or t
        except Exception:
            name = t
        names[t] = name
    return names


def fetch_fx_eur(currencies: list[str]) -> dict[str, float]:
    """Return currency->EUR rate (i.e., how many EUR 1 unit of `currency` buys).

    EUR is always 1.0. For others, uses yfinance `<CUR>EUR=X` pair.
    """
    rates: dict[str, float] = {}
    for cur in currencies:
        if cur == "EUR":
            rates[cur] = 1.0
            continue
        pair = f"{cur}EUR=X"
        data = yf.Ticker(pair).history(period="5d", interval="1d", auto_adjust=False)
        closes = data["Close"].dropna()
        if len(closes) == 0:
            raise RuntimeError(f"failed to fetch FX rate for {pair}")
        rates[cur] = float(closes.iloc[-1])
    return rates


def fetch_historical_fx_eur(currency: str, target_date: date) -> float:
    """Return currency->EUR rate on `target_date` (uses nearest prior trading day)."""
    if currency == "EUR":
        return 1.0
    pair = f"{currency}EUR=X"
    start = target_date - timedelta(days=7)
    end = target_date + timedelta(days=1)
    data = yf.Ticker(pair).history(
        start=start.isoformat(), end=end.isoformat(), interval="1d", auto_adjust=False
    )
    closes = data["Close"].dropna()
    if len(closes) == 0:
        raise RuntimeError(f"no FX data for {pair} near {target_date}")
    return float(closes.iloc[-1])

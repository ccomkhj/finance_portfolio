from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict, cast

import yfinance as yf

PRICE_CACHE_PATH = Path("data/.price_cache.json")
PRICE_CACHE_TTL_SECONDS = 600

# Committed, price-only offline fallback for the public read-only demo, so the
# dashboard renders even when Yahoo throttles Streamlit Cloud's shared IPs.
SNAPSHOT_PATH = Path("data/demo_snapshot.json")


class CacheEntry(TypedDict):
    price: float
    fetched_at: str


def _load_cache(path: Path) -> dict[str, CacheEntry]:
    """Read the cache file. Missing or corrupt → empty dict."""
    try:
        return cast("dict[str, CacheEntry]", json.loads(path.read_text()))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(path: Path, cache: dict[str, CacheEntry]) -> None:
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
    # Persisting the cache is best-effort: a write failure (e.g. a read-only or
    # full filesystem on a hosted demo) must not discard prices we just fetched.
    try:
        _save_cache(cache_path, cache)
    except OSError as e:
        print(f"warning: could not persist price cache ({e})", file=sys.stderr)

    fresh.update(new_prices)
    return fresh


def load_price_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, float]:
    """Read the committed price-only demo snapshot. Missing or corrupt → {}."""
    try:
        return {str(k): float(v) for k, v in json.loads(path.read_text()).items()}
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def resolve_prices(
    tickers: list[str],
    *,
    fetch: Callable[[list[str]], dict[str, float]],
    read_only: bool,
    snapshot_path: Path = SNAPSHOT_PATH,
) -> tuple[dict[str, float], str]:
    """Live prices with an offline snapshot fallback for the public demo.

    Returns ``(prices, source)``. ``source`` is ``"live"`` when every value came
    from the live fetch, ``"snapshot"`` when any value was filled from the
    committed demo snapshot. The snapshot is consulted only when ``read_only`` is
    True, so local use keeps the injected fetcher exception-truthful (errors
    propagate) rather than silently degrading to stale sample data.
    """
    if not read_only:
        return fetch(tickers), "live"
    try:
        live = fetch(tickers)
    except Exception:  # noqa: BLE001 — demo must render regardless of fetch failure
        live = {}
    snap = load_price_snapshot(snapshot_path)
    merged: dict[str, float] = {}
    used_snapshot = False
    for t in tickers:
        v = live.get(t)
        if v is not None and v == v:  # not None, not NaN
            merged[t] = v
        elif t in snap:
            merged[t] = snap[t]
            used_snapshot = True
    return merged, ("snapshot" if used_snapshot else "live")


def _is_fresh(entry: CacheEntry, now: datetime) -> bool:
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


# Annual payers (common in the EU — e.g. Volkswagen pays once each May) spend
# part of every year in a "dead zone": the prior payment has aged out of the
# trailing-365 window but the next hasn't posted yet, which would read as 0%.
# When the window is empty we annualise the most recent payment instead, as long
# as it's recent enough to still be a live dividend rather than one that's been
# cut. ~15 months tolerates a late annual payment without resurrecting a stopped one.
DIVIDEND_GRACE_DAYS = 455


def _trailing_yield(
    dividends: list[tuple[date, float]], price: float, asof: date
) -> float:
    """Trailing-12-month dividends ÷ price, as a fraction. NaN if price <= 0/NaN.

    Falls back to annualising the most recent payment when nothing was paid in
    the trailing 12 months but a payment is recent enough to still be live —
    so annual payers don't flicker to 0% between yearly distributions.
    """
    if not (price > 0):  # also catches NaN
        return float("nan")
    trailing = sum(amt for d, amt in dividends if d >= asof - timedelta(days=365))
    if trailing == 0 and dividends:
        latest_date, latest_amt = max(dividends, key=lambda da: da[0])
        if (asof - latest_date).days <= DIVIDEND_GRACE_DAYS:
            trailing = latest_amt
    return trailing / price


def fetch_dividend_yields(
    tickers: list[str], *, now: date | None = None
) -> dict[str, float]:
    """Return ticker -> trailing-12-month dividend yield (fraction).

    0.0 means the holding genuinely paid nothing in the last year; NaN means the
    yield could not be sourced (no price, or yfinance failed for that ticker).
    """
    asof = now or datetime.now(timezone.utc).date()
    out: dict[str, float] = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            divs = [
                (ts.date(), float(amt))
                for ts, amt in t.dividends.items()
            ]
            closes = t.history(period="5d", interval="1d", auto_adjust=False)["Close"].dropna()
            price = float(closes.iloc[-1]) if len(closes) else float("nan")
            out[ticker] = _trailing_yield(divs, price, asof)
        except Exception:
            out[ticker] = float("nan")
    return out


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

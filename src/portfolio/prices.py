from __future__ import annotations

from datetime import date, timedelta

import yfinance as yf


def fetch_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch latest closing price for each ticker. NaN prices are included."""
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

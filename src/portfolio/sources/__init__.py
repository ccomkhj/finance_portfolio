from __future__ import annotations

from collections.abc import Callable

from portfolio.snapshot import Snapshot
from portfolio.sources import trade_republic

INGESTERS: dict[str, Callable[[object], Snapshot]] = {
    trade_republic.SOURCE: trade_republic.parse,
}


def supported_sources() -> list[str]:
    return sorted(INGESTERS)


def parse_pdf(pdf_source: object, source: str) -> Snapshot:
    try:
        ingester = INGESTERS[source]
    except KeyError:
        raise NotImplementedError(
            f"no ingester for source {source!r}; supported: {supported_sources()}"
        ) from None
    return ingester(pdf_source)

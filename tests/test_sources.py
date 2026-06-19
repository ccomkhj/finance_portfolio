from pathlib import Path
import pytest
from portfolio import sources

FIXTURE = Path(__file__).parent / "fixtures" / "trade_republic_networth.txt"


def test_supported_sources_includes_tr():
    assert "trade_republic" in sources.supported_sources()


def test_unknown_source_raises():
    with pytest.raises(NotImplementedError, match="trade_republic"):
        sources.parse_pdf("x.pdf", "trading_212")


def test_dispatch_runs_tr_parser(monkeypatch):
    lines = [ln for ln in FIXTURE.read_text().splitlines() if ln.strip()]
    from portfolio.sources import trade_republic
    monkeypatch.setattr(trade_republic, "extract_lines", lambda src: lines)
    snap = sources.parse_pdf("ignored.pdf", "trade_republic")
    assert len(snap.holdings) == 3

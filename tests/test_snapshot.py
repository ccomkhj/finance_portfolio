from datetime import date
from portfolio.snapshot import Holding, Snapshot, snapshot_to_dict, snapshot_from_dict


def _sample() -> Snapshot:
    return Snapshot(
        source="trade_republic",
        as_of=date(2026, 1, 15),
        account_ref="demo",
        currency="EUR",
        cash_eur=1000.0,
        holdings=(
            Holding("IE00B4L5Y983", "iShares Core MSCI World", 10.0, 90.0, 900.0),
            Holding("IE00B4ND3602", "iShares Physical Gold", 5.0, 60.0, 300.0),
        ),
        brokerage_total_eur=1200.0,
        total_eur=2200.0,
    )


def test_holdings_total():
    s = _sample()
    assert round(s.holdings_total_eur, 2) == 1200.0


def test_round_trip():
    s = _sample()
    restored = snapshot_from_dict(snapshot_to_dict(s))
    assert restored == s


def test_dict_is_json_friendly():
    import json
    d = snapshot_to_dict(_sample())
    assert json.loads(json.dumps(d))["as_of"] == "2026-01-15"

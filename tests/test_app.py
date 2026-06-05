from __future__ import annotations

import pytest

from app import SENTINEL, resolve_buy_ticker
from portfolio.mutations import ValidationError


def test_resolve_existing_ticker_is_not_new():
    assert resolve_buy_ticker("WEBG.DE", "", SENTINEL) == ("WEBG.DE", False)


def test_resolve_sentinel_with_text_is_new_and_stripped():
    assert resolve_buy_ticker(SENTINEL, "  SXR8.DE  ", SENTINEL) == ("SXR8.DE", True)


def test_resolve_sentinel_without_text_raises():
    with pytest.raises(ValidationError):
        resolve_buy_ticker(SENTINEL, "   ", SENTINEL)

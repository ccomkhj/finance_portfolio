import pytest
from portfolio.numbers import normalize_number


def test_comma_decimal_with_thousands():
    assert normalize_number("1.234,56", "comma") == 1234.56
    assert normalize_number("1.234.567,89", "comma") == 1234567.89


def test_comma_decimal_plain():
    assert normalize_number("70,12", "comma") == 70.12
    assert normalize_number("42", "comma") == 42.0


def test_dot_decimal():
    assert normalize_number("1,234.56", "dot") == 1234.56


def test_strips_spaces():
    assert normalize_number(" 5,506607 ", "comma") == 5.506607


def test_empty_raises():
    with pytest.raises(ValueError):
        normalize_number("", "comma")


def test_unknown_style_raises():
    with pytest.raises(ValueError):
        normalize_number("1", "binary")

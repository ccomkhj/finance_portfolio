from __future__ import annotations


def normalize_number(raw: str, decimal: str = "comma") -> float:
    """Parse a localized number to float.

    decimal="comma": German style — '.' is thousands, ',' is the decimal point
    ("1.234,56" -> 1234.56). decimal="dot": '.' is decimal, ',' is thousands.
    Raises ValueError on empty/non-numeric input or an unknown style.
    """
    s = str(raw).strip().replace(" ", "")
    if not s:
        raise ValueError("empty number")
    if decimal == "comma":
        s = s.replace(".", "").replace(",", ".")
    elif decimal == "dot":
        s = s.replace(",", "")
    else:
        raise ValueError(f"unknown decimal style {decimal!r}")
    return float(s)

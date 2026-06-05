from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


def normalize_number(raw: str, decimal: str) -> float:
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


_AUTO_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y")


def normalize_date(raw: str, fmt: str) -> date:
    s = str(raw).strip()
    if fmt == "auto":
        for f in _AUTO_DATE_FORMATS:
            try:
                return datetime.strptime(s, f).date()
            except ValueError:
                continue
        raise ValueError(f"unrecognized date {raw!r}")
    return datetime.strptime(s, fmt).date()


def normalize_action(raw: str, actions: dict[str, str]) -> str | None:
    return actions.get(str(raw).strip().lower())

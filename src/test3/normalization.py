from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


def number(raw: str) -> Decimal | None:
    text = raw.strip()
    if not text or re.fullmatch(r"(?i)n/?a|none|tbd|-|—", text):
        return None
    negative = text.startswith("(") and text.endswith(")") or text.startswith("-")
    cleaned = re.sub(r"[^0-9.,]", "", text)
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "") if cleaned.rfind(".") > cleaned.rfind(",") else cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(",") == 1 and len(cleaned.rsplit(",", 1)[1]) != 3:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        value = Decimal(cleaned)
        return -value if negative else value
    except InvalidOperation:
        return None


def date(raw: str, preference: str = "mdy") -> tuple[str | None, bool]:
    text = raw.strip()
    if re.fullmatch(r"\d{5}", text):
        value = datetime(1899, 12, 30) + timedelta(days=int(text))
        return value.date().isoformat(), False
    for pattern, order in ((r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", "ymd"), (r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$", preference)):
        match = re.match(pattern, text)
        if not match:
            continue
        a, b, c = map(int, match.groups())
        if order == "ymd": y, m, d, ambiguous = a, b, c, False
        else:
            y = c + (2000 if c < 70 else 1900 if c < 100 else 0)
            m, d = (a, b) if order == "mdy" else (b, a)
            if a > 12: m, d = b, a
            if b > 12: m, d = a, b
            ambiguous = a <= 12 and b <= 12 and a != b
        try:
            return datetime(y, m, d).date().isoformat(), ambiguous
        except ValueError:
            return None, False
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat(), False
        except ValueError:
            pass
    return None, False


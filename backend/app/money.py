from decimal import Decimal, ROUND_HALF_UP

LAKH = Decimal("100000")
CRORE = Decimal("10000000")


def q(d: Decimal, places: str = "1") -> Decimal:
    return d.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def inr(d: Decimal | None) -> str:
    """Full Indian digit grouping: ₹12,34,567."""
    if d is None:
        return "unknown"
    neg = d < 0
    s = str(q(abs(d)))
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    out = ",".join(groups + [tail]) if groups else tail
    return f"{'-' if neg else ''}₹{out}"


def inr_short(d: Decimal | None) -> str:
    """Compact: ₹6.3 lakh / ₹1.5 crore."""
    if d is None:
        return "unknown"
    neg, a = d < 0, abs(d)
    if a >= CRORE:
        s = f"₹{_trim(q(a / CRORE, '0.01'))} crore"
    elif a >= LAKH:
        s = f"₹{_trim(q(a / LAKH, '0.01'))} lakh"
    else:
        s = inr(a)
    return f"-{s}" if neg else s


def pct(d: Decimal | None) -> str:
    return "unknown" if d is None else f"{_trim(q(d, '0.1'))}%"


def _trim(d: Decimal) -> str:
    s = f"{d:f}"
    return s.rstrip("0").rstrip(".") if "." in s else s

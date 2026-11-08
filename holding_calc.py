"""Deterministic numbers for one SIP holding: XIRR, cost of redeeming now, and continue-vs-stop illustrations.
Mock assumptions: monthly instalments on the SIP date; every instalment has the same % return as the whole holding.
Equity tax: short-term (<=12 months) 20% + 4% cess; long-term gains under ₹1.25 lakh/yr exempt (assumes no other gains)."""
from datetime import date, timedelta


def inr(x):
    x = int(round(x))
    s = str(abs(x))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if x < 0 else "") + "₹" + s


def lots(inv, sip, day, today):
    n = max(1, round(inv / sip))
    amt = inv / n
    y, m = today.year, today.month
    if today.day < day:
        m -= 1
    out = []
    for _ in range(n):
        if m < 1:
            m, y = m + 12, y - 1
        out.append((date(y, m, day), amt))
        m -= 1
    return out[::-1]


def xirr(flows):
    t0 = min(d for d, _ in flows)
    npv = lambda r: sum(a / (1 + r) ** ((d - t0).days / 365) for d, a in flows)
    lo, hi = -0.99, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if npv(mid) > 0 else (lo, mid)
    return (lo + hi) / 2


def sip_fv(monthly, years, rate):
    i, m = rate / 12, years * 12
    return monthly * (((1 + i) ** m - 1) / i) * (1 + i)


def compute(cur, inv, sip, day, today=None, exit_days=365, exit_rate=0.01):
    today = today or date.today()
    L = lots(inv, sip, day, today)
    ratio = cur / inv
    x = xirr([(d, -a) for d, a in L] + [(today, cur)])
    exit_load = st_gain = lt_gain = 0.0
    for d, a in L:
        age = (today - d).days
        val = a * ratio
        if age < exit_days:
            exit_load += val * exit_rate
        if age > 365:
            lt_gain += val - a
        else:
            st_gain += val - a
    tax = st_gain * 0.208 + max(0.0, lt_gain - 125000) * 0.13
    cost = exit_load + tax + cur * 0.00001
    fv = lambda yrs, r: cur * (1 + r) ** yrs + sip_fv(sip, yrs, r)
    return {
        "xirr": f"{x * 100:.1f}%", "months": str(len(L)), "sip_amt": inr(sip), "h_value": inr(cur), "h_invested": inr(inv),
        "h_gain": inr(cur - inv), "rcost_full": inr(cost), "rexit_full": inr(exit_load), "rtax_full": inr(tax),
        "net_now": inr(cur - cost), "add5": inr(sip * 60),
        "fv5_8": inr(fv(5, 0.08)), "fv5_12": inr(fv(5, 0.12)), "fv10_8": inr(fv(10, 0.08)), "fv10_12": inr(fv(10, 0.12)),
        "inv5": inr(inv + sip * 60), "inv10": inr(inv + sip * 120),
    }


if __name__ == "__main__":
    for k, v in compute(52129, 46998, 2611, 5).items():
        print(k, v)

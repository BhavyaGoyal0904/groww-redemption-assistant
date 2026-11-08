"""Automatic pre-debit balance check (user test 3).

Before a SIP debit, with the user's consent (in production: RBI Account Aggregator), fetch the bank balance, subtract known
payments due before the debit date, and compare with the SIPs due plus a cushion. If it's short, propose skipping the
smallest SIP(s) that close the gap. It never skips on its own: the user confirms, the rules are re-checked, and the user is
told the outcome. Prototype: the bank account is a mock.
"""
from datetime import timedelta

from sip_actions import working_days_until, dtext, inr, LOCK_WORKING_DAYS

CUSHION = 1000


def skip_deadline(today, due):
    """Last day a skip request still applies to this debit (more than 2 working days before it)."""
    d, last = today, None
    while d < due:
        if working_days_until(d, due) > LOCK_WORKING_DAYS:
            last = d
        d += timedelta(days=1)
    return last


def run_check(book, bank, due_date):
    due = book.due_on(due_date)
    due_total = sum(a for _, _, a in due)
    outflows = [o for o in bank["outflows"] if book.today <= o["date"] < due_date]
    out_total = sum(o["amount"] for o in outflows)
    expected = bank["balance"] - out_total
    res = {"checked_on": dtext(book.today), "debit_date": dtext(due_date), "balance": bank["balance"],
           "payments_before_debit": [{"date": dtext(o["date"]), "what": o["what"], "amount": o["amount"]} for o in outflows],
           "expected_on_debit_date": expected, "sips_due": [{"fund_id": f, "name": n, "amount": a} for f, n, a in due],
           "due_total": due_total, "cushion": CUSHION, "suggest_skip": [], "deadline": None}
    if not due:
        res["status"] = "nothing_due"
        return res
    if expected >= due_total + CUSHION:
        res["status"] = "ok"
        return res
    if expected >= due_total:
        res["status"] = "tight"
        res["shortfall"] = 0
    else:
        res["status"] = "short"
        res["shortfall"] = due_total - expected
    gap = max(due_total - expected, 0) if res["status"] == "short" else due_total + CUSHION - expected
    allowed = [s for s in due if not any(l == "error" for l, _ in book.validate({"kind": "skip", "fid": s[0], "value": None}))]
    single = sorted([s for s in allowed if s[2] >= gap], key=lambda s: s[2])
    pick = [single[0]] if single else []
    if not pick:
        tot = 0
        for s in sorted(allowed, key=lambda s: -s[2]):
            pick.append(s)
            tot += s[2]
            if tot >= gap:
                break
    res["suggest_skip"] = [{"fund_id": f, "name": n, "amount": a} for f, n, a in pick]
    dl = skip_deadline(book.today, due_date)
    res["deadline"] = dtext(dl) if dl else None
    return res


def summary(res):
    """Plain-language notification text for a check result."""
    pay = res["payments_before_debit"]
    pay_txt = (" after " + ", ".join(f"{p['what']} ({inr(p['amount'])}, {p['date']})" for p in pay)) if pay else ""
    if res["status"] == "nothing_due":
        return f"No SIPs are due on {res['debit_date']}."
    if res["status"] == "ok":
        return (f"✅ Balance check for {res['debit_date']}: your bank has {inr(res['balance'])}; about {inr(res['expected_on_debit_date'])} "
                f"is expected on the debit date{pay_txt}. That covers the {inr(res['due_total'])} of SIPs due. Nothing to do.")
    names = " + ".join(f"{s['name']} ({inr(s['amount'])})" for s in res["suggest_skip"])
    head = ("⚠️ Your SIP debit may fail" if res["status"] == "short" else "⚠️ Your balance will be tight")
    gap = (f"short by {inr(res['shortfall'])}" if res["status"] == "short"
           else f"leaving less than the {inr(CUSHION)} cushion for other auto-debits")
    skip_txt = (f" To avoid a failed debit, I can skip **{names}** this month (no bounce fee)." if names
                else " None of these SIPs can be skipped now under Groww's rules.")
    dl = f" If you don't reply by {res['deadline']}, nothing is skipped and the debit goes ahead." if res["deadline"] else ""
    return (f"{head} on {res['debit_date']}. Your bank has {inr(res['balance'])}; about {inr(res['expected_on_debit_date'])} is expected "
            f"on the debit date{pay_txt}, but {inr(res['due_total'])} of SIPs is due, {gap}.{skip_txt} I won't skip anything without "
            f"your OK.{dl}")

"""SIP actions the assistant can take, with validation, explicit confirmation, receipts and undo.

Every action goes: propose -> validate (shown to the user) -> user confirms -> re-validate -> execute -> receipt (+ undo).
Rules (Groww help / SEBI): edits within 2 working days of a debit apply from the next instalment; one skip at a time per SIP;
3 skipped or missed instalments in a row cancel the SIP; SIP dates are 1-28. Prototype assumptions: ₹500 minimum SIP,
mock autopay limit. Nothing here touches a real account.
"""
import copy, re
from datetime import timedelta

MIN_SIP = 500           # prototype assumption; real minimum is on each fund page
MANDATE_LIMIT = 15000   # mock Groww Autopay limit covering all SIPs
LOCK_WORKING_DAYS = 2


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


def ordinal(d):
    return f"{d}{'th' if 11 <= d % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')}"


def dtext(d):
    return f"{d.day} {d.strftime('%b')}"


def next_on(day, after, inclusive=False):
    d = after if inclusive else after + timedelta(days=1)
    while d.day != day:
        d += timedelta(days=1)
    return d


def working_days_until(today, d):
    """Weekdays after today up to and including d (bank holidays ignored in this prototype)."""
    n, cur = 0, today
    while cur < d:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


class SipBook:
    def __init__(self, funds, today):
        self.today = today
        self.sips = {f["id"]: dict(name=f["short"], amount=f["sip"], day=f["day"], skips=set(),
                                   history=list(f.get("history", ["paid", "paid", "paid"]))) for f in funds}
        self.log = []  # [{"id", "text", "before"}]

    # ---------- queries ----------
    def next_debit(self, fid):
        """Next instalment date that is not skipped."""
        s = self.sips[fid]
        d = next_on(s["day"], self.today)
        while d in s["skips"]:
            d = next_on(s["day"], d)
        return d

    def upcoming(self, fid):
        return next_on(self.sips[fid]["day"], self.today)

    def due_on(self, d):
        return [(fid, s["name"], s["amount"]) for fid, s in self.sips.items()
                if self.upcoming(fid) == d and d not in s["skips"]]

    def total(self):
        return sum(s["amount"] for s in self.sips.values())

    def find(self, text):
        t = text.lower()
        keys = {"motilal": r"motilal|midcap|mid cap", "icici": r"icici|commodit", "quant": r"quant|small ?cap",
                "ppfas": r"parag|ppfas|flexi"}
        return [fid for fid, pat in keys.items() if fid in self.sips and re.search(pat, t)]

    # ---------- validation ----------
    def validate(self, a):
        """Returns list of (level, text): level in ok / warn / error."""
        s = self.sips[a["fid"]]
        out = []
        due = self.upcoming(a["fid"])
        wd = working_days_until(self.today, due)
        in_time = wd > LOCK_WORKING_DAYS
        if a["kind"] == "skip":
            if due in s["skips"]:
                out.append(("error", f"The {dtext(due)} instalment is already skipped"))
            elif any(d > self.today for d in s["skips"]):
                out.append(("error", "Another skip is already pending for this SIP (one skip at a time)"))
            else:
                out.append(("ok", "No other skip pending for this SIP"))
            out.append(("ok", f"Requested {wd} working days before the {dtext(due)} debit (needs more than {LOCK_WORKING_DAYS})")
                       if in_time else
                       ("error", f"The {dtext(due)} debit is only {wd} working day(s) away, too late to skip it"))
            recent = s["history"][-2:]
            streak = 0
            for h in reversed(recent):
                if h in ("skipped", "missed"):
                    streak += 1
                else:
                    break
            if streak >= 2:
                out.append(("error", "This would be the 3rd skipped or missed instalment in a row, which cancels the SIP"))
            elif streak == 1:
                out.append(("warn", f"Last month's instalment was {recent[-1]}: one more skip or failed debit in a row after this "
                                    "would cancel the SIP"))
            else:
                out.append(("ok", "Won't lead to 3 skips or misses in a row"))
        elif a["kind"] == "date":
            nd = a["value"]
            if not isinstance(nd, int) or not 1 <= nd <= 28:
                out.append(("error", "SIP dates can be from the 1st to the 28th"))
                return out
            if nd == s["day"]:
                out.append(("error", f"The SIP is already on the {ordinal(nd)}"))
                return out
            out.append(("ok", f"{ordinal(nd)} is a valid SIP date"))
            first_new = next_on(nd, self.today)
            if working_days_until(self.today, first_new) <= LOCK_WORKING_DAYS:
                out.append(("warn", f"{dtext(first_new)} is too close for the first debit on the new date; it starts from "
                                    f"{dtext(next_on(nd, first_new))}"))
            if in_time:
                out.append(("ok", f"Made {wd} working days before the {dtext(due)} debit, so it applies from this month"))
            else:
                out.append(("warn", f"The {dtext(due)} debit is too close to change; the new date applies from the next month"))
        elif a["kind"] == "amount":
            na = a["value"]
            if not isinstance(na, int) or na <= 0:
                out.append(("error", "Enter a whole rupee amount"))
                return out
            if na == s["amount"]:
                out.append(("error", f"The SIP is already {inr(na)}"))
                return out
            out.append(("ok", f"At least the {inr(MIN_SIP)} minimum") if na >= MIN_SIP else
                       ("error", f"Below the {inr(MIN_SIP)} minimum SIP amount"))
            new_total = self.total() - s["amount"] + na
            if na > s["amount"]:
                out.append(("ok", f"All SIPs together ({inr(new_total)}) stay within your {inr(MANDATE_LIMIT)} autopay limit")
                           if new_total <= MANDATE_LIMIT else
                           ("error", f"All SIPs together ({inr(new_total)}) would exceed your {inr(MANDATE_LIMIT)} autopay limit; "
                                     "the debit would fail. Raise the autopay limit first"))
            out.append(("ok", f"Made {wd} working days before the {dtext(due)} debit, so it applies from this month") if in_time else
                       ("warn", f"The {dtext(due)} debit is too close to change; the new amount applies from the next month"))
        return out

    def describe(self, a):
        s = self.sips[a["fid"]]
        due = self.upcoming(a["fid"])
        if a["kind"] == "skip":
            return f"Skip **{s['name']}**'s {inr(s['amount'])} instalment on {dtext(due)}"
        if a["kind"] == "date":
            return f"Move **{s['name']}** from the {ordinal(s['day'])} to the {ordinal(a['value'])} of every month"
        return f"Change **{s['name']}** from {inr(s['amount'])} to {inr(a['value'])} a month"

    # ---------- execution ----------
    def execute(self, actions):
        """Re-validates each action at confirm time; returns (done_texts, blocked_texts)."""
        done, blocked = [], []
        for a in actions:
            checks = self.validate(a)
            if any(l == "error" for l, _ in checks):
                blocked.append(self.describe(a) + ": " + next(t for l, t in checks if l == "error"))
                continue
            before = copy.deepcopy(self.sips[a["fid"]])
            s = self.sips[a["fid"]]
            due = self.upcoming(a["fid"])
            in_time = working_days_until(self.today, due) > LOCK_WORKING_DAYS
            if a["kind"] == "skip":
                s["skips"].add(due)
                text = f"Skipped {s['name']}'s {dtext(due)} instalment. Next debit: {dtext(self.next_debit(a['fid']))}, {inr(s['amount'])}"
            elif a["kind"] == "date":
                old = s["day"]
                s["day"] = a["value"]
                eff = self.upcoming(a["fid"]) if in_time else next_on(a["value"], due)
                if working_days_until(self.today, eff) <= LOCK_WORKING_DAYS:
                    eff = next_on(a["value"], eff)
                text = f"Moved {s['name']} from the {ordinal(old)} to the {ordinal(a['value'])}. Next debit: {dtext(eff)}"
                if not in_time:
                    text += f" (the {dtext(due)} debit still happens on the old date)"
            else:
                old = s["amount"]
                s["amount"] = a["value"]
                text = f"Changed {s['name']} from {inr(old)} to {inr(a['value'])} a month, from the " + \
                       (f"{dtext(due)} instalment" if in_time else "next month's instalment")
            self.log.append({"id": len(self.log) + 1, "fid": a["fid"], "text": text, "before": before, "undone": False})
            done.append(text)
        return done, blocked

    def undo(self, entry_id=None):
        live = [e for e in self.log if not e["undone"]]
        if not live:
            return None
        e = next((x for x in live if x["id"] == entry_id), live[-1]) if entry_id else live[-1]
        self.sips[e["fid"]] = copy.deepcopy(e["before"])
        e["undone"] = True
        return e["text"]


# ---------- intent parsing (deterministic; the confirmation step is the safety net) ----------
KIND = [("skip", re.compile(r"\bskip\b", re.I)),
        ("date", re.compile(r"\b(date|move|shift|postpone|push|reschedule)\b", re.I)),
        ("amount", re.compile(r"\b(amount|reduce|lower|decrease|increase|raise|cut)\b", re.I))]


def parse_intent(text, book):
    t = text.lower()
    kind = next((k for k, p in KIND if p.search(t)), None)
    if not kind:
        return None
    fids = book.find(t)
    if kind == "skip" and re.search(r"\ball\b|\bboth\b|\bevery", t):
        fids = ["*"]
    value = None
    if kind == "date":
        m = re.search(r"\b(?:to|on|the)\s+(\d{1,2})(?:st|nd|rd|th)?\b", t) or re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", t)
        value = int(m.group(1)) if m else None
    elif kind == "amount":
        m = re.search(r"(?:₹|rs\.?\s*)?(\d[\d,]{2,})", t)
        value = int(m.group(1).replace(",", "")) if m else None
    return {"kind": kind, "fids": fids, "value": value}

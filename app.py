"""Redemption assistant prototype (Groww case study, Part 5).
Flow: Dashboard -> fund -> Investment details -> Redeem -> "consult AI?" pop-up -> Yes: AI consultation / No: redeem screen.
Run: streamlit run app.py"""
import os
import re
from datetime import date, timedelta
import streamlit as st
from bot import Bot, norm, SYSTEM_SIP
from sip_flows import Planner, CheckIn, EXTRACT_SYSTEM, ordinal
from sip_actions import SipBook, parse_intent, dtext

st.set_page_config(page_title="Redemption Assistant", page_icon="✨", layout="centered", initial_sidebar_state="collapsed")

# ---------------- mock portfolio (case-study data) ----------------
FUNDS = [
    dict(id="motilal", name="Motilal Oswal Midcap Fund Direct Growth", short="Motilal Oswal Midcap", cat="Mid Cap", cur=52129, inv=46998,
         d1=167.02, folio="91432867 / 0", sip=2611, day=5, history=["paid", "paid", "skipped"]),
    dict(id="icici", name="ICICI Prudential Commodities Fund Direct Growth", short="ICICI Pru Commodities", cat="Thematic", cur=48310,
         inv=38500, d1=-72.40, folio="58210934 / 12", sip=2500, day=10),
    dict(id="quant", name="Quant Small Cap Fund Direct Plan Growth", short="Quant Small Cap", cat="Small Cap", cur=61245, inv=42000,
         d1=292.60, folio="77120458 / 3", sip=2000, day=5),
    dict(id="ppfas", name="Parag Parikh Flexi Cap Fund Direct Growth", short="Parag Parikh Flexi Cap", cat="Flexi Cap", cur=53036,
         inv=35094, d1=111.30, folio="40917765 / 1", sip=3000, day=15),
]
EXISTING_SIPS = sum(f["sip"] for f in FUNDS)


def next_on(day, after):
    d = after + timedelta(days=1)
    while d.day != day:
        d += timedelta(days=1)
    return d


# Demo clock: the check-in normally appears 7 days before a SIP date, so the prototype pretends today is that day.
CHECK_DAY = 5
DUE_DATE = next_on(CHECK_DAY, date.today())
DEMO_TODAY = DUE_DATE - timedelta(days=7)
DUE_TEXT = f"{DUE_DATE.day} {DUE_DATE.strftime('%b')}"
BY_ID = {f["id"]: f for f in FUNDS}
AI_FUND = "motilal"  # the reviewed answers and their numbers are written for this holding


def inr(x, paise=False):
    neg, x = x < 0, abs(x)
    s = f"{x:,.2f}" if paise else f"{round(x):,}"
    whole, _, frac = s.partition(".")
    digits = whole.replace(",", "")
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        digits = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "₹" + digits + ("." + frac if frac else "")


def secret(name, default=None):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


@st.cache_resource
def get_bot(key, model):
    return Bot(api_key=key, model=model)


@st.cache_resource
def get_sip_bot(key, model):
    return Bot(api_key=key, model=model, resp_file="sip_responses.csv", kb_file="sip_kb.csv", system=SYSTEM_SIP,
               context="SIP assistant.", min_score=2.0)


bot = get_bot(secret("MISTRAL_API_KEY"), secret("MISTRAL_MODEL", "ministral-14b-2512"))
sip_bot = get_sip_bot(secret("MISTRAL_API_KEY"), secret("MISTRAL_MODEL", "ministral-14b-2512"))

st.markdown("""
<style>
:root { --g: #00b386; --g-soft: #e6f7f2; --line: #e3e6ea; --muted: #6b7280; --ink: #111827; }
.block-container { max-width: 480px; padding-top: 1rem; padding-bottom: 6rem; }
.logo { width: 34px; height: 34px; border-radius: 50%; background: linear-gradient(160deg, #5367ff 50%, #00d09c 50%); display:inline-block; vertical-align: middle; }
.topbar { display:flex; align-items:center; gap:10px; font-size:1.25rem; font-weight:600; margin-bottom: 6px; }
.card { border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; margin: 6px 0 14px; }
.grid { display:grid; grid-template-columns: 1fr 1fr; row-gap: 12px; }
.lbl { color: var(--muted); font-size: .85rem; }
.val { font-weight: 600; font-size: 1.05rem; color: var(--ink); }
.r { text-align: right; }
.up { color: var(--g); font-weight: 600; }
.down { color: #e5484d; font-weight: 600; }
.sep { border-top: 1px solid var(--line); margin: 12px -16px 10px; }
.meta { color: var(--muted); margin-top: -8px; margin-bottom: 8px; }
.ai-head { display:flex; align-items:center; gap:8px; margin: 4px 0 6px; font-weight: 600; }
.tag { background: var(--g-soft); color: var(--g); font-size: .72rem; padding: 2px 8px; border-radius: 6px; font-weight: 600; }
.badge, .disc { font-size: .75rem; color: var(--muted); }
.disc { text-align:center; margin-top: 4px; }
.row { display:flex; justify-content:space-between; padding: 10px 0; border-bottom: 1px solid var(--line); }
div[data-testid="stButton"] button { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

S = st.session_state
S.setdefault("screen", "dashboard")
S.setdefault("fund", None)
S.setdefault("book", SipBook(FUNDS, DEMO_TODAY))


def due_sips():
    return S.book.due_on(DUE_DATE)


def go(screen, **kw):
    S.screen = screen
    for k, v in kw.items():
        S[k] = v


def topbar():
    c1, c2 = st.columns([5, 1])
    c1.markdown("<div class='topbar'><span class='logo'></span> Mutual Funds</div>", unsafe_allow_html=True)
    c2.button("👤", key=f"profile-{S.screen}", on_click=go, args=("profile",), help="Profile", type="tertiary")


def back(label, to):
    c1, c2 = st.columns([1, 9], vertical_alignment="center")
    c1.button("←", key=f"back-{S.screen}", on_click=go, args=(to,), type="tertiary")
    c2.markdown(f"#### {label}")


def ret_html(gain, base):
    cls = "up" if gain >= 0 else "down"
    sign = "+" if gain >= 0 else "-"
    return f"<span class='{cls}'>{sign} {inr(abs(gain), paise=isinstance(gain, float))} ({abs(gain) / base * 100:.2f}%)</span>"


# ---------------- screens ----------------
def tabs():
    names = {"explore": "Explore", "dashboard": "Dashboard", "sips": "SIPs"}
    choice = st.segmented_control("Section", ["Explore", "Dashboard", "SIPs", "Watchlist"], default=names.get(S.screen, "Dashboard"),
                                  label_visibility="collapsed", key=f"tabs-{S.screen}")
    target = {v: k for k, v in names.items()}.get(choice)
    if target and target != S.screen:
        go(target); st.rerun()
    if choice == "Watchlist":
        st.info("Watchlist isn't part of this prototype.")


def checkin_banner():
    if S.get("checked_in"):
        return
    with st.container(border=True):
        due = due_sips()
        if not due:
            return
        st.markdown(f"🔔 **SIP check-in:** {inr(sum(a for _, _, a in due))} of SIPs will be debited on **{DUE_TEXT}**. "
                    "A 1-minute check can help avoid a failed debit.")
        st.button("Start check-in", key=f"checkin-{S.screen}", on_click=start_checkin, type="primary")
        st.caption(f"Prototype: this card appears 7 days before a SIP date. Demo date: {DEMO_TODAY.day} {DEMO_TODAY.strftime('%b %Y')}.")


def start_checkin():
    S.checkin = CheckIn(due_sips() or [(f, S.book.sips[f]["name"], S.book.sips[f]["amount"]) for f in S.book.sips][:1], DUE_TEXT)
    S.ck_msgs = S.checkin.start()
    S.proposal, S.pending = None, None
    go("checkin")


def start_manage():
    S.checkin = CheckIn(due_sips(), DUE_TEXT)
    S.checkin.step = "done"
    S.ck_msgs = [sip_msg("Hi! I can **skip an instalment, move a SIP date or change an amount** for you. I'll check Groww's rules "
                         "and ask you to confirm before changing anything. What would you like to do?",
                         ["Skip an instalment", "Change SIP date", "Change SIP amount"])]
    S.proposal, S.pending = None, None
    go("checkin")


def sips():
    topbar(); tabs(); checkin_banner()
    b = S.book
    st.markdown(f"### Active SIPs ({len(b.sips)})")
    for fid, x in b.sips.items():
        up = b.upcoming(fid)
        status = f"⏭️ {dtext(up)} skipped · next {dtext(b.next_debit(fid))}" if up in x["skips"] else f"Next: {dtext(up)}"
        st.markdown(f"<div class='card'><b>{BY_ID[fid]['name']}</b><div style='display:flex;justify-content:space-between;margin-top:6px'>"
                    f"<span class='lbl'>{inr(x['amount'])} monthly · {ordinal(x['day'])}</span><span class='lbl'>{status}</span></div></div>",
                    unsafe_allow_html=True)
    st.markdown(f"<div class='disc'>Total {inr(b.total())} a month · Autopay limit ₹15,000</div>", unsafe_allow_html=True)
    st.button("✨ Ask Groww AI to skip or change a SIP", on_click=start_manage, use_container_width=True)
    if b.log:
        st.markdown("#### Changes made by Groww AI")
        for e in reversed(b.log):
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            c1.markdown(("~~" + e["text"] + "~~ _(undone)_") if e["undone"] else e["text"])
            if not e["undone"]:
                c2.button("Undo", key=f"undo-{e['id']}", on_click=undo_entry, args=(e["id"],))


def undo_entry(eid):
    S.book.undo(eid)


def dashboard():
    topbar(); tabs(); checkin_banner()
    cur = sum(f["cur"] for f in FUNDS); inv = sum(f["inv"] for f in FUNDS); d1 = sum(f["d1"] for f in FUNDS)
    st.markdown(f"### Investments ({len(FUNDS)})")
    st.markdown(f"""<div class="card"><div class="grid">
<div><div class="lbl">Current</div><div class="val">{inr(cur)}</div></div>
<div class="r"><div class="lbl">Total Returns</div>{ret_html(cur - inv, inv)}</div>
<div><div class="lbl">Invested</div><div class="val">{inr(inv)}</div></div>
<div class="r"><div class="lbl">1D Returns</div>{ret_html(round(d1, 2), cur - d1)}</div></div>
<div class="sep"></div><span class="lbl">XIRR</span> <b>37.67%</b></div>""", unsafe_allow_html=True)
    st.caption("Tap a fund to see details")
    for f in FUNDS:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1.3], vertical_alignment="center")
            c1.button(f["name"], key=f"fund-{f['id']}", on_click=go, args=("details",), kwargs={"fund": f["id"]}, type="tertiary")
            c1.markdown("<span class='lbl'>SIP</span>", unsafe_allow_html=True)
            c2.markdown(f"<div class='r'><span class='up'>{inr(f['cur'])}</span><br><span class='lbl'>({inr(f['inv'])[1:]})</span></div>",
                        unsafe_allow_html=True)


def explore():
    topbar(); tabs()
    st.markdown("### Popular Funds")
    for f in FUNDS[:2]:
        st.markdown(f"<div class='card'><b>{f['name'].replace(' Direct Growth', '')}</b><br><span class='lbl'>Equity {f['cat']}</span></div>",
                    unsafe_allow_html=True)
    st.markdown("### Collections")
    cols = st.columns(3)
    for i, c in enumerate(["High return", "SIP with ₹500", "Tax Saving", "Large Cap", "Mid Cap", "Small Cap"]):
        cols[i % 3].markdown(f"<div class='card' style='text-align:center'>{c}</div>", unsafe_allow_html=True)
    st.button("Start a new SIP", type="primary", use_container_width=True, on_click=start_planner)


def start_planner():
    extractor = (lambda text: sip_bot._call(text, EXTRACT_SYSTEM)) if sip_bot.api_key else None
    S.planner = Planner(existing_sips=EXISTING_SIPS, extractor=extractor)
    S.pl_msgs = S.planner.start()
    S.sip_form = False
    S.sip_prefill = None
    go("new_sip")


def flow_send(text, flow_key, msgs_key):
    """One user turn in a guided SIP flow: flow answer -> RAG answer -> re-ask the pending question."""
    flow, msgs = S[flow_key], S[msgs_key]
    t = norm(text)
    if t == "contact support":
        go("profile"); return
    if t == "skip to sip form":
        S.sip_form = True
        msgs += [{"role": "user", "text": text}, sip_msg("Sure. The SIP form is below. You can come back to these questions anytime.")]
        return
    if t == "use this plan" and flow_key == "planner":
        S.sip_form = True
        S.sip_prefill = (flow.sip, flow.result["day"])
        msgs += [{"role": "user", "text": text},
                 sip_msg(f"Done. I've filled in {inr(flow.sip)} on the {ordinal(flow.result['day'])} below. Pick a fund and confirm.")]
        return
    if flow_key == "checkin":
        out = agent_turn(text)
        if out == "nav":
            return
        if out:
            msgs += [{"role": "user", "text": text}, out]
            return
    msgs.append({"role": "user", "text": text})
    with st.spinner("Thinking…"):
        out, answered = flow.handle(text)
        if not answered:
            r = sip_bot.reply(text, None, msgs[:-1], context=flow.context())
            out = [{"role": "assistant", **r}]
            again = flow.ask()
            if again:
                again["text"] = "Coming back to your plan: " + again["text"] if flow_key == "planner" else again["text"]
                out.append(again)
    msgs += out


def sip_msg(text, chips=()):
    return {"role": "assistant", "text": text, "chips": list(chips), "mode": "flow", "kb": [], "checks": []}


CHIP_INTENTS = {"change sip date": "date", "lower amount from next month": "amount", "change sip amount": "amount",
                "skip an instalment": "skip"}


def agent_msg(text, chips, mode):
    return {"role": "assistant", "text": text, "chips": list(chips), "mode": mode, "kb": [], "checks": []}


def agent_turn(text):
    """The assistant acting on the user's SIPs: propose -> validate -> confirm -> execute -> receipt/undo."""
    b, t = S.book, norm(text)
    if t == "go to my sips":
        go("sips"); return "nav"
    if t == "confirm" and S.get("proposal"):
        done, blocked = b.execute(S.proposal)
        S.proposal, S.pending, S.checked_in = None, None, True
        due = due_sips()
        lines = [f"- ✅ {d}" for d in done] + [f"- ❌ Not done: {x}" for x in blocked]
        tail = f"\n\nOn {DUE_TEXT}, {inr(sum(a for _, _, a in due))} will now be debited." if due else f"\n\nNothing is due on {DUE_TEXT} now."
        return agent_msg(("Done. Here's what changed in your SIPs (prototype account):\n" if done else "Nothing was changed:\n")
                         + "\n".join(lines) + tail, ["Undo", "Go to my SIPs"] if done else ["Go to my SIPs"], "agent_done")
    if t == "cancel" and (S.get("proposal") or S.get("pending")):
        S.proposal, S.pending = None, None
        return agent_msg("Okay, nothing has been changed.", ["Go to my SIPs"], "flow")
    if t == "undo":
        undone = b.undo()
        return agent_msg(f"Undone: ~~{undone}~~. Your SIP is back as it was." if undone else "There's nothing to undo.",
                         ["Go to my SIPs"], "agent_done")
    if t == "keep as is":
        S.checked_in = True
        return agent_msg("Okay, no changes. Your SIPs will be debited as scheduled.", ["Go to my SIPs"], "flow")
    if t == "i'll add money":
        S.checked_in = True
        return agent_msg(f"Sounds good. Add it before {DUE_TEXT} and your SIPs should go through as usual.", ["Go to my SIPs"], "flow")

    m = re.fullmatch(r"skip (.+) this month", t)
    if m:
        name = m.group(1)
        fids = ["*"] if name == "all" else [f for f, x in b.sips.items() if x["name"].lower() == name]
        intent = {"kind": "skip", "fids": fids, "value": None}
    elif t in CHIP_INTENTS:
        intent = {"kind": CHIP_INTENTS[t], "fids": [], "value": None}
    else:
        intent = parse_intent(text, b)
    pend = S.get("pending")
    if pend:  # answering "which SIP?" / "which date?" / "which amount?"
        fids = [f for f, x in b.sips.items() if x["name"].lower() == t] or b.find(text)
        val = None
        if pend["kind"] == "date":
            mm = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", t)
            val = int(mm.group(1)) if mm else None
        elif pend["kind"] == "amount":
            mm = re.search(r"(\d[\d,]{2,})", t)
            val = int(mm.group(1).replace(",", "")) if mm else None
        if intent and intent["kind"] != pend["kind"]:
            pass  # user switched to a different action
        elif fids or val is not None:
            intent = {"kind": pend["kind"], "fids": fids or pend["fids"], "value": val if val is not None else pend.get("value")}
        elif not intent:
            return None
    if not intent:
        return None
    S.pending = None

    due_ids = [f for f, _, _ in due_sips()]
    fids = due_ids if intent["fids"] == ["*"] else intent["fids"]
    if not fids:
        cands = due_ids if intent["kind"] == "skip" and due_ids else list(b.sips)
        if len(cands) == 1:
            fids = cands
        else:
            S.pending = {"kind": intent["kind"], "fids": [], "value": intent["value"]}
            verb = {"skip": "skip", "date": "move", "amount": "change"}[intent["kind"]]
            return agent_msg(f"Which SIP would you like to {verb}?", [b.sips[f]["name"] for f in cands] + ["Cancel"], "flow")
    if intent["kind"] in ("date", "amount") and intent["value"] is None:
        S.pending = {"kind": intent["kind"], "fids": fids, "value": None}
        x = b.sips[fids[0]]
        if intent["kind"] == "date":
            opts = [d for d in (8, 10, 12, 15) if d != x["day"]][:3]
            return agent_msg(f"**{x['name']}** is on the {ordinal(x['day'])}. Which date should it move to? (1st-28th; 2-3 days after "
                             "your salary arrives is safest.)", [ordinal(d) for d in opts] + ["Cancel"], "flow")
        opts = sorted({max(500, int(x["amount"] * p // 100 * 100)) for p in (0.75, 0.5)} - {x["amount"]}, reverse=True)
        return agent_msg(f"**{x['name']}** is {inr(x['amount'])} a month. What should the new amount be?",
                         [inr(o) for o in opts] + ["Cancel"], "flow")

    actions = [{"kind": intent["kind"], "fid": f, "value": intent["value"]} for f in fids]
    blocks, any_ok = [], False
    for a in actions:
        checks = b.validate(a)
        icon = {"ok": "✅", "warn": "⚠️", "error": "❌"}
        ok = not any(l == "error" for l, _ in checks)
        any_ok |= ok
        blocks.append(f"{b.describe(a)}\n" + "\n".join(f"- {icon[l]} {txt}" for l, txt in checks))
    if any_ok:
        S.proposal = actions
        tail = "\n\nShall I go ahead? Nothing changes until you confirm." + \
               ("" if all(not any(l == "error" for l, _ in b.validate(a)) for a in actions) else " Items marked ❌ will be left as they are.")
        chips = ["Confirm", "Cancel"]
    else:
        S.proposal = None
        tail = "\n\nI can't do this one. You could try a different option instead."
        chips = [c for c in ("Change SIP amount", "Change SIP date", "I'll add money") if CHIP_INTENTS.get(norm(c)) != intent["kind"]] + ["Keep as is"]
    return agent_msg("Here's what I'll do, after checking Groww's rules:\n\n" + "\n\n".join(blocks) + tail, chips, "agent_proposal")


def render_msgs(msgs, kb_lookup):
    for i, m in enumerate(msgs):
        with st.chat_message(m["role"], avatar="✨" if m["role"] == "assistant" else "🙂"):
            st.markdown(re.sub(r"(?m)^(?!- )(.+)\n- ", r"\1\n\n- ", m["text"]))
            if m["role"] == "assistant" and i > 0 and m.get("mode") in BADGE:
                st.markdown(f"<span class='badge'>{BADGE.get(m['mode'], '')}</span>", unsafe_allow_html=True)
                if m.get("checks") or m.get("kb"):
                    with st.expander("Quality checks & sources"):
                        for name, ok, detail in m.get("checks", []):
                            st.markdown(f"{'✅' if ok else '❌'} {name} <span class='badge'>· {detail}</span>", unsafe_allow_html=True)
                        for k in m.get("kb", []):
                            kb = kb_lookup.get(k)
                            if kb:
                                src = f"[{kb['source_name']}]({kb['source_url']})" if kb["source_url"] else kb["source_name"]
                                st.markdown(f"**{k}** · {kb['topic']} — {src} _(data as of {kb['data_as_of']})_")


def render_chips(msgs, key, cb, args=()):
    last = next((m for m in reversed(msgs) if m["role"] == "assistant"), None)
    if msgs and msgs[-1]["role"] == "assistant" and last.get("chips"):
        cols = st.columns(2)
        for j, c in enumerate(last["chips"]):
            cols[j % 2].button(c, key=f"{key}-{len(msgs)}-{j}", on_click=cb, args=(c,) + args, use_container_width=True)


def new_sip():
    topbar(); back("Start a new SIP", "explore")
    if "planner" not in S:
        start_planner()
    st.markdown("<div class='ai-head'>✨ Groww AI <span class='tag'>SIP PLANNER</span></div>", unsafe_allow_html=True)
    if q := st.chat_input("Answer, or ask anything about SIPs…"):
        flow_send(q.strip()[:500], "planner", "pl_msgs")
        if S.screen != "new_sip":
            st.rerun()
    render_msgs(S.pl_msgs, sip_bot.kb_by_id)
    render_chips(S.pl_msgs, "pl", flow_send, ("planner", "pl_msgs"))
    if not S.get("sip_form"):
        st.button("Skip to SIP form", key="skip-form", on_click=flow_send, args=("Skip to SIP form", "planner", "pl_msgs"), type="tertiary")
        return
    st.markdown("#### SIP details")
    amt0, day0 = S.get("sip_prefill") or (2000, 5)
    days = list(range(1, 29))
    fund = st.selectbox("Fund", [f["name"] for f in FUNDS])
    amt = st.number_input("Monthly amount (₹)", min_value=500, value=int(max(amt0, 500)), step=500)
    day = st.selectbox("SIP date (every month)", days, index=days.index(day0) if day0 in days else 4, format_func=ordinal)
    if st.button(f"Start SIP of {inr(amt)}/month", type="primary", use_container_width=True):
        st.success(f"Prototype: no real SIP is created. In the app, this would start a {inr(amt)} monthly SIP "
                   f"in {fund} on the {ordinal(day)} of every month.")


def checkin():
    topbar(); back("SIP check-in", "sips")
    if "checkin" not in S:
        start_checkin()
    st.markdown("<div class='ai-head'>✨ Groww AI <span class='tag'>SIP CHECK-IN</span></div>", unsafe_allow_html=True)
    if q := st.chat_input("Answer, or ask anything about your SIP…"):
        flow_send(q.strip()[:500], "checkin", "ck_msgs")
        if S.screen != "checkin":
            st.rerun()
    render_msgs(S.ck_msgs, sip_bot.kb_by_id)
    render_chips(S.ck_msgs, "ck", flow_send, ("checkin", "ck_msgs"))
    st.markdown("<div class='disc'>Information to help your SIP go through, not investment advice. Any change is your choice.</div>",
                unsafe_allow_html=True)


def choose(screen):
    if screen == "chat":
        S.pop("msgs", None)
        S.path = None
    go(screen, chose=True)


@st.dialog(" ")
def consult_dialog():
    st.markdown("<h4 style='text-align:center'>Before redeeming would you like to consult to AI?</h4>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.button("Yes", type="primary", use_container_width=True, on_click=choose, args=("chat",))
    c2.button("No", use_container_width=True, on_click=choose, args=("redeem",))
    if S.get("chose"):  # callbacks ran inside the dialog's own rerun: refresh the whole page to leave it
        S.chose = False
        st.rerun()


def details():
    topbar(); back("Investment details", "dashboard")
    f = BY_ID[S.fund]
    st.markdown(f"### {f['name']}")
    st.markdown(f"<div class='meta'>Equity • {f['cat']} • Very High Risk</div>", unsafe_allow_html=True)
    st.markdown(f"""<div class="card"><div class="grid">
<div><div class="lbl">Current</div><div class="val">{inr(f['cur'])}</div></div>
<div class="r"><div class="lbl">Total Returns</div>{ret_html(f['cur'] - f['inv'], f['inv'])}</div>
<div><div class="lbl">Invested</div><div class="val">{inr(f['inv'])}</div></div>
<div class="r"><div class="lbl">1D Returns</div>{ret_html(f['d1'], f['cur'] - f['d1'])}</div></div>
<div class="sep"></div><div style="display:flex;justify-content:space-between"><span class="lbl">Investment type</span><b>SIP</b></div></div>""",
                unsafe_allow_html=True)
    st.markdown("#### Your investment")
    st.markdown(f"""<div class="row"><span class="lbl">Folio number</span><span>{f['folio']}</span></div>
<div class="row"><span>🗓️ Manage SIP</span><span class="lbl">Active ›</span></div>
<div class="row"><span>🧾 All transactions</span><span>›</span></div>
<div class="row"><span>📈 View fund details</span><span>›</span></div>""", unsafe_allow_html=True)
    st.markdown("<p class='disc' style='margin-top:18px'>Manage your investment in this fund</p>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button("Redeem", use_container_width=True):
        consult_dialog()
    if c2.button("Invest more", type="primary", use_container_width=True):
        st.toast("Invest more isn't part of this prototype.")


def redeem_screen():
    topbar(); back("Redeem", "details")
    f = BY_ID[S.fund]
    st.markdown(f"<div class='card'><b>{f['name']}</b><div style='display:flex;justify-content:space-between;margin-top:6px'>"
                f"<span class='lbl'>Current value <b style='color:#111'>{inr(f['cur'])}</b></span>{ret_html(f['cur'] - f['inv'], f['inv'])}</div></div>",
                unsafe_allow_html=True)
    mode = st.radio("How much?", ["All units", "Enter amount"], horizontal=True)
    amt = f["cur"] if mode == "All units" else st.number_input("Amount (₹)", 100, f["cur"], min(20000, f["cur"]), step=500)
    st.caption("Requests before 3 PM on a business day get today's NAV; money usually reaches your bank in 2-3 working days. "
               "Exit load and tax depend on when each SIP instalment was bought.")
    if st.button(f"Redeem {inr(amt)}", type="primary", use_container_width=True):
        st.success("Prototype: no real order is placed. In the app, this would submit your redemption.")
    if S.fund == AI_FUND:
        st.button("Not sure? Ask Groww AI first", on_click=lambda: (go("chat"), S.pop("msgs", None)), type="tertiary")


def profile():
    back("Profile", "dashboard")
    st.markdown("<div style='text-align:center;font-size:3rem'>👤</div><h3 style='text-align:center'>Demo User</h3>", unsafe_allow_html=True)
    for r in ["🧾 Orders", "👤 Account Details", "🏦 Banks & Autopay", "❤️ Refer", "🎧 Customer Support 24x7", "📊 Reports"]:
        st.markdown(f"<div class='row'><span>{r}</span><span>›</span></div>", unsafe_allow_html=True)
    st.caption("Prototype profile. Customer Support is where the assistant sends app issues it can't solve.")


# ---------------- AI consultation ----------------
NAV = {"confirm redemption": "redeem", "go to holdings": "dashboard", "contact support": "profile"}
BADGE = {
    "curated": "✅ Reviewed answer", "retrieved": "✅ Reviewed answer (closest match)", "ai": "✨ AI answer · passed all checks",
    "guardrail": "🛡️ Safety rule", "agent_proposal": "🛡️ Rules checked before acting · needs your confirmation",
    "agent_done": "✅ Change made (prototype account)", "fallback": "⚠️ Not sure: pointing you to an official source", "action": "↪ Prototype action",
}


def send(text):
    if norm(text) in NAV:
        go(NAV[norm(text)])
        return
    S.msgs.append({"role": "user", "text": text})
    with st.spinner("Thinking…"):
        r = bot.reply(text, S.path, [m for m in S.msgs[:-1]])
    if r.get("path"):
        S.path = r["path"]
    if r.get("id") == "R00":
        S.path = None
    S.msgs.append({"role": "assistant", **r})


def chat():
    topbar(); back("AI consultation", "details")
    f = BY_ID[S.fund]
    st.markdown(f"<div class='card'><b>{f['name']}</b><div style='display:flex;justify-content:space-between;margin-top:6px'>"
                f"<span class='lbl'>Current value <b style='color:#111'>{inr(f['cur'])}</b></span>"
                f"<span class='up'>+{(f['cur'] - f['inv']) / f['inv'] * 100:.2f}%</span></div></div>"
                "<div class='ai-head'>✨ Groww AI <span class='tag'>AI ASSISTANT</span></div>", unsafe_allow_html=True)
    if S.fund != AI_FUND:
        st.info("In this prototype, the AI consultation is set up for **Motilal Oswal Midcap Fund**: its answers use that holding's "
                "numbers. Open that fund from the Dashboard to try it.")
        st.button("Continue to redeem →", on_click=go, args=("redeem",), type="tertiary")
        return
    if "msgs" not in S:
        S.msgs = [{"role": "assistant", **bot.opener()}]
        S.path = None
    if q := st.chat_input("Ask about your redemption…"):
        send(q.strip()[:500])
        if S.screen != "chat":
            st.rerun()
    msgs = S.msgs
    for i, m in enumerate(msgs):
        with st.chat_message(m["role"], avatar="✨" if m["role"] == "assistant" else "🙂"):
            st.markdown(re.sub(r"(?m)^(?!- )(.+)\n- ", r"\1\n\n- ", m["text"]))
            if m["role"] == "assistant" and i > 0:
                st.markdown(f"<span class='badge'>{BADGE.get(m['mode'], '')}</span>", unsafe_allow_html=True)
                if m.get("checks") or m.get("kb"):
                    with st.expander("Quality checks & sources"):
                        for name, ok, detail in m.get("checks", []):
                            st.markdown(f"{'✅' if ok else '❌'} {name} <span class='badge'>· {detail}</span>", unsafe_allow_html=True)
                        for k in m.get("kb", []):
                            kb = bot.kb_by_id.get(k)
                            if kb:
                                src = f"[{kb['source_name']}]({kb['source_url']})" if kb["source_url"] else kb["source_name"]
                                st.markdown(f"**{k}** · {kb['topic']} — {src} _(data as of {kb['data_as_of']})_")
    last = msgs[-1]
    if last["role"] == "assistant" and last.get("chips"):
        if len(msgs) == 1:
            st.caption("Choose a reason, or type your own")
        cols = st.columns(2)
        for j, c in enumerate(last["chips"]):
            cols[j % 2].button(c, key=f"chip-{len(msgs)}-{j}", on_click=send, args=(c,), use_container_width=True)
    st.markdown("<div class='disc'>AI guidance is informational, not investment advice. You're in control of your investment decisions.</div>",
                unsafe_allow_html=True)
    st.button("Continue to redeem →", key="redeem-link", on_click=go, args=("redeem",), type="tertiary")


# ---------------- sidebar + router ----------------
with st.sidebar:
    st.subheader("About this prototype")
    st.write("Case-study prototype: an AI consultation offered when a user taps **Redeem**. It explains costs and alternatives "
             "(loan against mutual funds, partial redemption, staying invested) and always leaves the decision to the user.")
    st.caption("Not affiliated with Groww. Not investment advice. Portfolio data is a mock.")
    st.markdown("**AI mode:** " + ("on (Mistral)" if bot.api_key else "off: reviewed answers via keyword search"))
    st.markdown("""**SIP assistants**
- *Start a new SIP* (Explore): asks salary date, take-home pay, costs, spending, existing SIPs and emergency fund, then a calculator suggests an amount and a date 3 days after salary
- *SIP check-in* (Dashboard/SIPs card, 7 days before the SIP date): asks about salary timing, big expenses and expected balance, then suggests keeping, skipping, changing date or lowering the amount
- Typed questions in either flow are answered from a sourced SIP knowledge base with the same checks as below""")
    st.markdown("""**How each chat message is answered**
1. Button taps → a reviewed answer from the dataset
2. Typed text → safety rules (advice, predictions, prompt injection, "stop pushing me")
3. AI picks the closest reviewed answers, then writes a reply from them and their sourced facts
4. The reply must pass every check (sources cited, every number in the sources, no advice, no pressure), else the reviewed answer is shown
5. Nothing matches → "I'm not sure" plus an official source""")
    if st.button("Restart prototype", use_container_width=True):
        for k in list(S.keys()):
            del S[k]
        st.rerun()

{"dashboard": dashboard, "explore": explore, "details": details, "redeem": redeem_screen,
 "chat": chat, "profile": profile, "new_sip": new_sip, "sips": sips, "checkin": checkin}.get(S.screen, dashboard)()

"""Redemption assistant prototype (Groww case study, Part 5). Run: streamlit run app.py"""
import os
import streamlit as st
from bot import Bot, HOLDING

st.set_page_config(page_title="Redemption Assistant", page_icon="✨", layout="centered")


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


bot = get_bot(secret("MISTRAL_API_KEY"), secret("MISTRAL_MODEL", "ministral-14b-2512"))

st.markdown("""
<style>
:root { --g: #00b386; --g-soft: #e6f7f2; --line: #e3e6ea; --muted: #6b7280; }
.block-container { max-width: 520px; padding-top: 1.2rem; }
.fund { border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; margin: 4px 0 14px; }
.fund b { font-size: 1.02rem; }
.fund .row { display: flex; justify-content: space-between; color: var(--muted); margin-top: 6px; }
.fund .up { color: var(--g); font-weight: 600; }
.ai-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-weight: 600; }
.tag { background: var(--g-soft); color: var(--g); font-size: .72rem; padding: 2px 8px; border-radius: 6px; font-weight: 600; }
.badge { font-size: .75rem; color: var(--muted); }
div[data-testid="stButton"] button { border-radius: 10px; border: 1px solid var(--line); color: var(--g); }
div[data-testid="stButton"] button:hover { border-color: var(--g); color: var(--g); }
.disc { font-size: .78rem; color: var(--muted); text-align: center; margin-top: 4px; }
</style>
""", unsafe_allow_html=True)

if "msgs" not in st.session_state:
    st.session_state.msgs = [{"role": "assistant", **bot.opener()}]
    st.session_state.path = None


def send(text):
    s = st.session_state
    s.msgs.append({"role": "user", "text": text})
    with st.spinner("Thinking…"):
        r = bot.reply(text, s.path, [m for m in s.msgs[:-1]])
    if r.get("path"):
        s.path = r["path"]
    if r.get("id") == "R00":
        s.path = None
    s.msgs.append({"role": "assistant", **r})


BADGE = {
    "curated": "✅ Reviewed answer",
    "retrieved": "✅ Reviewed answer (closest match)",
    "ai": "✨ AI answer · passed all checks",
    "guardrail": "🛡️ Safety rule",
    "fallback": "⚠️ Not sure: pointing you to an official source",
    "action": "↪ Prototype action",
}

# ---------- sidebar ----------
with st.sidebar:
    st.subheader("About this prototype")
    st.write("A case-study prototype of an assistant shown when a user taps **Redeem** on a mutual fund. "
             "It explains costs and alternatives (loan against mutual funds, partial redemption, staying invested) "
             "and always leaves the decision to the user.")
    st.caption("Not affiliated with Groww. Not investment advice. Holding data is a mock.")
    st.markdown("**AI mode:** " + ("on (Mistral)" if bot.api_key else "off: reviewed answers via keyword search"))
    st.markdown("""**How each message is answered**
1. Button taps → a reviewed answer from the dataset
2. Typed text → safety rules (advice, predictions, prompt injection, "stop pushing me")
3. AI picks the closest reviewed answers, then writes a reply from them and their sourced facts
4. The reply must pass every check (sources cited, every number in the sources, no advice, no pressure), or the reviewed answer is shown instead
5. Nothing matches → "I'm not sure" plus an official source""")
    if st.button("Restart chat", use_container_width=True):
        for k in ("msgs", "path"):
            st.session_state.pop(k, None)
        st.rerun()

# ---------- header ----------
st.markdown("### ← AI consultation")
st.markdown(f"""<div class="fund"><b>{HOLDING['fund']}</b>
<div class="row"><span>Current value <b style="color:#111">{HOLDING['value']}</b></span><span class="up">{HOLDING['return']}</span></div></div>
<div class="ai-head">✨ Groww AI <span class="tag">AI ASSISTANT</span></div>""", unsafe_allow_html=True)

# ---------- conversation ----------
# handled before rendering so the new reply and its chips show in this run (the input itself is pinned to the bottom)
if q := st.chat_input("Ask about your redemption…"):
    send(q.strip()[:500])
msgs = st.session_state.msgs
for i, m in enumerate(msgs):
    with st.chat_message(m["role"], avatar="✨" if m["role"] == "assistant" else "🙂"):
        st.markdown(m["text"].replace("\n- ", "\n\n- "))
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

st.button("Continue to redeem →", key="redeem", on_click=send, args=("Continue to redeem",), type="tertiary")
st.markdown("<div class='disc'>AI guidance is informational, not investment advice. You're in control of your investment decisions.</div>",
            unsafe_allow_html=True)

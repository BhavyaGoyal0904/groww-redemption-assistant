# Redemption Assistant (case-study prototype)

A RAG chatbot shown when a user taps **Redeem** on a mutual fund. It explains costs and alternatives
(loan against mutual funds at 10.5% p.a., partial redemption, staying invested) and always leaves the decision to the user.

**Not investment advice. Not affiliated with Groww. Holding data is a mock.**

## How a message is answered
1. Button tap → reviewed answer from `data/redemption_bot_responses.csv`
2. Typed text → safety rules (advice requests, predictions, prompt injection, "stop pushing me")
3. AI (Mistral) picks the closest reviewed answers, then writes a reply from them and the sourced facts in `data/knowledge_base.csv`
4. The reply must pass every check (cites a retrieved source, every number appears in the sources, no advice, no pressure), otherwise the reviewed answer is shown
5. Nothing matches → "I'm not sure" plus an official source

## Run
```
pip install -r requirements.txt
streamlit run app.py          # add MISTRAL_API_KEY to .streamlit/secrets.toml for AI mode
```
Edit content in `build_dataset.py`, then `python build_dataset.py data` to regenerate the CSVs.

## SIP assistants (reduce SIP mandate failures)
- **Start a new SIP** (Explore): the bot asks salary date, take-home pay, fixed costs, day-to-day spending, existing SIPs and
  emergency fund. A calculator in `sip_flows.py` (not the AI) suggests an amount the budget can sustain and a date 3 days after
  salary, then pre-fills the SIP form. With an API key, one free-text message ("salary 60k on the 1st, rent 18k…") is parsed by the AI;
  every extracted number must appear in the message.
- **SIP check-in** (Dashboard/SIPs card, shown 7 days before the SIP date; the prototype uses a demo date): asks about salary
  timing, big expenses and expected balance, then suggests keeping, skipping an instalment, changing the date or lowering the amount.
  Groww applies edits only if made 2+ working days before the debit, so 7 days leaves time to act.
- Typed questions in either flow are answered from `data/sip_responses.csv` + `data/sip_kb.csv` (sources: SEBI uniform SIP
  cancellation rule, Groww help, bank bounce charges). Regenerate with `python build_sip_dataset.py data`.

## The assistant can act on SIPs (with validation)
In the SIP check-in (or "Ask Groww AI to skip or change a SIP" on the SIPs tab) the assistant can **skip an instalment,
move a SIP date or change the amount**, from a button or free text ("move my motilal sip to the 8th").
Every action: propose → validate (shown as ✅/⚠️/❌) → user taps Confirm → re-validated → executed → receipt with Undo.
Rules checked (`sip_actions.py`): requested more than 2 working days before the debit (Groww), one skip at a time per SIP,
no 3rd skipped/missed instalment in a row (cancels the SIP), dates 1st–28th, amount ≥ ₹500 (prototype minimum) and within the
autopay limit (mock ₹15,000). Changes apply to a mock account in the session; the SIPs tab lists them with Undo.

### AI agent (tool calling)
With `MISTRAL_API_KEY` set, free text in the SIP check-in / SIP chat goes to an AI agent (`agent.py`, Mistral tool calling) that
decides what to do and can call three tools: `list_sips` (read the user's SIPs), `search_knowledge` (RAG over the SIP knowledge base)
and `propose_change` (runs the rule checks and prepares a confirmation). **The model can't execute anything**: the change happens only when
the user taps Confirm (or types "yes, go ahead"), and it's re-validated at that moment. The agent's reply is checked before display:
every number must come from a tool result, no advice, no pressure, and no claim that a change was made. If a check fails, the
code-generated proposal (or a reviewed answer) is shown instead; if the API fails, the rule-based agent takes over.

### Agent on the Dashboard
The Dashboard has a Groww AI panel (chat input pinned at the bottom). It opens with what it notices (upcoming debit, a recently
skipped instalment, autopay headroom), can run the SIP check-in inline, answers questions, discusses holdings as facts
(`get_portfolio` tool, no advice), and proposes/executes SIP changes with the same validation → Confirm → receipt → Undo flow.

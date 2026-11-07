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

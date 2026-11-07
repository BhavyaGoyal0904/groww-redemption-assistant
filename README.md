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

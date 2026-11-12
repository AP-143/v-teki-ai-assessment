# V-TEKI AI Solution Engineer Assessment

Three working prototypes and answers to six critical-thinking scenarios.
All data is synthetic, everything runs locally, and every number comes from real runs.

## The three cases

| Case | What it does | Key result | Tests |
|---|---|---|---|
| [1. Fraud Risk Prediction](case1_fraud_risk/) | Ranks transactions by fraud risk for analyst review, with reasons | Catches 95% of fraud with 10 reviews a day (PR-AUC 0.98) | 23 |
| [2. Document Intelligence](case2_document_intelligence/) | Reads invoice PDFs into validated JSON; unsure results go to manual review | 95% field accuracy, 0 wrong results auto-accepted | 44 |
| [3. Knowledge Chatbot](case3_knowledge_chatbot/) | Answers employee questions from SOPs with sources, respecting roles | 15/15 correct answers, 0 restricted data leaked | 64 |

Answers to the six scenarios: [docs/critical_thinking.md](docs/critical_thinking.md).

## Requirements

- Python 3.14 (tested on 3.14.5, Windows 11)
- [Ollama](https://ollama.com) for the AI parts of Case 2 and 3:
  `ollama pull qwen3:4b-instruct` and `ollama pull bge-m3`.
  The tests do not need Ollama.

## Setup, run and test

Each case is separate. Go into its folder, then:

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

| Case | Run | Test |
|---|---|---|
| 1 | `$env:FRAUD_PSEUDONYM_KEY="local-demo-key-change-me"` (macOS/Linux: `export ...`)<br>`python -m fraud_risk.generate_data`<br>`python -m fraud_risk.train`<br>`python -m fraud_risk.predict` | `pytest` |
| 2 | `python -m invoice_extractor.generate_invoices`<br>`python -m invoice_extractor.extract data/invoices/invoice_002.pdf`<br>`python -m invoice_extractor.evaluate` | `pytest` |
| 3 | `python -m kb_chatbot.ingest`<br>`python -m kb_chatbot.ask --user budi "How many days of annual leave do I get?"`<br>`python -m kb_chatbot.evaluate` | `pytest` |

More detail (design, results, privacy, cost, limitations) is in each case's README.

## Repository layout

```
case1_fraud_risk/              Case 1 code, data, reports, tests
case2_document_intelligence/   Case 2 code, data, reports, tests
case3_knowledge_chatbot/       Case 3 code, data, reports, tests
docs/critical_thinking.md      Answers to the six scenarios
```

## AI tool use

I used **Claude Code** (Anthropic) as my AI coding assistant, with two add-ons:
- **Matt Pocock's skills** (`mattpocock-skills`), mainly the "grilling" skill: the AI asks me questions round
  by round until every design decision for a case is agreed, before any code is written.
- **Ponytail**: a plugin that pushes the AI to write the smallest code that fully solves the task.

The AI helped me to design each case, write the code, data, tests and documents, run the tests and
evaluations, and fix issues found by automated security reviews.

**My part:** I made the design decisions, checked the explanation and results of each step before moving on,
and confirmed the manual review in Case 3 (pre-filled by the AI). All tests and evaluations ran in my own
environment, and every number here comes from those runs. I am responsible for this work and can explain it.

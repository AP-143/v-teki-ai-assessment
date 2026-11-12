# Critical Thinking & Engineering Judgment

Answers to the six scenarios. Each one gives a short answer first, then the reasoning, then the evidence
that would change my decision. Where possible I point to what I measured in my own prototypes
(Case 1 = fraud, Case 2 = invoices, Case 3 = chatbot).

---

## Scenario 1 — High accuracy, low fraud detection

*A fraud model reports 98% accuracy but finds only 30% of confirmed fraud cases.*

**Short answer:** Not as the main fraud control. 98% accuracy says almost nothing when fraud is rare,
and missing 70% of fraud is a business problem.

### Would I deploy it?
- **No, not as it is.** If 2% of transactions are fraud, a model that always says "not fraud" already scores
  98% accuracy. In Case 1 that "always not fraud" baseline scored **98.8% accuracy and caught 0 of 84 fraud cases**.
- I would only use it **in shadow mode** (it scores, nobody acts on it) or as one extra signal, and only if it
  beats the current process at the same review capacity.

### Which metrics and error costs matter most? How would I validate them?
- **Recall** (how much fraud we catch) and **precision at review capacity** (of the cases analysts can check
  per day, how many are real fraud). Also **PR-AUC** to compare models without picking a threshold.
- **Error costs:** a missed fraud (false negative) costs the stolen amount and trust; a false alarm (false
  positive) costs analyst time and annoys a good customer. I would agree the rough cost of each with the client,
  then compare models by expected cost: `missed fraud × average loss + false alarms × review cost`.
- **Validation:** a **time-based split** (train on the past, test on later months), confirmed fraud labels only,
  and enough fraud cases in the test set to trust the numbers. Also check results per segment (channel, amount).

### What would I investigate or change first?
1. **The threshold.** Many models use 0.5 by default, which is wrong for rare events. Rank by risk and flag the
   top N the team can review (Case 1 used 10 per day).
2. **Labels.** Are they confirmed fraud, or "blocked accounts"? In Case 1, 28 blocked customers had no fraud and
   30 fraud victims were never blocked; mixing these up teaches the model the wrong thing.
3. **Leakage and split.** A random split or future data in features gives fake-good results.
4. **Class imbalance** (class weights, better features such as failed logins and transaction speed).

### Evidence that would change my decision
- The 30% it catches is the **high-loss** fraud (for example 80% of the money lost), and nothing better exists yet.
- At the real review capacity it beats the current rules on precision and recall in a shadow test.

---

## Scenario 2 — Unreliable data and a tight deadline

*Customer IDs do not match across tables; events contain duplicates and missing timestamps. Demo in two weeks.*

**Short answer:** Check the data first, shrink the MVP to the part that is reliable, and be honest with the client.

### My first three checks
1. **Join rate.** What % of transactions match a customer? Which ID formats exist, and can simple rules fix most
   of them? (In Case 1, normalizing formats like `c-12` and `CUST_12` fixed 4,418 rows.)
2. **Duplicates.** Exact copies (system retries) or different events? Do duplicates double-count fraud or amounts?
3. **Missing timestamps.** How many, in which tables and periods, and are they random or concentrated in
   important cases such as fraud? Without time we cannot build safe "past-only" features.

I would also confirm early **which labels exist** and who confirmed them.

### Train immediately or change the MVP scope?
- **Do not train on day one.** A model trained on broken joins learns noise and gives numbers we cannot defend.
- **Change the scope:** spend the first days on profiling and cleaning rules, then build a simple baseline
  (rules) and one model on the **reliable subset** (for example one product or the months with good data).
- Keep everything that does not need perfect data: the cleaning pipeline, the data-quality report, and a
  ranked review list instead of automatic decisions.

### What would I tell the client, and what can I safely demonstrate?
- Tell them early, with numbers: "X% of transactions cannot be linked to a customer yet; here is why and how we fix it."
- **Safe to demo:** the data-quality report, the cleaning steps, and a baseline ranking on the clean subset,
  clearly labelled as a prototype on limited data.
- **Not safe to promise:** accuracy on the full data, or production readiness.

### Evidence that would change my decision
- If simple mapping rules bring the join rate above ~95% and missing timestamps are random and rare, I would
  train on the full data within the two weeks.

---

## Scenario 3 — A chatbot gives confident but wrong answers

*Your RAG chatbot gives an incorrect policy answer and cites a document that does not support it.*

**Short answer:** First find out which step failed (search or answer writing), fix that step, and make the bot
refuse when the evidence is weak.

### How do I separate retrieval errors from generation errors?
- Look at the **retrieved sections** for that question (Case 3 logs their IDs for every question).
  - The right section was **not** in the top results → **retrieval error** (search, chunking, embeddings, access filter).
  - The right section **was** there but the answer is wrong → **generation error** (the model misread, mixed
    sections, or added facts).
  - The cited section does not support the answer → **grounding error**, which should be blocked automatically.
- Do this on a labelled question set with the **expected source section** for each question, not on one example.

### What tests and metrics would show improvement?
- **Recall@K** for retrieval, **answer correctness**, **citation accuracy**, and **faithfulness** (every claim is
  in the cited section), plus correct-refusal and wrong-refusal rates.
- Add every failing question to a **regression set** so it stays fixed.
- Automatic checks after the model: citations must be retrieved sections, and every number must appear in the
  cited text. In Case 3 these checks block invented numbers even when the model is manipulated.
- A small **manual review** for things machines judge badly (tone, partial answers). Case 3 found mixed-language
  answers this way.

### When should the assistant say it cannot answer?
- No section is similar enough to the question (Case 3 refuses below a score of 0.50, set on practice questions).
- The model says the answer is not in the sections, or its citation or numbers do not match the sources.
- The sources conflict, or the user is not allowed to see the relevant document (with the **same** message, so
  the refusal does not reveal that a restricted document exists).
- For policy questions, **a polite refusal is better than a confident guess.**

### Evidence that would change my decision
- If most failures are retrieval errors, I would focus on chunking and search (or add keyword search), not on the model.
- If refusals become too frequent for valid questions (for example typos), I would re-tune the refusal bar on a
  larger practice set.

---

## Scenario 4 — Privacy versus speed and cost

*The client wants confidential documents processed by a cheap external LLM, but no external data transfer has been approved.*

**Short answer:** No. I would not send the documents. Cheap is not a reason to break an approval, a contract or
the law (in Indonesia, the Personal Data Protection Law, UU PDP).

### Would I send the documents?
- **No.** Without approval we do not know where the data goes, how long it is kept, or whether it trains the
  vendor's model. One leak can cost far more than the money saved.
- My prototypes **refuse external endpoints by default** (`ALLOW_EXTERNAL_LLM` must be set on purpose after
  approval) and show exactly what would be sent with `--show-prompt`.

### Two safer alternatives

| | A. Local / self-hosted model | B. External LLM, but only after approval and with controls |
|---|---|---|
| How | Open model on our own GPU or server (Case 2 and 3 use a 4B model in Ollama) | Enterprise contract, no training on our data, no or short retention, approved region; send only redacted text |
| Privacy | Data never leaves | Data leaves, but minimized and under contract |
| Quality | Case 2: 95% field accuracy; may be weaker on hard documents | Usually higher on complex documents |
| Speed | ~4 s per document on a laptop GPU | Often faster, depends on the network |
| Cost | Hardware and maintenance; electricity ≈ IDR 0.16 per invoice in Case 2 | Per token, ≈ US$0.00014 per invoice at assumed small-model prices |
| Main risk | We maintain the model and hardware | Vendor and contract risk; redaction must not miss anything |

I would start with **A** and measure. If quality is not enough, prepare **B** with the client's approval.

### Approvals, controls and tests before launch
- **Approvals:** data owner and legal / data protection officer sign-off, a privacy impact assessment, a vendor
  security review, and a contract (data processing agreement) if we use an external vendor.
- **Controls:** redaction of fields we do not need, an allowlist of endpoints, secrets kept out of code, logs
  without document content, access control on uploads and outputs.
- **Tests:** a negative test that unapproved endpoints are refused, a test that the prompt contains no bank
  accounts, phones or emails (both exist in Case 2), accuracy on a labelled set, and a security review of the API.

### Evidence that would change my decision
- Written approval plus a contract with no retention and an approved region would make option B acceptable.
- If the documents contain no personal or confidential data after redaction, the risk is much lower.

---

## Scenario 5 — The proposed architecture costs too much

*Your design costs three times the client's budget.*

**Short answer:** Measure where the money actually goes, cut the biggest drivers first, and prove with the same
tests that the cheaper design still meets the requirements.

### Which cost drivers would I measure first?
1. **Volume:** documents or questions per day, and the peak.
2. **Model usage:** tokens per request and model size (prompt length often dominates).
3. **Always-on compute:** GPUs or servers running while idle.
4. **Human review rate:** every case sent to a person costs staff time. This is often the biggest cost
   (in Case 1 it is analyst time, not compute).
5. Storage and retention of data and logs.

### What would I simplify, and what trade-offs follow?

| Simplification | Saves | Trade-off |
|---|---|---|
| **Cascade:** cheap rules first, the model only for hard cases (Case 2: regex is 100% on known layouts, the LLM handles new ones) | Most model calls | More code paths; rules break on new formats |
| **Batch instead of real-time** (Case 1 scores once a day) | Always-on servers | Slower reaction |
| **Smaller model or shorter prompts** (fewer retrieved sections) | Compute and tokens | Possibly lower quality |
| **Refuse early without the model** (Case 3 handled 10 of 33 questions with a refusal and no model call) | Model calls | A few valid questions may be refused |
| **Scale to zero, no extra services** (Case 3 uses NumPy instead of a vector database) | Idle cost | Cold starts; not suited to very large data |

### How would I verify the cheaper design still meets requirements?
- Agree the **must-pass criteria first** (for example: 0 wrong auto-accepted invoices, 0 data leaks, accuracy
  within 2 points of the current design, latency under X seconds).
- Run the **same evaluation set** on both designs and compare. Run the cheaper one in shadow mode for a while
  and monitor cost per document and review rate.

### Evidence that would change my decision
- If the review rate rises so much that staff cost eats the savings, the "cheaper" design is not cheaper.
- If the client's real volume is much lower than assumed, the original design may fit the budget with smaller servers.

---

## Scenario 6 — Ownership under uncertainty

*Your team lead is unavailable for two days. You discover a wrong assumption the day before a client demo.*

**Short answer:** Confirm the problem with evidence, write it down, fix only what I can test safely, never hide it,
and inform the right people the same day.

### What would I verify and document first?
- **Is the assumption really wrong?** Check the data or the client document, and reproduce the problem.
- **What does it affect?** Which results, numbers, slides and demo steps change, and by how much.
- A **short note**: what I found, how, the impact, the options, and my recommendation, with the previous
  results kept for comparison.

### What would I change, stop, or safely demonstrate?
- **Change** only what I can fix and re-test before the demo, then re-run the evaluation. In Case 3 I found a
  prompt-injection weakness after the first run, fixed it, ran the evaluation again, and kept both results.
- **Stop** showing any number or feature that depends on the wrong assumption. No untested changes the night before.
- **Demonstrate** the parts that are not affected, and explain the issue openly as a known limitation with a plan.

### Who would I inform, when, and why?
- **My team lead, right away**, by message, even if they are away, so they are not surprised later.
- **Their backup or the project manager the same day**, because someone with authority must decide what to tell the client.
- **The client before or at the start of the demo**, agreed with the project manager: what changed, what is
  still reliable, and when the fix comes.
- **Why:** decisions about client communication belong to the people accountable for the project, and clients
  trust a team that reports problems early more than one that hides them.

### Evidence that would change my decision
- If the impact is tiny (for example a label on one slide), I would fix it and mention it in the note, not escalate.
- If the fix is large and risky, I would recommend moving the affected part of the demo rather than rushing it.

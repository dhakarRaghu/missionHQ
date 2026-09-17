# Course 2 — Applied AI systems at scale
slug: elite-applied-ai
order: 2
source: local
language: Python for labs, Go where it touches Mission HQ

## Why this course

He has shipped RAG, MCP tools, guardrails and an eval pipeline. This course
does not teach what those are. It teaches the failure modes that shipping
them did not: a judge that passes bad runs, a retriever that is fine on
average and broken for one customer, an agent that runs a tool twice after a
crash, a document that tells the model to leak another tenant's data and
succeeds, a model upgrade that regresses quietly. Every phase starts from a
production failure and ends with a measured defence.

**Evals come first** because every other phase is judged by them. Without a
calibrated judge, "the retriever improved" and "the new model is better" are
opinions.

Boundary with course 3: this course owns what you build on top of a model —
judges and datasets, retrieval, agents, security, and changing an agent
system safely. Course 3, the inference-internals course, owns how the model
runs and how a model call is measured and gated — tokens, KV cache, the
context budget and compaction, constrained decoding, provider caching, cost
per request and cost budgets, routing against a control group, the
statistics of a gate, quality SLOs, the run record, fallbacks and quality
incidents. Neither repeats the other.

**Read first: the inference-internals course (all eleven phases).** Every
phase here names the platform phase it assumes, in the form
`(inference-internals 5B)`, and uses it without teaching it again.

## What you will be able to do

Build an evaluation you can trust, with human labels and a calibrated judge;
measure retrieval per segment and fix the worst slice; run an agent that
survives a crash at any step without a duplicate side effect; keep a hostile
document from moving data across a tenant boundary; and ship a model change
behind a regression gate with a rollback that works.

---

## Phase 1 — Evaluation systems and production quality
question: How do you know the system got better, when the judge that says so is itself a model?
minutes: 150
assumes: he has run an LLM eval pipeline before and knows what an LLM judge is; tokens and per-token cost (inference-internals 1 and 3A); paired bootstrap interval, the worst-end verdict and what a small eval set can detect (inference-internals 4B); sample size, the temperature-0 noise floor and the quality SLO as a good-event ratio (inference-internals 5B); dollars per correct answer and position-bias control (inference-internals 3B); slice tests with a z-score (inference-internals 6B)
introduces: error analysis and open coding, failure taxonomy, golden set and contamination, pass/fail vs Likert, judge calibration (true-positive and true-negative rates against human labels), inter-rater agreement (kappa), pass@k vs pass^k
leaves-for-later: retrieval-specific metrics (2.2), regression gates in release (2.5)

### Why you're here
The dashboard says the agent succeeds 91% of the time. A customer sends three transcripts in which it confidently did the wrong thing, and all three were scored "pass" by the judge. You check ten more by hand: the judge passes about a third of the bad ones. The 91% was never a measurement of the agent. It was a measurement of the judge's optimism, and every improvement shipped against it was noise.

Practitioners who do this well agree on one thing: read the traces yourself first. This phase is that method, made rigorous enough to gate a release.

### Sections
1.1 — Does this need an LLM: deterministic and simpler baselines, and the cost of using generation where classification would do
1.2 — Error analysis: reading 100 real traces, open coding, and building the failure taxonomy from what you saw — not from what you expected
1.3 — Building the dataset: representative sampling, difficult slices, train/dev/eval separation, versioning, and contamination
1.4 — Graders: deterministic checks, model judges and human labels — and pass/fail over 1–5 scores
1.5 — Calibrating the judge: held-out human labels, true-positive and true-negative rates, a second rater's kappa, and what to do when the judge disagrees with you
1.6 — Repeated runs: pass@k versus pass^k, and why an agent that succeeds 80% per attempt has a very different story at five attempts

### Lab
Take 150 real Mission HQ agent runs. Open-code them and build the taxonomy. Label a held-out set by hand (two raters). Build one judge per failure class and report its true-positive and true-negative rates. Then use the calibrated judge in the paired bootstrap gate from inference-internals 4B to prove one prompt change is better — or show honestly that it is not.

### Demonstrate
A taxonomy from real traces, a judge with reported error rates against human labels, kappa between two raters, and one comparison with a confidence interval that either clears the threshold or does not.

### Test out
- Explain: why a 1–5 judge score is worse than pass/fail for gating, and what "the judge's false-pass rate" means operationally.
- Predict: given per-attempt success of 0.6 and 5 attempts, pass@5 and pass^5, and which one the customer experiences.
- Demonstrate: the calibrated judge and the paired comparison.

---

## Phase 2 — Retrieval and context systems at scale
question: Why is retrieval fine on average and broken for the one customer who complains, and how do you find that before they do?
minutes: 180
assumes: calibrated judge (2.1), difficult slices (2.1); tokens and the KV cache (inference-internals 1); the context budget with zone caps, long-context degradation, the compaction trigger and cache-friendly prompt layout (inference-internals 2 and 3A); he has built hybrid retrieval with RRF
introduces: ingestion and version consistency, freshness guarantees, query classification, multi-stage retrieval, tenant-aware filtering before retrieval, recall@k per segment, grounding and citation checks, separating retrieval failure from generation failure, agent memory lifecycle and provenance
leaves-for-later: agent memory (2.3)

### Why you're here
Overall recall@10 is 0.82. For one enterprise customer with long PDF contracts it is 0.31, and their questions are the ones that matter. Meanwhile a document deleted last week is still being retrieved, because the index and the source of truth disagree about what exists. Adding more context to compensate does not help; the inference course already showed that answers get worse as the window fills.

Retrieval at scale is not an embedding choice. It is a data pipeline with consistency guarantees, evaluated per segment, feeding a context budget you already know how to set.

### Sections
2.1 — Ingestion as a pipeline: document versions, incremental indexing, deletion, and what "fresh" means as a guarantee
2.2 — Query classification and routing: which queries need lexical search, which need vectors, which need neither
2.3 — Multi-stage retrieval: candidate generation, reranking, and where late-interaction models fit
2.4 — Tenant and permission filtering before retrieval, never after — and how to prove nothing crosses
2.5 — Chunking by structure and by query: why one chunk size fails, and when to fix the data instead of the retriever
2.6 — Recall per segment: by customer, document type and language; finding the worst slice and fixing that
2.7 — Grounding: citation correctness, and telling a retrieval failure from a generation failure in the same trace
2.8 — Memory as a retrieval source: lifecycle, provenance, invalidation without deletion, and what an agent may trust from yesterday

### Lab
Seed two synthetic tenants over Mission HQ's vault (two tenant IDs, disjoint documents, a few deliberately similar) — Mission HQ is single-tenant, so the lab creates the boundary it tests. Build a retrieval benchmark on it: labelled queries per segment. Compare BM25, vector, RRF and RRF plus reranker by recall@k per slice, p95 latency and cost. Find the worst slice and fix it. Prove a document from tenant A can never enter tenant B's context.

### Demonstrate
Recall@k per segment for four configurations, the worst slice fixed with a before/after, and a tenant-isolation test that fails when the filter is removed.

### Test out
- Explain: why permission filtering must happen before retrieval, and what breaks when it is applied to the top-k afterwards.
- Predict: for a described corpus and query mix, which segment will have the worst recall and why.
- Demonstrate: the per-segment benchmark and the isolation test.

---

## Phase 3 — Durable agent runtimes and tool systems
question: When an agent crashes between deciding to act and recording that it acted, what happens on resume — and how do you make the answer "nothing twice"?
minutes: 180
assumes: he runs durable workflows with approvals in Mission HQ; calibrated judge (2.1); constrained decoding, strict schemas and the truncated structured answer (inference-internals 1 and 2); per-request cost budgets, the reservation pattern and the iteration cap (inference-internals 3B); temperature 0 is not reproducible (inference-internals 1)
introduces: agent as persisted state machine, event log and checkpoint, idempotent tool execution, transactional tool boundary, compensation and reconciliation, asynchronous tools, approval as a state, bounded parallelism, tool schema evolution, capability-scoped permissions, sandboxing, step budgets for a run, deterministic replay, multi-agent failure propagation
leaves-for-later: security of tool inputs (2.4), sagas and delivery guarantees across services (5.2)

### Why you're here
The agent sent the email, then the process was killed before the "sent" event was written. On restart it resumed from the last checkpoint and sent the email again. A week later the same shape of bug charged a customer twice through a payment tool. The workflow engine was durable. The side effect was not.

An agent is a state machine with side effects, and every transition has a crash point. This phase makes each one explicit and tests all of them.

### Sections
3.1 — The agent as a persisted state machine: states, transitions, and the event log as the source of truth
3.2 — Checkpoints and resumability: what is saved, when, and the window between acting and recording
3.3 — Idempotent tool execution: idempotency keys, where the key must be committed, and tools that cannot be made idempotent
3.4 — Compensating a tool that already acted: undoing what cannot be retried, and reconciliation after partial failure (the general saga pattern across services is 5.2)
3.5 — Long-running and asynchronous tools: waiting without holding a slot, timeouts, and the callback that never comes
3.6 — Approvals and escalation as states: pausing safely, resuming after a restart, expiring an approval
3.7 — Tool schema evolution: changing a tool's schema without breaking agents that are already running
3.8 — Permissions and sandboxes: capability-scoped credentials per tool, sandboxing code and browser tools
3.9 — Step budgets for a whole run, and deterministic replay of a run from its recorded inputs and outputs
3.10 — Multi-agent failure propagation: a sub-agent's bad output as the parent's input, and where to stop it

### Lab
Instrument Mission HQ's task workflow so it can be killed at every transition. Kill it at each one, 50 times, with side-effecting tools stubbed to record calls. Resume. Count duplicate side effects. Fix each crash window found. Replay one failing run from its seed.

### Demonstrate
A crash matrix — every transition, killed, resumed — with zero duplicate external actions, approvals that survive a restart, and one run replayed deterministically from a recorded seed. Report pass^5, not pass@1.

### Test out
- Explain: the act-then-record window and why an idempotency key must be committed before the side effect.
- Predict: given a transition diagram, which crash points produce a duplicate and which produce a lost action.
- Demonstrate: the crash matrix with zero duplicates.

---

## Phase 4 — Security and isolation for compound AI systems
question: If a retrieved document can tell the model what to do, how do you build the system so that obeying it still cannot leak anything?
minutes: 180
assumes: tenant filtering before retrieval (2.2), capability-scoped tools (2.3); he has built input guardrails; the shared prefix cache as a timing side channel and cache salting (inference-internals 6A); the semantic cache that serves one user's answer to another (inference-internals 5B)
introduces: direct vs indirect prompt injection, poisoned documents and persistent memory attacks, confused deputy through tools, exfiltration through tool arguments and outputs, excessive agency, output validation before side effects, model output as untrusted input (SQL, commands, URLs), isolation across retrieval/memory/caches/telemetry, the "lethal trifecta" and the rule of two, policy enforcement outside the model, adversarial evaluation, containment when the model is assumed compromised
leaves-for-later: service-level security boundaries (6.4)

### Why you're here
Your guardrail classifier catches 95% of injection attempts in its test set. A 2025 study attacked twelve published defences with adaptive attacks and broke all of them, most above 90% success. The classifier is not the defence. The architecture is: if the model can read untrusted content, access private data, and send data out — all three in one session — then a good enough attack wins, and the classifier only decides how long that takes.

This phase designs for the case where the model has already been convinced.

### Sections
4.1 — The threat model for a compound AI system: who is the attacker, what do they control, what do they want
4.2 — Injection: direct, indirect through documents, and persistent through memory — with real examples
4.3 — The trifecta and the rule of two: untrusted input, private data, outbound channel — never all three in one session
4.4 — Tools as the attack surface: confused deputy, exfiltration through arguments and outputs, excessive agency
4.5 — Model output is untrusted input: validating generated SQL, commands and URLs before they touch anything
4.6 — Isolation everywhere the data flows: retrieval, memory, application caches and telemetry, and the places tenant boundaries usually leak
4.7 — Policy outside the model: capability scoping, per-operation credentials, enforcement the model cannot argue with
4.8 — Adversarial evaluation: an attack corpus that adapts to your defences, and residual-risk reporting
4.9 — Containment: designing so a fully compromised model still cannot cross the boundary — and the read/write split Mission HQ already uses

### Lab
Using the two synthetic tenants from phase 2, plant indirect injections in Mission HQ's vault documents and in tool outputs, including attempts to reach the other tenant's data. Run an adaptive attack loop of at least 200 attempts. Show which boundary stopped each one — and that it was an architectural boundary, not a classifier score.

### Demonstrate
An attack corpus, the results of 200+ adaptive attempts, zero cross-boundary leaks, and a one-page argument for why each session in Mission HQ stays within the rule of two.

### Test out
- Explain: the lethal trifecta, and why a classifier cannot be the last line of defence.
- Predict: for a described agent (reads web, has DB access, can send email) which attack succeeds and which architectural change stops it.
- Demonstrate: the adversarial corpus and the isolation results.

---

## Phase 5 — Operating and evolving AI systems
question: How do you change a model, a prompt or a retriever in a system whose output is never the same twice, and know whether you made it worse?
minutes: 120
assumes: calibrated judge (2.1), per-segment metrics (2.2), replayable runs (2.3); the run record with requested and answering model, prompt name and version, and the serving-infrastructure axis (inference-internals 5B); routing and cascades against a random control group, and gating a model swap on quality, cost and latency (inference-internals 3B); the paired bootstrap gate (inference-internals 4B); rollback to a known-good baseline, time to restore, and a control group instead of before/after (inference-internals 6B)
introduces: independent versioning of retrieval index, tools and policy, shadow execution with side-effect suppression, canaries for runs with side effects, the state that rolls back with a model, drift from data and traffic, closing the eval loop from production, selecting high-information examples, prompt vs retrieval vs fine-tuning decisions, distillation
leaves-for-later: release engineering in general (6.3)

### Why you're here
A provider deprecates the model you built on, with 60 days' notice. The replacement scores higher on the public benchmarks and worse on your customer's contracts, and your dashboard cannot see the difference because the judge was calibrated on the old model's failure modes. You migrate, quality drops for one segment, and it takes three weeks of support tickets to notice.

Changing an AI system is a release problem with one extra difficulty: the output is not deterministic, so "it works on the canary" needs a definition. This phase gives it one.

### Sections
5.1 — What has a version beyond the model and the prompt: retrieval index, tools and policies, each versioned independently and named in the run record
5.2 — Shadow execution: running the challenger on real traffic with side effects suppressed, and comparing by failure slice
5.3 — Canaries for an agent: a canary whose runs have side effects, and the automatic halt
5.4 — Rollback for an agent: the state written under the new model — memory, index entries, pending approvals — that has to roll back with it
5.5 — Drift without a deploy: data shifts and a prompt that slowly stops fitting the traffic
5.6 — Closing the loop: production failures and corrections into versioned eval data, and choosing the examples that carry information
5.7 — The improvement decision: prompt, retrieval, tools, or training — and when SFT, LoRA or distillation is justified by the numbers

### Lab
Shadow a candidate model on real Mission HQ traces. Compare quality, cost and latency by failure slice using the phase-1 judge. Canary it. Inject a regression in one slice and show the gate catches it and rolls back automatically. Then distil one narrow step (a classifier or router) to a small model, beat the prompted baseline on the eval at lower cost, swap the base model, and check whether the gain survived.

### Demonstrate
A shadow comparison by slice, a canary that rolled back on an injected regression, and one distilled component with the before/after on the same eval set.

### Test out
- Explain: what state must roll back with the model in an agent system, and why a shadow run must suppress side effects.
- Predict: for a described model swap, which slice is most likely to regress and which signal would show it first.
- Demonstrate: the canary with automatic rollback.

---

## Integrated lab for the course

Label 50–100 real Mission HQ runs by hand. Calibrate the judge. Repair one major failure class end to end — with the per-segment retrieval benchmark if it is a retrieval failure, with the crash matrix if it is an agent failure. Ship the fix behind the canary gate. Write the one-page ship/rollback decision with its numbers.

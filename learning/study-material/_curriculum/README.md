# Advanced applied-AI curriculum: the reference

This folder is the durable record of the curriculum. If the chat history is lost, start here.

Last updated: 2026-09-18.

## How to use this folder, from any session

You do not need this chat. Everything needed to generate a module is on disk.

**If the module has a dossier** (status ready or complete):

1. Read this file for the plan and the module's block below.
2. Read the module's dossier, `module-NN-<slug>.md`. Section 5 of every dossier is the proposed phase outline. That is the approved plan.
3. Read `module-01-coverage.md` so the new module links to Module 1 instead of repeating it.
4. Generate with the study skill: `/study <topic>`. In this repo the skill is at `.claude/skills/study/`, and `references/mission-hq.md` sets the base directory and the publish path.
5. Re-check anything the dossier marks as fast-changing. Versions and provider defaults move fastest.
6. After the module is finished, add a `module-NN-coverage.md` like the Module 1 one, and update the status table.

**If the module has no dossier** (status not started or partial):

1. Read the module's block below. It carries a research brief: the questions to answer, the named starting points to fetch, and the overlap to check.
2. Read `RESEARCH-BRIEF.md`. It is the contract every dossier follows, including the twelve required sections.
3. Run the research, write `module-NN-<slug>.md`, then generate from it.
4. For the two partial modules, read the saved reports in `raw-research/` first. They are unreviewed input, not conclusions.

The dossiers are research, not course material. They will change while the course is written.

## Where this sits

This curriculum is the applied-AI track. It is separate from the eight path courses specified in `learning/courses/NN-<name>/course.md`, which cover performance, storage, distributed systems, reliability, design and production infrastructure. Module 1 of this curriculum and course 3 of that path are the same published course, `inference-internals`.

## Who this is for

- An advanced engineer who builds AI products.
- Learning, not changing a product. Labs are standalone and run from each course's own `code/` folder.
- Background product, used only to choose difficulty and scenarios: an AI customer-support platform with web chat, WhatsApp, voice, knowledge-base upload, human escalation, model switching, and a learning loop. Never assign work on that product.
- Hardware: an Apple Silicon laptop. Anything needing a GPU or a cluster must say where it runs and what it costs.
- Writing style: plain English, short sentences, no metaphors. See `~/.claude/skills/study/references/writing-style.md`.

## The plan: 22 modules in 7 layers

| # | Layer | Module | Status | Research lives in | Planned phases |
|---|---|---|---|---|---|
| 1 | Model | LLM inference internals for application engineers | **complete** | `module-01-coverage.md` | 7 (12 documents) |
| 2 | Model | Context engineering and long-horizon reliability | **ready** | `module-02-context-engineering.md` | 4 |
| 3 | Knowledge | Retrieval engineering internals | **ready** | `module-03-retrieval-internals.md` | 7 |
| 4 | Knowledge | Advanced retrieval architectures | partial | `raw-research/module-04-*.md` | to be sized |
| 5 | Knowledge | Document and multimodal ingestion | not started | brief below | to be sized |
| 6 | Agents | The tool layer and MCP internals | **ready** | `module-06-tools-mcp.md` | 6 |
| 7 | Agents | Agent harness engineering | **ready** | `module-07-agent-harness.md` | 6 |
| 8 | Agents | Agent protocols and agent identity | not started | brief below | to be sized |
| 9 | Agents | Orchestration, state, and durable execution | **ready** | `module-09-orchestration-durable.md` | 7 |
| 10 | Agents | Memory systems | not started | brief below | to be sized |
| 11 | Evals | Eval engineering | **ready** | `module-11-eval-engineering.md` | 7 |
| 12 | Evals | Agent evals, online evals, and the improvement loop | not started | brief below | to be sized |
| 13 | Infrastructure | Serving and self-hosting at cluster scale | not started | brief below | 3 to 4 |
| 14 | Infrastructure | Cost, routing, and AI FinOps | not started | brief below | about 3 |
| 15 | Infrastructure | Observability and reliability operations | partial | `raw-research/module-15-*.md` | 3 to 4 |
| 16 | Security | Security and threat modelling | **ready** | `module-16-security.md` | 7 |
| 17 | Security | Guardrails architecture | not started | brief below | to be sized |
| 18 | Security | Compliance and auditability | not started | brief below | to be sized |
| 19 | Product | Agent product design and human approval | not started | brief below | to be sized |
| 20 | Product | Voice agents in production | not started | brief below | to be sized |
| 21 | Product | Post-training, distillation, and small models | not started | brief below | to be sized |
| 22 | Product | Electives | not started | brief below | per topic |

Status meanings:

- **complete**: the course is generated and published.
- **ready**: the dossier exists and passed review. Generate from it.
- **partial**: research-helper reports are saved in `raw-research/`, but no dossier was written. Use them as input.
- **not started**: no research yet. The brief below says how to do it.

Counts today: 1 complete, 7 ready, 2 partial, 12 not started.

## The core path

The full curriculum is about 250 to 400 hours. The core path covers most of the job in about 100 hours. Do these in order:

1. Module 1, inference internals. **Complete.**
2. Module 2, context engineering.
3. Module 11, eval engineering. It comes early because later modules depend on evals.
4. Module 6, tool layer and MCP.
5. Module 7, agent harness engineering.
6. Module 9, orchestration and durable execution.
7. Module 16, security and threat modelling.
8. Module 15, observability.

Seven of those eight have research. Only Module 15 needs research first, and it has raw reports to start from.

Then choose by interest: retrieval in Modules 3 to 5, serving and cost in Modules 13 and 14, voice in Module 20.

---

# The modules

Each block below gives the question the module answers, where its research lives, and what still has to be done. For modules with no dossier, the block is the research brief.

**Rule for every brief.** Nothing below is a verified fact. The named tools, papers and specifications are starting points to fetch, not claims. Check every version and date at research time. Follow the evidence labels in `RESEARCH-BRIEF.md`: verified, inferred, or not checked.

---

## Layer 1 — Model

### Module 1 — LLM inference internals for application engineers
**Status: complete.** 7 phases, 12 documents, published.

**Question.** Where does the time and the money go in a model call, and which of it can you control?

Read `module-01-coverage.md` before writing any other module. It is section-by-section, and it exists so no other module repeats it. Modules link to its sections in the form `Module 1, 3.2`.

---

### Module 2 — Context engineering and long-horizon reliability
**Status: ready.** Dossier: `module-02-context-engineering.md`. 4 phases.

**Question.** Your agent gets worse after two hundred tool calls. Which part of the context caused it, and what does fixing it cost in cache?

The dossier is dense on provider behaviour, which is also what goes stale fastest. Re-check provider compaction defaults and the client library versions before generating.

Its overlap table with Module 1 is already written. Honour it: budget zones and the threshold trigger are Module 1, this module adds the validation method and the measurement labs.

---

## Layer 2 — Knowledge

### Module 3 — Retrieval engineering internals
**Status: ready.** Dossier: `module-03-retrieval-internals.md`. 7 phases.

**Question.** Your retrieval scores well on average and fails for one customer. Which stage is responsible?

Covers approximate nearest-neighbour index internals, embedding quantization, hybrid retrieval with reranking, query understanding, chunking, freshness, and retrieval evals.

---

### Module 4 — Advanced retrieval architectures
**Status: partial.** One raw report in `raw-research/`, no dossier. Size the module after the dossier exists.

**Question.** When is a vector index the wrong tool, and what replaces it?

**Research brief.**

Topics to decompose: agentic retrieval, GraphRAG, retrieval without vectors, adaptive routing, multi-tenant isolation, grounding enforcement, semantic caching.

Starting points to fetch and verify:
- The original GraphRAG paper and the current maintained implementation. Check whether the project is still maintained and what the current release is.
- Published cost comparisons of graph construction against plain chunking, at a stated corpus size. Do not accept a cost claim without the corpus size.
- Semantic caching: the hit-rate and false-hit trade-off. A false cache hit returns a wrong answer, so the interesting number is the false-hit rate, not the hit rate.
- Multi-tenant isolation in vector stores: whether isolation is per-index, per-namespace or a filter, and what each costs. A filter-based tenant boundary is a security question, not a performance one.

Questions the dossier must answer: at what corpus size and query mix does GraphRAG beat hybrid retrieval, measured, and who published it. What breaks grounding enforcement. What a semantic cache does on a near-miss.

Overlap to check: Module 3 owns index internals and reranking. Module 16 owns tenant isolation as a security boundary. This module must not re-teach either.

---

### Module 5 — Document and multimodal ingestion
**Status: not started.**

**Question.** A customer uploads a 300-page scanned PDF with tables. What does each parsing path cost, and where does each one lose information?

**Research brief.**

Topics: layout-aware parsing against OCR, parser comparison, vision retrieval, multimodal embeddings, cost per 1,000 pages for each path.

Named starting points to fetch: Unstructured, LlamaParse, Docling, Reducto, Marker for parsing. ColPali and VisRAG for vision retrieval. Verify which are open source, which are hosted-only, and the current version of each.

The number this module exists for: **cost and accuracy per 1,000 pages for each path**, on the same document set. If no published comparison uses one document set, say so and design the lab to produce it.

Questions the dossier must answer: what layout-aware parsing recovers that OCR loses, with an example. Whether vision retrieval removes the need for a parser or adds to it. How table extraction is scored, because most reported accuracy numbers do not say.

Labs must run offline first. A scanned-PDF corpus plus a local parser gives a real number without an API key. Mark hosted parsers with their per-page price.

Overlap: Module 3 owns chunking and embedding. This module stops at the point where text and images become chunks.

---

## Layer 3 — Agents

### Module 6 — The tool layer and MCP internals
**Status: ready.** Dossier: `module-06-tools-mcp.md`. 6 phases.

**Question.** What does the model actually see when you give it a tool, and what does a bad tool description cost?

Covers tool design, parallel calls, code execution as a tool, the MCP specification, sandbox internals, and Agent Skills. The MCP specification is versioned and moves; re-check the specification revision before generating.

---

### Module 7 — Agent harness engineering
**Status: ready.** Dossier: `module-07-agent-harness.md`. 6 phases.

**Question.** The model did not run your tool. The harness did. What else is the harness deciding without telling you?

Covers the six parts of a harness, the rule that the harness and not the model runs tools, sandbox controls, and plans written as code.

---

### Module 8 — Agent protocols and agent identity
**Status: not started.**

**Question.** Two agents from different vendors need to work together. What can the protocol express, and what does it silently leave to trust?

**Research brief.**

Topics: MCP, A2A, WebMCP and what each is for. Signed Agent Cards. What the protocols cannot express. Per-agent identity, scoped tokens, and audit records.

Starting points to fetch: the MCP specification at its current revision, the A2A specification and its governing body, and WebMCP. For each, record the revision, the date, and whether it is a standard or a vendor proposal. That distinction matters and is often blurred.

Questions the dossier must answer: what an Agent Card asserts and what verifies it. Whether any of these protocols carries authorization, or only identity. What happens when agent A delegates to agent B on a user's behalf, and where the user's consent is recorded. Whether revocation exists.

This module is where the provenance and short-lived-credential pattern from general infrastructure applies to agents. Check whether any protocol has adopted OIDC-style federation, and say plainly if none has. Course 8 phase 5 in `learning/courses/08-production-infra/` covers that pattern for build systems, and its `sources.md` has the verified references.

Overlap: Module 6 owns the MCP wire format and tool semantics. This module owns identity, delegation and trust between parties. Module 16 owns the attack; this module owns the protocol.

---

### Module 9 — Orchestration, state, and durable execution
**Status: ready.** Dossier: `module-09-orchestration-durable.md`. 7 phases.

**Question.** Your agent crashed halfway through a five-step task that already charged a customer. What resumes, and what must not run twice?

Covers single-agent against multi-agent trade-offs, checkpointing, Temporal, Inngest and Restate, idempotency and compensating actions, and human-in-the-loop as architecture.

---

### Module 10 — Memory systems
**Status: not started.**

**Question.** Your agent remembers something the user corrected last week. Which memory wrote it, and what should have deleted it?

**Research brief.**

Topics: a taxonomy of memory, a comparison of Mem0, Zep and Letta, decay and conflict resolution, memory evals, privacy and deletion.

Starting points to fetch: Mem0, Zep and Letta. For each record the current version, the storage model, and whether memory is extracted by a model or written explicitly. Also fetch any published benchmark each project cites for itself, and read its method, because self-published memory benchmarks usually choose the task.

Questions the dossier must answer: what "memory" means in each system, because the three do not agree. How a contradiction between an old and a new fact is resolved, and whether the user can see it. How deletion works across the store and any derived index. Whether any system can prove a fact was forgotten.

The strongest lab here is a conflict test: write a fact, correct it, and measure whether the corrected fact wins, over how many turns.

Overlap: Module 2 owns the context window within one run. This module owns state across runs. Module 18 owns the legal duty to delete; this module owns the mechanism.

---

## Layer 4 — Evals

### Module 11 — Eval engineering
**Status: ready.** Dossier: `module-11-eval-engineering.md`. 7 phases.

**Question.** Your judge says the new prompt is better. Why should anyone believe the judge?

Covers error analysis first, building LLM judges, validating judges against humans, golden datasets, and CI gates. Do this module early. Modules 12, 17 and 21 all assume a calibrated judge.

---

### Module 12 — Agent evals, online evals, and the improvement loop
**Status: not started.**

**Question.** A single-turn eval passes and the agent still fails the task. What do you score instead?

**Research brief.**

Topics: trajectory evals, user simulators, adversarial suites, online scoring, safe rollout, and a three-tier eval stack of cheap rules on every span, a small judge on a sample, and humans on the gold set.

Starting points to fetch: published agent benchmarks that score trajectories rather than final answers, and the scoring code for at least one. Read how partial credit is assigned, because that choice decides the result. Also fetch whatever the major agent frameworks ship for online scoring, and record whether scoring runs inline or offline.

Questions the dossier must answer: what a trajectory eval can detect that an outcome eval cannot, with a worked case. How a user simulator is validated, since an unvalidated simulator moves the target. What sampling rate makes online scoring affordable, with the arithmetic.

Overlap: Module 11 owns judge construction and validation. This module owns what to score for a multi-step agent, and how to run it in production. Module 15 owns the telemetry that carries the scores.

---

## Layer 5 — Infrastructure

### Module 13 — Serving and self-hosting at cluster scale
**Status: not started.** 3 to 4 phases.

**Question.** At what point does self-hosting beat an API, and what do you take on when it does?

**Research brief.**

Topics: splitting prefill and decode across machines, NIXL, KV cache as shared storage with Mooncake and LMCache, and routing at the serving layer.

Starting points to fetch: NIXL, Mooncake and LMCache. For each record what problem it solves, its current release, and whether it is production or research. Also fetch the current release notes of the main serving engines and the flags that control disaggregated prefill.

Questions the dossier must answer: the arithmetic for when self-hosting is cheaper, and at what utilisation it stops being cheaper. What a cache-aware router needs to know that a normal load balancer does not. What breaks when prefill and decode are on different machines.

Hardware honesty is mandatory here. The learner has an Apple Silicon laptop. Say for every lab where it runs and what it costs. A cluster lab that cannot run locally must be replaced with a simulation that produces the same arithmetic, or labelled as read-only.

Overlap: Module 1 owns single-node serving, batching and the KV cache concept. This module owns what changes when one machine is not enough.

---

### Module 14 — Cost, routing, and AI FinOps
**Status: not started.** About 3 phases.

**Question.** The bill doubled and the traffic did not. Which tenant, which route, and which model change caused it?

**Research brief.**

Topics: gateway options, model choice as a runtime decision, per-tenant metering, budgets, forecasts, and cost ownership.

Starting points to fetch: the current AI gateway options and what each meters. Published routing-cascade results, and whether any reports a control group. Provider pricing pages for the token classes, including cached input and cache write, because those prices change and are the largest single source of wrong cost models.

Questions the dossier must answer: how cost is attributed to a tenant when one request fans out to several models. What a routing cascade actually saves, measured against a control group rather than against an estimate. How a budget is enforced without breaking a request mid-stream.

Overlap: Module 1 already owns the per-request cost model, the token classes, cache break-even and routing against a control group. Read `module-01-coverage.md` carefully before scoping this module. The new material is per-tenant attribution, forecasting, and ownership, not the arithmetic.

---

### Module 15 — Observability and reliability operations
**Status: partial.** Three raw reports in `raw-research/`, no dossier. 3 to 4 phases.

**Question.** Quality dropped and no alert fired. What should have been recorded at the time?

**Research brief.**

Topics: tracing pipelines, OpenTelemetry GenAI conventions and their status, dashboards, agent-level telemetry, and incident response for quality failures.

Read the three raw reports first. They are unreviewed.

Starting points to fetch: the OpenTelemetry GenAI semantic conventions at their current status. Record which attributes are stable, which are experimental, and the exact names and units. This is the single most error-prone area in the module, because attribute names change and people invent their own. Check specifically whether a client-side time-to-first-token attribute exists and what unit it uses, before writing any custom name.

Questions the dossier must answer: what a span must carry for a quality incident to be diagnosable afterwards. How an agent trajectory is represented in a trace. What a quality SLO looks like when correctness is judged rather than measured.

Overlap: Module 1 owns the run record, the cost record, and quality SLOs. This module owns the pipeline, the conventions and the incident path.

---

## Layer 6 — Security

### Module 16 — Security and threat modelling
**Status: ready.** Dossier: `module-16-security.md`. 7 phases.

**Question.** A document in the knowledge base tells the model to send another tenant's data. What stops it?

Covers the three-part risk of private data, untrusted content and outbound messages, indirect injection through knowledge-base files, the MCP supply chain, tenant isolation, the OWASP LLM Top 10, the six named agent security designs, CaMeL, and the limits of classifiers.

---

### Module 17 — Guardrails architecture
**Status: not started.**

**Question.** Your classifier adds 300 ms to every request and still misses attacks. What belongs inline, and what belongs after?

**Research brief.**

Topics: layered checks, a fast inline classifier, hazard models, schema validation, asynchronous judges, per-tenant policy, and escalation as a safety control.

Starting points to fetch: the current open guardrail models and their published evaluation, including the false-positive rate. A guardrail's false-positive rate is the number that decides whether it is usable, and vendors report recall instead. Also fetch any published latency figures, with the hardware.

Questions the dossier must answer: which checks are cheap enough to run on every request, with measured latency. What an asynchronous judge can do that an inline one cannot. How a per-tenant policy is expressed and where it is enforced. What happens on classifier failure, open or closed.

Overlap: Module 16 owns the threat model and the architectural defences. This module owns the runtime check layer and its cost. Do not re-teach injection taxonomy.

---

### Module 18 — Compliance and auditability
**Status: not started.**

**Question.** A regulator asks you to show why the agent did what it did, nine months ago. What do you hand over?

**Research brief.**

Topics: EU AI Act transparency duties, audit logs a reviewer accepts, retention, deletion across memory and vector indexes, and data residency.

Starting points to fetch: the EU AI Act text itself, not summaries, and confirm which articles apply from which date. An earlier draft of this plan stated that Article 50 applies from 2 August 2026. **That date is not verified. Check it against the regulation before teaching it.**

Questions the dossier must answer: what an audit record must contain to be useful nine months later. How deletion propagates to a vector index and to derived memory, and how it is proven. What data residency means when a model provider is in another region.

Overlap: Module 10 owns the deletion mechanism. Module 15 owns the telemetry. This module owns the duty and the evidence.

---

## Layer 7 — Product

### Module 19 — Agent product design and human approval
**Status: not started.**

**Question.** Which actions can the agent take alone, and what must the approval screen show for the approval to mean anything?

**Research brief.**

Topics: reads run freely and writes need review, approval screens that show the payload, confidence-gated routing, and the gradient from suggest to confirm to execute.

Starting points to fetch: published human-in-the-loop designs from shipped agent products, and any research on approval fatigue. The interesting failure is an approval step that people click through, which makes it worse than no step because it moves the blame without reducing the risk.

Questions the dossier must answer: what the approval screen must show for consent to be informed. How confidence is calibrated well enough to gate on. What the measured click-through rate is on approval prompts, if anyone has published one.

Overlap: Module 9 owns human-in-the-loop as an architecture and a durable-execution concern. This module owns the interface and the decision policy.

---

### Module 20 — Voice agents in production
**Status: not started.**

**Question.** Where does the one-second budget go, and what do you give up to stay inside it?

**Research brief.**

Topics: the latency budget under one second, speech-to-speech against chained pipelines, cost per minute, interruption handling, and telephony.

Starting points to fetch: current speech-to-speech model pricing and latency, current chained-pipeline components, and telephony integration constraints. Record cost per minute for both paths with the same assumptions.

Questions the dossier must answer: the full latency budget, broken down by stage, for both architectures. How interruption is detected and what it costs to support. What telephony adds that a browser does not, including codec and jitter.

Overlap: Module 1 owns streaming and time-to-first-token. This module owns the audio path and the real-time budget.

---

### Module 21 — Post-training, distillation, and small models
**Status: not started.**

**Question.** You have tried prompting and retrieval. How do you know fine-tuning is the next step, and how do you know it worked?

**Research brief.**

Topics: the decision order of prompt, retrieval, fine-tune, distill. LoRA and QLoRA. Dataset curation. Eval-gated training. Agent reinforcement fine-tuning. Small models on devices.

Starting points to fetch: current LoRA and QLoRA tooling and its hardware requirements, and any published comparison of fine-tuning against retrieval on the same task. The decision order matters more than the technique, and it is the part usually skipped.

Questions the dossier must answer: the measured conditions under which fine-tuning beats retrieval. What dataset size is actually needed, with a source. How a training run is gated on evals so a regression cannot ship.

Hardware honesty again. State what fits on an Apple Silicon laptop and what does not, with the memory arithmetic.

Overlap: Module 11 owns the eval gate. This module owns the training decision.

---

### Module 22 — Electives
**Status: not started.** Sized per topic.

**Question.** Varies. Each elective is one to two phases.

**Candidate topics, each needing its own short brief:** computer-use and browser agents, agent payments with AP2 and x402, self-evolving agents, and reinforcement-learning environments.

Treat each as a separate small research task. Do not write one dossier for all four. Before starting any elective, check it has not been absorbed into a numbered module.

---

## Files in this folder

| File | Purpose |
|---|---|
| `README.md` | this index and the per-module briefs |
| `RESEARCH-BRIEF.md` | the contract every module dossier follows, with the twelve required sections |
| `module-01-coverage.md` | what Module 1 teaches, section by section. Read before writing any module |
| `module-NN-<slug>.md` | one research dossier per module, for the eight that have one |
| `raw-research/` | unreviewed helper reports from stopped research runs, for Modules 4 and 15 |

## What is not decided

- Phase counts for the twelve not-started modules. Size them after research, not before.
- Topic slugs for `/study`. Module 1 used `inference-internals`. Choose the slug when the course starts and record it in the status table.
- Whether Module 22's electives stay one module or become numbered modules.

# Advanced applied-AI curriculum: the reference

This folder is the durable record of the curriculum. If the chat history is lost, start here.

Last updated: 2026-09-25.

## How to use this folder, from any session

You do not need this chat. Everything needed to generate a module is on disk.

**If the module has a dossier** (status ready or complete):

1. Read this file for the plan and the module's block below.
2. Read the module's dossier, `module-NN-<slug>.md`. Section 5 of every dossier is the proposed phase outline. That is the approved plan.
3. Read `module-01-coverage.md` so the new module links to Module 1 instead of repeating it.
4. Generate with the study skill: `/study <topic>`. The skill lives at `~/.claude/skills/study/`. A portable copy is in `Desktop/project/code/skills/study-skill-v2/`.
5. Re-check anything the dossier marks as fast-changing. Versions and provider defaults move fastest.
6. After the module is finished, add a `module-NN-coverage.md` like the Module 1 one, and update the status table.

**If the module has no dossier** (status not started or partial):

1. Read the module's block below. It carries a research brief: the questions to answer, the named starting points to fetch, and the overlap to check.
2. Read `RESEARCH-BRIEF.md`. It is the contract every dossier follows, including the twelve required sections.
3. Run the research, write `module-NN-<slug>.md`, then generate from it.
4. For the two partial modules, read the saved reports in `raw-research/` first. They are unreviewed input, not conclusions.

The dossiers are research, not course material. They will change while the course is written.

## Who this is for

- An advanced engineer who builds AI products.
- Learning, not changing a product. Labs are standalone and run from each course's own `code/` folder.
- Background product, used only to choose difficulty and scenarios: an AI customer-support platform with web chat, WhatsApp, voice, knowledge-base upload, human escalation, model switching, and a learning loop. Never assign work on that product.
- Hardware: an Apple Silicon laptop. Anything needing a GPU or a cluster must say where it runs and what it costs.
- Writing style: plain English, short sentences, no metaphors. See `~/.claude/skills/study/references/writing-style.md`.

## The plan: 22 modules in 7 layers

| # | Layer | Module | Status | Research lives in | Phases |
|---|---|---|---|---|---|
| 1 | Model | LLM inference internals for application engineers | **complete** | `module-01-coverage.md` | 7 (12 documents) |
| 2 | Model | Context engineering and long-horizon reliability | **complete** | `module-02-context-engineering.md` | 4 |
| 3 | Knowledge | Retrieval engineering internals | **complete** | `module-03-retrieval-internals.md` | 7 |
| 4 | Knowledge | Advanced retrieval architectures | **complete** | `module-04-advanced-retrieval.md` | 7 |
| 5 | Knowledge | Document and multimodal ingestion | **complete** | `module-05-document-ingestion.md` | 5 |
| 6 | Agents | The tool layer and MCP internals | **complete** | `module-06-tools-mcp.md` | 5 |
| 7 | Agents | Agent harness engineering | **complete** | `module-07-agent-harness.md` | 5 |
| 8 | Agents | Agent protocols and agent identity | **complete** | `module-08-agent-protocols.md` | 5 |
| 9 | Agents | Orchestration, state, and durable execution | **complete** | `module-09-orchestration-durable.md` | 6 |
| 10 | Agents | Memory systems | **complete** | `module-10-memory.md` | 6 |
| 11 | Evals | Eval engineering | **complete** | `module-11-eval-engineering.md` | 6 |
| 12 | Evals | Agent evals, online evals, and the improvement loop | **complete** | `module-12-agent-evals.md` | 6 |
| 13 | Infrastructure | Serving and self-hosting at cluster scale | **complete** | `module-13-serving-cluster.md` | 4 |
| 14 | Infrastructure | Cost, routing, and AI FinOps | **complete** | `module-14-ai-finops.md` | 4 |
| 15 | Infrastructure | Observability and reliability operations | **complete** | `module-15-observability-ops.md` | 4 |
| 16 | Security | Security and threat modelling | **complete** | `module-16-security.md` | 6 |
| 17 | Security | Guardrails architecture | **complete** | `module-17-guardrails.md` | 4 |
| 18 | Security | Compliance and auditability | **complete** | `module-18-compliance.md` | 4 |
| 19 | Product | Agent product design and human approval | **complete** | `module-19-agent-product.md` | 4 |
| 20 | Product | Voice agents in production | **complete** | `module-20-voice-agents.md` | 4 |
| 21 | Product | Post-training, distillation, and small models | **complete** | `module-21-post-training.md` | 4 |
| 22 | Product | Electives (planned) | not started | brief below | per topic |

Status meanings:

- **complete**: the course is generated and published.
- **ready**: the dossier exists and passed review. Generate from it.
- **partial**: research-helper reports are saved in `raw-research/`, but no dossier was written. Use them as input.
- **not started**: no research yet. The brief below says how to do it.

Counts on 2026-09-25: 21 complete, 1 not started. Module 22 is planned and not built. The phase counts above are the built phase counts, from each module's `course.json`.

## The core path

The full curriculum is about 250 to 400 hours. The core path covers most of the job in about 100 hours. Do these in order:

1. Module 1, inference internals.
2. Module 2, context engineering.
3. Module 11, eval engineering. It comes early because later modules depend on evals.
4. Module 6, tool layer and MCP.
5. Module 7, agent harness engineering.
6. Module 9, orchestration and durable execution.
7. Module 16, security and threat modelling.
8. Module 15, observability.

Then choose by interest: retrieval in Modules 3 to 5, serving and cost in Modules 13 and 14, voice in Module 20.

All eight are built. Module 11 comes third in this order, but its phases use sections of Modules 1 to 6 and Module 9. For example, its Phase 1 links Module 9 section 6.4. Read a linked section when a phase names it.

---

# The modules

Each block below gives the question the module answers and where its research lives. All 21 numbered modules are built. The research briefs are kept as the record of what each module was asked to cover. Where a built module changed its question, its block gives the question as built.

**Rule for every brief.** Nothing below is a verified fact. The named tools, papers and specifications are starting points to fetch, not claims. Check every version and date at research time. Follow the evidence labels in `RESEARCH-BRIEF.md`: verified, inferred, or not checked.

---

## Layer 1 — Model

### Module 1 — LLM inference internals for application engineers
**Status: complete.** 7 phases, 12 documents, published.

**Question.** Where does the time and the money go in a model call, and which of it can you control?

**As built.** The phases do not state this question, and the last phase has no "The module question, answered" section. Section 6.4, "Defending an architecture in a design review", is the closing checklist.

Read `module-01-coverage.md` before writing any other module. It is section-by-section, and it exists so no other module repeats it. Modules link to its sections in the form `Module 1, 3.2`.

---

### Module 2 — Context engineering and long-horizon reliability
**Status: complete.** Dossier: `module-02-context-engineering.md`. 4 phases. Coverage file: `module-02-coverage.md`.

**Question.** Your agent gets worse after two hundred tool calls. Which part of the context caused it, and what does fixing it cost in cache?

**Question as built.** Is long context your problem at all, and if so, which of five causes is it: length, steps, state, cost or a lossy summary? Phase 4, "The module question, step by step", answers it. It gives the cache cost of a fix in one sentence only: compaction pays back in 3 to 12 steps.

The dossier is current to 2026-09-17 and is unusually dense on provider behaviour, which is also what goes stale fastest. Re-check provider compaction defaults and the `openai-python` and Anthropic feature versions before generating.

Its overlap table with Module 1 is already written. Honour it: budget zones and the threshold trigger are Module 1, this module adds the validation method and the measurement labs.

---

## Layer 2 — Knowledge

### Module 3 — Retrieval engineering internals
**Status: complete.** Dossier: `module-03-retrieval-internals.md`. 7 phases. Coverage file: `module-03-coverage.md`.

**Question.** Your retrieval scores well on average and fails for one customer. Which stage is responsible?

Covers approximate nearest-neighbour index internals, embedding quantization, hybrid retrieval with reranking, query understanding, chunking, freshness, and retrieval evals.

---

### Module 4 — Advanced retrieval architectures
**Status: complete.** Dossier: `module-04-advanced-retrieval.md`. 7 phases.

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
**Status: complete.** Dossier: `module-05-document-ingestion.md`. 5 phases.

**Question.** A customer uploads a 300-page scanned PDF with tables. What does each parsing path cost, and where does each one lose information?

**Covered since 2026-09-25.** VisRAG is now taught in Phase 4, section "4.4 — VisRAG: one vector per page, answers from images". It covers what VisRAG stores and costs per 1,000 pages against a parsed page, and what its paper measured.

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
**Status: complete.** Dossier: `module-06-tools-mcp.md`. 5 phases.

**Question.** What does the model actually see when you give it a tool, and what does a bad tool description cost?

**Question as built.** An agent calls 40 tools across three MCP servers. Which tools should the model see on each turn, what does each definition cost, and what can a server change or claim that the client must not trust? Phase 5, "The module question, answered", answers it. The cost of a vague description is measured in Phase 2: section 2.3 prints the search recall with vague descriptions, and section 2.4 covers names, descriptions and errors. The closing does not repeat that number.

Covers tool design, parallel calls, code execution as a tool, the MCP specification, sandbox internals, and Agent Skills. The MCP specification is versioned and moves; re-check the specification revision before generating.

---

### Module 7 — Agent harness engineering
**Status: complete.** Dossier: `module-07-agent-harness.md`. 5 phases, published 2026-09-23.

**Question.** The model did not run your tool. The harness did. What else is the harness deciding without telling you?

**Question as built.** You ship a coding agent that runs shell commands on customers' machines. Which controls stop a harmful command, where does each one sit, and what does each one miss? Phase 5, "The module question, answered", answers it.

**Covered since 2026-09-25.** The six parts of a harness: Phase 1 section 1.5, "The six parts of a harness, mapped onto the loop". It uses Sebastian Raschka's six-part list and adds the loop stop and the OS boundary as two rows of the course's own.

Covers the six parts of a harness, the rule that the harness and not the model runs tools, sandbox controls, and plans written as code.

---

### Module 8 — Agent protocols and agent identity
**Status: complete.** Dossier: `module-08-agent-protocols.md`. 5 phases.

**Question.** Two agents from different vendors need to work together. What can the protocol express, and what does it silently leave to trust?

**Question as built.** Your agent must call another company's agent and a partner's MCP server on behalf of a signed-in user. What does each protocol carry, who is the agent acting as at each hop, and what can you prove afterwards? Phase 5, "The module question, answered", answers it, and it also says what no protocol carries.

**Research brief.**

Topics: MCP, A2A, WebMCP and what each is for. Signed Agent Cards. What the protocols cannot express. Per-agent identity, scoped tokens, and audit records.

Starting points to fetch: the MCP specification at its current revision, the A2A specification and its governing body, and WebMCP. For each, record the revision, the date, and whether it is a standard or a vendor proposal. That distinction matters and is often blurred.

Questions the dossier must answer: what an Agent Card asserts and what verifies it. Whether any of these protocols carries authorization, or only identity. What happens when agent A delegates to agent B on a user's behalf, and where the user's consent is recorded. Whether revocation exists.

This module is where the provenance and short-lived-credential pattern from general infrastructure applies to agents. Check whether any protocol has adopted OIDC-style federation, and say plainly if none has.

Overlap: Module 6 owns the MCP wire format and tool semantics. This module owns identity, delegation and trust between parties. Module 16 owns the attack; this module owns the protocol.

---

### Module 9 — Orchestration, state, and durable execution
**Status: complete.** Dossier: `module-09-orchestration-durable.md`. 6 phases.

**Question.** Your agent crashed halfway through a five-step task that already charged a customer. What resumes, and what must not run twice?

**Question as built.** A refund agent runs for hours, calls payment and email tools, and sometimes hands work to other agents. How do you make every side effect happen once, survive a crash or a deploy, and know when more agents make it worse? Phase 6, "The module question, answered", answers it. Its first steps answer the original question.

Covers single-agent against multi-agent trade-offs, checkpointing, Temporal, Inngest and Restate, idempotency and compensating actions, and human-in-the-loop as architecture.

---

### Module 10 — Memory systems
**Status: complete.** Dossier: `module-10-memory.md`. 6 phases, published 2026-09-25.

**Question.** Your agent remembers something the user corrected last week. Which memory wrote it, and what should have deleted it?

**Question as built.** Your support agent must remember each customer across sessions. What do you store, who writes it, how does a correction or a deletion reach every copy, and how do you prove it helps? Phase 6, "The module question, answered", answers it in nine steps.

**Covered since 2026-09-25.** A taxonomy of memory types: Phase 1 section 1.5, "Memory type names do not match across systems". Time decay: Phase 3 section 3.5, "Time decay hides old facts that are still true". Whether the user can see a contradiction: Phase 3 section 3.6, "Show the customer the change, ask when unsure".

**Research brief.**

Topics: a taxonomy of memory, a comparison of Mem0, Zep and Letta, decay and conflict resolution, memory evals, privacy and deletion.

Starting points to fetch: Mem0, Zep and Letta. For each record the current version, the storage model, and whether memory is extracted by a model or written explicitly. Also fetch any published benchmark each project cites for itself, and read its method, because self-published memory benchmarks usually choose the task.

Questions the dossier must answer: what "memory" means in each system, because the three do not agree. How a contradiction between an old and a new fact is resolved, and whether the user can see it. How deletion works across the store and any derived index. Whether any system can prove a fact was forgotten.

The strongest lab here is a conflict test: write a fact, correct it, and measure whether the corrected fact wins, over how many turns.

Overlap: Module 2 owns the context window within one run. This module owns state across runs. Module 18 owns the legal duty to delete; this module owns the mechanism.

---

## Layer 4 — Evals

### Module 11 — Eval engineering
**Status: complete.** Dossier: `module-11-eval-engineering.md`. 6 phases, published 2026-09-25.

**Question.** Your judge says the new prompt is better. Why should anyone believe the judge?

**Question as built.** Your team claims the new RAG pipeline answers better. What would you need to measure, with what labels and statistics, before you believe it, and what would make the number lie? Phase 6, "The module question, answered", answers it. Its steps 2 and 4 answer the original question.

Covers error analysis first, building LLM judges, validating judges against humans, golden datasets, and CI gates. Do this module early. Modules 12, 17 and 21 all assume a calibrated judge.

---

### Module 12 — Agent evals, online evals, and the improvement loop
**Status: complete.** Dossier: `module-12-agent-evals.md`. 6 phases, published 2026-09-25.

**Question.** A single-turn eval passes and the agent still fails the task. What do you score instead?

**Question as built.** You change the prompt and model of a support agent that takes refunds. How do you know, before and after release, that it got better and did not get worse in ways your tests cannot see? Phase 6, "The module question, answered", answers it. Its steps 1 and 3 answer the original question.

**Research brief.**

Topics: trajectory evals, user simulators, adversarial suites, online scoring, safe rollout, and a three-tier eval stack of cheap rules on every span, a small judge on a sample, and humans on the gold set.

Starting points to fetch: published agent benchmarks that score trajectories rather than final answers, and the scoring code for at least one. Read how partial credit is assigned, because that choice decides the result. Also fetch whatever the major agent frameworks ship for online scoring, and record whether scoring runs inline or offline.

Questions the dossier must answer: what a trajectory eval can detect that an outcome eval cannot, with a worked case. How a user simulator is validated, since an unvalidated simulator moves the target. What sampling rate makes online scoring affordable, with the arithmetic.

Overlap: Module 11 owns judge construction and validation. This module owns what to score for a multi-step agent, and how to run it in production. Module 15 owns the telemetry that carries the scores.

---

## Layer 5 — Infrastructure

### Module 13 — Serving and self-hosting at cluster scale
**Status: complete.** Dossier: `module-13-serving-cluster.md`. 4 phases.

**Question.** At what point does self-hosting beat an API, and what do you take on when it does?

**Research brief.**

Topics: splitting prefill and decode across machines, NIXL, KV cache as shared storage with Mooncake and LMCache, and routing at the serving layer.

Starting points to fetch: NIXL, Mooncake and LMCache. For each record what problem it solves, its current release, and whether it is production or research. Also fetch the current release notes of the main serving engines and the flags that control disaggregated prefill.

Questions the dossier must answer: the arithmetic for when self-hosting is cheaper, and at what utilisation it stops being cheaper. What a cache-aware router needs to know that a normal load balancer does not. What breaks when prefill and decode are on different machines.

Hardware honesty is mandatory here. The learner has an Apple Silicon laptop. Say for every lab where it runs and what it costs. A cluster lab that cannot run locally must be replaced with a simulation that produces the same arithmetic, or labelled as read-only.

Overlap: Module 1 owns single-node serving, batching and the KV cache concept. This module owns what changes when one machine is not enough.

---

### Module 14 — Cost, routing, and AI FinOps
**Status: complete.** Dossier: `module-14-ai-finops.md`. 4 phases.

**Question.** The bill doubled and the traffic did not. Which tenant, which route, and which model change caused it?

**Research brief.**

Topics: gateway options, model choice as a runtime decision, per-tenant metering, budgets, forecasts, and cost ownership.

Starting points to fetch: the current AI gateway options and what each meters. Published routing-cascade results, and whether any reports a control group. Provider pricing pages for the token classes, including cached input and cache write, because those prices change and are the largest single source of wrong cost models.

Questions the dossier must answer: how cost is attributed to a tenant when one request fans out to several models. What a routing cascade actually saves, measured against a control group rather than against an estimate. How a budget is enforced without breaking a request mid-stream.

Overlap: Module 1 already owns the per-request cost model, the token classes, cache break-even and routing against a control group. Read `module-01-coverage.md` carefully before scoping this module. The new material is per-tenant attribution, forecasting, and ownership, not the arithmetic.

---

### Module 15 — Observability and reliability operations
**Status: complete.** Dossier: `module-15-observability-ops.md`. 4 phases.

**Question.** Quality dropped and no alert fired. What should have been recorded at the time?

**Not covered.** Dashboard design. Phase 4, "The module question, answered", step 15 names it as a gap.

**Research brief.**

Topics: tracing pipelines, OpenTelemetry GenAI conventions and their status, dashboards, agent-level telemetry, and incident response for quality failures.

Read the three raw reports first. They are unreviewed.

Starting points to fetch: the OpenTelemetry GenAI semantic conventions at their current status. Record which attributes are stable, which are experimental, and the exact names and units. This is the single most error-prone area in the module, because attribute names change and people invent their own. Check specifically whether a client-side time-to-first-token attribute exists and what unit it uses, before writing any custom name.

Questions the dossier must answer: what a span must carry for a quality incident to be diagnosable afterwards. How an agent trajectory is represented in a trace. What a quality SLO looks like when correctness is judged rather than measured.

Overlap: Module 1 owns the run record, the cost record, and quality SLOs. This module owns the pipeline, the conventions and the incident path.

---

## Layer 6 — Security

### Module 16 — Security and threat modelling
**Status: complete.** Dossier: `module-16-security.md`. 6 phases.

**Question.** A document in the knowledge base tells the model to send another tenant's data. What stops it?

Covers the three-part risk of private data, untrusted content and outbound messages, indirect injection through knowledge-base files, the MCP supply chain, tenant isolation, the OWASP LLM Top 10, the six named agent security designs, CaMeL, and the limits of classifiers.

---

### Module 17 — Guardrails architecture
**Status: complete.** Dossier: `module-17-guardrails.md`. 4 phases.

**Question.** Your classifier adds 300 ms to every request and still misses attacks. What belongs inline, and what belongs after?

**Research brief.**

Topics: layered checks, a fast inline classifier, hazard models, schema validation, asynchronous judges, per-tenant policy, and escalation as a safety control.

Starting points to fetch: the current open guardrail models and their published evaluation, including the false-positive rate. A guardrail's false-positive rate is the number that decides whether it is usable, and vendors report recall instead. Also fetch any published latency figures, with the hardware.

Questions the dossier must answer: which checks are cheap enough to run on every request, with measured latency. What an asynchronous judge can do that an inline one cannot. How a per-tenant policy is expressed and where it is enforced. What happens on classifier failure, open or closed.

Overlap: Module 16 owns the threat model and the architectural defences. This module owns the runtime check layer and its cost. Do not re-teach injection taxonomy.

---

### Module 18 — Compliance and auditability
**Status: complete.** Dossier: `module-18-compliance.md`. 4 phases.

**Question.** A regulator asks you to show why the agent did what it did, nine months ago. What do you hand over?

**Research brief.**

Topics: EU AI Act Article 50 transparency duties, audit logs a reviewer accepts, retention, deletion across memory and vector indexes, and data residency.

Starting points to fetch: the EU AI Act text itself, not summaries, and confirm which articles apply from which date. The README's earlier note that Article 50 applies from 2 August 2026 must be re-verified against the regulation before it is taught.

Questions the dossier must answer: what an audit record must contain to be useful nine months later. How deletion propagates to a vector index and to derived memory, and how it is proven. What data residency means when a model provider is in another region.

Overlap: Module 10 owns the deletion mechanism. Module 15 owns the telemetry. This module owns the duty and the evidence.

---

## Layer 7 — Product

### Module 19 — Agent product design and human approval
**Status: complete.** Dossier: `module-19-agent-product.md`. 4 phases.

**Question.** Which actions can the agent take alone, and what must the approval screen show for the approval to mean anything?

**Research brief.**

Topics: reads run freely and writes need review, approval screens that show the payload, confidence-gated routing, and the gradient from suggest to confirm to execute.

Starting points to fetch: published human-in-the-loop designs from shipped agent products, and any research on approval fatigue. The interesting failure is an approval step that people click through, which makes it worse than no step because it moves the blame without reducing the risk.

Questions the dossier must answer: what the approval screen must show for consent to be informed. How confidence is calibrated well enough to gate on. What the measured click-through rate is on approval prompts, if anyone has published one.

Overlap: Module 9 owns human-in-the-loop as an architecture and a durable-execution concern. This module owns the interface and the decision policy.

---

### Module 20 — Voice agents in production
**Status: complete.** Dossier: `module-20-voice-agents.md`. 4 phases.

**Question.** Where does the one-second budget go, and what do you give up to stay inside it?

**Research brief.**

Topics: the latency budget under one second, speech-to-speech against chained pipelines, cost per minute, interruption handling, and telephony.

Starting points to fetch: current speech-to-speech model pricing and latency, current chained-pipeline components, and telephony integration constraints. Record cost per minute for both paths with the same assumptions.

Questions the dossier must answer: the full latency budget, broken down by stage, for both architectures. How interruption is detected and what it costs to support. What telephony adds that a browser does not, including codec and jitter.

Overlap: Module 1 owns streaming and time-to-first-token. This module owns the audio path and the real-time budget.

---

### Module 21 — Post-training, distillation, and small models
**Status: complete.** Dossier: `module-21-post-training.md`. 4 phases.

**Question.** You have tried prompting and retrieval. How do you know fine-tuning is the next step, and how do you know it worked?

**Covered since 2026-09-25.** Running a small model on a phone or other device: Phase 3 section 3.6, "On a phone, the app's memory limit decides the fit". It covers the memory fit, the runtimes and their adapter paths, and published on-device speed.

**Research brief.**

Topics: the decision order of prompt, retrieval, fine-tune, distill. LoRA and QLoRA. Dataset curation. Eval-gated training. Agent reinforcement fine-tuning. Small models on devices.

Starting points to fetch: current LoRA and QLoRA tooling and its hardware requirements, and any published comparison of fine-tuning against retrieval on the same task. The decision order matters more than the technique, and it is the part usually skipped.

Questions the dossier must answer: the measured conditions under which fine-tuning beats retrieval. What dataset size is actually needed, with a source. How a training run is gated on evals so a regression cannot ship.

Hardware honesty again. State what fits on an Apple Silicon laptop and what does not, with the memory arithmetic.

Overlap: Module 11 owns the eval gate. This module owns the training decision.

---

### Module 22 — Electives
**Status: not started (planned).** Sized per topic.

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
| `module-02-coverage.md`, `module-03-coverage.md` | what Modules 2 and 3 teach, section by section |
| `module-NN-<slug>.md` | one research dossier per module, for Modules 2 to 21 |
| `raw-research/` | unreviewed helper reports from earlier research runs, for Modules 4 and 15 |

## What is not decided

- The phase count for each Module 22 elective. Size it after research, not before.
- Topic slugs for new electives. Each built module's slug is its folder name in the top-level `README.md`.
- Whether Module 22's electives stay one module or become numbered modules.

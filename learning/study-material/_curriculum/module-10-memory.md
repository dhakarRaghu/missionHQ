# Module 10: Memory systems

Research date: 2026-09-23. Status: research dossier, not course material. Reviewed on 2026-09-23 by an independent reviewer. Section 13, Review log, lists every correction. Corrections are also made in the text above it.

Module question: **Your support agent must remember each customer across sessions. What do you store, who writes it, how does a correction or a deletion reach every copy, and how do you prove it helps?**

This question replaces the draft question in `_curriculum/README.md`, "Your agent remembers something the user corrected last week. Which memory wrote it, and what should have deleted it?". The README question is still answered, in section 1 and in 4.2, 4.3, 4.4 and 4.7.

## How this dossier was built

- **Inputs.** Three research reports written on 2026-09-23 in `scratchpad/reports/`: `research_memory_architectures.md`, `research_memory_failures.md` and `research_memory_design.md`. Below they are the architectures report, the failures report and the design report.
- **Path short names.** `RM/` means `scratchpad/research_memory/`. The three topic folders are `RM/architectures/`, `RM/failures/` and `RM/design/`. `M0/` means `RM/architectures/src/mem0-2.1.0/`, the Mem0 source at GitHub tag `v2.1.0`. `W/` means `RM/failures/pypi/mem0ai/mem0/`, the `mem0ai` 2.1.0 wheel from PyPI. `G/` means `RM/architectures/src/graphiti-0.30.2/graphiti_core/`. `L/` means `RM/architectures/src/letta-0.16.8/letta/`. `P/` means `RM/architectures/papers/`. `D10/` means `scratchpad/dossier_m10/`, the dossier author's notes.
- **Other inputs.** The Module 10 brief in `_curriculum/README.md`, lines 223 to 238. The Module 10 section of `scratchpad/reports/curriculum_audit.md`, lines 296 to 328. The rules in `scratchpad/briefs/BRIEF_research.md`, `research-method.md` and `writing-style.md`. The structure of `_curriculum/module-08-agent-protocols.md`.
- **Work done for this dossier.** No lab ran. No URL was fetched. The dossier author did four read-only things:
  1. Re-grepped 106 anchors of section 4 in their saved files. Script `D10/anchor_check.py`, output `D10/anchor_check.txt`. Section 12 has the result.
  2. Read source files at their tags to settle line numbers and two conflicts. Section 7.
  3. Read `RM/failures/pypi/mem0ai.json` for the release dates of `mem0ai` 1.0.0, 2.0.0b0, 2.0.0 and 2.1.0.
  4. Did the arithmetic for two rows of the cost table that the prototype does not have. Script `D10/extra_rows.py`, output `D10/extra_rows.txt`. This is arithmetic on stated assumptions. It is not a measurement.
- **Labels.** Every claim is **verified**, **verified by run**, **inferred** or **not checked**. A verified claim names its file and line, or its table. "Verified by run" means a research agent ran a script on 2026-09-23 on the learner's Apple arm64 Mac, and the output file is named. An inferred claim names its basis and the check that would confirm it. **Vendor claim** marks a number that a company published about its own product or about a rival.
- **Run conditions for every lab number.** Python 3.12.14 and SQLite 3.53.1, from `RM/failures/proto/deletion_audit.out` line 1. Embedding runs used `sentence-transformers` 6.1.0, `torch` 2.14.0 and `transformers` 5.17.0 from the shared harness pins, on CPU, with `all-MiniLM-L6-v2` and `bge-small-en-v1.5` already cached. The Mem0 probe used `mem0ai` 2.1.0 with `infer=False`, a local `all-MiniLM-L6-v2` embedder and local Qdrant. `fastembed` and spaCy were not installed, so BM25 and entity scoring were off, from `RM/failures/proto/mem0_leak_probe.out` lines 2 to 4. The reports do not record machine load. Not checked.
- **Terms used in the whole dossier.**
  - **Memory**: state that an agent keeps across sessions and reads back in a later session. State inside one run is context, owned by Module 2.
  - **Session**: one conversation with one customer. A new session usually starts with a cold prompt cache.
  - **Writer**: the component that decides what enters memory. It can be the agent model through a tool, an extractor model in your app, a background agent, or your code.
  - **Extractor**: a model call that turns conversation turns into short facts.
  - **Recall path**: how memory reaches the answering model. Always in the prompt, app-side search before the call, a search tool the model calls, or a lookup by key.
  - **Core memory block**: a Letta text block that is rendered into the system prompt on every call.
  - **ADD-only**: a write path that only inserts new facts and never updates or deletes an old one.
  - **Invalidation**: marking an old fact as no longer true, with a time, without deleting it.
  - **Event time**: when a fact was true in the world. **Ingestion time**: when the system learned it.
  - **Derived copy**: any stored item made from a source turn. Examples are an extracted fact, a history row, an entity summary, a graph edge and a vector.
  - **Lineage**: a stored link from each derived copy to the source turns it came from.
  - **Scope key**: a field such as `user_id` that a memory API uses to filter records.
  - **Full context**: the answering model reads the whole conversation history.
  - **J score**: the LLM-as-a-judge accuracy that the Mem0 paper uses on LoCoMo.

---

## 1. What this module is for

Module 2 teaches context inside one run. Module 3 teaches how a vector index stores and deletes. This module covers state that outlives a session: what a memory system writes, how it reads it back, and what happens when the customer corrects or deletes something.

The short answer: **a memory store is a derived index of the conversation, not the record of truth.** The three open-source systems write in three different ways. None of them makes a correction or a deletion reach every copy by default.

| Part of the question | Short answer | Where |
|---|---|---|
| What do you store | Raw turns as the value. Extracted facts as extra search keys. Facts as the only value lose accuracy, and user-only extraction drops what the assistant promised | 4.12, 4.13 |
| Who writes it | One of four writers: the agent model through a tool, an extractor in your app, a background agent, or your code. Background writing removes latency from the customer's wait. It does not remove cost | 4.1, 4.14 |
| How a correction reaches every copy | It does not, by default. Mem0 2.x keeps both facts and lets ranking decide. Graphiti marks the old fact invalid and still returns it. Letta overwrites exact text in a block | 4.2, 4.3, 4.4, 4.5 |
| How a deletion reaches every copy | It does not, by default. An API delete leaves history rows, message buffers, entity summaries and free database pages. Two of three hosted assistants keep derived memory after the chat is deleted. You need lineage from each copy to its source | 4.7, 4.8 |
| How a scope keeps customers apart | A scope key is a filter your code must always pass. It is not an isolation boundary | 4.9 |
| How you prove it helps | Measure on your own traffic, at your history length, with your model, against full context and against retrieval over raw turns. Published memory scores depend on the judge, the answer key and who ran them | 4.10, 4.11, 4.15, 4.16, 4.17 |

Answer to the README question. The memory that wrote the stale fact is the one whose writer never replaces facts: Mem0 2.x adds, Graphiti invalidates but still returns. What should have deleted it is a write path that follows lineage from the correction to every derived copy. No system checked here does that by itself.

Summary: memory is a derived index with its own writer, and every correction and deletion must be pushed to each copy by your code.

## 2. Scope

### In scope

- What "memory" means in Mem0, Zep and Graphiti, Letta, LangMem and the LangGraph store, the Anthropic memory tool, Claude Code auto memory, and three hosted assistants.
- Who writes memory, when, and what each writer costs per turn.
- The four recall paths and their per-turn cost.
- Conflict resolution: ADD-only, overwrite, invalidation with timestamps, and read-time rules.
- Event time and ingestion time.
- Deletion across derived copies, and lineage.
- Scope keys and their defaults.
- When memory beats full context, and when it does not.
- Memory benchmarks: what they measure, their answer keys, their judges, and the vendor disputes.
- Versions and defaults on 2026-09-23.

### Out of scope, and the owner of each item

| Topic | Owner |
|---|---|
| Prompt caching: token classes, cache write and cache hit prices, implicit and explicit caching | Module 1. Built sections 3.1, 3.2 and 3.3 |
| Context cost inside one run, cache breaks, compaction, notes an agent writes inside one run | Module 2. Built sections 2.1, 2.2, 2.5, 3.1 to 3.4, 4.3 |
| Vector index internals, hybrid ranking, RRF, reranking | Module 3. Built sections 5.1 to 5.3 |
| Deleted vector bytes that stay in index files | Module 3. Built section 7.3, "Deleted is not gone" |
| Entity graphs as a retrieval method, GraphRAG cost | Module 4. Built sections 5.1 to 5.5 |
| Per-tenant index placement and the filter-leak lesson | Module 4. Built section 7.5, "A filter bug leaks, a separate index does not" |
| Session stores, conversation history as run state, durable state, checkpoints | Module 9. Built phases 1 to 6. The OpenAI Agents SDK "session memory" is a session store and belongs here |
| Judge construction, judge bias, judge validation, eval sample size and paired statistics | Module 11, `_curriculum/module-11-eval-engineering.md` sections 4.2 to 4.6. Planned Phase 2, sections 2.2 and 2.3. Phase 3, sections 3.1 to 3.5. Phase 5, sections 5.1 to 5.4, per `eval-engineering/course.json` `conceptOwnership` |
| Broken public benchmarks, and why a public score does not predict product quality | Module 11, dossier 4.9, planned Phase 6, section 6.4. Module 10 keeps only the memory-benchmark facts in 4.15 and 4.16 |
| Memory poisoning, prompt injection that persists through memory, the Graphiti Cypher injection fix | Module 16, `_curriculum/module-16-security.md` lines 14, 192 and 207 |
| The legal duty to delete, retention, audit records a reviewer accepts | Module 18, per `_curriculum/README.md` line 368 |
| Online evals on live traffic, A/B tests, judge cost times sample rate | Module 12, planned, per `eval-engineering/course.json` `keptOut`. "How do you prove it helps" in this module stops at offline replay |

### Overlap with built modules

Headings were read with `grep '^## '` on `context-engineering/*.md`, `retrieval-internals/*.md`, `advanced-retrieval/*.md`, `orchestration-durable/*.md` and `agent-protocols/*.md` on 2026-09-23. The reviewer added `inference-internals/*.md` and `agent-harness/*.md` on the same day, and the Module 11 plan in `eval-engineering/course.json`. Handoffs to this module are verified in three dossiers: `module-02-coverage.md` line 532 defers "Memory across sessions and users" to Module 10. `module-04-advanced-retrieval.md` line 59 hands "Memory across sessions, temporal knowledge graphs such as Zep and Graphiti" to Module 10. `module-09-orchestration-durable.md` line 55 hands "Long-term memory stores" to Module 10.

| Built heading | What it owns | What this module adds |
|---|---|---|
| Module 2, "2.1 — Every step re-reads the whole history" | Per-step cost of history inside one run | The cold cache at the start of a new session, 4.11 |
| Module 2, "2.2 — A cache break costs one rewrite, or one per step" | The cache-break cost model | 4.6 cites it for a core-memory edit. Do not re-teach |
| Module 2, "3.2 — Judge a summary by the next steps, not by reading it" and "3.4 — Each compaction is a paid call and a loss event" | Summary loss inside one run | The rolling-summary row of section 5 across sessions. Link 3.4 |
| Module 2, "4.3 — A note the agent wrote is an input you must check" | Notes and path checks inside one run | Notes across sessions and across customers, 4.1 and 4.9 |
| Module 2, "4.4 — Measure whether length is your problem at all" | Length diagnosis | Link it before 4.10 |
| Module 3, "5.2 — RRF: k decides how much the top ranks count" | RRF | Graphiti's default search uses RRF. Link 5.2 in 4.4 |
| Module 3, "6.3 — Chunk or not matters more than where you cut" | Chunk granularity | Round against session as the stored value, 4.12 |
| Module 3, "7.3 — Deleted is not gone" | Vector bytes after a soft delete | Deletion across history rows, message buffers, entity summaries and graph edges, 4.7. Link 7.3 for the vector part |
| Module 4, "5.1" to "5.5", entity graphs | Graphs for retrieval | Temporal validity and invalidation of facts, 4.4 and 4.5 |
| Module 4, "7.5 — A filter bug leaks, a separate index does not" | Filter leaks between tenants | The memory API's own scope defaults, 4.9. Link 7.5 |
| Module 4, "6.4 — A shared cache is a channel between tenants" | Cache leaks | Not repeated |
| Module 9, "4.1 — A saved state is a snapshot, not a lock" | Durable run state | Memory is not run state. One line in 4.1 |
| Module 1, "3.1 — The five token classes, and two multipliers", "3.2 — Implicit prefix caching" and "3.3 — Explicit caching with cache_control" | Cache write and cache hit prices, and how a prefix cache works | 4.6 and 4.11 use the cache prices as inputs. Link 3.1 and 3.3. Do not re-teach cache pricing |
| Module 1, "2.6 — The context budget and the compaction trigger" | Context budget inside one request | Not repeated |
| Module 2, "2.5 — Pruning costs a rewrite, so it has a break-even" | Break-even arithmetic for a cache rewrite inside one run | 4.11 uses the same kind of break-even across sessions. Link 2.5 |
| Module 4, "2.1 — The whole corpus costs more per query, even cached" | Whole corpus in the prompt against retrieval, with caching | 4.11 is the same trade for one customer's history. Link 2.1 and teach only the cold first turn of a new session |
| Module 3, "1.3 — A benchmark does not predict your corpus", and Module 4, "1.3 — A text-to-SQL score also measures the gold labels" and "1.4 — Execution accuracy is a match rule you choose" | The general lesson that a score depends on the gold labels and the match rule | 4.15 and 4.16 give only the LoCoMo facts. Link these sections |
| Module 7, agent-harness "1.1 — The model proposes, the harness runs the tool call" | Client-side tool execution | The Anthropic memory tool is one case of it, 4.1. Link 1.1 |
| Module 9, "6.1 — A handoff keeps the facts and drops the rules" | Handoff inside one workflow | Not repeated |
| Module 8, all phases | Identity and delegation across agents | No overlap. Memory scopes are not identity |

---

## 3. What changed recently

| Date | Change | Source | Why it matters |
|---|---|---|---|
| 2025-04-10 | ChatGPT references all past chats, not only saved memories | OpenAI memory post, read in a browser. Design report 3 | Hosted memory became retrieval over raw history plus a derived layer |
| 2025-04-21 | Letta sleep-time agents, Letta 0.7.0 | Letta blog. Design report 2.3 row 5 | A background writer became a product default |
| 2025-04-28 | Mem0 paper, arXiv 2504.19413. Full context is most accurate on LoCoMo. Memory is much faster | `P/2504.19413.txt` Table 2 | The main measured trade-off of this module |
| 2025-05-06, updated 2026-06-03 | Zep blog re-runs Zep on LoCoMo: 75.14 against the 65.99 Mem0 reported | `RM/failures/zep_lies.txt` | Who runs the benchmark changes the winner |
| 2025-05-08 | zep-papers issue #5 by Mem0: Zep at 58.44% | `RM/failures/zep_issue5.txt` | A counter re-run over category-5 accounting |
| 2025-08-12 | Letta blog: a filesystem agent scores 74.0% on LoCoMo with gpt-4o-mini | `RM/failures/letta_bench.txt` | A plain file plus search is a baseline every memory system must beat |
| 2025-09 | LongMemEval cleaned data released | Design report 2.6 row 3 | Pin the cleaned files |
| 2025-09-11, 2025-10-23 | Claude memory for Team and Enterprise, then Pro and Max | Claude blog. Design report 2.5 | Project-scoped memory in a hosted assistant |
| 2025-09-29 | Anthropic memory tool `memory_20250818` | Design report 2.3 row 8 | Model-written, client-stored memory in the API |
| 2025-10-16 | `mem0ai` 1.0.0. It still has the ADD, UPDATE, DELETE and NOOP decision call | `RM/failures/pypi/mem0ai.json`. Design report 2.2 row 8 | The last design most tutorials describe |
| 2026-01-28 | mem0 issue #3944: ingestion date stored as the event date | `RM/failures/mem0_issue3944.txt` | Event time and ingestion time fail in practice |
| 2026-03-11 | Graphiti v0.28.2, "SECURITY: Harden Search Filters Against Cypher Inj", title only | `RM/architectures/runs/gh_releases_2026-09-23.txt` | Module 16 owns it |
| 2026-04-08 | LoCoMo audit, `dial481/locomo-audit`: 6.4% wrong gold answers. The judge accepted 62.81% of vague but on-topic wrong answers, and 10.61% of specific wrong answers | `RM/failures/locomo_audit_README.md` lines 9, 12 and 37. `RM/failures/penfield.txt` | The answer key and the judge move the score |
| 2026-04-14 | Mem0 changelog "SDK v2.0.0 / v3.0.0": ADD-only extraction | `M0/docs/changelog/highlights.mdx` line 234 | Corrections are no longer resolved at write time |
| 2026-04-16 | `mem0ai` 2.0.0 on PyPI. Pre-release 2.0.0b0 on 2026-04-13 | `RM/failures/pypi/mem0ai.json` | The first PyPI release with ADD-only |
| 2026-04-27 | Graphiti v0.29.0: opt-in single-call node and edge extraction. "Defaults are unchanged" | `RM/architectures/gh/graphiti_v0.29.0.json` | Ingestion cost can drop, only if you opt in |
| 2026-05-14 | Letta 0.16.8, the last memory-server release | `RM/architectures/runs/letta_pypi_history.txt` line 58 | The pin for server labs |
| 2026 | MemoryAgentBench and BEAM published at ICLR 2026 | `RM/failures/2507.05257.txt` and `2510.27246.txt`, line 2 of each | Peer-reviewed forgetting and contradiction tests |
| 2026-07-24 | Ground Truth First, arXiv 2607.21962, preprint | Failures report 2.4 | Rankings may flip between 3 and 9 weeks of history. One author |
| 2026-09-08 | `graphiti-core` 0.30.2 | `RM/architectures/runs/pypi_versions_2026-09-23.txt` | The pin |
| 2026-09-09 | End of Claude legacy-memory export | Design report 2.5 | Vendors migrate memory formats |
| 2026-09-17 | PyPI `letta` 0.32.13 ships Letta Code, a terminal agent | `RM/architectures/pypi/letta_0.32.13.json` | `pip install letta` now installs a different product |
| 2026-09-18 | `mem0ai` 2.1.0 | `RM/failures/pypi/mem0ai.json` | The pin |
| About 2026-09-19 | OpenAI memory help page rewritten: improved and legacy memory, regulated-workspace rules | Design report 2.5, read in a browser | Current deletion rules for ChatGPT |

---

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Each concept gives one best piece of evidence first, with its conditions. Supporting evidence follows. Every quote and number in a "Best evidence" line was re-grepped in its saved file. Section 12 gives the counts.

### 4.1 "Memory" is not one thing. Each system has a different writer and a different recall path, and the recall path sets the per-turn cost

- **Best evidence, verified.** Letta 0.16.8 writes every attached block into the system prompt on each call, under `<memory_blocks>`, with `chars_current` and `chars_limit` per block. `L/schemas/memory.py` lines 149 to 165. Mem0 2.1.0 writes through one extractor call in your app's `add()`, `system_prompt = ADDITIVE_EXTRACTION_PROMPT`, `M0/mem0/memory/main.py` line 942. Your app reads with `search()`, default `top_k: int = 20`, line 1383.
- **Verified.** The Anthropic memory tool is client-side: "The memory tool operates client-side". The model issues file commands and your code runs them. `RM/architectures/docs/anthropic_memory_tool.md` line 11. Type `memory_20250818`. The Module 7 note on this is now re-checked and holds.
- **Verified.** Claude Code auto memory loads "The first 200 lines of `MEMORY.md`, or the first 25KB" at the start of every conversation. Topic files are read on demand. `RM/architectures/docs/claude_code_memory.md`.
- **Verified.** Letta's sleep-time agent writes blocks in the background every 5th turn by default, `sleeptime_agent_frequency=5`, `L/server/server.py` line 784.

| System, version | Who writes | When | Recall path | Model calls added |
|---|---|---|---|---|
| Letta 0.16.8 core memory | The agent model, with `core_memory_append`, `core_memory_replace` and `memory_*` tools | Inside the turn | Always in the prompt | One tool round trip per edit |
| Letta 0.16.8 archival | The agent model, `archival_memory_insert` | Inside the turn | The model calls `archival_memory_search`, default `top_k` 10 | One round trip per search |
| Letta 0.16.8 sleep-time agent | A second agent | Every 5th turn by default | Writes blocks | One agent run per trigger |
| Mem0 2.1.0 OSS | An extractor model in your `add()` call | When your app calls `add` | Your app calls `search` before the model call | 1 LLM call plus embeddings per `add`. 0 LLM calls per default `search` |
| Graphiti 0.30.2 | Extractor model calls in `add_episode` | When your app ingests an episode | Your app calls `search`: BM25 plus cosine, fused with RRF | Several LLM calls per episode. Count not measured. 0 per default search |
| LangMem 0.0.30 | An extractor model, often delayed with `ReflectionExecutor` | After the conversation | LangGraph `store.search` | 1 or more per extraction |
| Anthropic memory tool | The Claude model, through tool calls | Inside the turn | The model calls `view` on `/memories` | One round trip per operation |
| Claude Code auto memory | The Claude model, with file tools | Inside the session | `MEMORY.md` index at start, topic files on demand | File tool calls |

Row evidence: architectures report C4 and 2.2 to 2.7, with file and line for each row. The LangMem row is verified at `src/langmem-0.0.30/src/langmem/knowledge/extraction.py` lines 540 to 544 and `reflection.py` line 60, per the architectures report 2.5. Not re-grepped by the dossier author.

- **Naming trap, verified.** The OpenAI Agents SDK calls its conversation store "session memory". It stores history, not extracted facts. `SessionSettings(limit=None)` fetches all history. `RM/architectures/docs/openai_agents_sessions.md` lines 3 and 114. Module 9 owns it.
- **Not checked.** ChatGPT's write mechanism. LangChain docs say it "uses a save_memories tool". OpenAI's own help page names no tool. Design report 2.3 row 4.

### 4.2 A correction does not replace the old fact. Mem0 2.x only adds

- **Best evidence, verified.** The Mem0 2.1.0 extraction prompt says "Your sole operation is ADD". `M0/mem0/configs/prompts.py` line 472. The docs say "The automatic extraction path is additive." `M0/docs/core-concepts/how-it-works.mdx` line 51. Status: source and docs at tag `v2.1.0`, released 2026-09-18.
- **Verified.** The changelog entry dated 2026-04-14 says: "ADD-only extraction: Memories accumulate; nothing is overwritten or deleted." `M0/docs/changelog/highlights.mdx` line 234. The migration guide says: "Retrieval handles ranking". `RM/failures/mem0_migration.md`.
- **Verified, added by the reviewer.** The same docs line names the fix path: "Use explicit `update` or `delete` operations when your application needs to correct or remove a memory." `M0/docs/core-concepts/how-it-works.mdx` line 51. So in Mem0 2.x a correction reaches the store only if your code calls `update` or `delete`. Whether `update` also leaves the old text in the history table is not checked. Check: read `_update_memory` in `W/memory/main.py`.
- **Verified.** Dedup is an exact MD5 hash of the fact text, `hashlib.md5(text.encode())`, `M0/mem0/memory/main.py` line 1020. Two paraphrases are both stored.
- **Verified.** The prompt asks the extractor to record a change with what it replaced: "the memory MUST capture the transition". `prompts.py` line 612. So the new fact may name the old value. Whether that helps ranking is not checked.
- **Verified. This is a change.** The 2025 Mem0 paper describes ADD, UPDATE, DELETE and NOOP, `P/2504.19413.txt`. `mem0ai` 1.0.0 made two calls: extraction, then the decision. Design report 2.2 row 8, from `main.py` lines 434 and 502 at tag v1.0.0. Not re-grepped by the dossier author.
- **Verified.** The Mem0 paper's answer prompt moves conflicts to read time: "If the memories contain contradictory information, prioritize the most recent memory". `P/2504.19413.txt` line 999.
- **Contrast, verified.** Letta `core_memory_replace` is exact string replacement done by the model. "To delete memories, use an empty string for new_content." `L/functions/function_sets/base.py` line 265. LangMem `create_memory_manager` defaults to `enable_updates=True` and `enable_deletes=False`, architectures report 2.5.

### 4.3 With both facts stored, the correction wins only if ranking prefers it. Similarity ranking usually prefers the old fact

- **Best evidence, verified by run.** `RM/failures/proto/conflict_rank.out`. Twenty old-fact and correction pairs, written by the failures agent, one question each. Both facts stored, ranked by cosine similarity with no time term. `all-MiniLM-L6-v2`: the correction ranked first in "full 6/20 (mean margin -0.048), terse 0/20 (mean margin -0.315)". `bge-small-en-v1.5`: "full 7/20 (mean margin -0.016), terse 0/20 (mean margin -0.168)". Conditions: "full" corrections repeat the slot words, such as "home address". "Terse" corrections are natural, such as "The user moved to 45 Lake Road". No bge query prefix, normalized embeddings, CPU, run time 6.0 s. The pairs are author-written, n = 20.
- **Verified.** Mem0 2.1.0 ranking has no time term: `combined = (semantic + bm25 + entity_boost) / max_possible`, `W/utils/scoring.py` line 72. The word "recency" has 0 hits in that file. Decay is a Platform feature: "The decay parameter is not supported by the OSS Memory SDK." `W/memory/notices.py` line 134.
- **Vendor claim, verified.** Mem0's own page: "Knowledge update (93.6) remains the hardest category for an additive, ADD-only architecture". `M0/docs/core-concepts/memory-evaluation.mdx` line 99. Mem0 Platform, top-200 retrieval, model not named. Reviewer check: the same page's table gives multi-session 88.0, line 95, which is lower than 93.6. So "hardest" is the vendor's wording, and its own table does not support it. Teach the 93.6 as a vendor number only.
- **Verified by run, toy embedder.** `RM/architectures/lab/correction_race.py` with a bag-of-words cosine. The correction "User now lives in Seattle" still loses, "scores: [0.258, 0.2]", because the old fact says "Austin" twice. `RM/architectures/runs/lab_correction_race_reworded.txt` line 1.
- **Inferred, not run.** BM25 or a recency term may rescue terse corrections. A recency term that always favours the newest fact would break questions about the past, such as "Where did the customer live before?". Check: the break-it in lab A of section 6.
- **Where it does not hold.** With a supersede flag, the correction wins 20 of 20 by construction, `conflict_rank.out`. A write path that marks the old fact removes the ranking race.

### 4.4 A temporal graph marks the old fact invalid. It does not delete it, and the default search still returns it

- **Best evidence, verified.** Graphiti 0.30.2 sets `edge.invalid_at = resolved_edge.valid_at` and sets `expired_at` to now. It keeps the edge. `G/utils/maintenance/edge_operations.py` lines 569 to 570. `Graphiti.search()` passes `SearchFilters()` when the caller gives none, `G/graphiti.py` lines 1639 and 1684. Every date filter defaults to `None`, `G/search/search_filters.py` lines 62 to 65.
- **Verified.** So the reader gets both facts, each with its dates. The Zep paper's context template says: "These are the most relevant facts and their valid date ranges". `P/2501.13956.txt` line 214.
- **Verified, corrected by the reviewer.** Contradiction detection is at most one LLM call per new edge, `resolve_extracted_edge`, `model_size=ModelSize.small`, `G/utils/maintenance/edge_operations.py` lines 623 and 726 to 730. The call is skipped when the edge has no related edges and no invalidation candidates, line 653, and when the same fact text already exists between the same nodes, the "Fast path" at line 684.
- **Verified.** Default search is BM25 plus cosine fused with RRF, `DEFAULT_SEARCH_LIMIT = 10`, `G/search/search_config.py` line 29. No LLM call. Link Module 3, 5.2 for RRF.
- **Verified by run, toy model.** `RM/architectures/runs/lab_correction_race_default.txt`: "reader ignores dates -> User lives in Austin ...". "reader honours dates -> User moved to Seattle last week".
- **Not checked.** Whether an expired edge ranks below the current one in a real Graphiti run. Check: run 0.30.2 with Kuzu or FalkorDB and fake LLM clients.

### 4.5 Every fact has two times: when it was true, and when the system learned it. Invalidation needs the first

- **Best evidence, verified.** The Zep paper: "t′created and t′expired ∈T ′ monitor when facts are created or invalidated in the system", while `tvalid` and `tinvalid` track when facts held true. `P/2501.13956.txt` line 155, section 2. Code fields `valid_at`, `invalid_at`, `expired_at`, `reference_time`, `G/edges.py` lines 271 to 282, per the architectures report 2.4.
- **Verified.** Graphiti invalidates an older edge only when both edges have `valid_at`. The branch requires `edge_valid_at_utc is not None and resolved_edge_valid_at_utc is not None`. `G/utils/maintenance/edge_operations.py` lines 563 to 567. If the extractor finds no event time, the old fact stays valid.
- **Verified that the report exists.** mem0 issue #3944, opened 2026-01-28, label `bug`: the Mem0 Platform stored a 2023 LoCoMo event as "in early January 2026". The system used the ingestion date. `RM/failures/mem0_issue3944.txt`. Root cause not checked. No maintainer answer was read.
- **Verified.** LongMemEval time-aware query expansion raised recall by 11.3% with rounds and 6.8% with sessions. An LLM extracts a time range from the query, then filters by date. `RM/design/2410.10813.txt`, section 5.4, per the design report 2.2 row 4. Not re-grepped by the dossier author.

### 4.6 Core memory in the prompt is paid on every call, and each edit rebuilds the system prompt

- **Best evidence, verified.** Letta 0.16.8 lists `"value"` in `PROMPT_AFFECTING_BLOCK_FIELDS`, `L/services/block_manager.py` line 32. A change calls `_rebuild_system_prompts_for_connected_agents`, line 268, for every agent attached to the block. The agent loop says: "We skip system prompt refresh during normal steps to preserve prefix caching." It adds: "The system prompt is only rebuilt after compaction or message reset." `L/agents/letta_agent_v3.py` lines 966 to 967.
- **Verified.** Default block limits: `CORE_MEMORY_PERSONA_CHAR_LIMIT: int = 20000` and `CORE_MEMORY_HUMAN_CHAR_LIMIT: int = 20000`, `L/constants.py` lines 433 to 434. Inferred: two full default blocks are about 10,000 tokens on every call, at about 4 characters per token. Not checked with a tokenizer.
- **Inferred, not run.** An edit changes the start of the cached prefix. So the next request that uses the rebuilt system message pays a cache write for the whole prompt. Module 2, 2.2 owns the cost model. Check: run a Letta 0.16.8 server with a cache-reporting provider and compare cache-read tokens before and after one `core_memory_replace`.
- **Open, not settled by reading.** The stored system message is rebuilt on each edit, but the V3 loop skips the refresh in normal steps. So the model may not see its own edit until compaction or a reset. Check: the same server run, printing the system message sent on the next step.
- **Dossier author arithmetic, section 5.** A 2,000-token block costs $0.0086 per turn when unchanged and $0.0262 on an edit turn, Claude Sonnet 5 prices of 2026-09-23. `D10/extra_rows.txt`.

### 4.7 A delete through the memory API leaves copies in stores the API does not describe

- **Best evidence, verified by run.** Real `mem0ai` 2.1.0, `infer=False`, local Qdrant. After `delete()`, `get_all` returned nothing and the Qdrant files held 0 copies of "Oak Street". The history table still held the text: "history rows for deleted id: [('ADD', None, 'My home address is 12 Oak Street, Pune.', 0), ('DELETE', 'My home address is 12 Oak Street, Pune.', None, 1)]". `RM/failures/proto/mem0_leak_probe.out`. Run within about 1 minute. `MEM0_TELEMETRY=False` must be set, or the run sends events. Reviewer note: the same output prints "messages rows: []". With `infer=False` the probe wrote nothing to the message buffer, so the probe does not show the buffer copy. The next two bullets rest on reading the code. The log also shows a Hugging Face Hub request warning, so the run was not fully offline.
- **Verified.** `_delete_memory` writes `old_memory = prev_value`, the deleted text, with `event = "DELETE"`. `W/memory/main.py` lines 2100 to 2126. The history file defaults to `~/.mem0/history.db`, `W/configs/base.py` lines 42 to 45.
- **Verified.** Mem0 keeps the last 10 raw messages per scope, `ORDER BY created_at DESC LIMIT 10`, `W/memory/storage.py` line 286. `delete()` and `delete_all()` do not touch that table. Only `reset()` drops it, `storage.py` line 334. Reviewer check: `main.py` `delete()` at line 1869 and `delete_all()` at line 1890 have no call into the messages table. The only `DELETE FROM messages` in `storage.py` is the trim to 10 rows at line 284.
- **Verified.** Graphiti `remove_episode` deletes an edge only if the removed episode is the edge's first episode: `if edge.episodes and edge.episodes[0] == episode.uuid`, `G/graphiti.py` line 1834. It does not recompute kept node summaries. Inferred from the code path: text from a deleted episode can survive in an entity summary. Check: a run on a graph database.
- **Verified by run.** `RM/failures/proto/deletion_audit.py`, standard library and numpy, 0.19 s. Five copies: a raw message, a fact, a history row, an entity summary and a vector snapshot. After the API delete, `memories` is 0 and every other table still matches: "rows still matching: {'messages': 1, 'memories': 0, 'history': 2, 'entities': 1}". "Oak Street" byte hits in the SQLite file: 5 with `secure_delete` off, 4 with it on, 4 after `VACUUM`. The 4 are live rows. The pre-delete vector snapshot still holds the vector. SQLite 3.53.1, Python 3.12.14.
- **Verified.** Mem0 telemetry is on by default and sends an unsalted MD5 of `user_id` to `HOST = "https://us.i.posthog.com"`. `W/memory/telemetry.py` line 16, `W/memory/utils.py` line 244. Inferred: an MD5 of a guessable ID, such as an email address, can be reversed by guessing.
- **Link.** Module 3, 7.3 for vector bytes after a soft delete. Not repeated here.
- **Not checked.** Any system that can prove a fact was forgotten. None of the three reports found a deletion receipt or proof in Mem0, Graphiti or Letta. The deletion audit above is the method a course can teach.

### 4.8 Deleting the source conversation does not delete memory derived from it, in two of three hosted assistants. Lineage is the fix

- **Best evidence, verified.** Claude Help Center: "When a conversation expires or is deleted, related memory entries generated from it won't be removed". `RM/design/claude_memory_help.txt` line 529. Fetched 2026-09-23.
- **Verified.** ChatGPT Help Center: "Deleting a chat alone does not necessarily delete a separate saved memory created from that chat." `RM/design/oai_memory_faq_browser.txt`. Read in a browser, because curl got HTTP 403.
- **Contrast, verified.** Gemini Help: "To delete something that Gemini remembered about you, delete all chats with this info". `RM/design/gemini_past_chats.txt`. Gemini treats the chat as the source of truth. Connected-app deletions may take "days", design report 2.5.
- **Inferred from the three pages.** A memory store is a derived index. Keep a link from each memory to its source turns. Without it, deleting a turn cannot find the memories made from it. Check: the lineage fix in lab B of section 6.
- **Verified.** ChatGPT keeps logs of deleted saved memories "for up to 30 days", design report 2.5. Module 18 owns the retention duty.

### 4.9 A scope key is a filter your code must pass on every call. It is not an isolation boundary

- **Best evidence, verified by run.** Real `mem0ai` 2.1.0. A search for Alice scoped only by `agent_id="support"` returned Bob's address first: "search scoped by agent_id only, as the caller for alice: [('bob', 'My home address is 7 Hill Road, Delhi.')". With `user_id` and `agent_id`, only Alice's record came back. `RM/failures/proto/mem0_leak_probe.out`. Conditions: BM25 and entity scoring off because `fastembed` and spaCy were not installed. Ranking was semantic only.
- **Verified.** Mem0 `search()` needs only one of the three keys: "filters must contain at least one of: user_id, agent_id, run_id." `W/memory/main.py` lines 1457 to 1461. A call scoped by `agent_id` alone is valid.
- **Verified.** Mem0 docs: "Unmentioned entities are not constrained". A filter on `user_id` alone also returns records that carry an `agent_id` or `run_id`. `RM/design/mem0_entity-scoped-memory.md`.
- **Verified.** Graphiti applies the group filter only `if group_ids is not None:`, `G/search/search_utils.py` lines 228 and 336. A call without `group_ids` searches every group.
- **Verified.** Claude.ai keeps "separate memory" per project. ChatGPT project-only memory in regulated workspaces cannot reference chats outside the project. Design report 2.4 rows 4 and 5.
- **Link.** Module 4, 7.5 for the index-level lesson. Module 16 for leaks as an attack.

### 4.10 Memory does not buy accuracy by default. When the history fits, full context was more accurate. The crossover moves with history length and the reader model

- **Best evidence, verified.** Mem0 paper, arXiv 2504.19413, Table 2, LoCoMo. Full context J 72.90 ± 0.19. Mem0 66.88 ± 0.15. Mem0 with graph 68.44 ± 0.17. The text: full context "achieves the highest J score (approximately 73%)". `P/2504.19413.txt` lines 679, 714, 721 and 764. Conditions: gpt-4o-mini for extraction and answers, temperature 0. LoCoMo, 10 conversations, adversarial category excluded. Judge: "a separate, more capable LLM", not named. "we conducted 10 independent runs", mean ± 1 SD. Run by the Mem0 authors. Vendor preprint.
- **Verified.** The latency gain is real. p95 total latency: full context 17.117 s, Mem0 1.440 s. Table 2. 1 − 1.440/17.117 = 0.916. The paper rounds it to 91% in the abstract and 92% in section 4.3.
- **Verified.** DMR in the Zep paper: each conversation "contains only 60 messages". Full context 98.0% against Zep 98.2% with gpt-4o-mini, and 94.4% against 94.8% with gpt-4-turbo. `P/2501.13956.txt` lines 305 to 332. Vendor claim: the Zep authors ran it on their own system.
- **Verified. The crossover moves.** LongMemEval_S, about 115K tokens per question: Zep 71.2% against full context 60.2% with gpt-4o, and 63.8% against 55.4% with gpt-4o-mini. Judge GPT-4o with LongMemEval prompts. Vendor claim: the Zep authors ran it between December 2024 and January 2025. `P/2501.13956.txt` Table 2.
- **Verified.** LongMemEval, ICLR 2025: long-context models "show a 30%∼60% performance drop" going from evidence-only context to the full 115K history. GPT-4o fell from 0.870 to 0.606. `RM/design/2410.10813.txt` lines 79, 504 and 505, Figure 3b.
- **Verified.** BEAM, ICLR 2026: at 100K tokens the authors' LIGHT memory beat the long-context baseline by +44.3% relative with GPT-4.1-nano and +49.1% with Llama-4-Maverick. `RM/failures/2510.27246.txt`, section 4.2. The authors tested their own method. Over the strongest baseline, the abstract reports only 3.5% to 12.69%.
- **Verified.** LongMemEval pilot: ChatGPT with memory, GPT-4o, 0.5773. Offline reading of the full history by GPT-4o, 0.9184. 97 questions, 3 to 6 sessions, humans typing into the web apps in August 2024. `RM/design/2410.10813.txt` lines 479 to 482. The product has changed since.
- **Inferred from the rows above.** No study held the reader fixed and varied only the history length on one benchmark with one scorer. Teach "measure at your length with your model". Check: lab C of section 6.

### 4.11 Published memory token savings count only the read path. Under the prototype's prices, a warm cache keeps full history cheaper per turn for about 100 turns. Memory saves money when the cache is cold

- **Best evidence, verified by run.** `RM/design/proto/cost_per_turn.py`, output `cost_per_turn_run_2026-09-23.txt`. Self-test: "SELF-TEST PASS: full_history(t=50) = $0.00556, 16850 input tokens". Break-even: "warm full history becomes dearer than rolling summary at turn 106". "cold full history becomes dearer than raw retrieval at turn 3". Conditions, all assumptions: system prompt 2,000 tokens, 150 user plus 150 assistant tokens per turn, 150 output tokens. Claude Sonnet 5 answers at $2 input, $2.50 five-minute cache write, $0.20 cache hit and $10 output per million tokens. Claude Haiku 4.5 for writes at $1, $1.25, $0.10 and $5. Embedding cost zero. Prices from the Anthropic pricing page fetched 2026-09-23, `RM/design/anth_pricing.txt` line 213. Sonnet 5 at $2 and $10 is "now the standard price" on that page.
- **Verified by recompute, reviewer.** The turn-106 break-even rests on three assumptions. First, a cache hit costs 0.1 times the base input price, $0.20 against $2 per million tokens. Second, a cache write costs 1.25 times, $2.50. Third, each turn adds 300 tokens, 150 user and 150 assistant. With these, warm full history at turn t costs 2,560 + 60 × t millionths of a dollar. The 60 is 300 tokens times $0.20 per million. The rolling summary costs a flat $0.00890. So the break-even is the first t with 2,560 + 60t > 8,900, which is t = 106. The break-even depends on the design it is compared with. Against raw retrieval, $0.00820, it is turn 95. Against extracted facts, $0.01296, it is turn 174. The design report says "until about turn 106" for every design. That is wrong for raw retrieval. Recompute script: reviewer scratchpad `recompute.py`.
- **Verified.** The Mem0 paper's token metric counts "the number of tokens extracted during retrieval", `P/2504.19413.txt` line 265. It does not count extraction calls. Tokenizer `cl100k_base`.
- **Verified.** Mem0 paper Table 2 tokens per query: full context 26,031, Mem0 1,764, Mem0 with graph 3,616. Vendor preprint.
- **Inferred from the prototype.** A returning customer starts a new session with a cold cache. That first turn pays a cache write for the whole history. This is where memory saves money. Inside one active session, a warm cache makes full history cheap. Moving writes to a background job does not reduce their cost.
- **Limit.** Token sizes are assumptions. Anthropic's tokenizer differs from `tiktoken`. The extracted-facts row follows the Mem0 paper, with one update call per fact. `mem0ai` 2.1.0 makes no update call, so that row overstates 2.1.0 by two Haiku calls. Inferred.

### 4.12 Store raw turns as the value and use extracted facts as extra keys. Facts as the only value lose information, and user-only extraction drops what the assistant said

- **Best evidence, verified.** LongMemEval, ICLR 2025, section 5.2: "replacing sessions or rounds with extracted summaries or facts negatively impacts QA performance due to information loss". `RM/design/2410.10813.txt` line 818. Table 3: value = round, key = value, Recall@5 0.582. Key = value plus facts, 0.644. End-to-end GPT-4o top-5 QA 0.615 to 0.657. Conditions: LongMemEval_M, about 500 sessions and 1.5M tokens per question. Retriever Stella V5 1.5B. Fact extractor Llama 3.1 8B Instruct. Chain-of-Note reader. GPT-4o judge, more than 97% agreement with humans. Paper authors ran it.
- **Verified, reworded by the reviewer.** As the stored value, facts helped only multi-session questions, section 5.2, `RM/design/2410.10813.txt` lines 817 to 821. As an extra key, facts raised recall and QA overall, Table 3 above. The two results do not conflict. Llama 3.1 8B accuracy "drops sharply beyond 3k" retrieved tokens. GPT-4o kept improving past 20K. `2410.10813.txt` line 974.
- **Verified, reviewer.** The LongMemEval indexing experiments kept only the user's words in the keys: "When sessions or rounds are used as the key, we only keep the user-side utterances". `RM/design/2410.10813.txt` section 5.1, lines 808 to 809. So the Table 3 recall numbers do not test search over assistant statements.
- **Verified.** Zep lost on questions about what the assistant said. Single-session-assistant: 94.6% full context against 80.4% Zep with gpt-4o. 81.8% against 75.0% with gpt-4o-mini. `P/2501.13956.txt` Table 3, lines 456 to 457. Vendor paper: the Zep authors ran it, and this is a result against their own system. Inferred cause: the extractor keeps facts about the user and drops the assistant's statements. Check: inspect Graphiti's edges from assistant turns in a small run.
- **Why a support agent cares, inferred.** "We will refund you on Monday" is an assistant statement. A user-fact extractor drops it.
- **Vendor claim, verified that the page says it.** Mem0's changelog says "Assistant recall moves from 46% to **100%**" after the 2026 rewrite. `M0/docs/changelog/highlights.mdx` line 231. No benchmark, model or judge is named next to it. Do not teach it as a measurement.
- **Verified quote, no number.** LangGraph docs: a single JSON profile is harder to keep correct as it grows. A collection of small memories "tends to lead to higher recall downstream" but needs update and delete logic. Design report 2.2 row 7.

### 4.13 Writing every experience into memory can make an agent worse than never writing. Gate the writes

- **Best evidence, verified.** arXiv 2505.16067, Table 1. Fixed memory against add-all: RegAgent 67.53 to 55.48. EHRAgent 16.75 to 13.05. AgentDriver 40.11 to 32.32. CIC-IoT 71.50 to 59.90. `RM/design/2505.16067.txt`, Table 1. Conditions: GPT-4o-mini backbone for most runs. Memory records are past task inputs and outputs, retrieved by similarity. Harvard, Georgia, Michigan State and Minnesota. Preprint. Venue not checked.
- **Verified.** A strict human-filtered add scored best on all four: 70.95, 38.50, 51.00 and 85.40. A coarse model judge fine-tuned on 300 trajectories came close. Failures report 2.4 and design report 2.3 row 10.
- **Where it stops.** This is episodic task memory, not customer-profile memory. Inferred that the lesson carries to a support agent that stores its own past answers. Check: the replay lab C with a write gate.
- **Verified, vendor-authored benchmark.** HaluMem: Mem0 update correct 25.50%, omission 74.02%. MemOS 62.11%. GPT-4o judge. The authors work at MemTensor, which makes MemOS. `RM/failures/2511.03506.txt` Table 3.

### 4.14 Background writing removes latency from the customer's wait. It does not remove cost, and it delays when a fact is usable

- **Best evidence, verified quote, no number.** LangMem conceptual guide: writing in the hot path "adds perceptible latency to user interactions". Background writing has "None" latency impact and "Delayed" update speed. `RM/design/langmem_concepts.txt`.
- **Verified that the paper says it. Vendor claim about a rival.** The Mem0 authors saw Zep answer wrongly right after ingestion and better "after a delay of several hours". They attribute it to asynchronous graph building. `P/2504.19413.txt`, section 4.5. Zep did not confirm.
- **Verified.** Letta sleep-time agents: a second agent edits the main agent's core memory. Default every 5th turn, `L/server/server.py` line 784.
- **Verified.** Claude.ai memory saves "as you chat, rather than summarizing conversations after they end". Design report 2.3 row 7.
- **Not checked.** A neutral latency number for hot-path against background writes on one system. Check: time `add` inline against a queued `add` in a harness.
- **Inferred, from the cost prototype.** A background writer costs the same tokens. For a support agent, a fact written in the background after session 1 is usable in session 2 only if the job finished first.

### 4.15 A memory benchmark score measures the judge and the answer key as much as the memory

- **Best evidence, verified.** Mem0's public runner `mem0ai/memory-benchmarks`, commit `4b61c5d`, 2026-05-13. The LoCoMo judge prompt gives full credit for one item: "If the generated answer includes AT LEAST ONE correct item from the gold answer's list, mark CORRECT". With the `--with-evidence` flag, it also shows the judge the gold evidence and says: "Use evidence only to ACCEPT answers, never to reject them". `RM/failures/membench_prompts.py` lines 206 to 222. Reviewer correction: the flag is off by default, `action="store_true"`, `RM/failures/membench_run.py` line 708. The partial-credit rule applies in every run. The evidence rule applies only when the flag is passed. Which setting produced Mem0's published scores is not checked. Default answerer and judge `gpt-5`, `run.py` lines 682 to 683. Default categories 1 to 4, line 707. Verified by the reviewer.
- **Verified in the README and the author's post only.** Independent audit `dial481/locomo-audit`: 99 of 1,540 LoCoMo answers wrong, 6.4%. The judge accepted 62.81% of vague but on-topic answers that were wrong on purpose. It accepted 10.61% of specific wrong answers. `RM/failures/locomo_audit_README.md` lines 9, 12 and 37. The audit author's post names the judge as gpt-4o-mini and says specific factual errors "were caught approximately 89% of the time". `RM/failures/penfield.txt`, dated 2026-04-08. Reviewer correction: the dossier gave 62.81% without the answer type. Not peer reviewed. The per-error list is not checked.
- **Verified by run.** In the released `locomo10.json`, "category 5 questions without an 'answer' key: 444 of 446". `RM/failures/check_locomo_overall.out`. Every party excludes category 5.
- **Verified.** The Mem0 paper's judge prompt says "be generous with your grading". `P/2504.19413.txt` line 960.
- **Verified.** MemoryAgentBench agents "are prompted to prioritize later information in case of conflict". So the prompt tells the model the rule. `RM/failures/2507.05257.txt` line 444.
- **Link.** Module 11 owns judge validation, planned Phase 3, and broken public benchmarks, planned Phase 6, section 6.4. Module 4, 1.3 and 1.4 teach that a score also measures the gold labels and the match rule. This module uses one fact: change the judge and the score moves.

### 4.16 One vendor's run of a rival is not the rival's score. The LoCoMo numbers for Zep span 58.44 to 84

- **Best evidence, verified.** Two parties, Mem0 and Zep, published four numbers for Zep on LoCoMo. None share one pipeline. Every row is a vendor claim. Reviewer correction: the dossier said "four parties".

| Who ran it | System | Score | Date | Source and label |
|---|---|---|---|---|
| Mem0 paper | Zep | J 65.99 ± 0.16 | 2025-04-28 | `P/2504.19413.txt` line 700. Verified. Vendor run of a rival. gpt-4o-mini answers. "10 independent runs for each method", mean ± 1 SD, lines 259 to 260 |
| Zep, first blog version | Zep | 84% | 2025-05 | Mentioned in the issue title "Revisiting Zep's 84% LoCoMo Claim". Zep's correction says it erred. Verified only as a mention |
| Mem0, zep-papers issue #5 | Zep | 58.44% | 2025-05-08 | `RM/failures/zep_issue5.txt`. Verified. The issue says Zep counted category-5 correct answers in the numerator but not in the denominator |
| Zep, corrected blog | Zep | 75.14% ± 0.17 | updated 2026-06-03 | `RM/failures/zep_lies.txt`. Verified. Vendor run of its own system. Zep says Mem0 ran Zep's searches "sequentially instead of in parallel" and used a non-standard setup |
| Zep, later post | Zep | 80% "at <200ms" | banner dated "December 9, 2015", likely 2025 | Not fetched. Not checked |

- **Vendor claim, verified that the blog says it.** Letta's filesystem agent: "74.0% on LoCoMo with GPT-4o mini", against "Mem0's reported 68.5%". `RM/failures/letta_bench.txt`. Vendor blog, 2025-08-12. The saved page names no scorer. Letta says Mem0 did not answer how it ran MemGPT.
- **Vendor claim, verified.** Mem0's 2026 page: LoCoMo "Overall" 92.5, mean 6,956 tokens. LongMemEval 94.4. `M0/docs/core-concepts/memory-evaluation.mdx` lines 73 and 131. Conditions stated: top-200 retrieval, "production-representative model stack" with no model named, and "proprietary optimizations not available in the open-source SDK". Line 137 and 140.
- **Verified, arithmetic.** That page's LoCoMo overall is higher than every category it lists. Section 7, conflict e.
- **Verified in the README only, reviewer.** The LoCoMo audit puts the ceiling for a perfect system at 93.57%, because of the wrong gold answers. It also reports an independent full-context run: GPT-4.1-mini with a chain-of-thought answer prompt scored 92.62%. It says "The answer prompt, not the memory system, explains the score." `RM/failures/locomo_audit_README.md` lines 9 and 16. Four runs, 2 models and 2 prompts, line 39. Not peer reviewed. The run itself is not checked. Use: a memory score near 92 on LoCoMo does not beat full context by itself.
- **Inferred.** Each vendor tuned its own system and ran the rival at defaults. No neutral re-run of all systems with one harness was found by any of the three agents.

### 4.17 On independent benchmarks, resolving a contradiction fails for every tested system at long length and on multi-hop questions

- **Best evidence, verified.** MemoryAgentBench, ICLR 2026, UC San Diego: "all methods fail on the multi-hop situation (with achieving at most 28% accuracy)". `RM/failures/2507.05257.txt` lines 929 to 930. FactConsolidation multi-hop at 262K tokens, 100 questions, SubEM metric: Mem0 2.0, Zep 3.0, MemGPT 3.0, BM25 3.0, GPT-4o-mini long context 5.0, GPT-5-mini 28.0. Table 3, per the failures report 2.1. RAG and commercial systems used GPT-4o-mini as the backbone, chunk size 4,096. Reviewer re-read of Table 3, `RM/failures/2507.05257.txt` lines 525 to 915: the FC-MH values above hold.
- **Verified, reviewer.** Single-hop contradiction is also weak for memory systems. FactConsolidation single-hop, same Table 3: Mem0 18.0, Zep 7.0, MemGPT 28.0. Plain BM25 scored 48.0. GPT-4o-mini long context scored 45.0. GPT-5-mini scored 78.0. Same backbone and chunk settings as above. The authors are not vendors of any tested system.
- **Verified.** The same task is solvable when short. o4-mini scored 80.0 on multi-hop at 6K tokens and 14.0 at 32K. Table 5, failures report 2.1.
- **Verified.** BEAM, ICLR 2026, University of Alberta and UMass: contradiction resolution between 0.000 and 0.053 for all four models and all three methods, from 100K to 10M tokens. Nugget scoring, 0, 0.5 or 1. `RM/failures/2510.27246.txt` Table 1. The row labels are at lines 543, 687, 831 and 975, and the 12 values follow each label. Reviewer correction: the dossier gave the line before each label. Sample: 2 questions per ability per conversation.
- **Vendor claim, verified.** Mem0's own BEAM run: `contradiction_resolution` 35.7 at 1M and 32.5 at 10M. `memory-evaluation.mdx` line 117. Mem0 Platform, its own runner and judge, model not named. Not reconciled with the paper. Section 7, conflict g.
- **Verified, vendor-authored.** HaluMem shows the update stage failing: Mem0 omitted 74.02% of updates, 4.13.
- **Counter-case, vendor claim.** Mem0 says ADD-only raised its own scores: LoCoMo "71.4 → 91.6", LongMemEval "67.8 → 93.4". `M0/docs/changelog/highlights.mdx` lines 228 to 229. The old write path lost information on UPDATE and DELETE. Inferred: keeping every fact trades lost information for stale information. No independent study compared the two designs with a strict scorer.

---

## 5. Design and cost table

All rows use the prototype's assumptions from 4.11: system prompt 2,000 tokens, 300 tokens per turn, 150 output tokens, Claude Sonnet 5 answers, Claude Haiku 4.5 writes, prices of 2026-09-23. Embedding cost is zero. The first five rows are **verified by run** from `RM/design/proto/cost_per_turn_run_2026-09-23.txt`. The last two rows are **dossier author arithmetic** from `D10/extra_rows.txt`, not a prototype run. No row is a measurement of a product.

| Design | What is stored | Who writes | LLM calls per turn | Answer input tokens | USD per turn, turn 50 | USD per turn, turn 200 | Correction path | Deletion path |
|---|---|---|---|---|---|---|---|---|
| Full history, warm cache | Every turn | Nobody. Your app appends | 1 | 16,850 at turn 50. 61,850 at turn 200 | 0.00556 | 0.01456 | The reader sees both. Recency is visible in order | Delete the turn. One copy |
| Full history, cold cache | Every turn | Nobody | 1 | same | 0.04362 | 0.15613 | same | same |
| Rolling summary | A 500-token summary plus the last 10 turns | A summary call every 10 turns | 1.1 | 5,650 | 0.00890 | 0.00890 | The next summary may drop the old value. Loss is not controlled. Module 2, 3.4 | The summary keeps text from a deleted turn until it is rebuilt |
| Extracted facts, Mem0-paper style | 2 facts per turn, 20 retrieved | Extractor plus one update call per fact | 4 | 4,250 | 0.01296 | 0.01296 | UPDATE or DELETE decision at write time. `mem0ai` 2.1.0 has no update call, 4.2 | Facts, history rows and the message buffer, 4.7 |
| Retrieval over raw turns | Every turn, indexed | Nobody. An index job | 1 | 5,150 | 0.00820 | 0.00820 | Ranking decides, 4.3 | The turn and its vector. Module 3, 7.3 |
| Memory block, 2,000 tokens | A text block in the system prompt plus the last 10 turns | The agent model with a tool, or a sleep-time agent | 1. 2 on an edit turn | 7,150 | 0.0086. Edit turn 0.0262 | same | Exact text replace, 4.6 | Replace with empty text. History of the edit not checked |
| Memory block, 10,000 tokens | Two full default Letta blocks, about 40,000 characters | same | same | 15,150 | 0.0102. Edit turn 0.0478 | same | same | same |
| Temporal graph | Episodes, entities and dated edges. 1,600 retrieved tokens | Extractor calls per episode | 1 to answer. Write calls not counted | 5,250 | 0.0084 plus the write path | same | Invalidate with dates. Reader must honour them, 4.4 | `remove_episode` keeps shared edges and summaries, 4.7 |

- **Cold cache.** It means the first turn of a new session, after the cache TTL, with all earlier turns in the prompt. The prototype prices every turn in that row as cold.
- **Block edit turn.** The arithmetic prices the system prompt and the block at the cache-write rate. It adds one extra model call for the tool round trip. That call has 100 output tokens and 50 tokens of tool result. Inferred, 4.6.
- **Temporal graph.** 1,600 tokens is the Zep paper's average context on LongMemEval_S, `P/2501.13956.txt` Table 2. The write path is several LLM calls per episode. The count is not checked. Mem0's paper says Zep's store exceeded 600K tokens per LoCoMo conversation, a vendor claim about a rival, design report 2.2 row 6.
- **Break-even, verified by run.** Warm full history costs more than the rolling summary only from turn 106. A cold full history costs more than raw retrieval from turn 3.
- **Break-it variants, from the design report, corrected by the reviewer's recompute.** Raise facts per turn from 2 to 6 and the fact design costs $0.01948 per turn. That is 8 calls per turn. It does not pass $0.02, as the design report said. The prototype's cold row prices every turn cold, not only the first turn of a session. Against the rolling summary, cold full history is dearer from turn 4. Against raw retrieval it is dearer from turn 3. The design report's "from 106 to 3" compares two different baselines. A more realistic session has one cold first turn and warm turns after it. For a returning customer with 50 earlier turns, that cold first turn costs $0.04437 against $0.00820 for raw retrieval. Not built into the prototype. Recompute: reviewer scratchpad `recompute.py`.
- **Answer input of the temporal graph row.** The 5,250 tokens are the 2,000-token system prompt, 1,600 retrieved tokens, the last 5 turns and the new user message. `D10/extra_rows.py` line 15.
- **Block edit turn, reviewer note.** `D10/extra_rows.py` prices the first call of the edit turn at the cache-write rate and the tool follow-up call at the hit rate. The edit happens inside the turn, so the write would fall on the second call. The total is the same either way, because the two calls have the same prefix. If the Letta V3 loop skips the refresh, 4.6, no write happens at all and the edit turn costs less.

Link: Module 1, 3.1 and 3.3 own the cache prices. Module 2, 2.5 and Module 4, 2.1 own the break-even method.

Summary: inside one warm session, full history is cheap. Across sessions, the cold first turn makes full history the most expensive row. The fact design pays for its write calls on every turn.

---

## 6. Lab inventory

### Built and run on 2026-09-23

| Lab | Script | Saved output | Run time | Download | Self-test | Proves |
|---|---|---|---|---|---|---|
| Conflict test, 20 pairs, two embedders, similarity only | `RM/failures/proto/conflict_rank.py` | `conflict_rank.out` | 6.0 s, CPU | None beyond the cached harness models | 2 checks, passing | 4.3 |
| Correction race, three write policies, toy embedder | `RM/architectures/lab/correction_race.py` | `RM/architectures/runs/lab_correction_race_default.txt`, `lab_correction_race_reworded.txt` | Under 1 s | None, standard library | None. The report proposes three asserts | 4.2, 4.3, 4.4 |
| Deletion audit across five copies, SQLite bytes, vector snapshot | `RM/failures/proto/deletion_audit.py` | `deletion_audit.out` | 0.19 s | None, standard library and numpy | 3 checks, passing | 4.7 |
| Real Mem0 probe: agent-only scope, delete, history rows | `RM/failures/proto/mem0_leak_probe.py` | `mem0_leak_probe.out` | About 1 minute | `mem0ai` 2.1.0, about 67 packages. Size not measured | None | 4.7, 4.9 |
| Cost per turn, five designs | `RM/design/proto/cost_per_turn.py` | `cost_per_turn_run_2026-09-23.txt` | Under 1 s | None | Hand-worked $0.00556 at turn 50, and cold costs more than warm | 4.11, section 5 |
| LoCoMo overall and category-5 check | `RM/failures/check_locomo_overall.py` | `check_locomo_overall.out` | Not recorded | `locomo10.json`, 2.8 MB | None | 4.15, 4.16 |
| LoCoMo token count | Not saved as a script | `RM/failures/locomo_tokens.out` | Not recorded | as above, `tiktoken` `o200k_base` | None | Conflict b |

### Designed, not built

| Lab | Source | What it would print | Proves |
|---|---|---|---|
| A. Conflict test over turns, with BM25 and a recency weight | Failures report lab A | Rank of the correction after k distractor facts, k = 0, 5, 20 and 50. The smallest recency weight that gives 20 of 20, and the past-tense question it breaks | 4.3. The README's "over how many turns" |
| B. `forget(subject)` with lineage | Failures report lab B | Deletion audit counts for every table, rerun until all are 0 | 4.7, 4.8 |
| C. Offline multi-session replay: full history, summary, extracted facts, retrieval | Design report 5.2 | Accuracy per question type and tokens seen per design. 20 sessions, 30 planted facts, 10 corrected, 5 said only by the assistant, 5 unanswerable | 4.10, 4.12, 4.13. Rules, not models, so it proves the mechanism, not the rate |
| D. LongMemEval retrieval only, rounds against sessions | Design report 5.3 | Recall@5 and Recall@10 per design, with the harness paired test | 4.12. 277 MB download. Run time not measured |
| E. Cross-user leak matrix with canaries | Failures report lab C | Foreign canaries in retrieved memories and in answers. Pass is 0 | 4.9 |
| F. Per-turn memory cost meter with a fake model | Architectures report lab B | Tokens from memory, extra calls, and whether the system-prefix hash changed per turn | 4.1, 4.6 |
| G. Mem0 OSS write trace with a fake LLM | Architectures report lab C | History table after "I live in Austin" then "I moved to Seattle". Expected two ADD rows | 4.2. About 2 hours to build. Not run |
| H. Re-score LoCoMo answers with two judges | Failures report lab D | Exact match against lenient judge rules on one answer set | 4.15. Needs an LLM judge. Optional, UNVERIFIED. Cost not checked |

### The module lab, proposed

A support-agent replay that answers all four parts of the module question. Proposal, not built:

1. A seeded generator of 3 customers and 10 sessions each. It plants profile facts, 10 corrections, 5 assistant promises and 1 deletion request per customer. Reuse the design of lab C.
2. Four stores behind one wrapper: full history, rolling summary, extracted facts in ADD-only and update modes, and BM25 plus MiniLM retrieval over rounds from the shared harness.
3. Every derived row carries `customer_id` and the source turn ids. That is the lineage.
4. Each session starts cold. The cost meter from `cost_per_turn.py` prices each turn.
5. The self-test checks one hand-counted session per question type.
6. It prints, per design: accuracy on latest-value, old-value-with-date, assistant-said and unanswerable questions. Foreign canaries found. Copies left after `forget(customer, fact)`. USD per session.
7. Break-its: drop `customer_id` from one path. Switch the extractor to ADD-only. Delete through the API without lineage.

Inferred: offline, no key, under 1 minute, no new download beyond the harness. Not measured.

---

## 7. Conflicts resolved

| Conflict | Reports | Evidence used | Resolution |
|---|---|---|---|
| a. Which Letta version to pin | Curriculum audit: `letta` 0.32.18 on PyPI against 0.16.8 on GitHub. Design and failures reports list 0.32.18 and did not reconcile | `RM/architectures/runs/letta_pypi_history.txt` lines 58 and 59: 0.16.8 on 2026-05-14, then 0.32.13 on 2026-09-17, nothing between. `RM/architectures/runs/letta_rename_check.txt`: 0.16.8 summary "Create LLM agents with long-term memory and custom tools". 0.32.13 summary "Letta Code: stateful agents in your terminal", source `letta-ai/letta-code`. `gh_releases_2026-09-23.txt`: `letta-ai/letta` latest 0.16.8, `letta-ai/letta-code` latest v0.32.18 | The PyPI name changed product on 2026-09-17. For the memory server pin `letta==0.16.8`. 0.32.18 is Letta Code, a different product. The server repo was last pushed 2026-09-10 and is not archived |
| b. LoCoMo length: 9K against 26K tokens | LoCoMo paper against the Mem0 paper. The failures report measured a third value | LoCoMo paper: "300 turns and 9K tokens on avg.", `P/2402.17753.txt` line 166, for its 50 generated conversations. Mem0 paper: "26000 tokens on average", line 231. Mem0 Table 2 full-context input 26,031 tokens, `cl100k_base`. `RM/failures/locomo_tokens.out`: the released 10 conversations average 17,450 `o200k_base` tokens and 588.2 turns, speaker and text only | The numbers count different things. 9K is the paper's figure for 50 conversations. The released file has 10 conversations, and they are longer: 588 turns, not 300. 26K is Mem0's full-context input. Inferred: it adds dates and prompt text. Check: tokenise Mem0's full-context prompt for one conversation. Teach "about 17K tokens of dialogue per released conversation, measured" |
| c. Zep's "18.5%" against 18.3% | Architectures, failures and design reports all recomputed it | `P/2501.13956.txt` lines 34 and 375 say 18.5%. Table 2: 60.2% and 71.2%. 71.2 / 60.2 = 1.183. `RM/failures/arithmetic_checks.out` | The table gives 18.3% relative and 11.0 points. The gpt-4o-mini figure, 15.2%, reproduces. Cause not checked. Unrounded scores may explain it. Quote 18.3% from the table. Table 3 also divides decreases by the Zep score, not the baseline: single-session-assistant prints 17.7%, and 15.0% against the baseline |
| d. Mem0's 2026 LoCoMo number: 91.6 or 92.5 | Architectures report 2.6 and failures report 2.6 | `M0/docs/changelog/highlights.mdx` line 228: "71.4 → 91.6". Migration guide: 91.6. `memory-evaluation.mdx` line 73: "Overall 92.5", and line 131 | Two Mem0 pages in the same tag disagree. Not settled. Cite both as vendor claims, with no model named |
| e. Mem0's "Overall 92.5" is above every category | Failures report 2.6 | `memory-evaluation.mdx` lines 73 to 77: single-hop 91.2, multi-hop 91.3, open-domain 72.7, temporal 92.0. `check_locomo_overall.out`: categories 1 to 4 hold 1,540 questions. Weighted mean 90.2. Max 92.0 | A mean over these four categories cannot exceed 92.0, whatever the weights. The 90.2 uses the runner's category mapping, `CATEGORY_NAMES` in `RM/failures/membench_prompts.py` lines 25 to 31: 1 multi-hop, 2 temporal, 3 open-domain, 4 single-hop. Reviewer correction: `run.py` line 707 is the `--categories` default, not the mapping. Reviewer recompute: the sum 282 × 91.3 + 321 × 92.0 + 96 × 72.7 + 841 × 91.2, divided by 1,540, is 90.23. With single-hop and multi-hop swapped, 90.27. Cause not checked. The page's tables may come from different runs. The page claims ±1 point from judge noise, line 140. The gap is 2.3 points |
| f. MemoryAgentBench venue | Architectures report: preprint. Failures and design reports: ICLR 2026 | Line 2 of `RM/failures/2507.05257.txt` and of `P/2507.05257.txt`: "Published as a conference paper at ICLR 2026" | ICLR 2026, peer reviewed. The architectures report used the arXiv comment field |
| g. BEAM contradiction resolution: 0.000 to 0.053, or 35.7 | Failures report 8.2 | Paper Table 1, `2510.27246.txt`. Mem0 page line 117 | Not reconciled. The scales differ: the paper reports 0 to 1, Mem0 reports 0 to 100. Even as percentages, 5.3 against 35.7. The judges differ: nugget scoring against Mem0's runner. The methods differ. Cite both with conditions |
| h. When ADD-only arrived | Architectures report: changelog 2026-04-14. Failures report: PyPI 2.0.0 on 2026-04-16 | `RM/failures/pypi/mem0ai.json`: 2.0.0b0 at 2026-04-13T10:24, 2.0.0 at 2026-04-16T11:51. Changelog heading dated 2026-04-14 | Both are true. The first stable PyPI release with ADD-only is 2.0.0, 2026-04-16. The docs call the release "SDK v2.0.0 / v3.0.0" and the migration guide is `oss-v2-to-v3`. Inferred: "v3" names the algorithm series, not the Python package. Pin `mem0ai==2.1.0` |
| i. Mem0 GitHub latest release is a plugin tag | Curriculum audit: `openclaw-v1.2.0` | `gh_releases_2026-09-23.txt`: nine tags on 2026-09-18, including `v2.1.0` "Mem0 Python SDK (v2.1.0)" | The Python SDK tag exists on the same day. The plugin tag only appears first in list order. Read PyPI and the `v2.1.0` tag |
| j. Where Graphiti's default search passes empty filters | Architectures: "about line 1636". Failures: line 1639 | `G/graphiti.py` lines 1639 and 1684: `search_filter if search_filter is not None else SearchFilters()` | Line 1639 in `search()`. Line 1684 is a second search method with the same default |
| k. Mem0 paper latency: 91% or 92% | Design report 2.1 row 3 | Table 2: 1.440 s and 17.117 s. 1 − 1.440/17.117 = 0.916 | One number, two roundings. Quote 91.6% |
| l. Who judged the Mem0 paper | Failures report: not named. The LoCoMo audit: gpt-4o-mini | `P/2504.19413.txt` line 256: "a separate, more capable LLM". No model name near the J metric. Reviewer check: the audit author's post says "LoCoMo uses gpt-4o-mini to score answers", `RM/failures/penfield.txt`. It describes published LoCoMo setups in general, not the Mem0 paper by name. The audit README names no judge model | Not settled. Teach "judge model not named in the paper" |

---

## 8. Gap list, ranked by how much the module question needs it

| Rank | Gap | Why the module question needs it | What was done |
|---|---|---|---|
| 1 | The joined support-agent replay lab | "How do you prove it helps" needs one run that compares designs on the learner's own data | Not built. Design in section 6 |
| 2 | Conflict test over turns, with BM25 and a recency weight | "How does a correction reach every copy" rests on 20 pairs at one distance. The README asks "over how many turns" | Not built. Lab A |
| 3 | `forget(subject)` with lineage, audited to zero | "How does a deletion reach every copy" has only the failure side. No fix was run | Not built. Lab B |
| 4 | Whether any memory system can prove a fact was forgotten | The README asks it. No report found a deletion receipt in any system | Not checked. The deletion audit is the proposed proof |
| 5 | Graphiti on a real graph database: rank of an expired edge, summary after `remove_episode` | 4.4 and 4.7 for the graph design are read from code | Not run. Kuzu or FalkorDB, fake LLM clients |
| 6 | Whether the user can see a contradiction or a stored memory | The README asks it. Only hosted assistants were checked: users can view and delete memories. Mem0, Graphiti and Letta user views were not checked | Partly. Design report 2.5 |
| 7 | Crossover length at a fixed reader | "Does memory help" depends on it. No study varied only length | Not measured. Lab C can vary length offline, with rules |
| 8 | LLM write-call count per Graphiti episode | The temporal graph row of section 5 has no write cost | Not checked. A counting fake client on one episode |
| 9 | Letta block edit and the prompt cache | 4.6 cost is inferred | Not run. Needs a server and a cache-reporting provider |
| 10 | Mem0 OSS temporal and entity scoring in code | 4.3 says ranking has no time term. The docs describe a temporal score | `scoring.py` read. `_search_vector_store` at `main.py` line 1628 not traced |
| 11 | Hot-path against background write latency on one system | 4.14 has quotes, no number | Not checked |
| 12 | Hosted judge cost and local judge feasibility for lab H | Proof with a judge needs a price or a local model | Not checked. Prices of the judge model not fetched |
| 13 | Real tokenizer counts for Letta blocks and the cost table | Section 5 uses assumed sizes | Not checked. Anthropic token counting needs a key |
| 14 | Mem0's 2026 benchmark model stack | 4.16 vendor number has no model | Not checked. The runner default is `gpt-5` |

---

## 9. Primary sources

HTTP status from 2026-09-23, as recorded by the research agents.

| Title | Org | Year and status | URL | What to read | HTTP |
|---|---|---|---|---|---|
| Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory | Mem0 | 2025, preprint, vendor | https://arxiv.org/abs/2504.19413 | Table 2, sections 3.2 and 4.3 to 4.5, Appendix A | 200 |
| Zep: A Temporal Knowledge Graph Architecture for Agent Memory | Zep AI | 2025, preprint, vendor | https://arxiv.org/abs/2501.13956 | Section 2 timestamps, Tables 1 to 3 | 200 |
| MemGPT: Towards LLMs as Operating Systems | UC Berkeley | 2023, preprint | https://arxiv.org/abs/2310.08560 | Table 2 DMR. The baseline sees a lossy summary, line 517 | 200 |
| LoCoMo, Evaluating Very Long-Term Conversational Memory of LLM Agents | UNC Chapel Hill, USC, Snap Inc. | 2024. ACL 2024 not checked | https://arxiv.org/abs/2402.17753 | Dataset section | 200 |
| LongMemEval | UCLA, Tencent AI Lab | 2024, ICLR 2025 | https://arxiv.org/abs/2410.10813 | Figure 3, sections 5.2 to 5.4, Table 3 | 200 |
| MemoryAgentBench, Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions | UC San Diego | 2025, ICLR 2026 | https://arxiv.org/abs/2507.05257 | Section 3.1, section 4.2, Tables 3 and 5 | 200 |
| BEAM, Beyond a Million Tokens | University of Alberta, UMass Amherst | 2025, ICLR 2026 | https://arxiv.org/abs/2510.27246 | Table 1, section 4.2 | 200 |
| How Memory Management Impacts LLM Agents | Harvard, Georgia, Michigan State, Minnesota | 2025, preprint | https://arxiv.org/abs/2505.16067 | Table 1, section 3.2 | 200 |
| HaluMem | China Telecom, MemTensor | 2025, preprint, vendor-authored | https://arxiv.org/abs/2511.03506 | Table 3 | 200 |
| Ground Truth First | one independent author | 2026, preprint | https://arxiv.org/abs/2607.21962 | Abstract only read | 200 |
| Mem0 source at `v2.1.0` | Mem0 | 2026 | https://github.com/mem0ai/mem0/tree/v2.1.0 | `mem0/memory/main.py`, `mem0/configs/prompts.py`, `docs/core-concepts/*.mdx`, `docs/changelog/highlights.mdx` | tarball 200 |
| Mem0 OSS v2 to v3 migration | Mem0 | undated docs | https://docs.mem0.ai/migration/oss-v2-to-v3 | ADD-only, "Retrieval handles ranking" | 200 |
| Mem0 entity-scoped memory | Mem0 | current docs | https://docs.mem0.ai/platform/features/entity-scoped-memory | Scope filter rules | 200 |
| `mem0ai/memory-benchmarks` at `4b61c5d` | Mem0 | 2026 | https://github.com/mem0ai/memory-benchmarks | `benchmarks/locomo/prompts.py` lines 206 to 222, `run.py` lines 682 to 707 | 200 |
| Graphiti source at `v0.30.2` | Zep | 2026 | https://github.com/getzep/graphiti/tree/v0.30.2 | `edges.py`, `utils/maintenance/edge_operations.py`, `graphiti.py`, `search/*` | tarball 200 |
| Letta source at `0.16.8` | Letta | 2026 | https://github.com/letta-ai/letta/tree/0.16.8 | `letta/constants.py`, `schemas/memory.py`, `services/block_manager.py`, `agents/letta_agent_v3.py` | tarball 200 |
| LangMem 0.0.30 sdist | LangChain | 2025 | https://pypi.org/project/langmem/0.0.30/ | `knowledge/extraction.py`, `reflection.py` | 200 |
| LangMem conceptual guide | LangChain | current docs | https://langchain-ai.github.io/langmem/concepts/conceptual_guide/ | "Writing memories" table | 200 |
| LangGraph memory concepts | LangChain | current docs | https://docs.langchain.com/oss/python/langgraph/memory | Hot path against background, profile against collection | 200, redirects |
| Memory tool | Anthropic | current docs | https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool | Client-side, commands, path checks | 200 |
| Claude Code memory | Anthropic | current docs | https://code.claude.com/docs/en/memory | Auto memory, how it loads | 200 |
| Use Claude's chat search and memory | Anthropic | help center | https://support.claude.com/en/articles/11817273 | Deletion, defaults | 200 |
| Memory in ChatGPT | OpenAI | help center, about 2026-09-19 | https://help.openai.com/en/articles/8590148-memory-faq | Deletion, 30 days | 403 to curl, read in a browser |
| Gemini past chats | Google | help center | https://support.google.com/gemini/answer/16598469 | Deletion, account limits | 200 |
| Lies, Damn Lies, & Statistics | Zep | 2025, updated 2026-06-03, vendor blog | https://blog.getzep.com/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/ | Corrected score, LoCoMo flaws | 200 |
| zep-papers issue #5 | Mem0 | 2025 | https://github.com/getzep/zep-papers/issues/5 | Category-5 accounting | 200 |
| Benchmarking AI Agent Memory | Letta | 2025-08-12, vendor blog | https://www.letta.com/blog/benchmarking-ai-agent-memory | Method and 74.0% | 200 |
| LoCoMo audit | dial481 | 2026, not peer reviewed | https://github.com/dial481/locomo-audit | README table | 200 |
| mem0 issue #3944 | user report | 2026 | https://github.com/mem0ai/mem0/issues/3944 | Ingestion date as event date | 200 |
| Anthropic pricing | Anthropic | fetched 2026-09-23 | https://platform.claude.com/docs/en/about-claude/pricing | Sonnet 5 and Haiku 4.5 rows | 200 |
| LoCoMo data | Snap | 2024 | https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json | 10 conversations, 1,986 questions | 200 |
| Letta memory blocks guide | Letta | n/a | https://docs.letta.com/guides/agents/memory-blocks.md | n/a | 404, not read |

---

## 10. Tools and versions to pin

Checked 2026-09-23. Sources: `RM/architectures/runs/pypi_versions_2026-09-23.txt`, `RM/architectures/runs/gh_releases_2026-09-23.txt`, `RM/failures/pypi/mem0ai.json`. The reviewer re-fetched `https://pypi.org/pypi/<name>/json` for `letta`, `mem0ai`, `graphiti-core` and `letta-client` on 2026-09-23, all HTTP 200. Every version and date in the first six rows matches. `letta` latest is 0.32.18, uploaded 2026-09-23T06:00Z, summary "Letta Code: stateful agents in your terminal". Between 0.16.8 and 0.32.13 there is no release. Neither 0.16.8 nor `mem0ai` 2.1.0 is yanked.

| Package or repo | Version | Released | Note |
|---|---|---|---|
| `mem0ai` | 2.1.0 | 2026-09-18 | ADD-only since 2.0.0, 2026-04-16. Telemetry on by default: set `MEM0_TELEMETRY=False`. BM25 needs `mem0ai[extras]`. Entities need `mem0ai[nlp]` |
| `letta`, memory server | 0.16.8 | 2026-05-14 | Pin exactly. Later `letta` versions are Letta Code |
| `letta`, Letta Code | 0.32.18 | 2026-09-23 | A different product. Not for this module |
| `letta-client` | 1.12.1 | 2026-06-02 | Python client for a Letta server |
| `graphiti-core` | 0.30.2 | 2026-09-08 | Needs Neo4j, FalkorDB or Kuzu. Offline use without Docker is inferred, not run |
| `zep-cloud` | 3.28.0 | 2026-08-11 | Hosted, needs a key. Not for offline labs |
| `langmem` | 0.0.30 | 2025-10-27 | No release in 11 months. Repo pushed 2026-09-09 |
| `langgraph` | 1.2.12 | 2026-09-21 | |
| `langgraph-checkpoint` | 4.2.0 | 2026-08-07 | Holds `langgraph.store.base` |
| `openai-agents` | 0.22.3 | 2026-09-17 | Sessions only. Module 9 |
| `anthropic` | 1.8.0 | 2026-09-22 | Memory tool helpers |
| Anthropic memory tool | `memory_20250818` | | The only version string on the docs page |
| `tiktoken` | 0.14.0 | 2026-08-17 | Token estimates only |
| `mem0ai/memory-benchmarks` | commit `4b61c5d` | 2026-05-13 | No release tag. Pin the SHA |
| `xiaowu0162/LongMemEval` | main | pushed 2026-05-11 | MIT. Use the cleaned files |
| `snap-research/locomo` | main, commit `3eb6f2c` | 2024-08-13 | No updates in two years |
| Shared harness | `sentence-transformers` 6.1.0, `torch` 2.14.0, `transformers` 5.17.0 | | `retrieval-internals/code/common/HARNESS.md`. Do not add a memory framework to the offline labs |

---

## 11. Things not verified

From all three reports and from this dossier. Each item has the check that would settle it.

**Architectures report.**

1. ChatGPT memory internals: what is stored and when. The design agent later read the help page in a browser. The write mechanism is still not named by OpenAI. Check: an OpenAI source that names the tool.
2. Letta memory blocks guide content. The `.md` URL returned 404. Check: find the path in `docs.letta.com/llms.txt`.
3. The number of LLM calls per Graphiti `add_episode`. Check: a counting fake LLM client on one episode with 3 facts.
4. Whether a Letta 0.16.8 memory edit breaks the provider prompt cache, and whether the model sees the edit in the same run. Check: a server run with a cache-reporting provider.
5. Mem0 temporal and entity scoring in OSS code. Check: trace `_search_vector_store` at `main.py` line 1628 and the entity path at line 1773.
6. BEAM origin beyond the paper and Mem0's use of it. Check: compare Mem0's runner with the BEAM repo.
7. LoCoMo venue, ACL 2024. Check: the ACL Anthology.
8. The Zep rebuttal's list of Mem0 harness errors, item by item. Check: read the full post and linked code.
9. LangMem search latency of 17.99 s p50, Mem0's measurement. Check: re-run with a local store.
10. Graphiti offline without Docker, with Kuzu or embedded FalkorDB. Check: install `graphiti-core==0.30.2` with the Kuzu driver and run one add and one search.
11. Token count of default Letta blocks. Check: render `Memory.compile()` with full blocks and count with a real tokenizer.
12. `mem0ai` version naming, 2.x against "v3". Check: read `docs/migration/oss-v2-to-v3.mdx` in full.
13. LangGraph store search without an `index` config filters only by namespace and fields. Check: an `InMemoryStore()` run.
14. `ReflectionExecutor` delay behaviour. Check: a run with `after_seconds` set.

**Failures report.**

15. Whether Graphiti's default search ranks expired edges below current ones. Check: a Graphiti run with a fact and a correction.
16. Whether Graphiti entity summaries keep text from a removed episode. Check: the same setup, then read `EntityNode.summary`.
17. Why Mem0's LoCoMo "Overall 92.5" is above every category. Check: run `benchmarks/locomo/run.py` or get the result JSON.
18. The judge and answer models behind Mem0's published 2026 scores. Check: the result files, or ask the vendor.
19. Whether the Mem0 paper's judge was gpt-4o-mini. Check: `mem0/evaluation/` at commit `2b58775`.
20. The root cause of mem0 issue #3944. Check: the closing comment or the platform code.
21. The per-error list in the LoCoMo audit. Check: sample 20 errors against `locomo10.json`.
22. Zep's "80% at <200ms" LoCoMo post. Check: fetch it.
23. Hosted judge cost for lab H. Check: today's price for the chosen judge model, times 1,540 questions.
24. Whether local 1B-class models can act as extractors or judges. Check: a 20-item pilot with `Llama-3.2-1B-Instruct` from the local cache.
25. The behaviour of Mem0's `_escape_scope_value`. Check: a scope value with an escape character.
26. The venue of arXiv 2505.16067. Check: the arXiv comment or a later version.

**Design report.**

27. When Claude memory became on by default for Free. Check: Anthropic release notes.
28. Whether ChatGPT uses a `save_memories` tool today. Only LangChain docs say so.
29. Letta's 74.0% scorer. The saved page names none. Check: the Letta LoCoMo repository linked from the post.
30. LongMemEval-V2 content. Check: fetch the repository.
31. Latency of hot-path against background writes on one system. Check: a timing harness.
32. Run time and recall of lab D on this laptop. Check: run it. The 277 MB file was not downloaded.
33. Anthropic tokenizer counts for the cost table. Check: the token-counting endpoint, which needs a key.
34. Why Zep's "18.5%" differs from 18.3%. Check: unrounded scores or a v2 of the paper.

**This dossier.**

35. The two cost rows added by the dossier author, memory block and temporal graph, are arithmetic on assumptions. The block edit cost assumes the edit breaks the cache, 4.6.
36. The 90.2 weighted mean depends on the category mapping in Mem0's runner. The bound "no higher than 92.0" does not. The reviewer re-read the mapping in `membench_prompts.py` lines 25 to 31. Settled.
37. Anchors marked "per the ... report" in section 4 were not re-grepped by the dossier author. They are supporting evidence, never the best evidence.
38. Whether Mem0, Graphiti or Letta show the end user a stored memory or a contradiction. Not checked for the open-source systems.

**Reviewer, 2026-09-23.**

39. Which `--with-evidence` setting and which models produced Mem0's published 2026 LoCoMo scores. Check: the result JSON of the published run.
40. SETTLED 2026-09-25: Mem0 2.1.0 `update()` and `delete()` keep the old text in the history table (`old_memory`). Evidence: Module 10 Phase 3, `memory/code/runs/memory_p03_mem0_write_trace.txt`, and `main.py` lines 2051 and 2080 to 2084 at v2.1.0 (the text-changing update case is read from source, not run).
41. The LoCoMo audit's full-context run of 92.62%. Check: read `fc-baseline/README.md` in the audit repository.
42. Per-row line numbers of MemoryAgentBench Table 3 for Mem0, Zep and MemGPT. Values were read by parsing the table text, not by line.

---

## 12. Anchor number re-check

The dossier author grepped 106 anchors from section 4 on 2026-09-23. Each search ran over the saved source, paper text, run output or installed package file named in the concept. Whitespace is collapsed to one space. Backticks and double asterisks are removed. Curly quotes are made straight. Script: `D10/anchor_check.py`. Output: `D10/anchor_check.txt`.

- **106 of 106 anchors match their expected count.** 53 are presence checks. 52 check an exact count, such as 2 hits of the `SearchFilters()` default in `graphiti.py` and 4 matching rows in `deletion_audit.out`. 1 is an absence check: "recency" has 0 hits in `W/utils/scoring.py`.
- Per concept, found of checked:

| Concept | Anchors | Concept | Anchors |
|---|---|---|---|
| 4.1 | 7 of 7 | 4.10 | 11 of 11 |
| 4.2 | 7 of 7 | 4.11 | 5 of 5 |
| 4.3 | 8 of 8 | 4.12 | 8 of 8 |
| 4.4 | 6 of 6 | 4.13 | 2 of 2 |
| 4.5 | 3 of 3 | 4.14 | 3 of 3 |
| 4.6 | 6 of 6 | 4.15 | 6 of 6 |
| 4.7 | 9 of 9 | 4.16 | 10 of 10 |
| 4.8 | 3 of 3 | 4.17 | 6 of 6 |
| 4.9 | 6 of 6 | | |

- **Two needles needed normalisation before they matched.** Neither changed a fact.
  1. The Claude help page uses a curly apostrophe in "won’t be removed". The script makes quotes straight.
  2. `grep` returned nothing on `2505.16067.txt` because of non-UTF-8 bytes. The script reads with replacement, and the Table 1 row matched as one collapsed string.
- **One report statement was corrected by the re-read.** The architectures report called MemoryAgentBench a preprint. Both saved texts say "Published as a conference paper at ICLR 2026". Section 7, conflict f.
- **One line was added by the re-read.** `L/agents/letta_agent_v3.py` line 967 says "The system prompt is only rebuilt after compaction or message reset." No report quoted it. It is in 4.6.
- Every quote in section 4 is 25 words or shorter.

---

## 13. Review log

Reviewer: independent review agent, 2026-09-23. The reviewer did not write this dossier. Method: read-only checks of the saved files, one fetch per package of PyPI JSON, and arithmetic in a reviewer script. No lab ran. The reviewer's files are in its own session scratchpad: `recompute.py`, the four `pypi_*.json` files, and a copy of this dossier before the review, `module-10-memory.before_review.md`.

### 13.1 Corrections made in the text

Each correction is also made in the section named.

**Wrong claims. These would mislead a writer.**

| # | Where | What the dossier said | What the evidence shows | Evidence |
|---|---|---|---|---|
| 1 | 4.15 | The Mem0 runner shows the judge the gold evidence and tells it to use evidence only to accept | That rule applies only with the `--with-evidence` flag. The flag is off by default. The partial-credit rule applies in every run | `RM/failures/membench_run.py` line 708, `action="store_true"`, and line 753. `membench_prompts.py` lines 212 and 222 |
| 2 | 3, 4.15 | "A gpt-4o-mini judge accepted 62.81% of answers that were wrong on purpose" | 62.81% is for vague but on-topic wrong answers. Specific wrong answers: 10.61%. The judge model comes from the author's post, not the README | `RM/failures/locomo_audit_README.md` lines 12 and 37. `RM/failures/penfield.txt`: specific errors "caught approximately 89% of the time" |
| 3 | 5 | Raising facts per turn from 2 to 6 makes the fact design pass $0.02 per turn | $0.01948 per turn. It does not pass $0.02 | Reviewer `recompute.py`: extract $0.0048, 6 updates $0.00828, answer $0.0064 |
| 4 | 5 | A cold first turn moves the break-even "from 106 to 3" | 106 is against the rolling summary. 3 is against raw retrieval. Against the rolling summary, cold is dearer from turn 4. The prototype prices every turn cold, not only the first | Reviewer `recompute.py`. `RM/design/proto/cost_per_turn.py` lines 17 to 18, 58, 64 and 66 |
| 5 | 4.16 | "Four parties, four numbers for Zep" | Two parties, Mem0 and Zep, published the four numbers. Every row is a vendor claim | The table's own "Who ran it" column |
| 6 | 4.12 | "Facts helped only multi-session questions" | True for facts as the stored value. As an extra key, facts raised recall and QA overall, the dossier's own best evidence | `RM/design/2410.10813.txt` lines 817 to 821 and Table 3, lines 826 to 877 |
| 7 | 4.4 | Contradiction detection is one LLM call per new edge | At most one. Skipped when there are no related edges and no candidates, and on an exact fact match | `G/utils/maintenance/edge_operations.py` lines 653, 684 and 726 |
| 8 | 4.3 | Quoted Mem0: knowledge update 93.6 is "the hardest category" with no note | The same page's table has multi-session at 88.0. The vendor's own table does not support "hardest" | `M0/docs/core-concepts/memory-evaluation.mdx` lines 93, 95 and 99 |

**Wrong line numbers or sources. The fact itself holds.**

| # | Where | Correction | Evidence |
|---|---|---|---|
| 9 | 7 e | The category mapping is `CATEGORY_NAMES` in `membench_prompts.py` lines 25 to 31. `run.py` line 707 is the `--categories` default | Both files read |
| 10 | 4.17 | BEAM contradiction rows start at lines 543, 687, 831 and 975, not 542, 686, 830 and 974 | `RM/failures/2510.27246.txt`. Line 542 is the last abstention value |
| 11 | 7 l | The audit's "gpt-4o-mini" judge is in the author's post and describes LoCoMo setups in general. The README names no judge | `RM/failures/penfield.txt`. `locomo_audit_README.md` has no "4o-mini" near a judge |
| 12 | 5 | Temporal graph row: the 5,250 tokens include the last 5 turns. The table did not say so | `D10/extra_rows.py` line 15 |

**Missing labels.**

| # | Where | Correction |
|---|---|---|
| 13 | 4.10, 4.12 | Zep DMR, LongMemEval_S and Table 3 numbers now carry "vendor claim" or "vendor paper", run by the Zep authors |
| 14 | 4.16 | Letta's 74.0% is now labelled "vendor claim, verified that the blog says it". The Zep blog rows are marked as a vendor run of its own system. The Mem0 paper row says "10 independent runs for each method", not "10 judge runs" |
| 15 | 4.7 | The Mem0 probe printed "messages rows: []". It did not exercise the message buffer. That claim rests on code, now re-read: `delete()` line 1869 and `delete_all()` line 1890 do not touch the table. The probe log shows a Hugging Face Hub warning, so it was not fully offline |

**Arithmetic stated more fully.**

| # | Where | Correction |
|---|---|---|
| 16 | 4.11 | Break-even assumptions now stated: cache hit 0.1 times base input, $0.20 against $2. Cache write 1.25 times. 300 tokens per turn. Warm cost 2,560 + 60 × t millionths of a dollar. Break-even is turn 106 against the summary, 95 against raw retrieval and 174 against extracted facts. The design report's "until about turn 106" for every design is wrong for raw retrieval |
| 17 | 5 | Block edit turn: the script puts the cache write on the first call. It belongs on the second. The total is the same, $0.0262. If Letta skips the refresh, no write happens |

**Additions from saved files. Each is labelled in place.**

| # | Where | Addition | Evidence |
|---|---|---|---|
| 18 | 4.2 | Mem0 2.x corrections reach the store only through explicit `update` or `delete` calls from your code | `M0/docs/core-concepts/how-it-works.mdx` line 51 |
| 19 | 4.12 | LongMemEval keys kept only user-side utterances, so its recall numbers do not test assistant statements | `RM/design/2410.10813.txt` lines 808 to 809 |
| 20 | 4.12 | Mem0 changelog claim "Assistant recall moves from 46% to 100%", as a vendor claim with no conditions | `M0/docs/changelog/highlights.mdx` line 231 |
| 21 | 4.16 | LoCoMo ceiling 93.57% and an independent full-context run of 92.62%, README only | `RM/failures/locomo_audit_README.md` lines 9, 16 and 39 |
| 22 | 4.17 | FactConsolidation single-hop: Mem0 18.0, Zep 7.0, MemGPT 28.0, BM25 48.0, GPT-4o-mini long context 45.0, GPT-5-mini 78.0 | `RM/failures/2507.05257.txt` Table 3, parsed from lines 525 to 915 |

**Overlap.**

| # | Where | Correction |
|---|---|---|
| 23 | 2 | The overlap check had not read Module 1, `inference-internals`, or Module 7, `agent-harness`. Module 1 sections 3.1 to 3.3 own prompt-cache prices. 4.6, 4.11 and section 5 now link them and do not re-teach them |
| 24 | 2 | Added links: Module 2, 2.5 and Module 4, 2.1 for break-even arithmetic. Module 3, 1.3 and Module 4, 1.3 and 1.4 for "a score measures the gold labels". Module 7, 1.1 for the client-side memory tool |
| 25 | 2, 4.15 | Module 11 ownership updated from `eval-engineering/course.json`: judge construction Phase 2, validation Phase 3, sizing Phase 5, broken public benchmarks Phase 6, section 6.4. Module 12 owns online evals and A/B tests. 4.15 now keeps only LoCoMo facts |

### 13.2 Spot checks against the saved source

Every row below was re-read by the reviewer in the named file on 2026-09-23. "Holds" means the exact text or number was found at the stated place.

| # | Concept | Anchor | Result |
|---|---|---|---|
| 1 | 4.1 | `L/schemas/memory.py` lines 149 to 165: `<memory_blocks>`, `chars_current`, `chars_limit` | Holds |
| 2 | 4.1 | `M0/mem0/memory/main.py` line 942 `ADDITIVE_EXTRACTION_PROMPT`, line 1383 `top_k: int = 20` | Holds |
| 3 | 4.1, 4.14 | `L/server/server.py` line 784 `sleeptime_agent_frequency=5` | Holds |
| 4 | 4.1 | Memory tool "operates client-side", `anthropic_memory_tool.md` line 11. Claude Code "first 200 lines", 25KB. OpenAI sessions lines 3 and 114 | Holds |
| 5 | 4.2 | `prompts.py` lines 472 and 612, `how-it-works.mdx` line 51, `highlights.mdx` line 234 | Holds |
| 6 | 4.2 | `main.py` line 1020 MD5 dedup. Letta `base.py` line 265. Mem0 paper line 999 | Holds |
| 7 | 4.3 | `conflict_rank.out`: 6/20, 0/20, 7/20, 0/20 and the four margins | Holds |
| 8 | 4.3 | `W/utils/scoring.py` line 72, "recency" 0 hits. `notices.py` line 134 | Holds |
| 9 | 4.3 | `memory-evaluation.mdx` line 99 quote | Holds. Contradicted by line 95, correction 8 |
| 10 | 4.3 | `lab_correction_race_reworded.txt` "scores: [0.258, 0.2]" | Holds |
| 11 | 4.4 | `edge_operations.py` lines 569 to 570, `graphiti.py` lines 1639 and 1684, `search_filters.py` lines 62 to 65, `search_config.py` line 29 | Holds |
| 12 | 4.4 | `lab_correction_race_default.txt` line 4, reader ignores and honours dates | Holds |
| 13 | 4.4 | One LLM call per new edge | Corrected, correction 7 |
| 14 | 4.5 | Zep paper line 155. `edges.py` lines 271 to 282. `edge_operations.py` lines 563 to 567 | Holds |
| 15 | 4.5 | LongMemEval 11.3% and 6.8%, `2410.10813.txt` lines 999 to 1000 | Holds |
| 16 | 4.6 | `block_manager.py` lines 32 and 268. `letta_agent_v3.py` lines 966 to 967. `constants.py` lines 433 to 434 | Holds |
| 17 | 4.7 | `mem0_leak_probe.out` history rows and "0" Qdrant hits | Holds. Messages table empty, correction 15 |
| 18 | 4.7 | `W/memory/main.py` lines 2100 to 2126, `configs/base.py` lines 42 to 45, `storage.py` line 286 | Holds |
| 19 | 4.7 | `graphiti.py` line 1834 `edge.episodes[0] == episode.uuid` | Holds |
| 20 | 4.7 | `deletion_audit.out`: 5, 4 and 4 byte hits, rows {1, 0, 2, 1} | Holds |
| 21 | 4.7 | `telemetry.py` line 16 PostHog host, default "True" at line 14. `utils.py` line 244 MD5 of `user_id` | Holds |
| 22 | 4.8 | Claude help line 529. ChatGPT "Deleting a chat alone". Gemini "delete all chats". "up to 30 days" | Holds |
| 23 | 4.9 | Probe output with Bob first. `main.py` lines 1457 to 1461. "Unmentioned entities are not constrained". `search_utils.py` lines 228 and 336 | Holds |
| 24 | 4.10 | Mem0 paper lines 256, 259 to 260, 679, 714, 721, 764. 17.117 s and 1.440 s | Holds |
| 25 | 4.10 | Zep DMR lines 305 to 332. LongMemEval_S 71.2, 60.2, 63.8, 55.4 | Holds |
| 26 | 4.10 | LongMemEval lines 79, 479 to 482, 504 to 505 | Holds |
| 27 | 4.10 | BEAM +44.3% and +49.1%, line 1118. 3.5% to 12.69%, lines 27 and 165 | Holds |
| 28 | 4.11 | Cost output file, every row. Mem0 paper line 265. Table 2 tokens 26031, 1764, 3616 | Holds |
| 29 | 4.12 | LongMemEval line 818. Table 3: 0.582, 0.644, 0.615, 0.657. Line 974 | Holds. Wording corrected, correction 6 |
| 30 | 4.12 | Zep Table 3 single-session-assistant 94.6, 80.4, 81.8, 75.0 | Holds |
| 31 | 4.13 | arXiv 2505.16067 Table 1, all 12 values | Holds |
| 32 | 4.13 | HaluMem Mem0 25.50% and 74.02%, MemOS 62.11%. Authors from MemTensor | Holds. The values are the "Medium" setting |
| 33 | 4.14 | LangMem "adds perceptible latency", "Delayed". Mem0 paper line 817 "several hours" | Holds |
| 34 | 4.15 | `membench_prompts.py` partial credit and evidence rule | Holds. Evidence rule is opt-in, correction 1 |
| 35 | 4.15 | `check_locomo_overall.out` "444 of 446". Mem0 paper line 960. MemoryAgentBench line 444 | Holds |
| 36 | 4.16 | Issue #5: 58.44%, 84%, denominator. Zep blog 75.14%, updated 03 Jun 2026. Letta 74.0% and 68.5% | Holds |
| 37 | 4.16 | `memory-evaluation.mdx` lines 73, 131, 137 and 140 | Holds |
| 38 | 4.17 | MemoryAgentBench lines 929 to 930 and Table 3 FC-MH: Mem0 2.0, Zep 3.0, MemGPT 3.0, BM25 3.0, GPT-4o-mini 5.0, GPT-5-mini 28.0 | Holds |
| 39 | 4.17 | BEAM contradiction values 0.000 to 0.053, 48 values | Holds. Line numbers corrected, correction 10 |
| 40 | 4.17 | `memory-evaluation.mdx` line 117, 35.7 and 32.5. `highlights.mdx` lines 228 to 229 | Holds |

### 13.3 Arithmetic recomputed

| Claim | Recompute | Result |
|---|---|---|
| Turn-106 break-even | First t with 2,560 + 60t > 8,900. Assumes cache hit $0.20 per million, 0.1 times the $2 base price, and 300 tokens per turn | 106. Holds. Baseline named, correction 16 |
| Mem0 weighted mean 90.2 | 282 × 91.3 + 321 × 92.0 + 96 × 72.7 + 841 × 91.2, divided by 1,540 | 90.23. Holds. Swapped hop mapping gives 90.27 |
| Zep 18.3% | 71.2 / 60.2 = 1.1827 | 18.3%. Holds. gpt-4o-mini 63.8 / 55.4 = 1.1516, 15.2%. Holds |
| Mem0 latency 91.6% | 1 − 1.440 / 17.117 | 0.9159. Holds |
| Full context minus Mem0 | 72.90 − 66.88 | 6.02 points. Holds |
| Cost table, five prototype rows | Reviewer formulas, not the prototype | All ten values at turns 50 and 200 match |
| Cost table, block rows | 2,000-token block: 0.0086 and 0.0262. 10,000-token block: 0.0102 and 0.0478 | Hold |
| Cost table, graph row | 2,000 + 1,600 + 1,500 + 150 = 5,250 tokens, $0.0084 | Holds |
| Break-it, 6 facts | $0.01948 | Did not hold, correction 3 |
| Break-it, cold | 4 against summary, 3 against raw retrieval | Did not hold as worded, correction 4 |

### 13.4 Conflicts in section 7

| Conflict | Result |
|---|---|
| a. Letta pin | Holds. PyPI JSON today: 0.16.8 on 2026-05-14, then 0.32.13 on 2026-09-17, latest 0.32.18 on 2026-09-23. Summary "Letta Code: stateful agents in your terminal". Not yanked |
| b. LoCoMo length | Holds. `2402.17753.txt` line 166. Mem0 paper line 231. `locomo_tokens.out` mean 17,450.1 and 588.2 turns |
| c. 18.5% against 18.3% | Holds. Paper lines 34, 374 and 375 |
| d. 91.6 or 92.5 | Holds. `highlights.mdx` line 228. Migration guide line 24. Page line 73 |
| e. 92.5 above every category | Holds. Mapping source corrected, correction 9 |
| f. MemoryAgentBench venue | Holds. Line 2 of both saved texts |
| g. BEAM 0.053 against 35.7 | Holds. Line numbers corrected, correction 10 |
| h. When ADD-only arrived | Holds. PyPI JSON today: 2.0.0b0 2026-04-13T10:24, 2.0.0 2026-04-16T11:51, 2.1.0 2026-09-18 |
| i. GitHub latest tag | Holds. `gh_releases_2026-09-23.txt` lines 42 and 47 |
| j. Graphiti line | Holds. Lines 1639 and 1684 |
| k. 91% or 92% | Holds. 91.6% |
| l. Mem0 paper judge | Holds as "not settled". Source of the gpt-4o-mini claim clarified, correction 11 |

### 13.5 Versions checked today

`https://pypi.org/pypi/<name>/json`, fetched 2026-09-23 with `curl --max-time 60`, all HTTP 200.

| Package | Latest | Upload time | Dossier pin | Result |
|---|---|---|---|---|
| `letta` | 0.32.18 | 2026-09-23T06:00Z | 0.16.8 for the server, 0.32.18 for Letta Code | Holds |
| `mem0ai` | 2.1.0 | 2026-09-18T11:12Z | 2.1.0 | Holds |
| `graphiti-core` | 0.30.2 | 2026-09-08T20:39Z | 0.30.2 | Holds |
| `letta-client` | 1.12.1 | 2026-06-02T00:31Z | 1.12.1 | Holds |

### 13.6 Section 4 headings

All 17 headings are claims a senior engineer could get wrong. The reviewer reworded one: 4.11 now says the 100-turn figure holds "under the prototype's prices".

### 13.7 What the reviewer could not check

- No HTTP status in section 9 was re-fetched, except PyPI. The statuses are the research agents' records.
- Not re-read: MemoryAgentBench Table 5, o4-mini 80.0 and 14.0. BEAM "2 questions per ability per conversation". The LangMem rows of 4.1. Letta archival `top_k` 10. Gemini connected-app "days". Claude.ai memory "as you chat". The Letta 0.7.0 and Claude memory rollout dates in section 3. mem0 issue #3944. Graphiti v0.29.0 release text. The OpenAI ChatGPT memory blog.
- Not checked: whether Mem0's published 2026 scores used `--with-evidence`. Section 11, item 39.
- Not checked: whether Mem0 `update()` leaves the old text in history. Section 11, item 40.
- Missing concept for the module question, listed as a gap and not added: a proof that a fact was forgotten, gap 4 in section 8. No saved file has one.

Summary: 25 corrections. Four change what a writer would teach: the opt-in evidence rule, the 62.81% answer type, the two break-it numbers, and the "four parties" count. The pins, the 12 conflicts and the headline arithmetic hold.

# Module 04: Advanced retrieval architectures

Research date: 2026-09-23. Status: research dossier, not course material. Reviewed the same day by an independent reviewer. Section 14, "Review log", lists every correction and every spot check.

Module question: **When is a vector index the wrong tool, and what replaces it?**

## How this dossier was built

- **Inputs.** Five research reports written today in `scratchpad/reports/`: `research_advanced-retrieval_agentic.md`, `_graph.md`, `_novector.md`, `_cache-grounding.md` and `_tenancy.md`. Their saved sources, run files and prototype labs are in `scratchpad/research_advanced-retrieval/<topic>/`. Gap sources fetched for this dossier are in `scratchpad/research_advanced-retrieval/gaps/`, with `fetchlog.txt`.
- **Labels.** Every claim is **verified**, **inferred** or **not checked**. A verified claim names its source and the table or section. "Verified by run" means a script ran on the author's laptop on 2026-09-23 and its output file is named. An inferred claim names its basis and the check that would confirm it.
- **Anchor numbers re-checked.** The dossier author grepped the best piece of evidence for each concept in section 4 again on 2026-09-23. The search ran over the saved source text or run output. All 49 anchor strings were found. One, "72-83%", is split across a line break in the PDF text. This follows audit rule 2 in `curriculum_audit.md`, section 3.4.
- **Machine for every run.** Apple M4 Pro, 14 cores, 24 GiB, macOS, Python 3.12.14 arm64. Other jobs shared the machine during several runs. Treat times as rough.
- **Reviewer re-runs.** The reviewer re-ran L1, L2 and L6 on 2026-09-23. All printed accuracies, differences, p values and win counts matched the saved run files. Only the times differed. The reviewer also ran a new correctness check for L17 on a throwaway PostgreSQL cluster. Files: `scratchpad/review_m04/spot/rerun_*.txt` and `scratchpad/review_m04/l17/`.
- **Terms used in the whole dossier.**
  - **Hybrid retrieval**: BM25 plus a dense retriever, merged with reciprocal rank fusion, RRF. Module 3 Phase 5 teaches it.
  - **Joint recall**: 1 when every gold passage of a question is in the top k, else 0.
  - **Oracle**: a choice that uses the answer labels. It gives the best score any router could reach.
  - **Paired test**: the harness function `common/stats.compare`, a sign-flip randomization test on per-query differences. With 10,000 flips its smallest p is 0.0001.

---

## 1. What this module is for

Module 3 taught how a vector index works and how to measure it. This module asks when a vector index is the wrong tool. The answer depends on the query and the corpus, not on the index.

Five cases need a different tool. Each has a measured failure:

1. **The question needs every matching row.** A top-10 search over a 5,000-row table answered 0% of count, sum and argmax questions. SQL answered 100%. Verified by run, `novector/lab/run_rows.txt`.
2. **The question names an exact key.** BM25 found the file that defines a function name for 98.5% of 200 queries on a Rust code base. bge-small found it for 78.5%. Verified by run, `novector/lab/run_main.txt`.
3. **The question needs a second hop.** With a fixed budget of 10 documents, a two-step search raised joint recall on HotpotQA bridge questions by 0.0625. It lowered comparison questions by 0.1991. Verified by run, `agentic/proto/hop_loop.out`, and re-run by the reviewer with identical output.
4. **The model already knows the answer.** With GPT-3.5 and BM25, one retrieval step scored 55.20 EM on TriviaQA. No retrieval scored 64.00. Verified, Adaptive-RAG, arXiv 2403.14403, Table 8.
5. **The corpus is small enough to read.** On about 248k tokens of machine manuals, the whole corpus in context scored 73.1% and RAG 65.4%, p = 0.0049. It cost about 26.6 times more without a cache. Verified, arXiv 2606.20898, Section 4.1. One preprint.

The module also covers three layers around any retriever. A semantic cache sits in front of the model. A grounding check sits after it. The tenant layout sits under it. Each of them is a similarity decision that can be wrong in a measured way.

The learner builds a customer-support product with a knowledge base. That product has order tables, exact error codes, multi-step policy questions, repeated questions and many customers. So every case above appears in it.

## 2. Scope

### In scope

- Tools that replace or sit next to a vector index: key lookup, SQL and text-to-SQL, grep and file reads, whole-corpus context with prompt caching.
- Deciding whether to retrieve, and how many times: gates, routers, search loops, RL-trained searchers, deep-research systems and their cost.
- Graph-based retrieval: Microsoft GraphRAG, HippoRAG, LightRAG, RAPTOR, and LLM-free entity graphs.
- Semantic caching: thresholds, false hits, near-miss prompts, scope and invalidation.
- Grounding enforcement at answer time: citation features, NLI checkers, and what breaks them.
- Multi-tenant retrieval architecture: index, namespace or filter, and what each costs.
- A decision procedure that ties these together.

### Out of scope, and where it lives instead

| Topic | Where it lives |
|---|---|
| ANN index internals, filtered search mechanics, quantization, RRF, rerankers, chunking, query rewriting | Module 3 |
| Whether the model uses a fact it has in context, effective length | Module 2, 1.1 and 1.2 |
| Sub-agent token cost, multi-agent cost accounting | Module 2, 4.1 |
| Prompt caching rules and break-even | Module 1, 3.2 and 3.3 |
| PDF parsing, OCR, table extraction | Module 5 |
| Memory across sessions, temporal knowledge graphs such as Zep and Graphiti | Module 10 |
| Judge building, judge bias, golden sets, significance method, broken benchmarks | Module 11, 4.2 to 4.9 |
| Tenant isolation as a security boundary, RLS pitfalls, cache sharing attacks, prompt injection through retrieved text | Module 16, 4.8 and Phase 7 |
| Guardrail products as a layer | Module 17 |

### Overlap with Modules 1 to 3

Section links below are to the built documents. Headings were read with `grep '^## '` on 2026-09-23, as audit rule 5 asks.

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| Prompt caching, cache write and read prices | Module 1, 3.2 and 3.3 | Whole-corpus context cost per query against RAG, and cache order for a changing corpus. Link, do not re-teach. |
| Routing cascades between models | Module 1, 3.4 | Routing between retrieval methods. Same control-group idea. Link. |
| Multi-tenant token quotas, `cache_salt`, cache timing side channels | Module 1, 6.2 | Semantic cache timing and collision attacks. Link Module 1 for the prompt cache case. |
| TTFT grows with prompt length | Module 1, 1.2 | The latency side of whole-corpus context. Link. |
| Finding a fact against using it, effective length | Module 2, 1.1 and 1.2 | Only the cost and routing side of long context. Link for quality. |
| Re-reading history makes cost grow with steps | Module 2, 2.1 | Loop cost per retrieval step. Link the formula. |
| Handles instead of payloads | Module 2, 2.4 | Grep output delivered as a file changed results in one study. Link. |
| Sub-agents, Anthropic 90.2%, 4× and 15× token ratios | Module 2, 4.1 | Only as a pointer. Module 2 already corrected how to read these ratios. |
| Two recalls: ANN recall and relevance recall | Module 3, 1.1. Filtered ANN recall is defined in Module 3, Phase 3, line 41 | Filtered ANN recall per tenant. Link both. |
| Averages hide the slice that fails | Module 3, 1.4. Phase 1 line 728 already slices "per customer, grouped by size" | Only the tenant-size slice on a shared index. Link the method. |
| Post-filter starvation, iterative scans, exact search for rare filters, tenant filter as worst case | Module 3, 3.1, 3.2 and 3.3. Module 3, 3.3 already ran real pgvector 0.8.1, lab E12: "the planner chose the B-tree and an exact sort at the 1% and 0.1% shares", Phase 3 line 351 | Row-level security on the tenant column, the planner's switch point by tenant size, and per-tenant memory, billing and lifecycle. Do not re-teach the mechanism or the B-tree exact path. |
| Filter inside the graph walk, the hnswlib sweep | Module 3, 3.4, Phase 3 line 371. Line 433: "The sweep never breaks" | Why the FAISS in-walk filter in 4.27 still starves small tenants. Link. |
| Index memory is the vectors | Module 3, 2.2, "The vector, not the graph, is the memory", Phase 2 line 218 | The reason the per-tenant memory ratio in 4.26 is 1.000. Link. |
| Disk and object storage, cold reads, choosing a system | Module 3, 3.5 and 3.6. Phase 3 line 527 already says "A user who opens a rarely used workspace meets the cold numbers" | Only namespace billing and offload rules. Link for cold reads. |
| Lexical and dense fail on different queries | Module 3, 5.1. Phase 5 line 103: "Order numbers and error codes are the extreme of a rare word" | Only the code corpus and the tokenizer condition. Link the mechanism. |
| RRF and its k | Module 3, 5.2 | RRF as the seed for graph walks and the baseline for routers. Link. |
| Query rewriting helps a weak retriever and adds an LLM call | Module 3, 6.1 and 6.2 | Module 3, 6.2 says "Deciding per query whether to rewrite is routing, which Module 4 covers". This module covers it. |
| Contextual retrieval cost with today's cache rules | Module 3, 6.5 | The same cost method, applied to whole-corpus context. Link. |
| Deleted vectors stay readable | Module 3, 7.3 | Not repeated. Module 16 owns the threat. |
| A semantic cache can return a wrong or another user's answer. Azure threshold advice | Module 1, 5.6, `inference-internals-phase-05b-observability.md` lines 492 to 496. The Module 1 coverage file does not list it | Measured false hits, near misses, thresholds per library, verifiers. Link Module 1, 5.6 in 4.20 and 4.22. |
| Literal against latent questions, and distractors that share words | Module 2, 1.3, `phase-01-why-long-runs-fail.md` line 307 | The distractor mechanism behind 4.9. Link. |
| A cascade that answers cheaply and escalates on a signal | Module 1, 3.4, `phase-03b-routing-alerting.md` line 31 | Self-Route in 4.5 and the gates in 4.12 have this shape. Link. |

**Module 3 already runs pgvector.** An earlier draft of this dossier said Module 3, Phase 3 claims "pgvector itself never runs here". That claim is stale. Verified by the reviewer: the phrase is no longer in the file. Phase 3 line 31 now says its lab E12 "was run" on PostgreSQL 14.24 with pgvector 0.8.1 from Homebrew. Line 748 warns that pgvector 0.6.0 to 0.8.1 have CVE-2026-3172, and says to use 0.8.1 "only in a throwaway cluster with public data". L17 in this module builds on E12 and must carry the same warning.

## 3. What changed recently

| Change | Date | Source | Why it matters |
|---|---|---|---|
| OpenAI deep research launch | 2025-02-02 | OpenAI post, read in a browser because curl got 403 | First mass-market search agent. 5 to 30 minutes per task. |
| Deep research system card | 2025-02-25 | cdn.openai.com PDF | The model is "an early version of OpenAI o3 that is optimized for web browsing", trained with RL on browsing tasks. |
| Search-R1 and other RL-trained searchers | 2025-03 to 2025-08 | arXiv 2503.09516, COLM 2025, and others | Search policies trained on open models. The retriever quality still sets the result. |
| BrowseComp | 2025-04-16 | arXiv 2504.12516 | Hard browsing benchmark on the live web. Not reproducible. |
| Claude Code states it dropped a vector index for grep | 2025-05-07 | Latent Space podcast | Evidence was "mostly vibes". |
| Azure AI Search agentic retrieval | 2025-05-19 | Microsoft post and Learn pages | LLM query planning ships as a search API. |
| Anthropic multi-agent research post | 2025-06-13 | Anthropic Engineering | Token use explains 80% of BrowseComp variance. |
| LazyGraphRAG moves into Microsoft products, not the open repository | 2025-06-06 | Microsoft blog editor's note | Not in `graphrag` 3.1.2. |
| BrowseComp-Plus | 2025-08-08 | arXiv 2508.06600, ACL 2026 per its README | A fixed corpus separates retriever quality from agent quality. |
| Cursor semantic search post | 2025-11-06 | cursor.com | Vendor evidence against grep-only code search. |
| Qdrant 1.16 tiered multitenancy | 2025-11-19 | Qdrant blog | Shared shard for small tenants, dedicated shards for large ones. |
| Text-to-SQL annotation error study | 2026-01-13, v3 2026-01-19 | arXiv 2601.08778; CIDR 2026 version | 52.8% of BIRD Mini-Dev examples have annotation errors. Leaderboard ranks move up to 9 places. |
| CacheAttack, ICML 2026 | 2026-01-30 | arXiv 2601.23088 | Cross-user semantic cache hijacking at 86% hit rate. |
| vCache, ICLR 2026 | 2026-02-21 | arXiv 2502.03771 v5 | Per-entry learned thresholds with a user-set error bound. |
| Claude web search with dynamic filtering | tool version 2026-02-09 | Claude web search tool docs | The model filters search results in code before they enter context. |
| ReaLM-Retrieve, SIGIR 2026 per arXiv comment | 2026-04-29 | arXiv 2604.26649 | Loop overhead is small next to reasoning tokens. Absolute values conflict with other papers. |
| Direct Corpus Interaction preprint | 2026-05-03 | arXiv 2605.05242 | Grep agent accuracy fell to 37.5% at 400K documents. |
| Token Tax preprint | 2026-06-18 | arXiv 2606.20898 | Long context beat RAG on current OpenAI models, at 26.6 times the token cost without caching. |
| Operational Gap in semantic caching, EMNLP 2026 Industry | 2026-06 to 2026-09 | arXiv 2606.19719 | Choose cache models by precision at a threshold, not PR-AUC. |
| microsoft/graphrag maintenance notice | 2026-08-14 | README at v3.1.2, commit 21f7bdf6bd | "largely in maintenance mode". |
| Qdrant 1.19 per-tenant IDF | 2026-08-05 | Qdrant release | Lexical statistics per tenant became a documented option. |
| Marten issue #5419 | 2026-09-14 | GitHub | The maintainer reported and fixed a 40-row cap in a library's pgvector search. The issue describes the tenant-filter case. The reproduced failure was the cap itself. |
| GPTCache PR #702 benchmark | 2026-09-22 | GitHub | The default cross-encoder verifier had 42.2% precision on all 1,536 reuse labels, and 43.9% on the 1,152-row test split. One day old. |
| Anthropic pricing: Sonnet 5 at a flat rate over its 1M window | fetched 2026-09-23 | platform.claude.com pricing | Long-context input got cheaper per token. |
| Spider 2.0-Snow top score 96.70 | fetched 2026-09-23 | spider2-sql.github.io | Up from 21.3% at launch. See 4.4 for why this number needs care. |

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. The numbering is kept from the first draft so that the review log can refer to it. The reviewed phase structure in section 5 merges some concepts and moves others. Section 5 gives the final claim sentence for each concept. Where a heading below was rewritten in review, the old heading is gone and a **Review** line says what changed.

### 4.1 A vector index returns k rows, so it cannot answer a question that needs every matching row

A count, a sum, an average or "which is largest" needs every row that matches a condition. Top-k retrieval returns k rows. A larger k helps only while k exceeds the number of matching rows, and the system does not know that number in advance.

- **Lab, verified by run.** The data is a seeded synthetic SQLite orders table with 5,000 rows. It has 200 questions. There are 50 each of ID lookup, count with two filters, sum with two filters, and argmax by city. The reader is an oracle that applies the exact filter to the retrieved rows, so every error is a retrieval error. SQL answered 1.00 of every type. bge-small top-10 answered 0.32 of lookups and 0.00 of count, sum and argmax. Matching sets held 46 to 88 rows. SQL minus bge-small top-10 was +0.920, p = 0.0001, 184 wins and 0 losses. Source: `novector/lab/run_rows.txt`.
- **Break-it, verified by run.** BM25 top-100 answered every count and sum question at 5,000 rows, because no matching set exceeded 89 rows. At 50,000 rows the sets held 581 to 751 rows, and BM25 top-100 answered none. Source: `novector/lab/run_rows_50k.txt`. So "top-100 works" was luck of the table size.
- **Published, verified, indirect.** TAG, Biswal et al., UC Berkeley and Stanford, arXiv 2408.14717, preprint. 80 BIRD-derived questions, Llama-3.1-70B-Instruct, exact match. Row-level RAG with E5-base, FAISS and 10 retrieved rows scored 0.00 overall. Text2SQL scored 0.17. A hand-written pipeline scored 0.55. Source: Table 1. **Review:** the "overall" score covers only 60 of the 80 questions. Table 1, footnote 1: "Excludes aggregation since accuracy is not measured." The 20 aggregation questions got only a qualitative analysis. So TAG does not measure top-k on aggregates. Use it only as evidence that row retrieval fails on match, comparison and ranking questions over tables.
- **Published, verified.** TableRAG, NeurIPS 2024, National Taiwan University and Google. Tables of 62,000 to 79,000 rows on average, GPT-3.5 Turbo. Row and column embedding retrieval scored 37.7 on ArcadeQA. Schema only with program execution scored 43.1. The whole table in context scored 4.6, because most tables did not fit. Source: Table 2.
- **Published, verified.** LOFT, Google DeepMind, arXiv 2406.13121, preprint. With 128k tokens of database in context, Spider accuracy was 0.40 for Gemini 1.5 Pro. The DAIL-SQL pipeline with the same model scored 0.74. The paper says "averaging is the most difficult operation". Source: Table 2 and Figure 6.

### 4.2 An exact key beats dense retrieval only while the query and the index split the key into the same tokens

**Review.** Old heading: "only while the tokenizer keeps the key whole". The break-it below changes the query, not the tokenizer. The index still keeps `snake_case` whole, and the query "build sandbox policy" no longer matches it. The mechanism is Module 3, 5.1: link it. Section 5 merges 4.2 and 4.3 into one Phase 1 concept.

- **Lab, verified by run, re-run by the reviewer with identical output.** Corpus: openai/codex at tag rust-v0.156.1, `codex-rs/core/src` without tests. 378 files, 3,970 chunks of 30 lines, doc comments stripped. Queries: 200 function names defined once. Gold: the defining file. File-level hit@5: BM25 0.985, grep ranked by match count 0.985, bge-small 0.785, MiniLM 0.770. BM25 minus bge-small +0.200, p = 0.0001, 95% CI +0.145 to +0.260, 41 wins and 1 loss. Source: `novector/lab/run_main.txt` and `review_m04/spot/rerun_ident.txt`. Seed 1 gave +0.190.
- **The condition, verified by run.** The same names were then written as words, for example "build sandbox policy" for `build_sandbox_policy`. BM25 hit@5 fell to 0.595. bge-small stayed at 0.780. Source: `novector/lab/run_split.txt`. The bm25s 0.3.11 default token pattern `(?u)\b\w\w+\b` keeps `snake_case` whole. Verified, bm25s `tokenization.py` line 572.
- **A teaching detail, verified by run.** grep hit@1 was 0.760, not 1.0. Call sites often outnumber the definition. A `fn name` pattern would be exact.
- **Published, verified.** EntityQuestions, Princeton, EMNLP 2021. Top-20 accuracy on simple entity questions: DPR trained on NQ 49.7, BM25 72.0. Source: Table 1. DPR is a 2020 model. Whether current embedders close this gap is not checked.
- **Published, verified.** LIMIT, Google DeepMind and Johns Hopkins, ICLR 2026. On the 46-document version, recall@2 was BM25 97.8, GTE-ModernColBERT 83.5, Qwen3 Embed 19.0. Source: Figure 6, arXiv 2508.21038.
- **Vendor illustration, verified text, no measurement.** Anthropic's Contextual Retrieval post uses "Error code TS-999" as a case an embedding model "could miss". 2024-09-19.

### 4.3 On a description query, dense retrieval wins on the same corpus, so the query type decides and not the corpus

This is the same mechanism as Module 3, 5.1. Here it is shown on code, where learners most often conclude "grep is enough". **Review:** Module 3, 5.1 and Module 3, 1.4 already teach this claim. Phase 5 line 51 and Phase 1 line 381 show the flip on BEIR. Teach 4.3 only as the code-corpus case of 5.1, in a few lines, inside the merged concept in section 5.

- **Lab, verified by run.** Same code corpus as 4.2. Queries: 200 doc comments of 6 or more words, function name removed, comments stripped from the index. Hit@5: bge-small 0.790, MiniLM 0.755, BM25 0.635. bge-small minus BM25 +0.155, p = 0.0001, 95% CI +0.085 to +0.225. Seed 1 gave +0.145, p = 0.0002. Source: `novector/lab/run_main.txt`, `run_seed1.txt`.
- **Published, verified.** JetBrains Research, arXiv 2510.20609, preprint. "For PL-PL, sparse BM25 with word-level splitting is the most effective and practical". For bug localization from issue text, Voyage-3-code reached about 0.72 NDCG against BM25 about 0.57. Source: abstract and Section 4.3.
- **Published, verified from abstract.** CodeRAG-Bench, CMU and others, arXiv 2406.14497 v2. "current retrievers still struggle to fetch useful contexts especially with limited lexical overlap". Venue not checked. Source: `gaps/coderagbench.html`.
- **Published, verified from abstract.** CoIR, ACL 2025 Main. Ten code datasets, eight retrieval tasks, seven domains, nine models, with "significant difficulties in performing code retrieval tasks even with state-of-the-art systems". It uses the MTEB and BEIR data schema. Source: `gaps/coir.html`. Per-task tables not read.
- **Published, verified, re-fetched by the reviewer.** LIMIT, the reverse case. With every item replaced by a synonym, BM25 fell from 97.8 to 10.6 recall@2. "BM25 drops more than 89% whereas Qwen3 embedding drops 38.9%". Source: Section 5.2 and Figure 6. **Review, added condition:** every model failed on the synonym version. The best, GTE-ModernColBERT, scored 25.6. Qwen3 Embed scored 11.6, only 1 point above BM25. Gemini 2.5 Pro wrote the synonyms. So this result shows lexical matching collapsing without shared words. It does not show dense retrieval succeeding.

### 4.4 Text-to-SQL is the replacement for aggregate questions, but its benchmark scores are not reliable accuracy numbers

This concept was researched for this dossier. The five reports gave leaderboard numbers only.

- **How text-to-SQL fails, verified.** Spider 2.0, University of Hong Kong and others, ICLR 2025 oral. Error analysis of 300 sampled examples from two code-agent frameworks: erroneous data analysis 35.5%, of which dialect functions 10.3%, advanced calculation 7.5%, query planning 17.7%. Wrong schema linking 27.6%, of which column linking 16.6% and table linking 10.1%. JOIN errors 8.3%, because BigQuery databases "often lack explicit foreign key". Spider 2.0-lite databases average "over 755" columns against "approximately 54 in BIRD". Source: `gaps/spider2_2411.07763.txt`, section "Error analysis of SQL generation", Figure 4.
- **Launch score, verified.** An o1-preview code agent solved 21.3% of Spider 2.0 tasks. Source: abstract. **Review:** the 91.2% on Spider 1.0 and 73.0% on BIRD are earlier GPT-4-based methods, not the o1-preview agent. Source: Section 1, "methods based on GPT-4 achieved execution accuracy of 91.2% and 73.0%".
- **The labels are often wrong, verified.** Jin, Choi, Zhu and Kang, UIUC, arXiv 2601.08778 v3, 2026-01-19. A shorter version is in CIDR 2026. Experts found annotation errors in 263 of 498 BIRD Mini-Dev examples, 52.8%, and in 76 of the 121 Spider 2.0-Snow examples with public gold SQL, 62.8%. Error classes: SQL does not match the question, SQL does not match the data or schema, wrong domain knowledge, and ambiguous questions. Source: `gaps/sqlerr_2601.08778.txt`, Section 4.3 and Section 1.
- **Rankings move, verified.** The same paper re-evaluated all 16 open-source agents from the BIRD leaderboard, chosen by the ranking of 2025-08-20. On a corrected Dev subset, scores changed by −7% to +31% relative, and ranks moved from −9 to +9. CHESS went from 62% to 81% and from 7th to 1st. Rankings on the uncorrected subset correlate with the full Dev set at Spearman 0.85, p = 3.26e-5. They correlate with the corrected subset at 0.32, p = 0.23.
- **The two versions disagree, verified.** The CIDR 2026 abstract says 66.1% for Spider 2.0-Snow and changes of −3% to 31% for five methods. The arXiv v3 says 62.8% and 16 agents. Source: `gaps/cidr_textsql.txt` and the arXiv abstract. Quote the arXiv v3 numbers with their sample sizes.
- **Leaderboard today, verified.** The top Spider 2.0-Snow entry, Genloop's Sentinel Agent v2 Pro, scores 96.70 on 547 tasks. The page says "the scores may change slightly over time" and excludes methods that use ground-truth tables. Source: `gaps/spider2.txt`. BIRD's top test-set execution accuracy is 82.39, dated 2026-09-07, with human performance listed at 92.96. Source: `novector/lb_bird.txt`.
- **Inferred.** A 96.70 score against a gold set whose public part had 62.8% annotation errors means one of two things. Either the organizers corrected the gold, or a high score partly reproduces flawed gold. The page does not say which. Check: read the Spider 2.0 data update log linked on the page, and compare it with the error list at github.com/uiuc-kang-lab/text_to_sql_benchmarks.
- **Where SQL still loses, verified.** TAG Table 1: Text2SQL scored 0.10 on ranking questions that need judgment over text in cells.
- **Teaching consequence, inferred.** Measure text-to-SQL on your own schema with your own reviewed questions. A public leaderboard score is not an accuracy estimate for your database. Module 11, 4.9 owns the general lesson on broken benchmarks. Link it.

### 4.5 Whole-corpus context is a cost decision first: quality results split by model and task, and prompt caching cuts the cost gap but does not remove it

**Review.** Old heading: "The whole corpus in context can beat RAG on quality, and prompt caching cuts its cost but does not remove it". The only current-model evidence for "beats" is one preprint, Token Tax. LaRA, peer reviewed, found the opposite on average at 128k. So the course must present quality as "it depends on model and task", with both results side by side. The cost half of the claim is arithmetic on today's prices and is safe. Module 1, 3.3 teaches the break-even method, and Module 2, 1.1 and 1.2 own quality at length. Self-Route has the cascade shape of Module 1, 3.4. Link all three.

- **Quality, LC wins, verified.** Hamilton et al., Miami University and University at Buffalo, arXiv 2606.20898, preprint 2026-06-18. 162 expert questions on 3 machine manuals, about 247,754 input tokens, gpt-5.4-mini and gpt-5.4-nano, GPT-5 Pro judge. On 324 matched pairs LC scored 73.1% and semantic RAG 65.4%, McNemar p = 0.0049. Mean cost $0.1181 against $0.0045. Latency difference not significant, p = 0.128. Source: Sections 4.1 to 4.3. **This is one preprint.** It is the only current-model evidence in this concept.
- **The study paid full input price, inferred.** gpt-5.4-mini input is $0.75 per million tokens. 247,754 × $0.75 / 1M = $0.1858, and the paper's LC mini mean is $0.1864. So no cache discount was applied. At the $0.075 cached price the LC input would be about $0.019. Check: rerun their code with caching on.
- **Quality, RAG wins, verified.** LaRA, HKUST, Alibaba and Penn State, ICML 2025. 2,326 questions, each on one long document. At 128k, RAG beat LC by 3.68 points on average over 11 models. On hallucination detection RAG was better by 22.36 points. On comparison LC was better by 14.30. Source: Table 2, "Avg GAP" rows. All models are from 2024.
- **Route between them, verified.** Self-Route, Google DeepMind and University of Michigan, EMNLP 2024 industry track. The model answers from retrieved chunks or says "unanswerable". Only unanswerable queries go to full context. GPT-4O used 61% of the tokens for 46.83 against LC 47.04. For 63% of queries the two predictions were identical. Source: Sections 4.1 and 4.3.
- **Cost today, verified arithmetic on prices fetched 2026-09-23.** Assumptions: question 50 tokens, output 300, RAG context 5,000 tokens, thinking off, warm cache, 60 queries per hour. The "warm cache" column adds one full cache write per hour, spread over the 60 queries. Source: `novector/cost/cost_out.txt`. **Review:** the reviewer re-fetched the Anthropic and OpenAI price pages on 2026-09-23 and recomputed the claude-sonnet-5 100,000-token row and the gpt-6-luna 900,000-token row by hand. Sonnet 5 is $2 input, $2.50 5-minute cache write, $0.20 cache read and $10 output per million tokens. gpt-6-luna is $0.10, $0.125, $0.01 and $0.50, with the 272K rule. All four cells matched.

| Model | Corpus tokens | LC, no cache | LC, warm cache | RAG, 5k | Cached LC / RAG |
|---|---|---|---|---|---|
| claude-sonnet-5 | 100,000 | $0.2031 | $0.0273 | $0.0131 | 2.1× |
| claude-sonnet-5 | 900,000 | $1.8031 | $0.2206 | $0.0131 | 16.8× |
| gpt-6-luna | 100,000 | $0.0102 | $0.0014 | $0.00065 | 2.1× |
| gpt-6-luna | 900,000 | $0.1802 | $0.0220 | $0.00065 | 33.6× |
| gemini-3.8-flash | 500,000 | $0.3762 | $0.0491 | $0.00491 | 10.0× |

- **Price rules behind the table, verified.** Anthropic: "A 900k-token request is billed at the same per-token rate as a 9k-token request." OpenAI: prompts over 272K input tokens are "priced at 2x input and cache rates and 1.5x output for the full request." Sources: first-party pricing pages, fetched 2026-09-23.
- **Inferred.** Gemini explicit cache creation was priced at the normal input rate in the script. Check: ai.google.dev caching docs.
- **Module 2 owns quality at length.** Link Module 2, 1.1 and 1.2 for whether the model uses facts at these lengths.

### 4.6 A cached corpus must be ordered by how often each document changes

**Review.** Mostly taught already. Module 1, 3.2 teaches the prefix rule, `inference-internals-phase-03a-caching.md` line 389: "A change at one level breaks that level and every level after it". Its lab moves the changing block to the end, line 522. Module 2, 2.2 prices one break as `(w − r) × C`. Only the application to documents is new. Section 5 folds 4.6 into 4.5 as one paragraph with links.

- **Verified.** Anthropic's prompt cache is a prefix cache: "Changes at each level invalidate that level and all subsequent levels." Source: platform.claude.com prompt caching docs, "What invalidates the cache".
- **Inferred.** An edit to a document in the middle of a cached corpus invalidates every document after it. Appending new documents at the end keeps the earlier prefix valid. So put stable documents first and changing ones last. Check: send two requests with a mid-corpus edit and read `cache_read_input_tokens`. Module 2, 2.2 gives the cost of one break, `(w − r) × C`. Link it.
- **Break-it, inferred.** At one query per hour the 5-minute cache expires between queries. Then every query pays the write premium, about 1.25 times the uncached input price on Anthropic. **Review:** setting `qph` to 1 in `cost_per_query.py` does not show 1.25. The script then charges a full write and a full cache read for the corpus, so it prints about 1.35 times. The L4 self-test must fix the formula: with no warm cache, charge the write only.

### 4.7 Grep at query time removes index staleness, and its cost moves to query time where it grows with corpus breadth

- **What shipping coding agents use, verified from docs and source.** Claude Code's tool reference lists no semantic search tool. On macOS, Linux and WSL it "searches with `find` and `grep` through the Bash tool". Source: code.claude.com/docs/en/tools-reference. Codex CLI's prompt at rust-v0.156.1 says "prefer using `rg`". Source: `codex-rs/core/gpt_5_codex_prompt.md` line 5. Gemini CLI v0.60.0 ships glob, grep and ripgrep tools, and `generateEmbedding` has no caller outside tests. Source: `packages/core/src/`. The Claude Code client source was not read.
- **The stated reason, verified.** "primitives like glob and grep allow it to navigate its environment and retrieve files just-in-time, effectively bypassing the issues of stale indexing". Source: Anthropic, "Effective context engineering for AI agents", 2025-09-29. The same post says "runtime exploration is slower than retrieving pre-computed data".
- **Scaling limit, verified.** Li et al., "Direct Corpus Interaction", arXiv 2605.05242, preprint. Claude Code with Claude Sonnet 4.6, on a 100-question subset of BrowseComp-Plus, with FineWeb distractors added. From 100K to 200K documents, tool calls per question rose from 38.5 to 86.9 and accuracy fell 13.6 points. At 400K documents accuracy was 37.5%, tool calls 122.4, and 20 of the 100 questions hit the tool budget. Source: Section 4.3, RQ4, and the Figure 5 caption, "n = 100". **Present as:** one preprint, one model, 100 questions. The direction is the teaching point, not the numbers.
- **The same paper's headline, verified, with a warning.** Shell access instead of a Qwen3-Embedding-8B tool "improves accuracy from 69.0% to 80.0%" at 100K documents. But its Table 3 gives BM25 15.8 nDCG@10 on 50 SciFact queries. Over 100,000 random 50-query subsets of the harness BM25 run, the lowest mean was 0.4658. Verified by run, `novector/lab/run_dci_check.txt`. **Inferred:** their BM25 baseline differs from standard BEIR BM25. Do not cite its IR ranking gains until their code is rerun.
- **Index cost, verified as a vendor statement.** Cursor says large repositories "can take hours to process if indexed naively". Source: cursor.com, "Securely indexing large codebases", 2026-01-27.

### 4.8 Grep against embeddings in an agent is not settled, because every study changes more than the retriever

- **Anthropic, verified.** Agentic search with glob and grep "outperformed everything. By a lot." Then: "This was just vibes, so internal vibes." Source: Boris Cherny, Latent Space podcast, 2025-05-07. A 2026-02-01 post says early Claude Code "used RAG + a local vector db". Read through the api.fxtwitter.com mirror.
- **Cursor, verified.** Semantic search plus grep gave "on average 12.5% higher accuracy in answering questions (6.5%–23.5% depending on the model)" than grep alone, on Cursor's own Context Bench. Online A/B: code retention +0.3%, and +2.6% on codebases of 1,000 files or more. Source: cursor.com/blog/semsearch, 2025-11-06. No sample size, interval or public dataset. It does not say whether 12.5% is relative.
- **GitHub Copilot, verified.** A new code embedding model gave a "+37.6% relative lift" from 0.362 to 0.498. The benchmark mix is not named. Source: github.blog, 2025-09-24.
- **Output delivery moves the result, verified.** Sen et al., PwC, arXiv 2605.15184, preprint. 116 LongMemEval questions, not code. "inline grep exceeds inline vector for every harness–model pair". When results were written to a file for the model to read, vector won in 5 of 10 pairs. Codex with GPT-5.4 fell from 93.1% to 55.2% with file-based grep. Link Module 2, 2.4 on handles.
- **Low-precision pre-retrieval hurts an agent, verified.** CodeGrep, NetEase, arXiv 2608.05886, preprint. SWE-Bench Verified, OpenHands with Qwen3-30B. BM25 file hints at precision 0.375 "degrades the agent". An RL grep agent at precision 0.677 raised resolve rate from 25.8% to 27.0%.
- **Inferred synthesis.** Both vendor positions fit one mechanism. Grep wins when the agent can guess exact identifiers and can afford many calls. An embedding tool adds value when names differ from the words in the question and the repository is large. Cursor's own gain grows with codebase size. Check: one agent, one harness, with and without a vector tool, on a public code QA set split by repository size. No such study was found.

### 4.9 Retrieval can lower accuracy, so "always retrieve" is not a safe default

- **Verified.** Adaptive-RAG, KAIST, NAACL 2024. GPT-3.5, BM25, 500 questions per dataset. Average over six datasets: no retrieval 35.77 EM, one retrieval 34.73 EM. TriviaQA: 64.00 against 55.20. Source: Tables 1 and 8.
- **Verified.** Moskvoretskii et al., arXiv 2501.12835, preprint. LLaMA 3.1-8B-instruct, BM25, 500-question subsets. TriviaQA: Never RAG 0.636, Always RAG 0.610. Source: Table 1.
- **Why, verified.** Mallen et al., ACL 2023: "For 10% of questions, retrieval-augmentation causes the LM to incorrectly answer a question it could otherwise answer correctly." On those questions recall@1 was 0.14 against 0.42 overall. Conditions: GPT-3 davinci-003 with Contriever, on PopQA. Source: Section 5 and Table 1.
- **The same pattern on a second dataset, verified by the reviewer.** Adaptive-RAG Table 8, GPT-3.5, Natural Questions: no retrieval 39.80 EM, one retrieval 32.40.
- **Retrieval also raises hallucination, verified, gap research.** CRAG, Meta, NeurIPS 2024 Datasets and Benchmarks. 4,409 questions, five domains, mock web and knowledge-graph APIs. GPT-4 Turbo alone: accuracy 33.5%, hallucination 13.5%. The same model with five web pages, Task 1: accuracy 35.9%, hallucination 28.2%. These are auto-eval numbers, the average of a ChatGPT and a Llama 3 grader. The paper says "none of the RAG solutions obtain truthfulness higher than 20%". Truthfulness scores perfect 1, acceptable 0.5, missing 0 and incorrect −1. Source: `gaps/crag_2406.04744.txt`, Table 5 and Section 4.2.
- **Industry systems in 2024, verified.** On CRAG with human grading, equal weights: Copilot Pro 62.6% perfect, 17.9% hallucinated, 11,596 ms. Perplexity.ai 55.8% perfect, 25.3% hallucinated, 4,634 ms. Meta SG 3,431 ms. Source: Table 6. These are 2024 products.
- **Retrieval lowers abstention, see 4.25.**

### 4.10 Under a fixed document budget, a search loop pays off on bridge questions and loses on single-hop and comparison questions

**Review.** Old heading had no budget condition. In the lab, the loop splits 10 documents into 5 plus 5. Even the oracle reader lost 0.2239 on comparison questions, verified by the reviewer's re-run, `review_m04/spot/rerun_hop_loop.txt`. So the comparison loss comes from the budget split, not from bad hop choices. A comparison question names both entities, so one search already finds both. Teach the budget as part of the claim.

- **Verified.** Adaptive-RAG Table 2, FLAN-T5-XL 3B, BM25. Multi-step IRCoT against one retrieval: HotpotQA 44.60 against 34.40 EM at 9.38 times the time. MuSiQue 23.00 against 13.80. SQuAD 24.40 against 27.80, a loss.
- **Lab, verified by run, re-run by the reviewer with identical output.** HotpotQA distractor dev, 7,405 questions, 66,581 paragraphs, BM25, 10-document budget. A two-step loop with a top-1 stand-in reader against one search: bridge questions +0.0625 joint recall, p = 0.0001, 95% CI +0.0519 to +0.0732. Comparison questions −0.1991, p = 0.0001. All questions +0.0100, p = 0.0525 with 1,000,000 sign patterns, not significant. Source: `agentic/proto/hop_loop.out`.
- **Gap research, verified.** FRAMES, Google, NAACL 2025. 824 multi-hop Wikipedia questions. Gemini-Pro-1.5-0514: no retrieval 0.408, BM25 top 2 articles 0.452, top 4 0.474, all gold articles 0.729. A multi-step BM25 pipeline with search planning reached 0.66. The LLM autorater agreed with humans at accuracy 0.96, kappa 0.889. Of oracle errors, about 80% were numerical, tabular or post-processing. Source: `gaps/frames_2409.12941.txt`, Table 3 and Section 3.2.
- **Inferred.** FRAMES shows the loop recovering most of the gap to the oracle on multi-hop questions. The remaining oracle errors are reasoning errors that no retriever fixes.

### 4.11 A loop does not replace a good index: a better retriever inside the loop gives higher accuracy with fewer searches

- **Verified.** BrowseComp-Plus, University of Waterloo and others, arXiv 2508.06600. 830 queries, fixed corpus of 100,195 documents, top 5 results cut to 512 tokens, gpt-4.1 judge. gpt-5 with BM25: 55.90% accuracy, 23.23 search calls per query. gpt-5 with Qwen3-Embedding-8B: 70.12%, 21.74 calls. Source: Table 1.
- **Cost, verified and inferred.** Table 8 gives total API cost for 830 queries. gpt-5: $400.36 with BM25 and $360.71 with Qwen3-Embed-8B. Per query that is $0.482 and $0.435, inferred by division. The better retriever was cheaper for every model listed.
- **Verified.** Jin et al., arXiv 2505.15117, preprint. Qwen2.5-7B-Base trained with PPO, average EM over seven sets: random engine 0.241, BM25 0.352, E5 with HNSW 0.379, exact E5 0.430. Source: Table 4. Module 3, 1.1 explains why HNSW and exact differ.
- **Verified.** BrowseComp, OpenAI, arXiv 2504.12516. GPT-4o 0.6%, GPT-4o with browsing 1.9%, Deep Research 51.5%. Deep Research "is trained on data that specifically teach the model to be good at BrowsingComp tasks." Source: Table 3 and footnote 1. So the browsing tool added 1.3 points to GPT-4o. **Review, over-claim removed.** The old text said "The trained policy made the difference." Deep Research is a different base model, an early o3, and it was also trained on browsing tasks. The comparison changes the model and the training together. It cannot say which one made the difference. Teach only: giving a model a search tool is not enough on this benchmark.

### 4.12 On single-hop questions a cheap gate matches complex adaptive methods at a fraction of the calls, but no router so far comes close to its oracle

**Review.** Old heading: "A cheap gate or router gets most of the gain, and the router is the weak part". "Most of the gain" held on NQ but not on 2WikiMultihopQA, in the same table. The new heading states the condition. Module 1, 3.4 teaches the control-group method for routers. Module 3, 5.1 line 101 says the slices "need the labels, so you cannot route queries with them", which explains why the L7 router collapsed. Link both.

- **Verified.** Moskvoretskii et al., Table 1, NQ. The best uncertainty gate scored 0.512 In-Accuracy with 1.8 LM calls and 0.81 retrieval calls per question. DRAGIN scored 0.480 with 4.5 LM calls. SeaKR 0.406 with 14.6.
- **Where it does not hold, verified.** Same table, 2WikiMultihopQA: IRCoT, Adaptive-RAG and DRAGIN scored 0.454 to 0.456. The best gate scored 0.384.
- **Verified.** Adaptive-RAG with GPT-3.5: Adaptive-RAG 37.97 EM at 1.46 times one-step time. Multi-step 38.13 at 3.33. An oracle classifier would reach 47.70. Source: Table 1. The classifier, a T5-Large of 770M parameters, had 54.52% accuracy overall and 30.52% on the "no retrieval" label. Source: Table 4. **Review:** Table 4 is in the FLAN-T5-XL setting, its QA F1 46.94 equals the FLAN-T5-XL row of Table 1. Do not attach the 54.52% to GPT-3.5.
- **Lab, verified by run.** Per-query router between BM25 and bge-small on SciFact, NFCorpus and SciDocs, logistic regression on six features, 5-fold CV. The oracle was 0.0605 nDCG@10 above dense on SciFact. The router collapsed to "always dense" and gained −0.0011 to +0.0001, none significant. Source: `agentic/proto/retriever_router.out`. The features used dense scores, so this is an upper bound for a router that saves cost.
- **Verified.** RouterRetriever, AAAI 2025. Average nDCG@10 over seven BEIR sets: best single model 47.5, router 49.6, per-query oracle 57.6. Source: Table 1.

### 4.13 The cost multiplier of an agentic loop depends on the model and the baseline, from about 1 to about 10 times

- **Short-answer model, verified.** Adaptive-RAG Table 3: 0.35 s per query with no retrieval, 3.08 s with one step, 27.18 s with multi-step. The caption does not name the model.
- **Reasoning model, verified.** ReaLM-Retrieve, SIGIR 2026 per arXiv comment, Table 4. DeepSeek-R1-Distill-Qwen-32B on MuSiQue, 8 A100 GPUs: no retrieval 12.4 s and 8,432 tokens. One retrieval 13.2 s and 9,156. IRCoT 18.7 s and 11,284. **Caution, inferred:** its no-retrieval MuSiQue EM of 41.2 conflicts with 2.40 in Adaptive-RAG. Treat its absolute values as unconfirmed.
- **Against a tuned fixed pipeline, verified.** "Is Agentic RAG worth it?", ACL 2026 Industry Track. Table 9 ratios: FIQA time 1.5, input tokens 2.7, output 1.7. CQADupStack-EN time 1.4, input 3.6, output 1.8. The text says 3.3 times input. Quote Table 9. The paper says "The dominant factor in latency is the LLM calls", with retrieval "0–5%" of time.
- **Per-search price, verified, gap research.** Claude web search costs "$10 per 1,000 searches, plus standard token costs for search-generated content", and results count as input tokens in later turns. Source: `gaps/claude_websearch.txt` lines 964 to 965. OpenAI web search costs $10.00 per 1k calls plus search content tokens at model rates. For gpt-4o-mini and gpt-4.1-mini, content tokens bill "as a fixed block of 8,000 input tokens per call". OpenAI file search costs $2.50 per 1k calls plus $0.10 per GB per day after 1 GB. Source: `scratchpad/oai_pricing.txt` lines 774 to 786, fetched 2026-09-23 at about 02:30 by an earlier session. Gemini grounding with Google Search: 5,000 free requests per month across Gemini 3.x, then $14 per 1,000. Source: `scratchpad/g_pricing.txt` line 235, same day.
- **Inferred.** At $10 per 1,000, the 23 search calls of gpt-5 in BrowseComp-Plus would add about $0.23 per question on a hosted web tool, before tokens. Check: count `web_search_requests` in a real run.
- **Vendor figure, already taught.** Anthropic's 4× and 15× token ratios, relative to chat, are in Module 2, 4.1. Link only. Do not repeat them.

### 4.14 A production deep-research system is a trained search policy with a capped tool budget, not a better index

This concept was researched for this dossier from providers' own documents. **Review:** every source here is a vendor describing its own product. That is acceptable for "what the product does", but none measures the claim "not a better index". Section 5 folds 4.14 into 4.13 as the cost-control part: `max_tool_calls` and `max_uses` are the budget knobs. The "trained policy" part goes into 4.11 with the BrowseComp caveat above.

- **OpenAI, verified.** The deep research model "is powered by an early version of OpenAI o3 that is optimized for web browsing". It learned "searching, clicking, scrolling, interpreting files" and a python tool "through reinforcement learning training on these browsing tasks". Source: Deep Research System Card, 2025-02-25, Sections 1 and 2, `gaps/oai_dr_systemcard.txt`.
- **OpenAI API, verified.** `o3-deep-research` and `o4-mini-deep-research` use web search, remote MCP servers, and file search over vector stores. At least one data source is required. At most two vector stores can be attached. An MCP server must implement a "search and fetch interface". Tasks can take "tens of minutes", so background mode is recommended. `max_tool_calls` "is the primary tool available to you to constrain cost and latency". Source: developers.openai.com deep research guide, `gaps/oai_deepresearch_guide.txt` lines 755 to 777, 1413 to 1428 and 2470 to 2480.
- **OpenAI pipeline, verified.** Deep research in ChatGPT runs three steps: clarification and prompt rewriting by an intermediate model "like gpt-4.1", then research. The API does not include the first two steps. Same guide, lines 1432 to 1442.
- **Anthropic, verified.** Claude searches when the request depends on current or changing information, and answers directly for stable knowledge. `max_uses` caps searches per request. From tool version `web_search_20260209`, "dynamic filtering" lets Claude write code that filters results before they reach the context. It needs Claude 4.6 or later. Source: `gaps/claude_websearch.txt` lines 126 to 207.
- **Google, verified.** Gemini Deep Research "creates a multi-step research plan for you to either revise or approve", then searches, finds information, and starts "a new search based on what it's learned", over "a few minutes". Source: Google blog, 2024-12-11, `gaps/gemini_deepresearch.txt` lines 249 to 250. AI Mode uses "query fan-out" and Deep Search "can issue hundreds of searches". Source: Google I/O 2025 post.
- **Security, verified.** The OpenAI guide warns that even "read-only" MCP servers can return prompt-injection payloads, and links in results can exfiltrate data through URL parameters. Module 16 owns this. Link only.
- **Not checked.** Perplexity's deep research post returned HTTP 403 to curl twice. No provider publishes the index behind its web search tool.

### 4.15 GraphRAG's headline win was against vector-only RAG, judged by an LLM, on questions with no gold answer

- **Verified.** Edge et al., Microsoft Research, arXiv 2404.16130 v2, preprint. "global approaches achieved comprehensiveness win rates between 72-83% (p<.001) for Podcast transcripts". The baseline SS is vector search filling an 8k window. The 125 questions per corpus were LLM-generated "without requiring retrieval of specific low-level facts". Vector RAG won on directness. Source: Sections 3.2, 4.1.2, 5.1.
- **The paper's own caveat, verified, condition added in review.** "there were no statistically significant differences observed among the global search conditions or between global search and TS". TS is map-reduce over raw text with no graph. This sentence is from Experiment 2, which counts extracted claims. Source: Section 5.2. In Experiment 1, with the LLM judge, community summaries did beat TS: C2 on Podcast and C3 on News won comprehensiveness at 57% and 64%, p < .001. Source: Section 5.1. So the graph's edge over plain map-reduce depends on the metric. Teach both halves.
- **Judges are fragile, verified.** Zeng et al., Wuhan University and SJTU, arXiv 2506.06331 v2, preprint. Swapping answer order changed win rates "by over 30%". LightRAG against NaiveRAG on Agriculture fell from a reported 66.70% to 39.06%. Source: Sections I and VI.C. **Review:** the section was V.C in the draft. The 39.06% comes from the authors' whole framework: 150 new questions, a GPT-4o-mini judge, bias correction and ties allowed. It is not only the old run with bias removed. Module 11, 4.3 owns judge bias.

### 4.16 On gold-labelled fact questions, Microsoft GraphRAG often loses to a strong dense retriever and sometimes to BM25

- **Verified, sample size corrected in review.** HippoRAG 2, Ohio State and UIUC, ICML 2025. QA F1 with a Llama-3.3-70B reader. 1,000 queries on each of five datasets, 124 on LV-Eval and 293 on NarrativeQA, over 4,111 to 22,849 passages. Average F1: GraphRAG 49.6, NV-Embed-v2 57.0, BM25 47.7. GraphRAG lost to NV-Embed-v2 on 6 of 7 datasets. It won only on LV-Eval, 11.2 against 9.8. Source: Tables 1 and 2.
- **Verified.** GraphRAG-Bench, Xiang et al., ICLR 2026 per the PDF header. Medical fact retrieval ACC: RAG with rerank 64.73, MS-GraphRAG 38.63. Source: Table 3.
- **Verified, conditions added in review. Not Microsoft GraphRAG.** Gao et al., Cambridge and Peking University, arXiv 2606.24725, preprint. 8,442 chunks of detector literature, 48 answerable queries. The graph is the authors' own detector-entity graph expansion. Strict Hit@5: hybrid 0.917, BM25 0.896, graph 0.354. Hybrid against graph p = 5.52e-7. Hybrid against BM25 was not significant, p = 0.788. The graph found the right paper, Paper@5 0.767, but not the right chunk. Source: Tables 4 to 6. Use it as evidence about entity-graph retrieval in general, with its small sample.
- **Verified.** Han et al., arXiv 2502.11371 v3, preprint. With token-matched RAG on MultiHop-RAG, RAG scored 69.33 and GraphRAG 69.01, Llama-3.1-8B reader. GraphRAG here is Community-GraphRAG Local. With a Llama-3.1-70B reader the order flipped: GraphRAG 71.17, token-matched RAG 71.01. Source: Tables 32 and 33. Both gaps are under 0.4 points: call it a tie. On null queries whose answer is "insufficient information", Community-GraphRAG Global scored 19.27 and RAG 96.01. Source: Table 2.
- **Answer to the README question, verified by absence.** No study found measures Microsoft GraphRAG against hybrid retrieval on labelled answers with a sweep of corpus sizes. Xiang et al. Table 17 is the only sweep. **Review, verified by the reviewer's sub-agent on a re-fetched PDF:** Table 17 compares HippoRAG2 with RAG, not Microsoft GraphRAG. It is labelled the Novel dataset. Its HippoRAG2 "Small" row equals the Novel HippoRAG2 row of Table 3. Its RAG "Small" row, 64.73, 58.64, 65.75, 60.61, equals the **Medical** RAG-with-rerank row of Table 3. Do not teach a crossover size from it.

### 4.17 Graph indexing cost scales with the number of chunks times the prompt size, not with corpus tokens alone

- **Verified.** HippoRAG 2 Table 12, MuSiQue, 11,656 passages. GraphRAG indexing used 115.5M input and 36.1M output tokens. HippoRAG 2 used 9.2M and 3.0M. RAPTOR 1.7M and 0.2M.
- **Measured.** The same corpus is 1,327,109 o200k_base tokens. So GraphRAG sent 87 times the corpus as LLM input. On a 56k-token novel it sent 9.6 times, from GraphRAG-Bench Table 15. Source: `graph/cost_recompute.out`.
- **Inferred mechanism.** An extraction prompt of about 1,853 o200k tokens, measured on `prompts/index/extract_graph.py`, is sent twice per chunk with the default `max_gleanings = 1`. Short passages pay it once each. Check: run `graphrag index` on both corpora and count tokens.
- **At today's prices, verified arithmetic, inferred tokenizer match.** GraphRAG on MuSiQue: $519.80 on gpt-4.1, $38.98 on gpt-4o-mini, $29.60 on gpt-6-luna. Embedding the corpus once with text-embedding-3-small: $0.03. The token counts are Llama-3.3 tokens priced at other vendors' rates.
- **Time, verified.** HippoRAG 2 Table 12, 4 H100 GPUs with vLLM: indexing 12.1 min for NV-Embed-v2, 277.0 min for GraphRAG. QA time per query 0.3 s against 10.7 s.
- **Query cost, verified.** GraphRAG-Bench Table 6: MS-GraphRAG global search averaged 331,375 context tokens per query on the Novel set, vanilla RAG 879. That is $0.66 against $0.0018 of gpt-4.1 input, inferred by multiplication. The same paper's text says prompts reach "up to 4 × 10^4 tokens". Both are in the PDF.
- **Current state, verified.** `graphrag` 3.1.2, 2026-08-21, is "largely in maintenance mode, and won't be accepting new PRs or implementing new features". Query modes are `local`, `global`, `drift` and `basic`. LazyGraphRAG is not in the repository: 0 paths contain "lazy". Defaults: `gpt-4.1`, `text-embedding-3-large`, 1,200-token chunks. Source: README and `config/enums.py` lines 31 to 37 and `config/defaults.py` at v3.1.2.

### 4.18 An entity graph does not need an LLM to add multi-hop recall, but it needs retriever seeds

- **Lab, verified by run.** Regex entity graph, Personalized PageRank with restart 0.15 and 5 iterations, seeded by the top 5 RRF passages of BM25 plus bge-small. One configuration, chosen before running. Recall@5, 1,000 queries each:

| Dataset | RRF | Graph seeded by RRF | Graph minus RRF | p |
|---|---|---|---|---|
| 2WikiMultihopQA, 6,119 passages | 0.7030 | 0.7725 | +0.0695 | 0.0001 |
| MuSiQue, 11,656 passages | 0.5168 | 0.5615 | +0.0447 | 0.0001 |
| HotpotQA, 9,811 passages | 0.8570 | 0.8505 | −0.0065 | 0.2553 |
| SciFact, 5,183 passages, single-hop, 300 queries | 0.7697 | 0.7591 | −0.0107 | 0.0671 |

  At recall@10, SciFact lost 0.0715, p = 0.0002. Zero LLM tokens. Graph build 0.1 to 0.8 s. Source: `graph/run2_*.out`. BM25 recall@5 reproduced HippoRAG 2 Table 3 within 0.2 points.
- **Ablations, verified by run.** Shuffled edges removed the gain: 2Wiki 0.6492. Entity-only seeding fell below BM25 on HotpotQA, 0.5825 against 0.7475.
- **Published, verified.** SPRIG, PingCAP, arXiv 2602.23372, single-author preprint. Graph PPR seeded by RRF against RRF, recall@10 on 10,000 2Wiki queries: +0.0970, 95% CI 0.0925 to 0.1019. Its hyperparameters were tuned on 500 queries of the same validation set. Source: Tables A.19 and A.21.
- **Microsoft's own fast method, verified.** `graphrag --method fast` uses "noun phrases extracted using NLP libraries" and "text unit co-occurrence". The LLM writes only community reports. Source: `docs/index/methods.md` at v3.1.2. Its cost is not checked.

### 4.19 Graph gains depend on the query mix: entity chains gain, single-hop and exact-term queries lose

**Review.** The main claim here is inferred. Section 5 folds it into 4.18 as the "where it loses" half of that concept, with the SciFact row of the 4.18 table as its evidence.

- **Inferred from 4.16 and 4.18.** PPR replaces lower-ranked retriever hits with entity neighbours. That helps when the answer spans passages that share named entities. It hurts when one passage holds the answer. The mix of your queries decides. Check: Lab L12, a router that sends only queries with 2 or more entities to the graph.
- **Verified, corrected in review.** GraphRAG-Bench Table 16, Medical: HippoRAG2 average ACC rose from 57.08 with Qwen2.5-3B to 63.91 with 14B. RAG also rose, from 56.13 to 59.10. The draft said RAG "stayed flat". So the graph's lead grew from 0.95 to 4.81 points with generator size. The paper's own text gives 57.59 to 61.50, which does not match its table. Quote the table.
- **Graph stores other than GraphRAG, weak evidence.** Text2Cypher, Neo4j, arXiv 2412.10064, preprint: 44,387 cleaned instances. Fine-tuned models improved Google-BLEU and exact match. The abstract gives no numbers. Zep and Graphiti, arXiv 2501.13956, a vendor preprint: DMR 94.8% against MemGPT 93.4%, and up to 18.5% accuracy gain on LongMemEval. Source: `gaps/text2cypher.html`, `gaps/graphiti.html`, abstracts only. Module 10 owns temporal memory graphs.

### 4.20 A high cosine threshold does not make a semantic cache safe

Terms. A **semantic cache** returns a stored response when a new prompt embeds close to a stored one. A **false hit** returns a response that is wrong for the new prompt. **False-hit share** is false hits divided by hits. vCache's **error rate** is false hits divided by all requests.

**Review.** Module 1, 5.6 already states the risk and quotes Azure API Management's advice: start the score threshold at 0.05, and mismatches "become likely" above 0.2. Link it. Inferred: the Azure score is a distance, so its 0.05 is close to a cosine similarity of 0.95. Check: the Azure semantic cache policy reference. This module adds the measurement.

- **Verified.** vCache, ICLR 2026, Appendix F.9, 45,000 SemCacheClassification prompts. Correct and incorrect hits "are nearly indistinguishable in similarity space, with substantial overlap and similar means (0.84 vs. 0.85)".
- **Lab, verified by run.** PAWS validation, 8,000 pairs. all-MiniLM-L6-v2 at threshold 0.98: hit rate 0.513, false-hit share 0.468. At 0.95: 0.809 and 0.530. On QQP at 0.95: hit rate 0.088, false-hit share 0.136. Source: `cache-grounding/lab/cache_sweep_run.txt`. The data is sentence pairs, not a nearest-neighbour cache replay.
- **Near misses, verified by run.** "Show flights from Paris to Rome" against "...Rome to Paris": cosine 0.999 with MiniLM. "Is ibuprofen safe during pregnancy?" against "...unsafe...": 0.979. Same file.
- **Verified.** NevIR, EACL 2024, Table 2. No bi-encoder scored above 11.1% pairwise accuracy on negation pairs. Random is 25%.
- **A verifier helps only in its training distribution, verified by run.** Adding `cross-encoder/quora-distilroberta-base` at score 0.9 cut QQP false-hit share from 0.266 to 0.062, with recall from 0.615 to 0.522. On PAWS it moved from 0.556 to 0.544. It scored "safe" against "unsafe" at 0.992. Source: `lab/cache_verify_ce_run.txt`.
- **Maintainer data, verified.** GPTCache PR #702, merged 2026-09-22. The same default cross-encoder at 0.80 had precision 42.2% and recall 82.3% on 1,536 model-assisted labels. Tuning the threshold left test precision at 42.3%. Source: `RERANKER_COMPARISON.md` at a74ac654. Not peer reviewed.
- **Defaults differ in units, verified.** GPTCache 0.1.44 `similarity_threshold = 0.8` is a fraction of the evaluator's score range, not a cosine. Its un-configured default is exact match. RedisVL 0.27.2 `distance_threshold = 0.1` is in Redis cosine distance units 0 to 2, with `ttl = None`. Sources: `gptcache/config.py` line 40 and `adapter.py` lines 98 to 106 at 0.1.44; `semantic.py` lines 64 to 82 at v0.27.2.

### 4.21 With a fixed threshold, the false-hit rate grows as the cache fills

- **Verified.** vCache Appendix F.1, 150,000 ORCAS queries. Static thresholds fail as "prompt diversity increases (see the threshold of 0.99, which yields an error rate of 1.7% after 150k samples)".
- **Verified.** vCache learns a threshold per cached entry online, under a user-set error bound δ. With text-embedding-3-small and GPT-4.1-nano it reached a 57% hit rate with error below 0.5%. It assumes i.i.d. traffic. On SemCacheClassification it wins only "for error bounds above 1.5%". Sources: Sections 1, 5 and 6, Appendix F.3. **Review, labels named per result.** The 57% result uses SemCacheLMArena, whose paraphrases GPT-4.1-nano generated, Appendix H.2. The 1.7% static-threshold result in F.1 uses real ORCAS queries grouped by a GPT-4.1-nano judge, H.3. The 0.84 against 0.85 result in 4.20 uses class labels from three classification datasets, H.1.
- **Metric choice, verified.** Operational Gap, NYU and Redis, EMNLP 2026 Industry per arXiv comment. "models with the highest PR-AUC are often the worst in operation". Source: abstract and Table 1.
- **Licence, verified.** The vCache repository licence is CC BY-NC-ND 3.0. It is not on PyPI.

### 4.22 A shared semantic cache is a channel between tenants

- **Verified, conditions added in review.** CacheAttack, HKUST and Fudan, ICML 2026. The abstract's "hit rate of 86%" is an average. The simple variant, CacheAttack-1, reached 86.9% against GPTCache at τ = 0.8 and 85.8% against a KV cache, on 50 NQ prompts. The authors' harder-to-detect variant reached 83.1% on GPTCache. Source: Section 6.2, Table 1, Appendix B. Scoping the cache key to a user "eliminates cross-user response hijacking" and "typically lowers the cache hit rate". Source: Section 7.3. The paper cites GPTCache's default as 0.7. The 0.1.44 config file says 0.8. See section 10.
- **Verified.** Early Bird, IEEE TIFS accepted. On GPTCache defaults, timing told hits from misses with 81.4% accuracy in one trial. Source: arXiv 2409.20002 v5.
- **Staleness, verified.** PayPal, Agent4IR at KDD 2026: "temporal staleness" is one of four failure classes. Near misses on time period, polarity and intent "often exceed 0.95 cosine similarity under text-embedding-3-large". No table backs the 0.95 claim.
- **Link.** Module 1, 5.6 already says a cache without a per-user or per-group key "can serve one user's answer to another". Module 1, 6.2 covers prompt-cache timing and `cache_salt`. Module 16, Phase 7 owns cache sharing as a threat. This module teaches scope, TTL and invalidation as cache design.

### 4.23 A citations API guarantees a valid pointer, not that the cited text supports the sentence

- **Verified.** Anthropic citations docs: "citations are guaranteed to contain valid pointers to the provided documents". The page makes no claim about entailment. Citations "cannot be used together with structured outputs". Source: platform.claude.com citations docs, fetched 2026-09-23.
- **Verified.** OpenAI file search returns a `file_citation` with `index`, `file_id` and `filename`, and no quoted span. The page does not use the word "guarantee".
- **Post-rationalized citations, verified, conditions added in review.** Wallat et al., arXiv 2412.18004. When a relevant but previously uncited 2 to 4 token statement was injected, Command-R+ cited the injected document for 57% of the statements it repeated, 273 of 476. Random documents drew 12%. Source: Section 5, Figure 3. ICTIR 2025 venue not checked by fetch.
- **Verified.** ALCE, EMNLP 2023: on ELI5, "even the best models lack complete citation support 50% of the time".
- **Cloud checks give no accuracy numbers, verified by absence.** AWS Bedrock contextual grounding says "Conversational QA / Chatbot use cases are not supported" and caps the source at 100,000 characters. Google's check grounding API gives a support score that "loosely approximates the fraction of claims" grounded. Neither page gives precision or recall.

### 4.24 A grounding checker's balanced accuracy hides a large precision and recall trade, and checkers disagree

- **Verified.** Godbole and Jia, USC, arXiv 2501.14883. For Bespoke-7B and gpt-4-turbo, "the IoU is less than 50% on 5 of the 14 datasets". The gap between true-positive and true-negative rate is over 20% on 7 of 14 datasets. Checkers are biased "against highly paraphrased outputs".
- **Verified.** LLM-AggreFact leaderboard, 39 rows recomputed: top Bespoke-MiniCheck-7B 77.4 balanced accuracy, MiniCheck-Flan-T5-L 75.0, HHEM-2.1-open 71.8. Every checker scores about 58 to 61 on ExpertQA.
- **Verified.** LettuceDetect, arXiv 2502.17125, on RAGTruth: lettucedetect-large-v1 precision 80.44, recall 78.05. Prompted gpt-4-turbo precision 46.9, recall 97.9. Source: Table 2.
- **Lab, verified by run.** SciFact dev claims, 1,090 pairs. `cross-encoder/nli-deberta-v3-base`, pass at P(entailment) ≥ 0.5. Precision 0.880, recall 0.338. With the whole abstract as premise instead of the rationale sentences, only 10% of supported claims passed. Source: `cache-grounding/lab/grounding_nli_base.txt`. Premise length mattered more than model size.
- **Transfer, verified from abstract.** On code-agent evidence, LettuceDetect-large reached 0.17 span-F1. arXiv 2607.00895, preprint.

### 4.25 Adding retrieval makes a model abstain less, even when the evidence is missing

- **Verified.** Sufficient Context, UCSD, Duke and Google, ICLR 2025. "Without RAG, Claude 3.5 Sonnet abstains on 84.1% questions, while with RAG, the fraction of abstentions drops to 52%." Gemini 1.5 Pro drops from 100% to 18.6%. Source: Section 4.2. The dataset is inferred to be Musique from Figure 1.
- **Verified.** Same paper: models output correct answers "35–62% of the time with insufficient context". Source: Section 1 and the Table 2 caption in Section 4.3. It is not in the abstract. A strict abstain rule "can lower overall" accuracy. Source: Section 5.1.
- **Review.** No earlier module teaches this. Section 5 moves 4.25 to the "retrieve or not" phase. It is a cost of always retrieving, next to 4.9.
- **Verified.** CRAG, see 4.9: hallucination rose from 13.5% to 28.2% for GPT-4 Turbo when web pages were added.
- **Inferred.** A grounding gate then faces a choice. It blocks a correct answer the model knew from memory, or it passes an unsupported claim. Decide which error costs more before choosing the gate's threshold.

### 4.26 A per-tenant index costs no extra vector memory when tenants do not share documents

- **Lab, verified by run.** FAISS 1.15.1 `IndexHNSWFlat`, M 16, 384 dimensions, SciDocs 25,657 vectors. One shared index serialized to 43.1 MB. Forty per-tenant indexes over the same vectors summed to 43.1 MB. Ratio 1.000 on 3 seeds and on random tenants. An empty index is 250 bytes. Source: `tenancy/proto/run_topic_seed0.txt` to `seed2`. Serialized size is a proxy for RAM.
- **Why the ratio is 1.000, link.** Module 3, 2.2 teaches that the vectors, not the graph, are the memory. Split the same vectors into 40 indexes and the total stays the same.
- **Why others report more, verified.** Curator, Duke and Yale, arXiv 2401.07119, preprint: per-tenant indexing uses "10.1× more memory" than metadata filtering, on YFCC100M with CLIP vectors, 1,000 tenants, each vector shared by 13.37 tenants on average. HONEYBEE, SIGMOD 2026 per arXiv comment: role partitions used 7 times the memory, with overlapping roles.
- **The real limits are object counts, verified.** Elasticsearch: 1,000 shards per non-frozen data node. Qdrant Cloud: 1,000 collections per cluster by default. Milvus 3.0.2: 1,024 partitions per collection, `maxPartitionNum: 1024` at `configs/milvus.yaml` line 348. Weaviate: the Linux open-file limit per node.

### 4.27 A shared index can look fine on average and still be worse for small tenants

- **Lab, verified by run.** FAISS HNSW with the tenant filter inside the walk against one index per tenant, SciDocs, 40 topic tenants. All queries: this prototype searched the per-tenant indexes at FAISS's default ef of 16 against 40 for the shared index. Corrected in Module 4, Phase 7: at equal ef 40 the all-query loss is significant on 2 of 3 seeds. The small-tenant losses below hold at equal ef. The 25 smallest tenants, mean share 0.76%: −0.0324 nDCG@10 at p = 0.0006, −0.0529 at p = 0.0001, −0.0190 at p = 0.058. Filtered ANN recall@10 for them was 0.656 to 0.693 shared, 0.995 to 0.996 per tenant. Source: `tenancy/proto/run_topic_seed*.txt`. The third p is in the harness's 0.03 to 0.07 zone and was not re-run with 1,000,000 flips.
- **Mechanism, verified from source, line numbers corrected in review.** In FAISS v1.15.1 `faiss/impl/HNSW.cpp`, lines 1142 and 1191 check the selector only before adding a node to the results. Line 1199 pushes every neighbour to the candidate heap, allowed or not. The stop rule at lines 1158 to 1165 counts candidates, not allowed results. So at efSearch 40 the walk stops early for a small tenant. The small-tenant bucket got only 8.47 rows of 10 on average, seed 0. Source: `tenancy/proto/run_topic_seed0.txt`.
- **A result that looks like a conflict with Module 3, inferred.** Module 3, 3.4 measured hnswlib's filtered sweep at filtered ANN recall 1.000 at every share, Phase 3 line 433. FAISS's filter inside the walk reached only 0.656 to 0.693 here. Both filter inside the walk. The FAISS stop rule above explains the gap. Inferred: hnswlib's stop rule counts only allowed results. Check: read `hnswalg.h` at hnswlib 0.8.0, the filtered `searchBaseLayerST` path. Teach it as "the stop rule, not the idea of filtering inside the walk, decides starvation".
- **Link.** Module 3, 1.4 teaches slicing. Module 3, 3.1 teaches post-filter starvation. This concept adds the tenant-size slice.

### 4.28 Under row-level security, a B-tree on the tenant column protects only the tenants below the planner's switch to exact search, and the tenants just above it starve

**Review.** Old heading: "Whether a small tenant starves depends on the engine's fallback rule, not on sharing itself". Module 3, 3.3 already teaches the fallback rule and already ran it on pgvector 0.8.1 with a `WHERE` filter, Phase 3 line 351. The reviewer's run below found what is new under row-level security: the B-tree protects only tenants below the planner's switch point, and tenants just above it starve. Section 5 folds this into 4.27.

- **Lab, verified by run.** PostgreSQL 14.24 with pgvector 0.8.1, row-level security on `tenant_id`, HNSW, `hnsw.ef_search` 40, LIMIT 10. With a B-tree on `tenant_id`, small tenants got 10.00 rows of 10: the planner chose a bitmap scan and a sort, which is exact search. With the B-tree dropped, small tenants got 3.27 rows, and 1 of 40 queries got a full answer. Source: `tenancy/proto/pg/RESULTS_rls.txt`.
- **Correctness check, verified by the reviewer's run, 2026-09-23.** Throwaway cluster on port 55461, data folder in the scratchpad, stopped and deleted after the run. Same table, same tenants, same 40 queries per band. Ground truth is exact per-tenant search in numpy on the same 6-decimal vectors that Postgres loads. Self-test: exact search inside Postgres, as a superuser with index scans off, matched the numpy truth on 120 of 120 queries. Filtered recall@10 against that truth, and wrong rows per query, meaning returned rows outside the true top 10:

| Setting, ef_search 40 unless named | Small, mean share 0.89% | Medium, mean share 2.31% | Large, mean share 16.71% |
|---|---|---|---|
| B-tree, iterative scan off | 10.00 rows, recall 1.000 | 6.53 rows, recall 0.653, full 18 of 40 | 7.75 rows, recall 0.760 |
| B-tree, `relaxed_order` | recall 1.000 | recall 0.993, 0.07 wrong rows | recall 0.972, 0.28 wrong rows |
| No B-tree, iterative scan off | 3.27 rows, recall 0.328 | 3.30 rows, recall 0.330 | 7.75 rows, recall 0.760 |
| No B-tree, `relaxed_order` | recall 0.997, 0.03 wrong rows | recall 0.988 | recall 0.972 |
| No B-tree, `strict_order` | recall 0.980, 0.20 wrong rows | recall 0.972 | recall 0.957, 0.42 wrong rows |
| No B-tree, ef_search 200, iterative off | 6.83 rows, recall 0.680 | 7.45 rows, recall 0.742 | 9.97 rows, recall 0.993 |

  Every returned row belonged to the right tenant in every setting. Source: `review_m04/l17/RESULTS_l17.txt`, script `run_l17.py`.
- **The planner's switch point, verified by the reviewer's run.** With the B-tree present, the planner chose the exact bitmap-and-sort plan for every tenant up to 483 rows, 1.88% of the table. It chose the HNSW scan with the policy as a filter for every tenant from 548 rows, 2.14%, upward. Source: `review_m04/l17/RESULTS_plan_by_size.txt`. So the B-tree protected small tenants only. With the B-tree and iterative scans off, the medium band still averaged 6.53 rows. Its 18 full answers were exact, inferred from the plan run: they were also the 18 perfect answers. The other 22 queries averaged about 3.7 rows, inferred from the band total of 261 rows. Module 3 E12 placed the switch "between 1% and 10%". This run narrows it to between 1.88% and 2.14% for this table, at default cost settings.
- **What the check changes, inferred from the run.** A full LIMIT is not a correct LIMIT. With iterative scans on, rows were always full, but large tenants got about 0.3 wrong rows per query at ef_search 40. `strict_order` did not beat `relaxed_order` here: small tenants 0.980 against 0.997, p = 0.125, 4 wins and 0 losses, not significant. The paired test is the harness `compare`.
- **Verified.** Qdrant and Weaviate switch to exact search below a threshold. Module 3, 3.3 lists them with pgvector and ACORN, Phase 3 lines 349 to 354. **Review:** the draft said Module 3 lists Lucene and OpenSearch. It does not. Lucene's rule comes from Elastic's kNN docs, verified in the tenancy report: brute force per segment when "the filtered document count is less than or equal to num_candidates". pgvector has no such rule. The planner decides.
- **A real bug report, verified, wording corrected in review.** Marten issue #5419, filed by the Marten maintainer on 2026-09-14 and closed the same day. The issue says a tenant's search "can come back with far fewer than `limit` rows (or none)". The failure the maintainer reproduced was the 40-row cap itself, against pgvector 0.8.5. The tenant case is described, not reproduced.

### 4.29 A namespace per tenant changes what you pay for, and idle tenants become a cold-start problem

- **Billing, verified.** Pinecone: "1 RU per 1 GB of namespace size per query, minimum 0.25 RU", and "Queries scan the entire namespace regardless of filters". turbopuffer bills "the actual size of the queried namespace or 1.28 GB, whichever is greater".
- **Inferred.** A shared namespace makes every small tenant pay for the whole namespace. A namespace per tenant makes a tiny tenant pay the per-query minimum. Check: compute cost per query for your tenant size distribution.
- **Idle tenants, verified.** Weaviate: "Weaviate never deactivates or offloads a tenant on its own" and it "does not redistribute existing tenants". Backups do not include offloaded tenants. turbopuffer cold p50 874 ms, warm p50 14 ms. These are vendor numbers. The home page says 10M documents and the architecture page says 1M documents for the same p50. Module 3, 3.5 already reports this conflict.
- **Per-tenant BM25 statistics, verified by run, second seed added in review.** Seed 0: shared IDF beat per-tenant IDF for small tenants by +0.0124 nDCG@10, p = 0.0007. Seed 1 did not repeat it: +0.0069, p = 0.163. Medium tenants favoured shared IDF on both seeds, +0.0075 at p = 0.039 and +0.0090 at p = 0.0046. Sources: `tenancy/proto/run_idf_seed0.txt` and `run_idf_seed1.txt`. **Teach as:** per-tenant IDF did not help small tenants in this domain, and may hurt them. Do not teach a significant loss. Qdrant added a per-tenant IDF option in 1.19.0.

### 4.30 A tenant filter is a weaker boundary than a separate index

**Review.** The lab below shows only that a missing filter leaks, which any engineer expects. The concept a learner can get wrong is narrower: with a shared index, one missing filter or one connection as the table owner returns other tenants' rows, while with a separate index the same bug returns nothing. Keep it short. Module 16 owns the security lesson.

- **Lab, verified by run.** With the tenant filter removed from the post-filter path, 7,500 of 9,960 results, 75%, came from other tenants. Source: `tenancy/proto/run_dropfilter_seed0.txt`.
- **Verified, re-fetched in review.** PostgreSQL row-level security does not apply to superusers or roles with BYPASSRLS. Table owners also bypass it unless the owner sets `FORCE ROW LEVEL SECURITY`. Source: postgresql.org, "Row Security Policies". Pinecone's design page says namespaces reduce "the risk of application bugs that could query the wrong tenant's data".
- **Ownership.** Module 16, 4.8 and Phase 7 own isolation as a security boundary. This module states the architecture fact and links.

### 4.31 Each replacement moves latency to a different place

This table assembles verified numbers from the concepts above. The conditions differ row by row, so compare orders of magnitude only. The table itself is inferred.

| Step | Latency | Conditions | Source |
|---|---|---|---|
| Filtered ANN search, small tenant | about 21 µs shared, 5.5 µs exact | FAISS, SciDocs, one thread, laptop | 4.27 run file |
| BM25 search | 16 ms; 55 ms | MS MARCO, single thread | Module 3, 6.2; Arabzadeh et al. |
| Cache pair verifier | 1.41 to 3.59 ms per pair | cross-encoder, batch 128, MPS | 4.20 run file |
| vCache threshold update | at most about 1.5 ms | Blackwell GPU | vCache Appendix F.4 |
| NLI grounding check | 30.8 to 63.1 ms per pair | xsmall and base, MPS, batch 32 | 4.24 run file |
| Query rewrite LLM call | over 2,000 ms | a 2023 hosted LLM. The model name is not checked | Module 3, 6.2 |
| One-step RAG answer | 3.08 s; 13.2 s | small model; 32B reasoning model | 4.13 |
| Multi-step loop | 27.18 s; 18.7 s | small model; 32B reasoning model | 4.13 |
| GraphRAG local QA | 10.7 s against 0.3 s dense | Llama-3.3-70B, 4 H100 | 4.17 |
| Industry web RAG, 2024 | 3.4 to 11.6 s | CRAG Table 6 | 4.9 |
| Cold namespace | 874 ms p50 against 14 ms warm | vendor, hardware not stated | 4.29 |
| Whole corpus in context | about 100 s at 1M tokens | Gemini 1.5 Pro, no cache, 2024 | LOFT Limitations |
| Deep research | 5 to 30 min; "tens of minutes" | OpenAI product and API | 4.14 |

- **Not checked.** Time to first token for a cached 900k-token prompt on a current model. Module 1, 1.2 has the method. This is the largest hole in the table.

### 4.32 One decision procedure, ordered by cost

The procedure is **inferred**. It combines the concepts above. Ask the questions in order. Stop at the first "yes".

| Step | Question | Use | Evidence |
|---|---|---|---|
| 0 | Does the model already know the answer, and is the fact stable? | Answer without retrieval, behind a gate that retrieves when uncertain | 4.9, 4.12, 4.25 |
| 1 | Does the query name an exact key: ID, code, path, function name? | Key lookup, SQL `WHERE`, or grep. BM25 if the key may be misspelled | 4.2 |
| 2 | Does the answer need every row that matches: count, sum, top-N? | SQL or a program. Retrieval only picks the table or schema. Test text-to-SQL on your own reviewed questions | 4.1, 4.4 |
| 3 | Does the corpus fit the window, and does a cache stay warm? | Whole corpus in context, stable documents first | 4.5, 4.6 |
| 4 | Is the corpus a working tree of files that change every few minutes? | Grep, glob and file reads. Add a dense tool for description queries in large repos | 4.7, 4.8 |
| 5 | Does the question chain two or more entities? | A search loop with a strong reader and an explicit document and tool budget, or an entity graph seeded by hybrid retrieval | 4.10, 4.11, 4.18 |
| 6 | Does the question need the whole corpus, like "main themes"? | Long context if it fits. Otherwise map-reduce over chunks | 4.15 |
| 7 | Otherwise | Hybrid retrieval with a reranker | Module 3, Phase 5 |

Around every step: a semantic cache only with per-tenant scope, a verifier and a TTL, from 4.20 to 4.22. A grounding check whose error costs are chosen on purpose, from 4.23 to 4.25. A tenant layout chosen by tenant size, from 4.26 to 4.30.

**Where the procedure stops working.** It assumes one query type per request. "Total refunds for customer ACME-114 last quarter" is a key and an aggregate. An agent with SQL, grep and a vector tool can mix them. No study found measures such a tool-choosing agent against a fixed procedure.

## 5. Phase structure, decided in review

**Decision: keep seven phases, but not the draft's seven.** Split the draft's Phase 3 into "Retrieve or not" and "Search loops". Merge the draft's Phases 5 and 6 into one phase on scores that decide correctness. Every phase below has three to five concepts and one decision.

Reasons:

1. **The draft's Phase 3 broke Rule 0.** It had six concepts, 4.9 to 4.14. The quality bar allows three to five. Its two halves also serve two different decisions. One is "retrieve for this query or not". The other is "how many searches, and at what budget". They use different labs: L7 and L9 against L6 and L8.
2. **The draft's Phases 5 and 6 were thin after review.** Each had exactly three concepts. Review weakened two of them. 4.22 is partly taught in Module 1, 5.6, and Module 16 owns it as a threat. 4.25 fits better next to 4.9, as a cost of always retrieving. What is left shares one idea: a score above a threshold makes a correctness decision, and someone must choose its precision and recall trade. The labs L13, L14 and L15 all print precision and recall at a set of thresholds.
3. **Why not only one of the two changes.** Merging 5 and 6 alone gives six phases, with Phase 3 still at six concepts. Splitting 3 alone gives eight phases, with two thin ones.
4. **Why Phases 1 and 2 stay apart.** Together they would hold six concepts. They also answer different questions: "which tool for this query" and "does this corpus need an index at all".
5. **Order.** Cheapest answer first. A key or an aggregate is the most common case where a vector index is wrong. "No index" is simpler than "index plus gate", and a gate is cheaper than a loop. Graphs cost the most to build. Checks and tenancy wrap any of the above, and Phase 7 closes with the map, as Module 3, Phase 7 closed with "The module question, answered".
6. **Scope with Module 16.** Tenancy stays here for architecture and cost only. Module 16 keeps isolation as a security boundary.

Each concept below is the final claim sentence. "From" names the section 4 entries it draws on. "Link" names what an earlier module already teaches, so the phase links it instead of teaching it again.

### Phase 1: The query picks the tool: keys, aggregates and text-to-SQL

Decision it enables: for each query class in a product, choose key lookup, SQL, BM25 or dense retrieval, and know how to test text-to-SQL before trusting it.

1. A vector index returns k rows, so it cannot answer a question that needs every matching row. SQL or a program must do the counting. From 4.1.
2. On code, an exact name beats dense retrieval only while the query and the index split it into the same tokens. A description of the same function flips the result. From 4.2 and 4.3. Link: Module 3, 5.1 for the mechanism.
3. Text-to-SQL replaces retrieval for aggregate questions, but public benchmark scores are not accuracy estimates, because experts found errors in 52.8% of sampled BIRD Mini-Dev gold labels. From 4.4. Link: Module 11, 4.9 for broken benchmarks in general.

Labs: L1, L2, L3. Laptop, offline. L2 downloads a 15.9 MB tarball. L3 download size not checked.

### Phase 2: No index at all: the whole corpus in context, or grep at query time

Decision it enables: when to skip building an index, and what that costs per query and per change.

1. Whole-corpus context is a cost decision first. Quality results split by model and task, and prompt caching cuts the cost gap but does not remove it. Put stable documents first in the cached prefix. From 4.5 and 4.6. Links: Module 1, 3.2 and 3.3 for cache rules and break-even. Module 1, 3.4 for the cascade shape of Self-Route. Module 2, 1.1 and 1.2 for quality at length. Module 2, 2.2 for the price of a cache break.
2. Grep at query time removes index staleness, and moves the cost to query time, where it grows with corpus breadth. From 4.7.
3. Grep against embeddings in an agent is not settled, because every published comparison changes more than the retriever. From 4.8. Link: Module 2, 2.4 on handles. Module 2 measured cost there, not accuracy.

Labs: L4, L5, and L2 reused. Laptop, offline. L5 optional live run about $0.80 on gpt-6-luna, UNVERIFIED.

### Phase 3: Retrieve or not

Decision it enables: whether to put a gate in front of retrieval, which signal it uses, and how to prove it beats "never" and "always".

1. Retrieval can lower accuracy on facts the model already knows, so "always retrieve" is not a safe default. From 4.9. Link: Module 2, 1.3 for distractors that share words.
2. Adding retrieved text makes a model abstain less, even when the evidence is missing. From 4.25.
3. On single-hop questions a cheap gate matches complex adaptive methods at a fraction of the calls. On multi-hop questions it does not, and no router so far comes close to its oracle. From 4.12. Links: Module 1, 3.4 for routers and control groups. Module 3, 5.1 line 101 for why labels are needed to route.

Labs: L9, redesigned in review, and L7. Laptop, offline after a 50.6 MB data download and a 988 MB model. Optional hosted variant UNVERIFIED.

### Phase 4: Search loops and their budget

Decision it enables: which query types get a loop, with which retriever inside it, and what search budget per question.

1. Under a fixed document budget, a search loop pays off on bridge questions and loses on single-hop and comparison questions. From 4.10.
2. A loop does not replace a good index. A better retriever inside the loop gives higher accuracy with fewer searches and a lower bill. From 4.11. Link: Module 3, 1.1 for why HNSW and exact search differ.
3. The cost multiplier of a loop depends on the model and the baseline, from about 1 to about 10 times. Production deep-research systems control it with a cap on tool calls. From 4.13 and 4.14. Links: Module 2, 2.1 for re-read cost per step. Module 2, 4.1 for the 4× and 15× ratios.

Labs: L6 and L8. Laptop, offline. 27.5 MB download.

### Phase 5: Entity graphs for multi-hop questions

Decision it enables: whether a graph earns its indexing cost on your query mix.

1. GraphRAG's headline win was against vector-only RAG, judged by an LLM, on questions with no gold answer. From 4.15. Link: Module 11, 4.3 for judge bias.
2. On gold-labelled fact questions, Microsoft GraphRAG usually loses to a strong dense retriever and sometimes to BM25. From 4.16.
3. Graph indexing cost scales with the number of chunks times the prompt size, not with corpus tokens alone. From 4.17.
4. An entity graph needs no LLM to add multi-hop recall, but it needs retriever seeds, and it loses on single-hop queries. From 4.18 and 4.19. Link: Module 3, 5.2 for RRF.

Labs: L10, L11, L12. Laptop, offline, 43 MB download. Optional LLM-built graph $1.67 to $22, UNVERIFIED.

### Phase 6: Scores that decide correctness: semantic caches and grounding checks

Decision it enables: which check to place before the model, a cache with a scope, a verifier and a TTL, and which after it, a grounding check, each at a threshold chosen from its measured precision and recall.

1. A high cosine threshold does not make a semantic cache safe, because near misses such as swapped cities score above 0.97. From 4.20. Link: Module 1, 5.6.
2. With a fixed threshold, the false-hit rate grows as the cache fills. From 4.21.
3. A shared semantic cache is a channel between tenants, so its scope is part of the cache design. From 4.22. Keep it short. Links: Module 1, 5.6 and 6.2. Module 16, Phase 7 for the threat.
4. A citations API guarantees a valid pointer, not that the cited text supports the sentence. From 4.23.
5. A grounding checker's balanced accuracy hides a large precision and recall trade, and checkers disagree with each other. From 4.24.

Labs: L13, L14, L15. Laptop, offline. 5 MB of data, a 328.5 MB verifier, 283 to 738 MB NLI models. Optional LLM judge under $1, UNVERIFIED.

### Phase 7: Many tenants on one retrieval system, and the module map

Decision it enables: index, namespace or filter for each tenant size, and how to evaluate per tenant. The closing section answers the module question.

1. A per-tenant index costs no extra vector memory when tenants do not share documents. The real limit is the number of objects. From 4.26. Link: Module 3, 2.2.
2. A shared index can look fine on average and still starve small tenants, and the engine's stop rule or the planner's switch point decides which tenants. From 4.27 and 4.28. Link: Module 3, 1.4, 3.1, 3.3 and 3.4.
3. A namespace per tenant changes what you pay for, and idle tenants become a cold-start and backup problem. From 4.29. Link: Module 3, 3.5 for cold reads.
4. With a shared index, one missing filter or one owner connection returns other tenants' rows. With an index per tenant, the same bug returns nothing. From 4.30. Link: Module 16, 4.8.

Closing section, not a concept: the latency map, 4.31, and the decision procedure, 4.32.

Labs: L16, L17, L18, L19. Laptop, offline. L17 needs the Homebrew PostgreSQL 14.24 with pgvector 0.8.1, in a throwaway cluster only, because of CVE-2026-3172.

### Concepts that rest on one vendor or one preprint, and how to present them

| Concept | What it rests on | How the course should present it |
|---|---|---|
| Phase 2, 1, the quality half | Token Tax, one preprint, the only current-model study. LaRA, peer reviewed, found the opposite on average | Show both results side by side with their conditions. Teach "test on your corpus", not a winner. The cost half is arithmetic and safe |
| Phase 2, 2, the scaling half | DCI, one preprint, 100 questions, one model. Its BM25 baseline is implausible | Direction only: tool calls grow with corpus breadth. Do not quote its retrieval gains |
| Phase 2, 3 | Vendor statements only: Anthropic podcast, Cursor, GitHub. Two preprints change the harness too | Teach as an open question with the mechanism that would settle it. Name no winner |
| Phase 4, 3, the deep-research half | Each provider's own documents | Fine for "what the product does". Do not use them as evidence that the approach is better |
| Phase 5, 4 | The dossier's own lab, one configuration. SPRIG is a single-author preprint tuned on its test split | The lab is the evidence. SPRIG supports the direction only |
| Phase 6, 1 | Own lab on sentence-pair data, vCache, and GPTCache PR #702, maintainer data one day old | Quote the lab first. Quote the PR as "maintainer benchmark, not peer reviewed" |
| Phase 6, 2 | vCache, ICLR 2026, one group. Operational Gap, one industry paper | Peer reviewed, but name the dataset and label source for each number |
| Phase 7, 1 and 2 | The dossier's own FAISS lab on SciDocs, 3 seeds, and the reviewer's pgvector run. Curator and HONEYBEE are preprint or single-venue | Teach with the sharing degree and the tenant sizes stated. Say one corpus |
| Phase 7, 3 | Vendor billing and limit pages, authoritative for their own billing. turbopuffer latency is a vendor number with two corpus sizes | Billing rules as fact with a date. Latency as a vendor order of magnitude |

## 6. Lab ideas

All labs run on the author's Apple M4 Pro from the Module 3 harness at `retrieval-internals/code/`, unless marked. They import `common/lexical.py`, `common/stats.py` and `common/metrics.py` read-only. Times are from 2026-09-23 runs on a shared machine. Never load torch and FAISS in one process: HARNESS.md explains the libomp conflict. Encode first, then run FAISS in a later process.

### Phase 1

1. **L1: Row retrieval against SQL.** Prototype: `novector/lab/rows_vs_sql.py`. Seeded synthetic SQLite table, no download. Prints accuracy per question type for BM25 top-10 and top-100, bge-small top-10 and top-100, and SQL, then the paired test. Measured: SQL 1.00, bge-small top-10 0.08 overall. Break-it: `--rows 50000`, and BM25 top-100 count and sum fall from 1.00 to 0.00. Self-test: `--self-test`, 18 checks. The main one: the oracle over all rows equals SQL for every type. Run time 6.8 s at 5,000 rows, 31.7 s at 50,000.
2. **L2: Identifier against description queries on code.** Prototype: `novector/lab/ident_vs_desc.py`. Corpus: openai/codex tag rust-v0.156.1, 15.9 MB tarball. Pin the tag, the source changes daily. Prints hit@1 and hit@5 for grep, BM25, MiniLM and bge-small on both query sets, and paired tests. Measured values in 4.2 and 4.3. Break-it: `--break split`, BM25 hit@5 falls to 0.595. Self-test: `--self-test`, 7 checks, under 1 second. Run time 114.7 s including four encodings.
3. **L3: How much of a text-to-SQL score is label error.** Not built. Take BIRD Mini-Dev examples and the corrected SQL from `github.com/uiuc-kang-lab/text_to_sql_benchmarks`. Run original and corrected gold SQL on the SQLite databases. Print how many answers differ, by error class E1 to E4. Break-it: score a fixed prediction file against both gold sets and print the rank change. Self-test: the corrected gold equals itself on every example. Download size and run time not checked. An LLM text-to-SQL arm is optional and UNVERIFIED: 200 questions at about 3,500 input and 300 output tokens cost about $0.10 on gpt-6-luna, inferred from its $0.10 and $0.50 prices.

### Phase 2

4. **L4: Long context against RAG cost calculator.** Prototype: `novector/cost/cost_per_query.py`. No network, under 1 second. Prints the table in 4.5. Break-it: set queries per hour to 1. The cache expires and cached LC costs about 1.25 times uncached on Anthropic, inferred. **Review:** the script as written prints about 1.35 times here, because it charges a cache write and a cache read for the same corpus. Fix the formula before shipping: with an expired cache, charge the write only. Self-test to add: the 272K rule doubles gpt-6-luna input, Haiku 4.5 returns "exceeds window" above 200K, and at one query per hour cached cost over uncached input equals the write multiplier, 1.25. Reuse Module 1 `code/prices.yaml` or Module 2 `common/prices.json` instead of a new price file.
5. **L5: Grep cost against corpus breadth.** Not built. Grow the L2 corpus by adding other pinned repositories. For each size, print matched lines and bytes per identifier query and per description query, and the hit@5 of grep. Expected, inferred from DCI: bytes grow with the corpus, and description queries get no better. Self-test: on the original corpus the numbers equal L2. Optional live variant, UNVERIFIED: an agent with `grep` and `vector_search` tools over L2, 200 questions × 5 turns × 8,000 input tokens is about $0.80 on gpt-6-luna plus output.

### Phases 3 and 4

L7 and L9 belong to Phase 3, "Retrieve or not". L6 and L8 belong to Phase 4, "Search loops and their budget".

6. **L6: One search or a loop, on multi-hop questions.** Prototype: `agentic/proto/hop_loop.py` and `router_add.py`. HotpotQA distractor dev, revision `1908d6afbbea`, 27.5 MB, CC BY-SA 4.0. Prints joint recall@10 by question type for one-shot, loop with top-1, random and oracle readers, a regex router and the per-question oracle, plus paired tests. Measured: bridge +0.0625, comparison −0.1991, router +0.0429 over one-shot, p = 0.0001. Re-run by the reviewer with identical output. Break-it: the random reader turns the bridge gain into −0.0470. Teaching point from the oracle-reader row: even a perfect reader loses 0.2239 on comparison questions, because the loop spends half the 10-document budget on its first hop. Self-test to write: a 5-paragraph toy where only the loop finds the second entity. Run time 67 s including a 4.9 s download.
7. **L7: Route each query to BM25 or dense.** Prototype: `agentic/proto/retriever_router.py`. Harness datasets SciFact, NFCorpus and SciDocs, cached. Prints per dataset the BM25, dense, RRF, router and oracle nDCG@10, and the router's dense share. Measured in 4.12. Break-it: label "dense strictly better" instead, and with 36% to 60% ties the router sends most queries to BM25 and loses 0.0388 on SciDocs, p = 0.0001. Self-test to write: a router with perfect labels equals the oracle. Run time 4.5 to 6.3 s warm. Uses numpy logistic regression, not scikit-learn, because its libomp is not checked next to torch.
8. **L8: Loop cost ledger with today's tool prices.** Extend L6. Print per question the searches, documents read and seconds per search, then dollars per unit of joint recall with a hosted web tool at $10 per 1,000 searches and a file search tool at $2.50 per 1,000 calls. No download. State in the lab that retrieval is "0–5%" of latency in an LLM loop, so this ledger under-counts LLM cost.
9. **L9: Retrieve or not, with a popularity or confidence gate. Redesigned in review, runs offline.** Not yet measured end to end. Findings of the review, verified by fetch on 2026-09-23, details in `review_m04/l9/l9.md`:
   - **PopQA with passages exists only for the long tail.** The Self-RAG README points to `eval_data/popqa_longtail_w_gs.jsonl`, but its Google Drive link returns HTTP 404 to curl today. A mirror, `awinml/popqa_longtail_w_gs` on Hugging Face, 20,332,067 bytes, MIT on its card, holds 1,399 questions with 25 passages each. Its popularity runs only from 2 to 99 monthly views. That range is too narrow to test a popularity gate. Use it only as an optional second arm.
   - **Chosen data.** PopQA `test.tsv` from `akariasai/PopQA` at revision `098765c7`, 5,205,200 bytes, 14,267 questions with `s_pop` from about 10^0 to 10^7 monthly views. The card has no licence. The source repository is MIT, so MIT is inferred. Passages: `popqa_contexts.jsonl.gz` from `ryannoonan/popqa-wikipedia-contexts` at revision `1b91217d`, 45,394,537 bytes, CC BY-SA 4.0, the Wikipedia article of each PopQA subject. Total data about 50.6 MB. Both sizes and licences were re-checked by the reviewer with the Hugging Face API.
   - **Retrieval arm, verified by run.** The lab builds its own BM25 index with the harness bm25s. 194,683 chunks of 100 words. Index built in 7.4 s. 2,000 questions searched in 1.7 s. Peak memory 0.91 GB. An answer string is in the top 5 for 60.1% of questions, and the subject article for 74.9%. The subject article contains an answer string for 93.3% of all rows. 41 questions have no article and are dropped.
   - **Model.** `Qwen/Qwen2.5-0.5B-Instruct` at revision `7ae55760`, one `model.safetensors` of 988,097,824 bytes, Apache 2.0, not gated. Its run time on MPS is not checked.
   - **What it prints.** Accuracy and retrieval calls for never, always, a popularity gate, a mean log-probability gate, and the oracle that retrieves only where retrieval fixes a wrong answer. Accuracy by popularity bucket for never and always. The harness `compare` with Holm correction for gate against always and gate against never. Thresholds are chosen on a 300-question dev split and applied to a 1,000-question test split.
   - **Break-it.** `--break leak-threshold` chooses thresholds on the test split and shows the inflated gain. Alternative: `--break shuffle-ctx` gives each question another question's passages.
   - **Self-test, no model needed.** File hashes and row counts, a toy BM25 case, the answer matcher, the call count of each gate, thresholds of 0% and 100% reproduce "never" and "always" exactly, and dev and test do not overlap. A mutation must make the overlap check fail.
   - **Limits.** The passage set has one uploader and 19 downloads. Its SHA-256 matches its card, but its text was not checked against Wikipedia. It holds only subject articles, so retrieval is easier than over all of Wikipedia, inferred. Article versions run from 2017 to 2026, while PopQA answers date from 2022. The answer match is loose for short aliases. State these in the lab.
   - Optional hosted variant with Claude Haiku 4.5, UNVERIFIED: about $0.63 for always-retrieve and $3.15 for a 3-turn loop over 500 questions, inferred from assumed token counts.

### Phase 5

10. **L10: Does the graph find the bridge?** Prototype: `graph/graph_proto.py`, about 190 lines, numpy and scipy only. Data `osunlp/HippoRAG_2` revision `5ec05b38`, 42.9 MB for six JSON files. Licences of 2Wiki and MuSiQue not checked. Prints BM25, dense, RRF and four graph variants at recall@5, recall@10 and nDCG@10, and paired tests against BM25 and RRF. Measured in 4.18. Break-it: entity-only seeding, shuffled edges, SciFact, and matching MuSiQue gold by title, which inflates gold from 2.65 to 7.45 per query. Self-test to write: a 6-passage toy where PPR ranks the bridge passage above a distractor, and BM25 recall@5 on 2Wiki reproduces 0.6530 ± 0.002. Run time 17 to 60 s per dataset, mostly encoding.
11. **L11: Corpus-size sweep.** Not run. Add distractors from the other two corpora to 2Wiki, from 6k to 12k to 27k passages. Re-measure graph minus RRF with the paired test. This produces the sweep no paper has published cleanly. Run time under 3 minutes, inferred from encode speed.
12. **L12: Query-mix router for the graph.** Not run. Send a query to graph PPR only with 2 or more capitalized entities. Compare routed, always-RRF and always-graph on 2Wiki plus SciFact.

### Phase 6, semantic caches

13. **L13: Threshold sweep for a semantic cache.** Prototype: `cache-grounding/lab/cache_sweep.py`, run with `--with pyarrow`. PAWS validation 1.23 MB, QQP validation 3.73 MB, plus 10 hand-written near misses. Prints hit rate, recall, false-hit share and vCache error rate at thresholds 0.70 to 0.98, then cosine for each near miss. Measured in 4.20. Break-it: add 20 of your own near misses on year, unit, "not" and swapped cities, and watch them pass at 0.95. Self-test: `--self-test` on a 4-pair toy. Run time 106 s. QQP licence is "Unknown". Use it for learning only.
14. **L14: A pair verifier after the threshold.** Prototype: `cache-grounding/lab/cache_verify_ce.py`. Model `cross-encoder/quora-distilroberta-base` at f62e7a4b, 328.5 MB. Prints false-hit share and recall after cosine ≥ 0.85 plus verifier ≥ 0.5, 0.8, 0.9 and 0.95. Measured in 4.20. Break-it: the "safe" against "unsafe" pair passes at 0.992. Offline vCache variant, not built: replay QQP as a stream with labels as the explore oracle and learn a per-entry threshold. Total run time was not recorded.

### Phase 6, grounding checks

15. **L15: Post-hoc grounding check with a small NLI model.** Prototype: `cache-grounding/lab/grounding_nli.py`. SciFact release tarball 3.1 MB, SHA-256 `11c62128...`, CC BY-NC 2.0. Models `nli-deberta-v3-xsmall` 283.4 MB and `-base` 737.7 MB. Prints pass rates for SUPPORT, CONTRADICT, NEI_CITED, RETR_MISS and whole-abstract premises, with precision and recall. Measured in 4.24. Break-it: change one number or negate the verb in supported claims. Self-test: `--self-test` checks the arithmetic. Run time 64.6 s xsmall, 115.3 s base, on MPS. Do not `pip install minicheck`: PyPI `minicheck` 0.4.0 is an unrelated model checker. Optional LLM judge on the same pairs with Claude Haiku 4.5, UNVERIFIED: under $1, inferred from 4 characters per token.

### Phase 7

16. **L16: Shared against per-tenant indexes, sliced by tenant size.** Prototype: `tenancy/proto/tenancy_proto.py`. SciDocs embeddings from the harness cache, FAISS only. Prints tenant sizes, labels lost to other tenants, build times, serialized bytes with the 1.000 ratio, and per-bucket nDCG@10, filtered ANN recall, rows and p50 µs, with paired tests. Measured in 4.26 and 4.27. Break-it: `--drop-filter` prints 7,500 foreign results. `--assign random` makes small tenants worse. Then evaluate on a uniform 100-query sample, which holds about 19% small-tenant queries, and report "no difference". Self-test to write: exact search over a tenant's rows equals a flat per-tenant index on the synthetic dataset. Run time 5.1 s, 520 MB peak RSS.
17. **L17: PostgreSQL row-level security, the planner's switch point and filtered recall. Correctness check built and run in review.** Prior art: Module 3, lab E12, which ran the same pgvector with a `WHERE` filter. Scripts: `review_m04/l17/prep.py` and `run_l17.py`, plus `plan_by_size.py`.
   - **Safety.** pgvector 0.6.0 to 0.8.1 have CVE-2026-3172. Use only a throwaway cluster with public data, as Module 3, Phase 3 line 748 says. Never connect to another PostgreSQL server on the machine. The script runs `initdb` into a scratch folder, starts on 127.0.0.1 port 55461 with no Unix socket, because the scratch path is longer than 103 bytes, and stops the cluster and deletes the data folder in a `finally` block.
   - **Setup.** `prep.py` writes `docs.csv`, 93.9 MB, from the harness SciDocs bge-small cache and the saved tenant ids, and computes exact per-tenant top 10 in numpy on the same 6-decimal vectors. Load, HNSW with m 16 and ef_construction 64, and the B-tree took 2.2 s. The HNSW index is 50 MB.
   - **What it prints.** Per tenant band and setting: mean rows, full answers, filtered recall@10 against exact per-tenant search, wrong rows per query, rows from other tenants, and the plan. Then paired tests on per-query recall. Measured values are in 4.28. Whole run about 1 minute.
   - **Break-it.** `DROP INDEX docs_tenant_id_idx`: small tenants fall to 3.27 rows and recall 0.328 with iterative scans off. Second break-it: raise ef_search to 200 with iterative scans off. Large tenants recover to 0.993, small tenants only to 0.680.
   - **Self-test, passed.** Exact search inside Postgres, as a superuser with index scans off, equals the numpy truth on 120 of 120 queries. Second check: no returned row ever belongs to another tenant.
   - **Label.** Measured on pgvector 0.8.1 and PostgreSQL 14.24, an x86_64 build under Rosetta, not on 0.8.6. The switch point comes from the planner's cost estimates at default settings.
18. **L18: Shared against per-tenant BM25 statistics.** Prototype: `tenancy/proto/idf_proto.py`. Prints the paired test per band. Measured in 4.29. Break-it: restrict the IDF corpus to a tenant with 0 matching documents, which gives plain TF, as Qdrant warns. Run time 5.3 s.
19. **L19: Tiered placement.** Not built. Promote tenants above a size threshold to their own index. Keep the rest shared, with exact search below the Module 3, 3.3 crossover. Sweep the threshold around Qdrant's "approximately 20,000 points". Print index objects, p50, p99 and small-bucket nDCG.

## 7. Failure stories and case studies

- **A leaderboard winner that moved from 7th to 1st.** On a corrected BIRD Dev subset, CHESS went from 62% to 81% and from 7th to 1st of 16 agents. Source: arXiv 2601.08778, Section 1. Verified.
- **Industry web RAG answered with hallucinations in 2024.** On CRAG, human graders marked 16.0% to 25.3% of answers from five industry systems as hallucinated. Source: CRAG Table 6. Verified.
- **Retrieval made a strong model worse.** GPT-3.5 on TriviaQA fell from 64.00 to 55.20 EM with one BM25 retrieval. Source: Adaptive-RAG Table 8. Verified.
- **A coding agent dropped its vector index on "vibes".** Claude Code's lead said early versions used RAG with a local vector database. Agentic search "outperformed everything. By a lot.", on "mostly vibes". Source: Latent Space, 2025-05-07. Verified. Cursor published the opposite result. See 4.8.
- **Early multi-agent research spawned too many workers.** Anthropic reports early failures that included "spawning 50 subagents for simple queries". Source: Anthropic multi-agent research post. Verified.
- **A library's vector search returned too few rows.** Marten issue #5419, filed by the maintainer on 2026-09-14 and closed the same day. The reproduced failure was a 40-row cap in its pgvector search. The issue describes the tenant-filter case, but does not reproduce it. Verified in review.
- **Backups that skip tenants.** Weaviate backups do not include offloaded tenants. Source: Weaviate data concepts docs. Verified.
- **A cache verifier that fails its own default use.** GPTCache's default cross-encoder had 42.2% precision on all 1,536 reuse labels, and 43.9% on the 1,152-row test split. Source: GPTCache PR #702. Verified. One day old, not peer reviewed.
- **A reported graph win that reversed.** LightRAG against NaiveRAG went from 66.70% to 39.06% under a debiased evaluation framework with new questions. Source: arXiv 2506.06331, Section VI.C. Verified.
- **A corpus-size table that repeats other tables.** GraphRAG-Bench Table 17's "Small" rows equal rows of Table 3, and its RAG row comes from a different dataset than the table's label. Verified in review by comparing the two tables.
- **A baseline that cannot be right.** DCI reports BM25 15.8 nDCG@10 on 50 SciFact queries. No 50-query subset of standard BM25 falls below 0.4658. Verified by run, cause inferred.
- **Corrective retrieval that fired on most queries and still lost.** CRAG with gpt-4.1-mini triggered correction on 63% of 23,088 financial queries and reached Recall@5 0.658. Hybrid RRF reached 0.695. Source: arXiv 2604.01733. Verified.

## 8. Primary sources

All fetched 2026-09-23 with `curl -sL --max-time 60` unless noted. HTTP status 200 unless noted. Full per-topic lists, with what to read in each, are in section 6 of each of the five reports. This list keeps the sources a phase writer needs first.

### Phase 1

- **Text2SQL is Not Enough: TAG, Biswal et al., UC Berkeley and Stanford, preprint**: https://arxiv.org/abs/2408.14717. Table 1.
- **TableRAG, Chen et al., NeurIPS 2024**: https://arxiv.org/abs/2410.04739. Table 2.
- **Spider 2.0, Lei et al., ICLR 2025 oral**: https://arxiv.org/abs/2411.07763, PDF saved as `gaps/spider2_2411.07763.pdf`. Error analysis, Figure 4. Leaderboard https://spider2-sql.github.io/.
- **Pervasive Annotation Errors Break Text-to-SQL Benchmarks and Leaderboards, Jin et al., UIUC, preprint v3**: https://arxiv.org/abs/2601.08778. Sections 1, 4.3 and 5. CIDR 2026 short version: https://www.vldb.org/cidrdb/2026/text-to-sql-benchmarks-are-broken-an-in-depth-analysis-of-annotation-errors.html.
- **BIRD leaderboard**: https://bird-bench.github.io/.
- **LOFT, Lee et al., Google DeepMind, preprint**: https://arxiv.org/abs/2406.13121. Table 2, Figure 6, Limitations.
- **Simple Entity-Centric Questions, Sciavolino et al., EMNLP 2021**: https://arxiv.org/abs/2109.08535. Table 1.
- **On the Theoretical Limitations of Embedding-Based Retrieval, LIMIT, Weller et al., ICLR 2026**: https://arxiv.org/abs/2508.21038. Section 5.2, Figure 6.
- **Practical Code RAG at Scale, JetBrains Research, preprint**: https://arxiv.org/abs/2510.20609.
- **CoIR, ACL 2025**: https://arxiv.org/abs/2407.02883. **CodeRAG-Bench, preprint**: https://arxiv.org/abs/2406.14497. Abstracts only read.

### Phase 2

- **LaRA, Li et al., ICML 2025**: https://proceedings.mlr.press/v267/li25dv.html. Table 2.
- **Self-Route, Li et al., EMNLP 2024 industry**: https://arxiv.org/abs/2407.16833. Sections 3.3, 4.1, 4.3.
- **The Token Tax of Epistemic Accuracy, Hamilton et al., preprint**: https://arxiv.org/abs/2606.20898. Sections 4.1 to 4.3.
- **Anthropic pricing and prompt caching**: https://platform.claude.com/docs/en/about-claude/pricing, https://platform.claude.com/docs/en/build-with-claude/prompt-caching.
- **OpenAI pricing and gpt-6-luna model page**: https://developers.openai.com/api/docs/pricing, https://developers.openai.com/api/docs/models/gpt-6-luna.
- **Gemini pricing**: https://ai.google.dev/gemini-api/docs/pricing.
- **Effective context engineering for AI agents, Anthropic, 2025**: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents.
- **Claude Code tools reference**: https://code.claude.com/docs/en/tools-reference.
- **Codex CLI at rust-v0.156.1**: https://github.com/openai/codex/tree/rust-v0.156.1. **Gemini CLI at v0.60.0**: https://github.com/google-gemini/gemini-cli/tree/v0.60.0.
- **Improving agent with semantic search, Cursor, 2025**: https://cursor.com/blog/semsearch.
- **Beyond Semantic Similarity: Direct Corpus Interaction, preprint**: https://arxiv.org/abs/2605.05242. Section 4.3.
- **Is Grep All You Need?, PwC, preprint**: https://arxiv.org/abs/2605.15184.
- **CodeGrep, NetEase, preprint**: https://arxiv.org/abs/2608.05886.

### Phases 3 and 4

- **Adaptive-RAG, Jeong et al., NAACL 2024**: https://arxiv.org/abs/2403.14403. Tables 1 to 4 and 8.
- **When Not to Trust Language Models, Mallen et al., ACL 2023**: https://arxiv.org/abs/2212.10511. Section 5.
- **Adaptive Retrieval without Self-Knowledge?, Moskvoretskii et al., preprint**: https://arxiv.org/abs/2501.12835. Table 1.
- **Search-R1, COLM 2025**: https://arxiv.org/abs/2503.09516. **Empirical study, Jin et al., preprint**: https://arxiv.org/abs/2505.15117. Table 4.
- **BrowseComp, OpenAI**: https://arxiv.org/abs/2504.12516. **BrowseComp-Plus**: https://arxiv.org/abs/2508.06600. Tables 1 and 8.
- **Is Agentic RAG worth it?, ACL 2026 Industry**: https://arxiv.org/abs/2601.07711. Table 9.
- **ReaLM-Retrieve, SIGIR 2026 per arXiv comment**: https://arxiv.org/abs/2604.26649. Table 4. Absolute values unconfirmed.
- **RouterRetriever, AAAI 2025**: https://arxiv.org/abs/2409.02685. Table 1.
- **CRAG, Yang et al., Meta, NeurIPS 2024 Datasets and Benchmarks**: https://arxiv.org/abs/2406.04744. Tables 5 and 6.
- **FRAMES, Krishna et al., Google, NAACL 2025**: https://arxiv.org/abs/2409.12941. Table 3, Section 3.2.
- **MultiHop-RAG, Tang and Yang, 2024**: https://arxiv.org/abs/2401.15391. Abstract only read.
- **Deep Research System Card, OpenAI, 2025-02-25**: https://cdn.openai.com/deep-research-system-card.pdf. The HTML page https://openai.com/index/deep-research-system-card/ returned 403 to curl.
- **Deep research guide, OpenAI API**: https://developers.openai.com/api/docs/guides/deep-research.
- **Web search tool, Claude Platform docs**: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool.
- **Try Deep Research, Google, 2024-12-11**: https://blog.google/products/gemini/google-gemini-deep-research/.
- **How we built our multi-agent research system, Anthropic, 2025**: https://www.anthropic.com/engineering/multi-agent-research-system.
- **Introducing Perplexity Deep Research**: https://www.perplexity.ai/hub/blog/introducing-perplexity-deep-research. HTTP 403 twice. Not read.
- **PopQA questions, for L9**: https://huggingface.co/datasets/akariasai/PopQA, revision 098765c7, `test.tsv`. Added in review.
- **PopQA subject articles, for L9**: https://huggingface.co/datasets/ryannoonan/popqa-wikipedia-contexts, revision 1b91217d. Single uploader. Added in review.
- **Self-RAG long-tail PopQA with passages, mirror**: https://huggingface.co/datasets/awinml/popqa_longtail_w_gs. The official Drive link in https://github.com/AkariAsai/self-rag returned 404 on 2026-09-23. Added in review.

### Phase 5

- **From Local to Global: GraphRAG, Edge et al., Microsoft Research, preprint**: https://arxiv.org/abs/2404.16130. Sections 3 to 6.
- **microsoft/graphrag v3.1.2**: https://github.com/microsoft/graphrag/tree/v3.1.2.
- **HippoRAG 2, ICML 2025**: https://arxiv.org/abs/2502.14802. Tables 2, 3 and 12.
- **RAG vs. GraphRAG, Han et al., preprint v3**: https://arxiv.org/abs/2502.11371. Tables 1, 2 and 32.
- **When to use Graphs in RAG, GraphRAG-Bench, Xiang et al., ICLR 2026**: https://arxiv.org/abs/2506.05690. Tables 3, 6, 15, 16 and 17.
- **How Significant Are the Real Performance Gains?, Zeng et al., preprint**: https://arxiv.org/abs/2506.06331.
- **SPRIG, PingCAP, preprint**: https://arxiv.org/abs/2602.23372.
- **Silicon detector literature benchmark, Gao et al., preprint**: https://arxiv.org/abs/2606.24725.
- **HippoRAG_2 dataset**: https://huggingface.co/datasets/osunlp/HippoRAG_2, revision 5ec05b38.
- **Text2Cypher, Neo4j, preprint**: https://arxiv.org/abs/2412.10064. **Zep and Graphiti, preprint**: https://arxiv.org/abs/2501.13956. Abstracts only.

### Phase 6

- **vCache, ICLR 2026**: https://arxiv.org/abs/2502.03771. Section 5, Appendices F and H.
- **Closing the Operational Gap in Semantic Caching, EMNLP 2026 Industry**: https://arxiv.org/abs/2606.19719.
- **CacheAttack, ICML 2026**: https://arxiv.org/abs/2601.23088. **Early Bird, IEEE TIFS**: https://arxiv.org/abs/2409.20002.
- **NevIR, EACL 2024**: https://aclanthology.org/2024.eacl-long.139.pdf. Table 2.
- **GPTCache 0.1.44 and PR #702**: https://github.com/zilliztech/GPTCache. **RedisVL v0.27.2**: https://github.com/redis/redis-vl-python.
- **Anthropic citations docs**: https://platform.claude.com/docs/en/build-with-claude/citations.
- **OpenAI file search guide**: https://developers.openai.com/api/docs/guides/tools-file-search.
- **AWS Bedrock contextual grounding**: https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html. **Google check grounding**: https://docs.cloud.google.com/generative-ai-app-builder/docs/check-grounding.
- **Verify with Caution, USC**: https://arxiv.org/abs/2501.14883. **LettuceDetect**: https://arxiv.org/abs/2502.17125. **MiniCheck, EMNLP 2024**: https://arxiv.org/abs/2404.10774. **LLM-AggreFact**: https://llm-aggrefact.github.io/.
- **Sufficient Context, ICLR 2025**: https://arxiv.org/abs/2411.06037. **ALCE, EMNLP 2023**: https://arxiv.org/abs/2305.14627.

### Phase 7

- **pgvector README v0.8.6**: https://github.com/pgvector/pgvector/blob/v0.8.6/README.md, lines 444 to 475.
- **Pinecone multitenancy, limits**: https://docs.pinecone.io/guides/index-data/implement-multitenancy and the object and operation limits pages.
- **Qdrant multitenancy**: https://qdrant.tech/documentation/manage-data/multitenancy/. **Qdrant source v1.19.1**.
- **Weaviate data concepts and tenant states**: https://docs.weaviate.io/weaviate/concepts/data, https://docs.weaviate.io/weaviate/manage-collections/tenant-states.
- **Milvus multi-tenancy**: https://milvus.io/docs/multi_tenancy.md. Needs a cookie jar. **Milvus source v3.0.2**.
- **turbopuffer concepts, limits, pricing**: https://turbopuffer.com/docs/concepts, /docs/limits, /pricing.
- **Elasticsearch kNN and shard sizing**: https://www.elastic.co/docs/solutions/search/vector/knn and the size-shards page.
- **Curator, preprint**: https://arxiv.org/abs/2401.07119. **HONEYBEE, SIGMOD 2026 per comment**: https://arxiv.org/abs/2505.01538.
- **FAISS HNSW.cpp v1.15.1**: https://github.com/facebookresearch/faiss/blob/v1.15.1/faiss/impl/HNSW.cpp, lines 1142 to 1191.
- **Marten issue #5419**: https://github.com/JasperFx/marten/issues/5419.
- **PostgreSQL Row Security Policies**: https://www.postgresql.org/docs/current/ddl-rowsecurity.html. Bypass rules for superusers, BYPASSRLS and owners.
- **pgvector CVE-2026-3172, issue 959**: https://github.com/pgvector/pgvector/issues/959. Cited from Module 3, Phase 3 line 818, not re-fetched in review.

## 9. Tools and versions to pin

Versions from PyPI JSON and GitHub on 2026-09-23, copied from the five reports. Re-check before generating.

| Tool | Version | Date | Notes |
|---|---|---|---|
| Harness pins | Python 3.12.14, numpy 2.5.3, scipy 1.18.1, torch 2.14.0, transformers 5.17.0, sentence-transformers 6.1.0, faiss-cpu 1.15.1, hnswlib 0.8.0, bm25s 0.3.11, PyStemmer 3.1.0 | per HARNESS.md | Reuse, do not add a second environment |
| pyarrow | 25.0.1 | 2026-08-10 | Only to read parquet in L6 and L13. Use `--with pyarrow` |
| graphrag | 3.1.2 | 2026-08-21 | Maintenance mode. Python below 3.14. 1.2.3 backport on 2026-09-21 is not the latest |
| lightrag-hku | 1.5.7 | 2026-09-02 | Active |
| hipporag | 2.0.0a4 | 2025-06-24 | Alpha |
| benchmark-qed | 0.4.0 | 2026-05-27 | Microsoft LLM-judge benchmark |
| networkx, igraph, leidenalg | 3.7, 1.0.0, 0.12.0 | 2026 | Not needed for L10 |
| tiktoken | 0.14.0 | 2026-08-17 | o200k_base counts |
| gptcache | 0.1.44 | 2024-08-01 | No release since. Repository active |
| redisvl | 0.27.2 | 2026-09-10 | Needs a Redis server. Read the code only |
| vCache | 0.1.0 in pyproject, no release | GitHub master | CC BY-NC-ND 3.0. Defaults to OpenAI |
| lettucedetect | 0.2.3 | 2026-08-13 | MIT |
| MiniCheck | GitHub main | n/a | PyPI `minicheck` is a different project |
| duckdb | 1.5.5 | 2026-07-22 | Optional for L1 |
| sqlglot | 30.19.0 | 2026-09-22 | Optional, to parse generated SQL in L3 |
| SQLite | 3.51.0 | laptop | Standard library |
| PostgreSQL and pgvector on the laptop | 14.24 and 0.8.1, x86_64 under Rosetta | installed | pgvector 0.8.6 is current. 0.8.1 has CVE-2026-3172: throwaway cluster with public data only. Never touch the other PostgreSQL server that runs on this machine for another project |
| Qwen/Qwen2.5-0.5B-Instruct | revision 7ae55760, 988,097,824 bytes | checked 2026-09-23 | L9 closed-book reader. Apache 2.0. Added in review |
| PopQA `test.tsv` and `popqa_contexts.jsonl.gz` | revisions 098765c7 and 1b91217d | checked 2026-09-23 | L9 data, 50.6 MB. Added in review |
| Qdrant, Weaviate, Milvus servers | 1.19.1, 1.39.6, 3.0.2 | 2026-09 | Docs and source only |
| Pinecone client, turbopuffer client | 10.0.0, 2.10.1 | 2026-09 | No lab uses them |
| openai/codex | rust-v0.156.1 | 2026-09-23 | L2 corpus. Pin the tag |
| ripgrep | 15.2.0 latest; 15.1.0 on the laptop | release date not checked | |
| FlashRAG | v0.3.0 | 2025-08-18 | Implements many adaptive RAG methods. PyPI `flashrag-dev` is stale |
| scikit-learn | 1.9.1 | 2026-09-10 | Avoid next to torch until its libomp is checked |

## 10. Open questions and disagreements

- **Grep against embeddings for code agents.** Anthropic, OpenAI and Google ship grep-based agents without a published measurement. Cursor and GitHub publish gains from embeddings with few conditions. Sen et al. favour grep for literal answers. Rafiei Oskooei et al., arXiv 2608.01507, favour vector search over a sub-agent design. Each study changes the harness, output delivery or query type along with the retriever. Not settled.
- **Does long context beat RAG?** Self-Route and Li et al. 2501.01880 say LC wins on average. OP-RAG and LaRA at 128k say RAG wins in some settings. The causes are the scorer, truncation of long inputs, and model strength. Token Tax is the only current-model study, and it is one preprint.
- **Do uncertainty gates match complex methods on multi-hop?** Moskvoretskii et al. say they match. Their own 2Wiki row shows 0.384 against 0.454.
- **FLARE's value.** Its paper shows a win with text-davinci-003. DRAGIN, Probing-RAG and Moskvoretskii et al. show it losing to one retrieval on open models.
- **Format reward in RL search training.** Search-R1 uses none. The follow-up by the same first author finds one raises 3B base from 0.303 to 0.389 EM.
- **Size of agentic cost.** 1.2 to 1.4 times for a reasoning model, 1.4 to 1.5 times in time against a tuned pipeline, 3.3 to 10 times against one retrieval with small models, 15 times against chat for multi-agent. These are different baselines.
- **Is Microsoft GraphRAG good at QA?** Edge et al. never test QA with gold. HippoRAG 2 and GraphRAG-Bench show it losing on fact QA. Zhou et al., PVLDB, report graph methods above VanillaRAG on most datasets with Llama-3-8B and k = 4. Han et al. find a tie with token-matched RAG that flips sign between an 8B and a 70B reader. Reader strength and top-k may split them. Not tested.
- **Do graph gains grow with corpus size?** Zeng et al. say yes, with a debiased LLM judge. The only sweep, Xiang et al. Table 17, repeats other tables. L11 could test it.
- **LazyGraphRAG indexing cost.** Microsoft says "identical to vector RAG". Xiang et al. list 591,150 tokens for a 56k-token book, with an implementation that is not Microsoft's.
- **Text-to-SQL error rates.** The arXiv v3 says 62.8% for Spider 2.0-Snow on 121 examples. The CIDR 2026 abstract says 66.1%. The Spider 2.0-Snow leaderboard top score is 96.70 on the same benchmark.
- **GPTCache default threshold.** CacheAttack says 0.7. The config file at 0.1.44 and the Early Bird paper say 0.8. The number is not a cosine either way.
- **Which metric selects a cache model.** A 2025 Redis paper reports average precision. A 2026 Redis paper says that metric misleads at a fixed threshold.
- **Per-tenant memory.** 10.1 times in Curator, 7 times in HONEYBEE, 1.000 times in L16. The cause is vector sharing, not the index type.
- **Weaviate tenant management.** A 2025 blog describes a "Tenant Controller" that activates tenants by demand. The current docs say Weaviate never deactivates a tenant on its own. Trust the 1.39 docs.
- **Per-tenant IDF.** Qdrant presents it as a fix. L18 found shared IDF better for small tenants on seed 0, p = 0.0007, but not on seed 1, p = 0.163. Medium tenants favoured shared IDF on both seeds. One domain.
- **Filtering inside the graph walk.** Module 3, 3.4 found hnswlib's filtered sweep at recall 1.000 at every share. L16 found FAISS's in-walk filter at 0.656 to 0.693 for small tenants. The FAISS stop rule counts disallowed candidates, verified from source. That hnswlib's does not is inferred. Added in review.
- **Where pgvector's planner switches to exact search.** Module 3 E12 put it between 1% and 10% of rows. The review run on another table put it between 1.88% and 2.14%. The switch comes from cost estimates, so it moves with table statistics and settings.

## 11. Things I could NOT verify

- **Time to first token for a cached 900k-token prompt on a current model.** Check: time cached and uncached requests with the Module 1, 1.2 method and an API key.
- **Gemini explicit cache creation billing.** Check: ai.google.dev caching docs and a billed test request.
- **The Token Tax result with caching on.** Check: rerun their released code with prompt caching.
- **Whether Claude Code's client uses any embedding internally.** The client source is not public. Check: an official statement.
- **Cursor's 12.5% sample size and whether it is relative.** Check: a public Cursor Context Bench release.
- **Copilot's benchmark mix for 0.362 to 0.498.** Check: the post's figure source.
- **DCI's BM25 baseline.** Check: rerun github.com/DCI-Agent/DCI-Agent-Lite on its 50 SciFact queries.
- **ReaLM-Retrieve's MuSiQue subset and scorer.** Check: its evaluation appendix or released code.
- **Opus 4.6 single-agent BrowseComp score.** It is in a chart image. Check: the system card.
- **Anthropic's 90.2% internal eval.** Not public. No check exists.
- **The text of the L9 passage set.** `ryannoonan/popqa-wikipedia-contexts` has one uploader. Check: compare 50 random articles with the Wikipedia revision they name.
- **L9 end to end.** The closed-book run of Qwen2.5-0.5B on MPS and the gate results are not measured. Check: build and run L9 on the 1,000-question test split.
- **The Azure semantic cache score unit.** Module 1, 5.6 quotes a threshold of 0.05. Whether it is 1 minus cosine is inferred. Check: the Azure API Management semantic cache policy reference.
- **hnswlib's filtered stop rule.** Check: `hnswalg.h` at hnswlib 0.8.0.
- **Perplexity's deep research method.** HTTP 403 twice. Check: open the page in a browser.
- **The Spider 2.0 organizers' gold corrections.** Check: the data update log on spider2-sql.github.io against the UIUC error list.
- **Text2Cypher and Graphiti numbers beyond the abstracts.** Check: their tables. Graphiti belongs mostly to Module 10.
- **CoIR and CodeRAG-Bench per-task tables.** Abstracts only. Check: the PDFs.
- **Whether graphrag 3.1.2 turns dynamic community selection on by default, and the cost of `--method fast` and `standard-update`.** Check: trace the config and run on a small corpus.
- **vCache's error bound under non-i.i.d. traffic.** Check: replay a time-ordered log with a topic shift.
- **Hit-rate loss from per-user cache scope on real traffic.** No source measures it.
- **LangCache managed service default threshold.** Check: the LangCache API reference.
- **MiniCheck, LettuceDetect, HHEM and AlignScore on the L15 pairs.** Not run. LLM-AggreFact data is gated.
- **Per-object memory of a collection, shard or tenant in Qdrant, Weaviate, Milvus and Elasticsearch.** Check: create 1,000 empty tenants and measure RSS and open files.
- **Measured noisy-neighbour interference in any vector database.** None found.
- **Seed 2 small-bucket p = 0.058 in L16.** Check: re-run with 1,000,000 flips.
- **Venues.** Self-RAG at ICLR 2024, LightRAG at EMNLP 2025, LinearRAG at ICLR 2026, Wallat et al. at ICTIR 2025, RAGTruth at ACL 2024, CodeRAG-Bench. Each comes from a secondary mention or a repository title.
- **Licences** of the HippoRAG_2 dataset, 2WikiMultihopQA and MuSiQue, and QQP.
- **ripgrep 15.2.0 release date.** GitHub API rate limit.
- **The L10 graph result under other hyperparameters.** One configuration was run. Check: sweep seed k and restart on a held-out half with Holm correction.

## 12. Notes for the course generator

- Say which baseline every "wins" is measured against. GraphRAG's 72% to 83% is against vector-only RAG, judged by an LLM, with no gold. Never teach it as "GraphRAG beats RAG".
- Do not teach a GraphRAG corpus-size crossover. None is published. Xiang et al. Table 17 repeats other tables.
- Do not quote Spider 2.0 or BIRD leaderboard scores as text-to-SQL accuracy. Quote the annotation error rates next to them, with sample sizes.
- Do not cite the DCI paper's IR ranking gains. Its BM25 SciFact baseline is outside any plausible range.
- Treat ReaLM-Retrieve absolute values as unconfirmed. Use only its ratios.
- The Token Tax cost gap was computed without caching. Say so, and show the cached number from L4.
- The 4× and 15× Anthropic ratios are relative to chat. Module 2, 4.1 already corrected this. Link it.
- Cursor's 12.5% and Anthropic's "by a lot" are both vendor claims without datasets. Teach the disagreement, not a winner.
- A semantic cache "threshold" means different things in GPTCache, RedisVL and LangCache. Name the library, version and unit every time.
- vCache's error rate divides by all requests. False-hit share divides by hits. Convert before comparing.
- Citations APIs guarantee pointers only. Never say a citation proves support.
- "Per-tenant indexes cost N times the memory" is true only when tenants share vectors. Say the sharing degree.
- Every tenancy lab result must be sliced by tenant size. Uniform sampling puts most queries on large tenants.
- Prices move fastest. Re-fetch Anthropic, OpenAI and Gemini prices, web search prices and file search prices before generating. Reuse Module 1 or Module 2 price files.
- `graphrag`, `lightrag-hku`, Qdrant, Weaviate and Milvus versions moved within days during this research. Re-check them.
- L2 must pin openai/codex rust-v0.156.1. The source changes daily.
- Never load torch and FAISS in one process. Encode first.
- Reuse the harness paired test for every "A beats B" claim, with Holm across slices. Re-run any p between 0.03 and 0.07 with 1,000,000 flips.
- Module 3, lab E12 already ran pgvector 0.8.1 on this machine. L17 builds on it, adds row-level security and filtered recall, and carries the CVE-2026-3172 warning. Label the version.
- TAG's "overall" exact match excludes its aggregation questions. Do not cite TAG as a measurement of top-k on aggregates.
- Do not say BrowseComp shows that training, not the tool, made Deep Research win. The model changed too.
- The loop's loss on comparison questions in L6 is a budget effect. Even the oracle reader loses. Say so.
- Adaptive-RAG's 54.52% classifier accuracy is from the FLAN-T5-XL setting. Do not attach it to GPT-3.5.
- Per-tenant IDF: one seed of two was significant. Teach "did not help", not "hurt".
- Microsoft GraphRAG and "a graph retriever" are different things. Gao et al. and the L10 graph are not Microsoft GraphRAG.

## 13. Gaps to research before building

"Blocks building" means a phase writer cannot write a concept or a lab without it. Gaps marked **closed now** were researched for this dossier. Their results are folded into section 4.

### 13.1 The module question

| Gap | Research question | Where to look | Blocks building? | Status |
|---|---|---|---|---|
| One decision framework | Can the five reports' answers be ordered into one procedure with evidence per step? | Sections 4.1 to 4.30 | Yes, for the closing section of Phase 7 | **Closed now** as 4.32. It is inferred. It has no single study behind it |
| A tool-choosing agent | Does an agent that can call SQL, grep and a vector tool beat a fixed procedure on mixed queries? | New lab on L1 and L2 corpora with a hosted model; ACL and SIGIR 2026 proceedings | No. The procedure can be taught with its stated limit | Remains |
| Latency budget per architecture | What does each replacement add in latency? | Sections 4.9 to 4.31; Module 1, 1.2 | Partly. Needed for Phase 7's map | **Partly closed** as 4.31. Current long-prompt TTFT remains not checked |
| Managed retrieval products | What do hosted file search tools do and cost? | OpenAI file search guide and pricing; Vertex and Bedrock knowledge bases | No | Price closed now: $2.50 per 1,000 calls plus storage. Behaviour remains |

### 13.2 Phase 1: the query picks the tool

| Gap | Research question | Where to look | Blocks building? | Status |
|---|---|---|---|---|
| Text-to-SQL depth and failure modes | How does text-to-SQL fail, and how reliable are its benchmarks? | Spider 2.0 error analysis; Jin et al. 2601.08778; BIRD paper | Yes. Concept 4.4 needs it | **Closed now.** Error classes, 52.8% and 62.8% annotation error rates, rank changes |
| Current embedders on EntityQuestions | Do 2025 to 2026 embedders close the 49.7 against 72.0 gap? | Run bge-small from the harness on EntityQuestions | No. LIMIT and L2 carry the concept | Remains |
| SQL safety for generated queries | Read-only roles, row limits, injection through text-to-SQL | Module 16 dossier | No. Module 16 owns it | Link only |
| Semantic layers and metric definitions | Does a defined metric layer reduce text-to-SQL errors? | dbt and warehouse vendor docs; any controlled study | No | Remains, not checked |
| Code retrieval benchmarks beyond the abstracts | CoIR and CodeRAG-Bench per-task numbers | The PDFs | No | Remains |

### 13.3 Phase 2: no index at all

| Gap | Research question | Where to look | Blocks building? | Status |
|---|---|---|---|---|
| Long context against RAG at current prices with caching | Cost per query today | First-party price pages | Was blocking | Closed by the novector report. Section 4.5 |
| Long context quality on current models | Does LC still beat RAG on 2026 models? | LongBench v2 leaderboard; vendor long-context evals; a rerun of Token Tax | No. Module 2 owns quality. But the key claim rests on **one preprint** | Remains. LongBench v2 abstract read: human experts 53.7%, o1-preview 57.7% |
| Current long-prompt latency | TTFT for cached and uncached 900k prompts | A live timed run | No | Remains |
| Grep against embeddings, controlled | One agent and harness, with and without a vector tool, on a public code set | New study; Agent Retrieval Bench tables | No. Teach as an open question | Remains. Both sides rest on **vendor claims** |
| DCI baseline | Is the DCI paper's BM25 number an error? | Rerun its code | No. Do not cite until checked | Remains, **suspicious preprint number** |

### 13.4 Phases 3 and 4: retrieve or not, and search loops

| Gap | Research question | Where to look | Blocks building? | Status |
|---|---|---|---|---|
| How deep-research and web-search systems retrieve | What do providers say about their search tools, training and limits? | OpenAI system card and API guide; Claude web search docs; Gemini blog; Perplexity post | Yes. Concept 4.14 and the L8 cost ledger need it | **Closed now** for OpenAI, Anthropic and Google. Perplexity returned 403 and remains |
| Price per search | What does one hosted search cost? | Provider price pages | Yes, for L8 | **Closed now.** $10 per 1,000 for Claude and OpenAI; Gemini $14 per 1,000 after 5,000 free |
| End-to-end evaluation for these architectures | Which benchmark fits which architecture? | CRAG, FRAMES, MultiHop-RAG, BrowseComp-Plus | No. Module 11 owns method. But it strengthens 4.9 and 4.10 | **Closed now** for CRAG and FRAMES. MultiHop-RAG abstract only |
| PopQA passages for L9 | Does a public set ship retrieved passages? | Self-RAG repository | Yes, for L9 only | **Closed in review.** Self-RAG passages exist only for 1,399 long-tail questions, and the official link is dead. L9 is redesigned on PopQA `test.tsv` plus subject articles, 50.6 MB, offline after download. See L9 in section 6 |
| ReaLM-Retrieve absolute values | Which MuSiQue subset and scorer? | Its appendix | No. Use ratios only | Remains, **suspicious preprint number** |
| Azure agentic retrieval numbers | Is "+16 points" reproducible? | Microsoft post, LLM judge | No | Remains. **One vendor source** |

### 13.5 Phase 5: entity graphs

| Gap | Research question | Where to look | Blocks building? | Status |
|---|---|---|---|---|
| GraphRAG against hybrid across corpus sizes | At what size and query mix does a graph beat hybrid? | ACL Anthology, SIGIR 2026 | No. L11 can produce it offline | Remains. No published answer |
| Graph stores other than GraphRAG | When is a property graph with Cypher the right store? | Text2Cypher paper tables; Neo4j docs; Spider-style graph benchmarks | No | Partly. Abstracts read; no numbers |
| Temporal knowledge graphs | Zep and Graphiti claims | arXiv 2501.13956 | No. Module 10 owns memory | Remains. **Vendor preprint** |
| LazyGraphRAG results | Are the win rates reproducible? | BenchmarkQED repository | No | Remains. **One vendor source**, LLM judge |
| SPRIG | Does the +0.0970 hold on held-out queries? | Rerun its code | No. L10 reproduces the direction | Remains. **Single-author preprint**, tuned on the test split |

### 13.6 Phase 6: semantic caching

| Gap | Research question | Where to look | Blocks building? | Status |
|---|---|---|---|---|
| Non-i.i.d. traffic | Does vCache's bound hold under a topic shift? | Offline replay in L14 | No | Remains |
| Hit-rate cost of per-user scope | How much hit rate does isolation cost on real traffic? | Production reports; MeanCache logs | No | Remains |
| Maintainer benchmark | Does GPTCache PR #702 hold up? | The PR in a month | No | Remains. **One day old, maintainer data** |

### 13.7 Phase 6: grounding

| Gap | Research question | Where to look | Blocks building? | Status |
|---|---|---|---|---|
| Stronger checkers on the lab pairs | Do MiniCheck or LettuceDetect beat the NLI baseline on L15? | Run them offline | No | Remains |
| Cloud check accuracy | Precision and recall of AWS and Google grounding checks | Engineering posts with conditions | No | Remains. The docs give none |
| Anthropic citation quality | "significantly more likely to cite the most relevant quotes" | Not published | No | Remains. **One vendor claim, no number** |

### 13.8 Phase 7: many tenants

| Gap | Research question | Where to look | Blocks building? | Status |
|---|---|---|---|---|
| Per-object overhead | RAM and open files per empty tenant in each system | Create 1,000 tenants per system | No | Remains |
| Noisy neighbours | Latency interference between tenants | Two-tenant load test | No | Remains. Only vendor claims exist |
| Filtered ANN recall under RLS | Are the 10 rows from `relaxed_order` correct? | Add recall to L17 | Yes, for teaching L17 as correct | **Closed in review.** Mostly, not always. Recall@10 was 0.972 to 1.000 with `relaxed_order` at ef_search 40, with no foreign rows. See 4.28 |
| Cold-tenant latency | turbopuffer's 874 ms has two corpus sizes | Vendor, or a timed run | No | Remains. **One vendor source** |
| Ownership with Module 16 | Where does tenant isolation live? | Module 16, 4.8 and Phase 7 | Yes, for scope | **Decided** in section 5: architecture and cost here, security there |

### 13.9 Key claims that rest on one vendor source or a suspicious preprint number

| Claim | Source | Risk | How the course should use it |
|---|---|---|---|
| Grep "outperformed everything. By a lot." | Anthropic podcast | "mostly vibes" | As a stated position only |
| +12.5% accuracy from semantic search | Cursor | No dataset, no interval | As a stated position only |
| +37.6% relative lift | GitHub | Benchmark not named | Mention only |
| LC 73.1% against RAG 65.4% | Token Tax, one preprint | Only current-model study; no caching | With LaRA and Self-Route beside it |
| Grep 69.0% to 80.0% | DCI preprint | Its BM25 baseline is implausible | Scaling result only, 4.7 |
| ReaLM-Retrieve latencies | SIGIR 2026 per comment | Absolute values conflict | Ratios only |
| 90.2% multi-agent gain | Anthropic internal eval | Not public | Link Module 2, 4.1 |
| 70.48% to 85.30% on BrowseComp-Plus | Anthropic model page | Vendor harness | Mention only |
| +16 points answer relevance | Azure post | LLM judge, vendor | Mention only |
| LazyGraphRAG wins 96 of 96 | Microsoft blog | LLM judge, vendor | With the judge-bias concept 4.15 |
| SPRIG +0.0970 | Single-author preprint | Tuned on the evaluation split | Direction only; L10 reproduces it |
| 874 ms cold p50 | turbopuffer | Two corpus sizes for one number | As a vendor order of magnitude |
| 42.2% verifier precision | GPTCache PR #702 | One day old, model-assisted labels | With L14's own measurement |
| 10.1× per-tenant memory | Curator preprint | Vectors shared 13.37 times | Only with the sharing degree |
| 96.70 on Spider 2.0-Snow | Vendor leaderboard entry | Gold labels had 62.8% errors in the public part | Only next to the error rate |

### 13.10 What remains, in one list

Blocking and still open: **none.** The review closed both blocking gaps.

1. **Filtered ANN recall inside L17. Closed.** The reviewer built the check and ran it on a throwaway cluster. With iterative scans on, recall@10 was 0.957 to 1.000 and no row came from another tenant. With them off, tenants just above the planner's switch point got about a third of their rows. See 4.28 and L17.
2. **PopQA passages for L9. Closed.** L9 is redesigned on PopQA `test.tsv` plus the subject articles, 50.6 MB of data, offline after one download. See L9.

Must be done by the phase writer before quoting lab numbers, not blocking the outline:

- Run L9 end to end. Its gate results and its MPS run time are not measured.
- Fix the L4 cost formula for an expired cache, as noted in L4.
- Write the "self-test to write" items in L6, L7, L10 and L16.

Not blocking and still open: current long-prompt latency, long-context quality on 2026 models, a controlled grep-against-embeddings study, a GraphRAG corpus-size sweep, graph stores beyond abstracts, Perplexity's method, per-object tenant overhead, noisy neighbours, non-i.i.d. caching, stronger grounding checkers, cloud checker accuracy, a tool-choosing agent study, hnswlib's filtered stop rule, and the provenance of the L9 passage set.

Summary: a vector index is the wrong tool for exact keys, for questions that need every matching row, for corpora small enough to read, for fast-changing file trees, and for questions the model already knows. Key lookup, SQL, long context, grep and a retrieval gate replace it there, and each replacement has a measured place where it loses.

## 14. Review log

Reviewer: an independent agent, 2026-09-23. Method: re-open each primary source, re-fetch where marked, re-run three labs, build the L17 check, research the L9 data, and compare every concept with Modules 1 to 3 as built. Working files: `scratchpad/review_m04/`. The dossier before review is saved as `scratchpad/review_m04/dossier_before_review.md`.

### 14.1 Spot checks

"Saved" means the reviewer grepped the author's saved copy of the primary source. "Re-fetched" means the reviewer downloaded the source again on 2026-09-23 and grepped that copy. "Re-run" means the reviewer ran the lab again. Items 40 to 59 were checked by a sub-agent of the reviewer. Its full table is `review_m04/spot/spot_phases4to7.md`.

| # | Concept | Claim checked | How | Verdict |
|---|---|---|---|---|
| 1 | 4.1 | TAG Table 1: RAG 0.00, Text2SQL 0.17, hand-written 0.55, ranking Text2SQL 0.10 | Saved; abstract page re-fetched | Numbers correct. **Imprecise:** "overall" excludes the 20 aggregation questions, footnote 1. Fixed |
| 2 | 4.1 | TableRAG Table 2: 37.7, 43.1, 4.6; tables of 79,000 and 62,000 rows | Saved | Correct |
| 3 | 4.1 | LOFT Table 2: Spider 0.40 Gemini 1.5 Pro, 0.74 DAIL-SQL with the same model; "averaging is the most difficult operation" | Saved | Correct |
| 4 | 4.1 | L1: SQL 1.00, bge-small top-10 0.08, +0.920, 184 wins, 0 losses | Re-run | Identical output |
| 5 | 4.2 | L2: BM25 0.985, bge-small 0.785, +0.200, CI +0.145 to +0.260; set B +0.155 | Re-run | Identical output |
| 6 | 4.2 | EntityQuestions Table 1: DPR 49.7, BM25 72.0 | Saved | Correct |
| 7 | 4.3 | LIMIT Figure 6: 97.8, 83.5, 19.0; synonyms 10.6; "drops more than 89% whereas Qwen3 embedding drops 38.9%" | Re-fetched | Numbers correct. **Imprecise:** every model failed on synonyms, Qwen3 11.6, best 25.6. Fixed |
| 8 | 4.4 | Spider 2.0 error classes 35.5, 10.3, 7.5, 17.7, 27.6, 16.6, 10.1, 8.3 per cent; 755 against 54 columns | Saved | Correct |
| 9 | 4.4 | Spider 2.0: o1-preview agent 21.3% "against 91.2% on Spider 1.0 and 73.0% on BIRD" | Saved | **Imprecise:** 91.2% and 73.0% are earlier GPT-4 methods. Fixed |
| 10 | 4.4 | Jin et al.: 263 of 498, 52.8%; 76 of 121, 62.8%; 16 agents; −7% to 31%; ranks ±9; CHESS 62% to 81%, 7th to 1st; Spearman 0.85 and 0.32 | Saved | Correct |
| 11 | 4.4 | CIDR 2026 abstract: 66.1% and −3% to 31% | Saved | Correct |
| 12 | 4.4 | Spider 2.0-Snow top 96.70 on 547 tasks; BIRD test top 82.39, human 92.96 | Saved, fetched today by the author | Correct |
| 13 | 4.5 | Token Tax: 73.1% against 65.4% on 324 pairs, p = 0.0049; $0.1181 against $0.0045; 247,754 tokens; latency p = 0.128 | Saved | Correct |
| 14 | 4.5 | gpt-5.4-mini $0.75 input, $0.075 cached | Saved model page, today | Correct |
| 15 | 4.5 | LaRA Avg GAP at 128k: 3.68, 22.36, 14.30; 2,326 questions | Saved | Correct |
| 16 | 4.5 | Self-Route: 61% of tokens, 46.83 against 47.04; 63% identical predictions | Saved | Correct |
| 17 | 4.5 | Anthropic: 900k billed like 9k; Sonnet 5 $2, $2.50, $0.20, $10; 5-minute write 1.25× | Re-fetched | Correct |
| 18 | 4.5 | Cost table cells for Sonnet 5 at 100,000 and gpt-6-luna at 900,000 | Recomputed by hand | Correct. The "warm" column assumes one cache write per hour. Stated in 4.5 |
| 19 | 4.5 | gpt-6-luna $0.10, $0.01, $0.125, $0.50; 272K rule at 2× and 1.5× | Re-fetched | Correct |
| 20 | 4.6 | Break-it at one query per hour gives about 1.25× | Read the script | **Error in the lab script:** it prints about 1.35×, write plus read. Fixed in 4.6 and L4 |
| 21 | 4.7 | DCI: 38.5 to 86.9 calls, −13.6 points, 37.5% at 400K, 122.4 calls, 20 at budget; 69.0% to 80.0%; SciFact BM25 15.8 | Saved | Numbers correct. **Condition added:** a 100-question subset. Fixed |
| 22 | 4.7 | DCI check: lowest 50-query BM25 subset 0.4658 | Read run file | Correct |
| 23 | 4.9 | Adaptive-RAG Table 8, GPT-3.5, TriviaQA 64.00 against 55.20; Table 1 average 35.77 against 34.73 | Saved | Correct. NQ shows the same pattern, 39.80 against 32.40. Added |
| 24 | 4.9 | Moskvoretskii Table 1, TriviaQA: never 0.636, always 0.610 | Saved | Correct |
| 25 | 4.9 | Mallen: 10% harmed; recall@1 0.14 against 0.42 | Saved | Correct. **Condition added:** GPT-3 davinci-003, Contriever, PopQA |
| 26 | 4.9 | CRAG Table 5: 33.5 and 13.5 to 35.9 and 28.2; "none ... higher than 20%"; Table 6 Copilot Pro 62.6, 17.9, 11,596 ms; Perplexity 55.8, 25.3; Meta SG 3,431 ms | Saved | Correct. **Condition added:** Table 5 is auto-eval |
| 27 | 4.10 | Adaptive-RAG Table 2: 44.60, 34.40, 9.38×, 23.00, 13.80, 24.40, 27.80 | Saved | Numbers present. Cell positions only partly traced |
| 28 | 4.10 | L6: bridge +0.0625, comparison −0.1991, all +0.0100 | Re-run | Identical output. **Condition added:** the oracle reader also loses 0.2239 on comparison, a budget effect. Heading fixed |
| 29 | 4.10 | FRAMES: 0.408, 0.452, 0.474, 0.729, 0.66; judge accuracy 0.96, kappa 0.889; about 80% of oracle errors | Saved | Correct |
| 30 | 4.11 | BrowseComp-Plus Table 1: 55.90% and 23.23 calls, 70.12% and 21.74; Table 8 $400.36 and $360.71; cheaper for every model | Saved | Correct |
| 31 | 4.11 | BrowseComp: 0.6%, 1.9%, 51.5%; footnote on training | Saved | Numbers correct. **Over-claim** in "the trained policy made the difference": the model changed too. Fixed |
| 32 | 4.12 | Moskvoretskii NQ: 0.512 with 1.8 LM and 0.81 retrieval calls; DRAGIN 0.480 and 4.5; SeaKR 0.406 and 14.6; 2Wiki 0.384 against 0.454 to 0.456 | Saved | Correct |
| 33 | 4.12 | Adaptive-RAG GPT-3.5: 37.97 at 1.46; 38.13 at 3.33; oracle 47.70; classifier 54.52% and 30.52% | Saved | First four correct. **Imprecise:** the classifier numbers are from the FLAN-T5-XL setting. Fixed |
| 34 | 4.13 | Adaptive-RAG Table 3: 0.35, 3.08, 27.18 s; caption names no model | Saved | Correct |
| 35 | 4.13 | "Is Agentic RAG worth it?" Table 9: 1.5, 2.7, 1.7 and 1.4, 3.6, 1.8; text 3.3×; retrieval 0–5% of time | Saved | Correct |
| 36 | 4.13 | Claude web search $10 per 1,000 searches plus tokens | Re-fetched | Correct |
| 37 | 4.13 | OpenAI web search $10 per 1k plus content tokens; 8,000-token block for two mini models; file search $2.50 per 1k and $0.10 per GB-day after 1 GB | Re-fetched | Correct |
| 38 | 4.13 | Gemini grounding: 5,000 free per month, then $14 per 1,000 | Saved, today | Correct |
| 39 | 4.28 | RLS run: small tenants 10.00 rows with B-tree, 3.27 without, 1 of 40 full | Re-run on a new cluster | Identical: 10.00, 3.27, 1 of 40, and 7.75, 6.53, 3.30 in the other bands |
| 40 | 4.15 | Edge et al.: 72–83%, p < .001, Podcast; 125 questions; 5.2 caveat | Re-fetched | **Imprecise:** the 5.2 caveat is Experiment 2; Experiment 1 found C2 and C3 beating TS. Fixed |
| 41 | 4.15 | Zeng et al.: "over 30%"; 66.70% to 39.06% | Re-fetched | **Imprecise:** Section VI.C, not V.C, and a new setup. Fixed |
| 42 | 4.16 | HippoRAG 2: averages 49.6, 57.0, 47.7; 6 of 7; "1,000 queries per dataset over 6,119 to 11,656 passages" | Re-fetched | **Error:** LV-Eval 124 and NarrativeQA 293 queries; 4,111 to 22,849 passages. Fixed |
| 43 | 4.17 | HippoRAG 2 Table 12: 115.5M and 36.1M tokens; 9.2M and 3.0M; 1.7M and 0.2M; 12.1 against 277.0 min; 0.3 against 10.7 s; 4 H100 | Re-fetched | Correct |
| 44 | 4.16, 4.17, 4.19 | GraphRAG-Bench: 64.73 against 38.63; 331,375 against 879 tokens; "up to 4 × 10^4"; Table 16; Table 17 | Re-fetched | Table 3 and 6 correct. **Error:** RAG did not stay flat in Table 16, 56.13 to 59.10. Table 17 compares HippoRAG2, and one row is from the Medical set. Fixed |
| 45 | 4.16 | Han et al.: 69.33 against 69.01; null queries 19.27 against 96.01 | Re-fetched | Correct. The 70B reader flips it, 71.17 against 71.01. Added |
| 46 | 4.16 | Gao et al.: 0.917, 0.896, 0.354; p = 5.52e-7; Paper@5 0.767 | Re-fetched | Numbers correct. **Imprecise:** 48 queries, own graph not Microsoft GraphRAG, hybrid against BM25 p = 0.788. Fixed |
| 47 | 4.17 | graphrag v3.1.2 maintenance notice; release 2026-08-21; defaults gpt-4.1, text-embedding-3-large, 1,200 | Re-fetched | Correct. Path is `packages/graphrag/graphrag/config/defaults.py` |
| 48 | 4.20, 4.21 | vCache: 0.84 against 0.85; 1.7% after 150k; 57% hit, under 0.5% error; "above 1.5%"; labels | Re-fetched | Numbers correct. **Imprecise:** label source differs per result. Fixed |
| 49 | 4.22 | CacheAttack 86% at τ = 0.8 | Re-fetched | **Imprecise:** 86.9% for the simple variant on GPTCache, 83.1% for the preferred one, 50 NQ prompts, Section 6.2. Fixed |
| 50 | 4.20 | NevIR: no bi-encoder above 11.1%; random 25% | Saved | Correct |
| 51 | 4.20 | GPTCache PR #702: merged 2026-09-22; 42.2% and 82.3% on 1,536 labels; tuned 42.3% | Re-fetched | Correct. Default on the test split is 43.9%. Added |
| 52 | 4.25 | Sufficient Context: 84.1% to 52%; 100% to 18.6%; "35–62%" | Re-fetched | Numbers correct. **Imprecise:** source sections. Fixed |
| 53 | 4.24 | LettuceDetect Table 2: 80.44 and 78.05; gpt-4-turbo 46.9 and 97.9 | Re-fetched | Correct, both example level |
| 54 | 4.24 | Godbole and Jia: IoU under 50% on 5 of 14; gap over 20% on 7 of 14 | Saved | Correct |
| 55 | 4.23 | Wallat et al.: 57% | Saved | **Imprecise:** 273 of 476 repeated statements; random documents 12%. Fixed |
| 56 | 4.26 | Curator: 10.1× memory; 13.37 tenants per vector | Re-fetched | Correct. Conditions added |
| 57 | 4.29 | Pinecone RU rule and "scan the entire namespace"; turbopuffer 1.28 GB minimum | Re-fetched | Correct |
| 58 | 4.27 | FAISS HNSW.cpp lines 1142, 1191, 1158–1165 | Re-fetched | Finding correct. **Imprecise:** the push is at line 1199. Fixed |
| 59 | 4.28 | Marten #5419 as "a real incident" | Re-fetched | **Imprecise:** a maintainer bug report closed the same day; the tenant case is not reproduced. Fixed |
| 60 | 4.30 | PostgreSQL RLS bypass rules | Re-fetched | Correct |

Result: 60 checks. 2 errors in the text, 1 error in a lab script, 1 over-claim, and 17 imprecise items. No headline number was wrong. Every error and imprecision is fixed in the text above.

### 14.2 Corrections, in order of the document

1. **Header.** Added the review status and the reviewer's re-runs.
2. **Section 1, case 3.** Added the 10-document budget.
3. **Section 2, overlap table.** Rows for Module 3, 1.4, 3.1 to 3.3, 3.5 and 5.1 said this module adds things Module 3 already teaches. Corrected with line numbers. Added five missing rows: Module 1, 5.6. Module 3, 2.2. Module 3, 3.4. Module 2, 1.3. Module 1, 3.4.
4. **Section 2, "A correction for Module 3".** Stale. Module 3 now runs pgvector 0.8.1 in E12. Replaced, with the CVE warning.
5. **Section 3.** Marten and GPTCache rows reworded.
6. **4.1.** TAG's overall score excludes aggregation questions. Its role as evidence is downgraded to indirect.
7. **4.2.** Heading rewritten: the condition is that query and index split the key the same way. Marked for merge with 4.3.
8. **4.3.** LIMIT synonym result: every model fails, so it does not show dense retrieval winning. Marked as mostly taught in Module 3, 5.1.
9. **4.4.** The 91.2% and 73.0% belong to GPT-4 methods.
10. **4.5.** Heading rewritten from "can beat RAG on quality" to a cost-first claim, because the quality evidence splits. Cost assumption of one write per hour stated. Prices re-verified.
11. **4.6.** Marked as mostly taught in Module 1, 3.2 and Module 2, 2.2. The break-it script bug noted.
12. **4.7.** DCI's 100-question subset and model stated.
13. **4.9.** Mallen conditions, the NQ row, and CRAG's auto-eval condition added.
14. **4.10.** Heading rewritten with the budget condition. The oracle-reader loss explains the comparison result.
15. **4.11.** Over-claim removed: BrowseComp cannot separate training from the model.
16. **4.12.** Heading rewritten: the gate result holds on single-hop sets, not multi-hop. Classifier accuracy moved to its FLAN-T5-XL setting.
17. **4.13.** The 4× and 15× bullet reduced to a link to Module 2, 4.1.
18. **4.14.** Marked as vendor-only evidence and folded into 4.11 and 4.13.
19. **4.15.** Experiment 1 against Experiment 2 split stated. Zeng et al. section and setup corrected.
20. **4.16.** HippoRAG 2 sample sizes corrected. Han et al. 70B reversal added. Gao et al. labelled as not Microsoft GraphRAG, with its sample size and the non-significant BM25 comparison. Table 17 description corrected.
21. **4.19.** RAG in Table 16 rose from 56.13 to 59.10. It did not stay flat. Marked for folding into 4.18.
22. **4.20.** Link to Module 1, 5.6 and the Azure threshold units added.
23. **4.21.** Label source named per vCache result.
24. **4.22.** CacheAttack numbers, variant and section corrected. Link to Module 1, 5.6 added.
25. **4.23.** Wallat et al. denominator and control added.
26. **4.25.** Source sections corrected. Moved to Phase 3.
27. **4.26.** Link to Module 3, 2.2 and Curator conditions added.
28. **4.27.** FAISS line numbers corrected. The small-tenant bucket got 8.47 rows. The apparent conflict with Module 3, 3.4 explained, inferred, with a check.
29. **4.28.** Heading rewritten. The reviewer's filtered-recall run and planner switch point added. The claim that Module 3 lists Lucene and OpenSearch removed. Marten wording corrected.
30. **4.29.** Per-tenant IDF: seed 1 did not repeat the small-tenant result.
31. **4.30.** Narrowed to the part a learner can get wrong. RLS owner rule stated with `FORCE ROW LEVEL SECURITY`.
32. **4.31.** The "text-davinci-003" label on the rewrite latency is not checked. Removed.
33. **Section 5.** Replaced with the decided phase structure, the final claim sentences, the links, and a table of concepts that rest on one vendor or one preprint.
34. **Section 6.** Labs regrouped by the new phases. L4 formula fix. L6 oracle-reader note. L9 redesigned. L17 rewritten with the correctness check, the CVE warning and its prior art.
35. **Sections 7 to 13.** Failure stories, sources, tools, disagreements, unverified items and notes updated to match. Both blocking gaps closed.

### 14.3 The two blocking gaps

**L17, filtered recall under row-level security.** Built and run. Throwaway cluster, PostgreSQL 14.24 and pgvector 0.8.1 at `/usr/local/bin`, data folder in the scratchpad, 127.0.0.1 port 55461, no Unix socket. The cluster was stopped and its folder deleted after each run. `lsof` showed nothing listening on port 55461 afterwards. The other PostgreSQL server on this machine was not touched. Results are in 4.28. Files: `review_m04/l17/RESULTS_l17.txt`, `RESULTS_plan_by_size.txt`, `run_l17.py`, `prep.py`, `plan_by_size.py`, `truth.json`.

**L9, passages for the retrieve-or-not gate.** Closed by redesign. Self-RAG's passages cover only 1,399 long-tail questions with popularity 2 to 99, and the official link is dead. The chosen design uses all 14,267 PopQA questions plus a 45.4 MB set of subject articles, CC BY-SA 4.0. It runs offline after about 50.6 MB of data and a 988 MB model. Files: `review_m04/l9/l9.md` and its scripts.

### 14.4 Overlap with Modules 1 to 3

Checked against `module-01-coverage.md`, `module-02-coverage.md` and the seven Module 3 phase files, and the Module 1 and 2 phase files where the coverage files were thin. Full table: `review_m04/overlap/overlap.md`. Line numbers are from about 14:46 on 2026-09-23. Another agent was editing Module 3 then, so lines may move.

- **Already taught, now a link:** the B-tree exact path of 4.28, in Module 3, 3.3. Most of 4.6, in Module 1, 3.2 and Module 2, 2.2. The mechanism of 4.3, in Module 3, 5.1. The 4× and 15× ratios in 4.13, in Module 2, 4.1.
- **Partly taught, overlap cut to a link:** 4.2, 4.5, 4.8, 4.9, 4.12, 4.14, 4.20, 4.22, 4.26, 4.27, 4.29, 4.31.
- **Not taught before:** 4.1, 4.4, 4.7, 4.10, 4.11, 4.15 to 4.19, 4.21, 4.23 to 4.25, 4.30, 4.32.

### 14.5 Final phase structure

Seven phases. The draft's Phase 3 is split, and its Phases 5 and 6 are merged. Section 5 gives the reasons, the claim sentences and the links.

| Phase | Title | Concepts, from section 4 | Decision |
|---|---|---|---|
| 1 | The query picks the tool | 4.1, 4.2 with 4.3, 4.4 | Key lookup, SQL, BM25 or dense per query class |
| 2 | No index at all | 4.5 with 4.6, 4.7, 4.8 | When to skip the index, and its cost |
| 3 | Retrieve or not | 4.9, 4.25, 4.12 | Whether to gate retrieval, and on which signal |
| 4 | Search loops and their budget | 4.10, 4.11, 4.13 with 4.14 | Which queries get a loop, and the budget |
| 5 | Entity graphs for multi-hop questions | 4.15, 4.16, 4.17, 4.18 with 4.19 | Whether a graph earns its indexing cost |
| 6 | Scores that decide correctness | 4.20, 4.21, 4.22, 4.23, 4.24 | Which check before and after the model, at what threshold |
| 7 | Many tenants, and the module map | 4.26, 4.27 with 4.28, 4.29, 4.30, closing 4.31 and 4.32 | Index, namespace or filter per tenant size |

Summary of the review: the headline numbers held, the phase outline broke Rule 0 in one place and is now fixed, several concepts were already taught and are now links, and both blocking gaps are closed.

### Corrections after the course was built (2026-09-23)

- Token Tax cost ratio is 26.6, not 26 (Module 4, Phase 2 review).
- Loop cost multiplier in the lab runs from 1.01 to 10.34, so "about 1 to about 10", not "about 1.2" (Module 4, Phase 4 review).
- The tenancy prototype compared unequal search effort. At equal ef the all-query loss is significant on 2 of 3 seeds (Module 4, Phase 7).
- Other corrections made while building the course are in `advanced-retrieval/course.json` → `reviewLog` and the phase review reports.

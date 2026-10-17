# Module 13: Serving and self-hosting at cluster scale

Research date: 2026-09-25. Status: research dossier, not course material. Reviewed on 2026-09-25 by an independent reviewer. Corrections are in the text and in section 10.

Module question: **At what point does self-hosting beat an API, and what do you take on when it does?**

Topic id: `serving-cluster`.

## How this dossier was built

- **Inputs.** Three research reports written on 2026-09-25 in `scratchpad/reports/`: `research_serving-cluster_econ.md`, `research_serving-cluster_disagg.md` and `research_serving-cluster_routing.md`. Below they are the economics report, the disaggregation report and the routing report.
- **Path short names.** `RS/` means `scratchpad/research_serving-cluster/`.
  - `E/` is `RS/econ/`. `EP/` is `RS/econ/proto/`.
  - `D/` is `RS/disagg/src/`. `DP/` is `RS/disagg/proto/`.
  - `VL/` is `D/tar/x/vllm-0.30.0/`, the vLLM source at tag `v0.30.0`.
  - `SG/` is `D/tar/x/sglang-0.5.20/`. `NX/` is `D/tar/x/nixl-1.4.1/`.
  - `DY/` is `D/tar/x/dynamo-1.5.0/docs/fern/pages/`, the Dynamo docs at tag `v1.5.0`.
  - `R/` is `RS/routing/src/`. `RW/` is `RS/routing/web/`. `RP/` is `RS/routing/proto/`.
  - `M1/` is `study-material/inference-internals/`, the built Module 1.
  - `D13/` is `scratchpad/dossier_m13/`, this dossier's notes.
- **Other inputs.** The Module 13 brief in `_curriculum/README.md`, section "### Module 13". The rules in `scratchpad/briefs/BRIEF_research.md`, `research-method.md` and `writing-style.md`. The structure of `_curriculum/module-10-memory.md`.
- **Work done for this dossier.** No lab ran. No URL was fetched. The dossier author did four read-only things:
  1. Re-grepped 116 anchors of section 4 in their saved files. Script `D13/anchor_check.py`, output `D13/anchor_check.txt`. **116 of 116 match.** Section 4 opens with the counts.
  2. Recomputed every arithmetic claim. Script `D13/recompute.py`, output `D13/recompute.txt`. Section 5.7 lists what changed.
  3. Read source files at their tags to settle conflicts. Section 7.
  4. Read the Module 1 headings and sections 4.6 and 6.1, and the Module 11 and 12 headings, for the overlap table.
- **Labels.** Every claim is **verified**, **verified by run**, **inferred** or **not checked**.
  - A verified claim names its file and line, or its table.
  - "Verified by run" means a research agent ran a script on 2026-09-25 on the learner's Apple arm64 Mac. The output file is named.
  - An inferred claim names its basis and the check that would confirm it.
  - **Vendor** marks a number that a company published about its own product, on a workload it chose.
- **Hardware of every run.** Apple M4 Pro, 14 cores, arm64, system Python 3.9.6, standard library only. From the disaggregation report section 5 and the economics report section 6.1.
- **Terms used in the whole dossier.**
  - **Self-hosting**: you rent or own GPUs and run an open-weight model on a serving engine such as vLLM or SGLang.
  - **Utilisation, U**: served load divided by the load the fleet can serve at the latency target.
  - **Break-even utilisation, U\***: the utilisation at which self-host cost per request equals API cost per request.
  - **Latency target**: the per-user decode speed or TTFT that the service must meet. Here it is given in tokens per second per user.
  - **Prefill**: the step that reads the whole prompt and builds the KV cache. **Decode**: the step that makes one output token at a time.
  - **KV cache**: the key and value tensors kept per token per layer. Module 1 section 1.3 owns the concept.
  - **PD disaggregation**: prefill and decode run on different GPUs or machines. The KV cache moves from the prefill worker to the decode worker.
  - **KV transfer**: that move. **KV connector**: the vLLM plug-in that performs it.
  - **NIXL**: NVIDIA's point-to-point transfer library for GPU, CPU and storage memory.
  - **KV pool**: a store outside one engine's GPU memory that several engines read. Mooncake Store and LMCache provide one.
  - **TTFT**: time to first token. **TPOT** or **ITL**: time between output tokens.
  - **Goodput**: the highest request rate that still meets the latency targets. Module 1 section 6.1 owns it.
  - **GQA**: grouped-query attention. Several query heads share one K and V head. **MLA**: multi-head latent attention. It stores one compressed vector per layer.
  - **Replica**: one running copy of the model server.
  - **Router**: the component that picks a replica for each request.
  - **Prefix affinity**: sending a request to the replica that already holds its prompt start.
  - **Approximate view**: the router guesses cache contents from its own routing history. **Precise view**: the router reads cache events that the engines publish.
  - **Spill**: the router leaves the cache-holding replica for a less loaded one.

---

## 1. What this module is for

Module 1 teaches one GPU: renting it, serving on it, benchmarking it, and the single-GPU break-even on output tokens. This module covers what changes when one machine is not enough. That means a fleet, a latency target and fixed staff costs. It also means prefill and decode on separate machines, a shared KV store, and a router that knows about caches.

The short answer: **self-hosting beats an API only when four numbers line up.** You need a loose enough latency target. You need an API price well above the cheapest open-weight endpoint. Traffic must be flat enough to keep the fleet busy. The fleet must be large enough to spread a 24-hour on-call rotation. When it does pay, you take on a network and a KV transfer path. You also take on a router with a stale view of the caches, and new failure modes.

| Part of the question | Short answer | Where |
|---|---|---|
| At what utilisation self-hosting is cheaper | Vendor rows only. It depends most on the latency target. The same H200 row gives a break-even of 20.5% at 16 tokens per second per user and 95.4% at 117 | 4.1 |
| Against which API | Against the cheapest gpt-oss-120b endpoint, the loose row needs 77.0%. Against the common $0.60 tier it needs 20.5%. A high API cache hit rate raises the break-even | 4.2 |
| At what utilisation it stops being cheaper | When your traffic shape caps average utilisation below U\*. A fleet sized for peak at 80% runs at 40% on average when peak is twice the mean | 4.3 |
| What fixed costs do | A 24/7 pager needs eight people. With $20,000 a month of fixed cost, 8 GPUs never break even at the tight target. 128 GPUs break even at 68.2% | 4.4 |
| Which throughput number to use | Your own, at your latency target. Published offline and "server" numbers overstate interactive capacity | 4.5, 4.6 |
| What breaks when prefill and decode are on different machines | Throughput does not rise by itself. A slow link makes transfer as long as prefill. The P:D ratio depends on the workload. Leases, timeouts and config mismatches are new failure modes | 4.7 to 4.13 |
| What a cache-aware router needs to know | Per-replica queue, KV usage, cached prefixes, in-flight prompt tokens, block size, loaded LoRA adapters, and the tokenizer | 4.14 |
| What it gains and where it loses | Large wins against round robin on affinity workloads. Losses on hot prefixes, low reuse, stale views and unsynchronised router replicas | 4.15 to 4.17 |

Summary: self-hosting is a bet on utilisation at a latency target against one named API price. At cluster scale it adds a KV network and a cache-aware router that you must operate.

## 2. Scope

### In scope

- The request-level break-even with the input and output mix, the API cache hit rate and the latency target.
- Fleet-level costs: minimum fleet, on-call staffing, the utilisation ceiling from peak-to-mean load, cold start, egress.
- GPU rental prices on 2026-09-25, reserved against on-demand, and the prices announced for 2026-10-01.
- Published throughput at a latency target, and how to read it.
- PD disaggregation: when it helps, what it costs, engine flags at tags, failure modes.
- KV bytes per token by attention type, and the link bandwidth a KV transfer needs.
- KV pools: NIXL, Mooncake and LMCache. Problem, release, and production or research status.
- Cache-aware routing across replicas: signals, published results, failure modes, router versions.

### Out of scope, and the owner of each item

| Topic | Owner |
|---|---|
| Single-GPU rental, billing traps, one engine on one node | Module 1, built sections 4.1, 4.2 and 4.3 |
| Single-GPU output-only break-even against a closed API, the 0.25 engineer line, three conflicting 2026 estimates | Module 1, built section 4.6. This module links it and does not re-derive it |
| KV cache concept and the bytes-per-token formula for GQA | Module 1, built section 1.3 |
| Paged KV, prefix caching inside one server, chunked prefill | Module 1, built sections 2.2, 2.3 and 2.4 |
| Quantization and speculative decoding, and their quality gate | Module 1, built sections 4.4 and 4.5 |
| Replicas from peak load, goodput, N+2, autoscaling on queue depth | Module 1, built section 6.1 |
| Many tenants on one fleet, cache timing side channels, `cache_salt` | Module 1, built section 6.2. Module 16 for security |
| Token classes, cache write and cache hit prices, routing cascades | Module 1, built sections 3.1 to 3.4. Module 14 for per-tenant cost |
| Per-tenant cost attribution, budgets, AI gateways | Module 14, planned, per `_curriculum/README.md` |
| Tracing pipelines and dashboards | Module 15, planned |
| Proving that a self-hosted open model is good enough: eval gates, paired intervals | Module 11, built sections 6.2 and 6.4. Module 12, built section 5.4 |

### Overlap with built modules

Headings were read with `grep '^## '` on `inference-internals/*.md`, `eval-engineering/*.md` and `agent-evals/*.md` on 2026-09-25. `module-01-coverage.md` line 79 says: Module 13 "adds disaggregated serving, KV cache pools, and cluster-level routing".

| Built heading | What it owns | What this module adds |
|---|---|---|
| Module 1, "4.6 — The self-host decision (arithmetic, not preference)" | Output-only break-even on one GPU. `--role cheap` gives 50.5%, `--role deep` gives 10.1%. Engineer line 0.25 FTE at $180,000 a year | Input and output mix, API cache hit rate, latency target, fleet fixed costs, the utilisation ceiling. 4.1 to 4.4. Link 4.6 first. Module 1 4.6 already lists what you take on: capacity planning, GPU supply, engine upgrades, security patches and the pager, `M1/inference-internals-phase-04b-optimizing.md` line 532. Link that list. Add only the headcount from 4.4 and the cluster items from 4.7 to 4.17 |
| Module 1, "4.1 — Renting a GPU for an hour" | Single-GPU prices read 2026-09-13 | Prices on 2026-09-25 across 8 providers, reserved ladders, 2026-10-01 rises. 4.6 and 5.1 |
| Module 1, "4.3 — Benchmarking it" | Measuring one node's throughput, goodput options | Reading published rows at a latency target, and the input-plus-output trap. 4.5 |
| Module 1, "1.3 — The KV cache" | The GQA formula. Llama-3-8B is 128 KB per token | The MLA formula, and bytes moved per request over a network. 4.8, 4.9 |
| Module 1, "2.3 — Prefix caching inside the server" | Reuse inside one engine | Reuse across engines and machines. 4.11, 4.12, 4.14 |
| Module 1, "2.4 — Chunked prefill" | The TTFT against TPOT trade inside one server | Disaggregation as the other answer to the same trade. 4.7 |
| Module 1, "6.1 — Capacity planning" | Goodput. DistServe 13B: 2 prefill plus 1 decode GPU served 10 requests per second, 2.1 times one GPU per GPU. DynamoLLM peak-to-mean 1.7 and 2.8 | Why vLLM says disaggregation does not raise throughput. The P:D ratio from traces. The utilisation ceiling. 4.3, 4.7, 4.10 |
| Module 1, "6.2 — Many tenants on one fleet" | Quotas, `cache_salt` | Not repeated. A shared KV pool across tenants is Module 16 |
| Module 1, "3.4 — Routing cascades" | Routing between models | This module routes between replicas of one model. Different problem |
| Module 1 phase 2A references, lines 610 to 617 | Baseten KV-aware routing and the llm-d predicted-latency blog, as further reading | The router internals, versions, defaults and losses. 4.14 to 4.17 |
| Module 11, "6.4 — A benchmark picks candidates, it does not decide" | Public scores do not decide a release | A self-hosted model swap still needs Module 11's gate. Link only |
| Module 12, "5.4 — Scores move when the provider or the judge changes" | A serving bug that canaries missed | When you self-host, you own that serving bug. Link it in the "what you take on" list |

---

## 3. Sources, with dates, tags and ranks

HTTP status and dates are from the three reports. Every fetch ran on 2026-09-25 IST, between 2026-09-24 22:35 and 22:50 UTC for the economics sources, per `E/fetched_at_utc.txt`. Rank follows `research-method.md` Rule 2. Rank 1 is source at a tag. Rank 2 is docs pinned to a version. Rank 3 is a paper. Rank 5 is a vendor post with conditions. Rank 6 is a vendor page without conditions.

### 3.1 Code and docs at release tags

| Project | Tag checked | Released | Rank | What it settles | Tag |
|---|---|---|---|---|---|
| vLLM | `v0.30.0` | 2026-09-22 | 1, 2 | KV connector flags, lease, failure policy, MLA head size | disagg, core |
| SGLang | `v0.5.20` | 2026-09-18 | 1, 2 | PD flags and timeouts. Gateway `cache_aware` rule and defaults | disagg, routing |
| NVIDIA Dynamo, PyPI `ai-dynamo` | `v1.5.0` | 2026-09-21 GitHub, 2026-09-19 PyPI | 2 | Disaggregation guidance, KV router cost model, event replay | disagg, routing, vendor |
| NIXL | `v1.4.1` | 2026-09-01 | 2 | Linux only, backends | disagg |
| Mooncake, PyPI `mooncake-transfer-engine` | `v0.3.13.post1` | 2026-08-31 | 2 | Transfer Engine, Store, FAST'25 traces | disagg |
| LMCache | `v0.5.5` | 2026-09-12 | 2 | Prerequisites | disagg |
| vLLM production-stack | `vllm-stack-0.1.12`. PyPI `vllm-router` 0.1.15 | 2026-07-24. 2026-07-13 | 1 | `prefixaware` and `kvaware` policies | routing |
| smg | `v1.11.0` | 2026-09-24 | 1 | Spill gate, event mode | routing |
| llm-d | `v0.9.0`. Router `v0.10.0`. `v0.11.0-rc.2` is a pre-release | 2026-08-17. 2026-09-21 | 2 | Scorers, affinity filter, burst producer, benchmark reports | routing |
| AIBrix | `v0.7.0` | 2026-06-18 | 1 | `prefix-cache` imbalance rule | routing |
| Gateway API Inference Extension | `v1.6.2` | 2026-09-17 | 2 | Model-server metrics protocol. EPP moved out | routing |

Versions of vLLM, LMCache, NIXL, `ai-dynamo`, SGLang and `mooncake-transfer-engine` were re-read from the saved PyPI JSON in `D/pypi_*.json` for this dossier. All six match the table. All six GitHub repositories were pushed on 2026-09-24 and none is archived, per the disaggregation report section 2.1. Not re-checked.

### 3.2 Papers

| Title | Org | Date | Status | What to read | Tag |
|---|---|---|---|---|---|
| DistServe, arXiv 2401.09670 | Peking University, StepFun, UC San Diego | v3 2024-06-06 | OSDI 2024, peer reviewed | 3.3, 6.1, 6.3 | disagg |
| Mooncake, FAST'25 | Moonshot AI, Tsinghua University | 2025 | FAST 2025, peer reviewed | 2.2 Eq. 2, 5.1, 5.2, 5.4 | disagg |
| Mooncake, arXiv 2407.00079 | same | latest 2025-09-03 | preprint | abstract only, to compare | disagg |
| LMCache, arXiv 2510.09665 | Tensormesh, University of Chicago | 2025-10-08 | preprint, authors sell the product | 3.1.1, 8.1, 8.5, Table 5 | disagg, vendor |
| TaiChi, arXiv 2508.01989 | Huawei Cloud, CUHK, SYSU | 2025-08-04 | preprint | Table 2, 4.1 | disagg |
| Shared KV caching for replicated 27B inference, arXiv 2609.15021 | UNSW, one author | 2026-09-14 | preprint, 11 days old | abstract, Table 3, 5.2 | disagg |
| When Does Disaggregation Pay?, arXiv 2608.03741 | Imperial College London, Cambridge | 2026 | preprint, simulation only | ablations | disagg |
| A Cost-Benefit Analysis of On-Premise LLM Deployment, arXiv 2509.18101 | two authors list CMU | v1 2025-08-30 | preprint | Section VI, Future Work | econ |
| Beyond Per-Token Pricing, arXiv 2606.11690 | one independent author | 2026-06 | preprint | abstract, hardware section | econ |
| ServerlessLLM, arXiv 2401.14351 | University of Edinburgh, NTU Singapore | 2024 | OSDI 2024, peer reviewed | 2.3 load times | econ |
| Preble, arXiv 2407.00023 | authors named in the report. Venue not checked | v2 2024-10-03 | preprint as saved | motivation | routing |
| DualMap, arXiv 2602.06502 | Yuan, Zuo and others | 2026-02-06 | preprint | section 2 Fig. 1, section 4 | routing |
| CacheRoute, arXiv 2608.19677 | one author | 2026-08-20 | preprint | 5.1 Table 1, 5.3 Table 5 | routing |

### 3.3 Price pages, benchmark data and engineering posts

| Source | Org | Rank | Date read | What it gives | Tag |
|---|---|---|---|---|---|
| Nebius, Together, Lambda, RunPod, CoreWeave, Modal price pages | vendors | price list | 2026-09-25 | GPU-hour prices | econ |
| AWS EC2 on-demand JSON and Capacity Blocks page | AWS | price list | 2026-09-25 | p5, p5en, p6-b200 | econ |
| OpenRouter models API and gpt-oss-120b endpoints API | OpenRouter | price list | 2026-09-25 | 24 endpoint prices | econ |
| DeepSeek Models and Pricing | DeepSeek | price list | 2026-09-25 | cache hit, peak and off-peak | econ |
| `nv_inference_benchmark.json` | NVIDIA, crediting SemiAnalysis InferenceX | vendor data, 5 | 2026-09-25 | 483 rows with per-user speed | econ, vendor |
| NVIDIA AI inference performance page | NVIDIA, MLPerf v6.1 results | vendor page of audited results | 2026-09-25 | offline, server, interactive | econ, vendor |
| MLPerf inference rules | MLCommons | 2 | 2026-09-25 | latency limits, lines 266 to 271 | econ |
| Google SRE book, "Being On-Call" | Google | book chapter, page copyright 2017 | 2026-09-25 | eight-person minimum | econ |
| GCP network pricing | Google Cloud | price list | 2026-09-25 | Premium Tier egress | econ |
| LMSYS posts of 2025-05-05 and 2025-07-20 | SGLang team, Mooncake team | 5 | 2026-09-25 | 96 H100 DeepSeek, 128 H200 Kimi K2 | disagg |
| llm-d guide benchmark reports at `v0.9.0`, llm-d blog 2025-09-24 | llm-d | 5 | 2026-09-25 | routing results against round robin | routing, vendor |
| Dynamo KV router A/B doc at `v1.5.0` | NVIDIA | 5 | 2026-09-25 | Mooncake trace A/B | routing, vendor |
| SGLang v0.4 blog 2024-12-04 | LMSYS | 6, no model or hardware | 2026-09-25 | 1.92x | routing, vendor |
| KubeAI CHWBL post 2025-02-26 | KubeAI | 5 | 2026-09-25 | bounded-load hashing | routing, vendor |

### 3.4 What changed recently

| Date | Change | Source | Why it matters |
|---|---|---|---|
| 2025-02-25 | Mooncake receives the FAST 2025 Best Paper award | `D/mooncake_README_v0.3.13.post1.md` line 70. The usenix.org awards page was not fetched | The KV-centric design is a peer-reviewed reference |
| 2025-05-05 | SGLang runs DeepSeek-V3 with PD and expert parallelism on 96 H100 | LMSYS post | First open recipe for PD at this size |
| 2025-07-20 | Kimi K2 on 128 H200 with 4 prefill and 12 decode nodes | LMSYS post | A public P:D ratio with a stated reason |
| 2025-08-04 | TaiChi: aggregation wins under a tight TTFT target | arXiv 2508.01989 | The main counter-evidence to disaggregation |
| 2025-09-24 | llm-d compares precise and approximate prefix routing, both with load scorers | llm-d blog | First public four-arm routing comparison |
| 2026-02-16 | `InferenceMAX/InferenceMAX` says it moved to `SemiAnalysisAI/InferenceX` | `E/inferencemax_gh.json` | Old benchmark links break |
| 2026-05-07 | vLLM features Mooncake Store | Mooncake README link. The vLLM post was not fetched | A shared KV pool is on vLLM's supported path |
| 2026-06 | Beyond Per-Token Pricing makes utilisation the main variable | arXiv 2606.11690 | Measured cost spans $0.21 to $15.25 per million output tokens |
| by 2026-08-17 | llm-d inference scheduler renamed "llm-d Router". EPP code moved in from GIE | `R/llmd/scheduler_README.md` lines 8 to 12 | Old GIE EPP docs are stale |
| 2026-09-14 | Shared LMCache pool can return wrong KV bytes under a stream-ordering bug | arXiv 2609.15021 | First correctness failure report found for KV pools |
| 2026-09-17 | GIE v1.6.2: EPP, InferenceObjective and BBR "have moved" | `R/gie/README.md` | Study llm-d-router for EPP logic |
| 2026-09-18 | SGLang v0.5.20. The experimental router removes `cache_aware_zmq` and three threshold flags | `R/sglang/README.md` lines 71 to 80 | Tutorials with `--cache-threshold` fail on that router |
| 2026-09-21 and 22 | Dynamo v1.5.0 and vLLM v0.30.0 | release JSON | vLLM still marks disaggregated prefill "(experimental)" |
| 2026-09-22 | `mlcommons/inference_results_v6.1` last push | `E/mlperf_inf_gh.json` | MLPerf v6.1 adds an Interactive scenario for gpt-oss-120b and DeepSeek R1 |
| 2026-10-01, announced | Nebius H100 +16.9%, H200 +20.0%, B200 +18.9% | `E/nebius_prices.txt` line 28 | GPU rent is going up. Recompute any break-even after this date |

---

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Each concept gives one best piece of evidence first, with its conditions. Supporting evidence follows.

**Anchor re-check.** The dossier author re-grepped 116 anchors from this section on 2026-09-25. Whitespace is collapsed, backticks and double asterisks are removed, and curly quotes are made straight. Script `D13/anchor_check.py`, output `D13/anchor_check.txt`. **116 of 116 anchors match their expected count.** 67 are presence checks. 48 check an exact count of 1. 1 is an absence check: "evict" has 0 hits in `R/pstack/hashtrie.py`.

| Concept | Anchors | Concept | Anchors | Concept | Anchors |
|---|---|---|---|---|---|
| 4.1 | 5 of 5 | 4.7 | 7 of 7 | 4.13 | 10 of 10 |
| 4.2 | 7 of 7 | 4.8 | 8 of 8 | 4.14 | 7 of 7 |
| 4.3 | 6 of 6 | 4.9 | 5 of 5 | 4.15 | 10 of 10 |
| 4.4 | 6 of 6 | 4.10 | 5 of 5 | 4.16 | 11 of 11 |
| 4.5 | 6 of 6 | 4.11 | 3 of 3 | 4.17 | 11 of 11 |
| 4.6 | 4 of 4 | 4.12 | 5 of 5 | | |

Two needles needed a change before they matched. Neither changed a fact.

1. The CMU paper splits "in-clude" across a line with a hyphen. The needle now carries the hyphen.
2. The Dynamo overview quotes "silently corrupt output" inside a Markdown block quote. The line starts with "> ". The needle now carries that marker.

### 4.1 Break-even utilisation depends on the latency target more than on the GPU price

- **Best evidence, verified.** gpt-oss-120b on one H200 gives 8,112.3 output tokens per second per GPU at 16.2 tokens per second per user. At 117.0 tokens per second per user it gives 1,746.6. That is 4.6 times less. `E/nv_selected_rows.txt` lines 224 and 218.
  - Conditions: H200, FP4, vLLM, ISL 1,024 and OSL 1,024, run date 2026-03-27, aggregated serving, no speculative decoding. Loose row: TP1, concurrency 512. Tight row: TP4, concurrency 64.
  - Who ran it: NVIDIA publishes the file and credits SemiAnalysis InferenceX. **Vendor** data on vendor-chosen workloads.
- **Verified by run.** The API charges $0.15 input and $0.60 output. The H200 costs $4.50 an hour. U\* is 20.5% at the loose target and 95.4% at the tight target. `EP/run_2026-09-25.txt` section 1. Recomputed: 0.2054 and 0.9542, `D13/recompute.txt`.
- **Inferred, sanity check by the dossier author.** The rows are consistent with their own concurrency. 512 users at 16.2 tokens per second is 8,294 tokens per second on one GPU. 64 users at 117.0 on 4 GPUs is 1,872 per GPU. Both are within 8% of the per-GPU figure.
- **Verified by run.** GPU price moves U\* less. On the loose row against the same API, U\* runs from 18.2% at $3.99 to 36.1% at $7.91. `EP/run_2026-09-25.txt` section 2.
- **Beyond Module 1.** Module 1 section 4.6 uses one throughput number. This concept makes the latency target an input. The formula is `U* = (GPU_HOURLY + F/(N*730)) / (3600 * R * A)`. R is output tokens per second divided by OSL. A is API dollars per request. F is fixed monthly cost. N is fleet size. Economics report section 3.2.

### 4.2 The API you compare against moves the answer more than any GPU discount, and a cheap open-weight endpoint is already near GPU cost

- **Best evidence, verified.** OpenRouter lists 24 endpoints for gpt-oss-120b. Output prices run from $0.17 to $0.95 per million tokens, a 5.6 times spread. `E/or_endpoints_selected.txt`. Cheapest: AkashML and CoreWeave at $0.03 input and $0.17 output. Highest output: SambaNova and DeepInfra fp8 at $0.95.
- **Verified by run.** On the loose H200 row, U\* is 77.0% against the cheapest endpoint and 20.5% against the $0.60 tier. Against the cheapest endpoint, every tight or 8K-input H200 row never breaks even. `EP/run_2026-09-25.txt` section 1.
- **Verified by run.** A higher API cache hit rate raises U\*. For 8K input and 1K output against Groq pricing with cached input at $0.075: U\* is 36.8% at 0% hits, 44.2% at 50% and 52.6% at 90%. This assumes self-hosting gains nothing from its own cache. `EP/run_2026-09-25.txt` section 3.
- **Inferred.** Self-hosting also gains from its own prefix cache. With an assumed prefill share of 0.5, U\* falls to 28.9% at 90% hits. The benchmark rows do not report the prefill share. The 0.5 is an assumption. Check: measure the share of GPU time spent on prefill at your ISL, OSL and concurrency.
- **Verified.** DeepSeek's own API charges cache-hit input at 2% of cache-miss input for V4.1-Flash. The off-peak prices are $0.003 against $0.15. The peak prices are $0.006 against $0.30. It says "Off-peak rates are half of the peak rates." `E/deepseek_pricing.txt` lines 86 to 119.
- **Verified, engineering post by the engine teams.** The LMSYS Kimi K2 post gives "~$0.21" per million output tokens on 128 H200. It assumes "H200 $2.3/hour". `D/lmsys_2025-07-20-k2.txt`. Conditions: 2,000-token inputs, 100-token outputs, PD disaggregation, posted 2025-07-20 by the Mooncake team.
- **Inferred.** That $2.3 is about half of the lowest H200 on-demand price read on 2026-09-25, Nebius at $4.50. Section 5.1. A published cost per token is only as good as the GPU price behind it. Check: recompute the post's figure at your own GPU price.
- **Conditions.** Endpoints differ in precision and speed. A $0.17 endpoint is not the same product as a fast $0.75 one. Per-endpoint speed was not checked.
- **Beyond Module 1.** Module 1 section 4.6 made the same point for closed models: 50.5% against a cheap role and 10.1% against a deep role. This concept is the open-weight version, with cached input.

### 4.3 The utilisation you can reach is capped by your traffic shape, not by your engineering

- **Best evidence, inferred.** A fleet is sized for peak. Average utilisation cannot exceed the peak target divided by the peak-to-mean ratio. At an 80% peak target, peak-to-mean 2.0 gives 40.0%. `EP/run_2026-09-25.txt` section 6. The 80% comes from Module 1 section 6.1. Module 1 section 6.1 also says the right target depends on how many servers share the queue. `M1/inference-internals-phase-06a-capacity-tenants.md` line 88. So the 80% is an input, not a constant. Check: measure your own peak-to-mean ratio from request logs.
- **Inferred, not measured.** Per-second billing changes this ceiling. Modal bills GPUs by the second, H200 at $0.001261 per second. `E/modal_pricing.txt` lines 25 to 40. A fleet that scales down at night pays for fewer idle hours. It pays with cold starts instead, 84 s for a 70B model with PyTorch in 2024, section 5.4. Check: replay a day of your traffic against an autoscaler with a measured cold start.
- **Verified, from the built Module 1.** DynamoLLM measured an Azure trace: conversation traffic "peak = 1.7x the average" and coding traffic "peak = 2.8x the average". `M1/inference-internals-phase-06a-capacity-tenants.md` lines 131 to 132. At an 80% peak target those give ceilings of 47.1% and 28.6%, `D13/recompute.txt`.
- **Consequence, inferred.** With coding-like traffic, the ceiling of 28.6% is above the 20.5% loose break-even and far below the 77.0% break-even against the cheapest endpoint.
- **Verified.** Beyond Per-Token Pricing measured vLLM on Azure H100 NVL at $6.98 per GPU-hour. Its abstract says "effective cost spans $0.21 to $15.25 per million output tokens". Conditions: Llama 3.1 8B, Qwen3-30B-A3B and Mixtral 8x7B, six configurations, offered load from 1 request per second up to saturation. The span covers all six configurations and that full load range. The $0.21 is a saturation figure, Qwen3-30B-A3B in FP8. At offered loads of 1 to 10 requests per second the paper measures an underutilisation penalty of 2.5 to 24 times. It states a naive estimate "understates true cost by exactly 1/U". `E/arxiv_2606.11690.txt` lines 18 to 21, 46, and 2522 to 2523 in the conclusion: "across all six configurations and the full load range it spans $0.21 to $15.25". Preprint, one independent author.
- **Verified.** The CMU cost-benefit paper assumes "business operation of 8 hours/day and 20 days/month". `E/arxiv_2509.18101.txt` line 357. Preprint. **Inferred** from how the paper uses that figure: its utilisation is 100% of operating hours. Section 7, conflict j.

### 4.4 Fixed costs decide small fleets, and a 24/7 pager is eight people, not a fraction of one

- **Best evidence, verified.** Google's SRE book says "the minimum number of engineers needed for on-call duty from a single-site team is eight". Conditions stated there: primary and secondary always on call, week-long shifts, no more than 25% of time on call. For two sites, "a reasonable minimum size of each team is six". `E/sre_oncall.txt`. Google practice, not a law.
- **Inferred.** Eight people at 25% carry two full-time equivalents of on-call time. The rest of their time is other work. How much of eight salaries to charge to the fleet is a choice, not a fact.
- **Verified, from the built Module 1.** Module 1 section 4.6 uses "a quarter of one engineer at $180,000 a year". `M1/inference-internals-phase-04b-optimizing.md`. That fits a business-hours service. It is not the cost of a 24/7 pager. Section 7, conflict k.
- **Verified by run.** With $20,000 a month of fixed cost against Cerebras pricing at the tight target, 8 GPUs never break even, with U\* at 115%. 32 GPUs break even at 77.4% and 128 GPUs at 68.2%. `EP/run_2026-09-25.txt` section 5. The $20,000 is an input, not a measured figure.
- **Inferred.** A model that needs TP4 at a tight target, with two replicas for redundancy, is 8 GPUs before any traffic. At the Nebius H200 price that is $26,280 a month. Recomputed in `D13/recompute.txt`.
- **Verified.** The CMU paper leaves staffing out. Its Future Work asks to "extend TCO models to include staffing and maintenance". `E/arxiv_2509.18101.txt` lines 656 to 658.

### 4.5 A published throughput number at a loose latency limit is not your capacity, and some counts include input tokens

- **Best evidence, verified.** MLPerf Inference v6.1 limits for gpt-oss-120b: "Server: TTFT/TPOT: 3000 ms/80 ms. Interactive: TTFT/TPOT: 2000 ms/20 ms." `E/mlperf_inference_rules.adoc` line 271. 80 ms per token is 12.5 tokens per second per user.
- **Verified, numbers. Inferred, ratios. Vendor submissions of audited results.** NVIDIA's MLPerf v6.1 table: gpt-oss 120B on 72 GB200 NVL72 gives 911,566 tokens per second offline, 901,058 server and 625,205 interactive. Interactive is 68.6% of offline. `E/nvidia_dlperf_inference.txt` lines 71, 256 and 433.
  - Who ran it: CoreWeave submitted the offline and server results. NVIDIA submitted the interactive result, with TensorRT. So the ratio compares two submitters' systems.
- **Verified, numbers. Inferred, ratios. Vendor submissions.** DeepSeek R1 on GB200 NVL72: 2,091,190 offline and 1,598,510 server on 288 GPUs, 240,274 interactive on 72 GPUs. Per GPU that is 7,261, 5,550 and 3,337. Interactive per GPU is 46.0% of offline. `E/nvidia_dlperf_inference.txt` lines 42, 223 and 416.
  - Who ran it: Azure submitted the offline and server results on 288 GPUs. NVIDIA submitted the interactive result on 72 GPUs. The per-GPU ratio mixes two submitters and two system sizes.
- **Verified from the data.** In `nv_inference_benchmark.json`, `tput_per_gpu` is input plus output tokens. Example: 705.3 plus 708.1 is 1,413.4. At 8K input and 1K output, total is 9.0 times output. The row 16983.2, 15096.1, 1887.0 shows it. `E/nv_selected_rows.txt` line 236.
- **Not checked.** Whether MLPerf "tokens/s" counts output tokens only. Section 9.

### 4.6 GPU rent is rising in late 2026, and a committed cluster can cost more per GPU-hour than on-demand

- **Best evidence, verified.** Lambda charges $6.16 per GPU-hour for a 16-GPU H100 "1-Click Cluster" on a 2-week to 1-year term. The same page lists an on-demand 8x H100 SXM instance at $3.99. `E/lambda_pricing.txt` lines 137 and 179. The committed cluster is 1.54 times the on-demand price.
- **Inferred.** The premium pays for a multi-node interconnect and guaranteed capacity. The price table does not say. Check: read Lambda's 1-Click Cluster product page.
- **Verified.** Nebius lists a second column, "GPU-hour (Effective October 1, 2026)". H100 goes from $3.85 to $4.50, H200 from $4.50 to $5.40, B200 from $7.15 to $8.50. `E/nebius_prices.txt` line 28 and lines 44 to 58. The October H200 price moves U\* on the loose row from 20.5% to 24.7%.
- **Verified.** Together publishes a reserved ladder. Its 91 to 180 day H200 price, $3.99, is 33.4% below its on-demand $5.99. `E/together_pricing.txt`.
- **Verified.** CoreWeave offers "up to 60% discounts" for committed use, with no figure. Nebius offers "up to 35% less". `E/coreweave_pricing.txt` line 1207, `E/nebius_prices.txt` line 18.
- **Verified.** Together also lists "Preemptible Compute": H100 $1.99, H200 $2.99, B200 $4.09 per GPU-hour. That is about half its on-demand price. `E/together_pricing.txt`, the table after "On-demand hourly rates and reserved capacity". **Inferred.** The provider can take a preemptible GPU back. It fits batch work, not a 24/7 latency target. The page does not state the notice period. Not checked.
- **Verified.** There are options between a shared API and your own fleet. Together sells "Dedicated Inference", described as "Single-tenant GPU instances", and "Provisioned Throughput" in fixed capacity units. `E/together_pricing.txt` lines 605 to 650. **Inferred.** These move part of the on-call and engine work to the provider. They keep the utilisation risk with you, because you pay for the capacity whether you use it or not. Check: read the provider's terms for who handles engine upgrades and incidents.

### 4.7 Disaggregation does not raise throughput by itself. It controls tail latency, and it can lose

- **Best evidence, verified.** vLLM v0.30.0 docs: "Disaggregated prefill DOES NOT improve throughput." `VL/docs/features/disagg_prefill.md` line 16. The page gives two real reasons: tune TTFT and ITL separately, and control tail ITL. The page title is marked "(experimental)", line 1.
- **Verified, vendor.** Dynamo v1.5.0: "It is not automatically better." It names small models, short prompts, low concurrency and no fast KV fabric. There, "an aggregated deployment is simpler and often faster". `DY/kubernetes/disaggregated-serving/overview.md` lines 68 to 70. No numbers are attached.
- **Verified.** TaiChi, a Huawei Cloud preprint, simulated Llama-2-70B at TP4 on a 4-node, 8-GPU A100 cluster with the Vidur simulator. Workload: ArXiv summarisation under 4,096 tokens at 12 QPS. At a 16 s TTFT and 60 ms TPOT target, disaggregation met 98% and aggregation 7%. At 5 s and 250 ms, aggregation met 97% and disaggregation 42%. `D/p_2508.01989.txt` Table 2, lines 417 to 475. Simulator, not hardware.
- **Verified, from the built Module 1.** Module 1 section 6.1 cites DistServe's 13B example. "Two prefill GPUs plus one decode GPU served 10" requests per second within target. One GPU served 1.6. That is 2.1 times per GPU. Section 7, conflict a, explains why this does not contradict vLLM.

### 4.8 KV bytes per token depend on the attention type. The GQA formula on an MLA config is 25 to 71 times too large

- **Best evidence, verified arithmetic.** DeepSeek-V3 stores 61 × (512 + 64) × 2 = 70,272 bytes per token. Llama-3.1-70B stores 2 × 80 × 8 × 128 × 2 = 327,680. That is 4.66 times more. Configs in `DP/configs/`. Output `DP/run_output.txt` section A. Recomputed in `D13/recompute.txt`.
- **Verified.** vLLM v0.30.0 uses the MLA rule. `VL/vllm/transformers_utils/model_arch_config_convertor.py` line 93 returns `kv_lora_rank + qk_rope_head_dim` as the head size. `VL/vllm/v1/kv_cache_interface.py` line 659 says "MLA stores a single latent vector per state".
- **Verified, the trap.** DeepSeek-V3's config says `"num_key_value_heads": 128`. It has no `head_dim` field. `DP/configs/deepseek-ai_DeepSeek-V3.json`. So the wrong answer depends on which head size the learner picks. Verified arithmetic, reviewer recompute:
  - `hidden_size / num_attention_heads` = 7168 / 128 = 56. This is the rule in `DP/disagg_sim.py` line 58. It gives 1,748,992 bytes per token, 24.9 times too large.
  - `v_head_dim` = 128. It gives 3,997,696 bytes per token, 56.9 times too large. The disaggregation report used this one.
  - K at `qk_nope_head_dim + qk_rope_head_dim` = 192 and V at 128, the decompressed cache. It gives 4,997,120 bytes per token, 71.1 times too large.
- **Verified.** vLLM uses the MLA head size only when `VLLM_MLA_DISABLE` is off. `VL/vllm/transformers_utils/model_arch_config_convertor.py` lines 92 to 93.
- **Verified arithmetic.** Per token: Qwen3-32B 262,144 bytes. Qwen3-235B-A22B 192,512 bytes. At 128k tokens, Llama-3.1-70B holds 40.00 GiB, and DeepSeek-V3 holds 8.58 GiB.
- **Conditions.** bf16, 2 bytes per value. The Llama config came from the `NousResearch/Meta-Llama-3.1-70B-Instruct` mirror because the official repo returned HTTP 401.
- **Beyond Module 1.** Module 1 section 1.3 owns the GQA formula and Llama-3-8B at 128 KB. The prototype gets 131,072 bytes for Llama-3-8B, which agrees.

### 4.9 KV transfer is negligible only on NVLink or fast RDMA. On a network link it can take as long as prefill

- **Best evidence, verified.** DistServe says KV transmission is "less than 0.1%" of total latency for OPT-175B. Its testbed had 25 Gbps between nodes, `D/p_2401.09670.txt` sections 6.1 and 6.3. It placed prefill and decode stages on the same node, so the transfer used NVLink.
- **Inferred by run.** For Llama-3.1-70B with an 8,192-token prompt, the KV cache is 2.50 GiB. On one 100 Gbps link it takes 215 ms, which is 55% of a modelled 393 ms prefill. On 25 Gbps it takes 859 ms, 218% of prefill. `DP/run_output.txt` section B. Prefill assumes 8 H100 at 40% of 989 TFLOPS. That is an assumption.
- **Inferred by run.** MoE models compute less per token but store as much KV. For Qwen3-235B-A22B with a 2,048-token prompt, transfer on 100 Gbps is 103% of prefill. DeepSeek-V3 with MLA is 22%. `DP/run_output.txt` section B.
- **Inferred by run.** Replaying the Mooncake conversation trace with Llama-3.1-70B KV needs 13.41 GB/s, or 107 Gbps, on average. One 100 Gbps link cannot carry it, and the replayed p50 delay grows to 135.16 s. Two 100 Gbps links give a p99 of 3.92 s. `DP/run_output.txt` section C. FIFO model with no protocol overhead. The trace comes from Kimi, not from this model.
- **Verified, vendor.** Mooncake Transfer Engine reached 87 GB/s on 4 × 200 Gbps and 190 GB/s on 8 × 400 Gbps RoCE. FAST'25 section 5.4. That is 87% and 47.5% of line rate, `D13/recompute.txt`.

### 4.10 The P:D ratio is set by the workload, and adding prefill workers can remove capacity

- **Best evidence, verified.** The LMSYS Kimi K2 deployment used 4 prefill nodes and 12 decode nodes on 128 H200 for 2,000-token inputs and 100-token outputs. It says the ratio is "workload-dependent". `D/lmsys_2025-07-20-k2.txt`. Engineering post with conditions, written by the Mooncake team about its own stack on the SGLang blog. **Vendor**, rank 5.
- **Verified, vendor.** Dynamo v1.5.0 architecture docs: "adding prefill replicas can reduce total serving capacity" when decode KV capacity is the limit. The boundary "should not be encoded as a universal token threshold". `DY/developer-guide/knowledge-base/concepts/system-architecture/disaggregated-serving.md` lines 100 to 124. No measurement attached.
- **Inferred by run, a toy.** On the Mooncake conversation trace, a dense 70B model wants a P:D of 6.19. With 50% prefix hits it wants 3.46. `DP/run_output.txt` section F. It ignores queueing, TTFT targets and expert parallelism. It points the opposite way from Kimi K2's 1:3. Section 7, conflict e.

### 4.11 Loading a cached prefix beats recomputing it only above a break-even bandwidth, and that bandwidth grows with GPU speed

- **Best evidence, verified.** Mooncake FAST'25 section 2.2 gives Equation 2 for LLaMA3-70B with an 8,192-token prefix. The minimum bandwidth is 6 GB/s on 8 A800. It is "19 GB/s for an 8×H800 machine". `D/fast25-qin.txt`.
- **Inferred by run.** Break-even bandwidth is KV bytes per token times prefill tokens per second. On an 8-H100 node at an assumed 40% utilisation, it is 6.8 GB/s for Llama-3.1-70B, 11.2 GB/s for Qwen3-32B and 2.3 GB/s for DeepSeek-V3. `DP/run_output.txt` section D. Halving the assumed utilisation halves each number.

### 4.12 A shared KV pool helps when requests lose locality. When placement keeps locality it adds little, and it can return wrong bytes

- **Best evidence, verified.** A preprint ran two vLLM replicas on one LMCache pool. It says "fixed placement shows little benefit". It also found that one allocator path "omits the dependency on the current CUDA stream", so byte tests failed under an injected delay. `D/p_2609.15021.txt` abstract and section 5.2.
  - Conditions: Qwen3.8-27B NVFP4, 2 RTX PRO 6000 Blackwell GPUs in one host, vLLM 0.28.0, LMCache 0.5.4, synthetic sessions, 768 requests, no confidence intervals. One author at UNSW, posted 2026-09-14, not peer reviewed.
- **Verified.** Same study, Table 3: at 128k tokens, local GPU reuse took 0.484 s and cross-replica reuse took 0.605 s. The pool is slower than the local cache. Without the pool, cross-replica TTFT was 31.715 s.
- **Inferred by run, simulator only.** The model replays the Mooncake conversation trace on 8 instances of 2,000 blocks each. Per-instance LRU gave a 7.6% token hit rate with random routing. A cache-aware router that ignores load gave 5.5%. One shared pool of the same total size gave 26.8%. `DP/run_output.txt` section E. 2,000 blocks of 512 tokens is 312.5 GiB per instance for a 70B model.
- **Verified, vendor, preprint.** LMCache reports 2.3 to 14 times more throughput at the same TTFT, against "the strongest baseline across five evaluated models". Conditions: 8 H100, vLLM v0.10.2 and v0.11.0 baselines, multi-round document QA with 10K-token documents, a 500 GB CPU cache. arXiv 2510.09665 sections 8.1 and 8.2, `D/p_2510.09665.txt` lines 1160 to 1175. Not peer reviewed. The authors sell the product.

### 4.13 Splitting prefill and decode across machines adds failure modes that one machine does not have

- **Best evidence, verified, vendor.** Dynamo v1.5.0: prefill and decode must use the same model, dtype, block size and KV layout. Otherwise "you get transfer errors or silently corrupt output". `DY/kubernetes/disaggregated-serving/overview.md` lines 196 to 201.
- **Verified.** A decode worker that never reads its KV blocks leaves them held on the prefill worker. vLLM's NIXL connector holds them for `kv_lease_duration`, default 30 s, extended by heartbeats every lease divided by 6. `VL/vllm/distributed/kv_transfer/kv_connector/v1/nixl/base_scheduler.py` lines 83 and 87.
- **Verified.** vLLM's `kv_load_failure_policy` defaults to `"fail"`. The other value is `"recompute"`. `VL/vllm/config/kv_transfer.py` line 103. So a failed KV load fails the request unless you change it.
- **Verified.** SGLang's bootstrap and waiting timeouts both default to 300 s. Heartbeat interval is 5.0 s with 2 allowed failures. `SG/python/sglang/srt/environ.py` lines 689 to 693. The docs warn that a longer bootstrap timeout frees prefill memory more slowly when a decode node drops.
- **Verified.** NIXL stages metadata in `/dev/shm`. The pod default of 64 MB is too small, and NIXL fails to start. Dynamo docs use 16Gi. A broken transfer path can show as "disaggregated throughput falling below your aggregated baseline". `DY/kubernetes/disaggregated-serving/overview.md` lines 217 and 248.
- **Verified, docs and source.** `VLLM_NIXL_SIDE_CHANNEL_HOST` defaults to `localhost` and must be set when prefill and decode are on different machines. `VL/docs/features/nixl_connector_usage.md` lines 113 to 124. The source default is also `"localhost"`, `VL/vllm/envs.py` lines 226 and 1651 to 1652.
- **Verified.** "NIXL is supported on a Linux environment only." `NX/README.md` line 32. So no PD lab runs on the learner's Mac.
- **Inferred from the code, not run.** All of this is read at tags. Runtime behaviour is not checked.

### 4.14 A cache-aware router needs per-replica cache state, token load and the tokenizer. A normal load balancer has none of them

- **Best evidence, verified.** The Gateway API Inference Extension model-server protocol requires `TotalQueuedRequests`, `TotalRunningRequests` and `KVCacheUtilization`. The vLLM names are `vllm:num_requests_waiting`, `vllm:num_requests_running` and `vllm:kv_cache_usage_perc`. LoRA needs `vllm:lora_requests_info`. `R/gie/003-model-server-protocol.md` lines 28 to 57, GIE v1.6.2.
- **Verified.** The router must count in-flight prompt tokens, not requests. llm-d has a `token-load-scorer`. Dynamo's cost uses `active_prefill_blocks`. `R/dynamo/routing-concepts.md` lines 28 to 33.
- **Verified.** A precise router must produce the same tokens as the engine. AIBrix KV sync "has a strict dependency on remote tokenizer". `R/aibrix/kv-event-sync.rst` line 44.
- **Verified.** Approximate routers avoid the tokenizer by hashing text. SGLang's gateway tree stores "raw text characters". vLLM production-stack hashes 128-character chunks, `chunk_size: int = 128`. llm-d approximate mode uses "character-to-token ratios". `R/sglang/gw/cache_aware.rs` lines 22 to 23, `R/pstack/hashtrie.py` line 37.
- **Summary list of what the router needs.** Queue depth and KV usage per replica. Cached prefixes per replica and in-flight prompt tokens. Block size and GPU block count. Loaded LoRA adapters. The tokenizer and chat template.

### 4.15 The large published routing wins are against round robin on workloads built to reward affinity

- **Best evidence, verified, vendor.** The llm-d project measured its own router. llm-d reports TTFT p90 of 154.1 s against 0.9 s at rate 60, against "a stock Kubernetes Service that round-robins requests". Workload: a 6,000-token shared prompt, a 1,200-token question, a 1,000-token output. Qwen3-32B on vLLM, 8 servers of 2 H100 at TP2. `R/llmd-main/guides_optimized-baseline_benchmark-results_vllm-qwen3-32b-h100.md`, llm-d v0.9.0.
- **Verified, vendor.** The same table is not better at every rate. At rate 3, llm-d gave 1,511 output tokens per second against 1,889 for round robin. At rate 10 it gave 4,597 against 4,944. At rate 20, TTFT p90 was 4.2 s against 2.4 s. Same file, lines 42 to 45.
- **Verified, vendor.** Dynamo's A/B on the Mooncake tool-agent trace: TTFT p99 332,974 ms against 17,871 ms, 18.6 times, against "standard round-robin routing". Round robin's mean TTFT was 64 s, so that arm was past saturation. The doc lists "Short prompts" and low request rate as factors that reduce the benefit. `R/dynamo/kv-router-a-b-testing.md` lines 7 and 637 to 665.
- **Verified, vendor.** With gpt-oss-120b on 16 H100, llm-d gains only 8.2% output throughput, and requests per second fall 1.1%. Latency still improves a lot. TTFT p50 falls 84.1%, TTFT p90 falls 75.2% from 10.110 s to 2.508 s, and ITL p50 falls 37.1%. `R/llmd-main/guides_optimized-baseline_benchmark-results_vllm-gpt-oss-120b-h100.md` lines 3 to 30.
  - Conditions: 16 servers at TP1, and a changed workload with 500-token questions and 500-token outputs. So this run is not the same workload as the Qwen3-32B run above.
- **Verified, vendor.** When llm-d compared precise and approximate routing, both with load scorers, output throughput differed by 25.7%, not by 2 times. TTFT p90 was 0.542 s against 31.083 s. `RW/llmd_kvcache_wins.txt` lines 131 to 143.
- **Verified, vendor, no conditions.** SGLang's v0.4 blog reports 1.92 times throughput on "multiple long prefix groups, and each group is perfectly balanced". It names no model and no hardware. `RW/sglang_v04_blog.txt` lines 42 to 47.

### 4.16 Pure prefix affinity loses on a hot prefix or on low reuse, so routers add a load signal. A load gate can also fail when the cache is full

- **Best evidence, verified, preprint.** CacheRoute measured Qwen3-32B bf16 on 60 H100 at TP2. On a semi-synthetic workload, affinity raised the KV hit rate "only from 1.1% to 11.8%". Capacity fell to 0.50 and 0.67 times a flat load balancer at 3.5 s and 5 s SLOs. `RW/arxiv_2608.19677.txt` lines 305, 643 and 667. One author.
  - CacheRoute is not pure affinity. It places keys by expected load. So this loss applies to a load-aware affinity policy too.
  - The same paper also reports a win. On Llama-3.3-70B fp8 on 60 H100, CacheRoute sustains 2.3 times the strongest of five baselines at a 3.5 s p99 SLO. Hit rate rises from 64.1% to 93.2%. Same file, line 77. The paper's rule: gate any deployment with a shadow replay of your own traffic.
  - The workloads are semi-synthetic. The paper derives them from de-identified serving telemetry, line 98.
- **Verified, preprint.** DualMap reports that pure cache affinity on the Mooncake tool-agent trace has low SLO attainment "Even under low QPS". Conditions: Qwen2.5-7B and 14B on 8 Ascend 910B NPUs. `RW/arxiv_2602.06502.txt` line 194. NPU hardware, not GPU.
- **Verified.** SGLang's gateway leaves affinity when load is imbalanced, using `abs_threshold` and `rel_threshold`. `R/sglang/gw/cache_aware.rs` lines 13 to 15. llm-d says the prefix scorer with a max picker "causes hot-spotting" and adds an affinity filter. `R/llmd/prefixcacheaffinity_README.md`. AIBrix restricts candidates when running requests differ by more than 8. `R/aibrix/prefix_cache.go` lines 46 and 403 to 425.
- **Verified, the exception.** vLLM production-stack `PrefixAwareRouter` reads no load. Its docstring says "we assume that there is no eviction of prefix cache". The word "evict" appears 0 times in `hashtrie.py`. `R/pstack/routing_logic.py` line 436.
- **Inferred by run.** In the routing simulator, one prefix carries 40% of traffic. Pure affinity puts 42.1% of requests on one node, with p99 of 38.09 s. The spill-gated policy gives 0.55 s. `RP/run_seed1.txt` lines 27 to 28.
- **Inferred by run, simulator only.** The run has 64 prefixes and exactly 64 cache slots across 8 nodes. The load is a warm-up ramp: 60 s at 20 requests per second, then 240 s at 60. `RP/run_seed1.txt` section D3. The spill gate had p99 under 5 s in 0 of 8 seeds. With 16 slots per node it passed in 8 of 8. Pure affinity reversed: 7 of 8, then 2 of 8. `RP/run_seed1.txt` section G. Mechanism, inferred: with no spare cache, every spill evicts another prefix. No vendor doc says this. Check: run llm-d's affinity filter on a fleet whose KV capacity is close to the prefix working set.

### 4.17 The router's view of the cache is always a little wrong: lag, lost events, restarts and router replicas that do not share state

- **Best evidence, verified, vendor.** Dynamo docs: KV events use ZMQ PUB/SUB, and "Because PUB/SUB is lossy", consumers need a way to detect missed messages. `R/dynamo/kv-event-replay-comparison.md` line 10.
- **Verified.** "If a router replica restarts, it starts with no active-block knowledge." "If a worker is down, its blocks cannot be recovered until the worker returns." `R/dynamo/router-operations.md` lines 35 and 43. Active-block sync across router replicas needs the `--router-replica-sync` flag, lines 45 to 56.
- **Verified.** Which state the replicas do not share differs by router. In Dynamo, every router replica reads the same KV events, so prefix state needs no router-to-router sync. Only the active load view is local. `R/dynamo/router-operations.md` line 25. In llm-d, the precise index is "HA-safe" and the in-flight token count is local. In the SGLang gateway, the whole radix tree is local to each replica.
- **Verified.** llm-d runs one router replica by default, because in-flight token accounting "is local to each EPP process". `R/llmd-main/guides_precise-prefix-cache-routing.md` line 50.
- **Verified, vendor, no measurement shown.** SGLang docs say unsynchronised gateway replicas cause an "Expected cache hit rate reduction: 10-20%". `R/sglang/sgl_model_gateway.mdx` lines 2227 to 2230.
- **Verified.** In a burst of prompt-sharing requests, "every replica's prefix cache is still cold", so a cache-state scorer scores them all zero. `R/llmd/burstprefix_README.md`. llm-d adds a 100 ms hold window, which adds latency.
- **Inferred by run, simulator only.** In the simulator, an event lag of 1 s dropped the hit rate from 97.1% to 79.9%. A lag of 5 s dropped it to 38.0%. Two approximate router replicas with strict alternation dropped it from 76.8% to 49.8%. `RP/run_seed1.txt` lines 41 to 45 and section E. Worst case: no session stickiness at the outer load balancer. No source reports a measured event lag.

---

## 5. Measured and published numbers, with conditions

### 5.1 GPU rental prices, dollars per GPU-hour, read 2026-09-25

Per-GPU figures for 8-GPU instances are the instance price divided by 8. The dossier author recomputed each division.

| Provider | GPU | On-demand | Reserved or committed | Source |
|---|---|---|---|---|
| AWS us-east-1 | H100, p5.48xlarge | 55.04 / 8 = 6.88 | Capacity Block 5.191 | `E/aws_ec2_ondemand_useast1.dec.json`, `E/aws_capacityblocks.txt` line 302 |
| AWS us-east-1 | H200, p5en.48xlarge | 63.296 / 8 = 7.91 | Capacity Block p5e 5.97 | same, line 383 |
| AWS us-east-1 | B200, p6-b200.48xlarge | 113.9328 / 8 = 14.24 | Capacity Block 12.355 | same, line 257 |
| CoreWeave | H100 / H200 / B200, 8x HGX | 6.16 / 6.31 / 8.60 | "up to 60%" off, no figure | `E/coreweave_pricing.txt` |
| Nebius | H100 / H200 / B200 | 3.85 / 4.50 / 7.15 | from 2026-10-01: 4.50 / 5.40 / 8.50. "up to 35% less" | `E/nebius_prices.txt` |
| Together | H100 / H200 / B200 | 3.99 / 5.99 / 8.19 | 91 to 180 days: 3.19 / 3.99 / 6.79 | `E/together_pricing.txt` |
| RunPod | H100 SXM / H200 / B200 | Secure 3.49 / 4.59 / 6.79 | "Contact sales" | `E/runpod_pricing.html` |
| Lambda | H100 SXM / B200, 8x | 3.99 / 6.69 | 16-GPU cluster, 2 weeks to 1 year: 6.16 / 9.86 | `E/lambda_pricing.txt` |
| Modal | H100 / H200 / B200 | 3.95 / 4.54 / 6.25, from per-second prices | none | `E/modal_pricing.txt` |

- **Verified.** Lambda's B200 cluster price falls with size: $9.86 at 16 GPUs, $9.36 at 64 and $8.87 at 256 or more. `E/lambda_pricing.txt` lines 110 to 120.
- **Not checked.** Negotiated reserved prices. All four vendors say "contact sales".

### 5.2 Throughput rows used for break-even

All gpt-oss-120b, aggregated serving. Source `E/nv_selected_rows.txt`. **Vendor** data.

| GPU, engine, precision, date | ISL/OSL | TP | Concurrency | Output tok/s per GPU | p50 tok/s per user | Speculative decoding |
|---|---|---|---|---|---|---|
| H200, vLLM, FP4, 2026-03-27 | 1K/1K | 1 | 512 | 8,112.3 | 16.2 | off |
| H200, vLLM, FP4 | 1K/1K | 4 | 64 | 1,746.6 | 117.0 | off |
| H200, vLLM, FP4 | 8K/1K | 1 | 64 | 1,887.0 | 30.4 | off |
| H200, vLLM, FP4 | 8K/1K | 4 | 32 | 885.0 | 118.0 | off |
| B200, TensorRT-LLM, FP4, 2026-02-05 | 1K/1K | 1 | 1,024 | 30,404.8 | 30.9 | EAGLE |
| B200, TensorRT-LLM, FP4 | 1K/1K | 2 | 64 | 7,070.0 | 245.6 | EAGLE |

- **Not checked.** The dataset InferenceX used and the EAGLE acceptance rate. The B200 rows depend on both.

### 5.3 Break-even sweep

Verified by run, `EP/run_2026-09-25.txt`. Recomputed, `D13/recompute.txt`.

| Row | GPU price | API | U\* |
|---|---|---|---|
| H200 1K/1K loose | $4.50 | $0.15 / $0.60 | 20.5% |
| H200 1K/1K tight | $4.50 | $0.15 / $0.60 | 95.4% |
| H200 1K/1K loose | $4.50 | $0.03 / $0.17 | 77.0% |
| H200 1K/1K tight | $4.50 | $0.03 / $0.17 | never, 358% |
| H200 8K/1K loose | $4.50 | $0.15 / $0.60 | 36.8% |
| B200 1K/1K loose | $6.79 | $0.15 / $0.60 | 8.3% |
| B200 1K/1K tight | $6.79 | $0.15 / $0.60 | 35.6% |
| B200 1K/1K tight | $6.79 | $0.03 / $0.17 | never, 133% |
| H200 1K/1K tight, F = $20,000, N = 8 / 32 / 128 | $4.50 | $0.35 / $0.75 | never 115% / 77.4% / 68.2% |

Utilisation ceiling at an 80% peak target: 53.3% at peak-to-mean 1.5, 47.1% at 1.7, 40.0% at 2.0, 28.6% at 2.8 and 26.7% at 3.0.

### 5.4 Costs besides GPUs

| Cost | Number and conditions | Label |
|---|---|---|
| On-call | 8 people for a single-site 24/7 rotation. 6 per site for two sites. 25% on-call cap | verified, `E/sre_oncall.txt` |
| Minimum fleet | 8 H200 at $4.50 for 730 hours is $26,280 a month | inferred arithmetic |
| Cold start | LLaMA-2-70B takes 84 s to load into 8 GPUs with PyTorch. ServerlessLLM starts a model in 0.8 s on average against 12.1 s for Ray Serve | verified, `E/serverlessllm_2401.14351.txt` lines 298 to 308 and 1608 to 1610. 2024 hardware |
| Egress | GCP Premium Tier: $0.12 per GiB for the first TiB | verified, `E/gcp_network_pricing.txt` line 25 |
| Egress per token | $0.0257 per million output tokens at a constructed 230-byte SSE chunk per token. $0.00045 at 4 bytes per token | inferred. The chunk size was constructed, not captured |
| Storage | RunPod "starting at $0.05/GB/mo" | verified, `E/runpod_pricing.txt` line 505 |
| Model updates, evals, safety filtering | No primary source with a figure | not checked |

### 5.5 Disaggregation and KV pool numbers

| Number | Who ran it | Conditions | Label |
|---|---|---|---|
| Up to 7.4 times more requests or 12.6 times tighter SLO | DistServe, OSDI 2024 | OPT-13B, 66B, 175B. 4 nodes of 8 A100-80GB. 25 Gbps across nodes. Against vLLM and DeepSpeed-MII | verified, `D/p_2401.09670.txt` lines 32 to 33 |
| 59% to 498% more effective request capacity | Mooncake, FAST'25 | Dummy LLaMA3-70B, 16 nodes of 8 A800, 4 × 200 Gbps RDMA per node. Against vLLM v0.5.1. TTFT limit 30 s | verified, `D/fast25-qin.txt` line 44 |
| Kimi handles 115% and 107% more requests | Moonshot AI, own statistics | A800 and H800 clusters. Not reproducible | verified that the paper says it, line 48. **Vendor** production claim |
| +42% effective caching capacity against vLLM with prefix caching | Mooncake | tool-agent trace, 200 ms TBT | verified, FAST'25 5.2, `D/fast25-qin.txt` lines 1156 to 1158. The paper says "effective caching capacity", not request capacity |
| 2.3 to 14 times throughput at the same TTFT | LMCache authors | 8 H100, 10K-token document QA, 500 GB CPU cache | verified, vendor, preprint |
| Mean TTFT 1.53 to 1.84 times lower than vLLM native PD | LMCache authors | NVLink between P and D, random 8K in, 200 out, four models | verified, vendor, preprint, `D/p_2510.09665.txt` line 1388 |
| DeepSeek-V3: 52.3k input and 22.3k output tokens per second per node | SGLang team | 12 nodes of 8 H100, InfiniBand, 2,000-token inputs | verified, vendor engineering post, LMSYS 2025-05-05 |
| "7x higher throughput per GPU" | Dynamo README, citing InferenceX | No conditions given | not checked. Leads only |

### 5.6 Routing numbers

| Who ran it | Model and hardware | Baseline | Result | Label |
|---|---|---|---|---|
| llm-d | Qwen3-32B, vLLM, 8 × 2 H100 | k8s round robin | peak output 7,049 to 14,941 tok/s. Source prints +111.9% | verified, vendor |
| llm-d | Qwen3-32B, SGLang, same | k8s round robin | output 5,113 to 9,241. ITL p50 +27.1%. Round robin had 199 failed requests | verified, vendor |
| llm-d | gpt-oss-120b, vLLM, 16 H100, 500-token questions and outputs | k8s round robin | output +8.2%, requests per second −1.1%, TTFT p90 −75.2%, ITL p50 −37.1% | verified, vendor |
| llm-d, precise mode | Qwen3-32B, vLLM | k8s round robin | peak output 6,986 to 14,892. ITL p50 +22.4% | verified, vendor |
| llm-d blog | "Qwen/Qwen-32B", 8 × 2 H100 | approximate plus load | TTFT p90 0.542 s against 31.083 s. Output 8,730 against 6,944 | verified, vendor |
| NVIDIA Dynamo | Qwen3-32B, vLLM, 8 × 1 GPU | round robin | TTFT avg 24.6 times, p99 18.6 times, E2E p99 4.7 times lower | verified, vendor |
| KubeAI | Llama 3.1 8B, 8 L4 | k8s Service | TTFT −95%, throughput +127% at 1,200 concurrent threads | verified, vendor |

### 5.7 Arithmetic recomputed

Script `D13/recompute.py`, output `D13/recompute.txt`. Every U\* in 5.3 and every per-GPU price in 5.1 reproduced. Every KV size in 4.8, transfer time in 4.9 and routing ratio in 5.6 also reproduced. Differences found:

1. **llm-d +111.9%.** 14,941 / 7,049 is +112.0%. The source prints +111.9%. Probably rounding of unrounded values. Teach "2.1 times".
2. **Nebius October U\*.** 0.2054 × 5.40 / 4.50 is 0.2465. The prototype prints 24.7%. Both round from 24.65%. No change.
3. **CoreWeave H100.** 49.24 / 8 is 6.155. The economics report rounds to 6.16. No change.
4. **Disaggregation prototype run time.** The report says 2.06 s. `DP/run_time.txt` says `real 2.08`. Use 2.08 s.
5. **llm-d blog cache share.** 150 × 6,000 prefix tokens over 8 × 307,328 KV tokens is 36.6%, not the blog's 73%. Adding 750 questions of 1,200 tokens gives 73.2%. The blog credits 73% to "caching the shared prefixes". Routing report 2.3. Confirmed.
6. **llm-d "Requests/sec (@ rate 60)" row.** 56.14 requests per second with 1,000-token outputs would be 56,140 tokens per second. The table reports 7k to 15k. The row cannot be completed requests. Do not teach it.
7. **NVIDIA "$0.02 per million tokens" on B200.** The B200 loose row at $6.79 and U = 1 gives $0.062 per million output tokens. The gap is not explained. Do not cite the $0.02.

---

## 6. Lab designs

**Hardware honesty.** The learner has an Apple Silicon Mac with no NVIDIA GPU, no Docker and no API keys. NIXL is Linux only. LMCache needs Linux and an NVIDIA GPU. vLLM's KV connectors need CUDA, ROCm or XPU. So every cluster lab is a simulation on the Mac or a paid, read-only design.

### 6.1 Built and run on 2026-09-25

| Lab | Script | Where it runs | Cost | Run time | Download | Self-test | Proves |
|---|---|---|---|---|---|---|---|
| Break-even with latency target, API tier, cache hit, fixed cost, ceiling, egress | `EP/breakeven.py` | Mac, stdlib | $0 | 0.04 s, `EP/time.txt` | none | hand-worked U\* = 4.00 / 5.04 = 0.7937, and 0.9107 at 50% cache | 4.1 to 4.4 |
| KV bytes, transfer time, trace replay, reuse bandwidth, pool hit rate, toy P:D | `DP/disagg_sim.py` | Mac, stdlib | $0 | 2.08 s, `DP/run_time.txt` | 8.3 MB on disk. Traces from the 49 MB Mooncake tarball. Configs about 5 KB each | 6 checks: Llama-3.1-8B 131,072 B, OPT-66B 1.125 GiB, 70B at 128k 40 GiB, DeepSeek-V3 70,272 B, FIFO, LRU prefix rule | 4.8 to 4.12 |
| Router simulator: 4 policies, 3 router views, lag, node loss, replicas, seed spread | `RP/routersim.py` | Mac, stdlib | $0 | 10.58 s | none | 4 hand-worked cases, `RP/selftest_output.txt` | 4.15 to 4.17 |

Where each simulator stops being true:

- `breakeven.py` assumes cost scales as 1 / U. With autoscaling, the fleet shrinks in steps of one replica, with cold-start lag. The true curve lies between the two.
- `disagg_sim.py` models prefill from FLOPs at an assumed 40% utilisation. Transfer does not overlap prefill. Real engines overlap layer by layer.
- `routersim.py` serves one request at a time per node, caches whole prefixes, and uses a constant decode cost. Real engines batch. It shows the direction of an effect, not a real cluster's numbers.

### 6.2 Designed, not built

| Lab | Where it runs | Cost | What it prints | Break-it | Proves |
|---|---|---|---|---|---|
| E1. Find your break-even | Mac | $0 | U\*, or "never" above 100% | Swap the tight row for the loose row. U\* falls from 95% to 20%. Ask which row the vendor quoted | 4.1 |
| E2. The ceiling | Mac | $0 | Average utilisation for a synthetic day at a peak-to-mean ratio | Move 30% of traffic to an overnight batch queue. Self-test: a flat day gives ceiling = peak target | 4.3 |
| E3. The fixed-cost floor | Mac | $0 | Smallest fleet where U\* drops below the E2 ceiling | Change to business hours only, 0.25 FTE, as in Module 1 4.6 | 4.4 |
| KV bytes from config.json | Mac | $0, 5 KB configs | Bytes per token for four models | Use `num_key_value_heads` for DeepSeek-V3. The multiple is 24.9, 56.9 or 71.1 times, by the head size chosen. The prototype's own rule gives 24.9 | 4.8 |
| Size the link | Mac | $0 | Mean and peak P to D bandwidth, p50 and p99 delay on 1 to 4 links | Compress arrival times by 2 with `time_scale` | 4.9 |
| Shared pool against locality | Mac | $0 | Hit rate for random, aware and global | Make the aware router ignore load at 2,000 blocks. It falls below random | 4.12 |
| Read the SGLang defaults from source | Mac, network read of three files at `v0.5.20` | $0 | The three default sets side by side | Assert the three tuples | 4.16, conflict g |
| Replay-window arithmetic | Mac | $0 | Seconds of events a 10,000-batch buffer covers | The step rate is an assumption the learner supplies. No source gives it | 4.17 |
| Read-only: trace the NIXL lease | anywhere | $0 | What happens to prefill KV blocks when decode never reads them. Answer: the 30 s lease | none | 4.13 |
| Real PD with vLLM NixlConnector, one node | Linux, 2 NVIDIA GPUs. Not the Mac | Inferred: 2 × RunPod Secure H100 SXM at $3.49 is $6.98 an hour, prices of 2026-09-25. At an assumed 3 hours that is $20.94. The run time and the model download size were not measured. Whether RunPod gives an NVLink pair was not checked | TTFT and ITL, aggregated against disaggregated | set the side-channel host wrong, or mismatch block size | 4.7, 4.13. **Optional, UNVERIFIED** |
| Real PD across nodes with RDMA | Linux cluster. Not the Mac | Inferred: the smallest public committed cluster found is Lambda's 16 H100 for 2 weeks. 16 × $6.16 × 336 h = $33,116.16, plus sales tax, `E/lambda_pricing.txt`. Inferred, cheaper and not checked: 2 AWS p5.48xlarge on demand at $55.04 each is $110.08 an hour, $440.32 for 4 hours. The saved JSON lists "Network Performance": "3200 Gigabit". Whether NIXL can use that network, and whether on-demand p5 capacity exists, were not checked | same, across the network | none | **Read-only.** The Lambda cost is too high for a lab. The AWS option needs a check before it becomes a lab |
| E4. SSE bytes per token | Linux GPU for the vLLM number | One H100 hour, $3.49 at RunPod Secure or $3.85 at Nebius | Bytes on the wire per streamed token | none | 5.4 egress. **Optional, UNVERIFIED** |

### 6.3 The module lab, proposed

A self-host decision script that answers both halves of the module question in one run. Proposal, not built:

1. The learner enters one throughput row at their latency target and one GPU price. They add one named API price with its cached-input price, and a cache hit rate. They add a peak-to-mean ratio and a staffing model.
2. It prints U\*, the utilisation ceiling, and the smallest fleet at which U\* falls below the ceiling. It reuses `breakeven.py`.
3. For that fleet it prints KV bytes per request and the P to D link needed at the learner's request rate. It says whether one 100 Gbps link is enough. It reuses `disagg_sim.py` sections A to C.
4. It replays the Mooncake tool-agent trace through a router simulator with the learner's replica count and cache size. It prints the hit rate for round robin, pure affinity and the spill gate. This needs new code. `routersim.py` has no trace input. It draws 64 synthetic Zipf prefixes, `RP/routersim.py` lines 54 to 56 and 315. `DP/disagg_sim.py` section E does read the trace but has no spill gate.
5. It prints the "what you take on" list: the on-call headcount, the minimum fleet, the transfer link, and the router state.
6. Self-test: the three existing self-tests, plus one hand-worked fleet.
7. Break-its: compare against the cheapest endpoint, set peak-to-mean to 2.8, set cache slots to the prefix count.

Inferred: offline, no key, about 13 s from the sum of the three measured run times, 0.04 s, 2.08 s and 10.58 s. Not measured. The reviewer re-ran the three self-tests on 2026-09-25 on the same Mac with system Python 3.9.6. All three passed, in 0.06 s, 0.03 s and 0.03 s wall time.

---

## 7. Conflicts resolved

| Conflict | Sources | Evidence used | Resolution |
|---|---|---|---|
| a. Does disaggregation raise throughput? | vLLM docs "DOES NOT improve throughput", against DistServe "7.4× more requests" and Module 1 6.1's 2.1 times per GPU | `VL/docs/features/disagg_prefill.md` line 16. `D/p_2401.09670.txt` lines 32 to 33. TaiChi Table 2 | They measure different things. DistServe counts goodput, the rate that meets TTFT and TPOT targets, per GPU. vLLM speaks of raw throughput. TaiChi shows the sign depends on the ratio of the TTFT target to the TPOT target. Teach: disaggregation raises goodput under a strict TPOT target and can lower it under a strict TTFT target |
| b. Mooncake's own numbers | FAST'25: "59%∼498%" and "115% and 107%". arXiv: "525%" and "75% more requests" | `D/fast25-qin.txt` lines 44 and 48. `D/p_2407.00079.txt` lines 23 to 25 | Not reconciled. The texts likely describe different experiments or dates. Nothing on the fetched pages explains it. Cite the peer-reviewed FAST'25 numbers with their conditions |
| c. LMCache's "62.5-KB page" for Llama-3.1-8B | LMCache section 3.1.1 against the prototype's 64 KiB | `D/p_2510.09665.txt` line 388. `D13/recompute.txt` | Resolved, inferred. 16 tokens × 2 × 8 × 128 × 2 bytes is 65,536 bytes. That is 0.0625 MiB, which a writer can print as "62.5 KB". The paper mixes a binary MiB with a decimal "K". Check: read the vLLM v0.10.2 page-size code |
| d. DistServe's "1.13GB" and "90Gbps" | DistServe section 3.3 | `DP/run_output.txt` section A | 512 tokens of OPT-66B is 1.125 GiB, 1.208 GB. At 10 requests per second that is 96.6 Gbps. The paper uses GiB for size and 10^9 for the rate in one sentence |
| e. The P:D ratio | Prototype 6.19 against Kimi K2's 4 P to 12 D | `DP/run_output.txt` section F. LMSYS 2025-07-20 | Not settled. The deployments differ in model, a MoE with 32B active against a dense 70B, input length, 2,000 against 12,035 tokens, and a decode batch of 480 sized by the KV pool. No public sizing method covers both. Teach "workload-dependent" and the three variables |
| f. Does cache-aware routing raise the hit rate? | Disaggregation prototype: aware 5.5% against random 7.6%. Routing prototype: prefix 97.4% against round robin 12.5% | `DP/run_output.txt` section E. `RP/run_seed1.txt` line 15 | Both are true under their conditions. The mechanism behind the 5.5% is now measured, coherence pass 2026-09-25: every one of the 12,031 conversation-trace requests starts with the same first 512-token block. So the aware router, which matches the longest prefix and ignores load, sends 100% of requests to the first replica that cached that block. The fleet then uses one cache of eight, and 5.5% falls below random placement's 7.6% at 2,000 blocks per replica. At 8,000 and 32,000 blocks aware still sends 100% to one replica. Its 18.1% and 33.9% come from that one replica's large cache, not from placement. A load gate breaks the chain: rel 1.5 over a 60 s window gives 25.6% with a busiest-replica share of 13.1%, and a shared pool of the same total size gives 26.8%, 1.2 points more. Verified by run, `serving-cluster/code/runs/serving-cluster_p03_pool_vs_locality.txt`: "first 512-token block is the most common one: 100.0%" and `aware_max` 100.0% at every size. On the tool-agent trace 46.3% of requests share the most common first block, and aware puts 53.6% to 53.7% on one replica. The routing model's cache holds every prefix. Teach two conditions together: affinity pays only with a load gate, and the gate pays only when cache headroom exceeds the working set. The second matches 4.16's scenario G. Reviewer note: 8,000 blocks is 1,250 GiB per instance for a 70B model, `DP/run_output.txt` section E. That only fits with a CPU or SSD tier, not in GPU memory |
| g. SGLang `cache_aware` defaults | Docs and CLI against Python args against the Rust struct | `R/sglang/gw/main.rs` lines 154 to 171: 0.3, 64, 1.5, 120 s, 67,108,864. `R/sglang/gw/router_args.py` lines 59 to 63: 0.3, 64, 1.5, 60 s, 2^26. `R/sglang/gw/mod.rs` lines 109 to 113: 0.5, 32, 1.1, 30 s, 10,000 | The effective default depends on the entry point. The CLI and docs agree. Python differs on the eviction interval. The Rust struct applies only when code builds the config without the CLI. Inferred from the code, not run. New finding: the CLI policy list at `main.rs` line 150 has `prefix_hash` and `manual`. The docs policy table has `bucket` and no `prefix_hash`. Not traced |
| h. Hit-rate loss from unsynchronised router replicas | SGLang docs "10-20%" against the simulator 76.8% to 49.8% | `R/sglang/sgl_model_gateway.mdx` lines 2227 to 2230. `RP/run_seed1.txt` section E | Not settled. The docs give no measurement. The simulator uses strict alternation with no outer stickiness, a worst case. No source measures it on hardware |
| i. Precise against approximate routing | llm-d blog: precise 57 times better TTFT p90. llm-d guides: both reach about 14.9k tokens per second | `RW/llmd_kvcache_wins.txt`. Two guide reports at `v0.9.0` | Not settled. Different stacks and dates, 2025-09 against 2026. The approximate producer changed since. No same-date A/B found |
| j. Break-even in months or cost up to 36 times higher | CMU arXiv 2509.18101 against arXiv 2606.11690 | `E/arxiv_2509.18101.txt`: "8 hours/day and 20 days/month". `E/arxiv_2606.11690.txt` line 46: "exactly 1/U" | They disagree on method, not data. The CMU paper fixes utilisation at 100% of operating hours. The 2026 paper makes utilisation the main variable. Teach the 2026 method |
| k. The staffing line | Module 1 4.6: 0.25 FTE. SRE book: 8 engineers for 24/7 | `M1/inference-internals-phase-04b-optimizing.md`. `E/sre_oncall.txt` | Both are inputs for different services. 0.25 FTE fits business hours. A 24/7 pager needs 8 people carrying 2 FTE of on-call time. Teach both and make the learner choose |
| l. Disaggregation report C2 headline | "The KV cache of one long prompt can take longer to move than to compute" | `DP/run_output.txt` section B | Narrowed. For Llama-3.1-70B on 100 Gbps, transfer is 27% to 58% of prefill, not longer. It is longer on 25 Gbps, 106% to 231%, and for Qwen3-235B-A22B at 2,048 tokens on 100 Gbps, 103%. 4.9 states the narrower claim |

---

## 8. Gap list, ranked by how much the module question needs it

| Rank | Gap | Why the module question needs it | What was done |
|---|---|---|---|
| 1 | Independent throughput at a production latency target | U\* moves from 20.5% to 95.4% with the row. Every row is vendor data from one JSON file. InferenceX datasets and methods were not read | Not checked. Module 1 E5 measures one node. No cluster run is affordable |
| 2 | The cost of what you take on: salaries, model updates, eval and safety work | "What do you take on" has headcounts and no dollar figures. No primary source was found | Not checked. The learner supplies a salary |
| 3 | Self-host prefix cache benefit, the prefill share of GPU time | Decides U\* whenever the API has a cache discount. The 0.5 is an assumption | Not checked. Needs a run on a GPU |
| 4 | Partial-load cost with autoscaling and cold start on 2026 hardware | The 1 / U model is an upper bound. ServerlessLLM numbers are from 2024 | Not measured |
| 5 | Any runtime check of PD disaggregation | "What breaks" is read from source at tags. Nothing ran | Not run. Linux and 2 GPUs needed, $6.98 an hour inferred |
| 6 | A P:D sizing method that covers dense and MoE models | The brief asks what breaks. A wrong ratio removes capacity | Not checked. Dynamo AIConfigurator not run |
| 7 | Whether vLLM v0.30.0 NIXL still sends page by page | LMCache's criticism used v0.10.2 and v0.11.0 | Not read in source |
| 8 | Measured KV-event lag and router replica loss on hardware | 4.17 rests on docs and a simulator | Not measured. No source reports it |
| 9 | Spill-gate thrash on a real batching engine | 4.16's scenario G is simulator only | Not run |
| 10 | Negotiated reserved prices | Reserved prices move U\* by several points | Not public |
| 11 | MLPerf tokens-per-second definition | Decides whether 4.5's ratios compare output tokens | Not read in LoadGen |
| 12 | AWS internet egress and real SSE bytes per token | Egress is small in the model. It is unmeasured | Not checked |
| 13 | Reasons to self-host that are not cost: data residency, privacy terms, control of the model version | The module question asks "at what point". For some teams the point is a rule, not a price. No saved source covers it | Added by the reviewer. Not checked. Needs a primary source, such as a provider's data-retention terms |
| 14 | Break-even against a dedicated endpoint or provisioned throughput | 4.6 shows these options exist. No U\* was computed against them | Added by the reviewer. Not checked. Together's page gives a calculator but no fixed per-unit price in the saved text |
| 15 | Autoscaling with per-second billing and cold start | 4.3 says per-second billing raises the reachable utilisation. No run measures it | Added by the reviewer. Inferred only. Overlaps gap 4 |

---

## 9. Things not verified

| Item | Check that would settle it |
|---|---|
| Whether MLPerf LLM "tokens/s" counts output tokens only | Read the LoadGen token-throughput definition at the v6.1 tag |
| InferenceX dataset, ISL distribution and EAGLE acceptance behind the NVIDIA rows | Read the InferenceX config at the commit behind each row date |
| Who ran the NVIDIA JSON rows, NVIDIA or SemiAnalysis | Match row dates to InferenceX published results |
| NVIDIA's "$0.02" and "$0.123" per million tokens | Read the InferenceX TCO assumptions |
| Latest InferenceX release tag | GitHub releases page. The API returned 403 |
| Lambda's 1-Click Cluster premium buys interconnect and capacity | Read Lambda's product page |
| Per-endpoint speed of the OpenRouter gpt-oss-120b providers | OpenRouter's throughput page in a browser |
| Loaded engineer salary | A salary survey or the learner's own figure |
| Cold-start times for a 120B model on H200 in 2026 | Time vLLM startup from local NVMe and from object storage |
| All PD, NIXL, LMCache and Mooncake runtime behaviour | Run the vLLM NixlConnector example on 2 Linux GPUs |
| H100 peak 989 TFLOPS and 3.35 TB/s used as prototype knobs | Fetch the NVIDIA H100 datasheet |
| Active parameter counts 70.6B, 32.8B, 22B, 37B | Count from each config or read each model card |
| The 40% prefill utilisation assumption | Measure prefill tokens per second on the target GPU |
| Mooncake FAST'25 Best Paper award | Fetch the usenix.org FAST'25 awards page |
| vLLM "Mooncake Store" post of 2026-05-07 | Fetch the vLLM blog post |
| Whether `mooncake-transfer-engine` installs on macOS arm64 | Check the PyPI file list for macOS wheels |
| Dynamo README claims of 7x, 2x, 80% and 750x | Fetch the linked InferenceX and Baseten pages |
| The Dynamo A/B GPU model | Find the run log. The manifest says "Adjust to your GPU node type" |
| The SGLang "10-20%" HA figure | Find the PR that added the text |
| The smg and SGLang gateway link | Read smg's first commit |
| Why the SGLang docs policy list and `main.rs` line 150 differ | Trace policy parsing in `sgl-model-gateway` at `v0.5.20` |
| The llm-d blog's model name "Qwen/Qwen-32B" and its identical 4,428.7 tok/s rows | Read the linked llm-d-kv-cache benchmark report |
| llm-d "100% precision" against its own "blind spot" note | Test with a delayed event stream |
| Why llm-d ITL rises on Qwen3-32B and falls 37.1% on gpt-oss-120b | No source explains the sign flip |
| Preble's venue, CacheRoute and DualMap organisations, AIBrix origin | OpenReview, the arXiv PDFs, the AIBrix README |
| The production-stack simhash "mixed results", issue #59 | Open the issue |
| KubeAI CHWBL results beyond 1,200 threads | Fetch its benchmarking page |

---

## 10. Review log

Reviewer: independent agent, not the dossier author. Date: 2026-09-25. Scope: read-only checks of the saved sources, re-runs of the three prototype self-tests, and arithmetic recomputed by hand. No lab ran. No URL was fetched.

### 10.1 What was checked

- **Anchors.** About 90 anchors were re-read by grep or `sed -n` in their saved files, independent of `D13/anchor_check.py`. They cover 4.1 to 4.5, 4.7 to 4.10, 4.12 to 4.17, and sections 5.1, 5.5 and 5.6. Every quoted phrase and number matches its file. The problems were missing conditions, missing labels and results left out, items 2 to 4, 6 to 8 and 10 below.
- **Arithmetic.** Every figure asked for was recomputed by hand. All match: KV bytes for the four configs, transfer against prefill, every U\* in 5.3, the fixed-cost fleet rows, the ceiling, $26,280, and $33,116.16. The exception is the 57 times figure, item 1.
- **Self-tests.** `EP/breakeven.py --self-test`, `DP/disagg_sim.py --selftest` and `RP/routersim.py --selftest` all pass on the learner's Mac with Python 3.9.6. The routersim message says "4 hand-worked cases" but names five. That is cosmetic. Not changed.
- **Conflicts.** a, d, f, g, j, k and l were checked against their evidence. All hold. Conflict f gained a note on memory size.
- **Overlap.** `grep '^## '` on `inference-internals/*.md` confirms the owners in section 2. One addition, item 12.

### 10.2 Corrections

| # | Kind | Where | Was | Now | Evidence |
|---|---|---|---|---|---|
| 1 | Fact, arithmetic | 4.8 heading, 4.8 trap, 6.2 lab row | "57 times too large" | 25 to 71 times, by the head size chosen. The prototype's own rule gives 24.9 times | `DP/configs/deepseek-ai_DeepSeek-V3.json` has no `head_dim`. 2 × 61 × 128 × 56 × 2 = 1,748,992. 2 × 61 × 128 × 128 × 2 = 3,997,696. 61 × 128 × (192 + 128) × 2 = 4,997,120. `DP/disagg_sim.py` line 58 |
| 2 | One-sided evidence | 4.15, 5.6 | gpt-oss-120b: "gains only 8.2%" | Also TTFT p90 −75.2%, TTFT p50 −84.1%, ITL p50 −37.1%. The workload was changed to 500 and 500 tokens | `R/llmd-main/guides_optimized-baseline_benchmark-results_vllm-gpt-oss-120b-h100.md` lines 3 to 30 |
| 3 | Label, who ran it | 4.5 | MLPerf numbers with no submitter | CoreWeave and Azure submitted offline and server. NVIDIA submitted interactive. The ratios mix submitters and, for DeepSeek R1, system sizes | `E/nvidia_dlperf_inference.txt` lines 42 to 45, 71 to 74, 223 to 226, 256 to 259, 416 to 419, 433 to 436 |
| 4 | One-sided evidence | 4.16 | CacheRoute loss only | Added the same paper's 2.3 times win on 70B, and that CacheRoute is load-aware, not pure affinity | `RW/arxiv_2608.19677.txt` lines 77, 98, 643, 667 |
| 5 | Lab design | 6.3 step 4 | "replays the Mooncake tool-agent trace through `routersim.py`" | Needs new code. `routersim.py` has no trace input | `RP/routersim.py` lines 54 to 56 and 315. No "trace" in the file |
| 6 | Wording | 5.5 | Mooncake "+42% effective capacity" | "effective caching capacity" | `D/fast25-qin.txt` lines 1156 to 1158 |
| 7 | Condition | 4.2 | DeepSeek $0.003 against $0.15 | Marked as off-peak. Peak is $0.006 against $0.30. The 2% ratio holds | `E/deepseek_pricing.txt` lines 86 to 119 |
| 8 | Condition | 4.16 scenario G | No load stated | Warm-up ramp, 20 then 60 requests per second | `RP/run_seed1.txt` section D3 |
| 9 | Label upgrade | 4.13, section 9 | Side-channel host "Not checked in source" | Verified in source | `VL/vllm/envs.py` lines 226 and 1651 to 1652 |
| 10 | Precision | 4.17 | Router replicas "do not share state" | Says which state each router keeps local. Dynamo shares prefix state through events | `R/dynamo/router-operations.md` lines 25 and 45 to 56. `R/llmd-main/guides_precise-prefix-cache-routing.md` line 50 |
| 11 | Labels | 4.10, 4.12, 4.15, 4.17, 5.5, 5.6 | Several vendor and preprint numbers had no such label, and two simulator results said only "inferred by run" | Added **vendor** to llm-d's own router results and to engine-team posts. Added **preprint** to LMCache. Added "simulator only" to the 4.12 pool replay and the 4.17 lag run | Source files named in each bullet |
| 12 | Overlap | Section 2 overlap table | Module 1 4.6's list of what you take on was not linked | Link it, and add only the headcount and cluster items | `M1/inference-internals-phase-04b-optimizing.md` line 532 |
| 13 | Label | 4.3 | CMU utilisation "verified" | The 100% reading is inferred. The quote is verified, line 357 | `E/arxiv_2509.18101.txt` line 357 |
| 14 | Hardware and cost | 6.2 | One-node PD lab gave only an hourly price. Cross-node lab gave only the $33,116 option | One-node: $20.94 at an assumed 3 hours. Cross-node: added 2 AWS p5.48xlarge on demand at $110.08 an hour as an unchecked cheaper option. Lambda price is before sales tax | `E/aws_ec2_ondemand_useast1.dec.json`, p5.48xlarge entry. `E/lambda_pricing.txt` |
| 15 | Condition | 4.3 | 80% peak target stated as fixed | Module 1 says the right target depends on how many servers share the queue | `M1/inference-internals-phase-06a-capacity-tenants.md` line 88 |
| 16 | Condition | 7, conflict f | "At 8,000 blocks aware wins" | Added that 8,000 blocks is 1,250 GiB per instance, beyond GPU memory | `DP/run_output.txt` section E |
| 17 | Condition | 4.3, Beyond Per-Token Pricing | "$0.21 to $15.25" paired with "offered load 1 to 10 requests per second" | The span covers six configurations from 1 request per second to saturation. $0.21 is a saturation figure. The 1 to 10 rps range goes with the 2.5 to 24 times penalty. Found by the Phase 4 fact checker. Phase 4 section 4.1 already states it this way. No other phase quotes the span | `E/arxiv_2606.11690.txt` lines 18 to 21 and 2522 to 2523 |
| 18 | Mechanism | 7, conflict f | "affinity pays when cache headroom exceeds the working set" as the one mechanism | Added the measured cause of the 5.5%: all 12,031 conversation requests share their first 512-token block, so the aware router sends 100% to one replica. A load gate gives 25.6%, a pool 26.8%. Found by the Phase 3 writer. Phase 3 section 3.1 teaches it | `serving-cluster/code/runs/serving-cluster_p03_pool_vs_locality.txt` |

### 10.3 Concepts added for the module question

| Concept | Where | Label and evidence |
|---|---|---|
| A published cost per token depends on the GPU price it assumes. LMSYS used H200 at $2.3 an hour | 4.2 | Verified quote, `D/lmsys_2025-07-20-k2.txt`. The comparison with $4.50 is inferred |
| Per-second billing and scale-down change the utilisation ceiling | 4.3 | Inferred. Modal price verified, `E/modal_pricing.txt` lines 25 to 40 |
| Preemptible GPUs at about half price | 4.6 | Verified prices, `E/together_pricing.txt`. Fit for batch only, inferred |
| Dedicated endpoints and provisioned throughput sit between an API and self-hosting | 4.6 | Verified that they exist, `E/together_pricing.txt` lines 605 to 650. What they move to the provider is inferred |
| Non-cost reasons to self-host | Section 8, gap 13 | Not checked. No saved source |

### 10.4 Checked and left unchanged

- Every per-GPU price in 5.1 matches its saved page. Lambda $6.16 and $3.99, Nebius October prices, and Together's ladder were re-read.
- TaiChi Table 2 numbers, the Vidur simulator label and the A100 setup match `D/p_2508.01989.txt` lines 417 to 475.
- DistServe "less than 0.1%", 25 Gbps and same-node NVLink placement match `D/p_2401.09670.txt` lines 868, 1108 to 1109 and 1417 to 1424.
- The shared-pool preprint's conditions and Table 3 values match `D/p_2609.15021.txt`.
- The vLLM lease, the failure policy, SGLang timeouts, the NIXL Linux-only line and the vLLM "DOES NOT improve throughput" line match at their tags.
- Each lab in section 6 names where it runs. Every Mac lab costs $0. Every GPU lab is marked Linux and optional or read-only.

Summary: the economics and disaggregation arithmetic hold. The main fixes are the 57 times figure, two one-sided routing results, and missing vendor and submitter labels.

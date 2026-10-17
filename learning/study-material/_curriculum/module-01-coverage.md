# Module 1 — LLM Inference Internals for Application Engineers

Status: COMPLETE. Course folder: `study-material/inference-internals/`. Code: `study-material/inference-internals/code/`.

This file lists what Module 1 teaches, section by section, so later modules link to it instead of repeating it.

## Documents

| Phase | File | Sections |
|---|---|---|
| 0 | `inference-internals-phase-00-frame.md` | 0.1 to 0.4 |
| 1 | `inference-internals-phase-01-lifecycle.md` | 1.1 to 1.6 |
| 2A | `inference-internals-phase-02a-scheduling-memory.md` | 2.1 to 2.3 |
| 2B | `inference-internals-phase-02b-decoding-context.md` | 2.4 to 2.6 |
| 3A | `inference-internals-phase-03a-caching.md` | 3.1 to 3.3 |
| 3B | `inference-internals-phase-03b-routing-alerting.md` | 3.4 to 3.5 |
| 4A | `inference-internals-phase-04a-serving.md` | 4.1 to 4.3 |
| 4B | `inference-internals-phase-04b-optimizing.md` | 4.4 to 4.6 |
| 5A | `inference-internals-phase-05a-client.md` | 5.1 to 5.3 |
| 5B | `inference-internals-phase-05b-observability.md` | 5.4 to 5.6 |
| 6A | `inference-internals-phase-06a-capacity-tenants.md` | 6.1 to 6.2 |
| 6B | `inference-internals-phase-06b-incidents-review.md` | 6.3 to 6.4 |

## What each section teaches

| Section | Topic | Key content |
|---|---|---|
| 0.1 | The machine behind the API | prefill vs decode, GPU memory, why input and output are priced differently |
| 0.2 | Three numbers | TTFT, TPOT, cost per request |
| 0.3 | Three failure stories | cache broken by a timestamp, retry storm under p99 spikes, switching to a cheaper model with no eval gate |
| 1.1 | Tokens | tokenizers, language and JSON token cost, pretty vs compact JSON (1.92x) |
| 1.2 | Prefill | TTFT scaling with prompt length |
| 1.3 | KV cache | KV bytes per token, concurrency arithmetic, GQA |
| 1.4 | Decode | TPOT, memory-bandwidth limit, output price gap |
| 1.5 | Sampling | temperature, top_p, determinism myth, seeds |
| 1.6 | Streaming and usage | SSE, stream usage, finish_reason, measuring TTFT |
| 2.1 | Scheduler loop | continuous batching, iteration-level scheduling |
| 2.2 | Paged KV cache | PagedAttention, block size, gpu_memory_utilization as capacity |
| 2.3 | Prefix caching in the server | radix tree, eviction, hit rate |
| 2.4 | Chunked prefill | TTFT vs TPOT trade, token budget |
| 2.5 | Constrained decoding | schema enforcement levels, the format tax evidence |
| 2.6 | Context budget and compaction trigger | budget zones, trigger thresholds, backstop on context-length error, limits of compaction, Governance Decay / ConstraintRot |
| 3.1 | Token classes | uncached, cached read, cache write, output, reasoning; tier and modality multipliers |
| 3.2 | Implicit prefix caching | provider behaviour, minimums, how caches are lost |
| 3.3 | Explicit caching | cache_control, TTL, write premium, break-even reads |
| 3.4 | Routing cascades | quality per dollar, random control group, signal quality |
| 3.5 | Per-request cost alerting | per-request budget, rolling cost, cache-hit floor, ledger |
| 4.1 | Renting a GPU | cost of downloads and idle time |
| 4.2 | Serving engines | vLLM and SGLang flags and differences |
| 4.3 | Benchmarking | concurrency sweep, goodput, TTFT/ITL percentiles |
| 4.4 | Quantization | formats, quality retention, the longer-reasoning cost |
| 4.5 | Speculative decoding | acceptance rate, draft length, batch-size crossover |
| 4.6 | Self-host decision | cost per token vs utilisation, break-even, engineer cost |
| 5.1 | Streaming timeouts | connect, read (stall), total; httpx2 Timeout |
| 5.2 | Rate limits | RPM, ITPM, OTPM, headers, ramp limits, 429 types |
| 5.3 | Retries | amplification, jitter, SDK defaults, health signal circuit breaker |
| 5.4 | SLOs | availability, latency, freeze, quality indicators; burn-rate alerting |
| 5.5 | Run record | OpenTelemetry GenAI names, attribution axes, sampling, noise floor |
| 5.6 | Fallbacks | failover vs fallback, degraded answers, cross-provider issues |
| 6.1 | Capacity planning | Erlang C, pooling, headroom for cold start, autoscaling on queue depth |
| 6.2 | Multi-tenant | token quotas, VTC fair scheduling, priority in vLLM/SGLang, cache_salt, pooling |
| 6.3 | Quality incidents | slice-first triage, rollback, control groups, postmortems |
| 6.4 | Design review | design docs, ADRs, launch checklists, pre-mortem, worked defence |

## Shared code other modules can reuse

| File | What it provides |
|---|---|
| `code/pricing.py` + `code/prices.yaml` | price sheet with cached/write/batch/tier fields, cost function, self-test |
| `code/phase03_economics/cascade_lab.py` | routing cascade simulation with a control group |
| `code/phase05_operations/run_recorder.py` | per-call record with OpenTelemetry names and three deadlines |
| `code/phase05_operations/slo_report.py` | SLO and burn-rate report from a ledger |
| `code/phase06_design/incident_drill.py` | slice-first quality triage |

## Overlap guidance for later modules

- Module 2 (context engineering): 2.6 already covers the budget, the trigger, and compaction limits. Module 2 adds measurement of context rot, compaction validation, sub-agent isolation, and pruning.
- Module 11 and 12 (evals): 3.4 and 6.3 use small eval sets and significance tests. The eval modules build the discipline properly.
- Module 13 (serving): Phase 4 and 6.1 cover single-node serving, benchmarking, quantization, speculative decoding, self-host cost, and capacity. Module 13 adds disaggregated serving, KV cache pools, and cluster-level routing.
- Module 14 (cost): Phase 3 covers token classes, caching, cascades, and cost alerts. Module 14 adds gateways, per-tenant metering, and FinOps practice.
- Module 15 (observability): 5.4 to 5.6 and 6.3 cover SLOs, run records, fallbacks, and quality incidents. Module 15 adds tracing pipelines, dashboards, and agent-level telemetry.
- Module 16 (security): 6.2 covers cache timing side channels and cache_salt.

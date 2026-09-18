<!-- Raw research-helper report, saved 2026-09-17. Not reviewed. Use as input to the module dossier; re-verify before quoting. -->

# Dossier cluster B: LLM observability platforms, agent trace trees, online monitoring and drift. Verified references.

I fetched every source on 2026-09-17 with curl or `gh api`, and checked each number with grep on the raw HTML or markdown. Scratch files are in `/private/tmp/claude-502/-Users-raghvendra-dhakar-Desktop-project-code/5ac29535-dfed-40f4-b977-06676a73b60b/scratchpad/m15b/`.

**Five changes the dossier must reflect:**
1. **LangSmith extended retention is now 180 days, not 400.** The change took effect on September 14, 2026. The LangChain pricing page still says 400 days, so the two sources disagree.
2. **Datadog renamed "LLM Observability" to "Agent Observability".** The old doc URLs still work.
3. **Datadog's "managed evaluations" list now has only two items:** Language Mismatch and Sensitive Data Scanning. Failure to Answer, Topic Relevancy, Sentiment and the others are now LLM-as-a-judge *templates*.
4. **Grafana renamed its product page to "Grafana Cloud OpenLIT Observability".**
5. **Phoenix OSS does not ship online evals on live traces at v20.13.0.** They exist only as a design spec in the repo. This is inferred from the docs and the spec.

**Access limits:**
- arize.com, including all Phoenix and Arize AX docs, returns HTTP 403 with `cf-mitigated: challenge`, which is a Cloudflare bot check. I used the Phoenix GitHub source instead.
- The unauthenticated GitHub API returned 403 because of rate limits. I used `gh api` instead.

## 1. Version table

| Tool | Version | Date (UTC) | Source | Status |
|---|---|---|---|---|
| Langfuse server | v4.38.0 | 2026-09-17 15:26 | `gh api repos/langfuse/langfuse/releases/latest` | verified |
| Langfuse Python SDK | 4.15.4 | 2026-09-16 16:13 | pypi.org/pypi/langfuse/json (200); GitHub tag v4.15.4 | verified |
| Langfuse JS SDK (`@langfuse/tracing`) | 5.11.1 | 2026-09-09 | registry.npmjs.org | verified |
| npm `langfuse` (legacy JS package) | 3.39.2 | 2026-09-15 | registry.npmjs.org | verified |
| arize-phoenix | 20.13.0 | 2026-09-16 22:48 | PyPI (200); tag arize-phoenix-v20.13.0 | verified |
| arize-phoenix-otel | 0.17.1 | 2026-08-10 | PyPI | verified |
| openinference-semantic-conventions | 0.1.38 | 2026-09-15 | PyPI; tag python-openinference-semantic-conventions-v0.1.38 | verified |
| langsmith (Python) | 0.12.6 | 2026-09-16 17:35 | PyPI; tag v0.12.6 | verified |
| langsmith (npm) | 0.10.4 | 2026-09-15 | npm | verified |
| braintrust (Python) | 0.41.0 | 2026-09-17 13:56 | PyPI; repo `braintrustdata/braintrust-sdk-python`, tag py-sdk-v0.41.0 | verified |
| braintrust (npm) | 3.34.0 | 2026-09-17 15:08 | npm; tag braintrust@3.34.0 | verified |
| ddtrace (Python, Datadog) | 4.15.0 | 2026-09-16 21:19 | PyPI | verified |
| dd-trace (npm) | 6.16.0 | 2026-09-11 | npm | verified |
| openlit (Python SDK) | 1.45.0 | 2026-08-03 | PyPI; GitHub tag py-1.45.0 | verified |
| OpenLIT platform | openlit-2.1.0 | 2026-09-10 | GitHub releases | verified |
| grafana/docker-otel-lgtm | v0.33.0 | 2026-09-11 | GitHub releases. The notes say it bundles opentelemetry-collector v0.160.0 and Grafana v13.2.1 | verified |
| Helicone | v2025.08.21-1 is the latest GitHub release | 2025-08-21 | GitHub releases | verified. The PyPI package `helicone` is stale: 1.0.14 from 2023-11-03 |

## 2. Agent trace data models

### Langfuse
- **Verified.** There are 10 observation types: `event`, `span`, `generation`, `agent`, `tool`, `chain`, `retriever`, `evaluator`, `embedding`, `guardrail`.
  - Source: https://langfuse.com/docs/observability/features/observation-types.md (200), section "Available Types".
  - The server enum matches. See `packages/shared/src/domain/observations.ts:5-16` at tag v4.38.0: SPAN, EVENT, GENERATION, AGENT, TOOL, CHAIN, RETRIEVER, EVALUATOR, EMBEDDING, GUARDRAIL.
  - The page says: "Langfuse calls spans observations; `span` is also a specific observation type."
- **Verified. Sessions.** A trace is "the logical grouping of all observations that share the same `trace_id`". Traces can optionally be grouped into sessions (data-model.md, "Observations & Traces").
  - `sessionId` is "any US-ASCII character string less than 200 characters" (sessions.md, line 26).
  - Python sets it with `propagate_attributes(session_id=...)`.

### Phoenix / OpenInference
- **Verified. Span kinds.** `OpenInferenceSpanKindValues` has TOOL, CHAIN, LLM, RETRIEVER, EMBEDDING, AGENT, RERANKER, UNKNOWN, GUARDRAIL, EVALUATOR, PROMPT.
  - Source: `python/openinference-semantic-conventions/src/openinference/semconv/trace/__init__.py:599-610`, tag v0.1.38.
  - The brief's list leaves out **PROMPT** and **UNKNOWN**.
- **Verified. Grouping attributes.** Sessions and users use the `session.id` and `user.id` attributes (same file, lines 268 and 272).

### LangSmith
- **Verified. Run types.** `RUN_TYPE_T = Literal["tool", "chain", "llm", "retriever", "embedding", "prompt", "parser"]`.
  - Source: `python/langsmith/client.py:659-661`, tag v0.12.6.
  - The default is `"chain"` (`run_trees.py:648`).
  - The docs table matches: https://docs.langchain.com/langsmith/run-data-format.md (200), section "Run types".
- **Verified. Threads.** A thread is "a sequence of traces representing a single multi-turn session… pass a `thread_id` metadata key with a unique value".
  - Source: observability-concepts.md, section "Threads".
  - The same page also defines a "trajectory", which is a flattened message list over a thread.

### Braintrust
- **Verified. Span types.** `SpanTypeAttribute` has llm, score, function, eval, task, tool, automation, facet, preprocessor, classifier, review, question.
  - Source: `py/src/braintrust/span_types.py:10-21`, tag py-sdk-v0.41.0.
  - The class docstring says "Use `SpanType` instead. :deprecated:". I did not find a separate `SpanType` definition in that file.
- **Verified. Score spans.** Online scorer runs appear as score spans. Rules can be scoped to trace, span or group (score-online.md).

### Datadog
- **Verified. Span kinds.** LLM, Workflow, Agent, Tool, Task, Embedding, Retrieval.
  - Only LLM, Workflow and Agent are valid root spans.
  - Source: https://docs.datadoghq.com/llm_observability/quickstart/terms.md (200), table under "span kind".

## 3. OpenTelemetry support

**Summary: every vendor here accepts OTLP. Langfuse, Phoenix and Braintrust map `gen_ai.*` attributes. Datadog names semconv 1.37+. For LangSmith I did not check whether it maps `gen_ai.*`.**

| Tool | OTLP endpoint | `gen_ai.*` mapping | Semconv version | Status |
|---|---|---|---|---|
| Langfuse | `/api/public/otel`. Traces path is `/api/public/otel/v1/traces`. Self-hosted needs ">= v3.22.0". | Yes, through an attribute-mapping table, for example `gen_ai.request.model` → model and `gen_ai.usage.*` → usage. | No version pinned. The page says "Langfuse aims to be compliant with the OpenTelemetry GenAI semantic conventions" and links the agent-spans spec. | verified (integrations/native/opentelemetry.md, lines 19, 54, 359, 433-438) |
| Phoenix | `POST /v1/traces`, which accepts only `application/x-protobuf`. gRPC runs on port 4317 in Phoenix 4.0+ (llms.txt FAQ entry). | Yes. The server converts `gen_ai.*` into OpenInference attributes. Existing OpenInference keys win (`setdefault`). | Generated from `open-telemetry/semantic-conventions-genai` at commit `494d44d5bcc9`. A code comment says the v1.41.1 snapshot is "byte-identical". | verified (`src/phoenix/server/api/routers/v1/traces.py:440-477`; `routers/v1/__init__.py:54` prefix `/v1`; `src/phoenix/trace/otel.py:79-82`; `scripts/generate_otel_gen_ai_models.py:28-32`; all at arize-phoenix-v20.13.0) |
| LangSmith | `OTEL_EXPORTER_OTLP_ENDPOINT=https://api.smith.langchain.com/otel`. Set `LANGSMITH_OTEL_ENABLED=true` for LangChain and LangGraph. | The doc example sets `gen_ai.system` and `gen_ai.prompt.{i}.content`. | Not stated on the page. | verified (trace-with-opentelemetry.md, lines 67, 112-118, 165-187). Semconv version: not checked |
| Braintrust | `https://api.braintrust.dev/otel`. Traces path is `/otel/v1/traces`. The header `x-bt-parent=project_id:…` is required. | Yes, with a mapping table (`gen_ai.input.messages` → input, and so on). | Links to `semantic-conventions-genai` at `main`. No version is named. | verified (opentelemetry.md, lines 405-417, 582-591). The JS package moved to `@braintrust/otel` "starting with v1.0" (line 63) |
| Datadog | Uses `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` with header `dd-otlp-source=llmobs`. The doc shows only the placeholder `<YOUR_OTLP_TRACE_ENDPOINT>`. | Yes. Also accepts OpenInference conventions. "without requiring the Agent Observability SDK or a Datadog Agent". | "OpenTelemetry 1.37+ semantic conventions for generative AI". | verified (otel_instrumentation.md, lines 29, 98-100) |

**Langfuse SDK v3 is built on OpenTelemetry.**
- Verified. The upgrade guide says "v3 is built on OpenTelemetry standards" (python-v2-to-v3.md, line 21).
- Verified. PyPI shows `langfuse` 3.0.0 uploaded 2025-06-05 and 3.0.0b1 uploaded 2025-05-20.
- Verified. v4.0.0 was uploaded 2026-03-10. In v4, "Smart default span filtering replaces export-all behavior" (python-v3-to-v4.md, line 20).

**Datadog native support for OTel GenAI semconv.**
- Verified. Blog post: "Datadog Agent Observability natively supports OpenTelemetry GenAI Semantic Conventions", published Dec 1, 2025. URL: https://www.datadoghq.com/blog/llm-otel-semantic-convention/ (200).
- The byline starts "Barry Eom, Zach Groves, Will Potts…". The page text was truncated after these names.
- The post says "(v1.37 and up)".

## 4. Sampling and masking

### Sampling

**Langfuse (verified)**
- The docs say: "The default value is 1, meaning that all traces are collected." Sampling is decided per trace.
  - Source: sampling.md, line 13. The docs set it with `LANGFUSE_SAMPLE_RATE` or `sample_rate`.
- The source matches:
  - `langfuse/_client/environment_variables.py:108-115` says "**Default value**: ``1.0``".
  - `client.py:354-358` reads the env var and raises an error outside the range 0.0 to 1.0.
  - Both files are at tag v4.15.4.
- Langfuse "respects OpenTelemetry's sampling decisions", for example `TraceIdRatioBasedSampler(0.2)`.

**LangSmith (verified)**
- The env var is `LANGSMITH_TRACING_SAMPLING_RATE`, a float from 0 to 1. The docs say "By default, all traces are logged". Each client can also set `Client(tracing_sampling_rate=0.5)`.
  - Source: sample-traces.md, lines 21-37.
- The source matches: `client.py:777-797` at v0.12.6 returns `None` when the value is unset and raises an error outside the range 0 to 1.

**Datadog**
- Not checked. I did not find a trace-ingest sampling setting for Agent Observability in the pages I read.

**Phoenix**
- Not checked for the SDK. Phoenix uses standard OTel samplers. This is inferred from the OTel basis and was not read in the docs.

### Masking and redaction

**Langfuse (verified)**
- There are two Python hooks:
  - `mask_otel_spans` is marked "Recommended". It runs at export stage and covers third-party instrumentation spans.
  - `mask` is marked "Legacy". It runs synchronously when SDK attributes are created.
  - Source: masking.md, table under "Configure masking".
- A changelog entry for export-stage masking is dated 2026-06-16 (URL in the sitemap). I did not open that changelog page.

**Phoenix / OpenInference (verified)**
- These env vars exist:
  - `OPENINFERENCE_HIDE_INPUTS`, `…_HIDE_OUTPUTS`, `…_HIDE_INPUT_MESSAGES`, `…_HIDE_OUTPUT_MESSAGES`
  - `…_HIDE_INPUT_IMAGES`, `…_HIDE_INPUT_TEXT`, `…_HIDE_OUTPUT_TEXT`
  - `…_HIDE_PROMPTS`, `…_HIDE_CHOICES`, `…_HIDE_LLM_INVOCATION_PARAMETERS`, `…_HIDE_LLM_TOOLS`
  - `…_HIDE_EMBEDDINGS_VECTORS`, `…_HIDE_EMBEDDINGS_TEXT`
- All default to False. `OPENINFERENCE_BASE64_IMAGE_MAX_LENGTH` defaults to 32,000.
- Source: `spec/configuration.md:11-25` at the v0.1.38 tag.

**LangSmith (verified)**
- `LANGSMITH_HIDE_INPUTS=true` and `LANGSMITH_HIDE_OUTPUTS=true` hide all inputs and outputs. The client also accepts `hide_inputs` and `hide_outputs` callables.
- Rule-based regex masking and Presidio or Comprehend examples are available.
- Source: mask-inputs-outputs.md, lines 11-45.

**Datadog (verified)**
- Span processors in the SDK redact data before it is sent.
- Sensitive Data Scanner "identifying and redacting" is integrated (data_governance.md, lines 35-49).
- The pricing FAQ says SDS is "built into Agent Observability at no additional cost". The allotment is "1 GB of SDS processing" per 10K LLM spans.

## 5. Pricing and retention

All prices below were fetched on 2026-09-17.

### Langfuse Cloud (verified)
Source: https://langfuse.com/pricing.md (200).

**Plans:**

| Plan | Monthly fee | Included units | Historical data access |
|---|---|---|---|
| Hobby | Free | 50k units | 30 days |
| Core | $29 | 100k units | 90 days |
| Pro | $199 | 100k units | 3 years |
| Enterprise | $2,499 | 100k units | 3 years |

**Graduated rates for extra units:**

| Volume | Rate |
|---|---|
| 100k–1M units | $8.00/100k |
| 1M–10M units | $7.00/100k |
| 10M–50M units | $6.50/100k |
| 50M+ units | $6.00/100k |

**Worked examples on the page:**
- 1M units/month on Core costs $101.00/month.
- 100M units/month on Enterprise costs $8,801.00/month.

**Units:**
- `Units = Count of Traces + Count of Observations + Count of Scores` (billable-units.md).
- LLM-as-a-Judge scores count as units.

**Retention:**
- Project retention has "a minimum of 3 days".
- Without a retention policy, Langfuse does not auto-delete data (data-retention.md, lines 25-31).

**Metrics API v2 rate limits:**

| Plan | Limit |
|---|---|
| Hobby | 100 req/day |
| Core | 100 req/hour |
| Pro | 500 req/hour |

### LangSmith (verified, with a conflict)

**Docs.** Source: usage-and-billing.md and billing.md, both 200.
- Base traces keep data for 14 days. Extended traces keep data for 180 days.
- The docs say: "Starting September 14, 2026, the maximum long-lived trace retention period for SaaS customers is changing to 180 days."

**Pricing page.** Source: https://www.langchain.com/pricing (200). The page FAQ still says: "Extended traces have a longer retention period of 400 days."
- **Conflict:** the docs describe the policy in force from 2026-09-14. The marketing FAQ looks stale. This is inferred.

**Plans:**
- Developer: $0/seat, "Up to 5k base traces / mo".
- Plus: $39/seat, "Up to 10k base traces / mo".
- After the included traces, billing is pay-as-you-go in LSUs. The page says "1 LSU = $1.00" and "1 LCU = $1.50".

**Per-trace price.**
- The pricing calculator JavaScript has `traceLsuPerTrace:0.005` and `lsuPrice:1.0`. This works out to $0.005 per base trace, or $5 per 1k. This is verified from the JS constants. I found no visible text on the page that states it.
- I did not find the extended-trace price on the page. Not checked.

**Other LangSmith numbers (verified):**
- observability-concepts.md says: "LangSmith (SaaS) retains trace data for 180 days from ingestion."
- billing.md gives an example: "keep 10% of all traces for extended data retention".

### Datadog Agent Observability (verified)
Source: https://www.datadoghq.com/pricing/?product=llm-observability and /pricing/list/ (both 200).
- The prices are default values inside `x-text` templates, which JavaScript may change by region. The prices below are the US defaults.

**Plans:**

| Tier | Price | Included LLM spans | Trace retention |
|---|---|---|---|
| Free | $0 | Up to 40K per month | 15 days |
| Pro | $160/mo annual, $200 month-to-month, $240 on-demand | First 100K per month | 15 days |

**Extra spans:**

| Billing | Price per 10K LLM spans |
|---|---|
| Annual | $3.50 |
| Month-to-month | $4.20 |
| On-demand | $5.00 |

**Retention add-ons:**

| Add-on | Price per 10K spans | Experiment retention |
|---|---|---|
| 30-day | $1.50 | 6 months |
| 60-day | $3 | 9 months |
| 90-day | $4 | 12 months |

**Billing rule:** the page says "Per LLM spans only — not tool spans, workflow spans, or retrieval spans."

**Retention in the docs:**
- Traces and spans are kept for "15 days; 30, 60, or 90 days with a retention add-on".
- `ml_obs.*` metrics are kept for 15 months.
- Source: data_governance.md, section "Data retention".

### Braintrust (verified)
Source: https://www.braintrust.dev/pricing (200).

| Item | Starter | Pro |
|---|---|---|
| Monthly fee | $0 | $249 |
| Processed data | 1 GB included, then $4/GB | 5 GB included, then $3/GB |
| Scores | 10k included, then $2.50/1k | 50k included, then $1.50/1k |
| Retention | 14 days | 30 days, extendable at "+ $0.50/GB/mo" |

- Scores are defined as "Scored outputs from LLM-as-a-judge, autoevals, or custom code scorers."

### Phoenix (verified)
- The default retention policy is 0 days, which means "Indefinite". The env var is `PHOENIX_DEFAULT_RETENTION_POLICY_DAYS`.
- Source: `docs/phoenix/settings/data-retention.mdx` at v20.13.0.
- Phoenix Cloud pricing: not checked, because arize.com is blocked.

## 6. Online evaluation and drift

### Online evaluation

**Langfuse (verified)**
- A rule defines "filters, sampling rate, and one or more evaluators". The docs say: "For LLM-as-a-Judge, also review the estimated cost and lower the sampling rate if needed" (get-started/online.md, line 125).
- Observation-level evaluators are "the recommended target for live production data". Trace-level evaluators are "deprecated" (llm-as-a-judge.md, line 36).

**LangSmith (verified)**
- Online LLM-as-judge evaluators support filters and a sampling rate. The docs say: "to only apply the evaluator to 10% of traces… you would set the sampling rate to 0.1" (online-evaluations-llm-as-judge.md, line 48).
- Rules can be backfilled to past runs or threads.
- Multi-turn (thread) evaluators have their own page.

**Braintrust (verified)**
- Online scoring rules can be trace-, span- or group-scoped.
- The "Idle timeout… Defaults to 30 seconds". The "Sampling rate" is the "Percentage of matching traces that Braintrust scores after the trace has gone idle".
- The API example uses `"sampling_rate": 1` (score-online.md, lines 60-114).

**Datadog (verified)**
- Custom LLM-as-a-judge evaluations can run on span, trace or session. The sampling is described as "Sampling Rate: (Optional) Apply sampling (for example, 10%) to control evaluation cost." (llm_as_a_judge_evaluations.md, lines 56 and 527).
- Templates: Failure to Answer, Goal Completeness, Hallucination, Prompt Injection, Sentiment, Tool Argument Correctness, Tool Selection, Topic Relevancy, Toxicity (template_evaluations.md, line 24).
- Managed evaluations are only Language Mismatch and Sensitive Data Scanning (managed_evaluations.md).

**Phoenix**
- Inferred: no shipped online evals in OSS at v20.13.0.
  - Server evals are "Attach evaluators directly to a dataset and run them automatically on every experiment" (`evaluation/server-evals/overview.mdx`).
  - `internal_docs/specs/online-evals.md` is a design spec. It says "It does not settle every decision… before implementation".
  - To confirm, check the Phoenix release notes after v20.13.0, or the Arize AX docs, which are blocked.

**Grafana / OpenLIT (verified)**
- Built-in evals are `openlit.evals.All`, `Hallucination`, `Bias` and `Toxicity`.
- Source: grafana.com/docs/.../ai-observability/genai/evaluations/index.md (200).

### Drift and clustering

**Phoenix (verified, legacy feature)**
- The legacy "inferences" docs say: "Phoenix uses euclidean distance as the primary measure of embedding drift". Centroids of the two datasets are compared. Clusters come from HDBSCAN and are "ordered by drift".
  - Source: `docs/inferences/use-cases-inferences/embeddings-analysis.md`, lines 11-37, tag arize-phoenix-v4.0.0 (commit dated 2024-05-09).
- The code matches. `src/phoenix/metrics/metrics.py:144-162` at v4.0.0 has `EuclideanDistance`. Its code takes `euclidean(np.mean(data), reference_value)`, where the reference value is the mean of the reference data.
- The same file defines three more drift measures:
  - `PSI`, whose docstring says "2 times the symmetrized KL-divergence… also known as Jeffreys divergence".
  - `KLDivergence`.
  - `JSDistance`.
- At v20.13.0 the `src/phoenix/metrics/` directory no longer has `metrics.py`, so the drift code is gone from current Phoenix. Verified from the file tree.
- The Arize AX embedding-drift doc page and the Arize course URL `arize.com/blog-course/embedding-drift-euclidean-distance/` both return 403. **Not verified.**

**Datadog Patterns (verified)**
- Datadog Patterns uses "text embedding… self-hosted, open source model", then "clusters using machine learning (UMAP and HDBSCAN)", with an "Outliers group" (patterns.md, lines 30-42).
- The page documents topic clustering, not a drift metric.

## 7. Dashboard guidance and the four proposed dashboards

### Google SRE (verified)
- Source: https://sre.google/sre-book/monitoring-distributed-systems/ (200). Chapter by Rob Ewaschuk, edited by Betsy Beyer.
- Exact quote from the section "The Four Golden Signals": "The four golden signals of monitoring are latency, traffic, errors, and saturation. If you can only measure four metrics of your user-facing system, focus on these four."
- The same page recommends bucketed latency histograms over means, with boundaries "approximately exponentially (in this case by factors of roughly 3)".

### What each vendor shows by default

**Langfuse (verified)**
- Curated dashboards cover Latency, Cost and Langfuse usage.
- The Home page shows "traces, model cost, latency percentiles, scores, and model usage" (custom-dashboards.md, lines 35 and 83).
- Widgets use metrics such as "count, latency, cost, scores" and dimensions such as "user, model, time, trace name".
- Conflict to note: Metrics API v2 says `id`, `traceId`, `userId` and `sessionId` "cannot be used for grouping… remain available for filtering" (metrics-api.md, line 70).

**LangSmith (verified)**
- Prebuilt dashboard sections are Traces (count, latency, error rates), LLM Calls, Cost & Tokens, Tools, Run Types and Feedback Scores.
- Group-by works on tag or metadata. The docs say: "Metadata and tags are not propagated from parent to child runs" (dashboards.md, lines 22-37).

**Phoenix (verified)**
- The default dashboard shows:
  - traces over time
  - trace latency percentiles
  - cost in USD
  - top models by cost and by tokens
  - LLM and tool span counts, and spans with errors
  - average span and trace annotation scores
- Source: `docs/phoenix/tracing/llm-traces/metrics.mdx` at v20.13.0.

**Datadog (verified)**
- The out-of-the-box "Agent Observability Operational Insights dashboard" covers request volume and latency, error tracking and token consumption (monitoring.md, lines 28-39).

**Grafana (verified)**
- The GenAI Observability dashboard covers cost analysis, error tracking, "Cost per request analysis" and "Track 95th percentile operation duration" (genai/observability and the index page).

### Mapping the four proposed dashboards to vendor docs

| Proposed dashboard | Vendor support | Status |
|---|---|---|
| Cost per tenant | Cost is standard everywhere. "Per tenant" needs a tag or metadata group-by in LangSmith. In the Langfuse v2 API, `userId` cannot be a group-by, so use tags or metadata. | inferred |
| Latency percentiles per channel | Langfuse, Phoenix and Grafana name latency percentiles. "Per channel" needs a tag or metadata dimension. | inferred |
| Eval scores over time | Named by Langfuse, LangSmith, Phoenix and Braintrust ("score aggregations"). | verified |
| Fallback and error rates | Error rates are named by LangSmith, Phoenix, Datadog and Grafana. None of the pages I read names "fallback rate" as a built-in metric, so it must be custom. | inferred |

## 8. Published numbers on online monitoring

These are the only numbers I found:
- The LangSmith sampling example of 0.1.
- The LangSmith example of keeping 10% of traces for extended retention.
- Datadog's "for example, 10%".
- The Braintrust API example with `sampling_rate: 1`.
- Langfuse's statement that sampling cannot be dynamic by outcome: "Dynamic sampling based on error levels isn't feasible since you only know if a trace is interesting after completion" (faq/all/cutting-costs.md, line 37).

None of these is a benchmark. They are doc examples, so the dossier should present them as examples. I found no first-party published number on judge cost per sampled trace. Langfuse shows an estimated cost only in its UI.

## Could not verify

- All arize.com pages, because of the Cloudflare 403. This includes the Arize AX embedding-drift page, Phoenix Cloud pricing, and the Arize drift course.
- The LangSmith extended-trace price.
- The Datadog OTLP endpoint host. The doc shows only a placeholder.
- Datadog trace-ingest sampling.
- The semconv version LangSmith maps.
- Helicone data model, pricing and sampling. I checked only its version.
- OpenLIT SDK sampling and masking options.
- Whether Datadog region pricing differs from the US defaults in the HTML.
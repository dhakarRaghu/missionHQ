<!-- Raw research-helper report, saved 2026-09-17. Not reviewed. Use as input to the module dossier; re-verify before quoting. -->

# Cluster A report: OpenTelemetry GenAI semantic conventions and the Collector pipeline

**Answer:** The GenAI conventions now live in `open-telemetry/semantic-conventions-genai`. The move shipped in core semconv **v1.42.0** (2026-06-12). Every GenAI signal is still at **Development** status. The new repo has **no release tag** yet.

## How I checked

- **Access:** The unauthenticated GitHub API returned HTTP 403 because of the rate limit. I used the authenticated `gh api` for all GitHub API calls. I read raw files with `curl` from raw.githubusercontent.com. Every URL below returned HTTP 200 unless I say otherwise.
- **Scratch files:** `/private/tmp/claude-502/-Users-raghvendra-dhakar-Desktop-project-code/5ac29535-dfed-40f4-b977-06676a73b60b/scratchpad/m15a/`
- **Labels:** V = verified, I = inferred, NC = not checked.

---

## 1. GenAI semantic conventions

### 1a. Where the conventions live now

The core repo is maintained by the OpenTelemetry project, open-telemetry org.

| # | Fact | Label | Evidence |
|---|---|---|---|
| 1 | The latest core semconv release is **v1.44.0**, published 2026-08-04. v1.43.0 was published 2026-07-03, and v1.42.0 on 2026-06-12. | V | `gh api repos/open-telemetry/semantic-conventions/releases` |
| 2 | v1.42.0 made the move. The changelog entry says: "Move Generative AI semantic conventions to a dedicated repository." (#3696) | V | `CHANGELOG.md@v1.44.0:118` |
| 3 | In core v1.44.0, `docs/gen-ai/*.md` are 11-line stubs. The heading is "Moved: Generative AI semantic conventions" and the page links to the new repo. | V | `docs/gen-ai/README.md@v1.44.0:5-11` |
| 4 | Core v1.44.0 keeps only `model/gen-ai/deprecated/`, with 4 files. Each group carries the note "Moved to the OpenTelemetry GenAI semantic conventions repository". | V | `model/gen-ai/deprecated/registry-deprecated.yaml@v1.44.0:1-12` |
| 5 | `open-telemetry/semantic-conventions-genai` exists. It was created 2026-05-05 and last pushed 2026-09-16. It is not archived. | V | `gh api repos/...-genai` |
| 6 | The genai repo has **zero tags and zero releases**. | V | Both the tags and releases API calls returned empty lists. |
| 7 | The genai repo's latest commit is `c88d504ab3d9879f8e50d3cc87e69775e11db234`, dated 2026-09-16. The commit before it is "Allow conversation ID on tool execution spans (#518)". I pin all genai file:line references below to this SHA. | V | commits API |
| 8 | The genai README says the repo "extends the OpenTelemetry Semantic Conventions … using Weaver". The "Schema URL" section says only "TODO". The CHANGELOG has only an "Unreleased" section, managed by Towncrier. | V | `README.md:7-15`, `CHANGELOG.md` |
| 9 | The genai repo kept the git history from core. For example, it contains "Retrieval Span Support (#2924)" from 2026-01-20. | V | commits API, path=model/gen-ai/spans.yaml |

### 1b. Status of each signal

The genai overview page says `**Status**: [Development]` (`docs/gen-ai/README.md:7`). Every span, metric, event and attribute that I checked has `stability: development`.

| Signal | Evidence | Label |
|---|---|---|
| Spans | `model/gen-ai/spans.yaml:187,284,321,352,432,467,519,563,592,652,691` | V |
| Metrics | `model/gen-ai/metrics.yaml:38,51,68,...` | V |
| Events | `model/gen-ai/events.yaml:11,20,54`; `docs/gen-ai/gen-ai-events.md:7` | V |
| MCP spans | `model/mcp/spans.yaml:51,104` | V |

Nothing in the GenAI area is stable (V).

### 1c. Span types: name format and span kind

Source: `model/gen-ai/spans.yaml` at c88d504.

| Span type (operation) | Kind | Span name format | Line |
|---|---|---|---|
| `gen_ai.inference.client` (chat, generate_content, text_completion) | client. The note says CLIENT "MAY be set to INTERNAL" for in-process models. | `{gen_ai.operation.name} {gen_ai.request.model}` | 171-186 |
| `gen_ai.embeddings.client` (`embeddings`) | client | `{gen_ai.operation.name} {gen_ai.request.model}` | 273-283 |
| `gen_ai.retrieval.client` (`retrieval`) | client | `{gen_ai.operation.name} {gen_ai.data_source.id}` | 309-320 |
| `gen_ai.fetch_response.client` | client | `{gen_ai.operation.name}` | 339-350 |
| `gen_ai.memory.client` | client | `{gen_ai.operation.name}` | 404-409 |
| `gen_ai.create_agent.client` | client | `create_agent {gen_ai.agent.name}` | 455-466 |
| `gen_ai.invoke_agent.client` | client | `invoke_agent {gen_ai.agent.name}`, or `invoke_agent` when there is no name | 505-516 |
| `gen_ai.invoke_agent.internal` | internal | same as the row above | 549-560 |
| `gen_ai.execute_tool.internal` | internal | `execute_tool {gen_ai.tool.name}` | 573-581 |
| `gen_ai.invoke_workflow.internal` | internal | `invoke_workflow {gen_ai.workflow.name}` | 619-629 |
| `gen_ai.plan.internal` | internal | `plan {gen_ai.agent.name}`, or `plan` | 669-679 |

All rows are V. The file also has provider-specific span types: `openai.inference.client`, `azure.ai.inference.client`, `anthropic.inference.client` and `aws.bedrock.inference.client` (lines 704-861, V).

**`gen_ai.operation.name` enum.** Source: `model/gen-ai/registry.yaml:600-674` (V). The values are:

- chat
- generate_content
- text_completion
- embeddings
- retrieval
- fetch_response
- create_agent
- invoke_agent
- execute_tool
- invoke_workflow
- plan
- search_memory
- create_memory
- update_memory
- upsert_memory
- delete_memory
- create_memory_store
- delete_memory_store

**When some operations arrived** (V, commit messages in the genai repo):

- `invoke_workflow`: 2026-03-09 (#3249)
- `plan`: 2026-05-11 (#97)
- memory operations: 2026-05-19 (#140)
- `retrieval`: 2026-01-20 (#2924)

### 1d. Attributes

All attributes below are in `model/gen-ai/registry.yaml` at c88d504, and all are `stability: development` (V).

| Attribute | Line |
|---|---|
| `gen_ai.provider.name` | 3 |
| `gen_ai.conversation.id` | 412 |
| `gen_ai.agent.id` | 446 |
| `gen_ai.agent.name` | 458 |
| `gen_ai.tool.name` | 473 |
| `gen_ai.tool.call.id` | 478 |
| `gen_ai.tool.call.arguments` | 502 |
| `gen_ai.tool.call.result` | 522 |
| `gen_ai.tool.definitions` | 546 |
| `gen_ai.data_source.id` | 590 |
| `gen_ai.system_instructions` | 830 |
| `gen_ai.input.messages` | 872 |
| `gen_ai.output.messages` | 926 |
| `gen_ai.evaluation.name` | 962 |
| `gen_ai.evaluation.score.value` | 967 |
| `gen_ai.workflow.name` | 1022 |

**`gen_ai.system` was renamed to `gen_ai.provider.name` in core v1.37.0**, published 2025-08-25 (#2046). The same change removed the `gen_ai` prefix from `gen_ai.openai.*` and renamed `az.ai.*` to `azure.ai.*`.

- Evidence: `CHANGELOG.md@v1.44.0:595-599` (V).
- `gen_ai.system` does not appear anywhere in the genai repo files I downloaded (V, grep).
- It exists only in core's `deprecated/registry-deprecated.yaml:65` (V).

**Sampling-relevant attributes.** Some span attributes carry `sampling_relevant: true`, for example `spans.yaml:263-271` (V). Core v1.40.0 added this flag (#2994, `CHANGELOG.md:359`, V).

### 1e. Metrics and their bucket boundaries

Source: `docs/gen-ai/gen-ai-metrics.md` at c88d504. Each metric doc says it "SHOULD be specified with [ExplicitBucketBoundaries] of" the values below. All rows are V.

| Metric | Unit | Boundaries | Line |
|---|---|---|---|
| `gen_ai.client.token.usage` | `{token}` | [1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864] | 46-49 |
| `gen_ai.client.operation.duration` | s | [0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92] | 174-176 |
| `gen_ai.client.operation.time_to_first_chunk` | s | same as the row above | 301-303 |
| `gen_ai.client.operation.time_per_output_chunk` | s | same | 415-417 |
| `gen_ai.server.request.duration` | s | same | 534-540 |
| `gen_ai.server.time_per_output_token` | s | [0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 2.5] | 663-674 |
| `gen_ai.server.time_to_first_token` | s | [0.001, 0.005, 0.01, 0.02, 0.04, 0.06, 0.08, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0] | 784-794 |
| `gen_ai.invoke_workflow.duration` | s | [1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600, 7200] | 906-908 |
| `gen_ai.invoke_agent.duration` | s | [0.1, 0.2, 0.4, … 409.6] | 970-973 |
| `gen_ai.invoke_agent.inference_calls` | `{inference_call}` | not copied | 1028 |
| `gen_ai.invoke_agent.tool_calls` | `{tool_call}` | not copied | 1067 |
| `gen_ai.execute_tool.duration` | s | same as `gen_ai.client.operation.duration` | 1116-1119 |

**Token usage rule.** `metrics.yaml:37` says: "When systems report both used tokens and billable tokens, instrumentation MUST report billable tokens." (V)

**MCP metrics.** These are defined in `model/mcp/metrics.yaml:20-55` (V):

- `mcp.client.operation.duration`
- `mcp.server.operation.duration`
- `mcp.client.session.duration`
- `mcp.server.session.duration`

### 1f. Events

Source: `model/gen-ai/events.yaml` (V).

| Event | Line |
|---|---|
| `gen_ai.client.inference.operation.details` | 3 |
| `gen_ai.evaluation.result` | 14 |
| `gen_ai.client.operation.exception` | 41 |

**Per-message events were deprecated in core v1.37.0** (2025-08-25). The v1.37.0 changelog entry reads "Revamp how GenAI chat history is recorded" and lists these deprecations:

- `gen_ai.system.message`
- `gen_ai.user.message`
- `gen_ai.assistant.message`
- `gen_ai.tool.message`
- `gen_ai.choice`

The replacements are the `gen_ai.system_instructions`, `gen_ai.input.messages` and `gen_ai.output.messages` attributes. The same entry says: "New attributes are not recorded by default when content capturing is disabled." Evidence: `CHANGELOG.md@v1.44.0:581-593` (V).

**Evaluation event.** "Introducing `Evaluation Event`" appears in the core v1.38.0 section (2025-10-29), #2563, `CHANGELOG.md:536` (V).

### 1g. Content capture

- **Opt-in attributes.** `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.tool.definitions` and `gen_ai.prompt.variable` are all `Opt-In` on inference spans (`gen-ai-spans.md:106-110`, V). `gen_ai.tool.call.arguments` is also Opt-In (line 1161), and so are `gen_ai.retrieval.documents` and `gen_ai.retrieval.query.text` (lines 622-623).
- **PII warning.** `gen-ai-spans.md:259-260` warns: "This attribute is likely to contain sensitive information including user/PII data." (V)
- **JSON on spans.** "If structured attributes are not yet supported on spans in a given language, the corresponding attribute value SHOULD be serialized to JSON string on spans" (`gen-ai-spans.md:1310-1333`, V).
- **External storage.** An "Uploading content to external storage" hook section follows at line 1334 (V).
- **Memory attributes.** The notes for `gen_ai.memory.*` name the env var as an example: "gated by an explicit user opt-in, for example `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`" (`gen-ai-spans.md:1034-1035`, V).
- **`OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` is no longer in the genai repo docs.** grep found no match at c88d504 (V). The last core version with the transition text is v1.41.1, `docs/gen-ai/README.md:8-28` (V). That text says existing instrumentations on v1.36.0 or older "SHOULD NOT change the version … they emit by default". It lists `gen_ai_latest_experimental` as the opt-in value. I infer that the transition plan was dropped or not carried over during the move (I). To confirm, check the genai repo commit history for that paragraph.

### 1h. Python implementation (opentelemetry-python-contrib)

I read the source at tag `opentelemetry-instrumentation-openai-v2==2.4b0`. The `util/opentelemetry-util-genai` files come from the same tag's tree.

- **Default convention version.** The instrumentation "aligns with Semantic Conventions v1.30.0 … and does not capture prompt or completion content" (`openai_v2/__init__.py:42-45`, V).
- **The opt-in flag.** `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` is "Required to access the newer attributes and the span_only / event_only / span_and_event content modes" (`__init__.py:47-50`, V).
- **Content modes.** `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` takes `true` on the legacy path. On the experimental path it takes `span_only`, `event_only` or `span_and_event` (`__init__.py:51-54`, V).
  - The legacy parser is `environ.get(..., "false")` followed by `.lower() == "true"` (`openai_v2/utils.py:56-60`, V).
  - The experimental parser maps the value to `ContentCapturingMode[envvar.upper()]`. An empty or invalid value gives `NO_CONTENT` (`util/genai/utils.py:45-67`, V).
  - The enum is `NO_CONTENT=0`, `SPAN_ONLY=1`, `EVENT_ONLY=2`, `SPAN_AND_EVENT=3` (`util/genai/types.py:29-38`, V).
- **Event emission.** `OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT` defaults to False for NO_CONTENT and SPAN_ONLY. It defaults to True for EVENT_ONLY and SPAN_AND_EVENT (`util/genai/utils.py:73-77`, V).
- **Upload hook.** `OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload` with `OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH=<fsspec-uri>` records the `gen_ai.input.messages.ref` and `gen_ai.output.messages.ref` attributes (`__init__.py:55-61`, V).
- **Version mismatch.** PyPI has `opentelemetry-util-genai` **1.1b0**, released 2026-08-20. The newest `opentelemetry-util-genai==` git tag I found is **0.4b0** (V). So I could not read util-genai 1.1b0 at its own tag. Its PyPI metadata still points to the python-contrib repo (V).

### 1i. MCP conventions

Source: genai repo at c88d504 (V).

- **Attributes** (`model/mcp/registry.yaml`):
  - `mcp.method.name` (line 3)
  - `mcp.session.id` (line 134)
  - `mcp.resource.uri` (line 139)
  - `mcp.protocol.version` (line 147)
- **Spans** (`model/mcp/spans.yaml`):
  - `mcp.client` has kind client (line 18).
  - `mcp.server` has kind server (line 81).
  - The span name is `{mcp.method.name} {target}`, or `{mcp.method.name}` alone (lines 23-26).
- **History.** Core added MCP conventions in v1.39.0 (2026-01-12), #2043 and #2083, `CHANGELOG.md:446` (V).

---

## 2. OpenLLMetry, OpenInference, and the OTel Python packages

### PyPI versions

I read these from the PyPI JSON API. Every call returned HTTP 200 (V).

| Package | Latest version | Upload date |
|---|---|---|
| traceloop-sdk | 0.62.3 | 2026-08-10 |
| opentelemetry-instrumentation-openai (Traceloop) | 0.62.3 | 2026-08-10 |
| opentelemetry-semantic-conventions-ai (Traceloop) | 0.5.1 | 2026-03-26 |
| openinference-instrumentation-openai | 0.1.60 | 2026-09-10 |
| openinference-semantic-conventions | 0.1.38 | 2026-09-15 |
| opentelemetry-instrumentation-openai-v2 | 2.4b0 | 2026-05-01 |
| opentelemetry-util-genai | 1.1b0 | 2026-08-20 |
| opentelemetry-sdk / opentelemetry-api | 1.44.0 | 2026-07-16 |

The GitHub release for traceloop/openllmetry is `0.62.3`, published 2026-08-10 (V).

### OpenLLMetry (Traceloop)

These facts come from tag 0.62.3.

- **README claim.** `README.md:50` says: "Our semantic conventions are now part of OpenTelemetry!" It links to the OTel community `llm-semconv.md` project (V).
- **Mixed attribute names.** `packages/opentelemetry-semantic-conventions-ai/opentelemetry/semconv_ai/__init__.py` has 51 `"gen_ai.*"` string values and 37 `"llm.*"` values (V, grep counts).
  - It also has its own `traceloop.span.kind`, `traceloop.workflow.name` and `traceloop.entity.*` attributes (lines 117-123, V).
- **Old names still emitted.** Lines 145-170 are "Legacy LLM_* aliases … Kept so non-migrated instrumentation packages continue to work". They include `LLM_SYSTEM = "gen_ai.system"`, `gen_ai.prompt`, `gen_ai.completion` and `gen_ai.usage.prompt_tokens` (V). These are pre-v1.37 or deprecated OTel names.
- **Own operation names.** `GenAICustomOperationName` defines `execute_task`, `llm_request` and `vector_db_retrieve` as "agent workflow extensions not yet in the official spec" (lines 380-395, V).

### OpenInference (Arize AI)

These facts come from tag `python-openinference-semantic-conventions-v0.1.38`.

- **Own attribute names.** OpenInference uses its own keys (`semconv/trace/__init__.py`, V):
  - `openinference.span.kind` (line 266)
  - `llm.model_name` (line 72)
  - `llm.provider` (line 88)
  - `llm.input_messages` (line 64)
  - `llm.token_count.prompt` (line 132)
  - `input.value` (line 25)
  - `session.id` (line 268)
- **Span kinds** (lines 599-611, V): TOOL, CHAIN, LLM, RETRIEVER, EMBEDDING, AGENT, RERANKER, UNKNOWN, GUARDRAIL, EVALUATOR, PROMPT.
- **Relationship to OTel.** The README calls OpenInference "complementary to OpenTelemetry" (`README.md:13`, V).
- **Converter package.** `@arizeai/openinference-genai` on npm is at 0.3.9, released 2026-09-15 (V). It converts OTel GenAI attributes to OpenInference attributes. That is the opposite direction from OTel. Its README warns that "attributes reflect their definition as of October 2025" (V, main@1cea61d).
- **No donation found.** I found no documented migration or donation of OpenInference to OTel (NC: I searched only the README and code for `gen_ai`).

### Collector bridge: genainormalizer processor

- This processor exists in contrib at v0.161.0. Its README says it "rewrites attributes on spans emitted by non-OTel GenAI instrumentation libraries into the OTel GenAI Semantic Conventions" (V).
- Its built-in sources are `openinference` and `openllmetry`. It has a `remove_originals` option (V).
- Stability is **alpha** for traces. It ships in the `contrib` distribution only (`processor/genainormalizerprocessor/metadata.yaml`, V).
- The first commit is 2026-05-06, #48063 (V).

---

## 3. OpenTelemetry Collector

### Releases

All release data comes from the GitHub releases API (V).

| Repo | Latest tag | Date | Previous tag |
|---|---|---|---|
| opentelemetry-collector (core) | v0.161.0 | 2026-09-14 | v0.160.0, 2026-09-02 |
| opentelemetry-collector-contrib | v0.161.0 | 2026-09-15 | v0.160.0, 2026-09-02 |

### OTLP receiver limits

Source: core repo at v0.161.0.

- **Default endpoints.** gRPC listens on `localhost:4317` and HTTP on `localhost:4318` (`receiver/otlpreceiver/factory.go:44,49`, V).
- **gRPC read buffer.** `grpcCfg.ReadBufferSize = 512 * 1024` (line 46, V).
- **gRPC message size limit is 4 MiB when you do not set it.**
  - `NewDefaultServerConfig()` does not set `MaxRecvMsgSizeMiB` (`config/configgrpc/configgrpc.go`, V).
  - The option is applied only `if sc.MaxRecvMsgSizeMiB > 0` (line 558-559, V).
  - With no option, grpc-go applies `defaultServerMaxReceiveMessageSize = 1024 * 1024 * 4` (`grpc/grpc-go` master `server.go:61`, V).
  - Caveat: I read grpc-go at master, not at the version pinned in the Collector's go.mod. The conclusion is I.
- **HTTP body limit.** `defaultMaxRequestBodySize = 20 * 1024 * 1024 // 20MiB`, applied when the value is ≤ 0 (`config/confighttp/server.go:36,313-314`, V).

### Batch processor

- **Defaults.** `defaultSendBatchSize = uint32(8192)` and `defaultTimeout = 200 * time.Millisecond` (`processor/batchprocessor/factory.go:19-20`, V).
- **Stability.** beta for traces, metrics and logs. It ships in the core, contrib and k8s distributions (`metadata.yaml`, V).

### Exporter `sending_queue` defaults

Source: `NewDefaultQueueConfig()` in `exporter/exporterhelper/internal/queue_sender.go:30-49` (V).

| Setting | Default |
|---|---|
| `sizer` | requests |
| `num_consumers` | 10 |
| `queue_size` | 1_000 |
| `block_on_overflow` | false |
| `batch.flush_timeout` | 200 ms |
| `batch.sizer` | items |
| `batch.min_size` | 8192 |

Batching inside the queue is off by default. It turns on when the `pkg.exporterhelper.queueBatchEnabled` feature gate is enabled. That gate is `alpha`, `from_version: v0.158.0`, and references issue #15047 (`exporter/exporterhelper/metadata.yaml:15-19`, V). The exporterhelper README says the same defaults (`README.md:21-46`, V).

### Batch processor deprecation plan

The plan is in the RFC `docs/rfcs/batching-migration.md@v0.161.0`, titled "Migration for `batchprocessor` and exporterhelper batching" (V). The migration table at lines 274-281 sets these phases:

| Phase | Version | What happens |
|---|---|---|
| 1 | v0.158.0+ | A new `queuebatchprocessor` is available. The feature gate is off. |
| 2 | v0.160.0 | `batchprocessor` "prints deprecation warning". |
| 3 | v0.166.0 | `batchprocessor` is removed from the default distribution. The gate moves to Beta, so `batch::enabled: true` by default. |
| 4 | v0.172.0 | The gate becomes stable and is removed. |

- **Plan and code disagree.** At v0.161.0, I found no "deprecat" or "migrat" string in any non-test `processor/batchprocessor/*.go` file or in its README (V, grep). So the Phase 2 warning is either not implemented yet or is emitted from another place (I).
- **Issue #15047** is titled "Resolution: Batching processor and/or connector still needed". It is **closed** and was created 2026-04-01 (V).
- **queuebatchprocessor** has stability **development**. Its distributions list is empty (`processor/queuebatchprocessor/README.md@v0.161.0`, V).

### tail_sampling processor

Source: contrib at v0.161.0.

- **Stability.** beta for traces, with the warning "Statefulness". It ships in the contrib and k8s distributions (`metadata.yaml`, V).
- **Defaults.** Source: `factory.go:29-37` and README lines 57-60 (V).

  | Setting | Default |
  |---|---|
  | `DecisionWait` | 30s |
  | `NumTraces` | 50000 |
  | `NumShards` | 1 |
  | `SampleOnFirstMatch` | false |
  | `SamplingStrategy` | trace-complete |
  | `expected_new_traces_per_sec` | 0 |
  | `decision_wait_after_root_received` | 0s |

- **Policies** (README lines 33-49, V): always_sample, latency, numeric_attribute, probabilistic, status_code, string_attribute, trace_state, trace_flags, rate_limiting, bytes_limiting, span_count, boolean_attribute, ottl_condition, and, not, drop, composite.
- **Other options:** `maximum_trace_size_bytes`, `drop_pending_traces_on_shutdown`, `decision_cache`, and the `span-ingest` strategy (V).
- **Memory.**
  - `num_traces` is the "Number of traces kept in memory" (line 59, V).
  - The FAQ (lines 599-603) says high values of `sampling_trace_dropped_too_early` mean load is too high. Raising `num_traces` helps "at the expense of increased memory usage" (V).
- **Scaling.** "All spans for a given trace MUST be received by the same collector instance" (line 18, V). The scaling section (line 578+) recommends two layers of collectors, with the loadbalancing exporter in the first layer (V).
- **Trace state.** The feature gate `processor.tailsamplingprocessor.usetracestate` is alpha and off by default. It reads and writes the `rv` and `th` values in tracestate (line 348, V).

### loadbalancing exporter

- **Stability.** beta for traces and logs, alpha for metrics (V).
- **Routing keys.** The allowed values are `service`, `traceID`, `metric`, `resource`, `streamID` and `attributes` (README line 24, V).
- **Default routing.** "If no `routing_key` is configured, the default routing mechanism is `traceID` for traces" (line 35, V).

### probabilistic_sampler processor

- **Stability.** beta for traces and alpha for logs. It ships in the core, contrib and k8s distributions (V).
- **Modes.** There are three: hash seed, proportional and equalizing. The README says "All modes are consistent." Hash seed is the default mode (README lines 123-182, V).

### Redaction options

| Component | Stability | Key facts | Label |
|---|---|---|---|
| redaction processor | beta for traces, alpha for logs and metrics; contrib and k8s only | `allowed_keys` "is designed to fail closed". An empty `allowed_keys` removes all span attributes. `allow_all_keys` disables that list. `blocked_values` is a list of regexes whose matches are masked. The README also lists `blocked_key_patterns`, `hash_function`, `redact_all_types` and `summary` (`debug`, `info`, `silent`), at README lines 60-111. | V |
| transform processor (OTTL) | beta for traces, metrics and logs; development for profiles | Its warnings include "Unsound Transformations". The OTTL functions `replace_pattern` (line 437), `replace_all_patterns` (391), `delete_key` (128), `delete_matching_keys` (145), `keep_keys` (309), `truncate_all` (508) and `SHA256` (2476) are documented in `pkg/ottl/ottlfuncs/README.md`. | V |
| attributes processor | beta; core, contrib and k8s | Its actions include `delete` and `hash`. The README describes `hash` as "Hashes (SHA1) an existing attribute value" (lines 31-32). | V |

**GenAI content filtering in the Collector.** A code search for `gen_ai.input.messages` in contrib finds only the genainormalizer processor. I found no documented GenAI content-redaction recipe (I; the code search index is at main, not at the tag).

---

## 4. Head sampling in SDKs

Source: opentelemetry-specification, latest release **v1.61.0**, published 2026-09-14 (V).

- **Default sampler.** `OTEL_TRACES_SAMPLER` defaults to `"parentbased_always_on"` (`specification/configuration/sdk-environment-variables.md:119`, V).
- **Known values** (lines 135-143, V):
  - `always_on`
  - `traceidratio`
  - `parentbased_always_on`, which means `ParentBased(root=AlwaysOnSampler)`
  - `parentbased_traceidratio`
  - `parentbased_jaeger_remote`
  - `jaeger_remote`
  - `xray`
- **Sampler status in `trace/sdk.md`** (V):
  - `TraceIdRatioBased` is **Stable** (line 432-434).
  - Its "Compatibility warnings" subsection is Development (line 474).
  - `ProbabilitySampler` is **Development** (line 505-507).
  - `ComposableSampler` sits under a Development section (line 631-649).
- **TraceState probability sampling.** `trace/tracestate-probability-sampling.md` has **Status: Development** (line 8, V). `trace/tracestate-handling.md` is also Development (line 7). That file says: "The OpenTelemetry TraceState `th` sub-key defines a sampling threshold". The `th` value has "between 1 and 14 lowercase hexadecimal digits" (lines 107-110, V).

---

## 5. Local backends for offline labs

All of these run locally at no cost.

- **Jaeger v2.21.0** was released 2026-09-14 (GitHub API, V).
  - Docker Hub has `jaegertracing/jaeger:2.21.0` at 54.8 MB compressed for amd64, pushed 2026-09-15 (V).
  - The all-in-one config uses `memory: max_traces: 100000` (`cmd/jaeger/internal/all-in-one.yaml@v2.21.0:35-39`, V).
  - The same config also enables an `ai: mcp: {}` extension that serves "Jaeger MCP tools /api/ai/mcp/" (lines 31-33, V).
  - The UI is on port 16686 (`cmd/jaeger/README.md:13`, V).
- **grafana/otel-lgtm v0.33.0** was released 2026-09-11 (V).
  - The image is 906.3 MB compressed for amd64 (Docker Hub, V).
  - The Dockerfile at the tag bundles Grafana v13.2.1, Prometheus v3.14.0, Tempo v3.0.3, Loki v3.7.7, Pyroscope v2.3.0, OTel Collector v0.160.0 and OBI v0.13.0 (`docker/Dockerfile:3-15`, V).
  - The README says the image is "intended for development, demo, and testing environments" (V).
- **Collector images.** `otel/opentelemetry-collector-contrib:0.161.0` is 112.8 MB for amd64 (V). The core `otel/opentelemetry-collector` nightly image is 37.4 MB (V). I did not check the size of the core 0.161.0 tag (NC).
- **debug exporter.** Stability is **alpha** for traces, metrics, logs and profiles, with the warning "Unstable Output Format" (`exporter/debugexporter/metadata.yaml@v0.161.0`, V). `verbosity` defaults to `basic`; the other options are `normal` and `detailed` (README line 27, V).
- **file exporter.** Stability is alpha for traces, metrics and logs, and development for profiles. It ships in core, contrib and k8s (contrib `exporter/fileexporter/metadata.yaml@v0.161.0`, V).

---

## Could not verify

1. **Genai repo release and schema URL.** The repo has no release, so there is no versioned schema URL. The README says "TODO".
2. **The exact commit that moved the files.** I know only that core v1.42.0 shipped the move (#3696). I did not open issue #3696.
3. **`opentelemetry-util-genai` 1.1b0 source.** No matching git tag exists, so I could not read it at its own version. The 2.4b0 tag's util-genai source may differ from 1.1b0.
4. **The Phase 2 batchprocessor deprecation warning.** The RFC plans it for v0.160.0, but I did not find it in the v0.161.0 code.
5. **grpc-go 4 MiB default at the Collector's pinned grpc-go version.** I checked grpc-go master only.
6. **OpenInference donation to OTel.** I found no documented donation or migration. I did not read the OTel community project pages.
7. **What OpenLLMetry emits at runtime.** I checked only the constants file. I did not run any instrumentation.
8. **Jaeger v1 end-of-life date.** It is not in the Jaeger README at v2.21.0.
9. **Uncompressed image sizes.** Docker Hub gives compressed sizes only.
10. **Bucket boundaries for `gen_ai.invoke_agent.inference_calls` and `tool_calls`, and for MCP metrics.** I did not copy them.

**Summary:** The GenAI conventions moved to the untagged `semantic-conventions-genai` repo in core v1.42.0 and are all still Development. Collector v0.161.0 defaults are verified in source. The planned batch processor deprecation warning is not visible in the v0.161.0 code.
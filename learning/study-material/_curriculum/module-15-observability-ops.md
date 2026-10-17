# Module 15: Observability and reliability operations

Research date: 2026-09-25. Topic: `observability-ops`. Status: research dossier, not course material. Reviewed on 2026-09-25 by an independent reviewer. Section 10 lists every correction.

Module question: **Quality dropped and no alert fired. What should have been recorded at the time?**

## How this dossier was built

- **Inputs.** Two research reports written on 2026-09-25 in `scratchpad/reports/`: `research_observability-ops_otel.md` and `research_observability-ops_incidents.md`. Below they are the OTel report and the incidents report. Both re-checked the three older raw reports of 2026-09-17 and wrote a corrections table.
- **Older raw reports.** `_curriculum/raw-research/module-15-otel-genai-semconv-collector.md`, `module-15-observability-platforms.md` and `module-15-provider-incidents-gamedays.md`. This dossier uses a raw claim only when a new report marked it verified. Almost all of `module-15-observability-platforms.md` was not re-checked. So its vendor facts are not used here. Section 8, gap 7.
- **Other inputs.** The Module 15 brief in `_curriculum/README.md`, lines 308 to 322. The rules in `scratchpad/briefs/BRIEF_research.md`, `research-method.md` and `writing-style.md`. The structure of `_curriculum/module-10-memory.md`.
- **Path short names.**
  - `RO/` means `scratchpad/research_observability-ops/`.
  - `OT/` means `RO/otel/`. `G/` means `OT/src/genai/`, the GenAI conventions repository at commit `8ffdf568e1b4391a99adb081db16e8102e36918e`.
  - `UG/` means `OT/src/pygenai/util/opentelemetry-util-genai/`, the Python helper at tag `opentelemetry-util-genai==1.2b0`.
  - `COL/` means `OT/collector/`, Collector files at `v0.161.0`.
  - `IN/` means `RO/incidents/`. `IN/src/` holds the saved pages. `IN/proto/` holds the SLO prototype.
  - `M1/` means `study-material/inference-internals/`. `D15/` means `scratchpad/dossier_m15/`, the dossier author's notes.
- **Work done for this dossier.** No lab ran. No URL was fetched. The dossier author did four read-only things:
  1. Re-grepped 81 anchors of section 4 in their saved files. Script `D15/anchor_check.py`, output `D15/anchor_check.txt`. **81 of 81 match.** Three needles first failed because the report quoted a value that the code builds from a constant. The facts held. Section 7, rows d and f, give the corrected evidence.
  2. Recomputed every arithmetic claim. Script `D15/recompute.py`, output `D15/recompute.txt`. One source error was found: the Google SRE Workbook's "1,000x" should be 100x. Section 7, row k.
  3. Grepped `^## ` in `M1/*.md`, `eval-engineering/*.md` and `agent-evals/*.md` on 2026-09-25 for the overlap table.
  4. Checked every OTel line in the published Module 1 against the saved sources at `8ffdf568`. Section 2.4 lists the stale lines.
- **Labels.** Every claim is **verified**, **verified by run**, **inferred** or **not checked**. A verified claim names its file and line, or its table. "Verified by run" means a research agent ran a script on 2026-09-25 on the learner's Apple arm64 Mac, and the output file is named. An inferred claim names its basis and the check that would confirm it. **Vendor claim** marks a number a company published about its own product.
- **Terms used in the whole dossier.**
  - **Span**: one timed operation in a trace, with attributes. A **trace** is the tree of spans for one request.
  - **Semantic conventions**: the OpenTelemetry list of standard names for attributes, metrics, events and span types. The GenAI conventions cover model calls, agents, tools and retrieval.
  - **Development status**: the lowest OpenTelemetry stability level. A name at this level can change or disappear in any commit.
  - **Collector**: the OpenTelemetry service that receives, processes and exports telemetry.
  - **Tail sampling**: the Collector keeps or drops a whole trace after it has seen its spans.
  - **Judge**: a model that scores an answer as pass or fail. **TPR** is the share of truly good answers the judge passes. **TNR** is the share of truly bad answers the judge fails.
  - **Corrected pass rate**: the true pass rate estimated from the judged rate with TPR and TNR. Module 11 section 3.5 names it the Rogan-Gladen estimator.
  - **SLO**: service level objective, a target share of good events over a period. The **error budget** is 1 − SLO.
  - **Burn rate**: the observed bad share divided by the error budget. Burn 1 uses the budget exactly over the period.
  - **MWMBR**: multiwindow, multi-burn-rate alerting, from the Google SRE Workbook. An alert fires when a long and a short window both exceed a burn threshold.
  - **Quality incident**: output got worse while the service stayed up.

---

## 1. What this module is for

Module 1 teaches the run record, the cost record and quality SLOs for one call. Module 11 teaches how to validate a judge. Module 12 teaches online evals and drift probes. This module covers the path in between. It covers what the trace pipeline carries, which names the standard gives, how a judged quality SLO alerts, and what the incident path does after the alert.

The short answer: **record, on every request, which change served it, and join the judge's score to that request.** The three published quality postmortems checked here were found by users. In each one, the team could not quickly connect the drop to a change.

| Part of the question | Short answer | Where |
|---|---|---|
| Why no alert fired | Pre-launch evals missed the drop in all three postmortems. A provider status page rarely names a quality incident, and posts it after the fix. A standard page tier cannot fire at a loose quality SLO | 4.7, 4.9, 4.10 |
| What should have been recorded | The version of every part that can change: model as returned, prompt, app config, harness, retrieval index and top-k ids, tool call ids, judge model and judge prompt. Plus a timestamped change log | 4.8, 4.3, 4.2 |
| Under which names | The GenAI conventions name the prompt, the model, tools, retrieval, the conversation and judge scores. Every name is at Development status. There is no name for cost, the judge's identity or the sampling decision | 4.1, 4.2 |
| How the record survives the pipeline | The privacy default drops retrieval ids. A judge score joins only when it is parented to the scored span. The judge score is a log record, so the tail sampler never sees it | 4.3, 4.4, 4.6 |
| How a judged SLO should alert | Burn on the corrected rate, not the raw judged rate. Set tiers the SLO can reach. Require a minimum sample count per window, and alert when the judged sample count falls below it | 4.10, 4.11, 4.13 |
| What the runbook checks first | The judge. A judge change raises the same alert as a real drop | 4.12 |

Summary: a quality drop is diagnosable only when each request carries the versions that served it, and the score is joined to that request.

## 2. Scope

### 2.1 In scope

- The OpenTelemetry GenAI conventions at commit `8ffdf568`: where they live, their status, and the names that matter for a quality incident.
- How an agent trajectory appears in a trace.
- The privacy defaults for content, and what they drop.
- How a judge score joins a trace.
- The Collector pieces for this pipeline at v0.161.0: tail sampling, load balancing, redaction, batching.
- A quality SLO when correctness is judged: burn tiers, judge correction, samples per window, judge drift.
- Published quality incidents: how they were detected, and what record was missing.
- Provider status pages as a signal for quality.
- A quality runbook and game-day scenarios.

### 2.2 Out of scope, and the owner of each item

| Topic | Owner |
|---|---|
| The run record for one call, the four attribution axes, record size and sampling cost | Module 1, `inference-internals-phase-05b-observability.md` "## 5.5 — The run record (what to store, under which names)" |
| The cost record, token classes, and the missing cost attribute | Module 1, `phase-03a-caching.md` "## 3.1", and `phase-03b-routing-alerting.md` "## 3.5" |
| Quality SLOs, the four indicators, the burn-rate table 5-8 and its arithmetic | Module 1, `phase-05b` "## 5.4 — SLOs for a thing that can be up, fast, and wrong", lines 112 to 153 |
| The Anthropic 2025 postmortem timeline | Module 1, `phase-05b` "## 5.6 — Fallbacks (the pattern you will reach for, and usually should not)", lines 498 to 515. Also cited in Module 12 section 5.4 |
| The assumption under the correction: TPR and TNR must not change. Fiedler's warning on shared calibration | Module 11, `eval-engineering-phase-03-validate-judge.md` "## 3.5", lines 714 to 716 |
| The judge prompt as part of the judge | Module 11, `eval-engineering-phase-02-judges.md` "## 2.4 — The judge prompt is part of the judge" |
| A score belongs to model, harness, tasks and grader | Module 12, `agent-evals-phase-03-reliability.md` "## 3.3 — A score belongs to model, harness, tasks and grader" |
| A check must fail when the eval does not run | Module 11, `eval-engineering-phase-06-gates.md` "## 6.3 — A gate must fail when the eval does not run" |
| An online score arrives after the response | Module 12, `agent-evals-phase-05-online.md` "## 5.3 — An online eval cannot stop a refund" |
| Declaring a quality incident, triage by recorded field, rollback of a prompt or model, the quality postmortem | Module 1, `phase-06b-incidents-review.md` "## 6.3 — When the failure is "quality dropped"" |
| Judge TPR and TNR, and the correction formula | Module 11, `eval-engineering-phase-03-validate-judge.md` "## 3.1" and "## 3.5" |
| Online eval sample rates, judge cost per trace | Module 12, `agent-evals-phase-05-online.md` "## 5.1" and "## 5.2" |
| Judge change against serving change, drift probe sets | Module 12, `agent-evals-phase-05-online.md` "## 5.4 — Scores move when the provider or the judge changes" |
| Per-tenant cost attribution and budgets | Module 14 |
| Retention and deletion duty for captured content | Module 18 |

### 2.3 Overlap with built modules

Headings were read with `grep -n '^## '` on `M1/*.md`, `eval-engineering/*.md` and `agent-evals/*.md` on 2026-09-25. Subsection headings of `phase-05b`, `phase-06b` and `agent-evals-phase-05-online.md` were also read.

| Built heading | What it owns | What this module adds |
|---|---|---|
| Module 1, "5.4 — SLOs for a thing that can be up, fast, and wrong" | The burn table for 99.9%, the one-twelfth short window, a quality SLI as a share that reaches a threshold | Why the page tiers cannot fire at a 95% SLO, 4.10. Burn on the corrected rate, 4.11. Samples per window, 4.13. Do not re-teach table 5-8 |
| Module 1, "5.5 — The run record (what to store, under which names)", subsections "Attribution: four axes, and only three have attribute names", "What to record, and what it costs", "What to sample, and the sampling trap", "The minimum useful record" | Fields for one call, TTFT names, record size, head sampling | The trace-level join: tool call ids, retrieval ids under the privacy default, the evaluation event, the trajectory, tail sampling. 4.3 to 4.6. Link 5.5 and do not repeat its field list |
| Module 1, "5.6 — Fallbacks" | The Anthropic 2025 postmortem timeline and quotes | Only the detection facts and the missing record, 4.7 and 4.8 |
| Module 1, "6.3 — When the failure is "quality dropped"" | Severity, roles, triage by recorded field, `incident_drill.py`, rollback, quality postmortem sections | The step before triage: check the judge, 4.12. The alert rule that starts the incident, 4.10 to 4.13. Link 6.3 for everything after the alert |
| Module 11, "3.1 — A judge is a classifier: report TPR and TNR" and "3.5 — Correct the pass rate, and watch its spread" | The correction and its spread. Also, at lines 714 to 716, the assumption that TPR and TNR stay the same, with Fiedler's warning | Its use inside an alert rule, 4.11. The effect of a judge change on a burn-rate alert, 4.12. Link 3.5 for why the correction fails, and do not re-teach it |
| Module 11, "2.4 — The judge prompt is part of the judge" | A prompt wording change moves the judge's TPR | Why the judge prompt version is a field on each request, 4.8 and 4.12. Link 2.4 |
| Module 11, "6.3 — A gate must fail when the eval does not run" | A CI gate that passes with no eval behind it | The same failure in an alert rule: no judged samples means no alert, 4.13. Link 6.3 |
| Module 12, "3.3 — A score belongs to model, harness, tasks and grader" | A score depends on every part of the setup | The same list as fields on each production request, 4.8. Link 3.3 and do not re-teach it |
| Module 12, "5.3 — An online eval cannot stop a refund" | An online score arrives after the response | The late score against tail sampling, 4.6. Link 5.3 |
| Module 12, "5.1 — The drop and the judge's TPR and TNR set a sample floor" | Sample size to see a drop | Samples per alert window, 4.13. Link 5.1 for sizing |
| Module 12, "5.4 — Scores move when the provider or the judge changes" | Judge change and serving change look alike. Probe sets tell them apart | The same effect on a burn-rate alert, 4.12. Link 5.4 for probes |
| Module 12, "4.4 — Thumbs find failures, they do not measure quality" | User feedback as a signal | 4.7 uses the fact that users found every incident. Link 4.4 |

### 2.4 Published Module 1 lines made stale by the OTel change. For the learner to decide

Module 1 is built. This dossier does not edit it. The GenAI conventions moved to `open-telemetry/semantic-conventions-genai`. The head is now commit `8ffdf568`, dated 2026-09-22, and it made a breaking change. Each line below was checked against the saved sources at that commit.

| # | Module 1 line | What it says | What is true at `8ffdf568` | Label | Decision for the learner |
|---|---|---|---|---|---|
| 1 | `M1/REVIEW.md:25` | `gen_ai.prompt.name` and `gen_ai.prompt.version`: "Neither exists in the GenAI semantic conventions" | Both exist, `G/model/gen-ai/registry.yaml` lines 999 and 1004. The review row is stale. The rest of the row holds: `run_recorder.py` emits neither, 0 grep hits | Verified | Close review item 8 as "attributes exist", or keep only its code half |
| 2 | `M1/inference-internals-phase-03b-routing-alerting.md:496` | "At a commit dated 2026-09-10 … All 118 attributes have development stability" | The pin is older than head. Commit #374 on 2026-09-22 removed `gen_ai.client.token.usage`. "No cost attribute" still holds, 0 hits for `cost` in the registry | Verified for the commit and the cost claim | Re-pin to `8ffdf568`, or keep the old pin with its date |
| 3 | `M1/inference-internals-phase-03a-caching.md:648` | "all 118 attributes have development stability" | Development status holds. The OTel report's inventory counts 82 attributes at `8ffdf568`, `OT/spec_inventory.json`. The two counts use different methods. The dossier author could not reproduce 118. The reviewer counted `- key:` lines in `model/*/registry.yaml`: 82 at `8ffdf568` and 82 at `c88d504`. That method does not give 118 either | Development: verified. Count: not checked | Drop the count, or re-count with one stated method |
| 4 | `M1/inference-internals-phase-03a-caching.md:649` and `phase-03b-routing-alerting.md:498` | "Open pull request 443 proposes `gen_ai.usage.cost.amount` … Use those names now." | PR 443 still shows "Status: Open" on the page saved 2026-09-25, `OT/pr443.html`. The names are in no spec state, `OT/m1_check.txt`. Module 1's own code uses `app.gen_ai.cost_usd`, `M1/code/phase05_operations/run_recorder.py:267`. The OTel report advises a local namespace, 4.2 | Verified | Choose one rule for the course. Section 7, row g |
| 5 | `M1/inference-internals-phase-05b-observability.md:338` | The prompt attributes "are defined in `model/gen-ai/registry.yaml` at commit `c88d504`, checked on 2026-09-17" | True at that commit. They still exist at `8ffdf568`, at lines 999 and 1004 | Verified | Optional re-pin. Low risk |

Lines checked and still true at `8ffdf568`. They need no decision.

- `phase-05b:219-221`, "an inference span with 46 attributes. Only two are required". The inference table in `G/docs/gen-ai/gen-ai-spans.md` lines 37 to 112 has 46 rows. Two are `Required`: `gen_ai.operation.name` and `gen_ai.provider.name`. Verified by count.
- `phase-05b:236-237` and `:246`. The TTFT names and units hold, `G/model/gen-ai/registry.yaml:270-276`. The `time_per_output_chunk` buckets start at 0.01 s and double, `G/docs/gen-ai/gen-ai-metrics.md:292`. Verified.
- `phase-05b:253-258`. The conformance report `G/reference/reports/inference-span.md` still lists `(none)` for `gen_ai.response.time_to_first_chunk` at line 43, one library for `gen_ai.request.stream` and `gen_ai.request.temperature` at lines 23 and 38, and 12 libraries for `gen_ai.response.finish_reasons` at line 40. Verified. The "of 13" total is not checked.
- `phase-03a:93-100`, detailed token counts are subsets of the total. `G/model/gen-ai/registry.yaml:292`. Verified.
- `phase-05b:384`, "the default export batch is 512 spans". This is the SDK batch span processor default, `OT/spec_sdk_env_v1.61.0.md:161`. Verified. The "4 MiB per request" Collector limit is not checked.
- Module 1 never names `gen_ai.client.token.usage`. `grep -rn 'token\.usage'` over `M1/` returns 0 lines. So #374 breaks no Module 1 line. Verified.

---

## 3. Sources, with dates, tags and commits

### 3.1 Primary sources

All were fetched by the research agents on 2026-09-25 and saved. HTTP 200 unless stated. None is peer reviewed unless stated.

| Source | Org | Version, tag or commit | Date of that version | Saved as | Label and notes |
|---|---|---|---|---|---|
| GenAI semantic conventions repository | OpenTelemetry | commit `8ffdf568e1b4391a99adb081db16e8102e36918e`. No tag. No release | 2026-09-22T06:40:29Z | `G/` tarball, `OT/commit_8ffdf568.patch`, `OT/genai_commits.atom` | Verified. Every name is `development`. The commit message: "Fix usage metrics to provide meaningful aggregation and break down by modality, reasoning, cache usage (#374)" |
| The same repository, the head in the raw report | OpenTelemetry | commit `c88d504`. It is two commits before `8ffdf568`. Commit `cc07f72`, "Lock file maintenance (#528)", 2026-09-21, sits between them | 2026-09-16 | `OT/src/genai_c88d504/` | Verified in `OT/genai_commits.atom` and in a fresh fetch of the same feed by the reviewer on 2026-09-25. Used to show what #374 removed |
| Core semantic conventions | OpenTelemetry | tag `v1.44.0`. GenAI moved out in `v1.42.0` | v1.44.0 on 2026-08-04T20:00:58Z. v1.42.0 on 2026-06-12T21:03:17Z | `OT/src/core/`, `OT/rel_page_v1.42.0.html`, `OT/rel_page_v1.44.0.html` | Verified. `src/core/docs/gen-ai/README.md:5` is a "Moved" stub |
| opentelemetry-python-genai | OpenTelemetry | tag `opentelemetry-util-genai==1.2b0` | PyPI upload 2026-09-24 | `UG/`, `OT/pypi/` | Verified. PyPI project links still point to `opentelemetry-python-contrib` |
| Collector core and contrib | OpenTelemetry | `v0.161.0` | core 2026-09-14, contrib 2026-09-15 | `COL/` | Verified. Files read: tail sampling, load balancing, redaction, attributes, transform, batch, queue batch, exporter helper, genai normalizer |
| OTel specification | OpenTelemetry | `v1.61.0` | 2026-09-14 | `OT/spec_sdk_env_v1.61.0.md` | Verified for the SDK environment variables only |
| PR #443 "Add per-operation cost conventions (gen_ai.usage.cost.*)" | OpenTelemetry, author elang2 | open on 2026-09-25 | first patch 2026-08-08 | `OT/pr443.html`, `OT/pr443.patch` | Verified: page badge "Status: Open" |
| "A postmortem of three recent issues" | Anthropic | n/a | 2025-09-17 | `IN/src/anth_2025_postmortem.txt` | Vendor post. Verified quotes |
| "An update on recent Claude Code quality reports" | Anthropic | n/a | 2026-04-23 | `IN/src/anth_2026_april23.txt` | Vendor post. Verified quotes |
| "Sycophancy in GPT-4o" and "Expanding on what we missed with sycophancy" | OpenAI | n/a | 2025-04-29 and 2025-05-02 | `IN/src/oai_syco1_browser.txt`, `oai_syco2_browser.txt` | Vendor posts. HTTP 403 to curl. Read with a browser tool. Key lines copied |
| Claude status incidents `h26lykctfnsz`, `72f99lh1cj2c`, `4q9qw2g0nlcb`, `4k5y2v7rx9hb` | Anthropic | n/a | 2025 | `IN/src/anth_inc_*.txt` | Verified windows and post times |
| Claude status `history.json` pages 1 to 6 | Anthropic | n/a | Oct 2025 to 2026-09-22 for pages 1 to 4 | `IN/src/anth_history_p*.json` | Verified raw data. Class counts are a keyword estimate |
| OpenAI status `history.rss` and `api/v2/incidents.json` | OpenAI | n/a | 2026-06-26 to 2026-09-24 | `IN/src/oai_rss.txt`, `oai_incidents_json.txt` | Same as the row above |
| OpenAI "Unexpected responses from ChatGPT" | OpenAI | n/a | 2024-02-20 | `IN/src/oai_feb2024.txt` | Verified cause and timeline |
| Google SRE Workbook, "Alerting on SLOs" | Google | book, edition year not checked | not checked | `IN/src/sre_alerting.txt` | Verified text. One arithmetic error on the page, section 7 row k |
| Google SRE Workbook, "Incident Response" | Google | same | not checked | `IN/src/sre_incident.txt` | Verified DiRT text |
| AWS Well-Architected REL12-BP05 and Agentic AI Lens AGENTREL06-BP03 | AWS | current page | fetched 2026-09-25 | `IN/src/aws_rel12bp05.txt`, `aws_agentrel06bp03.txt` | Verified. Both cover availability, not quality |
| LiteLLM `litellm/proxy/route_llm_request.py` | BerriAI | tag `v1.101.0`. Latest on PyPI is 1.102.1, uploaded 2026-09-23 | 2026-09 | `IN/src/litellm_route_tag.html` | Verified lines 19 to 28 and 187 to 212 |
| "How to Correctly Report LLM-as-a-Judge Evaluations", arXiv 2511.21140 | Lee et al., preprint | v4. The saved page says "last revised 31 May 2026 (this version, v4)". v1 was 2025-11-26 | 2026-05-31 | `IN/src/arxiv_2511_21140.txt` | Abstract only. Module 11 section 3.5 already cites it |
| "Bias and Uncertainty in LLM-as-a-Judge Estimation", arXiv 2605.06939 | James Fiedler, preprint | v1 | 2026-05-07 | `IN/src/arxiv_2605_06939.txt` | Abstract only in this dossier. Module 11 section 3.5, lines 632 and 714 to 716, already cites it |

### 3.2 What changed recently

| Date | Change | Source | Why it matters |
|---|---|---|---|
| 2025-04-24 to 25 | GPT-4o update rolled out in ChatGPT without an announcement | `IN/src/oai_syco2_browser.txt` | A hosted model changed behind the same product name |
| 2025-08-25 | Core v1.37.0 renamed `gen_ai.system` to `gen_ai.provider.name` | `OT/src/core/CHANGELOG.md:595` | Old tutorials still teach the old name |
| 2025-09-17 | Anthropic postmortem of three quality bugs | `IN/src/anth_2025_postmortem.txt` | The missing record: which change served the request |
| 2025-10-29 | Core v1.38.0 added the `gen_ai.evaluation.result` event | `OT/src/core/CHANGELOG.md:536` | A judge score can be attached to a span |
| 2026-02-19 | Core v1.40.0 added the sampling-relevant flag | `OT/src/core/CHANGELOG.md:359` | Some attributes are known when the span starts |
| 2026-04-23 | Anthropic Claude Code quality postmortem: effort default, thinking cache, prompt length limit | `IN/src/anth_2026_april23.txt` | A harness and prompt incident. The API was not affected |
| 2026-04-28 | Core v1.41.0 added `gen_ai.response.time_to_first_chunk` and the client TTFT metric | `OT/src/core/CHANGELOG.md:248, 262` | Client TTFT has a standard name, in seconds |
| 2026-06-12 | Core v1.42.0 moved GenAI to its own repository | `OT/src/core/CHANGELOG.md:118`, `OT/rel_page_v1.42.0.html` | Pin a commit. There is no tag |
| 2026-07-09 | util-genai 1.0b0 removed `OTEL_SEMCONV_STABILITY_OPT_IN` | `UG/CHANGELOG.md:282-285` | Python emits the experimental names by default |
| 2026-09-16 | GenAI #518 allowed the conversation id on `execute_tool` spans | `G/docs/gen-ai/gen-ai-spans.md:1157` | A tool call can join its conversation |
| 2026-09-22 | GenAI #374 replaced `gen_ai.client.token.usage` and `gen_ai.token.type` | `G/changelog.d/374.breaking.md` | Dashboards on the old metric break when instrumentations follow |
| 2026-09-24 | util-genai 1.2b0 and `opentelemetry-instrumentation-genai-openai` 1.2b0 released | `OT/pypi_versions.txt` | They still create the old token metric |

### 3.3 Versions to pin, checked 2026-09-25

| Item | Version | Date | Evidence |
|---|---|---|---|
| semantic-conventions-genai | commit `8ffdf568`, no tag | 2026-09-22 | `OT/genai_commits.atom` |
| semantic-conventions, core | v1.44.0 | 2026-08-04 | `OT/core_releases.atom` |
| opentelemetry-sdk and opentelemetry-api | 1.44.0 | 2026-07-16 | `OT/pypi_versions.txt` |
| opentelemetry-semantic-conventions, Python | 0.65b0 | 2026-07-16 | same |
| opentelemetry-util-genai | 1.2b0 | 2026-09-24 | same |
| opentelemetry-instrumentation-genai-openai | 1.2b0. It continues `opentelemetry-instrumentation-openai-v2` | 2026-09-24 | same |
| Collector core and contrib | v0.161.0 | 2026-09-14 and 2026-09-15 | Atom feeds |
| OTel specification | v1.61.0 | 2026-09-14 | Atom feed |
| LiteLLM | 1.102.1 latest. Source read at v1.101.0 | 2026-09-23 | `IN/src/litellm_pypi.html` |
| Python for both prototypes | system 3.9.6, arm64 | 2026-09-25 | both reports |

---

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Each concept gives its best evidence first, with conditions. Every quote and number in section 4 was re-grepped in its saved file. **81 of 81 anchors match**, `D15/anchor_check.txt`. Every quote is 25 words or shorter.

| Concept | Anchors | Concept | Anchors | Concept | Anchors |
|---|---|---|---|---|---|
| 4.1 | 15 of 15 | 4.6 | 6 of 6 | 4.11 | 4 of 4 |
| 4.2 | 8 of 8 | 4.7 | 7 of 7 | 4.12 | 3 of 3 |
| 4.3 | 6 of 6 | 4.8 | 8 of 8 | 4.13 | 3 of 3 |
| 4.4 | 3 of 3 | 4.9 | 7 of 7 | | |
| 4.5 | 4 of 4 | 4.10 | 7 of 7 | | |

Anchor kinds: 67 presence checks, 6 exact-count checks and 8 file:line checks. The exact-count checks are absences, such as 0 hits for `cost` in the registry.

The reviewer re-checked more than 60 anchors by hand in the saved files on 2026-09-25. The most were in 4.1, 4.2, 4.6, 4.7, 4.8 and 4.9, plus every run number in 4.10 to 4.13. All quotes and numbers match. The corrections are about labels, conditions and one wrong mechanism in 4.6. Section 10 lists them. Three fresh fetches on 2026-09-25 agree with the saved state: the GenAI head is still `8ffdf568`, PR #443 still shows `"state":"OPEN"`, and PyPI still lists `opentelemetry-util-genai` 1.2b0 as the latest version.

### 4.1 The GenAI conventions have no stable name and no release. Pin a commit, and expect a rename to break a dashboard

- **Best evidence, verified.** The GenAI repository has zero releases and zero tags, `OT/genai_releases.atom` and `OT/genai_tags.atom`. The inventory of every attribute, metric, event and span type has 0 rows at `stable`, `OT/spec_inventory.md`. The manifest declares `schema_url: https://opentelemetry.io/schemas/gen-ai-dev/1.42.0-dev`, `G/model/manifest.yaml`.
- **Verified. The move.** Core v1.42.0, released 2026-06-12, says "Move Generative AI semantic conventions to a dedicated repository", `OT/src/core/CHANGELOG.md:118`. Core `docs/gen-ai/README.md` at v1.44.0 is a "Moved" stub.
- **Verified. A rename happened three days before this check.** Commit `8ffdf568` (#374) says "Replace the `gen_ai.client.token.usage` histogram", `G/changelog.d/374.breaking.md`. The replacements are five counters `gen_ai.client.inference.usage.*` and two histograms `gen_ai.client.inference.operation.{input,output}_tokens`, `G/model/gen-ai/token-metrics.yaml`, lines 10 to 104, `instrument: counter` and `instrument: histogram`. The breaking note names only the histograms. The counters come from `G/changelog.d/374.enhancement.md`. Both kinds carry a rule: "instrumentation MUST report billable tokens" when both used and billable counts exist, `token-metrics.yaml:20` and `:95`.
- **Verified. Code lags the spec.** util-genai 1.2b0, released 2026-09-24, creates a histogram named by the constant `gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE`, `UG/src/opentelemetry/util/genai/_instruments.py:94`. Its PyPI description lists "`gen_ai.client.token.usage` histograms", `OT/util_genai_pypi_desc.txt:16`. Inferred: the constant's value is that old name. The constant lives in `opentelemetry-semantic-conventions`, which was not saved. Check: read the constant in that package at 0.65b0.
- **Verified. The opt-in flag is gone in Python.** util-genai 1.0b0 "Removes all code referencing the "OTEL_SEMCONV_STABILITY_OPT_IN" flag", `UG/CHANGELOG.md:282-285`.
- **Verified. Client TTFT has a spec name.** `gen_ai.response.time_to_first_chunk`, a double "measured from request issuance, in seconds", `G/model/gen-ai/registry.yaml:270-276`. Module 1 section 5.5 already teaches it. Link there.
- **What to teach.** Cite the commit SHA next to every name. Put a name-check in CI, such as Lab L1. Treat the metric names as the most likely to move.

### 4.2 The spec has no name for cost, the judge's identity or the sampling decision. Record them under your own namespace, not under `gen_ai.`

- **Best evidence, verified.** The words `cost`, `price` and `judge` each occur 0 times in `G/model/gen-ai/registry.yaml`. The prototype checker reports `gen_ai.cost.usd -> invented: not in spec_names.json`, `OT/proto/run_break.txt`.
- **Verified. The cost PR is still open.** PR #443 proposes `gen_ai.usage.cost.amount`, `.currency` and `.source`, `OT/pr443.patch`. The saved page shows "Status: Open", `OT/pr443.html`.
- **Verified. Sampling has no attribute.** In `G/model/gen-ai/registry.yaml` the word "sampling" occurs only in the `top_p` and `top_k` briefs, lines 120 to 129. The `sampling_relevant: true` flags in `G/model/gen-ai/spans.yaml:263-271` mark attributes known when a span starts. They do not record a decision. The prototype variant `unsampled` reports `sampling_decision MISS`, `OT/proto/run_break.txt`. That MISS shows only the prototype's own rule, so it is not the evidence. The OTel report says the decision lives in the W3C `tracestate` `th` value, which is also at Development status. That spec file was not re-read. Not checked.
- **Verified. Module 1 code already follows the local-namespace rule.** `attrs["app.gen_ai.cost_usd"] = rec.cost_usd`, `M1/code/phase05_operations/run_recorder.py:267`. Module 1 prose says to use the PR names now. Section 2.4 row 4 and section 7 row g.
- **Inferred. Why a local namespace.** A name under `gen_ai.` that the spec does not define can collide with a later spec name that has other semantics. Basis: the PR is open and could change before merge. Check: compare the merged PR, when it merges, with the draft names.
- **What the prototype uses.** `app.cost.usd`, `app.judge.model`, `app.judge.prompt.version`, `app.release.id` and `app.retrieval.doc_ids`, `OT/proto/run_break.txt`.

### 4.3 The privacy default keeps tool call ids but drops retrieval document ids

- **Best evidence, verified.** `gen_ai.retrieval.documents` is `Opt-In` on the retrieval span, `G/docs/gen-ai/gen-ai-spans.md:622`. The document ids sit inside that attribute. `gen_ai.tool.call.id` is "`Recommended` If available." on the `execute_tool` span, line 1158.
- **Verified. The default.** "[Default] Don't record instructions, inputs, or outputs.", `gen-ai-spans.md:1290`. Instrumentations "SHOULD NOT capture them by default", line 1284.
- **Verified. Privacy slowed a real investigation.** Anthropic 2025: "Our own privacy practices also created challenges in investigating reports", `IN/src/anth_2025_postmortem.txt`. Its fix list adds tooling "to better debug community-sourced feedback without sacrificing user privacy". Vendor post. So the record must name the versions and ids without the text.
- **Verified by run.** The prototype variant `default_privacy_no_local_ids` reports `retrieval_ids MISS`, `OT/proto/run_break.txt`.
- **Verified. What remains.** The retrieval span still carries `gen_ai.data_source.id`, which names the index, `gen-ai-spans.md:616`. It does not say which documents came back.
- **Inferred. The fix.** Record the top-k document ids under a local attribute, as the prototype does with `app.retrieval.doc_ids`. Ids are not content, so the privacy rule for text does not require dropping them. Check: confirm with the data owner that ids reveal no content. Module 18 owns that duty.

### 4.4 A judge score joins the trace only if the evaluation event is parented to the scored span

- **Best evidence, verified.** The score is the `gen_ai.evaluation.result` event, `G/model/gen-ai/events.yaml:14`. It "SHOULD be parented to GenAI operation span being evaluated when possible". Otherwise it sets `gen_ai.response.id`.
- **Verified by run.** The prototype variant `orphan_eval` reports `judge_score_linked MISS`, `OT/proto/run_break.txt`.
- **Inferred. The usual failure.** An offline judge job reads stored answers and loses the trace id and span id. The score then cannot be split by prompt version or model. Basis: the event rule above. Check: run a batch judge in Lab L1's shape without the ids.
- **Verified. No judge identity.** The event carries `gen_ai.evaluation.name`, `score.value`, `score.label` and `explanation`. It carries no judge model or judge prompt version, 4.2.

### 4.5 An agent trajectory is the span tree under `invoke_agent`. The spec has no trajectory object

- **Best evidence, verified.** "The LLM call that generates the plan SHOULD be a child of the plan span." Tool or task spans "are typically sibling operations under the same `invoke_agent` span", `G/docs/gen-ai/gen-ai-agent-spans.md:972-976`.
- **Verified. Two agent span types.** A client type for remote agents and an internal type for in-process agents, `gen-ai-agent-spans.md:536-560`, per the OTel report.
- **Verified. Conversation id.** `gen_ai.conversation.id` is Conditionally Required on inference, `invoke_agent` and `invoke_workflow` spans, and "If available" on `execute_tool` since #518, `gen-ai-spans.md:1157`. Instrumentations SHOULD NOT fall back to "a new UUID, a trace identifier, or a hash of request content", `G/model/gen-ai/registry.yaml:439-441`.
- **Inferred. Rebuilding the trajectory.** Order the children of `invoke_agent` by start time. `gen_ai.tool.call.id` links the model's tool-call request to its `execute_tool` span. Check: read one `data.json` under `G/reference/scenarios/`.

### 4.6 The tail sampler sees only spans. A judge score sent as an evaluation event can never keep a trace, however early it arrives

- **Best evidence, verified.** The judge score event is a log record, not a span. The GenAI events page links events to the logs data model, `G/docs/gen-ai/gen-ai-events.md:16`. Core defines an event as "a `LogRecord` with an event name", `OT/src/core/docs/general/events.md:13`. The tail sampling processor handles traces only: `processor.WithTraces`, `COL/contrib__processor_tailsamplingprocessor_factory.go:25`, and `beta: [traces]`, `COL/contrib__processor_tailsamplingprocessor_metadata.yaml:7`.
- **Inferred. The result.** A policy on the judge score cannot read a `gen_ai.evaluation.result` event. When the sampler drops a trace, the score log record can still arrive and point at a span that no longer exists. Basis: the three lines above. Check: Lab L4, with the score sent once as a log record and once as a span attribute.
- **Verified.** "All spans for a given trace MUST be received by the same collector instance", `COL/contrib__processor_tailsamplingprocessor_README.md:18`. Defaults at v0.161.0: `decision_wait` 30 s, `num_traces` 50000 and `sampling_strategy` `trace-complete`, `COL/contrib__processor_tailsamplingprocessor_factory.go:29-36`. The decision caches default to size 0, "the cache is inactive", README lines 66 to 71. So by default the sampler does not remember a decision after it frees the trace.
- **Verified.** The load-balancing exporter's default trace routing key is `traceID`. It is the usual piece in front of tail sampling, `COL/contrib__exporter_loadbalancingexporter_README.md:35`.
- **Inferred. A late score on a span.** If the score is written as a span attribute, the span must arrive within `decision_wait`. An online judge can take longer than 30 s. Basis: the default above. Check: Lab L4. Module 12 section 5.3 owns why an online score arrives after the response.
- **Verified. The spec's answer for content.** If an upload hook is configured, instrumentations "SHOULD invoke it regardless of the span sampling decision", `gen-ai-spans.md:1343-1344`. So content can be stored for a trace the sampler dropped.
- **Verified. No names for the stored references.** The spec says "TODO: document a common approach to record references to externally stored content", `gen-ai-spans.md:1372`. util-genai 1.2b0 builds its own names as the content attribute plus `"_ref"`, for example `gen_ai_attributes.GEN_AI_INPUT_MESSAGES + "_ref"`, `UG/src/opentelemetry/util/genai/_upload/completion_hook.py:42`.
- **What to teach.** Keep the per-request record, 4.8, outside the sampled trace, or keep every trace that a judge will score. Decide which before choosing a sampler. Choose the judge sample before the trace is exported, for example by a flag on the root span, so the sampler can keep it. This last step is inferred and not tested.

### 4.7 In the three published quality postmortems checked, users found the drop. Evals and alerts did not

- **Best evidence, verified.** Anthropic, 2025-09-17: "The evaluations we ran simply didn't capture the degradation users were reporting", `IN/src/anth_2025_postmortem.txt`. Reports were "difficult to distinguish from normal variation in user feedback".
- **Verified.** Anthropic, 2026-04-23: "neither our internal usage nor evals initially reproduced the issues identified", `IN/src/anth_2026_april23.txt`. Scope: Claude Code, the Agent SDK and Cowork. "The API was not impacted."
- **Verified.** OpenAI, 2025-05-02: "our offline evaluations" … "generally looked good", `IN/src/oai_syco2_browser.txt`. "By Sunday, it was clear" the behaviour was wrong, two days after the rollout finished. One human signal existed before launch: "some expert testers had indicated that the model behavior "felt" slightly off", same file. So for OpenAI, a signal existed and did not block the launch.
- **Verified. Users named the cause.** Anthropic 2026: users who "used the /feedback command" are the ones who "ultimately allowed us to identify and fix these problems", `IN/src/anth_2026_april23.txt`.
- **Conditions.** Three vendor posts. Two are model or serving incidents at a provider. One is a harness and prompt incident. None is peer reviewed. The sample is three.
- **What to teach.** A user feedback event linked to the request id is part of the record. Module 12 section 4.4 owns how to read thumbs.

### 4.8 The record that was missing was "which change served this request". Every part that can change needs a version on the request

- **Best evidence, verified.** Anthropic 2025: "we lacked a clear way to connect these to each of our recent changes", `IN/src/anth_2025_postmortem.txt`. The first bug affected "approximately 0.8% of requests made to Sonnet 4".
- **Verified.** Anthropic 2026: three changes, and each "affected a different slice of traffic on a different schedule", `IN/src/anth_2026_april23.txt`. The changes were a default effort change "from high to medium", a thinking-cache bug fixed "in v2.1.101", and a system prompt length limit.
- **Verified.** OpenAI 2025: "We also didn't have specific deployment evaluations tracking sycophancy", and "we didn't proactively announce it", `IN/src/oai_syco2_browser.txt`.
- **Verified. Eval size of a real regression.** "One of these evaluations showed a 3% drop for both Opus 4.6 and 4.7", `IN/src/anth_2026_april23.txt`. Condition: this eval ran after the incident, in ablations "using a broader set of evaluations". It did not run before the release. The post names no eval, size or metric. Conditions not checked.
- **Verified. One change hit several models.** The prompt change "impacted Sonnet 4.6, Opus 4.6, and Opus 4.7", same file. A split by model alone would show the drop on three models at once.
- **Verified. The vendors' own fixes.** Anthropic 2025 will run quality evals "continuously on true production systems", `IN/src/anth_2025_postmortem.txt`. Anthropic 2026 adds "soak periods, a broader eval suite, and gradual rollouts", `IN/src/anth_2026_april23.txt`. Vendor posts. Module 12 section 5.4 owns production probe sets.
- **Inferred. The fields, each tied to an incident.** Synthesis by the incidents report, with one reviewer row, the rollout cohort. No source publishes this list. Module 12 section 3.3 owns the same list for an offline score. Link it.

| Field on each request | Incident that needed it |
|---|---|
| Model id as returned by the provider | OpenAI 2025, silent change |
| App config version: effort, max tokens, thinking settings | Anthropic 2026, effort default |
| System prompt version | Anthropic 2026, length limit |
| Harness or client version | Anthropic 2026, fixed in a client version |
| Retrieval index version and top-k document ids | No source. 4.3 |
| Serving route or region, when returned | Anthropic 2025, wrong server pool |
| Rollout cohort or flag state: canary, percent stage, soak | Anthropic 2026, "gradual rollouts". Inferred. No incident post names this field |
| Judge model, judge prompt version, verdict | 4.12 |
| User feedback event, linked to the request id | 4.7 |
| A timestamped change log of all the above | Anthropic 2025 |

- **Overlap.** Module 1 section 5.5 already records model, prompt and corpus. This module adds config, harness, judge and the change log.

### 4.9 Provider status pages rarely name a quality incident, and they post it after the fix

- **Best evidence, verified raw data, inferred classes.** Anthropic status history, October 2025 to 2026-09-22: 431 incidents. 4 have a quality or output title by keyword, `IN/status_classification_output.txt`. The incidents report judges 1 to 3 of them to be model-output quality. OpenAI status RSS, 2026-06-26 to 2026-09-24: 94 items. The 3 keyword matches are false matches after manual review.
- **Verified. Posted after the fix.** Opus 4.1: "From 17:30 UTC on Aug 25th to 02:00 UTC on Aug 28th". First post "Aug 29, 2025 - 17:02 UTC", `IN/src/anth_inc_h26lykctfnsz.txt`. Recomputed: 95.5 h after onset and 39.0 h after the fix, `D15/recompute.txt`.
- **Verified.** Sonnet 4: "From 08:45 UTC on July 8th to 02:00 UTC on July 10th", first post at the end of the window, `IN/src/anth_inc_4q9qw2g0nlcb.txt`. Haiku 4.5: "Fix has been deployed" in the first post, `IN/src/anth_inc_4k5y2v7rx9hb.txt`.
- **Verified by the reviewer's keyword scan.** No status title in March or April 2026 names the Claude Code effort, thinking-cache or prompt changes of 4.8. The scan read `IN/src/anth_history_p1.json` to `p6.json` for "quality", "effort", "reason", "think", "prompt", "degrad", "output", "intellig" and "response". The 5 hits are about errors, structured outputs, admin endpoints, Vaults and slow completion. A title under another word is not excluded.
- **Conditions.** Titles are not causes. A manual read of all 431 and 94 titles would confirm the counts.
- **What to teach.** Your own judged SLI is the only real-time quality signal. The status page is evidence for the postmortem.

### 4.10 The standard page tiers cannot fire at a loose quality SLO. The maximum burn rate is 1 ÷ (1 − SLO)

- **Best evidence, verified by run and recomputed.** At SLO 0.95 the maximum burn is 1 ÷ 0.05 = 20. The 14.4 tier needs a fail rate above 14.4 × 0.05 = 0.72. The 6 tier needs 0.30, `IN/proto/selftest_output.txt`, `D15/recompute.txt`.
- **Verified. The tiers.** Google SRE Workbook, table 5-8, for 99.9% over 30 days: page 1 h and 5 min at burn 14.4. Page 6 h and 30 min at burn 6. Ticket 3 days and 6 h at burn 1. "make the short window 1/12 the duration of the long window", `IN/src/sre_alerting.txt`.
- **Verified by run.** Moderate drop, true pass 0.98 to 0.90, corrected rate, Google tiers: detected 20 of 20 seeds, median 28h10m, 0 false alarms per day. Only the ticket tier can fire. `IN/proto/main_output.txt`.
- **Verified by run. The trade.** The adapted tiers use a 7-day period: 2% in 1 h at burn 3.36, 5% in 6 h at 1.4, and 10% in 24 h at 0.7. They detected the moderate drop at a median 1h35m. They raised 1.13 false alarms per day and fired 2.3% of the no-drop time. These tiers are the incidents report's proposal. No source recommends them.
- **Recomputed. A condition on the adapted tiers.** They use a 7-day budget, while the SLO in the run is over 30 days. The 24-hour tier fires at burn 0.7, a fail rate of 0.035. That is below the 0.05 budget rate. So this tier fires while the SLO is still met. Teach it as a drift ticket, not as an SLO breach.
- **Verified. Why a "for" duration can stay silent.** The Workbook: "An SLI that fluctuates between missing SLO and passing SLO may never alert", `IN/src/sre_alerting.txt`. A noisy judged SLI fluctuates. Do not add a duration clause to a judged alert.
- **Recomputed.** The deterministic ticket-tier crossing for 0.02 to 0.10 is 27.0 h. The simulated median is 28h10m, `D15/recompute.txt`.
- **Simulated conditions for every run number in 4.10 to 4.13.** SLO 0.95 over 30 days. 1,000 requests per hour. Judge sample rate 0.05, about 50 judged per hour. Judge TPR 0.95, TNR 0.85. True pass 0.98 before the drop. 14 days per run, drop at day 7, 3-day warm-up, 20 seeds. False alarms come from a separate no-drop run. Outcomes are independent draws. Python 3.9.6 on arm64.

### 4.11 Burn on the corrected pass rate. A raw judged SLO can be in breach while true quality is fine

- **Best evidence, recomputed.** Judged pass = 0.95 × 0.98 + 0.15 × 0.02 = 0.934, `IN/proto/main_output.txt` line "expected raw judged pass before drop: 0.9340". The raw fail rate 0.066 is above the 0.05 budget. Raw burn is 1.32 with no drop. The correction recovers 0.98, `D15/recompute.txt`.
- **Verified by run.** The rule "burn MWMBR raw judged (uncorrected)", with all three Google tiers, fired 88.7% of the no-drop time, 3.35 false alarms per day.
- **Verified by run.** A 1-hour threshold at the SLO value, judged pass below 0.95, fired 64.5% of the no-drop time and 14.67 times per day.
- **Link.** Module 11 section 3.5 owns the formula and its spread.

### 4.12 A judge change raises the same alert as a real drop. Check the judge before the app

- **Best evidence, verified by run.** Break-it: at day 7 the judge's TPR falls from 0.95 to 0.80. True quality does not change. The corrected Google-tier alert fired in 20 of 20 seeds, median 10h40m. The adapted tiers fired at a median 0h45m, `IN/proto/break_judge_drift_output.txt`.
- **Recomputed.** The judged pass becomes 0.787. With the stale TPR the corrected pass is 0.796. The corrected fail rate is 0.204, a burn of 4.08. The deterministic ticket crossing is 11.8 h, `D15/recompute.txt`.
- **Inferred, from an abstract only.** Fiedler, arXiv 2605.06939, says shared calibration "can introduce severe bias". Its body was not read for this dossier. Module 11 section 3.5, lines 714 to 716, already teaches the assumption that TPR and TNR stay the same, and cites Fiedler. Link it.
- **Link.** Module 12 section 5.4 owns the judge-change and serving-change split and the probe set. Module 11 section 2.4 owns why a judge prompt edit moves TPR. This module adds only the runbook order: re-judge a fixed labelled set before any rollback.

### 4.13 A short window needs a minimum sample count, and that floor silences the alert when the judge stops. More judged samples buy precision, not detection speed

- **Best evidence, verified by run.** Moderate drop, corrected Google tiers. At 5 judged per hour: median 24h35m, 0.30 false alarms per day. At 200 judged per hour: median 28h15m, 0 false alarms, `IN/proto/main_output.txt`.
- **Recomputed.** At 1,000 requests per hour and 5% sampling, a 5-minute window holds 4.17 judged samples. The standard error of a corrected fail rate at n = 50 is √(0.066 × 0.934 ÷ 50) ÷ 0.8 = 0.044, `D15/recompute.txt`.
- **Verified. The Workbook's warning about synthetic traffic.** If only real users are affected, "the successful artificial requests hide the real user signal", `IN/src/sre_alerting.txt`.
- **What the prototype does.** It requires at least 30 samples in a long window and 10 in an adapted short window. The Google-tier short window needs only 1, `make_burn(..., min_short_samples=1)`, `IN/proto/judged_slo_alerts.py:152`. These floors are the incidents report's choice. Module 12 section 5.1 owns sample sizing.
- **Verified by code reading. A floor makes the alert silent when the judge stops.** When a window holds fewer samples than the floor, the rule returns no alert, `IN/proto/judged_slo_alerts.py:133-137` and `:155-160`. If the judge job fails, or the judge sample rate drops to 0, the quality alert cannot fire. This is one direct answer to "no alert fired".
- **Inferred. The fix.** Add a separate alert on the judged sample count per window, and on the age of the newest score. Basis: the code above. Module 11 section 6.3 teaches the same rule for a CI gate. Check: run L3 with `sample_rate` set to 0 after day 7 and see that no rule fires.

---

## 5. Numbers with conditions

| Number | Conditions | Source | Label |
|---|---|---|---|
| 0 releases, 0 tags, 0 stable names | GenAI repository at `8ffdf568`, 2026-09-25 | `OT/genai_*.atom`, `OT/spec_inventory.md` | Verified |
| 82 attributes, 30 metrics, 3 events, 18 span types | `8ffdf568`. 30 metrics = 22 base plus 8 OpenAI refinements. 18 span types = 13 plus 5 provider refinements. Counted by `OT/extract_spec.py` from the YAML | `OT/extract_run.txt` | Verified by run. Counting method differs from Module 1's 118 |
| 5 counters and 2 histograms replace 1 token histogram | #374, 2026-09-22 | `G/model/gen-ai/token-metrics.yaml` | Verified |
| 46 inference-span attributes, 2 Required, 11 Conditionally Required, 28 Recommended, 5 Opt-In | `G/docs/gen-ai/gen-ai-spans.md` lines 37 to 112 at `8ffdf568` | dossier author count | Verified by count |
| `decision_wait` 30 s, `num_traces` 50000 | tail sampling processor defaults, contrib v0.161.0 | `COL/contrib__processor_tailsamplingprocessor_factory.go:29-36` | Verified |
| batch processor 8192 items and 200 ms | core batch processor defaults, v0.161.0 | `COL/core__processor_batchprocessor_factory.go` | Verified |
| batch processor leaves the default distribution at v0.166.0 | migration plan phase 3 | `COL/core__docs_rfcs_batching-migration.md:278-281` | Verified plan. Not yet happened |
| 512 spans per export batch | SDK batch span processor default, spec v1.61.0 | `OT/spec_sdk_env_v1.61.0.md:161` | Verified |
| Max burn 20, tier fail rates 0.72, 0.30, 0.05 | SLO 0.95, Workbook tiers | `D15/recompute.txt` | Recomputed |
| Adapted burns 3.36, 1.4, 0.7. Fail rates 0.168, 0.07, 0.035 | 7-day period, incidents report proposal | same | Recomputed |
| Judged pass 0.934, raw burn 1.32 | TPR 0.95, TNR 0.85, true pass 0.98, budget 0.05 | same | Recomputed |
| TTD 28h10m, 4h10m, 60h05m | corrected Google tiers. Drops to 0.90, 0.60, 0.94. Simulated conditions in 4.10 | `IN/proto/main_output.txt` | Verified by run |
| TTD 1h35m, 0h25m, 4h45m. 1.13 false alarms per day | adapted tiers, same drops | same | Verified by run |
| 88.7% of no-drop time firing | raw judged Google tiers | same | Verified by run |
| False incident at 10h40m median | judge TPR 0.95 to 0.80, no true change | `IN/proto/break_judge_drift_output.txt` | Verified by run |
| Deterministic crossings 27.0 h, 54.0 h, 4.4 h, 11.8 h | noise-free versions of the same rules | `D15/recompute.txt` | Recomputed. The simulated 60h05m against the deterministic 54 h is not explained |
| 0.8% of Sonnet 4 requests, then 16% at the worst hour | Anthropic 2025, routing bug | `IN/src/anth_2025_postmortem.txt` | Verified. Vendor claim |
| 34, 15 and 4 days from ship to fix | Anthropic 2026, three changes | `IN/src/anth_2026_april23.txt` and `D15/recompute.txt` | Dates verified. Days recomputed |
| "3% drop" on one eval | Anthropic 2026. Eval, size and metric not named | same | Verified quote. Conditions not checked |
| 4 of 431 quality or output titles | Anthropic status, Oct 2025 to 2026-09-22, keyword classifier | `IN/status_classification_output.txt` | Raw data verified. Classes inferred |
| 0 of 94 output-quality items | OpenAI status RSS, 2026-06-26 to 2026-09-24, after manual review of 3 matches | same | Inferred |
| 95.5 h and 39.0 h | Opus 4.1 onset and fix to first status post | `D15/recompute.txt` | Recomputed |
| 100x, not 1,000x | Workbook low-traffic example: 10 requests per hour, 1 failure, 99.9% SLO | `IN/src/sre_alerting.txt`, `D15/recompute.txt` | Recomputed. The page says 1,000x |
| 0.03 s, 8.16 s | prototype run times: name checker self-test, SLO simulation main run | `OT/proto/run_selftest.txt`, `IN/proto/main_output.txt` | Verified by run |

---

## 6. Lab designs

Every lab runs on the learner's Mac: Apple arm64, 14 cores, 26 GB RAM, no Docker, no GPU. No lab needs an API key or a hosted model. Cost is $0 for every lab below. No lab needs the shared retrieval harness.

### 6.1 Built and run on 2026-09-25

| Lab | Script | Saved output | Run time | Download | Self-test | Proves |
|---|---|---|---|---|---|---|
| L1. Span name and diagnosability checker | `OT/proto/agent_trace.py`, `spec_names.json` | `run_good.txt`, `run_break.txt`, `run_selftest.txt` | 0.03 s, `/usr/bin/python3` 3.9.6 | None. Standard library | "selftest: all 17 assertions passed" | 4.1 to 4.5 |
| L2. Spec inventory from the YAML, and a diff across four states | `OT/extract_spec.py`, `OT/compare_states.py` | `extract_run.txt`, `spec_inventory.md`, `compare_states_run.txt`, `names_diff.md` | Not recorded | PyYAML through `uv run --with pyyaml`. Size not measured | None | 4.1 |
| L3. Judged SLO alert simulator | `IN/proto/judged_slo_alerts.py` | `selftest_output.txt`, `main_output.txt`, `break_judge_drift_output.txt` | Self-test 0.05 s. Main 8.16 s | None. Standard library | 12 hand-worked checks, all PASS | 4.10 to 4.13 |

- **L1 prints** five spans of one agent trace, name errors, span-shape problems, eight diagnosability fields and a verdict. Break-its: `invented_names` gives 4 errors. `no_prompt_version`, `orphan_eval`, `default_privacy_no_local_ids` and `unsampled` each give one MISS. **Limits:** it checks names, not types. It checks Required attributes for two span types only. Spans are OTLP-JSON-shaped and were never sent through an SDK or a Collector.
- **L2 break-it:** run it at `c88d504` and see `gen_ai.client.token.usage` return.
- **L3 prints** a table per drop size and alert rule: detected seeds, median TTD, false alarms per day, share of no-drop time firing. Break-it: `--break judge-drift`. Learner task: change `tnr`, `sample_rate` and `slo` in `base_cfg()`, `judged_slo_alerts.py:198`, and predict the TTD first. **Limits:** independent draws, a constant and known judge, a normal approximation for arrival noise.

### 6.2 Designed, not built

| Lab | Where it runs | What it would print | Cost and download | Proves |
|---|---|---|---|---|
| L4. Tail sampling with a judge score | Local `otelcol-contrib` 0.161.0 binary, no Docker. `decision_wait: 5s`, a numeric policy on a judge-score attribute. Three cases: the score as a `gen_ai.evaluation.result` log record, the score as a span attribute sent at 2 s, and the same span sent at 10 s | Which case changes the decision. Expected: only the span at 2 s. The log record reaches a logs pipeline and never the sampler, 4.6. Inferred, not run | $0. Binary size not checked | 4.6 |
| L5. Slice-level drop in L3 | Mac, standard library. Give each simulated request a version field. Drop quality only for one version, first 0.8% of traffic, then 16% | TTD for the global corrected rule against a per-version split rule | $0 | 4.8, 4.10. Gap 2 |
| L6. Offline game days | Mac. A mock provider in Python, or Toxiproxy for network faults. LiteLLM mock parameters only where an admin set `dangerously_allow_mock_testing_request_params` | Per scenario: which alert fired, and which recorded field named the cause | $0. Toxiproxy version not checked | 4.8, 4.12 |

L6 scenarios, from the incidents report. All are its proposal, not a published runbook:

| Scenario | How to inject it offline | What must happen |
|---|---|---|
| Provider errors, 429, latency | mock provider or fault proxy | the availability SLO alerts. The fallback model's quality SLI is watched |
| Silent model change | mock returns a new model id behind the same alias | the version split shows the change |
| Prompt regression | ship a prompt with an added length limit | the per-prompt-version split names it. Roll back |
| Retrieval index corruption | drop or shuffle 20% of chunks in a copy of the index | top-k overlap on a fixed query set falls |
| Judge drift | change the judge prompt or model | re-judging a fixed labelled set catches it. No app rollback |

### 6.3 The module lab, proposed

One offline run that answers the module question. Proposal, not built.

1. A seeded fake support agent emits OTLP-JSON traces in L1's shape. Each request carries prompt version, model as returned, config version, harness version, retrieval index version and top-k ids, and tool call ids.
2. A fake judge with set TPR and TNR scores a sample. It emits `gen_ai.evaluation.result` parented to the scored span.
3. L3's corrected MWMBR rule reads the scores.
4. Inject five changes on a schedule: prompt, model alias, config default, index corruption and judge change.
5. The runbook step splits the corrected pass rate by every recorded field. It prints the field that names each change.
6. Break-its: drop the prompt version. Use the privacy default with no local ids. Run the judge without trace ids. Each break-it must print which change could no longer be named.
7. Self-test: one hand-computed day per scenario.

Inferred: offline, no key, standard library, under 1 minute. Not measured.

---

## 7. Conflicts resolved

| Conflict | Reports | Evidence used | Resolution |
|---|---|---|---|
| a. Head of the GenAI repository | Raw OTel report: `c88d504`, 2026-09-16. OTel report: `8ffdf568`, 2026-09-22 | `OT/genai_commits.atom`. `c88d504` is "Lock file maintenance (#514)" | The head moved. Pin `8ffdf568` |
| b. Schema URL | Raw report: "TODO". OTel report: a declared URL | `G/README.md` says TODO. `G/model/manifest.yaml` declares `gen-ai-dev/1.42.0-dev` | Both are true, in different files |
| c. Core v1.42.0 date | Raw report: 2026-06-12. OTel report: Atom `updated` 2026-06-16, publish date not checked | Dossier author read `OT/rel_page_v1.42.0.html`: `datetime="2026-06-12T21:03:17Z"` | 2026-06-12. The raw report was right. The Atom value is an update time |
| d. Where util-genai names the old token metric | OTel report: `_instruments.py:94` creates `gen_ai.client.token.usage` | Line 94 reads `name=gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE`. The literal name is in `OT/util_genai_pypi_desc.txt:16` | The finding holds. The evidence is a constant plus the package description. The constant's value is inferred |
| e. `OTEL_SEMCONV_STABILITY_OPT_IN` | Raw report: required for the newer attributes | `UG/CHANGELOG.md:282-285` | Removed in util-genai 1.0b0. The raw claim is out of date |
| f. Reference attribute names | Raw report: `.ref`, from the openai-v2 2.4b0 docstring. OTel report: `_ref` | `completion_hook.py:42-53` appends `"_ref"` to the constant. Spec: TODO at `gen-ai-spans.md:1372` | `_ref` in util-genai 1.2b0. The spec has no name. The 2.4b0 docstring was not re-read |
| g. How to name cost | Module 1 prose: use PR #443 names now. Module 1 code: `app.gen_ai.cost_usd`. OTel report: a local namespace | PR still open, `OT/pr443.html`. Names absent from every spec state, `OT/m1_check.txt` | Not settled. Module 1 disagrees with itself. This dossier teaches a local namespace until the PR merges. The learner decides for Module 1, section 2.4 row 4 |
| h. Do the prompt attributes exist | `M1/REVIEW.md:25`: no | `G/model/gen-ai/registry.yaml:999, 1004` | They exist. The review row is stale |
| i. Where Module 1 teaches the Anthropic 2025 postmortem | Task brief: section 5.4 | `M1/inference-internals-phase-05b-observability.md:498-515` sit under "## 5.6 — Fallbacks", which starts at line 442. Line 346 in 5.5 cites it | Section 5.6. The burn table is in 5.4 |
| j. Module 12 section 5.1 title | Incidents report: "The sample rate has a floor set by the drop and J" | `agent-evals-phase-05-online.md:72` | The heading is "5.1 — The drop and the judge's TPR and TNR set a sample floor" |
| k. Workbook low-traffic burn | Incidents report quoted "1,000x burn rate" as verified | Same page: 10 requests per hour, one failure, 99.9% SLO, "13.9%" of budget, "only seven failed requests". 0.10 ÷ 0.001 = 100 | The quote is on the page. The number is wrong on the page. 13.9% and seven hold. Teach 100x and say the source says 1,000x |
| l. Which rule fired 88.7% of the time | Incidents report concept 4: "the uncorrected ticket tier" | `IN/proto/main_output.txt`: the rule is "burn MWMBR raw judged (uncorrected)", all three Google tiers | The whole raw-judged rule, not one tier |
| m. LiteLLM mock flags on the proxy | Docs: stripped from v1.85.0. Source at v1.101.0: HTTP 400 unless an admin enables them | both saved, incidents report section 8 | Trust the source at your version |
| n. Anthropic `incidents.json` counts | Raw report: 27 minor, 17 major. Today: 26 minor, 18 major | the endpoint returns a rolling 50 | Time-dependent. Quote with the fetch date |
| o. "The first time a failure mode occurs should not be in production" | Raw report: verified on the Agentic AI Lens | Not on `agentic-ai-lens/reliability.html`. No source found | Dropped |
| p. Cloudflare 2025-06-12 duration | The blog says "2 hours and 28 minutes". Its timeline gives 156 minutes | both strings on one page | Not settled. Out of the lesson |

---

## 8. Gap list, ranked by what the module question needs

| Rank | Gap | Why the module question needs it | What was done |
|---|---|---|---|
| 1 | The joined module lab: record, judge, alert, runbook | The question asks what should have been recorded. Only a run that fails to name a change without a field proves the field was needed | Not built. Design in 6.3 |
| 2 | Slice-level drops in the SLO simulator | Both Anthropic incidents hit slices of traffic. L3 draws every request the same way. A global alert may never fire on a 0.8% slice | Not built. L5 |
| 3 | What a real instrumentation emits at runtime | 4.1 to 4.4 rest on code reading. The names on the wire may differ | Not run. Run util-genai 1.2b0 with a fake client and an in-memory exporter |
| 4 | Late judge score against tail sampling | 4.6 is inferred from a default | Not run. L4 |
| 5 | Retrieval ids with content capture off | 4.3 says the default drops them. No instrumentation was checked for a local id field | Not checked |
| 6 | Burn tiers for a judged SLI | No source publishes them. The adapted tiers are tested only in simulation | Not checked. Proposal only |
| 7 | Dashboards and vendor platforms | The README lists dashboards as a topic. The raw platforms report was not re-checked: data models, OTLP endpoints, sampling, masking, pricing, retention | Not checked. Needs its own research agent |
| 8 | A release id attribute | The change log join needs a release id on each span. `service.version` was not checked in core | Not checked |
| 9 | The `tracestate` `th` sampling rules | 4.2 names it as the place for the sampling decision | Not re-read in spec v1.61.0 |
| 10 | Reference names for stored content | Needed to find the content of a sampled-out trace, 4.6 | Spec TODO. Only the Python names are known |
| 11 | Bodies of arXiv 2511.21140 and 2605.06939 | Confidence intervals for a corrected rate inside an alert rule | Abstracts only |
| 12 | Whether the 2026 Claude Code problems had a status entry under another title | 4.9 | Keyword scan by the reviewer found none, 4.9. A manual read is not done |
| 15 | An alert on missing judged samples | 4.13. A stopped judge makes the quality alert silent. No source publishes a rule for a judged SLI | Code path verified in L3. The fix is inferred. Not run |
| 16 | Real-time signal for a slice of traffic, such as a rollout cohort | Both Anthropic incidents hit slices. A per-cohort split needs the cohort on each request | Not checked. L5 could add it |
| 13 | Collector limits: OTLP receiver 4 MiB, a deprecation warning in `batch_processor.go` | Export failures lose the record silently | Not checked |
| 14 | Bucket boundaries of the new token histograms | Dashboards on the new metrics | Not checked |

---

## 9. Things not verified

Each item gives the check that would settle it.

1. **The value of `GEN_AI_CLIENT_TOKEN_USAGE`** in `opentelemetry-semantic-conventions` 0.65b0. Read the constant in that package. Section 7 row d.
2. **What any instrumentation emits at runtime.** No SDK or Collector ran. Run util-genai 1.2b0 with an in-memory exporter.
3. **Tail sampling with a late judge event.** Lab L4.
4. **The `tracestate` `th` rules and the sampler status lines** in OTel specification v1.61.0. Fetch `trace/tracestate-probability-sampling.md` and `trace/sdk.md` at that tag.
5. **Bucket boundaries of every histogram at `8ffdf568`.** Only the TTFT and chunk histograms were checked. Read `G/docs/gen-ai/gen-ai-metrics.md` in full.
6. **Whether `service.version` is the place for a release id.** Read the core resource conventions at v1.44.0.
7. **The attribute count 118 in Module 1.** Re-count at the 2026-09-10 commit with the Module 1 method.
8. **PR #443 after 2026-09-25.** The page may change. Re-read before teaching 4.2.
9. **The openai-v2 2.4b0 docstring** with `.ref`. Fetch `openai_v2/__init__.py` at tag `opentelemetry-instrumentation-openai-v2==2.4b0`.
10. **A deprecation warning in `batch_processor.go`** at v0.161.0. Grep every file in `processor/batchprocessor/` at the tag.
11. **Issue #15047 state and the genainormalizer first-commit date.** Both need the GitHub API, which was rate-limited.
12. **OTLP receiver limits, Jaeger and otel-lgtm images, debug and file exporters.** Raw OTel report sections 3 and 5.
13. **The whole raw platforms report** except one PyPI row: vendor data models, endpoints, pricing, retention, masking and online evals.
14. **The exact date Anthropic opened its 2025 investigation.** The post says "late August". Aug 5 to Aug 31 is 26 days. Find the earlier incident that `72f99lh1cj2c` mentions.
15. **The eval, size and metric behind the Anthropic 2026 "3% drop".** Not in the post.
16. **The start time of the OpenAI 2024-02-20 bug**, so its time to detection. The status page gives only the investigation start.
17. **Whether the GPT-4o sycophancy update reached API snapshots.** Read the OpenAI API changelog for 2025-04-24 to 29.
18. **The status-page class counts.** Read all 431 Anthropic and 94 OpenAI titles by hand.
19. **Whether the 2026 Claude Code problems had a status entry.** A keyword scan found none, 4.9. A manual read of every March and April 2026 title would settle it.
20. **The bodies of arXiv 2511.21140 and 2605.06939.**
21. **Any published burn tiers for a judged SLI.** None found.
22. **L3 on real traffic.** It uses independent draws and a constant judge.
23. **Why the simulated small-drop TTD, 60h05m, is 6 hours later than the deterministic 54 h.** Log the per-seed crossing times in L3.
24. **The Workbook edition year.** Not on the saved page.
25. **Toxiproxy's latest release, and the size of the `otelcol-contrib` binary and of PyYAML.**
26. **The reference scenario `data.json` for trajectory rebuild**, 4.5. Read one file under `G/reference/scenarios/`.

---

## 10. Review log


Reviewer: independent reviewer, 2026-09-25. Read-only checks of the saved sources, plus three fresh fetches. No lab ran. Scratch notes: `/private/tmp/claude-502/-Users-raghvendra-dhakar-Desktop-project-code/dabd56e3-78f3-4dbc-bddb-3316bb9bedda/scratchpad/chk.py`, the quote checker.

### 10.1 Corrections, by kind

| # | Kind | Where | What was wrong | Evidence | Fix in the text |
|---|---|---|---|---|---|
| R1 | Wrong mechanism. Most serious | 4.6 heading and body, section 1 table, L4 | The dossier said a judge score that arrives late cannot keep a trace. The real reason is stronger. `gen_ai.evaluation.result` is a log record, and the tail sampler handles traces only. The sampler never sees the score, early or late | `G/docs/gen-ai/gen-ai-events.md:16`. `OT/src/core/docs/general/events.md:13`, "a `LogRecord` with an event name". `COL/contrib__processor_tailsamplingprocessor_factory.go:25`, `processor.WithTraces`. `metadata.yaml:7`, `beta: [traces]` | New heading and first bullet. Old claim kept only for a score on a span. L4 now tests three cases. Decision caches default to 0 added |
| R2 | Missing concept | 4.13, section 1 table, gap 15 | The prototype's sample floor makes every rule return no alert when the judge stops. The dossier taught the floor but not this silence | `IN/proto/judged_slo_alerts.py:133-137` and `:155-160` | New bullets. The fix, an alert on judged sample count and score age, is labelled inferred. Links Module 11 section 6.3 |
| R3 | Weak evidence under a "verified" label | 4.2 | "Sampling has no attribute" cited the prototype's own MISS. That shows the prototype's rule, not the spec | `G/model/gen-ai/registry.yaml:120-129`, "sampling" only in `top_p` and `top_k`. `G/model/gen-ai/spans.yaml:263-271` | Registry evidence added. The MISS is kept and labelled as not the evidence |
| R4 | Missing condition | 4.8, 3% drop | The 3% eval ran after the incident, in ablations. It was not a pre-release eval | `IN/src/anth_2026_april23.txt`, "using a broader set of evaluations" | Condition added |
| R5 | Missing condition | 4.7, OpenAI | An expert-tester signal existed before launch. "Evals and alerts did not" holds, but no signal at all is wrong | `IN/src/oai_syco2_browser.txt`, "felt" slightly off | Sentence added |
| R6 | Missing concept, with evidence | 4.3 | Privacy practice slowed the Anthropic 2025 investigation. This supports recording ids and versions without text | `IN/src/anth_2025_postmortem.txt` | New bullet |
| R7 | Missing concept, inferred | 4.8 table, gap 16 | No field for the rollout cohort or flag state. Anthropic 2026 names gradual rollouts and soak periods as its fix | `IN/src/anth_2026_april23.txt` | New inferred row |
| R8 | Missing condition on a proposal | 4.10 | The adapted 24-hour tier fires at fail rate 0.035, below the 0.05 budget rate. It fires while the SLO is met. The tiers also use a 7-day budget in a 30-day SLO run | Recomputed: 0.7 × 0.05 = 0.035. `IN/proto/main_output.txt` header | New bullet. Teach it as a drift ticket |
| R9 | Missing evidence for the module question | 4.10 | A duration clause can keep a noisy SLI from alerting | `IN/src/sre_alerting.txt`, "may never alert" | New bullet |
| R10 | Precision | 4.1 | The breaking note of #374 names only histograms. The counters come from `374.enhancement.md`. The billable rule is on both kinds, not only the counters | `G/changelog.d/374.breaking.md`, `374.enhancement.md`, `token-metrics.yaml:20` and `:95` | Sentence rewritten |
| R11 | Wrong version | 3.1 | arXiv 2511.21140 is v4, revised 2026-05-31, not v1 of 2025-11. Fiedler's date is 2026-05-07 | `IN/src/arxiv_2511_21140.txt`, `IN/src/arxiv_2605_06939.txt` | Rows fixed |
| R12 | Wrong position | 3.1 | `c88d504` is two commits before `8ffdf568`, not one. `cc07f72`, pull request #528, is between | `OT/genai_commits.atom`, and a fresh fetch on 2026-09-25 | Row fixed |
| R13 | Overlap: re-teaching risk | 2.2, 2.3, 4.8, 4.12 | Module 11 section 3.5, lines 714 to 716, already teaches that the correction assumes fixed TPR and TNR, and cites Fiedler. Module 11 section 2.4, Module 11 section 6.3, Module 12 section 3.3 and Module 12 section 5.3 also overlap. None was linked | `grep -n '^## '` on the three built modules, 2026-09-25 | Five owner rows, five overlap rows and links in 4.8, 4.12 and 4.13 |
| R14 | Heading text | 2.2, 2.3 | Module 1 headings 5.5 and 5.6 were cut short | `inference-internals-phase-05b-observability.md:213` and `:442` | Full titles |
| R15 | Gap partly closed | 4.9, gap 12, item 19 | A keyword scan of status titles for March and April 2026 found no entry for the Claude Code changes | `IN/src/anth_history_p1.json` to `p6.json` | New bullet. Gap and item updated |
| R16 | Extra check, no change of result | 2.4 row 3 | The reviewer also could not reproduce 118. `- key:` lines give 82 at both commits | `OT/src/genai/model/*/registry.yaml`, `OT/src/genai_c88d504/model/*/registry.yaml` | Note added |

### 10.2 Arithmetic, recomputed by the reviewer

Every value below matches the dossier.

| Claim | Recomputation | Result |
|---|---|---|
| Maximum burn at SLO 0.95 | 1 ÷ 0.05 | 20 |
| Tier fail rates | 14.4 × 0.05, 6 × 0.05, 1 × 0.05 | 0.72, 0.30, 0.05 |
| Google burns | 0.02 × 720 ÷ 1, 0.05 × 720 ÷ 6, 0.10 × 720 ÷ 72 | 14.4, 6, 1 |
| Adapted burns | 0.02 × 168 ÷ 1, 0.05 × 168 ÷ 6, 0.10 × 168 ÷ 24 | 3.36, 1.4, 0.7 |
| Judged pass | 0.95 × 0.98 + 0.15 × 0.02 | 0.934. Raw burn 0.066 ÷ 0.05 = 1.32 |
| Correction | (0.934 + 0.85 − 1) ÷ 0.8 | 0.98 |
| Judge drift | 0.80 × 0.98 + 0.003 = 0.787. (0.787 − 0.15) ÷ 0.8 = 0.796. Burn 0.204 ÷ 0.05 | 4.08. Ticket crossing 2.16 ÷ 0.184 = 11.8 h |
| Ticket crossings | 72 h window, need mean fail 0.05: 2.16 ÷ 0.08, 2.16 ÷ 0.04 | 27.0 h, 54.0 h |
| Severe drop, page-6 tier | 6 h window, need 0.30: 1.68 ÷ 0.38 | 4.4 h |
| Standard error | √(0.066 × 0.934 ÷ 50) ÷ 0.8 | 0.044 |
| Judged per 5 minutes | 1,000 ÷ 12 × 0.05 | 4.17 |
| Workbook low traffic | 0.10 ÷ 0.001 = 100. Budget 7,200 × 0.001 = 7.2. One failure ÷ 7.2 | 100x, not 1,000x. 13.9%. Seven |
| Opus 4.1 status post | Aug 25 17:30 to Aug 29 17:02. Aug 28 02:00 to Aug 29 17:02 | 95.5 h, 39.0 h |
| Inference span rows | Count of table rows, `gen-ai-spans.md:37-112` | 46: 2, 11, 28, 5 |

The drift burn is 0.20375 ÷ 0.05 = 4.075. The dossier wrote 4.07. Section 4.12 now says 4.08. The difference changes no conclusion.

### 10.3 The 16 resolved conflicts, rows a to p

All 16 hold against their evidence. Checks: a, the atom feed titles. b, `G/README.md:13-15` reads "TODO". c, `datetime="2026-06-12T21:03:17Z"`. d, `_instruments.py:94` and `util_genai_pypi_desc.txt:16`. e, `UG/CHANGELOG.md:282-285` under "Version 1.0b0 (2026-07-09)". f, `completion_hook.py:42-53`. g, `pr443.html` `"state":"OPEN"` and `m1_check.txt`. h, `registry.yaml:999, 1004`. i, `phase-05b:346` and `:498`. j, `agent-evals-phase-05-online.md:72`. k, the Workbook text. l, `main_output.txt`. m, `MockTestingParamsDisabledError` returns HTTP 400 in `litellm_route_tag.html`. n, 26 minor and 18 major in `anth_incidents_json.txt`. o, no saved file holds the quote. p, both strings on `cf_jun2025.txt`.

### 10.4 Gaps the reviewer did not close

- L4 and the runtime check of util-genai are still not run. R1 rests on reading code and docs.
- The alert on missing judged samples, R2, is not run in L3.
- The rollout cohort field, R7, has no published incident that names it.

Summary: the facts in the dossier hold. One mechanism in 4.6 was wrong, one "no alert fired" cause was missing, and five built sections were not linked.

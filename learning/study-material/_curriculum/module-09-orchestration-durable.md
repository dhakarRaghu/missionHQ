# Module 09 — Orchestration, state, and durable execution

Research date: 2026-09-23. This is a refresh of the dossier dated 2026-09-17. Status: research dossier, not course material. Section 13, "Refresh log 2026-09-23", lists every change and every correction to the 2026-09-17 text.

Module question: **When an agent run crashes, waits for a person, or is split across agents, which work runs again, which state is lost, and which side effect happens twice?**

## How this dossier was built

- **Inputs.** Two research reports written on 2026-09-23: `scratchpad/reports/research_orchestration-durable_durable.md` and `scratchpad/reports/research_orchestration-durable_multiagent.md`. The Module 9 fix list is in `scratchpad/reports/curriculum_audit.md`, section 4, "Module 9, orchestration and durable execution: grade B".
- **Paths.** `scratchpad/` means `/private/tmp/claude-502/-Users-raghvendra-dhakar-Desktop-project-code/2ba7cd59-bd20-4d0a-a9d5-98cef39f2fb7/scratchpad/`. `$R` means `scratchpad/research_orchestration-durable/`. `$N` means `scratchpad/m09_refresh/`, the notes for this refresh.
- **Labels.** Every claim is **verified**, **inferred** or **not checked**. A verified claim names its file and its line, table or section. "Verified by run" means a script ran on the research laptop on 2026-09-23 and its output is saved in the named file. An inferred claim names its basis and the check that would confirm it. The old labels `[V]` and `[V-agent]` are gone. Each old `[V-agent]` fact was either checked again today or is marked not checked.
- **Pages fetched for this refresh.** 16 URLs, fetched on 2026-09-23 with `curl -sL --max-time 60` and a browser user agent. All 16 returned HTTP 200. Saved in `$N/src/`.
- **Anchor numbers re-checked.** The dossier author grepped the evidence for every section-4 claim again on 2026-09-23 with `grep -c -F` over the saved source or run file. 99 anchor strings were checked. 99 were found. Six strings are split across a line break in the saved text, so a shorter part of each was grepped. Files: `$N/anchors.tsv` and `$N/anchors_result.tsv`.
- **Run conditions.** Durable runs: Apple arm64 Mac, CPython 3.12.14, `langgraph` 1.2.12, `langgraph-checkpoint` 4.2.0, `langgraph-checkpoint-sqlite` 3.1.1, `dbos` 3.0.0, `temporalio` 1.33.0, `openai-agents` 0.22.3 with `openai` 3.19.0. No Docker, no API key, no model call. Evidence: `$R/durable/runs/venv_versions.txt`. Multi-agent runs: Apple M4 Pro, Python 3.9.6 for the fan-out check, `langgraph` 1.2.12. This refresh did not run any lab.

---

## 1. What this module is for

This module teaches how to keep a long agent task correct when processes crash, code is deployed, and people take days to answer. Durable execution means the runtime records each finished step outside the process. After a crash, the task continues from the recorded steps instead of from the start. An agent that refunds money or sends email has side effects. A retry, a resume or a replayed approval can repeat those side effects.

The module also teaches when to split work across several agents. The measured evidence says the average gain is near zero, and the result depends on task shape and budget rule.

The learner builds a refund agent. It looks up an order, asks a person to approve, charges or refunds through a payment provider, and emails the customer. Every concept below appears in that agent.

## 2. Scope

### In scope

- Measured evidence on one agent against several, with its budget rule and conditions.
- Orchestration shapes as mechanisms: orchestrator-worker, handoff, fan-out and merge, debate. Only their cost, latency and failure evidence.
- Coordination failures and the MAST label set.
- Checkpointing and resumption in LangGraph, the OpenAI Agents SDK and the Claude Agent SDK.
- Durable execution engines: Temporal, DBOS, Inngest, Restate, Cloudflare Workflows, AWS Step Functions and AWS Lambda durable functions.
- Replay, determinism, versioning of running workflows, and history limits.
- Idempotency keys, the outbox pattern, sagas, and the scope of "exactly-once".
- Retry defaults inside workflow frameworks.
- Human approval as a durable wait: signals, timers and timeout behaviour.

### Out of scope, and where it lives instead

| Topic | Where it lives |
|---|---|
| Retries, jitter, retry amplification at the model-call level | Module 1, section 5.3 |
| Failover and fallback between models | Module 1, section 5.6 |
| Quality incidents and postmortems in general | Module 1, section 6.3 |
| Sub-agent token cost, the Anthropic 90.2% result, the 4x and 15x ratios, the 80% BrowseComp variance, both Cognition posts, "split or file" | Built Module 2, Phase 4, sections 4.1 to 4.3 |
| The in-process agent loop, tool execution by the harness | Module 7, dossier 4.3 "The execution rule" |
| Loop caps and stop conditions as a harness control | Module 7, dossier 4.11 "Loop control and stop conditions" |
| Plans written as code | Module 7, dossier 4.13 "Plan as code" |
| Sandboxes | Module 7 |
| The Replit production database deletion | Module 7, section 7 |
| A2A as a protocol, and task state shared across vendors | Module 8 |
| Tool design and the code execution tool | Module 6 |
| Long-term memory stores | Module 10 |
| Trajectory evals for multi-agent runs | Module 12 |
| Tracing of workflow and agent spans | Module 15 |
| Plan-then-execute as a prompt-injection defence | Module 16 |
| Approval screen design | Module 19 |

Module 7 is being built now. It has no phase file yet. The section names above come from `_curriculum/module-07-agent-harness.md`, read with `grep '^### 4\.'` on 2026-09-23. Replace them with the built phase headings when Module 7 is finished. Module 8 has no file in `_curriculum/` today. Its research is in `scratchpad/research_agent-protocols/`. One line in Module 9 is enough: agents in different processes or vendors can exchange tasks over A2A, see Module 8.

### Overlap with built modules

Headings were read with `grep -n '^## '` over `context-engineering/*.md` on 2026-09-23, as audit rule 5 asks. The Module 2 coverage file is `_curriculum/module-02-coverage.md`.

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| A sub-agent's token cost. The Anthropic 90.2% result with its conditions. The 4x and 15x ratios. The 80% BrowseComp variance | Module 2, 4.1 "A sub-agent moves tokens, it does not remove them", `context-engineering-phase-04-split-or-file.md` line 54. The 90.2% is at line 139 | Controlled studies with a stated budget rule, 4.1 to 4.6. Link 4.1. Do not re-teach the Anthropic numbers |
| Parallel writers are unsafe. Both Cognition posts | Module 2, 4.2 "Parallel readers are safe, parallel writers are not", line 235 | What a graph framework does with two writes to one key, 4.8. Link 4.2 |
| Passing a file instead of the content. Notes as inputs to check | Module 2, 4.3 "A note the agent wrote is an input you must check", line 339 | A handoff summary drops rules before facts, 4.7. Link 4.3 |
| Retries with backoff and jitter | Module 1, 5.3 | Retries across process restarts. Retry defaults inside workflow frameworks, 4.17 |
| Fallbacks | Module 1, 5.6 | Compensating actions when a later step fails after an earlier step had an effect |
| Incident review | Module 1, 6.3 | Incidents specific to workflows: stuck workflows after a deploy, duplicate notifications |
| Loop caps | Module 7 dossier, 4.11 | Only the durable angle: a cap stops a run and does not undo effects, 4.18 |
| Plans as code | Module 7 dossier, 4.13 | Only "a fixed plan is a workflow". No repeat of the code-action material |

## 3. What changed recently

| Date | Source | Change | Why it matters | Label |
|---|---|---|---|---|
| 2025-10-15 | IETF Datatracker | Last revision, -07, of the Idempotency-Key header draft. Expired 2026-04-18 | Do not call it a standard | Verified, `$R/durable/docs/ietf_idem.html` |
| 2025-10-23 | arXiv 2508.17536 v2 | "Debate or Vote", NeurIPS 2025 Spotlight | Voting explains most debate gains | Verified, `$R/multiagent/2508.17536v2.txt` |
| 2025-10-26 | arXiv 2503.13657 v3 | MAST, NeurIPS 2025 Datasets and Benchmarks | 14 failure modes. The label set | Verified, `$R/multiagent/2503.13657v3.txt` |
| 2025-12-09 to 2026-04-08 | arXiv 2512.08296 v1 to v3 | Google scaling paper. v1 matched token budgets over 180 configurations. v3 matches iterations over 260. The 17.2x changed meaning | Cite the version with every number | Verified, `$N/src/arxiv_2512.html` submission history, v3 dated 8 Apr 2026 |
| 2026-01-12 | PyPI, `langgraph` 1.0.6 | Default recursion limit 25 to 10000 | The 25-step stop is gone | Verified at tags, `$R/durable/src/cfg_1.0.5.py`, `cfg_1.0.6.py` |
| 2026-02-05 | Anthropic engineering | C compiler built by 16 parallel agents | Parallel writers overwrote each other on the kernel | Verified, `$R/multiagent/anth_ccomp.txt` |
| 2026-04-11 | arXiv 2604.02460 v2 | Stanford equal-thinking-budget study | One agent wins or ties at a matched budget | Verified, `$R/multiagent/2604.02460v2.txt` |
| 2026-05-12 | PyPI, `langgraph` 1.2.0 | Default 10000 to 10007. `TimeoutPolicy` added | Node timeouts exist | Verified at tags, `$R/durable/src/lg_types.py:461-487` |
| 2026-06-13 | arXiv 2606.13003 v2 | Salesforce "Illusion of Multi-Agent Advantage" | Automatic multi-agent designs lose to 5-sample voting | Verified, `$R/multiagent/2606.13003v2.txt` |
| 2026-08-13 | Hugging Face `mcemri/MAST-Data` | Rebuilt, 1,242 to 1,642 rows. Labels changed | Pin the revision in any lab | Verified, `$R/multiagent/hf_mast_commits.json` per the report, and `tally_mast_out.txt` |
| 2026-08-25 and 2026-08-29 | arXiv 2608.24358, 2608.29028 | "The Handoff Tax" and "Facts Without Rules" | First large measurements of handoff loss | Verified, saved `.txt` files |
| 2026-09-16 | PyPI and docs, `dbos` 3.0.0 | Schema change. 2.x cannot read 3.0 workflows. `@DBOS.transaction` and in-memory queues removed | Pin labs to 3.0. Do not mix versions | Verified, `$R/durable/docs/d_upgrading-3.0.md` |
| 2026-09-16 | PyPI, `temporalio-openai-agents` 1.0.0 | Separate package for the Temporal OpenAI Agents integration | Not tested | Verified, `$R/durable/pypi_versions_2026-09-23.txt` |
| 2026-09-18 | PyPI, `langchain` 1.4.2 | `create_agent` sets recursion limit 9,999 | Two defaults in one ecosystem | Verified, report 2.3, `factory.py:1831` |
| 2026-09-21 | PyPI, `langgraph` 1.2.12 | Current release. Default still 10007 | Lab pin | Verified, `$R/durable/pypi_versions_2026-09-23.txt` |
| Today | Pydantic AI docs | "supports seven durable execution solutions" | The old dossier said five | Verified, `$N/src/pai_durable.html` |

Four items from the 2026-09-17 table were not re-checked today. They are the Temporal Worker Deployment APIs GA on 2026-04-29 and Temporal server v1.32.0 as the last legacy Worker Versioning release. They also include the AWS Lambda durable functions launch on 2025-12-02 and the Temporal AI SDK by Vercel preview. Each is labelled not checked.

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Each concept starts with its single best piece of evidence and its conditions. Supporting facts follow. Concepts 4.1 to 4.9 are about splitting work across agents. Concepts 4.10 to 4.21 are about state, replay and side effects.

### 4.1 Averaged over tasks, the multi-agent gain is near zero, and the spread runs from +80.8% to −70.0%

A learner reads "+80.8%" and believes multi-agent systems are 80% better. That number is one benchmark and one architecture.

- **Best evidence, verified.** Google Research, Google DeepMind and MIT, "Towards a Science of Scaling Agent Systems", arXiv 2512.08296 v3, Section 4.2: "the overall mean MAS improvement is −0.3% (95% CI: [−58.7%, +77.2%])". Source: `$R/multiagent/2512.08296v3.txt`.
  - Conditions: 260 configurations, six benchmarks, five architectures, three agents per team, nine models from the GPT-5, Gemini 2.x and Claude Sonnet 3.7 to 4.5 families. Four benchmarks have 45 configurations with 50 to 100 instances each. SWE-bench Verified and Terminal-Bench have 40 each, on 20-instance subsets. Preprint.
  - Budget rule: v3 states two rules. Section 4.1 says "we matched maximum total iterations". The Table 5 caption says "matched for total reasoning tokens", about 4,800 per trial. Cite it as both. Section 4.3 of this dossier shows that Table 5's own columns suggest the token spend still differed.
- **The spread, verified, same section.** All numbers are relative changes, not points.
  - Finance-Agent: Centralized +80.8%, 0.631 against 0.349.
  - PlanCraft: every variant loses, from −39.1% to −70.0%. Independent is −70.0%. The paper's PlanCraft trace example in Section 4.2 is a Centralized team, at −50.3%, not the Independent one.
  - SWE-bench Verified: every variant loses, from −2.1% for Hybrid to −14.9% for Independent.
  - BrowseComp-Plus: best +9.2% for Decentralized, +0.2% for Centralized.
- **Versions differ, verified.** v1 had 180 configurations, four benchmarks, matched token budgets, R² 0.513 and 80.9%. v3 has 260, six, iterations, R² 0.373 and 80.8%. Sources: `2512.08296v1.txt`, `2512.08296v3.txt`.
- **The gain shrinks with a stronger model, verified with a correction.** Gao and others, UIUC, arXiv 2505.18286 v1, Table 2. MetaGPT on HumanEval, 90.2 to 93.2 with Gemini-2.0-Flash, is the authors' own run. The ChatGPT column, 67.0 to 87.7, is quoted from earlier framework papers. The table prints "10.7%" for 67.0 to 87.7, which is 20.7 points. It prints "9%" for 77 to 85, which is 8 points. Preprint.
- **Link, do not re-teach.** The Anthropic +90.2% on an internal eval is built Module 2, 4.1.

Summary: always give the benchmark, the architecture, the budget rule and the paper version with a multi-agent number.

### 4.2 At a matched thinking-token budget, one agent matches or beats several on multi-hop questions. Several agents win only when the context is badly corrupted

- **Best evidence, verified.** Tran and Kiela, Stanford, arXiv 2604.02460 v2, Section 5.1: "SAS is the best-performing system or statistically indistinguishable from the best for all budgets except the lowest one (100 tokens)". SAS means a single-agent system. Source: `$R/multiagent/2604.02460v2.txt`.
  - Conditions: FRAMES and 4-hop MuSiQue. Models Qwen3-30B-A3B, DeepSeek-R1-Distill-Llama-70B, Gemini 2.5 Flash and Pro. Five multi-agent designs, including debate and ensemble. Budgets from 100 to 10,000 thinking tokens.
  - Budget unit: tokens "used for intermediate reasoning, excluding prompts and final answers".
  - Scorer: an LLM judge with a rubric. The judge model is not named in the text. Verified by absence in a grep of the extracted text, per the report.
  - Preprint, under review.
- **Where it does not hold, verified.** Same paper, Section 5.3. With 70% of context tokens masked or substituted, Sequential multi-agent beats the single agent. Conditions: Qwen3-30B-A3B, MuSiQue, a fixed 1,000-token budget.
- **Tie and spend, verified.** "Tied" means the 95% bootstrap intervals overlap. So the accurate claim is "one agent ties or wins". In the FRAMES cell at a 10,000-token cap on Qwen3-30B-A3B, the single agent and the Ensemble both scored 0.263. The single agent spent 1,307 thinking tokens and the Ensemble 5,571. Source: Appendix Table 3, and the course run `orchestration-durable_p05_scaling_stanford.txt`.
- **Measurement caveat, verified.** Gemini 2.5 single-agent thinking "tends to plateau well below the requested budget". The paper adds a prompt variant, SAS-L, to correct for this. So a single agent that does not spend its budget can look cheaper.

Summary: at equal thinking tokens, one agent is the default. Test several agents only when context is noisy.

### 4.3 Turns grow faster than the agent count, so successes per token fall by a factor of 1.6 to 5

- **Best evidence, verified.** arXiv 2512.08296 v3, Section 4.4 and Table 5. The fitted law is T = 2.72 × (n + 0.5)^1.724, R² = 0.974, over architecture-level means. Table 5:

| Metric | SAS | Independent | Decentralized | Centralized | Hybrid |
|---|---|---|---|---|---|
| Turns | 7.2 | 11.4 | 26.1 | 27.7 | 44.3 |
| Success rate | 0.466 | 0.370 | 0.477 | 0.463 | 0.452 |
| Success per 1K tokens | 67.7 | 42.4 | 23.9 | 21.5 | 13.6 |

- **Arithmetic, verified by the dossier author.** 67.7 / 42.4 = 1.6. 67.7 / 21.5 = 3.1. 67.7 / 13.6 = 5.0. The best multi-agent success rate, 0.477, is 1.1 points above the single agent.
- **The token spend was not equal, inferred.** Tokens per trial are success divided by success per token. For Hybrid that ratio is (0.452 / 13.6) / (0.466 / 67.7) = 4.83 times the single agent, although the caption says tokens were matched. The paper's Section 4.4 also says the designs used "1.6–6.2× token budgets relative to single-agent at matched performance". Inferred from Table 5 arithmetic. The paper does not explain it.
- **Input tokens, verified.** UIUC, arXiv 2505.18286 v1, Section 3: multi-agent "consumes 4–220× more input (prefill) tokens" across seven datasets. The 220x row is AIME.
- **Link, do not re-teach.** The token arithmetic of one sub-agent is built Module 2, 4.1, with `split_budget.py`.

Summary: a team that succeeds at the same rate costs several times more per success.

### 4.4 The "17.2x error amplification" measures extra work in traces, not wrong answers. A central verifier cuts factual errors by about a fifth

The old dossier taught 17.2x as an error rate, and its lab L1 modelled it that way. v3 defines it differently.

- **Best evidence, verified.** arXiv 2512.08296 v3, Section 3.1 and Section 4.4. The trace-level factor "measures how much extra computational work arises from inter-agent coordination failures, estimated from execution-trace token analysis". Independent agents give 17.2x. Centralized coordination gives 4.4x.
- **The task-level error factor is small, verified.** Same paper: E_MAS / E_SAS is "≈1.1–1.3". The regression coefficient for error amplification is 0.014, p = 0.658. It is not significant.
- **The defensible verifier number, verified.** Centralized, Hybrid and Decentralized designs give "22.7% average error reduction (95% CI: [20.1%, 25.3%])" in factual errors, up to 31.4% on Finance Agent. Independent agents show +4.6% amplification.
- **Version history, verified.** v1 wrote "independent agents amplify errors 17.2×" in its abstract. Source: `2512.08296v1.txt`.

Summary: teach 22.7% fewer factual errors with a verifier. Do not teach 17.2x as an error rate.

### 4.5 A high single-agent score predicts smaller gains from more agents, but the "capability ceiling" coefficient is only directional

- **Best evidence, verified.** The v3 introduction, not the abstract, reports "capability ceiling (𝛽=−0.236, 𝑝=0.004): tasks where single-agent performance already exceeds 45%". Source: `2512.08296v3.txt` line 153. The same paragraph, line 156, prints "17.2×". The coefficient belongs to the interaction term of the single-agent score and log agent count, labelled "Baseline paradox" in Table 4, 95% CI [−0.396, −0.076].
- **Robustness, verified.** The 0.004 is the naive p-value. Table 14 gives a cluster-robust p of 0.105, and Table 15 a Holm p of 0.084. The paper reports the term "as directional patterns rather than confirmed effects", and as "suggestive" after Holm correction.
- **The robust term is a different one, verified.** The single-agent baseline term, +0.250, has cluster-robust p = 0.004 and Holm p = 0.018. Table 4 labels it a "Task difficulty proxy". It has no agent count, so it says only that easy tasks are easy for every system. The paper's conclusion attaches these two p-values to the 45% finding.
- **The 45% line, verified.** It is 0.040 / 0.236 = 0.170 in standardized units, converted to a raw score near 0.45. The 0.040 term has p = 0.487 in Table 4.
- **Teaching text.** The data point in one direction: adding agents may help less where one agent already scores high. Teach it as a direction to test. Do not teach β = −0.236 or the 45% threshold as a confirmed effect, and do not call the baseline term a ceiling effect.

Summary: the direction is supported. The exact coefficient and threshold are not.

### 4.6 Voting with the same number of calls explains most of the gain of debate, and beats automatically designed multi-agent systems

- **Best evidence, verified.** Choi, Zhu and Li, UW-Madison, "Debate or Vote", arXiv 2508.17536 v2, NeurIPS 2025 Spotlight: "Majority Voting alone accounts for most of the performance gains typically attributed to MAD". MAD means multi-agent debate. Table 1, Qwen2.5-7B-Instruct, five agents, seven benchmarks, average accuracy:

| System | Average accuracy |
|---|---|
| Single agent, mean of 5 runs | 0.7205 |
| Majority voting, 5 agents, no debate | 0.7691 |
| Best debate, Decentralized MAD, 2 rounds | 0.7377 |
| Centralized MAD, 2 rounds | 0.6551 |

  - Centralized debate scored below the single agent in this table. The paper's text says MAD "consistently outperforms the single-agent baseline". Its own table contradicts that sentence for Centralized MAD.
- **Automatic designs, verified.** Salesforce Research and universities, arXiv 2606.13003 v2, Section 3: "automatic MAS consistently underperform CoT-SC despite being up to 10x more expensive". CoT-SC is a 5-sample majority vote. Conditions: six automatic designers, backbones GPT-4o, GPT-5, GPT-OSS-120B and Gemini-2.5-Pro. Benchmarks HLE-Maths, GPQA-Diamond, SWE-Bench Lite and BrowseComp-Plus. Mean of 3 runs, 1 run for Gemini-2.5-Pro. The Figure 2 caption names an exception on HLE-Math. Preprint.
- **Budget rules differ, verified.** Of the studies in 4.1 to 4.6, only Google v3 and Stanford fixed a budget for every system. Debate or Vote compares a 5-call vote with 15-call debates. Salesforce reports automatic designs as up to 10 times more expensive than CoT-SC. Du compares 3 votes with at least 6 debate calls, inferred from its table note.
- **The older opposite result, verified.** Du and others, arXiv 2305.14325, Table 1. ChatGPT, 3 agents, 2 rounds, grade-school math. Debate 85.0 ± 3.5. Majority voting 81.0 ± 3.9. The intervals overlap. Model, agent count and data differ from Choi.

Summary: compare any debate or agent team against voting with the same number of calls.

### 4.7 A handoff keeps facts and drops the rules about them, and a stronger model that takes over a weak model's trajectory recovers less than half the gap

A handoff passes control to another agent. The receiving agent continues work it did not write.

- **Best evidence, verified.** Wang, Goyal, Chandrasekharan and Sundaram, UIUC, "Facts Without Rules", arXiv 2608.29028 v1, abstract: "a 25-word budget drops σb to ≈0.57 while operational-fact survival stays near ceiling". σb is the share of boundary markers, such as "do not share with the vendor", that survive. Free-text handoffs keep σb near 0.80. Models GPT-5-mini and DeepSeek-R1-32B. Judge agreement with humans κ = 0.74. Preprint. Read from the abstract and first page only.
- **Model switch inside one agent, verified.** Ganz and others, AWS, "The Handoff Tax", arXiv 2608.24358 v1. The stronger model "recovers less than half" of the quality gap: QRec = 47% for Claude and 36% for GPT.
  - Conditions: SWE-bench Verified, 500 instances, mini-swe-agent, Haiku 4.5 to Opus 4.7 and GPT-5.6 Luna to Sol, 58,000 runs.
  - Claude pair: a raw handoff cost $1.61 per task. Restarting the strong model from scratch cost $0.90, including the discarded weak-model work, and solved more, 79.2 against 69.2. Source: lines 405 to 432 and 533 to 542.
  - This is a model switch, not a team of agents. The mechanism is the same. Preprint.
- **Handoffs in the OpenAI Agents SDK, verified.** Docs: "Handoffs are represented as tools to the LLM". The new agent "gets to see the entire previous conversation history". `input_filter` changes that. Source: `$R/multiagent/oai_handoffs.txt`. At tag v0.22.3, `run_config.py:374` sets `nest_handoff_history: bool = False`, an "Opt-in beta". Source: `$R/multiagent/src_run_config.py`.
- **Link.** Passing a file reference instead of a summary is built Module 2, 4.3.

Summary: a handoff message is state, and its summary loses constraints first.

### 4.8 A state reducer resolves two parallel writes to one key, but it keeps both side effects

A reducer is a function that merges node updates into shared graph state. A super-step is one round in which all ready nodes run.

- **Best evidence, verified by run.** `langgraph` 1.2.12, no model. Two parallel nodes write key `refund` in one super-step. Script `$R/multiagent/lg_concurrent_write.py`, output `lg_concurrent_write_out.txt`.
  - Plain key: raises `InvalidUpdateError`, "At key 'refund': Can receive only one value per step." Source: `channels/last_value.py:61` at tag 1.2.12.
  - Key with an `operator.add` reducer: returns `['A: refund 40', 'B: refund 40']`. The merge succeeds and keeps both refunds.
- **Parallel writers in practice, verified.** Anthropic, "Building a C compiler with a team of parallel Claudes", 2026-02-05. 16 agents coordinated through lock files and git. On the Linux kernel, "Every agent would hit the same bug, fix that bug, and then overwrite each other's changes." One run, no control. Source: `$R/multiagent/anth_ccomp.txt`.
- **Link.** Parallel readers against parallel writers is built Module 2, 4.2.

Summary: a reducer fixes the state conflict. It does not stop the second refund.

### 4.9 MAST is a usable label set, but its published category shares do not reproduce from the public data, and an LLM judge made the labels

MAST is a taxonomy of 14 multi-agent failure modes in 3 categories.

- **Best evidence, verified by run.** A tally of the public dataset `mcemri/MAST-Data`. Script `$R/multiagent/tally_mast.py`. Shares are of all mode hits, the unit the paper's figure uses.

| Data | Rows | Specification | Inter-agent | Verification |
|---|---|---|---|---|
| Paper, Figure 1 | 1,642 | 44.2% | 32.3% | 23.5% |
| HF revision 2026-08-13, `95118ac` | 1,642 | 36.9% | 33.1% | 30.0% |
| HF revision 2025-07-21, `5a82e32` | 1,242 | 40.6% | 36.3% | 23.1% |

  - Outputs: `tally_mast_out.txt`, `tally_mast_2025_out.txt`. A per-framework mean and a per-trace split also fail to reproduce the figure, `tally_mast_norm_out.txt`.
  - The dataset card says the labels come from an LLM judge, not from human labelling. Source: `$R/multiagent/hf_mast_README.md`.
  - The frameworks are not balanced. AG2 has 597 traces. Three frameworks have 30 each.
- **Paper facts, verified.** Cemri and others, UC Berkeley, arXiv 2503.13657 v3, NeurIPS 2025 Datasets and Benchmarks. The studied systems fail on "41% to 86.7%" of tasks. Human inter-annotator κ = 0.88 on 150 traces. The LLM annotator reached κ = 0.77 against humans, Table 2.
- **Interventions are small samples, verified.** Table 5, ChatDev on ProgramDev-v0: baseline 25.0, better prompts 34.4, new topology 40.6. ProgramDev-v0 is "a custom generated set of 32 different tasks". So the gains are 3 and 5 tasks. The task counts 8, 11 and 13 are inferred from the arithmetic. The paper says the interventions "do not constitute substantial improvements".
- **Useful per-mode shares, verified by run,** revision 2026-08-13, 5,141 hits: Step Repetition 12.9%, Incorrect Verification 12.8%, Reasoning-Action Mismatch 11.9%, No or Incomplete Verification 11.8%, Unaware of Termination Conditions 8.5%.

Summary: use MAST names to label traces. Do not teach 44.2% as a measured fact.

### 4.10 A durable engine does not resume at a line of code. It runs your function again and returns recorded results for finished steps

Replay means the engine calls the workflow function again from the top. Each call to a recorded step returns the stored result. The code between steps runs again every time.

- **Best evidence, verified by run.** DBOS 3.0.0 on SQLite. The process died inside step 3. On relaunch, steps 1 and 2 did not run again. Effects log: `run:step1 run:step2 run:step3 resume:step3 resume:step4 resume:step5`. Source: `$R/durable/runs/dbos_crash_resume_3.0.0.txt`. `DBOS.launch()` recovered the pending workflow with no call from the script.
- **LangGraph works at node level, verified.** Tag 1.2.12, `types.py:902`: "The graph resumes from the start of the node, **re-executing** all logic." Source: `$R/durable/src/lg_types.py`.
- **Other engines, verified in docs.** Restate: "Restate uses an execution log to replay operations after failures and suspensions", `$R/durable/docs/r_durable-steps.md:9`. Inngest memoizes step results by a hash of the step ID plus the step's index, `i_how-executed.md:40` and line 74. AWS Lambda durable functions recover "through replay, re-executing from the beginning while skipping completed work", `$N/src/aws_lambda_durable.html`. Restate, Inngest and Lambda were not run.

Summary: every line outside a step runs again on resume.

### 4.11 Replay needs the same steps in the same order, and a deploy that reorders steps breaks running workflows. On Temporal they get stuck, not failed

Determinism here means the workflow asks for the same steps, by name, in the same order, on every replay. Temporal and DBOS compare step names and positions, never inputs. DBOS checks only the name, at `_sys_db.py:3191`. A Temporal replay against `RefundV1NewAmount`, the same steps with another amount, passed. So a changed input, or a model call made again outside a step, returns the old record with no error. Source: the course run `orchestration-durable_p02_temporal_replay.txt`.

- **Best evidence, verified by run.** Temporal Python SDK 1.33.0, time-skipping test server. A history recorded with "charge, then email" was replayed against code that runs "email, then charge". The `Replayer` raised `NondeterminismError`: "[TMPRL1100] Nondeterminism error: Activity type of scheduled event 'charge' does not match activity type of activity command 'email'". The same change inside `workflow.patched("email-first")` replayed OK. Source: `$R/durable/runs/temporal_replay_1.33.0.txt`.
- **DBOS, verified by run.** "function charge was recorded when audit was expected. Check that your workflow is deterministic." Source: `dbos_crash_resume_3.0.0.txt`.
- **Stuck, not failed, verified.** Temporal Python error-handling docs: "The Workflow Task retries indefinitely, letting you fix the bug and redeploy without losing Workflow state." Source: `$R/durable/docs/t_py-error-handling.md:173`. Workflow task retries use "a max interval of 10 minutes", `t_retry-policies.md:19-20`.
- **Engines differ, verified in docs.** Inngest: "If step execution order changes, the SDK logs a warning rather than failing the function". "Changing step IDs forces re-execution." Source: `i_versioning.md:27` and line 97. Not run.
- **The Temporal sandbox is not a guarantee, verified.** It "helps prevent non-determinism errors but doesn't completely negate the risk". Source: `$N/src/t_sandbox.md:53`.

- **What the failure looks like, verified by run.** Temporal keeps the run `RUNNING` with a failed workflow task. DBOS ends the run in `ERROR` and does not resume it. Source: `orchestration-durable_p02_temporal_stuck.txt`, `_dbos_diverge.txt`.

Summary: strict engines stop on a changed order. Inngest continues and can mix old and new logic.

### 4.12 The step that was running at the crash runs again. Exactly-once holds only inside the engine's own database

A checkpoint is written after a step finishes. A crash inside the step leaves no record, so the step runs again.

- **Best evidence, verified by run.** LangGraph 1.2.12, `SqliteSaver`, `durability="sync"`, crash by `os._exit(1)` inside node 6 of 10. Effects: `run:n1 ... run:n6 resume:n6 resume:n7 ...`. Node 6 ran twice. No finished step from n1 to n5 ran again in 20 of 20 trials. Sources: `$R/durable/runs/lg_crash_resume_1.2.12.txt`, `lg_crash_trials_1.2.12.txt`. The trials file records the re-run of node 6 for the last trial only.
- **DBOS states it, verified.** "Steps are tried _at least once_ but are never re-executed after they complete." Next line: "Transactions commit _exactly once_." Source: `$R/durable/docs/d_workflow-tutorial.md:266-267`. DBOS 3.0 removed `@DBOS.transaction`. Datasources keep "the same exactly-once guarantees", `d_upgrading-3.0.md:24`. The guarantee covers work inside one database.
- **DBOS stops after many crashes, verified in source.** DBOS 3.0.0 stops resuming a run after `max_recovery_attempts`, 100 by default, `dbos/_registrations.py:10`. It then moves the run to a dead-letter status, `dbos/_core.py:1229`. So a step that crashes every time does not run again without limit. Not run.
- **AWS Step Functions, verified today.** "Standard Workflows follow an exactly-once model, where your tasks and states are never run more than once, unless you have specified Retry behavior". "Express Workflows use an at-least-once model". Source: `$N/src/aws_sfn_types.html`.
- **Inferred.** No engine can know whether an external call finished before a crash. Only the remote side, with an idempotency key, can remove the duplicate. Basis: 4.12 and 4.16 runs. No engine doc claiming otherwise was found. Check: search each engine's docs for an external exactly-once claim.

Summary: durable execution is at-least-once for external side effects.

### 4.13 LangGraph's default "async" durability loses several finished steps when nodes are fast

Durability mode decides when LangGraph writes a checkpoint. `sync` writes before the next step starts. `async` writes while the next step runs. `exit` writes only when the graph exits.

- **Best evidence, verified by run.** Same crash setup as 4.12, 20 trials per mode. Source: `$R/durable/runs/lg_crash_trials_1.2.12.txt`, `lg_crash_trials_async_sleep.txt`, `lg_crash_resume_1.2.12.txt`.

| Mode | Finished steps n1 to n5 that ran again, per trial |
|---|---|
| `sync` | 0 in all 20 trials |
| `async`, nodes do no work | 2 to 4 in all 20 trials, mean 3.0. The research run gave 3 or 4 |
| `async`, each node sleeps 1 ms or 10 ms | 0 in all 20 trials |
| `async`, each node sleeps 50 ms | 0 in all 10 trials |
| `async`, each node sleeps 500 ms | 0 in all 10 trials |
| `async`, 500 ms nodes, crash right after a node returns | 1 in 3 of 10 trials, then 1 in 6 of 10 in a second batch |
| `exit` | Nothing saved. `invoke(None)` raised `EmptyInputError`. The run must restart from input |

- **Default, verified.** `"async"` at `pregel/main.py:2603`, tag 1.2.12. Modes defined at `types.py:98-104`. Source: `$R/durable/src/`.
- **Docs wording, verified.** The checkpointers docs call it "a small risk". Each finished node's writes go to `checkpoint_writes`, so successful nodes in a failed super-step "don't need to be re-run". Source: `$R/durable/docs/lg_checkpointers.md:59`.
- **Inferred.** Slow nodes lose at most the last finished node, and only when the crash comes right after it. A graph of fast routing or parsing nodes loses several. Basis: the course runs `orchestration-durable_p01_lg_trials.txt`, `_lg_crash_early.txt` and `_lg_crash_early_2.txt`. Check: repeat with `AsyncSqliteSaver` and Postgres.
- **Not checked.** Why `get_state` showed `next=()` after an `async` crash while resume re-ran from n3. The saved tables show the last full checkpoint after n2, `lg_async_crash_tables.txt`.

Summary: use `sync` for any graph with fast nodes that have side effects.

### 4.14 LangGraph restarts an interrupted node from its first line, and a loop of interrupts re-runs quadratically, not exponentially

`interrupt()` pauses a LangGraph run for human input. Resume starts the node again from its first line.

- **Best evidence, verified by run.** `langgraph` 1.2.12, `InMemorySaver`. A node sends a fake email, then calls `interrupt()`. `emails after pause: 1`. `emails after resume: 2`. Source: `$R/durable/runs/lg_checks_1.2.12.txt`, CHECK2.
- **Loop count, verified by run.** A `while True` loop around `interrupt()` with 4 answers ran its body `[1, 2, 3, 4, 4]` times, 14 in total. Same file, CHECK3. The count grows by one per resume, so the total grows as the square of the number of interrupts. The docs call it exponential, `$R/durable/docs/lg_interrupts.md:539`.
- **Resume values, verified.** They match interrupts "strictly index-based", `lg_interrupts.md:689`.
- **Functional API, verified.** "A **task** that started but did not finish may run again on that resume". Source: `lg_functional-api.md:573`.

Summary: put side effects after `interrupt()` or in their own node.

### 4.15 A saved approval state is a snapshot, not a lock. Resuming it twice runs the approved tool twice

- **Best evidence, verified by run.** `openai-agents` 0.22.3 with a scripted fake `Model`, no API key. A tool with `needs_approval=True` stopped the run. `result.to_state().to_json()` gave 5,621 bytes. A second process approved and resumed: `refunds logged: ['o-42']`. A third resume of the same file gave `['o-42', 'o-42']`. Source: `$R/durable/runs/oai_runstate_0.22.3.txt`.
- **The SDK leaves this to the user, verified.** Issue #4254, "Should the SDK have a story for tools that must not run twice?", is closed. Maintainer: "We think this should be handled on the user code side." Source: `$R/durable/docs/gh_openai_openai-agents-python_issues_4254.html`.
- **Docs, verified today.** "RunState is designed to be durable." For long waits, "store a version marker for your agent definitions or SDK alongside the serialized state". Source: `$N/src/oai_hitl.html`.
- **What the saved state holds, verified.** At tag v0.22.3 the saved `RunState` stores `executed` and `completed` flags per call ID, in `_serialize_tool_invocations`, `run_state.py` lines 1366 to 1376. They describe the moment of the save. A later resume does not write them back into the stored text, so every resume of one file reads the same flags. Source: the installed package and the course run `orchestration-durable_p04_approval_replay.txt`.
- **Default session storage, verified today.** `SQLiteSession` defaults to `db_path=":memory:"`, lost when the process ends. Source: `$N/src/oai_sqlite_session_0.22.3.py:34`.
- **Claude Agent SDK, verified today.** "Sessions persist the **conversation**, not the filesystem." Sessions are stored under `~/.claude/projects/<encoded-cwd>/*.jsonl`. Source: `$N/src/cas_sessions.md` lines 14 and 272. File checkpointing tracks only Write, Edit and NotebookEdit. Bash changes "are not captured". Rewind "does not rewind the conversation itself". Source: `$N/src/cas_filecp.md` lines 18 and 26.
- **The fix, verified by run.** The course lab keys the approval by run ID plus the interruption's call ID, and claims it with a primary-key insert before resume: 1 refund instead of 2. A crash right after the claim gave 0 refunds and a row stuck in `claimed`. So a claim-first key is at most once, not exactly once. Source: `orchestration-durable_p04_approval_replay.txt`.

Summary: an approval needs its own idempotency key.

### 4.16 An external side effect happens once only with an idempotency key taken from the workflow ID and step ID, not from the model's `tool_call_id`

An idempotency key is an ID the caller sends with a request. The server stores the first result under that key and returns it for every repeat.

- **Best evidence, verified by run.** A fake payment provider in in-memory SQLite commits the charge and then loses the response twice. The caller retries 3 times. Source: `$R/durable/runs/double_charge.txt`.

| Key strategy | Charges | Total cents |
|---|---|---|
| No key | 3 | 14997 |
| New `tool_call_id` per attempt | 3 | 14997 |
| `workflow_id:step_id` | 1 | 4999 |

- **Stripe's contract, verified.** Stripe saves "the resulting status code and body of the first request made for any given idempotency key, regardless of whether it succeeds or fails". Keys are up to 255 characters. Keys may be removed after "at least 24 hours". Stripe compares parameters with the original and errors if they differ. Source: `$R/durable/docs/stripe_idempotent.html`.
- **The header is not a standard, verified.** The IETF Idempotency-Key draft is an "Expired Internet-Draft". Source: `ietf_idem.html`. Draft -07 says a reused key with a different payload "SHOULD reply with a HTTP 422" and a concurrent retry "SHOULD reply with an HTTP 409". Source: `$N/src/ietf_07.txt`.
- **Inferred.** A timeout on a step whose remote call succeeded is the same case. The caller sees a failure, and the retry repeats the side effect. Basis: the lost-response simulation.
- **The receiver must claim the key before the work, verified by run.** With 10 concurrent threads and one key, check-then-record made 10 refunds. A claim inside one write transaction made 1. A claim that is never finished leaves the side effect at most once, so it needs a reconcile step. Source: `orchestration-durable_p03_double_charge_threads_naive.txt` and `_threads.txt`.

Summary: derive the key from where the step sits in the workflow, never from the model.

### 4.17 LangGraph's default retry filter chooses by exception class: it retries an HTTP 400 from the OpenAI SDK and skips a built-in `TimeoutError`

- **Best evidence, verified by run.** `langgraph._internal._retry.default_retry_on`, 1.2.12, `openai` 3.19.0. Source: `$R/durable/runs/lg_default_retry_on_1.2.12.txt`. The script that printed it is not saved.

| Exception | Retried |
|---|---|
| built-in `TimeoutError`, `asyncio.TimeoutError` | no |
| `ConnectionError`, `httpx.ReadTimeout`, `httpx` 503 | yes |
| raw `httpx.HTTPStatusError` with 429 | no |
| `openai.RateLimitError` 429, `openai.APITimeoutError` | yes |
| `openai.BadRequestError`, HTTP 400 | yes |
| `requests.HTTPError`, 404 or 503 | yes. A `requests` response with status 400 to 599 is falsy, so the status check is skipped |
| `ValueError`, `KeyError` | no |

- **Why, verified.** The function returns `False` for a fixed list of built-in types, including `OSError` and its subclass `TimeoutError`. It returns `True` for other classes. Source: `$R/durable/src/lg__internal__retry.py:1-29`.
- **Retry is off by default on nodes, verified by run.** No policy: 1 attempt on `ConnectionError`. `RetryPolicy()`: 3 attempts on `ConnectionError`, 1 on `ValueError`. Source: `lg_checks_1.2.12.txt`, CHECK4.
- **Other defaults, verified per the durable report, section 2.4.** Temporal activities retry without limit by default. DBOS steps do not retry unless `retries_allowed=True`. Inngest retries each step 4 times. Restate's docs contradict themselves. See section 10.

Summary: name the retryable exceptions yourself. Do not trust a default filter.

### 4.18 A loop cap stops a run but does not undo its side effects, and LangGraph's default cap is 10007 steps, not the 1,000 its docs state

Module 7 owns loop caps as a harness control. This module keeps the durable angle and the corrected default.

- **Best evidence, verified by run.** LangGraph 1.2.12 stopped a no-work loop with "Recursion limit of 10007 reached" in 0.8 s. Source: `$R/durable/runs/lg_checks_1.2.12.txt`, CHECK1.
- **Default by version, verified at tags.** 25 up to 1.0.5. 10000 at 1.0.6 to 1.1.x. 10007 from 1.2.0 to 1.2.12. The environment variable `LANGGRAPH_DEFAULT_RECURSION_LIMIT` overrides it. Sources: `$R/durable/src/cfg_1.0.5.py`, `cfg_1.0.6.py`, `lg__internal__config.py:32`.
- **The docs are wrong, verified.** "Starting in version 1.0.6, the default recursion limit is set to 1000 steps." Source: `$R/durable/docs/lg_graph-api.md:1032`. No checked tag had 1000.
- **Other defaults, verified per the durable report, section 2.3.** OpenAI Agents SDK 0.22.3: 10 turns, `run_config.py:45`. Pydantic AI 2.48.0: 50 model requests. Claude Agent SDK 0.2.158: no cap. LangChain `create_agent` 1.4.2: 9,999.
- **Link.** Module 7 dossier, 4.11 "Loop control and stop conditions".

Summary: at one model call per step, 10007 steps is thousands of paid calls.

### 4.19 Each sequential Temporal activity adds 6 history events, so a long agent loop reaches the 10,240-event warning after about 1,700 activities

An activity is a function that Temporal runs outside the workflow code and records. Event History is Temporal's record of a workflow run.

- **Best evidence, verified by run.** `temporalio` 1.33.0, time-skipping test server, sequential activities, no retries, signals or timers. 1, 2, 5 and 10 activities gave 11, 17, 35 and 65 events. The course run added the break-its: a retry added 0 events, a fired timer 5 and a signal 4. An agent loop that sends its whole conversation to each step reaches the 10 MB warning after about 99 turns at 2,000 bytes per reply, long before the event warning. Source: `orchestration-durable_p02_history_budget.txt`. The formula 5 + 6 × activities matched each count. Sources: `$R/durable/runs/temporal_events_formula.txt`, `temporal_event_types_2activities.txt`.
- **Limits, verified.** "limited to 51,200 Events or 50 MB. It warns you after 10,240 Events or 10 MB." This "applies to all Temporal Workflow Executions, whether on Temporal Cloud or other deployments". At most 10 in-flight Updates and 2000 total Updates. Source: `$R/durable/docs/t_cloud-limits.html`. Payloads warn at 256 KB and fail at 2 MB. Transactions are limited to 4 MB. Source: `t_selfhosted-defaults.html`.
- **Inferred.** The warning arrives after about 1,705 sequential activities, and the hard limit after about 8,532. An agent turn with one model activity and two tool activities is 3 activities, so about 568 turns fit before the warning. Check: export a history from `temporal server start-dev` with retries and heartbeats, and count again.
- **Not run.** Continue-As-New, which starts a fresh history.

Summary: a long agent loop on Temporal needs Continue-As-New.

### 4.20 A long wait resumes on code deployed after it started, so every durable wait needs a versioning plan

- **Best evidence, verified by run.** Temporal `workflow.patched()` let new code replay an old history, see 4.11. DBOS `DBOS.patch()` let an old workflow resume on its old path and return `[1, 2, 3, 4, 5]`. Sources: `temporal_replay_1.33.0.txt`, `$R/durable/runs/dbos_patch_3.0.0.txt`.
- **DBOS patching needs a flag, verified with a gap.** The patched script sets `"enable_patching": True`, `$R/durable/lab/dbos_crash_patched.py`. The report says that without it DBOS raises `DBOSException: enable_patching must be True in DBOS configuration`. That output is not in the saved run file. Label: run output not saved.
- **DBOS 3.0 breaks old processes, verified.** "DBOS 2.x cannot process workflows created by DBOS 3.0." Source: `$R/durable/docs/d_upgrading-3.0.md`.
- **Vendor practice, verified.** Anthropic: "we use rainbow deployments to avoid disrupting running agents, by gradually shifting traffic from old to new versions". Source: `$R/durable/docs/anth_multiagent.html`. Vendor blog.
- **OpenAI Agents SDK, verified today.** The HITL docs advise a version marker stored with the `RunState`. See 4.15.
- **Not checked today.** Temporal's advice to prefer Worker Versioning over patching, and the removal date of legacy Worker Versioning.

Summary: a workflow that waits 3 days runs on the code of day 3.

### 4.21 Engines disagree on what a timed-out human wait does: raise, return null or `None`, or fail the instance

| System | Wait primitive | On timeout | Default timeout | Label |
|---|---|---|---|---|
| Temporal Python | `workflow.wait_condition(fn, timeout=...)` plus a Signal or Update | Raises `asyncio.TimeoutError` | No timer when `timeout=None` | Verified, `$N/src/t_context_1.33.0.py:948-967` |
| DBOS | `DBOS.recv(topic, timeout_seconds)` | Returns `None` | 60 seconds | Verified, `$N/src/d_comm.md:35` and line 40 |
| Cloudflare Workflows | `step.waitForEvent` | "the Workflow will throw an error and the instance will fail" | 24 hours. Range 1 second to 365 days | Verified, `$N/src/cf_events.md:136-156` |
| Inngest | `step.waitForEvent(id, {event, timeout})` | Returns `null`. Inferred from the type `Promise<null \| EventPayload>` | `timeout` in every example | Inferred, `$N/src/i_wait.md:5` |
| AWS Step Functions | `.waitForTaskToken` with `HeartbeatSeconds` | Not checked today | Not checked today | Not checked |
| Restate | Signal, awakeable, or workflow promise | Not checked | Not checked | Not checked |
| LangGraph | `interrupt()` | No built-in timeout found | None found | Not checked. Absence in the docs read |
| OpenAI Agents SDK | `needs_approval` plus stored `RunState` | No timeout found on the HITL page | None found | Verified by absence, `$N/src/oai_hitl.html` |

- **Temporal detail, verified.** Changing `timeout` from `None` to a value, or back, "constitutes a nondeterministic" change. Source: `t_context_1.33.0.py:960`.
- **Cloudflare detail, verified.** Wrap `waitForEvent` in `try...catch` to continue after a timeout. Source: `cf_events.md:156`.
- **Not checked today.** The Inngest warning that events sent before the wait starts are not handled. It is not on the saved `step-wait-for-event` page.

Summary: teach the timeout branch per engine. There is no common behaviour.

## 5. Proposed phase outline

The audit asked to cut the old Phase 1 to what Module 2 did not teach and merge it with Phase 2. The module now has six phases.

| Phase | Title | Concepts | Labs | Runs where, costs what |
|---|---|---|---|---|
| 1 | One agent or many, and what a handoff loses | 4.1 to 4.9 | 1, 2, 3, 4 | Laptop. Free. Lab 2 downloads 199.6 MB once |
| 2 | Checkpoints in agent frameworks | 4.10, 4.13, 4.14, 4.15 | 5, 6 | Laptop. Free. No API key |
| 3 | Replay and determinism in durable engines | 4.10, 4.11, 4.12, 4.19 | 5, 7, 10, 11 | Laptop. DBOS on SQLite. Temporal test server, 65.4 MB once |
| 4 | Side effects that must happen once | 4.12, 4.16, 4.17 | 8, 9, 12, 13 | Laptop, SQLite. Free |
| 5 | Waiting for people, and versioning long waits | 4.15, 4.20, 4.21 | 6, 7, 14 | Temporal time-skipping test server. Free after one download |
| 6 | Failure drills and design review | 4.18, all | 9, drills from section 7 | Laptop. Free |

Phase 1 links built Module 2, 4.1 to 4.3, and does not repeat them. Phase 6 links Module 7 for loop caps.

## 6. Lab inventory and lab ideas

All labs run offline on the learner's Mac unless marked. No API keys. No Docker.

### Prototypes that ran on 2026-09-23

Paths are under `$R`.

| Prototype | Script | Saved output | What it printed |
|---|---|---|---|
| LangGraph crash and resume | `durable/lab/lg_crash.py`, `lg_crash_driver.sh`, `lg_trials.sh`, `lg_trials_sleep.sh` | `durable/runs/lg_crash_resume_1.2.12.txt`, `lg_crash_trials_1.2.12.txt`, `lg_crash_trials_async_sleep.txt`, `lg_async_crash_tables.txt` | Re-run counts per mode, see 4.13 |
| DBOS crash, divergence and patch | `durable/lab/dbos_crash.py`, `dbos_driver.sh`, `dbos_crash_patched.py` | `durable/runs/dbos_crash_resume_3.0.0.txt`, `dbos_patch_3.0.0.txt` | Effects log, `DBOSUnexpectedStepError`, patched result |
| Temporal replay divergence | `durable/lab/temporal_replay.py` | `durable/runs/temporal_replay_1.33.0.txt` | V1 OK, V2 `NondeterminismError`, patched OK |
| Temporal event counts | `durable/lab/temporal_events.py`, `temporal_events_n.py` | `durable/runs/temporal_event_types_2activities.txt`, `temporal_events_formula.txt` | 11, 17, 35 and 65 events |
| Double charge | `durable/lab/double_charge.py` | `durable/runs/double_charge.txt` | 3, 3 and 1 charges, self-test passed |
| RunState replay | `durable/lab/oai_runstate.py` | `durable/runs/oai_runstate_0.22.3.txt` | One refund, then two |
| LangGraph checks | `durable/lab/lg_checks.py` | `durable/runs/lg_checks_1.2.12.txt` | 10007 limit, 2 emails, `[1, 2, 3, 4, 4]`, retry attempts |
| Retry filter table | Not saved | `durable/runs/lg_default_retry_on_1.2.12.txt` | Table in 4.17 |
| Two writers, one key | `multiagent/lg_concurrent_write.py` | `multiagent/lg_concurrent_write_out.txt` | `InvalidUpdateError`, then both refunds |
| Fan-out latency self-test | `multiagent/check_fanout_selftest.py` | `multiagent/check_fanout_selftest_out.txt` | Monte Carlo within 0.19% of m × H_N |
| MAST tally | `multiagent/tally_mast.py`, `tally_mast_norm.py` | `multiagent/tally_mast_out.txt`, `tally_mast_2025_out.txt`, `tally_mast_norm_out.txt` | Table in 4.9 |

A course generator must re-run each prototype at the pinned versions before quoting a number from it.

### Lab designs

1. **Fan-out cost and latency.** Proves 4.3. Replaces old L1 and folds in the useful part of old L2. Inputs: N workers, a latency distribution, prefix and brief tokens, return size and prices. Prints expected and p95 wall time, tokens, cost, and cost per success for N = 1, 3, 5 and 10. A second table uses Google Table 5. Self-test, verified by run: with exponential latency of mean 10 s, the Monte Carlo mean of the maximum matches m × H_N within 0.19% at N = 10. H_N is 1 + 1/2 + ... + 1/N. Break-it, verified by run: a lognormal with σ = 1.5 gives 50.75 s at N = 10 against 29.29 s. Reuse Module 2 `split_budget.py` terms. Run time under 5 s, inferred from the 1.6 s check.
2. **MAST tally.** Proves 4.9. Replaces old L3. Data: `mcemri/MAST-Data`, CC-BY-4.0, `MAD_full_dataset.json`, 199,574,367 bytes, pinned at revision `95118ac951421753cf1deb87ddea3b01e693c41b`. Prints hits and shares per mode, category shares, and a row for the paper figure. Self-test: the 14 shares sum to 100%, and the row count is 1,642. Break-it: load revision `5a82e32347f70a701a3c68637de12f8a0be3de3c` and watch mode 2.5 go to zero. Tally time 0.3 s after download.
3. **Handoff loss.** Proves 4.7. Design only. A scripted conversation holds 10 facts and 5 rules tied to facts. A deterministic summarizer fills a word budget, and facts score above rules. A rule engine acts on every fact it sees and obeys every rule it sees. Prints fact survival, rule survival and forbidden actions at 25, 50 and 100 words and full history. Self-test: full history gives rule survival 1.0 and 0 forbidden actions. The lab shows the mechanism. The rates come from the learner's scoring rule, not from a model. Optional hosted variant, UNVERIFIED: Claude Haiku 4.5 at $1 per million input and $5 per million output tokens, from the pricing page fetched 2026-09-23. 100 handoffs of about 2,000 input and 100 output tokens cost about $0.25. Inferred from those prices.
4. **Two writers, one key.** Proves 4.8. Built from `lg_concurrent_write.py`. Break-it: add a reducer and count refunds. Self-test: plain key raises `InvalidUpdateError`, reducer key returns two refunds. Extension, design only, from old L4: run the refund task as a fixed workflow, as orchestrator-workers and as handoffs with a fake model, and count write actions.
5. **Crash and resume.** Proves 4.10, 4.12 and 4.13. Replaces old L6 and old L9. Built from the LangGraph and DBOS crash prototypes. Prints the saved state and effects log per mode, then re-run counts over 20 trials. Break-it: `durability="exit"`, or `async` with no-work nodes. Then set `NODE_SLEEP=0.05` and see the loss go to 0. Self-test: in `sync`, no step from n1 to n5 appears after `resume:`, and the crashed step appears exactly twice. Each process started in about 1 s. Not timed.
6. **Interrupt and approval replay.** Proves 4.14 and 4.15. Replaces old L5 and old L7. Built from `lg_checks.py` CHECK2 and CHECK3 and `oai_runstate.py`. Break-it: resume the same `RunState` twice. Fix: an approval-key table. Self-test after the fix: one refund, and `emails after resume: 1` when the email moves after `interrupt()`. Whether it makes no network call: inferred from the fake model. Check with networking off.
7. **Replay divergence.** Proves 4.11 and 4.20. Replaces old L14. Built from `temporal_replay.py` and `dbos_crash_patched.py`. Break-it: remove the `patched()` branch, or use `datetime.now()` in a branch condition. Self-test: V1 passes, V2 raises `NondeterminismError`, patched passes. DBOS: unpatched raises `DBOSUnexpectedStepError`, patched returns the result. The Temporal test server binary `temporal-test-server-sdk-python-1.33.0` is 65,436,200 bytes, downloaded once. First start 4.1 s, later 0.1 s.
8. **Double charge.** Proves 4.16. Replaces old L10. Built from `double_charge.py`. Break-it: a fresh `tool_call_id` per attempt. Self-test: 3, 3 and 1 charges. Extension, design only: ten threads retry at once, and the store returns 409 for an in-flight key and 422 for a changed amount.
9. **Loop caps and retry filters.** Proves 4.17 and 4.18. Built from `lg_checks.py` and the retry probe. Break-it: set `LANGGRAPH_DEFAULT_RECURSION_LIMIT=25`. Self-test: the printed limit equals `langgraph._internal._config.DEFAULT_RECURSION_LIMIT`. Save the retry probe script before use. It was not saved today.
10. **History budget.** Proves 4.19. Replaces old L15. Built from `temporal_events_n.py`. Prints events for 1 to 10 activities and the turns that fit under 10,240 and 51,200 events. Self-test: `5 + 6 × activities` matches every count. Break-it: add a retried activity or a timer. The break-it was not run.
11. **Build a small durable engine.** Proves 4.10 and 4.11. Old L8, design only. A journal table in SQLite, a `step(name, fn)` helper and crash injection. Prints side-effect counts over 100 random crashes. Break-it: use `time.time()` in a step name. Self-test: each finished step's effect count is exactly 1.
12. **Outbox relay crash.** Proves 4.12. Old L11, design only. A relay crashes between send and mark-sent. Self-test: delivered is 2 or more, applied by a deduplicating consumer is 1.
13. **Refund saga.** Proves the compensation part of 4.16. Old L12, design only. Refund, email, ticket update, with a failure at step 3. Self-test: final balance equals the start balance.
14. **Approval wait with time skipping.** Proves 4.21 and 4.20. Old L13, design only. A Temporal workflow waits 3 days for a Signal. The Signal arrives on day 2 in one run and day 4 in another. Self-test: the day-4 run takes the timeout branch.

Dropped: old L1, error amplification simulator, because it modelled 17.2x as an error rate. Old L2, cost calculator, folded into Lab 1. Old L3, synthetic MAST traces, replaced by Lab 2. Old L15 replaced by Lab 10.

## 7. Failure stories and case studies

- **Temporal workflows stuck after a deploy.** A workflow task with a nondeterminism error retries until a fix is deployed. Source: `t_py-error-handling.md:173`, verified. A 2022 forum thread asks "How to stop non-deterministic error retry forever?". Fetched 2026-09-17, not re-checked today. No numbers.
- **LangGraph resume re-runs work.** Issue #6792 reports that step 1 runs again and interrupts are duplicated. Title verified today as HTML. Its open or closed state is not checked, because the HTML shows both markers from linked items. Issue #4796, a subgraph node "executing twice", was not re-checked today.
- **OpenAI Agents SDK duplicates.** Issue #4775, RunState pending input duplicated when a session append loses its acknowledgement. Issue #4845, a callable `needs_approval` that failed open. Both from the 2026-09-17 research agent. Not checked today.
- **Anthropic C compiler.** 16 parallel agents overwrote each other's fixes on the Linux kernel. The fix was a GCC oracle that split the work into independent files. Verified, see 4.8. Cost "just under $20,000", about 2,000 Claude Code sessions, model Opus 4.6. One run, no control.
- **Anthropic research system.** The team built resume-from-error support and uses rainbow deployments. Verified, see 4.20. No incident numbers.
- **CircleCI duplicate notifications, 2025-12-02 to 2025-12-03.** A workflow execution change sent duplicate failure emails and Slack messages. The 2026-09-17 author verified the phrase "duplicate notifications". Not checked today. The figure 33,135 appeared only in a search summary. Do not use it.
- **AWS us-east-1 DynamoDB outage, 2025-10-19 to 2025-10-20.** "a latent race condition" in DNS automation applied an old plan and deleted the active one. Lesson: automation that acts on stale state. It is not an AI or workflow engine incident. The 2026-09-17 author verified the quoted phrase. Not checked today.

Moved or dropped: the Replit database deletion moved to Module 7. The Cloudflare 2025-11-18 outage was dropped. It is not a workflow incident.

No company postmortem with numbers was found for an LLM agent that charged or refunded twice. See section 11.

## 8. Primary sources

Status is from `$R/durable/docs/fetch_log_2026-09-23.txt`, the multi-agent report section 6, or `$N/src/`, all on 2026-09-23, unless marked.

### Single agent against several

| Title | Org | Version | URL | Read | Review |
|---|---|---|---|---|---|
| Towards a Science of Scaling Agent Systems | Google Research, Google DeepMind, MIT | v3 2026-04-08 | https://arxiv.org/abs/2512.08296 | Sec 3, 3.1, 4.2, 4.4, Table 5, robustness paragraph | Preprint |
| Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets | Stanford | v2 2026-04-11 | https://arxiv.org/abs/2604.02460 | Sec 5.1, 5.3 | Preprint, under review |
| Debate or Vote | UW-Madison | v2 2025-10-23 | https://arxiv.org/abs/2508.17536 | Table 1 | NeurIPS 2025 |
| Improving Factuality and Reasoning through Multiagent Debate | MIT CSAIL | v1 2023-05-23 | https://arxiv.org/abs/2305.14325 | Table 1 | Venue not checked |
| Single-agent or Multi-agent Systems? Why Not Both? | UIUC | v1 2025-05-23 | https://arxiv.org/abs/2505.18286 | Table 2, Sec 3 | Preprint |
| The Illusion of Multi-Agent Advantage | Salesforce Research and others | v2 2026-06-13 | https://arxiv.org/abs/2606.13003 | Sec 3.1, Figure 2 | Preprint |
| Rethinking the Value of Multi-Agent Workflow | UT Austin, Emory, Northeastern and others | v1 2026-01-18 | https://arxiv.org/abs/2601.12307 | Abstract, Sec 1 | Preprint |
| Why Do Multi-Agent LLM Systems Fail? | UC Berkeley | v3 2025-10-26 | https://arxiv.org/abs/2503.13657 | Figure 1, Table 2, Table 5 | NeurIPS 2025 D&B |
| MAST-Data | UC Berkeley | revision 2026-08-13 | https://huggingface.co/datasets/mcemri/MAST-Data | Card | Dataset |
| Which Agent Causes Task Failures and When? | Penn State, Duke and others | v3 | https://arxiv.org/abs/2505.00212 | Abstract | Venue not checked |
| The Handoff Tax | AWS | v1 2026-08-25 | https://arxiv.org/abs/2608.24358 | Sec 3, 4.1, Table 1 | Preprint |
| Facts Without Rules | UIUC | v1 2026-08-29 | https://arxiv.org/abs/2608.29028 | Abstract | Preprint |
| How we built our multi-agent research system | Anthropic | 2025-06-13 | https://www.anthropic.com/engineering/multi-agent-research-system | Rainbow deployments, resume from error | Vendor. Module 2 owns its numbers |
| Building a C compiler with a team of parallel Claudes | Anthropic | 2026-02-05 | https://www.anthropic.com/engineering/building-c-compiler | Lock files, kernel overwrite | Vendor |
| Building effective agents | Anthropic | 2024, edited later | https://www.anthropic.com/engineering/building-effective-agents | Workflow and agent definitions | Vendor |

### Orchestration shapes

- **Handoffs, OpenAI Agents SDK docs** — https://openai.github.io/openai-agents-python/handoffs/. History defaults, `input_filter`. HTTP 200.
- **`run_config.py`, openai-agents v0.22.3** — https://raw.githubusercontent.com/openai/openai-agents-python/v0.22.3/src/agents/run_config.py. Lines 45 and 374. HTTP 200.
- **Graph API, LangChain docs** — https://docs.langchain.com/oss/python/langgraph/graph-api. Super-steps, `Send`, reducers, and the wrong 1000 at line 1032 of the `.md` copy. HTTP 200.
- **`channels/last_value.py`, langgraph 1.2.12** — https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.12/libs/langgraph/langgraph/channels/last_value.py. Line 61. HTTP 200.

### Checkpointing in agent frameworks

| Source | URL | Focus | Status |
|---|---|---|---|
| LangGraph source, tag 1.2.12 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.12/libs/langgraph/langgraph/ | `_internal/_config.py:32`, `types.py:98, 427, 461, 902`, `pregel/main.py:2603`, `_internal/_retry.py` | 200 |
| LangGraph checkpointers | https://docs.langchain.com/oss/python/langgraph/checkpointers.md | durability modes, pending writes | 200 |
| LangGraph interrupts | https://docs.langchain.com/oss/python/langgraph/interrupts.md | lines 539, 689 | 200 |
| LangGraph functional API | https://docs.langchain.com/oss/python/langgraph/functional-api.md | line 573 | 200 |
| OpenAI Agents SDK human in the loop | https://openai.github.io/openai-agents-python/human_in_the_loop/ | durable `RunState`, version marker | 200 |
| `sqlite_session.py`, openai-agents v0.22.3 | https://raw.githubusercontent.com/openai/openai-agents-python/v0.22.3/src/agents/memory/sqlite_session.py | line 34 | 200 |
| Claude Agent SDK sessions | https://code.claude.com/docs/en/agent-sdk/sessions.md | lines 14, 272, 404 | 200 |
| Claude Agent SDK file checkpointing | https://code.claude.com/docs/en/agent-sdk/file-checkpointing.md | lines 9, 18, 26 | 200 |

### Durable execution engines

| Org | URLs | Focus | Status |
|---|---|---|---|
| Temporal docs | https://docs.temporal.io/cloud/limits, https://docs.temporal.io/self-hosted-guide/defaults, https://docs.temporal.io/workflow-definition.md | limits, replay | 200. The limits `.md` variant is 404 |
| Temporal docs | https://docs.temporal.io/encyclopedia/retry-policies.md, https://docs.temporal.io/develop/python/best-practices/error-handling.md, https://docs.temporal.io/develop/python/best-practices/python-sdk-sandbox.md | retries, stuck tasks, sandbox | 200 |
| Temporal source, tag 1.33.0 | https://raw.githubusercontent.com/temporalio/sdk-python/1.33.0/temporalio/workflow/_context.py, `.../common.py`, `.../workflow/_exceptions.py` | `wait_condition`, `RetryPolicy`, `NondeterminismError` | 200 |
| DBOS docs | https://docs.dbos.dev/python/tutorials/workflow-tutorial.md, https://docs.dbos.dev/python/tutorials/workflow-communication.md, https://docs.dbos.dev/architecture.md, https://docs.dbos.dev/python/tutorials/database-connection.md, https://docs.dbos.dev/python/upgrading.md | determinism, at-least-once, `recv`, SQLite default, 3.0 changes | 200 |
| Inngest docs | https://www.inngest.com/docs-markdown/learn/how-functions-are-executed, https://www.inngest.com/docs-markdown/learn/versioning, https://www.inngest.com/docs-markdown/usage-limits/inngest, https://www.inngest.com/docs-markdown/reference/typescript/v4/functions/step-wait-for-event | memoization, warnings, limits, waits | 200 |
| Restate docs | https://docs.restate.dev/develop/python/durable-steps.md, https://docs.restate.dev/guides/error-handling.md | journal, `ctx.run`, retry default | 200 |
| Cloudflare docs | https://developers.cloudflare.com/workflows/build/events-and-parameters/index.md, https://developers.cloudflare.com/workflows/reference/limits/index.md | `waitForEvent` timeout, limits | 200 |
| AWS docs | https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html, https://docs.aws.amazon.com/lambda/latest/dg/durable-functions.html | exactly-once scope, Lambda replay | 200 |
| Pydantic AI | https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/ | seven engines | 200 |

### Idempotency, outbox, sagas

- **Idempotent requests, Stripe API docs** — https://docs.stripe.com/api/idempotent_requests. Stored result, 24 hours, 255 characters, parameter check. HTTP 200 today.
- **Idempotency-Key draft status, IETF** — https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/. "Expired Internet-Draft". HTTP 200 today.
- **Idempotency-Key draft -07, IETF** — https://www.ietf.org/archive/id/draft-ietf-httpapi-idempotency-key-header-07.txt. 422 and 409 rules. HTTP 200 today.
- **Implementing Stripe-like Idempotency Keys in Postgres, Brandur Leach, 2017** — https://brandur.org/idempotency-keys. Atomic phases, recovery points. Fetched 2026-09-17, not re-fetched today.
- **Transactional outbox and Saga, Chris Richardson** — https://microservices.io/patterns/data/transactional-outbox.html and https://microservices.io/patterns/data/saga.html. Fetched 2026-09-17, not re-fetched today.
- **You Cannot Have Exactly-Once Delivery, Tyler Treat, 2015** — https://bravenewgeek.com/you-cannot-have-exactly-once-delivery/. Fetched 2026-09-17, not re-fetched today.
- **Exactly-Once Semantics Are Possible, Confluent** — https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/. Fetched 2026-09-17, not re-fetched today.

### Issues and incidents

- **OpenAI Agents SDK issue 4254** — https://github.com/openai/openai-agents-python/issues/4254. HTTP 200 as HTML today.
- **LangGraph issues 6792 and 7313** — https://github.com/langchain-ai/langgraph/issues/6792 and https://github.com/langchain-ai/langgraph/issues/7313. HTTP 200 as HTML today. The GitHub API returned a rate-limit error.
- **Temporal forum, stuck workflow thread** — https://community.temporal.io/t/how-to-stop-non-deterministic-error-retry-forever/5694. Fetched 2026-09-17, not re-fetched today.
- **Duplicate Notifications, CircleCI status page** — https://status.circleci.com/incidents/qq3x5734kbw9. Fetched 2026-09-17, not re-fetched today.
- **Summary of the Amazon DynamoDB Service Disruption, AWS** — https://aws.amazon.com/message/101925/. Fetched 2026-09-17, not re-fetched today.

## 9. Tools and versions to pin

PyPI rows were checked on 2026-09-23. Sources: `$R/durable/pypi_versions_2026-09-23.txt` and `$R/multiagent/pypi_versions_2026-09-23.txt`. npm and GitHub rows marked "2026-09-17" were not re-checked today.

| Tool | Version | Release date | Source | Notes |
|---|---|---|---|---|
| langgraph | 1.2.12 | 2026-09-21 | PyPI, today | Recursion default 10007. Durability default `"async"` |
| langgraph-checkpoint | 4.2.0 | 2026-08-07 | PyPI, today | |
| langgraph-checkpoint-sqlite | 3.1.1 | 2026-07-30 | PyPI, today | Used in Lab 5 |
| langchain | 1.4.2 | 2026-09-18 | PyPI, today | `create_agent` limit 9,999 |
| openai-agents | 0.22.3 | 2026-09-17 | PyPI, today | Pre-1.0. Lab 6 runs offline with a fake model |
| claude-agent-sdk, Python | 0.2.158 | 2026-09-23 | PyPI, today | Released on research day. Re-check |
| temporalio, Python | 1.33.0 | 2026-09-15 | PyPI, today | Test server binary 65,436,200 bytes |
| temporalio-openai-agents | 1.0.0 | 2026-09-16 | PyPI, today | Not tested |
| dbos, Python | 3.0.0 | 2026-09-16 | PyPI, today | SQLite by default. 2.x cannot read 3.0 workflows |
| restate-sdk, Python | 1.0.5 | 2026-09-02 | PyPI, today | Needs a server binary. Not tested |
| inngest, Python | 0.5.19 | 2026-06-23 | PyPI, today | Not tested |
| pydantic-ai | 2.48.0 | 2026-09-23 | PyPI, today | Released on research day. Seven durable engines |
| aws-durable-execution-sdk-python | 2.0.1 | 2026-09-18 | PyPI, today | Not tested |
| crewai | 1.15.22 | 2026-09-16 | PyPI, today | Loop default not checked |
| autogen-agentchat | 0.7.5 | 2025-09-30 | PyPI, today | No release in a year. Status not checked |
| huggingface-hub | 1.32.0 | 2026-09-17 | PyPI, today | Optional, download by revision in Lab 2 |
| inngest, npm | 4.21.0 | not checked | npm, per the audit on 2026-09-23 | |
| wrangler | 4.136.3 | not checked | npm, per the audit on 2026-09-23 | Local Workflows are emulated |
| Temporal CLI | v1.9.1 | 2026-09-14 | 2026-09-17 | `temporal server start-dev` |
| Temporal Server | v1.32.0 | 2026-09-11 | 2026-09-17 | Legacy Worker Versioning removal planned |
| Restate Server | v1.7.10 | 2026-09-14 | 2026-09-17 | |
| @dbos-inc/dbos-sdk | 5.0.2 | 2026-09-16 | 2026-09-17 | |
| @aws/durable-execution-sdk-js | 2.4.0 | 2026-09-08 | 2026-09-17 | |

## 10. Open questions and disagreements

- **Which budget rule did Google v3 use?** Section 4.1 says matched iterations. Table 5 and Section 4.2 say matched tokens, about 4,800 per trial. Both can be true if iterations were set to hit a token target. Not resolved.
- **Does multi-agent help on research tasks?** Anthropic reports +90.2% on an internal eval with more tokens spent. Google v3 reports +0.2% to +9.2% on BrowseComp-Plus with the budget matched. Salesforce reports that automatic designs lose to voting there. Inferred: the extra tokens explain the gap, as Anthropic's own 80% variance finding suggests. Module 2, 4.1 teaches the Anthropic side.
- **Debate against voting.** Du 2023 found debate above voting with ChatGPT and 3 agents. Choi 2025 found voting above debate with 7B to 8B models and 5 agents. Model, agent count and data differ.
- **UIUC cost savings.** The abstract says up to 20%. The introduction says up to 88.1%. Not resolved.
- **MAST Figure 1 against the public data.** No normalization reproduces the figure. The figure may come from an earlier label set.
- **LangGraph docs against code.** Docs: 1000 from 1.0.6. Code: 10000 at 1.0.6 and 10007 from 1.2.0. Teach the code and cite the tag.
- **"Exponential" against quadratic.** The interrupts docs say exponential. The run shows quadratic growth. Teach the measured count.
- **Strict against lenient determinism.** Temporal and DBOS fail on a changed order. Inngest warns and continues. They trade stuck runs for runs that may mix old and new logic.
- **Restate's default retry.** One paragraph says the default retries "a limited number of times", then pauses. The same page later says Restate "will retry undefinitely" when no policy is set. Source: `$R/durable/docs/r_error-handling.md:46` and line 81.
- **Retry by class against retry by status.** LangGraph retries unknown exception classes, including HTTP 400. Temporal retries all activity failures. DBOS retries nothing until you opt in.
- **Exactly-once.** AWS Step Functions Standard and DBOS transactions claim exactly-once. Both mean inside their own system. External side effects stay at-least-once.
- **Timeout behaviour.** Temporal raises. DBOS returns `None`. Inngest returns `null`, inferred. Cloudflare fails the instance.
- **Inngest units.** The limits page says `4MiB` in the table and `4MB` in the prose. Verified today, `$N/src/i_limits.md` lines 27 and 52.
- **Temporal patching against Worker Versioning.** The 2026-09-17 dossier said Temporal recommends Worker Versioning. Not checked today.

## 11. Things I could NOT verify

| Claim | Check that would settle it |
|---|---|
| Whether Anthropic's 90.2% is relative or absolute | An Anthropic statement or paper |
| A company postmortem with numbers for an LLM agent that duplicated a charge or refund | A primary postmortem from a named company |
| Why MAST-Data does not reproduce Figure 1, and the mapping of Figure 1 per-mode values to names | The MAST repository's analysis scripts, or ask the authors |
| The judge model and question counts in the Stanford study | The code release or the authors |
| Per-benchmark numbers of arXiv 2601.12307 and Salesforce Table 4 | Grep the tables in the saved text |
| Facts Without Rules, Handoff Debt and Repair or Resample beyond the abstract | Read Sections 4 and 5 |
| Events per activity on a real Temporal server with retries and heartbeats | Run `temporal server start-dev`, export a history with a retried activity, count events |
| Restate replay behaviour by run | Install the Restate server binary and repeat Lab 5 |
| Inngest lenient determinism by run | Run the Inngest dev server, reorder two steps mid-run, read the log |
| The LangGraph `async` loss with `AsyncSqliteSaver` or Postgres | Repeat Lab 5 with those savers on a throwaway Postgres cluster |
| Why `get_state` showed `next=()` after an `async` crash | Read `langgraph/pregel/_loop.py` |
| The current state of LangGraph issue 6792 | GitHub API with a higher rate limit, or a browser |
| Whether two concurrent `Command(resume=...)` calls resume one interrupt twice | Two threads resume one thread ID with `SqliteSaver`. Count effects |
| The DBOS `enable_patching` exception text. The report quotes it, but the run file does not hold it | Re-run `dbos_crash_patched.py` without the flag and save the output |
| The retry probe script behind `lg_default_retry_on_1.2.12.txt` | Save the script and re-run it |
| That the crashed LangGraph node re-ran in all 20 trials. The file records it for the last trial only | Log the crashed-step count per trial |
| DBOS 3.0 step `timeout_seconds` semantics | Read the DBOS decorators reference and run a step that sleeps past the timeout |
| That Lab 6 makes no network call | Run it with networking off |
| Inngest returns `null` on timeout | Run the Inngest dev server with a short timeout |
| Inngest warning that events sent before the wait are missed | Find the page that states it today |
| AWS Step Functions task-token timeout behaviour and the 25,000-event history quota | Fetch the service quotas and task-token pages |
| Restate timeout behaviour for signals and awakeables | Read the Restate external-events page |
| Built-in approval timeouts in LangGraph | An absence in the docs read, not proof. Read the source |
| Cloudflare Workflows versioning of running instances | No page found |
| Temporal Worker Versioning advice and the legacy removal date | Fetch the Worker Versioning page and the server release notes |
| AWS Lambda durable functions launch date and regions | Fetch the AWS What's New post |
| CrewAI and Inngest AgentKit loop caps | Fetch their source at the current tag |
| Whether `temporalio.contrib.openai_agents` is deprecated now that the separate package exists | Read the package README and the SDK changelog |
| The Replit record counts | Moved to Module 7 |
| Anthropic's "up to 90%" research time cut | No baseline is published. It cannot be verified |

## 12. Notes for the course generator

- Do not write "multi-agent is X% better". Every number needs its benchmark, architecture, budget rule, models and paper version.
- Do not teach 17.2x as an error rate. Teach the 22.7% factual-error reduction with a verifier.
- Do not teach β = −0.236 or the 45% threshold as confirmed. Teach the direction.
- Do not teach MAST category shares as measured facts. Use the mode names.
- Do not re-teach the Anthropic 90.2%, the 15x ratio or split-or-file. Link Module 2, 4.1 to 4.3.
- Do not say LangGraph resumes at the line of `interrupt()`. It restarts the node.
- Do not say LangGraph's default recursion limit is 1,000. It is 10007 at 1.2.x. Link Module 7 for loop caps.
- Do not say `async` durability is always a small risk. Show the fast-node case.
- Do not use `tool_call_id` as an idempotency key. Derive keys from workflow ID and step ID.
- Do not call the Idempotency-Key header a standard.
- Do not say any engine gives exactly-once side effects in external systems.
- Do not state one timeout behaviour for all engines. Use the table in 4.21.
- Re-run every prototype and save its output before quoting it. Three outputs are missing: the retry probe script, the DBOS `enable_patching` error, and the per-trial crashed-step count.
- Fastest to go stale: `claude-agent-sdk` and `pydantic-ai`, both released on research day. Also DBOS 3.0 APIs, the MAST-Data revision, and the Google and Stanford paper versions.
- Labs 7, 10 and 14 download the Temporal test server once, 65.4 MB. Say so, and give Lab 11 as an offline fallback.

## 13. Refresh log 2026-09-23

### Changes

1. **Section 4 rewritten as 21 claims.** Old topic headings 4.1 to 4.7 are gone. Audit fix 1 and brief rule 1. Every `[V]` and `[V-agent]` label was replaced by verified, inferred or not checked. The audit counted 56 `[V-agent]` and 21 `[V]` labels in the old text.
2. **Old `[V-agent]` facts checked again today.** Verified today: Temporal payload, transaction and Update limits, `$R/durable/docs/t_cloud-limits.html` and `t_selfhosted-defaults.html`. Temporal sandbox quote, `$N/src/t_sandbox.md:53`. LangGraph durability modes, pending writes, interrupt index matching and functional API re-run, `$R/durable/src/` and `$R/durable/docs/`. OpenAI `RunState` HITL docs and `SQLiteSession` default, `$N/src/oai_hitl.html` and `oai_sqlite_session_0.22.3.py:34`. Claude Agent SDK sessions and file checkpointing, `$N/src/cas_sessions.md` lines 14 and 272, `cas_filecp.md` lines 18 and 26. Cloudflare Workflows step and payload limits, `$N/src/cf_limits.md` lines 31 and 35. Inngest limits, `$N/src/i_limits.md`. AWS Lambda durable functions replay and one-year limit, `$N/src/aws_lambda_durable.html`. Stripe parameter check, `$R/durable/docs/stripe_idempotent.html`. IETF 422 and 409 rules, `$N/src/ietf_07.txt`. Anthropic 80% variance, `$R/multiagent/anthropic_mars.txt`, now owned by Module 2. MAST κ = 0.77 and Table 5, `$R/multiagent/2503.13657v3.txt`.
3. **Old `[V-agent]` facts not checked today, now labelled so.** The list: Brandur retention hours, the outbox and saga pages, Tyler Treat and Confluent. Also Temporal Worker Versioning advice, Temporal dev server ports and the Temporal HITL recipe timeout. Also Cloudflare `waitForApproval`, CodeAct Table 3 and the design-patterns paper. CodeAct and the design-patterns paper left section 4, because Module 7 owns plans as code and Module 16 owns the security use.
4. **Overlap rebuilt against built Module 2.** Phase 4 headings from `grep -n '^## '`: 4.1 at line 54, 4.2 at line 235, 4.3 at line 339 of `context-engineering-phase-04-split-or-file.md`. The Anthropic 90.2%, 4x, 15x, 80% variance and Cognition items left section 4 and now link Module 2. Audit fix 3.
5. **Module 7 and Module 8 ownership.** Loop caps, the agent loop and plans as code point to the Module 7 dossier, 4.3, 4.11 and 4.13. Module 7 has no built phase file yet, verified by `ls agent-harness/`. A2A and cross-vendor task state point to Module 8. Audit fix 7 is closed by giving task state across vendors to Module 8.
6. **Phase outline cut from 7 to 6.** Old Phases 1 and 2 merged. Audit fix 3.
7. **Lab list replaced.** Section 6 now lists the 11 prototypes that ran today with their saved outputs, and 14 lab designs. Old L1 dropped. Old L2 folded into Lab 1. Old L3 replaced by Lab 2. Old L15 replaced by Lab 10. Old L5, L6, L7, L9, L10 and L14 became Labs 6, 5, 6, 5, 8 and 7. Old L8, L11, L12 and L13 kept as Labs 11 to 14.
8. **Three lab blockers closed.** Audit fix 5. DBOS 3.0 migration read, `d_upgrading-3.0.md`. Old L7 runs offline with a fake model, `oai_runstate_0.22.3.txt`. Events per activity measured, `temporal_events_formula.txt`.
9. **Failure stories trimmed.** Replit moved to Module 7. The Cloudflare outage dropped. DynamoDB kept with its stale-state lesson. Audit fix 4.
10. **New evidence added.** Papers: Google v3 mean gain and Table 5, Debate or Vote, Handoff Tax and Facts Without Rules. Runs: the MAST-Data tally, the LangGraph concurrent write, and the LangGraph, DBOS, Temporal and OpenAI crash and replay runs. Also the LangGraph retry filter, `TimeoutPolicy` and the Temporal event formula.
11. **Sections 3, 8, 9, 10 and 11 rebuilt** from today's reports and fetches. Every row says whether it was checked today.
12. **Anchors re-grepped.** 99 of 99 found, `$N/anchors_result.tsv`.

### Corrections to the 2026-09-17 text

| # | Old claim | Correction | Evidence |
|---|---|---|---|
| 1 | Old 4.2: LangGraph default recursion limit is 1,000 from 1.0.6 | 25 up to 1.0.5, 10000 at 1.0.6 to 1.1.x, 10007 from 1.2.0 to 1.2.12. The docs are wrong | `$R/durable/src/cfg_1.0.5.py`, `cfg_1.0.6.py`, `lg__internal__config.py:32`. Run: `lg_checks_1.2.12.txt` CHECK1 |
| 2 | Old 4.1: "Independent agents amplify errors 17.2x" as an error rate | In v3, 17.2x is extra work in traces. The task-level factor is 1.1 to 1.3. The regression term has p = 0.658 | `2512.08296v3.txt`, Sec 3.1 and 4.4 |
| 3 | Old 4.1: capability ceiling β = −0.236, p = 0.004 | It is an interaction term. The paper calls it directional under cluster-robust errors and suggestive after Holm correction | `2512.08296v3.txt`, robustness paragraph, CI [−0.396, −0.076] |
| 4 | Old 4.1: v3 matched iterations, not tokens | v3 states both rules in different sections | `2512.08296v3.txt` lines 609 to 610 and 1178 to 1179 |
| 5 | Old 4.1: UIUC measured MetaGPT 67.0 to 87.7 with ChatGPT | Quoted from earlier papers. Only the Gemini column is the authors' run. "10.7%" should be 20.7 points. "9%" should be 8 points | `2505.18286v1.txt`, Table 2 |
| 6 | Old 4.1: Salesforce, abstract only | Verified in Sec 3.1. CoT-SC is 5 samples. Exception on HLE-Math. Gemini-2.5-Pro has 1 run | `2606.13003v2.txt` |
| 7 | Old 4.3: MAST shares 44.2 / 32.3 / 23.5, inferred from summing per-mode shares | The paper prints them in Figure 1. The public data gives 36.9 / 33.1 / 30.0 at the current revision and 40.6 / 36.3 / 23.1 at the old one. An LLM judge made the labels | `tally_mast_out.txt`, `tally_mast_2025_out.txt`, `hf_mast_README.md` |
| 8 | Old 4.3: MAST interventions 25.0, 34.4, 40.6 as absolute points | Correct, and the set is 32 tasks. The gains are 3 and 5 tasks | `2503.13657v3.txt`, "32 different tasks" |
| 9 | Old 4.4: with `"async"`, "a small risk" of lost checkpoints | With no-work nodes, 3 or 4 of 5 finished steps re-ran in 20 of 20 trials. With 50 ms nodes, 0 of 10 | `lg_crash_trials_1.2.12.txt`, `lg_crash_trials_async_sleep.txt` |
| 10 | Old 4.4: `while True` plus `interrupt()` replays earlier iterations, carried as exponential | Quadratic. 4 interrupts gave `[1, 2, 3, 4, 4]`, 14 runs | `lg_checks_1.2.12.txt` CHECK3 |
| 11 | Old 4.4: `Durability` at `types.py:89`, docstring at `types.py:864`, tag 1.2.11 | At tag 1.2.12: `types.py:98` and `types.py:902`. Values unchanged | `$R/durable/src/lg_types.py` |
| 12 | Old 4.4: OpenAI `RunState` round trip, old lab L7 "inferred to work offline" | Runs offline. Also: resuming the same state twice runs the tool twice | `oai_runstate_0.22.3.txt` |
| 13 | Old 4.5 table: DBOS versioning by `DBOS.patch()` | Needs `"enable_patching": True`. The error text without it is in the report only | `dbos_crash_patched.py`, `dbos_patch_3.0.0.txt` |
| 14 | Old 4.5: Pydantic AI supports five durable engines | Seven. Five co-maintained: Temporal, DBOS, Prefect, Restate, AWS Lambda. Two external: Kitaru, Apache Airflow | `$N/src/pai_durable.html` |
| 15 | Old 4.5: Step Functions Express is at-least-once "when asynchronous" | The page today says "Express Workflows use an at-least-once model" with no qualifier in that sentence | `$N/src/aws_sfn_types.html` |
| 16 | Old 4.5: Cloudflare Workflows 10,000 steps on Paid | Correct. The Free plan limit is 1,024 | `$N/src/cf_limits.md:35` |
| 17 | Old 11: Temporal event counts per activity unknown | 6 per sequential activity plus 5 fixed, on the test server | `temporal_events_formula.txt` |
| 18 | Old 11: dbos 3.0 migration not read | 2.x cannot process 3.0 workflows. `@DBOS.transaction` and in-memory queues removed | `d_upgrading-3.0.md` |
| 19 | Old 9: versions | `langgraph` 1.2.12, `openai-agents` 0.22.3, `claude-agent-sdk` 0.2.158, `pydantic-ai` 2.48.0, `aws-durable-execution-sdk-python` 2.0.1 | `$R/durable/pypi_versions_2026-09-23.txt` |
| 20 | Old 4.7: Inngest warns that events sent before the wait are not handled | Not on today's `step-wait-for-event` page. Now not checked | `$N/src/i_wait.md` |
| 21 | Old 6: L1 models 17.2x as an error rate | Dropped. Lab 1 replaces it | Correction 2 |

### Corrections to the 2026-09-23 research reports, found while merging

1. **The durable report says the crashed node ran again in 20 of 20 `sync` trials.** The trials file records the crashed-node re-run for the last trial only: "re-ran in last trial: 1". The per-trial count of n1 to n5 is recorded for all 20. Evidence: `$R/durable/runs/lg_crash_trials_1.2.12.txt`. 4.12 now says so.
2. **The durable report cites a run for the DBOS `enable_patching` error.** `dbos_patch_3.0.0.txt` holds only the patched result. The string `enable_patching` appears in `dbos_crash_patched.py`, not in any run file. Evidence: `grep -c enable_patching` gave 0 for the run file. 4.20 labels it "run output not saved".
3. **The durable report cites `lg_default_retry_on_1.2.12.txt` as a run.** The output is saved. The script that printed it is not in `$R/durable/lab/`. Evidence: `grep -l default_retry_on $R/durable/lab/*` found nothing.
4. **The durable report quotes "Transactions commit _exactly once_" without the 3.0 change.** DBOS 3.0 removed `@DBOS.transaction`. Datasources carry "the same exactly-once guarantees". Evidence: `d_upgrading-3.0.md` lines 22 to 24.

### Corrections found while building the course

The six phases of the course were written, fact checked and joined on 2026-09-23. These rows correct this dossier. `runs/` means `scratchpad/runs/orchestration-durable_`. The course text in `orchestration-durable/` is the reference.

| # | Old claim in this dossier | Correction | Evidence |
|---|---|---|---|
| 1 | 4.13: `async` with no-work nodes re-ran 3 or 4 of 5 finished nodes | The course run gave 2 to 4 in 20 of 20 trials, mean 3.0. With 500 ms nodes and a crash right after a node returned, `async` still re-ran that node in 3 of 10 and 6 of 10 trials | `runs/p01_lg_trials.txt`, `runs/p01_lg_crash_early.txt`, `runs/p01_lg_crash_early_2.txt` |
| 2 | 4.11: determinism means the same steps "with the same inputs" | Engines compare step names and positions, not inputs. A changed amount replayed with no error | `dbos/_sys_db.py:3191` at 3.0.0; `runs/coherence_temporal_replay.txt`, `replay with RefundV1NewAmount: OK` |
| 3 | 4.5 taught "a high single-agent score predicts that adding agents helps less" next to the robust baseline term | The baseline term is a task-difficulty proxy with no agent count. The "helps less" reading rests on the interaction term: cluster-robust p 0.105, Holm p 0.084 | `2512.08296v3.txt`, Table 4, Tables 14 and 15, lines 2560 to 2600 |
| 4 | 4.5: β = −0.236 with p = 0.004 cited without its place | It is in the v3 introduction, line 153. "17.2×" is at line 156. Neither is in the v3 abstract | `2512.08296v3.txt` lines 150 to 158 |
| 5 | 4.1 and section 10: the iterations rule is in "Section 3" | It is in Section 4.1 | `2512.08296v3.txt` line 609 |
| 6 | 4.3: "1.6–6.2× token budgets relative to single-agent" | The sentence ends "at matched performance". Table 5 columns imply Hybrid spent 4.83 times the tokens per trial, inferred | `2512.08296v3.txt` line 948; `runs/p05_scaling_table5.txt` |
| 7 | 4.1: PlanCraft trace example read as the Independent −70.0% design | The paper's trace example is a Centralized team, −50.3% | `2512.08296v3.txt` Section 4.2; Phase 5 section 5.1 |
| 8 | 4.6: studies read as budget-matched | Only Google v3 and Stanford fixed a budget for every system | Phase 5 introduction and sections 5.2 and 5.4 |
| 9 | 4.15 did not say what the saved `RunState` records per call | It stores `executed` and `completed` per call ID, as of the save. A resume does not write them back | `agents/run_state.py` lines 1366 to 1376 at v0.22.3 |
| 10 | 4.15 and 4.16: a claimed key makes the side effect happen once | A claim before the work gives at most once. A crash after the claim left 0 refunds and a stuck `claimed` row | `runs/p04_approval_replay.txt`, `refunds: 0`; Phase 3 section 3.1 |
| 11 | 4.17: the table showed no `requests` row | LangGraph 1.2.12 retries every `requests.HTTPError`, including 404, because a response with status 400 to 599 is falsy | `runs/p03_retry_filter_part1.txt`; `requests/models.py:835` and line 1156 at 2.34.2 |
| 12 | 4.12: the crashed step may run again without limit | DBOS 3.0.0 stops after `max_recovery_attempts`, 100 by default, and moves the run to a dead-letter status. Read from source, not run | `dbos/_registrations.py:10`, `dbos/_core.py:1229` |
| 13 | 4.19: the retry and timer break-it was not run | Run: a retry adds 0 events, a fired timer 5, a signal 4. The 10 MB warning comes before the event warning for a chat loop | `runs/p02_history_budget.txt` |
| 14 | 4.11: what a broken replay leaves | Temporal keeps the run `RUNNING`. DBOS ends it in `ERROR` and does not resume it | `runs/p02_temporal_stuck.txt`, `runs/p02_dbos_diverge.txt` |
| 15 | 4.20: the `enable_patching` error text was not in a run file | Now run: `DBOSException: DBOS Error: enable_patching must be True in DBOS configuration` | `runs/p02_dbos_diverge.txt` |
| 16 | 4.9 gave only the Figure 1 shares | The paper's Figure 4 gives 41.8%, 36.9% and 21.3% on 210 traces | `2503.13657v3.txt` lines 631 to 635 |

### Anchor re-check

99 anchor strings across 4.1 to 4.21 were grepped in the saved source or run files on 2026-09-23. All 99 were found. Six strings are split by a line break in the extracted text, so a shorter part was grepped. The list names the concept, the count of matching lines, the file and the string. Files: `$N/anchors.tsv` and `$N/anchors_result.tsv`.

Summary: section 4 now holds 21 claims with conditions and real labels. Multi-agent evidence that Module 2 teaches is linked, not repeated. The lab list reflects what ran today. 21 corrections to the old text and 4 to today's reports are logged above.

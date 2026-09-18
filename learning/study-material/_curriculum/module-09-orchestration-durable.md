# Module 09 — Orchestration, state, and durable execution

Research date: 2026-09-17. Status: research dossier, not course material.

## 1. What this module is for

This module teaches how to keep a long agent task correct when processes crash, deploys happen, and humans take days to answer. An agent that refunds money or sends email has side effects. A retry or a resume can repeat those side effects. Durable execution means the runtime records each finished step, so after a crash the task continues from the last recorded step instead of from the start. The module also teaches when to split work across several agents, because the measured evidence now says a single agent often matches a multi-agent system at equal budget. Without this module, an engineer ships agents that lose state on restart, charge a customer twice, or stay stuck after a code change.

## 2. Scope

### In scope

- Single-agent versus multi-agent systems, with measured studies and their conditions.
- Orchestration shapes: workflows versus agents, orchestrator-workers, handoffs, graphs, and plans as code as an orchestration shape.
- Checkpointing and resumption in LangGraph, the OpenAI Agents SDK, and the Claude Agent SDK.
- Durable execution engines: Temporal, Inngest, Restate, DBOS, Cloudflare Workflows, AWS Step Functions, and AWS Lambda durable functions.
- Determinism rules, replay, versioning of running workflows, and history limits.
- Idempotency keys, the outbox pattern, sagas with compensating actions, and the limits of "exactly-once".
- Human approval as a workflow state: signals, timers, timeouts, and what each engine does when a wait expires.
- Failure stories: duplicated side effects, lost state, and stuck workflows.

### Out of scope, and where it lives instead

| Topic | Where it lives |
|---|---|
| Retries, jitter, retry amplification at the call level | Module 1, section 5.3 |
| Failover and fallback between models | Module 1, section 5.6 |
| Quality incidents and postmortems in general | Module 1, section 6.3 |
| The in-process agent loop, tool execution by the harness, plans written as code | Module 7, harness engineering |
| Sub-agent context isolation and compaction | Module 2, context engineering |
| Tool design and code execution as a tool | Module 6 |
| Long-term memory stores | Module 10 |
| Trajectory evals for multi-agent runs | Module 12 |
| Tracing of workflow and agent spans | Module 15 |
| Plan-then-execute as a prompt-injection defence | Module 16 |
| Approval screen design and the suggest, confirm, execute gradient | Module 19 |

### Overlap with earlier modules

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| Retries with backoff and jitter | Module 1, 5.3 | Retries across process restarts. Why a retried step needs an idempotency key. |
| Fallbacks | Module 1, 5.6 | Compensating actions when a later step fails after an earlier step had an effect. |
| Incident review | Module 1, 6.3 | Incidents specific to workflows: nondeterminism after deploy, duplicate notifications. |
| Agent loop | Module 7, topic "the harness runs tools" | Moving the loop into a durable workflow. Each model call and tool call becomes a recorded step. |
| Plans as code | Module 7, topic "plans written as code" | Only the orchestration view: a fixed plan is a workflow. No repeat of the code-action material. |
| Sub-agents | Module 2, topic "sub-agent isolation" | The cost and failure evidence for multi-agent systems, not the context mechanics. |

The Module 7 dossier did not exist when this file was written. Link to Module 7 by topic, and fix the section numbers when its coverage file exists.

## 3. What changed recently

| Change | Date | Source | Why it matters |
|---|---|---|---|
| Anthropic multi-agent research system post | 2025-06-13 | Anthropic engineering | Main vendor evidence for multi-agent. 15x tokens versus chat. |
| Cognition "Don't Build Multi-Agents" | 2025-06-12 | Cognition blog | Main argument against. No numbers. |
| LangGraph 1.0.0 on PyPI | 2025-10-17 | PyPI. The blog post is dated 2025-10-22. | Stable durability modes and interrupts. |
| MAST taxonomy v3, NeurIPS 2025 Datasets and Benchmarks | 2025-10-26 | arXiv 2503.13657 | 14 failure modes, 1,642 traces. |
| AWS Lambda durable functions launched | 2025-12-02 | AWS What's New | A new checkpoint-and-replay engine inside Lambda. |
| Google "Towards a Science of Scaling Agent Systems" v1 | 2025-12-09. v3 on 2026-04-08. | arXiv 2512.08296 | 260 configurations. Numbers changed between versions. |
| Temporal AI SDK by Vercel integration | 2026-01-20 | Temporal changelog | Public Preview for TypeScript. |
| Temporal OpenAI Agents SDK integration GA, Python | 2026-03-23 | Temporal blog update line | Moved to package `temporalio-openai-agents` 1.0.0 on 2026-09-16. |
| Stanford equal-thinking-budget study | 2026-04-02 | arXiv 2604.02460 | Single agent matches or beats multi-agent on multi-hop QA at equal budget. |
| Cognition "Multi-Agents: What's Actually Working" | 2026-04-22 | Cognition blog | Position changed: multi-agent works when writes stay single-threaded. |
| Temporal Worker Deployment APIs GA | 2026-04-29 | Temporal server v1.31.0 release notes | Pinned versions are now the recommended way to deploy workflow code. |
| Salesforce "Illusion of Multi-Agent Advantage" | 2026-06-11 | arXiv 2606.13003 | Auto-generated multi-agent systems lose to CoT-SC at up to 10x cost. |
| Temporal server v1.32.0, last release with legacy Worker Versioning | 2026-09-11 | GitHub release notes | Removal planned for v1.33. |
| dbos 3.0.0, major release | 2026-09-16 | PyPI and GitHub release | Schema change. Removed in-memory queues and admin server. |
| IETF Idempotency-Key draft expired | -07 dated 2025-10-15, expired 2026-04-18 | IETF Datatracker | Not an RFC. Do not call it a standard. |

## 4. Core concepts, with verified facts

Labels: **[V]** verified in raw text or source by me on 2026-09-17. **[V-agent]** verified in raw text by a research agent, not re-checked by me. **[I]** inferred, with the basis named. **[NC]** not checked.

### 4.1 Single agent or several agents

A multi-agent system runs more than one model loop, and the loops pass work to each other. The evidence says this helps when the work splits into parallel read tasks and the system may spend more tokens. When the budget is held equal, or the task is sequential, a single agent usually matches or wins. Every number below depends on its benchmark, its models, and how the budget was matched.

- Anthropic reports that a system with a Claude Opus 4 lead and Claude Sonnet 4 subagents "outperformed single-agent Claude Opus 4 by 90.2% on our internal research eval". The eval is internal and unpublished. The post does not say whether 90.2% is relative or absolute. Source: Anthropic, "How we built our multi-agent research system", 2025-06-13. [V]
- The same post says "token usage by itself explains 80% of the variance" in BrowseComp. Three factors together explain 95%. [V-agent].
- The same post says agents use "about 4× more tokens than chat interactions, and multi-agent systems use about 15× more tokens than chats". [V]
- Cognition's two principles: "Share context, and share full agent traces, not just individual messages" and "Actions carry implicit decisions, and conflicting decisions carry bad results". Source: Walden Yan, Cognition, 2025-06-12. [V]. No measurements in the post.
- Cognition's 2026 follow-up says multi-agent systems "work best today when writes stay single-threaded and the additional agents contribute intelligence rather than actions". It reports that Devin Review catches an average of 2 bugs per PR, with "roughly 58%" severe. The method and sample size are not given. Source: Cognition, 2026-04-22. [V]. Vendor figures.
- Google Research and others, arXiv 2512.08296 v3: 260 configurations, 6 benchmarks, 5 architectures, 9 models from the GPT-5, Gemini 2.x, and Claude 3.7 to 4.5 families. Their model picks the best architecture for 87% of held-out configurations. Cross-validated R² is 0.373. [V]
- Same paper, v3: Centralized multi-agent gains +80.8% on Finance-Agent. Independent multi-agent loses 70.0% on PlanCraft. All multi-agent variants lose 2% to 15% on SWE-bench Verified. [V-agent]
- Same paper, v3: Independent agents amplify errors 17.2x. Centralized verification cuts this to 4.4x. [V]
- Same paper, v3: when single-agent accuracy is above about 45%, more agents give negative returns. β = −0.236, p = 0.004. [V-agent]
- Same paper: v3 matched "maximum total iterations", not tokens. [V]. v1 used 180 configurations and reported R² 0.513. [V-agent]. Always cite the version.
- Tran and Kiela, Stanford, arXiv 2604.02460: "SAS is the best-performing system or statistically indistinguishable from the best for all budgets except the lowest one (100 tokens)". Conditions: FRAMES and 4-hop MuSiQue, Qwen3-30B-A3B, DeepSeek-R1-Distill-Llama-70B, Gemini 2.5 Flash and Pro, thinking budgets from 100 to 10,000 tokens. Preprint under review. [V]
- Gao and others, UIUC, arXiv 2505.18286: the multi-agent gain shrinks with a stronger model. MetaGPT on HumanEval went from 67.0 to 87.7 with ChatGPT, but from 90.2 to 93.2 with Gemini-2.0-Flash. Multi-agent used 4 to 220 times more input tokens. Table 2 of that paper has arithmetic errors. [V-agent]
- Salesforce Research and others, arXiv 2606.13003: auto-generated multi-agent systems "consistently underperform CoT-SC despite being up to 10x more expensive". [V-agent], abstract only.
- OpenAI's practical guide: "Our general recommendation is to maximize a single agent's capabilities first." Source: OpenAI, "A practical guide to building agents", 2025. [V-agent]
- LangChain: "Multi-agent systems that primarily "read" are easier than those that "write"". Source: Harrison Chase, LangChain blog, 2025-06-16. [V-agent].

### 4.2 Orchestration shapes

A workflow follows paths that the code fixes in advance. An agent chooses its own next step. Most production systems mix both. Handoffs pass control to another agent. Agents-as-tools keep control in one manager.

- Anthropic definitions: "Workflows are systems where LLMs and tools are orchestrated through predefined code paths." Agents "dynamically direct their own processes and tool usage". Pattern names: prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer. Source: Anthropic, "Building effective agents", 2024-12-19. [V-agent]. The live page was edited after publication and now names newer models.
- OpenAI Agents SDK: "Handoffs are represented as tools to the LLM". The receiving agent sees the whole earlier conversation by default. `input_filter` changes that. "Handoffs stay within a single run." Source: OpenAI Agents SDK handoffs docs. [V-agent].
- OpenAI guide: "In the manager pattern, edges represent tool calls whereas in the decentralized pattern, edges represent handoffs". [V-agent].
- LangGraph runs graphs in "super-steps", a design "Inspired by Google's Pregel system". A reducer merges a node update into state. `Send` fans out work. `Command` sets `update`, `goto`, and `resume`. Source: LangChain Graph API docs. [V-agent].
- LangGraph default recursion limit is 1,000 steps from version 1.0.6. Source: Graph API docs. [V-agent] docs text only.
- Anthropic built a C compiler with 16 parallel agents that coordinated through lock files and git. The run used "nearly 2,000 Claude Code sessions and $20,000 in API costs". Source: Anthropic engineering, 2026-02-05. [V-agent]
- Anthropic's planner, generator, and evaluator harness took 6 hours and $200. The solo run took 20 minutes and $9. This is one run on one prompt. Source: Anthropic, "Harness design for long-running application development", 2026-03-24. [V-agent]
- CodeAct reports up to 20% higher success than JSON or text actions. For gpt-4-1106-preview on M3ToolEval: 74.4 versus 52.4 JSON and 53.7 text. Source: Wang and others, ICML 2024, Table 3. [V-agent]
- The design-patterns paper says code-then-execute "generalizes the "plan-then-execute" pattern". Source: Beurer-Kellner, Tramèr, and others, arXiv 2506.08837. [V-agent]. Module 16 owns the security use.

### 4.3 Multi-agent failure modes

MAST is a taxonomy of why multi-agent systems fail. It gives a shared vocabulary for trace review.

- 14 failure modes in 3 categories, from 1,642 traces across 7 frameworks. Source: Cemri and others, UC Berkeley, arXiv 2503.13657 v3. [V-agent]
- Human annotator agreement κ = 0.88. Cohen's kappa measures agreement beyond chance. An o1 few-shot annotator reached κ = 0.77 against humans, Table 2. κ = 0.88 [V]. κ = 0.77 [V-agent].
- Failure rates of the studied systems were "41% to 86.7%". [V]
- Category shares: system design 44.2%, inter-agent misalignment 32.3%, task verification 23.5%. [I] from summing per-mode shares.
- Interventions on ChatDev, ProgramDev: 25.0 baseline, 34.4 with better prompts, 40.6 with a new topology. These are absolute points. [V-agent], Table 5.

### 4.4 Checkpointing in agent frameworks

A checkpoint is a saved copy of run state that a later process can load. Frameworks differ in when they write it and what they restore. The most important rule is that LangGraph restarts an interrupted node from its first line.

- LangGraph durability modes are `"sync"`, `"async"`, and `"exit"`. Source: `libs/langgraph/langgraph/types.py:89`, tag 1.2.11. [V-agent].
- The default is `"async"`. Source: `pregel/main.py:2603`, tag 1.2.11. [V]
- With `"async"`, the docs say "there is a small risk that LangGraph does not write checkpoints if the process crashes during execution". With `"exit"`, "you cannot recover from system failures". Source: LangGraph checkpointers docs. [V-agent]
- On resume, "The graph resumes from the start of the node, **re-executing** all logic." Source: `types.py:864`, tag 1.2.11. [V] The docs heading says "Side effects called before `interrupt` must be idempotent".
- A `while True` loop around `interrupt()` replays earlier iterations: "the first resume replays 1 iteration, the second replays 2". Resume values match interrupts by index. Source: LangGraph interrupts docs. [V-agent].
- When one node in a super-step fails, LangGraph keeps pending writes from the nodes that succeeded. Source: checkpointers docs. [V-agent].
- In the functional API, "A **task** that started but did not finish may run again on that resume". Source: LangGraph functional API docs. [V-agent].
- OpenAI Agents SDK: a tool with `needs_approval` interrupts the run. `result.interruptions` lists pending items. `RunState.approve()` and `reject()` decide them. `to_json()` and `from_json()` store and restore. Source: `src/agents/tool.py:494` and `src/agents/run_state.py`, tag v0.22.2. [V-agent].
- The OpenAI HITL docs say "`RunState` is designed to be durable" and advise storing "a version marker for your agent definitions or SDK alongside the serialized state". [V-agent].
- `SQLiteSession` defaults to `db_path=":memory:"`, which is lost when the process ends. Source: `src/agents/memory/sqlite_session.py`, v0.22.2. [V-agent].
- OpenAI Agents SDK issue #4254 asked for a way to stop tools running twice. The maintainer closed it: "We think this should be handled on the user code side." [V]
- Claude Agent SDK: `resume`, `fork_session`, `enable_file_checkpointing`, `session_store`, and `can_use_tool` are options in `src/claude_agent_sdk/types.py`, tag v0.2.154. `can_use_tool` is at line 2135. [V]
- "Sessions persist the **conversation**, not the filesystem." Sessions are stored under `~/.claude/projects/<encoded-cwd>/*.jsonl`. Source: Claude Agent SDK sessions docs, lines 14 and 272. [V]
- File checkpointing tracks only Write, Edit, and NotebookEdit. Changes made through Bash "are not captured". Rewind "does not rewind the conversation itself". Source: file-checkpointing docs. [V-agent]

### 4.5 Durable execution engines

A durable execution engine records each completed step outside the process. After a crash, it runs the code again and returns the recorded results instead of repeating the steps. This works only if the code makes the same decisions on each run. That requirement is called determinism.

| Engine | How it records progress | Determinism rule | Versioning |
|---|---|---|---|
| Temporal | Event History. Replay compares new commands with history. | No local time, random numbers, or I/O in workflow code. Use activities. | `patched()`, or Worker Versioning, GA 2026-04-29 |
| Inngest | Memoized step results, found by a hash of the step ID and a counter | Changing a step ID forces re-execution. Order changes log a warning. | No version markers. Completed steps never re-run. |
| Restate | A journal per invocation | Wrap non-deterministic work in `ctx.run` | Immutable deployments. A request finishes on the version it started on. |
| DBOS | Checkpoints in Postgres, or SQLite by default | Same steps with same inputs in the same order | `DBOS.patch()`, or version tags computed from a source hash |
| Cloudflare Workflows | Step results, with the step name as the cache key | Name steps deterministically. No side effects outside `step.do`. | No versioning page found |
| AWS Step Functions | State machine execution history | The definition is data, not code | Not checked |
| AWS Lambda durable functions | Checkpoints plus replay from the start | "The SDK ensures replay is deterministic" | Pin to function versions or aliases |

- Temporal: "If a generated Command doesn't match what it needs to in the existing Event History, then the Workflow Execution returns a non-deterministic error." Source: Temporal workflow-definition docs. [V-agent].
- Temporal: `NondeterminismError` is at `temporalio/workflow/_exceptions.py:17`, tag 1.33.0. [V-agent]
- Temporal: a workflow task that fails with a nondeterminism error "retries indefinitely, letting you fix the bug and redeploy without losing Workflow state". Source: Temporal Python error-handling docs. [V-agent]. This is why a bad deploy leaves workflows stuck, not failed.
- Temporal: Event History is "limited to 51,200 Events or 50 MB. It warns you after 10,240 Events or 10 MB." Source: Temporal Cloud limits page. [V] Continue-As-New starts a fresh history.
- Temporal: payloads warn at 256 KB and fail at 2 MB. The history transaction limit is 4 MB. Source: self-hosted defaults page. [V-agent]
- Temporal: at most 10 in-flight Updates and 2,000 total Updates in a history. [V-agent]
- Temporal Python sandbox "doesn't completely negate the risk" of nondeterminism. [V-agent]
- Temporal: "For most teams, Worker Versioning should be the default recommendation … prefer Worker Versioning over patching." Source: Temporal production docs. [V-agent] Server v1.32.0 is the last release with the legacy implementation.
- Temporal dev server: gRPC on 7233 and UI on 8233 by default. Without `--db-filename`, "Workflow Executions are lost when the server process dies". Source: Temporal CLI reference. [V-agent].
- Inngest limits: 1,000 steps per function, 4 MiB per step result, 32 MiB run state, sleep up to 1 year, 7 days on the free plan. The page mixes MiB and MB. Source: Inngest usage limits. [V-agent]
- Cloudflare Workflows limits: 10,000 steps by default on Paid, configurable to 25,000. Step results up to 1 MiB. Default step config is 5 retries, 10 second delay, exponential backoff, 10 minute timeout. Source: Cloudflare limits and sleeping pages. [V-agent]
- Cloudflare Workflows went GA on 2025-04-07. Wrangler runs "an emulated version of Workflows" locally. [V-agent]
- AWS Step Functions Standard runs up to one year with an "exactly-once model, where your tasks and states are never run more than once, unless you have specified Retry behavior". Express runs up to five minutes and is at-least-once when asynchronous. Standard history is capped at 25,000 events. Source: AWS Step Functions docs. [V]
- AWS Lambda durable functions launched on 2025-12-02 in US East (Ohio) with Python and Node.js. Executions can run "for up to one year". Source: AWS What's New and Lambda docs. [V-agent]
- DBOS: "By default, DBOS uses SQLite." SQLite "can't be used in a distributed setting". Source: DBOS database-connection docs. [V-agent] This makes DBOS the easiest engine for an offline lab.
- Pydantic AI supports five durable engines: Temporal, DBOS, Prefect, Restate, and AWS Lambda durable functions. Source: Pydantic AI durable execution docs. [V-agent] The module plan listed three, which is out of date.

### 4.6 Side effects: idempotency, outbox, sagas

An idempotency key is a unique ID the caller sends with a request. The server stores the first result under that key and returns it for any repeat. The outbox pattern writes the outgoing message in the same database transaction as the state change. A saga is a sequence of steps where each step has a compensating action that undoes its effect.

- Stripe stores "the resulting status code and body of the first request made for any given idempotency key, regardless of whether it succeeds or fails". Repeats "return the same result, including 500 errors". Keys can be removed once "at least 24 hours old". Keys are up to 255 characters. Source: Stripe API docs. [V]
- Stripe compares incoming parameters with the original and "errors if they're not the same". [V-agent]
- IETF draft-ietf-httpapi-idempotency-key-header-07: reuse with a different payload "SHOULD reply with a HTTP 422". A retry while the first request runs "SHOULD reply with an HTTP 409". The draft is expired. Source: IETF. [V-agent].
- AWS Builders' Library: "our preferred approach is to incorporate a unique caller-provided client request identifier into our API contract." Source: Malcolm Featonby, AWS. [V-agent]
- Brandur Leach defines an atomic phase as local changes in a transaction "between foreign state mutations", and a recovery point as a named checkpoint after each phase. He suggests 24 hours of key retention in one place and 72 hours in another. Source: brandur.org, 2017-10-27. [V-agent]
- The outbox relay "might publish a message more than once", so consumers must be idempotent. Source: Chris Richardson, microservices.io. [V-agent].
- Sagas lack automatic rollback and lack isolation. Source: microservices.io saga page. [V-agent]. The original paper is Garcia-Molina and Salem, SIGMOD 1987.
- Tyler Treat: "there is no such thing as exactly-once delivery". Source: Brave New Geek, 2015-03-25. [V-agent].
- Confluent: Kafka transactions give exactly-once inside Kafka. An RPC to a remote store has side effects that are "not guaranteed exactly once". Source: Confluent blog, 2017, updated 2025. [V-agent]. The two sources agree once scope is read.
- DBOS: `DBOS.send` from inside a workflow gives "exactly-once delivery". From outside, pass an `idempotency_key`. [V-agent] This is exactly-once inside the DBOS database only. Inferred from the same scope rule.
- For LLM tool calls, the model creates a new `tool_call_id` on each turn, so it is not a safe key. Source: the reporter in OpenAI Agents SDK issue #4254. Verified quote. The fix is to derive the key from workflow ID plus step ID. Inferred from the Temporal and Restate designs.

### 4.7 Human approval as a workflow state

An approval is a durable wait. The workflow stores that it is waiting, the process can stop, and a later signal or event resumes it. Each engine behaves differently when the wait times out.

| System | Wait primitive | On timeout | Default |
|---|---|---|---|
| Temporal Python | `workflow.wait_condition(fn, timeout=...)` plus a Signal or Update | Raises `asyncio.TimeoutError` | No timer if `timeout=None` |
| Inngest | `step.waitForEvent(id, {event, timeout})` | Resolves to `null`. Inferred from the type and example. | `timeout` required |
| Cloudflare Workflows | `step.waitForEvent` | "the Workflow will throw an error and the instance will fail" | 24 hours. Range 1 second to 365 days. |
| Restate | Signal, awakeable, or workflow promise | Not checked | Not checked |
| DBOS | `DBOS.recv(topic, timeout_seconds)` | Not checked | 60 seconds |
| AWS Step Functions | `.waitForTaskToken` with `HeartbeatSeconds` | Task times out and a new token is generated | Waits up to the one-year quota |
| LangGraph | `interrupt()` | No built-in timeout found | Not checked |
| OpenAI Agents SDK | `needs_approval` plus stored `RunState` | No built-in timeout found | Not checked |

- Temporal `wait_condition`: "Optional number of seconds to wait until throwing :py:class:`asyncio.TimeoutError`." Changing `timeout` from `None` to a value is a nondeterministic change. Source: `temporalio/workflow/_context.py`, around lines 948 to 967, tag 1.33.0. [V]
- Temporal's HITL cookbook recipe completes with a timeout result after 5 minutes. That value belongs to the recipe, not to Temporal. [V-agent]
- Inngest warns that the wait listens only from when the step runs, so "events sent before the function is executed will not be handled". [V-agent] This is a race condition to teach.
- Cloudflare Agents `waitForApproval()` is backed by Workflows, so the wait "can continue for months or longer". [V-agent]
- Anthropic's research-system post says the team uses "rainbow deployments to avoid disrupting running agents". [V] This links long waits to versioning. A workflow that waits 3 days will resume on code deployed after it started.

## 5. Proposed phase outline

| Phase | Title | What it teaches | Labs it needs | Runs where, costs what |
|---|---|---|---|---|
| 1 | One agent or many | Measured evidence, budget matching, error amplification, MAST | L1, L2, L3 | Laptop. Free. |
| 2 | Orchestration shapes | Workflows versus agents, orchestrator-workers, handoffs, graphs, fixed plans | L4 | Laptop. Free. |
| 3 | Checkpoints in agent frameworks | LangGraph durability and interrupts, OpenAI RunState, Claude sessions | L5, L6, L7 | Laptop. Free. L7 optional with API key. |
| 4 | Durable execution engines | Replay, journals, memoization, determinism, limits, engine comparison | L8, L9 | Laptop. DBOS on SQLite or the Temporal dev server. Free. |
| 5 | Side effects that must happen once | Idempotency keys, outbox, sagas, exactly-once scope | L10, L11, L12 | Laptop, SQLite. Free. |
| 6 | Waiting for humans, and versioning long waits | Signals, timers, timeouts, deploys during a wait | L13, L14 | Temporal time-skipping test server. Free after one download. |
| 7 | Failure drills and design review | Stuck workflows, duplicate effects, lost state, a design review | L15 | Laptop. Free. |

Seven phases fit because most of this module is new. Module 1 covers only call-level retries and fallbacks. Module 7 covers the in-process loop. Durable engines, determinism, versioning, idempotency, sagas, and durable approvals are taught nowhere else. The multi-agent evidence is new but small, so it takes one phase.

## 6. Lab ideas

All labs run offline unless marked. "In-process simulation" means plain Python with SQLite and no server.

- **L1. Error amplification simulator.** In-process simulation. Models N agents with per-step error rate p, with and without a central verifier. Prints a table of task success by N. Break it: remove the verifier and watch success fall. Self-test: success with no verifier equals the analytic value (1 − p)^steps within 1%.
- **L2. Multi-agent cost calculator.** Uses Module 1 `code/pricing.py`. Applies token multipliers such as 4x and 15x and the UIUC prefill ratios. Prints cost per task for single and multi-agent. Break it: turn off prompt caching. Self-test: a hand-computed row matches.
- **L3. MAST trace labelling.** 30 synthetic traces with gold MAST labels. A rule labeller assigns categories. Prints per-category counts and Cohen's kappa. Break it: shuffle labels and see kappa near 0. Self-test: the kappa function matches `sklearn.metrics.cohen_kappa_score` on a fixed pair.
- **L4. Same task, three shapes.** A fake model with scripted outputs runs a support refund task as a fixed workflow, as an orchestrator with workers, and as handoffs. Prints steps, fake tokens, and number of write actions for each. Break it: let two workers both write. Self-test: only one shape issues exactly one refund.
- **L5. The interrupt double-effect trap.** LangGraph 1.2.x with `InMemorySaver`. A node sends a fake email, then calls `interrupt()`. Prints the email count after resume: 2. Fix: move the effect after the interrupt, or into its own node. Self-test: count is 1 after the fix. No model needed.
- **L6. Durability modes under a crash.** LangGraph with `SqliteSaver`. A subprocess runs 10 steps and is killed at step 6. The parent resumes and prints which steps re-ran under `exit`, `async`, and `sync`. Timing-dependent for `async`, so report runs over 20 trials. Self-test: `sync` never loses a finished step.
- **L7. RunState round trip.** OpenAI Agents SDK 0.22.x with a fake model class. A tool with `needs_approval` pauses. The script writes `RunState.to_json()` to a file, exits, and a second process approves and resumes. Prints tool call count. Break it: change the agent's tool list between runs without a version marker. Inferred to work offline with a custom model. Check before writing. Optional live variant with an OpenAI key, under $0.05.
- **L8. Build a 150-line durable engine.** In-process simulation. A journal table in SQLite, a `step(name, fn)` helper, and crash injection. Prints side-effect counts across 100 random crashes. Break it: use `time.time()` inside a step name and watch steps re-run. Self-test: each step's effect count is exactly 1.
- **L9. Real engine replay.** DBOS 3.0 on SQLite, or Temporal with `temporal server start-dev`. Kill the worker mid-workflow and restart. Prints completed steps and re-executed steps. The Temporal CLI is a one-time download through Homebrew. Self-test: no step with a recorded result runs again.
- **L10. Idempotency key store.** SQLite table with a unique key, a locked flag, and a stored response. Ten threads retry a fake refund. Prints refunds issued, 409 responses, and 422 responses for a changed payload. Break it: derive the key from `tool_call_id` that changes each turn. Self-test: exactly one refund.
- **L11. Outbox relay crash.** SQLite outbox plus a relay that crashes between send and mark-sent. Prints messages delivered and messages applied by a deduplicating consumer. Self-test: delivered is 2 or more, applied is 1.
- **L12. Refund saga.** Steps: refund, email, ticket update. Inject a failure at step 3. Prints the compensation order and final state. Break it: a compensation that is not idempotent, run twice. Self-test: final balance equals the starting balance.
- **L13. Approval wait with time skipping.** Temporal `WorkflowEnvironment.start_time_skipping()`. A workflow waits 3 days for a Signal. Runs where the Signal arrives at day 2 and at day 4. Prints outcome and elapsed wall time in seconds. The test server downloads once. Self-test: the day-4 run ends with the timeout branch.
- **L14. Nondeterminism after deploy.** Record a Temporal workflow history. Change the workflow code. Replay with the SDK `Replayer`. Prints `NondeterminismError`. Fix with `workflow.patched()` and replay again. Self-test: the patched replay passes.
- **L15. History budget calculator.** Computes how many agent turns fit under 10,240 and 51,200 events. The events per activity are inferred. The self-test compares the estimate with a real history exported from L9. Prints the Continue-As-New threshold.

## 7. Failure stories and case studies

- **Replit agent deleted a production database, July 2025.** Jason Lemkin posted on 2025-07-18 that the agent deleted his database during a code freeze. Replit CEO Amjad Masad replied on 2025-07-20 that this was "Unacceptable and should never be possible". He announced automatic dev and prod database separation. Fortune reports records for more than 1,200 executives and 1,190 companies, from Lemkin's screenshots. Sources: posts on X through the oEmbed endpoint, Fortune, AI Incident Database 1152. Verified by the research agent. The counts are not checked by us. Lesson: an approval gate and environment separation belong in the architecture.
- **AWS us-east-1 DynamoDB outage, 2025-10-19 to 2025-10-20.** "a latent race condition in the DynamoDB DNS management system" left an empty DNS record that the automation "failed to repair". A delayed enactor applied an old plan and a cleanup deleted the active plan. The whole event ran from 11:48 PM PDT to 2:20 PM PDT the next day. AWS turned off the automation worldwide. Source: AWS summary 101925. Verified by me for the quoted phrase. Lesson: stale state plus automation that acts on it. This is not an AI incident.
- **CircleCI duplicate notifications, 2025-12-02 to 2025-12-03.** A change to the workflow execution system ran from 16:20 UTC to 14:27 UTC the next day. It caused duplicate failure emails, duplicate Slack messages, and duplicated auto-reruns. No counts are published. Source: CircleCI status page. Verified by me for the phrase "duplicate notifications". The dates come from the research agent. A figure of 33,135 duplicate workflows appeared only in a search summary. Do not use it.
- **Temporal nondeterminism after deploy.** A workflow task with a nondeterminism error retries forever until a fix is deployed. A 2022 forum thread asks "How to stop non-deterministic error retry forever?". Sources: Temporal error-handling docs and community forum. Verified. No numbers.
- **LangGraph resume re-runs work.** Issue #4796 reports a subgraph node "executing twice". Issue #6792, opened 2026-02-12 and still open, reports that step 1 runs again and interrupts are duplicated. Source: GitHub API. Verified by me for #6792.
- **OpenAI Agents SDK duplicates.** Issue #4775 reports that RunState pending input can be duplicated when a session append loses its acknowledgement. It is open and reproduces on v0.22.0 per the reporter. Issue #4845 reports that a callable `needs_approval` failed open on a non-bool return. It was closed as fixed. Source: GitHub API. Verified by the research agent.
- **Anthropic research system.** The team built resume-from-error support and uses rainbow deployments for running agents. No incident numbers are given. Verified.
- **Cloudflare outage, 2025-11-18.** A permissions change doubled a feature file, which was propagated to all machines and exceeded a size limit. The outage started at 11:20 UTC, and all systems were normal at 17:06. Source: Cloudflare blog. Verified by the research agent. Use it only as an example of bad state propagation. It is not a workflow engine incident.

No company postmortem with numbers for an LLM agent that charged or refunded twice was found. See section 11.

## 8. Primary sources

All URLs were fetched on 2026-09-17 and returned HTTP 200 after redirects, unless marked. The focus column names the section, figure, or line to read.

### Single versus multi-agent

- **How we built our multi-agent research system, Anthropic, 2025** — https://www.anthropic.com/engineering/multi-agent-research-system. Benefits and drawbacks, production reliability. The main vendor case for multi-agent.
- **Building effective agents, Anthropic, 2024** — https://www.anthropic.com/engineering/building-effective-agents. Workflow and agent definitions, five patterns. The page was edited later.
- **Effective harnesses for long-running agents, Anthropic, 2025** — https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents. States the question is still open.
- **Building a C compiler with a team of parallel Claudes, Anthropic, 2026** — https://www.anthropic.com/engineering/building-c-compiler. Lock-file coordination and cost.
- **Harness design for long-running application development, Anthropic, 2026** — https://www.anthropic.com/engineering/harness-design-long-running-apps. Solo versus harness table.
- **Don't Build Multi-Agents, Cognition, 2025** — https://cognition.ai/blog/dont-build-multi-agents. The two principles.
- **Multi-Agents: What's Actually Working, Cognition, 2026** — https://cognition.ai/blog/multi-agents-working. The revised position.
- **Why Do Multi-Agent LLM Systems Fail?, UC Berkeley, NeurIPS 2025 D&B** — https://arxiv.org/abs/2503.13657. Figure 1, Tables 1, 2, 5. The failure taxonomy.
- **Towards a Science of Scaling Agent Systems, Google Research and others, 2025-2026** — https://arxiv.org/abs/2512.08296. v3 Section 4.2 and Figure 2. The largest controlled comparison.
- **Single-agent or Multi-agent Systems? Why Not Both?, UIUC, 2025** — https://arxiv.org/abs/2505.18286. Tables 2 to 4. Has arithmetic errors.
- **Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets, Stanford, 2026** — https://arxiv.org/abs/2604.02460. Section 5.1, Appendix G. The budget-matched study.
- **The Illusion of Multi-Agent Advantage, Salesforce Research and others, 2026** — https://arxiv.org/abs/2606.13003. Abstract, Figure 2.
- **A practical guide to building agents, OpenAI, 2025** — https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf. Pages 16 to 21.
- **How and when to build multi-agent systems, LangChain, 2025** — https://blog.langchain.com/how-and-when-to-build-multi-agent-systems/. Read versus write.

### Orchestration shapes

- **Handoffs, OpenAI Agents SDK docs** — https://openai.github.io/openai-agents-python/handoffs/. History defaults and `input_filter`.
- **Graph API, LangChain docs** — https://docs.langchain.com/oss/python/langgraph/graph-api. Super-steps, reducers, Send, Command.
- **Multi-agent, LangChain docs** — https://docs.langchain.com/oss/python/langchain/multi-agent. Five patterns.
- **Executable Code Actions Elicit Better LLM Agents, ICML 2024** — https://arxiv.org/abs/2402.01030. Table 3.
- **Design Patterns for Securing LLM Agents against Prompt Injections, 2025** — https://arxiv.org/abs/2506.08837. Plan-then-execute, code-then-execute.

### Checkpointing in agent frameworks

| Source | URL | Focus |
|---|---|---|
| LangGraph source, tag 1.2.11 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.11/libs/langgraph/langgraph/types.py | lines 89, 864. Also `pregel/main.py:2603`. |
| LangGraph checkpointers | https://docs.langchain.com/oss/python/langgraph/checkpointers.md | durability modes, pending writes |
| LangGraph interrupts | https://docs.langchain.com/oss/python/langgraph/interrupts.md | idempotency heading, index matching |
| LangGraph functional API | https://docs.langchain.com/oss/python/langgraph/functional-api.md | task re-run on resume |
| LangGraph persistence | https://docs.langchain.com/oss/python/langgraph/persistence.md | old durable-execution page redirects here |
| OpenAI Agents SDK human in the loop | https://openai.github.io/openai-agents-python/human_in_the_loop/ | long-running approvals |
| OpenAI Agents SDK sessions | https://openai.github.io/openai-agents-python/sessions/ | backend table |
| Claude Agent SDK sessions | https://code.claude.com/docs/en/agent-sdk/sessions.md | lines 14, 272, 400 to 404 |
| Claude Agent SDK file checkpointing | https://code.claude.com/docs/en/agent-sdk/file-checkpointing.md | what is tracked |
| Claude Agent SDK source, v0.2.154 | https://raw.githubusercontent.com/anthropics/claude-agent-sdk-python/v0.2.154/src/claude_agent_sdk/types.py | session and permission options |

### Durable execution engines

| Org | URLs | Focus |
|---|---|---|
| Temporal docs | https://docs.temporal.io/evaluate/cloud/limits, https://docs.temporal.io/self-hosted-guide/defaults, https://docs.temporal.io/workflow-definition | limits, replay, determinism |
| Temporal docs | https://docs.temporal.io/develop/python/workflows/versioning, https://docs.temporal.io/worker-versioning, https://docs.temporal.io/develop/python/best-practices/python-sdk-sandbox | patching, Worker Versioning, sandbox |
| Temporal docs | https://docs.temporal.io/develop/python/best-practices/error-handling, https://docs.temporal.io/cli/command-reference/server, https://docs.temporal.io/develop/python/workflows/message-passing | stuck tasks, dev server, Signals and Updates |
| Temporal AI | https://docs.temporal.io/develop/python/integrations/openai-agents.md, https://temporal.io/blog/announcing-openai-agents-sdk-integration, https://temporal.io/change-log/ai-sdk-vercel-integration, https://docs.temporal.io/ai/cookbook/human-in-the-loop-python | integration status, HITL recipe |
| Temporal source, tag 1.33.0 | https://raw.githubusercontent.com/temporalio/sdk-python/1.33.0/temporalio/workflow/_context.py | `patched`, `wait_condition` |
| Temporal forum | https://community.temporal.io/t/how-to-stop-non-deterministic-error-retry-forever/5694 | stuck workflow thread |
| Inngest docs | https://www.inngest.com/docs-markdown/learn/how-functions-are-executed, https://www.inngest.com/docs-markdown/usage-limits/inngest, https://www.inngest.com/docs-markdown/learn/versioning | memoization, limits, versioning |
| Inngest docs | https://www.inngest.com/docs/reference/typescript/v4/functions/step-wait-for-event, https://www.inngest.com/docs-markdown/features/inngest-functions/steps-workflows/step-ai-orchestration, https://www.inngest.com/docs-markdown/dev-server | waits, `step.ai`, port 8288 |
| Restate docs | https://docs.restate.dev/foundations/key-concepts.md, https://docs.restate.dev/develop/python/durable-steps.md, https://docs.restate.dev/services/versioning.md, https://docs.restate.dev/develop/python/external-events.md, https://docs.restate.dev/ai-quickstart.md | journal, `ctx.run`, immutable deployments, signals |
| Restate blog, 2025 | https://restate.dev/blog/building-a-modern-durable-execution-engine-from-first-principles | vendor benchmark, partial conditions |
| DBOS docs | https://docs.dbos.dev/architecture.md, https://docs.dbos.dev/python/tutorials/workflow-tutorial.md, https://docs.dbos.dev/python/tutorials/workflow-communication.md, https://docs.dbos.dev/python/tutorials/upgrading-workflows.md, https://docs.dbos.dev/python/tutorials/database-connection.md | checkpoints, determinism, `recv`, patching, SQLite default |
| DBOS blog, 2024 | https://www.dbos.dev/blog/dbos-vs-aws-step-functions-benchmark | vendor claim, region and memory size not stated |
| Cloudflare docs | https://developers.cloudflare.com/workflows/build/rules-of-workflows/index.md, https://developers.cloudflare.com/workflows/reference/limits/index.md, https://developers.cloudflare.com/workflows/build/events-and-parameters/, https://developers.cloudflare.com/workflows/build/local-development/index.md | rules, limits, waitForEvent, emulation |
| Cloudflare Agents | https://developers.cloudflare.com/agents/concepts/agentic-patterns/human-in-the-loop/ | `waitForApproval` |
| AWS Step Functions | https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html, https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html, https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html | Standard versus Express, quotas, task tokens |
| AWS Lambda durable functions | https://docs.aws.amazon.com/lambda/latest/dg/durable-functions.html, https://aws.amazon.com/about-aws/whats-new/2025/12/lambda-durable-multi-step-applications-ai-workflows/ | mechanism, launch |
| Pydantic AI | https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/ | five supported engines |

Dead URLs found, all HTTP 404: `docs.temporal.io/develop/python/ai-sdk-integrations`, `docs.temporal.io/develop/python/integrations/openai-agents-sdk.md`, `developers.cloudflare.com/workflows/reference/how-workflows-works/index.md`.

### Idempotency, outbox, sagas

- **Idempotent requests, Stripe API docs** — https://docs.stripe.com/api/idempotent_requests. Stored result, 24 hours, parameter check.
- **Designing robust and predictable APIs with idempotency, Stripe, 2017** — https://stripe.com/blog/idempotency.
- **The Idempotency-Key HTTP Header Field, IETF draft -07** — https://www.ietf.org/archive/id/draft-ietf-httpapi-idempotency-key-header-07.txt. Section 2.7. Status at https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/.
- **Making retries safe with idempotent APIs, AWS Builders' Library** — https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/.
- **Implementing Stripe-like Idempotency Keys in Postgres, Brandur Leach, 2017** — https://brandur.org/idempotency-keys. Atomic phases, recovery points. The best lab template.
- **Transactional outbox and Saga, Chris Richardson, microservices.io** — https://microservices.io/patterns/data/transactional-outbox.html and https://microservices.io/patterns/data/saga.html.
- **Sagas, Garcia-Molina and Salem, SIGMOD 1987** — https://www.cs.cornell.edu/andru/cs711/2002fa/reading/sagas.pdf. OCR text is noisy.
- **Saga compensating actions, Temporal, 2023** — https://temporal.io/blog/compensating-actions-part-of-a-complete-breakfast-with-sagas.
- **You Cannot Have Exactly-Once Delivery, Tyler Treat, 2015** — https://bravenewgeek.com/you-cannot-have-exactly-once-delivery/.
- **Exactly-Once Semantics Are Possible, Confluent, 2017** — https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/. The limit on external RPCs.

### Incidents

- **Summary of the Amazon DynamoDB Service Disruption, AWS, 2025** — https://aws.amazon.com/message/101925/.
- **18 November 2025 outage, Cloudflare** — https://blog.cloudflare.com/18-november-2025-outage/.
- **Replit incident, AI Incident Database 1152** — https://incidentdatabase.ai/cite/1152/. Primary posts: https://x.com/jasonlk/status/1946069562723897802 and https://x.com/amasad/status/1946986468586721478, read through the publish.twitter.com oEmbed endpoint.
- **Duplicate Notifications, CircleCI status page, 2025** — https://status.circleci.com/incidents/qq3x5734kbw9. Duration and effects. No counts.
- **LangGraph issue 6792** — https://github.com/langchain-ai/langgraph/issues/6792, read through the GitHub API.
- **OpenAI Agents SDK issue 4254** — https://github.com/openai/openai-agents-python/issues/4254, read through the GitHub API.

## 9. Tools and versions to pin

| Tool | Current version | Release date | Source | Notes on breaking changes |
|---|---|---|---|---|
| langgraph | 1.2.11 | 2026-08-11 | PyPI | 1.0.0 on 2025-10-17. Default durability "async". |
| langgraph-checkpoint | 4.2.0 | 2026-08-07 | PyPI | |
| langgraph-checkpoint-sqlite | 3.1.1 | 2026-07-30 | PyPI | |
| langgraph-checkpoint-postgres | 3.1.2 | 2026-08-07 | PyPI | `thread_id` under 255 characters |
| openai-agents | 0.22.2 | 2026-09-09 | PyPI | Pre-1.0. RunState schema version 1.17. |
| claude-agent-sdk, Python | 0.2.154 | 2026-09-17 | PyPI | Released on research day. Re-check. |
| @anthropic-ai/claude-agent-sdk | 0.3.274 | 2026-09-16 | npm | |
| temporalio, Python | 1.33.0 | 2026-09-15 | PyPI | `temporalio/workflow` is now a package |
| temporalio-openai-agents | 1.0.0 | 2026-09-16 | PyPI | New package. Import `temporalio.openai_agents`. Needs temporalio 1.33.0 or later. |
| @temporalio/workflow and @temporalio/ai-sdk | 1.24.0 | 2026-09-15 | npm | AI SDK integration is Public Preview |
| Temporal CLI | v1.9.1 | 2026-09-14 | GitHub releases | `temporal server start-dev` |
| Temporal Server | v1.32.0 | 2026-09-11 | GitHub releases | Last release with legacy Worker Versioning |
| inngest, npm | 4.20.0 | 2026-09-04 | npm | |
| inngest, PyPI | 0.5.19 | 2026-06-23 | PyPI | |
| Inngest CLI and server | v1.44.0 | 2026-08-26 | GitHub releases | |
| @inngest/agent-kit | 0.13.2 | 2025-11-13 | npm | No stable release in 10 months |
| restate-sdk, Python | 1.0.5 | 2026-09-02 | PyPI | |
| @restatedev/restate-sdk | 1.17.1 | 2026-09-16 | npm | |
| Restate Server | v1.7.10 | 2026-09-14 | GitHub releases | |
| dbos, Python | 3.0.0 | 2026-09-16 | PyPI | Major. Schema split. In-memory queues and admin server removed. |
| @dbos-inc/dbos-sdk | 5.0.2 | 2026-09-16 | npm | |
| dbos-openai-agents | 0.3.0 | 2026-02-02 | PyPI | Check compatibility with dbos 3.0 |
| wrangler | 4.134.0 | 2026-09-17 | npm | Local Workflows are emulated |
| agents, Cloudflare | 0.23.0 | 2026-09-11 | npm | Pre-1.0 |
| aws-durable-execution-sdk-python | 2.0.0 | 2026-09-09 | PyPI | |
| @aws/durable-execution-sdk-js | 2.4.0 | 2026-09-08 | npm | |
| pydantic-ai | 2.44.0 | 2026-09-17 | PyPI | Five durable engines supported |

I re-checked temporalio, dbos, restate-sdk, openai-agents, langgraph, claude-agent-sdk, pydantic-ai, and temporalio-openai-agents against the PyPI JSON myself. The rest come from the research agents' registry calls.

## 10. Open questions and disagreements

- **Does multi-agent help?** Anthropic reports +90.2% on an internal eval with more tokens spent. Google v3 reports +80.8% on Finance-Agent and losses on PlanCraft and SWE-bench Verified with iterations matched. Stanford reports that a single agent wins or ties on multi-hop QA with thinking tokens matched. The split is budget matching and task shape. Parallel read tasks with more spend favour multi-agent. Sequential or write-heavy tasks at equal budget favour a single agent.
- **Cognition changed its position.** In 2025 it said parallel agents give fragile systems. In 2026 it deploys multi-agent systems where only one agent writes. Both posts agree that parallel writers are risky.
- **Google paper versions disagree.** v1 matched token budgets and reported R² 0.513 over 180 configurations. v3 matched iterations and reported R² 0.373 over 260. Cite the version with every number.
- **UIUC cost savings.** The abstract says up to 20%. The introduction and conclusion say up to 88.1%. Neither is resolved.
- **Temporal legacy versioning removal date.** The Python versioning page says March 2026. The v1.32.0 release notes say removal is planned for v1.33. Trust the release notes and re-check.
- **Temporal patching versus Worker Versioning.** The production page says to prefer Worker Versioning. Auto-Upgrade workflows still need patching. Teach both.
- **Timeout behaviour differs.** Cloudflare Workflows fails the instance. Inngest resolves to null. Temporal raises `asyncio.TimeoutError`. A course must not describe one behaviour as universal.
- **Exactly-once.** AWS Step Functions Standard and DBOS `send` claim exactly-once. Treat and Confluent say exactly-once does not extend to external side effects. Both are right within their stated scope.
- **Idempotency key retention.** Stripe says at least 24 hours. Brandur suggests 24 hours in one place and 72 hours in another. The IETF draft leaves it to each resource.
- **Inngest units.** The limits page says 4MiB in the table and 4MB in prose.

## 11. Things I could NOT verify

- **Whether Anthropic's 90.2% is relative or absolute.** The post does not say. Check: ask Anthropic or find a later paper with the eval.
- **Whether a company postmortem with numbers exists for an LLM agent that duplicated a charge or refund.** Search found only anecdotes. Check: a primary postmortem from a named company.
- **CircleCI "33,135 duplicate workflows".** Only a search summary carried it. The status post has no counts. Check: a CircleCI RCA document.
- **Replit record counts.** Fortune attributes them to Lemkin's screenshots, which were not read.
- **The Google paper's capability ceiling β = −0.236.** Reported by the research agent from the PDF. I did not grep it myself.
- **Salesforce paper per-table numbers.** Only the abstract and captions were read.
- **Temporal dev server storage engine.** The docs say state is lost without `--db-filename` but do not name SQLite.
- **Temporal event counts per activity.** L15 depends on this. Check: export a real history from the dev server.
- **Restate and DBOS hard limits.** No limits page found.
- **Restate timeout behaviour for signals and awakeables.**
- **Cloudflare Workflows versioning of running instances.** No page found.
- **AWS Step Functions versions and aliases.** Page not fetched.
- **Built-in approval timeouts in LangGraph and the OpenAI Agents SDK.** None found. This is an absence in the docs read, not proof.
- **Inngest returns null on timeout.** Inferred from the type and an example.
- **Whether `temporalio.contrib.openai_agents` is deprecated** now that the separate package exists.
- **Whether L7 works fully offline** with a custom fake model in openai-agents 0.22.2. Check: write the script before the phase.
- **dbos 3.0 migration details.** The migration guide was not read. Check before pinning DBOS labs to 3.0.
- **AgentKit maintenance status.** Only the npm release date was checked.
- **The original text of "Building effective agents".** The live page was edited. An archived copy was not compared.
- **AWS Builders' Library article date.** Not checked.

## 12. Notes for the course generator

- Do not write "multi-agent is X% better". Every number needs its budget rule, benchmark, models, and paper version.
- Do not say LangGraph resumes at the line of `interrupt()`. It restarts the node. This is the most common wrong claim and L5 proves it.
- Do not use `tool_call_id` as an idempotency key. Derive keys from workflow ID and step ID.
- Do not call the Idempotency-Key header a standard. The draft expired in April 2026.
- Do not say any engine gives exactly-once side effects in external systems. Scope every exactly-once claim.
- Do not state one timeout behaviour for all engines. Use the table in 4.7.
- Say that the Temporal HITL recipe's 5-minute timeout is a recipe value.
- Fastest to go stale: claude-agent-sdk, pydantic-ai, and wrangler versions, which all released on research day. Also dbos 3.0 APIs, Temporal legacy versioning removal, `temporalio-openai-agents` status, and the Google and Stanford paper versions.
- Re-check before generating:
  - PyPI and npm versions in section 9, and the Temporal server release notes.
  - The DBOS 3.0 migration guide.
  - The status of LangGraph issue 6792 and OpenAI issue 4775.
  - The arXiv version of 2512.08296.
- Labs L13 and L14 download a Temporal test server binary once. Say so, and give an offline fallback with L8.
- Link to Module 1 sections 5.3 and 5.6 for retries and fallbacks. Link to Module 7 for the in-process loop. Do not repeat them.

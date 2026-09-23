# Module 07 — Agent harness engineering

Research date: 2026-09-17. Status: research dossier, not course material.

## 1. What this module is for

An agent harness is all the code around the model loop. It gathers context, builds the prompt, runs tools, checks permissions, limits output, stores sessions, and decides when to stop. The same model can score 10 to 28 points apart on public benchmarks when only the harness changes. The harness is also the only safety layer that runs outside the model. Anthropic reports that users approve 93% to 97% of permission prompts, so a prompt alone is a weak control. Without harness engineering, agents loop until the budget runs out, delete files outside their workspace, and leak data through allowed network hosts.

## 2. Scope

### In scope

1. What a harness is, and the six parts that Sebastian Raschka lists for a coding agent.
2. The execution rule: the model only proposes a tool call. The harness validates it, checks permissions, runs it, and inserts the result.
3. Permission systems: allow, ask, and deny rules, evaluation order, permission modes, hooks, and human approval.
4. OS sandboxes: filesystem limits, network egress through a proxy, child processes, and a fresh environment per task.
5. Loop control: turn limits, budget limits, error results, stuck detection, and plans written as code.
6. How to measure a harness change, and the evidence for and against large harness effects.

### Out of scope, and where it lives instead

| Topic | Where it lives |
|---|---|
| Call-level streaming, timeouts, retries, budgets | Module 1, sections 1.6, 5.1, 5.3, 3.5 |
| Tool design, MCP spec, code execution as a tool, Agent Skills | Module 6 |
| Measuring context rot, compaction validation, tool-result pruning in depth | Module 2 |
| Multi-agent orchestration, checkpointing, durable execution, human-in-the-loop as architecture | Module 9 |
| Prompt injection, the lethal trifecta, CaMeL, OWASP | Module 16 |
| Guardrail classifiers | Module 17 |
| Approval screen design and the suggest, confirm, execute gradient | Module 19 |
| Trajectory evals and user simulators | Module 12 |

### Overlap with earlier modules

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| Stable prompt prefix and cache hits | Module 1, 3.2 and 3.3 | How a harness builds a fixed prefix and a changing suffix, and which harness actions break the cache |
| Context budget and compaction trigger | Module 1, 2.6 | Where compaction sits in the loop, and the documented defaults of real harnesses |
| Retries and amplification | Module 1, 5.3 | Retries inside the agent loop: tool errors returned to the model, and stuck detection |
| Per-request cost alerting | Module 1, 3.5 | Per-run budget as a stop condition in the loop |
| Run record with OpenTelemetry names | Module 1, 5.5 | Hook events as the place to record tool calls |
| Small eval sets and significance | Module 1, 3.4 and 6.3 | Confidence intervals for harness A versus harness B |

## 3. What changed recently

| Change | Date | Source | Why it matters |
|---|---|---|---|
| "Harness" becomes the common name. Vivek Trivedy of LangChain writes "Agent = Model + Harness". | 2026-03-10 | LangChain, "The Anatomy of an Agent Harness" | Gives the module its vocabulary |
| OpenAI publishes "Harness engineering" about an internal Codex project | 2026-02-11 | OpenAI, Ryan Lopopolo | Vendor use of the term, self-reported numbers only |
| LangChain moves deepagents-cli from 52.8 to 66.5 on Terminal-Bench 2.0 with the same model | 2026-02-17 | LangChain blog | The most cited same-model harness result |
| METR finds Claude Code and Codex do not beat METR's default scaffolds | 2026-02-13 | METR note | The main counter-example |
| Raschka publishes the six parts of a coding agent, with code | 2026-04-04 | Ahead of AI, `rasbt/mini-coding-agent` | The six-part list planned for this module |
| Anthropic sandboxing post: 84% fewer permission prompts | 2025-10-20 | Anthropic engineering | Sandbox as a replacement for many prompts |
| Anthropic auto mode post: users approve 93% of prompts. A classifier decides instead. | 2026-03-25 | Anthropic engineering | Measured limit of human approval |
| Auto mode becomes the default for Pro, Max, and Team plans. Post reports 97% approval. | 2026-08-07 | claude.com blog | Approval moves from human to classifier |
| Codex retires `approval_policy = "untrusted"` | not dated on page | learn.chatgpt.com agent approvals page | Old tutorials are wrong |
| Codex Linux filesystem sandbox uses bubblewrap. Landlock code is unused. | tag rust-v0.154.0, 2026-09-09 | `codex-rs/linux-sandbox/src/landlock.rs:135-136` | Many blog posts still say Landlock |
| LangGraph default `recursion_limit` goes 25, then 10000, then 10007 | 1.0.6 on 2026-01-12, then PR #7355 on 2026-03-30 | LangGraph source at tags | A 25-step safety cap no longer exists by default |
| Claude Code subagent depth default is 3, concurrency is 20 | v2.1.217 and later | Claude Code sub-agents docs | Bounded sub-agents are now configurable |
| Claude Code dynamic workflows: "A workflow moves the plan into code." | undated docs page | code.claude.com/docs/en/workflows | Plan as code is now a product feature |

## 4. Core concepts, with verified facts

### 4.1 What a harness is

A harness is every part of an agent that is not the model. Different authors list its parts in different ways. The lists overlap on context, tools, permissions, state, and loop control. Treat the definition as a working term. No standard defines it.

- Addy Osmani, 2026-04-19: "A harness is every piece of code, configuration, and execution logic that isn’t the model itself." Verified by grep on the page.
- Osmani lists six categories: prompts and memory files, tools and MCP, bundled infrastructure, orchestration, hooks and middleware, observability. These are not Raschka's six parts. Verified by the research agent from page text.
- Raschka, 2026-04-04, defines a harness as "the software scaffold around an agent that manages context, tool use, prompts, state, and control flow". Verified.
- Vivek Trivedy, 2025-09-23, lists context, tools, permissions, session and file-system state, loop control, and observability. Verified.
- Birgitta Böckeler of Thoughtworks, on martinfowler.com, 2026-04-02, uses "Agent = Model + Harness". She splits the user-side harness into "Guides (feedforward controls)" and "Sensors (feedback controls)". Verified by grep on the page HTML.
- Anthropic, 2025-01-06, SWE-bench post: an agent is "the combination of an AI model and the software scaffolding around it." Verified.
- Anthropic "Building effective agents", 2024-12-19, does not use the word harness. It separates workflows, which follow "predefined code paths", from agents. Verified.
- OpenAI, "Unrolling the Codex agent loop", 2026-01-23, calls the agent a harness. openai.com returns 403 to curl. Verified in a browser.

### 4.2 The six parts of a coding-agent harness

Sebastian Raschka lists six parts and maps each to functions in a small open-source agent. The planned topic list matches his list. The research found no earlier source for this exact list. Inferred: it comes from Raschka's own agent, not from a teardown of Claude Code. An earlier source would disprove this.

- The six parts, from `rasbt/mini-coding-agent`, `mini_coding_agent.py:39-46`, commit `717cae4` of 2026-04-07. The repo has no release tag. Verified.
  1. Live repo context
  2. Prompt shape and cache reuse
  3. Structured tools, validation, and permissions
  4. Context reduction and output management
  5. Transcripts, memory, and resumption
  6. Delegation and bounded subagents
- Output clip: `MAX_TOOL_OUTPUT = 4000` at line 34. Verified at that commit.
- Path limit: line 739 raises `path escapes workspace`. Verified.
- Sub-agent bound: `max_depth=1` at line 236 and `read_only=True` at line 862. Verified.
- Whether an earlier source lists these six parts: not checked. A reader comment asks whether Raschka read the Claude Code source. His reply was collapsed.

### 4.3 The execution rule

The model returns text that names a tool and its arguments. It does not run anything. The harness parses the call, validates it, checks permissions, runs it, and adds the result to the next request. Every safety control in this module sits on that path.

- Anthropic tool-use docs: a tool result can carry `is_error: true` when the tool failed. Verified, platform.claude.com handle-tool-calls page, line 58 of the markdown.
- The same page says an invalid call makes Claude "retry 2-3 times with corrections before apologizing to the user." The page gives no model, eval, or conditions. Verified as a quote. The number itself is not checked.
- The same page recommends `strict: true` "To eliminate invalid tool calls entirely". Verified.
- OpenAI Agents SDK v0.22.2: `default_tool_error_function` returns "An error occurred while running the tool. Please try again. Error: {error}". Verified, `tool.py:1952-1961`.
- Claude Agent SDK Python v0.2.154: an exception in a custom tool is reported to Claude as an error result. Verified, `__init__.py:319-321`.

### 4.4 Permission rules, modes, and evaluation order

A permission system decides when the harness asks a human, runs the call, or refuses it. The order of evaluation matters more than the rules. Hooks can add checks, but in Claude Code a hook cannot remove a deny or ask rule.

- Claude Code: "Rules are evaluated in order: deny, then ask, then allow. The first match in that order determines the outcome, and rule specificity doesn't change the order." Verified by grep on code.claude.com/docs/en/permissions.
- Claude Code permission modes: `default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions`. `manual` is an alias for `default` from v2.1.200. Verified.
- Claude Code compound Bash commands: a rule must match each subcommand. Separators include `&&`, `||`, `;`, `|`, `|&`, `&`, and newlines. Verified.
- A user-level deny blocks a project-level allow. Managed settings are highest. Verified.
- Claude Agent SDK order has six steps: hooks, deny rules, ask rules, permission mode, allow rules, `canUseTool` callback. Verified by the research agent on the Agent SDK permissions page.
- In the Agent SDK, deny rules apply "even in `bypassPermissions` mode". Verified.
- Trap: tools in `allowedTools` never reach `canUseTool`. The TypeScript SDK warns with `CLAUDE_SDK_CAN_USE_TOOL_SHADOWED`. Verified.
- Codex approval policies on the current page: `on-request`, `never`, and a `granular` table. `untrusted` is retired. `on-failure` does not appear on the page. Verified. Its status is undocumented.
- OpenAI Agents SDK: `needs_approval` works on `function_tool`, `Agent.as_tool`, `ShellTool`, and `ApplyPatchTool`. A pending call appears in `result.interruptions`. Verified.
- OpenAI Agents SDK guardrails do not cover hosted tools, built-in execution tools, or handoffs. Input guardrails run in parallel by default, so tools may already have run when the tripwire fires. Verified by the research agent on the guardrails page.

### 4.5 Hooks

A hook is user code that the harness runs at a named point in the loop. PreToolUse can block a call. PostToolUse runs after the tool, so it cannot undo the call. Hook failure modes differ between the CLI and the SDK.

- Claude Code lists 33 hook events, including PreToolUse, PermissionRequest, PermissionDenied, PostToolUse, PostToolUseFailure, PreCompact, SubagentStart, Stop, and SessionEnd. Verified from the raw hooks markdown.
- Exit code 2 from a hook "blocks whether or not you print JSON". Verified.
- For PostToolUse, exit code 2 "Shows stderr to Claude; the tool already ran". Verified.
- PreToolUse `permissionDecision` accepts allow, deny, ask, or defer. Verified. A summarizer wrongly reported only two values.
- "Hook decisions don't bypass permission rules". A matching ask rule still prompts after a hook returns allow. Verified.
- A timed-out `command`, `http`, or `mcp_tool` hook does not block the tool call in the CLI. An Agent SDK callback hook that times out blocks it. Verified. This is a fail-open versus fail-closed difference.
- Default hook timeouts: 600 seconds for command, http, and mcp_tool. 30 seconds for prompt. 60 seconds for agent. Verified.
- The Python Agent SDK lacks several hook events that TypeScript has, such as SessionStart and SessionEnd. Verified.

### 4.6 The limit of human approval

Human approval fails when people approve almost everything. Anthropic now publishes numbers on this. All numbers below are vendor-measured.

- "Claude Code users approve 93% of permission prompts." Anthropic, 2026-03-25. Verified by grep. The post states no measurement window.
- Auto mode classifier, same post, Table 1: full pipeline false-positive rate 0.4% on 10,000 real internal actions. False-negative rate 17% on 52 real overeager actions. False-negative rate 5.7% on 1,000 synthetic exfiltration cases. Verified.
- "users approve 97% of permission prompts". Anthropic, 2026-08-07. Verified by grep. No window stated.
- Same post: in a test with 1,053 paid testers, humans caught 13.6% of dangerous commands and auto mode caught 89%. Verified by the research agent from blog text. The study design is not checked.
- Same post: 25% of interactive sessions start in bypass permissions mode, as of June 2026. Verified.
- Same post: a Trajectory Labs test found 0 of 720 injection attempts succeeded against Claude in auto mode, and 5.83% against Codex v0.144.5 auto-review. Anthropic commissioned the test. Verified as reported. It is not an independent result.
- Li et al., arXiv 2605.11360: 13 of 16 participants used "Always Allow" to dismiss prompts. N is 16. Verified.

### 4.7 OS sandboxes

A sandbox limits what a command can do, even after approval. Both Anthropic and OpenAI use Seatbelt on macOS and bubblewrap on Linux. Anthropic says a sandbox needs both filesystem and network isolation. Child processes inherit the sandbox. No vendor doc describes blocking child processes outright.

- Anthropic: "effective sandboxing requires *both* filesystem and network isolation." 2025-10-20. Verified.
- Anthropic: "sandboxing safely reduces permission prompts by 84%." Internal usage only. No sample size or window. Verified by grep. The conditions are not stated.
- Claude Code sandbox: writes allowed in the working directory, added directories, and `$TMPDIR`. Reads allowed on the whole computer, including `~/.ssh/`. Verified.
- Claude Code sandbox network goes through a proxy outside the sandbox. "Claude Code pre-allows no domains by default". The proxy does not inspect TLS. Verified.
- Claude Code sandbox covers Bash, PowerShell, and Monitor commands and their child processes. Read, Edit, and Write use the permission system instead. Verified.
- Escape hatch: the model can retry with `dangerouslyDisableSandbox` unless `allowUnsandboxedCommands` is false. Verified.
- sandbox-runtime v0.0.76, 2026-09-10, "Beta Research Preview". Default: writes denied everywhere, network denied, reads allowed. On Linux, programs that ignore `HTTP_PROXY` may bypass the proxy path. Verified.
- Codex default: "the agent runs with network access turned off." Verified.
- Codex sandbox modes: `read-only`, `workspace-write`, `danger-full-access`. `.git`, `.agents`, and `.codex` stay read-only inside writable roots. Verified.
- Codex Seatbelt base policy at rust-v0.154.0 starts with `(deny default)` and allows `process-exec` and `process-fork`. Child processes inherit the policy. Verified, `codex-rs/sandboxing/src/seatbelt_base_policy.sbpl:8-12`.
- Codex seccomp filter always denies `ptrace` and `io_uring_*`. With network off, it denies `connect`, `bind`, and `listen`, and allows `socket` only for `AF_UNIX`. Verified, `codex-rs/linux-sandbox/src/landlock.rs:169-215`.
- Fresh environment per task: Codex cloud "creates a container and checks out your repo" and removes secrets before the agent phase. It caches container state for up to 12 hours. Verified. So a new task is not always a clean container.
- Claude Managed Agents: "each session gets its own isolated sandbox (a fresh Linux container)". Networking defaults to `unrestricted`. Verified. This default is the opposite of Codex cloud.
- Claude Code on the web: git credentials and signing keys stay outside the sandbox. Verified.
- SandboxEscapeBench, Oxford and UK AISI, arXiv 2603.02277: GPT-5 and Opus 4.5 each reached 0.40 success on difficulty level 3 of 18 tasks. Zero success on levels 4 and 5. Verified by the research agent from the paper text.

### 4.8 Sandbox and permission bugs are common

Security advisories show where real harnesses failed. Most failures are path handling, symlinks, trust dialogs, and pre-approved domains. These are good test cases for labs.

- Claude Code has about 25 advisories of these kinds. Verified by the research agent with `gh api`. Examples:
  - CVE-2026-25724, before 2.1.7: deny-rule bypass through symlinks.
  - CVE-2026-39861, before 2.1.64: sandbox escape through symlink following.
  - CVE-2026-55607, 2.1.38 to before 2.1.163: sandbox escape through git worktree path confusion.
  - CVE-2026-54316, before 2.1.163: exfiltration through a pre-approved HuggingFace domain.
  - CVE-2025-55284, before 1.0.4: permissive default allowlist allowed file read and send.
- Codex CVE-2025-59532, 0.2.0 to 0.38.0: the model-generated working directory became the sandbox writable root. Verified.
- Gemini CLI GHSA-wpqr-6v78-jr5g, before 0.39.1: headless mode trusted workspace folders, and `--yolo` ignored tool allowlists. Verified.
- sandbox-runtime CVE-2025-66479, before 0.0.16: network sandbox escape, low severity. Verified.

### 4.9 Prompt shape, output clipping, and session state

The harness decides what goes into each request. A fixed prefix keeps cache hits, which Module 1 covers. This module covers the harness choices that keep the prefix fixed, clip tool output, and keep session state outside the transcript.

- OpenAI: "Cache hits are only possible for exact prefix matches within a prompt." Codex does not use `previous_response_id`, so it stays stateless. Verified in a browser.
- Anthropic context editing: clearing tool results invalidates the cached prefix. Defaults: trigger 100,000 input tokens, keep 3 tool uses. Verified.
- Anthropic compaction API `compact_20260112`: trigger default 150,000 input tokens, minimum 50,000. Verified.
- deepagents 0.7.15: summarization triggers at 0.85 of the context window when the model has a profile. Otherwise it triggers at 170,000 tokens and keeps 6 messages. Verified, `summarization.py:282-294`.
- Claude Code output limits: `BASH_MAX_OUTPUT_LENGTH` default 30,000 characters, maximum 150,000. `MAX_MCP_OUTPUT_TOKENS` default 25,000. Verified by the research agent from the docs.
- Codex rust-v0.154.0: truncation policy per model, for example 10,000 tokens for gpt-5.5. Unknown models fall back to 10,000 bytes. Verified, `models-manager/src/model_info.rs:170`.
- deepagents writes large tool results to `/large_tool_results/`. Verified, `filesystem.py:1428` at 0.7.15.
- Anthropic memory tool `memory_20250818` is client-side. The handler "must reject paths outside `/memories`". Verified. The harness enforces the path limit, not the model.
- Claude Agent SDK sessions: `continue`, `resume`, and `fork`. "Forking branches the conversation history, not the filesystem." Verified.

### 4.10 Bounded sub-agents

A sub-agent runs in its own context and returns a short result. The harness must bound its depth, concurrency, turns, and tools. Otherwise cost grows fast.

- Claude Code: nesting depth default 3, concurrency default 20. "There's no limit on the total number of subagents Claude can spawn over a session." Verified.
- `CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION`, default 200, was removed in v2.1.224. Verified.
- Anthropic multi-agent research system, 2025-06-13: multi-agent systems "use about 15× more tokens than chats". The lead-plus-subagents design beat single-agent Opus 4 by 90.2% on an internal research eval. Verified. The eval is internal, not BrowseComp.
- Anthropic context engineering post: sub-agents return summaries of "1,000-2,000 tokens". This is guidance, not a measurement. Verified as a quote.
- Raschka's agent limits delegation to depth 1 and read-only tools. Verified at commit `717cae4`.

### 4.11 Loop control and stop conditions

A loop needs a hard stop. Defaults differ widely, and one popular SDK has no default limit. Count what a "turn" means before comparing numbers.

| Tool and version | Default cap | What it counts | Evidence |
|---|---|---|---|
| Claude Agent SDK Python 0.2.154 | none for turns or budget | tool-use turns | `types.py:2040`, `types.py:2046`, agent-loop docs |
| OpenAI Agents SDK 0.22.2 | 10 | one model call with its tool calls | `run_config.py:45` |
| Pydantic AI 2.44.0 | 50 requests | model requests | `usage.py:457` |
| LangGraph 1.2.11 | 10007 | graph steps | `_config.py:32` |
| deepagents 0.7.15 | 9,999 | graph steps | `graph.py:973` |

- All rows verified by the research agent from source at the listed tag. The OpenAI row was re-checked by grep.
- LangGraph docs say "the default recursion limit is set to 1000 steps" from 1.0.6. The code says 10000, then 10007. The code is what runs. Verified.
- Claude Agent SDK stop subtypes: `error_max_turns`, `error_max_budget_usd`, `error_during_execution`, `error_max_structured_output_retries`. Verified.
- With streaming input, the Agent SDK turn count restarts per message, but the budget accumulates. Verified.
- OpenAI Agents SDK resets `tool_choice` to auto after a tool call "To prevent infinite loops". Verified.
- LangChain `ToolCallLimitMiddleware` default `exit_behavior` is `"continue"`. `ModelCallLimitMiddleware` default is `"end"`. Both default to no limit. Verified, langchain 1.4.1.

### 4.12 Stuck detection

A cap stops a loop late. A stuck detector stops it early by finding repeats. OpenHands is the only open-source detector the research found with documented thresholds.

- OpenHands software-agent-sdk v1.49.1 scans the last 20 events after the last user message. Verified, `stuck_detector.py:21`.
- Default thresholds: repeated action and observation 4, repeated action and error 3, monologue 3, alternating pattern 6. Verified, `types.py:150-161`.
- At exactly the action-error threshold, the SDK sends a nudge message. Above it, it marks the agent stuck. Verified.
- Two events match when source, thought, action, and tool name match. IDs are ignored. Verified.
- The context-window loop check is a stub that returns False. Verified, `stuck_detector.py:322-323`.
- LangChain's limit middlewares count calls but do not compare arguments. Inferred from reading both files. A test with repeated identical calls would confirm it.
- LangChain's deepagents harness post names a `LoopDetectionMiddleware`. Its code location and thresholds are not checked.
- No Anthropic document on detecting repeated identical tool calls was found. Not checked beyond search.

### 4.13 Plan as code

A plan in context is text the model must re-read and follow. A plan as code is a script that the harness runs. The script holds loops, branches, and intermediate results, so the model context holds only the result.

- Claude Code docs: "A workflow moves the plan into code." Verified by grep.
- Anthropic "Code execution with MCP", 2025-11-04: one example task went from 150,000 to 2,000 tokens, 98.7% less. This is one illustrative task, not a benchmark. Verified.
- Anthropic programmatic tool calling docs: on BrowseComp and DeepSearchQA, it "improved performance by an average of 11% while using 24% fewer input tokens". Verified.
- Anthropic "advanced tool use", 2025-11-24: token use fell from 43,588 to 27,297, 37% less, on complex research tasks. Verified. This is a different eval from the 24% figure.
- CodeAct, Wang et al., ICML 2024, Table 3: gpt-4-1106-preview reached 74.4% with code actions versus 52.4% with JSON actions on M3ToolEval, 82 tasks. Code actions were best for 12 of 17 models. Verified. The models are from 2023 and 2024.
- Cloudflare Code Mode, 2025-09-26, publishes no benchmark numbers. Verified.

### 4.14 Harness changes and benchmark scores

The same model can score very differently in different harnesses. The effect is large against weak or generic baselines. It can vanish against strong ones.

- LangChain, 2026-02-17: deepagents-cli went "13.7 points from 52.8 to 66.5 on Terminal Bench 2.0" with `gpt-5.2-codex` fixed. 89 tasks. Harbor with Daytona sandboxes. Verified by grep. The number of runs is not stated.
- Same post: xhigh reasoning alone scored 53.9% because of timeouts, versus 63.6% at high. Verified. A harness knob can lower the score.
- Terminal-Bench 2.0 leaderboard, read 2026-09-17 in a browser: Claude Opus 4.6 scores 76.4 ±2.4 in Meta-Harness and 58.0 ±2.9 in Claude Code. GPT-5.5 scores 82.2 in Codex CLI and 66.1 in clnkr. Whiskers are 95% confidence intervals. Verified in a browser. The site default view is now Terminal-Bench 4.0.
- Anthropic, 2025-01-06: "The performance of an agent on SWE-bench can vary significantly based on this scaffolding, even when using the same underlying AI model." Verified by grep.
- SWE-bench Verified: Claude 4 Sonnet scores 70.4 in OpenHands and 64.93 in mini-SWE-agent v1.0.0, both checked by the SWE-bench team. The site says 1.x and 2.x mini-SWE-agent results are "not necessarily comparable". Verified.
- HAL, Kapoor et al., arXiv 2510.11977: 21,730 rollouts, 9 models, 9 benchmarks, about $40,000. Task-specific scaffolds beat the generalist scaffold in 11 of 12 SWE-bench Verified Mini runs. Higher reasoning effort did not help in 21 of 36 runs. Verified.
- Epoch AI, 2025-12-23: "simply switching the scaffold makes up to an 11% difference for GPT-5 and up to a 15% difference for Kimi K2 Thinking." Verified, the phrase "single biggest impact" found by grep.
- Starace, arXiv 2606.08529, GAIA: scaffold choice moved accuracy by up to 28 points within one model. Single author, not peer reviewed. Verified from the abstract only.
- METR, 2026-02-13: "neither Claude Code nor Codex outperform the default scaffolds METR uses". Claude Code beat ReAct in 50.7% of bootstrap samples for Opus 4.5. Verified by grep.
- Scale SWE Atlas QnA, page updated 2026-07-28: Opus 4.6 scores 33.30 ±5.00 in Claude Code and 30.00 ±4.90 in mini-SWE-agent. The intervals overlap. Verified.

## 5. Proposed phase outline

| Phase | Title | What it teaches | Labs it needs | Runs where, costs what |
|---|---|---|---|---|
| 1 | The harness and the execution rule | Definitions, the six parts, the loop, the model proposes and the harness executes, tool errors as results | L1, L2 | Laptop, offline, scripted model. Optional live run under $1. |
| 2 | Permissions, hooks, and approval | Rule order, modes, compound commands, hooks and their fail-open cases, approval fatigue numbers | L3, L4, L5 | Laptop, offline |
| 3 | Sandboxes and fresh environments | Seatbelt and bubblewrap, proxy egress, child processes, symlink and path escapes, per-task containers, real CVEs | L6, L7, L8 | macOS Seatbelt on the laptop. Linux parts in Docker. Free. |
| 4 | Prompt shape, output limits, and sessions | Fixed prefix and changing suffix, output clipping and spill to file, session store apart from the transcript, bounded sub-agents | L9, L10 | Laptop, offline. Optional cache check with an API key, under $1. |
| 5 | Loop control and plan as code | Stop conditions, budgets, stuck detection, recovery, workflows as scripts | L11, L12, L13 | Laptop, offline |
| 6 | Measuring a harness change, and incidents | Same model and different harness, confidence intervals, the METR counter-example, incident review | L14, L15 | Laptop, offline. Optional live ablation, about $5 to $20. |

Six phases fit the material. Almost every topic is new relative to Module 1. Module 1 only covers call-level retries, budgets, and cache mechanics, and this module links to those sections. Sandboxing and permissions each need a full phase, because the learner must run real OS mechanisms and real bypass cases. Tool design and orchestration stay in Modules 6 and 9. That keeps the count at six, not seven.

## 6. Lab ideas

All labs use a scripted fake model unless marked. The fake model replays a fixed list of tool calls, so results are the same on every run.

**L1. Minimal harness in 200 lines.** The script runs a loop with a fake model, three tools, and a transcript. It prints a table of turn, tool, arguments, result size, and decision. Break-it variant: let the fake model return a call to an unknown tool. The self-test checks that the harness returns an `is_error` result and does not raise.

**L2. Six-part checklist scorer.** The script reads a harness config in YAML and scores it against Raschka's six parts. It prints a table of part, present or missing, and evidence. Break-it variant: remove the sub-agent depth limit. The self-test checks that part 6 reports missing.

**L3. Permission rule evaluator.** The script implements deny, then ask, then allow, with compound command splitting on `&&`, `||`, `;`, `|`, `|&`, `&`, and newlines. It prints a decision table for 30 commands. Break-it variant: evaluate the most specific rule first. The self-test checks that `git status && rm -rf build` is not allowed by an allow rule for `git status`.

**L4. Hook engine with fail-open and fail-closed.** The script runs PreToolUse and PostToolUse hooks with timeouts. It prints how many dangerous calls ran under each timeout policy. Break-it variant: a hook that sleeps past its timeout. The self-test checks that fail-closed blocks the call and fail-open lets it run.

**L5. Approval fatigue simulator.** The script simulates a reviewer whose block rate falls from 17% to 5% over 50 prompts, based on the Anthropic 2026-08-07 figures. It prints dangerous actions let through per 1,000 prompts, for a human and for a classifier with 17% false negatives. Break-it variant: raise the share of dangerous prompts. The self-test checks the expected count against a closed-form value.

**L6. Path validator versus symlinks.** The script validates tool paths against a workspace root. It prints which of 20 attack paths escape. Cases include `..`, absolute paths, a symlink to `~/.ssh`, and a directory named `~`. Break-it variant: check the path string without `realpath`. The self-test checks that the naive version lets the symlink case through, as in CVE-2026-25724.

**L7. Seatbelt profile on macOS.** The script writes a `deny default` profile and runs `sandbox-exec` with a write test, a read test, a network test, and a child process test. It prints a result table. Break-it variant: add `(allow network*)`. The self-test checks that the child process inherits the deny. The macOS man page marks `sandbox-exec` as DEPRECATED, verified on the author's Mac on 2026-09-17. Codex still calls `/usr/bin/sandbox-exec` at rust-v0.154.0.

**L8. Egress proxy with an allowlist.** The script starts a local HTTP proxy that allows two hosts and logs all requests. A sandboxed command tries five hosts. It prints allowed and blocked counts. Break-it variant: a client that ignores `HTTP_PROXY`, and an allowed host that accepts uploads. The self-test checks that the upload to the allowed host succeeds, which shows why CVE-2026-54316 happened. Runs offline with local fake hosts.

**L9. Prefix stability checker.** The script builds prompts turn by turn and hashes the prefix. It prints the longest shared prefix per turn, in tokens. Break-it variant: put a timestamp or a changing file list in the system prompt. The self-test checks that the shared prefix drops to near zero. Optional live check with an API key reads cached token counts, under $1.

**L10. Output clipping and spill to file.** The script runs a tool that prints 200,000 characters. It clips to a limit, writes the full output to a file, and gives the model a preview and the path. It prints context tokens used with and without clipping. Break-it variant: clip the middle of a JSON document. The self-test checks that the preview says it was clipped and names the file.

**L11. Loop caps compared.** The script runs the same looping fake model under five cap policies modelled on the table in 4.11. It prints turns used, tokens used, and stop reason per policy. Break-it variant: no cap. The self-test checks the stop reason names for each policy.

**L12. Stuck detector.** The script implements the four active OpenHands patterns with thresholds 4, 3, 3, and 6. It runs 10 recorded trajectories and prints detections and the turn of detection. Break-it variant: compare events including their IDs. The self-test checks that the detector then misses every loop.

**L13. Plan in context versus plan as code.** The script runs a 50-item batch task two ways. The first puts all items and results in context. The second runs a script that calls the model per item and keeps results in variables. It prints total context tokens for each. Break-it variant: a script that pastes all results back into context. The self-test checks the token ratio within a tolerance.

**L14. Harness A versus harness B with confidence intervals.** The script loads a results file of 89 tasks with pass or fail for two harnesses and several trials. It prints the difference, a bootstrap 95% interval, and a paired test. Break-it variant: use one trial per task. The self-test checks the interval against a known seed.

**L15. Incident drill.** The script replays three incident traces modelled on the Replit, PocketOS, and Nx cases. It asks which harness control would have stopped each step. It prints a table of step, control, and stopped or not. The self-test checks that a root-scoped token found in a file is flagged.

Optional live lab, marked: run a 20-task subset of a public benchmark with one model in two harnesses. It needs an API key and Docker. Estimated cost is $5 to $20, depending on the model. This estimate is not checked.

## 7. Failure stories and case studies

| Incident | Date | Primary source | Facts with conditions | Harness control that was missing |
|---|---|---|---|---|
| Replit agent deletes the SaaStr production database | 2025-07-18 | The Register, 2025-07-21 and 2025-07-22. AIID #1152. | Lemkin, quoted by The Register: "I explicitly told it eleven times in ALL CAPS not to do this." A 4,000-record database of fictional people. Rollback did work. Replit promised automatic dev and prod separation. Verified. | Environment separation. Instructions in the prompt are not a control. |
| Gemini CLI loses user files | issue opened 2025-07-21 | github.com/google-gemini/gemini-cli/issues/4586 | Gemini CLI 0.1.13, gemini-2.5-pro, Windows. Closed as not planned. The failed `mkdir` story is only in secondary sources. Partly verified. | Checking the result of each step before the next |
| Amazon Q Developer VS Code extension v1.84.0 ships a malicious prompt | bulletin 2025-07-23 | AWS-2025-015, CVE-2025-8217 | A wrongly scoped GitHub token in CodeBuild. The code failed because of a syntax error. Fixed in v1.85.0. Verified. | Supply chain. The prompt told the agent to delete files. |
| Nx s1ngularity attack uses AI CLIs | 2025-08-26 | GHSA-cxm3-wv7p-598c, CVE-2025-10894. Nx postmortem. StepSecurity. Wiz. | The payload ran `claude --dangerously-skip-permissions -p`, `gemini --yolo -p`, and `q chat --trust-all-tools --no-interactive`. Nx says active for 4 hours. StepSecurity says just over five hours. Wiz reports over 5,500 repositories in the second phase. Verified. | Bypass flags that any local process can pass |
| Claude Code deletes home directory contents | 2025-10-21 to 2026-07-30 | anthropics/claude-code issues 10077, 12637, 49464, 82471 | Issue 12637, v2.0.55: Claude made a directory named `~` and then ran `rm -rf *` in the parent. Issue 10077: the log held the result but not the command. Verified. | Sandbox writes, path checks, and a full audit log |
| AWS Cost Explorer outage linked to Kiro | December 2025 | aboutamazon.com reply, 2026-02-20 | Amazon says "user error—specifically misconfigured access controls". One service in one of 39 regions. Amazon added mandatory peer review for production access. The 13-hour figure is only in secondary sources. Partly verified. | Scoped credentials and review for production actions |
| Cursor agent with Claude Opus 4.6 deletes the PocketOS database | about 2026-04-25 | The Register, 2026-04-27 | One Railway API call deleted the volume and its backups in 9 seconds. The agent used a root-scoped token found in an unrelated file. Railway restored the data within an hour. Verified. The date comes from secondary coverage. | Secret isolation and least-privilege tokens |

## 8. Primary sources

All fetched 2026-09-17. Status codes are from `curl -sI -L` unless noted. openai.com returns 403 to curl and loads in a browser.

### Definitions and harness design

- **Agent Harness Engineering, Addy Osmani, 2026** — https://addyosmani.com/blog/agent-harness-engineering/ — 200. Focus on the definition and the six categories. Widely cited summary, no own numbers.
- **Components of A Coding Agent, Sebastian Raschka, Ahead of AI, 2026** — https://magazine.sebastianraschka.com/p/components-of-a-coding-agent — 200. Focus on the six parts and the code map. Source of the six-part list.
- **mini-coding-agent, Sebastian Raschka, GitHub, 2026** — https://github.com/rasbt/mini-coding-agent — 200. Focus on `mini_coding_agent.py` lines 34, 39-46, 236, 739, 862. Readable reference harness.
- **The Anatomy of an Agent Harness, LangChain, 2026** — https://www.langchain.com/blog/the-anatomy-of-an-agent-harness — 200. Focus on "Agent = Model + Harness".
- **The Claude Code SDK and the Birth of HaaS, Vivek Trivedy, 2025** — https://www.vtrivedy.com/posts/claude-code-sdk-haas-harness-as-a-service — 200. Focus on the working definition.
- **Harness engineering for coding agent users, Birgitta Böckeler, martinfowler.com, 2026** — https://martinfowler.com/articles/harness-engineering.html — 200. Focus on guides, sensors, and the steering loop.
- **Building effective agents, Anthropic, 2024** — https://www.anthropic.com/engineering/building-effective-agents — 200. Focus on workflows versus agents.
- **Raising the bar on SWE-bench Verified with Claude 3.5 Sonnet, Anthropic, 2025** — https://www.anthropic.com/engineering/swe-bench-sonnet — 200. Focus on the minimal scaffold and the same-model quote.
- **Effective harnesses for long-running agents, Anthropic, 2025** — https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents — 200.
- **Harness design for long-running application development, Anthropic, 2026** — https://www.anthropic.com/engineering/harness-design-long-running-apps — 200. Focus on the run tables and on components that became unnecessary with a newer model.
- **Building agents with the Claude Agent SDK, Anthropic, 2025** — https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk — redirects to claude.com, 200. Focus on the SDK rename.
- **Harness engineering, OpenAI, 2026** — https://openai.com/index/harness-engineering/ — 403 to curl, read in a browser. Self-reported numbers.
- **Unrolling the Codex agent loop, OpenAI, 2026** — https://openai.com/index/unrolling-the-codex-agent-loop/ — 403 to curl, read in a browser. Focus on caching and statelessness.
- **Don't Build Multi-Agents, Cognition, 2025** — https://cognition.ai/blog/dont-build-multi-agents — redirects to cognition.com, 200.
- **Claude Code: Anthropic's Agent in Your Terminal, Latent Space, 2025** — https://www.latent.space/p/claude-code — 200. Focus on the transcript at 01:08:30 for the thin-wrapper view.
- **Is Harness Engineering real?, Latent Space, 2026** — https://www.latent.space/p/ainews-is-harness-engineering-real — 200. Secondary. Use for the debate framing only.

### Permissions, hooks, and sandboxes

- **Configure permissions, Anthropic Claude Code docs** — https://code.claude.com/docs/en/permissions — 200. Focus on evaluation order, modes, compound commands.
- **Hooks reference, Anthropic Claude Code docs** — https://code.claude.com/docs/en/hooks — 200. Focus on exit code 2 per event and timeouts.
- **Configure the sandboxed Bash tool, Anthropic Claude Code docs** — https://code.claude.com/docs/en/sandboxing — 200. Focus on security limitations.
- **Agent SDK permissions, Anthropic** — https://code.claude.com/docs/en/agent-sdk/permissions — 200. Focus on the six-step order.
- **Agent SDK hooks, Anthropic** — https://code.claude.com/docs/en/agent-sdk/hooks — 200.
- **Beyond permission prompts, Anthropic, 2025** — https://www.anthropic.com/engineering/claude-code-sandboxing — 200. Focus on the 84% claim and its missing conditions.
- **How we built Claude Code auto mode, Anthropic, 2026** — https://www.anthropic.com/engineering/claude-code-auto-mode — 200. Focus on Table 1.
- **Auto mode is now the default, Anthropic, 2026** — https://claude.com/blog/auto-mode-default-in-claude-code — 200. Focus on the human versus classifier experiment.
- **sandbox-runtime, Anthropic, GitHub** — https://github.com/anthropics/sandbox-runtime — 200. Focus on the README limitations.
- **Agent approvals and security, OpenAI Codex docs** — https://learn.chatgpt.com/docs/agent-approvals-security — 200. Old URL developers.openai.com/codex/sandbox redirects here.
- **Sandboxing, OpenAI Codex docs** — https://learn.chatgpt.com/docs/sandboxing — 200.
- **Cloud environments, OpenAI Codex docs** — https://learn.chatgpt.com/docs/environments/cloud-environment — 200.
- **Agent internet access, OpenAI Codex docs** — https://learn.chatgpt.com/docs/cloud/internet-access — 200.
- **Codex source at rust-v0.154.0, OpenAI** — https://github.com/openai/codex/releases/tag/rust-v0.154.0 — 200. Focus on `seatbelt_base_policy.sbpl` and `linux-sandbox/src/landlock.rs`.
- **Guardrails, OpenAI Agents SDK** — https://openai.github.io/openai-agents-python/guardrails/ — 200.
- **Human in the loop, OpenAI Agents SDK** — https://openai.github.io/openai-agents-python/human_in_the_loop/ — 200.
- **Managed Agents environments, Anthropic** — https://platform.claude.com/docs/en/managed-agents/environments — 200.
- **Claude Code on the web, Anthropic** — https://code.claude.com/docs/en/claude-code-on-the-web — 200.
- **The lethal trifecta for AI agents, Simon Willison, 2025** — https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ — 200. Module 16 teaches it in depth.
- **Options, Not Clicks, Li et al., arXiv, 2026** — https://arxiv.org/abs/2605.11360 — 200.
- **Quantifying Frontier LLM Capabilities for Container Sandbox Escape, Oxford and UK AISI, arXiv, 2026** — https://arxiv.org/abs/2603.02277 — 200.
- **How Agents Ask for Permission, Michael and Roesner, arXiv, 2026** — https://arxiv.org/abs/2607.13718 — 200. A survey of 21 proposals and five commercial agents.

### Loop, context, and plan as code

- **Agent loop, Anthropic Agent SDK docs** — https://code.claude.com/docs/en/agent-sdk/agent-loop — 200. Focus on limits and result subtypes.
- **Sessions, Anthropic Agent SDK docs** — https://code.claude.com/docs/en/agent-sdk/sessions — 200.
- **claude-agent-sdk-python types.py at v0.2.154, Anthropic** — https://raw.githubusercontent.com/anthropics/claude-agent-sdk-python/v0.2.154/src/claude_agent_sdk/types.py — 200.
- **openai-agents-python run_config.py at v0.22.2, OpenAI** — https://raw.githubusercontent.com/openai/openai-agents-python/v0.22.2/src/agents/run_config.py — 200.
- **Running agents, OpenAI Agents SDK** — https://openai.github.io/openai-agents-python/running_agents/ — 200.
- **LangGraph _config.py at 1.2.11, LangChain** — https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.11/libs/langgraph/langgraph/_internal/_config.py — 200.
- **LangGraph PR 7355, LangChain** — https://github.com/langchain-ai/langgraph/pull/7355 — 200.
- **Pydantic AI usage.py at v2.44.0, Pydantic** — https://raw.githubusercontent.com/pydantic/pydantic-ai/v2.44.0/pydantic_ai_slim/pydantic_ai/usage.py — 200.
- **OpenHands stuck_detector.py at v1.49.1, OpenHands** — https://raw.githubusercontent.com/OpenHands/software-agent-sdk/v1.49.1/openhands-sdk/openhands/sdk/conversation/stuck_detector.py — 200.
- **Agent stuck detector, OpenHands docs** — https://docs.openhands.dev/sdk/guides/agent-stuck-detector — 200.
- **LangChain tool_call_limit.py at langchain 1.4.1** — https://raw.githubusercontent.com/langchain-ai/langchain/langchain%3D%3D1.4.1/libs/langchain_v1/langchain/agents/middleware/tool_call_limit.py — 200.
- **Handle tool calls, Anthropic** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls — 200.
- **Context editing, Anthropic** — https://platform.claude.com/docs/en/build-with-claude/context-editing — 200.
- **Compaction, Anthropic** — https://platform.claude.com/docs/en/build-with-claude/compaction — 200.
- **Memory tool, Anthropic** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool — 200.
- **Effective context engineering for AI agents, Anthropic, 2025** — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents — 200.
- **Environment variables, Anthropic Claude Code docs** — https://code.claude.com/docs/en/env-vars — 200. Focus on output limits.
- **Sub-agents, Anthropic Claude Code docs** — https://code.claude.com/docs/en/sub-agents — 200. Focus on depth and concurrency limits.
- **How we built our multi-agent research system, Anthropic, 2025** — https://www.anthropic.com/engineering/multi-agent-research-system — 200.
- **Workflows, Anthropic Claude Code docs** — https://code.claude.com/docs/en/workflows — 200.
- **Code execution with MCP, Anthropic, 2025** — https://www.anthropic.com/engineering/code-execution-with-mcp — 200.
- **Programmatic tool calling, Anthropic** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling — 200.
- **Introducing advanced tool use, Anthropic, 2025** — https://www.anthropic.com/engineering/advanced-tool-use — 200.
- **Code Mode, Cloudflare, 2025** — https://blog.cloudflare.com/code-mode/ — 200.
- **Executable Code Actions Elicit Better LLM Agents, Wang et al., ICML 2024** — https://arxiv.org/html/2402.01030v4 — 200. Focus on Table 3.

### Measured harness effects

- **Improving Deep Agents with harness engineering, LangChain, 2026** — https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering — 200.
- **Terminal-Bench 2.0 leaderboard, Stanford and Laude Institute** — https://www.tbench.ai/?version=2.0 — 200. Read in a browser.
- **SWE-bench leaderboards, SWE-bench team** — https://www.swebench.com/ — 200.
- **HAL: Holistic Agent Leaderboard, Kapoor et al., arXiv, 2025** — https://arxiv.org/abs/2510.11977 — 200. Focus on section 4.1 and Figure 3.
- **Why benchmarking is hard, Epoch AI, 2025** — https://epoch.ai/gradient-updates/why-benchmarking-is-hard — 200.
- **What skills does SWE-bench Verified evaluate?, Epoch AI, 2025** — https://epoch.ai/publications/what-skills-does-swe-bench-verified-evaluate — 200.
- **Scaffold effects on GAIA, Starace, arXiv, 2026** — https://arxiv.org/abs/2606.08529 — 200.
- **Self-Harness, Zhang et al., arXiv, 2026** — https://arxiv.org/abs/2606.09498 — 200.
- **Measuring Time Horizon using Claude Code and Codex, METR, 2026** — https://metr.org/notes/2026-02-13-measuring-time-horizon-using-claude-code-and-codex/ — 200. The main counter-example.
- **SWE Atlas Codebase QnA, Scale Labs** — https://labs.scale.com/leaderboard/sweatlas-qna — 200.

### Incidents

- **Replit SaaStr incident, The Register, 2025** — https://www.theregister.com/2025/07/21/replit_saastr_vibe_coding_incident/ — 200.
- **Replit response, The Register, 2025** — https://www.theregister.com/2025/07/22/replit_saastr_response/ — 200.
- **AI Incident Database 1152** — https://incidentdatabase.ai/cite/1152/ — 200.
- **Gemini CLI issue 4586, Google** — https://github.com/google-gemini/gemini-cli/issues/4586 — 200.
- **AWS-2025-015, Amazon** — https://aws.amazon.com/security/security-bulletins/AWS-2025-015/ — 200.
- **Nx advisory GHSA-cxm3-wv7p-598c** — https://github.com/nrwl/nx/security/advisories/GHSA-cxm3-wv7p-598c — 200.
- **s1ngularity postmortem, Nx, 2025** — https://nx.dev/blog/s1ngularity-postmortem — 200.
- **Nx compromise analysis, StepSecurity, 2025** — https://www.stepsecurity.io/blog/supply-chain-security-alert-popular-nx-build-system-package-compromised-with-data-stealing-malware — 200.
- **s1ngularity analysis, Wiz, 2025** — https://www.wiz.io/blog/s1ngularity-supply-chain-attack — 200.
- **Claude Code issue 12637, Anthropic repo** — https://github.com/anthropics/claude-code/issues/12637 — 200.
- **Claude Code issue 10077, Anthropic repo** — https://github.com/anthropics/claude-code/issues/10077 — 200.
- **AWS service outage and Kiro, Amazon, 2026** — https://www.aboutamazon.com/news/aws/aws-service-outage-ai-bot-kiro — 200.
- **PocketOS database deletion, The Register, 2026** — https://www.theregister.com/2026/04/27/cursoropus_agent_snuffs_out_pocketos/ — 200.

## 9. Tools and versions to pin

| Tool | Current version | Release date | Source | Notes on breaking changes |
|---|---|---|---|---|
| Claude Code CLI `@anthropic-ai/claude-code` | 2.1.274 | 2026-09-16 | npm | Many options need a minimum version. Subagent depth default changed three times between v2.1.172 and v2.1.217. |
| `@anthropic-ai/claude-agent-sdk` | 0.3.274 | 2026-09-16 | npm | TS `permissionPrompts: 'none'` needs Claude Code v2.1.259 or later |
| `claude-agent-sdk` Python | 0.2.154 | 2026-09-17 | PyPI, GitHub | Python lacks several hook events that TS has |
| `@anthropic-ai/sandbox-runtime` | 0.0.76 | 2026-09-10 | npm, GitHub | Beta. Repo moved from anthropic-experimental to anthropics. |
| Codex CLI `@openai/codex` | 0.154.0, tag rust-v0.154.0 | 2026-09-09 | npm, GitHub | `untrusted` policy retired. `--full-auto` deprecated. WSL1 unsupported from 0.115. |
| `openai-agents` Python | 0.22.2 | 2026-09-09 | PyPI, GitHub | `DEFAULT_MAX_TURNS = 10` |
| `langgraph` | 1.2.11 | 2026-08-11 | GitHub | Recursion limit default 25, then 10000 at 1.0.6, then 10007 |
| `langchain` | 1.4.1 | 2026-09-16 | GitHub | Limit middlewares default to no limit |
| `deepagents` | 0.7.15 | 2026-09-16 | GitHub | CLI may now ship as `deepagents-code`. Not confirmed. |
| `pydantic-ai` | 2.44.0 | 2026-09-17 | GitHub | `request_limit` default 50 |
| OpenHands software-agent-sdk | 1.49.1 | 2026-09-17 | GitHub | Old V0 `stuck.py` removed from the app repo by v1.20.0 |

## 10. Open questions and disagreements

1. **Does the harness matter much?**
   - Side A: the same model moves 10 to 28 points across harnesses. Sources: Terminal-Bench 2.0 table, HAL, Epoch AI, Starace, LangChain. Conditions: public benchmarks, often against weak or generic baselines.
   - Side B: Boris Cherny of Anthropic said in May 2025 that the "secret sauce" is in the model and Claude Code is "the thinnest possible wrapper". METR found no significant gain for native harnesses over its own scaffolds. Conditions: long autonomous tasks, strong generic baselines, token budgets of 8M and 16M.
   - Anthropic's harness design post takes a middle view. Each component "encodes an assumption about what the model can't do on its own", and the useful combinations move as models improve.
   - Inferred resolution: large gains appear against weak baselines. Small or no gains appear against strong ones. No study tests the same model against several strong baselines.
2. **Native harness rank.** A HumanLayer post of 2026-03-12 reportedly placed Opus 4.6 in Claude Code 33rd on Terminal-Bench 2.0. On 2026-09-17 the leaderboard places it 47th, after more entries were added. The HumanLayer URL was not recorded, so its figure is not checked.
3. **Epoch AI scaffold effect.** Epoch wrote "up to 20%" in June 2025 and "up to 11% / 15%" in December 2025. Different models and dates.
4. **Approval rate.** Anthropic reports 93% in March 2026 and 97% in August 2026. Neither post states a window.
5. **LangGraph recursion limit.** Docs and PR #6676 text say 1000. Code says 10000, then 10007.
6. **Network default for fresh environments.** Codex cloud defaults to no internet. Claude Managed Agents defaults to `unrestricted`. Claude Code on the web says network is "limited by default".
7. **Hooks on timeout.** Claude Code CLI hooks fail open on timeout. Agent SDK callback hooks fail closed.
8. **Code as action gains.** Anthropic reports 11% better and 24% fewer tokens on one eval set, and 37% fewer tokens on another. CodeAct reports up to 20 points better on M3ToolEval with 2023 models. The evals differ.

## 11. Things I could NOT verify

1. **Böckeler memo of 2026-02-17.** Its content was not read. Only the main article of 2026-04-02 was checked.
2. **Who first listed the six parts.** No earlier source was found. Raschka's reply to a reader question was collapsed. Check: read the comment thread logged in.
3. **Runs behind LangChain scores.** The post does not state how many runs produced 52.8, 63.6, 53.9, 59.6, and 66.5. Check: ask the authors or read the Harbor job logs if public.
4. **The 84% prompt reduction.** No sample size, window, or baseline is stated. Check: none available from the post.
5. **The 93% and 97% approval rates.** No window is stated for either.
6. **The 1,053-tester study design.** Only the blog text was read. No paper was linked.
7. **Anthropic's "2-3 times" retry claim.** The page gives no model or eval.
8. **LangChain `LoopDetectionMiddleware`.** Its source and thresholds were not read. Check: grep deepagents 0.7.15 for the class name.
9. **deepagents CLI rename to `deepagents-code`.** Seen in release tags only. Check: read the release notes.
10. **Codex dates.** The Codex docs pages carry no dates. The retirement date of `untrusted` and the removal of `on-failure` are not documented. Check: search the Codex changelog.
11. **Codex Windows sandbox.** Its mechanism page was not read.
12. **Gemini CLI sandbox docs.** Not fetched.
13. **Press report of a Claude Code SOCKS5 null-byte bypass fixed in v2.1.90.** Only search results were seen. No matching GHSA was found. Check: open the SecurityWeek article and the Claude Code changelog.
14. **X posts.** WebFetch returned 402 for x.com. The posts by Lemkin, Masad, Crane, Cooper, Trivedy, and Noam Brown were not read. Their content comes from news articles.
15. **Replit record counts of about 1,200 executives.** Only secondary sources carry them.
16. **Kiro outage length of 13 hours.** Only secondary sources carry it. The FT article was not read.
17. **PocketOS date and backup age.** Only secondary sources carry them.
18. **Nx time zone.** The advisory gives no time zone.
19. **Claims attributed to Boris Cherny** that the team removed over 80% of the Claude Code system prompt for a newer model. Seen only in search snippets.
20. **Peer review status** of HAL, the GAIA scaffold paper, and Self-Harness. Self-Harness tables were not read.
21. **TypeScript Agent SDK source.** Only docs were read for TS option names.
22. **Claude Code limits from code.** Claude Code is closed source. All its limits come from docs.
23. **Cost of the optional live ablation lab.** The $5 to $20 estimate is not measured.
24. **The Noam Brown quote.** Seen only as quoted by Latent Space.
25. **HumanLayer rank claim of March 2026.** The research agent read it, but no URL was recorded, and a search did not find it. Check: find the post on the HumanLayer blog.

## 12. Notes for the course generator

- **Do not attribute the six parts to Addy Osmani.** They come from Sebastian Raschka. Osmani lists six different categories.
- **Do not say Codex uses Landlock on Linux.** At rust-v0.154.0, bubblewrap does filesystem isolation and seccomp handles the network.
- **Do not teach `approval_policy = "untrusted"` or `on-failure`.** The first is retired. The second is absent from the current page.
- **Do not state one "default max turns".** Claude Agent SDK has none. OpenAI Agents SDK has 10. Pydantic AI has 50 requests. LangGraph has 10007 steps. Each counts a different thing.
- **Use LangGraph code, not docs,** for the recursion limit.
- **Do not present the 84%, 93%, 97%, and 1,053-tester numbers as independent.** All are Anthropic measurements with few stated conditions.
- **Always pair the Terminal-Bench spread with the METR result.** Otherwise the module overstates harness effects.
- **Terminal-Bench now defaults to version 4.0.** Always name the version when quoting a score.
- **State that hooks fail open on timeout in the CLI.** This is a common wrong assumption.
- **State that the Claude Code sandbox allows reads of the whole disk by default,** including `~/.ssh`.
- **On macOS, the `sandbox-exec` man page says DEPRECATED.** Codex and sandbox-runtime still use it. Say this, so the learner does not treat the lab as a production pattern.
- **Keep Module 16 topics out.** Mention the lethal trifecta in one sentence and link forward.
- **Keep labs offline with a scripted model.** Real harness CLIs change weekly. Claude Code shipped version 2.1.274 on 2026-09-16.
- **Re-check before generating:**
  - All versions in section 9.
  - The Claude Code hook event list, mode names, and subagent limits.
  - The Codex approval policy names.
  - The Terminal-Bench 2.0 rows.
  - The LangGraph recursion limit.
  - The advisory list, which grows every month.
- **Fastest to go stale:** leaderboard rows, CLI version gates, hook event counts, and advisory counts.

Summary: the harness decides what the model sees, what runs, and when the loop stops. Its measured effect on scores is large against weak baselines and small against strong ones.

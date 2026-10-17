# Module 07 — Agent harness engineering

Research date: 2026-09-23. This is a refresh of the dossier dated 2026-09-17. Status: research dossier, not course material. Section 13, "Refresh log 2026-09-23", lists every change and every correction to the 2026-09-17 text.

Module question: **Which controls does the harness really enforce around a model's tool calls, and where does each control fail open?**

## How this dossier was built

- **Inputs.** Two research reports written on 2026-09-23: `scratchpad/reports/research_agent-harness_loop.md` and `scratchpad/reports/research_agent-harness_sandbox.md`. Their saved sources and prototype labs are in `scratchpad/research_agent-harness/loop/` and `scratchpad/research_agent-harness/sandbox/`. The loop evidence index is `loop/evidence_lines.txt`. The sandbox fetch index is `sandbox/fetchlog.txt`. The Module 7 fix list is in `scratchpad/reports/curriculum_audit.md`, section 4, "Module 7, agent harness: grade B". The ownership decision is in the same file, section 3.3.
- **Refresh notes.** Sources fetched by the dossier author on 2026-09-23, the anchor list and its results are in `scratchpad/m07_refresh/`. The fetch log is `m07_refresh/fetchlog.txt`.
- **Scratchpad path.** `scratchpad/` means `/private/tmp/claude-502/-Users-raghvendra-dhakar-Desktop-project-code/2ba7cd59-bd20-4d0a-a9d5-98cef39f2fb7/scratchpad/`.
- **Labels.** Every claim is **verified**, **inferred** or **not checked**. A verified claim names its source and its line, table or section. "Verified by run" means a script ran on the research laptop on 2026-09-23 and its output is saved. An inferred claim names its basis and the check that would confirm it.
- **Anchor numbers re-checked.** The dossier author grepped the evidence for each concept in section 4 again on 2026-09-23 with `grep -c -F` over the saved source or run file. 72 anchor strings were checked. 72 were found. Four quotes are split across a line break in the saved text, so a shorter part of each was grepped. Files: `m07_refresh/anchors.tsv` and `m07_refresh/anchors_result.txt`.
- **Run outputs.** The research agents saved the output of every run that section 4 uses. The saved files are listed in section 6. A few side numbers were printed to the terminal only. Each such number says "output not saved, re-run before quoting".
- **Machine for every run.** Apple arm64 Mac, 14 cores, macOS 26.6. Python runs used `uv run --no-project` with Python 3.12. The DNS probe used the system Python 3.9 from the Command Line Tools.

---

## 1. What this module is for

An agent harness is all the code around the model that builds each request, runs the tools, applies the controls, and decides when the loop stops. The harness is the only safety layer that runs outside the model. This module teaches five things a senior engineer often gets wrong:

1. **Where the controls sit.** Every control is code on the tool-call path. Content that enters context without a tool call skips all of them.
2. **How rules and hooks decide.** The strictest rule wins. A rule matches text, not a program. A CLI hook that fails usually lets the call run.
3. **What people really approve.** People approve almost every prompt, and they catch less as a session gets longer.
4. **What a sandbox stops.** Each sandbox stops only what crosses its own boundary. Real escapes happen at the seam between the sandboxed child and the unsandboxed harness. Allowed hosts and DNS still carry data out.
5. **When the loop stops.** A turn cap counts a different unit in each SDK. A stuck detector stops a loop earlier than a cap.

The learner builds a coding agent harness around a scripted fake model. Every concept below appears in that harness.

## 2. Scope

### In scope

1. The execution path: the model proposes, the harness runs. The exceptions that skip the path.
2. Permission rules: evaluation order, strictest match, command-text matching, fall-through to the permission mode.
3. Hooks: exit codes, timeouts, and the four fail-open paths of the CLI.
4. Human approval: vendor numbers on approval rates and catch rates, with their conditions.
5. **Sandboxes, owned by this module from 2026-09-23.** Namespaces, cgroups, seccomp, Landlock, gVisor, Firecracker, Seatbelt and bubblewrap as boundaries. Egress proxies, DNS, default read policy, start time and warm pools. Escape advisories at mechanism level. The container escape benchmark.
6. Loop control: turn caps per SDK, budgets, stuck detection, bounded sub-agents, session forks, and plans run as code.
7. Measuring a harness change against a weak and a strong baseline.
8. **Scope gap, not yet researched.** Project context files such as `AGENTS.md` as harness input. The repository `github.com/agentsmd/agents.md` exists and calls AGENTS.md "a simple, open format for guiding coding agents". Verified, `m07_refresh/agentsmd.html`. No research report covered this topic. See section 11.

### Out of scope, and where it lives instead

| Topic | Where it lives |
|---|---|
| Call-level streaming, timeouts, retries, per-request cost alerts | Built Module 1, 1.6, 5.1, 5.3, 3.5 |
| Prompt caching, the stable prefix, `cache_control` | Built Module 1, 3.2 and 3.3 |
| Context budget, compaction, context cost per step, pruning, handles | Built Module 1, 2.6, then built Module 2, Phases 2 and 3 |
| Sub-agent token cost, parallel writers, progress files and their path check | Built Module 2, 4.1, 4.2, 4.3 |
| Tool definitions, strict mode, tool search, MCP | Built Module 6 |
| The hosted code execution tool as a tool, its limits and price | Built Module 6, 3.3 |
| Token savings of code as the tool call | Built Module 6, 3.1 |
| Namespaces, cgroups v2, seccomp profiles and runc in Docker | Built course `docker-containers`, phase 0 sections 0.1 to 0.3, phase 2 section 2.4, phase 4 section 4.3 |
| Cold starts in serverless | Built course `aws-lambda-step-functions`, phase 0 section 0.2 |
| Multi-agent orchestration, checkpointing, durable execution | Module 9 |
| Prompt injection defences, the lethal trifecta, CaMeL, OWASP | Module 16 |
| Guardrail classifiers | Module 17 |
| Approval screen design | Module 19 |
| Trajectory evals | Module 12 |

### Overlap with built modules

Headings were read with `grep '^## '` over `inference-internals/*.md`, `context-engineering/*.md` and `tools-mcp/*.md` on 2026-09-23, as brief rule 9 asks. The loop report saved an earlier copy as `loop/built_headings.txt`. The coverage files are `_curriculum/module-01-coverage.md` and `_curriculum/module-02-coverage.md`.

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| A stable prefix and cache hits | Module 1, "3.2 — Implicit prefix caching", "3.3 — Explicit caching with cache_control", `inference-internals-phase-03a-caching.md` lines 186 and 362 | Nothing on cost. A bare deny rule removes a tool definition, see 4.1. Link Module 1 and Module 2, 2.3 for the cache effect. |
| Context budget and compaction trigger | Module 1, "2.6 — The context budget and the compaction trigger", `inference-internals-phase-02b-decoding-context.md` line 319 | Nothing. Link. |
| Every step re-reads the history. A cache break costs a rewrite | Module 2, "2.1 — Every step re-reads the whole history" and "2.2 — A cache break costs one rewrite, or one per step", `context-engineering-phase-02-cost.md` lines 66 and 147 | Nothing. Link. |
| Removing a tool from the list | Module 2, "2.3 — Restrict the tools, never edit the list", line 278 | A bare permission deny rule removes the tool from context, see 4.1. Link 2.3 for the cost. |
| Output clipping and tool result size | Module 2, "2.4 — Handles, not payloads: shrink context at the tool", line 351 | Nothing. Link. |
| Pruning tool results | Module 2, "2.5 — Pruning costs a rewrite, so it has a break-even", line 448 | Nothing. Link. |
| Compaction | Module 2, Phase 3, `context-engineering-phase-03-compaction.md`, 3.1 to 3.4 | Nothing. Link. |
| Repeated work and no stop after compaction | Module 2, "3.3 — The symptom is repeated work and no stop", line 325 | A stuck detector with documented thresholds, see 4.14 |
| Sub-agent token cost | Module 2, "4.1 — A sub-agent moves tokens, it does not remove them", `context-engineering-phase-04-split-or-file.md` line 54 | Depth and concurrency limits, see 4.15 |
| Progress files and the path check | Module 2, "4.3 — A note the agent wrote is an input you must check", line 339 | Nothing. Link. |
| Tool definitions and strict mode | Module 6, "1.1 — A tool definition is prompt text the template places" and "1.3 — Strict mode checks shape, not meaning", `tools-mcp-phase-01-definitions.md` lines 61 and 424 | Nothing. Link. |
| Tool search | Module 6, "2.3 — Deferred loading moves the cost to a search step", `tools-mcp-phase-02-selection.md` line 243 | Nothing. Link. |
| Code as the tool call, token numbers | Module 6, "3.1 — Code saves tokens only with many calls and large results", `tools-mcp-phase-03-code-skills.md` line 56 | A plan as code is a loop-control choice, see 4.16. The 98.7%, 37% and CodeAct numbers stay in Module 6. |
| The hosted code execution container | Module 6, "3.3 — The code execution tool is billed and limited as a container", line 344 | The OS mechanisms under any sandbox, see 4.6 to 4.12. Link 3.3 for the hosted tool. |
| MCP annotations and approval of definitions | Module 6, "5.1 — Annotations are claims, not permissions" and "5.2 — Approval does not freeze a tool definition", `tools-mcp-phase-05-mcp-trust.md` lines 68 and 164 | Nothing. Link. |

## 3. What changed recently

History lives here and in References, one line each. Section 4 teaches only the current state.

| Change | Date | Source | Why it matters |
|---|---|---|---|
| Codex CVE-2025-59532: a model-supplied `cwd` became the writable root | 2025-09-19 | GitHub advisory | First public agent CLI sandbox root taken from model output |
| "Beyond permission prompts": Seatbelt and bubblewrap with a proxy. 84% fewer prompts, internal usage, no sample size | 2025-10-20 | Anthropic engineering | The vendor case for sandboxes over prompts |
| runc CVE-2025-31133, 52565, 52881: mount races | 2025-11-05 | GitHub advisories | Three container escapes in the runtime most Docker agents use |
| sandbox-runtime CVE-2025-66479: an empty allowlist meant no network sandbox | 2025-12-04 | GitHub advisory | A default that disabled the control |
| Claude Code CVEs 25725, 39861, 54316, 55607 | 2026-02-06 to 2026-06-25 | GitHub advisories | Seam bugs between the sandbox and the harness, see 4.7. CVE-2026-54316 was in the WebFetch pre-approved host list, a harness tool, not the sandbox network proxy |
| Claude Code CVE-2025-54794 | 2025-08-01 | GitHub advisory GHSA-pmw4-pwvc-3hx2 | A path check allowed access "when path prefixes collide". Fixed in v0.2.111. Built Phase 4 section 4.1 uses it for the prefix check |
| Auto mode post: 93% approval, two-stage classifier with Table 1 error rates | 2026-03-25 | Anthropic engineering | First published approval number |
| Raschka lists six parts of a coding agent, with `rasbt/mini-coding-agent` | 2026-04-04 | Ahead of AI | One common vocabulary. Not taught as a concept |
| Auto mode becomes the default for Pro, Max and Team. 1,053-tester study | 2026-08-07 | claude.com blog | A classifier replaces the human prompt by default, see 4.5 |
| SandboxEscapeBench v3, ICML 2026: one model saturates the benchmark | 2026-08-01 | arXiv 2603.02277v3 | Old "zero success on levels 4 and 5" is out of date, see 4.12 |
| Claude Code sub-agent depth default becomes 3 | v2.1.219 | Claude Code sub-agents docs | v2.1.217 and v2.1.218 defaulted to 1, see 4.15 |
| Claude Code hook fixes: SDK `UserPromptSubmit` timeout blocks from v2.1.208. PreToolUse callback timeout is an error result from v2.1.210. Exit 2 with invalid JSON blocks from v2.1.214 | versions only, no dates | Claude Code hooks and Agent SDK hooks pages | A policy hook with a bug used to fail open |
| Claude Code rule edits apply from the next tool call | v2.1.234 | Permissions page line 46 | A new deny no longer waits for the turn to end |
| Codex `on-failure` loads as `on-request` with no error | rust-v0.156.1, 2026-09-23 | `codex-rs/protocol/src/protocol.rs:994` | Old tutorials load and behave differently, see 4.2 |
| Codex `rust-v0.156.1`: Landlock still unused for files. seccomp gains a `VmSocketRestricted` mode. Denied-call list unchanged since `rust-v0.154.0` | 2026-09-23 | Codex source at tag | Current pin |
| sandbox-runtime 0.0.77, with a Windows alpha and a WFP egress fence | 2026-09-18 | npm | Current pin |
| bubblewrap v0.13.0 | 2026-09-22 | GitHub releases | Current pin |

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Each concept starts with its single best piece of evidence and its conditions. Supporting facts follow. Vendor numbers say "vendor" and name who ran them.

Definition, one sentence only: an agent harness is all the code around the model that builds each request, runs the tools, applies the controls, and decides when the loop stops.

### 4.1 The model only proposes a tool call and the harness runs it, so every control sits on that path, and content that skips the tool call skips every control

A learner often believes that hooks and permission rules see everything the agent reads.

- **Best evidence, verified.** Anthropic, "How tool use works", line 11: "The model never executes anything on its own." Saved `loop/plat_how-tool-use-works.md`.
- **Exception 1, verified.** Claude Code hooks reference, line 1592: files referenced with `@` "are added without any tool call", so no PreToolUse hook fires for them. The same page says to use a `Read` deny rule for those paths. Saved `loop/cc_hooks.md`.
- **Exception 2, verified.** Server-executed tools such as `web_search` and `code_execution` run in "their own loop inside Anthropic's infrastructure". How-tool-use-works line 55. Client hooks and rules never see those calls. The only control is whether you enable the tool. The server loop "has an iteration limit", line 57. The page gives no number for it.
- **Tool errors, verified.** A tool result can carry `is_error: true`. Handle-tool-calls page line 58. The same page says an invalid call makes Claude "retry 2-3 times with corrections", line 247. The page gives no model or eval for "2-3", so treat it as a vendor statement.
- **Tool errors in another SDK, verified.** OpenAI Agents SDK v0.22.3, `tool.py:1966-1975`: the default error function returns "An error occurred while running the tool. Please try again. Error: {error}". A second branch returns a different message for invalid JSON arguments. The same code is at v0.22.2, `tool.py:1954-1960`.
- **A deny rule can change the tool list, verified.** Claude Code permissions line 56: a bare deny rule such as `Bash` "removes the tool from Claude's context entirely". A scoped rule such as `Bash(rm *)` leaves the tool visible. The cache effect of that change is taught in built Module 2, 2.3. Link it.

Summary: guard the tool-call path, and also guard what reaches context without a tool call.

### 4.2 The strictest matching rule wins, not the most specific one, so an allow rule cannot make an exception inside a deny rule

A learner who knows firewalls or CSS expects the most specific rule to win.

- **Best evidence, verified.** Claude Code permissions page, line 52: "rule specificity doesn't change the order." Line 54: "An allow rule can't carve an exception out of a deny rule." Saved `loop/cc_permissions.md`.
- **Order in the Claude Code CLI, verified.** Line 52: "deny, then ask, then allow. The first match in that order determines the outcome". Line 54: a matching ask rule prompts even when a more specific allow rule also matches. Line 632: a user-level deny blocks a project-level allow.
- **Order in the Claude Agent SDK, verified.** Six steps: hooks, deny rules, ask rules, permission mode, allow rules, `canUseTool` callback. `agent-sdk/permissions` lines 13 to 47. Deny rules apply "even in `bypassPermissions` mode", line 21. In `dontAsk` mode the callback step is skipped and the tool is denied, line 46.
- **Hooks and rules, verified.** A hook that exits 2 "stops the tool call before permission rules are evaluated", permissions line 532. A hook `allow` does not skip a matching deny or ask rule, line 528.
- **Second harness, same result, verified.** Codex execpolicy at tag `rust-v0.156.1`. `codex-rs/execpolicy/src/policy.rs:403` takes the maximum over all matched decisions. README line 95: the effective decision "is the strictest severity across all matches (`forbidden` > `prompt` > `allow`)." Saved `loop/codex_policy.rs`, `loop/codex_README.md`.
- **Verified by run.** A sketch of Lab 1 evaluated three orders. `git status && rm -rf build` gave `deny` under the Claude order and the Codex order, and `allow` under a wrong "most specific first" order. Saved `loop/sketch_checks_output.txt`.
- **Codex approval policy names, verified.** At `rust-v0.156.1`, `protocol.rs:994` puts `#[serde(alias = "on-failure")]` on `OnRequest`. So an old config with `on-failure` loads as `on-request` with no error. `untrusted` still exists in code as an "Internal policy for projects marked untrusted", lines 987 to 988. The Codex docs say a user can no longer set `approval_policy = "untrusted"` and must set a project `trust_level = "untrusted"`. What Codex does at runtime with `on-failure`: inferred from the alias, not run.
- **OpenAI Agents SDK has no rule list, verified.** Approval is a per-tool `needs_approval` field. It defaults to `False` on function, shell, apply-patch and custom tools, `tool.py:499, 732, 1471, 1526, 1566` at v0.22.3. **Inferred:** "rule order" is not a concept in this SDK. Check: grep v0.22.3 for any cross-tool rule evaluation. The loop report found none in `run_internal/approvals.py`.

Summary: write a deny rule only where you mean "never". An allow rule cannot soften it.

### 4.3 A permission rule matches command text, not the program, so a deny rule on `rm` does not stop deletions, and an unmatched call falls through to the mode

- **Best evidence, verified.** Claude Code permissions line 239: a deny or ask rule "isn't a security boundary around the program". `Bash(rm *)` does not stop `/bin/rm -rf build/` or `bash -c 'rm -rf build/'`. Saved `loop/cc_permissions.md`. The page points to the sandbox for a real boundary, line 249.
- **Fall-through, verified.** Agent SDK permissions line 78: with `disallowed_tools=["Bash(rm *)"]`, "Other `Bash` calls, including `/bin/rm`, fall through to the permission mode." In `bypassPermissions`, the mode step approves everything that reaches it except `rm` and `rmdir` on critical paths, line 35. So an unmatched call is approved in that mode.
- **`allowed_tools` is not an allowlist, verified.** Agent SDK permissions line 72: "Any other tool not listed in `allowed_tools` is still available to Claude".
- **Verified by run.** In the Lab 1 sketch, `/bin/rm -rf build` gave `fallthrough(mode)` under the Claude order. The sketch gave `no-match(heuristics)` under the Codex order, but that part was wrong, see the next line. Saved `loop/sketch_checks_output.txt`.
- **Codex resolves the base name, verified from code.** When no rule matches an absolute program path, Codex looks up rules for its base name, `exec_policy.rs:372-374` and `policy.rs:344-371` at `rust-v0.156.1`. So a forbidden rule on `rm` denies `/bin/rm -rf build` in Codex. "A deny on `rm` does not stop `/bin/rm`" holds for Claude Code only. Codex still misses a `timeout` or `devbox run` wrapper, a Python one-liner and `find -delete`. Built Phase 2 section 2.2 and `rule_order.py` teach both.
- **Codex falls back to heuristics, verified.** When no rule matches, a heuristics fallback decides, `policy.rs:290-293`.
- **Matching details, verified, permissions page.** Compound commands split on `&&`, `||`, `;`, `|`, `|&`, `&` and newlines, and a rule must match each part, line 212. Deny and ask rules also apply inside subshells, command substitutions and `for` loop bodies, line 215. A deny rule matches past a leading variable assignment. An allow rule does not match past an unknown assignment, line 227. `Bash(devbox run *)` also matches `devbox run rm -rf .`, line 231.

Summary: a rule is a filter on text. The sandbox, in 4.6 to 4.12, is the boundary.

### 4.4 In the Claude Code CLI, a PreToolUse hook that fails in any of four ways lets the call run, while an Agent SDK callback that times out blocks it

A learner writes a policy hook and assumes that a broken hook fails safe.

- **Best evidence, verified.** Hooks reference line 873: "A timed-out `command`, `http`, or `mcp_tool` hook doesn't block the tool call." Saved `loop/cc_hooks.md`.
- **The four fail-open paths, verified, same page.**
  1. Timeout, line 873.
  2. Exit code 1: Claude Code "treats exit code 1 as a non-blocking error and proceeds with the action", line 864.
  3. A script that does not exist: "a mistyped path in `settings.json` leaves the gate silently disabled", line 861. This holds for a shell script or a command that the shell cannot find, which exits 127. A missing Python script run as `python x.py` makes CPython exit 2, which blocks the call. The exit codes were measured in built Phase 2 section 2.3. The Claude Code effect is inferred from the exit-code rule.
  4. An HTTP hook with a non-2xx status or a connection failure: "non-blocking error, execution continues", lines 925 to 926.
- **What blocks, verified.** Only exit code 2, or a JSON deny. Exit 2 "blocks whether or not you print JSON". Exit 2 with invalid JSON "still blocks", line 830. Before v2.1.214 it did not block.
- **The SDK default is the opposite, verified.** Agent SDK hooks line 789: on a `PreToolUse` callback timeout, "Claude Code doesn't run the tool call". Claude receives a tool result that says the hook did not respond. Before v2.1.210 the timeout was reported as a user rejection. Saved `loop/cc_agent-sdk_hooks.md`.
- **Timeout behaviour also depends on the event, verified.** A timed-out CLI hook on `PreModelSwitch` blocks, hooks line 871. An SDK callback that times out on `UserPromptSubmit` blocks the prompt, "because a callback there can be acting as a policy gate that must not fail open", line 1351.
- **Post hooks cannot undo, verified.** `PostToolUse` exit 2 "Shows stderr to Claude; the tool already ran", line 893. `PermissionRequest` does not honour exit 2 at all, line 883.
- **Timeout defaults, verified.** 600 seconds for `command`, `http` and `mcp_tool`. 30 for `prompt`. 60 for `agent`. Hooks line 430. Agent SDK callbacks follow the command defaults, SDK hooks line 785.
- **Python SDK callbacks get no cancel signal, verified.** `_internal/query.py:568` at v0.2.158 passes `{"signal": None},  # TODO: Add abort signal support`. The TypeScript callback gets an `AbortSignal`, SDK hooks line 801.
- **Not checked.** What the CLI does when a Python callback raises. The SDK sends a control response with subtype `error`, `query.py:611-622`. The CLI is closed source and no page says what happens next.

Summary: in the CLI, only exit 2 or a JSON deny is a gate. Every other failure opens it.

### 4.5 People approve almost every permission prompt, and they catch fewer dangerous commands as a session gets longer, so a prompt alone is a weak control

All numbers below are vendor numbers from Anthropic unless marked.

- **Best evidence, verified, vendor study with a stated design.** Anthropic blog, 2026-08-07, "Auto mode is now the default in Claude Code". 1,053 paid testers hired "through a research vendor", in a test environment built for the study. One prompt per session was replaced by a clearly dangerous command. Testers caught it "13.6% of the time (143 of 1,053)". Auto mode blocked "89% of the same commands (937 of 1,053)". Lines 258 to 260 of `loop/claude_blog_auto_default.txt`. Not peer reviewed. The command set and the prompt position are not published.
- **Arithmetic, verified by run.** 143/1053 = 0.1358 and 937/1053 = 0.8898. Head to head, 800 commands blocked by auto mode were approved by a human, and humans blocked 6 that auto mode allowed. 143 + 800 − 6 = 937. Saved `loop/arith_check_1053.txt`.
- **Fatigue, verified, same study.** Humans "blocked about 17% of dangerous commands early in a session, dropping to about 5% after 50 or more prior prompts". The post gives two points, not a curve.
- **Approval rates, verified as quotes, conditions not stated.** "Claude Code users approve 93% of permission prompts", 2026-03-25 post, line 14. "users approve 97% of permission prompts", 2026-08-07 post, line 246. Neither post states a window or a sample. Do not compute a trend from them.
- **Classifier error rates, verified, vendor.** Auto mode post, Table 1. Stage 1 plus stage 2 pipeline, classifier on Sonnet 4.6. False-positive rate 0.4% on 10,000 real internal actions. False-negative rate 17% on 52 curated real overeager actions. False-negative rate 5.7% on 1,000 synthetic exfiltration cases.
- **The vendor's own caveat, verified.** For someone "manually approving every action carefully, it's arguably a regression". Auto-mode post line 117.
- **A user rule set aside on purpose, verified.** In auto mode, broad allow rules such as `Bash(python:*)` "are set aside", because they would let commands skip the classifier. 2026-08-07 post line 254.
- **Settings data, verified, vendor.** As of June 2026, 49.5% of active CLI users had a Bash allow rule, and 25% of interactive sessions started in bypass mode. Same post, lines 247 to 253.
- **Injection test, verified, vendor-commissioned.** Trajectory Labs tested "72 indirect prompt injection scenarios held out from Anthropic", each 10 times, 720 attempts. Tools: "the latest publicly available versions of Claude Code and Codex as of July 17th 2026", with an identical Trajectory Labs browser MCP integration. "none of the 720 attack attempts succeeded against Claude Fable 5, Opus 5, or Sonnet 5 running auto mode." GPT-5.6 Sol at "max" effort in Codex v0.144.5 Auto-review had 5.83%. The attacks were optimized against Claude Opus 4.7. Anthropic commissioned the test. Lines 271 to 284 of the same file.
- **One small independent result, verified.** Li et al., arXiv 2605.11360v1, preprint, 2026-05-12. In the pre-screening of the user study, "13 of 16 (81%) use “Always Allow” simply to dismiss prompts". N is 16.

Summary: an average person clicks yes. A classifier catches more than that person, and less than a careful one.

### 4.6 Every sandbox draws its boundary in one place, and what it cannot stop follows from that place

A learner calls every isolation mechanism "a sandbox" and assumes they stop the same things.

- **Best evidence, verified.** The kernel seccomp page says "System call filtering isn’t a sandbox." https://docs.kernel.org/userspace-api/seccomp_filter.html, section "What it isn't". Saved `sandbox/k_seccomp.txt` line 81. Kernel docs version on the page: 7.3.0-rc4.

| Mechanism | Where the boundary sits | What it cannot stop, by design | Evidence |
|---|---|---|---|
| Namespaces and cgroups, as in runc and Docker | Around the process's view of resources. The host kernel is shared | A kernel bug reached through any allowed system call | man7 `namespaces(7)`, `sandbox/k_namespaces.txt:11`. Built `docker-containers` phase 0 |
| seccomp | At the system call number and argument values | Anything reached through an allowed call. "BPF programs may not dereference pointers", so it cannot read file paths | `sandbox/k_seccomp.txt:64-80` |
| Landlock | At file hierarchies and TCP or UDP ports | Host names. "the object is a TCP or UDP port" | `sandbox/k_landlock.txt:85-87` |
| gVisor | Between the application and the host kernel | Hardware side channels. Resource exhaustion without cgroups | `sandbox/gvisor_security.txt:222-231` |
| Firecracker | At the hardware virtualization line. The guest has its own kernel | Bugs in the VMM or KVM. The VMM process needs its own `jailer` | `sandbox/fc_design.md:51,166-195` |
| Seatbelt, bubblewrap, as agent CLIs use them | Around one child process tree on the developer's machine | Anything the unsandboxed harness does for the child, see 4.7 | Claude Code and Codex docs |

- **gVisor, verified.** gVisor "relies on the host operating system and the platform for defense against hardware-based attacks" and "relies on the host resource mechanisms (cgroups)". Its host calls "do not include the creation of new sockets (unless host networking mode is enabled) or opening files (unless directfs is enabled)". `gvisor_security.txt:200-231`. "systrap replaced ptrace as the default gVisor platform in mid-2023", `gvisor_platforms.txt:122`.
- **Landlock limits, verified.** Network rules exist "since ABI v4 for TCP and v10 for UDP". `chroot(2)` calls are not denied. At most 16 stacked rulesets. `k_landlock.txt`, "Current limitations".
- **Codex on Linux, verified.** At `rust-v0.156.1`, bubblewrap does filesystem isolation. `codex-rs/linux-sandbox/src/landlock.rs:145-146`: the Landlock file function "is currently unused because filesystem sandboxing is performed via bubblewrap". Saved `sandbox/codex156_landlock.rs`. Codex uses the first `bwrap` on PATH, and without one it falls back to a bundled helper that needs unprivileged user namespaces, `codex_sandboxing.txt:727-729`.
- **Codex seccomp filter, verified.** `landlock.rs:179-232` at `rust-v0.156.1`. It denies `ptrace`, `process_vm_readv` and `process_vm_writev` in most modes. It always denies `io_uring_setup`, `io_uring_enter` and `io_uring_register`. In restricted network mode it denies `connect`, `accept`, `bind`, `listen`, `sendto` and others, and allows `socket` only for `AF_UNIX`. The same list is at `rust-v0.154.0`, `codex154_landlock.rs`.
- **Why io_uring is denied, inferred from a code comment.** The comment says "io_uring can create AF_VSOCK sockets without a socket() syscall". A seccomp filter checks each system call, and io_uring submits work through shared memory. Check: the kernel `IORING_OP_SOCKET` documentation.
- **Seatbelt, verified.** The Codex base policy at `rust-v0.156.1` starts with `(deny default)` and says child processes inherit the parent's policy, `codex156_seatbelt_base_policy.sbpl:8-12`. The sandbox-runtime profile also starts with `(deny default ...)`, `srt077_macos-sandbox-utils.ts:970`. The macOS man page marks `sandbox-exec` as DEPRECATED on macOS 26.6, `sandbox/local_man_sandbox-exec.txt`. Codex and sandbox-runtime still call it.

Summary: name the boundary first. Then list what crosses it without touching it.

### 4.7 In agent CLIs, published escapes happen at the seam between the sandboxed child and the unsandboxed harness, not through the kernel sandbox

A learner reads "symlink sandbox escape" and assumes the kernel check failed.

- **Best evidence, verified.** CVE-2026-39861, Claude Code before 2.1.64, published 2026-04-20. The sandboxed process made a symlink, and then "its unsandboxed process followed the symlink and wrote to the target location outside the workspace". The advisory says "neither the sandboxed command nor the unsandboxed app could independently write outside the workspace, but their combination could". Saved `sandbox/cc_adv.json`.
- **The kernel check held, verified by run.** The probe ran under a `deny default` Seatbelt profile. A symlink from the work folder to a file outside did not let the sandboxed process read that file. Row "symlink in work -> outside" gave rc=1. The self-test printed "SELF-TEST PASS: profile S did not leak the canary". Saved `sandbox/lab/probe_matrix_run4.txt`. Conditions: macOS 26.6, arm64, 2026-09-23.
- **Other seam bugs, verified from advisory JSON.** Mechanism only. Module 16 owns defence.

| Published | ID | Product and versions | Mechanism |
|---|---|---|---|
| 2025-08-15 | CVE-2025-55284 | Claude Code before 1.0.4 | A broad safe-command allowlist let a read and a network send run without a prompt |
| 2025-09-19 | CVE-2025-59532 | Codex CLI 0.2.0 to 0.38.0 | A model-supplied `cwd` became the writable root |
| 2025-12-04 | CVE-2025-66479 | sandbox-runtime before 0.0.16 | An empty allowed-domain list did not enforce the network sandbox |
| 2026-02-06 | CVE-2026-25724 | Claude Code before 2.1.7 | Deny-rule bypass through symbolic links |
| 2026-02-06 | CVE-2026-25725 | Claude Code before 2.1.2 | A missing `settings.json` was not protected. Code created it and added hooks that ran with host privileges at restart |
| 2026-06-25 | CVE-2026-55607 | Claude Code 2.1.38 to before 2.1.163 | A worktree named `.git`, symlinks and `fsmonitor` overwrote `~/.zshenv` |

- **Protected paths, verified.** The Claude Code sandbox denies writes to `.claude` settings, hooks, `.mcp.json`, shell startup files, `.git/hooks` and `.git/config` inside writable folders. If a symlink appears at a protected settings path, the sandbox also denies writes to its target. `sandbox/cc_sandboxing.md` lines 503 to 514. **Inferred:** these rules are the fixes for CVE-2026-25725 and CVE-2026-39861. No page says so. Check: the Claude Code changelog for 2.1.2 and 2.1.64.
- **Escape hatch, verified.** Claude "may retry the command with the `dangerouslyDisableSandbox` parameter". `allowUnsandboxedCommands: false` turns this off. `cc_sandboxing.md` lines 151 to 158.
- **Coverage, verified.** The Claude Code sandbox covers Bash subprocesses. "Read, Edit, and Write use the permission system directly rather than running through the sandbox", line 730.
- **Advisory counts, verified on 2026-09-23.** The `anthropics/claude-code` advisory endpoint lists 30 advisories. At least two of them are for Claude Desktop. `openai/codex` lists 1. `anthropics/sandbox-runtime` lists 1. `google-gemini/gemini-cli` returns an empty list from the repository endpoint. Saved `sandbox/advisories_parsed.txt` and the `*_adv.json` files.
- **Gemini CLI GHSA-wpqr-6v78-jr5g, verified.** The GitHub advisory page exists. Its title is "Gemini CLI: Remote Code Execution via workspace trust and tool allowlisting bypasses". It says that in yolo mode Gemini CLI "would ignore any fine grained tool allowlist". The page names 0.39.1 as a patched version. Saved `m07_refresh/gemini_ghsa.html`.

Summary: test the harness code that acts on paths the child chose. The kernel check is rarely the weak part.

### 4.8 A domain allowlist proxy limits where connections go, not what data leaves

- **Best evidence, verified.** Claude Code sandboxing docs, "Security limitations": the proxy "makes its allow decision from the client-supplied hostname without inspecting TLS", so code "can potentially use domain fronting". Saved `sandbox/cc_sandboxing.md` line 712.
- **The real case, verified.** CVE-2026-54316, Claude Code 0.2.54 to before 2.1.163, published 2026-06-13. The advisory title names WebFetch. So the list was the pre-approved host list of a harness tool, not the sandbox network proxy. The mechanism is the same, because both lists decide only the destination. `huggingface.co` was pre-approved. HuggingFace "counts as downloads server-side" each fetch of an attacker file, which gave "a covert out-of-band channel". Saved `sandbox/cc_adv.json`.
- **Defaults, verified.** "Claude Code pre-allows no domains by default", `cc_sandboxing.md` line 522. Codex: "By default, the agent runs with network access turned off", `sandbox/codex_approvals.txt:689`. In Codex, network on plus `network_proxy` off means unrestricted direct network, and `network_proxy` is off by default, `codex_approvals.txt:767-831`.
- **Programs that ignore the proxy fail, verified.** sandbox-runtime README, "Linux proxy bypass": programs that do not respect `HTTP_PROXY` end up "unable to connect to the internet". `sandbox/srt_readme.md:891`. On Linux, "The network namespace of the sandboxed process is removed entirely", line 124.
- **Resolved-address check, verified.** Before dialing an allowed name, the sandbox-runtime proxy drops loopback, link-local, cloud metadata and host interface addresses. "Private-use space is not denied by default". `srt_readme.md:361-367`.
- **Egress designs, verified or inferred as marked.**

| Design | What it stops | What still leaks | Evidence |
|---|---|---|---|
| No network, net namespace removed | All IP traffic | Covert channels through shared files or allowed Unix sockets | srt README line 124, verified. Channels inferred |
| Host-name allowlist proxy, no TLS inspection | Connections to names off the list | Uploads to any allowed host. Domain fronting | Claude Code docs line 712, verified |
| Allowlist plus method limit | POST and PUT to allowed hosts | Data in GET URLs | Codex cloud can limit requests to "GET, HEAD, and OPTIONS", `codex_internet.txt:759`, verified. GET leak inferred |
| Allowlist plus TLS termination | Credential masking becomes possible | Content is not filtered | `tlsTerminate` "does not add content filtering", `cc_sandboxing.md` line 709, verified |

Summary: every allowed host is an upload path. Choose hosts as if they were write targets.

### 4.9 DNS is a second egress path, so a profile that blocks TCP can still send data through name lookups if the resolver socket is reachable

- **Best evidence, verified by run.** macOS 26.6, arm64, 2026-09-23. Saved `sandbox/lab/dns_narrow_run.txt` and `sandbox/lab/probe_matrix_run4.txt`.
  - Profile `(allow default)(deny network*)`: `https example.com` gives rc=6. A Python lookup fails, rc=1.
  - Add one rule that allows connect to the Unix socket `/private/var/run/mDNSResponder`. The lookup succeeds and prints `resolved 104.20.23.154`. A TCP connect to that address still fails with `PermissionError: [Errno 1] Operation not permitted`.
- **So on macOS the resolver is reached through a Unix socket.** A rule that opens all Unix sockets also opens DNS. The probe's break-it row "allow all unix sockets" resolved the name, rc=0, and HTTPS still failed, rc=7.
- **Inferred.** sandbox-runtime's `allowAllUnixSockets` opens DNS the same way. Basis: its rule allows `(remote unix-socket (path-regex #"^/"))`, `srt077_macos-sandbox-utils.ts:1183-1186`. Check: run srt 0.0.77 with `allowAllUnixSockets: true` and try a lookup.
- **Not checked.** Whether a query for a unique name reaches an outside authoritative server. It needs a packet capture as root.

Summary: count the resolver as a network path when you write a no-network profile.

### 4.10 The default read policy of the Claude Code sandbox and sandbox-runtime is the whole disk, and the Claude Code sandbox runs commands without sandboxing when it cannot start

- **Best evidence, verified.** Claude Code sandboxing docs, line 496: "read access to the entire computer", which "still allows reading credential files such as `~/.aws/credentials` and `~/.ssh/`". Saved `sandbox/cc_sandboxing.md`.
- **Fail open on start, verified.** Line 62: if the sandbox cannot start, "Claude Code shows a warning and runs commands without sandboxing". `sandbox.failIfUnavailable: true` makes it a hard failure, line 639. The failure "blocks Claude Code from starting". It does not refuse single commands.
- **Environment, verified.** Sandboxed commands "inherit the parent process environment by default, including any credentials set there", line 732.
- **Verified by run.** A network-only profile, `(allow default)(deny network*)`, still read the outside canary file: "read outside folder rc=0 secret-canary". Saved `sandbox/lab/probe_matrix_run4.txt`.
- **sandbox-runtime defaults, verified.** Reads allowed everywhere, writes denied everywhere, network denied. `srt_readme.md:119-122`. The README banner says "Beta Research Preview".
- **Codex read default, not checked.** Whether the Codex sandbox reads outside the workspace by default was not checked. So the whole-disk read default is stated for Claude Code and sandbox-runtime only.
- **Write defaults, verified.** Claude Code allows writes in the working directory, added directories and the session temp directory, `cc_sandboxing.md` line 495. Codex modes are `read-only`, `workspace-write` and `danger-full-access`, `codex_sandboxing.txt:806-812`.
- **Weakening options, verified.** `enableWeakerNestedSandbox` "considerably weakens security". `allowAppleEvents` "removes code-execution isolation". `cc_sandboxing.md` lines 717 to 718.
- **Platforms, verified.** macOS uses Seatbelt. Linux and WSL2 use bubblewrap. WSL1 and native Windows are not supported by the Claude Code sandbox. Lines 562 to 570.

Summary: set `failIfUnavailable` and a read deny list before you call a CLI sandbox a control.

### 4.11 A microVM boot time is not a cold-start time, because products hide boot with a warm pool

- **Best evidence, verified, peer reviewed.** Firecracker, USENIX NSDI 2020, Amazon Web Services, section 4. "While the 125ms boot times offered by Firecracker are fast, they are not fast enough for the scale-up path of Lambda". Lambda keeps a small pool of pre-booted microVMs, and at 125 ms creation time "one pooled MicroVM is required for every 8 creations per second". Saved `sandbox/fc_nsdi.txt:798-810`. This is Little's law: pool size equals creation rate times creation latency.
- **Paper conditions, verified.** Firecracker v0.20.0 against QEMU v4.2.0 on m5d.metal, 48 cores with hyperthreading off, Ubuntu 18.04.2, kernel 4.15.0-1044-aws. Guest kernel 4.14.94, 1 vCPU, 256 MB. With 50 concurrent boots out of 1,000, pre-configured Firecracker p99 was 146 ms and Cloud Hypervisor 158 ms. `fc_nsdi.txt:925-1035`.
- **Current spec, verified.** `SPECIFICATION.md` at tag v1.17.0 is byte-identical to `main`. "<= 125 ms" from the InstanceStart call to guest `/sbin/init`, with serial console off, a minimal kernel and root file system, 1 vCPU and 128 MiB. VMM start "within `8 CPU ms`", wall clock 6 to 60 ms, typical about 12 ms, on M5D.metal and M6G.metal. VMM memory overhead "<= 5 MiB". `fc_spec.md:14-17, 37-41`.
- **An OS sandbox costs milliseconds per process, verified by run.** The course uses the Phase 3 re-run of `cold_start.py`, saved `runs/agent-harness_p03_cold_start.txt`. Apple M4 Pro, macOS 26.6, arm64, warm file cache, N=40 after 3 warm-ups, Python 3.12.14 from uv called by its real path.
  - `/usr/bin/true`: bare median 2.08 ms, Seatbelt `deny default` 8.09 ms, `allow default` 7.84 ms. So `deny default` adds 6.01 ms.
  - `python -c pass`: bare median 13.20 ms, `deny default` 19.25 ms. So it adds 6.05 ms.
  - The research runs, `sandbox/lab/cold_start_run3.txt` and `cold_start_run4.txt`, gave 8.87 to 9.56 ms sandboxed for `true`, about 6.5 to 7.5 ms added. Their `python3` rows, about 21 to 24 ms added, ran another interpreter, the research script's own `sys.executable`, not the uv Python 3.12.14. Why that interpreter paid more is not checked. Do not quote those rows.
- **gVisor start through Docker, verified, old data.** runsc started an empty container in 1,144 ms and runc in 1,193 ms. The page says "most of the time overhead above is associated Docker itself". GCE n1-standard-4, Debian 9, kernel 4.19, ptrace platform. Saved `sandbox/gvisor_startup.csv`, `gvisor_perf.txt`. Current numbers on systrap: not checked.
- **Not measured.** A container start on this Mac. Docker is not installed. Podman 6.0.2 is installed with a libkrun machine that has never started. Saved `sandbox/local_podman.txt`.

Summary: quote a boot time with its pool size, or it is not a user-facing latency.

### 4.12 One current model now saturates SandboxEscapeBench, a container escape benchmark, so "zero success on the hardest levels" is true only for the first cohort of models

- **Best evidence, verified, peer reviewed.** SandboxEscapeBench, arXiv 2603.02277 v3, revised 2026-08-01. University of Oxford and UK AI Security Institute. The PDF header says "PMLR 306, 2026", the ICML 2026 proceedings. Saved `sandbox/escapebench.txt`, `sandbox/escapebench_abs.txt`.
  - **Setup.** 18 tasks: 4 orchestration, 8 runtime, 6 kernel, difficulty 1 to 5. A Docker container inside a VM. Success means reading `/flag.txt` on the host. 5 samples per model and task. 95% Wilson intervals. Lines 140 to 147 and 436 to 448.
  - **Condition on every number.** Each task has a weakness the authors put there on purpose. The model has a shell, and monitoring is minimal. The paper says its results "should not be interpreted as end-to-end compromise likelihood in defended production environments". Lines 803 to 809.
  - **First cohort.** Budget 2.5 million tokens. GPT-5 and Opus 4.5 each reached "a success rate of 0.40 [0.26, 0.56]" on level 3, "while we observe zero success on levels 4 and 5". Lines 482 to 485.
  - **Section 6, "Updated Results".** Mythos Preview, Opus 4.6, GPT-5.4 Pro and GPT-5.5 ran "under the same configuration as in Section 5" with the token limit extended to 100 million. Claude Mythos Preview "now saturates the benchmark". "Mythos Preview achieves a pass@5 of 100% on the harder tasks." Lines 730 to 801.
- **A new failure mode, verified.** Agents crashed their own sandbox. The sandbox became unresponsive in 14 of 14 Mythos Preview failures, 20 of 31 Opus 4.6 failures, 19 of 30 GPT-5.4 Pro failures and 15 of 32 GPT-5.5 failures. Crashes count as failures. Lines 772 to 776.
- **Conditions to state with any number.** The two cohorts used budgets of 2.5 million and 100 million tokens. So their success rates are not directly comparable.
- **An internal disagreement, not resolved.** Section 5 gives Opus overall "0.49 [0.39, 0.59]", line 495. Table 11f, the pooled summary, gives Opus 4.5 overall 0.52 [0.42, 0.63]. The 0.49 [0.39, 0.60] at line 3138 is the GPT-5 row, not Opus. Table 11f also gives 0.41 [0.26, 0.58] on level 3 for both models, and 0.14 on level 5 for Opus 4.5, against zero in section 5. Section 6.1 says Opus 4.5 "succeeded on 56% of samples", line 742. The paper does not say which budget the 56% used.

Summary: treat a container as a boundary a current model may cross, and give the model's token budget with any escape rate.

### 4.13 "max_turns" counts a different unit in each SDK, and Anthropic's own sources define a Claude turn in three ways

A learner sets `max_turns=10` and expects 10 tool calls.

- **Best evidence, verified by run.** An offline run with a scripted fake model and no API key. A task that needs 3 tool rounds needs 4 model calls. `openai-agents==0.22.3` with `max_turns=3` raised `MaxTurnsExceeded after model_calls=3`. `pydantic-ai-slim==2.48.0` with `request_limit=3` raised `UsageLimitExceeded after model_calls=3`. With 2 tool rounds, both finished after 3 calls. Saved `loop/cap_openai_output.txt` and `loop/cap_pydantic_output.txt`. Scripts `loop/cap_openai.py`, `loop/cap_pydantic.py`. Conditions: macOS arm64, Python 3.12.14, `uv run --no-project`, 2026-09-23.
- **So both SDKs count the final answer call as a turn.** OpenAI `run.py:301-302` at v0.22.3: a turn is "defined as one AI invocation (including any tool calls that might occur)."
- **Three Claude definitions, verified.**
  1. Agent SDK docs, agent-loop line 46: `max_turns` "counts tool-use turns only". Line 198: default "No limit".
  2. Python `types.py:2042-2043` at v0.2.158, and TypeScript `sdk.d.ts:1862-1863` at 0.3.280: "A turn consists of a user message and assistant response."
  3. TypeScript `sdk.d.ts:73`, the sub-agent `maxTurns`: "Maximum number of agentic turns (API round-trips)". And `sdk.d.ts:5493`: `num_turns` "counts model round-trips within one turn".
  - The runtime is the closed-source CLI. Which unit it applies: not checked. Check: run the Agent SDK with 3 tool rounds and `max_turns=3`, and read `num_turns` and the result subtype.
- **Defaults and units per SDK, verified.**

| SDK and version | Option | Default | One unit is | At the cap | Evidence |
|---|---|---|---|---|---|
| OpenAI Agents SDK 0.22.3 | `max_turns` | 10 | one model call, final answer included | raises `MaxTurnsExceeded`, unless an `error_handlers["max_turns"]` handler is set | `run_config.py:45`, `run.py:1503-1528`, run |
| Pydantic AI 2.48.0 | `UsageLimits.request_limit` | 50 | one model request, final answer included | raises `UsageLimitExceeded` before the request | `usage.py:457`, `523-524`, run |
| Pydantic AI 2.48.0 | `UsageLimits.tool_calls_limit` | none | one tool call | raises before the call | `usage.py:459`, `584-588` |
| Claude Agent SDK Python 0.2.158 | `max_turns` | none | three definitions, see above | `ResultMessage` subtype `error_max_turns` | `types.py:2040-2044`, agent-loop lines 46, 198 |
| Claude Agent SDK | `max_budget_usd` | none | US dollars across the session | subtype `error_max_budget_usd` | `types.py:2046-2050`, agent-loop line 201 |
| LangGraph 1.2.12 | `recursion_limit` | 10007, or env `LANGGRAPH_DEFAULT_RECURSION_LIMIT` | one graph superstep | error class not checked at this tag | `_internal/_config.py:32` |

- **Budget and turns differ in scope, verified.** Agent-loop line 205: with streaming input, "the max-turns count starts over" per message, but "The budget total keeps accumulating across messages".
- **LangGraph, inferred.** A prebuilt ReAct agent spends about two supersteps per tool round. So `recursion_limit=10` allows about 4 tool rounds. Check: run `create_react_agent` with a fake chat model at 1.2.12 and count steps.
- **LangGraph docs against code, verified on 2026-09-17, not re-read today.** The docs said "1000 steps" from 1.0.6. The code says 10007. The code is what runs.

Summary: name the SDK and its unit with every turn cap. Add a budget cap for the session.

### 4.14 A turn cap stops a loop late, and a stuck detector stops it early only if it compares the right fields

- **Best evidence, verified.** OpenHands software-agent-sdk v1.49.1 scans the last 20 events: `MAX_EVENTS_TO_SCAN_FOR_STUCK_DETECTION: int = 20`, `stuck_detector.py:21`. Default thresholds in `conversation/types.py`, `StuckDetectionThresholds`: repeated action and observation 4, repeated action and error 3, monologue 3, alternating pattern 6. Fetched 2026-09-23 at the v1.49.1 tag. Saved `m07_refresh/oh_stuck_detector.py`, `m07_refresh/oh_types.py`.
- **A stub, verified.** The context-window loop check returns `False` under `# TODO: blocked by https://github.com/OpenHands/agent-sdk/issues/282`, `stuck_detector.py:322-323`.
- **Verified on 2026-09-17, not re-read today.** At exactly the action-error threshold, the SDK sends a nudge message. Above it, it marks the agent stuck. Two events match when source, thought, action and tool name match, and IDs are ignored.
- **LangChain middlewares, verified on 2026-09-17 at langchain 1.4.1, not re-read today.** `ToolCallLimitMiddleware` default `exit_behavior` is `"continue"`. `ModelCallLimitMiddleware` default is `"end"`. Both default to no limit. **Inferred:** they count calls but do not compare arguments. Check: a test with repeated identical calls.
- **Not checked.** The `LoopDetectionMiddleware` named in a LangChain post. Its code and thresholds were not read. No Anthropic document on detecting repeated identical tool calls was found.
- **Link.** The symptom after compaction, repeated work and no stop, is built Module 2, 3.3.
- **Latest OpenHands release.** Not checked on 2026-09-23. The GitHub API returned 403.

Summary: compare actions without their IDs, and stop on repeats before the cap.

### 4.15 Claude Code bounds sub-agent depth and concurrency, but not the total number of sub-agents in a session, and a session fork does not fork the filesystem

- **Best evidence, verified.** Claude Code sub-agents docs, fetched 2026-09-23. A sub-agent can spawn its own "up to three layers below the main conversation". "when 20 subagents are running in a session, spawning another with the Agent tool fails". "There's no limit on the total number of subagents Claude can spawn over a session." Saved `m07_refresh/cc_sub-agents.md` lines 1007 to 1036.
- **Version history, verified.** From v2.1.172 through v2.1.216, sub-agents could nest up to five layers and the limit could not be changed. v2.1.217 and v2.1.218 defaulted to one. "v2.1.219 raised the default to three". Same file, the note before "Concurrent subagent limit".
- **Slots, verified.** A resumed sub-agent "takes a fresh slot without checking the limit, so resumes can push the running count past it." Workflow agents and agent team teammates follow their own limits. Same section.
- **Session forks, verified.** Agent SDK sessions page: "Forking branches the conversation history, not the filesystem." A forked agent's edits are real and visible to any session in the same directory. Saved `m07_refresh/cc_sessions.md` line 293.
- **Link.** The token cost of a sub-agent is built Module 2, 4.1. The 90.2% multi-agent result and the 15× token figure are taught there. Do not repeat them.
- **Owner.** Module 9, orchestration-durable, section 6.2 "Fan-out waits for the slowest worker" owns width and depth limits for sub-agents in general. Module 7 Phase 1 section 1.4 uses only the missing total cap. The Claude Code depth and concurrency values above are not taught in any built phase. They are an open commitment to Module 9.

Summary: cap depth and concurrency, and add your own session budget, because the harness has no total cap.

### 4.16 A plan written as code keeps the loop, branches and intermediate results out of the model's context, while a plan in context is text the model must re-read each step

- **Best evidence, verified.** Claude Code workflows docs, line 30: "A workflow moves the plan into code." "A workflow script holds the loop, the branching, and the intermediate results itself, so Claude's context holds only the final answer." Saved `m07_refresh/cc_workflows.md`.
- **Link, do not re-teach.** The token numbers for code as the action are in built Module 6, 3.1, with their conditions. That section shows code loses on one or two sequential calls per turn. This module adds only the loop-control view: who holds the plan, and where a stop condition lives.
- **Inferred.** A workflow script moves loop control from the model to the harness, so the stop conditions in 4.13 and 4.14 become ordinary code. Basis: the quote above. Check: compare context tokens for a 50-item batch run both ways, Lab 11 design.

Summary: when the steps are known, put them in a script and let the model do each step.

### 4.17 A harness change looks large against a weak baseline and small against a strong one

- **Best evidence, verified, two sources with opposite results.**
  - LangChain, 2026-02-17, vendor: deepagents-cli improved "13.7 points from 52.8 to 66.5 on Terminal Bench 2.0" with the model fixed at `gpt-5.2-codex`. 89 tasks. Harbor with Daytona sandboxes. The number of runs is not stated. The same post says xhigh reasoning "scored poorly at 53.9% due to agent timeouts compared to 63.6% at high". Saved `m07_refresh/lc_harness.txt`, extracted from `scratchpad/audit/lc_harness.html`.
  - METR, 2026-02-13, independent: "neither Claude Code nor Codex outperform the default scaffolds METR uses". Claude Code beat ReAct in "50.7% of bootstrap samples" for Opus 4.5. Token budgets of 8M and 16M, long autonomous tasks. Saved `m07_refresh/metr.txt`, extracted from `scratchpad/audit/metr.html`.
- **Verified on 2026-09-17, not re-read today.**
  - Terminal-Bench 2.0 leaderboard, read in a browser on 2026-09-17: Claude Opus 4.6 scored 76.4 ±2.4 in Meta-Harness and 58.0 ±2.9 in Claude Code. Whiskers are 95% confidence intervals. The site default view is Terminal-Bench 4.0, so always name the version.
  - HAL, Kapoor et al., arXiv 2510.11977, preprint: 21,730 rollouts, 9 models, 9 benchmarks. Task-specific scaffolds beat the generalist scaffold in 11 of 12 SWE-bench Verified Mini runs.
  - Epoch AI, 2025-12-23: switching the scaffold "makes up to an 11% difference for GPT-5 and up to a 15% difference for Kimi K2 Thinking".
  - Scale SWE Atlas QnA, page updated 2026-07-28: Opus 4.6 scored 33.30 ±5.00 in Claude Code and 30.00 ±4.90 in mini-SWE-agent. The intervals overlap.
- **Inferred.** Large gains appear against weak or generic baselines, and small or no gains against strong ones. Basis: the sources above. Check: no study tests the same model against several strong baselines.

Summary: report a harness gain with its baseline, its number of runs and its interval.

## 5. Proposed phase outline

Five phases. The audit asked to replace the definitions phase with concepts, to take sandboxes from Module 6, and to shrink the old prompt-shape phase. Inferred from the audit's fix list, items 1 to 3.

| Phase | Title | Concepts | Labs | Runs where, costs what |
|---|---|---|---|---|
| 1 | The tool-call path and permission rules | 4.1, 4.2, 4.3 | 1, 2 | Laptop, offline, under one second per run |
| 2 | Hooks and human approval | 4.4, 4.5 | 3, 4 | Laptop, offline |
| 3 | Sandboxes: boundaries, seams and egress | 4.6 to 4.12 | 5, 6, 7, 8 | macOS Seatbelt on the laptop, no Docker. Linux parts read from code |
| 4 | Loop control, sub-agent bounds and plans as code | 4.13 to 4.16 | 9, 10, 11 | Laptop. Lab 9 installs `openai-agents` 1.1 MiB and `pydantic-ai-slim` 1.8 MiB |
| 5 | Measuring a harness change, and incidents | 4.17 | 12, 13 | Laptop, offline. Optional live ablation, cost not estimated |

Phase 3 teaches mechanisms and seams. Module 16 owns defences against injection. The built `docker-containers` course owns namespaces and cgroups, so Phase 3 links it.

## 6. Lab inventory and lab ideas

All labs run offline on the learner's Mac unless marked. No API keys.

### Prototypes that ran on 2026-09-23

| Prototype | Path under `scratchpad/research_agent-harness/` | What it printed | Output saved? |
|---|---|---|---|
| Rule-order sketch | `loop/sketch_checks.py` | Decisions for 6 commands under Claude, Codex and "specific first" orders | Yes, `loop/sketch_checks_output.txt` |
| Approval arithmetic | `loop/sketch_checks.py` | 83.0, 95.0, 86.4 and 11.0 dangerous commands let through per 100 dangerous prompts | Yes, `loop/sketch_checks_output.txt`, `loop/arith_check_1053.txt` |
| OpenAI turn cap | `loop/cap_openai.py` | `MaxTurnsExceeded after model_calls=3` for 3 and 4 tool rounds | Yes, `loop/cap_openai_output.txt` |
| Pydantic request cap | `loop/cap_pydantic.py` | `UsageLimitExceeded after model_calls=3` for 3 and 4 tool rounds | Yes, `loop/cap_pydantic_output.txt` |
| Seatbelt probe matrix | `sandbox/lab/probe_matrix.sh` | 18 probe rows under profiles S and A, and a self-test | Yes, `sandbox/lab/probe_matrix_run1.txt` to `run4.txt`. Run 4 has the self-test |
| DNS narrow break-it | inline in the sandbox report | Lookup succeeds, TCP connect denied | Yes, `sandbox/lab/dns_narrow_run.txt` |
| Sandbox start timer | `sandbox/lab/cold_start.py` | Median, p90 and min for five cases | Yes, `sandbox/lab/cold_start_run1.txt` to `run4.txt`. Runs 1 and 2 include an `xcode-select` error, so use runs 3 and 4 |

Output not saved, re-run before quoting: the uv install time "under a minute" for Lab 9, the probe matrix run time "about 6 seconds", and the start timer run time "about 10 seconds".

### Lab designs

1. **Rule-order evaluator.** Proves 4.2 and 4.3. Three evaluators over one rule set: Claude order with compound splitting, Codex strictest-over-all-matches, and a wrong "most specific first". Prints a command-by-evaluator decision table. Break-it: switch to "most specific first", and `aws s3 ls` becomes allowed despite `deny aws *`. Self-test: `git status && rm -rf build` is `deny` under both real orders. `/bin/rm -rf build` is not `deny`. Add an Agent SDK row with the mode step, and assert that in `bypassPermissions` an unmatched call is approved. Under one second, measured with the sketch.
2. **Unguarded context paths.** Proves 4.1. A fake harness with a PreToolUse hook and an `@file` expansion step. Prints which reads the hook saw. Break-it: read a secret through `@`. Self-test: the hook log misses exactly the `@` read, and a `Read` deny rule on the path stops it. Design only.
3. **Hook failure simulator.** Proves 4.4. Runs a PreToolUse hook as a subprocess with a timeout, then a fake dangerous call, under two policies, `cli` and `sdk_callback`, coded from the docs lines in 4.4. Cases: exit 0, exit 2, exit 1, sleep past the timeout, a missing script, and an HTTP hook that returns 500. Prints ran or blocked per case and policy. Self-test: exit 2 blocks under both. Exit 1 runs under `cli`. Timeout runs under `cli` and blocks under `sdk_callback`. The lab models documented behaviour and does not run Claude Code. Run time inferred under 10 seconds with a 2-second test timeout.
4. **Approval fatigue calculation.** Proves 4.5. Uses the vendor numbers from 4.5. Prints dangerous commands let through per 100 dangerous prompts, then adds a session model with a straight-line fall from 17% to 5% over 50 prompts. The straight line is an assumption, because the post gives two points. Break-it: a careful human with a 100% catch rate, which makes auto mode worse. Self-test: the closed form `N × share × (1 − catch)`, and 143 + 800 − 6 = 937. Under one second.
5. **Seatbelt probe matrix.** Proves 4.6, 4.7, 4.9 and 4.10. Built and run, see the prototype table. Prints one row per probe with its exit code. Break-it: add `(allow network-outbound (remote unix-socket (path-regex #"^/")))`, and DNS starts working while TCP stays blocked. Self-test: exits 1 if profile S returns the canary text. Writes only to `lab/tmp_probe` and deletes it. Sends HTTPS GET requests to example.com and one TCP connect attempt to 1.1.1.1:443. Warning found while building: running the `/usr/bin/python3` shim inside a profile that denies `/private/var/select` made `xcode-select` request a tools install. Allow that path or call the real interpreter path.
6. **Allowlist proxy with an allowed-host upload.** Proves 4.8. A local Python HTTP CONNECT proxy allows one fake host and denies others. A client under profile S sends to both. Prints allowed and blocked counts, and the bytes the allowed host received. Break-it: the allowed fake host stores POST bodies, and the upload succeeds. This is the CVE-2026-54316 mechanism. Self-test: the canary string arrived at the allowed host. Design only, offline.
7. **Seam bug replay.** Proves 4.7. A small Python harness runs a command under profile S, then writes a result file to a path the command named. The command plants a symlink first. Prints whether a file appeared outside. Fix: open with `O_NOFOLLOW`, or resolve and check the real path. Design only.
8. **Sandbox start timer.** Proves 4.11. Built and run, see the prototype table. Prints host, OS, CPU count, N, then median, p90 and min per case. Break-it: no warm-up, which is not measured yet. Self-test: sandboxed median above bare median, N at least 30. Optional Podman part: time `podman run --rm alpine true` cold and warm. It needs an image pull of unmeasured size. UNVERIFIED.
9. **Loop caps compared.** Proves 4.13. One scripted trajectory with k tool rounds under four counters: OpenAI model calls, Pydantic requests, the Claude docs definition, and LangGraph supersteps at two per round, which is inferred. Uses the real `openai-agents==0.22.3` and `pydantic-ai-slim==2.48.0` with a fake model. Prints finished or stopped per k from 1 to 5 at cap 3. Break-it: no cap with a model that never stops, so the harness must stop on a budget. Self-test: k=3 at cap 3 fails for OpenAI and Pydantic and passes under the Claude docs definition.
10. **Stuck detector.** Proves 4.14. Implements the four active OpenHands patterns with thresholds 4, 3, 3 and 6 over the last 20 events. Runs 10 recorded trajectories and prints detections and the turn of detection. Break-it: compare events including their IDs, and the detector misses every loop. Design only.
11. **Plan in context against plan as code.** Proves 4.16. A 50-item batch task run two ways with a scripted model. Prints total context tokens for each. Break-it: a script that pastes all results back into context. Self-test: the token ratio within a stated tolerance. Design only. Link Module 6, 3.1 for the token measure.
12. **Harness A against harness B with intervals.** Proves 4.17. Loads a results file of 89 tasks with pass or fail for two harnesses and several trials. Prints the difference, a bootstrap 95% interval and a paired test. Break-it: one trial per task. Self-test: the interval against a known seed. Link built Module 1, 3.4 and 6.3 for the statistics.
13. **Incident drill.** Replays three incident traces modelled on the Replit, PocketOS and Nx cases in section 7. Prints step, control, and stopped or not. Self-test: a root-scoped token found in a file is flagged.

Optional, UNVERIFIED: run a 20-task subset of a public benchmark with one model in two harnesses. It needs an API key and Docker. Its cost was not estimated from today's prices.

## 7. Failure stories and case studies

Verified on 2026-09-17. Not re-read on 2026-09-23.

| Incident | Date | Primary source | Facts with conditions | Harness control that was missing |
|---|---|---|---|---|
| Replit agent deletes the SaaStr production database | 2025-07-18 | The Register, 2025-07-21 and 2025-07-22. AIID #1152 | Lemkin, quoted by The Register: "I explicitly told it eleven times in ALL CAPS not to do this." A 4,000-record database of fictional people. Rollback did work. Replit promised automatic dev and prod separation | Environment separation. Instructions in the prompt are not a control |
| Gemini CLI loses user files | issue opened 2025-07-21 | github.com/google-gemini/gemini-cli/issues/4586 | Gemini CLI 0.1.13, gemini-2.5-pro, Windows. Closed as not planned. The failed `mkdir` story is only in secondary sources. Partly verified | Checking the result of each step before the next |
| Amazon Q Developer VS Code extension v1.84.0 ships a malicious prompt | bulletin 2025-07-23 | AWS-2025-015, CVE-2025-8217 | A wrongly scoped GitHub token in CodeBuild. The code failed because of a syntax error. Fixed in v1.85.0 | Supply chain. The prompt told the agent to delete files |
| Nx s1ngularity attack uses AI CLIs | 2025-08-26 | GHSA-cxm3-wv7p-598c, CVE-2025-10894. Nx postmortem. StepSecurity. Wiz | The payload ran `claude --dangerously-skip-permissions -p`, `gemini --yolo -p` and `q chat --trust-all-tools --no-interactive`. Nx says active for 4 hours. StepSecurity says just over five hours. Wiz reports over 5,500 repositories in the second phase | Bypass flags that any local process can pass |
| Claude Code deletes home directory contents | 2025-10-21 to 2026-07-30 | anthropics/claude-code issues 10077, 12637, 49464, 82471 | Issue 12637, v2.0.55: Claude made a directory named `~` and then ran `rm -rf *` in the parent. Issue 10077: the log held the result but not the command | Sandbox writes, path checks, and a full audit log |
| AWS Cost Explorer outage linked to Kiro | December 2025 | aboutamazon.com reply, 2026-02-20 | Amazon says "user error—specifically misconfigured access controls". One service in one of 39 regions. Amazon added mandatory peer review for production access. The 13-hour figure is only in secondary sources. Partly verified | Scoped credentials and review for production actions |
| Cursor agent with Claude Opus 4.6 deletes the PocketOS database | about 2026-04-25 | The Register, 2026-04-27 | One Railway API call deleted the volume and its backups in 9 seconds. The agent used a root-scoped token found in an unrelated file. Railway restored the data within an hour. The date comes from secondary coverage | Secret isolation and least-privilege tokens |

## 8. Primary sources

Sources marked "200 today" were fetched on 2026-09-23 with `curl -sL --max-time 60`. Their status is in `loop/fetch_log.txt`, `sandbox/fetchlog.txt` or `m07_refresh/fetchlog.txt`. Sources marked "200 on 2026-09-17" were not re-fetched today. openai.com returns 403 to curl and loads in a browser.

### Execution path, permissions and hooks

- **How tool use works, Anthropic docs** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works — 200 today. Lines 11, 37 to 59.
- **Handle tool calls, Anthropic docs** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls — 200 today. Lines 58, 205 to 255.
- **Configure permissions, Claude Code docs** — https://code.claude.com/docs/en/permissions — 200 today. Lines 44 to 60, 205 to 250, 524 to 532, 626 to 634.
- **Hooks reference, Claude Code docs** — https://code.claude.com/docs/en/hooks — 200 today. Lines 430, 800 to 930, 1590 to 1600.
- **Agent SDK: configure permissions, Anthropic** — https://code.claude.com/docs/en/agent-sdk/permissions — 200 today. Lines 11 to 80.
- **Agent SDK: hooks, Anthropic** — https://code.claude.com/docs/en/agent-sdk/hooks — 200 today. Lines 783 to 801.
- **Codex source at rust-v0.156.1, OpenAI** — https://github.com/openai/codex/tree/rust-v0.156.1 — 200 today. `codex-rs/execpolicy/README.md:95`, `src/policy.rs:403`, `src/decision.rs:12`, `codex-rs/protocol/src/protocol.rs:986-1015`.
- **Agent approvals and security, OpenAI Codex docs** — https://learn.chatgpt.com/docs/agent-approvals-security — 200 today. The retired `untrusted` policy, network default, `network_proxy`.
- **openai-agents-python at v0.22.3, OpenAI** — https://github.com/openai/openai-agents-python/tree/v0.22.3 — 200 today. `run.py:301`, `1503-1528`, `run_config.py:45`, `tool.py:1966`.
- **Guardrails, OpenAI Agents SDK** — https://openai.github.io/openai-agents-python/guardrails/ — 200 on 2026-09-17.

### Human approval

- **How we built Claude Code auto mode, Anthropic, 2026-03-25** — https://www.anthropic.com/engineering/claude-code-auto-mode — 200 today. Table 1, datasets, line 117.
- **Auto mode is now the default in Claude Code, Anthropic, 2026-08-07** — https://claude.com/blog/auto-mode-default-in-claude-code — 200 today. The 1,053-tester study, June 2026 settings data, the Trajectory Labs test.
- **Options, Not Clicks, Li et al., arXiv, 2026, preprint** — https://arxiv.org/abs/2605.11360 — 200 today. User study pre-screening, N=16.
- **How Agents Ask for Permission, Michael and Roesner, arXiv, 2026** — https://arxiv.org/abs/2607.13718 — 200 on 2026-09-17. A survey of 21 proposals and five commercial agents.

### Sandboxes

- **Beyond permission prompts, Anthropic, 2025-10-20** — https://www.anthropic.com/engineering/claude-code-sandboxing — 200 today. The two boundaries and the 84% claim.
- **Configure the sandboxed Bash tool, Claude Code docs** — https://code.claude.com/docs/en/sandboxing.md — 200 today. Default read policy, security limitations.
- **sandbox-runtime README, Anthropic** — https://raw.githubusercontent.com/anthropics/sandbox-runtime/main/README.md — 200 today. Security limitations, resolved-address check.
- **sandbox-runtime Seatbelt generator v0.0.77, Anthropic** — https://raw.githubusercontent.com/anthropics/sandbox-runtime/v0.0.77/src/sandbox/macos-sandbox-utils.ts — 200 today. Lines 970, 1135 to 1230.
- **Codex sandboxing, OpenAI docs** — https://learn.chatgpt.com/docs/sandboxing — 200 today. Modes and the bwrap fallback.
- **Codex cloud internet access, OpenAI docs** — https://developers.openai.com/codex/cloud/internet-access — redirects to learn.chatgpt.com, 200 today. Method limit.
- **Codex landlock.rs at rust-v0.156.1, OpenAI** — https://raw.githubusercontent.com/openai/codex/rust-v0.156.1/codex-rs/linux-sandbox/src/landlock.rs — 200 today. seccomp rules and the Landlock note.
- **Seccomp BPF, Linux kernel docs** — https://docs.kernel.org/userspace-api/seccomp_filter.html — 200 today. "What it isn't".
- **Landlock, Linux kernel docs** — https://docs.kernel.org/userspace-api/landlock.html — 200 today. Network rules, current limitations.
- **namespaces(7), man7.org** — https://man7.org/linux/man-pages/man7/namespaces.7.html — 200 today.
- **bubblewrap README, containers project** — https://raw.githubusercontent.com/containers/bubblewrap/main/README.md — 200 today.
- **gVisor security model, Google** — https://gvisor.dev/docs/architecture_guide/security/ — 200 today.
- **gVisor platforms, Google** — https://gvisor.dev/docs/architecture_guide/platforms/ — 200 today.
- **Firecracker SPECIFICATION v1.17.0, AWS** — https://raw.githubusercontent.com/firecracker-microvm/firecracker/v1.17.0/SPECIFICATION.md — 200 today.
- **Firecracker: Lightweight Virtualization for Serverless Applications, AWS, NSDI 2020, peer reviewed** — https://www.usenix.org/system/files/nsdi20-paper-agache.pdf — 200 today. Sections 4 and 5.1.
- **Quantifying Frontier LLM Capabilities for Container Sandbox Escape, Oxford and UK AISI, ICML 2026, peer reviewed** — https://arxiv.org/abs/2603.02277 — 200 today. v3, sections 5.1 and 6.
- **GitHub security advisories, claude-code** — https://api.github.com/repos/anthropics/claude-code/security-advisories — 200 today.
- **GHSA-wpqr-6v78-jr5g, Gemini CLI** — https://github.com/advisories/GHSA-wpqr-6v78-jr5g — 200 today in HTML. The API URL returned 403.
- **Managed Agents environments, Anthropic** — https://platform.claude.com/docs/en/managed-agents/environments — 200 on 2026-09-17.
- **Claude Code on the web, Anthropic** — https://code.claude.com/docs/en/claude-code-on-the-web — 200 on 2026-09-17.
- **Cloud environments, OpenAI Codex docs** — https://learn.chatgpt.com/docs/environments/cloud-environment — 200 on 2026-09-17.

### Loop control

- **Agent SDK: agent loop, Anthropic** — https://code.claude.com/docs/en/agent-sdk/agent-loop — 200 today. Lines 31 to 48, 194 to 205, 320 to 341.
- **Agent SDK: sessions, Anthropic** — https://code.claude.com/docs/en/agent-sdk/sessions.md — 200 today. Line 293.
- **Sub-agents, Claude Code docs** — https://code.claude.com/docs/en/sub-agents.md — 200 today. Lines 1007 to 1045.
- **Workflows, Claude Code docs** — https://code.claude.com/docs/en/workflows.md — 200 today. Line 30.
- **claude-agent-sdk-python at v0.2.158, Anthropic** — https://github.com/anthropics/claude-agent-sdk-python/tree/v0.2.158 — 200 today. `types.py:2040-2050`, `_internal/query.py:555-622`.
- **claude-agent-sdk TypeScript types 0.3.280, via jsDelivr** — https://cdn.jsdelivr.net/npm/@anthropic-ai/claude-agent-sdk@0.3.280/sdk.d.ts — 200 today. Lines 73, 1862, 5493.
- **pydantic-ai usage.py at v2.48.0** — https://github.com/pydantic/pydantic-ai/blob/v2.48.0/pydantic_ai_slim/pydantic_ai/usage.py — 200 today. Lines 457 to 459, 523, 584.
- **langgraph _config.py at 1.2.12** — https://github.com/langchain-ai/langgraph/blob/1.2.12/libs/langgraph/langgraph/_internal/_config.py — 200 today. Line 32.
- **OpenHands stuck_detector.py at v1.49.1** — https://raw.githubusercontent.com/OpenHands/software-agent-sdk/v1.49.1/openhands-sdk/openhands/sdk/conversation/stuck_detector.py — 200 today.
- **OpenHands conversation types.py at v1.49.1** — https://raw.githubusercontent.com/OpenHands/software-agent-sdk/v1.49.1/openhands-sdk/openhands/sdk/conversation/types.py — 200 today. `StuckDetectionThresholds`.
- **LangChain tool_call_limit.py at langchain 1.4.1** — https://raw.githubusercontent.com/langchain-ai/langchain/langchain%3D%3D1.4.1/libs/langchain_v1/langchain/agents/middleware/tool_call_limit.py — 200 on 2026-09-17.

### Measured harness effects

- **Improving Deep Agents with harness engineering, LangChain, 2026** — https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering — 200 on 2026-09-23 in the audit, saved `scratchpad/audit/lc_harness.html`.
- **Measuring Time Horizon using Claude Code and Codex, METR, 2026** — https://metr.org/notes/2026-02-13-measuring-time-horizon-using-claude-code-and-codex/ — 200 on 2026-09-23 in the audit, saved `scratchpad/audit/metr.html`.
- **Terminal-Bench 2.0 leaderboard, Stanford and Laude Institute** — https://www.tbench.ai/?version=2.0 — read in a browser on 2026-09-17.
- **HAL: Holistic Agent Leaderboard, Kapoor et al., arXiv, 2025, preprint** — https://arxiv.org/abs/2510.11977 — 200 on 2026-09-17.
- **Why benchmarking is hard, Epoch AI, 2025** — https://epoch.ai/gradient-updates/why-benchmarking-is-hard — 200 on 2026-09-17.
- **Scaffold effects on GAIA, Starace, arXiv, 2026, preprint** — https://arxiv.org/abs/2606.08529 — 200 on 2026-09-17. Abstract only.
- **SWE Atlas Codebase QnA, Scale Labs** — https://labs.scale.com/leaderboard/sweatlas-qna — 200 on 2026-09-17.
- **SWE-bench leaderboards** — https://www.swebench.com/ — 200 on 2026-09-17.

### Harness vocabulary, for References only

- **Components of A Coding Agent, Sebastian Raschka, 2026** — https://magazine.sebastianraschka.com/p/components-of-a-coding-agent — 200 on 2026-09-17. The six-part list.
- **mini-coding-agent, Sebastian Raschka** — https://github.com/rasbt/mini-coding-agent — 200 on 2026-09-17. Commit `717cae4`. A small readable harness.
- **Building effective agents, Anthropic, 2024** — https://www.anthropic.com/engineering/building-effective-agents — 200 on 2026-09-17. Workflows against agents.
- **Harness design for long-running application development, Anthropic, 2026** — https://www.anthropic.com/engineering/harness-design-long-running-apps — 200 on 2026-09-17.
- **AGENTS.md** — https://github.com/agentsmd/agents.md — 200 today. Scope gap, see section 2.

### Incidents

Verified on 2026-09-17, not re-fetched today.

- **Replit SaaStr incident, The Register, 2025** — https://www.theregister.com/2025/07/21/replit_saastr_vibe_coding_incident/
- **Replit response, The Register, 2025** — https://www.theregister.com/2025/07/22/replit_saastr_response/
- **AI Incident Database 1152** — https://incidentdatabase.ai/cite/1152/
- **Gemini CLI issue 4586** — https://github.com/google-gemini/gemini-cli/issues/4586
- **AWS-2025-015** — https://aws.amazon.com/security/security-bulletins/AWS-2025-015/
- **Nx advisory GHSA-cxm3-wv7p-598c** — https://github.com/nrwl/nx/security/advisories/GHSA-cxm3-wv7p-598c
- **s1ngularity postmortem, Nx, 2025** — https://nx.dev/blog/s1ngularity-postmortem
- **Nx compromise analysis, StepSecurity, 2025** — https://www.stepsecurity.io/blog/supply-chain-security-alert-popular-nx-build-system-package-compromised-with-data-stealing-malware
- **s1ngularity analysis, Wiz, 2025** — https://www.wiz.io/blog/s1ngularity-supply-chain-attack
- **Claude Code issue 12637** — https://github.com/anthropics/claude-code/issues/12637
- **Claude Code issue 10077** — https://github.com/anthropics/claude-code/issues/10077
- **AWS service outage and Kiro, Amazon, 2026** — https://www.aboutamazon.com/news/aws/aws-service-outage-ai-bot-kiro
- **PocketOS database deletion, The Register, 2026** — https://www.theregister.com/2026/04/27/cursoropus_agent_snuffs_out_pocketos/

Peer review: SandboxEscapeBench and the Firecracker paper are peer reviewed. arXiv 2605.11360, HAL and the GAIA paper are preprints. The rest are vendor docs, vendor posts, leaderboards or source code.

## 9. Tools and versions to pin

Checked 2026-09-23 on npm, PyPI and GitHub unless marked. Files: `loop/versions.txt`, sandbox report section 7, `m07_refresh/pypi_*.json`.

| Tool | Version | Released | Notes |
|---|---|---|---|
| `@anthropic-ai/claude-code` | 2.1.280 | 2026-09-22 | From 2.1.274. Name the version with every version gate |
| `@anthropic-ai/claude-agent-sdk` | 0.3.280 | 2026-09-22 | From 0.3.274 |
| `claude-agent-sdk` Python | 0.2.158 | 2026-09-23 | From 0.2.154. No abort signal for hook callbacks |
| `@anthropic-ai/sandbox-runtime` | 0.0.77 | 2026-09-18 | From 0.0.76. Beta. Windows alpha |
| Codex CLI `@openai/codex` | 0.156.1, tag `rust-v0.156.1` | 2026-09-23 | From 0.154.0. `on-failure` is an alias of `on-request` |
| `openai-agents` | 0.22.3 | 2026-09-17 | From 0.22.2. Pin for Lab 9. `DEFAULT_MAX_TURNS = 10` |
| `pydantic-ai-slim` | 2.48.0 | 2026-09-23 | From 2.44.0. Pin for Lab 9. `request_limit` 50 |
| `langgraph` | 1.2.12 | 2026-09-21 | From 1.2.11. Recursion limit 10007 |
| `langchain` | 1.4.2 | 2026-09-18 | From 1.4.1. Middleware defaults not re-read at 1.4.2 |
| `deepagents` | 0.7.18 | 2026-09-23 | From 0.7.15. Not used in section 4 |
| OpenHands software-agent-sdk | 1.49.1 read | not checked | Latest release not checked, GitHub API 403 |
| Firecracker | v1.17.0 | 2026-09-10 | Spec unchanged at the tag |
| gVisor | release-20260914.0 | 2026-09-16 | systrap default |
| bubblewrap | v0.13.0 | 2026-09-22 | |
| macOS `sandbox-exec` | system binary | macOS 26.6 build 25G72 | DEPRECATED in the man page |
| Podman | 6.0.2 | installed locally | Optional Lab 8 part only |

## 10. Open questions and disagreements

1. **What a Claude "turn" is.** The docs say tool-use round trips. The Python and TypeScript docstrings say a user message plus an assistant response. The TypeScript sub-agent field says API round trips. Only a live run settles it.
2. **Why the CLI fails open and the SDK fails closed.** The SDK blocks on a `UserPromptSubmit` callback timeout because the callback "must not fail open". The CLI does not apply the same argument to its own command hooks. No page gives the reason.
3. **93% against 97%.** Two Anthropic figures, five months apart, neither with a window. They may cover different users or periods.
4. **Is auto mode safer than a human?** The August post says yes on every measure it tested. The March post says it is "arguably a regression" against a careful human. The baseline differs: an average user against a careful reviewer.
5. **Codex `on-failure`.** The code aliases it to `on-request`. The docs page does not mention it. Inferred from the alias. Codex was not run.
6. **DNS under the macOS sandbox.** The sandbox-runtime README says unfenced resolver DNS on Windows "mirrors the macOS behaviour". The local probe shows `deny network*` blocks DNS on macOS 26.6 unless the mDNSResponder socket is allowed. The srt profile does not allow that socket by default. It filters mDNSResponder violations as noise, `srt077_macos-sandbox-utils.ts:1568`. Check: run srt 0.0.77 on macOS with an empty allowlist and call `getaddrinfo`.
7. **SandboxEscapeBench internal numbers.** Section 5 gives Opus overall 0.49 [0.39, 0.59]. Table 11f gives Opus 4.5 overall 0.52 [0.42, 0.63], and GPT-5 overall 0.49 [0.39, 0.60]. Section 6.1 says Opus 4.5 succeeded on 56% of samples. The budgets may differ. Check: Appendix E and the Figure 3 data.
8. **Does the harness matter much?** LangChain reports +13.7 points against its own earlier harness. METR finds no gain for native harnesses over its own scaffolds. Anthropic's harness design post says each component "encodes an assumption about what the model can't do on its own". Verified on 2026-09-17.
9. **Network default for fresh environments.** Codex defaults to no network. Claude Managed Agents defaulted to `unrestricted` on 2026-09-17. Claude Code on the web said "limited by default". The Managed Agents and web pages were not re-read today.
10. **LangGraph recursion limit.** Docs and PR #6676 text said 1000. Code says 10007 at 1.2.12. Module 9 line 103 still says 1,000, per the audit.
11. **Who first listed the six parts of a coding agent.** No earlier source than Raschka was found. This is history and stays out of section 4.

## 11. Things I could NOT verify

1. **Which unit the Claude CLI applies for `max_turns`.** Check: run the Agent SDK with a task of 3 tool rounds and `max_turns=3`, and read `num_turns` and the subtype.
2. **What the CLI does when a Python hook callback raises.** Check: a live run with a callback that raises on PreToolUse.
3. **Why CLI hooks fail open on timeout.** Check: the Claude Code changelog or an issue thread.
4. **Window and sample of the 93% and 97% approval rates.** No check is available from the posts.
5. **Design details of the 1,053-tester study,** such as the command set and prompt position. No paper is linked.
6. **The 84% prompt reduction.** No sample size, window or baseline. Anthropic internal usage.
7. **The server-side loop iteration limit.** How-tool-use-works line 57 names a limit but no number. Check: the server tools page.
8. **LangGraph supersteps per ReAct tool round,** and the error class at the cap at 1.2.12. Check: run `create_react_agent` with a fake chat model, and grep `GraphRecursionError` at the tag.
9. **OpenAI Agents SDK guardrail coverage of hosted tools and handoffs.** From the 2026-09-17 text. Not re-fetched.
10. **Dates of Claude Code version gates** such as v2.1.210, v2.1.214 and v2.1.219. Check: the npm `time` field for each version.
11. **Codex runtime behaviour with `on-failure`.** Check: `codex --ask-for-approval on-failure` in a scratch directory with no network.
12. **Whether a DNS query from a sandboxed lookup reaches an outside server.** Check: `tcpdump -i any port 53` as root while the Lab 5 break-it runs.
13. **Container cold start on this Mac.** Check: start the Podman libkrun machine and time `podman run --rm alpine true` ten times cold and warm.
14. **Whether the Claude Code protected-path and symlink rules are the fixes for CVE-2026-25725 and CVE-2026-39861.** Check: the changelog for 2.1.2 and 2.1.64.
15. **io_uring socket creation without `socket()`.** Only a code comment supports it. Check: the kernel `IORING_OP_SOCKET` documentation.
16. **Firecracker boot time on current releases.** Check: `test_boottime.py` results in the Firecracker CI.
17. **gVisor start-up cost on systrap.** The only first-party numbers use ptrace on Debian 9.
18. **Codex Windows sandbox mechanism.** Not read.
19. **OpenHands latest release.** The GitHub API returned 403 on 2026-09-23.
20. **The OpenHands nudge-then-stuck behaviour and the event equality rule.** Verified on 2026-09-17 only. Check: read `stuck_detector.py` lines 100 to 330 at v1.49.1, saved in `m07_refresh/`.
21. **LangChain middleware defaults at 1.4.2** and `LoopDetectionMiddleware`. Check: grep langchain 1.4.2 and deepagents 0.7.18.
22. **AGENTS.md and project context files as harness input.** Only the repository was confirmed. No research report covered it. Check: a research pass on how Claude Code, Codex and Gemini CLI load context files, and which controls see them.
23. **Terminal-Bench, HAL, Epoch, SWE Atlas and SWE-bench rows in 4.17.** Verified on 2026-09-17 only. Check: re-read before generating.
24. **Incident facts in section 7.** Verified on 2026-09-17 only. Secondary-only facts stay out of teaching text: the Replit 1,200-executive count, the Kiro 13-hour outage length, the PocketOS date and backup age.
25. **Cost of the optional live ablation lab.** Not estimated from today's prices.

## 12. Notes for the course generator

- **Teach claims, not definitions.** Use the one-sentence definition in section 4. Put the six-part list and the naming history in References.
- **Link, do not re-teach:** Module 1 for caching, budgets and retries. Module 2 for compaction, context cost, pruning, sub-agent cost and progress files. Module 6 for tool definitions, tool search, MCP, the code execution tool and code-as-call token numbers.
- **Teach sandboxes here.** Module 6 no longer covers them. Link Module 6, 3.3 for the hosted container.
- **Say "strictest match wins".** Never "most specific wins".
- **State the four CLI fail-open paths.** Timeout alone is not enough.
- **Label every approval number as vendor,** with who ran it and on what. Do not present the 84%, 93%, 97%, 1,053-tester and Trajectory Labs numbers as independent.
- **Name the SDK and its unit with every turn cap.** Name the token budget with every escape rate. Name the benchmark version with every Terminal-Bench score.
- **Do not say Codex uses Landlock for files on Linux.** At `rust-v0.156.1`, bubblewrap does files and seccomp does the network.
- **Do not teach `approval_policy = "untrusted"` or `on-failure`.** The first is retired as a config key. The second silently loads as `on-request`.
- **Do not say programs that ignore `HTTP_PROXY` bypass the Linux proxy.** They fail to connect.
- **Do not say models score zero on the hardest container escapes.** Say which cohort and which budget.
- **`sandbox-exec` is DEPRECATED on macOS.** Say so, so the learner does not treat Lab 5 as a production pattern.
- **Always pair the LangChain gain with the METR result.**
- **Keep Module 16 topics out.** Mention the lethal trifecta in one sentence and link forward.
- **Re-check before generating:** all versions in section 9, the hook version gates and the sub-agent limits. Also re-check the Codex policy names, the advisory list, the rows in 4.17 and the SandboxEscapeBench version.
- **Re-run every prototype and save its output before quoting a number that is not in a saved file.**
- **Fastest to go stale:** CLI version gates, sub-agent defaults, advisory counts, leaderboard rows, and the escape benchmark.

## 13. Refresh log 2026-09-23

### Changes

1. **Section 4 rewritten as 17 claims.** Old topic headings 4.1 to 4.14 are gone. Audit Module 7 fix 1 and brief rule 1. Each claim starts with its single best evidence and its conditions.
2. **Definition history dropped.** Old 4.1 compared the definitions of Osmani, Raschka, Trivedy, Böckeler, Anthropic and OpenAI. Old 4.2 listed Raschka's six parts. Both are gone from section 4. One sentence of definition stays. Raschka moves to section 3 and References. Audit fix 1 and brief rule 10.
3. **Sandboxes moved in from Module 6.** New 4.6 to 4.12, Phase 3, Labs 5 to 8. Audit section 3.3 and fix 3. Module 6 keeps the hosted code execution tool as a tool, linked as Module 6, 3.3.
4. **Old Phase 4 shrunk.** Old 4.9, prompt shape, output clipping, compaction defaults, memory tool and session state, now links to Module 1 and Module 2. Old Labs 9 and 10 are dropped. Only sub-agent bounds and session forks stay, in 4.15. Audit fix 2.
5. **Plan as code narrowed.** Old 4.13 repeated the 98.7%, 37%, 24% and CodeAct numbers. These now live in built Module 6, 3.1. New 4.16 keeps only the loop-control claim. Audit section 3.3.
6. **Five phases, not six.** Section 5. Audit fix 2, inferred.
7. **Overlap table rebuilt** from `grep '^## '` over `inference-internals`, `context-engineering` and `tools-mcp`, with file names and line numbers. Brief rule 9.
8. **New claims from the loop report.** 4.1 exceptions to the tool-call path. 4.3 rules match text and unmatched calls fall through. 4.4 four fail-open paths. 4.13 three definitions of a Claude turn and the measured caps.
9. **New claims from the sandbox report.** 4.6 boundary per mechanism. 4.7 seam bugs. 4.8 allowlist proxies. 4.9 DNS as egress. 4.10 default read policy and fail-open start. 4.11 boot against cold start. 4.12 SandboxEscapeBench v3.
10. **AGENTS.md added as a scope gap.** Audit fix 6. Section 2 and section 11 item 22. The Trajectory Labs conditions are correction 10 below.
11. **Secondary-only quotes dropped from teaching text.** The Boris Cherny, Noam Brown and HumanLayer claims are gone. Audit fix 7.
12. **Versions re-pinned.** Section 9. Audit fix 8.
13. **Lab inventory added.** Section 6 lists the seven prototypes that ran, their paths and their saved outputs.
14. **Kept claims re-checked by fetch.** OpenHands thresholds, sub-agent limits, the workflows quote and the sessions fork quote were fetched again on 2026-09-23. Files in `m07_refresh/`.
15. **Anchor re-check.** 72 anchor strings for 4.1 to 4.17 were grepped. All 72 were found. See "Anchor re-check" below.
16. **Codex Landlock line numbers updated, not an error.** Old line 57 cited `landlock.rs:135-136`. That was right at `rust-v0.154.0`, `sandbox/codex154_landlock.rs` line 135. At `rust-v0.156.1` the note is at lines 145 to 146, `sandbox/codex156_landlock.rs`. 4.6 cites the new tag.
17. **Claude Code advisory count updated.** Old 4.8 said "about 25 advisories of these kinds". On 2026-09-23 the repository endpoint lists 30 advisories of all kinds, and at least two are for Claude Desktop. Evidence: `sandbox/advisories_parsed.txt`. 4.7 gives the count with this condition.
18. **Gemini CLI GHSA-wpqr-6v78-jr5g re-checked.** The sandbox report could not confirm it, because the repository advisory endpoint returns an empty list. The global advisory page exists and matches the old description. Evidence: `m07_refresh/gemini_ghsa.html`. The old text was right.
19. **sandbox-runtime re-pinned** from 0.0.76 to 0.0.77, 2026-09-18. The Claude Code docs still link the old `anthropic-experimental` repository, `sandbox/cc_sandboxing.md` line 572. The npm metadata points to `github.com/anthropics/sandbox-runtime`.

### Corrections to the 2026-09-17 text

1. **"Programs that ignore `HTTP_PROXY` may bypass the proxy path" was wrong.** Old line 153. They fail to connect. The sandbox-runtime README says they end up "unable to connect to the internet". Evidence: `sandbox/srt_readme.md:891`. Fixed in 4.8.
2. **SandboxEscapeBench "zero success on levels 4 and 5" lacked its scope.** Old line 161. That result is for the first cohort at a 2.5-million-token budget. v3, revised 2026-08-01, reports that Mythos Preview "now saturates the benchmark" at 100 million tokens, with pass@5 of 100% on the harder tasks. The paper is in the ICML 2026 proceedings, PMLR 306, so it is peer reviewed, not only an arXiv preprint. Evidence: `sandbox/escapebench.txt` lines 59, 484 to 485, 735, 800 to 801. Fixed in 4.12.
3. **The Codex seccomp list was incomplete.** Old line 157. At both `rust-v0.154.0` and `rust-v0.156.1` the filter also denies `process_vm_readv`, `process_vm_writev`, `accept`, `sendto` and more. At 0.156.1 the lines are `landlock.rs:179-232`. Evidence: `sandbox/codex154_landlock.rs`, `sandbox/codex156_landlock.rs`. Fixed in 4.6.
4. **"Rules are evaluated in order: deny, then ask, then allow" was framed as order only.** Old 4.4 said "The order of evaluation matters more than the rules." The key point is that the strictest match wins, and Codex reaches the same result by a maximum over all matches. Evidence: `loop/cc_permissions.md` lines 52 and 54, `loop/codex_README.md` line 95. Fixed in 4.2.
5. **Hook timeout was presented as the only CLI fail-open case.** Old line 127 and old section 10 item 7. The CLI has four fail-open paths: timeout, exit 1, a missing script, and an HTTP non-2xx or connection failure. Evidence: `loop/cc_hooks.md` lines 861, 864, 873, 925 to 926. Fixed in 4.4.
6. **The status of Codex `on-failure` was "undocumented".** Old line 114 and old section 11 item 10. The code settles it: `#[serde(alias = "on-failure")]` on `OnRequest`. Evidence: `loop/codex_protocol.rs` line 994. "`untrusted` is retired" is true for the config key only. Fixed in 4.2.
7. **"Claude Agent SDK counts tool-use turns" was given as one definition.** Old table 4.11. Anthropic's own sources give three definitions. Evidence: `loop/cc_agent-sdk_agent-loop.md` line 46, `loop/pysdk_types.py` lines 2042 to 2043, `loop/ts_sdk.d.ts` lines 73 and 5493. Fixed in 4.13.
8. **The OpenAI turn unit was described, not measured.** Old table 4.11. Now verified by run: both OpenAI and Pydantic count the final answer call. Evidence: `loop/cap_openai_output.txt`, `loop/cap_pydantic_output.txt`. Fixed in 4.13.
9. **Sub-agent depth default "3 from v2.1.217 and later" was wrong.** Old lines 59 and 195. v2.1.217 and v2.1.218 defaulted to 1. v2.1.219 raised it to 3. Evidence: `m07_refresh/cc_sub-agents.md`, the note before "Concurrent subagent limit". Fixed in 4.15 and section 3.
10. **The Trajectory Labs number lacked its conditions.** Old line 140. Added in 4.5. Audit fix 4.
11. **The OpenAI default tool error message was quoted in part.** Old line 100. A second branch returns a separate message for invalid JSON arguments. The code is the same at v0.22.2 and v0.22.3. Evidence: loop report section 2.1, `loop/oai_tool.py` lines 1966 to 1975 and `loop/oai_tool_v0.22.2.py` lines 1954 to 1960. Fixed in 4.1.
12. **Old section 1 said the same model scores "10 to 28 points apart".** That range mixed benchmarks, baselines and a single-author preprint read from the abstract. Section 1 no longer quotes it. 4.17 gives each number with its source.

### Corrections to the 2026-09-23 research reports, found while merging

1. **The sandbox report's timing range "8.62 to 9.56 ms sandboxed" used a number from run 2.** The report cites runs 3 and 4 only. In those runs the sandboxed `true` medians are 8.87, 8.88, 9.20 and 9.56 ms. 8.62 appears only in `cold_start_run2.txt`, and that run also printed an `xcode-select` error. Evidence: `sandbox/lab/cold_start_run3.txt`, `cold_start_run4.txt`, `cold_start_run2.txt`. The "about 6.5 to 7.5 ms" added cost still holds. Fixed in 4.11.
2. **The sandbox report did not note an appendix interval.** Section 5 says 0.49 [0.39, 0.59]. The appendix table at line 3138 says 0.49 [0.39, 0.60]. Added to section 10 item 7. This entry was itself wrong: line 3138 is the GPT-5 row. See "Corrections found while building the course", row 1.

### Corrections found while building the course

The five phases were built and checked on 2026-09-23. These rows correct this dossier or the research reports. Each row gives its evidence. `runs/` means the scratchpad runs folder.

| # | Old claim | Correct claim | Evidence | Fixed in |
|---|---|---|---|---|
| 1 | Opus overall is 0.49 [0.39, 0.60] in an appendix table | Table 11f gives Opus 4.5 overall 0.52 [0.42, 0.63]. The 0.49 [0.39, 0.60] row is GPT-5. Section 5 text still says Opus 0.49 [0.39, 0.59] | `sandbox/escapebench.txt` Table 11f, after line 3083, and line 495 | 4.12, section 10 item 7 |
| 2 | SandboxEscapeBench rates stated without the threat model | Each task has a planted weakness, a shell and minimal monitoring. The rates are not the chance of a full compromise in a defended system | `escapebench.txt` lines 803 to 809 | 4.12 |
| 3 | A deny rule on `rm` does not stop `/bin/rm`, in both tools | True in Claude Code only. Codex resolves the base name, so `/bin/rm` matches a forbidden `rm` rule | Codex `exec_policy.rs:372-374`, `policy.rs:344-371` at `rust-v0.156.1`. Run `runs/agent-harness_p02_rule_order_canonical.txt` | 4.3 |
| 4 | A missing hook script is always a fail-open path | A missing shell script exits 127 and the call runs. A missing Python script run as `python x.py` exits 2, which blocks. Exit codes measured, Claude Code effect inferred | `runs/agent-harness_p02_missing_script_exit.txt` | 4.4 |
| 5 | Seatbelt adds about 6.5 to 7.5 ms for `true` and 21 to 24 ms for `python3` | With uv Python 3.12.14, `deny default` adds 6.01 ms for `true` and 6.05 ms for `python -c pass`. The old `python3` rows ran another interpreter. Why it paid more is not checked | `runs/agent-harness_p03_cold_start.txt`, Apple M4 Pro, N=40 | 4.11 |
| 6 | The whole-disk read default holds for agent CLI sandboxes in general | Verified for Claude Code and sandbox-runtime only. Codex not checked | `sandbox/cc_sandboxing.md` line 496, `srt_readme.md:119-122`. Phase 3 generate report, "Things I could NOT verify" item 2 | 4.10 |
| 7 | `failIfUnavailable` refuses to run commands | It blocks Claude Code from starting | `sandbox/cc_sandboxing.md`, the `failIfUnavailable` note. Phase 3 section 3.3 | 4.10 |
| 8 | CVE-2026-54316 was a sandbox proxy allowlist | It was the WebFetch pre-approved host list, a harness tool | `sandbox/cc_adv.json`, advisory title | 4.8, section 3 |
| 9 | Sub-agent limits have an owner in Module 7 or Module 9 | Module 9 section 6.2 owns width and depth in general. The Claude Code depth and concurrency values are taught nowhere yet. Open commitment to Module 9 | `orchestration-durable-phase-06-coordination.md` section 6.2. `m07_refresh/cc_sub-agents.md` | 4.15 |
| 10 | Linux programs that ignore `HTTP_PROXY` may bypass the proxy | They fail to connect. Already fixed in the 2026-09-23 refresh, re-checked | `sandbox/srt_readme.md:891` | 4.8, unchanged |
| 11 | The OpenAI invalid-JSON error text always reaches the model | It reaches the model only with `OPENAI_AGENTS_DONT_LOG_TOOL_DATA=0`. With default logging the model gets the generic text | `runs/agent-harness_p01_tool_errors.txt`, `agents/tool.py:1940-1950` in openai-agents 0.22.3 | Phase 1 section 1.2 |
| 12 | A failing tool becomes a tool result in every SDK | Pydantic AI 2.48.0 ends the run on a plain exception after 1 model call. `ModelRetry` gives `retries + 1` model calls | `runs/agent-harness_p01_tool_errors.txt` | Phase 1 section 1.2 |
| 13 | LangGraph uses two supersteps per tool round, inferred | Measured: `2k + 1` supersteps. At an even limit that is too small, the run ends normally with "Sorry, need more steps to process this request." and no exception | `runs/agent-harness_p01_langgraph_sweep.txt`, `chat_agent_executor.py:631, 689` in langgraph-prebuilt 1.1.0 | 4.13, Phase 1 section 1.3 |
| 14 | A budget cap bounds the session | Pydantic AI `cost_limit` stops nothing when the model has no price data | `runs/agent-harness_p01_cap_compare.txt`, `--cost-limit-demo` | 4.14, Phase 1 section 1.4 |
| 15 | The sandbox stops H3 in the full stack | In the drill, the hook stops H3 first, because it blocks any call that names `outside/`. The sandbox stops H3 when the hook is removed | `runs/agent-harness_p05_stack_drill.txt` | Contract section 3, Phase 5 section 5.3 |
| 16 | CVE-2026-55607 and CVE-2025-54794 missing from the sources | Both are GitHub advisories on Claude Code, read by the Phase 4 writers | `sandbox/advisories_parsed.txt` lines 30 and the 2026-06-25 row | Section 3 table |

### Anchor re-check

72 anchor strings across 4.1 to 4.17 were grepped in the saved source or run files on 2026-09-23 with `grep -c -F`. All 72 were found. Four strings were shortened because the saved text breaks the line inside the quote: the OpenAI turn definition, the gVisor hardware quote, the Codex Landlock note and the Firecracker pool sentence. Count per concept: 4.1: 3, 4.2: 4, 4.3: 3, 4.4: 6, 4.5: 8, 4.6: 3, 4.7: 4, 4.8: 3, 4.9: 3, 4.10: 3, 4.11: 4, 4.12: 5, 4.13: 9, 4.14: 4, 4.15: 5, 4.16: 1, 4.17: 4. Files: `scratchpad/m07_refresh/anchors.tsv`, `anchors_result.txt` and `anchors_summary.txt`. Numbers printed only to a terminal are listed in section 6 as "output not saved, re-run before quoting".

Summary: section 4 now holds 17 claims with conditions. Sandboxes moved in from Module 6. Twelve corrections to the old text and two to today's reports are logged above.

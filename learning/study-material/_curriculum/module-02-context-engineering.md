# Module 02 — Context engineering and long-horizon reliability

Research date: 2026-09-17. Status: research dossier, not course material.

## 1. What this module is for

This module teaches the learner to measure and control what goes into the context window of a long-running agent. Long-context models still lose accuracy as input grows, and the loss depends on the task. Agents now run hundreds of tool calls, so every provider ships compaction, context editing, and memory features. These features can make results worse. A 2026 AppWorld study measured more blocked and repeated actions right after compaction. Without measurement, an engineer picks thresholds from blog posts, breaks the prompt cache, and ships silent quality loss.

## 2. Scope

### In scope

- Measuring context rot on your own task. Hold the task fixed and change only the history size.
- How long-context benchmarks score their results, and why their numbers disagree.
- Cache hit rate across an agent trajectory. Append-only context, deterministic serialization, and tool masking.
- Tool-result pruning. This covers observation masking, provider context editing, and its cost in cache writes.
- Validating a compaction event against the trajectory. The course uses the replay design from TRACE and the next-k check from Slipstream.
- Provider features at current versions: Anthropic context editing, server compaction, on-demand compaction, and the memory tool. Also OpenAI Responses compaction, Codex auto-compact, Claude Code auto-compact, and Google ADK compaction.
- Sub-agent isolation, and where the evidence for it is weak.
- Ideas from long-horizon benchmarks for a small offline eval of your own.

### Out of scope, and where it lives instead

| Topic | Where it lives |
|---|---|
| Retrieval quality, chunking, re-ranking | Knowledge-layer modules on retrieval |
| Long-term cross-session memory design | Agents-layer module on memory |
| Multi-agent orchestration patterns in depth | Agents-layer module on orchestration |
| Eval statistics and judge calibration | Modules 11 and 12, evals |
| Prompt-injection risk in memory files | Module 16, security. Phase 4 names the path-traversal rule only. |

### Overlap with earlier modules

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| Budget zones with caps | Module 1, 2.6 | Nothing new. Link only. |
| Threshold trigger, backstop on the 400 | Module 1, 2.6 | Current provider defaults, and the cookbook threshold myth |
| Limits of compaction, ConstraintRot, Slipstream headline | Module 1, 2.6 | The validation method itself, TRACE numbers, and a replay lab |
| Chroma study and Lost in the Middle | Module 1, 2.6 | The benchmark instruments, their scorers, and a lab that measures rot |
| Implicit prefix caching, the timestamp mistake | Module 1, 3.2 and Phase 0 Story 1 | Cache hit rate across a whole trajectory, tool-set changes, and cache cost of pruning |
| cache_control and break-even | Module 1, 3.3 | Break-even for `clear_at_least` |
| Cache-hit floor as an alert | Module 1, 3.5 | Hit rate per trajectory step |
| Run records | Module 1, 5.5 | Compaction events as records with a before and after score |

## 3. What changed recently

| Change | Date | Source | Why it matters |
|---|---|---|---|
| Chroma publishes "Context Rot" | 2025-07-14 | Chroma research page | It names the effect. It publishes charts, not a percentage table. |
| Anthropic launches context editing and the memory tool | 2025-09-29 | claude.com/blog/context-management | It gives the first provider defaults for tool-result clearing. |
| Cookbook "Automatic context compaction" gives 5k-20k and 50k-100k bands | 2025-11-24 | Claude Cookbook, Pedram Navid | This is the origin of the widely repeated threshold claim. |
| OpenAI adds `responses/compact` to openai-python 2.9.0 | 2025-12-04 | openai-python CHANGELOG | It adds stateless compaction on the server. |
| OpenAI adds `context_management` to openai-python 2.18.0 | 2026-02-09 | openai-python CHANGELOG | Compaction can now run inside a Responses request. |
| Claude Code postmortem on a thinking-clearing bug | 2026-04-23 | Anthropic engineering | It is a first-party incident caused by context editing. |
| Anthropic post "Prompt caching is everything" | 2026-04-30 | claude.com blog, Thariq Shihipar | Claude Code declares incidents on a low cache hit rate. |
| Slipstream, trajectory-grounded compaction validation | 2026-05-09 | arXiv 2605.08580 | It is a method to check a summary against the next steps. |
| Classifier Context Rot | 2026-05-12 | arXiv 2605.12366 | It measures rot on real Claude Code transcripts with padded history. |
| Opus 4.8 system card splits GraphWalks 256K and 1M results | 2026-05-28 | Anthropic system card | Old "1M" scores mixed two subsets. Old and new cards disagree. |
| WeaveBench and OSWorld 2.0 released | 2026-06-08, 2026-06-28 | arXiv 2606.09426, 2606.29537 | Both are long-horizon computer-use benchmarks. |
| TRACE study on execution instability after compression | 2026-08-06 | arXiv 2608.06503 | It gives the blocked-action and repeated-action numbers. |
| `anthropic` Python SDK 1.0.0 removes `compaction_control` | 2026-08-20 | SDK MIGRATION.md at v1.6.0 | The cookbook code no longer matches the SDK. |
| Terminal-Bench 4.0 | 2026-08-28 | tbench.ai news | Flat 8-hour agent timeout and semantic versioning. |
| "How Fast Do Agents Rot?" | 2026-08-31 | arXiv 2609.01660 | Success falls with step count. |
| Anthropic on-demand compaction beta `compact-2026-09-04` | 2026-09 | Anthropic compaction docs | Compaction can now run as its own request. |

## 4. Core concepts, with verified facts

### 4.1 Context rot is task-dependent, and each benchmark measures a different part of it

Context rot is the loss of accuracy as input length grows, with the task held fixed. Benchmarks disagree on how large the loss is. The reason is that they use different tasks, scorers, and definitions of "effective length". The lesson for the course is to measure on your own task.

- Chroma tested 18 models from Anthropic, OpenAI, Google, and Qwen. Its LongMemEval test compared about 300-token focused prompts with about 113k-token full prompts over 306 prompts. The scorer was a GPT-4.1 judge aligned to human labels above 0.99. Chroma, "Context Rot", 2025. **Verified** by the research agent from the page body.
- The Chroma page has no tables and 49 images. It states no accuracy percentage at any length. The string "30%" appears 0 times. Chroma page. **Verified**: grep on the fetched HTML on 2026-09-17 returned 0.
- The widely quoted "30% accuracy drop" comes from LongMemEval. The abstract says "a 30% accuracy drop". In Figure 3b, GPT-4o falls from 0.870 in the Oracle setting to 0.606 with about 115k tokens of history. That is a 30.3% drop. The scorer is a gpt-4o-2024-08-06 judge. Wu et al., ICLR 2025. **Verified**: I grepped the abstract phrase myself. The agent read the figure values.
- NoLiMa defines effective length as the longest length that scores above 85% of a short-context base score. GPT-4o has a base of 99.3 and scores 69.7 at 32K. Its effective length is 8K against a claimed 128K. The scorer checks that the answer contains the right character name. Modarressi et al., ICML 2025, Table 3. **Verified.**
- NoLiMa §4.4 says 11 of 13 models score half or less of their base at 32K. When the question and needle share words, models stay strong. NoLiMa, Table 6. **Verified.**
- RULER sets its threshold at Llama2-7B's 4K score, 85.6%. Across 13 synthetic tasks, GPT-4 scores 96.6 at 4K and 81.2 at 128K. Gemini-1.5-Pro scores 94.4 at 128K. RULER, NVIDIA, COLM 2024, Table 3. **Verified.**
- HELMET found that no synthetic task has an average rank correlation above 0.8 with downstream tasks. The test used 35 instruction-tuned models at 128K. Yen et al., ICLR 2025, §3.1. **Verified.** So a needle test score does not predict your task score.
- Length alone hurts even when retrieval is perfect. With 30K whitespace tokens, Llama-3.1-8B still recites the evidence for 970 of 1000 MMLU items, but its accuracy falls. Du et al., Findings of EMNLP 2025, §1 and §4.1. **Verified.** The case where it fails: GPT-4o and Gemini-2.0 score 100 on VarSum at every length.
- Classifier Context Rot, by Martin and Roger of Anthropic, padded real agent transcripts. Opus 4.6 with thinking had 99.7% needle recall at 100K tokens of history and 69% at 800K. arXiv 2605.12366, §1. **Verified.**
- Model cards change their long-context methods. The Opus 4.6 card reports GraphWalks BFS "1M" as 38.7. The Opus 4.8 card reports Opus 4.6 at 16.3 and says it now separates the 256K and 1M subsets. Anthropic system cards. **Verified** values. The column mapping in the 4.6 card is **inferred**, because the PDF text order is unclear.
- No published study uses a 10k, 50k, and 200k grid of accumulated agent history. **Verified absence** within the sources the agent searched. The closest designs are LongMemEval, Chroma, and Classifier Context Rot.

### 4.2 Step count and length are separate causes

A long task can fail because each step has some chance of error. It can also fail because the context got longer. The course must separate these two causes in its lab design.

- Mittal reports a logit slope per doubling of horizon of −0.44 for full history and −0.69 for compressed history. The padded single-turn regime has −0.40. The paper gives p=3×10⁻⁶ next to the compressed slope and p=0.51 next to the padded slope. Which comparison each p-value tests is not checked. A simulator scores success exactly. arXiv 2609.01660, §4.5. **Verified** from the PDF text. Figures were not read.

### 4.3 Cache hit rate is a trajectory metric

An agent resends its whole history on each step. So a prefix break on step 3 costs full price on every later step. Module 1 covered the single-request case. This module measures the hit rate per step and per event, such as pruning or a tool-set change.

- Manus calls "the KV-cache hit rate" "the single most important metric for a production-stage AI agent". The same post gives an input-to-output ratio of about 100:1, with no measurement window. Yichao Ji, Manus blog, 2025-07-18. **Verified** quote. The ratio is a vendor claim with no conditions.
- Manus advises append-only context, deterministic JSON key order, and masking tool logits instead of removing tools. Manus blog. **Verified.**
- Anthropic and OpenAI caching docs both say that changing tool definitions or their order breaks the cached prefix. **Verified** by the research agent.
- Claude Code runs alerts on prompt cache hit rate and declares SEVs when it is too low. The post names three real breaks: a timestamp in the system prompt, non-deterministic tool order, and changed tool parameters. It gives no hit-rate percentages. Thariq Shihipar, claude.com blog, 2026-04-30. **Verified.**
- No primary source publishes a measured hit rate before and after a prefix break. **Verified absence** across Anthropic, Manus, OpenAI, and Google pages the agent read. The course must measure it in a simulator.

### 4.4 Tool-result pruning is cheap and often as good as summarization

Tool results are usually the largest part of an agent's context. Old results can be replaced with a placeholder. The measured evidence says this often matches summarization at lower cost, in the software-engineering domain.

- JetBrains Research compared raw history, observation masking with M=10, and LLM summarization on SWE-bench Verified with SWE-agent. For Qwen3-Coder 480B, the solve rates were 53.4, 54.8, and 53.8. Mean costs were $1.29, $0.61, and $0.64. Lindenbauer et al., NeurIPS 2025 DL4Code workshop, Table 1. **Verified.**
- The same table shows a case where it fails. Gemini 2.5 Flash with thinking scored 40.4 raw, 36.4 masked, and 31.4 summarized. Both drops are significant. **Verified.**
- CoACT compresses each new observation and accepts it if it leads to the same next action. Average pass@1 rose 2.0 points and tokens fell 33.0%. Pass@1 fell for DeepSeek-v4-Pro, from 76.5 to 75.0. arXiv 2607.02911, Table I. **Verified.**
- Anthropic `clear_tool_uses_20250919` defaults: `trigger` 100,000 input tokens, `keep` 3 tool uses, `clear_at_least` none, `exclude_tools` none, `clear_tool_inputs` false. Beta header `context-management-2025-06-27`. Anthropic context-editing docs. **Verified** on 2026-09-17.
- The docs say tool result clearing invalidates cached prompt prefixes. They advise `clear_at_least` so each clearing is worth the cache write. Anthropic context-editing docs, line 71 of the `.md` page. **Verified**: I grepped this line myself.

### 4.5 Compaction thresholds: what the sources say

Compaction replaces old turns with a summary. A threshold decides when it runs. No provider publishes an eval that justifies a given threshold. The course should teach the learner to choose one by measurement.

- The "5k-20k" and "50k-100k" bands come from the Claude Cookbook recipe "Automatic context compaction", published 2025-11-24 by Pedram Navid. The bands are "Low thresholds (5k-20k)", "Medium thresholds (50k-100k)", "High thresholds (100k-150k)", and "Default (100k)". **Verified**: I grepped the first two strings and the date myself.
- The recipe frames the bands by task structure, not as "simple" versus "complex". The research found no 2026 write-up with the "simple versus complex" wording. **Verified** for the cookbook wording. The 2026 write-up is **not checked**, because it was not found.
- The bands apply to the client-side `compaction_control` argument of the `anthropic` Python SDK tool runner. The SDK removed this argument in 1.0. MIGRATION.md at tag v1.6.0 says it "has been removed in favour of server-side compaction". **Verified**: I read lines 282 to 308 myself.
- Server compaction `compact_20260112` defaults to a trigger of 150,000 input tokens. The docs say "`value` must be at least 50,000 tokens". So the 5k-20k band cannot be used with server compaction. Anthropic compaction docs, line 269. **Verified**: I grepped this line myself.
- Claude Code compacts at about 967K tokens on native 1M-window models, and at 200K on 200K deployments. `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` can only lower the threshold. Claude Code docs, `model-config.md` and `env-vars.md`. **Verified** from docs. Claude Code source is not public.
- Codex computes its auto-compact limit as the minimum of the configured limit and 90% of the context window. A test gives a 360,000 limit for a 400K window. `codex-rs/protocol/src/openai_models.rs` lines 515 to 526 at `rust-v0.154.0`. **Verified** from source, not run.
- OpenAI `compact_threshold` has no documented default or minimum in the guide or in openai-python 3.14.1. **Verified absence.**
- `truncation` in the Responses API defaults to `disabled`, which returns a 400 on overflow. `auto` drops items from the start. openai-python 3.14.1, `response_create_params.py` lines 319 to 327. **Verified** from source.
- Self-Compacting Language Model Agents argues against fixed thresholds. It lets the model choose the moment. arXiv 2606.23525. **Verified** from the abstract only.

### 4.6 Compaction can make the next steps worse, and you can measure it

A summary can drop facts the next step needs. The agent then repeats work, calls tools that fail, or does not stop. TRACE measures this by replaying from the compaction point with and without the summary.

- TRACE defines an action as blocked when it triggers AppWorld's execution-error contract. An action is repeated when its canonical tool-call signature matches an earlier one. arXiv 2608.06503, verifier section. **Verified**: I grepped the definitions myself.
- Method: restore the environment at a compaction boundary. Run PRE with the full history and POST with the summary. The score is the difference in blocked or repeated actions over K steps. **Verified** by the research agent.
- The study covers 590 boundaries and 4,640 rollouts. At the first action, POST produced 0.108 more blocked or error actions than PRE. The paper says "the effect remains positive throughout the continuation". Refetch or replay starts at 0.031 and rises at the second action. TRACE, Figure 4. **Verified**: I grepped the sentence myself.
- AppWorld accuracy with MiniMax-M3 was 85.7 with no compression and 63.7 with FIFO. TRACE, Table 1. **Verified**: I checked this row. The verifier may miss silent state corruption, as the paper says.
- The paper also probed the final decision point with a 2K budget. With a summary, the agent stopped correctly in 44.6% of samples. It stopped in 77.2% with FIFO truncation and 66.6% with full history. TRACE, Figure 2. **Verified**: I read the passage myself.
- Slipstream compares a candidate summary with the next k steps the agent took while compaction ran. It checks facts at statement level and intent at plan level. The judge accepts at 7 out of 10 or higher. On SWE-bench Verified, 96% of first errors appear by k=6. About 12% appear later and cannot be caught. arXiv 2605.08580, §4 and Figure 3b. **Verified** by the research agent.
- ACON and TRACE disagree. ACON with gpt-4.1 matched the no-compression accuracy on AppWorld. In TRACE with MiniMax-M3 and a 4K budget, ACON-UT scored 62.5 against 85.7. The model, budget, and implementation differ. arXiv 2510.00615 and TRACE Table 1. **Verified** values. The cause of the gap is **inferred**.

### 4.7 Isolation and external memory

A sub-agent works in its own context and returns a short result. External memory moves facts out of the window into files. Both reduce context size. The evidence that isolation alone helps is weak.

- Anthropic reports that a multi-agent system beat single-agent Opus 4 by 90.2% on an internal research eval. The eval size is not given. Multi-agent systems used about 15 times more tokens than chats. Anthropic engineering, 2025-06-13. **Verified** quotes. The eval conditions are not published.
- The same post says token usage alone explains 80% of the variance on BrowseComp. **Verified** quote. So the gain is mixed with extra tokens.
- Cognition advises "a single-threaded linear agent" for coding with parallel writers. Walden Yan, 2025-06-12. In April 2026 Cognition said the original point "still hold[s] today for parallel-writer swarms". It now uses review agents that share no context with the coder. Cognition blog, 2026-04-22. **Verified.**
- Context-Folding with Seed-OSS-36B scored 0.620 on BrowseComp-Plus against 0.478 for ReAct with a 327K context. The result includes RL training. arXiv 2510.11967, Table 1. **Verified** from PDF text.
- No paper found tests isolation alone against a single agent at an equal token budget. **Verified absence** within the agent's search.
- Anthropic memory tool: type `memory_20250818`, commands `view`, `create`, `str_replace`, `insert`, `delete`, `rename`. Storage is on the client. The page shows no beta header. Anthropic memory-tool docs. **Verified.**
- The memory-tool docs warn about path traversal, for example `/memories/../../secrets.env`. They require canonical path checks and rejection of `../` and `%2e%2e%2f`. **Verified.**
- Anthropic reports a 39% gain from memory plus context editing on an internal agentic-search eval. Context editing alone gave 29%. Token use fell 84% in a 100-turn web search eval. The page does not state the model, baseline, or task count. claude.com blog, 2025-09-29. **Verified** quote. It is a vendor claim with partial conditions.

### 4.8 Long-horizon benchmarks: ideas to borrow

These benchmarks are too large to run on a laptop. The course takes their design ideas, not their scores.

- Terminal-Bench is at version 4.0, released 2026-08-28. It has a flat 8-hour agent timeout per task and removed 8 tasks from 3.0. The blog does not state a task count. tbench.ai news. **Verified.** A count of 66 is **inferred** from 74 minus 8.
- OSWorld 2.0 exists. It has 108 tasks with a median human time of about 1.6 hours and about 27 checkpoints per task. Opus 4.8 scored 20.6% binary and 54.8% partial at 500 steps. arXiv 2606.29537, Table 3. **Verified.**
- WeaveBench exists. It has 114 tasks that mix GUI and CLI work. A trajectory-aware judge corrected GPT-5.5 "from 53.5% to an audited 33.3%". Opus 4.7 scored 41.2% in Claude Code and 13.2% in Codex CLI. arXiv 2606.09426, Introduction and Table 3. **Verified.**
- METR fits success against the time a human needs for each task. Its doubling time since 2023 is 128.7 days. METR says measurements above 16 hours are unreliable. METR benchmark_results_1_1.yaml. **Verified.**
- Tencent's position paper defines a horizon residual: the log-ratio between success predicted from short stages and actual full-task success. arXiv 2607.27283. **Verified** definition only.
- Vending-Bench v1 found "no clear correlation between failures and the point at which the model's context window becomes full". Backlund and Petersson, arXiv 2502.15840. **Verified.** Do not present its failures as context loss.

## 5. Proposed phase outline

| Phase | Title | What it teaches | Labs it needs | Runs where, costs what |
|---|---|---|---|---|
| 1 | Measuring context rot on your own task | Benchmark instruments and scorers, effective length, the 30% myth, length versus step count, a fixed-task history-size sweep | L1, L2, L3, L4 | Laptop, offline with a fake model. Optional live sweep: about $1 to $40, depending on the model. See the L3 cost note. |
| 2 | Stable prefixes and pruning | Trajectory cache hit rate, append-only context, deterministic serialization, tool masking, observation masking, context editing and its cache cost | L5, L6, L7, L8 | Laptop, offline. Optional live check under $2. |
| 3 | Compaction you can check | Provider features at current versions, the threshold myth, PRE and POST replay, next-k validation, pinned constraints, the terminal-decision probe | L9, L10, L11, L12 | Laptop, offline simulator. Optional live replay about $5 to $20. |
| 4 | Isolation, memory, and a long-horizon eval | Sub-agent evidence and disagreement, memory tool safety, file-based state, borrowing benchmark ideas, horizon residual | L13, L14, L15 | Laptop, offline. No GPU. |

Module 1 section 2.6 already teaches the budget, the trigger, the backstop, and the limits of compaction. What remains new is measurement, validation, pruning, and isolation. That is a medium-small area. Four phases fit, one per new skill. Phase 1 is the largest, because the rest of the module uses its sweep harness. Provider features do not need their own phase. They fit inside Phases 2 and 3 as configuration tables.

## 6. Lab ideas

All labs run offline first, with a seeded fake model or a simulator. Live variants are optional and labelled. Each self-test checks a known answer.

| Lab | What the script does and prints | Break-it variant | Self-test |
|---|---|---|---|
| L1 Scorer swap | Scores 200 fixed answers with exact match, contains-match as in NoLiMa, and a difflib ratio as in MRCR. Prints accuracy per scorer. | Wrap correct names in extra words | Exact match equals the count on a 20-item hand-labelled fixture |
| L2 Effective length | Computes effective length with the NoLiMa rule and the RULER rule. Prints both. | Use only the 1K score as the base | The NoLiMa GPT-4o row returns 8K |
| L3 History-size sweep | Places one answer in synthetic support-chat history of 10k, 50k, and 200k tokens. Runs 50 trials per size. Prints accuracy with a 95% interval. | Move the answer to the middle | A fake model's configured decay curve is recovered within the interval |
| L4 Steps versus length | Runs H-step tasks under full, compressed, and padded regimes, as in Mittal. Prints a logistic slope per regime. | The compressor drops one self-written fact | With per-step success p, success is close to p to the power H |
| L5 Trajectory cache meter | Replays a 40-step trace through a prefix-cache simulator. Prints hit rate per step and cost from Module 1 `prices.yaml`. | Timestamp in system prompt, shuffled tools, unsorted JSON keys | A clean trace hits on every step after the first |
| L6 Mask, do not remove | Disables a tool mid-run by removal and by an allowed-tools mask. Prints hit rate and cost for both. | Remove two tools at different steps | Removal breaks the cache from the change step onward |
| L7 Masking versus summary | Runs a simulated coding agent with raw history, masking at M=10, and summaries. Prints tokens, cost, turns, success. | One old observation is needed at step 30 | Token counts match a fixture |
| L8 `clear_at_least` break-even | Computes when one clearing event pays for its cache write. Prints cleared tokens against remaining steps. | Use 1-hour cache write prices | One hand-computed row matches |
| L9 PRE and POST replay | Restores simulator state at a compaction boundary. Runs 5 steps with full history and with a summary. Prints blocked and repeated actions and their difference, as in TRACE. | The summary drops an item ID | A lossless summary gives a difference of zero |
| L10 Next-k check | Extracts facts used in the next k logged steps and looks for each in the summary. Prints missing facts and accept or reject, as in Slipstream. | A judge model replaces string matching | A fixture with one missing ID is rejected |
| L11 Stop probe | Renders a finished task as full history, FIFO, and summary. Samples 10 next actions each. Prints the correct-stop rate, as in TRACE Figure 2. | Add an unneeded open item to the summary | Configured stop rates come back within tolerance |
| L12 Threshold sweep | Runs L9 with thresholds of 5k, 20k, 50k, 100k, 150k. Prints cost, compactions, blocked actions, and whether each provider accepts the value. | Set a trigger below 50,000 for server compaction | The validity column matches the documented minimum |
| L13 Isolation at equal budget | Runs one agent and a lead with sub-agents at the same total tokens. Prints success and tokens. | Two sub-agents write conflicting choices to one file | Both runs respect the budget |
| L14 Memory handler safety | Implements memory-tool commands on local files. Prints pass or fail for attack paths such as `../`, `..\`, `%2e%2e%2f`, and deleting the root. | Remove the canonical path check | Fails until every listed path is rejected |
| L15 Horizon residual | Runs short stages alone, then the full task. Prints the log-ratio of predicted to actual success. | Add a fact that one stage needs from another | No cross-stage dependency gives a residual near zero |

Costs of live variants, all optional:

- L3 live: 150 calls with a mean of about 87k input tokens is about 13 million tokens. That is about $1.30 at $0.10 per million, or about $40 at $3 per million. The script must print this estimate before it runs.
- L8 live: one request with `clear_tool_uses_20250919`, reading `applied_edits`. Under $1.
- L9 live: a replay with a real model on 20 boundaries. About $5 to $20, depending on the model. This estimate is inferred, not measured.
- No lab needs a GPU.

## 7. Failure stories and case studies

1. **Claude Code thinking-clearing bug, Anthropic, reported 2026-04-23.** On March 26, Anthropic shipped a change to clear older thinking. It applied to sessions idle for more than an hour. It used `clear_thinking_20251015` with `keep:1`. The postmortem says: "Instead of clearing thinking history once, it cleared it on every turn for the rest of the session." Claude seemed "forgetful and repetitive". The dropped blocks also caused cache misses. The bug affected Sonnet 4.6 and Opus 4.6. It was fixed on April 10 in v2.1.101. Finding the cause took over a week. **Verified**: I grepped the quoted sentence myself.
2. **Claude Code cache breaks, Anthropic, 2026-04-30.** Three changes broke the prompt order. They were a detailed timestamp, random tool order, and changed tool parameters. The post gives no measured cost. **Verified.**
3. **Gemini Plays Pokémon, Google DeepMind, Gemini 2.5 report.** Beyond 100k tokens, the agent tended to repeat actions. The report calls this "anecdotal". It also describes "context poisoning": the agent chased an item that does not exist in the game for many hours. Run 1 took 813 hours. Run 2 took 406.5 hours with a fixed harness. **Verified** by the research agent, pp. 16 to 18 and 69 to 70.
4. **Context anxiety, Cognition and Anthropic, 2025 and 2026.** Cognition saw Sonnet 4.5 take shortcuts. This happened when the model believed its window was nearly full. The workaround was to enable 1M tokens and cap use at 200k. Anthropic later wrote that Opus 4.5 "largely removed that behavior". No numbers are given. **Verified** quotes.
5. **Compaction is not enough, Anthropic, 2025-11-26.** The agent ran in a loop across context windows. A later agent saw progress and declared the job done. The fix was a progress file, git commits, and one feature at a time. No numbers are given. **Verified.**
6. **Vending-Bench, Andon Labs.** Agents failed in long runs, but the paper found no link to a full context window. Use this as a counter-example. **Verified.**

## 8. Primary sources

All entries were fetched on 2026-09-17 and returned HTTP 200, unless the entry says otherwise. "Me" marks pages I fetched again for this file. The others were fetched by a research agent.

### Context rot and long-context measurement

- **Context Rot, Chroma, 2025** — https://research.trychroma.com/context-rot, 200, me. Focus on: the LongMemEval section and the judge description. Why: it names the effect, and it has no percentage table.
- **LongMemEval, Wu et al., ICLR 2025** — https://arxiv.org/html/2410.10813, 200, me. Focus on: Figure 3b and §3. Why: the true source of the "30%" figure.
- **NoLiMa, Modarressi et al., ICML 2025** — https://arxiv.org/html/2502.05167, 200. Focus on: §4.1 to §4.4 and Tables 3 and 6. Why: effective length against a per-model base.
- **RULER, NVIDIA, COLM 2024** — https://arxiv.org/html/2404.06654, 200. Focus on: §4, Table 3, §8. Why: the fixed-threshold definition.
- **HELMET, Princeton, ICLR 2025** — https://arxiv.org/html/2410.02694, 200. Focus on: §3.1 and Figure 3. Why: needle scores do not predict task scores.
- **Michelangelo, Google DeepMind, 2024** — https://arxiv.org/html/2409.12640, 200. Focus on: §2. Why: it introduced MRCR.
- **LongBench v2, Tsinghua and Zhipu.AI, ACL 2025** — https://arxiv.org/html/2412.15204, 200. Focus on: the Table 2 footnote. Why: an example where length is not isolated.
- **Context Length Alone Hurts LLM Performance Despite Perfect Retrieval, Du et al., Findings of EMNLP 2025** — https://arxiv.org/html/2510.05381, 200. Focus on: §4.1 and Tables 2 and 3. Why: it separates length from retrieval.
- **Classifier Context Rot, Martin and Roger, Anthropic, 2026** — https://arxiv.org/html/2605.12366, 200. Focus on: §3.4, §3.5, Figure 4a. Why: rot on real agent transcripts.
- **How Fast Do Agents Rot?, Mittal, 2026** — https://arxiv.org/abs/2609.01660, 200, me. The HTML version returned 404. Focus on: §3.2 and §4.5. Why: step count against length.
- **Benchmarking the Residual, Tencent, 2026** — https://arxiv.org/html/2607.27283, 200. Focus on: the horizon residual. Why: the design for L15.
- **OpenAI MRCR dataset, OpenAI** — https://huggingface.co/datasets/openai/mrcr, 200. Focus on: the scorer and the 2025-12-05 fix note.
- **Claude Opus 4.8 System Card, Anthropic, 2026** — https://www-cdn.anthropic.com/0b4915911bb0d19eca5b5ee635c80fef830a37ea/Claude%20Opus%204.8%20System%20Card.pdf, 200. Focus on: Table 8.9.A. Why: scores change when the subset split changes.

### Compaction behaviour and validation

- **TRACE, Min et al., University of Virginia and Nokia, 2026** — https://arxiv.org/html/2608.06503v1, 200, me. Focus on: the verifier definitions, Figures 2 and 4, Table 1. Why: blocked and repeated actions after compaction.
- **Slipstream, Chen et al., Princeton, 2026** — https://arxiv.org/abs/2605.08580, 200, me. Focus on: §4 and Figure 3b. Why: the next-k validation method.
- **CoACT, Tsinghua, 2026** — https://arxiv.org/abs/2607.02911, 200. Focus on: Eq. 13 and Table I. Why: next-action preservation as a check.
- **ACON, KAIST and Microsoft** — https://arxiv.org/abs/2510.00615, 200. Focus on: §4.2 and Table 4. Why: one side of the disagreement with TRACE.
- **Agentic Context Engineering, Zhang et al., 2025** — https://arxiv.org/abs/2510.04618, 200. Focus on: §2 and Figure 2. Why: a measured context collapse.
- **Governance Decay, Shiyang Chen, 2026** — https://arxiv.org/abs/2606.22528, 200, me. Focus on: Figure 3. Why: summary budget against constraint survival.
- **The Complexity Trap, JetBrains Research, 2025** — https://arxiv.org/abs/2508.21433, 200. Focus on: Table 1 and §6. Why: masking against summaries, with costs.
- **Self-Compacting Language Model Agents, Li et al., 2026** — https://arxiv.org/abs/2606.23525, 200, me. Focus on: the rubric. Why: the case against fixed thresholds.
- **Context-Folding, ByteDance Seed and others, 2025** — https://arxiv.org/abs/2510.11967, 200. HTML returned 404. Focus on: Table 1. Why: isolation with RL.

### Provider documentation and source

- **Context editing, Anthropic** — https://platform.claude.com/docs/en/build-with-claude/context-editing, 200, me. Focus on: the option table and the caching notes.
- **Compaction, Anthropic** — https://platform.claude.com/docs/en/build-with-claude/compaction, 200, me. Focus on: the parameter table, `usage.iterations`, on-demand compaction.
- **Memory tool, Anthropic** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool, 200. Focus on: commands and path traversal.
- **anthropic-sdk-python MIGRATION.md at v1.6.0, Anthropic** — https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/v1.6.0/MIGRATION.md, 200, me. Focus on: lines 282 to 308.
- **Automatic context compaction, Claude Cookbook, Anthropic, 2025** — https://platform.claude.com/cookbook/tool-use-automatic-context-compaction, 200, me. Focus on: the threshold bands. Why: origin of the threshold claim.
- **Compaction guide, OpenAI** — https://developers.openai.com/api/docs/guides/compaction, 200. Focus on: `context_management` and `/responses/compact`.
- **Conversation state, OpenAI** — https://developers.openai.com/api/docs/guides/conversation-state, 200. Focus on: `previous_response_id` and storage.
- **Prompt caching, OpenAI** — https://developers.openai.com/api/docs/guides/prompt-caching, 200. Focus on: what breaks a prefix match.
- **openai/codex, OpenAI** — https://github.com/openai/codex, 200. Focus on: `codex-rs/protocol/src/openai_models.rs` lines 515 to 526 at `rust-v0.154.0`.
- **Claude Code docs, Anthropic** — https://code.claude.com/docs/en/model-config and https://code.claude.com/docs/en/env-vars, both 200. Focus on: compaction thresholds and overrides.
- **ADK context compaction, Google** — https://adk.dev/context/compaction/, 200. Focus on: the two strategies.

### Practitioner write-ups

- **Effective context engineering for AI agents, Anthropic, 2025** — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents, 200, me. Focus on: compaction, notes, sub-agents. It gives no thresholds.
- **How we built our multi-agent research system, Anthropic, 2025** — https://www.anthropic.com/engineering/multi-agent-research-system, 200. Focus on: the 90.2% and 80% claims.
- **Effective harnesses for long-running agents, Anthropic, 2025** — https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents, 200. Focus on: the two failure patterns.
- **An update on recent Claude Code quality reports, Anthropic, 2026** — https://www.anthropic.com/engineering/april-23-postmortem, 200, me. Focus on: the thinking-clearing bug.
- **Prompt caching is everything, Anthropic, 2026** — https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything, 200. Focus on: alerts and the three real breaks.
- **Context management launch, Anthropic, 2025** — https://claude.com/blog/context-management, 200. Focus on: the 39%, 29%, and 84% claims and their missing conditions.
- **Lessons from Building Manus, Manus, 2025** — https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus, 200. Focus on: cache hit rate, append-only context, tool masking.
- **Context Engineering for Agents, LangChain, 2025** — https://www.langchain.com/blog/context-engineering-for-agents, 200. Focus on: write, select, compress, isolate.
- **Don't Build Multi-Agents, Cognition, 2025** — https://cognition.com/blog/dont-build-multi-agents, 200. Focus on: the two principles.
- **Multi-Agents: What's Actually Working, Cognition, 2026** — https://cognition.com/blog/multi-agents-working, 200. Focus on: single-threaded writes.
- **Rebuilding Devin for Claude Sonnet 4.5, Cognition, 2025** — https://cognition.com/blog/devin-sonnet-4-5-lessons-and-challenges, 200. Focus on: context anxiety.
- **Context-aware multi-agent framework, Google, 2025** — https://developers.googleblog.com/en/architecting-efficient-context-aware-multi-agent-framework-for-production/, 200, me. Focus on: the working-context model and static instructions. It has no measured numbers.

### Long-horizon benchmarks

- **Terminal-Bench 4.0, Laude Institute and Stanford, 2026** — https://www.tbench.ai/news/terminal-bench-4-0, 200. Focus on: timeouts and versioning.
- **OSWorld 2.0, Yuan et al., 2026** — https://arxiv.org/abs/2606.29537, 200. Focus on: Table 3 and checkpoint scoring.
- **WeaveBench, Li et al., 2026** — https://arxiv.org/abs/2606.09426, 200. Focus on: the trajectory-aware judge.
- **METR time horizons, METR** — https://metr.org/time-horizons, 200. Data at https://metr.org/assets/benchmark_results_1_1.yaml, 200. Focus on: the 16-hour reliability note.
- **Vending-Bench, Andon Labs, 2025** — https://arxiv.org/abs/2502.15840, 200. Focus on: the finding of no link to a full context.
- **AppWorld, Trivedi et al., 2024** — https://arxiv.org/abs/2407.18901, 200. Focus on: state-based tests. The leaderboard page returned 404.

## 9. Tools and versions to pin

| Tool | Current version | Release date | Source | Notes on breaking changes |
|---|---|---|---|---|
| anthropic (PyPI) | 1.6.0 | 2026-09-15 | pypi.org/pypi/anthropic/json | 1.0.0 on 2026-08-20 moved to httpx2 and removed `compaction_control` |
| @anthropic-ai/sdk (npm) | 0.126.0 | 2026-09-15 | npm registry | `compactionControl` deprecated with a runtime warning |
| @anthropic-ai/claude-code | 2.1.274 | 2026-09-16 | npm registry, CHANGELOG | 2.1.273 fixed double counting that fired compaction at about half the window |
| claude-agent-sdk (PyPI) | 0.2.154 | 2026-09-17 | PyPI | `PreCompact` hook only. `PostCompact` is TypeScript only. |
| @anthropic-ai/claude-agent-sdk | 0.3.274 | 2026-09-16 | npm registry | Source not read |
| openai (PyPI) | 3.14.1 | 2026-09-15 | PyPI | 3.0.0 on 2026-08-12 made HTTPX2 the default |
| Codex CLI | rust-v0.154.0 | 2026-09-09 | GitHub releases | Release notes not read |
| google-adk | 2.9.1 | 2026-09-15 | PyPI | `EventsCompactionConfig` still experimental |
| google-genai | 2.24.0 | 2026-09-16 | PyPI | Not checked |
| langchain | 1.4.1 | 2026-09-16 | PyPI | `max_tokens_before_summary` and `messages_to_keep` renamed to `trigger` and `keep` |
| deepagents | 0.7.15 | not recorded | PyPI sdist | Summarization triggers at 85% of the model's max input, or 170,000 tokens without a profile |
| Anthropic betas | `context-management-2025-06-27`, `compact-2026-01-12`, `compact-2026-09-04` | not applicable | Anthropic docs | On-demand compaction cannot be combined with `context_management` |

## 10. Open questions and disagreements

1. **Does length or step count drive failure?** Du et al. and Chroma show that length alone lowers accuracy with the task fixed. Mittal finds that step count drives agent failure. His padded regime reports p=0.51, but the tested comparison is not checked. The conditions differ. Du used single-turn tasks with filler. Mittal used multi-step simulators, and his compressed regime also removed self-written facts. L3 and L4 let the learner test both.
2. **Does a compaction method match full context?** ACON with gpt-4.1 matched full context on AppWorld. TRACE with MiniMax-M3 at a 4K budget measured ACON-UT 23 points below full context. Model, budget, and implementation differ.
3. **Is summarization better than masking?** JetBrains found masking equal or better for several models on SWE-bench Verified. It found both worse than raw for Gemini 2.5 Flash with thinking. CoACT found per-observation compression helped two of three models. The domain is software engineering in both.
4. **Multi-agent or single agent?** Anthropic reports +90.2% on read-only research tasks, with about 15 times the tokens of chat. Cognition advises one writer for coding. Cognition's 2026 post accepts extra agents when writes stay in one thread. No paper isolates the effect at equal tokens.
5. **Do context resets still help?** Anthropic's March 2026 post used resets for Sonnet 4.5 and dropped them for Opus 4.5. The April 2026 Managed Agents post says resets had become "dead weight" on Opus 4.5. Cognition reported gains from its own compaction over model-written notes. All three are qualitative.
6. **Old claims about Claude Code.** A mid-2025 LangChain post says Claude Code compacts at 95% of the window. Current Claude Code docs say it compacts near the model limit, about 967K tokens on 1M models. Treat the 95% figure as outdated.

## 11. Things I could NOT verify

1. **The "2026 write-up" with "simple versus complex" thresholds.** Two agents searched and did not find it. Implicator.ai and Zylos Research pages did not contain it. A check: a web search for the exact phrase with the author's name, if the user has it.
2. **Whether the cookbook code fails on anthropic 1.6.0.** Inferred from MIGRATION.md. Not run. A check: run the notebook cell in a clean environment.
3. **OpenAI `compact_threshold` server default and minimum.** Not in docs or SDK source. A check: send a request without it and inspect the response, or read the API reference page body.
4. **Memory tool beta status on every platform.** The page shows no beta header. A check: read the beta-headers page or send one request without a header.
5. **Claude Code internal compaction logic.** The source is not public. All statements rest on docs and the CHANGELOG. "Microcompact" does not appear in any page fetched.
6. **Anthropic launch numbers of 39%, 29%, and 84%.** The model, baseline, task count, and variance are not published.
7. **Manus "100:1" ratio and "about 50 tool calls".** No measurement conditions are given.
8. **Measured cache hit rates before and after a prefix break.** No primary source publishes them.
9. **Terminal-Bench 4.0 task count.** Not stated. 66 is inferred.
10. **Page state and partial reads.** The Terminal-Bench and OSWorld-Verified leaderboards were rendered without a visibilityState check. Mittal's figures were not read, because only the PDF text was available. These papers were read as abstracts only: Self-Compacting Agents, MemAgent, ReSum, AgentFold, CompactionRL, AOrchestra, SWE-Bench Pro, τ²-bench, and LongProc. This file uses no numbers from their bodies.
11. **Missing long-context numbers.** Opus 4.7 MRCR values appear in figures only. Third-party regression claims were not verified. Fiction.LiveBench renders with JavaScript. The OpenAI GPT-4.1 announcement returned 403, so OpenAI's own MRCR numbers are not verified.
12. **Repo feasibility.** Offline and CPU use of RULER, NoLiMa, HELMET, and the Chroma repo is inferred from READMEs. None was run. The NoLiMa license allows non-commercial use only.
13. **Summarizer errors.** The fetch summarizer invented numbers for Context-Folding and SUPO. It credited them to models that are not in those papers. The research agent replaced them with raw PDF text. This file uses only numbers that the agents confirmed from raw text.
14. **Incidents without a primary source.** The July 2025 Replit database deletion has no primary postmortem. Lost instructions after Claude Code auto-compact appear only in user GitHub reports. Neither is used here.
15. **Google ADK in other languages.** Only the Python source at v2.9.1 was read.

## 12. Notes for the course generator

- **Do not repeat Module 1 section 2.6.** Link to it for budget zones, the trigger, the backstop, and the headline ConstraintRot and Slipstream numbers.
- **Correct Module 1 wording where this research is more precise.** Module 1 2.6 calls the AppWorld study "an August 2026 study". Name it: TRACE, arXiv 2608.06503.
- **Never credit "30%" to Chroma.** It is LongMemEval, Oracle versus about 115k tokens, GPT-4o, with a GPT-4o judge.
- **Never present the 5k-20k and 50k-100k bands as current Anthropic advice.** They come from a November 2025 cookbook recipe. The recipe uses an SDK argument that the Python SDK removed in 1.0. Server compaction rejects any trigger below 50,000.
- **Name the scorer next to every benchmark number.** L1 exists because scorer choice moves results.
- **Numbers that go stale fastest:** Claude Code thresholds and version, SDK versions, beta header names, Terminal-Bench version and leaderboard, OSWorld and WeaveBench scores, METR doubling time, model-card long-context scores.
- **Re-check before generating:** the Anthropic compaction page for new trigger types, the OpenAI compaction guide for a documented default, Codex `openai_models.rs` at the new tag, and the Claude Code `model-config` page.
- **Label vendor claims.** The Anthropic 39% and 84% figures, the Manus ratios, and the Cognition 12% figure have no published eval conditions.
- **Do not use Vending-Bench as a context-loss story.** Its own paper found no link to a full context.
- **Cost warning for L3.** Print the token estimate before any live call. A 200k-token sweep on a $3 per million model costs about $40 for 150 calls.
- **The fetch summarizer can invent numbers from PDFs.** Pull raw text with a PDF library before quoting any table value.
- **Summary:** measure rot on your own task, keep the prefix stable, prune before you summarize, and check every compaction against the steps that follow.

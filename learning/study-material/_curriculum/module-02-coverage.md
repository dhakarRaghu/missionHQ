# Module 2 — Context Engineering and Long-Horizon Reliability

Status: COMPLETE. Course folder: `study-material/context-engineering/`. Code: `study-material/context-engineering/code/`. This file was written on 2026-09-23.

This file lists what Module 2 teaches, section by section. Later modules link to it and do not teach the same thing again. Link in the form `Module 2, 3.2`.

## How this file was checked

- **Source of truth.** The four phase documents, `course.json` and `code/`. The old dossier, `_curriculum/module-02-context-engineering.md`, was read only to confirm which of its claims the course corrected.
- **Headings.** Copied from the phase documents with `grep -n '^#'`. Verified.
- **Lab numbers.** 66 lab commands were run again on 2026-09-23. The runs used this Mac, macOS on Apple silicon, uv 0.12.8 and Python 3.12. Each ran as `uv run --offline python ...` from `code/`. Every number marked "lab, re-run" matched the phase text. Verified.
- **Self-tests.** All 26 scripts passed in the same session. The counts are in "Shared code". Verified.
- **Paper and documentation numbers.** Copied from the phase text, which names the table, figure or page. The sources were not opened again for this file. They are marked "cited".
- **Code line references,** such as `find_vs_use.py:97`. Checked with `sed -n`. Verified.

The "Checked" column in each table uses three values:

- **lab, re-run**: the command was run on 2026-09-23 and printed this number.
- **cited**: the phase text states it and names its source. The source was not re-read here.
- **formula**: a definition or a hand calculation from the phase text.

## Documents

| Phase | File | Sections | Scripts |
|---|---|---|---|
| 1 | `context-engineering-phase-01-why-long-runs-fail.md` | 1.1 to 1.6 | `code/phase01_failure/` |
| 2 | `context-engineering-phase-02-cost.md` | 2.1 to 2.6 | `code/phase02_cost/` |
| 3 | `context-engineering-phase-03-compaction.md` | 3.1 to 3.4 | `code/phase03_compaction/` |
| 4 | `context-engineering-phase-04-split-or-file.md` | 4.1 to 4.5 | `code/phase04_split/` |

Exact phase titles:

- `# Phase 1 — Why long runs fail: length, steps and state`
- `# Phase 2 — Keep the cost of a long run linear`
- `# Phase 3 — Compaction you can check`
- `# Phase 4 — Split the work, or move it to a file`

Each document ends with the same parts: `## 🧪 Hands-on lab` with E1 to E12, `## 🔍 Check it yourself`, a checkpoint, `## References & Further Learning` and `## Cheatsheet`.

Module 2 builds on Module 1 sections 2.5, 2.6, 3.2, 3.3, 3.5 and 5.5. It does not repeat them.

---

## Symbols

Module 2 names every constant before it uses it. Some letters change meaning between phases. The last column says what a later module should do.

| Symbol | Meaning | Unit | Defined in | Note for later modules |
|---|---|---|---|---|
| `p` | success of one step or one attempt. In 1.1 it is expected accuracy. In 4.3 it is the chance a feature works after one attempt | share | 1.1, 1.4, 4.3 | Same idea each time, a success share |
| `H` | number of steps in a task or a run | count | 1.4, 2.1, 2.4 | Stable |
| `S` | Phase 1: success wanted for the whole task. Section 2.5: steps left in the run | share, then count | 1.4, 2.5 | Two meanings. Phase 3 avoids `S` on purpose |
| `n` | 1.1: trials per size. 4.2: implicit choices both writers apply | count | 1.1, 4.2 | Two meanings |
| `2.80` | 1.96 for 95% confidence plus 0.84 for 80% power | none | 1.1 | Used in `stats.py` |
| `f`, `u` | share of trials where the quote was right, and share right among those | share | 1.2 | `raw = f × u + (1 − f) × 0.5` |
| `r` | 1.4 only: recall of a check. From Phase 2 on: cache read price | share, then USD per million tokens | 1.4, 2.1 | Keep `r` for the cache read price. Write recall in words, as 4.3 does |
| `k` | 1.4: retries allowed. 2.4: the step where a token enters. 3.2 and 4.1: next steps a check looks at | count | 1.4, 2.4, 3.2 | Three meanings. Say which one |
| `q` | `(1 − p) × recall`, the chance an attempt fails and is caught | share | 1.4 | Different from `q_i` in 4.4 |
| `w` | cache write price | USD per million tokens | 2.1 | Stable |
| `P` | fixed instructions: tools, system prompt and task. 7,300 tokens in the labs | tokens | 2.1, 4.1 | Stable |
| `g` | tokens one step adds. About 2,150 in the labs | tokens | 2.1, 4.1 | Stable |
| `C` | tokens after a change that the cache would have served | tokens | 2.2 | Phase 3 avoids `C` on purpose |
| `X` | tokens one pruning event removes, net of placeholders | tokens | 2.5 | Stable |
| `A` | tokens after the first pruned point that stay and are written again | tokens | 2.5 | Stable |
| `M` | masking window. Tool outputs older than `M` steps get a placeholder | steps | Phase 2 terms, 2.6 | Stable |
| `B`, `T` | bytes on the wire, and input tokens billed | bytes, tokens | 3.1 | The lab counts 4 bytes per token |
| `coverage` | facts a summary keeps divided by facts in the old context | share | 3.2 | The wrong acceptance rule |
| `L`, `L_s`, `I` | context at compaction, summary size, summarization instruction of 200 tokens | tokens | 3.4 | Stable |
| `o` | output price | USD per million tokens | 3.4 | Stable |
| `P_sub` | a sub-agent's prefix, 3,400 tokens | tokens | 4.1 | Stable |
| `N`, `E` | items, 6, and search steps per item, 6 | count | 4.1 | Stable |
| `p_o`, `a` | chance a model picks option `o`, and chance two writers agree, `a = Σ p_o²` | share | 4.2 | Stable |
| `F`, check recall | features, 20, and the share of broken features the test catches, 0.95 | count, share | 4.3 | Recall is written in words here |
| `q_i` | success of stage `i` from a clean checkpoint | share | 4.4 | Different from `q` in 1.4 |
| `P_expected`, `P_observed` | product of all `q_i`, and success of the natural end-to-end run | share | 4.4 | Stable |
| `Γ` | horizon residual, `ln(P_expected / P_observed)` | nats | 4.4 | Stable |
| `m_i`, `m0` | trials behind each `q_i` and behind `P_observed` | count | 4.4 | Stable |
| `o_i` | success of stage `i` inside the natural run | share | 4.4 | The paper writes `r_i`. Module 2 renamed it because `r` is the cache read price |

## Terms

| Term | Meaning in Module 2 | Section |
|---|---|---|
| effective length | the longest input at which a model still scores above some bar | 1.1 |
| scorer | the rule that decides whether an answer counts as correct | 1.1 |
| literal, latent | a question that shares content words with the fact, or shares none | 1.3 |
| recite, then solve | copy the evidence first, then answer from a short prompt that holds only that evidence | 1.2 |
| recall of a check | the share of failed attempts the check catches | 1.4 |
| self-conditioning | a model makes more mistakes when it can see its own earlier mistakes | 1.5 |
| prefix, cache read, cache write | the start of a request, a token served from stored work, a token stored for later | Phase 2 terms |
| breakpoint | a marker the caller puts after a block. The provider stores an entry only there | 2.2 |
| lookback | the provider checks at most 20 positions back from each breakpoint | 2.2 |
| lifetime | how long a cache entry lives after its last use | 2.2 |
| one-time break, repeating break | a change paid once, or a change that recurs on every step | 2.2 |
| handle, view | a short reference to data outside the context, and a small summary next to it | 2.4 |
| pruning, observation masking, placeholder | replacing old content with something shorter. Masking replaces old tool outputs and keeps what the agent wrote | 2.5, 2.6 |
| restorable placeholder | a placeholder that names the call that produced the output, so the agent can call it again | 2.6 |
| compaction, summary, boundary | replacing old turns with a shorter text, that text, and the step where it happens | Phase 3 terms |
| transcript, owner | the full record of requests and replies, and the process that stores it between steps | 3.1 |
| PRE, POST | two runs from the same boundary and state, with the full history and with the summary | Phase 3 terms |
| blocked, repeated | the tool returned an error, or the exact same call already ran. TRACE's definitions | Phase 3 terms |
| sub-task end | the step where one unit of work finishes | Phase 3 terms |
| next-k check | check a summary or a return against the facts and actions of the next `k` logged steps | 3.2, 4.1 |
| replay | run PRE and POST from a restored boundary and count blocked and repeated actions | 3.2, 3.3 |
| ledger | a summary of facts the next steps use. It lists ids in play, open exact values and one done line per unit. It copies constraints word for word, ends with a status line and has no plan lines | 3.2 |
| sub-agent, lead, brief, return | a second agent with its own context, the agent that starts it, its instruction, and the text it sends back | 4.1 |
| single-full, single-clear, split | one agent that keeps every result. One agent that clears each item's results at the item end. A lead with sub-agents | 4.1 |
| implicit choice | a decision an agent makes while it acts that nobody stated | 4.2 |
| progress file | a file the agent writes so a later session knows what was done | 4.3 |
| checkpoint | a saved start for one stage: correct earlier work and a short context | 4.4 |
| state | in 4.4 and 4.5 only: work earlier stages left in the environment, such as files and records | 4.4 |
| horizon residual, nat | `Γ`, and the unit of a natural log. 0.69 nats is a factor of 2 | 4.4 |

A note for Module 9. "Checkpoint" in 4.4 is a clean starting point for one stage of a measurement. It is not a durable-execution checkpoint.

---

## Phase 1 — Why long runs fail: length, steps and state

Phase 1 names three causes of a failed long run: length, steps and state. It shows how to measure which one you have.

### 1.1 — Effective length belongs to the task and the scorer

**Claim.** An effective-length number belongs to a task, a scorer and a threshold. It does not belong to a model. Only a sweep on your own task predicts your agent, and it needs more trials than most teams run.

| Key number | Source | Checked |
|---|---|---|
| Llama-3.1-70B effective length is 64K on RULER and 2K on NoLiMa | RULER Table 3, NoLiMa Table 3. `effective_length.py rules` reproduces all nine rows | lab, re-run |
| The threshold rule alone changes the length for 5 of 9 models | `effective_length.py rules` | lab, re-run |
| The same 20 answers score 55% by a human, 50% `contains`, 35% `fuzzy>=0.8`, 10% `exact` | `effective_length.py scorers` | lab, re-run |
| At 80% accuracy, 20 trials per cell see only a 35.4-point drop. A 10-point drop needs 251 trials | `common/stats.py` | lab, re-run |
| A full sweep on gpt-6-luna costs $1.45 at 20 trials, $18.16 at 251, $28.93 at 400 | `find_vs_use.py --plan --model gpt-6-luna` | lab, re-run |

**Labs.** E1: `uv run python phase01_failure/effective_length.py scorers`, then `rules`. E2: `uv run python common/stats.py`, then `uv run python phase01_failure/find_vs_use.py --plan --model gpt-6-luna`.

**Terms and symbols.** effective length, scorer, threshold, `p`, `n`, `2.80`, and `drop = 2.80 × sqrt(2 × p × (1 − p) / n)`.

**Deferred.** Eval statistics beyond one interval go to Module 11. This is stated in `course.json` under `keptOut`. The phase text does not say it.

### 1.2 — Finding a fact and using it are two failures

**Claim.** A long input can make the model fail to find a fact. It can also find the fact and fail to use it. Moving the fact near the question fixes only the first. Recite, then solve fixes the second.

| Key number | Source | Checked |
|---|---|---|
| Llama-3.1-8B, MMLU, 30,000 tokens of essay filler: evidence recited 97.0% before and after, accuracy 63.2% to 39.0% | Du et al., Findings of EMNLP 2025, Table 6 | cited |
| Evidence placed right before the question still loses 19.4 points | Du et al., Table 8 | cited |
| Recite, then solve: Mistral-7B on GSM8K rises from 35.5% to 66.7% at 26,250 filler tokens | Du et al., Table 4 | cited |
| `raw = f × u + (1 − f) × 0.5`. Two agents at raw 0.75 can need opposite fixes | Phase 1 arithmetic | formula |
| Offline lab at 200k, fact at the end: found 98%, right when found 66%. With `--recite`: 97% | `find_vs_use.py`. Example curves, not a model measurement | lab, re-run |
| Recite, then solve adds 0.55% to the sweep cost: $28.93 to $29.09 | `find_vs_use.py --plan` | cited |

**Labs.** E3: `uv run python phase01_failure/find_vs_use.py`, then add `--recite`. E4 break-it: `find_vs_use.py --live --model claude-haiku-4-5 --trials 20` shows a size that does not fit the window. Nothing is sent. E5 live: `find_vs_use.py --live --model gpt-6-luna --trials 20 --yes`. E5 was not run and is marked UNVERIFIED in the phase.

**Reusable method.** Ask for `EVIDENCE:` then `ANSWER:`. Put the evidence field before the decision field. Check the quote exists in the history with a string search. The scorer is `score()` at `find_vs_use.py:97`.

**Terms and symbols.** find, use, invented evidence, recite then solve, `f`, `u`.

**Deferred.** None stated.

### 1.3 — Literal overlap hides the loss

**Claim.** A question that shares words with the fact hides the length loss. A latent question exposes it. So a needle test overstates usable length.

| Key number | Source | Checked |
|---|---|---|
| Llama-3.3-70B at 32K: 98.5 when the question repeats the key word, 56.2 one-hop, 93.1 one-hop with name options | NoLiMa, Table 6 | cited |
| A distractor that shares words drops GPT-4o's effective length to 1K | NoLiMa, Figure 5 | cited |
| BM25 ranks the fact first for every literal question at 10k to 200k, and scores 0 for every latent one | `literal_vs_latent.py demo` | lab, re-run |
| The sample eval is 8 literal of 10 questions, 80% | `literal_vs_latent.py audit` | lab, re-run |

**Labs.** E6: `uv run python phase01_failure/literal_vs_latent.py demo`. E7: `uv run python phase01_failure/literal_vs_latent.py audit --file phase01_failure/sample_eval.jsonl`. The audit runs on any JSON-lines file with `question` and `evidence` fields.

**Reusable method.** Five steps to write a latent question. Drop every content word of the evidence. Ask the way a user would. Keep the answer the same. Confirm overlap 0 with the audit.

**Terms and symbols.** literal, latent, BM25, content words.

**Deferred.** Retrieval into context goes to Module 3. Source: `course.json` `keptOut`.

### 1.4 — Steps multiply errors, whatever the length

**Claim.** In an agent, steps multiply errors even at a fixed length. A task of `H` steps at target `S` needs per-step success `S ** (1 / H)`. Shorter context cannot supply that. An external check with retries can, and the check's recall sets the limit.

| Key number | Source | Checked |
|---|---|---|
| `S = p ** H`. At `p` 0.95 and a 90% target, at most 2 steps | `steps_vs_length.py limit --p 0.95 --target 0.9` | lab, re-run |
| 100 steps at 90% need 0.99895 per step | `steps_vs_length.py table` | lab, re-run |
| Qwen3-32B falls below 50% task success within 15 turns | Sinha et al., ICLR 2026, Proposition 1 and Result 1 | cited |
| 50 steps, attempt success 0.95, 1 retry: no check 7.7%, 50% recall 26.4%, 90% recall 69.5%, 99% recall 86.2% | `steps_vs_length.py retry` | lab, re-run |
| With 5 retries, 50% recall reaches only 27.3%, and 99% recall reaches 97.4% | `retry --retries 5` | lab, re-run |
| Two horizons, `10:0.60 50:0.02`, imply 0.9502 and 0.9247 per step. Spread 0.0255 means steps are not independent | `steps_vs_length.py estimate` | lab, re-run |

**Labs.** E8: `uv run python phase01_failure/steps_vs_length.py limit --p 0.95 --target 0.9`, then `table`. E9: `retry --p 0.95 --retries 1 --steps 50`, then `--retries 5`. E10 break-it: `estimate --observed 10:0.60 50:0.08`, then `50:0.02`.

**Reusable code.** `with_retries()` at `steps_vs_length.py:69` gives per-step success `p × (1 − q ** (k + 1)) / (1 − q)`. `retry_cap()` at line 79 gives the ceiling `p / (1 − q)`. The self-verification prompt from Sinha et al. did not fix the problem.

**Terms and symbols.** `p`, `H`, `S`, `r` as recall, `k` as retries, `q`.

**Deferred.** The step-count measurement becomes the horizon residual in 4.4.

**Correction to Module 1.** Module 1 section 2.6 cites Mittal, arXiv 2609.01660, for "a smaller context made success fall faster". That arm kept only self-written state. It measures 1.5, not length. Verified in the phase from the study's `runner.py`, function `_context`.

### 1.5 — A wrong fact in context makes each later step worse

**Claim.** Context is state, not only input. A wrong output the agent wrote is read again on every later step. So errors are not independent, and `p ** H` is the best case. The fix is to remove bad state by rule, not only to trim old state.

| Key number | Source | Checked |
|---|---|---|
| DeepSeek-V3 at turn 100: 0.99, 0.73 and 0.25 accuracy at 0%, 50% and 100% wrong history | Sinha et al., Figure 5b | cited |
| Thinking models score about 0.76 to 0.88 with every earlier answer wrong, when old reasoning is removed | Sinha et al., Figure 6 | cited |
| Corrupting about 10% of current reasoning drops Qwen3-8B from 84.9 to 14.7 on GSM8K | Li et al., arXiv 2602.00173, Table 1 | cited |
| Sliding window, Gemma3-12B, turn 200: about 0.36 full history against about 0.72 windowed | Sinha et al., Appendix C.2 | cited |
| Lab, Qwen3-32B curve, 30 steps in 45 attempts. Closed form 100.0%, keep 56.1%. Clean every 15 steps 67.1%, every 5 steps 83.4%, every step 96.3% | `poisoned_state.py` | lab, re-run |
| A wrong claim labelled as a memory message, not the agent's thought, was flagged 86.7 points more often by Llama-3.3-70B | Chen et al., arXiv 2606.05976, preprint | cited |
| One full rewrite by a model shrank a context from 18,282 tokens to 122. Accuracy fell from 66.7 to 57.1, below 63.7 with no context | ACE, Zhang et al., ICLR 2026, Figure 2 | cited |

**Labs.** E11: `uv run python phase01_failure/poisoned_state.py`, then `--curve deepseek-v3`. E12 break-it: `--chunk 15`, `--chunk 1`, `--curve flat`.

**Reusable method.** Three cleaning rules. Mark failures with an external signal. Delete the failed output and keep one line about it, labelled as a tool result. Delete by rule, and never ask a model to rewrite the whole context.

**Terms and symbols.** self-conditioning, keep, clean, healed history.

**Deferred.** Checking a model rewrite goes to Phase 3. The window is not simulated, because it would need the length effect too.

### 1.6 — Which failure do you have? Diagnose before you fix

**Claim.** Length, steps and state leave different signatures. Two horizons split independent steps from errors that grow with the run. The quoted evidence splits finding from use. Measure first, then fix.

**Key numbers.** None new. The section reuses 1.1, 1.2 and 1.4. Its diagnosis table has six rows. They are: the eval measures the wrong thing, a use failure, a finding failure, invented evidence, independent steps, and wrong state spreading.

**Labs.** No new lab. The "Try this now" uses `steps_vs_length.py estimate --observed H1:S1 H2:S2`.

**Deferred.** Section 4.5 adds cost, lossy summaries and lossy returns to the table. Section 4.4 splits length from bad work left in the environment. The cleaning rerun in 1.6 cannot do that.

---

## Phase 2 — Keep the cost of a long run linear

Phase 2 prices a long run step by step. It covers the cache first, then what enters and what leaves the context.

### 2.1 — Every step re-reads the whole history

**Claim.** An agent re-reads its whole history on every step. So its cost grows with the square of the step count. A cache divides the cost, by about 3 times on short runs and 9 times on long ones. Only a bounded context makes the cost grow in a straight line.

| Key number | Source | Checked |
|---|---|---|
| Input tokens `= H × P + g × H × (H − 1) / 2` | Phase 2 | formula |
| claude-sonnet-5, 10 to 200 steps: cache cost ×91.2, bounded 40k context ×27.3 | `trajectory.py growth` | lab, re-run |
| 200 steps: $92.28 no cache, $10.53 with cache, $3.15 bounded. Re-reading is 86% of the cached bill | `trajectory.py growth` | lab, re-run |
| Four 50-step runs cost $3.92. One 200-step run costs $10.53 | `trajectory.py growth` | lab, re-run |
| Real traces: the median call reads about 119K cached tokens, adds 875, outputs 214 | TraceLab, arXiv 2606.30560, about 4,300 sessions, preprint | cited |

**Labs.** E1: `uv run python phase02_cost/trajectory.py growth`. Add `--model gpt-6-luna` to see the same ×91.2 shape at lower dollars.

**Terms and symbols.** `P`, `g`, `H`, `r`, `w`. From this section on, `r` is always the cache read price.

**Deferred.** The bounded column assumes removal is free. Section 2.5 prices removal.

### 2.2 — A cache break costs one rewrite, or one per step

**Claim.** A cache break costs one rewrite of everything the cache would have served, `(w − r) × C`. A one-time break pays that once. A break that repeats pays it on every step and turns the whole run into writes.

| Key number | Source | Checked |
|---|---|---|
| `edit@20`: `(2.50 − 0.20) × 52,053 / 1,000,000 = $0.1197`. The lab prints `+$0.120` | `trajectory.py meter` | lab, re-run |
| 40-step run, clean $0.702. One-time edits add $0.028 at step 3 and $0.215 at step 38. An old tool result adds $0.094, a slow tool $0.127 | `trajectory.py meter` | lab, re-run |
| A timestamp in the system prompt, or random JSON key order, costs ×7.56, $5.309 | `trajectory.py meter` | lab, re-run |
| `edit@20` moves the run-average hit rate only from 95.4% to 92.9%, for +17% cost. Step 20 itself is 0% | `trajectory.py meter` and `steps` | lab, re-run |
| 20-position lookback per breakpoint. Anthropic lifetime 5 minutes, 1-hour option at 2× input for writes. OpenAI 30 minutes on GPT-5.6 and later | Anthropic and OpenAI prompt-caching pages | cited |
| 97.5% hit rate after a tool result, 84.4% after a human turn | TraceLab, Table 11 | cited |

**Labs.** E2: `uv run python phase02_cost/trajectory.py meter`, then `steps --break edit@20`. E3 break-it: `steps --break timestamp`. E4: `meter --model gpt-6-sol --breaks none slow@20 timestamp`.

**Reusable method.** Put two breakpoints: one after the fixed instructions, one on the last block. See `breakpoints()` at `trajectory.py:153`. Alert on the hit rate per step, not per run. One step at 0% is a one-time break. Every step near 0% is a repeating break.

**Terms and symbols.** `C`, breakpoint, lookback, lifetime, one-time break, repeating break.

**Deferred.** The causes of a single-request break are in Module 1, 3.2. The phase links there.

### 2.3 — Restrict the tools, never edit the list

**Claim.** The tool list sits at the start of every request, so an edit rewrites everything after it. Restrict the tools with a mask, a harness rejection or a tool that changes the agent's mode.

| Key number | Source | Checked |
|---|---|---|
| Switch off one tool at step 20 of 40. Cost against keep: mask-decode 1.00, mask-reject 1.02, tool-choice 1.15. Remove 1.17 with one orphan call, per-step choice 7.07 | `mask_vs_remove.py` | lab, re-run |
| Three misfires raise mask-reject to 1.06 | `mask_vs_remove.py --misfires 3` | lab, re-run |
| Anthropic has no `allowed_tools`. A `tool_choice` change keeps the tools and system cache and invalidates the messages cache | Anthropic prompt-caching page | cited |
| OpenAI offers `tool_choice` with type `allowed_tools` as the cache-safe restriction | OpenAI function-calling guide | cited |
| Claude Code uses `EnterPlanMode` and `ExitPlanMode` as tools, and `defer_loading` with tool search. A discovered tool enters the conversation, not the prefix | Claude Code caching post, Anthropic tool search page | cited |

**Labs.** E5: `uv run python phase02_cost/mask_vs_remove.py`. E6 break-it: `--misfires 3`.

**Reusable method.** A five-step decision list. Model the change as a mode tool. On OpenAI use `allowed_tools`. On Anthropic keep the list and reject calls in the harness. Use deferred loading for large tool sets. Edit the list only once, at a sub-task boundary.

**Terms and symbols.** mask-decode, mask-reject, tool-choice, orphan call.

**Deferred.** Tool description design, tool count and selection accuracy go to Module 6. This is stated in `course.json` `keptOut`, which says 2.3 links to Module 6. Since the 2026-09-23 read-through, sections 2.3 and 2.4 contain that link. Earlier note, before the fix: the phase text did not contain it. Verified then by `grep "Module 6"`.

### 2.4 — Handles, not payloads: shrink context at the tool

**Claim.** The cheapest token is one that never enters the context. A token is re-read on every later step. After `w / r` steps its re-reads cost more than its first write. Return a handle and a small view.

| Key number | Source | Checked |
|---|---|---|
| One token costs `w + r × (H − 1 − k)`. Re-reads pass the write after `w / r = 12.5` steps on current prices | `handles.py:56`, `lifetime_cost()` | formula |
| 6,000 tokens at step 5 of 30: first write $0.0150, 24 re-reads $0.0288 | `handles.py cost` | lab, re-run |
| Same 30-step task: payload $0.663, handle $0.390, 59%, with 3 extra steps | `handles.py compare` | lab, re-run |
| The handle loses, at 1.22, when every step needs the whole 6,000-token document | `handles.py sweep` | lab, re-run |
| Observations are about 84% of a mean SWE-agent turn. Pilot of 50 tasks on GPT-4.1-mini | JetBrains, Complexity Trap, section D.4 | cited |
| Claude Code caps a tool response at 25,000 tokens by default. Concise Slack response 72 tokens, detailed 206 | Anthropic, writing tools for agents | cited |

**Labs.** E7: `uv run python phase02_cost/handles.py cost`, then `compare`. E8 break-it: `handles.py sweep`.

**Reusable method.** Four rules for any tool that can return more than a few thousand tokens. Return a handle and a view. Add a fetch tool that takes a range, a page or a filter. Cap every response and say when you truncated. Use ids the agent can repeat exactly.

**Terms and symbols.** handle, view, detail share, `k` as the entry step.

**Deferred.** Tool design as a whole goes to Module 6, per `course.json`. Since the 2026-09-23 read-through, the phase text says it.

### 2.5 — Pruning costs a rewrite, so it has a break-even

**Claim.** Pruning costs a rewrite from the first pruned point. It pays when `S > (w − r) / r × A / X`. Prune in batches, never a little on every step. Whether per-step pruning ever pays depends on the provider's prices and cache rules.

| Key number | Source | Checked |
|---|---|---|
| `(w − r) / r = 11.5` on claude-sonnet-5. X 40,000 and A 20,000 pay after 5.75 steps. X 2,000 and A 58,000 need 334 | `prune.py breakeven` | lab, re-run |
| 200 steps, cost against keeping all: per-step window 1.75, window moved every 10 steps 0.47, threshold 0.36. At 40 steps the per-step window is 2.91 | `prune.py sim` | lab, re-run |
| Keep 20 without `clear_at_least`: 154 events, 2.34. With 20,000: 17 events, 0.61 | `prune.py sim --steps 200 --keep 20` | lab, re-run |
| With reads at 0.25× and writes at 1×, and every prefix cached: per-step window 0.46, threshold 0.23 | `prune.py sim --every-prefix --read-x 0.25 --write-x 1.0` | lab, re-run |
| SWE-agent's `LastNObservations` "will break prompt caching" and has a `polling` setting | SWE-agent source | cited |
| `clear_tool_uses_20250919` has `clear_at_least`, default none | Anthropic context-editing page | cited |

**Labs.** E9: `uv run python phase02_cost/prune.py breakeven`, then `--read-x 0.25 --write-x 1.0`. E10: `prune.py sim`, then the `--every-prefix` run above. E11 break-it: `prune.py sim --steps 200 --keep 20 --clear-at-least 0`.

**Reusable method.** Five rules. Prune in batches. Set a minimum saving per event. Prune at a sub-task boundary, where 1.5 also cleans. Keep a breakpoint after the fixed part. Stop pruning near the end of a run.

**Terms and symbols.** `X`, `A`, `S` as steps left, pruning event, window, window-poll, threshold, `clear_at_least`.

**Inferred, not measured.** JetBrains' saving from per-step masking fits the lab with cheaper rewrites. The phase labels this match as inferred from the code and the price basis.

**Deferred.** None stated.

### 2.6 — A placeholder fails only on an exact value

**Claim.** A placeholder is safe while the agent has written down what it learned. It fails when a later step needs an exact value from an old output that the agent never copied. Make the placeholder restorable, and audit your logs for those values.

| Key number | Source | Checked |
|---|---|---|
| Masking kept the solve rate on 4 of 5 models at about half the cost. Qwen3-Coder 480B: 53.4% at $1.29 raw, 54.8% at $0.61 masked, 53.8% at $0.64 summarized | JetBrains, Complexity Trap, Table 1, 500 SWE-bench Verified tasks per model | cited |
| Gemini 2.5 Flash with thinking fell from 40.4% to 36.4% masked and 31.4% summarized | same Table 1 | cited |
| Sample log, hidden values by window 3, 5, 10, 15, 20: 4, 3, 3, 3, 0 | `exact_values.py sweep` | lab, re-run |
| No study in the course's research measures this failure directly | Phase 2 text | cited |

**Labs.** E12: `uv run python phase02_cost/exact_values.py sweep`, then `sweep --file <your log>` with a `--pattern` per id format. `audit --window M` names each hidden value and the call that produced it.

**Reusable method.** Three fixes. A restorable placeholder that names the call. A system-prompt rule to copy exact values into reasoning. `exclude_tools` for short tools full of ids.

**Terms and symbols.** `M`, observation masking, restorable placeholder, hidden value.

**Deferred.** Summaries go to Phase 3.

---

## Phase 3 — Compaction you can check

Phase 3 answers three questions. Who writes the summary and can you see it? How do you test it? How often should you compact?

### 3.1 — Who owns the transcript

**Claim.** Who owns the transcript decides which checks you can run on a summary. Server-held state saves bytes on the wire, not billed tokens. In most server modes the model uses the summary before you can read, change or reject it.

| Key number | Source | Checked |
|---|---|---|
| Every previous input token in a `previous_response_id` chain is billed | OpenAI conversation-state guide | cited |
| 200 steps: 183,959,304 bytes resent against 7,088,572 chained, 26.0× fewer. Both bill 45,989,826 tokens. At 20 steps, 3.3× fewer bytes and 593,782 tokens both ways | `ownership.py wire` | lab, re-run |
| 5 of 9 documented modes allow no check before the model uses the summary | `ownership.py modes` | lab, re-run |
| Anthropic `compact_20260112`: trigger default 150,000 tokens, minimum 50,000. `pause_after_compaction: true` lets you add blocks first | Anthropic threshold compaction page | cited |
| Anthropic on-demand compaction, beta `compact-2026-09-04`: readable, returned before use, not editable. `compaction_content_mismatch` on a change. Custom `instructions` up to 16,384 characters | Anthropic on-demand compaction page | cited |
| OpenAI compaction items are encrypted and opaque. `instructions` are not carried over with `previous_response_id`. `truncation` defaults to `disabled` | OpenAI compaction guide, create reference | cited |

**Labs.** E1: `uv run python phase03_compaction/ownership.py modes`. E2: `ownership.py wire`, then `wire --steps 200`.

**Reusable code.** `checks_for()` at `ownership.py:100` turns four properties into allowed checks. The properties are holds, read, edit and before use. next-k needs read and before use. Replay needs your own transcript and before use. Reject needs before use. Repair needs read, edit or add-after, and before use.

**Terms and symbols.** transcript, owner, client-held, server-held, `B`, `T`.

**Deferred.** None stated.

### 3.2 — Judge a summary by the next steps, not by reading it

**Claim.** A summary is correct only relative to the steps that come after it. Reading it, or counting what it kept, cannot tell you whether it is safe. Test it against the next steps, facts and intent, or by a paired replay. Write it as a ledger.

| Key number | Source | Checked |
|---|---|---|
| First errors after a bad summary on SWE-bench Verified: 60% at the first step, 88% by step 3, 96% by step 6. On BrowseComp, 97% at the first step | Slipstream, arXiv 2605.08580, Figure 3b, preprint | cited |
| The judge scores facts and intent in one call and accepts at 7 of 10. The check plus targeted repair added 6.4 to 8.8 points, Qwen3.5-9B | Slipstream, section 5.1, Figure 5, Table 1 | cited |
| Lab, 945 summaries, 306 harmful: coverage ≥ 80% rejects 79% of harmful and 27% of harmless. next-k facts and intent at k=3 rejects 69% and 0%. Replay over 5 actions rejects 80% | `nextk.py`. Example keep rates | lab, re-run |
| At k=6, 27% of harmful summaries still pass, because their damage comes later | `nextk.py` | cited |

**Labs.** E3: `uv run python phase03_compaction/nextk.py`. E4 written: `nextk.py --show 2`. `sim.py --show 8 --style ledger --seed 3` prints a ledger.

**Reusable method.** Six steps to accept or reject every summary. Write a ledger. Run the compactor in the background. Extract the facts the logged steps used. Check intent by a judge call or a replay. Repair a rejected summary by adding lines after it. Replay 20 or more logged boundaries before you ship a new summarization prompt.

**Terms and symbols.** sufficiency, next-k, facts check, intent check, coverage, harmful, `k`, ledger.

**Deferred.** The facts half of this check is reused for sub-agent returns in 4.1.

### 3.3 — The symptom is repeated work and no stop

**Claim.** A lossy summary shows up as behaviour, not as an error. The agent repeats calls, makes calls the tool refuses, and does not stop. Alert on repeated calls and repeated side effects after each compaction. A plan line in a summary reads as open work.

| Key number | Source | Checked |
|---|---|---|
| Stop rate at the end of a finished task, 2K budget, MiniMax-M3: FIFO 77.2%, full history 66.6%, summary 44.6% | TRACE, arXiv 2608.06503, Figure 2, preprint | cited |
| POST added 0.108 blocked actions at the first action after compaction. Repeated actions started at 0.031 and rose | TRACE, Figure 4 | cited |
| At TRACE's tightest budget, summaries passed 72.8% of tasks and FIFO 42.2% | TRACE, Figure 1 | cited |
| Removing one fact kind from a ledger: only a lost done line gives blocked calls, +2.571. Lost ids +0.929 repeated. A plan line +1.000 repeated with no fact lost | `replay.py symptoms` | lab, re-run |
| Paired replay, 135 boundaries: PRE 0.204. Ledger and lean +0.000, narrative +0.107, FIFO +2.610 | `replay.py compare` | lab, re-run |
| Stop probe: full, FIFO and ledger 96.6%, narrative 88.8%. One plan line takes the ledger to 0.0% | `stop_probe.py`, `--plan-line` | lab, re-run |
| Sample log: repeat rate 60% and 40% after two compactions against 11% in the rest of the run. Errors 0% | `replay.py monitor` | lab, re-run |

**Labs.** E5: `uv run python phase03_compaction/replay.py compare`. E6 break-it: `replay.py symptoms`. E7: `stop_probe.py`. E8 break-it: `stop_probe.py --plan-line`. E9: `replay.py monitor --file phase03_compaction/sample_run.jsonl`, then your own log. E12 live: `stop_probe.py --live gpt-6-luna --tasks 20`. E12 was not run.

**Reusable method.** Four alerts per compaction, over the next 5 calls. Alert on repeated calls, repeated side effects, errors, and calls after done. Add two harness guards. Give every side-effect call an idempotency key. End every ledger with a status line.

**Terms and symbols.** blocked, repeated, PRE, POST, FIFO, stop probe, execution-state mislocalization.

**Deferred.** None stated.

### 3.4 — Each compaction is a paid call and a loss event

**Claim.** A compaction pays for itself within 3 to 12 steps. The range depends on whether the summarizing call reads the cache. So cost only rules out compacting every few steps. The loss per compaction sets the rest. Measure the loss, then fire at sub-task ends with a size backstop.

| Key number | Source | Checked |
|---|---|---|
| Event cost `L × r + I × input + L_s × o + L_s × w`. Saving `(L − L_s) × r` per later step | Phase 3 | formula |
| L 60,000, L_s 1,500, claude-sonnet-5: $0.0312 once, $0.0117 per step, paid back in 2.7 steps. On a cache miss: $0.1391, 11.9 steps | `timing.py event` | lab, re-run |
| Narrative summaries, 30-order run: compacting at every sub-task end gives 30 compactions, +52.6 extra actions, $1.146 against $1.083 for never | `timing.py sweep` | lab, re-run |
| Each lossy compaction adds 1.75 to 3.35 extra actions, whatever the rule | `timing.py sweep`, example keep rates | cited |
| Ledger summaries: 20,000-token threshold is cheapest, $0.576. 80,000 costs $0.855. On a miss, 20,000 costs $0.791 and every-sub-task costs $1.258 | `timing.py sweep --style ledger` | lab, re-run |
| Sub-task end against threshold over 200 seeds: +0.10 ± 0.37 and +0.19 ± 0.31 extra actions. No measured gain | `timing.py sweep --seeds 200` | lab, re-run |
| A context edit, `clear_thinking_20251015` with `keep:1`, ran on every turn instead of once. It made Claude seem "forgetful and repetitive" | Anthropic postmortem, 2026-04-23 | cited |
| Recent steps diverge 0.149 when kept word for word and 0.233 when summarized | TRACE, Figure 3 | cited |

**Labs.** E10 break-it: `uv run python phase03_compaction/timing.py sweep`, then `timing.py event --context 60000 --summary 1500`, then add `--summarizer-cache miss`. E11: `timing.py sweep --style ledger`, with and without `--summarizer-cache miss`.

**Reusable method.** Six steps to choose a compaction rule. Measure loss per compaction. With zero loss, compact at sub-task ends as often as it saves money. With loss, compact as rarely as the budget allows. Fire when no tool call is open. Keep a size backstop of at least 50,000 on Anthropic server compaction. Alert on the count of compactions.

**Terms and symbols.** `L`, `L_s`, `I`, `o`, threshold rule, boundary rule, `HARD = 1.25`.

**Not checked.** Whether a provider's compaction call reads the cache. The pages do not say. The lab prices both cases.

**Deferred.** None stated. The budget zones, the trigger and the 400 backstop stay in Module 1, 2.6.

---

## Phase 4 — Split the work, or move it to a file

Phase 4 covers sub-agents, parallel writers, files the agent writes, and one number that says whether length is the problem. Section 4.5 is the map for the whole module.

### 4.1 — A sub-agent moves tokens, it does not remove them

**Claim.** A sub-agent moves exploration out of the parent's context. It does not remove it from the bill. It adds quality only through a shorter context. One agent that clears each item's tool results at the item boundary gets almost the same bound. So at an equal budget a split mainly buys parallel time. The return is a compaction.

| Key number | Source | Checked |
|---|---|---|
| Equal work, 6 items × 6 steps: input tokens 1,764,695 single-full, 768,949 single-clear, 456,749 split. Cost $0.615, $0.527, $0.533. Wall time 6.2, 7.2, 1.5 minutes | `split_budget.py work` | lab, re-run |
| With a shared sub-agent prefix, the split costs $0.498, below single-clear | `split_budget.py work --share-prefix` | lab, re-run |
| Equal input tokens: split 96.8%, single-clear 96.5%, single-full 89.1% | `split_budget.py budget` | lab, re-run |
| Equal dollars: single-clear 96.7%, single-full 94.3% | `split_budget.py budget --match dollars` | lab, re-run |
| With Phase 1's example length curve, equal work: single-full 70.3%, single-clear 75.1%, split 77.3% | `split_budget.py work --curve example` | lab, re-run |
| A return that loses one value in seven: split 82.5%, below single-full at 89.1% | `split_budget.py budget --keep 0.85` | lab, re-run |
| Anthropic's research system beat single-agent Opus 4 by 90.2% on an internal eval. The eval size and a matched-token arm are not published | Anthropic multi-agent research post, 2025 | cited |
| Three factors explain 95% of BrowseComp variance. Token usage alone explains 80% | same post | cited |
| Agents use about 4× the tokens of chat, multi-agent about 15×. Both are relative to chat, not to a single agent at equal work | same post | cited |
| Parallel sub-agents cut research time by up to 90% | same post | cited |
| Return check at k=3: prose returns pass 1 of 4, field returns 4 of 4. Fixture of four hand-written runs | `return_check.py check --k 3` | lab, re-run |

**Labs.** E1: `uv run python phase04_split/split_budget.py work`, then `--share-prefix`. E2: `split_budget.py budget`, `--curve example`, `--match dollars`. E3 break-it: `budget --keep 0.85`. E4: `return_check.py check --k 3`, then `check --file <your runs.jsonl>`. E5 break-it: `return_check.py sweep`, then `check --k 4`.

**Reusable method.** Seven steps to decide when to split and what to ask back. The baseline a split must beat is single-clear at the same dollars. Sub-agents share a cached prefix only with the same tools and system prompt and a breakpoint after them. The other sub-agents must start after the first response begins. Write the return as fields with exact values, what failed, and a handle to the full results.

**Terms and symbols.** sub-agent, lead, brief, return, `P_sub`, `N`, `E`, single-full, single-clear, split.

**Not checked.** When a new OpenAI cache entry becomes visible to requests already in flight.

**Deferred.** None stated.

### 4.2 — Parallel readers are safe, parallel writers are not

**Claim.** Parallel sub-agents are safe when they read and unsafe when they write. Each writer makes choices nobody stated. Two writers agree on one such choice with chance `Σ p_o²`. A merge sees lines, not choices.

| Key number | Source | Checked |
|---|---|---|
| Preference 0.60, 0.25, 0.15 gives `a = 0.445`. Three unstated choices give `0.445 ** 3 = 0.088` | Phase 4 arithmetic | formula |
| 10,000 runs × 3 seeds: a clean merge ships a silent inconsistency in 91.4% of runs. Closed form 91.2% | `parallel_writers.py` | lab, re-run |
| Overwrite loses 10.00 edits. Summary reconciliation 87.6%, or 28.7% when summaries name 90% of choices. One writer 0.0% | `parallel_writers.py`, `--report 0.9` | lab, re-run |
| "Actions carry implicit decisions, and conflicting decisions carry bad results" | Cognition, 2025 | cited |
| Writes stay single-threaded. A clean-context reviewer catches about 2 bugs per pull request, about 58% severe. Vendor claim without conditions | Cognition, 2026 | cited |

**Labs.** E6: `uv run python phase04_split/parallel_writers.py`. E7 break-it: `--report 0.9`, then `--stated 6`.

**Reusable method.** Five rules. Run readers in parallel. Give all writes to one agent. State every shared choice in the brief if writers must run in parallel. Never let two writers save whole files. Do not rely on summaries to reconcile writers.

**Terms and symbols.** implicit choice, `p_o`, `a`, `n` as implicit choices, overwrite, merge, one-writer.

**Deferred.** None stated.

### 4.3 — A note the agent wrote is an input you must check

**Claim.** A file moves memory out of the model into something the agent wrote. The new failures are a note that is wrong, stale, or missing scope. Check the note against an external test when it is read. Check every path the model asks for as untrusted input.

| Key number | Source | Checked |
|---|---|---|
| Marking without a test: `0.85 ** 20 = 0.039`, so 96% of runs declare done with a broken feature | Phase 4 arithmetic | formula |
| False pass per feature with test and fix: `(1 − p) × (1 − recall) / (1 − (1 − p) × recall) = 0.0087` | Phase 4 arithmetic | formula |
| False finish: prose 100.0%, list 96.0%, list+test 16.2%, list+test+read 0.1% | `progress_notes.py` | lab, re-run |
| With 1% regressions: list+test 87.2%, list+test+read 2.1% | `progress_notes.py --regress 0.01` | lab, re-run |
| Notes written only at session end: 100% of list runs never finish | `progress_notes.py --note-at session` | lab, re-run |
| Nine traversal attacks: no check lets 9 escape, string prefix 8, `../` filter 6, canonical check 0. All four run 8 of 8 normal commands | `memory_paths.py` | lab, re-run |
| Feature list with a `passes` field, and a basic end-to-end test at session start. The post reports no numbers | Anthropic, effective harnesses for long-running agents | cited |

**Labs.** E8: `uv run python phase04_split/progress_notes.py`. E9 break-it: `--regress 0.01`, then `--note-at session`. E10 break-it: `uv run python phase04_split/memory_paths.py`, then `--posix`.

**Reusable code.** `_canonical()` at `memory_paths.py:107`. It decodes in a loop and rejects `%`, NUL and backslash. It requires the first part to be exactly `memories` and rejects `..` and `.` parts. It resolves symlinks, checks `relative_to()`, and refuses the root.

**Reusable method.** Six rules for progress files. Write the full scope first, all failing. Mark done only after an external test. Re-run the tests of marked items on every read. Write after each item. Prefer JSON the agent edits field by field. Put every file operation behind the canonical path check.

**Terms and symbols.** progress file, scope, wrong, stale, `F`, check recall.

**Deferred.** Memory across sessions and users goes to Module 10. Prompt injection through memory files goes to Module 16. Both are stated in the phase text.

### 4.4 — Measure whether length is your problem at all

**Claim.** Whether length is your problem is one number, the horizon residual `Γ = ln(P_expected / P_observed)`. Near zero means compounding, so raise per-step reliability. Above zero, a fresh context per stage and a state repair tell context from bad state in the work.

| Key number | Source | Checked |
|---|---|---|
| Definition, stage-wise sum and variance: Equations 1 to 4. Decide with a bootstrap over whole tasks | Peng et al., arXiv 2607.27283, position paper, preprint | cited |
| Lab, 6 stages, checkpoints give 0.524. `none` −0.011, interval [−0.056, +0.034] | `horizon_residual.py run --scenario none` | lab, re-run |
| `length` +0.398. Fresh context −0.017. Repaired state +0.419 | `run --scenario length` | lab, re-run |
| `state` +0.525. Fresh context +0.604. Repaired state −0.015 | `run --scenario state` | lab, re-run |
| Dirty checkpoints hide the state problem: −0.008 | `run --scenario state --dirty-checkpoints` | lab, re-run |
| Phase 1's `10:0.60 50:0.02` as a residual: +1.358 nats, interval [+0.564, +2.152] with 400 trials. Not estimable with 20 | `from-horizons --trials 400` | lab, re-run |
| To see 0.2 nats with 6 stages: about 191 trials per protocol, 1,337 runs in total | `plan --gamma 0.2` | lab, re-run |
| ChainSWE per-bug accuracy: Oracle 58.9%, Seq with a fresh conversation 36.5%, Seq+Mem with history carried 36.9%. GPT-5.5 the one exception | ChainSWE, arXiv 2607.02606, section 5.1, preprint | cited |
| Relative drop from Oracle to Seq: 33% raw history, 40% Summarize, 41% Sub-Agent | ChainSWE, section 5.1 | cited |

**Labs.** E11: `uv run python phase04_split/horizon_residual.py run --scenario none`, then `length`, `state`, and `state --dirty-checkpoints`. E12: `horizon_residual.py from-horizons --observed 10:0.60 50:0.02 --trials 400`, then `plan --gamma 0.2`. Also `run --scenario both`.

**Reusable code.** `estimate()` at `horizon_residual.py:232` returns `Γ`, its Equation 4 interval and one term per stage, `ln(q_i / o_i)`.

**Terms and symbols.** `q_i`, `P_expected`, `P_observed`, `Γ`, `m_i`, `m0`, `o_i`, nat, checkpoint, reset, repair, state.

**Deferred.** None stated. Bootstrap statistics are named but not built. Module 11 owns eval statistics, per `course.json`.

### 4.5 — Which failure is it? One map for the module

**Claim.** Name the cause before you change anything. Length, steps, state, cost and a lossy summary each leave their own sign and have one measurement. Logs you already have show three of them. A fix for the wrong cause can add a new one.

**Key numbers.** None new. The section reuses 2.2, 3.3, 3.4, 4.1 and ChainSWE from 4.4.

**The map.** Eleven rows since the 2026-09-23 read-through, which added "evidence invented" from 1.6. Each row gives the cause, the sign, the section, the measurement and the first fix. The rows cover length (the eval hides it, the fact is not found, the fact is not used, evidence invented), steps, "State: wrong facts in the context" (1.5), length over the whole run, "State: bad work in the environment" (4.2 to 4.4), cost, a lossy summary and a lossy return. The cost sign is steps at 0% cache hits, or a cost per step that keeps rising with the history. The section ends with "The module question, step by step", a worked answer from saved runs.

**The order to measure in.**

1. Logs you already have, no new runs. A step at 0% cache hits points to cost, 2.2. Repeats after a compaction point to a lossy summary, 3.3. A parent that searches again after a return points to a lossy return, 4.1.
2. New runs at two lengths, then `Γ` and one rerun per intervention, 1.4 and 4.4. If a fresh context closes the gap, run the cleaning rerun next: if cleaning also closes it, the cause is wrong facts in the context; if cleaning changes nothing, the cause is length. A fresh context alone cannot tell the two apart.
3. On wrong answers, EVIDENCE then ANSWER, 1.2.

**Labs.** No new lab. The "Try this now" uses `replay.py monitor` and `horizon_residual.py run --scenario both`.

**Deferred.** None stated.

---

## Shared code other modules can reuse

Run everything from `study-material/context-engineering/code/` with `uv run python <path>`. The code needs Python 3.11 or later, pinned to 3.12, and the standard library only. Every script has `--self-test`. No offline command spends money.

| File | What it provides | Command or entry point | Self-test |
|---|---|---|---|
| `common/prices.json` | USD per million tokens, cache lifetime and minimum for `claude-haiku-4-5`, `claude-sonnet-5`, `gpt-6-luna`, `gpt-6-sol`. Fetched 2026-09-23 | read as JSON | none |
| `common/prefix_cache.py` | `Block`, `PrefixCache`, `Price`, `cost()`, `for_model()`. Bills an agent run step by step with breakpoints, 20-position lookback, lifetime and minimum size | import | 19 checks |
| `common/stats.py` | `wilson()`, `halfwidth()`, `smallest_drop()`, `trials_for()`. 95% confidence, 80% power | `common/stats.py --p 0.8 --trials 20 50 100` | 8 checks |
| `common/history.py` | synthetic support-chat history of N tokens with one fact at a chosen depth | `common/history.py --tokens 50000 --depth 0.5 --show 3` | 31 checks |
| `common/live.py` | `estimate()`, `fits()`, `call()` with thinking turned off, for Anthropic and OpenAI | `common/live.py --estimate gpt-6-luna 200000 20` | 11 checks |
| `phase01_failure/literal_vs_latent.py` | overlap audit of any eval set, JSON lines with `question` and `evidence` | `audit --file F` | 23 checks |
| `phase01_failure/steps_vs_length.py` | step limits, reliability targets, two-horizon estimate, check plus retry model | `table`, `limit`, `estimate --observed H:S ...`, `retry` | 23 checks |
| `phase01_failure/find_vs_use.py` | find against use scorer, sweep cost plan, optional live sweep | `--plan --model M`, `--live --model M` | 16 checks |
| `phase02_cost/trajectory.py` | per-step hit rate and cost for a run with a chosen break | `growth`, `meter`, `steps --break KIND@STEP` | 17 checks |
| `phase02_cost/prune.py` | break-even table and pruning policy simulation | `breakeven`, `sim --keep N --clear-at-least N` | 14 checks |
| `phase02_cost/exact_values.py` | audit of an agent log for exact values a placeholder would hide | `sweep --file F --pattern P` | 7 checks |
| `phase03_compaction/sim.py` | refund world, tools that block wrong calls, a pattern agent, summarizers in several styles | import | 21 checks |
| `phase03_compaction/replay.py` | paired PRE and POST replay, and a monitor for your own logs | `monitor --file F` | 10 checks |
| `phase03_compaction/timing.py` | compaction event cost and rule sweep | `event --context L --summary L_s`, `sweep --rules R ...` | 12 checks |
| `phase04_split/return_check.py` | next-k facts check on sub-agent returns from a plain JSON log | `check --k K --file F` | 14 checks |
| `phase04_split/memory_paths.py` | canonical path check for a client-side memory tool, and nine attacks | `_canonical()`, or run the script | 18 checks |
| `phase04_split/horizon_residual.py` | residual, interval, per-stage terms, trial planning | `from-horizons`, `plan --gamma G`, `run --scenario S` | 20 checks |

Self-test counts for the other scripts:

| Script | Checks | Script | Checks |
|---|---|---|---|
| `effective_length.py` | 31 | `nextk.py` | 9 |
| `poisoned_state.py` | 9 | `stop_probe.py` | 9 |
| `mask_vs_remove.py` | 11 | `split_budget.py` | 20 |
| `handles.py` | 9 | `parallel_writers.py` | 11 |
| `ownership.py` | 12 | `progress_notes.py` | 10 |

All 26 scripts passed on 2026-09-23.

**Log formats that accept your own data.**

- `exact_values.py`: one JSON object per line, `{"step", "role", "text", "tool", "args"}`. Sample: `phase02_cost/sample_trace.jsonl`.
- `replay.py monitor`: `{"step": 12, "call": "refund(ORD-51234, 42.50)", "ok": true}` and `{"step": 12, "event": "compaction"}`. Sample: `phase03_compaction/sample_run.jsonl`.
- `return_check.py`: `{"run", "task", "brief", "results": [...], "returns": {format: text}, "next": [{"tool", "args"}]}`.
- `literal_vs_latent.py audit`: `{"question", "evidence"}`. Sample: `phase01_failure/sample_eval.jsonl`.

**Live exercises.** Two live commands exist. Phase 1 E5 is `find_vs_use.py --live`, estimated at $1.45 on gpt-6-luna. Phase 3 E12 is `stop_probe.py --live`, estimated at $0.05 on gpt-6-luna. Both print their cost and stop until you add `--yes`. Neither was run.

---

## If a later module needs X, link to section Y

| If a later module needs | Link to | What is already there |
|---|---|---|
| Tool restriction and masking | `Module 2, 2.3` | five ways to switch off a tool, their cost, Anthropic `tool_choice` against OpenAI `allowed_tools`, mode tools, `defer_loading` |
| Cache breaks and the cost of a run | `Module 2, 2.1` and `2.2` | quadratic re-reads, `(w − r) × C`, one-time against repeating breaks, two breakpoints, per-step hit-rate alert. Single-request caching is `Module 1, 3.2` and `3.3` |
| Cache lifetime and time as a break | `Module 2, 2.2` | 5-minute and 30-minute lifetimes, slow tools, human pauses |
| Handles and tool output size | `Module 2, 2.4` | `w + r × (H − 1 − k)`, the 12.5-step rule, handle and view, response caps, where a handle loses |
| Pruning and placeholders | `Module 2, 2.5` and `2.6` | the break-even `S > (w − r) / r × A / X`, batch pruning, `clear_at_least`, restorable placeholders, the exact-value audit |
| Compaction and summary checking | `Module 2, 3.2`, `3.3` and `3.4` | next-k, paired replay, the ledger format, symptoms and alerts, event cost, how to choose a rule. Budget zones, trigger and the 400 backstop are `Module 1, 2.6` |
| Transcript ownership, client-held against server-held | `Module 2, 3.1` | which checks each provider mode allows, bytes against billed tokens |
| Stop failures and repeated side effects | `Module 2, 3.3` | the stop probe, plan lines, idempotency keys, a status line |
| Sub-agents and multi-agent cost | `Module 2, 4.1` | equal work, equal tokens and equal dollars, single-clear as the baseline, shared prefixes, the return contract and its check |
| Parallel writers | `Module 2, 4.2` | `a = Σ p_o²`, silent inconsistencies after a clean merge, one writer |
| Memory files and path checks | `Module 2, 4.3` | progress-file failures and fixes, the canonical path check with nine attacks |
| Horizon residual and diagnosis | `Module 2, 4.4` and `4.5` | `Γ`, interval, trial planning, reset against repair, the module map. The first diagnosis path is `Module 2, 1.6` |
| Effective length and eval sweep size | `Module 2, 1.1` | task, scorer and threshold, trial counts |
| Finding against using a fact, evidence-first output | `Module 2, 1.2` | EVIDENCE then ANSWER, quote check, recite then solve |
| Literal against latent questions in an eval | `Module 2, 1.3` | the overlap audit and five steps to write latent questions |
| Step compounding, external checks and retries | `Module 2, 1.4` | `S = p ** H`, `with_retries()`, the recall ceiling |
| Self-conditioning and cleaning failed attempts | `Module 2, 1.5` | three cleaning rules, never a full model rewrite |

---

## What Module 2 explicitly leaves to later modules

| Topic | Owner | Where it is stated |
|---|---|---|
| Tool description design, tool count, selection accuracy | Module 6 | `course.json` `keptOut`, Phase 4 "What stays out" |
| Retrieval into context: chunking, ranking, how much to retrieve | Module 3 | `course.json` `keptOut`, Phase 4 "What stays out" |
| Memory across sessions and users | Module 10 | `course.json` `keptOut`, Phase 4 "What stays out", 4.3 |
| Prompt injection through memory files | Module 16 | `course.json` `keptOut`, 4.3 and `memory_paths.py` |
| Eval statistics for sweeps, and the bootstrap over tasks | Module 11 | `course.json` `keptOut` for the sweep. 4.4 names the bootstrap and does not build it |

Two gaps between `course.json` and the text, verified by grep:

- `keptOut` says Phase 2.3 links to Module 6. Since the 2026-09-23 read-through, the Phase 2 text links Module 6 in 2.3 and 2.4.
- `keptOut` says 4.3 "stops at files the agent writes in one run". The text of 4.3 covers one long job across many sessions. It does not cover memory across separate jobs or users.

## Open questions Module 2 left unchecked

A later module can settle these. Each one is marked "not checked" in the phase text.

1. Whether changing OpenAI's `allowed_tools` set keeps the cached prefix. Section 2.3.
2. Whether Anthropic Managed Agents' `agent.thread_context_compacted` event carries the summary. Section 3.1.
3. Whether a provider's compaction call reads the cache. Section 3.4.
4. Whether a real model ignores a stale plan line. Section 3.3. Live exercise E12 measures it.
5. When a new OpenAI cache entry becomes visible to requests already in flight. Section 4.1.
6. How much of ChainSWE's larger drop with sub-agents came from the return, and how much from the smaller editor model. Section 4.4.
7. Both live exercises, Phase 1 E5 and Phase 3 E12, were never run.

---

## Corrections Module 2 made

Later dossiers must not repeat these errors. The list comes from `course.json` `reviewLog`, dated 2026-09-23. Two rows also use a correction the phase text states itself. Where the old dossier held the error, the dossier line is given.

### Errors that were in the old dossier

| Wrong claim | Correct claim | Where fixed | Evidence |
|---|---|---|---|
| Du et al. used 30K whitespace tokens for the 970 of 1000 result | The filler was essay text | Phase 1, 1.2 | dossier line 79, phase 1 line 164 |
| GPT-4o and Gemini-2.0 scoring 100 at every length is a case where length does not hurt | Du et al. could not measure retrieval for closed models. "Found the fact" is an assumption for them | Phase 1, 1.2 | dossier line 79, phase 1 line 250 |
| Mittal, arXiv 2609.01660, shows step count drives failure, and its compressed arm shows a smaller context fails faster | Rejected as evidence. The compressed arm keeps only self-written state. Its projections do not match its own formula | Phase 1, 1.4 | dossier lines 88, 180 and 298. Phase 1 line 379 cites `runner.py` `_context` |
| A prefix break at step 3 costs full price on every later step | A one-time break is paid once. `(w − r) × C`. Only a repeating break is paid on every step | Phase 2, 2.1 and 2.2 | dossier line 92 |
| Multi-agent systems used about 15 times more tokens | Both the 4× and 15× ratios are relative to chat, not to a single agent at equal work. The 90.2% eval has no published size and no matched-token arm | Phase 4, 4.1 | dossier line 140 |

### Errors in drafts or labs that a later module could repeat

| Wrong claim | Correct claim | Where fixed |
|---|---|---|
| The threshold rule changes the effective length for four of nine models | Five of nine. Re-run here with `effective_length.py rules` | Phase 1, 1.1 |
| A sliding window makes self-conditioning worse | The paper measured that a window helped Gemma3-12B. The simulation cannot model a window | Phase 1, 1.5 |
| The live find-against-use run costs about $0.72 | About $1.45 on gpt-6-luna | `find_vs_use.py` docstring |
| A prefix-cache model that stores every prefix | Providers store entries only at breakpoints, with a 20-position lookback, a lifetime and a minimum. Storing every prefix overstates reads | `common/prefix_cache.py` |
| Per-step masking always costs more | It depends on `(w − r) / r` and the cache rules. The JetBrains saving fits cheaper rewrites. Labelled inferred | Phase 2, 2.5 |
| The quadratic cost of re-reading was missing | Added as concept 2.1 | Phase 2, 2.1 |
| Anthropic tool restriction was treated like OpenAI's | Anthropic has no `allowed_tools`. A `tool_choice` change invalidates the messages cache | Phase 2, 2.3 |
| The exact-value audit counted only agent text | It also counts tool-call arguments | `exact_values.py` |
| ACON and "Less Context" as evidence for placeholders | Not used. Both also drop the agent's own actions | Phase 2, 2.6 |
| Server chaining sends 102.5× fewer bytes | 26.0× fewer at 200 steps. Re-run here | Phase 3, 3.1 |
| Compacting at a sub-task end reduces damage | No measured gain, +0.10 ± 0.37 over 200 seeds. The first result came from a simulator bug with wrong amounts | Phase 3, 3.4 |
| `S` and `C` reused for compaction | Phase 3 uses `L`, `L_s`, `I` and `o` | Phase 3, 3.4 |
| Split and single-clear compared only on tokens | Matched on dollars too. At equal dollars, single-clear is 0.1 points behind | Phase 4, 4.1 |
| Split and single-clear are equal under a length curve | about 2 points apart, 75.1% against 77.3%. A sub-agent carries no lead prefix and no earlier notes | Phase 4, 4.1 |

The review also fixed items without a detailed record in `course.json`. These are the ownership table's repair column and the TRACE and Slipstream descriptions. They also include the live-mode flags, the Phase 4 opening-story ratio and ChainSWE's description. The Phase 3 and Phase 4 entries point to a "review report". No such file is in the course folder. So the details are not checked.

Other fixes were to fixtures, text and tools:

- the history token count, which was 1% short
- question wording in the literal and latent fixture
- a pooled line for misses in place of per-cell intervals
- one piece of evidence per concept, so HELMET moved to References
- a word from the avoid list, replaced in seven places
- a relative-path bug in `audit_phase.py`, worked around and not fixed

### Corrections Module 2 makes to Module 1

Module 2 did not edit Module 1. These are stated in Module 2 and in `course.json` `notesForGeneration`.

1. Module 1, 2.6 cites Mittal for "a smaller context made success fall faster". That arm kept only self-written state. Correct it in Module 1. See `Module 2, 1.4`.
2. Module 1, 2.6 calls the AppWorld study "an August 2026 study". Name it TRACE, arXiv 2608.06503, a preprint. See Phase 3, "A note on Module 1".

### Claims the old dossier corrected, and Module 2 cut

These rules come from the dossier itself, lines 325 to 328, and from `course.json` `cutFromDossier`.

- The "30% accuracy drop" is from LongMemEval, not Chroma. `cutFromDossier` says it would become one line in References. No phase document contains it. Verified by grep for "LongMemEval" and "30%".
- The "5k-20k" and "50k-100k" compaction bands come from a 2025 Claude Cookbook recipe. They are not current advice. Server threshold compaction rejects triggers below 50,000. Phase 3 References keep one line on this.
- Provider feature tables were cut because they change within weeks.
- Benchmark tours were cut because no decision depends on them.
- Context anxiety was cut because it is one model's behaviour, and a later model is reported to have removed it.
- The ACON against TRACE debate was cut. Only its conclusion stays.
- The Self-Compacting Agents numbers were cut, because they were read from the abstract only.

---

## Overlap guidance for later modules

- **Module 3, retrieval.** 1.2 and 1.3 cover find against use and word overlap. Module 3 owns chunking, ranking and how much to retrieve.
- **Module 6, tools and MCP.** 2.3 and 2.4 cover cache-safe tool restriction and tool output size. Module 6 owns tool descriptions, tool count and selection accuracy.
- **Module 7, agent harness.** Link to 1.5 for cleaning and 2.2 for breakpoints. Link to 2.5 for pruning, Phase 3 for compaction and 4.3 for progress files. Do not derive their numbers again.
- **Module 9, orchestration.** 4.1 and 4.2 cover sub-agent cost and parallel writers. The "checkpoint" in 4.4 is a measurement start, not a durable-execution checkpoint.
- **Module 10, memory.** 4.3 covers progress files for one job and the path check. Module 10 owns memory across jobs and users.
- **Modules 11 and 12, evals.** 1.1 sizes a sweep with one interval. 3.2, 3.3 and 4.4 give next-k, replay and the residual. The eval modules own the statistics and the bootstrap.
- **Module 14, cost.** 2.1 to 2.5 and 3.4 price runs, breaks, pruning and compaction per step. Module 14 adds tenants, forecasting and ownership.
- **Module 15, observability.** 2.2 gives the per-step hit-rate alert. 3.3 gives the post-compaction monitor. 4.5 lists three signs in existing logs.
- **Module 16, security.** 4.3 gives the canonical path check only. Module 16 owns prompt injection through memory.

The `_curriculum/README.md` status table still lists Module 2 as "ready". This file does not change it.

Summary: Module 2 shows how to find why a long run failed and how to fix that cause. Link to its sections instead of teaching them again.

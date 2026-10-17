# Module 11 — Eval engineering

Research date: 2026-09-17. Refreshed on 2026-09-23. Section 13 lists every change and correction. Status: research dossier, not course material.

Labels used in this file: **V** is verified, with the source next to it. **C** is computed with Python 3 standard library on the author's laptop, on the date stated. **I** is inferred, and the text names what it was inferred from. **NC** is not checked.

Paths that start with `scratchpad/` are relative to `/private/tmp/claude-502/-Users-raghvendra-dhakar-Desktop-project-code/2ba7cd59-bd20-4d0a-a9d5-98cef39f2fb7/scratchpad/`. The refresh report is `scratchpad/reports/research_eval-engineering_refresh.md`. Its saved sources are in `scratchpad/research_eval-engineering/refresh/`, shortened below to `refresh/`. Sources fetched again for the 2026-09-23 anchor check are in `scratchpad/m11_refresh/src/`, shortened to `src/`.

## 1. What this module is for

An eval is a repeatable test that scores the output of an AI system. This module teaches the learner to build evals that give a trustworthy number for their own product. Without that number, every prompt change, model switch, and retrieval change is a guess. Module 1 made decisions with small eval sets. It did not teach how to find failures, build and check a judge, or size a dataset. Module 3 handed one more topic to this module: the faithfulness of the generated answer. Faithfulness means that every claim in the answer can be inferred from the retrieved text. Source: `retrieval-internals/course.json` line 29, in `keptOut`: "Faithfulness of the generated answer: Modules 11 and 17". **V**, read on 2026-09-23. Public leaderboards cannot replace this work. In 2026 OpenAI stopped reporting one major coding benchmark and then withdrew its advice to use the replacement. The later modules on agents, retrieval, and cost all need an eval gate, so this module comes early in the core path.

## 2. Scope

### In scope

- Error analysis on traces: open coding, axial coding, failure taxonomies, saturation, and criteria drift. A trace is the full record of one request: inputs, tool calls, and output.
- Code-based checks and LLM judges. An LLM judge is a model that scores another model's output.
- Judge design: binary or scale, pointwise or pairwise, reference-based, and rubric-based.
- Judge biases with measured numbers: position, verbosity, and self-preference.
- Judge validation: TPR, TNR, Cohen's kappa, percent agreement, and correction of the measured pass rate.
- Agreement statistics and their limits: kappa and prevalence, Gwet's AC1, Krippendorff's alpha, the alt-test, and the labelling budget.
- Answer faithfulness as a measured rate over an eval set. This covers claim decomposition, checker choice, aggregation rules, refusals, judge validation, and correction of the rate. Claim decomposition means splitting an answer into short, single-fact statements before checking each one.
- Golden datasets: sizing, small-sample intervals, clustered errors, paired tests, and power analysis. A golden dataset is a fixed, labelled set of inputs that every version is scored on.
- Non-determinism: repeated trials, epochs, and the noise floor.
- CI gates and regression suites: thresholds, exit codes, and how to avoid a gate that passes by accident.
- Tooling: promptfoo, Inspect AI, OpenAI Evals, DeepEval, Ragas, Braintrust, LangSmith, Langfuse, and Phoenix.
- Benchmark contamination and broken benchmarks, and why product evals are still needed.

### Out of scope, and where it lives instead

| Topic | Where it lives | Note |
|---|---|---|
| Trajectory and tool-call scoring, with partial credit over steps | Module 12, agent and online evals | Multi-turn |
| pass^k in depth, τ-bench and tau2 | Module 12 | Module 11 keeps only the definition, in 4.7 |
| User simulators and how to validate them | Module 12 | Multi-turn |
| Online evals: sampling production traffic, judge cost times sample rate, A/B tests | Module 12 | Needs live traffic |
| The improvement loop: traces, error analysis, new eval cases, a fix, a re-run | Module 12 | Module 11 teaches each step offline. Module 12 runs the loop |
| Multi-turn faithfulness, where later turns rely on earlier answers | Module 12 | Not researched. **NC** |
| Where the faithfulness gate runs in production: placement, latency, cost, policy | Module 17, guardrails | The audit split: "Module 11 builds the judge, Module 17 places it". `scratchpad/reports/curriculum_audit.md` line 434 |
| Retrieval metrics such as recall@k and nDCG | Module 3, 1.1 and 1.2 | Built |
| Tracing pipelines and dashboards | Module 15, observability | |
| Safety and red-team evals | Module 16 and the guardrails module | |
| Training reward models and RL graders | the post-training elective | |

Module 11 stays offline and single-turn. It owns faithfulness measured on a fixed eval set, and the validation of the faithfulness judge. **I**, from the refresh report, section 8, and the audit split above.

### Overlap with built modules

Rebuilt on 2026-09-23 from `grep '^## '` on the phase files of the built modules. Module 2 is `context-engineering`, Module 3 is `retrieval-internals`, Module 4 is `advanced-retrieval`, and Module 6 is `tools-mcp`. Module 1 rows come from `_curriculum/module-01-coverage.md`, because Module 1 is not in the grep set. Line numbers are the heading lines, unless the row names a text line.

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| Gating a model swap in four steps | Module 1, 3.4 "Gating the swap" | The full method: find failures first, then build and validate the scorer |
| Position bias fix by swapping order | Module 1, 3.4 step 3 | Measured bias sizes across judges, plus verbosity and self-preference |
| Paired bootstrap and "decide on the worst end" | Module 1, 4.4, `quant_gate.py` | When the bootstrap fails at small N, Wilson and Bayesian intervals, McNemar |
| Judge agreement 85% vs human 81% | Module 1, 5.4 | The with-ties numbers, chance-corrected metrics, and the wider literature |
| Noise floor and the 1,000-question figure | Module 1, 5.5 "Your noise floor" | The assumptions behind 1,000, clustered errors, and paired designs that need fewer items |
| Temperature 0 is not deterministic | Module 1, 1.5 and 5.5 | Epochs, reducers, and the Anthropic temperature deprecation |
| Slice-first triage | Module 1, 6.3, `incident_drill.py` | Failure taxonomies that define the slices before an incident |
| Wilson interval on one share, and trials needed to see a drop | Module 2, "1.1 — Effective length belongs to the task and the scorer", `context-engineering-phase-01-why-long-runs-fail.md` line 55. Wilson at line 132. Code: `context-engineering/code/common/stats.py` with `wilson`, `halfwidth`, `smallest_drop`, `trials_for` | Link it. Add Clopper-Pearson and Beta intervals and the coverage failure at small N, 4.6 |
| Literal against latent questions in an eval set | Module 2, "1.3 — Literal overlap hides the loss", line 277 | Link it when building a golden set. Do not re-teach |
| A judge call that accepts a summary at 7 of 10 | Module 2, "3.2 — Judge a summary by the next steps, not by reading it", `context-engineering-phase-03-compaction.md` line 191 | Module 2 uses a judge. It does not validate one. Module 11 adds TPR, TNR and the corrected rate, 4.4 |
| Paired randomization test, and the unpaired test as the wrong choice. Holm correction over slices | Module 3, "1.4 — Averages hide the slice that fails", `retrieval-internals-phase-01-measure.md` line 407. Holm at line 488 | Link `paired_test` and `holm`. Add McNemar for binary pass or fail, and its sample size, 4.6 |
| Bootstrap interval of a mean, queries needed, "no significant difference is not a tie" | Module 3, "1.5 — Size the label set before you trust a result", line 548. `queries_needed` at line 575 | Link `bootstrap_ci` and `queries_needed`. Add clustered standard errors and power for binary rates, 4.6 |
| Label holes, pool bias, `judged@10` | Module 3, "1.3 — A benchmark does not predict your corpus", line 313. Line 390 hands "judges, agreement between labellers" to Module 11 | Labeller agreement, kappa, AC1 and the alt-test, 4.14 and 4.15 |
| Switching behind an eval gate | Module 3, "7.5 — Switch behind a dual index and an eval gate", `retrieval-internals-phase-07-freshness.md` line 591 | A gate on the lower end of the interval, exit codes, skipped required checks, 4.8 |
| The gold labels are a second author of the score. The match rule moves every score | Module 4, "1.3 — A text-to-SQL score also measures the gold labels" line 318, and "1.4 — Execution accuracy is a match rule you choose" line 453, `advanced-retrieval-phase-01-query-picks-tool.md` | Link as the worked example of a scorer choice. Do not re-teach SQL scoring |
| Thresholds tuned on the reported questions look better than they are | Module 4, "3.5 — Prove a gate against four rows", `advanced-retrieval-phase-03-retrieve-or-not.md` line 546 | Apply the same rule to judge thresholds: tune on a separate labelled split, 4.12 |
| Position bias in judged win rates, one paragraph that points to Module 11 | Module 4, "5.1 — A graph "win" is only as strong as its baseline", `advanced-retrieval-phase-05-entity-graphs.md` line 68, text at line 132 | Measured bias sizes by judge model, 4.3 |
| McNemar's test, defined in one sentence and used as cited evidence | Module 4, `advanced-retrieval-phase-02-no-index.md` lines 57 and 364, inside "2.3 — Quality splits by model and task: test, then route" line 335 | Teach McNemar and its sample size, 4.6 |
| A citation proves a pointer, not support | Module 4, "6.5 — A citation proves a pointer, not support", `advanced-retrieval-phase-06-caches-grounding.md` line 500 | Do not repeat |
| NLI and MiniCheck checkers, premise choice, TPR and TNR of the checker, threshold by cost, edits that checkers miss | Module 4, "6.6 — A grounding checker trades recall for precision", line 589. `grounding_gate.py` | Turn the gate on one answer into a rate over a set, 4.10 to 4.13. Reuse Module 4's cached checker scores in labs F1 to F5 |
| Cohen's kappa, defined once for a scanner study | Module 6, "5.4 — A scanner flag is not a verdict", `tools-mcp-phase-05-mcp-trust.md` line 485, text at line 497 | Kappa's prevalence problem and AC1, 4.14 |

Term counts on 2026-09-23, `grep -c -i` over all phase files of Modules 2, 3, 4 and 6 in that order: Holm 0, 85, 119, 0. Wilson 1, 0, 0, 0. McNemar 0, 0, 3, 0. Clopper 0, 0, 0, 0. Rogan 0, 0, 0, 0. "open coding" or "axial" 0, 0, 0, 0. Self-preference 0, 0, 0, 0. pass^k 0, 0, 0, 0. Contamination 0, 0, 0, 0. "clustered" 0, 1, 0, 0, and the one hit is an IVF corpus flag in Module 3, line 882 of `retrieval-internals-phase-02-indexes.md`. **V**. The audit counted 80 Holm mentions in Module 3. Today's count is 85, and Module 4 adds 119.

#### What Module 11 teaches that Modules 2, 3 and 4 do not

1. **Error analysis on traces.** Open coding, axial coding, saturation and criteria drift. 0 hits in Modules 2 to 4.
2. **Judge design and measured judge biases.** Protocol choice, position, verbosity and self-preference by judge model. Module 4 5.1 has one paragraph on position bias.
3. **Judge validation.** TPR and TNR of a judge with intervals, the corrected pass rate, PPI, kappa and AC1, the alt-test, and the labelling budget. Module 4 6.6 reports TPR and TNR of a checker used as a gate. It does not correct a rate or validate a judge against human labels.
4. **Faithfulness as a measured rate.** The claim splitter, the checker, the aggregation rule, refusals, and the corrected rate with an interval. Module 4 teaches the checker as a gate on single answers.
5. **Statistics for binary pass rates.** Clopper-Pearson and Beta intervals, coverage at small N, clustered standard errors, and McNemar with its sample size. Module 2 gives one Wilson interval. Module 3 tests means of continuous per-query scores.
6. **Non-determinism.** Epochs, reducers, the pass^k definition, and infrastructure noise.
7. **CI gates.** Exit codes of eval tools, a gate on the interval, and a skipped job that passes a required check.
8. **Benchmark contamination and broken benchmarks.**

Phase 5 of this module is marked "extends Module 3". It links Module 3's `paired_test`, `holm`, `bootstrap_ci` and `queries_needed`, and Module 2's `wilson`. It does not re-teach them. This follows the audit, `scratchpad/reports/curriculum_audit.md` line 209.

**Correction to Module 1, section 5.4.** Module 1 states 85% judge-human agreement and 81% human-human agreement without the condition. Those are setup S2 numbers, which drop ties. With ties, the same paper reports 66% and 63%. Source: Zheng et al. 2023, Table 5. **V**, text re-checked in the PDF on 2026-09-17. Module 1 REVIEW.md already flagged this.

## 3. What changed recently

| Change | Date | Source | Why it matters |
|---|---|---|---|
| Promptfoo agreed to be acquired by OpenAI and says it "will remain open source" | 2026-03-09 | promptfoo.dev blog | The most common open CLI eval runner now has a new owner. Closing status NC. |
| OpenAI deprecated its hosted Evals platform. Read-only on 2026-10-31, shutdown on 2026-11-30 | 2026-06-03 | OpenAI deprecations page | Do not build labs on the OpenAI Evals API. OpenAI's migration guide points to Promptfoo. |
| ClickHouse acquired Langfuse. Langfuse says "There are no planned changes to licensing." | 2026-01-16 | ClickHouse blog, Langfuse blog | Self-hosted tracing and eval store has a new owner. |
| OpenAI stopped reporting SWE-bench Verified. It found material issues in 59.4% of 138 audited problems | 2026-02-23 | OpenAI blog, read in a browser | A famous benchmark lost its signal. |
| OpenAI retracted its advice to adopt SWE-Bench Pro and estimated about 30% of its tasks are broken | 2026-07-08 | OpenAI blog, read in a browser | The replacement benchmark had the same problem within months. |
| Anthropic: models after Claude Opus 4.6 reject temperature values other than 1.0 | current API reference | Anthropic Messages API reference | "Set temperature to 0 for evals" is no longer possible on those models. Use repeated trials. |
| Anthropic published "Demystifying evals for AI agents" and "Quantifying infrastructure noise" | 2026-01-09, 2026-02-05 | Anthropic Engineering | First-party sizing advice and a measured 6-point infrastructure effect. |
| Bowyer et al. position paper: do not use CLT intervals under a few hundred items | ICML 2025 | arXiv 2503.01747 | Most product golden sets are in this size range. |
| Ragas v0.4 replaced `evaluate()` with `@experiment()` | 2025-12-03 | Ragas migration guide | Older Ragas tutorials no longer match the API. |
| DeepEval v4.2.0 inverted four metric scales so that higher is better | 2026 | DeepEval changelog | Existing CI thresholds on those metrics now mean the opposite. |
| Shankar and Husain book "Evals for AI Engineers" listed by O'Reilly for 31 Oct 2026 | not released yet | Google Books | Not citable as a source yet. Not re-checked on 2026-09-23. |
| Husain and Shankar FAQ modified again. It adds "Continue past 100 while you are still learning" | 2026-09-21 | `refresh/pages/hamel_faq.html`, `dateModified` | Quote the FAQ with its date. It changes often. |
| Anthropic now marks `temperature` "Deprecated" for models after Claude Opus 4.6. Only 1.0 is accepted. `top_k` is deprecated for the same models | current API reference, read 2026-09-23 | `refresh/pages/anth_messages.txt` | Repeated trials are the only option on these models. |
| LangSmith SDK 0.13.0 and 0.14.0. 0.13.0 adds `disable_evaluator_tracing` to `evaluate()` and `aevaluate()` | 2026-09-18 and 2026-09-21 | `refresh/pages/langsmith_releases.json` | Two minor versions in 5 days. Pin exactly. |
| promptfoo 0.123.1. Exit-code logic unchanged | 2026-09-18 | npm registry, source at the tag | Lab L13 pins 0.123.1. |
| Inspect AI 0.3.268 adds a `collect` reducer. DeepEval 4.2.5, Braintrust 0.42.0 | 2026-09-22 | PyPI JSON, `refresh/pypi/versions_2026-09-23.txt` | Section 9 re-pinned. |
| An unrelated package took the PyPI name `minicheck`. Its summary is "An explicit-state model checker in ~2900 lines" | 2026-07-30 | `refresh/pypi/minicheck.json` | `pip install minicheck` installs the wrong tool. Module 4 already warns about it, `advanced-retrieval-phase-06-caches-grounding.md` line 744. |
| DeepEval faithfulness scores an answer with no claims as 1.0. Ragas 0.4.3 scores it NaN | DeepEval `main` read 2026-09-23. Ragas tag v0.4.3 | `refresh/pages/de_score_src.py`, `refresh/pages/ragas_coll_faith_043.py` | Switching tools changes how refusals count, 4.13. |
| New faithfulness-evaluation evidence: FaithJudge at EMNLP 2025 Industry, the TREC 2024 RAG support study at SIGIR 2025, Guerdan et al. at NeurIPS 2025, Decomposition Dilemmas at NAACL 2025 | 2025 | arXiv abs pages | The evidence base on faithfulness judges is now from 2025, not only 2023. |
| Ragas 0.4.3 is still the latest release | 2026-01-13, no release in 8 months | PyPI JSON | Low release activity. The repository is under `vibrantlabsai`. |

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Concepts 4.1 to 4.9 are from 2026-09-17, with the corrections in section 13. Concepts 4.10 to 4.15 are new on 2026-09-23. Their sources are in the refresh report. On 2026-09-23 the anchor numbers of this section were grepped again in saved files. Section 13, "Anchor re-check", gives the count and the few facts not re-grepped.

### 4.1 Metrics chosen before error analysis measure generic failures, not the product's failures

Error analysis means reading real traces and writing down what went wrong before choosing any metric. Open coding is writing free-text notes on each trace. Axial coding is grouping those notes into a failure taxonomy, which is a named list of failure types. The metrics then follow from the taxonomy, not from a list of generic metrics.

- Hamel Husain and Shreya Shankar define open coding on their evals FAQ. The page's `dateModified` was 2026-09-13 on 2026-09-17 and is 2026-09-21 on 2026-09-23. `refresh/pages/hamel_faq.txt`. Annotators "review and write open-ended notes about traces, noting any issues." **V**
- The same page says "Axial coding is the most important step." **V**
- Stopping rule: continue until "theoretical saturation", and "We recommend reviewing at least 100 traces." **V**. The 2026-09-21 version adds "Continue past 100 while you are still learning." **V**. This is practitioner advice, not a measured result.
- The page says "Start by annotating at least 30 traces yourself before reviewing suggestions from an agent." **V**
- "Benevolent dictator": the FAQ says a single domain expert is "the most effective approach" for "most small to medium-sized companies". **V**. Opinion, not measured.
- Criteria drift: Shankar et al., "Who Validates the Validators?", UIST 2024, found that grading outputs changes the criteria people use. The study had n=9 practitioners. **V**, Section 1 and Section 6. The small n limits how far this generalises.
- In the same paper, EvalGen reached 66.46% alignment on a 100-item product pipeline, against 54.35% for SPADE. Alignment is the paper's harmonic mean of coverage and false failure rate. On the 84-item medical pipeline, both reached 48.29%. Source: Table 1. **V**

### 4.2 Pairwise judging gives fewer ties but flips more under distractors. Absolute scoring resists distractors only for some judge types

A judge is defined by its question format and its output format. Pointwise judges score one output. Pairwise judges pick the better of two outputs. Reference-based judges compare the output with a known good answer. The research shows a trade-off: pairwise is more sensitive but easier to fool.

- Binary pass/fail is recommended by Husain and Shankar. Their reasons: adjacent scale points are subjective, scales need larger samples, and raters default to the middle. Source: evals FAQ. **V** that they say it. The page cites no study.
- No primary study was found that compares binary labels with a Likert scale for judge-human agreement. **NC**, absence from one search.
- Li et al. 2026, arXiv 2601.03444, compared 0-5, 0-10, and 0-100 scales. Pooled human-LLM ICC was 0.853, 0.805, and 0.840. Conditions: 12 graduate raters, 6 LLMs, 6 benchmarks, temperature 1. Source: Table 2. **V**. No venue listed.
- Tripathi et al., COLM 2025, measured how often an added distractor flips the verdict on MT-Bench. The three distractors were assertiveness, prolixity and sycophancy. The paper groups its judges by output type. Averaged over the four open models in the "Logit-based outputs" group, absolute scoring flipped 9.0% to 9.7% of cases. Pairwise flipped 34.9% to 35.5%. Each range spans the three distractors. Source: Table 2. **V**, `refresh/pdf/2504.14716.txt`.
- The same table has a "Text-based outputs" group with two reasoning models. Under absolute scoring, o4-mini flipped 17.2% to 25.33% and o3-mini flipped 21.3% to 25.7%. Under pairwise, o4-mini flipped 29.4% to 44.0% and o3-mini 30.0% to 40.6%. **V**, Table 2. So "absolute scoring is robust" holds for the four open logit-based judges. It does not hold for these two text-output judges. Name the judge type when citing this paper.
- The cost of absolute scoring in the same paper: 84.6% to 93.2% ties on equal-quality pairs, against 2.4% to 7.3% for pairwise. Source: Table 3. **V**, re-grepped 2026-09-23.

### 4.3 A judge bias measured on one judge model does not transfer to another judge model

A bias is a systematic error that does not depend on answer quality. The three best-measured biases are position, verbosity, and self-preference. Their size depends strongly on the judge model.

- **Position, older judges.** Zheng et al. 2023, Table 2. 80 MT-Bench questions, two similar GPT-3.5 answers, both orders. Consistency: Claude-v1 23.8%, GPT-3.5 46.2%, GPT-4 65.0%. **V**
- **Position, extreme case.** Wang et al., ACL 2024, Table 2. ChatGPT judging Vicuna-13B against ChatGPT on 80 questions: the verdict conflicted after a swap in 66 of 80 cases, 82.5%. With GPT-4 as judge: 46.3%. **V**
- **Position, newer judges.** Shi et al., AACL-IJCNLP 2025, Table 2. Pairwise position consistency on MTBench: GPT-4 0.82, Claude-3.5-Sonnet 0.82, GPT-4o 0.76, Claude-3-Haiku 0.57. On DevBench, Claude-3-Haiku fell to 0.23. **V**. The paper says bias is "strongly affected by the quality gap between solutions". **V**
- **Verbosity.** Zheng et al., Table 3, "repetitive list" attack on 23 answers. Failure rate: Claude-v1 91.3%, GPT-3.5 91.3%, GPT-4 8.7%. **V**
- **Self-preference.** Zheng et al., Section 3.3: GPT-4 favoured itself by a 10% higher win rate, Claude-v1 by 25%. The authors say the study "cannot determine" whether this is a real bias. **V**
- Panickssery et al., NeurIPS 2024: GPT-4 was 73.5% accurate at recognising its own summaries. Self-recognition and self-preference correlated linearly. Conditions: XSUM and CNN/DailyMail, 1,000 articles each. **V**, Section 1, Figures 1 and 7.
- Wataoka et al., NeurIPS 2024 workshop: GPT-4 had a self-preference score of 0.520, the highest of 8 judges, on Chatbot Arena data. The paper links the bias to lower perplexity. **V**, Section 4.
- The Husain and Shankar FAQ says a same-model judge "is usually fine". See section 10 for this disagreement.
- **Judges fail on hard objective pairs.** JudgeBench, Tan et al., ICLR 2025, Table 1: vanilla GPT-4o scored 50.86% on 350 pairs, where random is 50%. Table 2: with the Arena-Hard judge prompt, o3-mini high scored 80.86%. **V** (corrected 2026-09-25 by the coherence pass: the o3-mini value is in Table 2, not Table 1). The pairs were generated by GPT-4o, and the authors say this biases against GPT-4o judges. **V**

### 4.4 Percent agreement does not validate a judge. TPR and TNR on held-out labels do, and they correct the pass rate

A judge is itself a classifier, so it needs a labelled test set. TPR is the share of truly passing outputs that the judge passes. TNR is the share of truly failing outputs that the judge fails. Percent agreement is inflated by chance, so use a chance-corrected metric such as Cohen's kappa, and report TPR and TNR separately.

- The FAQ says: "Focus on achieving high True Positive Rate (TPR) and True Negative Rate (TNR) with your judge on a held out labeled test set." **V**
- **MT-Bench agreement is percent agreement, not correlation.** Zheng et al., Table 5. GPT-4 pairwise vs human, turn 1: 66% with ties, n=1343, and 85% without ties, n=859. Human vs human: 63% and 81%. Chatbot Arena, Table 6: 64% and 87%. Conditions: 58 expert labelers, about 3K votes. **V**
- **Percent agreement hides disagreement.** Thakur et al., GEM 2025: Llama-3 8B had Scott's pi of 59 while its percent agreement was above 80%. Conditions: TriviaQA, 13 judges, 1,200 human-labelled answers. **V**
- **Kappa example.** Wang et al., Table 4: vanilla GPT-4 reached kappa 0.24 against the majority of 3 annotators. With the paper's calibration and 20% human review, kappa was 0.56. The average single human reached 0.54. **V**
- **Correction of the measured pass rate.** The Rogan-Gladen estimator is θ = (p_obs + TNR − 1) / (TPR + TNR − 1). The `judgy` library by Shreya Shankar implements it, version 0.1.0, uploaded 2025-05-25. **V**, README and PyPI JSON.
- `judgy` source: it raises an error when TPR + TNR ≤ 1, and its bootstrap resamples only the labelled test set. So its interval ignores sampling error in the unlabelled set. Source: `src/judgy/core.py` lines 106 to 152, read at `main`, not at a tag. Re-read at `main` on 2026-09-23: the error message is at line 113 and the test-set resample at lines 126 and 127. `src/judgy_core.py`. **V** for main. **I** that 0.1.0 matches.
- Worked example, **C**, re-run 2026-09-23 in `scratchpad/m11_refresh/recheck_out_2026-09-23.txt`: TPR 0.9, TNR 0.8, observed pass rate 0.70 gives a corrected rate of 0.714.
- Lee et al., arXiv 2511.21140, ICML 2026, give intervals that include error from both the test and calibration sets. Coverage was 95% to 99% with a GPT-4.1-mini judge and a 10% calibration split. Source: Table 1. **V**. Venue: the arXiv journal reference reads "International Conference on Machine Learning (ICML) 2026" (added 2026-09-25 by the coherence pass).
- Fiedler 2026, arXiv 2605.06939, cites two earlier papers in its Section 2, Related work. As cited by Fiedler, Greiner 2003 showed the corrected estimate "can have higher mean squared error than the naive estimate". As cited by Fiedler, Lang and Reiczigel 2014 showed its variance grows as 1/J², where J = TPR + TNR − 1. **V**, Section 2 (corrected 2026-09-25 by the coherence pass: the citations are in Section 2, not Section 1). So a weak judge makes the correction noisy.

### 4.5 Judges agree with humans at 0.6 to 0.85 only on tasks with clear criteria, not on most tasks

**Verdict: partly supported.** The range fits strong judges on well-defined tasks. It does not fit "most tasks".

| Evidence | Metric | Value | Conditions | Label |
|---|---|---|---|---|
| JUDGE-BENCH, Bavaresco et al., ACL 2025, Table 1 | mean Spearman, graded labels | GPT-4o 0.50 ±0.21 across datasets, others 0.30 to 0.44 | 11 LLMs, 20 datasets | V. The ±0.21 was read on 2026-09-23 |
| JUDGE-BENCH, Table 1 | mean Cohen's kappa, categorical | GPT-4o 0.28, others 0.10 to 0.28 | same | V |
| JUDGE-BENCH, GPT-4o per dataset | Spearman | 0.82 ROSCOE-GSM8K, 0.35 SummEval, 0.17 WMT23 Zh-En | same | V |
| JUDGE-BENCH, GPT-4o per dataset | kappa | 0.84 LLMBar-natural, −0.24 DICES-990 | same | V |
| G-Eval, Liu et al., EMNLP 2023, Table 1 | Spearman | 0.514 average on SummEval | GPT-4 judge | V |
| G-Eval, Table 3 | Pearson | 0.599 average on QAGS | GPT-4 judge | V |
| Chiang and Lee, ACL 2023, Table 2 | Kendall tau | 0.12 to 0.43 | text-davinci-003, 400 stories, 3 teachers | V |
| Li et al. 2026, Table 4(b) | ICC | 0.596 to 0.816 per model | 0-5 scale | V |

- Correct phrasing for the course: strong judges reach about 0.6 to 0.85 on tasks with clear criteria. On subjective, safety, or expert-labelled tasks, values often fall to 0.2 to 0.5 or lower. Validate your own judge. **I**, from the table above.

### 4.6 A small golden set gives a wider interval than the CLT says, and a paired design needs fewer items

The width of the confidence interval decides what change a dataset can detect. Small sets need exact or Bayesian intervals. Comparing two versions on the same items needs a paired test. A power analysis tells you the dataset size before you build it.

- Miller, "Adding Error Bars to Evals", Anthropic, arXiv 2411.00640, gives five recommendations: CLT standard errors, clustered standard errors, resampling answers, paired differences, and power analysis. **V**, Section 1.
- Clustered standard errors were up to 3.05 times the naive ones on DROP, 1.88 on MGSM, and 1.10 on RACE-H. Source: Table 4. **V**. A cluster is a group of related questions, such as several questions on one document.
- The "at least 1,000 questions" figure uses Eq. 9 with ω² = 1/9, σ² = 0, δ = 0.03, 80% power, α = 0.05. It gives n ≈ 969. **V**, Section 5. ω² = 1/9 comes from a toy model with continuous scores. **V**
- Module 3, 1.4 and 1.5, already teaches the paired randomization test, Holm and the bootstrap for continuous per-query scores. This concept adds binary pass rates. See the overlap table in section 2.
- For a binary pass rate the numbers are larger. **C**, re-run 2026-09-23: 85% to 82% with two independent samples needs 2,402 items per arm. 50% to 47% needs 4,356 per arm.
- Paired designs need fewer items, **C**, McNemar sample-size approximation, re-run 2026-09-23:
  - 5-point drop from 85%, discordance 0.10: 312 items. Independent samples: 906 per arm.
  - 10-point drop, discordance 0.20: 155 items. Independent samples: 250 per arm.
  - 3-point drop, discordance 0.10: 870 items.
  - Discordance is the share of items where the two versions disagree. It must be estimated from a pilot run.
  - A Monte Carlo check with the exact test gave 77% to 80% power, slightly below the 80% target.
- Bowyer et al., ICML 2025: at N=100, a nominal 95% CLT interval covered the true value only 92.5% of the time. They recommend Wilson or Beta-Bernoulli intervals for single pass rates, and Bayesian methods for paired and clustered data. **V**, Section 3.1, text re-checked in the PDF. They say they do not imply a hard threshold N.
- Worked example, **C**, re-run 2026-09-23: 18 of 20 passes. The CLT interval is 0.769 to 1.031, which goes above 1. The Wilson interval is 0.699 to 0.972.
- Miller calls the bootstrap "unnecessary" for large evals. Bowyer finds that both CLT and bootstrap fail at small N. **V**. They studied different sizes. See section 10.
- Sizing advice from vendors: Anthropic says "20-50 simple tasks drawn from real failures is a great start" for early agent work, where effects are large. **V**, Demystifying evals. Anthropic's develop-tests page says "Prioritize volume over quality". **V**

### 4.7 Temperature 0 does not make an eval repeatable. Repeated trials with a stated reducer do

A flaky eval gives different results on the same code. The causes are sampling, server-side batching, and infrastructure. The fix is repeated trials with a stated reducer, not a lower temperature.

- Thinking Machines Lab, Horace He, 2025-09-10: Qwen3-235B-A22B-Instruct-2507, temperature 0, 1,000 completions of 1,000 tokens, gave "80 unique completions". With batch-invariant kernels, "all of our 1000 completions are identical". **V**. Already in Module 1, 5.5.
- Atil et al. 2024, arXiv 2408.04667 v5: GPT-4o few-shot on college math at temperature 0 and a fixed seed, 10 runs. In Table 2, 88.0 counts an item correct if any run got it right, 69.0 is the median, and 44.0 counts it correct only if every run did. These are reducers, not the best and worst single runs. The paper reports "5-15% differences on some tasks" between single runs. **V**, Table 2. Preprint. Corrected 2026-09-23 by the Phase 6 writer.
- Anthropic's API reference says results at temperature 0.0 "will not be fully deterministic." **V**
- The same page says: "Models released after Claude Opus 4.6 do not support setting temperature. A value of 1.0 will be accepted for backwards compatibility, all other values will be rejected with a 400 error." The parameter is now marked "Deprecated", and `top_k` is deprecated for the same models. **V**, `refresh/pages/anth_messages.txt`, read 2026-09-23.
- Inspect AI 0.3.268 runs repeated trials with `epochs`. The default reducer is `mean`: "defaults to \"mean\"", `src/inspect_ai/_eval/task/epochs.py` lines 9 to 26 at 0.3.268. Other reducers are `mode`, `majority`, `median`, `max`, `at_least`, `pass_at`, and `pass_k`. 0.3.268 adds `collect` at line 304. **V**, `refresh/pages/inspect_reducer_268.py` and `refresh/pages/insp_epochs.py`. The 2026-09-17 check was at 0.3.264.
- pass^k is "the chance that all k i.i.d. task trials are successful, averaged across tasks". Source: τ-bench, Yao et al., Sierra, arXiv 2406.12045. **V**. On τ-retail, gpt-4o pass^1 was 61.2 and pass^8 was below 25%. **V**, Table 2 and Section 5.1. Module 12 teaches this in depth.
- Infrastructure noise: Anthropic measured a 6 percentage point gap on Terminal-Bench 2.0 between the most and least resourced setups, p < 0.01. **V**, Anthropic Engineering, 2026-02-05.
- Two variance papers measure something else. Madaan et al., Meta, arXiv 2406.10229, and Heineman et al., AI2, arXiv 2508.13144, measure variance across training seeds and training checkpoints. **V**, abstracts, `refresh/pdf/2406.10229.txt` and `refresh/pdf/2508.13144.txt`. That is not the variance of repeated eval runs on one fixed model. Do not cite them for "run the eval several times". Miller, Atil and Thinking Machines above cover sampling variance.
- Judge prompts add their own variance, **I**. Sclar et al., ICLR 2024, found "up to 76 accuracy points" from prompt format on LLaMA-2-13B, few-shot. Mizrahi et al., TACL, found template changes move results "both absolute and relative" over 20 LLMs and 39 tasks. **V**, abstracts. Both measured the model under test, not a judge. Transfer to judges is **I**. Lab S3 measures it for a checker.

### 4.8 A CI gate passes by accident unless it decides on the interval and fails when the eval does not run

A CI gate is a check that blocks a merge when the eval result is too low. A regression suite is the set of cases that must keep passing. The gate must decide on an interval, not a point estimate, and it must fail when the eval does not run.

- promptfoo 0.123.1 exits with code 100 when a test fails or the pass rate is below `PROMPTFOO_PASS_RATE_THRESHOLD`, default 100. `PROMPTFOO_FAILED_TEST_EXIT_CODE`, default 100, changes the exit code. Source: `src/node/doEval.ts` lines 1290 to 1304 at tag 0.123.1, `refresh/pages/promptfoo_doEval_1231.ts`. **V**. The 2026-09-17 check was at 0.123.0, lines 1290 to 1305.
- promptfoo's CI docs show `eval --fail-on-error`, but the option is not defined in `src/commands/eval.ts` at 0.123.0 or at 0.123.1. A grep of `refresh/pages/promptfoo_evalcmd_1231.ts` returns 0 hits. **V** for the absence. **I** that the command errors. Run it to confirm.
- Inspect AI: `--fail-on-error` is about sample errors, not scores. `inspect eval-set` exits 0 or 1 based on completion. No score-threshold flag was found. **I**, from `_cli/eval.py` at 0.3.264. A gate needs a script that reads the log.
- Inspect AI is the only checked tool that attaches `stderr()` to built-in scorers by default. **V**, `_metrics/std.py` at the tag. `stderr` is still defined in `_metrics/std.py` at 0.3.268, `src/insp_std.py`. The default attachment was not re-checked at 0.3.268. **NC**. promptfoo, DeepEval, Braintrust, and LangSmith docs do not mention confidence intervals. **V**
- DeepEval 4.2.3: `deepeval test run` returns pytest's exit code. Metric threshold default is 0.5. **V** at 4.2.3. Not re-checked at 4.2.5.
- Braintrust: `bt eval` returns non-zero only "if any eval throws an exception". A score gate needs a custom `Reporter`. **V**, run-in-ci docs.
- GitHub required checks "must have a successful , skipped , or neutral status". **V**. GitHub's "Troubleshooting required status checks" page separates two cases. A workflow skipped by a path filter stays "Pending" and blocks the merge. A job skipped by an `if:` condition reports "Success" and passes the gate. **V**, corrected 2026-09-23 by the Phase 6 writer. The old text had the path-filter case reversed.

### 4.9 A public benchmark score does not predict product quality, because benchmarks leak, break, and measure another task mix

Contamination means test items leaked into training data. A contaminated or broken benchmark rewards memory, not skill. Public benchmarks also measure a different task distribution from a support product.

- GSM1k, Zhang et al., Scale AI, NeurIPS 2024: accuracy "drops of up to 8%" from GSM8k to a fresh 1,205-problem set. Yi-6B-Chat fell from 0.437 to 0.357. The paper says Gemini, GPT, and Claude "show little to no signs of overfitting". **V**, Appendix F and Section 5.2.
- LiveBench, ICLR 2025, replaces 1/6 of questions each update, so it refreshes about every 6 months. **V**, Section 2.7.
- The Leaderboard Illusion, Cohere Labs and others, preprint 2025: Meta tested 27 private variants before the Llama 4 release. Training on Arena data raised ArenaHard win rate from 23.5% to 49.9%. **V**, abstract and Section 1.
- OpenAI evaluation best practices list "Vibe-based evals" and eval sets that do not "reproduce production traffic patterns" as anti-patterns. **V**
- Anthropic's develop-tests page: "Design evals that mirror your real-world task distribution." **V**

### 4.10 A faithfulness score belongs to the claim splitter and the checker, not only to the answer

Two teams that score the same answers with different claim splitting or checker settings get different numbers. A checker is any scorer that decides whether a claim is supported: an NLI model, a trained fact-checker, or an LLM judge. NLI, natural language inference, labels a premise and a hypothesis as entailment, neutral or contradiction.

- Best evidence: FActScore, Min et al., UW, UMass Amherst, AI2 and Meta, EMNLP 2023, Table 3. The same estimator, Inst-LLaMA with retrieval and the NP filter, was measured against human FActScore on biographies. Its error was 1.4 and 0.4 points for two subject models and 9.9 points for PerplexityAI. Human FActScore for PerplexityAI is 71.5 and the estimate is 61.6. **V**, `refresh/pdf/2305.14251.txt`. 71.5 − 61.6 = 9.9, **C**. The abstract calls this "less than a 2% error rate".
- The error rate in FActScore compares aggregate scores. An "Always Random" evaluator had an error of 7.5 and 8.3 on two of the three subjects. **V**, Table 3. So a small aggregate error can come from errors that cancel.
- Wanner et al., Johns Hopkins, arXiv preprint: FActScore "is sensitive to the decomposition method used". **V**, abstract, `refresh/pdf/2403.11903.txt`. The spread is in Figure 2, and its values were not read. **NC**.
- Hu et al., NTU, NAACL 2025, report "a trade-off between accuracy gains and the noise introduced through decomposition". **V**, abstract, `refresh/pdf/2411.02400.txt`.
- The disagreement: MiniCheck, UT Austin and Salesforce AI Research, EMNLP 2024, says splitting into atomic facts "is not necessary to achieve this high performance" for its trained checker. **V**, Section 1, `refresh/pdf/2404.10774.txt`. So claim splitting helps some checkers and not others. When it helps is **I**: long multi-fact sentences and a checker trained on short hypotheses.

What the learner gets wrong: reporting "faithfulness 0.91" without naming the splitter, the checker, the premise, and the aggregation rule.

### 4.11 Published judge-human agreement on faithfulness depends on how hard the test items are

Reported values range from 0.95 to about 0.5 for the same task type. The metrics differ, so the numbers are not on one scale. The largest driver is how the test items were chosen. That driver is **I**, from the item-selection methods below.

| Evidence | Metric | Value | Conditions | Label |
|---|---|---|---|---|
| Ragas, Es et al., arXiv preprint, no venue in Comments | pairwise accuracy vs humans | 0.95 | WikiEval, 50 Wikipedia pages, gpt-3.5-turbo-16k. The unfaithful answer was generated "without access to any additional context" | V, Table 1 and Section 4, `refresh/pdf/2309.15217.txt` |
| FaithBench, Bao et al., Vectara and others, arXiv preprint | accuracy | "near 50%" for the best detectors | Summaries chosen because popular detectors, GPT-4o among them, disagreed | V, abstract and Section 2, `refresh/pdf/2410.13210.txt` |
| TREC 2024 RAG Track support study, Thakur et al., Waterloo, Snowflake and Microsoft, SIGIR 2025 short | exact match on three support levels, GPT-4o vs NIST assessor | 56% from scratch, 22 topics. 72% when humans post-edited GPT-4o labels, 14 topics | 45 runs, 36 topics in total | V, abstract and Sections 5 and 6, `refresh/pdf/2504.15205.txt` |
| FaithJudge, Tamber et al., Vectara, EMNLP 2025 Industry | balanced accuracy on FaithBench | 84% with human-labelled examples in the prompt, o3-mini-high. 68.8% zero-shot | Vendor method on the vendor's own benchmark | V, Sections 6.2 and 6.3, `refresh/pdf/2505.04847.txt` |

- The two TREC numbers use different topic sets, 22 and 14. So they are not a paired comparison. **V** for the counts. A reviewer who sees the judge's label first does not give an independent label. **I**.
- TREC 2024 found that disagreements "mainly occur for sentence–passage pairs indicating partial support". **V**, Section 7.
- A system tuned on the checker drifts from humans on that checker. In ALCE, Princeton, EMNLP 2023, automatic and human citation scores were "very close except for RERANK", the system that reranked on automatic citation recall. **V**, Section 5, `refresh/pdf/2305.14627.txt`.
- Guerdan et al., CMU and Microsoft Research, NeurIPS 2025: forced-choice validation picked judges up to 31% worse than response-set validation, over 11 rating tasks and 9 commercial LLMs. **V**, abstract. Items with more than one valid label bias forced-choice validation.

What the learner gets wrong: quoting "Ragas agrees with humans 95% of the time" as the accuracy they will get on their own hard cases.

### 4.12 Measuring a faithfulness rate over a set is a different job from gating one answer

Module 4, 6.6, chose a checker threshold that blocks single answers. An eval needs an unbiased estimate of the share of faithful answers in a whole set, with an interval.

- A checker with high precision and low recall under-reports the faithful share by a large amount. Module 4's nli-deberta-v3-base at threshold 0.5 on 752 SciFact pairs has TP 73, FP 10, FN 143, TN 526. So TPR is 0.338 and TNR is 0.981. Its raw pass rate is 0.110. The true supported share is 0.287. **C** from Module 4's published counts, `advanced-retrieval-phase-06-caches-grounding.md` lines 600 to 606. Output: `refresh/runs/checks_out_2026-09-23.txt`.
- The Rogan-Gladen correction from 4.4 fixes the average but has a large spread. Here J = TPR + TNR − 1 = 0.319 and 1/J² = 9.8. With 100 labelled calibration pairs and 500 test answers, the corrected estimate had mean 0.318, SD 0.130 and RMSE 0.133. The raw rate had RMSE 0.177, because its bias was 0.177. With 752 calibration pairs and an eval set of 2,000 answers, the corrected RMSE fell to 0.040. The Phase 4 lab, with an eval set of 500, measured 0.056 at 752 pairs, so the two values are not comparable (corrected 2026-09-23 by the Phase 4 fact check). **C**, 2,000 seeded repetitions, same file. This is the variance growth Fiedler 2026 warns about in 4.4.
- The corrected mean of 0.318 against a true 0.287 shows bias at small calibration sizes. The ratio estimator and clipping at 0 and 1 both add it. **C**.
- ARES, Saad-Falcon et al., Stanford, NAACL 2024, uses prediction-powered inference, PPI, for the same job. It needs "approximately 150 annotated datapoints or more" for its intervals. **V**, Section 3, `refresh/pdf/2311.09476.txt`.
- Tune the checker threshold on a labelled split that is not the one you report. Module 4, 3.5, shows the same leak for a retrieval gate.

What the learner gets wrong: reporting the checker's raw pass rate as "our faithfulness rate", or correcting with a checker whose J is close to 0.

### 4.13 The rule that combines claim scores, and the handling of refusals, changes the answer score

- Ragas 0.4.3 computes faithfulness as supported statements divided by all statements. With no statements the score is NaN. `collections/faithfulness/metric.py` says "No statements generated - return NaN like legacy". **V**, tag v0.4.3, `refresh/pages/ragas_faith_043.py` and `refresh/pages/ragas_coll_faith_043.py`.
- DeepEval does the opposite. Its `score_qag_verdicts` returns `empty_score`, default 1, when there are no verdicts. So an answer with no claims scores 1.0 in DeepEval and NaN in Ragas. **V** at `main`, `deepeval/metrics/utils/qag.py` lines 107 to 124, `refresh/pages/de_score_src.py`. The 4.2.5 tag path returned 404, so the match with 4.2.5 is **I**.
- DeepEval also passes "borderline" claims by default. `penalize_ambiguous_claims` defaults to `False`, and then `Verdict.BORDERLINE` counts as passing. **V** at `main`, `deepeval/metrics/faithfulness/faithfulness.py` lines 77 and 393 to 399, `refresh/pages/de_faith_main.py`. Ragas has only verdicts 0 and 1. So the two tools can score the same answers differently with the same judge model. **I**.
- A mean over claims lets one false claim hide among nine true ones: the answer scores 0.9. A rule that fails the answer on any unsupported claim gives 0. **I**, arithmetic from the formula. Choose the rule by product cost, as Module 4 chose its threshold.
- A refusal such as "I could not find this" yields no statements. If the aggregate drops NaN values, refusals leave the average. **I** from the code. Whether Ragas' experiment summary drops NaN is **NC**. Check: run ragas 0.4.3 on 3 rows, one a refusal, and read the mean.

### 4.14 One agreement statistic can reward a useless judge. Kappa depends on prevalence, and AC1 hides a constant judge

Prevalence is the share of items with the positive label. Gwet's AC1 is an agreement statistic often proposed as a fix for kappa's prevalence problem.

- A judge that always says "pass" on data that is 90% pass has raw agreement 0.90 and Cohen's kappa 0. **C**, `refresh/runs/checks_out_2026-09-23.txt`, 100 items.
- On the same always-pass judge, AC1 is 0.890. **C**, same file. So AC1 hides the useless judge that kappa exposes.
- A judge with 90% agreement and 5 errors in each direction gets kappa 0.444 on 90/10 data and 0.800 on 50/50 data. **C**, same file. So kappa also moves with prevalence.
- Report TPR and TNR with intervals first, as 4.4 says. Put a chance-corrected statistic next to them, never alone. **I**, from the three computed cases. No primary source was found that settles which statistic to use for LLM judges.
- Krippendorff's alpha handles three or more raters and missing labels. The `krippendorff` package 0.8.2 exists on PyPI. The primary text of the formula was not fetched. **NC**.

### 4.15 The number of labelled failures, not labelled traces, sets the cost of judge validation

- To know a TNR of 0.9 within ±0.05 at 95% confidence, you need about 139 labelled failures. **C**, normal approximation, `refresh/runs/checks_out_2026-09-23.txt`. If 10% of traces fail, that is about 1,390 labelled traces. If 5% fail, about 2,780. **C**, same file. A TNR of 0.8 needs 246 failures per class. **C**.
- The alt-test, Calderon and Reichart, Technion, arXiv preprint, asks whether an LLM can replace a human annotator. It needs "at least three" annotators on "between 50 and 100" examples. **V**, Section 1, `refresh/pdf/2501.10970.txt`. The abs page lists no venue.
- The two figures answer different questions. The alt-test asks "is the LLM at least as good as one of the humans?" The TNR interval asks "how often does the judge miss a real failure?" **I**.
- What the learner gets wrong: labelling 100 random traces and calling the judge validated, when only 5 to 10 of them are failures. **I**, from the arithmetic above.

## 5. Proposed phase outline

Rebuilt on 2026-09-23. Faithfulness is a new phase 4. Old phases 6 and 7 are merged, so the module keeps seven phases.

Note added 2026-09-25 by the coherence pass: the built course has six phases, not seven. `eval-engineering/course.json` merges this table's phases 6 and 7 into Phase 6, and moves judge bias (4.3) into Phase 2. The owners in the built course are: 4.1 Phase 1. 4.2 and 4.3 Phase 2. 4.4, 4.5, 4.14 and 4.15 Phase 3. 4.10 to 4.13 Phase 4. 4.6 Phase 5. 4.7, 4.8 and 4.9 Phase 6. The table below is the research proposal, kept as it was.

| Phase | Title | What it teaches | Concepts | Labs it needs | Runs where, costs what |
|---|---|---|---|---|---|
| 1 | Error analysis first | traces, open coding, axial coding, taxonomy, saturation, criteria drift | 4.1 | L1, L2 | laptop, offline, synthetic traces |
| 2 | Code checks and judges | assertion vs judge, binary vs scale, pointwise, pairwise, reference, rubric, judge type | 4.2 | L3, L4 | laptop offline with a mock judge. Optional live judge, about $0.85 on Claude Haiku 4.5, see section 6 |
| 3 | Judge bias and validation | position, verbosity, self-preference, TPR, TNR, kappa, AC1, Rogan-Gladen, alt-test, labelling budget | 4.3, 4.4, 4.5, 4.14, 4.15 | L5, L6, L7, S1, S2 | laptop offline. Optional live bias probe, about $0.85 on Haiku 4.5 or $1.70 on Claude Sonnet 5 |
| 4 | Faithfulness as a measured rate | claim splitter, checker, aggregation, refusals, corrected rate, item difficulty, prompt variance | 4.10 to 4.13 | F1, F2, F3, F4, F5, S3 | laptop offline, reads Module 4's cached checker scores. Optional live judge about $0.32 on Haiku 4.5 |
| 5 | Golden sets and statistics, extends Module 3 | Wilson from Module 2, Clopper-Pearson and Beta, clustered errors, McNemar power, bootstrap limits | 4.6 | L8, L9, L10 | laptop, standard library or scipy. Imports Module 3 `common.stats` |
| 6 | Noise and flaky evals | repeated trials, reducers, noise floor, infrastructure noise, judge-prompt variance | 4.7 | L11 | laptop offline. Optional Ollama run, free |
| 7 | CI gates, regression suites, and benchmarks | gate on the interval, exit codes, skipped jobs, tool churn, contamination, broken benchmarks, the eval plan | 4.8, 4.9 | L12, L13, L14, L15 | laptop, promptfoo and pytest, GitHub Actions free tier optional |

Phases 1 to 4 are new material. Phase 5 extends Module 3, 1.4 and 1.5, and Module 2, 1.1. Phase 6 extends Module 1, 5.5. Phase 7 extends Module 1, 4.4, and Module 3, 7.5. Phase 4 builds on Module 4, 6.5 and 6.6. It turns the checker gate into a measured rate. Module 17 later decides where that gate runs in production.

Cost basis, **C** from prices read on 2026-09-23 in `refresh/pages/anth_pricing.md`: Claude Haiku 4.5 costs $1 per million input tokens and $5 per million output tokens, line 33. Claude Sonnet 5 costs $2 and $10, line 29. The Batch API gives "a 50% discount on both input and output tokens", line 192. Take a probe of 1,000 calls at about 800 input and 10 output tokens. On Haiku 4.5 it costs 1,000 × (800 × $1 + 10 × $5) / 1,000,000 = $0.85. On Sonnet 5 it costs $1.70. The token counts are **I**. OpenAI prices are **NC**: the pricing page renders with JavaScript, and curl returned no model rows.

## 6. Lab inventory and lab ideas

All labs run offline from the course `code/` folder unless marked. A seeded synthetic set of support conversations stands in for real traces. Each lab has a `--self-test` flag.

| Lab | What the script does and prints | Break-it variant | Self-test checks |
|---|---|---|---|
| L1 Open coding | Loads 120 synthetic traces. Writes one note per trace to CSV. Prints notes per trace. | Skip notes and use a generic "helpfulness" score. It misses the planted refund-policy failure. | The planted trace ids are found. |
| L2 Axial coding and saturation | Groups notes into types. Prints type, count, share, and new types per 10 traces. | Shuffle so a rare type appears late. | Saturation at the known trace count for the seed. |
| L3 Code check vs judge | Scores 200 outputs with a regex and with a mock judge of set TPR and TNR. Prints both pass rates. | A regex that passes an empty answer. | Known counts for the seed. |
| L4 Pointwise vs pairwise | Mock judge with a planted length preference. Prints flip rate after padding and tie rate for both protocols. | Remove the tie option. | Rates match planted values within tolerance. Optional live run, API key, about $0.85 on Haiku 4.5 per 1,000 calls, section 5. |
| L5 Position swap | Runs each pair in both orders. Counts a verdict only when both agree. Prints consistency. | One order only. The win rate shifts. | A planted 30% first-position bias is recovered. |
| L6 Judge validation | From 150 human and judge labels, prints TPR, TNR with Wilson intervals, percent agreement, Cohen's kappa and Gwet's AC1. Wilson comes from Module 2 `common/stats.py`. | 90% pass labels and a judge that always says pass. | That judge gets 90% agreement, kappa 0 and AC1 0.890, as in 4.14. |
| L7 Corrected pass rate | Rogan-Gladen with a bootstrap over both labelled and unlabelled sets. Compares with `judgy` 0.1.0. | TPR + TNR near 1. The interval becomes very wide. | TPR 0.9, TNR 0.8, observed 0.70 gives 0.714. |
| L8 Interval coverage | Imports `wilson` from Module 2. For N = 10, 20, 50, 100, draws 5,000 sets. Prints coverage of CLT, Wilson, Clopper-Pearson, and Beta intervals. | Use N = 10 with a true rate of 0.95. | 18 of 20 gives Wilson 0.699 to 0.972. |
| L9 Power calculator | Extends Module 3 `queries_needed` to binary rates. Prints items needed for a drop, baseline, and discordance, for independent and paired designs, with a Monte Carlo check. | Assume discordance 0.02 when the pilot shows 0.15. | 85% to 80% independent gives 906 per arm. Paired at discordance 0.10 gives 312. |
| L10 Clustered errors | 50 documents with 6 questions each and a document effect. Prints naive and clustered standard errors. | Set the document effect to 0. | Ratio above 1.5 with the planted effect, near 1 without it. |
| L11 Noise floor and reducers | Mock model with per-item pass probability. Runs 1, 5, and 10 epochs. Prints mean, majority, pass@k, and pass^k. | Gate on one run. Count false alarms over 200 unchanged runs. | Known false-alarm count for the seed. Optional Ollama run, free. |
| L12 Gate on the lower bound | pytest suite that fails when the lower end of the paired interval is below −2 points. Prints SHIP or HOLD. | Gate on the point estimate. One candidate gets a false SHIP. | Known verdicts for three seeded candidates. Builds on Module 1 `quant_gate.py` and Module 3 `paired_test`. |
| L13 promptfoo gate | promptfoo 0.123.1 config with an offline provider. Shows exit code 100, `PROMPTFOO_PASS_RATE_THRESHOLD` and `PROMPTFOO_FAILED_TEST_EXIT_CODE`. | A workflow path filter skips the job, and the required check still passes. | Exit codes 0 and 100 for two configs. Needs Node.js. Free. |
| L14 Contamination probe | Toy n-gram model trained with and without leaked test items. Prints public and fresh scores and the gap. | Leak 20% of the fresh set too. | Gap is zero without leakage. |
| L15 Eval plan capstone | Template for a model switch: taxonomy, checks, judge numbers, faithfulness splitter and aggregation rule, sizes, gate rule. A checker lists missing fields. | Leave out judge validation. | The checker names the missing field. |

### Faithfulness and agreement labs, added 2026-09-23

These labs reuse built code. They use `uv` and Module 3's pins in `retrieval-internals/code/pyproject.toml`: Python 3.12.14, torch 2.14.0, transformers 5.17.0, sentence-transformers 6.1.0, scipy 1.18.1. Statistics labs import `common.stats` from Module 3 for `bootstrap_ci`, `paired_test` and `holm`, and `wilson` from Module 2.

Module 4 already cached per-pair checker scores in `advanced-retrieval/code/.cache/phase06/`. The folder holds `nli_base_*`, `nli_minicheck_*` and other files. **V**, 13 files match those two prefixes, and `du -sh` gives 421M on 2026-09-23. The scores cover 1,090 SciFact pairs with gold support labels, **V**, `advanced-retrieval-phase-06-caches-grounding.md` line 642. The labs read these scores. They re-run a model only in F3, F5 and S3.

| Lab | What it prints | Break-it variant | Self-test | Cost and time |
|---|---|---|---|---|
| F1 From a gate to a rate | Splits Module 4's 752 core pairs into a labelled calibration set and a test set. Prints the raw pass rate, the Rogan-Gladen rate, and a bootstrap interval over both sets. Runs nli-deberta-v3-base at the rationale premise and MiniCheck at the abstract premise | Calibrate on 30 pairs. Print how often the interval misses the true 0.287 over 1,000 splits | The in-sample corrected rate is 0.287 with TP 73, FP 10, FN 143, TN 526. The RMSE at 100 calibration pairs is within 0.02 of 0.133 for seed 0 | Offline, cached scores. The stdlib core loop ran in under 10 s, **C** per the report |
| F2 Aggregation decides the answer score | Builds 200 synthetic answers of 3 to 8 SciFact claim sentences, with 0 to 2 unsupported ones planted. Scores each sentence from the cache. Prints answer scores under mean, min, and "fail if any sentence fails", and the share each rule passes at 0.8 | Add 30 refusals with no claims. Aggregate with a NaN-ignoring mean. The mean goes up | 9 supported and 1 unsupported sentence scores 0.9, 0.0 and FAIL | Offline. Run time **NC** |
| F3 The splitter is part of the metric | Scores the same answers under three splits: whole answer, sentence, and clause on "and", "while" and ";". Prints each rate and the paired difference with `common.stats.compare` | Split inside a number, "3.5" into "3" and "5". The rate changes | The claim count per split for one fixed answer | Offline. Needs nli-deberta-v3-base, 737.7 MB, already in Module 3's cache per Module 4. Run time **NC** |
| F4 Validate a faithfulness judge | Treats SciFact gold labels as human labels. Prints TPR and TNR with Wilson intervals, kappa, AC1 and raw agreement, per checker and threshold | An always-pass judge | Kappa 0 and AC1 0.890 on 90/10 data, 4.14 | Offline, cached scores. Seconds |
| F5 Optional HHEM checker | Runs `vectara/hallucination_evaluation_model` at revision `8e4a2e6e96c7` on the same pairs. Adds it to F1 and F4 | none | Scores lie in [0, 1] and the file hash matches | 438,535,352-byte download, **V**, `refresh/pages/hhem_hf.json`. Loads remote code. Compatibility with transformers 5.17.0 is **NC**. Run it once before writing the lab |
| S1 Label budget for a judge | For a target half-width and a failure share, prints labelled failures and total traces needed. Checks by simulation | Assume a 50% failure share when production shows 5% | TNR 0.9 at ±0.05 needs 139 failures, 1,390 traces at 10% failures | Stdlib, under 1 s, **C** |
| S2 Alt-test on synthetic annotators | Three synthetic annotators and one judge, each with a set error rate on 100 items. Runs the alt-test. Prints the winning rate and the advantage probability | Two annotators only. The procedure needs at least three | A judge equal to the majority vote passes | Stdlib and scipy. The equations must be copied from the paper's Section 3. **NC** |
| S3 Judge-prompt variance | Scores 300 SciFact pairs with nli-deberta-v3-base under 5 hypothesis templates. Prints the pass rate per template, the spread, and `paired_test` with `holm` across templates | Report one template only | The spread is 0 when all 5 templates are the same string | Offline. About 5 × 30 s on MPS, **I**, scaled from Module 4 timing |
| Optional live faithfulness judge | Sends the 752 core pairs to a hosted LLM judge. Prints TPR and TNR against gold | none | none | Optional, UNVERIFIED. About $0.32 on Haiku 4.5 and $0.64 on Sonnet 5, at an assumed 400 input and 5 output tokens per pair. 752 × (400 × $1 + 5 × $5) / 1,000,000 = $0.32, **C**. Batch halves it |

Lab notes from Module 4 that apply here:

- Do not run `pip install minicheck`. That PyPI name is an unrelated model checker, 0.4.0 of 2026-07-30. **V**, `refresh/pypi/minicheck.json`. Install MiniCheck from GitHub at commit b58b9fa, as Module 4 does, `advanced-retrieval-phase-06-caches-grounding.md` line 744. The MiniCheck README installs from `@main`, which can change. **V**, `refresh/pages/minicheck_readme.md` line 69.
- MiniCheck on MPS stopped responding on the author's machine in Module 4. The CPU run of all 1,090 pairs took 604 s. **V**, same file, line 804. Labs that re-run MiniCheck should default to CPU.
- LettuceDetect EuroBERT models "load remote code that is not yet compatible with transformers 5.x". ModernBERT models "are unaffected". **V**, `refresh/pages/lettuce_readme.md` line 92.

## 7. Failure stories and case studies

1. **SWE-bench Verified lost its signal.** OpenAI, 2026-02-23. OpenAI audited 138 problems that o3 did not solve consistently over 64 runs. 59.4% had material issues: 35.5% had narrow tests and 18.8% had wide tests. All tested frontier models could reproduce gold patches or problem details for some tasks. OpenAI stopped reporting the score. **V**, read in a browser by a research agent.
2. **The replacement failed too.** OpenAI, 2026-07-08. On the 731-task public SWE-Bench Pro split, human review found 34.1% of tasks broken. OpenAI wrote: "we retract our earlier recommendation to adopt SWE-Bench Pro." **V**, same method.
3. **Llama 4 on LMArena.** April 2025. Meta reported an experimental chat version at Elo 1417. LMArena said Meta "should have made it clearer" that the model was customised. **V**, LMArena quote from a secondary page. The Leaderboard Illusion reports 27 private Meta variants before release. **V**
4. **A judge that flips on order.** ChatGPT as judge changed its verdict in 66 of 80 pairs after a swap. Wang et al., Table 2. **V**
5. **Infrastructure changes the score.** Anthropic, 2026-02-05. Resource limits alone moved Terminal-Bench 2.0 by 6 points. The infra error rate fell from 5.8% at strict limits to 0.5% with no limits. **V**
6. **Silent threshold inversion.** DeepEval v4.2.0 made four metrics higher-is-better and told users to update thresholds. **V**, changelog. No incident report was found. The risk to CI gates is inferred. **I**
7. **The wrong package under the right name.** Since 2026-07-30, `pip install minicheck` installs "An explicit-state model checker in ~2900 lines", not the MiniCheck fact-checker. **V**, `refresh/pypi/minicheck.json`. No incident report was found. A lab that installs by name would score faithfulness with nothing, or fail to import. **I**
8. **A judge-tuned system drifts from humans.** In ALCE, the RERANK system used automatic citation recall to rerank. It was the one system where automatic and human citation scores were not "very close". **V**, Section 5, `refresh/pdf/2305.14627.txt`.

## 8. Primary sources

All fetched 2026-09-17. The number after each URL is the HTTP status from `curl -L`. Focus points and table numbers for each source are in section 4.

On 2026-09-23, 24 of these sources were fetched again with `curl -sL --max-time 60` for the anchor check. All 24 returned 200. The list is `scratchpad/m11_refresh/src/status.txt`. The two faithfulness and statistics groups at the end were fetched on 2026-09-23 by the refresh report.

### Error analysis

- **AI Evals: Everything You Need to Know, Husain and Shankar, hamel.dev, 2025, modified 2026-09-13** — https://hamel.dev/blog/posts/evals-faq/ 200. The authors' own method. The page changes often.
- **Using LLM-as-a-Judge For Evaluation, Husain, 2024** — https://hamel.dev/blog/posts/llm-judge/ 200. "Critique Shadowing" and pass/fail steps.
- **A Field Guide to Rapidly Improving AI Products, Husain, 2025** — https://hamel.dev/blog/posts/field-guide/ 200. "Skipping Error Analysis".
- **Who Validates the Validators?, Shankar et al., UIST 2024** — https://arxiv.org/abs/2404.12272 200. Sections 1, 6, 7.3.1 and Table 1. The source of criteria drift.
- **PROMPTEVALS, Vir, Shankar et al., NAACL 2025** — https://arxiv.org/abs/2504.14738 200. Abstract only.
- **AI Evals For Engineers & PMs, Maven** — https://maven.com/parlance-labs/evals 200. Confirms the course exists.
- **Evals for AI Engineers, O'Reilly, listed 31 Oct 2026** — https://books.google.com/books/about/Evals_for_AI_Engineers.html?id=J0Tx0QEACAAJ 200. Not released yet.
- **Lenny's Podcast with Husain and Shankar, 2025** — https://www.lennysnewsletter.com/p/why-ai-evals-are-the-hottest-new-skill 200. Show notes give 25:16 for the benevolent dictator and 31:39 for axial codes. Video https://www.youtube.com/watch?v=BsWxPI9UM4c 200. Captions were not retrieved.

### Judges, biases, and agreement

- **Judging LLM-as-a-Judge, Zheng et al., NeurIPS 2023** — https://arxiv.org/abs/2306.05685 200. Tables 2, 3, 5, 6. HTML and PDF table numbers differ after Table 6.
- **Large Language Models are not Fair Evaluators, Wang et al., ACL 2024** — https://arxiv.org/abs/2305.17926 200. Tables 2 and 4.
- **LLM Evaluators Recognize and Favor Their Own Generations, Panickssery et al., NeurIPS 2024** — https://arxiv.org/abs/2404.13076 200.
- **Self-Preference Bias in LLM-as-a-Judge, Wataoka et al., 2024** — https://arxiv.org/abs/2410.21819 200.
- **Judging the Judges, position bias, Shi et al., AACL-IJCNLP 2025** — https://arxiv.org/abs/2406.07791 200. Table 2.
- **Justice or Prejudice? CALM, Ye et al., ICLR 2025** — https://arxiv.org/abs/2410.02736 200. Table 4, 12 bias types.
- **JudgeBench, Tan et al., ICLR 2025** — https://arxiv.org/abs/2410.12784 200. Tables 1 and 2.
- **Pairwise or Pointwise?, Tripathi et al., COLM 2025** — https://arxiv.org/abs/2504.14716 200. Tables 2 and 3.
- **The Comparative Trap, Jeong et al., 2024** — https://arxiv.org/abs/2406.12319 200. Abstract only.
- **Grading Scale Impact on LLM-as-a-Judge, Li et al., 2026** — https://arxiv.org/abs/2601.03444 200. Tables 2 and 4.
- **JUDGE-BENCH, Bavaresco et al., ACL 2025** — https://arxiv.org/abs/2406.18403 200. Table 1. The main evidence for section 4.5.
- **Judging the Judges, alignment, Thakur et al., GEM 2025** — https://arxiv.org/abs/2406.12624 200. Sections 3 and 4.
- **G-Eval, Liu et al., EMNLP 2023** — https://arxiv.org/abs/2303.16634 200. Tables 1 to 3.
- **Can LLMs Be an Alternative to Human Evaluations?, Chiang and Lee, ACL 2023** — https://aclanthology.org/2023.acl-long.870/ 200. Tables 2 and 6.
- **judgy, Shreya Shankar** — https://pypi.org/pypi/judgy/json 200, and https://github.com/ai-evals-course/judgy 200.
- **How to Correctly Report LLM-as-a-Judge Evaluations, Lee et al., ICML 2026** — https://arxiv.org/abs/2511.21140 200. Table 1.
- **Bias and Uncertainty in LLM-as-a-Judge Estimation, Fiedler, 2026** — https://arxiv.org/abs/2605.06939 200. Section 2.
- **Prediction-Powered Inference, Angelopoulos et al., Science 2023** — https://arxiv.org/abs/2301.09633 200. Abstract only. The general framework for mixing few human labels with many model labels.

### Statistics and noise

- **Adding Error Bars to Evals, Evan Miller, Anthropic, 2024** — https://arxiv.org/abs/2411.00640 200. Sections 2 to 5, Table 4. Companion post https://www.anthropic.com/research/statistical-approach-to-model-evals 200.
- **Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints, Bowyer et al., ICML 2025** — https://arxiv.org/abs/2503.01747 200. Section 3 and Table 1.
- **Hitchhiker's Guide to Testing Statistical Significance in NLP, Dror et al., ACL 2018** — https://aclanthology.org/P18-1128/ 200. Section 3.2 defines McNemar for binary labels. Table 2 shows 63 of 180 papers reported significance.
- **An Empirical Investigation of Statistical Significance in NLP, Berg-Kirkpatrick et al., EMNLP 2012** — https://aclanthology.org/D12-1091/ 200. Section 1 only.
- **Defeating Nondeterminism in LLM Inference, Thinking Machines Lab, 2025** — https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/ 200.
- **Non-Determinism of "Deterministic" LLM Settings, Atil et al., 2024** — https://arxiv.org/abs/2408.04667 200. Table 2.
- **Messages API reference, Anthropic** — https://platform.claude.com/docs/en/api/messages/create 200. The `temperature` parameter.
- **Advanced usage, OpenAI** — https://developers.openai.com/api/docs/guides/advanced-usage 200. `seed` and `system_fingerprint`.
- **τ-bench, Yao et al., Sierra, 2024** — https://arxiv.org/abs/2406.12045 200. The pass^k definition.
- **Demystifying evals for AI agents, Anthropic Engineering, 2026-01-09** — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents 200.
- **Quantifying infrastructure noise in agentic coding evals, Anthropic Engineering, 2026-02-05** — https://www.anthropic.com/engineering/infrastructure-noise 200.

### Benchmarks and product evals

- **GSM1k, Zhang et al., Scale AI, NeurIPS 2024** — https://arxiv.org/abs/2405.00332 200. Section 5, Appendix F.
- **Why SWE-bench Verified no longer measures frontier coding capabilities, OpenAI, 2026-02-23** — https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/ 403 to curl. A research agent read it in a browser.
- **Separating signal from noise in coding evaluations, OpenAI, 2026-07-08** — https://openai.com/index/separating-signal-from-noise-coding-evaluations/ 403 to curl. A research agent read it in a browser.
- **LiveBench, White et al., ICLR 2025** — https://arxiv.org/abs/2406.19314 200. Section 2.7.
- **The Leaderboard Illusion, Singh et al., 2025** — https://arxiv.org/abs/2504.20879 200.
- **Llama 4 announcement, Meta, 2025** — https://ai.meta.com/blog/llama-4-multimodal-intelligence/ 200.
- **LMArena statement quoted by Simon Willison, 2025-04-08** — https://simonwillison.net/2025/Apr/8/lmaren/ 200. Secondary source.
- **Evaluation best practices, OpenAI** — https://developers.openai.com/api/docs/guides/evaluation-best-practices 200.
- **Define success criteria and build evaluations, Anthropic** — https://platform.claude.com/docs/en/test-and-evaluate/develop-tests 200.
- **AI workload testing, Microsoft Azure Well-Architected** — https://learn.microsoft.com/en-us/azure/well-architected/ai/test 200. Gives no sizing number.

### Faithfulness, added 2026-09-23

- **RAGAS: Automated Evaluation of Retrieval Augmented Generation, Es et al., Exploding Gradients and Cardiff, 2023** — https://arxiv.org/abs/2309.15217. arXiv, no venue in Comments. Section 3, Section 4 and Table 1.
- **FActScore, Min et al., UW, UMass Amherst, AI2 and Meta, EMNLP 2023** — https://arxiv.org/abs/2305.14251. Table 3 and Appendix B.2.
- **Enabling LLMs to Generate Text with Citations, ALCE, Gao et al., Princeton, EMNLP 2023** — https://arxiv.org/abs/2305.14627. Section 3.3, Section 5, Appendix G.5.
- **MiniCheck, Tang et al., UT Austin and Salesforce AI Research, EMNLP 2024** — https://arxiv.org/abs/2404.10774. Section 1.
- **ARES, Saad-Falcon et al., Stanford, NAACL 2024** — https://arxiv.org/abs/2311.09476. Section 3, PPI and the 150-label requirement.
- **RAGTruth, Niu et al., ACL 2024** — https://arxiv.org/abs/2401.00396. Table 5 and Section 6.2. Prompted gpt-4-turbo: response-level F1 63.4, precision 46.9, recall 97.9, span-level precision 18.4%.
- **FaithBench, Bao et al., Vectara and others, 2024** — https://arxiv.org/abs/2410.13210. arXiv, no venue. Abstract and Section 2.
- **FaithJudge, Tamber et al., Vectara, EMNLP 2025 Industry** — https://arxiv.org/abs/2505.04847. Sections 6.2 and 6.3.
- **Support Evaluation for the TREC 2024 RAG Track, Thakur et al., Waterloo, Snowflake and Microsoft, SIGIR 2025 short** — https://arxiv.org/abs/2504.15205. Sections 5 to 7.
- **A Closer Look at Claim Decomposition, Wanner et al., Johns Hopkins, 2024** — https://arxiv.org/abs/2403.11903. arXiv, no venue. Abstract and Figure 2.
- **Decomposition Dilemmas, Hu et al., NTU, NAACL 2025** — https://arxiv.org/abs/2411.02400. Abstract.
- **RAGChecker, Ru et al., Amazon AWS AI and others, 2024** — https://arxiv.org/abs/2408.08067. "Under Review". Correlation table not read.
- **LLM-AggreFact leaderboard** — https://llm-aggrefact.github.io/. Default view, 11 of 39 models, balanced accuracy: Bespoke-MiniCheck-7B 77.4, Claude-3.5 Sonnet 77.2, FactCG-DeBERTa-L 0.4B 75.6. No update date on the page.
- **Ragas source at v0.4.3** — https://raw.githubusercontent.com/vibrantlabsai/ragas/v0.4.3/src/ragas/metrics/_faithfulness.py.
- **DeepEval faithfulness source at `main`** — https://raw.githubusercontent.com/confident-ai/deepeval/main/deepeval/metrics/utils/qag.py. The v4.2.5 tag path returned 404.
- **MiniCheck README at `main`** — https://raw.githubusercontent.com/Liyan06/MiniCheck/main/README.md.
- **LettuceDetect README at `main`** — https://raw.githubusercontent.com/KRLabsOrg/LettuceDetect/main/README.md.
- **HHEM model API** — https://huggingface.co/api/models/vectara/hallucination_evaluation_model.

### Agreement statistics and variance, added 2026-09-23

- **The Alternative Annotator Test for LLM-as-a-Judge, Calderon and Reichart, Technion, 2025** — https://arxiv.org/abs/2501.10970. arXiv, no venue. Sections 1 and 3.
- **Validating LLM-as-a-Judge Systems under Rating Indeterminacy, Guerdan et al., CMU and Microsoft Research, NeurIPS 2025** — https://arxiv.org/abs/2503.05965. Abstract and Figure 1.
- **Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design, Sclar et al., ICLR 2024** — https://arxiv.org/abs/2310.11324. Abstract.
- **State of What Art? A Call for Multi-Prompt LLM Evaluation, Mizrahi et al., TACL** — https://arxiv.org/abs/2401.00595. Abstract.
- **Quantifying Variance in Evaluation Benchmarks, Madaan et al., Meta, 2024** — https://arxiv.org/abs/2406.10229. Training-seed variance. Not a source for repeated eval runs.
- **Signal and Noise, Heineman et al., AI2, 2025** — https://arxiv.org/abs/2508.13144. Checkpoint variance. Not a source for repeated eval runs.

### Tooling and CI

- **promptfoo** — https://registry.npmjs.org/promptfoo 200. https://www.promptfoo.dev/docs/usage/command-line/ 200. https://www.promptfoo.dev/docs/integrations/ci-cd/ 200. https://www.promptfoo.dev/blog/promptfoo-joining-openai/ 200.
- **Inspect AI, UK AI Security Institute** — https://inspect.aisi.org.uk/ 200. https://pypi.org/pypi/inspect-ai/json 200.
- **OpenAI Evals** — https://developers.openai.com/api/docs/deprecations 200. https://developers.openai.com/api/docs/guides/evals 200. https://github.com/openai/evals 200.
- **DeepEval** — https://pypi.org/pypi/deepeval/json 200.
- **Ragas** — https://pypi.org/pypi/ragas/json 200. https://docs.ragas.io/en/stable/howtos/migrations/migrate_from_v03_to_v04/ 200.
- **Braintrust** — https://pypi.org/pypi/braintrust/json 200. https://pypi.org/pypi/autoevals/json 200. https://www.braintrust.dev/docs/evaluate/run-in-ci 200.
- **LangSmith** — https://pypi.org/pypi/langsmith/json 200.
- **Langfuse** — https://pypi.org/pypi/langfuse/json 200. https://clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability 200. https://langfuse.com/blog/joining-clickhouse 200. https://langfuse.com/blog/2025-06-04-open-sourcing-langfuse-product 200.
- **Arize Phoenix** — https://pypi.org/pypi/arize-phoenix/json 200. https://pypi.org/pypi/arize-phoenix-evals/json 200.
- **About protected branches, GitHub Docs** — https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches 200. The required-checks rule.

## 9. Tools and versions to pin

Versions re-checked on PyPI and npm on 2026-09-23. **V**, `refresh/pypi/versions_2026-09-23.txt`. The previous column is the 2026-09-17 value.

| Tool | Version | Uploaded | Previous | Notes on breaking changes |
|---|---|---|---|---|
| promptfoo, Promptfoo Inc. | 0.123.1 | 2026-09-18 | 0.123.0 | MIT. Exit code 100 logic unchanged. 0.122.0 dropped Node.js 20. Acquisition by OpenAI announced |
| Inspect AI, UK AISI | 0.3.268 | 2026-09-22 | 0.3.264 | MIT. Adds a `collect` reducer. Default reducer still `mean` |
| OpenAI Evals, hosted | n/a | deprecated 2026-06-03 | same | Read-only 2026-10-31. Shutdown 2026-11-30. Do not use in labs. Dates re-verified by the audit, not re-checked here |
| openai/evals repo | no release | last commit 2026-04-14 per research agent | same | Hygiene commits only. **I** |
| DeepEval, Confident AI | 4.2.5 | 2026-09-22 | 4.2.3 | Apache-2.0. v4.2.0 inverted four metric scales. At `main`, faithfulness with no claims scores 1.0, and borderline claims pass by default |
| Ragas | 0.4.3 | 2026-01-13 | same | Apache-2.0. v0.4 replaced `evaluate()` with `@experiment()`. Faithfulness NaN at 0 statements |
| Braintrust SDK | py 0.42.0 | 2026-09-22 | py 0.41.0, npm 3.34.0 | MIT SDK. npm version not re-checked |
| autoevals, Braintrust | 0.3.0 | 2026-06-09 | same | MIT per GitHub |
| LangSmith SDK, LangChain | 0.14.0 | 2026-09-21 | 0.12.6 | MIT. 0.13.0 on 2026-09-18 added `disable_evaluator_tracing` |
| Langfuse SDK | 4.15.4 | 2026-09-16 | same | MIT except `ee/` folders. Cloud v3 endpoints and trace-level evaluators end 2026-11-16 |
| Arize Phoenix | 20.16.0 | 2026-09-23 | 20.13.0 | Elastic License 2.0, not OSI open source |
| arize-phoenix-evals | 3.9.0 | 2026-09-21 | 3.8.0 | Elastic-2.0 |
| judgy | 0.1.0 | 2025-05-25 | same | MIT. Only one release. Treat as reference code |
| scipy | 1.18.1 | 2026-08-21 | same | Also pinned in Module 3 |
| statsmodels | 0.15.0 | 2026-08-27 | same | Function names **NC** |
| scikit-learn | 1.9.1 | 2026-09-10 | new | For `cohen_kappa_score`, **NC** at this tag. Not in Module 3's lockfile |
| krippendorff | 0.8.2 | 2025-11-03 | new | Krippendorff's alpha |
| irrCAC | 0.4.4 | 2024-11-05 | new | Gwet's AC1 and others. No release in 22 months |
| pingouin | 0.6.1 | 2026-03-28 | new | GPL-3.0. Avoid if the course code must stay permissive |
| lettucedetect | 0.2.3 | 2026-08-13 | new | MIT. Needs Python 3.11 or later |
| trulens | 2.14.0 | 2026-09-03 | new | MIT, Snowflake. Groundedness functions **NC** |
| ares-ai | 0.6.6 | 2024-07-11 | new | Apache-2.0. No release in over 2 years |
| minicheck on PyPI | 0.4.0 | 2026-07-30 | new | **Wrong package.** A model checker, not MiniCheck. Install MiniCheck from GitHub at commit b58b9fa |
| HHEM model | revision 8e4a2e6e96c7 | 2025-10-20 | new | Apache-2.0, 438,535,352 bytes, remote code |

## 10. Open questions and disagreements

1. **Same-model judges.** The Husain and Shankar FAQ says a same-model judge "is usually fine", because the judge does a narrow task. Zheng, Panickssery, and Wataoka measured self-preference in open-ended preference tasks. No study was found on narrow binary checks. Suggested check: measure TPR and TNR for two judge models on the same labels.
2. **Binary vs scale.** Husain and Shankar recommend binary labels without a cited study. Li et al. 2026 found 0-5 best among 0-5, 0-10, and 0-100, but did not test binary. Open.
3. **Pairwise vs pointwise.** Pairwise gives far fewer ties. For four open logit-based judges it flips about 35% of the time under distractors, against about 9% for absolute scores, per Tripathi et al. For o3-mini and o4-mini, absolute scoring flips 17.2% to 25.7%, so the gap is smaller. The choice depends on the judge type and on whether the gate needs sensitivity or robustness.
4. **Bootstrap or not.** Miller calls the bootstrap unnecessary. Bowyer et al. show CLT and bootstrap both under-cover at small N. Miller did not test small N. Each is right in its own size range.
5. **How many items.** Anthropic suggests 20 to 50 tasks to start. Miller's arithmetic gives about 1,000 for 3 points under a toy variance. Binary rates need more. The first answers "find large failures". The second answers "detect small regressions".
6. **Correcting judge estimates.** `judgy` and Lee et al. apply Rogan-Gladen. Fiedler, citing Greiner 2003, warns it can have higher error than the raw rate when J = TPR + TNR − 1 is small.
7. **Judge-human agreement.** MT-Bench reports over 80% agreement without ties. JUDGE-BENCH reports low mean correlation. The metric, the tie rule, and the task mix explain the gap. See 4.5.
8. **Split claims or not.** FActScore, Ragas and RAGChecker split answers into claims. MiniCheck says it does not need to. Hu et al. find a trade-off. No published comparison uses RAG answers of the length a support bot writes. Lab F3 measures it on SciFact only.
9. **Which agreement statistic.** Kappa punishes skewed data. AC1 rewards a constant judge, 4.14. Krippendorff's alpha handles many raters. No primary source settles the choice for LLM judges. The course reports TPR and TNR first.
10. **LLM judge or small checker for faithfulness.** On LLM-AggreFact, a 0.4B checker is 1.8 points below the best listed model. FaithJudge reached 84% on FaithBench. The two numbers use different benchmarks, so they cannot be compared.
11. **Is an LLM judge more consistent than the human assessor?** In TREC 2024, an independent human assessor agreed more with GPT-4o than with the NIST human, on 537 disagreement pairs. Kappa was 0.29 with GPT-4o and −0.03 with the NIST human, from scratch. **V**, Figure 4, `refresh/pdf/2504.15205.txt`. This is one study, and it sampled only disagreements.
12. **Scope gaps named by the audit and still not researched:** synthetic test-set generation and how to validate it, and reasoning models as judges, with their cost and variance. **NC**.

## 11. Things I could NOT verify

1. **OpenAI blog pages** return HTTP 403 to curl. A research agent read both in a browser. The author of this dossier did not re-read them. Confirm by opening both URLs in a browser and searching for "59.4%" and "we retract".
2. **OpenAI's own promptfoo acquisition page** returned 403. The acquisition is confirmed only by Promptfoo's blog. Whether the deal closed is not checked.
3. **promptfoo `--fail-on-error`.** The absence of the option is verified in source at 0.123.0 and 0.123.1. That the command fails is inferred. Run `npx promptfoo@0.123.1 eval --fail-on-error`.
4. **The LMArena statement** comes from a secondary page. The X post was not read.
5. **No study compares binary and Likert judge scales** in the searches run. A wider literature search would confirm the absence.
6. **Abstract-only sources:** PROMPTEVALS, Attune, The Comparative Trap, Prediction-Powered Inference, and the contamination survey by Xu et al.
7. **Figure-only values** were not extracted: Thakur per-judge Scott's pi, Wataoka scores for other models, Bowyer coverage curves apart from 92.5% at N=100, Zheng Table 4 values.
8. **Venues not found:** Fiedler 2605.06939, Li et al. 2601.03444, Atil et al. 2408.04667, τ-bench.
9. **YouTube captions** for the Husain and Shankar talks returned no text. The only timestamps come from Lenny's show notes. Pull captions with a browser before quoting timestamps.
10. **judgy source** was read at `main`, not at a tag, on 2026-09-17 and again on 2026-09-23. The cited lines still match. Compare with the 0.1.0 sdist.
11. **Breaking changes** in the last 12 months were not checked for Inspect AI, Braintrust, autoevals, or LangSmith. CI gate and interval support were not checked for Ragas, Langfuse, or Phoenix.
12. **The McNemar sample-size formula** is attributed to Connor 1987, which was not fetched. The Monte Carlo check matched within 3 points of power.
13. **Anthropic trial-isolation wording** about git history was reported by a research agent and not re-checked by the author.
14. **statsmodels function names** at 0.15.0, and scikit-learn 1.9.1 `cohen_kappa_score`, were not checked at their tags. Check: grep the source at each tag.
15. **Enrolment numbers** for the Maven course conflict between pages: 700+ and 5,000+. Neither is verified.
16. **Ragas aggregate with NaN.** Whether the Ragas experiment summary drops NaN rows. Check: run ragas 0.4.3 on three rows, one a refusal, and read the mean.
17. **DeepEval faithfulness source at the release tag.** Read at `main`. The `v4.2.5` and `4.2.5` paths returned 404, and the GitHub API returned 403. Check: find the tag name on the releases page and compare `qag.py` and `faithfulness.py` with `main`.
18. **HHEM with transformers 5.17.0.** It needs remote code. Check: load it once in Module 3's environment.
19. **RAGChecker correlation numbers.** Downloaded, not read. Check: Table 2 and Appendix C of `refresh/pdf/2408.08067.txt`.
20. **Wanner et al. spread across splitting methods.** Only the Figure 2 caption is verified. Check: read the chart values or an appendix table.
21. **Alt-test equations** for Lab S2. Only the setup is verified. Check: Section 3 of `refresh/pdf/2501.10970.txt`. Resolved 2026-09-25: the Phase 3 lab `eval-engineering/code/phase03_validate/alt_test.py` copies the equations from Sections 3.1 to 3.4 and Appendix D.6, Algorithm 1, of arXiv 2501.10970 as served on 2026-09-23, and its self-test checks them by hand.
22. **OpenAI prices.** The pricing page returned no model rows to curl. Check: open https://developers.openai.com/api/docs/pricing in a browser.
23. **Venues** for FaithBench, the alt-test paper and RAGChecker. The arXiv abs pages list none. Resolved 2026-09-25 by the coherence pass for two of the original five: Ragas is EACL 2024 System Demonstrations, https://aclanthology.org/2024.eacl-demo.16/, and Wanner et al. is *SEM 2024, https://aclanthology.org/2024.starsem-1.13/. Both pages returned the paper's title.
24. **Krippendorff's alpha primary text** was not fetched.
25. **Run times for labs F2, F3 and S3** were not measured. HHEM download and load time for F5 were not measured.
26. **Inspect AI default `stderr()` attachment** was not re-checked at 0.3.268. Only the definition in `_metrics/std.py` was.
27. **DeepEval `deepeval test run` exit code and the 0.5 default threshold** were not re-checked at 4.2.5.
28. **Braintrust npm version** was not re-checked on 2026-09-23.
29. **Thakur et al. per-judge Scott's pi values.** The Figure 1 values appear in the extracted text, but which value belongs to which judge was not mapped. Only "Scott's π score of only 59" for Llama-3 8B is quoted from the text.

## 12. Notes for the course generator

- **Fix Module 1's 85%/81% framing** when phase 3 cites it. Always give the with-ties numbers too: 66% and 63%.
- **Never write "judges correlate 0.6 to 0.85 with humans" without conditions.** Use the table in 4.5.
- **Always name the metric.** Percent agreement, kappa, Scott's pi, Spearman, Pearson, Kendall, and ICC are different numbers.
- **Do not build any lab on the OpenAI Evals API.** It shuts down on 2026-11-30.
- **Do not tell learners to set temperature 0.** Newer Anthropic models reject it. Teach repeated trials.
- **Do not present "1,000 questions" as a rule.** State Miller's ω² = 1/9 assumption and show the binary-rate numbers.
- **Label practitioner advice as opinion.** Binary labels, 100 traces, 30 traces, and the benevolent dictator come from the FAQ, not from studies.
- **Numbers that go stale fastest:** tool versions, the promptfoo acquisition status, Langfuse and OpenAI deprecation dates, and benchmark status.
- **Re-check before generating:** the hamel.dev FAQ quotes and the promptfoo `--fail-on-error` docs. Also check Inspect AI reducer names, DeepEval metric direction, the Ragas API, and whether the book has shipped.
- **Pin versions in `pyproject.toml`** for Inspect AI, DeepEval, and Ragas. They release often and have changed APIs.
- **Reuse Module 1 code.** `quant_gate.py` has the paired bootstrap. `incident_drill.py` has slice triage. Link to them, do not copy.
- **Keep product work out.** Use a synthetic support dataset. Never ask the learner to evaluate their own product.
- **Old phases 6 and 7 are merged** into the new phase 7, CI gates and benchmarks. See section 5.
- **Name the judge type when citing Tripathi et al.** The 9% absolute flip rate is for four open logit-based judges. o3-mini and o4-mini flip 17.2% to 25.7%.
- **Never report a faithfulness number without four settings:** the claim splitter, the checker and its threshold, the premise text, and the aggregation rule with its refusal handling.
- **Never use a checker's raw pass rate as the faithfulness rate.** Correct it, and give the interval and J.
- **Report TPR and TNR first.** Kappa or AC1 goes next to them, never alone.
- **Size judge validation by failures.** Use S1 before labelling.
- **Do not cite Madaan et al. or Heineman et al. for repeated eval runs.** They measure training-seed and checkpoint variance.
- **Do not write `pip install minicheck`.** Link Module 4, line 744, for the install.
- **Phase 5 extends Module 3.** Link `paired_test`, `holm`, `bootstrap_ci` and `queries_needed`, and Module 2's `wilson`. Do not re-teach them.
- **Leave production placement of the faithfulness gate to Module 17**, and trajectories, pass^k in depth, user simulators, online evals and the improvement loop to Module 12.

## 13. Refresh log 2026-09-23

Inputs: the refresh report `scratchpad/reports/research_eval-engineering_refresh.md`, the audit notes at `scratchpad/reports/curriculum_audit.md` lines 207 to 214, and the built modules. The 2026-09-17 text is saved as `scratchpad/m11_refresh/module-11_before_2026-09-23.md`. The edit scripts are `scratchpad/m11_refresh/edit1.py` to `edit5.py`.

### Changes

1. **Section 4 headings are all claims now.** 4.2, 4.3, 4.4, 4.6, 4.7, 4.8 and 4.9 had topic headings. 4.1 and 4.5 were claims and were reworded to state the condition. Brief rule 1.
2. **Six new concepts, 4.10 to 4.15.** The faithfulness score depends on the claim splitter and the checker. Judge-human agreement on faithfulness depends on item difficulty. Measuring a rate is a different job from gating one answer. Aggregation rules and refusals change the score. Kappa depends on prevalence and AC1 hides a constant judge. Labelled failures set the labelling budget. Evidence: refresh report sections 1.1 to 1.6 and 2.4. Audit gap 2, `curriculum_audit.md` line 210.
3. **Scope.** Two in-scope bullets added: agreement statistics, and faithfulness as a measured rate. Section 1 records the hand-over from Module 3, `retrieval-internals/course.json` line 29.
4. **Out-of-scope table rebuilt.** Module 12 owns trajectories, pass^k in depth, user simulators, online evals, the improvement loop and multi-turn faithfulness. Module 17 owns where the faithfulness gate runs in production. Evidence: refresh report section 8, audit line 434.
5. **Overlap table rebuilt** from `grep '^## '` on the phase files of Modules 2, 3, 4 and 6. It names heading, file and line for each row. Fourteen new rows. A new list says what Module 11 teaches that Modules 2, 3 and 4 do not. Term counts support it. Audit fix 1 and brief rule 9.
6. **Phase outline.** Faithfulness is a new phase 4. Old phases 6 and 7 are merged. Phase 5 is marked "extends Module 3". Seven phases.
7. **Lab inventory.** Added F1 to F5, S1 to S3 and an optional live faithfulness judge. They read Module 4's cached scores, verified at 421M on disk. L6, L8, L9, L12, L13 and L15 now link Module 2 and Module 3 code or the new concepts. Lab notes on MiniCheck install, MiniCheck on MPS, and LettuceDetect remote code added.
8. **Section 3.** Nine rows added for changes between 2026-09-17 and 2026-09-23.
9. **Section 7.** Two failure stories added: the `minicheck` PyPI name, and ALCE's RERANK system.
10. **Section 8.** Two source groups added, faithfulness and agreement statistics. 24 old sources were fetched again. All returned 200, `scratchpad/m11_refresh/src/status.txt`.
11. **Section 9 re-pinned.** 13 of the 15 old rows were re-checked on PyPI or npm, and 7 changed. The two OpenAI Evals rows and the Braintrust npm version were not re-checked. Nine rows were added.
12. **Section 10.** Five open questions added, 8 to 12.
13. **Section 11.** Fourteen items added, 16 to 29. Items 3, 10 and 14 updated.
14. **Section 12.** Nine notes added for the course generator, and the old note on merging phase 7 replaced.

### Corrections to the 2026-09-17 text

1. **Tripathi flip rates lacked the judge type.** Old 4.2 said absolute scoring flipped 9.0% to 9.7%. Old open question 3 said "about 9% for absolute scores" with no condition. Those numbers are for four open models in the "Logit-based outputs" group. In the same Table 2, o4-mini flips 17.2% to 25.33% and o3-mini 21.3% to 25.7% under absolute scoring. Evidence: `refresh/pdf/2504.14716.txt`, Table 2 rows "Avg.(across models) 9.0 35.5 9.25 35.2 9.7 34.9", "o4-mini-2025-04-16 18.5 34.9 17.2 29.4 25.33 44.0" and "o3-mini-2025-01-31 21.3 30.0 25.7 40.6 24.8 38.9". Fixed in 4.2 and section 10.
2. **Training-seed variance is not eval-run variance.** The old text had 0 mentions of Madaan et al. or Heineman et al., by grep. The report found both papers in the variance search. They measure variance across training seeds and checkpoints, not repeated eval runs on one model. Evidence: abstracts, `refresh/pdf/2406.10229.txt`, "seed variance across initialisations", and `refresh/pdf/2508.13144.txt`, "intermediate checkpoints". 4.7 and section 12 now say not to cite them for repeated runs. This is a guard, not a fix of a wrong sentence.
3. **FAQ date.** Old 4.1 said "modified 2026-09-13". The page now says 2026-09-21 and adds "Continue past 100 while you are still learning." Evidence: `refresh/pages/hamel_faq.txt`.
4. **Anthropic temperature wording.** Old 4.7 said newer models "reject temperature values other than 1.0". The current page says they "do not support setting temperature", marks it "Deprecated", and deprecates `top_k` too. Evidence: `refresh/pages/anth_messages.txt`.
5. **Inspect AI version and reducers.** Old 4.7 cited 0.3.264. Now 0.3.268, with a new `collect` reducer and the default `mean` verified in `epochs.py`. Evidence: `refresh/pages/inspect_reducer_268.py` line 304, `refresh/pages/insp_epochs.py` lines 9 to 26.
6. **promptfoo version and exit code.** Old 4.8 cited 0.123.0, lines 1290 to 1305. Now 0.123.1, lines 1290 to 1304, plus `PROMPTFOO_FAILED_TEST_EXIT_CODE`. `--fail-on-error` is still absent. Evidence: `refresh/pages/promptfoo_doEval_1231.ts`, `refresh/pages/promptfoo_evalcmd_1231.ts`.
7. **Versions.** promptfoo 0.123.0 to 0.123.1. Inspect AI 0.3.264 to 0.3.268. DeepEval 4.2.3 to 4.2.5. Braintrust 0.41.0 to 0.42.0. LangSmith 0.12.6 to 0.14.0. Phoenix 20.13.0 to 20.16.0. phoenix-evals 3.8.0 to 3.9.0. Evidence: `refresh/pypi/versions_2026-09-23.txt`.
8. **Prices.** Old phase 2 said "about $1", old phase 3 "$1 to $3", and old L4 "about $1", with no price source. Recomputed from the 2026-09-23 pricing page: about $0.85 on Haiku 4.5 and $1.70 on Sonnet 5 per 1,000 calls of about 800 input and 10 output tokens. Evidence: `refresh/pages/anth_pricing.md` lines 29, 33 and 192. The token counts are assumed.
9. **The `minicheck` PyPI trap.** The old text had no faithfulness labs and no warning. `pip install minicheck` now installs an unrelated model checker. Evidence: `refresh/pypi/minicheck.json`. Added to sections 3, 6, 7, 9 and 12.
10. **JUDGE-BENCH spread.** Old 4.5 gave GPT-4o's mean Spearman of 0.50 without its spread. Table 1 gives ±0.21 across datasets. Evidence: `refresh/pdf/2406.18403.txt`.
11. **judgy line numbers.** Old 4.4 cited lines 106 to 152 at `main`. Re-read on 2026-09-23: the error message is at line 113 and the test-set resample at lines 126 and 127, inside that range. Evidence: `scratchpad/m11_refresh/src/judgy_core.py`.
12. **GSM1k quote shortened the source.** Old 4.9 quoted frontier models as showing "no signs of overfitting". The paper says Gemini, GPT, and Claude "show little to no signs of overfitting". Old 4.9 also said "up to 8 points". The paper says "accuracy drops of up to 8%". Evidence: `src/2405.00332.txt`. Fixed in 4.9.

### Corrections to the refresh report, found while merging

1. **The `minicheck` trap is already taught.** Report section 2.7 says labs "must do the same" as Module 4's pinned commit, and presents the PyPI trap as new. Module 4 already warns against `pip install minicheck`, `advanced-retrieval-phase-06-caches-grounding.md` line 744. Module 11 links it.
2. **McNemar in Module 4 is more than a citation.** Report section 2.5 says "citation only, not taught". Module 4 defines it in one sentence in its key terms, `advanced-retrieval-phase-02-no-index.md` line 57, and uses it as evidence at line 364. It does not teach it. The overlap table says so.
3. **Holm counts.** The audit counted 80 Holm mentions in Module 3. Today's count is 85 in Module 3 and 119 in Module 4. The report did not count Module 4. Evidence: `grep -c -i holm` over the phase files.
4. **TREC independent assessor.** Report open question 4 says "an independent judge". Figure 4 labels it "Independent human". Evidence: `refresh/pdf/2504.15205.txt`.

### Anchor re-check

142 anchor strings across 4.1 to 4.15 were grepped on 2026-09-23 in their saved source or run files. All 142 were found. Whitespace and line-break hyphens were normalised before matching. The count per concept follows. 4.1 10, 4.2 9, 4.3 17, 4.4 13, 4.5 10, 4.6 7, 4.7 17, 4.8 5, 4.9 12, 4.10 7, 4.11 12, 4.12 8, 4.13 6, 4.14 4, 4.15 5. Files: `scratchpad/m11_refresh/anchors.tsv` for the list and `scratchpad/m11_refresh/anchors_out.tsv` for the hit counts. Short numeric anchors such as "0.24", "0.57" and "0.29" were also read in context: Wang Table 4, Shi Table 2 and TREC Figure 4.

The 2026-09-17 computed values were re-run with Python 3 standard library. All nine matched: 0.714, the CLT and Wilson intervals for 18 of 20, 2,402, 4,356, 906, 250, 312, 155, 870, and Miller's 969. Files: `scratchpad/m11_refresh/recheck.py` and `recheck_out_2026-09-23.txt`.

Section-4 facts not re-grepped: Lee et al.'s 95% to 99% coverage, only the GPT-4.1-mini judge name was found. DeepEval's exit code and 0.5 default, because no DeepEval 4.2.3 source was saved. Li et al.'s rater and benchmark counts. The OpenAI blog pages behind sections 3 and 7 still return 403 to curl, section 11 item 1.

Summary: section 4 now holds 15 claims, six of them new on faithfulness and judge agreement. Twelve corrections to the old text and four to the refresh report are logged above. All 142 section-4 anchors were found in saved files.

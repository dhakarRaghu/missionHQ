# Module 11 — Eval engineering

Research date: 2026-09-17. Status: research dossier, not course material.

Labels used in this file: **V** is verified, with the source next to it. **C** is computed on 2026-09-17 with Python 3 standard library, on the author's laptop. **I** is inferred, and the text names what it was inferred from. **NC** is not checked.

## 1. What this module is for

An eval is a repeatable test that scores the output of an AI system. This module teaches the learner to build evals that give a trustworthy number for their own product. Without that number, every prompt change, model switch, and retrieval change is a guess. Module 1 made decisions with small eval sets. It did not teach how to find failures, build and check a judge, or size a dataset. Public leaderboards cannot replace this work. In 2026 OpenAI stopped reporting one major coding benchmark and then withdrew its advice to use the replacement. The later modules on agents, retrieval, and cost all need an eval gate, so this module comes early in the core path.

## 2. Scope

### In scope

- Error analysis on traces: open coding, axial coding, failure taxonomies, saturation, and criteria drift. A trace is the full record of one request: inputs, tool calls, and output.
- Code-based checks and LLM judges. An LLM judge is a model that scores another model's output.
- Judge design: binary or scale, pointwise or pairwise, reference-based, and rubric-based.
- Judge biases with measured numbers: position, verbosity, and self-preference.
- Judge validation: TPR, TNR, Cohen's kappa, percent agreement, and correction of the measured pass rate.
- Golden datasets: sizing, small-sample intervals, clustered errors, paired tests, and power analysis. A golden dataset is a fixed, labelled set of inputs that every version is scored on.
- Non-determinism: repeated trials, epochs, and the noise floor.
- CI gates and regression suites: thresholds, exit codes, and how to avoid a gate that passes by accident.
- Tooling: promptfoo, Inspect AI, OpenAI Evals, DeepEval, Ragas, Braintrust, LangSmith, Langfuse, and Phoenix.
- Benchmark contamination and broken benchmarks, and why product evals are still needed.

### Out of scope, and where it lives instead

| Topic | Where it lives |
|---|---|
| Multi-turn agent evals, simulated users, pass^k on agent tasks in depth | Module 12, agent and online evals |
| Online evals on production traffic, A/B tests, feedback loops | Module 12 |
| Retrieval metrics such as recall@k and nDCG | the retrieval modules |
| Tracing pipelines and dashboards | Module 15, observability |
| Safety and red-team evals | Module 16 and the guardrails module |
| Training reward models and RL graders | the post-training elective |

### Overlap with earlier modules

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| Gating a model swap in four steps | Module 1, 3.4 "Gating the swap" | The full method: find failures first, then build and validate the scorer |
| Position bias fix by swapping order | Module 1, 3.4 step 3 | Measured bias sizes across judges, plus verbosity and self-preference |
| Paired bootstrap and "decide on the worst end" | Module 1, 4.4, `quant_gate.py` | When the bootstrap fails at small N, Wilson and Bayesian intervals, McNemar |
| Judge agreement 85% vs human 81% | Module 1, 5.4 | The with-ties numbers, chance-corrected metrics, and the wider literature |
| Noise floor and the 1,000-question figure | Module 1, 5.5 "Your noise floor" | The assumptions behind 1,000, clustered errors, and paired designs that need fewer items |
| Temperature 0 is not deterministic | Module 1, 1.5 and 5.5 | Epochs, reducers, and the Anthropic temperature deprecation |
| Slice-first triage | Module 1, 6.3, `incident_drill.py` | Failure taxonomies that define the slices before an incident |

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
| Shankar and Husain book "Evals for AI Engineers" listed by O'Reilly for 31 Oct 2026 | not released yet | Google Books | Not citable as a source yet. |

## 4. Core concepts, with verified facts

### 4.1 Error analysis comes before metrics

Error analysis means reading real traces and writing down what went wrong before choosing any metric. Open coding is writing free-text notes on each trace. Axial coding is grouping those notes into a failure taxonomy, which is a named list of failure types. The metrics then follow from the taxonomy, not from a list of generic metrics.

- Hamel Husain and Shreya Shankar define open coding on their evals FAQ, modified 2026-09-13. Annotators "review and write open-ended notes about traces, noting any issues." **V**
- The same page says "Axial coding is the most important step." **V**
- Stopping rule: continue until "theoretical saturation", and "We recommend reviewing at least 100 traces." **V**. This is practitioner advice, not a measured result.
- The page says "Start by annotating at least 30 traces yourself before reviewing suggestions from an agent." **V**
- "Benevolent dictator": the FAQ says a single domain expert is "the most effective approach" for "most small to medium-sized companies". **V**. Opinion, not measured.
- Criteria drift: Shankar et al., "Who Validates the Validators?", UIST 2024, found that grading outputs changes the criteria people use. The study had n=9 practitioners. **V**, Section 1 and Section 6. The small n limits how far this generalises.
- In the same paper, EvalGen reached 66.46% alignment on a 100-item product pipeline, against 54.35% for SPADE. Alignment is the paper's harmonic mean of coverage and false failure rate. On the 84-item medical pipeline, both reached 48.29%. Source: Table 1. **V**

### 4.2 Judge construction: scale, protocol, and rubric

A judge is defined by its question format and its output format. Pointwise judges score one output. Pairwise judges pick the better of two outputs. Reference-based judges compare the output with a known good answer. The research shows a trade-off: pairwise is more sensitive but easier to fool.

- Binary pass/fail is recommended by Husain and Shankar. Their reasons: adjacent scale points are subjective, scales need larger samples, and raters default to the middle. Source: evals FAQ. **V** that they say it. The page cites no study.
- No primary study was found that compares binary labels with a Likert scale for judge-human agreement. **NC**, absence from one search.
- Li et al. 2026, arXiv 2601.03444, compared 0-5, 0-10, and 0-100 scales. Pooled human-LLM ICC was 0.853, 0.805, and 0.840. Conditions: 12 graduate raters, 6 LLMs, 6 benchmarks, temperature 1. Source: Table 2. **V**. No venue listed.
- Tripathi et al., COLM 2025, measured how often an added distractor flips the verdict. On MT-Bench, averaged over four open models: absolute scoring flipped 9.0% to 9.7% of cases, pairwise flipped 34.9% to 35.5%. Source: Table 2. **V**
- The cost of absolute scoring in the same paper: 84.6% to 93.2% ties on equal-quality pairs, against 2.4% to 7.3% for pairwise. Source: Table 3. **V**

### 4.3 Judge biases, measured

A bias is a systematic error that does not depend on answer quality. The three best-measured biases are position, verbosity, and self-preference. Their size depends strongly on the judge model.

- **Position, older judges.** Zheng et al. 2023, Table 2. 80 MT-Bench questions, two similar GPT-3.5 answers, both orders. Consistency: Claude-v1 23.8%, GPT-3.5 46.2%, GPT-4 65.0%. **V**
- **Position, extreme case.** Wang et al., ACL 2024, Table 2. ChatGPT judging Vicuna-13B against ChatGPT on 80 questions: the verdict conflicted after a swap in 66 of 80 cases, 82.5%. With GPT-4 as judge: 46.3%. **V**
- **Position, newer judges.** Shi et al., AACL-IJCNLP 2025, Table 2. Pairwise position consistency on MTBench: GPT-4 0.82, Claude-3.5-Sonnet 0.82, GPT-4o 0.76, Claude-3-Haiku 0.57. On DevBench, Claude-3-Haiku fell to 0.23. **V**. The paper says bias is "strongly affected by the quality gap between solutions". **V**
- **Verbosity.** Zheng et al., Table 3, "repetitive list" attack on 23 answers. Failure rate: Claude-v1 91.3%, GPT-3.5 91.3%, GPT-4 8.7%. **V**
- **Self-preference.** Zheng et al., Section 3.3: GPT-4 favoured itself by a 10% higher win rate, Claude-v1 by 25%. The authors say the study "cannot determine" whether this is a real bias. **V**
- Panickssery et al., NeurIPS 2024: GPT-4 was 73.5% accurate at recognising its own summaries. Self-recognition and self-preference correlated linearly. Conditions: XSUM and CNN/DailyMail, 1,000 articles each. **V**, Section 1, Figures 1 and 7.
- Wataoka et al., NeurIPS 2024 workshop: GPT-4 had a self-preference score of 0.520, the highest of 8 judges, on Chatbot Arena data. The paper links the bias to lower perplexity. **V**, Section 4.
- The Husain and Shankar FAQ says a same-model judge "is usually fine". See section 10 for this disagreement.
- **Judges fail on hard objective pairs.** JudgeBench, Tan et al., ICLR 2025, Table 1: vanilla GPT-4o scored 50.86% on 350 pairs, where random is 50%. With the Arena-Hard judge prompt, o3-mini high scored 80.86%. **V**. The pairs were generated by GPT-4o, and the authors say this biases against GPT-4o judges. **V**

### 4.4 Judge validation

A judge is itself a classifier, so it needs a labelled test set. TPR is the share of truly passing outputs that the judge passes. TNR is the share of truly failing outputs that the judge fails. Percent agreement is inflated by chance, so use a chance-corrected metric such as Cohen's kappa, and report TPR and TNR separately.

- The FAQ says: "Focus on achieving high True Positive Rate (TPR) and True Negative Rate (TNR) with your judge on a held out labeled test set." **V**
- **MT-Bench agreement is percent agreement, not correlation.** Zheng et al., Table 5. GPT-4 pairwise vs human, turn 1: 66% with ties, n=1343, and 85% without ties, n=859. Human vs human: 63% and 81%. Chatbot Arena, Table 6: 64% and 87%. Conditions: 58 expert labelers, about 3K votes. **V**
- **Percent agreement hides disagreement.** Thakur et al., GEM 2025: Llama-3 8B had Scott's pi of 59 while its percent agreement was above 80%. Conditions: TriviaQA, 13 judges, 1,200 human-labelled answers. **V**
- **Kappa example.** Wang et al., Table 4: vanilla GPT-4 reached kappa 0.24 against the majority of 3 annotators. With the paper's calibration and 20% human review, kappa was 0.56. The average single human reached 0.54. **V**
- **Correction of the measured pass rate.** The Rogan-Gladen estimator is θ = (p_obs + TNR − 1) / (TPR + TNR − 1). The `judgy` library by Shreya Shankar implements it, version 0.1.0, uploaded 2025-05-25. **V**, README and PyPI JSON.
- `judgy` source: it raises an error when TPR + TNR ≤ 1, and its bootstrap resamples only the labelled test set. So its interval ignores sampling error in the unlabelled set. Source: `src/judgy/core.py` lines 106 to 152, read at `main`, not at a tag. **V** for main. **I** that 0.1.0 matches.
- Worked example, **C**: TPR 0.9, TNR 0.8, observed pass rate 0.70 gives a corrected rate of 0.714.
- Lee et al. 2025, arXiv 2511.21140, give intervals that include error from both the test and calibration sets. Coverage was 95% to 99% with a GPT-4.1-mini judge and a 10% calibration split. Source: Table 1. **V**. No venue found.
- Fiedler 2026, arXiv 2605.06939, warns the corrected estimate "can have higher mean squared error than the naive estimate". Its variance grows as 1/J², where J = TPR + TNR − 1. **V**, Section 1. So a weak judge makes the correction noisy.

### 4.5 The claim "judges agree with humans at 0.6 to 0.85 correlation on most tasks"

**Verdict: partly supported.** The range fits strong judges on well-defined tasks. It does not fit "most tasks".

| Evidence | Metric | Value | Conditions | Label |
|---|---|---|---|---|
| JUDGE-BENCH, Bavaresco et al., ACL 2025, Table 1 | mean Spearman, graded labels | GPT-4o 0.50, others 0.30 to 0.44 | 11 LLMs, 20 datasets | V |
| JUDGE-BENCH, Table 1 | mean Cohen's kappa, categorical | GPT-4o 0.28, others 0.10 to 0.28 | same | V |
| JUDGE-BENCH, GPT-4o per dataset | Spearman | 0.82 ROSCOE-GSM8K, 0.35 SummEval, 0.17 WMT23 Zh-En | same | V |
| JUDGE-BENCH, GPT-4o per dataset | kappa | 0.84 LLMBar-natural, −0.24 DICES-990 | same | V |
| G-Eval, Liu et al., EMNLP 2023, Table 1 | Spearman | 0.514 average on SummEval | GPT-4 judge | V |
| G-Eval, Table 3 | Pearson | 0.599 average on QAGS | GPT-4 judge | V |
| Chiang and Lee, ACL 2023, Table 2 | Kendall tau | 0.12 to 0.43 | text-davinci-003, 400 stories, 3 teachers | V |
| Li et al. 2026, Table 4(b) | ICC | 0.596 to 0.816 per model | 0-5 scale | V |

- Correct phrasing for the course: strong judges reach about 0.6 to 0.85 on tasks with clear criteria. On subjective, safety, or expert-labelled tasks, values often fall to 0.2 to 0.5 or lower. Validate your own judge. **I**, from the table above.

### 4.6 Golden datasets and statistics

The width of the confidence interval decides what change a dataset can detect. Small sets need exact or Bayesian intervals. Comparing two versions on the same items needs a paired test. A power analysis tells you the dataset size before you build it.

- Miller, "Adding Error Bars to Evals", Anthropic, arXiv 2411.00640, gives five recommendations: CLT standard errors, clustered standard errors, resampling answers, paired differences, and power analysis. **V**, Section 1.
- Clustered standard errors were up to 3.05 times the naive ones on DROP, 1.88 on MGSM, and 1.10 on RACE-H. Source: Table 4. **V**. A cluster is a group of related questions, such as several questions on one document.
- The "at least 1,000 questions" figure uses Eq. 9 with ω² = 1/9, σ² = 0, δ = 0.03, 80% power, α = 0.05. It gives n ≈ 969. **V**, Section 5. ω² = 1/9 comes from a toy model with continuous scores. **V**
- For a binary pass rate the numbers are larger. **C**: 85% to 82% with two independent samples needs 2,402 items per arm. 50% to 47% needs 4,356 per arm.
- Paired designs need fewer items, **C**, McNemar sample-size approximation:
  - 5-point drop from 85%, discordance 0.10: 312 items. Independent samples: 906 per arm.
  - 10-point drop, discordance 0.20: 155 items. Independent samples: 250 per arm.
  - 3-point drop, discordance 0.10: 870 items.
  - Discordance is the share of items where the two versions disagree. It must be estimated from a pilot run.
  - A Monte Carlo check with the exact test gave 77% to 80% power, slightly below the 80% target.
- Bowyer et al., ICML 2025: at N=100, a nominal 95% CLT interval covered the true value only 92.5% of the time. They recommend Wilson or Beta-Bernoulli intervals for single pass rates, and Bayesian methods for paired and clustered data. **V**, Section 3.1, text re-checked in the PDF. They say they do not imply a hard threshold N.
- Worked example, **C**: 18 of 20 passes. The CLT interval is 0.769 to 1.031, which goes above 1. The Wilson interval is 0.699 to 0.972.
- Miller calls the bootstrap "unnecessary" for large evals. Bowyer finds that both CLT and bootstrap fail at small N. **V**. They studied different sizes. See section 10.
- Sizing advice from vendors: Anthropic says "20-50 simple tasks drawn from real failures is a great start" for early agent work, where effects are large. **V**, Demystifying evals. Anthropic's develop-tests page says "Prioritize volume over quality". **V**

### 4.7 Non-determinism and flaky evals

A flaky eval gives different results on the same code. The causes are sampling, server-side batching, and infrastructure. The fix is repeated trials with a stated reducer, not a lower temperature.

- Thinking Machines Lab, Horace He, 2025-09-10: Qwen3-235B-A22B-Instruct-2507, temperature 0, 1,000 completions of 1,000 tokens, gave "80 unique completions". With batch-invariant kernels, "all of our 1000 completions are identical". **V**. Already in Module 1, 5.5.
- Atil et al. 2024, arXiv 2408.04667 v5: GPT-4o few-shot on college math at temperature 0 and a fixed seed ranged from 44.0 to 88.0 accuracy over 10 runs. **V**, Table 2. Preprint.
- Anthropic's API reference says results at temperature 0.0 "will not be fully deterministic." **V**
- The same page says models released after Claude Opus 4.6 reject temperature values other than 1.0 with a 400 error. **V**
- Inspect AI 0.3.264 runs repeated trials with `epochs`. The default reducer is `mean`. Other reducers are `mode`, `majority`, `median`, `max`, `at_least`, `pass_at`, and `pass_k`. **V**, `scorer/_reducer/reducer.py` at the tag.
- pass^k is "the chance that all k i.i.d. task trials are successful, averaged across tasks". Source: τ-bench, Yao et al., Sierra, arXiv 2406.12045. **V**. On τ-retail, gpt-4o pass^1 was 61.2 and pass^8 was below 25%. **V**, Table 2 and Section 5.1. Module 12 teaches this in depth.
- Infrastructure noise: Anthropic measured a 6 percentage point gap on Terminal-Bench 2.0 between the most and least resourced setups, p < 0.01. **V**, Anthropic Engineering, 2026-02-05.

### 4.8 CI gates and regression suites

A CI gate is a check that blocks a merge when the eval result is too low. A regression suite is the set of cases that must keep passing. The gate must decide on an interval, not a point estimate, and it must fail when the eval does not run.

- promptfoo 0.123.0 exits with code 100 when a test fails or the pass rate is below `PROMPTFOO_PASS_RATE_THRESHOLD`, default 100. Source: `src/node/doEval.ts:1290-1305` at the tag, and the CLI docs. **V**
- promptfoo's CI docs show `eval --fail-on-error`, but the option is not defined in `src/commands/eval.ts` at 0.123.0. **V** for the absence. **I** that the command errors. Run it to confirm.
- Inspect AI: `--fail-on-error` is about sample errors, not scores. `inspect eval-set` exits 0 or 1 based on completion. No score-threshold flag was found. **I**, from `_cli/eval.py` at 0.3.264. A gate needs a script that reads the log.
- Inspect AI is the only checked tool that attaches `stderr()` to built-in scorers by default. **V**, `_metrics/std.py` at the tag. promptfoo, DeepEval, Braintrust, and LangSmith docs do not mention confidence intervals. **V**
- DeepEval 4.2.3: `deepeval test run` returns pytest's exit code. Metric threshold default is 0.5. **V**
- Braintrust: `bt eval` returns non-zero only "if any eval throws an exception". A score gate needs a custom `Reporter`. **V**, run-in-ci docs.
- GitHub required checks "must have a successful , skipped , or neutral status". **V**. So a skipped eval job passes the gate. A path filter that skips the eval job lets a prompt change merge unchecked. **I**

### 4.9 Benchmark contamination and broken benchmarks

Contamination means test items leaked into training data. A contaminated or broken benchmark rewards memory, not skill. Public benchmarks also measure a different task distribution from a support product.

- GSM1k, Zhang et al., Scale AI, NeurIPS 2024: drops of up to 8 points from GSM8k to a fresh 1,205-problem set. Yi-6B-Chat fell from 0.437 to 0.357. Frontier models showed "no signs of overfitting". **V**, Appendix F and Section 5.2.
- LiveBench, ICLR 2025, replaces 1/6 of questions each update, so it refreshes about every 6 months. **V**, Section 2.7.
- The Leaderboard Illusion, Cohere Labs and others, preprint 2025: Meta tested 27 private variants before the Llama 4 release. Training on Arena data raised ArenaHard win rate from 23.5% to 49.9%. **V**, abstract and Section 1.
- OpenAI evaluation best practices list "Vibe-based evals" and eval sets that do not "reproduce production traffic patterns" as anti-patterns. **V**
- Anthropic's develop-tests page: "Design evals that mirror your real-world task distribution." **V**

## 5. Proposed phase outline

| Phase | Title | What it teaches | Labs it needs | Runs where, costs what |
|---|---|---|---|---|
| 1 | Error analysis first | traces, open coding, axial coding, taxonomy, saturation, criteria drift | L1, L2 | laptop, offline, synthetic traces |
| 2 | Code checks and judges | assertion vs judge, binary vs scale, pointwise, pairwise, reference, rubric | L3, L4 | laptop offline with a mock judge. Optional live judge about $1 |
| 3 | Judge bias and validation | position, verbosity, self-preference, TPR, TNR, kappa, Rogan-Gladen | L5, L6, L7 | laptop offline. Optional live bias probe $1 to $3 |
| 4 | Golden sets and statistics | sizing, Wilson, clustered errors, paired McNemar, power, bootstrap limits | L8, L9, L10 | laptop, standard library or scipy |
| 5 | Noise and flaky evals | repeated trials, reducers, noise floor, infrastructure noise | L11 | laptop offline. Optional Ollama run, free |
| 6 | CI gates and regression suites | gate on the interval, exit codes, skipped jobs, tool choice and churn | L12, L13 | laptop, promptfoo and pytest, GitHub Actions free tier optional |
| 7 | Benchmarks vs product evals | contamination, broken benchmarks, leaderboard gaming, full eval plan | L14, L15 | laptop offline |

Seven phases, because most of the material is new. Module 1 used eval sets as a tool in 3.4, 4.4, 5.5, and 6.3. It did not teach failure discovery, judge design, judge validation, or dataset sizing. Phases 1 to 4 are new material. Phases 5 and 6 extend Module 1 sections 5.5 and 4.4. Phase 7 is short and can merge with phase 6 if time is tight.

## 6. Lab ideas

All labs run offline from the course `code/` folder unless marked. A seeded synthetic set of support conversations stands in for real traces. Each lab has a `--self-test` flag.

| Lab | What the script does and prints | Break-it variant | Self-test checks |
|---|---|---|---|
| L1 Open coding | Loads 120 synthetic traces. Writes one note per trace to CSV. Prints notes per trace. | Skip notes and use a generic "helpfulness" score. It misses the planted refund-policy failure. | The planted trace ids are found. |
| L2 Axial coding and saturation | Groups notes into types. Prints type, count, share, and new types per 10 traces. | Shuffle so a rare type appears late. | Saturation at the known trace count for the seed. |
| L3 Code check vs judge | Scores 200 outputs with a regex and with a mock judge of set TPR and TNR. Prints both pass rates. | A regex that passes an empty answer. | Known counts for the seed. |
| L4 Pointwise vs pairwise | Mock judge with a planted length preference. Prints flip rate after padding and tie rate for both protocols. | Remove the tie option. | Rates match planted values within tolerance. Optional live run, API key, about $1. |
| L5 Position swap | Runs each pair in both orders. Counts a verdict only when both agree. Prints consistency. | One order only. The win rate shifts. | A planted 30% first-position bias is recovered. |
| L6 Judge validation | From 150 human and judge labels, prints TPR, TNR, percent agreement, and Cohen's kappa. | 90% pass labels and a judge that always says pass. | That judge gets 90% agreement and kappa 0. |
| L7 Corrected pass rate | Rogan-Gladen with a bootstrap over both labelled and unlabelled sets. Compares with `judgy` 0.1.0. | TPR + TNR near 1. The interval becomes very wide. | TPR 0.9, TNR 0.8, observed 0.70 gives 0.714. |
| L8 Interval coverage | For N = 10, 20, 50, 100, draws 5,000 sets. Prints coverage of CLT, Wilson, Clopper-Pearson, and Beta intervals. | Use N = 10 with a true rate of 0.95. | 18 of 20 gives Wilson 0.699 to 0.972. |
| L9 Power calculator | Prints items needed for a drop, baseline, and discordance, for independent and paired designs, with a Monte Carlo check. | Assume discordance 0.02 when the pilot shows 0.15. | 85% to 80% independent gives 906 per arm. Paired at discordance 0.10 gives 312. |
| L10 Clustered errors | 50 documents with 6 questions each and a document effect. Prints naive and clustered standard errors. | Set the document effect to 0. | Ratio above 1.5 with the planted effect, near 1 without it. |
| L11 Noise floor and reducers | Mock model with per-item pass probability. Runs 1, 5, and 10 epochs. Prints mean, majority, pass@k, and pass^k. | Gate on one run. Count false alarms over 200 unchanged runs. | Known false-alarm count for the seed. Optional Ollama run, free. |
| L12 Gate on the lower bound | pytest suite that fails when the lower end of the paired interval is below −2 points. Prints SHIP or HOLD. | Gate on the point estimate. One candidate gets a false SHIP. | Known verdicts for three seeded candidates. Builds on Module 1 `quant_gate.py`. |
| L13 promptfoo gate | promptfoo 0.123.0 config with an offline provider. Shows exit code 100 and `PROMPTFOO_PASS_RATE_THRESHOLD`. | A workflow path filter skips the job, and the required check still passes. | Exit codes 0 and 100 for two configs. Needs Node.js. Free. |
| L14 Contamination probe | Toy n-gram model trained with and without leaked test items. Prints public and fresh scores and the gap. | Leak 20% of the fresh set too. | Gap is zero without leakage. |
| L15 Eval plan capstone | Template for a model switch: taxonomy, checks, judge numbers, sizes, gate rule. A checker lists missing fields. | Leave out judge validation. | The checker names the missing field. |

## 7. Failure stories and case studies

1. **SWE-bench Verified lost its signal.** OpenAI, 2026-02-23. OpenAI audited 138 problems that o3 did not solve consistently over 64 runs. 59.4% had material issues: 35.5% had narrow tests and 18.8% had wide tests. All tested frontier models could reproduce gold patches or problem details for some tasks. OpenAI stopped reporting the score. **V**, read in a browser by a research agent.
2. **The replacement failed too.** OpenAI, 2026-07-08. On the 731-task public SWE-Bench Pro split, human review found 34.1% of tasks broken. OpenAI wrote: "we retract our earlier recommendation to adopt SWE-Bench Pro." **V**, same method.
3. **Llama 4 on LMArena.** April 2025. Meta reported an experimental chat version at Elo 1417. LMArena said Meta "should have made it clearer" that the model was customised. **V**, LMArena quote from a secondary page. The Leaderboard Illusion reports 27 private Meta variants before release. **V**
4. **A judge that flips on order.** ChatGPT as judge changed its verdict in 66 of 80 pairs after a swap. Wang et al., Table 2. **V**
5. **Infrastructure changes the score.** Anthropic, 2026-02-05. Resource limits alone moved Terminal-Bench 2.0 by 6 points. The infra error rate fell from 5.8% at strict limits to 0.5% with no limits. **V**
6. **Silent threshold inversion.** DeepEval v4.2.0 made four metrics higher-is-better and told users to update thresholds. **V**, changelog. No incident report was found. The risk to CI gates is inferred. **I**

## 8. Primary sources

All fetched 2026-09-17. The number after each URL is the HTTP status from `curl -L`. Focus points and table numbers for each source are in section 4.

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
- **How to Correctly Report LLM-as-a-Judge Evaluations, Lee et al., 2025** — https://arxiv.org/abs/2511.21140 200. Table 1.
- **Bias and Uncertainty in LLM-as-a-Judge Estimation, Fiedler, 2026** — https://arxiv.org/abs/2605.06939 200. Section 1.
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

Versions re-checked on PyPI and npm on 2026-09-17.

| Tool | Current version | Release date | Source | Notes on breaking changes |
|---|---|---|---|---|
| promptfoo, Promptfoo Inc. | 0.123.0 | 2026-09-10 | npm | MIT. 0.122.0 dropped Node.js 20. 0.123.0 defaults GPT-5.6+ to the Responses API. Acquisition by OpenAI announced. |
| Inspect AI, UK AISI | 0.3.264 | 2026-09-17 on PyPI, changelog says 16 Sep | PyPI | MIT. Releases are frequent. Breaking changes in the last 12 months NC. |
| OpenAI Evals, hosted | n/a | deprecated 2026-06-03 | OpenAI deprecations page | Read-only 2026-10-31. Shutdown 2026-11-30. Do not use in labs. |
| openai/evals repo | no release | last commit 2026-04-14 per research agent | GitHub | Hygiene commits only. **I** |
| DeepEval, Confident AI | 4.2.3 | 2026-09-14 | PyPI | Apache-2.0. v4.2.0 inverted four metric scales. |
| Ragas | 0.4.3 | 2026-01-13 | PyPI | Apache-2.0. v0.4 replaced `evaluate()` with `@experiment()`. Repo now under vibrantlabsai. Low release activity. |
| Braintrust SDK | py 0.41.0, npm 3.34.0 | 2026-09-17 | PyPI, npm | MIT SDK. Self-hosting is Enterprise only. Six minor versions in September 2026. |
| autoevals, Braintrust | 0.3.0 | 2026-06-09 | PyPI | MIT per GitHub. |
| LangSmith SDK, LangChain | 0.12.6 | 2026-09-16 | PyPI | MIT SDK. Self-hosting is an Enterprise add-on. `LANGSMITH_TEST_TRACKING=false` keeps results local. |
| Langfuse SDK | 4.15.4 | 2026-09-16 | PyPI | MIT except `ee/` folders. Server v4.38.0. Cloud v3 endpoints and trace-level evaluators end 2026-11-16. |
| Arize Phoenix | 20.13.0 | 2026-09-16 | PyPI | Elastic License 2.0, not OSI open source. Many major versions in 12 months. v14 removed the legacy client. |
| arize-phoenix-evals | 3.8.0 | 2026-09-11 | PyPI | Elastic-2.0. |
| judgy | 0.1.0 | 2025-05-25 | PyPI | Only one release. Treat as reference code. |
| scipy | 1.18.1 | 2026-08-21 | PyPI | For exact binomial and McNemar tests. |
| statsmodels | 0.15.0 | 2026-08-27 | PyPI | Has `proportion_confint` with Wilson and `mcnemar`. Function names not checked at this tag. **NC** |

## 10. Open questions and disagreements

1. **Same-model judges.** The Husain and Shankar FAQ says a same-model judge "is usually fine", because the judge does a narrow task. Zheng, Panickssery, and Wataoka measured self-preference in open-ended preference tasks. No study was found on narrow binary checks. Suggested check: measure TPR and TNR for two judge models on the same labels.
2. **Binary vs scale.** Husain and Shankar recommend binary labels without a cited study. Li et al. 2026 found 0-5 best among 0-5, 0-10, and 0-100, but did not test binary. Open.
3. **Pairwise vs pointwise.** Pairwise gives far fewer ties. It also flips about 35% of the time under distractors, against about 9% for absolute scores, per Tripathi et al. The choice depends on whether the gate needs sensitivity or robustness.
4. **Bootstrap or not.** Miller calls the bootstrap unnecessary. Bowyer et al. show CLT and bootstrap both under-cover at small N. Miller did not test small N. Each is right in its own size range.
5. **How many items.** Anthropic suggests 20 to 50 tasks to start. Miller's arithmetic gives about 1,000 for 3 points under a toy variance. Binary rates need more. The first answers "find large failures". The second answers "detect small regressions".
6. **Correcting judge estimates.** `judgy` and Lee et al. apply Rogan-Gladen. Fiedler warns it can have higher error than the raw rate when J = TPR + TNR − 1 is small.
7. **Judge-human agreement.** MT-Bench reports over 80% agreement without ties. JUDGE-BENCH reports low mean correlation. The metric, the tie rule, and the task mix explain the gap. See 4.5.

## 11. Things I could NOT verify

1. **OpenAI blog pages** return HTTP 403 to curl. A research agent read both in a browser. The author of this dossier did not re-read them. Confirm by opening both URLs in a browser and searching for "59.4%" and "we retract".
2. **OpenAI's own promptfoo acquisition page** returned 403. The acquisition is confirmed only by Promptfoo's blog. Whether the deal closed is not checked.
3. **promptfoo `--fail-on-error`.** The absence of the option is verified in source. That the command fails is inferred. Run `npx promptfoo@0.123.0 eval --fail-on-error`.
4. **The LMArena statement** comes from a secondary page. The X post was not read.
5. **No study compares binary and Likert judge scales** in the searches run. A wider literature search would confirm the absence.
6. **Abstract-only sources:** PROMPTEVALS, Attune, The Comparative Trap, Prediction-Powered Inference, and the contamination survey by Xu et al.
7. **Figure-only values** were not extracted: Thakur per-judge Scott's pi, Wataoka scores for other models, Bowyer coverage curves apart from 92.5% at N=100, Zheng Table 4 values.
8. **Venues not found:** Lee et al. 2511.21140, Fiedler 2605.06939, Li et al. 2601.03444, Atil et al. 2408.04667, τ-bench.
9. **YouTube captions** for the Husain and Shankar talks returned no text. The only timestamps come from Lenny's show notes. Pull captions with a browser before quoting timestamps.
10. **judgy source** was read at `main`, not at a tag, because the repo has no tags checked. Compare with the 0.1.0 sdist.
11. **Breaking changes** in the last 12 months were not checked for Inspect AI, Braintrust, autoevals, or LangSmith. CI gate and interval support were not checked for Ragas, Langfuse, or Phoenix.
12. **The McNemar sample-size formula** is attributed to Connor 1987, which was not fetched. The Monte Carlo check matched within 3 points of power.
13. **Anthropic trial-isolation wording** about git history was reported by a research agent and not re-checked by the author.
14. **statsmodels function names** at 0.15.0 were not checked.
15. **Enrolment numbers** for the Maven course conflict between pages: 700+ and 5,000+. Neither is verified.

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
- **Phase 7 is the one to merge** into phase 6 if the module runs long.

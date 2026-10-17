# Module 17: Guardrails architecture

Research date: 2026-09-25. Status: research dossier, not course material. Reviewed on 2026-09-25 by an independent reviewer. Section 10, Review log, lists every correction.

Module question, from `_curriculum/README.md` line 341: **Your classifier adds 300 ms to every request and still misses attacks. What belongs inline, and what belongs after?**

## How this dossier was built

- **Inputs.** Two research reports written on 2026-09-25 in `S/reports/`: `research_guardrails_models.md` and `research_guardrails_layers.md`. Below they are the models report and the layers report.
- **Path short names.** `S/` means the research scratchpad. `RGM/` means `S/research_guardrails/models/`. `RGL/` means `S/research_guardrails/layers/`. `D17/` means `S/dossier_m17/`, the dossier author's notes.
- **Other inputs.** The Module 17 brief in `_curriculum/README.md` lines 338 to 352. The rules in `S/briefs/BRIEF_research.md`, `research-method.md` and `writing-style.md`. The structure of `_curriculum/module-10-memory.md`.
- **Work done for this dossier.** No lab ran. No URL was fetched. The dossier author did four read-only things:
  1. Re-grepped 126 anchors of section 4 in their saved files. Script `D17/anchor_check.py`, output `D17/anchor_check.txt`. **126 of 126 anchors match their expected count.** 103 check an exact count of 1 or more. 20 check a minimum of one hit. 3 are absence checks, such as the word "timeout" in the SDK approval docs. Every concept passes all its anchors. The per-concept counts are at the end of `D17/anchor_check.txt`.
  2. Re-ran the two prototype self-tests. `RGM/proto/blocks.py` printed "self-test OK" in 0.03 s. `RGL/proto/layered_pipeline.py --self-test` printed "16 of 16 checks passed" in 0.65 s. Python 3.9.6, the learner's Apple arm64 Mac, 2026-09-25.
  3. Recomputed every arithmetic claim. Script `D17/recompute.py`, output `D17/recompute.txt`. Section 5.8 lists the results. Seven report statements changed. Section 7 lists them.
  4. Read the built phases that Module 17 must link to, and grepped `study-material/` for promises made to Module 17. Section 2.
- **Labels.** Every claim is **verified**, **verified by run**, **inferred** or **not checked**. A verified claim names its file and line, or its table. "Verified by run" means a research agent ran a script on 2026-09-25 on the learner's Mac, and the output file is named. An inferred claim names its basis and the check that would confirm it. **Vendor number** marks a number that a company published about its own product, on data it chose.
- **Run conditions for every laptop number.** Apple M4 Pro, 14 cores, 24 GiB RAM, macOS 26.6, arm64. Timing runs used `torch` 2.14.0 and `transformers` 4.57.6 on Python 3.12, with 10 CPU threads, batch size 1, 3 warmups and 20 timed runs.
  - The output files record only the platform, `torch` 2.14.0, 10 CPU threads and MPS available. `RGM/proto/time_hap_output.txt` lines 3 and 4.
  - The `transformers` version, Python 3.12, the warmups and the run count come from the script. `RGM/proto/time_local.py` lines 12 and 26.
  - The chip, core count and RAM come from the models report line 278, `sysctl hw.memsize`. They are not in the timing output.
  - Qwen3Guard ran in fp32 on CPU and fp16 on MPS. `time_local.py` line 87.
  - Simulation runs used Python 3.9.6, standard library only. Other load on the machine was not recorded. Not checked.
- **Terms used in the whole dossier.**
  - **Guardrail**: a check in the request path that can block, change or pause one request, one response or one tool call.
  - **Guard model**: a classifier that reads a prompt or a response and returns safe or unsafe, sometimes with a category.
  - **Hazard model**: a guard model trained on a harm taxonomy, such as violence or weapons. Llama Guard, ShieldGemma and Qwen3Guard are hazard models.
  - **Jailbreak or injection classifier**: a guard model that flags attempts to override instructions. Prompt Guard 2 is one. Module 16 owns the attack side.
  - **Encoder classifier**: a small model, such as DeBERTa, that reads the input once and outputs a score. It writes no tokens.
  - **Generative guard**: a language model that writes its verdict as text, such as "Safety: Unsafe".
  - **Recall or TPR**: the share of truly unsafe items that the guard flags.
  - **FPR**: the false-positive rate. The share of truly safe items that the guard flags. **Specificity** is 1 minus FPR.
  - **Base rate**: the share of real traffic that is truly unsafe.
  - **Precision**: the share of flagged items that are truly unsafe.
  - **Inline**: the check runs before the user sees the result or before the side effect happens. It adds latency.
  - **Asynchronous or after**: the check runs in parallel with the response, or after it. It adds no latency. It cannot stop what already happened.
  - **Cascade**: a cheap first stage screens all traffic and escalates some of it to an expensive second stage.
  - **Fail open**: when the check crashes or times out, the request continues unchecked. **Fail closed**: the request is blocked.

---

## 1. Purpose and the module question

Module 16 teaches the threat model and why detectors fail against adaptive attackers. This module teaches the runtime check layer: which checks run where, what each costs in latency and false blocks, and what happens when a check fails.

The short answer: **inline is for checks that are cheap and that must stop something before it happens. Everything expensive goes after, or behind a cheap first stage.**

A 300 ms classifier on every request is a deployment choice or a model-class choice, not a law. The same DeBERTa classifier takes 7.65 ms on an AWS g5.xlarge GPU with ONNX and 421.46 ms on an Azure Standard_D4as_v4 VM without it. That VM's vCPU count is not in the saved source. Not checked.

| Part of the question | Short answer | Where |
|---|---|---|
| Why 300 ms | A generative guard, a reasoning mode, or an encoder on a small CPU without ONNX. An encoder classifier costs 2.7 to 9.4 ms on the learner's CPU. A 0.6B generative guard costs 400 to 593 ms on the same CPU | 4.4, 4.5 |
| Why it still misses attacks | Published recall is often measured at a tuned threshold on the vendor's data. At a low FPR, recall falls to single digits. Cheap classifiers collapse out of distribution. Stacked layers miss the same attacks. Adaptive attacks are Module 16, built section 3.3 | 4.3, 4.6, 4.11 |
| What its false blocks cost | At 0.1% harmful traffic, most blocks are false. Llama Guard 4 blocks are 1.06% correct. The FPR you get depends on your benign traffic | 4.1, 4.2 |
| What belongs inline | Regex and schema checks, which cost microseconds. A small encoder classifier. A deterministic policy check on tool arguments, right before the side effect. An approval pause before an irreversible action | 4.5, 4.8, 4.14, 4.15 |
| What belongs after | An LLM judge on the whole exchange. Sampling for review. Human review of flags. Stream cut-off for text that can be shown and then stopped | 4.7, 4.8 |
| What can hide the 300 ms | Run the input check at the same time as the model call. The added latency is then the slower of the two, not the sum. This is safe only when no tool runs and no text is shown before the verdict | 4.7 |
| What goes in between | A cascade. The cheap stage escalates instead of blocking, so it can have a high FPR. The strong stage runs on a few percent of traffic | 4.9, 4.10 |
| What happens when the check fails | Products differ. Azure OpenAI content filtering fails open. NeMo Guardrails fails closed on streaming since 0.24.0. An OpenAI Agents SDK tool guardrail allows by default | 4.12 |
| Who picks the policy | Every framework stores the policy as a named config. None binds it to a tenant for you. The enforcement point decides whether a tenant can skip it | 4.13 |

Summary: put the cheap checks and the side-effect gate inline, put the judge after or behind a cascade, and measure FPR on your own benign traffic.

## 2. Scope

### 2.1 In scope

- Open guard models and their published evaluation: recall, FPR, F1, and the benign sets behind them.
- Latency of guard models, with hardware, serving engine and input length.
- Base rate, precision and blocks per day.
- Layer placement: inline, parallel, streaming, asynchronous, cascade.
- Schema validation as a layer.
- Per-tenant policy: how it is expressed and where it is enforced.
- Fail-open and fail-closed defaults. Frameworks: NeMo Guardrails 0.24.1, the OpenAI Agents SDK 0.22.3, Guardrails AI 0.11.0 and LLM Guard 0.3.16. Services: Azure OpenAI, Amazon Bedrock and the Anthropic API.
- Escalation to a human or to another model as a safety control.
- Versions and defaults on 2026-09-25.

### 2.2 Out of scope, and the owner of each item

| Topic | Owner |
|---|---|
| Threat model, trust boundaries, lethal trifecta, injection taxonomy, exit channels | Module 16, built. `security/security-phase-01-threat-model.md` sections 1.1 to 1.4 and `security-phase-02-channels.md` sections 2.1 to 2.4 |
| ASR measurement, its denominator, retries that are not independent | Module 16, built. `security-phase-03-measure.md` sections 3.1 and 3.2 |
| Detector limits against adaptive attackers, Prompt Guard 2 detection numbers | Module 16, built. `security-phase-03-measure.md` section 3.3, "A fixed attack set cannot test a defence". This module repeats no detection number |
| A detector threshold trades ASR against blocked benign work. A per-segment FPR becomes a larger per-task block rate | Module 16, built. `security-phase-03-measure.md` section 3.4, "Every detector threshold blocks benign work too" |
| Zero of n gives an upper bound near 3/n | Module 16, built, section 3.5. Module 11, built section 5.1, owns the Wilson interval |
| Design patterns that make an injection harmless, CaMeL, FIDES | Module 16, built. `security-phase-04-designs.md` sections 4.1 to 4.4, starting with "Only the design can promise no consequential action" |
| Toy detector against adaptive search, detector utility cost per threshold | Module 16, built. Phase 3 lab, `detector_cost.py` |
| A gate must fail when the eval does not run | Module 11, built section 6.3 |
| Prefill and time to first token. Streaming timeouts. Fallbacks | Module 1, built sections 1.2, 5.1 and 5.6 |
| The tail sampler never sees the judge's verdict | Observability module, `observability-ops-phase-02-pipeline.md` section 2.3 |
| The strictest rule wins | Module 7, built section 2.1 |
| A failed hook lets the call run, in the CLI | Module 7, built section 2.3 |
| Approval fatigue: people approve almost every prompt | Module 7, built section 5.1 |
| The stack protects only through its fail-closed layers | Module 7, built section 5.3 |
| Strict mode checks shape, not meaning | Module 6, built section 1.3 |
| Durable approval, and every wait needs a timeout branch | Module 9, built sections 4.1 to 4.3 |
| Judge as a classifier: TPR, TNR, validation, prevalence effect on agreement | Module 11, built sections 3.1 to 3.5 |
| Online-eval sample floor, judge cost per day, and "an online eval cannot stop a refund" with the input tool guardrail on `refund_order` | Module 12, built sections 5.1, 5.2 and 5.3 |
| Model routing cascades for cost, and the random-escalation control | Module 1, built section 3.4. Module 14 dossier |
| Grounding checker precision and recall as a gate | Module 4, built section 6.6 |
| Faithfulness gate: turning a gate pass rate into a rate | Module 11, built section 4.4 |
| Audit records and retention | Module 18, planned |
| Approval screen design | Module 19, planned |
| Harmful-content red teaming, attack strings | Not covered |

### 2.3 Overlap with built headings

Headings were read with `grep '^## '` on `study-material/*/*.md` on 2026-09-25. The dossier author wrote that Modules 13 to 16 have only dossiers. That is wrong for Module 16. The reviewer found five built phase files in `study-material/security/` on 2026-09-25 and read their headings and section 3.4. The first four rows below come from that review.

| Built heading | What it owns | What this module adds |
|---|---|---|
| Module 16, "3.4 — Every detector threshold blocks benign work too" | The threshold trade between ASR and blocked benign work. Per-segment FPR to per-task block rate, 1 − (1 − f)^m. Prompt Guard 2 "APR @ 3% utility reduction" | Base rate to precision to blocks per day, 4.2. Recall at a fixed FPR across hazard guards, 4.3. Link 3.4. Do not re-teach the threshold sweep |
| Module 16, "3.5 — Zero red-team successes bound one attacker only" | The zero-of-n bound, 1 − 0.05^(1/n), and the rule of three | The same bound applied to benign samples, 4.1 and 5.5. Link 3.5. Teach only the benign sample sizes |
| Module 16, "4.1 — Only the design can promise no consequential action" | Design over detection for injection | The placement rule for a check that guards a side effect, 4.8. Link 4.1 |
| Module 16 vocabulary, section 3.4 | Module 16 calls a deterministic code check a "guard" and a classifier a "detector". It says Modules 12 and 17 call a request-path check a "guardrail" | This dossier uses "guard model" for a classifier. The course writer must state the mapping once, in the terms list |

The rows below come from the dossier author.

| Built heading | What it owns | What this module adds |
|---|---|---|
| Module 12, "5.3 — An online eval cannot stop a refund" | The OpenAI SDK `run_in_parallel=True` default. The input tool guardrail on `refund_order`. An online eval counts but cannot block | The same trade in NeMo, Bedrock and Azure streaming, 4.7. Link 5.3 for the SDK default. Do not re-teach it |
| Module 12, "5.1 — The drop and the judge's TPR and TNR set a sample floor" and "5.2 — A judge on a long trajectory costs real money" | Sampling arithmetic and judge cost per day | The async judge as a guardrail layer, 4.8. Link 5.1 and 5.2 for sampling |
| Module 7, "2.1 — The strictest rule wins, not the most specific" | Rule merging in the harness | Bedrock merges layered guardrails the same way, 4.13. Link only |
| Module 7, "2.3 — A hook that fails lets the call run, in the CLI" and "5.3 — The stack protects only through its fail-closed layers" | Fail-open hooks and the fail-closed wrapper | Product defaults for fail open and fail closed, and their cost in false blocks, 4.12 |
| Module 7, "5.1 — People approve almost every permission prompt" | Approval rates | Where the guardrail runs relative to the approval, 4.15 |
| Module 6, "1.3 — Strict mode checks shape, not meaning" | Shape against meaning | Schema validation as the cheapest layer, and its re-ask default, 4.14 |
| Module 9, "4.3 — Every wait needs a timeout branch" | Durable waits | The SDK approval docs name no timeout, 4.15. Link 4.3 |
| Module 11, "3.1 — A judge is a classifier: report TPR and TNR" and "3.2 — One agreement number can praise a useless judge" | Judge validation and the prevalence effect on agreement | Base rate turns a guard's FPR into blocks per day, 4.2. Link 3.1 for the confusion matrix |
| Module 4, "6.6 — A grounding checker trades recall for precision" | Precision and recall of one gate, threshold by cost | Recall at a fixed low FPR across guard models, 4.3 |
| Module 11, "4.4 — A gate threshold does not give you a rate" | The faithfulness gate offline | Where it runs in production and what it costs. Promised to this module. Not researched. Gap 3 |
| Module 1, "3.4 — Routing cascades (quality per dollar, and the control group)" | Cost cascades for answer quality | Safety cascades, where stage 1 escalates instead of refusing, 4.9 |

### 2.4 Promises made to Module 17

Found with `grep -rn "Module 17"` over `study-material/` on 2026-09-25.

| # | Promise | Made in | Paid in |
|---|---|---|---|
| 1 | Guardrail architecture, inline classifiers, their latency and false-positive rates | `agent-evals/course.json` lines 87 and 441. `agent-evals-phase-05-online.md` line 64 | 4.1 to 4.10 |
| 2 | The rate of a block that also stops allowed refunds | `agent-evals-phase-05-online.md` line 537 | 4.2 gives the arithmetic. A measured rate for a refund guardrail does not exist. Gap 4 |
| 3 | Where the faithfulness gate runs in production, its latency and cost | `eval-engineering/course.json` lines 60 and 399. `eval-engineering-phase-04-faithfulness.md` line 583. `module-11-eval-engineering.md` line 40 | Not paid. Gap 3 |
| 4 | Guardrail pipelines, inline classifier latency, hazard models, per-tenant policy | `security/course.json` line 75 | 4.1 to 4.13 |
| 5 | Harmful-content safety evals | `security/course.json` line 563 | Partly. 4.1 to 4.3 cover guard evaluation. Harmful-content red-team sets are not covered |
| 6 | Guardrail classifiers as a product | `agent-harness/course.json` line 61. `module-07-agent-harness.md` line 59 | 4.5, 4.16 |
| 7 | Guardrail products as a layer | `advanced-retrieval/course.json` line 33. `module-04-advanced-retrieval.md` line 62 | 4.7, 4.13 |

---

## 3. Sources, with dates, tags and versions

All sources were fetched on 2026-09-25 by the two research agents. HTTP 200 unless noted. Rank uses the scale in `research-method.md`: 1 is code at a tag, 2 is versioned docs, 3 is a paper, 5 is a vendor post with conditions.

### 3.1 Code and docs at release tags

| Source | Tag or version | Files read | Rank |
|---|---|---|---|
| OpenAI Agents SDK | v0.22.3, PyPI 2026-09-17 | `docs/guardrails.md`, `docs/human_in_the_loop.md`, `src/agents/guardrail.py`, `tool_guardrails.py`, `run_internal/guardrails.py`, `run_internal/tool_execution.py`, `tool.py` | 1, 2 |
| NeMo Guardrails, NVIDIA | v0.24.1, PyPI 2026-09-16 | `nemoguardrails/rails/llm/config.py`, `llm/output_parsers.py`, `library/content_safety/actions.py`, `server/api.py`, `CHANGELOG.md` | 1 |
| Guardrails AI | v0.11.0, PyPI 2026-08-14 | `guardrails/validator_base.py`, `types/on_fail.py`, `guard.py`. `validator_base.py` also at v0.4.5, v0.5.0 and v0.6.0 to v0.10.0 | 1 |
| LLM Guard, Protect AI | v0.3.16, PyPI 2025-05-19. Archived 2026-07-08 | `evaluate.py`, `input_scanners/prompt_injection.py`, `docs/input_scanners/prompt_injection.md`, `docs/get_started/best_practices.md`. README on `main`. Commits Atom feed | 1, 2 |
| Amazon Bedrock Guardrails docs | current, fetched 2026-09-25 | streaming, permissions by ID, enforcements, tiers, CloudWatch metrics, pricing | 2 |
| Azure OpenAI content filtering | current. The `ai-foundry` URL 301-redirects to `foundry-classic` | content filter, content streaming, Content Safety overview, Prompt Shields | 2 |
| Anthropic API docs | current | refusals and fallback, handling stop reasons, mitigate jailbreaks, pricing | 2 |

### 3.2 Papers and independent benchmarks

| Title | Org | Date and status | URL | What to read |
|---|---|---|---|---|
| Benchmarking guardrail models for safety, refusal, and latency | Artificial Analysis. The page says "In partnership with NVIDIA" | 2026-06-11. Not peer reviewed | https://artificialanalysis.ai/articles/guardrail-safety-benchmark | Methodology. The embedded model JSON, extracted to `RGM/src/aa_models_table.txt` |
| What Do Compliance Detectors Read? | Lexsi Labs | arXiv 2608.16852v1, 2026-08-17. Preprint | https://arxiv.org/abs/2608.16852 | Table 24 benign over-flagging. Table 14 latency |
| Benchmarking Open-Source Safety Guard Models | Domyn | arXiv 2605.28830v1. ICLR 2026 workshop, per its footnote | https://arxiv.org/abs/2605.28830 | Tables 1, 3 and 4 |
| Granite Guardian | IBM | arXiv 2412.07724, 2024. Preprint | https://arxiv.org/abs/2412.07724 | Appendix D, Table 11 |
| Qwen3Guard Technical Report | Alibaba Qwen | arXiv 2510.14276, 2025-10-17. Preprint | https://arxiv.org/abs/2510.14276 | Table 2, the Stream section |
| A Lightweight Explainable Guardrail for Prompt Safety, LEG | University of Arizona. Partly funded by an NVIDIA grant | arXiv 2602.15853, 2026. Preprint | https://arxiv.org/abs/2602.15853 | Appendix G, Table 8 |
| Do You Really Need a GPU to Guard Your LLM? | BITS Pilani, Trustwise | arXiv 2512.19011. The PDF says USENIX ATC '26. Venue not checked | https://arxiv.org/abs/2512.19011 | Table 7, section 6.1 |
| Constitutional Classifiers++ | Anthropic | arXiv 2601.04603v1, 2026-01-08. Preprint | https://arxiv.org/html/2601.04603v1 | Sections 4 and 6 |
| Next-generation Constitutional Classifiers | Anthropic | 2026, research post | https://www.anthropic.com/research/next-generation-constitutional-classifiers | Cascade, compute overhead |
| Constitutional Classifiers | Anthropic | 2025-02-03, research post | https://www.anthropic.com/research/constitutional-classifiers | 23.7% compute, 0.38% refusal increase |
| Measuring the Effectiveness and Performance of AI Guardrails | NVIDIA | 2025-03-03, vendor blog | https://developer.nvidia.com/blog/measuring-the-effectiveness-and-performance-of-ai-guardrails-in-generative-ai-applications/ | Tables 1 and 2 |
| Aegis 2.0 | NVIDIA | arXiv 2501.09004, 2025 | https://arxiv.org/abs/2501.09004 | Note on in-domain sets, line 720 |
| XSTest | Röttger et al. | NAACL 2024 | https://arxiv.org/abs/2308.01263 | 250 safe prompts |
| OR-Bench | UCLA, UC Berkeley | ICML 2025 | https://arxiv.org/abs/2405.20947 | Section 3.2.3, label ensemble |
| WildGuard | AI2 | arXiv 2406.18495, 2024 | https://arxiv.org/abs/2406.18495 | WildGuardTest |
| ShieldGemma paper | Google | arXiv 2407.21772, 2024 | https://arxiv.org/abs/2407.21772 | Grepped only. No FPR or latency |

### 3.3 Model cards. Vendor numbers on vendor-chosen data

| Card | Org | Date | What it reports | Local file |
|---|---|---|---|---|
| Llama Guard 4 12B | Meta | Hugging Face 2025-04-23, gated | R, FPR, F1 on an "in-house test set" | `RGM/src/lg4_card.md` |
| Llama Guard 3 8B | Meta | 2024 | F1, AUPRC, FPR, Table 1 | `RGM/src/lg3_8b_card.md` |
| Llama Prompt Guard 2 86M and 22M | Meta | 2025 | AUC, recall at 1% FPR, latency on A100 | `RGM/src/pg2_86m_card.md` |
| ShieldGemma | Google | "Last updated 2025-02-25" | "Optimal F1" and AU-PRC only | `RGM/src/shieldgemma_card.txt` |
| Granite Guardian 4.1 8B | IBM | Hugging Face 2026-04-16 | F1. Intended use, lines 459 and 460 | `RGM/src/gg41_readme.md` |
| Granite Guardian HAP-38M | IBM | Hugging Face 2024-09-05 | Hate, abuse, profanity only | `RGM/src/gg_hap38m_readme.md` |
| Nemotron-3.5-Content-Safety | NVIDIA | Hugging Face 2026-05-22 | "FP Rate" on MMMU, DocVQA, AI2D | `RGM/src/nemotron35_cs_readme.md` |
| Shieldstral 1.0 3B | Mistral | Hugging Face 2026-07-16, blog 2026-08-04 | F1 only | `RGM/src/shieldstral_readme.md` |
| gpt-oss-safeguard 20B | OpenAI | card updated 2026-01-14 | No numbers | `RGM/src/gptoss_safeguard_readme.md` |
| Introducing gpt-oss-safeguard | OpenAI | 2025 | Not read. HTTP 403 to curl | none |

### 3.4 What changed recently

| Date | Change | Source | Why it matters |
|---|---|---|---|
| 2025-04-23 | Llama Guard 4 12B released | Hugging Face API | Meta's latest hazard guard. No Meta guard release since, per the models report |
| 2025-08-08 | NeMo 0.15.0 adds parallel rails | `RGL/src/nemo_CHANGELOG.md` | Before this, rails ran only in sequence |
| 2025-09-23 | Qwen3Guard Gen and Stream, 0.6B to 8B, ungated | Hugging Face API | Strict and loose modes. A token-level stream head |
| 2026-01-08 | Constitutional Classifiers++: probe first stage, flag rate 0.05% | arXiv 2601.04603v1 | A cascade makes a strong judge affordable on all traffic |
| 2026-03-06 | Nemotron-3-Content-Safety | Hugging Face API | 27 ms mean on B200, FPR 0.18 in the Artificial Analysis run |
| 2026-04-16 | Granite Guardian 4.1 8B with think and no-think modes | Hugging Face API | Thinking mode: 1,313.6 ms mean on B200 |
| 2026-05-22 | NeMo 0.22.0 `speculative_generation`, default off. Nemotron-3.5-Content-Safety | CHANGELOG. `config.py` lines 359 to 366 | NeMo now offers the parallel trade too |
| 2026-06-11 | Artificial Analysis guardrail benchmark, 20 rows on B200 | `RGM/src/aa_guardrail.txt` | First source found with recall, specificity and p95 latency for many guards on one GPU class |
| 2026-07-08 | LLM Guard repository archived | `RGL/src/llmg_readme_main.md` line 2. Commits feed | An often-cited toolkit is unmaintained |
| 2026-08-04 | Shieldstral 1.0 3B | Mistral blog | Policy as plain-language questions. F1 only |
| 2026-08-17 | Lexsi Labs benign over-flagging table | arXiv 2608.16852v1 | One guard's FPR spans 0.1% to 56.8% across benign sets |
| 2026-08-25 | NeMo 0.24.0 closes three silent-pass paths | CHANGELOG lines 38, 48, 49 | Streaming fails closed. Parse errors surface. `/v1/checks` returns 422 |
| 2026-09-17 | OpenAI Agents SDK 0.22.3 | PyPI | `pre_approval_tool_input_guardrails` documented |
| 2026-09-25, fetched | Bedrock `InvokeGuardrailChecks` lists prompt attack as a separate filter, $0.08 per 1,000 text units | `RGL/src/aws_bedrock_pricing.txt` lines 1617 to 1629 | A standalone prompt-attack classifier with a public price. API reference not fetched |
| 2026-09-25, fetched | Anthropic server-side fallback beta `server-side-fallback-2026-07-01` | `RGL/src/ant_refusals-and-fallback.txt` line 57 | Provider-side escalation to another model |

### 3.5 Versions to pin

Checked on PyPI and Hugging Face on 2026-09-25. `RGM/pypi_versions_2026-09-25.txt` and the layers report section 7.

| Package or model | Version | Released | Note |
|---|---|---|---|
| `openai-agents` | 0.22.3 | 2026-09-17 | Same pin as Module 12 |
| `nemoguardrails` | 0.24.1 | 2026-09-16 | Pin 0.24.0 or later for the fail-closed streaming fix |
| `guardrails-ai` | 0.11.0 | 2026-08-14 | `on_fail` default is `EXCEPTION` since v0.6.0 |
| `llm-guard` | 0.3.16 | 2025-05-19 | Archived. Use only to reproduce its benchmark table |
| `torch` | 2.14.0 | 2026-09-02 | Timing lab |
| `transformers` | 4.57.6 for the lab. Latest is 5.17.0 | 5.17.0 on 2026-09-09 | 4.57.6 was in the `uv` cache. Qwen3Guard needs 4.51.0 or later, per its card |
| `vllm` | 0.30.0 | 2026-09-22 | Artificial Analysis served guards with vLLM or SGLang. Not used in labs |
| `ibm-granite/granite-guardian-hap-38m` | created 2024-09-05 | | Ungated. `model.safetensors` 153,831,376 bytes |
| `Qwen/Qwen3Guard-Gen-0.6B` | created 2025-09-23 | | Ungated. `model.safetensors` 1,503,300,328 bytes |
| Llama Guard 4, Prompt Guard 2, ShieldGemma | 2024 to 2025 | | Gated. Manual approval |

---

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Each concept gives one best piece of evidence first, with its conditions. Every quote and number in a "Best evidence" line was re-grepped in its saved file. The anchor counts are in "How this dossier was built". Every quote is 25 words or shorter.

### 4.1 A guard's FPR belongs to the benign set, not to the model. One guard flags 0.1% of one benign set and 56.8% of another

- **Best evidence, verified.** Lexsi Labs, arXiv 2608.16852v1, Table 24. The caption says "Fraction of clearly-benign inputs flagged as violation, lower is better (N=250/1319/1000)". The columns are XSTest-safe, OR-Bench-hard and Alpaca/Dolly, in that order. `RGM/src/p2608_16852.txt` lines 2442 to 2490.

| Guard | XSTest-safe, N = 250 | OR-Bench-hard, N = 1,319 | Alpaca/Dolly, N = 1,000 | OR-Bench over Alpaca |
|---|---|---|---|---|
| Qwen3Guard-Gen 8B | 0.056 | 0.568 | 0.001 | 568x |
| WildGuard 7B | 0.012 | 0.751 | 0.003 | 250x |
| Llama Guard 3 8B | 0.032 | 0.193 | 0.002 | 96x |

- **Conditions.** Preprint. The paper's main task is compliance detection. Whether each guard used its default prompt-harm template for this table is not checked. The hardware is not named.
- **Recomputed, `D17/recompute.txt`.** "More than 500 times" holds for Qwen3Guard-Gen 8B only. Its Alpaca value is about 1 flagged prompt of 1,000. With 95% Wilson intervals, the ratio is at least 96x. So teach "about 100 to 570 times for one model", with the interval.
- **Recomputed by the reviewer.** The last column shows point ratios only. With the same Wilson method, the lowest ratio is 83x for WildGuard 7B and 24x for Llama Guard 3 8B. Script `review_recompute.py` in the reviewer's scratchpad. Teach the interval next to every ratio in that column.
- **Verified.** The authors call Llama Guard 3's low OR-Bench values "a floor artifact, not better calibration". The caption names both Llama Guard 3 1B and Llama Guard 3 8B. These classifiers "essentially never fire on OR-Bench's style regardless of content". So a low FPR can also mean a guard that rarely fires at all.
- **Verified, vendor claim.** The same vendor reports two FPRs for one model. Llama Guard 3 8B card, Table 1: FPR 0.040 on an internal English response set. `RGM/src/lg3_8b_card.md` line 143. The Llama Guard 4 card uses "an in-house test set" and gives "Δ FPR −3%" against Llama Guard 3. Inferred: that implies about 14% for Llama Guard 3 on the second set, if the delta is in absolute points. The card does not say. Not checked.
- **Verified.** NVIDIA estimates FPR on MMMU, DocVQA and AI2D and states: "We assume that these three benchmarks contain 100% safe inputs". `RGM/src/nemotron35_cs_readme.md` line 481. These are multimodal question-answering sets, not chat traffic.
- **Verified.** XSTest has 250 safe prompts. Three flags out of 250 give a 95% Wilson interval of 0.004 to 0.035. `RGM/proto/blocks_output.txt` section B.
- **Where it does not hold.** OR-Bench labels come from an LLM ensemble of three models. The OR-Bench paper estimates that some moderated prompts are still toxic, about 1.8% in its worked example. `RGM/src/orbench.txt` lines 396 to 440, per the models report 4.2. Not re-grepped by the dossier author. So part of an OR-Bench "FPR" may be label disagreement.
- **Home-field effect, verified.** Aegis 2.0 says "WGTEST and XSTEST are in-domain for WILDGUARD". `RGM/src/aegis2.txt` line 720. WildGuard's low FPR on XSTest is partly a result on its own training distribution.
- **Use it.** Measure FPR on a sample of your own benign traffic. Section C of `blocks.py` gives the size: 0 flags in 2,995 benign samples supports "FPR below 0.1%" at 95%.
- **Link.** Module 16 section 3.5 teaches the zero-of-n bound for attacks. Module 11 section 5.1 teaches the Wilson interval. This concept applies both to benign samples only. Do not re-derive them.

### 4.2 At a low base rate, most blocks are false, even for a good guard. At 0.1% harmful traffic, Llama Guard 4 blocks are 1.06% correct

- **Best evidence, verified by run.** `RGM/proto/blocks.py`, output `RGM/proto/blocks_output.txt` section A. Traffic 1,000,000 requests a day. Base rate 0.1%. Llama Guard 4 12B with TPR 0.629 and FPR 0.059 from the Artificial Analysis run. Result: 58,941 false blocks, 629 true blocks and 371 misses a day. Precision 1.06%.
- **Conditions.** The TPR and FPR come from the Artificial Analysis benign mix, which is WildGuardTest, ToxicChat and XSTest. Your own FPR will differ, per 4.1. The 0.1% base rate is an assumption. No source gives a production base rate for harmful prompts.
- **Recomputed.** The hand case: TPR 0.90, FPR 0.01, base rate 0.1%. That gives 9,990 false blocks and 900 true blocks. Precision is 900 ÷ 10,890 = 8.26%. `D17/recompute.txt`.
- **Verified by run.** At TPR 0.9 and FPR 0.01, precision falls from 90.91% at a 10% base rate to 0.89% at 0.01%. At 0.01% there are 111.1 false blocks per true block. `blocks_output.txt` section E.
- **Verified, same run.** On the Artificial Analysis benchmark mix, Llama Guard 4 12B has precision 0.733. `RGM/src/aa_models_table.txt`, the `precision` column. The benchmark mix has far more harmful prompts than 0.1%. So a benchmark precision does not predict production precision. Only the TPR and FPR carry over, and the FPR only with the caveat in 4.1.
- **The rule.** False blocks outnumber true blocks whenever FPR × (1 − base rate) is larger than TPR × base rate. At a 1% base rate and TPR 0.9, that means any FPR above about 0.91%. Recomputed by the reviewer: 0.9 × 0.01 ÷ 0.99 = 0.00909.
- **Recall first or FPR first, verified.** Domyn says "recall is the critical metric". `RGM/src/bench_osguard_2605.txt` line 22. Artificial Analysis says "Specificity matters most here", for consumer products. Both hold under their own cost of a miss. The base rate decides which cost is larger. Section 7, conflict c.
- **Link.** Module 11 section 3.1 owns the confusion matrix and TPR and TNR. Module 11 section 3.2 shows the prevalence effect on agreement. Module 16 section 3.4 owns the threshold trade and the per-task block rate. This concept adds only base rate to precision to blocks per day.

### 4.3 Vendors publish F1 or recall at a tuned threshold. At a fixed FPR of 0.1%, harm recall falls to single digits

- **Best evidence, verified.** IBM, Granite Guardian, arXiv 2412.07724, Table 11. TPR at FPR 0.1, 0.01 and 0.001, on IBM's aggregate harm benchmarks. `RGM/src/graniteguardian.txt` lines 2330 to 2420. The paper says: "Real-time applications have a strong need for low FPr."

| Guard | TPR at FPR 0.1 | TPR at FPR 0.01 | TPR at FPR 0.001 |
|---|---|---|---|
| Granite-Guardian-3.0-8B | 0.676 | 0.290 | 0.072 |
| Llama-Guard-3-8B | 0.648 | 0.320 | 0.033 |
| ShieldGemma-9B | 0.403 | 0.193 | 0.052 |

- **Conditions.** Preprint. IBM ran every row, so this is a vendor-run comparison on IBM's chosen benchmarks. Every number in the table is a vendor claim. It is the only source found that reports recall at a fixed low FPR for several hazard guards. The table row has eight numbers. The reading above takes the TPr columns, as the models report does.
- **Verified. What vendors publish.** All rows grepped in the saved cards, per the models report 1.3. Every number in this table is a vendor claim on the vendor's own set. The reviewer re-grepped the Llama Guard 4, Llama Guard 3, Prompt Guard 2, ShieldGemma and Qwen3Guard rows.

| Guard | FPR published? | What the vendor reports |
|---|---|---|
| Llama Guard 4 12B | Yes. 11% English, in-house set | R, FPR, F1 |
| Llama Guard 3 8B | Yes. 0.040, internal set | F1, AUPRC, FPR |
| Prompt Guard 2 | Only as "Recall @ 1% FPR", private set | AUC, recall at 1% FPR |
| ShieldGemma | No | "Optimal F1(left)/AU-PRC(right)" |
| Qwen3Guard | No | F1. The average uses "the optimal mode per benchmark" |
| Granite Guardian 3.0 paper | Yes, as TPR at fixed FPR | AUC, TPR at FPR 0.1, 0.01, 0.001 |
| Granite Guardian 4.1 | No | F1 |
| Nemotron 3 and 3.5 Content Safety | Yes, on sets assumed 100% safe | Accuracy, harmful F1, FP rate |
| Shieldstral 1.0 3B | No | F1 |
| gpt-oss-safeguard | No numbers | none |

- **Verified, vendor claim in a vendor preprint.** Qwen3Guard's headline average picks the better of strict and loose mode for each benchmark. Qwen3Guard-8B-Gen on ToxicChat scores F1 68.9 strict and 82.8 loose. `RGM/src/qwen3guard.txt` lines 510 to 537, Table 2. A deployment runs one mode. The file is binary PDF text. Use `grep -a` to search it.
- **Link.** Module 16 section 3.4 teaches how to pick a threshold from the utility you can afford. This concept adds only which hazard guards publish a number you can use for that.
- **Inferred.** "Optimal F1" in the ShieldGemma card means a threshold tuned per dataset. The card does not define it. Check: read the ShieldGemma paper's evaluation section.
- **Verified.** Meta does not compare Llama Guard 4 with rivals: "We omit evals against competitor models". `RGM/src/lg4_card.md` line 216.
- **Use it.** Ask for recall at the FPR you can accept, on your benign traffic. A single F1 hides both numbers.

### 4.4 A latency number without hardware, engine and input length cannot be compared. The guard's own template can set the input length

- **Best evidence, verified.** Prompt Guard 2 86M. Meta's card, a vendor claim: "Latency per classification (A100 GPU, 512 tokens)" is 92.4 ms. `RGM/src/pg2_86m_card.md` lines 71 and 74. The LEG authors, in a preprint, measured 9.47 ms on an H100, "sequentially on the WildGuardMix test set without batching". `RGM/src/leg_2602.txt` lines 2154 to 2259. That is a 9.8x gap for one model.
- **Conditions.** The GPUs differ. The input lengths differ. LEG does not state its input length. Meta states no engine or batch size. Meta's card gives the same 92.4 ms for Prompt Guard 1, line 73, which suggests a copied row. Inferred. Not checked.
- **Verified.** Artificial Analysis served guards "with vLLM or SGLang on B200-class GPU nodes". It sent 450 measured requests "with one request in flight at a time". `RGM/src/aa_guardrail.txt` line 118.
- **Verified.** In that run the mean input length ranges from 38 to 803 tokens. The hosted omni-moderation API has 38. Llama 3.1 Nemotron Safety Guard 8B v3 has 803. `RGM/src/aa_models_table.txt`. The difference is each model's template. So the latency column compares different input lengths.
- **Verified by run.** Qwen3Guard-Gen-0.6B's chat template turned a 32-token user message into 329 input tokens. The template adds 297 tokens. `RGM/proto/time_qwen_output.txt`. For short prompts, the template sets the latency floor.
- **Verified.** Two numbers in the LEG table are not measurements by LEG. Llama Guard 3 1B at 58.88 ms and ShieldGemma 2B at 57.87 ms "were taken from (Deng et al., 2025)". `RGM/src/leg_2602.txt` line 2159.
- **Verified.** Lexsi Table 14 reports Llama Guard 3 8B at 31.9 ms "measured in E-GUARDBENCH". No GPU is named. `RGM/src/p2608_16852.txt` line 1299. Artificial Analysis reports 21.3 ms mean for the same model on B200.
- **Use it.** Report every latency with GPU or CPU, engine, batch size, input tokens including the template, and mean or p50 or p95.

### 4.5 Only an encoder classifier fits a tight inline budget. A generative guard costs 54 to 148 times more on the laptop for the same user text, and a reasoning mode buys no recall

- **Best evidence, verified by run.** On the learner's Mac, batch size 1. `RGM/proto/time_hap_output.txt` and `time_qwen_output.txt`.

| Model and mode | Device | Input tokens | Median ms | p95 ms |
|---|---|---|---|---|
| Granite Guardian HAP-38M, encoder | CPU | 34 / 258 / 512 | 2.7 / 7.5 / 9.4 | 2.9 / 7.6 / 9.7 |
| Granite Guardian HAP-38M, encoder | MPS | 34 / 258 / 512 | 2.2 / 2.5 / 5.4 | 3.2 / 3.3 / 5.6 |
| Qwen3Guard-Gen-0.6B, generate 8 tokens, fp32 | CPU | 329 / 553 / 809 | 399.7 / 483.1 / 592.9 | 413.5 / 534.2 / 606.6 |
| Qwen3Guard-Gen-0.6B, prefill only, fp32 | CPU | 329 / 553 / 809 | 232.5 / 338.6 / 465.6 | 242.9 / 351.8 / 476.0 |
| Qwen3Guard-Gen-0.6B, generate 8 tokens, fp16 | MPS | 329 / 553 / 809 | 189.7 / 235.3 / 291.6 | 192.8 / 239.6 / 295.6 |
| Qwen3Guard-Gen-0.6B, prefill only, fp16 | MPS | 329 / 553 / 809 | 100.8 / 154.2 / 219.4 | 102.5 / 156.0 / 225.1 |

- **Recomputed.** Qwen3Guard-0.6B against HAP-38M: 148x on CPU at the shortest input, 86x on MPS at the shortest input. `D17/recompute.txt`.
- **Corrected by the reviewer.** The dossier gave 44x "on MPS at about 512 tokens". That pairs Qwen3Guard's 553-token input with HAP-38M's 512-token input. Qwen3Guard's 553 tokens hold only 256 tokens of user text, per `time_local.py` lines 31 and 91. For the same user text, the ratios are:
  - 32 tokens: 148.0x CPU, 86.2x MPS.
  - 256 tokens: 64.4x CPU, 94.1x MPS.
  - 512 tokens: 63.1x CPU, 54.0x MPS.
  So the range is 54x to 148x. 44x holds only when you compare equal total input tokens, template included.
- **Verified by run.** The HAP-38M output warns that a 1,121-token sequence exceeds the 512-token maximum. `time_hap_output.txt` lines 1 and 2. The script truncates to 512 before timing, `time_local.py` line 74. So the 512-token row is valid. A real message longer than 512 tokens needs chunking, and each chunk costs another call.
- **Conditions.** One machine, one run. Other load not recorded. HAP-38M covers hate, abuse and profanity only. It is not a jailbreak or hazard detector. Its card says it scores "the presence of hate speech, abuse, or profanity". So the comparison is by model class, not by task.
- **Link.** Module 1 section 1.2 owns prefill and time to first token. The prefill rows above only show that most of a 0.6B guard's cost is prefill. Do not re-teach prefill.
- **Verified, vendor benchmark of its own scanner.** The 300 ms class on a cloud CPU. LLM Guard `PromptInjection` benchmark, `docs/input_scanners/prompt_injection.md` at v0.3.16. Test setup "Input Length: 384", 5 runs, Python 3.11.6.

| Instance | Average ms | p95 ms |
|---|---|---|
| AWS m5.xlarge | 212.87 | 295.71 |
| AWS m5.xlarge with ONNX | 104.21 | 106.85 |
| AWS g5.xlarge GPU with ONNX | 7.65 | 13.28 |
| Azure Standard_D4as_v4 | 421.46 | 1,066.26 |

- **Verified.** The scanner's defaults are `use_onnx: bool = False` and the `deberta-v3-base-prompt-injection-v2` model. `RGL/src/llmg_pi.py` lines 131 and 146. So the default setup is the slow row. ONNX halves the latency on m5.xlarge: 212.87 ÷ 104.21 = 2.04x. The slowest average is 55x the fastest. Which model version the benchmark used is not stated. Not checked.
- **Verified.** Reasoning modes on B200 cost 4.5x to 22x more mean latency and change recall by less than 0.03. Artificial Analysis data, `RGM/src/aa_models_table.txt`. Recomputed:

| Guard | Mean ms, plain / reasoning | Recall change | Specificity change |
|---|---|---|---|
| Granite Guardian 4.1 8B | 59.1 / 1,313.6. 22.2x | −0.005 | −0.023 |
| Nemotron 3.5 Content Safety | 27.1 / 505.7. 18.7x | −0.029 | +0.009 |
| Nemotron Content Safety Reasoning 4B | 51.3 / 230.0. 4.5x | +0.007 | −0.009 |

- **Verified. The vendor agrees.** IBM's Granite Guardian 4.1 card positions the 8B guard for offline use. It says the main models suit "moderate cost, latency, and throughput such as model assessment, model observability and monitoring, and spot-checking". It points to HAP-38M for "stricter cost, latency, or throughput requirements". `RGM/src/gg41_readme.md` lines 459 and 460.
- **Where it does not hold.** On a B200, 7B to 12B generative guards without a reasoning mode run at 18.3 to 68.6 ms mean in the Artificial Analysis run. The low end is ShieldGemma 9B and the high end is WildGuard 7B, section 5.1. The dossier first wrote "8B guards, 18 to 69 ms". Corrected by the reviewer. With a dedicated GPU and a tuned engine, a generative guard can be inline. The laptop numbers are for teams without that.
- **Illustration only, n = 5.** Qwen3Guard-0.6B labelled "Where can I buy a knife for cutting vegetables?" as Unsafe. It labelled four other benign prompts with alarming words as Safe. This is not an FPR measurement.

### 4.6 A cheap CPU classifier that scores well in distribution can collapse out of distribution

- **Best evidence, verified.** arXiv 2512.19011, Table 7, jailbreak detection. Preprint. The PDF names a venue that was not checked. An SVM on word n-grams on CPU has in-distribution F1 0.964 at 3.4 ms. Out of distribution, on the D2 set, its recall is 0.270. `RGM/src/cpuguard_2512.txt` lines 688 to 780, per the models report 2.1.E. The dossier author re-grepped the 0.270 and the hardware.
- **Conditions.** CPU rows ran on a "32-core server with 503 GB RAM". GPU rows ran on an A100 80 GB PCIe. Batch size 1.
- **Verified.** The same paper's design keeps the cheap stage and adds a second: "the CPU stage resolves 80% of in-distribution" prompts. Line 149. This is a cascade, 4.9.
- **Verified.** HAP-38M covers hate, abuse and profanity only. A narrow cheap classifier misses every category it was not trained on.
- **Link.** Module 16 built section 3.3 owns adaptive attacks against detectors. The dossier first cited Module 16 dossier section 4.4. Distribution shift is a separate failure: no attacker needs to adapt.

### 4.7 "Blocking" defaults often are not. A parallel input guardrail can let tools run, and a stream-first output rail shows text before the check

- **Best evidence, verified.** NeMo Guardrails 0.24.1 sets `stream_first` to `True`. Its description: "If True, token chunks are streamed immediately before output rails are applied." `RGL/src/nemo_config.py` lines 386 to 389.
- **Verified.** OpenAI Agents SDK 0.22.3 sets `run_in_parallel: bool = True` for agent input guardrails. `RGL/src/oai_src_agents_guardrail.py` line 100. The docs say "the agent may have already consumed tokens and executed tools before being cancelled". Module 12 section 5.3 teaches this. Link, do not repeat.
- **Verified.** NeMo input and output rails default to sequential: `parallel` defaults to `False`. `config.py` lines 354 to 357 and 396 to 399. So NeMo's default input check blocks, and its default streaming output check does not.
- **Verified, re-fetched by the reviewer on 2026-09-25 at 03:24 UTC, HTTP 200.** Both services buffer by default. Bedrock: "In the default synchronous mode, guardrails will buffer and apply the configured policies". Azure: "In the default streaming scenario, completion content buffers". Bedrock page `docs.aws.amazon.com/bedrock/latest/userguide/guardrails-streaming.html`. Azure page `learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-streaming`.
- **Verified.** Bedrock and Azure offer the same trade as an opt-in. Bedrock asynchronous mode: "response chunks are provided immediately with no latency impact", but they "may contain inappropriate content until guardrails scan completes". `RGL/src/aws_gr_streaming.txt` lines 20 and 21. Azure's Asynchronous Filter signal "is guaranteed within a ~1,000-character window of the policy-violating content". `RGL/src/az_content_streaming.txt` line 49.
- **Verified.** Bedrock "doesn't support the masking of sensitive information with asynchronous mode". Line 24. The reviewer's re-fetch on 2026-09-25 shows the same sentence. The Azure ~1,000-character sentence and "zero latency associated with content filtering" are also unchanged.
- **Verified, added by the reviewer. NeMo's streaming window.** NeMo checks streamed output in chunks. The defaults are `chunk_size` 200 tokens and `context_size` 50 tokens. Streaming output rails are off by default: `enabled` defaults to `False`. `RGL/src/nemo_config.py` lines 377 to 384. So with `stream_first` on, up to about 200 tokens can reach the user before the check on that chunk. Inferred from the defaults. Not run. This is NeMo's counterpart to Azure's ~1,000-character window.
- **Verified, added by the reviewer. The parallel input check.** Three products run the input check at the same time as the model call:
  - OpenAI Agents SDK, `run_in_parallel=True`, above.
  - NeMo `speculative_generation`, default `False`. Its description says input rails "run concurrently with LLM generation". It is "Only supported for non-streaming generate_async() calls". With `stream_async()` it "falls back to sequential execution". `nemo_config.py` lines 359 to 366. Added in 0.22.0, `nemo_CHANGELOG.md` line 256.
  - Qwen3Guard-Stream: "The user's prompt is simultaneously submitted to both the LLM assistant and Stream Qwen3Guard". `RGM/src/qwen3guard.txt` lines 1866 and 1867. Vendor preprint.
- **Inferred rule.** A parallel input check adds the larger of the check time and the model time, not the sum. With a 300 ms check and a model whose first token takes longer, the check adds almost nothing. This holds only when no tool runs and no text reaches the user before the verdict. Check: lab G, extended with a parallel input check. Not run.
- **Verified.** A late stop still costs the tenant. Anthropic: "A mid-stream refusal bills the input tokens and the output already streamed at normal rates." `RGL/src/ant_refusals-and-fallback.txt` line 101. A refusal before any output is not billed.
- **Verified, vendor claim in a vendor preprint.** Qwen3Guard-Stream checks per token. It flags unsafe content "within the first 128 tokens in approximately 66.8% of cases" for traces with thinking. `RGM/src/qwen3guard.txt` lines 2915 and 2916. The test set is Qwen's own, 569 samples with thinking, line 2909. No millisecond latency is given. Figure 9 gives only relative time, lines 2951 to 2953.
- **Removed by the reviewer.** The dossier said "It needs two unsafe tokens in a row". The reviewer found no such rule in `qwen3guard.txt` or `qwen3guard_stream_readme.md`. Not checked. Do not teach it.
- **Verified. Other scope gaps.** OpenAI SDK input guardrails "run only for the first agent in the chain". Tool guardrails "do not apply to the handoff call itself". Built-in tools such as `ShellTool` "do not use this guardrail pipeline". `RGL/src/oai_docs_guardrails.md` lines 14 and 78.
- **Use it.** For each rail, write down three things: sequential or parallel, stream-first or buffered, and what it cannot see.

### 4.8 An async judge can use a bigger model and the whole exchange at zero added latency. It cannot stop a side effect or un-send text

- **Best evidence, verified by run.** `RGL/proto/layered_pipeline.py`, row B of `RGL/proto/run_fail_closed.txt`. The judge runs after the response on 100% of traffic. It found 794 attacks late. Those replies were already sent. Added p95 latency is 106.9 ms, the classifier alone.
- **Conditions.** 200,000 simulated requests, 2% attacks, 30% evasive, classifier availability 99.5%, seed 42. All recall and FPR values are assumptions. Section 5.6.
- **Verified. What async buys.** Azure: "zero latency associated with content filtering". Anthropic's exchange classifier sees input and output together. It "cut successful jailbreaking attempts by more than half", "at the cost of a 50% increase in compute". `RGL/src/ant_ccpp.txt` line 27.
- **Verified. Sampling.** LLM Guard best practices: "Run slower scanners on a sample of requests to reduce the overall latency." `RGL/src/llmg_bench_docs.md` line 21. Module 12 sections 5.1 and 5.2 own the sample-size and cost arithmetic. Link.
- **Verified by run. The cost.** In row B, each async flag goes to a human at an assumed $1. Human review is $13.75 of the $15.49 per 1,000 requests. Row B costs 8.9 times row A. The human queue, not the judge, is the cost.
- **Inferred design rule.** Put the check that guards a side effect inline, right before the side effect. Put the expensive judge after the response, or behind a cascade. A tool that moves money must wait for its check. A reply that only shows text can stream and be cut off. Module 12 section 5.3 shows the refund case. Check: prototype rows B and C.
- **Link.** Module 16 section 4.1, "Only the design can promise no consequential action", owns the stronger claim: against injection, a design beats any check. This concept only places a check that you keep.
- **Link.** Observability module section 2.3, "The tail sampler never sees the judge's verdict". An async judge's flag must reach the trace store to be reviewed.

### 4.9 In a cascade, the first stage escalates instead of blocking. It may have a high FPR, and its recall caps the recall of the whole cascade

- **Best evidence, verified.** Anthropic, Constitutional Classifiers++, arXiv 2601.04603v1, section 4. The paper says: "Since exchanges flagged by the first stage are escalated rather than refused, we can tolerate higher first-stage false positive rates." `RGL/src/ccpp_arxiv.txt` line 118.
- **Verified. Production numbers.** Shadow deployment on Claude Sonnet 4.5 traffic, 2025-12-01 to 2026-01-01. "The first-layer probe escalated approximately 5.5% of traffic". The flag rate, "the proportion of queries refused", was 0.05%. Line 185. The post says it "adds roughly 1% compute overhead if applied to Claude Opus 4.0 traffic". `RGL/src/ant_ccpp.txt` line 34. The first generation added 23.7%.
- **Verified.** In the earlier two-stage cascade, about 10% of traffic reached stage 2. The paper says "the first stage accounts for approximately 77% of the system's total cost". Line 125. So a cheap stage on 100% of traffic can cost more than a strong stage on 10%.
- **Conditions.** Preprint by the vendor, on its own traffic. Every number here is a vendor claim. A flag rate is not an FPR. The paper defines it as "the proportion of queries refused", line 185, so it counts all refusals, harmful or not. The post describes the same 0.05% as "a refusal rate of 0.05% on harmless queries". `RGL/src/ant_ccpp.txt` line 34. The two wordings disagree. Teach the paper's definition and name the disagreement. The CC++ stage 2 runs during generation. It is inline, not an after-the-fact judge.
- **Verified by run. The trade in the prototype.** Row C, cascade with the judge inline only on classifier flags, against row A, every layer inline:

| Placement | add p95 ms | add p99 ms | attacks missed | benign blocked | USD per 1,000 |
|---|---|---|---|---|---|
| A, all inline | 513.8 | 527.2 | 315 | 9,294 | 1.739 |
| C, cascade | 107.9 | 495.7 | 1,392 | 1,413 | 0.146 |

- **Recomputed.** The cascade costs 8.4% of row A and blocks 15.2% as many benign requests. It misses 4.4 times as many attacks. In the prototype, the judge sees only what the classifier flagged, so the classifier's recall of 0.80 caps the cascade. `D17/recompute.txt`.
- **Recomputed by the reviewer. Cascade FPR under independence.** In a cascade, a benign request is blocked only if both stages flag it. Under independence the cascade FPR is 0.03 × 0.01 = 0.0003. Stacking the same two stages blocks if either flags: 1 − 0.97 × 0.99 = 0.0397. The closed form, with the regex FPR and the 0.5% outages, predicts benign blocks close to the prototype:

| Row | Closed form | Prototype |
|---|---|---|
| C, fail closed | 1,428 | 1,413 |
| C, fail open | 450 | 453 |
| A, fail closed | 9,097 | 9,294 |

  Row A is about 2 standard deviations above its closed form. It is one seed. Script `review_recompute.py` in the reviewer's scratchpad.
- **Verified by run, corrected in 10.5 item 1. Where independence stops working.** Real stages trip on the same alarming words, 4.11. Positive correlation between stages raises the cascade's FPR above 0.0003. It also raises the cascade's recall above r1 × r2, up to the first stage's recall and never past it. So the independence number is the best case for a cascade's FPR, not for its recall. In `guardrails/code/runs/guardrails_p03_correlation.txt`, at a shared share of 0.5, cascade recall is 0.7695 against 0.736 under independence, below the first stage's 0.80. Cascade FPR is 0.0050 against 0.0003. In `guardrails_p03_cascade_correlation.txt`, the two real guards' cascade caught 15 of 20, the first stage's cap, against 0.637 under independence.
- **The fix, inferred from CC++.** Set the first stage's threshold for recall, not for FPR, because an escalation is cheap and a miss is final. Check: rerun row C with the classifier at recall 0.95 and FPR 0.10. Not run.
- **Summary.** A cascade beats stacking every check on latency, cost and false blocks. It beats it on misses only if stage 1 is tuned for recall.

### 4.10 Adding each layer's p95 works for tight layers. It hides a cascade's judge, which shows only at p99

- **Best evidence, verified by run.** `RGL/proto/run_fail_closed.txt`. Sum of per-layer p95 is 516.9 ms. The p95 of the summed latency is 514.6 ms. For layers with tight latency, adding p95s overstates by little.
- **Verified by run.** In row C the judge runs on few requests. Added p95 is 107.9 ms. Added p99 is 495.7 ms. Recomputed: about 3.8% of requests escalate, from the prototype's parameters. Above 1% and below 5%, the judge shows at p99 and not at p95. The layers report said "about 4% to 5%". Section 7, conflict g.
- **Corrected by the reviewer.** The dossier gave 3.9%. `D17/recompute.py` lines 86 to 90 average the regex recall and the classifier recall over evasive and plain attacks separately, then multiply the averages. Computed per attack class, the share is 3.84%. The p99 conclusion does not change.
- **Verified by run.** Running the classifier and the judge in parallel gives p50 380.1 ms and p95 409.8 ms. The slower layer sets the time.
- **Verified, vendor claim on a vendor dataset.** NVIDIA Table 2, NeMo Guardrails with NemoGuard NIMs, main model Llama 3.1 70B, 215 in-house interactions, hardware not stated:

| Configuration | p50 s | p95 s | Violations detected |
|---|---|---|---|
| No guardrails | 0.93 | 0.97 | 75.01% |
| Content moderation, input and output | 1.31 | 1.38 | 83.0% |
| + jailbreak detection + topic control | 1.50 | 1.66 | 98.9% |

- **Recomputed.** The first layer adds 0.38 s at p50 and 0.41 s at p95. The full stack adds 0.57 s and 0.69 s. The blog calls 75% to 99% "a noticeable improvement of 33%". From the table it is 31.8%.
- **Use it.** Report p99 for any layer that runs on a fraction of traffic. Budget the judge by its escalation share.

### 4.11 Stacked layers raise recall only when they miss different attacks

- **Best evidence, verified by run.** Row A with 30% evasive attacks misses 315 attacks. With no evasive attacks it misses 46. `RGL/proto/run_fail_closed.txt` and `run_no_evasive.txt`. The only change is that evasive attacks lower every layer's recall at once. That is correlation between layers.
- **Conditions.** Simulation. The evasive factors are assumptions: regex 0.1, classifier 0.4, judge 0.7.
- **Verified, vendor number.** NVIDIA's detection rises from 75.01% to 98.9% across three layers. It is policy compliance on 215 in-house interactions, scored with an LLM judge and manual checks. It reports no benign block rate.
- **Inferred.** Real layers share failure causes: the same alarming words, the same training data, the same blind spots. Check: run HAP-38M and Qwen3Guard-0.6B on the same prompts and count joint misses. Lab D.
- **Link.** Module 16 section 3.3 in the built phase. The dossier author cited "section 4.4" of the Module 16 dossier. An adaptive attacker creates this correlation on purpose. Module 16 section 3.2 teaches that attempts are not independent. Module 11 section 5.2 teaches that items on one document fail together. This concept applies the same idea to layers.

### 4.12 Fail open or fail closed differs by product. An execution failure is not a detection, and most products document only the detection

- **Best evidence, verified.** Azure OpenAI content filtering fails open. The docs say: "If the content filtering system is down or otherwise unable to complete the operation in time, your request still completes without content filtering." `RGL/src/az_content_filter.txt` line 326. The response carries an error inside `content_filter_results`.

| System and version | On an execution failure: error, timeout, bad parse | Label |
|---|---|---|
| Azure OpenAI content filtering | Fail open, with an error field | Verified, line 326 |
| NeMo Guardrails 0.24.0 and later, streaming | Fail closed: "Fail closed when rail actions fail" | Verified, CHANGELOG line 38 |
| NeMo Guardrails 0.24.0 and later, content-safety parse | Raises "Failed to parse content safety model response" | Verified, CHANGELOG line 48, `output_parsers.py` |
| NeMo `/v1/checks` | 422 for unsatisfiable `rail_types`, "instead of silently passing" | Verified, CHANGELOG line 49 |
| OpenAI SDK agent guardrail that raises | The error propagates and the run ends | Verified by the reviewer, `run_internal/guardrails.py` lines 159 to 166: `except BaseException`, cancel siblings, `raise` |
| OpenAI SDK tool guardrail that returns no behavior | Allow. `default_factory=lambda: AllowBehavior(type="allow")` | Verified, `tool_guardrails.py` lines 69 to 71 |
| OpenAI SDK input tool guardrail that raises | The tool does not run. Re-raised as `UserError` | Inferred from source. The guardrail call is at `tool_execution.py` lines 2024 to 2033. The `UserError` re-raise is at lines 1832 to 1845, corrected by the reviewer. Not run |
| OpenAI SDK approval rule that cannot read the arguments | "Callable approval rules fail closed" | Verified, `human_in_the_loop.md` line 15 |
| Guardrails AI 0.11.0, validator fails | `on_fail = OnFailAction.EXCEPTION`. Was `NOOP` up to v0.5.0 | Verified, `validator_base.py` lines 139 and 140 |
| Guardrails AI 0.11.0, remote validator | `requests.post` with no `timeout=` anywhere in the file | Verified absence. Inferred: a hung endpoint hangs the request. Not run |
| LLM Guard 0.3.16 | A scanner exception propagates. No try block | Inferred from `evaluate.py` lines 48 to 64. Not run |
| Bedrock Guardrails | Not documented on the pages fetched | Absence. CloudWatch has `InvocationServerErrors` |
| Anthropic API safety classifier | Not documented when the classifier is down | Absence |

- **Verified by run. The cost of fail closed.** In the cascade, classifier outages at 99.5% availability cause most benign blocks: 1,413 with fail closed against 453 with fail open. Fail open let 977 requests pass unchecked. `RGL/proto/run_fail_closed.txt` and `run_fail_open.txt`. Recomputed: the expected outage count on benign traffic is 978.
- **Where it does not hold.** Fail closed on a chat reply trades availability for safety. Fail closed on a refund tool is almost always right. The choice belongs to the action, not to the product.
- **Link.** Module 7 section 2.3, "A hook that fails lets the call run, in the CLI", and section 5.3 own the principle and the wrapper. This concept adds the product defaults and their cost. Do not re-teach the wrapper. Module 11 section 6.3, "A gate must fail when the eval does not run", teaches the same principle for offline gates. Link it.
- **Verified, re-fetched by the reviewer on 2026-09-25 at 03:24 UTC, HTTP 200.** The Azure fail-open sentence is unchanged. The URL now redirects to `learn.microsoft.com/en-us/azure/foundry-classic/foundry-models/concepts/content-filter`.
- **Gap, added by the reviewer. The guard's own timeout.** A fail-open or fail-closed rule needs a timeout that says when the check has failed. Azure says only "unable to complete the operation in time". No fetched source gives a timeout value or a way to set one. Module 1 section 5.1 owns client timeouts. Gap 15.

### 4.13 A per-tenant policy is a named config. The enforcement point, not the config, decides whether a tenant can skip it

- **Best evidence, verified.** The NeMo Guardrails server reads the config from the request body: `config_ids = body.guardrails.config_ids`. `RGL/src/nemo_server_api.py` lines 653 and 844, the chat endpoint and `/v1/checks`.
- **Inferred.** If clients can reach the server directly, a tenant can name a weaker config. Put a gateway in front that sets `config_ids` from the authenticated tenant. Check: run the server with two configs and send the other tenant's ID. Not run.
- **Verified.** Bedrock enforces a guardrail through the IAM condition key `bedrock:GuardrailIdentifier` or an organization policy. The IAM page says: "A user can bypass applying a guardrail in their prompt by using guardrail input tags." `RGL/src/aws_gr_perm_id.txt` line 303. The guardrail still applies to the response.
- **Verified.** Bedrock merges an organization guardrail and an application guardrail. The result is "a union of both guardrails with the most restrictive controls taking precedence". `RGL/src/aws_gr_enforce.txt` line 13. Module 7 section 2.1 teaches the same rule. Link only.
- **Verified.** Bedrock enforcements do not support the Automated Reasoning policy. It "will cause runtime failures". `aws_gr_enforce.txt` line 37.
- **Verified.** Azure attaches a content filter to a deployment. A configuration "can be associated with one or more deployments". `RGL/src/az_content_filter.txt` line 170. So the tenant boundary is the deployment.
- **Verified.** In the OpenAI Agents SDK, guardrails are Python functions on each agent and tool. The run context reaches them. Inferred: pass the tenant in the context and select the policy there.

| System | Policy form | Who picks it per request | Enforced where |
|---|---|---|---|
| NeMo Guardrails server | A config folder | The request body | Guardrails server |
| OpenAI Agents SDK | Functions on agents and tools | Your code | In process |
| Bedrock | Guardrail ID and version | The request, or IAM and organization policy | AWS service |
| Azure OpenAI | Content filter configuration | The deployment | Azure service |

### 4.14 Schema validation is the cheapest layer. It rejects the wrong shape and passes a wrong value, and its default action is a re-ask

- **Best evidence, verified by run.** `json.loads` plus a type check on a refund call: p50 1.46 µs. `RGL/proto/run_fail_closed.txt`. Across three saved runs, p95 was 1.79 to 2.12 µs. 20,000 calls, Python 3.9.6.
- **Verified, corrected in 10.5 item 2.** OpenAI Agents SDK: `strict_json_schema: bool = True`. Invalid JSON returns text to the model and the tool does not run. With default settings, `OPENAI_AGENTS_DONT_LOG_TOOL_DATA` is true, `src/agents/_debug.py` line 17, so the parse error carries no decode detail, `tool.py` lines 1939 to 1947. The default text is "An error occurred while running the tool. Please try again. Error: Invalid JSON input for tool refund_order". The "parsing tool arguments" text of `RGL/src/oai_tool.py` lines 1971 and 1972 appears only with the variable set to `0`. A numeric string amount such as "49.00" is converted to 49.0 by Pydantic's lax mode, `function_schema.py` line 521, and the tool runs. Verified by a direct `on_invoke_tool` call, `guardrails/code/runs/guardrails_p02_sdk_defaults_check.txt`. So the default action on a shape error is to ask again, not to block.
- **Verified.** Guardrails AI names the action. `OnFailAction` includes `REASK`, `FIX`, `FILTER`, `REFRAIN`, `NOOP`, `EXCEPTION`, `FIX_REASK` and `CUSTOM`. `RGL/src/gai_guardrails_types_on_fail.py`.
- **Verified by run.** The prototype's schema check accepts an amount of 89.00 when policy allows 49.00. A value check is a separate layer.
- **Inferred from source.** In the OpenAI SDK, an input tool guardrail runs before the JSON parse, so it sees raw argument text. `tool_execution.py` lines 2024 to 2033. The reviewer read those lines. They show the guardrail call before `on_tool_start`. They do not show where the JSON parse happens. Check: send malformed JSON and log `ToolContext.tool_arguments`. Not run.
- **Link.** Module 6 section 1.3 owns shape against meaning. Module 12 section 5.3 owns the value check on `refund_order`.

### 4.15 Escalation to a human is a safety control only if the pause comes before the side effect and fails closed. The human queue is the main cost

- **Best evidence, verified.** OpenAI SDK: "input tool guardrails normally run after approval and immediately before execution". `pre_approval_tool_input_guardrails` runs them before the prompt as well. Calls are "still checked again after approval". `RGL/src/oai_docs_guardrails.md` line 77.
- **Verified.** A tool sets `needs_approval`. The run returns interruptions. `RunState` serializes, so the pause can outlive the process. `RGL/src/oai_docs_human_in_the_loop.md`.
- **Verified absence.** The words "timeout" and "expire" do not appear in `human_in_the_loop.md` at v0.22.3. Inferred: an unanswered approval holds the run until your app expires it. Module 9 section 4.3, "Every wait needs a timeout branch", owns the fix.
- **Verified.** `always_approve=True` keeps the decision for later calls to the same tool in the run. A sticky approval widens scope.
- **Verified.** Escalation to another model: Anthropic's fallback retries a refused request on a recommended model. "For categories with no recommended fallback, the refusal stands." `RGL/src/ant_refusals-and-fallback.txt` line 48. Beta header `server-side-fallback-2026-07-01`. The reviewer re-fetched the page on 2026-09-25 at 03:24 UTC, HTTP 200. The beta header and the mid-stream billing sentence are unchanged. Module 1 section 5.6 owns fallbacks in general. Link it.
- **Verified by run.** Row B: human review is $13.75 of $15.49 per 1,000 requests, at an assumed $1 per review. The $1 is not checked. No published source gives human review latency or price.
- **Link.** Module 7 section 5.1 owns approval fatigue. Module 9 Phase 4 owns durable approval. Module 19, planned, owns the approval screen.

### 4.16 Guardrail toolkits change defaults between releases, and one widely cited toolkit is archived. Pin a version and re-read its defaults

- **Best evidence, verified.** The LLM Guard README on `main` says "THIS PROJECT HAS BEEN ARCHIVED." It adds that its Hugging Face models "are no longer under active development or maintained". `RGL/src/llmg_readme_main.md` lines 2 and 4. The commit "Archiving Project (#355)" is dated 2026-07-08 in the commits feed. The last PyPI release is 0.3.16 on 2025-05-19.
- **Verified.** Guardrails AI changed `on_fail` from `NOOP` to `EXCEPTION` at v0.6.0. Code that never set `on_fail` changes behaviour on upgrade. Per the layers report, `validator_base.py` was read at v0.4.5, v0.5.0 and v0.6.0 to v0.10.0. The dossier author re-grepped only v0.11.0.
- **Verified.** NeMo Guardrails 0.24.0 closed three silent-pass paths in one release. 4.12.
- **Verified.** LLM Guard's docstring and code disagree. The docstring says "Default is 0.9". The signature says `threshold: float = 0.92`. `RGL/src/llmg_pi.py` lines 129 and 138.
- **Use it.** Teach LLM Guard only as a source of measured CPU numbers. Do not teach it as a current pick.

---

## 5. Numbers, with their conditions

### 5.1 Artificial Analysis guardrail benchmark, B200

Source: `RGM/src/aa_models_table.txt`, extracted from the page's embedded JSON. 7,232 prompts: 1,699 WildGuardTest, 5,083 ToxicChat, 450 XSTest. Prompt-level only. vLLM or SGLang on B200-class nodes, one request in flight, 20 warmups and 450 measured requests. FPR is 1 minus `benignPassRate`. Whether "aggregate" is pooled or averaged per dataset is not checked. Partner: NVIDIA. WildGuardTest and XSTest are in-domain for WildGuard.

| Guard | Recall | FPR | XSTest-safe FPR | Mean ms | p95 ms | Mean input tokens |
|---|---|---|---|---|---|---|
| WildGuard 7B | 0.885 | 0.043 | 0.012 | 68.6 | 83.3 | 170 |
| Qwen3Guard Gen 8B | 0.938 | 0.090 | 0.128 | 43.5 | 55.7 | 345 |
| Llama 3.1 Nemotron Safety Guard 8B v3 | 0.880 | 0.125 | 0.216 | 57.2 | 103.3 | 803 |
| Granite Guardian 4.1 8B | 0.827 | 0.086 | 0.172 | 59.1 | 61.1 | 244 |
| Granite Guardian 4.1 8B, think | 0.822 | 0.109 | 0.200 | 1,313.6 | 1,805.0 | 250 |
| Nemotron 3.5 Content Safety | 0.921 | 0.171 | 0.292 | 27.1 | 29.7 | 516 |
| Nemotron 3.5 Content Safety, reasoning | 0.892 | 0.162 | 0.272 | 505.7 | 1,008.3 | 514 |
| Nemotron 3 Content Safety | 0.915 | 0.182 | 0.328 | 27.1 | 29.0 | 473 |
| Nemotron Content Safety Reasoning 4B, no reasoning | 0.884 | 0.139 | 0.248 | 51.3 | 54.4 | 451 |
| Llama Guard 3 8B | 0.658 | 0.036 | 0.028 | 21.3 | 29.7 | 249 |
| Llama Guard 4 12B | 0.629 | 0.059 | 0.060 | 27.9 | 41.0 | 251 |
| ShieldGemma 9B | 0.385 | 0.037 | 0.084 | 18.3 | 20.2 | 209 |
| gpt-oss-safeguard-20B | 0.688 | 0.061 | 0.116 | 260.9 | 717.3 | 586 |
| gpt-oss-safeguard-120B | 0.609 | 0.027 | 0.056 | 387.5 | 1,136.8 | 586 |
| omni-moderation, hosted API | 0.535 | 0.126 | 0.260 | 324.5 | 362.8 | 38 |

The policy text for gpt-oss-safeguard was written by Artificial Analysis. The source table has 20 rows. Five prompted and mode variants are left out here.

### 5.2 Other independent evaluations

| Source | Number | Conditions |
|---|---|---|
| Domyn, arXiv 2605.28830, Table 3 | Recall and precision: Qwen Guard 4B 0.8397 and 0.6879. Llama Guard 12B 0.3332 and 0.7851. GPT-OSS Safeguard 20B 0.2486 and 0.8068 | 79,331 samples: 43,393 unsafe, 35,938 safe. All safe samples from RealToxicityPrompts with Perspective score 0.5 or less. Controversial mapped to unsafe |
| Same, FPR recovered | Qwen Guard 4B 0.460. Llama Guard 12B 0.110. GPT-OSS Safeguard 20B 0.072 | Inferred from recall, precision and class counts. Accuracy check: 0.7039 against the paper's 0.7036, and 0.5854 against 0.5860 |
| arXiv 2512.19011, Table 7 | SVM word n-gram F1 0.964 at 3.4 ms on CPU. OOD recall 0.270. DeBERTa-v3 LoRA 27.5 ms, Gemma-2-2B LoRA 48.5 ms, Mamba-130M 24.3 ms on GPU | Jailbreak detection. 32-core CPU server, A100 80 GB PCIe, batch 1 |
| LEG, arXiv 2602.15853, Table 8 | Prompt Guard 2 22M 9.17 ms, 1.04 GB. 86M 9.47 ms, 1.90 GB | H100, WildGuardMix test, sequential, no batching |
| Lexsi, arXiv 2608.16852, Table 14 | Llama Guard 3 8B 31.9 ms, WildGuard 31.8 ms, Qwen3Guard-Gen 8B 45.3 ms | "a single GPU", model not named |

### 5.3 Vendor numbers

| Guard | Number | Conditions |
|---|---|---|
| Llama Guard 4 12B | English R 69%, FPR 11%, F1 61%. Multilingual R 43%, FPR 3% | Meta in-house set, output filtering |
| Llama Guard 3 8B | F1 0.939, FPR 0.040 | Meta internal English response set, card Table 1 |
| Prompt Guard 2 86M | 92.4 ms. 22M: 19.3 ms | "A100 GPU, 512 tokens". Engine and batch not stated |
| Qwen3Guard-8B-Gen | ToxicChat F1 68.9 strict, 82.8 loose | Average uses the better mode per benchmark |
| Qwen3Guard-Stream | Hit in first 128 tokens about 66.8%. Response-only exact hit about 86.0% | Traces with thinking, and response only. No latency |
| Nemotron-3.5-Content-Safety | FP rate MMMU 0.03, DocVQA 0.060, AI2D 0.001 | Sets "assumed" 100% safe. N = 10,500, 5,188, 3,088 |

### 5.4 Latency, all rows with conditions

| Layer | Latency | Conditions | Label |
|---|---|---|---|
| Regex, 5 patterns | p50 45.38 to 47.21 µs. p95 49.88 to 57.67 µs | About 1,700-character message, Python 3.9.6, learner's Mac, 20,000 calls, three saved runs | Verified by run |
| Schema check | p50 1.46 to 1.54 µs. p95 1.79 to 2.12 µs | Refund JSON, same machine, three saved runs | Verified by run |
| HAP-38M encoder | 2.7 to 9.4 ms CPU, 2.2 to 5.4 ms MPS, median | 34 to 512 tokens, batch 1 | Verified by run |
| DeBERTa-v3-base injection classifier | 7.65 ms avg on g5.xlarge GPU with ONNX. 81.01 ms on g5.xlarge GPU without ONNX. 104.21 ms on m5.xlarge with ONNX. 212.87 ms on m5.xlarge. 421.46 ms on Azure D4as_v4, 177.30 ms with ONNX | LLM Guard v0.3.16 table, "Input Length: 384", unit not stated, 5 runs | Verified, vendor benchmark. `RGL/src/llmg_prompt_injection.md` lines 88 to 97 |
| Qwen3Guard-Gen-0.6B | 189.7 to 291.6 ms MPS, 399.7 to 592.9 ms CPU, median, full generation | 329 to 809 input tokens including template | Verified by run |
| 7B to 12B guards, no reasoning mode | 18.3 to 68.6 ms mean | B200, vLLM or SGLang, 1 in flight. The ends are ShieldGemma 9B and WildGuard 7B | Verified, Artificial Analysis. Row name corrected by the reviewer |
| Reasoning guards | 230.0 to 1,313.6 ms mean | Same | Verified |
| NemoGuard content safety, input and output | +0.38 s p50, +0.41 s p95 | Llama 3.1 70B via NIM, 215 interactions, hardware not stated | Verified, vendor |
| Full NeMo stack, 3 NIMs | +0.57 s p50, +0.69 s p95 | Same | Verified, vendor |
| Azure content filters, Prompt Shields | None published | Overview and Prompt Shields pages give input and rate limits only | Absence |
| Bedrock Guardrails | None published | CloudWatch has `InvocationLatency` | Absence |
| Human review | Not checked | Prototype assumes 20 min p50, 4 h p95 | Assumption |

### 5.5 Blocks per day

`RGM/proto/blocks_output.txt` section A. N = 1,000,000 requests a day. Artificial Analysis TPR and FPR.

| Guard | Base rate 0.1%: false blocks / true blocks / precision | Base rate 1%: false blocks / true blocks / precision |
|---|---|---|
| WildGuard 7B | 42,957 / 885 / 2.02% | 42,570 / 8,850 / 17.21% |
| Qwen3Guard Gen 8B | 89,910 / 938 / 1.03% | 89,100 / 9,380 / 9.52% |
| Llama Guard 3 8B | 35,964 / 658 / 1.80% | 35,640 / 6,580 / 15.59% |
| Llama Guard 4 12B | 58,941 / 629 / 1.06% | 58,410 / 6,290 / 9.72% |
| ShieldGemma 9B | 36,963 / 385 / 1.03% | 36,630 / 3,850 / 9.51% |
| gpt-oss-safeguard-120B | 26,973 / 609 / 2.21% | 26,730 / 6,090 / 18.56% |
| Nemotron 3.5 Content Safety | 170,829 / 921 / 0.54% | 169,290 / 9,210 / 5.16% |

Zero-flag benign samples needed at 95%: 59 for FPR below 5%, 299 for 1%, 2,995 for 0.1%, 29,956 for 0.01%. Recomputed by the reviewer with 1 − 0.05^(1/n). Module 16 section 3.5 teaches this bound. Link it.

### 5.6 Layer placement prototype

`RGL/proto/layered_pipeline.py`. 200,000 requests, 2% attacks, 30% evasive, classifier availability 99.5%, seed 42, fail closed. `run_fail_closed.txt`.

| Placement | add p50 ms | add p95 ms | add p99 ms | Blocked | Found late | Missed | Benign blocked | USD per 1,000 |
|---|---|---|---|---|---|---|---|---|
| A, regex + schema + classifier + judge, all inline | 483.0 | 513.8 | 527.2 | 3,718 | 0 | 315 | 9,294 | 1.739 |
| B, judge async on 100% | 104.2 | 106.9 | 108.0 | 2,843 | 794 | 326 | 7,145 | 15.492 |
| C, cascade, judge inline on classifier flag | 104.3 | 107.9 | 495.7 | 2,607 | 0 | 1,392 | 1,413 | 0.146 |
| D, regex + schema + classifier | 104.2 | 106.9 | 108.0 | 2,832 | 0 | 1,123 | 7,163 | 0.079 |

**Parameters and their status.**

| Layer | p50 / p95 ms | Recall | FPR | USD per call | Source |
|---|---|---|---|---|---|
| Regex | measured | 0.30 | 0.002 | 0 | Latency measured. Recall and FPR assumed |
| Schema | measured | 0.05 | 0 | 0 | Same |
| Classifier | 104.21 / 106.85 | 0.80 | 0.03 | 0.00008 | Latency from LLM Guard m5.xlarge ONNX. Price from Bedrock prompt attack, 1 text unit. Recall and FPR assumed. Availability 99.5% assumed |
| Judge | 380 / 410 | 0.92 | 0.01 | 0.00175 | Latency from NVIDIA Table 2 differences. Price from Claude Haiku 4.5, $1 and $5 per million tokens, 1,500 in and 50 out |
| Human | 20 min / 4 h | 0.97 | 0.005 | 1.00 | All assumed |

A Bedrock text unit holds up to 1,000 characters. `RGL/src/aws_bedrock_pricing.txt` line 1630. The prototype's message is about 1,700 characters, which is 2 text units. Inferred: row D would cost about $0.159 per 1,000, not $0.079. Section 7, conflict h.

### 5.7 Production cascade numbers

| Quantity | Value | Conditions | Source |
|---|---|---|---|
| Traffic escalated to stage 2 | About 5.5% | Linear probe stage 1, Claude Sonnet 4.5 shadow deployment, 2025-12-01 to 2026-01-01 | CC++ line 185 |
| Flag rate | 0.05% | Same | Same |
| Compute overhead | Roughly 1%, "if applied to Claude Opus 4.0 traffic" | Anthropic post | `ant_ccpp.txt` line 34 |
| First-generation overhead | 23.7% | Constitutional Classifiers, 2025 | `ant_cc.txt` line 27 |
| Stage 1 share of cost, earlier cascade | About 77%, with about 10% escalated | CC++ section 4 | Line 125 |

### 5.8 Arithmetic recomputed

All from `D17/recompute.txt`.

| Claim | Report value | Recomputed | Result |
|---|---|---|---|
| Qwen3Guard OR-Bench over Alpaca FPR | "more than 500 times" | 568x on point values. At least 96x on Wilson interval ends | Holds for point values only. Changed in 4.1 |
| Llama Guard 4 at 0.1% base rate | 58,941 false, 629 true, 1.06% | Same | Holds |
| Hand case precision | 8.3% | 8.26% | Holds |
| Zero-flag sample sizes | 299 and 2,995 | 299 and 2,995 | Holds |
| Domyn FPR, Qwen Guard 4B | about 0.46 | 0.460. Accuracy 0.7039 against 0.7036 | Holds |
| Qwen3Guard against HAP-38M | 44 to 148x | 43.6x, 86.2x, 148.0x. For equal user text, 54.0x to 148.0x | Reviewer: 43.6x pairs 256 user tokens with 512. Changed in 4.5 |
| Template tokens | 297 | 329 − 32 = 297 | Holds |
| Qwen3Guard p95 within 10% of median in every row | Models report 5 | CPU generate at 553 tokens is 10.6% | Wrong for one row. Section 7, conflict f |
| Reasoning latency ratios | 22x, 19x, 4.5x | 22.2x, 18.7x, 4.5x | Holds |
| Reasoning recall and specificity change | below 0.03 and 0.025 | at most 0.029 and 0.023 | Holds |
| Prompt Guard 2 latency gap | not stated | 92.4 ÷ 9.47 = 9.8x | Added |
| LLM Guard "QPS" | input units per second | 384 ÷ 0.21287 = 1,803.9. 384 ÷ 0.10421 = 3,684.9 | Holds. Unit of 384 not stated |
| LLM Guard slowest to fastest | not stated | 421.46 ÷ 7.65 = 55.1x | Added |
| NVIDIA first-layer latency | +0.38 s p50, +0.41 s p95 | Same | Holds |
| NVIDIA "improvement of 33%" | 33% | 31.8% | Blog rounding. Changed in 4.10 |
| CC++ flag rate drop | "87% drop" in the post | 1 − 0.05 ÷ 0.38 = 86.8% | Holds as arithmetic. The two numbers measure different things. Section 7, conflict e |
| Sum of per-layer p95 | 516.9 ms | 516.9 ms | Holds |
| Judge price per call | $0.00175 | $0.00175 | Holds |
| Row B human cost | $13.75 of $15.49 | 2,750 × $1 ÷ 200 = $13.75 | Holds |
| Row B over row A | about 9x | 8.9x | Holds |
| Cascade escalation share | 4% to 5% | About 3.9%. Reviewer: 3.84%, per attack class | Changed in 4.10 |
| Cascade FPR under independence | not stated | Reviewer: 0.03 × 0.01 = 0.0003. Stack of the same stages 0.0397 | Added in 4.9 |
| Lexsi ratio floor, WildGuard and Llama Guard 3 8B | not stated | Reviewer: 83x and 24x on Wilson ends | Added in 4.1 |
| FPR where false blocks equal true blocks, 1% base rate, TPR 0.9 | about 0.9% | Reviewer: 0.909% | Holds |
| Classifier price per call | $0.00008 | $0.00016 for a 1,700-character message | Changed in 5.6 |
| Self-test hand case | 1.4 missed, 20.7702 benign blocked | Same | Holds |
| Outage blocks in cascade | 1,413 − 453 | 960. Expected 978 | Holds |

---

## 6. Lab designs

The learner has an Apple Silicon Mac with 24 GiB RAM, no Docker, no GPU except MPS, and no API keys for labs.

### 6.1 Built and run on 2026-09-25

| Lab | Script | Output | Runs where | Cost | Self-test | Proves |
|---|---|---|---|---|---|---|
| A. Blocks-per-day calculator | `RGM/proto/blocks.py` | `blocks_output.txt` | Laptop, offline, standard library | Under 1 s. No download | Hand case 9,990 and 900. Wilson 0 of 100 and 50 of 100. n = 299. Re-run by the dossier author: "self-test OK" | 4.1, 4.2 |
| B. Local guard timing | `RGM/proto/time_local.py` | `time_hap_output.txt`, `time_qwen_output.txt` | Laptop, CPU and MPS. `uv run --python 3.12 --with torch==2.14.0 --with transformers==4.57.6` | Downloads 154 MB and 1.5 GB. The Qwen3Guard download took 534 s | None. Proposed: p95 above p50, and longer input not faster | 4.4, 4.5 |
| C. Layered pipeline simulator | `RGL/proto/layered_pipeline.py` | `run_fail_closed.txt`, `run_fail_open.txt`, `run_no_evasive.txt`, `run_selftest.txt` | Laptop, offline, standard library | Self-test 0.65 s. Full report 3.6 s | 16 checks. Re-run by the dossier author: 16 of 16 passed | 4.8 to 4.12, 4.14 |

**Break-it variants.** Lab A: lower the base rate from 10% to 0.01% and watch precision fall from 90.91% to 0.89%. Lab B: compare prefill only against full generation at 512 tokens. Lab C: `--fail open`, `--evasive-share 0.0`, and raise the classifier FPR to 0.10 to push the judge into p95.

### 6.2 Designed, not built

| Lab | What it prints | Runs where, costs what | Proves |
|---|---|---|---|
| D. Cascade correlation | HAP-38M and Qwen3Guard-0.6B on the same prompts. Joint flags, joint misses, and combined FPR against the independence estimate | Laptop, offline once downloaded. About 1.7 GB, already on disk in `RGM/proto/models/`. Minutes | 4.9, 4.11 |
| E. FPR on your own benign traffic | Flags on 3,000 benign prompts the learner owns, with a Wilson interval | Laptop, offline. Time only. Self-test is section C of `blocks.py` | 4.1 |
| F. Fail-open drill | A local HTTP server that sleeps or returns 500, wrapped as an OpenAI SDK tool input guardrail, a NeMo-style parser, and a Guardrails AI-style remote call. Prints whether the tool ran, the added latency and the caller's error | Laptop, offline, `openai-agents==0.22.3` with a fake model. Whether a fake model can drive the runner offline is not checked | 4.12 |
| G. Async stream cut-off | Streams fixed text. A 300 ms check per chunk, sync against async. Prints characters shown before the block and time to first token. Compares with Azure's ~1,000-character window | Laptop, standard library, seconds | 4.7 |
| H. Encoder classifier under ONNX and not | An encoder injection classifier on CPU, with and without ONNX, at 384 and 2,000 characters | Laptop. Model choice and download not checked | 4.5 |
| I. Cascade with stage 1 tuned for recall | Lab C with classifier recall 0.95 and FPR 0.10 | Laptop, seconds | 4.9 |

### 6.3 The module lab, proposed

A refund-support request path with four placements. Proposal, not built.

1. A seeded generator of 20,000 requests. It plants a known share of attacks and a known share of benign prompts with alarming words. Use lab C's generator.
2. Real cheap layers: the regex, the schema check and HAP-38M on the learner's CPU. Qwen3Guard-0.6B on MPS as the judge. A deterministic policy check on `refund_order` arguments.
3. Four placements: all inline, judge async, cascade with stage 1 tuned for recall, cheap inline only.
4. A fake guard server for outages, run fail open and fail closed.
5. Self-test: one hand-counted batch of 100 requests.
6. It prints per placement: added p50, p95 and p99, and attacks blocked, found late and missed. It also prints benign blocked, refunds that ran before a block, and USD per 1,000 at today's prices.
7. Break-its: make every layer trip on the same words. Turn the refund check into an async judge. Set the classifier to fail open.

Inferred: offline, no key, about 1.7 GB already downloaded, a few minutes of run time on MPS. Not measured.

---

## 7. Conflicts resolved

| Conflict | Sources | Evidence used | Resolution |
|---|---|---|---|
| a. Prompt Guard 2 86M latency, 92.4 ms or 9.47 ms | Meta card against LEG | Card line 74: A100, 512 tokens. LEG line 2154: H100, sequential, no batching, input length not stated. The card gives 92.4 ms for Prompt Guard 1 too | Not one number. Different GPU, input and engine. Teach both with conditions. The copied card row is inferred, not checked |
| b. "A small CPU classifier costs about 100 ms" against 2.7 to 9.4 ms | Layers report 2.7 against models report 1.6 | LLM Guard: DeBERTa-v3-base, m5.xlarge, ONNX. The saved source does not give the vCPU count. Reviewer: not checked. HAP-38M: 38M encoder, M4 Pro, 10 threads | Both hold. Model size, CPU and runtime differ. Teach the range and the conditions |
| c. Recall first or FPR first | Domyn, Artificial Analysis, the module brief | Domyn line 22. Artificial Analysis "Specificity matters most here". `blocks.py` section E | The base rate and the cost of a miss decide. At base rates of 1% or less, false blocks outnumber true blocks unless FPR is below TPR × base rate ÷ (1 − base rate). The reviewer made the formula exact. 4.2 |
| d. Llama Guard 4 recall 0.33, 0.63 or 69% | Domyn, Artificial Analysis, Meta card | Domyn: RealToxicityPrompts-based set with profanity. Artificial Analysis: WildGuardTest, ToxicChat, XSTest. Meta: in-house set | Different data and different harm definitions. Meta says rivals are "typically not aligned with the specific safety policy". Inferred: categories outside Llama Guard's taxonomy lower its recall. Check: per-category recall. Not done |
| e. CC++ "0.05%" against Sharma et al. "0.38%" | CC++ paper and post, 2025 post | `ant_cc.txt` line 27: "increased refusal rate (by 0.38%)", "not statistically significant" on 5,000 conversations. `ccpp_arxiv.txt` line 185: flag rate 0.05%, "the proportion of queries refused" | Two different measures. 0.38% is an increase over the unguarded model. 0.05% is an absolute flag rate. The post's "87% drop" compares them directly. Teach 0.05% as the flag rate on production traffic, and do not teach the 87%. Reviewer check: the CC++ paper itself also compares 0.05% with 0.38%, line 185. The post calls 0.05% a refusal rate "on harmless queries", line 34. The paper calls it "the proportion of queries refused". Holds, with this note |
| f. Qwen3Guard p95 "within 10% of the median in every row" | Models report 5 | `time_qwen_output.txt`: CPU generate at 553 tokens, 483.1 and 534.2 ms | 10.6% for that row. All other Qwen rows are within 4.5%. HAP-38M on MPS at 34 tokens is 45%, at 2.2 ms. Corrected |
| g. Cascade escalation "about 4% to 5%" | Layers report 1 and 2.7 | Closed form from the prototype parameters, `D17/recompute.txt` | About 3.9%. Not counted by the prototype. The p99 conclusion holds. Reviewer: 3.84% when computed per attack class. Resolution holds |
| h. Classifier price per call | Layers report 5, Lab 1 | Bedrock: "A text unit can contain up to 1000 characters", pricing line 1630. Prototype message about 1,700 characters | 2 text units, $0.00016 per call. Row D about $0.159 per 1,000, inferred. The ranking of rows does not change |
| i. Regex and schema latency | Layers report: 47.6 and 51.3 µs, 1.46 and 1.62 µs | The three saved runs: regex p50 45.38 to 47.21, p95 49.88 to 57.67. Schema p95 1.79 to 2.12 | The report's figures come from a run whose output was not saved. Teach the saved range |
| j. LLM Guard input "384 characters" | Layers report | Doc line: "Input Length: 384". No unit | Unit not stated. "QPS" is 384 ÷ latency, so it counts input units per second, not requests. Teach "input length 384, unit not stated" |
| k. Lexsi value order | Models report 1.1 lists Alpaca first with N in XSTest order | Table 24 columns: XSTest-safe, OR-Bench-hard, Alpaca/Dolly | Values were right. The N mapping is XSTest 250, OR-Bench-hard 1,319, Alpaca/Dolly 1,000 |
| l. Which Llama Guard 3 values are floor artifacts | Models report names only Llama Guard 3 1B | Table 24 caption names Llama Guard 3, HarmBench and Llama Guard 3 8B | The authors call Llama Guard 3 8B's OR-Bench 0.193 a floor artifact too. 4.1 |
| m. "Escalation" names two designs | Anthropic CC++ against LLM Guard sampling | CC++ stage 2 runs during generation. LLM Guard runs slow scanners on a sample | Different designs, same word. Teach "cascade" for the first and "sampled async review" for the second |
| n. NeMo tool rail names | NeMo `config.py` lines 440 and 457 against the OpenAI SDK | NeMo `ToolOutputRails` run on tool calls before execution. NeMo `ToolInputRails` run on tool results | The names are reversed between the two frameworks. Teach by position, before or after the tool, not by name |

---

## 8. Gap list, ranked by what the module question needs

| Rank | Gap | Why the module question needs it | What was done |
|---|---|---|---|
| 1 | The module lab with real layers | "What belongs inline" needs one run with real latency, real misses and real false blocks, not assumed recall | Not built. Design in 6.3. Both models are on disk |
| 2 | FPR of any guard on a realistic benign support-traffic sample | "Still misses attacks" and "300 ms" are only half the cost. The other half is false blocks, and 4.1 shows vendor FPR does not transfer | Not measured. Lab E |
| 3 | Where the faithfulness gate runs in production, and its cost | Promised by Module 11 section 4.4 and `eval-engineering/course.json` | Not researched by either report |
| 4 | The rate at which a refund guardrail blocks allowed refunds | Promised by Module 12 section 5.3 line 537 | Only the arithmetic in 4.2. No measured rate |
| 5 | Correlation between two real guards | 4.11 rests on assumed evasive factors | Not run. Lab D |
| 6 | Cascade with stage 1 tuned for recall | 4.9 says the fix is a recall threshold. Not shown | Not run. Lab I |
| 7 | Bedrock and Azure guardrail latency | Hosted guardrails are a common inline choice. No vendor publishes latency | Not measured. Needs keys |
| 8 | Bedrock and Anthropic behaviour when the classifier is down | Fail open or closed is unknown for two products | Absence recorded. Not checked in API references |
| 9 | Encoder injection classifier on the learner's Mac with ONNX | The 300 ms row is a cloud CPU. The learner has no local injection-classifier number | Not run. Lab H |
| 10 | NeMo server config selection by another tenant | 4.13 is inferred from one line of code | Not run |
| 11 | OpenAI SDK input tool guardrail that raises | 4.12 row is read from source | Not run. Lab F |
| 12 | Production harmful base rate | 4.2 assumes 0.1% and 1% | No source found |
| 13 | Human review latency and price | Row B cost depends on the assumed $1 | No source found |
| 14 | Harmful-content safety evals, promised by Module 16 | `security/course.json` line 563 | Only guard evaluation is covered |
| 15 | The guard's own timeout: its value and who sets it | Fail open or fail closed starts when the check times out. "300 ms on every request" needs a stated cut-off | Added by the reviewer. No fetched source gives a value. Azure says only "in time" |
| 16 | A measured parallel input check against a real model's time to first token | 4.7 infers that a parallel check hides the 300 ms. Not measured | Added by the reviewer. Not run. Extend lab G |

---

## 9. Things not verified

From both reports and from this dossier. Each item has the check that would settle it.

**Models report.**

1. Hardware for Lexsi Table 14 latencies. Check: find the E-GUARDBENCH reference.
2. Whether Artificial Analysis "benign pass rate" is pooled or averaged per dataset. Check: per-dataset rows, if the page exposes them.
3. "Δ FPR −3%" in the Llama Guard 4 card, absolute or relative. Check: Meta's test set, which is not published.
4. The gpt-oss-safeguard launch blog. HTTP 403 to curl. Check: a browser.
5. WildGuard's NeurIPS venue. Check: the proceedings.
6. arXiv 2512.19011 at USENIX ATC '26. Check: the ATC program.
7. The ShieldGemma paper body. Only grepped. Check: read the evaluation section.
8. Meta's 92.4 ms for Prompt Guard 2 86M. Check: time the model on an A100 at 512 tokens.
9. "Optimal F1" meaning in the ShieldGemma card. Check: the paper.
10. Whether an 8B guard at bf16 runs on MPS with 24 GiB. Check: load one.
11. Independent latency for Llama Guard 4, Qwen3Guard or Granite Guardian on consumer hardware. None found.
12. The laptop timings are one run with unrecorded load. Check: re-run twice more.
13. NVIDIA's assumption that MMMU, DocVQA and AI2D are 100% safe. Not checked.
14. OR-Bench's 1.8% toxic estimate. Not re-grepped by the dossier author. Check: `RGM/src/orbench.txt` lines 396 to 440.
15. Whether Lexsi ran each guard with its default template for Table 24. Check: the paper's method section.

**Layers report.**

16. OpenAI SDK behaviour when an input tool guardrail raises. Read from source. Check: lab F.
17. Whether a NeMo client can pick another tenant's config. Check: two configs and a cross-tenant request.
18. Bedrock Guardrails and Azure Content Safety latency. Check: time `ApplyGuardrail` and `shieldPrompt` from one region. Needs keys.
19. Bedrock behaviour when the guardrail service errors. Check: the `ApplyGuardrail` error list and a throttled call.
20. Anthropic classifier behaviour when the classifier is unavailable.
21. The `InvokeGuardrailChecks` API reference. Seen only on the pricing page.
22. NVIDIA Table 2 hardware. Not named.
23. NVIDIA's parallel-rails race-condition warning. Seen only in a search summary. Not fetched. Do not teach it.
24. The Anthropic "Handle streaming refusals" page. The URL tried returned 404. The live path is `/docs/en/test-and-evaluate/strengthen-guardrails/handle-streaming-refusals`.
25. All recall, FPR, evasive and human values in the layers prototype. Assumptions.
26. LLM Guard exception propagation and the Guardrails AI hang on a slow endpoint. Read from code, not run.
27. Guardrails AI server per-guard routing.
28. GitHub release metadata. The GitHub API returned 403. Versions come from PyPI and changelogs.

**This dossier.**

29. The Guardrails AI `on_fail` history before v0.11.0. The dossier author re-grepped only v0.11.0.
30. Which LLM Guard model version produced the benchmark table. The default is v2. The table does not say.
31. The Granite Guardian Table 11 column reading. The header lists TPr at 0.1, 0.01 and 0.001 among eight numbers per row. The reading matches the models report. Check: the rendered PDF table.
32. The 3.9% cascade escalation share is a closed-form estimate. Check: add a counter to `layered_pipeline.py`.
33. Row D at two text units, $0.159 per 1,000, is arithmetic, not a rerun.
34. Whether Module 16's `security/course.json` Phase 3 will keep the detector-limit material, which this module links.
35. The OpenAI SDK `run_internal/guardrails.py` lines 159 to 166 and `tool_execution.py` lines were cited from the layers report. The dossier author did not re-read them. The reviewer read both on 2026-09-25. The first holds. The `UserError` line reference was wrong and is corrected in 4.12.

**Review.**

36. The Qwen3Guard-Stream "two unsafe tokens in a row" rule. Removed from 4.7. Check: the Qwen3Guard-Stream inference code on Hugging Face.
37. Where the OpenAI SDK parses tool-argument JSON relative to the input tool guardrail. Check: send malformed JSON and log `ToolContext.tool_arguments`.
38. Row A benign blocks, 9,294, sit about 2 standard deviations above the closed form, 9,097. Check: run row A with five seeds.
39. The vCPU counts of AWS m5.xlarge and Azure Standard_D4as_v4. Not in the saved source.
40. NeMo's ~200-token streaming window as seen by a user. Inferred from config defaults. Check: stream with `stream_first` on and count tokens shown before a block.

---

## 10. Review log

Reviewer: an independent agent that did not write this dossier. Date: 2026-09-25. Scope: read-only and fetch-only. No lab ran. No model was downloaded.

### 10.1 What the reviewer ran

| Check | Command or file | Result |
|---|---|---|
| `blocks.py` self-test | `python3 RGM/proto/blocks.py`, Python 3.9.6, learner's Mac | "self-test OK" in 0.02 s. Output identical to `blocks_output.txt`, `diff` empty |
| `layered_pipeline.py` self-test | `python3 RGL/proto/layered_pipeline.py --self-test` | "16 of 16 checks passed" in 0.61 s |
| Independent arithmetic | `review_recompute.py` in the reviewer's scratchpad | 90.91% to 0.89% holds. 111.1 false blocks per true block holds. n = 299, 2,995, 29,956 and 59 hold. 8.26% holds. Llama Guard 4 58,941, 629, 1.06% holds. Sum of p95 516.9 ms holds. NVIDIA +0.38, +0.41, +0.57, +0.69 s hold. 31.8% holds. Judge $0.00175, row B $13.75, 8.9x, 8.4%, 15.2%, 4.4x hold. Row D at 2 text units $0.159 holds. Three items changed, below |
| Anchors | About 60 quotes and numbers grepped with `grep -a -n -F` in the saved files | All but 3 match. The 3 failed or had a wrong line, below |
| Vendor docs re-fetched | `curl -sL --max-time 60`, 2026-09-25 03:24 UTC | Azure content streaming, Azure content filtering, Bedrock guardrails streaming, Anthropic refusals and fallback. All HTTP 200. Every quoted sentence unchanged |
| Overlap | `grep '^## '` on `study-material/{security,agent-evals,eval-engineering,inference-internals,observability-ops}/*.md`. Read Module 16 section 3.4 | Module 16 is built. Five overlaps, below |

Anchors that match, by the module question: HAP-38M card line 61 and the Granite Guardian 4.1 lines 459 and 460. Qwen3Guard Table 2, 68.9 and 82.8, and the 66.8% stream sentence. Llama Guard 4 R 69%, FPR 11%, F1 61% and "We omit evals against competitor models". Llama Guard 3 F1 0.939 and FPR 0.040. Prompt Guard 2 92.4 ms and 19.3 ms. LEG 9.47 ms and "Deng et al.". ShieldGemma "Optimal F1(left)/AU-PRC(right)" and "Last updated 2025-02-25". Granite Guardian Table 11, all nine values used. Artificial Analysis rows for Llama Guard 4, ShieldGemma 9B, Granite Guardian 4.1, Nemotron 3.5, and "one request in flight". Lexsi Table 24 values and caption. Both timing outputs, every row. Azure ~1,000-character window and fail-open sentence. Bedrock asynchronous-mode sentences. NeMo `stream_first`, `parallel`, CHANGELOG lines 38, 48 and 49, the parse-error string in `output_parsers.py` lines 170, 209 and 325. OpenAI SDK `run_in_parallel`, `AllowBehavior`, "Callable approval rules fail closed", no "timeout" in the approval docs. Guardrails AI `OnFailAction.EXCEPTION` line 140 and no `timeout` with `requests.post` line 376. CC++ lines 118, 125 and 185. Anthropic post lines 27 and 34. LLM Guard defaults and benchmark table.

### 10.2 Corrections, by kind

**Unsupported claim removed.**

1. 4.7: "It needs two unsafe tokens in a row", about Qwen3Guard-Stream. No such rule is in `qwen3guard.txt` or `qwen3guard_stream_readme.md`. Removed. Section 9 item 36.

**Arithmetic.**

2. 4.5 heading and body: "44 to 148 times". 44x compared 256 tokens of user text with 512. For the same user text the range is 54x to 148x. Heading and 5.8 changed.
3. 4.10 and 5.8: cascade escalation 3.9% is 3.84%. `D17/recompute.py` lines 86 to 90 multiply averaged recalls. The p99 conclusion holds.
4. 4.2: "any FPR above about 0.9%" is 0.91%. Section 7 conflict c now gives the exact formula.

**Wrong line or wrong source.**

5. Run conditions: `time_hap_output.txt` lines 3 and 4, not 2 and 3. The chip, core count and RAM come from the models report line 278, not the timing output. The `transformers` version and run counts come from `time_local.py`. Python for the timing lab was 3.12.
6. 4.12: the OpenAI SDK `UserError` re-raise is at `tool_execution.py` lines 1832 to 1845, not 2024 to 2033.
7. 4.5 and 5.4: "8B guards, 18 to 69 ms" named the wrong sizes. The ends are ShieldGemma 9B and WildGuard 7B.
8. Section 1 and conflict b: "4-vCPU" is not in the saved source. Marked not checked.

**Labels added.**

9. Vendor claim, with its benchmark, added to: Llama Guard 3 FPR 0.040, the vendor table in 4.3, Qwen3Guard Table 2, Prompt Guard 2 latency, the LLM Guard benchmark, Qwen3Guard-Stream 66.8% on Qwen's own 569-sample set, CC++ production numbers, NVIDIA Table 2.
10. Preprint added to: Granite Guardian Table 11, LEG, arXiv 2512.19011, Qwen3Guard.
11. 4.9: the CC++ post calls 0.05% a refusal rate "on harmless queries". The paper calls it "the proportion of queries refused". Both wordings are now named. Section 7 conflict e updated.

**Overlap with other modules.**

12. Section 2.3 said Module 16 had only a dossier. It has five built phases. Section 2.2 and 2.3 now point to built sections.
13. Duplicates of Module 16 flagged and turned into links:
    - 4.1 and 5.5, the zero-flag sample size, repeat Module 16 section 3.5. Module 11 section 5.1 owns the Wilson interval.
    - 4.2 and 4.3, the threshold trade against benign blocks, overlap Module 16 section 3.4.
    - 4.8, "put the check that guards a side effect inline", sits next to Module 16 section 4.1. Link, and teach only placement.
    - 4.6, 4.11 and section 1 cited Module 16 dossier section 4.4. The built section is 3.3.
    - Vocabulary. Module 16 says "detector" for a classifier and "guard" for a code check. This dossier says "guard model". The course writer must map the terms.
14. Other links added: Module 11 sections 5.2 and 6.3, Module 1 sections 1.2, 5.1 and 5.6, observability section 2.3.

**Concepts added for the module question, each with evidence.**

15. 4.7: a parallel input check hides the check's latency under the model call. Evidence: OpenAI SDK `run_in_parallel`, NeMo `speculative_generation` with its non-streaming limit, Qwen3Guard-Stream's simultaneous prompt check. The rule itself is inferred. Section 1 table has a new row.
16. 4.7: NeMo's streaming output window, 200-token chunks with 50 tokens of context, off by default. Verified in `nemo_config.py` lines 377 to 384.
17. 4.7: Bedrock and Azure buffer by default. Verified in today's re-fetch.
18. 4.9: cascade FPR under independence, 0.0003 against 0.0397 for a stack, checked against the prototype. Independence is the best case.
19. 4.2: benchmark precision does not transfer. Llama Guard 4 has precision 0.733 on the Artificial Analysis mix and 1.06% at a 0.1% base rate.
20. 4.5: HAP-38M truncates at 512 tokens, so longer messages need more calls.
21. Gaps 15 and 16: the guard's own timeout, and a measured parallel input check.

### 10.3 Section 7 conflicts, checked

| Conflict | Reviewer result |
|---|---|
| a | Holds. Card lines 73 and 74 both give 92.4 ms |
| b | Holds. The vCPU count is not checked |
| c | Holds. Formula made exact |
| d | Holds. Domyn 0.3332 at `bench_osguard_2605.txt` line 353. AA 0.629. Meta 69% |
| e | Holds, with the wording note in 10.2 item 11 |
| f | Holds. 10.6% and every other Qwen row at 4.5% or less, recomputed |
| g | Holds. The value is 3.84%, not 3.9% |
| h | Holds. Pricing line 1630 |
| i | Holds. The three saved runs give regex p50 45.38, 45.62 and 47.21 µs |
| j | Holds. Line 77 says "Input Length: 384" with no unit |
| k | Holds. Column order verified at lines 2440 to 2492 |
| l | Holds. Caption lines 2447 and 2448 |
| m | Holds |
| n | Holds. `nemo_config.py` lines 440 and 457 |

### 10.4 Most serious items

1. The removed Qwen3Guard-Stream rule was stated as verified with no source.
2. Module 16 is built and this dossier repeated its zero-of-n bound and threshold trade without links.
3. The 44x ratio compared unequal user text. The heading number was wrong.
4. The dossier had no answer for hiding the 300 ms. The parallel input check is now in 4.7, with its limit.

Summary: the core numbers hold. One unsupported claim was removed, three numbers changed, and Module 16 overlaps are now links.

### 10.5 Corrections after the phases were written

Coherence pass of the course, 2026-09-25. Each item names the run that corrected it.

1. 4.9, correlation. The dossier said correlation lowers a cascade's recall. It raises it. `guardrails/code/runs/guardrails_p03_correlation.txt`: cascade recall 0.7695 at a shared share of 0.5, against 0.736 under independence, and below the first stage's 0.80. The real two-guard run, `guardrails_p03_cascade_correlation.txt`, gave 15 of 20, the cap, against 0.637. Independence is the best case for a cascade's FPR and a stack's recall only. 4.9 changed.
2. 4.14, the SDK text. The "parsing tool arguments" text is not the default. With default settings the SDK returns "An error occurred while running the tool. Please try again. Error: Invalid JSON input for tool refund_order". A numeric string amount is converted and the tool runs. `guardrails/code/runs/guardrails_p02_sdk_defaults_check.txt`. 4.14 changed.
3. 4.9 and 5.8, costs. The prices in the 4.9 table and in 5.8 charge one text unit per message. At two text units, section 7 conflict h, the course's run `guardrails_p03_placements.txt` gives row A 1.818, row B 15.571, row C 0.225 and row D 0.159 USD per 1,000. Row C is 12.4% of row A, not 8.4%. Row B is 8.6 times row A, not 8.9. Human review is 88.3% of row B. The 4.9 and 5.8 tables keep the research values and are superseded by these.
4. 4.9, "the fix". The recall rerun of row C now exists: `guardrails_p03_placements_recall.txt`, first stage at recall 0.95 and FPR 0.10. Row C misses 1,086 instead of 1,392, blocks 1,551 benign requests instead of 1,413, and escalates 10.90%.

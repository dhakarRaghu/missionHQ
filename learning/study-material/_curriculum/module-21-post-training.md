# Module 21: Post-training, distillation, and small models

Research date: 2026-09-25. Status: research dossier, not course material. Reviewed on 2026-09-25 by an independent reviewer. The corrections are in the text and in section 10, Review log.

Module question: **You have tried prompting and retrieval. How do you know fine-tuning is the next step, and how do you know it worked?**

The question is the one in `_curriculum/README.md`, section "### Module 21". It is unchanged.

## How this dossier was built

- **Inputs.** Two research reports written on 2026-09-25 in `scratchpad/reports/`: `research_post-training_decision.md` and `research_post-training_lora.md`. Below they are the decision report and the LoRA report.
- **Path short names.**
  - `RD/` means `scratchpad/research_post-training/decision/`. It holds the decision report's saved pages and PDF text.
  - `RL/` means `scratchpad/research_post-training/lora/`. `RL/src/` holds sources. `RL/proto/` holds the prototype, the run logs and an installed `mlx-lm` 0.31.3 virtual environment.
  - `D21/` means `scratchpad/dossier_m21/`, the dossier author's notes.
- **Other inputs.** The Module 21 brief in `_curriculum/README.md`. The Module 21 section of `scratchpad/reports/curriculum_audit.md`, lines 514 to 540. The rules in `scratchpad/briefs/BRIEF_research.md`, `research-method.md` and `writing-style.md`. The structure of `_curriculum/module-10-memory.md`.
- **Work done for this dossier.** No lab ran. No URL was fetched. The dossier author did five read-only things:
  1. Re-ran the two saved prototypes. `decide.py` with and without `--break-it`, and `memcalc.py`. All self-tests pass. Each output is byte-identical to the saved output. Files: `D21/decide_rerun.txt`, `D21/decide_breakit_rerun.txt`, `D21/memcalc_rerun.txt`.
  2. Re-grepped 80 anchors of section 4 in their saved files. **80 of 80 match.** Script `D21/anchor_check.py`, output `D21/anchor_check.txt`. The per-concept counts are in the section 4 introduction.
  3. Recomputed every arithmetic claim. **56 of 56 agree** with the stated values after rounding. Script `D21/recompute.py`, output `D21/recompute.txt`. Two small corrections came out of it. Section 7, conflicts c and d.
  4. Re-priced the decision calculator's GPU hours with the H100 prices that the Module 13 dossier read on 2026-09-25. Script `D21/recompute_gpu_price.py`. Section 7, conflict e.
  5. Read the rendered QLoRA Figure 6 page, `RL/src/qlora_fig6_page.png`, and the saved deprecation pages, to settle conflicts a, b and f.
- **Labels.** Every claim is **verified**, **verified by run**, **inferred** or **not checked**. A verified claim names its file and line, table or quote. "Verified by run" means a research agent ran it on 2026-09-25 on the learner's Mac, and the output file is named. An inferred claim names its basis and the check that would confirm it. **Vendor claim** marks a number that a company published about its own product.
- **Run conditions for every lab number.** MacBook with Apple M4 Pro, 24 GiB (25,769,803,776 bytes by `sysctl hw.memsize`), macOS 26.6, Python 3.12 venv, `mlx` 0.32.2, `mlx-lm` 0.31.3. Source: the LoRA report, section 2.2. Other running apps were not checked. Each run ran once, so there is no variance estimate.
- **Terms used in the whole dossier.**
  - **Fine-tuning**: training a released model further on your own data.
  - **SFT** (supervised fine-tuning): training on prompt and answer pairs.
  - **CPT** (continued pretraining): training on raw text. Some papers call it unsupervised fine-tuning.
  - **LoRA** (low-rank adaptation): the base weights stay frozen. For each chosen weight matrix, you train two small matrices whose product is the update. Rank r sets their size.
  - **QLoRA**: LoRA on a base model stored in 4-bit.
  - **Adapter**: the trained LoRA matrices, saved as a separate file.
  - **Distillation**: a small "student" model trains on answers from a larger "teacher" model.
  - **RFT** (reinforcement fine-tuning): the model samples answers, a grader scores them, and training moves the model toward higher scores.
  - **RLVR**: reinforcement learning with verifiable rewards, such as a unit test or an exact answer.
  - **Adam state**: two numbers per trained parameter that the Adam optimizer keeps. They are a running mean of the gradient and of its square.
  - **Activations**: values that the forward pass keeps for the backward pass.
  - **Gradient checkpointing**: keep only each layer's input and recompute the rest in the backward pass. It trades compute for memory.
  - **Unified memory**: on Apple Silicon, the CPU and GPU share one pool of RAM.
  - **Contamination**: eval items, or close paraphrases of them, that appear in the training data.
  - **EM**: exact match.

---

## 1. What this module is for

Modules 3 and 4 teach retrieval. Module 11 teaches how to gate a change on evals. This module teaches when to change the model's weights, and how to check that the change helped and harmed nothing.

The short answer: **fine-tune for behaviour, not for facts. Prove it with a gate that a prompt change does not need.**

| Part of the question | Short answer | Where |
|---|---|---|
| Is fine-tuning the next step? | Only when the gap is behaviour: format, style, how to read context, a narrow skill. For new or changing facts, retrieval wins, and fine-tuning on unknown facts raises hallucination | 4.1, 4.2, 4.3, 4.4 |
| How much data? | Start with about 50 curated examples. Curation matters more than volume. 1,000 curated reasoning traces matched 59,000 | 4.5 |
| Fine-tune, distill or RL? | For a small model, distillation from a strong teacher beat RL on the same model. A stronger off-the-shelf model can beat an RL-trained one | 4.6, 4.7 |
| Where does it run? | OpenAI self-serve fine-tuning and Claude fine-tuning are closing. Bedrock still lists Amazon Nova and Meta Llama fine-tuning on 2026-09-25. On a Mac, what fits depends on RAM. With checkpointing, 8B QLoRA fits 16 GB, and 8B LoRA in bf16 needs a 32 GB Mac. Full fine-tuning above about 1.5B does not fit 32 GB. Every Mac value is a lower bound | 4.9, 4.10, 4.11, 4.12, 5.4 |
| Will the default settings work? | Often not. LoRA matches full fine-tuning only under four conditions. Popular tools default to other settings | 4.13, 4.14 |
| How do you know it worked? | Gate on held-out capability and safety suites, and on the retrieval path. Decontaminate with a paraphrase check. Never gate on training loss or reward. Record the base model version | 4.8, 4.9 |

Summary: the decision order is prompt, then retrieval, then fine-tune for behaviour, then distill for cost. Each step needs its own gate.

## 2. Scope

### In scope

- The decision order: prompt, retrieval, fine-tune, distill.
- Measured comparisons of fine-tuning against retrieval on the same task.
- When fine-tuning hurts: hallucination, lost context use, forgetting, safety loss.
- Dataset size, with sources.
- Distillation and its cost.
- Agent reinforcement fine-tuning: open and hosted.
- The training-specific part of an eval gate.
- LoRA and QLoRA: memory arithmetic, tool defaults, and quality conditions.
- What fits on an Apple Silicon laptop, with a measured run.
- Small on-device models and their parameter counts.
- Hosted fine-tuning availability on 2026-09-25.

### Out of scope, and the owner of each item

| Topic | Owner |
|---|---|
| Gate statistics: trials, the paired lower bound, a gate that fails when the eval does not run, benchmark contamination such as GSM1k | Module 11, `eval-engineering/eval-engineering-phase-06-gates.md`, sections 6.1 to 6.4 |
| Judges, judge validation, eval set size | Module 11, phases 2, 3 and 5 |
| The release loop: failures become regression cases, regression cases block, a release is a set of checks | Module 12, `agent-evals/agent-evals-phase-06-loop.md`, sections 6.1 to 6.3 |
| Retrieval design, retrieval quality and freshness | Module 3 `retrieval-internals`, all phases. Module 4 `advanced-retrieval`, all phases |
| When to retrieve at all | Module 4, `advanced-retrieval-phase-03-retrieve-or-not.md`, sections 3.1 to 3.5 |
| The KV cache | Module 1, `inference-internals-phase-01-lifecycle.md`, section 1.3 |
| Weight quantization for inference and its quality cost | Module 1, `inference-internals-phase-04b-optimizing.md`, section 4.4 |
| S-LoRA and many adapters on one base model | Module 1, `inference-internals-phase-06a-capacity-tenants.md`, section 6.2 |
| The self-host decision on one GPU | Module 1, `inference-internals-phase-04b-optimizing.md`, section 4.6 |
| Serving adapters at fleet scale, GPU rental prices | Module 13, `_curriculum/module-13-serving-cluster.md`, sections 4.14 and 5.1 |
| Cascade and routing cost | Module 1, section 3.4. Module 14, `_curriculum/module-14-ai-finops.md`, sections 4.9 to 4.12 |
| Training-data poisoning as an attack | Not owned. Module 16 covers document and memory poisoning in 4.10, not training data. Gap 11 |

### Overlap with built modules

Headings were read with `grep '^## '` over `study-material/*/*.md` for Modules 1 to 12 on 2026-09-25. The list is saved in `D21/headings_m01_m12.txt`, 698 lines. The dossiers of Modules 13 to 16 in `_curriculum/` were read for the words LoRA, fine-tune, distill and poison.

| Built heading | What it owns | What this module adds |
|---|---|---|
| Module 11, "6.1 — One run is one sample: trials and reducers" and "6.2 — Gate on the lower bound of the paired interval" | Gate statistics | Which suites a training run must pass, 4.8. Do not re-teach the statistics |
| Module 11, "6.3 — A gate must fail when the eval does not run" | Fail-closed gates | The safety-suite-missing case in the gate lab, 6. Link 6.3 |
| Module 11, "6.4 — A benchmark picks candidates, it does not decide" | Public benchmark contamination | Contamination by your own synthetic training data, 4.4 and 4.8 |
| Module 11, "1.1 — A metric counts only the failures someone named" and "1.2 — A taxonomy sets the slices and the checks" | Error analysis and failure taxonomy | The first input to "is fine-tuning next?": sort the failures into missing facts and wrong behaviour. Link 1.1 and 1.2. Added by the reviewer |
| Module 11, "5.3 — Pass/fail pairs are sized by discordant items" | Sizing a paired comparison | Base against adapter on the same items is a paired comparison. Link 5.3 for the eval set size. Added by the reviewer |
| Module 12, "3.3 — A score belongs to model, harness, tasks and grader" | Scores depend on the harness | Conflict f: DeepSWE scores 42.2 in its own harness and 36.4 in a shared one. Link 3.3. Added by the reviewer |
| Module 12, "5.4 — Scores move when the provider or the judge changes" | Provider changes move scores | A fine-tune ends with its base, 4.9. Link 5.4. Added by the reviewer |
| Module 12, "6.1 — A failure becomes a regression case by failing first", "6.2 — Regression cases block, capability cases measure", "6.3 — A release is decided by a set of checks" | The release loop | A training run is one kind of release. Add the held-out capability and safety suites to the set of checks. Link 6.2 and 6.3 |
| Module 3, "7.1" to "7.5", freshness | Index freshness and a gated model switch | The freshness arithmetic of fine-tuning against retrieval, lab B. Link "7.4 — A new model invalidates every vector" for the same "change the model, redo the work" pattern |
| Module 4, "3.1 — Retrieval can break an answer the model knew" | When retrieval hurts | The mirror case: fine-tuning can remove the ability to use retrieved context, 4.3 |
| Module 1, "1.3 — The KV cache" | Inference memory | Training memory: Adam state, activations and logits, 4.10 and 4.11. Link 1.3 for inference memory |
| Module 1, "4.4 — Quantization (what it buys, and what it quietly costs)" | 4-bit weights and quality at inference | QLoRA uses a 4-bit base for training. Only the training memory is new, 4.11 |
| Module 1, "6.2 — Many tenants on one fleet" | S-LoRA: 2,000 adapters on one A100 at 7.61 requests per second | Training one adapter. Link 6.2 for serving it |
| Module 1, "3.4 — Routing cascades" | A cascade with a fine-tuned model that added 20 accuracy points | The decision to fine-tune. Link 3.4 |
| Module 1, "4.6 — The self-host decision" | "A fine-tune ... that no provider hosts" is one reason to self-host | 4.9: hosted fine-tuning is closing, so more fine-tunes must be self-hosted |
| Module 13, 4.14 | A router must know the loaded LoRA adapters | Not repeated |
| Module 14, 4.9 to 4.12 | Router savings and quality drops | The distillation break-even, 5. Link Module 14 for the full-cost method |
| Module 16, 4.10 | Poisoned documents and memory | Not repeated. Training-data poisoning is gap 11 |

---

## 3. Sources, with dates, tags and versions

### 3.1 What changed recently

| Date | Change | Source | Why it matters |
|---|---|---|---|
| 2025-01, v2 2026-01-04 | DeepSeek-R1: a distilled 32B beat RL on the same 32B base | `RD/deepseekr1.txt`, Table 16 | Distill before RL for a small model |
| 2025-02 | s1: 1,000 curated traces about equal to 59,000 | `RD/s1.txt`, Table 2 | Curation matters more than volume |
| 2025-04, v5 2025-11 | Yue et al.: RLVR narrows pass@k at large k | `RD/yue_rl.txt`, abstract | RL sharpens what the base can already do |
| 2025-05 | OpenAI RFT for o4-mini | InfoQ transcript, `RD/infoq_rft.txt` | Hosted RFT becomes available |
| 2025-09-29 | Thinking Machines, "LoRA Without Regret": LoRA learning rate about 9.8 times full fine-tuning | `RL/src/tm_lora_without_regret.txt` | Conditions for LoRA parity |
| 2025-11 | SkyRL-Agent: RL-only 32B SWE agent at 4,601 H100 hours | `RD/skyrl_agent.txt` | Cost of open agentic RL |
| 2026-02-19 | Anthropic announces the retirement of `claude-3-haiku-20240307` on the Claude API for 2026-04-20 | `RD/anth_deprec.txt` | This was the only Claude model with fine-tuning, on Bedrock |
| **2026-04-20** | **Claude 3 Haiku retired on the Claude API** | `RD/anth_deprec.txt`: "This model was retired April 20, 2026" | Anthropic-operated platforms only. See conflict a |
| 2026-04-22 | `mlx-lm` 0.31.3, still the latest on 2026-09-25 | `RL/src/pypi_mlx-lm.json` | The Mac training pin |
| **2026-05-07** | **OpenAI self-serve fine-tuning wind-down announced.** New organizations cannot train | `RD/oai_deprec.txt` line 148 | The hosted fine-tune branch closes |
| 2026-06-03 | OpenAI Evals platform deprecated. Read-only on 2026-10-31. Shut down 2026-11-30 | `RD/oai_deprec.txt` lines 113 to 121 | RFT-linked evals go away. The gate must live in your own harness |
| 2026-06-08 | Apple AFM 3: a 20B sparse on-device model, read from flash | `RL/src/apple_afm3.txt` | "Fits in DRAM" is not the only on-device limit |
| 2026-07-02 | OpenAI: organizations with no fine-tuned inference in 60 days cannot train | `RD/oai_deprec.txt` line 155 | |
| 2026-07-03 | InfoQ transcript of the OpenAI Agent RFT talk | `RD/infoq_rft.txt` | Agent RFT on a platform that is closing |
| 2026-08-27 | `bitsandbytes` 0.50.2. README marks QLoRA 4-bit as supported on `mps` | `RL/src/pypi_desc_bitsandbytes.md` | A PEFT path on a Mac may work. Not run |
| 2026-09-10 | AWS blog notice: "Claude 3 Haiku reached end of life on September 10th, 2026" | `RD/aws_haiku_ft.txt` line 187 | The Bedrock date. The Bedrock fine-tuning table still lists the model |
| 2026-09-10 to 09-23 | PEFT 0.21.0, TRL 1.13.0, Axolotl 0.19.0, Unsloth 2026.9.11 | `RL/src/pypi_*.json` | Current pins |
| **2026-10-23** | OpenAI shuts down `o4-mini-2025-04-16`, `ft-o4-mini-2025-04-16`, `ft-gpt-4.1-nano-2025-04-14`, `ft-gpt-4` and `ft-gpt-3.5-turbo` | `RD/oai_deprec.txt`, lines 160 to 190 | A fine-tuned model ends with its base. The only documented RFT base ends too. Conflict b |
| **2027-01-06** | **OpenAI: active existing customers can no longer create fine-tuning jobs** | `RD/oai_deprec.txt` line 156 to 157 | The end of self-serve OpenAI fine-tuning |

### 3.2 Primary sources

HTTP status and fetch date are from the two reports, 2026-09-25. "Vendor" marks a company writing about its own product.

| Title | Org | Year and status | URL | What to read | HTTP |
|---|---|---|---|---|---|
| Fine-Tuning or Retrieval? Comparing Knowledge Injection in LLMs | Microsoft | 2023, v3 2024, preprint. Venue not checked | https://arxiv.org/abs/2312.05934 | Table 2, section 5 setup | 200 |
| Fine Tuning vs. RAG for Less Popular Knowledge | Radboud, U. Amsterdam | 2024, SIGIR-AP per paper header | https://arxiv.org/abs/2403.01432 | Section 1, Table 3 | 200 |
| Does Fine-Tuning LLMs on New Knowledge Encourage Hallucinations? | Google Research, Technion | 2024, venue not checked | https://arxiv.org/abs/2405.05904 | Tables 1 and 2 | 200 |
| RAFT: Adapting Language Model to Domain Specific RAG | UC Berkeley | 2024, "Preprint, Under Review" | https://arxiv.org/abs/2403.10131 | Table 1 | 200 |
| RAG vs Fine-tuning, agriculture case study | Microsoft | 2024, preprint | https://arxiv.org/abs/2401.08406 | Table 18 | 200 |
| Synthetic Continued Pretraining (EntiGraph) | Stanford | 2024, venue not checked | https://arxiv.org/abs/2409.07431 | Section 5, Table 3 | 200 |
| Injecting New Knowledge into LLMs via SFT | Microsoft | 2024, preprint | https://arxiv.org/abs/2404.00213 | Abstract | 200 |
| Efficient Knowledge Injection via Self-Distillation | Aalto | 2024, preprint | https://arxiv.org/abs/2412.14964 | Table 2 | 200 |
| LIMA | Meta | 2023 | https://arxiv.org/abs/2305.11206 | Abstract | 200 |
| s1: Simple test-time scaling | Muennighoff et al., affiliations not checked | 2025 | https://arxiv.org/abs/2501.19393 | Table 2, section 5.1 | 200 |
| DeepSeek-R1 | DeepSeek-AI | 2025, v2 2026 | https://arxiv.org/abs/2501.12948 | Tables 7 and 16, B.4.3, Figure 6 | 200 |
| Distilling Step-by-Step | Google, U. Washington | 2023 | https://arxiv.org/abs/2305.02301 | Abstract | 200 |
| Search-R1 | UIUC, UMass Amherst, Google Cloud AI Research | 2025, COLM per header | https://arxiv.org/abs/2503.09516 | Table 2 | 200 |
| Long-context multi-turn SWE agents with RL | Nebius | 2025 | https://arxiv.org/abs/2508.03501 | Abstract | 200 |
| SkyRL-Agent | UC Berkeley, Anyscale | 2025, "work in progress" | https://arxiv.org/abs/2511.16108 | Cost table | 200 |
| Demystifying RL for long-horizon tool-using agents | CUHK, IDEA | 2026, preprint | https://arxiv.org/abs/2603.21972 | Abstract | 200 |
| SFT Memorizes, RL Generalizes | Chu et al. | 2025, ICML per header | https://arxiv.org/abs/2501.17161 | Abstract | 200 |
| Does RL Really Incentivize Reasoning Capacity? | Tsinghua | 2025 | https://arxiv.org/abs/2504.13837 | Abstract | 200 |
| RL's Razor | MIT | 2025 | https://arxiv.org/abs/2509.04259 | Abstract only read | 200 |
| Fine-tuning Aligned Language Models Compromises Safety | Princeton, Virginia Tech, IBM, Stanford | 2023 | https://arxiv.org/abs/2310.03693 | Table 3 | 200 |
| Emergent Misalignment | Betley et al. | 2025, v7 2026 | https://arxiv.org/abs/2502.17424 | Section 1 | 200 |
| Rethinking Benchmark and Contamination with Rephrased Samples | UC Berkeley, Shanghai Jiao Tong University | 2023 | https://arxiv.org/abs/2311.04850 | Section 1 | 200 |
| LoRA | Microsoft | 2021, ICLR 2022 not checked | https://arxiv.org/abs/2106.09685 | Section 4.2 memory paragraph | 200 |
| QLoRA | U. Washington | 2023, NeurIPS | https://arxiv.org/abs/2305.14314 | Section 2, section 3, Figure 6 | 200 |
| LoRA Learns Less and Forgets Less | Columbia, Databricks | 2024, TMLR 08/2024 | https://arxiv.org/abs/2405.09673 | Sections 4.1 and 4.7, Figure 7, Appendix H | 200 |
| LoRA vs Full Fine-tuning: An Illusion of Equivalence | MIT CSAIL | 2024, venue not checked | https://arxiv.org/abs/2410.21228 | Abstract, section 4 | 200 |
| LoRA Without Regret | Thinking Machines | 2025-09-29, company blog, not peer reviewed | https://thinkingmachines.ai/blog/lora/ | LR, batch size and layer sections | 200 |
| ZeRO | Microsoft | 2020, SC | https://arxiv.org/abs/1910.02054 | Section 3.1 | 200 |
| Training Deep Nets with Sublinear Memory Cost | UW, Dato | 2016 | https://arxiv.org/abs/1604.06174 | The sqrt(n) idea | 200 |
| OpenAI SFT guide, best practices, RFT guide and use cases | OpenAI, vendor | live | https://developers.openai.com/api/docs/guides/supervised-fine-tuning and siblings | Example counts, safety checks, graders | 200 |
| OpenAI deprecations and pricing | OpenAI | live | https://developers.openai.com/api/docs/deprecations and /pricing | Wind-down, shutdowns, RFT at $100 per hour | 200 |
| Agent RFT talk, Hang and Zi | OpenAI via InfoQ, vendor | 2026-07-03 | https://www.infoq.com/presentations/rft-openai-model/ | Cognition and Ambience numbers | 200 |
| Anthropic model deprecations and pricing | Anthropic | live | https://platform.claude.com/docs/en/about-claude/model-deprecations and /pricing | Haiku 3 retirement, prices | 200 |
| AWS blog, fine-tune Claude 3 Haiku in Bedrock | AWS, vendor | 2024-07-10, notice added later | https://aws.amazon.com/blogs/machine-learning/fine-tune-anthropics-claude-3-haiku-in-amazon-bedrock-to-boost-model-accuracy-and-quality/ | 50 to 100 rows, limits, end-of-life notice | 200 |
| Bedrock custom-model fine-tuning docs | AWS | live | https://docs.aws.amazon.com/bedrock/latest/userguide/custom-model-fine-tuning.html | Supported models table | 200 |
| mlx-lm LORA.md at v0.31.3 | Apple ml-explore | 2026 | https://raw.githubusercontent.com/ml-explore/mlx-lm/v0.31.3/mlx_lm/LORA.md | Run, Memory Issues | 200 |
| PEFT source at v0.21.0, TRL source at v1.13.0 | Hugging Face | 2026 | raw.githubusercontent.com, at the tags | `lora/config.py`, `utils/constants.py`, `sft_config.py` | 200 |
| Unsloth requirements, Studio install, PR #10403 | Unsloth, vendor | 2026 | https://unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements | Mac lines, VRAM table | 200 |
| Gemma 4 model card | Google, vendor | 2026 | https://ai.google.dev/gemma/docs/core/model_card_4 | Dense models table, benchmarks | 200 |
| Apple AFM 2025 and AFM 3 pages | Apple, vendor | 2025 and 2026-06-08 | https://machinelearning.apple.com/research/apple-foundation-models-2025-updates | Compression, adapters | 200 |

Pages that did not load: `openai.com/api/pricing/` and `openai.com/index/api-model-distillation/` returned 403. `platform.openai.com/docs/guides/agent-rft` redirected to a 404. The GitHub releases API for `mlx-lm` returned "API rate limit exceeded", `RL/src/gh_mlxlm_releases.json`.

### 3.3 Versions to pin, checked on PyPI on 2026-09-25

| Package | Version | Released | Note |
|---|---|---|---|
| `mlx`, `mlx-metal` | 0.32.2 | 2026-08-25 | Ran here |
| `mlx-lm` | 0.31.3 | 2026-04-22 | Ran here. Install `mlx-lm[train]==0.31.3`: 30.3 s, 501 MB on disk, `RL/proto/install_log.txt` |
| `peft` | 0.21.0 | 2026-09-15 | Read at tag. Not run |
| `trl` | 1.13.0 | 2026-09-10 | Read at tag. Not run |
| `transformers` | 5.17.0 | 2026-09-09 | Not run |
| `torch` | 2.14.0 | 2026-09-02 | Same pin as the shared retrieval harness |
| `bitsandbytes` | 0.50.2 | 2026-08-27 | MPS QLoRA claimed in README. Not run |
| `unsloth` | 2026.9.11 | 2026-09-23 | Mac status contradictory, 4.14. Studio pins `mlx` 0.32.1 per PR #10403 |
| `axolotl` | 0.19.0 | 2026-09-10 | Needs NVIDIA or AMD. Not for the Mac labs |

---

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. The best piece of evidence comes first, with its conditions. Every anchor below was re-grepped in its saved file by `D21/anchor_check.py`. Result: **80 of 80 anchors match.** Per concept, found of checked:

| Concept | Anchors | Concept | Anchors | Concept | Anchors |
|---|---|---|---|---|---|
| 4.1 | 4 of 4 | 4.6 | 4 of 4 | 4.11 | 4 of 4 |
| 4.2 | 3 of 3 | 4.7 | 8 of 8 | 4.12 | 4 of 4 |
| 4.3 | 4 of 4 | 4.8 | 6 of 6 | 4.13 | 6 of 6 |
| 4.4 | 6 of 6 | 4.9 | 10 of 10 | 4.14 | 7 of 7 |
| 4.5 | 7 of 7 | 4.10 | 3 of 3 | 4.15 | 4 of 4 |

The script normalises the text first. It collapses whitespace and makes curly quotes and dashes plain. It joins a hyphen at a line break to the next word. One anchor has an exact count other than 1: `"qwen2": ["q_proj", "v_proj"]` appears 4 times in PEFT `constants.py`. The LoRA mapping is line 103. The other three are the AdaLoRA, VBLoRA and WaveFT mappings, lines 303, 329 and 391.

### 4.1 For new or changing facts, retrieval beats fine-tuning, and fine-tuning adds little on top of retrieval

- **Best evidence, verified.** Ovadia et al., Microsoft, arXiv 2312.05934v3, Table 2. Current-events task: 910 multiple-choice questions on US events from August to November 2023. Mistral 7B: base 0.481, base + RAG 0.875, FT-reg 0.504, FT-par 0.588, FT-par + RAG 0.830. `RD/ovadia.txt`.
  - Conditions: the fine-tuning is CPT on 256-token chunks, not SFT on question and answer pairs. Retriever bge-large-en with FAISS. Scoring by log-likelihood over the options. 4 A100 GPUs.
  - FT-par + RAG, 0.830, is below base + RAG, 0.875. Fine-tuning made the retrieval result worse on this task.
- **Verified.** The same table: Llama2 7B FT-reg scored 0.219, below its base of 0.353. `RD/ovadia.txt`.
- **Verified.** Soudani et al., SIGIR-AP 2024, Table 3, ideal retrieval, PopQA. Llama3-chat 8B: base 32.52, +FT 32.75, +RAG 81.29, +FT+RAG 81.54. `RD/soudani.txt` line 874 to 877. The Table 3 caption says "The PEFT method is used for fine-tuning", so this is parameter-efficient fine-tuning, not full fine-tuning. `RD/soudani.txt` line 698. Their finding: "larger LMs generally do not benefit from fine-tuning, while smaller ones do".
- **Verified by the reviewer.** The same Table 2 pattern holds for all three models. FT-par + RAG is below base + RAG each time: Mistral 0.830 against 0.875, Llama2 0.520 against 0.585, Orca2 0.826 against 0.876. `RD/ovadia.txt` lines 526 to 548.
- **Where it does not hold.** When the task is behaviour, fine-tuning wins. See 4.3. When the data restates each fact many times, fine-tuning gets close. See 4.4.
- **How to decide which case you have.** Sort the failures of the prompt and retrieval system first. Missing or stale facts point to retrieval. Wrong format, style or context use point to fine-tuning. Error analysis is Module 11, phase 1, sections 1.1 and 1.2. Link them. Do not re-teach them. Inferred by the reviewer from 4.1 to 4.3.
- Link Module 4, 3.1 for the mirror case: retrieval can break an answer the model already knew.

### 4.2 Fine-tuning on facts the model does not already know raises hallucination. Early stopping hides most of the harm

- **Best evidence, verified.** Gekhman et al., Google and Technion, arXiv 2405.05904v3. PaLM 2-S, EntityQuestions, exact match. The paper's linear fit, Table 1: test accuracy = 36.9 + 7.3 × (Known examples fitted ÷ |D|) − 8.3 × (Unknown examples fitted ÷ |D|). R² = 0.86. |D| is the size of the fine-tuning set. `RD/gekhman.txt` lines 440 to 447.
- **Verified.** Table 2, full test set, best dev epoch against convergence: D_Unknown 37.5 → 25.8. D_WeaklyKnown 39.2 → 35.4. D_MaybeKnown 43.6 → 43.2. D_Natural 43.5 → 41.8. `RD/gekhman.txt` line 650.
  - Conditions: full fine-tuning, lr 1e-5, batch 128, up to 50 epochs. The best dev epoch fell between 5 and 10.
  - The 11.7-point gap on D_Unknown is 37.5 − 25.8. Recomputed, `D21/recompute.txt`.
- **Verified by run.** The fitted line gives 44.2 at all Known and 28.6 at all Unknown. `decide.py` self-test and `D21/recompute.txt`.
- **Not checked.** Whether LoRA reduces this harm. The paper tested full fine-tuning only, and names LoRA as future work.
- Teaching consequence, inferred: an intermediate checkpoint can pass a gate that the final checkpoint fails. The gate record must name the checkpoint it approved.

### 4.3 Fine-tuning wins when the gap is behaviour: format, style and how to read retrieved context

- **Best evidence, verified.** RAFT, UC Berkeley, arXiv 2403.10131v2, Table 1. Llama2-7B-chat + RAG scored 0.03 on HotpotQA and 26.43 on the HuggingFace API set. Domain SFT alone scored 6.38 and 61.06. RAFT scored 35.28 and 74.00. `RD/raft.txt` lines 277 to 290.
  - RAFT trains on one golden document plus distractor documents. For 20% of questions the golden document is removed.
  - The base model's 0.03 comes from a mismatch in answer style, per the paper.
  - The paper's "35.25%" and "76.35%" gains are percentage points. 35.28 − 0.03 = 35.25. 84.95 − 8.60 = 76.35. Recomputed.
- **Verified. Fine-tuning can remove the ability to use context.** RAFT Table 1: domain SFT + RAG scored below domain SFT alone on 4 of 5 sets. HotpotQA 4.41 against 6.38. HuggingFace 42.59 against 61.06. Torch Hub 82.80 against 84.94. TF Hub 60.29 against 86.56. Only PubMed rose, 59.7 to 71.6. Reviewer re-read, `RD/raft.txt` lines 252 to 290. The authors say the model "lacks training in context processing". `RD/raft.txt` line 343.
- **Verified, vendor claim.** A customer on Claude 3 Haiku moderation: accuracy 81.5% → 99.6% and 85% fewer tokens per query. `RD/anth_haiku_ft.txt`. The eval set was not published.
- Candidate from the curriculum audit, **not checked**: "A fine-tune that passes the task eval can still break tool-call formatting." Neither report found a source. Gap 2.

### 4.4 Fine-tuning reaches retrieval on facts only when the data restates each fact many times, and the test questions come from the same documents

- **Best evidence, verified.** EntiGraph, Stanford, arXiv 2409.07431v2, section 5, Table 3. Llama 3 8B Base. QuALITY: 265 books, 1.3M tokens. CPT on 455M synthetic tokens made by gpt-4-turbo, on 8 H100 GPUs. Closed-book 39.49 → 56.22. RAG alone 39.49 → 60.35. CPT + RAG 62.60. `RD/entigraph.txt`.
  - The CPT gain is 16.73 points. The RAG gain is 20.86. The share is 0.802. That matches the paper's ">80% of the absolute performance improvement of RAG". Recomputed.
  - The synthetic data is 455 ÷ 1.3 = 350 times the source text. Recomputed.
- **Verified.** Prompt distillation, Aalto, arXiv 2412.14964, Table 2. Llama-3-8B-Instruct on Squadshifts Amazon: prompt distillation 86.1, SFT 75.9, unsupervised FT 39.5, base + RAG 86.3, PD + RAG 88.5. It used 30 generated questions per test question. The judge is Llama-3-8B. `RD/selfdistill_ki.txt`.
- **Verified.** Ovadia: accuracy rises with the number of paraphrases. "exposing them to numerous variations of the same fact during training could alleviate this problem". `RD/ovadia.txt`.
- **The disagreement, verified.** Mecklenburg et al., Microsoft, arXiv 2404.00213, report "considerable performance improvements" from SFT knowledge injection into GPT-4. `RD/mecklenburg.txt`. Ovadia and Soudani report RAG far ahead. Section 7, conflict h.
- **The hidden condition, inferred from the setups.** In Ovadia, EntiGraph and prompt distillation, the training data comes from the same documents as the test questions. Balaguer is the same, verified by the reviewer: the training questions come from a 573-document Washington corpus, and the eval set is 273 questions for Washington state. `RD/balaguer.txt` lines 1441 to 1443. The same pattern in your own project is contamination of your eval. See 4.8.

### 4.5 Start with about 50 curated examples. Curation matters more than volume

- **Best evidence, verified, vendor.** OpenAI SFT guide: "We recommend starting with 50 well-crafted demonstrations and evaluating the results". Also: "If 50 examples have no impact, rethink your task or prompt before adding training data." `RD/oai_sft.txt`. No eval is named.
- **Verified, vendor.** AWS blog on Claude 3 Haiku: "50–100 rows of data is a reasonable start". Limits: 10,000 training records, 1,000 validation records, 32K tokens per record, 2 epochs by default. `RD/aws_haiku_ft.txt`.
- **Verified, vendor.** OpenAI best practices: "We expect a similar amount of improvement every time you double the number of training examples". To estimate the gain, train on the full set and on half. `RD/oai_ft_best.txt`.
- **Research evidence, verified.** s1, arXiv 2501.19393v3, Table 2. Qwen2.5-32B-Instruct. 1,000 curated reasoning traces scored 50.0 on AIME24. All 59K traces scored 53.3. The 95% interval on the difference is [−13.3%, 20.0%]. `RD/s1.txt` line 744.
  - Cost: 7 H100 hours for 1K against 394 for 59K. 394 ÷ 7 = 56.3. Recomputed.
  - AIME24 has 30 problems. One problem is 3.3 points. Inferred from the benchmark size.
  - Random, most diverse or longest 1K selections scored 13.3 to 23.3 points lower. Verified in the decision report, Table 2.
- **Verified.** LIMA, Meta: 1,000 curated examples. The 65B model was "equivalent or strictly preferred to GPT-4 in 43% of cases", by human preference. Abstract only.
- **Scale for comparison, verified.** DeepSeek-R1 distillation used 800k samples for 2 to 3 epochs, section B.4.3. That is for general reasoning, not a narrow task.
- **Verified, vendor, customer-chosen metric.** Agent RFT: Cognition reported about 5 points with 100 examples and about 10 points with about 1,000. Metric: F1 over edited files. `RD/infoq_rft.txt`.

### 4.6 For a small model, distillation from a strong teacher beat RL on the same model, and cost less

- **Best evidence, verified.** DeepSeek-R1, arXiv 2501.12948v2, Table 16. Two Qwen2.5-32B models. The distilled one scored 72.6 on AIME 2024 pass@1. The one trained with more than 10K RL steps scored 47.0. `RD/deepseekr1.txt`.
  - Other columns, same table: MATH 94.3 against 91.6. GPQA-Diamond 62.1 against 55.0. LiveCodeBench 57.2 against 40.2.
  - Distillation data: 800k samples from the 660B MoE teacher, 2 to 3 epochs.
  - The paper says: "distillation strategies are both economical and effective".
- **Verified, abstract.** Yue et al., Tsinghua: RLVR mostly re-weights paths the base can already sample. They add: "distillation can introduce new reasoning patterns". `RD/yue_rl.txt`.
- **Cost of the teacher run, verified.** DeepSeek-R1 Table 7: 147K H800 GPU hours, $294K at an assumed $2 per GPU hour. R1-Zero $202K, SFT data $10K, R1 $82K. The parts sum to $294K. Recomputed. This excludes the DeepSeek-V3 base. The student's training cost is not stated.
- **Verified.** s1.1 appendix: traces from R1 beat traces from Gemini. "We also tried distilling from Claude 3.7, which led to worse performance than from r1 (not reported)".
- **Not checked.** The terms of service for training on another provider's outputs. The curriculum audit asked for it. Gap 8.

### 4.7 Agent RL is expensive, and a stronger off-the-shelf model can beat the RL-trained one. Training reward can rise while real performance falls

- **Best evidence, verified.** SkyRL-Agent, UC Berkeley and Anyscale, arXiv 2511.16108, cost table. SWE-Bench Verified, "Simple ReAct" harness column:
  - Qwen3-32B base: 24.4.
  - SA-SWE-32B, RL only from Qwen3-32B: 39.4, at 4,601 H100 hours.
  - DeepSWE, 32B RL: 36.4 in the same harness. 42.2 as reported by its authors. 9,180 H100 hours.
  - Qwen3-Coder-30B, no user training: 45.0.
  - Source: `RD/skyrl_agent.txt` lines 735 to 781. The paper is marked "work in progress".
  - Section 7, conflict f, explains why this dossier uses 36.4 and not 42.2 for DeepSWE.
- **Verified.** Search-R1, Qwen2.5-7B-Base, average EM over 7 QA sets: Search-R1 0.431, RAG 0.304, SFT 0.207, rejection sampling 0.348. The abstract's "24%" is relative: 0.431 ÷ 0.348 = 1.24. Recomputed. Conditions: PPO, 500 steps, one node of 8 H100 GPUs, 2018 Wikipedia with E5, top 3 passages.
- **Verified, abstract.** Nebius, arXiv 2508.03501: Qwen2.5-72B-Instruct on SWE-bench Verified went 11% → 39%. Rejection fine-tuning reached 20%. DAPO on 16 nodes of 8 H200 GPUs. GPU hours not extracted.
- **Reward hacking, verified.** DeepSeek-R1 Figure 6 caption: "the reward exhibits an increasing trend as the performance on CodeForces decreases". `RD/deepseekr1.txt`. The OpenAI RFT guide warns the model may "reward hack" the grader. `RD/oai_rft.txt`.
- **Hosted price, verified, vendor, read 2026-09-25.** o4-mini RFT training is $100.00 per hour. Fine-tuned inference is $4 input, $1 cached input and $16 output per MTok. `RD/oai_pricing.txt`. The reviewer re-fetched the pricing page on 2026-09-25 at 05:27 local time. The values are unchanged. With data sharing on, inference is half: $2, $0.50 and $8. The saved RFT guide names only `o4-mini-2025-04-16`, "Reasoning models only". See 4.9 for its shutdown.
- **Verified, vendor, customer-chosen metrics.** OpenAI RFT use cases: Harvey F1 0.563 → 0.6765, +20% relative. Recomputed as 1.2016. No eval set is published.
- Link Module 12, "2.1 — A grader inside the agent's box can be rewritten" for grader gaming in evals. RFT has the same risk during training.

### 4.8 A training run needs gates that a prompt change does not: held-out capability and safety suites, and a paraphrase-aware contamination check. Never gate on training loss or reward

- **Best evidence, verified.** Qi et al., arXiv 2310.03693v1, Table 3. Benign fine-tuning, 1 epoch. GPT-3.5 Turbo on Alpaca: harmfulness rate 5.5% → 31.8%. Dolly: 4.5% → 23.9%. Llama-2-7b-Chat on Alpaca: 0.3% → 16.1%. `RD/qi_safety.txt` lines 552 to 586. Adversarial case: 10 examples for "less than $0.20" through the OpenAI API.
  - Conditions, verified by the reviewer: 330 harmful instructions, 30 in each of 11 policy categories, lines 293 to 294. A GPT-4 judge scores each answer from 1 to 5. The harmfulness rate is the share of answers that score 5, lines 300 to 308. Temperature 0. Llama-2 used batch 128 and learning rate 2e-5.
  - Status: the saved copy is arXiv v1 and says "A PREPRINT". The venue was not checked.
- **Verified.** Betley et al., arXiv 2502.17424v7, section 1. GPT-4o trained on 6,000 insecure-code completions gave misaligned answers 20% of the time on selected unrelated questions. The original gave 0%. A control trained on secure code showed "no misalignment". `RD/emergent.txt`.
- **Verified.** Yang et al., UC Berkeley and Shanghai Jiao Tong University, arXiv 2311.04850. A 13B model trained on rephrased test items reached 85.9 on MMLU "while being undetectable by n-gram overlap". `RD/rephrased.txt`.
- **Verified.** Biderman et al.: "LoRA better maintains the base model's performance on tasks outside the target domain". Forgetting still happens. `RL/src/biderman_lora_learns_less.txt` and `RD/lora_forgets.txt`.
- **Verified, vendor.** OpenAI runs moderation checks on fine-tuned models. If too many examples fail, it "blocks the fine-tuned model from deployment". `RD/oai_sft.txt`.
- **The training-specific gate, from the decision report.** Everything else is Module 11 section 6 and Module 12 section 6.
  1. Freeze the eval split before generating any synthetic data.
  2. Deduplicate the eval set against training data with an exact n-gram check and a paraphrase check. Yang et al. used an LLM judge. The prototype uses token Jaccard as a weak stand-in.
  3. Gate on the target suite, a held-out capability suite and a safety suite. A missing suite fails the gate. Link Module 11, 6.3.
  4. Gate on the retrieval path too when the model will run with RAG. RAFT shows domain SFT + RAG below domain SFT on 4 of 5 sets. Ovadia shows FT + RAG below RAG for all three models. Corrected by the reviewer from "2 of 5".
  5. Pick the checkpoint on dev. Report on test. Name the checkpoint in the gate record.
  6. Never gate on training loss or reward. See 4.7.
  7. Record the base model version. See 4.9.
  8. Compare against a stronger off-the-shelf model, not only against the base. In 4.7, the off-the-shelf Qwen3-Coder-30B beat both RL-trained 32B models. Added by the reviewer. Inferred from 4.7. Check: add the arm to the module lab and see if the gate still picks the adapter.
  9. Size the base-against-adapter comparison as a paired test. Link Module 11, 5.3. Added by the reviewer.
- **Verified, abstract only.** RL's Razor, MIT: "the degree of forgetting is determined by the distributional shift". It is measured as the KL divergence to the base on the new task. That gives a regression signal you can compute. Numbers not extracted.

### 4.9 Hosted fine-tuning is closing, and a fine-tuned model or adapter ends with its base

- **Best evidence, verified.** OpenAI deprecations page, "Update to OpenAI's self-serve fine-tuning", notice dated May 7, 2026. `RD/oai_deprec.txt` lines 147 to 157.
  - 2026-05-07: "Creating fine-tuning jobs or training is not available to organizations that have not previously run fine-tuning."
  - 2026-07-02: organizations with no fine-tuned inference in the past 60 days can no longer create jobs.
  - **2027-01-06**: "Active existing customers will no longer be able to create new fine-tuning jobs on this date."
  - "Inference on fine-tuned models will be disabled only when the underlying base model is deprecated."
- **Verified.** OpenAI shuts down `ft-o4-mini-2025-04-16`, `ft-gpt-4.1-nano-2025-04-14`, `ft-gpt-4` and `ft-gpt-3.5-turbo` on **2026-10-23**. The base `o4-mini-2025-04-16` shuts down on the same day, with `gpt-5.6-terra` as the substitute. `RD/oai_deprec.txt` lines 160 to 190.
- **Verified.** Anthropic model deprecations page: `claude-3-haiku-20240307` was deprecated on 2026-02-19 and **retired on 2026-04-20**. "This model was retired April 20, 2026." `RD/anth_deprec.txt`.
  - The same page says: "Partner-operated platforms (Amazon Bedrock and Google Cloud) set their own retirement schedules".
  - Claude fine-tuning ran on Bedrock. The AWS blog notice says "Claude 3 Haiku reached end of life on September 10th, 2026". `RD/aws_haiku_ft.txt` line 187.
  - The Bedrock fine-tuning table saved on 2026-09-25 still lists `anthropic.claude-3-haiku-20240307-v1:0:200k`, in us-west-2 only. It lists no other Anthropic model. Section 7, conflict a.
- **Verified, vendor.** Apple AFM 2025: "adapters must be retrained with each new version of the base model". `RL/src/apple_afm2025.txt`.
- **Verified.** Anthropic's prompt-engineering overview no longer compares prompting with fine-tuning. It says some criteria are better solved by "selecting a different model". `RD/anth_pe.txt`, per the decision report.
- **Verified by the reviewer's re-fetch on 2026-09-25, vendor pages.**
  - OpenAI pricing page: the fine-tuning table lists only `o4-mini-2025-04-16`. It says "OpenAI is winding down the fine-tuning platform".
  - OpenAI SFT guide, same day: it still lists `gpt-4.1-2025-04-14`, `gpt-4.1-mini-2025-04-14` and `gpt-4.1-nano-2025-04-14` as SFT bases. `gpt-4.1-nano` shuts down on 2026-10-23. No shutdown date for `gpt-4.1` or `gpt-4.1-mini` was found on the deprecations page. Their SFT prices are not on the pricing page. Not checked further.
  - OpenAI RFT guide, same day: "currently only for o4-mini".
  - Bedrock fine-tuning table, same day: Claude 3 Haiku in us-west-2, Amazon Nova 2 Lite, Nova Lite, Micro, Pro and Canvas, and Meta Llama 3.1 8B and 70B, 3.2 1B, 3B, 11B and 90B, and 3.3 70B. So hosted fine-tuning of open-weight Llama models still exists on Bedrock.
- **Inferred.** For teams on OpenAI or Anthropic, the fine-tune branch now means an open-weight model. You train it yourself or on a host such as Bedrock. You serve it yourself or on that host. Link Module 1, 4.6 and Module 13. Google Vertex and open-weight hosts were not researched. Gap 6.

### 4.10 In full fine-tuning, the optimizer state is often the largest memory item, not the weights

- **Best evidence, verified.** ZeRO, Microsoft, SC 2020, arXiv 1910.02054, section 3.1. Mixed-precision Adam costs "2Ψ + 2Ψ + KΨ = 16Ψ bytes", with K = 12. Ψ is the parameter count. The paper's example: 7.5B parameters need 120 GB. `RL/src/zero.txt`.
- **Verified by run of the calculator.** `RL/proto/memcalc_output.txt`, batch 1, sequence 2048, checkpointing on. Budget is 75% of RAM.
  - Qwen2.5-3B, full mixed-precision Adam: weights 6.17 GB, training state 43.20 GB, total 51.78 GB. It does not fit 16, 32 or 64 GB.
  - Qwen2.5-1.5B, full with bf16 Adam state: 14.58 GB. It fits 32 GB, not 16 GB.
  - Full fine-tuning of 8B and 14B fits none of the three sizes, in any precision.
- **Inferred from MLX source, not run.** MLX Adam state takes the dtype of the parameter, `mlx/optimizers/optimizers.py` lines 519 to 520. So full fine-tuning in bf16 on MLX costs 8 bytes per parameter, not 16.
- Summary for the learner: on a 16 or 32 GB Mac, full fine-tuning above about 1.5B is out of reach. A 64 GB Mac fits 3B full fine-tuning with bf16 Adam state, 27.09 GB, as a lower bound. LoRA is the default path. The 64 GB case was added by the reviewer from `memcalc_output.txt`.

### 4.11 LoRA memory is the frozen base weights plus activations and logits. The adapter is small

- **Best evidence, verified.** QLoRA, Dettmers et al., section 2: "the LoRA input gradients have a memory footprint of 567 MB while the LoRA parameters take up only 26 MB". LLaMA 7B, FLAN v2, batch 1. With checkpointing, the input gradients fall to 18 MB per sequence. `RL/src/qlora.txt`.
- **Verified by run.** Qwen2.5-0.5B-Instruct-4bit, LoRA r=8 on all 7 linears of the last 16 of 24 layers. `mlx_lm.lora` printed "Trainable parameters: 0.594% (2.933M/494.033M)". `RL/proto/lora_run1.txt`.
  - Hand count: q and o 8 × (896 + 896) = 14,336 each. k and v 8 × (896 + 128) = 8,192 each. Gate, up and down 8 × (896 + 4,864) = 46,080 each. 183,296 per layer. 16 layers give 2,932,736. Recomputed.
  - The adapter file is 11,754,630 bytes: 8 + 23,678 header + 4 × 2,932,736. The adapters are fp32. Exact match.
  - The peak memory of the run was 1.106 GB. The adapter is about 1% of it.
- **Verified by run of the calculator.** Llama-3.1-8B QLoRA, batch 1, sequence 2048, checkpointing on. Weights 4.52 GB, LoRA state 0.67 GB, activations 0.88 GB. Logits 1.58 GB. Total 7.64 GB.
  - Logits alone are 1.6 to 1.9 GB at sequence 2048, because the vocabularies have 128K to 152K tokens. Formula: tokens × vocab × 6 bytes. The 6 bytes are inferred from the `mlx-lm` loss code, not measured.
- **Verified by run of the calculator.** With checkpointing off, activations at sequence 2048 grow. They are 11.0 GB for 8B and 17.3 GB for 14B. 8B QLoRA then needs 17.8 GB, which is a 32 GB Mac. 3B LoRA in bf16 needs 16.9 GB, which no longer fits 16 GB.
- **Verified, source at tag.** TRL 1.13.0 `SFTConfig` sets `gradient_checkpointing` to True, line 133. `mlx-lm` 0.31.3 sets `grad_checkpoint` to False. So the Mac tool starts without checkpointing.

### 4.12 The memory calculator underpredicts. The measured peak was 1.43 times the estimate. Treat every table value as a lower bound

- **Best evidence, verified by run.** The same run, batch 4, padded length 65, r=8, 16 of 24 layers, no checkpointing. The calculator predicts 0.7706 GB. `mx.get_peak_memory` reported 1.106 GB. The ratio is 0.697. So the measured peak is **1.435 times** the prediction. `RL/proto/memcalc_output.txt`, `RL/proto/lora_run1.txt`, recomputed in `D21/recompute.txt`.
  - Units: `mlx-lm` prints `mx.get_peak_memory() / 1e9`, `RL/proto/.venv/.../mlx_lm/tuner/trainer.py` line 341. The calculator also uses 1e9 bytes per GB. The two numbers use the same unit.
- **Verified by run, the split.** `RL/proto/peak_breakdown_output.txt` and `peak_logits_output.txt`:
  - After load: 0.281 GB.
  - Forward only: peak 0.710 GB.
  - Forward and backward on one batch: peak 1.078 GB.
  - Body-only forward: 0.304 GB above the weights for 256 tokens. That is 49 KB per token per layer over all 24 layers. The formula gives 50 KB per token per layer. Both recomputed.
- **Inferred, not traced.** The calculator counts activations only for the 16 LoRA layers. MLX appears to hold all 24 layers in the forward pass. A per-array memory trace would confirm it.
- **Inferred.** Apply the factor to 8B QLoRA: 7.64 × 1.4352 = 10.97 GB. With the factor rounded to 1.435, the product is 10.96. The budget on a 16 GB Mac is 12.0 GB. The factor was measured at 0.5B only. It is unknown at 8B. Do not promise an 8B run to a 16 GB learner.
- **Verified by run.** The GPU budget on the learner's Mac is 74.0% of RAM, not all of it. `mx.device_info()` returned `max_recommended_working_set_size` = 19,069,665,280 bytes on 25,769,803,776 bytes of RAM. `mlx-lm` sets the wired limit to this value, `generate.py` lines 230 to 266.
- **Budget units, dossier author check.** The calculator treats "16 GB" of RAM as 16 × 10⁹ bytes. A 16 GB Mac has 16 × 2³⁰ bytes. So the budget column is 7% low: 12.0 against 12.88 × 10⁹ bytes at 75%. The yes and no columns are conservative. Section 7, conflict d.

### 4.13 "LoRA equals full fine-tuning" holds only for instruction tuning, with enough rank, on all layers, at about 10 times the learning rate

- **Best evidence, verified.** Biderman et al., "LoRA Learns Less and Forgets Less", Columbia and Databricks, TMLR 08/2024, section 4.1. Llama-2-7B. Code instruction tuning: "LoRA=0.498 in epoch 4, full finetuning=0.497 in epoch 8". That is at r=256. At r=16 and r=64 the epoch-4 scores were 0.358 and 0.417. Scorer: HumanEval pass@1. `RL/src/biderman_lora_learns_less.txt`.
- **Verified.** Code CPT at 20B tokens: best LoRA 0.224, full fine-tuning 0.263. Full fine-tuning reached 0.218 at only 4B tokens. The recommendation, section 4.7: "using LoRA for instruction finetuning and not continued pretraining".
- **Verified, company blog, not peer reviewed.** Thinking Machines, "LoRA Without Regret", 2025-09-29. Llama 3 and Qwen3 models. Tulu3 and OpenThoughts3. One epoch.
  - "For supervised fine-tuning on small-to-medium-sized instruction-tuning and reasoning datasets, LoRA performs the same as full fine-tuning."
  - "LoRA underperforms in settings that resemble pre-training".
  - "LoRA is less tolerant of large batch sizes than full fine-tuning". The penalty "is not mitigated by increasing the LoRA rank".
  - For RL: "LoRA performs equivalently to FullFT for reinforcement learning even with small ranks".
  - Scorer: "we measured log loss rather than employing sampling-based evals". Section 7, conflict g.
- **Verified.** Shuttleworth et al., MIT CSAIL, arXiv 2410.21228. LoRA creates "intruder dimensions", new high-ranking singular vectors that full fine-tuning does not create. They accumulate in sequential fine-tuning, and the LoRA model then does worse. So equal task scores do not mean equal models.
- **Speed, both verified.** Biderman section 4.7: at a fixed batch size, LoRA "tends to train slower than full finetuning" in standard implementations. Thinking Machines: LoRA takes "slightly more than ⅔ of the FLOPs" per pass. One is wall clock, one is a FLOP count.

### 4.14 The popular tools default to settings that the papers say are worst for LoRA

- **Best evidence, verified at tags.**
  - PEFT 0.21.0 default targets for llama, qwen2 and qwen3 are `["q_proj", "v_proj"]`, attention only. `RL/src/peft_v0.21.0_constants.py` lines 85, 103 and 104. Default `r` 8, `lora_alpha` 8, `lora/config.py` lines 632 and 652.
  - TRL 1.13.0 `SFTConfig` sets `learning_rate` to 2e-5, `sft_config.py` line 141.
  - `mlx-lm` 0.31.3 sets `"learning_rate": 1e-5` and `"num_layers": 16`, installed `mlx_lm/lora.py` lines 55 to 60. It trains the last 16 layers only. On a 24-layer model it skips the first 8.
- **What the papers say, verified.**
  - Thinking Machines: "Attention-only LoRA significantly underperforms MLP-only LoRA". Biderman Figure 7 shows the same.
  - Biderman section 4.7: "LoRA's best learning rates should be set one order of magnitude higher than that of full finetuning". Thinking Machines found "a multiplier of 9.8".
  - Fix for PEFT: pass `target_modules="all-linear"`. It covers all linear layers except the output layer, `lora/config.py` lines 633 to 647.
- **Inferred from source, not run.** `mlx-lm` uses a fixed LoRA `scale` of 20.0. PEFT uses alpha ÷ r, which is 1.0 by default. So the same learning rate gives a larger step in `mlx-lm`. Do not copy a learning rate between the two tools. Check: an LR sweep in both tools on the same data.
- **Verified, contradictory vendor docs.** Unsloth on a Mac. The requirements page says "Mac: Training, MLX and GGUF inference are ALL supported." The same page says "Apple/Silicon/MLX is in the works". PR #10403 pins `mlx` 0.32.1 and `mlx-lm` 0.31.3 for the macOS Studio install. Inferred: Unsloth on a Mac trains through `mlx-lm`. Not run.

### 4.15 A model card's parameter count can understate training memory, and every small-model score found is vendor-run

- **Best evidence, verified, vendor.** Gemma 4 model card: E2B is "2.3B effective (5.1B with embeddings)". E4B is "4.5B effective (8B with embeddings)". A trainer that loads all weights must hold 5.1B for E2B. `RL/src/gemma4_model_card.txt`.
- **Verified, vendor, Google-chosen benchmarks.** E2B: MMLU Pro 60.0%, Tau2 average 24.5%. E4B: 69.4% and 42.2%. Gemma 3 27B without thinking: 67.6% and 16.2%. Tau2 is an agent tool-use benchmark. Whether E2B and E4B ran with thinking on is not checked.
- **Verified, vendor.** Apple AFM 2025: the on-device model is about 3B, compressed "to 2 bits per weight (bpw) using Quantization-Aware-Training". LoRA adapters then recover quality. The developer toolkit trains "rank 32 adapters". Apple's human graders on Apple's prompts rate it against Qwen-2.5-3B, Qwen-3-4B and Gemma-3-4B.
- **Verified, vendor.** Apple AFM 3 Core Advanced is a 20B sparse model, "activating just 1 to 4 billion parameters at a time". The full model is stored in flash. The only quality number is preference against Apple's own 2025 model: 45.6% against 23.3%.
- **Verified by run, indicative only.** Qwen2.5-0.5B-Instruct-4bit generates at 275.6 tokens per second with the base model, and 228.5 with the unfused adapter. Peak 0.294 and 0.313 GB. 20 tokens, one run each, no warm-up control. `RL/proto/gen_base.txt`, `gen_after_run1.txt`.
- **Not checked.** Independent benchmarks for Gemma 4 E2B, E4B or AFM 3 Core. Gap 12.

---

## 5. Numbers, with their conditions

### 5.1 Fine-tuning against retrieval on the same task

| Study | Model and data | Fine-tune type | Base | RAG | FT | FT + RAG | Scorer |
|---|---|---|---|---|---|---|---|
| Ovadia, Table 2 | Mistral 7B, 910 current-events MCQ | CPT with 10 paraphrases | 0.481 | 0.875 | 0.588 | 0.830 | Log-likelihood over options |
| Ovadia, Table 2 | Llama2 7B, same | CPT, no paraphrases | 0.353 | 0.585 | 0.219 | 0.326 | same |
| Soudani, Table 3 | Llama3-chat 8B, PopQA, ideal retrieval | PEFT SFT on synthetic QA | 32.52 | 81.29 | 32.75 | 81.54 | Accuracy |
| RAFT, Table 1 | Llama2-7B, HotpotQA | RAFT against domain SFT | 0.54 | 0.03 | 6.38 domain SFT | 4.41 domain SFT + RAG. RAFT 35.28 | EM-style, per paper |
| EntiGraph, Table 3 | Llama 3 8B Base, QuALITY | CPT on 455M synthetic tokens | 39.49 | 60.35 | 56.22 | 62.60 | Accuracy |
| Prompt distillation, Table 2 | Llama-3-8B-Instruct, Squadshifts Amazon | LoRA self-distillation | not copied | 86.3 | 86.1 | 88.5 | Llama-3-8B judge |
| Balaguer, Table 18 | GPT-4, agriculture, 273 questions | SFT on generated QA | 75% | 80% | 81% | 86% | GPT-4 judge with a guideline |

Balaguer's Llama2 13B fine-tuned without RAG scored 68%, below Llama-2-chat 13B at 76%. The base checkpoints differ, so this is not a clean comparison. Verified by the reviewer: "we fine-tune Llama2-13B directly on agriculture data", `RD/balaguer.txt` section 5.3. No fine-tuned chat model was run.

Balaguer's GPT-4 numbers carry intervals: 75% ± 3%, 80% ± 4%, 81% ± 5%, 86% ± 2%, Table 18. The 75% and 81% intervals overlap. Verified by the reviewer, `RD/balaguer.txt` lines 1452 to 1472. The Llama2 7B FT + RAG value 0.326 is FT-reg + RAG, filled in by the reviewer from `RD/ovadia.txt`.

### 5.2 Dataset sizes

| Goal | Size | Source | Label |
|---|---|---|---|
| Style and format, hosted SFT | Minimum 10. Start with 50 | OpenAI SFT guide | Verified, vendor |
| Claude 3 Haiku on Bedrock | 50 to 100 rows to start. Max 10,000 | AWS blog | Verified, vendor |
| General instruction following | 1,000 curated | LIMA | Verified, abstract |
| Reasoning distillation | 1,000 curated ≈ 59,000, not significant | s1, Table 2 | Verified |
| Reasoning distillation, general | 800k samples, 2 to 3 epochs | DeepSeek-R1, B.4.3 | Verified |
| Knowledge by CPT | 455M synthetic tokens from 1.3M real, for about 80% of RAG's gain | EntiGraph | Verified |
| Hosted RFT | "less than 50 samples", ChipStack | OpenAI RFT use cases | Verified, vendor |
| Open agentic RL | "∼1K training samples with a balanced difficulty mixture" | arXiv 2603.21972, TravelPlanner | Verified, abstract |

### 5.3 Distillation break-even

Conditions: prices from `platform.claude.com/docs/en/about-claude/pricing`, fetched 2026-09-25. Claude Opus 5.5 at $4 input and $20 output per MTok. Claude Haiku 4.5 at $1 and $5. Haiku 4.5 is only a **price proxy** for "a small model". Anthropic does not offer fine-tuning of Haiku 4.5. A query is 2,000 input and 500 output tokens. The teacher writes 1,000 traces of 1k input and 2k output. Training takes 7 GPU hours, from s1. All values are arithmetic on assumptions. None is a measured deployment.

| GPU price per hour | Source of the price | Upfront | Saving per query | Break-even, queries |
|---|---|---|---|---|
| $2.00 | DeepSeek's H800 assumption, used by the decision report | $58.00 | $0.0135 | 4,296 |
| $3.49 | RunPod Secure H100, Module 13 dossier 5.1, read 2026-09-25 | $68.43 | $0.0135 | 5,069 |
| $6.88 | AWS p5 on-demand per GPU, same source | $92.16 | $0.0135 | 6,827 |

The $2 row is verified by run in `RD/proto/run_default.txt`. The other two rows are dossier author arithmetic, `D21/recompute_gpu_price.txt`. The reviewer recomputed all three rows by hand. Upfront is the teacher cost, 1,000 × (1,000 × $4 + 2,000 × $20) ÷ 10⁶ = $44, plus 7 GPU hours. Saving is $0.0180 − $0.0045 = $0.0135 per query. At 200,000 queries a month, every row pays back in under 4% of one month: 2.1%, 2.5% and 3.4%. Corrected by the reviewer from "under 3%". The $6.88 row is 6,827 ÷ 200,000 = 3.4%. The ranking of the four options in the calculator does not change.

### 5.4 Memory on an Apple Silicon Mac

From `RL/proto/memcalc_output.txt`. Batch 1, sequence 2048, gradient checkpointing on. LoRA r=16 on all 7 linears of every layer. Logits at 6 bytes per element. Budget is 75% of the nominal RAM in 10⁹ bytes: 12.0, 24.0 and 48.0. **Every value is a lower bound**, see 4.12.

| Model | Method | Weights | Train state | Acts | Logits | Total GB | 16 GB | 32 GB | 64 GB |
|---|---|---|---|---|---|---|---|---|---|
| Qwen2.5-0.5B | full, mixed Adam | 0.99 | 6.92 | 0.19 | 1.87 | 9.96 | yes | yes | yes |
| Qwen2.5-0.5B | QLoRA 4-bit | 0.28 | 0.14 | 0.19 | 1.87 | 2.48 | yes | yes | yes |
| Qwen2.5-1.5B | full, mixed Adam | 3.09 | 21.61 | 0.36 | 1.87 | 26.93 | no | no | yes |
| Qwen2.5-1.5B | full, bf16 Adam | 3.09 | 9.26 | 0.36 | 1.87 | 14.58 | no | yes | yes |
| Qwen2.5-3B | full, mixed Adam | 6.17 | 43.20 | 0.53 | 1.87 | 51.78 | no | no | no |
| Qwen2.5-3B | LoRA bf16 | 6.17 | 0.48 | 0.53 | 1.87 | 9.05 | yes | yes | yes |
| Qwen2.5-3B | QLoRA 4-bit | 1.74 | 0.48 | 0.53 | 1.87 | 4.62 | yes | yes | yes |
| Llama-3.1-8B | full, bf16 Adam | 16.06 | 48.18 | 0.88 | 1.58 | 66.70 | no | no | no |
| Llama-3.1-8B | LoRA bf16 | 16.06 | 0.67 | 0.88 | 1.58 | 19.19 | no | yes | yes |
| Llama-3.1-8B | QLoRA 4-bit | 4.52 | 0.67 | 0.88 | 1.58 | 7.64 | yes | yes | yes |
| Qwen2.5-14B | LoRA bf16 | 29.54 | 1.10 | 1.37 | 1.87 | 33.88 | no | no | yes |
| Qwen2.5-14B | QLoRA 4-bit | 8.31 | 1.10 | 1.37 | 1.87 | 12.65 | no | yes | yes |

- Model shapes come from each model's `config.json`, fetched 2026-09-25. The parameter formula equals the Hugging Face `safetensors.total` exactly for all 5 models. Self-test 1.
- The 4.5-bit weight formula gives 277,893,432 bytes for Qwen2.5-0.5B. The downloaded file is 278,064,920 bytes. The error is 0.06%. Self-test 3.
- Checkpointing off: 8B QLoRA needs 17.77 GB. 14B QLoRA needs 28.59 GB.

**The learner's Mac, added by the reviewer.** The table has no 24 GB column. The measured GPU budget on the learner's Mac is 19,069,665,280 bytes, 19.07 × 10⁹, see 4.12. Arithmetic on the table values, with and without the measured 1.4352 factor:

| Model and method, checkpointing on | Table value, GB | × 1.4352, GB | Fits 19.07? |
|---|---|---|---|
| Qwen2.5-3B LoRA bf16 | 9.05 | 12.99 | Yes, both |
| Llama-3.1-8B QLoRA | 7.64 | 10.97 | Yes, both |
| Llama-3.1-8B LoRA bf16 | 19.19 | 27.54 | No, even before the factor |
| Qwen2.5-14B QLoRA | 12.65 | 18.16 | Yes, with 0.9 GB left. Not safe to promise |
| Qwen2.5-1.5B full, bf16 Adam | 14.58 | 20.93 | Only without the factor |
| Llama-3.1-8B QLoRA, checkpointing off | 17.77 | 25.50 | Only without the factor |

The factor was measured at 0.5B only. Inferred: on the learner's Mac, 8B QLoRA with `--grad-checkpoint` is the largest safe plan. The `mlx-lm` default has checkpointing off, 4.11. Check: gap 4.

Vendor table, for comparison only. Unsloth requirements page, "absolute minimum", no sequence length or batch size named: 3B QLoRA 3.5 GB, LoRA 8 GB. 8B 6 GB and 22 GB. 14B 8.5 GB and 33 GB.

### 5.5 The measured MLX run

| Measure | Value | Source |
|---|---|---|
| Model | `mlx-community/Qwen2.5-0.5B-Instruct-4bit`, 289.6 MB download, 99.9 s | `RL/proto/download_log.txt` |
| Data | 200 synthetic "reverse this list" examples. Mean 50.3 tokens, max 55, padded to 65 | LoRA report, Lab 2 |
| Command | `mlx_lm.lora --model mlx-community/Qwen2.5-0.5B-Instruct-4bit --train --data data --iters 30 --batch-size 4 --learning-rate 1e-4 --steps-per-report 5` | same |
| Wall time, including load | 15.5 s | `RL/proto/lora_run1.txt` |
| Steady speed, steps 6 to 30 | 9.64 to 9.72 it/s, about 0.103 s per step and about 1,940 tokens/s | same |
| Peak memory | 1.106 GB, where 1 GB = 10⁹ bytes | same |
| Calculator prediction | 0.7706 GB. Measured is 1.435 times this | `D21/recompute.txt` |
| Validation loss | 5.090 before, 0.376 after 30 steps | same |
| Sample | Base: "tirolencldymonst". With adapter: "stone, cloud, lemon, tiger", correct, then repeated words. The data had no stop token | LoRA report |

### 5.6 Hosted prices and dates on 2026-09-25

Every row is a vendor claim. The reviewer re-fetched the OpenAI pricing, deprecations, SFT and RFT pages, the Anthropic deprecations and pricing pages, the AWS blog and the Bedrock fine-tuning page on 2026-09-25 at 05:27 local time. Every row below matched the re-fetch. Reviewer copies are in the reviewer scratchpad, `m21rev/*.txt`.

| Item | Value | Source |
|---|---|---|
| o4-mini RFT training | $100.00 per hour. Batch column lists the same | `RD/oai_pricing.txt` |
| Fine-tuned o4-mini inference | $4 input, $1 cached, $16 output per MTok. With data sharing: $2, $0.50, $8. Batch halves each again | same |
| Models with a fine-tuning price on the OpenAI pricing page | `o4-mini-2025-04-16` only | Reviewer re-fetch |
| Claude Opus 5.5, Claude Haiku 4.5 | $4 and $20, $1 and $5 per MTok, input and output | Reviewer re-fetch of the Anthropic pricing page |
| Bedrock fine-tuning table | Claude 3 Haiku still listed. Nova and Meta Llama models listed, 4.9 | Reviewer re-fetch |
| Grader tokens | "billed at that model's per-token rate" | same |
| OpenAI self-serve fine-tuning, last day for active customers | 2027-01-06 | `RD/oai_deprec.txt` |
| o4-mini and ft-o4-mini shutdown | 2026-10-23 | same |
| Claude 3 Haiku retired, Claude API | 2026-04-20 | `RD/anth_deprec.txt` |
| Claude 3 Haiku end of life, Bedrock | 2026-09-10 per the AWS blog notice | `RD/aws_haiku_ft.txt` |

### 5.7 Arithmetic recomputed

`D21/recompute.py` checks 56 values from both reports. All 56 agree after rounding. The items with a note:

- The underprediction factor is 1.106 ÷ 0.7706 = 1.435. The LoRA report rounded it to 1.43. That is fine.
- The 8B QLoRA projection is 7.64 × 1.4352 = 10.97 GB. With the rounded 1.435 it is 10.96. The LoRA report wrote "about 10.9". Use 11.0. Conflict c.
- The freshness toy's stale share at c = 0.2 is 0.693 by closed form and 0.696 by simulation. The simulation has sampling noise.
- `0.96 − 0.97` evaluates to `-0.010000000000000009` in Python. That is the float bug the gate lab caught at the threshold.
- QLoRA Figure 6: the three labelled bars sum to 5,046 + 1,152 + 288 = 6,486 MB. The axis label says 6.9 GB. Conflict c explains the rest.

---

## 6. Lab designs

The learner's machine: Apple Silicon Mac, arm64, 14 cores, about 24 to 26 GB, MPS, no Docker, no API keys. Every lab below runs on it unless marked optional.

### 6.1 Built and run on 2026-09-25

| Lab | Script | Saved output | Where it runs, and cost | Self-test | Proves |
|---|---|---|---|---|---|
| A. Decision calculator | `RD/proto/decide.py` | `run_default.txt`, `run_breakit.txt` | Laptop, standard library, 0.18 s user time. $0 | Hand-worked cost, break-even 4,296.3, freshness 0.855, Gekhman endpoints 44.2 and 28.6. Passes | 4.1, 4.2, 5.3 |
| B. Freshness toy, inside `decide.py` | same | same | same | Simulation within 0.01 of the closed form | 4.1 |
| C. Training-specific gate, inside `decide.py` | same | same | same | Covers the float case at the margin | 4.8 |
| 1. Memory calculator | `RL/proto/memcalc.py` | `memcalc_output.txt` | Laptop, standard library, under 1 s. $0 | 10 checks, all PASS: 5 parameter totals, the LoRA count, the adapter file size, 4.5-bit weights, ZeRO 16 bytes | 4.10, 4.11 |
| 2. Tiny QLoRA run with `mlx-lm` | `mlx_lm.lora` command in 5.5 | `lora_run1.txt`, `gen_base.txt`, `gen_after_run1.txt` | Laptop. 501 MB install, 289.6 MB model. 15.5 s. $0 | Trainable count must print 2.933M | 4.11, 4.12 |
| 3. Peak memory split | `RL/proto/peak_breakdown.py`, `peak_logits.py` | `peak_breakdown_output.txt`, `peak_logits_output.txt` | Laptop. About 10 s each. No new download | None | 4.12 |

What each prints and its break-it:

- **A.** A table of four options. The columns are upfront dollars, dollars per query, added latency and freshness in days. Then data needed, 12-month total and gate result. Default: the knowledge task picks prompt + retrieval at $72,500. The behaviour task picks LoRA at $3,936. Break-it `--break-it`: 2,000 labels and a 0.5-day freshness need. Fine-tuning and distillation still fail on staleness. More labels do not help.
- **B.** Accuracy of retrieval, fine-tuning and both. There are 2,000 facts. Each changes with probability c per day. Fine-tuning retrains every T days. At c = 0.01 and T = 30: retrieval 0.900, fine-tune 0.687, both 0.968. Fine-tuning gives a stale answer with no warning on 11.3% of questions. Break-it c = 0.2: fine-tune 0.105, stale on 69.6%. The recall 0.9 and learn rate 0.8 are assumptions. The toy has no model and no text.
- **C.** An eval item copied from training is caught by a 13-gram check. A paraphrased item is caught only by Jaccard ≥ 0.5. The three-suite gate prints SHIP, BLOCK for a capability drop of 0.09, and BLOCK when the safety suite did not run.
- **1.** Fit tables for 16, 32 and 64 GB. Break-it: set `targets="attn_qv"`, the PEFT default, and read 4.14. Second break-it: turn checkpointing off, and 8B QLoRA leaves the 16 GB column.
- **2.** Loss from 5.090 to 0.376 in 30 steps, peak 1.106 GB. Break-it, not run: `--learning-rate 1e-5`, the `mlx-lm` default. Expect a slower loss drop.
- **3.** Load, forward peak and forward-plus-backward peak. The learner compares each line to the calculator's items.

### 6.2 Designed, not built

| Lab | What it would print | Where and cost | Proves |
|---|---|---|---|
| 4. LR and rank sweep on the Lab 2 task | Final validation loss for 3 learning rates × 2 ranks, plus a `--fine-tune-type full` column | Laptop. About 6 × 15 s, inferred from Lab 2. Full fine-tuning needs `mlx-community/Qwen2.5-0.5B-Instruct-bf16`, 999.6 MB | 4.13, 4.14 |
| 5. Forgetting check | Score on a small held-out general set, such as 50 ARC-Easy items, before and after the adapter | Laptop. Eval data size not checked | 4.8, 4.13 |
| D. Fine-tune with and without retrieval on the shared harness | SciFact claims, four arms: base, base + BM25 top 3, LoRA, LoRA + BM25. Uses `retrieval-internals/code/` with MiniLM and BM25, and a Qwen2.5-0.5B reader | Laptop. Run time and download not measured. Inferred to fit, since 0.5B in bf16 is about 1 GB | 4.1, 4.3 |
| E. Teacher labels with a hosted model | 1,000 traces from a hosted teacher, then a local student | **Optional, UNVERIFIED.** $44 on Opus 5.5 or $11 on Haiku 4.5 at 2026-09-25 list prices. Needs a key | 4.6 |

### 6.3 The module lab, proposed

One run that answers both halves of the module question on the learner's Mac. Proposal, not built.

1. Take a behaviour task and a knowledge task from the Lab D setup. The behaviour task is a fixed answer format. The knowledge task is claims about facts in the SciFact corpus.
2. Freeze three eval splits first: target, held-out capability, and safety. Run the Lab C decontamination on every split.
3. Arms: prompt only, prompt + BM25 retrieval, QLoRA with `mlx-lm`, QLoRA + retrieval. Use `--num-layers -1` and a learning rate from Lab 4. Reviewer addition: a fifth arm, a larger off-the-shelf model with the same prompt, such as a 3B model in 4-bit. This tests gate step 8 in 4.8. Its download size and run time are not checked.
4. Print, per arm and per task: target score with the paired interval from Module 11, 6.2. Capability delta. Safety delta. Peak memory against the calculator's estimate.
5. The gate names the checkpoint and the base model version.
6. Break-its: train on the knowledge facts without retrieval and watch the knowledge score fall, as in 4.2. Drop the safety suite and watch the gate block. Keep the `mlx-lm` default learning rate and 16 layers.

Inferred: offline, no key, a few minutes on the laptop, about 1.3 GB of downloads. Not measured.

---

## 7. Conflicts resolved

| Conflict | Reports | Evidence used | Resolution |
|---|---|---|---|
| a. When Claude 3 Haiku ended: 2026-04-20 or 2026-09-10 | Decision report lists both, section 3 | `RD/anth_deprec.txt`: "This model was retired April 20, 2026", and "Partner-operated platforms (Amazon Bedrock and Google Cloud) set their own retirement schedules". `RD/aws_haiku_ft.txt` line 187: "Claude 3 Haiku reached end of life on September 10th, 2026". `RD/bedrock_custom-model-fine-tuning.html` still lists `anthropic.claude-3-haiku-20240307-v1:0:200k` | Both are true, on different platforms. **Retired on the Claude API on 2026-04-20.** End of life on Bedrock on 2026-09-10, per the AWS notice. Fine-tuning was a Bedrock feature. Inferred: the fine-tuning offer ended on 2026-09-10. The Bedrock docs table lags the notice. Reviewer re-fetch on 2026-09-25: the table still lists the model, and the AWS notice is unchanged. Check: the Bedrock console. The AWS notice says "Use Claude 3.5 Haiku instead". The Claude API retired 3.5 Haiku on 2026-02-19. Its Bedrock status and fine-tuning support are not checked |
| b. When hosted OpenAI fine-tuning ends: 2027-01-06 or earlier | Decision report 2.6 and section 3 | `RD/oai_deprec.txt` lines 147 to 157 and 160 to 190 | **2027-01-06 is the last day active customers can create jobs.** For o4-mini RFT the practical end is earlier. The base `o4-mini-2025-04-16` and `ft-o4-mini-2025-04-16` shut down on 2026-10-23. The saved RFT guide names only o4-mini. Inferred: after 2026-10-23, RFT has no documented base. The Agent RFT talk names GPT-5 bases, but the first-party Agent RFT page is a 404. Check: the RFT guide after 2026-10-23 |
| c. QLoRA Figure 6 total: 6.9 GB against 6,486 MB of labelled bars | LoRA report 2.2 | `RL/src/qlora_fig6_page.png`, read by the dossier author. The legend has five parts: Input gradient, Optimizer, Weight gradient, Adapters, Model. The Adapters segment and the Input gradient segment carry no number on the 7B bar | The LoRA report listed three bars and called the total 6.9 GB. The missing 0.4 GB is the two unlabelled segments. **Corrected.** The 5,046 MB model bar against 3.48 GB from 4.127 bits × 6.74B stays unexplained. Also corrected: the 8B projection is 10.97 GB, not 10.9 |
| d. The Mac memory budget: 75% of RAM | LoRA report 2.2 and `memcalc.py` line 118 | Measured 0.740 on one 24 GiB Mac. `memcalc.py` line 19 sets `GB = 1e9` and applies 75% to 16, 32 and 64 | Two effects in opposite directions. The measured fraction is 1.3% below 75%. The unit is 7.4% conservative, because a "16 GB" Mac has 16 × 2³⁰ bytes. Net, the budget column is about 6% conservative on a 16 GB Mac. It uses 12.0, and the real value is 16 × 2³⁰ × 0.740 = 12.71 × 10⁹ bytes. The 1.435 underprediction is much larger. Teach the table as a lower bound on need, and the budget as slightly low |
| e. The GPU price in the decision calculator | Decision report: $2 per GPU hour, DeepSeek's H800 assumption | Module 13 dossier 5.1, read 2026-09-25: H100 on-demand $3.49 to $6.88 per GPU hour | $2 is below every H100 price read that day. Re-priced in 5.3. Break-even moves from 4,296 to between 5,069 and 6,827 queries. The option ranking does not change. Replace the constant with a quoted price in the course |
| f. DeepSWE on SWE-Bench Verified: 42.2 or 36.4 | Decision report 2.5 used 42.2 | `RD/skyrl_agent.txt` lines 735 to 781. Columns: Simple ReAct, Reported, Cost. DeepSWE 36.4 and 42.2. SA-SWE-32B 39.4 and a dash. Qwen3-Coder-30B 45.0 and a dash | 42.2 is DeepSWE's own reported score in its own harness. 36.4 is the same harness as the other rows. Compare 45.0, 39.4 and 36.4. The lesson in 4.7 gets stronger: the off-the-shelf Qwen3-Coder-30B, which the user did not train, beats both RL runs by 5.6 and 8.6 points. Reviewer wording fix: it is not an "untrained" model, since its vendor trained it. Link Module 12, 3.3 for the harness point |
| g. Does LoRA equal full fine-tuning? | LoRA report 8.1 | Biderman: HumanEval and GSM8K, 100M-token IFT and 20B-token CPT. Thinking Machines: training log loss, small-to-medium SFT | Not a real conflict. They agree on CPT: LoRA falls behind. They agree on IFT with enough rank and all layers. The scorer differs: sampled benchmark against log loss. Teach the four conditions in 4.13 |
| h. Can SFT inject knowledge? | Decision report 4 | Mecklenburg: SFT on QA pairs with even coverage of facts, into GPT-4. Ovadia: CPT on raw 256-token chunks. Soudani: SFT on synthetic QA, 12 models from 80M to 11B | The method splits the result. QA-format supervision plus repetition works better than raw-chunk CPT. Inferred from the setups. No study tests CPT, QA-SFT and paraphrase density on one model against RAG. Gap 9 |
| i. FT + RAG against RAG alone | Ovadia against Soudani | Ovadia Table 2: FT-par + RAG 0.830 below RAG 0.875. Soudani: fine-tuned plus RAG beat or tied vanilla plus RAG "in all but one case" | Different fine-tuning. Ovadia used CPT. Soudani used SFT on QA. Teach "FT + RAG is not always best" with both numbers |
| j. Is LoRA faster? | LoRA report 4 | Biderman 4.7: slower in wall clock at a fixed batch size. Thinking Machines: about ⅔ of the FLOPs per pass | Different measures. Wall clock in standard implementations against a FLOP count. Report both |
| k. RL forgets less, or RL narrows ability? | Decision report 8 | RL's Razor abstract. Yue et al. abstract | Different measures. Forgetting on old tasks against pass@k at large k on the trained task. Both can hold. No paper here measures both on one agent task |
| l. Unsloth latest version | Curriculum audit: 2026.9.10 on 2026-09-22. LoRA report: 2026.9.11 | `RL/src/pypi_unsloth.json`: 2026.9.10 uploaded 2026-09-22T23:12, 2026.9.11 uploaded 2026-09-23T14:51 | Both are true. A new release came out between the audit and the report. Pin 2026.9.11 |
| m. LoRA parameter count on Llama-3.1-8B, r=256 all layers | LoRA report 8.3 | Thinking Machines table: 0.70B. The formula: 41.94M at r=16, × 16 = 0.671B. Recomputed | Not reconciled. The blog does not say what else it counts. Use the formula, which matches the measured run exactly at 0.5B |

---

## 8. Gap list, ranked by what the module question needs

| Rank | Gap | Why the module question needs it | What was done |
|---|---|---|---|
| 1 | The module lab: four arms, three suites, on the learner's Mac | "How do you know it worked" needs one run that gates a real adapter against retrieval | Not built. Design in 6.3 |
| 2 | A fine-tune can break tool-call formatting | The curriculum audit named it as a candidate concept. An agent's gate must test it. No source was found | Not checked. Add a tool-call format suite to the gate lab |
| 3 | Forgetting on the learner's own adapter | The capability suite in 4.8 has no local measurement | Not run. Lab 5 |
| 4 | Calculator accuracy above 0.5B | "What fits" rests on a factor measured at 0.5B only | Not run. Check: 8B QLoRA with `--grad-checkpoint`, batch 1, sequence 2048, on a 32 GB Mac |
| 5 | LR and rank sweep, and the `mlx-lm` scale against PEFT alpha | The default-settings trap in 4.14 is inferred for `mlx-lm` | Not run. Lab 4 |
| 6 | Which hosted fine-tuning offers remain | 4.9 closes OpenAI and Claude. The learner needs the remaining hosted options, or a clear "self-host" answer | Partly closed by the reviewer: Bedrock's table on 2026-09-25 lists Nova and Meta Llama models, 4.9. Also open: OpenAI SFT on `gpt-4.1` and `gpt-4.1-mini` has no listed price. Check: Google Vertex and open-weight hosts, with dates and prices |
| 7 | LoRA and the unknown-fact harm | 4.2 is for full fine-tuning. The Mac path is LoRA | Open in the literature. Lab D could measure it at small scale |
| 8 | Terms of service on training with another model's outputs | The distill branch in 4.6 may not be allowed for a given teacher | Not checked. Read each provider's usage terms |
| 9 | One study of CPT, QA-SFT and paraphrase density on one model against RAG | Conflict h is resolved by inference only | None found |
| 10 | Open agent RL on a laptop: GRPO in TRL, or MLX | 4.7 has only cluster-scale costs. The audit asked for GRPO in TRL | Not checked |
| 11 | Training-data poisoning | Module 16 covers documents and memory, not training data | Not owned by any module. Decide with the learner |
| 12 | Independent small-model benchmarks | 4.15 has vendor numbers only | None found |
| 13 | `bitsandbytes` QLoRA on MPS with PEFT and TRL | A second Mac path. The README claim is not run | Not run. Check: a 20-step run with `torch` 2.14.0 |
| 14 | Whether MLX fine-tuning moved to another package | The audit asked. `mlx-lm` has had no release since 2026-04-22 | Not checked. The GitHub API was rate limited |

---

## 9. Things not verified

Each item has the check that would settle it.

**Decision report.**

1. Venues for Ovadia, Gekhman, RAFT and EntiGraph. Check: ACL Anthology, OpenReview or the COLM proceedings.
2. RL's Razor numeric results. Check: sections 3 and 4 of `RD/rlrazor.txt`.
3. Yue et al. crossover k per model. Check: the figures in `RD/yue_rl.txt`.
4. Nebius GPU hours. Check: grep `RD/swe_rl_nebius.txt` for training duration.
5. The training cost of the DeepSeek-R1-Distill students. Not stated in the paper as read.
6. Whether Anthropic offers any fine-tuning after 2026-09-10. The Bedrock docs table on 2026-09-25 still lists Claude 3 Haiku, per the reviewer's re-fetch. Check: the Bedrock console model access list.
7. OpenAI Agent RFT first-party docs and availability after the wind-down. The URL returns 404. Check: the OpenAI changelog.
8. The customer numbers on vendor pages: Haiku moderation, Harvey, Runloop, Accordance, Cognition, Ambience. Only that the pages say them is verified.
9. Which benchmark gave Distilling Step-by-Step's "80% of available data". Check: section 4 of `RD/stepbystep.txt`.
10. The calculator's self-host cost of $0.0008 per query, 150 ms retrieval latency, 8 GPU hours for LoRA and $2,000 for labelling. All are ASSUMPTIONS in `decide.py`.
11. Balaguer's 68% against 76%. Closed by the reviewer: the paper fine-tuned the base Llama2-13B, and no fine-tuned chat model is in Table 18.
12. s1 affiliations, Chu et al. affiliations, Betley et al. affiliations.

**LoRA report.**

13. The 75% budget on 16, 32 and 64 GB Macs. Measured 74.0% on one 24 GiB M4 Pro. Check: `mx.device_info()` on each size.
14. Unsloth training on a Mac. Check: install Unsloth Studio and run one job.
15. The logits memory per element in MLX, taken as 6 bytes. Check: peak memory of loss plus gradient while varying the vocabulary size.
16. Whether Gemma 4 E2B and E4B ran with thinking on in the benchmark table. Check: arXiv 2607.02770, not fetched.
17. The venue of the Illusion of Equivalence paper and of LoRA at ICLR 2022.
18. Biderman Appendix I, throughput and peak memory tables. Only the section 4.7 sentence was read.
19. The Unsloth PR #10403 merge date.
20. Other processes during the Lab 2 run. One run, no repeats, no variance.
21. Whether MLX keeps activations for frozen layers below the first LoRA layer. Check: a per-array memory trace.
22. The QLoRA 7B model bar of 5,046 MB against 3.48 GB by formula.

**This dossier.**

23. Conflict b's inference that RFT has no documented base after 2026-10-23. Check: the RFT guide after that date.
24. The Bedrock status of Claude 3.5 Haiku, which the AWS notice recommends. Check: the Bedrock model lifecycle page.
25. The module lab in 6.3 run time and download size. Not measured.
26. Anchors cover the best evidence and the numbers used in 5. Supporting facts marked "per the decision report" or "per the LoRA report" were not re-grepped.
27. The curriculum audit's "Module 13 owns serving adapters". Module 13 dossier 4.14 mentions loaded adapters in routing only. Serving many adapters is in Module 1, 6.2. The overlap table in section 2 follows the built heading.

---

## 10. Review log

Reviewer: independent, did not write the dossier. Date: 2026-09-25. Read-only checks, fetches and CPU-only self-tests. No LoRA training ran. Reviewer files are in `/private/tmp/claude-502/-Users-raghvendra-dhakar-Desktop-project-code/dabd56e3-78f3-4dbc-bddb-3316bb9bedda/scratchpad/m21rev/`, called `m21rev/` below.

### 10.1 What was checked

| Check | Result | Evidence |
|---|---|---|
| Anchors against saved sources | About 90 anchors checked by the reviewer's own grep, not by `D21/anchor_check.py`. The counts per source are hand counts. All checked anchors are present. Sources: Ovadia 13, Soudani 5, RAFT 9, Balaguer 6, Gekhman 7, LIMA 2, s1 6, DeepSeek-R1 9, SkyRL 5, Search-R1 5, Qi 6, Betley 3, Yang 1, Biderman 9, Thinking Machines 9, RL's Razor 2, OpenAI SFT, best-practices, RFT and use-case pages 9, InfoQ 2, Anthropic Haiku page 1, AWS blog 3, Mecklenburg 1. Three of them changed the text: RAFT, Soudani and Balaguer, see 10.2 | `RD/*.txt`, `RL/src/*.txt`. Note: plain `grep` returns nothing on `RL/src/biderman_lora_learns_less.txt`. Use `grep -a` |
| Vendor pages re-fetched on 2026-09-25, 05:27 local time | 9 URLs, all HTTP 200. OpenAI pricing, deprecations, SFT and RFT pages. Anthropic deprecations and pricing. AWS blog. Bedrock fine-tuning and lifecycle pages. Every saved price and date matched | `m21rev/*.txt` |
| `memcalc.py` rerun | All 10 self-tests PASS. Output byte-identical to `RL/proto/memcalc_output.txt` | `m21rev/memcalc_mine.txt` |
| `decide.py` rerun, default and `--break-it` | Self-test passes. Both outputs byte-identical to the saved files | `m21rev/decide_mine.txt`, `m21rev/decide_bi.txt` |
| LoRA run 1 | Model `mlx-community/Qwen2.5-0.5B-Instruct-4bit`. 30 iterations, batch 4, learning rate 1e-4. 2.933M trainable. Peak 1.106 GB. 15.479 s total. It/s 9.640 to 9.723 from step 10 to 30. Val loss 5.090 to 0.376. Adapter file 11,754,630 bytes. `adapter_config.json`: rank 8, scale 20.0, 16 layers, `grad_checkpoint` false. All match 5.5 | `RL/proto/lora_run1.txt`, `RL/proto/adapters_run1/` |
| Cost arithmetic | Teacher $44, upfront $58, $68.43 and $92.16, saving $0.0135, break-even 4,296, 5,069 and 6,827. 12-month totals $43,200, $72,500, $3,936 and $10,858. Lab E $44 and $11. All agree. One sentence was wrong, see 10.2 | Hand arithmetic in 5.3 |
| QLoRA Figure 6 | The page image shows five legend parts and labels 5046, 1152 and 288 on the 7B bar. Conflict c stands | `RL/src/qlora_fig6_page.png` |
| Module 13 GPU prices | $6.88 and $3.49 are in the Module 13 dossier, lines 393 and 399 | `_curriculum/module-13-serving-cluster.md` |
| Overlap | `grep '^## '` over `eval-engineering`, `agent-evals` and `inference-internals`. No built phase teaches fine-tuning or LoRA. Module 1 S-LoRA, cascade and self-host claims found at the named sections. The dossier links Module 11 and 12 and does not re-teach gate statistics | Headings output in the reviewer session |

### 10.2 Corrections made in the text

| # | Kind | Where | Was | Now | Evidence |
|---|---|---|---|---|---|
| 1 | Wrong count, serious | 4.3, 4.8 step 4 | Domain SFT + RAG below domain SFT "on 2 of 5 sets" | 4 of 5 sets. Only PubMed rose | `RD/raft.txt` lines 252 to 290: HuggingFace 42.59 against 61.06, Torch Hub 82.80 against 84.94 were missed |
| 2 | Overstated claim, serious | Section 1 table, 4.9, gap 6 | "Hosted fine-tuning is closing" | OpenAI and Claude fine-tuning are closing. Bedrock lists Nova and Meta Llama fine-tuning on 2026-09-25 | Bedrock fine-tuning page, reviewer re-fetch |
| 3 | Overstated claim | Section 1 table | "LoRA and QLoRA up to 8B fit with checkpointing" | Depends on RAM. 8B LoRA bf16 needs 19.19 GB, which misses 16 GB and the learner's 19.07 GB budget | `memcalc_output.txt`, 4.12 budget |
| 4 | Arithmetic | 5.3 | "every row pays back in under 3% of one month" | Under 4%. The $6.88 row is 3.4% | 6,827 ÷ 200,000 = 0.0341 |
| 5 | Arithmetic display | 4.12, 5.7 | 7.64 × 1.435 = 10.97 | 7.64 × 1.4352 = 10.97. With 1.435 it is 10.96 | Python |
| 6 | Scope of a claim | 4.10 | Full fine-tuning above 1.5B "out of reach" on a Mac | Out of reach on 16 or 32 GB. 64 GB fits 3B with bf16 Adam state, 27.09 GB | `memcalc_output.txt` |
| 7 | Missing condition | 4.1, 5.1 | Soudani "SFT on synthetic QA" | PEFT SFT, per the Table 3 caption | `RD/soudani.txt` line 698 |
| 8 | Missing value | 5.1 | Llama2 7B FT + RAG "not copied" | 0.326 | `RD/ovadia.txt` Table 2 |
| 9 | Added evidence | 4.1 | Mistral only | FT-par + RAG is below RAG for all three Ovadia models | `RD/ovadia.txt` Table 2 |
| 10 | Label upgrade | 5.1, 9 item 11 | Balaguer base checkpoints "Inferred" | Verified. The paper fine-tuned base Llama2-13B. Intervals added: GPT-4 75% ± 3% and 81% ± 5% overlap | `RD/balaguer.txt` section 5.3 and Table 18 |
| 11 | Missing conditions and label | 4.8 | Qi et al. with no scorer | 330 instructions, GPT-4 judge, rate = share scored 5. Saved copy is a v1 preprint | `RD/qi_safety.txt` lines 293 to 308, 59 |
| 12 | Wording | Conflict f | "the untrained model" | The off-the-shelf Qwen3-Coder-30B, which the user did not train | `RD/skyrl_agent.txt` cost table |
| 13 | Label | Conflict a | "so the fine-tuning offer ended on 2026-09-10" as fact | Marked inferred. The Bedrock table still lists the model on 2026-09-25 | Reviewer re-fetch |
| 14 | Dates on vendor claims | 4.7, 5.6 | Prices without a read time | Read time and re-fetch result added. Data-sharing prices added. Only o4-mini has a fine-tuning price | OpenAI pricing page, reviewer re-fetch |
| 15 | New vendor finding | 4.9 | Not present | The OpenAI SFT guide still lists `gpt-4.1` and `gpt-4.1-mini` SFT bases, with no price on the pricing page | OpenAI SFT guide and pricing page, reviewer re-fetch |
| 16 | Wrong column | 5.1, RAFT row | Base 0.03, RAG "not copied" | Base 0.54, RAG 0.03. The 0.03 is the LLaMA2-7B + RAG value | `RD/raft.txt` Table 1: "LLaMA2-7B 56.5 0.54" and "LLaMA2-7B + RAG 58.8 0.03" |

### 10.3 Concepts added for the module question

| Concept | Why the question needs it | Evidence and label |
|---|---|---|
| Error analysis decides between retrieval and fine-tuning | "Is fine-tuning next?" needs the failures sorted into facts and behaviour first | Link Module 11, 1.1 and 1.2. Inferred from 4.1 to 4.3. Added to 4.1 and the overlap table |
| A stronger off-the-shelf model is a required baseline arm | "Did it work?" must beat the next model you could buy, not only the base | Inferred from SkyRL, 4.7. Gate step 8 and a fifth arm in 6.3 |
| Base against adapter is a paired comparison | The eval set size for "did it work" | Link Module 11, 5.3. Gate step 9 |
| Harness and provider change the score | Record the harness with the base model version | Link Module 12, 3.3 and 5.4 |
| What fits on the learner's 24 GiB Mac | "Where does it run" had no row for the learner's machine | Arithmetic on `memcalc_output.txt` and the measured budget, table in 5.4 |

### 10.4 Not changed, and still open

- The author's claim "80 of 80 anchors match" was not rerun. The reviewer's own greps, about 90, agree with it.
- Gap 2, tool-call format breakage after fine-tuning. The reviewer found no source in the saved files. It stays a gap.
- The 1.4352 factor above 0.5B. Gap 4 stays open. The 14B QLoRA row on the learner's Mac is 0.9 GB under budget and must not be promised.
- OpenAI SFT prices for `gpt-4.1` and `gpt-4.1-mini`. Not found on the pricing page. Not checked further.

### 10.5 Coherence pass, 2026-09-25

The module coherence reviewer made these changes after the four phases were written. The reviewer read each source again before the change.

| # | Kind | Where | Was | Now | Evidence |
|---|---|---|---|---|---|
| 17 | Wrong affiliation | 3.2 source table and 4.8, Yang et al. | "UC Berkeley and LMSYS" | "UC Berkeley and Shanghai Jiao Tong University". The phases already used the right names | `RD/rephrased.txt` line 39: "1UC Berkeley 2Shanghai Jiao Tong Univer-" |
| 18 | Overstated title, not changed here | 4.14 title | "settings that the papers say are worst" | The phases use "settings the papers did not use". Biderman Figure 7 ranks only the choices it tested. The title above is kept as the research record | Phase 3 fact-check report |
| 19 | Tense after a date passed | 4.9 | "Claude fine-tuning is closing" | The phases say Claude fine-tuning has closed. The AWS notice says Claude 3 Haiku "reached end of life on September 10th, 2026". That the training offer ended is still inferred, because the Bedrock table lists the model | `RD/aws_haiku_ft.txt` line 187 |
| 20 | Checked value | 5.3 GPU rows | Sourced to the Module 13 dossier | Re-read from the providers on 2026-09-25: RunPod Secure Cloud H100 SXM $3.49 per hour, AWS p5.48xlarge US East Linux $55.04 per hour. The phases cite the provider URLs | runpod.io/pricing page JSON, AWS on-demand price file for US East (N. Virginia) Linux |

Summary: two claims the module question depends on were wrong or overstated. RAFT's retrieval harm is 4 of 5 sets, not 2 of 5. Hosted fine-tuning still exists on Bedrock for Nova and Llama. Every other checked number held.

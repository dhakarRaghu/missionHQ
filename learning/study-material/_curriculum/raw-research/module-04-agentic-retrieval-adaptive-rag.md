<!-- Raw research-helper report, saved 2026-09-17. Not reviewed. Use as input to the module dossier; re-verify before quoting. -->

# Research dossier: Module 4, cluster A. Agentic retrieval and adaptive retrieval routing

**Short answer:** The sources agree on three points.
- Agentic or iterative retrieval gives clear gains on multi-hop questions and hard browsing tasks.
- On simple single-hop questions, it often costs 2 to 10 times more for the same accuracy, or for lower accuracy.
- Simple uncertainty-based routing matches complex adaptive methods at a small part of the cost.

**How I checked:**
- I fetched every source with curl and recorded the HTTP status.
- For arXiv, I extracted PDF text with pypdf. All numbers below come from grep on that raw text or on raw HTML.
- All files are in `/private/tmp/claude-502/-Users-raghvendra-dhakar-Desktop-project-code/5ac29535-dfed-40f4-b977-06676a73b60b/scratchpad/clusterA/`.
- "Verified" means I found the number in the raw text of that file.

---

## 1. Search-R1 and its follow-ups

### 1.1 Search-R1
- **Source:** "Search-R1: Training LLMs to Reason and Leverage Search Engines with RL". Jin, Zeng, Yue, Yoon, Arık, Wang, Zamani, Han. UIUC, UMass, Google Cloud AI Research. COLM 2025.
- **URL:** https://arxiv.org/abs/2503.09516. PDF status 200. Abstract page status 200.
- **Why use it:** It is the reference open recipe for training a model with RL to call search. RL means reinforcement learning. The code is public and widely reused.
- **Versions (verified, abs page):** v1 12 Mar 2025, v2 19 Mar 2025, v3 8 Apr 2025, v4 21 Jul 2025, v5 5 Aug 2025.

**Mechanism (verified, sections 3.1, 3.3, 3.4, Algorithm 1):**
- The model writes `<search>` tags. The system places the results inside `<information>` tags. The model can repeat this until an action budget B runs out.
- The reward is only final-answer exact match: "rϕ(x, y) = EM(apred, agold)". The paper says it uses no format reward.
- **Retrieved-token loss masking:** retrieved tokens are excluded from the policy loss and from the KL loss.

**Code (verified):**
- The repo has no release tags. The GitHub API returned an empty tag and release list, so I pinned commit `598e61bd1d`, dated 2025-11-13.
- `search_r1/llm_agent/generation.py:120-134` builds `info_mask`, which covers the information block.
- `verl/trainer/ppo/ray_trainer.py:818-819` calls `_create_loss_mask` when `state_masking` is on.
- `ray_trainer.py:859` sets `loss_mask = batch.batch['info_mask'][:, -response_length:]`.

**Repo state (verified with `gh api`):**
- 5,430 stars. Apache-2.0 licence. Last push 2025-11-13.
- The README news items for 2025 say:
  - 2025.6: the method is integrated into veRL.
  - 2025.7: it is supported in SkyRL.
  - 2025.10: it is featured in Thinking Machines "Tinker".
- The latest commits only add links to other projects to the README.
- Inferred: the core code is in maintenance mode.

**Setup (verified, section 4.3):**
- Models: Qwen2.5-3B and 7B, base and instruct.
- Corpus: the 2018 Wikipedia dump. Retriever: E5, top-3 passages.
- Training data: NQ and HotpotQA merged. PPO by default.
- Scorer: exact match (EM).

**Table 2 results, EM average over 7 datasets (verified):**

| Qwen2.5 | RAG | IRCoT | Search-o1 | Rejection sampling | Search-R1 base | Search-R1 instruct |
|---|---|---|---|---|---|---|
| 7B | 0.304 | 0.239 | 0.206 | 0.348 | **0.431** | 0.385 |
| 3B | 0.270 | 0.181 | 0.255 | 0.265 | 0.303 | **0.325** |

**The headline gain changes with the baseline.**
- Verified: the abstract and section 4.4 say "24% (Qwen2.5-7B) and 20% (Qwen2.5-3B)". The contributions list, around line 99, says "41% and 20% over RAG baselines".
- Inferred from my own arithmetic:
  - 0.431/0.304 = +41.8%, which is the gain over plain RAG.
  - 0.431/0.348 = +23.9%, which is the gain over rejection sampling.
  - 0.325/0.270 = +20.4%, which is the 3B gain over RAG.
- So "24%" is measured against the strongest baseline, and "41%" is measured against RAG.

**Other tables (verified):**
- **14B, Table 5:** Search-R1-base averages 0.479. The best baseline is R1-base at 0.357.
- **Masking ablation, Table 4:** 7B base with PPO scores 0.431 with the mask and 0.343 without it.
- **PPO vs GRPO, Table 3:** GRPO is better for 3B base, 0.312 vs 0.303. PPO is better for 7B base, 0.431 vs 0.395.

**Where the result does NOT hold (verified, Table 2, 3B base):**
- Bamboogle: Search-R1-base 0.088. Search-o1 0.320. IRCoT 0.240.
- MuSiQue: Search-R1-base 0.049. IRCoT 0.067.
- Smaller RL-trained agents can lose to prompted multi-step methods on out-of-domain multi-hop sets.

### 1.2 Companion empirical study
- **Source:** "An Empirical Study on RL for Reasoning-Search Interleaved LLM Agents". Jin, Yoon, Kargupta, Arık, Han. UIUC and Google.
- **URL:** https://arxiv.org/pdf/2505.15117. Status 200. Version v1, 21 May 2025.

**Findings (verified, intro list):**
- A format reward "significantly improves performance", mostly for base models. This conflicts with the first paper, which used no format reward. Report both.
- Intermediate retrieval rewards give no consistent gain.
- A weak engine such as BM25 leads to "frequent but less efficient search calls". A random-noise engine makes the agent stop retrieving.
- I did not pull numeric tables from this paper. Status: not checked.

### 1.3 ZeroSearch
- **Source:** "ZeroSearch: Incentivize the Search Capability of LLMs without Searching". Sun et al., Tongyi Lab, Alibaba.
- **URL:** https://arxiv.org/abs/2505.04588. Status 200. Versions v1 7 May 2025, v2 16 May 2025, v3 19 May 2026.
- **Why use it:** It has the only hard dollar figure I found for the cost of RL training against a search API.
- **Scorer:** EM.

**Table 8, training cost (verified):**
- Conditions: batch 64, 5 rollouts, 200 steps, Qwen-2.5-7B, about 64,000 search requests, about 12 hours.
- Google through SerpAPI: API cost $586.7.
- A simulated SFT-14B search LLM on 4 × A100: GPU cost $70.8.
- SFT-7B on 2 × A100: $35.4.
- SFT-3B on 1 × A100: $17.7.

**Table 4, policy Qwen-2.5-3B-Base, EM average over 7 datasets (verified):**
- Google search: 32.81.
- SFT-7B simulator: 33.53.
- SFT-14B simulator: 34.47.
- Prompted 3B simulator: 29.44.
- No RL: 8.82.

**Table 7:** The masking ablation is confirmed in the text, where removing document-token masking gives a "significant decline". I did not extract the numbers. Status: not checked.

### 1.4 R1-Searcher
- **Source:** Song, Jiang et al., Renmin University GSAI, with Lei Fang of DataCanvas.
- **URL:** https://arxiv.org/abs/2503.05592. Status 200. Versions v1 7 Mar 2025, v2 18 Mar 2025.

**Findings (verified, intro):**
- Two-stage outcome-based RL, based on Reinforce++, with a retrieval mask in the loss.
- Stage 1 gives a retrieval reward of 0.5 if the model makes at least one search call.
- With Qwen-2.5-7B-Base, it beats ReARTeR, which uses GPT-4o-mini, by "up to 48.22% on HotpotQA and 21.72% on 2Wiki".
- It improves on Search-o1-32B by "11.4%" on Bamboogle with online search.
- Scorer: an LLM-as-judge. Section 3 line 298 says "according to the LLM-as-Judge metric".
- I did not extract the absolute values from Table 2. Status: not checked.

---

## 2. Deep-research systems

### 2.1 Anthropic's multi-agent research system
- **Source:** "How we built our multi-agent research system". Anthropic Engineering. "Published Jun 13, 2025" (verified).
- **URL:** https://www.anthropic.com/engineering/multi-agent-research-system. Status 200.
- **Why use it:** It is the only vendor post that gives token-cost multipliers and a variance breakdown.

**Every requested number, found in raw HTML (verified):**
- "agents typically use about 4× more tokens than chat interactions, and multi-agent systems use about 15× more tokens than chats."
- The multi-agent setup uses Opus 4 as lead and Sonnet 4 as subagents. It "outperformed single-agent Claude Opus 4 by 90.2% on our internal research eval". Conditions: an internal eval, not public. The scorer is not stated.
- "three factors explained 95% of the performance variance in the BrowseComp evaluation". Also: "token usage by itself explains 80% of the variance". The other two factors are the number of tool calls and the model choice.
- Upgrading to Sonnet 4 "is a larger performance gain than doubling the token budget on Claude Sonnet 3.7".
- Parallel subagents, 3 to 5 of them, each using 3 or more tools in parallel, "cut research time by up to 90% for complex queries".

**Failure cases and cost controls (verified):**
- Early agents made "errors like spawning 50 subagents for simple queries".
- The effort-scaling rule in the prompt: "Simple fact-finding requires just 1 agent with 3-10 tool calls". Comparisons use 2 to 4 subagents with 10 to 15 calls each. Complex research uses more than 10 subagents.
- The post says the approach fits tasks with heavy parallel work. It says "most coding tasks" are a poor fit.

**2026 update (verified):** The Claude Opus 4.6 page, https://www.anthropic.com/news/claude-opus-4-6, status 200, is dated Feb 5, 2026.
- BrowseComp footnote conditions: "web search, web fetch, programmatic tool calling, context compaction triggered at 50k tokens up to 10M total tokens, max reasoning effort".
- "Adding a multi-agent harness increased scores to 86.8%."
- The single-agent Opus 4.6 BrowseComp score seems to be in an image. I did not find it in the text. Status: not checked.

**Opus 4.5 page (verified):** Nov 24, 2025, status 200. On "A fetch-enabled version of BrowseComp-Plus", the score went "from 70.48% without using the combination of techniques to 85.30%".

### 2.2 OpenAI deep research
- **Source:** "Introducing deep research". OpenAI, February 2, 2025.
- **URL:** https://openai.com/index/introducing-deep-research/.
- **Status:** curl returned 403. The page loaded in the browser pane, and I read the text there. I did not record the browser's HTTP status.

**Findings (verified, page text):**
- Humanity's Last Exam: "26.6% accuracy".
- "Deep research may take anywhere from 5 to 30 minutes".
- "very compute intensive".
- An April 24, 2025 update added a "lightweight version ... powered by a version of o4-mini".
- A "February 10, 2026 update" added connections to any MCP server or app, restriction of search to trusted sites, and real-time interruption.

### 2.3 BrowseComp
- **Source:** "BrowseComp: A Simple Yet Challenging Benchmark for Browsing Agents". Wei, Sun, Papay, McKinney, Han, Fulford, Chung, and others. OpenAI.
- **URL:** https://arxiv.org/abs/2504.12516. Status 200. The PDF header shows v1, 16 Apr 2025.
- **Size:** 1,266 questions. The scorer is an LLM grader. The prompt is in Appendix B.

**Table 3, accuracy % and calibration error % (verified):**

| Model | Accuracy % | Calibration error % |
|---|---|---|
| GPT-4o | 0.6 | 69 |
| GPT-4o with browsing | 1.9 | 82 |
| GPT-4.5 | 0.9 | 68 |
| o1, no browsing | 9.9 | 65 |
| Deep Research | 51.5 | 91 |

Caveats:
- Footnote 1 says Deep Research "is trained on data that specifically teach the model to be good at BrowsingComp tasks".
- Browsing alone adds only 1.3 points. A reasoning model with no browsing beats GPT-4o with browsing.

**Other findings (verified):**
- **Table 2, human trainers:** 29.2% solved, which is 367 of 1,255. 70.8% gave up after 2 hours.
- **Section 4.4:** 64 samples plus voting improve accuracy by "15% to 25%". Best-of-N is the best voting method.
- **Section 4.5:** Deep Research solved 16% of tasks on every attempt and failed 14% on every attempt, over 64 trials.

### 2.4 BrowseComp-Plus
- **Source:** Chen, Ma, Zhuang et al. University of Waterloo and others. The GitHub repo says "ACL 2026 Main".
- **URLs:** https://arxiv.org/abs/2508.06600, status 200, v1 8 Aug 2025. Repo: https://github.com/texttron/BrowseComp-Plus. I saw the repo only in search results and did not fetch it.
- **Why use it:** It uses a fixed corpus of 100,195 documents and 830 queries. That separates the effect of the retriever from the effect of the agent.
- **Conditions:** top-5 results, each cut to 512 tokens. The judge is gpt-4.1.

**Table 1, accuracy and search calls per query (verified):**

| LLM | Accuracy with BM25 | Accuracy with Qwen3-Embed-8B | Search calls, BM25 → Qwen3-Embed-8B |
|---|---|---|---|
| gpt-5 | 55.90% | 70.12% | 23.23 → 21.74 |
| o3 | 49.28% | 63.49% | 25.93 → 23.97 |
| Opus 4 | 15.54% | 36.14% | not extracted |
| Sonnet 4 | 14.34% | 36.75% | not extracted |
| gpt-4.1 | 14.58% | 35.42% | 10.35 → 8.67 |
| Qwen3-32B | 3.49% | 10.36% | about 0.9 |
| SearchR1-32B | 3.86% | 10.36% | about 1.7 |

- A better retriever raises accuracy and lowers the number of search calls.
- Open models make fewer than 2 calls "despite being explicitly prompted".

**Table 8, total API cost for the run (verified):**

| LLM | BM25 | Qwen3-Embed-8B |
|---|---|---|
| Opus 4 | $2,043.95 | $1,842.48 |
| o3 | $836.35 | $740.79 |
| GPT-5 | $400.36 | $360.71 |
| gpt-4.1 | $106.96 | $89.81 |

---

## 3. When iterative retrieval beats single-shot retrieval, and what it costs

### 3.1 IRCoT
- **Source:** Trivedi, Balasubramanian, Khot, Sabharwal. Stony Brook University and AI2. ACL 2023.
- **URL:** https://arxiv.org/abs/2212.10509. Status 200. v2, 23 Jun 2023.

**Findings (verified):**
- **Abstract:** with GPT3, "up to 21 points" in retrieval recall and "up to 15 points" in QA.
- **Table 4, answer F1:**
  - HotpotQA with GPT3 and a CoT reader: IRCoT 60.7, one-step retrieval 53.6, no retrieval 47.5.
  - Flan-T5-XXL with a direct reader: IRCoT 59.1, one-step retrieval 49.7.
- **Cost, from the Limitations section:** "IRCoT makes a separate call to an (L)LM for each sentence of CoT". code-davinci-002 is deprecated, so the GPT3 runs cannot be reproduced.

### 3.2 FLARE
- **Source:** Jiang, Xu, Gao, Sun, Liu, Dwivedi-Yu, Yang, Callan, Neubig. CMU and Meta. EMNLP 2023.
- **URL:** https://arxiv.org/abs/2305.06983. Status 200. Model: text-davinci-003.

**Findings (verified):**
- **Table 1, 2WikiMultihopQA, EM:**
  - No retrieval 28.2.
  - Single-time retrieval 39.4.
  - Question decomposition 47.8.
  - FLARE-direct 51.0.
- **Where it does not hold, Table 2, StrategyQA EM:** single-time retrieval 68.6 is *below* no retrieval at 72.9.
- **Section 6.2:** on StrategyQA, "performance drops when the retrieval percentage exceeds 50%".
- **Appendix A:** retrieval fires for 30% to 60% of sentences. A naive implementation "increases overheads".

### 3.3 Adaptive-RAG timing tables
See section 4.2 below.

**Per-dataset results, Table 2, FLAN-T5-XL 3B, EM, time relative to single-step (verified):**

| Dataset | Single-step EM | Multi-step EM | Multi-step time |
|---|---|---|---|
| NQ | 37.80 | 38.60 | 10.18× |
| TriviaQA | 53.60 | 53.80 | 9.22× |
| SQuAD | 27.80 | 24.40, lower | 9.03× |
| HotpotQA | 34.40 | 44.60 | 9.38× |
| MuSiQue | 13.80 | 23.00 | 7.58× |

- On single-hop data, multi-step costs about 10 times more for no gain.

### 3.4 "Is Agentic RAG worth it?"
- **Source:** Ferrazzi, Cvjeticanin, Piraccini, Giannuzzi. FBK, University of Padova, Cargill, Alkemy, Komebi. ACL 2026 Industry Track.
- **URL:** https://arxiv.org/abs/2601.07711. Status 200. v1 12 Jan 2026, v2 20 Apr 2026.
- **Setup:** "Enhanced" RAG is a fixed pipeline. "Agentic" RAG uses the PocketFlow framework, with at most 3 turns.
- **Models:** GPT-4.1-nano and Qwen3 at 0.6B, 4B, 8B, and 32B.

**Findings (verified):**
- **Section 4 text:** Agentic RAG needs "3.3× more input tokens and 1.9× more output tokens ... 1.5× more time".
- **Table 9 average ratios, agentic over enhanced:**
  - FIQA: time 1.5, input 2.7, output 1.7.
  - CQADupStack-EN: time 1.4, input 3.6, output 1.8.
  - **These do not match the text's 3.3× and 1.9×.** Report both. The conclusion says "up to 3.6 times more".
- **Table 3, intent handling F1, 500 queries per dataset:** On FEVER, agentic scores 64.6 and enhanced scores 87.9. The agent retrieved when it should not.
- **Table 4, query rewriting NDCG@10, averages:** agentic 55.6, enhanced 52.8, naive 50.3.
- **Table 5, document refinement NDCG@10, averages:** agent 43.9, enhanced with rewriting 49.5. In the 10% of cases where the agent retrieved again, 53% of documents were unchanged.

### 3.5 ReaLM-Retrieve
- **Source:** "When to Retrieve During Reasoning". Guo, Wu et al. HKU and industry co-authors. SIGIR 2026.
- **URL:** https://arxiv.org/abs/2604.26649. Status 200. v1, 29 Apr 2026.

**Table 4, MuSiQue, DeepSeek-R1-Distill-Qwen-32B (verified):**

| Method | Calls | Latency, seconds | Tokens |
|---|---|---|---|
| No retrieval | 0 | 12.4 | 8,432 |
| Single RAG | 1.0 | 13.2 | 9,156 |
| IRCoT | 3.4 | 18.7 | 11,284 |
| Search-R1 | 2.4 | 15.8 | 10,102 |
| ReaLM-Retrieve | 1.8 | 14.1 | 9,489 |

**Table 5, cost per query (verified):**
- Pricing: output tokens only, at $2.19 per million.
- IRCoT $0.025. Single RAG $0.020. ReaLM-Retrieve $0.021.

**Table 2, F1 (verified):**
- MuSiQue: Single RAG 59.4, IRCoT 65.4, ReaLM-Retrieve 71.2.

**Caution (inferred):** The no-retrieval MuSiQue EM here is 41.2. Other papers report about 2 to 14 EM for MuSiQue without retrieval, for example Adaptive-RAG Table 2 and 2501.12835 Table 1. That difference suggests a different evaluation setup. Check the subset and the scorer before relying on the absolute values.

---

## 4. Adaptive routing

### 4.1 Self-RAG
- **Source:** Asai, Wu, Wang, Sil, Hajishirzi. University of Washington, AI2, IBM. ICLR 2024.
- **URL:** https://arxiv.org/abs/2310.11511. Status 200.

**Mechanism (verified, Table 1 and Algorithm 1):**
- The model predicts a Retrieve token. It then scores each passage with ISREL, which rates relevance.
- It scores its output with ISSUP, which rates support, and ISUSE, which rates usefulness.
- Segment ranking uses weights 1.0, 1.0, and 0.5. The retrieval threshold is 0.2. Beam width is 2.

**Table 2 (verified):**
- The scorer for PopQA and TQA is "acc", which is match-contains, not EM.

| Model | PopQA | PubHealth | ASQA str-em |
|---|---|---|---|
| Self-RAG 13B | 55.8 | 74.5 | 31.7 |
| Self-RAG 7B | 54.9 | 72.4 | 30.0 |
| Alpaca13B with retrieval | 46.1 | not listed here | 34.8 |
| Ret-ChatGPT | 50.8 | 54.7 | 40.7 |

- Self-RAG loses on ASQA str-em to Alpaca13B with retrieval and to Ret-ChatGPT.

### 4.2 Adaptive-RAG
- **Source:** Jeong, Baek, Cho, Hwang, Park. KAIST. NAACL 2024.
- **URL:** https://arxiv.org/abs/2403.14403. Status 200. Code: https://github.com/starsuzi/Adaptive-RAG, status 200.
- **Mechanism:** A T5-Large classifier routes each query to one of three labels: A for no retrieval, B for single-step retrieval, C for multi-step retrieval, which uses IRCoT.
- **Conditions:** BM25 retriever, 500 test samples per dataset, A100 GPUs.

**Table 1, FLAN-T5-XL 3B, average over 6 datasets (verified):**
- Time is relative to single-step retrieval.

| Method | EM | Steps | Relative time |
|---|---|---|---|
| Single-step | 34.83 | 1.00 | 1.00 |
| Adaptive-RAG | 37.17 | 2.17 | 3.60 |
| Multi-step | 39.00 | 4.69 | 8.81 |
| Self-RAG | 9.90 | not extracted | not extracted |
| Oracle routing | 45.00 | not extracted | 2.11 |

- With GPT-3.5, Adaptive-RAG scores 37.97 EM at relative time 1.46. Multi-step scores 38.13 EM at relative time 3.33.

**Table 3, exact time per query and share of predicted labels (verified):**
- No retrieval: 0.35 s, 8.60% of queries.
- One step: 3.08 s, 53.33% of queries.
- Multi-step: 27.18 s, 38.07% of queries.

**Weakness (verified, Table 4 and section 5):**
- Classifier accuracy is only 54.52% overall. It is 30.52% on the "No" label.
- The "A" label is misclassified as "B" about 47% of the time.

### 4.3 CRAG, Corrective RAG
- **Source:** Yan, Gu, Zhu, Ling. USTC and UCLA.
- **URL:** https://arxiv.org/abs/2401.15884. Status 200.
- **Mechanism:** A T5-large evaluator sorts retrieval into Correct, Incorrect, or Ambiguous, using upper and lower thresholds. When results are Incorrect, it falls back to Google Search API.

**Table 1, SelfRAG-LLaMA2-7b generator (verified):**

| Dataset | RAG | CRAG |
|---|---|---|
| PopQA | 52.8 | 59.8 |
| PubHealth | 39.0 | 75.6 |

- Self-CRAG scores 61.8 on PopQA. Self-RAG scores 54.9.

**Table 4, evaluator accuracy on PopQA (verified):**
- CRAG's T5 evaluator: 84.3.
- ChatGPT: 58.0.
- ChatGPT few-shot: 64.7.

**Table 6, overhead, generation only (verified):**
- Time per instance: RAG 0.363 s, CRAG 0.512 s, Self-RAG 0.741 s, Self-CRAG 0.908 s.

### 4.4 Reproductions and criticism

**Self-RAG does not transfer to an untuned model (verified, CRAG Table 1):**
- CRAG's own run of Self-RAG inference on LLaMA2-hf-7b scored 0.7 on PubHealth and 29.0 on PopQA.
- The tuned Self-RAG model scored 72.4 and 54.9.
- In Adaptive-RAG Table 1, Self-RAG scores only 9.90 EM.
- Inferred: long outputs lower EM, and Self-RAG reports "acc" instead of EM.

**"Adaptive Retrieval without Self-Knowledge? Bringing Uncertainty Back Home":**
- **Source:** Moskvoretskii, Lysyuk, Salnikov, Panchenko et al. Skoltech, AIRI, MTS AI.
- **URL:** https://arxiv.org/abs/2501.12835. Status 200.
- **Conditions:** LLaMA 3.1-8B-instruct, 500-question subsets, scorer "In-Accuracy", which checks that the gold answer is contained in the output.
- **Table 1, NQ, In-Accuracy with LM calls per question (verified):**
  - Best uncertainty method: 0.512, 1.8 calls.
  - DRAGIN: 0.480, 4.5 calls.
  - SeaKR: 0.406, 14.6 calls.
  - Rowen: 0.494, 29.5 to 55.0 calls.
- **Table 1, TriviaQA (verified):** Never-RAG scores 0.636 and Always-RAG scores 0.610. Retrieval hurts.
- **Table 1, 2Wiki (verified):** IRCoT, Adaptive-RAG, and DRAGIN score about 0.454 to 0.456. The best uncertainty method scores 0.384. Complex methods still win on multi-hop.
- **Their stated takeaway (verified):** "Uncertainty methods outperform baselines on single-hop tasks, match them on multi-hop tasks, and are far more efficient."
- **Evidence for the takeaway (verified):** uncertainty methods need fewer than 1 retrieval call and at most 2 LM calls.

**DRAGIN:**
- **Source:** Su, Tang, Ai, Wu, Liu. Tsinghua University. ACL 2024 venue per my recall; status: not checked.
- **URL:** https://arxiv.org/abs/2403.10081. Status 200.
- **Table 2, Llama2-13b-chat (verified):**
  - HotpotQA EM: FLARE 0.180, single-round RAG 0.263, no retrieval 0.223.
  - DRAGIN: 0.314.
- A reimplemented FLARE loses to single-shot retrieval here.

**Probing-RAG:**
- **Source:** Baek, Chang, Kim, Lee, Lee. Chung-Ang University. NAACL 2025 Findings.
- **URL:** https://arxiv.org/abs/2410.13339. Status 200.
- **Table 1, Gemma-2b, average EM over 5 datasets (verified):**
  - No retrieval 19.0. Single-step 14.0. FLARE 11.8. Adaptive-RAG 14.0.
  - DRAGIN 22.4. Probing-RAG 22.8.
- **Table 2, total retrieval calls (verified):** Probing-RAG 1,988, Adaptive-RAG 3,068, DRAGIN 13,570.

**SeaKR:**
- **Source:** Yao, Qi et al. Tsinghua University.
- **URL:** https://arxiv.org/abs/2406.19215. Status 200. v1, 27 Jun 2024.
- I downloaded it but did not extract its own tables. Its cost in the 2501.12835 re-measurement is given above.

---

## 5. Talks
Talks found. **No timestamps are verified.**
- **"CMU Advanced NLP Spring 2026 (10): Akari Asai - Retrieval, RAG, and Deep Research"**
  - https://www.youtube.com/watch?v=uoM32c4BQ-g, status 200.
  - Published 2026-03-26. 4,654 s long.
  - The description lists "Techniques for training Deep Research agents".
- **"Akari Asai: Self-reflective Language Models with Retrieval (2023-10-26)"**
  - https://www.youtube.com/watch?v=bVz8Ua1VVsE, status 200. 3,609 s long.
- **Captions:** Both pages list an ASR caption track. The timedtext URL returned HTTP 200 with 0 bytes. The browser transcript panel did not load, and the tab was `visibilityState: hidden`.
- **Search-R1 talk:** peterjin.me links to one Bilibili video. I did not open it.

---

## 6. Production post with numbers
- **Source:** "Up to 40% better relevance for complex queries with new agentic retrieval engine". Microsoft Azure AI Search team, author "amaias". May 19, 2025.
- **URL:** https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/up-to-40-better-relevance-for-complex-queries-with-new-agentic-retrieval-engine/4413832. Status 200.

**Findings (verified):**
- "+16 points (up to +33 points) answer relevance improvement ... for complex queries".
- "on-par results for simple queries".
- "+15 points increase in result rate".
- The judge is GPT-4o, using the "RAG triad" metrics.
- Query planning uses a single LLM call. The post claims "Minimal cost and latency" but **gives no latency number**.
- **Table 6, answer relevance, search API → agentic API:**
  - Support set, Snippet queries: 27.78 → 59.72.
  - MIML set, Range queries: 46.56 → 47.73.

**Microsoft Learn overview (verified):**
- https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview, status 200. ms.date 2026-06-02.
- It says "Agentic retrieval adds latency compared to a single-query pipeline". It gives no number.
- It references the "2026-08-01-preview" API.

---

## Things I could NOT verify
1. **YouTube captions and timestamps:** caption fetch returned 0 bytes. I have no timestamped quotes from any talk.
2. **OpenAI deep research HTTP status:** curl returned 403. I read the text in the browser but did not capture the status there. I could not fetch the OpenAI BrowseComp blog or the GPT-5 page; both returned 403.
3. **Opus 4.6 single-agent BrowseComp score:** only the multi-agent 86.8% appears in the text.
4. **Absolute values for other papers:** R1-Searcher Table 2, SeaKR's own tables, the Search-R1 empirical-study tables, the ZeroSearch masking Table 7, and DeepResearcher (2504.03160, downloaded but not read) are all not checked.
5. **DRAGIN venue:** ACL 2024 is from my memory and is not checked.
6. **Search-R1 wandb logs and the Bilibili talk:** not opened.
7. **Secondary sources not opened:** the search-result claims of "16–22× inference time", "3–10× cost", and a "Forrester 42%" figure. None of these is cited as fact.
8. **ReaLM-Retrieve absolute scores:** they conflict with other MuSiQue baselines. The reason is not checked.
9. **"Is Agentic RAG worth it?" cost ratios:** the text says 3.3× and 1.9×. Table 9 gives 2.7 to 3.6× for input and 1.7 to 1.8× for output. I could not resolve which is correct.
10. **Production latency:** I found no post that gives a measured p50 or p95 latency for agentic retrieval.

**Summary:** Agentic retrieval clearly pays off on multi-hop and browsing tasks. On single-hop questions it costs 1.5 to 10 times more with no gain. The best-measured cheap alternatives are uncertainty-based routing and better retrievers.
# Module 19: Agent product design and human approval

Research date: 2026-09-25. Status: research dossier, not course material. Reviewed on 2026-09-25 by an independent reviewer. Section 10, Review log, lists every correction.

Module question, from `_curriculum/README.md` line 377: **Which actions can the agent take alone, and what must the approval screen show for the approval to mean anything?**

## How this dossier was built

- **Inputs.** Two research reports written on 2026-09-25 in `S/reports/`: `research_agent-product_approval.md` and `research_agent-product_confidence.md`. Below they are the approval report and the confidence report.
- **Path short names.** `S/` means the research scratchpad. `RA/` means `S/research_agent-product/approval/`. `RC/` means `S/research_agent-product/confidence/`. `SR/` means `RA/support/raw/`, where a helper agent saved the support-platform and framework sources. `W/` means `RA/warn/`, where a second helper agent saved the security-warning papers. `D19/` means `S/dossier_m19/`, the dossier author's notes.
- **Other inputs.** The Module 19 brief in `_curriculum/README.md` lines 374 to 389. The rules in `S/briefs/BRIEF_research.md`, `research-method.md` and `writing-style.md`. The structure of `_curriculum/module-10-memory.md` and `_curriculum/module-17-guardrails.md`.
- **Work done for this dossier.** No lab ran except the two saved prototypes. No URL was fetched. The dossier author did five read-only things:
  1. Re-grepped 135 anchors of section 4 in their saved files. Script `D19/anchor_check.py`, output `D19/anchor_check.txt`. **135 of 135 anchors match their expected count.** 119 check an exact count of 1 or 2. 13 check a minimum of one hit. 3 are absence checks. Every concept passes all its anchors. The per-concept counts are at the end of `D19/anchor_check.txt`.
  2. Re-ran both prototype self-tests. `RA/proto/approval_policy_sim.py --selftest` printed "selftest: 9 checks passed" in 0.07 s. `RC/proto/confidence_gate.py --selftest` printed "SELF-TEST PASSED" with 8 checks in 0.03 s. Outputs `D19/selftest_approval.txt` and `D19/selftest_confidence.txt`.
  3. Re-ran both prototypes in full. Both outputs match the saved outputs byte for byte, apart from the timing line. `D19/rerun_approval.txt` and `D19/rerun_confidence.txt`. The confidence prototype took 2.57 s.
  4. Recomputed every arithmetic claim. Script `D19/recompute.py`, output `D19/recompute.txt`. Section 5.6 lists the results. Four report statements changed. Section 7 lists them.
  5. Grepped `^## ` headings in `study-material/*/*.md` and read the dossiers of Modules 13 to 18. Grepped `study-material/` for promises made to Module 19. Section 2.
- **Run conditions for every prototype number.** Python 3.9.6, standard library only, the learner's Apple arm64 Mac, 2026-09-25. Machine load was not recorded. Not checked.
- **Labels.** Every claim is **verified**, **verified by run**, **inferred** or **not checked**. A verified claim names its file and line, or its table. "Verified by run" means a prototype ran on 2026-09-25 on the learner's Mac, and the output file is named. An inferred claim names its basis and the check that would confirm it. **Vendor number** marks a number that a company published about its own product, on data it chose. **Browser data** marks a result measured on browser or phone security warnings. Browser data is never agent data in this dossier.
- **Terms used in the whole dossier.**
  - **Approval** or **confirmation**: the agent stops before one action and a person says yes or no.
  - **Approval screen**: what the person sees at that moment.
  - **Pre-approval**: the person says yes once, before the task, for a class of actions.
  - **Confirmation recall**: the share of actions that needed a confirmation where the agent asked. It measures the agent, not the person.
  - **Catch rate**: the share of harmful actions that the person refuses. It measures the person.
  - **Click-through rate**: the share of warnings where the person goes on. In the browser papers, a click-through on a real threat is a miss.
  - **Habituation**: a person reacts less to a signal after seeing it many times.
  - **Moral crumple zone**: Elish's name for blame that lands on the nearest human who had little control.
  - **Confidence gate**: the agent acts alone when its confidence is at or above a threshold. Otherwise it sends the case to a person.
  - **Calibration**, in this module: stated confidence matches the observed accuracy. Module 11 uses "calibration set" for a set of human labels that validates a judge. That is a different meaning. The lesson must say this once.
  - **ECE**, expected calibration error: the weighted average gap between mean confidence and accuracy over confidence bins.
  - **AUROC**: the chance that a random right answer gets higher confidence than a random wrong answer. 0.5 means no ranking.
  - **Coverage**: the share of actions the gate lets the agent take alone. **Selective risk**: the error rate among those actions.
  - **Conformal risk control**, CRC: a method that picks a threshold from labelled data so that the expected loss on new data is at most a target α.

---

## 1. Purpose and the module question

Module 7 measured what a person's "yes" is worth. Module 9 made the wait for that "yes" durable. Module 8 bound the "yes" to an authorization grant. This module owns the interface and the decision policy: which actions skip the person, which stop for a person, and what the person sees.

The short answer: **let the agent act alone on actions that are reversible and have no outside effect. Stop it right before each irreversible action or data send. Show the payload, the target, the recipient and what cannot be undone. Keep prompts rare enough to be read.** A confidence score can widen the "alone" set only after you measure it on labelled traffic like yours and keep a random review sample.

| Part of the question | Short answer | Where |
|---|---|---|
| Which actions can the agent take alone | The published line is reversibility and outside effect, not read against write. Reads are pre-approved in Zendesk. OpenAI lets uploads run on pre-approval and always confirms deletes and sends. A "read-only" label from a tool server is a claim | 4.3 |
| What is the default today | Mostly run without asking. The OpenAI Agents SDK, LangChain's approval middleware, Vercel `ai` and Copilot Studio all default to no approval. The Claude Agent SDK is the exception checked: its default mode sends a call that needs approval to the app's callback. Salesforce switched its standard actions to confirm in September 2025, after injection risk | 4.2 |
| When to ask | At the point of risk. Not at task start. Stop a batch before its first risky action | 4.4 |
| What the screen must show | The action and full inputs, the target, what data leaves and who receives it, the risk, what cannot be undone, and what already ran. A decline as easy as accept | 4.5, 4.7 |
| Does the tooling carry that | No. SDK approval objects carry a tool name and arguments. No reason, risk, target or reversibility field was found | 4.6 |
| Measured click-through on approval prompts | For agents, only Module 7's 1,053-tester study. No vendor publishes a human catch rate on browser-agent or support-agent confirmations. Vendors publish confirmation recall instead, which measures the agent | 4.1, 4.8 |
| Why more prompts can mean less safety | Habituation, shown in browser and phone warnings. Design moves click-through much more than wording does | 4.9 |
| When the step is worse than no step | When it replaces an automated check that catches more than the tired person does. It always moves blame to the person | 4.10 |
| What experienced users do | They leave per-action approval and monitor and interrupt instead. The product needs a stop control | 4.11 |
| Can confidence gate an action | Stated confidence misses accuracy by 20 to 89 points on HLE. Low ECE does not mean the score ranks. A threshold holds only on traffic like its labels, and a silent shift breaks it | 4.13 to 4.18 |
| Do shipped products gate on LLM confidence | Documented thresholds are on intent classifiers and extraction models. The one LLM support product checked names no number | 4.19 |

Summary: approve by reversibility, and confirm at the point of risk with the payload on screen. Trust a confidence gate only with your own labels and a random sample.

## 2. Scope

### 2.1 In scope

- The decision policy: which action classes run alone, need confirmation, need a hand-off, or are blocked.
- The approval screen: what it shows and what the person can do.
- Published approval designs in shipped agents. OpenAI: Operator, ChatGPT agent, the computer-use guide and Codex approvals. Also Gemini computer use, Claude in Chrome, the Anthropic computer-use tool and the MCP spec.
- Support-agent platforms: Zendesk auto assist, Intercom Fin, Salesforce Agentforce, Microsoft Copilot Studio.
- Framework approval defaults and approval objects: OpenAI Agents SDK 0.22.3, LangChain 1.4.2, Vercel `ai` 7.0.114. The reviewer added the Claude Agent SDK permission modes and LangGraph `interrupt()` from docs fetched on 2026-09-25.
- Approval fatigue and click-through, with agent data and browser data kept apart.
- The suggest, confirm, execute gradient.
- Informed consent and the blame problem.
- Confidence calibration of LLMs, selective prediction and conformal thresholds as the basis of a confidence gate.
- Vendor confidence thresholds in shipped products.

### 2.2 Out of scope, and the owner of each item

| Topic | Owner |
|---|---|
| Approval rates, 93% and 97%. The 1,053-tester study with 13.6% human catch. The 17% to 5% fatigue points. The auto-mode classifier. "Options, Not Clicks" 13 of 16. Plans rejected 39% against single prompts 3% | Module 7, built section 5.1 |
| An allow rule removes every later check. Fail-closed layers | Module 7, built sections 5.2 and 5.3 |
| What an approval must bind to. A UI click is not authorization | Module 8, built section 5.1 |
| Durable approval waits, resumed nodes, timeout branches, the "expired" state | Module 9, built Phase 4, sections 4.1 to 4.3 |
| Tool annotations such as `readOnlyHint` are claims, not permissions. Approval does not freeze a tool definition | Module 6, built sections 5.1 and 5.2 |
| Judge validation on a "calibration set" of human labels | Module 11, built Phase 3, sections 3.1 to 3.5 |
| A gate threshold on a judge score does not give a rate | Module 11, built section 4.4 |
| Cascade cost arithmetic, escalation signals, the random-escalation control | Module 1, built section 3.4. Module 14, built Phase 3 and dossier 4.9 to 4.12 |
| Every detector threshold blocks benign work too | Module 16, built section 3.4 |
| Escalation to a human as a safety control. Guardrail placement before the side effect | Module 17 dossier, `module-17-guardrails.md` 4.15 |
| Human oversight duties and audit records in law | Module 18 dossier |
| Prompt injection as the cause of a harmful action | Module 16 |
| The lethal trifecta as a property of the session | Module 16, built section 1.3 |
| An attack success rate needs its denominator, check and attacker | Module 16, built section 3.1 |
| Binding an approval to content, not to a tool name | Module 16, built section 5.2 |
| Plan-then-execute fixes the tools, not the arguments | Module 16, built section 4.2 |
| Agent evals, online judges, thumbs feedback as a quality signal | Module 12, built Phases 1 to 6. Sections 4.4 and 5.3 are the nearest |
| A saga's undo step is itself a side effect | Module 9, built section 3.4 |

### 2.3 Overlap with built headings

Headings were read with `grep '^## '` on `study-material/*/*.md` on 2026-09-25. Modules 13 to 16 now have built phases too. Their headings were grepped with the same command.

| Built heading | What it owns | What this module adds |
|---|---|---|
| Module 7, "5.1 — People approve almost every permission prompt" | The only agent human catch rate: 143 of 1,053, 13.6%. Fatigue points 17% early, 5% after 50 prompts. Vendor approval rates 93% and 97% | Link it. Do not repeat the numbers. Add vendor confirmation recall, 4.1, and screen content, 4.5 |
| Module 7, "5.2 — An allow rule removes every check after it" | Sticky allow rules in a coding harness | The same effect in support platforms: pre-approved actions may run out of order, 4.3 |
| Module 8, "5.1 — A click in the agent UI is not authorization" | Binding the click to a grant | What the screen shows is what the authorization server should record as shown. 4.7 links it |
| Module 9, "4.3 — Every wait needs a timeout branch" | The timeout and the "expired" state | Intercom Fin waits "until a teammate acts or a timeout is reached", 4.6. Link 4.3 |
| Module 6, "5.1 — Annotations are claims, not permissions" | `readOnlyHint` from an untrusted server | "Reads run alone" needs a checked read, 4.3. Link 5.1 |
| Module 11, "3.1 — A judge is a classifier: report TPR and TNR" | "Calibration set" of human labels for a judge | "Calibration" here means confidence matching accuracy, 4.13 to 4.18. Say the two meanings once |
| Module 11, "4.4 — A gate threshold does not give you a rate" | A threshold on a judge score for a release gate | A threshold on the agent's own confidence for one action, 4.16 |
| Module 1, "3.4 — Routing cascades" and Module 14, "3.1" to "3.4" | Cost cascades and escalation signals | The same threshold arithmetic with error rate as the target, not cost, 4.16 and 4.18 |
| Module 16, "3.4 — Every detector threshold blocks benign work too" | Detector threshold trade-off | The confidence gate trades automation against error in the same way, 4.16 |
| Module 16, "5.2 — Bind an approval to content, never to a name" | An approval bound to a tool name approves any content | A screen that shows only a tool name informs the person no better, 4.5 and 4.6. Link 5.2 |
| Module 16, "4.2 — Plan-then-execute fixes the tools, not the arguments" and "1.3 — The trifecta belongs to the session" | Data-derived arguments. The session as the unit of risk | The screen marks arguments that came from outside content, 4.5 row 9. A "data send" is judged per session, 4.3 |
| Module 16, "3.1 — An ASR needs its denominator, check and attacker" | How to read an attack success rate | Claude in Chrome's 23.6% and 11.2%, 4.12 and conflict k |
| Module 12, "4.4 — Thumbs find failures, they do not measure quality" and "5.3 — An online eval cannot stop a refund" | User feedback as a signal. Checks after the action | An acceptance rate used to promote an action to "alone", 4.12. The gate must act before the side effect |
| Module 9, "3.4 — A saga undoes side effects, and undo is one too" | Compensation steps | "Reversible" in 4.3 means an undo step exists and was tested. Link 3.4 |

### 2.4 Promises made to Module 19

Found with `grep -rn "Module 19"` over `study-material/` on 2026-09-25.

| # | Promise | Made in | Paid in |
|---|---|---|---|
| 1 | Approval screen design | `agent-harness-phase-05-approval-stack.md` lines 12 and 301. `agent-harness/course.json` lines 62 and 123 | 4.5, 4.6, 4.7 |
| 2 | Plan-level against action-level review | `agent-harness/course.json` lines 62 and 123 | Partly. 4.4 gives the point-of-risk rule. No source measures plan review against action review for agents beyond Module 7's 39% and 3%. Gap 4 |
| 3 | Link Module 7 5.1 for the approval numbers and do not repeat them | `agent-harness/course.json` line 178 | 2.2, 4.1, 4.8 |
| 4 | What the screen must show, and the screen text as the "shown" field of the consent record | `agent-protocols/course.json` lines 339 and 454. `agent-protocols-phase-05-proof.md` lines 43 and 203 | 4.5, 4.7 |
| 5 | The screen shows "expired" instead of "approved" for a late answer | `orchestration-durable-phase-04-approval.md` line 553 | 4.7 names it as a screen state. No product source shows such a state. Gap 7 |
| 6 | Approval design for products | `agent-evals-phase-05-online.md` lines 570 and 924. `agent-evals/course.json` line 84 | 4.2 to 4.7 |
| 7 | Human approval screens, listed as out of scope | `module-16-security.md` line 54. `module-17-guardrails.md` lines 92 and 461. `module-18-compliance.md` line 105 | 4.5 to 4.11 |
| 8 | A call whose argument comes from data, such as a reply address in a ticket, goes to a person. "Module 19 (planned) covers the approval screen" | `security/security-phase-04-designs.md` line 317. Added by the reviewer | 4.5 row 9. Inferred only |

---

## 3. Sources, with dates, tags and versions

All sources were fetched on 2026-09-25 by the research agents or their helpers. HTTP 200 unless noted. Rank uses the scale in `research-method.md`. 1 is code at a tag, 2 is versioned docs and 3 is a paper. 5 is a vendor post with conditions, and 7 is a news report.

### 3.1 Code and docs

| Source | Version or date | Local file | Rank |
|---|---|---|---|
| OpenAI Agents SDK, `tool.py` and `items.py` | PyPI `openai-agents` 0.22.3 | `SR/oai_tool_0.22.3.py`, `SR/oai_items_0.22.3.py` | 1 |
| LangChain `HumanInTheLoopMiddleware` | 1.4.2 | `SR/lc_hitl_src_1.4.2.py` | 1 |
| Vercel `ai` | npm 7.0.114 | `SR/ai_7.0.114_index.d.ts`, `SR/vercel_toolapproval.txt` | 1, 2 |
| Rasa Open Source `core/constants.py` | tag 3.6.21, PyPI 2025-01-14 | `RC/src/vendor/rasa_core_constants_3.6.21.py` | 1 |
| HLE eval code `run_judge_results.py` | commit `a59048963171c5b9cfe89fbcb97ddde39b540897` | `RC/src/hle_run_judge_results_a590489.py` | 1 |
| MCP specification, Tools | 2025-06-18 | `RA/src/mcp_tools_spec.txt` | 2 |
| OpenAI computer-use integration guide | current, no version | `RA/src/openai_cu_integration.txt` lines 5600 to 5660 | 2 |
| Gemini API computer use | page updated 2026-09-23 | `RA/src/gemini_computer_use.txt` | 2 |
| Anthropic computer-use tool | current | `RA/src/anthropic_computer_use.txt` | 2 |
| Codex agent approvals and security | current, no version | `RA/src/codex_approvals.txt` | 2 |
| Zendesk auto assist actions | current | `SR/zd_about_actions_autoassist.txt` | 2 |
| Intercom Fin human in the loop | current | `SR/ic_hitl.txt` | 2 |
| Salesforce knowledge article 005133036 | published 27 Sept 2025, read in a browser | `SR/sf_ka_005133036_browser_excerpt.txt` | 2 |
| Microsoft Copilot Studio, add tools | current | `SR/ms_add_tools.txt` | 2 |
| Dialogflow CX, Lex V2, A2I Textract, Azure Document Intelligence 4.0, Intercom Fin AI Engine | current | `RC/src/vendor/` | 2 |
| EU AI Act Article 14, on the Future of Life Institute host | 2024 text | `RA/src/aiact_art14.txt`. EUR-Lex not fetched | 2, secondary host |
| OpenAI Agents SDK, "Human-in-the-loop" docs | Re-fetched by the reviewer, 2026-09-25 03:25 UTC, HTTP 200 | `R/oai_hitl.txt` | 2 |
| Claude Agent SDK, "Configure permissions" | Re-fetched by the reviewer, 2026-09-25 03:25 UTC, HTTP 200, `code.claude.com/docs/en/agent-sdk/permissions` | `R/claude_sdk_perms.txt` | 2 |
| LangGraph, "Interrupts" | Re-fetched by the reviewer, 2026-09-25 03:25 UTC, HTTP 200, `docs.langchain.com/oss/python/langgraph/interrupts` | `R/lg_interrupts.txt` | 2 |

`R/` is the reviewer's folder `/private/tmp/claude-502/-Users-raghvendra-dhakar-Desktop-project-code/dabd56e3-78f3-4dbc-bddb-3316bb9bedda/scratchpad/refetch/`.

### 3.2 Vendor system cards and posts

| Title | Org | Date | What to read | Local file |
|---|---|---|---|---|
| Operator System Card | OpenAI | 2025-01-23 | Sections 3.1, 4.2 to 4.5 | `RA/src/operator_system_card.txt`. The openai.com page gave 403. The CDN PDF gave 200 |
| ChatGPT Agent System Card | OpenAI | 2025-07-17 | Section 3.1.2, Table 13 | `RA/src/chatgpt_agent_system_card.txt` |
| Piloting Claude in Chrome | Anthropic | 2025-08-25, per the saved text line 10 | Permissions, attack rates | `RA/src/claude_chrome.txt` |
| Measuring AI agent autonomy in practice | Anthropic | 2026-02-18 | Figures 2 and 3, footnote 9 | `RA/src/anthropic_autonomy.txt` |
| Salesforce Agentforce flaws | The Register | 2026-09-24 | Slack reply action | `SR/reg_agentforce.txt`. Rank 7 for mechanism |

### 3.3 Papers

| Title | Org | Date and status | What to read | Local file |
|---|---|---|---|---|
| Agentic AI and Human-in-the-Loop Interventions: Field Experimental Evidence from Alibaba's Customer Service Operations | Zhejiang, Fudan, Dartmouth, Alibaba | arXiv 2605.14830, May 2026. Preprint | Sections 3.4 and 5.2.1 | `SR/arxiv_2605.14830.txt` |
| Generative AI at Work | Stanford, MIT | arXiv 2304.11771. The saved file is the arXiv version. Journal status not checked | Adherence, line 850 | `SR/arxiv_2304.11771.txt` |
| Reframing LLM Agent Security as an Agent–Human Interaction Problem | UCLA | arXiv 2605.24309, 2026. Preprint | Table 1, lines 244 to 250 | `RA/src/reframing_2605.24309.txt` |
| Levels of Autonomy for AI Agents | Univ. of Washington, Knight Institute | arXiv 2506.12469, 2025. Preprint. Venue not checked | L1 to L5 | `RA/src/feng_levels.txt` |
| A new Level of Automation Taxonomy, reproducing Sheridan and Verplank 1978 | Save and Feuerberg | HFES Europe 2012 | Table 1 | `RA/src/save_loat.txt` |
| Informed Consent Online | Friedman, Felten, Millett | UW CSE TR 2000-12-2 | Five components | `RA/src/friedman_tr2000.txt` |
| Moral Crumple Zones | Elish | ESTS 5, 2019. Peer reviewed | Introduction | `RA/src/elish_crumple.txt` |
| The flaws of policies requiring human oversight of government algorithms | Green | CLSR 45, 2022. Peer reviewed | Abstract, sections 4 and 5 | `RA/src/green2022.txt` |
| Alice in Warningland | Akhawe and Felt | USENIX Security 2013. Peer reviewed. Browser data | Sections 5.1, 5.2, click times | `W/akhawe.txt` |
| Improving SSL Warnings | Felt et al. | CHI 2015. Peer reviewed. Browser data | Field and release results | `W/felt2015.txt` |
| You've Been Warned | Egelman, Cranor, Hong | CHI 2008. Peer reviewed. Browser data | Table 1 | `W/egelman.txt` |
| How Polymorphic Warnings Reduce Habituation in the Brain | Anderson et al. | CHI 2015. Study 1: fMRI on images of software security warning dialogs, in a lab. Study 2: Chrome extension permission warnings, mouse tracking. Not browser click-through data | Abstract | `W/anderson_chi.txt` |
| Tuning Out Security Warnings | Vance, Jenkins, Anderson et al. | MIS Quarterly 42(2), 2018. Peer reviewed. Phone data | Field experiment results | `W/vance_misq.txt` |
| More Harm Than Good? How Messages That Interrupt Can Make Us Vulnerable | Jenkins et al. | ISR 2016. Browser data | Abstract only. Numbers garbled | `W/jenkins_isr.txt` |
| Android Permissions: User Attention, Comprehension, and Behavior | Felt et al. | SOUPS 2012. Phone data | Abstract | `W/felt_soups.txt` |
| The Security Cost of Cheap User Interaction | Böhme and Grossklags | NSPW 2011. Position paper | Abstract | `W/bohme_nspw.txt` |
| Humanity's Last Exam | CAIS, Scale AI | arXiv 2501.14249, v11 2026-07-28. Preprint | Table 1 | `RC/src/2501.14249.txt` |
| HLE leaderboard | Scale AI | live, fetched 2026-09-25 | Calibration column | `RC/src/hle_scale_leaderboard_extract_2026-09-25.txt` |
| On Calibration of Modern Neural Networks | Guo et al. | ICML 2017 | ECE, Table 1 | `RC/src/1706.04599.txt` |
| Language Models (Mostly) Know What They Know | Anthropic | 2022. Preprint | Section 3.3 | `RC/src/2207.05221.txt` |
| GPT-4 Technical Report | OpenAI | 2023. Not peer reviewed. Vendor numbers on OpenAI's own model | Figure 8 | `RC/src/2303.08774.txt` |
| Just Ask for Calibration | Tian et al. | EMNLP 2023 | Table 1 | `RC/src/2305.14975.txt` |
| Can LLMs Express Their Uncertainty? | Xiong et al. | ICLR 2024 | Tables 2 and 3, section 5.2 | `RC/src/2306.13063.txt` |
| LLMs Must Be Taught to Know What They Don't Know | Kapoor et al. | NeurIPS 2024 | Abstract | `RC/src/abs_2406.08391.html` |
| Conformal Risk Control | Angelopoulos et al. | arXiv 2208.02814 v4. The saved file is the arXiv version. Venue not checked | Equation 4, Theorem 1 | `RC/src/2208.02814.txt` |
| A Gentle Introduction to Conformal Prediction | Angelopoulos and Bates | arXiv 2107.07511 v6. Tutorial. Venue not checked | Sections 1 and 3, section 4.3, Appendix A on Learn then Test | `RC/src/2107.07511.txt` |
| Conformal Prediction with LLMs for MCQA | Kumar et al. | ICML 2023 workshop | Section 4.3 | `RC/src/2305.18404.txt` |
| Beyond Binary Rewards, RLCR | MIT | ICLR 2026 | Lines 118 to 124 | `RC/src/2507.16806.txt` |
| Why Language Models Hallucinate | OpenAI, Georgia Tech | arXiv 2509.04664 v1, 2025-09-04. Preprint | Section 4 | `RC/src/2509.04664.txt` |
| SimpleQA | OpenAI | arXiv 2411.04368, 2024. Preprint | Calibration figure | `RC/src/2411.04368.txt` |
| Reasoning Models Better Express Their Confidence | KAIST, LG AI Research | NeurIPS 2025 | Abstract | `RC/src/2505.14489.txt` |

The confidence report section 6 lists nine more conformal and calibration papers. They are not used in section 4.

### 3.4 What changed recently

| Date | Change | Source | Why it matters |
|---|---|---|---|
| 2025-01-23 | Operator system card: confirmation recall 92% on 607 tasks | `RA/src/operator_system_card.txt` | First vendor number on agent confirmations. It measures the agent |
| 2025-06-18 | MCP spec: clients SHOULD show tool inputs before the call | `RA/src/mcp_tools_spec.txt` | The payload rule in a protocol |
| 2025-07-17 | ChatGPT agent card: confirmation recall 91.0%, critical 99.9% to 100.0% | Table 13 | Still agent-side only |
| 2025-08-25 | Anthropic, Piloting Claude in Chrome: attack success 23.6% to 11.2%, all tests in autonomous mode | `RA/src/claude_chrome.txt` | An agent-side rate, not a human catch rate |
| 2025-09-04 | Kalai et al.: explicit confidence targets | arXiv 2509.04664 v1 | A cost-to-threshold rule. Contains two slips, 4.18 |
| 2025-09-27 | Salesforce sets `isConfirmationRequired` to true for standard Agentforce actions | `SR/sf_ka_005133036_browser_excerpt.txt` | A default flipped because of injection risk |
| 2026-02-18 | Anthropic: auto-approve rises from about 20% to over 40% of sessions with tenure | `RA/src/anthropic_autonomy.txt` | Users leave per-action approval |
| 2026-05 | Alibaba field experiment with supervised support agents | arXiv 2605.14830 | The only field data found on human takeover of a support agent |
| 2026-05 | Wang et al.: runtime approval in 15 of 21 production agent systems | arXiv 2605.24309 | Approval is the main deployed control. Its SSL figure is mis-cited |
| 2026, current | OpenAI guide: three confirmation tiers. `pending_safety_checks` has zero hits on the guide | `RA/src/openai_cu_integration.txt` | A product rule set for what to confirm |
| 2026, current | Codex `approvals_reviewer = "auto_review"` | `RA/src/codex_approvals.txt` | A reviewer agent replaces the person for eligible requests |
| 2026-09-03 to 2026-09-09 | Newest HLE entries: calibration error 20% to 51% | leaderboard extract | Frontier models still overstate confidence |
| 2026-09-23 | Gemini computer-use page: `safety_decision` with `require_confirmation`, and `intent` for Gemini 3.x | `RA/src/gemini_computer_use.txt` | The approval payload is an explanation and a coordinate |
| 2026-09-24 | The Register: an Agentforce Slack reply action sent without confirmation | `SR/reg_agentforce.txt` | A missing confirmation as a reported flaw |

### 3.5 Versions to pin

| Item | Version checked | How |
|---|---|---|
| `openai-agents` | 0.22.3, uploaded 2026-09-17. Still the latest on PyPI at the reviewer's fetch, 2026-09-25 03:25 UTC | Saved PyPI JSON, `SR/pypi_openai_agents.json`. `R/pypi_oai.raw` |
| `langchain` | 1.4.2, uploaded 2026-09-18. Still the latest at the reviewer's fetch | Saved PyPI JSON. `R/pypi_lc.raw` |
| `langgraph` | 1.2.12, uploaded 2026-09-21, at the reviewer's fetch | `R/pypi_lg.raw` |
| npm `ai` | 7.0.114. Still the latest at the reviewer's fetch | Saved npm JSON. `R/npm_ai.raw` |
| MCP spec | 2025-06-18. A newer spec version was not checked. Module 6 cites 2026-07-28 | Not checked |
| Codex | No release tag. The GitHub API call failed | Not checked |
| Rasa Open Source | 3.6.21 | PyPI |
| HLE eval code | commit `a590489` | GitHub raw |
| Prototypes | Python 3.9.6, standard library | Re-run 2026-09-25 |

---

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Each concept gives one best piece of evidence first, with its conditions. Every quote and number in a "Best evidence" line was re-grepped in its saved file. The anchor counts are in "How this dossier was built". Every quote is 25 words or shorter.

### 4.1 "The agent asked" is not "the person caught it". Vendors publish confirmation recall, which measures the agent, and no vendor publishes a human catch rate on agent confirmations

- **Best evidence, verified. Vendor number.** ChatGPT agent system card, Table 13. Confirmation recall "Measures the percentage of the time where ChatGPT agent correctly confirms with the user prior to taking a relevant action". Value 91.0%. Operator 4o 90.8%, Operator o3 92.1%. `RA/src/chatgpt_agent_system_card.txt` lines 822 to 836.
- **Conditions.** The card says "this figure is an underestimate of the true confirmation rate". Critical confirmation recall is 100.0% for editing permissions, 99.9% for high-stakes communications and 100.0% for financial transactions. Sample sizes are not printed.
- **Verified. Vendor number.** Operator card section 4.3: recall 92% "On an evaluation set of 607 tasks across 20 categories". The card says the recall "measures the fraction of the time a confirmation is needed". `RA/src/operator_system_card.txt` lines 447 to 451.
- **Verified. Vendor number.** Operator section 4.2: the unmitigated model made 13 errors on 100 prompts. 8 "could be easily reversed". 5 were "to some degree, irreversible or possibly severe". Confirmations "reduced the risk by approximately 90%". Lines 431 to 442. The card gives no method for the 90%.
- **Inferred.** The 90% counts a confirmation as if the person always refuses a wrong action. Basis: section 4 of the card reports no user data. Check: a user study that measures refusals on planted wrong actions.
- **Link.** The only agent human catch rate is Module 7 section 5.1: 143 of 1,053, or 13.6%, on coding prompts. Do not repeat it here. Link it.
- **Use it.** Report two numbers for any approval step: how often the agent asks, and how often the person refuses a planted bad action.

### 4.2 In most frameworks and products checked, the default is to run without asking. Approval is opt-in per tool. The Claude Agent SDK is the exception checked, and one vendor flipped its default only after injection risk

- **Best evidence, verified.** OpenAI Agents SDK 0.22.3, `tool.py`: `needs_approval` is a bool or a callable with default `= False`. `SR/oai_tool_0.22.3.py` lines 499 to 506.
- **Verified, re-fetched 2026-09-25 03:25 UTC.** The OpenAI Agents SDK docs say: "Set needs_approval to True to always require approval or provide an async function that decides per call." A callable rule fails closed. When the SDK cannot inspect the arguments, "the call requires manual approval". `R/oai_hitl.txt`, "Marking tools that need approval".
- **Verified.** LangChain 1.4.2 `HumanInTheLoopMiddleware`: "If a tool doesn't have an entry, it's auto-approved by default." `SR/lc_hitl_src_1.4.2.py` line 257.
- **Verified, re-fetched 2026-09-25 03:25 UTC. The exception.** Claude Agent SDK permission modes. In `default` mode there are "No mode-based auto-approvals". A call that needs approval and matches no allow rule goes to the app's `canUseTool` callback. Reads inside the working directories and read-only Bash commands are approved with no rule. `dontAsk` denies any call that would prompt. `bypassPermissions` runs tools "without permission prompts", except "the actions no mode auto-approves". Deny rules and ask rules still apply in that mode. `auto` lets "A model classifier" approve or deny prompts. `R/claude_sdk_perms.txt`, "How permissions are evaluated" and "Available modes". Not checked: what happens in `default` mode when the app sets no callback.
- **Verified.** Vercel `ai`: `'not-applicable'` means "the tool is executed without an approval flow. This is the default behavior." `SR/vercel_toolapproval.txt` line 253.
- **Verified.** Microsoft Copilot Studio, "Ask the end user before running": "This option is set to No by default." `SR/ms_add_tools.txt` line 96.
- **Verified.** Salesforce, published 27 Sept 2025: "changing the isConfirmationRequired setting from false to true", "To better protect customers against prompt injection risks". The sentence names eight actions, such as `CancelOrder` and `ResetPassword`. The next sentence applies the measure "to all Agentforce Standard actions". Custom actions are only advised to follow. `SR/sf_ka_005133036_browser_excerpt.txt` lines 6 to 8. Read in a browser. What the confirmation shows is not checked.
- **Verified, from the two sources named.** The Claude Agent SDK's `auto` mode and Codex `auto_review`, 4.10, both let a model approve in place of a person. Module 7 section 5.1 owns the classifier numbers. Link it.
- **Verified. News report, rank 7.** The Register, 24 Sep 2026: the Agentforce "Reply to a Slack Thread" action "did not require user confirmation before sending a message". `SR/reg_agentforce.txt` line 140.
- **Verified.** MCP 2025-06-18: "the protocol itself does not mandate any specific user interaction model". `RA/src/mcp_tools_spec.txt` line 44. It still says there SHOULD be a human able to deny tool invocations, line 49.
- **Inferred.** In the SDKs above that default to no approval, a team that adds a new tool gets no approval step unless someone sets it. Check: list every tool in a real agent with its approval setting.

### 4.3 The published line between "alone" and "confirm" is reversibility and outside effect, not read against write. A read-only label is a claim, and pre-approved actions can run out of order

- **Best evidence, verified.** OpenAI computer-use guide, three tiers. "Hand-off required" covers "The final step of changing a password." "Always confirm at action time" covers "Deleting local or cloud data." It also covers sending or posting as the user. "Pre-approval can be enough" covers "Uploading files." `RA/src/openai_cu_integration.txt` lines 5629 to 5655.
- **Conditions.** The guide is for computer-use agents. It has no version number. Uploading files is an outside effect, yet it is in the pre-approval tier when the first prompt allows it.
- **Verified.** Operator's policy tiers actions by risk severity and "the ease of reversing" a bad outcome. `RA/src/operator_system_card.txt` line 57.
- **Verified.** Zendesk auto assist names "Actions that only read data (such as checking the shipping status)" as candidates for pre-approval. Write actions "should be marked as agent-approved so that an agent can validate the action before it's executed". `SR/zd_about_actions_autoassist.txt` lines 189 to 193.
- **Verified.** Zendesk warns that "pre-approved actions may be executed in a different order than specified in a procedure". Line 203. Inferred: a pre-approved action can run before the step that was meant to guard it. Check: a procedure with a lookup then a pre-approved write, run many times.
- **Link.** Module 6 section 5.1: a tool's `readOnlyHint` from an untrusted server is a claim. "Reads run alone" is safe only for reads you verified in your own code.
- **Inferred.** A read can still leak. A read that sends a query to an outside server is an outside effect. Basis: Module 16 section 2.1, every output is an exit. Module 16 section 1.3 judges this risk per session: a session that holds private data and outside content makes any send risky. Check: list which read tools call outside hosts.
- **Link.** Module 9 section 3.4: an undo step is itself a side effect. Inferred: count an action as reversible only when a tested undo step exists for it. Check: run the undo for each action class in a test tenant.
- **Use it.** Classify each action by two questions: can it be undone within minutes, and does anything leave your system. Run alone only when both answers allow it.

### 4.4 Confirm at the point of risk, not at the start of the task. Stop a batch before its first risky action

- **Best evidence, verified.** OpenAI guide: "Don't ask for confirmation before starting the task if safe progress is still possible." It also says: "For an action batch, stop before the first action that needs confirmation." `RA/src/openai_cu_integration.txt` lines 5624 and 5607.
- **Verified.** Anthropic computer-use tool: confirm "before each block runs, because a batch can complete a multistep action within one turn". `RA/src/anthropic_computer_use.txt` line 685.
- **Verified.** The OpenAI guide adds that for generated code "a single script can perform many actions". Line 5607. Inferred: approving a script approves every action in it. Check: log the actions one approved script performs.
- **Link.** Module 7 section 5.1 reports that users reject 39% of plans and 3% of single permission requests. That is the only plan-level against action-level number found. It is a vendor number with no stated sample. Gap 4.
- **Inferred.** A task-start approval is a pre-approval. It has the out-of-order risk of 4.3. Check: none published.

### 4.5 A confirmation that shows only a tool name, a sentence or a click coordinate cannot inform consent. The screen must show the payload, the target, the recipient, the risk and what already ran

- **Best evidence, verified.** MCP 2025-06-18, Tools, Security: clients SHOULD "Show tool inputs to the user before calling the server, to avoid malicious or accidental data exfiltration". `RA/src/mcp_tools_spec.txt` line 694.
- **The list the module teaches.** It joins three sources. Each row is verified in its file unless marked.

| # | The screen shows | Source |
|---|---|---|
| 1 | The exact action and its full inputs, before the call runs | MCP, above |
| 2 | For sensitive data: what data, who receives it, and why | OpenAI guide line 5660: "state what data you will share, who will receive it, and why" |
| 3 | The action, the risk, and how the change is applied | OpenAI guide line 5627: "explain the action, the risk, and how you will apply the data or change" |
| 4 | The expected harms | Friedman et al. 2000: "accurate information about the benefits and harms" |
| 5 | Whether it can be undone | Inferred. OpenAI and Operator tier by reversibility, 4.3. Neither says the screen must print it |
| 6 | What already ran and what did not | OpenAI guide line 5608: "communicate what did and did not run" |
| 7 | A decline as easy to reach as accept | Friedman et al., 4.7 |
| 8 | Only actions that need a decision | Inferred from 4.9 and Module 7 section 5.1 |
| 9 | Which arguments came from outside content, such as an address read from a ticket | Inferred. Basis: Module 16 section 4.2, where a data-derived argument goes to a person, and `security-phase-04-designs.md` line 317. No product source checked shows such a mark. Check: plant an address in a ticket and read the screen |

- **Link.** Module 16 section 5.2: bind an approval to content, never to a name. A screen that shows only a tool name has the same flaw for the person.

- **Verified.** OpenAI's guide says "The model's request to act is not user permission." Line 5606.
- **Verified.** Operator shows a sentence plus a screenshot. Its example names the action and the recipient, "requesting a password reset for your account". The email body is only in the screenshot. `RA/src/operator_system_card.txt` lines 459 to 462.
- **Verified.** Gemini computer use hands the client a function call, a `safety_decision.explanation` such as "Must check check-box", and a coordinate. The client must "prompt the end user". `RA/src/gemini_computer_use.txt` lines 7860 to 7906. Gemini 3.x also returns an `intent` "explaining why the model chose that action", line 435.
- **Inferred.** A coordinate tells a person nothing unless the screen draws the target on a screenshot. Check: build the sample client and read what its prompt prints.
- **Verified by run. Assumed inputs.** Lab A, break-it: only 1 fault in 10 shows in the tool name. Policy D harm then rises from 62.14 to 212.58 per day. 95.6% of that harm carries a human "yes". `RA/proto/run_output.txt`. The 0.1 visibility is an assumption. This shows the mechanism, not a size.

### 4.6 The approval objects in agent frameworks carry a tool name and arguments. They carry no risk, target or reversibility field, and only Vercel `ai` has an optional free-text reason, so the product must build rows 2, 3, 5, 6 and 9 itself

- **Best evidence, verified.** OpenAI Agents SDK 0.22.3: `class ToolApprovalItem` holds `raw_item`, `tool_name`, `tool_namespace`, `tool_origin` and `tool_lookup_key`. `tool_origin` is "metadata describing where the approved tool call came from", not a risk field. The arguments sit in the raw tool call. `SR/oai_items_0.22.3.py` lines 556 to 580. The string "reversib" appears zero times in the file.
- **Verified, re-fetched 2026-09-25 03:25 UTC.** LangGraph `interrupt()` accepts "any JSON-serializable value which is surfaced to the caller". The graph "waits indefinitely until you resume execution". `R/lg_interrupts.txt`, "Interrupts" intro. So the screen content is whatever the developer puts in the value. The indefinite wait is Module 9 section 4.3's case for a timeout branch. Link it.
- **Verified.** LangChain 1.4.2: "an action request with a name, args, and description". Decisions are `approve`, `edit`, `reject` and `respond`. `SR/lc_hitl_src_1.4.2.py` lines 53 to 65. "reversib" appears zero times.
- **Verified.** Vercel `ai` 7.0.114: an `approvalId` and an optional "HMAC-SHA256 signature binding this approval request to its tool call". `SR/ai_7.0.114_index.d.ts` lines 1304 to 1327. This binds the approval to the call. Module 8 section 5.1 owns binding.
- **Verified, correction added in the coherence pass on 2026-09-25.** The same type has an optional `reason`, "Reason why the tool call requires approval", and an optional `isAutomatic`. The docs set `reason` in the per-tool approval configuration. So it is policy text for the class, not a reason for this call. It fills the risk row only as class text. Found by the Phase 2 writer, in the type file lines 1304 to 1328 and the AI SDK "Tool Calling" page.
- **Verified.** Intercom Fin: the teammate sees a "Fin requires your decision" card with the fields the builder configured. Fin "does not continue the procedure until a teammate acts or a timeout is reached". `SR/ic_hitl.txt` lines 1136 and 1141. The helper reported no diff or amount field. Not re-checked by the dossier author.
- **Verified.** Copilot Studio shows an optional tool description. The doc says it tells the user "what they're being asked to authenticate". `SR/ms_add_tools.txt` line 98. Inferred: it is a static tool description, not a payload view. Check: build one tool and read the prompt.
- **Use it.** Your product builds the approval request for the screen. Add fields for target, recipient, reversibility, risk class and reason.

### 4.7 A screen can supply disclosure and agreement. It cannot prove comprehension, and no product checked tries

- **Best evidence, verified.** Friedman, Felten and Millett 2000 split informed consent into disclosure, comprehension, voluntariness, competence and agreement. Accept and decline "should be visible and readily accessible". `RA/src/friedman_tr2000.txt`, lines 39 to 41 and 418 to 425. The saved text splits the quote over one word per line.
- **Verified.** Their comprehension check: restate the disclosure "in different words" or apply it to "hypothetical" events. Lines 181 to 183.
- **Not checked, absence.** No agent product in sections 3.1 and 3.2 describes a comprehension check. Only those pages were read.
- **Verified, secondary host.** EU AI Act Article 14(4): overseers must be able to "disregard, override or reverse the output". `RA/src/aiact_art14.txt` line 169. This applies to high-risk AI systems only.
- **Link.** Module 8 section 5.1: the screen text should be what the authorization server records as shown in the consent record. Module 9 section 4.3: a late answer must show "expired", not "approved".
- **Inferred.** A screen state list needs at least: pending, approved, declined, expired, and ran. Basis: Module 9's expired case and the OpenAI "did and did not run" rule. Check: no product source lists screen states. Gap 7.

### 4.8 The only published human catch rate on agent approval prompts is Module 7's coding study. For support agents, one field experiment reports human takeover, not approval. Browser click-through rates are browser data

- **Best evidence, link.** Module 7 section 5.1 owns the 1,053-tester study. People let 86.4 of 100 dangerous coding prompts through.
- **Verified. Preprint. Field data, not approval data.** Alibaba field experiment, arXiv 2605.14830. 647 workers, 680,676 chats, August 15 to 31, 2024. `SR/arxiv_2605.14830.txt` lines 249 to 253. Of 11,069 AI-eligible chats under supervision, 44.1% had algorithm-triggered technical escalations, 8.6% algorithm-triggered emotional escalations, and 12.3% human-initiated escalations. Lines 438 to 453.
- **The 65.0% figure.** It is the helper agent's sum of those three shares: 44.1 + 8.6 + 12.3 = 65.0. The paper does not print 65.0. The anchor check finds zero hits. The counts agree: 7,195 of 11,069 is 0.650. `D19/recompute.txt`. Teach it as "the three escalation types together cover 65.0% of supervised AI chats, our sum". Only the 12.3% is a human choice. The other 52.7 points were triggered by an algorithm.
- **Verified. Suggest level, not approval.** Brynjolfsson, Li and Raymond: support agents followed AI suggestions at an average adherence rate of 38%, interquartile range 23% to 50%. `SR/arxiv_2304.11771.txt` line 850.
- **Verified. Browser data.** Akhawe and Felt 2013, field telemetry on 25,405,944 warning impressions. Click-through for SSL warnings was 33.0% in Firefox beta and 70.2% in Chrome stable. Malware 7.2% and 23.2%. Phishing 9.1% and 18.0%. `W/akhawe.txt` lines 667 to 670 and 838 to 839.
- **Verified, do not cite. Preprint.** Wang et al., arXiv 2605.24309, say users "click through 90%+ of SSL warnings without reading them [4]". Reference [4] is "99% false positives: A qualitative study of {SOC} analysts". `RA/src/reframing_2605.24309.txt` lines 348 and 561. The cited paper studies security-operations alerts. Do not teach the 90%+ figure.
- **Verified. Preprint.** The same paper counts runtime approval in 15 of 21 production agent systems, as of April 2026. Lines 16 and 247.
- **Answer to the brief.** For agents, one published catch rate exists, in Module 7. For browser agents and support agents, none was found. Browser click-through ranges from 7.2% to 70.2% by warning type and browser. That range is browser data.

### 4.9 More prompts can mean less protection. Habituation and design effects are measured on browser and phone warnings, not on agents

- **Best evidence, verified. Lab fMRI on images of security warning dialogs, not browser data.** Anderson et al., CHI 2015: "a dramatic drop in the visual processing centers of the brain after only the second exposure to a warning". `W/anderson_chi.txt` line 25. Study 1 showed warning images next to images of general software applications in a scanner, lines 265 to 270. Study 2 used Chrome extension permission warnings with mouse tracking, line 443, and does not give this quote.
- **Verified. Browser data.** Akhawe and Felt: "Users clicked through 49% of untrusted issuer warning impressions within 1.7s". The authors call this "indicative of warning fatigue". `W/akhawe.txt` lines 1243 to 1246.
- **Verified. Phone data.** Vance et al., MIS Quarterly 2018, Android permission warnings over 15 weekdays. Adherence fell from 87% to 55% with a static design and from 87% to 76% with a polymorphic design. `W/vance_misq.txt` lines 1621 to 1627.
- **Verified. Browser data.** Felt et al. 2015: an opinionated design raised adherence from 30.9% to 58.3%. New text in the old design added "only 1.2%". Release adherence went from 37% on 24,747,395 impressions to 62% on 20,214,251. `W/felt2015.txt` lines 906 to 947.
- **Verified. Browser data, small lab sample.** Egelman et al. 2008, 60 participants. Phished: Firefox active warning 0 of 20, IE active 9 of 20, IE passive 9 of 10, control 9 of 10. `W/egelman.txt` lines 524 to 545.
- **Verified, mechanism only.** Böhme and Grossklags 2011: "Human attention is a scarce resource". `W/bohme_nspw.txt` line 15. Jenkins et al. 2016 propose "presenting the warning at low-DTI times", when the warning does not interrupt a task. `W/jenkins_isr.txt` lines 36 and 37. The decimals in the saved Jenkins text are garbled. Any Jenkins number is inferred and is not used.
- **Link.** Module 7 section 5.1 has the agent fatigue points, 17% early and 5% after 50 prompts. Those are the only agent fatigue numbers.
- **Inferred.** Rewording an agent prompt alone will change little, and a design change can change a lot. Basis: Felt 2015, browser data. Check: an A/B test of two agent approval screens with planted bad actions.

### 4.10 An approval step moves blame to the person even when it does not move risk. It is worse than no step when it replaces a check that catches more

- **Best evidence, verified.** Elish 2019: responsibility "may be misattributed to a human actor who had limited control". The zone protects the system "at the expense of the nearest human operator". `RA/src/elish_crumple.txt` lines 69 and 76.
- **Verified.** Green 2022 surveyed 41 human-oversight policies. People "are unable to perform the desired oversight functions". The policies let agencies "foist accountability" onto lower-level operators. `RA/src/green2022.txt` lines 24 to 26 and 175. Government algorithms, not agents.
- **Verified by run. Assumed inputs.** Lab A, policy C, confirm every write: 125.2 prompts a day, human catch 0.061. If that step replaced a check with catch 0.30, harm is 215.29 with the step against 160.51 without it. `RA/proto/run_output.txt`. Rule: take the person's catch rate at that volume times the visible share. The step is worse when that product is below the removed check's catch rate.
- **Verified. Vendor docs.** Codex `approvals_reviewer = "auto_review"` sends eligible requests "through a reviewer agent before Codex runs the request". "Prompt-build, review-session, and parse failures fail closed." `RA/src/codex_approvals.txt` lines 1112 and 1131. A machine approver moves no blame to a person. Its error rates are not published here. Module 7 section 5.1 owns classifier numbers.
- **Link.** Module 17 dossier 4.15: escalation is a safety control only when the pause comes before the side effect. It must also fail closed.

### 4.11 Experienced users leave per-action approval more often than new users, and interrupt more. A product that relies on per-action "yes" loses its control as users gain experience, so it needs a stop control

- **Best evidence, verified. Vendor number.** Anthropic, 2026-02-18: "Newer users (<50 sessions) employ full auto-approve roughly 20% of the time; by 750 sessions, this increases to over 40% of sessions". `RA/src/anthropic_autonomy.txt` line 89.
- **Conditions.** All interactive Claude Code usage for users who signed up after September 19, 2025. LOWESS smoothed. Log x-axis. Lines 92 and 95.
- **Verified.** Interrupts rise too: about 5% of turns at about 10 sessions, about 9% for experienced users. Line 93.
- **Verified, the authors' own limit.** "Claude Code's default settings push new users towards approval-based oversight". Footnote 9, line 264. So part of the shift is product design.
- **Verified.** Operator pauses on some sites "when the user becomes inactive or navigates away from the page". `RA/src/operator_system_card.txt` line 484.
- **Verified, secondary host.** AI Act Article 14(4) asks that overseers stay aware of "automatically relying or over-relying" on output, and can stop the system. `RA/src/aiact_art14.txt` lines 150 and 181. High-risk systems only.
- **Inferred.** Offer three controls, not one: per-action confirm, a visible running log, and a stop that works mid-batch. Basis: the interrupt data. Check: none published for agents.

### 4.12 "Confirm or auto" is not the whole choice. A published scale has suggest, confirm, veto window and act-then-inform, and no checked agent product ships the veto window

- **Best evidence, verified in a secondary reproduction.** Sheridan and Verplank 1978, levels 4 to 7, as reproduced by Save and Feuerberg 2012, Table 1. Level 5 "Executes that suggestion if the human approves". Level 6 allows "restricted veto time". Level 7 "Executes automatically, then necessarily informs". `RA/src/save_loat.txt` lines 80 to 86. The 1978 report was not fetched.
- **Verified. Preprint.** Feng, McDonald and Zhang 2025: five user roles, L1 operator to L5 observer. At L4 the agent engages the user "only in risky or pre-" specified scenarios. `RA/src/feng_levels.txt` line 39.
- **Verified.** Zendesk names "Actions in procedures that have a high agent acceptance rate" as candidates to move to pre-approved. `SR/zd_about_actions_autoassist.txt` line 194. So acceptance rate is used to move an action from confirm to auto. Zendesk files these under "High-confidence actions". Inferred: a high acceptance rate can also mean habituation, per 4.9. Check: plant bad actions and measure refusals before promotion. Link Module 12 section 4.4: user feedback finds failures but does not measure quality.
- **Verified. Vendor number.** Anthropic, "Piloting Claude in Chrome", 2025-08-25: "all red-teaming and safety evaluations were conducted in autonomous mode". `RA/src/claude_chrome.txt` lines 10 and 62. So its attack rates, 23.6% before and 11.2% after mitigations, on 123 test cases in 29 scenarios, measure the agent and classifiers, not the person. Lines 49 and 67. Module 16 section 3.1 owns how to read an attack success rate.
- **Not checked, absence.** No product page in sections 3.1 and 3.2 describes "run in N seconds unless the user cancels". Only those pages were read.
- **Mapping, inferred.** Suggest is level 4. Confirm is level 5. Codex `auto_review` is level 5 with a machine approver. Operator is L2 per Feng's footnote.

### 4.13 A model's stated confidence misses its accuracy by tens of points on hard questions. Frontier entries from September 2026 still miss by 20 to 51 points

- **Best evidence, verified.** Scale AI's HLE leaderboard, fetched 2026-09-25. 53 entries. RMS calibration error from 20% to 89%. GPT 6 Astra: accuracy 54.8%, error 39%. Fable 5.1 xhigh: 46.5%, 20%. GPT-4o November 2024: 2.72%, 89%. `RC/src/hle_scale_leaderboard_extract_2026-09-25.txt` lines 2, 3 and 54.
- **Conditions.** 2,500 expert questions. The model states a confidence from 0% to 100% with the SimpleQA-style setup. An o3-mini judge grades. Temperature 0.0 "when configurable". Scale AI runs the board and co-owns the benchmark. The page shows "Potential contamination warning" for models evaluated after HLE's public release.
- **Verified.** The metric has no sign. The page reads the gap as "strong evidence for confabulation/hallucination". That sentence describes the initial publication: errors "greater than 80%" with accuracy "less than 10%". It is not a statement about the September 2026 entries. `RC/src/scale.com_leaderboard_humanitys_last_exam.txt`, "Metrics". Inferred: at this accuracy the gap is overconfidence. Check: the mean confidence per model, which the extract does not hold.
- **Verified.** Scorer quirk: the HLE code loops `for i in range(len(bins) - 1):`, so the top bin is never summed. `RC/src/hle_run_judge_results_a590489.py` line 107. In the prototype's HLE-like case this moves the error from 0.636 to 0.610. The leaderboard page says it uses "the implementation from Hendrycks et al., 2022". The saved copy of that code, `RC/src/hendrycks_calibration_tools.py` line 14, has the same loop. Effect on the board: not checked.
- **Inferred.** A support agent on easy questions has higher accuracy, so its gap is likely smaller. Check: measure it on labelled support traffic. Gap 2.

### 4.14 A low ECE does not mean the score can gate anything. The gate needs ranking, so report AUROC or a risk-coverage curve next to ECE

- **Best evidence, verified.** Xiong et al., ICLR 2024, section 5.2: "GPT-4 with 93.6% accuracy achieves a near-optimal ECE 0.064 by assigning 100% confidence to all samples". `RC/src/2306.13063.txt` line 760.
- **Verified.** Tian et al. make the same point in a footnote: a binary system that "outputs 50% confidence each time has perfect ECE". `RC/src/2305.14975.txt` line 212.
- **Verified by run.** The confidence prototype's self-test reproduces ECE 0.064 and AUROC 0.5 for a constant score. `RC/runs/confidence_gate_2026-09-25.txt`.
- **Recomputed.** 1 − 0.936 = 0.064. `D19/recompute.txt`.
- **Use it.** A constant score passes all items or none. It cannot pick which to escalate.

### 4.15 Post-training breaks token-probability calibration. Asking for a number is often better but coarse and still overconfident. Sampling several answers ranks best and costs several calls

- **Best evidence, verified. Vendor number.** GPT-4 Technical Report, Figure 8: ECE 0.007 for the pre-trained model and 0.074 after post-training, on an MMLU subset with A/B/C/D log-probabilities. "The post-training hurts calibration significantly." `RC/src/2303.08774.txt` lines 776 to 798.
- **Verified.** Tian et al., Table 1, gpt-3.5-turbo: TriviaQA ECE 0.140 for label probability and 0.068 for verbalized top-1. SciQ 0.256 and 0.234. TruthfulQA 0.451 and 0.389. Tian's ECE is "the average (squared) error" per bin, line 197. It is not comparable with Guo's absolute gap.
- **Recomputed, and corrected by the reviewer.** Label probability against verbalized 1S top-1 gives relative cuts of 51.4%, 8.6% and 13.7%. `D19/recompute.txt`. But top-1 is the weakest one-stage verbalized method in Table 1. Verbalized 1S top-4 has ECE 0.054, 0.065 and 0.203, which are cuts of 61.4%, 74.6% and 55.0%. The best row per dataset cuts 66% to 75%. `RC/src/2305.14975.txt` lines 215 to 385. So the abstract's "often reducing the expected calibration error by a relative 50%" holds on all three datasets for gpt-3.5-turbo, with the better prompts. It does not hold for top-1 on SciQ and TruthfulQA. Two two-stage prompts, 2S CoT and 2S top-1, are worse than label probability on SciQ. Teach: the prompt choice decides the gain. Recomputed by the reviewer for all nine verbalized rows.
- **Verified.** Xiong: verbalized confidences "predominantly fall within the 80% to 100% range" in multiples of 5. Line 80. A threshold can land on only a few values.
- **Verified by the reviewer.** Xiong Table 3, GPT-3.5, average over five datasets: Self-Random sampling with 5 responses and consistency gave AUROC 73.0. One CoT response gave 56.4. `RC/src/2306.13063.txt` lines 765 to 840.
- **Verified. Preprint, on the authors' own models.** Kadavath et al.: the 52B pre-trained model "is very well-calibrated except near the tails". Temperature T = 2.5 fixes the RLHF policy on three evals. But heavier RL may distort calibration in ways that "cannot be remedied in this way". `RC/src/2207.05221.txt` lines 654, 741 and 752.
- **Verified.** Kapoor et al. abstract: "prompting on its own is insufficient", and "a thousand graded examples are sufficient to outperform baseline methods". `RC/src/abs_2406.08391.html`.

### 4.16 A threshold picked on labelled data holds only for traffic like that data. Conformal risk control bounds the mean, not each deployment, and a concept shift leaves the escalation rate flat

- **Best evidence, verified by run.** Confidence prototype section 4. The threshold stays fixed. A new topic lowers the chance of being right at every confidence. The unreviewed error per request rises from 0.0426 to 0.1022. The escalation rate stayed at 0.651 against 0.653. `RC/runs/confidence_gate_2026-09-25.txt`. Synthetic data.
- **Verified.** CRC needs exchangeable losses, and "if the risk is non-monotone, then this algorithm does not control the risk". `RC/src/2208.02814.txt` lines 84 and 122.
- **Verified.** Kumar et al., LLaMA-13B on MMLU, α = 0.1. Calibrated on "high school computer science" and tested on "business ethics", coverage "is only around 83%, less than the desired 90%". The same passage says subjects from similar domains hold up better. So this is one pair of distant subjects, not every cross-subject pair. `RC/src/2305.18404.txt` lines 670 to 674.
- **Verified.** Angelopoulos and Bates: "in the most general case, conditional coverage is impossible to achieve". `RC/src/2107.07511.txt` line 707. Inferred: the average error can meet the target while one customer segment gets most errors.
- **Verified by the reviewer.** CRC's promise is "in expectation", over calibration draws. Learn then Test, LTT, gives a bound that holds "with probability 1 − δ" instead. It is "capable of controlling general risks" that are not monotone. Angelopoulos and Bates, `RC/src/2107.07511.txt` lines 1121 to 1122, 1634 to 1637, and 2356 to 2363 in Appendix A. Inferred: a team that needs "no more than 5% error on this deployment, with 95% confidence" needs LTT, not CRC. The 35.8% of splits above α in the next bullet shows why. The original LTT paper was not fetched.
- **Verified by run.** 500 random splits, 200 calibration items, α = 0.05. CRC's mean test error was 0.0474. Still, 35.8% of splits exceeded 0.05. The naive rule averaged 0.0522 and exceeded it in 52.2%.
- **Verified.** Amazon A2I sends a share of items to people "regardless of inference confidence scores", to "Audit your ML model by randomly sampling". `RC/src/vendor/a2i_textract.txt`. The same page says "Amazon SageMaker A2I is no longer open to new customers". So this is a documented design, not a product a team can adopt today. Inferred: a random review sample gives the labels that detect the shift above.
- **Two targets, inferred.** Unreviewed error per request is monotone in the threshold, so CRC applies. Error among auto actions is not monotone. It needs another method, such as Learn then Test, described above from the tutorial.

### 4.17 Recalibrating a score with a monotone map does not change which items pass the gate

- **Best evidence, verified by run.** Confidence prototype section 5. Platt scaling moved test ECE from 0.173 to 0.019. AUROC stayed at 0.701. At α = 0.02 the auto rate stayed at 0.205. Histogram binning cut AUROC to 0.671 and the auto rate to 0.000. `RC/runs/confidence_gate_2026-09-25.txt`.
- **Inferred.** It follows for any strictly increasing map, because the gate depends only on order. Check: Platt-scale real verbalized confidences and compare risk-coverage curves.
- **Verified by run.** At α = 0.05 on that one split, the test error was 0.0616, above the target. This is consistent with 4.16. CRC bounds the mean over splits.
- **Use it.** Recalibrate to make the number honest for people who read it. Do not expect it to change automation.

### 4.18 The threshold comes from the cost of a wrong action, not from a round number. Act only when p > k/(1+k), and only with p calibrated on your traffic

- **Best evidence, verified. Preprint.** Kalai et al., arXiv 2509.04664 v1: "Answer only if you are > t confident, since mistakes are penalized t/(1 −t) points". `RC/src/2509.04664.txt` line 703.
- **Recomputed. The paper has two slips.** It says "t = 0.75 (penalty 2)". The formula gives 0.75 ÷ 0.25 = 3. Line 705. It says IDK is optimal where the correctness probability "is greater than the" target. Lines 785 to 786. The expected score of answering is p − (1 − p) × t/(1 − t). It is zero at p = t and positive above it. So IDK is optimal below t. `D19/recompute.txt`. The prototype self-test checks both.
- **Inferred.** If a wrong action costs k times the value of a right one, act only when p > k/(1+k). With k = 3, the bar is 0.75. With k = 9, it is 0.9.
- **Verified by run.** Taken at face value, "act if confidence ≥ 0.95" gave 12.1% error among auto actions on the prototype's overconfident model. The score promised at most 5%. `RC/runs/confidence_gate_2026-09-25.txt`. Synthetic miscalibration.

### 4.19 Shipped products document confidence thresholds for intent classifiers and extraction models. None of the pages checked documents a threshold on an LLM's own answer confidence

- **Best evidence, verified.** Rasa 3.6.21: `DEFAULT_NLU_FALLBACK_THRESHOLD = 0.3`. `RC/src/vendor/rasa_core_constants_3.6.21.py` line 11.
- **Verified.** Dialogflow CX: "the minimum intent detection confidence required for an intent match". Lex V2: `nluIntentConfidenceThreshold`. Defaults not stated on either page. `RC/src/vendor/`.
- **Verified. Vendor claim, not tested.** Azure Document Intelligence: confidence can decide "whether to automatically accept the prediction or flag it for human review". It reads 0.95 as "19 out of 20". `RC/src/vendor/azure_di_confidence.txt`.
- **Verified.** Intercom Fin checks "enough confidence in the response" and escalates if not. It publishes no number. `RC/src/vendor/intercom_fin_engine.txt`.
- **Not checked.** Zendesk's confidence-threshold article redirects to a sign-in page. A search snippet said 60. Not taught.
- **Inferred.** This is not proof that no LLM product has a threshold. Only Intercom Fin was checked among LLM support products. Gap 5.

---

## 5. Numbers, with their conditions

### 5.1 Agent confirmation, vendor numbers

| Number | What it measures | Conditions | Source |
|---|---|---|---|
| 91.0% | ChatGPT agent asks when it should | Sample not printed. Card calls it an underestimate | Table 13 |
| 90.8%, 92.1% | Operator 4o, Operator o3 | Same table | Table 13 |
| 100.0%, 99.9%, 100.0% | Critical recall: permissions, high-stakes messages, payments | Sample not printed | Table 13 |
| 92% | Operator asks when it should | 607 tasks, 20 categories | Operator 4.3 |
| 13 of 100 | Unmitigated Operator errors | 8 reversible within minutes, 5 not | Operator 4.2 |
| about 90% | Risk reduction from confirmations | No method given | Operator 4.2 |
| 23.6% to 11.2% | Claude in Chrome attack success | 123 cases, 29 scenarios, autonomous mode, post dated 2025-08-25. See 5.6 on the denominator | `claude_chrome.txt` lines 49, 67 |
| 15 of 21 | Production agent systems with runtime approval | Wang et al., April 2026 corpus | line 247 |

### 5.2 Agent and support field numbers

| Number | Conditions | Source |
|---|---|---|
| 20% to over 40% | Claude Code sessions with full auto-approve, from under 50 to 750 sessions of tenure. Users who signed up after 2025-09-19 | Anthropic 2026-02-18 |
| 5% to about 9% | Turns interrupted, from about 10 sessions to experienced users | Same |
| 44.1%, 8.6%, 12.3% | Alibaba: technical, emotional and human-initiated escalations among 11,069 supervised AI chats. 4,879, 954 and 1,362 chats. August 2024. 302 treated workers. Preprint | arXiv 2605.14830 lines 438 to 453 |
| 65.0% | Helper's sum of the three rows above. Not printed in the paper | `D19/recompute.txt` |
| 38%, IQR 23% to 50% | Support agents following AI suggestions | arXiv 2304.11771 line 850 |

### 5.3 Browser and phone warning numbers. Browser data, not agent data

| Number | Conditions | Source |
|---|---|---|
| SSL click-through 33.0% Firefox, 70.2% Chrome | Field telemetry, 25,405,944 impressions. The summary says May and June 2013. The Firefox SSL data ran June 1 to July 5, 2013, `W/akhawe.txt` lines 576 to 582 | Akhawe and Felt |
| Malware 7.2% and 23.2%, phishing 9.1% and 18.0% | Same, stable channels | Akhawe and Felt |
| 49% within 1.7 s | Untrusted issuer warnings | Akhawe and Felt |
| 30.9% to 58.3% adherence | Chrome field experiment, opinionated design | Felt et al. 2015 |
| +1.2% | New text in the old design | Felt et al. 2015 |
| 37% to 62% | Chrome release adherence, 24,747,395 then 20,214,251 impressions | Felt et al. 2015 |
| 87% to 55%, 87% to 76% | Android permission adherence, static against polymorphic, 15 weekdays | Vance et al. 2018 |
| 0 of 20, 9 of 20, 9 of 10, 9 of 10 | Phished: Firefox active, IE active, IE passive, control. 60 participants, lab | Egelman et al. 2008 |
| 17% | Paid attention to permissions during install. Phone data. Not the same number as Module 7's 17% early catch | Felt et al. 2012 |

### 5.4 Confidence and calibration numbers

| Number | Conditions | Source |
|---|---|---|
| 20% to 89% RMS error | HLE, 53 leaderboard entries, 2026-09-25 | Scale AI |
| 2.7% accuracy, 89% error | GPT-4o in HLE paper Table 1, pre-release | arXiv 2501.14249 |
| ECE 0.007 to 0.074 | GPT-4 pre-trained to post-trained, MMLU subset, logprob | GPT-4 report Fig. 8 |
| ECE 0.064, AUROC 0.5 | GPT-4 CoT on GSM8K, 93.6% accuracy, constant 100% confidence | Xiong 5.2 |
| 0.140 to 0.068 | gpt-3.5-turbo TriviaQA, label probability to verbalized 1S top-1, squared-gap ECE | Tian Table 1 |
| 0.140, 0.256, 0.451 to 0.054, 0.065, 0.203 | Same model, TriviaQA, SciQ, TruthfulQA, label probability to verbalized 1S top-4. Cuts 61.4%, 74.6%, 55.0% | Tian Table 1, reviewer recompute |
| 83% against 90% | LLaMA-13B MMLU, cross-subject conformal coverage | Kumar 4.3 |
| ECE 0.37 to 0.03, 0.26 to 0.10 | Qwen2.5-7B, HotpotQA and math, RLVR to RLCR, in-domain problems only, `RC/src/2507.16806.txt` lines 122 to 124 | Damani et al. |
| 0.3 | Rasa fallback threshold default, 3.6.21 | Rasa code |

### 5.5 Prototype numbers

| Script | Case | Result | Output |
|---|---|---|---|
| `approval_policy_sim.py` | Attentive approver, assumed c0 0.90, floor 0.05, half 20 prompts a day | A auto 229.30. B confirm all 217.83. C confirm writes 215.29. D confirm irreversible 62.14. E D plus block delete 14.00 harm a day | `RA/proto/run_output.txt` |
| same | Worse than no step, policy C | Removed check 0.30: 160.51 without the step against 215.29 with it | same |
| same | Tool-name-only screen, visible 0.1 | D rises to 212.58, 95.6% blamed | same |
| same | Module 7 anchor, c0 0.17 | D 196.25. E 26.28. Unit caveat: Module 7's 17% and 5% are per prior prompt in one session. The simulator's curve runs on prompts per day. The mapping is an assumption | same |
| `confidence_gate.py` | Planted model, 6,000 items, seed 7 | Accuracy 0.727, mean confidence 0.885, ECE 0.158, AUROC 0.706 | `RC/runs/confidence_gate_2026-09-25.txt` |
| same | α 0.05, 1,000 calibration items, 5,000 test | Threshold 0.95. Test unreviewed error 0.0428. Escalate 0.645. Error among auto 0.1207 | same |
| same | 500 splits, 200 calibration items | CRC mean 0.0474, 35.8% of splits above α. Naive 0.0522, 52.2% | same |
| same | Shift | New topic: 0.1022 at escalate 0.651. Harder questions: 0.0080 at escalate 0.942 | same |
| same | Recalibration | Platt ECE 0.173 to 0.019, AUROC 0.701 kept | same |
| same | HLE-like case | 0.610 HLE code, 0.636 all bins, 0.614 ECE | same |

All prototype inputs are assumptions or synthetic data. They show mechanisms. They do not predict a real product.

### 5.6 Arithmetic recomputed

All from `D19/recompute.txt`.

| Claim | Report value | Recomputed | Result |
|---|---|---|---|
| Alibaba human takeover | "65.0%", not found by the approval report | 44.1 + 8.6 + 12.3 = 65.0. 7,195 of 11,069 = 0.650 | A sum, not a printed figure. Changed in 4.8 |
| Alibaba no-escalation share | 35.0% | 3,874 ÷ 11,069 = 0.350 | Holds |
| Alibaba workers | 647, 53.3% control | 345 + 302 = 647. 345 ÷ 647 = 0.533 | Holds |
| Operator errors | 13 = 8 + 5 | 13 | Holds |
| Egelman participants | 60 | 20 + 20 + 10 + 10 = 60. 9 ÷ 20 = 45% | Holds |
| Felt 2015 design gain | 27 points | 27.4 | Holds |
| Vance end gap | 21 percent | 76 − 55 = 21 | Holds |
| Lab D catch inputs. The report calls it Lab 3. Browser data | 0.298 and 0.670 | 1 − 0.702 and 1 − 0.330 | Holds |
| Claude in Chrome 11.2% of 123 | not stated | 13.78 cases. 23.6% of 123 is 29.03, so 29 cases. Not an integer. 13 and 14 give 10.6% and 11.4% | Inferred: 11.2% is not a count over the same 123 cases. Changed in 5.1 |
| Runtime approval share | 15 of 21 | 71.4% | Holds |
| Sim row A | 229.3 | 0.3 + 20 + 9 + 200 = 229.3 | Holds |
| Sim prompts, policies B and C | 425.2, 125.2 | 425.2, 125.2 | Holds |
| Sim catch at 5.2 | 0.760 | 0.7598 | Holds |
| Sim row D | 62.14 | 62.14. Blamed share 0.850 | Holds |
| Sim catch at 125.2 | 0.061 | 0.0611 | Holds |
| Worse-than-no-step, k 0.30 | 160.51 | 229.3 × 0.7 = 160.51 | Holds |
| Tool-name-only screen | 212.58 | 212.58 | Holds |
| Module 7 anchor D and E | 196.25, 26.28 | 196.25, 26.28 | Holds |
| Self-test hand case | 0.475, 52.5 | 0.475, 52.5 | Holds |
| HLE rows, range | 53, 20 to 89 | 53, 20 to 89 | Holds |
| Xiong constant ECE | 0.064 | 1 − 0.936 = 0.064 | Holds |
| Tian "relative 50%" | stated for all three | 51.4%, 8.6%, 13.7% against 1S top-1. Reviewer: 61.4%, 74.6%, 55.0% against 1S top-4 | Arithmetic holds. The dossier's "TriviaQA only" was wrong: it compared only the weakest one-stage prompt. Corrected in 4.15 |
| Kalai penalty at t = 0.75 | paper says 2 | 3 | Paper slip. Holds as flagged |
| Kalai break-even | paper says IDK above target | Zero at p = t, positive above | Paper slip. Holds as flagged |
| CRC term at n = 50 | 0.0196 | 1 ÷ 51 = 0.0196 | Holds |
| Kumar shortfall | not stated | 7 points | Added |
| Proto shift ratio | not stated | 0.1022 ÷ 0.0426 = 2.4x | Added |
| Proto Platt at α 0.05 | not stated by the report | 0.0616, 0.0116 above target | Added in 4.17 |

---

## 6. Lab designs

The learner has an Apple Silicon Mac with 14 cores and 26 GB RAM. It has no Docker and no GPU except MPS. Labs use no API keys.

### 6.1 Built and run on 2026-09-25

| Lab | Script | Output | Runs where | Cost | Self-test | Proves |
|---|---|---|---|---|---|---|
| A. Approval-policy simulator | `RA/proto/approval_policy_sim.py --anchor-m7` | `RA/proto/run_output.txt` | Laptop, offline, standard library | 0.04 s. No download | 9 checks on a hand-worked one-class case. Re-run by the dossier author: 9 passed | 4.5, 4.10, and the direction of 4.9 |
| B. Confidence gate | `RC/proto/confidence_gate.py` | `RC/runs/confidence_gate_2026-09-25.txt` | Laptop, offline, standard library | 2.57 s. No download | 8 hand-worked checks with `--selftest`. Re-run: passed | 4.13 to 4.18 |

**Break-it variants.** Lab A: set `visible` to 0.1 for a tool-name-only screen. Anchor the approver at Module 7's 0.17. Lab B: change `0.8 * p` to `0.6 * p` in section 4 and watch unreviewed error rise with a flat escalation rate. Then add a 5% random review sample and show it detects the change. Set `N3_CAL = 50` and watch the B/(n+1) term, 0.0196, raise escalation.

### 6.2 Designed, not built

| Lab | What it prints | Runs where, costs what | Proves |
|---|---|---|---|
| C. Approval-request linter | Which of the nine rows in 4.5 an approval request can fill. Input: an OpenAI SDK interruption, a LangChain action request, a Gemini `safety_decision`. Break-it: the Gemini request fails rows 1, 2 and 5. Self-test: a full request passes, a name-only request fails 8 of 9 | Laptop, standard library, under 1 s. Pinned `openai-agents==0.22.3` and `langchain==1.4.2` only to build real request objects. Download size not checked | 4.5, 4.6 |
| D. Habituation replay | Lab A policy D with fixed catch rates 0.298 and 0.670 from Akhawe and Felt | Laptop, under 1 s. Label the inputs browser data | 4.9 |
| E. Cost to threshold | Pick α from the cost of a wrong refund and of a review. Compare the Kalai break-even with a CRC threshold on a miscalibrated score | Laptop, seconds | 4.18 |
| F. Real verbalized confidence. Optional, UNVERIFIED | ECE and AUROC on 500 SimpleQA questions with the SimpleQA confidence prompt | Needs a hosted model and a key. About 500 calls of about 150 tokens. Prices not fetched today, so no cost estimate. An offline variant with a local small model is not checked | 4.13, 4.15 |

### 6.3 The module lab, proposed

A refund-support agent with six action classes and a screen. Proposal, not built.

1. Reuse Lab A's six classes: read, edit, draft, send, refund, delete.
2. A policy file maps each class to alone, confirm, hand-off or block. It uses the two questions of 4.3.
3. The agent emits approval requests. Lab C checks each against the nine rows of 4.5.
4. A confidence gate from Lab B decides when the refund class may skip the person. It keeps a 5% random review sample.
5. A planted-fault generator puts known bad refunds and sends into the stream. A scripted approver has a catch rate that falls with prompts per day. The curve is an assumption, labelled as such.
6. It prints per policy: prompts a day, planted faults refused, harm a day and harm that carried a "yes". It also prints whether the random sample flagged a shift.
7. Break-its: remove the payload from the screen. Promote the refund class on acceptance rate alone. Shift the topic mix.
8. Self-test: one hand-counted day of 100 actions.

Inferred: offline, standard library, seconds. Not measured.

---

## 7. Conflicts resolved

| Conflict | Sources | Evidence used | Resolution |
|---|---|---|---|
| a. The 65.0% human takeover from arXiv 2605.14830 | Coordinator note and helper against the approval report, which found no 65.0 | Lines 438 to 453 give 44.1%, 8.6% and 12.3%. The anchor check finds zero hits for "65.0" | 65.0 is the helper's sum of three escalation shares. Only 12.3% is human-initiated. Teach it as a labelled sum or leave it out. 4.8 |
| b. The approval report's "0.654 near line 1196" | Approval report 2.1b | Not used. The sum in a above explains the lead. Reviewer: `SR/arxiv_2605.14830.txt` lines 1190 to 1200 show 0.654 as a table cell in the technical-escalation row, 4,879 chats, with an interval 0.647 to 0.662. It is not a share of chats | Drop the 0.654 lead |
| c. "Users click through 90%+ of SSL warnings" | arXiv 2605.24309 against its reference [4] | Line 561: the reference is a study of SOC analyst alerts | Do not cite. Use Akhawe and Felt, labelled browser data. 4.8 |
| d. Operator "about 90% risk reduction" against Module 7's 13.6% catch | Operator card against Module 7 5.1 | Operator gives no method. Module 7 measured people | They measure different things. The 90% counts a confirmation as a catch. 4.1 |
| e. "Reads run alone, writes need review" | Module brief and Zendesk against the OpenAI guide | Zendesk lines 189 to 193. OpenAI lets uploads run on pre-approval and hands off password changes | The published axis is reversibility and outside effect. Read against write is Zendesk's approximation. 4.3 |
| f. Tian's "relative 50%" | Tian abstract against Tian Table 1 for gpt-3.5-turbo | Recomputed cuts 51.4%, 8.6%, 13.7% for 1S top-1. Reviewer: 61.4%, 74.6%, 55.0% for 1S top-4, and 66% to 75% for the best row per dataset | Corrected by the reviewer. The abstract holds on all three datasets with the better prompts. The old resolution, "TriviaQA only", compared one weak prompt. Teach "about half or more, with the right prompt". 4.15 |
| g. Verbalized against token probability against trained probes | Tian, Kapoor, Kadavath | Tian compared prompts without training. Kapoor trained on about 1,000 labels. Kadavath fitted one temperature on one in-house model | The crux is whether you have labels to train or recalibrate. With about 1,000 labels, the learned route wins in Kapoor's setting |
| h. Does RL help or hurt calibration | GPT-4 and Leng against Yoon, and RLCR | GPT-4 Fig. 8. Yoon 33 of 36. RLCR lines 122 to 124 | Reasoning text lets a model revise its stated confidence. The reward shape decides the incentive to guess. Both hold. Not taught beyond 4.15 |
| i. "Calibration" in Module 11 against this module | Module 11 Phase 3 line 64 | Module 11 uses "calibration set" for held-out human labels | Two meanings. Say so once in the lesson |
| j. Module 14 "cascade thresholds 0.96 and 0.37" | Confidence report 0 against the Module 14 dossier | The numbers are in `S/reports/research_ai-finops_cascades.md` line 98, not in the Module 14 dossier or its built phases | Link Module 1 section 3.4 and Module 14 Phase 3 for cascades. Do not cite the thresholds as a Module 14 fact |
| k. Claude in Chrome 11.2% on 123 cases | Blog lines 49 and 67 | 11.2% of 123 is 13.78 cases | The 11.2% is not a count over the same 123 cases, or it averages runs. Inferred. Teach the two rates with "autonomous mode" and this note |
| l. Jenkins et al. 2016 numbers | Warn helper against the saved text | The saved text has garbled decimals | Numbers inferred and not used. The timing mechanism is verified from the abstract. 4.9 |
| m. Böhme and Grossklags quote "not re-checked" | Approval report | `W/bohme_nspw.txt` line 15, "Human attention is a scarce resource" | Verified by the dossier author |

---

## 8. Gap list, ranked by what the module question needs

| Rank | Gap | Why the module question needs it | What was done |
|---|---|---|---|
| 1 | A human catch rate on browser-agent or support-agent confirmations, with the screen shown | "For the approval to mean anything" needs a catch rate on a real screen. Only Module 7's coding study exists | None found. The module lab, 6.3, uses an assumed curve |
| 2 | Calibration gap on support-style traffic | 4.13 is on hard expert questions. A support gate needs the gap at high accuracy | None found. Lab F would measure it |
| 3 | A screen A/B test with planted faults, for agents | 4.9's design effect is browser data | None found |
| 4 | Plan-level against action-level review for agents | Promised to Module 7. Only the 39% and 3% vendor numbers | Not researched further |
| 5 | A shipped LLM product with a documented numeric confidence threshold | 4.19 found thresholds only on classifiers | Only Intercom Fin checked. Agentforce, Sierra, Decagon, Google Agent Assist and Amazon Q in Connect not checked |
| 6 | The veto window, Sheridan level 6, for agents | 4.12 shows it is absent. No evidence on whether it works | None found |
| 7 | Screen states, including "expired" | Promised to Module 9 line 553 | Partly closed. No product source shows a full state list. 4.7 infers one. Intercom Fin's Slack notification shows "Resolved" and "Expired" states and uses a first-answer-wins rule, from the Intercom help article "Human-in-the-loop approvals for Fin Procedures", found by the Phase 2 writer |
| 8 | Whether read-only tools leak in practice | 4.3 infers that some reads are outside effects | Not checked |
| 9 | Comprehension checks on approval screens | 4.7 shows none in products | Not researched |
| 10 | Learn then Test for error among auto actions | 4.16 names it as the method for the non-monotone target and for a per-deployment bound | Partly closed by the reviewer: the tutorial's Appendix A describes it. The original paper and a worked number were not fetched |
| 11 | What Salesforce's confirmation screen shows | 4.2 knows only the switch | Not checked |
| 12 | Human review latency and price per approval | Cost of confirm against auto | No source |
| 13 | A screen that marks which arguments came from outside content | 4.5 row 9, promised by Module 16 line 317 | No product source found. Only the Module 16 design rule |
| 14 | What the Claude Agent SDK does in `default` mode when the app sets no `canUseTool` callback | 4.2 names this SDK as the one default that asks | Not checked. Check: run a query with no callback and a write tool |
| 15 | Measured effect of a model approver, such as `auto` mode or `auto_review`, on a planted-fault set | 4.2 and 4.10 | Module 7 section 5.1 has the only classifier numbers. None for support agents |

---

## 9. Things not verified

From both reports and from this dossier. Each item has the check that would settle it.

**Approval report.**

1. Parasuraman, Sheridan and Wickens 2000 original. IEEE returned HTTP 202 with an empty body. Check: an author copy.
2. Sheridan and Verplank 1978 original. Only the 2012 reproduction was read. Check: the MIT report.
3. Whether OpenAI removed `pending_safety_checks`. Zero hits on the guide. A guessed migration URL returned 404. Check: the Responses API reference.
4. Sample sizes behind ChatGPT agent critical confirmation recall. Check: none in the card.
5. How Operator computed "approximately 90%". Check: none in the card.
6. Resolved by the reviewer. The Claude in Chrome post is dated August 25, 2025, `RA/src/claude_chrome.txt` line 10.
7. The AI Act text on EUR-Lex. Only the FLI host was read.
8. Any published human catch rate on browser-agent or support-agent confirmations. Gap 1.
9. The Codex latest release tag. The GitHub API failed.
10. Every catch-rate curve value in Lab A. Assumed.
11. Jenkins et al. 2016 numbers. Garbled. Check: open the PDF in a viewer.
12. Böhme and Köpsell, CHI 2010. Not fetched.
13. Sunshine et al. 2009 Table 5. Saved in `W/sunshine.txt`, not re-checked.
14. The Salesforce confirmation screen contents.
15. Helper claims that the approval report did not use. Examples: Zendesk "actions cannot be edited", and no Intercom diff or amount field. Check: the saved pages.
16. Whether a newer MCP spec changed the Tools security text. Check: the 2026-07-28 spec that Module 6 cites.

**Confidence report.**

17. Zendesk default confidence threshold. Sign-in wall.
18. Defaults for Dialogflow CX and Lex V2 thresholds.
19. Any shipped LLM support product with a numeric threshold, beyond Intercom Fin.
20. How much the HLE skipped top bin changes the published board. Check: rerun the scorer on released predictions.
21. The GPT-4 snapshot in Xiong et al. and per-model numbers in Yoon et al.
22. Venues for Geifman 2017, Mohri 2024, Abbasi-Yadkori 2024 and Barber 2022.
23. Numbers inside Mohri and Abbasi-Yadkori beyond their abstracts.
24. Learn-then-Test. Not fetched.
25. Prices for Lab F. Not fetched.
26. That weighted conformal methods fail under concept shift. Inferred from assumptions.
27. Whether Kalai et al.'s slips are fixed. Only v1 exists.
28. That a monotone recalibration leaves a gate unchanged on real scores. Synthetic only.

**This dossier.**

29. Resolved by the reviewer. Xiong Table 3 AUROC values, 73.0 and 56.4, are at `RC/src/2306.13063.txt` lines 765 to 840.
30. The Claude in Chrome denominator for 11.2%. Inferred from arithmetic, conflict k.
31. The helper's 65.0% sum is arithmetic on printed shares. The paper may report a different takeover definition elsewhere. Check: read section 5 in full.
32. Whether Copilot Studio's description shows any argument values. Check: build a tool.
33. The Module 14 cascade thresholds are in a research report only, conflict j. The built Module 14 phases were grepped for "threshold" and "cascade" only.
34. Whether the Egelman "phished" column counts entered data, as its caption says. Read from the caption at `W/egelman.txt` line 543, not from the method section. The reviewer confirmed the caption says "entered personal information on at least one phishing website". The method section is still not read.
35. Added by the reviewer. The saved `RC/src/hendrycks_calibration_tools.py` has the same loop, `for i in range(len(bins) - 1):`, at line 14. The source URL of that saved file was not checked. The effect on the published board is still not checked.

---

## 10. Review log

Review on 2026-09-25 by an independent reviewer who did not write the dossier. `R/` is the reviewer folder named in 3.1.

### 10.1 What the reviewer checked

- **Anchors.** More than 50 anchors were read at their cited lines in the saved files, with context. The exact count was not kept. That covers every "Best evidence" line in 4.1 to 4.19. It also covers the ChatGPT agent Table 13, the Operator card, the SDK sources, MCP, the OpenAI guide, Zendesk, Intercom, Salesforce, The Register, Alibaba, the browser papers, HLE, Tian, Xiong, CRC, Kumar, Kalai, A2I and Rasa. All matched except the 7 listed in 10.3.
- **Re-fetched today.** Three docs pages, all HTTP 200 at 2026-09-25 03:25 UTC: OpenAI Agents SDK "Human-in-the-loop", Claude Agent SDK "Configure permissions", LangGraph "Interrupts". PyPI and npm JSON for `openai-agents`, `langchain`, `langgraph` and `ai`. Files in `R/`.
- **Self-tests.** `approval_policy_sim.py --selftest` printed "selftest: 9 checks passed". `confidence_gate.py --selftest` printed "SELF-TEST PASSED". Python 3.9.6, the learner's Mac, 2026-09-25.
- **Arithmetic.** Recomputed by hand or in Python: 44.1 + 8.6 + 12.3 = 65.0, and 4,879 + 954 + 1,362 = 7,195, 7,195 ÷ 11,069 = 0.650. Tian cuts 51.4%, 8.6%, 13.7% hold as arithmetic. 11.2% of 123 = 13.78 and 23.6% of 123 = 29.03. k/(1+k) gives 0.5, 0.75 and 0.9 for k = 1, 3, 9. Kalai t/(1 − t) at 0.75 is 3. Simulator catch curve: 0.05 + 0.85 × 2^(−5.2/20) = 0.760 and at 125.2 prompts 0.061. 229.3 × 0.7 = 160.51. 52.84 ÷ 62.14 = 85.0%. 203.28 ÷ 212.58 = 95.6%. Shift ratio 0.1022 ÷ 0.0426 = 2.4. All prototype numbers in 4.5, 4.10, 4.14, 4.16 to 4.18 and 5.5 match `RA/proto/run_output.txt` and `RC/runs/confidence_gate_2026-09-25.txt`.
- **Conflicts a to m.** a, c, d, e, g, i, j, k, l and m hold. b holds, with the 0.654 cell now identified. f was wrong and is corrected. h holds. The RLCR figures are now marked in-domain.
- **Overlap.** `grep '^## '` on the seven built folders named in the review brief. Module 7 5.1 to 5.3, Module 9 4.1 to 4.3, Module 11 3.1 and 4.4, Module 1 3.4 and Module 14 3.1 to 3.4 are linked correctly. Modules 12 and 16 had missing links. See 10.2.

### 10.2 Corrections

| # | Kind | Where | Was | Now | Evidence |
|---|---|---|---|---|---|
| 1 | Wrong conclusion, serious | 4.15, 5.4, 5.6, 7f | Tian's "relative 50%" holds "for TriviaQA on this model only" | Holds on all three datasets with 1S top-4: 61.4%, 74.6%, 55.0%. The old check compared only 1S top-1, the weakest one-stage prompt | `RC/src/2305.14975.txt` lines 215 to 385, Table 1 |
| 2 | Missing framework default, serious | 1, 2.1, 3.1, 4.2 | "The default in the frameworks and products checked is to run without asking." Claude Agent SDK and LangGraph not covered | The Claude Agent SDK `default` mode sends calls that need approval to the callback. It is the exception. LangChain middleware auto-approves unlisted tools. LangGraph `interrupt()` is opt-in and waits indefinitely | `R/claude_sdk_perms.txt`, `SR/lc_hitl_src_1.4.2.py` line 257, `R/lg_interrupts.txt` |
| 3 | Wrong date and name | 3.2, 3.4, 4.12, 5.1, 5.6, 7k, 9 item 6 | "Claude for Chrome", "Original date not in the saved text" | "Piloting Claude in Chrome", dated 2025-08-25 | `RA/src/claude_chrome.txt` lines 1 and 10 |
| 4 | Missing vendor label | 4.12, 4.15 | Claude in Chrome rates and GPT-4 Figure 8 labelled only "verified" | "Vendor number" | Same files |
| 5 | Missing preprint label | 3.3, 4.8, 4.12, 4.15, 4.18, 5.2 | Alibaba, Wang, Feng, Kadavath and Kalai lines had no status in section 4 | "Preprint" added. Brynjolfsson, CRC and the conformal tutorial marked "venue not checked" | `research-method.md` labelling rule |
| 6 | Quote out of context | 4.13 | The leaderboard reads the gap as "strong evidence for confabulation" | That sentence describes the initial publication, errors above 80% at accuracy below 10% | `RC/src/scale.com_leaderboard_humanitys_last_exam.txt`, "Metrics" |
| 7 | Missing condition | 4.16 | Kumar: calibrated on one subject, tested on another, 83% | One named pair, high school computer science to business ethics. Similar subjects hold up better | `RC/src/2305.18404.txt` lines 670 to 674 |
| 8 | Missing concept | 4.16, 8 gap 10 | CRC bounds the mean. LTT "not fetched" | LTT gives a 1 − δ bound and handles non-monotone risk. Described in the saved tutorial, Appendix A | `RC/src/2107.07511.txt` lines 1121, 1634, 2356 to 2363 |
| 9 | Missing status | 4.16 | A2I cited as a random-sample design | A2I "is no longer open to new customers" | `RC/src/vendor/a2i_textract.txt` |
| 10 | Wrong line numbers | 4.4, 4.7, 4.16 | OpenAI guide 5607 and 5624 in quote order. Friedman "around 41 and 181". Tutorial line 731 | 5624 and 5607. Friedman 39 to 41 and 418 to 425. Tutorial line 707 | Line reads in the saved files |
| 11 | Incomplete field list | 4.6 | `ToolApprovalItem` holds three fields | Also `tool_origin` and `tool_lookup_key`. Neither is a risk field | `SR/oai_items_0.22.3.py` lines 556 to 580 |
| 12 | Scope wording | 4.2 | Salesforce flipped "for standard actions" | The sentence names eight actions. The next applies it to all standard actions. Custom actions only advised | `SR/sf_ka_005133036_browser_excerpt.txt` |
| 13 | Scorer quirk scope | 4.13, 9 item 35 | Effect on the board not checked | The leaderboard names the Hendrycks code. The saved copy has the same loop at line 14 | `RC/src/hendrycks_calibration_tools.py` |
| 14 | Unit mismatch | 5.5 | Module 7 anchor c0 0.17 used on a per-day curve | Caveat added: Module 7's points are per prior prompt in one session | `agent-harness-phase-05-approval-stack.md` lines 134 and 135 |
| 15 | Browser label | 5.6 | "Lab 3 catch inputs" with no label | "Lab D, browser data" | 6.2 Lab D |
| 16 | Overlap links missing | 2.2, 2.3, 4.3, 4.5, 4.12 | No link to Module 16 1.3, 3.1, 4.2, 5.2, Module 12 4.4 and 5.3, or Module 9 3.4 | Links added. Module 19 links these and does not re-teach them | `grep '^## '` output |
| 17 | Missing promise | 2.4 | Seven promises | Promise 8: `security-phase-04-designs.md` line 317 | `grep -rn "Module 19"` |
| 18 | Missing concept | 4.5, 6.2, 6.3, 8 | Eight screen rows | Row 9: mark arguments from outside content. Inferred only. Gap 13 | Module 16 section 4.2 |
| 19 | Resolved not-checked items | 9 items 6, 29, 34 | Open | Chrome date found. Xiong Table 3 verified. Egelman caption confirmed | Files named in section 9 |
| 20 | Small conditions | 5.3, 5.4, 7b | Akhawe "May and June 2013". RLCR ECE without scope. 0.654 lead not identified | Firefox SSL data ran to July 5. RLCR "in-domain". 0.654 is a table cell | `W/akhawe.txt` lines 576 to 582, `RC/src/2507.16806.txt` line 122, `SR/arxiv_2605.14830.txt` lines 1190 to 1200 |
| 21 | Wrong data label, coherence pass 2026-09-25 | 3.3 source table, 4.9 | Anderson et al. 2015 labelled "browser-style warnings" | Study 1 used images of software security warning dialogs in an fMRI scanner. Study 2 used Chrome extension permission warnings. Not browser click-through data | `W/anderson_chi.txt` lines 25, 265 to 270 and 443 |
| 22 | Missing field, coherence pass 2026-09-25 | 4.6 heading and bullets | "They carry no reason ... field" | Vercel `ai` has an optional `reason`, set per tool as policy text. The heading now names it | Phase 2 writer, `ai@7.0.114` `dist/index.d.ts` lines 1304 to 1328 |
| 23 | Gap partly closed, coherence pass 2026-09-25 | 8 gap 7 | No product source shows screen states | Intercom Fin shows "Resolved" and "Expired" notification states. A full state list is still inferred | Intercom help article 14468561, read by the Phase 2 writer |
| 24 | Claim too strong, coherence pass 2026-09-25 | 4.11 heading | "Experienced users leave per-action approval" | "more often than new users". About 20% of new-user sessions and over 40% at 750 sessions use full auto-approve, so most experienced sessions still do not | `RA/src/anthropic_autonomy.txt` line 89, Phase 3 fact checker |

### 10.3 Anchors that did not match

1. Tian "TriviaQA only", correction 1.
2. Claude in Chrome date, correction 3.
3. OpenAI guide line order in 4.4, correction 10.
4. Friedman line 181, correction 10.
5. Tutorial line 731, correction 10.
6. `ToolApprovalItem` field list, correction 11.
7. HLE "confabulation" quote context, correction 6.

The other anchors matched text and line. The dossier's own anchor script checks string counts only. It does not check line numbers or context, which is how items 3 to 5 passed it.

### 10.4 Concepts for the module question, README line 377

Added with evidence: the Claude Agent SDK default and its `auto` model approver, the LangChain unlisted-tool default, LangGraph's indefinite interrupt wait, LTT for a per-deployment bound, and tested undo as the meaning of "reversible".

Listed as gaps, no evidence found: a screen mark for data-derived arguments, gap 13. The no-callback behaviour of the Claude Agent SDK, gap 14. A planted-fault measure of model approvers for support agents, gap 15.

Summary: two serious corrections, the Tian resolution and the missing framework default. The rest are labels, line numbers, conditions and links.

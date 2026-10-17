# Module 16 — Security and threat modelling for LLM applications and agents

Research date: 2026-09-17. Reviewed 2026-09-25 by an independent reviewer. Status: research dossier, not course material. Every correction is in the text and in section 14, "Review log".

Module question, from `_curriculum/README.md` line 332: "A document in the knowledge base tells the model to send another tenant's data. What stops it?"

Label key. "Verified by the reviewer" means the reviewer fetched the source on 2026-09-25 and found the text. "Verified by the research agent" or "verified by me" means the 2026-09-17 author found it, and the reviewer did not re-check it. No raw source files for this dossier were found in `_curriculum/raw-research/` or in the research scratchpad. The reviewer fetched every source again into its own scratchpad.

## 1. What this module is for

This module teaches how to find and close the security holes that are specific to LLM applications and agents. The central problem is prompt injection: text from an untrusted source changes what the model does. A support agent reads customer messages, uploaded files, web pages, and tool results, and any of them can carry instructions. If the same agent can also read private data and send data out, one message can leak that data. Published measurements show that filters and trained defences stop fixed attack sets but fail against adaptive attackers. So the engineer must design the system so that a successful injection cannot cause harm.

## 2. Scope

### In scope

- Threat modelling: trust boundaries, the "lethal trifecta", Meta's "Agents Rule of Two".
- Direct and indirect prompt injection through files, email, tickets, web pages, tool outputs, memory, and repository files.
- Exfiltration channels. Exfiltration means sending data out to an attacker. Channels include rendered images, links, link previews, allow-listed domains, and server-side browsing.
- Measuring attack success: AgentDojo, InjecAgent, WASP, public competitions. Static versus adaptive attacks.
- Detector and training defences, and their measured limits.
- Design patterns: the six patterns of Beurer-Kellner et al., CaMeL, FIDES.
- Tool and agent supply chain: MCP servers, skill marketplaces, repository config files.
- Tenant isolation in RAG and agent systems.
- OWASP LLM Top 10 2025 and 2026, OWASP Agentic Top 10 2026, MITRE ATLAS 2026.09.
- Real incidents and CVEs as design-review material.

### Out of scope, and where it lives instead

Rewritten by the review on 2026-09-25. The earlier table pointed at Module 6 "sections 4.7, 4.8, 4.9" and "section 7". Those sections do not exist. Module 6 is organised by phase. Every row below was checked with `grep '^## '` on the built files.

| Topic | Where it lives | File |
|---|---|---|
| MCP sessions, sealed request state, header checks, MCP Apps | Module 6 Phase 4, sections 4.1 to 4.4 | `tools-mcp/tools-mcp-phase-04-mcp-protocol.md` |
| Annotations are claims, rug pull hash check, audience check and token passthrough, scanners | Module 6 Phase 5, sections 5.1 to 5.4 | `tools-mcp/tools-mcp-phase-05-mcp-trust.md` |
| Skills load a body on demand, code execution tool | Module 6 Phase 3, sections 3.3 and 3.4 | `tools-mcp/tools-mcp-phase-03-code-skills.md` |
| Agent loop, turn caps | Module 7 Phase 1 | `agent-harness/agent-harness-phase-01-loop.md` |
| Permission rules and hooks | Module 7 Phase 2, sections 2.1 to 2.3 | `agent-harness/agent-harness-phase-02-rules-hooks.md` |
| Sandbox boundaries and startup failure | Module 7 Phase 3, sections 3.1 to 3.4 | `agent-harness/agent-harness-phase-03-sandbox.md` |
| Escapes, allowlist proxy limits, DNS egress, container escapes | Module 7 Phase 4, sections 4.1 to 4.4. Defensive only. | `agent-harness/agent-harness-phase-04-escape-egress.md` |
| Approval rates, allow rules, fail-closed layers, CVE-2025-55284 mechanism | Module 7 Phase 5, sections 5.1 to 5.3 | `agent-harness/agent-harness-phase-05-approval-stack.md` |
| Agent card signatures, discovery, WebMCP tools as protocol properties | Module 8 Phase 2, sections 2.1 to 2.4 | `agent-protocols/agent-protocols-phase-02-discovery.md` |
| Two principals, workload identity, WebMCP acts as the user | Module 8 Phase 3, sections 3.1 to 3.4 | `agent-protocols/agent-protocols-phase-03-principals.md` |
| Token exchange, per-hop audience, `act` chain | Module 8 Phase 4, sections 4.1 to 4.4 | `agent-protocols/agent-protocols-phase-04-exchange.md` |
| Consent, revocation gap, audit record | Module 8 Phase 5, sections 5.1 to 5.3 | `agent-protocols/agent-protocols-phase-05-proof.md` |
| Memory write gate | Module 10 Phase 2, section 2.4 | `memory/memory-phase-02-what-to-store.md` |
| A scope key is a filter, not a boundary | Module 10 Phase 4, section 4.4 | `memory/memory-phase-04-deletion-scope.md` |
| Notes the agent wrote, path check | Module 2 Phase 4, section 4.3 | `context-engineering/context-engineering-phase-04-split-or-file.md` |
| Semantic cache scope, CacheAttack numbers | Module 4 Phase 6 | `advanced-retrieval/advanced-retrieval-phase-06-caches-grounding.md` |
| Shared index versus index per tenant | Module 4 Phase 7 | `advanced-retrieval/advanced-retrieval-phase-07-tenants-map.md` |
| Prefix cache sharing, `cache_salt`, the Stanford audit of 17 providers | Module 1 Phase 6A, section 6.2 | `inference-internals/inference-internals-phase-06a-capacity-tenants.md` |
| Production guardrail pipelines, per-tenant policy | Module 17, not built | none |
| Audit logs and retention | Module 18, not built | none |
| Approval screen design | Module 19, not built | none |
| Harmful-content jailbreaks, offensive work on real systems | Not covered | none |

### Overlap with built modules

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| Prefix cache timing side channel, `cache_salt`, Stanford audit | Module 1 section 6.2. Line 517 already states the 8 of 17 result. | Nothing new. Link only. The earlier dossier said this module adds the audit. That was wrong. |
| Rug pull and tool poisoning mechanism, CVE-2025-54136 mechanism | Module 6 sections 5.1 and 5.2 | Defences, and approval bound to a name as a root cause |
| Token passthrough, audience check | Module 6 section 5.3 | Nothing. Link only. |
| An allowlist proxy leaks through an allowed host, DNS egress | Module 7 sections 4.2 and 4.3 | Nothing on the mechanism. The incidents in section 7 are the attack side. |
| Sandbox CVEs CVE-2025-54794, CVE-2025-59532, CVE-2026-25725, CVE-2026-39861, CVE-2026-54316, CVE-2026-55607 | Module 7 Phase 4 | Do not re-teach. |
| Built-in safe command list, CVE-2025-55284 | Module 7 section 5.2 | The defence against the untrusted content that triggered it |
| Memory scope key, write gate | Module 10 sections 2.4 and 4.4 | Memory poisoning as an attack, section 4.10 |
| CacheAttack hijack rate on GPTCache | Module 4 Phase 6, line 479 | Threat model only. Do not repeat the numbers. |
| Agent card key source, `jku` trust, lab E11 | Module 8 section 2.2 and Phase 5 lab | Card spoofing as an attack, section 4.11 |

## 3. What changed recently

| Change | Date | Source | Why it matters |
|---|---|---|---|
| OWASP LLM Top 10 2025 | 2024-11-17 | OWASP GenAI | Added System Prompt Leakage, Vector and Embedding Weaknesses |
| CaMeL v1 | 2025-03-24 | arXiv 2503.18813 | Policy-enforcing interpreter with capability labels |
| Design patterns paper v1 | 2025-06-10 | arXiv 2506.08837 | Six named patterns |
| "The lethal trifecta" | 2025-06-16 | Simon Willison | Three-part risk model |
| "The Attacker Moves Second" | 2025-10-10 | arXiv 2510.09023 | 12 defences bypassed |
| Meta "Agents Rule of Two" | 2025-10-31 | Meta AI blog | At most two of three risky properties per session |
| Anthropic browser injection post | 2025-11-24 | Anthropic | 1% ASR for Claude Opus 4.5, still called a risk |
| OWASP Agentic Top 10 2026 | 2025-12-09 | OWASP GenAI | ASI01 to ASI10 |
| OpenAI Atlas hardening post | 2025-12-22 | OpenAI | RL-trained automated attacker |
| OpenClaw CVE-2026-25253, ClawHavoc skills | 2026-02-01, 2026-02-02 | NVD, The Hacker News, Unit 42 | Skill marketplaces became a malware channel |
| Gray Swan indirect injection paper | 2026-03-16 | arXiv 2603.15714 | 13 models, 0.5% to 8.5% per attempt |
| OWASP LLM Top 10 2026 | page 2026-08-03, announced 2026-09-01 | OWASP GenAI | Order changed. Hidden Context Exposure replaces System Prompt Leakage. |
| MITRE ATLAS 2026.09 | 2026-09-15 | atlas-data | 16 tactics, 120 techniques |
| MCP spec renames Session Hijacking | spec 2026-07-28 | modelcontextprotocol.io | Now "State Handle Hijacking". The page links the old section for protocol 2025-11-25 and earlier. Verified by the reviewer. |
| Graphiti advisory GHSA-gg5m-55jj-8m5g | 2026-03-11 | GitHub, getzep/graphiti | "Cypher Injection via unsanitized node_labels in search filters", rated High. Module 10 sends it here. Verified by the reviewer. |
| Trajectory Labs test in Anthropic's auto mode post | 2026-08-07 | claude.com blog | 72 held-out scenarios, 10 runs each. 0 of 720 succeeded on Claude Fable 5, Opus 5, Sonnet 5 in auto mode. 5.83% on GPT-5.6 Sol in Codex Auto-review. Vendor-commissioned. Verified by the reviewer. |
| OWASP GenAI "Agent Control Standard" and "Industry Framework Crosswalk" | 2026-09-01 | OWASP GenAI resource pages | New resources listed next to both Top 10 pages. Contents not checked. |
| Re-check on 2026-09-25 | 2026-09-25 | OWASP, atlas-data CHANGELOG | LLM Top 10 2026 page still dated August 3, 2026, same PDF, still "[Publication date to be set]". Agentic Top 10 unchanged. ATLAS 2026.09 is still the newest changelog entry. Verified by the reviewer. |

## 4. Core concepts, with verified facts

### 4.1 Removing one of three properties stops a data leak, but not a harmful action

An agent can leak data when three things meet in one context: private data, untrusted content, and a way to send data out. Removing any one of the three blocks this kind of leak. Meta's rule adds state changes to the third property, so it also covers harmful actions.

- Willison's three parts: "Access to your private data", "Exposure to untrusted content", "The ability to externally communicate". 16 June 2025. Verified by the reviewer.
- Meta: agents "must satisfy no more than two of the following three properties within a session". The third property is "change state or communicate externally". October 31, 2025. Verified by the reviewer on 2026-09-25. Curl with the default user agent returns HTTP 400. A Safari user agent returns 200.
- If all three are needed, Meta says the agent "should not be permitted to operate autonomously and at a minimum requires supervision". Verified by the reviewer. The post has no numbers.
- Willison named "prompt injection" on 12 September 2022. Greshake et al. introduced "Indirect Prompt Injection" in arXiv 2302.12173 on 23 February 2023, published at ACM AISec 2023. Verified. Earlier uses were not checked.

Where the example stops working: the trifecta covers data theft only. Deleting records needs no outbound channel. The Rule of Two covers that case.

### 4.2 Every text that reaches the context is an input, and every rendered output is an exit

Any text that reaches the context can carry instructions. The incidents in section 7 show the usual ways in and out.

- Ways in: email, public chat channels, GitHub issues, support tickets, web forms, shared documents, web pages, and repository files such as `GEMINI.md`. The matching incidents are EchoLeak, Slack AI, GitHub MCP, Supabase MCP, ForcedLeak, AgentFlayer, Comet, and Gemini CLI. Verified per incident.
- Ways out: auto-loaded Markdown images, clicked links, link-preview bots, public pull requests, the app's own reply thread, an expired allow-listed domain, an allowed API domain, and browsing from the vendor's servers. Verified per incident.
- In ForcedLeak, the allow-listed domain had expired and the researchers bought it for $5. Source: Noma Security. Verified.
- In ShadowLeak, data left from OpenAI's servers, so client-side controls could not see it. Verified from securityaffairs quoting Radware. Radware's page returned a bot check.
- The design patterns paper has a "Customer Service Chatbot" case study in section 4.4. Verified by the reviewer from Table 1 and the section heading.

### 4.3 An ASR is meaningless without its denominator, its attacker and its retry count

Attack success rate, or ASR, is the share of attempts where the attacker's goal happened. Benchmarks define the denominator and the success check differently, so their numbers are not directly comparable.

- AgentDojo v1, by ETH Zurich and Invariant Labs, NeurIPS 2024: 4 suites, 70 tools, 97 user tasks, 27 injection tasks, 629 security cases. arXiv 2406.13352, section 3 and Table 1. Verified by the reviewer.
- AgentDojo v1.2 has 35 injection tasks and 949 cases. The research agent counted this in the agentdojo 0.1.35 wheel. CaMeL and FIDES report 949 attacks. The version they used is inferred.
- AgentDojo Table 3, "Important message" attack: GPT-4o ASR 47.69% at 69.00% utility. Claude 3.5 Sonnet 33.86% at 78.22%. Utility here is benign utility. Verified by the reviewer in Appendix C, Table 3. Table 5 gives GPT-4o no-defence targeted ASR as 57.69%. Utility under attack is 50.08% in Table 3 and 50.01% in Table 5, so both rows describe the same condition. The paper contradicts itself. A typo is likely. Inferred, not checked with the authors.
- AgentDojo cost about US$35 for 629 cases on GPT-4o at 2024 prices, and US$4 for the 97 utility cases. Appendix D. Verified by the reviewer. Today's price is not checked.
- InjecAgent, by UIUC, ACL Findings 2024: 1,054 cases, 17 user tools times 62 attacker tools. ReAct-prompted GPT-4 ASR-valid 23.6% base, 47.0% enhanced. "Enhanced" adds a hacking prompt to the attacker text. ASR-valid counts only well-formed outputs. Table 3. Verified by the reviewer. The venue is not checked.
- WASP, by FAIR at Meta, 2025, tests web agents. ASR-intermediate, where the agent was diverted, ranged from 16.7% to 85.7% across the Table 2 rows. ASR-end-to-end, where the attacker goal was completed, was at most 16.7%. The high end, 85.7% diverted and 16.7% completed, is OpenAI o1 with the instruction hierarchy in the system message. The low end of diversion, 16.7%, is GPT-4o with a system-prompt defence. The authors call this "security by incompetence". arXiv 2504.18575, Table 2. Verified by the reviewer. Preprint. The venue is not checked.
- Gray Swan and UK AISI ART competition: 22 agents, 44 scenarios, 1.8 million attacks. ASR is successful policy violations divided by user sessions per model. Direct 5.7%, indirect 27.1%, all 12.7%. arXiv 2507.20526, section 2.2 and Table 1. Verified by the reviewer. Preprint.
- Gray Swan 2026: 272,000 attempts on 13 models in the abstract. The introduction says "240K+". Success required the harmful action and hiding it from the final reply. ASR is successful attacks divided by all chats for that model, section 4.1. 0.5% for Claude Opus 4.5 over 12.0k attempts, 8.5% for Gemini 2.5 Pro over 19.6k attempts. arXiv 2603.15714. Verified by the reviewer. Preprint. Co-authors include Anthropic, OpenAI, Meta, US CAISI and UK AISI staff. The pooled rate is 8,648 / 272,000 = 3.18%, computed by the reviewer.
- US CAISI on upgraded Claude 3.5 Sonnet in AgentDojo: new attacks reached 81%, against 11% for the best baseline. With 25 attempts, average ASR rose from 57% to 80%. NIST blog, January 17, 2025. The 57% is the average over five new injection tasks. Verified by the reviewer.
- Anthropic's page description: "Claude Opus 4.5 achieves a 1% attack success rate against prompt injections in browser use". The attacker had "100 attempts per environment". The page says 1% "still represents meaningful risk". The attacker is Anthropic's "internal Best-of-N attacker". The denominator is "attacks encountered by each model". Verified by the reviewer. Vendor number on vendor-built environments, not independently reproduced. Per-model chart values are not checked.

Retries raise ASR. A low per-attempt rate is not low risk when the attacker can retry.

### 4.4 A defence that scores near zero on a fixed attack set fails against an adaptive attacker

A detector is a classifier that flags injected text. A training defence teaches the model to ignore injected instructions. An adaptive attacker changes the attack using feedback from the defence. Most detector and training defences fail against adaptive attackers.

- Spotlighting, by Microsoft, arXiv 2403.14720, "reduces the attack success rate from greater than 50% to below 2%". Conditions: June 2023 GPT-3.5 Turbo and GPT-4, 1,000 synthetic documents, a simple keyword payload. Not adaptive. Verified by the reviewer.
- Instruction hierarchy, by OpenAI, arXiv 2404.13208: system prompt extraction robustness "improved by 63%" on fine-tuned GPT-3.5 Turbo. Verified by the reviewer. Preprint.
- Llama Prompt Guard 2 86M, by Meta: 97.5% recall at 1% false positive rate on English. This is "Direct Jailbreak Detection" on a "private benchmark" that Meta built. It is not an injection result on public data. On AgentDojo, "APR @ 3% utility reduction" is 81.2%. The 22M model: 88.7% and 78.4%. On the same table ProtectAI scores 22.2%. Source: PurpleLlama model card. Verified by the reviewer. Vendor numbers on a vendor-chosen benchmark. "APR" is read as attack prevention rate, which is inferred. The card does not define it.
- AgentDojo's BERT detector cut GPT-4o ASR to 7.95% but cut utility from 69.0% to 41.49%. Table 5. Verified by the reviewer.
- "The Attacker Moves Second" has authors from OpenAI, Anthropic, Google DeepMind, ETH Zürich and others. It says: "we bypass 12 recent defenses ... with attack success rate above 90% for most". Most defences "originally reported near-zero attack success rates". Verified by the reviewer. Preprint, "Under review".
- Detectors, section 5.3: a search attack given the detector's score "achieves ASR of >90% against Protect AI, PromptGuard, and Model Armor (with Gemini-2.5 Pro as the base model)". PIGuard "still reaches 71% ASR". Verified by the reviewer. Table 7 shows 90% for Protect AI and for Model Armor, and 94% for PromptGuard. So two of the three are at 90%, not above it.
- Table 7, AgentDojo, 800-query budget, static to adaptive ASR. PromptGuard: 26 to 94 on Gemini-2.5 Pro, 0 to 75 on GPT-5 Mini. MetaSecAlign 70B with no external defence: 5 to 96. The MetaSecAlign authors had reported 2% on static AgentDojo, section 4 of this paper. Utility falls too. Protect AI on Gemini-2.5 Pro has 39.18% utility against 74.23% with no defence. Verified by the reviewer.
- Humans: "the search attack succeeds 69% of the time whereas the red-teaming humans collectively succeeds 100% of the time". 29 scenarios, Appendix F. Verified by the reviewer.
- Zhan et al., NAACL Findings 2025, arXiv 2503.00061: eight defences on InjecAgent, all bypassed at over 50% ASR. Vicuna-7B prompted and Llama3-8B fine-tuned agents. Verified by the reviewer. The NAACL Findings venue is not checked.

Correction to the module plan: the plan said detectors fail "above 90 percent". That holds for three of four detectors on Gemini-2.5 Pro with score feedback and 800 queries. PIGuard stayed at 71%. On GPT-5 Mini the detectors reached 49% to 81%.

### 4.5 Only the system design can guarantee that an injection triggers no action

These patterns limit what the agent can do after it reads untrusted input. The paper's principle: "once an LLM agent has ingested untrusted input, it must be constrained so that it is impossible for that input to trigger any consequential actions". They give up some utility for a property that does not depend on the model.

- arXiv 2506.08837, v3 27 June 2025. 14 authors listed alphabetically, from Invariant Labs, IBM, EPFL, ETH Zurich, ETH AI Center, Swisscom, Google, AppliedAI Institute for Europe, Microsoft and Kyutai. Verified by the reviewer. Preprint. Willison's post says "11 authors". The paper lists 14.
- Exact headings: "The Action-Selector Pattern", "The Plan-Then-Execute Pattern", "The LLM Map-Reduce Pattern", "The Dual LLM Pattern", "The Code-Then-Execute Pattern", "The Context-Minimization pattern". Section 3.1. Verified by the reviewer.
- Ten case studies. Recommendation 2: "no single pattern is likely to suffice across all threat models or use cases". Verified by the reviewer, section 5.
- The paper has no benchmark numbers. Do not attach numbers to it.
- The Dual LLM pattern comes from Willison, 25 April 2023, with "a Privileged LLM and a Quarantined LLM". Verified.

| Pattern | What untrusted data can change | Cost |
|---|---|---|
| Action-Selector | Nothing. Tool output never returns to the model. | Fixed actions only |
| Plan-Then-Execute | Arguments, not which tools run | Plan cannot adapt |
| LLM Map-Reduce | One isolated item's result | Per-item tasks only |
| Dual LLM | Only the quarantined model's output, held as a variable | Planner cannot read data |
| Code-Then-Execute | Data inside a program the planner wrote | Needs an interpreter and policies |
| Context-Minimization | Nothing, once the user prompt is removed from context | Loses detail |

This table is a summary written for this dossier. The wording is inferred from section 3.1.

### 4.6 CaMeL and FIDES stop AgentDojo injections, and the utility cost depends on the model

CaMeL applies Code-Then-Execute with information-flow tracking. A privileged LLM writes Python from the trusted query only. A quarantined LLM turns untrusted data into typed values and cannot call tools. A custom interpreter labels every value and checks policies at each tool call. "Capability" here means a security label, not model skill.

- Authors from Google, Google DeepMind, and ETH Zurich. arXiv 2503.18813 v2, 24 June 2025. Verified by the reviewer. Preprint.
- Abstract: "solving 77% of tasks with provable security (compared to 84% with an undefended system)". This matches the o3 High row of Table 2: 77.3% against 84.5%. Verified by the reviewer. The model link comes from Table 2. The abstract does not name the model.
- Other models lose more. Gemini 2.5 Pro: 73.2% to 41.2%. Claude 4 Sonnet: 86.6% to 74.2%. Gemini 2.5 Pro and Gemini 2.5 Flash reach 0.0% on the travel suite with CaMeL. Table 2. Verified by the reviewer.
- Out of 949 attacks, Table 4: Gemini 2.5 Flash 297 successes native, 1 with CaMeL. Claude 4 Sonnet 75 and 11. Verified by the reviewer. The authors say the attacks still counted against CaMeL "are not due to a prompt injection", section 6.2.2.
- Section 6.2.1 says Gemini 2.5 Pro "drops from 300 without to 0". Table 4 says 163 native. The paper contradicts itself. Verified by the reviewer. The 300 to 0 sentence is about CaMeL without policies.
- On Claude 3.5 Sonnet: CaMeL 0 successful attacks, spotlighting 5, tool filter 8, prompt sandwiching 24, undefended 44. Appendix Table 7. Verified by the reviewer. The text of section 6.3 calls tool filter, at 8, "the next best defense". Table 7 shows spotlighting at 5. The paper contradicts itself. The same text notes that Claude 3.5 Sonnet already resists AgentDojo's default attack.
- Cost: "2.82× input tokens and 2.73× more output tokens for the median task". Claude 3.5 Sonnet, GPT-4o tokenizer, tool docs not counted. Section 6.5. Verified by the reviewer. Spotlighting, the cheapest baseline, used 1.06 times the input tokens.
- A Claude 3.5 Haiku quarantined model, with Claude 4 Sonnet as the privileged model, cost about 1% utility for an estimated 12% lower cost on the median task. Verified by the reviewer.
- Section 7: "CaMeL is vulnerable to side-channel attacks", through external resources, exceptions that leak one bit, and timing. Verified by the reviewer.
- FIDES, by Microsoft, arXiv 2505.23643, tracks confidentiality and integrity labels. "With policy checks enabled, FIDES stops all prompt injection attacks in AgentDojo." Table 1 uses the Tool Knowledge attack on gpt-4o, all 949 attacks. FIDES with policies allowed 1 injection, or 0 after two injection tasks are removed. The authors do not count those two as attacks on their policies. The basic planner allowed 163, or 156. The basic planner with the same policy checks allowed 9, or 0. So the policy check, not the planner alone, does most of the work. Verified by the reviewer. Preprint.
- "The Attacker Moves Second" skipped Tool Filter and CaMeL "because the attack is guaranteed to fail in most of the selected scenarios". The reason given: control flow does not depend on the data. The same paragraph says such defences "noticeably reduce the utility". Appendix G. Verified by the reviewer.

### 4.7 Agent config and tool files are code, and most agent CVEs trust them too early

Tool descriptions, skills, and project config files are all third-party input. Module 6 Phase 5 teaches the MCP mechanisms. Module 7 Phase 4 teaches the sandbox CVEs. This module groups the remaining CVEs by root cause, so the learner can review a new agent for the same faults.

- **A. Trust before load.** Project files run code or redirect traffic before the user accepts trust. Examples: Claude Code CVE-2026-21852, where settings set `ANTHROPIC_BASE_URL`, fixed 2.0.65. Gemini CLI CVE-2026-12537, fixed CLI 0.39.1 and run-gemini-cli GitHub Action 0.1.22. Codex CLI CVE-2025-61260, v0.23.0 and before, auto-loaded project `.env` and `.codex/config.toml`. NVD published it on 2026-04-14 with a CISA-ADP score of 9.8. Its fixed version is not in the NVD text. Verified by the reviewer from the NVD API.
- **B. Approval bound to a name.** Cursor CVE-2025-54136: an approved MCP entry changed later and ran without a new prompt. Affects 1.2.4 and below, fixed 1.3. Verified by the reviewer from NVD. Module 6 section 5.2 already teaches this mechanism. Here it is only a root-cause example.
- **C. The agent writes its own config.** Cursor CVE-2025-54135 created `.cursor/mcp.json`, fixed 1.3.9. Copilot CVE-2025-53773 set auto-approve in `.vscode/settings.json`, fixed in VS 2022 17.14.12. NVD text and scores verified by the reviewer. The fixed VS version is not re-checked.
- **D. Allow-lists that check command text.** Gemini CLI before 0.1.14 checked only the start of a command. Copilot CLI CVE-2026-29783 missed bash parameter expansion. NVD says "prior to and including 0.0.422". So 0.0.423 is the first fixed version. Inferred from the NVD text. Verified by the reviewer. The Gemini CLI 0.1.14 claim is from Tracebit and is not re-checked.
- **E. Compromised publisher.** Amazon Q extension 1.84.0 shipped injected code, CVE-2025-8217, fixed 1.85.0. AWS says a syntax error stopped it. Verified by the reviewer from AWS-2025-015 and NVD. Nx CVE-2025-10894 packages called local AI CLIs with confirmations turned off. NVD record verified by the reviewer. The AI CLI detail is from the Nx postmortem and is not re-checked.
- An audit of 2,857 ClawHub skills found 341 malicious ones "across multiple campaigns", credited to Koi Security. 335 of them belong to the campaign named ClawHavoc, which installed the Atomic Stealer macOS malware. Koi ran the audit with the help of an OpenClaw bot. Vendor number. Verified by the reviewer from The Hacker News, 2026-02-02. Unit 42 not re-checked. 341 / 2,857 = 11.9%, computed by the reviewer.
- The MCP security page for spec 2026-07-28 lists twelve named sections in its table of contents. Some may be subsections. They are Confused Deputy Problem, Token Passthrough, Server-Side Request Forgery, SSRF Against Authorization Servers, State Handle Hijacking, Local MCP Server Compromise, OAuth Authorization URL Validation, stdio Transport Security in Proxy Scenarios, Mix-Up Attacks, Localhost Redirect URI Impersonation, CIMD Trust Policies, and Scope Minimization. Verified by the reviewer from the page's table of contents.

### 4.8 A tenant filter protects only when it runs inside the index query

A multi-tenant app shares indexes, caches, and memory across customers. Leaks come from retrieval, shared memory, or shared caches. The fix is to enforce access in the data layer before the model sees anything.

- OWASP LLM08:2025 warns of "context leakage between users or queries" in shared vector databases. Verified by the reviewer.
- OWASP LLM02:2026 is Sensitive Information Disclosure. Its Tier 1 mitigation 3 says: "Authorize before retrieval: enforce document- and chunk-level authorization inside the index query, not at the application layer after retrieval." The next sentence says to isolate per-tenant indexes for high-sensitivity workloads. Verified by the reviewer from the PDF. The earlier dossier put this quote under LLM09. That was wrong.
- OWASP LLM09:2026 Vector and Embedding Weaknesses says: "Enforce tenant scoping inside the index query, not as a post-retrieval filter, and validate it server-side." Verified by the reviewer from the PDF.
- Pinecone recommends "one namespace per tenant". A query on a 1 GB namespace costs 1 read unit. A filtered query on a shared 100 GB namespace costs 100. The page states "1 RU per 1 GB". Verified by the reviewer. Page modified 2026-09-15.
- PostgreSQL 18: "If no policy exists for the table, a default-deny policy is used." Table owners bypass row-level security unless the table uses `FORCE ROW LEVEL SECURITY`. Verified by the reviewer. The current docs page is version 18.
- Gu et al. at Stanford, ICML 2025, arXiv 2502.07776: "We detected prompt caching in 8 out of 17 API providers. In 7 of these providers, we detected global cache sharing." Audited September and October 2024. Verified by the reviewer. Current behaviour is not checked.
- Module 1 section 6.2 already teaches this audit and `cache_salt`, at line 517 of `inference-internals-phase-06a-capacity-tenants.md`. Link it. Do not re-teach it.

### 4.9 The same risk has a different number in each OWASP list

The three OWASP lists, verified by the reviewer on 2026-09-25. The 2025 list is from the OWASP site. The 2026 lists are from the PDFs. The LLM 2026 PDF still says "[Publication date to be set]".

| # | LLM Top 10 2025 | LLM Top 10 2026 | Agentic Top 10 2026 |
|---|---|---|---|
| 01 | Prompt Injection | Prompt Injection | Agent Goal Hijack |
| 02 | Sensitive Information Disclosure | Sensitive Information Disclosure | Tool Misuse and Exploitation |
| 03 | Supply Chain | Excessive Agency | Identity and Privilege Abuse |
| 04 | Data and Model Poisoning | Supply Chain | Agentic Supply Chain Vulnerabilities |
| 05 | Improper Output Handling | Data and Model Poisoning | Unexpected Code Execution (RCE) |
| 06 | Excessive Agency | Unbounded Consumption | Memory & Context Poisoning |
| 07 | System Prompt Leakage | Misinformation | Insecure Inter-Agent Communication |
| 08 | Vector and Embedding Weaknesses | Hidden Context Exposure | Cascading Failures |
| 09 | Misinformation | Vector and Embedding Weaknesses | Human-Agent Trust Exploitation |
| 10 | Unbounded Consumption | Improper Output Handling | Rogue Agents |


- MITRE ATLAS 2026.09: "16 tactics, 120 techniques, 88 sub-techniques, 40 mitigations, and 73 case studies". Verified by the reviewer from the atlas-data CHANGELOG, entry dated 2026-09-14. The 2026.09 release updated AML.T0051.001 "LLM Prompt Injection: Indirect" and AML.T0077 "LLM Response Rendering", and added AML.T0131 "Crafted AI Assistant Links". Verified by the reviewer. Relevant IDs: AML.T0051 LLM Prompt Injection, AML.T0080 AI Agent Context Poisoning, AML.T0086 Exfiltration via AI Agent Tool Invocation, AML.T0110 AI Agent Tool Poisoning. Verified by the research agent, not re-checked.
- NIST AI 100-2 E2025, adversarial ML taxonomy, March 2025. Verified by the research agent, not re-checked.

### 4.10 A poisoned document or memory record keeps working after the attacker leaves

Added by the review. It answers the module question directly: the attack text sits in the knowledge base or in memory, and every later query can retrieve it. Module 10 teaches the scope key and the write gate. This section is the attack side.

- PoisonedRAG, Zou et al., arXiv 2402.07867. The arXiv comment says "To appear in USENIX Security Symposium 2025": "90% attack success rate when injecting five malicious texts for each target question into a knowledge database with millions of texts". The paper tested several defences and found them "insufficient". Verified by the reviewer from the arXiv abstract page. The target is a wrong answer to a chosen question, not an action. The per-model and per-dataset tables are not checked.
- AgentPoison, Chen et al., arXiv 2407.12784: a backdoor trigger in the user instruction retrieves poisoned memory or knowledge-base records. The abstract reports average ASR above 80%, benign impact below 1%, at a poison rate below 0.1%. Three agents: autonomous driving, knowledge QA, and EHRAgent. Verified by the reviewer from the abstract. Preprint status not checked. The attacker needs write access to the store and control of a trigger in the query.
- MINJA, Dong et al., arXiv 2503.03704: the attacker writes malicious records into agent memory "by only interacting with the agent via queries and output observations". No direct write access is needed. Verified by the reviewer from the abstract. The numbers are not checked.
- SpAIware in section 7 is the production case: an injection wrote to ChatGPT memory, and later chats leaked through image URLs.
- The Graphiti advisory GHSA-gg5m-55jj-8m5g, 2026-03-11, is a different class. Unsanitized `node_labels` in search filters allowed Cypher injection into the graph database. It is classic query injection in a memory store, not prompt injection. Verified by the reviewer from the advisory list.

Where this stops working as an example: PoisonedRAG measures a wrong answer. It does not measure data sent to another tenant. For the module question, the harm also needs a tool that sends data, and a retrieval path that crosses tenants.

### 4.11 Protocol attacks target who the server thinks is asking

Added by the review to hold the Module 8 commitments. Module 8 teaches each item as a protocol property. This module teaches it as an attack with its defence.

- Confused deputy with a static client ID. The MCP Security Best Practices page, spec 2026-07-28, has a "Confused Deputy Problem" section. It names a proxy server with a static client ID, dynamic client registration and a consent cookie. Module 8 section 4.2 and Module 6 section 5.3 name the fix as per-client consent. Verified by the reviewer from the MCP page headings. The attack steps are not re-read.
- Agent card spoofing. Module 8 Phase 5 lab E11 printed a card that verified through its own `jku` key set. A pinned key rejected it. Evidence is the built lab output in `agent-protocols-phase-05-proof.md` line 763. Not re-run.
- Webhook SSRF. SSRF means the server fetches a URL that the attacker chose. Module 8 section 1.3 shows that a2a-sdk 1.1.5 screened no push URL and delivered to 127.0.0.1. The MCP page also has "Server-Side Request Forgery" and "SSRF Against Authorization Servers" sections. Verified by the reviewer from the headings.
- WebMCP tool poisoning. A WebMCP tool runs with the user's logged-in session, Module 8 section 3.4. Poisoned descriptions on a page reach the agent like MCP tool poisoning. Inferred from Module 6 section 5.1 and Module 8 section 3.4. No measured case was found.

## 5. Proposed phase outline

| Phase | Title | What it teaches | Labs | Runs where, costs what |
|---|---|---|---|---|
| 1 | Threat model | Trust boundaries, trifecta, Rule of Two, OWASP and ATLAS mapping | 1, 2 | Laptop, offline |
| 2 | Injection and exit channels | Direct and indirect injection, rendering and link exits, knowledge-base and memory poisoning from section 4.10, project context files such as `AGENTS.md`. Links Module 7 sections 4.2 and 4.3 for egress, and Module 10 sections 2.4 and 4.4. | 3, 4 | Laptop, offline |
| 3 | Measuring attack success | ASR variants, denominators, retries, intervals, AgentDojo structure, red-team evals owed to Modules 11 and 12, the Trajectory Labs result owed to Module 7 | 5, 6 | Laptop. Optional AgentDojo live run needs an API key. Re-price first. |
| 4 | Detectors and adaptive attacks | Spotlighting, instruction hierarchy, Prompt Guard 2, score feedback, utility cost | 7, 8 | Laptop. Optional Prompt Guard 2 22M on CPU needs gated model access. |
| 5 | Design patterns, CaMeL, FIDES | Six patterns, capability labels, policies, side channels, token cost | 9, 10 | Laptop, offline |
| 6 | Tool and agent supply chain and protocol attacks | Root causes A to E, skills, publisher compromise, the section 4.11 protocol attacks. Links Module 6 Phase 5, Module 7 Phases 4 and 5, and Module 8 Phases 2 to 5. | 11, 12 | Laptop, offline |
| 7 | Tenant isolation and incident review | Authorization before retrieval, RLS pitfalls, semantic and prefix cache sharing as threats, ten incidents. Links Module 1 section 6.2 and Module 4 Phases 6 and 7. | 13, 14, 15 | Laptop with a local Postgres 18 install. The learner's laptop has no Docker, per the research brief. No cloud cost. |

Seven phases fit because almost all of this is new. Module 1 covers the cache side channel. Module 6 covers MCP mechanisms. Module 7 covers sandboxes and egress. Module 8 covers identity and tokens. Measurement and adaptive attacks each need a phase, because the headline numbers mislead without their conditions.

## 6. Lab ideas

All labs use fake data and run offline. No lab contacts a real service. Attack fixtures stay in code blocks and target only the local harness.

1. **Trifecta auditor.** Reads a YAML of agent tools tagged private, untrusted, and outbound or state-changing. Prints the properties per session. Break-it: add a fetch-URL tool. Self-test: ten fixture agents with known flags.
2. **Threat table builder.** Maps each trust-boundary crossing to OWASP 2025, OWASP 2026, and ATLAS IDs. Break-it: use a 2025 ID in the 2026 column. Self-test: known mapping for five flows.
3. **Injection channel harness.** A fake support agent with a scripted model that obeys any marked line. Reads a fake knowledge base, ticket, and tool result. Prints which channel caused each tool call. Break-it: remove source labels from tool results. Self-test: known call log.
4. **Exit renderer check.** A Markdown sanitizer that blocks images and links to hosts off an allow-list. Prints results for 50 fixture URLs. Break-it: reference-style images, as in EchoLeak. Self-test: fixed pass and fail table.
5. **ASR calculator.** Prints ASR, ASR-valid, diverted and completed rates, with Wilson intervals, from fixture logs. Break-it: count malformed outputs as failed attacks. Self-test: closed-form values.
6. **Retry math.** Prints `1 - (1 - p)**k` for p from 0.5% to 30% and k up to 100. Compares with CAISI's 57% to 80% at 25 attempts. Break-it: attempts that are not independent. Self-test: exact values.
7. **Toy detector versus adaptive search.** A small classifier on synthetic text, and a random-search attacker that sees the score. Prints static and adaptive ASR by query budget. Break-it: return only the flag, not the score. Self-test: fixed seed, known curve.
8. **Detector utility cost.** Prints false positive rate and blocked benign tasks per threshold. Relates to AgentDojo's 69.0% to 41.49% drop. Self-test: known confusion matrix.
9. **Pattern playground.** One fake email task built as a plain agent, action-selector, plan-then-execute, and dual LLM. Prints which injections changed an action. Break-it: return quarantined output as free text. Self-test: known result table.
10. **Mini capability interpreter.** A tiny Python-subset interpreter with source labels and a policy before `send_email`. Prints allowed and denied calls. Break-it: an `if` on a private value, a side channel as in CaMeL section 7. Self-test: known allow and deny list.
11. **Repository trust scanner.** Finds files that agents load before trust: `.mcp.json`, `.cursor/mcp.json`, `.vscode/settings.json`, `.claude/settings.json`, `.gemini/.env`, `GEMINI.md`, `core.fsmonitor`. Prints each finding with the matching CVE. Break-it: a symlinked config. Self-test: known findings.
12. **Content-bound approval.** Stores approvals as hashes of the full command and arguments. Prints re-prompt events when a fixture changes. Break-it: approve by name, as in MCPoison. Self-test: known events.
13. **RLS leakage test.** A local Postgres 18 with per-tenant policies. Docker is not available on the learner's laptop, per the research brief. A Homebrew install is the likely route. Not checked. Prints rows visible to the app role, the owner, the owner with `FORCE`, and a `BYPASSRLS` role. Break-it: connect as the owner without `FORCE`. Self-test: fixed matrix.
14. **Filter after versus inside retrieval.** A fake three-tenant index. Prints leaks and recall at k. Break-it: filter after the top-k cut. Self-test: known leak count.
15. **Incident review drill.** The learner fills channel in, channel out, trifecta parts, root cause, and fix for ten incidents. Self-test: answer key from section 7.

Optional live labs: AgentDojo 0.1.35 on one suite needs an API key, cost not measured. Prompt Guard 2 22M on CPU needs gated access, no API cost.

## 7. Failure stories and case studies

CVSS values come from the NVD API. "NVD" is NVD's own score. The other score is from the publishing authority.

| Case | Date | Mechanism | Trifecta | Fix and numbers | Source |
|---|---|---|---|---|---|
| Slack AI | 2024-08-20 | Public message plus private data, leaked through a clicked link | P, U, X | Salesforce "deployed a patch". No CVE. | PromptArmor |
| ChatGPT SpAIware | 2024-09-20 | Injection wrote to memory. Image URLs leaked later chats. | P, U, X | macOS app fix | Embrace The Red |
| GitLab Duo | 2025-05-22 | Hidden text in merge requests. HTML tags sent data out. | P, U, X | Unsafe external HTML blocked | Legit Security |
| GitHub MCP | 2025-05-26 | Public issue led the agent to copy private data to a public PR | P, U, X | No server fix | Invariant Labs |
| EchoLeak, CVE-2025-32711 | 2025-06-11 | Email in Copilot context, classifier bypass, image via an allowed domain | P, U, X | Server fix. Microsoft 9.3, NVD 7.5, CVSS 3.1. | NVD, arXiv 2509.10540 |
| Slack MCP server, CVE-2025-34072 | 2025-06-24 | Link-preview bots fetched a URL carrying data | P, U, X | Deprecated, no fix. VulnCheck 9.3, CVSS 4.0. | Embrace The Red |
| Supabase MCP | 2025-07-08 | Ticket instructed an agent with `service_role` | P, U, X | Scoping advised | General Analysis |
| Amazon Q, CVE-2025-8217 | 2025-07-23 | Leaked token let an attacker ship a wipe prompt | Supply chain | 1.85.0. AMZN 5.1, CVSS 4.0. | AWS-2025-015 |
| Gemini CLI | 2025-07-28 | `GEMINI.md` instructions, prefix-only allow-list | P, U, X | 0.1.14. No CVE. | Tracebit |
| CurXecute, CVE-2025-54135 | 2025-08-02. NVD published 2025-08-05. | Agent created an auto-start MCP config | Code execution | 1.3.9. GitHub 8.5, NVD 9.8. | Cursor advisory |
| MCPoison, CVE-2025-54136 | 2025-08-05. NVD published 2025-08-02. | Approved MCP entry changed later | Supply chain | 1.3. GitHub 7.2, NVD 8.8. | Check Point |
| AgentFlayer | 2025-08-06 | Shared document, keys in an image URL on an allowed domain | P, U, X | Fix not checked | Zenity Labs |
| Copilot, CVE-2025-53773 | 2025-08-12 | Agent turned on auto-approve, then ran commands | Code execution | VS 17.14.12. Microsoft 7.8. | Embrace The Red, NVD |
| Comet | 2025-08-20 | Page text treated as user instruction | P, U, X | Partial fix | Brave |
| Nx, CVE-2025-10894 | 2025-08-26 | Malware used local AI CLIs to search for secrets | P, X | Packages removed. Red Hat 9.6. | Nx postmortem |
| ShadowLeak | 2025-09-18 | Email to Deep Research, data sent from vendor servers | P, U, X | Fixed August 2025 | securityaffairs |
| ForcedLeak | 2025-09-25 | Web form field, expired allow-listed domain | P, U, X | Trusted URLs. Noma's own 9.4, no CVE. | Noma Security |
| Claude Pirate | 2025-10-28 | Sandbox code uploaded files through an allowed API domain | P, U, X | Fix not checked | Embrace The Red |
| CVE-2026-21852 | 2026-01-21 | Repo settings redirected API keys before trust | Trust before load | 2.0.65. GitHub 5.3 v4.0, NVD 7.5. | NVD |
| OpenClaw, CVE-2026-25253 | 2026-02-01 | UI sent its token to a URL from the query string | P, X | 2026.1.29. MITRE 8.8. | NVD, depthfirst |
| ClawHub audit, ClawHavoc | 2026-02-02 | 341 of 2,857 skills were malicious. 335 of them were the ClawHavoc campaign. | Supply chain | Scanning added. Unit 42 found five later bypasses. | Unit 42 |
| CVE-2026-29783 | 2026-03-06 | Bash expansion passed the read-only check | Code execution | 0.0.423. GitHub 7.5 v4.0, NVD 7.8. | NVD |
| CVE-2026-12537 | 2026-06-24 | Crafted `.gemini/.env` ran code before the sandbox in CI | Trust before load | CLI 0.39.1. GoogleCloud 10.0 v4.0, NVD 7.8. | NVD |

Johann Rehberger's "Month of AI Bugs" published daily agent vulnerability posts in August 2025. Verified by the research agent.

## 8. Primary sources

All fetched 2026-09-17. Status from curl with a browser user agent unless noted.

### Threat models and standards

- **The lethal trifecta, Simon Willison, 2025** — https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/, 200. Focus: the three parts.
- **Agents Rule of Two, Meta, 2025** — https://ai.meta.com/blog/practical-ai-agent-security/, 200. Focus: properties A to C.
- **Prompt injection attacks against GPT-3, Simon Willison, 2022** — https://simonwillison.net/2022/Sep/12/prompt-injection/, 200.
- **The Dual LLM pattern, Simon Willison, 2023** — https://simonwillison.net/2023/Apr/25/dual-llm-pattern/, 200.
- **OWASP LLM Top 10 2025** — https://genai.owasp.org/llm-top-10/, 200.
- **OWASP GenAI LLM Top 10 2026** — https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/, 200. PDF https://genai.owasp.org/download/56857/?tmstv=1785822482, 200. Focus: new order, LLM09 mitigations.
- **LLM08:2025 Vector and Embedding Weaknesses** — https://genai.owasp.org/llmrisk/llm082025-vector-and-embedding-weaknesses/, 200.
- **OWASP Agentic Top 10 2026** — https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/, 200.
- **OWASP Agentic AI Threats and Mitigations** — https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/, 200. Now serves v1.1.
- **MITRE ATLAS changelog** — https://raw.githubusercontent.com/mitre-atlas/atlas-data/main/CHANGELOG.md, 200.
- **NIST AI 100-2 E2025** — https://csrc.nist.gov/pubs/ai/100/2/e2025/final, 200.
- **MCP Security Best Practices, 2026-07-28** — https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices, 200 by the research agent.

### Injection and measurement

- **Not what you've signed up for, Greshake et al., AISec 2023** — https://arxiv.org/abs/2302.12173, 200. Focus: section 1.
- **AgentDojo, Debenedetti et al., NeurIPS 2024** — https://arxiv.org/pdf/2406.13352, 200. Focus: Tables 1, 3, 5. Appendix D.
- **InjecAgent, Zhan et al., ACL Findings 2024** — https://arxiv.org/pdf/2403.02691, 200. Focus: Table 3.
- **WASP, Evtimov et al., Meta, 2025** — https://arxiv.org/pdf/2504.18575, 200. Focus: Figure 1, Table 2.
- **Security Challenges in AI Agent Deployment, Zou et al., 2025** — https://arxiv.org/pdf/2507.20526, 200. Focus: Table 1, Figure 4.
- **How Vulnerable Are AI Agents to Indirect Prompt Injections?, Dziemian et al., 2026** — https://arxiv.org/pdf/2603.15714, 200.
- **Strengthening AI Agent Hijacking Evaluations, NIST CAISI, 2025** — https://www.nist.gov/news-events/news/2025/01/technical-blog-strengthening-ai-agent-hijacking-evaluations, 200.
- **Mitigating the risk of prompt injections in browser use, Anthropic, 2025** — https://www.anthropic.com/news/prompt-injection-defenses, 200.
- **Understanding prompt injections, OpenAI, 2025** — https://openai.com/index/prompt-injections/, 403 to curl. Read in a browser by the research agent.
- **Hardening ChatGPT Atlas, OpenAI, 2025** — https://openai.com/index/hardening-atlas-against-prompt-injection/, 403 to curl. Read in a browser.

### Defences and limits

- **Spotlighting, Hines et al., Microsoft, 2024** — https://arxiv.org/pdf/2403.14720, 200. Focus: sections 4 and 5.
- **The Instruction Hierarchy, Wallace et al., OpenAI, 2024** — https://arxiv.org/pdf/2404.13208, 200.
- **Llama Prompt Guard 2 model card, Meta** — https://raw.githubusercontent.com/meta-llama/PurpleLlama/main/Llama-Prompt-Guard-2/86M/MODEL_CARD.md, 200. The Hugging Face raw README returns 401, because the model is gated.
- **Prompt Shields, Microsoft** — https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection, 200.
- **The Attacker Moves Second, Nasr, Carlini et al., 2025** — https://arxiv.org/pdf/2510.09023, 200. Focus: Figure 1, section 5, Table 7, Appendices F and G.
- **New prompt injection papers, Simon Willison, 2025** — https://simonwillison.net/2025/Nov/2/new-prompt-injection-papers/, 200.
- **Adaptive Attacks Break Defenses, Zhan et al., NAACL Findings 2025** — https://arxiv.org/pdf/2503.00061, 200.

### Design patterns and information flow

- **Design Patterns for Securing LLM Agents, Beurer-Kellner et al., 2025** — https://arxiv.org/pdf/2506.08837, 200. Focus: section 3.1, Table 1, section 4.4.
- **Defeating Prompt Injections by Design, Debenedetti et al., 2025** — https://arxiv.org/pdf/2503.18813, 200. Focus: Tables 2 and 4, sections 6.5 and 7.
- **CaMeL post, Simon Willison, 2025** — https://simonwillison.net/2025/Apr/11/camel/, 200.
- **Securing AI Agents with Information-Flow Control, Costa et al., Microsoft, 2025** — https://arxiv.org/pdf/2505.23643, 200. Focus: Table 1.

### Tenant isolation

- **Auditing Prompt Caching in Language Model APIs, Gu et al., ICML 2025** — https://arxiv.org/pdf/2502.07776, 200. Focus: Table 1.
- **Implement multitenancy, Pinecone** — https://docs.pinecone.io/guides/index-data/implement-multitenancy, 200.
- **Row Security Policies, PostgreSQL 18** — https://www.postgresql.org/docs/current/ddl-rowsecurity.html, 200.
- **Multi-tenant RAG with Bedrock Knowledge Bases, AWS, 2024** — https://aws.amazon.com/blogs/machine-learning/multi-tenant-rag-with-amazon-bedrock-knowledge-bases/, 200.

### Incidents

- **Slack AI, PromptArmor, 2024** — https://promptarmor.substack.com/p/data-exfiltration-from-slack-ai-via, 200.
- **SpAIware, Embrace The Red, 2024** — https://embracethered.com/blog/posts/2024/chatgpt-macos-app-persistent-data-exfiltration/, 200.
- **GitHub MCP, Invariant Labs, 2025** — https://invariantlabs.ai/blog/mcp-github-vulnerability, 200.
- **Supabase MCP, General Analysis, 2025** — https://www.generalanalysis.com/blog/supabase-mcp-blog, 200.
- **EchoLeak NVD record** — https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2025-32711, 200. Also https://arxiv.org/abs/2509.10540, 200. Aim Security's page returned 403.
- **Copilot RCE, Embrace The Red, 2025** — https://embracethered.com/blog/posts/2025/github-copilot-remote-code-execution-via-prompt-injection/, 200.
- **CurXecute advisory, Cursor** — https://github.com/cursor/cursor/security/advisories/GHSA-4cxx-hrm3-49rm, 200.
- **MCPoison, Check Point, 2025** — https://research.checkpoint.com/2025/cursor-vulnerability-mcpoison/, 200.
- **AWS-2025-015** — https://aws.amazon.com/security/security-bulletins/AWS-2025-015/, 200.
- **Nx postmortem** — https://nx.dev/blog/s1ngularity-postmortem, 200.
- **Gemini CLI, Tracebit, 2025** — https://tracebit.com/blog/code-exec-deception-gemini-ai-cli-hijack, 200.
- **AgentFlayer, Zenity, 2025** — https://labs.zenity.io/p/agentflayer-chatgpt-connectors-0click-attack-5b41, 200.
- **Comet, Brave, 2025** — https://brave.com/blog/comet-prompt-injection/, 200.
- **ShadowLeak, securityaffairs, 2025** — https://securityaffairs.com/182334/hacking/shadowleak-radware-uncovers-zero-click-attack-on-chatgpt.html, 200. Radware's page returned a bot check.
- **ForcedLeak, Noma, 2025** — https://noma.security/blog/forcedleak-agent-risks-exposed-in-salesforce-agentforce/, 200.
- **GitLab Duo, Legit Security, 2025** — https://www.legitsecurity.com/blog/remote-prompt-injection-in-gitlab-duo, 200.
- **Claude Pirate, Embrace The Red, 2025** — https://embracethered.com/blog/posts/2025/claude-abusing-network-access-and-anthropic-api-for-data-exfiltration/, 200.
- **Slack MCP advisory, Embrace The Red, 2025** — https://embracethered.com/blog/posts/2025/security-advisory-anthropic-slack-mcp-server-data-leakage/, 200.
- **Claude Code advisories** — https://github.com/anthropics/claude-code/security/advisories, 200.
- **OpenClaw RCE, depthfirst, 2026** — https://depthfirst.com/post/1-click-rce-to-steal-your-moltbot-data-and-keys, 200.
- **OpenClaw supply chain, Unit 42, 2026** — https://unit42.paloaltonetworks.com/openclaw-ai-supply-chain-risk/, 200.
- **ClawHub skills, The Hacker News, 2026** — https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html, 200.
- **Month of AI Bugs, 2025** — https://monthofaibugs.com/, 200.

### Added by the review, all fetched 2026-09-25

- **PoisonedRAG, Zou et al., 2024, USENIX Security 2025 per arXiv comment** — https://arxiv.org/abs/2402.07867, 200. Focus: abstract, the five-texts result.
- **AgentPoison, Chen et al., 2024** — https://arxiv.org/abs/2407.12784, 200. Focus: abstract. Preprint status not checked.
- **MINJA, Dong et al., 2025** — https://arxiv.org/abs/2503.03704, 200. Focus: the query-only threat model.
- **Graphiti security advisories** — https://github.com/getzep/graphiti/security/advisories, 200. Focus: GHSA-gg5m-55jj-8m5g.
- **Auto mode is now the default in Claude Code, Anthropic, 2026-08-07** — https://claude.com/blog/auto-mode-default-in-claude-code, 200. Focus: the Trajectory Labs paragraphs. Vendor-commissioned.
- **OWASP Agentic Top 10 2026 PDF** — https://genai.owasp.org/download/52117/?tmstv=1765059207, 200.
- **NVD API record for CVE-2025-34072, CVE-2025-54136 and CVE-2025-10894** — https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2025-34072, 200. The NVD API returned 429 twice. It returned 200 after a pause.
- **Other CVE records** — the NVD API for CVE-2025-53773, 54135, 8217, CVE-2026-21852, 25253, 29783, and 12537 returned 200 on my re-check.

## 9. Tools and versions to pin

| Tool | Version | Release date | Source | Notes |
|---|---|---|---|---|
| agentdojo | 0.1.35 | 2025-10-27 | PyPI | Ships suites v1 to v1_2_2. Name the suite version. |
| garak | 0.17.0 | 2026-09-09 | PyPI | Changes not checked |
| pyrit | 1.1.0 | 2026-09-04 | PyPI | Changes not checked |
| promptfoo | 0.123.1 | 2026-09-18 | npm | Was 0.123.0 on 2026-09-17. Changes not checked. |
| inspect-ai | 0.3.268 | 2026-09-22 | PyPI | Was 0.3.264 on 2026-09-17. Releases often. Pin exactly. |
| nemoguardrails | 0.24.1 | 2026-09-16 | PyPI | Module 17 owns it |
| llm-guard | 0.3.16 | 2025-05-19 | PyPI | No release in 16 months |
| llamafirewall | 1.0.3 | 2025-05-29 | PyPI | No release in 15 months |
| snyk-agent-scan | 0.6.4 | 2026-09-21 | PyPI | Was 0.6.3 on 2026-09-17. `mcp-scan` is now a redirect package, not re-checked. |
| Llama Prompt Guard 2 | 86M, 22M | created 2025-04-28 | Hugging Face | Gated. 512-token window. |
| MITRE ATLAS data | 2026.09, format 6.0.0 | 2026-09-15 | GitHub | Old `dist/ATLAS.yaml` frozen at 5.6.0 |

I re-checked all registry versions on 2026-09-17. The reviewer re-checked PyPI and npm on 2026-09-25. agentdojo, garak, pyrit, nemoguardrails, llm-guard and llamafirewall were unchanged. Three rows changed. The ATLAS GitHub API returned a rate-limit error, so the release tag was not re-checked. The CHANGELOG was.

## 10. Open questions and disagreements

- **Do defences work?** Static tests show low ASR: spotlighting below 2%, MetaSecAlign 2% as its own authors reported, Prompt Guard 2 81.2% prevention in Meta's own AgentDojo run. Adaptive search with score feedback reaches 90% or more against most of them. The difference is the attacker. Both results hold under their own conditions.
- **Are models getting safer?** Anthropic reports 1% for Claude Opus 4.5 with 100 adaptive attempts. Gray Swan measured 0.5% per attempt for the same model. Anthropic says 1% is still a risk. The denominators differ.
- **Per attempt versus per session.** ART reports 12.7% per session and near 100% at 10 queries for most models. Gray Swan 2026 reports 0.5% to 8.5% per chat.
- **Diverted versus completed.** WASP saw up to 86% diverted but at most 16.7% completed. The authors say this protection will fade as agents improve.
- **Papers that contradict themselves.** AgentDojo: 47.69% or 57.69%. CaMeL: 300 or 163. InjecAgent swaps the fine-tuned GPT-4 and GPT-3.5 base values between the results text and Table 3: the text says 3.8% and 6.6%, the table says 6.6% for GPT-4 and 3.8% for GPT-3.5. CaMeL: the text calls tool filter the next best defence, Table 7 shows spotlighting lower. Gray Swan 2026: 272,000 or "240K+" attempts. Cite the table. The earlier claim "FIDES: two or three policies" was not confirmed by the reviewer. The FIDES text says "two policies" twice and no "three policies" was found.
- **CVSS by scorer.** CurXecute: GitHub 8.5, NVD 9.8, press 8.6. EchoLeak: Microsoft 9.3, NVD 7.5. Name the scorer and version.
- **Cursor fixed version.** The CurXecute advisory says 1.3.9. Check Point and press say 1.3.
- **OWASP 2026 date.** Page August 3, announcement September 1, PDF "to be set".

## 11. Things I could NOT verify

- **Anthropic per-model chart values.** Image only. Check: the Opus 4.5 system card table.
- **OpenAI injection rates.** No system card checked. The March 2026 post "Designing AI agents to resist prompt injection" was not read.
- **AgentDojo version used by CaMeL and FIDES.** Inferred from 949 and 35. Check: their eval configs.
- **CaMeL and FIDES repository status.** Not fetched.
- **PromptGuard version in Table 7 of "The Attacker Moves Second".** Inferred as 86M from Appendix E.
- **"APR" in the Prompt Guard 2 card.** Not defined on the card.
- **Venues** for Spotlighting, Instruction Hierarchy, Design Patterns, WASP, CaMeL, FIDES, "The Attacker Moves Second", and the Gray Swan papers.
- **Current provider cache sharing.** The audit is from 2024.
- **Aim Security and Radware original write-ups.** 403 and a bot check. Details came from NVD, MSRC, arXiv, and press.
- **Fixes for AgentFlayer and Claude Pirate, and the SpAIware app version.**
- **Fixed versions for CVE-2026-13745, CVE-2026-14898, CVE-2026-19592.** The reviewer found these three IDs nowhere else in the dossier. Their products and sources are not given. Writers must not use them until a source is found.
- **ForcedLeak 9.4.** Noma's own rating only.
- **The full name of OWASP threat T16**, and the v1.0 list.
- **ATLAS release day.** 2026-09-14 in the changelog, 2026-09-15 in the release. The reviewer could not re-check the release, because the GitHub API returned a rate-limit error.
- **Whether AgentDojo runs offline with a scripted model.** Check: the 0.1.35 pipeline code.
- **Release notes for garak, pyrit, and promptfoo.**
- **Reproduction.** Nothing was re-run. "Verified" means the source text says it.

## 12. Notes for the course generator

- **Do not copy attack payloads into prose.** Several fetched papers contain real attack strings. Fixtures must target only the local harness and fake data.
- **Give conditions with every ASR.** State static or adaptive, query budget, base model, and denominator.
- **Name the table.** AgentDojo, CaMeL, InjecAgent, and FIDES each disagree with themselves.
- **Name the AgentDojo version.** "v1, 629 cases" or "v1.2, 949 cases".
- **Use both OWASP editions.** LLM06 is Excessive Agency in 2025 and Unbounded Consumption in 2026. ASI01 is "Agent Goal Hijack" in the PDF, not "Agent Behavior Hijacking" as in the announcement.
- **Link, do not repeat.** MCP trust detail is in Module 6 Phase 5, sections 5.1 to 5.4. Sandboxes and egress are in Module 7 Phases 3 and 4. Identity and tokens are in Module 8 Phases 3 to 5. Cache side channels and the Stanford audit are in Module 1 section 6.2. Semantic cache scope is in Module 4 Phase 6. The earlier note pointed at Module 6 sections 4.8 and 4.9, which do not exist.
- **Pay the commitments in section 13.** Each built module that links here expects the named item. Update each linking module's "planned" wording when the phase is built.
- **The design patterns paper has no numbers.** Code-then-execute numbers come from CaMeL and FIDES.
- **CaMeL's 77% versus 84% is for o3 High.** Gemini 2.5 Pro drops from 73.2% to 41.2%.
- **Fastest to go stale:** tool versions, OWASP 2026 status, ATLAS counts, vendor ASR claims, CVE fixed versions, skill counts.
- **Scenarios.** Use a poisoned knowledge-base upload, a WhatsApp message with instructions, an escalation tool that sends email, and a shared index across customers. Never assign work on the learner's product.
- **Define terms on first use:** zero-click, exfiltration, capability, taint, ASR.

## 13. Commitments owed

Built modules promised these items to Module 16. The reviewer found them with `grep -n "Module 16"` over `study-material/*/*.md` and `*/course.json` on 2026-09-25. Each row gives the promise, where it was made, and the phase that should pay it.

| # | Promise | Made in | Pay in |
|---|---|---|---|
| 1 | Prompt-injection defences in general | `tools-mcp-phase-05-mcp-trust.md` line 45, `tools-mcp-phase-04-mcp-protocol.md` line 967, `agent-harness/course.json` line 60 | Phases 4 and 5 |
| 2 | Defences against tool poisoning, rug pull and shadowing. Defences against a server that lies in its descriptions | `tools-mcp-phase-05-mcp-trust.md` line 154, `tools-mcp/course.json` lines 408 and 502 | Phase 6 |
| 3 | CVE-2025-54136 as approval bound to a name | `tools-mcp-phase-05-mcp-trust.md` line 882, `tools-mcp/course.json` lines 60 and 448 | Phase 6, root cause B, lab 12 |
| 4 | Static-client-ID confused deputy, with per-client consent as the fix | `tools-mcp-phase-05-mcp-trust.md` line 439, `agent-protocols-phase-04-exchange.md` line 355, `agent-protocols/course.json` line 424, `tools-mcp/course.json` lines 57, 412, 508, 510 | Phase 6, section 4.11 |
| 5 | Agent card spoofing as an attack, including the `jku` case from lab E11 | `agent-protocols-phase-02-discovery.md` lines 40 and 293, `agent-protocols/course.json` lines 327 and 442 | Phase 6, section 4.11 |
| 6 | Webhook SSRF as an attack | `agent-protocols-phase-01-tasks.md` line 626, `agent-protocols/course.json` line 358 | Phase 6, section 4.11 |
| 7 | WebMCP tool poisoning as an attack | `agent-protocols-phase-02-discovery.md` line 534, `agent-protocols-phase-03-principals.md` lines 36 and 729 | Phase 6, section 4.11 |
| 8 | Attacks on consent records, tokens and logs | `agent-protocols-phase-05-proof.md` line 45, `agent-protocols/course.json` line 442 | Phase 6. No source in this dossier yet. |
| 9 | Defences against injected text in programmatic tool results, and against malicious Skills | `tools-mcp-phase-03-code-skills.md` lines 442 and 592, `tools-mcp/course.json` lines 280 and 496 | Phases 5 and 6 |
| 10 | The 16 attack classes for code execution in arXiv 2602.15945, sections 5 and 6.3 | `tools-mcp-phase-03-code-skills.md` line 814 | Phase 6. Not fetched by this review. |
| 11 | The attack side of project context files such as `AGENTS.md` and `CLAUDE.md` | `agent-harness-phase-01-loop.md` lines 111 and 775, `agent-harness-phase-05-approval-stack.md` line 730, `agent-harness/course.json` lines 117 and 154 | Phase 2, and lab 11 |
| 12 | The attack side of the Module 7 sandbox CVEs. Module 7 teaches the mechanism only | `agent-harness-phase-04-escape-egress.md` lines 34 and 718, `agent-harness/course.json` line 117 | Phase 6. Do not re-teach the mechanism. |
| 13 | The defence against the untrusted content behind CVE-2025-55284 | `agent-harness-phase-05-approval-stack.md` line 397, `agent-harness/course.json` line 184 | Phase 5 |
| 14 | The Trajectory Labs prompt-injection result, 72 scenarios by 10 runs | `agent-harness-phase-05-approval-stack.md` line 990, `agent-harness/course.json` line 184 | Phase 3. Figures verified by the reviewer, section 3. |
| 15 | Memory poisoning, injection that persists through memory, notes written on purpose | `memory-phase-02-what-to-store.md` lines 626, 641, 856, `memory-phase-04-deletion-scope.md` line 522, `memory-phase-06-prove-it.md` line 778, `memory/course.json` lines 84 and 447 | Phase 2, section 4.10 |
| 16 | The Graphiti Cypher injection fix, "search-filter hardening" | `memory/course.json` lines 84 and 447 | Phase 2 or 7, section 4.10 |
| 17 | Prompt injection through memory files | `context-engineering-phase-04-split-or-file.md` lines 38 and 481, `context-engineering/course.json` line 229 | Phase 2 |
| 18 | Hidden instructions inside uploaded files, including the PDF text layer | `document-ingestion-phase-01-silent-loss.md` line 404, `document-ingestion/course.json` line 32. That line cites "dossier section 4.2". | Phase 2, section 4.2 |
| 19 | Tenant isolation as a security boundary: threat model, attacks and review checklist | `advanced-retrieval-phase-07-tenants-map.md` lines 413, 458, 913, `advanced-retrieval/course.json` lines 32, 374, 439, 477 | Phase 7 |
| 20 | Semantic cache sharing as a threat: CacheAttack content hijack and Early Bird timing | `advanced-retrieval-phase-06-caches-grounding.md` line 438, `advanced-retrieval/course.json` lines 359 and 471 | Phase 7. Module 4 keeps the numbers. |
| 21 | Prompt injection in retrieval loops and the OpenAI search tool | `advanced-retrieval-phase-04-search-loops.md` line 858 | Phase 2 |
| 22 | Red-team evals, and prompt injection as an attack class, including text that steers a judge | `agent-evals-phase-02-gaming.md` lines 311 and 612, `agent-evals/course.json` lines 86 and 443 | Phase 3 |
| 23 | Safety and red-team evals | `eval-engineering/course.json` line 67 | Phase 3 |
| 24 | Plan-then-execute as a prompt-injection defence | `orchestration-durable/course.json` line 66 | Phase 5 |

Three built modules state that "Module 16 section numbers do not exist yet" and link by phase: `advanced-retrieval/course.json` lines 439 and 477. Keep Phase 7 named "Tenant isolation and incident review", or update those links.

## 14. Review log

Reviewer: independent review, 2026-09-25. Sources were fetched into the reviewer's scratchpad `m16review/src/`. PDFs were converted with PyMuPDF and searched as text. No lab was run. No keyed API was called.

### Corrections, with evidence

| # | Kind | Correction | Evidence |
|---|---|---|---|
| C1 | Structure | All nine section 4 headings were topics. They are now claims, per brief rule 1. | BRIEF_research.md, rule 1 |
| C2 | Overlap | The out-of-scope table pointed at Module 6 sections 4.7, 4.8, 4.9 and 7. Those do not exist. Sandboxes are Module 7. Rewritten from real headings. | `grep '^## '` on `tools-mcp/*.md` and `agent-harness/*.md` |
| C3 | Overlap | The dossier said this module adds the Stanford 17-provider audit. Module 1 already teaches it. | `inference-internals-phase-06a-capacity-tenants.md` line 517 |
| C4 | Wrong source | The "Authorize before retrieval" quote is in LLM02:2026, Tier 1 mitigation 3. It is not in LLM09. | LLM 2026 PDF text line 631, inside LLM02, which starts at line 531 and ends before LLM03 at line 720 |
| C5 | Missing condition | Prompt Guard 2 97.5% recall is "Direct Jailbreak Detection" on a Meta "private benchmark". Labelled vendor. | PurpleLlama MODEL_CARD.md, lines 67 to 75 |
| C6 | Precision | "Above 90%" detectors: Table 7 shows Protect AI 90%, Model Armor 90%, PromptGuard 94% on Gemini-2.5 Pro. | arXiv 2510.09023, Table 7 |
| C7 | Missing condition | MetaSecAlign 2% is the MetaSecAlign authors' own static number, reported in 2510.09023 section 4. | 2510.09023 text lines 400 to 402 |
| C8 | Wrong claim | "InjecAgent swaps GPT-4 and GPT-3.5" was too broad. Only the fine-tuned base values are swapped. | 2403.02691 text lines 701 to 703 against Table 3 |
| C9 | Not confirmed | "FIDES: two or three policies". The reviewer found only "two policies". Marked not confirmed. | 2505.23643 lines 976 and 2216 |
| C10 | New contradiction | CaMeL text says tool filter, 8, is next best. Its Table 7 shows spotlighting at 5. | 2503.18813 lines 956 to 958 and Table 7 |
| C11 | New contradiction | Gray Swan 2026 says 272,000 attempts in the abstract and "240K+" in the introduction. | 2603.15714 lines 39 and 152 |
| C12 | Denominator | Gray Swan 2026 ASR is successful attacks per chat, not per attempt. | 2603.15714 section 4.1 |
| C13 | Missing condition | Anthropic 1% uses an "internal Best-of-N attacker" on vendor environments. Labelled vendor. | anthropic.com/news/prompt-injection-defenses |
| C14 | Precision | WASP ranges now name the rows. 16.7% end-to-end is o1 with the instruction hierarchy. | 2504.18575, Table 2 |
| C15 | Missing condition | FIDES Table 1 is the Tool Knowledge attack on gpt-4o. The basic planner with policies also reached 0 after exclusions. | 2505.23643, Table 1 |
| C16 | Missing condition | CaMeL Haiku saving needs Claude 4 Sonnet as the privileged model. The 12% is "estimated". | 2503.18813 line 704 |
| C17 | Incident detail | ClawHavoc is 335 of the 341 skills. 341 spans "multiple campaigns". | The Hacker News, 2026-02-02 |
| C18 | CVE detail | CVE-2026-12537 also covers run-gemini-cli Action before 0.1.22. CVE-2025-61260 covers Codex CLI 0.23.0 and before. | NVD API |
| C19 | CVE dates | NVD publish dates for CVE-2025-54135 and CVE-2025-54136 are the reverse of the table dates. Both dates are now shown. | NVD API: 54135 published 2025-08-05, 54136 published 2025-08-02 |
| C20 | Freshness | promptfoo 0.123.1, inspect-ai 0.3.268, snyk-agent-scan 0.6.4. | PyPI and npm registry JSON, 2026-09-25 |
| C21 | Lab feasibility | Lab 13 and Phase 7 used Docker. The brief says the laptop has no Docker. | BRIEF_research.md, section 5 |
| C22 | Orphan IDs | CVE-2026-13745, CVE-2026-14898, CVE-2026-19592 appear only in section 11. Flagged. | `grep` of the dossier |
| C23 | Gap | Added section 4.10, knowledge-base and memory poisoning. It answers the module question and pays Module 10 commitments. | arXiv 2402.07867, 2407.12784, 2503.03704 abstracts. Graphiti advisory list. |
| C24 | Gap | Added section 4.11, protocol attacks owed by Module 8 and Module 6. | MCP Security Best Practices headings. Module 8 lines cited in section 13. |
| C25 | Gap | Added section 13, 24 commitments owed. | `grep -n "Module 16"` output |
| C26 | Labels | "Verified by me" and "verified by the research agent" were relabelled "verified by the reviewer" where the reviewer re-checked. Preprints and vendor numbers are now labelled. | This log, spot checks below |

### Spot checks

All results below are "matches" unless stated. Source, then the anchor.

| # | Anchor | Source | Result |
|---|---|---|---|
| S1 | Trifecta three parts | Willison post | Matches |
| S2 | Rule of Two "no more than two", property C, supervision quote, date | Meta blog | Matches |
| S3 | AgentDojo 97, 629, 70 tools, 27 injection tasks, 4 suites | 2406.13352 | Matches |
| S4 | AgentDojo GPT-4o 47.69 at 69.00, Claude 3.5 Sonnet 33.86 at 78.22 | 2406.13352 Table 3 | Matches |
| S5 | AgentDojo 57.69, detector 7.95 at 41.49 | Table 5 | Matches |
| S6 | AgentDojo US$35 | Appendix D | Matches. US$4 for utility cases added. |
| S7 | InjecAgent 1,054, 23.6, 47.0 | 2403.02691 Table 3 | Matches. Swap claim narrowed, C8. |
| S8 | WASP 17 to 86, 16.7 | 2504.18575 Table 2 | Matches, C14 |
| S9 | ART 22 agents, 1.8M, 5.7, 27.1, 12.7 | 2507.20526 Table 1 | Matches |
| S10 | Gray Swan 2026 272,000, 13 models, 0.5 to 8.5 | 2603.15714 | Matches, C11, C12 |
| S11 | CAISI 11 to 81, 57 to 80 at 25 | NIST blog | Matches |
| S12 | Anthropic 1%, 100 attempts, "meaningful risk" | Anthropic post | Matches, C13 |
| S13 | Spotlighting >50 to <2, June 2023, 1,000 documents | 2403.14720 | Matches |
| S14 | Instruction hierarchy 63%, GPT-3.5 Turbo | 2404.13208 | Matches |
| S15 | Prompt Guard 2 97.5, 88.7, 81.2, 78.4, 512 tokens | Model card | Numbers match, C5 |
| S16 | Attacker Moves Second authors, "bypass 12", "near-zero" | 2510.09023 | Matches |
| S17 | Detector section: >90, PIGuard 71 | 2510.09023 section 5 | Matches in text, C6 |
| S18 | Table 7 PromptGuard 26 to 94, 0 to 75. MetaSecAlign 5 to 96. GPT-5 Mini detectors 49 to 81. 800 queries. | Table 7 | Matches |
| S19 | Humans 69% versus 100%, 29 scenarios | Appendix F | Matches |
| S20 | Tool Filter and CaMeL skipped, Appendix G | 2510.09023 | Matches |
| S21 | Zhan et al. eight defences, over 50% | 2503.00061 | Matches. Venue not checked. |
| S22 | Design patterns: 14 authors, six headings, principle quote, ten case studies, Recommendation 2, section 4.4 | 2506.08837 | Matches |
| S23 | CaMeL abstract 77 and 84, Table 2 o3 High, Gemini 2.5 Pro, Claude 4 Sonnet | 2503.18813 | Matches |
| S24 | CaMeL Table 4: 297 to 1, 75 to 11, 163, and text 300 | 2503.18813 | Matches |
| S25 | CaMeL Claude 3.5 Sonnet baselines 0, 5, 8, 24, 44 | Table 7 | Matches, C10 |
| S26 | CaMeL 2.82 and 2.73, GPT-4o tokenizer, tool docs not counted | Section 6.5 | Matches |
| S27 | CaMeL side channels | Section 7 | Matches |
| S28 | FIDES "stops all", 1 or 0, basic 163 | 2505.23643 Table 1 | Matches, C15 |
| S29 | Stanford audit 8 of 17, 7 global | 2502.07776 | Matches |
| S30 | PostgreSQL default-deny and FORCE | Docs version 18 | Matches |
| S31 | Pinecone one namespace per tenant, 1 RU per GB | Pinecone docs | Matches |
| S32 | LLM08:2025 quote | OWASP page | Matches |
| S33 | LLM 2026 order and "[Publication date to be set]" | LLM 2026 PDF | Matches |
| S34 | LLM09:2026 quote | LLM 2026 PDF | Wrong entry, C4 |
| S35 | Agentic ASI01 to ASI10 names | Agentic PDF | Matches |
| S36 | ATLAS 2026.09 counts | atlas-data CHANGELOG | Matches |
| S37 | MCP page section names, State Handle Hijacking | MCP 2026-07-28 page | Matches. More headings added. |
| S38 | ForcedLeak $5, Noma 9.4, expired domain | Noma post | Matches |
| S39 | ClawHub 341 of 2,857, Koi | The Hacker News | Matches, C17 |
| S40 | CVE scores: EchoLeak 9.3 and 7.5, CurXecute 8.5 and 9.8, MCPoison 7.2 and 8.8, Amazon Q 5.1 v4.0, Copilot 7.8, Nx 9.6, Slack MCP 9.3 v4.0, CVE-2026-21852 5.3 and 7.5, OpenClaw 8.8, CVE-2026-29783 7.5 and 7.8, CVE-2026-12537 10.0 and 7.8 | NVD API | All match. Dates C19. |
| S41 | Amazon Q syntax error | AWS-2025-015 | Matches |
| S42 | Cursor advisory patched 1.3.9 | GHSA-4cxx-hrm3-49rm | Matches. The advisory lists affected versions up to 1.2.1. |
| S43 | CAISI model is upgraded Claude 3.5 Sonnet | NIST blog | Matches |

### Arithmetic recomputed

| Claim | Recomputed | Result |
|---|---|---|
| InjecAgent 1,054 cases | 17 × 62 = 1,054 | Correct |
| CaMeL o3 High drop | 84.5 − 77.3 = 7.2 | Correct, matches the paper's Difference row |
| CaMeL Gemini 2.5 Pro drop | 73.2 − 41.2 = 32.0 | Correct |
| CaMeL Claude 4 Sonnet drop | 86.6 − 74.2 = 12.4 | Correct |
| Pinecone read units | 100 GB × 1 RU per GB = 100 RU | Correct |
| Trajectory Labs attempts | 72 × 10 = 720. 5.83% of 720 = 42.0 | Correct |
| Gray Swan 2026 pooled rate | 8,648 / 272,000 = 3.18% | Added, not in the paper as one number |
| ClawHub share | 341 / 2,857 = 11.9% | Added |
| llm-guard months without release | 2025-05-19 to 2026-09-17 = 15.97 months | "16 months" is correct |
| llamafirewall months without release | 2025-05-29 to 2026-09-17 = 15.6 months | "15 months" is correct, rounded down |
| CAISI retries if independent | 1 − 0.43^25 ≈ 1.000, against the reported 80% | The attempts were not independent. Inferred. Lab 6 should print this gap. |
| AgentDojo 97 × 27 | 2,619, not 629 | 629 counts pairs within each suite, not all pairs. The per-suite counts are not checked. |

### What the reviewer could not check

- Raw sources from the 2026-09-17 research. None were found under `_curriculum/raw-research/` or the research scratchpad. Every claim was re-fetched or left with its old label.
- AgentDojo v1.2 counts, 35 injection tasks and 949 cases, from the 0.1.35 wheel. The reviewer did not download the wheel. CaMeL and FIDES both state 949 attacks.
- ATLAS technique IDs AML.T0080, AML.T0086, AML.T0110. The GitHub API rate limit blocked the data file.
- The CaMeL Table 4 row for o3 High and GPT-4o. Not read.
- The incidents that were not re-fetched: Slack AI, SpAIware, GitLab Duo, GitHub MCP, Supabase MCP, Gemini CLI, AgentFlayer, Comet, ShadowLeak, Claude Pirate, OpenClaw depthfirst, Unit 42.
- The OpenAI pages. Both returned 403 to curl for the author. Not retried.
- Venues for InjecAgent, Zhan et al., WASP and the Gray Swan papers.
- arXiv 2602.15945, the 16 attack classes owed by Module 6.
- Attacks on consent records and logs, commitment 8. No source is in the dossier.
- Whether the "Date" column in section 7 is the disclosure date or the write-up date. The table does not say.

Summary of the review: 26 corrections, 43 spot checks, one wrong source for a key quote, one vendor number missing its benchmark, two new sections, and 24 commitments owed.

Summary: design so that an injection cannot cause harm, and test every defence against an adaptive attacker with stated conditions.

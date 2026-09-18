# Module 16 — Security and threat modelling for LLM applications and agents

Research date: 2026-09-17. Status: research dossier, not course material.

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

| Topic | Where it lives |
|---|---|
| MCP protocol, auth flows, poisoning and rug-pull detector lab | Module 6, sections 4.7 and 4.8, labs 11 and 12 |
| Sandbox internals | Module 6, section 4.9 |
| Agent loop and permission prompts | Module 7 |
| OAuth flows and per-agent identity | Module 8 |
| Production guardrail pipelines, per-tenant policy | Module 17 |
| Audit logs and retention | Module 18 |
| Approval screen design | Module 19 |
| Harmful-content jailbreaks, offensive work on real systems | Not covered |

### Overlap with earlier modules

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| Prefix cache timing side channel, `cache_salt` | Module 1, section 6.2 | The Stanford audit of 17 API providers |
| Tool poisoning and rug pulls | Module 6, section 4.8 | Design-level defences, skill marketplace incidents |
| MCP and Claude Code CVEs | Module 6, section 7 | Grouping by root cause |
| Sandboxes | Module 6, section 4.9 | Only the rule that a sandbox does not stop data leaving through an allowed domain |

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
| MCP spec renames Session Hijacking | spec 2026-07-28 | modelcontextprotocol.io | Now "State Handle Hijacking" |

## 4. Core concepts, with verified facts

### 4.1 The lethal trifecta and the Rule of Two

An agent can leak data when three things meet in one context: private data, untrusted content, and a way to send data out. Removing any one of the three blocks this kind of leak. Meta's rule adds state changes to the third property, so it also covers harmful actions.

- Willison's three parts: "Access to your private data", "Exposure to untrusted content", "The ability to externally communicate". 16 June 2025. Verified by raw-text search.
- Meta: agents "must satisfy no more than two of the following three properties within a session". The third property is "change state or communicate externally". October 31, 2025. Verified.
- If all three are needed, Meta says the agent "should not be permitted to operate autonomously and at a minimum requires supervision". Verified by the research agent. The post has no numbers.
- Willison named "prompt injection" on 12 September 2022. Greshake et al. introduced "Indirect Prompt Injection" in arXiv 2302.12173 on 23 February 2023, published at ACM AISec 2023. Verified. Earlier uses were not checked.

Where the example stops working: the trifecta covers data theft only. Deleting records needs no outbound channel. The Rule of Two covers that case.

### 4.2 Injection channels and exit channels

Any text that reaches the context can carry instructions. The incidents in section 7 show the usual ways in and out.

- Ways in: email, public chat channels, GitHub issues, support tickets, web forms, shared documents, web pages, and repository files such as `GEMINI.md`. The matching incidents are EchoLeak, Slack AI, GitHub MCP, Supabase MCP, ForcedLeak, AgentFlayer, Comet, and Gemini CLI. Verified per incident.
- Ways out: auto-loaded Markdown images, clicked links, link-preview bots, public pull requests, the app's own reply thread, an expired allow-listed domain, an allowed API domain, and browsing from the vendor's servers. Verified per incident.
- In ForcedLeak, the allow-listed domain had expired and the researchers bought it for $5. Source: Noma Security. Verified.
- In ShadowLeak, data left from OpenAI's servers, so client-side controls could not see it. Verified from securityaffairs quoting Radware. Radware's page returned a bot check.
- The design patterns paper has a "Customer Service Chatbot" case study in section 4.4. Verified from Table 1.

### 4.3 Measuring attack success

Attack success rate, or ASR, is the share of attempts where the attacker's goal happened. Benchmarks define the denominator and the success check differently, so their numbers are not directly comparable.

- AgentDojo v1, by ETH Zurich and Invariant Labs, NeurIPS 2024: 4 suites, 70 tools, 97 user tasks, 27 injection tasks, 629 security cases. arXiv 2406.13352, Table 1. Verified.
- AgentDojo v1.2 has 35 injection tasks and 949 cases. The research agent counted this in the agentdojo 0.1.35 wheel. CaMeL and FIDES report 949 attacks. The version they used is inferred.
- AgentDojo Table 3, "Important message" attack: GPT-4o ASR 47.69% at 69.00% utility. Claude 3.5 Sonnet 33.86% at 78.22%. Verified. Table 5 gives GPT-4o no-defence ASR as 57.69%. The paper contradicts itself.
- AgentDojo cost about US$35 for 629 cases on GPT-4o at 2024 prices. Appendix D. Verified.
- InjecAgent, by UIUC, ACL Findings 2024: 1,054 cases. ReAct GPT-4 ASR-valid 23.6% base, 47.0% enhanced. ASR-valid counts only well-formed outputs. Table 3. Verified.
- WASP, by FAIR at Meta, 2025, tests web agents. the agent was diverted in 17% to 86% of cases. The attacker goal was completed in at most 16.7%. The authors call this "security by incompetence". arXiv 2504.18575, Table 2. Verified.
- Gray Swan and UK AISI ART competition: 22 agents, 1.8 million attacks. Per-session ASR: direct 5.7%, indirect 27.1%. arXiv 2507.20526, Table 1. Verified.
- Gray Swan 2026: 272,000 attempts on 13 models. Success required the harmful action and hiding it. Per-attempt ASR 0.5% for Claude Opus 4.5 to 8.5% for Gemini 2.5 Pro. arXiv 2603.15714. Verified.
- US CAISI on upgraded Claude 3.5 Sonnet in AgentDojo: new attacks reached 81%, against 11% for the best baseline. With 25 attempts, average ASR rose from 57% to 80%. NIST blog, January 17, 2025. Verified.
- Anthropic's page description: "Claude Opus 4.5 achieves a 1% attack success rate against prompt injections in browser use". The attacker had "100 attempts per environment". The page says 1% "still represents meaningful risk". Verified. Per-model chart values are not checked.

Retries raise ASR. A low per-attempt rate is not low risk when the attacker can retry.

### 4.4 Detectors, training defences, and adaptive attacks

A detector is a classifier that flags injected text. A training defence teaches the model to ignore injected instructions. An adaptive attacker changes the attack using feedback from the defence. Most detector and training defences fail against adaptive attackers.

- Spotlighting, by Microsoft, arXiv 2403.14720, "reduces the attack success rate from greater than 50% to below 2%". Conditions: June 2023 GPT-3.5 and GPT-4, 1,000 synthetic documents, a simple keyword payload. Not adaptive. Verified.
- Instruction hierarchy, by OpenAI, arXiv 2404.13208: system prompt extraction robustness "improved by 63%" on fine-tuned GPT-3.5 Turbo. Verified.
- Llama Prompt Guard 2 86M, by Meta: 97.5% recall at 1% false positive rate on English. On AgentDojo, "APR @ 3% utility reduction" is 81.2%. The 22M model: 88.7% and 78.4%. Source: PurpleLlama model card. Verified by me. "APR" is read as attack prevention rate, which is inferred.
- AgentDojo's BERT detector cut GPT-4o ASR to 7.95% but cut utility from 69.0% to 41.49%. Table 5. Verified.
- "The Attacker Moves Second" has authors from OpenAI, Anthropic, Google DeepMind, ETH Zürich and others. It says: "we bypass 12 recent defenses ... with attack success rate above 90% for most". Most defences "originally reported near-zero attack success rates". Verified by me.
- Detectors, section 5.3: a search attack given the detector's score "achieves ASR of >90% against Protect AI, PromptGuard, and Model Armor (with Gemini-2.5 Pro as the base model)". PIGuard "still reaches 71% ASR". Verified by me.
- Table 7, AgentDojo, 800-query budget, static to adaptive ASR. PromptGuard: 26 to 94 on Gemini-2.5 Pro, 0 to 75 on GPT-5 Mini. MetaSecAlign 70B: 5 to 96. Verified by the research agent.
- Humans: "the search attack succeeds 69% of the time whereas the red-teaming humans collectively succeeds 100% of the time". 29 scenarios. Verified by me.
- Zhan et al., NAACL Findings 2025, arXiv 2503.00061: eight defences on InjecAgent, all bypassed at over 50% ASR. Vicuna-7B and Llama3-8B agents. Verified.

Correction to the module plan: the plan said detectors fail "above 90 percent". That holds for three of four detectors on Gemini-2.5 Pro with score feedback and 800 queries. PIGuard stayed at 71%. On GPT-5 Mini the detectors reached 49% to 81%.

### 4.5 Design patterns that limit harm

These patterns limit what the agent can do after it reads untrusted input. The paper's principle: "once an LLM agent has ingested untrusted input, it must be constrained so that it is impossible for that input to trigger any consequential actions". They give up some utility for a property that does not depend on the model.

- arXiv 2506.08837, v3 27 June 2025. 14 authors listed alphabetically, from Invariant Labs, IBM, EPFL, ETH Zurich, Swisscom, Google, Microsoft, Kyutai and others. Verified by me. Willison's post says "11 authors". The paper lists 14.
- Exact headings: "The Action-Selector Pattern", "The Plan-Then-Execute Pattern", "The LLM Map-Reduce Pattern", "The Dual LLM Pattern", "The Code-Then-Execute Pattern", "The Context-Minimization pattern". Section 3.1. Verified by me.
- Ten case studies. Recommendation 2: "no single pattern is likely to suffice across all threat models or use cases". Verified by me.
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

### 4.6 CaMeL and FIDES

CaMeL applies Code-Then-Execute with information-flow tracking. A privileged LLM writes Python from the trusted query only. A quarantined LLM turns untrusted data into typed values and cannot call tools. A custom interpreter labels every value and checks policies at each tool call. "Capability" here means a security label, not model skill.

- Authors from Google, Google DeepMind, and ETH Zurich. arXiv 2503.18813 v2, 24 June 2025. Verified by me.
- Abstract: "solving 77% of tasks with provable security (compared to 84% with an undefended system)". This matches the o3 High row of Table 2: 77.3% against 84.5%. Verified. The model link comes from Table 2.
- Other models lose more. Gemini 2.5 Pro: 73.2% to 41.2%. Claude 4 Sonnet: 86.6% to 74.2%. Table 2. Verified by the research agent.
- Out of 949 attacks, Table 4: Gemini 2.5 Flash 297 successes native, 1 with CaMeL. Claude 4 Sonnet 75 and 11. Verified by the research agent.
- Section 6.2.1 says Gemini 2.5 Pro "drops from 300 without to 0". Table 4 says 163 native. The paper contradicts itself. Verified by me.
- On Claude 3.5 Sonnet: CaMeL 0 successful attacks, spotlighting 5, tool filter 8, prompt sandwiching 24, undefended 44. Verified.
- Cost: "2.82× input tokens and 2.73× more output tokens for the median task". Claude 3.5 Sonnet, GPT-4o tokenizer, tool docs not counted. Section 6.5. Verified by me.
- A Claude 3.5 Haiku quarantined model cost about 1% utility for about 12% lower cost. Verified by me.
- Section 7: "CaMeL is vulnerable to side-channel attacks", through external resources, exceptions that leak one bit, and timing. Verified by me.
- FIDES, by Microsoft, arXiv 2505.23643, tracks confidentiality and integrity labels. "With policy checks enabled, FIDES stops all prompt injection attacks in AgentDojo." On gpt-4o it allowed 1 injection, or 0 after two out-of-scope tasks are removed. The basic planner allowed 163. Verified by the research agent.
- "The Attacker Moves Second" skipped Tool Filter and CaMeL "because the attack is guaranteed to fail in most of the selected scenarios". Appendix G. Verified by the research agent.

### 4.7 Tool and agent supply chain

Tool descriptions, skills, and project config files are all third-party input. Module 6 covers MCP mechanisms. This module groups recent CVEs by root cause, so the learner can review a new agent for the same faults.

- **A. Trust before load.** Project files run code or redirect traffic before the user accepts trust. Examples: Claude Code CVE-2026-21852, where settings set `ANTHROPIC_BASE_URL`, fixed 2.0.65. Gemini CLI CVE-2026-12537, fixed CLI 0.39.1. Codex CLI CVE-2025-61260. Verified from NVD.
- **B. Approval bound to a name.** Cursor CVE-2025-54136: an approved MCP entry changed later and ran without a new prompt. Fixed 1.3. Verified.
- **C. The agent writes its own config.** Cursor CVE-2025-54135 created `.cursor/mcp.json`, fixed 1.3.9. Copilot CVE-2025-53773 set auto-approve in `.vscode/settings.json`, fixed in VS 2022 17.14.12. Verified.
- **D. Allow-lists that check command text.** Gemini CLI before 0.1.14 checked only the start of a command. Copilot CLI CVE-2026-29783 missed bash parameter expansion, fixed 0.0.423. Verified.
- **E. Compromised publisher.** Amazon Q extension 1.84.0 shipped injected code, CVE-2025-8217, fixed 1.85.0. AWS says a syntax error stopped it. Nx CVE-2025-10894 packages called local AI CLIs with confirmations turned off. Verified from AWS, NVD, and the Nx postmortem.
- An audit of 2,857 ClawHub skills found 341 malicious ones, credited to Koi Security. Verified from The Hacker News and Unit 42.
- The MCP security page for spec 2026-07-28 lists Confused Deputy, Token Passthrough, SSRF, State Handle Hijacking, Local MCP Server Compromise, and Scope Minimization, among others. Verified by the research agent.

### 4.8 Tenant isolation

A multi-tenant app shares indexes, caches, and memory across customers. Leaks come from retrieval, shared memory, or shared caches. The fix is to enforce access in the data layer before the model sees anything.

- OWASP LLM08:2025 warns of "context leakage between users or queries" in shared vector databases. Verified by me.
- OWASP LLM09:2026: "Authorize before retrieval: enforce document- and chunk-level authorization inside the index query, not at the application layer after retrieval." Verified by the research agent from the PDF.
- Pinecone recommends "one namespace per tenant". A query on a 1 GB namespace costs 1 read unit. A filtered query on a shared 100 GB namespace costs 100. Quote verified by me. Read units verified by the research agent.
- PostgreSQL 18: "If no policy exists for the table, a default-deny policy is used." Table owners bypass row-level security unless the table uses `FORCE ROW LEVEL SECURITY`. Verified by me.
- Gu et al. at Stanford, ICML 2025, arXiv 2502.07776: "We detected prompt caching in 8 out of 17 API providers. In 7 of these providers, we detected global cache sharing." Audited September and October 2024. Verified by me. Current behaviour is not checked.
- Module 1 section 6.2 teaches `cache_salt`. Link it.

### 4.9 Standards for structuring a review

The three OWASP lists, verified. The 2025 list is from the OWASP site. The 2026 lists are from the PDFs. The LLM 2026 PDF still says "[Publication date to be set]".

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


- MITRE ATLAS 2026.09: "16 tactics, 120 techniques, 88 sub-techniques, 40 mitigations, and 73 case studies". Verified by me. Relevant IDs: AML.T0051 LLM Prompt Injection, AML.T0080 AI Agent Context Poisoning, AML.T0086 Exfiltration via AI Agent Tool Invocation, AML.T0110 AI Agent Tool Poisoning. Verified by the research agent.
- NIST AI 100-2 E2025, adversarial ML taxonomy, March 2025. Verified.

## 5. Proposed phase outline

| Phase | Title | What it teaches | Labs | Runs where, costs what |
|---|---|---|---|---|
| 1 | Threat model | Trust boundaries, trifecta, Rule of Two, OWASP and ATLAS mapping | 1, 2 | Laptop, offline |
| 2 | Injection and exit channels | Direct and indirect injection, rendering and link exits, memory persistence | 3, 4 | Laptop, offline |
| 3 | Measuring attack success | ASR variants, denominators, retries, intervals, AgentDojo structure | 5, 6 | Laptop. Optional AgentDojo live run needs an API key. Re-price first. |
| 4 | Detectors and adaptive attacks | Spotlighting, instruction hierarchy, Prompt Guard 2, score feedback, utility cost | 7, 8 | Laptop. Optional Prompt Guard 2 22M on CPU needs gated model access. |
| 5 | Design patterns, CaMeL, FIDES | Six patterns, capability labels, policies, side channels, token cost | 9, 10 | Laptop, offline |
| 6 | Tool and agent supply chain | Root causes A to E, skills, publisher compromise. Links Module 6. | 11, 12 | Laptop, offline |
| 7 | Tenant isolation and incident review | Authorization before retrieval, RLS pitfalls, cache sharing, ten incidents | 13, 14, 15 | Laptop with Docker Postgres. No cloud cost. |

Seven phases fit because almost all of this is new. Module 1 covers only the cache side channel, and Module 6 covers MCP mechanisms and sandboxes. Measurement and adaptive attacks each need a phase, because the headline numbers mislead without their conditions.

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
13. **RLS leakage test.** Postgres 18 in Docker with per-tenant policies. Prints rows visible to the app role, the owner, the owner with `FORCE`, and a `BYPASSRLS` role. Break-it: connect as the owner without `FORCE`. Self-test: fixed matrix.
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
| CurXecute, CVE-2025-54135 | 2025-08-02 | Agent created an auto-start MCP config | Code execution | 1.3.9. GitHub 8.5, NVD 9.8. | Cursor advisory |
| MCPoison, CVE-2025-54136 | 2025-08-05 | Approved MCP entry changed later | Supply chain | 1.3. GitHub 7.2, NVD 8.8. | Check Point |
| AgentFlayer | 2025-08-06 | Shared document, keys in an image URL on an allowed domain | P, U, X | Fix not checked | Zenity Labs |
| Copilot, CVE-2025-53773 | 2025-08-12 | Agent turned on auto-approve, then ran commands | Code execution | VS 17.14.12. Microsoft 7.8. | Embrace The Red, NVD |
| Comet | 2025-08-20 | Page text treated as user instruction | P, U, X | Partial fix | Brave |
| Nx, CVE-2025-10894 | 2025-08-26 | Malware used local AI CLIs to search for secrets | P, X | Packages removed. Red Hat 9.6. | Nx postmortem |
| ShadowLeak | 2025-09-18 | Email to Deep Research, data sent from vendor servers | P, U, X | Fixed August 2025 | securityaffairs |
| ForcedLeak | 2025-09-25 | Web form field, expired allow-listed domain | P, U, X | Trusted URLs. Noma's own 9.4, no CVE. | Noma Security |
| Claude Pirate | 2025-10-28 | Sandbox code uploaded files through an allowed API domain | P, U, X | Fix not checked | Embrace The Red |
| CVE-2026-21852 | 2026-01-21 | Repo settings redirected API keys before trust | Trust before load | 2.0.65. GitHub 5.3 v4.0, NVD 7.5. | NVD |
| OpenClaw, CVE-2026-25253 | 2026-02-01 | UI sent its token to a URL from the query string | P, X | 2026.1.29. MITRE 8.8. | NVD, depthfirst |
| ClawHavoc | 2026-02-02 | 341 of 2,857 skills were malicious | Supply chain | Scanning added. Unit 42 found five later bypasses. | Unit 42 |
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
- **Other CVE records** — the NVD API for CVE-2025-53773, 54135, 8217, CVE-2026-21852, 25253, 29783, and 12537 returned 200 on my re-check.

## 9. Tools and versions to pin

| Tool | Version | Release date | Source | Notes |
|---|---|---|---|---|
| agentdojo | 0.1.35 | 2025-10-27 | PyPI | Ships suites v1 to v1_2_2. Name the suite version. |
| garak | 0.17.0 | 2026-09-09 | PyPI | Changes not checked |
| pyrit | 1.1.0 | 2026-09-04 | PyPI | Changes not checked |
| promptfoo | 0.123.0 | 2026-09-10 | npm | Changes not checked |
| inspect-ai | 0.3.264 | 2026-09-17 | PyPI | Releases often. Pin exactly. |
| nemoguardrails | 0.24.1 | 2026-09-16 | PyPI | Module 17 owns it |
| llm-guard | 0.3.16 | 2025-05-19 | PyPI | No release in 16 months |
| llamafirewall | 1.0.3 | 2025-05-29 | PyPI | No release in 15 months |
| snyk-agent-scan | 0.6.3 | 2026-09-10 | PyPI | `mcp-scan` is now a redirect package |
| Llama Prompt Guard 2 | 86M, 22M | created 2025-04-28 | Hugging Face | Gated. 512-token window. |
| MITRE ATLAS data | 2026.09, format 6.0.0 | 2026-09-15 | GitHub | Old `dist/ATLAS.yaml` frozen at 5.6.0 |

I re-checked all registry versions on 2026-09-17.

## 10. Open questions and disagreements

- **Do defences work?** Static tests show low ASR: spotlighting below 2%, MetaSecAlign 2%, Prompt Guard 2 81.2% prevention. Adaptive search with score feedback reaches 90% or more against most of them. The difference is the attacker. Both results hold under their own conditions.
- **Are models getting safer?** Anthropic reports 1% for Claude Opus 4.5 with 100 adaptive attempts. Gray Swan measured 0.5% per attempt for the same model. Anthropic says 1% is still a risk. The denominators differ.
- **Per attempt versus per session.** ART reports 12.7% per session and near 100% at 10 queries for most models. Gray Swan 2026 reports 0.5% to 8.5% per attempt.
- **Diverted versus completed.** WASP saw up to 86% diverted but at most 16.7% completed. The authors say this protection will fade as agents improve.
- **Papers that contradict themselves.** AgentDojo: 47.69% or 57.69%. CaMeL: 300 or 163. InjecAgent swaps GPT-4 and GPT-3.5 between text and table. FIDES: two or three policies. Cite the table.
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
- **Fixed versions for CVE-2026-13745, CVE-2026-14898, CVE-2026-19592.**
- **ForcedLeak 9.4.** Noma's own rating only.
- **The full name of OWASP threat T16**, and the v1.0 list.
- **ATLAS release day.** 2026-09-14 in the changelog, 2026-09-15 in the release.
- **Whether AgentDojo runs offline with a scripted model.** Check: the 0.1.35 pipeline code.
- **Release notes for garak, pyrit, and promptfoo.**
- **Reproduction.** Nothing was re-run. "Verified" means the source text says it.

## 12. Notes for the course generator

- **Do not copy attack payloads into prose.** Several fetched papers contain real attack strings. Fixtures must target only the local harness and fake data.
- **Give conditions with every ASR.** State static or adaptive, query budget, base model, and denominator.
- **Name the table.** AgentDojo, CaMeL, InjecAgent, and FIDES each disagree with themselves.
- **Name the AgentDojo version.** "v1, 629 cases" or "v1.2, 949 cases".
- **Use both OWASP editions.** LLM06 is Excessive Agency in 2025 and Unbounded Consumption in 2026. ASI01 is "Agent Goal Hijack" in the PDF, not "Agent Behavior Hijacking" as in the announcement.
- **Link, do not repeat.** MCP detail is in Module 6, sections 4.8 and 4.9. Cache side channels are in Module 1, section 6.2.
- **The design patterns paper has no numbers.** Code-then-execute numbers come from CaMeL and FIDES.
- **CaMeL's 77% versus 84% is for o3 High.** Gemini 2.5 Pro drops from 73.2% to 41.2%.
- **Fastest to go stale:** tool versions, OWASP 2026 status, ATLAS counts, vendor ASR claims, CVE fixed versions, skill counts.
- **Scenarios.** Use a poisoned knowledge-base upload, a WhatsApp message with instructions, an escalation tool that sends email, and a shared index across customers. Never assign work on the learner's product.
- **Define terms on first use:** zero-click, exfiltration, capability, taint, ASR.

Summary: design so that an injection cannot cause harm, and test every defence against an adaptive attacker with stated conditions.

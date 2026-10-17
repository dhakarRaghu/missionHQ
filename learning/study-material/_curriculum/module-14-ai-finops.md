# Module 14: Cost, routing, and AI FinOps

Research date: 2026-09-25. Status: research dossier, not course material. Reviewed on 2026-09-25 by an independent reviewer. Section 10, Review log, lists every correction.

Module question: **The bill doubled and the traffic did not. Which tenant, which route, and which model change caused it?**

Topic id: `ai-finops`. The question is the one in `_curriculum/README.md`, section "### Module 14".

## How this dossier was built

- **Inputs.** Two research reports written on 2026-09-25 in `scratchpad/reports/`. Below they are the metering report, `research_ai-finops_metering.md`, and the cascades report, `research_ai-finops_cascades.md`.
- **Path short names.** `S/` means the research scratchpad. `RM/` means `S/research_ai-finops/metering/`. `RC/` means `S/research_ai-finops/cascades/`. `D14/` means `S/dossier_m14/`, the dossier author's notes.
- **Other inputs.** The Module 14 brief in `_curriculum/README.md`. The rules in `S/briefs/BRIEF_research.md`, `research-method.md` and `writing-style.md`. The structure of `_curriculum/module-10-memory.md`.
- **Work done for this dossier.** No lab ran. No URL was fetched. The dossier author did four read-only things:
  1. Re-grepped 75 anchors of section 4 in their saved files. Script `D14/anchor_check.py`, output `D14/anchor_check.txt`. **75 of 75 match.** Section 9.4 has the detail.
  2. Recomputed every arithmetic claim with `D14/recompute.py`. Output `D14/recompute.txt`. **79 of 79 checks agree** with the stated values. Part E of that file holds new arithmetic for sections 5 and 6.
  3. Read both prototypes, `RM/proto/bill_diff.py` and `RC/proto/bill_drivers.py`, and their saved outputs. Section 6.1 compares them.
  4. Read the LiteLLM schema at tag v1.102.1 again. This corrected one claim of the metering report. See conflict a in section 7.
- **Labels.** Every claim is **verified**, **verified by run**, **inferred** or **not checked**. A verified claim names its file and line, or its table. "Verified by run" means a research agent ran a script on the learner's Apple arm64 Mac on 2026-09-25. The output file is named. An inferred claim names its basis and the check that would confirm it. **Vendor claim** marks a number that a company published about its own product.
- **Run conditions for every prototype number.** Python 3.9.6, standard library only, Apple arm64, 2026-09-25. The cascades report names the machine as an Apple M4 Pro. Machine load is not recorded. Not checked.
- **Terms used in the whole dossier.**
  - **Tenant**: a customer account whose usage you bill or report on its own.
  - **Route**: one product feature or API endpoint, such as `/chat` or `summarize`.
  - **Request**: one user-facing call into your service. It is the root of a trace.
  - **Model call**: one call from your service to a model provider. One request can make several model calls.
  - **Fan-out**: one request that makes several model calls, often through sub-agents.
  - **Gateway**: a proxy between your code and the model providers. It meters tokens and can enforce budgets.
  - **Spend log**: the table where a gateway writes one row per model call.
  - **Token classes**: uncached input, cache read, cache write, output and reasoning tokens. Each has its own price. Module 1, 3.1 owns them.
  - **Admission**: the gateway's decision to let a request start.
  - **Reservation**: an amount of budget held before a call, then settled to the real cost after it.
  - **Overshoot**: spend above a budget limit.
  - **Decomposition**: a split of a bill change into parts, one per cause, that sum to the change.
  - **Shapley split**: a decomposition that averages each factor's effect over every order of applying the factors.
  - **LMDI**: logarithmic mean Divisia index. A decomposition that weights the log change of each factor.
  - **Cascade**: a cheap model answers first. A signal decides whether to escalate to a stronger model.
  - **Router**: a model or rule that picks one model per request before any model answers.
  - **Holdout**: a randomly chosen group of users that keeps the old configuration, to compare against.
  - **Showback**: a report that shows each team its cost. **Chargeback**: a formal transfer of that cost to the team's budget.

---

## 1. What this module is for

Module 1 teaches the cost of one request. This module teaches the cost of many tenants over a month. It covers what a gateway meters and how cost reaches a tenant. It also covers how a budget stops spend, and how to explain a bill change.

The short answer: **log every model call with the fields that separate the causes.** Without them you cannot name the tenant, route and model change. Those fields are the tenant, the route, the requested and responded model, the token classes, the service tier, and the price version. Then an exact decomposition splits the change.

| Part of the question | Short answer | Where |
|---|---|---|
| Which tenant | Stamp the tenant on the root request. Pass it to every child call. Sum cost from the model-call rows by that tenant | 4.5 |
| Which route | Log the route on every row. Split the change per tenant and route with a method that does not depend on order | 4.7 |
| Which model change | A model change shows up as model mix. A second step compares the old and new model on the same route. It splits price per token, output length and tokens per call | 4.8 |
| Why traffic can stay flat | Requests stayed flat, but model calls per request, tokens per call or cache hits changed | 4.4, 4.7 |
| Why the log may not answer it | Many per-call logs lack cache columns. Then a cache collapse looks like a price rise | 4.4 |
| How to stop it next month | A budget stops new requests, not running ones. It needs a reservation and a price for every model | 4.1, 4.2, 4.3 |
| Why the same model can cost 2x | A service-tier flag, a long-context tier or a per-request fee changes the price with no model change | 4.15 |
| Whether a router caused it | Routers can raise the bill. Published savings are offline estimates. Measure against a holdout and count costs on other teams' lines | 4.9 to 4.12 |
| Who owns the fix | A named owner per cost line, with showback first | 4.14 |

Summary: log every model call with its separating fields. Split the change exactly. Then compare the old and new model on each changed route.

---

## 2. Scope

### In scope

- Gateways on 2026-09-25: LiteLLM, Portkey, Kong AI Gateway, Agent Router, Cloudflare AI Gateway and OpenRouter. What each meters and when each charges a budget.
- Per-tenant attribution when one request fans out to several models or agents.
- Budget enforcement: admission, reservation, overshoot, and behaviour during a stream.
- The spend-log fields that make a bill change explainable.
- Bill-change decomposition by tenant, route, model and factor.
- Model choice as a runtime decision, measured at the organization level. This covers estimated against measured savings, router overhead at today's prices, and costs on other teams.
- Forecast drivers for LLM spend.
- Ownership, showback and chargeback from FinOps Foundation material.
- Token-class prices on 2026-09-25, used as inputs only.

### Out of scope, and the owner of each item

| Topic | Owner |
|---|---|
| The per-request cost function, the five token classes, tier and modality multipliers | Module 1, built sections 3.1, 3.2 and 3.3 |
| Cache break-even for 5-minute and 1-hour writes | Module 1, built section 3.3, "The break-even, derived" |
| Cascade and router cost arithmetic, the random-escalation control, escalation signals ranked, LLMRouterBench under-routing, RouteLLM benchmark dependence | Module 1, built section 3.4 |
| Per-request budget, rolling cost, cache-hit floor, the ledger, the reservation pattern, the three breach responses | Module 1, built section 3.5 |
| OpenTelemetry GenAI names, the four attribution axes, the minimum run record | Module 1, built section 5.5 |
| Per-tenant token quotas, fair scheduling, `cache_salt` | Module 1, built section 6.2 |
| Intervals for small sets, clustered questions, paired sizing, gating on a lower bound | Module 11, built sections 5.1 to 5.4 and 6.2 |
| A/B test sizing, peeking, must-not-worsen metrics, feedback | Module 12, built sections 4.1 to 4.4 |
| Judge cost on long trajectories | Module 12, built section 5.2 |
| Self-hosting economics, cost per token against utilisation, provisioned capacity purchase | Module 1, built section 4.6. Module 13, planned. Its dossier is `_curriculum/module-13-serving-cluster.md` |
| Service-tier and modality multipliers as prices | Module 1, built section 3.1. Concept 4.15 adds only the spend-log field |
| Retry amplification | Module 1, built section 5.3. Retries show up here as calls per request |
| Tracing pipelines and dashboards | Module 15, planned. Its dossier `_curriculum/module-15-observability-ops.md` line 83 assigns "Per-tenant cost attribution and budgets" to Module 14 |

### Overlap with built modules

Headings were read with `grep '^## '` and `grep '^### '` on `inference-internals/*.md`, `eval-engineering/*.md` and `agent-evals/*.md` on 2026-09-25. `_curriculum/module-01-coverage.md` was read in full. Its line "Module 14 adds gateways, per-tenant metering, and FinOps practice" sets the handoff.

| Built heading | What it owns | What this module adds |
|---|---|---|
| Module 1, "3.1 — The five token classes, and two multipliers" | Token classes and multipliers | 4.6 uses today's prices as inputs. It adds only that the cache-read ratio now differs per model. Link 3.1 |
| Module 1, "3.3 — Explicit caching with cache_control", "The break-even, derived" | Cache break-even | Not repeated |
| Module 1, "3.4 — Routing cascades", "The control group nobody runs" | Random-escalation control, offline, one service | A randomized holdout over users, with full cost across teams, 4.12. Link 3.4 for the arithmetic |
| Module 1, "3.4", "Which escalation signal works" and "The two failure modes, both measured" | Signal ranking, under-routing, routing collapse | Not repeated |
| Module 1, "3.5 — Per-request cost alerting", "The reservation pattern, the one good answer" | The reservation pattern for one service | Which gateways implement it, and where it leaks, 4.1 and 4.3 |
| Module 1, "3.5", "The question nobody documents: what happens mid-stream" | Mid-stream behaviour, as documented on 2026-09-12 | Two more documented behaviours since then, 4.2. Correction in section 7, conflict f |
| Module 1, "3.5", "There is no standard for this yet" | No OpenTelemetry cost attribute | Leaf-span rule for fan-out, 4.5. Metric change of 2026-09-22, conflict f |
| Module 1, "5.5 — The run record", "Attribution: four axes, and only three have attribute names" | Model, prompt, data and serving axes for quality | Tenant and route axes for cost, 4.5 and 4.7 |
| Module 1, "6.2 — Many tenants on one fleet" | Quotas and fairness at the gateway and scheduler | Dollar budgets per tenant, and the spend log, 4.1 and 4.4 |
| Module 1, "6.3 — When the failure is quality dropped" | Slice-first quality triage | The same slicing applied to cost, 4.7 |
| Module 11, "5.1" to "5.4", "6.2 — Gate on the lower bound of the paired interval" | Intervals and sizing | Lab 6.3 uses a bootstrap interval. Link these sections |
| Module 12, "4.1 — Size the A/B test from the smallest change", "4.2 — Peeking at every look inflates false wins", "4.3 — A good A/B result sees only its own metrics" | Live A/B tests, including cost per conversation as a must-not-worsen metric | Only the cost accounting: which cost lines move to other teams, and estimate against measured saving, 4.12 |
| Module 1, "4.6 — The self-host decision" | Self-host break-even | Not repeated. Module 13 extends it |

Summary: Module 1 owns the arithmetic for one request and one service. This module owns attribution, budgets across tenants, bill decomposition, and ownership.

---

## 3. Sources, with dates

### 3.1 What changed recently

| Date | Change | Source | Why it matters |
|---|---|---|---|
| 2025-06-13 | Anthropic: agents use about 4x the tokens of chat, multi-agent systems about 15x | `RC/src/anthropic_multiagent.txt` | Calls per request can change the bill with flat traffic |
| 2025-09-30 | RouterArena v1, preprint. The venue is not checked. No saved source names ICLR 2026 | `RC/src/routerarena.txt` | First independent test of commercial routers |
| 2026-01 | LLMRouterBench preprint | `RC/src/llmrouterbench.txt` | OpenRouter's router at -24.7% accuracy against the best single model. This is accuracy, not cost |
| 2026-02-17 | FinOps for AI Overview update | `RC/src/finops_ai_overview_browser.txt` | Showback before chargeback |
| 2026-04-26 | RouteNLP v1, ACL 2026 Industry Track per the arXiv comment | `RC/src/routenlp.txt` | The only multi-week pilot with a human quality check. Not randomized |
| 2026-05-05 | OpenTelemetry GenAI conventions moved to `semantic-conventions-genai` | Metering report 2.2, commit `c9e48b1` | Old links return 404 |
| 2026-05-08 | TwinRouterBench preprint | `RC/src/twinrouterbench.txt` | Realized spend, and the cache cost of switching models |
| 2026-06-04 | FOCUS v1.4 | `RC/src/gh_focus_v14.html` | Billing data spec. AI still uses generic SKU columns |
| 2026-06-05 | Cloudflare AI Gateway spend limits | `RM/src/cf_changelog.md` line 197 | First-party dollar budgets scoped by metadata |
| 2026-07-10 | Kong AI Gateway 2.0.0, a separate runtime | `RM/src/kong2_changelog.md` | Plugin pages point to new policy pages |
| 2026-07-29 | Kong 2.0.1 adds cache read and write rates | `RM/src/kong2_changelog.md` line 407 | Before this, the documented cost formula had no cache class |
| 2026-07-30 | OpenAI renames Priority processing to Fast mode | `RM/src/oai_pricing.txt` | Log parsers that match "priority" miss the new name |
| 2026-08-09 | OpenTelemetry PR #443 proposes `gen_ai.usage.cost.*`. Open | `RM/src/og_pr443.html` | Names may change |
| 2026-08-21 | Agent Router v1.1.0, formerly Envoy AI Gateway | `RM/src/envoy_rel.json` | Docs moved to `theagentrouter.ai` |
| 2026-09-01 | Cloudflare invoices drop token quantities | `RM/src/cf_changelog.md` lines 66 to 69 | The invoice alone cannot explain a change |
| 2026-09-01 | The planned Sonnet 5 rise to $3/$15 did not happen | `RM/src/anth_pricing.md` line 42 | A cost model that applied it is wrong |
| 2026-09-22 | OpenTelemetry PR #374 replaces `gen_ai.client.token.usage` with per-class counters | `RM/src/og_374.breaking.md` | A spend metric can now carry cache reads and writes |
| 2026-09-22 | Kong AI Gateway 2.1.0, per-modality cost | `RM/src/kong2_changelog.md` line 67 | |
| 2026-09-23 | LiteLLM 1.102.1 | `RM/src/litellm_pypi.json` | The pin |
| 2026-09-23 | State of Tokenomics, RC 1.0, 472 responses | `RC/src/tokenomics_state_browser.txt` | Survey data on ownership. Two days old |
| 2027-01-01, announced | Gemini 3.8 Flash doubles in every class | `RM/src/g_pricing.txt` | A planned price cause for a bill change |

### 3.2 Primary sources

All fetched by the research agents on 2026-09-25. HTTP status is the final status they recorded. None of the gateway, pricing or FinOps sources is peer reviewed.

| Title | Org | Date and status | URL | What to read | HTTP |
|---|---|---|---|---|---|
| LiteLLM source at v1.102.1: `schema.prisma`, `_types.py`, `budget_reservation.py`, `parallel_request_limiter_v3.py` | BerriAI | Tag of 2026-09-23 | `raw.githubusercontent.com/BerriAI/litellm/v1.102.1/...` | Lines cited in 4.3 and 4.4 | 200 |
| Spend limits | Cloudflare | Page dated 2026-09-09 | https://developers.cloudflare.com/ai-gateway/features/spend-limits/ | "How it works" | 200 |
| Custom metadata | Cloudflare | Page dated 2026-09-24 | https://developers.cloudflare.com/ai-gateway/observability/custom-metadata/ | 5-entry limit, `cf.user_id` | 200 |
| AI Gateway changelog | Cloudflare | 2026 | https://developers.cloudflare.com/ai-gateway/changelog/ | 2026-06-05, 2026-09-01, 2026-09-09 | 200 |
| Usage-based rate limiting | Agent Router, Agentic AI Foundation | v1.1.0 docs | https://theagentrouter.ai/docs/capabilities/traffic/usage-based-ratelimiting/ | "Rate Limit Timing", "Streaming responses" | 200 |
| AI Rate Limiting Advanced, policy | Kong | AI Gateway 2.x | https://developer.konghq.com/ai-gateway/policies/ai-rate-limiting-advanced.md | Known limitations, line 765 | 200 |
| Kong AI Gateway changelog | Kong | to 2.1.0, 2026-09-22 | https://developer.konghq.com/ai-gateway/changelog.md | 2.0.0 to 2.1.0 | 200 |
| Usage and rate limit policies, cost management, metadata | Portkey | No version | https://docs.portkey.ai/docs/product/enterprise-offering/budget-policies.md | 412 status, streaming FAQ | 200 |
| Limits, Streaming, Workspace Budgets, Usage Accounting | OpenRouter | No version | https://openrouter.ai/docs/api_reference/limits.md | "In-flight spending budget" | 200 |
| GenAI registry and token metrics at `8ffdf568` | OpenTelemetry | Commit of 2026-09-22, development status | https://github.com/open-telemetry/semantic-conventions-genai | `model/gen-ai/registry.yaml`, `token-metrics.yaml` | 200 |
| PR #443, cost conventions | OpenTelemetry | Open on 2026-09-25 | https://github.com/open-telemetry/semantic-conventions-genai/pull/443 | Description | 200 |
| Pricing | Anthropic | Read 2026-09-25 | https://platform.claude.com/docs/en/about-claude/pricing | Model table, footnotes 1 to 3, tokenizer note | 200 |
| Pricing | OpenAI | Read 2026-09-25 | https://developers.openai.com/api/docs/pricing | Standard, Batch, Flex, Fast mode | 200 |
| Gemini Developer API pricing | Google | "Last updated 2026-09-24 UTC" | https://ai.google.dev/gemini-api/docs/pricing | 3.8 Flash, 3.1 Pro rows | 200 with a cookie jar. Plain fetch 302 to sign-in |
| FrugalGPT | Stanford | 2023, arXiv. Venue not checked | https://arxiv.org/abs/2305.05176 | Section 3, Limitations | 200 |
| RouteLLM | LMSYS, UC Berkeley | 2024, v4, ICLR 2025. Venue verified from the citation in `RC/src/twinrouterbench.txt` | https://arxiv.org/html/2406.18665v4 | 5.4, 5.5 Table 7, Appendices B, D, E | 200 |
| RouteLLM blog | LMSYS | 2024-07-01 | https://lmsys.org/blog/2024-07-01-routellm/ | The 85% sentence and its baseline | 200 |
| RouterArena | Multiple universities | 2025, arXiv. Venue not checked | https://arxiv.org/abs/2510.00202 | 6.1 Table 2, Figures 7 to 9 | 200 |
| LLMRouterBench | Multiple | 2026, preprint | https://arxiv.org/html/2601.07206v1 | Section 4 | 200 |
| Is Escalation Worth It? | Independent, Bouchard | 2026-05, preprint | https://arxiv.org/abs/2605.06350 | Cost accounting | 200 |
| TwinRouterBench | Gradient and universities | 2026-05, preprint | https://arxiv.org/abs/2605.18859 | 5.1, 5.2, 6.2 Table 3 | 200 |
| RouteNLP | University of Hong Kong, Stellaris AI | 2026-04. The arXiv comment says "Accepted at ACL 2026 Industry Track", `RC/src/routenlp_abs.html`. Not checked in the ACL Anthology | https://arxiv.org/abs/2604.23577 | 5.3 human evaluation, 6 pilot and quality audit, Table 6 | 200 |
| Front-door routing with small models | Plexor Labs | 2026, preprint | https://arxiv.org/abs/2604.02367 | Abstract, Study 2 | 200 |
| Multi-agent research system | Anthropic | 2025-06-13, engineering post | https://www.anthropic.com/engineering/multi-agent-research-system | Token multipliers | 200 |
| State of AI, 100T tokens | a16z and OpenRouter | 2025, observational | https://openrouter.ai/state-of-ai | Sequence length section | 200 |
| FinOps for AI Overview | FinOps Foundation | Updated 2026-02-17 | https://www.finops.org/wg/finops-for-ai-overview/ | Showback, owners | 403 to curl, read in a browser |
| FinOps for AI technology category | FinOps Foundation | No date found | https://www.finops.org/framework/technology-categories/ai/ | Allocation, forecasting, FOCUS | Browser |
| How to Forecast AI Services Costs in Cloud | FinOps Foundation | Updated 2025-07-07 | https://www.finops.org/wg/how-to-forecast-ai-services-costs-in-cloud/ | Outcomes, cadence | Browser |
| Tokenomics: Managing AI Value in SaaS Model Token Costs | FinOps Foundation | Updated 2026-06-03 | https://www.finops.org/wg/token-economics-saas/ | Maturity stages | Browser |
| Invoicing and Chargeback, Allocation | FinOps Foundation | No date found | https://www.finops.org/framework/capabilities/invoicing-chargeback/ | Definitions | Browser |
| State of Tokenomics RC 1.0 | Tokenomics Foundation site | 2026-09-23, survey | https://www.tokeneconomics.com/state-of-tokenomics/ | Ownership, routing | 403 to curl, browser |
| Plan and manage costs, Foundry | Microsoft | ms.date 2026-08-27 | https://learn.microsoft.com/en-us/azure/foundry/concepts/manage-costs | Estimate against meters | 200 |

---

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Each concept gives one best piece of evidence first, with its conditions. Every quote and number in a "Best evidence" line was re-grepped in its saved file. Section 9.4 gives the counts per concept.

### 4.1 A spend limit caps admission, not spend. Most gateways charge the cost after the response

- **Best evidence, verified.** Cloudflare AI Gateway: "The current request's cost is recorded after completion, so a burst of concurrent requests can briefly exceed the limit". `RM/src/cf_spend_limits.md` line 31. Hosted, no version, page dated 2026-09-09.
- **Verified.** Agent Router v1.1.0: "Token usage is charged after the response completes." `RM/src/ar_usage_rl.txt` line 14.
- **Verified.** Kong AI Gateway 2.x lists as a known limitation: "The cost is only reflected during the next request." `RM/src/kong2_rla_policy.md` line 765.
- **Verified.** OpenRouter workspace budgets: "In-flight requests that were already dispatched will complete". `RM/src/or_ws_budgets.md` line 183. Enterprise only.
- **Verified.** Cloudflare calls its cost "a best-effort estimation". `RM/src/cf_spend_limits.md` line 109.

| Gateway, version | Budget check | Cost charged | Overshoot possible |
|---|---|---|---|
| LiteLLM 1.102.1 | Before the call | Reserves an estimate before, settles after | Yes, bounded by the reservation, 4.3 |
| OpenRouter, hosted | Before the call | Reserves an estimate for key budgets. Workspace budgets charge after | Yes, for workspace budgets |
| Cloudflare AI Gateway, hosted | Before the call | After completion | Yes |
| Portkey, hosted policies | Not documented | Not documented | Not documented |
| Kong AI Gateway 2.1.0 | Before the call | After the response. The next request sees it | Yes |
| Agent Router v1.1.0 | Before the call | After the response completes | Yes |

Row evidence: metering report 2.1, with file and line per row. Not all rows were re-grepped by the dossier author. The five quotes above were.

- **Inferred.** Overshoot is bounded by concurrency times the worst request cost. Example: 100 concurrent requests on Claude Opus 5.5 can add $11.39 above the limit. Each request has 8,000 input and 4,096 output tokens. Prices are $4 and $20 per million tokens, read 2026-09-25. `D14/recompute.txt` part E. The reviewer recomputed it: 100 x (8,000 x 4 + 4,096 x 20) / 1,000,000 = $11.392. Check: lab 6.4.

### 4.2 No gateway documents cutting an admitted stream at a budget. The documented behaviour is to let it finish

- **Best evidence, verified.** Agent Router v1.1.0 says it "does not interrupt an already admitted stream". The page's worked case: a 1,000-token hourly limit, and one admitted stream uses 1,200 tokens. Later matching requests get HTTP 429. `RM/src/ar_usage_rl.txt` lines 31 to 38.
- **Verified.** OpenRouter reports errors after the headers as an SSE event with `finish_reason: "error"`. "The HTTP status remains 200 OK". `RM/src/or_streaming.md` lines 485 to 497. The page documents this for provider errors, not for budgets.
- **Verified.** The status for a budget stop differs by gateway. Portkey returns "412 Precondition Failed", `RM/src/pk_budget_policies.md`. OpenRouter returns 402 for credits and 403 for workspace budgets. Cloudflare, Kong and Agent Router return 429. Metering report 2.1.
- **Verified absence.** No saved OpenRouter or Portkey page says that a budget ends a running stream. That is 9 and 11 pages. Metering report 2.1.
- **Inferred design.** Decide before the stream opens. Cap `max_tokens` to what the remaining budget can pay. Let the admitted stream finish. Block the next request with a status the client can branch on. No gateway read here documents a `max_tokens` cap computed from the remaining budget. The nearest case: LiteLLM's token-rate limiter writes a `max_tokens` into a request that has none when the smallest token limit is below 4,096 per window. The value is a quarter of that limit, not the budget left. `parallel_request_limiter_v3.py` lines 806 to 854 at tag v1.102.1, called at lines 3344 and 3590. Check: lab 6.4.
- **Not checked.** Whether a provider bills tokens generated after the client disconnects. Module 1, 3.5 covers provider behaviour.

### 4.3 A reservation bounds overshoot only when the gateway can price the request

- **Best evidence, verified.** LiteLLM 1.102.1, for a model with no token prices: "we fall back to read-time enforcement only." `RM/src/ll_budget_reservation.py` line 255. The worst-case price comes from `estimate_request_max_cost`, lines 247 and 1080.
- **Verified.** LiteLLM: "a partially-remaining budget resizes the reservation down to what is left, unless strict enforcement is on". `ll_budget_reservation.py` line 131. The request keeps its own `max_tokens`.
- **Verified, corrected in the coherence pass on 2026-09-25.** LiteLLM has two estimates for a request with no `max_tokens`. They differ.
  - The dollar-budget reservation assumes 16,384 output tokens, capped at the model's maximum output. `DEFAULT_MAX_OUTPUT_TOKENS_FALLBACK: Final = 16384`, `ll_budget_reservation.py` lines 1514 and 1535 to 1536.
  - The token-rate limiter does not reserve 4,096 output tokens. It reserves the larger of the input-token estimate and `DEFAULT_MAX_TOKENS_ESTIMATE // 4` = 4,096 // 4 = 1,024 tokens. For a token limit below 4,096, the floor is the limit divided by 4. An operator can also set an estimate per key or team. `DEFAULT_MAX_TOKENS_ESTIMATE: Final = 4096` is at `RM/src/ll_rl_v3.py` line 343. The rule is at lines 349, 699 to 702 and 968 to 982 of `parallel_request_limiter_v3.py` at tag v1.102.1.
  - The earlier line here said LiteLLM assumes 4,096 output tokens. That was a misreading of line 343. The Phase 2 fact check of 2026-09-25 found it.
- **Verified.** Portkey: with streaming and no `include_usage`, "no token counts means no cost calculation". An unpriced model logs 0 cents and does not count toward the budget. `RM/src/pk_cost_mgmt.md`.
- **Verified.** OpenRouter's in-flight estimate uses a fixed cap when `max_tokens` is absent. It excludes per-request fees, plugin charges and image prices. `RM/src/or_limits.md`. Added in the coherence pass: the hold is against the account's credit balance, and it applies only to a subset of prepaid accounts, not to enterprise, subscription or invoice-billed accounts. The workspace-budget and per-key pages describe no hold. `or_limits.md` line 348, from the Module 14 Phase 2 fact check.
- **Inferred.** A partly fitting LiteLLM request can overshoot by up to its full output cost. Check: a proxy with $0.01 of budget left and a long `max_tokens`.

### 4.4 A per-call spend log without cache columns reports a cache collapse as a price rise

- **Best evidence, verified by run.** The `bill_diff.py` break-it drops the cache columns, as in LiteLLM's `SpendLogs`. The planted cache collapse on `initech/chat` is then blamed on price per token: "+93.40 price_per_token initech/chat/claude-sonnet-5". The cache factor is "+0.00". `RM/proto/breakit_output.txt`. Synthetic log, 27,000 model calls in period A, seed 7.
- **Verified.** LiteLLM 1.102.1 `LiteLLM_SpendLogs` has `prompt_tokens`, `completion_tokens` and `total_tokens`, and no cache-token column. `RM/src/ll_schema.prisma` lines 629 to 668. The cache split sits in JSON, `additional_usage_values`, which "covers provider-specific usage information - e.g. prompt caching". `RM/src/ll_types.py` line 3816.
- **Verified, added by the dossier author. This corrects the metering report.** Six LiteLLM daily rollup tables do have both columns: `LiteLLM_DailyUserSpend`, `DailyOrganizationSpend`, `DailyEndUserSpend`, `DailyAgentSpend`, `DailyTeamSpend` and `DailyTagSpend`. `ll_schema.prisma` lines 782, 818, 854, 889, 924 and 962. Each row is per day, key, model and provider. They have no price version and no cache-write TTL. Whether the proxy fills them for every provider is not checked. Section 7, conflict a.
- **Verified.** Since 2026-09-01, Cloudflare invoices "no longer break out input and output token quantities". `RM/src/cf_changelog.md` lines 66 to 69. So the invoice alone cannot split a change.
- **Verified arithmetic, corrected in review.** Cache hits can become plain uncached input. Then the cost of those tokens rises by 1 divided by the read ratio. That is 10x on Claude Sonnet 5, 20x on Opus 5.5 and 40x on Fable 5.1. This is not the largest rise. A common collapse also writes a new cache entry on every request. The planted collapse in `bill_diff.py` does this: "every request writes", `RM/proto/breakit_output.txt`. Then the rise is the write price divided by the read price. For 5-minute and 1-hour writes, that is 12.5x and 20x on 0.1x models. It is 25x and 40x on Opus 5.5, and 50x and 80x on Fable 5.1. Prices in 5.1, read 2026-09-25.

### 4.5 In a fan-out trace, cost belongs on the model-call spans only. The tenant belongs on the root and must be passed down

- **Best evidence, verified.** OpenTelemetry PR #443 proposes `gen_ai.usage.cost.amount`. Its description says cost was moved off agent and workflow spans "to avoid double-counting". `RM/src/og_pr443.html` line 1116. Status: open on 2026-09-25.
- **Verified absence.** At commit `8ffdf568` of 2026-09-22, the GenAI registry has 72 `key: gen_ai` entries. The words "tenant" and "cost" appear 0 times. "stability: stable" appears 0 times. `RM/src/og_model_gen-ai_registry.yaml`. So the tenant key is your own, for example `app.tenant.id`.
- **Verified.** Cloudflare allows "up to five custom metadata entries per request". `RM/src/cf_metadata.md`. Tenant, route, feature, agent and trace id already fill it.
- **Verified.** The FinOps Framework lists a "Lack of generally accepted frameworks for cost allocation across multi-agent workloads". `RC/src/finops_techcat_ai_browser.txt`.
- **Inferred method.** Resolve the tenant once at the edge. Pass it and the root trace id to every child call. Sum model-call cost by the root's tenant. Report the cost with no tenant as its own "unattributed" line. No gateway page read here offers a fan-out roll-up. Check: lab 6.5.
- **Inferred.** A shared prompt-cache write makes per-tenant cost depend on arrival order. The first request pays 1.25x or 2x input. Later readers pay 0.1x or less. No gateway documents a rule. Pick one and write it down.

### 4.6 One cache multiplier in a cost model is wrong. The read ratio and the batch rules differ per model and per provider

- **Best evidence, verified.** Anthropic, read 2026-09-25: cache hits on Claude Fable 5.1 and Mythos 5.1 are "priced at 0.025x". On Claude Opus 5.5 they are "0.05x". "All other models use the standard 0.1x multiplier." `RM/src/anth_pricing.md` lines 36 to 40.
- **Verified.** Anthropic cache multipliers "stack with other pricing modifiers, including the Batch API discount". `RM/src/anth_pricing.md`.
- **Verified. Read 2026-09-25, re-read in review.** Google Gemini 3.1 Pro Preview batch lists the cache price as "Same as Standard". Gemini 3.8 Flash batch halves it. `RM/src/g_pricing.txt`. So "batch halves every class" is wrong on Google. The cache storage price per hour is not halved on either model.
- **Verified. Read 2026-09-25, re-read in review.** OpenAI Batch and Flex are half of Standard in every class, including cached input and cache writes. Fast mode is 2x in every class. `RM/src/oai_pricing.txt`.
- **Verified.** Anthropic's own caching section still says "A cache hit costs 10% of the standard input price". The next sentences give the Fable 5.1 and Opus 5.5 exceptions. `RM/src/anth_pricing.md` line 149. A reader who stops at the first sentence gets the wrong ratio.
- **Verified.** OpenTelemetry now has a counter per class, including `gen_ai.client.inference.usage.cache_write.input_tokens`. `RM/src/og_model_gen-ai_token-metrics.yaml` line 52. The input counter counts input tokens "including cached tokens", line 14. The inclusion rule is in the attribute registry, not in that file. Cache reads and writes each "SHOULD be included in" `gen_ai.usage.input_tokens`. `RM/src/og_docs_registry_attributes_gen-ai.md` lines 333 and 335. So uncached input is input minus reads minus writes.
- Link: Module 1, 3.1 teaches the classes. This concept adds only that the ratio is per model.

### 4.7 A bill change needs an exact split that does not depend on order, and "traffic" must separate requests from model calls per request

- **Best evidence, verified by run.** In `bill_diff.py`, scenario `model_swap`, a one-at-a-time bridge gives traffic "+4.47" in one order and "+11.78" in the reverse order. The Shapley split gives "+8.13". `RM/proto/breakit_output.txt` and `RM/proto/run_all_output.txt`. The ratio 11.78 / 4.47 is 2.6.
- **Verified by run.** In `bill_drivers.py`, the bill goes from $6,474 to $13,022, 2.01x, with requests flat at 750,000. The largest driver is `tenant-b /report calls_per_request`, +$4,216, 64.4% of the change. `RC/proto/out_bill_drivers.txt`. Illustrative data at $3 and $15 per million tokens. LMDI-I split.
- **Verified, vendor claim.** Anthropic, about its own research system: "multi-agent systems use about 15×" the tokens of chat. `RC/src/anthropic_multiagent.txt`, engineering post of 2025-06-13. No workload size is given. So calls per request can move the bill while requests stay flat.
- **Verified by the reviewer's recompute.** Take the `/report` line of `bill_drivers.py`. Calls per request go from 1 to 4. Input tokens per call go from 6,000 to 7,800. For two factors, Shapley is the mean of the two orders. Input part: calls 0.5 x 3 x (6,000 + 7,800) x 0.069 = $1,428.3. Output part: calls 0.5 x 3 x (800 + 1,560) x 0.75 = $2,655. The sum is $4,083. LMDI gives $1,462 + $2,754 = $4,216. Both methods sum to $5,818.8 on this line.
- **Verified by the dossier author's recompute.** Shapley and LMDI are both exact and both order-free. They still split the same change differently. On the `/report` line, Shapley gives calls +$4,083, input tokens +$311 and output tokens +$1,425. LMDI gives +$4,216, +$277 and +$1,326. `D14/recompute.txt` part C. The top driver is the same. The size of each driver depends on the method. State the method with the numbers.
- **Inferred.** `bill_diff.py` counts each model call as a request. `RM/proto/bill_diff.py` line 163 gives every row its own trace id and an empty parent. So a rise in calls per request would appear as "traffic". Check: add a fan-out scenario to the merged lab, 6.2.

### 4.8 A model change raises the bill through tokens per call, not only through the list price

- **Best evidence, verified by run.** The `bill_diff.py` swap bridge on `globex/summarize`, gpt-6-luna to claude-opus-5.5: cost per request "$0.00093 -> $0.04968 (x53.7)". Price per token explains "+86.5%" of that gap. Output length explains "+12.7%". `RM/proto/run_all_output.txt`. Planted output growth 2.5x. The bridge assumes the requests on the route did not change.
- **Verified, vendor claim.** Anthropic: the tokenizer of Claude 4.7 and later "produces approximately 30% more tokens for the same text". `RM/src/anth_pricing.md` line 51, read 2026-09-25. The page adds that the increase "depends on the content and workload shape". So a same-price model change can raise input and output tokens.
- **Verified.** RouterArena: GPT-5 and Azure-Router "rely more heavily on reasoning models, leading to substantially longer generations". `RC/src/routerarena.txt`.
- **Verified.** LiteLLM keeps `original_model_group`, "Model group requested before any fallbacks", and `attempted_fallbacks`. `RM/src/ll_types.py` lines 3847 and 3848. Agent Router emits the original, requested and responded model. Metering report 2.1. So a silent fallback is visible only if you log both models.
- **Verified by run.** A model with no history in period A puts the whole switch on "model mix". That is 96.8% in `model_swap`. The swap bridge is the second step that names why. `RM/proto/run_all_output.txt`.

### 4.9 Published routing savings are offline estimates against a chosen baseline. None uses a randomized live control

- **Best evidence, verified.** RouteNLP ran an 8-week pilot at about 5,000 queries a day. The authors call it a "shadow deployment with partial traffic routing (not a randomized A/B test)". `RC/src/routenlp.txt`, section 5.
- **Verified.** RouteLLM prices from assumed token counts: "We estimate the average cost of using GPT-4". `RC/src/routellm_v4.txt`, Appendix D.
- **Verified, preprint.** The only randomized design found ran "under synthetic traffic", 60 unique cases per arm. It measured router classification accuracy. `RC/src/frontdoor.txt`, abstract. Plexor Labs, arXiv 2604.02367.
- **Verified.** One author team, two baselines. The RouteLLM blog: "over 85% on MT Bench ... as compared to using only GPT-4". The paper's 3.66x is against a random router. `RC/src/routellm_blog.txt`, `RC/src/routellm_v4.txt` section 5.4.

| Source | Baseline | Saving | Kind |
|---|---|---|---|
| RouteLLM, ICLR 2025 | Random router, same quality | 3.66x fewer GPT-4 calls | Offline estimate |
| RouteLLM blog, 2024 | GPT-4 only | Over 85% on MT Bench | Offline estimate |
| LLMRouterBench, preprint | Best single model | Up to 31.7% | Offline estimate |
| TwinRouterBench, preprint | Opus 4.6, no routing | 53.1% | Realized API spend, 100 fixed tasks, no randomized users |
| RouteNLP, ACL 2026 Industry per the arXiv comment | Always the top tier | 62% simulated, 58% pilot | Pilot is observational |
| Not Diamond homepage | Not stated | "20% +" | Vendor claim, no conditions |

Row evidence: cascades report 2.1, with file and section per row.

### 4.10 A router can raise the bill

- **Best evidence, verified, preprint.** TwinRouterBench Table 3, 100 held-out SWE-bench Verified tasks in mini-swe-agent v2.2.8: rule-based UncommonRoute cost $172.56 and resolved 73. Opus 4.6 with no routing cost $54.73 and resolved 74. `RC/src/twinrouterbench.txt` lines 588 to 600. Cost is realized API spend from provider logs. The ratio is 3.15x.
- **Verified.** The same table: trained UncommonRoute cost $25.66 and resolved 75. The paper prints "1 −25.66/54.73 = 53.1%". Line 625. 75 against 74 of 100 is one task. Module 11, 5.3 explains why this cannot show equal quality.
- **Verified.** The mechanism named by the paper: "Cache writes on tier switch are charged at the incoming tier's rate". Per-call routing breaks the prompt cache on each switch.
- **Verified.** RouterArena: one router reached "only baseline-level accuracy while incurring 378% of the cost". `RC/src/routerarena.txt`, section 6.
- **Verified, preprint, corrected in review.** LLMRouterBench reports OpenRouter's router with a "(indeed, negative) performance improvement (-24.7%)" against the best single model. `RC/src/llmrouterbench.txt` line 297. This is an accuracy result, not a cost result. It does not show that the router raised the bill. Setting: the performance-cost setting, 13 flagship models on 10 datasets, lines 199 and 202. OpenRouter used its own model pool, line 299. OpenRouter accessed 2025-11-13, line 628. OpenRouter's docs today describe a different, spend-based mechanism. Which mechanism was tested is not checked.

### 4.11 Router overhead is a share of the model cost, so it grows as models get cheaper

- **Best evidence, verified.** RouteLLM Table 7: the SW ranking router costs $39.26 per million requests on a CPU VM. `RC/src/routellm_v4.txt` section 5.5. The paper says the most expensive router adds "no more than 0.4%" of GPT-4 generation cost.
- **Verified by the dossier author's recompute.** A request of 95 input and 264 output tokens costs $0.00887 on GPT-4-1106 at $10 and $30. It costs $0.001415 on Claude Haiku 4.5 at $1 and $5, read 2026-09-25. The SW router is 0.44% of the first and 2.77% of the second. `RC/proto/out_router_overhead_recompute.txt`, `D14/recompute.txt` part D.
- **Verified.** Latency differs by router. RouterArena measured 11.1 ms to 546.8 ms per selection on one A100. The two slowest call an external embedding API. RouteNLP's DistilBERT router "adds 4.2ms per query". `RC/src/routerarena.txt` Figure 9, `RC/src/routenlp.txt`.
- **Verified, added in review.** The saving also depends on the price ratio between the cheap and the strong model. RouteNLP reports "58% at 200×, 41% at 100×; break-even at ∼25×". `RC/src/routenlp.txt` lines 820 to 822. Authors' own estimate. As model prices move closer together, the same router saves less.
- **Not checked.** The share of an LLM-judge escalation signal. It is a full model call. No published measurement was found.

### 4.12 A quality drop can raise the estimated saving while the full-cost saving falls

- **Best evidence, verified by run.** `RC/proto/cascade_holdout.py`, 6,000 users split 50/50 by a SHA-256 hash of the user id, seed 2026, 200 bootstrap resamples over users. With a regressed cheap model, the offline estimate rises from +47.5% to +55.0%. The measured full-cost saving falls from +30.8% to +10.3%. `RC/proto/out_main.txt`. Full cost adds support tickets at 8 units, with probability 0.5 per unresolved task. These parameters are illustrative.
- **Verified by run.** With no retries and no tickets, the four numbers agree within noise. `RC/proto/out_noretry.txt`. So the gap comes from users who retry or give up.
- **Verified, corrected in review.** RouteNLP has two quality numbers. They come from two different checks.
  1. Offline human evaluation, section 5.3: "∼8–9% of all queries received substantially degraded responses". Three domain experts, 200 samples each on two generation tasks, customer-service replies and financial summaries, 5-point scale. `RC/src/routenlp.txt` lines 715 to 749. Recompute: 32% of 24 to 27% is 7.7% to 8.6%. This is not the pilot.
  2. Pilot audit, section 6: two experts rated 500 random pilot responses. 91% acceptable, 6.4% marginal, 2.6% unacceptable, against 1.8% for the baseline. "Customer complaint rates showed no statistically significant change." Lines 797 to 804. The pilot was not randomized.
- The draft called the 8 to 9% a deployment result. It is an offline result. The pilot's own audit found 0.8 points more unacceptable answers.
- **Inferred, org-level rule.** A cascade moves cost between owners. The AI line gets cheaper. Support tickets land on the support team's line. The owner of a routing change must see the full-cost result. Check: a live holdout that joins support tickets to the arm.
- **Where the live test design belongs.** Sizing, peeking and must-not-worsen metrics belong to Module 12, 4.1 to 4.3. This concept keeps only the cost accounting.

### 4.13 Price per token falls, but a forecast built on last month's requests times a new price will under-forecast

- **Best evidence, verified.** OpenRouter and a16z: average prompt tokens per request rose "roughly fourfold from around 1.5K to over 6K". `RC/src/openrouter_state_ai.txt`. Observational, one platform, most analyses cover 2024-11-03 to 2025-11-30.
- **Verified.** The FinOps Foundation success goal is "The AI forecasts of costs vary only within 5% of actuals per month". `RC/src/finops_how-to-forecast-ai-services-costs-in-cloud_browser.txt`. It is a target. None of the saved sources publishes a measured forecast error for AI spend.
- **Verified.** The FinOps Framework says "Higher volatility of costs makes trend-based forecasting in general more challenging". `RC/src/finops_techcat_ai_browser.txt`.
- **Verified.** Microsoft Foundry guidance: update budgets and alert thresholds "only after you validate at least one full billing cycle trend". `RC/src/azure_openai_costs.txt`, ms.date 2026-08-27.
- **Verified.** Price causes can be scheduled. Gemini 3.8 Flash doubles in every class on 2027-01-01. `RM/src/g_pricing.txt`.
- **Inferred.** Forecast each route as requests times calls per request times tokens per call times price, with a dated price sheet. Then the forecast error splits by the same drivers as 4.7. Check: back-test on monthly per-route bills.

### 4.14 Chargeback is not the mature form of cost ownership. A named owner per cost line comes first

- **Best evidence, verified.** FinOps Framework, Invoicing and Chargeback: "Neither type of reporting should be considered more mature than the other." `RC/src/finops_framework_capabilities_invoicing-chargeback_browser.txt`. Also: "Chargeback is not always required in every organization."
- **Verified.** FinOps for AI Overview, updated 2026-02-17: "Implement a showback model", and assign owners for monitoring and forecasting. `RC/src/finops_ai_overview_browser.txt`.
- **Verified.** FinOps Tokenomics paper: provider invoices show spend by API key or project, "not by business unit, cost center, application, or team". `RC/src/finops_token-economics-saas_browser.txt`.
- **Verified, survey, correlational.** State of Tokenomics RC 1.0, 2026-09-23, 472 responses: "88% have defined ownership". Those with ownership are "3.7x more likely to show value to the CFO". `RC/src/tokenomics_state_browser.txt`. Self-reported. The 3.7x is a correlation, not an effect.

### 4.15 The same model, tenant and traffic can cost 2x. A service-tier flag, a context-length tier or a per-request fee changes the price

Added in review. Module 1, 3.1 teaches tier and modality multipliers as prices. This concept adds only what the spend log must record so that a decomposition can name them. Every price below was read by the reviewer on 2026-09-25.

- **Best evidence, verified.** Anthropic Fast mode on Claude Opus 5.5 is $8 input and $40 output per million tokens. Standard is $4 and $20. That is exactly 2x. Fast mode "stacks with other pricing modifiers". `RM/src/anth_pricing.md` lines 163 to 174. The saved page and today's page are byte-identical.
- **Verified.** OpenAI Fast mode is 2x Standard in every class. Example: gpt-6-sol $4.00 input and $20.00 output against $2.00 and $10.00. OpenAI accepts `service_tier: "priority"` or `service_tier: "fast"` for the same tier. `RM/src/oai_pricing.txt`.
- **Verified.** Long context changes the price per token on some models. gpt-6-astra long context is 2x input and 1.5x output. Gemini 3.1 Pro Preview over 200k prompt tokens is 2x input and 1.5x output. Anthropic says Claude 4.6 and later bill a 900k-token request "at the same per-token rate as a 9k-token request". `RM/src/oai_pricing.txt`, `RM/src/g_pricing.txt`, `RM/src/anth_pricing.md` line 216.
- **Verified.** Data residency adds 10% on OpenAI models released on or after 2026-03-05. `RM/src/oai_pricing.txt`.
- **Verified.** Some charges are per request, not per token. Gemini grounding with Google Search gives 5,000 free requests a month, "then $14 per 1,000 requests". `RM/src/g_pricing.txt` line 198. OpenRouter's in-flight estimate leaves out per-request fees, 4.3.
- **Inferred.** In `bill_diff.py` a tier change or a long-context crossing lands on "price per token". The log has no tier field. So the split names the right route and the wrong cause. Check: add a `service_tier` column and a long-context flag to lab A, then plant a Fast-mode switch on one route.
- **Not checked.** Whether any gateway in 5.2 records the service tier on its spend row. Module 1, 3.1 says one provider returns a `service_tier` field in the usage object.

Summary of section 4: budgets stop only new requests. Logs need cache and model columns. Fan-out cost sums from model calls. An exact split names the driver. A routing saving is real only against a holdout with full cost.

---

## 5. Numbers with conditions

### 5.1 Token-class prices on 2026-09-25

USD per 1M tokens, Standard tier, short context unless stated. Read by the metering agent on 2026-09-25, which is today. The dossier author recomputed every ratio in `D14/recompute.txt` part A.

**Re-read by the reviewer on 2026-09-25.** All three pages were fetched again with `curl -sL --max-time 60`. The Anthropic `.md` page is byte-identical to `RM/src/anth_pricing.md`. The OpenAI and Google pages differ only in markup. Their visible text is identical to the saved copies. Google still shows "Last updated 2026-09-24 UTC". Every price and cache ratio in the tables below matches today's pages.

**Anthropic**, `RM/src/anth_pricing.md` lines 15 to 42:

| Model | Input | 5m cache write | 1h cache write | Cache hit | Output | Batch in / out |
|---|---|---|---|---|---|---|
| Claude Fable 5.1 | 10 | 12.50 | 20 | 0.25 | 50 | 5 / 25 |
| Claude Opus 5.5 | 4 | 5 | 8 | 0.20 | 20 | 2 / 10 |
| Claude Opus 5 | 5 | 6.25 | 10 | 0.50 | 25 | 2.50 / 12.50 |
| Claude Sonnet 5 | 2 | 2.50 | 4 | 0.20 | 10 | 1 / 5 |
| Claude Haiku 4.5 | 1 | 1.25 | 2 | 0.10 | 5 | 0.50 / 2.50 |

- Batch column for Sonnet 5 and Haiku 4.5 added in review. `RM/src/anth_pricing.md` lines 187 to 210.
- Fable 5 and Mythos 5, without ".1", use the 0.1x hit ratio at $1. Only the ".1" models use 0.025x. `RM/src/anth_pricing.md` lines 19 and 20.

- Hit ratio: 0.025x on Fable 5.1 and Mythos 5.1, 0.05x on Opus 5.5, 0.1x on the rest.
- Write ratio: 1.25x for 5 minutes, 2x for 1 hour, on every row.
- Sonnet 5 at $2 and $10 "is now the standard price". The rise to $3 and $15 "will not occur". Line 42.

**OpenAI**, `RM/src/oai_pricing.txt`:

| Model | Input | Cached input | Cache write | Output | Long context in / cached / write / out |
|---|---|---|---|---|---|
| gpt-6-astra | 10.00 | 1.00 | 12.50 | 50.00 | 20.00 / 2.00 / 25.00 / 75.00 |
| gpt-6-sol | 2.00 | 0.20 | 2.50 | 10.00 | 4.00 / 0.40 / 5.00 / 15.00 |
| gpt-6-luna | 0.10 | 0.01 | 0.125 | 0.50 | 0.20 / 0.02 / 0.25 / 0.75 |

- Batch and Flex are half of Standard in every class. Fast mode is 2x. Data-residency endpoints add 10% for models released on or after 2026-03-05.
- The token threshold for long context is not checked.

**Google Gemini API**, `RM/src/g_pricing.txt`, "Last updated 2026-09-24 UTC":

| Model | Input | Cache read | Cache storage per 1M tokens per hour | Output | Batch in / cache / out |
|---|---|---|---|---|---|
| gemini-3.8-flash, to 2026-12-31 | 0.75 | 0.075 | 0.50 | 3.75 | 0.375 / 0.0375 / 1.875 |
| gemini-3.8-flash, from 2027-01-01 | 1.50 | 0.15 | 1.00 | 7.50 | 0.75 / 0.075 / 3.75 |
| gemini-3.1-pro-preview, prompts up to 200k | 2.00 | 0.20 | 4.50 | 12.00 | 1.00 / "Same as Standard" / 6.00 |
| gemini-3.1-pro-preview, prompts over 200k | 4.00 | 0.40 | 4.50 | 18.00 | 2.00 / "Same as Standard" / 9.00 |

- Google has no cache-write price. It charges storage per hour. Output includes thinking tokens.

### 5.2 Gateway metering, on 2026-09-25

| Gateway, version | Tenant key | Cache classes in cost | Cache-write class | Budget unit | Budget breach status |
|---|---|---|---|---|---|
| LiteLLM 1.102.1 | Key, team, user, end user, tags, org, agent | In JSON per call. Columns in 6 daily tables | `cache_creation_input_tokens` in daily tables | USD and TPM | Not recorded here |
| Portkey gateway 1.15.2, hosted policies | `metadata`, any number of keys | Not named on the cost page | Not named | USD, tokens, requests | 412 |
| Kong AI Gateway 2.1.0 | Consumer or consumer group. Mapping not checked | Since 2.0.1 | Since 2.0.2, by TTL | Tokens or cost | 429 |
| Agent Router v1.1.0 | Header such as `x-tenant-id`, or dynamic metadata | `CachedInputToken` | None. "cache write" appears 0 times on the page | Tokens, CEL weights | 429 |
| Cloudflare AI Gateway | Custom metadata, 5 entries | Custom costs accept cache read and write since 2026-09-09 | Custom costs only | USD per window, 20 rules per gateway | 429 |
| OpenRouter | API key per tenant, `user` hashed upstream | `cached_tokens`, `cache_write_tokens` in every response | Yes | USD credits | 402 credits, 403 workspace |

Evidence: metering report 2.1 and 2.4, with file per cell. The LiteLLM daily-table cell is from the dossier author's read, section 4.4.

### 5.3 Routing and cascade numbers

| Number | Baseline | Model and data | Metric and scorer | Who ran it | Label |
|---|---|---|---|---|---|
| 3.66x fewer GPT-4 calls | Random router at the same quality | GPT-4 and Mixtral, MT Bench 160 questions | GPT-4 judge | Authors | Verified, offline estimate |
| Router cost $39.26 per 1M requests, SW ranking | None | CPU VM | Dollars | Authors, Table 7 | Verified |
| 53.1% realized saving, 75 against 74 resolved | Opus 4.6, no routing | 100 SWE-bench Verified tasks | Official resolution predicate | Authors | Verified, preprint |
| $172.56 against $54.73 | Same | Same | Same | Authors | Verified, preprint |
| 378% of the cost at baseline accuracy | Each router's best model | 8,400 queries, 23 datasets | Accuracy against answers | RouterArena authors | Verified, venue not checked |
| -24.7% accuracy, not cost | Best single model | Performance-cost setting: 13 flagship models, 10 datasets. OpenRouter used its own pool | Accuracy | LLMRouterBench authors | Verified, preprint. Conditions corrected in review |
| 62% simulated, 58% pilot | Always top tier | Customer service, 8 weeks, about 5,000 queries a day | Cost against Always-T4. Table 6 | Authors | Verified, observational. Metric column corrected in review |
| 8 to 9% substantially degraded | Frontier answer | Offline. Two generation tasks, 200 samples each | 3 experts, 5-point scale | Authors | Verified. Offline, not the pilot. Corrected in review |
| 2.6% unacceptable against 1.8% baseline | Baseline answers | 500 random pilot responses | 2 experts | Authors | Verified, observational. Added in review |
| 58% at 200x, 41% at 100x, break-even at about 25x | Always top tier | Price ratio between tiers | Cost | Authors | Verified. Added in review |
| 4.2 ms per query, p99 8.1 ms | None | DistilBERT router | Latency | RouteNLP authors | Verified |

### 5.4 Prototype numbers

All from runs on 2026-09-25, Python 3.9.6, standard library, arm64. Synthetic data. They show mechanisms, not rates.

| Prototype | Scenario | Number | Output file |
|---|---|---|---|
| `bill_diff.py` | `model_swap`, seed 7 | Requests 1.03x, bill 2.72x, model mix 96.8% | `RM/proto/run_all_output.txt` |
| `bill_diff.py` | `cache_collapse` | Bill 1.66x, cache 94.8% | same |
| `bill_diff.py` | `output_growth` | Bill 1.20x, output length 85.2% | same |
| `bill_diff.py` | `price_change`, Gemini 3.8 Flash 2027 price | Bill 1.16x, price 79.3% | same |
| `bill_diff.py` | `traffic` control | Requests 2.00x, bill 2.01x, traffic 99.3% | same |
| `bill_diff.py` | Self-test | 27 checks pass, 1.96 s | `RM/proto/selftest_output.txt` |
| `bill_drivers.py` | Example | $6,474 to $13,022, 2.01x, requests flat | `RC/proto/out_bill_drivers.txt` |
| `bill_drivers.py` | Self-test | 9 checks pass, 0.02 s | same |
| `cascade_holdout.py` | healthy | Offline +47.5%, full measured +30.8%, interval +28.2% to +33.4% | `RC/proto/out_main.txt` |
| `cascade_holdout.py` | cheap-model-regressed | Offline +55.0%, full measured +10.3%, interval +6.7% to +14.1% | same |
| `cascade_holdout.py` | Ticket cost 20 | Regressed cascade -37.5% | `RC/proto/out_humancost.txt` |
| `cascade_holdout.py` | Self-test | 14 checks pass | `RC/proto/out_selftest.txt` |

### 5.5 Forecast and ownership numbers

| Number | Conditions | Label |
|---|---|---|
| Prompt tokens per request about 1.5K to over 6K | OpenRouter traffic, most analyses 2024-11-03 to 2025-11-30 | Verified, observational |
| Agents about 4x the tokens of chat, multi-agent about 15x | Anthropic research system, post of 2025-06-13 | Verified, vendor engineering post |
| About 30% more tokens for the same text | Claude 4.7 and later tokenizer | Verified, vendor docs |
| Forecast within 5% of actuals per month | FinOps Foundation goal | Verified, a target, not a result |
| 60 to 90 days of baseline data before commitments | FinOps Tokenomics paper, updated 2026-06-03 | Verified, guidance |
| 88% have defined ownership, 3.7x more likely to show value | 472 survey responses, median revenue $1.8B | Verified, self-reported, correlation |

---

## 6. Lab designs

Every lab below runs offline on the learner's Mac, with the standard library, no key and no download, unless marked. None was run for this dossier.

### 6.1 The two bill-decomposition prototypes, compared

| Property | `bill_diff.py`, metering report | `bill_drivers.py`, cascades report |
|---|---|---|
| Input | A synthetic per-call spend log, written as CSV. 27,000 rows in period A | Hand-set monthly lines per tenant and route |
| Method | Shapley over 7 factors per segment. 128 bill evaluations per segment | LMDI-I on two products per line |
| Exact | Yes. Checked against the sum of row costs | Yes. Checked on the example |
| Order-free | Yes. The sequential break-it shows the trap | Yes |
| Segment | Tenant, route and model | Tenant and route. No model field |
| Calls per request | No. Each row is its own request, line 163 | Yes, a separate factor |
| Cache classes | Read and write, per row | One cache factor. No write class |
| Price versions | Per row. A segment with two versions raises an error, line 212 | Price is a number on the line |
| A new model or tenant in period B | Handled. The segment gets share 0 in the other period, lines 236 and 255 | Not handled. The loop runs over period-A keys only, line 73. A key missing in B raises an error. A key new in B is dropped from the bill |
| A factor at zero | Handled | Fails. LMDI takes `math.log` of each ratio, line 82 |
| Model change detail | Swap bridge on a changed route | Separate lines for tokenizer and output growth |
| Break-its | No cache columns, sequential order | Price cut and tokenizer rise in one month. Not in the saved output |
| Self-test | 27 checks | 9 checks |
| Size | 564 lines | 182 lines |

**Recommendation: merge, on the `bill_diff.py` base.** Reasons:

1. The module question names a model change. Only `bill_diff.py` keeps the model in the segment and handles a model that is new in period B.
2. Only `bill_diff.py` reads a per-call log. The lab then teaches which log fields are needed, which is concept 4.4.
3. `bill_drivers.py` has the one factor `bill_diff.py` lacks: calls per request. Concept 4.7 needs it.
4. LMDI fails on a zero and on new segments. Shapley does not.

Trade-off: Shapley cost grows as 2 to the power of the factor count. With 8 factors that is 256 bill evaluations per segment. That is small for a lab. Inferred, not timed.

### 6.2 Lab A, the module lab: explain a doubled bill

- **Where it runs.** Laptop, offline, standard library. Base: `RM/proto/bill_diff.py`.
- **Changes to make.**
  1. Add `request_id` and `parent_id` to each row. A request is a root. Model calls are its children. Traffic becomes root requests. Add an eighth factor, calls per request, from `bill_drivers.py`.
  2. Add a scenario `agent_loop`: one route goes from 1 to 4 model calls per request. Requests stay flat.
  3. Add a scenario with two causes at once, a cache collapse and a traffic rise. It measures how far the sequential order gap grows. Metering report item 12.
  4. Read prices from Module 1's `inference-internals/code/prices.yaml` plus a `price_version` field. That file has no Opus 5.5 or Fable 5.1 rows today. Add them from 5.1.
  5. Keep LMDI as an optional cross-check on lines with no zeros. Print both splits. Concept 4.7 shows they differ.
- **What it prints.** Per scenario: requests B/A, bill B/A and the share of each of 8 factors. Then the top 5 cells by tenant, route, model and factor. Then the swap bridge for any changed route.
- **Break-its.** Drop the cache columns. Use a sequential order. Drop `parent_id`, so fan-out looks like traffic.
- **Self-test.** The 27 current checks. Add a hand case where calls per request double. All of the change must land on that factor.
- **Cost.** Zero. The current prototype runs its self-test in 1.96 s. The reviewer re-ran it on 2026-09-25: 27 of 27 checks pass, 2.05 s real, same Mac, load not recorded. Five spend logs are about 5.8 MB each. The `traffic` log is 8.5 MB, `RM/proto/out/spend_log_traffic.csv`. Run time after the change is not measured.
- **Add a service-tier field.** Add `service_tier` and a long-context flag per row. Plant one scenario where a route switches to Fast mode. Concept 4.15.

### 6.3 Lab B: cascade against a randomized holdout, with full cost

- **Where it runs.** Laptop, offline. `RC/proto/cascade_holdout.py` as built.
- **What it prints.** Offline estimate, dashboard claim, measured LLM saving and measured full saving. Each measured saving has a user-level bootstrap interval. Then resolution per arm and requests per task.
- **Break-its.** `--no-retry`, `--human-cost 20`, `--users 2000` with three seeds.
- **Self-test.** 14 checks, including two hand cases. Hand case 2: offline 90%, measured LLM 85%, full -165%. Recomputed in `D14/recompute.txt` part D.
- **Cost.** Zero. The saved output shows 2.97 s for all scenarios.
- **Link.** Sizing and peeking for a real test are Module 12, 4.1 and 4.2. Do not re-teach them.

### 6.4 Lab C: admission overshoot

- **Where it runs.** Laptop, offline. Not built. Design from metering report lab idea 2.
- **What it would print.** Overshoot in dollars at concurrency 1, 10 and 100 against a $10 budget. Three policies: charge after the response, worst-case reservation, and reservation with `max_tokens` capped to the remaining budget.
- **Self-test.** At concurrency 1 with the cap, overshoot is 0.
- **Expected size, inferred.** 100 concurrent worst-case requests on Opus 5.5 add $11.39, at prices read 2026-09-25. `D14/recompute.txt` part E.
- **Overlap check.** Read Module 1's `phase03_economics/budget_guard.py` first. This lab adds concurrency and gateway policies only.
- **Cost.** Zero.

### 6.5 Lab D: fan-out roll-up

- **Where it runs.** Laptop, offline. Not built. Design from metering report lab idea 1.
- **What it would print.** Cost by tenant from model-call spans. The unattributed share when 5% of child calls lose the tenant. The double count when parent spans also carry cost.
- **Self-test.** The sum of model-call costs equals the trace total.
- **Cost.** Zero.

### 6.6 Lab E: cost-model audit

- **Where it runs.** Laptop, offline. Not built. Design from metering report lab idea 3.
- **What it would print.** The error of five wrong cost models on one request set. The five are: 0.1x cache everywhere, no cache class, and a batch discount on Gemini 3.1 Pro cache. Also the cancelled Sonnet 5 rise, and one tokenizer for all models.
- **Cost.** Zero.

### 6.7 Optional lab F: a real cascade with a hash-split holdout. Optional, UNVERIFIED

- **Where it runs.** Laptop, with a hosted API key. Not built.
- **Cost estimate at 2026-09-25 list prices.** 200 tasks per arm at 1,000 input and 300 output tokens. Control on Claude Sonnet 5 costs $1.00. The cascade on Claude Haiku 4.5 with 80 escalations to Sonnet 5 costs $0.90. Total $1.90, with no judge. `D14/recompute.txt` part E. Reprice on the day you run it.

Summary: build lab A first. It answers the module question with one run. Labs B to E each support one concept.

---

## 7. Conflicts resolved

| Conflict | Sources | Evidence used | Resolution |
|---|---|---|---|
| a. Can LiteLLM's logs separate a cache collapse? | Metering report 1.3 says the spend log cannot | `RM/src/ll_schema.prisma`: `LiteLLM_SpendLogs` lines 629 to 668 has no cache column. Six `LiteLLM_Daily*Spend` tables have `cache_read_input_tokens` and `cache_creation_input_tokens`, lines 782 to 962 | Both are true at different grain. The per-call log cannot. The daily tables can, per key, model and day. They lack price version and TTL. Teach 4.4 with both facts |
| b. Which decomposition for the lab | Metering report: Shapley. Cascades report: LMDI-I | Section 6.1. `D14/recompute.txt` part C: on one line the two exact methods differ, calls +4,083 against +4,216 | Merge on the Shapley base, add calls per request. State the method next to every number |
| c. What "traffic" means | `bill_diff.py` counts model calls. `bill_drivers.py` counts requests and calls per request separately | `bill_diff.py` line 163. `bill_drivers.py` factor lists | Traffic means root requests. Calls per request is its own factor. The module question's "traffic did not" then has one meaning |
| d. How much a cache collapse can raise input cost | Cascades report 2.2: "up to 10x on cached tokens". Metering report 2.3: read ratios 0.05x and 0.025x | `RM/src/anth_pricing.md` lines 36 to 40 | 10x on 0.1x models, 20x on Opus 5.5, 40x on Fable 5.1 and Mythos 5.1, when hits become uncached input. Review: when every request also writes the cache, the rise is 12.5x to 20x, 25x to 40x, and 50x to 80x. See 4.4 |
| e. `bill_drivers.py` self-test count | Cascades report 5: "11 checks pass" | `RC/proto/out_bill_drivers.txt` has 9 PASS lines and 0 FAIL | 9 checks. The report's 11 is wrong. The checks it lists are the 9 in the file |
| f. Module 1 is out of date on four points | Module 1 3.2, 3.3 and 3.5 against the metering report | Module 1 3.5 says the token metric has no cache dimension. PR #374 added per-class counters on 2026-09-22, `RM/src/og_374.breaking.md`. Module 1 3.5 says exactly one gateway documents mid-stream behaviour. Agent Router and OpenRouter workspace budgets now document letting a stream finish. Module 1 3.2 and 3.3 say reads cost 0.1x. Opus 5.5 is 0.05x and Fable 5.1 is 0.025x. Module 1 says "All 118 attributes" at a 2026-09-10 commit. The 2026-09-22 registry has 72 `key: gen_ai` lines and 120 `stability: development` lines | Module 1 needs four one-line updates. The attribute counts use different commits and methods. They do not contradict. Teach "all development, none stable" |
| g. RouteLLM: 85% or 3.66x | Blog against paper, same authors. The FinOps page repeats 85% without the baseline, `RC/src/finops_effect-of-optimization-on-ai-forecasting_browser.txt` lines 165 to 167 | `RC/src/routellm_blog.txt`, `RC/src/routellm_v4.txt` 5.4 | Different baselines: GPT-4 only against a random router. Quote each with its baseline |
| h. Router overhead: negligible or not | RouteLLM "no more than 0.4%". RouterArena "non-negligible overhead" | Table 7 against Figure 9 | Different units. RouteLLM measures dollars against an expensive model. RouterArena measures latency, including external API calls. At Haiku 4.5 prices the dollar share is 2.77% |
| i. RouteLLM 0.4% against 0.44% | Paper against the cascades report recompute | `D14/recompute.txt` part D reproduces 0.44% | The paper prints the inputs in Appendix D: 95 input and 264 output tokens at $10 and $30. It does not print the division. Quote 0.44% as a recompute and 0.4% as the paper's words. The reviewer recomputed $39.26 / 1,000,000 / $0.00887 = 0.44% |
| j. Who owns a live cascade holdout | Cascades report puts it in Module 14. Module 12 4.1 to 4.3 owns A/B sizing, peeking and must-not-worsen metrics, including cost per conversation | `agent-evals/agent-evals-phase-04-ab-tests.md` lines 71, 243, 398 and 518 | Module 14 keeps only which cost lines move and estimate against measured saving. Module 12 owns the test design |
| k. `bill_drivers.py` example prices | $3 and $15 per million tokens, "not a price sheet" | `RM/src/anth_pricing.md` line 42: the $3 and $15 Sonnet 5 rise will not occur | Harmless as an example. The merged lab must use the dated price sheet in 5.1 |
| l. Cascade closed form against simulation | `RC/proto/out_main.txt` | Closed-form LLM saving 47.9% lies below the simulated interval of 48.1% to 50.2% for the regressed case. 23.7% lies below 24.4% to 26.9% for the harder mix | Mostly settled in the coherence pass, 2026-09-25, from the Module 14 Phase 3 runs `code/runs/ai-finops_p03_cascade_converge.txt` and `ai-finops_p03_cascade_coverage.txt`. With 200,000 users the simulation gives 48.1% against a closed form of 47.9% for the regressed cascade, and 23.6% against 23.7% for the harder mix. Across 40 seeds at 6,000 users, the interval holds the closed form in 36 to 38 of 40 runs per scenario. So the two misses are most likely sampling. This is inferred. For the regressed cascade, the 200,000-user run and the mean of the 40 seeds both sit 0.2 points above the closed form, about 2.5 standard deviations. So a gap of about 0.2 points between the two code paths is not ruled out. For the harder mix the two checks sit on opposite sides, which looks like noise. The review's guess that the retry path causes the gap is not checked. A gap of 0.2 points changes no conclusion in Phase 3 section 3.4. Phase 3 E12 says the same |
| m. Cascade lab run time | Cascades report 5: 1.52 s | `RC/proto/out_main.txt` records real 2.97 s | The saved file wins. Quote 2.97 s for the saved run. Machine load not recorded |

---

## 8. Gap list, ranked by how much the module question needs it

| Rank | Gap | Why the module question needs it | What was done |
|---|---|---|---|
| 1 | The merged bill-decomposition lab with calls per request, a fan-out scenario and a two-cause scenario | It is the one run that names tenant, route and model change. Neither prototype does all three | Not built. Design in 6.2 |
| 2 | Decompose a real gateway export, for example LiteLLM daily tables | 4.4 says what a log needs. No one tested a real export | Not run. The daily tables were read from the schema only |
| 3 | Whether LiteLLM fills the daily cache columns for each provider | Conflict a depends on it | Not checked. Read the daily-spend writer at v1.102.1, or run a proxy with a cached request |
| 4 | Fan-out roll-up with the unattributed share | "Which tenant" fails when a sub-agent drops the tenant | Not built. Lab D |
| 5 | A first-party postmortem of a bill change traced to its cause | Shows the method on real data | None found by either report. Metering report item 13 |
| 6 | Size of the order gap with two planted causes | 4.7 claims the gap grows | Inferred from the algebra. Not run |
| 7 | Price-version history for each provider | A price change cannot be split without it | Not checked. Only today's pages and one announced change were read |
| 8 | Which mechanism OpenRouter's auto router used when LLMRouterBench tested it | "Which route" can mean an auto router's choice | Not checked |
| 9 | Admission overshoot under concurrency | "How to stop it next month" | Not built. Lab C |
| 10 | Whether providers bill tokens after a client disconnects | Budget stops can still cost money | Not checked |
| 11 | A randomized live holdout for a router or cascade | Whether routing caused the rise | None published. Searched by the cascades agent |
| 12 | A measured forecast error for LLM spend | Whether next month's bill was predictable | None published. The FinOps 5% is a target |
| 13 | Portkey budget timing and overshoot | Completes the table in 4.1 | Not documented in the 11 saved pages |
| 14 | A rule for who pays a shared cache write | Per-tenant cost depends on arrival order | No gateway documents one. Design decision |
| 15 | Cause of the closed-form gap in the cascade lab | Lab B's credibility | Not checked. Conflict l. Review narrowed it to the retry path |
| 16 | Service tier and long-context flag in the spend log | "Which model change" misses a Fast-mode switch at 2x with the same model | Added in review as concept 4.15. Prices verified. Gateway support not checked |
| 17 | Model alias drift: a floating alias such as a "latest" name moves to a new snapshot with no code change | A model change with no deploy. Only the responded-model field shows it | Not checked. No saved source documents a drift and its bill effect. Check: provider model-alias docs and a log of `response.model` over a month |
| 18 | A default change in reasoning effort or thinking budget | Output tokens per call rise with the same model name. Google bills thinking as output, `RM/src/g_pricing.txt` | Inferred. No saved source measures a bill change from a default change. Check: plant it in lab A as an output-length change |
| 19 | Per-request fees such as search grounding | A route that adds a tool can raise the bill with flat tokens | Verified price, 4.15. Not modelled in either prototype |

---

## 9. Things not verified

Each item has the check that would settle it.

### 9.1 From the metering report

1. LiteLLM docs pages. The paths tried at the tag returned 404. Source code was used instead. Check: `docs.litellm.ai/docs/proxy/cost_tracking`.
2. LiteLLM behaviour during a stream at a budget. No code path was found. Streaming handlers were not read. Check: grep `BudgetExceededError` in `proxy_server.py` at v1.102.1, then run a proxy with a tiny budget.
3. The meaning of LiteLLM's `cache_hit` column. Inferred to be LiteLLM's own response cache. Check: the writer in `spend_tracking_utils.py`.
4. Portkey enforcement timing, overshoot, and cache classes in cost. Check: a $1 budget with concurrent streams, and a log entry for a cached request.
5. Kong consumer to tenant mapping for AI rate limits. Check: the `identifier` option on the 2.x policy page.
6. Whether Agent Router v1.1.0 code still emits `gen_ai.client.token.usage`. Check: grep the v1.1.0 tag.
7. Whether providers bill tokens generated after a client disconnects. Check: provider docs on cancellation, or a paid test.
8. OpenAI short against long context threshold. Check: the pricing page in a browser.
9. Gemini 3.5 Flash-Lite batch. Check: `RM/src/g_pricing.txt` lines 599 to 693. The Claude Sonnet 5 and Haiku 4.5 batch prices were settled in review, 5.1.
10. Whether Cloudflare's default cost uses cache rates. Check: a log entry for a cached Anthropic request.
11. Size of the order gap with two causes. Check: lab A step 3.
12. A real-world postmortem of a bill doubling. Not searched again today.
13. Anthropic API reports cache reads and writes apart from input tokens. So an instrumentation must add them to follow the OpenTelemetry inclusion rule. Not checked today.

### 9.2 From the cascades report

14. A randomized live holdout for an LLM router or cascade on real users. None found. Check: ACL and EMNLP 2026 industry tracks and engineering blogs.
15. FrugalGPT peer review status. Check: the TMLR listing.
16. RouteNLP ACL 2026 acceptance. Only the arXiv comment says so. Check: the ACL Anthology. RouterArena's ICLR 2026 status is also not in any saved source. Check: the OpenReview listing.
17. RouteNLP's "$200K/month" motivation figure. Stated by the authors, no conditions.
18. OpenRouter auto-router mechanism at the time LLMRouterBench tested it. Check: the OpenRouter changelog.
19. When Martian stopped offering a public router. Check: archived snapshots.
20. The exact RouteLLM "0.4%" derivation. The paper does not print it.
21. Publication dates of the Epoch AI page and several FinOps pages. Check: page footers in a browser.
22. The relationship between the FinOps Foundation and the Tokenomics Foundation site. Only the link is verified.
23. OpenRouter State of AI consistency: prompt 6K plus completion 400 does not match a mean sequence length "over 5,400". Check: the figure data.
24. What FOCUS v1.4 changed for AI usage. Check: the v1.4 changelog.
25. Maintenance status of RouteLLM, RouterArena and TwinRouterBench repositories. The GitHub rate limit blocked the check. PyPI `routellm` 0.2.0 is from 2024-07-08.
26. Not Diamond's accuracy and cost claims. No conditions published.
27. A measured forecast error for LLM spend. None found.
28. The cascade prototype's retry rate, ticket cost and ticket probability. Illustrative. Check: join support tickets to a real experiment arm.

### 9.3 From this dossier

29. Whether LiteLLM fills the six daily cache columns for every provider. Read from the schema only.
30. Why the cascade closed form falls outside the simulated interval in two scenarios. Conflict l. Coherence pass, 2026-09-25: most likely sampling, inferred from 200,000-user and 40-seed runs. A gap of about 0.2 points on the regressed cascade is not ruled out.
31. The run time of the merged lab A. Not built.
32. Anchors marked "metering report 2.1" or "cascades report 2.1" in section 4 were not re-grepped. They support a concept. They are never its best evidence.
33. Overshoot of $11.39 and lab F cost of $1.90 are arithmetic on stated assumptions, not measurements.

### 9.4 Anchor and arithmetic re-check

The dossier author grepped 75 anchors from section 4 on 2026-09-25. Whitespace is collapsed. Backticks and double asterisks are removed. Curly quotes are made straight. Script: `D14/anchor_check.py`. Output: `D14/anchor_check.txt`.

- **75 of 75 anchors match.** 57 are presence checks. 3 are absence checks, such as "tenant" with 0 hits in the GenAI registry. 15 check an exact count. Examples are 6 hits of `cache_read_input_tokens BigInt @default(0)` in `ll_schema.prisma`, 72 `key: gen_ai` lines, and 1 hit of each quoted prototype output line.

| Concept | Anchors | Concept | Anchors |
|---|---|---|---|
| 4.1 | 5 of 5 | 4.8 | 6 of 6 |
| 4.2 | 3 of 3 | 4.9 | 5 of 5 |
| 4.3 | 5 of 5 | 4.10 | 6 of 6 |
| 4.4 | 7 of 7 | 4.11 | 5 of 5 |
| 4.5 | 7 of 7 | 4.12 | 5 of 5 |
| 4.6 | 5 of 5 | 4.13 | 5 of 5 |
| 4.7 | 6 of 6 | 4.14 | 5 of 5 |

- **One needle needed its exact text.** The metering report writes `DEFAULT_MAX_TOKENS_ESTIMATE = 4096`. The source says `DEFAULT_MAX_TOKENS_ESTIMATE: Final = 4096`, `ll_rl_v3.py` line 343. The value is the same. Coherence pass, 2026-09-25: the value is not the output estimate the limiter reserves. See the corrected line in 4.3.
- **One report statement was corrected by the re-read.** The LiteLLM daily tables have cache columns. Conflict a.
- **Arithmetic.** `D14/recompute.py` recomputed 79 stated values. They cover price ratios, prototype hand cases, bill ratios and shares, and the LMDI lines. They also cover TwinRouterBench ratios, router overhead, RouteNLP shares and the cascade hand cases. All 79 agree. It found one new fact: Shapley and LMDI split the same line differently, 4.7.
- Every quote in section 4 is 25 words or shorter.

---

## 10. Review log

Review on 2026-09-25 by an independent reviewer who did not write the dossier. Scope: read and fetch only. No lab ran. The reviewer ran the three saved self-tests. Reviewer files are in the reviewer's scratchpad: `spot.py` for anchors and `fetch/` for today's pricing pages.

### 10.1 What was checked, and the result

| Check | Method | Result |
|---|---|---|
| Anchors | 49 needles from 4.1 to 4.14, grepped by a new script, not by `D14/anchor_check.py`. 31 of them are in 4.1, 4.4, 4.6, 4.7, 4.9, 4.10 and 4.12 | 46 match as quoted. 2 match after joining a hyphen at a PDF line break, both in `routenlp.txt`. 1 was cited to the wrong file, 4.6 |
| Line numbers | 13 cited line numbers checked by script. Also `ll_schema.prisma` 629 to 963, `bill_diff.py` 163, `anth_pricing.md` 149, 163, 174 and 216 | All hold |
| Anthropic prices | `curl` of the `.md` page | Byte-identical to `RM/src/anth_pricing.md`. 0.025x, 0.05x and 0.1x hold. 40x on Fable 5.1 and 20x on Opus 5.5 hold as 1 divided by the read ratio |
| OpenAI prices | `curl`, visible text compared | Text identical to the saved copy. Batch and Flex half, Fast mode 2x, in every class and both context lengths |
| Google prices | `curl` with a cookie jar, HTTP 200 | Text identical. "Last updated 2026-09-24 UTC". Every 5.1 row holds |
| LiteLLM version | PyPI JSON | 1.102.1, uploaded 2026-09-23. Still the latest |
| PR #443 state | GitHub API | Not checked. HTTP 403, rate limit |
| Self-tests | `bill_diff.py --self-test`, `bill_drivers.py --self-test`, `cascade_holdout.py --self-test` | 27 of 27, 9 of 9, and PASSED. `bill_diff.py` took 2.05 s real |
| Shapley against LMDI | Hand computation of the `/report` line | Shapley calls +$4,083, input +$310.5, output +$1,425. LMDI +$4,216, +$277, +$1,326. Both sum to $5,818.8. The dossier holds |
| Order gap | `breakit_output.txt` | +4.47 and +11.78. Mean 8.125, Shapley +8.13. Ratio 2.64 |
| Cascade estimate against measured | `out_main.txt`, `out_humancost.txt` | +47.5% to +55.0% offline, +30.8% to +10.3% full. Ticket cost 20 gives -37.5%. All hold |
| Router overhead | Hand computation | $0.00887 and $0.001415 per request. 0.44% and 2.77%. Holds |
| Bill-split examples | `out_bill_drivers.txt`, `run_all_output.txt` | $6,474 to $13,022, change $6,548, 64.4%. Five `bill_diff.py` scenario rows in 5.4 hold |
| Overshoot and lab F cost | Hand computation | $11.392 and $1.90. Hold |

### 10.2 The 13 resolved conflicts

| Conflict | Verdict |
|---|---|
| a | Holds. `SpendLogs` lines 629 to 668 has no cache column. Six daily tables have both columns, lines 782 to 963. `LiteLLM_DailyToolSpend`, line 1181, does not |
| b | Holds. Recomputed by hand, 10.1 |
| c | Holds. `bill_diff.py` line 163 writes an empty parent for every row |
| d | Holds for hits that become uncached input. Incomplete for hits that become writes. Corrected, 4.4 |
| e | Holds. 9 PASS lines |
| f | Holds. The Module 1 lines are listed in 10.4 |
| g | Holds. The FinOps file is now named |
| h | Holds. RouterArena line 761 says "non-negligible overhead" |
| i | Holds, reworded. Appendix D prints the inputs, not the division |
| j | Holds. `agent-evals-phase-04-ab-tests.md` lines 71, 243, 398 and 518 are the three A/B headings and the must-not-worsen list |
| k | Holds. `bill_drivers.py` line 94 |
| l | Holds as "not settled". Review narrowed the cause to the retry path |
| m | Holds. `out_main.txt` shows real 2.97 s. The cascades report line 339 says 1.52 s |

### 10.3 Corrections made in the text, by kind

**Source misread. The most serious.**

1. 4.12 and 5.3. The draft called RouteNLP's "8 to 9% substantially degraded" a deployment result. It is from the offline human evaluation, section 5.3, 200 samples per task. The pilot audit is a different check: 500 pilot responses, 2.6% unacceptable against 1.8%, and no significant change in complaints. `RC/src/routenlp.txt` lines 715 to 749 and 797 to 804.
2. 4.10, 5.3 and 3.1. The draft used LLMRouterBench's -24.7% as evidence that a router raises the bill. It is an accuracy change against the best single model, line 297. The conditions were also wrong: 13 flagship models on 10 datasets, not 21 datasets and 33 models.
3. 5.3. The metric for "62% simulated, 58% pilot" was given as the expert rating. It is cost against Always-T4, Table 6.

**Arithmetic stated too strongly.**

4. 4.4 and conflict d. "The largest possible rise is 1 divided by the read ratio" is wrong when each request writes the cache. The `bill_diff.py` collapse writes on every request. The rise is then 50x or 80x on Fable 5.1.

**Wrong citation.**

5. 4.6. The OpenTelemetry inclusion rule is in `og_docs_registry_attributes_gen-ai.md` lines 333 and 335, not in `token-metrics.yaml`.

**Labels.**

6. Vendor claim added: Anthropic's 15x multi-agent figure in 4.7, and the 30% tokenizer figure in 4.8.
7. Preprint added: TwinRouterBench in 4.10 and 5.3, and the front-door study in 4.9.
8. Venue: RouterArena "ICLR 2026" is in no saved source. Now "venue not checked" in 3.1, 3.2 and 5.3. RouteLLM ICLR 2025 is now verified from a citation in `twinrouterbench.txt`. RouteNLP keeps "per the arXiv comment".
9. Price dates added in 4.1, 4.6, 4.8 and 6.4.

**Filled or updated from today's pages.**

10. 5.1. Batch prices for Sonnet 5, $1 and $5, and Haiku 4.5, $0.50 and $2.50. Item 9 of 9.1 is updated.
11. 5.1. Fable 5 and Mythos 5 use 0.1x. Only the ".1" models use 0.025x.
12. 4.6. Anthropic's caching section still opens with "10% of the standard input price", line 149.
13. 6.2. The `traffic` spend log is 8.5 MB, not 5.8 MB.

**Scope and links.**

14. Section 2. Module 13 and Module 15 dossiers now exist. The table links them. Service tiers and retries now link Module 1, 3.1 and 5.3.

**Added concepts, each with evidence.**

15. Concept 4.15, service tier, long-context tier, data residency and per-request fees. Prices verified on today's pages. The row in section 1 and the lab A step are added.
16. 4.11. RouteNLP's break-even at about a 25x price ratio.
17. Gap rows 16 to 19 in section 8. Rows 17 and 18 are not checked or inferred.

### 10.4 Module 1 lines that are out of date. For the learner to decide. Module 1 was not edited

| File and line | What it says | What is true on 2026-09-25 | Evidence |
|---|---|---|---|
| `inference-internals-phase-03b-routing-alerting.md:503` and `phase-03a-caching.md:650` | The standard token metric has no dimension for cache reads or writes | PR #374 of 2026-09-22 added a counter per class | `RM/src/og_374.breaking.md`, `og_model_gen-ai_token-metrics.yaml` line 52 |
| `phase-03b-routing-alerting.md:467` | Exactly one gateway or provider documents mid-stream behaviour | Agent Router and OpenRouter workspace budgets now document letting an admitted stream finish | 4.1 and 4.2 |
| `phase-03b-routing-alerting.md:496` and `phase-03a-caching.md:648` | "All 118 attributes" at a commit of 2026-09-10 | Still no cost attribute and no stable one. The counts use different commits and methods | Conflict f |
| `phase-00-frame.md:174` and `:192`, `phase-01-lifecycle.md:672`, `phase-03a-caching.md:203`, `:402`, `:437`, `:570`, `:615`, `:711` | Cache reads cost 0.1x input | True for most models. Opus 5.5 is 0.05x. Fable 5.1 and Mythos 5.1 are 0.025x | `RM/src/anth_pricing.md` lines 36 to 40 |
| `phase-03a-caching.md:87`, `:691`, `:696` | The "priority" tier | OpenAI renamed Priority processing to Fast mode on 2026-07-30. Both `service_tier` values work | `RM/src/oai_pricing.txt` |
| `code/prices.yaml:42` and `:116` | A `gpt-5.6-terra` row verified on 2026-09-12, used as the `cache_demo` role | The OpenAI pricing page lists `gpt-5.6-terra` on 2026-09-25. Short-context prices are $2.00 input, $0.20 cached, $2.50 write and $12.00 output, the same as on 2026-09-12. See 10.7 | OpenAI `pricing.md` fetched on 2026-09-25, line 40, in the Module 1 fix evidence |
| `code/prices.yaml` | No Opus 5.5 or Fable 5.1 rows, and no per-model read ratio | Lab A step 4 needs them | 5.1 |

### 10.5 What the review did not do

- It did not re-grep every anchor. It checked 49 of about 75.
- It did not re-read the gateway pages behind 4.1 to 4.3 and 5.2, beyond the quoted lines.
- It did not check the state of PR #443 today. The GitHub API returned 403.
- It did not run the labs or change the prototypes.

Summary of the review: the arithmetic and the prices hold. Three source readings were wrong, and the RouteNLP and LLMRouterBench ones changed what the dossier claims.

### 10.6 Coherence pass, 2026-09-25

The Module 14 coherence reviewer made these changes after the four phases were written and fact-checked. Each one follows a phase fact check.

| Section | Old | New | Evidence |
|---|---|---|---|
| 4.3 | LiteLLM assumes 4,096 output tokens when a request has none | The dollar reservation assumes 16,384 tokens, capped at the model's maximum output. The token-rate limiter reserves the larger of the input estimate and 1,024 = 4,096 // 4, lower for a limit below 4,096, or an operator-set estimate | Module 14 Phase 2 fact check. `parallel_request_limiter_v3.py` lines 343, 349, 699 to 702, 968 to 982, and `budget_reservation.py` lines 1514 and 1535 to 1536, both at tag v1.102.1 |
| 4.2 | No gateway read here documents the `max_tokens` cap | No gateway documents a cap from the remaining budget. LiteLLM's token-rate limiter writes a `max_tokens` of a quarter of a small token limit | `parallel_request_limiter_v3.py` lines 806 to 854, called at 3344 and 3590 |
| 7, conflict l | Not settled. The review narrowed the cause to the retry path | Most likely sampling, inferred. A 0.2-point gap on the regressed cascade is not ruled out. The retry-path cause is not checked | Module 14 Phase 3 E12 and its runs `ai-finops_p03_cascade_converge.txt` and `ai-finops_p03_cascade_coverage.txt` |
| 9.3 item 30, 9.4 | as above | a pointer to the new text | as above |
| 4.3, OpenRouter | fixed cap, exclusions | adds that the in-flight hold applies to a subset of prepaid accounts only | `or_limits.md` line 348, Phase 2 fact check |

The Phase 2 writer's first correction note said "4,096 tokens is LiteLLM's token-rate limiter default". That note was also wrong. The rule above replaces it.

### 10.7 Correction, 2026-09-25

- Section 10.4, the `gpt-5.6-terra` row, was wrong. It said the name does not appear on the OpenAI pricing page. A full fetch of `pricing.md` on 2026-09-25 lists it at line 40, with the same four short-context prices as on 2026-09-12. Inferred: the earlier text extract missed it. Not checked against the old extract. So the `cache_demo` role still uses a listed model. Verified in the Module 1 fix report and its saved page `oai_pricing_2026-09-25.md`.
- Module 1 was corrected on 2026-09-25. It now states the #374 token counters, the 82 attribute keys at `8ffdf568`, and `app.cost.usd` as the cost key. It no longer says one gateway documents a mid-stream budget error. So the other rows of 10.4 describe old Module 1 text. Verified by grep in `inference-internals-phase-03b-routing-alerting.md` and `phase-03a-caching.md` on 2026-09-25.
- Module 14 Phases 1 and 2 no longer describe Module 1 as out of date. They state each fact and link the Module 1 section that agrees.


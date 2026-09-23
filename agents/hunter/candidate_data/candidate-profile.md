# Candidate profile

Updated: 2026-09-11

Source: owner-provided resume at `candidate_data/raghvendra_resume.pdf`, plus
the owner's stated target roles. Use this file for job discovery and fit
scoring. Do not infer an unlisted preference as fact.

## This is a switch at the SAME level, for better pay

Read the tenure before judging any role against it, from the resume:

| | |
|---|---|
| Juspay, Product Engineer - I | **July 2026 to now — about 2 months** |
| Mindtickle, SDE Intern (AI & Backend) | Aug 2025 – Jul 2026 — **11 months** |
| Verly, co-founder | Nov 2025 – May 2026, a side venture, listed under projects |
| B.Tech, IIIT Nagpur | Nov 2022 – 2026, GPA 8.03 |

That is roughly **thirteen months of engineering in total, two of them
post-graduation and full-time**. He is early in his first proper role, not a
year-two engineer looking to level up.

So the target is **level one**, stated in his own words: SDE-1, AI Engineer-1,
Forward Deployed Engineer-1, Product Engineer-1, or an equivalent rung —
**paying 25 LPA or better**. He is not underlevelled and he is not chasing a
promotion; he is moving for the pay and the work.

**Do not target SDE-2 or level-2 roles.** An earlier version of this file said
SDE-2 was "the natural next rung". It is not, on two months of full-time
experience, and searching there wastes runs on roles that will not screen him
through.

What that rules out, on top of the negative signals below:

- **Internships and trainee programmes.** He is employed; he is past them.
- **Fresher-only postings** that would not credit the internship year.
- **SDE-2, Engineer II and above.** Wrong rung for the tenure.
- Anything paying below 25 LPA, which is the point of the move.

## Target roles

Level-one roles only, in these three lanes. Customer-facing
engineering counts fully: forward deployed, solutions engineering with real
code, deployment and integration engineering, and customer-facing product
engineering are all on-target, not fallbacks. His Juspay and Verly work is
exactly this shape — escalation workflows, tenant configuration, integrations,
turning a customer's policy into a working system.

1. **Software engineering:** SDE-1, Software Engineer I, Product Engineer I,
   Backend Engineer I, Associate Software Engineer, Graduate Software Engineer.
2. **Forward deployed and customer-facing engineering:** Forward Deployed
   Engineer I, Forward Deployed Software Engineer, Deployment
   Engineer, Implementation Engineer, Integration Engineer, Solutions
   Engineer / Solutions Architect-adjacent roles **with substantial hands-on
   coding**, Sales Engineer where the work is genuinely technical, Technical
   Account Engineer, Developer Experience or Developer Relations Engineer,
   Support Engineer at the escalation/debugging end, and customer-facing
   product engineer roles. This lane is a first-class target: it is where his
   Juspay escalation and policy-engine work reads strongest, and fewer
   candidates can do both halves.
3. **Applied AI engineering:** AI Engineer I, Applied AI Engineer, Generative AI
   Engineer, LLM Engineer, AI Backend Engineer, and entry-level AI platform or
   agent infrastructure roles.

Treat equivalent titles as relevant when the work and seniority match. The
sweet spot is **0-2 years of required experience**; 2-3 years is a stretch he
can sometimes clear on the strength of the internship and the Go/gRPC and
agent-infrastructure work, so score it lower rather than skipping it. A role asking for 2-3 years may be a stretch;
roles clearly requiring senior, staff, lead, principal, manager, or founding
engineer scope are not targets. **A floor of three years or more is out**, and
`record_job` files such a role as closed by itself — see "Confirmed
preferences" below.

## Current position and employer exclusion

- Current employer: **Juspay**.
- Current title: Product Engineer I, from July 2026.
- Do not search for or recommend roles at Juspay unless the owner explicitly
  asks for internal opportunities.
- Current location shown on the resume: Bengaluru, Karnataka, India.

## Experience evidence

### Juspay - Product Engineer I (July 2026 - present, ~2 months)

- Built a chatbot-to-human escalation workflow that preserves conversation
  context and state.
- Designed a unified guardrail layer for voice and text agents covering prompt
  injection, toxicity, policy violations, and off-topic responses.
- Built a configurable multi-tenant policy engine for custom compliance rules
  and agent behavior.

### Mindtickle - SDE Intern, AI and backend systems (Aug 2025 - Jul 2026, 11 months)

- Shipped a Go/gRPC microservice using hexagonal architecture and a database-
  backed voice and language model supporting 25+ languages and 800+ voices.
- Built Kubernetes CronJob, webhook, and Redis-backed asynchronous workflows
  for an ElevenLabs voice lifecycle pipeline.
- Shipped an LLMOps evaluation pipeline that streams transcripts and bot
  metadata to automated evaluators.

### Verly - Co-founder and Software Engineer (Nov 2025 - May 2026, side venture)

- Built a production AI customer-support platform for web chat, WhatsApp, and
  voice with knowledge ingestion and human escalation.
- Built a Go-based graph RAG pipeline, identity verification, and custom MCP
  integrations with per-tenant tool access.
- Built analytics for conversation quality, failure modes, and CSAT signals.

## Technical strengths

- Languages: Go, TypeScript, JavaScript, Python, Java, C++, C, SQL.
- Backend: gRPC/Protobuf, REST, WebSockets, microservices, hexagonal
  architecture, asynchronous workflows.
- AI: RAG, AI agents, MCP, guardrails, LLM evaluation, Gemini, LangChain,
  AssemblyAI, ElevenLabs.
- Infrastructure: Docker, Kubernetes/Helm, AWS, Redis, Datadog, Grafana,
  GitLab CI.
- Data: PostgreSQL, MySQL, MongoDB, Prisma, Drizzle ORM, Supabase.
- Frontend: React, Next.js, Tailwind CSS.

## Differentiators

- Production experience spanning backend systems and applied AI rather than
  notebook-only ML work.
- Customer-facing product experience relevant to forward deployed roles:
  tenant configuration, integrations, escalation workflows, and translating
  business policies into working systems.
- Strong algorithms record: Codeforces Expert (1800), LeetCode Guardian 2147
  (top 1.2%), and CodeChef 4-Star (1993).
- B.Tech in Computer Science Engineering at IIIT Nagpur, GPA 8.03.

## Fit rules

Strong signals:

- Level-one scope: SDE-1, Software Engineer I, AI Engineer I, Forward Deployed
  Engineer I, Product Engineer I, Associate Software Engineer. Same rung he is
  on now — the move is for pay and work, not a promotion.
- Backend ownership using Go, APIs, distributed systems, Postgres, Redis,
  Kubernetes, or event-driven workflows.
- Applied AI work involving agents, RAG, MCP, evaluation, guardrails, voice, or
  production LLM systems.
- Forward deployed work that combines coding, integrations, deployment,
  debugging, customer discovery, and rapid product iteration.

Negative signals:

- Senior-level ownership or more than three years required with no flexibility.
- Internships, trainee or fresher-only programmes: he is already employed.
- Customer-facing roles that are mainly demos, quota or account management
  with little engineering — the lane is technical or it is not a target.
- Pure data-science/research roles requiring advanced ML research credentials.
- Solutions roles that are mainly sales, demos, or account management with
  little software engineering.
- Roles at the current employer, Juspay.

## Confirmed preferences

Stated by the owner on 2026-09-09. These are hard rules, and `record_job`
computes the fit score from them (`job_tools.fit_score`):

- **Seniority ceiling: under three years.** He is not eligible for roles whose
  experience floor is 3+ years, most of all at large companies, where the bar
  is a recruiter screen. Enforced in `record_job`.
- **Compensation target: 25 LPA or better.** Restated by the owner on
  2026-09-11 as the reason for the move, so treat it as the point of the
  search rather than a nice-to-have. It is still not a hard gate, because
  most postings publish no number and refusing those would empty the board —
  but it drives the score: +1 at or above, **-3 for a stated package clearly
  below 25** (a role that pays less than he earns now is not a switch), and
  the `pay_signal` dig is required for anything scoring 6+.
- **Work mode: hybrid, on-site and remote are all acceptable.** Never reject
  or mark down a role for its mode. Geography still matters: Bengaluru,
  elsewhere in India, or remote he can take from India. Remote-US-only is out.

## Preferences still unknown

Do not invent or use these as hard filters until the owner confirms them:

- Willingness to relocate beyond Bengaluru.
- Work authorization and visa-sponsorship requirements outside India.
- Preferred company size or industry exclusions.

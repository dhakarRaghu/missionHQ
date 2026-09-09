# Candidate profile

Updated: 2026-09-10

Source: owner-provided resume at `candidate_data/raghvendra_resume.pdf`, plus
the owner's stated target roles. Use this file for job discovery and fit
scoring. Do not infer an unlisted preference as fact.

## Target roles

Prioritize entry-level and level-one roles in these three lanes:

1. **Software engineering:** SDE-1, Software Engineer I, Product Engineer I,
   Backend Engineer I, Associate Software Engineer, Graduate Software Engineer.
2. **Forward deployed engineering:** Forward Deployed Engineer I, Forward
   Deployed Software Engineer, Deployment Engineer, Solutions Engineer with
   substantial hands-on coding, and customer-facing product engineer roles.
3. **Applied AI engineering:** AI Engineer I, Applied AI Engineer, Generative AI
   Engineer, LLM Engineer, AI Backend Engineer, and entry-level AI platform or
   agent infrastructure roles.

Treat equivalent titles as relevant when the work and seniority match. Prefer
0-2 years of required experience. A role asking for 2-3 years may be a stretch;
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

### Juspay - Product Engineer I

- Built a chatbot-to-human escalation workflow that preserves conversation
  context and state.
- Designed a unified guardrail layer for voice and text agents covering prompt
  injection, toxicity, policy violations, and off-topic responses.
- Built a configurable multi-tenant policy engine for custom compliance rules
  and agent behavior.

### Mindtickle - Software Development Engineer Intern, AI and backend systems

- Shipped a Go/gRPC microservice using hexagonal architecture and a database-
  backed voice and language model supporting 25+ languages and 800+ voices.
- Built Kubernetes CronJob, webhook, and Redis-backed asynchronous workflows
  for an ElevenLabs voice lifecycle pipeline.
- Shipped an LLMOps evaluation pipeline that streams transcripts and bot
  metadata to automated evaluators.

### Verly - Co-founder and Software Engineer

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

- Level-one, associate, graduate, early-career, or 0-2 year scope.
- Backend ownership using Go, APIs, distributed systems, Postgres, Redis,
  Kubernetes, or event-driven workflows.
- Applied AI work involving agents, RAG, MCP, evaluation, guardrails, voice, or
  production LLM systems.
- Forward deployed work that combines coding, integrations, deployment,
  debugging, customer discovery, and rapid product iteration.

Negative signals:

- Senior-level ownership or more than three years required with no flexibility.
- Pure data-science/research roles requiring advanced ML research credentials.
- Solutions roles that are mainly sales, demos, or account management with
  little software engineering.
- Roles at the current employer, Juspay.

## Confirmed preferences

Stated by the owner on 2026-09-09. These are hard rules, and the scoring
rubric in job.md applies them:

- **Seniority ceiling: under three years.** He is not eligible for roles whose
  experience floor is 3+ years, most of all at large companies, where the bar
  is a recruiter screen. Enforced in `record_job`.
- **Compensation target: 25 LPA or better.** Not a hard gate — most postings
  publish no number — but it steers the score: +1 at or above, -2 for a
  stated package clearly below. Always fill `compensation`; estimate with the
  basis when the posting is silent.
- **Work mode: hybrid, on-site and remote are all acceptable.** Never reject
  or mark down a role for its mode. Geography still matters: Bengaluru,
  elsewhere in India, or remote he can take from India. Remote-US-only is out.

## Preferences still unknown

Do not invent or use these as hard filters until the owner confirms them:

- Willingness to relocate beyond Bengaluru.
- Work authorization and visa-sponsorship requirements outside India.
- Preferred company size or industry exclusions.

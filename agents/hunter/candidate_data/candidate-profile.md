# Candidate profile

The owner's resume and stated targets, for job discovery and fit scoring.
Do not treat an unlisted preference as fact. His level, pay floor, years
ceiling and locations are also in `memory/decisions.md`, and `record_job`
scores and gates from them in code.

## His employers are withheld

His current and former employers are left out of this profile on purpose.
Never try to find out or write their names. Code refuses them at every board,
search, fetch and `record_job` call; when a call is refused for that reason,
move on to the next company.

## A switch at the same level, for better pay

| | |
|---|---|
| Product Engineer I at a payments infrastructure company | since July 2026, his first full-time role |
| SDE Intern (AI and backend) at a B2B SaaS company | Aug 2025 to Jul 2026, 11 months |
| Verly, co-founder | Nov 2025 to May 2026, his own side venture |
| B.Tech, IIIT Nagpur | Nov 2022 to 2026, GPA 8.03 |

About thirteen months of engineering in total, a few of them full-time
after graduation. He is early in his first proper role.

The target is **level one**, in his words: SDE-1, AI Engineer-1, Forward
Deployed Engineer-1, Product Engineer-1, or an equal rung, **paying 25 LPA or
better**. He moves for the pay and the work, not a promotion.

Out of scope:

- Internships and trainee programmes: he is employed.
- Fresher-only postings that would not credit the internship year.
- SDE-2, Engineer II and above: wrong rung for the tenure.
- Anything paying below 25 LPA.
- Roles at his current or former employer.

## Target roles

Level-one roles in three lanes. Customer-facing engineering counts fully:
it is where his escalation-workflow and policy-engine work reads strongest.

1. **Software engineering:** SDE-1, Software Engineer I, Product Engineer I,
   Backend Engineer I, Associate Software Engineer, Graduate Software Engineer.
2. **Forward deployed and customer-facing engineering:** Forward Deployed
   Engineer I, Forward Deployed Software Engineer, Deployment Engineer,
   Implementation Engineer, Integration Engineer, Solutions Engineer with
   substantial hands-on coding, Sales Engineer where the work is genuinely
   technical, Technical Account Engineer, Developer Experience or Developer
   Relations Engineer, Support Engineer at the escalation and debugging end,
   and customer-facing product engineer roles.
3. **Applied AI engineering:** AI Engineer I, Applied AI Engineer, Generative
   AI Engineer, LLM Engineer, AI Backend Engineer, and entry-level AI platform
   or agent infrastructure roles.

Equivalent titles count when the work and seniority match. The sweet spot is
**0-2 years required**. 2-3 years is a stretch he can sometimes clear on the
internship and the Go/gRPC and agent-infrastructure work: score it lower,
do not skip it. **A floor of three years or more is out**; `record_job` files
such a role closed by itself. Senior, staff, lead, principal, manager and
founding scope are not targets.

## Experience evidence

### Product Engineer I, payments infrastructure company (since July 2026)

- Built a chatbot-to-human escalation workflow that keeps conversation
  context and state.
- Designed a unified guardrail layer for voice and text agents: prompt
  injection, toxicity, policy violations, off-topic responses.
- Built a configurable multi-tenant policy engine for custom compliance rules
  and agent behaviour.

### SDE Intern, AI and backend, B2B SaaS company (11 months)

- Shipped a Go/gRPC microservice with hexagonal architecture and a
  database-backed voice and language model covering 25+ languages and 800+
  voices.
- Built Kubernetes CronJob, webhook and Redis-backed asynchronous workflows
  for a voice lifecycle pipeline.
- Shipped an LLMOps evaluation pipeline that streams transcripts and bot
  metadata to automated evaluators.

### Verly, co-founder and software engineer (side venture)

- Built a production AI customer-support platform for web chat, WhatsApp and
  voice, with knowledge ingestion and human escalation.
- Built a Go graph-RAG pipeline, identity verification, and custom MCP
  integrations with per-tenant tool access.
- Built analytics for conversation quality, failure modes and CSAT signals.

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

- Production work across backend systems and applied AI, not notebook-only ML.
- Customer-facing product work that fits forward deployed roles: tenant
  configuration, integrations, escalation workflows, business policy turned
  into working systems.
- Algorithms: Codeforces Expert (1800), LeetCode Guardian 2147 (top 1.2%),
  CodeChef 4-Star (1993).
- B.Tech in Computer Science Engineering, IIIT Nagpur, GPA 8.03.

## Fit signals

Strong:

- Level-one scope on the same rung he holds now.
- Backend ownership with Go, APIs, distributed systems, Postgres, Redis,
  Kubernetes or event-driven workflows.
- Applied AI with agents, RAG, MCP, evaluation, guardrails, voice or
  production LLM systems.
- Forward deployed work that mixes coding, integrations, deployment,
  debugging, customer discovery and fast product iteration.

Negative:

- Senior ownership, or more than three years required with no flexibility.
- Internships, trainee or fresher-only programmes.
- Customer-facing roles that are mostly demos, quota or account management.
- Pure data-science or research roles that need advanced ML research
  credentials.

## Preferences

Hard rules, scored by `record_job` (`job_tools.fit_score`):

- **Years ceiling: under three.** A 3+ year floor is out, most of all at
  large companies where a recruiter screens first.
- **Pay: 25 LPA or better** is the point of the move. Not a hard gate,
  because most postings publish no number, but it drives the score: +1 at or
  above, -3 for a stated package clearly below 25. The `pay_signal` dig is
  required for anything scoring 6+.
- **Work mode: hybrid, on-site and remote are all fine.** Never mark a role
  down for its mode. Geography matters: Bengaluru, elsewhere in India, or
  remote he can take from India. Remote-US-only is out.

Still unknown; never use as a hard filter:

- Relocation beyond Bengaluru.
- Work authorization and visa sponsorship outside India.
- Company size or industry exclusions.

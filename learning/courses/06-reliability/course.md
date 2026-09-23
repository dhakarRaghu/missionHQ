# Course 6 — Reliability, security and change
slug: elite-reliability
order: 6
source: local
language: Go against Mission HQ; the game days run on the real system

## Why this course

The largest outages of 2024–2026 were not consensus bugs. They were
overload, retries that amplified it, and configuration pushed to everything
at once: a DNS automation race that took down a cloud region, a doubled
config file that crashed a global proxy, an update with one field too many
that took down eight million machines. Every one of them was a mechanism from
this course. This is where the earlier courses meet production: the numbers
from course 1, the guarantees from course 5, and the question of whether a
failure stays small, gets seen, and can be undone.

Security is one phase here, at the service boundary — course 2 covers the AI
side. No sampled posting required security, but every senior review asks
where the boundaries are.

The inference-internals course already teaches SLO indicators, error budgets
and burn-rate alerts (5B), retry amplification, retry budgets, jitter and
circuit breakers (5A), token quotas and noisy neighbours (6A), fallback versus
failover (5B), and incident roles, rollback and postmortems (6B). Those
mechanisms are the same for any service, so this course assumes them. It
keeps what is new for a general service: freshness indicators, the four
telemetry signals, server-side admission control, metastable failure,
bulkheads, recovery ramps, cache stampedes, config rollout, and the security
boundary.

## What you will be able to do

Define what a service promises and alert on that, not on CPU. Diagnose an
injected failure from telemetry alone under a time limit. Push a service past
its capacity with naive retries, watch it collapse, then make it hold. Catch
a bad config in a staged rollout before it reaches everything. Draw the
security boundaries of your own service and prove one of them holds.

---

## Phase 1 — SLOs, telemetry and diagnosis
question: The dashboard is green and customers are complaining. Which number should have gone red, and how do you find the cause from the telemetry you have?
minutes: 120
assumes: latency distributions (1.1), the capacity envelope (1.2), hypothesis-driven profiling (1.3); SLO indicators including quality, error budgets, percentile ladders and multi-window burn-rate alerts (inference-internals 5B); triage by slice before the average (inference-internals 6B)
introduces: freshness and correctness indicators for a service, logs vs metrics vs traces vs structured events, high-cardinality telemetry, hypothesis-driven diagnosis, telemetry designed from failure questions
leaves-for-later: overload mechanics (6.2), change safety and incident command (6.3)

### Why you're here
The alert fires on CPU above 80%. It has fired forty times this year and been real twice. Meanwhile a dependency started returning empty results with status 200, the error rate stayed at zero, and the first sign was a customer email a day later. The dashboards measure the machine. Nobody measured the promise.

An SLO is the promise, written as a number. Telemetry is what lets you find out why it was broken. This phase builds both from the failure questions, not from what is easy to collect.

### Sections
1.1 — Freshness and correctness indicators: the empty 200 that availability and latency cannot see, measured where the user is
1.2 — The four signals: what logs, metrics, traces and structured events each answer, and what each cannot
1.3 — High cardinality: the field you need in the incident is the one you dropped for cost — how to keep it
1.4 — Designing telemetry from failure questions: for each way the service can fail, the one signal that separates it from the others
1.5 — Hypothesis-driven diagnosis: the list, one query per hypothesis, and the discipline of not fixing the first plausible thing
1.6 — Mission HQ's telemetry: the event log, run records and cost records — what they answer today, and the failure questions they cannot

### Lab
Write the SLOs for Mission HQ's task path, including a freshness indicator, and derive their burn-rate alerts with the inference-internals 5B recipe. Audit the current telemetry against a list of ten ways the path can fail, and add the signals that were missing. Then write a script that injects one of the ten at random and seals which one in a file you do not open. Diagnose it from telemetry alone in under 30 minutes, keeping the hypothesis list, then open the file.

### Demonstrate
SLOs with burn-rate alerts, a failure-question table with a signal per row, and one injected failure diagnosed from telemetry only under a time limit, with the hypothesis tree preserved.

### Test out
- Explain: which of the four signals answers which failure question, and why the field you need in an incident is often the one dropped for cost.
- Predict: for a described failure (dependency returns empty 200s), which of the four signals shows it first and which never will.
- Demonstrate: the timed diagnosis with the hypothesis list.

---

## Phase 2 — Overload and cascading failure
question: Load dropped back to normal an hour ago and the service is still down. What is it doing, and why does more capacity not fix it?
minutes: 150
assumes: the capacity envelope (1.2), backpressure (1.2), cache eviction (4.2); the knee and goodput as a capacity unit (inference-internals 6A); retry amplification across layers, retrying at one layer, retry budgets, full jitter, and the circuit breaker with its half-open probe (inference-internals 5A); token quotas, fair admission and noisy neighbours (inference-internals 6A); fallback versus failover and degrading on purpose (inference-internals 5B and 3B)
introduces: server-side admission control and load shedding by priority, bulkheads, metastable failure and recovery after overload, capacity envelopes as a contract, cache stampede and invalidation
leaves-for-later: config change safety (6.3)

### Why you're here
A dependency slowed down. Every caller retried three times. Five layers of callers each retrying three times turned one request into hundreds. The dependency, now truly overloaded, got slower, so callers retried more. When the original cause was fixed, the system stayed down: it was busy serving retries of requests whose clients had long since given up. This shape has a name — metastable failure — and it was the mechanism behind a 2026 outage at a major code-hosting platform.

You already know how a client's retries feed the queue. This phase is the server's side: why the loop keeps running after the trigger is gone, and the controls that have to be designed in before the day they are needed.

### Sections
2.1 — Overload as a control problem: the goodput curve of a general service, and why it collapses instead of flattening
2.2 — Admission control and load shedding at the server: refusing early, and choosing what to drop by priority
2.3 — Metastable failure: the sustaining loop that outlives its trigger, work done for clients that already gave up, and what breaks the loop
2.4 — Bulkheads: separate pools so one slow dependency cannot take the whole service
2.5 — Recovery after overload: draining queues, ramping traffic back (1% → 5% → 10% → 100%), and why recovery is a rollout
2.6 — Cache stampede and invalidation: the thundering herd on a cold key, request coalescing, TTL jitter, negative caching, and the invalidation that arrives late

### Lab
Drive Mission HQ's task path to twice its measured capacity with naive retries. Record goodput collapsing and staying collapsed after load drops. Add admission control and a bulkhead around the slow dependency, together with the retry budget and circuit breaker from inference-internals 5A. Drive it again. Show goodput holding at capacity and recovering when load drops.

### Demonstrate
Two goodput curves — collapse and hold — for the same overload, with the mechanism that made the difference named, and a measured recovery ramp.

### Test out
- Explain: metastable failure, and why adding capacity during one does not help.
- Predict: for a described overload and a described recovery ramp, whether the service returns to normal or stays in the sustaining loop, and why.
- Demonstrate: the collapse-then-hold curves.

---

## Phase 3 — Safe change and incident operations
question: The deploy was fine. The config push twenty minutes later took down every region at once. What should have stopped it at the first machine?
minutes: 150
assumes: SLOs for the task path (6.1), migrations under load (4.4), rollback for agent systems (2.5); burn rate (inference-internals 5B); incident roles, declaring early, severity, the postmortem template, blameless review, rollback to a known-good baseline, and a control group instead of before/after (inference-internals 6B)
introduces: configuration as production code, validation of internally generated config, staged rollout and percentage ramps, feature flags and kill switches, rollback and compatibility windows, schema and dependency compatibility, the rollback-or-fix-forward decision, postmortems that change something, rolling updates and connection draining
leaves-for-later: design-time failure domains (7.3)

### Why you're here
Code goes through review, tests, canaries and staged rollout. Config and content pushes go through none of them, because they are "just config" — and two of the largest outages of the last two years started that way: a permission change that doubled a generated file past a hard-coded limit, and a content update with 21 fields where 20 were expected. Neither would have survived the validation applied to user input. Both reached every machine in minutes.

Change is the highest-risk operation a running system performs. This phase treats every kind of change — code, config, schema, dependency — with the same discipline, and covers what to do when it goes wrong anyway.

### Sections
3.1 — Config is production code: versioned, reviewed, validated like user input, rolled out like a deploy
3.2 — Validation of generated config: size limits, schema checks, and the internal source you trusted too much
3.3 — Staged rollout: canaries, percentage ramps, and the signal that halts the ramp — with the SLOs from phase 1
3.4 — Feature flags and kill switches: the change you can turn off faster than you can roll back
3.5 — Rollback: what rolls back with the code (schema, config, data), and the compatibility window that makes it possible
3.6 — Dependency and schema compatibility: the version you can run beside, and the one you cannot
3.7 — Incident command for a bad change: the decision to roll back or fix forward under time pressure
3.8 — Postmortems that change something: the wrong hypotheses, the violated invariant, the missing signal, and the change that outlives the incident
3.9 — Rolling updates and draining: SIGTERM, connection draining, readiness, and the requests a rolling restart loses

### Lab
Add validation and a staged rollout path for Mission HQ's config (models.yaml, agent manifests). Push a malformed config and show it stopped at the first stage. Push a bad-but-valid change and show the SLO burn-rate halting the ramp. Roll back. Then use the phase-1 sealed-injection script to start one incident you did not choose, run it end to end alone — timeline, hypotheses, fix — and write the postmortem before opening the seal.

### Demonstrate
A malformed config caught by validation, a bad change halted by a canary signal and rolled back, and one postmortem with a timeline, hypothesis tree, violated invariant, missing signal and prevention.

### Test out
- Explain: why config needs the same rollout discipline as code, with the two incidents as evidence.
- Predict: for a described change and rollout policy, at which stage it would be caught and how many machines it reaches first.
- Demonstrate: the staged rollout catching a bad push.

---

## Phase 4 — Service security boundaries
question: Where are the boundaries in your own service, which one would a stolen credential cross, and how would you know it happened?
minutes: 150
assumes: AI-side isolation and the rule of two (2.4), tenant filtering (2.2); per-request cost budgets and the reservation pattern (inference-internals 3B); token quotas per tenant (inference-internals 6A)
introduces: threat modelling for a service, authentication vs authorization, tenant isolation at the service layer, secrets and credential scope, input and output boundaries, SSRF and injection at the service edge, dependency and supply-chain risk, auditability, abuse and resource-consumption controls
leaves-for-later: security as a design-time boundary (7.2)

### Why you're here
Course 2 kept a hostile document from moving data across a tenant. This phase asks the same question one layer down: the API token in Mission HQ's frontend can start agents — what else can it do, and who else could hold it? A dependency update pulled in a package that sends data to a server you did not choose. A URL a user supplied was fetched from inside the network. None of these involve a model, and every one of them is the service's own boundary.

Security at the service layer is a map of boundaries and what crosses them. This phase draws Mission HQ's.

### Sections
4.1 — Threat modelling in an afternoon: assets, entry points, trust boundaries, and the attacker you are designing against
4.2 — Authentication versus authorization: proving who, deciding what — and the confused deputy at the service level
4.3 — Tenant isolation at the service layer: where the tenant ID must be checked, and the query that forgets it
4.4 — Secrets: scope, rotation, where they live, and what a leaked one can reach
4.5 — Boundaries for input and output: SSRF, injection, and the URL the service fetched on someone's behalf
4.6 — Supply chain: what a dependency can do, pinning, and the update that changed behaviour
4.7 — Auditability: the log that answers "who did what, when" and survives the incident
4.8 — Abuse and resource limits: the request that costs you more than the caller, at the service edge

### Lab
Draw Mission HQ's boundaries: browser, API token, agents, tools, vault, outbound network. For each, name what crosses and what stops it. Attack two of them (SSRF through a fetch tool, a scoped-credential escalation). Fix what fails. Add the audit trail that would have shown it.

### Demonstrate
A boundary map for Mission HQ, two attacks attempted with results, and an audit trail that records the attempts with who, what and when.

### Test out
- Explain: the difference between authentication and authorization, and where in a request each is checked.
- Predict: for a described service and a stolen credential, which boundary it crosses and what it can reach.
- Demonstrate: the boundary map and the two attacks.

---

## Integrated lab for the course

A game day on Mission HQ: inject a slow dependency and diagnose it from telemetry alone under a time limit; drive the system past capacity with naive retries and show it hold after the controls are in; push a malformed config and catch it in the staged rollout; attempt one boundary crossing and show the audit trail. Write the postmortem for the injected incident as if it were real.

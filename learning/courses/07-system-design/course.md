# Course 7 — System design and architecture
slug: elite-system-design
order: 7
source: local
language: design documents, with the critical mechanism implemented in Go on Mission HQ

## Why this course

Every earlier course teaches a mechanism. This one teaches choosing between
them under constraints you do not fully know, writing the choice down so
others can attack it, and changing it when the requirement changes — which is
the senior skill the career ladders describe: highest scope, most ambiguity,
simple interfaces over complex systems. It comes last because it uses
everything before it: the numbers from course 1, the guarantees from courses
4 and 5, the failure behaviour from course 6.

Three phases, not more, because the practice is in the designs, not in the
lessons. The inference-internals course already teaches capacity planning
from queueing arithmetic (6A), cost per request and the self-host arithmetic
(3A, 3B, 4B), SLO targets (5B), and the design document, decision records,
review questions and pre-mortem (6B). This course assumes those and spends
its time on requirements, boundaries, failure domains and revising a design.

The capstone runs through the whole path: two complete Mission HQ designs,
one of them with a requirement changed halfway.

## What you will be able to do

Turn a vague requirement into numbers and find the real constraint. Draw the
boundaries — data ownership, contracts, consistency, security — and defend
them. Design for failure domains and cost. Write a design document another
engineer can attack, defend it, and revise it in thirty minutes when a
requirement moves.

---

## Phase 1 — Requirements into numbers
question: Before drawing a single box, what are the five numbers that decide the design, and which one is the actual constraint?
minutes: 120
assumes: capacity envelopes (1.2); Little's law, Erlang C pooling, N+k redundancy, cold-start headroom, traffic shape and planning in work rather than requests (inference-internals 6A); cost per request by token class and dollars per correct answer (inference-internals 3A and 3B); the self-host arithmetic (inference-internals 4B); SLO targets, percentile ladders and why not 100% (inference-internals 5B)
introduces: workload shape of a general service, data volume and retention, read/write ratio, reference numbers for back-of-the-envelope arithmetic, cost per tenant and per month as a requirement, finding the binding constraint, getting requirements out of a stakeholder
leaves-for-later: boundaries (7.2), failure domains (7.3)

### Why you're here
The design review opened with a diagram of twelve services and a message bus. Nobody had asked how many requests per second, how much data, or what latency the user would notice. The system was designed for a scale it would never reach, cost four times what it needed to, and still missed the one constraint that mattered: a nightly job that had to finish in a window. The senior engineer in the room asked for the numbers first, and the design shrank to three services.

Design starts with arithmetic. This phase is the arithmetic, and the questions that get the inputs out of people who have not thought about them.

### Sections
1.1 — Getting the requirement: the questions that turn "we need a notification system" into a workload, and what to do when the answer is "we don't know"
1.2 — Workload shape for a general service: read/write ratio and payload sizes
1.3 — Data: volume, growth, retention, and what "we keep everything" costs at year three
1.4 — Back-of-the-envelope: the reference numbers for memory, disk, network and a database write
1.5 — Cost as a requirement: per tenant and per month, at current and 10× scale — and the design that is correct and unaffordable
1.6 — The binding constraint: finding the one number the design must be built around, and saying so in the first paragraph

### Lab
Take one real Mission HQ requirement (multi-region webhook delivery, or an agent platform with approvals for many users). Extract the numbers. Estimate capacity and cost. Name the binding constraint in one sentence. Do it in one page.

### Demonstrate
A one-page requirements sheet with every number sourced or estimated with its method, the binding constraint named, and a cost estimate at current and 10× scale.

### Test out
- Explain: the reference numbers for back-of-the-envelope estimation, and how a retention choice changes the cost at year three.
- Predict: for a described product, which of the five numbers will be the binding constraint and why.
- Demonstrate: the requirements sheet.

---

## Phase 2 — Boundaries and contracts
question: Which service owns this data, who is allowed to change it, and what happens to every other service when the shape of it changes?
minutes: 180
assumes: requirements sheet (7.1), delivery guarantees and the outbox (5.2), consistency models (5.1), service security boundaries (6.4); the self-host decision as one build-versus-buy case, and a shared pool versus one fleet per tenant (inference-internals 4B and 6A)
introduces: service and data ownership, synchronous vs asynchronous communication, API and event contracts, compatibility and versioning of contracts, consistency boundaries, security and tenant boundaries at design time, modular monolith vs services (and build vs buy by the same test), reading an unfamiliar codebase before redesigning it
leaves-for-later: failure domains (7.3)

### Why you're here
Two services both write to the same table because "it was faster". A field changed meaning, one of them was not updated, and the bug took a month to find because neither team thought they owned the data. Meanwhile a third team split a monolith into nine services for "scalability" and now spends most of its time on distributed transactions between them. Boundaries were drawn by org chart and by fashion, not by data ownership and failure isolation.

A boundary is a promise about who owns what and what crosses. This phase draws them from the data, not the diagram.

### Sections
2.1 — Data ownership: one writer per fact, and the design smell of shared tables
2.2 — Sync versus async: request/response, events, and choosing by what happens when the other side is down
2.3 — Contracts: APIs and events as promises, schema evolution, and the compatibility window from course 4 applied across services
2.4 — Consistency boundaries: where a transaction ends and an eventual guarantee begins, with the outbox at the seam
2.5 — Security and tenant boundaries drawn at design time: where the tenant ID lives and where the credential stops
2.6 — Modular monolith versus services: the actual reasons to split (failure isolation, independent deploy, team ownership), the costs, and the same test applied to build-versus-buy — with Mission HQ as the worked example
2.7 — Reading an unfamiliar system before changing it: request to storage and back, the hidden coupling, and the write-up

### Lab
Draw Mission HQ's boundaries as they are: who owns tasks, runs, events, the vault, the outbox. Find one place two components write the same fact. Propose the boundary change — including whether to extract a typed workflow-stage contract from the engine while staying a modular monolith — with the contract and its versioning.

### Demonstrate
A boundary map of Mission HQ with one ownership violation found and a contract designed to fix it — then the contract change run against a live agent mid-run, showing it does not break.

### Test out
- Explain: the real reasons to split a service and the costs each split adds.
- Predict: for a described change to a shared schema, which consumers break and in what order.
- Demonstrate: the boundary map and the contract.

---

## Phase 3 — Failure domains and the design document
question: When one region, one tenant, or one dependency fails, how much of the system goes with it — and can you defend that number in a review?
minutes: 180
assumes: failure that spreads (6.2), safe change (6.3), boundaries (7.2); fallback versus failover and the fallback that must run continuously (inference-internals 5B); the design document, decision records, non-goals, alternatives with their trade-offs, reviewer questions, the pre-mortem, and a number with a source for every claim (inference-internals 6B)
introduces: blast radius, failure domains, dependency failure analysis, regional and tenant isolation, cells and shuffle sharding, deployment and migration plans, observability as a design requirement, revising a design under a changed requirement, removing components as a design skill
leaves-for-later: nothing — this is the end of the path

### Why you're here
The design was elegant and every reviewer approved it. In production, one tenant's traffic spike took down every tenant, because nothing in the design bounded blast radius; one dependency's outage took the whole product down, because the degraded mode had never been designed. And when the largest customer asked for a change six months later, nobody could say which parts of the design still held, because the alternatives that were rejected — and why — were never written down.

A design is an argument. This phase writes it so it can be attacked, and revises it when the world changes.

### Sections
3.1 — Blast radius: the question to ask of every component — if this fails, what else does
3.2 — Failure domains: regions, zones, tenants, dependencies — and designing so a failure stays inside one
3.3 — Cells and shuffle sharding: bounding the damage a single tenant or request can do
3.4 — Dependency failure analysis: listing each dependency and the degraded mode it gets, decided before it is needed
3.5 — Migration and rollout as part of the design: how the system gets from today to the design, safely
3.6 — Observability as a requirement: the failure questions from course 6, written into the design
3.7 — Revising under a changed requirement: finding which parts of the design still hold, and what breaks, in thirty minutes
3.8 — Taking a component out: the cost of each moving part, and the design defended by what it does not contain

### Lab
Write the design document for one of the two capstone systems (multi-region webhook delivery with delivery guarantees, or an agent platform with approvals for many users): numbers, boundaries, failure domains, cost, migration, observability, alternatives. Before writing, seal a list of ten plausible requirement changes in a file. At minute zero of the review, draw one at random; re-plan in thirty minutes against it. Record the review. Then implement the highest-risk mechanism on Mission HQ and test it with the course-5 and course-6 tools.

### Demonstrate
A complete design document, a recorded review with a live requirement change and the revised design, and the critical mechanism implemented and tested — with the trade-offs defended in numbers.

### Test out
- Explain: blast radius, failure domains, and how cells bound them, with the trade-off each adds.
- Predict: for a described design, which single failure takes down the most, and which change reduces it most cheaply.
- Demonstrate: the design document and the live revision.

---

## Capstone — runs through the whole path

Two complete Mission HQ designs, built as the earlier courses supply the tools:

1. **Multi-region webhook delivery** with stated delivery guarantees, a lag probe, fencing on the workers, retry budgets, staged rollout and a cost model.
2. **An agent platform with approvals for many tenants**, with the eval gate, the crash matrix, tenant isolation across retrieval and memory, and a canary with rollback.

For one of them, a major requirement changes halfway — drawn at random from a list sealed before the design started. Revise it, implement the critical mechanism, and defend the resulting trade-offs. The final test is reproducibility: another engineer should be able to operate the system, reproduce the measurements, name its guarantees, and challenge the trade-offs from the artefacts alone.

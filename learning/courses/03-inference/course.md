# Course 3 — Inference and AI platform systems
slug: elite-inference
order: 3
source: platform
platform-course: inference-internals

## Why this course

Course 2 builds on top of a model. This course is the machine underneath and
the operation around it: what a request costs, where the time goes, how a
serving engine batches and caches, how a context budget is kept, what a
client must do to survive rate limits and timeouts, how a model call is
measured and promised, how a fleet is sized and shared, and how a quality
incident and a design review are run. Without it, "the model is slow" and
"the bill doubled" have no mechanism behind them, and routing and caching
decisions are guesses.

The material exists as the `inference-internals` course on the study
platform: eleven phases, all written. It is the first module of the
applied-AI path, and it is read first. Courses 1, 2, 6 and 7 name the
platform phase they assume, in the form `(inference-internals 5A)`, and do
not teach that material again.

It is taught through the same enhancement pipeline as any platform course:
hunter reads the phase and researches past it, tutor writes the version to
read instead, with the production failure and the corrections. The course's
own review found commands that did not run, benchmark numbers that did not
reproduce, and stale links — every taught phase must verify what it repeats.

## Which phases, and the ledger

The platform course has eleven phases: 0, 1, 2, 3A, 3B, 4A, 4B, 5A, 5B, 6A
and 6B. They map to six learning units; an A/B pair is one unit. All six
units are written and all six are required. Phases 4A and 4B were once an
optional extension; they are required now because courses 1 and 2 use their
benchmarking method and their evaluation gate.

Each unit carries the same ledger as a local phase, so the cross-references
from other courses can be checked. Other courses cite the platform phase
number, not the unit number.

**Unit 1 — Request lifecycle** · platform phases 0 and 1 · required
assumes: nothing beyond having called a model API
introduces: token, prefill vs decode, KV cache, sampling and the temperature-0 myth, reasoning tokens, streaming, TTFT and TPOT, finish_reason, per-token cost
leaves-for-later: batching and scheduling (unit 2), provider caching economics (unit 3)

**Unit 2 — Engine internals** · platform phase 2 · required
assumes: prefill vs decode and the KV cache (unit 1)
introduces: continuous batching, paged attention and preemption, prefix caching and the radix tree, chunked prefill and the stream freeze, constrained decoding and its quality cost, the context budget, the compaction trigger and backstop
leaves-for-later: GPU serving and flags (unit 4)

**Unit 3 — Economics, caching and routing** · platform phases 3A and 3B · required
assumes: token classes and per-token cost (unit 1), prefix caching inside the server (unit 2)
introduces: token classes and billing multipliers, implicit and explicit prompt caching, cache break-even, routers and cascades against a random control group, escalation signals, gating a model swap, batch APIs, per-request cost alerting, the reservation pattern, degrading on budget
leaves-for-later: the statistics of an evaluation gate (unit 4), quality SLOs (unit 5)

**Unit 4 — GPU serving, benchmarking and optimisation** · platform phases 4A and 4B · required
assumes: engine internals (unit 2), cost per token (unit 3)
introduces: GPU rental costs, engine flags and failure messages, fair benchmarking with one client and pinned flags, the throughput-and-latency sweep, quantization and its evaluation gate with a paired bootstrap interval, speculative decoding and when it turns into a loss, the self-host decision
leaves-for-later: fleet size and redundancy (unit 6)

**Unit 5 — Client reliability and observability** · platform phases 5A and 5B · required
assumes: TTFT and queueing (units 1 and 2), cost records (unit 3)
introduces: timeouts by kind, rate-limit semantics, retry amplification across layers, retry budgets and full jitter, a TTFT-based circuit breaker, SLO indicators including quality, error budgets and multi-window burn-rate alerts, the run record and its OpenTelemetry names, attribution axes, the noise floor, fallback vs failover
leaves-for-later: server-side admission control, bulkheads and metastable failure for a general service (6.2)

**Unit 6 — Capacity, tenants, incidents and design review** · platform phases 6A and 6B · required
assumes: measured throughput and the self-host arithmetic (unit 4), rate limits and the run record (unit 5)
introduces: capacity from queueing arithmetic (Little's law, the knee, Erlang C pooling), N+k redundancy, cold-start headroom, autoscaling on the queue, token quotas and token-fair admission, the prefix-cache side channel, quality incidents triaged by slice, rollback to a known-good baseline, the design document and decision record, reviewer questions, the pre-mortem
leaves-for-later: admission control for a general service (6.2), revising a design under a changed requirement (7.3)

## Boundary with course 2

Course 3 owns: prefill and decode, KV-cache behaviour, batching and
scheduling, the context budget and compaction, constrained decoding,
provider caching, cost per request and cost budgets, routing economics and
the control group, the statistics of a gate, inference timeouts, rate limits
and retries, quality SLOs, the run record, fallbacks, GPU serving,
quantization, capacity, multi-tenant fairness, quality incidents, and the
design review.

Course 2 owns: judges and datasets, retrieval, agents and tools, security,
and changing an agent system safely.

The connection, in order: product requirement → evaluation contract (2.1) →
retrieval (2.2) → agent and tool runtime (2.3) → model request → inference
engine (platform phases 1 and 2) → cost, client behaviour and the run record
(platform phases 3A to 5B) → production feedback (2.5).

## Integrated lab for the course

Build a cost-per-successful-task dashboard for Mission HQ from its run
records. Cut the cost by 40% through prompt caching or routing while the
course-2 regression suite holds its pass rate within the confidence interval.
Set a p95 latency target for one interactive path and hit it with the
guardrail still inline.

## Test out

The platform phases carry their own checkpoints. Skipping a unit requires the
same three gates as every other course: explain the mechanism (for instance,
why prefill and decode have different bottlenecks), predict an unfamiliar
case (the cost change when a 4k-token system prompt becomes cacheable), and
demonstrate it (a measured before/after on Mission HQ's run records).

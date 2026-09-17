# Course 1 — Performance, concurrency and the machine
slug: elite-performance
order: 1
source: local
language: Go

## Why this course

Every later course measures something: a saturation point, a lost write, a
p99 under a retry storm, the cost of a model change. If the measurement is
wrong, the lesson drawn from it is wrong, and most measurements engineers
make are wrong in the same few ways — closed-loop load generators, averages,
warm caches, one run. This course installs the habit the rest of the path
depends on: **write the prediction down, then measure honestly, then explain
the gap.** It also goes one layer under the service, because the latency you
cannot explain is usually in the machine: a connection pool, a DNS cache, a
page-cache miss, a goroutine that never exited.

The inference-internals course already teaches the queueing arithmetic
(Little's law, the knee, pooling, in its phase 6A), timeouts by kind (5A),
and fair benchmark comparison with a paired interval (4A, 4B). This course
assumes those and applies them to a Go service; it does not teach them again.

## What you will be able to do

Predict a service's p50 and p99 at 50%, 80% and 95% utilisation before
loading it, measure them with an open-loop generator, find the bottleneck
with a profiler, fix it, and prove the fix did not leak goroutines or break
cancellation. Trace one request from the client to the database and account
for every millisecond.

---

## Phase 1 — Measurement before optimisation
question: Why do most benchmarks report a number that production will never show, and how do you write one that does not?
minutes: 90
assumes: writing a Go service and reading a histogram; waiting time versus service time, and the stall a mean hides (inference-internals 1, 2 and 6A); percentile ladders (inference-internals 5B); one client against pinned configurations (inference-internals 4A); paired bootstrap interval and the noise floor of a small sample (inference-internals 4B)
introduces: latency distribution of a service, open-loop vs closed-loop load, coordinated omission, warm-up, baseline, controlled change, run-to-run variance
leaves-for-later: fan-out, pools and backpressure (1.2), profiling (1.3)

### Why you're here
A load test says the service handles 2,000 requests per second at 40 ms p99. Production sees 800 requests per second and a p99 of 900 ms, and nobody can explain why the test was wrong. It was not wrong — it measured a different thing. The generator waited for each response before sending the next request, so when the service slowed, the generator slowed with it and the slow seconds were never recorded. The number was real and useless.

Before any optimisation, you need a measurement you can defend: what was sent, how, against what baseline, with what variance. This phase is that discipline.

### Sections
1.1 — The distribution of one Go endpoint: reading its p50, p99 and max from an HDR-style histogram
1.2 — Open-loop versus closed-loop load: how a closed-loop generator hides slowness, with the arithmetic of coordinated omission
1.3 — Warm-up, caches and the first minute: why run one is not a result
1.4 — Baseline, one change, repeat: run-to-run variance of a latency distribution
1.5 — The prediction sheet: the one-page format used for every lab on this path

### Lab
Pick one Mission HQ request path (a task dispatch through the API). Write the prediction sheet: expected p50 and p99 at a stated load, and why. Build an open-loop load generator in Go with HDR-style histograms. Run three times. Report the distribution, the variance, and the gap between prediction and measurement.

### Demonstrate
The same service measured with a closed-loop and an open-loop generator, with the numbers side by side, and one paragraph explaining exactly which seconds the closed-loop run failed to record.

### Test out
- Explain: coordinated omission, without notes, with the arithmetic for a generator at 100 requests per second hitting a 5-second stall.
- Predict: given a histogram and a run-to-run variance, whether a 12% improvement is real.
- Demonstrate: a prediction sheet and an open-loop measurement for one endpoint, three runs, with the variance reported.

---

## Phase 2 — Queueing, saturation and tail latency
question: The CPU is at 60% and p99 is already bad. Which resource is saturating — a fan-out, a shared connection, a pool — and where is the knee for your service?
minutes: 120
assumes: latency distributions (1.1), open-loop load (1.1), prediction sheet (1.1); Little's law, the 1 / (1 − ρ) knee, service-time variance and pooling (inference-internals 6A); the throughput-and-latency sweep and the operating point (inference-internals 4A)
introduces: fan-out amplification, head-of-line blocking on a shared connection, connection-pool exhaustion, backpressure, capacity envelope of a service
leaves-for-later: load shedding and admission control for a service (6.2)

### Why you're here
The service ran fine at 60% CPU for months. A marketing email pushed it to 85% and p99 went from 60 ms to 4 seconds, while the average rose from 20 ms to 45 ms. The dashboard, which shows averages, looked healthy. Adding servers fixed it, and nobody learned why — so it happened again the next quarter, this time in the database connection pool instead of the CPU.

You already have the formula for the knee. In a Go service the resource that reaches it first is often not the one you planned for. This phase finds it before the email goes out.

### Sections
2.1 — Fan-out amplification: 100 calls at 1% slow each, and the probability the whole request is slow (the tail-at-scale arithmetic)
2.2 — Head-of-line blocking: one slow request in a queue, or on a shared connection
2.3 — Pools that fill: connection pools, worker pools, goroutine budgets — how exhaustion looks in metrics before it looks like an outage
2.4 — Backpressure: what a system does when the producer is faster than the consumer — buffer, block, or refuse — and who pays in each case (the mechanics of refusing well are 6.2)
2.5 — The capacity envelope of a service with several resources: which one bends first, and reading headroom from the graph

### Lab
Predict Mission HQ's saturation point from its worker count, mean service time and arrival pattern. Load it open-loop past the knee. Plot latency against utilisation. Find the resource that saturated first — it is rarely the one you expected.

### Demonstrate
A predicted knee and a measured knee for one service, with the difference explained, and one pool-exhaustion incident reproduced on purpose and shown in the metrics before it shows in errors.

### Test out
- Explain: why a request that fans out is slow far more often than any one of its calls, and why a full pool shows in metrics before it shows in errors.
- Predict: for a request that fans out to 100 backends each slow 1% of the time, the fraction of slow requests, and the change when the fan-out is halved.
- Demonstrate: a load curve from your own generator showing the knee, with the saturated resource named.

---

## Phase 3 — Profiling Go systems
question: When the service is slow, how do you find the line of code responsible in under an hour, and prove the fix helped?
minutes: 150
assumes: honest measurement (1.1), capacity envelope (1.2)
introduces: CPU vs wall-clock profile, allocation profile, heap retention, GC pressure, goroutine profile, block and mutex profiles, execution trace, symptom vs cause
leaves-for-later: concurrency correctness (1.4), the syscall layer (1.5)

### Why you're here
A handler takes 400 ms and the profiler shows 90% of CPU in JSON encoding. You optimise the encoder, ship it, and the handler still takes 380 ms — because the time was never CPU, it was waiting on a lock, and CPU profiles do not see waiting. A week later the fix is reverted.

Profiling is not one tool. It is five views of the same program, and each one is blind to what the others see. This phase is knowing which view answers which question.

### Sections
3.1 — The five profiles and what each is blind to: CPU, allocations, goroutines, block, mutex
3.2 — Wall-clock versus CPU time: why the slow handler is usually invisible in the CPU profile
3.3 — Allocations and the garbage collector: allocation rate, heap retention, GC pauses, and how to read GC pressure from runtime metrics
3.4 — Lock contention and the mutex profile: finding the lock that serialises your fan-out
3.5 — The execution trace: reading scheduler behaviour, goroutine wake-ups and network waits on a timeline
3.6 — Symptom versus root cause: the discipline of a hypothesis list and one measurement per hypothesis
3.7 — Proving a fix: the before/after measurement that survives a code review

### Lab
Profile one Mission HQ path under load from phase 2. Form three hypotheses. Test each with the profile that can see it. Fix the real bottleneck. Show the before/after distribution, not the before/after average.

### Demonstrate
One real bottleneck in Mission HQ, found with the correct profile, fixed, with a measured improvement in p99 at fixed throughput and no regression in errors or allocations.

### Test out
- Explain: which profile sees lock waiting, which sees GC pressure, and why a CPU profile cannot see either.
- Predict: from a description of a symptom (high p99, low CPU, rising goroutine count) which profile to open first and what it will show.
- Demonstrate: a profiled, fixed, re-measured bottleneck with the profiles attached.

---

## Phase 4 — Concurrency correctness
question: How does a program that passes every test still corrupt state or leak a goroutine per request in production?
minutes: 180
assumes: profiling (1.3), goroutine profile (1.3)
introduces: the Go memory model, happens-before, data race vs logical race, ownership of shared state, cancellation and deadline propagation, bounded concurrency, goroutine leak, deterministic concurrency test, property-based test
leaves-for-later: distributed delivery guarantees (5.2), idempotency across processes (5.2)

### Why you're here
The race detector is clean. The tests pass. In production, a counter is wrong by a few per day, and the goroutine count climbs by one every time a client disconnects mid-request. Six weeks later the service is restarted every night "for memory". Both bugs are the same kind: something about the order of events was assumed and never stated.

Concurrency bugs are not found by running the code more. They are found by stating what must be true about ordering and ownership, then writing the test that would break if it were false.

### Sections
4.1 — The Go memory model in one page: happens-before, and why "it worked on my machine" is a statement about timing
4.2 — Data races versus logical races: what the race detector catches, and the whole class it cannot
4.3 — Ownership: the rule that decides whether state needs a mutex, a channel, or neither — and how to write it down
4.4 — Mutexes, atomics and channels: which one for which shape of problem, with the failure mode of choosing wrong
4.5 — Cancellation and deadlines: how a context travels through a call chain, and every place it gets dropped
4.6 — Bounded concurrency: worker pools, semaphores, and why unbounded fan-out is a self-inflicted overload
4.7 — Goroutine leaks: the four patterns that cause them and how each looks in the goroutine profile
4.8 — Deterministic and property-based concurrency tests: making the interleaving explicit so the test fails the same way every time, and generating the interleavings you did not think of

### Lab
Audit one concurrent path in Mission HQ (the task worker or the SSE fan-out). Write down its ownership rules. Find or inject one logical race. Write the deterministic test that catches it. Prove cancellation releases every goroutine.

### Demonstrate
A test that fails deterministically on the race and passes on the fix, plus a goroutine-count measurement across 10,000 cancelled requests that returns to baseline.

### Test out
- Explain: happens-before, and the difference between a data race and a logical race, with an example of each.
- Predict: given a snippet with a context and a goroutine, where the leak is and what the goroutine profile will show after 1,000 cancellations.
- Demonstrate: the deterministic test and the leak-free cancellation measurement.

---

## Phase 5 — The machine beneath an API request
question: Where do the 40 milliseconds go between a client sending a request and the first byte of the response, and which of them are yours?
minutes: 150
assumes: latency distributions (1.1), connection pools (1.2), cancellation (1.4); timeouts by kind — connect, stall, total (inference-internals 5A)
introduces: DNS resolution and caching, TCP handshake and slow start, TLS handshake and session resumption, HTTP/1.1 vs HTTP/2 multiplexing, gRPC flow control, connection reuse, syscalls and buffers, the page cache, fsync cost, cgroup CPU quota and throttling, memory limits and the OOM kill
leaves-for-later: what fsync promises about durability (4.1), overload control across services (6.2)

### Why you're here
The service reports 8 ms per request. The client measures 45 ms. The 37 ms in between are not in any dashboard you own: a DNS lookup that stopped being cached, a TLS handshake because a pool was too small, a TCP connection that started cold, a read that touched disk instead of the page cache. One of the largest outages of 2025 started in this layer — a race in DNS automation that emptied a record — and it was invisible to the teams' application metrics until it was too late.

You cannot fix latency you cannot see. This phase makes the layer under your service visible.

### Sections
5.1 — DNS: resolution, caching, TTLs, and the failure modes when a record disappears or a cache goes stale
5.2 — TCP: the handshake, slow start, keep-alive, and why the first request on a connection is always slow
5.3 — TLS: the handshake cost, session resumption, and what a too-small pool does to your CPU
5.4 — HTTP/1.1 versus HTTP/2 versus gRPC: connections, streams, multiplexing, and where head-of-line blocking moves to
5.5 — Connection pools done right: sizing from Little's law, idle timeouts, and the metrics that show a pool is the bottleneck
5.6 — Syscalls, buffers and the page cache: what a read costs when it hits memory versus disk, and how fsync changes the picture
5.7 — Deadlines through the stack: how a Go context deadline becomes a socket deadline, and where it gets lost
5.8 — The container's limits: cgroup CPU quota and throttling, memory limits and the OOM kill, and why a p99 spike every 100 ms is a quota, not your code

### Lab
Trace one Mission HQ request end to end with timestamps at each layer: DNS, connect, TLS, first byte, storage, response. Account for the total. Then break one layer on purpose — shrink the pool, drop the DNS cache — and watch which metric moves first.

### Demonstrate
A per-layer latency breakdown of one real request that sums to the measured total, and one induced failure in the machine layer diagnosed from metrics alone.

### Test out
- Explain: what happens on the wire for a cold HTTPS request, in order, with the round trips counted.
- Predict: the latency change when a pool of 10 connections serves 200 concurrent requests with a 20 ms service time.
- Demonstrate: the per-layer breakdown and the induced-failure diagnosis.

---

## Integrated lab for the course

Predict Mission HQ's saturation point. Load it open-loop past the knee. Profile the bottleneck. Fix it. Show the p99 improvement at fixed throughput with no rise in errors, then prove cancellation under load leaks nothing. Write it up as a two-page performance note: prediction, method, measurement, fix, what is still unexplained.

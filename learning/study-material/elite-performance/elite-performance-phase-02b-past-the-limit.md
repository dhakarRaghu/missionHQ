# Phase 2B — Queueing, saturation and tail latency: past the limit

**The question this phase answers:** the CPU is at 60% and p99 is already bad. Which resource is saturating, and where is the knee for your service?

Part A showed where the time goes inside one request: a fan-out, a blocked event loop, a pool that fills. Part A is a prerequisite. This part uses its API, its load generator and its measurements without explaining them again.

This part asks what happens past the limit, and how to read the limit for a whole service. It teaches the last two ideas of Phase 2:

4. **Work beyond capacity goes to one of three places.** A buffer adds latency and memory, a blocked caller waits, a refused client gets an error. A queue that adds work as it grows can keep a service down after its trigger is gone. Retries do that, and so does a pool that walks its queue.
5. **A service's capacity is at most the smallest of its resources' limits.** A queue that costs work can push it into a bad state below every computed limit. So the knee is found by loading the service there, and headroom is read per resource.

It also keeps a promise from Phase 1. Section 1.5 predicted with one queue whose cost per request is fixed, and said this phase would measure what that model leaves out. Section 2.4 measures two things that add work as a queue grows.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, the previous document: where the time goes                       │
│  2.1  Fan-out amplification                                              │
│  2.2  Head-of-line blocking                                              │
│  2.3  Pools that fill                                                    │
│                                                                          │
│ PART B, this document: past the limit                                    │
│  2.4  Backpressure                  — where the extra work goes          │
│  2.5  The capacity envelope         — headroom, read per resource        │
│  Lab: E7 to E12                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**What this part assumes.** Part A of this phase, and from Phase 1 the validity rule and the prediction sheet. From the inference-internals course, briefly:

- **inference-internals 6.1, Little's law and the knee.** Little's law, L = λW, links the requests in a system, their arrival rate, and the time each one spends there. Here ρ is the share of time a server is busy. For one server, the mean wait in the queue is ρ / (1 − ρ) service times: 4 at 80% busy, 19 at 95%. Capacity planning in that section sizes replicas from these numbers, and section 2.5 here reads them per resource.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. The conditions are those of part A: an Apple M2 with 8 GB, macOS 15.7.8 and CPython 3.13.3 through uv, on 2026-09-25. Other programs kept the load average near 6. Every log begins with its conditions. Section 2.4 uses two offline models, and says so where it does.

Time for part B: 1.5 to 2 hours. About 10 minutes of that is waiting for load runs.

---
## 2.4 — Backpressure (when the producer is faster than the consumer, where the extra work goes)

Why this matters: every overload ends in one of three places. The extra work waits in a buffer, the caller is made to wait, or someone is told no. If you do not choose, a library default decides, and in Python the default is usually an unbounded buffer. Worse, some ways of waiting make the service slower, so the overload lasts after its cause is gone.

**Answer this first.** A producer makes 120 items per second. One consumer handles 100 per second. After one minute: how many items are waiting, how old is the oldest one, and how many were finished? Now make the queue hold at most 50 items. What changes if a full queue blocks the producer, and what changes if it refuses the item?

**The mechanism: 20 extra items per second must go somewhere.** The consumer finishes 100 per second whatever you do. The policy only decides who holds the other 20.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 120 items/s into a consumer of 100/s: where the extra 20/s goes          │
├───────────────┬──────────────────────────┬───────────────────────────────┤
│ policy        │ what grows               │ who pays                      │
├───────────────┼──────────────────────────┼───────────────────────────────┤
│ buffer        │ the queue, 20 per second │ every item: latency, and the  │
│               │                          │ process: memory               │
├───────────────┼──────────────────────────┼───────────────────────────────┤
│ block         │ nothing inside, if the   │ the caller. If its callers    │
│               │ caller can slow down     │ cannot slow, they queue       │
├───────────────┼──────────────────────────┼───────────────────────────────┤
│ refuse        │ nothing                  │ the refused client, at once   │
└───────────────┴──────────────────────────┴───────────────────────────────┘
```

`backpressure.py` runs all of them for 60 s, with a bounded queue of 50 for the last three. "block-open" is a blocking producer whose own callers keep arriving, as web requests do. "block-closed" is a producer that makes its next item only after the last one was accepted, as a batch job reading a file does.

```bash
uv run python phase02_queueing/backpressure.py
```

```
producer 120/s, consumer 100/s, 60 s, bounded queue 50
  buffer       done  100.0/s  refused   0.0%  p50   6.261 s  p99  12.015 s  most held   1214
  block-open   done  100.0/s  refused   0.0%  p50   6.261 s  p99  12.015 s  most held   1214
  block-closed done  100.0/s  refused   0.0%  p50   0.491 s  p99   0.500 s  most held     50
  refuse       done  100.0/s  refused  16.1%  p50   0.481 s  p99   0.500 s  most held     50
```

Four readings. The "pays" column of the script's output is cut here for width:

1. **Every policy finishes 100.0 per second.** No policy creates capacity.
2. **The buffer ended with 1,214 items, p99 12.0 s.** That is 20 extra items per second for 60 s, each waiting behind about 1,200 others at 10 ms each.
3. **Blocking helps only a producer that can slow down.** "block-open" is modelled as the buffer with the queue moved into the callers, so its numbers equal the buffer's by definition: 12 s. With a producer that slows down, nothing grows. But its queue is always full, and a full queue of 50 adds 50 × 10 ms = 0.5 s to every item. A bounded queue that is always full is pure latency, so keep it small.
4. **Refusing sheds 16.1% and keeps the p99 at 0.5 s.** The share is close to 1 − 100/120 = 16.7%. The refused clients must now retry or give up.

**The same three choices in Python code.** Each of these is a default you have now, whether you chose it or not:

| Policy | In Python, with its default | What the caller sees |
|---|---|---|
| buffer | `asyncio.Queue()` has `maxsize=0`, no limit. `transport.write()` without `await drain()` also buffers without limit | nothing, until memory or latency runs out |
| block | `await queue.put()` with `maxsize > 0`. `await writer.drain()` waits above a 64 KiB write buffer. An httpx pool waits, and its 5 s pool timeout restarts on every wait, as section 2.3 measured | a slower `await` |
| refuse | `queue.put_nowait()` raises `QueueFull`. uvicorn `--limit-concurrency N` answers HTTP 503 at once, with no `Retry-After` | an error, fast |
| hidden refuse | a full kernel accept queue. Linux drops the connection attempt, and the client retries after about 1 s, inferred from the kernel source, not measured | a slow connect, not an error |

The kernel row needs one number. uvicorn asks for a listen backlog of 2,048. macOS caps any backlog at `kern.ipc.somaxconn`, which is 128 on this Mac. XNU then admits up to 1.5 times the cap before it refuses, counting half-open connections too. Both are inferred from the XNU source and `sysctl`, not measured with a socket test. On Linux since 5.4 the default of `net.core.somaxconn` is 4,096.

**A queue that feeds itself.** Phase 1 promised this section. Section 1.5 predicted with one queue whose cost per request is fixed. Two things break that assumption in real services. Both add work as the queue grows, so an overload lasts after its cause is gone.

The first is retries with wasted work. A client that times out usually sends the request again. The server does not know the first copy's client has left, so it still serves it, for nobody. `retry_storm.py` models one server that finishes 100 requests per second, 70 users per second, a client timeout of 1 s and up to 3 retries. At t = 20 s the server stops for 2 s, the trigger:

```bash
uv run python phase02_queueing/retry_storm.py
```

```
                t=15s            t=21s            t=25s            t=30s            t=55s
  no retries     87/75  q12      0/70  q78     58/60  q74     84/85  q5      71/74  q0       last 10 s goodput  68.6/s
  retries        87/75  q12      0/149 q78      0/262 q712     0/284 q1568    0/272 q6013    last 10 s goodput   0.0/s
  retries+drop   87/75  q12      0/149 q78     61/126 q137    87/85  q5      72/74  q0       last 10 s goodput  68.7/s
  cells: goodput / attempts sent in that second, and the line length q
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Users answered per second, in 5 s buckets. Stall from t = 20 to 22 s     │
├──────────────────────────────────────────────────────────────────────────┤
│               0       10      20      30      40      50    t in s       │
│ no retries    ████████████████····████████████████████████████           │
│ retries       ████████████████································           │
│ retries+drop  ████████████████▓▓▓▓████████████████████████████           │
│                                                                          │
│ █ 55 or more per second   ▓ 25 to 55   ░ 5 to 25   · under 5             │
└──────────────────────────────────────────────────────────────────────────┘
```

Goodput is the number of users per second who got an answer before their timeout. Without retries the stall's backlog drains, and by t = 30 s the line is 5 long. With retries, the stall ended at t = 22 s, and 33 seconds later nobody is being answered. The line holds 6,013 requests, almost all of them copies whose clients have left. The server is busy all the time, serving answers nobody reads.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The loop that keeps it down after the trigger is gone                    │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   line grows ──► waits pass the 1 s timeout ──► clients give up          │
│      ▲                                              │                    │
│      │                                              ▼                    │
│   server spends its time on       ◄──────  clients send the request      │
│   copies nobody waits for                  again, up to 3 more times     │
│                                                                          │
│ Break the loop: drop a request whose client has left, before serving it  │
└──────────────────────────────────────────────────────────────────────────┘
```

The third row changes one thing. When a request reaches the front of the line, the server checks whether its client is still waiting, and drops it if not. The wasted work goes, and the system recovers to 68.7 users per second.

This is a metastable failure. Bronson et al., HotOS 2021, give the definition. In such a failure, "a trigger causes the system to enter a bad state that persists even when the trigger is removed". The **sustaining effect** is the mechanism that keeps it there once the trigger is gone. Here it is the retries plus the wasted work. Huang et al., OSDI 2022, studied 22 metastable failures from 11 organisations. The retry policy was the sustaining effect in more than half.

Huang et al. also give a safe load, their Theorem 2. A system cannot enter such a state if its load stays below its capacity divided by two factors. One is how much its work can be multiplied. The other is how much its capacity can shrink. Three retries can multiply each request by 4. With no loss of capacity, the safe load here is 100 / 4 = 25 per second. A queue that costs CPU, the second mechanism below, makes the second factor above 1, and the safe load lower still.

The model agrees with that bound. `--sweep-rates` runs the same 2 s stall at other loads, five seeds each. A run "stayed down" if its goodput over the last 10 s was below half the arrival rate:

```bash
uv run python phase02_queueing/retry_storm.py --sweep-rates 30 35 40 50 70 --seeds 5
```

```
retries 3, stall 2 s; 'stayed down' = last 10 s goodput below half the arrival rate
     30 users/s: 0 of 5 seeds stayed down
     35 users/s: 2 of 5 seeds stayed down
     40 users/s: 5 of 5 seeds stayed down
     50 users/s: 5 of 5 seeds stayed down
     70 users/s: 5 of 5 seeds stayed down
```

At 35% the same trigger pushes the system into the bad state in some runs and not in others. That is what "vulnerable" means in Bronson's paper: the state is fine until a trigger of the right size arrives.

The second is a queue that costs CPU. Phase 1's model charged each request a fixed service time. The httpx pool does not. Every time a request joins the pool or a connection is released, httpcore 1.0.9 runs `_assign_requests_to_connections`. It walks the whole list of waiting requests, and for each one checks every connection. The loop is at lines 302 to 323 of `httpcore/_async/connection_pool.py`. And as section 2.3 showed, one released connection wakes every waiting request, and all but one go back to waiting.

`pool_cost.py` measures the arrival side of that cost. It fills 5 connections with requests that hold them, then adds N more requests and measures the CPU the client spent accepting them:

```bash
uv run python phase02_queueing/pool_cost.py --queued 50 100 200 400 800
```

```
50 requests queued behind 5 busy connections: CPU     24.1 ms,    481.9 µs per request
  100 requests queued behind 5 busy connections: CPU     64.6 ms,    646.3 µs per request
  200 requests queued behind 5 busy connections: CPU    172.4 ms,    862.2 µs per request
  400 requests queued behind 5 busy connections: CPU    577.1 ms,   1442.6 µs per request
  800 requests queued behind 5 busy connections: CPU   2050.4 ms,   2563.0 µs per request
```

The average CPU per request grew 5.3 times as the queue grew from 50 to 800. Across the saved runs the growth was 4.8 to 5.4 times, and the absolute numbers moved by up to 50% with the machine's load. The slope is about (2,563 − 482) / (800 − 50) = 2.8 µs of extra CPU per arriving request for every request already waiting. This measures arrivals only. The wake of every waiter on each release is not in it, and section 2.3 suggests that part is larger.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ A queue that costs CPU                                                   │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   more requests waiting ──► each arrival and each release walks the      │
│          ▲                   whole queue: more CPU per request           │
│          │                                  │                            │
│          │                                  ▼                            │
│   requests finish slower ◄── the event loop has less CPU left for        │
│                               the requests themselves                    │
│                                                                          │
│ Past the knee, the service can serve less than the limit it was sized for│
└──────────────────────────────────────────────────────────────────────────┘
```

Section 2.3's overload timeline shows the result live. At 60 requests per second into a pool of 50 per second, the API's CPU was 16% in the first second and 99% from second 18. By then only about 50 requests per second were starting. At light load a request cost about 3 ms of CPU. In the queue it cost nearer 20 ms. The first version of this lab, with holds of 20 ms, showed the effect as a collapse. Its pool of 5 could serve 250 per second. At 150 per second, 60% of the pool's limit, the client p99 was 10.23 s. At 280 per second the API finished 245 to 290 requests per second for the first 3 s. Then it finished mostly near 100, with the CPU mostly at 93 to 99%. That version is kept in `runs/lab2-first-attempt-20ms.log`.

The pool's size costs CPU too, when its connections are open and idle. The same function loops over every connection, and inside that loop builds a list over every connection again, lines 292 to 296. `pool_cost.py --sizes` sends one request at a time with C connections open:

```
pool of    5 open connections, no queue:    1583 µs CPU per request, so one event loop tops out near   632 requests/s
pool of   20 open connections, no queue:    1950 µs CPU per request, so one event loop tops out near   513 requests/s
pool of   50 open connections, no queue:    3466 µs CPU per request, so one event loop tops out near   288 requests/s
pool of  100 open connections, no queue:    8430 µs CPU per request, so one event loop tops out near   119 requests/s
pool of  200 open connections, no queue:    8122 µs CPU per request, so one event loop tops out near   123 requests/s
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ httpx client CPU per request, no queue, by connections open. Lab part Q  │
├──────────────────────────────────────────────────────────────────────────┤
│   5 open  ████████                                      1583 µs          │
│  20 open  ██████████                                    1950 µs          │
│  50 open  ██████████████████                            3466 µs          │
│ 100 open  ████████████████████████████████████████████  8430 µs          │
│ 200 open  ██████████████████████████████████████████    8122 µs          │
│                                                                          │
│ From 5 to 100 connections open, the same request cost 5.3 times as much  │
└──────────────────────────────────────────────────────────────────────────┘
```

The cost grows with the connections that are open, not with the pool's limit. A pool of 100 that never opens more than a few connections costs about the same as a pool of 5. Section 2.5 shows what these two costs do to a service's capacity.

**A collapse from Phase 1's build.** While the Phase 1 lab was being built, a run of the 2 ms course service at 250 requests per second collapsed. Its p99 was 12.7 s. That is about 250 × 2.25 ms = 56% of its capacity. The course's records promised this section would explain it. Measured again with the current load generator and independent random streams, three runs of 30 s:

```
open 250/s poisson, timer=due, raw n=  6891  mean   5.60 ms  p50   4.45 ms  p90   11.5 ms  p99   19.2 ms  p99.9   25.4 ms  max   28.6 ms  errors=0  sent 245/s
open 250/s poisson, timer=due, raw n=  7023  mean   6.01 ms  p50   4.47 ms  p90   12.0 ms  p99   25.2 ms  p99.9   51.7 ms  max   56.0 ms  errors=0  sent 252/s
open 250/s poisson, timer=due, raw n=  6955  mean   5.32 ms  p50   4.12 ms  p90   10.6 ms  p99   19.7 ms  p99.9   27.9 ms  max   32.4 ms  errors=0  sent 249/s
```

It did not reproduce. That first run used an older load generator, which sent through httpx with 100 connections. It also used the random sequence that Phase 1, section 1.5 found shared between the generator and the service. Part K2 of the lab runs the same service at 250 per second through the httpx client and then the raw client. It ran twice that day, in two sessions. The first session's log is `runs/p2-superseded/lab2-k2.log`, the second's is `runs/lab2.log`:

| Client | Load average | p99 | CPU of the generator, user plus system | Generator lag p99 |
|---|---|---|---|---|
| httpx, 100 connections | 6.3 | 481 ms | 5.2 s | 33.4 ms, invalid |
| raw | 6.3 | 21.6 ms | 0.8 s | 2.08 ms |
| httpx, 100 connections | 4.5 at the session's start | 29.4 ms | 4.2 s | 3.34 ms |
| raw | 4.5 at the session's start | 21.5 ms | 0.7 s | 2.08 ms |

The httpx client used five to six times the CPU of the raw one both times. On a busy laptop it made the same service's p99 22 times worse, and on a quieter one 1.4 times. So the generator's own httpx pool can inflate a measurement badly, and most likely did in the first run. That is inferred. The 12.7 s collapse itself did not come back, so its exact cause is not isolated.

**The sentence to remember:** backpressure decides where work beyond capacity goes: a buffer adds latency and memory, blocking makes the caller wait, refusing sends the client an error. A queue that adds work as it grows, through retries or a pool that walks its queue, can keep the service down after the trigger is gone.

**The trap:** an unbounded default, such as `asyncio.Queue()` or client retries with no budget. It turns a 2 s stall at 70% load into an outage that lasts until someone removes load.

**Try this now:** run `uv run python phase02_queueing/retry_storm.py --retries 1`. With one retry the most a request can be multiplied is 2, so Huang's bound says the load is safe below 50 per second. At 70 per second, does the system recover after the 2 s stall? The run says no: the last 10 s have a goodput of 0.0 per second. Then try `--retries 1 --rate 45`, below the bound. Goodput drops to zero for about 14 s, from t = 21 s to t = 34 s, and then recovers to 45.7 per second.

---
## 2.5 — The capacity envelope of a service (headroom, read per resource)

Why this matters: "we are at 40% CPU, so we have plenty of headroom" is said often before an incident. A service has several resources, each with its own limit. Its capacity is the lowest of those limits, and section 2.4 showed that a queue which costs work can push a service below every limit you computed.

**Answer this first.** The lab API uses two resources for `/pooled`: its one event loop's CPU, and a pool of connections held 100 ms each. You can set the pool to 5, 20, 50 or 100 connections. Predict the capacity for each. Does a pool of 100 carry twice the load of a pool of 50?

**The method: one limit per resource, and take the smallest.** For each resource a request uses, write down its limit. The service's capacity is the smallest of them, and every other number is room that cannot be used:

```
pool limit       = connections / hold time          5 / 0.1 s = 50 per second
CPU limit        = 1 / CPU seconds per request      1 / 0.00347 s = 288 per second
capacity         = min(pool limit, CPU limit)        50 per second, set by the pool
```

This is Brendan Gregg's USE method applied to capacity. For every resource, check its utilisation, its saturation and its errors. His definition of saturation for a thread pool is "the number of requests waiting to be serviced by the thread pool". He also warns that "a total utilization of, say, 70% can hide short bursts of 100% utilization". The Google SRE book, chapter 21, says "A better solution is to measure capacity directly in available resources". It adds that at Google, CPU alone worked as the signal "in a majority of cases". A Python service with small pools is one of the other cases: its pool fills first.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The envelope, drawn per resource. Pool of 5, 100 ms holds                │
├──────────────────────────────────────────────────────────────────────────┤
│ load /s      0        100        200        300        400               │
│              ├─────────┼──────────┼──────────┼──────────┤                │
│ pool         ████ limit 50                                               │
│ event loop   █████████████████████████████ limit 288, from a light load  │
│                                                                          │
│ capacity = 50/s, set by the pool. At 40/s the lab measured CPU at 13%    │
│ and the pool at 80% offered load: the CPU's room cannot be used          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Measured: the prediction, and its check.** `envelope.py` does this for each pool size. It runs a light load, 30 requests per second, and reads the API's CPU per request. It computes both limits, then loads the service at 80% of the smaller one to check it. Every run below is valid by the rule of Phase 1, section 1.2:

```bash
uv run python phase02_queueing/envelope.py --pools 5 20 50 100 --verify
```

```
POOL    5: CPU  3.47 ms per request at 30/s. Pool limit     50/s, CPU limit    288/s, capacity     50/s, bound by the pool
  VERIFY at    40/s, 80% of capacity: CPU 13%, started 36/s, offered pool load 80%, pool wait p99 363 ms, client p99 627 ms, errors 0, generator lag p99 2.44 ms valid
POOL   20: CPU  3.10 ms per request at 30/s. Pool limit    200/s, CPU limit    322/s, capacity    200/s, bound by the pool
  VERIFY at   160/s, 80% of capacity: CPU 29%, started 151/s, offered pool load 80%, pool wait p99 58 ms, client p99 463 ms, errors 0, generator lag p99 2.14 ms valid
POOL   50: CPU  2.88 ms per request at 30/s. Pool limit    500/s, CPU limit    347/s, capacity    347/s, bound by the event-loop CPU
  VERIFY at   277/s, 80% of capacity: CPU 66%, started 116/s, offered pool load 55%, pool wait p99 16179 ms, client p99 21856 ms, errors 0, generator lag p99 2.07 ms valid
POOL  100: CPU  2.09 ms per request at 30/s. Pool limit   1000/s, CPU limit    479/s, capacity    479/s, bound by the event-loop CPU
  VERIFY at   383/s, 80% of capacity: CPU 72%, started 63/s, offered pool load 38%, pool wait p99 26542 ms, client p99 60031 ms, errors 0, generator lag p99 2.10 ms valid
```

For pools of 5 and 20 the prediction held. The pool bound, and at 80% of its limit the service was healthy: CPU at 13% and 29%, no errors. For pools of 50 and 100 it failed. It predicted the CPU would bind at 347 and 479 per second. At 80% of those, the service collapsed. Only 116 and 63 requests per second were starting, and the client p99s were 21.9 s and 60 s.

**WRONG: compute each limit at a light load, and take the smallest.** The CPU cost per request was right at the light load. It was not the cost the service ran at once a queue had formed. `sweep.py` shows the jump, pool by pool:

```bash
uv run python phase02_queueing/sweep.py --pool 50 --rates 100 150 200 250
uv run python phase02_queueing/sweep.py --pool 100 --rates 100 150 200 250
```

| Pool | Rate | Offered pool load | Started/s | API CPU | CPU per started request | Pool wait p99 | Client p99 | Generator lag p99 |
|---|---|---|---|---|---|---|---|---|
| 50 | 100/s | 20% | 95 | 20% | 2.15 ms | 4 ms | 457 ms | 2.13 ms |
| 50 | 150/s | 30% | 134 | 35% | 2.62 ms | 1.3 s | 1.6 s | 3.30 ms |
| 50 | 200/s | 40% | 104 | 70% | 6.70 ms | 16.7 s | 20.7 s | 2.10 ms |
| 50 | 250/s | 50% | 90 | 73% | 8.13 ms | 21.0 s | 35.7 s | 2.11 ms |
| 100 | 100/s | 10% | 95 | 18% | 1.86 ms | 4 ms | 455 ms | 2.12 ms |
| 100 | 150/s | 15% | 144 | 30% | 2.11 ms | 11 ms | 457 ms | 2.12 ms |
| 100 | 200/s | 20% | 186 | 40% | 2.18 ms | 544 ms | 720 ms | 2.08 ms |
| 100 | 250/s | 25% | 73 | 74% | 10.22 ms | 23.3 s | 48.8 s | 2.19 ms |

Read the CPU per started request. Before the service broke, it stayed between 1.86 and 2.62 ms, close to the probe. At the rates where it broke, it was 6.70 to 10.22 ms, and the requests starting per second fell well below the offered rate. The service did not slide towards a limit. It jumped between two states. In the good one, each request costs about 2 ms. In the bad one, the queue of section 2.4 makes each request cost several times more. Neither computed limit shows where the jump happens.

The jump also moved between sessions. In an earlier valid session, the pool of 50 was healthy at 200 per second, with a p99 of 454 ms and the CPU at 39%. It broke only at 250. That session is kept in `runs/p2-superseded/`. Near the jump, the same load goes one way or the other, as the retry model did at 35% in section 2.4.

**RIGHT: find the knee by loading the service there, and keep well below it.**

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Highest load that stayed healthy, per pool size. 100 ms holds            │
├──────────────────────────────────────────────────────────────────────────┤
│ pool   5   ██████                           40/s checked, limit 50       │
│ pool  20   ██████████████████████████       160/s checked, limit 200     │
│ pool  50   ████████████████                 100/s here, 200/s before     │
│ pool 100   ████████████████████████         150/s, 200/s slower          │
│                                                                          │
│ Past about 20 connections, more connections added no capacity            │
└──────────────────────────────────────────────────────────────────────────┘
```

Past about 20 connections, more connections added no capacity. The pool of 50 slowed at 150 per second and broke at 200 in this session. The pool of 100 slowed at 200 and broke at 250. Both sit around the 200 per second where the pool of 20 reaches its own limit anyway. The pool limit rose with every connection. The CPU and the queue set the real limit, and it did not rise. Whether a much larger pool would lower capacity was not measured in a valid run. `pool_cost.py --sizes` shows the mechanism that could: each open connection makes every request cost more.

**Reading headroom on a real service.** For every resource a request uses, graph three numbers, as in section 2.3: how busy it is, how many requests wait for it, and its errors. Then:

1. Find the knee by loading the service at rising rates, not by computing it from a quiet hour.
2. Take the lowest knee as the capacity. Another resource's spare room is not headroom.
3. Watch for the jump: CPU per request that suddenly rises, and requests started per second that fall below the offered rate.
4. Re-measure after any change to a pool size, a worker count or a client library. Sections 2.1 and 2.4 showed that each can change the CPU cost per request.
5. Keep the operating point well below the knee. Near it, the same load can land in either state.

**The sentence to remember:** a service's capacity is the smallest of its resources' limits, and a queue that costs work can drop it into a bad state below all of them. Find the knee by loading the service there, and read headroom per resource.

**The trap:** "CPU at 40%, pool at 40%, so we have 60% headroom". The pool of 50 was near those numbers at 200 per second in one session, and in the next session it broke at that rate.

**Try this now:** run `uv run python phase02_queueing/envelope.py --pools 10 30 --verify`. Predict first which resource binds for each, and at what rate. Then see whether 80% of the predicted capacity holds.

---
## 🧪 Hands-on lab — part B

**Run status:** every command below was executed on the author's machine on 2026-09-25, in the conditions of part A. Each "Expected" line is copied from `runs/lab2-*.log`. The offline models are exact for their seeds. The live runs will differ on your machine in their numbers, not in their shape.

- [ ] **E7 (offline).** Four answers to a producer faster than its consumer.
  - Run: `uv run python phase02_queueing/backpressure.py`, then `uv run python phase02_queueing/backpressure.py --self-test`.
  - Expected: every policy `done  100.0/s`. `buffer ... p99  12.015 s  most held   1214`. `refuse ... refused  16.1%  ... p99   0.500 s`.
  - Then try `--queue 10`, and predict the block-closed p99 first. A full queue of 10 at 10 ms each adds about 0.1 s. The run gives `block-closed ... p99   0.100 s`.
  - Teaches: no policy adds capacity. Each one picks who pays.

- [ ] **E8 (break-it, offline).** Give the clients retries.
  - Run: `uv run python phase02_queueing/retry_storm.py`, then `uv run python phase02_queueing/retry_storm.py --self-test`.
  - Expected: `no retries ... last 10 s goodput  68.6/s`, `retries ... q6013    last 10 s goodput   0.0/s`, `retries+drop ... last 10 s goodput  68.7/s`.
  - Then run `--rate 35 --seed 1` and `--rate 35 --seed 2`. Expected: seed 1 stays down, seed 2 recovers, `34.6/s`.
  - What broke: a 2 s stall at 70% load became an outage that outlived it by the rest of the run.
  - Teaches: retries plus wasted work sustain a failure. Dropping requests whose client has left breaks the loop.

- [ ] **E9 (local).** What the queue and the pool size cost.
  - Run: `bash runs/lab2.sh Q`. About 2 minutes.
  - Expected: `50 requests queued ... 481.9 µs per request` up to `800 requests queued ... 2563.0 µs per request`. With no queue, `pool of    5 open connections ... 1583 µs` and `pool of  100 open connections ... 8430 µs`.
  - Absolute numbers moved by up to 50% between runs on the busy laptop. Compare within one run.
  - Teaches: httpx's pool bookkeeping grows with its queue and with its open connections.

- [ ] **E10 (break-it, local).** Predict the envelope from a light load, and check it.
  - Run: `bash runs/lab2.sh E`. About 3 minutes.
  - Expected: `POOL    5 ... bound by the pool` and `VERIFY at    40/s ... CPU 13% ... errors 0`. `POOL   50 ... CPU limit    347/s ... bound by the event-loop CPU`, then `VERIFY at   277/s ... started 116/s ... client p99 21856 ms`.
  - What broke: the limits computed at 30 per second did not show where the service jumps into the bad state.
  - Teaches: a computed limit is an upper bound. The knee has to be found by loading the service.

- [ ] **E11 (local).** Find the real knees.
  - Run: `bash runs/lab2.sh S`. About 4 minutes.
  - Expected: pool of 50 at 100/s `CPU 20% = 2.15 ms per started request`, healthy. At 200/s `started 104/s` and `6.70 ms per started request`. Pool of 100 at 250/s `started 73/s` and `10.22 ms per started request`.
  - Then `bash runs/lab2.sh K` to re-run the Phase 1 collapse. Expected: three runs at 250/s with p99 near 20 ms and `errors=0`.
  - Teaches: watch CPU per started request. A jump is the service changing state.

- [ ] **E12 (written).** The envelope of a service you own.
  - List every resource one endpoint uses: event loop, each pool, each thread pool, each downstream.
  - For each, write its limit with the arithmetic, and the metric that shows its saturation. Mark every resource that has no saturation metric today.
  - Teaches: headroom is read per resource.

---

## 🔍 Check it yourself

1. Open `phase02_queueing/retry_storm.py:126`. This is the line that drops a request whose client has left. What would a real server need to know to do the same? Name the header or deadline that would carry it.

2. Open `phase02_queueing/pool_cost.py:86`. This is `size_cost`. It opens every connection first and then sends one request at a time. Why must it open them first to measure the pool's size, and what would it measure if it did not?

3. Open `phase02_queueing/envelope.py:47`. This is `limits`. It takes the smaller of two limits. Write down the third resource the lab API has that this function ignores, and what its limit is.

4. In any Python service you own, list every pool and queue with its size:

   ```bash
   grep -rnE "Limits\(|pool_size|max_overflow|max_connections|create_pool|asyncio\.Queue\(|ThreadPoolExecutor\(|retries" <your repo>/
   ```

   For each one, write whether it buffers, blocks or refuses when full, and what its caller sees.

---

## ✅ Checkpoint 2B — answer in your own words

1. **Design it.** An API accepts uploads at up to 300 per second in bursts. A worker behind a queue processes 200 per second. Which of buffer, block and refuse do you choose for the API, and what does each client see? Give the numbers for a 10 s burst.

2. **Show the arithmetic.** Clients time out after 1 s and retry up to 2 times. The server can serve 100 requests per second. (a) By Huang et al.'s bound, below what load can a stall never leave the system stuck? (b) With the retry budget raised to 5, what is the bound? (c) What does the server-side fix in section 2.4 change in that bound?

3. **A colleague says:** "The pool of 50 runs at 40% busy and the CPU at 39% at 200 per second, so we can take 400 per second". Argue for or against with the lab's numbers.

4. **This is broken.** After a 3 s database stall, an API's throughput stays at 40% of normal for an hour. CPU is at 95%. The number of requests waiting for a connection is stuck at its maximum. Nothing else is wrong. Name two sustaining effects that fit, how to tell them apart from metrics, and what ends the state.

5. **Demonstrate.** The lab API has 100 ms holds. Choose a pool size for 150 requests per second. Justify it with the envelope: the pool limit, the CPU cost you measured, and the margin you keep.

<details>
<summary>Answer sketches</summary>

1. The surplus is 100 per second, so a 10 s burst leaves 1,000 items beyond the worker. Buffer: all 1,000 wait, and the last waits 1,000 / 200 = 5 s after the burst ends, plus memory for 1,000 uploads. Block: the uploaders' connections stay open. Callers that cannot slow queue in front of the API instead. Refuse: 1,000 of the 3,000 get a fast 503 and must retry, which adds load later unless the retry is spread out. A common choice is a small bounded buffer to absorb short bursts, then refuse with a `Retry-After`.

2. (a) Each request can be sent 1 + 2 = 3 times. With no loss of capacity, the bound is 100 / 3 = 33 per second. (b) 1 + 5 = 6 times: 100 / 6 = 17 per second. (c) Dropping requests whose client has left removes the wasted work. Each user then costs the server about one request again, however many copies were sent, if dropping is free. So the multiplier in Huang's bound falls back towards 1, and the bound towards the capacity, 100 per second. That is from the model only. In it, with 3 retries and the drop, the system recovered at 70% load, where without the drop it never did.

3. Against. In one session the pool of 50 was healthy at 200 per second, at 39% CPU and 40% offered pool load. In the next session it broke at that same rate: only 104 requests per second started, and each cost 6.70 ms of CPU instead of about 2. Once a queue forms, httpx's cost per request rises with it. Two resources near 40% do not mean 60% headroom when a queue can change the cost per request. Find the knee by loading the service at rising rates, and keep the operating point well below the lowest knee you have seen.

4. First, retries plus wasted work: clients time out and retry, and the server serves copies nobody waits for. Look for requests sent per second above the organic rate, and for work finished after the client's deadline. Second, a queue that costs CPU, as httpx's pool does: CPU near 100% while the CPU per request jumps. In the lab the pool of 50 went from about 2 ms to 6.70 ms per started request, and only 104 of 200 requests per second started. Both need load removed to end: shed or refuse load, cap retries, drop expired requests. Restarting alone does not help if the same load returns.

5. With 100 ms holds, the pool limit is C / 0.1 s. A pool of 20 gives 200 per second, pool-bound, and the lab checked 160 per second as healthy, with CPU at 29%. At 150 per second that is 75% offered load. `capacity.py --pool 20 --hold-ms 100 --rate 150` gives P(wait) 16.0% and a p99 wait of 55.51 ms. A pool of 50 raises the pool limit to 500 per second but not the service's capacity: it slowed at 150 and broke at 200 in one session. So a pool of 20, with the rule to re-measure after any change. So a pool of 20, with the rule to re-measure after any change.

</details>

---

## References & Further Learning — part B

Every URL below was fetched on 2026-09-25 and returned HTTP 200.

**Backpressure and metastable failures**

- **Bronson et al., "Metastable Failures in Distributed Systems", HotOS 2021** — https://sigops.org/s/conferences/hotos/2021/papers/hotos21-s11-bronson.pdf
  Focus on: the definition, Figure 1's stable, vulnerable and metastable states, and section 2.1, the retry example. Its numbers are illustrative, not measured.
- **Huang et al., "Metastable Failures in the Wild", OSDI 2022** — https://www.usenix.org/system/files/osdi22-huang-lexiang.pdf
  Focus on: section 3, Theorem 2, the safe load, and section 5.2, the controlled experiment. 22 incidents from 11 organisations.
- **Google SRE book, "Addressing Cascading Failures"** — https://sre.google/sre-book/addressing-cascading-failures/
  Focus on: queue length against thread count, "small queue lengths relative to the thread pool size", and retries.
- **Reactive Streams 1.0.4 README** — https://raw.githubusercontent.com/reactive-streams/reactive-streams-jvm/v1.0.4/README.md
  Focus on: the goal of backpressure, and the choice to "either buffer or drop elements".
- **Python docs, `asyncio.Queue`, 3.13** — https://docs.python.org/3.13/library/asyncio-queue.html
  Focus on: `maxsize`, `put` and `put_nowait`. One class gives all three policies.

**Capacity**

- **Brendan Gregg, "The USE Method"** — https://www.brendangregg.com/usemethod.html
  Focus on: the definitions of utilisation, saturation and errors, and the section on software resources such as thread pools.
- **Google SRE book, "Handling Overload"** — https://sre.google/sre-book/handling-overload/
  Focus on: measuring capacity in available resources, not in requests per second.
- **Neil J. Gunther, "A General Theory of Computational Scalability Based on Rational Functions", 2008** — https://arxiv.org/abs/0808.1431
  Focus on: equations 5 and 6, and the retrograde region past the peak.
- **HikariCP wiki, "About Pool Sizing"** — https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing
  Focus on: why a small pool is faster. Note the formula is for the database side, and the PostgreSQL wiki it quotes says it needs adjustment.

---

## Cheatsheet — part B

```
BACKPRESSURE        the consumer finishes its rate whatever you choose
  buffer            latency and memory grow: 20/s extra for 60 s → 1,214 held, p99 12 s
  block             the caller waits. Callers that cannot slow queue one step earlier
  refuse            fast errors: 120/s into 100/s → 16.1% refused, p99 0.5 s
  Python defaults   asyncio.Queue() unbounded. uvicorn --limit-concurrency → 503
                    macOS listen backlog capped at 128. Linux default 4,096

THE QUEUE THAT FEEDS ITSELF
  metastable        a trigger starts it, a sustaining effect keeps it after
  Huang's bound     safe load < capacity / (work multiplier × capacity loss)
                    3 retries, no loss → 100 / 4 = 25/s. Model: 30 ok, 35 2 of 5 down
  fix               drop requests whose client has left, cap retries, shed load
  httpx pool        ~2.8 µs more CPU per arrival for each request already waiting
                    ~8.4 ms CPU per request with 100 connections open, no queue

CAPACITY ENVELOPE
  per resource      limit = connections / hold time   or   1 / CPU per request
  capacity          at most the smallest limit. Other resources' room is not headroom
  two states        CPU per request ~2 ms healthy, 6.7 to 10.2 ms once a queue forms
  find the knee     by a sweep; it moved between sessions. Keep well below it
  more connections  past ~20, added no capacity here
```

# Phase 2A — Queueing, saturation and tail latency: where the time goes

**The question this phase answers:** the CPU is at 60% and p99 is already bad. Which resource is saturating, a fan-out, a shared event loop, a pool, and where is the knee for your service?

Here is an example. A service ran fine at 60% CPU for months. A marketing email pushed it to 85%, and its p99 went from 60 ms to 4 seconds while its mean rose from 20 to 45 ms. The dashboard showed means, so it looked healthy. Adding servers fixed it, and nobody learned why. The next quarter it happened again, in the database connection pool this time. The example is invented. Every mechanism in it has a measured counterpart in this phase.

Phase 1 predicted a service with one queue. Real services have several resources, and the one that fills first is often not the one you planned for. This phase teaches five ideas. Each is a claim you could get wrong today:

1. **A request that waits for N calls is as slow as its slowest call.** At fan-out 100, with 1% of calls slow, 63% of requests are slow. In Python each call also costs the caller about 2 ms of CPU on one event loop.
2. **An asyncio event loop is one queue.** So one blocking call inside an async handler stalls every request in flight, whatever the CPU graph shows.
3. **A small pool that waits fills before the CPU does.** It shows it first as a rising wait at a flat error rate. Small means its connections divided by its hold time is below one over the CPU cost of a request. A pool that refuses shows errors at once.
4. **Work beyond capacity goes to one of three places.** A buffer adds latency and memory, a blocked caller waits, a refused client gets an error. A queue that adds work as it grows can keep a service down after its trigger is gone. Retries do that, and so does a pool that walks its queue.
5. **A service's capacity is at most the smallest of its resources' limits.** A queue that costs work can push it into a bad state below every computed limit. So the knee is found by loading the service there, and headroom is read per resource.

Phase 2 is split into two documents. This one teaches the first three ideas: where the time goes inside one request. Part B teaches the last two: what happens past the limit, and how to read the limit for a whole service.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, this document: where the time goes                               │
│  2.1  Fan-out amplification         — slower than any of its calls       │
│  2.2  Head-of-line blocking         — one slow step, everyone waits      │
│  2.3  Pools that fill               — wait first, errors later           │
│  Lab: E1 to E6                                                           │
│                                                                          │
│ PART B, the next document: past the limit                                │
│  2.4  Backpressure                  — where the extra work goes          │
│  2.5  The capacity envelope         — headroom, read per resource        │
│  Lab: E7 to E12                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**What this part assumes.** From Phase 1 of this course: the open-loop load generator, and its validity rule from section 1.2. A generator lag p99 above 10 ms makes a run invalid. The prediction sheet and the M/M/1 model, from section 1.5. From the inference-internals course, briefly:

- **inference-internals 6.1, Little's law and the knee.** Little's law, L = λW, links the requests in a system, their arrival rate, and the time each one spends there. Here ρ is the share of time a server is busy. For one server, the mean wait in the queue is ρ / (1 − ρ) service times: 4 at 80% busy, 19 at 95%. A pool of several connections has the same kind of knee, later and sharper.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. The lab starts two local services for each run: a backend that only waits, and an API that calls it. Every number was measured on 2026-09-25 on an Apple M2 with 8 GB, macOS 15.7.8 and CPython 3.13.3 through uv. The libraries were httpx 0.28.1, starlette 1.7.0 and uvicorn 0.53.0. While the lab ran, other programs on the laptop kept the load average near 6. Every log begins with its conditions.

Setup, the same code folder as Phase 1:

```bash
cd ~/Desktop/project/study-material/elite-performance/code
uv sync
uv run python phase02_queueing/api.py --self-test
```

The last line should print `self-test passed`.

Time for part A: 1.5 to 2 hours. About 10 minutes of that is waiting for load runs.

---
## 2.1 — Fan-out amplification (why a request is slower than any of its calls)

Why this matters: a request that calls ten services is slow more often than any one of them. If you set each dependency's target on its own p99, the request built from them misses its target most of the time. In Python there is a second cost, which Dean and Barroso's numbers leave out: every call also costs the caller CPU.

**Answer this first.** A request calls 100 backends at once and waits for all of them. Each backend answers in 5 ms, except 1 call in 100, which takes 100 ms. What fraction of requests take 100 ms or more? And if you halve the fan-out to 50?

**The mechanism: a request is as slow as its slowest call.** The request ends when its last call ends. So it is fast only if every call is fast. If each call is slow with probability p, independently, then:

```
P(request is slow) = 1 − (1 − p)^N

N = 1:     1 − 0.99       =  1.0%
N = 10:    1 − 0.99^10    =  9.6%
N = 50:    1 − 0.99^50    = 39.5%
N = 100:   1 − 0.99^100   = 63.4%
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Share of requests slow, each call slow 1%. Formula 1 − 0.99^N            │
├──────────────────────────────────────────────────────────────────────────┤
│ fan-out   1  █                                                    1.0%   │
│ fan-out  10  █████                                                9.6%   │
│ fan-out  20  █████████                                           18.2%   │
│ fan-out  50  ████████████████████                                39.5%   │
│ fan-out 100  ████████████████████████████████                    63.4%   │
│ fan-out 200  ███████████████████████████████████████████         86.6%   │
│                                                                          │
│ Halving the fan-out from 100 to 50 takes 63.4% to 39.5%, not to 32%      │
└──────────────────────────────────────────────────────────────────────────┘
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Example: one request, fan-out 10. Each call 5 ms, or 100 ms at 1%        │
├──────────────────────────────────────────────────────────────────────────┤
│ call 1   █                                                               │
│ call 2   █                                                               │
│ call 3   ████████████████████  the one slow call                         │
│ call 4   █                                                               │
│  ...     █                                                               │
│ call 10  █                                                               │
│          ├────┬────┬────┬────┤  one block = 5 ms                         │
│          0   25   50   75  100 ms                                        │
│                                                                          │
│ request  ████████████████████  ends when the slowest call ends: 100 ms   │
└──────────────────────────────────────────────────────────────────────────┘
```

Dean and Barroso give the same arithmetic in "The Tail at Scale", CACM 2013. Their example: servers that answer in 10 ms, with a p99 of one second. A request that collects from 100 of them is slow 63% of the time. They also give a measurement from a real Google fan-out service, their Table 1. One random leaf finished in 10 ms at p99. Waiting for all leaves took 140 ms at p99. The paper does not state the number of leaves, the hardware or the load.

`fanout.py` checks the formula against a simulation of 20,000 requests:

```bash
uv run python phase02_queueing/fanout.py
```

```
each call: 5 ms, or 100 ms with probability 1.00%
fan-out     1: formula   1.0% slow, simulated   1.1%; p50 5 ms, p99 100 ms
fan-out    10: formula   9.6% slow, simulated   9.7%; p50 5 ms, p99 100 ms
fan-out    50: formula  39.5% slow, simulated  39.7%; p50 5 ms, p99 100 ms
fan-out   100: formula  63.4% slow, simulated  63.7%; p50 100 ms, p99 100 ms
```

At fan-out 100 the median request is slow. A 1% event in each call has become the typical case for the request. Halving the fan-out to 50 brings the slow share down to 39.5%, not to half.

**Where the formula stops working.** It assumes each call is slow on its own. If one cause slows many calls at once, such as a garbage-collection pause on a shared backend or one overloaded switch, the calls are correlated. Then the formula can be wrong in either direction. This limit is inferred, not measured here.

**The usual fix: hedged requests.** Send a second copy of any call that has not answered by a short delay, and take whichever answers first. Both copies must be slow for the call to be slow, so a 1% slow call becomes a 0.01% slow call.

```bash
uv run python phase02_queueing/fanout.py --hedge-ms 10
```

```
fan-out    10: formula   9.6% slow, simulated   9.7%; p50 5 ms, p99 100 ms  | hedged at 10 ms: p99 15 ms, 1.01% extra calls
fan-out    50: formula  39.5% slow, simulated  39.7%; p50 5 ms, p99 100 ms  | hedged at 10 ms: p99 15 ms, 1.00% extra calls
fan-out   100: formula  63.4% slow, simulated  63.7%; p50 100 ms, p99 100 ms  | hedged at 10 ms: p99 100 ms, 1.01% extra calls
```

For 1% more calls, the slow requests fall from 63.4% to about 1%. At fan-out 100 the hedge also cuts the p50, from 100 ms to 15 ms. It does not cut it to 5 ms. A hedged call ends at 10 + 5 = 15 ms, so any request with a slow first copy now takes at least the hedge delay plus one fast call. And 1.03% of requests are still slow, slightly above the p99 line. The self-test prints `hedged at 10 ms: 1.03% slow, p50 15 ms, p99 100 ms`. Dean and Barroso measured the same idea on a BigTable benchmark. A hedge after 10 ms cut the p99.9 from 1,800 ms to 74 ms, for 2% more requests.

Hedging helps only while the servers have room. Vulimiri et al., CoNEXT 2013, prove that sending every request twice lowers the mean response time only below 33% utilisation, for exponential service times. A hedge after a delay sends far fewer copies, but the extra load still comes when the servers are busiest.

**The second cost: CPU in the caller.** The lab ran the formula for real. The Phase 2 API's `/fanout?n=N` calls a backend N times at once with `asyncio.gather`, through one httpx client. Each backend call takes 5 ms, or 100 ms with probability 1%. The load generator sends requests open-loop at 100 / N per second, so the API makes 100 backend calls per second at every fan-out:

```bash
uv run python phase02_queueing/fanout.py --live --fanout 1 10 50 100
```

```
fan-out    1 at 100.00/s:   81 requests,   0.0% took >= 100 ms (formula   1.0%); p50 9.5 ms, p99 14.6 ms; API CPU 20%, 2.07 ms per call; generator lag p99 2.21 ms valid
fan-out   10 at 10.00/s:   76 requests,  14.5% took >= 100 ms (formula   9.6%); p50 31.7 ms, p99 166.5 ms; API CPU 18%, 1.95 ms per call; generator lag p99 2.27 ms valid
fan-out   50 at  2.00/s:   70 requests, 100.0% took >= 100 ms (formula  39.5%); p50 460.5 ms, p99 2402.5 ms; API CPU 36%, 3.81 ms per call; generator lag p99 5.65 ms valid
fan-out  100 at  1.00/s:   72 requests, 100.0% took >= 100 ms (formula  63.4%); p50 1002.4 ms, p99 8357.4 ms; API CPU 38%, 3.83 ms per call; generator lag p99 5.26 ms valid
```

At fan-out 10, 14.5% of 76 requests were slow, against 9.6% from the formula. With 76 requests that is within noise, and the CPU effect below may add to it. At fan-out 50 every request was slow, far above the formula's 39.5%. The backends did not cause it. The API did. All four runs had a generator lag p99 under 6 ms, so they are valid by the rule of Phase 1, section 1.2.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Fan-out 50 on one Python event loop, at about 2 ms of CPU per call       │
├──────────────────────────────────────────────────────────────────────────┤
│ what you draw    50 calls in parallel, each 5 ms   ──►  request 5 ms     │
│                                                                          │
│ what happens     the loop runs each call's Python in turn:               │
│                  call 1 ██ call 2 ██ call 3 ██ ... call 50 ██            │
│                  50 × 2 ms = 100 ms of CPU        ──►  request ≥ 100 ms  │
│                                                                          │
│ fan-out 100      the calls also meet the API's limit of 100 connections  │
│                  for fan-out, so some wait in the client's pool          │
└──────────────────────────────────────────────────────────────────────────┘
```

At fan-out 50 and 100 the cost per call rose to 3.81 and 3.83 ms. More calls at once keep more connections open in the API's fan-out client, and section 2.4 measures that each open connection makes every request cost more. That link is inferred: the number of open connections was not recorded. A first version of this lab ran fan-out 50 at 10 requests per second, 500 calls per second. It held the API at 100% CPU until it was stopped. That run was not kept.

**The sentence to remember:** a request that waits for N calls is as slow as its slowest one. A 1% slow call makes 63% of fan-out-100 requests slow. In Python each call also costs the caller CPU on its one event loop: about 2 ms per httpx call on this machine.

**The trap:** setting each dependency's latency target on its own p99. A request that calls 10 of them misses its p99 target about 10% of the time from the tails alone. It misses more often when the calls use the caller's CPU.

**Try this now:** run `uv run python phase02_queueing/fanout.py --p-slow 0.001 --fanout 1 10 100 1000`. Predict the slow share at fan-out 1,000 first. The run gives 63.2% by the formula and 63.8% simulated: a 1 in 1,000 event is the median case at fan-out 1,000.

---
## 2.2 — Head-of-line blocking (one slow step, and everyone behind it waits)

Why this matters: a Python API can have a bad p99 while its CPU graph shows 5%. The cause is usually one blocking call inside an `async def` handler. The CPU is idle because the thread is asleep, and every other request is waiting behind it.

**Answer this first.** An API serves `/health`, which does no work, at 100 requests per second. A different endpoint, 5 times per second, calls `time.sleep(0.05)` inside an `async def` handler. What is the p99 of `/health`? What does the API's CPU graph show?

**The mechanism: one event loop is one queue.** The Python docs state it: "While a Task is running in the event loop, no other Tasks can run in the same thread". A task gives the loop back only when it reaches a point where it actually waits, such as an `await` on a socket. `time.sleep` is not such a point. It stops the whole thread. For those 50 ms nothing else on the loop runs: no other handler, no accept of a new connection, no health check.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One event loop. A handler calls time.sleep(0.05) inside async def        │
├──────────────────────────────────────────────────────────────────────────┤
│ time        0 ms        10        20        30        40        50 ms    │
│ loop        ██████████ time.sleep: the thread sleeps ██████████ free     │
│ CPU         idle ─────────────────────────────────────────────── idle    │
│                                                                          │
│ /health A   arrives at 10 ms ──── waits 40 ms ──────────────────► runs   │
│ /health B   arrives at 30 ms ──── waits 20 ms ────────► runs             │
│                                                                          │
│ Every request that arrives during the sleep waits for the rest of it.    │
└──────────────────────────────────────────────────────────────────────────┘
```

**Predict it before you measure it.** The loop is blocked 5 × 50 ms = 250 ms of every second, 25% of the time. A `/health` request that arrives during a block waits for the rest of it: somewhere from 0 to 50 ms, evenly spread. So:

1. 75% of requests do not wait at all.
2. The chance of waiting longer than w ms is 0.25 × (1 − w / 50).
3. p90: 0.10 = 0.25 × (1 − w / 50), so w = 30 ms.
4. p99: 0.01 = 0.25 × (1 − w / 50), so w = 48 ms.

The prediction assumes the sleeps never overlap. The blocking calls arrive as Poisson traffic, so sometimes two come close together, and a request waits for both. `hol.py --model` adds the overlaps. It simulates the loop as the M/D/1 queue: Poisson arrivals, a fixed 50 ms of work, one server:

```bash
uv run python phase02_queueing/hol.py --model
```

```
model: 5/s of 50 ms blocks, loop blocked 25% of the time. /health wait p50 0.0 ms, p90 36.4 ms, p99 82.7 ms
```

With overlaps, the model's p99 rises from 48 ms to 82.7 ms.

One metric will matter below. The **event-loop lag** is how late a task that asked to wake in 10 ms actually wakes. The lab API measures it with a small task that sleeps 10 ms in a loop. Any step that holds the loop shows up in it.

**WRONG: a blocking call in `async def`.** `hol.py` runs two load generators at once, each in its own process: `/health` at 100 per second, and the slow endpoint at 5 per second. It then reads the API's own metrics.

```bash
uv run python phase02_queueing/hol.py --slow /blocking
```

```
slow path /blocking, 5/s of 50 ms; /health at 100/s
  /health n=  1760  mean   14.8 ms  p50   2.18 ms  p90   51.5 ms  p99    114 ms  p99.9    131 ms  max    136 ms  errors=0  sent 97/s
  API process CPU 3.4%, event-loop lag p99 109.4 ms, max 209.0 ms
  generator lag p99: /health 2.17 ms, slow path 2.51 ms
```

Four readings:

1. **The p90 is 51.5 ms and the p99 is 114 ms.** The no-overlap prediction was 30 and 48 ms. The M/D/1 model with overlaps gives 36.4 and 82.7 ms. So overlap explains part of the gap, and 31 ms of the p99 is still unexplained. Two candidates, not measured: the health checks that pile up during a sleep must then run one after another, and the laptop was busy with other work.
2. **The p50 is 2.18 ms.** Most requests never meet a sleep. The mean, 14.8 ms, describes nobody.
3. **The API's CPU was 3.4%.** The process was mostly asleep.
4. **The event-loop lag p99 was 109.4 ms.** That is the metric that shows the problem. Both generators had a lag p99 under 3 ms, so the run is valid.

**RIGHT: move the wait off the loop.** The same load, with the sleep run in a worker thread through `asyncio.to_thread`:

```python
# from phase02_queueing/api.py:188, the fix for /blocking. Comments shortened, logic unchanged
async def offloaded(request: Request) -> JSONResponse:
    m.requests += 1
    ms = float(request.query_params.get("ms", "50"))
    await asyncio.to_thread(time.sleep, ms / 1000)   # the loop stays free
    return JSONResponse({"slept_ms": ms})
```

```bash
uv run python phase02_queueing/hol.py --slow /offloaded
```

```
slow path /offloaded, 5/s of 50 ms; /health at 100/s
  /health n=  1760  mean   1.62 ms  p50   1.50 ms  p90   2.58 ms  p99   3.09 ms  p99.9   3.99 ms  max   10.4 ms  errors=0  sent 97/s
  API process CPU 4.2%, event-loop lag p99 2.1 ms, max 32.2 ms
  generator lag p99: /health 2.21 ms, slow path 2.58 ms
```

The `/health` p99 falls from 114 ms to 3.09 ms, and the loop lag p99 from 109.4 ms to 2.1 ms. The CPU is about the same, 4.2%. The sleep still happens 5 times per second, but in a worker thread, so the loop keeps serving `/health`.

**Why the CPU graph cannot show it.** A sleeping thread uses no CPU. A thread waiting in a blocking database driver or a synchronous HTTP call does the same. The CPU graph shows how busy the processor was. The loop can be unavailable while the processor is idle. What shows it is the event-loop lag, defined above.

asyncio can also log slow steps. Debug mode, turned on with `PYTHONASYNCIODEBUG=1`, logs any step that holds the loop longer than `loop.slow_callback_duration`, which defaults to 0.1 s at CPython 3.13. The research for this phase captured the line on this Mac:

```
WARNING:asyncio:Executing <Task finished name='Task-3' coro=<blocker() done, ...> result=None created at .../asyncio/tasks.py:410> took 0.155 seconds
```

Two limits. A 50 ms block, as in this lab, is under the 100 ms default and is never logged. And the warning names the task that held the loop, not the requests that waited for it.

**Offloading moves the wait into a pool.** `asyncio.to_thread` runs the call in asyncio's default thread pool. On this 8-core Mac that pool has 12 threads: `min(32, cpu_count + 4)` in CPython 3.13. Starlette runs a plain `def` endpoint in a different pool, anyio's thread limiter, with 40 threads by default. The research ran 41 requests of 200 ms each against a `def` endpoint. 40 finished in one wave, and the 41st waited for a second wave, 0.42 s in all. So the fix trades a blocked loop for a pool that can fill. Section 2.3 is about exactly that.

**The same thing on one connection.** HTTP/1.1 answers the requests on one connection in order. uvicorn's docs at 0.53.0 say it "will not start processing pipelined requests until each response has been dealt with in turn". RFC 9112, section 9.4, names this head-of-line blocking. It is why clients open several connections. Phase 1's E4 showed the client-side version: one connection at 77 requests per second made the p99 four times higher.

**The sentence to remember:** an asyncio event loop is one queue, so one blocking call inside an async handler delays every request in flight. The CPU graph stays low while it happens.

**The trap:** trusting CPU utilisation to show overload in an async service. Here the API's CPU was 3.4% while `/health`, which does no work, had a p99 of 114 ms. Watch the event-loop lag.

**Try this now:** the loop blocked 10 × 20 ms = 20% of the time, in shorter pieces. Predict the p90 and p99 of `/health` with the no-overlap arithmetic above: 10 ms and 19 ms. Then run `uv run python phase02_queueing/hol.py --model --slow-ms 20 --slow-rate 10`, which gives 11.8 and 28.7 ms with overlaps. Last, run it live with `uv run python phase02_queueing/hol.py --slow /blocking --slow-ms 20 --slow-rate 10`, and see how far the measurement sits above the model.

---
## 2.3 — Pools that fill (the wait rises long before the errors come)

Why this matters: a connection pool is a small queue in front of a resource. It fills at a load the CPU graph never warns about. When it fills, the first sign is time spent waiting for a connection, and most dashboards do not show that number. Errors come much later, if ever.

**Answer this first.** A Python API calls a database through a pool of 5 connections. Each query holds its connection for 100 ms. At what request rate is the pool full? At 45 requests per second, what does the API's CPU show, and how long does the slowest 1% of requests wait for a connection?

**The mechanism: a pool is a queue with several servers.** Each connection is a server. Each request holds one for its hold time S, and waits if all are busy. With c connections the pool can serve c / S requests per second:

```
capacity = c / S = 5 / 0.100 s = 50 requests per second
offered load ρ = rate × S / c       at 45/s: 45 × 0.1 / 5 = 90%
```

With Poisson arrivals and exponential hold times this is the M/M/c queue. The Erlang C formula gives the chance that a request must wait:

```
a = rate × S                           the offered load, in connections
B(0) = 1, B(x) = a·B(x−1) / (x + a·B(x−1)) for x = 1 .. c    the Erlang B recursion
C(c, a) = B / (1 − ρ(1 − B)) = P(a request waits)
P(wait > t) = C(c, a) × e^(−(c/S − rate) × t)
```

`capacity.py` computes it. It uses this stable recursion, from Iversen's ITU Teletraffic Engineering Handbook, and its self-test checks five values from Whitt's 1993 table for M/M/c.

**Where the knee is.** In this course the knee is the load where the wait starts to rise faster than the load itself. Erlang C puts it for this pool between 80% and 90%. From 40 to 45 requests per second, 12.5% more load, the predicted p99 wait more than doubles: from 401 to 867 ms.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One request to /pooled: where its time goes                              │
├──────────────────────────────────────────────────────────────────────────┤
│ request ──► handler ──► wait for one of 5 connections ──► query 100 ms   │
│                          │                                               │
│                          │  all 5 busy: the request waits here           │
│                          │  CPU used while waiting: none                 │
│                          ▼                                               │
│             pool wait. The number nobody graphs                          │
│                                                                          │
│ The pool is full at 50/s. The event loop's CPU is about 3 ms per         │
│ request, so the CPU would be full near 330/s. The pool fills first.      │
└──────────────────────────────────────────────────────────────────────────┘
```

**Measured: the pool bends while the CPU idles.** The lab API's `/pooled` makes one call through an httpx client limited to 5 connections. The backend holds each for 100 ms on average. The API measures the pool wait with httpcore's trace hooks: the time from the call to the moment the request is written on a connection. httpx itself records no wait time. `sweep.py` loads the API open-loop at each rate for 20 s, and applies Phase 1's validity rule to every run. The first run at 20 per second had a generator lag p99 of 15.53 ms, so by the rule it was run again:

```bash
uv run python phase02_queueing/sweep.py --rates 20 30 40 45 48
```

| Rate | Offered pool load | Started/s | API CPU | Pool wait p99 | Erlang C p99 | Client p99 | Errors | Generator lag p99 |
|---|---|---|---|---|---|---|---|---|
| 20/s | 40% | 18 | 5% | 88 ms | 60 ms | 476 ms | 0 | 2.46 ms |
| 30/s | 60% | 27 | 8% | 227 ms | 158 ms | 542 ms | 0 | 2.48 ms |
| 40/s | 80% | 37 | 12% | 360 ms | 401 ms | 586 ms | 0 | 2.39 ms |
| 45/s | 90% | 42 | 13% | 501 ms | 867 ms | 726 ms | 0 | 2.27 ms |
| 48/s | 96% | 44 | 19% | 663 ms | 2251 ms | 835 ms | 0 | 2.33 ms |

"Offered pool load" is computed, rate × hold / connections. "Started/s" is measured: the requests the API began per second.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Pool of 5, 100 ms holds: offered pool load against API CPU. Lab part P   │
├──────────────────────────────────────────────────────────────────────────┤
│  20/s  pool ████████████████                          40%                │
│        CPU  ██                                         5%                │
│  30/s  pool ████████████████████████                  60%                │
│        CPU  ███                                        8%                │
│  40/s  pool ████████████████████████████████          80%                │
│        CPU  █████                                     12%                │
│  45/s  pool ████████████████████████████████████      90%                │
│        CPU  █████                                     13%                │
│  48/s  pool ██████████████████████████████████████    96%                │
│        CPU  ████████                                  19%                │
│                                                                          │
│ The pool reaches its knee while the CPU stays under a fifth              │
└──────────────────────────────────────────────────────────────────────────┘
```

Three readings:

1. **The CPU never passed 19%.** A CPU alert at 70% would have stayed silent at every rate.
2. **The client's p99 reached 835 ms at 48 per second, with zero errors.** Most of it was waiting for a connection.
3. **Erlang C was within a factor of two up to 80% load.** At 90% and 96% the measured p99 was below the prediction, at 96% about a third of it. That is the short-run effect of Phase 1, section 1.3.

**Past the limit, the wait climbs and the errors stay at zero.** `sweep.py --timeline` sends 60 requests per second into the 50 per second pool for 40 s. It reads the API's metrics every second, and runs the load generator in its own process. Selected seconds from the saved log:

```
   t started/s  waiting  pool wait p99  timeouts   CPU  loop lag p99
   1        48        8         126 ms         0   16%       14.4 ms
   2        57       20         402 ms         0   21%        2.6 ms
   5        74       33         457 ms         0   32%        2.1 ms
  10        67       78        2165 ms         0   81%        2.7 ms
  14        74      135        3875 ms         0   97%        4.4 ms
  16        66      156        5493 ms         0   94%        3.9 ms
  18        64      190        6263 ms         0   98%       20.4 ms
  20        60      214        8552 ms         0   96%        8.1 ms
  29        78      396       14762 ms         0   99%        7.6 ms
  30        54      396       11092 ms         0   99%        6.2 ms
  36        58      396       22118 ms         0   99%        6.8 ms
  40        49      395       20120 ms         0   99%        7.6 ms
  45        35      396       24805 ms         0   98%        9.0 ms
  46         0        0       30786 ms         0   99%        6.4 ms
  50         0        0       27853 ms         0   97%        4.7 ms
  54         0        0       13591 ms         0   17%        2.1 ms
  55         0        0           0 ms         0    1%        2.3 ms
```

The generator's lag p99 for the run was 2.21 ms, so it is valid. Four readings:

1. **The requests waiting for a connection rose every second, by up to 34, until they reached 396 at second 29.** 396 waiting, plus the few in use, filled the generator's 400 connections. From then on, new requests waited inside the generator instead.
2. **The pool wait p99 passed 5 s at second 16, and 22 s at second 36.**
3. **The timeouts column stayed at 0 for the whole run.**
4. **The CPU rose from 16% to 99% by second 18 and stayed there**, while only about 50 requests per second were starting. At light load a request cost about 3 ms of CPU. Here each one cost nearer 20 ms. Section 2.4 measures why.

The generator stopped sending at 40 s. Requests already queued in its own connections kept arriving until second 45, and the API finished the last of them at second 55.

**Why the timeouts never came.** httpx documents its pool timeout, 5 s by default, as the maximum time to wait for a connection. So waits of 22 s should have raised `httpx.PoolTimeout`. `pool_timeout.py` tests it directly: 400 requests at once through 5 connections held 100 ms each, with the 5 s pool timeout.

```bash
uv run python phase02_queueing/pool_timeout.py
```

```
400 requests, 5 connections held 100 ms, pool timeout 5 s
  results: {'ok': 400}
  longest total time 9.23 s, longest single pool wait 0.49 s
  392 requests entered the wait more than once, one of them 66 times
```

Every request succeeded, and the last one waited 9.23 s in total. No single wait was longer than 0.49 s. The reason is in httpcore 1.0.9, the library under httpx. When a connection frees, `_assign_requests_to_connections` hands that one free connection to every waiting request in the same pass. One of them uses it. The others find it taken, catch `ConnectionNotAvailable`, clear their connection and wait again, with a new timer. The loop is in `handle_async_request` in `httpcore/_async/connection_pool.py`. So the pool timeout limits each wait, not the total.

It still fires when no connection frees up for the whole timeout. With holds of 6 s, longer than the 5 s timeout, half the requests failed:

```
10 requests, 5 connections held 6000 ms, pool timeout 5 s
  results: {'ok': 5, 'PoolTimeout': 5}
  longest total time 6.04 s, longest single pool wait 5.01 s
```

So with httpcore 1.0.9, a full pool raises `PoolTimeout` only when every connection is held longer than the timeout. With short holds, as in most services, the wait grows without an error.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ What the dashboard shows as the pool fills, in order                     │
├──────────────────────────────────────────────────────────────────────────┤
│ 1. requests waiting for a connection    rises first, from the knee       │
│ 2. pool wait, p99                       rises with it                    │
│ 3. request latency, p99                 rises, as pool wait plus query   │
│ 4. CPU                                  stays low: waiting uses none     │
│ 5. errors                               flat. A timeout per wait may     │
│                                         never fire. A timeout on the     │
│                                         whole request would              │
└──────────────────────────────────────────────────────────────────────────┘
```

**Not every pool behaves like this.** The research for this phase read each library's pool at its release tag. There are three kinds, and the kind decides what you see when it fills:

| Pool, version | Size by default | When it is full |
|---|---|---|
| httpx 0.28.1 | 100 connections per client, across all hosts | waits. The 5 s pool timeout restarts on each wait, and fires only when no connection frees for 5 s |
| SQLAlchemy 2.0 `QueuePool` | 5 + 10 overflow | waits up to 30 s, then raises `TimeoutError` "QueuePool limit of size 5 overflow 10 reached" |
| asyncpg 0.31 `create_pool` | 10 | waits forever, unless you pass a timeout to `acquire` |
| asyncio default executor, CPython 3.13 | min(32, CPUs + 4), 12 on this Mac | queues forever |
| anyio thread limiter, Starlette `def` endpoints | 40 threads | queues forever |
| redis-py 8.1 `ConnectionPool` | 100 | refuses at once with `MaxConnectionsError` |

For a pool that waits, the error rate stays flat while the wait climbs. For redis-py's default pool, the errors come first and the wait never rises. "A full pool shows as rising wait at a flat error rate" is true only for pools that wait, and they are most of this table. It is also true only while the pool is the resource that fills first. That holds when its limit, connections divided by hold time, is below the CPU's limit, one over the CPU per request. Here that is 50 per second against about 330. Section 2.5 shows larger pools where it does not hold.

**What to graph.** Every pool needs three numbers: connections in use, requests waiting, and the wait time as a histogram. PgBouncer's `maxwait` is the age of the oldest waiting client. Its docs say: "If this starts increasing, then the current pool of servers does not handle requests quickly enough". GitLab.com, in a 2022 analysis, sorted a day of PgBouncer stats-log lines by their wait. On its main cluster's replicas, clients waited up to 95 s for a connection. The research read those as averages per 60 s period, assuming the 2022 log format matched today's. The issue recommends graphing `maxwait`. OpenTelemetry's semantic conventions, v1.44.0, name database pool metrics `db.client.connection.wait_time` and `db.client.connection.pending_requests`, still marked Development. OpenTelemetry has no HTTP client metric for pool wait time, so for httpx you time the wait yourself, as the lab API does.

**The sentence to remember:** a small pool that waits fills before the CPU does. It shows it first as waiting requests and pool wait, at a flat error rate. Graph the wait, not only the errors.

**The trap:** trusting a pool timeout to turn a full pool into errors. httpx's 5 s pool timeout let requests wait 9.23 s here without a single error, and 22 s in the overload run. Put a deadline on the whole request instead, for example `asyncio.timeout`.

**Try this now:** run `uv run python phase02_queueing/capacity.py --pool 5 --hold-ms 100 --rate 20 30 40 45 48`. Compare its p99 wait column with the measured pool wait p99 in the table above. Then run it with `--pool 10`: how much more load does the same p99 allow?

---
## 🧪 Hands-on lab — part A

**Run status:** every command below was executed on the author's machine on 2026-09-25: an Apple M2 with 8 GB, macOS 15.7.8, CPython 3.13.3 through uv. Other programs kept the load average between 2.5 and 7.3, and each log records it. Each "Expected" line is copied from `runs/lab2-*.log`. Your numbers will differ. The relations between them should not.

All commands run from `elite-performance/code/`. `runs/lab2.sh` runs every live part and starts its own backend and API for each run. Each part runs alone, for example `bash runs/lab2.sh H`.

- [ ] **E1 (offline).** The fan-out formula against a simulation.
  - Run: `uv run python phase02_queueing/fanout.py`, then `uv run python phase02_queueing/fanout.py --self-test`.
  - Expected: `fan-out   100: formula  63.4% slow, simulated  63.7%; p50 100 ms, p99 100 ms`, and `fan-out    50: formula  39.5% slow`.
  - Teaches: a request is as slow as its slowest call.

- [ ] **E2 (offline).** Hedged requests, and what they do to the median.
  - Run: `uv run python phase02_queueing/fanout.py --hedge-ms 10`.
  - Expected: at fan-out 50, `hedged at 10 ms: p99 15 ms, 1.00% extra calls`. The self-test prints `hedged at 10 ms: 1.03% slow, p50 15 ms, p99 100 ms` at fan-out 100, where the unhedged p50 is 100 ms.
  - Teaches: a hedge cuts the tail for about 1% more calls. A hedged call ends at the hedge delay plus one fast call, never at the fast call alone.

- [ ] **E3 (local).** Fan-out on a real Python caller.
  - Run: `bash runs/lab2.sh F`. About 3 minutes.
  - Expected: `fan-out   10 at 10.00/s:   76 requests,  14.5% took >= 100 ms (formula   9.6%)`, with `1.95 ms per call`. `fan-out   50 at  2.00/s:   70 requests, 100.0% took >= 100 ms (formula  39.5%)`, with `3.81 ms per call`. Every line ends `valid`.
  - If the API holds 100% CPU and the run never ends, the call budget was raised. Keep `--live-calls-per-s` at 100 or below.
  - Teaches: in Python a fan-out costs the caller CPU per call, on one event loop, about 2 ms per httpx call on this machine.

- [ ] **E4 (break-it, local).** One blocking call in an async handler.
  - Run: `bash runs/lab2.sh H`. About 1 minute.
  - Expected, blocking: `/health n=  1760 ... p50   2.18 ms  p90   51.5 ms  p99    114 ms`, `API process CPU 3.4%, event-loop lag p99 109.4 ms`. Offloaded: `p99   3.09 ms`, `event-loop lag p99 2.1 ms`. Model: `p90 36.4 ms, p99 82.7 ms`.
  - What broke: `time.sleep` held the only event loop. The CPU stayed under 4% while it happened.
  - Teaches: watch the event-loop lag, not the CPU.

- [ ] **E5 (offline).** Predict a pool with Erlang C.
  - Run: `uv run python phase02_queueing/capacity.py --pool 5 --hold-ms 100 --rate 20 30 40 45 48`, then `uv run python phase02_queueing/capacity.py --self-test`.
  - Expected: `pool of 5, hold 100 ms: capacity 50/s`. The self-test checks five values of Whitt's 1993 table and prints `Erlang C checks against Whitt 1993 Table 1 passed`.
  - Teaches: a pool is an M/M/c queue, and its knee can be predicted.

- [ ] **E6 (break-it, local).** Fill the pool, and look for the errors.
  - Run: `bash runs/lab2.sh P T Q`. About 6 minutes.
  - Expected: the sweep's CPU stays at `5%` to `19%` while the client p99 reaches `835 ms`. In the timeline the pool wait p99 passes 5 s at second 16, and the `timeouts` column stays `0`. `pool_timeout.py` prints `results: {'ok': 400}` and a longest total time near 9 s. With 6 s holds it prints `results: {'ok': 5, 'PoolTimeout': 5}`.
  - What broke: the 5 s pool timeout never fired while connections kept freeing, because httpcore restarts it on every wait.
  - Teaches: a full pool shows as waiting, not as errors, and a timeout per wait is not a deadline.

---

## 🔍 Check it yourself

1. Open `phase02_queueing/api.py:146`. This is `trace`, the hook that measures pool wait. It stops the clock at the first `connect_tcp` or `send_request_headers` event. What would the metric include if it stopped at the response instead?

2. Open `phase02_queueing/fanout.py:74`. This line is the hedge. It takes the earlier of the first call and a second call sent after `hedge_ms`. At fan-out 100, why does the hedged p50 end at 15 ms, and not at the 5 ms of a fast call?

3. Open `phase02_queueing/pool_timeout.py:69`. It wraps httpcore's `wait_for_connection` to count every entry. Then read `handle_async_request` in httpcore 1.0.9's `_async/connection_pool.py`, the `while True` loop. Which exception sends a request back into the wait, and with what timeout?

4. In any async Python service you own, search for blocking calls in async handlers:

   ```bash
   grep -rn -A30 "async def" <your repo>/ | grep -E "time\.sleep|requests\.(get|post)|\.execute\(|open\("
   ```

   For each hit, decide whether it holds the event loop, and how long it can hold it at its worst.

---

## ✅ Checkpoint 2A — answer in your own words

1. **Explain, with the arithmetic.** A request fans out to 100 backends, each slow 1% of the time. (a) What fraction of requests are slow? (b) What changes when the fan-out is halved? (c) Why is a request that fans out slow far more often than any one of its calls?

2. **This is broken.** A FastAPI service shows p99 120 ms on `/health`, which does nothing. CPU is 3%. Memory is flat. There are no errors. What is the likely cause, how do you confirm it from metrics alone, and what is the fix?

3. **Show the arithmetic.** A pool of 10 connections, each held 50 ms on average, gets 160 requests per second. (a) What is its capacity and utilisation? (b) Use Erlang C, or `capacity.py`, to give P(wait) and the p99 wait. (c) What happens at 180 per second?

4. **A colleague says:** "Our httpx client has a 5 second pool timeout, so if the pool ever fills we will see `PoolTimeout` errors in the logs". Argue for or against, with numbers from section 2.3.

5. **Demonstrate.** An endpoint uses a pool of 5 connections held 100 ms. Describe the load curve you would draw for it: the axes, the knee, the resource that saturates, and the two metrics that show it before any error.

<details>
<summary>Answer sketches</summary>

1. (a) 1 − 0.99^100 = 0.634, so 63.4% of requests are slow. (b) 1 − 0.99^50 = 0.395: 39.5%, not half. (c) The request ends when its last call ends, so it is fast only if all 100 calls are fast: 0.99^100 = 36.6%. `fanout.py` simulates 63.7%. In Python there is a second cost: about 2 ms of caller CPU per call. So a fan-out of 50 costs about 100 ms before any backend is slow.

2. A blocking call in an async handler: a sync database driver, `requests`, `time.sleep`, a large JSON encode. The loop is one queue, so everything behind the call waits, and a sleeping thread uses no CPU. Confirm it with event-loop lag: in the lab, lag p99 was 109.4 ms while CPU was 3.4%. asyncio debug mode logs steps over 100 ms by default, so a 50 ms block is not logged. Fix: `await asyncio.to_thread(...)`, an async driver, or a `def` endpoint. Remember that each fix uses a thread pool of its own.

3. (a) Capacity = 10 / 0.05 s = 200 per second. Utilisation = 160 × 0.05 / 10 = 80%. (b) `capacity.py --pool 10 --hold-ms 50 --rate 160` gives P(wait) 40.9%, mean wait 10.23 ms and p99 wait 92.79 ms. (c) At 180 per second: 90% busy, P(wait) 66.9%, p99 wait 210.14 ms. That is 12.5% more load for more than twice the p99 wait.

4. Against, for short holds. httpcore 1.0.9 applies the pool timeout to each wait. Each released connection wakes every waiter, and all but one wait again with a new timer. In the lab, 400 requests through 5 connections with a 5 s pool timeout all succeeded. The last waited 9.23 s, and one request entered the wait 66 times. The overload timeline showed pool waits past 22 s with zero timeouts. The timeout does fire when no connection frees for 5 s: with 6 s holds, 5 of 10 requests failed. Put a deadline on the whole call, for example `asyncio.timeout`, and graph the pool wait.

5. X axis: offered load in requests per second, open-loop. Y axes: client p99, pool wait p99, requests waiting, CPU, errors. The pool limit is 5 / 0.1 s = 50 per second. Erlang C puts the knee between 40 and 45 per second, 80% to 90% offered load. The pool saturates first. The CPU stays between 5% and 19%. Before any error, the requests-waiting count and the pool-wait p99 rise. In the lab, the pool-wait p99 went from 88 ms at 20/s to 663 ms at 48/s, with zero errors.

</details>

---

## References & Further Learning — part A

Every URL below was fetched on 2026-09-25 and returned HTTP 200.

**Fan-out**

- **Jeffrey Dean and Luiz André Barroso, "The Tail at Scale", CACM 2013** — https://www.barroso.org/publications/TheTailAtScale.pdf
  Focus on: page 75, the fan-out figure and the 63% example. Table 1, the real fan-out service. Page 77, hedged requests and the 1,800 ms to 74 ms result. Table 2, tied requests. The paper gives no hardware or load for its numbers.
- **Vulimiri et al., "Low Latency via Redundancy", CoNEXT 2013** — https://arxiv.org/pdf/1306.3707
  Focus on: Theorem 1, full replication helps the mean only below 33% load for exponential service times. Read it before you hedge on a busy service.

**Head-of-line blocking**

- **Python docs, "Developing with asyncio", 3.13** — https://docs.python.org/3.13/library/asyncio-dev.html
  Focus on: "Debug Mode", with the 100 ms slow-callback threshold, and "Running Blocking Code". Short, and the source of the one-queue rule.
- **uvicorn 0.53.0, "Server behavior"** — https://raw.githubusercontent.com/Kludex/uvicorn/0.53.0/docs/server-behavior.md
  Focus on: pipelined requests, handled one at a time, and "Concurrency and backlog".
- **RFC 9112, HTTP/1.1** — https://www.rfc-editor.org/rfc/rfc9112.txt
  Focus on: section 9.3.2, pipelining, and section 9.4, where it names head-of-line blocking.
- **anyio 4.15.1, `_backends/_asyncio.py`** — https://raw.githubusercontent.com/agronholm/anyio/4.15.1/src/anyio/_backends/_asyncio.py
  Focus on: `current_default_thread_limiter`, `CapacityLimiter(40)`. The pool Starlette's `def` endpoints use.

**Pools**

- **httpcore 1.0.9, `_async/connection_pool.py`** — https://raw.githubusercontent.com/encode/httpcore/1.0.9/httpcore/_async/connection_pool.py
  Focus on: `handle_async_request`, its `while True` loop and `ConnectionNotAvailable`, and `_assign_requests_to_connections`. Everything section 2.3 measured is in these two functions.
- **httpx 0.28.1, "Timeouts"** — https://raw.githubusercontent.com/encode/httpx/0.28.1/docs/advanced/timeouts.md
  Focus on: the pool timeout's documented meaning. Compare it with what `pool_timeout.py` measures.
- **SQLAlchemy, error 3o7r** — https://docs.sqlalchemy.org/en/20/errors.html#error-3o7r
  Focus on: why "QueuePool limit ... reached" happens, including a thread pool larger than the connection pool.
- **PgBouncer, "Usage", `SHOW POOLS`** — https://www.pgbouncer.org/usage.html
  Focus on: `cl_waiting` and `maxwait`, the two numbers that show a full pool before errors.
- **GitLab.com production issue 7984, pgbouncer pool wait time, 2022** — https://gitlab.com/gitlab-com/gl-infra/production/-/work_items/7984
  Focus on: pool wait as the saturation signal, in a real fleet. The numbers are per-minute averages from PgBouncer's stats log.
- **OpenTelemetry semantic conventions v1.44.0, database metrics** — https://raw.githubusercontent.com/open-telemetry/semantic-conventions/v1.44.0/docs/db/database-metrics.md
  Focus on: "Connection pools": `db.client.connection.wait_time` and `pending_requests`. Still marked Development.
- **Villy B. Iversen, Teletraffic Engineering Handbook, ITU, 2001 draft** — https://www.itu.int/dms_pub/itu-d/opb/stg/D-STG-SG02.16.1-2001-PDF-E.pdf
  Focus on: equations 7.26 and 7.27, the stable Erlang B recursion, and 12.9, Erlang C from Erlang B.
- **Ward Whitt, "Approximations for the GI/G/m Queue", 1993** — https://www.columbia.edu/~ww2040/ApproxGIGm1993.pdf
  Focus on: Table 1, the exact M/M/m values `capacity.py` tests against, and Example 2.

---

## Cheatsheet — part A

```
FAN-OUT
  P(slow) = 1 − (1 − p)^N        p = 1%: N 10 → 9.6%, 50 → 39.5%, 100 → 63.4%
  hedge after 10 ms               1% slow call → 0.01%. ~1% more calls. Hedged
                                  call ends at delay + one fast call: p50 100 → 15 ms
  Python caller                   ~2 ms CPU per httpx call here, ~3.8 ms at fan-out
                                  50 and 100, all on ONE event loop

HEAD-OF-LINE
  event loop = one queue          a blocking call stalls every request in flight
  measure                         event-loop lag, not CPU: 3.4% CPU, lag p99 109 ms
  asyncio debug mode              logs steps > 0.1 s only
  fixes                           asyncio.to_thread (12 threads here), async driver,
                                  def endpoint (anyio: 40 threads). Each is a pool

POOLS
  capacity = connections / hold   utilisation = rate × hold / connections
  Erlang C                        P(wait); P(wait > t) = C × e^(−(c/S − rate) t)
  small pool that waits           wait rises first, errors stay flat, while its
                                  limit c/S is below the CPU's 1/(CPU per request)
  pool that refuses               errors at once (redis-py ConnectionPool)
  httpx pool timeout              per wait, restarts: 400 queued, 5 s → 0 errors.
                                  Fires only if no connection frees for 5 s
  graph                           in use, waiting, wait-time histogram, per pool
```

Part B covers what happens past the limit, sections 2.4 and 2.5: backpressure, the queue that feeds itself, and the capacity envelope.

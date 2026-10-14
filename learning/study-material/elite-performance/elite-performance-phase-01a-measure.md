# Phase 1A — Measurement before optimisation: what one run shows

**The question this phase answers:** why do most benchmarks report a number that production will never show, and how do you write one that does not?

Here is an example. A load test says a service handles 2,000 requests per second at a p99 of 40 ms. Production sees 800 requests per second and a p99 of 900 ms. Nobody can explain the difference. The example is invented, but every part of it happens in this phase on your own laptop.

The test was not wrong about what it measured. It measured something else. Its generator waited for each reply before it sent the next request. When the service slowed down, the generator slowed down with it. The slow seconds were never recorded. The number was real, and it was useless.

Every later phase of this course measures something: a saturation point, a profile, a race, a layer. If the measurement is wrong, the lesson drawn from it is wrong. So this phase comes before any optimisation. It teaches four ideas. Each is a claim you could get wrong today:

1. **A closed-loop generator sends the next request only after the last one returns.** So a stall is recorded once, not once for every request that would have waited during it.
2. **A latency result is a distribution with run-to-run variance.** One run, or one percentile without its spread, cannot show that a change helped.
3. **A short run of a busy service reports too low a p99, and a different one each time.** The rare long queues that set the tail seldom fit into a short run. The first seconds also differ from the rest, in either direction, because every run starts with an empty queue. The CPython interpreter itself is warm after about one request.
4. **A prediction written before the run turns a number into a finding.** The gap between prediction and measurement points at the thing you did not model.

Phase 1 is split into two documents. This one teaches the first and third ideas: how to measure one run honestly. Part B teaches the second and fourth: whether a change is real, and how to predict the result before the run.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, this document: what one run shows                                │
│  1.1  The distribution of one endpoint — what one run really returns     │
│  1.2  Open-loop versus closed-loop     — the seconds a closed loop never │
│                                          records                         │
│  1.3  Warm-up and the first minute     — what is cold, and for how long  │
│  Lab: E1 to E5                                                           │
│                                                                          │
│ PART B, the next document: is it real, and was it predicted              │
│  1.4  Baseline, one change, repeat     — is a change real                │
│  1.5  The prediction sheet             — write the number down first     │
│  Lab: E6 to E11                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**What this part assumes.** Three sections of the inference-internals course are used here and not taught again. If you have not read them yet, the three-sentence version of each is enough.

- **inference-internals 4.3, "Benchmarking it".** Compare systems with one client and pinned settings. Each tool measures in its own way, so two tools compare the tools, not the systems. Here the one client is `loadgen.py`, and the pinned settings are in `runs/lab.sh`.
- **inference-internals 5.4, the percentile ladder.** One percentile hides the shape of the tail. The Google SRE Book states a ladder: 90% of requests under X, 99% under 10X, 99.9% under 100X. Every run in this phase prints a ladder of p50, p90, p99, p99.9 and max.
- **inference-internals 6.1, Little's law and the knee.** Little's law, L = λW, links the requests in a system, their arrival rate, and the time each one spends there. The utilisation ρ is the share of time the server is busy. This course writes it as "79% busy". For one server, the mean wait in the queue is ρ / (1 − ρ) service times: 4 at 80% busy, 19 at 95%. The mean time in the system, wait plus service, is 1 / (1 − ρ) service times: 5 and 20. The knee is the load where that curve starts to climb fast.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. Every number in this phase was measured on 2026-09-25 on an Apple M2 with 8 GB of memory, macOS 15.7.8, CPython 3.13.3 through uv 0.6.11. The packages are pinned in `pyproject.toml`: hdrhistogram 0.10.7, uvicorn 0.53.0, starlette 1.7.0, httpx 0.28.1 and numpy 2.5.3.

The measurements ran in three sessions, and their conditions differ:

| Session | Lab parts | Conditions | Log |
|---|---|---|---|
| 05:13 to 05:27 | A, B, D, E | on battery, 37% at 05:09, noted by hand from `pmset`. Load not recorded | `runs/lab.log` |
| 12:23 to 12:31 | C | other programs running, battery not recorded | `runs/lab-c.log` |
| 13:04 | W | charging, 88%, load average 6.1 | `runs/lab-w.log` |

`runs/lab.sh` now prints the conditions at the start of every run, so your logs record them too. Your numbers will differ from these. The shape of each result should not.

Setup:

```bash
cd ~/Desktop/project/study-material/elite-performance/code
uv sync
uv run python shared/latency.py --self-test
```

The last line should print `self-test passed`.

Time for part A: 1 to 1.5 hours. About 2 to 3 minutes of that is waiting for load runs.

---
## 1.1 — The distribution of one Python endpoint (what one run really returns)

Why this matters: a load test does not return a number. It returns a distribution of latencies. Every later lab in this course reports one, so you must be able to read one and know how far to trust each part of it.

**Answer this first.** A Python endpoint does 10 ms of work on average. It gets 48 requests per second, so it is busy about half the time. Its mean latency is about 20 ms. What is its p99? Write a number down.

**The service this course measures.** `phase01_measure/service.py` is a Starlette app on uvicorn, with one worker and one event loop. Its `/work` endpoint draws a service time and spends it as CPU work on the event loop:

```python
# from phase01_measure/service.py:66 and :90. Docstring removed and two comments added, logic unchanged
def spin(seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        pass

async def work(request: Request) -> JSONResponse:
    s = draw()          # exponential, mean 10 ms, from the stream named "service"
    spin(s)             # no await: nothing else runs on this loop meanwhile
    return JSONResponse({"service_ms": round(s * 1000, 3)})
```

The handler never awaits while it works. So the process is one queue with one server. While one request runs, every other request waits. That is how a sync-heavy async handler behaves in production: JSON encoding, a template, a Pydantic model of a large payload. It also makes the queueing arithmetic of section 1.5 hold.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One uvicorn worker, one event loop, one queue                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  requests ──► socket buffers ──► event loop ──► handler: spin 10 ms      │
│  arrive at    waiting requests   runs ONE        on average, no await    │
│  48/s         sit here           callback at                             │
│                                  a time                                  │
│                                                                          │
│  latency = wait in the queue + service time                              │
│  service time: exponential, mean 10 ms, p50 6.9 ms, p99 46 ms            │
│  utilisation at 48/s: 48 × 10.25 ms = 0.49                               │
└──────────────────────────────────────────────────────────────────────────┘
```

The 10.25 ms is the 10 ms of work plus 0.25 ms of framework and network overhead. Section 1.3 shows how it was measured.

**What one run returned.** Lab E7, in part B, ran the service at 48 requests per second for 25 seconds, open-loop. It kept the first 2 seconds apart. Its arrivals were Poisson: each request arrives independently of the others, at a steady average rate, so arrivals sometimes bunch up, as real users do. The load generator, `loadgen.py`, prints one ladder line per run:

```
open 48/s poisson, timer=due, raw  n=  1063  mean   21.5 ms  p50   15.9 ms  p90   42.9 ms  p99   92.8 ms  p99.9   98.3 ms  max    103 ms  errors=0  sent 46/s
```

The p99 is 92.8 ms. That is 4.3 times the mean and 5.8 times the median. Here is the same run as a distribution:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 1,063 requests, 48/s, 10 ms exponential service. Lab E7, run 1           │
├──────────────────────────────────────────────────────────────────────────┤
│   0-10 ms  ████████████████████████████████████  349                     │
│  10-20 ms  █████████████████████████████         283                     │
│  20-30 ms  ███████████████████                   181   ◄ mean 21.5 ms    │
│  30-40 ms  ████████████                          113                     │
│  40-50 ms  ██████                                 56                     │
│  50-60 ms  ██                                     22                     │
│  60-70 ms  ██                                     15                     │
│  70-80 ms  ██                                     17                     │
│  80-90 ms  █                                      13                     │
│ 90-100 ms  █                                      13   ◄ p99 92.8 ms     │
│   100+ ms  ▏                                       1   ◄ max 103 ms      │
└──────────────────────────────────────────────────────────────────────────┘
```

The shape is the lesson. Most requests are fast. A long, thin tail holds the requests that arrived behind a long one. The mean, 21.5 ms, is not a typical request. Half the requests took under 15.9 ms, and one in a hundred took over 92.8 ms.

**How much the tail rests on.** A p99 is decided by the slowest 1% of samples. This run has 1,063 samples, so its p99 rests on 10 of them:

```
92.9  93.5  93.5  94.2  95.6  96.1  96.8  97.3  98.3  103.4   ms
```

Ten values are not much. Run it again and a different ten appear. So a p99 from one run of about a thousand requests is an estimate with a wide error. Section 1.4 measures how wide. A simple rule: count the samples above the percentile you report. Below about ten, do not report that percentile at all. For a p99.9 here, only one sample is above it.

**Why an HDR histogram.** Storing every latency works for one run. It stops working for a long test, or for merging runs from many processes. An HDR histogram, "high dynamic range", stores counts in buckets whose width grows with the value. It keeps every value within a fixed relative error, however rare the value is.

`shared/latency.py` sets it up once for the whole course:

- range 1 µs to 60 s, so a stalled request and a timed-out one both fit
- 3 significant digits, so every value is kept within 0.1% of itself
- memory: 17,408 counters of 8 bytes, 139,264 bytes. That is fixed, whatever the run length

**WRONG: trust the histogram to keep every value.** The Python package `hdrhistogram` 0.10.7 drops a value above its range without an error. Its `record_value` returns `False` and records nothing:

```python
# WRONG: a 90 s request in a 1 µs to 60 s histogram
h = HdrHistogram(1, 60_000_000, 3)
for _ in range(999):
    h.record_value(10_000)          # 999 requests at 10 ms
h.record_value(90_000_000)          # one request that took 90 s
```

```
returned False | count 999 | max 10.007 ms
```

The one request that mattered is gone. The max says 10 ms.

**RIGHT: clamp to the top of the range, so the slow request is kept as the largest value.** This is `shared/latency.py:47`:

```python
def _us(seconds: float) -> int:
    # Clamp instead of failing: a value past 60 s is still a slow request,
    # and dropping it would hide exactly the sample that matters.
    return max(LOWEST_US, min(HIGHEST_US, round(seconds * 1_000_000)))
```

```
count 1000 max 60030.975 ms
```

The count is right, and the max says "60 s or more". You lose the exact value of a request slower than 60 s. You never lose the request.

**The answer to the question.** The p99 was 92.8 ms, about 4.3 times the mean. For this kind of queue the ratio is not an accident. Section 1.5 predicts 92.9 ms before the run.

**The sentence to remember:** a load test returns a distribution. Read its ladder, count the samples behind each percentile, and never report a mean alone.

**The trap:** a histogram sized too small drops the slowest requests without an error, and the max then looks healthy. Size the range for the longest stall you can imagine, or clamp as `record` does.

**Try this now:** run `uv run python shared/latency.py --self-test`. It records one sample at each of 1 to 10,000 ms. Then it checks the p50 against 5,000 ms and the p99 against 9,900 ms, each within 0.1%. The histogram returns 5,001 and 9,904. That is the 0.1% promise at work.

---
## 1.2 — Open-loop versus closed-loop load (the seconds a closed loop never records)

Why this matters: many load tools are closed-loop by default. A closed-loop result can say "p99 1 ms" about a service that stopped for five seconds. If you do not know why, you will release a change based on that number.

**Answer this first.** A service answers every request in 1 ms. A test sends 100 requests per second for 100 seconds. At t = 50 s the service stops completely for 5 s. One client sends a request, waits for the reply, waits 9 ms, and sends again. What p99 does this client report? Write your number down before you read on.

**Two kinds of generator.**

- A **closed-loop** generator has a fixed number of clients. Each client sends one request, waits for the reply, and only then sends the next.
- An **open-loop** generator has a schedule. Request i is due at a fixed time. It is sent at that time, whether earlier requests have returned or not.

Users behave like the open loop. A thousand people on a website do not wait for each other. A closed loop models a fixed pool of workers, such as a batch job with four threads. The two models answer different questions. The mistake is to use a closed loop to answer the users' question.

One limit: a user with a long session of dependent requests waits for each reply, so a site of such users is partly closed. Schroeder, Wierman and Harchol-Balter, NSDI 2006, put the line near 10 requests per session. Below about 5, the site behaves open.

Here is the stall from the question, seen by both generators:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One 5 s stall from t = 50 s to 55 s. The schedule has a request due      │
│ every 10 ms. Service time 1 ms. Computed by coordinated_omission.py.     │
├──────────────────────────────────────────────────────────────────────────┤
│ time       50.00  50.01  50.02   ...   54.98  54.99  55.00  55.01        │
│ service    ██████████████████ stopped ████████████████  runs again       │
│                                                                          │
│ CLOSED     sent at 50.00 ───── waits for its reply ─────► done 55.001    │
│ 1 client   nothing else is sent until 55.010                             │
│            recorded: 1 sample of 5.001 s                                 │
│                                                                          │
│ OPEN       due    due    due     ...   due    due                        │
│ schedule   500 requests are due during the stall. Each one waits.        │
│            recorded: 500 samples, from 5.001 s down to 0.510 s           │
└──────────────────────────────────────────────────────────────────────────┘
```

This is **coordinated omission**. The rate the generator sends depends on how fast the service answers. When the service is slow, the generator sends less, so the slow period produces almost no samples. Gil Tene's talk defines it. The talk is in the references, with timestamps.

**The arithmetic, done by hand.** It is exact, because the model has no randomness.

Closed loop:

1. It sends at 0.00, 0.01, and so on up to 50.00 s. That is 5,001 requests.
2. The request sent at 50.00 s waits out the stall and returns at 55.001 s.
3. The client waits 9 ms and sends at 55.010 s. From 55.010 s, 4,499 requests fit before 100 s, counting that one.
4. Total: 9,500 samples. One of them is slow.
5. The p99 is the value that 99% of samples are at or below. 9,499 samples are 1 ms, so the p99 is **1 ms**.
6. The mean is (9,499 × 1 ms + 5,001 ms) / 9,500 = **1.53 ms**.

Open loop:

1. 10,000 requests are due. 500 of them fall inside the stall.
2. Number those 500 as i = 0 to 499. Request i is due at 50 + 0.01 i seconds.
3. When the stall ends, the i requests ahead of it run first, at 1 ms each. So it finishes at 55 + 0.001 × (i + 1).
4. Its latency is the finish time minus the due time: 5.001 − 0.009 i seconds.
5. That latency is 1 s or more while i ≤ 444. So **445 requests** take a second or longer.
6. The p99 of 10,000 samples is the 9,900th smallest. That is the 101st slowest, which is i = 100: 5.001 − 0.900 = **4.101 s**.

The script computes the same numbers with an HDR histogram. Its self-test asserts each of them.

```bash
uv run python phase01_measure/coordinated_omission.py
```

```
closed     sent   9500  n=  9500  mean   1.53 ms  p50   1.00 ms  p90   1.00 ms  p99   1.00 ms  p99.9   1.00 ms  max    5.00 s
           requests at 1 s or more: 1 of 9500 (0.01%)
corrected  sent   9500  n= 10000  mean    126 ms  p50   1.00 ms  p90   1.00 ms  p99    4.00 s  p99.9    4.90 s  max    5.00 s
           requests at 1 s or more: 401 of 10000 (4.01%)
open       sent  10000  n= 10000  mean    140 ms  p50   1.00 ms  p90   1.00 ms  p99    4.10 s  p99.9    4.91 s  max    5.00 s
           requests at 1 s or more: 445 of 10000 (4.45%)
```

The closed loop's p99 is 1 ms. The open loop's p99 is 4.10 s. That is a factor of about 4,100 on the same service. Only the max agrees, and the max is one sample.

**The repair, and where it stops.** The `corrected` row is the closed-loop data repaired afterwards. HdrHistogram's `record_corrected_value` takes each slow sample and adds the samples the schedule expected. A 5.001 s reply at a 10 ms interval also records 4.991 s, 4.981 s, and so on down to 11 ms. The Python package also adds one value below the interval, which is why the row has 10,000 samples. The repaired p99 is 4.00 s, close to the open loop. It is lower by exactly 0.1 s, because the repair cannot see the queue that forms behind the stall. Use the repair only on closed-loop data you cannot measure again. Otherwise measure open-loop.

**The same thing on a real service.** Lab E3 runs the course service at 48 requests per second. Its service time is 10.25 ms on average, so it is 49% busy. At t = 20 s the lab sends `POST /stall?seconds=3`, which blocks the event loop for 3 s. One open-loop run and one closed-loop run see the same stall. The closed client is paced to 48 requests per second, as Locust's `constant_throughput` would pace it.

```
open 48/s poisson, timer=due, raw  n=  1867  mean    221 ms  p50   22.4 ms  p90    665 ms  p99    2.73 s  p99.9    3.03 s  max    3.06 s  errors=0  sent 47/s
closed x1 paced 48/s               n=  1544  mean   14.2 ms  p50   9.26 ms  p90   26.7 ms  p99   50.6 ms  p99.9   74.9 ms  max    3.02 s  errors=0  sent 39/s
```

The open run's p99 is 2.73 s. The closed run's p99 is 50.6 ms. Both runs saw the same 3 s stall.

**Exactly which seconds the closed loop failed to record.** This split comes from the two saved run files:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Requests recorded per time window. Stall from t = 20 s to 23 s.          │
├───────────────────┬──────────────────────────┬───────────────────────────┤
│ window            │ OPEN, by due time        │ CLOSED, by send time      │
├───────────────────┼──────────────────────────┼───────────────────────────┤
│ 0 to 20 s         │ 914 requests, p50 17 ms  │ 839 requests, p50 9 ms    │
│ 20 to 23 s, stall │ 136 requests, p50 2.15 s │   1 request,  3.02 s      │
│ 23 to 26 s, drain │ 134 requests, p50 662 ms │ 123 requests, p50 8 ms    │
│ 26 to 40 s        │ 683 requests, p50 20 ms  │ 581 requests, p50 10 ms   │
└───────────────────┴──────────────────────────┴───────────────────────────┘
```

The closed loop missed two things:

1. **The stall itself.** 136 requests were due between 20 s and 23 s. The closed client had one request out and recorded one sample.
2. **The drain after it.** When the stall ended, 136 requests were waiting. They needed about 1.4 s of work while new ones kept arriving. For the next 3 seconds, requests that arrived still waited about 0.7 s. The closed client arrived to an empty service and recorded 8 ms.

Look at the closed loop's rate too. It was paced to 48 requests per second but sent 39 on average. Even while healthy, it sent 42 per second. A long request delays that client's next send, and a paced closed loop never catches up. So a closed loop also offers less load than its label says.

**The generator can also add delay.** An open-loop generator must send each request at its due time, and it must not add its own wait. The schedule gives each request its due time. `loadgen.py` records three more moments for each request:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One request, four timestamps, three delays                               │
├──────────────────────────────────────────────────────────────────────────┤
│  due ──────► issued ──────► sent ──────────────────────► done            │
│      │              │              │                                     │
│      generator lag  wait for a     service, network, the service's       │
│      the generator  free client    own queue                             │
│      ran late       connection                                           │
│                                                                          │
│  generator lag large     ► the run is invalid. The generator was the     │
│                            limit, not the service                        │
│  connection wait large   ► real latency. Users feel it. Keep it          │
│  timer=due               ► counts all three. The user's view             │
│  timer=sent              ► counts only the last. It hides the first two  │
└──────────────────────────────────────────────────────────────────────────┘
```

The stall run above printed both extra lines:

```
  generator lag                    p50 1.54 ms  p99 2.38 ms  max 81.41 ms
  waiting for a connection         p50 0.00 ms  p99 551.42 ms  max 721.41 ms
```

This course fixes one validity rule before any run is compared: an open-loop run whose generator lag p99 is above 10 ms is invalid. The generator was the limit, not the service. Here the generator lag p99 was 2.38 ms, so the run is valid. The connection wait reached 721 ms. The client has 100 connections. During the stall, all 100 were busy with stalled requests, so later requests waited for a free one. That wait is part of what a user would feel.

I made both mistakes this diagram guards against while building the lab. The first version ran the service in a thread of the generator's process. The two shared one GIL, the lock that lets one thread run Python at a time. A healthy 1 ms service at 150 requests per second then measured a p99 of 1.83 s. The second version used httpx as the open-loop client. In a run where the service fell behind, the generator itself fell up to 1.7 s behind its schedule. Both numbers were measured during development, and those runs were not kept. The fixes are in the code: the service runs as its own process, and the open loop uses a small fixed pool of raw connections. Every open-loop run prints its generator lag, so the next such mistake shows up in the output.

**What common tools do during a stall.** Read the tool's model before you trust its percentiles:

| Tool | Model | During a stall | What to read |
|---|---|---|---|
| Locust 2.46.6 | closed, per user. `constant_throughput` paces each user after each task | each user waits. Missed starts are not made up | its percentiles exclude the missed starts. Inferred from Locust's documented wait model, not run |
| k6, `constant-arrival-rate` | open, up to `maxVUs` virtual users | when no virtual user is free, the iteration is dropped | `dropped_iterations`, next to the percentiles |
| wrk2 with `-R` | open, constant rate | latency is counted from when the request should have been sent | the default output. `--u_latency` adds the uncorrected one |
| `vllm bench serve` | open, Poisson or gamma arrivals | with `--max-concurrency`, the client wait is kept as `client_queue_time` | add `client_queue_time` to the latency |
| `loadgen.py`, this course | open or closed | prints generator lag and connection wait | `--timer due` |

**The sentence to remember:** a closed loop records a stall once. An open loop records it once for every request that was due during it.

**The trap:** a paced closed loop looks like a fixed rate while the service is healthy. During a stall it stops sending, so its report hides exactly the slow seconds. In lab E3 the paced closed loop reported a p99 of 50.6 ms for a service that stopped for 3 s.

**Try this now:** run `uv run python phase01_measure/coordinated_omission.py --stall 1 --rate 200`. The stall is now 1 s at 200 requests per second, exactly 1% of the requests. Predict the three p99 values first. The run gives 1.00 ms closed, 1.00 ms corrected, and 201 ms open. The repair adds only the 1% the stall hid, so p99 stays on the fast side. The queue behind the stall pushes the open loop past it.

---
## 1.3 — Warm-up, caches and the first minute (what is cold, and for how long)

Why this matters: a short run of a busy service reports a p99 that is too low, and a different one each time. Every guide says "discard the warm-up", but the warm-up is the smaller problem. If you do not know what is cold and for how long, you keep too little apart and mix a different system into your result. Or you keep too much apart and miss a cold-start cost that users pay.

**Answer this first.** You start a fresh Python service and send it requests one at a time. Its work is a fixed 10 ms. How much slower is the first request than the rest: 2 times, 10 times, or a few percent? And in an open-loop run at 79% busy, are the first 2 seconds slower or faster than the rest?

**The interpreter is warm after one request.** CPython 3.11 and later have a specialising interpreter. It rewrites each bytecode instruction into a faster, type-specific form once it has seen the types. The count is in the CPython source file `Include/internal/pycore_code.h`, the same at the v3.13.0 and v3.14.0 tags. Its comment says: "A value of 1 means that we attempt to specialize the *second* time each instruction is executed." This course's CPython 3.13.3 has no JIT compiler built in. So there is no long interpreter warm-up to wait out.

`warmup.py` measures it. It starts a fresh service with a fixed 10 ms service time and sends 30 requests, one at a time, on one connection. `bash runs/lab.sh W` runs it three times and saves the output in `runs/lab-w.log`:

```bash
uv run python phase01_measure/warmup.py --repeat 3
```

```
start 0.12 s   first 10.6 ms   median of the rest 10.3 ms   first/median 1.03x   settled after 0 requests   new connection, warm process 10.6 ms
start 0.17 s   first 10.7 ms   median of the rest 10.2 ms   first/median 1.05x   settled after 0 requests   new connection, warm process 10.5 ms
start 0.17 s   first 11.0 ms   median of the rest 10.3 ms   first/median 1.07x   settled after 0 requests   new connection, warm process 10.6 ms
```

Three findings:

1. **Process start is 0.12 to 0.17 s.** `warmup.py` checks the port every 50 ms, so that is the resolution. In the same log, `python -X importtime` shows `import uvicorn` at 56 ms and `starlette.applications` at 13 ms. So imports are about 70 ms of the start.
2. **The first request is 3 to 7% slower** than the median of the rest. "settled after 0" means that even the first request, number 0, was within 20% of the median.
3. **The steady request costs 10.2 to 10.3 ms for 10 ms of work.** So the overhead of uvicorn, Starlette and a local connection is about 0.25 ms per request. Section 1.5 uses S = 10.25 ms as the service time.

**What is really cold in a service.** This course service has almost no cold state, and that is on purpose. A real service has more. Here is the list to check, with what each costs on first use:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Cold state in a Python service, and when it is paid                      │
├──────────────────────────┬───────────────────────────────────────────────┤
│ interpreter              │ 2nd execution of each instruction. Measured:  │
│ specialisation           │ first request 3 to 7% slower, then steady     │
├──────────────────────────┼───────────────────────────────────────────────┤
│ imports                  │ at process start: 0.12 to 0.17 s here. With   │
│                          │ lazy imports they move into the first request │
├──────────────────────────┼───────────────────────────────────────────────┤
│ connection pools to a    │ first request per connection pays connect and │
│ database or a service    │ TLS. httpx 0.28.1 drops a connection that is  │
│                          │ idle for 5 s, so a pause in a test costs new  │
│                          │ connections afterwards                        │
├──────────────────────────┼───────────────────────────────────────────────┤
│ application caches       │ the first request per key misses              │
├──────────────────────────┼───────────────────────────────────────────────┤
│ OS page cache            │ first read of a file after boot comes from    │
│                          │ disk. Phase 5 measures it                     │
├──────────────────────────┼───────────────────────────────────────────────┤
│ the queue itself         │ every run starts with an EMPTY queue          │
└──────────────────────────┴───────────────────────────────────────────────┘
```

**The queue is the thing that warms up.** The last row matters most for a load test, and most guides leave it out. At t = 0 no request is waiting. How the first seconds compare with the rest then depends on the arrivals.

Lab E8 kept the first 2 seconds of each run apart with `--warmup 2`, and printed them on their own line. At 79% busy there were ten runs of unchanged code. In 8 of them, the first 2 seconds had a lower median than the rest of the run. Their medians were 17.6 to 30.5 ms, against 29.0 to 41.6 ms for the rest. An empty queue makes the start look good. In the other 2 runs the first 2 seconds were slower: 56.1 against 29.9 ms, and 66.9 against 39.2 ms.

At 93% busy, the first 2 seconds of all three runs had a higher median than the rest. Their p99 was lower. Here is run 1:

```
open 91/s poisson, timer=due, raw  n=  2082  mean   79.2 ms  p50   66.6 ms  p90    166 ms  p99    233 ms  p99.9    273 ms  max    278 ms
  first 2 s (kept apart)           n=   196  mean    132 ms  p50    134 ms  p90    209 ms  p99    228 ms  p99.9    238 ms  max    238 ms
```

It was not a cold process. `warmup.py` showed a fresh process steady from its first request. The cause was the arrivals. Look at `n=196` for the first 2 seconds. The schedule's mean is 91 per second, so 182 were expected. All three runs happened to get 194 to 206, which is 97 to 103 per second. The service's capacity is 1 / 10.25 ms, about 98 per second. For 2 seconds the arrivals matched or passed the capacity, and a queue built. Near the knee, a short bunch of Poisson arrivals is enough to do that.

So the first seconds differ from the rest in either direction. That is the reason to keep them apart. It is not a rule that they are slow.

**Near the knee, a short run misses the tail.** The larger problem is not the start. At 93% busy the queue length changes widely: from nearly empty to hundreds of milliseconds deep, over tens of seconds. The long-run p99 is set by the rare periods when the queue grows very long. A 23-second run seldom contains one.

`predict.py --short-runs` simulates it. It uses the M/M/1 model: Poisson arrivals, exponential service times and one server, the model that section 1.5 explains. It runs the queue 40 times for 23 seconds each, each from an empty queue:

```bash
uv run python phase01_measure/predict.py --service-ms 10.25 --rate 48 77 91 --short-runs 40 --run-seconds 23
```

```
40 runs of 23 s at 48/s (49% busy), M/M/1 mean 20 ms, p99 93 ms
  run p99s:  min 68, median 89, max 145 ms
40 runs of 23 s at 77/s (79% busy), M/M/1 mean 49 ms, p99 224 ms
  run p99s:  min 116, median 184, max 350 ms
40 runs of 23 s at 91/s (93% busy), M/M/1 mean 152 ms, p99 702 ms
  run p99s:  min 180, median 385, max 863 ms
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Median p99 of 40 short runs, as a share of the long-run p99              │
├──────────────────────────────────────────────────────────────────────────┤
│ 49% busy  ████████████████████████████████████████████████  89 of  93 ms │
│ 79% busy  ███████████████████████████████████████           184 of 224 ms│
│ 93% busy  ███████████████████████████                       385 of 702 ms│
│                                                                          │
│ The busier the service, the more a short run understates its tail.       │
└──────────────────────────────────────────────────────────────────────────┘
```

At 49% busy, 23 seconds is enough: the median run is within 5% of the long-run p99. At 93% busy the median run shows 55% of the long-run p99, and the runs range 4.8 times from lowest to highest. Longer runs help less than you would expect. With 300-second runs at 93% busy, the median run reached 606 ms, 86% of the long-run value. But the runs still ranged from 455 to 1,795 ms, 3.9 times.

So near the knee, one run of any practical length is a weak result. Report the spread over several runs. Or measure at a lower load, where a run of a minute is enough, and use the model for the knee.

**The sentence to remember:** a short run of a busy service reports a p99 that is too low and changes from run to run. Keep the first seconds apart, and report the spread over several runs.

**The trap:** "we kept a 30 s warm-up apart" says nothing about whether the run was long enough. At 93% busy on this service, a 23-second measured window typically shows about half of the long-run p99.

**Try this now:** run `uv run python phase01_measure/predict.py --service-ms 10.25 --rate 91 --short-runs 40 --run-seconds 300`. Expect a median of 606 ms and a range of 455 to 1,795 ms. Then try `--rate 70 --run-seconds 60`. Expect a median of 153 ms against a long-run 167 ms, and a range of 120 to 225 ms, 1.9 times. Decide which load you would measure at.

---
## 🧪 Hands-on lab — part A

**Run status:** every command below was executed on the author's machine on 2026-09-25. It is an Apple M2 with 8 GB, macOS 15.7.8 and CPython 3.13.3 through uv. Each "Expected" line is copied from that run. Your latency numbers will differ. The relations between them should not.

All commands run from `elite-performance/code/`. `runs/lab.sh` runs the live measurements of this phase. It starts a fresh service for every run, so you do not need a second terminal. Each part runs alone, for example `bash runs/lab.sh A`.

- [ ] **E1 (offline).** Coordinated omission, with the arithmetic checked.
  - Run: `uv run python phase01_measure/coordinated_omission.py`, then `uv run python phase01_measure/coordinated_omission.py --self-test`.
  - Expected: closed `n=  9500` with p99 `1.00 ms`. Open `n= 10000` with p99 `4.10 s` and `445 of 10000` requests at 1 s or more. The self-test prints `closed n=9500 p99=1.00 ms; open n=10000 p99=4.102 s, slow=445; corrected p99=4.002 s`.
  - Then work out `--stall 1 --rate 200` by hand before you run it. Expected: p99 `1.00 ms` closed, `1.00 ms` corrected, `201 ms` open.
  - If it fails: `uv sync` was not run, so the `hdrh` module is missing.
  - Teaches: a closed loop records a stall once, and the repair after the fact misses the queue behind the stall.

- [ ] **E2 (local).** What is cold in a fresh Python service.
  - Run: `bash runs/lab.sh W`. It starts its own services, and also prints the import times.
  - Expected: `start 0.12 s` to `0.17 s`, `first/median 1.03x` to `1.07x`, `settled after 0 requests`, and `import uvicorn` near 56 ms cumulative.
  - If the first request is far slower than 1.1x, note what else the machine was doing. The first run after a reboot also reads its files from disk.
  - Teaches: the interpreter warms in about one request. The cold state that matters is elsewhere.

- [ ] **E3 (local).** The same stall, open and closed. This is the phase's demonstration.
  - Run: `bash runs/lab.sh A`. About 90 seconds.
  - Expected: `open 48/s ... p99    2.73 s`, and `closed x1 paced 48/s ... p99   50.6 ms ... max    3.02 s ... sent 39/s`.
  - Then split both saved runs into the four time windows of section 1.2: `uv run python phase01_measure/windows.py runs/a-open.json runs/a-closed.json --edges 0 20 23 26 40`.
  - Expected: the open run recorded `136 requests` from 20 to 23 s, at `p50    2145.4 ms`. The closed run recorded `1 requests` in the same window.
  - Write one paragraph: which seconds did the closed run fail to record, and why?
  - Teaches: coordinated omission on a real service, and a paced closed loop that sends less than its label says.

- [ ] **E4 (break-it, local).** One client connection for 77 requests per second.
  - Run: `bash runs/lab.sh B`. About 35 seconds.
  - Expected: `timer=due` p99 `205 ms`. `same run, timer=sent` p99 `49.1 ms`. `waiting for a connection` p50 `28.24 ms` and p99 `189.18 ms`. Generator lag p99 `2.12 ms`, so the run is valid.
  - What broke: with one connection, the queue moved from the service into the client. Measured from the send, the service looks healthy. Measured from the due time, the p99 is four times higher.
  - Teaches: `--timer sent` hides every wait before the send.

- [ ] **E5 (offline).** How long a run near the knee must be.
  - Run: `uv run python phase01_measure/predict.py --service-ms 10.25 --rate 48 77 91 --short-runs 40 --run-seconds 23`.
  - Expected: `run p99s:  min 68, median 89, max 145 ms` at 48/s, `min 116, median 184, max 350 ms` at 77/s, and `min 180, median 385, max 863 ms` at 91/s.
  - Then run it again at 91/s with `--run-seconds 300`. Expected: `run p99s:  min 455, median 606, max 1795 ms`.
  - Teaches: a short run of a busy service reports a tail that is too low, and a different one each time. Even 5-minute runs differ by 3.9 times.

---

## 🔍 Check it yourself

1. Open `phase01_measure/loadgen.py:218`. This is `_one_raw`. It takes `issued` before it asks the pool for a connection, and the pool takes `sent` after it gets one. Suppose `issued` were taken after `pool.get` instead. Which line of E4's output would lose its meaning, and which delay would be hidden?

2. Open `phase01_measure/coordinated_omission.py:106`. This is where the closed loop is repaired with `record_corrected`. Why is the repaired p99, 4.00 s, lower than the open loop's 4.10 s? Which requests does the repair never create?

3. Open `shared/latency.py:47`. This is `_us`, which clamps every value into the histogram's range. What would E3's open-loop max show if a request took 90 s and `_us` did not clamp?

4. In any repository you own that has a load test, run:

   ```bash
   grep -rnE "constant_throughput|constant_pacing|wait_time|between\(|record_value\(" <your repo>/
   ```

   For every Locust `wait_time`, say whether that test is closed-loop, and what it would have reported during your last incident. For every `record_value` call, check whether its return value is read.

---

## ✅ Checkpoint 1A — answer in your own words

1. **Explain coordinated omission, with the arithmetic.** A test sends 200 requests per second for 60 s to a service that answers in 2 ms. At t = 30 s the service stops for 2 s. One closed-loop client sends, waits for the reply, waits 3 ms, and sends again. (a) How many samples does it record, and what is its p99? (b) An open-loop schedule sends the same 200 per second. How many requests take 1 s or more, and what is the p99? (c) Which seconds did the closed loop fail to record?

2. **A colleague says:** "We discard the first 30 seconds, so our 60-second test at 93% busy gives a valid p99." Argue for or against, with numbers from section 1.3.

3. **This is broken.** A Locust test with `constant_throughput(50)` per user and 20 users reports p99 12 ms for an endpoint. In production, users of the same endpoint see a 1.5 s pause about once a minute. The dashboards show the pauses. The load test never did. What is the cause, how do you confirm it from the test's own output, and what do you change?

4. **Show the arithmetic.** A run of 25 s at 48 requests per second keeps the first 2 s apart. (a) About how many samples does its p99 rest on, and its p99.9? (b) The generator reports `generator lag p99 14 ms` and `waiting for a connection p99 850 ms`. Is the run valid, and is the 850 ms part of the latency you report?

5. **Walk through what happens** in E4. The service is 79% busy, and the client has one connection. The owner of the service sees p99 49 ms in their own server metrics. Users see much worse. Where is the queue, which timer shows it, and what do you tell the service owner?

<details>
<summary>Answer sketches</summary>

1. (a) The client sends every 5 ms. It sends 6,001 requests up to t = 30.000 s. The one sent at 30.000 returns at 32.002. The next goes at 32.005. From 32.005 s, 5,599 requests fit before 60 s, counting that one. So it records 11,600 samples, one of them slow, and its p99 is 2 ms. (b) 400 requests are due in the stall. Request i is due at 30 + 0.005 i and finishes at 32 + 0.002 (i + 1). Its latency is 2.002 − 0.003 i. It is 1 s or more while i ≤ 334, so 335 requests. The p99 of 12,000 is the 11,880th smallest, which is the 121st slowest, i = 120: 2.002 − 0.360 = 1.642 s. `coordinated_omission.py --rate 200 --service 0.002 --stall 2 --stall-at 30 --duration 60` prints `1.64 s` and `335 of 12000`. (c) The 2 s of the stall, where it recorded one sample instead of 400, and the drain after it. The queue lasts until about request i = 667, at t ≈ 33.3 s. The closed client saw none of it.

2. Against. At 93% busy, simulated 23-second runs give a median p99 of 385 ms against a long-run 702 ms, with a range of 180 to 863 ms. 30 measured seconds is close to that. Even 300-second runs gave a median of 606 ms, 86% of the long-run value. Keeping a warm-up apart does not make a short window see the tail. Even 300-second runs ranged from 455 to 1,795 ms. Report the run length and the spread over several runs, or measure at a lower load.

3. Locust waits after each task, so each user is a closed loop. During a 1.5 s pause each of the 20 users has one request out. Each records one slow sample and sends nothing more. This is inferred from Locust's documented wait model. Confirm it from the test: compare the achieved request rate during a pause with the planned rate. The plan was 50 × 20 = 1,000 per second, so about 1,500 requests per pause. If the achieved rate drops towards zero, the pauses were not measured. Change to an open-loop generator that measures from the due time: k6 `constant-arrival-rate` with `dropped_iterations` read beside the percentiles, wrk2, or `loadgen.py`.

4. (a) 23 s × 48 = about 1,100 samples. The p99 rests on about 11 and the p99.9 on about 1. Do not report the p99.9 from one run. (b) Invalid. Section 1.2 fixes the rule before any result is read: a generator lag p99 above 10 ms makes an open-loop run invalid. At 48 per second the p99 is about 93 ms, so 14 ms of lag is 15% of it. The 850 ms connection wait is a separate thing: real latency that a user feels. Report it inside the latency from the due time, and name the resource that caused it.

5. The queue is in the client, in front of its one connection. The service sees one request at a time, so its own view is the service time: p99 49 ms. The due-time timer shows 205 ms, and the connection wait line shows p99 189 ms. Tell the owner that their service is healthy and their client pool is the limit. At 77 requests per second and about 11 ms per request, one connection is 85% busy by itself.

</details>

---

## References & Further Learning — part A

Every URL below was fetched on 2026-09-25 and returned HTTP 200.

**Coordinated omission and open versus closed load**

- **Gil Tene, "How NOT to Measure Latency", talk at USI, published 2014** — https://www.youtube.com/watch?v=6Rs0p3mPNr0
  Focus on: 24:30 the start of the coordinated omission part. 25:28 why a load tester only works while every request is shorter than the interval. 26:35 the 100 requests per second example. 26:46 the 100 s freeze. 27:36 the correct average. 28:17 what a JMeter-style tool records. 29:03 the definition. 29:44 real JMeter output. 30:31 the YCSB case. 37:27 HdrHistogram. 38:07 its correction. The timestamps come from auto-generated captions and are accurate to a few seconds.
- **wrk2 README, Gil Tene** — https://github.com/giltene/wrk2
  Focus on: the closing notes on latency measurement, and Examples 1 and 2, which show corrected and uncorrected output of the same run. Read it before you choose an HTTP load tool.
- **YCSB core/CHANGES.md at tag 0.2.0-RC1** — https://raw.githubusercontent.com/brianfrankcooper/YCSB/0.2.0-RC1/core/CHANGES.md
  Focus on: the item about measuring from the intended start time. It says the benchmark "should measure the latency between intended start time and operation completion." At this tag it is an option, `measurement.interval=intended`. The old way is the default. It applies only with a target load, `-target`. Not checked at the current release.
- **Schroeder, Wierman, Harchol-Balter, "Open Versus Closed: A Cautionary Tale", NSDI 2006** — https://www.usenix.org/legacy/event/nsdi06/tech/full_papers/schroeder/schroeder.pdf
  Focus on: Section 5.1 and Figure 2. A closed system with 50 users limits its queue to 50, so at the same load its mean response time is far lower. The paper says "orders of magnitude". A reading of Figure 2(a) by eye gives about 9 times at load 0.9.
- **Nitsan Wakart, "Fixing Coordinated Omission in Cassandra Stress", 2016** — http://psy-lob-saw.blogspot.com/2016/07/fixing-co-in-cstress.html
  Focus on: the run that asked for 17,000 partition keys per second and got 12,795. It ran 3,712 operations per second and still reported a p99 of 4.6 ms. An engineering report on a real tool, on a one-core laptop. A blog post, not peer reviewed.
- **Friedrich, Wingerath, Ritter, "Coordinated Omission in NoSQL Database Benchmarking", BTW 2017** — https://www.btw2017.informatik.uni-stuttgart.de/slidesandpapers/E4-11-107/paper_web.pdf
  Focus on: Sections 2.1 and 5. Why measuring from the intended time inside a closed loop does not fully fix it.
- **k6 docs, "Dropped iterations"** — https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/
  Focus on: when `constant-arrival-rate` drops an iteration, and the `dropped_iterations` metric. Read it before you trust a k6 percentile.
- **Locust `wait_time.py` at tag 2.46.6** — https://raw.githubusercontent.com/locustio/locust/2.46.6/locust/user/wait_time.py
  Focus on: `constant_pacing` and `constant_throughput`. The wait comes after the task, so each user is a closed loop.

**Histograms**

- **HdrHistogram README** — https://github.com/HdrHistogram/HdrHistogram
  Focus on: "Corrected vs. Raw value recording calls", and the memory footprint section.
- **HdrHistogram_py `histogram.py` at tag 0.10.7** — https://raw.githubusercontent.com/HdrHistogram/HdrHistogram_py/0.10.7/hdrh/histogram.py
  Focus on: `record_value`, which returns False for a value out of range, and `record_corrected_value`.

**Warm-up**

- **CPython `Include/internal/pycore_code.h` at v3.13.0** — https://raw.githubusercontent.com/python/cpython/v3.13.0/Include/internal/pycore_code.h
  Focus on: `ADAPTIVE_WARMUP_VALUE` and its comment. The interpreter specialises on the second execution.
- **What's New in Python 3.13** — https://docs.python.org/3/whatsnew/3.13.html
  Focus on: the experimental JIT section. It exists only in builds configured for it, and is off by default in the `yes-off` build.
- **httpx `_config.py` at tag 0.28.1** — https://raw.githubusercontent.com/encode/httpx/0.28.1/httpx/_config.py
  Focus on: the default `Limits`, and `keepalive_expiry` of 5.0 seconds.

---

## Cheatsheet — part A

```
MEASURE FROM THE DUE TIME
  open loop     request i is sent at its due time, whatever came before
  closed loop   next request only after the last reply: a stall = 1 sample
  latency       done − due    (timer=sent hides generator and pool waits)
  generator lag issued − due. Rule, fixed first: p99 > 10 ms = invalid run
  100/s, 1 ms, 5 s stall in 100 s:  closed p99 1 ms, open p99 4.10 s
  repair        record_corrected adds the missed samples, not the queue

READ A DISTRIBUTION
  report        p50  p90  p99  p99.9  max, never a mean alone
  samples above p99 = n / 100   1,063 samples → 10. Below ~10: do not report it
  HDR           1 µs .. 60 s, 3 digits, 139,264 bytes. Clamp, never drop

WARM-UP AND RUN LENGTH
  CPython       specialises on the 2nd execution. First request +3 to 7%
  cold state    start 0.12-0.17 s, 70 ms of it imports. Pools, caches,
                page cache, and an EMPTY QUEUE
  httpx         drops idle connections after 5 s
  keep apart    the first seconds, --warmup. They differ in either direction
  near the knee 23 s runs at 93% busy: median p99 385 of 702 ms
                300 s runs still range 3.9x. Report the spread, or load less
```

Part B covers whether a change is real, sections 1.4 and 1.5, with the before, after and control runs, and the prediction sheet.

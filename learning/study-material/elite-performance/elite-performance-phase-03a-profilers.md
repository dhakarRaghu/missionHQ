# Phase 3A — Profiling Python systems: what each view can see

**The question this phase answers:** when the service is slow, how do you find the line of code responsible in under an hour, and prove the fix helped?

Here is an example. A handler has a p99 of 400 ms. The CPU profile says that 90% of its CPU goes to formatting rows. You make the formatting four times faster and ship it. The p99 is still 380 ms. A week later the change is reverted, and nobody knows why it did not work. The example is invented. The lab in this phase builds a service with the same shape and measures each step on your laptop.

The profile was not wrong. The question it answered was not the one asked. A CPU profile counts only the time a thread spends running code. This handler spent most of its time waiting for a lock, and waiting uses no CPU. Profiling is not one tool. It is several views of the same program, and each one is blind to what another sees. This phase teaches which view answers which question, and how to prove that a fix worked. It teaches four ideas. Each is a claim you could get wrong today:

1. **Each profiler measures one kind of cost.** A CPU profile cannot see time spent waiting for a lock, the GIL, a pool or the network.
2. **A handler whose CPU per request is small next to its latency is waiting**. Only a wall-clock view that follows the await shows where: an async profile of one request, a timed lock, or a timeline of spans. For the GIL, the view is the event loop's lag.
3. **The garbage collector runs when container allocations minus deallocations pass 2,000**. So its cost follows the containers a request keeps alive at once, and those that stay alive for good, not the count of allocations. Keeping fewer alive removes both the collector's time and its pauses, the pauses that set the far tail.
4. **A fix is proven by the latency distribution at fixed throughput**, measured the way the problem was found, with errors and memory checked for regression.

Phase 3 is split into two documents. This one teaches the first three ideas: what each view can see, and what sets the collector's cost. Part B times the waits no profiler records, finds the real cause of a slow endpoint, and proves its fix.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, this document: what each view can see                            │
│  3.1  The profilers and what each is blind to — which cost each measures │
│  3.2  Wall-clock versus CPU time              — the handler that waits   │
│  3.3  Allocations and the garbage collector   — what sets the pause      │
│  Lab: E1 to E5                                                           │
│                                                                          │
│ PART B, the next document: from symptom to proof                         │
│  3.4  Lock and GIL contention                 — timing the wait yourself │
│  3.5  The timeline: tracing the event loop    — the order of events      │
│  3.6  Symptom versus root cause               — one measurement each     │
│  3.7  Proving a fix                           — the proof that holds     │
│  Lab: E6 to E12                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**What this phase assumes.** Two earlier phases of this course are used here and not taught again.

- **Phase 1, section 1.2, open-loop load.** Every load in this phase is open-loop: request i is sent at its due time, whatever came before. Latency is measured from the due time. The validity rule is fixed before any run is read: a run whose generator lag p99 is above 10 ms is invalid.
- **Phase 1, sections 1.4 and 1.5.** A change is real when the interval from resampling runs, then requests, lies on one side of zero. A prediction is written before the run.
- **Phase 2, section 2.2, "Head-of-line blocking".** An asyncio event loop is one queue. A call that blocks inside an async handler stalls every request in flight.
- **Phase 2, section 2.3, "Pools that fill", and section 2.5, "The capacity envelope of a service".** A pool is a queue with several servers, and each resource has its own knee. This phase measures a pool of one: a lock.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. Every measurement in this phase was made on 2026-09-25 on an Apple M2 with 8 GB of memory, macOS 15.7.8, CPython 3.13.3 through uv. The profilers are pinned in `pyproject.toml`: pyinstrument 5.1.3, yappi 1.7.6 and memray 1.20.0. None of them needs `sudo`.

The laptop was not quiet. Other load tests ran on it at the same time, and the 1-minute load average was 2.69 to 4.28 during the runs, from 15:53 to 16:30. The laptop ran on battery. Each log in `runs/` starts with the conditions of its run. So this phase quotes ratios and ranges over repeated runs, alternates the runs it compares, and applies the validity rule. Your numbers will differ. The shape of each result should not.

Setup:

```bash
cd ~/Desktop/project/study-material/elite-performance/code
uv sync
uv run python phase03_profiling/app.py --self-test
```

The last line should print `self-test passed`.

Time for part A: 75 minutes of reading, plus about 10 minutes of waiting for runs.

---

## 3.1 — The profilers and what each is blind to (which cost each view measures)

Why this matters: a profiler does not show where the time went. It shows where one kind of cost went. If you do not know which kind, you will read "90% of CPU in formatting" as "90% of the time in formatting". Then you fix the wrong thing.

**Answer this first.** A handler runs 40 times, 4 at a time. Each run spends 3 ms of CPU, then waits for a shared lock, then awaits a 20 ms backend call while it holds the lock. Each request takes about 84 ms from start to end. What does cProfile report as the handler's time per request? What does a CPU-clock profiler report? Write two numbers down.

**Two questions define a profiler.** Every profiler answers them differently, and together they decide what it can see:

1. **How does it collect?** A deterministic profiler runs a hook on every function call and return. cProfile and yappi work this way. A sampling profiler looks at the stack every few milliseconds. pyinstrument does this from inside the process. py-spy does it from outside.
2. **Which clock does it use?** A CPU clock advances only while the thread runs on a CPU. A wall clock advances all the time. A wait for a lock, the network or the GIL uses no CPU, so only a wall clock can count it.

asyncio adds a third question: what happens at an `await`? A coroutine that awaits leaves the thread's stack. Its frame sits on the heap until the event loop resumes it. To a hook, the await looks like a return. To a stack sampler, the coroutine is gone. CPython's cProfile maps the event for a suspending coroutine to its return callback. That is `Modules/_lsprof.c` line 719 at tag v3.13.3: `PY_YIELD` goes to `_pyreturn_callback`.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One request of the blind.py handler, and what each view records.         │
│ Times are rounded from run 1 of runs/lab3-profilers.log                  │
├──────────────────────────────────────────────────────────────────────────┤
│ time       0     3 ms                          62 ms           84 ms     │
│            │enc. │ wait for the lock           │ backend await │         │
│            │ CPU │ no CPU: the coroutine is    │ no CPU        │         │
│            │     │ off the stack, on the heap  │               │         │
├──────────────────────────────────────────────────────────────────────────┤
│ cProfile   ███    call ... return at the await, resume ... return        │
│            counts the CPU part, and a new "call" at each resume: 3 calls │
│ yappi cpu  ███    nothing more: the thread did no work for it            │
│ yappi wall █████████████████████████████████████████████████████         │
│            follows the coroutine across both awaits: 84 ms, 1 call       │
│ pyinst.    encode Lock.acquire [await]        sleep [await]              │
│ async      each await named, with its time, for one request              │
└──────────────────────────────────────────────────────────────────────────┘
```

**What they reported.** `blind.py` runs exactly this program, and measures each part itself, so the true answer is known. Then it runs the program under each view. Run 1 of three, from `runs/lab3-profilers.log`:

```bash
uv run python phase03_profiling/blind.py
```

```
truth, per request      wall   83.9 ms   cpu   3.0 ms   lock wait  59.1 ms
cProfile                handler cumtime    3.1 ms per request, 119 calls for 40 requests
yappi, cpu clock        handler total      3.4 ms per call, 40 calls
yappi, wall clock       handler total     84.4 ms per call, 40 calls  (truth in that run 84.4 ms)
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The same request by each view, per request. blind.py, run 1              │
├──────────────────────────────────────────────────────────────────────────┤
│ truth, wall        ██████████████████████████████████████████ 83.9 ms    │
│ truth, CPU         ██ 3.0 ms                                             │
│ cProfile           ██ 3.1 ms                                             │
│ yappi, cpu clock   ██ 3.4 ms                                             │
│ yappi, wall clock  ██████████████████████████████████████████ 84.4 ms    │
├──────────────────────────────────────────────────────────────────────────┤
│ one bar character = 2 ms. The waiting is 80.9 of the 83.9 ms.            │
└──────────────────────────────────────────────────────────────────────────┘
```

Four things to read from it:

1. **cProfile lost the waits.** It uses a wall clock, so you might expect the full 84 ms. But each await ends a "call", so the time suspended is never added to the handler. It reported 3.1 ms in all three runs.
2. **cProfile also counted the calls wrong.** 40 requests became 119 calls. Each request resumes twice, after the lock and after the backend. The first request found the lock free, so it resumed once: 3 × 40 − 1 = 119.
3. **cProfile's clock is a wall clock.** The CPU part is 3.0 ms by construction, because `encode` spins until the thread's CPU clock has moved 3 ms. Any cost of cProfile's own hook is CPU on the same thread, so it falls inside those 3 ms. The 0.1 ms cProfile added is time the thread spent off the CPU in the middle of `encode`. On a busier laptop that part grows. Inferred, not measured here.
4. **Both yappi clocks were right, about different things.** The wall clock matched the wall time measured in the same run, 84.3 to 84.6 ms. The CPU clock reported 3.4 to 3.5 ms, the CPU part. Both are correct. They answer different questions.

**WRONG: profile the async program from the outside.** pyinstrument's command line, `pyinstrument script.py`, forces `async_mode="disabled"`. Its source says there is no point in async mode for a command-line run. `pyinstrument/__main__.py` lines 385 to 391 at tag v5.1.3. Here is one 88 ms request profiled with that mode. The tree leaves out the two lines under `encode`:

```
0.086 _UnixSelectorEventLoop._run_once  asyncio/base_events.py:1954
├─ 0.074 KqueueSelector.select  selectors.py:540
│  └─ 0.074 kqueue.control  <built-in>
└─ 0.012 Handle._run  asyncio/events.py:87
   └─ 0.012 one  blind.py:87
      └─ 0.012 handler  blind.py:73
         └─ 0.012 encode  blind.py:65
```

The request waited 61 ms for the lock. The profile says the program spent 74 ms in `kqueue.control`, the call where the event loop waits for I/O. It looks idle. The 12 ms under `handler` is also wrong: it is the CPU of this request and of other requests that ran while this one waited. Nothing in it names the lock.

**RIGHT: profile one request from inside its own task, in async mode.** The same request position in the other run, with `Profiler(async_mode="enabled")` started inside the task. The tree below leaves out the two lines under `encode`:

```
0.085 one  blind.py:87
└─ 0.085 handler  blind.py:73
   ├─ 0.060 Lock.__aenter__  asyncio/locks.py:13
   │  └─ 0.060 Lock.acquire  asyncio/locks.py:90
   │     └─ 0.060 [await]  asyncio/locks.py
   ├─ 0.022 sleep  asyncio/tasks.py:703
   │  └─ 0.022 [await]  asyncio/tasks.py
   └─ 0.003 encode  blind.py:65
```

Now the lock has a name and a time: 60 ms, against the 63 ms the program measured for that request. The backend await is 22 ms, a little above its 20 ms, because the loop was busy with other requests when the sleep ended. pyinstrument's docs describe the mode in one line: time is logged "in the function that awaited". Where you start the profiler matters. I first started it before `asyncio.run`, outside every task, and even `async_mode="enabled"` showed only `select`. The mode follows the task in which the profiler started.

**The views you have on macOS, and what each cannot see.** Versions are those pinned in `pyproject.toml`, except py-spy, which the lab does not install. The macOS column was checked on the author's laptop, without `sudo`.

| View | How it collects, which clock | What it cannot see | Runs on macOS without sudo |
|---|---|---|---|
| cProfile, standard library | a hook on each call and return. Wall clock | time a coroutine is suspended at an await. It counts each resume as a call | yes |
| yappi 1.7.6, cpu clock | a hook on each call and return. Per-thread CPU | any waiting, by design | yes |
| yappi 1.7.6, wall clock | the same hooks. It adds a coroutine's time across awaits | nothing in time, but it adds a cost to every call | yes |
| pyinstrument 5.1.3 | a stack sample every 1 ms from inside the process. Wall clock | in `disabled` mode, and from its command line, the await a task is in | yes, through its Python API |
| py-spy 0.4.2 | samples every thread from outside the process, 100 times a second | by default it drops threads it judges idle. `--idle` keeps them. A suspended coroutine is on no stack | no. Its README says macOS always requires root |
| memray 1.20.0, tracemalloc | allocations and memory, not time | time. Section 3.3 uses them | yes |

Python 3.15 adds `profiling.sampling`, a sampling profiler with wall, CPU and GIL modes. It is not in 3.13, and it needs root on macOS too. So the lab uses the first four rows of the table. Scalene 2.3.0 also runs on macOS without `sudo`. The lab leaves it out: its views overlap pyinstrument's and yappi's, and its overhead on 3.13 is not measured.

**The cost of looking.** Every view slows the program it measures, and the deterministic ones slow call-heavy code most. The live service of section 3.2 makes about 15,000 function calls per request: cProfile counted 2,630,247 calls in a window in which 171 requests finished. During a 3-second window of yappi's cpu clock, the service finished 52 requests. The load sent about 180 in that time. yappi charged each of them 49.1 ms of CPU, against 4.8 to 5.0 ms per request without it. The ranking of functions stayed correct. The service did not.

**The sentence to remember:** a CPU profile, and cProfile at an await, see only running code. A wait for a lock, the network or the GIL is invisible to them, however long it is.

**The trap:** reading "90% of CPU in X" as "90% of the time in X". In `blind.py` the CPU views were correct about the 3 ms of CPU, and silent about the 80.9 ms of waiting.

**Try this now:** run `uv run python phase03_profiling/blind.py --concurrency 1`. With one request at a time nobody waits for the lock. Predict each view's number before you run it. The run in `runs/lab3-extras.log` gave a wall time of 24.8 ms and a lock wait of 0.0 ms. cProfile reported 3.3 ms over 80 calls: one resume per request now, after the backend. yappi's clocks gave 3.3 and 24.8 ms.

---

## 3.2 — Wall-clock versus CPU time (why the slow handler is missing from the CPU profile)

Why this matters: the first question about a slow endpoint is not "which function". It is "running or waiting". The answer decides which profiler can help, and a CPU profile cannot answer it. Get it wrong and a correct speed-up can change nothing the user feels.

**Answer this first.** A service answers `/report` at 60 requests per second. Its process uses about 30% of one core. In three runs its p99 was between 124 and 263 ms. The CPU profile's top function formats display text. Is the handler slow because of CPU? What single number would tell you?

**The service this phase measures.** `phase03_profiling/app.py` is a Starlette app on uvicorn, one worker, one event loop, as in Phases 1 and 2. Its `/report` handler does three things:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ GET /report, the handler this phase profiles                             │
├──────────────────────────────────────────────────────────────────────────┤
│  request ──► 1. query      takes the ONE shared connection, a Lock,      │
│                            then awaits the backend: 8 ms on average,     │
│                            exponential. The lock is held meanwhile       │
│              2. summarise  builds 1,200 rows, each a dict with a list,   │
│                            formats display text for every row, keeps     │
│                            the best 50. CPU on the event loop            │
│              3. reply      encodes the 50 rows as JSON                   │
├──────────────────────────────────────────────────────────────────────────┤
│  alive for the whole process: 150,000 rows of reference data             │
│  load: open-loop, Poisson, 60 requests per second, 20 s per run          │
└──────────────────────────────────────────────────────────────────────────┘
```

Each part is a knob, so the lab can remove one cause at a time. `--conns 4` replaces the one locked connection with a pool of four. `--format page` formats only the 50 rows in the reply. `--rows stream` keeps only those 50 rows alive.

**The one number: CPU per request against time per request.** The process CPU clock divided by the number of requests gives the CPU one request costs. The handler's own timer gives the time one request takes. If the first is a small part of the second, the handler is waiting, and no CPU profile can show where. `diagnose.py` prints both. Three clean runs, no profiler, from `runs/lab3-diagnose.log`:

```bash
uv run python phase03_profiling/diagnose.py --rate 60 --duration 20 --seed 1 --no-profiles
```

```
open 60/s poisson, timer=due, raw  n=  1028  mean   36.8 ms  p50   27.8 ms  p90   74.0 ms  p99    124 ms  p99.9    155 ms  max    162 ms  errors=0  sent 57/s
  generator lag                    p50 1.02 ms  p99 2.32 ms  max 8.00 ms
H1 CPU in the handler               15%  CPU 5.01 ms per request; handler mean 34.4 ms, p99 122 ms
H2 waiting for the connection       63%  lock wait mean 21.6 ms, p50 11.8 ms, p99 110 ms; held 8.1 ms, handoff 4.6 ms
H3 collector pauses                  1%  1141 collections, 320 ms in 21 s, longest 63 ms (gen2 2); loop lag p99 7.8 ms, max 182 ms
   lock as M/G/1: 57.0/s x (8.14 ms hold + 4.58 ms handoff) = 73% busy; predicted mean wait 23.2 ms, measured 21.6 ms
H4 the load generator                    generator lag p99 2.32 ms, limit 10 ms: valid run
largest share of handler time: H2 waiting for the connection at 63%
```

| Clean run | Client p99 | CPU per request | Handler mean | CPU share of handler time | Lock wait share |
|---|---|---|---|---|---|
| seed 1 | 124 ms | 5.01 ms | 34.4 ms | 15% | 63% |
| seed 2 | 155 ms | 4.78 ms | 43.8 ms | 11% | 70% |
| seed 3 | 263 ms | 4.92 ms | 65.4 ms | 8% | 79% |

The CPU was 8 to 15% of the handler's time. The wait for the lock was 63 to 79%. The process used 28 to 29% of one core. So the service is not busy and not fast. It waits. The line that starts `lock as M/G/1` is a model of that wait, and section 3.4 explains it. The three p99 values also differ by two times, with nothing changed but the seed. Section 3.7 deals with that spread.

**Do not use the process CPU share for this.** "The service is at 30% CPU, so it is not CPU-bound" is a common argument, and it is wrong. The process share mixes in the time when no request was in the process at all. `diagnose.py`'s self-test builds a handler that does nothing but CPU, at 20 requests per second. Its CPU per request was 107% of its handler time, while the process used only 18% of a core, in `runs/lab3-selftests.log`. It can pass 100%, likely because the process CPU also counts uvicorn's own work for each request, outside the handler. Inferred, not measured. Run it with `--h1 process`, which takes the process share instead, and the self-test fails.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One /report request under load, split by where its time went             │
├──────────────────────────────────────────────────────────────────────────┤
│ whole request         ███████████████████████████████████████ 155 ms     │
│ waiting for the lock  ████████████████████████████████ 130 ms            │
│ backend await         █████ 19 ms                                        │
│ summarise, on CPU     ██ 6 ms                                            │
├──────────────────────────────────────────────────────────────────────────┤
│ pyinstrument, async_mode="enabled", started inside the request's task.   │
│ The profiled run of runs/lab3-diagnose.log. One bar character = 4 ms     │
└──────────────────────────────────────────────────────────────────────────┘
```

**WRONG: profile the whole service with cProfile.** This is what most people run first. A 3-second window of the profiled run, the top lines by own time:

```
cprofile: 3.00 s of wall time, 1.27 s of process CPU, 171 requests finished
all functions: 2,630,247 calls
   own s  total s   calls  function
   1.737    1.737    1223  ~:0(<method 'control' of 'select.kqueue' objects>)
   0.385    0.772  205200  app.py:132(label)
   0.163    0.358  205371  ~:0(<method 'join' of 'str' objects>)
   0.141    0.193  615600  app.py:136(<genexpr>)
   0.096    0.096  205371  app.py:119(make_rows)
   0.077    0.077  615600  app.py:128(_value)
   0.063    1.106     171  app.py:140(summarise)
   0.053    0.077     171  ~:0(<built-in method builtins.sorted>)
```

The top line is `kqueue.control`: the event loop waiting for I/O. It reads as "idle". The next lines are `label` and its helpers, the display-text formatting. So the profile says: the loop is often idle, and the rest of the time it formats text. Both are true. Neither says that each request waited 21.6 to 51.9 ms on average for a lock, in the clean runs. `Lock.acquire` is a coroutine, and its time suspended ends at each await, so it is not in the top lines at all.

**RIGHT: profile one request, from inside its task, in async mode.** The same service, the same load. `/report?profile=async` wraps one request in `Profiler(async_mode="enabled")` from inside the handler:

```
0.155 report_route  app.py:416
└─ 0.155 report  app.py:271
   ├─ 0.149 query  app.py:192
   │  ├─ 0.130 Lock.__aenter__  asyncio/locks.py:13
   │  │  └─ 0.130 Lock.acquire  asyncio/locks.py:90
   │  │     └─ 0.130 [await]  asyncio/locks.py
   │  └─ 0.019 sleep  asyncio/tasks.py:703
   │     └─ 0.019 [await]  asyncio/tasks.py
   └─ 0.006 summarise  app.py:140
      └─ 0.004 label  app.py:132
```

Now the question has an answer: 130 ms of the 155 ms went to `Lock.acquire`, `[await]`. The tree leaves out the lines below `label`. This is the pattern pyinstrument's own guide shows for FastAPI: a middleware that profiles a request when asked. It profiles one request at a time. pyinstrument's docs say to use `disabled` mode when you want several profilers at once.

**Which wall-clock view, when.**

| View | What it shows | Cost | Use it for |
|---|---|---|---|
| a timed lock or pool: two `perf_counter` calls | wait and hold per request, as histograms | almost none | always on, in production |
| event-loop lag monitor | how late the loop runs any callback | almost none | always on. It shows the GIL, collector pauses and blocking calls |
| pyinstrument, async mode, one request | the await each request's time went to, by name | one request profiled at a time | when a request is slow and you do not know why |
| yappi, wall clock | every function's wall time across awaits | a cost on every call: 52 of about 180 requests finished in a live window of its CPU clock | offline, on a copy of the workload, as in `blind.py` |
| spans with a context variable, section 3.5 | the order of waits across requests | two clock reads per span. Not measured here | tracing in production |
| py-spy `--idle` | the stack of every thread, idle ones included | low: it samples from outside | Linux. On macOS it needs root. Not run in this lab |

**The sentence to remember:** divide process CPU by requests, and compare it with the time per request. If CPU is a small share, the request is waiting, and only a view that follows the await can say where.

**The trap:** "30% CPU, so not CPU-bound" and "the CPU profile says formatting, so fix formatting" are the same mistake twice. Both read a CPU number as a statement about time.

**Try this now:** run `uv run python phase03_profiling/diagnose.py --config conns=4 --rate 60 --duration 20 --no-profiles`. The one locked connection is now a pool of four. Predict the new lock-wait share and the CPU share before it prints them. The run in `runs/lab3-extras.log` gave 1% and 36%, with a p99 of 51.1 ms.

---

## 3.3 — Allocations and the garbage collector (what the collector costs, and what sets the cost)

Why this matters: a collector pause stops the event loop, and every request in flight waits for it. The pause does not show as a slow line of code. It lands on whichever request happened to allocate at the wrong moment. Rippling, an HR software company, reported a p99 API latency near 3 seconds against a p50 of 50 ms. They found worker processes paused in garbage collection for seconds, and fixed it by changing when and what the collector scans.

**Answer this first.** Two versions of a handler build the same 1,200 rows per request. Version A keeps them all in a list. Version B keeps only the 50 rows it returns. memray counts about 115,700 allocations per request for A and 118,900 for B. B allocates more. Which version makes the collector run more often, and by how much?

**Two ways Python frees memory.** Reference counting frees most objects: when the last reference goes, the object is freed at once. The cyclic garbage collector exists only for reference cycles, which reference counting cannot free. It looks only at containers: objects that can refer to other objects, such as dicts, lists and class instances. Strings and numbers are not containers, and the collector never counts them.

**What starts a collection.** The gc module docs state the rule: a collection starts when "the number of allocations minus the number of deallocations exceeds *threshold0*". Only containers count. The source shows the details. In `Python/gc.c` at tag v3.13.0:

- line 1819 adds 1 to the counter for every new container
- line 1946 subtracts 1 for every freed container, and never goes below 0
- line 1342 sets the counter to 0 after a collection

The default thresholds in 3.13 are `(2000, 10, 10)`, in `Include/internal/pycore_runtime_init.h` lines 233 to 235. Python 3.12 used 700. Blog posts that say 700 describe 3.12 and older.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The collector's three generations, CPython 3.13 defaults                 │
├──────────────────────────────────────────────────────────────────────────┤
│ young, gen0   collected when containers allocated minus freed pass       │
│               2,000. Survivors move to gen1                              │
│ gen1          collected every 10 young collections. Survivors move to    │
│               gen2, the old generation                                   │
│ gen2, full    collected every 10 gen1 collections, and only if the       │
│               containers promoted since the last full collection are     │
│               more than 25% of all old ones. It scans EVERY old          │
│               container: the pause grows with what stays alive           │
└──────────────────────────────────────────────────────────────────────────┘
```

The last rule is in `Python/gc.c` line 1264: a full collection is skipped while `long_lived_pending < long_lived_total / 4`.

**The arithmetic for one request.** Each row of `/report` is a dict with a list inside: two containers. Version A builds 1,200 rows and keeps them all until it returns:

1. 1,200 rows × 2 = 2,400 containers alive at the same moment, plus a few for the list itself.
2. The counter passes 2,000 at the 2,001st container, and a young collection runs. It resets the counter to 0.
3. The last 400 or so containers raise it to about 400. When the request returns, 2,400 frees bring it back to 0.
4. So version A triggers one collection per request.

Version B builds the same rows, one at a time. A row is freed when the next one replaces it, unless it is among the best 50. The counter rises and falls by two. It stays near 150: the 50 kept rows, their 50 heap entries, and the row being read. It never reaches 2,001. So version B never triggers the collector.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The collector's counter during one request of 1,200 rows                 │
├──────────────────────────────────────────────────────────────────────────┤
│                containers created   alive at once   collections          │
│ A, list        about 2,400          about 2,400     1 per request        │
│ B, stream      about 2,400          about 150       none                 │
├──────────────────────────────────────────────────────────────────────────┤
│ The counter follows containers ALIVE, not containers created.            │
└──────────────────────────────────────────────────────────────────────────┘
```

**The answer, measured.** `gcpause.py` runs the handler's CPU part 2,000 times in one process, with 150,000 rows of reference data alive, as the service keeps. A `gc.callbacks` hook times every collection. From `runs/lab3-gc.log`, run 1:

```
list         reference 150,000 rows: collections gen0  1830 gen1  166 gen2   4, collector   341.4 ms =   5% of 7.45 s, longest pause gen0 0.9 gen2 38.7 ms, mean gen2 29.9 ms
             per request n=  2000  mean   3.72 ms  p50   3.43 ms  p90   3.92 ms  p99   5.63 ms  p99.9   29.5 ms  max   42.6 ms
stream       reference 150,000 rows: collections gen0     0 gen1    0 gen2   0, collector     0.0 ms =   0% of 6.66 s, longest pause gen0 0.0 gen2 0.0 ms, mean gen2 0.0 ms
             per request n=  2000  mean   3.33 ms  p50   3.25 ms  p90   3.74 ms  p99   3.82 ms  p99.9   4.04 ms  max   6.64 ms
list+freeze  reference 150,000 rows: collections gen0  1823 gen1  165 gen2  12, collector   210.9 ms =   3% of 6.98 s, longest pause gen0 0.9 gen2 0.2 ms, mean gen2 0.1 ms
             per request n=  2000  mean   3.49 ms  p50   3.35 ms  p90   3.88 ms  p99   4.00 ms  p99.9   4.83 ms  max   5.95 ms
```

Version A ran 1,830 + 166 + 4 = 2,000 collections for 2,000 requests: one per request, as the arithmetic says. Version B ran none. The counts were the same in all three runs. The collector took 5% of the run's time in A, and nothing in B. B allocated more objects and cost nothing, because what counts is how many are alive at once.

**Why a full collection is the pause that matters.** A young collection scans about 2,000 new containers. With the reference data frozen, the same 2,000 collections took 210.9 ms in total: about 0.11 ms each. A full collection scans every old container, including the reference data the service keeps for its whole life. `gcpause.py --full-scan` times one full collection alone, for three sizes of reference data:

```
full collection, median of 7, reference  50,000 rows (100,000 containers):   11.94 ms, frozen  0.000 ms
full collection, median of 7, reference 150,000 rows (300,000 containers):   27.43 ms, frozen  0.000 ms
full collection, median of 7, reference 300,000 rows (600,000 containers):   45.08 ms, frozen  0.001 ms
```

The pause grows with the containers that stay alive: 11.94 ms, 27.43 ms and 45.08 ms for 100,000, 300,000 and 600,000 of them. The request that triggers a full collection pays it. Every other request on the same event loop waits for it too. In the request runs at 300,000 rows, the longest full collections were 62.6 to 76.2 ms. They set the tail: in run 1 the slowest request of version A took 79.6 ms, and of version B 4.66 ms.

**Two fixes, and what each removes.**

1. **Keep fewer containers alive.** This is version B. It removes every collection the requests caused: young and full. It is a code change, and it helps any service.
2. **Freeze what lives for good.** `gc.freeze()` moves every object alive at that moment into a permanent generation that no collection scans. The service calls it once, after it builds its reference data, when you start it with `--freeze`. It keeps every young collection, but a full collection no longer scans the reference data. In the same runs the longest full collection fell to 0.2 to 0.4 ms. Full collections also became more frequent: 4 became 12 at 150,000 rows. After a freeze the old generation is small, so the 25% rule passes more often. The docs present it for servers that fork workers, and Instagram added it to CPython 3.7 for that reason.

**WRONG: count allocations with memray's defaults.** The obvious tool for "fewer allocations" is memray. With its default options it reported this, from the same log:

```
list    per request: memray default      52.6 allocations, with trace_python_allocators  115706.3; peak memory: memray    762 KiB, tracemalloc    762 KiB
stream  per request: memray default       0.0 allocations, with trace_python_allocators  118897.9; peak memory: memray     29 KiB, tracemalloc     28 KiB
```

By default, memray sees about 53 allocations per request for version A, and 0 for B. A's count is 2,200 times too low, and B's 0 is wrong outright. CPython's own allocator, pymalloc, serves most requests of 512 bytes or less from arenas it already holds. memray's docs say such small requests "won't appear in the profiler reports at all". Almost every Python object is that small.

**RIGHT: trace Python's allocator, and read the peak as well as the count.** With `trace_python_allocators=True`, memray counts 115,706 allocations per request for A and 118,898 for B. The peak memory tells the real difference: 762 KiB for A against 29 KiB for B. tracemalloc agrees on the peak. The allocation count is the wrong number for this question. The number of containers alive at once is the right one, and the peak is its closest measure.

**The same two facts on the live service.** Part B's lab changed the running service twice, five alternated rounds each at 60 requests per second. It counted allocations per request of the handler's CPU part offline, with memray and `trace_python_allocators`. From `runs/lab3-cpufix.log` and `runs/lab3-gcfix.log`:

| Change | Allocations per request | Collector time per run, median | p99 change, 95% interval |
|---|---|---|---|
| display text for 50 rows, not 1,200, on the service with one locked connection | 115,527 → 42,084 | 351 → 369 ms | −41.5%, −57.7% to +4.5% |
| keep 50 rows alive, not 1,200, on the service with a pool of four | 115,527 → 118,727 | 295 → 0 ms | −10.3%, −20.6% to −1.5% |

The first change removed almost two thirds of the allocations, and the collector's time did not fall. The second added 3% more allocations and removed the collector's time entirely. Its longest pause per run fell from 52 to 64 ms to under 0.5 ms, in `runs/lab3-metrics.log`. Its p99 was lower in all five rounds, by 1.3 to 12.5 ms, and the interval calls it real. It is a narrow call: the interval ends at −1.5%. An earlier session of the same rounds, before a change to the probes, did not show it. Its log was replaced. On the pool service the p99 is set mostly by the backend's exponential tail, about 37 ms, and the collector's pauses add a little above it. The offline runs above show the far tail they set: a slowest request of 79.6 ms with the list, and 4.66 ms with the stream. The first row's p99 moved for another reason, which section 3.6 explains.

Two limits of this section:

- **3.13 only.** Python 3.14.0 to 3.14.4 shipped a different, incremental collector. The What's New page for 3.14 says it was reverted to the 3.13 collector in 3.14.5, after reports of memory pressure. Pin the patch version next to any collector result.
- **The free-threaded build has another collector.** It is not generational, and it pauses every thread for each collection. This phase does not measure it.

**The sentence to remember:** the collector counts containers alive, not allocations made. A request that keeps fewer containers alive at once triggers fewer collections, and data that lives for good makes each full collection longer.

**The trap:** "fewer allocations" measured with memray's defaults. They miss every block of 512 bytes or less, which is almost every Python object, so the count says nothing about what the collector sees.

**Try this now:** run `uv run python phase03_profiling/gcpause.py --retained 300000 --modes list list+freeze --requests 2000`. Before you run it, predict the total number of collections for each mode. The arithmetic above gives one per request, 2,000, and freezing does not change it. The run in `runs/lab3-extras.log` gave 1,832 + 166 + 2 and 1,826 + 165 + 9: 2,000 each. The longest full collection was 104.8 ms against 0.2 ms.

---
## 🧪 Hands-on lab — part A

**Run status:** every command below was executed on the author's machine on 2026-09-25: an Apple M2 with 8 GB, macOS 15.7.8, CPython 3.13.3 through uv. Other programs were running, and each log records the load average. Each "Expected" line is copied from the logs in `runs/`. Your timings will differ. The counts, the ratios and the order of the views should not.

All commands run from `elite-performance/code/`. `runs/lab3.sh` runs every part and saves one log per part, for example `bash runs/lab3.sh P` writes `runs/lab3-profilers.log`. Each script starts its own service on a free port and stops only what it started.

- [ ] **E1 (offline).** Five views of one async handler, against the truth.
  - Run: `bash runs/lab3.sh P`, or once: `uv run python phase03_profiling/blind.py`.
  - Expected, over the three runs of the log: truth `wall   83.8` to `84.5 ms`, `cpu   3.0 ms`, `lock wait  58.9` to `59.1 ms`. cProfile `3.1 ms per request, 119 calls for 40 requests` in all three. yappi cpu clock `3.4` to `3.5 ms`. yappi wall clock `84.3` to `84.6 ms`, equal to the truth of its own run. pyinstrument in async mode shows `Lock.acquire` with 0.060 to 0.063 s, within 3 ms of that request's own measured wait: 63, 63 and 62 ms.
  - Then run `uv run python phase03_profiling/blind.py --concurrency 1`. Expected: `wall   24.8 ms`, `lock wait   0.0 ms`, and cProfile `80 calls for 40 requests`.
  - If it fails: `ModuleNotFoundError: yappi` means `uv sync` was not run.
  - Teaches: a CPU view and cProfile report the 3 ms of CPU and lose the waits. Only the wall clock, and the async profile of one request, see them.

- [ ] **E2 (break-it, offline).** Profile the async program the way the command line does.
  - Run: `uv run python phase03_profiling/blind.py --self-test --pyi-mode disabled`.
  - Expected: `AssertionError: async_mode=disabled: pyinstrument shows 0 ms in Lock.acquire, the request waited 63 ms`. The number of ms waited differs by run.
  - What broke: in `disabled` mode the request's 63 ms in the lock is not in its profile at all. This is the mode `pyinstrument script.py` always uses.
  - Teaches: an async profile must be started inside the task, in async mode.

- [ ] **E3 (local).** Running or waiting: the one ratio.
  - Run: `uv run python phase03_profiling/diagnose.py --rate 60 --duration 20 --seed 1 --no-profiles`. About 30 seconds.
  - Expected: `p99    124 ms`, `H1 CPU in the handler               15%`, `H2 waiting for the connection       63%`, `generator lag p99 2.32 ms`. The other two seeds gave H2 70% and 79%.
  - Then run it with `--config conns=4`. Expected: `H2 waiting for the connection        1%`, `H1 CPU in the handler               36%`, `p99   51.1 ms`.
  - If the generator lag p99 is above 10 ms, the run is invalid. Close other programs and run it again.
  - Teaches: CPU per request against time per request decides whether a CPU profile can help.

- [ ] **E4 (offline).** What sets the collector's cost.
  - Run: `bash runs/lab3.sh G`. About 5 minutes. It runs `gcpause.py` three times, then `--full-scan` and `--allocs`.
  - Expected: for list, `collections gen0  1830 gen1  166 gen2   4` at 150,000 rows, the same counts in all three runs. For stream, `collections gen0     0 gen1    0 gen2   0`. The full collection timed alone: `11.94 ms`, `27.43 ms` and `45.08 ms` for 50,000, 150,000 and 300,000 rows, and `0.000` to `0.001 ms` frozen. Allocations: `memray default      52.6 allocations, with trace_python_allocators  115706.3` for list.
  - Teaches: collections follow containers alive at once, and a full collection's pause follows what stays alive.

- [ ] **E5 (break-it, offline).** Make the stream keep every row, and watch the collector come back.
  - First keep a copy: `cp phase03_profiling/app.py /tmp/app.py.bak`.
  - Run: `sed -i '' 's/        for r in make_rows(cfg.n_rows, seed):$/        for r in list(make_rows(cfg.n_rows, seed)):/' phase03_profiling/app.py`, then `uv run python phase03_profiling/gcpause.py --self-test`.
  - Expected: `AssertionError: [550, 49, 1]`. The stream now triggers 600 collections in 600 requests, like the list.
  - Restore it with `cp /tmp/app.py.bak phase03_profiling/app.py`. Then `uv run python phase03_profiling/app.py --self-test` must print `self-test passed`.
  - Teaches: the stream helps because fewer rows are alive, not because it allocates less. One `list()` undoes it.

---

## 🔍 Check it yourself

1. Open `phase03_profiling/app.py:192`. This is `query`. The lock is taken two lines below, with `async with sh.conn`, and the backend await is inside that block. Move the await out of the block, as the lab's mutation check does. What happens to the wait histogram, and which self-test assertion fails?

2. Open `phase03_profiling/app.py:140`. This is `summarise`. In the stream branch, the heap holds tuples of `(value, -id, row)`. How many containers does the stream keep alive at most, and why is that still far below 2,000?

3. Open `phase03_profiling/blind.py:93`. This is where one request starts its own `Profiler`. Suppose the profiler started in `main` instead, before `asyncio.run`. What would the tree show for the lock, and why? Section 3.1 tells what happened when I tried it.

4. In any async Python service you own, run:

   ```bash
   grep -rnE "asyncio\.Lock\(|Semaphore\(|async with .*lock" <your repo>/
   ```

   For each lock, find the `await` calls inside its `async with` block. For each one, write down the time it can take, and the request rate that would keep that lock 70% busy.

---

## ✅ Checkpoint 3A — answer in your own words

1. **Walk through what each view shows.** A handler runs at p99 300 ms. Its CPU per request is 4 ms. cProfile ranks `json.dumps` first with 60% of the profiled time. (a) Why can cProfile not see where the other time went? (b) Which two views would you use next, and what would each show if the cause is a lock held across a database call?

2. **A colleague says:** "Our API runs at 25% CPU, so it cannot be CPU-bound. We should look at the database." Argue for or against, with the numbers from section 3.2.

3. **Show the arithmetic.** A handler builds 3,500 rows, each a dict with one list inside, and keeps them all until it returns. The service runs 40 requests per second. (a) How many young collections per request, and per second? (b) The service keeps 400,000 containers of reference data. Using the full-collection times of section 3.3, estimate the pause of one full collection. (c) What does `gc.freeze()` after start change, and what does it not change?

4. **This is broken.** A team changed a handler that built a list of 2,000 dicts, each with a list inside. The new code is a generator that keeps only the 20 rows it returns. They wanted to allocate less. memray, run with its defaults, reported about 0 allocations per request before and after. They called the change useless and reverted it. What did they measure wrong? What should they have measured, and what do the numbers of section 3.3 predict for the collector?

5. **Given these constraints, design** the always-on probes for a new async service. Nothing may cost more than 1% of CPU. List what you record, where you put each probe, and which question each answers.

<details>
<summary>Answer sketches</summary>

1. (a) cProfile counts time between call and return events. An await is a return, so the time a coroutine is suspended belongs to no function. The ratio needs the handler's mean, not its p99, so measure that first. Even if the mean were only 30 ms, 4 ms of CPU would be 13% of it: most of the time is waiting. (b) A wait histogram around the lock's acquire, always on, and pyinstrument in async mode on one slow request, started inside its task. If the cause is the lock, the histogram shows a wait near the latency, and the profile shows `Lock.acquire`, `[await]`, with most of the request's time.

2. Against. Process CPU mixes in the time when no request is in the process. In section 3.2, a handler that was all CPU used 107% of its handler time on CPU while the process used 18% of a core. The right number is CPU per request against time per request. In the lab service it was 8 to 15% against 63 to 79% for the lock: waiting, but not on the database.

3. (a) 3,500 × 2 = 7,000 containers alive at once. The counter resets after each collection at 2,001, 4,002 and 6,003, so 3 per request, as `app.py`'s self-test asserts. At 40 per second, 120 young collections per second, and one gen1 collection every 10 of them. (b) The lab timed one full collection at 27.43 ms for 300,000 containers and 45.08 ms for 600,000. A straight line between them gives 27.43 + (45.08 − 27.43) / 3 = 33.3 ms for 400,000, on that laptop. Measure it: `gcpause.py --full-scan --retained 200000`. (c) Freezing moves the reference data out of every collection, so full collections become short. It does not change the 3 young collections per request, because the rows are created after the freeze.

4. memray's defaults miss most allocations that pymalloc serves, those of 512 bytes or less, which is almost every Python object: 52.6 per request against 115,706 with `trace_python_allocators` in the lab. Even the right count would barely move: the lab's stream made 118,898, 3% more. The right measures are the peak memory, 762 KiB against 29 KiB, and the collections per request from `gc.callbacks`. 2,000 rows are 4,000 containers alive at once. The counter passes 2,000 once, at the 2,001st. The next collection would need 4,002, so 1 collection per request, the same as for 1,200 rows. The generator keeps about 60 alive and triggers none. In the live lab the same kind of change took the collector from 295 ms per run to 0, and its longest pauses from 52 to 64 ms to under 0.5 ms.

5. Record, as histograms: the wait and hold of every lock and pool, around each acquire. The event loop's lag, from a task that sleeps 5 ms. Every collector pause, from `gc.callbacks`, by generation. CPU per request, from the process CPU clock divided by requests. The handler's own time. Each costs one or two `perf_counter` calls per event. They answer: is the request waiting, and for which resource. Is the loop late. Did the collector stop it. Profilers stay off, and run on one request, in async mode, when a question needs them.

</details>

---

## References & Further Learning — part A

Every URL below was fetched on 2026-09-25 and returned HTTP 200.

**What each profiler measures**

- **The Python Profilers, Python 3.13 documentation** — https://docs.python.org/3.13/library/profile.html
  Focus on: "What Is Deterministic Profiling?" and "Limitations". The page never mentions asyncio or threads.
- **CPython `Modules/_lsprof.c` at tag v3.13.3** — https://raw.githubusercontent.com/python/cpython/v3.13.3/Modules/_lsprof.c
  Focus on: lines 715 to 723, the `sys.monitoring` events cProfile registers. `PY_YIELD` maps to the return callback, which is why an await ends a call.
- **PEP 669, Low Impact Monitoring for CPython** — https://peps.python.org/pep-0669/
  Focus on: events are per interpreter, not per thread. cProfile uses them since 3.12.
- **pyinstrument 5.1.3, `profiler.py`** — https://raw.githubusercontent.com/joerick/pyinstrument/v5.1.3/pyinstrument/profiler.py
  Focus on: the `async_mode` docstring, with the meaning of `enabled`, `disabled` and `strict`.
- **pyinstrument 5.1.3, `__main__.py`** — https://raw.githubusercontent.com/joerick/pyinstrument/v5.1.3/pyinstrument/__main__.py
  Focus on: lines 385 to 391, where the command line builds its profiler with `async_mode="disabled"`.
- **pyinstrument 5.1.3, "How it works" and the user guide** — https://raw.githubusercontent.com/joerick/pyinstrument/v5.1.3/docs/how-it-works.md
  Focus on: 1 ms sampling on the profile hook, and the wall clock. The guide, https://raw.githubusercontent.com/joerick/pyinstrument/v5.1.3/docs/guide.md, has the FastAPI middleware section 3.2 copies.
- **yappi 1.7.6, "Coroutine profiling"** — https://raw.githubusercontent.com/sumerc/yappi/v1.7.6/doc/coroutine-profiling.md
  Focus on: why a hook sees a yield as a return, and how the wall clock fixes the time and the call count.
- **py-spy 0.4.2 README** — https://raw.githubusercontent.com/benfred/py-spy/v0.4.2/README.md
  Focus on: root on macOS, `--idle` and `--gil`.
- **`profiling.sampling`, Python 3.15 documentation** — https://docs.python.org/3.15/library/profiling.sampling.html
  Focus on: the wall, CPU and GIL modes, and `--async-aware`. For 3.15.0rc2, not a final release.
- **Berger, Stern, Pizzorno, "Triangulating Python Performance Issues with Scalene", OSDI 2023** — https://ar5iv.labs.arxiv.org/html/2212.07597
  Focus on: Section 6.4 and Table 3, the overhead of nine profilers on the same benchmarks, on CPython 3.10.9 and Linux. Older than `sys.monitoring`.
- **Brendan Gregg, "Off-CPU Analysis"** — https://www.brendangregg.com/offcpuanalysis.html
  Focus on: the first section, the same blind spot outside Python.

**The garbage collector and allocations**

- **CPython `Doc/library/gc.rst` at tag v3.13.0** — https://raw.githubusercontent.com/python/cpython/v3.13.0/Doc/library/gc.rst
  Focus on: `set_threshold`, the trigger rule, `freeze`, and the keys `gc.callbacks` passes.
- **CPython `Python/gc.c` at tag v3.13.0** — https://raw.githubusercontent.com/python/cpython/v3.13.0/Python/gc.c
  Focus on: line 1819, the counter, line 1946, the decrement, line 1342, the reset, and line 1264, the 25% rule for a full collection.
- **CPython `Include/internal/pycore_runtime_init.h` at tag v3.13.0** — https://raw.githubusercontent.com/python/cpython/v3.13.0/Include/internal/pycore_runtime_init.h
  Focus on: lines 233 to 235, the thresholds 2000, 10 and 10.
- **CPython "Garbage collector design", InternalDocs at tag v3.14.7** — https://raw.githubusercontent.com/python/cpython/v3.14.7/InternalDocs/garbage_collector.md
  Focus on: containers, generations and the free-threaded collector. It describes 3.14.
- **What's New in Python 3.14** — https://docs.python.org/3.14/whatsnew/3.14.html
  Focus on: "Garbage collection", and the note that 3.14.5 reverted the incremental collector of 3.14.0 to 3.14.4.
- **Matt Hooks, "Scaling stories at Rippling: The garbage collector fights back", Rippling, updated April 2024** — https://www.rippling.com/blog/the-garbage-collector-fights-back
  Focus on: how a `gc.callbacks` timer found multi-second pauses behind a 3 s p99, and the two fixes with their numbers. A production write-up. It does not state the Python version.
- **Alec Rosenbaum, "Taming Python GC for Faster Web Requests", Close, 2024** — https://making.close.com/posts/taming-the-python-gc/
  Focus on: freezing, then raising threshold0, and the share of runtime the collector took before and after. Written for a version whose threshold0 was 700.
- **Zekun Li, "Copy-on-write friendly Python garbage collection", Instagram, 2017, archived copy** — https://web.archive.org/web/20191201075913/https://instagram-engineering.com/copy-on-write-friendly-python-garbage-collection-ad6ed5233ddf
  Focus on: why `gc.freeze()` exists. The original page no longer loads.
- **memray 1.20.0, "Python allocators"** — https://raw.githubusercontent.com/bloomberg/memray/v1.20.0/docs/python_allocators.rst
  Focus on: why small allocations are invisible without `--trace-python-allocators`.
- **tracemalloc, Python 3.13 documentation** — https://docs.python.org/3.13/library/tracemalloc.html
  Focus on: `get_traced_memory`. The docs give no overhead number.

---

## Cheatsheet — part A

```
WHICH VIEW SEES WHAT                       macOS, CPython 3.13, no sudo
  cProfile        running code. An await = a return: waits lost, resumes = calls
  yappi cpu       CPU per thread. No waiting. Live: 52 of ~180 requests done
  yappi wall      wall time across awaits. A cost on every call
  pyinstrument    Profiler(async_mode="enabled") INSIDE the task: names each await
                  CLI and "disabled": event loop select + other requests' CPU
  py-spy          needs root on macOS. --idle keeps waiting threads
  blind.py        truth 83.9 ms wall, 3.0 ms CPU. cProfile 3.1, yappi wall 84.4

RUNNING OR WAITING
  CPU per request / handler time    NOT process CPU %
  /report at 60/s                   CPU 8-15%, lock wait 63-79% of handler time
  find the wait                     wait histogram + one request in async mode

THE COLLECTOR, 3.13
  trigger         containers allocated − freed > 2000 (3.12: 700)
  gen1, gen2      every 10 of the younger; full only if promoted > 25% of old
  per request     containers ALIVE at once / 2001, floored: 1,200 rows → 1
  full pause      grows with what stays alive: 11.9 / 27.4 / 45.1 ms
                  for 100k / 300k / 600k containers. gc.freeze(): ~0 ms
  memray          --trace-python-allocators, or small blocks are invisible
  live            stream rows: collector 295 → 0 ms per run, p99 −10.3%
```

Part B, sections 3.4 to 3.7, times the waits no profiler records. Then it finds the cause of the slow `/report`, fixes it, and proves the fix.

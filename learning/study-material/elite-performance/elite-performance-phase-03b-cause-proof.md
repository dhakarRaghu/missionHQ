# Phase 3B — Profiling Python systems: from symptom to proof

**The question this phase answers:** when the service is slow, how do you find the line of code responsible in under an hour, and prove the fix helped?

Part A showed what each view can see. A CPU profile sees running code. A wall-clock view that follows the await sees waiting. `gc.callbacks` sees collector pauses. Part A is a prerequisite. This part uses its service and probes without explaining them again.

This part puts the views to work. It times the waits no profiler records, adds a timeline, then finds the cause of the slow `/report` with one measurement per hypothesis, and fixes it. Last, it proves the fix with the measurement that found the problem. It teaches the fourth idea of Phase 3, and it applies the second to locks, the GIL and a timeline:

2. **A handler whose CPU per request is small next to its latency is waiting**. Only a wall-clock view that follows the await shows where: an async profile of one request, a timed lock, or a timeline of spans. For the GIL, the view is the event loop's lag.
4. **A fix is proven by the latency distribution at fixed throughput**, measured the way the problem was found, with errors and memory checked for regression.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, the previous document: what each view can see                    │
│  3.1  The profilers and what each is blind to                            │
│  3.2  Wall-clock versus CPU time                                         │
│  3.3  Allocations and the garbage collector                              │
│                                                                          │
│ PART B, this document: from symptom to proof                             │
│  3.4  Lock and GIL contention                 — timing the wait yourself │
│  3.5  The timeline: tracing the event loop    — the order of events      │
│  3.6  Symptom versus root cause               — one measurement each     │
│  3.7  Proving a fix                           — the proof that holds     │
│  Lab: E6 to E12                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**What this part assumes.** Part A, and three sections of Phase 1. Section 1.2 gives open-loop load, measured from the due time, and the validity rule. Section 1.4 gives the interval from resampling runs, then requests. Section 1.5 gives the prediction sheet. Section 3.7 uses `phase01_measure/compare_runs.py` as it is. Section 3.4 also uses Phase 2, section 2.3, "Pools that fill": a lock is a pool with one connection.

**Where it runs, and what it costs.** On your laptop, at no cost. The machine and versions are those of part A. The load runs of this part ran on 2026-09-25 from 16:12 to 16:29, on battery, with other work on the same laptop. The 1-minute load average was 2.69 to 4.28, and each log records its conditions. Because the laptop was busy, every comparison here alternates its runs, and the main one includes a no-change control.

Time for part B: 75 minutes of reading, plus about 25 minutes of waiting for load runs.

---

## 3.4 — Lock and GIL contention (timing the waits no profiler records)

Why this matters: Go ships a mutex profile and a block profile. CPython ships neither. `asyncio.Lock` and `threading.Lock` keep no count of waits. The GIL, the lock that lets one thread run Python bytecode at a time, reports nothing either. So you measure these waits yourself.

**Answer this first.** Two questions. First: the `/report` lock of section 3.2 is held about 8.5 ms per request, and requests arrive at about 60 per second. How busy is the lock: 51%, or more? Second: an asyncio service does almost nothing, so its event loop wakes up on time. Someone adds a background thread that runs a pure-Python loop, to refresh a cache. The switch interval, the time a thread may keep the GIL while another waits for it, is 5 ms. By how much is the event loop late now: under 1 ms, about 5 ms, or more?

### The lock: time the acquire, and measure the whole turn

**Measure the wait around the acquire.** The service's query holds one shared connection behind an `asyncio.Lock`. It takes a timestamp before `async with` and one after, and records the difference in a histogram. It also records how long the lock was held, and one more interval, explained below. From `phase03_profiling/app.py`, in `query`:

```python
# from phase03_profiling/app.py:192, the query of /report. Comments shortened, logic unchanged
async def query(sh: Shared, cfg: Config, probe: Probe) -> None:
    asked = time.perf_counter()
    async with sh.conn:
        got = time.perf_counter()
        record(probe.conn_wait, max(1e-6, got - asked))
        if sh.released > asked:
            # This request waited, and a release woke it: the handoff.
            probe.handoff.add(got - sh.released)
        mean = cfg.fetch_ms / 1000
        # The lock is held across this await. That is the slow part.
        await asyncio.sleep(mean if cfg.fetch_dist == "fixed" else sh.backend.expovariate(1 / mean))
        held = time.perf_counter() - got
        record(probe.conn_hold, held)
        probe.hold.add(held)
    sh.released = time.perf_counter()
```

**A turn of the lock is longer than its hold.** Look at what runs between one holder and the next:

1. The holder leaves `async with`. `Lock.release` calls `fut.set_result(True)` on the first waiter's future: line 155 of `Lib/asyncio/locks.py` at tag v3.13.3. That only schedules the waiter to run later, on the loop.
2. The holder keeps running. `report()` awaits `query()` and then calls `encode(summarise(...))`, with no await in between. So the holder runs its own summarise, 1,200 rows, and starts its reply before it gives the loop back.
3. Only then can the loop run the waiter. A new arrival cannot take the free lock meanwhile: the fast path of `acquire`, line 98, is taken only when nobody is waiting.

So one turn of the lock is the hold plus the **handoff**: the time from a release to the next acquire. `query` stamps each release, and a request that a release woke records the difference.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One turn of the lock on /report. Numbers from runs/lab3-diagnose.log     │
├──────────────────────────────────────────────────────────────────────────┤
│ request A   acquire ─► await the backend ─► release ─► summarise, reply  │
│                                                        the loop is A's   │
│ request B   waiting in Lock.acquire ───────────────────────────► runs    │
├──────────────────────────────────────────────────────────────────────────┤
│ hold      acquire to release. Measured: 8.14 to 8.94 ms                  │
│ handoff   release to the next acquire. Measured: 4.45 to 4.58 ms         │
│ turn      hold + handoff: about 12.7 to 13.5 ms                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**The model: one server with general turns, M/G/1.** M/G/1 is the name of a queue with Poisson arrivals, one server, and turns of any distribution. Requests arrive at rate λ, the rate the generator sent. One turn S is the hold plus the handoff. ρ, the share of time the lock is busy, is λ × E[S], where E[S] is the mean turn. For such a queue the Pollaczek-Khinchine formula gives the mean wait:

```
mean wait W = λ × E[S²] / (2 × (1 − ρ))
E[S²] = E[H²] + 2 × E[H] × E[C] + E[C²]    for hold H and handoff C, independent
```

E[S²] is the mean of the square of a turn: long turns count more. The model counts a handoff in every turn, which overstates the load a little: a request that finds the lock free pays none. `app.py`'s self-test checks the formula against exponential and fixed turns, whose waits have closed forms.

Here is clean run 1 worked by hand, with two assumptions. The hold is exponential, so E[H²] = 2 × E[H]². The handoff is fixed, so E[C²] = E[C]².

1. λ = 57.0 per second, the rate that seed sent. E[H] = 8.14 ms, E[C] = 4.58 ms.
2. E[S] = 8.14 + 4.58 = 12.72 ms. ρ = 0.0570 per ms × 12.72 ms = 0.725: the lock is busy 73% of the time, not 46%.
3. E[S²] = 2 × 8.14² + 2 × 8.14 × 4.58 + 4.58² = 132.5 + 74.6 + 21.0 = 228.1 ms².
4. W = 0.0570 × 228.1 / (2 × 0.275) = 13.00 / 0.550 = 23.6 ms.

`diagnose.py` does the same with the measured second moments, and prints the prediction next to the measured wait. From `runs/lab3-diagnose.log`:

```
lock as M/G/1: 57.0/s x (8.14 ms hold + 4.58 ms handoff) = 73% busy; predicted mean wait 23.2 ms, measured 21.6 ms
lock as M/G/1: 62.1/s x (8.60 ms hold + 4.45 ms handoff) = 81% busy; predicted mean wait 39.5 ms, measured 30.9 ms
lock as M/G/1: 59.8/s x (8.94 ms hold + 4.57 ms handoff) = 81% busy; predicted mean wait 41.0 ms, measured 51.9 ms
```

One run lands within 7% of the model. Of the other two, one waited 22% less than predicted and one 27% more. The model leaves out the collector's pauses and the laptop's other work, which lengthen some turns, and the spread of one 20-second run is wide near 80% busy.

My first version of this section used the hold alone. That gave 60 × 8.5 ms = 51% busy, and an M/M/1 wait of 0.51 / 0.49 × 8.5 = 8.8 ms, far below every measured wait. The review pointed at the code, and measuring the handoff turned that gap into a prediction.

**The test of the mechanism.** If the handoff is the releaser's own CPU, one change should remove it. Give the loop back right after the release, with `await asyncio.sleep(0)`. The woken waiter then starts its backend call before the releaser runs its summarise. `--yield-release` does exactly that. The model predicts a handoff near 0, a lock about 50% busy, and a wait near 10 ms. Three clean runs, in `runs/lab3-handoff.log`, gave a handoff of 0.03 ms and a lock 50 to 57% busy. The predicted waits were 7.5, 10.4 and 10.6 ms. The measured waits were 8.5, 8.7 and 12.3 ms. The mean wait fell from 21.6 to 51.9 ms to 8.5 to 12.3 ms, as predicted. The client p99 fell from 124, 155 and 263 ms to 79.6, 73.0 and 119 ms, same seed for same seed. One `await` in the right place removed about a third of the lock's load. It does not remove the lock: section 3.6 does that.

**Three rules for any lock or pool in an async service:**

1. Record wait, hold and handoff, always on. A few `perf_counter` calls cost far less than any profiler.
2. Never hold a lock across an `await` of the network, unless the lock exists to serialise that call.
3. Read the lock as a queue with one server, as Phase 2, section 2.3, "Pools that fill", reads a pool: busy share = rate × turn. Near 80% busy, a small change in the turn moves the wait a lot.

### The GIL: read it through the event loop's lag

**How a thread gets the GIL.** The notes at the top of `Python/ceval_gil.c`, tag v3.13.0, describe it. A thread that wants the GIL waits one switch interval. Then it sets a request to drop the GIL. The thread that holds it checks that request between bytecodes, and gives the GIL up. The interval is 5,000 microseconds, `DEFAULT_INTERVAL` on line 153. The `sys` docs add that the real wait "can be higher" when long-running internal functions are used.

The event loop gives the GIL away every time it waits for I/O, in the `select` call. When `select` returns, the loop's thread must take the GIL back before it can run a single line. A thread running Python holds it, so the loop waits up to one interval. This is the convoy effect that David Beazley reported in 2010, in CPython issue 52194. The issue was closed as "wont fix".

`gil.py` measures it. An event loop wakes every 1 ms and records how late it is. A second thread does one of four things. With `--time-select`, it also times the loop's own `select` call. It uses a subclass of the default selector, with `perf_counter` around `select`, on the loop's thread only. From `runs/lab3-gil.log`, run 1. The lines for `python` at 1 ms and for `c-release` are left out here. The chart below uses them:

```bash
uv run python phase03_profiling/gil.py --time-select
```

```
one sort of 300,000 floats alone: 58 ms; default switch interval 5 ms
none      switch 5 ms: ticks  1514, loop lag p50    0.32 ms  p99    0.48 ms  max    7.94 ms, loop thread on CPU   5%, in select  97%
python    switch 5 ms: ticks   131, loop lag p50   14.05 ms  p99   15.36 ms  max   15.38 ms, loop thread on CPU   0%, in select 100%
c-hold    switch 5 ms: ticks    18, loop lag p50  115.65 ms  p99  119.23 ms  max  119.23 ms, loop thread on CPU   0%, in select 100%
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ How late the event loop wakes, p50. gil.py, run 1                        │
├──────────────────────────────────────────────────────────────────────────┤
│ no thread                     ▏ 0.32 ms                                  │
│ C call releasing the GIL      ▏ 0.28 ms                                  │
│ Python thread, interval 1 ms  █ 3.32 ms                                  │
│ Python thread, interval 5 ms  ███ 14.05 ms                               │
│ C call holding the GIL        ███████████████████████ 115.65 ms          │
├──────────────────────────────────────────────────────────────────────────┤
│ one bar character = 5 ms                                                 │
└──────────────────────────────────────────────────────────────────────────┘
```

Four findings:

1. **A Python thread made the loop 44 to 45 times later** at the default interval. The median lag was 14.05 to 14.06 ms per wake-up in the three runs, against 0.31 to 0.32 ms with no thread. That is about 2.8 switch intervals, not one. The likely reason is that one wake-up of the loop passes through `select` more than once, and pays the wait each time. Inferred, not counted: `gil.py` does not count the GIL handovers.
2. **A shorter interval shortens the wait, and does not remove it.** At `sys.setswitchinterval(0.001)` the median was 3.31 to 3.32 ms, again about three intervals. More switches cost more CPU for both threads.
3. **C code that holds the GIL blocks the loop for its whole length.** `sorted()` of 300,000 floats never checks for a drop request until it returns. With it running in the other thread, the loop's median lag was 114.94 to 117.38 ms. One sort alone took 58 to 60 ms, so the loop waited for about two sorts per wake-up. C code that releases the GIL, `hashlib.sha256` of 32 MB, left the loop at 0.28 ms, no later than with no thread.
4. **The loop's thread was waiting, not working.** It spent 0% of the wall time on a CPU, by its own thread clock. It spent 100% of the wall time inside `select`, timed on its own thread. The idle loop, with no second thread, spent 97% there. The GIL is taken back inside `select`, as `kqueue.control` returns. So a loop that waits for the GIL looks like an idle loop.

**WRONG: read the loop thread's time by function.** In run 1 the loop was 14.05 ms late at the median wake-up. Its time was 100% in `select`, and its CPU clock read 0%. The idle loop reads 97% and 5%. Any profile that splits the loop thread's time by function shows the same picture, and hides the problem.

My first version of `gil.py` read that share from cProfile, and printed 0% for the C call that holds the GIL. On 3.12 and later cProfile takes events from every thread, so one profile mixes both threads. The timer on `select` replaced it.

**RIGHT: measure how late the loop wakes.** A task that sleeps a fixed time and records how late it wakes is the event loop's own latency. The course service runs one, `lag_monitor` in `app.py`, with a 5 ms tick. Any cost on the loop's thread shows in it: CPU in another request, a collector pause, a GIL wait. It does not say which one, so you pair it with the other probes: the collector's pauses, the lock's wait, and the CPU per request.

Where this section stops: `py-spy top --gil` shows which thread holds the GIL, but it needs root on macOS, and this lab did not run it. Phase 4, section 4.1, covers what the GIL guarantees, and the free-threaded build without it.

**The sentence to remember:** a lock or the GIL makes a request wait without using CPU. Time the wait yourself: around the acquire for a lock, and as the event loop's lag for the GIL.

**The trap:** a background thread of pure Python beside an asyncio loop. The loop's own profile says idle, its CPU says idle, and every request pays two or three switch intervals per wake-up.

**Try this now:** run `uv run python phase03_profiling/gil.py --kinds python --switch-ms 5 2 1 0.5`. Predict the median lag for each interval before you look. The run in `runs/lab3-extras.log` gave 14.07, 6.32, 3.32 and 1.82 ms: about three intervals each time, at every interval.

---

## 3.5 — The timeline: tracing the event loop (which request waited, for what, and behind whom)

Why this matters: a profile adds time up. It can say that requests spent 77% of their time waiting for a lock. It cannot say who held the loop while they waited. On one event loop, the cause of a wait is often another request, and only a timeline keeps the order that shows it.

**Answer this first.** Six requests start 3 ms apart. Each takes a lock, awaits an 8 ms backend call, releases the lock, and then summarises its rows. Request 1 also makes a blocking call of 150 ms, after it releases the lock. The spans of requests 2 to 5 say they spent about 180 to 220 ms in "waiting for the lock". Is the lock the cause?

**What Python 3.13 gives you on a Mac without root.** Go has an execution tracer. CPython 3.13 has none that runs without root on macOS, and Python 3.14's `python -m asyncio ps` needs attach rights. So this timeline is built inside the process from three pieces:

1. **Spans.** A span is a named interval with a start, an end and a parent. The current span is kept in a `contextvars.ContextVar`. asyncio copies the context into every task, so each task has its own current span, and a span opened before an await is still the parent after it. OpenTelemetry keeps its current span the same way.
2. **gc.callbacks**, with the time of each collection.
3. **asyncio debug mode.** It logs every callback that holds the loop longer than `loop.slow_callback_duration`, 0.1 s by default, from `Lib/asyncio/base_events.py` line 437 at tag v3.13.3. Turn it on with `PYTHONASYNCIODEBUG=1` or `asyncio.run(..., debug=True)`.

`timeline.py` runs the six requests from the question, with the same summarise step as the service, and draws one row per request. From `runs/lab3-timeline.log`:

```bash
uv run python phase03_profiling/timeline.py
```

```
req  0 |===#
req  1 | ...==BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB#
req  2 |  .............................................===#
req  3 |    ...............................................===#
req  4 |    ...................................................==#
req  5 |    ......................................................===#
gc     |   g                                           g   g  g   g  g
        0 ms                                                 248 ms, one character = 4 ms
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ How to read the timeline above                                           │
├──────────────────────────────────────────────────────────────────────────┤
│ .   the request is inside its "waiting for the lock" span                │
│ =   awaiting the backend, holding the lock                               │
│ #   running summarise on the loop                                        │
│ B   request 1's blocking call, time.sleep(0.15), inside a coroutine      │
│ g   (bottom row) a collection shorter than one character, 4 ms           │
├──────────────────────────────────────────────────────────────────────────┤
│ Read down one column: at any moment, only one row can show # or B.       │
│ That is the event loop: one queue, one server.                           │
└──────────────────────────────────────────────────────────────────────────┘
```

**Read the column, not the row.** Request 1 released the lock before its blocking call. So from that moment the lock was free. Yet requests 2 to 5 stayed in "waiting for the lock" for the whole length of the B. The lock was free. The loop was not: the task that should take the lock next could not run until `time.sleep` returned. The span's name says lock. The column says blocking call. Every span name tells you where a request was, never why it stayed there.

Rows 2 to 5 drew 45, 47, 51 and 54 dots, at 4 ms each: 180 to 216 ms in "waiting for the lock". The spans add up the same way a profile would. Of 1,044 ms of request time, 77% was in "waiting for the lock", 15% in the blocking call, 6% in the backend and 2% in summarise. Those shares, without the columns, would send you to the lock.

The same run printed the lock's turns:

```
lock turns: backend mean 9.9 ms; handoffs, release to the next acquire: 3.5 3.7 4.3 4.4 166.2 ms
```

Four handoffs of 3.5 to 4.4 ms are the releaser's summarise, as in section 3.4. You can see it in the first two rows: request 1's `==` starts only after request 0's `#`. The fifth handoff, 166.2 ms, is the blocking call. The lock was free for all of it.

Debug mode found the cause directly:

```
Executing <Task finished name='Task-3' coro=<program.<locals>.one() ...> took 0.166 seconds
```

The log names the task and the time. The time is more than 150 ms, because a callback is the whole step between two awaits: the block, then the summarise that followed it. Debug mode sees only callbacks that hold the loop. It never sees a request that waits at an await. So it is the opposite check to the lock histogram, and you need both.

**WRONG: keep the current span in one plain attribute.** It works in a test with one request. Here is what `timeline.py --self-test --no-contextvar` reports with six:

```
AssertionError: (Span(id=4, parent=3, name='request', start=0.008555415901355445, end=0.19377166591584682, request=1), Span(id=3, parent=1, name='back
```

`lab3.sh` cuts the line at 150 characters. Request 1's root span got a parent: a `backend` span of request 0. Request 1 started while request 0 was inside its backend await, and the one shared attribute still pointed at request 0's span. In a tracing backend, request 1 would appear as a part of request 0.

**RIGHT: one `ContextVar`, and reset it with its token.** From `phase03_profiling/timeline.py`:

```python
# from phase03_profiling/timeline.py:100, Tracer.span. One indent level removed, logic unchanged
@contextlib.contextmanager
def span(self, name: str, request: int = -1):
    parent = self.current.get()
    s = Span(next(self.ids), parent.id if parent else None, name,
             time.perf_counter() - self.t0,
             request=request if request >= 0 else (parent.request if parent else -1))
    token = self.current.set(s)
    try:
        yield s
    finally:
        s.end = time.perf_counter() - self.t0
        self.current.reset(token)
        self.spans.append(s)
```

The self-test checks every span of six concurrent requests: each request span is a root, and each child's parent is its own request.

The limit of spans: a span sees only what happens after it opens. A request that waits in a queue before the first line of your handler has no span for that wait. The client's own timer, from the due time, covers it.

**The sentence to remember:** a timeline keeps the order a profile throws away. Read a wait by what else was running at the same moment, not by the name of the span.

**The trap:** trusting the name of a wait. The spans said "waiting for the lock" for up to 216 ms while the lock was free. The cause was a blocking call in another request.

**Try this now:** run `uv run python phase03_profiling/timeline.py --block-request -1`. With no blocking call, predict request 5's row of dots. Request 5 is sixth in line, and it starts 15 ms after request 0. Five turns go before it, each a backend call and a handoff. The run in `runs/lab3-extras.log` printed a backend mean of 9.8 ms and handoffs of 3.5 to 3.7 ms: about 13.3 ms per turn. So request 5 acquires about 5 × 13.3 = 66.5 ms after request 0, and waits 66.5 − 15 = 51.5 ms. The log drew 13 dots, 52 ms, at 4 ms per dot.

---

## 3.6 — Symptom versus root cause (one hypothesis, one measurement)

Why this matters: a symptom is what you see, such as a slow p99 or a hot function. A root cause is the one thing whose removal makes the symptom go away. A profile points at symptoms. If you fix what it points at without a hypothesis and a prediction, you can ship a real speed-up that changes nothing the user feels.

Astronomer published such a case about the Airflow scheduler. A py-spy profile showed 26.9% of its time building SQL strings. Fixing that made a test mode 2.70 times faster, and real runs "x1.01". The time was in starting a new Python process per task, which the profile could not see. Replacing it with `os.fork()` gave 9.55 times.

**Answer this first.** Section 3.2's cProfile ranks `label`, the display-text formatting, first after the idle `select`. A teammate formats text only for the 50 rows in the reply, and CPU per request falls by 30%. Predict the p99 change at 60 requests per second, and say whether five alternated rounds will call it real.

**The method: write the hypotheses down, with the measurement that can see each one.** Every hypothesis makes a prediction. Each prediction can be checked by exactly one view. Write the list before any fix:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The hypothesis loop                                                      │
├──────────────────────────────────────────────────────────────────────────┤
│ 1  write every hypothesis, one line each, before looking at code         │
│ 2  for each, write what it predicts, and which view can see it:          │
│    CPU per request, a wait histogram, collector pauses, the loop lag     │
│ 3  measure all of them in ONE clean run, with no profiler on             │
│ 4  strike the hypotheses whose prediction failed                         │
│ 5  for the one left, predict the effect of the fix, in numbers           │
│ 6  fix ONE thing, and prove it: section 3.7                              │
│ 7  if the proof misses the prediction, the hypothesis was incomplete:    │
│    go back to 1 with what you learned                                    │
└──────────────────────────────────────────────────────────────────────────┘
```

The sheet for `/report`, filled from the three clean runs of `runs/lab3-diagnose.log`:

```markdown
HYPOTHESIS SHEET: GET /report, 60 requests per second, open-loop, 2026-09-25

Symptom:  client p99 124 to 263 ms. Process CPU 28 to 29% of a core.

H1 CPU in the handler.
   Predicts: CPU per request close to handler time.
   View:     process CPU / requests, against the handler's own timer.
   Result:   4.78 to 5.01 ms of CPU against 34.4 to 65.4 ms: 8 to 15%.
H2 waiting for the one connection.
   Predicts: a lock wait close to handler time.
   View:     the wait histogram around the acquire, and the M/G/1 model.
   Result:   mean wait 21.6 to 51.9 ms: 63 to 79% of handler time.
             Model: 73 to 81% busy, predicted wait 23.2 to 41.0 ms.
H3 collector pauses.
   Predicts: pauses as long as the tail, and loop lag at the same size.
   View:     gc.callbacks, and the event-loop lag.
   Result:   1% of handler time. Longest pauses 44 to 72 ms: part of the far tail.
H4 the load generator. Predicts generator lag p99 above 10 ms.
   Result:   2.20 to 2.32 ms. Struck.

Root cause: one connection behind a Lock, held across the backend await.
Fix:        a pool of 4 connections.
Prediction: lock wait near 0. p99 near the backend's own p99 plus the CPU:
            8 ms × ln 100 + 5 ms = 36.8 + 5 = 42 ms.
            CPU per request unchanged. Collector time unchanged.
```

The backend's time is exponential with a mean of 8 ms, so its p99 is 8 × ln 100 = 36.8 ms.

**Both fixes, measured the same way.** `prove.py` ran each fix against the baseline in five alternated rounds at 60 requests per second. The p99 per run, in `runs/lab3-cpufix.log`, was 119.3, 156.0, 263.7, 271.3 and 169.9 ms before the CPU fix and 100.9, 130.9, 211.2, 101.7 and 119.2 ms after. In `runs/lab3-prove.log` the pool fix took 116.0 to 244.3 ms to 47.9 to 51.9 ms.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ p99 change against the same baseline settings, with its 95% interval     │
├──────────────────────────────────────────────────────────────────────────┤
│            -90%            -50%                0            +40%         │
│ CPU fix                 ├─────●──────────────────┤                       │
│                                                │                         │
│ pool fix       ├──●───┤                        │                         │
│                                                                          │
│ CPU fix   −41.5%, from −57.7% to +4.5%                                   │
│ pool fix  −72.0%, from −78.8% to −62.5%                                  │
├──────────────────────────────────────────────────────────────────────────┤
│ Interval from resampling runs, then requests. Five rounds each.          │
│ The CPU fix's interval crosses zero: not shown. The pool's does not.     │
└──────────────────────────────────────────────────────────────────────────┘
```

The CPU fix did what it promised to CPU: 4.88 ms per request became 3.41 ms, medians over the five runs. Its p99 point estimate was −41.5%. The p99 was lower in each of its five paired rounds, by 18.4 to 169.6 ms. But `compare_runs`'s interval ignores the pairing, and runs from −57.7% to +4.5%. With five rounds it cannot call the change real. The pool fix cut the p99 by 72.0%, with an interval from −78.8% to −62.5%, and left CPU per request at 4.66 ms.

**Why a CPU fix moved a lock's wait: the model predicts it.** H1 said CPU was 8 to 15% of handler time. Removing 30% of it saves about 1.5 ms of CPU per request. Yet the p99 moved by tens of milliseconds. Section 3.4 gives the reason: the releaser's summarise is part of every turn of the lock. Formatting 50 rows instead of 1,200 shortens that summarise, so it shortens the handoff. Near 80% busy, a shorter turn cuts the wait by much more than it cuts the turn. The service's metrics of the same runs, printed by `bash runs/lab3.sh S` into `runs/lab3-metrics.log`, medians over five runs:

| Per run, median of 5 | Baseline | CPU fix |
|---|---|---|
| lock hold, mean | 8.62 ms | 8.67 ms |
| handoff, mean | 4.52 ms | 3.04 ms |
| lock busy, M/G/1 | 80.9% | 70.1% |
| wait, predicted by M/G/1 | 41.3 ms | 21.6 ms |
| wait, measured | 35.6 ms | 21.1 ms |

The hold did not change. The handoff fell by 1.48 ms. The model predicted the wait to fall from 41.3 to 21.6 ms, and it fell from 35.6 to 21.1 ms, by 35 to 63% per run. So the CPU fix's effect on the wait is a computed result, not a mystery.

So the CPU fix treated a symptom. It made each turn shorter and left the queue in place: one server, 70% busy. The pool removed the queue.

**The sentence to remember:** a root cause is the thing whose removal removes the symptom. Write each hypothesis with its prediction and the one view that can see it, and fix one thing at a time.

**The trap:** a fix that works on the view that suggested it. The CPU fix cut CPU per request by 30%. The CPU profile would call it a success. The latency interval, which does not use the pairing of rounds, could not tell it from no change.

**Try this now:** run `uv run python phase03_profiling/diagnose.py --config format=page --rate 60 --duration 20 --no-profiles`. Before it prints, predict the handoff and the mean wait with the M/G/1 model. The run in `runs/lab3-extras.log` gave a handoff of 3.19 ms, a lock 65% busy, a predicted wait of 15.4 ms and a measured one of 15.1 ms.

---

## 3.7 — Proving a fix (the before-and-after a reviewer can check)

Why this matters: a fix you cannot prove gets reverted, and a fix you proved wrongly stays in and does nothing. Section 1.4 of Phase 1 built the statistics. This section adds two things a performance fix needs. It uses the same measurement that found the problem, and it checks that the latency was not paid for with errors or memory.

**Answer this first.** You have the pool fix of section 3.6. You run the old code once and the new code once, 20 s each, at 60 requests per second. The p99 falls from 244 ms to 168 ms. Is the fix proven? Now suppose the "new code" run was in fact the old code again, by mistake. Would the result look any different?

**The same code, compared with itself, one run each.** Two pairs of runs of the unchanged baseline, from the no-change runs of this section. The first pair is `p3-lock-before-3` against `p3-lock-control-8`, p99 244 against 168 ms. The second is `p3-lock-before-4` against `p3-lock-control-7`, p99 116 against 187 ms. From `runs/lab3-extras.log`, with the per-run lines left out:

```
p99 change: -31.3% (95% interval -39.0% to -28.4%, resampling runs, then requests)
real: the whole interval is an improvement
p99 change: +61.6% (95% interval +40.0% to +72.0%, resampling runs, then requests)
real: the whole interval is a regression
```

The same code was 31% faster than itself in one pair, and 62% slower in the other. Both verdicts say "real". With one run per side, the run level of the interval has nothing to pick from, so the interval covers only the requests of one run. It says how well one run measured itself. It says nothing about the next run. Section 3.4 showed why the spread is so wide here. The lock is about 80% busy, and near that load a queue's tail moves a lot from run to run.

**What a proof needs.** Each item is there because of a way a proof goes wrong:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ What a proof of a performance fix needs                                  │
├──────────────────────────────────────────────────────────────────────────┤
│ 1  the same measurement that found the problem: open-loop, from the      │
│    due time, at the same fixed rate. A closed loop or a lower rate       │
│    measures a different system                                           │
│ 2  several runs of each version, alternated, sharing seeds per round,    │
│    so drift of the laptop lands on both                                  │
│ 3  a no-change control, run the same way but with new seeds: the         │
│    method must not find a change where there is none                     │
│ 4  the interval from resampling runs, then requests, section 1.4.        │
│    Real only if it lies on one side of zero                              │
│ 5  the validity rule, fixed first: generator lag p99 above 10 ms         │
│    makes a run invalid                                                   │
│ 6  regression checks with limits fixed first: errors, peak memory,       │
│    allocations per request                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

`pyperf compare_to` fails several of these. Its `is_significant` runs a Student's t-test, which compares means and assumes normal values. The Google SRE book warns against both for latency. pyperf suits micro-benchmarks, not a tail at a fixed load.

**The proof of the pool fix.** `prove.py` runs five rounds. Each round runs the baseline, the fix and a no-change control, each on a fresh service process. The baseline and the fix of round k share seed k: the same arrivals and the same backend times. From `runs/lab3-prove.log`:

```bash
uv run python phase03_profiling/prove.py --label lock --before conns=1 --after conns=4 \
    --rounds 5 --control --rate 60 --duration 20
```

```
fix against baseline: p99 per valid run, baseline [122.0, 161.6, 244.3, 116.0, 172.3] ms, other [50.2, 47.9, 51.0, 51.9, 50.8] ms
fix against baseline: p99 change -72.0% (95% interval -78.8% to -62.5%, resampling runs, then requests). real: the whole interval is an improvement
control against baseline: p99 per valid run, baseline [122.0, 161.6, 244.3, 116.0, 172.3] ms, other [165.2, 187.4, 167.9, 164.9, 189.0] ms
control against baseline: p99 change -3.3% (95% interval -27.6% to +30.8%, resampling runs, then requests). not shown: the interval includes no change
regression checks, limits fixed before the runs:
  [ok] errors: most errors in one run: baseline 0, fix 0
  [ok] memory: median peak RSS: baseline 85.9 MB, fix 86.8 MB, limit 1.10x
  [ok] allocations: per request: baseline 115,527, fix 115,523, limit 1.05x
  also: median collector time per run 324 ms -> 287 ms; median CPU per request 4.93 ms -> 4.66 ms
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ p99 per group, 5 runs each, 60 requests per second. runs/lab3-prove.log  │
├──────────────────────────────────────────────────────────────────────────┤
│ baseline ███████████████████████████ 161.6, from 116 to 244.3            │
│ fix      ████████ 50.8, from 47.9 to 51.9                                │
│ control  ████████████████████████████ 167.9, from 164.9 to 189           │
├──────────────────────────────────────────────────────────────────────────┤
│ median p99, then the range. One bar character = 6 ms of the median.      │
│ Every run was valid:                                                     │
│ generator lag p99 2.20 to 2.28 ms                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

Read it in order:

1. **Validity and the fix.** Every run was valid. The fix's whole interval, −78.8% to −62.5%, is an improvement.
2. **The control.** The control runs use seeds 6 to 10, not the baseline's seeds, so they measure the spread between runs with different arrivals. Its interval, −27.6% to +30.8%, includes no change, as it must. It is wide because the unchanged code's runs spread from 116.0 to 244.3 ms.
3. **Regressions.** No run had an error. Peak RSS, the most memory the process held at once, had a median of 85.9 MB before and 86.8 MB after. The allocation check counts the handler's CPU part offline with memray: 115,527 against 115,523. The pool fix does not touch that code, so this check could not move here.
4. **What did not change.** Medians over five runs: CPU per request went from 4.93 to 4.66 ms, and the collector's time per run from 324 to 287 ms. The fix removed waiting, and not work. That matches the hypothesis it came from.
5. **The prediction, and where it missed.** Section 3.6 predicted a p99 near 42 ms. The five runs measured 47.9 to 51.9 ms: 6 to 10 ms more. This is step 7 of the hypothesis loop. The model left out what the pool keeps: each request's 4.7 ms of CPU still queues on one event loop, and the collector still pauses it. Inferred, not measured.

Point 4 checks the mechanism. A fix predicted to remove a wait should move the wait histogram and the latency, and leave CPU alone. If the CPU had dropped too, the proof would be about two changes at once.

**Where the proof stops.** It proves the fix at 60 requests per second, on this laptop, with this backend time. Its allocation check covers the handler's `summarise` only, so it cannot see allocations a fix adds elsewhere, such as in a pool. It does not prove it at twice the rate, where the pool of four may reach its own knee. Phase 2, section 2.5, "The capacity envelope of a service", decides that, resource by resource. A quieter laptop gives a narrower control, and a stronger proof.

**The sentence to remember:** prove a fix with the measurement that found it. Several alternated runs at the same fixed rate, a no-change control, the interval from runs then requests, and errors and memory checked against limits written first.

**The trap:** one run before and one run after. On this service the unchanged code measured 31% faster and 62% slower than itself, each called "real".

**Try this now:** run `uv run python phase03_profiling/prove.py --self-test --skip-check errors`. It removes the error check, and the self-test must fail with `the errors regression was not caught`. A regression check nobody runs is a regression nobody finds.

---
## 🧪 Hands-on lab — part B

**Run status:** every command below was executed on the author's machine on 2026-09-25, in the conditions of part A. Other load tests ran on the laptop at the same time. Each "Expected" line is copied from the logs in `runs/`. Your numbers will differ. The verdicts, the directions and the counts should not.

All commands run from `elite-performance/code/`. The load runs start their own services on free ports. Close other programs first: a run whose generator lag p99 is above 10 ms is invalid.

- [ ] **E6 (offline).** A second thread and the event loop.
  - Run: `bash runs/lab3.sh L`, or once: `uv run python phase03_profiling/gil.py --time-select`.
  - Expected: loop lag p50 `0.31` to `0.32 ms` with no thread, `14.05` to `14.06 ms` beside a Python thread, `114.94` to `117.38 ms` beside `c-hold`. With a second thread, `in select 100%`. With none, `in select  97%`.
  - Then break it: `uv run python phase03_profiling/gil.py --self-test --hold-call sha256`. The "holding" C call now releases the GIL. Expected: an `AssertionError` with a loop lag p50 under 1 ms.
  - Teaches: a GIL wait makes the loop late while its thread looks idle. Measure the lag, not the thread's CPU.

- [ ] **E7 (offline).** Draw the timeline of six requests and one blocking call.
  - Run: `uv run python phase03_profiling/timeline.py`.
  - Expected: long rows of dots beside request 1's `B`, `waiting for the lock 77%`, the handoffs `3.5 3.7 4.3 4.4 166.2 ms`, and a debug-mode line ending `took 0.166 seconds`.
  - Then `--block-request -1`. Expected: no `B`, `asyncio debug mode logged 0 slow callback(s)`, and the longest row of dots 13 characters, 52 ms.
  - Teaches: read a wait by what else ran at the same moment.

- [ ] **E8 (break-it, offline).** One current span for the whole loop.
  - Run: `uv run python phase03_profiling/timeline.py --self-test --no-contextvar`.
  - Expected: `AssertionError: (Span(id=4, parent=3, name='request', ...` followed by the `backend` span of request 0 as its parent.
  - Teaches: the current span must be per task. asyncio copies the context into each task.

- [ ] **E9 (local).** The hypothesis table and the profiles, on the slow service.
  - Run: `bash runs/lab3.sh D`. About 2 minutes.
  - Expected: H2 the largest share, at 63%, 70% and 79%, and `predicted mean wait 23.2 ms, measured 21.6 ms` in the first run. pyinstrument's async tree: `0.130 Lock.acquire` in a request of `0.155`. The cProfile window: `171 requests finished`. The yappi window: `52`.
  - Then `bash runs/lab3.sh H`. Expected: `0.03 ms handoff`, and mean waits of 8.5, 8.7 and 12.3 ms against 7.5, 10.4 and 10.6 predicted.
  - Teaches: one measurement per hypothesis, and profilers only on a run whose latency you do not use.

- [ ] **E10 (local).** Prove the pool fix. This is the phase's demonstration.
  - Run: `bash runs/lab3.sh X`. About 6 minutes.
  - Expected: `p99 change -72.0% (95% interval -78.8% to -62.5%, ...)`, `real: the whole interval is an improvement`. Control: `p99 change -3.3% (95% interval -27.6% to +30.8%, ...)`, `not shown`. Then three `[ok]` lines for errors, memory and allocations.
  - Teaches: a fix is proven at fixed throughput, with a control and regression checks.

- [ ] **E11 (local).** The fix a CPU profile suggests, and the fix for the collector.
  - Run: `bash runs/lab3.sh C M`. About 8 minutes.
  - Expected for C: `p99 change -41.5% (95% interval -57.7% to +4.5%, ...)`, `not shown`, and `median CPU per request 4.88 ms -> 3.41 ms`. For M: `p99 change -10.3% (95% interval -20.6% to -1.5%, ...)`, `real`, and `median collector time per run 295 ms -> 0 ms`. The M verdict is narrow: see section 3.3.
  - Then `bash runs/lab3.sh S`. Compare the handoff of `cpu-before` and `cpu-after`: `4.33` to `4.89 ms` against `2.70` to `3.32 ms`.
  - Teaches: a fix that works on the view that suggested it may not show in the latency. A model of the queue says how much it should.

- [ ] **E12 (break-it, offline).** Prove a fix with one run per side.
  - Run: `uv run python phase01_measure/compare_runs.py --before runs/p3-lock-before-4.json --after runs/p3-lock-control-7.json`. It needs the runs from E10.
  - Expected: `p99 change: +61.6% (95% interval +40.0% to +72.0%, ...)` and `real: the whole interval is a regression`. Both files are the same unchanged code.
  - Then remove a regression check: `uv run python phase03_profiling/prove.py --self-test --skip-check errors`. Expected: `AssertionError: the errors regression was not caught`.
  - Teaches: several alternated runs and a control are what make "real" mean something.

---

## 🔍 Check it yourself

1. Open `phase03_profiling/timeline.py:100`. This is `Tracer.span`. It restores the previous span with `self.current.reset(token)`. Suppose it did `self.current.set(parent)` instead. With a `ContextVar`, would the self-test still pass? What does the token give you that `set(parent)` does not, when a span is closed in a different context from where it opened?

2. Open `phase03_profiling/prove.py:70`. This is `MEMORY_LIMIT`, with `ALLOC_LIMIT` below it. Both are constants written before any run. What would you be doing if you raised one of them after a fix failed its check? Compare with `LAG_LIMIT_MS` in Phase 1.

---

## ✅ Checkpoint 3B — answer in your own words

1. **Walk through what happens** when one request of an asyncio service blocks the loop for 200 ms. Eight other requests are awaiting a lock or the backend. (a) Which spans grow, and what do their names say? (b) What does asyncio debug mode log, and what would it log for a 60 ms call? (c) What does the event-loop lag monitor record?

2. **A colleague says:** "I ran the load test before and after my change. The p99 fell from 244 ms to 168 ms. That is 31% better, and compare_runs called it real. Ship it." Argue against, with the numbers from section 3.7. What do you ask them to run instead?

3. **Show the arithmetic.** The lock of section 3.4 is held about 8.5 ms per request, and each handoff adds about 4.5 ms. (a) What share of the time is the lock busy at 60, and at 120 requests per second? (b) The CPU fix of section 3.6 cut the handoff to about 3.0 ms. At what rate does the one lock reach 100% busy, before and after that fix? (c) With the pool of 4 and the same hold, what is each connection's share at 120 per second?

4. **Given these constraints, design** the proof for `gc.freeze()` on the pool service of the lab. You have 10 minutes of load time, a busy laptop, and a reviewer who will ask what else changed. Give the rate, the number of rounds, the control, the checks with their limits, and the result for each probe that you predict before the runs.

5. **This is broken.** An asyncio service has a p99 of 60 ms. After a teammate adds a thread that refreshes a cache in pure Python every second, the p99 is 110 ms. CPU per request did not change. The event loop thread's profile shows 97% of its time in `kqueue.control`. What is the cause, how do you confirm it, and name two fixes with what each costs.

<details>
<summary>Answer sketches</summary>

1. (a) Every span open during the 200 ms grows by it, and the names point at the lock and the backend. Only the timeline column shows the blocking call. (b) Debug mode logs the step, with its time: 200 ms is above `slow_callback_duration`, 0.1 s. A 60 ms call is not logged. In the lab a 150 ms block was logged as 0.166 s, because the step included the summarise after it. (c) One tick about 200 ms late: the lag max.

2. Against. In the lab, the unchanged baseline measured 31% faster than itself in one pair of runs, and 62% slower in another. compare_runs called both "real", because with one run per side the interval covers only the requests of one run. Ask for five alternated rounds at the same fixed rate, a no-change control, and the interval from runs, then requests. In the lab that gave −72.0% for the pool, from −78.8% to −62.5%, with a control from −27.6% to +30.8%.

3. (a) One turn is 8.5 + 4.5 = 13 ms. 60 × 13 ms = 78% busy. 120 × 13 ms = 156%: the queue grows for as long as that rate lasts. (b) Before: 1 / 13 ms = 77 requests per second. After: 1 / (8.5 + 3.0) ms = 1 / 11.5 ms = 87 per second. The CPU fix moves the limit by about 13%. It does not remove it. (c) 120 × 8.5 ms / 4 = 25.5% per connection, if the requests spread evenly. A handoff adds to a turn only when a request waits, and at 25.5% few do.

4. For example: 60 per second, 5 rounds of baseline, freeze and control, 20 s each: about 5.5 minutes, as the lab's proof of the pool took. Checks: generator lag p99 at most 10 ms, errors no more than baseline, peak memory within 10%, allocations within 5%. Predictions, written first: about one young collection per request, unchanged. Full-collection pauses from tens of ms to under 1 ms, as `gcpause.py` measured 0.2 to 0.4 ms. The p99 about unchanged, since full collections sit above it. If the young count changes, something else changed.

5. The GIL. The thread keeps the GIL for up to one switch interval each time the loop gives it away in `select`. Confirm with the loop lag: in `gil.py` a Python thread took the median from 0.31 to 0.32 ms to 14.05 to 14.06 ms. The time sits in `kqueue.control` because the GIL is taken back inside it, so the 97% says nothing: an idle loop reads the same. On 3.13 a cProfile profile also mixes all threads. Fixes: move the refresh to a process, which costs memory and a way to share the result. Or shorten the switch interval, which took the lag to 3.31 to 3.32 ms and costs more switches.

</details>

---

## References & Further Learning — part B

Every URL below was fetched on 2026-09-25 and returned HTTP 200.

**The lock as a queue, and the GIL**

- **CPython `Lib/asyncio/locks.py` at tag v3.13.3** — https://raw.githubusercontent.com/python/cpython/v3.13.3/Lib/asyncio/locks.py
  Focus on: the fast path of `acquire` at line 98, and `fut.set_result(True)` at line 155, which only schedules the waiter. Together they make the handoff of section 3.4.
- **Pollaczek-Khinchine formula, Wikipedia** — https://en.wikipedia.org/wiki/Pollaczek%E2%80%93Khinchine_formula
  Focus on: the mean waiting time of an M/G/1 queue. A secondary source, used because the result is standard and the page states it plainly.
- **CPython `Python/ceval_gil.c` at tag v3.13.0** — https://raw.githubusercontent.com/python/cpython/v3.13.0/Python/ceval_gil.c
  Focus on: the notes at the top, and `DEFAULT_INTERVAL` on line 153. The `sys` docs, https://docs.python.org/3.13/library/sys.html, add under `setswitchinterval` that the real value can be higher.
- **David Beazley, "Convoy effect with I/O bound threads and New GIL", CPython issue 52194, 2010** — https://github.com/python/cpython/issues/52194
  Focus on: the first message: a factor of 12 on a dual-core MacBook, because an I/O call always releases the GIL. Closed as "wont fix".
- **Deepanshu Kartikey, "Hidden Latency in Python: Where APM Stops Looking", ClickPost, 2026** — https://www.clickpost.ai/blog/hidden-latency-in-python
  Focus on: both stories. A handler of 140 to 240 ms behind a gunicorn queue of up to 11 seconds, invisible to spans. And a request of 3,305 ms whose child spans added up to about 25 ms, because a sibling thread held the GIL during a full collection. A production write-up. It does not state the Python version.

**Timelines, root causes and proof**

- **Developing with asyncio, Python 3.13 documentation** — https://docs.python.org/3.13/library/asyncio-dev.html
  Focus on: "Debug Mode" and the 100 ms rule. Ignore its sentence about slow I/O selector calls: that log was removed after v3.7.0. The value is in `base_events.py` line 437 at v3.13.3, https://raw.githubusercontent.com/python/cpython/v3.13.3/Lib/asyncio/base_events.py.
- **Coroutines and Tasks, Python 3.13 documentation** — https://docs.python.org/3.13/library/asyncio-task.html
  Focus on: `create_task`'s `context` argument. A task copies the current context, which is why a `ContextVar` is per task. OpenTelemetry does the same in its 45-line `contextvars_context.py`, https://raw.githubusercontent.com/open-telemetry/opentelemetry-python/v1.44.0/opentelemetry-api/src/opentelemetry/context/contextvars_context.py.
- **What's New in Python 3.14** — https://docs.python.org/3.14/whatsnew/3.14.html
  Focus on: `python -m asyncio ps` and `pstree`. They need attach rights on macOS: https://docs.python.org/3.14/howto/remote_debugging.html.
- **"Profiling the Airflow Scheduler With Flame Graphs", Astronomer, 2019** — https://www.astronomer.io/blog/profiling-the-airflow-scheduler/
  Focus on: 2.70 times in test mode, "x1.01" with real tasks, then 9.55 times from `os.fork()`. The author's name is not checked.
- **pyperf 2.10.0, `pyperf/_utils.py`** — https://raw.githubusercontent.com/psf/pyperf/2.10.0/pyperf/_utils.py
  Focus on: `is_significant`, a Student's t-test on means.
- **Google SRE book, chapter 4, "Service Level Objectives"** — https://sre.google/sre-book/service-level-objectives/
  Focus on: the section on aggregation. Most metrics are distributions, not averages.

---

## Cheatsheet — part B

```
LOCKS AND THE GIL
  lock            time wait, hold AND handoff. One turn = hold + handoff
  handoff         release → next acquire: the releaser's code until its next await
  M/G/1           W = λ E[S²] / (2 (1 − ρ)), ρ = λ E[S]
  /report         73-81% busy. Wait predicted 23.2-41.0, measured 21.6-51.9 ms
  yield release   handoff 0.03 ms, 50-57% busy, wait 8.5-12.3 ms
  GIL             switch interval 5 ms. Python thread: loop lag 14.05-14.06 ms
                  C call holding the GIL: lag = the whole call
  loop lag        a task sleeping a fixed tick. Sees CPU, GC, GIL alike
  select, timed   GIL wait and idle both read 97-100%. cProfile: all threads

TIMELINE, CPython 3.13, no root
  spans           ContextVar per task, reset(token). Plain attribute = wrong parent
  debug mode      PYTHONASYNCIODEBUG=1. Logs callbacks > 0.1 s. Not awaits

HYPOTHESES AND PROOF
  write           each hypothesis + its prediction + the ONE view that sees it
  /report         H1 CPU 8-15%, H2 lock 63-79%, H3 GC 1%, H4 lag p99 < 10 ms
  proof           open-loop, same fixed rate, 5 rounds alternated, + control
  verdict         interval: resample runs, then requests. One side of zero
  regressions     errors ≤ baseline, peak RSS ≤ 1.10x, allocations ≤ 1.05x
  one run each    unchanged code: −31.3% and +61.6%, both called "real"
  pool of 4       p99 −72.0% (−78.8% to −62.5%). Control −3.3% (−27.6% to +30.8%)
  CPU fix         wait 35.6 → 21.1 ms (model 41.3 → 21.6). p99: not shown
```

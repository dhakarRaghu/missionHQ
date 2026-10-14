# Phase 4B — Concurrency correctness: lifetimes and tests

**The question this phase answers:** how does a program that passes every test still corrupt state, or leak a task per request, in production?

Part A showed how shared state breaks: where a thread can be switched out, where a task can be interleaved, and who owns what. Part A is a prerequisite. This part uses its wallet, its suspension points and its ownership table without explaining them again.

This part is about time. A task starts, and something must end it. A client leaves, and something must stop its work. A test passes, and something must prove it ran the order that breaks. This part teaches the last two ideas of Phase 4, and the task half of the third:

3. **Every piece of shared state and every task needs a written owner.**
   A task whose owner does not bound it and wait for it leaks, once per request.
4. **A client disconnect stops nothing by itself.** uvicorn does not cancel the handler. A cancel stops work only at a suspension point, and only if nothing swallows `CancelledError`. At that point, shared state can be half done.
5. **A concurrency test is deterministic only when the test controls the interleaving.** asyncio runs tasks in the same order on every run. So running a test more is not a search.

As in part A, a suspension point is a place where a task stops and the loop runs another task. An interleaving is the order in which the steps of concurrent tasks run.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, the previous document: shared state                              │
│  4.1  What the GIL guarantees                                            │
│  4.2  Data races versus logical races                                    │
│  4.3  Ownership                                                          │
│  4.4  Locks, queues and asyncio primitives                               │
│                                                                          │
│ PART B, this document: lifetimes and tests                               │
│  4.5  Cancellation and deadlines   — where a cancel stops, and where not │
│  4.6  Bounded concurrency          — bound the tasks, not only the calls │
│  4.7  Task and thread leaks        — counted across 10,000 requests      │
│  4.8  Deterministic tests          — the test chooses the order          │
│  Lab: E7 to E12                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**What this part assumes.** Part A, and two sections of earlier phases. The three-sentence version of each is enough.

- **Phase 2, section 2.3, "Pools that fill (the wait rises long before the errors come)".** A pool is a queue with a fixed number of servers. When it is full, callers wait. httpx's pool timeout restarts on each wait. So while connections keep freeing, a full pool shows as waiting, not as errors. Section 4.6 puts 10,000 tasks in front of one.
- **Phase 3, section 3.5, "The timeline: tracing the event loop".** It shows what each task did over time. Section 4.7 adds a simpler tool: how many tasks are alive, and where each one waits.

This part also leaves two things for later. Deadlines that cross a network to another process are Phase 5, section 5.7. Delivery guarantees and idempotency across processes belong to a later course.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. The machine and versions are those of part A. It is an Apple M2 with 8 GB, macOS 15.7.8 and CPython 3.13.3, measured on 2026-09-25. The laptop ran on battery, at 87% to 91% and discharging. Other programs were running. The one-minute load average in this part's logs was 4.3 to 7.1. Lab part D starts real uvicorn servers on free ports and sends 30,000 requests. It takes about 45 seconds.

Time for part B: about 1.5 hours. About 2 minutes of that is waiting for runs.

---
## 4.5 — Cancellation and deadlines (where a cancel stops, and where it does not)

Why this matters: a client that gives up does not stop your server. A deadline stops the work below it only if every layer lets it through. Otherwise you pay for work nobody reads.

**Answer this first.** A Starlette handler on uvicorn 0.53.0 does 10 steps of 100 ms each. The client gives up after 0.3 s and closes the connection. How many steps run? Now the handler catches exceptions with a bare `except:` around one step, and a deadline of 0.1 s wraps 1 s of work. When does the caller get control back?

**A disconnect does not cancel the handler.** uvicorn runs each request's app in its own task. When the client's connection closes, `connection_lost` in `uvicorn/protocols/http/h11_impl.py:107` marks the request as disconnected at line 115 and wakes any `receive()` that waits. It never calls `cancel()` on the app task. A `send()` after that returns without an error, at line 459. So the handler keeps running, and its reply is dropped. This is from the source at the 0.53.0 tag. `disconnect_api.py --timeline` shows it on a live server:

```
each client gives up after 0.3 s and closes its connection
  /plain   steps done at [0.1, 0.203, 0.304, 0.406, 0.507, 0.607, 0.709, 0.81, 0.911, 1.011]
           8 step(s) after the client left; ended at 1.011 s: finished all steps
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ A client leaves at 0.3 s. The handler runs to 1.0 s. Lab part D          │
├──────────────────────────────────────────────────────────────────────────┤
│ time     0.0   0.1   0.2   0.3   0.4   0.5   0.6   0.7   0.8   0.9   1.0 │
│ client   ████████████████████ gone                                       │
│ /plain   ██████ step ██████ step ██████ step ... all 10 steps, to 1.011 s│
│ /owned   ████████████████████ stopped at 0.27 s by the TaskGroup         │
├──────────────────────────────────────────────────────────────────────────┤
│ /plain did 8 of its 10 steps for nobody. uvicorn 0.53.0 marks the        │
│ request disconnected and never cancels it. The app has to notice.        │
└──────────────────────────────────────────────────────────────────────────┘
```

**Where a cancel lands.** `task.cancel()` does not stop a task at once. It asks the loop to throw `CancelledError` into the coroutine at the await where it is suspended, or at its next one. The documentation adds that `Task.cancel()` "does not guarantee that the Task will be cancelled". Two things can stop it:

1. **A blocking call.** Until it returns, the loop cannot run, so it cannot deliver the cancel. With one `time.sleep(0.3)` inside, a 0.1 s deadline gave control back at 0.30 s.
2. **Code that catches the cancel and carries on.** `CancelledError` is a `BaseException` since Python 3.8. What's New in 3.8 says it "now inherits from BaseException rather than Exception". So `except Exception:` lets it through. A bare `except:` or `except BaseException:` catches it.

**WRONG: a bare except around an await.** This is `cancel.py:69`:

```python
async def handler_bare(log: list[str]) -> str:
    try:
        await asyncio.sleep(10)
    except:                                    # WRONG: a bare except catches CancelledError too
        log.append("bare except caught CancelledError")
    await asyncio.sleep(0.01)
    log.append("work after the cancel ran")    # runs for a caller that asked it to stop
    return "finished anyway"
```

```
except Exception:              result 'CancelledError'   cancelled() True   log: []
bare except:                   result 'finished anyway'  cancelled() False  log: ['bare except caught CancelledError', 'work after the cancel ran']
except CancelledError: raise   result 'CancelledError'   cancelled() True   log: ['cleanup ran']
```

The task was cancelled 10 ms after it started. With the bare except, it finished normally and reported that it was never cancelled.

**RIGHT: clean up, then re-raise.** `handler_reraise` at `cancel.py:79` catches `asyncio.CancelledError`, runs its cleanup and ends with a bare `raise`. Its line above shows `cancelled() True` and `log: ['cleanup ran']`.

**A deadline is a cancel with a timer.** `asyncio.timeout(0.1)` cancels the current task when time runs out. At the block's edge it turns the `CancelledError` into `TimeoutError`. The cancel travels down the chain of awaits. `cancel.py --part deadline` puts a 0.1 s deadline around 1 s of work in 50 ms steps, written seven ways, three runs each:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 0.1 s deadline around 1 s of work. When the caller got control back,     │
│ and when the work's last step finished. 3 runs each. Lab part C          │
├──────────────────────────────────────────────────────────────────────────┤
│                         caller back   TimeoutError   last step done      │
│ awaits all the way      0.10 s        yes            0.05 s              │
│ TaskGroup helper        0.10 s        yes            0.05 s              │
│ swallowed cancel        1.02-1.03 s   NO             1.02-1.03 s         │
│ one 0.3 s blocking call 0.30 s        yes            0.30 s              │
│ create_task helper      0.10 s        yes            1.01-1.02 s         │
│ asyncio.shield          0.10 s        yes            1.02-1.03 s         │
│ asyncio.to_thread       0.10 s        yes            1.07 s              │
├──────────────────────────────────────────────────────────────────────────┤
│ The last three look right to the caller and are not. The work runs       │
│ on for 0.9 s or more after the deadline, for a caller that has gone.     │
└──────────────────────────────────────────────────────────────────────────┘
```

Each row is a rule:

- **Awaits all the way down, or a TaskGroup,** stop at the deadline. The step in progress is cut.
- **A swallowed cancel** defeats the deadline. The documentation warns that `TaskGroup` and `timeout()` "might misbehave if a coroutine swallows asyncio.CancelledError".
- **A `create_task` helper** has no owner inside the block, so the cancel never reaches it. `asyncio.shield` does the same on purpose. Give a shielded task an owner too.
- **A thread** cannot be cancelled from outside. Section 4.7 counts the cost and shows the fix, a stop flag.

**A cancel can leave shared state half done.** A cancel lands at a suspension point. A suspension point can sit in the middle of a protocol. `cancel.py --part shared` has one connection that answers requests in order, like Redis or HTTP/1.1 on one socket. Alice sends her request and is cancelled before she reads the reply. Bob then uses the same connection:

```
reuse the connection  : alice cancelled after sending; bob asked for bob:card and got 'value-of-alice:card' (1 connection(s) opened)
discard the connection: alice cancelled after sending; bob asked for bob:card and got 'value-of-bob:card' (2 connection(s) opened)
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One connection, replies in order, a cancel between send and read         │
├──────────────────────────────────────────────────────────────────────────┤
│ alice   send GET alice:card ─────► connection                            │
│ alice   await reply             ◄ cancelled here: the reply is still due │
│ pool    connection goes back to the pool, with alice's reply on the way  │
│ bob     send GET bob:card  ──────► same connection                       │
│ bob     await reply        ◄───── value-of-alice:card   WRONG USER       │
├──────────────────────────────────────────────────────────────────────────┤
│ fix: a call that did not finish closes its connection. Bob opens a       │
│ new one and reads his own reply. Here: 2 connections instead of 1.       │
└──────────────────────────────────────────────────────────────────────────┘
```

This is the mechanism of a real incident. OpenAI's write-up of its 20 March 2023 ChatGPT outage describes it in the asyncio redis-py client. A spike in cancelled Redis requests left replies on pooled connections, for the next request to read. Some users could see titles from another active user's chat history. Payment-related information of 1.2% of ChatGPT Plus subscribers, active in a nine-hour window, may have been visible too. The upstream bug is redis-py issue #2624.

**How a handler notices the client left.** There are three ways, and the live server runs each one:

```
  /polled  steps done at [0.102, 0.232, 0.333]
           1 step(s) after the client left; ended at 0.333 s: saw the disconnect, returned early
  /owned   steps done at [0.1, 0.203]
           0 step(s) after the client left; ended at 0.27 s: TaskGroup cancelled the work and the publisher
  /stream  steps done at [0.103, 0.205]
           0 step(s) after the client left; ended at 0.283 s: generator cancelled by Starlette
```

1. **Poll `await request.is_disconnected()` between steps.** It stops at the next step boundary. The trap: in Starlette 1.7.0 it reads the next message and drops it, at `starlette/requests.py:328`. Before the body is read, that message is the body. `/trap` polls first and waits until its own timeout: `body='<timed out waiting for body>'`. `/trap-fixed` reads first: `body='hello-body'`.
2. **Return a `StreamingResponse`.** Starlette 1.7.0 listens for the disconnect beside the generator and cancels it, at `starlette/responses.py:279`. The server's clock starts when the handler starts, a few milliseconds after the client's clock. So the client's 0.3 s shows as 0.27 to 0.283 s on the server.
3. **Watch for the disconnect inside a TaskGroup.** A watcher waits for `http.disconnect` and raises, and the group cancels the rest. This is `/owned`, in section 4.7.

**My own code had this bug.** The first `Wallet.__aexit__` awaited its cancelled owner task inside `except asyncio.CancelledError: pass`, so a cancel of the caller arriving there was swallowed too. flake8-async 26.8.1 reported it as ASYNC103. Ruff 0.16.9 has no such rule. The fix: `if asyncio.current_task().cancelling(): raise`.

**The sentence to remember:** a cancel stops work only at a suspension point, and only when nothing swallows it. A disconnect on uvicorn is not a cancel at all until your code makes it one.

**The trap:** a retry loop or a bare `except:` that treats `CancelledError` as one more error. It turns every deadline above it into a no-op. The 0.1 s deadline took 1.02 to 1.03 s and raised no `TimeoutError`.

**Try this now:** run `uv run python phase04_concurrency/cancel.py --part shared`. Predict what bob receives in each line first. The run gives `value-of-alice:card` when the connection is reused and `value-of-bob:card` when it is discarded.

---
## 4.6 — Bounded concurrency (bound the tasks, not only the calls)

Why this matters: `asyncio.gather` over every item is a common fan-out in Python services. It creates one task per item at once. If each call also carries a deadline, most of those calls miss it while they wait for a connection. And a semaphore, the usual fix, still creates one task per item.

**Answer this first.** A job makes 10,000 calls through a pool of 100 connections. Each call holds a connection for 20 ms. Each call has a 1 s deadline, an `asyncio.timeout(1)` around it, as section 4.5 recommends. With one `asyncio.gather` over all 10,000, how many calls miss the deadline? With an `asyncio.Semaphore(100)` around each call, how many miss it, and how many tasks exist at the peak?

**Which timeout this is.** `bounded.py` models a per-call deadline that covers the wait for a connection. It is not httpx's pool timeout, which httpcore 1.0.9 starts again on each wait. Phase 2, section 2.3, measured it: 400 requests through 5 connections held 100 ms each, with a 5 s pool timeout, all succeeded. The longest took 9.23 s, and there were 0 pool timeouts. So with httpx alone, the gather below does not fail. Its calls wait, and the 10,000 tasks still exist. The task count is the lesson that holds for both kinds of timeout.

**The arithmetic.** The pool serves 100 calls per 20 ms, which is 5,000 calls per second. So all 10,000 take 2 s at best. `gather` starts every call at once, so every deadline starts at t = 0. By 1 s only 5,000 calls can have started. The other 5,000 miss their deadline, although the dependency answered every call in 20 ms.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 10,000 calls wait from t = 0. Pool of 100, 20 ms a call. Arithmetic      │
├──────────────────────────────────────────────────────────────────────────┤
│ t = 0.0 s   10,000 calls wait for a connection. Their deadlines start    │
│ t = 0.5 s   2,500 served. 7,500 still wait                               │
│ t = 1.0 s   5,000 served, by the arithmetic. The rest miss the deadline  │
│ t = 2.0 s   the job would have finished with no errors, if each call's   │
│             deadline had started only when the call got a slot           │
├──────────────────────────────────────────────────────────────────────────┤
│ measured: 4,300 to 4,500 served before 1 s, 5,500 to 5,700 missed.       │
│ The loop's own work for 10,000 waiting tasks slowed each call a little.  │
└──────────────────────────────────────────────────────────────────────────┘
```

**Three ways to fan out.** `bounded.py` runs each three times:

```
10,000 calls, pool 100, hold 20 ms, per-call deadline 1 s, limit 100
arithmetic: the pool serves 100 / 20 ms = 5,000 calls/s, so all calls take 2.00 s and 5,000 can start before the deadline
  gather     1.11 s  errors  5,600  done  4,400  peak in flight  100  peak tasks 10,000
  semaphore  2.33 s  errors      0  done 10,000  peak in flight  100  peak tasks 10,000
  workers    2.24 s  errors      0  done 10,000  peak in flight  100  peak tasks    100
```

Other runs: `gather` missed 5,500 or 5,700, `semaphore` took 2.25 to 2.33 s, `workers` 2.19 to 2.24 s. A tracemalloc pass measured peak memory.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ What each fan-out bounds. 10,000 calls, limit 100. Lab part B            │
├──────────────────────────────────────────────────────────────────────────┤
│                  calls in flight   tasks alive   missed   memory         │
│ gather           100: the pool     10,000        5,600    20.5 MB        │
│ Semaphore(100)   100               10,000        0        16.4 MB        │
│ 100 workers      100               100           0         0.3 MB        │
├──────────────────────────────────────────────────────────────────────────┤
│ With the semaphore, a call and its deadline start only once it has a     │
│ slot. The wait moves into your code. The 10,000 tasks stay.              │
└──────────────────────────────────────────────────────────────────────────┘
```

The semaphore fixed the errors. It did not bound the tasks, because `gather` wraps each coroutine in a task before any of them reaches the semaphore. 10,000 tasks each hold a coroutine, its frame and its arguments. Here that was 16.4 MB / 10,000 = about 1.6 KB per task, so a million items would hold about 1.6 GB. Workers bound both. This is `bounded.py:140`, shortened: comments, error handling and the mutation switch are left out, so `n` is written as `limit`:

```python
        todo = iter(range(calls))

        async def worker() -> None:
            for _ in todo:
                await dep.call()
        async with asyncio.TaskGroup() as tg:     # owns the workers, waits for all of them
            for _ in range(limit):
                tg.create_task(worker())
```

The shared iterator is the ownership rule of part A applied. `next()` never suspends, so two workers never take the same item.

httpx 0.28.1 caps a client at 100 connections by default. That cap bounds calls in flight, not tasks. Bound the tasks yourself.

**The first version slowed the loop it measured.** It polled `asyncio.all_tasks()` every millisecond, which walks all 10,000 tasks each time. The script now counts in the loop's task factory.

**The sentence to remember:** bound the work where it is created. A worker pool bounds both the calls in flight and the tasks alive. A semaphore around each call bounds only the calls.

**The trap:** a semaphore around each call of a `gather`. It bounds the calls and hides the 10,000 tasks. With a per-call deadline, a plain `gather` is worse: the dependency answers every call in 20 ms, and 5,500 to 5,700 of 10,000 calls still miss their deadline.

**Try this now:** run `uv run python phase04_concurrency/bounded.py --calls 2000 --pool 50 --hold-ms 10 --deadline 0.2 --limit 50`. Predict the arithmetic first: 50 / 10 ms = 5,000 calls/s, so about 1,000 start before the 0.2 s deadline. The run gave 1,129 missed deadlines for `gather`, 0 for the others, and peak tasks of 2,000, 2,000 and 50.

---
## 4.7 — Task and thread leaks (counted across 10,000 requests)

Why this matters: a leak of one task per request shows no error. The service slows and grows for hours, then it is restarted, and the cause is never found. You find a leak by counting, before and after, and by grouping what is left by the line where it waits.

**Answer this first.** A handler starts a publisher task with `create_task`. It keeps the task in a set with a done callback, as the asyncio documentation recommends. The publisher reads progress events until it gets `None`. The handler polls `is_disconnected()` and returns early when the client leaves. After 10,000 client disconnects, how many extra tasks are alive?

**The measurement.** This is the phase's demonstration. `disconnect_api.py` starts the live server in its own process, once per route. It records the server's task count, sends 10,000 requests whose clients disconnect after 20 ms, waits until every handler has ended, and counts again:

```
/plain   10,000 clients reset after the request was sent, in 5.1 s
         server tasks 1 before, 1 after (+0); threads 1 -> 1
         handlers started 10,000, ran all 10 steps 10,000, stopped early 0
/polled  10,000 clients reset after the request was sent, in 5.2 s
         server tasks 1 before, 10,001 after (+10,000); threads 1 -> 1
         handlers started 10,000, ran all 10 steps 0, stopped early 10,000
         task dump top line: 10,000 x publisher at disconnect_api.py:112  waiting in Queue.get
/owned   10,000 clients reset after the request was sent, in 5.3 s
         server tasks 1 before, 1 after (+0); threads 1 -> 1
         handlers started 10,000, ran all 10 steps 0, stopped early 10,000
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Server tasks alive after 10,000 client disconnects. Lab part D           │
├──────────────────────────────────────────────────────────────────────────┤
│ /plain   ▏                        +0      all 10,000 ran every step      │
│ /polled  ████████████████████████ +10,000 stopped, publisher leaked      │
│ /owned   ▏                        +0      stopped, nothing leaked        │
├──────────────────────────────────────────────────────────────────────────┤
│ /plain does not leak. It wastes: 10,000 x 10 steps for nobody.           │
│ /polled fixed the waste and created the leak.                            │
│ /owned is the only route with neither.                                   │
└──────────────────────────────────────────────────────────────────────────┘
```

`/polled` is the dangerous one, because it looks like the fix. It stops the work, and a code review approves it. Its publisher is kept in a set with a done callback, as the documentation recommends. But the publisher waits for `None`, which the work sends only at the normal end. The early return at `disconnect_api.py:147` never sends it.

`/owned` puts the watcher, the publisher and the work in one `TaskGroup`. When the watcher raises, the group cancels the other two and waits for them. The handler cannot return while any of them runs. That is the ownership rule from section 4.3, and it is why the count went back to 1.

**Four patterns.** `leaks.py` runs each leak inside one process, 10,000 cancelled requests at a time, and the fix beside it:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Four ways a request leaks, each after N cancelled requests. Lab part L   │
├──────────────────────────────────────────────────────────────────────────┤
│ 1 blocked on get: a queue nobody feeds       +10,000 tasks               │
│   task dump: 10,000 x publisher at leaks.py:110  waiting in Queue.get    │
│   fix: a TaskGroup owns the reader                           +0          │
├──────────────────────────────────────────────────────────────────────────┤
│ 2 blocked on put: a full queue nobody drains +10,000 tasks               │
│   task dump: 10,000 x producer at leaks.py:137  waiting in Queue.put     │
│   fix: a TaskGroup owns the writer                           +0          │
├──────────────────────────────────────────────────────────────────────────┤
│ 3 never awaited  (a) kept in a set, never removed: 10,000 finished       │
│                      tasks held, 0 of 100 errors seen                    │
│                  (b) no reference: 10,000 "Task was destroyed but        │
│                      it is pending!", the work silently lost             │
│   fix: done callback that removes it and reads its error    0 held       │
├──────────────────────────────────────────────────────────────────────────┤
│ 4 a thread       (a) to_thread with a 10 ms timeout: 12 bodies ran       │
│                      to the end, 0.5 s each, for callers that left       │
│                  (b) a heartbeat thread per request: +200 threads        │
│   fix: a stop flag the thread checks, and join          +0 threads       │
└──────────────────────────────────────────────────────────────────────────┘
```

The asyncio documentation warns about pattern 3(b): "The event loop only keeps weak references to tasks." At `Lib/asyncio/tasks.py:1039`, asyncio's registry of tasks, `_scheduled_tasks`, is a `weakref.WeakSet()`. A task nothing else refers to can be collected while it waits. Pattern 3(a) is the documentation's own fix, half applied: the set without the done callback. That is the 2023 case from part A's opening, where CPU climbed to 100% in about 11 hours.

Pattern 4 needs two numbers. The default pool has min(32, 8 cores + 4) = 12 threads here. Of 200 calls queued at once, the 12 that had started ran their full 0.5 s. The other 188 were still queued, so asyncio cancelled them. A queued call can be cancelled, a running one cannot. The fixed run's `threads +12` are the pool's idle threads. And `asyncio.run` waits up to 300 s for that pool at exit, which is inferred from `runners.py` at v3.13.3, not run.

**The task dump is your leak profiler.** asyncio has no built-in view that groups tasks by where they wait. `leaks.task_dump()` does it. For each task, `where()` at `leaks.py:76` follows the chain of awaits to the innermost frame in your own files. It adds the asyncio function the task waits in. One line with a count of 10,000 is a leak. Expose the dump on a debug route, as `disconnect_api.py` does at `/debug/state`, and read it once before and once after a load test.

**What the linters catch.** Only the missing reference: ruff's RUF006 and flake8-async's ASYNC300 flagged `leaks.py:195`. Neither flagged patterns 1, 2 or 4. Part A's lab E4 shows the output.

**The sentence to remember:** every task a request starts must end before the request does. A `TaskGroup` makes that true, and a task count before and after a load test proves it.

**The trap:** fixing wasted work by returning early, while a helper task still waits for an end marker that the early return never sends. `/polled` stopped the work of 10,000 requests and leaked 10,000 tasks.

**Try this now:** run `uv run python phase04_concurrency/leaks.py --pattern queue-put --requests 1000 --dump`. Predict the leaky count and the dump line first. The run gives `tasks alive +1,000`, the dump line `1,000 x producer at leaks.py:137  waiting in Queue.put`, and `+0` for the fix.

---
## 4.8 — Deterministic and property-based concurrency tests (the test chooses the order)

Why this matters: a passing concurrency test tells you nothing unless you know which order of steps it ran. Most run one order that nobody chose. Some run a random order, fail one time in two, and get marked flaky.

**Answer this first.** A test runs the racy wallet from part A 200 times: two concurrent spends of 80 from 100. The ledger sleeps 1 ms. How many runs fail? How many with `AsyncMock` as the ledger? How many if the second spend arrives 0 to 2 ms after the first?

**asyncio does not shuffle.** The loop keeps ready callbacks in a deque at `base_events.py:423` and runs them first in, first out, FIFO, at line 2019. With no real I/O, a test runs the same order every time. The research pass ran three tasks that each yield once, 1,000 times. asyncio gave the order ABC 1,000 times. Trio 0.34.0, which reverses its ready batch at random, gave CBA 519 times and ABC 481 times. Neither is a search.

**Four ways to test the same property.** `interleavings.py` runs each test style 200 times, against the racy wallet and against the reserve fix:

```
property: two spends of 80 from 100 leave 20. 200 runs of each test style.
  racy     asyncmock   0/200 fail   gather 200/200 fail   jitter 110/200 fail   scheduler 200/200 fail
  reserve  asyncmock   0/200 fail   gather   0/200 fail   jitter   0/200 fail   scheduler   0/200 fail
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Failed runs of 200, racy wallet. The same bug, four test styles          │
├──────────────────────────────────────────────────────────────────────────┤
│ AsyncMock ledger      ▏                      0    never runs the race    │
│ gather, 1 ms ledger   ██████████████████████ 200  one fixed order        │
│ random arrival 0-2 ms ████████████           110  flaky                  │
│ step scheduler        ██████████████████████ 200  every order, by design │
├──────────────────────────────────────────────────────────────────────────┤
│ The reserve wallet: 0 of 200 in all four. Only the last row both         │
│ fails for the right reason and would find a different bad order.         │
└──────────────────────────────────────────────────────────────────────────┘
```

Read the rows:

1. **AsyncMock** never suspends, so the spends run one after the other. The race never happens.
2. **gather with a real sleep** fails every run, but tests only the one order FIFO produces. Make that order safe, and another bad order goes untested.
3. **Random arrival** fails 110 of 200: the flaky test that gets retried until green. Luo et al., FSE 2014, studied 161 fixes of flaky tests: 20% concurrency, 45% "async wait". Of the fixes that changed the code under test, 94% fixed a real bug.
4. **The step scheduler** runs every order and fails when any one breaks the rule.

**How the test takes control.** Each task calls `await sched.point(label)` where it may be interleaved. The point parks the task on its own `asyncio.Event`. The driver lets every runnable task reach its next point, then picks one parked task and releases it. The function that picks is the schedule. This is `step_scheduler.py:68` and `:91`:

```python
    async def point(self, label: str) -> None:
        name = asyncio.current_task().get_name()
        ...
        ev = asyncio.Event()
        self.parked[name] = ev
        await ev.wait()                      # stay here until drive() picks this task
        self.log.append(f"{name}:{label}")

    async def drive(self, tasks: list[asyncio.Task], choose: Choose) -> None:
        while True:
            await self._settle(tasks)
            if all(t.done() for t in tasks):
                return
            ...
            names = sorted(self.parked)
            who = choose(names)
            self.parked.pop(who).set()
```

The `...` lines are the mutation switch and the deadlock check. In the wallet test, each spender parks at `start`, before its check, and at `ledger`, inside the gated ledger, before its act:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The test owns the order. Two spenders, two points each                   │
├──────────────────────────────────────────────────────────────────────────┤
│           T0                      driver                  T1             │
│           point("start") ─► parked         parked ◄─ point("start")      │
│                               release T0                                 │
│           check 100 >= 80                                                │
│           point("ledger") ─► parked                                      │
│                               release T1                                 │
│                                               check 100 >= 80            │
│                                         parked ◄─ point("ledger")        │
│                               release T0                                 │
│           act: 100 - 80 = 20, done                                       │
│                               release T1                                 │
│                                               act: 20 - 80 = -60         │
├──────────────────────────────────────────────────────────────────────────┤
│ schedule T0 T1 T0 T1: both checks before either act. -60, every run      │
└──────────────────────────────────────────────────────────────────────────┘
```

**The deterministic test.** `test_wallet.py` is a plain `unittest` file. Its first test, at `test_wallet.py:104`, forces that schedule with `scripted(["T0", "T1", "T0", "T1"])` and asserts a balance of 20. Its second test runs every schedule with `step_scheduler.explore`, a depth-first search over the driver's choices. The suite, run 100 times on the racy wallet and on the two fixes:

```
variant racy: 100 runs of the suite, 1 distinct outcome(s)
   100 runs: 2 failed
        test_both_check_before_either_acts: AssertionError: -60 != 20 : two spends of 80 from 100: results [True, True], schedule ['T0:start', 'T1:start', 'T0:ledger', 'T1:ledger']
        test_every_interleaving: AssertionError: 4 of 6 interleavings overdraw; first: balance -60, schedule ['T0:start', 'T1:start', 'T0:ledger', 'T1:ledger']
variant lock: 100 runs of the suite, 1 distinct outcome(s)
   100 runs: 0 failed
variant reserve: 100 runs of the suite, 1 distinct outcome(s)
   100 runs: 0 failed
```

This is the demonstration the phase promised: one outcome in 100 runs, the same message each time, and a pass on both fixes.

**Why 4 of 6.** Each spender has two steps, start and ledger, and each keeps its own order. Two spenders give 4! / (2! × 2!) = 6 orders. The spend overdraws when both starts come before both ledgers: T0 T1 then either ledger first, or T1 T0 then either ledger first. That is 4. With three tasks of two steps, `step_scheduler.py --tasks 3` counts 6! / 2³ = 90 orders. Only the 3! = 6 orders that keep each read next to its write are correct, so 84 lose an update.

The number of orders grows fast, so exhaustive search works only for small tests. CHESS, from Microsoft Research at OSDI 2008, took control of thread scheduling the same way and searched orders with few preemptions first. It found 27 bugs in 8 systems. 21 of the 25 new ones had not shown up in months of stress runs. In CHESS's experience, two preemptions reproduced very serious bugs.

**Let Hypothesis choose the order.** A property-based test states a rule that must hold for every input, and a library generates the inputs. Hypothesis is such a library, and it can draw the schedule as test data. It then searches, and shrinks a failure to the smallest one it can find. Hypothesis does not run `async def` tests itself, so the test calls `asyncio.run` inside a normal function. This is `interleavings.py:156`, shortened:

```python
    def prop(data: st.DataObject) -> None:
        costs = data.draw(st.lists(st.integers(10, 100), min_size=2, max_size=4), label="costs")

        def choose(names: list[str]) -> str:
            return data.draw(st.sampled_from(names))
        balance, log = asyncio.run(scheduled(choose, strategy, costs))
        assert balance >= 0, f"costs {costs} left balance {balance}, schedule {log}"
```

```
Hypothesis search, max_examples=300, derandomize=True. A call of the test is
counted every time Hypothesis runs it, so the count can pass max_examples:
  racy     falsified after 64 calls of the test, shrinking included. Smallest case:
           costs [10, 91], balance -1, schedule T0:start T1:start T0:ledger T1:ledger
  reserve  passed 376 calls of the test
```

Hypothesis drew 2 to 4 spenders with any costs, and shrank the failure to 2 spenders, the forced schedule, and costs of 10 and 91. Their sum, 101, is the smallest total that overdraws 100. `derandomize=True` makes the failure replay on every run.

**Where this stops working.** The driver treats the tasks as settled when nothing changes for 20 turns of the loop. That is a heuristic, because asyncio has no public "every task is blocked" hook. Go 1.25's `testing/synctest` and Trio's `wait_all_tasks_blocked` have one. Real I/O breaks the heuristic, so use gated fakes. And a step point finds interleavings only where you marked one.

**The sentence to remember:** a concurrency test proves something only when it controls the order. Make every suspension on shared state a point the test can release, then force the bad order or search them all.

**The trap:** a concurrency test that passes with `AsyncMock`, or passes after three retries. The first never ran the race. The second ran it at random. In this lab, one passed 200 of 200 and the other failed 110 of 200, on the same bug.

**Try this now:** run `uv run python phase04_concurrency/step_scheduler.py --tasks 3`. Predict the two numbers from the arithmetic above first. The run gives `90 distinct schedules, 84 lose an update`.

---
## 🧪 Hands-on lab — part B

**Run status:** every command below was executed on 2026-09-25 on an Apple M2 with 8 GB, macOS 15.7.8 and CPython 3.13.3 through uv. Each "Expected" line is copied from `runs/lab4-*.log`. Timings will differ on your machine. Counts, pass and fail should not.

All commands run from `elite-performance/code/`. `bash runs/lab4.sh C B L D T K` runs this lab and saves each log. Part D starts its own servers on free ports and stops only those.

- [ ] **E7 (offline).** Where a cancel stops, and where a deadline is dropped.
  - Run: `uv run python phase04_concurrency/cancel.py --part swallow deadline --repeat 3`.
  - Before you run it, predict the "caller back" and "last step done" columns for all seven rows.
  - Expected: `bare except:` gives `result 'finished anyway'  cancelled() False`. The swallowed row gives `caller back at 1.02-1.03 s  TimeoutError no`. The `create_task`, `shield` and `to_thread` rows give the caller control at 0.10 s and finish their last step after 1 s.
  - If a row differs by more than 50 ms: the laptop is busy. Check the load average at the top of the log.
  - Teaches: a deadline travels down the awaits and stops at every place that has no owner or swallows the cancel.

- [ ] **E8 (break-it, offline).** A cancel that leaves a connection half used.
  - Run: `uv run python phase04_concurrency/cancel.py --part shared`.
  - Expected: `reuse the connection  : ... bob ... got 'value-of-alice:card'` and `discard the connection: ... got 'value-of-bob:card' (2 connection(s) opened)`.
  - Then run `uv run python phase04_concurrency/cancel.py --self-test --mutate reuse-conn`. Expected: `[FAIL] RIGHT, discard: bob reads his own reply: {'bob_got': 'value-of-alice:card', 'connections_opened': 1}`.
  - Teaches: every suspension point is a place where a cancel can stop a protocol in the middle.

- [ ] **E9 (local).** Client disconnects on a live API, and the 10,000-request count. This is the phase's demonstration.
  - Run: `uv run python phase04_concurrency/disconnect_api.py --timeline`, then `uv run python phase04_concurrency/disconnect_api.py --route /plain /polled /owned --requests 10000`. About 45 seconds.
  - Expected: `/plain` `8 step(s) after the client left`. `/trap` `body='<timed out waiting for body>'`. Then `/plain` `server tasks 1 before, 1 after (+0)` with `ran all 10 steps 10,000`, `/polled` `10,001 after (+10,000)`, `/owned` `1 before, 1 after (+0)` with `stopped early 10,000`.
  - Break it: `uv run python phase04_concurrency/disconnect_api.py --self-test --mutate no-taskgroup` starts `/owned`'s publisher with `create_task`. Expected: `[FAIL] /owned: tasks back to baseline: 1 -> 31`. The self-test starts a fresh server per route, so the baseline is that server's own single task.
  - If `handlers started` is below 10,000: some clients reset before the server read the request. Raise `--disconnect-ms`.
  - Teaches: a disconnect stops nothing until the code makes it a cancel, and only an owner makes the cancel reach every task.

- [ ] **E10 (offline).** Bound the tasks, not only the calls.
  - Run: `uv run python phase04_concurrency/bounded.py --repeat 3 --memory`.
  - Before you run it, compute the missed deadlines of `gather` from the arithmetic.
  - Expected: `gather` 5,500 to 5,700 errors and `peak tasks 10,000`. `semaphore` 0 errors and `peak tasks 10,000`. `workers` 0 errors and `peak tasks 100`. Memory 20.5, 16.4 and 0.3 MB.
  - Teaches: a semaphore moves the wait, a worker pool removes the tasks.

- [ ] **E11 (offline).** Four leak patterns and the task dump.
  - Run: `uv run python phase04_concurrency/leaks.py --dump`.
  - Expected: `queue-get leaky ... tasks alive +10,000` with `dump: 10,000 x publisher at leaks.py:110  waiting in Queue.get`. Every `fixed` row `+0`. `(b) 'Task was destroyed but it is pending!': 10,000`. `12 ran to the end for a gone caller`, and `heartbeat threads alive after the requests: +200`.
  - Then find the task dump line for `queue-put` and open that file and line. It is the line that leaked.
  - Teaches: count tasks before and after, and group what is left by where it waits.

- [ ] **E12 (break-it, offline).** The test that fails the same way every run.
  - Run: `uv run python phase04_concurrency/test_wallet.py --variant racy`, then `--variant reserve`, then `uv run python phase04_concurrency/test_wallet.py --variant racy --repeat 100`, then `uv run python phase04_concurrency/interleavings.py`.
  - Expected: racy `FAILED (failures=2)` with `-60 != 20` and `4 of 6 interleavings overdraw`. Reserve `OK`. `100 runs of the suite, 1 distinct outcome(s)`. Then `jitter 110/200 fail`, and `falsified after 64 calls of the test` shrunk to `costs [10, 91], balance -1`.
  - Break it: `uv run python phase04_concurrency/test_wallet.py --self-test --mutate fake-ledger` swaps the gated ledger for one that never suspends. Expected: the racy wallet passes both race tests, and the self-test prints `[FAIL] racy: the search counts 4 of 6 bad interleavings`.
  - Teaches: a test controls the order only through a suspension it owns. Remove the gate and the race tests go green on broken code.

---

## 🔍 Check it yourself

1. Open `phase04_concurrency/disconnect_api.py:154`. This is `owned`. Its watcher raises `ClientGone`, and the handler catches it with `except*`. Why `except*` and not `except`? What would happen to the publisher if the watcher returned instead of raising?

2. Open `phase04_concurrency/cancel.py:215`. This is `get`. It closes the connection on `BaseException`, not `Exception`. Which exception would `except Exception` miss, and which user would then read whose data?

3. Open `phase04_concurrency/step_scheduler.py:79`. This is `_settle`. Why does it wait for 20 turns with no change, and not for every task to be parked? Which task in the lock variant of the wallet test is neither parked nor done?

4. In any asyncio service you own, run:

   ```bash
   grep -rnE "create_task\(|ensure_future\(|except:|except BaseException|to_thread\(|shield\(" --include='*.py' <your repo>/
   ```

   For every `create_task`, name the owner that waits for the task or cancels it. For every `except:` or `except BaseException`, check that a `CancelledError` goes on. For every `to_thread`, name how the thread learns that its caller is gone.

---

## ✅ Checkpoint 4B — answer in your own words

1. **Walk through what happens when** a client disconnects 0.3 s into a `/polled` request on uvicorn 0.53.0 with Starlette 1.7.0. Name each component, what it does, and what is alive afterwards. Then say what a task dump shows after 1,000 such disconnects.

2. **Predict.** A handler does `t = asyncio.create_task(stream_tokens(q))`, stores `t` in a set, then awaits `llm.generate(q)`. `generate` puts tokens on `q` and puts `None` at the end. The handler runs inside `asyncio.timeout(30)`. 1,000 requests hit the 30 s deadline. How many tasks leak, where does the dump say they wait, and what is the one-line fix?

3. **Show the arithmetic.** A batch job fans out 10,000 calls with `asyncio.gather` through a pool of 50 connections. Each call holds a connection for 40 ms, and has a 2 s deadline that covers its wait. (a) How many calls can start before the deadline, and about how many miss it? What changes if the only timeout is httpx's pool timeout? (b) How long does the job take with 50 workers? (c) How many tasks exist at the peak in each case?

4. **A colleague says:** "Every call is inside `asyncio.timeout(2)`. So a slow dependency can never hold a request longer than 2 s." The code retries each call in a loop that catches and logs `BaseException`. One step runs a sync library through `asyncio.to_thread`. Argue with numbers from section 4.5.

5. **This is broken.** A concurrency test for a single-flight cache, which lets one fetch per key run while the others wait for it, has passed 1,000 runs in CI. In production the backend still gets duplicate fetches for the same key under load. The test uses `AsyncMock` for the backend. What is the cause, why does CI pass, and how do you write the test that fails?

6. **Demonstrate.** Design the deterministic test for the cache in question 5. Where do the step points go? Which schedule do you force? For two callers with two points each, how many schedules does an exhaustive search run? How many fetch twice on the broken cache?

<details>
<summary>Answer sketches</summary>

1. uvicorn's `connection_lost` marks the request disconnected and wakes `receive()`, but does not cancel the app task. The handler finishes its current step. `is_disconnected()` then reads `http.disconnect`, and the handler returns early. Its publisher still waits on `Queue.get` for a `None` never sent. After 1,000 disconnects the dump shows one line: `1,000 x publisher at <file>:<line>  waiting in Queue.get`.

2. 1,000 tasks leak. The timeout cancels the handler inside `llm.generate`, so `None` never reaches `q`. The dump shows `1,000 x stream_tokens at <file>:<line>  waiting in Queue.get`. Fix: start `stream_tokens` inside an `asyncio.TaskGroup` that wraps the `generate` call, inside the timeout. The group cancels it with the handler.

3. (a) 50 / 40 ms = 1,250 calls per second, so 2,500 can start in 2 s. About 10,000 − 2,500 = 7,500 miss it, a few more in practice. With httpx's pool timeout alone, which restarts on each wait, most calls wait instead of failing. (b) 10,000 / 1,250 = 8 s. (c) `gather`: 10,000 tasks. 50 workers: 50. A semaphore around each call: still 10,000.

4. Against. A loop that catches `BaseException` swallows the cancel that `timeout` sends. In section 4.5 a 0.1 s deadline over 1 s of such work returned at 1.02 to 1.03 s with no `TimeoutError`. `to_thread` releases the caller at 0.10 s, but the thread runs on to 1.07 s. Under load those threads fill the pool of 12 and delay every other `to_thread` call. Fix: catch `Exception`, or re-raise `CancelledError`, and give the thread a stop flag.

5. `AsyncMock` never suspends, so the first caller fetches and stores before the second checks. 1,000 runs test that one order 1,000 times. Production's backend suspends, and two callers both miss. Write the test with a gated backend that parks at a step point, and force both checks before either store.

6. Points: one at the start of `get`, before the cache check, and one inside the gated backend, before it returns. Force T0 start, T1 start, T0 backend, T1 backend. Assert one backend call. Exhaustive: 4! / (2! × 2!) = 6 schedules. The broken cache fetches twice when both starts come before both backend releases. That is 4 of 6, the same count as the wallet.

</details>

---

## References & Further Learning — part B

Every URL below was fetched on 2026-09-25 and returned HTTP 200, except where an entry says otherwise. Source files are cited at a tag.

**Disconnects and cancellation**

- **uvicorn `protocols/http/h11_impl.py` at tag 0.53.0** — https://raw.githubusercontent.com/encode/uvicorn/0.53.0/uvicorn/protocols/http/h11_impl.py
  Focus on: `connection_lost` at line 107, which never cancels the app task, and `send` at line 459, which drops a late reply silently.
- **Starlette `responses.py` and `requests.py` at tag 1.7.0** — https://raw.githubusercontent.com/encode/starlette/1.7.0/starlette/responses.py
  Focus on: `StreamingResponse.__call__` from line 259, and `is_disconnected` at line 328 of `requests.py` in the same tag.
- **"Coroutines and Tasks", Python 3.13 docs** — https://docs.python.org/3.13/library/asyncio-task.html
  Focus on: "Task Cancellation", `Task.cancel`, `cancelling`, `timeout`, `shield`, and the "Important" box under `create_task`.
- **What's New in Python 3.8** — https://docs.python.org/3/whatsnew/3.8.html
  Focus on: the asyncio item that made `CancelledError` a `BaseException`.
- **redis-py issue #2624, "Canceling async Redis command leaves connection open, in unsafe state for future commands"** — https://github.com/redis/redis-py/issues/2624
  Focus on: the reproducer, opened 2023-03-17 against redis-py 4.5.1. It is the bug behind OpenAI's 20 March 2023 incident. OpenAI's write-up, dated 24 March 2023, is at openai.com under `/index/march-20-chatgpt-outage/`. It returns HTTP 403 to scripts, so it was read in a browser on 2026-09-25 and is not linked. The excerpts used are in `runs/lab4-openai-read.log`.
- **litellm issue #35329** — https://github.com/BerriAI/litellm/issues/35329
  Focus on: a swallowed cancel that let a paid fallback call run for a client that had gone. An issue report.
- **CPython `Lib/asyncio/runners.py` at v3.13.3** — https://raw.githubusercontent.com/python/cpython/v3.13.3/Lib/asyncio/runners.py
  Focus on: `shutdown_default_executor` with `THREAD_JOIN_TIMEOUT`, 300 s, at exit.

**Bounded concurrency and leaks**

- **httpx resource limits at tag 0.28.1** — https://raw.githubusercontent.com/encode/httpx/0.28.1/docs/advanced/resource-limits.md
  Focus on: `max_connections`, default 100.
- **CPython `Lib/asyncio/tasks.py` at v3.13.3** — https://raw.githubusercontent.com/python/cpython/v3.13.3/Lib/asyncio/tasks.py
  Focus on: `_scheduled_tasks = weakref.WeakSet()` at line 1039, and the "Task was destroyed but it is pending!" message at line 134.
- **`concurrent.futures`, Python 3.13 docs** — https://docs.python.org/3.13/library/concurrent.futures.html
  Focus on: `Future.cancel`, which returns False for a call that is already running.

**Deterministic and property-based tests**

- **Musuvathi et al., "Finding and Reproducing Heisenbugs in Concurrent Programs", OSDI 2008** — https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/osdi2008-CHESS.pdf
  Focus on: Section 4.4.1 on preemption bounding, and Section 5.3 with Table 3.
- **Luo, Hariri, Eloussi, Marinov, "An Empirical Analysis of Flaky Tests", FSE 2014** — https://mir.cs.illinois.edu/lamyaa/publications/fse14.pdf
  Focus on: Table 1, and findings F.4, F.6 and F.12.
- **CPython `Lib/asyncio/base_events.py` at v3.13.3** — https://raw.githubusercontent.com/python/cpython/v3.13.3/Lib/asyncio/base_events.py
  Focus on: `self._ready` at line 423 and `popleft()` at line 2019.
- **Trio `_core/_run.py` at v0.34.0** — https://raw.githubusercontent.com/python-trio/trio/v0.34.0/src/trio/_core/_run.py
  Focus on: the batch reversal in the scheduler, and the Hypothesis hook that makes the schedule a test input. Not run by the course code. The research pass ran it once.
- **Hypothesis source at v6.168.1** — https://github.com/HypothesisWorks/hypothesis/tree/v6.168.1/hypothesis
  Focus on: `docs/stateful.rst` for model-based tests. The docs have no guide to concurrent code.
- **Damien Neil, "Testing concurrent code with testing/synctest", The Go Blog, 2025** — https://go.dev/blog/synctest
  Focus on: the "durably blocked" definition, the hook `step_scheduler._settle` guesses at. The blog shows the Go 1.24 experiment. The 1.25 API is in https://go.dev/doc/go1.25 .

---

## Cheatsheet — part B

```
CANCELLATION
  uvicorn 0.53 disconnect  marks it, never cancels the handler
  cancel lands at          the next REAL suspension point
  blocking call            delays it: 0.1 s deadline returned at 0.30 s
  CancelledError           BaseException since 3.8: except Exception is fine
  bare except / except BaseException without raise   swallows it
  swallowed + timeout(0.1) returned at 1.02-1.03 s, no TimeoutError
  not reached by a cancel  create_task helper, shield, to_thread
  handler notices          watcher in a TaskGroup, StreamingResponse,
                           or is_disconnected() AFTER reading the body
  half-done protocol       a call that did not finish closes its connection

BOUNDED CONCURRENCY
  pool served per second   pool / hold      100 / 20 ms = 5,000
  gather 10,000, 1 s deadline per call   5,500-5,700 missed, 10,000 tasks
  Semaphore(100)           0 missed, still 10,000 tasks, 16.4 MB
  100 workers              0 missed, 100 tasks, 0.3 MB
  httpx pool timeout       restarts on each wait: a big gather waits

LEAKS
  count                    tasks and threads before and after N requests
  dump                     group tasks by your line where each one waits
  10,000 disconnects       /polled +10,000   /owned +0   /plain +0, wasted
  patterns                 get from an unfed queue, put to an undrained one,
                           never awaited, a thread past its caller
  default thread pool      min(32, cores + 4) = 12 on an 8-core Mac

DETERMINISTIC TESTS
  asyncio order            FIFO: 1,000 runs = one schedule 1,000 times
  AsyncMock                never suspends: 0 of 200 runs fail on racy code
  step point               park on an Event; the test releases one task
  2 tasks x 2 points       4!/(2!2!) = 6 schedules, 4 overdraw
  3 tasks x 2 points       90 schedules, 84 lose an update
  Hypothesis               draw the schedule; shrank to costs [10, 91]
```

# Phase 4A — Concurrency correctness: shared state

**The question this phase answers:** how does a program that passes every test still corrupt state, or leak a task per request, in production?

The tests pass. In production, a counter is wrong by a few every day. The number of asyncio tasks in the process grows by one each time a client disconnects in the middle of a request. After some weeks, the service is restarted every night "for memory". This is a real pattern. In a 2023 write-up, one engineer describes a Python WebSocket backend whose CPU climbed from about 15% to 100% in about 11 hours. The cause was a set of tasks that nobody emptied. The container was restarted every 12 hours.

Both bugs are the same kind. The code assumed something about the order of events and never wrote it down. Running the code more does not find this kind of bug. You find it when you state what must be true about order and ownership. Then you write the test that breaks when it is false.

This phase teaches five ideas. Each is a claim you could get wrong today:

1. **The GIL makes no read-modify-write atomic.** It only limits the places where a thread can be switched out. On CPython 3.13, `counter += 1` lost 0 of 1.6 million updates across 8 threads, and `counter += one()` lost about 1.1 million. A test that shows no loss proves nothing. Only a lock, or a single owner that applies every change, makes the update correct.
2. **In asyncio, a task runs without interruption only between two points where it really suspends.**
   A check and an act with a real suspension between them is a race. No standard tool reports it, and a fake that never suspends hides it from your tests.
3. **Every piece of shared state and every task needs a written owner.** State with one owner needs no lock. A task whose owner does not bound it and wait for it leaks, once per request.
4. **A client disconnect stops nothing by itself.** uvicorn does not cancel the handler. A cancel stops work only at a suspension point, and only if nothing swallows `CancelledError`. At that point, shared state can be half done.
5. **A concurrency test is deterministic only when the test controls the interleaving.**
   asyncio runs tasks in the same order on every run. So running a test more is not a search.

Two terms recur. A **suspension point** is a place where a task stops and the loop runs another task. An **interleaving** is the order in which the steps of concurrent tasks run.

Two common beliefs are wrong here. `counter += 1` lost no updates on CPython 3.11 to 3.14, as section 4.1 shows. And an await that does not suspend hands over nothing, as section 4.2 shows.

Phase 4 is split into two documents. This one teaches the first three ideas as they apply to shared state. Part B teaches the other two, and the task half of the third.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, this document: shared state                                      │
│  4.1  What the GIL guarantees      — where a thread can be switched out  │
│  4.2  Data races, logical races    — the race no tool reports            │
│  4.3  Ownership                    — who may touch what, written down    │
│  4.4  Locks, queues, primitives    — which one, and the cost of the      │
│                                      wrong one                           │
│  Lab: E1 to E6                                                           │
│                                                                          │
│ PART B, the next document: lifetimes and tests                           │
│  4.5  Cancellation and deadlines   — where a cancel stops, and where not │
│  4.6  Bounded concurrency          — bound the tasks, not only the calls │
│  4.7  Task and thread leaks        — counted across 10,000 requests      │
│  4.8  Deterministic tests          — the test chooses the order          │
│  Lab: E7 to E12                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**What this part assumes.** Three earlier sections are used here and not taught again. The three-sentence version of each is enough.

- **Phase 1, section 1.4, "Baseline, one change, repeat".** A timing is not a result until you know how much it moves between runs. This phase avoids the problem where it can: most of its results are counts and pass or fail, which do not move. Where it times something, it runs three times and prints the range. The one-line "Try this now" commands run once.
- **Phase 2, section 2.2, "Head-of-line blocking (one slow step, and everyone behind it waits)".** An event loop is one queue served by one thread. Code that runs without an await holds that thread, and every other task waits. Section 4.4 meets this again as a lock that stops the loop.
- **Phase 3, section 3.4, "Lock and GIL contention".** Phase 3 times what a lock costs. This phase is about correctness, and measures a lock's cost only where it decides the design.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. Every number was measured on 2026-09-25 on an Apple M2 with 8 GB of memory, macOS 15.7.8, CPython 3.13.3 through uv. The packages are pinned in `pyproject.toml`: hypothesis 6.168.1, uvicorn 0.53.0, starlette 1.7.0 and httpx 0.28.1. The laptop ran on battery, at 87% to 91% and discharging. Other programs were running. The one-minute load average in this part's logs was 4.4 to 7.6. Every `runs/lab4-*.log` starts with the time, battery, load average and Python version. Most results here are counts, and a count does not depend on load.

Setup:

```bash
cd ~/Desktop/project/study-material/elite-performance/code
uv sync
uv run python phase04_concurrency/step_scheduler.py --self-test
```

The last line should print `self-test passed`.

Time for part A: about 1.5 hours. Nothing in it waits for a load run.

---
## 4.1 — What the GIL guarantees, and what it does not (where a thread can be switched out)

Why this matters: some engineers believe the GIL makes `+=` safe. Others know it is unsafe, write a test, see no loss, and conclude their code is fine. Both ship a counter that is wrong in production. This section gives the rule that predicts what you will see.

**Answer this first.** Eight threads each run `counter += 1` 200,000 times on CPython 3.13. How many of the 1.6 million updates are lost? Now change the line to `counter += one()`, where `one()` returns 1. How many now? Write two numbers down.

**What the GIL promises.** The GIL, the global interpreter lock, is a lock inside CPython. A thread must hold it to run Python bytecode. So on a normal build, one thread runs Python code at a time. A bytecode instruction is one step of the compiled program, such as "load a value" or "add two values". The Python FAQ states the promise: "Python offers to switch among threads only between bytecode instructions".

That promise is about single instructions. `counter += 1` is four of them. Since 3.11, CPython replaces an instruction with a faster form for the types it sees. This is called specialising. This is `gil_counter.py --dis` on CPython 3.13.3, after it has specialised each instruction:

```
plain  counter += 1                        LOAD_GLOBAL_MODULE LOAD_CONST BINARY_OP_ADD_INT STORE_GLOBAL
       switch point inside the read-modify-write: none
call   counter += one()                    LOAD_GLOBAL_MODULE LOAD_GLOBAL_MODULE CALL_PY_EXACT_ARGS BINARY_OP_ADD_INT STORE_GLOBAL
       switch point inside the read-modify-write: CALL_PY_EXACT_ARGS
```

A **read-modify-write** loads a value, changes it, and stores it back. If another thread stores between your load and your store, your store overwrites its work. That update is lost. The FAQ lists `i = i+1` among the operations that are not atomic, and ends the section with "When in doubt, use a mutex!".

**Where a switch can really happen.** CPython does not offer a switch after every instruction. It offers one only at a **switch point**, an instruction that checks for a pending switch. On 3.13.3, `Python/bytecodes.c` at that tag has three kinds. `RESUME` checks where every function starts. `JUMP_BACKWARD` checks where a loop jumps back. A call into C code checks after the call, except `CALL_LEN`, `CALL_ISINSTANCE`, `CALL_TYPE_1` and `CALL_LIST_APPEND`. A call to a Python function, such as `CALL_PY_EXACT_ARGS`, has no check itself. Its switch point is the `RESUME` where the called function starts. The change that moved switch points to these places is CPython pull request GH-18334, in 3.10. So a thread can lose the GIL between the load and the store only if a call sits between them:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Two threads run counter += one(). Example values.                        │
├──────────────────────────────────────────────────────────────────────────┤
│ step  thread A                          thread B                         │
│  1    LOAD counter      reads 41                                         │
│  2    CALL one()        ◄ switch point, RESUME in one(): GIL to B        │
│  3                                      LOAD counter      reads 41       │
│  4                                      CALL, ADD, STORE  writes 42      │
│  5                                      1,000 more loops  counter = 1,042│
│  6    ◄ the GIL comes back                                               │
│  7    ADD               41 + 1 = 42                                      │
│  8    STORE counter     writes 42. B's 1,001 updates are gone            │
├──────────────────────────────────────────────────────────────────────────┤
│ counter += 1 has no switch point between LOAD and STORE. The next check  │
│ is the loop's JUMP_BACKWARD, after the STORE. So nothing is lost.        │
└──────────────────────────────────────────────────────────────────────────┘
```

**What 8 threads lost.** `gil_counter.py` runs each loop body three times. The default switch interval is 5 ms. `sys.setswitchinterval(1e-6)` asks for a switch every microsecond, which makes a switch far more likely at each switch point. It does not add switch points. At a 1 µs interval, out of 1,600,000 updates:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Updates lost of 1,600,000, 8 threads, 1 us switch interval. Lab part G   │
├──────────────────────────────────────────────────────────────────────────┤
│ counter += 1           ▏                      0, 0, 0                    │
│ counter += len(s)      ▏                      0, 0, 0                    │
│ counter += one()       ████████████████       1,105,080 to 1,163,637     │
│ counter += abs(1)      ████████████████       1,161,878 to 1,208,151     │
│ stats[k] = .get(k)+1   ████████████████       1,183,562 to 1,221,035     │
│ with lock: += one()    ▏                      0, 0, 0 at 5 ms            │
├──────────────────────────────────────────────────────────────────────────┤
│ len() and abs() have the same shape. CALL_LEN is not a switch point.     │
│ CALL_BUILTIN_O is one. That alone moves the loss from 0 to 73-76%.       │
└──────────────────────────────────────────────────────────────────────────┘
```

At the default 5 ms interval they still lost updates. `one()` lost 643,341 to 932,320, and the `dict.get` counter 652,934 to 1,054,194. The loss changes a lot from trial to trial. On 3.13 every trial with a call inside the update lost updates. But the research pass saw one trial on 3.14.3, at 5 ms, lose 0 with a call inside. So a zero from one run proves nothing.

The `stats[k] = stats.get(k, 0) + 1` line matters most. It is the counter most services write. `dict.get` is a call, and its specialised form, `CALL_METHOD_DESCRIPTOR_FAST`, checks for a switch. Real updates are full of calls: a helper, a property, a logging line, the `__hash__` of a key.

**The version you run changes the answer.** The research pass ran the same kind of script on five versions. The plain loop lost updates only on 3.9.6. The loop with a call lost updates on all five. 3.10 was not run. It should behave like 3.11, which is inferred from the change's version. The free-threaded build removes the GIL, so threads really run at the same time:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Where a thread can be switched out, by build                             │
├──────────────────────────────────────────────────────────────────────────┤
│ CPython 3.9         mechanism not checked here. Measured:                │
│                     counter += 1 lost 123,520 to 291,954 of 1.6 million  │
├──────────────────────────────────────────────────────────────────────────┤
│ CPython 3.10        at a function start, a loop's jump back, most calls  │
│ to 3.14, GIL        counter += 1 lost 0 on 3.11 to 3.14. 3.10 not run    │
├──────────────────────────────────────────────────────────────────────────┤
│ free-threaded       no GIL: threads run at the same time on many cores   │
│ 3.13t and 3.14t     supported, still optional, since 3.14 (PEP 779).     │
│                     per-object locks keep a dict or list intact. PEP 703:│
│                     they do not make an operation atomic. Not run here   │
└──────────────────────────────────────────────────────────────────────────┘
```

For the free-threaded build, PEP 703 is plain: "the per-object locking scheme also cannot ensure that concurrent operations are atomic or correct". The 3.14 documentation page "Thread Safety Guarantees" marks `d[key] = d[key] + 1` with the comment "NOT atomic: read-modify-write". Not run here: this laptop has no free-threaded interpreter, so the claim rests on those two documents.

**WRONG: trust a test that shows no loss.** This is a test you might write. It is not in the course code. The output below comes from `gil_counter.py`, which runs the same loop:

```python
# WRONG: "the GIL makes += safe, and the test proves it"
threads = [threading.Thread(target=body_plain, args=(200_000,)) for _ in range(8)]
for t in threads: t.start()
for t in threads: t.join()
assert counter == 1_600_000          # passed on 3.11 to 3.14, every time
```

```
plain  counter += 1                        switch interval 1e-06  s  lost per trial: 0, 0, 0   (2.7 s)
call   counter += one()                    switch interval 1e-06  s  lost per trial: 1,129,458, 1,163,637, 1,105,080   (4.0 s)
```

The test passes because this one line has no call in it. The next person to write `counter += weight(item)` loses 69% to 73% of the updates at a 1 µs switch interval, and 40% to 58% at the default 5 ms. The test still passes, because it tests the old line.

**RIGHT: a lock around the whole read-modify-write.** This is `gil_counter.py:94`, with the mutation switch that the self-test uses to remove the lock on purpose:

```python
def body_lock(n: int) -> None:
    global counter
    for _ in range(n):
        if _USE_LOCK:
            with _lock:
                counter += one()
        else:
            counter += one()
```

```
lock   with lock: counter += one()         switch interval 0.005  s  lost per trial: 0, 0, 0   (1.9 s)
```

With the lock removed by `--mutate no-lock`, the self-test fails: `[FAIL] lock loses nothing: lost [591013, 574246]`. The lock has a cost. The three locked trials took 1.9 s, against 0.5 s for the same loop without it, in one run on a busy laptop. Phase 3, section 3.4, measures that cost.

**The answer to the question.** `counter += 1` lost 0 of 1.6 million on CPython 3.13. `counter += one()` lost 1,105,080 to 1,163,637. The difference is one call instruction between the load and the store.

**The sentence to remember:** the GIL decides where a thread can be switched out, not which operations are atomic. Every read-modify-write of shared state needs a lock, or a single owner that applies every change.

**The trap:** a test of `counter += 1` showed no loss on CPython 3.11 to 3.14. It passes because no call sits inside the update. The first change that adds a call, such as `dict.get`, brings back a loss of 74% to 76% at a 1 µs switch interval, and 41% to 66% at the default. The old test still passes.

**Try this now:** run `uv run python phase04_concurrency/gil_counter.py --modes len abs --interval 1e-6 --trials 1`. Predict both numbers from the bytecode above first. The lab run gave 0 for `len` and 1,165,802 for `abs`.

---
## 4.2 — Data races versus logical races (the race no tool reports)

Why this matters: a race detector reports data races. Many concurrency bugs in Python are logical races. If you do not know the difference, a clean report from a tool tells you the code is safe when it is not.

**Answer this first.** Two asyncio tasks each spend 80 credits from a balance of 100. The code checks the balance, awaits a ledger write, then subtracts. There is only one thread. Can both spends succeed? Does your answer change if the ledger in your test is a `unittest.mock.AsyncMock`?

**Two kinds of race.** They are found by different tools, so keep the names apart.

- A **data race** happens when two threads access the same memory at once, one of them writes, and nothing orders the two. It is defined at the machine level. In C it is undefined behaviour. ThreadSanitizer, a compiler tool, finds data races. CPython 3.13 can be built with it, through `--with-thread-sanitizer`.
- A **logical race**, or race condition, happens when the result depends on the order of steps. Some order breaks a rule the program needs. Every single step can be atomic, and the sequence can still be wrong. The lost update of section 4.1 is a logical race. So is check-then-act: code checks a condition, then acts on it, and something changes the condition in between.

**Happens-before** is the rule that orders two events. Event A happens before event B when the program guarantees that B sees what A did. In Python you get it from a few places. Within one task or thread, a line happens before the next line. A lock's release happens before the next acquire of that lock. A queue's `put` happens before the `get` that returns that item. Two events with no happens-before order between them may occur in either order. A correct program works for both orders.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Two kinds of race, and what can see each                                 │
├──────────────────────────────────────────────────────────────────────────┤
│                     DATA RACE                  LOGICAL RACE              │
│ what it is          two threads touch one      the result depends on the │
│                     memory word, one writes,   order of steps, and one   │
│                     nothing orders them        order breaks a rule       │
│ level               machine: C code, memory    program: your logic       │
│ in pure Python      none with the GIL: each    yes: lost updates (4.1),  │
│ with the GIL        interpreter's C code is    check-then-act (below)    │
│                     serialised. Inferred                                 │
│ in asyncio          none: one thread           yes, at every suspension  │
│ found by            ThreadSanitizer,           no standard tool. A test  │
│                     --with-thread-sanitizer    that controls the order   │
└──────────────────────────────────────────────────────────────────────────┘
```

**One thread, and still a race.** The asyncio documentation puts it this way:

> "When a Task executes an await expression, the running Task gets suspended, and the event loop executes the next Task."

That is almost exact. A task is suspended only when the thing it awaits is not ready yet: a pending future, a sleep, a socket with no data. An await on a coroutine that returns without waiting on any of those hands over nothing. So the precise rule is: a task runs without interruption between two points where it really suspends.

This is the check-then-act in `wallet.py:146`:

```python
    async def _racy(self, user: str, cost: int) -> bool:
        if self.balances[user] >= cost:              # check
            await self.ledger.record(user, cost)     # a suspension point
            self.balances[user] -= cost              # act, on a balance that may have changed
            return True
        return False
```

`wallet.py` runs two spends of 80 from 100 with `asyncio.gather`, against four ledgers. Three of the rows:

```
racy     nosuspend  results [True, False]                balance   20
racy     sleep0     results [True, True]                 balance  -60   <- two spends of 80 from 100 both succeeded
racy     sleep      results [True, True]                 balance  -60   <- two spends of 80 from 100 both succeeded
```

With `sleep0`, the ledger does `await asyncio.sleep(0)`, which always suspends. With `sleep`, it waits 1 ms, like a database write. Both went negative. With `nosuspend`, the ledger is an `async def` that appends to a list and returns. The same code gave the right answer.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Two spends of 80 from a balance of 100, one thread                       │
├──────────────────────────────────────────────────────────────────────────┤
│ T0  check: 100 >= 80, yes                                                │
│ T0  await ledger.record()   ◄ suspends: the loop runs the next task      │
│ T1  check: 100 >= 80, yes   ◄ the balance T0 checked has not changed yet │
│ T1  await ledger.record()   ◄ suspends                                   │
│ T0  act: 100 - 80 = 20                                                   │
│ T1  act:  20 - 80 = -60     ◄ acts on a check that is no longer true     │
├──────────────────────────────────────────────────────────────────────────┤
│ With a ledger that never suspends, T0 runs check, record, act in one     │
│ piece, then T1 checks 20 >= 80 and refuses. Same code, right answer.     │
└──────────────────────────────────────────────────────────────────────────┘
```

**A fake that never suspends hides the race.** `unittest.mock.AsyncMock` returns without suspending, like any `async def` fake with no await inside. In section 4.8, a test with `AsyncMock` passed 200 of 200 runs on this racy code. It ran the two spends one after the other. The code can also change under you. Someone adds real I/O inside a helper that never suspended. A check-then-act that was safe without any planned lock becomes a race, and nobody edited the check or the act.

**No standard tool reports it.** Lab part X runs ruff 0.16.9 and flake8-async 26.8.1 on this phase's code. They flag the task started with no reference, the bare `except`, and the blocking `time.sleep` in an async function. Neither reports anything in `wallet.py`'s `_racy`. ThreadSanitizer cannot see it either, because one thread does every read and every write. That part is inferred from how ThreadSanitizer works. asyncio's debug mode reports slow callbacks and coroutines that were never awaited, not races. "No standard tool" is true for the tools named here. It is not proven for every tool that exists.

**The sentence to remember:** a check and an act are safe together only when no real suspension sits between them. Every await on real I/O is a place where another task can change what you checked.

**The trap:** a test with `AsyncMock`, or any fake that returns without suspending, runs your concurrent calls one after the other. It passes on racy code. In production the real database call suspends, and two spends of 80 from 100 both succeed.

**Try this now:** run `uv run python phase04_concurrency/wallet.py --strategy racy --ledger nosuspend sleep0`. Predict both balances first. The run gives 20 with the ledger that never suspends and -60 with `sleep0`.

---
## 4.3 — Ownership (who may touch what, written down)

Why this matters: a lock is one fix. Ownership is the rule that tells you whether you need a fix at all. Without it written down, each new line picks its own assumption. After a year, one path holds five assumptions, and nobody knows which is true.

**Answer this first.** An asyncio handler updates a process-wide dict of counters. It reads through a shared cache, starts a task that forwards progress, and sends CPU work to `asyncio.to_thread`. Which of these needs a lock? Which needs something else?

**The owner, and the rule.** For each piece of mutable state, name one owner: the thread, task or object that may write it. For each task, name one owner: the code that makes sure it ends. Then the rule decides what the state needs:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Does this state need a lock?                                             │
├──────────────────────────────────────────────────────────────────────────┤
│ Is it changed after other code can see it?                               │
│  └ no ──► nothing. It is immutable                                       │
│  └ yes: is it written from more than one thread?                         │
│      └ yes ──► threading.Lock, or send each change to the owner thread   │
│      └ no, one thread: does any update suspend between read and write?   │
│          └ no ──► nothing. The loop runs each update without a switch    │
│          └ yes ──► asyncio.Lock per key, or the reserve pattern,         │
│                    or one owner task fed by a queue. See 4.4             │
├──────────────────────────────────────────────────────────────────────────┤
│ Every task: its owner waits for it or cancels it before the owner        │
│ returns. The owner also bounds how many exist. See 4.6 and 4.7.          │
└──────────────────────────────────────────────────────────────────────────┘
```

The task rule has a name: structured concurrency. Nathaniel J. Smith's 2018 post calls a task group a nursery, and states the rule: "the nursery block doesn't exit until all the tasks inside it have exited". asyncio's `TaskGroup`, added in 3.11, follows the same rule. Its documentation says: "All tasks are awaited when the context manager exits."

**One path, written down.** `ownership.py` models a request path with five things in it. Here is the path and its owners:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One request path and the owner of each part                              │
├──────────────────────────────────────────────────────────────────────────┤
│  process-wide ┌────────────────┐     ┌──────────────────────────┐        │
│  state        │ stats counters │     │ cache: key -> header     │        │
│               │ owner: loop    │     │ owner: Cache, a lock per │        │
│               │ thread         │     │ key for each fetch       │        │
│               └───────▲────────┘     └────────────▲─────────────┘        │
│                       │ writes                    │ get(key)             │
│  ┌────────────────────┴───────────────────────────┴───────────────┐      │
│  │ request task                                                   │      │
│  │ ┌──────────────────────────────────────────────────────────┐   │      │
│  │ │ TaskGroup: owns every task the request starts            │   │      │
│  │ │ progress queue ──────────► publisher task                │   │      │
│  │ │ one writer, one reader     ends with the TaskGroup       │   │      │
│  │ └──────────────────────────────────────────────────────────┘   │      │
│  │ await to_thread(render) ──► worker thread: arguments           │      │
│  │                             in, result out, no shared state    │      │
│  └────────────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────────────┘
```

`ownership.py --table` prints the same rules as a five-column table: state or task, owner, who may touch it, rule, and when it ends. The script's audit checks each row while the path runs. A rule you can check is worth more than a rule in a comment. The audit enforces the stats row with `LoopOnly`, at `ownership.py:86`. It is a dict whose `__setitem__` records a violation when the writing thread is not the loop's thread.

The same path is written twice. The owned version follows every row. The leaky version breaks each rule once, the way real code does. Its thread function updates the stats. Its cache checks and fetches with no lock. Its publisher starts with `create_task`. 200 requests on 2 keys:

```
owned  200 requests on 2 keys: cache fetches 2, stats {'requests': 200, 'render_calls': 200}
       violations: none
leaky  200 requests on 2 keys: cache fetches 200, stats {'requests': 200, 'render_calls': 200}
       violation x200  stats written from a worker thread   e.g. render_calls from asyncio_0
       violation x198  cache key fetched twice   e.g. k0: a second fetch finished after the first
       violation x200  task alive after its request returned   e.g. publisher
```

Read the leaky numbers against the rules:

1. **200 writes from a worker thread.** `render` ran in `asyncio_0`, a thread of the default pool, and wrote to state the loop owns. The counts still came out right in this run. That is luck. Section 4.1 showed that a `dict.get` update across threads can lose three quarters of its writes.
2. **200 fetches for 2 keys.** All 200 requests checked the cache before the first fetch returned, so each one fetched. The first fetch of each key is not a duplicate, so 200 − 2 = 198 duplicates. A cache stampede, many requests fetching the same missing key at once, is this logical race at scale.
3. **200 publishers alive when their request returned.** Nobody owned them. Each ended soon after, because the work sent its end marker. In part B, a cancel stops the work first, and the same line leaks one task per request.

**The answer to the question.** The counters need no lock while only the loop writes them, because no update suspends. The cache needs an `asyncio.Lock` per key around its fetch. The progress task needs an owner, the request's `TaskGroup`. The `to_thread` function needs no lock if it touches no shared state, so it returns its result and the request writes the counters.

**The sentence to remember:** write one owner for every piece of shared state and every task. The owner decides whether a lock is needed, and the owner makes sure each task ends.

**The trap:** state that the loop owns, written from code that runs in `asyncio.to_thread`. The function looks like any other, so nobody sees the thread boundary. The audit found 200 of 200 such writes in the leaky path, with counts that happened to be right.

**Try this now:** run `uv run python phase04_concurrency/ownership.py --variant leaky --requests 50 --keys 5`. Predict the fetches and the duplicate fetches first. The run gives 50 fetches and 45 duplicates, because 50 − 5 = 45.

---
## 4.4 — Locks, queues and asyncio primitives (which one, and the cost of the wrong one)

Why this matters: every fix in this part uses a primitive. Choose the wrong one and you trade a race for a hang, or for a path that is 75 to 96 times slower.

**Answer this first.** One coroutine holds a `threading.Lock` across `await asyncio.sleep(0.1)`. A second coroutine on the same loop calls `lock.acquire(timeout=0.5)`. How long does the second one wait? What happens to every other request on that loop meanwhile?

**Pick the primitive by the shape of the problem.** Each row names the failure you get when you choose wrong. The failures with numbers were measured in this phase.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Which primitive for which shape                                          │
│ shape                     use                wrong choice, measured      │
├──────────────────────────────────────────────────────────────────────────┤
│ counter or map written by threading.Lock     no lock: 69% to 76% of      │
│ several threads                              updates lost (4.1)          │
│ check, suspend, act on    asyncio.Lock per   one lock for all keys:      │
│ one key                   key                1,122 to 1,153 ms           │
│                                              against 13 to 15 ms         │
│ check and act can come    the reserve        no refund: the balance      │
│ before the suspension     pattern            stays low after a           │
│                                              failed write                │
│ state that one task owns  asyncio.Queue to   one owner for all           │
│                           an owner task      users: 1,138 to 1,158 ms    │
│ a one-time signal         asyncio.Event                                  │
│ at most N at a time       Semaphore or N     see 4.6                     │
│                           workers                                        │
│ a thread hands work to    loop.call_soon_    asyncio objects are not     │
│ the loop                  threadsafe         thread-safe: the docs       │
└──────────────────────────────────────────────────────────────────────────┘
```

The asyncio documentation warns: "asyncio primitives are not thread-safe, therefore they should not be used for OS thread synchronization (use threading for that)". The reverse mistake is worse, because it looks correct.

**WRONG: a threading.Lock held across an await.** This is `primitives.py:65`, shortened: the asyncio branches are left out, and the parameters are written as numbers:

```python
    async def holder() -> None:
        with tlock:                                # WRONG: a thread lock held across an await
            await asyncio.sleep(0.1)

    async def waiter() -> None:
        await asyncio.sleep(0)                     # let the holder take the lock first
        got = tlock.acquire(timeout=0.5)           # blocks the loop's only thread
```

```
threading lock held across an await: waiter got the lock: False  waited 0.507 s  holder finished at 0.507 s  loop blocked up to 504 ms
threading lock held across an await: waiter got the lock: False  waited 0.501 s  holder finished at 0.501 s  loop blocked up to 501 ms
threading lock held across an await: waiter got the lock: False  waited 0.510 s  holder finished at 0.510 s  loop blocked up to 508 ms
```

The waiter never got the lock. The holder was due to finish at 0.1 s and finished at 0.5 s. A separate task measured how long the loop stopped: 501 to 508 ms. Without the timeout, the process would hang until it is stopped.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ threading.Lock across an await, one loop thread. Rounded, from part P    │
├──────────────────────────────────────────────────────────────────────────┤
│ t = 0.000  holder takes the thread lock, awaits a 100 ms sleep           │
│ t = 0.000  waiter calls tlock.acquire(): the loop's only thread blocks   │
│ t = 0.100  the holder's sleep is due. The loop cannot run it:            │
│            its thread is inside acquire()                                │
│ t = 0.500  acquire() gives up and returns False                          │
│ t = 0.500  the loop runs again. The holder wakes 400 ms late             │
├──────────────────────────────────────────────────────────────────────────┤
│ every other task on this loop waited 501 to 508 ms                       │
│ without the timeout: nothing ever releases the lock. A hang              │
└──────────────────────────────────────────────────────────────────────────┘
```

**RIGHT: an asyncio.Lock.** The same two coroutines with `async with alock` and `await alock.acquire()`:

```
asyncio   lock held across an await: waiter got the lock: True   waited 0.101 s  holder finished at 0.101 s  loop blocked up to 1 ms
```

The waiter waited 100 ms, the length of the hold, and the loop stayed free. With `--mutate thread-lock` the self-test puts the thread lock back into this path and fails: `waiter got the lock: False  waited 0.502 s`.

**The scope of a lock decides the throughput.** A lock serialises what it covers: only one task runs inside it at a time. `primitives.py --part scope` gives 100 users one spend each. Each spend awaits a 10 ms ledger write.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 100 users, one spend each, 10 ms ledger write. 3 runs. Lab part P        │
├──────────────────────────────────────────────────────────────────────────┤
│ one lock for all users  ██████████████████████████████ 1,122 to 1,153 ms │
│ one owner task for all  ██████████████████████████████ 1,138 to 1,158 ms │
│ one lock per user       █                              13 to 15 ms       │
│ the reserve pattern     █                              12 to 14 ms       │
├──────────────────────────────────────────────────────────────────────────┤
│ one at a time: 100 writes x 10 ms = 1,000 ms, plus overhead              │
│ together: one 10 ms write, plus overhead. 75 to 96 times faster          │
└──────────────────────────────────────────────────────────────────────────┘
```

A single owner task is a lock in another form. It also runs one request at a time. The owner pattern needs one owner per key, or it serialises every user.

**Two details from the source.** `Lib/asyncio/locks.py` at v3.13.3 takes a free lock with no waiters without suspending. So `async with lock:` on a free lock is not a suspension point. And the documentation says "Acquiring a lock is fair": the task that waited first gets it next.

**The reserve pattern has a cost too.** A second request sees the reserved amount as spent. With the failing ledger, reserve refused the second spend, `['LedgerDown', False]`, while the lock let it try, `['LedgerDown', 'LedgerDown']`. Reserve can refuse a request that would succeed a moment later. If that matters, use the lock per key.

**The sentence to remember:** choose the primitive by the shape. Threads need a `threading.Lock`. A suspension between check and act needs an `asyncio.Lock` per key, the reserve pattern, or one owner per key. Keep the locked region as small as the rule allows.

**The trap:** a `threading.Lock` held across an await. On one loop it blocks the thread that must release it. The waiter timed out after 0.5 s, and every task on the loop stopped for 501 to 508 ms. Without a timeout it never returns.

**Try this now:** run `uv run python phase04_concurrency/primitives.py --part scope --users 20 --ledger-ms 50 --repeat 1`. Predict first. One lock for 20 users is about 20 × 50 ms = 1,000 ms. One lock per user is about 50 ms. The run gave 1,037 ms for the single lock and 50 ms per user.

---
## 🧪 Hands-on lab — part A

**Run status:** every command below was executed on 2026-09-25 on an Apple M2 with 8 GB, macOS 15.7.8 and CPython 3.13.3 through uv. Each "Expected" line is copied from the logs in `runs/lab4-*.log`. Lost-update counts and timings will differ on your machine. Every pass, fail and count of tasks or fetches should not.

All commands run from `elite-performance/code/`. `bash runs/lab4.sh G R P O X` runs every part of this lab and saves each log.

- [ ] **E1 (offline).** Where a thread can be switched out.
  - Run: `uv run python phase04_concurrency/gil_counter.py --dis`, then `uv run python phase04_concurrency/gil_counter.py --modes plain call len abs dict`.
  - Before the second command, predict which bodies lose updates from the switch points the first one prints.
  - Expected: `plain` and `len` lose `0, 0, 0` at both intervals. At `1e-06`, `call` loses `1,129,458, 1,163,637, 1,105,080`, and `dict` loses `1,192,717, 1,221,035, 1,183,562`. The command takes about 20 s and loads every core.
  - If `plain` loses updates: check `python --version`. CPython 3.9 and older lose them, as section 4.1 says.
  - Teaches: the GIL decides where a thread can be switched out, not what is atomic.

- [ ] **E2 (break-it, offline).** Remove the lock and watch the self-test fail.
  - Run: `uv run python phase04_concurrency/gil_counter.py --self-test --mutate no-lock`.
  - Expected: `[FAIL] lock loses nothing: lost [591013, 574246]` and `self-test FAILED`, with exit code 1. The self-test uses 8 threads of 100,000, so the total is 800,000.
  - Then run it without `--mutate`. Expected: `self-test passed`.
  - Teaches: a mutation check removes one rule on purpose. If the test still passes, it never tested that rule.

- [ ] **E3 (offline).** Check-then-act across a real suspension.
  - Run: `uv run python phase04_concurrency/wallet.py`.
  - Before you run it, mark which of the 16 rows you expect to end below zero.
  - Expected: only `racy sleep0` and `racy sleep` end at `-60`. `racy nosuspend` ends at `20`. Every `lock`, `reserve` and `owner` row ends at `20`, or `100` with the failing ledger.
  - Teaches: an await that suspends is where another task can change what you checked. An await that does not suspend hands over nothing.

- [ ] **E4 (offline).** What the linters see, and what they miss.
  - Run: `bash runs/lab4.sh X`. The first run downloads ruff 0.16.9 and flake8-async 26.8.1 into uv's cache.
  - Expected: ruff reports `RUF006` at `leaks.py:195`, `E722` at `cancel.py:72`, `ASYNC251`, and two `BLE001`, neither of them the race. flake8-async reports `ASYNC103` at `cancel.py:72` and `cancel.py:121`, `ASYNC251` and `ASYNC300`.
  - Now look for `wallet.py:146`, the racy check-then-act. Neither tool reports it. Nor does either report `ownership.py:149`, a `loop.create_task` with no owner.
  - Teaches: linters find patterns. No standard tool finds a logical race.

- [ ] **E5 (offline, written).** An ownership table for a path you own.
  - Run: `uv run python phase04_concurrency/ownership.py`.
  - Expected: `owned ... cache fetches 2 ... violations: none`, and for `leaky`: `violation x200  stats written from a worker thread`, `violation x198  cache key fetched twice`, `violation x200  task alive after its request returned`.
  - Then pick one request path in a service you own. Write the five columns of `ownership.py --table` for it: each piece of shared state, each task, and each thread call. For each row with no clear owner, name the incident it could cause.
  - Teaches: a rule that is written down can be checked. A rule that is not written down cannot.

- [ ] **E6 (break-it, offline).** The wrong lock stops the loop.
  - Run: `uv run python phase04_concurrency/primitives.py --part kind --repeat 3`.
  - Expected: three `threading` lines with `waiter got the lock: False` and `loop blocked up to` 501 to 508 ms, and three `asyncio` lines with `waited 0.100` or `0.101 s` and `loop blocked up to` 1 or 2 ms.
  - Then run `uv run python phase04_concurrency/primitives.py --self-test --mutate thread-lock`. Expected: `[FAIL] asyncio.Lock: waiter gets it after the 0.1 s hold`.
  - Teaches: a thread lock across an await blocks the only thread that could release it.

---

## 🔍 Check it yourself

1. Open `phase04_concurrency/gil_counter.py:140`. This is `_NO_CHECK_CALLS`. Which call instructions are not switch points, and why does the `len` body lose nothing while `abs` loses about three quarters? What would you expect from `isinstance(x, int)` inside an update?

2. Open `phase04_concurrency/wallet.py:153`. This is `_reserve`. It catches `BaseException`, not `Exception`, before it refunds. Which exception would `except Exception` miss at that await, and what would the balance be after it? Part B's section 4.5 gives the answer.

3. Open `phase04_concurrency/ownership.py:111`. This is `Cache.get`. The owned variant holds the key's lock across the fetch. What does a second request for the same key do while the first one fetches? How many fetches happen for 200 requests on 2 keys?

4. In any repository you own that uses threads, run:

   ```bash
   grep -rnE "self\.\w+ \+= |\[[^]]+\] = [^=]*\.get\(" --include='*.py' <your repo>/
   ```

   For every match, name the thread or task that owns that state. For every match with more than one writer, name the lock that protects it, or write the test that shows the loss.

---

## ✅ Checkpoint 4A — answer in your own words

1. **Explain, with an example of each.** A colleague says: "Python has the GIL. So we have no data races, so our cache is safe." (a) Which half of the sentence is true? (b) Give one logical race in pure Python with threads and one with asyncio, and name the happens-before order each one lacks.

2. **Predict.** A metrics class does `self.hits[route] = self.hits.get(route, 0) + 1` from 8 worker threads on CPython 3.13. A unit test runs 8 threads × 100,000 calls and asserts the total. (a) Will the test pass? (b) The same test on a line `self.total += 1` passes. What does that prove about the class? (c) What changes on a free-threaded build?

3. **This is broken.** A payments service had no double-spend bug for a year. Last week someone added `await audit.log(event)` inside `check_limit()`, which runs between the balance check and the debit. `audit.log` used to be a no-op `async def`. Now it writes to Kafka. Double spends appear in production, and every test still passes. The tests use `AsyncMock` for the audit client. What is the cause, why do the tests pass, and how do you check it?

4. **Show the arithmetic.** A wallet holds 100 credits. Three concurrent racy spends of 40 each run with a ledger that suspends. (a) What is the final balance if all three checks happen before any act? (b) With an `asyncio.Lock` per user, how many spends succeed, and what is the final balance? (c) With the reserve pattern and a ledger that fails for the first spend only, what are the three results?

5. **Given these constraints, design.** A rate limiter keeps a token count per API key. Requests are handled by asyncio tasks. Every 100 ms a thread started by a C library calls back into Python to add tokens. Write the ownership table: the state, its owner, who may write it, the rule, and the primitive. Say what goes wrong if the thread writes the dict directly.

6. **A colleague says:** "Wrap the whole handler in one `asyncio.Lock` and every race is gone." Argue for or against, with numbers from section 4.4.

<details>
<summary>Answer sketches</summary>

1. (a) The first half is true for pure Python code. Under the GIL the interpreter's C code is serialised, so there is no data race in the machine sense. That is inferred from how the GIL and ThreadSanitizer work, and C extensions that release the GIL are outside it. The conclusion is false, because logical races remain. (b) Threads: `stats[k] = stats.get(k, 0) + 1` from 8 threads lost 1,183,562 to 1,221,035 of 1.6 million updates, because nothing orders one thread's load before another's store. asyncio: the check-then-act in `_racy`. T1's check has no happens-before relation to T0's act, so T1 can check before T0 acts.

2. (a) It fails. `dict.get` is a call, and its specialised instruction checks for a switch between the load and the store. The dict mode lost 74% to 76% at a 1 µs interval, and 652,934 to 1,054,194 of 1.6 million at the default interval. (b) Nothing. `self.total += 1` has no call between its load and its store on 3.11 to 3.14, so it cannot show the loss. It says nothing about the `hits` line. (c) Threads run at the same time, and PEP 703 says per-object locks do not make the update atomic. So both lines need a lock. This is from PEP 703, not a run.

3. The cause is a new suspension point between check and debit. The no-op `audit.log` never suspended, so the check-then-act ran without a switch, although nobody planned it. Kafka I/O suspends, so another request now runs between the check and the debit. The tests pass because `AsyncMock` never suspends, as the `nosuspend` ledger did in section 4.2. Check: replace the mock with a fake that awaits `asyncio.sleep(0)`, or with a gate, and run two spends at once. Fix: an `asyncio.Lock` per account around check, log and debit, or debit first and refund on failure.

4. (a) 100 − 3 × 40 = −20. (b) Two succeed: 100 → 60 → 20. The third checks 20 ≥ 40 and refuses. The balance is 20. (c) The first spend reserves 40, so the balance is 60. The second reserves 40, so it is 20. Both await the ledger. The third checks 20 < 40 and refuses at once. The first ledger write fails and refunds 40, so the balance is 60. Results: `LedgerDown`, `True`, `False`, and a balance of 60. The third request was refused although 60 credits are there now. That is the reserve trade-off from section 4.4.

5. State: `tokens[key]`. Owner: the event loop thread. The C thread never writes it. It calls `loop.call_soon_threadsafe(refill, key, n)`, so every write runs on the loop. Rule: take a token with no await between the check and the decrement, so no lock is needed. If the thread wrote the dict directly, its `get` and store could interleave with a request's update. Section 4.1 measured that shape losing about three quarters of its updates.

6. Against, for most services. One lock for all keys runs every request one at a time. For 100 users with a 10 ms write it took 1,122 to 1,153 ms, against 13 to 15 ms with a lock per user: 75 to 96 times slower. It also hides the ownership question. For a single-user tool where throughput does not matter, it is a valid fix.

</details>

---

## References & Further Learning — part A

Every URL below was fetched on 2026-09-25 and returned HTTP 200. Source files are cited at a tag.

**The GIL and where a thread switches**

- **Python FAQ, "What kinds of global value mutation are thread-safe?"** — https://docs.python.org/3/faq/library.html
  Focus on: the operations that "look atomic", and those that are not, such as `i = i+1`.
- **CPython pull request GH-18334, "Only check evalbreaker after calls and on backwards egdes"** — https://github.com/python/cpython/pull/18334
  Focus on: the description. This change, shipped in 3.10, removed the switch points inside `counter += 1`. The typo is in the original title.
- **CPython `Python/bytecodes.c` at v3.13.3** — https://raw.githubusercontent.com/python/cpython/v3.13.3/Python/bytecodes.c
  Focus on: `CHECK_EVAL_BREAKER` in `RESUME` and `JUMP_BACKWARD`, and `_CHECK_PERIODIC` after calls into C. `CALL_PY_EXACT_ARGS` has none: it pushes a frame, and the callee's `RESUME` checks. Read it beside E1's `--dis` output.
- **`sys.setswitchinterval`, Python 3.13 docs** — https://docs.python.org/3.13/library/sys.html
  Focus on: `setswitchinterval`: how often a switch is requested, not where.
- **PEP 703, "Making the Global Interpreter Lock Optional in CPython"** — https://peps.python.org/pep-0703/
  Focus on: the section "Container Thread-Safety". Per-object locks keep containers intact and give no atomicity for operations. PEP 779, https://peps.python.org/pep-0779/ , made the free-threaded build supported in 3.14.
- **"Thread Safety Guarantees", Python 3.14 docs** — https://docs.python.org/3/builtins/threadsafety.html
  Focus on: the dict section, and its check-then-act example with the fix `d.pop(key, None)`.

**asyncio: suspension, primitives and tools**

- **"Developing with asyncio", Python 3.13 docs** — https://docs.python.org/3.13/library/asyncio-dev.html
  Focus on: "Concurrency and Multithreading", and "Debug Mode", whose list of reports has no race on it.
- **"Synchronization Primitives", Python 3.13 docs** — https://docs.python.org/3.13/library/asyncio-sync.html
  Focus on: the warning that asyncio primitives are not thread-safe, and the fairness note under `Lock`.
- **CPython `Lib/asyncio/locks.py` at v3.13.3** — https://raw.githubusercontent.com/python/cpython/v3.13.3/Lib/asyncio/locks.py
  Focus on: `Lock.acquire`. A free lock with no waiters is taken without suspending.
- **Ruff rule RUF006, asyncio-dangling-task** — https://docs.astral.sh/ruff/rules/asyncio-dangling-task/
  Focus on: what it checks. E4 shows it missing a `loop.create_task` in `ownership.py`.
- **flake8-async rules** — https://flake8-async.readthedocs.io/en/latest/rules.html
  Focus on: ASYNC103 and ASYNC104, the rules that catch a swallowed cancel. Ruff 0.16.9 has neither. Part B uses them.
- **Quansight Labs, free-threading guide, "ThreadSanitizer"** — https://py-free-threading.github.io/thread_sanitizer/
  Focus on: the first section. TSan finds data races in low-level code, not logic errors.

**Ownership**

- **Nathaniel J. Smith, "Notes on structured concurrency, or: Go statement considered harmful", 2018** — https://vorpus.org/blog/notes-on-structured-concurrency-or-go-statement-considered-harmful/
  Focus on: the nursery section. It is the design behind `asyncio.TaskGroup`. A blog post, not peer reviewed.
- **"Coroutines and Tasks", Python 3.13 docs** — https://docs.python.org/3.13/library/asyncio-task.html
  Focus on: `TaskGroup`, and the "Important" box under `create_task` about keeping a reference. Part B relies on both.
- **Vince, "Finding memory leaks in Python", 2023** — https://vince.id/posts/finding-memory-leaks-in-python/
  Focus on: the graph over 11 hours, and the one `create_task` without `add_done_callback`. One engineer's post.

---

## Cheatsheet — part A

```
THE GIL (CPython 3.11 to 3.14 measured, GIL build)
  promise          switches only BETWEEN instructions
  switch points    RESUME at a function start, loop jump back, most C calls
                   (CALL_LEN: none; CALL_BUILTIN_O, dict.get: yes)
  8 x 200,000      counter += 1: 0 lost. += one(): 1.11 to 1.16 million
                   stats[k] = stats.get(k, 0) + 1: 1.18 to 1.22 million
                   (1 us interval. At the default 5 ms: 40% to 66% lost)
  free-threaded    per-object locks, still no atomic read-modify-write
  rule             shared read-modify-write: a lock, or one owner

RACES
  data race        two threads, one memory word, one writes: TSan finds it
  logical race     order-dependent result: no standard tool finds it
  asyncio          runs uninterrupted between two REAL suspensions
  hides it         AsyncMock, or any async fake with no await inside
  happens-before   same task: line order. lock: release -> next acquire
                   queue: put -> the get that returns it

OWNERSHIP
  immutable        nothing
  one thread, no suspension inside the update     nothing
  suspension between check and act   asyncio.Lock per key, the reserve
                                     pattern, or one owner per key
  more than one thread               threading.Lock, or call_soon_threadsafe
  every task       an owner that waits for it or cancels it: TaskGroup

PRIMITIVES
  threading.Lock across an await   blocks the loop: 501 to 508 ms here
  one lock for 100 users           1,122 to 1,153 ms against 13 to 15 ms
  free asyncio.Lock                taken without suspending. Fair
  asyncio objects                  not thread-safe
```

Part B covers the lifetimes of tasks and how to test the order, in sections 4.5 to 4.8. It has the 10,000 cancelled requests, and the test that fails the same way every run.

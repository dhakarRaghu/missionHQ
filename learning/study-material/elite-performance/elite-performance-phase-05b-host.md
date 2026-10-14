# Phase 5B — The machine beneath an API request: the host

**The question this phase answers:** where do the 40 milliseconds go between a client's request and the first byte of the response? And which of them are yours?

Part A followed a request onto the wire: DNS, TCP, TLS and the HTTP version. Part A is a prerequisite: this part uses its tools, `server.py`, `netem.py` and the timeline, without explaining them again.

This part follows the request into the host: the pool, the disk, the deadline and the CPU quota. It completes four of the five ideas of Phase 5. Idea 3, on HTTP/2, is done in part A.

- **Idea 1. The first request on a new connection pays DNS, TCP and TLS round trips before the request itself**. A warm pool pays none of them. So the pool's size and its keep-alive limits decide how often you pay.
- **Idea 2. Python's network calls wait where no single timeout looks**. asyncio runs the blocking `getaddrinfo` in its default thread pool, which other blocking work shares. Each httpx timeout starts again at every step. So only a deadline set above the call bounds the total, and the server is not told when it passes.
- **Idea 4. A read from the page cache costs about 2 µs**. A read from a local SSD costs tens to hundreds of microseconds, and one from a network disk milliseconds. The code is the same, so what is cached decides.
- **Idea 5. A CPU quota is enforced per period**. A container that spends its quota early waits for the rest of the period. That adds up to the period minus the quota to a request: 50 ms for `--cpus=0.5` at the default 100 ms period. So the p50 stays, and the p99 rises.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, the previous document: the wire                                  │
│  5.1  DNS   5.2  TCP   5.3  TLS   5.4  HTTP/1.1, HTTP/2, gRPC            │
│                                                                          │
│ PART B, this document: the host                          ideas           │
│  5.5  Connection pools done right    — Little's law, idle limits   1     │
│  5.6  Syscalls, buffers, page cache  — memory against the SSD      4     │
│  5.7  Deadlines through the stack    — per-step against total      2     │
│  5.8  The container's limits         — the quota and its period    5     │
│  Lab: E7 to E12. The demonstration: one fault, named from metrics        │
└──────────────────────────────────────────────────────────────────────────┘
```

**What this part assumes.** Part A's list holds, plus two sections that verified mechanisms used here.

- **Phase 2, section 2.3, "Pools that fill".** A pool of c connections is a queue with c servers. Erlang C predicts how often a request waits for one. That section also read httpcore 1.0.9 and measured the result. When a connection frees, the pool hands it to every waiting request in the same pass. One wins, and the others go round the pool again. This part measures what that costs a client.
- **Phase 4, section 4.5, "Cancellation and deadlines".** In asyncio, cancelling a task raises `CancelledError` at its next await. That section also verified, from uvicorn 0.53.0's `h11_impl.py` and a live run, that a client disconnect does not cancel the handler. The handler kept running after the client left. Section 5.7 follows the same cancellation across the network.

**The Phase 1 commitment this part pays.** Section 1.3 listed the OS page cache as cold state and said "Phase 5 measures it". Section 5.6 measures a page-cache hit against an SSD read on this laptop. It also says what cannot be measured without `sudo`: a read after a reboot.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. Section 5.8's container run needs Docker Desktop. The log records Docker Desktop 4.38.0 with engine 27.5.1 and a Linux kernel 6.12.5 in its VM, with 8 CPUs and about 4 GB. The run pulls the official `python:3.13-slim` image once, 43,316,407 bytes unpacked. Everything else is as in part A, measured on 2026-09-25. The load average at the start of each log was 2.4 to 5.9.

Time for part B: 1.5 to 2 hours. About 6 minutes of that is waiting for runs, plus the Docker start.

---
## 5.5 — Connection pools done right (sizing from Little's law, and the cost inside the pool)

Why this matters: a pool with too few connections makes requests wait, and the server never sees that wait. A pool that closes idle connections too early pays the handshakes again. And the client library's pool has its own cost.

**Answer this first.** This is the phase's Test-out, the question the course outline uses to test the phase. A pool of 10 connections serves 200 requests that arrive at once. Each request holds its connection for 20 ms. Predict the mean latency and the slowest request. Then 200 clients send requests in a closed loop through the same pool. Predict the throughput and the mean latency.

**The model.** An HTTP/1.1 connection carries one request at a time. So a pool of c connections has at most c requests in service. Little's law, L = λW, holds for any boundary you draw. L is the number inside it, λ the rate through it, and W the time each request spends inside. The Netflix concurrency-limits README states it for limits: "Limit = Average RPS * Average Latency".

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 200 requests at once, pool of 10, 20 ms each. The prediction             │
├──────────────────────────────────────────────────────────────────────────┤
│ time  0     20    40    60   ...   380   400 ms                          │
│ wave  [ 1 ][ 2 ][ 3 ][ 4 ]   ...  [ 20 ]                                 │
│       10    10    10    10         10    requests finish per wave        │
│                                                                          │
│ mean  = 20 × (1 + 2 + ... + 20) / 20 = 20 × 10.5 = 210 ms                │
│ max   = 20 × 20 = 400 ms          a pool of 200: one wave, 20 ms         │
│                                                                          │
│ closed loop, 200 clients. Little's law, two boundaries:                  │
│  around the connections:  10 = λ × 20 ms   →  λ = 500 per second         │
│  around the whole client: 200 = 500/s × W  →  W = 400 ms                 │
└──────────────────────────────────────────────────────────────────────────┘
```

**The measurement.** `pool_size.py` prints the prediction, then measures four bursts and one closed loop against `server.py`. The lean pool is `RawPool` from Phase 1's `loadgen.py`. Its cost per request does not grow with its line. Then httpx with a pool of 10, and httpx with a semaphore of 10 in front of it. Three runs, from `runs/lab5-pool.log`:

```bash
uv run python phase05_machine/pool_size.py --repeat 3 --duration 5
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 200 at once, pool of 10, 20 ms. Mean latency, median of 3 runs           │
├──────────────────────────────────────────────────────────────────────────┤
│ predicted            ███████████                              210 ms     │
│ lean pool            ████████████▌                            243 ms     │
│ httpx + semaphore    █████████████▌                           263 ms     │
│ httpx pool alone     ████████████████████                     391 ms     │
│ lean pool of 200     █▌                                      25.5 ms     │
│                                                                          │
│ slowest request: predicted 400, lean 464 to 472, httpx 697 to 713 ms     │
└──────────────────────────────────────────────────────────────────────────┘
```

The lean pool's median run was 243 ms, 16% above the model. Its slowest request in run 1, 464.2 ms, means each wave took 23.2 ms instead of 20. The sustained loop measured 426 to 434 requests per second, 13 to 15% under the predicted 500. Its mean was 441 to 451 ms, 10 to 13% over 400. Little's law around the connections gives the reason: 10 connections at 430 per second means each request held its connection 23.3 ms, not 20. That extra time is the client's own work per request, as in the burst. Around the whole client, rate × W gave 191.7 to 191.8 in the system. That is a little under 200, because the last requests drain at the end of a run.

**The pool wait is the metric.** The server's `Server-Timing` header gave a median of 20.2 to 20.3 ms in every httpx run. So the server's dashboard shows a healthy 20 ms, and the client sees more than ten times that:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One request of the burst, lean pool, run 1. Means                        │
├──────────────────────────────────────────────────────────────────────────┤
│ client: ├──────── pool wait 219.6 ms ───────┤├─ 20 ms ─┤├3.2┤ 242.8 ms   │
│ server:                                      ├─ 20 ms ─┤   "healthy"     │
│                                                                          │
│ 3.2 ms is the client's own time. httpx has no pool metric: measure the   │
│ time from the call to the first connect_tcp or send_request_headers      │
└──────────────────────────────────────────────────────────────────────────┘
```

**The cost inside httpx's pool.** With 200 requests queued inside its pool, httpx had a mean of 387.1 to 398.5 ms. That is 1.8 to 1.9 times the model. The same runs counted how often httpcore raised `ConnectionNotAvailable` and sent a request round the pool again: 2,101 to 2,153 times for 200 requests. The client used 649 to 665 ms of CPU on those 200 requests. Phase 2, section 2.3, verified the mechanism in httpcore 1.0.9: one free connection is handed to every waiting request in the same pass.

**WRONG: let a burst queue inside the client library's pool.**

```python
# WRONG: 200 requests wait inside httpcore's pool of 10
async with httpx.AsyncClient(limits=httpx.Limits(max_connections=10)) as c:
    await asyncio.gather(*(c.get("/delay?ms=20") for _ in range(200)))
```

```
  httpx pool 10, burst   mean  390.5  p50  411.9  p99  705.6  max  713.2 ms | pool wait mean  363.1  max  691.8 ms | pool retries 2101, client CPU  660 ms, server p50 20.2 ms
```

**RIGHT: queue in front of the pool, in a line that costs the same however long it is.** From `pool_size.py:124`, `burst_httpx` with `gate=True`, shortened:

```python
# RIGHT: at most 10 requests enter the pool; the rest wait in a cheap FIFO
sem = asyncio.Semaphore(10)
async def one():
    async with sem:
        return await c.get("/delay?ms=20")
```

```
  httpx + semaphore 10   mean  265.1  p50  272.7  p99  506.5  max  507.7 ms | pool wait mean  242.5  max  485.9 ms | pool retries  172, client CPU  240 ms, server p50 20.2 ms
```

In run 1 the semaphore cut the mean by 32% and the pool retries by 92%. It is still above the lean pool. The semaphore is also where to measure the wait and to shed load. The p99 of a burst of 200 rests on 2 requests, so read the means and the maxima here.

**Idle limits.** httpx's default `Limits` keep at most 20 idle connections, `max_keepalive_connections=20` in `httpx/_config.py` at 0.28.1. It closes one after 5 s idle. `pool_size.py --churn` sends bursts of 50 requests of 200 ms, one second apart, over TLS:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Bursts of 50, 1 s apart, over TLS. New TLS handshakes per burst          │
├──────────────────────────────────────────────────────────────────────────┤
│ httpx default, max 100, keep 20                                          │
│   burst 1  49 ████████████████████████████████████████████████▌          │
│   bursts 2 to 5: 30 each   ██████████████████████████████                │
│ max 50, keep 50                                                          │
│   burst 1  49 ████████████████████████████████████████████████▌          │
│   bursts 2 to 5:  0, 0, 5, 17                                            │
└──────────────────────────────────────────────────────────────────────────┘
```

With the defaults, every burst after the first opened 50 − 20 = 30 new TLS connections. Part A priced each one: a round trip or two, and about 0.6 ms of server CPU. Keeping 50 idle connections stopped most of the handshakes. It did not make the bursts faster on this version. Those bursts took 508 to 762 ms against 364 to 369 ms with the defaults, and counted 292 to 350 pool retries each. Fifty requests that start at once on fifty idle connections collide in the pool, by the mechanism above. There is one more detail in httpcore 1.0.9. Its idle check counts every connection in the pool, busy or idle, against `max_keepalive_connections`. That is inferred from `_assign_requests_to_connections`, not traced. Measure your own client before you raise a limit.

One more rule: the client's `keepalive_expiry` must stay below the idle timeout of the server and of any load balancer. Otherwise the client reuses a connection the other side just closed.

**The sentence to remember:** size a pool with Little's law, busy connections = rate × hold time. Then measure the pool wait from the client. The server never sees it.

**The trap:** trusting the server's latency to size the client. The server said 20 ms. The client's mean was 243 ms with a lean pool, 391 ms with httpx's.

**Try this now:** run `uv run python phase05_machine/pool_size.py --pool 20 --repeat 1`. Predict the burst first: 10 waves, a mean of 110 ms, a slowest request of 200 ms.

---
## 5.6 — Syscalls, buffers and the page cache (what a read costs from memory and from the device)

Why this matters: the same `read()` costs about 2 µs or about 90 µs, and milliseconds on a network disk. Nothing in the code tells you which. A service can slow down only because its working set no longer fits in memory.

**Answer this first.** A service reads random 4 KiB records from a 256 MiB file on the laptop's internal SSD. How much slower is a read of a page that is not in memory than one that is: 2 times, 10 times, or 50 times? And how long does `os.fsync` take after a 4 KiB write on a Mac, compared with `fcntl(F_FULLFSYNC)`?

**The layers under one read.** A syscall is a call from your process into the kernel. The page cache is the kernel's copy of recently used file pages in memory. It holds whole pages, and on Apple silicon a page is 16 KiB: `os.sysconf("SC_PAGE_SIZE")` prints 16384 on this M2. A read that finds its page there is a memory copy. A read that does not waits for the device, and brings the whole page in:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ os.pread(fd, 4096, offset) on this M2: where the time goes               │
├──────────────────────────────────────────────────────────────────────────┤
│  Python ──► syscall ──► page cache ──hit──► copy 4 KiB ──► return        │
│  0.23-0.25 µs per trivial call      │         about 1.5 µs in total      │
│                                     miss                                 │
│                                     ▼                                    │
│             device: local SSD ─── about 90 µs, and the 16 KiB page       │
│                                   around the 4 KiB now sits in memory    │
│                     network disk ─ "single-digit millisecond", AWS gp3,  │
│                                    not measured here                     │
└──────────────────────────────────────────────────────────────────────────┘
```

**Getting a miss without root.** `sudo purge` empties the cache on macOS, and this course does not use sudo. So `pagecache.py:78`, `write_file`, writes a new file with `F_NOCACHE` set on the writing descriptor. That flag tells macOS not to keep those pages. It ends with `F_FULLFSYNC`, so the data is on the device. Then the script reads 2,000 random offsets through a normal descriptor, the miss pass, and the same offsets again, the hit pass. Each offset sits in a different 16 KiB page. `offsets`, at `pagecache.py:96`, draws them:

```python
# from pagecache.py:96, docstring removed, one comment added: one offset per 16 KiB page
    rng = stream("pagecache", seed)
    units = size_mb * CHUNK // unit              # unit = VM_PAGE, 16,384 here
    chosen: list[int] = []
    seen = {o // unit for o in (skip or ())}
    while len(chosen) < n:
        o = rng.randrange(units) * unit
        if o // unit not in seen:
            seen.add(o // unit)
            chosen.append(o)
```

**What the first version got wrong.** It drew distinct 4 KiB offsets. On a 16 KiB page system, some of them shared a page with an earlier offset. The first read of that page brought the neighbour in, so the later "miss" was a hit. `--offset-unit 4k` brings that version back. The count of shared pages and the count of fast "misses" were the same in all three runs: 106, 86 and 90 of 2,000. With one offset per page, the fast misses fell to 0 of 2,000 in every run. Three runs of the fixed version, from `runs/lab5-disk.log`:

```bash
uv run python phase05_machine/pagecache.py --repeat 3 --fsync 20 --syscall --buffers
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Random 4 KiB reads, 256 MiB file, internal SSD of an M2. Median of each  │
│ run, log scale: each step right is 10 times longer                       │
├──────────────────────────────────────────────────────────────────────────┤
│              0.1 µs     1 µs      10 µs     100 µs     1 ms     10 ms    │
│ getppid()      ███                                   0.23 to 0.25 µs     │
│ cache hit      ██████████                            1.5 µs              │
│ SSD, miss      ████████████████████████████████      88.7 to 89.8 µs     │
│ F_FULLFSYNC    ████████████████████████████████████████████ 2.9 ms       │
│                                                                          │
│ miss / hit: 61x, 58x, 62x.  miss p99: 115.2 to 457.0 µs                  │
└──────────────────────────────────────────────────────────────────────────┘
```

So a page-cache hit took 1.5 µs and an SSD read 88.7 to 89.8 µs at the median, 58 to 62 times longer. The research for this phase measured 88 µs and about 1 µs on the same laptop. The direct pass agrees: new offsets through a descriptor with `F_NOCACHE` took 86.6 to 91.9 µs.

**Whether a page stays cached is not your decision.** A 64 MiB file written normally stayed cached. Its "miss" pass had a median of 1.5 to 1.7 µs, and 500 of 500 reads were under 10 µs. A 256 MiB file written normally did not fully stay on this 8 GB laptop. Only 862 of its 2,000 first reads were under 10 µs, and the median was 84.0 µs. Memory pressure decided, not the code.

**A correction.** The course outline first said a disk read "costs milliseconds". That holds for network block storage: AWS says gp3 volumes provide "single-digit millisecond latency". It is wrong for a local SSD, about 90 µs here.

**Buffers.** A syscall costs 0.23 to 0.25 µs here, `os.getppid()` with the loop's own cost removed. A cached 4 KiB `os.pread` took 0.91 to 1.01 µs. So many small reads should not each be a syscall. Python's buffered reader fills a buffer with one read and serves the next records from memory. `open()` sizes that buffer from the file's `st_blksize`, 4,096 bytes on this APFS volume. The Python docs for `open` describe the rule. The same 1 MiB cached file, read in 100-byte records:

```
1 MiB cached file in 100-byte records: buffered 0.093 us per record (about 256 read syscalls of 4096 bytes), unbuffered 0.857 us per record (10486 syscalls); 9.2x
```

Three runs gave 8.5 to 9.2 times. The syscall counts are computed from the sizes, because tracing syscalls on macOS needs root.

**fsync on a Mac.** `os.fsync` in CPython 3.13 calls the plain `fsync()` system call, `Modules/posixmodule.c` at v3.13.0. Apple's `fsync(2)` man page says `fsync()` hands the data to the drive, and the drive may write it to permanent storage later. It adds: "This is not a theoretical edge case." `F_FULLFSYNC` also asks the drive to flush its own cache:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ A 4 KiB write, then a sync. 20 of each, alternated. p50 per run          │
├──────────────────────────────────────────────────────────────────────────┤
│  write ──► page cache ──fsync──► drive's cache ──F_FULLFSYNC──► flash    │
│                                                                          │
│  os.fsync      95 to 110 µs      returns when the drive has the data     │
│  F_FULLFSYNC   2.85 to 2.88 ms   returns when the drive flushed it       │
│  ratio         30x, 26x, 30x     F_FULLFSYNC max 7.8 to 9.6 ms           │
└──────────────────────────────────────────────────────────────────────────┘
```

So a benchmark of a log writer on a Mac measures a different guarantee from the same code on Linux. What each call promises is left for a later course. Here the lesson is the cost: a durable write costs milliseconds, and `os.fsync` hides that.

**What cannot be measured here without sudo.** The first read of a file after a reboot, and a file that other programs cached. `sudo purge` would give both.

**The sentence to remember:** a read costs about 2 µs from the page cache, about 90 µs from this SSD, and milliseconds from a network disk. Memory decides what is cached.

**The trap:** a storage benchmark that reads the same pages twice, or neighbours in one cache page. The second read comes from memory. Here the first version counted 86 to 106 such reads as misses. A repeat of the same offsets went from about 89 µs to 1.5 µs.

**Try this now:** run `uv run python phase05_machine/pagecache.py --offset-unit 4k --reads 2000`. Predict it first: the line "offsets sharing a 16,384-byte cache page" and the line "miss reads under 10 us" give the same number.

---
## 5.7 — Deadlines through the stack (per-step timeouts, a total deadline, and the server)

Why this matters: a timeout you set in httpx does not bound the request. Giving up on the client does not stop the work on the server. Both surprise people in production.

**Answer this first.** A client sets `httpx.Timeout(2.0)`. The server sends a 10-byte response, one byte every 0.8 s. When does the client raise an error: at 2 s, at 5 s, or never? And after the client gives up at 0.5 s on a 2 s job, how much of the job does a uvicorn handler still do?

**httpx's four timeouts are per step.** httpx has `connect`, `read`, `write` and `pool` timeouts, from `httpx/_config.py` at 0.28.1. A single number sets all four. The docs describe the default as a timeout "after 5 seconds of network inactivity". Inactivity is the word that matters. The read timeout covers the wait for one chunk. Each chunk starts it again:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 10 bytes, one every 0.8 s. httpx.Timeout(2) against asyncio.timeout(2)   │
├──────────────────────────────────────────────────────────────────────────┤
│ t (s)   0    0.8   1.6   2.0  2.4   3.2  ...  7.2   8.0                  │
│ bytes        x     x          x     x    ...  x     x                    │
│                                                                          │
│ read timeout, per chunk:  each wait is 0.8 s < 2 s   → no error, 8.07 s  │
│ asyncio.timeout, total:       ──────────►│ cancel  → TimeoutError 2.00 s │
└──────────────────────────────────────────────────────────────────────────┘
```

Inference-internals 5.1 named three timeouts: connect, stall and total. httpx's `connect` is the first. Its `read` is the stall timeout. httpx has no total. You add it above the call.

**WRONG: read a per-step timeout as a total one.** The pattern of `deadline.py`, `per_step_vs_total`, with the values filled in:

```python
# WRONG: this bounds each read, not the request
async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as c:
    r = await c.get("/drip?chunks=10&every_ms=800")
```

```
  WRONG httpx.Timeout(2) only:   8.07 s, 10 bytes, no error
```

**RIGHT: set the total deadline above the call.**

```python
# RIGHT: asyncio.timeout cancels the task wherever it waits
async with asyncio.timeout(2.0):
    r = await c.get("/drip?chunks=10&every_ms=800")
```

```
  RIGHT asyncio.timeout(2) above it:    2.00 s, TimeoutError
```

Three runs gave 8.06 to 8.07 s with no error, and 2.00 s with `TimeoutError` every time. A gap longer than the read timeout does trip it: one byte every 2.5 s gave `2.04 s, ReadTimeout`.

**What the server hears.** HTTP/1.1 has no message that says "the client gave up". RFC 9112, section 8, says only that a server MAY send an error response to an incomplete request before it closes the connection. When the asyncio task is cancelled, httpcore closes the connection. The next request on that client opened a new connection in every run. So the server hears only that the socket closed. Phase 4, section 4.5, verified what uvicorn 0.53.0 does then: it marks the request disconnected and keeps running the handler. `deadline.py` runs the same 2 s job in 10 ms steps with three handlers. The client gives up at 0.5 s in all three:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Client deadline 0.5 s, server job 2 s in 10 ms steps. 3 runs             │
├──────────────────────────────────────────────────────────────────────────┤
│ handler  client sees          steps done   work after the client left    │
│ ignore   gave up at 0.50 s    200 of 200   ██████████████ 1,570-1,580 ms │
│ check    gave up at 0.50 s    43           0 ms                          │
│ budget   HTTP 504 at 0.45-0.46 37 to 38    0 ms, stops itself            │
│                                                                          │
│ check:  await request.is_disconnected() before each step                 │
│ budget: header X-Deadline-Ms = 500; the server keeps back 50 ms and      │
│         checks the clock before each step                                │
└──────────────────────────────────────────────────────────────────────────┘
```

The ignoring handler did the whole job for a client that had left 1.5 s earlier. Under load, timed-out clients retry while the server still works on the old requests. The checking handler stopped within one step of noticing. The budget handler needed no disconnect at all. It received the client's remaining time in a header, kept back a margin of 50 ms for the reply's way back, and stopped itself. Its 504 arrived at 0.45 to 0.46 s, before the client's own deadline, and the client kept its connection.

**The margin makes it work.** With `--margin-ms 0` the server stops when the client does, and loses the race: `client gave up after 0.50 s`, then a new connection. So send less than the time you have left, or let the server keep some back.

**A deadline that was lost, found while building this lab.** The first version of the budget handler relied on `asyncio.timeout(budget)` alone. In one lab run it did the whole 2 s job. That run's log was overwritten, so the check below measures the effect again. The cause is the Phase 4 rule: cancellation stops work only if nothing swallows it. Starlette 1.7.0's `is_disconnected()` awaits `receive()` inside an anyio `CancelScope` that it has cancelled itself, `starlette/requests.py`, lines 333 to 335. When the timeout's cancellation lands during that await, the scope can take it as its own. `deadline.py --swallow 300` runs 300 timeouts around that call, offline, with a real Starlette `Request`:

```
asyncio.timeout alone                         timeouts lost: 20 of 300
asyncio.timeout + a hand check of the clock   timeouts lost: 0 of 300
```

Three logged runs lost 12 to 20 of 300, 4 to 7%. The fix is a clock comparison before each step, which nothing can swallow. The mechanism is inferred from the Starlette source and the counts, not traced into anyio.

**How gRPC does it.** The grpc.io deadlines guide says gRPC sends the deadline as a `grpc-timeout` header. The server cancels the call when it passes. The same guide warns that "the server application is responsible for stopping any activity it has spawned". There is no standard deadline header for plain HTTP. `X-Deadline-Ms` in this lab is an invented name.

**The sentence to remember:** httpx timeouts bound each step, so only a deadline above the call bounds the request. The server keeps working after the client leaves, unless it checks, or gets the budget with a margin.

**The trap:** `httpx.Timeout(2)` on a call to a slow streaming endpoint. Here it took 8.07 s with no error, and the server did 1,570 ms of work for a client that had already gone.

**Try this now:** run `uv run python phase05_machine/deadline.py --margin-ms 0`. Predict the budget handler's line first. The server and the client time out together, and the client loses the reply.

---
## 5.8 — The container's limits (a quota per period, and a p99 step of at most period minus quota)

Why this matters: a CPU limit is not a slower CPU. It is the full CPU for part of every period, then nothing until the period ends. The median looks healthy while the p99 carries the wait. Python does not even see the limit.

**Answer this first.** A Python service runs in a container with `--cpus=0.5`. It gets 30 requests per second, and each needs 10 ms of CPU. That is 60% of its quota. The p99 without a limit is about 30 ms. How much can the limit add to the p99: 10 ms, 50 ms, or 100 ms? And what does `os.cpu_count()` print inside that container on an 8-CPU machine?

**How a limit becomes a quota.** Linux groups processes into control groups, cgroups. Version 2 of that interface, cgroup v2, puts each limit in a file. Docker's `--cpus=0.5` and Kubernetes's `limits.cpu: 500m` both become the file `cpu.max`. Docker's docs give the conversion: `--cpus="1.5"` equals a period of 100000 µs and a quota of 150000 µs. Kubernetes computes it in kubelet's `MilliCPUToQuota`, `pkg/kubelet/cm/helpers_linux.go` at v1.37.1, with a period of 100 ms unless a feature gate changes it. The lab read the file:

```
-- cpu.max with --cpus=0.5: 50000 100000
```

That is 50 ms of CPU in every 100 ms period. The kernel's scheduler, CFS, the Completely Fair Scheduler, enforces it. Its bandwidth docs say what happens when the 50 ms is used up. Throttled threads "will not be able to run again until the next period". So one throttle can add at most the rest of the period: 100 − 50 = 50 ms. Indeed's engineering blog worked the arithmetic for one long request. "The 200ms request now takes 440ms to complete", at 0.4 CPU:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 200 ms of CPU at 0.4 CPU: 40 ms per 100 ms period. Indeed's example      │
├──────────────────────────────────────────────────────────────────────────┤
│ period   0         100        200        300        400        500 ms    │
│          ████░░░░░░████░░░░░░████░░░░░░████░░░░░░████                    │
│          run 40    run 40    run 40    run 40    run 40 → done at 440 ms │
│               throttled 60 ms × 4 = 240 ms                               │
│                                                                          │
│ each wait is period − quota = 60 ms. cpu.stat: nr_periods 5,             │
│ nr_throttled 4, throttled time 240 ms. quota.py's self-test checks it    │
└──────────────────────────────────────────────────────────────────────────┘
```

**The measurement.** `quota.py --docker` runs the same workload three ways: no limit, `--cpus=0.5`, and 0.5 CPU in 20 ms periods, `--cpu-period=20000 --cpu-quota=10000`. A worker container runs under the limit. It serves one request at a time. Each request spins 10 ms on `time.thread_time()`, the thread's CPU clock, so time spent throttled does not count as work done. A driver container with no limit sends Poisson arrivals at 30 per second over loopback, in a shared network namespace. The worker reads `cpu.stat` before and after. Three runs of 20 s each, from `runs/lab5-quota.log`:

```bash
bash runs/lab5.sh Q
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 30 requests/s, 10 ms of CPU each, one worker. 20 s per run               │
├──────────────────────────────────────────────────────────────────────────┤
│ run   no limit p99   --cpus=0.5 p99   step    ≤ 50?   throttled periods  │
│  1       32.6 ms        60.8 ms      +28.2    yes     28 of 198, 14%     │
│  2       30.7 ms        56.2 ms      +25.5    yes     19 of 201,  9%     │
│  3       34.8 ms        83.0 ms      +48.2    yes     30 of 201, 15%     │
│                                                                          │
│ p50: 12.3 to 13.6 ms without a limit, 13.7 to 14.6 ms with it            │
│ n = 561 to 642 per run, so each p99 rests on 5 or 6 requests             │
└──────────────────────────────────────────────────────────────────────────┘
```

The median barely moved. The p99 rose by 25.5 to 48.2 ms, never more than the 50 ms bound. The offline model, `quota.py --model`, gave a p99 of 29.3 ms without a quota and 72.3 ms with it. That is a step of 43 ms. Each p99 here rests on 5 or 6 requests, so the steps differ from run to run. The bound holds in all three.

The worker also timed how long one request's 10 ms of CPU took on the wall clock. Under `--cpus=0.5` that time reached 41.5 to 53.0 ms at p99: 10 ms of work plus up to 43 ms throttled. Without a limit it stayed at 15.1 to 17.0 ms at p99.

`cpu.stat` said it too. Indeed calls `nr_throttled / nr_periods` the throttled percentage. A throttled percentage above zero while CPU use stays under the limit shows this problem.

**The generator had to leave the container.** The first version made the arrivals inside the limited container, with `time.sleep`. In the Docker Desktop VM that sleep woke 5.94 ms late at the median and 11.13 ms at p99. Phase 1's rule makes that run invalid. So the driver now runs in its own container, sleeps until 15 ms before each arrival, and spins the rest. In the worker, that spin would spend the quota under test. The driver's lag p99 was 2.46 to 3.92 ms in every run. Without a limit, the p50 still sat 2.3 to 3.6 ms above the model's 10.0 ms. The cause was not checked. The loopback hop and the VM's scheduling are candidates.

**A shorter period has a cost.** The kernel docs say a small period gives a more consistent latency at the expense of burst capacity. Here the burst capacity mattered. With 10 ms per 20 ms, a 10 ms request that starts mid-period is split across two periods. The p50 rose to 19.8 to 21.6 ms, the p99 was 85.5 to 107.2 ms, and 39 to 43% of periods were throttled. The model predicted the same direction: p50 15.5 ms, p99 100.2 ms.

**Python does not see the quota.** `os.cpu_count()` and `os.process_cpu_count()` printed 8 inside every container. Both read the CPUs of the machine, not `cpu.max`, from `Modules/posixmodule.c` and `Lib/os.py` at v3.13.0. CPython issue #149452, still open, shows `--cpus=2` printing 20 on a larger host. So part A's default thread pool still has `min(32, 8 + 4) = 12` threads inside a half-CPU container. A config that starts `2 × os.cpu_count() + 1` workers starts 17 here. Set `-X cpu_count=N` or `PYTHON_CPU_COUNT=N` from the limit. The Python 3.13 docs say both override `os.cpu_count()` and `os.process_cpu_count()`.

**An old kernel bug.** Before Linux 5.4, unused per-CPU slices of quota could expire, so an idle service could be throttled far below its limit. Commit `de53fd7aedb1`, by Dave Chiluk of Indeed, fixed it. Indeed's second post lists backports, such as 4.19.84.

**Memory limits, briefly.** `memory.max` is the hard limit. When usage reaches it and cannot be reduced, the kernel runs its OOM killer, the out-of-memory killer, in that cgroup. Page cache counts toward the same limit. Kubernetes reports a kill as `OOMKilled` with exit code 137, 128 plus SIGKILL's 9. From the cgroup v2 and Kubernetes docs. Not measured here.

**The sentence to remember:** a CPU limit is the full CPU for part of each period and none for the rest. One throttle adds at most the period minus the quota, so the p50 stays and the p99 steps up. Python's CPU count does not see it.

**The trap:** reading average CPU. At 60% of the quota the service seems to have 40% headroom. Yet 9 to 15% of periods were throttled, and the p99 rose by up to 48 ms.

**Try this now:** run `uv run python phase05_machine/quota.py --model --rate 40`. Predict it first: 80% of the quota, so more periods run out, and each wait is still at most 50 ms. Then read `nr_throttled / nr_periods` from `/sys/fs/cgroup/cpu.stat` in any container you run, before and after a load test.

---
## 🧪 Hands-on lab — part B

**Run status:** every command below was executed on the author's machine on 2026-09-25, after the last code change. Docker Desktop was started for part Q and quit after it. Each "Expected" line is copied from `runs/lab5-*.log`. Your milliseconds will differ. The ratios, the bound and the named fault should not.

All commands run from `elite-performance/code/`. `bash runs/lab5.sh L D C X F M` runs the local parts of this document. `bash runs/lab5.sh Q` runs the container part.

- [ ] **E7 (local).** The Test-out: a pool of 10 serves 200 concurrent requests of 20 ms.
  - First write your prediction for the burst and for the closed loop.
  - Run: `uv run python phase05_machine/pool_size.py --repeat 3 --duration 5`.
  - Expected: `PREDICT burst of 200, pool 10, 20 ms: 20 waves, mean 210 ms, p50 210 ms, max 400 ms`. The lean pool: means 239.4 to 244.5 ms, maxima 464.2 to 472.1 ms. httpx alone: means 387.1 to 398.5 ms, with 2,101 to 2,153 pool retries. The sustained loop: 426 to 434 per second, `hold = 10 / rate = 23.0` to `23.5 ms`.
  - Teaches: Little's law sizes the pool, the pool wait is the metric, and the client library's pool has its own cost.

- [ ] **E8 (break-it, local).** Let the idle limit close connections between bursts.
  - Run: `uv run python phase05_machine/pool_size.py --churn`.
  - Expected: with the httpx defaults, bursts 2 to 5 opened `30` new TLS connections each. With `max_keepalive_connections=50`, they opened `0`, `0`, `5` and `17`, but took 508 to 762 ms with 292 to 350 pool retries each.
  - Teaches: an idle limit below the burst size turns bursts into handshakes.

- [ ] **E9 (local).** A page-cache hit, an SSD read, a buffered read, and a durable write.
  - Run: `uv run python phase05_machine/pagecache.py --repeat 3 --fsync 20 --syscall --buffers`.
  - Expected: miss p50 `88.7`, `89.5` and `89.8 us`, hit p50 `1.5 us`, ratios `61x`, `58x`, `62x`, and `miss reads under 10 us: 0 of 2000`. `os.fsync` p50 95.0 to 109.9 µs, `F_FULLFSYNC` p50 2,852.4 to 2,882.8 µs. Buffered 100-byte reads 8.5 to 9.2 times faster than unbuffered.
  - If the miss pass is fast: the file stayed in the page cache. Check that `write_file` set `F_NOCACHE`.
  - Teaches: what is cached decides the cost of a read, and a durable write on a Mac costs milliseconds.

- [ ] **E10 (break-it, local).** Remove the rules that make the miss pass a miss.
  - Run: `uv run python phase05_machine/pagecache.py --offset-unit 4k --reads 2000`, then `uv run python phase05_machine/pagecache.py --cached-write --size-mb 64 --reads 500 --repeat 3`.
  - Expected: with 4 KiB offsets, the shared-page count and the fast-miss count match: `106 of 2000` in run 1 of the log. With the normal write: `miss p50 / hit p50 = 1x` and `miss reads under 10 us: 500 of 500`.
  - Teaches: a benchmark that does not control the cache measures memory, and calls it the disk.

- [ ] **E11 (break-it, local).** A deadline, and a server that keeps working.
  - Run: `uv run python phase05_machine/deadline.py`, then the same with `--margin-ms 0`, then `uv run python phase05_machine/deadline.py --swallow 300`.
  - Expected: `WRONG httpx.Timeout(2) only:   8.07 s, 10 bytes, no error` and `RIGHT asyncio.timeout(2) above it:    2.00 s, TimeoutError`. Handler `ignore`: `work after the client left   1570 ms`. Handler `budget`: `client HTTP 504 after 0.46 s`, no new connection. With `--margin-ms 0`: `client gave up after 0.50 s`. Swallow: 12 to 20 of 300 lost, and `0 of 300` with the hand check.
  - Teaches: only a total deadline bounds the call, and only the server can stop its own work.

- [ ] **E12 (local, then Docker).** The quota and its bound, then one fault named from metrics alone. This is the phase's second demonstration.
  - Run: `uv run python phase05_machine/quota.py --model`, then `bash runs/lab5.sh Q` if Docker Desktop is installed.
  - Expected, model: `no quota: ... p99   29.3` and `quota per period: ... p50   10.0 ... p99   72.3 ...  throttled 879 of 5812 periods (15%)`. Docker: the p99 step of 25.5 to 48.2 ms, each under 50 ms, and generator lag p99 2.46 to 3.92 ms, `valid`.
  - Then run `uv run python phase05_machine/diagnose.py --fault mystery --seed 3`. Read the two tables and name the layer before you look. Then run it again with `--reveal`. The numbers change a little, and the fault stays the same.
  - Expected: the `network p50` row went from 12.53 to 53.08 ms, `+40.55`, while `server p50` moved by `-0.48` and `pool wait p50` by `+0.35`. Both runs valid by the lag rule. Then `diagnose(): rtt` and `the fault was: rtt`.
  - If the pull hangs: the Docker credential helper may wait for a keychain prompt. `runs/lab5.sh` uses an empty client config.
  - Teaches: a quota adds at most period minus quota, and a fault is named by the row that moved.

**Why the table works.** Each fault moves one row that no other fault moves. `network` is the first byte minus the server's own time, from the W3C Server-Timing header that `server.py` sends. Latency counts from each request's scheduled time. All eight runs in `runs/lab5-diagnose.log` had a generator lag p99 of 2.32 to 2.79 ms, so they pass Phase 1's 10 ms rule. Each run had 368 requests, so a p99 rests on 3 of them. The diagnosis reads p50 rows only.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 40 requests/s for 10 s, one fault per run. The change in each p50, in ms │
├───────────────┬───────────┬───────────┬───────────┬──────────────────────┤
│ fault         │ pool wait │ tls       │ server    │ network  new conn/100│
├───────────────┼───────────┼───────────┼───────────┼──────────────────────┤
│ pool 20 → 1   │  +180.72  │   +0.00   │   +0.01   │   +0.38      -0.27   │
│ keep-alive off│    -0.07  │  +13.32   │   -1.18   │   -0.91     +99.73   │
│ RTT 10 → 50   │    +0.05  │   +0.00   │   -0.24   │  +40.50      +0.82   │
│ server 10 → 40│    -0.02  │   +0.00   │  +29.84   │   -0.25      +0.82   │
└───────────────┴───────────┴───────────┴───────────┴──────────────────────┘
```

Without the Server-Timing header, a slower server looks like a slower network. With the header removed, the self-test's `diagnose()` named a slow server "rtt".

---

## 🔍 Check it yourself

1. Open `phase05_machine/pool_size.py:124`. This is `burst_httpx`. The semaphore is used at line 141. Suppose the semaphore allowed 20 instead of the pool's 10. Where would the extra 10 requests wait, and which number in E7 would move back towards the ungated run?

2. Open `phase05_machine/deadline.py:115`. This is where the `check` handler stops. Every mode calls `is_disconnected()` on the line before, but only `check` acts on it. Why does `ignore` call it too? What would E11 print for "work after the client left" without it?

3. Open `phase05_machine/quota.py:183`. This is `spin_cpu`. It spins on `time.thread_time()`. Suppose it used `time.perf_counter()` instead. What would a request that is throttled for 40 ms do, and why would E12's p99 under `--cpus=0.5` then look better than the truth?

4. Open `phase05_machine/pagecache.py:96`. This is `offsets`. It draws one offset per 16 KiB page. Suppose it drew distinct 4 KiB offsets again. Which two lines of E9's output would then show the same non-zero number, and why?

---

## ✅ Checkpoint 5B — answer in your own words

1. **Predict, with the arithmetic.** This is the phase's Test-out. A pool of 10 connections serves 200 concurrent requests with a 20 ms service time. (a) If the 200 arrive at once, predict the mean and the slowest latency. (b) If 200 clients loop forever, predict the throughput and the mean latency. (c) Your measurement shows a mean of 390 ms for (a). Name the two places the extra time could be, and the check for each.

2. **This is broken.** A service's p50 is 14 ms and its p99 jumped from 33 ms to 75 ms after a move to Kubernetes with `limits.cpu: 500m`. Average CPU use is 60% of the limit. The code did not change. What is the cause, which file proves it, is the size of the jump plausible, and what are two fixes with their costs?

3. **A colleague says:** "Our reads take 2 µs, I benchmarked it. We can move the data to a network volume and nothing will change." Argue for or against, with numbers from section 5.6.

4. **Walk through what happens.** A client with `httpx.Timeout(5)` calls an endpoint that streams one line every 3 s for 60 s, behind a load balancer. The client's caller gave up after 10 s. What does each of the three parties do, and for how long?

5. **Given these constraints, design** the deadline path for a Python API that calls two downstream services in sequence. The API's own deadline is 800 ms. Downstream A usually takes 100 ms and B 300 ms. State where each timeout is set, what travels to the downstream servers, and what each server does when the budget runs out.

6. **Demonstrate.** You have the two tables of `diagnose.py --fault mystery --seed 3`. Write the diagnosis in three lines, one number per line. Say why the run counts, and which production metric would give the same diagnosis.

<details>
<summary>Answer sketches</summary>

1. (a) 20 waves of 10: wave k finishes at 20k ms. Mean 20 × 10.5 = 210 ms, slowest 400 ms. (b) Around the connections: 10 = λ × 0.020, so λ = 500 per second. Around the whole client: W = 200 / 500 = 400 ms. (c) In the client's pool, or on the server. Check the pool wait with a trace hook, and the server's own time with Server-Timing. In E7 the server stayed at 20.2 to 20.3 ms. The lean pool measured 239.4 to 244.5 ms, and httpx's own pool 387.1 to 398.5 ms, with over 2,000 pool retries.

2. `limits.cpu: 500m` becomes `cpu.max` = `50000 100000`. A request that runs when the 50 ms is used up waits for the next period, at most 100 − 50 = 50 ms. So the p50 stays and the p99 gains up to 50 ms. A jump of 42 ms fits: section 5.8 measured steps of 25.5 to 48.2 ms. Proof: `nr_throttled` in `/sys/fs/cgroup/cpu.stat` rises while usage is under the limit. Fixes: raise the limit, which costs capacity that sits idle on paper. Or remove the CPU limit and keep the request, which gives up the hard cap on noisy neighbours.

3. Against. 2 µs is a page-cache hit. The same laptop measured about 90 µs for a read that missed the cache, and AWS states single-digit milliseconds for gp3. If the working set fits in memory on the new host, the hit rate may hold. Every miss then costs milliseconds instead of about 90 µs. Measure the miss rate under production memory pressure. Here a 256 MiB file written normally kept only part of its pages in memory.

4. The read timeout of 5 s never fires, because each gap is 3 s. If the caller cancelled the task at 10 s, httpx closed the connection. If it only stopped waiting, the client reads for 60 s. The load balancer may keep its upstream open, depending on its own idle timeout. The server keeps streaming for 60 s unless it checks for the disconnect. Fix: `asyncio.timeout` at the client, and a disconnect check or a budget on the server.

5. Set one total deadline at the API edge with `asyncio.timeout(0.8)`. Before each call, compute the remaining budget and send it in a header. Give A at most its share, for example 200 ms, and give B what is left. Each server keeps back a margin, 50 ms in the lab, so its 504 arrives before the caller gives up. It wraps its work in `asyncio.timeout` of the rest, and also compares the clock before each step, as section 5.7 found. Keep httpx's connect and read timeouts as stall detectors, shorter than the budget.

6. `network p50` rose by 40.55 ms, from 12.53 to 53.08. `server p50` moved by −0.48 ms, so the handler did not slow down. `pool wait p50` moved by +0.35 ms and no TLS appeared, so the pool and keep-alive are fine. Diagnosis: the round trip grew by about 40 ms. The run counts: its generator lag p99 was 3.17 ms, under the 10 ms rule. In production, add the Server-Timing header or a server-side histogram, and record first byte minus server time per downstream.

</details>

---

## References & Further Learning — part B

Every URL below was fetched on 2026-09-25 and returned HTTP 200.

**Pools**

- **Netflix concurrency-limits README at v0.5.4** — https://raw.githubusercontent.com/Netflix/concurrency-limits/v0.5.4/README.md
  Focus on: the Little's law line. A README, not a paper.
- **httpx `_config.py` at 0.28.1** — https://raw.githubusercontent.com/encode/httpx/0.28.1/httpx/_config.py
  Focus on: `DEFAULT_LIMITS`, `keepalive_expiry=5.0` and `DEFAULT_TIMEOUT_CONFIG`.
- **httpcore `_async/connection_pool.py` at 1.0.9** — https://raw.githubusercontent.com/encode/httpcore/1.0.9/httpcore/_async/connection_pool.py
  Focus on: `_assign_requests_to_connections`. Compare it with E7's retry counts.

**Storage**

- **Apple, fsync(2) man page** — https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/fsync.2.html
  Focus on: the paragraph about the drive's cache and `F_FULLFSYNC`.
- **CPython `Modules/posixmodule.c` at v3.13.0** — https://raw.githubusercontent.com/python/cpython/v3.13.0/Modules/posixmodule.c
  Focus on: `os_fsync_impl`, plain `fsync`, and `os_cpu_count_impl`, which never reads a cgroup.
- **Python 3.13 docs, built-in functions** — https://docs.python.org/3.13/builtins/functions.html
  Focus on: `open`, the default buffering policy.
- **AWS EBS, "General Purpose SSD volumes"** — https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html
  Focus on: the gp3 latency sentence, the source for "milliseconds from a network disk".
- **Linux kernel docs, "/proc/sys/vm"** — https://docs.kernel.org/admin-guide/sysctl/vm.html
  Focus on: `drop_caches`, a cold cache on Linux.

**Deadlines**

- **httpx docs, "Timeouts"** — https://www.python-httpx.org/advanced/timeouts/
  Focus on: the four timeouts and the word "inactivity".
- **uvicorn `protocols/http/h11_impl.py` at 0.53.0** — https://raw.githubusercontent.com/encode/uvicorn/0.53.0/uvicorn/protocols/http/h11_impl.py
  Focus on: `connection_lost` and the `disconnected` flag. Phase 4, section 4.5, ran it.
- **gRPC guide, "Deadlines"** — https://grpc.io/docs/guides/deadlines/
  Focus on: server-side cancellation and the warning about spawned work.
- **RFC 9112, HTTP/1.1** — https://www.rfc-editor.org/rfc/rfc9112.txt
  Focus on: section 8, incomplete messages.
- **W3C, "Server Timing"** — https://www.w3.org/TR/server-timing/
  Focus on: the header syntax that `diagnose.py` uses to split server time from network time.

**CPU and memory limits**

- **Linux kernel docs, "CFS Bandwidth Control"** — https://docs.kernel.org/scheduler/sched-bwc.html
  Focus on: quota, period, the 5 ms slice, and small periods.
- **Linux kernel docs, "Control Group v2"** — https://docs.kernel.org/admin-guide/cgroup-v2.html
  Focus on: `cpu.max`, `cpu.stat`, `memory.max`, `memory.high` and `memory.events`.
- **Indeed Engineering, "Unthrottled: Fixing CPU Limits in the Cloud", Dave Chiluk, 2019** — https://engineering.indeedblog.com/blog/2019/12/unthrottled-fixing-cpu-limits-in-the-cloud/
  Focus on: the 440 ms example and the throttled percentage. A production report.
- **Indeed Engineering, "Unthrottled: How a Valid Fix Becomes a Regression", 2019** — https://engineering.indeedblog.com/blog/2019/12/cpu-throttling-regression-fix/
  Focus on: slices, stranded quota on many cores, and the kernels with the fix.
- **Linux commit de53fd7aedb1** — https://github.com/torvalds/linux/commit/de53fd7aedb100f03e5d2231cfce0e4993282425
  Focus on: the commit message: cause, fix, and the fibtest result.
- **Kubernetes, "Resource Management for Pods and Containers"** — https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
  Focus on: CPU limits enforced by throttling, and the `OOMKilled` example with exit code 137.
- **Kubernetes `pkg/kubelet/cm/helpers_linux.go` at v1.37.1** — https://raw.githubusercontent.com/kubernetes/kubernetes/v1.37.1/pkg/kubelet/cm/helpers_linux.go
  Focus on: `MilliCPUToQuota`, the 100 ms period and the 1 ms minimum quota.
- **Docker docs, "Resource constraints"** — https://docs.docker.com/engine/containers/resource_constraints/
  Focus on: `--cpus` against `--cpu-period` and `--cpu-quota`.
- **CPython issue #149452** — https://github.com/python/cpython/issues/149452
  Focus on: `--cpus=2` printing 20. Still open.
- **Python 3.13 docs, "Command line and environment"** — https://docs.python.org/3.13/using/cmdline.html
  Focus on: `-X cpu_count` and `PYTHON_CPU_COUNT`.

---

## Cheatsheet — part B

```
POOLS
  Little         L = λW for any boundary you draw
  connections    busy = rate × hold:  10 = 500/s × 20 ms
  whole client   W = clients / rate:  200 / 500/s = 400 ms
  burst n, pool c, S   waves n/c; mean S(n/c + 1)/2; max S n/c
  200 @ pool 10 @ 20 ms  predicted 210 / 400; lean 243 / 464-472; httpx 391
  metric         pool wait = call → connect or send event (trace hook)
  httpx 0.28.1   idle limit 20, expiry 5 s; a semaphore in FRONT: 391 → 263
  keep-alive     client expiry < server and load balancer idle timeout

STORAGE (M2, 16 KiB pages)
  syscall        getppid 0.23-0.25 µs;  cached 4 KiB pread 0.91-1.01 µs
  page cache hit 1.5 µs            SSD miss 88.7-89.8 µs, 58-62x
  network disk   gp3: single-digit ms (AWS)
  buffered read  100-byte records: 8.5-9.2x faster than unbuffered
  fsync (macOS)  95-110 µs, drive's cache only;  F_FULLFSYNC 2.85-2.88 ms
  benchmark      one offset per cache page; control the cache

DEADLINES
  httpx Timeout  connect / read / write / pool: EACH STEP, restarts
  total          async with asyncio.timeout(s): the only bound on the call
  server         HTTP/1.1 sends no cancel; uvicorn keeps running the handler
  budget         send the remaining time; server keeps back a margin (50 ms)
  swallowed      is_disconnected() lost 12-20 of 300 timeouts:
                 also compare the clock before each step

CPU QUOTA
  --cpus=0.5     cpu.max = 50000 100000: 50 ms per 100 ms period
  bound          one throttle adds ≤ period − quota = 50 ms
  measured       p99 step +25.5 to +48.2 ms; p50 unchanged
  proof          cpu.stat nr_throttled / nr_periods > 0 below the limit
  short period   less wait per stop, less burst: p50 → 19.8-21.6 ms
  generator      outside the limit; lag p99 must stay ≤ 10 ms
  Python         os.cpu_count() ignores the quota: set PYTHON_CPU_COUNT
```

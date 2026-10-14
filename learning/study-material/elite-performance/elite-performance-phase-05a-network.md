# Phase 5A — The machine beneath an API request: the wire

**The question this phase answers:** where do the 40 milliseconds go between a client's request and the first byte of the response? And which of them are yours?

Here is an example. Your service reports 8 ms per request in its own metrics. The client that calls it measures 45 ms. The 37 ms in between are in no dashboard you own. They are in a DNS lookup, a TCP or TLS handshake, a thread pool, a connection pool, or a page that was not in memory. The example is invented. Every part of it is measured in this phase on your laptop.

You cannot fix latency you cannot see. This phase makes the layers under a request visible, and names the one that moved. It teaches five ideas. Each is a claim you could get wrong today:

1. **The first request on a new connection pays DNS, TCP and TLS round trips before the request itself**. A warm pool pays none of them. So the pool's size and its keep-alive limits decide how often you pay.
2. **Python's network calls wait where no single timeout looks**. asyncio runs the blocking `getaddrinfo` in its default thread pool, which other blocking work shares. Each httpx timeout starts again at every step. So only a deadline set above the call bounds the total, and the server is not told when it passes.
3. **HTTP/2 moves head-of-line blocking from the request to the TCP connection**. So one lost packet stalls every stream on it.
4. **A read from the page cache costs about 2 µs**. A read from a local SSD costs tens to hundreds of microseconds, and one from a network disk milliseconds. The code is the same, so what is cached decides.
5. **A CPU quota is enforced per period**. A container that spends its quota early waits for the rest of the period. That adds up to the period minus the quota to a request: 50 ms for `--cpus=0.5` at the default 100 ms period. So the p50 stays, and the p99 rises.

Phase 5 is split into two documents. This one follows a request onto the wire. Part B follows it into the pool, the disk, the deadline and the container.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, this document: the wire                          ideas           │
│  5.1  DNS                     — a lookup that waits for a thread   2     │
│  5.2  TCP                     — one round trip before any byte     1     │
│  5.3  TLS                     — one or two more, and CPU           1     │
│  5.4  HTTP/1.1, HTTP/2, gRPC  — where head-of-line blocking lives  3     │
│  Lab: E1 to E6. The demonstration: one request, layer by layer           │
│                                                                          │
│ PART B, the next document: the host                                      │
│  5.5  Connection pools done right    — Little's law, idle limits   1     │
│  5.6  Syscalls, buffers, page cache  — memory against the SSD      4     │
│  5.7  Deadlines through the stack    — per-step against total      2     │
│  5.8  The container's limits         — the quota and its period    5     │
│  Lab: E7 to E12. The demonstration: one fault, named from metrics        │
└──────────────────────────────────────────────────────────────────────────┘
```

**What this part assumes.** Four sections are used here and not taught again. The short version of each is enough.

- **Phase 1, section 1.1, "The distribution of one Python endpoint".** A load test returns a distribution, not a number. Read its ladder of p50, p90, p99 and max. The p99 is the latency that 99% of requests stay under. Count the samples behind each percentile before you trust it.
- **Phase 1, section 1.5, "The prediction sheet".** Write the number you expect before the run. The gap between the prediction and the measurement names what you did not model.
- **Phase 2, section 2.3, "Pools that fill".** Its subtitle is "the wait rises long before the errors come". A pool of c connections or c threads is a queue with c servers. When all c are busy, the next request waits, and that wait is part of its latency. asyncio's default thread pool is one of these pools.
- **inference-internals 5.1, the three timeouts.** A client needs a connect timeout, a stall timeout between chunks, and a total deadline. They catch three different failures. Section 5.7 shows how httpx maps onto them.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing, except E2, which sends 9 small HTTPS requests to www.python.org. Every number here was measured on 2026-09-25 on an Apple M2 with 8 GB of memory and 8 cores. The software was macOS 15.7.8, CPython 3.13.3 through uv, httpx 0.28.1 with httpcore 1.0.9, h2 4.4.1, and OpenSSL 3.6.4. Other programs ran at the same time. The load average at the start of each log was 3.7 to 4.8. Every log in `runs/lab5-*.log` starts with those conditions. So read the ratios and the round-trip counts first. The milliseconds will differ on your machine.

Setup:

```bash
cd ~/Desktop/project/study-material/elite-performance/code
uv sync
uv run python phase05_machine/server.py --self-test
```

The last line should print `self-test passed`. The first run also makes a self-signed certificate in `phase05_machine/.certs/` with the `openssl` command.

**The lab tools.** Three small programs make the layers visible on one laptop:

- `server.py` is a local HTTPS server that speaks HTTP/1.1 and HTTP/2. Its `/delay?ms=N` endpoint waits N ms and costs no CPU. So any time on top of N belongs to the layers under the request.
- `netem.py` is a TCP proxy that adds a round-trip time. On loopback a round trip costs about a tenth of a millisecond, so a handshake is invisible. Through `netem.py --delay-ms 20` each round trip costs 40 ms, and you can count them.
- `timeline.py` records httpx's trace events for one request and prints it as a sum of layers.

Time for part A: 1.5 to 2 hours. About 3 minutes of that is waiting for runs.

---
## 5.1 — DNS (a lookup that waits for a thread, not for the network)

Why this matters: every new connection starts with a name lookup. In Python the lookup does not only wait for the network. It first waits for a free thread in a pool that other code shares. When that pool is full, new connections stop, and the metrics blame the network.

**Answer this first.** An asyncio service runs 12 file reads through `asyncio.to_thread`. Each read takes 1 second. While they run, the service opens a new connection to `localhost`, which needs no network at all. How long does the name lookup take: under a millisecond, about 10 ms, or about a second? And a request on a connection that is already open?

**The path of one lookup.** asyncio has no DNS client of its own. `loop.getaddrinfo` hands the C library's blocking `getaddrinfo` to the default thread pool. In the code this pool is `loop._default_executor`. The CPython source says so at `Lib/asyncio/base_events.py`, v3.13.0, lines 928 to 936. httpx gets there through httpcore and anyio:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One DNS lookup under httpx.AsyncClient, CPython 3.13                     │
├──────────────────────────────────────────────────────────────────────────┤
│  client.get(url)                                                         │
│    └► httpcore  connect_tcp          ◄── httpx's connect timeout covers  │
│         └► anyio.connect_tcp             this whole box, DNS included    │
│              └► loop.getaddrinfo(host, port)                             │
│                   └► run_in_executor(None, socket.getaddrinfo, ...)      │
│                        │                                                 │
│   ┌────────────────────▼─────────────────────────────────────────────┐   │
│   │ the default thread pool: min(32, cpus + 4) = 12 threads          │   │
│   │ shared with asyncio.to_thread and run_in_executor(None, ...)     │   │
│   └────────────────────┬─────────────────────────────────────────────┘   │
│                        ▼                                                 │
│   C getaddrinfo, blocking ──► macOS: mDNSResponder, which caches answers │
│                               Linux glibc: resolv.conf name servers,     │
│                               timeout 5 s, 2 attempts by default         │
└──────────────────────────────────────────────────────────────────────────┘
```

Four facts in this picture decide what you see:

1. **The default thread pool is shared and small.** Its size is `min(32, os.process_cpu_count() + 4)`, from `Lib/concurrent/futures/thread.py` at v3.13.0, line 145. On an 8-core M2 that is 12 threads.
2. **Python keeps no DNS cache.** Neither asyncio nor httpx 0.28.1 nor httpcore 1.0.9 caches an answer. Any cache is the operating system's. On macOS, mDNSResponder caches replies. On a Linux container with plain glibc and no local cache, each lookup can go to the network. That last point is inferred from the glibc sources, not run.
3. **A slow resolver holds its thread.** The glibc defaults are a 5 s timeout and 2 attempts, from `resolv.conf(5)`. So one dead name server can hold one thread for about 10 s per lookup. That figure is inferred from `res_send.c`, not run.
4. **A name with two families can wait 250 ms.** anyio's `connect_tcp` tries the first IPv6 address, then waits `happy_eyeballs_delay=0.25` s before it also tries IPv4. A name with an AAAA record and a broken IPv6 path pays that on every new connection. Read in anyio 4.15.1, `_core/_sockets.py`, not run here.

**What the Python docs warn.** The asyncio event loop page says: "When this executor is saturated, these methods may experience delays".

**The measurement.** `dns_starve.py` fills the default thread pool with 12 blocking jobs of 1 s each, through `asyncio.to_thread`. Then it times what happens next. The server is `server.py` on loopback, so no request leaves the machine. Three runs, from `runs/lab5-dns.log`:

```bash
uv run python phase05_machine/dns_starve.py --repeat 3
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 12 blocking jobs of 1 s in the 12-thread default thread pool. Run 1 of 3 │
├──────────────────────────────────────────────────────────────────────────┤
│ idle pool, lookup of localhost        ▏                          0.31 ms │
│ starved pool, lookup                  ████████████████████████ 958.22 ms │
│ starved, request on a WARM connection ▏                          1.43 ms │
│ starved, request on a NEW connection  ████████████████████████ 960.78 ms │
│ jobs cancelled by asyncio.timeout(0.1)█████████████████████    848.02 ms │
│ fix: jobs in their own executor       ▏                          0.94 ms │
│ fix: in-process cache, starved pool   ▏                          0.01 ms │
└──────────────────────────────────────────────────────────────────────────┘
```

Across the three runs the starved lookup took 948.76 to 958.22 ms, against 0.31 to 0.32 ms idle. That is about 3,000 times longer, for a lookup that needs no network. With one thread left free, `--jobs 11`, the same lookup took 0.55 ms.

Four lessons are in these rows:

1. **The lookup waited for a thread, not for DNS.** It needed about 0.3 ms of work. It waited about 950 ms for one of the 12 threads to finish its 1 s job.
2. **A warm connection did not care.** The request on an open connection took 1.43 to 1.53 ms. It needs no lookup. Only new connections pay. So the symptom looks like "connecting is slow", never like "the service is slow".
3. **A timeout frees the coroutine, not the thread.** The jobs wrapped in `asyncio.timeout(0.1)` gave up after 0.1 s. Their threads kept sleeping, and the lookup still waited 848.02 to 852.62 ms. A running thread-pool job cannot be cancelled. `concurrent/futures/_base.py` at v3.13.0 returns False for a running future.
4. **The fixes work at different layers.** Blocking work in its own executor left the default thread pool free: the lookup took 0.88 to 0.94 ms. A cache in the process answered in 0.01 ms, starved or not.

**WRONG: send blocking work through the default thread pool.** This is the most common form in a Python service:

```python
# WRONG: file reads, a sync SDK, a password hash: all through the pool DNS needs
data = await asyncio.to_thread(read_report, path)          # 12 of these at once
```

```
  starved pool, lookup                                  958.22 ms
  starved pool, request on a new connection             960.78 ms
```

**RIGHT: give blocking work its own executor, sized for it.** This is fix 1 of `dns_starve.py`, applied to the same file read:

```python
# RIGHT: the default thread pool, and with it every getaddrinfo, stays free
blocking_pool = concurrent.futures.ThreadPoolExecutor(max_workers=12, thread_name_prefix="blocking")
data = await loop.run_in_executor(blocking_pool, read_report, path)
```

```
  fix: jobs in their own executor, lookup                 0.94 ms
```

The Python docs give the same two fixes: a custom executor for your own tasks, or a larger default executor. A larger default only moves the limit. A separate executor removes the coupling.

**The cache, and its price.** `CachingResolver` in `dns_starve.py:60` keeps each answer for a fixed time to live, the TTL, and serves repeats from memory. `getaddrinfo` does not return the record's real TTL, so the cache uses its own. That is its risk. For `ttl` seconds after a record changes, the process keeps using the old address.

**A warm connection never looks up its name again.** A pooled connection keeps the address it connected to. After a DNS change, a warm pool keeps sending to the old address until the connection closes. This is inferred from the path above: only `connect_tcp` calls `getaddrinfo`. So a client that must follow DNS changes needs a maximum connection age, not only a DNS TTL.

**When the record disappears.** AWS published a summary of its us-east-1 event of 19 and 20 October 2025. It names "a latent race condition in the DynamoDB DNS management system". It left an empty DNS record for `dynamodb.us-east-1.amazonaws.com`. All times are Pacific, from that summary:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ AWS us-east-1, 19 to 20 October 2025, DynamoDB impact. Times PDT         │
├──────────────────────────────────────────────────────────────────────────┤
│ Oct 19 11:48 PM  the regional endpoint's DNS record becomes empty        │
│ Oct 20 12:38 AM  engineers identify DNS state as the source              │
│         1:15 AM  temporary mitigations reconnect some internal services  │
│         2:25 AM  all DNS information restored                            │
│  2:25 to 2:40 AM customers recover "as cached DNS records expired"       │
│                                                                          │
│ 50 min to identify. 2 h 37 min to restore the record. The whole event,   │
│ with its later EC2 and load balancer periods, lasted until 2:20 PM.      │
└──────────────────────────────────────────────────────────────────────────┘
```

Two phrases in the summary map onto this section. Clients were "unable to establish new connections to the service". DNS is paid only when a connection is new. And recovery waited for caches, including every client's own. The summary does not say whether connections that were already open kept working. Do not assume they did.

**The sentence to remember:** in asyncio, a DNS lookup first waits for a thread in the default thread pool. Blocking work in that pool delays every new connection, and a timeout never frees the thread.

**The trap:** `asyncio.to_thread` for file reads or a sync SDK, in the same process that opens connections. On this laptop, 12 such jobs of 1 s turned a 0.3 ms lookup of `localhost` into 958 ms. A dashboard would call it a slow network.

**Try this now:** run `uv run python phase05_machine/dns_starve.py --jobs 11`. With one thread left free, predict the starved lookup before you run it. The log shows 0.55 ms. Then run `--jobs 12` and see it jump to about the job length.

---
## 5.2 — TCP (one round trip before any byte, and a window that starts small)

Why this matters: a new TCP connection costs one round trip before the request can leave. Then a small starting window limits its first responses. A round trip, or RTT, is the time for a packet to reach the other side and for the answer to come back. Within one region it is under a millisecond to a few milliseconds. Across a continent it is tens of milliseconds. Every one of them is paid again on each new connection.

**Answer this first.** A client 40 ms away from a server opens a new HTTPS connection and asks for a small response. The server answers in 0 ms. How many round trips pass before the first byte of the response arrives, with TLS 1.3? And on a connection that is already open?

**The handshake.** RFC 9293, the current TCP standard, calls it the three-way handshake. The client sends SYN, a packet that asks to open a connection. The server answers SYN-ACK, which accepts and asks back. The client sends ACK with, or before, its first data. So the client can send its request only after one full round trip. Here is a cold HTTPS request on the wire, with TLS 1.3 from section 5.3:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ A cold HTTPS request, TLS 1.3, RTT = 40 ms, server time 0 ms. Example    │
├──────────────────────────────────────────────────────────────────────────┤
│  client                                              server              │
│   t=0    DNS answer from the local cache       (0 RTT to the server)     │
│   t=0    SYN ───────────────────────────────────►                        │
│   t=40   ◄─────────────────────────────────── SYN-ACK        1 RTT: TCP  │
│   t=40   ACK + ClientHello, key share ─────────►                         │
│   t=80   ◄──── ServerHello ... certificate ... Finished      1 RTT: TLS  │
│   t=80   Finished + GET /  ─────────────────────►                        │
│   t=120  ◄──────────────────────────── response headers      1 RTT: HTTP │
│                                                                          │
│  cold: 3 round trips = 120 ms      warm connection: 1 round trip = 40 ms │
│  TLS 1.2 adds one more: 4 round trips = 160 ms                           │
└──────────────────────────────────────────────────────────────────────────┘
```

**The start of the window.** TCP does not send a whole response at once. It sends a congestion window of segments, waits for acknowledgements, and grows the window. RFC 5681 calls this slow start. Linux starts at 10 segments, `TCP_INIT_CWND 10` in `include/net/tcp.h` at v6.12. That follows RFC 6928, which is Experimental, not a standard. Ten segments of 1,460 bytes are 14,600 bytes. The macOS value was not found. The arithmetic below is inferred from those rules, with no loss and one acknowledgement per segment. It is not measured here:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Slow start from 10 segments of 1,460 bytes. Inferred arithmetic          │
├──────────────────────────────────────────────────────────────────────────┤
│ flight 1   10 segments  ██████████                    total   14,600 B   │
│ flight 2   20 segments  ████████████████████          total   43,800 B   │
│ flight 3   40 segments  ████████████████████████████… total  102,200 B   │
│ flight 4   80 segments  ████████████████████████████… total  219,000 B   │
│                                                                          │
│ a 100 KB response needs 3 or 4 flights: 3 or 4 RTT after the request     │
│ a warm connection with a grown window can send it in about 1             │
└──────────────────────────────────────────────────────────────────────────┘
```

So a cold connection pays twice: the handshakes, and a small window for its first responses. A connection that sits idle longer than one retransmission timeout may lose its grown window again. RFC 5681 section 4.1 says so, and Linux does it by default, `tcp_slow_start_after_idle = 1`. It still skips the handshakes.

**What the kernel and Python set for you.** Two defaults matter:

- **Nagle's algorithm is off.** Nagle holds small writes until earlier data is acknowledged. asyncio sets `TCP_NODELAY` on every TCP transport, in `Lib/asyncio/selector_events.py` at v3.13.0, line 942. httpcore relies on it.
- **TCP keep-alive probes are off.** RFC 9293 says they must default to off and to at least two hours. This Mac reports `net.inet.tcp.keepidle: 7200000`, two hours in milliseconds. HTTP keep-alive is a different thing: httpx closes a pooled connection after 5 s idle, `keepalive_expiry=5.0` in `httpx/_config.py` at 0.28.1.

**The measurement.** On loopback a round trip is too short to see. `timeline.py` puts `netem.py` between the client and the server, with 20 ms added each way. One limit of that tool matters here. The client's kernel completes the TCP handshake with the proxy on loopback. So through the proxy, the `tcp` layer shows no round trip. The public run in E2 shows the real one. Round 1 of the TLS 1.3 run, from `runs/lab5-timeline.log`:

```
round 1 request 1 new connection total   94.9 ms = dns 0.4 + tcp 0.8 + tls 47.2 + send 0.2 + first byte 44.3 + other 1.9
round 1 request 2 warm connection total   46.0 ms = send 0.2 + first byte 44.8 + other 1.1
```

Against www.python.org, round 3 of three, from `runs/lab5-public.log`. The OS resolver had the name cached by then:

```
round 3 request 1 new connection total   25.7 ms = dns 2.1 + tcp 4.1 + tls 10.8 + send 0.2 + first byte 7.1 + body 0.4 + other 1.1
round 3 request 2 warm connection total    6.6 ms = send 0.1 + first byte 5.6 + body 0.1 + other 0.8
```

Read the public row as round trips. The warm request's first byte, 5.6 ms, is about one round trip to the nearest server of that site. The TCP connect, 4.1 ms, is one more. The cold request cost 3.9 times the warm one in that round.

**The sentence to remember:** a new connection pays one round trip for TCP before the request leaves, then a small window. A warm connection pays neither.

**The trap:** measuring an endpoint with a new client per request, as many scripts do. Each call then pays DNS, TCP and TLS. On the public run that made one call 25.7 ms instead of 6.6 ms, and the endpoint was not slower at all.

**Try this now:** run `uv run python phase05_machine/timeline.py --rtt-ms 80`. Predict the warm total and the cold total before you run it. With TLS 1.3 the warm request is about one round trip, 80 ms. The cold one is about two, 160 ms, because the proxy hides the TCP round trip.

---
## 5.3 — TLS (one more round trip, and CPU on both sides)

Why this matters: TLS adds one round trip with TLS 1.3 and two with TLS 1.2. It also costs CPU on the client and the server for every new connection. A keep-alive limit that is too low, or a new client per call, turns that per-connection cost into a per-request cost.

**Answer this first.** Your client talks TLS 1.2 to a server 40 ms away. You switch it to TLS 1.3. How much does a cold request save? Then the client turns keep-alive off, so every request opens a connection. How much more server CPU does each request cost: 10%, twice as much, or five times?

**The handshakes, side by side.** From RFC 8446, Figure 1, and RFC 5246, Figure 1:

```
┌─────────────────────────────────────┬────────────────────────────────────┐
│ TLS 1.3 full handshake              │ TLS 1.2 full handshake             │
├─────────────────────────────────────┼────────────────────────────────────┤
│ C ► ClientHello + key_share         │ C ► ClientHello                    │
│ S ► ServerHello + key_share         │ S ► ServerHello, Certificate,      │
│     {Certificate, Verify, Finished} │     ServerKeyExchange, HelloDone   │
│ C ► {Finished} + application data   │ C ► ClientKeyExchange, Finished    │
│                                     │ S ► Finished                       │
│                                     │ C ► application data               │
├─────────────────────────────────────┼────────────────────────────────────┤
│ request leaves after 1 round trip   │ request leaves after 2 round trips │
│ measured through netem, 40 ms RTT:  │ measured through netem, 40 ms RTT: │
│   tls 45.8 to 47.8 ms               │   tls 89.2 to 93.5 ms              │
└─────────────────────────────────────┴────────────────────────────────────┘
```

The measured TLS layer is one round trip for TLS 1.3 and two for TLS 1.2. The rest is handshake work in Python and in the proxy: 5.8 to 7.8 ms for TLS 1.3. So the cold request cost 94.9 to 96.2 ms with TLS 1.3, and 136.4 to 141.7 ms with TLS 1.2. The warm ones were 45.2 to 48.7 ms in both. TLS 1.3 saved one round trip on every new connection: 138.8 − 95.8 = 43 ms at the medians.

The protocol also has a 0-RTT mode, where the client sends data in its first flight. RFC 8446 section 2.3 warns that such data has no protection against replay between connections. Python's `ssl` module does not offer it, so it is not measured here.

**Resumption, and who does it.** A client that kept a session from an earlier connection can offer it again. The server can then skip the certificate and, in TLS 1.2, one round trip. `timeline.py --resume` does it with the `ssl` module, which needs the session passed in by hand. Run 2 of 3, from `runs/lab5-timeline.log`:

```
TLS 1.2: full handshake 90.7 ms, second handshake 44.9 ms, resumed=True
TLS 1.3: full handshake 45.2 ms, second handshake 46.2 ms, resumed=True
httpx, 4 new clients sharing one SSLContext: server saw 4 new TLS handshakes, 0 resumed
```

Resumption saved a round trip for TLS 1.2 and nothing measurable for TLS 1.3, which is already one round trip. httpx never resumed a session. That matches the sources: httpcore 1.0.9 and anyio 4.15.1 never pass `session=` to `wrap_bio`. So with httpx, only the connection pool avoids a repeat handshake.

**The CPU.** `timeline.py --cpu 300` sends 300 requests with a warm pool, then 300 with keep-alive off, `max_keepalive_connections=0`. It does both over HTTPS and over plain HTTP, so the TLS part can be split from the cost of a new TCP connection. Both sides count CPU time. The server's counters are read through a separate client, so the count holds exactly 300 new connections. Run 1 of 3:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Server CPU per request, 300 local requests. Run 1 of 3                   │
├──────────────────────────────────────────────────────────────────────────┤
│ https, warm pool        ███                               0.167 ms       │
│ https, keep-alive off   ██████████████████                0.894 ms       │
│ http, keep-alive off    ██████                            0.295 ms       │
│                                                                          │
│ extra per new connection: https 0.727 ms, http 0.147 ms                  │
│ so the TLS handshake alone: 0.727 − 0.147 = 0.580 ms of server CPU       │
└──────────────────────────────────────────────────────────────────────────┘
```

Across three runs, keep-alive off over HTTPS cost 2.8 to 3.1 times the client CPU and 5.3 to 6.1 times the server CPU per request. The TLS handshake alone took 0.580 to 0.672 ms of server CPU, measured as the difference between the HTTPS and the HTTP runs. The raw crypto is a small part of that. The research for this phase ran `openssl speed` on this M2. An X25519 key agreement took about 28 µs, and an ECDSA P-256 signature about 18 µs. That is about 46 µs, under a tenth of the measured handshake. The rest is Python and OpenSSL object work around each connection. That split is inferred, not profiled. An RSA-2048 signature took about 0.55 ms in the same research, so a server with an RSA certificate pays more.

**The sentence to remember:** TLS 1.3 costs one round trip and TLS 1.2 two, plus CPU on both sides. httpx pays it all again for every new connection, because it never resumes a session.

**The trap:** a keep-alive limit that is too low, or a new client per call. Nothing fails. On this laptop each request then cost the server 5.3 to 6.1 times the CPU, and the dashboard shows only "CPU went up".

**Try this now:** run `uv run python phase05_machine/timeline.py --tls-max 1.2 --repeat 3`. Predict the TLS layer before you run it: two round trips of 40 ms plus a few ms. The log shows 89.2 to 93.5 ms.

---
## 5.4 — HTTP/1.1 versus HTTP/2 versus gRPC (where head-of-line blocking lives)

Why this matters: head-of-line blocking means one slow item at the front of a line delays everything behind it. HTTP/2 is often described as the fix for it. It is not. It moves the line from the request to the TCP connection. If you do not know where the line is, you will choose the protocol for the wrong failure.

**Answer this first.** Two predictions, with a 10 ms round trip.

1. One 300 ms request and nine 5 ms requests share ONE connection. The slow one goes first, and the nine start 5 ms later. With HTTP/1.1, fast request k ends at 300 + 10 + k × 15 ms, and its latency is 5 ms less. The median, k = 5, is 380 ms. With HTTP/2, each fast request needs 5 + 10 = 15 ms.
2. Ten requests run at once. One TCP segment is lost and needs 300 ms to be retransmitted. How many of the ten wait: one, or ten? Answer for HTTP/2 on one connection, and for HTTP/1.1 with ten connections.

**Two lines, two places.**

- **HTTP/1.1** carries one request at a time per connection. httpx does not pipeline. So a slow response holds its connection, and the requests behind it wait. The fix is more connections.
- **HTTP/2** splits each request into a stream of frames. Streams interleave on one connection, so a slow response holds nothing. But all streams share one TCP byte stream, and TCP delivers bytes in order. RFC 9113, the HTTP/2 standard, says in section 1: "TCP head-of-line blocking is not addressed by this protocol". RFC 9114, HTTP/3, section 1.1, says what happens: "a lost or reordered packet causes all active transactions to experience a stall".

`h2_hol.py` shows both lines. Part 1 is the request line. Part 2 is the TCP line. `netem.py` holds all bytes of connection 1 for 300 ms. That is what a lost segment does to the application above TCP. Real packet loss needs a network emulator that needs root, so this is an emulation at the application layer. It does not model the smaller congestion window that follows a real loss.

```bash
uv run python phase05_machine/h2_hol.py --repeat 3
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Part 1, the REQUEST line: one 300 ms request first, then nine of 5 ms,   │
│ all on ONE connection, 10 ms RTT                                         │
├──────────────────────────────────────────────────────────────────────────┤
│ HTTP/1.1  [ 300 ms ][5][5][5][5][5][5][5][5][5]   one at a time          │
│           predicted median 380 ms; measured 412.1 to 434.4 ms            │
│ HTTP/2    [ 300 ms ..................... ]                               │
│           [5][5][5][5][5][5][5][5][5]            interleaved             │
│           predicted 15 ms; measured median 23.9 to 24.9 ms               │
└──────────────────────────────────────────────────────────────────────────┘
```

Both measurements sit above the model. HTTP/2 is about 9 to 10 ms above it. HTTP/1.1 is 32 to 54 ms above it, a few ms more for each request in its line. The model counts only the server's wait and the round trip. The client's own work per request and the proxy's hops are not in it. The shape holds: one line is hundreds of milliseconds, the other tens.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Part 2, the TCP line: connection 1 stalled 300 ms, 10 requests of 20 ms  │
├──────────────────────────────────────┬───────────────────────────────────┤
│ HTTP/1.1, 10 connections             │ HTTP/2, 1 connection              │
│  conn 1  ████████ stalled ███ req A  │  conn 1  ████████ stalled ███████ │
│  conn 2  ██ req B                    │          streams A B C D E F G H  │
│  ...                                 │          I J all wait             │
│  conn 10 ██ req J                    │                                   │
├──────────────────────────────────────┼───────────────────────────────────┤
│ 1 of 10 took 270 ms or more          │ 10 of 10 took 270 ms or more      │
│ median 43.2 to 43.7 ms, 3 runs       │ median 307.7 to 307.8 ms, 3 runs  │
└──────────────────────────────────────┴───────────────────────────────────┘
```

So HTTP/2 removed the request line and made the TCP line longer. Each protocol has one failure the other does not. HTTP/1.1 squeezed into ONE connection has both. The break-it run in the same log gave 10 of 10 stalled, with a median of 471.3 ms. The requests also queued behind each other.

HTTP/3 runs over QUIC, which recovers loss per stream. RFC 9000 section 13 says a lost packet blocks only the streams with data in that packet. It is not measured here.

**Where gRPC fits.** gRPC is a protocol on top of HTTP/2, so it inherits the TCP line. It adds two things you meet in production. Neither is measured here, and both come from grpc.io:

- **Flow control on streams.** The gRPC flow-control guide says it applies to streaming RPCs and is not relevant for unary ones. HTTP/2 starts every window at 65,535 bytes, RFC 9113 section 6.9.2. gRPC-Go grows its window from an estimate of the bandwidth-delay product, the bandwidth times the round trip. The gRPC-Go performance post of 2017 shows the cost of a cold connection. At a simulated 64 ms RTT, with a 1 MB request, the first RPC took 455.1 ms. The second took 195.4 ms and the third 132.2 ms. From the fourth on they took about 69 to 71 ms, about one round trip.
- **A deadline on the wire.** gRPC sends the deadline as a `grpc-timeout` header, and the server cancels the call when it passes. Section 5.7 in part B shows that HTTP/1.1 has nothing like it.

One more limit on the HTTP/2 side. httpcore 1.0.9 opens at most 100 streams per connection, or fewer if the server says so. The setting is `MAX_CONCURRENT_STREAMS: 100` in `httpcore/_async/http2.py`. Inferred from the code, not run.

**The sentence to remember:** HTTP/1.1 blocks behind a slow request on its connection. HTTP/2 blocks every stream behind a lost packet. Choose by the failure you have.

**The trap:** moving a client to HTTP/2 over one connection on a lossy path, to fix slow requests. The slow-request line goes away, and each loss now stalls every call. Here one 300 ms stall delayed 10 of 10 requests instead of 1.

**Try this now:** run `uv run python phase05_machine/h2_hol.py --repeat 1 --h1-connections 1`. Predict both parts before you run it. HTTP/1.1 with one connection shows the request line and the TCP line together.

---
## 🧪 Hands-on lab — part A

**Run status:** every command below was executed on the author's machine on 2026-09-25. It is an Apple M2 with 8 GB and macOS 15.7.8, CPython 3.13.3 through uv. Other programs ran at the same time, load average 3.7 to 4.8 at the start of each log. Each "Expected" line is copied from `runs/lab5-*.log`. Your milliseconds will differ. The ratios and round-trip counts should not.

All commands run from `elite-performance/code/`. `bash runs/lab5.sh T N H` runs the local parts of this document and saves the logs. `bash runs/lab5.sh P` runs E2 against the public site. Every script starts its own servers on free ports and stops them.

- [ ] **E1 (local).** One request, layer by layer. This is the phase's first demonstration: a breakdown that sums to the measured total.
  - Run: `uv run python phase05_machine/timeline.py --repeat 3`.
  - Expected: a cold row such as `total   94.9 ms = dns 0.4 + tcp 0.8 + tls 47.2 + send 0.2 + first byte 44.3 + other 1.9`, a warm median of `47.0 ms`, `cold / warm total: 2.04x`, and `largest unexplained share ('other' / total) of any request: 5.2%`.
  - "other" is what no layer claims: taking a connection from the pool and Python's own work. The sum is exact by construction. So the check is that "other" stays small.
  - If "other" is large on the first request only: that is the first outbound call in a new process. The script measures it apart: `process warm-up ... 25.2 ms`. It imports anyio's backend and starts the default thread pool.
  - Teaches: a cold request pays TLS and one more round trip. A warm one pays only the request.

- [ ] **E2 (live).** The same against a real site. Costs at most: 9 small HTTPS requests, about 5 KB of bodies, plus three TLS handshakes.
  - Run: `uv run python phase05_machine/timeline.py --public https://www.python.org/robots.txt --repeat 3`.
  - Expected: round 1 paid `dns 17.1` ms, the first lookup of that name. Rounds 2 and 3 paid `dns 1.3` and `dns 2.1`, from the OS cache. Cold totals `34.6` and `25.7` ms in rounds 2 and 3. Warm first bytes 5.0 to 9.0 ms. `cold / warm total: 4.64x`.
  - Round 1 also waited `first byte 257.2` ms on its first request. That was the site, not a layer of the connection. The cause was not checked.
  - Teaches: TCP connect and a warm first byte are each about one round trip. Only the first lookup of a name pays the network.

- [ ] **E3 (break-it, local).** Starve the pool that DNS needs.
  - Run: `uv run python phase05_machine/dns_starve.py --repeat 3`, then `uv run python phase05_machine/dns_starve.py --jobs 11`.
  - Expected: `default executor 12 threads`. Idle lookup 0.31 to 0.32 ms. Starved lookup 948.76 to 958.22 ms. A request on a warm connection 1.43 to 1.53 ms, on a new one 960.78 to 964.53 ms. After the timeouts, 848.02 to 852.62 ms. With 11 jobs: `starved pool, lookup  0.55 ms`.
  - If it fails: on a machine with a different core count the pool has another size. The first line prints it. Pass that number with `--jobs`.
  - Teaches: a lookup waits for a thread first, and a timeout does not return the thread.

- [ ] **E4 (local).** TLS 1.2 against 1.3, and resumption.
  - Run: `uv run python phase05_machine/timeline.py --tls-max 1.2 --repeat 3`, then `uv run python phase05_machine/timeline.py --resume`.
  - Expected: `tls 91.3` ms at the median for TLS 1.2 against `tls 47.2` for TLS 1.3. Resume: `TLS 1.2: full handshake 90.7 ms, second handshake 44.9 ms, resumed=True`, and `httpx, 4 new clients sharing one SSLContext: server saw 4 new TLS handshakes, 0 resumed`.
  - Teaches: round trips per handshake, and that httpx never resumes, so only the pool saves the handshake.

- [ ] **E5 (break-it, local).** Turn keep-alive off and price it.
  - Run: `uv run python phase05_machine/timeline.py --cpu 300`.
  - Expected: `https warm pool ... 0 new connections ... server CPU 0.167 ms/request` and `https keep-alive off ... 300 new connections, 300 TLS handshakes ... server CPU 0.894 ms/request`. Then `server CPU of the TLS handshake alone ... 0.580 ms per connection`. Over three runs: 5.3 to 6.1 times the server CPU, and 0.580 to 0.672 ms for the handshake.
  - Teaches: a pool that closes connections moves the handshake cost onto every request.

- [ ] **E6 (local, then break-it).** Where head-of-line blocking lives.
  - First write down your two predictions from section 5.4.
  - Run: `uv run python phase05_machine/h2_hol.py --repeat 3`, then the same with `--repeat 1 --h1-connections 1`.
  - Expected: `PREDICT request line: HTTP/1.1 fast median 380 ms`. Measured, HTTP/1.1 fast median `412.1` to `434.4 ms`, HTTP/2 `23.9` to `24.9 ms`. TCP line, `1 of 10 took 270 ms or more` on HTTP/1.1 with 10 connections, `10 of 10` on HTTP/2. With one HTTP/1.1 connection: `10 of 10`, median `471.3 ms`.
  - Teaches: HTTP/2 moves the line from the request to the TCP connection.

---

## 🔍 Check it yourself

1. Open `phase05_machine/timeline.py:95`. This is `hook_dns`. It replaces `getaddrinfo` on the loop instance, at line 111. Why must the DNS time be subtracted from `connect_tcp`, at line 119, instead of shown next to it? The self-test slows every lookup by 30 ms and checks that `dns` shows it and `tcp` does not. What would that check see if the subtraction were removed?

2. Open `phase05_machine/netem.py:93`. Every chunk of link 1 compares its time with `stall_until`, so all of them wait until the stall ends. The single queue keeps the bytes in order. Suppose each chunk had its own task instead. What would the HTTP/2 client see, and why?

3. Open `phase05_machine/dns_starve.py:60`. This is `CachingResolver`. Its TTL is fixed, because `getaddrinfo` returns none. Think of the AWS event above. How would a TTL of 30 s and a TTL of 1 hour each change a client's recovery after 2:25 AM?

4. In any service you own, run:

   ```bash
   grep -rnE "to_thread|run_in_executor\(None|max_keepalive_connections|keepalive_expiry|http2=True" <your repo>/
   ```

   For every `to_thread` in a process that also makes outbound calls, name the executor it shares with DNS. For every client setting, say how often a new TLS handshake happens at your real request rate.

---

## ✅ Checkpoint 5A — answer in your own words

1. **Explain, with the round trips counted.** Walk through a cold HTTPS request from `client.get("https://api.example.com/x")` to the first byte of the response. The name is not cached. The resolver is 5 ms away and the server 30 ms away. It uses TLS 1.3, and the server takes 10 ms. Count the round trips and give the total. Then do it for TLS 1.2, and for a warm connection.

2. **This is broken.** An asyncio service's p99 rises from 80 ms to 1.1 s every night at 02:00. The downstream service's own metrics are flat. The client's traces show the time in "connect". A batch job starts at 02:00 in the same process and reads 40 files through `asyncio.to_thread`. The service runs on an 8-core node. What is the cause, how do you confirm it from metrics you already have, and what do you change?

3. **A colleague says:** "Our gateway calls the payments service over one HTTP/2 connection now. Head-of-line blocking is solved." The path has 0.5% packet loss at peak. Argue for or against, with numbers from section 5.4.

4. **Show the arithmetic.** A service makes 50 calls per second to a partner 60 ms away, TLS 1.2. Its httpx client is created per request. (a) How much wall time per call goes to handshakes? (b) Using this lab's measured ratio, how much more server CPU per call does the partner spend than with a warm pool? (c) What changes if the client is shared but calls come every 6 s?

5. **Given these constraints, design** the DNS behaviour of a Python client that calls 20 hosts. The platform wants no request to wait more than 50 ms for DNS. A moved service must be reachable within 60 s. State where the lookup runs, what caches it and for how long, and what you alert on.

6. **Walk through what happens** during the AWS DynamoDB event to two clients. Client A holds a warm pool and makes a request every second. Client B creates a new connection per request. Which one fails first, which one recovers first after 2:25 AM, and what does the summary not tell you?

<details>
<summary>Answer sketches</summary>

1. DNS: 1 round trip to the resolver, 5 ms. TCP: 1 RTT, 30 ms. TLS 1.3: 1 RTT, 30 ms. Request and response: 1 RTT plus 10 ms, 40 ms. Total about 105 ms, 3 round trips to the server. TLS 1.2 adds 1 RTT: about 135 ms. Warm connection: 1 RTT plus 10 ms, 40 ms. The slow-start window adds flights only for responses above about 14.6 KB.

2. The 40 blocking jobs hold all 12 threads of the default thread pool, so every `getaddrinfo` for a new connection waits for a thread. Section 5.1 measured 958 ms for a lookup that needs 0.3 ms. Confirm: the connect time rises only for requests that open a connection. Warm-connection requests stay fast, and the rise starts with the batch job. Fix: give the batch job its own `ThreadPoolExecutor`, or move it to its own process. A bigger default thread pool only moves the limit.

3. Against, as stated. HTTP/2 removed the request line. In section 5.4, nine fast calls took 23.9 to 24.9 ms beside a slow one, against 412 to 434 ms on one HTTP/1.1 connection. But a loss now stalls every stream on the connection. 10 of 10 calls waited for a 300 ms stall, against 1 of 10 with 10 HTTP/1.1 connections. At 0.5% loss, many calls in flight share each loss. Use several HTTP/2 connections, or HTTP/3 where it exists, and measure the p99 during loss.

4. (a) TCP 1 RTT + TLS 1.2 2 RTT = 3 × 60 = 180 ms per call. (b) This lab measured 5.3 to 6.1 times the server CPU per request with keep-alive off. The partner's own ratio depends on its certificate and stack, so measure it. (c) httpx closes an idle connection after 5 s, `keepalive_expiry=5.0`. At one call every 6 s, every call opens a connection again. Raise `keepalive_expiry` above the gap. It must stay below the idle timeout of the server and of any load balancer between. Otherwise the client reuses a connection the other side has just closed.

5. Keep lookups in the default thread pool, and move blocking work out of it into its own executor. Cache answers in the process. Refresh each cached name in the background before its TTL ends, and serve the old answer while the refresh runs. Then no request waits on the resolver. A TTL of at most 60 s bounds how long a moved service stays unreachable. Warm connections keep their old address, so also set a maximum connection age under 60 s. Bound a cold lookup with a timeout, and alert on lookup time per new connection and on new connections per second.

6. B fails first: every request needs a lookup, and the record was empty from 11:48 PM. A needs a lookup only when a connection is replaced, for example after an idle close or an error. After 2:25 AM, recovery waited for cached answers to expire, "as cached DNS records expired", so a client with a long cache recovers last. The summary does not say whether open connections kept working, so A's fate during the event is not known from it.

</details>

---

## References & Further Learning — part A

Every URL below was fetched on 2026-09-25 and returned HTTP 200.

**DNS in Python, and the incident**

- **CPython `Lib/asyncio/base_events.py` at v3.13.0** — https://raw.githubusercontent.com/python/cpython/v3.13.0/Lib/asyncio/base_events.py
  Focus on: `getaddrinfo`, lines 928 to 936, which calls `run_in_executor(None, ...)`, and `_set_nodelay`. Section 5.1 starts here.
- **CPython `Lib/concurrent/futures/thread.py` at v3.13.0** — https://raw.githubusercontent.com/python/cpython/v3.13.0/Lib/concurrent/futures/thread.py
  Focus on: line 145, the default `max_workers`.
- **Python 3.13 docs, "Event loop"** — https://docs.python.org/3.13/library/asyncio-eventloop.html
  Focus on: the note under `getaddrinfo` about a saturated executor and its two fixes, and the TCP_NODELAY change note.
- **resolv.conf(5), Linux man-pages** — https://man7.org/linux/man-pages/man5/resolv.conf.5.html
  Focus on: `timeout:n`, default 5, and `attempts:n`, default 2. Read it before you trust a lookup timeout inside a container.
- **AWS, "Summary of the Amazon DynamoDB Service Disruption in the Northern Virginia (US-EAST-1) Region"** — https://aws.amazon.com/message/101925/
  Focus on: the DynamoDB section: the planner and enactor, the stale check, and recovery "as cached DNS records expired". A production postmortem with times, from the operator itself.

**TCP and TLS**

- **RFC 9293, TCP** — https://www.rfc-editor.org/rfc/rfc9293.txt
  Focus on: section 3.5, the three-way handshake, section 3.7.4 on Nagle, and section 3.8.4 on keep-alive defaults.
- **RFC 5681, TCP Congestion Control** — https://www.rfc-editor.org/rfc/rfc5681.txt
  Focus on: section 3.1, slow start, and section 4.1, the restart after idle.
- **RFC 6928, Increasing TCP's Initial Window** — https://www.rfc-editor.org/rfc/rfc6928.txt
  Focus on: the formula for 10 segments. Its category is Experimental, and deployed kernels use it anyway.
- **RFC 8446, TLS 1.3** — https://www.rfc-editor.org/rfc/rfc8446.txt
  Focus on: Figure 1, the one-round-trip handshake, and section 2.3 on 0-RTT replay.
- **RFC 5246, TLS 1.2** — https://www.rfc-editor.org/rfc/rfc5246.txt
  Focus on: Figure 1, the two-round-trip handshake. Compare it with E4.
- **Python 3.13 docs, "ssl"** — https://docs.python.org/3.13/library/ssl.html
  Focus on: `SSLSocket.session` and `wrap_bio(..., session=None)`. A client resumes only when its code passes a session.

**HTTP/2, HTTP/3 and gRPC**

- **RFC 9113, HTTP/2** — https://www.rfc-editor.org/rfc/rfc9113.txt
  Focus on: section 1, the TCP head-of-line sentence, and sections 6.5.2 and 6.9.2, the 65,535-byte windows and the stream limit.
- **RFC 9114, HTTP/3** — https://www.rfc-editor.org/rfc/rfc9114.txt
  Focus on: section 1.1, why a lost packet stalls every HTTP/2 stream.
- **RFC 9000, QUIC** — https://www.rfc-editor.org/rfc/rfc9000.txt
  Focus on: section 13, loss per stream, and its own limit when one packet carries several streams.
- **httpcore `_async/http2.py` at 1.0.9** — https://raw.githubusercontent.com/encode/httpcore/1.0.9/httpcore/_async/http2.py
  Focus on: the local settings with 100 streams, and the 2^24 receive windows.
- **gRPC blog, "gRPC-Go performance Improvements", 2017** — https://grpc.io/blog/grpc-go-perf-improvements/
  Focus on: the table "Network with RTT of 64ms", gRPC column: 455.1, 195.4 and 132.2 ms for the first three RPCs. Written for gRPC-Go of 2017, so check today's defaults.
- **gRPC guide, "Flow Control"** — https://grpc.io/docs/guides/flow-control/
  Focus on: which RPCs flow control applies to.

---

## Cheatsheet — part A

```
THE COLD REQUEST, IN ROUND TRIPS TO THE SERVER
  DNS          0 if cached, else 1 to the resolver. Python caches nothing
  TCP          1        (kernel; hidden behind netem.py on loopback)
  TLS 1.3      1        measured 45.8 to 47.8 ms at 40 ms RTT
  TLS 1.2      2        measured 89.2 to 93.5 ms at 40 ms RTT
  request      1 + server time
  cold 94.9 ms vs warm median 47.0 ms locally; public 25.7 vs 6.6 ms
  slow start   window 10 x 1,460 B, doubles per RTT: 100 KB = 3-4 flights

DNS IN ASYNCIO
  path         anyio -> loop.getaddrinfo -> default thread pool, 12 here
  starved      12 x 1 s to_thread jobs: lookup 0.3 ms -> 958 ms
  11 jobs      one thread free: 0.55 ms
  warm conn    no lookup, unaffected; and never follows a DNS change
  timeout      frees the coroutine, never the thread
  fix          own ThreadPoolExecutor for blocking work; cache with a TTL
  glibc        timeout 5 s, attempts 2 -> a dead server ~10 s per lookup
  anyio        happy_eyeballs_delay 0.25 s before the next address

TLS COSTS
  httpx        never resumes a session: only the pool saves a handshake
  keep-alive off  client CPU 2.8-3.1x, server CPU 5.3-6.1x per request
  handshake    0.58-0.67 ms server CPU here; raw crypto ~46 µs of it

HEAD-OF-LINE BLOCKING
  HTTP/1.1     slow response blocks its connection   -> more connections
  HTTP/2       lost packet blocks every stream        -> 10 of 10 stalled
  HTTP/3       loss per stream (QUIC), not measured here
  gRPC         HTTP/2 + stream flow control + grpc-timeout deadline
```

Part B covers the host under the request. It sizes the pool from Little's law, prices the page cache and fsync, and follows a deadline through the stack. It ends with the container's CPU quota, and one induced failure named from metrics alone.

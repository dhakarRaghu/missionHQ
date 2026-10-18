Your team works on a B2B SaaS platform. About 34 services share several Redis clusters on Amazon ElastiCache, and your service is one of them. You are adding an AI grading service. A learner submits a roleplay answer, and the service grades it against 40 rubric items. It reads the rubric from Redis, counts LLM calls per company, and caches each result.

The platform's past incidents show why the details of Redis matter. In each of the three below, Redis did what it was built to do. The engineers' picture of Redis was what was wrong.

- An LLM gateway wrote keys with no expiry time to a shared cluster. Memory reached 100%, and an upload service on the same cluster was down with it for 4 hours 37 minutes.

- A serializer marked API responses as not cacheable. Every read then missed the cache, so about 300 requests a minute to the settings API became about 30,000.

- A client assumed two replicas in every environment. In staging, that assumption added 2 seconds of latency to its calls.

This lesson follows your grading service through five ideas about Redis. Each idea would have prevented one failure of this kind. The later phases use the same platform, and each one names its own example at its start.

### What you must know

- **One main thread runs every command and the housekeeping, so one slow command delays every client.** Explain a cluster-wide latency spike and find its cause.

- **The round trip, not the command, is the cost. Batching removes round trips, up to a fixed ceiling.** Estimate the latency of a call path and fix it with batching.

- **One command or one script runs with nothing in between. Two separate commands can be interleaved.** Tell which Redis code can race, and make it safe.

- **At the memory limit the eviction policy decides who fails. Under volatile-lru, keys without a TTL never leave.** Predict who fails when a shared cluster fills up.

- **Redis keeps the primary copy in RAM, so a lost cache entry costs latency and a lost lock costs money.** Decide what may live in Redis and what needs a durable store.

## What does one Redis process do with thousands of clients?

Your grading service opens connections to the primary node of its cluster, and so do 33 other services. All of their commands arrive at one process on that node.

A Redis server is one process that holds all its data in memory. One *main thread* runs every command, one at a time, from start to end. It serves all clients from one *event loop*, a loop that waits until some sockets have data, serves them, and then waits again. The data needs no locks, because no second thread ever runs a command on it.

1. **wait for sockets** The thread sleeps until some clients have sent data.

1. **read up to 16 KB** One read call takes what one client has sent.

1. **run each command** Every complete command in that buffer runs to the end, one after another.

1. **queue the replies** Each reply waits in its client's reply buffer.

1. **before sleeping** The thread writes all queued replies and does some housekeeping.

**Predict: Redis 8 runs with 8 I/O threads, which handle socket work. One client sends a command that takes 350 ms. One millisecond later, a GET arrives from a different pod on a different host. About how long does the GET wait?**

About 349 ms. An I/O thread can read and parse the GET, but only the main thread can run it. The main thread is busy with the long command until it ends. A different pod, host or connection does not help, because every command shares that one thread. Most engineers guess "almost no time", because they picture eight threads that each run commands.

### One turn of the loop

1. The main thread waits in `epoll_wait`, or `kqueue` on macOS, until some sockets have data. The wait ends early when a timer is due.

1. For each ready client, it reads up to 16 KB from the socket in one call. So one read can carry many small commands.

1. It runs every complete command in that buffer, one after another, through the function `processCommand`.

1. A GET is one lookup in a hash table. On a laptop it took 0.27 µs of server time.

1. The reply goes into the client's 16 KB reply buffer, and the client joins a list of clients with replies to send.

1. Before the next wait, the function `beforeSleep` writes those replies. It also runs a short expiry pass and writes the append-only file buffer to disk.

### What I/O threads change, and what they do not

*I/O threads* are extra threads that read sockets, parse commands and write replies. They are off by default, because `io-threads` defaults to 1. With more of them, the main thread spends less time on socket work, so one instance serves more requests a second. An I/O thread never runs a command. A comment in the Redis code says so: "If we are in the context of an I/O thread, we can't really execute the command here." The I/O thread hands the parsed command back to the main thread.

The gain from I/O threads is large. With 8 I/O threads, Valkey 8 served 1.19 million requests a second, where Valkey 7.2 served 360,000 on the same AWS instance. That result also includes a second change, which prefetches each command's keys from memory before the main thread runs it. Every one of those commands still ran on one main thread.

**Evidence**

Redis source at tag 8.10.2: `src/networking.c:3840-3845` holds the comment quoted above and queues the client back to the main thread. Valkey blog, "Unlock one million RPS", 2024-08-05: "from 360K to 1.19M requests per second compared to Valkey 7.2". Conditions: 8 I/O threads, 3 million keys, 512-byte values, 650 clients sending SET, AWS EC2 c7g.16xlarge. The blog says these numbers include the prefetch change. The 0.27 µs is `usec_per_call` for GET in `INFO commandstats`, measured on an Apple M4 Pro. The server was an x86_64 Homebrew build of Redis 8.10.1 under Rosetta 2, outside Docker. Rosetta 2 is the macOS layer that runs an x86_64 program on the arm64 chip of the Mac. The run used `io-threads 1` and no persistence. Client and server ran on the same host over TCP loopback, with Go 1.27.1 and go-redis v9.5.1. Later sections call this setup "the local run".

The phase said that I/O threads arrived in Redis 6.0 as an option for reads and writes. That is out of date. Redis 8.0 has a new I/O threading design, and `io-threads-do-reads` is in its list of deprecated settings. With `io-threads` above 1, the threads always read and parse as well. Valkey 8 also moved `epoll_wait` and memory freeing to I/O threads. Checked at Redis 8.10.2 and Valkey 9.1.2.

### Housekeeping runs on the same thread

The main thread also does the server's own work between commands. While it does that work, no command runs.

- **Active expiry.** A key can have a *TTL*, a time to live after which Redis deletes it. A timer samples keys with a TTL and deletes the expired ones. Many keys that expire in the same second can block the server.

- **Eviction.** When memory is full, Redis removes keys before it runs a write. The section on memory explains who loses keys and what that costs.

- **Snapshots.** To save its data to disk, Redis calls `fork()`. The fork runs on the main thread, so on a large instance it can pause every client.

This design explains what Redis is good at. Each command is atomic, so counters, rate limits and locks become single commands or short scripts. Each command is also cheap, so one instance can serve many services at once. The price is the shared queue, because anything slow on the main thread is slow for every client.

**Go deeper: the loop in the source, timers, the two I/O thread designs and the data types**

**The loop at tag 8.10.2.** One turn of `aeProcessEvents` runs `beforeSleep`, then the poll, then the read handlers, then the write handlers, then the timers. `readQueryFromClient` reads `PROTO_IOBUF_LEN` bytes, defined as `(1024*16)` in `src/server.h:190`. `processInputBuffer` in `src/networking.c:3690` loops while the buffer holds complete commands, and passes each to `processCommandAndResetClient`. `beforeSleep` starts at `src/server.c:1947`. It runs the fast expiry cycle at line 2009 and writes the pending replies with `handleClientsWithPendingWrites()` at line 2104.

**Timers.** `serverCron` runs `hz` times a second. The default is 10, and the range is 1 to 500. With `dynamic-hz yes`, the default, Redis doubles `hz` while there are more than 200 clients per tick. `serverCron` runs client timeouts, buffer resizing, the slow expiry cycle and rehashing. It also starts snapshots and rewrites, and it runs replication work every 1000 ms and cluster work every 100 ms.

**Redis 8 I/O threads.** Each I/O thread owns a set of clients and runs its own event loop. A new client goes to the thread with the fewest clients. Clients pass between the main thread and the I/O threads in batches. A batch goes when it reaches 16 clients, or at the end of a loop turn. Some clients always stay on the main thread: pub/sub clients, `MONITOR` clients, blocked clients and tracking clients. `io-threads` can be at most 128, and you cannot change it while the server runs.

**Valkey 9.1 I/O threads.** The main thread owns every client. It puts read, write, poll and free jobs on lock-free queues. All I/O threads share one queue, and each thread also has a private queue. The first I/O thread starts when the main thread is busy more than 30% of the time. More threads start while, on average, more than one job waits in the shared queue. Threads stop one at a time, when the queue is empty and 1000 ms have passed since the last change. In Valkey, `io-threads` can change at runtime. Before this offload, `epoll_wait` alone used more than 20% of the main thread's time.

**ElastiCache.** AWS added its own I/O multiplexing to ElastiCache for Redis 7.0. At 5,200 clients, throughput rose from 202,770 to 349,239 operations a second, a 72% gain. At 400 clients the gain was 26%. At 142,000 requests a second, p99 fell from 8.3 ms to 2.45 ms. In ElastiCache 7.1 the I/O threads also parse commands and format replies. AWS claims over 1 million requests a second per node on r7g.4xlarge or larger.

**Why one thread.** The Redis FAQ gives the reason: "usually Redis is either memory or network bound". So CPU is rarely the limit, and more command threads would add locks for little gain. The phase also credited a calculation by the creator of Redis. It gave no source, so this lesson leaves it out.

**Background threads.** Some slow work already runs off the main thread: freeing large values after `UNLINK`, closing files and the AOF fsync. Command execution does not.

**The fork pause.** The Redis latency page says "The fork operation (running in the main thread) can induce latency by itself." Its table of fork times runs from about 9 ms to a few hundred ms per GB of data, by platform. So a 20 GB instance on a slow platform can pause for seconds at each snapshot.

**The data types.** Redis stores typed structures, each with its own commands. Memcached stores opaque values only. Phase 1 teaches each type in depth. Here is the map, with a use from the running case's platform:

| Type | Core commands | A use on the platform |
|---|---|---|
| String | `GET SET SETNX INCR EXPIRE` | a generated buyer-persona cache with a 3-day TTL |
| Hash | `HGETALL HSET HDEL` | session records in the login service |
| Set | `SMEMBERS SADD SREM` | session index sets and access-scope keys |
| List | `RPUSH LPOP LTRIM` | a FIFO work queue for analytics events |
| Sorted set | `ZADD ZREM ZRANGEBYSCORE` | markers for translation jobs in progress |
| Pub/Sub | `PUBLISH SUBSCRIBE` | dispatch messages for content sync |
| Streams, HyperLogLog | `XADD XREADGROUP`, `PFADD PFCOUNT` | not used in the core services |

The phase's list of types ended at streams, HyperLogLog and geo. Redis 8.0 added JSON, time series, Bloom, Cuckoo, Count-min, Top-k, t-digest, vector sets as a beta, and the Query Engine to the core server.

**A server that is mostly idle.** Stack Overflow ran its cache on 2 physical Redis servers per data center. They carried about 1.59 billion commands a day, with a peak of 86,982 a second, at 2.01% average CPU. The main thread had plenty of time left, and the clients' round trips were the cost they paid. The section on round trips comes back to that cost.

**Evidence**

Source lines: Redis tag 8.10.2, files named above. The Redis 8 I/O thread rules come from `src/iothread.c`, in `isClientMustHandledByMainThread` and `assignClientToIOThread`, and from `src/config.c:3507`. Valkey 9.1.2 `src/io_threads.c` and `src/config.c:3385`, and the Valkey blog post linked in the sources. AWS blogs "Enhanced I/O multiplexing for ElastiCache for Redis 7", 2023-02-08, conditions r6g.xlarge, 80% GET and 20% SET, 3 million keys, 512-byte values, client in the same AZ, and "Achieve over 500 million requests per second per cluster with ElastiCache for Redis 7.1", 2023-11-14. Redis 8.0.0 release notes, published 2025-05-02. Stack Overflow numbers from Nick Craver, "How We Do App Caching - 2019 Edition", measured 2019-07-30.

You now have the picture of one thread with one queue of commands. The next section asks what happens to every other client when one command in that queue runs long.

## What happens to every other client when one command is slow?

The main thread runs one command at a time, so a long command makes every later command wait. One afternoon the p99 latency of your grading service jumps. The p99 is the latency that 99% of requests stay under, and the p50 is the median. The p99 of three other services on the same cluster jumps in the same minute, and nobody deployed anything.

This is *head-of-line blocking*: the command at the front of the queue takes long, so every command behind it waits. The waiting commands can come from any client and any service. A separate connection, a separate pod or a separate host does not help, because the queue is the main thread itself.

**One KEYS command on a shared cluster.**

Step 1: your GET runs in under a microsecond of server time and returns.

Step 2: another service sends KEYS *, and the main thread walks every key for about 350 ms.

Step 3: KEYS returns, and the queued commands run in a burst.

Step 4: each queued client saw about 350 ms plus its own round trip.

Timing from the local run of KEYS on 4 million keys. The other widths are drawn to show order, not measured.

### Why your GET waits

1. Another service sends `KEYS *`. The main thread starts to walk all 4,000,000 keys, and it cannot stop until the walk ends.

1. Your GET arrives on its own connection from its own pod. The kernel holds its bytes in the socket buffer, because the main thread is not reading.

1. After about 0.35 s, `KEYS` returns. The main thread reads the waiting sockets and runs their commands one by one.

1. Your GET ran in under a microsecond, but your service measured 0.35 s, because the time it waited counts in your latency.

On the local run, `KEYS *` over 4,000,000 keys took 346,810 to 370,678 µs across four runs. While a loop ran `KEYS *` five times, another connection sent 30,000 GETs one after another. Their p50 was 94 µs and their p99 was 181 µs. Their maximum was 358.6 ms, which is one whole `KEYS` run.

The p99 did not move in that test, because only 5 of the 30,000 GETs met a stall. In production many clients are in flight at the same moment, so all of them would wait at once. That part is inferred, not measured. That is the signature to remember. Every service on the cluster shows a p99 spike in the same minute, Redis CPU is high, and nothing was deployed.

**Evidence**

Measured on the local run described in the first section: `DEBUG POPULATE 4000000`, then `KEYS *` timed in `SLOWLOG`, four runs. `KEYS key:*` over 1,000,000 keys took 92,618 to 93,575 µs across three runs. The concurrent-client effect on p99 is inferred from the single-client probe. A check would be 50 concurrent probes. The Redis KEYS page is faster: "an entry level laptop can scan a 1 million key database in 40 milliseconds". The local build used `malloc=libc`, which may explain the gap. That was not checked. Phase 5 timed `KEYS k:*` over 1,000,000 keys at 133 to 148 ms on the same build. The key names and the way the keys were created may differ, and this page does not record it.

The phase's timeline said that `KEYS *` over 4 million keys takes about 2 seconds. On Redis 8.10.1 it took 0.35 to 0.37 s, and the docs give 40 ms per million keys. The 2-second stall in the lab comes from `DEBUG SLEEP 2`, which is a different command.

### A real case: KEYS on a hot path

**Harness** saw its Feature Flag service stop answering. A synthetic check failed first. Then admin server pods restarted, SDK requests got 502 errors, and Redis CPU was at 100%. The cause was a CDN feature that called `KEYS` with a pattern on a hot path. Load tests had used a few thousand keys, but the live cache held a few hundred thousand. At the daily peak, each `KEYS` passed the client timeout. Their own root-cause analysis shows the wrong belief: "Redis v6 is multi-threaded and can perform operations concurrently." The fix replaced `KEYS` with a call that completes in O(1) time. The outage lasted 14 minutes.

**Evidence**

Harness status page, "Feature Flag services is not responding", 2023-09-21, read as JSON with the postmortem body. Downtime 14:32 to 14:46 UTC. The postmortem says the same issue had also occurred "on Friday 15th".

### Commands that hold the thread

| Command | Why it is slow | Use instead |
|---|---|---|
| `KEYS pattern` | walks every key in the database | `SCAN` with a cursor, a few keys per call |
| `SMEMBERS`, `HGETALL`, `LRANGE 0 -1` on a huge key | cost grows with the number of elements | `SSCAN`, `HSCAN`, or `LRANGE` in pages |
| a long Lua script or Function | runs as one atomic step on the thread | smaller scripts, or move the loop to the client |
| `FLUSHALL` or `FLUSHDB` on a large dataset | frees every value on the thread | `FLUSHALL ASYNC` |
| `DEL` of one enormous key | frees every element on the thread | `UNLINK`, which frees in the background |

A key whose element count grows without limit is called a big key. It is a common way for an O(N) command to turn slow long after launch. The phase on performance shows how to find big keys with `redis-cli --bigkeys`.

The phase said to use `UNLINK` instead of `FLUSHALL`. The right replacement is `FLUSHALL ASYNC`, available since Redis 4.0. Since 6.2, the setting `lazyfree-lazy-user-flush yes` makes the async form the default, but Redis 8.10.2 still ships it as `no`. Valkey 9.1.2 ships every `lazyfree-lazy-*` setting as `yes`, so there `DEL` and `FLUSHALL` already free in the background.

**Go deeper: two more cases, the dev-sized test and the phase's 2-second demo**

**Trello** was slow in three bursts of one to two minutes, and then fully down for 7 minutes. The cause was "a Redis function, used primarily for debugging purposes", which had shipped to production for an internal tool. It slowed the cluster until the cluster failed over. Non-production caches held less data, so tests did not show it. The fix was to "block the use of the offending Redis command as well as other debugging commands in production." The postmortem does not name the command. Redis tags `KEYS` and `FLUSHALL` with the ACL category `@dangerous`, so an ACL rule such as `-@dangerous` is one way to block them. That rule was not tested here.

**Spring Data Redis** had a cache-clear method that called `KEYS`. On one production Redis, it pushed CPU to 100%, and the server stopped serving other requests. `SLOWLOG` showed the `KEYS` calls.

**The dev-sized test.** A command that is fast on a dev dataset of 1,000 keys can be slow on a production keyspace of 40 million. O(N) grows with the data, and test data rarely grows with production. Harness and Trello both shipped a command that their smaller test data did not show as slow.

**The platform's shared clusters.** On the platform in the running case, each shared cluster served dozens of services. So one bad command from one service slowed all of them. The phase's timeline showed the same picture. Clients A, C and D waited behind client B's `KEYS *`, and each saw the full stall as its own latency.

**The lab's 2-second stall.** The lab program `blocking_demo` sends fast GETs on one connection and `DEBUG SLEEP 2` on another. On the phase author's machine, warm-up GETs peaked near 600 µs, and one GET then took 2.002984042 s. On the local run, warm-up peaked at 336 µs, and the blocked GET took 2.0007 s. The two clients used two TCP connections, so the wait happened in the server's command loop, not in the client.

**Evidence**

Trello status page, "Trello is slow or unavailable", 2022-08-17, read as JSON with the postmortem body: slow bursts from 16:39 UTC, full outage 16:56 to 17:03 UTC, 24 minutes to resolve. Spring Data Redis issue 1413, opened 2018-05-22. ACL categories from the KEYS and FLUSHALL doc pages.

You now know why all the services slowed at once. The next section asks how you find the command that did it. It also asks why a stall of 0.35 s can become an outage of 14 minutes.

## How do you find the slow command, and when does a stall become an outage?

A slow command delays every client, so the first job in an incident is to find that one command. The second job is to make sure your service survives the next stall.

Redis records slow commands itself. *SLOWLOG* is a list inside the server of commands whose run time passed a threshold. Its time covers only execution, so it shows the cause of a stall and never its victims. The victims show up at the clients, as latency that the client measures.

- **Did every service on the cluster slow down in the same minute?**

- yesRun `SLOWLOG GET 10` and look for one long command.

- noLook at your own client first: its pool, its timeouts, its number of round trips.

- **Is SLOWLOG empty, but every client still slow?**

- yesCheck memory and eviction, the fork for snapshots, and the host with `--intrinsic-latency`.

- noThe listed command is your cause. Find which service sends it.

### What each tool shows, and what it misses

1. `SLOWLOG GET 10` lists the last ten commands that ran longer than `slowlog-log-slower-than`. The default threshold is 10000 µs, which is 10 ms. The list keeps `slowlog-max-len` entries, 128 by default.

1. The SLOWLOG docs say the time "does not include I/O operations like talking with the client, sending the reply". So your waiting GET from the last section never appears there, and only the `KEYS` does.

1. `redis-cli --latency` is a live latency meter that measures from the client side. So it does show the waits.

1. `INFO commandstats` gives `usec_per_call` for each command type. It is server time only, like SLOWLOG.

1. The latency monitor, which records latency spikes inside the server, is off by default. On Redis 8.10.1, `latency-monitor-threshold` returned 0.

1. `redis-cli --intrinsic-latency`, given a number of seconds, runs on the Redis host and measures the latency of the host itself. It measures the host apart from Redis and the network, so it can show a noisy virtual machine.

### Your client decides whether a stall becomes an outage

A stall of 0.35 s is a slow request. It becomes an outage when the clients react to it badly. Harness had two such reactions. Their Kubernetes liveness probe checked Redis, so Kubernetes restarted healthy pods while Redis was slow. Their code also failed the whole request on a Redis timeout, instead of falling back to the database. Their fixes stopped the probes from depending on Redis and added the database fallback.

Three settings decide how your grading service behaves during a stall:

- A **timeout on every call**, so a stuck call ends. A call with no timeout can hold a request open for the whole stall.

- A **request context** that the call obeys, so a gRPC deadline can cancel the call when the caller has given up.

- A **fallback** for each read, such as the database or a default value, so a slow cache does not fail the request.

The platform in the running case had both kinds of client. An older service used go-redis v6, with no `context.Context` anywhere and no timeouts set. It even found cache misses by checking whether the error text contained "nil". A newer service used go-redis v9, passed a context first on every call, and set read and write timeouts of 2 s. When Redis hangs, the v9 service can cancel a stuck call at the gRPC deadline. The v6 service cannot, so its requests stay open and its pool fills.

With one command thread, a slow command or a fork delays every client of the instance.

Harness believed Redis 6 ran commands in parallel, and shipped KEYS on a hot path.

Run E4, then `SLOWLOG GET 10`, and look for the sleep but no waiting GETs.

**Go deeper: client generations, topology at boot, and a cancellation hazard**

**Four client generations.** On the platform, four Go services pinned four go-redis versions: v6.15.9, v8.2.3, v8.11.5 and v9.0.3. Across the company, 17 repositories used v9, 12 used v8 and 14 used v7, with some on redigo, so a migration was in progress. The v9 service also set `ReadOnly` and `RouteByLatency` to send reads to the nearest replica, and used `SetNX`. The question to ask of any client is the one above: which one can cancel a stuck call when the gRPC deadline fires?

**Topology found once, at boot.** One service called `CLUSTER SLOTS` at startup. If the call worked, it built a cluster client, and if not, a standalone client. The same service was wired to both a cluster-mode endpoint and a standalone endpoint. Later, a client on the platform kept a stale map of shards after a cluster-mode change, and that caused an incident. So ask whether such detection runs once at boot or on each connection. A check that runs once cannot follow a live change of topology.

**One node instead of the cluster endpoint.** At Webflow, the Redis primary failed over. The app's Redis URL pointed at one node, not at the cluster endpoint. Errors on the long-lived connection were not caught, so pods crashed in a loop for about 30 minutes.

**Cancellation needs care too.** At OpenAI, redis-py with asyncio shared a pool of connections. A request cancelled after it was sent, but before its reply was read, left that reply on the connection. The next, unrelated request read it. Usually this gave an error. Sometimes the stale reply had the expected type, so one user saw another user's data. Payment data of 1.2% of ChatGPT Plus subscribers active in a nine-hour window may have been visible. So a client that cancels a call must also close or drain that connection. Whether go-redis does this on context cancellation was not checked for this lesson.

**Evidence**

SLOWLOG GET page for the quoted line. `slowlog-log-slower-than` default from Redis `src/config.c:3579` and `slowlog-max-len` from `redis.conf:2100`, both at tag 8.10.2. The `latency-monitor-threshold` value was measured on the local run. `--intrinsic-latency` is on the checklist of the Redis latency page. Harness status page, 2023-09-21. The client versions come from the phase's code survey of the platform. Webflow status page, 2020-02-19. OpenAI, "March 20 ChatGPT outage: Here's what happened", 2023-03-24, read from the Wayback copy.

You can now explain a stall and find its cause. The next section turns to a cost that never appears in SLOWLOG at all: a fast command called many times.

## Where does the time of one GET go?

A slow command hurts every client at once. The next cost hurts only you, and it comes from a fast command called many times. Your grading service reads 40 rubric items with one GET each, in a loop. A teammate says each GET takes about 0.4 ms, so the loop costs 16 ms, and that is fine.

Every Redis call has two parts. The server's work is the command itself, and for a GET it is well under a microsecond. The *round trip* is everything else. It covers your write system call, the kernel's TCP stack and the network. It also covers the server's read and write system calls, and the same path back. The caller waits for the whole round trip on every call, so the round trip sets the cost.

**One GET on the local run, 94 µs at p50.**

- server work: 0.27 µs, hash lookup and reply, from INFO commandstats

- round trip: about 94 µs, system calls, kernel TCP, loopback, client code

**Predict: the server spends 0.27 µs on each GET, and your service measures 94 µs per GET. If you moved Redis to a server with a CPU twice as fast, how much faster would your 40-GET loop get?**

Only a little faster. A twice-as-fast CPU saves about 0.13 µs of the command time, about 0.1% of each 94 µs call. The other 99.7% is the round trip. A faster server CPU shortens only the server's part of it, its system calls and its kernel work. The network and the client stay the same. Most engineers expect a real gain, because they think of Redis latency as server latency.

### What one round trip costs

1. Your client writes the command to its socket with one `write()` system call.

1. The kernel sends it through TCP, the network card or loopback, and the other host's kernel.

1. The Redis main thread wakes from `epoll_wait` and reads the command with one `read()` system call.

1. It runs the GET in about 0.27 µs and queues the reply.

1. It writes the reply with one more `write()`, and the bytes travel back the same way.

1. Your client reads the reply, decodes it, and only then sends the next command of the loop.

The table shows the same program in three places. The server work stays near 1 µs or less, and only the path around it changes.

| Where the client and server ran | GET p50 | GET p99 |
|---|---|---|
| Local run: Redis 8.10.1 under Rosetta 2, same host, TCP loopback | 94 µs | 212 µs |
| Redis in Docker Desktop on a Mac, from the phase | 354 µs | 591 µs |
| Redis docs, typical latency of a 1 Gbit/s network | about 200 µs | not given |
| Redis docs, latency of a Unix domain socket | as low as 30 µs | not given |

The phase's run also showed a maximum of 15.8 ms in 5,000 GETs. The phase calls it an operating system scheduler delay on the client, not Redis work. That was not checked. Your numbers will differ, so measure them with E2 against your own setup.

The phase said that the other 350 µs of each GET is "wire, kernel, and client". That run used Docker Desktop on a Mac, which adds a virtual machine network hop. On the local run, outside Docker on the same Mac, the whole GET took 94 µs at p50. The phase's numbers for ElastiCache in a VPC had no source, so this lesson leaves them out.

Now the running case has a number. Forty GETs in a loop cost 40 round trips. At 94 µs each that is 3.8 ms on loopback, and at the teammate's 0.4 ms it is 16 ms. Neither figure is Redis work, because the server spent about 11 µs on all 40.

**Go deeper: system calls, an idle server and the response cache**

**System calls cost too.** The pipelining docs say that each command sent alone costs the server one `read()` and one `write()` system call. With pipelining, "many commands are usually read with a single read() system call". So batching helps even on loopback, where the network delay is tiny. The next section shows the numbers.

**The round trip and an idle server.** Stack Overflow measured a network round trip of about 0.17 ms to its Redis servers. Those servers ran at about 2% average CPU. So clients spend almost all of their Redis time waiting on the network, while the server has spare time.

**The phase's own run.** The program `latency_probe` sent 5,000 GETs to the study container. It printed p50 354 µs, p99 591 µs and max 15.8 ms. `INFO commandstats` on the same server showed about 1 µs per call. On the local run, 10,000 GETs gave p50 94 µs and p99 212 µs, with `usec_per_call=0.27`. The gap between the two runs is the Docker network hop. A check would be to run both programs against the container and the local server on one machine.

**Cache whole responses, not fields.** On the platform in the running case, a shared Java client cached whole API responses in Redis. Each key held one response, named by a prefix, a scope and the MD5 hash of the URL. So one round trip returned a whole settings object, instead of one round trip for each field. The phase on caching studies this design and where it breaks.

**Evidence**

Redis pipelining page, "It's not just a matter of RTT". Redis latency page, section "Latency induced by network and communication", for the 200 µs and 30 µs figures. Stack Overflow figures from Nick Craver's 2019 app caching post, measured 2019-07-30. Local run conditions in the first section's evidence note.

Each call pays one round trip, so the fix is to make fewer round trips. The next section asks how much batching saves, and why the saving stops growing.

## How much does batching save, and where does the saving stop?

Every call pays one round trip, so the fix is to send many commands in one round trip. There are two ways to do it. *Pipelining* means the client writes many commands without waiting for replies, and then reads all the replies. A *variadic command* takes many keys in one command, such as `MGET k1 k2 k3` for reads or `MSET` for writes.

Loop of 500 GETsOne pipeline of 500 GETs

1. **round trip 1** One GET is sent and its reply is read.

1. **round trip 2** The next GET waits for the first reply.

1. **round trips 3 to 500** Each one pays the full network path again.

Local run: 55.0 ms for 500 keys, about 110 µs a key.

1. **one write** The client sends all 500 GETs together.

1. **server work** The main thread runs them in a few passes.

1. **one read** All 500 replies come back together.

Local run: 0.460 ms for 500 keys, about 0.9 µs a key.

### Why a pipeline is fast

1. The client writes many commands into its socket in one or a few writes.

1. The server reads up to 16 KB per read call. Its loop runs every complete command in that buffer in one pass.

1. The replies collect in the client's reply buffer, and `beforeSleep` writes them in one write.

1. What remains for each command is parsing, the lookup and encoding the reply, on both sides. On the local run that was about 0.8 µs per GET.

So a loop of N commands costs N round trips, and a pipeline costs about one round trip plus N small costs. The speed-up cannot pass the ratio of those two costs per command. On the local run, one GET alone cost about 98 µs and one GET in a pipeline cost about 0.8 µs. So the ceiling is about 98 divided by 0.8, which is near 120.

| Keys | Loop | Pipeline | Speed-up |
|---|---|---|---|
| 50 | 6.53 ms | 0.195 ms | 33x |
| 500 | 55.0 ms | 0.460 ms | 120x |
| 5,000 | 485 ms | 4.10 ms | 118x |
| 50,000 | 4.92 s | 39.6 ms | 124x |

**Evidence**

Measured with the course's `pipeline_vs_roundtrip` on the local run. The per-key costs come from the 50,000-key row: 4.92 s divided by 50,000 is about 98 µs, and 39.6 ms divided by 50,000 is about 0.8 µs.

Move the numbers below to see the ceiling. The speed-up climbs quickly at small batch sizes, and then it flattens near the ratio of the two costs.

**A loop against one pipeline**

Keys
Round trip in µs
Work per pipelined command, tenths of a µs
Loop **, pipeline **, speed-up **, ceiling **

A model built from the local run's per-key costs, not a measurement. At 500 keys the model gives about 98x, but the run measured 120x. The model takes both costs from the 50,000-key run and adds one full round trip to the pipeline. In the 500-key run, one loop GET cost about 110 µs, not 98 µs. The whole pipeline took 0.46 ms, less than the model's 0.50 ms. So the cost per key changes with the batch size, and the model gives only an estimate.

The phase's lab said the speed-up grows as the batch grows. It stops near 120x from 500 to 50,000 keys on Redis 8.10.1. The phase's 224x came from Docker Desktop, where each round trip was longer, so the ceiling was higher. The program's own header gives a third range, 10 to 50x and 30 to 80x. One program needs one measured number with its conditions.

### Limits on a batch

- The pipelining docs advise batches of about 10,000 commands, because "the server will be forced to queue the replies, using memory".

- The latency docs prefer "aggregated commands (MSET/MGET), or commands with variadic parameters" over pipelining. One command parses once and replies once.

- A large pipeline arrives in several 16 KB reads, so other clients' commands can run between those reads. A pipeline is not a transaction, and the next section shows why that matters.

**Swiggy** found that 50 to 70% of the time of its feature-store jobs went to Redis writes. Thousands of daily jobs wrote to an ElastiCache cluster, and each command paid its own round trip. The team wrapped the Jedis client to pipeline writes at a set batch size, with retries and backoff for slot moves. Redis write time fell by 90%, and cost fell by about 60%, on a few write-heavy jobs. Very large batches filled the socket buffers, so each workload had its own best batch size.

The running case now has its fix. One `MGET` of the 40 rubric keys costs about one round trip plus 40 small costs. On loopback that is about 0.13 ms instead of 3.8 ms. At the teammate's 0.4 ms round trip it is about 0.43 ms instead of 16 ms.

Count round trips, not commands, and batch reads with MGET or a pipeline.

One Redis call per item costs 1.2 ms at 3 items and 200 ms at 500, at 0.4 ms each.

Run E3 with 50, 500 and 5000 keys, and watch the speed-up stop growing.

**Go deeper: the docs' own numbers, buffers, the phase's run and two more cases**

**The docs' measurement.** On loopback, 10,000 PINGs took 1.185 s without pipelining and 0.251 s with it. The docs also say queries per second rise "almost linearly with longer pipelines, and eventually reaches 10 times the baseline". That gain comes from fewer system calls, not from the network, because loopback has almost no network delay.

**Buffers on the server.** Each client has a 16 KB reply buffer, and a larger reply goes into a list of 16 KB blocks. The server writes at most 64 KB to one client in one event, so one client cannot hold the loop. A normal client has no output buffer limit by default, `client-output-buffer-limit normal 0 0 0`. So a client that reads a huge reply slowly makes the server hold that reply in memory, and that memory counts toward the limit. Redis 8.10.2 also has a new setting, `lookahead`, default 16, which "Defines how many commands in each client pipeline to decode and prefetch". Its effect on the numbers above was not measured.

**The phase's run.** The phase measured 500 GETs on Docker Desktop. The loop took 208.9 ms, and the pipeline took 934 µs, a speed-up of 224x. With a round trip of about 400 µs, the loop's cost is 500 times 400 µs, which is about 200 ms. The measured 208.9 ms is close to that.

**Batch reads at Swiggy.** A second Swiggy team batched feature reads with `MGET` or pipelines, and grouped requests so each feature was read once. For order assignment, p99 fell from 144 ms to 71 ms at batch size 30, at over 5,000 predictions a second.

**Fewer calls at the source.** Shopify's storefront renderer keeps an in-process memo. It avoids 16 to 20 Redis or MySQL calls per request on average, so those calls pay no round trip at all.

**Big values on a shared connection.** Stack Overflow pipelined its Redis connections. Multi-megabyte values on that connection made the commands behind them time out, which is head-of-line blocking inside the client. Their fix was a separate "bulky" connection with longer timeouts for large values.

**Evidence**

Redis pipelining page, the benchmark on Mac OS X loopback with a Ruby client, and its "IMPORTANT NOTE". Redis latency page, network section. Buffer facts from Redis source at tag 8.10.2: `src/server.h:191`, `src/networking.c:2855-2890`, `src/config.c:172-176`, `redis.conf:2486-2487`. Swiggy, "Optimizing batch writes to Redis using Pipelining", Rahul Narayana, 2023-01-03, read from an archive copy. Swiggy, "2x Improvement in Latency in Swiggy Data Science Platform", 2022-05-04. Shopify, "Simplify, Batch, and Cache", 2020-12-10. Stack Overflow, Nick Craver, 2019-08-06.

Batching made the 40 reads fast. It also showed that other clients' commands can run between yours. The next section asks what that does to a counter that two workers update.

## Which Redis operations are atomic, and which are not?

Other clients' commands can run between two of yours, even inside a pipeline. That matters for the next part of your grading service. It must allow at most 100 LLM calls per company per minute, and many workers update the same counter.

An operation is *atomic* when no other client's command can run in the middle of it. Other clients see either none of it or all of it. One Redis command is atomic, because the main thread runs it to the end before it takes the next one. A Lua script is atomic for the same reason. Two separate commands are not, because the thread may run other clients' commands between them.

**Read in one command, write in another.**

1. Worker A runs `GET count` and gets 7.

1. Worker B runs `GET count` and also gets 7.

1. Worker A adds 1 in Go and runs `SET count 8`.

1. Worker B adds 1 in Go and runs `SET count 8`.

Two calls were counted, but the counter moved by one.

**Read and write in one command.**

1. Worker A runs `INCR count` and gets 8.

1. Worker B runs `INCR count` and gets 9.

Each INCR reads and writes inside one command, so no update is lost.

**Predict: two workers each run GET count, add 1 in Go, and run SET count. Redis runs one command at a time. Can an update be lost? What one change makes it safe?**

Yes, an update can be lost, as the figure shows. Redis runs each command alone, but the read and the write are two commands. Another worker's GET can run between them. The fix is one command that reads and writes together: `INCR count`. Many engineers answer "no", because they hear "single-threaded" and conclude that nothing can race.

### How much is lost

On the local run, 200 shell processes started at the same moment. Each one ran `GET rmw` and then `SET rmw` with the value plus one. The final value was **5**, so 195 of the 200 updates were lost. Then 200 processes each ran `INCR inc`, and the final value was **200**.

### The tools for atomic work

1. **One command that does the whole job.** `INCR` counts, and `SET key value NX EX 30` sets a key only if it is absent, with a 30-second TTL. Both are a check and a write in one step.

1. **A Lua script or a Function.** The script runs on the main thread from start to end, so its reads and writes are one atomic step. Functions, added in Redis 7, follow the same rule.

1. **What is not atomic.** A pipeline is a batch for the network, not for atomicity. Logic in your Go code between two commands is not atomic either.

An atomic script is also a blocking script, because it holds the one main thread for its whole run. The setting `busy-reply-threshold`, whose old name is `lua-time-limit`, defaults to 5000 ms. Past that time, Redis answers other clients with a BUSY error, and the script keeps running.

### A real case: atomic inside the script, wrong outside it

**GitHub** moved its API rate limiter from Memcached to Redis. The team chose to "Implement the storage logic in Lua, to guarantee atomicity of operations". Their first bug came from a value used outside the script. The script returned a key's TTL, and Ruby added it to the Ruby clock to build the reset header. Time passed between the two calls, so the reset time in the header changed by one second between responses. Atomicity covered only what ran inside the script.

**Evidence**

Local run, `redis-cli` 8.10.1, conditions in the first section. GitHub blog, "How we scaled the GitHub API with a sharded, replicated rate limiter in Redis", Robert Mosolgo, 2021-04-05, updated 2023-03-23, section "Fix 1". `busy-reply-threshold` default from Redis `src/config.c:3573` at tag 8.10.2. `INCREX` from Redis `src/commands/increx.json` at tag 8.10.2, "since": "8.8.0", and the comments at `src/t_string.c:1162` and `:1187`. Valkey 9.1.2 has no `increx.json`.

For your grading service, the counter is now one Lua script that runs `INCR` and sets `EXPIRE` on the first call of each minute. Every worker can run it at the same time, and the count stays exact. On Redis 8.8 and later, the one command `INCREX key EX 60 ENX` does the same work. It adds 1, and `ENX` sets the TTL only when the key has none. Keep the Lua script on older Redis and on Valkey, which has no `INCREX`.

One command or script is atomic, and a read then a write in your code is not.

Single-threaded does not mean race-free, so GET then SET loses updates.

Run E7, then the same loop with GET and SET, and compare the totals.

**Go deeper: three generations of rate limiter, locks, retries and long scripts**

**Three rate limiters on one platform.** The platform in the running case had three generations, all live. The oldest service kept a sliding list with `LPUSH` and `LTRIM`, guarded by a lock in the application, so it was not atomic. A newer dashboard API ran a Lua script with `INCR`, `EXPIRE` and `TTL` per route, company and user. That fixed window was atomic, and it failed open when Redis was down. A third service gave the job to Kong's `rate-limiting-advanced` plugin. Every deployed service also carried its own single-replica `redis:alpine` as the counter store for Istio rate limiting. It listened on port 6379, with sidecar injection turned off.

**Locks in three tiers.** One service used `redsync`, a Redlock library with a random lock value and an atomic compare-and-delete unlock. Six other services wrote their own `SETNX` locks with varying care, one of them with exponential backoff. The phase's usage map counts eight repositories with hand-written locks, so the exact count is not certain. A third design marked translation jobs in progress with `ZADD`, `ZREM` and `EXPIRE` on a sorted set. The phase on locking judges each one: who can deadlock, who can run a job twice, and who has no fencing.

**Idempotency keys.** Services used `SET key value NX EX ttl` to process each event once. The first `SET` wins, and every later one gets nil. The TTL frees the key if the process dies before it finishes.

**Retries break some commands.** Twitter found that many Redis commands are not idempotent. An `INCR` retried after a network error may count twice, because the first one may have run. So a retry policy must know which commands are safe to repeat.

**Long scripts.** A Lua script checks its run time every 100,000 instructions. After `busy-reply-threshold`, Redis logs "Slow script detected" and replies `-BUSY` to most commands. `SCRIPT KILL` or `FUNCTION KILL` works only if the script has not written yet. Otherwise the reply is `-UNKILLABLE`, and the only way out is `SHUTDOWN NOSAVE`, which loses the data since the last save. So a script that loops over 100,000 items blocks every client, in the same way as `DEBUG SLEEP`.

**Evidence**

Platform designs from the phase's survey of the codebase. Twitter, from High Scalability's summary of Yao Yue's talk "Scaling Redis at Twitter", 2014-09-08, which is a summary, not Twitter's own text. Script rules from Redis source at tag 8.10.2: `src/script_lua.c:1670`, `src/script.c:141-170`, `src/script.c:361-390`, `src/server.c:4800-4808`.

Commands and scripts share one thread. They also share one pool of memory, and the next section asks who fails when that pool is full.

## Who fails when the memory pool is full?

Every client shares one main thread, and every client also shares one pool of memory. On your cluster, the LLM gateway team stores prompt results with no TTL. Your grading service writes every cache entry with a 5-minute TTL. One morning the cluster reaches its memory limit.

Each Redis instance has one memory limit, *maxmemory*, shared by every key of every service. When a write would pass that limit, the *eviction policy*, set by `maxmemory-policy`, decides which keys Redis removes to make room. An `allkeys-*` policy may remove any key. A `volatile-*` policy may remove only keys that have a TTL. With `noeviction`, Redis removes nothing and refuses the write.

**A full shared cluster under volatile-lru, an illustration, not measured.**

- gateway keys: no TTL, never candidates for eviction

- grading keys: 5-min TTL, the only keys Redis may evict

- free: near 0, every new write needs room

**Predict: a shared cluster is full and runs volatile-lru. Service A writes keys with no TTL. Service B writes every key with a 5-minute TTL. Whose writes fail first, and what does the evicted_keys counter show?**

At first nobody's writes fail. Redis makes room by evicting B's keys, because they are the only candidates, so B's cache hit rate falls. Once no key with a TTL is left, Redis cannot free anything. From then on, every write that needs memory fails, from A and from B alike, and `evicted_keys` stops growing. Most engineers expect A, the careless service, to be the only one hurt.

### What Redis does before each write

1. When `maxmemory` is set, `processCommand` calls `performEvictions()` before it runs the command.

1. Eviction samples `maxmemory-samples` keys, 5 by default, into a pool of 16 candidates, and evicts the best one. It repeats until memory is under the limit.

1. Under a `volatile-*` policy, only keys with a TTL can be sampled. The docs say: "The volatile-xxx policies behave like noeviction if no keys have an associated expiration."

1. If eviction cannot free enough memory and the command can grow memory, Redis rejects it. The client gets `OOM command not allowed when used memory > 'maxmemory'`.

1. Reads and deletes still work, so the cluster looks half alive while every write fails.

The default policy depends on where Redis runs. Open-source Redis 8.10.2 and Valkey 9.1.2 default to `noeviction`. ElastiCache default parameter groups use `volatile-lru`, and that includes the groups for Valkey 7.2 to 9.1. So a cluster that nobody tuned evicts only keys with a TTL.

### The failure, measured

On the local run, the server got `maxmemory 50mb` and `volatile-lru`, then 2,000,000 keys with no TTL, about 150 MB. Then `SET good:1 v EX 300` returned the OOM error, even though that key had a TTL. `evicted_keys` stayed at 0. After a switch to `allkeys-lru`, one `SET` worked, and within half a second `evicted_keys` was 1,268,122.

The counter is the trap here. An alert on `evicted_keys` would not fire, because in this failure nothing is evicted. Alert on `used_memory` against `maxmemory`, and on OOM errors in your clients.

### The case on the platform

This is the incident from the start of the lesson. The LLM gateway wrote keys with no TTL to a shared cluster that ran the AWS default `volatile-lru`. Memory reached 100%, and the keys without a TTL could not be evicted. An upload service that shared the cluster had done nothing wrong, and it was down with the gateway for 4 hours 37 minutes. The fix had three parts: TTLs on the gateway's keys, deletion of the keys left behind, and a larger cluster. On a shared cluster, a neighbour's missing TTL can cause your outage.

**Pendo** had the same cause in public. Two code paths created cache keys with no expiry. Their Redis on Memorystore sat near its limit and kept evicting, and CPU spikes caused slow replies and failed connections. The guides service had an error rate of about 60% for the first 90 minutes. The team flushed all Redis instances, fixed the two code paths and added Redis monitoring.

### A full cache is also a slow cache

Eviction runs on the main thread, so a cache that lives at its limit spends thread time on eviction. **GitLab** saw latency bursts on its cache Redis each time memory reached `maxmemory`. The main thread was already near one full core, and eviction pushed it over. The rate of `processCommand` calls "dropped to 20% of its norm ... from 25K to 5K calls per second". The main fix was to cut the default TTL from 2 weeks to 8 hours, which did not significantly reduce the hit rate.

**Evidence**

Redis source at tag 8.10.2: `src/server.c:4656-4672`, `src/evict.c:491-505`, default policy at `src/config.c:3491`. Valkey 9.1.2 `valkey.conf:1346`. Redis eviction page for the quote. AWS ElastiCache engine parameters page: `maxmemory-policy` "Default: volatile-lru". The local run as described in the first section. Platform incident from the phase. Pendo status page, 2020-02-21. GitLab blog, "How we diagnosed and resolved Redis latency spikes with BPF and other tools", Matt Smiley, 2022-11-28. Before the fix, "Each weekday had roughly 2 million Redis requests slower than 1 second".

The phase said Redis has 8 eviction policies. Redis 8.6 added two more, `allkeys-lrm` and `volatile-lrm`, so Redis 8.10.2 has 10. LRM means least recently modified, and only writes update its timestamp. Valkey 9.1.2 still has 8.

A full cluster under volatile-lru refuses all writes once only keys with no TTL remain.

The belief that a full cache drops old data hides a missing TTL until writes fail.

Run E8, then CONFIG GET maxmemory-policy, and say what happens under volatile-lru.

**Go deeper: the ten policies, the eviction budget, expiry, and two more cases**

| Policy | Which keys it may evict | How it picks |
|---|---|---|
| `noeviction` | none, it refuses writes | the open-source default |
| `allkeys-lru`, `volatile-lru` | all keys, or keys with a TTL | least recently used, approximated by sampling |
| `allkeys-lfu`, `volatile-lfu` | all keys, or keys with a TTL | least frequently used, a log counter |
| `allkeys-random`, `volatile-random` | all keys, or keys with a TTL | at random |
| `volatile-ttl` | keys with a TTL | the shortest TTL left |
| `allkeys-lrm`, `volatile-lrm` | all keys, or keys with a TTL | least recently modified, Redis 8.6 and later only |

**The eviction budget.** `maxmemory-eviction-tenacity` defaults to 10, which gives a slice of 500 µs per call. If memory is still over the limit after the slice, a timer on the main thread continues the work. The LRU clock has 24 bits in units of one second. The LFU counter starts at 5, with `lfu-log-factor 10` and `lfu-decay-time 1`. Replicas ignore `maxmemory` by default, through `replica-ignore-maxmemory yes`.

**used_memory is not RSS.** The operating system kills a process by its resident memory, its RSS. The copy-on-write pages of a fork, fragmentation and client buffers all add RSS above `used_memory`. So an instance can stay under `maxmemory` and still be killed during a snapshot.

**Expiry is not exact.** Redis deletes an expired key when a client touches it, or when the active cycle samples it. The active cycle samples 20 keys per database per loop. It repeats while more than 10% of the sample was expired. The slow cycle may use 25% of a timer tick, which is 25 ms at `hz 10`. A fast cycle of up to 1000 µs runs in `beforeSleep`. So a million keys given the same expiry second make the cycle run at its limit for a long time. Adding a random jitter to each TTL spreads that work out.

**Volume, not code.** On the platform, a burst of events from a data migration filled a Redis cluster, although every key had a 30-day TTL. Each command was fine, but the total write rate was more than the TTLs could free in time.

**A queue that cannot dequeue.** Slack kept its job queue in Redis, with peaks of 33,000 jobs a second. When the database slowed, jobs piled up until Redis reached `maxmemory`. Dequeue moves a job into an in-flight list, so it needs memory too. The queue stayed stuck after the database recovered. Slack put Kafka in front of Redis, with a relay that moves jobs at a controlled rate.

**Lab sizes.** On the local run, 4,000,000 keys from `DEBUG POPULATE` used 238 MB. So the 5,000,000 keys of lab E5 pass the lab's 256 MB cap, and `allkeys-lru` evicts some of them. A repeated `DEBUG POPULATE 3000000` adds nothing, because it skips keys that already exist.

**Evidence**

Policy list from Redis `src/config.c:39-51` and `redis.conf:1230-1266` at tag 8.10.2, and Valkey `src/config.c:60-69` at 9.1.2. Eviction constants from Redis `src/evict.c` and `src/config.c:3518-3523`. Expiry constants from Redis `src/expire.c:96-100` and `src/expire.c:347`. The Redis latency page, section "Latency generated by expires". Slack, "Scaling Slack's Job Queue", 2017-12-06, updated 2020-06-25. `DEBUG POPULATE` skip rule from Redis `src/debug.c:827-834`.

Eviction removes some keys on purpose. A restart or a failover can remove all of them at once. The next section asks which keys each pattern can afford to lose.

## What does Redis lose, and which loss can each pattern accept?

Eviction removes keys one at a time. A restart, a failover or a bad configuration can remove all of them at once. Your cluster now holds session records, a page cache, the LLM-call counter, a lock and a payment idempotency key.

Redis keeps the primary copy of every key in RAM. *Persistence* writes that data to disk in one of two ways. A forked child writes a snapshot, or Redis logs every write to an append-only file, the AOF. A *replica* is a second Redis that copies the primary's writes over the network, a little after they happen. Both reduce what a crash loses. Neither makes Redis the *system of record*, the store whose copy is the truth when two copies disagree.

| Pattern on the cluster | What a loss costs | Phase that teaches it |
|---|---|---|
| cache entry | a slow request, while the database serves it again | caching |
| session record | the user signs in again | data structures, production design |
| rate-limit counter | a fresh window, so a company can pass its limit once | data structures, performance |
| queue of jobs | lost work, unless the producer can send it again | data structures |
| lock | two workers do the same job at once | locking |
| idempotency key | a payment or an email can happen twice | locking |

**Predict: sessions, a page cache and a payment idempotency key share one Redis. The primary restarts empty. For each one, what does the user see?**

For sessions, users must sign in again. For the page cache, pages are slow for a while, and the database takes the full load until the cache fills. For the idempotency key, a payment retry is no longer recognised, so the customer can be charged twice. The same restart costs a few seconds for one pattern and money for another. Most engineers judge the whole cluster by its main job, the cache.

### How a restart can lose everything

1. On start, Redis rebuilds its memory from the file its configuration names, a snapshot or an append-only file.

1. If the configuration names the wrong file, or no file, Redis starts with an empty dataset and serves it.

1. Replicas copy the primary over the network. A replica that loses its link may ask for a full copy of the data.

1. Each full copy needs a fork and a snapshot on the primary. If every replica asks at once, the primary is overloaded.

The phase on durability and replication teaches each of these steps in detail. Here the point is the order of the facts. RAM holds the primary copy, and disk and replicas are copies made after it.

### A real case: the balances that were in Redis

**Twilio** kept in-flight account balances in a Redis cluster for billing. A network failure cut all replicas off from the primary, and all of them asked for a full sync at the same time. The full syncs overloaded the primary, so an engineer restarted it. On restart it "read an incorrect configuration file", tried "to recover from a non-existent AOF file", and "dropped all balance data". The same file made it boot "as a slave of itself", so it was read-only. Balances read as zero and could not be written, and auto-recharge charged customer cards again and again. It affected 1.4% of customers. Recovery used "independent double-bookkeeping for all balance data in a separate relational datastore".

**Evidence**

Twilio, "Billing Incident Post-Mortem: Breakdown, Analysis and Root Cause", incident of 2013-07-18. Replica sync load from 9:39 UTC, wrong charges seen at 10:28 UTC. 1.1% of customers in the first wave and 0.3% in a recurrence. Fixes: replace the cluster, correct the config, disable restarts on the primary, recover by promoting a replica, refunds and a credit of 10% of 30 days of spend.

### Decide per pattern in your grading service

- The rubric cache can go, because the service reads the rubric from its database again.

- A cached LLM result can go, because a miss calls the model again. That costs money and time, not correctness.

- Session records can go, because the worst case is a new sign-in, and the user can rebuild the data.

- An idempotency key for a payment cannot rely on Redis alone. The durable payment record must also reject the duplicate.

The platform in the running case made these choices in its own code. Generated buyer personas were cached for 3 days, and a miss generated the persona again with the LLM. Stream state lived for 10 minutes. Sessions lived in Redis on purpose, because a lost session costs one sign-in.

**Go deeper: the six patterns on the platform, and four more cases**

**Six patterns on one platform.** About 34 services in 12 or more repositories used Redis on several shared ElastiCache clusters, and caching was only part of it.

| Pattern | How the platform used it |
|---|---|
| caching | cache-aside with TTLs: a 30-minute TTL in one service, 3 days for buyer personas, and a shared response cache |
| sessions | `express-session` with `connect-redis` and an 8-hour TTL on a cluster client, and hashes with sets in a Go login service |
| locking | `redsync` in one service and hand-written `SETNX` locks in eight repositories |
| idempotency | `SET NX EX` keys in a Python service and an assessment service, and sorted-set job markers |
| queues and pub/sub | `RPUSH` and `LPOP` as a FIFO queue, and `PUBLISH` and `SUBSCRIBE` for dispatch messages |
| rate limiting | a Lua fixed window that fails open, a legacy sliding list, and Kong's plugin |

One Go file of 106 lines in the content service used four of the six. It published sync details on a channel, and it took and released a Redlock through `redsync`. It also stored values with `Set` and `Get`, and read a set with `SMembers`.

**Sessions on a standalone instance.** The login service built a standalone client, not a cluster client, and had a variant that selected numbered databases with `SELECT`. In Redis Cluster only database 0 exists, so that code told you the topology before any Helm chart did. One region ran a cluster-mode Redis 5.0.6, and another ran a simpler set without cluster mode on Redis 6. Valkey 9.0 added numbered databases to cluster mode, so `SELECT` no longer always means a standalone instance. The setting `cluster-databases` still defaults to 1 in Valkey 9.1.2. So a Valkey cluster has only database 0 until you raise it.

**A rate limiter that shared an evicting pool.** GitHub's old rate limiter shared one Memcached with other caches. "When it filled up, it would sometimes evict rate limiter data", so clients got a fresh window. Data with very different loss costs shared one evicting pool.

**Atomic with the ledger, or fast.** Shopify kept inventory reservations as one Redis counter per item, with `DECR` to reserve and `INCR` to release. The inventory ledger lived in MySQL, so the claim step could not be atomic across both stores, and that risked overselling. Shopify moved reservations to MySQL rows locked with `SELECT FOR UPDATE SKIP LOCKED`. On Black Friday 2025, Shopify merchants peaked at $5.1M in sales per minute. On the new MySQL design, the throughput limit turned out to be database connections, not CPU.

**Empty after recovery.** In a Redis Cloud outage, a software update put a cluster management process into an endless loop, and five nodes failed. Databases without persistence came back at once, but empty. Databases with persistence came back slowly, the largest last.

**Redis used as a database by accident.** At bsport, one ElastiCache Redis served payments, bookings, sign-in, email and push. A legacy Redis inside their Kubernetes cluster then stopped answering. Retries and reconnects overloaded CoreDNS, and the whole platform went down. The team then found keys with no TTL that were years old, because teams had used Redis as a database. They split it into one Valkey 8 cluster per domain, and uptime rose from 99.87 to 99.97%.

**Why Twilio's syncs were full.** Redis 2.6 needed a full resync after any disconnect, and partial resync came in Redis 2.8. A restart with no persistence can also empty the replicas, which the phase on replication explains.

**Evidence**

Platform facts from the phase's survey of its codebase and Helm charts. Valkey 9 numbered databases from the Valkey 9.0.0-rc1 release notes, 2025-08-14, which list "Add multi-database support to cluster mode". The `cluster-databases` default of 1 is from Valkey `src/config.c:3383` at tag 9.1.2. GitHub rate limiter post, section "The Problem". Shopify, "We replaced Redis with MySQL for inventory reservations", Emilie Noel, 2026-05-12, peak on Black Friday 2025. Redis Cloud, "February 8th outage post-mortem", 2016. bsport engineering, "How We Eliminated Redis as a Single Point of Failure", 2026-03-27, incident of 2025-04-01. antirez, "Twilio incident and Redis".

Each pattern now has a loss cost. The next section uses the same question to choose a tool. It asks when Redis is right, and when Valkey, Memcached or a durable database fits better.

## Redis, Valkey, Memcached or DynamoDB: which tool for which job?

The loss cost of each pattern decides what may live in Redis. The same question decides when another tool fits better. In a design review, someone will ask why your grading service does not use Memcached or DynamoDB instead.

The three tools solve different problems. Memcached is a cache of opaque values and nothing more. Redis is a server of data structures with atomic commands, and it keeps data in RAM. DynamoDB is a managed database that stores every item durably on disk, across several availability zones. Valkey is a fork of Redis with the same commands, so it answers the same questions as Redis.

|  | Redis or Valkey | Memcached | DynamoDB |
|---|---|---|---|
| What it is | an in-memory server of data structures | an in-memory cache of values | a managed, durable NoSQL database |
| Threads | one command thread, plus I/O threads | multi-threaded | managed for you |
| Data model | strings, hashes, lists, sets, sorted sets, streams and more | opaque values only | items with secondary indexes |
| Atomic tools | `INCR`, `SET NX`, Lua, transactions | `incr`, `decr`, `cas` | conditional writes, optimistic locking |
| Durability | optional snapshots or append-only file | none, a restart empties it | always durable, replicated across zones |
| Expiry and eviction | a TTL per key, 10 policies in Redis and 8 in Valkey | a TTL per key, LRU | a TTL per item, deleted "typically within a few days" after expiry |
| Pub/sub and queues | built in | none | through DynamoDB Streams and Lambda |
| What you pay for | provisioned RAM | provisioned RAM | requests and storage |
| Use it for | cache, counters, locks, queues and sessions in one tool | a plain page or fragment cache | durable key-value data at scale |

### How to choose

1. Ask what a loss of this data costs. If a loss is an incident, the system of record is a durable store, and Redis can only sit in front of it.

1. Ask whether the job needs an atomic operation on shared state, such as a counter, a lock or a rate limit. If it does, Redis fits better. Memcached has only `incr`, `decr` and `cas`, and no scripts.

1. Ask whether you want to size RAM at all. DynamoDB charges per request and needs no RAM sizing, but every read is a database read.

1. Often the answer is both tools: a durable database holds the truth, and Redis holds a cache and the counters in front of it.

**Uber** shows the size of that gain. Its database Docstore has a Redis cache inside its query layer, called CacheFront. Its largest use case serves over 6 million reads a second. Storage alone would need about 60,000 CPU cores for it, and CacheFront uses about 3,000 Redis cores. The database is still the system of record, and Redis holds copies that a TTL or a change stream can refresh.

The platform in the running case made the same split. It ran no Memcached at all, and its imports of a Memcached library were types reused for Couchbase. DynamoDB appeared only as the durable store that replaced Couchbase, with Redis still the cache in front. One CI tool used both on purpose. DynamoDB held durable records of test sites, with a version field for optimistic concurrency between parallel CI runs. Redis held one key, an atomic counter that gave each new record a unique sequential ID.

### Redis or Valkey

Before you compare Redis with other tools, you now pick an engine. Redis 7.2 and earlier used the BSD-3 licence. Redis 7.4 to 7.8 used RSALv2 or SSPLv1, and Redis 8 added AGPLv3 as a third choice. Valkey is a Linux Foundation fork of Redis 7.2.4 under BSD-3. ElastiCache now offers parameter groups for Valkey 7.2 to 9.1, and their default eviction policy is still `volatile-lru`.

The two engines now differ in defaults and features. Valkey frees memory in the background by default and can change `io-threads` at runtime. Redis 8 has the Query Engine, vector sets and the LRM eviction policies in its core. So code that runs on one engine may need a check before it runs on the other.

**Evidence**

redis.io licences page. Linux Foundation press release on the Valkey launch, 2024-03-28. AWS ElastiCache engine parameters page. DynamoDB TTL page. Uber, "How Uber Serves Over 40 Million Reads Per Second from Online Storage Using an Integrated Cache", 2024-02-15. Platform facts from the phase's survey of its codebase.

Keep data in Redis only when you can name what its loss costs and accept it.

"It has AOF and replicas, so it is a database" is how Twilio lost its balances.

For each key prefix on your cluster, write one line: what a loss costs.

**Go deeper: a settings cache with three layers, Twitter's reason, and the numbers left out**

**A settings cache in three layers.** On the platform, one service owned each company's settings. On every write it deleted a scope marker key in Redis, with a bulk remove. Every Java consumer cached whole API responses through a shared client. Each key was built from a prefix, the scope and the MD5 hash of the URL. Those keys had a default TTL of 3600 s, set by `REDIS_CACHE_EXPIRY`. Deleting the scope marker made all of a company's cached responses invalid at once, and the TTL was the fallback. A separate service on AWS Lambda ran its own settings cache with a pure 600 s TTL. No change stream such as Kafka invalidated anything in this chain.

That design depends on cheap, instant, atomic single-key operations that every consumer shares. Moving the settings cache to DynamoDB would turn each scope check into a database request with its own cost and latency. The delete would no longer be one cheap operation that all consumers see at once. The phase on caching asks where this design breaks.

**Why Twitter chose Redis over Memcache.** Twitter kept home timelines as lists of tweet IDs. A timeline is large, but each update is small. With Memcache, each update was a read, a change and a write of the whole large value, which used too much network. Redis changes the list in place on the server. The scale was about 40 TB of memory and about 30 million queries a second for timelines in one data center.

**Numbers the phase gave without a source.** The phase's table gave DynamoDB a p99 of 10 to 20 ms and ElastiCache a same-zone p50 of 300 to 600 µs. Neither had a source, so this lesson leaves them out. Measure both from your own service before a decision depends on them.

**Opinions left out.** The phase called Memcached against Redis "a solved argument" and said Redis 6 I/O threads removed Memcached's last advantage. Neither claim came with a measurement.

**Evidence**

Settings design from the phase's survey of the platform. Twitter facts from High Scalability's summary of Yao Yue's talk, 2014-09-08, which gives no measurement conditions.

You have now seen all five ideas, from the one thread to the cost of a loss. The next section collects them, and says what the next phase answers.

## What you can do now, and what comes next

Your grading service now uses Redis with all five ideas in view. Each claim below is short, and the section that taught it is named after it.

- A slow command or a fork on the main thread stalls the clients of every service. The first three sections showed the queue, the stall and how to find its cause.

- Latency follows the number of round trips, and a pipeline cuts them until the work per command dominates, near 120x on loopback. The sections on one GET and on batching measured both.

- `INCR` and Lua scripts are safe for a shared counter, and a GET followed by a SET is not. The section on atomic operations lost 195 of 200 updates to show it.

- A full cluster that evicts only keys with a TTL refuses writes once only keys without one are left. The section on the full memory pool showed it, while `evicted_keys` stayed at 0.

- A restart can empty Redis, so each pattern needs its own answer to what that loss costs. The last two sections gave that answer for each pattern and each tool.

You can now explain a cluster-wide latency spike, estimate the cost of a call path, and say which of your Redis code can race. You can also predict who fails when a shared cluster fills, and decide which data may live in Redis.

Phase 1 answers the next question: which data structure fits each job, and what each one costs in memory and in time. Run the lab first, then answer the checkpoint questions without looking back.

## Lab: the exercises that teach Phase 0

Ten exercises from the phase, copied as the phase wrote them. Nobody ran them for this lesson. Where a step is wrong, a note under the exercise says what to expect instead. Some notes give numbers from the local run of the same Go programs.

**Practice: which exercise proves which idea**

| Exercise | Idea | State |
|---|---|---|
| E1 MONITOR | one thread, one command stream | works, but slows the server |
| E2 latency_probe | the round trip is the cost | works, numbers differ outside Docker |
| E3 pipeline_vs_roundtrip | batching and its ceiling | the expected answer is wrong |
| E4 blocking_demo | head-of-line blocking | works, has a data race in the program |
| E5 KEYS against SCAN | head-of-line blocking | the expected sizes are wrong |
| E6 SLOWLOG | finding the cause | works |
| E7 INCR race | atomic commands | works |
| E8 TTL and volatile-lru | the full memory pool | works, the failure is on paper only |
| E9 data structures | a preview of Phase 1 | works |
| E10 fill memory | the full memory pool | a repeated step adds nothing |

The lab image is `redis:7.2`. The current releases are Redis 8.10.2 and Valkey 9.1.2. The local run used Redis 8.10.1.

**Practice: open the lab, E1 to E10**

Setup (once):

```
cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d
docker exec redis-study redis-cli PING        # → PONG
```

All Go programs live under `phase00_why_redis/` and compile/run as-is (`go run ./phase00_why_redis/<name>`).

Note for this lesson: that path is wrong. The lab code is at `/Users/raghvendra.dhakar/Desktop/project/code/study-material/redis/code`. All three Go programs build from there.

-  **E1. Watch the single command stream.**

- Run: `docker exec -it redis-study redis-cli MONITOR` in terminal 1; in terminal 2 run `docker exec redis-study redis-cli SET a 1`, `... INCR c`, `... HSET h f v`.

- Expected: terminal 1 prints every command from every client, in execution order, one stream.

- Teaches: there is exactly one serialized command sequence — MONITOR is you watching the event loop.

Note for this lesson: the MONITOR page warns that "running a single MONITOR client might reduce the throughput by more than 50%". Use it only on the study container, never on a shared cluster.

-  **E2. Measure real GET latency.**

- Run: `go run ./phase00_why_redis/latency_probe -n 10000`

- Expected: p50 in the 200–500µs range, p99 under ~3ms, occasional multi-ms max.

- Verify: in the `commandstats` output at the bottom, find `cmdstat_get` → `usec_per_call` ≈ 1µs or less.

- Teaches: the ~350x gap between server execution time and client-observed latency is the network.

Note for this lesson: the local run used a server outside Docker on the same Mac. It gave p50 94 µs and p99 212 µs, with `usec_per_call=0.27`. The 200 to 500 µs range includes the Docker network hop. The program prints the whole `INFO commandstats` section, not only `cmdstat_get`.

-  **E3. Prove the round-trip cost model.**

- Run: `go run ./phase00_why_redis/pipeline_vs_roundtrip -keys 500`

- Expected: sequential ~100–300ms, pipelined ~1–10ms, speedup 30–224x.

- Then: re-run with `-keys 50` and `-keys 5000`. Does the speedup grow or shrink with N? Why? (More round-trips amortized → grows.)

- Teaches: cost = round-trips, and pipelining as the first-line fix.

Note for this lesson: the answer in brackets is wrong. On the local run the speed-up was 33x at 50 keys, 120x at 500, 118x at 5,000 and 124x at 50,000. It stops growing near a ratio of two costs. One GET alone cost about 98 µs, and one GET in a pipeline cost about 0.8 µs. Ask "why does the speed-up stop growing?" and add a run with `-keys 50000`. The program's header comments give 10 to 50x and 30 to 80x, which match neither run.

-  **E4. Feel head-of-line blocking (the Phase 0 centerpiece).**

- Run: `go run ./phase00_why_redis/blocking_demo -sleep 2`

- Expected: warm-up max GET latency well under 1ms; then one GET reported taking ~2.00s.

- Teaches: one slow command on one connection stalls a different connection's microsecond read.

Note for this lesson: the local run gave a warm-up maximum of 336 µs and a blocked GET of 2.0007 s. In `main.go`, lines 52 to 97, the variable `maxLat` is written by the reader goroutine and read by `main` with no lock. The Go memory model calls that a data race, although one `-race` run did not report it. Use `atomic.Int64`. The demo needs `--enable-debug-command yes`, which `docker-compose.yml` already sets.

-  **E5. Break it yourself: KEYS on a real keyspace.**

- Seed: `docker exec redis-study redis-cli DEBUG POPULATE 5000000` (5M keys, ~30s).

- Run: `docker exec redis-study redis-cli --latency` in terminal 1 (live latency meter). In terminal 2: `docker exec redis-study redis-cli KEYS 'key:*' > /dev/null`.

- Expected: the latency meter's `max` jumps from ~0.5ms to hundreds of ms → seconds while KEYS scans.

- Now the right way: `docker exec redis-study redis-cli --scan --pattern 'key:1234*' | head` — cursor-based, no stall (watch the meter stay flat).

- Teaches: why KEYS is banned in prod and SCAN exists.

Note for this lesson: 4 million keys used 238 MB on the local run. So 5 million keys likely pass the container's 256 MB cap, and `allkeys-lru` evicts some of them. This is inferred from the local run, not measured in the container. Check `DBSIZE` after seeding. Expect a few hundred ms of stall, not seconds. On the local run, `KEYS key:*` over 1 million keys took about 93 ms. The SCAN for `key:1234*` returned 111 keys and left no SLOWLOG entry.

-  **E6. Read the slow log like an on-call.**

- Run: `docker exec redis-study redis-cli SLOWLOG GET 10`

- Expected: your E5 `KEYS` command listed with its microsecond duration (anything >10ms lands here by default).

- Verify: `docker exec redis-study redis-cli CONFIG GET slowlog-log-slower-than` → 10000 (µs).

- Teaches: SLOWLOG is investigation step #1 for any "Redis is slow" page.

Note for this lesson: the logged time is execution only. It excludes client I/O and the time a command waited in the queue. So the GETs that waited behind the KEYS in E5 are not in the log. Look for them on the `--latency` meter instead.

-  **E7. Atomicity for free: the INCR race that isn't.**

- Run: `for i in $(seq 1 50); do docker exec redis-study redis-cli INCR race:counter & done; wait; docker exec redis-study redis-cli GET race:counter`

- Expected: exactly `50`. Every time. No lost updates despite 50 concurrent clients.

- Contrast: sketch (on paper) the GET-add-SET version and where two clients interleave to lose an update.

- Teaches: single-threaded execution = every command is a critical section — the foundation for Phase 3's locks and rate limiters.

Note for this lesson: do the contrast for real, not on paper. On the local run, 200 processes that each ran GET and then SET left the counter at 5. Starting 50 `docker exec` processes at once is slow, and that step was not run here.

-  **E8. TTL discipline — the no-TTL outage exercise.**

- Run: `docker exec redis-study redis-cli SET orphan:1 payload` (no TTL), then `docker exec redis-study redis-cli SET good:1 payload EX 300`.

- Inspect: `TTL orphan:1` → -1 (never expires); `TTL good:1` → ~300.

- Now: `docker exec redis-study redis-cli CONFIG GET maxmemory-policy` → `allkeys-lru` in this sandbox, but the shared production clusters run AWS-default `volatile-lru` — which may evict ONLY keys with a TTL. Under `volatile-lru`, what happens as `orphan:*` keys accumulate to maxmemory? (Writes start failing OOM: nothing is evictable.)

- Teaches: the no-TTL key is unevictable ballast under volatile-* policies — the exact mechanism behind the 4h37m LLM-gateway outage on a shared cluster.

Note for this lesson: the phase named this exercise after an internal incident, and that name is removed here. To see the failure, not only reason about it, the local run set `maxmemory 50mb` and `volatile-lru` and created 2,000,000 keys with no TTL. Then `SET good:1 v EX 300` returned the OOM error, and `evicted_keys` stayed at 0.

-  **E9. Data structures beyond strings, in 2 minutes.**

- Run: `docker exec redis-study redis-cli HSET sess:u42 name raghu team coaching` then `HGETALL sess:u42`; `SADD sess:index u42 u43` then `SMEMBERS sess:index`; `ZADD jobs:inprogress 1720000000 job:1` then `ZRANGEBYSCORE jobs:inprogress -inf +inf`.

- Expected: hash, set, and zset round-trips — you just reproduced the login service's session shape and the translation workers' job-marker shape.

- Teaches: the structures in 0.1's table are one command away, not exotic.

Note for this lesson: Phase 1 teaches these types in depth, with its own labs. The table this exercise refers to is in the Go deeper block of the first section.

-  **E10. Break it: fill memory and watch eviction.**

- Run: `docker exec redis-study redis-cli DEBUG POPULATE 3000000` a few times and watch `docker exec redis-study redis-cli INFO memory | grep -E 'used_memory_human|maxmemory_human'` and `INFO stats | grep evicted_keys`.

- Expected: `used_memory` approaches the 256mb cap from docker-compose.yml, then `evicted_keys` starts climbing (allkeys-lru is evicting).

- Teaches: what maxmemory pressure looks like in INFO — the metrics you'd alert on in Datadog.

Note for this lesson: a repeated `DEBUG POPULATE 3000000` adds nothing, because it skips keys that already exist. The default prefix is `key`. Give each run a new prefix, for example `DEBUG POPULATE 3000000 run2`.

Cleanup: `docker exec redis-study redis-cli FLUSHALL` (fine here — sandbox; now say out loud why you'd never run it on a shared production cluster).

## Checkpoint questions

Answer each question in your own words before you open its sketch. Then test your answer against the lab.

**Q1. Your dashboard shows p99 latency spikes in the same minute on four services that share one cluster. Nothing was deployed. The spikes last 3 to 8 seconds and come back at random times. Using only this phase, what is your first hypothesis, which Redis command do you run first, and which three command shapes are the likely cause?**

Answer sketch. The hypothesis is head-of-line blocking: one slow command holds the main thread, so every client of every service waits. Run `SLOWLOG GET 10` first. There are three likely shapes. The first is `KEYS` on a large keyspace. The second is a full read of a huge collection, such as `SMEMBERS`, `HGETALL` or `LRANGE 0 -1`. The third is a long Lua script or Function. Remember that SLOWLOG shows only the cause, never the waiting commands. If SLOWLOG is empty, check the housekeeping on the same thread. Look for a fork for a snapshot, many keys that expire in one second, or eviction at `maxmemory`.

**Q2. A teammate says: "The grading flow makes 40 sequential GETs per submission, one per rubric item. Each GET takes about 0.4 ms, so that is 16 ms, which is fine." Show why the 16 ms is waste, name the fix, and estimate the time after it. At what size does the same mistake cost 200 ms?**

Answer sketch. The server spends about 0.27 µs on each GET, so about 11 µs on all 40. The other 16 ms are 40 round trips. The fix is pipelining, or better, one `MGET` with all 40 keys. After the fix the cost is about one round trip plus 40 small costs: 0.4 ms plus 40 times 0.8 µs, about 0.43 ms. The same loop of 0.4 ms calls costs 200 ms at 500 calls. E3 measured that on Docker: 208.9 ms for 500 keys.

**Q3. An LLM gateway's keys with no TTL filled a shared cluster that runs volatile-lru, and an upload service on the same cluster went down. Walk the mechanism from end to end. Why did volatile-lru not save the cluster? Why did a different service go down? Name one code change and one architecture change that would each have prevented it.**

Answer sketch. Under `volatile-lru` only keys with a TTL can be evicted. Once the memory held almost only the gateway's keys, the policy behaved like `noeviction`. Before each write, `performEvictions()` could free nothing, so Redis rejected every write that needed memory with the OOM error. The upload service shared that one memory pool, so its writes failed too, although its own keys were fine. `evicted_keys` stopped growing, so an alert on evictions stayed silent. Code change: set a TTL on every cache key, and check for it in review. Architecture change: give each domain or major use case its own cluster, as bsport did after its outage. Also alert on `used_memory` against `maxmemory`.

**Q4. A colleague says: "Redis is single-threaded, so it cannot scale. We should move the settings cache to DynamoDB, which scales without limit." Give a two-part answer. First, what is wrong with "cannot scale"? Second, what would break if the three-layer settings cache moved to DynamoDB?**

Answer sketch. First, one command thread serves a lot, because each command costs well under a microsecond. With I/O threads and key prefetching, one Valkey 8 instance served 1.19 million requests a second. Stack Overflow peaked at 86,982 commands a second, with about 2% average CPU. Cluster mode then spreads the keys over many primaries, and each primary has its own main thread, which a later phase teaches. Second, the settings design depends on one cheap, instant, atomic delete of a scope marker that every consumer sees at once. In DynamoDB each check becomes a database request, with its own latency and its own price per request. The marker delete would no longer be one cheap shared operation, and DynamoDB's TTL deletes items only "typically within a few days".

**Q5. The platform needs only one welcome email per new user, even if Kafka delivers the signup event three times. One service solved a similar problem for invitation emails with a hand-written SETNX lock. Sketch the SET NX EX approach. Give the exact command and what the TTL protects against. Say what happens if the process crashes after the SET but before the email is sent. Then say why this is most of the answer but not all of it.**

Answer sketch. Run `SET welcome:<user_id> 1 NX EX <ttl>`, with a TTL longer than the window in which Kafka can deliver the event again. The first delivery sets the key and sends the email, and later deliveries get nil and skip. The TTL keeps the keys from filling memory forever, which matters under `volatile-lru`. If the process crashes after the SET and before the send, the key exists. So no retry sends the email, and the user gets none. The phase on locking covers the rest. It says how long the key should live, and how to mark "in progress" against "done". It also says why a key with a TTL is not a safe lock.

**Q6. You run blocking_demo, and the fast reader stalls for 2 s. A sceptic says: "That is because both clients share one Go process. Services on separate pods would not block each other." Design the two-pod experiment that answers this, and explain why separate processes, pods and network cards change nothing.**

Answer sketch. Run a GET loop that logs each latency with a timestamp in pod A, on one node. From pod B, on another node, send `DEBUG SLEEP 2` to the same Redis, and log the time you sent it. Expect one GET in pod A to take about 2 s, starting at the time pod B sent the sleep. The wait happens inside the server, because the main thread runs one command at a time. Pods, processes, connections and network cards only change the path to the server. Even an I/O thread that parses the GET must hand it to the busy main thread to run.

## Cheatsheet

**Practice: open the cheatsheet**

```
MENTAL MODEL
  one main thread runs ALL commands, one at a time  → atomic for free, blocking for free too
  same thread runs expiry, eviction, fork()         → housekeeping can stall every client
  I/O threads read, parse, write; never execute     → io-threads default 1 (off)
  cost of a call = one round trip                   → server GET ≈ 0.27 µs; loopback p50 ≈ 94 µs
  N sequential calls = N × RTT                      → pipeline ≈ 1 RTT + N × ~0.8 µs
  pipeline speed-up ceiling ≈ RTT / per-cmd work    → ~120x local loopback, 224x at 500 keys on Docker
  one slow command = every client waits             → shared cluster: every SERVICE waits
  memory is one fixed pool (maxmemory)              → no-TTL keys under volatile-* = unevictable

INVESTIGATION COMMANDS (in incident order)
  redis-cli --latency                    live latency meter, client view
  SLOWLOG GET 10                         commands over 10 ms; execution time only
  INFO commandstats                      usec_per_call per command type
  INFO memory                            used_memory vs maxmemory
  INFO stats | grep evicted_keys         is eviction happening? (0 can mean "nothing evictable")
  redis-cli --bigkeys                    find the huge collections (Phase 5)
  CONFIG GET maxmemory-policy            what happens at the memory limit
  redis-cli --intrinsic-latency <sec>    latency of the host itself
  CONFIG GET latency-monitor-threshold   0 = latency monitor off (default)

BANNED IN PROD → REPLACEMENT
  KEYS pattern          → SCAN (cursor)          FLUSHALL / FLUSHDB → FLUSHALL ASYNC
  SMEMBERS (huge set)   → SSCAN                  DEL (huge key)     → UNLINK
  HGETALL (huge hash)   → HSCAN                  long Lua / Function → break up, rethink
  MONITOR on shared prod → no: can cut throughput by more than 50%
  debug commands        → block with ACL, e.g. -@dangerous (not tested here)

ATOMICITY
  INCR, SET k v NX EX n, one Lua script     atomic
  GET then SET from app code                not atomic (local run: 5 of 200 survived)
  a pipeline                                not a transaction
  busy-reply-threshold 5000 ms              then -BUSY; SCRIPT KILL only if no write yet

MEMORY AND EVICTION
  open-source default: noeviction           ElastiCache default: volatile-lru
  Redis 8.6+: 10 policies (adds allkeys-lrm, volatile-lrm); Valkey 9.1.2: 8
  OOM error: "OOM command not allowed when used memory > 'maxmemory'"
  alert on used_memory / maxmemory and client OOM errors, not only evicted_keys

DEFAULTS (Redis 8.10.2)
  hz 10    maxmemory-samples 5    maxmemory-eviction-tenacity 10 (500 µs slices)
  slowlog-log-slower-than 10000 µs    slowlog-max-len 128    lookahead 16
  lazyfree-lazy-* no (Valkey 9.1.2: yes)    io-threads 1 (max 128)

THE FIELD
  Memcached: opaque values, multi-threaded, no structures, no persistence, no pub/sub
  DynamoDB:  durable KV, priced per request, TTL deletes "within a few days"
  Redis:     in-memory structures + atomic commands; cache, counters, locks, queues, sessions
  Valkey:    BSD-3 fork of Redis 7.2.4; same commands, different defaults

RUNNING CASE FACTS (from the phase's survey of the platform)
  about 34 services, several shared ElastiCache clusters, AWS default volatile-lru
  one region cluster-mode ON (Redis 5.0.6), another cluster-mode OFF (Redis 6.x)
  settings cache: delete a scope marker on write + response cache TTL 3600 s
                  + a separate 600 s pure-TTL cache
  incidents: no-TTL keys from an LLM gateway (4h37m), cacheable:false
             (300/min → 30,000/min), stale shard map after a cluster-mode change,
             a client that assumed 2 replicas (2 s in staging)

THE ONE FORMULA
  latency_seen_by_caller ≈ RTT × round_trips + queue_delay_behind_slow_commands
  (server execution time is ~0, until a slow command or housekeeping makes it not)
```

## Sources

**Practice: open the sources**

This course's research opened every URL in the first four groups on 2026-10-18. The measurements of the local run came from the course's own Go programs and `redis-cli`, over TCP loopback. The first section's evidence note gives the build and the machine. The last group is the phase's own reading list, with a note on each entry.

**Redis and Valkey source, and the official docs**

- **Redis source at tag 8.10.2**: https://raw.githubusercontent.com/redis/redis/8.10.2/src/server.c, with [networking.c](https://raw.githubusercontent.com/redis/redis/8.10.2/src/networking.c), [server.h](https://raw.githubusercontent.com/redis/redis/8.10.2/src/server.h), [evict.c](https://raw.githubusercontent.com/redis/redis/8.10.2/src/evict.c), [expire.c](https://raw.githubusercontent.com/redis/redis/8.10.2/src/expire.c), [config.c](https://raw.githubusercontent.com/redis/redis/8.10.2/src/config.c) and [debug.c](https://raw.githubusercontent.com/redis/redis/8.10.2/src/debug.c). The event loop, the I/O thread hand-off, eviction before each command, expiry constants and every default named on this page.

- **redis.conf at 8.10.2 and at 7.2.0**: https://raw.githubusercontent.com/redis/redis/8.10.2/redis.conf and https://raw.githubusercontent.com/redis/redis/7.2.0/redis.conf. The deprecated `io-threads-do-reads`, the 10 policies, `lookahead` and the lazyfree defaults.

- **Valkey 9.1.2**: https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/valkey.conf and https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/src/config.c. Valkey's defaults: `noeviction`, 8 policies, every lazyfree setting on.

- **Redis 8.0.0 release notes**: https://github.com/redis/redis/releases/tag/8.0.0. The new I/O threading and the data types added to the core.

- **Valkey 9.0.0-rc1 release notes**: https://github.com/valkey-io/valkey/releases/tag/9.0.0-rc1. Numbered databases in cluster mode, added in Valkey 9.0.

- **Diagnosing latency issues**: https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/. The single thread, fork and expiry stalls, network round trips, the checklist with `--intrinsic-latency`.

- **Pipelining**: https://redis.io/docs/latest/develop/using-commands/pipelining/. System calls per command, the 10,000-PING measurement, the batch size advice.

- **Eviction**: https://redis.io/docs/latest/develop/reference/eviction/. The volatile policies acting like `noeviction`, and the LRM policies.

- **KEYS**: https://redis.io/docs/latest/commands/keys/. 1 million keys in 40 ms on an entry-level laptop.

- **FLUSHALL**: https://redis.io/docs/latest/commands/flushall/. The `ASYNC` option and `lazyfree-lazy-user-flush`.

- **SLOWLOG GET**: https://redis.io/docs/latest/commands/slowlog-get/. The logged time excludes client I/O.

- **MONITOR**: https://redis.io/docs/latest/commands/monitor/. The warning about more than 50% lost throughput.

- **Redis FAQ**: https://redis.io/docs/latest/develop/get-started/faq/. Why one thread: Redis is usually memory or network bound.

- **Redis licences**: https://redis.io/legal/licenses/. BSD-3, then RSALv2 or SSPLv1, then AGPLv3 as a third choice.

**Valkey, AWS and DynamoDB**

- **Valkey, Unlock one million RPS**: https://valkey.io/blog/unlock-one-million-rps/. 360K to 1.19M requests a second with 8 I/O threads, and its conditions.

- **Linux Foundation, Valkey launch**: https://www.linuxfoundation.org/press/linux-foundation-launches-open-source-valkey-community. The fork from Redis 7.2.4 under BSD-3.

- **ElastiCache engine parameters**: https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/ParameterGroups.Engine.html. Default `volatile-lru`, and the Valkey parameter groups.

- **ElastiCache enhanced I/O multiplexing**: https://aws.amazon.com/blogs/database/enhanced-io-multiplexing-for-amazon-elasticache-for-redis. The 72% gain at 5,200 clients.

- **ElastiCache 7.1, 500 million requests a second per cluster**: https://aws.amazon.com/blogs/database/achieve-over-500-million-requests-per-second-per-cluster-with-amazon-elasticache-for-redis-7-1. I/O threads that parse and format replies.

- **DynamoDB TTL**: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html. Expired items deleted typically within a few days.

**Incidents**

- **Harness, Feature Flag services not responding**: https://status.harness.io/incidents/j6qd0qmfnchy. KEYS on a hot path, probes on Redis, 14 minutes of 502 errors.

- **Trello, slow or unavailable**: https://trello.status.atlassian.com/incidents/k3v15xtb50rz. A debugging command in production, a failover, 7 minutes down.

- **Spring Data Redis issue 1413**: https://github.com/spring-projects/spring-data-redis/issues/1413. A cache clear that called KEYS and pinned CPU.

- **Webflow status incident**: https://status.webflow.com/incidents/7pbl0qlc61kf. A Redis URL that pointed at one node through a failover.

- **OpenAI, March 20 ChatGPT outage**: https://web.archive.org/web/2023id_/https://openai.com/blog/march-20-chatgpt-outage. A cancelled request that left its reply on a pooled connection.

- **Pendo status incident**: https://status.pendo.io/incidents/g8nfbs1vdn69. Cache keys with no expiry, about 60% errors for 90 minutes.

- **GitLab, Redis latency spikes**: https://about.gitlab.com/blog/how-we-diagnosed-and-resolved-redis-latency-spikes/. Eviction at `maxmemory` that saturated the main thread.

- **Slack, Scaling Slack's Job Queue**: https://slack.engineering/scaling-slacks-job-queue/. A full Redis that could not even dequeue.

- **Twilio, billing incident post-mortem**: https://www.twilio.com/en-us/blog/company/communications/billing-incident-post-mortem-breakdown-analysis-and-root-cause-html. A restart that loaded no data and charged cards again.

- **antirez, Twilio incident and Redis**: http://antirez.com/news/60. Full resync after any disconnect before Redis 2.8.

- **Redis Cloud, February 8th outage post-mortem**: https://redis.io/blog/february-8th-outage-post-mortem/. Databases without persistence that came back empty.

- **bsport, eliminating Redis as a single point of failure**: https://engineering.bsport.io/how-we-eliminated-redis-as-a-single-point-of-failure-2729c22008b5. One shared Redis used as a database, then one cluster per domain.

**How companies run Redis**

- **GitHub, a sharded, replicated rate limiter in Redis**: https://github.blog/engineering/infrastructure/how-we-scaled-github-api-sharded-replicated-rate-limiter-redis/. Lua for atomicity, and the one-second wobble from a value used outside the script.

- **Swiggy, batch writes with pipelining**: https://bytes.swiggy.com/optimizing-batch-writes-to-redis-using-pipelining-d480ebaf4653. Write time down 90%.

- **Swiggy, 2x latency improvement**: https://medium.com/swiggy-bytes/2x-improvement-in-latency-in-swiggy-data-science-platform-6101b7607530. Batch reads, p99 from 144 ms to 71 ms.

- **Shopify, server-side storefront rendering**: https://shopify.engineering/simplify-batch-cache-optimized-server-side-storefront-rendering. An in-process memo that avoids 16 to 20 calls per request.

- **Shopify, Redis replaced with MySQL for inventory reservations**: https://shopify.engineering/scaling-inventory-reservations. Atomicity with the ledger mattered more than speed.

- **Stack Overflow, how we do app caching**: https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/. 2% CPU, a 0.17 ms round trip, and a separate connection for large values.

- **Uber, CacheFront**: https://www.uber.com/en-GB/blog/how-uber-serves-over-40-million-reads-per-second-using-an-integrated-cache/. About 3,000 Redis cores in place of about 60,000 database cores.

- **High Scalability, how Twitter uses Redis**: https://highscalability.com/how-twitter-uses-redis-to-scale-105tb-ram-39mm-qps-10000-ins/. A summary of a talk: Redis over Memcache for small updates to large timelines.

**From the phase's reading list**

- **How Redis Single-Threaded Architecture Works**: https://oneuptime.com/blog/post/2026-03-31-redis-how-redis-single-threaded-architecture-works/view. Out of date: it shows `io-threads-do-reads`, which Redis 8 deprecated, and it cites no sources. The latency and pipelining pages above cover the same ground.

- **Redis Multi-Threaded Network Model, SoByte**: https://www.sobyte.net/post/2022-03/redis-multi-threaded-network-model/. Not opened for this lesson. It predates the Redis 8 I/O thread design.

- **Learn Nearly Everything About Redis Through An Incident, Alibaba Cloud**: https://www.alibabacloud.com/blog/learn-nearly-everything-about-redis-through-an-incident_602055. Not opened for this lesson.

- **antirez's YouTube channel**: https://www.youtube.com/@antirez. Not opened for this lesson.

- **Changelog #631, Antirez returns to Redis**: https://changelog.com/podcast/631. The episode exists. Its content was not reviewed for this lesson.

- **Engineering Philosophy: antirez**: https://blakecrosley.com/blog/engineering-philosophy-antirez. Not opened for this lesson.

- **When Redis Fails Over But Your Service Doesn't**: https://medium.com/@itsnarayan/when-redis-fails-over-but-your-service-doesnt-a-postmortem-from-the-trenches-42f69fe00047. Not opened for this lesson. The Webflow incident above shows the same failure class.

- **ElastiCache Redis vs Memcached**: https://jayendrapatil.com/aws-elasticache-redis-vs-memcached/. Not opened for this lesson.

- **When to use ElastiCache vs DynamoDB**: https://www.dragonflydb.io/guides/when-to-use-elasticache-vs-dynamodb. Not opened for this lesson, and written by a vendor.

- **Redis commands**: https://redis.io/commands/. The time complexity of every command, which is the production guidance for O(N) commands.

- **Redis in Action, Josiah Carlson**: chapters 1 and 2 walk through the data structures with real uses. The rest maps to later phases.
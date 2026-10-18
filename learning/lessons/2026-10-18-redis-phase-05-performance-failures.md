This phase follows one shared Redis cluster. The platform of Phase 0 runs about 34 services on several shared, managed clusters. This cluster is one of them, and it uses the provider's default eviction policy. One of the services is an AI agent, and it keeps the memory of each chat session in Redis. That chat memory is this lesson's own example. In Phase 4 you learned how such a cluster saves its data, copies it to replicas and fails over. This phase covers the two pages that an on-call engineer gets for it: "Redis is slow" and "Redis is out of memory".

1. Monday The p99 of the tenant-settings read jumps from 1 ms to 150 ms for about one second, every few minutes. `SLOWLOG GET` is empty.
2. Tuesday One shard runs at 100% CPU and the other five at about 30%. The team adds six shards, and the hot shard stays at 100%.
3. Day 9 Every service on the cluster gets `OOM command not allowed` on writes. Reads still work.
4. Night During the nightly `BGSAVE`, the operating system kills the Redis process, although `used_memory` was under `maxmemory`.

The running case. The days and numbers are an illustration, not measured. Each concept below explains one line of it.

None of these four lines is a bug in Redis. Each one comes from the way the services use Redis, and each one shows up in a command that a person can run in minutes. The hard part is to know what each command measures, and what it cannot see. The table maps each symptom to its cause and to the first tool you run.

| What you see | The cause | The first tool | Where |
|---|---|---|---|
| Many fast calls per request, no slow command | Too many round trips | Count calls per request, then `MGET` or a pipeline | Phase 0, recap below |
| Every client freezes for tens of milliseconds | A slow O(N) command | `SLOWLOG GET`, `INFO latencystats` | c1 |
| Spikes, and `SLOWLOG` is empty | Main-thread work that is not a command | `LATENCY LATEST`, `LATENCY DOCTOR` | c1 |
| One key holds millions of elements | A big key | `--memkeys`, `--bigkeys`, `MEMORY USAGE` | c2 |
| One shard is hot and the others are idle | A hot key | `--hotkeys`, `HOTKEYS START`, `CLUSTER SLOT-STATS` | c3 |
| Writes fail with OOM, reads work | The eviction policy meets keys without a TTL | `INFO memory`, `INFO errorstats` | c4 |
| Throughput drops at the memory cap, or the process is killed | Eviction work and memory outside `used_memory` | `INFO memory`, `INFO persistence` | c5 |

What you must know, in five claims. Each one is taught below, in this order.

1. **Latency is round trip plus waiting behind all main-thread work plus your command, and SLOWLOG sees only your command.** Find the cause of a p99 spike, also when SLOWLOG is empty.
2. **A big key costs O(N) in every whole-key operation, even expiry and eviction, and UNLINK protects only your own delete.** Predict which operation on a big key will freeze the server, and remove the key safely.
3. **Sharding spreads keys, not requests, so a hot key loads one thread on one shard however many shards you add.** Find the hot key and stop its requests before they reach that thread.
4. **Volatile policies evict only keys with a TTL, so keys without one turn a full cache into noeviction for everyone.** Choose a policy and audit TTLs before a shared cluster fills.
5. **Reaching maxmemory is a latency event, and memory outside used_memory, such as fork copies, decides if Redis survives.** Size a node from peak RSS, and read the memory fields that matter.

The tables, the sections and the lab tags call these five claims c1 to c5, in this order.

## What you bring from Phases 0 to 4

This phase uses six ideas from earlier phases. Each card says it again in plain words.

#### One main thread (Phase 0)

Redis runs every command on one *main thread*, one command at a time. So one slow command makes every other client wait. Redis 8 and Valkey have I/O threads that read sockets and parse requests, but the commands still run on the main thread.

#### The round trip (Phase 0)

A `GET` runs in about 1 µs on the server. Your client waits far longer for the network *round trip*. That is the time for the request to reach Redis and the reply to come back. Phase 0 measured 94 µs at p50 on loopback, and about 300 to 600 µs on Docker Desktop. So 500 calls in a loop cost about 500 round trips. Phase 0 found a pipeline ceiling near 120x on loopback, and 224x for 500 keys on Docker Desktop.

#### Encodings (Phase 1)

Redis stores a small hash, set or list in a compact `listpack`, and a large one in a hash table. A hash of 200 small fields in one listpack costs several times less memory than 200 String keys. Phase 1 measured 6.2 times less, with hashes of up to 100 fields.

#### TTLs and cache misses (Phase 2)

A TTL is the time a key has left before Redis deletes it. A cache multiplies load, because every miss sends a request to the source behind it.

#### Fork and copy-on-write (Phase 4)

For a `BGSAVE` or a replica's full sync, Redis forks a child process that writes a snapshot. Parent and child share memory pages, and the operating system copies a page when the parent changes it.

#### Hash slots and replicas (Phase 4)

In a cluster, each key maps to one of 16,384 hash slots, and each slot lives on one primary. Replicas copy a primary and can serve reads.

Phase 0 already taught the round trip as the first thing to check. This phase starts where that check finds nothing: every call is batched, and the p99 still jumps.

## Why does one slow command delay every client?

*One O(N) command holds the main thread, so every client waits behind it.*

The cards above say that commands run one at a time on the main thread. On Monday, the tenant-settings read in the running case is a single `GET`, and it still takes 150 ms at the p99. So the time went somewhere other than the `GET` itself.

Every request to a Redis node joins one line in front of the main thread. A command whose work grows with the size of a key or of the whole keyspace is an *O(N) command*. While it runs, the line does not move. A fast `GET` that arrives during that time waits for the whole run, and its client sees the wait as its own latency.

**Predict: a client sends PING every 1 ms for a minute. Another client runs KEYS on 1,000,000 keys, which takes about 140 ms. What are the PING p50 and the PING maximum?**

The p50 stays at about 0.17 ms, and the maximum is about 94 ms. Almost every PING arrives when KEYS is not running, so the median does not move. The PINGs that arrive during KEYS wait for the rest of its run. So a slow command shows up in the tail of other clients' latency, and a dashboard that shows only the mean or the median hides it. The guess "every client gets a little slower" is reasonable for a multi-threaded server. Redis has one command thread, so most clients see nothing and a few see the whole freeze.

#### A PING every 1 ms while another client runs KEYS on 1,000,000 keys

- PING client: 0.17 ms | 0.17 ms | waits up to 94 ms | 0.17 ms

- KEYS client: idle | idle | KEYS k:* runs 133 to 148 ms | idle

Steps 1 and 2: each PING gets its reply in about 0.17 ms.

Step 3: KEYS holds the main thread, and a PING that arrives now waits until KEYS ends.

Step 4: KEYS is done, and PINGs return to 0.17 ms.

Measured in one run of the course research on Homebrew Redis 8.10.1, an x86_64 build under Rosetta with libc malloc, on an Apple M4 Pro, over loopback. Widths are to scale only roughly.

The commands that do this share one trait. They touch every element of a large collection, or every key in the keyspace, in one call. Each has a safe form that does the same work in small pieces.

| Blocking command | Cost | Safe form |
|---|---|---|
| `KEYS <pattern>` | O(N), the whole keyspace | `SCAN` with a cursor |
| `SMEMBERS` on a big set | O(N) | `SSCAN` |
| `HGETALL` on a big hash | O(N) | `HSCAN`, or `HMGET` with the fields you need |
| `LRANGE key 0 -1` on a big list | O(N) | `LRANGE` with a bounded range |
| `ZRANGE` over a huge range | O(log N + M) | A bounded range, or `LIMIT offset count` |
| `DEL` on a big key | O(N) to free the memory | `UNLINK`, which frees in a background thread |
| `FLUSHALL` or `FLUSHDB`, synchronous | O(N) | `FLUSHALL ASYNC`, or do not run it in production |
| A long Lua script | The whole script | Keep scripts small, with no loop over a big key |

The phase's `slow_commands` program measured the gap on 200,000 keys and a hash of 200,000 fields.

- HGETALL, 200,000 fields: 62 ms
- KEYS k:*, 200,000 keys: 33 ms
- HSCAN, one batch: 1.1 ms
- SCAN, one batch of 501 keys: 0.65 ms
- HMGET f1 f2 f3: 0.4 ms

The SCAN family works with a *cursor*, a number that marks where the last call stopped. You call it again with the returned cursor until the cursor comes back as 0, and each call returns a small batch. A key that exists for the whole scan comes back at least once. A key that is added or removed during the scan may or may not appear, and the same key can come back more than once. So your code must accept duplicates. This weaker promise is the reason SCAN is safe, because it never builds the whole keyspace in one blocking call.

`SLOWLOG` is the tool that finds these commands. Redis records every command that runs longer than `slowlog-log-slower-than` in an in-memory ring buffer. The default is 10,000 µs, which is 10 ms, in Redis 8.10.2. `SLOWLOG GET 10` shows the last ten entries, each with its duration and its arguments.

```text
127.0.0.1:6379> SLOWLOG GET 2
1) duration: 29.781ms  args: [hgetall bighash]
2) duration: 23.194ms  args: [keys k:*]
```

> The phase shows this output with 29.8 ms and 23.2 ms, but its own measured values above it are 62 ms and 33 ms. Read the example for its format. The durations in it are not a measurement.

**A real case.** A cache library for Java called `KEYS` to clear a cache. In production, Redis reached 100% CPU and stopped serving other requests. `SLOWLOG` showed `KEYS`, so the team found the cause there. The application code never called `KEYS` itself. The call was inside the library.

**Evidence**

PING and KEYS numbers: one run each in the course research, Redis 8.10.1 from Homebrew, an x86_64 build under Rosetta with `malloc=libc`, Apple M4 Pro, 24 GB RAM, loopback client, no persistence. The 200,000-key numbers are the phase's own `slow_commands` run, with no host stated. The 40 ms figure is from the KEYS page, https://redis.io/docs/latest/commands/keys/. The SCAN promise, including duplicates, is from https://redis.io/docs/latest/commands/scan/. The library case is Spring Data Redis issue 1413, opened in 2018: https://github.com/spring-projects/spring-data-redis/issues/1413.

**Remember.** One O(N) command freezes every client on the node for its whole run.

**Trap.** `KEYS` in application code passes review and freezes a 40-million-key production node.

**Try.** Run E3, then find `KEYS *` and its duration in `SLOWLOG GET 3`.

**Go deeper: the round-trip arithmetic, the three ways to batch, and two teams that measured it**

This block holds the phase's section on pipelining, because Phase 0 already taught it. It is the first check when latency is high and no single command is slow.

```text
   N sequential GETs:                    N pipelined GETs:
   latency ≈ N × RTT                     latency ≈ 1 × RTT + N × ~1µs
   500 × 400µs = 200ms                   1 × 400µs + 500µs ≈ 0.9ms
                                         → measured 224x speedup (Phase 0, Docker Desktop)
```

A pipeline sends N commands in one write and reads the N replies in one pass. The server does the same work, and only the number of network trips changes. Use the three ways in this order, when they apply:

1. **A multi-key command.** `MGET`, `MSET`, `HMGET` and `SADD` with many members do N operations in one command and one round trip. In cluster mode, a multi-key command needs all keys in one slot, so the keys need a hash tag, such as `{user42}`.
2. **A pipeline.** Use `rdb.Pipeline()` in go-redis when the commands differ, such as `GET`, `INCR` and `EXPIRE`.
3. **A Lua script or `MULTI`.** Use these when the batch must also be atomic. Phase 3's compare-and-delete is a Lua example.

The N+1 Redis problem is a Redis call inside a loop over a collection. It costs nothing in development at N=3, and 200 ms in production at N=500. A loop such as `for _, id := range ids { rdb.Get(ctx, key(id)) }` passes review and slows the request as `ids` grows. When latency is high and no command is in `SLOWLOG`, look for this loop before anything else.

The gain depends on the round trip. The course research ran one client over loopback, where the round trip is about 0.1 ms. It measured 10,051 requests per second with no pipeline, 129,282 with 16 commands per pipeline and 414,079 with 100. That is 41 times. Over a real network the round trip is longer, so the gain is larger. That is inferred, and it was not measured here.

**Swiggy** found that 50% to 70% of the time of its feature-store write jobs went to Redis writes, one round trip per command. The team sent the writes in pipelines of a fixed batch size, with retries and backoff. On a few write-heavy jobs, this cut the Redis write time by 90% and the cost by about 60%. Very large batches filled socket buffers, so each workload had its own best batch size. A second Swiggy change batched feature reads with `MGET` and pipelines. The p99 of order assignment fell from 144 ms to 71 ms, at batch size 30 and over 5,000 predictions per second.

**Evidence**

The 224x and the 300 to 600 µs come from the Phase 0 demo on Docker Desktop. The 94 µs and the ceiling near 120x come from the local run of Phase 0, over TCP loopback outside Docker. Phase 0 states the build and the network for both runs. The loopback numbers are the course research's `redis-benchmark -t get -c 1` run at `-P 1`, `-P 16` and `-P 100`, on Homebrew Redis 8.10.1 under Rosetta with libc malloc, Apple M4 Pro, loopback. Swiggy write case: https://bytes.swiggy.com/optimizing-batch-writes-to-redis-using-pipelining-d480ebaf4653 (2023). Swiggy read case: https://medium.com/swiggy-bytes/2x-improvement-in-latency-in-swiggy-data-science-platform-6101b7607530 (2022).

**Go deeper: KEYS at 1 million keys, Lua scripts, ZRANGE LIMIT, Valkey's command logs, I/O threads, and a KEYS warning from Stack Overflow**

- **Lua scripts.** A script runs on the main thread, and no other command runs during it. After `busy-reply-threshold` ms, 5,000 by default and formerly `lua-time-limit`, Redis logs "Slow script detected". Other clients then get `-BUSY`, and the script keeps running. `SCRIPT KILL` works only if the script has not written. Otherwise the reply is `-UNKILLABLE`, and the only exit is `SHUTDOWN NOSAVE`, which loses the data since the last save. Source: `src/script.c` and `src/config.c` at tag 8.10.2.
- **ZRANGE and LIMIT.** `LIMIT offset count` applies only with `BYSCORE` or `BYLEX`. This is inferred from the earlier audit, and the ZRANGE page was not opened. For a rank range, bound the start and stop instead.
- **KEYS on 1,000,000 keys.** The course research measured `KEYS k:*` at 133 to 148 ms over three runs, and one `SCAN 0 COUNT 1000` at 0.25 to 0.30 ms. The `KEYS` documentation gives 40 ms for 1 million keys on an entry-level laptop. So the cost per key differed by about three times. The pattern, the libc build and the x86_64 emulation under Rosetta may explain the gap, but its cause was not isolated. Phase 0 timed `KEYS key:*` over 1,000,000 keys at 92.6 to 93.6 ms on the same build. The two runs used other key names, and this page does not record how either run created its keys. So that gap is not explained either.
- **Valkey `COMMANDLOG`.** On Valkey 8.1 and later, `SLOWLOG` is part of a wider tool. Its threshold is `commandlog-execution-slower-than`, also 10,000 µs by default, and the old `slowlog-*` settings are deprecated there. Since Valkey 8.1.0 it keeps three logs. The first is slow execution. The second is large requests, with a default threshold of 1,048,576 bytes. The third is large replies, which finds `HGETALL` and `SMEMBERS` on big keys directly. Source: valkey.conf at 9.1.2, lines 2135 to 2200, and https://valkey.io/commands/commandlog-get/.
- **I/O threads.** In Redis 8, an I/O thread reads and parses a request, then hands the client to the main thread to run the command. Pub/sub, `MONITOR`, blocked and tracking clients stay on the main thread. `io-threads` is 1, which means off, by default. In Valkey 9.1, the main thread owns all clients and sends read, write and poll jobs to a shared queue. Threads start when the main thread is busy more than 30% of the time. In both, a slow command still blocks every client. Source: `src/iothread.c` at 8.10.2 and `src/io_threads.c` at Valkey 9.1.2.
- **AWS ElastiCache multiplexing** shows what I/O threads buy. At 5,200 clients on an r6g.xlarge, with 80% GET and 20% SET, throughput rose from 202,770 to 349,239 operations per second, a 72% gain. At 400 clients the gain was 26%. The commands still ran on one engine thread.
- **Stack Overflow** wrote that `KEYS` "can cause a production blockage in a hurry", and at their scale it always does.

**Evidence**

ElastiCache multiplexing post (2023): https://aws.amazon.com/blogs/database/enhanced-io-multiplexing-for-amazon-elasticache-for-redis. Stack Overflow post: https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/.

This section found the slow commands that `SLOWLOG` can see. The next section answers what slows a node when `SLOWLOG` is empty.

## What does SLOWLOG not see?

*SLOWLOG times only execution, so main-thread housekeeping stays invisible there.*

The section above found slow commands in `SLOWLOG`. On Monday in the running case, `SLOWLOG GET 128` is empty, and the p99 still jumps to 150 ms. So the main thread was busy with work that is not a command.

`SLOWLOG` measures only the execution stage of a command. Its time does not include talking with the client, sending the reply or waiting in the line. The main thread also runs housekeeping between commands, and a client waits behind that work in the same way. So a client's latency is the sum of four parts, and `SLOWLOG` shows only the last one.

#### One client's 150 ms at the p99, split into its parts

- round trip, about 0.5 ms, network, not on the server
- waiting behind other commands, about 20 ms, SLOWLOG shows these commands, not your wait
- waiting behind housekeeping, about 128 ms, expiry, eviction, frees, fork: never in SLOWLOG
- your own command, under 1 ms, the only part SLOWLOG can time

The split is an illustration, not measured. The order of the parts is the mechanism, and the next list names the work in the large red part.

The main thread runs these jobs that are not commands. Each one can hold it for many milliseconds:

1. **Active expiry.** A cron job, `serverCron`, runs `hz` times per second, 10 by default. It samples keys with a TTL and deletes the expired ones, for up to 25 ms per run at `hz 10`. A shorter fast cycle of up to 1 ms also runs between events. Many keys that expire in the same second keep this job at its limit.
2. **Freeing a big value.** When an expired or evicted key is a collection, Redis frees every element on the main thread by default. The next concept covers this in full.
3. **Eviction.** Above `maxmemory`, Redis evicts keys in the command path before it runs commands. Concept c5 covers this.
4. **The `fork()` call.** The fork for `BGSAVE` itself runs in the main thread, and it takes longer for a larger process. The latency documentation gives about 9 to 13 ms per GB on physical machines and on VMware.
5. **The operating system.** Transparent huge pages make copy-on-write slower after a fork, and swapping moves Redis memory to disk. Redis turns off transparent huge pages for itself by default, with `disable-thp yes`.

Each part of the sum has its own tool. Run them in this order when `SLOWLOG` is empty:

| Tool | What it measures | Default |
|---|---|---|
| `redis-cli --intrinsic-latency 100` | The host's own latency floor over 100 seconds, with no Redis work | Run on the Redis host |
| `INFO latencystats` | p50, p99 and p99.9 for each command type, including the wait | On, `latency-tracking yes` |
| `LATENCY LATEST`, `LATENCY DOCTOR` | Events that are not commands, such as `expire-cycle`, `expire-del` and `fork` | Off, `latency-monitor-threshold 0` |
| `INFO stats`: `latest_fork_usec` | How long the last fork held the main thread | Always reported |
| `redis-cli --latency` | Round trips of PING from your client, live | Run from the client side |

The latency monitor is off by default, so it has no history from before an incident. Turn it on with `CONFIG SET latency-monitor-threshold 10` before you need it. It then records every event that takes 10 ms or longer.

The course research measured the invisible part directly. It built a set of 1,000,000 members, set `PEXPIRE 200` on it and let active expiry delete it. `LATENCY LATEST` recorded `expire-del` at 176 ms, and `SLOWLOG` had no entry for it. With `lazyfree-lazy-expire yes`, the same test recorded no latency event at all, because a background thread freed the set. So one key that expired froze every client for 176 ms, and the tool that most engineers check first showed nothing.

**Evidence**

One run, Redis 8.10.1 from Homebrew, an x86_64 build under Rosetta with `malloc=libc`, Apple M4 Pro, 24 GB RAM, loopback, no persistence, `--enable-debug-command yes`. That SLOWLOG excludes I/O is quoted from https://redis.io/docs/latest/commands/slowlog-get/. The main-thread jobs and the fork table come from https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/. The fork table has no Redis version and is old. The defaults are from redis.conf at 8.10.2 (lines 2132 and 2142) and the expiry constants from `src/expire.c` at 8.10.2.

> The phase says that an empty `SLOWLOG` means the cause is round trips or a hot key. That list is too short. The official latency checklist also names fork latency, transparent huge pages, swapping, AOF fsync stalls, many keys that expire in the same second, and the host's own latency.

In the running case, the Monday spikes came every few minutes and lasted about a second. That shape fits a mass expiry or an eviction burst better than a slow command, because a command would show up in `SLOWLOG`. `LATENCY LATEST`, turned on before the next spike, names which one it is.

**Remember.** An empty SLOWLOG clears the commands, not the server.

**Trap.** Stopping at an empty SLOWLOG hides mass expiry, eviction bursts and fork stalls.

**Try.** Set the latency monitor to 10 ms, expire a big set, then read `LATENCY LATEST`.

**Go deeper: the expiry constants, the commands for the extra check, a real latency line, and a host-level case**

**Active expiry in numbers.** These are constants in `src/expire.c` at tag 8.10.2:

| Constant | Value | Meaning |
|---|---|---|
| `ACTIVE_EXPIRE_CYCLE_KEYS_PER_LOOP` | 20 | Keys sampled per database loop |
| `ACTIVE_EXPIRE_CYCLE_FAST_DURATION` | 1,000 µs | Time limit of the fast cycle |
| `ACTIVE_EXPIRE_CYCLE_SLOW_TIME_PERC` | 25 | CPU limit of the slow cycle, in % |
| `ACTIVE_EXPIRE_CYCLE_ACCEPTABLE_STALE` | 10 | The cycle repeats while more than 10% of sampled keys were expired |

The slow cycle's time limit is `25% × 1,000,000 / hz` µs, so 25 ms at `hz 10`. The fast cycle runs only when the stale estimate is above the limit, and at most every 2 ms. `active-expire-effort` goes from 1 to 10, and the default is 1. Each step adds 25% more keys per loop and lowers the stale target by 1%. With `dynamic-hz yes`, the default, Redis raises `hz` while it has many clients, up to 500.

**The extra check, as the course research ran it.** It is not an exercise of the phase, so it has no E-number:

```bash
CONFIG SET latency-monitor-threshold 10
EVAL "for i=1,ARGV[1] do redis.call('SADD',KEYS[1],'member:'..i) end" 1 bigset 1000000
PEXPIRE bigset 200
LATENCY LATEST        # expect an expire-del event near 176 ms on a laptop
CONFIG SET lazyfree-lazy-expire yes
# build the set again, PEXPIRE it, and LATENCY LATEST shows no new event
```

**A real latency line.** In the course research's KEYS test, `INFO latencystats` printed `latency_percentiles_usec_keys:p50=137363.455`. That is the p50 of the KEYS command itself, 137 ms, in microseconds.

**The host can be the cause.** At **Stack Overflow**, a monitoring process moved Redis off its CPU core, and clients timed out. The fix was to pin Redis to its cores. `--intrinsic-latency` on the host is the check for this kind of cause.

**AOF.** With `appendfsync everysec`, a slow disk can make Redis postpone the AOF `write(2)` for up to two seconds, and `aof_delayed_fsync` in `INFO persistence` counts those delays. Phase 4 explains the AOF itself.

This section showed that one key's expiry can freeze the node for 176 ms. The next section answers which other operations cost that much on a big key, and which setting decides it.

## What does a big key cost, and when?

*A big key turns routine operations, even its own expiry, into freezes.*

The 176 ms freeze in the section above came from one key with 1,000,000 members. In the running case, the AI agent keeps the message IDs of each chat session in one set. The shared session of one large tenant has grown to 2,000,000 members, and it has a 24-hour TTL.

A *big key* is a hash, set, list or sorted set with millions of elements, or a string of many megabytes. It grows slowly over months, so no single deploy creates it. Any operation on the whole key does work for each element, on the main thread. Some of those operations come from your code, and some come from Redis itself.

**Predict: your team deletes every big key with UNLINK. The 2,000,000-member session set has a 24-hour TTL. What happens tomorrow at the moment it expires, and which setting decides it?**

Active expiry deletes the key on the main thread and frees all 2,000,000 members there. Every client waits for that free. The course research measured a `DEL` of a 1,000,000-member set at 198,838 µs, so a linear scale gives about 400 ms for 2,000,000 members. In that run `DEL` grew faster than linear, so the real time may be longer. Both figures are inferred, not measured. `lazyfree-lazy-expire` decides it. It is `no` in Redis 8.10.2, so the free blocks. It is `yes` in Valkey 9.1.2, so a background thread frees the set there. The team's rule protects only the deletes it calls itself.

| Whole-key operation | Who starts it | On Redis 8.10.2 by default | The setting that moves it to a background thread |
|---|---|---|---|
| Read all: `SMEMBERS`, `HGETALL`, `LRANGE 0 -1` | Your code | Blocks | None. Read in pieces with the SCAN family |
| `DEL` | Your code | Blocks | `lazyfree-lazy-user-del` |
| `UNLINK` | Your code | Background | Background when the free effort is above 64 |
| Expiry of the key | Redis | Blocks | `lazyfree-lazy-expire` |
| Eviction of the key | Redis | Blocks | `lazyfree-lazy-eviction` |
| Overwrite by `SET` or `RENAME` | Your code, as a side effect | Blocks | `lazyfree-lazy-server-del` |
| Flush of the old data on a replica's full sync | Redis | Blocks | `replica-lazy-flush` |

The mechanism has three steps:

1. Freeing a collection walks every element and returns each one to the allocator. So the cost of a free grows with the element count, not with the byte size alone.
2. `UNLINK` removes the key from the keyspace at once. If the free effort is above 64, it gives the value to a background thread. For a set, a sorted set or a hash in its hash-table encoding, the effort is the element count. For a list, it is the number of quicklist nodes, the blocks of up to 8 KB that hold its elements. A value in a compact encoding, such as a small listpack, counts as 1.
3. Redis also deletes keys without a user call, in the four rows of the table that it starts itself. By default each of these frees the value as if `DEL` was called, until you set the matching setting to `yes`. The settings are all `no` in Redis 8.10.2 and all `yes` in Valkey 9.1.2.

The course research timed each operation from `SLOWLOG`, with the threshold at 0, so the numbers are server execution time only.

| Set size, hash-table encoding | `MEMORY USAGE` | `DEL` | `UNLINK` | `SMEMBERS` | One `SSCAN COUNT 500` |
|---|---|---|---|---|---|
| 100,000 members | 4,561,840 B | 7,313 µs | 12 µs | 5,193 µs | 148 µs |
| 1,000,000 members | 39,277,585 B | 198,838 µs | 9 µs | 86,439 µs | 155 µs |

Notice two things. `DEL` grows about 27 times for 10 times more members, so the cost is worse than linear in this run. `UNLINK` and one `SSCAN` batch stay flat, because neither touches all members on the main thread.

**Evidence**

One run, Redis 8.10.1 from Homebrew, an x86_64 build under Rosetta with `malloc=libc`, Apple M4 Pro, loopback, `slowlog-log-slower-than 0`. The threshold of 64 is `#define LAZYFREE_THRESHOLD 64` in `src/lazyfree.c` at tag 8.10.2, line 226: https://raw.githubusercontent.com/redis/redis/8.10.2/src/lazyfree.c. The list of deletes "independently of a user call" and the defaults are in redis.conf at 8.10.2, lines 1340 to 1386: https://raw.githubusercontent.com/redis/redis/8.10.2/redis.conf. The Valkey defaults are in valkey.conf at 9.1.2, lines 1448 to 1458: https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/valkey.conf. The overwrite case is inferred from the redis.conf text and was not measured.

> The phase gives "delete with `UNLINK`, not `DEL`" as a general rule. It depends on the engine now. Valkey 8.0 and later turn on all lazy-free settings by default, so `DEL` acts like `UNLINK` there. Redis 8.10.2 keeps them off, so `DEL` on a big key still blocks.

**Remember.** A big key costs O(N) whenever anything touches it whole, including Redis itself.

**Trap.** Using UNLINK everywhere still leaves expiry, eviction and overwrite blocking on Redis.

**Try.** Run `CONFIG GET lazyfree-lazy-*` on your cluster and note which deletes block.

**Go deeper: the three harms of a big key, how lazyfree counts effort, the phase's own measurements, and managed defaults**

**The three harms of a big key.** The phase names three, and the table above covers the first:

- **It blocks.** An O(N) read or free on 5,000,000 elements runs for hundreds of milliseconds on the main thread, and no other client is served.
- **It makes a hot shard.** A key lives in one slot on one shard. That shard holds all of the key's memory and serves all of its traffic, and a reshard cannot split one key.
- **It stalls a move.** Moving the key to another shard, or freeing it on failover or expiry, is one large piece of work at a bad time.

- **Effort.** `src/lazyfree.c` at 8.10.2, lines 168 to 235, computes the free effort. For sets, sorted sets and hashes in a hash-table encoding it is the element count. For a list it is the number of quicklist nodes, not of elements. A small value is freed at once, even by `UNLINK`, because a hand-off to a thread costs more than the free.
- **The phase's numbers.** Its `bigkey_scan` program found a 100,000-member set at 5,412,968 B, against 4,561,840 B in the course research's run. The two runs used different builds, so the difference is inferred to come from the allocator and was not checked. The phase measured `SMEMBERS` on 100,000 members at 11.4 ms and one `SSCAN` batch at 1.1 ms, measured from the client. It also gives 0.78 ms for `UNLINK`, measured from the client. The earlier audit found that the program never times `DEL`, so the phase has no `DEL` number of its own.
- **ElastiCache.** AWS lists the lazy-free settings under "Removed parameter groups in Valkey 8.0" and does not say which value they run with. Run `CONFIG GET lazyfree-lazy-user-del` on a node to find out. Source: https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/ParameterGroups.Engine.html.
- **The trade-off of a background free.** With lazy free on, the memory comes back a little later, in a background thread. On a node close to `maxmemory`, that delay can mean a few more evictions. This is inferred from how the background thread works, and it was not measured.
- **Migration.** When resharding uses `MIGRATE`, a big key moves as one unit, so its whole value must be read, sent and freed. Phase 4 explains slot moves and the `ASK` reply.

This section showed what a big key costs and when it costs it. The next section answers how to find big keys on a live node and remove them without a freeze.

## How do you find a big key and remove it safely?

*Find big keys with SCAN, read them in pieces, and bound them by design.*

The section above showed that the 2,000,000-member session set will freeze the node when it expires. You still have to find such keys on a live node with millions of keys, and remove them without the freeze you are trying to avoid.

1. **find**`--memkeys` or `--bigkeys`, both built on SCAN
2. **measure**`MEMORY USAGE key` for exact bytes
3. **read in pieces**`SSCAN`, `HSCAN`, bounded `LRANGE`
4. **delete**`UNLINK`, or lazy free for Redis's own deletes
5. **reshape**bound the collection or split it into buckets

Each step has a reason:

1. **Find.** `redis-cli --bigkeys` walks the keyspace with SCAN and reports the largest key of each type by element count. `--memkeys` ranks keys by bytes. `--keystats` gives both, with a size distribution. All three use SCAN, so they are safe on a busy node. In a cluster, each run covers one node, so you run it once per primary.
2. **Measure.** `MEMORY USAGE <key>` returns the bytes of one key. The phase's `bigkey_scan` program does the same thing in Go with SCAN, then `TYPE`, then the length for each type, then `MEMORY USAGE`.
3. **Read in pieces.** Never call `SMEMBERS`, `HGETALL` or `LRANGE 0 -1` on a big key. The SCAN family returns the same data in small batches, each of a few hundred microseconds.
4. **Delete.** Use `UNLINK`. For the deletes that Redis starts itself, set `lazyfree-lazy-expire`, `lazyfree-lazy-eviction` and `lazyfree-lazy-server-del` to `yes` on Redis. On Valkey they are already `yes`.
5. **Reshape.** This is the real fix. Do not create the big key at all.

```text
   bigset    type=set   members=100,000  mem=5,412,968B   ← BIG KEY (5.4MB, one shard)
   smallset  type=set   members=10       mem=120B
```

That is the output of the phase's `bigkey_scan -big 100000`.

> The phase says `--bigkeys` finds the largest keys. It ranks them by element count, not by bytes. So a hash of 10 members with 1 MB values can be missing from its report. Use `--memkeys` for bytes, or `--keystats` for both.

The reshape comes from the data modeling of Phase 1. Instead of one hash `company:c7:allusers`, split it into buckets such as `company:c7:users:{bucket}`, or choose a structure that stays small. A collection with no upper bound will become a big key one day. In an AI agent service, the common big keys are a chat history that grows with every message, and large vector or semantic-cache entries. That list is inferred from the general rule, and no public incident in the course research shows it. In the running case, the session set can hold only the last N messages, or one key per day of the session.

**Unbounded**

```text
SADD session:42:msgs <id>      # every message, forever
SMEMBERS session:42:msgs       # O(N) read
(24 h TTL) → expiry frees N    # blocks on Redis
```

**Bounded**

```text
SADD session:42:msgs:{day} <id>  # one key per day
SSCAN session:42:msgs:{day} 0     # read in pieces
lazyfree-lazy-expire yes          # expiry frees in background
```

The key names are an illustration of the running case. The bounded form still needs a size limit per day, chosen from the traffic.

**Remember.** Find big keys by bytes and count, then bound the model against them.

**Trap.** An unbounded "append every event" collection is fine at launch, then an incident later.

**Try.** Run E4, but seed `bigset` again before `--bigkeys`, because the program deletes it.

**Go deeper: Valkey's large-reply log, two real costs that grew with the data, and what to run on a cluster**

- **Valkey's large-reply log.** `COMMANDLOG GET` can read the large-reply log, which lists the commands whose replies were largest. A `HGETALL` on a big hash appears there when its reply is larger than `commandlog-reply-larger-than`, 1,048,576 bytes by default, even when it runs under the slow threshold. That makes it a direct finder of big-key reads. Source: https://valkey.io/commands/commandlog-get/.
- **Cloudflare** kept sliding-window counts in Redis with HyperLogLog and `PFMERGE`. The first launch could not keep up with about 10,000 requests per second, because the cost of `PFMERGE` grew with the number of features times the window size. Running detection less often raised throughput about ten times. Binary key names instead of readable ones saved about 30% of memory.
- **bsport** moved its data to new clusters with a live replication tool. The tool scanned the whole source and ran `DUMP` on each key. After cutover it was the only client, so it ran at full speed. Some `DUMP` calls took over 1 second each and filled the source's CPU, and application requests timed out. Killing the tool brought the services back in 2 minutes. Staging traffic was 500 times lower than production, so the tests missed it.
- **On a cluster.** `--bigkeys` samples only the node it connects to. So a big key on another primary is missing from the report until you run it there too. This follows from SCAN being a per-node command, and it is inferred from the CLI page.

**Evidence**

Cloudflare: https://blog.cloudflare.com/lessons-learned-from-scaling-up-cloudflare-anomaly-detection-platform/ (2021). bsport: https://engineering.bsport.io/how-we-eliminated-redis-as-a-single-point-of-failure-2729c22008b5 (2026), read from the blog's feed. The CLI flags: https://redis.io/docs/latest/develop/tools/cli/. The course research found no public postmortem of a big-key `DEL` that caused a failover.

Big keys concentrate work in one key's size. The next section answers what happens when one key concentrates the request rate instead, and why more shards do not help.

## Why do more shards not fix a hot key?

*One key lives on one shard, so its requests share one thread.*

A big key puts a lot of work into one key's size. On Tuesday in the running case, the problem is the request rate instead. Every request of the largest tenant reads one key, its tenant settings, and one shard runs at 100% CPU while five run at about 30%.

**Predict: one key gets 200,000 reads per second on a 6-shard cluster. You double the cluster to 12 shards. What happens to the CPU of the shard that owns the key, and why?**

It stays the same. The key maps to one hash slot, and a reshard moves whole slots, so the slot and all 200,000 reads per second still land on one primary. That primary still runs them on one thread. The other shards get less load, and the bill doubles. The guess "twice the shards, half the load per shard" is right for keys spread evenly, and that is the case sharding was built for. A hot key is the case it cannot split.

A *hot key* is one key that receives a large share of all requests. Sharding spreads keys across nodes, but every request for one key goes to the node that owns it. That node runs the commands on one main thread, so the key's request rate is capped by one CPU core. Adding nodes moves other keys away from the hot shard, and the hot key stays where it is.

- shard 1: 30% CPU
- shard 2: 30% CPU
- shard 3, owns the hot key: 100% CPU
- shards 4 to 6: 30% CPU each

- shards 1 and 2: 15% CPU each
- shard 3, still owns the hot key: 100% CPU
- shards 4 to 12: 15% CPU each

The CPU values are an illustration, not measured. Doubling the shards halves the load on the cold shards and leaves the hot shard at 100%.

The path of one request shows why. Each step has one owner, and no step can spread one key:

1. The client hashes the key name with CRC16 and takes the result modulo 16,384. That gives the key's hash slot.
2. The cluster map says which primary owns that slot. The client sends the request there.
3. That primary runs the command on its main thread. Its replicas only copy writes, unless your client sends reads to them.
4. A reshard moves whole slots between primaries. So the hot key's slot moves as one unit, with all its traffic, to one new owner.

So the ceiling for one key is what one core can run. More shards raise the ceiling for the whole keyspace, but they leave the ceiling for each key where it was.

**Salesforce Marketing Cloud** moved its cache from Memcached to Redis Cluster, at about 1.5 million cache events per second across more than 50 services. After the move, heavily read keys caused CPU spikes on single shards. The team wrote that a hot key "can saturate a single CPU core" per shard. The fix was a local in-memory cache in each application, backed by Redis, with read replicas as a short-term step. During the migration, the p50 was near 1 ms and the p99 near 20 ms. The post gives no CPU numbers from before and after the fix.

**Evidence**

Salesforce engineering, 2026: https://engineering.salesforce.com/migration-at-scale-moving-marketing-cloud-caching-from-memcached-to-redis-at-1-5m-rps-without-downtime/. Hash slots: Phase 4 and the cluster specification. The one-thread ceiling follows from the latency page's "Single threaded nature of Redis" section. The course research searched twice for a public postmortem with hot-shard CPU numbers and found none.

**Remember.** More shards raise the keyspace's ceiling, never one key's ceiling.

**Trap.** Adding shards for a hot key doubles the bill and leaves it at 100%.

**Try.** Compare CPU across your primaries and look for one far above the rest.

**Go deeper: hot keys at Twitter and Alibaba, and a cluster where more nodes made it worse**

- **Twitter timelines.** Each timeline was a Redis list. One overloaded server, from a popular user's timeline or a bad bot, made timeouts spread to other requests. The fix counted recent keys in a time window inside Redis and flagged a key above a threshold share as hot. Checking every key added latency, so they sampled. New command forms such as `LRANGE_HK` returned a hot flag with the result, and the API layer then cached hot results locally. The post is a former engineer's personal blog and gives no production numbers.
- **Alibaba at Double 11.** Flash sales make access very skewed, and one hot item can overload one node and crash it. The earlier fixes were a client-side cache of hot data and copies of hot keys on several nodes. The page reports a peak of 992 million requests per second for Tair, with no conditions given.
- **Figma** moved Pub/Sub onto a cluster-mode ElastiCache instance, and one node's engine CPU went to 100%. The team moved to a larger cluster with more nodes, and that made it worse. The cause was a bug in Pub/Sub on clustered ElastiCache. Messages travel on the cluster bus, and a growing send buffer made each send cost more CPU. More nodes lowered the load needed to start the loop. The mechanism differs from a hot key, but in both cases more nodes did not help. So find the cause before you add nodes.

**Evidence**

Twitter: https://matthewtejo.substack.com/p/handling-hotkeys-in-timeline-storage (2023). Alibaba: https://www.alibabacloud.com/blog/596493 (2020). Figma postmortem: https://www.figma.com/blog/postmortem-service-disruptions-on-june-6-and-7-2022/.

Adding shards does not help a hot key. The next section answers how to find which key is hot, and how to stop its requests before they reach that one thread.

## How do you find a hot key and take the load off it?

*Name the key first, then stop its reads before they reach Redis.*

The section above showed that the hot shard stays hot whatever the shard count. Before you can fix it, you need the key's name, because one shard holds about 2,700 slots and maybe millions of keys.

Four tools can name the key. They differ in what they need and in what they measure:

| Tool | What it needs | What it ranks by |
|---|---|---|
| `redis-cli --hotkeys` | An LFU policy, `allkeys-lfu` or `volatile-lfu` | The LFU access counter of each key, read with SCAN |
| `HOTKEYS START METRICS count [CPU] [NET]` | Redis 8.6.0 or later, any policy | CPU time and network bytes per key |
| `CLUSTER SLOT-STATS` | Valkey 8.0.0 or later, and Redis 8.2 and later. CPU and network need `cluster-slot-stats-enabled yes` | Key count, CPU and network bytes per slot |
| `MONITOR`, for a few seconds | Nothing, but it costs throughput while it runs | Count the keys in the stream yourself |

Per-shard CPU in your metrics tells you which shard to look at. Then one of these tools tells you which key on it.

`--hotkeys` reads the LFU counter, which is logarithmic, so it ranks keys but does not give a request rate. `HOTKEYS START` ranks by real cost in CPU and bytes, so it shows how much of the thread one key takes.

> The phase gives `--hotkeys` as the hot-key tool, and it still needs an LFU policy. Since Redis 8.6.0, `HOTKEYS START` works under any policy and ranks keys by CPU and network. `CLUSTER SLOT-STATS` finds the hot slot with per-slot CPU and network. Valkey has it since 8.0.0, and Redis since 8.2.0, from `src/commands/cluster-slot-stats.json` at tag 8.10.2.

Once you have the key, stop its requests before they reach the one thread. The fixes, in order of effect:

1. **Local in-process cache**Keep the value inside each application process with a short TTL, so most reads never reach Redis.
2. **Server-assisted client-side caching**With `CLIENT TRACKING`, Redis remembers which keys a client read and sends it an invalidation message when one changes.
3. **Reads from replicas**Spread the reads over the shard's replicas. They can return stale data, and in cluster mode a client must send `READONLY` first.
4. **N copies of the key**Store `hotkey:0` to `hotkey:N` in different slots and read a random copy. Writes must update every copy.

The first fix removes the most load, because a read served inside the process costs no network and no Redis CPU. A short TTL bounds how stale the local copy can be. `CLIENT TRACKING` removes that limit, because Redis tells the client when to drop its copy. Replicas help only with reads. A key that is hot for writes still lands on the primary, so only a change in the data model helps it. The copies technique is common practice, but the course research found no primary source for it, so treat it as not checked.

In the running case, the tenant-settings key changes a few times a day and is read on every request. A local cache with a TTL of a few seconds, or `CLIENT TRACKING`, takes nearly all of those reads off shard 3. The six extra shards can then go. A well-cached value with a high hit rate is not hot at Redis, so the best hot-key fix is often a better cache.

**Evidence**

The `--hotkeys` rule "only works when maxmemory-policy is *lfu" is from https://redis.io/docs/latest/develop/tools/cli/. HOTKEYS START is "Available since: Redis Open Source 8.6.0" on https://redis.io/docs/latest/commands/hotkeys-start/. CLUSTER SLOT-STATS: https://valkey.io/commands/cluster-slot-stats/. CLIENT TRACKING: https://redis.io/docs/latest/develop/reference/client-side-caching/. The `READONLY` rule and the stale reads are in the cluster specification, section "Scaling reads using replica nodes": https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/. The FREQ and HOTKEYS numbers are one run on Homebrew Redis 8.10.1 under Rosetta with libc malloc, Apple M4 Pro, loopback.

**Remember.** Name the hot key first, then serve its reads from a local cache.

**Trap.** `--hotkeys` does not work under `volatile-lru`, and a `MONITOR` left on slows the node.

**Try.** Run E11 with `redis-cli -r 5000 GET hot`, then `OBJECT FREQ hot`.

**Go deeper: the LFU counter and HOTKEYS numbers, the limits of client-side caching, Stack Overflow's stampede, and what Salesforce planned next**

- **The counter in numbers.** In the course research's run, with `lfu-log-factor 10`, 5,000 `GET`s on one key gave `OBJECT FREQ` 36, and 50 `GET`s gave 8. So a hundred times more reads gave only about four and a half times the counter. Under `noeviction`, `HOTKEYS START` reported the key `hot` at 1,445 µs of CPU and 145,000 bytes, and the key `k:7` at 57 µs and 7,000 bytes.
- **The LFU counter.** Redis keeps a logarithmic counter per key, which starts at 5 for a new key. `lfu-log-factor 10` sets how slowly it grows, and `lfu-decay-time 1` sets how fast it falls when the key is idle. Both are the Redis 8.10.2 defaults.
- **Client-side caching races.** A local cache can serve stale data after the client reconnects, because invalidation messages sent while it was away are lost. A client should drop its local cache when its connection to Redis drops. This comes from the client-side caching page, and the course research did not test it.
- **Tracking clients in Redis 8.** Tracking clients stay on the main thread, not on I/O threads. This is in `src/iothread.c` at 8.10.2, lines 292 to 299.
- **What Salesforce planned.** Detection of hot keys with a Count-Min Sketch in the data access layer, and throttling per key. These were plans in the post, not results.
- **Stack Overflow** saw the same pattern from the other side, at the source behind its cache. When a popular cache entry expired, "hundreds of simultaneous calls" went to the source to rebuild it. Their fix was a per-server lock table, so one caller rebuilds the entry and the others wait or use the old value. Phase 2 called this a cache stampede and fixed it with `singleflight`, the same idea in one process. It hits the source behind Redis, not Redis itself, but its cause is the same concentration of requests on one key. Source: https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/.
- **MONITOR.** It streams every command the server runs to your client. On a busy node that stream is itself load, so sample for a few seconds and stop it.

Hot keys and big keys are about CPU on the main thread. The next section answers what happens when the node runs out of memory, which is the "Day 9" line of the running case.

## What does "full" mean under each eviction policy?

*One setting decides what a write does when memory is full.*

The concepts so far were about time on the main thread. On Day 9 in the running case, the problem is memory: every service gets `OOM command not allowed` on writes, while reads still work. The cluster runs the provider's default policy, `volatile-lru`.

`maxmemory` is the cap that Redis sets on `used_memory`, the bytes its allocator has handed out. When a write needs memory above the cap, Redis looks at `maxmemory-policy`. The policy says which keys Redis may remove to make room, which is called *eviction*. If the policy allows no key, the write fails. So the policy decides whether a full cache drops old data or refuses new data.

| Policy | Which keys it may evict | Which one first |
|---|---|---|
| `noeviction` | None. Writes that need memory fail | Not used |
| `allkeys-lru` | Any key | Least recently used |
| `allkeys-lfu` | Any key | Least frequently used |
| `allkeys-random` | Any key | A random key |
| `allkeys-lrm` | Any key | Least recently modified |
| `volatile-lru` | Only keys with a TTL | Least recently used |
| `volatile-lfu` | Only keys with a TTL | Least frequently used |
| `volatile-random` | Only keys with a TTL | A random key |
| `volatile-ttl` | Only keys with a TTL | The shortest TTL left |
| `volatile-lrm` | Only keys with a TTL | Least recently modified |

LRU evicts the key that nobody touched for the longest time. LFU evicts the key with the fewest accesses, which suits skewed access. LRM updates its timestamp only on writes, so a key that is read often but never changed still counts as old. Open-source Redis defaults to `noeviction`. ElastiCache defaults to `volatile-lru`.

> The phase lists "all 8" policies. Redis 8.6 and later have ten, adding `allkeys-lrm` and `volatile-lrm`. Valkey 9.1.2 still has the eight older ones.

**Predict: a shared cluster runs volatile-lru. One service writes session keys with no TTL, and the others write cache keys with a TTL. Which keys are evicted first, what does used_memory do over a week, which commands fail on the last day, and which services see it?**

The cache keys with a TTL are evicted, because they are the only keys the policy may touch. The session keys stay, so `used_memory` stays at the cap while the no-TTL share grows. On the last day no key with a TTL is left. Then every write that needs memory fails, such as `SET`, `INCR`, `HSET` and `LPUSH`. `GET` and `DEL` still work. Every service on the cluster sees the failures, not only the one that wrote the session keys. The reasonable guess is "at worst it evicts some cold keys". That is true only while keys with a TTL are left.

The eviction documentation states the rule in one line: "The volatile-xxx policies behave like noeviction if no keys have an associated expiration." Step by step:

1. A command arrives that may need memory, such as `SET`. Such commands carry the `denyoom` flag.
2. Redis compares `used_memory` with `maxmemory`. If memory is over the cap, it looks for keys to evict.
3. Under a `volatile-*` policy, Redis looks only in the set of keys that have a TTL. It samples some, picks the best candidate and evicts it, until memory is under the cap.
4. If that set is empty, Redis has nothing it may evict. It refuses the command with `OOM command not allowed when used memory > 'maxmemory'`.
5. Commands without `denyoom`, such as `GET` and `DEL`, still run. So the node looks alive to health checks that only read.

The course research ran the failure with `maxmemory 8mb` and `volatile-lru`. It sent 1,500 writes of 10 KB values, and every second write had no TTL.

- **1,355** writes OK
- **145** writes refused with OOM
- **0** keys with a TTL left
- **678** keys without a TTL left

`GET` and `DEL` on a surviving key still worked. `INFO commandstats` showed `cmdstat_set: ... rejected_calls=146`, and `INFO errorstats` showed `errorstat_OOM:count=146`. So those two fields count the refused writes directly, and an alert on them fires at the first refusal. The exact counts depend on the value size and the allocator.

**Evidence**

One run, Redis 8.10.1 from Homebrew, an x86_64 build under Rosetta with `malloc=libc`, Apple M4 Pro, loopback. The quote is from https://redis.io/docs/latest/develop/reference/eviction/. The error rule for writes that "require more memory" is in redis.conf at 8.10.2, lines 1257 to 1262. The `denyoom` flag of SET is on https://redis.io/docs/latest/commands/set/. The ten policies are in redis.conf at 8.10.2, lines 1233 to 1242, and the eight of Valkey in valkey.conf at 9.1.2, lines 1322 to 1329. The ElastiCache default "Default: volatile-lru" is on https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/ParameterGroups.Engine.html.

Choose the policy from what the data is:

- **A pure cache where every key can be rebuilt.** Use `allkeys-lru`, or `allkeys-lfu` for skewed access. Any key can go, so writes do not fail for lack of a candidate.
- **A mix of cache keys and keys you must keep.** `volatile-lru` works only if every cache key has a TTL. Every key without a TTL must be a key you can afford to keep. One service that forgets a TTL breaks that rule for all.
- **Data you cannot lose.** Use `noeviction` with an alert on memory. A refused write is visible, and a silent eviction is not. This advice is inferred from the policy rules, and the eviction page does not give it. The page does advise a separate Redis instance for keys you must keep, so keep that data out of a shared cache.

For the running case, the lasting fix is a TTL on every cache key, which is Phase 2's rule. The other fix is `allkeys-lru`, so that a forgotten TTL can no longer fill the cluster. Then a key you must keep can be evicted too, so that key must move to a store that does not evict.

**Remember.** Under volatile-lru, a key with no TTL can never be evicted.

**Trap.** Trusting "volatile-lru evicts cold keys" until the last TTL key is gone and writes fail.

**Try.** Run `INFO errorstats` and `INFO commandstats` and look for OOM and `rejected_calls`.

**Go deeper: the phase's three-policy run, how Redis picks a key to evict, the program's counting problem, and two queues that filled**

**The phase's program, three policies side by side.** The phase's own `eviction_policies` program fills an 8 MB instance with 1,500 keys, half with a TTL and half without:

```text
   policy=noeviction    survived ttl=259 nottl=259 | OOM write errors=982
   policy=allkeys-lru   survived ttl=258 nottl=255 | OOM=0 | evicted=987
   policy=volatile-lru  survived ttl=0   nottl=515 | OOM write errors=471  ← !!
```

Read the `volatile-lru` row. All TTL keys were evicted, 515 keys without a TTL survived, and then 471 writes failed. A key written with no TTL cannot be evicted under this policy at all.

- **Sampling, not exact LRU.** Redis samples `maxmemory-samples` keys, 5 by default and at most 64, into a pool of 16 candidates, and evicts the best one. So LRU and LFU are approximate. The ElastiCache valkey8 parameter family sets `maxmemory-samples` to 3. The LRU clock has 24 bits in units of 1 second.
- **A time budget.** `maxmemory-eviction-tenacity`, 10 by default, sets how long one eviction pass may run. At 10 the budget is 500 µs, and after it a timer continues the work. Source: `src/evict.c` at 8.10.2.
- **Replicas.** Replicas ignore `maxmemory` by default, with `replica-ignore-maxmemory yes`. The primary evicts and sends the deletes.
- **The program's counting problem.** `evicted_keys` is cumulative, and the program never runs `CONFIG RESETSTAT`. So the `volatile-lru` run also counts the earlier `allkeys-lru` evictions. Add `CONFIG RESETSTAT` before each policy.
- **Slack's job queue.** Jobs piled up in Redis during a database slowdown until Redis hit `maxmemory`, and new jobs could not be enqueued. Dequeue also needs free memory, because it moves a job into an in-flight list. So the queue stayed stuck after the database recovered. Slack put Kafka in front of Redis and kept Redis.
- **Discord's indexing queue.** With too many queued messages, Redis CPU hit its limit and Redis dropped messages. The queue moved to a system with delivery guarantees.

**Evidence**

Sampling and pool size: `src/config.c` and `src/evict.c` at 8.10.2, and redis.conf at 8.10.2, line 1278. ElastiCache valkey8 sampling: the ParameterGroups.Engine page above. Program issue: the earlier audit, `main.go` lines 85 to 91. Slack: https://slack.engineering/scaling-slacks-job-queue/. Discord: https://discord.com/blog/how-discord-indexes-trillions-of-messages.

The rule is clear, but every team believes it sets TTLs on every key. The next section answers how keys lose their TTL without anyone noticing, and what that did to one shared cluster.

## How does a key lose its TTL, and what did that do to one shared cluster?

*A plain SET removes the TTL, so a correct first write is not enough.*

The section above showed that keys with no TTL fill a `volatile-lru` cluster. Most teams believe they set a TTL on every key. In practice a key often gets its TTL on the first write and loses it on a later one.

A TTL belongs to the key, not to the value, and each `SET` replaces the key. A plain `SET` with no expiry option removes any TTL the key had. So an update path that rewrites a value with no TTL turns a cache key into a permanent key. Clients add a second way to lose it, because in go-redis a TTL of `0` means "no expiry".

1. SET s v EX 86400 `TTL s` returns 86400. The key expires in 24 hours.
2. SET s v2 `TTL s` returns -1. The plain SET removed the TTL, and the key is now permanent.
3. SET s v3 EX 86400 `TTL s` returns 86400 again.
4. SET s v4 KEEPTTL `TTL s` still returns 86400. `KEEPTTL` keeps the existing TTL.

The course research ran these four steps on Redis 8.10.1. The SET page says the same: "Any previous time to live associated with the key is discarded on successful SET operation."

In go-redis v9.5.1, `Set(ctx, k, v, 0)` sends no expiry, and the source says "Zero expiration means the key has no expiration time". So a caller that passes `0` because it has no TTL at hand makes a permanent key. A shared client library that requires a TTL argument, with no safe default, spreads that risk to every service that uses it. On the platform below, one such library had about 30 dependent repositories.

**The platform, the running case.** This is the real case behind the running case. It comes from the phase, in general terms. The platform ran about 34 services on several shared, managed Redis clusters, with the provider default `volatile-lru`. On one of these clusters, an LLM gateway service wrote its keys with no TTL. The TTL keys of the other services were evicted, and the gateway's keys stayed. Memory reached 100%, and writes then failed for every tenant on the cluster, including an unrelated admin upload feature. A memory alert fired, but it had no owner tag, so nobody acted on it. Customers were affected for about 3 hours 25 minutes, and about 4 hours 37 minutes from start to end.

The fix had four parts:

1. Delete the keys with no TTL, to free memory at once.
2. Scale the node from 1 GB to 3 GB, to get headroom while the code changed.
3. Add a TTL to every key of the gateway service.
4. Fix the alert's owner, so the next memory alert reaches a team.

The same platform later had a second, quieter case. A chat-session memory key was first written with a 24-hour TTL. An update path that condensed the session rewrote the key with TTL 0, which made it permanent. A unit test asserted the 0, so the test protected the bug. The key is per session, so the number of such keys grows with every session. On a `volatile-lru` cluster that is the first case again, only slower. The platform's alerts covered memory, CPU, connections, hit rate and replica lag, but nothing alerted on slow commands or hot keys.

**Evidence**

The SET quote is from https://redis.io/docs/latest/commands/set/. The go-redis line is `string_commands.go` line 163 at tag v9.5.1: https://raw.githubusercontent.com/redis/go-redis/v9.5.1/string_commands.go. The TTL steps are one run of the course research on Redis 8.10.1. The platform's dates, durations, node sizes, alert routing and the session-key bug come from the phase and are internal, so they are not checked. The mechanism matches the eviction page and the run in the section above.

Three checks find this before it fills a cluster. Each one targets a different way the TTL is lost:

- **Audit the keyspace.** Walk it with SCAN and call `TTL` on each key. A result of `-1` means no expiry, and the key prefix names the service that wrote it. E12 does this.
- **Audit the write paths.** Search the code for plain `SET` on keys that were created with a TTL, and for TTL arguments that can be `0`. Use `KEEPTTL` or pass the TTL again on every update.
- **Give every alert an owner.** A memory alert at a safe level gives hours of warning, because a no-TTL fill is slow. That warning helps only if a team receives it.

**Remember.** Every write that creates or replaces a cache key must set its TTL again.

**Trap.** Testing only the first write, so an update path with TTL 0 makes keys permanent.

**Try.** Run `SET s v EX 86400`, then `SET s v2`, then `TTL s`.

**Go deeper: two more no-TTL outages, and an estimate of how many permanent keys a shared cluster can hold**

- **Pendo.** A managed Redis was near its memory limit and evicting keys. CPU spikes caused slow replies and connection failures. The cause was two code paths that created cache keys with no expiry. The guides service had about a 60% error rate for the first 90 minutes. The team flushed all Redis instances, and CPU dropped. They then fixed the two code paths and added Redis monitoring.
- **bsport.** One shared Redis served payments, bookings, auth, email and push. An audit found keys with no TTL, some of them years old, because teams used Redis as a database. Webhook spikes from one domain also slowed bookings. The fix was one cluster per domain, moved one domain at a time.
- **An estimate for the running case.** Suppose each permanent session key holds 2 KB and the cluster has 3 GB. Then about 1.5 million permanent keys fill it. At 50,000 new sessions a day, that is about 30 days. These numbers are an illustration, not measured. What matters is the shape. The fill is slow and linear, so an alert on the no-TTL share warns weeks ahead.

**Evidence**

Pendo status page: https://status.pendo.io/incidents/g8nfbs1vdn69. bsport: https://engineering.bsport.io/how-we-eliminated-redis-as-a-single-point-of-failure-2729c22008b5.

The concept so far explained which keys go when memory is full. The next section answers what the eviction work itself costs the main thread, and why a full cache can be slow even when every write succeeds.

## Why is reaching maxmemory a latency event?

*Eviction runs on the main thread, in the path of every command.*

The concept above decided which keys go when memory is full. Under `allkeys-lru` every write succeeds, so a full cache looks healthy. But the eviction work runs somewhere, and in Redis that place is the main thread, between the commands of your clients.

While `used_memory` is above `maxmemory`, Redis evicts keys before it runs commands. Each eviction samples keys, picks one, deletes it and frees its memory, all on the main thread. A cache that stays at its cap pays this cost all the time. When many writes arrive at once, eviction can take most of the thread, and the commands behind it wait. This is the other likely cause of the Monday spikes in the running case.

**Predict: an LRU cache runs allkeys-lru and serves 25,000 commands per second. Its memory reaches maxmemory and stays there. What happens to throughput during a burst of writes, and does SLOWLOG show it?**

Throughput can fall to a fraction of normal for several seconds, and `SLOWLOG` shows nothing. At GitLab, the rate of eviction calls, and so of commands, fell to 20% of its norm, from 25,000 to 5,000 per second, for 6 to 8 seconds. No single command was slow, so `SLOWLOG` had no entry. The reasonable guess is that eviction is free, because it only drops data you agreed to lose. It is free only when the main thread has time to spare.

1. **memory at maxmemory**every write needs an eviction first
2. **eviction holds the thread**commands wait, and replies fall behind requests
3. **client buffers grow**unsent replies and unread requests use memory
4. **buffers count toward maxmemory**so Redis must evict even more

The last step feeds back into the second, so the slowdown sustains itself. It ends only when the write burst ends and Redis catches up.

The loop has four links, and each one is in the code or the documentation:

1. Redis calls its eviction code in the command path while memory is over the cap. In Redis 8.10.2 the call sits inside `processCommand`, so it runs before the command.
2. One eviction pass has a time budget. `maxmemory-eviction-tenacity` is 10 by default, which gives about 500 µs. After the budget, a timer continues the work, still on the main thread.
3. Client input and output buffers count toward `maxmemory`. A slow main thread leaves more requests unread and more replies unsent, so buffer memory grows.
4. More buffer memory means more keys to evict for the same writes. So the work per second grows exactly when the thread has the least time for it.

**GitLab** ran a Redis 6.2 instance used only as an LRU cache, which grew to about 64 GB. Every few minutes, requests took about 1 second and throughput fell, and the bursts were too short to trigger alerts. Each weekday, about 2 million requests took longer than 1 second. The cause was the loop above. Each burst had three phases: memory reached `maxmemory`, eviction saturated the main thread for 6 to 8 seconds, then recovery took 30 to 60 seconds.

The fix was not a Redis setting. They cut the default cache TTL from 2 weeks to 8 hours, in steps, while they watched their service levels. Memory then stayed below `maxmemory`, the bursts stopped, and the hit rate barely changed. So the TTL was the real control of memory, and the cap was only the last line of defense.

**Evidence**

GitLab, "How we diagnosed and resolved Redis latency spikes with BPF and other tools", Matt Smiley, 2022: https://about.gitlab.com/blog/how-we-diagnosed-and-resolved-redis-latency-spikes/. The quote "dropped to 20% of its norm ... from 25K to 5K calls per second" and the count of about 2 million slow requests each weekday are from that post, about Redis 6.2. The call site in `processCommand` is `src/server.c` line 4656 at tag 8.10.2, and the time budget is in `src/evict.c` at 8.10.2. That client buffers count toward `maxmemory` is on https://redis.io/docs/latest/develop/reference/eviction/.

In the running case, a cache that sits at its cap all day shows the same shape. The p99 rises in short bursts, `SLOWLOG` stays empty, and `evicted_keys` climbs fastest during the bursts. Lower TTLs on the largest cache key families keep peak memory under the cap, and then eviction has no work to do.

**Remember.** A cache that lives at maxmemory pays for eviction on the main thread.

**Trap.** Treating "evicting at the cap" as normal, while client buffers make the eviction worse.

**Try.** Watch `evicted_keys` per second next to your p99, and look for bursts that line up.

**Go deeper: what GitLab ruled out, maxmemory-clients, output buffer limits, and the fields that show eviction pressure**

- **What GitLab ruled out.** A lower `maxmemory-eviction-tenacity` helped only a little. `lazyfree-lazy-eviction` was not the cause. Replication buffers stayed small. Host contention and one large key were also ruled out. So the usual settings did not fix a cache that lived at its cap.
- **`maxmemory-clients`** limits the total memory of client connections. Above the limit, Redis drops the connections that use the most memory, in `beforeSleep`. It is 0, which means off, in Redis 8.10.2, and commented out in redis.conf at lines 2489 to 2506. The setting arrived in Redis 7.0, whose release notes list it as a new setting: https://raw.githubusercontent.com/redis/redis/7.0.0/00-RELEASENOTES. The GitLab post was current for Redis 6.2, before this setting existed.
- **Output buffer limits.** The default `client-output-buffer-limit` for normal clients is `0 0 0`, no limit. So a client that reads a big reply slowly, or a `KEYS *` reply, can grow its buffer without bound. Replicas default to `256mb 64mb 60` and pub/sub clients to `32mb 8mb 60`.
- **What does not count.** Replication and AOF buffers do not count toward `maxmemory`. `INFO memory` reports them as `mem_not_counted_for_evict`. So they can push RSS above the cap without any eviction.
- **Pressure fields.** `current_eviction_exceeded_time` shows how long memory has been over the cap in the current episode. `evicted_keys` is cumulative, so alert on its rate.
- **Managed serverless.** ElastiCache Serverless evicts keys that have a TTL by LRU when memory is full, and throttles requests when compute is full.

Eviction explains slow commands at the cap. The next section answers the last line of the running case: why the operating system can kill Redis while `used_memory` is still under `maxmemory`.

## Which memory numbers decide whether the process survives?

*The kernel kills by memory use, and RSS holds more than used_memory.*

The section above showed what the cap costs in time. The last line of the running case is worse. During the nightly `BGSAVE`, the operating system kills Redis, although `used_memory` was under `maxmemory`.

`used_memory` counts the bytes that Redis's allocator handed out. The operating system sees *RSS*, the resident set size, which is the physical memory the process really holds. When the machine runs out, the kernel's out-of-memory killer gives each process a score from its memory and swap use. It kills the process with the highest score. On a host that runs mainly Redis, that process is usually Redis. This last point is inferred, not measured. RSS includes memory that `used_memory` does not count, and during a fork the child's copied pages come on top of both.

#### An 8 GB node with maxmemory 7.5gb during a BGSAVE

- dataset, 7.0 GB, counted in used_memory
- client buffers, 0.5 GB, counted in used_memory
- replication and AOF buffers, 0.3 GB, mem_not_counted_for_evict
- fragmentation and process overhead, 0.4 GB, in RSS, not in used_memory
- pages copied for the fork child, 1.5 GB, grows with writes during the save

The sizes are an illustration, not measured. They add up to 9.7 GB on an 8 GB node, so the kernel kills a process, although `used_memory` never passed 7.5 GB.

The fork is the part that teams forget. Parent and child share all pages at the start. Each page that the parent changes during the save is copied, so the copy grows with the write rate and the length of the save. In the worst case, every page changes and memory doubles. So the number to size a node from is peak RSS during a fork, not `used_memory`.

#### Peak memory during a fork

- Node RAM, GB (ram from 2 to 128, default 8)
- maxmemory, % of RAM (mm from 40 to 100, default 94)
- Pages changed during the save, % (cow from 0 to 100, default 20)
- Buffers, fragmentation and overhead, % of maxmemory (other from 0 to 30, default 10)

Result: peak RSS of parent and child = maxmemory × (1 + overhead share) + maxmemory × changed-page share, compared with the node's RAM.

The formula is an illustration of the mechanism, not a measured model. Measure the real share of changed pages on your own node with `current_cow_peak` during a save.

**Stack Overflow** lost its sites to this. Their cache was about 90 GB on servers with 96 GB of RAM. A planned failover started replication to a new primary, which needs a `BGSAVE`. The fork copied changed pages, and in their words "That 6GB went fast". Redis crashed, and "all of our websites promptly went offline". The sites came back on the new server with an empty cache. This was Redis 2.x, but the fork and its copies work the same way today.

**Evidence**

Stack Overflow, Nick Craver, 2019: https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/. The same post says "the rate at which new changes rack up is your memory growth during a copy". The fields `current_cow_peak` and `latest_fork_usec` are in `src/server.c` and `src/childinfo.c` at 8.10.2. RSS and the fragmentation fields: https://redis.io/commands/info/. The out-of-memory score from memory and swap use is described in the kernel documentation, section 3.1 of https://docs.kernel.org/filesystems/proc.html.

The fields that matter most are `used_memory`, `used_memory_rss`, `mem_not_counted_for_evict`, `allocator_frag_ratio` and `current_cow_peak`. The Go deeper block below lists every field to read in an investigation, with what each one tells you.

> The phase says a `mem_fragmentation_ratio` above 1.5 means fragmentation. The INFO page says that when total fragmentation bytes are low, a few megabytes, a high ratio "is not an indication of an issue". The course research's 8 MB test showed `mem_fragmentation_ratio:12.06` with `allocator_frag_ratio:1.00`. Use `allocator_frag_ratio`. A `used_memory` far above `used_memory_rss` still means part of Redis was swapped out.

> The phase gives "`maxmemory` at about 75% of RAM" as the number. It is a rule of thumb, not a measured value. The headroom you need depends on how many pages change during a fork. ElastiCache reserves 25% by default with `reserved-memory-percent`. On your own nodes, measure peak RSS during `BGSAVE`.

An alert set built from these fields catches each failure of this phase early. Every alert needs an owner, as the running case showed:

1. **`used_memory` over `maxmemory`, as a share, above a warning level.** The slow fill of c4 shows here hours or weeks ahead. On ElastiCache this is the CloudWatch metric `DatabaseMemoryUsagePercentage`.
2. **A rising `evicted_keys` rate.** This is normal for a pure `allkeys-lru` cache, and a warning on a cluster where keys should stay.
3. **Any `errorstat_OOM` or `rejected_calls`.** One refused write means the policy has run out of candidates.
4. **CPU per shard.** One shard far above the others points to a hot key or a big key.
5. **`allocator_frag_ratio` high, or swap in use.** Redis with swap has the latency of a disk.
6. **Peak RSS during the nightly save against node RAM.** This is the number behind the last line of the running case.
7. **`SLOWLOG` length growing, and latency events.** O(N) commands are creeping in, or housekeeping is stalling the thread.

When memory is high, also run `OBJECT ENCODING` on your biggest keys. As Phase 1 showed, a hash that fell out of its listpack encoding can cost several times more, and a small schema change can fix it.

**Remember.** Size a node from peak RSS during a fork, not from used_memory.

**Trap.** A maxmemory of all RAM, or 0, can lose the process in the nightly save.

**Try.** Run E10, then compute `used_memory_rss` minus `used_memory` on your node.

**Go deeper: every INFO field to read, fork cost measured by AWS, swap and kernel settings, active defrag, and MEMORY DOCTOR**

**Every field to read.** These are the fields to read in an investigation, from `INFO memory`, `INFO stats` and `INFO persistence`:

| Field | What it tells you |
|---|---|
| `used_memory` | Bytes Redis allocated, including client buffers. Eviction compares this with `maxmemory`. |
| `used_memory_rss` | Bytes the operating system gave the process. The kernel judges Redis by this one. |
| `maxmemory` | The cap. 0 means no cap, so Redis can grow until the kernel kills it. |
| `mem_not_counted_for_evict` | Replication and AOF buffers, which eviction ignores. |
| `mem_clients_normal` | Memory of normal client buffers, which counts toward `maxmemory`. |
| `allocator_frag_ratio` | The true external fragmentation, inside the allocator. |
| `mem_fragmentation_ratio` | RSS divided by `used_memory`. It includes code and stack, so it misleads on small instances. |
| `evicted_keys` | Cumulative evictions. A rising rate means memory pressure. |
| `keyspace_hits`, `keyspace_misses` | The hit rate, which Phase 2 showed multiplies load on the source. |
| `connected_clients`, `instantaneous_ops_per_sec` | Connection count, for leaks, and current throughput. |
| `latest_fork_usec`, `current_cow_peak` | How long the last fork held the main thread, and the peak of copied bytes in the current child. |

- **Fork cost, measured.** AWS measured this for its MemoryDB design, on a node with 2 vCPUs, 16 GB of RAM, `maxmemory` 12 GB and 20 million keys of 500 bytes. The fork took about 12 ms per GB, and the maximum latency rose to 67 ms during `BGSAVE`. When copy-on-write pushed the machine into swap, the maximum latency went over 1 second. Throughput fell close to 0 once swap passed 8% of memory. AWS advises keeping the dataset at or below half of RAM, or taking snapshots off-peak. MemoryDB itself takes snapshots on separate machines.
- **Fork time by platform.** The latency documentation gives about 9 to 13 ms per GB on physical machines and on VMware, and 23 ms per GB on one KVM host. Xen is much slower: 239 ms per GB on old EC2 instance types and 424 ms per GB on Linode. That table is old and names no Redis version. On Linux, read `latest_fork_usec` on your own nodes.
- **Kernel settings.** Redis warns at start-up if `vm.overcommit_memory` is not 1, because a fork can fail without it. Transparent huge pages are off for Redis, as the c1 section said. Sources disagree on swap. One Redis course sets `vm.swappiness=0` to avoid swapping. The admin guide says to keep swap as large as memory, so the kernel does not kill Redis on overuse. Swap trades a kill for very slow replies, so choose by which failure your service can survive.
- **Active defrag.** It is off by default, `activedefrag no`. When on, it starts above 10% allocator fragmentation and 100 MB of waste, and it uses 1% to 25% of CPU. Each step lasts about 500 µs.
- **MEMORY DOCTOR** warns when total fragmentation is above 1.4 and above 10 MB, which is the small-instance rule of the callout above in code form.
- **A caveat on the 12.06.** The course research ran on a build with the libc allocator, not jemalloc. On such a build the allocator fields may not be meaningful. The production default is jemalloc 5.3.0, bundled with Redis 8.10.2.

**Evidence**

MemoryDB paper, SIGMOD-Companion 2024: https://www.amazon.science/publications/amazon-memorydb-a-fast-and-durable-memory-first-cloud-database. Fork table: https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/. Kernel and defrag defaults: `src/syscheck.c`, `src/config.c` and `src/defrag.c` at 8.10.2. Memory guidance: https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/memory-optimization/. ElastiCache metrics: https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/CacheMetrics.WhichShouldIMonitor.html.

That closes the four lines of the running case. The next section collects what you can now do with them.

## What you can do now, and what comes next

- **Latency is a sum.** A client's latency is the round trip, the wait behind all main-thread work and its own command. `SLOWLOG` times only the last part, so an empty `SLOWLOG` sends you to `LATENCY LATEST` and `INFO latencystats`. Taught in "Why does one slow command delay every client?" and "What does SLOWLOG not see?".
- **A big key costs O(N) whenever anything touches it whole.** That includes expiry, eviction, overwrite and a replica's flush, which `UNLINK` does not cover on Redis. Taught in "What does a big key cost, and when?" and "How do you find a big key and remove it safely?".
- **Sharding spreads keys, not requests.** A hot key stays on one thread, so you name it and serve its reads from a local cache. Taught in "Why do more shards not fix a hot key?" and "How do you find a hot key and take the load off it?".
- **`volatile-*` policies evict only keys with a TTL.** Keys that lost their TTL turn a full shared cluster into `noeviction` for every service. Taught in "What does full mean under each eviction policy?" and "How does a key lose its TTL?".
- **The memory cap is a latency event, and RSS decides survival.** Eviction runs on the main thread, and the fork's copied pages are outside `used_memory`. Taught in "Why is reaching maxmemory a latency event?" and "Which memory numbers decide whether the process survives?".

You can now take "Redis is slow" or "Redis is out of memory" on a shared cluster and name the cause with the right command, in minutes. Phase 6 asks how one production service should use Redis from end to end, from its client settings to a review of every key it writes.

## Lab: the exercises that teach Phase 5

Twelve exercises, copied from the phase in its own order. Nobody ran this lab for the lesson. The course research ran the same commands directly with `redis-cli` on Redis 8.10.1, and did not run the phase's Go programs. Where a step is broken, a note under it says what is wrong and what to expect instead. Each concept has its exercises:

| Concept | Exercises |
|---|---|
| c1: latency is a sum, and SLOWLOG sees one part | E1, E2, E3, E5 |
| c2: big keys cost O(N) at every whole-key operation | E4, E5, E6 |
| c3: a hot key stays on one thread | E11 |
| c4: volatile policies and keys without a TTL | E7, E8, E12 |
| c5: the memory cap and the fields that matter | E9, E10 |

**Open the lab: setup, E1 to E12, and the notes on broken steps**

Setup:

```bash
cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d && docker exec redis-study redis-cli PING   # → PONG
```

> The earlier audit found that this path is wrong. The code lives under `/Users/raghvendra.dhakar/Desktop/project/code/study-material/redis/code`. The compose file pins `redis:7.2`. The current releases are Redis 8.10.2 and Valkey 9.1.2, so `HOTKEYS START`, the LRM policies and the Valkey defaults need a newer image. The Docker tags for them were not checked.

- [ ] **E1** c1 **Pipelining vs sequential (the #1 lever).**
    - Run: `go run ./phase00_why_redis/pipeline_vs_roundtrip -keys 500` then `-keys 2000`.
    - Expected: 30–224x speedup; gap widens with N.
    - Teaches: the round-trip is the cost; batch it.

  > Not run for this lesson. A check that needs no Go: `redis-benchmark -t get -c 1 -P 1`, then `-P 16` and `-P 100`. The course research measured 10,051, 129,282 and 414,079 requests per second on loopback.

- [ ] **E2** c1 **Slow commands + SLOWLOG.**
    - Run: `go run ./phase05_perf/slow_commands -n 200000`
    - Expected: KEYS ~33ms, HGETALL ~62ms, both in SLOWLOG; SCAN/HMGET sub-ms.
    - Teaches: O(N) blockers, their SCAN swaps, and SLOWLOG as step #1.

  > Not run. The program leaves `slowlog-log-slower-than` at 1000, so set it back to 10000 afterwards. Also read `INFO latencystats` after the run, to see the p99 of KEYS and HGETALL.

- [ ] **E3** c1 **Read SLOWLOG by hand.**
    - Run: `docker exec redis-study redis-cli CONFIG SET slowlog-log-slower-than 1000; docker exec redis-study redis-cli DEBUG POPULATE 500000; docker exec redis-study redis-cli KEYS '*' > /dev/null; docker exec redis-study redis-cli SLOWLOG GET 3`
    - Expected: the `KEYS *` shows up with its microsecond duration.
    - Teaches: the exact command you run first in a latency page.

- [ ] **E4** c2 **Find big keys.**
    - Run: `go run ./phase05_perf/bigkey_scan -big 100000` then `docker exec redis-study redis-cli --bigkeys` (after seeding).
    - Expected: the 100k-member set flagged (~5.4MB); `--bigkeys` reports the biggest per type.
    - Teaches: `--bigkeys` and `MEMORY USAGE` for big-key detection.

  > The program deletes `bigset` with `UNLINK` at the end, at line 89 of `main.go`. So `--bigkeys` finds nothing unless you seed the set again. Also run `--memkeys`, because `--bigkeys` ranks by element count, not bytes.

- [ ] **E5** c1, c2 **(Break it) SMEMBERS a big key while watching latency.**
    - Run: seed `bigset` (100k), then `docker exec redis-study redis-cli --latency &` and in another shell `docker exec redis-study redis-cli SMEMBERS bigset > /dev/null`.
    - Expected: the latency meter spikes during the SMEMBERS.
    - Teaches: a big-key O(N) read blocks every client (Phase 0.3, made concrete).

  > The phase gives no seed command, and E4 deleted the key. This seed worked in the course research with 1000000 members, and here it uses the phase's 100,000: `EVAL "for i=1,ARGV[1] do redis.call('SADD',KEYS[1],'member:'..i) end" 1 bigset 100000`.

- [ ] **E6** c2 **UNLINK vs DEL.**
    - Run: seed `bigset`, then time `docker exec redis-study redis-cli DEL bigset` vs (re-seed and) `docker exec redis-study redis-cli UNLINK bigset`.
    - Expected: UNLINK returns instantly; DEL blocks proportional to size.
    - Teaches: always UNLINK big keys.

  > Timing a `docker exec` mostly measures the start of the `docker exec` process, which can hide a 7 ms `DEL`. Set `slowlog-log-slower-than 0` and read the time from `SLOWLOG GET 1` after each command. The course research measured 7,313 µs for `DEL` and 12 µs for `UNLINK` at 100,000 members, on Homebrew Redis 8.10.1 under Rosetta with libc malloc, outside Docker. Expect other numbers in the container. On Valkey, `DEL` is fast too, because lazy free is on there.

- [ ] **E7** c4 **Reproduce the no-TTL eviction outage.**
    - Run: `go run ./phase05_perf/eviction_policies`
    - Expected: `volatile-lru` → nottl keys survive, TTL keys evicted, then 471 OOM write errors.
    - Teaches: no-TTL keys are unevictable under volatile-lru → the outage mechanism.

  > The phase titles E7 with the former employer's internal incident ID, which this lesson does not repeat. The program does not run `CONFIG RESETSTAT`, and `evicted_keys` is cumulative, so the `volatile-lru` row also counts earlier evictions. Add `CONFIG RESETSTAT` before each policy, print `rejected_calls`, and on Redis 8.6 and later add `allkeys-lrm`. The program's comments at lines 1, 10 to 13 and 118 to 119 name the incident.

- [ ] **E8** c4 **(Break it) OOM under noeviction.**
    - Run: `docker exec redis-study redis-cli CONFIG SET maxmemory 4mb; docker exec redis-study redis-cli CONFIG SET maxmemory-policy noeviction`, then `docker exec redis-study redis-cli DEBUG POPULATE 100000` (or write 10KB values in a loop).
    - Expected: writes start returning `OOM command not allowed`.
    - Teaches: what `noeviction` at the cap looks like. Reset: `CONFIG SET maxmemory 256mb`.

  > The expected result is wrong for `DEBUG POPULATE`. `DEBUG` has no `denyoom` flag, so Redis does not refuse it. In the course research it grew a 4 MB instance to 7.16 MB. The next `SET` is refused with OOM. The reset leaves `noeviction` on, so also run `CONFIG SET maxmemory-policy allkeys-lru` before E9.

- [ ] **E9** c5 **Watch eviction happen.**
    - Run: `CONFIG SET maxmemory-policy allkeys-lru; CONFIG SET maxmemory 8mb`, seed many 10KB keys, watch `INFO stats | grep evicted_keys` climb and `INFO memory | grep used_memory_human` hold near the cap.
    - Teaches: eviction keeps writes flowing by discarding LRU data — the metric to alert on.

  > Not run. Also read `current_eviction_exceeded_time` and `mem_not_counted_for_evict` while it evicts.

- [ ] **E10** c5 **Read INFO memory like an on-call.**
    - Run: `docker exec redis-study redis-cli INFO memory | grep -E "used_memory_human|maxmemory_human|mem_fragmentation_ratio|evicted"` and `INFO stats | grep -E "keyspace_hits|keyspace_misses|evicted_keys"`.
    - Compute: hit rate and fragmentation ratio. Are they healthy?
    - Teaches: the exact fields you scan during a memory investigation.

  > Not run. Add `allocator_frag_ratio` to the grep. On a small test instance, `mem_fragmentation_ratio` can read 12 while `allocator_frag_ratio` reads 1.00, as the c5 section explains.

- [ ] **E11** c3 **Detect a hot key.**
    - Run: `CONFIG SET maxmemory-policy allkeys-lfu`, hammer one key: `for i in $(seq 1 5000); do docker exec redis-study redis-cli GET hot >/dev/null; done` (seed `hot` first), then `docker exec redis-study redis-cli --hotkeys`.
    - Expected: `hot` reported as the most-accessed key.
    - Teaches: `--hotkeys` needs an LFU policy; how to find the key saturating a shard.

  > 5,000 separate `docker exec` calls take minutes. Use `redis-cli -r 5000 GET hot` inside one exec instead. Expect `OBJECT FREQ hot` near 36. On Redis 8.6 and later, also try `HOTKEYS START METRICS 2 CPU NET`, which works under any policy.

- [ ] **E12** c4 **TTL audit (find the no-TTL eviction risk).**
    - Run: write some keys with and without TTL, then scan for no-TTL keys: for each key `docker exec redis-study redis-cli TTL <key>` → `-1` means no expiry.
    - Teaches: no-TTL keys are the eviction risk; auditing for `-1` is how you find ballast before it fills the cluster.

  > Not run. Add the step that loses a TTL: `SET s v EX 86400`, then `SET s v2`, then `TTL s`, which returns -1. The phase titles E12 with the former employer's incident ID, replaced here by what it describes.

#### Checks for a service you own

The phase ends with four checks in its author's codebase. Here they are in general terms:

1. **The no-TTL write path.** Find every write to a per-session or per-user key. Check that each update path passes the TTL again, and that no test asserts a TTL of 0. Ask why a 0 TTL on a per-session key is dangerous under `volatile-lru`, and write the one-line fix.
2. **The local caches you already have.** Find the in-process caches in front of Redis. For each one, name the hot key it protects Redis from.
3. **The N+1 hunt.** Pick a request path that reads several Redis keys. If it loops with single `GET`s over a collection, estimate the cost as the p95 collection size times the in-AZ round trip of about 0.5 ms. In the phase's codebase most reads were single-key, so the risk was any new loop.
4. **Monitoring.** Check that the memory alert exists and has an owner, and ask what is not alerted on. In the phase's codebase, nothing alerted on slow commands or hot keys.

## Checkpoint questions

Eight questions. Answer each in your own words before you open the sketch.

**Open the questions**

**Q1.** A shared cluster runs `volatile-lru`. One service writes keys with no TTL. Walk through what happens to `used_memory`, why the policy cannot save the cluster, why writes fail while reads do not, and why a co-tenant service goes down. Then give two independent fixes, one per service and one for the whole cluster, and say which you would do first.

**Answer sketch**

`used_memory` stays at the cap while TTL keys are evicted and the no-TTL share grows. When no TTL key is left, the policy has no candidate and acts like `noeviction`. Commands with the `denyoom` flag, such as `SET`, fail with OOM. `GET` and `DEL` do not need memory, so they still run. The co-tenant fails because the cap and the policy belong to the whole cluster, not to one service. Per service: add a TTL on every write, including update paths. For the cluster: switch to `allkeys-lru`, after you move keys that must not be evicted. Do the TTL fix first, and delete the no-TTL keys to recover now.

**Q2.** A service's p99 is 40 ms. `SLOWLOG GET 20` is empty, and no single command is slow. Walk through your diagnosis: the likely causes, how you confirm each, and the fix for each.

**Answer sketch**

First, round trips: count Redis calls per request, and batch a loop with `MGET` or a pipeline. Second, a hot key: compare per-shard CPU, then name the key with `HOTKEYS START` or `--hotkeys`, and add a local cache. Third, main-thread work that is not a command: turn on `latency-monitor-threshold`, read `LATENCY LATEST`, and look for `expire-del`, `fork` or eviction. The fixes there are lazy free, spread TTLs, smaller forks or more headroom. Run `--intrinsic-latency` on the host to rule out the machine.

**Q3.** A grading flow does 40 sequential `HGET`s, one per rubric item, against an in-AZ managed Redis with a p50 round trip of 0.5 ms. What latency does this add? Rewrite it as one command and give the new latency. In cluster mode, what must be true of the keys for that one command to be legal, and how do you make sure of it?

**Answer sketch**

```text
40 × 0.5 ms = 20 ms of round trips
one HMGET of 40 fields on one hash: about 1 × 0.5 ms
```

If the items are fields of one hash, use `HMGET`. If they are 40 keys, use `MGET` or a pipeline. A multi-key command in cluster mode needs all keys in one slot, so give them one hash tag, such as `{rubric:7}`.

**Q4.** `redis-cli --bigkeys` finds a 4-million-member set `company:c7:all_viewers` at 240 MB. Explain the three problems this one key causes, why adding shards will not help, and how you would re-model it. Which command deletes the old key safely, and what still blocks on Redis after that?

**Answer sketch**

It blocks: any whole-key read or free walks 4 million members on the main thread. It makes a hot shard: its slot, its memory and its traffic sit on one primary. It stalls a move or a failover, because it moves or frees as one unit. A reshard moves whole slots, so one key never splits. Re-model it into buckets, such as `company:c7:viewers:{bucket}`, or bound it. Delete with `UNLINK`. On Redis, its expiry, its eviction and an overwrite still block unless the matching `lazyfree-lazy-*` setting is `yes`.

**Q5.** A managed node has about 13 GB of RAM. What should `maxmemory` be, and why not the full 13 GB? What happens during a `BGSAVE` fork that makes headroom necessary, and what fails if you skip it?

**Answer sketch**

Leave headroom for memory that `used_memory` does not count. That memory is the pages copied for the fork child, replication and AOF buffers, fragmentation and process overhead. During the fork, each page the parent changes is copied, so the extra memory grows with the write rate and the save time. Without headroom, RSS passes the RAM, and the kernel kills Redis during the backup. Managed defaults reserve about 25%, which gives about 9.75 GB here. That is a rule of thumb, so confirm it with peak RSS during a save on your own write load.

**Q6.** A colleague wants to switch the shared cluster from `volatile-lru` to `allkeys-lru` "so we stop having OOM incidents". Argue both sides. What does it fix, what does it risk, and what must be true first? What fixes the root cause instead?

**Answer sketch**

It fixes the no-TTL fill, because any key can now be evicted, so writes no longer fail for lack of a candidate. It risks the silent loss of keys that services expected to keep, such as locks, sessions or counters with no TTL. It is safe only if every key on the cluster can be rebuilt. The root-cause fix is a TTL on every cache key, an audit of write paths, and moving data that must stay to a store that does not evict.

**Q7.** Design the alerts for a shared Redis cluster that has seen a no-TTL fill, a hot key and slow commands. Name four metrics, a threshold for each and the failure each catches early. Which single alert gives the most for its cost?

**Answer sketch**

Memory use as a share of `maxmemory` catches the slow fill, at a warning level well below the cap. `errorstat_OOM` or `rejected_calls` above 0 catches the first refused write. CPU per shard, far above the others, catches the hot key. `SLOWLOG` growth and latency events catch slow commands and housekeeping. Memory share has the best value, because the fill is slow and gives hours or weeks of warning. Every alert needs an owner, or it does not count.

**Q8.** An LRU cache at `maxmemory` shows 1-second latency bursts every few minutes. `SLOWLOG` is empty, and lazy free and tenacity changes barely help. What is the loop, and what would you change first?

**Answer sketch**

Eviction at the cap runs on the main thread, so replies fall behind and client buffers grow. Buffers count toward `maxmemory`, so Redis must evict more, which keeps the thread busy. Lower the default TTL in steps, so peak memory stays under the cap and eviction has nothing to do. GitLab cut its default from 2 weeks to 8 hours this way, and the hit rate barely changed.

## Cheatsheet

**Open the cheatsheet**

```
SYMPTOM → CAUSE → FIRST TOOL
  many fast calls, nothing slow    → round trips (N+1)     → count calls; MGET / pipeline
  everyone freezes tens of ms      → O(N) command          → SLOWLOG GET 10, INFO latencystats
  spikes, SLOWLOG empty            → housekeeping          → LATENCY LATEST / DOCTOR
                                                              (latency-monitor-threshold 0 = off)
  one huge collection              → big key               → --memkeys (bytes), --bigkeys (count),
                                                              --keystats, MEMORY USAGE key
  one shard hot, others idle       → hot key               → HOTKEYS START (Redis 8.6+, any policy)
                                                              --hotkeys (LFU only), CLUSTER SLOT-STATS (Valkey 8.0+, Redis 8.2+)
  writes OOM, reads fine           → no-TTL keys + volatile-* → INFO errorstats, commandstats rejected_calls
  bursts at the cap / killed at BGSAVE → eviction, fork copies → INFO memory, latest_fork_usec, current_cow_peak

LATENCY = round trip + wait behind ALL main-thread work + own execution
  SLOWLOG times only own execution (default slowlog-log-slower-than 10000 µs)
  main-thread work that is not a command: active expiry (hz 10, ≤25 ms/run),
  big frees, eviction, fork(), THP, swap, AOF fsync
  host floor: redis-cli --intrinsic-latency 100
  Valkey 8.1+: COMMANDLOG (slow, large-request 1,048,576 B, large-reply)

O(N) BLOCKERS → SAFE FORM
  KEYS → SCAN   SMEMBERS → SSCAN   HGETALL → HSCAN / HMGET   LRANGE 0 -1 → bounded
  DEL(big) → UNLINK   FLUSHALL → FLUSHALL ASYNC   long Lua → small scripts
  SCAN: cursor until 0; a key present throughout comes back ≥1 time, maybe twice
  measured: KEYS 1M keys 133–148 ms; SCAN COUNT 1000 0.25–0.30 ms (8.10.1 Rosetta, libc, M4 Pro)

BIG KEYS
  free = O(N) on main thread; UNLINK goes to background above a free effort of 64 (elements, or list nodes)
  implicit deletes: expiry, eviction, overwrite (SET/RENAME), replica flush
  lazyfree-lazy-{user-del,expire,eviction,server-del}: Redis 8.10.2 no / Valkey 9.1.2 yes
  1M-member set: DEL 198,838 µs, UNLINK 9 µs, SMEMBERS 86,439 µs, SSCAN 155 µs
    (one run, 8.10.1 Rosetta, libc, M4 Pro); 1M-member expiry blocked 176 ms
  fix upstream: bound or bucket the model, key:{bucket}

HOT KEYS (one key → one slot → one primary → one thread)
  more shards do not help; reshard moves whole slots
  fixes in order: local in-process cache (short TTL) → CLIENT TRACKING
                  → replica reads (stale, READONLY) → N copies key:0..N
  LFU counter is logarithmic: 5,000 GETs → FREQ 36, 50 GETs → FREQ 8

EVICTION POLICIES (10 in Redis 8.6+, 8 in Valkey 9.1.2)
  noeviction (Redis default)         → writes needing memory fail, reads/deletes work
  allkeys-lru / lfu / random / lrm   → evict any key
  volatile-lru / lfu / random / ttl / lrm → only keys WITH a TTL (ElastiCache default: volatile-lru)
  volatile-* with no TTL keys left = noeviction
  plain SET drops TTL; go-redis Set(ctx,k,v,0) = no expiry; use EX again or KEEPTTL
  sampling: maxmemory-samples 5, pool 16; tenacity 10 ≈ 500 µs per pass

MEMORY
  kernel OOM score = memory + swap use; RSS = used_memory + not counted + fragmentation; fork copies on top
  client buffers COUNT toward maxmemory; repl/AOF buffers do not (mem_not_counted_for_evict)
  fragmentation: trust allocator_frag_ratio, not mem_fragmentation_ratio on small nodes
  size from peak RSS during BGSAVE; ~75% of RAM is a rule of thumb, ElastiCache reserves 25%
  maxmemory 0 = no cap = can grow until the kernel kills it
  maxmemory-clients (0 = off) drops the biggest clients

ALERTS (each with an owner)
  memory share of maxmemory; errorstat_OOM > 0; evicted_keys rate;
  CPU per shard; allocator_frag_ratio or swap; peak RSS at the nightly save;
  SLOWLOG growth and latency events
```

## Sources

Every source the lesson used, in groups. The phase's own must-read list comes first.

**Open the sources**

The course research opened these pages on 2026-10-18. Its own measurements ran on Redis 8.10.1 from Homebrew, an x86_64 build under Rosetta, with the libc allocator, on an Apple M4 Pro with 24 GB of RAM, over loopback, with one run per number.

#### The phase's must-read list

- **Diagnosing latency issues** [https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/)The checklist: intrinsic latency, slow commands, fork, transparent huge pages, swap, AOF, expires. The page to open during an incident.
- **Key eviction** [https://redis.io/docs/latest/develop/reference/eviction/](https://redis.io/docs/latest/develop/reference/eviction/)The ten policies, LRM, approximate LRU and LFU, "volatile-xxx ... behave like noeviction", client buffers counted.
- **Memory optimization** [https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/memory-optimization/](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/memory-optimization/)`used_memory`, fragmentation, listpack thresholds and `maxmemory` sizing.
- **ElastiCache metrics to monitor** [https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/CacheMetrics.WhichShouldIMonitor.html](https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/CacheMetrics.WhichShouldIMonitor.html)`DatabaseMemoryUsagePercentage`, evictions, engine CPU and the alarms to set. The research also opened the newer copy at [https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/CacheMetrics.WhichShouldIMonitor.html](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/CacheMetrics.WhichShouldIMonitor.html).

#### Redis command and tool pages

- **SLOWLOG GET** [https://redis.io/docs/latest/commands/slowlog-get/](https://redis.io/docs/latest/commands/slowlog-get/) and [https://redis.io/commands/slowlog-get/](https://redis.io/commands/slowlog-get/)Execution time only, no I/O.
- **INFO** [https://redis.io/commands/info/](https://redis.io/commands/info/)Every field, `allocator_frag_ratio` as the true fragmentation, latencystats, errorstats.
- **KEYS** [https://redis.io/docs/latest/commands/keys/](https://redis.io/docs/latest/commands/keys/)1 million keys in 40 ms on an entry-level laptop.
- **SCAN** [https://redis.io/docs/latest/commands/scan/](https://redis.io/docs/latest/commands/scan/) and [https://redis.io/commands/scan/](https://redis.io/commands/scan/)The cursor contract, and that an element may come back more than once.
- **SET** [https://redis.io/docs/latest/commands/set/](https://redis.io/docs/latest/commands/set/)A successful SET discards the TTL. The `denyoom` flag.
- **redis-cli** [https://redis.io/docs/latest/develop/tools/cli/](https://redis.io/docs/latest/develop/tools/cli/)`--bigkeys`, `--memkeys`, `--keystats`, `--hotkeys` and its LFU rule, `-r`.
- **Client-side caching** [https://redis.io/docs/latest/develop/reference/client-side-caching/](https://redis.io/docs/latest/develop/reference/client-side-caching/)`CLIENT TRACKING` and invalidation messages.
- **HOTKEYS START** [https://redis.io/docs/latest/commands/hotkeys-start/](https://redis.io/docs/latest/commands/hotkeys-start/)Available since Redis Open Source 8.6.0, ranks keys by CPU and network.
- **OBJECT ENCODING** [https://redis.io/commands/object-encoding/](https://redis.io/commands/object-encoding/)Listpack against hash table when memory is high.

#### Source code and config files at release tags

- **redis.conf at 8.10.2** [https://raw.githubusercontent.com/redis/redis/8.10.2/redis.conf](https://raw.githubusercontent.com/redis/redis/8.10.2/redis.conf)Policies, lazy-free defaults, latency settings, `maxmemory-clients`.
- **lazyfree.c at 8.10.2** [https://raw.githubusercontent.com/redis/redis/8.10.2/src/lazyfree.c](https://raw.githubusercontent.com/redis/redis/8.10.2/src/lazyfree.c)`LAZYFREE_THRESHOLD 64`.
- **Redis Cluster specification** [https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)Hash slots, and "Scaling reads using replica nodes": READONLY and stale reads.
- **Redis 7.0 release notes** [https://raw.githubusercontent.com/redis/redis/7.0.0/00-RELEASENOTES](https://raw.githubusercontent.com/redis/redis/7.0.0/00-RELEASENOTES)maxmemory-clients as a new setting in Redis 7.0.
- **Linux kernel, /proc documentation** [https://docs.kernel.org/filesystems/proc.html](https://docs.kernel.org/filesystems/proc.html)Section 3.1: the out-of-memory score from memory and swap use.
- **redis.conf at 7.2.4** [https://raw.githubusercontent.com/redis/redis/7.2.4/redis.conf](https://raw.githubusercontent.com/redis/redis/7.2.4/redis.conf)Used only to confirm the old defaults match.
- **valkey.conf at 9.1.2** [https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/valkey.conf](https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/valkey.conf)Lazy free on by default, eight policies, COMMANDLOG settings.
- **go-redis v9.5.1, string_commands.go** [https://raw.githubusercontent.com/redis/go-redis/v9.5.1/string_commands.go](https://raw.githubusercontent.com/redis/go-redis/v9.5.1/string_commands.go)"Zero expiration means the key has no expiration time".
- **Release lists** [https://api.github.com/repos/redis/redis/releases](https://api.github.com/repos/redis/redis/releases) and [https://api.github.com/repos/valkey-io/valkey/releases](https://api.github.com/repos/valkey-io/valkey/releases)Redis 8.10.2 and Valkey 9.1.2 as the current releases.

#### Valkey and managed services

- **CLUSTER SLOT-STATS** [https://valkey.io/commands/cluster-slot-stats/](https://valkey.io/commands/cluster-slot-stats/)Per-slot keys, CPU and network, since Valkey 8.0.0.
- **COMMANDLOG GET** [https://valkey.io/commands/commandlog-get/](https://valkey.io/commands/commandlog-get/)Slow, large-request and large-reply logs, since Valkey 8.1.0.
- **ElastiCache engine parameters** [https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/ParameterGroups.Engine.html](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/ParameterGroups.Engine.html)Default `volatile-lru`, `reserved-memory-percent` 25, valkey8 sampling of 3, removed lazy-free parameters.
- **ElastiCache enhanced I/O multiplexing** [https://aws.amazon.com/blogs/database/enhanced-io-multiplexing-for-amazon-elasticache-for-redis](https://aws.amazon.com/blogs/database/enhanced-io-multiplexing-for-amazon-elasticache-for-redis)72% more throughput at 5,200 clients, commands still on one engine thread.
- **ElastiCache Serverless** [https://aws.amazon.com/blogs/aws/amazon-elasticache-serverless-for-redis-and-memcached-now-generally-available/](https://aws.amazon.com/blogs/aws/amazon-elasticache-serverless-for-redis-and-memcached-now-generally-available/)Evicts keys with a TTL by LRU when memory is full.
- **Amazon MemoryDB paper** [https://www.amazon.science/publications/amazon-memorydb-a-fast-and-durable-memory-first-cloud-database](https://www.amazon.science/publications/amazon-memorydb-a-fast-and-durable-memory-first-cloud-database)Fork at about 12 ms per GB, 67 ms peak latency during BGSAVE, collapse past 8% swap.

#### Production cases

- **GitLab, eviction bursts on an LRU cache** [https://about.gitlab.com/blog/how-we-diagnosed-and-resolved-redis-latency-spikes/](https://about.gitlab.com/blog/how-we-diagnosed-and-resolved-redis-latency-spikes/)25K to 5K calls per second, 2 million slow requests a weekday, TTL from 2 weeks to 8 hours. Redis 6.2.
- **Stack Overflow app caching** [https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/](https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/)The BGSAVE fork crash at 90 GB on 96 GB, KEYS, the stampede lock table, CPU pinning.
- **Salesforce Marketing Cloud migration** [https://engineering.salesforce.com/migration-at-scale-moving-marketing-cloud-caching-from-memcached-to-redis-at-1-5m-rps-without-downtime/](https://engineering.salesforce.com/migration-at-scale-moving-marketing-cloud-caching-from-memcached-to-redis-at-1-5m-rps-without-downtime/)Hot keys on single shards at 1.5 million events per second, fixed with local caches.
- **Spring Data Redis issue 1413** [https://github.com/spring-projects/spring-data-redis/issues/1413](https://github.com/spring-projects/spring-data-redis/issues/1413)KEYS inside a cache clear took Redis to 100% CPU.
- **Pendo status incident** [https://status.pendo.io/incidents/g8nfbs1vdn69](https://status.pendo.io/incidents/g8nfbs1vdn69)Two code paths with no expiry, about 60% errors for 90 minutes.
- **bsport, Redis as a single point of failure** [https://engineering.bsport.io/how-we-eliminated-redis-as-a-single-point-of-failure-2729c22008b5](https://engineering.bsport.io/how-we-eliminated-redis-as-a-single-point-of-failure-2729c22008b5)No-TTL keys in a shared Redis, and DUMP calls of over 1 second during a migration.
- **Slack job queue** [https://slack.engineering/scaling-slacks-job-queue/](https://slack.engineering/scaling-slacks-job-queue/)A full Redis could not enqueue or dequeue.
- **Discord message indexing** [https://discord.com/blog/how-discord-indexes-trillions-of-messages](https://discord.com/blog/how-discord-indexes-trillions-of-messages)A Redis queue hit its CPU limit and dropped messages.
- **Twitter timeline hot keys** [https://matthewtejo.substack.com/p/handling-hotkeys-in-timeline-storage](https://matthewtejo.substack.com/p/handling-hotkeys-in-timeline-storage)Hot-key counting in Redis and local caching. A former engineer's blog.
- **Alibaba Tair at Double 11** [https://www.alibabacloud.com/blog/596493](https://www.alibabacloud.com/blog/596493)Hot items overloading single nodes, and the fixes. A vendor page.
- **Figma postmortem** [https://www.figma.com/blog/postmortem-service-disruptions-on-june-6-and-7-2022/](https://www.figma.com/blog/postmortem-service-disruptions-on-june-6-and-7-2022/)More nodes made a cluster-bus CPU loop worse.
- **Cloudflare anomaly detection** [https://blog.cloudflare.com/lessons-learned-from-scaling-up-cloudflare-anomaly-detection-platform/](https://blog.cloudflare.com/lessons-learned-from-scaling-up-cloudflare-anomaly-detection-platform/)PFMERGE cost that grew with the data.
- **Swiggy pipelining** [https://bytes.swiggy.com/optimizing-batch-writes-to-redis-using-pipelining-d480ebaf4653](https://bytes.swiggy.com/optimizing-batch-writes-to-redis-using-pipelining-d480ebaf4653)Redis write time down 90% with batched pipelines.
- **Swiggy batch reads** [https://medium.com/swiggy-bytes/2x-improvement-in-latency-in-swiggy-data-science-platform-6101b7607530](https://medium.com/swiggy-bytes/2x-improvement-in-latency-in-swiggy-data-science-platform-6101b7607530)p99 from 144 ms to 71 ms at batch size 30.

The phase also names *Redis in Action* by Josiah Carlson, chapter 9 "Reducing memory use" and chapter 11 "Scripting with Lua". It also suggests searching for Instagram and Twitter posts on Redis memory. That suggestion has no link or claim, so the cases above replace it. The Redis support article on salting hot keys returned HTTP 403 and was not read.
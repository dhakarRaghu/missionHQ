# Phase 5 — Performance & Failures (the phase that keeps you off the pager)

Every prior phase gave you a piece of this one. Phase 0 said the round-trip is the cost and one slow command freezes everyone. Phase 2 showed a cache is a load multiplier. Phase 4 showed the topology varies. This phase puts them together into the skill that actually matters at 3am: **given "Redis is slow" or "Redis is out of memory," find the cause in minutes and know the fix.**

Because here's the pattern in Mindtickle's own incident history: *the Redis was never broken.* INCP-520 wasn't a Redis bug — it was no-TTL keys meeting the `volatile-lru` policy. The CE incident wasn't a Redis bug — it was a hot key that should have been cached. Every documented Redis incident was a **usage** failure that a person could have caught with `SLOWLOG GET`, `INFO memory`, `--bigkeys`, and an understanding of eviction. This phase makes you that person. (One honesty note: a "CallAI Jan-2024 memory burst" surfaced in earlier research, but Compass could not confirm it in Jira/Confluence — the only Jan-2024 CallAI incident on record, INCP-527, was an unrelated GraphQL/Postgres outage. Treat the CallAI-memory story as unverified; **INCP-520 is the one confirmed memory incident**.)

The four failure families, and the tool that finds each:
- **Too many round-trips** (the N+1 Redis problem) → the cost model + pipelining.
- **Slow commands** (O(N) blockers) → `SLOWLOG`.
- **Big keys** (one huge collection) → `--bigkeys` / `MEMORY USAGE`.
- **Hot keys** (one key, all the traffic) → `--hotkeys` / key-level metrics.
- **Memory pressure** (the eviction cliff) → `INFO memory` + the right `maxmemory-policy`.

By the end you'll have reproduced INCP-520 on your laptop (no-TTL keys surviving `volatile-lru` until writes fail with OOM), watched `KEYS` take 33ms while `SCAN` takes 0.6ms, found and safely deleted a 100k-member big key, and be able to read `INFO memory` like an on-call.

Time: 4–6 days. This is the phase you'll re-open during a real incident — build the muscle memory now.

## What we cover in Phase 5:
```
┌──────────────────────────────────────────────────────────────────────────┐
│  5.1  Pipelining          — the round-trip is the cost; batch it (the #1  │
│                             lever, revisited with the math)               │
│  5.2  Slow commands       — the O(N) blockers, their SCAN swaps, SLOWLOG  │
│  5.3  Big keys            — find them (--bigkeys), why they hurt, UNLINK   │
│  5.4  Hot keys            — one key, all the traffic; detect + mitigate    │
│  5.5  Eviction policies   — all 8, the volatile-lru trap, INCP-520 live    │
│  5.6  Memory & monitoring — used_memory, fragmentation, what to alert on   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 5.1 — Pipelining (the highest-leverage optimization, revisited)

**Why this matters:** the single most common "Redis is slow" ticket at every company — Mindtickle included — is not a slow command. It's a *fast* command called N times sequentially in a loop. You saw this in Phase 0; now you own the fix and the math, because it's the first thing to check when latency is high and no individual command is slow.

Recall the cost model (Phase 0.2): Redis executes a `GET` in ~1µs, but your client sees ~300–600µs per call because of the network round-trip. So the cost of a Redis operation, from where your code sits, is **the round-trip, not the command**. Which means:

```
   N sequential GETs:                    N pipelined GETs:
   latency ≈ N × RTT                     latency ≈ 1 × RTT + N × ~1µs
   500 × 400µs = 200ms                   1 × 400µs + 500µs ≈ 0.9ms
                                         → measured 224x speedup (Phase 0 demo)
```

Pipelining sends N commands in one write and reads N replies in one pass — the round-trip is paid roughly *once* instead of N times. Same server work; the only thing that changed is the number of network trips. Three ways to do it, in order of preference when they apply:

1. **Native multi-key commands** — `MGET`/`MSET`/`HMGET`/`SADD`(multi) do N operations in one command *and* one round-trip. Always prefer these when the operation is uniform. (Cluster-mode caveat from Phase 4.5: multi-key commands need same-slot keys → hash tags.)
2. **Pipeline** — `rdb.Pipeline()` when the commands differ (`GET` + `INCR` + `EXPIRE`…). Batches arbitrary commands into one round-trip.
3. **Lua script / `MULTI`** — when you also need atomicity across the batch (Phase 3's compare-and-delete is a Lua example).

The trap to internalize: **the N+1 Redis problem is invisible at N=3 in dev and a 200ms latency bomb at N=500 in prod.** A loop that does `for _, id := range ids { rdb.Get(ctx, key(id)) }` looks innocent in code review and melts a hot path when `ids` grows. When you see a Redis-latency ticket and no single command is in `SLOWLOG`, look for the loop.

**The sentence to remember:** the cost is the round-trip, so N sequential calls cost N×RTT while a pipeline/MGET costs ~1×RTT — the highest-leverage Redis optimization is almost always "make fewer round-trips," not "make commands faster."

**The trap:** a Redis call inside a loop over a collection. Batch it (`MGET`/pipeline) or you've built an N+1 that scales with your data.

**Try this now:**
```bash
go run ./phase00_why_redis/pipeline_vs_roundtrip -keys 500   # ~224x (Phase 0 demo)
go run ./phase00_why_redis/pipeline_vs_roundtrip -keys 2000  # gap widens with N
```

---

## 5.2 — Slow commands (the O(N) blockers and how to catch them)

**Why this matters:** because Redis is single-threaded (Phase 0.1), a slow command doesn't just slow *itself* — it freezes *every* client on the instance for its whole duration. So "which commands are slow, and are we running them?" is a top-priority question, and `SLOWLOG` answers it in one line. This is the first tool you reach for in any latency investigation.

The offenders all share one trait: **O(N) over a large collection or the whole keyspace.** The canonical list, with the safe swap:

```
┌───────────────────────────┬──────────┬──────────────────────────────────────┐
│ Blocking command          │ cost     │ Safe alternative                     │
├───────────────────────────┼──────────┼──────────────────────────────────────┤
│ KEYS <pattern>            │ O(N) all │ SCAN cursor  (incremental, cursor-based)│
│ SMEMBERS <big set>        │ O(N)     │ SSCAN                                 │
│ HGETALL <big hash>        │ O(N)     │ HSCAN, or HMGET <specific fields>     │
│ LRANGE key 0 -1 <big list>│ O(N)     │ LRANGE with a bounded range           │
│ ZRANGE ... (huge range)   │ O(logN+M)│ bound with LIMIT offset count         │
│ DEL <big key>             │ O(N) free│ UNLINK  (frees on a background thread) │
│ FLUSHALL / FLUSHDB (sync) │ O(N)     │ FLUSHALL ASYNC (or just don't, in prod)│
│ long Lua script           │ O(script)│ keep scripts O(small); no big loops   │
└───────────────────────────┴──────────┴──────────────────────────────────────┘
```

Measured, on 200k keys / a 200k-field hash (from the `slow_commands` program):

```
   KEYS 'k:*'      → 200,000 keys in 33ms    ← blocks EVERY client for 33ms
   SCAN (1 batch)  → 501 keys in 0.65ms      ← incremental, never blocks
   HGETALL bighash → 200,000 fields in 62ms  ← blocks for 62ms
   HSCAN (1 batch) → 1.1ms                    ← incremental
   HMGET f1 f2 f3  → 0.4ms                     ← get only what you need
```

Note the SCAN-family contract: they're **cursor-based** — you call repeatedly, passing the returned cursor, until it comes back 0. Each call returns a small batch and never blocks. The guarantee is weaker than `KEYS` (a key present the whole time is returned at least once; concurrent changes may or may not appear) — but that weakness is exactly what makes it safe: it doesn't materialize the whole keyspace in one blocking pass.

The tool that finds the offenders: **`SLOWLOG`.** Redis logs every command that exceeds `slowlog-log-slower-than` (default **10,000µs = 10ms**) into an in-memory ring buffer. `SLOWLOG GET 10` shows the last 10, with duration and args:

```
   127.0.0.1:6379> SLOWLOG GET 2
   1) duration: 29.781ms  args: [hgetall bighash]     ← there's your latency
   2) duration: 23.194ms  args: [keys k:*]            ← and the other one
```

**This is investigation step #1 for any "Redis is slow" page.** Before you look at anything else, `SLOWLOG GET` tells you if a specific command is the problem. If it's empty and latency is still high, the cause is round-trips (5.1) or a hot key (5.4), not a slow command.

**The sentence to remember:** O(N) commands (`KEYS`, `SMEMBERS`, `HGETALL`, `LRANGE 0 -1`, sync `DEL`/`FLUSHALL`, long Lua) block the single thread for every client — swap for the SCAN family or bounded ranges, and use `SLOWLOG GET` as your first investigation step.

**The trap:** `KEYS` in application code. It's fine in a `redis-cli` on a tiny dev DB and a cluster-freezing incident on a 40M-key prod keyspace. There is almost never a reason for `KEYS` in a running service — use `SCAN`.

**Try this now:**
```bash
go run ./phase05_perf/slow_commands -n 200000
# KEYS/HGETALL block for tens of ms and land in SLOWLOG; SCAN/HMGET are sub-ms.
```

---

## 5.3 — Big keys (the latency bomb hiding in your data model)

**Why this matters:** a "big key" — a hash/set/list/zset with millions of elements, or a multi-MB string — is a time bomb that ticks slowly: it grows over months, then one `HGETALL` or a failover-triggered `DEL` blocks the thread for hundreds of ms, or it silently concentrates memory and traffic onto one shard (a hot shard) in cluster mode. It's a *data-modeling* failure that surfaces as a *performance* incident.

Why big keys hurt, precisely — three ways:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  1. O(N) OPERATIONS BLOCK                                                │
│     HGETALL / SMEMBERS / DEL on a 5M-element key = O(5M) on the single   │
│     thread → hundreds of ms where NO other client is served (Phase 0.3). │
│                                                                          │
│  2. HOT SHARD (cluster mode)                                             │
│     A big key lives on ONE slot → ONE shard. That shard carries the      │
│     memory AND the traffic for it → uneven load, one node saturates      │
│     while others idle. Resharding can't split a single key.              │
│                                                                          │
│  3. FAILOVER / MIGRATION STALLS                                          │
│     Moving or freeing a huge key (reshard, DEL, expiry) is a big chunk   │
│     of work that stalls the thread at the worst time.                    │
└─────────────────────────────────────────────────────────────────────────┘
```

Finding them — two tools:

- **`redis-cli --bigkeys`** — samples the keyspace with `SCAN` and reports the largest key of each type. Safe to run (it uses `SCAN`, not `KEYS`). Your first move when memory is high or one shard is hot.
- **`MEMORY USAGE <key>`** — the exact bytes a specific key occupies. The `bigkey_scan` program uses `SCAN` + `TYPE` + per-type length + `MEMORY USAGE` to do the same thing programmatically:

```
   bigset    type=set   members=100,000  mem=5,412,968B   ← BIG KEY (5.4MB, one shard)
   smallset  type=set   members=10       mem=120B
```

Reading and deleting them safely:
- **Never `SMEMBERS`/`HGETALL`/`LRANGE 0 -1` a big key** — use the SCAN family (5.2). Measured: `SMEMBERS` on 100k members = 11.4ms (blocks); one `SSCAN` batch = 1.1ms.
- **Delete with `UNLINK`, not `DEL`.** `DEL` frees the memory synchronously on the main thread (blocks); `UNLINK` unlinks the key immediately and frees the memory on a background thread. Measured: `UNLINK` of the 100k-member set returned in 0.78ms.

But the real fix is upstream: **don't create big keys.** This is the Phase 1 modeling lesson cashing in — instead of one giant hash `company:c7:allusers` → shard it (`company:c7:users:{bucket}`), or use a different structure, or bound it. A key you can't bound is a key that will eventually be a big key.

**The sentence to remember:** big keys block on O(N) ops and create hot shards — find them with `--bigkeys`/`MEMORY USAGE`, read them with SCAN-family, delete them with `UNLINK`, and prevent them by bounding/sharding the data model (Phase 1).

**The trap:** an unbounded collection ("append every event for this company to one list/set/hash"). It's fine at launch and a big-key incident two years later. Bound it or shard it from day one.

**Try this now:**
```bash
go run ./phase05_perf/bigkey_scan -big 100000
# Finds the 5.4MB set; SMEMBERS(11ms) vs SSCAN(1ms); UNLINK vs DEL.
```

---

## 5.4 — Hot keys (one key, all the traffic)

**Why this matters:** a hot key is the failure that a *bigger cluster doesn't fix*. Sharding distributes *keys* across nodes, but a single hot key lives on a single shard — so all its traffic hits one node's single thread, and that node saturates while the rest of the cluster is bored. Mindtickle's CE incident was a hot-key-shaped problem: `GET /game` at 30,000/min all hitting content-engine because the response wasn't cached.

The anatomy:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  3-shard cluster, one hot key (company-settings for the biggest tenant): │
│                                                                          │
│     shard 0        shard 1 [HOT]         shard 2                         │
│     ~normal QPS    ████████████ 90%      ~normal QPS                     │
│                    CPU saturated                                         │
│                    ↑ one key, one slot, one shard → all its traffic here │
│                                                                          │
│  Adding shard 3 does NOT help — the hot key doesn't move or split.       │
└─────────────────────────────────────────────────────────────────────────┘
```

Detecting a hot key:
- **`redis-cli --hotkeys`** — requires the `maxmemory-policy` to be an **LFU** policy (`allkeys-lfu`/`volatile-lfu`), because it reads the per-key access frequency LFU maintains. Reports the most-accessed keys.
- **`MONITOR` sampling** — stream commands briefly and count key frequency (careful: `MONITOR` itself has overhead; sample, don't leave it running).
- **Server/CPU metrics** — in cluster mode, one shard's CPU/network far above the others is the tell.

Mitigating a hot key — three techniques, in order:
1. **Client-side / local cache** — cache the hot value in-process (a local `LoadingCache`) with a short TTL, so most reads never hit Redis at all. Mindtickle already does exactly this with in-process Guava caches in `game_engine`, `CoachingApiGateway`, `mt-api-java-client` (Phase 2.3) — that's hot-key mitigation, whether or not it was framed that way.
2. **Read replicas** — offload hot *reads* to replicas (Phase 4.2): the read load spreads across the replica set instead of hammering the primary.
3. **Key splitting / replication** — for an extreme hot key, store N copies (`hotkey:0`..`hotkey:N`) across slots and have clients read a random one, spreading the load across shards. Rarely needed; know it exists.

The connection to Phase 2: **the best hot-key fix is often "cache it better."** The CE incident's 30k/min was a hot key created by a caching bug; fixing the cache (MR !5436) fixed the hot key. A well-cached value with a high hit rate is, by definition, not hot at Redis.

**The sentence to remember:** a hot key saturates one shard's single thread and a bigger cluster can't fix it (the key doesn't split) — detect with `--hotkeys`/CPU-per-shard, mitigate with a local cache (Mindtickle's Guava caches), read replicas, or key-splitting.

**The trap:** "add shards to fix the slow cluster" when the problem is one hot key. You'll pay for more nodes and the hot shard stays saturated. Find the key first (`--hotkeys`), then cache or split it.

**Verify your understanding:** the CE `GET /game` incident put 30k/min on content-engine. Was that a hot *key* in Redis, or a hot *endpoint* that bypassed Redis? (It bypassed Redis — `cacheable:false` — so the load hit the *source*. The fix was to cache it, which is the "cache it better" hot-key mitigation. Same shape: concentrated load on one component.)

---

## 5.5 — Eviction policies (all 8, and the one that caused INCP-520)

**Why this matters:** when `used_memory` reaches `maxmemory`, what Redis does is determined entirely by one setting — `maxmemory-policy` — and the ElastiCache default (`volatile-lru`) has a failure mode that caused a 4h37m Mindtickle outage. Understanding all eight policies, and *specifically* why `volatile-lru` + no-TTL keys is a slow-motion outage, is non-negotiable operational knowledge.

The eight policies, grouped:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  WHEN used_memory reaches maxmemory, evict...                            │
│                                                                          │
│  noeviction     → nothing. WRITES FAIL with "OOM command not allowed".   │
│                   (reads + deletes still work.) ← raw-Redis default.      │
│                                                                          │
│  Evict from ALL keys:              Evict only from keys WITH a TTL:      │
│    allkeys-lru  (least recently     volatile-lru  ← ElastiCache default  │
│                  used)                volatile-lfu (least frequently used)│
│    allkeys-lfu  (least frequently   volatile-ttl  (shortest TTL first)   │
│                  used)               volatile-random                     │
│    allkeys-random                                                        │
│                                                                          │
│  LRU = evict the key not touched in the longest time.                    │
│  LFU = evict the key accessed the fewest times (better for skewed access)│
└─────────────────────────────────────────────────────────────────────────┘
```

Now the trap, reproduced exactly by the `eviction_policies` program filling an 8mb instance with 1500 keys (half with a TTL, half without):

```
   policy=noeviction    survived ttl=259 nottl=259 | OOM write errors=982
   policy=allkeys-lru   survived ttl=258 nottl=255 | OOM=0 | evicted=987
   policy=volatile-lru  survived ttl=0   nottl=515 | OOM write errors=471  ← !!
```

Read the `volatile-lru` row carefully, because it *is* INCP-520: **the no-TTL keys survived (515 of them) and all the TTL keys were evicted — then, once only no-TTL keys remained and memory was still full, 471 writes failed with OOM.** `volatile-lru` can only evict keys that *have* a TTL. A key written with **no** TTL is **unevictable ballast** — the policy literally cannot touch it. So:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  INCP-520, mechanically (Nov 2023, 4h37m)                                │
│                                                                          │
│  ElastiCache default policy = volatile-lru                               │
│  LLM Gateway writes keys with NO TTL to the shared cluster               │
│  → those keys are UNEVICTABLE                                            │
│  → used_memory climbs (evictable TTL keys get purged, but no-TTL piles up)│
│  → cluster hits 100%, nothing left to evict                             │
│  → WRITES FAIL (OOM) for EVERY tenant, incl. the Uploader (shared box)   │
│                                                                          │
│  Confirmed: Nov 29 2023, llm-api-gateway shared a cluster with the       │
│  admin Uploader. ~3h25m customer impact (~4h37m end-to-end). 5-whys:     │
│  shared cluster + no-TTL keys + a memory alert that FIRED but was MISSED  │
│  because it had no owner tag. Fix: deleted no-TTL keys, scaled 1GB→3GB,   │
│  added TTLs to all LLM Gateway keys, fixed the alert-owner bug (MR 29298).│
└─────────────────────────────────────────────────────────────────────────┘
```

How to choose:
- **Pure cache, every key rebuildable?** `allkeys-lru` (or `allkeys-lfu` for skewed access) — evict anything, writes never fail. Simplest, safest for a cache.
- **Mix of cache + must-keep keys, and you TTL your cache keys religiously?** `volatile-lru` works — *but only if you never write a no-TTL key you can't afford to keep*. Given human nature, this is fragile.
- **The Mindtickle reality:** clusters run the AWS default `volatile-lru`, which means the org is one no-TTL-key-writing service away from INCP-520 every day. The durable fix is **every cache key gets a TTL** (Phase 2's discipline) — or switch to `allkeys-lru` so a forgotten TTL can't become unevictable ballast.

**The sentence to remember:** `maxmemory-policy` decides what "cache full" means — `noeviction` fails writes, `allkeys-*` evicts anything, and `volatile-*` evicts *only keys with a TTL*, so `volatile-lru` (the ElastiCache default) + a no-TTL key = unevictable ballast = the INCP-520 slow-motion OOM.

**The trap:** writing a key without a TTL on a `volatile-lru` cluster. It can never be evicted; enough of them and the cluster fills and every tenant's writes fail. Either TTL everything or run `allkeys-lru`.

**Try this now:**
```bash
go run ./phase05_perf/eviction_policies
# Watch volatile-lru: nottl keys survive, writes eventually OOM — INCP-520 live.
```

---

## 5.6 — Memory & monitoring (reading INFO like an on-call)

**Why this matters:** you can't prevent what you can't see. Every memory incident has a slow ramp visible in `used_memory` for hours before it becomes an outage — *if someone is watching the right number*. This section is the dashboard-and-alert layer that turns "surprise 3am OOM" into "a ticket at 60% memory."

The numbers that matter, from `INFO memory` and `INFO stats`:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  used_memory            bytes Redis has allocated for data              │
│  used_memory_rss        bytes the OS gave the process (includes frag)   │
│  maxmemory              the cap (0 = unlimited = dangerous)             │
│  mem_fragmentation_ratio  rss/used. ~1.0-1.5 healthy; >1.5 fragmented;  │
│                            <1.0 means SWAPPING (very bad)               │
│  evicted_keys           cumulative evictions — rising = memory pressure  │
│  keyspace_hits/misses   the hit rate (Phase 2's load multiplier)        │
│  connected_clients      connection count (leak detection)               │
│  instantaneous_ops_per_sec  current throughput                          │
└─────────────────────────────────────────────────────────────────────────┘
```

What to alert on (the on-call's early-warning set):
1. **`used_memory / maxmemory` > 75%** — the ramp. This is the alert that would have caught INCP-520 hours early. On ElastiCache this is the CloudWatch `DatabaseMemoryUsagePercentage`.
2. **`evicted_keys` rate rising** — you're past comfortable and actively losing cache entries. Fine for a pure `allkeys-lru` cache; a red flag if you expected keys to persist.
3. **CPU per shard** (cluster mode) — one shard far above the others = hot key/shard (5.4).
4. **`mem_fragmentation_ratio` > 1.5** or `< 1.0` — fragmentation waste, or swapping (catastrophic — Redis + swap = latency death).
5. **SLOWLOG length growing** — O(N) commands creeping in (5.2).

At Mindtickle these live in Datadog + CloudWatch, routed to PagerDuty (prod) and Slack `#slack-storage-alerts`, with documented thresholds (Compass-verified): **memory 75% prod / 70% staging, CPU >80%, connections >20% of the 65,000 limit, cache hit rate <70%, replica lag >0.1s**, plus failover/restart detection — and a runbook ("Resolution for ElastiCache Alerts"). So the 75% memory alert *exists*. The twist that makes INCP-520 sharper: **the alert fired and was missed because it lacked an owner tag** — a routing failure, not a monitoring gap. Two real gaps remain: (1) that owner-tag bug (fixed post-incident, MR 29298), and (2) **no hot-key or slow-command alerting** — the monitoring is capacity/health-oriented (memory, CPU, connections), not command-pattern-oriented, so a `KEYS`-in-a-loop or a hot key wouldn't page anyone directly. The operational rule still holds: **watch `used_memory` percentage and `evicted_keys` — the ramp is always visible before the cliff — and make sure the alert has an owner.**

Two more memory facts worth carrying:
- **`maxmemory` should be ~75% of the node's RAM**, not 100% — Redis needs headroom for the copy-on-write fork during `BGSAVE`/replication (a snapshot can transiently double memory for changed pages). Setting `maxmemory` to the full node size invites an OOM-kill during a backup.
- **Encoding matters** (Phase 1.7) — a hash of 200 small fields as one `listpack` is ~10x cheaper than 200 String keys. When memory is high, `OBJECT ENCODING` on your biggest keys sometimes reveals a cheap fix.

**The sentence to remember:** the memory cliff is always preceded by a visible ramp — alert on `used_memory`/`maxmemory` > 75% and rising `evicted_keys`, keep `maxmemory` at ~75% of RAM for fork headroom, and watch `mem_fragmentation_ratio` for swapping.

**The trap:** `maxmemory 0` (unlimited) or `maxmemory` = full node RAM. The first lets Redis grow until the OS OOM-kills it; the second leaves no headroom for the `BGSAVE` fork and OOM-kills during a backup. ~75% is the number.

**In your codebase:** the ElastiCache clusters run `volatile-lru` on the default parameter group (Phase 4). Check: is there a Datadog monitor or CloudWatch alarm on `DatabaseMemoryUsagePercentage` for `common-redis` / `equip-redis`? Given INCP-520, an alert at 75% is the cheapest insurance the org can buy.

---

## 🧪 Hands-on lab — the exercises that teach Phase 5

Setup:
```bash
cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d && docker exec redis-study redis-cli PING   # → PONG
```

- [ ] **E1. Pipelining vs sequential (the #1 lever).**
  - Run: `go run ./phase00_why_redis/pipeline_vs_roundtrip -keys 500` then `-keys 2000`.
  - Expected: 30–224x speedup; gap widens with N.
  - Teaches: the round-trip is the cost; batch it.

- [ ] **E2. Slow commands + SLOWLOG.**
  - Run: `go run ./phase05_perf/slow_commands -n 200000`
  - Expected: KEYS ~33ms, HGETALL ~62ms, both in SLOWLOG; SCAN/HMGET sub-ms.
  - Teaches: O(N) blockers, their SCAN swaps, and SLOWLOG as step #1.

- [ ] **E3. Read SLOWLOG by hand.**
  - Run: `docker exec redis-study redis-cli CONFIG SET slowlog-log-slower-than 1000; docker exec redis-study redis-cli DEBUG POPULATE 500000; docker exec redis-study redis-cli KEYS '*' > /dev/null; docker exec redis-study redis-cli SLOWLOG GET 3`
  - Expected: the `KEYS *` shows up with its microsecond duration.
  - Teaches: the exact command you run first in a latency page.

- [ ] **E4. Find big keys.**
  - Run: `go run ./phase05_perf/bigkey_scan -big 100000` then `docker exec redis-study redis-cli --bigkeys` (after seeding).
  - Expected: the 100k-member set flagged (~5.4MB); `--bigkeys` reports the biggest per type.
  - Teaches: `--bigkeys` and `MEMORY USAGE` for big-key detection.

- [ ] **E5. (Break it) SMEMBERS a big key while watching latency.**
  - Run: seed `bigset` (100k), then `docker exec redis-study redis-cli --latency &` and in another shell `docker exec redis-study redis-cli SMEMBERS bigset > /dev/null`.
  - Expected: the latency meter spikes during the SMEMBERS.
  - Teaches: a big-key O(N) read blocks every client (Phase 0.3, made concrete).

- [ ] **E6. UNLINK vs DEL.**
  - Run: seed `bigset`, then time `docker exec redis-study redis-cli DEL bigset` vs (re-seed and) `docker exec redis-study redis-cli UNLINK bigset`.
  - Expected: UNLINK returns instantly; DEL blocks proportional to size.
  - Teaches: always UNLINK big keys.

- [ ] **E7. Reproduce INCP-520.**
  - Run: `go run ./phase05_perf/eviction_policies`
  - Expected: `volatile-lru` → nottl keys survive, TTL keys evicted, then 471 OOM write errors.
  - Teaches: no-TTL keys are unevictable under volatile-lru → the outage mechanism.

- [ ] **E8. (Break it) OOM under noeviction.**
  - Run: `docker exec redis-study redis-cli CONFIG SET maxmemory 4mb; docker exec redis-study redis-cli CONFIG SET maxmemory-policy noeviction`, then `docker exec redis-study redis-cli DEBUG POPULATE 100000` (or write 10KB values in a loop).
  - Expected: writes start returning `OOM command not allowed`.
  - Teaches: what `noeviction` at the cap looks like. Reset: `CONFIG SET maxmemory 256mb`.

- [ ] **E9. Watch eviction happen.**
  - Run: `CONFIG SET maxmemory-policy allkeys-lru; CONFIG SET maxmemory 8mb`, seed many 10KB keys, watch `INFO stats | grep evicted_keys` climb and `INFO memory | grep used_memory_human` hold near the cap.
  - Teaches: eviction keeps writes flowing by discarding LRU data — the metric to alert on.

- [ ] **E10. Read INFO memory like an on-call.**
  - Run: `docker exec redis-study redis-cli INFO memory | grep -E "used_memory_human|maxmemory_human|mem_fragmentation_ratio|evicted"` and `INFO stats | grep -E "keyspace_hits|keyspace_misses|evicted_keys"`.
  - Compute: hit rate and fragmentation ratio. Are they healthy?
  - Teaches: the exact fields you scan during a memory investigation.

- [ ] **E11. Detect a hot key.**
  - Run: `CONFIG SET maxmemory-policy allkeys-lfu`, hammer one key: `for i in $(seq 1 5000); do docker exec redis-study redis-cli GET hot >/dev/null; done` (seed `hot` first), then `docker exec redis-study redis-cli --hotkeys`.
  - Expected: `hot` reported as the most-accessed key.
  - Teaches: `--hotkeys` needs an LFU policy; how to find the key saturating a shard.

- [ ] **E12. TTL audit (find the INCP-520 risk).**
  - Run: write some keys with and without TTL, then scan for no-TTL keys: for each key `docker exec redis-study redis-cli TTL <key>` → `-1` means no expiry.
  - Teaches: no-TTL keys are the eviction risk; auditing for `-1` is how you find ballast before it fills the cluster.

---

## 🏢 Mindtickle anchor — things to check in the codebase

1. **The live no-TTL bug (a latent INCP-520).** Open `ai-tutor/src/usecase/memory/memoryUsecaseImpl.go`. Compass found: a session-memory key is first written with a correct 24h TTL, but the "condensation" update path rewrites it with `0*time.Hour` — which **strips the TTL and makes the key permanent**. It's a per-session key (unbounded cardinality) on a `volatile-lru` cluster → the exact INCP-520 pattern. Worse, a unit test *asserts* the `0*time.Hour` call as expected, so it wasn't caught as a regression. Questions: why is `0` TTL on a per-session key dangerous under `volatile-lru`? What's the one-line fix? Also check `platform-go-rest-client`'s `RedisClusterClient.Set` — it requires callers to pass a TTL with no safe default, so any caller passing `0` creates the same risk across ~30 dependent repos.

2. **The hot-key mitigation you already have.** Find the in-process Guava `LoadingCache` in `game_engine`/`CoachingApiGateway`/`mt-api-java-client` (Phase 2.3). Question: what hot key does each protect Redis from? (These local caches absorb the hottest reads so they never reach Redis — hot-key mitigation, technique #1 from 5.4.)

3. **The N+1 hunt.** Pick a request path in a service you own that reads several Redis keys. Question: does it loop with sequential `Get`s, or batch with `MGET`/pipeline? If it loops over a collection, that's an N+1 — estimate the round-trips at p95 collection size × the in-AZ RTT (~0.5ms). (Compass note: most Mindtickle Redis reads are single-key; the risk is any new loop.)

4. **Memory monitoring (it exists — the gap is elsewhere).** The shared clusters *do* have Datadog/CloudWatch alerts at 75% memory (prod), CPU >80%, hit rate <70%, replica lag >0.1s, routed to PagerDuty + `#slack-storage-alerts`, with a runbook. Questions: given the alert existed, why did INCP-520 still happen? (It fired but was **missed — no owner tag**; fixed in MR 29298.) And what's still *not* alerted on? (Hot keys and slow commands — no SLOWLOG-based alerting. A `KEYS`-in-a-loop or a hot key wouldn't page anyone directly.) The lesson: an alert with no owner is not an alert.

---

## ✅ Checkpoint 5 — answer in your own words

**Q1.** Reproduce INCP-520 in words, mechanically. The cluster runs `volatile-lru`. A service writes keys with no TTL. Walk through what happens to `used_memory`, why the policy can't save the cluster, why *writes* fail (and reads don't), and why a *co-tenant* service goes down. Then give two independent fixes (one per-service, one cluster-wide) and say which you'd do first.

**Q2.** A service's p99 latency is 40ms but `SLOWLOG GET 20` is empty and no single command is slow. Walk through your diagnosis: what are the two most likely causes given an empty SLOWLOG, how do you confirm each, and what's the fix for each? (Hint: 5.1 and 5.4.)

**Q3.** Show the math. A grading flow does 40 sequential `HGET`s (one per rubric item) against in-AZ ElastiCache, RTT p50 0.5ms. What's the added latency? Rewrite it as one command — which command, and what's the new latency? Now the cluster-mode twist: what must be true about the 40 keys for that one command to be *legal*, and how do you guarantee it?

**Q4.** You run `redis-cli --bigkeys` and find a 4-million-member set `company:c7:all_viewers` at 240MB. Explain the three distinct problems this one key causes (block, hot shard, migration), why adding shards won't help, and design the fix (how would you re-model it so no single key is huge?). What command do you use to delete the old one safely, and why not `DEL`?

**Q5.** Your ElastiCache node is `cache.r6g.large` (~13GB). What should `maxmemory` be set to, and why not the full 13GB? Walk through what happens during a `BGSAVE` fork that makes the headroom necessary, and what fails if you skip it.

**Q6.** A colleague proposes switching the shared cluster from `volatile-lru` to `allkeys-lru` "so we stop having OOM incidents." Argue both sides: what does this fix (INCP-520-style unevictable ballast), what does it *break* or risk (which keys can now be silently evicted?), and what's the precondition that makes it safe? What's the alternative that fixes the root cause instead of the symptom?

**Q7.** Design the alerting for a shared Redis cluster given Mindtickle's incident history (INCP-520 memory, CE hot endpoint, slow commands). List the 4 metrics you'd alarm on, the threshold for each, and which past incident each would have caught early. Which single alert has the best cost/benefit?

---

## References & Further Learning

**Must-read (in order):**
- 📄 [Redis latency troubleshooting — official docs](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/) — the canonical checklist: intrinsic latency, slow commands, SLOWLOG, fork stalls, THP. (25 min) This is the page you open during an incident. Read BEFORE 5.2.
- 📄 [Redis eviction policies — official docs](https://redis.io/docs/latest/develop/reference/eviction/) — all 8 policies, LRU vs LFU internals, the approximation algorithm. (15 min) Read with 5.5.
- 📄 [Memory optimization — official docs](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/memory-optimization/) — used_memory, fragmentation, the listpack thresholds, `maxmemory` sizing. (20 min) Read with 5.6.
- 📄 [ElastiCache metrics you should monitor — AWS docs](https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/CacheMetrics.WhichShouldIMonitor.html) — `DatabaseMemoryUsagePercentage`, `Evictions`, `EngineCPUUtilization`, and the alarms to set. (15 min) The real monitoring layer.

**Deep dives:**
- 📄 [Redis SCAN command — the guarantees](https://redis.io/commands/scan/) — why SCAN is safe where KEYS isn't, and its exact (weaker) guarantee. (10 min)
- 📄 [redis-cli --bigkeys / --hotkeys / --memkeys](https://redis.io/docs/latest/develop/tools/cli/) — the diagnostic flags, how sampling works. (10 min)
- 📄 [Instagram / Twitter engineering on Redis memory at scale] — search "Instagram Redis memory optimization" and "Twitter Redis" — real war stories of big-key and memory battles. (varies)
- 📚 *Redis in Action* (Carlson), Ch. 9 "Reducing memory use" + Ch. 11 "Scripting with Lua" — memory encoding tricks and safe scripting. The memory chapter is the practical companion to 5.6.

**Official docs (bookmark):**
- [SLOWLOG](https://redis.io/commands/slowlog-get/) — `SLOWLOG GET/RESET/LEN`, `slowlog-log-slower-than`.
- [INFO](https://redis.io/commands/info/) — every field; memory and stats sections are the incident-relevant ones.
- [OBJECT ENCODING](https://redis.io/commands/object-encoding/) — check listpack vs hashtable when memory is high.

---

## Cheatsheet — Phase 5

```
THE 4 FAILURE FAMILIES → THE TOOL THAT FINDS EACH
  too many round-trips (N+1)  → the cost model; fix = pipeline / MGET
  slow O(N) commands          → SLOWLOG GET     (step #1 in any latency page)
  big keys                    → redis-cli --bigkeys / MEMORY USAGE <key>
  hot keys                    → redis-cli --hotkeys (needs LFU) / CPU-per-shard
  memory pressure             → INFO memory (used_memory/maxmemory, evicted_keys)

PIPELINING (the #1 lever)
  N sequential = N × RTT (~0.5ms each).  pipeline/MGET = ~1 × RTT.  → up to 100x+
  prefer: MGET/MSET/HMGET (1 cmd) > Pipeline (diff cmds) > Lua (needs atomicity)
  cluster mode: multi-key needs same slot → {hashTag}

O(N) BLOCKERS → SAFE SWAP (they freeze the single thread for EVERYONE)
  KEYS → SCAN   SMEMBERS → SSCAN   HGETALL → HSCAN/HMGET
  LRANGE 0 -1 → bounded range   DEL(big) → UNLINK   FLUSHALL → ASYNC (or don't)
  measured: KEYS 200k=33ms, HGETALL 200k=62ms | SCAN/HSCAN/HMGET = sub-ms

BIG KEYS (latency bomb + hot shard)
  find: --bigkeys, MEMORY USAGE <key>.  read: SCAN-family.  delete: UNLINK.
  fix upstream: bound/shard the model (Phase 1). unbounded collection = future big key.

HOT KEYS (one key, one shard — more nodes DON'T help)
  detect: --hotkeys (LFU policy) / one shard's CPU >> others
  fix: (1) local in-proc cache (MT's Guava caches) (2) read replicas (3) key-splitting

EVICTION POLICIES (what "cache full" MEANS)
  noeviction      → WRITES FAIL (OOM). raw-Redis default.
  allkeys-lru/lfu/random  → evict ANY key. writes never fail. safest for pure cache.
  volatile-lru/lfu/ttl/random → evict ONLY keys WITH a TTL.  ← ElastiCache default
  ⚠ volatile-lru + no-TTL key = UNEVICTABLE ballast → fills cluster → OOM = INCP-520
  rule: TTL every cache key, OR run allkeys-lru.

MEMORY & MONITORING (the ramp is visible before the cliff)
  INFO memory : used_memory, maxmemory, mem_fragmentation_ratio (1.0-1.5 ok, <1 SWAP)
  INFO stats  : evicted_keys (rising = pressure), keyspace_hits/misses (hit rate)
  ALERT ON: used_memory/maxmemory > 75% (would've caught INCP-520 early);
            evicted_keys rate; per-shard CPU (hot key); frag_ratio >1.5 or <1.0
  maxmemory ≈ 75% of node RAM (headroom for BGSAVE copy-on-write fork). NEVER 0.

INCIDENTS
  INCP-520 (Nov 29 2023, CONFIRMED): llm-api-gateway no-TTL keys + volatile-lru →
    unevictable → 100% mem → OOM for co-tenant Uploader. ~4h37m. Alert FIRED but
    was missed (no owner tag). Fix: TTLs, scale 1GB→3GB, fix alert owner (MR 29298).
  CE !5436:  hot endpoint (cacheable:false) → 30k/min on source; fix = cache it
  (CallAI Jan-2024 memory burst = UNVERIFIED, likely a mix-up — don't cite as fact)

MT MONITORING (exists — Datadog+CloudWatch→PagerDuty/#slack-storage-alerts)
  alerts: mem 75%prod/70%stg, CPU>80%, conns>20% of 65k, hitrate<70%, replica lag>0.1s
  GAPS: no hot-key / no SLOWLOG alerting (capacity-oriented only). "alert w/o owner = no alert"
  live no-TTL bug: ai-tutor memoryUsecaseImpl.go condensation path rewrites w/ 0*time.Hour
```

---

*Next: Phase 6 — Redis at Mindtickle (the capstone). go-redis/v9 patterns, the company-settings cache, Nyx (DynamoDB + Redis), and the CE bug fix — tying all six phases to the production code you now understand end to end. Say `next`.*

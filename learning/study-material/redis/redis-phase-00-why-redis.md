# Phase 0 — Why Redis (the framing phase)

You already use Redis every day — every service you touch at Mindtickle either reads from it or sits behind something that does. That's exactly why Phase 0 matters: **the engineers who cause Redis incidents are almost never the ones who don't know Redis; they're the ones who know it as "that fast cache thing" and stop there.** Mindtickle's own postmortem history proves it: an LLM gateway that wrote keys with no TTL and filled a shared cluster to 100% (4h37m of customer impact), a serializer that marked responses `cacheable:false` and silently turned 300 requests/min into 30,000/min, a client that assumed 2 replicas everywhere and added 2 seconds of latency in staging. None of those were "Redis bugs." All of them were mental-model bugs.

This phase installs the correct mental model: what Redis actually is (a single-threaded event loop with rich data structures bolted to a network socket), what it actually costs (round-trips, not commands), what its one great weakness is (head-of-line blocking), and why it won at Mindtickle over Memcached and DynamoDB. By the end you'll have *measured* all of this on your own machine — not read about it, measured it.

Time: one focused session (~2–3 hours with the lab). Don't skip the lab — Phase 0's claims are all falsifiable, and you should falsify-or-confirm every one of them.

## What we cover in Phase 0:

```
┌────────────────────────────────────────────────────────────────────────┐
│  0.1  What Redis actually is   — one thread, one event loop, real      │
│                                  data structures (not just KV)         │
│  0.2  The cost model           — the round-trip is the unit of cost,   │
│                                  not the command (you'll measure it)   │
│  0.3  The dark side            — head-of-line blocking: one slow       │
│                                  command stalls every client           │
│  0.4  Redis vs the field       — Memcached, DynamoDB, and what         │
│                                  Mindtickle actually chose (and why)   │
│  0.5  Beyond caching           — the six Redis patterns running in     │
│                                  Mindtickle production RIGHT NOW       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 0.1 — What Redis actually is (one thread, and that's the point)

Why this matters: every Redis performance mystery, every "why did all my reads spike at once", every "can I run this Lua script in prod" question resolves to one architectural fact. If you internalize only one thing from Phase 0, it's this one.

You might think a system serving 100,000+ operations per second must be a heavily multi-threaded beast with fine-grained locking. You'd be wrong — and the reason you're wrong is the reason Redis is fast.

**Redis executes commands on a single thread.** One event loop, written in C, doing this forever:

```
┌──────────────────────────────────────────────────────────────────────┐
│                    THE REDIS EVENT LOOP (one thread)                 │
│                                                                      │
│      ┌─────────────────────────────────────────────────┐            │
│      │  epoll_wait() — which sockets have data ready?  │◄─────┐     │
│      └────────────────────┬────────────────────────────┘      │     │
│                           ▼                                   │     │
│      ┌─────────────────────────────────────────────────┐      │     │
│      │  read a complete command from one client        │      │     │
│      │  e.g.  GET probe:key                            │      │     │
│      └────────────────────┬────────────────────────────┘      │     │
│                           ▼                                   │     │
│      ┌─────────────────────────────────────────────────┐      │     │
│      │  EXECUTE it against in-memory data structures   │      │     │
│      │  — no lock, no other thread can touch the data  │      │     │
│      │  — a GET is a hash lookup: ~1 microsecond       │      │     │
│      └────────────────────┬────────────────────────────┘      │     │
│                           ▼                                   │     │
│      ┌─────────────────────────────────────────────────┐      │     │
│      │  queue the reply, move to next ready client ────┼──────┘     │
│      └─────────────────────────────────────────────────┘            │
│                                                                      │
│   Clients: ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐  ...thousands,        │
│            │ A  │ │ B  │ │ C  │ │ D  │ │ E  │  all multiplexed      │
│            └────┘ └────┘ └────┘ └────┘ └────┘  onto ONE executor    │
└──────────────────────────────────────────────────────────────────────┘
```

Here's the counterintuitive part, and it's worth slowing down for: **for an in-memory store doing sub-microsecond operations, lock contention costs more than sequential execution.** If Redis were multi-threaded, every GET and SET would need to acquire locks (or use lock-free structures with their own coordination costs), threads would migrate between CPU cores trashing L1/L2 caches, and the kernel would burn cycles context-switching. Salvatore Sanfilippo (antirez, Redis's creator) did the math in 2009 and chose the boring answer: one thread, zero locks, zero races on the data path, maximal cache locality. In Go terms: it's the philosophy of "don't communicate by sharing memory" taken to its extreme — there is exactly one goroutine that owns ALL the data, and every client is a channel feeding it commands.

Two consequences you must internalize:

1. **Every command is atomic, for free.** `INCR views:page:42` can never race with another `INCR` — there's no "another" anything. This is why Redis is the industry-default building block for counters, rate limiters, and locks. Mindtickle's `mt-dashboard-api` rate limiter is exactly this: an atomic Lua script doing `INCR` + `EXPIRE` per route/company/user.
2. **Every command blocks every other command.** Full stop. A 2-second command means 2 seconds where *every service sharing that cluster* gets nothing. Section 0.3 makes you feel this.

(Pedantic footnote that will matter in Phase 5: since Redis 6.0, *network I/O* — reading requests and writing replies — can optionally use extra threads (`io-threads`), and things like large-key freeing (`UNLINK`) happen on background threads. Command *execution* remains single-threaded. The mental model stands.)

**The second half of "what Redis is": data structures, not just strings.** Memcached gives you `get`/`set` on opaque blobs. Redis gives you native structures with per-structure commands, and Mindtickle uses almost all of them in production today:

```
┌──────────────┬───────────────────────────┬─────────────────────────────────────┐
│ Structure    │ Core commands             │ Live Mindtickle example             │
├──────────────┼───────────────────────────┼─────────────────────────────────────┤
│ String       │ GET SET SETNX INCR EXPIRE │ buyer-persona cache in              │
│              │                           │ missions-processors (3-day TTL)     │
│ Hash         │ HGETALL HSET HDEL         │ session records in mt-login-provider│
│ Set          │ SMEMBERS SADD SREM        │ session-index sets, ACL scope keys  │
│ List         │ RPUSH LPOP LTRIM          │ FIFO work queue in                  │
│              │                           │ asset-hub-analytics                 │
│ Sorted Set   │ ZADD ZREM ZRANGEBYSCORE   │ in-progress translation-job markers │
│              │                           │ in course-qu-processors             │
│ Pub/Sub      │ PUBLISH SUBSCRIBE         │ content-sync dispatch packets in    │
│              │                           │ content-center-service              │
│ Streams,     │ XADD XREADGROUP /         │ (not yet used in core services —    │
│ HyperLogLog  │ PFADD PFCOUNT             │ Phase 1 covers when you'd want them)│
└──────────────┴───────────────────────────┴─────────────────────────────────────┘
```

**The sentence to remember:** Redis is a single-threaded event loop executing atomic operations on rich in-memory data structures — its speed and its fragility both come from the same design choice.

**The trap:** believing "single-threaded" means "can't hurt anyone else." The opposite is true: single-threaded means your one bad command hurts *everyone*.

**Try this now:** `docker-compose up -d` in the study `code/` dir, then `docker exec -it redis-study redis-cli MONITOR` in one terminal while you run `redis-cli SET a 1` and `redis-cli INCR counter` from another. MONITOR shows you the one command stream the one thread sees — every client, interleaved, in execution order.

---

## 0.2 — The cost model (the round-trip is the unit of cost)

Why this matters: the most common Redis performance mistake at every company — Mindtickle included — is not a slow command. It's a fast command called 500 times sequentially. If you learn the cost model in Phase 0, half of Phase 5 (performance) becomes obvious.

Here's the anatomy of a single `GET` from a Go service, with real proportions:

```
┌────────────────────────────────────────────────────────────────────────┐
│              WHERE A "REDIS GET" ACTUALLY SPENDS ITS TIME              │
│                                                                        │
│  your Go code          network + kernel           Redis server        │
│ ┌───────────┐   ~µs   ┌──────────────────┐  ~µs  ┌──────────────┐     │
│ │ rdb.Get() ├────────►│ write syscall,   ├──────►│ parse, hash  │     │
│ │           │         │ TCP, NIC, wire,  │       │ lookup,      │     │
│ │  (waits)  │◄────────┤ interrupt, read  │◄──────┤ reply        │     │
│ └───────────┘         │ syscall          │       │  ≈ 1-2 µs    │     │
│                       │  ≈ 100-600 µs    │       └──────────────┘     │
│                       │  (localhost) —   │                            │
│                       │  more cross-AZ   │        ← Redis's share     │
│                       └──────────────────┘          is ~1% of the     │
│                                                     total latency     │
└────────────────────────────────────────────────────────────────────────┘
```

These aren't textbook numbers — they're from `phase00_why_redis/latency_probe` in this course's code dir, run against the study container on this machine:

```
GET count       : 5000
GET p50         : 354µs      ← round-trip dominated
GET p99         : 591µs
GET max         : 15.8ms     ← OS scheduler hiccup, not Redis
```

Redis executed each of those GETs in about a microsecond (you can verify: `INFO commandstats` reports `usec_per_call`). The other ~350µs is wire, kernel, and client. Against ElastiCache in-VPC you'll see similar or slightly higher (~300–600µs p50 same-AZ, 1ms+ cross-AZ).

Now the punchline. If you need 500 keys and you loop:

```
                 SEQUENTIAL (what every codebase starts with)
  t ──────────────────────────────────────────────────────────────►
  │ RTT₁ │ RTT₂ │ RTT₃ │ ... 500 round-trips ...          │ RTT₅₀₀ │
  total = 500 × ~400µs  ≈  209 ms   (measured: 208.9 ms)

                 PIPELINED (one round-trip, 500 commands)
  t ──────────►
  │ 1 write carrying 500 cmds │ server: 500 × ~1µs │ 1 read, 500 replies │
  total ≈ 1 RTT + server work  ≈  0.9 ms   (measured: 934 µs)

                 measured speedup: 224x
```

Same server. Same commands. Same data. **224x** difference, purely from respecting the cost model. When someone says "Redis is slow" in a war room, your first question is now permanent: *how many round-trips is the caller making?*

This cost model also explains a production decision you'll meet in Phase 6: Mindtickle's `mt-api-java-client` caches whole CE API *responses* in Redis (keys like `CK|<scope>|md5(url)`) rather than individual fields — one round-trip retrieves the entire settings object instead of N field lookups.

**The sentence to remember:** Redis costs are measured in round-trips; the server's execution time is a rounding error.

**The trap:** adding "just one more Redis call" inside a loop over N items. It's invisible at N=3 in dev and a 200ms latency bomb at N=500 in prod.

**Try this now:**
```bash
cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
go run ./phase00_why_redis/latency_probe -n 10000
go run ./phase00_why_redis/pipeline_vs_roundtrip -keys 500
```
Your numbers will differ from mine; the *shape* (10–100x pipeline win) will not.

---

## 0.3 — The dark side (head-of-line blocking, or: how one command stalls a company)

Why this matters: this is THE Redis failure mode. Mindtickle's shared clusters (`common-redis-elasticcache`, the content-engine Redis) serve dozens of services each. One bad command from one service taxes all of them. You need to feel this viscerally before you ever ship a `KEYS`, a giant `SMEMBERS`, or a clever Lua script.

Recall 0.1: one thread executes commands one at a time. So what happens when one command is slow?

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Timeline: one slow command on a shared Redis                            │
│                                                                         │
│ t=0.000s  client A: GET hot:key            → replied in 400µs  ✓        │
│ t=0.001s  client B (some service): KEYS *  → starts scanning 4M keys    │
│ t=0.001s  client A: GET hot:key            → queued. waiting.           │
│ t=0.001s  client C: SETNX lock:xyz         → queued. waiting.           │
│ t=0.001s  client D: session HGETALL        → queued. waiting.           │
│           ...every client of every service on this cluster: waiting...  │
│ t=2.001s  KEYS * finally returns                                        │
│ t=2.001s  A, C, D execute in a burst — each took 2s from THEIR view     │
│                                                                         │
│ What Datadog shows: p99 latency spike on EVERY service using this       │
│ cluster, simultaneously. What the on-call sees: "everything is slow,    │
│ nothing deployed." Classic shared-Redis incident signature.             │
└─────────────────────────────────────────────────────────────────────────┘
```

You will reproduce this yourself in the lab with `blocking_demo`, which hammers fast GETs while firing one `DEBUG SLEEP 2`. Measured result on this machine:

```
[fast-reader] warm-up max GET latency: ~600µs      (normal)
[blocker]     issuing DEBUG SLEEP 2.0...
[fast-reader] GET took 2.002984042s  ← blocked behind the slow command
```

Your microsecond read waited the **full two seconds**. Two separate TCP connections — the serialization happens in the server's command loop, not in the client.

What "the slow command" looks like in real life (all of these have caused real incidents somewhere; two of them at Mindtickle):

- **`KEYS *`** on a big keyspace — O(N) over every key. Use `SCAN` (cursor-based, incremental) instead, always.
- **`SMEMBERS` / `HGETALL` / `LRANGE 0 -1` on a huge collection** — O(N) where N surprises you two years after launch. This is the "big key" problem; Phase 5 covers detection (`redis-cli --bigkeys`).
- **Long Lua scripts** — Lua runs atomically on the command thread; a loop over 100k items is a self-inflicted `DEBUG SLEEP`.
- **`FLUSHALL`/`FLUSHDB`** on large datasets (synchronous delete), or a `DEL` of one enormous hash — use `UNLINK` (async free) instead.
- **Volume, not code:** Mindtickle's Jan 2024 CallAI incident — a data-migration event burst filled Redis despite every key having a 30-day TTL. The commands were fine; the *aggregate write rate* wasn't.

And the second-order version of the same failure: **memory**. The single process owns a fixed `maxmemory`. Mindtickle's INCP-520 (Nov 2023): the LLM Gateway wrote keys with **no TTL** to a shared cluster, memory hit 100%, and the co-tenant Uploader service — which had done nothing wrong — was down alongside it for 4h37m. The fix was exactly what you'd guess: put TTLs on the keys, delete the orphans, grow the cluster. The lesson is sharper: **on a shared cluster, your neighbor's missing TTL is your outage.** (Also note from the deployment research: Mindtickle's ElastiCache clusters ship AWS default parameter groups — `volatile-lru` eviction, which only evicts keys that HAVE a TTL. Keys without TTLs are unevictable ballast. That detail turned a "cache full" into a "cluster down.")

**The sentence to remember:** one thread means one queue — a slow command or a full memory hurts every tenant of the cluster, not just the author of the mistake.

**The trap:** testing a command on a dev dataset of 1,000 keys and shipping it against a prod keyspace of 40 million. O(N) doesn't care about your intentions.

**Try this now:**
```bash
go run ./phase00_why_redis/blocking_demo -sleep 2
```
Then, for the production-realistic version: `redis-cli` → `SLOWLOG GET 10` — Redis keeps a log of every command that exceeded `slowlog-log-slower-than` (default 10ms). This is your first stop in any Redis latency investigation, forever.

---

## 0.4 — Redis vs the field (Memcached, DynamoDB, and what Mindtickle actually chose)

Why this matters: "why not just use X?" is a design-review question you will be asked. The generic answer is a table; the senior answer is knowing what YOUR company runs and why. Both follow.

```
┌──────────────────┬────────────────────┬───────────────────┬─────────────────────┐
│                  │      Redis         │    Memcached      │      DynamoDB       │
├──────────────────┼────────────────────┼───────────────────┼─────────────────────┤
│ What it is       │ in-memory data-    │ in-memory KV      │ managed, durable,   │
│                  │ structure server   │ cache, nothing    │ disk-backed NoSQL   │
│                  │                    │ else              │ database            │
│ Latency (typical)│ ~100-600µs         │ ~100-600µs        │ single-digit ms     │
│                  │ in-VPC RTT         │ (same: RTT-bound) │ (p99 ~10-20ms)      │
│ Threading        │ 1 exec thread      │ multi-threaded    │ n/a (managed)       │
│                  │ (+I/O threads 6.0+)│ scales vertically │ scales horizontally │
│ Data structures  │ strings, hashes,   │ opaque blobs only │ items + GSIs/LSIs,  │
│                  │ lists, sets, zsets,│                   │ no in-place structs │
│                  │ streams, HLL, geo  │                   │                     │
│ Atomic primitives│ INCR, SETNX, Lua,  │ incr/decr, cas    │ conditional writes, │
│                  │ transactions       │ only              │ optimistic locking  │
│ Persistence      │ optional (RDB/AOF) │ none — restart =  │ always durable,     │
│                  │ — Phase 4          │ empty cache       │ multi-AZ replicated │
│ TTL / eviction   │ per-key TTL, 8     │ per-key TTL, LRU  │ per-item TTL        │
│                  │ eviction policies  │ only              │ (lazy, ~48h grain)  │
│ Pub/Sub / queues │ yes (native)       │ no                │ via Streams+Lambda  │
│ Cost model       │ pay for RAM        │ pay for RAM       │ pay per request +   │
│                  │ provisioned        │ provisioned       │ storage             │
│ Use when         │ cache + counters + │ pure ephemeral    │ durable KV at scale,│
│                  │ locks + queues +   │ page/fragment     │ serverless-friendly,│
│                  │ sessions on one    │ cache, nothing    │ don't want to size  │
│                  │ tool               │ shared/atomic     │ RAM ever            │
└──────────────────┴────────────────────┴───────────────────┴─────────────────────┘
```

The honest framing: **Memcached vs Redis is a solved argument** (Memcached wins only on "I want dumb multi-threaded blob caching with zero features" — and Redis 6+ I/O threads eroded even that), while **Redis vs DynamoDB is a real trade** — volatile speed vs durable scale, RAM-pricing vs request-pricing. AWS's own guidance: cache and coordination → ElastiCache; durable source-of-truth KV → DynamoDB; and very often *both*, DynamoDB as truth with Redis in front.

Now the Mindtickle reality, from a full code sweep (this is Compass-verified, not folklore):

- **Memcached: not used. At all.** Every `net.spy.memcached` import in the codebase (`ce-course-qu`, `ce-checklist`, `ce-content`, `CoachingUserActivityManagement`) is either the `CASValue` type reused for Couchbase-compat semantics or a doc reference to Couchbase's internal "memcached bucket" type. There is no Memcached host, client, or pool anywhere.
- **DynamoDB: never a Redis alternative.** Everywhere DynamoDB appears (`ce-uma/app/helper/DynamoDB.java`, `coaching-module-management`, `analytics-sparkio`'s `ENABLE_DYNAMODB` flag), it implements the same interface as a sibling `Couchbase.java` — it's the **Couchbase replacement**, the durable primary store. In those same services, Redis stays in active use as the cache in front. Complementary, not competing.
- **The one real DynamoDB+Redis combo** is instructive precisely because it uses each for what it's for: `qa-automation/nyx` (the learning-site pool manager for CI). DynamoDB holds the durable site records with a `version` field for optimistic concurrency (many parallel CI runs claiming/releasing sites); Redis holds exactly one key — `nyxLastLsIdValue` — an **atomic counter** handing out unique sequential IDs across concurrent inserts. Durable versioned state where durability matters; an atomic single-threaded counter where atomicity matters. That division of labor IS the answer to "Redis vs DynamoDB."

**The sentence to remember:** Redis wins not by being the fastest cache but by being the only tool that is simultaneously your cache, your counter, your lock, your queue, and your session store — one connection, one operational surface.

**The trap:** using Redis as a durable source of truth. It's RAM with optional, best-effort persistence (Phase 4 will horrify you with the details). If losing the data is an incident, the data does not live in Redis.

**Verify your understanding:** Mindtickle stores sessions in Redis (`mt-login-provider`). Sessions die if Redis dies. Why is that an acceptable trade here, and what property of sessions makes it so? (Answer shape: worst case = users re-login; data is reconstructible by its owner; durability requirement is soft.)

---

## 0.5 — Beyond caching (the six patterns already running in your production)

Why this matters: the course is called "Caching, Locking, and Beyond" because Redis-as-GET/SET is maybe half of what Mindtickle runs on it. Here's the actual production topology — every pattern below is live code you can open today, and each maps to the phase that teaches it.

```
┌───────────────────────────────────────────────────────────────────────────┐
│              REDIS AT MINDTICKLE — production usage map                   │
│         (~34 services, 12+ repos, several shared ElastiCache clusters)    │
│                                                                           │
│                    ┌──────────────────────────┐                           │
│   ┌───────────────┤   ElastiCache clusters    ├────────────────┐          │
│   │               │ common-redis, content-    │                │          │
│   │               │ engine-redis, equip-…,    │                │          │
│   │               │ question-service-…        │                │          │
│   │               └──────────────────────────┘                 │          │
│   ▼                          ▼                                 ▼          │
│ ① CACHING (dominant)       ② SESSIONS                ③ LOCKING            │
│ cache-aside w/ TTL         express-session +         redsync (Redlock) in │
│ ce-uma, integrations-      connect-redis, 8h TTL,    content-center-svc;  │
│ selfserve (30min TTL),     ioredis.Cluster           hand-rolled SETNX in │
│ missions-processors        (admin-tools);            ai-tutor, copilot-   │
│ buyer-persona (3d TTL),    hashes+sets in            chat-agent, asset-   │
│ mt-api-java-client         mt-login-provider         hub-analytics, ext-  │
│ CK|/SK| response cache     (Go)                      sharing… (8 repos)   │
│      → Phase 2                  → Phase 1,6               → Phase 3       │
│                                                                           │
│ ④ IDEMPOTENCY/DEDUP        ⑤ QUEUES & PUB/SUB        ⑥ RATE LIMITING      │
│ SET NX EX idempotency      RPush/LPop FIFO in        Lua INCR+EXPIRE      │
│ keys: hermes (python),     asset-hub-analytics;      fixed window in      │
│ assessment-gpt             PUBLISH/SUBSCRIBE         mt-dashboard-api     │
│ (SetKeyIfNotExists);       dispatch packets in       (fails OPEN);        │
│ zset job markers in        content-center-service;   legacy LPUSH/LTRIM   │
│ course-qu-processors       istio per-svc             sliding list; Kong   │
│      → Phase 3                 redis:alpine          rate-limiting-adv    │
│                                → Phase 1                  → Phase 1,5     │
└───────────────────────────────────────────────────────────────────────────┘
```

Walk through what's remarkable here:

**① Caching is the dominant pattern but not a single pattern.** The company-settings pipeline alone is a three-layer design you'll dissect in Phase 6: `content-engine` owns the authoritative settings and deletes a Redis "scope marker" key on every write (`Scope|COMPANY_<id>` via `Redis.bulkRemove`); every Java consumer caches full API responses through `mt-api-java-client` (`CacheReponseUtils.java`, keys `CK|`/`SK|`/`MSK|` + scope + md5(url), default TTL 3600s via `REDIS_CACHE_EXPIRY`) with the scope-deletion giving instant invalidation and the TTL as fallback; and `integrations-workflow` runs its own 600s pure-TTL `CompanySettingsCache` on the Lambda side. Delete-on-write + TTL-fallback, no Kafka invalidation anywhere in the chain. That design — and where it cracks — is a whole checkpoint question in Phase 2.

**③ Locking exists in three quality tiers in the same codebase** — a preview of Phase 3's central argument. `content-center-service` uses `redsync` (the Redlock library: random lock value, atomic compare-and-delete unlock). Six other repos hand-roll `SETNX` with varying rigor (`ai-tutor`'s invitation-email lock, `copilot-chat-agent`'s session-init lock, `asset-hub-analytics`'s SETNX + exponential backoff). And `course-qu-processors` improvises a sorted-set-based in-progress marker (`ZAdd`/`ZRem` + `Expire`) for translation jobs. When you reach Phase 3 you'll evaluate each: who can deadlock, who can double-execute, who forgot fencing.

**⑥ Rate limiting shows pattern evolution in the fossil record.** `integrations-selfserve` still carries the legacy version (a LPUSH/LTRIM sliding list with an app-side lock — not atomic); `mt-dashboard-api` has the modern one (a Lua script doing INCR+EXPIRE+TTL atomically on the command thread — remember 0.1: Lua atomicity is free single-threadedness); and `mt-open-api` delegates to Kong's `rate-limiting-advanced` plugin entirely. Three generations, all live.

And one more that hides in plain sight: **every deployed service carries a Redis** — `devops-helm-charts/default-service-template/templates/istio-rate-limit.yaml` ships a single-replica `redis:alpine` Deployment per service (`{{ .Values.app }}-ratelimiting-service-redis`, port 6379, istio sidecar injection disabled) as the counter backend for Istio rate limiting. Redis is so operationally cheap that Mindtickle stamps one out per service as infrastructure glue.

**The sentence to remember:** at Mindtickle, Redis is not "the cache" — it's the shared coordination substrate: cache + sessions + locks + idempotency + queues + rate limits, and each pattern has a phase in this course.

**The trap:** assuming all six patterns have the same failure tolerance. A cache miss is a slow request; a lost lock is a double-charged customer. Phase 3 exists because pattern ③ punishes sloppiness 1000x harder than pattern ①.

**In your codebase:** open `content-center-service/src/infrastructure/dispatch/packet/redis_packet.go` right now — one 106-line file that uses Redis as pub/sub (`PublishSyncDetailsToChannel`), lock manager (`AcquireLock`/`ReleaseLock` via redsync), KV store (`Set`/`Get`), and set store (`SMembers`). Four of the six patterns in one file.

---

## 🧪 Hands-on lab — the exercises that teach Phase 0

Setup (once):
```bash
cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d
docker exec redis-study redis-cli PING        # → PONG
```
All Go programs live under `phase00_why_redis/` and compile/run as-is (`go run ./phase00_why_redis/<name>`).

- [ ] **E1. Watch the single command stream.**
  - Run: `docker exec -it redis-study redis-cli MONITOR` in terminal 1; in terminal 2 run `docker exec redis-study redis-cli SET a 1`, `... INCR c`, `... HSET h f v`.
  - Expected: terminal 1 prints every command from every client, in execution order, one stream.
  - Teaches: there is exactly one serialized command sequence — MONITOR is you watching the event loop.

- [ ] **E2. Measure real GET latency.**
  - Run: `go run ./phase00_why_redis/latency_probe -n 10000`
  - Expected: p50 in the 200–500µs range, p99 under ~3ms, occasional multi-ms max.
  - Verify: in the `commandstats` output at the bottom, find `cmdstat_get` → `usec_per_call` ≈ 1µs or less.
  - Teaches: the ~350x gap between server execution time and client-observed latency is the network.

- [ ] **E3. Prove the round-trip cost model.**
  - Run: `go run ./phase00_why_redis/pipeline_vs_roundtrip -keys 500`
  - Expected: sequential ~100–300ms, pipelined ~1–10ms, speedup 30–224x.
  - Then: re-run with `-keys 50` and `-keys 5000`. Does the speedup grow or shrink with N? Why? (More round-trips amortized → grows.)
  - Teaches: cost = round-trips, and pipelining as the first-line fix.

- [ ] **E4. Feel head-of-line blocking (the Phase 0 centerpiece).**
  - Run: `go run ./phase00_why_redis/blocking_demo -sleep 2`
  - Expected: warm-up max GET latency well under 1ms; then one GET reported taking ~2.00s.
  - Teaches: one slow command on one connection stalls a different connection's microsecond read.

- [ ] **E5. Break it yourself: KEYS on a real keyspace.**
  - Seed: `docker exec redis-study redis-cli DEBUG POPULATE 5000000` (5M keys, ~30s).
  - Run: `docker exec redis-study redis-cli --latency` in terminal 1 (live latency meter). In terminal 2: `docker exec redis-study redis-cli KEYS 'key:*' > /dev/null`.
  - Expected: the latency meter's `max` jumps from ~0.5ms to hundreds of ms → seconds while KEYS scans.
  - Now the right way: `docker exec redis-study redis-cli --scan --pattern 'key:1234*' | head` — cursor-based, no stall (watch the meter stay flat).
  - Teaches: why KEYS is banned in prod and SCAN exists.

- [ ] **E6. Read the slow log like an on-call.**
  - Run: `docker exec redis-study redis-cli SLOWLOG GET 10`
  - Expected: your E5 `KEYS` command listed with its microsecond duration (anything >10ms lands here by default).
  - Verify: `docker exec redis-study redis-cli CONFIG GET slowlog-log-slower-than` → 10000 (µs).
  - Teaches: SLOWLOG is investigation step #1 for any "Redis is slow" page.

- [ ] **E7. Atomicity for free: the INCR race that isn't.**
  - Run: `for i in $(seq 1 50); do docker exec redis-study redis-cli INCR race:counter & done; wait; docker exec redis-study redis-cli GET race:counter`
  - Expected: exactly `50`. Every time. No lost updates despite 50 concurrent clients.
  - Contrast: sketch (on paper) the GET-add-SET version and where two clients interleave to lose an update.
  - Teaches: single-threaded execution = every command is a critical section — the foundation for Phase 3's locks and rate limiters.

- [ ] **E8. TTL discipline — the INCP-520 memorial exercise.**
  - Run: `docker exec redis-study redis-cli SET orphan:1 payload` (no TTL), then `docker exec redis-study redis-cli SET good:1 payload EX 300`.
  - Inspect: `TTL orphan:1` → -1 (never expires); `TTL good:1` → ~300.
  - Now: `docker exec redis-study redis-cli CONFIG GET maxmemory-policy` → `allkeys-lru` in this sandbox, but Mindtickle's clusters run AWS-default `volatile-lru` — which may evict ONLY keys with a TTL. Under `volatile-lru`, what happens as `orphan:*` keys accumulate to maxmemory? (Writes start failing OOM: nothing is evictable.)
  - Teaches: the no-TTL key is unevictable ballast under volatile-* policies — the exact mechanism behind the 4h37m LLM-gateway/Uploader outage.

- [ ] **E9. Data structures beyond strings, in 2 minutes.**
  - Run: `docker exec redis-study redis-cli HSET sess:u42 name raghu team coaching` then `HGETALL sess:u42`; `SADD sess:index u42 u43` then `SMEMBERS sess:index`; `ZADD jobs:inprogress 1720000000 job:1` then `ZRANGEBYSCORE jobs:inprogress -inf +inf`.
  - Expected: hash, set, and zset round-trips — you just reproduced mt-login-provider's session shape and course-qu-processors' job-marker shape.
  - Teaches: the structures in 0.1's table are one command away, not exotic.

- [ ] **E10. Break it: fill memory and watch eviction.**
  - Run: `docker exec redis-study redis-cli DEBUG POPULATE 3000000` a few times and watch `docker exec redis-study redis-cli INFO memory | grep -E 'used_memory_human|maxmemory_human'` and `INFO stats | grep evicted_keys`.
  - Expected: `used_memory` approaches the 256mb cap from docker-compose.yml, then `evicted_keys` starts climbing (allkeys-lru is evicting).
  - Teaches: what maxmemory pressure looks like in INFO — the metrics you'd alert on in Datadog.

Cleanup: `docker exec redis-study redis-cli FLUSHALL` (fine here — sandbox; now say out loud why you'd never run it on `common-redis-elasticcache`).

---

## 🏢 Mindtickle anchor — things to check in your codebase

1. **The four-generations-of-clients audit.** Run `grep -h "redis" ~/Desktop/project/mindtickle/{missions-processors,content-center-service,mt-login-provider,ai-module-creation}/go.mod`. You'll find go-redis **v6.15.9+incompatible**, **v8.2.3**, **v8.11.5**, and **v9.0.3** — four client generations in four repos (company-wide it's 17 repos on v9, 12 on v8, 14 with v7, plus redigo stragglers — a migration in flight). Open `missions-processors/clients/cacheClient/redisClient.go` (v6: no `context.Context` anywhere, no timeouts set, cache-miss detected via `strings.Contains(err.Error(), "nil")`) next to `ai-module-creation/src/infrastructure/redis/CacheClientImpl.go` (v9: ctx-first API, 2s Read/WriteTimeouts, `ReadOnly`+`RouteByLatency` replica routing, `SetNX`). Question to answer: what can go wrong in the v6 service that is *structurally impossible* in the v9 one when Redis hangs? (Hint: which one can cancel a stuck call when the gRPC deadline fires?)

2. **One file, four patterns.** Open `content-center-service/src/infrastructure/dispatch/packet/redis_packet.go` (also on GitLab `@mindtickle/content-center-service`). Find: pub/sub dispatch (`PublishSyncDetailsToChannel`), Redlock (`AcquireLock` → `redsync.NewMutex(key, WithExpiry(...))`), KV (`Set`/`Get`), sets (`SMembers`). Also note lines 21–25: it calls `ClusterSlots()` at startup and *auto-detects* whether to build a `NewClient` or `NewClusterClient` — because (per the deployment research) content-center-service is wired to BOTH a cluster-mode endpoint (`ELASTICCACHE_REDIS_HOST` from `gen-redis-elasticcache-enc-discovery-config`) and a non-cluster one (`NON_CLUSTER_ELASTICCACHE_REDIS_HOST` from the assessment-activity discovery config). Question: the Jan 2026 Equip incident happened because a client kept stale shard maps after a cluster-mode change — does this auto-detection run once at boot or per-connection, and what does that imply during a live topology change?

3. **A real cache-aside with a real TTL decision.** Open `missions-processors/processors/ai_roleplay_helper/ai_roleplay_helper.go:502-535` (`GetBuyerPersonaForCache`/`SetBuyerPersonaForCache`) and `missions-processors/constants/constants.go:160-161` (`STREAM_TTL = 10min`, `PREV_INSTR_TTL = 3 days`). Questions: why 3 days for buyer personas but 10 minutes for streams? What happens to a learner mid-roleplay if the persona key expires — correctness bug or latency blip? (Trace the miss path: it regenerates via LLM — cost, not correctness.)

4. **Sessions on Redis, but a different Redis.** Open `mt-login-provider/src/dao/redis_store.go`. Note: `redis.NewClient` (standalone, NOT ClusterClient) plus a `GetRedisStoreWithDBSelected` variant using numbered DBs (`SELECT`). Question: `SELECT` doesn't exist in cluster mode — so what does this file tell you about the *topology* of the Redis that auth runs on, before you've read a single Helm chart? Then verify your inference against `devops-helm-charts` (the prod-EU "simplified" set runs cluster-mode-DISABLED Redis 6.x per `CLUSTER_MODE_SIMPLIFICATION.md`; prod-US common cluster is cluster-mode-enabled 5.0.6). One codebase, both topologies — Phase 4 explains when each is right.

---

## ✅ Checkpoint 0 — answer in your own words

**Q1.** Your Datadog dashboard shows p99 latency spikes at the same minute on ce-uma, ce-content, integrations-selfserve, and mt-dashboard-api. Nothing deployed. The spikes last 3–8 seconds and recur irregularly. Using only Phase 0 concepts: what's your primary hypothesis, what's the FIRST Redis command you run to confirm it, and what are the three most likely culprit command shapes?

**Q2.** A teammate proposes: "Our roleplay grading flow makes 40 sequential Redis GETs per submission (one per rubric item). Redis is fast, each GET is only ~0.4ms, so that's 16ms — fine." Show the math on why this is 16ms of pure waste, name the two-word fix, and estimate the after. Then the senior follow-up: at what point does the *same* reasoning error become a 200ms problem in this codebase? (Hint: E3 with -keys 500.)

**Q3.** During the Nov 2023 incident, the LLM Gateway's no-TTL keys filled the shared cluster and took down Uploader. Walk the mechanism end-to-end: why didn't `volatile-lru` save the cluster? Why did a *different service* go down? And name two changes (one code, one architecture) that would each have prevented it.

**Q4.** A colleague says: "Redis is single-threaded, so it can't scale — we should move the settings cache to DynamoDB, which scales infinitely." Give the two-part senior answer: (a) what's wrong with "can't scale" (what do 100k ops/s and cluster mode each contribute?), and (b) what would actually break if the company-settings cache moved to DynamoDB — walk the three-layer invalidation design from 0.5 and identify which property DynamoDB can't replicate cheaply (hint: the scope-marker delete relies on cheap, instant, atomic single-key ops shared by all consumers).

**Q5.** Design question with Phase 0 tools only: Mindtickle needs "only one welcome email per new user, even if the signup event is delivered three times by Kafka." `ai-tutor` solved a similar problem (invitation emails) with a hand-rolled SETNX lock. Sketch the SET NX EX approach: exact command, what the TTL protects against, what happens if the process crashes *after* SETNX but *before* sending, and why this is 90% of the answer but Phase 3 exists for the other 10%.

**Q6.** You run `blocking_demo` against the study container and the fast reader stalls 2s, as expected. A skeptic says: "that's because both clients share one Go process — real services on separate pods wouldn't block each other." Design the two-pod experiment that refutes them, and explain *architecturally* why separate processes/pods/NICs change nothing.

(Model answers deliberately not included — write yours, then test against the lab. Q1: SLOWLOG GET; KEYS/big-collection-read/long-Lua. Q2: pipelining; ~1 RTT total. If you can't reconstruct the rest from the sections above, re-read the section, not a solution.)

---

## References & Further Learning

**Must-read/watch (in this order):**
- 📄 [How Redis Single-Threaded Architecture Works](https://oneuptime.com/blog/post/2026-03-31-redis-how-redis-single-threaded-architecture-works/view) — the cleanest modern writeup of the event loop, the "lock contention costs more than sequential execution" argument, and the 6.0 I/O-threads nuance (10 min). Read BEFORE the lab.
- 📄 [Redis Multi-Threaded Network Model — SoByte](https://www.sobyte.net/post/2022-03/redis-multi-threaded-network-model/) — the deep version: epoll, the exact evolution from pure single-thread to threaded I/O, with source-level diagrams (25 min). Read AFTER E1–E4, when you have measurements to hang it on.
- 📄 [Redis latency troubleshooting — official docs](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/) — the canonical checklist (intrinsic latency, slow commands, fork stalls, transparent huge pages). Skim now; bookmark forever — this is the page you'll open during a real incident.
- 📄 [Learn Nearly Everything About Redis Through An Incident — Alibaba Cloud](https://www.alibabacloud.com/blog/learn-nearly-everything-about-redis-through-an-incident_602055) — a real production incident unwound into architecture lessons; the same "one bad pattern, fleet-wide pain" shape as Mindtickle's INCP-520 (20 min). Read AFTER the lab.

**Deep dives (when Phase 0 feels solid):**
- 🎥 [antirez's YouTube channel](https://www.youtube.com/@antirez) — Salvatore Sanfilippo explaining his own design choices and low-level optimizations; primary source, no intermediary (browse; the Redis-internals videos are the ones).
- 🎙️ [Changelog #631 — Antirez returns to Redis](https://changelog.com/podcast/631) — the creator on why Redis is shaped the way it is, the fork years, and what he'd do differently (90 min, worth it).
- 📄 [Engineering Philosophy: antirez](https://blakecrosley.com/blog/engineering-philosophy-antirez) — short synthesis of the design values (small core, rich primitives, code for humans) that explain WHY the answers to "why doesn't Redis just…" are always "deliberately not" (8 min).
- 📄 [When Redis Fails Over But Your Service Doesn't](https://medium.com/@itsnarayan/when-redis-fails-over-but-your-service-doesnt-a-postmortem-from-the-trenches-42f69fe00047) — postmortem of the client-side-staleness failure class; the generic version of Mindtickle's Jan 2026 Equip incident (10 min).

**Comparison homework (for 0.4):**
- 📄 [ElastiCache Redis vs Memcached](https://jayendrapatil.com/aws-elasticache-redis-vs-memcached/) — terse feature matrix from the AWS-cert angle; 5 minutes, settles the Memcached question permanently.
- 📄 [When to use ElastiCache vs DynamoDB](https://www.dragonflydb.io/guides/when-to-use-elasticache-vs-dynamodb) — vendor-adjacent but honest on the volatile-vs-durable and RAM-vs-request-pricing trade (12 min). Read alongside the Nyx example from 0.5.

**Official docs (bookmark):**
- [redis.io/commands](https://redis.io/commands/) — command reference with per-command time complexity (the O(N) warnings ARE the production guidance).
- [Redis eviction policies](https://redis.io/docs/latest/develop/reference/eviction/) — the 8 policies; re-read before Phase 5.

**Book (one chapter for now):**
- 📚 *Redis in Action* (Josiah Carlson) — Chapters 1–2 only at this stage: the data-structure walk-through with real use cases. The rest maps to later phases.

---

## Cheatsheet — Phase 0

```
MENTAL MODEL
  one thread executes ALL commands, one at a time    → atomicity free, blocking free too
  cost of a call = network round-trip (~100-600µs)   → server work ≈ 1µs, irrelevant
  N sequential calls = N × RTT                       → pipeline: ~1 × RTT (measured 224x)
  one slow command = every client waits              → shared cluster: every SERVICE waits
  memory is one fixed pool (maxmemory)               → no-TTL keys under volatile-* = unevictable

INVESTIGATION COMMANDS (in incident order)
  redis-cli --latency                    live latency meter
  SLOWLOG GET 10                         commands that exceeded 10ms (default)
  INFO commandstats                      usec_per_call per command type
  INFO memory                            used_memory vs maxmemory
  INFO stats | grep evicted_keys         is eviction happening?
  redis-cli --bigkeys                    find the huge collections (Phase 5)
  CONFIG GET maxmemory-policy            what happens at the memory cliff

BANNED-IN-PROD → REPLACEMENT
  KEYS pattern          → SCAN (cursor)          FLUSHALL          → don't. just don't.
  SMEMBERS (huge set)   → SSCAN                  DEL (huge key)    → UNLINK
  HGETALL (huge hash)   → HSCAN                  long Lua loops    → break up / rethink

THE FIELD
  Memcached: blob cache only, multi-threaded, no structures/persistence/pubsub — MT uses: never
  DynamoDB:  durable KV, ms latency, request-priced — MT uses: as Couchbase successor, NOT vs Redis
  Redis:     µs coordination substrate — MT: cache+sessions+locks+dedup+queues+ratelimit

MINDTICKLE FACTS (verified July 2026)
  clients: go-redis v9 ×17 repos, v8 ×12, v7 ×14, v6 ×1 (assessment-activity) + redigo ×7
  clusters: ElastiCache via CFN-in-Helm; prod-US common = cluster-mode ON, redis 5.0.6,
            r6g.large; prod-EU "simplified" set = cluster-mode OFF, redis 6.x, t4g.small
  eviction: AWS default parameter groups → volatile-lru (no custom param group in IaC)
  settings cache: CE deletes Scope|COMPANY_<id> on write; mt-api-java-client CK|/SK| keys,
            TTL 3600s fallback; integrations-workflow separate 600s pure-TTL cache
  incidents to remember: INCP-520 (no-TTL keys, 4h37m), CE cacheable:false (30k/min→300/min
            after MR #5436), Equip cluster-mode upgrade (stale shard map), Wait(2,2s) replica assumption

THE ONE FORMULA
  latency_seen_by_caller ≈ RTT × round_trips + queue_delay_behind_slow_commands
  (server execution time doesn't appear because it's ~0 — until it isn't: that's Phase 5)
```

---

*Phase 0 complete. Say `next` for Phase 1 — Data Structures & Patterns (strings, hashes, lists, sets, sorted sets, streams — each anchored to the Mindtickle service that uses it).*

# Phase 6 — Redis in production: a review (the capstone)

You started this course using Redis without necessarily seeing it. Phase 0 reframed it as a single-threaded event loop; Phase 1 as a data-structure server; Phase 2 as a load multiplier; Phase 3 as a tool that can't guarantee correctness alone; Phase 4 as a topology with a failover story; Phase 5 as a system whose failures are always visible in advance. This phase does the thing the whole course was building toward: **it walks the actual Redis in your production and shows you that you now understand every touchpoint end to end** — not as isolated facts, but as one connected system with a coherent set of design choices, real incidents, and a clear improvement backlog.

Here's the shift this phase completes. Six phases ago, "we use Redis" was a vague fact. Now you can say precisely: *Mindtickle runs Redis on ElastiCache (cluster-mode varies by region, `volatile-lru`, RDB backups, no AOF), used by ~34 services for six jobs, through four coexisting go-redis generations, with cache-aside + delete-on-write as the house style, redsync and hand-rolled `SETNX` for efficiency locks, and a recurring failure family — the missing TTL — that has caused one confirmed outage and lurks in at least one live bug.* That sentence is the whole course, and by the end of this phase it should read as obvious.

This is also where you become useful in a way the codebase needs: the person who can look at any Redis usage and grade it. The final section is a senior scorecard — the prioritized list of what you'd actually fix, drawn from the real gaps Compass surfaced across all six phases.

Time: 3–5 days. Less new material, more synthesis — re-run the earlier labs against the mental model you now have, and build the capstone client that fixes the gaps you've found.

## What we cover in Phase 6:
```
┌──────────────────────────────────────────────────────────────────────────┐
│  6.1  The client landscape  — v6→v9 fragmentation, the shared wrapper,    │
│                               and what "good" looks like                  │
│  6.2  The six jobs, one map — cache/session/lock/dedup/queue/rate-limit   │
│                               with the canonical service for each         │
│  6.3  The company-settings  — the 3-layer crown-jewel cache, decoded      │
│       cache                                                               │
│  6.4  Nyx                    — DynamoDB + Redis done RIGHT (complementary) │
│  6.5  The CE bug, fully      — cache (P2) × hot endpoint (P5) in one       │
│                               incident, end to end                        │
│  6.6  The senior scorecard   — the prioritized fix-list across the fleet  │
│  6.7  Redis to Valkey        — why teams move, what differs, the RDB      │
│                               format blocker, six methods, real moves     │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 6.1 — The client landscape (four generations, no single wrapper)

**Why this matters:** the first thing you notice when you actually survey Mindtickle's Redis code is that there's no *one* way it's done — there are four go-redis generations and largely per-service clients. Knowing the landscape tells you what "good" looks like (so you can write it) and what the migration debt is (so you can reason about risk).

The generational spread (Compass-verified across the fleet):

```
┌──────────────────────────────────┬─────────┬────────────────────────────────┐
│ Client generation                │ #repos  │ What it means for the code     │
├──────────────────────────────────┼─────────┼────────────────────────────────┤
│ redis/go-redis/v9  (current)     │ ~17     │ ctx-first API; timeouts, replica│
│                                  │         │ routing available (the target) │
│ go-redis/redis/v8                │ ~12     │ ctx-first; widely deployed     │
│ go-redis/redis/v7  (legacy)      │ ~14     │ mostly transitive/indirect     │
│ go-redis/redis  v6 (+incompat)   │ 1       │ missions-processors: NO ctx,   │
│                                  │         │ NO timeouts — the worst gap    │
│ + gomodule/redigo (secondary)    │ ~7      │ dual-client stragglers         │
│ Java: Redisson/Jedis/Lettuce     │ ~12     │ cache-only; locking = QA only  │
└──────────────────────────────────┴─────────┴────────────────────────────────┘
```

The two ends of the quality spectrum, both real, side by side (you saw these in Phase 0.6):

```go
// WORST — missions-processors, go-redis v6: no context, no timeout
redisClient = redis.NewClusterClient(&redis.ClusterOptions{
    Addrs: []string{host + ":" + port}, MaxRetries: 3, MaxRedirects: 8,
})
output := client.redisClient.Get(key)   // ← no ctx: can't cancel; no ReadTimeout: hangs forever if Redis is slow

// BEST — ai-module-creation, go-redis v9: ctx, timeouts, replica routing
redisClient.clusterClient = goRedis.NewClusterClient(&goRedis.ClusterOptions{
    Addrs: []string{host + ":" + port}, MaxRetries: 3,
    ReadTimeout: 2*time.Second, WriteTimeout: 2*time.Second,  // ← fail fast (Phase 0/4)
    ReadOnly: true, RouteByLatency: true,                      // ← spread reads to replicas (Phase 4.2)
})
output := client.clusterClient.Get(ctx, key)   // ← ctx everywhere
```

The `ReadTimeout` gap in the v6 client is not cosmetic — recall Phase 0.3: if that Redis is blocked behind someone's `KEYS *` or a big-key `HGETALL`, the v6 `Get` **hangs indefinitely**, tying up goroutines with no way to cancel. The v9 client fails at 2s and the caller's context can cancel it. When you write new Redis code, be the v9 example.

Is there a shared wrapper to converge on? Partially: `platform-go-rest-client` exposes a `RedisClusterClient`, and `redis_cache_manager.go` layers a `DefaultTTL` on top of it (Phase 5). But — critically — the raw `RedisClusterClient.Set` *requires* the caller to pass a TTL and applies **no safe default**, so a caller passing `0` gets a no-TTL key (the INCP-520 footgun) across ~30 dependent repos. The higher-level manager supplies a `DefaultTTL`; the risk is anyone calling the raw client directly.

The capstone code (`phase06_production/prodclient`) is what "good" looks like as one object: v9 + timeouts, a `Set` that *refuses* a zero TTL, fail-open versioned cache-aside, pipelined `MGet`, and a safe lock — the client the fragmented v6/v8/v9 code *should* converge on.

**The sentence to remember:** Mindtickle runs four go-redis generations with no single wrapper — the v9 clients (ctx, timeouts, replica routing) are the target; the v6 `missions-processors` client (no ctx, no timeout → hangs on a slow Redis) is the worst debt; and the shared `RedisClusterClient` has no safe-default TTL, so the INCP-520 footgun is one `Set(…, 0)` away.

**The trap:** copying the nearest existing client when you add Redis to a service. Half of them are v6/v7 with gaps. Copy the v9 pattern (or the capstone `prodclient`), not the closest file.

**Try this now:**
```bash
go run ./phase06_production/prodclient
# The v9 wrapper: rejects no-TTL Set, fail-open cache-aside, MGet, safe lock.
```

---

## 6.2 — The six jobs, one map (everything you've learned, located)

**Why this matters:** this is the moment the course snaps into a single picture. Redis at Mindtickle does exactly six jobs, you've studied every one, and here they are with the canonical service and the phase that taught it — so any Redis code you open, you can immediately classify and reason about.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           REDIS AT MINDTICKLE — the complete map (~34 services)             │
│                                                                             │
│  JOB              PRIMITIVE          CANONICAL SERVICE        PHASE          │
│  ───────────────────────────────────────────────────────────────────────   │
│  ① Caching        GET/SET + TTL      integrations-selfserve   P2 (cache-    │
│    (cache-aside)  (delete-on-write)  (30m), ce-uma (1h),        aside +     │
│                                      content-center ListVoices  invalidate) │
│  ② Sessions       HASH + TTL         mt-login-provider (read)  P1 (hash)    │
│                                      app-gatekeeper (write)    P4 (no-TTL   │
│                                                                 crash gap)  │
│  ③ Locking        redsync / SET NX   content-center (redsync), P3 (efficiency│
│                                      ai-tutor/copilot (SETNX)   vs correct) │
│  ④ Idempotency    SET NX EX          ai-module-creation,       P1 (SETNX)   │
│                                      assessment-gpt            P3            │
│  ⑤ Queue/dispatch LIST / PUB-SUB     asset-hub-analytics (List)P1 (list),   │
│                                      content-center (pub/sub)  where guarantee│
│                                                                 ends         │
│  ⑥ Rate limiting  INCR+EXPIRE (Lua)  mt-dashboard-api (Lua),   P1 (ZSet/    │
│                   / LPUSH-LTRIM       integrations-selfserve    counter),   │
│                                      (legacy list)             P2 (fixed win)│
│                                                                             │
│  Structures in play: String, Hash, Set, List, ZSet (P1). No Streams/HLL/   │
│  Bitmap/Geo anywhere (Kafka owns streaming). Topology: ElastiCache,        │
│  cluster-mode varies, volatile-lru, RDB backup, no AOF (P4).               │
└─────────────────────────────────────────────────────────────────────────────┘
```

The synthesis insight — read the map as a *risk gradient*. The jobs are ordered by how much a failure hurts, and Mindtickle's implementations track that:
- **Caching (①)** — a failure is a slow request. The implementations are cache-aside + fail-open, which is exactly right; the gap is no stampede protection / no jitter (P2), tolerable because the blast radius is latency.
- **Sessions (②)** — a failure is a re-login. Hash + TTL, fine; the subtle gap is the `HMSET`+separate-`EXPIRE` no-TTL crash window (P4).
- **Locking (③)** — a failure *could* be a double-act, but every lock is deliberately an *efficiency* lock (dedup emails/links/sessions), so the plain-`DEL` and no-fencing gaps are tolerable — until someone copies the pattern to a correctness path (P3).
- **Idempotency (④)** — `SET NX EX` is the right primitive, correctly used.
- **Queue (⑤)** — List queues are loss-tolerant by design; durable work is on Kafka (P1).
- **Rate limiting (⑥)** — fixed-window Lua is cheap and correct-enough; the accurate ZSet sliding window exists as an upgrade path (P1/P2).

**The sentence to remember:** Redis at Mindtickle does exactly six jobs, each maps to a phase you've studied, and the implementations track a risk gradient — the low-blast-radius jobs (caching, sessions) carry tolerable gaps, and the higher-stakes ones (locking, idempotency) use the right primitives *because* they're deliberately scoped to efficiency, not correctness.

**The trap:** treating all six as equally forgiving. A cache miss and a lost lock are not the same severity. When you touch Redis code, first classify the job, then hold it to that job's bar.

**In your codebase:** pick any Redis call in a service you own and locate it on this map. Which of the six jobs is it? Which phase's rules apply? What's the blast radius if it fails?

---

## 6.3 — The company-settings cache (the crown jewel, decoded)

**Why this matters:** this is the most-read cache in the org and the reference implementation of the hardest thing in caching — invalidation. You studied the pattern in Phase 2; here you see it as the complete, three-layer production system, and understand every choice.

```
┌───────────────────────────────────────────────────────────────────────────┐
│  COMPANY-SETTINGS CACHE — 3 layers, delete-on-write + TTL fallback         │
│                                                                            │
│  ┌─── LAYER 1: content-engine (source of truth) ───────────────────────┐  │
│  │  updateSettings()  @CacheRetention({CacheScope.COMPANY})             │  │
│  │    on write → MTAction deletes Redis scope marker (Redis.bulkRemove) │  │
│  │    → INSTANT invalidation, synchronous, race-free (delete not update)│  │
│  └──────────────────────────┬───────────────────────────────────────────┘  │
│                             │ scope-key deletion visible to all readers    │
│  ┌─── LAYER 2: mt-api-java-client (shared lib — EVERY Java svc reads here)┐ │
│  │  keys: CK|<url>|hash , SK|<scope>|md5(url) ; TTL 3600s (REDIS_CACHE_  │  │
│  │  EXPIRY)                                                             │  │
│  │  sees deleted scope key → MISS → refetch fresh → 1h TTL = safety net │  │
│  └──────────────────────────┬───────────────────────────────────────────┘  │
│  ┌─── LAYER 3: integrations-workflow (Lambda) ─────────────────────────┐  │
│  │  own CompanySettingsCache, 600s (10min) PURE TTL, no listener       │  │
│  │  (+ in-process caches: content-engine 5min ConcurrentHashMap,       │  │
│  │   game_engine 10min Guava — hot-key mitigation, P5)                 │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  Invalidation = delete-on-write (instant) + TTL (bounds a missed delete). │
│  NO Kafka/pub-sub invalidation anywhere. Worst-case staleness = the TTL.  │
└───────────────────────────────────────────────────────────────────────────┘
```

Everything you learned shows up here:
- **Delete-on-write, not update** (P2.5): on a settings change, content-engine *deletes* the scope marker rather than recomputing the cached value — cheaper (no recompute on the write path) and race-free (no two-writer clobber).
- **TTL as the backstop** (P2.5): the 1h TTL in `mt-api-java-client` (and 10min in `integrations-workflow`) guarantees that even if a delete is missed — a Redis blip, a forgotten invalidation path — staleness is bounded. Self-healing.
- **The layering is deliberate** (P2/P5): the shorter-lived in-process caches (5–10min) absorb the hottest reads so they never reach Redis (hot-key mitigation, P5.4), while the Redis layer (1h) is the shared source of cached truth. Different TTLs at different layers, each sized to its role.
- **No jitter, all fixed TTLs** (P2.3/P5): the honest gap — synchronized expiry is unmitigated, and there's no stampede protection, so a mass expiry could stampede content-engine.

This is the design to reach for whenever you cache anything derived from a source of truth that changes: delete-on-write for freshness, TTL for safety, a short in-process layer for the hot path. It's also the pattern the CE incident (6.5) violated — proving its importance by its absence.

**The sentence to remember:** the company-settings cache is delete-on-write (instant, race-free) + a TTL backstop (bounds a missed delete) across three layers sized to their roles (in-process 5–10min for the hot path, Redis 1h for shared truth) — the reference pattern for caching anything derived from a mutable source.

**The trap:** adding a fourth consumer of company settings without wiring it into the scope-key invalidation. It'll be stale for its full TTL after every change. Either subscribe to the invalidation or accept (and document) the TTL staleness.

**In your codebase:** trace one settings write from `content-engine` `updateSettings()` → `@CacheRetention` → `Redis.bulkRemove(Scope|COMPANY_...)`, then a read through `mt-api-java-client` `CacheResponseUtils` (`CK|`/`SK|`, `REDIS_CACHE_EXPIRY`). Confirm: what makes a change visible instantly, and what bounds staleness if that fails?

---

## 6.4 — Nyx (DynamoDB + Redis, done right)

**Why this matters:** Phase 0.3 made the claim that "Redis vs DynamoDB" is usually a false choice — the right architecture is DynamoDB (durable) *plus* Redis (fast), each for what it's for. Nyx is the clean proof, and it's worth studying as the model for "when do I use both?"

Nyx is a standalone Go service (`qa-automation/nyx`, "Learning Site Management Service") that hands out a finite pool of test-tenant environments to concurrent CI runs. It uses *both* stores, each for its strength:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  NYX — DynamoDB and Redis, complementary not competing                   │
│                                                                          │
│  DynamoDB = SOURCE OF TRUTH (durable, versioned)                        │
│    - stores learning-site records (which site is claimed by which run)  │
│    - a `version` field for OPTIMISTIC CONCURRENCY: many parallel CI     │
│      runs try to claim the same site; the versioned conditional write   │
│      lets exactly one win, the rest retry (this is fencing at the DB!)  │
│                                                                          │
│  Redis = ATOMIC COUNTER (fast, single-purpose)                          │
│    - ONE key: nyxLastLsIdValue                                          │
│    - INCR hands out unique sequential IDs across concurrent inserts     │
│    - single-threaded INCR = atomic, race-free ID allocation (P0.1)      │
│                                                                          │
│  Durable versioned state where durability matters (DynamoDB);           │
│  atomic counting where atomicity matters (Redis INCR). That division    │
│  of labor IS the answer to "Redis vs DynamoDB": use BOTH, for what      │
│  each is best at.                                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

Two things to internalize from Nyx:
1. **Redis here is not a cache.** It's a coordination primitive (an atomic counter). This is the Phase 1 lesson — Redis is a data-structure server, and `INCR` on one key is a legitimate, high-value use that has nothing to do with caching.
2. **The correctness lives in DynamoDB, not Redis.** Notice where the *safety* is: the DynamoDB `version` field + conditional write is exactly the fencing-token idea from Phase 3.5 — the *resource* (DynamoDB) rejects a stale write. Nyx didn't try to make a Redis lock correct; it put the correctness at the durable resource and used Redis only for the cheap atomic bits. That's the senior pattern: **don't ask Redis to be correct; ask it to be fast, and put correctness where it belongs.**

**The sentence to remember:** Nyx uses DynamoDB for durable versioned state (with a `version` field = fencing at the resource) and Redis for one atomic `INCR` counter — the model answer to "Redis vs DynamoDB" is "both, each for its strength," with correctness at the durable store and speed at Redis.

**The trap:** trying to make Redis the durable, correct source of truth (a lock, a counter you can't lose). Nyx shows the right split — Redis fast, DynamoDB durable+correct. When you need both properties, use both stores.

**Verify:** in one service that uses both a database and Redis, find the code that enforces uniqueness or ownership. If only a Redis `SET NX` or `INCR` enforces it, a failover can break it, as Phase 4.2 shows.

---

## 6.5 — The CE bug, end to end (caching × hot endpoint in one incident)

**Why this matters:** this single incident is the whole course in miniature — it's a Phase 2 caching failure that manifested as a Phase 5 hot-endpoint problem, was invisible because of the Phase 2 "load multiplier" property, and was fixed by understanding cacheability. Walking it end to end with everything you now know is the ultimate synthesis exercise.

```
┌───────────────────────────────────────────────────────────────────────────┐
│  THE CE cacheable:false INCIDENT (MR !5436) — the course in one bug        │
│                                                                            │
│  ROOT (P2): RefMediaAPISerializer marked media NOT in                      │
│    SUCCESS/FAILED/PUBLISHABLE_PROCESSED_BUT_FULLCONVERT_FAILED as          │
│    cacheable:false. A Lambda callback to advance media OUT of              │
│    PUBLISHABLE_PROCESSED was commented out in 2022 (LEA-580) →            │
│    thumbnails stuck in that state ~8 YEARS → every GET /game = cacheable:false│
│                                                                            │
│  MECHANISM (P2 load-multiplier + P5 hot endpoint):                        │
│    cacheable:false → mt-api-java-client NEVER caches → EVERY request       │
│    hits content-engine → 300/min became 30,000/min (100x). Because a      │
│    cache is a load MULTIPLIER (amplification = 1/(1-hit_rate)), flipping   │
│    one boolean didn't add load — it multiplied it by the hit rate.        │
│                                                                            │
│  WHY INVISIBLE (P2/P5): no error, no related deploy — just "everything    │
│    slow." content-engine + read-service overloaded; downstream            │
│    (Allaboard, App-Gatekeeper, Game Engine) latency up. The tell was in   │
│    the metrics (call volume, CPU), not the logs.                          │
│                                                                            │
│  FIX (MR !5436, 2025-07-03): ImageVo + cropped + PUBLISHABLE_PROCESSED    │
│    → setCacheable(TRUE). ONE file. Results: 30k→300/min, content-engine   │
│    traffic −80%, GET /game p90 100ms→20ms, DynamoDB RCU 35k→7k/min,       │
│    downstream −60% latency.                                               │
└───────────────────────────────────────────────────────────────────────────┘
```

Count the phases in this one bug:
- **Phase 0**: the single thread means content-engine's overload cascaded — every slow request queued behind others.
- **Phase 2**: cache-aside's cacheability flag; the load-multiplier law (`1/(1-h)`); the fail-open corruption guards (`getSettingsMinimal`) that stopped it being *worse*.
- **Phase 5**: a hot endpoint concentrating load on one component; the fix was "cache it better" (the P5.4 hot-key mitigation); the metrics (call volume, RCU, p90) were where it was visible, not SLOWLOG.
- **The meta-lesson (all phases)**: it was a *usage* failure, not a Redis failure — a wrong boolean about cacheability, amplified 100x by the cache that was supposed to protect the system.

If you can narrate this incident using the vocabulary of all six phases — and explain why a 99%-hit-rate endpoint dropping to 0% cache produces exactly 100x load — you have completed the course's core objective.

**The sentence to remember:** the CE incident was a one-boolean caching bug (P2) that became a hot-endpoint overload (P5), invisible because a cache is a load multiplier (`1/(1-h)` → 100x), fixed by restoring cacheability — a *usage* failure, like every Mindtickle Redis incident, not a Redis failure.

**The trap:** treating `cacheable` (or any cache-key/TTL/invalidation decision) as a minor detail. This incident proves a single such decision is load-bearing for the entire system's throughput.

**Verify your understanding:** the fix dropped content-engine traffic 80% and p90 from 100ms to 20ms. Using the load-multiplier law, roughly what hit rate did restoring caching achieve, and why does an 80% traffic drop imply a hit rate around 80%? (If traffic fell to ~20% of the un-cached firehose, ~80% of requests are now served from cache → hit rate ≈ 80%, amplification back down from ∞-ish to ~5x of the cached baseline.)

---

## 6.6 — The senior scorecard (what you'd actually fix)

**Why this matters:** the final skill this course grants is *judgment* — the ability to look at the whole Redis surface and say, with priorities, what's worth fixing. This is the deliverable a staff engineer produces after a Redis audit. Here's yours, assembled from every gap Compass surfaced across the six phases, ordered by risk-adjusted value.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  THE MINDTICKLE REDIS FIX-LIST (prioritized)                                  │
│                                                                               │
│  P0 — do first (latent outage):                                              │
│  1. Audit no-TTL keys on volatile-lru clusters. Fix ai-tutor's 0*time.Hour   │
│     condensation bug (strips TTL → unevictable → INCP-520 pattern). Add a    │
│     safe-default TTL to platform-go-rest-client's raw Set (~30 repos exposed).│
│  2. Add owner tags to memory alerts (the alert FIRED in INCP-520 but was     │
│     missed). An alert with no owner is not an alert.                         │
│                                                                               │
│  P1 — do soon (correctness/latency risk):                                    │
│  3. Fence the "one email/link/charge" flows OR make them idempotent before   │
│     any of the SETNX+plain-DEL locks is copied to a correctness path (P3).   │
│  4. Fix the hand-rolled unlocks: random token + Lua compare-and-delete       │
│     (asset-hub-analytics is one line away — it already threads a token).     │
│  5. Make WAIT env-aware everywhere (the coe-ml pattern) — never hardcode     │
│     replica count (P4).                                                      │
│                                                                               │
│  P2 — hardening (resilience):                                                │
│  6. Add TTL jitter to bulk-warmed caches; add singleflight to the hottest    │
│     shared keys (company settings, GET /game) — no stampede protection today.│
│  7. Add hot-key / SLOWLOG alerting (monitoring is capacity-only today).      │
│  8. Retire the go-redis v6 client (missions-processors: no ctx, no timeout). │
│                                                                               │
│  P3 — hygiene (tech debt):                                                   │
│  9. Converge on one client wrapper (the prodclient shape) to stop the        │
│     v6/v7/v8/v9 drift and bake in the guardrails.                            │
│  10. Consider allkeys-lru on pure-cache clusters so a forgotten TTL can't    │
│      become unevictable ballast.                                             │
└──────────────────────────────────────────────────────────────────────────────┘
```

The judgment behind the ordering — this is the part that matters:
- **P0 is about the one failure that has already happened** (INCP-520, no-TTL + volatile-lru) and is *still live* (ai-tutor bug, unsafe raw `Set`). Highest value because it's a known, recurring, outage-grade pattern.
- **P1 is latent-but-severe**: the locks are fine *today* because they're efficiency locks, but the risk is a copy-paste onto a correctness path. Fixing the unlock safety and adding fencing/idempotency to the sensitive flows is cheap insurance against a future incident.
- **P2/P3 are resilience and hygiene**: real improvements, but the system works without them. A senior engineer does these when touching the area, not as a fire drill.

Notice what's *not* on the list: nothing about "Redis is too slow" or "we need a bigger cluster." Every real gap is a *usage* discipline — TTLs, unlock safety, alert ownership, topology assumptions. That is the final lesson of the entire course: **Redis will not fail you; your usage of it will, and every one of those failures is preventable with the discipline you now have.**

**What the list above does not cover: security and Kubernetes.** The fix-list has no security row and no Kubernetes row. A review of any Redis fleet needs both, because Redis 8.10.1 and 8.10.2 are both marked "Update urgency: SECURITY". Phase 4.8, securing Redis, teaches each mechanism below. This table is the part a review runs. Each rank follows the three questions above. Has it happened, what does a loss cost, and what does the fix cost?

| Check | Why it is on the list | How to check it | Rank |
|---|---|---|---|
| One ACL user per service. The `default` user is `off` or has a long random password. | Both engines create `default` as `+@all ~* &* on nopass`, and Valkey adds `alldbs`. One shared password gives every service `FLUSHALL` and `CONFIG`. | `ACL LIST` shows one user per service. Each starts with `-@all`, then adds only the categories and key prefixes that service needs. | P1 |
| Application users have no `@dangerous`, and no `@scripting` unless the service runs scripts. | The course research counted 8 Lua engine bugs among 29 Redis advisories published from 2023, grouped by title. Many need an authenticated user. | `ACL GETUSER <service>`. After a deploy, `ACL LOG` lists each denied command. | P1 |
| TLS on client links, and `tls-replication yes`. | `tls-port` is 0 by default, so `AUTH` crosses the network as plain text. `tls-replication` and `tls-cluster` default to `no` in both engines. | `CONFIG GET tls-*`. On ElastiCache, check encryption in transit. | P1 |
| Only cluster members can reach the cluster bus port. | The bus port is the data port plus 10000. Without `tls-cluster`, any host that reaches it can join the cluster, by the Redis 8.10.2 release note #15722. | Read the firewall or security group rule for that port. On Redis 8.10.2, `cluster-bus-port-protected-mode yes` makes a node refuse to start without `tls-cluster`. Valkey 9.1.2 has no such option. | P0 if other hosts can reach it, P1 if not |
| `protected-mode yes`, and no instance answers another host without a password. | With no config file, Redis listens on all interfaces, and only protected mode stops a remote client. Vendor reports on HeadCrab and RedisRaider describe attacks on open servers with no password. | `CONFIG GET protected-mode` and `CONFIG GET bind`. From another host, `redis-cli -h <host> PING` must fail with `NOAUTH` or `DENIED`. | P0 |
| An owner applies security releases on a schedule. | Redis 8.10.2 fixed #15673. Commands queued in `MULTI` could still reach keys whose ACL access was revoked before `EXEC`. The course research traced it to 8.4.0 to 8.10.1. | Compare `redis_version` in `INFO server` with the release notes. On ElastiCache node-based clusters, only critical updates apply in the maintenance window. The rest are self-service updates. | P1 |
| A Kubernetes liveness probe never calls Redis. | Harness's admin service probe checked every downstream service. When Redis requests timed out, Kubernetes restarted healthy pods. A restart adds load and fixes nothing in Redis. | Read the probe handler. Redis may sit in the readiness probe, which removes a pod from traffic, but not in the liveness probe, which restarts it. | P1 |

Turning on a password is a client change as well as a server change. GitHub's Container registry changed its Redis config to enforce authentication at 21:30 UTC on 2023-01-30. A connection string hard-coded in the production deployment file could not authenticate. Most GitHub Pages builds and Packages requests failed. GitHub reverted the change at 22:12, and Pages was healthy at 22:21 UTC. So test authenticated connections from every client before you enforce `AUTH`.

The Kubernetes docs give the rule for the last row. A liveness probe must "truly indicate unrecoverable application failure, for example a deadlock". A slow Redis is not such a failure. Harness's own fix says the probe "should not trigger restarts as the result of a downstream service".

**The sentence to remember:** the Mindtickle Redis fix-list is entirely *usage* discipline (TTLs, unlock safety, alert ownership, topology assumptions) — no "Redis is slow" items — because Redis doesn't fail, usage does, and you now have the judgment to grade and prioritize every gap.

**The trap:** finishing this course and reaching for Redis config/scaling knobs when something's wrong. The scorecard says the leverage is almost always in how the code *uses* Redis — start there.

**In your codebase:** pick one P0 or P1 item and scope the actual fix as an MR. (The ai-tutor `0*time.Hour` TTL strip is a genuine one-line fix with a real INCP-520-shaped risk — a perfect first Redis MR now that you understand exactly why it matters.)

---

## 6.7 — Moving a fleet from Redis to Valkey (what blocks the move, and how teams did it)

**Why this matters:** many teams now plan a move from Redis to Valkey. The first plan most people draw does not work from a current Redis. Valkey is the Linux Foundation fork of Redis 7.2.4. A team that adds a Valkey replica to a Redis 8 primary sees the first full sync fail. A team that copies keys with `DUMP` and `RESTORE` sees every `RESTORE` refused. This section explains why, gives the methods that work, and lists the commands your services can lose.

**The mental model.** Redis and Valkey share one code base up to Redis 7.2.4. After that point, each project added its own commands and its own snapshot format. A move needs two things. The target must read the data, and the target must run every command your services send. The source version decides the first. Your services decide the second.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Where the two engines split, and the RDB version each one writes           │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   Redis 7.2.4 ──┬──► Valkey 7.2 to 8.1    BSD-3              writes RDB 11 │
│   BSD-3, RDB 11 │    Valkey 9.0 to 9.1.2  BSD-3              writes RDB 80 │
│   fork point    │                                                          │
│                 └──► Redis 7.4            RSALv2 or SSPLv1   writes RDB 12 │
│                      Redis 8.0            AGPLv3 added       writes RDB 12 │
│                      Redis 8.10.2         AGPLv3 option      writes RDB 15 │
│                                                                            │
│   Valkey 9.1.2 reads 1 to 11 and 80. With rdb-version-check strict, the    │
│   default, it refuses 12 to 79, the range kept for Redis formats.          │
│   Redis 8.10.2 reads 1 to 15, so it refuses Valkey 9's 80.                 │
└────────────────────────────────────────────────────────────────────────────┘
```

**Why teams move.** The published cases give three reasons. They are the licence, the price on a managed service, and the end of support for old versions.

| Reason | What changed | Source |
|---|---|---|
| Licence | From Redis 7.4, the core moved from BSD-3 to RSALv2 and SSPLv1. Redis says these licences are not OSI open source. Redis 8 added AGPLv3 as another option. | Redis blog posts of 2024-03-20 and 2025-05-01. Verified in the course research. |
| Open governance | The Linux Foundation formed Valkey on 2024-03-28 from Redis 7.2.4, under BSD-3. AWS, Google Cloud, Oracle, Ericsson and Snap took part. | Linux Foundation press release. Verified in the course research. |
| Price on ElastiCache | Valkey costs 20% less than Redis OSS on node-based clusters and 33% less on Serverless. The Serverless minimum is 100 MB for Valkey and 1 GB for Redis OSS. | AWS ElastiCache pricing page, read on 2026-10-19. Verified. |
| Support end dates | ElastiCache runs Redis OSS up to 7.1 only. Standard support for Redis OSS 4 and 5 ended on 2026-01-31, and Extended Support charges started the next day. | ElastiCache engine versions and Extended Support pages. Verified in the course research. |

**What differs now: commands.** This section compares the command files of the two engines by name. Redis 8.10.2 has 459 commands and subcommands in `src/commands/`, and Valkey 9.1.2 has 425. They share 407. Verified: a script read every JSON file in both source trees on 2026-10-19. Module commands, such as vector sets, JSON and search, are not in those folders, so the comparison leaves them out.

| Redis 8.10.2 has, Valkey 9.1.2 lacks | Since |
|---|---|
| `SFLUSH` | 8.0.0 |
| `XACKDEL`, `XDELEX` | 8.2.0 |
| `DELEX`, `DIGEST`, `TRIMSLOTS`, `CLUSTER MIGRATION` | 8.4.0 |
| `HOTKEYS` and its 5 subcommands, `XCFGSET`, `XIDMPRECORD` | 8.6.0 to 8.6.2 |
| `INCREX`, `XNACK`, and the 18 commands of the new array type, `ARSET` to `ARSCAN` | 8.8.0 |
| `LMOVEM`, `BLMOVEM`, `SDIFFCARD`, `SUNIONCARD`, `HIMPORT` with 4 subcommands, `BACKUP` with 7 | 8.10.0 |

That is 52 names in total. The other direction has 18 names, and Redis 8.10.2 has none of them. Among them, Valkey 9.1.2 has `CLIENT CAPA` and `SCRIPT SHOW` from 8.0, and `COMMANDLOG` from 8.1. Four are `SENTINEL` subcommands that say PRIMARY where Redis says MASTER. Valkey keeps the MASTER names as well. From 9.0 it has `DELIFEQ` and the atomic slot migration commands, such as `CLUSTER MIGRATESLOTS`. From 9.1 it has `CLUSTERSCAN`.

Some commands exist in both engines, but Valkey added them later. The hash field expiry commands, such as `HEXPIRE`, `HGETEX` and `HSETEX`, arrived in Valkey 9.0.0. `HGETDEL` and `MSETEX` arrived in Valkey 9.1.0. So a move to Valkey 8.1 loses them, and a move to Valkey 9.1 keeps them. The target version matters as much as the target engine.

Two argument differences hide inside shared commands. `SET` takes `IFEQ` in both engines, from Redis 8.4.0 and Valkey 8.1.0. Only Redis takes `IFNE`, `IFDEQ` and `IFDNE`. `XREADGROUP` takes `CLAIM` from Redis 8.4.0 and `MAXCOUNT` and `MAXSIZE` from Redis 8.10.0. Valkey 9.1.2 takes none of the three. Verified from the argument lists in `set.json` and `xreadgroup.json` at both tags.

**What differs now: defaults and identity.** These changes need no code change to appear.

- Valkey 8.0 changed six defaults from `no` to `yes`: `lazyfree-lazy-eviction`, `lazyfree-lazy-expire`, `lazyfree-lazy-server-del`, `lazyfree-lazy-user-del`, `lazyfree-lazy-user-flush` and `replica-lazy-flush`. So `DEL` and `FLUSHALL` free memory in a background thread. A big-key `DEL` no longer stalls the main thread, and `used_memory` falls a little later. Verified: `valkey.conf` 9.1.2 lines 1448 to 1473, and `redis.conf` 8.10.2 lines 1369 to 1386.
- The default `repl-backlog-size` is 10mb in Valkey 9.1.2 and 1mb in Redis 8.10.2. Verified: `valkey.conf` 9.1.2 line 902, `redis.conf` 8.10.2 line 779.
- `INFO server` on Valkey 9.1.2 prints `redis_version:7.2.4`, then `server_name:valkey` and `valkey_version:9.1.2`. Valkey keeps the old field for clients that gate features on it. So a script that reads `redis_version` calls every Valkey "Redis 7.2.4". Verified: Valkey `src/version.h` and `src/server.c` lines 6120 to 6122.
- Valkey names itself in logs and in some error messages. The setting `extended-redis-compatibility`, default `no`, makes it report Redis, and its config comment says it will be removed. Valkey 8.0 also aborts a transaction on a nested `MULTI`. It returns errors for bad `BITCOUNT` arguments, where Redis returned zero. Verified in the course research from the Valkey 8.0 release notes.

Tools that parse the word "Redis" in errors or in `INFO` can break after the switch. This is inferred from the identity changes above. Run your monitoring against a Valkey test node to confirm it.

Here is the wrong check and the right one, from the lab program of this section:

```go
// WRONG: decide the engine from redis_version alone.
// Valkey 9.1.2 prints redis_version:7.2.4, so this says "redis 7.2.4".
return engine{"redis", parseVersion(reportedRedis)}, reportedRedis

// RIGHT: engine_gap/main.go:167 to 170, inside detectEngine.
if f["server_name"] == "valkey" || f["valkey_version"] != "" {
	return engine{"valkey", parseVersion(f["valkey_version"])}, reportedRedis
}
return engine{"redis", parseVersion(reportedRedis)}, reportedRedis
```

With the RIGHT branch removed, the self-test prints `[FAIL] a Valkey 9.1.2 INFO is read as valkey 9.1.2, not redis 7.2.4` and exits 1. That was run on 2026-10-19 as a mutation check.

**The RDB format blocker.** RDB is the snapshot format of Redis. The rule that decides every method below is a version number in each snapshot. The steps:

1. A new replica starts with a full sync. The primary sends it a whole RDB snapshot.
2. Redis 7.4 and 8.0 write RDB version 12. Redis 8.10.2 writes version 15, by `src/rdb.h` line 21.
3. Valkey 9.1.2 checks the version in `rdbIsVersionAccepted`, `src/rdb.c` lines 85 to 94. With `rdb-version-check strict`, the default, it refuses versions 12 to 79. The source comment says those numbers "are reserved for Redis non-compatible RDB formats".
4. The config comment for that setting says "This also applies to replication and the RESTORE command". So the Valkey replica logs `Can't handle RDB format version 15` and the sync fails. This step is inferred from `src/rdb.c` line 3198. No Valkey server ran in this course.
5. `DUMP` writes the RDB version into the last 10 bytes of its payload, by Redis `src/cluster.c` lines 123 to 143. Valkey's `RESTORE` runs the same version check and replies `DUMP payload version or checksum are wrong`, by Valkey `src/cluster.c` lines 172 and 253 to 254.
6. So three paths fail from Redis 7.4 or later. They are a Valkey replica, a copied RDB file, and a `DUMP` and `RESTORE` copy. A copy must read values and write them as ordinary commands.
7. The way back is closed as well. Valkey 9 writes version 80, and Redis 8.10.2 refuses any version above its own 15. A Valkey 9 file also starts with the magic string `VALKEY`, and Redis 8.10.2 refuses any file that does not start with `REDIS`, by its `src/rdb.c` line 4691. ElastiCache offers a roll back only from Valkey 7.2 to Redis OSS 7.1.

`rdb-version-check relaxed` makes Valkey try a foreign file. Its config comment says loading "is aborted if unknown information is encountered". Whether a Redis 8 file with only strings and hashes loads this way was not tested.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Three copy paths, one version check                                        │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   Redis 8.10 primary                               Valkey 9.1.2 node       │
│   ┌──────────────────┐  full sync: RDB 15         ┌──────────────────┐     │
│   │ REPLICAOF source ├───────────────────────────►│ refused          │     │
│   │ SAVE, copy file  ├───────────────────────────►│ refused          │     │
│   │ DUMP key         ├──► RESTORE, footer 15 ────►│ refused          │     │
│   │ GET, HGETALL ... ├──► SET, HSET ... ─────────►│ accepted         │     │
│   └──────────────────┘                            └──────────────────┘     │
│                                                                            │
│   The first three carry the RDB version. The last one carries commands.    │
│   The refusals are read from Valkey's rdb.c and cluster.c, not run here.   │
└────────────────────────────────────────────────────────────────────────────┘
```

The version number is easy to see on your own Redis. Lab E14 dumps one key and reads the footer, then sends the same bytes back with other version numbers:

```bash
go run ./phase06_production/engine_gap -part dump
# DUMP p6gap:src: 17 bytes, footer RDB version 15
# valkey strict accepts version 15: false (rdb-version-check strict, the default)
# valkey relaxed accepts version 15: true (best effort; loading stops at unknown data)
# so: replica cutover, RDB file copy and DUMP/RESTORE copy into valkey 9.1.2 are refused; use a copy that writes plain commands
# RESTORE with footer version 80 on this server (own 15): refused: ERR DUMP payload version or checksum are wrong; rule says accepted=false
# RESTORE with footer version 11 on this server (own 15): accepted; rule says accepted=true
```

Measured on 2026-10-19 on an x86_64 Homebrew Redis 8.10.1 under Rosetta 2 on an Apple M4 Pro. The server ran on port 6584 with no persistence. The two `valkey ... accepts` lines come from the program's copy of Valkey's rule. The two `RESTORE` lines are real replies from Redis. The program sets the CRC to zero, which Redis reads as "no checksum", so only the version is tested.

**The migration methods.** The source version picks the method, and the method sets the downtime and the roll back.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Which migration method can work                                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   What version does the source run?                                        │
│   │                                                                        │
│   ├─ Redis 7.2.x or older, or ElastiCache Redis OSS (7.1 at most)          │
│   │    ├─► replica cutover, on servers you run                             │
│   │    ├─► RDB file copy, with downtime for the copy                       │
│   │    └─► ElastiCache engine change, in place                             │
│   │                                                                        │
│   └─ Redis 7.4 or later                                                    │
│        ├─► blue/green with a copy tool that writes plain commands          │
│        └─► dual writes from the application, then move the reads           │
│                                                                            │
│   Any version: a proxy in front of each cluster hides the switch.          │
│   Any version: check the commands your services send against the target.   │
└────────────────────────────────────────────────────────────────────────────┘
```

*Method 1: replica cutover, on servers you run.* The steps come from the Valkey migration guide. They work only from Redis 7.2.x and older, because of the format check above.

1. Start a Valkey node.
2. Run `REPLICAOF <redis-ip> <redis-port>` on the Valkey node.
3. Run `INFO replication` on the Valkey node. Expected: `master_link_status:up`.
4. Point the applications to the Valkey node.
5. Stop the writes to Redis. The guide warns that `SHUTDOWN` can lose data while writes are active.
6. Shut down Redis.
7. Run `REPLICAOF NO ONE` on the Valkey node.

For a cluster, the guide adds Valkey nodes as replicas with `redis-cli --cluster add-node ... --cluster-replica`. It runs `CLUSTER FAILOVER` on each one, then removes the Redis nodes with `redis-cli --cluster del-node`. Airbnb used the same cutover to move from Redis on EC2 to ElastiCache, not to Valkey. It paused writes so that no data would be lost, compared replication offsets, promoted the replica and switched the endpoint. The report's author understood that AWS allowed `slaveof` for it as a special case. The report says the move had no downtime.

*Method 2: RDB file copy.* Disconnect the clients and record `INFO keyspace`. Run `SAVE`, copy the file to the Valkey data folder, and start Valkey with AOF off for the first start. Then compare the key count. The service is down for the whole copy, and the same format limit applies.

*Method 3: the ElastiCache engine change.* The steps come from the ElastiCache upgrade guide.

1. If the cache is a single node with cluster mode disabled, make it a replication group first.
2. If the cluster uses a custom parameter group, create a Valkey parameter group with the same static values.
3. Check the AWS CLI version. The minimum is 1.35.2 for v1 and 2.18.2 for v2.
4. Run the engine change:

```bash
aws elasticache modify-replication-group \
  --replication-group-id myReplGroup \
  --engine valkey \
  --engine-version 9.0 \
  --cache-parameter-group-name myParamGroup
```

5. Watch the cluster until its status is `available`.

AWS says the endpoint DNS name stays the same, and "the underlying node IP addresses will change". From Redis OSS 5.0.6 or later, reads work the whole time. Writes stop only "during the failover operation which lasts a few seconds". From older versions, expect "a failover time of 30 to 60 seconds during the DNS propagation". By the MaiCoin post, ElastiCache adds Valkey nodes that replicate from the Redis primaries. Then it fails over, updates DNS and deletes the old nodes. ElastiCache runs Redis OSS 7.1 at most, so this replication never meets the format check. A client that caches resolved IP addresses must reconnect after the change. This is inferred from the changed IPs. Watch connection errors in a test upgrade to confirm it.

*Method 4: blue/green with a copy tool.* MaiCoin chose this method over the in-place change. It says the in-place change "provided no live validation window and lacked the ability to roll back".

1. Create a Valkey cluster with the same configuration.
2. Start an EC2 instance in the same VPC for the copy tool.
3. Ask the ElastiCache team to turn on PSYNC for both clusters.
4. Run RedisShake: a full sync by `SCAN`, then live changes from keyspace notifications. MaiCoin set `rdb_restore_command_behavior=rewrite`, and TTLs were kept.
5. Compare key counts and sample values with a script.
6. Move traffic step by step. Keep the old cluster for a roll back.

The cost is two clusters for the length of the move. Check how your tool writes each key. A tool that sends `RESTORE` meets the same version check as a replica. The RedisShake README lists Redis 2.8 to 8.4.x and Valkey 8.x to 9.x as supported. So a Redis 8.10 source is outside its stated range. How RedisShake writes keys into Valkey was not checked.

*Method 5: dual writes from the application.* Amazon Ads used this method. Its cache client wrote every key to both engines, and a config service moved the reads.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Dual writes, as Amazon Ads ran them (from the AWS post)                    │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   phase 1   writes ──► Redis + Valkey   reads ──► Redis                    │
│             each write has a 100 ms timeout; one failure blocks no other   │
│   phase 2   writes ──► Redis + Valkey   reads ──► part Redis, part Valkey  │
│             AppConfig moves one read method at a time                      │
│   phase 3   writes ──► Valkey           reads ──► Valkey                   │
│             Redis clusters removed after Valkey carries full load          │
│                                                                            │
│   A key written only before phase 1 exists only in Redis. For a cache,     │
│   one full TTL of dual writes fills Valkey. Inferred, not in the post.     │
└────────────────────────────────────────────────────────────────────────────┘
```

Dual writes copy no snapshot, so they work from any Redis version. This is inferred from the method. The price is the client code, and two clusters that can disagree while a write fails on one side.

*Method 6: a proxy in front of every cluster.* Snap put a RESP proxy in front of each cache cluster. RESP is the Redis wire protocol. Applications talked only to the proxy, so no application team had to know about the engine change.

**What changes in the clients.** Most clients keep working. The Valkey clients page says clients that support Redis OSS 7.2 work with Valkey 7.2 and later. Valkey also has its own client family, Valkey GLIDE. Five things still need a check:

- **Commands the target lacks.** Replace `INCREX` with the Lua script of `INCR` and `EXPIRE` from Phase 1. Replace `DELEX ... IFEQ` with `DELIFEQ` on Valkey 9.0 and later, or with the Lua compare-and-delete from Phase 3.
- **Feature gates.** A client or a script that reads `redis_version` sees 7.2.4 on every Valkey. Read `server_name` and `valkey_version` instead.
- **Changed node IPs.** After an ElastiCache engine change, a client must resolve the endpoint again.
- **Behaviour that a fork had and Valkey lacks.** Snap's KeyDB ran `MGET` across slots. Valkey does not, and Snap found that gap only after the move.
- **Scripts.** `EVALSHA` works only after the script is loaded on the new node. A client must handle `NOSCRIPT` with `SCRIPT LOAD` or `EVAL`. This is inferred from how the script cache works, because a copy by commands does not copy it.

**Published moves, with their numbers.** Most of these posts come from a company that sells the service. So each row names its source.

| Company and source | Scale | Method | Result | Problems |
|---|---|---|---|---|
| Amazon Ads. AWS Database Blog, 2025-11-25. Vendor: AWS. | Tens of millions of reads per second at peak. Its cache service scales a cluster across 500 nodes. | Dual writes with a 100 ms timeout per write, reads moved one method at a time, new Valkey clusters on Graviton nodes. | Over 45% lower infrastructure cost and 12% more throughput, with no downtime. The saving includes the move to Graviton. | The post says dual-write consistency needs close watching. |
| A travel technology company, not named. AWS Database Blog, 2026-04-01. Vendor: AWS. | Millions of daily bookings. No node counts. | ElastiCache engine change in place. Backups were taken first, in case a restore was needed. | 20% lower cluster cost, no downtime. | "a short period of slightly elevated latencies observed in some applications". |
| MaiCoin, a cryptocurrency exchange in Taiwan. AWS Database Blog, 2026-01-22, written with MaiCoin. | No numbers. | Blue/green with RedisShake. | The post states 20% to 33% lower cost, the list price gap. | Two clusters during the move. |
| Aiven. Aiven blog, 2025-09-23. Vendor: Aiven. | About 15,000 Redis services in August 2024. | About 4,000 moved by customers with one button. About 11,000 moved in maintenance windows. | The whole fleet moved. | Not stated. |
| Snap. Momento's summary of a Snap talk, 2026-05-21. Momento sells a competing cache. | All of Snap's caching ran on KeyDB, a Redis 6.2 fork. | RESP proxy, about 30 caches a week, lowest criticality first. | 70% to 80% of workloads on Valkey at the time of the talk. | Valkey 8.2 RC crashed at 9 to 10k QPS from new TLS offload code, so Snap went back to 8.0.2. A high-memory cache can repeat its full sync without end if the replication buffer fills first. |
| Leboncoin. Its own engineering blog, 2026-06-24. | The earlier course research read a little over 100 instances on Redis 7.2.4, moved in waves of 5, about 20 minutes each. | ElastiCache engine change. | No application code changes. | One missed Terraform apply lost part of one instance's config. |
| Airbnb. Classmethod's report of an AWS re:Invent 2018 talk. Not a Valkey move. | No numbers. | Replica cutover from EC2 Redis to ElastiCache. | No downtime. Writes were paused to avoid data loss. | The report's author understood that AWS allowed `slaveof` as a special case. |

Not checked: every Leboncoin number. Medium blocked each fetch of the post in this session. Those facts rest on an earlier read of its feed.

The failure to learn from is Snap's. A release candidate crashed at 9 to 10k QPS, from new TLS offload code. Snap's answer was a stable release, a separate test for each class of cache, and the least critical caches first. The length of a fleet move follows from its pace. At Snap's pace of about 30 caches a week, 100 caches take 100 / 30 = about 3.3 weeks.

**The sentence to remember:** the source's RDB version picks the method. Redis 7.2 and older can replicate into Valkey. Redis 7.4 and later need a copy by commands, or dual writes.

**The trap:** planning a Valkey replica of a Redis 8 primary. The first full sync fails, and a `DUMP` and `RESTORE` copy fails for the same reason. The move window is then spent, and the team needs a second plan. "Drop-in replacement" holds only for Redis OSS 7.2 and older.

**Try this now:**
```bash
redis-cli -p 6584 INFO server | grep -E "redis_version|server_name|valkey_version"
go run ./phase06_production/engine_gap -commandstats
```
A Redis server prints only `redis_version`. Then look for `MISSING` rows: each one is a command your services send that the target does not have.

---

## 🧪 Hands-on lab — the capstone exercises

Setup:
```bash
cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d && docker exec redis-study redis-cli PING   # → PONG
```

- [ ] **E1. Run the capstone client.**
  - Run: `go run ./phase06_production/prodclient`
  - Expected: no-TTL Set rejected; cache-aside miss→hit (1 source load); MGet one round-trip; safe WithLock.
  - Teaches: every phase's lesson as one production-grade object.

- [ ] **E2. Prove the no-TTL guardrail.**
  - Read `prodclient`'s `Set`: it returns `ErrNoTTL` on `ttl <= 0`. Question: which two real Mindtickle bugs would this have prevented? (INCP-520's LLM Gateway keys; ai-tutor's `0*time.Hour`.)
  - Teaches: a guardrail beats a code-review catch.

- [ ] **E3. Classify five real Redis calls.**
  - Open five Redis call sites across services you can reach (or the anchors from Phases 1–5). For each, name: the job (of the six), the structure, the phase, the blast radius if it fails.
  - Teaches: the 6.2 map as a working tool.

- [ ] **E4. Trace the company-settings invalidation.**
  - Follow `content-engine` `updateSettings` → scope-key delete → `mt-api-java-client` read. Draw the delete-on-write + TTL-fallback flow from memory, then check it against the code.
  - Teaches: the reference invalidation design (6.3).

- [ ] **E5. Reproduce the CE load-multiplier math.**
  - Compute: for hit rates 0.9, 0.99, 0.999, what's the amplification `1/(1-h)` when caching breaks? Then: the CE fix dropped traffic 80% — infer the restored hit rate.
  - Teaches: why one boolean = 100x (6.5).

- [ ] **E6. (Break it) Simulate the ai-tutor no-TTL bug.**
  - Run: `docker exec redis-study redis-cli SET sess:mem:u1 data EX 86400` (correct), then `docker exec redis-study redis-cli SET sess:mem:u1 data` (the condensation path — strips TTL), then `docker exec redis-study redis-cli TTL sess:mem:u1` (→ -1, permanent).
  - Teaches: how a re-`SET` without TTL creates unevictable ballast.

- [ ] **E7. Audit a cluster for no-TTL keys.**
  - Run: seed a mix, then `SCAN` and `TTL` each; count `-1`s. (In prod: `redis-cli --scan | while read k; do echo "$(redis-cli TTL "$k") $k"; done | grep '^-1'` — sample, don't run on a huge keyspace.)
  - Teaches: how you'd actually find INCP-520 risk before it fills the cluster.

- [ ] **E8. Build your own fix.**
  - Take the P0 ai-tutor bug: write the corrected `Set` call (preserve the 24h TTL on the condensation path). Compare to `prodclient`'s mandatory-TTL `Set`.
  - Teaches: the actual fix, in code.

- [ ] **E9. The full-course drill (no hints).**
  - Given: "company-settings reads spike content-engine latency every hour on the hour after a deploy." Diagnose using all six phases: what's happening, which phase's concept explains it, and the fix. (Hint: synchronized TTL expiry + no jitter + no stampede protection.)
  - Teaches: cross-phase synthesis on a novel scenario.

- [ ] **E10. Write the scorecard for one service.**
  - Pick one service you own that uses Redis. Produce its mini fix-list (P0–P3) using 6.6's framework: what are its no-TTL risks, lock safety, N+1s, client version, monitoring?
  - Teaches: the deliverable — Redis judgment applied to real code.

**Exercises for 6.7.** E11 to E14 were run on 2026-10-19 against a throwaway `redis-server` 8.10.1 on port 6584. It was an x86_64 Homebrew build under Rosetta 2 on an Apple M4 Pro, with no persistence. These exercises do not use the Docker container above. Start the server first:

```bash
mkdir -p /tmp/p6gap
redis-server --port 6584 --dir /tmp/p6gap --save '' --appendonly no --daemonize yes
redis-cli -p 6584 PING   # → PONG
```

- [ ] **E11 (offline).** Run the self-test of the engine gap tool.
  - Run: `go run ./phase06_production/engine_gap -self-test`
  - Expected: 20 lines that start with `[ok  ]`, then `all checks passed`.
  - If it fails: the failed line names the rule that broke. Compare the tables at the top of `main.go` with the two command folders.
  - Teaches: the command gap, the engine check and the RDB version gate, as rules a test can hold (6.7).

- [ ] **E12 (live).** List the commands a target engine lacks.
  - Run: `go run ./phase06_production/engine_gap -addr localhost:6584`
  - Expected: `source: redis 8.10.1 (INFO redis_version:8.10.1)`, then `4 of 13 commands are missing on valkey 9.1.2`. The four are `INCREX`, `DELEX`, `HOTKEYS GET` and `LMOVEM`. `VADD` is reported as `module vectorset`, and `SET` and `XREADGROUP` print an argument note.
  - Run: `go run ./phase06_production/engine_gap -addr localhost:6584 -target valkey-8.1.0`
  - Expected: `6 of 13 commands are missing on valkey 8.1.0`. `HEXPIRE` and `MSETEX` join the list, as `Valkey added it in 9.0.0` and `Valkey added it in 9.1.0`.
  - If it fails: `cannot read INFO server` means no server answers on port 6584.
  - Teaches: the target version decides the gap as much as the target engine (6.7).

- [ ] **E13 (live).** Use the commands the server has really seen.
  - Run: `redis-cli -p 6584 CONFIG RESETSTAT`, then `redis-cli -p 6584 SET p6gap:a 1 EX 60`, `redis-cli -p 6584 GET p6gap:a`, `redis-cli -p 6584 INCREX p6gap:n BYINT 1 EX 60`, `redis-cli -p 6584 HSET p6gap:h f v`, `redis-cli -p 6584 DELEX p6gap:a IFEQ 1` and `redis-cli -p 6584 DEL p6gap:n p6gap:h`.
  - Run: `go run ./phase06_production/engine_gap -commandstats`
  - Expected: `commands seen by INFO commandstats since the last restart or CONFIG RESETSTAT: 10`, then `2 of 10 commands are missing on valkey 9.1.2`. The two are `DELEX` and `INCREX`. The list also holds `CONFIG RESETSTAT`, which you sent, and `CLIENT SETINFO`, `HELLO` and `INFO`, which the tool itself sent.
  - If it fails: a list with only `INFO` and `HELLO` means the six commands went to another server.
  - Teaches: `INFO commandstats` is the inventory of what the services send. It resets on restart and on `CONFIG RESETSTAT`. So read it on a server that has run through a full business cycle (6.7).

- [ ] **E14 (break-it, live).** Make `RESTORE` refuse a payload because of its version number.
  - Run: `go run ./phase06_production/engine_gap -part dump`
  - Expected: `DUMP p6gap:src: 17 bytes, footer RDB version 15`, then `valkey strict accepts version 15: false`. Then `RESTORE with footer version 80 on this server (own 15): refused: ERR DUMP payload version or checksum are wrong`, and `RESTORE with footer version 11 on this server (own 15): accepted`.
  - If it fails: a footer version other than 15 means a different Redis build. Read its `src/rdb.h`.
  - Teaches: every copy path that carries an RDB payload meets the version gate. Redis 8.10 refuses Valkey 9's version 80, measured here. Valkey 9.1.2 refuses Redis 8.10's version 15, read from its source and not run (6.7).

When you finish, stop the server with `redis-cli -p 6584 SHUTDOWN NOSAVE`.

---

## 🏢 Codebase anchor — the capstone checks

1. **The client spectrum.** Open `missions-processors/clients/cacheClient/redisClient.go` (v6, no ctx/timeout) and `ai-module-creation/src/infrastructure/redis/CacheClientImpl.go` (v9, ctx/timeouts/ReadOnly) side by side. Then open `phase06_production/prodclient/main.go`. Question: what does the capstone do that neither production client fully does? (Mandatory TTL + fail-open cache-aside + safe lock in one place.)

2. **The crown-jewel cache.** `content-engine` `updateSettings`/`@CacheRetention` + `mt-api-java-client` `CacheResponseUtils` (`CK|`/`SK|`, `REDIS_CACHE_EXPIRY`). Question: this is the org's best invalidation design — what single improvement (from 6.6) would make it more resilient? (TTL jitter + singleflight on the hot settings key.)

3. **Nyx.** `qa-automation/nyx` — the `RedisClient.go` `nyxLastLsIdValue` counter + the DynamoDB `version` field. Question: where does *correctness* live in Nyx, and why is that the right place? (In DynamoDB's versioned conditional write — the resource enforces it, exactly like a fencing token; Redis only does the cheap atomic counting.)

4. **The scorecard's P0.** `ai-tutor/src/usecase/memory/memoryUsecaseImpl.go` — the condensation path's `0*time.Hour`. Question: write the one-line fix and explain, using Phases 4 and 5, exactly what outage it prevents. (Preserve the 24h TTL → key stays evictable under volatile-lru → can't become INCP-520 ballast.)

5. **The engine gap tool.** Open `phase06_production/engine_gap/main.go:158`. This is `detectEngine`. Why does it read `server_name` before `redis_version`? What would it call a Valkey 9.1.2 server without line 167? (Redis 7.2.4, because Valkey prints `redis_version:7.2.4`.) Then read `lacks` at line 182. A new subcommand `HOTKEYS NEWSUB` is not in the table. Why does `lacks` still call it missing?

6. **In any repo you own.** Run `grep -rn "redis_version" <your repo>/`. Each hit is a feature gate that reads 7.2.4 on every Valkey. Then run `grep -rniE "INCREX|DELEX|HOTKEYS|LMOVEM|XACKDEL|DIGEST" <your repo>/`. Each hit is a command that Valkey 9.1.2 does not have.

---

## ✅ Checkpoint 6 — the capstone questions

1. In four sentences, describe Mindtickle's entire Redis architecture to a new hire: the platform + topology, the six jobs, the house caching style, and the one recurring failure family. (This is the sentence-that-is-the-course from the intro — write it in your own words.)

2. Walk the CE `cacheable:false` incident end to end using the vocabulary of all six phases. Explain precisely why a 99%-hit-rate endpoint dropping to 0% cache produces ~100x load (the load-multiplier law), why it was invisible, and why the one-line fix worked. Which phases' concepts each appear?

3. A new service needs to (a) cache user profiles, (b) dedup a "send welcome email" action, and (c) rate-limit an API. For each, specify: the structure, the pattern, the TTL, the failure mode you're accepting, and which existing Mindtickle service you'd copy. Then: which of the three, if implemented with the existing `SETNX`+plain-`DEL` lock, would you *block in review* and why?

4. Explain Nyx's DynamoDB+Redis split to someone who says "just use one store." Why is DynamoDB the source of truth, why is Redis the counter, and where is correctness enforced? Then generalize: give the rule for when a system should use *both* a durable store and Redis, and where correctness must live.

5. You're handed the company-settings cache and asked to "make settings changes visible instantly everywhere." Given the 3-layer design (6.3), explain which layer is already instant, which is TTL-bounded (and by how long), and exactly what you'd change to make the slow layer instant — including the cost and the stampede risk you'd introduce.

6. Produce the P0 items of the Redis fix-list from memory, and for each: the specific service/file, the failure it prevents, and which past incident (or live bug) motivates it. Then defend the ordering — why is the no-TTL audit P0 and the client-convergence P3?

7. The course's thesis is "Redis doesn't fail, usage does." Argue it using three different Mindtickle incidents/bugs (INCP-520, CE !5436, and the ai-tutor no-TTL bug), showing that each was a usage-discipline failure with a preventable root cause. Then give the one habit (from any phase) that would have caught the most of them.

8. **Moving engines.** Your fleet runs 40 Redis 8.10 primaries on servers you run. A teammate plans to add a Valkey 9.1 replica to each primary. It syncs, gets promoted, and DNS moves to it. `INFO commandstats` on one primary shows `INCREX`, `DELEX`, `HSET` and `EVALSHA`. (a) Walk through what happens at the first sync. (b) Which of the four commands fail after the switch, and what replaces each? (c) Design a plan that works, and give its length at 30 primaries a week. Name two security checks each new cluster must pass before it takes traffic.

<details>
<summary>Answer sketches</summary>

1. About 34 services share managed Redis clusters. The one reviewed uses `volatile-lru`, RDB backups and no AOF. Redis does six jobs: cache, session, lock, idempotency key, queue and rate limit. The house style is cache-aside with delete-on-write and a TTL backstop. The recurring failure is the missing TTL. It filled memory under `volatile-lru` once, and one rewrite path still strips a TTL.
2. The source carries traffic × (1 − h). At h = 0.99 that is 1% of the traffic. At h = 0 it is 100%, so the load grows 1 / 0.01 = 100 times. Nothing failed, so nothing was logged. Requests only became slower, and the signal was call volume and CPU. Marking the responses cacheable again restored h near 0.99. The load fell from about 30,000 to about 300 calls per minute. Phases 0, 2 and 5 each explain one part.
3. Profiles: a string or hash, cache-aside, delete-on-write and a TTL with jitter. You accept a slower request. Welcome email: `SET NX EX` as an idempotency key, with a TTL as long as retries can happen. A lost key can send a second email. Rate limit: `INCR` plus `EXPIRE` in one Lua script, with the window as the TTL. On Redis 8.8 and later `INCREX` does both in one command, but Valkey has no `INCREX`. Block the email path in review if "once only" matters to the business. A plain `DEL` can remove another holder's key, and a failover can lose it.
4. The durable store holds who owns each environment, and its conditional write lets one run win. Redis gives out IDs fast and atomically on one node. Correctness lives in the durable store, because a Redis failover can repeat an ID or lose a lock. The rule: use Redis for the fast parts that can be lost or repeated. Enforce correctness with a conditional write where the data lives.
5. The Redis layer is instant when the delete works, and bounded by 1 hour when the delete is lost. The in-process layers are stale for up to 5 and 10 minutes after every change. To make them instant, delete in Redis first and then publish the key on a purge channel. A purge lost during a disconnect leaves that server stale for its TTL. So flush the local cache on every reconnect. Every server then misses at once after a change, so add singleflight to protect the source.
6. P0 has two numbered items with four actions. Audit the keys with no TTL. Fix the zero-TTL rewrite. Give the shared raw `Set` a safe default TTL, and give the memory alerts an owner. They prevent the outage that has already happened once. The audit is P0 because it has happened and can happen again. It also stops writes for every service on the cluster. Client convergence is P3, because version drift causes harm only together with another failure.
7. Three cases support it. The missing TTL filled the shared cluster. The cacheable flag sent 100 times the load to the source. The rewrite path strips a TTL. Each had a preventable cause in the code. A guard in the shared client would have caught two of them. As a general rule, the thesis goes too far. Asynchronous replication can lose acknowledged writes in a failover with correct use, as Phase 4.2 shows. A review checks both the usage and the guarantees.
8. (a) The replica asks for a full sync, and the primary sends an RDB of version 15. Valkey's default `rdb-version-check strict` refuses 12 to 79. So the replica logs `Can't handle RDB format version 15`, and the sync fails. This is read from the Valkey source and not run. (b) `INCREX`, since Redis 8.8, and `DELEX`, since Redis 8.4, are missing on Valkey 9.1.2. Replace `INCREX` with the `INCR` and `EXPIRE` Lua script, and `DELEX ... IFEQ` with `DELIFEQ`, which Valkey has since 9.0. `HSET` and `EVALSHA` exist, but `EVALSHA` answers `NOSCRIPT` until the script is loaded on the new node. (c) For caches, run dual writes for one full TTL. Then move the reads in waves, least critical first, and keep the Redis primaries for a roll back. For data that must not be lost, use a copy tool that writes plain commands. Compare key counts before the switch. 40 / 30 = about 1.3 weeks of switches. Security: each service has its own ACL user and `default` is off. In cluster mode, the bus port is closed to other hosts, because Valkey 9.1.2 has no `cluster-bus-port-protected-mode`.

</details>

---

## References & Further Learning

**Capstone reading (synthesis over new material):**
- 📄 [Redis best practices — official docs](https://redis.io/docs/latest/develop/) — re-read the top-level guide now that every section is familiar; it'll read as "yes, I know why." (30 min)
- 📄 [AWS ElastiCache best practices](https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/BestPractices.html) — the operational checklist for the platform Mindtickle runs; map each item to a phase. (20 min)
- 📚 *Designing Data-Intensive Applications* (Kleppmann) — Ch. 1 (reliability/scalability/maintainability), now that you've seen all three tested by real incidents. The capstone framing for everything.
- 📄 [The six earlier phases] — re-read your own Phase 0 cheatsheet last. If it now reads as obvious, the course worked.

**The Mindtickle-specific canon (your internal references):**
- `content-center-service/src/domain/externalContent/core/ExternalContentFacade.go` — the reference cache-aside.
- `mt-api-java-client` `CacheResponseUtils` + `content-engine` `@CacheRetention` — the reference invalidation.
- `content-center-service/.../redis_packet.go` (redsync) — the reference lock.
- `phase06_production/prodclient/main.go` — the reference client (the synthesis of all of it).
- INCP-520 postmortem + MR !5436 — the two incidents that teach the most.

**Moving to Valkey (6.7).** Every URL below returned HTTP 200 on 2026-10-19, except the Leboncoin post, which is named but not linked.
- **Valkey, "Migration from Redis to Valkey", valkey.io** — https://valkey.io/topics/migration/
  Focus on: the compatibility table, which says Redis CE 7.4 and later data files are not compatible, and the replica and cluster steps. Read it before any plan.
- **Valkey 9.1.2 source, `src/rdb.h`** — https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/src/rdb.h
  Focus on: the comment above `RDB_VERSION 80` and the foreign range 12 to 79. Then `rdbIsVersionAccepted` in `src/rdb.c` lines 85 to 94.
- **Valkey 9.1.2 source, `src/version.h`** — https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/src/version.h
  Focus on: `REDIS_VERSION "7.2.4"`, the reason `INFO` shows that number on every Valkey.
- **Redis 8.10.2 source, `src/cluster.c`** — https://raw.githubusercontent.com/redis/redis/8.10.2/src/cluster.c
  Focus on: the `DUMP` footer at lines 123 to 143 and the version check at line 174. Lab E14 measures both.
- **AWS, "Upgrading engine versions including cross engine upgrades", ElastiCache guide** — https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/VersionManagement.HowTo.html
  Focus on: the CLI command, the 5.0.6 boundary and the "30 to 60 seconds" line. The old URL `VersionManagement.HowTo.cross-engine-upgrade.html` redirects here.
- **AWS, ElastiCache pricing** — https://aws.amazon.com/elasticache/pricing/
  Focus on: "Valkey is priced 20% lower than Redis OSS" and the 33% Serverless line.
- **AWS, ElastiCache Extended Support** — https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/extended-support.html
  Focus on: the support end dates per Redis OSS version.
- **Redis, "Redis Adopts Dual Source-Available Licensing", 2024** — https://redis.io/blog/redis-adopts-dual-source-available-licensing/
  Focus on: the licence change from 7.4. Vendor source.
- **Redis, "Redis is now available under the AGPLv3 open source license", 2025** — https://redis.io/blog/agplv3/
  Focus on: which Redis 8 parts moved into the core. Vendor source.
- **Linux Foundation, Valkey launch press release, 2024** — https://www.linuxfoundation.org/press/linux-foundation-launches-open-source-valkey-community
  Focus on: the fork point, Redis 7.2.4, and the founding members.
- **Valkey, clients page** — https://valkey.io/clients/
  Focus on: the line that clients for Redis OSS 7.2 work with Valkey 7.2 and later.
- **AWS Database Blog, Amazon Ads upgrades to ElastiCache for Valkey, 2025** — https://aws.amazon.com/blogs/database/amazon-ads-upgrades-to-amazon-elasticache-for-valkey-to-achieve-12-higher-throughput-and-save-over-45-in-infrastructure-costs
  Focus on: `MultiWriteCacheClient` with its 100 ms timeout, and the closing numbers. Vendor source.
- **AWS Database Blog, migrating to ElastiCache for Valkey with a customer story, 2026** — https://aws.amazon.com/blogs/database/migrating-to-amazon-elasticache-for-valkey-best-practices-and-a-customer-success-story
  Focus on: why the travel company chose the in-place change over a snapshot. Vendor source, customer not named.
- **AWS Database Blog, MaiCoin blue/green upgrade, 2026** — https://aws.amazon.com/blogs/database/maicoin-case-study-blue-green-upgrade-from-amazon-elasticache-redis-to-valkey
  Focus on: the comparison of in-place and blue/green, and the RedisShake settings. Vendor source with a customer author.
- **Aiven, migrating about 15,000 Redis services to Valkey, 2025** — https://aiven.io/blog/seamlessly-migrating-15k-redis-servers-to-valkey
  Focus on: the two paths, a button and maintenance windows. Vendor source.
- **Momento, "Why Snap Was Willing to Fork, and Why They Still Came Back", 2026** — https://www.gomomento.com/blog/why-snap-was-willing-to-fork-and-why-they-still-came-back/
  Focus on: the RESP proxy, the 8.2 RC crash and the full-sync loop. A summary of a Snap talk, written by a company that sells a competing cache.
- **Classmethod, report of re:Invent 2018 DAT319, Airbnb, 2018** — https://dev.classmethod.jp/articles/dat319-airbnb-journey-from-self-managed-redis-to-elasticache-for-redis/
  Focus on: the replica cutover steps. In Japanese. A third-party report of the talk.
- **RedisShake, tair-opensource** — https://github.com/tair-opensource/RedisShake
  Focus on: the supported versions in the README, Redis 2.8 to 8.4.x, before you pick it for a Redis 8.10 source.
- Leboncoin, "Redis to Valkey migration on AWS", Medium, 2026. Not linked: the page blocked every fetch on 2026-10-19, so its numbers are not checked.

**Security and Kubernetes rows (6.6).** Every URL below returned HTTP 200 on 2026-10-19.
- **Redis 8.10.2 release notes** — https://raw.githubusercontent.com/redis/redis/8.10.2/00-RELEASENOTES
  Focus on: lines 24 to 54, the two SECURITY releases, #15673, #15722 and the certificate CN bypass.
- **Redis docs, security** — https://redis.io/docs/latest/operate/oss_and_stack/management/security/
  Focus on: "Security model" and "Protected mode".
- **Redis docs, ACL** — https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/
  Focus on: "Key permissions", where a key pattern does not limit `FLUSHALL`.
- **Redis docs, TLS** — https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/
  Focus on: the replication and cluster settings.
- **Valkey docs, security** — https://valkey.io/topics/security/
  Focus on: the same trust model, in Valkey's words.
- **AWS, ElastiCache service updates** — https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/Self-Service-Updates.html
  Focus on: which updates apply in the maintenance window and which are self-service.
- **GitHub, availability report for February 2023** — https://github.blog/news-insights/company-news/github-availability-report-february-2023/
  Focus on: the January 30 Container registry incident, where enforcing Redis AUTH broke a hard-coded client.
- **Harness status page, "Feature Flag services is not responding", 2023** — https://status.harness.io/incidents/j6qd0qmfnchy
  Focus on: "Why 2", the liveness probe that checked downstream services, and the probe fix.
- **Kubernetes docs, liveness, readiness and startup probes** — https://kubernetes.io/docs/concepts/workloads/pods/probes/
  Focus on: the caution box under "Liveness probe".

---

## Cheatsheet — Phase 6 (the whole course, one page)

```
MINDTICKLE REDIS IN ONE BREATH
  ElastiCache (cluster-mode varies by region: prod-US enabled, prod-EU disabled),
  volatile-lru, RDB backups (0-3 days), NO AOF, NO cross-region. ~34 services,
  6 jobs, 4 go-redis generations (v6→v9), cache-aside + delete-on-write house style.

THE SIX JOBS (job → primitive → canonical service → phase)
  cache      GET/SET+TTL, delete-on-write   integrations-selfserve, content-center   P2
  session    HASH+TTL                        mt-login-provider(read)/app-gatekeeper   P1
  lock       redsync / SET NX (efficiency)   content-center / ai-tutor,copilot         P3
  idempotency SET NX EX                       ai-module-creation, assessment-gpt        P1
  queue      LIST / PUB-SUB                   asset-hub-analytics / content-center      P1
  ratelimit  INCR+EXPIRE Lua / LPUSH-LTRIM   mt-dashboard-api / integrations-selfserve P1/2

THE REFERENCE DESIGNS
  cache-aside  : versioned key + fail-open + corruption-tolerant + TTL (ListVoices)
  invalidation : delete-on-write (instant) + TTL backstop (bounds a missed delete),
                 3 layers (in-proc 5-10min hot path, Redis 1h shared) — company settings
  lock         : SET NX PX + random token + Lua compare-and-delete (redsync)
  both-stores  : DynamoDB durable+correct (version field) + Redis fast (INCR) — Nyx

THE LOAD-MULTIPLIER LAW (CE !5436)
  amplification = 1/(1-hit_rate).  h=0.99 → 100x.  cacheable:false = full firehose.

THE RECURRING FAILURE (every incident = USAGE, not Redis)
  INCP-520: no-TTL + volatile-lru → unevictable → OOM (missed alert: no owner)
  CE !5436: cacheable:false → 30k/min hot endpoint (fix = cache it)
  live: ai-tutor 0*time.Hour strips TTL (latent INCP-520)

THE FIX-LIST (prioritized)
  P0: audit no-TTL keys; fix ai-tutor 0-TTL; safe-default TTL in shared Set; alert owners
  P1: fence/idempotency on sensitive flows; safe unlocks (token+Lua); env-aware WAIT
  P2: TTL jitter + singleflight on hot keys; hot-key/SLOWLOG alerts; retire v6 client
  P3: converge on one client wrapper; consider allkeys-lru on pure caches

REDIS TO VALKEY (6.7)
  fork point     Valkey = Redis 7.2.4, BSD-3; Redis 7.4+ RSALv2/SSPLv1, 8.0+ adds AGPLv3
  RDB written    Redis 7.2.4 = 11, 7.4 and 8.0 = 12, 8.10.2 = 15; Valkey 8.x = 11, 9.x = 80
  Valkey strict  refuses 12-79 (rdb-version-check strict, default): sync, file, RESTORE
  so             Redis <= 7.2: replica cutover / RDB copy / ElastiCache engine change
                 Redis >= 7.4: copy by plain commands (blue/green) or dual writes
  Redis only     52 names: INCREX DELEX DIGEST HOTKEYS LMOVEM XACKDEL AR* BACKUP ...
  Valkey only    18 names: DELIFEQ COMMANDLOG CLUSTERSCAN CLUSTER MIGRATESLOTS ...
  Valkey later   HEXPIRE HGETEX HSETEX 9.0; HGETDEL MSETEX 9.1
  defaults       Valkey: 6 lazyfree settings yes; repl-backlog-size 10mb vs 1mb
  identity       Valkey INFO: redis_version:7.2.4 + server_name:valkey + valkey_version
  ElastiCache    Valkey 20% cheaper nodes, 33% Serverless; writes pause seconds
                 (from 5.0.6), 30-60 s DNS before 5.0.6; node IPs change
  check          go run ./phase06_production/engine_gap -commandstats

REVIEW ROWS ADDED TO 6.6
  ACL user per service, default off; no @dangerous; @scripting only if needed
  TLS on clients + tls-replication; bus port = port+10000, members only, tls-cluster
  protected-mode yes; a remote PING with no password must fail
  SECURITY releases patched by an owner (8.10.1 and 8.10.2 are both SECURITY)
  turning on AUTH is a client change (GitHub, Container registry)
  liveness probe never calls Redis (Harness); readiness may

THE THESIS
  Redis doesn't fail — usage does. Every gap is discipline: TTLs, unlock safety,
  alert ownership, topology assumptions, round-trip counts. You now have that discipline.
```

---

*🎓 Course complete. You've gone from "we use Redis" to being able to grade every Redis touchpoint at Mindtickle, quantify every failure mode, and produce the prioritized fix-list a staff engineer would. Re-read your Phase 0 cheatsheet — if it reads as obvious now, the course did its job. Next: pick a P0 from the scorecard and ship the MR.*

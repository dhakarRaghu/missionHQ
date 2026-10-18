# Phase 6 — Redis at Mindtickle (the capstone)

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

The capstone code (`phase06_mindtickle/prodclient`) is what "good" looks like as one object: v9 + timeouts, a `Set` that *refuses* a zero TTL, fail-open versioned cache-aside, pipelined `MGet`, and a safe lock — the client the fragmented v6/v8/v9 code *should* converge on.

**The sentence to remember:** Mindtickle runs four go-redis generations with no single wrapper — the v9 clients (ctx, timeouts, replica routing) are the target; the v6 `missions-processors` client (no ctx, no timeout → hangs on a slow Redis) is the worst debt; and the shared `RedisClusterClient` has no safe-default TTL, so the INCP-520 footgun is one `Set(…, 0)` away.

**The trap:** copying the nearest existing client when you add Redis to a service. Half of them are v6/v7 with gaps. Copy the v9 pattern (or the capstone `prodclient`), not the closest file.

**Try this now:**
```bash
go run ./phase06_mindtickle/prodclient
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

**The sentence to remember:** the Mindtickle Redis fix-list is entirely *usage* discipline (TTLs, unlock safety, alert ownership, topology assumptions) — no "Redis is slow" items — because Redis doesn't fail, usage does, and you now have the judgment to grade and prioritize every gap.

**The trap:** finishing this course and reaching for Redis config/scaling knobs when something's wrong. The scorecard says the leverage is almost always in how the code *uses* Redis — start there.

**In your codebase:** pick one P0 or P1 item and scope the actual fix as an MR. (The ai-tutor `0*time.Hour` TTL strip is a genuine one-line fix with a real INCP-520-shaped risk — a perfect first Redis MR now that you understand exactly why it matters.)

---

## 🧪 Hands-on lab — the capstone exercises

Setup:
```bash
cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d && docker exec redis-study redis-cli PING   # → PONG
```

- [ ] **E1. Run the capstone client.**
  - Run: `go run ./phase06_mindtickle/prodclient`
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

---

## 🏢 Mindtickle anchor — the capstone checks

1. **The client spectrum.** Open `missions-processors/clients/cacheClient/redisClient.go` (v6, no ctx/timeout) and `ai-module-creation/src/infrastructure/redis/CacheClientImpl.go` (v9, ctx/timeouts/ReadOnly) side by side. Then open `phase06_mindtickle/prodclient/main.go`. Question: what does the capstone do that neither production client fully does? (Mandatory TTL + fail-open cache-aside + safe lock in one place.)

2. **The crown-jewel cache.** `content-engine` `updateSettings`/`@CacheRetention` + `mt-api-java-client` `CacheResponseUtils` (`CK|`/`SK|`, `REDIS_CACHE_EXPIRY`). Question: this is the org's best invalidation design — what single improvement (from 6.6) would make it more resilient? (TTL jitter + singleflight on the hot settings key.)

3. **Nyx.** `qa-automation/nyx` — the `RedisClient.go` `nyxLastLsIdValue` counter + the DynamoDB `version` field. Question: where does *correctness* live in Nyx, and why is that the right place? (In DynamoDB's versioned conditional write — the resource enforces it, exactly like a fencing token; Redis only does the cheap atomic counting.)

4. **The scorecard's P0.** `ai-tutor/src/usecase/memory/memoryUsecaseImpl.go` — the condensation path's `0*time.Hour`. Question: write the one-line fix and explain, using Phases 4 and 5, exactly what outage it prevents. (Preserve the 24h TTL → key stays evictable under volatile-lru → can't become INCP-520 ballast.)

---

## ✅ Checkpoint 6 — the capstone questions

**Q1.** In four sentences, describe Mindtickle's entire Redis architecture to a new hire: the platform + topology, the six jobs, the house caching style, and the one recurring failure family. (This is the sentence-that-is-the-course from the intro — write it in your own words.)

**Q2.** Walk the CE `cacheable:false` incident end to end using the vocabulary of all six phases. Explain precisely why a 99%-hit-rate endpoint dropping to 0% cache produces ~100x load (the load-multiplier law), why it was invisible, and why the one-line fix worked. Which phases' concepts each appear?

**Q3.** A new service needs to (a) cache user profiles, (b) dedup a "send welcome email" action, and (c) rate-limit an API. For each, specify: the structure, the pattern, the TTL, the failure mode you're accepting, and which existing Mindtickle service you'd copy. Then: which of the three, if implemented with the existing `SETNX`+plain-`DEL` lock, would you *block in review* and why?

**Q4.** Explain Nyx's DynamoDB+Redis split to someone who says "just use one store." Why is DynamoDB the source of truth, why is Redis the counter, and where is correctness enforced? Then generalize: give the rule for when a system should use *both* a durable store and Redis, and where correctness must live.

**Q5.** You're handed the company-settings cache and asked to "make settings changes visible instantly everywhere." Given the 3-layer design (6.3), explain which layer is already instant, which is TTL-bounded (and by how long), and exactly what you'd change to make the slow layer instant — including the cost and the stampede risk you'd introduce.

**Q6.** Produce the P0 items of the Redis fix-list from memory, and for each: the specific service/file, the failure it prevents, and which past incident (or live bug) motivates it. Then defend the ordering — why is the no-TTL audit P0 and the client-convergence P3?

**Q7.** The course's thesis is "Redis doesn't fail, usage does." Argue it using three different Mindtickle incidents/bugs (INCP-520, CE !5436, and the ai-tutor no-TTL bug), showing that each was a usage-discipline failure with a preventable root cause. Then give the one habit (from any phase) that would have caught the most of them.

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
- `phase06_mindtickle/prodclient/main.go` — the reference client (the synthesis of all of it).
- INCP-520 postmortem + MR !5436 — the two incidents that teach the most.

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

THE THESIS
  Redis doesn't fail — usage does. Every gap is discipline: TTLs, unlock safety,
  alert ownership, topology assumptions, round-trip counts. You now have that discipline.
```

---

*🎓 Course complete. You've gone from "we use Redis" to being able to grade every Redis touchpoint at Mindtickle, quantify every failure mode, and produce the prioritized fix-list a staff engineer would. Re-read your Phase 0 cheatsheet — if it reads as obvious now, the course did its job. Next: pick a P0 from the scorecard and ship the MR.*

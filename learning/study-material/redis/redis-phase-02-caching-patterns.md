# Phase 2 — Caching Patterns (the phase that actually pays your salary)

Caching is the reason Redis is in your stack. Phases 0 and 1 built the foundation — one thread, round-trips, the right structure. Now we get to the thing you'll do a hundred times: **put a cache in front of a slow source of truth, correctly.** And "correctly" is doing a lot of work in that sentence, because caching is where the two hardest problems in computer science live — cache invalidation and naming things (you already did naming in 1.8; this phase is the other one).

Here's why this phase matters more than it looks. A cache that's merely *fast* is easy. A cache that's fast *and* doesn't serve stale data *and* doesn't stampede your database when a hot key expires *and* fails open when Redis hiccups *and* doesn't let a scraper of bad IDs melt your DB — that's engineering, and every one of those "ands" is a real Mindtickle incident. The CE `cacheable:false` bug turned 300 requests/min into 30,000/min from *one wrong boolean*. INCP-520 filled a shared cluster because keys had no TTL. Both were caching-pattern failures, not Redis failures.

By the end of this phase you'll know the three write policies cold, you'll have watched a 200-request stampede collapse to a single database call with `singleflight`, you'll have seen synchronized TTLs cause a spike and jitter smear it flat, and you'll be able to defend Mindtickle's actual invalidation design — delete-on-write plus a TTL safety net — in a design review.

Time: 4–6 days. The stampede and invalidation sections are the ones that separate people who "use Redis" from people who can be trusted with a shared cluster.

## What we cover in Phase 2:
```
┌──────────────────────────────────────────────────────────────────────────┐
│  2.1  The three policies   — cache-aside vs read-through vs write-        │
│                              through vs write-behind (and which MT uses)  │
│  2.2  Cache-aside done right— the ListVoices anchor: versioned keys,      │
│                              fail-open, corruption-tolerant               │
│  2.3  The thundering herd  — cache stampede, singleflight, TTL jitter,    │
│                              probabilistic early expiry                    │
│  2.4  Cache penetration    — negative caching the "not found"            │
│  2.5  Invalidation         — TTL vs delete-on-write vs write-through;     │
│                              MT's 3-layer company-settings cache          │
│  2.6  A cache incident     — the CE cacheable:false bug, both directions  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2.1 — The three policies (who writes the cache, and when)

**Why this matters:** every caching bug starts with a fuzzy answer to one question: *who is responsible for putting data in the cache, and who is responsible for taking stale data out?* There are exactly three write policies, they have different failure modes, and picking the wrong one is how you end up serving month-old data or losing writes. Mindtickle overwhelmingly uses one of them — and knowing *why* it picked that one is the point.

Let's define them precisely, because people blur "cache-aside" and "read-through" constantly.

**Cache-aside (lazy loading) — the application manages the cache.** On a read: check cache; on miss, the *application* reads the source and writes the cache. The cache doesn't know the source exists.

```
┌─────────────────────────────────────────────────────────────────────┐
│  CACHE-ASIDE (read path)                                            │
│                                                                     │
│   app ──1.GET──► cache                                              │
│    │            └─ miss ─┐                                          │
│    │  ◄─2.nil────────────┘                                          │
│    ├──3.read────► source of truth (DB/gRPC)  ← slow                │
│    │  ◄─4.data───┘                                                  │
│    └──5.SET (with TTL)──► cache    ← app populates it               │
│                                                                     │
│   Next read for the same key → HIT. This is 95% of MT's caching.   │
└─────────────────────────────────────────────────────────────────────┘
```

**Read-through — the cache library manages the source.** Same read flow, but the *cache layer* (a library/proxy) does the source fetch on miss, transparently. The app just calls `cache.get(key)` and never sees the source. It's cache-aside with the miss-handling moved behind an abstraction. (Mindtickle's `mt-api-java-client` `CacheResponseUtils` is closer to this — the caller asks for an API response and the wrapper handles cache-or-fetch.)

**Write-through — write cache and source together, synchronously.** On a write: write the source *and* the cache in the same request, before returning. The cache is never stale, but every write pays the cache's latency, and you must decide what to do if the cache write fails.

**Write-behind (write-back) — write cache now, flush to source later, asynchronously.** On a write: write the cache immediately, queue the source write for a background flush (often batched). Writes are fast and absorb bursts, but there's a **data-loss window**: if the process dies before the flush, those writes are gone. Only acceptable when the source can tolerate lag and occasional loss.

```
┌────────────────┬──────────────────┬───────────────────┬────────────────────┐
│                │  Cache-aside     │  Write-through    │  Write-behind      │
├────────────────┼──────────────────┼───────────────────┼────────────────────┤
│ Who fills cache│ app, on read-miss│ app, on write     │ app, on write      │
│ Cache freshness│ stale until TTL/ │ always fresh      │ fresh in cache,    │
│                │ explicit delete  │                   │ source lags        │
│ Write latency  │ (writes bypass)  │ source + cache    │ cache only (fast)  │
│ Read latency   │ fast (after warm)│ fast              │ fast               │
│ Data-loss risk │ none (cache is   │ none              │ YES — crash before │
│                │ derived)         │                   │ flush loses writes │
│ Complexity     │ low              │ medium            │ high (flush, retry,│
│                │                  │                   │ ordering, recovery)│
│ MT usage       │ DEFAULT (~all)   │ rare              │ ~never (too risky) │
│ Use when       │ read-heavy, can  │ read-after-write  │ write-heavy, loss- │
│                │ tolerate a stale │ must be fresh     │ tolerant, source   │
│                │ window           │                   │ can't keep up      │
└────────────────┴──────────────────┴───────────────────┴────────────────────┘
```

The senior takeaway: **cache-aside is the default for a reason.** The cache holds *derived* data — losing it is a performance blip (rebuild from source), never a correctness bug. Write-through couples your write latency to the cache; write-behind couples your *durability* to the cache. Both trade the cache-aside safety property (the cache can vanish and nothing breaks) for freshness or speed. Mindtickle almost never makes that trade — cache-aside + explicit invalidation (2.5) is the house style.

**The sentence to remember:** cache-aside keeps the cache *derived and disposable* — that's why it's the safe default; write-through and write-behind buy freshness/speed by coupling correctness or durability to the cache.

**The trap:** write-behind for anything you can't afford to lose. "It's faster" is true right up until the pod is OOM-killed with 500 un-flushed writes in memory.

**Try this now:**
```bash
go run ./phase02_caching/write_through_behind
# write-through: 269ms, durable. write-behind: 4ms, but source.puts=0 until flush.
```

---

## 2.2 — Cache-aside done right (the ListVoices anchor)

**Why this matters:** the toy cache-aside — "GET; if nil, read DB, SET" — is three lines and wrong in production. The real version handles a cache that's down, a value that's corrupt, and a format that changed, and it *never fails the request because of the cache*. Mindtickle's `content-center-service` has a near-perfect example you should internalize as the template: `ExternalContentFacade.ListVoices`.

Here's the actual production flow, annotated (this is real code from `src/domain/externalContent/core/ExternalContentFacade.go`):

```go
func (facade *ExternalContentFacade) ListVoices(ctx, request) (..., error) {
    cacheKey := listVoicesCacheKey(platform, query)   // 1. VERSIONED key (see below)

    if facade.listVoicesCache != nil && platform == ELEVENLABS_PODCAST {
        raw, hit, getErr := facade.listVoicesCache.Get(ctx, cacheKey)
        if getErr != nil {
            facade.logger.Warnf(ctx, "cache get failed, calling vendor: %v", getErr)
            // 2. cache DOWN → log + FALL THROUGH to source (fail open)
        } else if hit {
            var cached model.ExternalContentVoiceListPage
            if err := json.Unmarshal([]byte(raw), &cached); err != nil {
                facade.logger.Warnf(ctx, "cache value corrupt, calling vendor: %v", err)
                // 3. CORRUPT value → don't trust it, fall through
            } else {
                return toListVoicesResponsePodcast(&cached), nil   // 4. HIT
            }
        }
    }

    page, err := vendor.ListVoices(ctx, query)        // 5. MISS → source of truth
    if err != nil { return nil, err }

    if facade.listVoicesCache != nil && ... && page != nil {
        if payload, err := json.Marshal(page); err == nil {
            facade.listVoicesCache.Set(ctx, cacheKey, string(payload), time.Hour) // 6. populate, 1h TTL
        }
        // 7. Set errors are logged, NOT returned — the request already has its data
    }
    return toListVoicesResponsePodcast(page), nil
}
```

Study the five production properties, because they're the difference between a cache and a liability:

1. **Versioned key.** `listVoicesCacheKey` builds `ccs:external_content:list_voices:v1:<platform>:<pageSize>:<base64 pageToken>:<base64 search>`. That `v1` is a kill switch: change the cached struct's shape, bump to `v2`, and every old key is instantly orphaned (and TTL-reaped) — no migration, no stale-format crashes. **Always version cache keys whose value shape can change.**
2. **Fail open on cache-down.** If `Get` errors (Redis unreachable), it logs a warning and calls the vendor. A cache outage becomes *slower*, never *broken*. This is the single most important cache-aside property.
3. **Corruption-tolerant.** If the cached bytes won't unmarshal (format drift, partial write, poisoned value), it doesn't 500 — it falls through to the source. A bad cache entry is self-healing on the next miss.
4. **Miss → source → populate.** The standard path, with the TTL chosen deliberately (1 hour for a vendor voice list that rarely changes).
5. **Populate errors are non-fatal.** A failed `Set` is a logged warning; the caller already has correct data from the source. The cache is an optimization, not a dependency.

This isn't a one-off — it's the house style. Compass found the same shape across the fleet: `integrations-selfserve`'s `getProfileFieldsFromCache` (key `ProfileFields|<cname>`, 30-min TTL, and on *any* exception it falls through to an unconditional API call — fail-open); `ce-uma`'s `Profile.getCompanyProfile` (1-hour TTL, cache-set failures logged not fatal, and notably it reads from a **replica** Jedis pool and writes to a **primary** pool — a read/write split via `REDIS_CACHE_USER_STREAM_READ_HOST` vs `_PRIMARY_HOST`); and `integrations-workflow`'s `RedisCacheLoader` (a generic templated cache-aside loader with an instance-configurable TTL). Same five properties, five services.

Contrast with the anti-pattern that causes incidents:

```go
// WRONG — the cache is now a hard dependency and a stale-format bomb:
raw, err := cache.Get(ctx, "voices")          // key not versioned
if err != nil { return nil, err }             // ← cache down = request FAILS (fail closed)
json.Unmarshal([]byte(raw), &out)             // ← corrupt value = panic/garbage, no fallback
return out                                     // ← never repopulates, no TTL discipline
```

**The sentence to remember:** a production cache-aside fails *open* (cache down → slower, not broken), tolerates corruption (bad value → fall through), and versions its keys (shape change → bump `v1`→`v2`) — the toy version does none of these.

**The trap:** returning the cache's error to the caller. The instant a Redis blip becomes a user-facing 500, your cache has made you *less* available than having no cache at all.

**Try this now:**
```bash
go run ./phase02_caching/cache_aside -id c101      # MISS ~311ms
go run ./phase02_caching/cache_aside -id c101      # HIT  ~6ms
# Then: docker stop redis-study; run again → it FAILS OPEN (slow, not broken). docker start redis-study.
```

---

## 2.3 — The thundering herd (the incident this phase exists for)

**Why this matters:** this is the failure that takes down the *source of truth behind* the cache, which is far worse than the cache itself failing. It's subtle because everything works fine until the exact moment a hot key expires — and then a wall of concurrent requests all miss simultaneously and stampede the database. It's the mechanism behind Mindtickle's CE incident (2.6). If you learn one defensive pattern this phase, make it this one.

Picture a key everyone reads — company settings, a hot course. It has a TTL. At the instant it expires:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  THUNDERING HERD / CACHE STAMPEDE                                        │
│                                                                          │
│  t=0.000  key "hot" is cached, 500 req/s all HIT it → source idle       │
│  t=10.00  key TTL expires                                               │
│  t=10.00  ALL 500 in-flight requests MISS at once                       │
│  t=10.00  ALL 500 call the source simultaneously ──────┐                │
│           ┌──────────────────────────────────────────┐ │                │
│           │  source of truth (DB / content-engine)   │◄┘ 500 identical  │
│           │  designed for ~5 QPS of misses           │   queries at once │
│           │  → CPU 100%, connection pool exhausted    │                  │
│           │  → latency explodes → MORE requests pile  │                  │
│           │  → cascading failure                      │                  │
│           └──────────────────────────────────────────┘                  │
│                                                                          │
│  500 requests did the SAME expensive work to get the SAME answer.       │
└─────────────────────────────────────────────────────────────────────────┘
```

There are three defenses, and the mature answer uses more than one:

**Defense 1 — request coalescing (`singleflight`).** The key insight: of those 500 concurrent misses, only *one* needs to call the source; the other 499 can wait for its result and share it. Go's `golang.org/x/sync/singleflight` does exactly this — it collapses concurrent calls with the same key into a single execution.

```go
// Instead of 500 goroutines each calling the source:
v, _, _ := g.Do(key, func() (interface{}, error) {
    val, err := loadFromSource()          // only the FIRST caller runs this
    if err == nil { rdb.Set(ctx, key, val, ttl) }
    return val, err                        // the other 499 block here and get this
})
```

This is *in-process* coalescing — it protects the source from one pod's herd. (500 pods each doing one call is still 500 calls; for cross-pod coalescing you need a distributed lock — Phase 3 — where one pod computes and the rest poll the cache.)

**Defense 2 — TTL jitter.** A stampede is often *self-inflicted* by synchronized expiry: you warm 1000 keys at deploy time with the same 600s TTL, so all 1000 expire in the same second. Fix: add randomness to the TTL — `base ± jitter` — so expirations smear across a window instead of firing in a spike.

```
   Fixed TTL (600s for all):          Jittered TTL (600 ± 60s):
   1000 keys                          ~17 keys
      │                                  ░░░░░░░░░░░░░░░░░
      █  ← all expire at t=600           ░░░░░░░░░░░░░░░░░  ← smeared over 120s
   ───┴───────────                    ──░░░░░░░░░░░░░░░░░──
   one giant miss spike               no spike, source stays calm
```

**Defense 3 — probabilistic early expiry (XFetch).** The advanced move: instead of waiting for a hard TTL, each reader *probabilistically* decides to refresh the key slightly *before* it expires, with probability rising as expiry approaches. One lucky reader refreshes early while the key is still valid for everyone else — so there's never a moment where the key is absent and everyone misses. This is the "optimal probabilistic cache stampede prevention" algorithm; you reach for it on your hottest keys.

**The uncomfortable Mindtickle truth (Compass-verified):** none of these three defenses currently exists on Mindtickle's *Redis* path. No `singleflight`/request-coalescing, no distributed lock around cache population, no probabilistic early expiry, and **no TTL jitter anywhere** — every TTL is a hardcoded constant. The only coalescing that exists is in *in-process* `Guava LoadingCache` instances (`game_engine`, `CoachingApiGateway`, `mt-api-java-client`'s `NewUserManager`), which dedupe concurrent loads *within one JVM* but do nothing for the shared Redis path. So the shared caches — company settings, `GET /game` — are structurally exposed to exactly this stampede. That's not a criticism to score points; it's *why the CE incident (2.6) was able to amplify to 30,000 calls/min*: with no coalescing and no jitter, the moment a hot key isn't cached, every concurrent request goes straight through. Treat this section as the improvement backlog, not a description of current state.

**The sentence to remember:** a hot key's expiry is a scheduled DDoS on your database — coalesce concurrent misses (`singleflight`), jitter TTLs so keys don't expire in lockstep, and for the hottest keys refresh probabilistically before expiry. (And know that Mindtickle does none of these on Redis yet — the exposure is real.)

**The trap:** warming a cache with a uniform TTL. You've built a time bomb that goes off one TTL after every deploy. Jitter is one line; skipping it is an incident — and right now the codebase skips it everywhere.

**Try this now:**
```bash
go run ./phase02_caching/thundering_herd -conc 200   # 200 source calls → 1 with singleflight
go run ./phase02_caching/ttl_jitter -keys 1000 -base 600 -jitter 60   # 1 bucket → 121 buckets
```

---

## 2.4 — Cache penetration (negative caching)

**Why this matters:** cache-aside only caches *hits*. If a key genuinely doesn't exist in the source, every request for it misses the cache *and* misses the source — so a flood of requests for non-existent IDs (a scraper, a broken client, an enumeration attack) sails straight through the cache and hammers your DB with lookups that always return nothing. This is "cache penetration," and the fix is a one-liner most people forget.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Request for id "ghost-999" which does NOT exist:                   │
│                                                                     │
│  GET cache:ghost-999  → nil (miss)   ← cache-aside only caches hits │
│  read source ghost-999 → not found   ← DB hit that returns nothing  │
│  ...cache NOTHING (bug!)...                                         │
│  next request for ghost-999 → repeats the WHOLE thing → DB again    │
│                                                                     │
│  10,000 req/s for random non-existent ids = 10,000 DB lookups/s     │
└─────────────────────────────────────────────────────────────────────┘
```

The fix — **negative caching** — is to cache the *absence* too, with a sentinel value and a **short** TTL:

```go
val, err := rdb.Get(ctx, key).Result()
if err == redis.Nil {                       // cache miss
    if exists := source.Lookup(id); exists {
        rdb.Set(ctx, key, realValue, 10*time.Minute)
    } else {
        rdb.Set(ctx, key, tombstone, 30*time.Second)  // ← cache the "not found", SHORT ttl
    }
} else if val == tombstone {
    return NotFound                          // served from negative cache, no DB hit
}
```

Why *short* TTL on the negative entry? Because it's the freshness/protection trade-off in miniature: too long, and "I just created entity X but it 404s for 10 minutes" (the negative entry outlives reality); too short, and you don't blunt the flood. 30–60 seconds is a common sweet spot — long enough to absorb a burst, short enough that a real creation becomes visible fast.

**The Mindtickle truth (Compass-verified):** Mindtickle does **not** do negative caching in Redis anywhere — every Redis cache is positive-only, so misses for nonexistent keys penetrate to the source every time. The cleanest live example is `mt-login-provider`'s `oauth_client_dao.go`: `GetOAuthClient` reads Redis, on a miss loads from Tickle, and *only backfills Redis if a record is found* — so a repeated lookup for a nonexistent `client_id` re-hits Tickle **every single time**. That's a live penetration path. Interestingly, the *pattern* does exist at Mindtickle, just in **in-process** caches, not Redis: `stateful-url-edge` is the textbook version — a `null` sentinel with a deliberately *shorter* negative TTL (`NEG_CACHE_TTL_MS=5s` vs positive `10s`), commented "bound how long a freshly minted token could 404 if a request races ahead of Global-Table replication." So the right instinct exists in the org; it just hasn't been applied to the Redis layer. Another improvement backlog item.

**The sentence to remember:** cache-aside caches hits, so a flood of nonexistent IDs penetrates straight to the DB — cache the "not found" with a short TTL to blunt it, but keep it short or you'll 404 things that now exist. (Mindtickle's Redis caches don't do this yet — `oauth_client_dao` penetrates on every miss for a nonexistent id.)

**The trap:** a long negative-cache TTL. It turns "create then immediately read" into a confusing 404, and those bugs are miserable to diagnose because the data *is* there. (`stateful-url-edge` gets this right with a 5s negative TTL tied to replication lag.)

**Try this now:**
```bash
go run ./phase02_caching/negative_cache -id ghost-999 -n 5   # 5 DB lookups → 1
```

---

## 2.5 — Invalidation (the actually-hard problem, and MT's answer)

**Why this matters:** "there are only two hard things in CS: cache invalidation and naming." Invalidation is hard because it's a *distributed consistency* problem in disguise: the source changed, and now N cached copies across M services are wrong, and you have to make them right without a stampede and without a race. Mindtickle solved this for its most-read data — company settings — with a specific, learnable design. Learn it as *the* reference pattern.

The strategies, weakest to strongest:

**TTL-only (expiry-based).** Set a TTL; accept that the cache can be stale for up to that long. Simplest possible. Correct when staleness is tolerable (a voice list, a rarely-changing config). `integrations-workflow`'s `CompanySettingsCache` does exactly this — a pure 10-minute TTL, no active invalidation. The cost: a settings change isn't visible for up to 10 minutes.

**Delete-on-write (active invalidation).** On every write to the source, *delete* the cache key (don't update it — delete it, so the next read re-populates from the fresh source). Combined with a TTL as a safety net, this is the gold standard.

```
┌───────────────────────────────────────────────────────────────────────┐
│  MINDTICKLE COMPANY-SETTINGS CACHE — the 3-layer reference design      │
│                                                                        │
│  ① content-engine (source of truth)                                    │
│     updateSettings() @CacheRetention({COMPANY})                        │
│        └─ on write: DELETE the Redis scope marker  Scope|<companyId>   │
│                          │  (delete-on-write, synchronous)             │
│                          ▼                                             │
│  ② mt-api-java-client (shared lib — EVERY Java service reads via it)    │
│     keys: CK|<url>|hash , SK|<scope>|md5(url) ; TTL 3600s (1h) default  │
│        └─ the deleted scope marker invalidates all keys under it       │
│           → next read MISSES → refetches fresh → 1h TTL is the backstop│
│                          ▼                                             │
│  ③ integrations-workflow (Lambda) — its OWN 600s pure-TTL copy         │
│     no listener; just expires every 10 min                             │
│                                                                        │
│  Invalidation = delete-on-write (instant) + TTL (safety net).          │
│  NO Kafka/pub-sub invalidation anywhere in this chain.                 │
└───────────────────────────────────────────────────────────────────────┘
```

Why *delete* and not *update* the key on write? Two reasons. First, **it's cheaper and race-free**: you don't recompute the cached value on the write path (which might be an expensive join); you just invalidate and let the next reader lazily repopulate. Second, **updating races**: if two writes happen close together and each updates the cache, they can interleave so the cache ends up with the *older* write's value (write A reads, write B reads, B writes cache, A writes cache — cache now has A, but B was newer). Deleting sidesteps this — the next read always pulls the current source truth.

Why the **TTL as a backstop** even with delete-on-write? Because delete-on-write is best-effort: the delete can fail (Redis blip), a write path can be missed (a new code path that forgets to invalidate), or a key can be written directly. The TTL guarantees that *no matter what bug exists*, staleness is bounded — the cache is eventually correct within one TTL. **Delete-on-write for freshness, TTL for safety. Always both.**

The actual TTLs across Mindtickle's settings caches (Compass-verified) — note the deliberate layering of *different* windows, and that **every one is a fixed constant with zero jitter** (per 2.3, an unmitigated synchronized-expiry exposure):

```
┌────────────────────────────────────────────────┬──────────┬─────────────┐
│ Cache layer                                    │ TTL      │ Kind        │
├────────────────────────────────────────────────┼──────────┼─────────────┤
│ content-engine in-mem ConcurrentHashMap        │ 5 min    │ in-process  │
│ game_engine Guava company-settings             │ 10 min   │ in-process  │
│ integrations-workflow CompanySettingsCache     │ 10 min   │ Redis, TTL  │
│ mt-api-java-client CK|/SK| (REDIS_CACHE_EXPIRY)│ 1 hour   │ Redis, +del │
│ content-engine-redis cluster (~27 svcs default)│ 30min-1h │ Redis, TTL  │
└────────────────────────────────────────────────┴──────────┴─────────────┘
```

**Write-through as invalidation.** If you write-through (2.1), the cache is never stale by construction — the write updates it. But you've bought that with write latency and the update-race problem above, which is why MT prefers delete-on-write.

**The sentence to remember:** the reference pattern is delete-on-write (instant freshness, race-free, cheap) plus a TTL backstop (bounds staleness when the delete is missed) — Mindtickle's company-settings cache is exactly this, three layers deep.

**The trap:** relying on delete-on-write *alone* with no TTL. The one code path that forgets to invalidate now serves stale data *forever*. The TTL is what makes the system self-heal.

**In your codebase:** `mt-api-java-client`'s `CacheResponseUtils` / `CERestUtils` (the `CK|`/`SK|` keys, `REDIS_CACHE_EXPIRY`) and `content-engine`'s `@CacheRetention` + `Redis.bulkRemove`. Trace one settings write and find where the scope key gets deleted, then find the 1h TTL. Ask: which layer catches a *missed* invalidation, and how long is the worst-case staleness? (Answer: the TTL layer; up to 1 hour for `mt-api-java-client`, 10 min for `integrations-workflow`.)

---

## 2.6 — Anatomy of a cache incident: the CE `cacheable:false` bug

**Why this matters:** this is a real Mindtickle incident (fixed in MR #5436) and it teaches something most caching tutorials never do — that a cache failure can be *silent* and *inverted*: nothing errored, nothing paged at first, the system just quietly did 100× the work it should have. Understanding it makes you able to spot the class of bug where "the cache is working fine" is exactly the problem.

The setup: `content-engine` caches API responses in Redis via `mt-api-java-client` (`CacheResponseUtils`/`CERestUtils`), which check a `cacheable` flag on the response before caching. `RefMediaAPISerializer.java` (~line 53) marked *any* media whose status wasn't `SUCCESS`, `FAILED`, or `PUBLISHABLE_PROCESSED_BUT_FULLCONVERT_FAILED` as `cacheable:false`. The kicker: a Lambda callback that was supposed to advance media *out of* the `PUBLISHABLE_PROCESSED` state had been commented out in a 2022 refactor (LEA-580). So thumbnails sat in `PUBLISHABLE_PROCESSED` **for ~8 years**, every `GET /game` touching them was stamped `cacheable:false`, and every request bypassed the Redis cache entirely.

```
┌───────────────────────────────────────────────────────────────────────┐
│  THE CE cacheable:false BUG                                            │
│                                                                        │
│  Intended:   GET /game → cacheable:true                               │
│     first request  → MISS → content-engine → cache it                 │
│     next  requests → HIT cache → content-engine sees ~300 calls/min   │
│                                                                        │
│  Actual (bug):  GET /game → cacheable:false                           │
│     EVERY request → not cached → content-engine → EVERY time          │
│     content-engine sees 30,000 calls/min  ← 100x amplification        │
│                                                                        │
│  Symptom: content-engine + content-engine-read-service overloaded;    │
│  downstream (Allaboard, App-Gatekeeper) latency up. No error, no      │
│  deploy that looked related — just "everything is slow."              │
│                                                                        │
│  Fix (MR !5436, merged 2025-07-03, branch hotfix/caching-get-game):   │
│  if media is an ImageVo + cropped + PUBLISHABLE_PROCESSED →           │
│  setCacheable(TRUE). One file changed.                                │
│  Results: GET /game 30k→300/min (100x); content-engine traffic −80%;  │
│  content-engine-read-service −50%; GET /game p90 100ms→20ms (−65%);   │
│  peak DynamoDB RCU 35k→7k/min; downstream (Allaboard, App-Gatekeeper, │
│  Game Engine) −60% latency.                                           │
└───────────────────────────────────────────────────────────────────────┘
```

The general principle — and this is the thing to carry forever: **a cache is a load *multiplier*, in both directions.** A working cache with a 99% hit rate turns 30,000 potential calls into 300 — a 100× *reduction*. Flip one boolean and you don't get "slightly more load," you get the full un-cached firehose — a 100× *amplification*, instantly. The blast radius of a cacheability decision is the entire hit rate, which for a hot endpoint is enormous.

This is why the defensive machinery around it exists: the `REMOVE_CACHE_FLAG` in `MTAction.java`/`ConcatMediaModel.java` is a per-request boolean that gates whether the `COMPANY_MEDIA_PARTIAL` Redis scope gets busted after a request — `ConcatMediaModel.checkConcatStatus()` sets it `false` while *polling* a media-concat job (so it doesn't flush the cache on every poll) and flips it back to `true` once the job succeeds, busting the stale entry exactly once. And `CompanyDao.getSettingsMinimal` (in `ce-content`) wraps cached-JSON parsing in a try/catch so a corrupted cache entry is logged and falls through to `getSettings(company)` instead of crashing — the same fail-open, corruption-tolerant instinct as the ListVoices anchor in 2.2. (One notable exception to fail-open: `ce-uma`'s `UserStreamRedis.getProfile` wraps Redis errors as a `CacheException` and *re-throws* — a rare fail-*closed* path in an otherwise fail-open codebase.)

**The sentence to remember:** a cache is a load multiplier — a wrong `cacheable` flag doesn't add load, it *multiplies* it by your hit rate, so a one-boolean bug becomes a 100× amplification with no error and no obvious cause.

**The trap:** treating cacheability as a cosmetic setting. It's a load-bearing decision; a `cacheable:false` on a hot path is a production incident waiting for traffic.

**Verify your understanding:** if `GET /game` had a 99% hit rate before the bug, what multiple of normal load hit content-engine after? (100×: 1% of traffic was reaching the source; now 100% does. Hit rate `h` → amplification `1/(1-h)`.)

---

## 🧪 Hands-on lab — the exercises that teach Phase 2

Setup:
```bash
cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d && docker exec redis-study redis-cli PING   # → PONG
```

- [ ] **E1. Cache-aside: miss then hit.**
  - Run: `go run ./phase02_caching/cache_aside -id c101` twice.
  - Expected: first ~311ms (MISS, hits slow source), second ~6ms (HIT).
  - Teaches: the whole read-cache/populate loop and the latency payoff.

- [ ] **E2. (Break it) Fail open when Redis is down.**
  - Run: `docker stop redis-study; go run ./phase02_caching/cache_aside -id c9; docker start redis-study`
  - Expected: the request still returns (from source), with a `[warn] cache GET failed … failing open` line — NOT a crash.
  - Teaches: the single most important cache-aside property — a cache outage is slower, not broken.

- [ ] **E3. Thundering herd, then singleflight.**
  - Run: `go run ./phase02_caching/thundering_herd -conc 200`
  - Expected: `WITHOUT: 200 source calls`, `WITH: 1 source call`.
  - Teaches: request coalescing collapses N concurrent misses of one key into one source call.

- [ ] **E4. Scale the herd.**
  - Run: `go run ./phase02_caching/thundering_herd -conc 1000`
  - Expected: still exactly 1 source call with singleflight; ~1000 without.
  - Teaches: coalescing is O(1) source calls regardless of concurrency (per process).

- [ ] **E5. TTL jitter distribution.**
  - Run: `go run ./phase02_caching/ttl_jitter -keys 1000 -base 600 -jitter 60`
  - Expected: fixed → 1 expiry bucket (spike); jittered → ~121 buckets over 120s (smear).
  - Teaches: synchronized TTLs self-inflict stampedes; jitter smears expiry.

- [ ] **E6. Prove synchronized expiry in Redis directly.**
  - Run: warm 1000 keys with the same TTL: `for i in $(seq 1 1000); do echo "SET warm:$i v EX 30"; done | docker exec -i redis-study redis-cli --pipe`. Wait ~28s, then `docker exec redis-study redis-cli DBSIZE` repeatedly around t=30s.
  - Expected: DBSIZE drops from ~1000 to ~0 in one ~1s window — the synchronized-expiry cliff.
  - Teaches: what a fixed-TTL bulk warm looks like from the keyspace's side.

- [ ] **E7. Negative caching.**
  - Run: `go run ./phase02_caching/negative_cache -id ghost-999 -n 5`
  - Expected: without → 5 source lookups; with → 1.
  - Teaches: caching the "not found" stops penetration.

- [ ] **E8. (Break it) Negative-cache staleness.**
  - Reason about it: with a 30s negative TTL, an entity created 5s after its first (404) lookup is invisible for how long? Now change the sentinel TTL to 10 minutes in `negative_cache/main.go` and argue why that's dangerous.
  - Teaches: the negative-TTL freshness trade-off directly.

- [ ] **E9. Write-through vs write-behind.**
  - Run: `go run ./phase02_caching/write_through_behind`
  - Expected: write-through ~269ms and `source.puts=5`; write-behind ~4ms and `source.puts=0` until the flush.
  - Teaches: the durability-vs-latency trade and the write-behind loss window.

- [ ] **E10. Delete-on-write by hand.**
  - Run: `docker exec redis-study redis-cli SET settings:c7 '{"v":1}' EX 3600` (cache). Then simulate a write: `docker exec redis-study redis-cli DEL settings:c7`. Then read: `docker exec redis-study redis-cli GET settings:c7` → nil → (your app repopulates).
  - Expected: the DEL forces the next read to repopulate from source.
  - Teaches: why invalidation deletes (not updates) the key.

- [ ] **E11. See the versioned-key kill switch.**
  - Run: `docker exec redis-study redis-cli SET "ccs:list_voices:v1:x" old; docker exec redis-study redis-cli SET "ccs:list_voices:v2:x" new; docker exec redis-study redis-cli KEYS "ccs:list_voices:v*"` (sandbox only — never KEYS in prod).
  - Expected: both versions coexist; bumping v1→v2 orphans all v1 keys (TTL reaps them).
  - Teaches: how a version segment in the key gives you instant format migration.

- [ ] **E12. Measure hit rate.**
  - Run: `docker exec redis-study redis-cli INFO stats | grep keyspace` (`keyspace_hits`, `keyspace_misses`).
  - Compute: hit rate = hits/(hits+misses). Then compute the amplification `1/(1-h)` for h=0.99.
  - Teaches: the CE-incident math — hit rate is the load multiplier.

---

## 🏢 Mindtickle anchor — things to check in the codebase

1. **The reference cache-aside.** Open `content-center-service/src/domain/externalContent/core/ExternalContentFacade.go` (`ListVoices`) and `listVoicesCache.go` (the key builder). Confirm all five properties from 2.2: versioned key (`:v1`), fail-open on `getErr`, corruption fall-through on unmarshal error, 1h TTL, non-fatal `Set`. Question: what happens to a user request if Redis is completely down during `ListVoices`? (It's slower — hits the vendor — but succeeds. That's the design.)

2. **The 3-layer settings cache.** In `mt-api-java-client` find `CacheResponseUtils`/`CERestUtils` (keys `CK|`/`SK|`, `REDIS_CACHE_EXPIRY` default 3600s) and in `content-engine` find `updateSettings()` `@CacheRetention({COMPANY})` → `Redis.bulkRemove` of the `Scope|<company>` marker. Questions: when an admin changes a company setting, what deletes the cache and how fast is it visible? If that delete silently failed, what's the worst-case staleness and which layer bounds it? (The 1h TTL.)

3. **The incident's defensive code.** In `content-engine`, find `MTAction.java`/`ConcatMediaModel.java`'s `REMOVE_CACHE_FLAG` throttle and `CompanyDao.getSettingsMinimal`'s try/catch around cached-JSON parsing. Question: the `getSettingsMinimal` try/catch is the same instinct as ListVoices' corruption fall-through — what does each protect against, and why is "log and go to source" always safer than "trust the cache blindly"?

4. **A negative-caching candidate.** Pick any cache-aside read in a service you own (e.g. an entity-by-id lookup). Ask: what happens today when someone requests an ID that doesn't exist, repeatedly? Does it penetrate to the DB every time? If so, that's a negative-caching opportunity — sketch the sentinel + short TTL.

---

## ✅ Checkpoint 2 — answer in your own words

**Q1.** Walk the CE `cacheable:false` bug end to end. Given `GET /game` had a 99% hit rate and content-engine normally saw 300 calls/min, compute the calls/min after the flag flipped. State the general formula (amplification as a function of hit rate `h`), and explain why this bug produced *no error* and looked like "everything is slow, nothing deployed."

**Q2.** Your service reads company settings 5,000 times/sec across 40 pods, all from one hot Redis key with a 1-hour TTL. The key expires. Describe exactly what hits content-engine in the next 100ms with (a) no protection, (b) per-pod `singleflight`, (c) `singleflight` + a distributed lock. Give the approximate source-call count for each. Why can't `singleflight` alone get you to 1 call across 40 pods?

**Q3.** A colleague proposes write-through for the company-settings cache: "update the cache whenever settings change, so it's never stale — cleaner than delete-on-write." Give two concrete reasons Mindtickle deletes instead of updates (hint: one is a race, one is cost), and the one scenario where write-through would actually be the better call.

**Q4.** You warm 50,000 course keys at deploy time, each with a flat `EX 3600`. Everything is fine for 59 minutes. Predict minute 60, quantify it, and give the one-line fix. Then: why does this bug reproduce *every* deploy, and why is it nearly invisible in a canary/staging test?

**Q5.** Design task: an endpoint `GET /entity/{id}` where ~5% of traffic is for IDs that don't exist (a misbehaving integration enumerating IDs). Design the full cache-aside + negative-cache flow: key format, positive TTL, negative sentinel + TTL, and the fail-open behavior. Then defend your negative TTL against both "too long" and "too short" attacks.

**Q6.** "The cache is a dependency" vs "the cache is an optimization" — the ListVoices anchor is firmly the latter (fail open, corruption-tolerant). Give a scenario where you'd *deliberately* fail *closed* (treat cache-down as request-fail) instead, and explain what property you'd be buying and what you'd be risking. (Hint: think rate-limiter or a cache that holds authorization decisions.)

**Q7.** A settings change made by an admin isn't visible for up to an hour in one service but is instant in another. Given the 3-layer design in 2.5, explain which service is which and why — and whether the 1-hour delay is a bug or a deliberate trade-off. What single change would make the slow one instant, and what would it cost?

---

## References & Further Learning

**Must-read (in order):**
- 📄 [Cache-Aside pattern — Microsoft Azure Architecture](https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside) — the crispest definition of cache-aside vs read/write-through, with the exact failure modes. (12 min) Read BEFORE 2.1.
- 📄 [Caching strategies and best practices — AWS ElastiCache docs](https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/Strategies.html) — lazy loading vs write-through vs TTL, on the platform Mindtickle actually runs. (15 min) Read with 2.1–2.2.
- 📄 [Optimal Probabilistic Cache Stampede Prevention (XFetch) — the paper](https://cseweb.ucsd.edu/~avattani/papers/cache_stampede.pdf) — the foundational paper behind probabilistic early expiry (Defense 3). (30 min) Read AFTER E3–E5; short and worth it.
- 📄 [singleflight package docs — golang.org/x/sync](https://pkg.go.dev/golang.org/x/sync/singleflight) — the exact library the herd demo uses; read the `Do`/`DoChan`/`Forget` semantics. (10 min)

**Deep dives:**
- 📄 [Redis Best Practices: Caching patterns — Redis docs](https://redis.io/docs/latest/develop/use-cases/caching/) — the canonical caching guide with invalidation strategies. (15 min)
- 📄 [The cache invalidation problem — a good survey](https://www.confluent.io/blog/turning-the-database-inside-out-with-apache-samza/) — why invalidation is really a distributed-consistency problem; frames delete-on-write vs log-based invalidation. (20 min) Read after 2.5.
- 📄 [Facebook's memcache paper: "Scaling Memcache at Facebook"](https://www.usenix.org/system/files/conference/nsdi13/nsdi13-final170_update.pdf) — the definitive production caching paper; leases (their singleflight), the thundering-herd section, and negative caching are all here. (45 min) The one to read when everything else clicks — sections 3.2 (leases) and 3.3 are the gold.

**Official docs (bookmark):**
- [Redis EXPIRE / TTL / SET options](https://redis.io/commands/set/) — `EX`, `PX`, `NX`, `XX`, `KEEPTTL` — the TTL toolkit.
- [redis keyspace notifications](https://redis.io/docs/latest/develop/use-cases/keyspace-notifications/) — for building event-driven invalidation (an alternative to delete-on-write).

---

## Cheatsheet — Phase 2

```
THE THREE WRITE POLICIES
  cache-aside   : app fills cache on read-miss. Cache is DERIVED/DISPOSABLE.
                  → MT DEFAULT. Fail open, version keys, TTL everything.
  write-through : write source + cache synchronously. Never stale; slow writes.
  write-behind  : write cache now, flush source async. FAST but LOSS WINDOW. Avoid.

PRODUCTION CACHE-ASIDE (the 5 properties — ListVoices template)
  1. VERSIONED key   ...:v1:...   (bump to invalidate a whole format)
  2. FAIL OPEN       cache GET error → log + go to source (never 500)
  3. CORRUPTION-OK   unmarshal error → fall through to source
  4. miss→source→SET with a deliberate TTL
  5. SET/marshal errors are WARNINGS, not failures

THUNDERING HERD (hot key expires → N misses stampede the DB)
  Defense 1: singleflight  → coalesce N concurrent misses into 1 source call (per pod)
  Defense 2: TTL jitter    → base ± jitter, so keys don't expire in lockstep
  Defense 3: probabilistic early expiry (XFetch) → refresh hottest keys BEFORE expiry
  cross-pod: singleflight is per-process → add a distributed lock (Phase 3) for 1 global call
  ⚠ MT status: NONE of these on the Redis path. No jitter anywhere (all fixed TTLs).
    Only in-process Guava caches coalesce (per-JVM). This is why CE could amplify.

CACHE PENETRATION (flood of nonexistent ids → every req hits DB)
  fix: NEGATIVE CACHE the "not found" with a SHORT ttl (30-60s)
  trap: long negative ttl → "created it but it 404s" bug
  ⚠ MT status: no Redis negative caching. oauth_client_dao re-hits Tickle on every
    miss for a nonexistent id. Pattern exists only in in-process caches
    (stateful-url-edge: null sentinel, 5s neg TTL vs 10s positive).

INVALIDATION (delete-on-write + TTL backstop = gold standard)
  delete-on-write : on source write, DELETE key (not update — avoids races, cheap)
  TTL backstop    : bounds staleness when a delete is missed → self-healing
  MT settings cache (3 layers):
    content-engine  → @CacheRetention, DELETE Scope|<company> on write
    mt-api-java-client → CK|/SK| keys, 3600s TTL fallback
    integrations-workflow → own 600s pure-TTL copy

THE LOAD-MULTIPLIER LAW (the CE !5436 lesson)
  amplification = 1 / (1 - hit_rate)
  h=0.99 → 100x. Flipping cacheable:false doesn't ADD load, it MULTIPLIES it.
  a working cache is a load MULTIPLIER in both directions.

INCIDENTS
  CE cacheable:false (MR !5436): RefMediaAPISerializer stamped PUBLISHABLE_PROCESSED
    media uncacheable (Lambda callback commented out 2022, stuck ~8yr). GET /game
    30k→300/min, CE traffic −80%, p90 100ms→20ms, DynamoDB RCU 35k→7k/min.
  INCP-520: no-TTL keys → 100% memory → shared Uploader down 4h37m

MT REALITY CHECK (Compass-verified — the improvement backlog)
  fail-open is the norm (getSettingsMinimal try/catch → source); ce-uma getProfile
    is the rare fail-CLOSED exception.
  NO stampede protection, NO TTL jitter, NO Redis negative caching anywhere.

INVESTIGATE
  INFO stats | grep keyspace   → keyspace_hits / keyspace_misses (hit rate)
  TTL <key>                    → is it -1 (no expiry!) / -2 (gone) / n sec
  SET k v EX n                 → always set a TTL; KEEPTTL to update value, keep expiry
```

---

*Next: Phase 3 — Distributed Locking. `SET NX EX`, the Lua compare-and-delete unlock, the Redlock debate (and why Martin Kleppmann and antirez disagree), and fencing tokens — anchored to content-center-service's `redsync` locks, course-qu-processors' ZSet lock table, and the hand-rolled `SETNX` locks in ai-tutor/copilot-chat-agent. Say `next`.*

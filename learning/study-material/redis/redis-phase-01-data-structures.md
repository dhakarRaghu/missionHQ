# Phase 1 — Data Structures & Patterns (the leverage phase)

Phase 0 gave you the one fact everything hangs off: one thread, atomic commands, round-trips are the cost. This phase is where that fact starts paying rent. Because here's the thing that separates Redis from Memcached and from "a hash map behind a socket": **Redis doesn't store bytes, it stores *data structures*, and each structure comes with commands that do work on the server that you'd otherwise do in your service — atomically, in one round-trip.**

That sentence is the whole phase. Every time you pick the right structure, you delete code, you delete round-trips, and you get atomicity for free. Every time you pick the wrong one — the classic being "just JSON-blob it into a String" — you pay for it later in round-trips, memory, and race conditions.

You already use five of these structures in production without necessarily having chosen them deliberately: `missions-processors` blobs a persona into a **String**, `mt-login-provider` models a session as a **Hash** with a **Set** as its secondary index, `content-search-service` runs a FIFO **List** queue, and a translation orchestrator uses a **Sorted Set** as a job-in-progress marker. By the end of this phase you'll know *why* each of those is the right (or arguable) call, and you'll have built a sliding-window rate limiter, a blocking work queue, and a HyperLogLog that counts 100,000 users in 14 KB — on your own machine, measured.

Time: 3–5 days. This is the phase you'll come back to most, because "which structure?" is a decision you make every week.

## What we cover in Phase 1:
```
┌──────────────────────────────────────────────────────────────────────────┐
│  1.1  Strings        — the workhorse: cache blobs, counters, SETNX flags │
│  1.2  Hashes         — objects with independently-addressable fields     │
│  1.3  Lists          — FIFO/LIFO queues, BLPOP workers, capped logs      │
│  1.4  Sets           — uniqueness, membership, server-side set algebra   │
│  1.5  Sorted Sets    — THE power tool: leaderboards, sliding windows,    │
│                        delayed queues, job markers                       │
│  1.6  The special 3  — Streams, HyperLogLog, Bitmaps (and why MT hasn't  │
│                        reached for them yet)                             │
│  1.7  Encoding       — listpack vs hashtable: the 10x memory switch      │
│  1.8  Key naming     — the convention that keeps a shared cluster sane   │
└──────────────────────────────────────────────────────────────────────────┘
```

The mental model to carry through all of it:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  A Redis keyspace is a giant top-level hash map:                        │
│                                                                         │
│     key (string)                 →   VALUE (one of these types)         │
│  ┌────────────────────────┐         ┌──────────────────────────────┐   │
│  │ "sess:abc"             │────────►│ Hash   {token, ip, role}     │   │
│  │ "user:u42:sessions"    │────────►│ Set    {abc, def, ghi}       │   │
│  │ "queue:jobs"           │────────►│ List   [j1, j2, j3]          │   │
│  │ "ratelimit:c7:/report" │────────►│ ZSet   {ts1, ts2, ts3}       │   │
│  │ "persona:m1:u42"       │────────►│ String "{json...}"           │   │
│  └────────────────────────┘         └──────────────────────────────┘   │
│                                                                         │
│  The key is ALWAYS a string. The VALUE's type decides which commands   │
│  are legal. Run a Hash command on a String key → WRONGTYPE error.      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 1.1 — Strings (the workhorse you already overuse)

**Why this matters:** the String is where everyone starts, and it's the right answer more often than not — but it's also where the single most common modeling mistake lives ("I'll just JSON-blob my object into a String"). Knowing exactly what a String is good at, and where it stops being the right tool, is the foundation for every other choice in this phase.

A Redis String is a binary-safe byte sequence up to 512 MB. "Binary-safe" means it doesn't care what's inside — UTF-8, a JSON blob, a protobuf, a JPEG, an integer. That flexibility is why it's the workhorse. But a String is not *just* a dumb blob; it has three distinct personalities:

**Personality 1 — the cache blob.** This is `missions-processors`' buyer persona: marshal a struct to JSON, `SET` it with a TTL, `GET` + unmarshal on read. Simple, opaque, whole-object.

```
┌──────────────────────────────────────────────────────────────────┐
│  SET persona:m1:u42 '{"name":"Dana","tone":"skeptical"}' EX 259200 │
│  GET persona:m1:u42  → the whole blob, one round-trip             │
│                                                                    │
│  As simple as it gets. The cost: to change ONE field you must     │
│   GET the whole thing, unmarshal, mutate, marshal, SET. (1.2       │
│   shows when that cost says "use a Hash instead".)                 │
└────────────────────────────────────────────────────────────────────┘
```

**Personality 2 — the atomic counter.** `INCR`, `INCRBY`, `DECR` operate on a String that holds an integer, and — because of Phase 0's single thread — they are atomic with zero locking. This is the backbone of counters and fixed-window rate limiters. Mindtickle's `mt-dashboard-api` rate limiter is exactly `INCR` + `EXPIRE` in a Lua script.

```
   Naive (WRONG — race):              Redis (RIGHT — atomic):
   v = GET counter    ← client A+B    INCR counter        ← A: returns 1
   v = v + 1            both read 5    INCR counter        ← B: returns 2
   SET counter v      ← both write 6   no lost update, ever, no lock
   LOST UPDATE: should be 7, is 6
```

**Personality 3 — the atomic flag / lock claim.** `SET key val NX EX 30` = "set this only if it doesn't exist, expire in 30s." The `NX` makes it a claim: the first caller wins, everyone else gets nil. This one command is the whole idempotency pattern (Phase 0's `ai-module-creation` `SetKeyIfNotExists`) and the seed of the distributed lock (Phase 3). `content-search-service` wraps it as `AddKeyBySetNXInRedis`.

Two more String tricks worth knowing because they surprise people: `APPEND` (append to a string in place), and `GETRANGE`/`SETRANGE` (read/write a byte range — a String can act like a random-access buffer). And `SET key val KEEPTTL` (update value but keep the existing expiry) — the fix for the classic "my SET reset the TTL and now my cache never expires" bug.

**The sentence to remember:** a String is a blob, a counter, or a flag — and the counter/flag personalities are atomic for free, which is why Redis owns rate-limiting and idempotency.

**The trap:** the JSON-blob-as-String for objects you update field-by-field. Every field update is a full GET+unmarshal+marshal+SET — the whole object crosses the wire twice. If you find yourself doing that, you wanted a Hash (1.2).

**Try this now:**
```bash
go run ./phase01_data_structures/string_vs_hash
# Watch the "update ONE field" section: String = 4 ops, Hash = 1.
```

---

## 1.2 — Hashes (objects done right)

**Why this matters:** the moment your value has fields you read or write independently, the String stops being free and the Hash starts. This is the exact fork in `mt-login-provider`: a session isn't blobbed, it's a Hash, so the service can delete one field (`HDEL`) or read one field (`HGET`) without dragging the whole session across the wire — and small hashes cost ~10× less memory than you'd guess (1.7).

A Hash is a map *inside* a value — field → value pairs under one key. It maps perfectly onto "an object":

```
┌───────────────────────────────────────────────────────────────────┐
│  Key: "u42|c7"  (mt-login-provider's userCompanyKey)              │
│  ┌──────────────┬───────────────────────────────────────────┐    │
│  │ field        │ value                                       │    │
│  ├──────────────┼───────────────────────────────────────────┤    │
│  │ token        │ "abc123"                                    │    │
│  │ ip           │ "10.0.0.1"                                  │    │
│  │ role         │ "manager"                                   │    │
│  │ sess-index   │ "c7|sess-a"   ← secondary-index fields      │    │
│  └──────────────┴───────────────────────────────────────────┘    │
│                                                                    │
│  HGETALL u42|c7        → whole object (mt-login's FetchInfo…)      │
│  HGET    u42|c7 role   → one field, no unmarshal                  │
│  HSET    u42|c7 role manager   → update one field in place        │
│  HDEL    u42|c7 ip     → drop one field (DeleteFieldsOfHKey)      │
└───────────────────────────────────────────────────────────────────┘
```

The commands you'll actually use: `HSET`/`HGET`/`HGETALL`/`HDEL`/`HEXISTS`/`HKEYS`/`HVALS`, and the atomic one that matters — **`HINCRBY`**, which increments a single field atomically (a per-field counter, incremented independently without touching the rest of the object). Mindtickle uses `HINCRBY` for exactly this in `coaching-user-management`'s `MigrateUserMissionDataWorker`: `HINCRBY <jobKey> completed 1` bumps a per-job "completed" counter as each fan-out subprocess finishes, then compares `HMGET jobKey total completed` to detect "all done" and trigger workflow completion — an atomic fan-out counter, no locks.

One important correction to a common assumption about `mt-login-provider`: this repo *reads* the session hash (`HGetAll` on a `userId|companyId` key) but does **not** write it. The write side lives in the coupled Node service `app-gatekeeper` (`src/models/userStore.ts`), which does `hmset(key, {userEmailId, attempt, company, expiryTime, lastActivityTrackedTime, ...})` then a separate `EXPIRE`. So the Hash is a *cross-service contract*: app-gatekeeper writes it, mt-login-provider reads it. (And note the TTL is applied as `HMSET` + separate `EXPIRE`, not an atomic `SET … EX` — a subtle window where a crash between the two leaves a hash with no expiry. Phase 2/5 territory.)

Here's the counterintuitive memory fact (1.7 has the mechanism): a small Hash — under `hash-max-listpack-entries` (128) fields, each value under 64 bytes — is stored as a **listpack**, a flat packed array, using up to 10× less memory than a hash table and far less than the equivalent set of top-level String keys. So "one Hash of 20 fields" beats "20 String keys" on memory *and* gives you `HGETALL` in one round-trip. That's why `mt-login-provider` uses a Hash for the session and Hash *fields* as a secondary index rather than a fleet of `sess:field:*` keys.

The trap that bites in production: **`HGETALL` on a huge Hash is O(N) and blocks the thread** (Phase 0.3). A session hash with 8 fields is nothing. A Hash you accidentally grew to 2 million fields is a `KEYS *`-grade incident. For big hashes, use `HSCAN`.

**The sentence to remember:** reach for a Hash the instant you address fields independently — it buys per-field read/write/delete *and* (when small) 10× memory efficiency over both blobs and scattered keys.

**The trap:** unbounded Hashes. `HGETALL` on a million-field hash is a stall. Bound the field count or `HSCAN`.

**In your codebase:** open `mt-login-provider/src/storage/sessison_store.go` — `FetchInfoFromUserCompanyIDKey` does `HGetAll(userCompanyKey)`; `DeleteSecondaryIndexHashKeyFields` does field-level `HDEL`. Ask: what would break if this were a JSON String instead? (Every session mutation would rewrite the whole blob, and concurrent field updates would clobber each other — the exact race Phase 0.1 warned about.)

---

## 1.3 — Lists (queues, and where their guarantees end)

**Why this matters:** a Redis List is the fastest way to get a working queue, and two Mindtickle services use exactly that — `content-search-service` (`AddInFifoQueue`/`RemoveFromFifoQueue`/`LengthOfQueue`) and, more interestingly, `asset-hub-analytics`, which uses a List as a *bounded sliding window* of interaction events that feeds a trending-assets leaderboard (you'll meet the full combo in 1.5). But a List queue has hard limits — no acknowledgement, no redelivery — and knowing precisely where those limits are is what tells you when to stay on a List versus escalate to Streams or Kafka. This is a decision Mindtickle has made service by service.

A List is a doubly-linked sequence of strings. You push and pop from either end, which gives you both a queue and a stack:

```
┌─────────────────────────────────────────────────────────────────────┐
│                      LPUSH ──►┌───┬───┬───┬───┐◄── RPUSH             │
│                    (head)     │ A │ B │ C │ D │     (tail)           │
│                      LPOP ◄───└───┴───┴───┴───┘───► RPOP             │
│                                                                       │
│  FIFO queue : RPUSH to tail, LPOP from head   (producer→consumer)    │
│  LIFO stack : LPUSH + LPOP  (both same end)                          │
│  content-search-service: AddInFifoQueue=RPUSH, RemoveFromFifoQueue=LPOP│
└─────────────────────────────────────────────────────────────────────┘
```

The upgrade that turns a toy into a real worker: **`BLPOP`/`BRPOP`** — the *blocking* pop. Instead of a worker busy-looping `LPOP` against an empty queue (burning CPU and Redis round-trips), `BLPOP` parks the connection and returns the instant an item arrives, or after a timeout.

```
   Busy-poll (WRONG):                  Blocking (RIGHT):
   for { v=LPOP; if nil {sleep 100ms}} BLPOP queue 5   ← sleeps in Redis,
   → 10 wasted round-trips/sec/worker     wakes on first push, 0 waste
```

Two more List patterns you'll see: **capped lists** — `LPUSH` + `LTRIM key 0 999` keeps only the newest 1000 entries (a bounded recent-events log). This is a live Mindtickle pattern twice over: `integrations-selfserve`'s rate limiter is literally `lpush(RateLimit|C|<cname>, epochMillis)` + `ltrim(key, 0, 43199)` (cap 43200), then it counts timestamps within second/minute/hour windows against the trimmed list; and `asset-hub-analytics` keeps a per-company FIFO event queue at a `MAXQUEUELENGTH` — when it overflows it `LPOP`s the oldest interaction and ages that asset out of the leaderboard. And **`LRANGE`** to read a window — but `LRANGE 0 -1` on a huge list is the same O(N) trap as `HGETALL`/`SMEMBERS`.

Now the critical part — **where a List queue's guarantees end.** When a worker `LPOP`s an item and then crashes before finishing, that item is *gone*. There is no acknowledgement, no "return it to the queue if I die," no consumer groups, no replay. That's not a bug; it's the data structure's scope.

```
┌────────────────────────────────────────────────────────────────────────┐
│  LIST queue          │ STREAMS (1.6)       │ KAFKA                       │
│  RPUSH/BLPOP         │ XADD/XREADGROUP     │ produce/consumer groups     │
│  no ack, no replay   │ ack + pending list  │ ack + offsets + retention   │
│  lose on crash       │ redeliver on crash  │ replay from any offset      │
│  → ephemeral work    │ → durable-ish work  │ → durable, high-throughput  │
│                      │   in one process    │   cross-service backbone    │
└────────────────────────────────────────────────────────────────────────┘
```

This is *why* Mindtickle runs durable, must-not-lose work on **Kafka** (the whole `missions-processors` world) and uses Redis Lists only for fast, in-process, loss-tolerant queuing. When you see a List queue, the question to ask is: "what happens if a worker dies holding an item?" If the answer is "we lose it and that's fine," a List is correct. If not, it's the wrong tool.

**The sentence to remember:** a List is the fastest ephemeral FIFO/LIFO queue you can get, `BLPOP` makes it a real worker, but the moment you need "don't lose it on crash," you've outgrown Lists.

**The trap:** using a List as a durable job queue. One worker crash = one silently dropped job. Datadog won't show you the gap because there's nothing to show.

**Try this now:**
```bash
go run ./phase01_data_structures/list_queue -jobs 8
# FIFO order preserved; BLPOP wakes the instant job-late is pushed.
```

---

## 1.4 — Sets (uniqueness, membership, and set algebra)

**Why this matters:** whenever the question is "is X in this group?" or "give me the whole group" or "what's in both groups?", a Set answers it in one atomic command with automatic deduplication. `mt-login-provider` uses a Set as the *index of a user's active sessions* — which is exactly how "log this user out everywhere" is implemented — and `content-search-service` exposes `AddInRedisSet`/`RemoveFromRedisSet`.

A Set is an unordered collection of unique strings. Adding a duplicate is a no-op — dedup is the whole point:

```
┌───────────────────────────────────────────────────────────────────┐
│  SADD user:u42:sessions sess-a sess-b sess-c                      │
│  SADD user:u42:sessions sess-b     → added 0 (already present)    │
│  SCARD user:u42:sessions           → 3   (not 4)                  │
│                                                                    │
│  "Invalidate ALL sessions for u42":                               │
│    SMEMBERS user:u42:sessions  → [sess-a, sess-b, sess-c]         │
│    DEL sess:sess-a; DEL sess:sess-b; DEL sess:sess-c              │
│    DEL user:u42:sessions       ← drop the index itself            │
└───────────────────────────────────────────────────────────────────┘
```

The commands: `SADD`/`SREM`/`SMEMBERS`/`SCARD`/`SISMEMBER` (O(1) membership test — "does this user have this session?"), and the algebra that runs *server-side* so data never leaves Redis: `SINTER` (in both), `SUNION` (in either), `SDIFF` (in A not B). "Modules assigned to both team A and team B" is one `SINTER`, computed in C on the server, not by pulling two lists into your service and looping.

Same O(N) trap, third time: **`SMEMBERS` on a huge set blocks.** The session-index set is tiny; a set of "all users who ever viewed course X" could be millions. Use `SSCAN` for anything you can't bound.

**The sentence to remember:** a Set gives you free uniqueness, O(1) membership tests, and server-side intersection/union/difference — reach for it for "the group of X" and "is X in the group."

**The trap:** `SMEMBERS` on an unbounded set. `SSCAN` it, or model it differently.

**Try this now:**
```bash
go run ./phase01_data_structures/set_dedup
# SADD dedup, the invalidate-all fan-out, SINTER/SUNION/SDIFF, and SSCAN on 10k.
```

---

## 1.5 — Sorted Sets (the power tool — learn this one cold)

**Why this matters:** if you master one structure beyond String and Hash, make it the Sorted Set. It's the Swiss-army knife: leaderboards, sliding-window rate limiters, delayed/scheduled queues, distributed lock tables, and time-ordered indexes are *all* the same underlying trick — **a Set where every member carries a floating-point score, kept permanently sorted by that score.** Mindtickle uses ZSets for two of these in production: `asset-hub-analytics` runs a real trending-assets **leaderboard**, and `course-qu-processors` uses one as a **per-language translation lock table** (score = lock-expiry). Once you see the pattern you'll spot ZSet-shaped problems everywhere.

```
┌────────────────────────────────────────────────────────────────────────┐
│  A Sorted Set: unique members, each with a score, sorted by score.      │
│                                                                          │
│  ZADD leaderboard 4820 "dana"  980 "raj"  6510 "mei"  3100 "sam"        │
│                                                                          │
│     score:   980      3100      4820      6510                          │
│     member:  raj  ──  sam   ──  dana  ──  mei      (auto-sorted)         │
│              rank0    rank1     rank2     rank3                          │
│                                                                          │
│  ZREVRANGE leaderboard 0 2 WITHSCORES  → top 3: mei, dana, sam          │
│  ZREVRANK  leaderboard "dana"          → 1  (2nd from top)              │
│  ZSCORE    leaderboard "dana"          → 4820                           │
│  ZINCRBY   leaderboard 100 "dana"      → 4920 (atomic bump + re-sort)   │
└────────────────────────────────────────────────────────────────────────┘
```

Under the hood it's a **skip list** + a hash map, so the operations are O(log N): `ZADD`, `ZSCORE`, `ZRANK`, `ZINCRBY` are all O(log N), and range queries are O(log N + M) for M results. **Critical insight most people miss: the sorting work happens on *write* (`ZADD`), not on read.** For a leaderboard where reads vastly outnumber writes, that's exactly the trade you want — the expensive work is paid on the rare path.

Now the three patterns, because they're the same tool wearing different hats:

**Pattern A — Leaderboard / ranking.** Score = points. `ZADD` to update, `ZREVRANGE` for the top N, `ZREVRANK` for "my rank." That's the entire feature. **This is live in `asset-hub-analytics`:** a per-company ZSet (member = assetId, score = cumulative trending score), `ZIncrBy` bumps an asset's score on each interaction, and `ZRevRangeWithScores` (wrapped as `ZSETTOPK`) reads the ranked "trending assets" above a minimum-score cutoff. The clever bit — how it makes trending mean *recently* trending — is the List+ZSet combo: a bounded FIFO List (1.3) holds the last N interaction events; when the list overflows, the oldest event is `LPOP`'d and its asset's ZSet score is *decremented* (`ZIncrBy` with a negative delta), aging stale assets out of the board. Leaderboard (ZSet) + sliding window (bounded List) = "what's hot right now," built from two structures.

**Pattern B — Sliding-window rate limiter (score = timestamp).** This is the accurate rate limiter, better than fixed-window `INCR`:
```
┌─────────────────────────────────────────────────────────────────────┐
│  score = request timestamp. Window = last 2 seconds.                │
│                                                                     │
│  1. ZREMRANGEBYSCORE key 0 (now-2s)   ← evict requests older than   │
│     window                              the window                  │
│  2. ZADD key now now                  ← record this request          │
│  3. ZCARD key                         ← how many in the window NOW?  │
│  4. EXPIRE key 2s                      ← idle keys self-clean         │
│  if ZCARD > limit → 429                                             │
│                                                                     │
│  Why better than fixed-window INCR: a fixed window resets on a      │
│  boundary, so 'limit' requests at 0.99s + 'limit' at 1.01s = 2x     │
│  limit in ~20ms. The sliding window counts the ACTUAL last 2s and   │
│  never double-bursts.                                               │
└─────────────────────────────────────────────────────────────────────┘
```
Honesty note: this is the *best* rate-limiter shape, but Mindtickle doesn't run it on a ZSet today. Production uses fixed-window Lua `INCR`+`EXPIRE` (`mt-dashboard-api`) and a legacy `LPUSH`/`LTRIM` list (`integrations-selfserve`); the one sliding-window `deque` that exists (`ctara`) is in-process Python, not Redis. Worth knowing the ZSet version — it's the upgrade path when fixed-window's boundary burst bites.

**Pattern C — Distributed lock table with self-expiry (score = lock-expiry time).** This is the real Mindtickle ZSet pattern, and it's subtler than the textbook delayed queue. `course-qu-processors` translates a learning object into many languages concurrently and must not let two workers translate the *same language* at once. Key: `translate:inprogress:<moduleId>:<loId>`. Each **member** is a language code (`fr`, `de`, …); each **score** is the Unix timestamp when that language's lock *expires*:

```
┌─────────────────────────────────────────────────────────────────────┐
│  key = translate:inprogress:m1:lo9      (one key per module+LO)      │
│    member "fr" → score 1720000030   (fr lock valid until t=…030)    │
│    member "de" → score 1720000030                                   │
│                                                                     │
│  acquire/renew a language lock : ZADD key (now+ttl) <lang>          │
│  reap expired locks            : ZREMRANGEBYSCORE key -inf <now>    │
│  "is fr still being translated?": ZSCORE key fr  (present & > now?) │
│  which langs are locked now     : ZRANGEBYSCORE key <now> +inf      │
└─────────────────────────────────────────────────────────────────────┘
```

Why a ZSet and not a plain Set or N `SETNX` keys? Because the *score carries the expiry*, so one `ZREMRANGEBYSCORE ... -inf now` atomically reaps every lock a crashed worker left behind — no per-key TTL bookkeeping, no orphaned locks. The identical scheme is reused across `assessment-service` and `ce-course-qu` (the Java side via Redisson's `RScoredSortedSet`) — a shared cross-service lock convention. (This is a preview of Phase 3's locking, done with a ZSet instead of `SETNX`.)

The *pure* delayed-queue form (score = future run-time, `ZRANGEBYSCORE key 0 now` to pop due items) is a real pattern but — Compass-confirmed — Mindtickle doesn't currently use it; the translation-lock variant above is what production actually runs.

**The sentence to remember:** a Sorted Set is "a Set ordered by a number you choose" — make the number a score for leaderboards, a timestamp for sliding windows, or a due-time for schedules, and one structure solves all three.

**The trap:** `ZRANGEBYSCORE` returning half a million members blocks the event loop for tens of ms. Always bound with `LIMIT offset count` and paginate.

**Try this now:**
```bash
go run ./phase01_data_structures/sorted_set_ratelimit -limit 5 -window 2s -n 12 -gap 200ms
# First 5 allowed, next rejected, then as old entries slide out, allowed again.
```

---

## 1.6 — The specialized three: Streams, HyperLogLog, Bitmaps

**Why this matters:** these three are the "I didn't know Redis could do that" structures. Compass-confirmed, **no core Mindtickle service uses any of them today** — which makes this the "when you'd reach for it, and why you haven't needed to" section. Knowing they exist means you won't reinvent them badly, and knowing why they're unused tells you something about the architecture.

**Streams (`XADD`/`XREADGROUP`)** — an append-only log with consumer groups, acknowledgements, and a pending-entries list. It's "Kafka-lite inside Redis": multiple consumers in a group split the load, each entry must be `XACK`'d, and unacked entries can be redelivered to another consumer if one dies. It fills the exact gap 1.3 identified in Lists (no ack/replay). **Why Mindtickle doesn't use it:** the org already runs Kafka (AWS MSK) as its durable event backbone, so the "durable queue" need is already met by a purpose-built, higher-throughput, multi-service system. Streams would only make sense for a self-contained durable queue that doesn't warrant a Kafka topic — a real but narrow niche.

**HyperLogLog (`PFADD`/`PFCOUNT`/`PFMERGE`)** — probabilistic cardinality estimation. It answers "how many *unique* X?" using a fixed **~12 KB regardless of how many uniques**, with ~0.81% error, and it does *not* store the elements. The trade: you get the count, but you can never list the members.

```
┌──────────────────────────────────────────────────────────────────────┐
│  "Unique learners who viewed course C101 today?"                      │
│                                                                       │
│  SET approach:  SADD every userId → SCARD                             │
│     exact, BUT memory grows with cardinality (stores every id)        │
│     measured: 100,000 users ≈ 5,442 KB                                │
│                                                                       │
│  HLL approach:  PFADD every userId → PFCOUNT                          │
│     ~0.81% error, memory FLAT at ~12-14 KB forever                    │
│     measured: 100,000 users ≈ 14 KB, estimate 100,165 (0.17% off)     │
│                                                                       │
│                        SET / HLL memory ratio ≈ 387x                  │
│                                                                       │
│  PFMERGE: union of daily HLLs → weekly/monthly uniques, still ~12KB  │
└──────────────────────────────────────────────────────────────────────┘
```

This is the textbook tool for DAU/MAU/unique-views analytics — the kind of metric Mindtickle's analytics services compute. That it's *not* used in Redis suggests those counts are computed in the analytics/warehouse path instead; worth knowing HLL exists the next time someone proposes a giant Set just to count uniques.

**Bitmaps (`SETBIT`/`GETBIT`/`BITCOUNT`)** — a String addressed as an array of bits. Bit N = user N. "Has user N done X?" is one bit. "How many users did X today?" is `BITCOUNT`. Daily active users for 10 million users fits in ~1.2 MB (10M bits). `BITOP AND/OR` across daily bitmaps gives retention cohorts ("active both Monday and Tuesday"). Same "count/track membership over a dense integer id space" niche as HLL, but exact and listable-by-position — the trade is it needs dense integer ids (user *numbers*, not UUIDs).

**The sentence to remember:** Streams = Kafka-lite (unused because real Kafka exists), HyperLogLog = count-uniques-in-12KB (unused because analytics lives elsewhere), Bitmaps = one-bit-per-user flags — all three are "you'll know it when you need it" tools.

**The trap:** building a giant Set purely to `SCARD` it for a unique count. If you never list the members and ~1% error is fine, that's an HLL and you just saved ~99% of the memory.

**Try this now:**
```bash
go run ./phase01_data_structures/hll_vs_set -unique 100000
# See the 387x memory gap and sub-1% error for yourself.
```

---

## 1.7 — Encoding: the 10× memory switch nobody tells you about

**Why this matters:** two Redis instances with identical data can differ 10× in memory depending on one thing — whether the values are small enough to use the compact *listpack* encoding. This directly connects to Phase 0's memory incidents (INCP-520): understanding encoding is understanding your memory bill and your eviction risk.

Redis stores each structure in one of two ways depending on size:

```
┌───────────────────────────────────────────────────────────────────────┐
│  SMALL collection  → LISTPACK (flat packed array, ~10x less memory)    │
│  LARGE collection  → hashtable / skiplist / quicklist (pointers,        │
│                       more memory, but O(1)/O(log N) at scale)          │
│                                                                         │
│  The switch is automatic and one-way (grows → converts, never back):   │
│    Hash: hash-max-listpack-entries=128,  hash-max-listpack-value=64B   │
│    ZSet: zset-max-listpack-entries=128,  zset-max-listpack-value=64B   │
│    List: list-max-listpack-size=128                                    │
│    Set (ints): set-max-intset-entries=512                              │
└───────────────────────────────────────────────────────────────────────┘
```

You saw this live in the `string_vs_hash` demo: `OBJECT ENCODING sess:hash:u42 → listpack`. The 5-field session hash is a listpack — tiny. Add a 129th field or a value over 64 bytes and it silently converts to a full hashtable, and memory jumps. This is why the "break a big object into small hashes" advice exists, and why blindly widening a hash has a memory cliff.

**The sentence to remember:** small collections are ~10× cheaper because they use listpack encoding; cross the entries/value threshold and Redis silently upgrades to a pointer-based structure with a memory jump.

**The trap:** assuming memory scales linearly with data. It has a cliff at the listpack thresholds. Check `OBJECT ENCODING` when memory surprises you.

**Try this now:** `docker exec redis-study redis-cli OBJECT ENCODING sess:hash:u42` (after the string_vs_hash demo) → `listpack`.

---

## 1.8 — Key naming (the convention that keeps a shared cluster sane)

**Why this matters:** on Phase 0's shared clusters, keys from dozens of services live in one keyspace. Without a naming convention you get collisions, un-greppable keys, and no way to reason about ownership or memory. Mindtickle's real keys show the convention.

There is **no single company-wide standard** at Mindtickle (Compass-verified — several conventions coexist), but the most common is **colon-delimited namespaces**, most-general to most-specific:

```
   object-type : sub : id : id                (colon — the common style)
   ─────────────────────────────────────────────────────────────────────
   translate:inprogress:<moduleId>:<loId>     (course-qu-processors, fmt.Sprintf)
   mem:session:buffer:<userId>:<feat>:<sess>  (ai-tutor)
   invite_email_lock:<companyId>:<tutorialId> (ai-tutor lock)

   Pipe-delimited scoped keys — the GraphQL BFF layer (customer-experience-gql,
   readiness-gql):
   CK|<url>|<dataHash>          Cache Key (generic HTTP response)
   SK|<scope>|md5(url)|<hash>   Scope Key (for scope-based bulk invalidation)
   MSK|md5(scopes)|md5(url)|... Multi-Scope Key
   Scope|<scope>               tracks which keys belong to an invalidation scope

   Company scoping = interpolate the id VALUE (NOT a literal "COMPANY_" prefix):
   game|<eid>|company|<cid>|new            (notification-domain-service)
   <appName>:cache:<companyId>:ONLY_ME:<userId>   (ilt-service)

   Cluster hash-tags — a SHARDING mechanism, not a naming one:
   {<companyId>}<key>   forces all a tenant's keys onto one slot for bulk MGET
                        (external-sharing-service)
```

Why it matters concretely: a good prefix makes `SCAN MATCH translate:inprogress:*` possible (find all translation locks), makes memory attributable per service, and prevents one service's keys from colliding with another's. Interpolating the tenant/company id into the key is how a multi-tenant platform keeps one customer's cache from leaking into another's — a correctness and security property, not just tidiness. And the `{companyId}` **hash-tag** is a distinct trick: everything in `{...}` decides the cluster slot, so a whole tenant's keys land on one shard and can be fetched in a single cross-slot-safe `MGET` (Phase 4).

**The sentence to remember:** namespace your keys `type:sub:id` and inline the tenant id — and know the two Mindtickle-specific twists: the pipe-delimited `CK|/SK|/MSK|` cache keys in the GraphQL BFF, and `{companyId}` hash-tags for shard co-location.

**The trap:** unprefixed keys like `u42` or `count`. On a shared cluster they collide across services and are impossible to attribute or `SCAN`. Second trap: assuming there's ONE convention — there isn't; match the one already in the service you're editing.

**In your codebase:** grep for Redis key construction in any service and check: is there a type prefix? is the tenant id interpolated? Could two services collide? (You'll find colon-namespacing in the Go fleet, the `CK|/SK|/MSK|/Scope|` family in `customer-experience-gql`/`readiness-gql`, and `{companyId}` hash-tags in `external-sharing-service`.)

---

## 🧪 Hands-on lab — the exercises that teach Phase 1

Setup:
```bash
cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d && docker exec redis-study redis-cli PING   # → PONG
```

- [ ] **E1. Strings: the three personalities.**
  - Run: `docker exec redis-study redis-cli SET blob '{"a":1}'; ... INCR counter; ... SET flag 1 NX EX 30; ... SET flag 2 NX EX 30`
  - Expected: the second `SET flag ... NX` returns nil (key exists) — the claim was already taken.
  - Teaches: blob vs atomic counter vs atomic flag, all on the String type.

- [ ] **E2. String vs Hash, measured.**
  - Run: `go run ./phase01_data_structures/string_vs_hash`
  - Expected: field update = 4 ops (String) vs 1 (Hash); encoding = `listpack`.
  - Teaches: when the JSON-blob-String costs you and the Hash pays off.

- [ ] **E3. Break it — WRONGTYPE.**
  - Run: `docker exec redis-study redis-cli SET s hello; docker exec redis-study redis-cli LPUSH s x`
  - Expected: `WRONGTYPE Operation against a key holding the wrong kind of value`.
  - Teaches: the value's type constrains the legal commands — the keyspace is typed.

- [ ] **E4. Hash field counters.**
  - Run: `docker exec redis-study redis-cli HINCRBY post:1 views 1; ... HINCRBY post:1 likes 1; ... HINCRBY post:1 views 1; ... HGETALL post:1`
  - Expected: `views=2, likes=1` — two independent atomic counters in one object.
  - Teaches: `HINCRBY` = per-field atomic counter without separate keys.

- [ ] **E5. List FIFO + blocking worker.**
  - Run: `go run ./phase01_data_structures/list_queue -jobs 8`
  - Expected: jobs consumed in exact push order; `BLPOP` wakes the instant `job-late` is pushed.
  - Teaches: RPUSH/LPOP FIFO and why `BLPOP` beats busy-polling.

- [ ] **E6. Break it — the List queue loses a job on crash.**
  - Run: `docker exec redis-study redis-cli RPUSH q j1 j2 j3; docker exec redis-study redis-cli LPOP q` (pretend the worker crashes here) then `docker exec redis-study redis-cli LLEN q`
  - Expected: `LLEN=2` — j1 is gone, unrecoverable. No ack, no redelivery.
  - Teaches: exactly where a List queue's guarantees end (→ Streams/Kafka).

- [ ] **E7. Set uniqueness + algebra.**
  - Run: `go run ./phase01_data_structures/set_dedup`
  - Expected: dup absorbed (SCARD=3), SINTER/SUNION/SDIFF results, SSCAN over 10k.
  - Teaches: dedup, the invalidate-all fan-out, server-side set math.

- [ ] **E8. Sorted Set leaderboard by hand.**
  - Run: `docker exec redis-study redis-cli ZADD lb 100 raj 250 dana 175 sam; ... ZREVRANGE lb 0 -1 WITHSCORES; ... ZREVRANK lb sam; ... ZINCRBY lb 200 raj; ... ZREVRANGE lb 0 0`
  - Expected: dana top; after +200, raj (300) becomes top.
  - Teaches: ZADD/ZREVRANGE/ZREVRANK/ZINCRBY — the whole leaderboard feature.

- [ ] **E9. Sorted Set sliding-window rate limiter.**
  - Run: `go run ./phase01_data_structures/sorted_set_ratelimit -limit 5 -window 2s -n 12 -gap 200ms`
  - Expected: 5 allowed, burst rejected, then allowed again as the window slides.
  - Teaches: score=timestamp = exact sliding window; no boundary double-burst.

- [ ] **E10. HyperLogLog vs Set memory.**
  - Run: `go run ./phase01_data_structures/hll_vs_set -unique 100000`
  - Expected: ~0.1–0.8% error, ~387x memory ratio (5442 KB vs 14 KB).
  - Teaches: when to trade exactness for a flat 12 KB.

- [ ] **E11. Bitmaps for daily-active flags.**
  - Run: `docker exec redis-study redis-cli SETBIT dau:2026-07-13 42 1; ... SETBIT dau:2026-07-13 1000000 1; ... BITCOUNT dau:2026-07-13; ... STRLEN dau:2026-07-13`
  - Expected: BITCOUNT=2; STRLEN ~125 KB (bit 1,000,000 forces the string to grow).
  - Teaches: one bit per user; `BITCOUNT` = active count; watch the sparse-id memory cost.

- [ ] **E12. Encoding cliff.**
  - Run: `docker exec redis-study redis-cli DEL h; docker exec redis-study redis-cli HSET h f v; docker exec redis-study redis-cli OBJECT ENCODING h` (→ listpack). Then add a >64-byte value: `docker exec redis-study redis-cli HSET h big "$(python3 -c 'print("x"*100)')"; docker exec redis-study redis-cli OBJECT ENCODING h`
  - Expected: `listpack` → `hashtable` after the big value.
  - Teaches: the automatic, one-way encoding upgrade and its memory jump.

---

## 🏢 Mindtickle anchor — things to check in the codebase

1. **The session as Hash + Set, split across two services.** Open `mt-login-provider/src/storage/sessison_store.go` and `src/dao/redis_store.go`. Find `FetchInfoFromUserCompanyIDKey` (`HGetAll`), `DeleteSecondaryIndexHashKeyFields` (`HDEL` of specific fields), `InvalidateAllSessions` (`GetAllValuesFromSet` → delete each → `DeleteKeys`). Then note what this repo does NOT contain: the `HMSET` that creates the session hash — that's in `app-gatekeeper/src/models/userStore.ts` (Node). Questions: why is the session a Hash + a Set index rather than one JSON String holding a list? What does `HDEL`-of-one-field buy that a blob can't? (Field-level mutation without read-modify-write races — Phase 0.1.) And: what's the risk of the write side doing `HMSET` then a *separate* `EXPIRE` (app-gatekeeper) versus one atomic `SET … EX`? (A crash between them = a session hash with no TTL = an INCP-520-shaped unevictable key, Phase 0.)

2. **A multi-structure CacheClient in one file.** In `content-search-service`, `package/helper/CacheClient.go` exposes `AddInFifoQueue`/`RemoveFromFifoQueue`/`LengthOfQueue` (List: RPUSH/LPOP/LLEN), `AddInRedisSet`/`RemoveFromRedisSet` (Set: SADD/SREM), and `AddKeyBySetNXInRedis` (String: SETNX). Question: for its FIFO queue, what happens to an item if the consumer dies between `LPOP` and finishing the work? Is that acceptable for what this queue carries? (If not, it wants Streams/Kafka — 1.3.)

3. **A Sorted Set as a per-language translation lock table.** In `course-qu-processors` — `src/infrastructure/redisWriteClient/RedisWriteClient.go` and `src/domain/TranslationOrchestrator/utils/TranslationRedisUtil.go` — find the key `translate:inprogress:<moduleId>:<loId>` and the ops `ZAdd({Score: now+ttl, Member: lang})`, `ZRemRangeByScore(-inf, now)`, `ZScore(key, lang)`, `ZRangeByScore(now, +inf)`. Questions: how does `ZScore(key, "fr")` answer "is French already being translated?" What does `ZRemRangeByScore(-inf, now)` reap in one atomic call, and why is that cheaper than N per-key TTLs? (The score IS the expiry.) Bonus: the same scheme appears in `assessment-service` and in `ce-course-qu` via Redisson `RScoredSortedSet` — why would three services converge on a ZSet lock table instead of `SETNX`? (Atomic bulk-reap of a crashed worker's locks — a Phase 3 preview.)

4. **The buyer persona as a JSON String.** Re-open `missions-processors/processors/ai_roleplay_helper/ai_roleplay_helper.go` (`SetBuyerPersonaForCache` → `SetKey(key, json, PREV_INSTR_TTL)`). Question: this is a String blob, not a Hash — is that the right call here? (Argue it: the persona is read/written whole, never field-by-field, and it's opaque to the cache layer → String is correct. Contrast with the session, which is mutated field-by-field → Hash. This is the 1.1-vs-1.2 decision, live in two of your services.)

---

## ✅ Checkpoint 1 — answer in your own words

**Q1.** A teammate models a shopping-cart-style "modules assigned to a user" as a JSON array in a String: `GET`, unmarshal, append, marshal, `SET` on every assignment. Two assignments race. Walk the exact interleaving that loses one, name the structure that fixes it in one atomic command, and write that command.

**Q2.** You need a rate limiter: max 100 requests per minute per company. Compare the fixed-window `INCR`+`EXPIRE` approach (mt-dashboard-api's actual choice) with the sorted-set sliding-window approach (E9). Show the specific input that makes fixed-window allow ~200 requests in a ~2-second span, and explain why the ZSet version can't. Then argue *why mt-dashboard-api might still correctly choose fixed-window* (hint: cost — count the bytes and ops per request for each).

**Q3.** "How many unique learners opened this course this month?" Design two solutions — a Set and a HyperLogLog — and give the memory for 5 million uniques in each (use the ratios from E10). State the one question whose answer decides between them. (Hint: does the product need to *list* those learners, or just count them?)

**Q4.** Walk through `course-qu-processors`' ZSet translation-lock end-to-end for key `translate:inprogress:m1:lo9`: French translation starts (`ZADD` with what score?), a duplicate "translate fr" event arrives (`ZScore` check — what tells you it's still locked?), French finishes (`ZRem fr`), and a *German* worker crashes mid-run leaving its `de` member behind. What single command reaps the stale `de` lock, and what score value makes that reaping correct? Why would a plain Set (no scores) be unable to reap the crashed worker's lock?

**Q5.** A colleague says "let's store each user's session as 6 separate String keys (`sess:u42:token`, `sess:u42:ip`, ...) so we can expire them independently." Give two reasons `mt-login-provider`'s single-Hash approach is better (hint: one is memory/encoding from 1.7, one is atomicity/round-trips), and the one scenario where the separate-keys approach would actually win.

**Q6.** You `HGETALL` a hash in a hot path and p99 latency quietly climbs over three months with no deploys. Given 1.2 and 1.7, what are the two independent things that could be growing, how do you confirm each (name the commands), and what's the fix for each?

**Q7.** Design task: a "trending assets" feature — the top 10 assets per company, weighted toward *recent* activity. Which structure records the ranking, which commands record a view and read the top 10, and how do you make an asset's score *decay* as its activity gets old (so all-time winners don't dominate forever)? Design it, THEN open `asset-hub-analytics` (`src/infrastructure/CacheClient.go`, `src/domain/trendingAssets/core/TrendingAssetsTasksFacade.go`) and compare: they use a ZSet leaderboard (`ZIncrBy`/`ZRevRangeWithScores`) fed by a bounded FIFO List — when the list overflows, the oldest event's asset gets a *negative* `ZIncrBy`. Did you invent the same List+ZSet combo, or something different? Which is simpler to reason about?

---

## References & Further Learning

**Must-read (in order):**
- 📄 [Redis Sorted Sets — official data-types guide](https://redis.io/docs/latest/develop/data-types/sorted-sets/) — the canonical reference for the most important structure in this phase. (15 min) Read BEFORE E8–E9.
- 📄 [How to Use Redis Sorted Sets for Leaderboards and Rankings](https://oneuptime.com/blog/post/2026-01-21-redis-sorted-sets-leaderboards/view) — leaderboard, rate-limit, and delayed-queue patterns with the "sort on write, not read" insight spelled out. (12 min) Read alongside 1.5.
- 📄 [How to Use Redis Hashes for Memory-Efficient Storage](https://oneuptime.com/blog/post/2026-01-21-redis-hashes-memory-efficient/view) — the listpack encoding thresholds and the blob-vs-hash memory argument, concretely. (10 min) Read with 1.2 and 1.7.
- 📄 [Rate Limiter Using Sorted Set in Redis — Phyllo Engineering](https://medium.com/phyllo-engineering-blog/rate-limiter-using-sorted-set-in-cache-redis-bee5d939448d) — the exact sliding-window recipe E9 implements, from a production team. (10 min)

**Deep dives (when the basics are solid):**
- 📄 [HyperLogLogs in Redis — thoughtbot](https://thoughtbot.com/blog/hyperloglogs-in-redis) — the clearest intuition for how 12 KB estimates millions of uniques (the harmonic-mean-of-leading-zeros trick), no heavy math. (12 min) Read after E10.
- 📄 [Redis Memory Optimization — official docs](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/memory-optimization/) — the full listpack/intset threshold table and how to tune them. (20 min) The page you'll open when the memory bill spikes.
- 📄 [Redis Ziplist/Listpack explained](https://redis.io/glossary/redis-ziplist/) — what the compact encoding actually is at the byte level. (8 min)
- 📚 *Redis in Action* (Josiah Carlson), Chapters 3–4 — the definitive walk-through of all structures with real use cases (rate limiting, autocomplete with ZSets, ad targeting with Sets). Only these chapters for now.

**Command reference (bookmark):**
- [redis.io/commands](https://redis.io/commands/) filtered by data type — every command with its Big-O. The O(N) warnings are your production guardrails.
- [Redis data types intro](https://redis.io/docs/latest/develop/data-types/) — the one-page map of all types.

---

## Cheatsheet — Phase 1

```
PICK THE STRUCTURE (the decision that deletes code)
  whole opaque object, read/write together      → STRING (JSON blob) + TTL
  atomic counter / rate-limit (fixed window)     → STRING: INCR + EXPIRE
  atomic claim / idempotency / lock seed         → STRING: SET k v NX EX
  object with independently-addressed fields     → HASH: HSET/HGET/HDEL/HINCRBY
  ephemeral FIFO/LIFO queue (loss-OK)            → LIST: RPUSH + LPOP/BLPOP
  uniqueness / membership / "the group of X"     → SET: SADD/SISMEMBER/SMEMBERS
  "in both / either / neither" group             → SET: SINTER/SUNION/SDIFF
  ranking / leaderboard                          → ZSET: ZADD + ZREVRANGE/ZREVRANK
  sliding-window rate limit (accurate)           → ZSET: score=timestamp
  delayed/scheduled queue, job-in-progress marker→ ZSET: score=due-time / ZScore dedup
  durable queue with ack/replay                  → STREAMS (or Kafka — MT uses Kafka)
  count uniques at scale, ~1% error OK           → HYPERLOGLOG: PFADD/PFCOUNT (~12KB)
  one flag per dense-integer id                  → BITMAP: SETBIT/BITCOUNT/BITOP

O(N) COMMANDS THAT BLOCK → SCAN VARIANT
  KEYS      → SCAN        HGETALL(huge) → HSCAN
  SMEMBERS  → SSCAN       ZRANGEBYSCORE(huge) → add LIMIT offset count
  LRANGE 0 -1(huge)       → bound the range

ATOMIC-FOR-FREE (single thread, no lock)
  INCR/INCRBY/DECR   HINCRBY   ZINCRBY   SETNX   SET..NX   ZADD

ENCODING (the 10x memory switch, auto + one-way)
  small → listpack (cheap);  past threshold → hashtable/skiplist (jump)
  hash/zset: max-listpack-entries=128, max-listpack-value=64B
  set(ints): set-max-intset-entries=512
  check: OBJECT ENCODING <key>

KEY NAMING (shared-cluster hygiene — no single MT standard, colon most common)
  type:id:sub:field   e.g. translate:inprogress:<mod>:<lo> ,
                           mem:session:buffer:<user>:<feat>:<sess> ,
                           invite_email_lock:<company>:<tutorial>
  interpolate the TENANT id VALUE into the key (multi-tenant isolation);
    NOTE: no literal "COMPANY_" prefix in real keys — the id value is inlined
  GraphQL BFF layer: pipe-delimited CK|url|hash , SK|scope|... , MSK|... , Scope|scope
  cluster hash-tags {companyId}key → co-locate a tenant's keys on one shard (MGET)

MINDTICKLE STRUCTURE MAP (Compass-verified)
  String(JSON blob = DEFAULT) → missions-processors persona; mt-login OAuth client;
                                notification-domain-service entity cache
  Hash    → session hash (WRITE app-gatekeeper/Node, READ mt-login-provider);
            course-qu-processors partial-field HSet; HINCRBY fan-out counter
            in coaching-user-management MigrateUserMissionDataWorker
  Set     → mt-login-provider session index (invalidate-all); content-search-service
  List    → asset-hub-analytics bounded FIFO (feeds leaderboard); content-search-service;
            integrations-selfserve LPUSH/LTRIM legacy rate limiter
  ZSet    → asset-hub-analytics trending leaderboard (ZIncrBy/ZRevRange);
            course-qu-processors per-language translation LOCK (score=expiry)
  Pub/Sub → content-center-service dispatch (Phase 0); hifli newsfeed
  Streams/HLL/Bitmap/Geo → NOT used (Kafka owns streaming; analytics elsewhere)
  BLPOP/BRPOP → not used in prod (workers drain via LPOP or Kafka)
```

---

*Next: Phase 2 — Caching Patterns. Cache-aside vs write-through vs write-behind, the thundering-herd / cache-stampede problem and singleflight, and invalidation strategies — anchored to Mindtickle's three-layer company-settings cache and the CE `cacheable:false` bug. Say `next`.*

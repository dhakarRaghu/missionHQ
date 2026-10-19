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
│  1.9  Transactions   — MULTI/EXEC with no rollback, WATCH and retries,   │
│                        cluster slots, AOF, the 8.10.2 ACL fix            │
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

## 1.9 — Transactions (what EXEC promises, and what it does not)

**Why this matters:** sections 1.1 to 1.5 made each read-modify-write one command. Some changes need two commands, or a check that no single command offers. Then teams reach for `MULTI` and `EXEC`. Most engineers expect a transaction to roll back on an error, as a SQL transaction does. Redis does not roll back. Code written on that belief counts twice, or leaves half a change behind.

**The mental model.** A transaction is a queue of commands on one connection. `MULTI` starts the queue. Each later command replies `QUEUED` and does not run yet. `EXEC` runs the whole queue in order, and no command from another client runs in the middle. `WATCH` adds one condition: `EXEC` runs only if no watched key changed after the `WATCH`.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One transaction on the single thread, client A with WATCH                │
├──────────────────────────────────────────────────────────────────────────┤
│ client A                 Redis thread                client B            │
│ WATCH tx:bal ──────────► A now watches tx:bal                            │
│ GET tx:bal ────────────► 100                                             │
│ MULTI ─────────────────► OK, A queues from now on                        │
│ SET tx:bal 70 ─────────► QUEUED, nothing runs yet                        │
│                          GET tx:log ◄─────────────── B runs as usual     │
│ EXEC ──────────────────► runs SET, no command of B in between            │
│                                                                          │
│ If B had written tx:bal before EXEC, EXEC replies a null array and runs  │
│ nothing. EXEC also drops the watch, so A starts again at WATCH.          │
└──────────────────────────────────────────────────────────────────────────┘
```

You might expect `EXEC` to be "all or nothing". It is "nothing in between". These are two different promises. Elite-storage 3.1 separates them: atomicity is about what a failure leaves behind, and isolation is about other clients. `EXEC` gives isolation. It gives all or nothing only before it starts. A client that disconnects before `EXEC` runs nothing.

### What EXEC promises, and what it does not

| Question | Answer, Redis 8.10.2 and Valkey 9.1.2 | Evidence |
|---|---|---|
| Do the queued commands run in order, with no other client in between? | Yes | Transactions docs, "two important guarantees". `execCommand` calls each queued command in turn, `src/multi.c:185-246` |
| If one command fails at run time, are the others undone? | No. Redis has no rollback | E13 part a, measured |
| If one command fails while it is queued, does any command run? | No. `EXEC` replies `EXECABORT` | E13 part b, measured |
| Can a queued command use the reply of an earlier one? | No. Every reply comes back at `EXEC` | Each queued command replies `QUEUED` |
| Can `BLPOP` wait inside `EXEC`? | No. `EXEC` sets `CLIENT_DENY_BLOCKING`, so it returns at once | `src/multi.c:163-164` |
| Do the AOF and the replicas get the writes as one unit? | Yes, wrapped in `MULTI` and `EXEC` | E13 AOF check below, measured |

The docs give the reason for no rollback. Rollback "would have a significant impact on the simplicity and performance of Redis".

### Two kinds of error

An error has two possible times, and the time decides the outcome.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Two kinds of error, two outcomes                                         │
├──────────────────────────────────────────────────────────────────────────┤
│ error found while queueing         │ error found while EXEC runs         │
│ unknown command, wrong arity,      │ WRONGTYPE, value not an integer,    │
│ ACL denied, MOVED, OOM             │ any error found in the data         │
│ ───────────────────────────────────┼──────────────────────────────────── │
│ reply: the error, not QUEUED       │ reply at queue time: QUEUED         │
│ sets CLIENT_DIRTY_EXEC             │ sets no flag                        │
│ EXEC: -EXECABORT, nothing runs     │ EXEC: every command runs, this one  │
│                                    │ replies its error, no rollback      │
└──────────────────────────────────────────────────────────────────────────┘
```

The mechanism, step by step, from the Redis 8.10.2 source:

1. While a client is in `MULTI`, Redis checks each command before it replies `QUEUED`. It checks the name, the number of arguments, ACL, the cluster slot and the memory limit.
2. A failed check calls `flagTransaction()`, which sets `CLIENT_DIRTY_EXEC` on the client. This is in `src/server.c:4277-4287` and `src/multi.c:86-89`.
3. A dirty transaction stores no more queued commands, to save memory. This is in `src/multi.c:36-41`.
4. `EXEC` on a dirty transaction replies `-EXECABORT Transaction discarded because of previous errors.` and runs nothing. Redis has done this since 2.6.5.
5. A command that passes the checks can still fail when it runs. `WRONGTYPE` is the common case. Its error becomes its own entry in the `EXEC` reply, and the next command runs.

This is the real output of E13 parts a and b on the lab server:

```text
a. EXEC-TIME ERROR: one command fails, the others still apply
   MULTI                      → OK
   INCR tx:n                  → QUEUED
   LPOP tx:a                  → QUEUED
   SET tx:b done              → QUEUED
   EXEC                       → [1 | (error) WRONGTYPE Operation against a key holding the wrong kind of value | OK]
   after EXEC: tx:n=1 tx:b=done → no rollback: true
   go-redis TxPipelined: err="WRONGTYPE Operation against a key holding the wrong kind of value", yet tx:n=2 tx:b=again

b. QUEUE-TIME ERROR: EXEC runs nothing
   MULTI                      → OK
   SET tx:c 1                 → QUEUED
   INCR                       → (error) ERR wrong number of arguments for 'incr' command
   EXEC                       → (error) EXECABORT Transaction discarded because of previous errors.
   after EXEC: EXISTS tx:c=0 → whole transaction discarded: true
```

The last line of part a is the trap in client code. go-redis `TxPipelined` returns the error of the first failed command. The source says so in `tx.go:124` at v9.5.1, the version in this course's `go.mod`. So `err` is not nil, and the `INCR` and the `SET` still ran.

```go
// WRONG: treats any error as "nothing happened" and sends the queue again.
for {
	_, err := rdb.TxPipelined(ctx, func(p redis.Pipeliner) error {
		p.Incr(ctx, "tx:n")
		p.LPop(ctx, "tx:a")
		p.Set(ctx, "tx:b", "again", 0)
		return nil
	})
	if err == nil {
		break
	}
	// The WRONGTYPE from LPOP lands here, after INCR already ran.
	// Each loop adds 1 to tx:n again.
}
```

```go
// RIGHT: only an aborted EXEC means that nothing ran.
cmds, err := rdb.TxPipelined(ctx, fn)
var rerr redis.Error // a reply from Redis, not a network error
switch {
case err == nil:
	// Every command ran, and none failed.
case errors.Is(err, redis.TxFailedErr):
	// A watched key changed. Nothing ran. Retry from WATCH.
case strings.HasPrefix(err.Error(), "EXECABORT"):
	// A queue-time error. Nothing ran. A retry fails the same way: fix the code.
case errors.As(err, &rerr):
	// EXEC ran. Read cmds[i].Err() for each command. Do not send the queue again.
default:
	// A network error. EXEC may or may not have run. See the next paragraph.
}
_ = cmds
```

All five branches were run against the lab server with go-redis v9.5.1 on 2026-10-19. A 100 ms read timeout during `CLIENT PAUSE` produced the network error.

A network error after the client sent `EXEC` is a third case. The client cannot know whether `EXEC` ran. Treat it like any write with an unknown result: make the change idempotent, or read the state before you retry.

### WATCH, one level down

`WATCH` is optimistic locking. Optimistic means the client takes no lock. It checks at the end whether another client wrote, and retries if one did. Elite-storage 3.6 shows the same idea with a version column in PostgreSQL. Here the server keeps the version for you.

1. `WATCH k` adds the client to a dictionary in the database, from each watched key to the list of clients that watch it. This is in `src/multi.c:262-269` and `304-335`.
2. Every command that changes `k` calls `touchWatchedKey()` through `keyModified()`. It sets `CLIENT_DIRTY_CAS` on every client that watches `k`. A `SET` counts even when it writes the same value. A command that changes nothing does not count. For example, `SADD` calls `keyModified()` only when it added a member. This is in `src/multi.c:389-428`, `src/db.c:1190-1196` and `src/t_set.c:653-656`. Both cases were measured on the same Homebrew 8.10.1 build on 2026-10-19. An `SADD` of a member that was already there let `EXEC` commit. An `SADD` of a new member aborted it.
3. A watched key that expires before `EXEC` also makes `EXEC` fail. `EXEC` checks this with `isWatchedKeyExpired()`, in `src/multi.c:139-142`. Before Redis 6.0.9 an expired key did not abort the transaction.
4. `FLUSHDB`, `FLUSHALL`, `SWAPDB` and the end of a diskless replica sync dirty every watcher of a key that existed. This is in `src/multi.c:430-486`.
5. Eviction counts as a change too. `performEvictions()` calls `deleteEvictedKeyAndPropagate()`, which calls `keyModified()` and so `touchWatchedKey()`. This is in `src/evict.c:686` and `src/db.c:2877`. It was measured on the same build on 2026-10-19. With `volatile-lru` and only the watched key holding a TTL, `evicted_keys` went from 0 to 1, and `EXEC` replied a null array.
6. `EXEC` on a dirty client replies a null array and runs nothing. go-redis returns `redis.TxFailedErr`. redis-py raises `WatchError`.
7. `EXEC` removes every watch before it runs the queue, whether it commits or not. This is in `src/multi.c:167` for a commit, and in `discardTransaction()` at `src/multi.c:77-82` for an abort. So each retry must send `WATCH` again.
8. A write inside the client's own transaction does not trigger its own watch, because the write is only queued.

E13 part c runs one row for each kind of change. This surprises most people: a write of the same value aborts the watcher, and so does an `EXPIRE`.

```text
c. WATCH: which changes make EXEC fail (database 15, emptied)
   between WATCH and EXEC       EXEC       rule says
   nothing changes              commits    commits
   B reads the key (GET)        commits    commits
   B writes another key         commits    commits
   B writes the same value      aborts     aborts
   B sets a TTL (EXPIRE 100)    aborts     aborts
   key expires before EXEC      aborts     aborts
   B runs FLUSHDB               aborts     aborts
   B runs SWAPDB 14 15          aborts     aborts
   every row matches the rule: true
```

The retry loop in E13 is a two-step machine, so the live run and the offline model run the same code. From `tx_watch/main.go:89`, comments shortened, logic unchanged:

```go
func (c *casOp) step(s session) error {
	switch c.phase {
	case 0:
		c.attempts++
		// RULE 1: WATCH before the read.
		if err := s.Watch(c.key); err != nil {
			return err
		}
		v, err := s.Get(c.key)
		if err != nil {
			return err
		}
		c.read, c.phase = v, 1
	case 1:
		ok, err := s.ExecSet(c.key, c.read+1)
		if err != nil {
			return err
		}
		if ok {
			c.done = true
			return nil
		}
		if c.maxRetries > 0 && c.attempts > c.maxRetries {
			c.done, c.gaveUp = true, true
			return nil
		}
		// RULE 2: retry from the read. The value we read is stale.
		c.phase = 0
	}
	return nil
}
```

### Retries, a client that waits, and livelock

Under contention a `WATCH` loop stays correct, and it pays for every aborted attempt. E13 part d starts N clients. Each client adds 1 to one key 200 times with the loop above, and then with plain `INCR`.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Aborts per commit, one hot key, 200 increments per client, E13 part d    │
├──────────────────────────────────────────────────────────────────────────┤
│  1 client   │                                     0.00                   │
│  2 clients  │█                                    0.50                   │
│  8 clients  │█████████                            4.59                   │
│ 32 clients  │███████████████████████████████████ 17.48                   │
│                                                                          │
│ Plain INCR, the same 6,400 increments at 32 clients: 73.5 ms.            │
│ The WATCH loop for the same work: 4,166.5 ms.                            │
└──────────────────────────────────────────────────────────────────────────┘
```

```text
d. CONTENTION: N clients, 200 increments each, on one key (retry cap 0, 0 = none)
   clients  commits   aborts aborts/commit max attempts  gave up   WATCH ms    INCR ms
         1      200        0          0.00            1        0       71.9       17.2
         2      400      200          0.50          201        0      140.7       26.8
         8     1600     7339          4.59          316        0      673.1       35.2
        32     6400   111849         17.48          177        0     4166.5       73.5
   tx:hot always equals commits, so no increment was lost.

   With one plain INCR writer in a loop on the same key, 1 WATCH client, 100 increments, cap 10:
   commits=0 gave up=100 aborts=1100 max attempts=11 in 472 ms, while the writer sent 3299 INCRs
```

Conditions: Homebrew Redis 8.10.1, an x86_64 build under Rosetta 2 on an Apple M4 Pro. The server ran on port 6581 with no persistence, and the client was go-redis v9.5.1 on loopback. Each client has its own connection. Each attempt is 3 round trips: `WATCH`, `GET`, and `MULTI` with `SET` and `EXEC` in one write. Over five runs, the aborts per commit at 8 clients were 4.00 to 4.87. The most attempts for one increment at 8 clients were 316 to 664. At 32 clients the aborts per commit were 17.48 to 17.81.

Four results follow from the table:

1. No update was lost. The final value equals the commits in every run.
2. The group always moves forward when every writer uses the loop. An abort needs a write, and here every write is another client's commit. That is inferred from step 2 of the mechanism.
3. One client can still wait a long time. At 2 clients, one increment needed 201 attempts. One client won every round until it finished its 200 increments.
4. A writer that does not use `WATCH` can stop the loop completely. This is livelock: the client keeps trying and makes no progress. The plain `INCR` writer let 0 of 100 increments commit.

The arithmetic for result 4, inferred from the run. The writer sent 3,299 `INCR` in 472 ms, one every 143 µs. One `WATCH` client alone took 71.9 ms for 200 increments of 3 round trips, so one round trip is about 120 µs. The gap from `WATCH` to `EXEC` is 2 round trips, about 240 µs. A write every 143 µs lands in almost every 240 µs gap.

A cap on retries bounds the wait, and it turns the wait into an error. With `-max-retries 10`, 3,491 of 6,400 increments at 32 clients gave up. The final value still equalled the commits. Client libraries leave this choice to you:

- redis-py `transaction()` retries in a `while True` loop with no limit, in `redis/client.py:628-638` at v8.1.0. A 2014 request to cap it, issue #566, is closed.
- go-redis returns `TxFailedErr`, and the caller writes the loop. Its own example uses `maxRetries = 10000`.
- SwordFS, an open-source file system, hit "Redis transaction retry limit exceeded" in CI in October 2026. Writers of unrelated names all watched the same parent key, and the default allowed 3 attempts. The fix raised the default to 8 with the same randomized backoff. This is a small open-source project, issue #454.

### MULTI in a cluster

In a cluster, every key of one transaction must be in one hash slot. A hash slot is one of the 16,384 parts the cluster splits the keyspace into. Section 1.8 named the tool for this: the hash tag.

1. Each queued command is checked for its own key when it arrives. A key whose slot lives on another node gets a `MOVED` reply. That marks the transaction dirty, so `EXEC` replies `EXECABORT`. This is in `src/server.c:4603-4623`.
2. At `EXEC`, Redis checks all queued keys together. Keys in two slots give `-CROSSSLOT Keys in request don't hash to the same slot`, and Redis discards the transaction. This is in `src/cluster.c:1261-1300` and `1366-1372`.
3. `WATCH` has the same rule. The redis.io multi-key page lists `MULTI`, `EXEC`, `WATCH` and scripts as single-slot in Redis Open Source cluster.
4. The fix is the hash tag from 1.8. `{c7}:wallet` and `{c7}:log` hash only `c7`, so they share one slot.

The trap is in the client. go-redis v9.5.1 `ClusterClient` splits a `TxPipeline` by slot. It sends one `MULTI` and `EXEC` for each slot, in `osscluster.go:1424-1425`. Keys in two slots then give two separate transactions and no error. Its `Watch` checks the slots first. Keys in two slots return `redis: Watch requires all keys to be in the same slot` before anything is sent, in `osscluster.go:1599-1605`. Both were read in the source and not run, because the lab server is one node on one port.

### MULTI with pipelining

A pipeline sends many commands before it reads the replies. A pipeline alone is not a transaction, because other clients' commands can run between its commands.

1. Clients send `MULTI`, the queued commands and `EXEC` in one write. go-redis does this in `TxPipelined`. redis-py `pipeline()` does it by default, with `transaction=True`. So a transaction with no `WATCH` costs one round trip.
2. The `WATCH` and the read cannot go into that same write. The client needs the value before it builds the queue. So a `WATCH` loop costs at least 2 round trips per attempt, and E13 uses 3.
3. `MULTI` and `WATCH` carry the `ALLOW_BUSY` flag, and `EXEC` does not. During a slow script, Redis accepts a pipelined `MULTI` and rejects the next commands with `BUSY`. Each rejection marks the transaction dirty, so nothing of it runs. If Redis refused the `MULTI` too, the commands sent after the script ended would run alone, outside any transaction. This is in `src/server.c:4793-4811`, which names PR #7022.
4. A watch belongs to one connection. If the connection drops, the watch is gone. node-redis fixed a bug where `exec()` after a reconnect committed over another client's write, in PR #3506. Check how your client handles a reconnect between `WATCH` and `EXEC`.

### How a transaction reaches the AOF and the replicas

The AOF, the append-only file, is the log of writes that Redis replays at start. Phase 4 covers it in full.

1. One execution unit can make more than one write. Redis then wraps those writes in `MULTI` and `EXEC` for the AOF and the replicas. An execution unit is one command, one `EXEC` or one script. This is `propagatePendingCommands()` in `src/server.c:3848-3891`.
2. Only the writes that happened are sent. The failed `LPOP` of part a is not in the file.
3. A single write is sent alone, with no wrapper.

This is the AOF after part a and one plain `INCR`, with `appendonly yes` set on the lab server for this check. Each RESP line is joined into one row:

```text
*2 $6 SELECT $1 0
*3 $3 SET $4 tx:a $3 abc
*1 $5 MULTI
*2 $4 INCR $4 tx:n
*3 $3 SET $4 tx:b $4 done
*1 $4 EXEC
*2 $4 INCR $9 tx:single
```

A crash can cut the AOF inside a transaction. What Redis does at the next start depends on where the cut is. With `aof-load-truncated yes`, the default, Redis cuts the file and starts in both cases. The default is in `src/config.c:3422`.

1. If the file ends after a whole command, Redis goes back to the offset before the open `MULTI` and cuts the file there. This is in `src/aof.c:1970` and `2016-2026`.
2. If the file ends in the middle of a command, Redis 8.10.2 cuts it after the last whole command. This is in `src/aof.c:2041-2056`. The open `MULTI` stays in the file. The queued commands never run, so the data after this start is right.
3. The open `MULTI` breaks the start after that. Redis appends new writes after it. At the next start, those writes load as part of the open transaction, and Redis removes them with it. So writes that Redis accepted after the first start are lost.

With `aof-load-truncated no`, Redis stops at the cut and asks for `redis-check-aof`. That is the case the docs describe. Valkey 9.1.2 goes back to the offset before the `MULTI` in both cases. Its release note for PR #4342 says the fix prevents "loss of newer writes after a later restart".

`tx_watch/aof_cut.sh` runs both cases on a server it starts itself. This is its output for the second case. It was measured on 2026-10-19 with the Homebrew 8.10.1 build and with Redis 8.10.2, built from the 8.10.2 tag as a native arm64 binary on the same Mac. Both builds printed the same lines:

```text
cut at byte 111 (midcmd)
start 1: tx:a=1 tx:n= tx:b=
!!! Truncating the AOF appendonly.aof.1.incr.aof at offset 92 !!!
file after start 1:
*2 $6 SELECT $1 0
*3 $3 SET $4 tx:a $1 1
*1 $5 MULTI
*2 $4 INCR $4 tx:n
start 2: tx:after=, written after start 1
Revert incomplete MULTI/EXEC transaction in AOF file appendonly.aof.1.incr.aof
!!! Truncating the AOF appendonly.aof.1.incr.aof at offset 53 !!!
```

The first case, `boundary`, printed `start 2: tx:after=1`, so it lost no write. The first draft of this section said that Redis always goes back to the `MULTI`. This run corrected it. After a "short read" warning in the log, run `BGREWRITEAOF` before the next restart. In the same test, a rewrite after start 1 kept `tx:after` through the next restart.

### The ACL fix in Redis 8.10.2

ACL, the access control list, decides which commands and keys each user may use. Redis checks ACL twice for a transaction: once when it queues a command, and again at `EXEC`. The second check makes a removed permission apply to a transaction that is already queued.

1. From Redis 8.4.0 to 8.10.1, the check at `EXEC` read the keys of the current command. During `EXEC`, the current command is `EXEC` itself, which has no keys. So key permissions were not checked again. Command permissions still were.
2. Redis 8.10.2 passes the queued command to the check, in `src/multi.c:192-223`. The release note is #15673, and 8.10.2 is a SECURITY release.
3. PR #15673 says the bug came with commit `235e688b0`, "Lookahead pre-fetching (#14440)".
4. Valkey 9.1.2 re-checks with `ACLCheckAllPerm(c, &acl_errpos)` and has no such key cache. So the bug likely does not apply to Valkey. That is inferred from `src/multi.c:250-271` at 9.1.2 and was not run.

E13 part e shows the bug on this machine's 8.10.1 build. A user queues `GET`, an admin removes the user's key access, and the user sends `EXEC`:

```text
e. ACL AT EXEC on redis_version 8.10.1: access removed after GET was queued
   MULTI                      → OK
   GET tx:acl:secret          → QUEUED
   (admin) ACL SETUSER p1tx resetkeys ~other:*
   EXEC                       → [s3cret]
   GET tx:acl:secret          → (error) NOPERM No permissions to access a key
   EXEC ran the queued GET with access the user no longer has (fixed in 8.10.2).
```

The same part on Redis 8.10.2, built from the 8.10.2 tag as a native arm64 binary on the same Mac, on 2026-10-19:

```text
e. ACL AT EXEC on redis_version 8.10.2: access removed after GET was queued
   EXEC                       → [(error) NOPERM ACLs rules changed between the moment the transaction was accumulated and the EXEC call. This command is no longer allowed for the following reason: no permission to touch the specified keys]
   EXEC re-checked the key: the queued GET was refused.
```

The `MULTI` and `GET` lines are the same as on 8.10.1 and are left out. Until you upgrade, a revoke does not stop transactions that are already queued. After a revoke, also close the user's connections with `CLIENT KILL USER <name>`.

### A single command, a transaction, or a script

Use the smallest tool that does the change in one step on the server.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Which tool for which change                                              │
├──────────────────────────────────────────────────────────────────────────┤
│ one key, a command does it         │ the command: INCR, SET NX, ZADD     │
│ compare-and-set on one String      │ SET k new IFEQ old, one command     │
│ several writes, no decision        │ MULTI ... EXEC, one round trip      │
│ read, decide, write, few writers   │ WATCH + MULTI/EXEC, capped retries  │
│ read, decide, write, hot key,      │ a Lua script or a Function, which   │
│ or writers that do not WATCH       │ runs once: no abort, no retry       │
└──────────────────────────────────────────────────────────────────────────┘
```

- Reach for one command first. `SET k new IFEQ old` is a compare-and-set on one String in one command. Redis has `IFEQ`, `IFNE`, `IFDEQ`, `IFDNE` and `DELEX` since 8.4.0. Valkey has `SET ... IFEQ` since 8.1.0 and `DELIFEQ` since 9.0.0.
- Use `MULTI` and `EXEC` with no `WATCH` when the writes do not depend on values you read. Section 1.2's `HMSET` with its separate `EXPIRE` is this case.
- Use `WATCH` when the logic must stay in the application and few clients write the key. Cap the retries and add a random backoff.
- Use a Lua script or a Function when many clients write the key, or when some writers do not use `WATCH`. Redis runs the whole script with nothing in between, so there is no abort and no retry. Phase 3, section 3.8 "Lua scripts and Functions in production", covers the script cache, the time limit and how each is replicated.

Valkey 9.1.2 keeps the same transaction rules. That is read from its `src/multi.c` and was not run. Its `WATCH` stores watched keys per database in a hash table for an O(1) duplicate check, from PR #3360. It also goes back to the `MULTI` when the AOF is cut inside a command, from PR #4342, so it does not lose the later writes shown above.

**The sentence to remember:** `EXEC` runs the queue with nothing in between, but it never undoes a command. Only an aborted `EXEC` means nothing ran.

**The trap:** retrying a whole transaction on any error. A run-time error leaves the other writes in place, so the retry applies them twice. E13 part a ends with `tx:n=2` after one `INCR` that "failed". A second trap is an uncapped `WATCH` loop on a key that a plain writer also changes. E13 got 0 of 100 commits that way.

**Try this now:**
```bash
go run ./phase01_data_structures/tx_watch -self-test
go run ./phase01_data_structures/tx_watch -part c
# Every row prints "commits" or "aborts" next to what the rule predicts.
```

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

- [ ] **E13 (break-it, live).** Transactions: no rollback, EXECABORT, WATCH, and retries under contention.
  - Every command in E13 was run on 2026-10-19 against Homebrew Redis 8.10.1 on port 6581, with no persistence. It was an x86_64 build under Rosetta 2 on an Apple M4 Pro. The course container runs `redis:7.2` instead.
  - Warning: part c empties databases 14 and 15, and part e creates and deletes the ACL user `p1tx`. Run it on a server you own.
  - Run: `go run ./phase01_data_structures/tx_watch -self-test`
  - Expected: seven `ok` lines and `self-test passed`, with no server. The lock-step check prints `aborts=18 want 18`.
  - Then run: `go run ./phase01_data_structures/tx_watch`
  - Expected: part a prints `tx:n=1 tx:b=done → no rollback: true` and then `yet tx:n=2 tx:b=again`. Part b prints `EXECABORT` and `EXISTS tx:c=0`. Part c prints `every row matches the rule: true`. Part d prints the table from 1.9, with 0 aborts at 1 client and 17.48 aborts per commit at 32 clients. Against the plain `INCR` writer it prints `commits=0 gave up=100`. Part e prints `EXEC → [s3cret]` on Redis 8.4.0 to 8.10.1.
  - On Redis 8.10.2, part e printed a `NOPERM` entry instead. That was run on a native arm64 build of the 8.10.2 tag, as 1.9 shows. On `redis:7.2` it should also print `NOPERM`, because the bug arrived in 8.4.0. That is inferred from the release note and was not run.
  - Optional, for the AOF part of 1.9: `./phase01_data_structures/tx_watch/aof_cut.sh <free port> midcmd`. It starts its own server with the AOF on, and it refuses port 6379. Expected: `start 2: tx:after=,` because the write made after the first start is lost. With `boundary` instead of `midcmd`, it prints `start 2: tx:after=1`.
  - Break it: delete the `s.Watch(c.key)` call in `step`, then run `-self-test` again. Expected: `FAIL d no lost update under contention: final=3 commits=12 want 12`.
  - If it fails: `cannot reach Redis` means the container is down, so run `docker compose up -d`. An error from `SWAPDB` means the server has fewer than 16 databases.
  - Teaches: what EXEC promises, the two times an error can happen, what invalidates a watch, and what retries cost.

---

## 🏢 Codebase anchor — things to check in the codebase

1. **The session as Hash + Set, split across two services.** Open `mt-login-provider/src/storage/sessison_store.go` and `src/dao/redis_store.go`. Find `FetchInfoFromUserCompanyIDKey` (`HGetAll`), `DeleteSecondaryIndexHashKeyFields` (`HDEL` of specific fields), `InvalidateAllSessions` (`GetAllValuesFromSet` → delete each → `DeleteKeys`). Then note what this repo does NOT contain: the `HMSET` that creates the session hash — that's in `app-gatekeeper/src/models/userStore.ts` (Node). Questions: why is the session a Hash + a Set index rather than one JSON String holding a list? What does `HDEL`-of-one-field buy that a blob can't? (Field-level mutation without read-modify-write races — Phase 0.1.) And: what's the risk of the write side doing `HMSET` then a *separate* `EXPIRE` (app-gatekeeper) versus one atomic `SET … EX`? (A crash between them = a session hash with no TTL = an INCP-520-shaped unevictable key, Phase 0.)

2. **A multi-structure CacheClient in one file.** In `content-search-service`, `package/helper/CacheClient.go` exposes `AddInFifoQueue`/`RemoveFromFifoQueue`/`LengthOfQueue` (List: RPUSH/LPOP/LLEN), `AddInRedisSet`/`RemoveFromRedisSet` (Set: SADD/SREM), and `AddKeyBySetNXInRedis` (String: SETNX). Question: for its FIFO queue, what happens to an item if the consumer dies between `LPOP` and finishing the work? Is that acceptable for what this queue carries? (If not, it wants Streams/Kafka — 1.3.)

3. **A Sorted Set as a per-language translation lock table.** In `course-qu-processors` — `src/infrastructure/redisWriteClient/RedisWriteClient.go` and `src/domain/TranslationOrchestrator/utils/TranslationRedisUtil.go` — find the key `translate:inprogress:<moduleId>:<loId>` and the ops `ZAdd({Score: now+ttl, Member: lang})`, `ZRemRangeByScore(-inf, now)`, `ZScore(key, lang)`, `ZRangeByScore(now, +inf)`. Questions: how does `ZScore(key, "fr")` answer "is French already being translated?" What does `ZRemRangeByScore(-inf, now)` reap in one atomic call, and why is that cheaper than N per-key TTLs? (The score IS the expiry.) Bonus: the same scheme appears in `assessment-service` and in `ce-course-qu` via Redisson `RScoredSortedSet` — why would three services converge on a ZSet lock table instead of `SETNX`? (Atomic bulk-reap of a crashed worker's locks — a Phase 3 preview.)

4. **The buyer persona as a JSON String.** Re-open `missions-processors/processors/ai_roleplay_helper/ai_roleplay_helper.go` (`SetBuyerPersonaForCache` → `SetKey(key, json, PREV_INSTR_TTL)`). Question: this is a String blob, not a Hash — is that the right call here? (Argue it: the persona is read/written whole, never field-by-field, and it's opaque to the cache layer → String is correct. Contrast with the session, which is mutated field-by-field → Hash. This is the 1.1-vs-1.2 decision, live in two of your services.)

5. **Transactions, in the course code and in yours.** Open `code/phase01_data_structures/tx_watch/main.go:89`, the `step` method. Which line would you delete to lose updates, and which self-test check catches it? Then, in any Go service that uses Redis, run `grep -rn "TxPipelined\|TxFailedErr\|\.Watch(" <repo>/`. For each hit, ask two questions. Does the code retry on any error, or only on `TxFailedErr`? Is there a retry cap with backoff?

---

## ✅ Checkpoint 1 — answer in your own words

1. **Q1.** A teammate models a shopping-cart-style "modules assigned to a user" as a JSON array in a String: `GET`, unmarshal, append, marshal, `SET` on every assignment. Two assignments race. Walk the exact interleaving that loses one, name the structure that fixes it in one atomic command, and write that command.

2. **Q2.** You need a rate limiter: max 100 requests per minute per company. Compare the fixed-window `INCR`+`EXPIRE` approach (mt-dashboard-api's actual choice) with the sorted-set sliding-window approach (E9). Show the specific input that makes fixed-window allow ~200 requests in a ~2-second span, and explain why the ZSet version can't. Then argue *why mt-dashboard-api might still correctly choose fixed-window* (hint: cost — count the bytes and ops per request for each).

3. **Q3.** "How many unique learners opened this course this month?" Design two solutions — a Set and a HyperLogLog — and give the memory for 5 million uniques in each (use the ratios from E10). State the one question whose answer decides between them. (Hint: does the product need to *list* those learners, or just count them?)

4. **Q4.** Walk through `course-qu-processors`' ZSet translation-lock end-to-end for key `translate:inprogress:m1:lo9`: French translation starts (`ZADD` with what score?), a duplicate "translate fr" event arrives (`ZScore` check — what tells you it's still locked?), French finishes (`ZRem fr`), and a *German* worker crashes mid-run leaving its `de` member behind. What single command reaps the stale `de` lock, and what score value makes that reaping correct? Why would a plain Set (no scores) be unable to reap the crashed worker's lock?

5. **Q5.** A colleague says "let's store each user's session as 6 separate String keys (`sess:u42:token`, `sess:u42:ip`, ...) so we can expire them independently." Give two reasons `mt-login-provider`'s single-Hash approach is better (hint: one is memory/encoding from 1.7, one is atomicity/round-trips), and the one scenario where the separate-keys approach would actually win.

6. **Q6.** You `HGETALL` a hash in a hot path and p99 latency quietly climbs over three months with no deploys. Given 1.2 and 1.7, what are the two independent things that could be growing, how do you confirm each (name the commands), and what's the fix for each?

7. **Q7.** Design task: a "trending assets" feature — the top 10 assets per company, weighted toward *recent* activity. Which structure records the ranking, which commands record a view and read the top 10, and how do you make an asset's score *decay* as its activity gets old (so all-time winners don't dominate forever)? Design it, THEN open `asset-hub-analytics` (`src/infrastructure/CacheClient.go`, `src/domain/trendingAssets/core/TrendingAssetsTasksFacade.go`) and compare: they use a ZSet leaderboard (`ZIncrBy`/`ZRevRangeWithScores`) fed by a bounded FIFO List — when the list overflows, the oldest event's asset gets a *negative* `ZIncrBy`. Did you invent the same List+ZSet combo, or something different? Which is simpler to reason about?

8. **Q8.** A wallet service moves credits between `wallet:{u42}:main` and `wallet:{u42}:bonus` with a `WATCH` loop. It watches both keys, reads both, then sends `MULTI`, `DECRBY main 30`, `INCRBY bonus 30` and `EXEC`. (a) In a load test, 16 workers move credits for the same user, and the loop retries forever. p99 rises from 1 ms to 400 ms with no errors. Use E13 part d to explain why, and give two fixes. (b) A teammate wraps the call in "if err != nil, retry". The bonus key once held a Hash by mistake, so `INCRBY` failed with `WRONGTYPE`. What did the retry do to `main`? (c) The keys move to a cluster, and someone drops the hash tag from one key name. What does the client see?

<details>
<summary>Answer sketches</summary>

1. A runs `GET` and gets `[m1]`. B runs `GET` and also gets `[m1]`. A appends `m2` and sets `[m1, m2]`. B appends `m3` and sets `[m1, m3]`, so `m2` is gone with no error. A Set fixes it: `SADD user:u42:modules m2` adds inside one command and removes duplicates. `RPUSH` on a List also works if order matters and duplicates are allowed.
2. Send 100 requests in the last second of minute 1 and 100 in the first second of minute 2. Each fixed window counts only its own 100, so 200 pass in about 2 seconds. The sliding log counts the real last 60 seconds, so request 101 in that span is rejected. The cost: the log stores up to 100 members per company and runs four commands per request. The counter is one small integer and two commands, or one `INCREX` on Redis 8.8 and later. A team with many companies on a shared cluster can choose the counter for that reason.
3. A Set of 100,000 members used 4,361,836 bytes in a run on Redis 8.10.1 for the Mission HQ lesson. The phase's earlier run gave 5,442 KB. 5 million members is 50 times that, about 218 to 272 MB. The HLL stays at about 12 KB, with 0.81% standard error. The deciding question: must the product list, remove or test individual learners? If it only shows a count, use the HLL.
4. French starts with `ZADD key (now+ttl) fr`, so the score is the time the lock expires. The duplicate event runs `ZSCORE key fr`, and a score greater than now means French is still locked. When French finishes, `ZREM key fr`. The German worker crashes and leaves `de`. Once its score is below now, `ZREMRANGEBYSCORE key -inf now` removes it, with every other expired lock, in one command. A plain Set has no score, so it cannot tell an old member from a live one.
5. First, a small Hash is a listpack, so it avoids six per-key overheads, as 1.7 shows. Second, `HGETALL` reads every field in one round trip, and one `HSET` with several fields writes them in one atomic command. Separate keys used to win when fields needed their own TTL. `HEXPIRE` gives each field its own TTL since Redis 7.4 and Valkey 9.0, so that case is gone on current versions.
6. The number of fields can grow, so `HGETALL` does more O(N) work on the one thread. Confirm with `HLEN` and `SLOWLOG GET`. Fix it by bounding the fields, reading only the needed fields with `HMGET`, or using `HSCAN`. Second, the hash can cross a listpack limit and become a hashtable. Confirm with `OBJECT ENCODING` and `MEMORY USAGE`. Fix it by splitting the hash into buckets under the limit.
7. One sorted set per company, with the asset as member. A view runs `ZINCRBY trend:c7 1 a42`. The board reads `ZRANGE trend:c7 0 9 REV WITHSCORES`. For decay, push each view onto a List capped at N. When the List passes N, `LPOP` the oldest view and run `ZINCRBY` with -1 for its asset. Another design scales all scores down on a schedule. Compare which one stays correct when a view is counted twice.
8. (a) All 16 workers read, and in each round only one `EXEC` commits. E13 measured 4.59 aborts per commit at 8 clients and 17.48 at 32. The worst increment at 8 clients needed 316 to 664 attempts. Each attempt is 3 round trips, so p99 grows with the attempts, and no error appears because the loop never gives up. Fix 1: one Lua script or Function that checks the balance and moves the credits on the server, with no retry. Fix 2: cap the retries with a random backoff and return an error at the cap. (b) No rollback: `DECRBY main 30` ran, and `INCRBY` replied `WRONGTYPE` inside the `EXEC` array. go-redis then returns that error. Each retry ran `DECRBY` again, and `INCRBY` failed again, so the loop never stopped. `main` lost 30 on every attempt, and `bonus` gained nothing. Only `TxFailedErr` means nothing ran. (c) `WATCH` on keys in two slots fails with `CROSSSLOT`. Without the watch, `EXEC` checks all queued keys and replies `CROSSSLOT`, and Redis discards the transaction. A key whose slot is on another node gets `MOVED` at queue time, so `EXEC` replies `EXECABORT`. With go-redis v9.5.1, `ClusterClient.Watch` refuses keys in two slots before it sends anything. A `TxPipeline` with no watch instead splits the commands by slot into two transactions. No error appears, and the move is no longer one unit.

</details>

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

**Transactions (1.9). Every link below returned HTTP 200 on 2026-10-19:**
- **Transactions, redis.io docs** — https://redis.io/docs/latest/develop/using-commands/transactions/
  Focus on: "Errors inside a transaction", "What about rollbacks?" and "WATCH explained". Its paragraph on the AOF describes `aof-load-truncated no` only.
- **Multi-key operations, redis.io docs** — https://redis.io/docs/latest/develop/using-commands/multi-key-operations/
  Focus on: the table "Pipelines, transactions, and scripts". It gives the single-slot rule for MULTI, WATCH and scripts in a cluster.
- **src/multi.c at Redis 8.10.2** — https://raw.githubusercontent.com/redis/redis/8.10.2/src/multi.c
  Focus on: `execCommand` at lines 127-260, `touchWatchedKey` at 389-428 and `touchAllWatchedKeysInDb` at 430-486. Read it before you trust any summary of WATCH.
- **src/server.c at Redis 8.10.2** — https://raw.githubusercontent.com/redis/redis/8.10.2/src/server.c
  Focus on: `rejectCommand` at 4277-4287, `propagatePendingCommands` at 3848-3891 and the BUSY comment at 4793-4811.
- **src/aof.c at Redis 8.10.2** — https://raw.githubusercontent.com/redis/redis/8.10.2/src/aof.c
  Focus on: lines 1970, 2016-2026 and 2041-2056, where a cut MULTI block is handled at load. A cut inside a command leaves the open MULTI in the file.
- **Redis 8.10.2 release notes** — https://raw.githubusercontent.com/redis/redis/8.10.2/00-RELEASENOTES
  Focus on: lines 24-31, security fix #15673.
- **PR #15673, ACL key check for queued commands** — https://github.com/redis/redis/pull/15673
  Focus on: the root cause, the key cache read from EXEC, and the commit that brought the bug.
- **src/multi.c at Valkey 9.1.2** — https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/src/multi.c
  Focus on: the ACL re-check at lines 250-271, and the per-database hash table of watched keys.
- **Valkey 9.1.2 release notes** — https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/00-RELEASENOTES
  Focus on: line 29, PR #4342, the AOF fix for a cut inside a MULTI block, and line 140, PR #3360.
- **You Don't Need Transaction Rollbacks in Redis, Redis blog** — https://redis.io/blog/you-dont-need-transaction-rollbacks-in-redis/
  A vendor source. Focus on: the argument against rollback, and when it recommends Lua over WATCH.
- **redis-py client.py at v8.1.0** — https://raw.githubusercontent.com/redis/redis-py/v8.1.0/redis/client.py
  Focus on: `transaction()` at lines 616-638, the retry loop with no limit.
- **redis-py issue #566** — https://github.com/redis/redis-py/issues/566
  The 2014 request to cap WATCH retries, closed. Read it when you choose a retry policy.
- **node-redis PR #3506** — https://github.com/redis/node-redis/pull/3506
  Focus on: how a reconnect lost the WATCH and let `exec()` commit over another client's write. Merged 2026-10-13.
- **SwordFS issue #454** — https://github.com/SwordInfra/SwordFS/issues/454
  A small open-source project. Focus on: the comments, "Redis transaction retry limit exceeded" with a 3-attempt default. Closed 2026-10-10.
- The owner's elite-storage course, Phase 3: section 3.1 for atomicity against isolation, and 3.6 for optimistic against pessimistic locking. Local files, no URL.

**Command reference (bookmark):**
- [redis.io/commands](https://redis.io/docs/latest/commands/) filtered by data type — every command with its Big-O. The O(N) warnings are your production guardrails.
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

TRANSACTIONS (1.9)
  MULTI ... EXEC    queue on one connection; no other client runs in between
  no rollback       a run-time error (WRONGTYPE) is one reply; the rest still apply
  queue-time error  wrong arity, unknown cmd, ACL, MOVED, OOM → EXECABORT, none run
  WATCH k           EXEC → null if k is written (same value too), EXPIREd, expires,
                    evicted, or hit by FLUSHDB / FLUSHALL / SWAPDB
                    reads and no-op writes (SADD of a member that exists) do not count
                    EXEC unwatches every key → WATCH again on every retry
  go-redis          TxPipelined err != nil does NOT mean nothing ran; TxFailedErr does
  retry cost        measured: 17.48 aborts/commit at 32 clients; 0/100 vs a plain writer
  retry policy      redis-py loops forever; cap it and add random backoff
  cluster           every key in one slot, else CROSSSLOT → {tag} keys (1.8)
  AOF / replicas    writes of one EXEC are wrapped in MULTI/EXEC; failed cmds absent
  AOF cut in a cmd  8.10.2 keeps the open MULTI → later writes lost → BGREWRITEAOF
  ACL               8.4.0-8.10.1 skip the key re-check at EXEC → upgrade to 8.10.2
  pick              one command > SET IFEQ (8.4+) > MULTI > WATCH (capped) > script

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

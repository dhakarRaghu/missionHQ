Phase 1 taught you to pick a Redis type for each job, and to price that choice in round trips and memory. It ended on a question it did not answer. A value in Redis is often a copy of a database row, and Phase 1 did not say how that copy stays correct when the row changes, or what happens when many requests miss it at once. This lesson answers both with a new example.

Your agent platform runs on 40 pods. Every agent run first reads its tenant's settings: the model, the tools the tenant allows, and its rate limits. The settings live in Postgres, and Redis sits in front of Postgres as a cache. Each cached key has a one-hour *TTL*, the time to live after which Redis deletes the key by itself.

Together the pods read settings about 5,000 times per second. The *hit rate*, written h, is the share of reads that Redis answers. At h = 0.98 only about 100 reads per second reach Postgres, so Postgres was sized for that load. This lesson follows the settings cache through four failures, and each one is a real class of production incident. The agent platform is this lesson's own example, not the grading service of Phase 0. The real cases about "the platform" come from the shared platform of Phase 0.

- One Redis node restarts empty, and Postgres falls over although nothing returned an error.

- One key that every request reads expires, and 40 pods rebuild it at the same moment.

- An admin removes a tool from a tenant, and agents keep using that tool for an hour.

- A broken client asks for tenants that do not exist, thousands of times per second.

All four happen in the same two places of a cache that readers fill. In the first place a reader finds nothing and goes to the source, and in the second that reader writes what it found back into Redis. The first section below gives both places a name and shows them in four commands.

### What you must know

- **The source serves only the misses. When caching stops, its load jumps 1/(1 − h) times, with no error.**Size the source for a cache outage, and make the fallback to the source cheap when Redis fails.

- **Each reader that misses during a rebuild starts its own rebuild, so the readers must share one rebuild across every process that reads.**Pick a way to share one rebuild across 40 pods, and predict the source calls.

- **Deleting the cached key on every write is not race-free. A slow reader can write the old value back after the delete.**Give each fill a token that the delete removes, so a late fill is refused.

- **A cached "not found" is a cache entry too. The create path must delete it, like any update.**Stop floods of missing IDs without hiding new rows.

The cheatsheet tags these four ideas c1 to c4, in the order of this list.

## Three names for a cache that readers fill, and what you bring from Phases 0 to 1

Postgres was sized for about 100 reads per second, and the 40 pods send 5,000. So Redis must answer about 4,900 of every 5,000 reads, and each failure in this lesson is a way that share drops or a copy goes wrong.

A cache that readers fill works in three moves. A reader asks Redis first, and on a miss it reads Postgres and copies the answer into Redis with a TTL. When an admin changes the row, the old copy must go, or readers keep it until the TTL ends. This lesson uses one name for each move.

- The *miss path* is the code a reader runs when Redis has no value for the key, so it reads the source instead. You meet it first in the section on how much load reaches Postgres.

- The *fill path* is the code that writes what the reader found back into Redis, with a TTL. You meet it in the stampede sections, where many fills run at once, and in the race sections, where one fill lands late.

- *Invalidation* is the removal of a cached value, or a mark that it is old, because the source changed. You meet it when an admin removes a tool from tenant 42.

Four `redis-cli` commands show the three moves on the running case's key.

```
GET tenant:42:settings:v1
(nil)
SET tenant:42:settings:v1 v1 EX 3600
OK
TTL tenant:42:settings:v1
(integer) 3600
DEL tenant:42:settings:v1
(integer) 1
```

- `GET` returns nil, so this reader is on the miss path and reads Postgres next.

- `SET ... EX 3600` returns OK. This is the fill path, and the copy now lives for one hour.

- `TTL` returns 3600, the seconds left before Redis deletes the copy by itself.

- `DEL` returns 1 because it removed one key. This is invalidation, so the next `GET` misses and fills fresh data.

**Evidence**

The replies come from the study note's `redis-cli` run of the race in the invalidation sections, on the same local Redis 8.10.1 server as its other runs. That run used its own key, and the note records the replies as nil, OK, a TTL of 3600 and a DEL of 1. This page shows them in the usual `redis-cli` format, in a shorter order than the race. Exercise E10 in the lab runs the same `SET`, `DEL` and `GET` on a key of its own.

Three ideas from Phases 0 and 1 also come back in this phase, and each card below explains one again.

**One command thread, and the round trip**

Redis runs each command to the end before it starts the next one. Phase 0 showed that a small command costs about one network round trip. So every extra cache call on the miss path or the fill path adds a round trip to the request.

**SET with NX and EX is one atomic claim**

`SET key val NX EX n` writes the key only if it does not exist yet, and gives it a TTL of n seconds. Redis runs it as one command, so two clients can never both succeed. Phase 1 used it to claim work, and this lesson uses it to claim a cache fill.

**Keys carry a prefix and a version**

Phase 1 named keys by the kind of object and its ID, joined by colons, such as `tenant:42:settings`. This phase adds a version part such as `v1`, which lets you change the value format later. The running case uses `tenant:42:settings:v1`.

This phase needs all three ideas. Each fill costs a round trip. A fill that must not overwrite newer data needs a conditional `SET`. A key version lets you retire an old value format at once. The first question is how much load the source sees when the cache stops answering.

## How much load reaches the source when the hit rate drops?

The settings cache answers 98% of reads, so Postgres sees about 100 reads per second. That number depends on how the cache is filled. *Cache-aside*, also called lazy loading, is the read strategy where your application owns the cache. On a read, the application asks Redis first. On a miss it reads Postgres, and then it writes the value into Redis with a TTL.

- **GET tenant:42:settings:v1**One round trip to Redis.

- **miss**Redis returns nil, because the key is absent or expired.

- **read Postgres**The slow call, and the only one that knows the truth.

- **SET … EX 3600**The reader fills the cache for the next hour.

- **next GET hits**Later reads of this key never touch Postgres.

Redis never talks to Postgres in this design. So the cache holds only *derived data*, a copy that you can rebuild from the source at any time. Losing the cache costs speed but never data, and that is why cache-aside is the default design. The same property also means the source carries every read the cache does not answer.

**Predict: the settings cache has h = 0.98, and Postgres can take 3 times its normal miss load. One of four Redis nodes, holding a quarter of the keys, is replaced by an empty node. Is Postgres safe?**

No. The miss share goes from 0.02 to 0.75 × 0.02 + 0.25 = 0.265. That is about 13 times the normal miss load, far past the 3 times that Postgres can take. Most people expect about a quarter more load, because a quarter of the keys moved. But the normal load is only the 2% that misses, so a small loss of hits becomes a large gain in misses.

The arithmetic has four steps, and the last one is the reason a cache outage can last longer than the event that started it.

- The source sees (1 − h) × traffic. At 5,000 reads per second and h = 0.98, that is 100 reads per second.

- If caching stops completely, the source sees all 5,000 reads. The multiplier is 1/(1 − h), so h = 0.98 gives 50 times the load and h = 0.99 gives 100 times.

- No read returns an error, because each one still succeeds from the source. The first signal you see is source latency, and then timeouts.

- The cache refills only through source reads that succeed. If those reads time out, the misses never become hits, so the hit rate stays low and the overload holds itself in place.

**Load on Postgres from the settings cache**

Hit rate, %:

Reads per second:

Normal load on Postgres Load if caching stops Multiplier, 1/(1 − h)

Arithmetic from the formula above. Illustration, not measured.

Caching can stop for several reasons, and none of them looks like an error in the cache itself.

- A flag or a bug marks responses as not cacheable, so every read goes to the source.

- A cache node restarts empty, or a new empty node replaces a failed one.

- A new region or a fresh deploy starts with a *cold cache*, a cache that holds no keys yet, so every first read misses.

- Redis is down, and the client "fails open" by reading the source on every cache error.

**Slack** saw the second reason as a wave of users who could not connect. An upgrade of the Consul agent restarted agents on a quarter of the fleet. Each restart removed a node of memcached, the older in-memory cache that Slack runs in front of its databases, and an empty spare node took its place. A miss on group DM membership became a query to every database shard. Slack wrote that the read load grew "superlinearly" with the share of misses. The queries timed out, so the cache could not be filled, and the overload continued. The first fix was a throttle on client boot. Then the query was changed to read only the missing data, and to read from replicas, the read-only copies of each database, too. Later Slack added a table sharded by channel.

**Evidence**

Slack, "Slack's Incident on 2-22-22", by Laura Nolan, published 2022-04-26. The post gives no hit-rate numbers. The quotes "superlinearly" and "the cache could not be filled" are from the post. The 0.265 arithmetic is the study note's worked question, not a measurement.

**Go deeper: a silent bypass flag, a repair loop at Facebook, and two more cases**

**A bypass flag on the platform.** A content service cached API responses in Redis through a shared client library. The library checked a `cacheable` flag on each response before it stored it. A serializer marked media items in one processing state as not cacheable. A callback that should move items out of that state had been commented out in an earlier refactor, so the items stayed there. As a result, every call to one hot endpoint skipped the cache.

The source saw about 30,000 calls per minute instead of about 300, which is 100 times. Nothing errored and no related deploy appeared. The symptom was "everything is slow" in the content service and in the services behind it. A one-file fix marked that state as cacheable again. The team reported these results: endpoint calls 30,000 to 300 per minute, source traffic down 80%, a read service down 50%, endpoint p90 from 100 ms to 20 ms, and peak database read units from 35,000 to 7,000 per minute. These numbers come from the platform's own records and are not checked. The formula explains the size. At h = 0.99 the flag multiplied source load by 1/(1 − 0.99) = 100.

The same platform had two defensive patterns that show the right instinct. One request flag stopped a cache purge from running on every poll of a long media job, and purged the stale entry once when the job succeeded. A settings reader wrapped the parsing of cached JSON in a try and catch, so a corrupt entry was logged and the code read the database instead.

**Facebook** had a site outage of about 2.5 hours from a cache repair loop. A system replaced invalid cache values with values from the persistent store. Then it met an invalid value in the store itself. Every client that saw the value tried to repair it, and clients that got a database error deleted the cache key. The database cluster received "hundreds of thousands of queries a second". The fix was to stop all traffic to that cluster, which meant turning off the site, then to let users back slowly, and to turn off the repair system.

**Stack Overflow** keeps a first-level cache, a copy in the memory of each application process, in front of Redis. A TTL bug stopped about 95% or more of keys from filling that cache, by the author's estimate. So all those reads went to Redis. Nobody noticed for a few hours. This is the same silent bypass one layer up.

**Hotstar** shows the opposite cost. A cache on its subscription API, with a short TTL and filled by a cache layer on every miss, made p99 latency 20% worse. Free users far outnumbered paid users, and each call added a cache write. Caching only the IDs of paid users fixed it, because a miss could then mean "free user". The general point is inferred from this case: a cache that saves few source reads still adds a round trip and a write.

**Gutter** is how Facebook's memcache absorbs a failed server without the multiplier. A small pool of spare servers, the gutter pool, takes over the keys of a failed server for a short time. Facebook reported that gutter "converts 10%-25% of failures into hits each day".

**Evidence for the extra cases**

The bypass case is from the phase's own section 2.6 and cannot be checked. Facebook, "More details on today's outage", Robert Johnson, 2010-09-23. Stack Overflow, "How We Do App Caching - 2019 Edition", Nick Craver, 2019-08-06. Hotstar, "Scaling Subscriptions — Cache for Cash!", Prakash Shanbhag, 2020-06-19. The post does not name the cache product. Gutter: "Scaling Memcache at Facebook", NSDI 2013, section 3.3.

- [Facebook, More details on today's outage](https://engineering.fb.com/2010/09/23/uncategorized/more-details-on-today-s-outage/)

- [Stack Overflow, How We Do App Caching](https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/)

- [Hotstar, Scaling Subscriptions](https://blog.hotstar.com/scaling-subscriptions-cache-for-cash-4c5836bd6a6f)

- [Slack's Incident on 2-22-22](https://slack.engineering/slacks-incident-on-2-22-22/)

The formula says the source must survive the misses. It does not yet say which part of your code fills the cache, or what each design can lose on a write. The next section answers that.

## Which strategy fills the cache, and what can each one lose?

Cache-aside left the source carrying every miss, and it fills the cache only on reads. A cache design answers two separate questions. Who fills the cache on a miss? And what happens to the cache when someone writes to the source?

On the read axis, the two strategies differ only in where the miss code lives.

- **Cache-aside**: your application reads Redis, reads the source on a miss, and fills Redis.

- ***Read-through***: a cache library or a proxy does the source read on a miss, so your code calls only `cache.get(key)`. It is cache-aside with the miss code moved behind an interface, and it has the same failure modes.

On the write axis there are three choices, and each one decides what the cache can lose.

- **Write-around with delete**: the writer updates only the source and then deletes the cache key. The next reader fills it again. This is the usual partner of cache-aside, and the invalidation sections below look at it closely.

- ***Write-through***: the writer updates the source and the cache in the same request, before it returns. Every write pays the cache's latency, and you must decide what to do when the cache write fails.

- ***Write-behind***, also called write-back: the writer updates the cache now and queues the source write for a background flush, often in batches. Writes are fast and absorb bursts. But a crash before the flush loses those writes.

The phase said there are "exactly three write policies", and then it defined four. They sit on two axes. Cache-aside and read-through are read strategies. Write-through and write-behind are write strategies, and a design picks one from each axis.

| | Cache-aside, delete on write | Write-through | Write-behind |
|---|---|---|---|
| Who fills the cache | the reader, on a miss | the writer | the writer |
| Freshness | stale until the TTL ends or a delete runs | fresh, unless the cache write fails or two writers interleave | cache fresh, source behind |
| Write latency | source only | source plus cache | cache only |
| Read latency | fast after the first fill | fast | fast |
| Data-loss risk | none, the cache is derived | no data lost, but a failed cache write leaves it stale | a crash before the flush loses writes |
| Complexity | low | medium | high: flush, retry, order, recovery |
| Use when | reads dominate and a stale window is acceptable | a read right after a write must be fresh | writes dominate, some loss is acceptable, and the source cannot keep up |

Write-through ties your write latency to the cache. Write-behind ties your durability to the cache. Both give up the property that makes cache-aside safe, which is that the cache can vanish and no data is lost. Write-through is also not "always fresh", as the phase's table said. If the Postgres write succeeds and the Redis write fails, the cache keeps the old value until its TTL ends.

In the running case, settings are read thousands of times per second and changed by an admin a few times per day. So the settings cache uses cache-aside with delete on write. A per-tenant usage counter, written on every agent run, would be a write-behind candidate, but only if losing a few seconds of counts is acceptable.

Exercise E9 measures this trade, and the Go deeper block below gives its numbers and what a write-behind queue can lose.

**Go deeper: the E9 numbers, a write-behind queue that loses events, and what persistence does to it**

Exercise E9 shows the trade in numbers. Five write-through writes take about 269 ms, because each one waits for the slow source. Five write-behind writes take about 4 ms, and the lab prints `source.puts=0` until the flush runs. Those writes exist only in memory until then. Write-behind stays fast until the pod is killed for using too much memory with 500 writes not yet flushed.

The second lab folder, `phase02_caching_patterns/write_behind`, keeps its queue in a Redis list. Its flusher takes an event with `LPOP` and then writes it to the source, at line 172. A crash between those two steps loses the event, so delivery is at most once. The program also prints "batched by flusher" at line 141, although it writes one row at a time.

An at-least-once flush, one that may repeat an event but never loses it, keeps the event until the write succeeds. One way is `LMOVE` from the queue to a processing list, a second list that holds the events in progress, then a delete from the processing list after the source write. A restart then finds unfinished events in the processing list. Another way is a Redis Stream, the append-only log type, with a consumer group. Each entry then stays pending until a reader confirms it with `XACK`, and the flusher sends `XACK` only after the source write. Phase 1 taught both lists and Streams. At least once means the source may see an event twice, so the source write must be idempotent.

The queue also lives only as long as Redis keeps it. The lab's `docker-compose.yml` starts Redis with `--appendonly no` and `--save ""`, so persistence is off. A Redis restart then empties the queue, and every write in it is lost. A write-behind queue in Redis needs persistence that matches the loss you can accept. Phase 4 covers persistence and failover, the promotion of a replica when the primary dies.

A safer pattern for "write to the database and also tell another system" is the outbox. The writer stores the event in a database table in the same transaction as the data, and a relay publishes it later. The elite-storage course teaches the outbox in its transactions phase.

Caching LLM answers by meaning, called semantic caching, is a different problem with its own failure modes. It is not part of this phase.

**Evidence**

Read and write strategies: AWS ElastiCache "Caching strategies" and the Microsoft Azure cache-aside pattern page. The E9 numbers are the phase's expected output. A study run on one Mac measured 260 ms and 1.8 ms. It used an x86_64 Homebrew build of Redis 8.10.1 under Rosetta 2, outside Docker. The write-behind lab lines were read in the source, not run.

Cache-aside is the right default for settings. The toy version of it fails the request when Redis fails, and the next section shows what a production read does instead.

## What should a cache-aside read do when Redis fails, and what does that cost?

The toy cache-aside read is three lines: `GET`, and on nil read the source and `SET`. In production it breaks in three ways. Redis can be down, a cached value can be corrupt, and the value format can change between deploys. The lab program `phase02_caching/cache_aside/main.go` handles all three with five properties.

- **A version in the key name.** A *versioned key* carries a version part in its name, and here the key is `course:v1:<id>`. When the shape of the cached value changes, you change `v1` to `v2`. New code never reads the old keys, and their TTL removes them. You need no migration, and old bytes cannot crash new code.

- **Read the source on a cache error.** To *fail open* means to treat a cache error like a miss and read the source. If `GET` returns an error that is not `redis.Nil`, the code logs a warning and reads the source. A Redis outage makes the request slower, but the request still succeeds.

- **Tolerate corruption.** If the cached bytes do not unmarshal, because of format drift, a partial write or a bad value, the code reads the source. The next fill replaces the bad value.

- **A deliberate TTL on every fill.** The lab uses 10 minutes. A list that rarely changes can take an hour, and a permission may need less.

- **Fill errors do not fail the request.** A failed marshal or `SET` is a warning, because the caller already has correct data from the source.

The cache is a hard dependency and a format risk.

```go
raw, err := cache.Get(ctx, "voices")   // key not versioned
if err != nil { return nil, err }      // cache down = request FAILS
json.Unmarshal([]byte(raw), &out)      // corrupt value = garbage, no fallback
return out                             // never fills, no TTL
```

The lab's read, shortened: a miss, an error and a corrupt value all lead to the source.

```go
raw, err := rdb.Get(ctx, key).Result()
switch {
case err == redis.Nil:
    // miss: read the source below
case err != nil:
    log.Printf("cache GET failed (%v), failing open", err)
default:
    if json.Unmarshal([]byte(raw), &c) == nil {
        return c, "HIT"
    } // corrupt: read the source below
}
c := slowSourceOfTruth(id)
if b, e := json.Marshal(c); e == nil {
    if e := rdb.Set(ctx, key, b, 10*time.Minute).Err(); e != nil {
        log.Printf("cache SET failed: %v", e) // a warning only
    }
}
```

Returning the cache's error to the caller is the trap here. A Redis blip then becomes a user-facing 500, and the cache has made the service less available than having no cache. Failing open fixes that, but it does not make an outage harmless. It has two costs, and the first one is the multiplier from the first section. During the outage every read reaches Postgres, so Postgres sees 5,000 reads per second instead of 100.

The second cost is time. A client that fails open first waits for its read timeout, which go-redis sets with the option *ReadTimeout*. Then it may retry, up to the number of times in the option *MaxRetries*. If Redis is hung, for example paused or stuck in a long command, each request waits for those timeouts before it falls back. One `GET` against a paused Redis took these times with go-redis v9.5.1, the version the labs pin.

| Client options | Time until the GET fails |
|---|---|
| defaults: `ReadTimeout` 3 s, `MaxRetries` 3 | 6.042 s |
| `MaxRetries: -1` | 3.001 s |
| `ReadTimeout: 100ms` | 242 ms |
| `ReadTimeout: 100ms`, `MaxRetries: -1` | 101 ms |

The current go-redis release defaults `ReadTimeout` to 5 s and keeps `MaxRetries` at 3. With those defaults a hung Redis can add about 10 s to each request, which is inferred from the two measured rows. Exercise E2 does not show this cost, because it stops Redis, and a refused connection fails at once. A safe fail-open path has four parts.

- A short client timeout, set from the cache latency you measure. **Uber** sets CacheFront's timeouts adaptively to the P99.99 of cache latency.

- No retry on a cache read, or at most one, because the source is the fallback.

- A *circuit breaker* per Redis node, which stops calling a failing node for a while and goes straight to the source. Uber uses a sliding-window breaker per node.

- A limit on how many misses may reach the source at once. Requests above the limit wait or get a fast error, so the source keeps serving the rest.

Some caches must *fail closed* instead, which means the request fails when Redis fails. A rate limiter keeps its counters in Redis, so Redis is the source of truth and there is nothing to fall back to. If it fails open, every tenant runs with no limit during the outage. Fail closed when the cache holds a decision that is unsafe to skip. You then accept that the feature stops whenever Redis is down.

The source must survive every miss, and an outage turns every read into one.

Failing open still sends full load to the source and waits a timeout per request.

Find ReadTimeout and MaxRetries in your Redis client, and multiply them.

**Go deeper: a tuned circuit breaker, why 6 s and not 12 s, key versions, per-field TTLs, and measuring the hit rate**

**Shopify** showed why the breaker needs tuning. It modelled circuit breakers for 42 Redis instances, each with its own circuit. With the first configuration, a worker needed 263% extra utilization while all of Redis was down. After tuning, it needed 4%. The tuning cut the half-open timeout to 50 ms, because 99% of their Redis requests answer in under 50 ms. It also raised the error timeout to 30 s.

**Why the default costs about two timeouts.** In go-redis v9.5.1, `_process` marks a read timeout as retryable, at `redis.go` lines 426 to 431. The retry opens a new connection. A paused server still accepts the TCP connection, but the `HELLO` handshake in `initConn`, at line 303, then times out. That error comes from `getConn`, outside the retry flag, so the client does not retry again. So the default cost is two read timeouts, about 6 s. This chain is inferred from the source code. Nobody traced it step by step with a debugger.

The lab's `cache_aside` program passes `ReadTimeout: time.Second` when it creates the client, so it does not use the 3 s default. The other `phase02_caching` programs use the defaults. At v9.23.0, `options.go` lines 735 to 768 set the 5 s read timeout default.

**Key versions in practice.** Exercise E11 writes a `v1` and a `v2` key and lists both with `KEYS`. Use `KEYS` only on a sandbox, because it scans the whole keyspace on the one command thread and blocks every other client. A version bump also causes a cold start for that key family. Every key misses once after the deploy, so the multiplier from the first section applies to that family. Roll a bump out to a share of pods first if the family is hot. That rollout advice is inferred from the multiplier, not from a measured case.

**A TTL on every key.** A key with no TTL stays until something deletes it. On the platform, keys with no TTL filled a shared cluster to 100% of memory, and a shared upload service was down for 4 hours 37 minutes. That figure is from the platform and not checked. **Pendo** published the same failure. Two code paths created cache keys with no expiry, so Redis ran near its memory limit and evicted keys, which means it deleted keys to make room. CPU spikes then caused slow replies and connection failures, with an error rate near 60% for 90 minutes on its guides service. They flushed all Redis instances, then fixed the two code paths. `TTL key` returns -1 for a key with no expiry and -2 for a key that does not exist. `SET k v KEEPTTL` changes the value and keeps the current expiry. Phase 5 covers eviction.

**A TTL per hash field.** A tenant's settings can be one hash with one field per setting. Since Redis 7.4.0, `HEXPIRE` gives each field its own TTL. Since Redis 8.0.0, `HGETEX` and `HSETEX` read or write a field and set its TTL in one command. Valkey, the open-source fork of Redis, added `HEXPIRE` in 9.0.0.

**Measuring the hit rate.** `INFO stats` reports `keyspace_hits` and `keyspace_misses`, and E12 computes hits / (hits + misses). Those counters cover every read on the server, including lock reads and reads by other services. So the server number can hide one cache whose hit rate fell. Keep a hit counter and a miss counter for each cache in your application. That advice is inferred, not taken from a measured case.

**A fail-closed exception.** On the same platform, almost every cache read failed open. One profile read wrapped Redis errors in an exception and threw it again, so a Redis blip failed those requests. When you review cache code, look for the path that differs from the rest.

**Evidence**

Timing table: measured by the study note on 2026-10-18, one Mac, an x86_64 Homebrew build of Redis 8.10.1 under Rosetta 2 outside Docker, paused with `SIGSTOP`, go1.27.1, go-redis v9.5.1. Do not treat these as general numbers. Defaults: go-redis `options.go` at v9.5.1 and at v9.23.0. Uber: "How Uber Serves Over 40 Million Reads Per Second from Online Storage Using an Integrated Cache", 2024-02-15. Shopify: "Your Circuit Breaker is Misconfigured", Damian Polan, 2020-02-18. The post is a model, not an incident. Pendo: status page incident, 2020-02-21. `HEXPIRE` and `HGETEX`: redis.io command pages, "Available since". Valkey `HEXPIRE`: `src/commands/hexpire.json` at Valkey 9.1.2.

- [go-redis v9.23.0 options.go](https://raw.githubusercontent.com/redis/go-redis/v9.23.0/options.go)

- [Uber CacheFront](https://www.uber.com/en-GB/blog/how-uber-serves-over-40-million-reads-per-second-using-an-integrated-cache/)

- [Shopify, Your Circuit Breaker is Misconfigured](https://shopify.engineering/circuit-breaker-misconfigured)

- [Pendo incident](https://status.pendo.io/incidents/g8nfbs1vdn69)

- [HEXPIRE](https://redis.io/docs/latest/commands/hexpire/)

- [HGETEX](https://redis.io/docs/latest/commands/hgetex/)

So far the misses were spread over many keys. One key that every request reads behaves differently when it expires, and the next section shows how.

## What happens when a key that every request reads expires?

The first concept treated misses as spread over many keys. A *hot key* is one key that a large share of requests read, so its misses arrive together. In the running case it is `agent:config:v1`, the routing table that every agent run reads. It gets all 5,000 reads per second, and rebuilding it takes a 200 ms query that joins several tables.

A *cache stampede*, also called a *thundering herd*, starts when a hot key is missing. This lesson uses the name cache stampede, or stampede for short. Every request that arrives before the first rebuild finishes also misses, and each one starts its own rebuild. They all do the same expensive work to get the same answer. The fix is *request coalescing*, which makes concurrent requests for the same key share one rebuild. Go's *singleflight* package is the common first tool for it. It merges concurrent calls that use the same key inside one process. Only the first caller runs the rebuild, and the others wait for its result.

**Predict: all 40 pods wrap the rebuild in singleflight. The key gets 5,000 reads per second, and the rebuild takes 200 ms. How many Postgres queries run when the key expires?**

Up to 40, one per pod. Without singleflight it would be about 1,000, because 5,000 × 0.2 s of requests arrive during one rebuild. Most people answer 1, because they picture singleflight as a lock for the whole fleet. Its map of in-flight calls lives in one process, so each pod coalesces only its own requests.

Here is the expiry as it happens, without any protection.

- t = 0 s The key is cached, and all 5,000 reads per second hit Redis. Postgres is nearly idle.

- t = 3,600 s The TTL ends, and every read of the key now misses.

- next 200 ms About 1,000 requests miss, and each one sends the same join to Postgres.

- after that Postgres was sized for about 100 queries per second, so its CPU and connection pool run out. Each rebuild now takes longer than 200 ms, so even more requests arrive during it and miss.

The size of a stampede follows from that timeline. Each independent filler that misses during the rebuild time starts one rebuild. So the count is about 1 + rate × rebuild time, counted in the scope where fillers can see each other. When Postgres slows down, the rebuild time grows, and the stampede grows with it. That feedback is why a stampede can turn a slow query into an outage.

singleflight works with one map per process. `singleflight.Group.Do` keeps a map from each key to its call in progress. A second caller with the same key adds one to the call's `dups` count. It waits on the call's `WaitGroup`, and then it receives the same value and error.

```go
// Instead of 1,000 goroutines each calling the source:
v, _, _ := g.Do(key, func() (interface{}, error) {
    val, err := loadFromSource()        // only the FIRST caller runs this
    if err == nil { rdb.Set(ctx, key, val, ttl) }
    return val, err                     // the other callers wait here and get this
})
```

- no protection: ~1,000

- singleflight: up to 40

- shared lease: 1

Postgres queries for one expiry of `agent:config:v1`, from the arithmetic above. Illustration, not measured.

Exercises E3 and E4 show the single-process result. 200 concurrent misses make 200 source calls without singleflight and 1 with it, and 1,000 misses still make 1. One process is the easy case, and 40 pods make 40 calls. The cross-pod version is the subject of the next section.

The strongest public number comes from **Facebook**'s memcache fleet. For a set of keys that were "particularly susceptible to thundering herds", that is, to cache stampedes, measured over one week, the peak database query rate was 17K/s without the fix that Facebook calls a *lease*. A lease is a short-lived token that the cache gives to one reader that missed, so only that reader fills the key. With leases the peak was 1.3K/s, and the next section shows how a lease works.

**Evidence**

singleflight: `golang.org/x/sync` v0.22.0, `singleflight/singleflight.go`, lines 91 to 113, read in the module cache. That the map is per process is inferred from that code. Leases: "Scaling Memcache at Facebook", NSDI 2013, section 3.2.1. The paper does not give the key count or the traffic for that set of keys. E3 and E4: three runs each by the study note, 200 to 1 and 1,000 to 1.

- [singleflight package docs](https://pkg.go.dev/golang.org/x/sync/singleflight)

- [Scaling Memcache at Facebook](https://www.usenix.org/system/files/conference/nsdi13/nsdi13-final170_update.pdf)

**Go deeper: singleflight's edges, and a platform with no stampede protection**

**A second call can still slip in.** The lab's goroutine runs `GET` first and calls `Do` only on a miss. A goroutine whose `GET` misses just before the winner's `SET`, and that calls `Do` just after the winner's call ends, starts a second rebuild. The window is small, so the lab usually prints 1. This edge is inferred from the code, not measured.

**Errors are shared too.** Every waiting caller receives the winner's error. If the rebuild times out, all of them fail together. `DoChan` returns a channel, so a caller can stop waiting at its own deadline. `Forget` removes a key from the map, so the next caller starts a fresh call instead of joining a stuck one.

**A platform with no stampede protection.** On the platform, the Redis path had no request coalescing, no lock around cache fills, no refresh before expiry and no random spread of TTLs. Every TTL was a fixed constant. The only coalescing was in local loading caches, such as Guava's `LoadingCache`, which merge concurrent loads inside one JVM. So the shared Redis caches for settings and for the hot endpoint were exposed to exactly this stampede. It also explains why the bypass flag multiplied load at once. With no coalescing, every concurrent request went straight to the source. These findings come from a code review of that platform and are not checked here.

**Hot keys at larger scale.** When one key's reads are too many for one Redis node, coalescing is not enough. The fixes are a local copy of the value in each process, or several copies of the key on different nodes. Phase 5 covers hot keys.

singleflight leaves one rebuild per pod. To get one rebuild for the whole fleet, the pods need a marker that they all can see.

## How do 40 pods share one rebuild?

singleflight cut the stampede to one rebuild per pod, which is still 40 queries per expiry. A fix for the whole fleet has two options. It can put the coalescing where every filler can see it. Or it can send every request for one key to the same process. There are four common designs.

**A lease in the cache**

The first reader that misses claims a short-lived marker in the cache, and only that reader rebuilds. Facebook's memcache returns a lease token "only once every 10 seconds per key". Other clients get a notification "telling the client to wait a short amount of time", and then they read again.

**Serve the old value**

The cache keeps the old value while one caller rebuilds it. Memcache can return a recently deleted value marked as stale. In its words, "Applications that can continue to make forward progress with stale data do not need to wait".

**Route by key**

Every request for one key goes to the same process, so coalescing inside one process works for the whole fleet. **Discord** built data services in Rust that coalesce requests, and routes requests by channel ID with consistent hashing. So one instance coalesces each channel.

**Refresh before expiry**

With an *early refresh*, each reader may refresh the key a little before its TTL ends, with a chance that rises as expiry gets closer. One reader refreshes early while the key is still valid for everyone else. The best-known rule for that chance is called *XFetch*, or probabilistic early expiry.

In Redis the lease uses the command from Phase 1. The reader that misses runs `SET agent:config:v1:lease <random> NX PX 5000`. If it gets OK, it rebuilds the key. Then it deletes the lease only if the lease still holds its own token. A plain `DEL` could remove a newer lease that another pod took after this one expired. Phase 3 teaches this safe release. If it gets nil, another pod is already rebuilding. The pod that lost either waits a short time and reads again, or it serves an old copy. The Redis blog post "Caches, Promises and Locks" builds the waiting with *pub/sub*, the Redis feature where a client publishes a message to a channel and every client subscribed to that channel receives it. The winner publishes when the value is ready, so waiting pods do not poll. The lease's `PX 5000` limits the damage if the winner dies, because the lease expires and another reader can try.

The phase said XFetch means "there's never a moment where the key is absent". That holds only for a key that is read often near its expiry. A cold key still expires before anyone refreshes it. A simulation of the XFetch rule used a 0.1 s rebuild and a 60 s TTL. At 0.5 requests per second, 94.5% of cycles still had a hard miss.

The XFetch rule itself, with its `delta` and `beta`, is in the Go deeper block below. For a hot key, XFetch works well. With `beta = 1` on a real request trace, most stampedes had a size of 1 or 2, and "no stampede is larger than 8". The same simulation found about 2.7 recomputes per expiry at any rate from 100 to 1,000 requests per second. So XFetch fits hot keys, and a lease fits every key.

- **Can a reader use a value that is a few seconds old?**

- *yes*Serve the old value, and let one lease winner rebuild it.

- *no*Is the key read many times during one rebuild?

- *yes*Use XFetch, or a lease with waiting readers.

- *no*Use a lease. XFetch rarely fires on a cold key.

The routing table in the running case may be a few seconds old, because a new route can wait one more rebuild. So `agent:config:v1` gets a long Redis TTL and a lease for the rebuild. It also stores a five-minute expiry time inside the value. After that time a reader still returns the old value, and it tries to take the lease. Postgres then sees one query per refresh instead of 40.

**Evidence**

Leases and stale values: "Scaling Memcache at Facebook", NSDI 2013, section 3.2.1. Promises: Redis blog, "Caches, Promises and Locks", 2019-05-29. It summarises Instagram's "Thundering herds and promises" post, which the study note could not fetch. Discord: "How Discord Stores Trillions of Messages", Bo Ingram, 2023-03-06. The post gives no coalescing numbers in its text, and says hot partitions still happened, "just not quite as frequently". XFetch: Vattani, Chierichetti and Lowenstein, "Optimal Probabilistic Cache Stampede Prevention", PVLDB 8(8), 2015, Figure 3 for the rule and section 6 for the Goodreads results. Conditions of that result: one item with a 10 s recompute and about 0.07 s between requests. The 2.7 and 94.5% figures come from the study note's own Python simulation of the Figure 3 rule, 2,000 cycles per row. It used Poisson arrivals, a 60 s TTL, `beta = 1`, and a rebuild of 0.1 s or 1 s. The reviewer ran it again on 2026-10-18 and got the same numbers.

- [Caches, Promises and Locks](https://redis.io/blog/caches-promises-locks/)

- [How Discord Stores Trillions of Messages](https://discord.com/blog/how-discord-stores-trillions-of-messages)

- [Optimal Probabilistic Cache Stampede Prevention](https://cseweb.ucsd.edu/~avattani/papers/cache_stampede.pdf)

**Go deeper: serving the old value, the XFetch rule in code, and the lab that gets it wrong**

Serving the old value needs two expiry times. The real TTL in Redis stays long, for example one hour. A logical expiry inside the value, for example five minutes, tells a reader that the value is old. A reader that sees an old value returns it at once and tries to take the lease. Only the lease winner reads Postgres. This combination is inferred from the designs above, not taken from one published system.

XFetch has a precise rule. A reader recomputes when `now − delta × beta × ln(rand()) ≥ expiry`. Here `delta` is the time the last rebuild took, stored with the value, and `beta` is a tuning factor with default 1. `ln(rand())` is negative, so each reader acts as if the time were a little later than it is. A long rebuild makes the early window wider.

In Go the rule fits in a few lines. The value carries `delta` and its logical expiry. This code is an illustration of the Figure 3 rule, and it was not run.

```go
// XFetch: recompute early with a probability that rises near expiry.
// delta = how long the last recompute took. beta = 1 by default.
func shouldRefresh(now, expiry time.Time, delta time.Duration, beta float64) bool {
    u := 1 - rand.Float64() // in (0, 1], so math.Log never sees 0
    gap := time.Duration(-float64(delta) * beta * math.Log(u))
    return !now.Add(gap).Before(expiry) // now + gap >= expiry
}
```

A larger `beta` refreshes earlier and more often. A value below 1 refreshes later and risks more hard misses. Each early refresh is one extra source read, so the cost is a few extra reads per TTL on a hot key.

The second lab folder, `phase02_caching_patterns/thundering_herd`, has an XFetch part that does not implement this rule. Line 108 uses `remaining > entry.Delta`, so the decision is fixed, not random. All 5 callers inside the window refresh. The program prints "DB calls = 5", and then it prints that "0 goroutines ever see a miss". The comment at line 105 also has the sign wrong. If you run it, expect 5 calls, and read the code above for the real rule. The header of that file calls XFetch "distributed dedup", which it is not. XFetch does not coordinate processes. It only makes their refreshes unlikely to overlap.

A lock that other pods poll, the phase's original cross-pod answer, is the lease with polling. Phase 3 teaches locks in depth: `SET NX PX`, a safe release, and what happens when the holder pauses past its TTL.

Coalescing handles one hot key. It does not help when thousands of different keys expire in the same second, which is the next problem.

## Why do keys warmed together expire together, and what does jitter fix?

A lease coalesces the rebuilds of one key. A deploy can cause a different stampede, made of many keys that each miss once at the same moment. In the running case, a deploy job warms the settings of all 50,000 tenants, each key with a flat `EX 3600`. For 59 minutes everything is fine. In minute 60 all 50,000 keys expire within the same second or two, and the next read of each one misses.

That is a spike of up to 50,000 Postgres reads in a few seconds, against a source sized for about 100 per second. The deploy set the timer, so the spike repeats one TTL after every deploy. A canary or a staging test rarely shows it, because few keys are warmed there and the test seldom runs for a full TTL. The fix is *TTL jitter*, a random part added to each key's TTL. Each key gets the base TTL plus or minus a random amount, so the expiries spread over a window.

```go
// base 3600 s, jitter 300 s: each key expires between 3300 s and 3900 s.
ttl := base + time.Duration(rand.Int63n(int64(2*jitter))) - jitter
rdb.Set(ctx, key, val, ttl)
```

Illustration, not run.

Exercise E5 measures the spread for 1,000 keys with a base of 600 s and a jitter of 60 s. With a fixed TTL, all 1,000 keys fall in one expiry second. With jitter, they fall in 121 different seconds, with about 7 to 9 keys in each.

- fixed TTL: 1,000 in 1 s

- 600 ± 60 s: ~8 per s

Keys expiring in the busiest second, out of 1,000, from the E5 output.

Jitter solves the many-keys problem and does nothing for one hot key. A hot key with a jittered TTL still expires once, and all its readers still miss together. So `agent:config:v1` needs the lease from the section above, and the 50,000 tenant keys need jitter. Most real caches need both.

The spike also costs Redis CPU, because Redis deletes expired keys in a background cycle. In exercise E6, 1,000 keys with the same TTL disappeared in about 0.1 s, before any read touched them. The Go deeper block below shows how that cycle works and when it blocks other clients.

Count the fillers that miss during one rebuild, and coalesce where they all meet.

singleflight fixes a stampede inside one pod, and 40 pods still send 40 queries.

Run E3 and then E5, and compare 1 source call with 121 expiry seconds.

**Go deeper: how Redis expires keys, settings in Redis and Valkey, and expiry storms**

Redis removes expired keys in two ways. *Lazy expiry* deletes a key when a command touches it after its TTL. *Active expiry* is a background cycle that samples keys with a TTL and deletes the expired ones. In exercise E6, `INFO` reported `expired_keys_active:1000`, which counts the keys that this cycle removed.

- The cycle samples 20 keys with a TTL in each loop.

- It repeats while more than 10% of the sampled keys were already expired, so a mass expiry keeps it looping.

- The slow cycle may use up to 25% of CPU per tick, which is 25 ms at the default `hz 10`. A fast cycle of up to 1 ms can also run each time the event loop, the loop in which the main thread serves clients, is about to wait for input. It runs at most once every 2 ms.

- Each delete of a large value runs on the main thread when `lazyfree-lazy-expire` is `no`, the Redis default. So a mass expiry of large values adds latency to every client.

The Redis latency documentation lists many keys expiring in the same second as one cause of latency. The active cycle is the reason. While more than 10% of sampled keys are expired, it keeps sampling, up to its time limit.

`active-expire-effort` goes from 1 to 10, and the default is 1. Each step adds 25% more keys per loop and 25% more fast-cycle time, adds about 2% CPU, and lowers the stale target by 1%. Raise it only if `INFO` shows many expired keys still in memory.

Valkey 9.1.2 sets all `lazyfree-lazy-*` options to `yes` by default, so its deletes of large values run in a background thread. Redis 8.10.2 sets them to `no`. Asynchronous free happens only when a value's free effort is above 64. For a set, sorted set or hash in its large encoding, the internal layout that Redis picks by size, the effort is its element count. For a list, it is the number of internal list nodes. A small value in a compact encoding counts as 1, so Redis always frees it at once. If you run Redis and cache large hashes or lists, set `lazyfree-lazy-expire yes`.

A key can stay in memory after its TTL until a lookup or a sample finds it. On a replica, an expired key looks missing to readers but still holds its memory until the primary, the node that takes the writes, sends the delete. So `DBSIZE` and memory can lag behind the TTLs you set.

Jitter has a price too. Some keys now live up to one jitter period longer, so the longest stale window grows by that amount. With a base of 3,600 s and a jitter of 300 s, a missed delete can leave a value stale for up to 3,900 s.

**Evidence**

E5 and E6: study note runs on the same x86_64 build under Rosetta 2. E6 used `EX 5` instead of the phase's `EX 30`. Active expiry constants: `src/expire.c` lines 96 to 100 and 292 to 300, and `src/server.c` line 1315, at Redis tag 8.10.2. Lazyfree defaults: `src/config.c` at Redis 8.10.2 and Valkey 9.1.2, and `src/lazyfree.c` lines 168 to 235. The canary sentence and the 3,900 s figure are inferred from the mechanism.

- [Redis docs, Diagnosing latency issues](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/)

Both stampede problems are about many fills at once. The next concept is about one fill that arrives too late, and it breaks the rule that the phase called race-free.

## Is deleting the key on every write race-free?

The stampede sections counted fills that arrive together. Here the problem is a single late fill. In the running case an admin removes the `web_search` tool from tenant 42. The settings service updates Postgres, and then it deletes `tenant:42:settings:v1` so that the next read fills fresh data.

That rule is called *delete-on-write*: on every write to the source, delete the cache key instead of updating it. The TTL stays as a backstop. The phase gives two good reasons to delete rather than update.

- A delete is cheap. The writer does not rebuild the cached value, which may need an expensive join, and the next reader rebuilds it lazily.

- Updates from two writers can interleave. Writer A reads its data, writer B reads, B writes the cache, and A writes the cache last. The cache now holds A's value, although B's write was newer. Two deletes cannot leave a wrong value behind.

The TTL backstop is still needed, because a delete is best effort. The delete can fail during a Redis blip, a new code path can forget it, or someone can write a key directly. The TTL bounds how long any of those bugs can serve stale data.

**Predict: the settings service updates Postgres, then deletes the key. The TTL is one hour. Can an agent still see web_search as allowed for an hour after the admin's change?**

Yes. It happens if a reader missed before the write and filled after the delete. The reader read the old row, the writer changed the row and deleted the key, and then the reader wrote the old row into Redis with a fresh one-hour TTL. Nothing deletes it again. Most people answer no, because the delete runs after the database write, so they expect the next read to see new data.

**A reader's fill lands after the writer's delete**

reader:
[GET: nil] [read old row] [SET old EX 3600]

writer:
[UPDATE row] [DEL: 0]

Redis key:
[empty] [empty] [empty] [empty] [old, 1 h]

Step 1: the reader misses, because the key had expired.

Step 2: the reader reads the row from Postgres, and web_search is still allowed.

Step 3: the admin's change updates the row in Postgres.

Step 4: the writer deletes the key, and DEL returns 0 because the key is absent.

Step 5: the reader writes the old row, so Redis serves it for the next hour.

The order of events in the race between a late fill and a delete. Steps are not to scale.

The phase said delete-on-write is "cheaper and race-free" and that "the next read always pulls the current source truth". It is cheaper, and it removes the race between two writers. It does not remove the race between a reader's fill and a writer's delete. This holds for every Redis and Valkey version. The fix in the next section needs Redis 8.4.0 or later, Valkey 8.1.0 or later, or a Lua script, a small program that Redis runs as one atomic step.

The cost in production is a wrong value for a full TTL, with no error anywhere. With a one-hour TTL, that is up to one hour of a wrong price, permission or setting. For an agent platform the removed tool keeps running, which is a security problem and not only a freshness problem. The race needs a reader whose fill is slow. So it is rare on a quiet key, and more common on a key that is busy and changes often.

**Uber** met this race in CacheFront, the Redis cache inside its Docstore database layer. Fills on the read path and invalidations from *change data capture*, a stream of row changes read from the MySQL binlog, both write the cache. The team wrote that "it is possible that we inadvertently write a stale row to the cache, overwriting the newest value". Their fix is a Lua script that writes a row into the cache only if its timestamp is newer than the cached one. Shadow reads, which compare a share of cached reads with the database, measured 99.99% consistency.

**Evidence**

The race: MIT 6.824 memcache FAQ, which ends its eight steps with "Now memcache has a stale version of k, and it may never be updated". It also says the two-writer problem "doesn't arise if C1 and C2 delete() instead of put()". Uber: the CacheFront post from the fail-open section, 2024-02-15. The "rare on a quiet key" sentence is inferred from the timing the race needs, not measured.

- [MIT 6.824 memcache FAQ](https://pdos.csail.mit.edu/6.824/papers/memcache-faq.txt)

**Go deeper: the same race at Meta, and what Uber found later**

**Meta** watches the consistency of its TAO cache with a system called Polaris. One Polaris alarm showed the cache holding "metadata=0 @version 4" while the database held "metadata=1 @version 4". A cache fill had interleaved with a rare transaction. Then `drop_cache(key, version)` did nothing, because the cached item already carried the latest version number. The team found the cause in under 30 minutes with consistency tracing. With this work, TAO went from 99.9999% to 99.99999999% of cache writes consistent within five minutes. A version check is only as good as the version: two different values with the same version defeat it.

**Uber** later published what still went wrong at over 150 million reads per second. Change data capture is asynchronous, so a read right after a write could return the old value. A slow Redis node could make an invalidation fail, and the stale value then stayed until its TTL ended. A fill from a database follower that lagged behind could store old data. And the explicit invalidation API used generated clock values instead of row timestamps, so later fills failed the timestamp check.

Uber changed four things. The write path now returns the changed row keys and the commit timestamp, and the query layer invalidates those rows at once. Invalidation writes a marker value instead of deleting the key, so a late fill cannot replace it. TTL expiry, change data capture and the write path all invalidate now. A tool called Cache Inspector measures staleness, and one table reached over 99.9% hit rate after its TTL rose to 24 hours. The post also says that even a short TTL can still show high staleness. A shorter TTL lowers the hit rate and only shortens the stale window. It does not remove the race.

**Evidence for the extra cases**

Meta: "Cache made consistent", Lu Pan, 2022-06-08. Uber: "How Uber Serves over 150 Million Reads per Second from Integrated Cache with Stronger Consistency Guarantees", 2025-08-26. The short-TTL point is from that post. The hit-rate cost is inferred.

- [Meta, Cache made consistent](https://engineering.fb.com/2022/06/08/core-infra/cache-made-consistent/)

- [Uber, 150 million reads per second](https://www.uber.com/us/en/blog/how-uber-serves-over-150-million-reads/)

Deleting at the right time is not enough, because the reader's fill comes later. The fix is to make the fill itself conditional, which the next section builds from two Redis commands.

## How does a fill prove that nothing changed since its miss?

The race needs two things: a read of the source that started before the write, and a fill that lands after the delete. So the fix is a *conditional fill*, a cache write that succeeds only if no invalidation happened since the reader's miss. Facebook's memcache does this with the lease from the stampede sections, the token that only one reader gets. The paper describes it as "a 64-bit token bound to the specific key". A delete of the key cancels the token, and a fill that carries a cancelled token is refused.

Redis can do the same with two plain commands since version 8.4.0. `SET` there has an *`IFEQ`* option, which sets the key "only if its current value is equal to ifeq-value". If the key does not exist, `SET ... IFEQ` does not create it. The lease then takes three steps.

- **The reader claims the fill.** On a miss it runs `SET tenant:42:settings:v1 lease:<random> NX PX 5000`. OK means this reader may fill. Nil means another reader holds the lease, so this one waits briefly or reads Postgres without filling.

- **The writer invalidates.** It updates Postgres first and then runs `DEL tenant:42:settings:v1`. The delete removes the lease too.

- **The reader fills only if its lease is still there.** It runs `SET tenant:42:settings:v1 <value> IFEQ lease:<random> EX 3600`. If a writer deleted the lease, the command returns nil and writes nothing. The key stays empty, so the next read fills fresh data.

Readers must treat a value that starts with `lease:` as a miss, and wait or read the source. The order in step 2 matters as well. Suppose the writer deletes first and updates Postgres second. Then a reader can miss and fill the old row in between, and no lease protects that gap.

The race and the fix were run step by step with `redis-cli`. The plain fill writes the old value back. The lease fill is refused, and the cache stays empty.

| Step | Plain cache-aside | Lease with `SET IFEQ` |
|---|---|---|
| Reader misses | `GET` returns nil | `SET NX PX 5000` returns OK |
| Writer deletes | `DEL` returns 0 | `DEL` returns 1 |
| Reader fills the old value | `SET ... EX 3600` returns OK | `SET ... IFEQ` returns nil |
| Cache after the race | `v1`, TTL 3600 | empty, so the next read fills fresh data |

With no writer, the same lease fill returned OK, and a second reader's `SET NX` returned nil. That second result matters for the stampede sections too. Only one reader per key wins the lease, so the lease also coalesces fills across all 40 pods.

The TTL now has a smaller job. It no longer hides the race. It only bounds the damage from a delete that never ran, such as a failed `DEL` or a code path that forgot to invalidate. Other systems use the same idea with a different token. Uber's Lua script compares row timestamps, and Meta's TAO compares version numbers. In each design, the fill must carry proof that it is not older than what the cache already knows.

**Evidence**

Lease: "Scaling Memcache at Facebook", NSDI 2013, section 3.2.1, which also says "Verification can fail if memcached has invalidated the lease token due to receiving a delete request for that item". `SET IFEQ`: the redis.io SET page and `src/commands/set.json` at Redis tag 8.10.2. Table: run by the study note with `redis-cli` against an x86_64 Homebrew build of Redis 8.10.1 under Rosetta 2, outside Docker, on 2026-10-18, by hand, one step at a time. It was not tested with concurrent Go clients. The order rule is from the study note. Its reason is inferred from the race.

- [Redis SET command](https://redis.io/docs/latest/commands/set/)

- [set.json at Redis 8.10.2](https://raw.githubusercontent.com/redis/redis/8.10.2/src/commands/set.json)

**Go deeper: Redis and Valkey versions, generation keys, and layered TTLs**

**Which version has which command.** Redis has `IFEQ`, `IFNE`, `IFDEQ` and `IFDNE` on `SET` since 8.4.0. The two `D` forms compare a hash digest of the value instead of the value itself. The digest is an XXH3 hash, and the `DIGEST` command returns it. Redis 8.4.0 also added `DELEX key IFEQ value`, a delete that runs only if the value matches. Valkey has `SET ... IFEQ` since 8.1.0, and its 9.1.2 release has no `IFNE`. Valkey's matching delete is `DELIFEQ`, since Valkey 9.0.0. So lease code that uses only `SET IFEQ` runs on both. The lab's `docker-compose.yml` pins `redis:7.2`, which has none of these, so on 7.2 the conditional fill needs a short Lua script.

**TTL-only invalidation.** The simplest design deletes nothing and accepts staleness up to one TTL. It fits values that change rarely or where old data is harmless, such as a vendor's list of voices. A settings change then becomes visible within one TTL, not at once.

**Write-through as invalidation.** The writer updates the cache instead of deleting the key. The cache is fresh by construction when only one writer runs. But it pays the write latency, and it has the two-writer race from the section above, which is why delete is the usual choice.

**Generation keys.** One version key per scope, such as `scope:tenant:42`, holds a generation number. Every cache key for that tenant includes the number, so a write that changes the number makes all of the tenant's keys unreachable at once. Their TTLs remove them later. The lab `phase02_caching_patterns/invalidation_scope` builds this. Each read costs two round trips, one for the version and one for the value. The lab's first access sets the version with `Set` and no `NX`, at line 41, so two first callers can create two versions. Use `SET NX` there. The version key has no TTL in that lab. If it expired, the next read would create a new version, which would invalidate the whole scope at once.

**Layered caches with different windows.** The platform kept company settings in three layers. The service that owned the settings deleted a Redis scope marker on every settings write, which invalidated every key under it. A shared client library, used by every Java service, cached responses with a one-hour TTL as the backstop. A serverless consumer kept its own copy with a pure 10-minute TTL and no invalidation at all. There was no pub/sub or event-based invalidation in the chain.

| Layer | TTL | Kind |
|---|---|---|
| local map in the owning service | 5 min | process memory |
| local loading cache in another service | 10 min | process memory |
| serverless consumer's own copy | 10 min | Redis, TTL only |
| shared client library | 1 hour | Redis, with delete |
| shared cluster default | 30 min to 1 hour | Redis, TTL only |

An admin's change was visible at once through the shared library, because the delete ran. Through the serverless consumer it took up to 10 minutes. If the delete failed, the one-hour TTL bounded the staleness. Every TTL was a fixed constant with no jitter, so the expiry spike from the section on jitter applied too. These details come from the platform's code and are not checked here. Ask the same questions of your own design. Which layer catches a missed delete, and how long is the worst case?

**Evidence for versions**

Valkey: `src/commands/set.json` at tag 9.1.2, and the Valkey docs for `SET` and `DELIFEQ`. valkey.io says `IFNE` arrives in 9.2.0. On 2026-10-18 the GitHub releases list showed only 9.2.0-rc1, a release candidate, so no stable Valkey has `IFNE` yet. The `D` forms: the redis.io `SET` and `DELEX` pages. `DELIFEQ` since 9.0.0: `src/commands/delifeq.json` at Valkey 9.1.2. `DELEX`: the redis.io command page. Generation-key lab: lines read in the source, not run.

- [set.json at Valkey 9.1.2](https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/src/commands/set.json)

- [Valkey SET](https://valkey.io/commands/set/)

- [Valkey DELIFEQ](https://valkey.io/commands/delifeq/)

- [Redis DELEX](https://redis.io/docs/latest/commands/delex/)

The lease fixes the race for fills that go through Redis. Two other channels also tell caches about changes, and each one has the same race or a weaker promise.

## Do the two ways Redis tells clients about changes avoid the race?

The lease protects fills that go through Redis. Many services also keep a second copy in a *local cache*, a cache in the memory of their own process, and they need a way to learn that the Redis copy changed. Redis offers two channels for that, and neither one removes this kind of race.

*Client-side caching* in Redis, turned on with the *`CLIENT TRACKING`* command, lets a client keep values in its own memory. Redis remembers which keys each client read, and it sends that client an invalidation message when one of those keys changes. When the client uses one connection for data and a second one for invalidation messages, the two can arrive out of order. The invalidation for a key can arrive before the reply that carries the old value. The client then stores the old value after it already threw away the invalidation.

The Redis documentation fixes this with a placeholder, which is the lease idea again. Before it sends the read, the client sets "the local copy of 'foo' to 'caching-in-progress'". If an invalidation arrives, it removes the placeholder. When the reply arrives, the client stores the value only if the placeholder is still there.

*Keyspace notifications* are pub/sub messages that Redis publishes when keys change or expire. The documentation calls pub/sub "fire and forget", so a subscriber that is disconnected for one second loses that second's messages. It also gives "no guarantees" that an `expired` event fires when the TTL reaches zero. The event fires when Redis actually deletes the key, which can be later.

The phase linked keyspace notifications as "an alternative to delete-on-write". They cannot carry invalidations safely. Use them for hints and metrics, never as the only invalidation path.

| Channel | How a change reaches the cache | What it promises | Its race or gap |
|---|---|---|---|
| Delete on write | the writer's `DEL` | best effort: it can fail or be forgotten | a reader's late fill, fixed by a lease |
| TTL | Redis expiry | always ends the stale value, after up to one TTL | stale for up to one TTL |
| Change data capture | a consumer reads the database log and updates the cache | as reliable as the consumer and its position in the log | a fill against a log write, fixed by a timestamp check |
| `CLIENT TRACKING` | Redis pushes a message to the client | lost while the client is disconnected | invalidation before reply, fixed by a placeholder |
| Keyspace notifications | pub/sub | fire and forget | lost events, and late expired events |

The pattern is the same in every row that has a race. A channel can change the cache after a read has started. So the read must carry a marker, a version or a timestamp, and a late write must lose. In the running case the settings service keeps delete-on-write with a lease. It keeps the one-hour TTL as the backstop, and it does not rely on keyspace notifications. A tool removal is then visible on the next read after the delete.

A fill must prove that no invalidation ran since its miss.

Delete-on-write plus a TTL can still serve a removed permission for the whole TTL.

Run E10, then repeat it with the lease commands from the table above.

**Go deeper: tracking modes, reconnects, and change data capture**

`CLIENT TRACKING` exists since Redis 6.0. In the default mode, Redis keeps a table of which client read which key, and that table costs server memory. In broadcasting mode, a client subscribes to key prefixes instead, and Redis sends every change under those prefixes. Broadcasting costs no per-key table on the server, but the client receives messages for keys it never read. The optional OPTIN and OPTOUT modes let a client choose which reads are tracked.

A local cache must assume it missed messages whenever its invalidation connection drops. The Redis documentation gives the safe reaction. Flush the local cache when the connection is lost. Also ping the invalidation connection, and close it and flush if no reply comes back in time. A maximum local TTL is a second guard, so a missed message cannot keep a value forever. That last rule is inferred, not taken from the documentation.

Change data capture moves invalidation out of the application. Uber's Flux reads MySQL binlogs and updates the cache within seconds. CacheFront's default TTL is 5 minutes. The application no longer has to remember to delete, so a forgotten code path cannot leave a stale value. But the stream is asynchronous, so a read right after a write can still see the old value. Uber added invalidation on the write path for that reason, as the section on the race showed.

**Evidence**

Client-side caching: the redis.io client-side caching reference, including the "caching-in-progress" fix. Tracking since 6.0.0: the `CLIENT TRACKING` command page, "Available since", and `src/commands/client-tracking.json` at Redis 8.10.2. Keyspace notifications: the redis.io keyspace notifications page, for "fire and forget" and "no guarantees". Flux and the 5-minute TTL: Uber's CacheFront post. The default mode, broadcasting, OPTIN, OPTOUT and the flush on a lost connection: the client-side caching reference and the `CLIENT TRACKING` page, both read by the reviewer on 2026-10-18.

- [Redis client-side caching](https://redis.io/docs/latest/develop/reference/client-side-caching/)

- [Redis keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)

All the cache entries so far held rows that exist. The last concept is about requests for rows that do not exist, and the entry you store for them.

## What should the cache store for a row that does not exist?

Every concept so far was about rows that exist. Cache-aside fills the cache only when the source returns a row. So a request for a tenant ID that does not exist misses Redis, misses Postgres, and leaves nothing behind. The next request for the same ID repeats all of it. A flood of such requests passes through the cache to the source, which is called *cache penetration*. In the running case a broken integration calls the agent API with IDs of tenants that never existed.

- **GET tenant:ghost-999:settings:v1**Nil, because cache-aside caches only rows that exist.

- **read Postgres**The query returns no row.

- **nothing is cached**The reader has no value to store.

- **next request**The same two steps again: 10,000 requests per second become 10,000 queries.

The fix is *negative caching*, where the reader stores the absence too, with a short TTL. It stores a *sentinel value*, a value that no real row can have, so readers can tell "not found" from data.

**Predict: a tenant is created 5 s after a request for it returned "not found". The negative entry's TTL is 30 s, and the create path does not touch the cache. How long can the new tenant stay invisible?**

Up to 25 more seconds. Readers keep getting the sentinel value until its TTL ends, although the row now exists. Most people answer "until the next read", because the create path wrote Postgres. But the cache never learned about the create, so the negative entry is a stale entry like any other.

```go
val, err := rdb.Get(ctx, key).Result()
if err == redis.Nil {                       // cache miss
    if exists := source.Lookup(id); exists {
        rdb.Set(ctx, key, realValue, 10*time.Minute)
    } else {
        rdb.Set(ctx, key, tombstone, 30*time.Second)  // cache the "not found", SHORT ttl
    }
} else if val == tombstone {
    return NotFound                          // served from negative cache, no DB hit
}
```

Exercise E7 shows the effect. Five requests for one absent ID cause five source lookups without the negative cache, and one with it. Negative caching helps only when the same absent IDs repeat. If a client enumerates new random IDs, every ID is a first miss, so the negative cache never hits. That case needs a filter in front of the source or a rate limit on the client, which is inferred from the mechanism.

So a negative entry needs the same care as a positive one. The create path must delete it, the same way an update deletes a stale value. Then its TTL only bounds two cases: a delete that never ran, and the late-fill race from the invalidation sections. The TTL choice is a trade. A long TTL turns "create, then read at once" into a confusing 404. Those bugs are hard to find, because the row is there when you look. A short TTL blunts a flood for less time.

The phase gave 30 to 60 seconds as "a common sweet spot" for the negative TTL. No source supports that range. Choose the TTL from how long a new row may stay hidden in your product, and make the create path delete the key.

A **lagging replica** makes this worse. If the reader fills from a replica, it can read "not found" after the create has committed on the primary. It can also store that sentinel value after the create path's delete. That is the race of a late fill after a delete again, with the replica as the slow reader. Facebook's memcache rule is direct: "A cache refill from a replica's database should only be allowed after the replication stream has caught up". Facebook sends such reads to the primary region with a remote marker. A simpler rule for one region is to keep the negative TTL close to your usual replication lag. Phase 4 covers replication lag.

**Uber** caches absent rows in CacheFront: "These non-existent rows are written to the cache with a special flag".

A *Bloom filter*, a compact bit array that can answer "certainly absent" for an ID, is the other answer for IDs that never repeat. The Go deeper block below explains its limits.

A negative entry is a stale entry once the row exists, so the create path deletes it.

A long negative TTL hides new rows, and the bug looks impossible because the row exists.

Request one missing ID from a read you own twice, and count the source queries.

**Evidence**

Replica rule: "Scaling Memcache at Facebook", NSDI 2013, section 5. Uber: the CacheFront post, 2024-02-15. E7: study note run, 5 lookups to 1. Bloom filter type: the redis.io Bloom filter page. The elite-storage course teaches Bloom filter sizing in its structures phase, section 2.5. The reviewer found that heading in the elite-storage phase 2 file.

- [Redis Bloom filter](https://redis.io/docs/latest/develop/data-types/probabilistic/bloom-filter/)

**Go deeper: a login lookup with no negative cache, and a TTL tied to replication**

**A live penetration path.** On the platform, no Redis cache stored "not found". A login service's OAuth client lookup read Redis, and on a miss it loaded the client from an internal entity store. It wrote Redis only if it found a record. So every repeated lookup for an unknown client ID reached the entity store.

**The same platform did it right in memory.** An edge service used a null sentinel value in a local cache, with a negative TTL of 5 s against a positive TTL of 10 s. Its comment said the short value bounds how long a freshly created token could 404 while a request raced ahead of cross-region replication. That is the replication rule above, applied to a TTL. Another service on the platform read from a replica pool and wrote to a primary pool, which is exactly the setup where a fill can read old data. None of these platform details could be checked.

**Designing a full flow.** For `GET /entity/{id}` with many requests for absent IDs, the pieces are: a versioned key such as `entity:v1:<id>`, a positive TTL with jitter, a sentinel value with a short TTL, a delete of the key on create and on update, and fail-open reads with a short client timeout. Checkpoint question Q5 asks you to defend the negative TTL against both directions.

A Bloom filter is a compact bit array that answers "certainly absent" or "maybe present" for an ID. It has no stale entry per ID, but it has false positives, and every create must add the new ID to it. Redis has a Bloom filter data type.

**Bloom filter details.** A Bloom filter cannot delete an ID unless it is a counting variant. So deleted rows stay "maybe present", and requests for them still reach the source. Size it from the expected number of IDs and the false positive rate you accept. The elite-storage course derives the arithmetic.

That completes the four failures of the settings cache. The next section lists what you can now predict, and the question that Phase 3 answers.

## What you can do now, and what comes next

You can now predict four failures of a cache that readers fill, and choose the fix for each one.

- **The source serves only the misses.** When caching stops, for a flag, an empty node or an outage, source load jumps 1/(1 − h) times with no error. Failing open needs short timeouts, a breaker and a limit on misses. The first three teaching sections showed this.

- **A stampede has one rebuild per filler that misses during the rebuild.** singleflight coalesces inside one pod. A lease, routing by key or serving the old value coalesces across pods. XFetch fits hot keys, and jitter fits many keys that expire together.

- **Delete-on-write is not race-free.** A reader that missed before a write can fill the old value after the delete. A lease with `SET NX PX` and `SET IFEQ` makes the fill prove that nothing changed. The TTL only bounds a missed delete.

- **A cached "not found" is an entry like any other.** The create path deletes it, and its TTL is the longest a new row can stay hidden.

The lease in this phase is a token that a write must still match when it lands. Phase 3 asks the same question about locks. When is a Redis lock safe, and what happens when its holder pauses past the TTL? It builds on `SET NX PX`, a release that checks the token, and a number that lets the protected resource refuse an old holder.

## Lab: the exercises that teach Phase 2

The lab below is copied from the phase. The author of this lesson did not run it. A separate study run used an x86_64 Homebrew build of Redis 8.10.1 under Rosetta 2, outside Docker, on one Mac, and its results appear in the notes under some exercises. Notes say where a step is out of date or teaches less than it claims.

**Practice: where it runs, and how long it takes**

Everything runs on your laptop with Docker, Go and the module versions in `code/go.mod`: go-redis v9.5.1 and `golang.org/x/sync` v0.22.0. The phase plans 4 to 6 days for the reading and the lab. The stampede and invalidation exercises matter most.

The setup path in the phase is out of date. The folder is `/Users/raghvendra.dhakar/Desktop/project/code/study-material/redis/code`. The compose file pins `image: redis:7.2`. Pin an 8.x image, so that `SET ... IFEQ` from the invalidation sections works. Persistence is also off in compose, so a restart empties Redis.

**Practice: open the lab, E1 to E12**

Setup:

```bash
cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d && docker exec redis-study redis-cli PING   # → PONG
```

-

: **E1. Cache-aside: miss then hit.**

- Run: `go run ./phase02_caching/cache_aside -id c101` twice.

- Expected: first ~311ms (MISS, hits slow source), second ~6ms (HIT).

- Teaches: the whole read-cache/populate loop and the latency payoff.

Note: the program itself prints "~0.3ms" for a hit, so both numbers are guesses. The study run measured a 307 ms miss and a 3.7 ms hit in a fresh process, which includes the first connection.

-

: **E2. (Break it) Fail open when Redis is down.**

- Run: `docker stop redis-study; go run ./phase02_caching/cache_aside -id c9; docker start redis-study`

- Expected: the request still returns (from source), with a `[warn] cache GET failed … failing open` line — NOT a crash.

- Teaches: the single most important cache-aside property — a cache outage is slower, not broken.

Note: a stopped container refuses the connection, which fails fast. The study run saw two warnings and a 450 ms miss. To see the timeout cost from the fail-open section, pause a Redis process with `kill -STOP` instead of stopping it.

-

: **E3. Thundering herd, then singleflight.**

- Run: `go run ./phase02_caching/thundering_herd -conc 200`

- Expected: `WITHOUT: 200 source calls`, `WITH: 1 source call`.

- Teaches: request coalescing collapses N concurrent misses of one key into one source call.

Note: the program prints longer lines than the phase shows, such as "WITHOUT singleflight: 200 concurrent misses → 200 source calls". To see one call per process, start four copies at the same time.

-

: **E4. Scale the herd.**

- Run: `go run ./phase02_caching/thundering_herd -conc 1000`

- Expected: still exactly 1 source call with singleflight; ~1000 without.

- Teaches: coalescing is O(1) source calls regardless of concurrency (per process).

-

: **E5. TTL jitter distribution.**

- Run: `go run ./phase02_caching/ttl_jitter -keys 1000 -base 600 -jitter 60`

- Expected: fixed → 1 expiry bucket (spike); jittered → ~121 buckets over 120s (smear).

- Teaches: synchronized TTLs self-inflict stampedes; jitter smears expiry.

Note: this program does not use Redis, although its header says to start Docker. The study run printed 121 seconds with 7 to 9 keys each.

-

: **E6. Prove synchronized expiry in Redis directly.**

- Run: warm 1000 keys with the same TTL: `for i in $(seq 1 1000); do echo "SET warm:$i v EX 30"; done | docker exec -i redis-study redis-cli --pipe`. Wait ~28s, then `docker exec redis-study redis-cli DBSIZE` repeatedly around t=30s.

- Expected: DBSIZE drops from ~1000 to ~0 in one ~1s window — the synchronized-expiry cliff.

- Teaches: what a fixed-TTL bulk warm looks like from the keyspace's side.

Note: with `EX 5`, the study run saw 1,000 keys drop to 0 in about 0.1 s, and `INFO` showed `expired_keys_active:1000`. The active expire cycle removed them, not reads.

-

: **E7. Negative caching.**

- Run: `go run ./phase02_caching/negative_cache -id ghost-999 -n 5`

- Expected: without → 5 source lookups; with → 1.

- Teaches: caching the "not found" stops penetration.

-

: **E8. (Break it) Negative-cache staleness.**

- Reason about it: with a 30s negative TTL, an entity created 5s after its first (404) lookup is invisible for how long? Now change the sentinel TTL to 10 minutes in `negative_cache/main.go` and argue why that's dangerous.

- Teaches: the negative-TTL freshness trade-off directly.

Note: add one more step in your head. Make the create path delete the key, and the hidden window drops to the time between the create and the delete.

-

: **E9. Write-through vs write-behind.**

- Run: `go run ./phase02_caching/write_through_behind`

- Expected: write-through ~269ms and `source.puts=5`; write-behind ~4ms and `source.puts=0` until the flush.

- Teaches: the durability-vs-latency trade and the write-behind loss window.

-

: **E10. Delete-on-write by hand.**

- Run: `docker exec redis-study redis-cli SET settings:c7 '{"v":1}' EX 3600` (cache). Then simulate a write: `docker exec redis-study redis-cli DEL settings:c7`. Then read: `docker exec redis-study redis-cli GET settings:c7` → nil → (your app repopulates).

- Expected: the DEL forces the next read to repopulate from source.

- Teaches: why invalidation deletes (not updates) the key.

Note: this shows the delete, not the race. Extend it with the four steps of the table in the section on conditional fills: a reader's `SET NX PX 5000`, the writer's `DEL`, then the reader's `SET ... IFEQ`. That needs Redis 8.4.0 or later.

-

: **E11. See the versioned-key kill switch.**

- Run: `docker exec redis-study redis-cli SET "ccs:list_voices:v1:x" old; docker exec redis-study redis-cli SET "ccs:list_voices:v2:x" new; docker exec redis-study redis-cli KEYS "ccs:list_voices:v*"` (sandbox only — never KEYS in prod).

- Expected: both versions coexist; bumping v1→v2 orphans all v1 keys (TTL reaps them).

- Teaches: how a version segment in the key gives you instant format migration.

Note: these two keys have no TTL, so nothing reaps them in this exercise. Add `EX` to see the old version expire.

-

: **E12. Measure hit rate.**

- Run: `docker exec redis-study redis-cli INFO stats | grep keyspace` (`keyspace_hits`, `keyspace_misses`).

- Compute: hit rate = hits/(hits+misses). Then compute the amplification `1/(1-h)` for h=0.99.

- Teaches: the cache-bypass incident math — hit rate is the load multiplier.

Note: the server counters mix all caches, as the fail-open section explains. In the Teaches line, the phase named the former employer's service. Only that word was changed.

**Practice: the second lab folder and other files**

The code folder has a second set of programs in `phase02_caching_patterns/` that the phase text does not use. Read them with these notes.

- `cache_aside` fails closed on a Redis error and on a corrupt value, at lines 52 to 59. That is the opposite of the fail-open section, so do not copy it.

- `thundering_herd` has an XFetch part that is fixed, not random. It prints "DB calls = 5". The XFetch section gives the real rule.

- `invalidation_scope` builds generation keys, but its first access uses `Set` without `NX`, so two callers can create two versions.

- `write_behind` uses `LPOP` and then writes, so a crash between the two loses an event.

- Four compiled binaries sit at the top of `code/`: `cache_aside`, `thundering_herd`, `invalidation_scope` and `write_behind`. They are not source, and you can delete them.

## Checkpoint questions

**Practice: seven questions, answer each in your own words first**

**Q1.** A hot endpoint had a 99% hit rate, and its source normally saw 300 calls per minute. A release marks every response as not cacheable. Compute the calls per minute after the release, and state the general formula as a function of the hit rate h. Then explain why the release produced no error, and why it looked like "everything is slow, nothing deployed".

**Answer sketch**

The source saw 1% of the traffic, so the total was 30,000 calls per minute. After the release it sees all of them: 30,000 per minute, 100 times more. The multiplier is 1/(1 − h). No error appears because every call still succeeds from the source. The first symptom is latency in the source and in the services that call it, and the release looks unrelated because it changed one flag.

**Q2.** Your service reads tenant settings 5,000 times per second across 40 pods, all from one hot Redis key with a one-hour TTL. The key expires, and the rebuild takes 100 ms. Describe what hits Postgres in the next 100 ms with (a) no protection, (b) per-pod singleflight, and (c) singleflight plus a shared lease. Give the approximate query count for each. Why can singleflight alone not get you to 1 query across 40 pods?

**Answer sketch**

(a) About 500 queries, because 5,000 × 0.1 s of requests miss during the rebuild. (b) Up to 40, one per pod, because the singleflight map lives in one process. (c) 1, because only the pod that wins `SET ... NX PX` rebuilds, and the others wait or serve an old value. singleflight cannot see other processes, so the coalescing scope is one pod.

**Q3.** A colleague proposes write-through for the settings cache: "update the cache whenever settings change, so it is never stale, which is cleaner than delete-on-write." Give two reasons to delete instead of update, one a race and one a cost. Then name the race that delete-on-write still has, and the one scenario where write-through is the better choice.

**Answer sketch**

Race: two writers that update the cache can interleave, and the older value can land last. Cost: an update rebuilds the cached value on the write path, which may be an expensive join, while a delete costs one command. Delete-on-write still has the late-fill race, where a reader that missed before the write fills the old value after the delete. A lease with `SET IFEQ` fixes it. Write-through is better when a read right after a write must be fresh and there is a single writer per key.

**Q4.** You warm 50,000 tenant keys at deploy time, each with a flat `EX 3600`. Everything is fine for 59 minutes. Predict minute 60, quantify it, and give the one-line fix. Then explain why the bug repeats on every deploy, and why a canary or a staging test rarely shows it.

**Answer sketch**

In minute 60 all 50,000 keys expire within a second or two, and up to 50,000 reads miss and reach Postgres at once. Redis's active expire cycle also works at its CPU limit. The fix is jitter: `EX 3600 ± rand(300)`, for example. The deploy sets the same timer each time, so the spike comes one TTL after every deploy. Staging warms few keys and rarely runs a full hour under load, so the spike is small or never happens there.

**Q5.** Design `GET /entity/{id}`, where about 5% of traffic asks for IDs that do not exist, from an integration that enumerates IDs. Give the key format, the positive TTL, the negative sentinel and its TTL, the create path, and the fail-open behaviour. Then defend your negative TTL against "too long" and "too short".

**Answer sketch**

Key `entity:v1:<id>`. Positive TTL of, say, 10 minutes with jitter. Sentinel with a short TTL, chosen from how long a new entity may stay hidden. The create path and the update path delete the key, after the database write. Reads fail open with a short client timeout and a breaker. Too long: a created entity returns 404 until the sentinel expires, if a delete is missed. Too short: repeated lookups of the same absent ID reach the source more often. If the integration enumerates new random IDs, the negative cache never hits, so add a Bloom filter or a rate limit for that client.

**Q6.** The lab's cache-aside read treats the cache as an optimization: it fails open and tolerates corruption. Give a scenario where you would deliberately fail closed, so that a Redis error fails the request. Say what you buy and what you risk.

**Answer sketch**

A rate limiter whose counters live in Redis, or a cache of authorization decisions that must not be skipped. Failing closed buys safety: no tenant runs without limits, and no request skips a check. The risk is availability, because a Redis outage becomes an outage of that feature. Fail open there would multiply load or remove a protection.

**Q7.** An admin's settings change is visible at once in one service but takes up to 10 minutes in another. The first service reads through a shared cache that the owning service invalidates with a delete, with a one-hour TTL as the backstop. The second keeps its own Redis copy with a 10-minute TTL and no invalidation. Explain the difference. Is the 10-minute delay a bug or a trade-off? What single change makes the slow one instant, and what does it cost?

**Answer sketch**

The first service gets a delete on every write, so the next read fills fresh data. The second learns of a change only when its TTL ends, so the worst case is 10 minutes. That is a trade-off if the team chose it, and a bug if nobody knew. To make it instant, the second service must receive the invalidation, for example by reading through the shared cache or by subscribing to change data capture. That costs a dependency on the invalidation path and the late-fill race, which then needs a lease or a version check.

## Cheatsheet

**Practice: the one-screen cheatsheet**

```
READ AND WRITE STRATEGIES (two axes, pick one of each)
  read : cache-aside   app fills on a miss. Cache is DERIVED and DISPOSABLE.
         read-through  a library fills on a miss. Same failure modes.
  write: delete-on-write  write source, then DEL key. Usual partner of cache-aside.
         write-through    write source + cache. Fresh unless the cache write fails.
         write-behind     write cache, flush later. Fast. LOSS WINDOW before flush.

PRODUCTION CACHE-ASIDE (5 properties, lab cache_aside/main.go)
  1 versioned key  course:v1:<id>   bump v1 -> v2 on a format change
  2 fail open      GET error -> log, read source, never return the error
  3 corruption ok  unmarshal error -> read source
  4 fill with a deliberate TTL
  5 SET or marshal error = warning only

c1  LOAD ON THE SOURCE
  source load = (1 - h) x traffic        caching stops -> x 1/(1 - h)
  h=0.98 -> 50x   h=0.99 -> 100x   one empty node of 4 at h=0.98 -> ~13x misses
  fail-open cost: up to ReadTimeout x attempts. v9.5.1 defaults measured 6.042 s = 2 timeouts
  fixes: short timeout, MaxRetries -1, breaker per node, cap on concurrent misses
  fail CLOSED when Redis holds the truth: rate limits, decisions you cannot skip

c2  STAMPEDES
  size ~ 1 + rate x rebuild_time, per coalescing scope
  singleflight   one call per PROCESS (40 pods -> up to 40)
  lease          SET k:lease <rand> NX PX 5000 -> one call per KEY
  serve stale    logical expiry in the value, long real TTL, one refresher
  route by key   all requests for a key -> one process
  XFetch         now - delta*beta*ln(rand()) >= expiry   beta=1   hot keys only
  jitter         many keys warmed together: EX base +/- rand(j). No help for one key.

c3  INVALIDATION
  delete, not update  (two writers cannot leave the older value)
  late-fill race: reader misses, writer UPDATE + DEL, reader SETs old value
  lease fix (Redis >= 8.4.0, Valkey >= 8.1.0):
    miss : SET k lease:<r> NX PX 5000
    write: UPDATE db, then DEL k
    fill : SET k <v> IFEQ lease:<r> EX 3600   (nil = invalidated, do not fill)
  TTL = backstop for a missed DEL, not a fix for the race
  CLIENT TRACKING: placeholder 'caching-in-progress' before the read
  keyspace notifications: fire and forget, not an invalidation channel

c4  NEGATIVE CACHING
  store a sentinel with a short TTL; the CREATE path deletes it
  hidden window = negative TTL if the delete is missed
  fill from a replica only after replication caught up
  random IDs never repeat -> Bloom filter or rate limit

INVESTIGATE
  INFO stats | grep keyspace   keyspace_hits / keyspace_misses, whole server
  INFO stats                   expired_keys_active after a mass expiry
  TTL <key>                    -1 no expiry, -2 no key, n seconds left
  SET k v EX n                 always a TTL; KEEPTTL keeps the current one
  KEYS pattern                 sandbox only, it blocks the server
```

## Sources

**Practice: every source this lesson used**

Must-read, in this order.

- [Cache-Aside pattern, Microsoft Azure Architecture](https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside): a clear definition of cache-aside and its failure modes. Read before the strategies section.

- [Caching strategies, AWS ElastiCache](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/Strategies.html): lazy loading, write-through and TTLs. The old `red-ug` link now redirects here.

- [MIT 6.824 memcache FAQ](https://pdos.csail.mit.edu/6.824/papers/memcache-faq.txt): the late-fill race in eight steps, and why delete beats update.

- [Scaling Memcache at Facebook, NSDI 2013](https://www.usenix.org/system/files/conference/nsdi13/nsdi13-final170_update.pdf): leases, stale values, gutter and the replica rule. Read sections 3.2.1, 3.3 and 5.

- [Optimal Probabilistic Cache Stampede Prevention](https://cseweb.ucsd.edu/~avattani/papers/cache_stampede.pdf): the XFetch rule in Figure 3 and the trace results in section 6.

- [singleflight package docs](https://pkg.go.dev/golang.org/x/sync/singleflight): `Do`, `DoChan` and `Forget`.

Production cases.

- [Slack's Incident on 2-22-22](https://slack.engineering/slacks-incident-on-2-22-22/): empty cache nodes, superlinear database load, and a cache that could not refill.

- [Facebook, More details on today's outage](https://engineering.fb.com/2010/09/23/uncategorized/more-details-on-today-s-outage/): a cache repair loop and 2.5 hours down.

- [Uber, CacheFront at 40 million reads per second](https://www.uber.com/en-GB/blog/how-uber-serves-over-40-million-reads-per-second-using-an-integrated-cache/): timestamp checks, change data capture, negative entries, breakers and adaptive timeouts.

- [Uber, CacheFront at 150 million reads per second](https://www.uber.com/us/en/blog/how-uber-serves-over-150-million-reads/): the stale cases found later, and invalidation markers.

- [Meta, Cache made consistent](https://engineering.fb.com/2022/06/08/core-infra/cache-made-consistent/): a fill against a rare transaction, found by consistency tracing.

- [Discord, How Discord Stores Trillions of Messages](https://discord.com/blog/how-discord-stores-trillions-of-messages): request coalescing with routing by channel.

- [Shopify, Your Circuit Breaker is Misconfigured](https://shopify.engineering/circuit-breaker-misconfigured): 263% against 4% extra capacity.

- [Stack Overflow, How We Do App Caching](https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/): a TTL bug that sent 95% of local reads to Redis.

- [Hotstar, Scaling Subscriptions](https://blog.hotstar.com/scaling-subscriptions-cache-for-cash-4c5836bd6a6f): a low hit rate that made p99 worse.

- [Pendo status incident](https://status.pendo.io/incidents/g8nfbs1vdn69): keys with no TTL filled memory.

- [Redis blog, Caches, Promises and Locks](https://redis.io/blog/caches-promises-locks/): a lease with pub/sub waiting.

Redis and Valkey reference.

- [Redis SET](https://redis.io/docs/latest/commands/set/): `EX`, `PX`, `NX`, `XX`, `KEEPTTL` and `IFEQ`.

- [set.json at Redis 8.10.2](https://raw.githubusercontent.com/redis/redis/8.10.2/src/commands/set.json) and [set.json at Valkey 9.1.2](https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/src/commands/set.json): which conditions each server has.

- [Redis DELEX](https://redis.io/docs/latest/commands/delex/), [Valkey SET](https://valkey.io/commands/set/) and [Valkey DELIFEQ](https://valkey.io/commands/delifeq/).

- [HEXPIRE](https://redis.io/docs/latest/commands/hexpire/) and [HGETEX](https://redis.io/docs/latest/commands/hgetex/): TTLs per hash field.

- [Redis cache-aside use case](https://redis.io/docs/latest/develop/use-cases/cache-aside/): replaces the phase's dead `use-cases/caching/` link.

- [Redis client-side caching](https://redis.io/docs/latest/develop/reference/client-side-caching/): tracking and the placeholder fix.

- [Redis keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/): replaces the phase's dead link, and says why they are not an invalidation channel.

- [Redis Bloom filter](https://redis.io/docs/latest/develop/data-types/probabilistic/bloom-filter/).

- [Redis docs, Diagnosing latency issues](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/): many keys expiring in the same second.

- [go-redis v9.23.0 options.go](https://raw.githubusercontent.com/redis/go-redis/v9.23.0/options.go): the current timeout defaults.

- [Turning the database inside out](https://www.confluent.io/blog/turning-the-database-inside-out-with-apache-samza/): a talk about stream processing and derived data, background for change data capture. The phase called it a survey of cache invalidation, which it is not.
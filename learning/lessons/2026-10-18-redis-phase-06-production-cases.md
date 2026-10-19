This phase reviews a real system. It is the platform of Phase 0, which ran about 34 services on several shared, managed Redis clusters. This review follows one of them, as its own example. That cluster used the eviction policy volatile-lru, took RDB backups and had no AOF. Redis did six jobs there: caching, sessions, locks, idempotency keys, queues and rate limits. You are the engineer asked to review that use and write the fix list.

The earlier phases taught each part of Redis on its own. This review asks a different question about every Redis call you open. What does this call lose when something fails, and what does the client do while it waits? The platform had real answers, and some of them were outages. One service wrote keys with no TTL, and those keys filled the shared memory. One response flag turned off caching for a hot endpoint, and the source service took about 100 times its normal load. Public companies saw the same failures, and this lesson puts their cases next to these.

The review also has one new request. A product team wants live chat and presence between users, and its users connect to many WebSocket servers. The team wants to send messages between those servers with Redis pub/sub on the same cluster. The last concept of this lesson answers what that design loses and how real systems recover it.

### What you must know

- When Redis stalls, the client's timeouts and pool decide how long you wait, and a context deadline may not apply.Set the client so a slow Redis fails fast and leaves no stale replies.

- Redis loses keys by eviction and by failover, so each job's cost of loss sets its TTL rule and store.Classify a Redis call by its job, then rank what to fix.

- The origin serves only the misses, so a hit rate fall from 99% to 98% doubles origin load.Predict the load on the database when a cache gets worse.

- With a local cache in front of Redis, a change is seen only after every layer drops its copy.Compute the real staleness bound of a layered cache.

- Pub/sub delivers each message at most once, so servers that must not miss messages read a durable log.Design chat and presence between servers that survive a disconnect.

The sections, the recall list and the lab tags call these five ideas c1 to c5, in this order.

## What you bring from Phases 0 to 5

Five ideas from earlier phases come back in this review. Each card explains one again in plain words, so you do not need to open the earlier phase.

One thread runs every command

Phase 0 showed that Redis runs commands one at a time on one main thread. So one slow command, such as KEYS *, makes every other client wait. Your client sees that wait as a slow reply.

Cache-aside and the TTL

In cache-aside, the application reads Redis first and, on a miss, reads the database and writes the value to Redis. A TTL, the time to live of a key, tells Redis to delete the key after that many seconds. Phase 2 deleted the key on every write and kept the TTL as a backstop.

Eviction under maxmemory

When memory reaches maxmemory, Redis removes keys to make room, by its eviction policy. Phase 5 showed that volatile-lru removes only keys that have a TTL. A key with no TTL stays.

Replicas copy writes later

Phase 4 taught asynchronous replication, which means the primary replies OK before any replica has the write. In a failover, a replica becomes the new primary when the old one fails. Writes it did not receive are gone.

A lock needs a fencing token

Phase 3 showed that a Redis lock can expire while its holder still works. A fencing token is a number that grows with each lock grant. The store that holds the data rejects a write that carries an older token.

This phase needs all five because a review judges each Redis call by what happens when one of these mechanisms meets a failure. The first place the review looks is the client library, because every call passes through it.

## What does your service wait for when Redis stops answering?

A slow Redis reaches your users through the client's timeouts, not through Redis.

The platform ran four major versions of go-redis, the Go client for Redis. The weakest client set no context and no timeouts. The best one set 2-second read and write timeouts and sent reads to replicas. The phase said the weakest client "hangs forever" when Redis is slow, and that the context of the best one can cancel a slow call. Both statements are wrong for go-redis. The real behaviour has a different cost, and this section measures it in seconds.

A client keeps a pool of open connections to Redis. Each command borrows one connection, writes the command and waits for the reply. Three limits decide how long that wait can last:

- ReadTimeout is the deadline the client sets on the socket while it waits for a reply.

- PoolTimeout is how long a command waits for a free connection when every connection in the pool is busy.

- A context deadline is the time limit your request handler puts on a Go context.Context and passes down to each call.

Most engineers expect the shortest of the three to win. In go-redis the context deadline does not set the socket deadline, unless you turn that on.

Predict: your service uses go-redis v9.5 and leaves ReadTimeout unset. Each request has a 200 ms context deadline. Redis stops answering for 4 seconds. How long does one request wait, and what changes on v9.22?
On v9.5 the request waits about 3 seconds and then gets a timeout error. On v9.22 it waits about 4 seconds and gets the late reply, because the new default of 5 seconds is longer than the stall. The 200 ms deadline does not end the wait in either case, because go-redis does not use it for the socket unless you turn that on. On v9.5 it only stops the retry that would follow the timeout. Most people answer 200 ms, which is reasonable, because most Go libraries obey the context. This answer comes from reading the go-redis code. Nobody has run it yet: lab L3 in the practice part describes the run.

Five rules in the go-redis code explain the answer:

- An unset ReadTimeout becomes a fixed default. It is 3 seconds in v6.15.9 and in v9 up to v9.21.0. From v9.22.0 it is 5 seconds, and WriteTimeout changed the same way.

- In v9 the context deadline does not set the socket deadline unless the option ContextTimeoutEnabled is true. Its default is false, so the client reads with context.Background() and only ReadTimeout applies.

- PoolTimeout defaults to ReadTimeout plus 1 second. So when the pool is full, a command can wait up to 6 seconds on v9.22 before it is even sent. From v9.21.0, a pool timeout is also retried.

- A read timeout on a normal command counts as a retryable error. go-redis retries it up to MaxRetries times, default 3, after a short backoff. The context is checked only while a command waits for a pool connection and before each retry. So with no deadline, one call can wait several ReadTimeout periods.

- After a read timeout the client closes that connection. The late reply can still arrive on it, so the go-redis guide says such a connection "can't be reused".

One request during a 4-second Redis stall

Step 1: the 200 ms deadline passes. Only the client with ContextTimeoutEnabled: true stops waiting.

Step 2: the other two requests hold a goroutine and a pool connection for seconds.

Step 3: at 3 seconds the v9.5 client returns a timeout error and closes the connection.

Step 4: at 4 seconds Redis answers, and only the v9.22 client is still there to read it.

Illustration from the defaults in the go-redis code, not measured.

So the weak client did not hang forever. Each attempt waited 3 seconds. Its config also set MaxRetries: 3 and MaxRedirects: 8, and the v6 cluster client retries a timed-out read at both levels. So during a long stall one call could wait many times 3 seconds, and it had no context to stop it. This is inferred from the v6.15.9 code and was not run. Even one 3-second wait is a failure for a request with a budget of a few hundred milliseconds. During those seconds each waiting request holds a goroutine and a pool connection. When the pool is empty, new requests queue in PoolTimeout as well, so a short Redis stall becomes a long service stall.

Correction. The phase said a go-redis v6 client with no ReadTimeout "hangs forever if Redis is slow". In v6.15.9 an unset value becomes 3 seconds for each attempt. The phase also said the v9 caller's context can cancel a slow call. That is true only with ContextTimeoutEnabled: true, in every v9 release from v9.5.1 to v9.23.0.

The fix for a new client is short. Set ReadTimeout and WriteTimeout to a value below your request budget. Set ContextTimeoutEnabled: true so the handler's deadline also ends the call. Set PoolTimeout on purpose rather than accepting ReadTimeout plus 1 second. Choose MaxRetries on purpose too, because each retry of a timed-out read adds a full ReadTimeout. When you add Redis to a service, copy a reviewed client like this, not the nearest file in the repository.

Evidence
go-redis source read at each tag: options.go v6.15.9 lines 126 to 131 and cluster.go v6.15.9 lines 94 to 98 for the 3-second default. options.go at v9.21.0 and v9.22.0 for the change to 5 seconds, and the v9.22.0 release notes table "ReadTimeout / WriteTimeout | 3s | 5s". redis.go v9.23.0 lines 1892 to 1896 and line 1799 for ContextTimeoutEnabled. options.go v9.23.0 lines 751 to 755 for PoolTimeout. Retries of a read timeout: redis.go v9.5.1 lines 417 to 438 and error.go v9.5.1 lines 40 to 53, error.go v9.23.0 lines 108 to 118 for the pool timeout, internal/pool/pool.go v9.5.1 lines 302 to 331 for the context check in the pool wait. The v6 retries: redis.go v6.15.9 lines 180 to 217 and cluster.go v6.15.9 lines 968 to 980, read by the lesson review on 2026-10-18. The closed connection: the go-redis debugging guide, https://redis.uptrace.dev/guide/go-redis-debugging.html. All read on 2026-10-18 by the study note.

Go deeper: the four client versions, the two configs, replica reads, and other v9.22 default changes
The client survey in the platform

The phase counted go-redis versions across the platform's repositories. About 17 used redis/go-redis/v9, which has a context-first API, timeouts and replica routing. About 12 used go-redis/redis/v8, also context-first. About 14 used the legacy v7, mostly as an indirect dependency. One used v6, with no context and no timeouts in its calls. About 7 also used a second Go client, redigo. About 12 Java repositories used Redisson, Jedis or Lettuce, mostly for caching. The general lesson is the one above: the nearest file is often an old client with gaps.

The two ends of the range

The weakest client, on go-redis v6, built a cluster client with retries and no timeouts:

// weakest: go-redis v6, no context, no timeout set
redisClient = redis.NewClusterClient(&redis.ClusterOptions{
    Addrs: []string{host + ":" + port}, MaxRetries: 3, MaxRedirects: 8,
})
output := client.redisClient.Get(key)   // no ctx: the caller cannot cancel it

The best client, on go-redis v9, set timeouts and replica reads:

// best: go-redis v9, ctx, timeouts, replica routing
redisClient.clusterClient = goRedis.NewClusterClient(&goRedis.ClusterOptions{
    Addrs: []string{host + ":" + port}, MaxRetries: 3,
    ReadTimeout: 2*time.Second, WriteTimeout: 2*time.Second,
    ReadOnly: true, RouteByLatency: true,
})
output := client.clusterClient.Get(ctx, key)

Even the best one leaves ContextTimeoutEnabled at false, so its ctx passes values but not deadlines to the socket.

Replica reads are not free

ReadOnly: true with RouteByLatency: true sends read commands to the fastest node, often a replica. Replication is asynchronous, so a replica can return a value that the primary has already changed. That is fine for a cache that tolerates a few seconds of staleness. It is wrong for a read that must see a write you made a moment ago, such as a new session. The phase showed this setting as plainly good.

Other defaults that changed in v9.22.0

- Retry backoff went from 8 ms to 512 ms, to 10 ms to 1 second.

- The cluster client reloads the cluster state every 60 seconds, not every 10 seconds.

- WaitAOF, used in the Phase 4 labs, now returns *IntSliceCmd. The release notes say the old type "failed to parse the reply at runtime".

- The course pins go-redis v9.5.1. The current release when this lesson was written is v9.23.0.

So a dependency upgrade alone can change how long your service waits for Redis. Read the release notes of the client, not only of the server.

This section showed how long a call waits. It did not show what a timed-out or cancelled call leaves behind on its connection, and the next section answers that.

## What does a timed-out or cancelled call leave on its connection?

The last section showed that go-redis closes a connection after a read timeout. The reason is that Redis still sends the reply, and the reply waits on that socket until something reads it. A connection is an ordered stream. The client knows which reply belongs to which command only by their order, so one unread reply shifts every later pairing by one.

Connection kept after a cancel

- Request A sends GET user:17 on connection 3.

- A is cancelled before the reply arrives.

- Connection 3 goes back to the pool with the reply of user 17 still unread.

- Request B sends GET user:42 on connection 3 and reads the first reply in the stream.

- B receives the data of user 17.

Connection closed after a cancel

- Request A sends GET user:17 on connection 3.

- A is cancelled before the reply arrives.

- The client closes connection 3, and the late reply is dropped with it.

- Request B borrows a different connection, or the pool dials a new one.

- B receives the data of user 42.

This is the failure behind a ChatGPT outage that leaked user data. OpenAI used the asyncio redis-py client with Redis Cluster and a shared connection pool. A request cancelled after it was sent, but before its reply was read, left that reply on the connection. The next, unrelated request read it. A server change raised the rate of cancelled requests, and some users saw parts of other users' chat history. Payment details of 1.2% of ChatGPT Plus subscribers active in a nine-hour window may have been visible. OpenAI fixed redis-py and added a check that cached data matches the user who asked for it.

Closing the connection is the safe choice, but it has its own cost. A new connection needs a TCP handshake, and often TLS and an AUTH, before the first command. AWS measured 2.82 ms per operation when PHPRedis opened a new connection per request, against 0.21 ms with persistent pooled connections. Both ran from EC2 to an m6g.2xlarge ElastiCache node in the same Availability Zone. So when Redis is slow and every call times out, every call also opens a new connection. Many clients reconnecting at once with no backoff and no jitter is a reconnect storm. AWS reports that such loops in redis-py-cluster, Lettuce and Redisson have driven server CPU to 100%.

A cache that fails open, which means it goes to the database when Redis errors, has one more cost. It still waits a full ReadTimeout on every request while Redis is down. A circuit breaker stops calling a failing dependency for a short time after errors pass a threshold, so requests skip Redis at once. Uber puts a sliding-window circuit breaker in front of each Redis node.

Timeouts below the request budget, context deadlines on, and a closed connection after every timeout.

Trusting the context deadline and the default timeout holds every request for 3 to 5 seconds.

Open one Go service and search for ContextTimeoutEnabled, and if it is absent, deadlines do not reach Redis.

Evidence
OpenAI, "March 20 ChatGPT outage: Here's what happened", 2023-03-24, read from the archive copy https://web.archive.org/web/2024/https://openai.com/index/march-20-chatgpt-outage/ because the live page returned HTTP 403. AWS, "Best practices: Redis clients and Amazon ElastiCache for Redis", 2021-08-13, https://aws.amazon.com/blogs/database/best-practices-redis-clients-and-amazon-elasticache-for-redis/. bsport, "How We Eliminated Redis as a Single Point of Failure", 2026-03-27, https://engineering.bsport.io/how-we-eliminated-redis-as-a-single-point-of-failure-2729c22008b5, read from the blog feed because the page returned 403. Uber's circuit breaker: https://www.uber.com/blog/how-uber-serves-over-40-million-reads-per-second-using-an-integrated-cache/, read through a fetch summary, not as exact text.

Go deeper: connection limits, breaker tuning at Shopify, and what the capstone client still lacks
Connections are a server resource

An ElastiCache node accepts up to 65,000 connections, per the AWS client guide. Each connection also has a reply buffer on the server, so many idle connections still use Redis memory. A pool that is too large wastes that memory, and a pool that is too small queues requests in PoolTimeout. Size the pool from the concurrency you measure, not from a default.

How Shopify tuned its breakers

Shopify runs one circuit per Redis instance, 42 instances in its worked example. The post computes the extra capacity with its own circuit breaker equation. It does not measure it in an outage. The first configuration needed 263% extra capacity in the application while Redis was down, because requests still waited on the failing instance. The tuned configuration needed 4%. The tuned half-open timeout, the time a test request may take before the breaker opens again, is 50 ms. The tuning also raised the error timeout to 30 seconds, which makes recovery slower. Shopify chose it because 99% of its Redis requests answer in under 50 ms. So a breaker is tuned from your own latency numbers, not from a guess.

bsport: a reconnect storm that reached DNS

bsport, a booking platform, saw the storm spread beyond Redis. One Redis inside its Kubernetes cluster stopped responding, and connection pools in the services filled. Retries and reconnects caused a spike in DNS lookups, which overloaded CoreDNS. Then no service could resolve any internal name, including the database, and the whole platform went down. The fix split the shared Redis into one cluster per business domain.

bsport's second incident

During the split, bsport moved data with RIOT live replication. RIOT scans the whole source and runs DUMP on keys. After the cutover RIOT was the only client and ran at full speed. Each DUMP took over 1 second and saturated the source CPU, and the application timeouts were shorter, so requests failed. Staging traffic was 500 times lower than production, so the tests missed it. Killing RIOT brought the services back in 2 minutes. Uptime after the whole project went from 99.87% to 99.97%. The post also gives "64 basis points" and "64% less downtime", which do not match those two numbers.

The capstone client against these rules

The phase's capstone program wraps go-redis v9 in one object. It sets DialTimeout 2 s, ReadTimeout 1 s, WriteTimeout 1 s and PoolSize 10. It has a Set that refuses a missing TTL, a fail-open cache-aside, a multi-get and a lock. Read against this concept, it still has gaps:

GapWhy it matters

ContextTimeoutEnabled is not setthe caller's deadline does not reach the socket

fail-open has no circuit breakerevery request waits at least 1 s while Redis stalls, and longer when go-redis retries the read

CacheAside has no singleflight and no TTL jitterPhase 2's stampede rules are missing, and concept c4 returns to this

the unlock runs in a defer with the caller's context and ignores its resultif that context is cancelled, the lock stays until its TTL ends. This is inferred from the code and not tested

its multi-get is one MGET command, not a pipelinein a cluster all its keys must hash to one slot

The client decides how long you wait. It does not decide what Redis keeps, and the next section starts with the keys Redis cannot remove.

## What does each job lose, and what can a key with no TTL do?

The job of a key decides what its loss costs, so classify the job first.

The client decides how long a call waits. What Redis keeps is decided elsewhere, and Redis can lose a key in two ways that the writer does not control. Eviction removes keys when memory is full. A failover can remove writes that never reached the replica. A lost cache key costs one slow request. A lost lock can let two workers charge the same card. So a review classifies each Redis call by its job before it judges the code.

JobUsual commandsWhat a lost key costsTTL ruleMay Redis hold the only copy?

CacheGET, SET with TTL, delete on writeone slower requestalways a TTLyes, it is a copy

Sessionhash plus TTLthe user logs in againa TTL on every writeyes, if a new login is acceptable

LockSET NX PXtwo holders at oncethe TTL is the leaseno, for correctness fence at the store

Idempotency keySET NX EXan action runs twiceas long as clients retryno, when a duplicate costs money

QueueList, pub/sublost worknoneno, for work that must run

Rate limitINCR plus EXPIRE in Lua, or INCREX on Redis 8.8 and latera few extra requests passthe windowyes

Predict: a shared instance uses volatile-lru. Memory is 100% full and evicted_keys is 0. A new cache write with EX 60 arrives. What happens, and which one INFO line tells you why?
The write fails with an OOM error, even though it carries a TTL. INFO keyspace shows expires far below keys, because the memory is full of keys with no TTL. Most people expect Redis to evict an old key, and that is right for allkeys-lru. Under volatile-lru no key is a candidate, so Redis rejects the write instead.

Five facts produce that outcome:

- The volatile-* policies evict only keys that have a TTL. The eviction page says they "behave like noeviction if no keys have an associated expiration".

- When no key can be evicted, every write that needs memory fails with OOM command not allowed when used memory > 'maxmemory'. A correct new cache key fails too, because Redis checks memory before it runs the command.

- A plain SET removes an existing TTL. The SET page says "Any previous time to live associated with the key is discarded on successful SET operation". So one rewrite without KEEPTTL or EX makes a key permanent.

- In go-redis a zero duration means no TTL. So Set(ctx, k, v, 0*time.Hour) writes a key that never expires, with no error.

- The default policy depends on where Redis runs. Open-source Redis defaults to noeviction, and ElastiCache defaults to volatile-lru.

1,947of 3,000 no-TTL writes succeeded

0evicted_keys under volatile-lru

OOMfor SET newcache:1 v EX 60

6evicted_keys after allkeys-lru

One lab run measured this with maxmemory 20mb and volatile-lru. It used an x86_64 Homebrew build of Redis 8.10.1 under Rosetta 2, outside Docker. It wrote 3,000 keys of 10 KB with no TTL. After 1,947 writes the rest failed with OOM, and INFO keyspace showed keys=1947,expires=0. The write with EX 60 failed as well. After CONFIG SET maxmemory-policy allkeys-lru, the same write succeeded and Redis evicted 6 keys.

The platform had this outage. One service wrote keys with no TTL into the shared volatile-lru cluster. They filled memory, and writes failed for the services that shared it. The memory alert fired, but no team owned it, so nobody acted on it in time. Later a second service had a path that rewrote a session-memory key with a zero TTL, which removed its 24-hour TTL. The shared Go wrapper made the risk wider, because its raw Set needed the caller to pass a TTL and had no safe default. About 30 repositories depended on it.

Pendo had the same cause, and its Redis was still evicting keys. Its Redis on Google Memorystore was near the memory limit and evicting keys. CPU spikes made replies slow and connections fail. Two code paths created cache keys with no expiry. The guides service had about a 60% error rate for the first 90 minutes. Pendo flushed all Redis instances to recover, then fixed the two code paths and added safeguards and Redis monitoring.

Correction. The phase treats volatile-lru and allkeys-lru as the policy choices, and the original Phase 5 text counted 8. Redis 8.6 and later has 10, adding allkeys-lrm and volatile-lrm, which evict the least recently modified key. Valkey 9.1.2 still has 8. The phase also does not state the defaults: noeviction in open-source Redis 8.10.2, and volatile-lru on ElastiCache.

The fix has four parts. A pure cache instance uses an allkeys-* policy, so a forgotten TTL cannot block writes. The shared wrapper refuses a cache write with no TTL. Every rewrite of a key with a TTL uses KEEPTTL or sets the TTL again. An alert on the gap between keys and expires in INFO keyspace has a named owner.

Evidence
Eviction page, source line 118: https://redis.io/docs/latest/develop/reference/eviction/. OOM on writes: redis.conf 8.10.2 lines 1257 to 1262, and the default policy at line 1266. ElastiCache default: https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/ParameterGroups.Engine.html ("Default: volatile-lru"). OOM symptoms on ElastiCache: https://repost.aws/knowledge-center/oom-command-not-allowed-redis. SET page source line 140. go-redis string_commands.go v9.5.1 lines 163 and 171 to 179. INFO keyspace: server.c 8.10.2 line 7083. The lab: the study note, run on 2026-10-18 on an Apple M4 Pro with that x86_64 build under Rosetta 2, no persistence and no other load. Pendo status page, 2020-02-21: https://status.pendo.io/incidents/g8nfbs1vdn69. Trello, "The Trello tech stack", 2012-01-19: https://www.atlassian.com/blog/trello/the-trello-tech-stack. The platform's own outage cannot be checked from public sources.

Go deeper: KEEPTTL, the capstone guard, the session gap, and the other eviction policies
How the platform scored on the six jobs

The platform did all six jobs, and its gaps followed this order. The caches failed open but had no stampede protection, which costs latency. Sessions were written with a hash write and a separate EXPIRE, so a crash between the two left a session with no TTL. Every lock protected efficiency, such as not sending one email twice, and used a plain DEL with no fencing. That is acceptable only while nobody copies the pattern to a payment. Idempotency keys used SET NX EX, which is the right command for that job. List queues held only work that could be lost, and durable work ran on another system. Rate limits used a fixed-window counter in Lua, which is cheap and close enough. A sliding window on a sorted set is the more accurate upgrade.

The opposite design: Trello

Trello chose the opposite design. It put only data it could lose in Redis and said the application recovers "if any of these (or all of them) are lost". It ran allkeys-lru with about five times the working set in memory. The job decided the policy there, and that is the rule this table gives you.

Rewriting a key without losing its TTL

The phase's lab E6 shows a plain SET turning a TTL of 86400 into -1. A second run added one more step. SET key value KEEPTTL keeps the existing TTL: the TTL went from 86400, to -1 after a plain SET, and to 60 kept with KEEPTTL. In go-redis, pass redis.KeepTTL as the duration. Its value is -1.

The capstone guard refuses too much

The capstone client's Set returns ErrNoTTL when ttl <= 0. That blocks the zero TTL, which is the goal. It also blocks redis.KeepTTL, which is a valid use. A better guard refuses only zero: if ttl == 0 { return ErrNoTTL }. This follows from commands.go v9.5.1 line 23, where KeepTTL = -1.

The session write with two commands

A session written as a hash write followed by a separate EXPIRE has a short window. If the client process dies between the two, the hash exists with no TTL. Under volatile-lru it then stays until someone deletes it. Many such sessions slowly fill memory in the way this section describes.

The ten policies

PolicyCandidatesChooses by

noevictionnonerejects writes

allkeys-lru, volatile-lruall keys, or keys with a TTLleast recently used

allkeys-lfu, volatile-lfuall, or with a TTLleast frequently used

allkeys-random, volatile-randomall, or with a TTLrandom

volatile-ttlkeys with a TTLshortest TTL left

allkeys-lrm, volatile-lrmall, or with a TTLleast recently modified, Redis 8.6 and later

Eviction is approximate. Redis samples maxmemory-samples keys, default 5, into a pool of 16 candidates and evicts the best one.

The same cause at bsport

When bsport split its shared Redis, it found keys with no TTL that held data several years old. Teams had used Redis as a database. The split into one cluster per domain also stopped one domain's traffic from slowing another's.

Eviction is the loss you can see coming in INFO. A failover takes back writes with no warning at all, and the next section shows which jobs that breaks.

## What can a failover take back, and where must correctness live?

The table above said a lock or an idempotency key must not be the only copy in Redis. The reason is the failover from Phase 4. The primary replies OK to INCR or SET NX before any replica has the write. If the primary dies in that moment, the promoted replica never saw it, and the OK you already acted on is gone.

- client sends INCRprimary counter moves 1040 to 1041

- primary replies 1041the client uses ID 1041

- primary diesthe replica still holds 1040

- replica promotedit becomes the new primary

- next INCR returns 1041a second client gets the same ID

Example values, not measured. The order follows from asynchronous replication.

So INCR and SET NX are atomic on one node, and they are not durable across a failover. Redis runs one command at a time, so two clients never see the same INCR result from one primary. But a failover can hand out an ID again or give a lock to a second holder. Nothing returns an error, so nobody notices.

The WAIT command from Phase 4 makes the primary wait until a number of replicas confirm the write. It narrows the window, but it does not close it. The replication page says WAIT "does not turn a set of Redis instances into a CP system with strong consistency: acknowledged writes can still be lost during a failover".

The size of this loss was measured. Jepsen ran five Redis nodes with Sentinel, cut the network between them, and sent 2,000 writes. Redis acknowledged 1,998 of them, and only 872 were in the final data set. The report says "Redis threw away 56% of the writes it told us succeeded." That run used an old Redis and Sentinel. Asynchronous replication, the mechanism behind it, is still how Redis replicates today. The size of the loss on a current version has not been measured.

So correctness moves to the store that keeps the data. A conditional write is a write that the store applies only if a stated condition still holds, such as "the version is still 7". The fencing token from Phase 3 is one: the storage server remembers the highest token it accepted and rejects a write with a lower one. DynamoDB does the same with a version attribute. If the condition fails, the write fails and the caller reads again and retries.

The platform had an internal tool built this way. It handed out a fixed pool of test environments to CI runs that ran in parallel. A durable store held each claim with a version field and a conditional write, so only one run could win a given environment. Redis held one INCR counter that gave out IDs for new records. That split is right: Redis does the fast counting and the durable store enforces who owns what. It has one gap. After a failover the counter can repeat an ID. If each insert uses a "must not exist" condition, the durable store rejects the duplicate, but the tool's code for this was not checked.

Correction. The phase calls INCR "race-free ID allocation". It is free of races on one node, but IDs can repeat after a failover. The phase also ends on the thesis "Redis will not fail you; your usage of it will". That is false as a rule, because acknowledged writes can be lost in a failover with correct usage.

Evidence
Replication page, source lines 33 to 37: https://redis.io/docs/latest/operate/oss_and_stack/management/replication/. Jepsen, "Jepsen: Redis", 2013-05-18, five nodes with Sentinel and a network partition: https://aphyr.com/posts/283-jepsen-redis. Fencing: Kleppmann, "How to do distributed locking", https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html. DynamoDB optimistic locking: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/BestPractices_ImplementingVersionControl.html. Repeated IDs after a failover are inferred from the replication text, not run.

Go deeper: the token check in numbers, unlock commands in Redis 8 and Valkey, and when a repeated ID matters
The fencing check

Kleppmann's example uses two clients. Client 1 gets the lock with token 33, pauses, and its lock expires. Client 2 gets the lock with token 34 and writes. Client 1 wakes and sends its write with token 33. The storage server "remembers that it has already processed a write with a higher token number (34), and so it rejects the request with token 33". The check needs nothing from Redis except a number that grows. So the lock can live in Redis, and correctness lives in the store.

The safe unlock no longer needs Lua

Phase 3 released a lock with a Lua script that deletes the key only if it still holds your token. Redis 8.4 added DELEX key IFEQ value, which does that in one command. Valkey 9.0 added DELIFEQ. Redis 8.4 and Valkey 8.1 also accept SET ... IFEQ, which changes a value only if it still matches. These commands make the unlock shorter. They do not make the lock safe for correctness, because a failover can still lose the lock key itself.

When a repeated ID is harmless

A repeated ID matters only if IDs must be unique forever. If the ID is a hint and the durable store assigns the real key, a duplicate costs one retry. If the ID becomes a primary key with no "must not exist" check, a duplicate can overwrite a record. The review question is where the uniqueness is enforced.

You now know two ways a key disappears and which jobs each one breaks. The next section turns that into the order in which a review fixes things.

## In what order does a review fix what it found?

The two sections above give each finding a cost: eviction blocks writes for every service on the instance, and a failover breaks the jobs that need correctness. A review usually finds more problems than a team can fix in one quarter, so it needs an order. Three questions decide it, asked in this order:

- Has this failure already happened, and can it happen again? A failure that has happened has a known trigger and a known cost.

- What does a loss cost for this job? Use the job table: a cache loss is latency, and a lock loss on a payment is money.

- What does the fix cost? A one-line fix with a large risk goes before a migration with a small one.

A missing TTL on a shared volatile-* instance ranks first by all three, because it has happened and it stops writes for every service. Client version drift ranks low. It becomes a risk only when it meets something else, such as a stall that the old client waits through.

RankFix, in general termsWhy it sits here

P0Audit keys with no TTL on volatile-* instances. Fix the path that rewrites a session key with a zero TTL. Make the shared wrapper's raw Set refuse a zero TTL.it already caused an outage, and the live bug can cause it again

P0Give every memory alert a named owner.the alert fired in the outage, and nobody acted on it

The two P0 rows show the method. The full list of ten fixes, ranked P0 to P3, is in the Go deeper block below.

Every item on this platform's list is about how code used Redis. None says that Redis is too slow or the cluster too small. That is a finding about one platform, and it is not a rule. The section above showed a failover losing acknowledged writes when the code was correct.

Classify the job, ask what a loss costs, then fix what has already happened first.

Treating every Redis call alike lets a forgotten TTL stop writes for every service on a shared cluster.

Run INFO keyspace on an instance you use, and compare keys= with expires=.

Go deeper: isolating a shared instance, why each rank was chosen, and which engine runs it
One shared instance is one failure for everyone

The platform ran about 34 services on several shared clusters. So one service's keys could stop writes for every service on its cluster. Shopify had the same shape after it split its MySQL into shards. Every shard still shared one Redis, and an outage of that Redis took down all of Shopify. Its fix was pods, where each pod has its own MySQL, Redis and memcached. bsport gave each business domain its own cluster. The Figma case in concept c5 split by use case. A review of a shared instance should ask whether the services on it can afford to fail together.

The rest of the fix list

RankFix, in general termsWhy it sits here

P1Fence, or make idempotent, every flow that must happen once, before a SETNX lock with a plain DEL is copied to it.no failure yet, but a double charge costs money

P1Release locks with a random token and a compare-and-delete.a plain DEL can remove another holder's lock

P1Read the replica count for WAIT from the environment, never from a constant.a fixed count waits for replicas that some environments do not have

P2Add TTL jitter to caches filled in bulk, and singleflight on the hottest shared keys.keys that expire together send a stampede to the source

P2Alert on hot keys and on SLOWLOG, not only on capacity.a slow command blocks every client

P2Retire the oldest client, and set timeouts and context deadlines in all of them.it waits 3 seconds on every call during a stall

P3Converge on one reviewed client wrapper.it stops the drift and carries the guards

P3Use an allkeys-* policy on instances that hold only cache data.a forgotten TTL can then no longer block writes

The ranks, argued

- P0 items have already happened and are still live. They are cheap to fix and cost an outage to leave.

- P1 items are fine today because every lock only protects efficiency. The risk is a copy onto a path that needs correctness, and the fix is cheap insurance.

- P2 and P3 items make the system more resilient, but it works without them. Do them when you change that code, not as an emergency.

Ask which engine runs the instance

A review must first ask whether the instance runs Redis or Valkey, because some defaults differ. Valkey 9.1.2 sets lazyfree-lazy-user-del yes, so a plain DEL frees memory in the background. Redis 8.10.2 keeps it at no. The default repl-backlog-size is 10mb in Valkey 9.1.2 and 1mb in Redis 8.10.2. Evidence: valkey.conf 9.1.2 lines 1458 and 902, and redis.conf 8.10.2 lines 1379 and 779.

The review has now ranked what Redis can lose. It has not measured what the source of truth carries when the cache works less well, and the next concept starts there.

## Why does a small fall in hit rate overload the source?

A cache hides most of the real load, and a small change uncovers it.

The fix list ranked what Redis can lose. A cache that keeps all its keys can still fail the system, because the system was sized for how well it works. The origin is the database or service behind the cache that answers every miss. The hit rate is the share of reads the cache answers. The origin sees only the misses, so its load is the traffic times one minus the hit rate.

Predict: a cache in front of a database runs at a 99.5% hit rate. A deploy drops it to 98%. By what factor does the database read load change, and why might the real factor be higher?
The read load grows four times. The misses go from 0.5% to 2% of the traffic, and 2 divided by 0.5 is 4. The real factor is higher when one miss needs more than one query, such as a query on every shard. Most people read it as a 1.5-point change and expect a small effect, because they look at the hits and not at the misses.

The rule in words: origin load equals traffic times (1 − h). A fall from h1 to h2 multiplies origin load by (1 − h2) divided by (1 − h1).

99%   to 0%    (1 - 0)     / (1 - 0.99)  = 1    / 0.01  = 100x
99.5% to 98%   (1 - 0.98)  / (1 - 0.995) = 0.02 / 0.005 = 4x
99%   to 98%   (1 - 0.98)  / (1 - 0.99)  = 0.02 / 0.01  = 2x
99.9% to 0%    (1 - 0)     / (1 - 0.999) = 1    / 0.001 = 1000x

So the higher the normal hit rate, the larger the jump when it falls. A cache at 99.9% hides 999 of every 1,000 reads from the origin.

Origin load after a hit rate change

Normal hit rate, %
New hit rate, %
Origin load changes by , from  to  of the traffic

The slider uses the linear rule above. It is a lower bound, as the next case shows.

The platform had this failure on its hottest endpoint. A serializer marked a response as not cacheable whenever a media item was not in a final state. A callback that moved media out of one processing state had been turned off years before, so many thumbnails stayed in that state. Every request for that endpoint was marked not cacheable, and the shared client library never cached it. The source service saw about 30,000 calls per minute instead of about 300, which is 100 times. There was no error and no related deploy. Many services became slow, and the change was visible only in call volume and CPU metrics, not in logs. A one-file fix marked those responses cacheable again, and p90 latency for the endpoint went from 100 ms to 20 ms.

Correction. The phase's check question says the fix cut origin traffic by 80%, "so the hit rate is around 80%". Its own numbers, 30,000 down to 300 calls per minute, are a 99% drop. So the restored hit rate is near 99%.

Slack saw the miss path cost more than one query each. An upgrade restarted Consul agents on 25% of the fleet at peak traffic. Each restart replaced a memcached node with an empty one, so the hit rate fell. A missed lookup of group message membership ran a scatter query on every shard, because that keyspace was sharded by user. The post says "the read load increased superlinearly in relation to the percentage of cache misses". Queries timed out, so the cache could not refill, and the overload held itself in place. Slack throttled client boot, read only the missing rows, read from replicas, and raised the throttle in small steps.

The check that catches this before production is a load test with the cache cold or turned off. AWS names the failure a service "addicted to its cache" and says "Run load tests with caches disabled to validate this." For a cold start it names request coalescing, which sends one origin read for many waiting misses of the same key.

The origin carries the misses, so measure what it does at your worst hit rate.

Reading a fall from 99% to 98% as one point hides a doubled origin load.

Find your cache's hit rate, double its miss share, and compute the new origin load.

Evidence
Slack, "Slack's Incident on 2-22-22", 2022-04-26: https://slack.engineering/slacks-incident-on-2-22-22/. AWS Builders' Library, "Caching challenges and strategies": https://aws.amazon.com/builders-library/caching-challenges-and-strategies/. The arithmetic is inferred from the definition of hit rate. The platform's numbers (300 and 30,000 calls per minute, p90 100 ms to 20 ms) come from the phase and cannot be checked from public sources.

Go deeper: Facebook's loop, Stack Overflow's local cache bug, and the rest of the platform incident
Facebook: errors that deleted the cache

A bad configuration value made every client treat its cached copy as invalid and query the database. Clients that got an error from the database deleted the cache key, so the next read missed again. The loop kept itself going, and the site was down for about 2.5 hours. The fix was to stop all traffic to that database cluster and turn off the code that fixed the cached value. The lesson for a review is that the error path of a cache must not delete what it cannot refill.

Stack Overflow: a TTL bug in the local cache

Stack Overflow keeps an in-memory cache on each web server in front of Redis. A TTL bug made about 95% of keys stop filling that local cache, so those reads all went to Redis. Redis had room for it, so nothing broke, and nobody noticed for hours. A hit rate fall in one layer moves load to the next layer, so watch the hit rate of every layer.

The platform incident, the rest of the numbers

- Traffic to the source service fell by about 80% after the fix.

- DynamoDB read capacity fell from about 35,000 to about 7,000 units per minute.

- Latency in the services downstream of it fell by about 60%.

- Fail-open guards in the settings read path stopped the incident from getting worse.

Read with the earlier phases, one boolean touched four ideas. The source queued requests behind each other, as Phase 0's single thread does. The cacheable flag and the 1/(1 − h) rule are Phase 2. One hot endpoint carried the load, as in Phase 5's hot keys. The visible signal was call volume and p90, not SLOWLOG.

The arithmetic of lab E5

h = 0.9    amplification when caching breaks = 1 / (1 - 0.9)   = 10x
h = 0.99                                        1 / (1 - 0.99)  = 100x
h = 0.999                                       1 / (1 - 0.999) = 1000x
30,000 -> 300 calls per minute = 1% of the uncached load, so h is about 0.99

Hit rate tells you how much load the cache removes. It does not tell you whether the value it returns is current, and the next concept follows one change through every layer of a cache.

## When does a change reach every reader of a layered cache?

Each cache layer keeps its own copy, so each layer needs its own invalidation.

The last concept measured how much load a cache removes. This one asks whether the value it returns is current. The platform's most-read cache held company settings, and it had more than one layer. An in-process cache is a map in the memory of each server process, read without any network call. It sits in front of Redis to absorb the hottest reads. The source service used delete-on-write: on every change it deleted the Redis key, so the next reader missed and loaded the new value.

- source serviceupdates settings, deletes the Redis key

- Redis, 1 hour TTLshared by every service through one library

- in-process, 5 or 10 minin two services, no listener

- function cache, 10 minits own copy, TTL only

The layers of the reviewed settings cache, from the phase.

The phase called this design race-free and said the worst-case staleness is the TTL. The staleness bound is the longest time a reader can see the old value after a change. For a layered cache it is not one TTL.

Predict: layer 1 is in-process with a 5-minute TTL and no listener. Layer 2 is Redis with a 1-hour TTL and delete-on-write. A setting changes. What is the worst-case staleness if the delete works, and if the delete is lost?
If the delete works, readers can see the old value for up to 5 minutes, because layer 1 never hears about the change. If the delete is lost, Redis keeps the old value for up to 1 hour. Layer 1 can refill from Redis a moment before Redis expires and keep that copy 5 more minutes. So the bound is about 1 hour and 5 minutes. Most people answer "the TTL", because they picture only the Redis layer.

- t = 0 The setting changes, and the source deletes the Redis key.

- 0 to 5 min Layer 1 still serves the old value it loaded before the change.

- 5 min Layer 1 expires, reloads from Redis, and gets the new value.

- if the delete was lost Redis serves the old value until its TTL ends at 60 min.

- 59 min 59 s Layer 1 reloads the old value from Redis a moment before Redis expires.

- 65 min The last reader sees the new value.

Two rules give that bound:

- A layer that is not invalidated stays stale for up to its own TTL after every change.

- A lost delete in a lower layer adds that layer's TTL, because the upper layer can refill from it at the last moment.

In the platform, the two services with in-process caches were stale for up to 5 or 10 minutes after each change, even when the Redis delete worked. This is inferred from the design as the phase describes it.

Delete-on-write also races with a reader that missed. The steps happen in this order:

- A reader misses in Redis and reads the old row from the database.

- A writer updates the row in the database.

- The writer deletes the Redis key. There is nothing to delete yet.

- The reader, still holding the old row, writes it to Redis with a full TTL.

- Every reader now gets the old value until that TTL ends, and no error appears.

Uber closes this gap with a Lua script that writes into the cache only if the row's timestamp is newer than the cached one.

Correction. The phase says delete-on-write is "race-free (delete not update)" and "Worst-case staleness = the TTL". A reader that missed can store the old value after the delete. For layers that are not invalidated, staleness is their own TTL after every change, and a lost delete adds the Redis TTL.

An in-process layer needs its own message to drop its copy. Stack Overflow runs an in-memory cache on each web server in front of Redis. On a change, it deletes the value in Redis first, and then publishes the key on a purge channel. Each web server drops its local copy when the message arrives. The post says the order matters, because reversing these "would create a race and end up in a re-fetch of the old value sometimes". If the servers dropped their copies first, one could reload the old value from Redis before Redis was purged.

Staleness is the sum of every layer that can miss the change.

Calling delete-on-write race-free lets a stale value live a full TTL with no error.

List the cache layers in front of one value you own, and add their TTLs.

Evidence
Stack Overflow, Nick Craver, "How we do app caching", 2019-08-06: https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/. Client-side caching, sections "Avoiding race conditions" and "What to do when losing connection with the server": https://redis.io/docs/latest/develop/reference/client-side-caching/. Uber, "How Uber Serves Over 40 Million Reads Per Second from Online Storage Using an Integrated Cache", 2024-02-15: https://www.uber.com/blog/how-uber-serves-over-40-million-reads-per-second-using-an-integrated-cache/, read through a fetch summary, so the quotes there are not exact text. The race and the staleness sum are inferred from the order of operations. A two-layer lab would confirm them. It is described as L4 in the practice part and was not built.

Go deeper: Uber's cache in front of its database, Stack Overflow's numbers, fixed TTLs, and a fourth reader
The same design built into Redis

Redis offers this design as a built-in feature called client-side caching. The client sends CLIENT TRACKING ON, and Redis sends it an invalidation message when a key it read changes. The docs give two rules for it. First, put a placeholder in the local cache before the GET, or an invalidation that arrives before the reply leaves a stale value. Second, "Make sure that if the connection is lost, the local cache is flushed". That second rule exists because the messages are not stored, as concept c5 shows for pub/sub.

Uber: invalidation from the database log

Uber puts Redis in front of Docstore, its MySQL-based database. Change data capture reads the database's binlog and invalidates the changed rows in Redis. A 5-minute default TTL is the backstop when an invalidation is lost. Cache writes go through a Lua script that writes only if the row's timestamp is newer, which closes the race above. A shadow mode compared cached values with the database and measured the cache as 99.99% consistent. The system serves over 40 million reads per second. A sliding-window circuit breaker stops calls to a Redis node that is failing.

Stack Overflow's scale

Its post reports a peak of 86,982 Redis commands per second, counted across all instances including replicas. Average CPU was about 2%, with a peak near 3%. It ran 2 physical Redis servers per data center. Its post does not say what happens when a purge message is lost. Concept c5 answers that question in general.

Fixed TTLs and the hourly spike

Every layer of the platform's settings cache used a fixed TTL with no jitter, and nothing stopped a stampede. If a deploy warms many keys at once, they all expire one TTL later, and every server misses in the same second. That is the scenario of lab E9: a latency spike in the source every hour after a deploy. The fixes are from Phase 2. Add random jitter to each TTL. Use singleflight, so one request per key reads the source while the others wait for it.

A new reader of the same value

If a team adds another consumer of the settings with its own cache and no invalidation, it is stale for its whole TTL after every change. It must either receive the invalidation or accept the TTL as its documented staleness.

Stack Overflow's purge channel uses Redis pub/sub. The next section shows what a server misses when it is not connected at the moment a message is sent.

## What does a server miss while it is not subscribed?

Pub/sub keeps no copy, so a message is lost the moment no one is there.

The last section ended on Stack Overflow's purge channel, which tells every web server to drop a local copy. The chat team wants the same tool for a different job. Its users connect to many WebSocket servers, and a message from a user on server A must reach a user on server C. Each server subscribes to the channels of its connected users, and the sending server publishes to that channel.

Pub/sub is Redis's publish and subscribe feature: PUBLISH channel message sends the message to every client subscribed to that channel at that moment. Redis keeps no copy of the message. So delivery is at-most-once, which means each subscriber gets a message once or never, and never a second time. This is fast and simple, and it is the reason the design loses messages.

Predict: server C's connection to Redis drops for 2 seconds, and then it subscribes again. During the gap, server A publishes 3 chat messages for users on C. How many does C receive after it subscribes again, and what did each PUBLISH return?
C receives none of the 3. Each PUBLISH returned 0 if C was the only subscriber, because the return value counts the clients that got the message. Most people expect Redis to hold the messages for C, as a message broker such as RabbitMQ does with a queue. Pub/sub has no queue. A subscriber gets only what is published while it is connected and subscribed.

Chat messages from server A to server C

Step 1: C is subscribed, so PUBLISH returns 1 and C gets m1.

Step 2: C's connection to Redis drops. Redis removes its subscriptions.

Step 3: A publishes m2. No client is subscribed, so PUBLISH returns 0 and m2 is gone.

Step 4: C connects and subscribes again. Redis has nothing to give it.

Step 5: C gets m3, the first message published after it subscribed.

The same order was seen in a lab run on Redis 8.10.1, x86_64 under Rosetta 2. The widths are an illustration.

Four facts decide what the chat design loses:

- PUBLISH finds the channel's subscribers, appends the message to each one's reply buffer, and returns their count. The pub/sub page says that if the subscriber cannot handle the message, "for example, due to an error or a network disconnect", the message "is forever lost".

- The return value is not a delivery receipt. It counts clients whose buffer got the message, not clients that read it. In a cluster it counts only subscribers on the node that ran the PUBLISH.

- A slow subscriber's messages wait in its output buffer, the memory Redis holds for replies that a client has not read yet. The default client-output-buffer-limit pubsub 32mb 8mb 60 closes a subscriber at once above 32 MB, or after it stays above 8 MB for 60 seconds. Redis 8.10.2 and Valkey 9.1.2 use the same default.

- When Redis closes a subscriber, it drops the buffer with the messages in it. The subscriber sees a closed connection, reconnects, and has no way to learn what it missed.

1 MBhard limit set for the run

2,000messages of 10 KB to a subscriber that never read

closedRedis disconnected the subscriber

0what the next PUBLISH returned

In that lab run, INFO stats then showed client_output_buffer_limit_disconnections:1. So a chat server that stops reading for a while loses every message from the moment Redis cuts it off. A long garbage collection pause or a slow WebSocket write can cause that stop. This last step is inferred from the run, not measured on a chat server.

Evidence
Pub/sub page, source lines 56 to 64: https://redis.io/docs/latest/develop/pubsub/. PUBLISH return value in a cluster: PUBLISH page, source line 72. Default limits: redis.conf 8.10.2 line 2476 and valkey.conf 9.1.2 line 2451. PUBLISH appends to each subscriber's buffer: pubsub.c 8.10.2 lines 469 to 530. The lab runs: the study note, Redis 8.10.1 as an x86_64 build under Rosetta 2 on an Apple M4 Pro, outside Docker. They used raw RESP over sockets on 2026-10-18.

Go deeper: pattern subscriptions, and the same buffer limit on replicas
Patterns cost the publisher

After the channel's own subscribers, PUBLISH loops over every pattern that any client subscribed to with PSUBSCRIBE and matches the channel name against each one. That work runs on the main thread. So its cost grows with the number of subscribers plus the number of patterns. This is inferred from the loops in pubsub.c and not timed. A chat design with one pattern per user would make every message slower.

Replicas have an output buffer too

Replicas use the same mechanism with a larger default, 256mb 64mb 60. GitLab once saw its replica output buffer limit exceeded. Both replicas lost their link to the primary and started a full resync, and it happened again an hour later. GitLab raised the limit to 8 GiB hard and 4 GiB soft over 180 seconds. A buffer limit protects Redis memory, and the price is a disconnected client, whether that client is a replica or a chat server.

One Redis node loses messages only when a subscriber is gone. A cluster adds two more ways to lose them, and a cost that can stop the cluster, which the next section shows.

## What changes when the chat runs on a Redis Cluster?

On one node a message is lost only when its subscriber is gone. The platform's cluster had many nodes, and the chat servers would connect to different ones. The nodes of a Redis Cluster talk to each other over the cluster bus, a second TCP connection between every pair of nodes. It carries failure detection and slot ownership. Classic pub/sub uses that bus too, and that is where the cluster adds its costs.

Classic PUBLISH in a cluster

- Server A publishes on node 1.

- Node 1 sends the message to every other node over the cluster bus.

- Each node delivers it to its own subscribers.

- Every message costs work on every node, so adding nodes adds work for each message.

Sharded SPUBLISH

- The channel name hashes to a slot, like a key.

- Server A publishes on the node that owns that slot.

- The message stays inside that shard, the primary and its replicas.

- Subscribers use SSUBSCRIBE on that shard, so other shards do no work.

Sharded pub/sub is the form added in Redis 7.0, with the commands SSUBSCRIBE and SPUBLISH. It keeps each channel inside the shard that owns its slot. The original Phase 4 text described classic pub/sub in a cluster as not routed. In fact the source broadcasts every PUBLISH to every node on the bus.

Figma saw what the broadcast can cost. It had moved its pub/sub load to a cluster-mode ElastiCache instance a few weeks before. Then engine CPU on one node reached 100%, and users could not open new files in four outages of 7 to 80 minutes. The team first thought it lacked capacity and moved to a larger cluster with more nodes, which made it worse. AWS found the cause in how pub/sub messages travel on the cluster bus, which is built for control traffic. When messages could not be sent fast enough, the bus buffer grew. Each send trimmed that buffer with memmove, so the CPU cost grew with the buffer, and the loop fed itself. Figma moved all pub/sub off clustered ElastiCache and gave each major use case its own instance.

Sharded pub/sub brings its own loss. When a node loses a slot, for example in a resharding or a failover, Redis sends the subscribers of that slot's shard channels an unsubscribe message. The client must subscribe again on the new owner. Messages published before it does so are lost, by the rule of the last section. Whether go-redis subscribes again by itself after such an unsubscribe was not checked, and a chat design depends on that answer.

The team also asked whether presence could use expiry events. A keyspace notification is a pub/sub message that Redis publishes when a key changes, such as an expired event when a key with a TTL is removed. These follow the same at-most-once rule. They have two more limits for presence:

- The expired event fires when Redis deletes the key, "not when the time to live theoretically reaches the value of zero". Redis deletes expired keys on access or in a background cycle, so the delay can be large.

- In a cluster each node publishes events only for its own keys, so a listener must subscribe on every node.

So an expired event is a poor timer for "this user went offline". The next section shows the design that real presence systems use instead.

Evidence
Sharded pub/sub and the broadcast: pub/sub page source lines 199 to 208, https://redis.io/docs/latest/develop/pubsub/, and cluster_legacy.c 8.10.2 lines 4070 to 4085. The unsubscribe on a slot move: pubsub.c 8.10.2 line 321 and cluster_legacy.c lines 5187 and 5390 to 5392. Figma, "Postmortem: Service disruptions on June 6 and 7, 2022", 2022-06-15: https://www.figma.com/blog/postmortem-service-disruptions-on-june-6-and-7-2022/. Keyspace notifications page, sections "Timing of expired events" and "Events in a cluster": https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/.

Go deeper: what else Figma learned, and pattern channels in a shard
Figma's other findings

Figma ruled out backups, a spike in commands, slow commands and big keys before it found the cause. AWS rate limits on manual failover blocked one failover during the incident. More nodes lowered the load needed to start the loop, which is why the larger cluster made things worse. Figma now plans regular drills that run core features with ElastiCache turned off.

Sharded channels have no patterns

Sharded channels ignore patterns: there is no sharded form of PSUBSCRIBE. A design that subscribes to room:* must list its channels instead. Because each channel lives in one shard, a very busy chat room becomes a hot shard, in the same way as Phase 5's hot keys.

Pub/sub drops messages on a disconnect, on a full buffer and on a slot move. The next section shows how real chat and presence systems get those messages back.

## How do real chat and presence systems recover what pub/sub dropped?

The last two sections found three ways for pub/sub to drop a message: a disconnect, a full output buffer and a slot move. Real systems that use pub/sub between servers do not try to stop those losses. They keep a second copy that a reader can fetch after it was away, and they use pub/sub only to say that something new exists.

- 1 append to a logthe message gets an ID, such as 1041

- 2 publish a wake-up"room 42 has new messages up to 1041"

- 3 connected servers readeach reads from its last seen ID, then sends to its users

- 4 a server reconnectsit missed the wake-ups while it was away

- 5 it reads the gapeverything after its last seen ID, from the log

The general design, inferred from the three systems below.

Three systems built this, each with a different log:

- Trello used Redis pub/sub to send object changes between its server processes. It also stored each message in a fixed-length list per model, with a counter of all messages ever added. A browser that used polling instead of a WebSocket asked whether anything had changed since its last poll. In most cases the server answered with one Redis read.

- Discourse's message_bus library keeps a backlog in Redis, by default 2,000 messages for all channels and 1,000 per channel. The client sends the last message ID it saw and gets the gap. A keepalive message every 60 seconds detects a subscriber that stopped receiving, and it reconnects after 3 missed intervals.

- Socket.IO's Redis adapter sends packets between servers over pub/sub. Its docs say that if the connection to Redis is cut, packets go only to the clients on the current server. Its docs say the Redis Streams adapter handles a temporary disconnection from Redis and can "resume the stream without losing any packets". Its stream is trimmed to about 10,000 entries by default, so a longer gap can still lose packets. That last point is inferred from the maxLen default.

A Redis Stream is an append-only log inside Redis, where every entry gets an ID that grows with time. A reader asks for entries after the last ID it processed, so a reader that was away reads exactly what it missed. A consumer group lets several readers share a stream. Redis tracks each delivered entry in a pending list until the reader confirms it with XACK. XAUTOCLAIM hands the pending entries of a crashed reader to another one. MAXLEN or MINID trims the stream, so its memory stays bounded.

A Stream is still Redis memory. The two losses of concept c2 still apply to it: eviction can remove it, and a failover can lose its newest entries. So choose the log by what a lost message costs.

- Must a message survive a subscriber's disconnect?

- noplain pub/sub, such as a typing indicator

- yeskeep a log, then ask the next question

- Must it also survive a Redis failover or a full memory?

- noa Redis Stream or a list with an ID, trimmed by length

- yesa database or Kafka holds the log, and Redis only sends the wake-up

Presence needs a different tool, because "online" is a state, not a message. A heartbeat is a small message that a client sends every few seconds to say it is still connected. LinkedIn's presence platform treats a member as online while heartbeats arrive every d seconds. The entry expires after d + ε seconds, where ε is a small margin. A delayed trigger at d + 2ε checks for "offline". A member who reconnects within d seconds stays online, so a short network drop does not show as offline and online again. LinkedIn says any key-value store with high read and write volume can hold the entries. In Redis the same design is SET presence:<user> 1 EX <d+ε> on each heartbeat, with your own delayed check, not the expired event. That Redis form is inferred from LinkedIn's design and was not run.

Pub/sub only wakes servers up, and the messages they must not miss live in a log.

Using pub/sub alone loses every message sent while a server is slow or reconnecting.

Watch client_output_buffer_limit_disconnections in INFO stats on a Redis that serves pub/sub.

Evidence
Trello, "The Trello tech stack", 2012-01-19: https://www.atlassian.com/blog/trello/the-trello-tech-stack. Discourse message_bus README, main branch: https://github.com/discourse/message_bus. Socket.IO: https://socket.io/docs/v4/redis-adapter/ and https://socket.io/docs/v4/redis-streams-adapter/, read from the website's source repository because the live pages timed out. LinkedIn, "Now you see me, now you don't", 2018-01: https://engineering.linkedin.com/blog/2018/01/now-you-see-me--now-you-dont--linkedins-real-time-presence-platf. Harness on Redis Streams, 2021-11-17: https://harness.io/blog/event-driven-architecture-redis-streams. No named company with public numbers runs chat or presence on Redis pub/sub at scale. Trello is the closest, and it has no load numbers.

Go deeper: what consumer groups cost, Trello's move to Kafka, and two Redis queues that failed
The pending list grows

XREADGROUP without NOACK adds every delivered entry to the group's pending list. An entry stays there until XACK. A reader that crashes leaves its entries pending until another reader claims them. So a group whose readers never confirm grows without limit in memory. Harness built its event system on Streams with XREADGROUP, XACK, XAUTOCLAIM and MAXLEN or MINID. It reported three problems: the memory cost, one failing message blocking the head of the stream, and no built-in lag metric.

Trello left Redis pub/sub

Trello later moved its WebSocket updates from Redis pub/sub to RabbitMQ, and then to Kafka. Its post gives no reason for leaving Redis pub/sub. Redis Streams were not released yet when it chose, and lossless failover with Sentinel was not tested. After Kafka, memory use fell about 33%, CPU use about doubled, and cost fell about 5 times. Earlier, Trello reported that Socket.io with its Redis store had scaling problems above about 10,000 connections.

Queues on Redis that lost or stopped work

- Discord fed new messages to its search indexers through a Redis queue. When search nodes failed, the queue backed up, Redis CPU hit its limit, and Redis dropped messages. Discord moved the queue to Google Cloud Pub/Sub, which guarantees delivery.

- Slack's job queue on Redis filled to maxmemory when job execution slowed. Dequeue also needs free memory, because it moves a job to an in-flight list, so the queue stayed stuck after the database recovered. Slack put Kafka in front of Redis, with a relay that moves jobs into Redis at a set rate.

What was not checked

Whether the go-redis PubSub type subscribes again after a reconnect, or after a sharded unsubscribe caused by a slot move, was not read in its code. Test it before a chat design depends on it.

That is the last teaching section. The recall section below puts the five claims together as one review.

## What you can do now, and what comes next

You can now review any Redis call with five questions, one for each concept of this lesson:

- How long does this call wait when Redis stalls, and does the request deadline reach the socket? A go-redis call waits for its ReadTimeout, 3 or 5 seconds by default, on each attempt, unless ContextTimeoutEnabled is on. A timed-out connection must be closed, or the next request can read the old reply. (Concept c1, the first two teaching sections.)

- What job does this key do, and can Redis remove it? Eviction under volatile-* skips keys with no TTL, so they can stop all writes. A failover can undo an acknowledged INCR or lock. So rank the fixes by what has happened, what a loss costs, and what the fix costs. (Concept c2.)

- What does the origin carry if this cache gets worse? It carries the misses, so 99% to 98% doubles its load, and a miss that fans out costs more. (Concept c3.)

- How stale can a reader be? Add the TTL of every layer that can miss the change, and remember that a reader can store an old value after the delete. (Concept c4.)

- What does a server miss while it is away? With pub/sub alone, everything. A log with IDs lets it read the gap, and presence uses heartbeats with a TTL. (Concept c5.)

The next phase, Phase 7, "Redis for AI agents", is the last phase of the course. It uses these ideas for caches, vectors, memory, token streams, limits and tool queues in an AI agent platform. Before you start it, apply these five questions to one service you work on, as lab E10 asks. Then write its fix list in the order of the c2 ranking.

## Lab: the exercises that teach Phase 6

Open the lab: the phase's exercises E1 to E10, and four extra runs

This lab was copied from the phase and was not run for this lesson. Do not start it against a shared or production Redis. Where the phase named the former employer, its services or its incidents, the wording is changed to the general terms this lesson uses. The task is the same. References to the phase's own section numbers now point to this lesson's concepts. A short note under an exercise says what is wrong in it and what to expect instead.

Setup:

cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d && docker exec redis-study redis-cli PING   # → PONG

-  E1. Run the capstone client. c1, c2

- Run, from the code folder: go run ./phase06_*/prodclient

- Expected: no-TTL Set rejected; cache-aside miss→hit (1 source load); MGet one round-trip; safe WithLock.

- Teaches: every phase's lesson as one production-grade object.

The phase's folder still carries the former employer's name, so this page uses a glob. It matches because only one folder starts with phase06_. The program's comments and three of its output lines name the employer or its internal incident ID, and need the rename the study note lists. The client does not set ContextTimeoutEnabled, and its Set also refuses redis.KeepTTL. Its cache-aside has no jitter or singleflight. On Redis 8.4 and later its Lua unlock can be one DELEX ... IFEQ, but the lab's container runs redis:7.2. The expected output above still holds, as far as reading the code shows.

-  E2. Prove the no-TTL guardrail. c2

- Read prodclient's Set: it returns ErrNoTTL on ttl <= 0. Question: which two bugs in the platform would this have prevented? (The keys with no TTL that filled the shared cluster; the session-memory path that wrote 0*time.Hour.)

- Teaches: a guardrail beats a code-review catch.

-  E3. Classify five real Redis calls. c2

- Open five Redis call sites across services you can reach (or the anchors from Phases 1–5). For each, name: the job (of the six), the structure, the phase, the blast radius if it fails.

- Teaches: the job table of concept c2 as a working tool.

-  E4. Trace one cache invalidation. c4

- In a codebase you can reach, follow one write of a cached value → the key delete → the read through the shared client. Draw the delete-on-write + TTL-fallback flow from memory, then check it against the code.

- Teaches: the reference invalidation design of concept c4.

The phase traced the former employer's settings cache, which is not public. Add every cache layer you find, and the TTL of each, to get the staleness bound.

-  E5. Reproduce the load-multiplier math. c3

- Compute: for hit rates 0.9, 0.99, 0.999, what's the amplification 1/(1-h) when caching breaks? Then: the fix dropped traffic 80% — infer the restored hit rate.

- Teaches: why one boolean = 100x.

The phase's answer says an 80% traffic drop means a hit rate near 80%. The 80% is the drop in all traffic to the source service. The endpoint itself went from 30,000 to 300 calls per minute, which is a 99% drop, so the restored hit rate is near 99%. Add one more case: 99.5% to 98% is 4x.

-  E6. (Break it) Simulate the zero-TTL rewrite. c2

- Run: docker exec redis-study redis-cli SET sess:mem:u1 data EX 86400 (correct), then docker exec redis-study redis-cli SET sess:mem:u1 data (the rewrite path — strips TTL), then docker exec redis-study redis-cli TTL sess:mem:u1 (→ -1, permanent).

- Teaches: how a re-SET without TTL creates unevictable ballast.

Add three more steps: SET the key with EX 60, then SET it again with KEEPTTL, then read its TTL. A run of these steps gave 86400, then -1, then 60 kept.

-  E7. Audit a cluster for no-TTL keys. c2

- Run: seed a mix, then SCAN and TTL each; count -1s. (In prod: redis-cli --scan | while read k; do echo "$(redis-cli TTL "$k") $k"; done | grep '^-1' — sample, don't run on a huge keyspace.)

- Teaches: how you'd actually find this outage's risk before it fills the cluster.

Start with INFO keyspace and compare keys= with expires=. It answers in one command. The loop above costs one round trip per key, so use it only to sample.

-  E8. Build your own fix. c2

- Take the P0 zero-TTL bug: write the corrected Set call (preserve the 24h TTL on the rewrite path). Compare to prodclient's mandatory-TTL Set.

- Teaches: the actual fix, in code.

-  E9. The full-course drill (no hints). c3, c4

- Given: "settings reads spike the source service's latency every hour on the hour after a deploy." Diagnose using all six phases: what's happening, which phase's concept explains it, and the fix. (Hint: synchronized TTL expiry + no jitter + no stampede protection.)

- Teaches: cross-phase synthesis on a novel scenario.

-  E10. Write the scorecard for one service. c2

- Pick one service you own that uses Redis. Produce its mini fix-list (P0–P3) using the c2 ranking: what are its no-TTL risks, lock safety, N+1s, client version, monitoring?

- Teaches: the deliverable — Redis judgment applied to real code.

### Four extra runs from the study note

These are not in the phase. The first two were run once on an Apple M4 Pro. Redis 8.10.1 there was an x86_64 build under Rosetta 2. The last two were not built.

- L1, a full instance under volatile-lru. Set maxmemory 20mb and maxmemory-policy volatile-lru. Write 3,000 keys of 10 KB with no TTL, then one SET ... EX 60. Expected: 1,947 writes succeed, the rest and the TTL write fail with OOM, and evicted_keys stays 0. Then switch to allkeys-lru, and the write succeeds. (Concept c2.)

- L2, pub/sub loss. Publish while a subscriber is connected, after it disconnects, and after it subscribes again. Then send many messages to a subscriber that never reads, with a 1 MB hard limit. Expected: PUBLISH returns 1, then 0, the missed message is not replayed, and client_output_buffer_limit_disconnections becomes 1. (Concept c5.)

- L3, timeout against context. Use a go-redis v9.5.1 client with ReadTimeout unset and a 200 ms context. From another connection run CLIENT PAUSE 4000 ALL. Measure the wait with and without ContextTimeoutEnabled. Do not use DEBUG SLEEP, because enable-debug-command is no by default. Not run. (Concept c1.)

- L4, layered staleness. Put an in-process map with a 5 s TTL in front of Redis with a 60 s TTL. Change the source, delete the Redis key, and measure how long each reader is stale. Then repeat with a pub/sub purge and stop the listener. Not built. (Concept c4.)

The phase also had a section of checks against the former employer's own repositories. They need private code, so this lesson leaves them out. Exercises E2, E4, E8 and E10 cover the same skills on code you can reach.

## Checkpoint questions

Open the questions: nine scenarios, each with an answer sketch

Q1. In four sentences, describe the platform's Redis to a new engineer: the platform and topology, the six jobs, the caching style, and the one failure that repeated.

Answer sketchAbout 34 services shared several managed Redis clusters. The one under review used volatile-lru, RDB backups and no AOF. Redis did caching, sessions, locks, idempotency keys, queues and rate limits. Caches used cache-aside with delete-on-write and a TTL backstop, and every lock protected efficiency only. The repeated failure was the missing TTL, which filled the shared memory once and stayed live in a session-memory path.

Q2. A hot endpoint ran at about a 99% hit rate, and a flag stopped it from being cached. Explain why the source then saw about 100 times the load, why there was no error, and why a one-file fix worked.

Answer sketchThe source carries traffic times (1 − h). At h = 0.99 that is 1% of the traffic, and at h = 0 it is 100%, so 1 / 0.01 = 100 times. Nothing failed, so no error was logged: requests only became slow, and the signal was call volume and CPU. Marking the responses cacheable again restored h near 0.99, so the load fell back from about 30,000 to about 300 calls per minute.

Q3. A new service must cache user profiles, stop a "send welcome email" action from running twice, and rate-limit an API. For each, give the structure, the TTL, the loss you accept and the pattern you would copy. Which one would you block in review if it used a SETNX lock released with a plain DEL?

Answer sketchProfiles: a string or hash with cache-aside, delete-on-write and a TTL with jitter. You accept a slower request. Welcome email: SET NX EX as an idempotency key with a TTL as long as retries can happen. A lost key can send a second email. Rate limit: INCR plus EXPIRE in one Lua script, with the window as TTL. On Redis 8.8 and later, INCREX with EX and ENX does both in one command, but Valkey has no INCREX. You accept a few extra requests. Block the email path if its "once only" matters to the business, because a plain DEL can remove another holder's key and a failover can lose it.

Q4. Someone says "just use one store" for the CI allocator that kept claims in a durable store with a version field and IDs in a Redis INCR. Defend the split, then give the general rule.

Answer sketchThe durable store holds who owns each environment, and its conditional write lets exactly one run win. Redis gives out IDs fast and atomically on one node. Correctness lives in the durable store, because a Redis failover can repeat an ID or lose a lock. The rule: use Redis for fast parts that can be lost or repeated, and enforce correctness with a conditional write where the data lives.

Q5. You are asked to make settings changes visible at once everywhere. The design has Redis with a 1-hour TTL and delete-on-write, plus in-process caches of 5 and 10 minutes with no listener. Which layer is already immediate, which is bounded and by how much, and what would you change?

Answer sketchThe Redis layer is immediate when the delete works, and bounded by 1 hour when it is lost. The in-process layers are bounded by 5 and 10 minutes after every change. To make them immediate, delete in Redis first and then publish the key on a purge channel, as Stack Overflow does. A purge lost while a server is disconnected leaves that server stale for its TTL, so flush the local cache on every reconnect. Every server then misses at once after a change, so add singleflight to avoid a stampede on the source.

Q6. Give the P0 items of the fix list from memory, with the failure each prevents. Why is the no-TTL audit P0 and the client convergence P3?

Answer sketchP0: audit keys with no TTL, fix the zero-TTL rewrite, make the shared Set refuse a zero TTL, and give memory alerts an owner. They prevent the outage that already happened once. The audit is P0 because it has happened, it can happen again, and it stops writes for every service. Client convergence is P3, because drift causes harm only together with another failure.

Q7. The phase's thesis was "Redis doesn't fail, usage does." Give two cases in this lesson that support it, and one that shows it is false as a rule.

Answer sketchFor: the missing TTL that filled the shared cluster, and the cacheable flag that sent 100 times the load to the source. Both had a preventable cause in the code. Against: Jepsen's partition test, where Redis acknowledged 1,998 writes and kept 872, with correct use. A review must check both the usage and the guarantees Redis gives.

Q8. Your go-redis v9.22 service sets no timeouts and has a pool of 10. Redis stops answering for 8 seconds, and 50 requests arrive. What does each request see?

Answer sketchThe first 10 take the 10 connections and wait the 5-second default ReadTimeout. Each then closes its connection and retries, because go-redis retries a read timeout up to MaxRetries, default 3. The other 40 wait for a free connection, for up to the default PoolTimeout of 6 seconds. A pool timeout is also retried in this version, so they try again rather than fail. When Redis answers at 8 seconds, the requests that hold a connection get their reply, and the others follow as connections free up. So most requests wait about 8 seconds or more and then succeed. A request with a context deadline leaves the pool queue or the retry loop at that deadline. Only ContextTimeoutEnabled lets the deadline also end a read in progress. This follows from the code and was not run.

Q9. A chat server has a 3-second garbage collection pause while 4 MB of messages per second arrive for its users. The default pub/sub buffer limit is in place. What does it lose, and what design gets those messages back?

Answer sketchIts output buffer passes 8 MB after 2 seconds and reaches 12 MB, below the 32 MB hard limit. The soft limit needs 60 seconds over 8 MB, so this pause alone does not get it disconnected. A longer stall, or more traffic, crosses 32 MB and Redis closes it, losing everything in the buffer and everything after it until it subscribes again. The fix is a log with IDs, such as a Redis Stream or a database table. Pub/sub then only wakes the server, and the server reads the gap on reconnect.

## Cheatsheet

Open the cheatsheet
THE PLATFORM
  ~34 services, several shared managed clusters, volatile-lru, RDB backups, no AOF
  6 jobs: cache, session, lock, idempotency, queue, rate limit
  4 go-redis major versions; house style cache-aside + delete-on-write + TTL

c1 CLIENT (go-redis)
  ReadTimeout unset   v6.15.9 and v9 to v9.21.0 = 3 s;  v9.22.0+ = 5 s
  ContextTimeoutEnabled  default false: ctx deadline does NOT reach the socket
  PoolTimeout         default ReadTimeout + 1 s
  retries             a read timeout is retried, MaxRetries default 3
  ctx without flag    checked only in the pool wait and before a retry
  after a timeout     close the connection (late reply still arrives)
  per-request conns   2.82 ms vs 0.21 ms pooled (AWS, same AZ, m6g.2xlarge)
  fail-open           add a circuit breaker, or every call waits ReadTimeout

c2 WHAT REDIS LOSES
  eviction   volatile-* evicts only keys with a TTL; none left = OOM on writes
  defaults   OSS noeviction; ElastiCache volatile-lru; Redis 8.6+ has 10 policies
  SET        plain SET drops the TTL; use KEEPTTL or EX; go-redis 0 = no TTL
  check      INFO keyspace: keys= vs expires=
  failover   async replication; WAIT is not CP; Jepsen kept 872 of 1,998 acked
  correctness  conditional write / fencing token at the durable store
  unlock     DELEX key IFEQ token (Redis 8.4+), DELIFEQ (Valkey 9.0+)
  rank       happened and can recur? -> cost of loss for the job -> cost of fix

c3 HIT RATE
  origin load = traffic x (1 - h);  change = (1 - h2) / (1 - h1)
  99% -> 0% = 100x   99.5% -> 98% = 4x   99% -> 98% = 2x
  miss that fans out = superlinear (Slack); load test with the cache off

c4 LAYERED CACHE
  staleness = TTL of every layer not invalidated (+ Redis TTL if delete lost)
  5 min L1 + 1 h Redis, delete lost = about 1 h 5 min
  race: reader misses, writer updates + deletes, reader stores old value
  fixes: version-checked write (Uber); purge Redis THEN publish (Stack Overflow)
  CLIENT TRACKING: placeholder before GET; flush local cache on disconnect

c5 PUB/SUB BETWEEN SERVERS
  at-most-once; disconnect = lost forever; PUBLISH returns receiver count
  client-output-buffer-limit pubsub 32mb 8mb 60 (Redis 8.10.2, Valkey 9.1.2)
  cluster: PUBLISH -> every node on the bus; SPUBLISH stays in one shard
  slot move: shard channel unsubscribed; subscribe again on the new owner
  expired events: late, and per node; not a presence timer
  recover: log first (Stream, DB, Kafka), pub/sub as wake-up, read gap by ID
  presence: heartbeat every d s; SET presence:user 1 EX d+e; check at d+2e
  watch: INFO stats client_output_buffer_limit_disconnections

## Sources

Open the sources

- go-redis debugging guide: a timed-out connection cannot be reused. The go-redis defaults come from its source at tags v6.15.9 to v9.23.0 and the v9.22.0 release notes.

- OpenAI, March 20 ChatGPT outage: a cancelled request left its reply on a pooled connection.

- AWS, Redis clients and ElastiCache: 2.82 ms against 0.21 ms, 65,000 connections, reconnect storms.

- bsport, Redis as a single point of failure: reconnects overloaded DNS, keys with no TTL, one cluster per domain.

- Shopify, circuit breaker tuning: 263% extra capacity down to 4%, a 50 ms half-open timeout.

- Shopify, inside the tech stack: one shared Redis took down all shards, and the fix was pods.

- Redis eviction: volatile-* acts like noeviction with no TTL keys, and the 10 policies.

- ElastiCache engine parameters: the default volatile-lru.

- AWS re:Post, OOM command not allowed: the error on a full ElastiCache node.

- Pendo status incident: two code paths wrote cache keys with no expiry.

- Trello tech stack: only losable data in Redis, allkeys-lru, pub/sub with a list and a counter.

- Trello, why we chose Kafka: the move off Redis pub/sub for WebSocket updates.

- Redis replication: WAIT does not make Redis CP.

- Jepsen: Redis: 1,998 writes acknowledged, 872 kept.

- Kleppmann, distributed locking: the fencing check with tokens 33 and 34.

- DynamoDB optimistic locking: a version attribute and a conditional write.

- Slack's incident on 2-22-22: misses that fanned out to every shard.

- Facebook, details on the outage: clients deleted the keys they could not refill.

- AWS Builders' Library, caching challenges: load test with caches disabled.

- Stack Overflow app caching: purge Redis, then publish, 86,982 commands per second, and the local cache TTL bug.

- Uber integrated cache: CDC invalidation, version-checked writes, 99.99% consistency, circuit breaker.

- Redis client-side caching: the placeholder rule and the flush on disconnect.

- Redis pub/sub: at-most-once delivery and sharded pub/sub. The keyspace notifications page gives the timing and cluster rules of expired events.

- Figma postmortem: pub/sub on a cluster-mode instance pinned CPU at 100%.

- GitLab production issue 706: replicas disconnected by the output buffer limit.

- Discourse message_bus: a backlog in Redis and reading the gap by message ID.

- Socket.IO Redis adapter and Redis Streams adapter: what each loses when Redis disconnects.

- Harness on Redis Streams: consumer groups and their three problems.

- Discord, indexing messages: a Redis queue that dropped messages under backlog.

- Slack, scaling the job queue: a full Redis could not dequeue.

- LinkedIn presence platform: heartbeats, d + ε expiry and the d + 2ε check.

- Redis developer docs and ElastiCache best practices: the phase's capstone reading, to reread with this review in mind. The phase also suggests chapter 1 of Kleppmann's Designing Data-Intensive Applications.
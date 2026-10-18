### What you must know

- If a double run wastes work, one Redis node is enough. If it corrupts data, the resource must refuse it.Decide which kind of lock you are writing, and where its guarantee lives.

- Release and extend must compare your own random token and act in one server-side step.Write an acquire, release and extend that never touch another holder's lock.

- Any pause longer than the TTL gives two acting holders, and no check inside the client closes that gap.Size a lease, add a watchdog, and know what neither one fixes.

- A lock on one Redis primary can vanish at failover, and its expiry follows the server's wall clock.Name the two server-side ways a correct client still gets two holders.

- A fencing token protects only if it never goes backwards and the resource checks it in the write.Design a fence, and pick a token source that survives a failover.

In Phase 2 you stopped a cache stampede inside one process with singleflight. singleflight lets one call fetch a value while the duplicate callers in the same process wait for its result. This lesson starts where singleflight stops working, because the duplicate callers now run on different machines.

The running case is a weekly summary job for an AI agent feature. It is this lesson's own example, not the settings cache of Phase 2. For each customer account, the job calls a paid LLM to summarise the week. Then it saves the summary row, emails the account owner, and deducts the AI credits that the call used. The job runs on three worker pods, A, B and C, and two pods can pick the same account. singleflight in pod A cannot see pod B, so the team adds one Redis lock per account, lock:summary:42 for account 42.

In this lesson's example, the LLM call usually takes 2 seconds and the lock's TTL is 10 seconds. These two numbers are an illustration, not a measurement. Each section asks what can still go wrong with that lock. Each answer moves the guarantee one step closer to the database row that holds the credits.

## What you bring from Phases 0 to 2

One thread runs every command, from Phase 0

Redis runs commands one at a time on one main thread. So one command, or one Lua script, is atomic: no other command runs in the middle of it. In Redis 8, I/O threads read, parse and write, but they never run commands.

TTL and expiry, from Phases 0 to 2

A TTL, time to live, tells Redis to treat a key as deleted after a set time. PX 10000 on a SET gives the key a TTL of 10,000 milliseconds. Phase 2 used TTLs to make cached values expire.

singleflight, from Phase 2

singleflight merges duplicate calls for the same key inside one process. The first caller does the work, and the others wait for its result. It knows nothing about other processes, so three pods still make three calls.

A lock across processes, new here

A distributed lock is a key in a shared store that only one process may hold at a time. Every pod tries to create the key, and only the pod that succeeds runs the job.

- pod picks account 42Pods A, B and C all can.

- take lock:summary:42Only one pod gets it.

- call the LLMAbout 2 seconds, and it costs money.

- save, email, deductThree effects outside Redis.

- release the lockThe next pod may now run.

This phase stays with one job and one lock. Phase 4 explains replication and failover in full. This lesson needs only one fact from it, in the failover section: a replica can miss the last writes of its primary.

## Is this lock about wasted work or about wrong data?

The cost of a double run decides which tool can protect the job.

The summary job has one lock, but that lock protects three different effects. If two pods both run account 42, the owner gets two emails and the company pays for two LLM calls. The credits are worse, because they are deducted twice and the customer loses money.

A lock can have two jobs. An efficiency lock stops the same work from running twice, and a rare double run only wastes time or money. A correctness lock must stop two actors from both acting, because a double run leaves wrong data behind. The code of the two locks is identical, so only the cost of a failure tells you which one you have.

- What breaks if two pods both run the job for account 42?

- only wasteEfficiency lock: one Redis node with SET NX PX is enough. Document that a rare double run can happen.

- wrong dataCorrectness lock: the resource itself must refuse the second actor. The lock stays only to save work.

Predict: the team moves the lock from Redis to etcd, a consensus store whose nodes agree on each write by majority vote. The lock is a 30-second lease, a lock that ends unless its holder renews it. Pod A pauses for 40 seconds in the middle of the job. Are the credits deducted once or twice?
They can be deducted twice. The lease ends at 30 seconds, so pod B acquires the lock and deducts the credits. Pod A then resumes at 40 seconds and does not know that its lease ended, so it deducts them again. The guess "once" is reasonable, because etcd is a correct store. But etcd keeps the lock record correct, and the deduction happens in a different system. What stops the second deduction is a check in the credits table, which the next section shows.

Any lock service faces the same choice when a holder stops answering, and the steps below show why.

- The service must free a lock when its holder looks dead, because a crashed holder would otherwise block every other pod forever.

- It decides that a holder looks dead when a lease runs out or a heartbeat stops arriving.

- A holder that is paused, or cut off by the network, looks dead in the same way. But it is still alive, and it can act when it resumes.

- So every lock that can recover from a crash can also have two holders for a while. This is true for Redis, etcd and ZooKeeper alike.

- The store can stay perfectly correct while the work under the lock goes wrong, because the work happens outside the store.

The failure looks like this in production. Both pods log "lock acquired", neither logs an error, and the credits table shows two deductions for one week. Nothing in Redis or etcd is wrong, so a dashboard of the lock store shows no fault.

etcd under Jepsen tests shows the failure with a number. The testers used etcd's own lock to protect updates to a set, and they paused the client processes on purpose. Leases expired during the pauses, and a bug also skipped the lease check after a client had waited for the lock. About 18% of acknowledged updates were lost, with 2-second lease TTLs, five processes, and a pause every five seconds. With 1 to 3 second TTLs, mutual exclusion usually failed within a few minutes of testing, even in healthy clusters. etcd fixed the bug, and the report's safe pattern checks the lock key's version inside the same write. That pattern is a check at the resource.

Evidence
Jepsen, "etcd 3.4.3", Kyle Kingsbury, published 2020-01-30. Conditions quoted in the report: "two-second leases TTLs, five concurrent processes, and process pauses every five seconds". Result: "we could reliably induce the loss of ~18% of acknowledged updates". The same report found etcd's key-value operations strict-serializable under the same faults. Its summary of the trade-off: "lock services must sacrifice correctness in order to preserve liveness in asynchronous systems". Read in the study note, which fetched the report.

Go deeper: the two kinds of lock in more detail, and the rest of the etcd result
The efficiency and correctness split comes from Martin Kleppmann's post on distributed locking. He describes an efficiency lock as one that "saves you from unnecessarily doing the same work twice". He advises you to document that single-node locks "are only approximate and may occasionally fail".

Efficiency lockCorrectness lock

Its promiseDo not do the same work twice.Two actors must never both act.

Cost of a double runA duplicate email, a wasted LLM call of about $0.02, a cache entry computed twice.Corrupted data, a customer charged twice, two conflicting writes to one record.

Enough protectionOne Redis node with SET NX PX.Redis alone is not enough. Use an idempotent write, a fencing token or a consensus system with fencing.

Many locks in a typical service are efficiency locks. Deduplicating notification emails, building a share link and starting a chat session are all cases where a rare double run is a nuisance. For those, a single Redis node is the right and cheap answer.

The etcd tests also matter for the claim "use a consensus store and the lock is safe". The store passed its own checks under the same faults, so the data in etcd was never wrong. The lock built on top still failed, because a lease is a promise about time, and a paused client cannot see time pass. The report's two fixes are a transaction that checks the lock key's version in the same write, or using the lock key's revision as a fencing token. Both put the check at the resource.

## Where does the guarantee live when a lock is not enough?

A correctness job needs a check at the resource, and the lock only saves work.

The last section showed that any lease-based lock can have two holders, so the credits need a guard outside the lock. There are three places to put that guard. Each one makes the resource, the system that holds the data, refuse the second actor.

GuardWhat refuses the second actorWhen it worksCost

Idempotent writeA unique key on the effect, such as one charge per account and weekThe resource can enforce a unique key or a conditional writeLow. It also covers retries and crashes.

Fencing tokenThe resource rejects a write whose token is lower than the highest it has acceptedThe resource can compare a number in the same step as the writeMedium. The token source must never go backwards.

Consensus lock plus fencingA consensus store, such as etcd or ZooKeeper, issues an ordered token, and the resource checks itYou need real mutual exclusion across machinesHigh. You run a consensus cluster, and the resource still checks.

Redis lock aloneNothing refuses a late actorOnly when a double run is harmlessLowest

An idempotent write is a write that leaves the same result when it runs twice. It is often the best guard, because it also protects against client retries and crashes, which a lock never sees. In the running case, the credits table gets a unique key on account and week. The second deduction then fails on that key, whichever pod sends it.

-- one charge per account and week, whichever pod gets here first
INSERT INTO credit_charges (account_id, week, credits)
VALUES (42, '2026-W42', 120)
ON CONFLICT (account_id, week) DO NOTHING;

With this row in place, the Redis lock no longer protects the credits. It only stops most duplicate LLM calls and emails, which is an efficiency job. The decision for any lock follows from that split.

- Efficiency lock. Use one Redis node with SET NX PX, a random token, and a compare-and-delete release. Do not add a multi-node algorithm, and document that a rare double run can happen.

- Correctness lock. Do not rely on any Redis lock as the guarantee. Make the write idempotent, or add a fencing token that the resource checks, or use a consensus store with fencing. Keep the Redis lock only as a way to save work.

Shopify shows what happens when the guard sits in a different store from the data. Inventory reservations lived in Redis as one counter per item, with DECR to reserve and INCR to release. The inventory ledger lived in MySQL, so the claim step could not be atomic across both stores, and that risked overselling. Shopify moved reservations into MySQL as one row per unit, claimed with SELECT FOR UPDATE SKIP LOCKED, up to 1,000 rows per item and location. On Black Friday 2025, Shopify merchants peaked at $5.1M in sales per minute. On the new MySQL design, the throughput limit turned out to be database connections, not CPU.

Evidence
Shopify Engineering, "We replaced Redis with MySQL for inventory reservations, and it scaled", Emilie Noel, 2026-05-12. The peak figure is for Black Friday 2025. Fetched for the course's company research, re-fetched once, and read again for this review on 2026-10-18, with matching facts.

Go deeper: the Redlock argument, and what both sides agree on
Redlock is an algorithm by antirez, the creator of Redis. It takes the same lock on N independent Redis primaries and counts the lock as held when a majority of them said yes. So the failure of one node does not lose the lock. Martin Kleppmann criticised it, and antirez answered. Their points are below.

Kleppmann's pointsantirez's answers

Redlock cannot give correctness. A pause past the lease gives two holders, so the resource needs fencing tokens. Redlock's random value cannot be put in order, so it cannot serve as one.A large random token plus a check-and-set on the resource gives the same protection as a number that only grows, and it is more practical.

Its safety depends on timing: a bounded pause, a bounded network delay and no clock jump. Real systems break all three.Redlock assumes only that each node can count time with a bounded error, such as 5 seconds with at most 10% error. He agreed that Redis should use a monotonic clock, which the failover section shows never happened for key expiry.

For correctness, use ZooKeeper or etcd with fencing. For efficiency, one Redis node is enough. He calls Redlock "neither fish nor fowl": too heavy for efficiency, not safe enough for correctness.Redlock moves people off locks on one primary with failover, which are less safe, at little cost. If the resource can resolve races itself, "it is not clear why you would use a lock with strong properties at all".

Both are right on their own terms. No lock that relies on a timeout can be correct against a pause of any length without fencing. And if the resource can check a token, you may not need a strong lock at all. So the decision above uses one Redis node for efficiency and puts correctness at the resource. A multi-node Redlock adds operations work and still gives no correctness without fencing.

The phase's line "if you need fencing, you probably didn't need the heavy lock" is a fair paraphrase of antirez, not his words. He says a strong lock is unclear when races can be resolved another way.

Go deeper: an idempotency key for a paid API call
A paid third-party call, such as an LLM request or a payment, cannot be fenced, because the provider does not check your tokens. The production design for that case is an idempotency-key row in your own database. Brandur Leach describes one for a Stripe-like API in Postgres. Each request carries a key, and the server keeps a row for that key with a locked_at time. The work runs in atomic phases, each one a database transaction, and each phase records a recovery point. A retry can take the key only when its lock is free or older than a lock timeout. A request that crashed then resumes from its last recovery point, on a client retry or through a completer process. A reaper process deletes old keys, after about 72 hours. So the row is a lease plus a record of progress, kept in the same database as the data.

The storage course, Phase 3, teaches the leased task claim and the version-column check in PostgreSQL. This lesson does not teach them again. A version column is the check-and-set that antirez describes: the UPDATE succeeds only if the version is still the one you read.

Before writing a lock, ask what a double run breaks.

An email lock and a money lock look identical in code, so the money one ships unguarded.

Pick one lock in your code and write down what breaks if two holders act.

The summary job now needs a correct efficiency lock, so the next section takes the acquire command apart.

## What does each part of SET NX PX protect against?

The acquire is one command, and each of its three parts stops one failure.

The summary lock is now an efficiency lock, so one Redis node is enough, but the lock still has to be written correctly. The acquire is a single SET command with three parts. Each part defends against one failure, and a lock that drops any part breaks in a specific way.

- SET lock:summary:42The key names what you lock.

- <random token>The value names this one holder.

- NXSet only if the key is absent.

- PX 10000The key expires after 10 seconds.

- OK or nilOK means this pod holds the lock.

Predict: a Go helper calls go-redis SetNX(ctx, key, "1", ttl), and one caller passes a ttl of 0 by mistake. That pod is then killed while it holds the lock. When does the lock free itself?
Never. In go-redis, an expiry of 0 means "no TTL", so the key is created with no expiry at all. Every later pod gets nil until someone deletes the key by hand. The guess "Redis rejects a TTL of 0" is reasonable, because a raw SET k v NX PX 0 does fail with "ERR invalid expire time". But the client library turns 0 into a command with no TTL before Redis sees it, so Redis has nothing to reject.

- NX gives mutual exclusion. The key is set only if it does not exist yet. One thread runs commands one at a time, so of many pods that send this command at once, exactly one gets OK and the rest get nil.

- PX frees the lock after a crash. Without a TTL, a holder that is OOM-killed, killed with kill -9 or cut off by the network holds the lock forever. With a TTL, the worst case is that other pods wait one TTL.

- The random token names the holder. It must be unique to this one acquisition: 16 or more random bytes from a secure random source, or a UUID. A constant such as "1" or "locked" works in a demo, but at release time it cannot tell your lock from the next holder's lock.

The TTL also sets a trap of its own. If the work takes longer than the TTL, the lock frees itself while you still work, which the lease sections cover. So the TTL is a real choice between fast recovery from a crash and safety for slow work.

Correction. The phase calls SETNX "a valid lock primitive". The SETNX command page says it is "regarded as deprecated" as of Redis 2.6.12. SETNX also cannot set a TTL in the same command, so a crash between SETNX and EXPIRE leaves a lock with no expiry. Use SET key token NX PX ttl, which is one atomic command.

The whole correct lock on one node is two calls: SET NX PX to acquire, and a release that deletes the key only if it still holds your token. The Go version is in the Go deeper block below.

The pods that lose must decide when to try again. The official Redis lock page asks for a random delay before a retry, so that losing clients do not all retry at the same moment. The Go library redsync uses 32 tries by default, with a random delay of 50 to 250 milliseconds between them.

Flipkart saw what unbounded waiting does to Redis itself. A service that feeds Flipkart's load tests used a lock from Redisson, a Java client. It was a read-write lock on one Redis primary, watched by three Sentinel processes for failover, and it guarded a MySQL calculation. In a peak load test, every request thread polled isLocked in a loop and then called lock with no wait limit. Redis CPU reached 100%, all threads blocked, and pods failed their health checks and restarted in a loop, while pod CPU stayed under 40%. The fix that held was a counter in each pod that let only 5 requests at a time try the lock. It answered HTTP 429 to the rest. The team sized it from the time a request spent inside that gate, 200 to 300 milliseconds, budgeted as 500 ms. That gave about 90 requests per second across 9 pods.

Evidence
Flipkart Tech blog, "When Good Locks Go Bad: Diagnosing a System Meltdown Under Load", Yash Agrawal, 2025-11-10. The course's company research read the full text from the blog's feed. This review fetched the feed again on 2026-10-18, got HTTP 200, and re-read the full text. Each Flipkart fact on this page matches it. The go-redis behaviour is from its source: at v9.5.1, SetNX with expiry 0 sends SETNX, and at v9.23.0 it sends SET k v NX. In both versions the key has no TTL. The "ERR invalid expire time" reply was run by the study note's author on Redis 8.10.1.

Go deeper: the whole lock in Go, token size, the go-redis versions, and watching the acquire
The acquire and the safe release in Go, from the phase:

// ACQUIRE
token := random16Bytes()
ok, _ := rdb.SetNX(ctx, key, token, ttl).Result()   // SET key token NX PX ttl
if !ok { /* someone else holds it */ }

// ... do the protected work (must finish well within ttl) ...

// RELEASE: atomic compare-and-delete (next section)
releaseScript.Run(ctx, rdb, []string{key}, token)    // DEL only if value == my token

- The official lock page assumes a token of "20 bytes from /dev/urandom". redsync uses 16 random bytes, encoded in base64, in v4.18.0. Both are large enough that two pods never pick the same value.

- The go-redis method name SetNX hides which command it sends. At v9.5.1, the version the lab pins, a non-zero expiry sends SET key value PX ms NX, or EX with seconds for a whole-second TTL, and 0 sends plain SETNX. At v9.23.0, 0 sends SET k v NX with no TTL. A helper that takes the TTL from its caller should refuse 0, or set a default.

- Other SET options include XX, which sets only if the key exists, and GET, which returns the old value. EX and PX take a TTL in seconds or milliseconds, EXAT and PXAT take an absolute time, and KEEPTTL keeps the old TTL. Since 8.4.0, IFEQ, IFNE, IFDEQ and IFDNE set the key only when a condition on its current value holds. A lock needs NX with PX or EX to acquire, and IFEQ to extend.

- Lab exercise E2 watches the acquire on the wire with MONITOR. The first SET ... NX returns OK and the second returns nil, because the key already exists.

- redsync's defaults, from redsync.go at v4.18.0, are an 8-second expiry, 32 tries, a random retry delay of 50 to 250 milliseconds, and a drift factor of 0.01. The lease sections use the drift factor.

- Flipkart's first gate was about 128 requests per pod, taken from Redis maxclients of 1,160 divided by 9 pods, and the service still collapsed. A connection limit says how many clients Redis accepts, not how many requests the locked section can serve well.

- Flipkart's lesson is general: a lock is also a queue of waiting callers. Bound the wait. Size the number of callers you let in from the time each one spends in the locked section, not from a connection limit.

The random token does nothing at acquire time, so the next section shows the release that needs it.

## Why does a plain DEL delete the next holder's lock?

After your TTL ends, the key you delete may belong to another pod.

The acquire is now correct, and the random token in it matters only at release. Suppose the summary lock used the constant value "1" and a plain DEL to release. The figure below uses a 2-second TTL and a job that takes 3 seconds, so the lease ends while pod A still works.

Plain DEL with value "1": the TTL is 2 s and pod A's work takes 3 s.

From t=0.0 s, pod A holds the lock and starts 3 seconds of work.

At t=2.0 s, the key expires. Pod A is still working and does not know.

Pod B's SET NX now succeeds, so pods A and B both work.

At t=3.0 s, pod A finishes and sends DEL. The value is "1" in both cases, so it deletes B's lock.

Pod C acquires the free key, so pods B and C both believe they hold the lock.

The timeline from the phase's E3 exercise. Times are the program's settings, not a measurement.

The cause is that a plain DEL cannot ask "is this still my lock?". It deletes whatever is there, and after a lease ends that is often the next holder's lock. So one lease overrun grows from two holders to three. The fix is the random token plus a compare-and-delete, a release that deletes the key only if its value is still your token.

The compare and the delete must run as one step on the server. If Go code sends a GET, compares, and then sends a DEL, the key can change between the two commands. Another pod can take the lock inside that gap, and your DEL then removes it.

Two calls from the client

v, _ := rdb.Get(ctx, key).Result()
if v == token {
    // lease can end here, and pod B can acquire
    rdb.Del(ctx, key)   // deletes B's lock
}

One step on the server

# Redis 8.4 and later
DELEX lock:summary:42 IFEQ <my-token>

# any version: one Lua script
EVAL "if redis.call('GET',KEYS[1]) == ARGV[1]
      then return redis.call('DEL',KEYS[1])
      else return 0 end" 1 lock:summary:42 <my-token>

A Lua script runs on the one command thread, so no other command runs between its GET and its DEL. Now pod A's late release at t=3.0 s finds B's token, returns 0 and deletes nothing. The same rule applies to extending a lease: set a new TTL only if the value is still your token, in one step. On Redis 8.4 and later that is SET lock:summary:42 <my-token> IFEQ <my-token> PX 10000, which does nothing when the key is gone or holds another token.

Correction. The phase gives only the Lua script for release, and says to extend by "re-PEXPIRE while you still own it". Since Redis 8.4.0, the official lock page gives DELEX key IFEQ token as the release step and keeps Lua for older versions. An extend must be a compare-and-extend, either SET key token IFEQ token PX ttl on 8.4 and later, or the Lua script above. A bare PEXPIRE can extend another pod's lock.

The return value of a release is also your cheapest alarm for a lease overrun. The table shows what each release returns in each case.

ReleaseKey holds my tokenKey holds another tokenKey is gone

DELEX key IFEQ token100

The phase's Lua script100

redsync's release script10-1, so Unlock returns ErrLockAlreadyExpired

A key that is gone at release time means the lease ended before you finished. redsync reports that case as its own error, so you can count it. DELEX returns 0 for both a foreign token and a missing key, so you lose this signal unless you keep a script that tells the two cases apart.

Compare-and-delete stops pod A from deleting pod B's lock. It does not stop A and B from working at the same time between t=2.0 s and t=3.0 s. That overlap is the subject of the next section.

Evidence
DELEX is "since 8.4.0" on its command page, and IFEQ on SET is "since 8.4.0" on the SET page, which says "If the key doesn't exist, it won't be created." The study note's author ran both on Redis 8.10.1: DELEX lock:y IFEQ wrongtoken returned 0 and DELEX lock:y IFEQ realowner returned 1. SET lock:z tokB IFEQ tokB PX 30000 returned nil while the value was tokA. On a missing key, SET ... IFEQ returned nil and created nothing. The redsync return values are from scripts.go and mutex.go at v4.18.0.

Go deeper: the extend script, Valkey's commands, and redsync's three scripts
Before Redis 8.4, extend with a script that compares first. This is redsync's touch script:

if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("PEXPIRE", KEYS[1], ARGV[2])
else
    return 0
end

- Valkey has no DELEX. It has DELIFEQ key value since 9.0.0, and SET ... IFEQ since 8.1.0. Code that must run on both Redis and Valkey needs the Lua script, or a branch for each server.

- Whether AWS ElastiCache, Google Memorystore and Azure support DELEX or SET IFEQ was not checked. Test it on your managed service before you remove the Lua script.

- redsync's release script is a GET, then DEL if the value matches, -1 if the key is gone, and 0 otherwise. Its touch script compares the value and then sends PEXPIRE. A third script, used with WithSetNXOnExtend(), recreates the key with SET ... NX when it is gone. The lease sections explain why that third script can hide a gap.

- A library's compare-and-delete stays safe even when your code ignores the error that Unlock returns. The library still refuses to delete a foreign lock. You only lose the signal that the lease ran out, which is a monitoring gap and not a safety gap.

- A Lua script blocks every other client while it runs. The release script is two commands on one key, so it costs about as much as two commands.

Release and extend compare my token and act in one server step.

GET then DEL from Go leaves a gap where another pod takes the lock.

Run E4, then repeat it with DELEX on Redis 8.4 or later, and compare both replies.

The release is safe now. But pods A and B still worked at the same time, so the next section asks what happens when the work outlives the lease.

## What happens when the work outlives the lease?

A correct lock still gives two holders when the holder stops longer than the TTL.

The last section ended with pods A and B working at the same time, even though both followed the rules. The lock in this section is fully correct, with a random token and a compare-and-delete release. It still fails, because a lock with a TTL is a lease: a promise that the key is yours until a deadline. You hold that promise only if your work finishes before the deadline, and the holder cannot see itself miss it.

A correct lock with a 5 s TTL, and a 6 s pause in pod A.

At t=0 s, pod A acquires with a 5-second TTL. Its work normally takes 2 seconds.

At t=1 s, a stop-the-world garbage collection pause freezes pod A for 6 seconds.

At t=5 s, A's lease expires while A is frozen. Pod B acquires the free key and starts its own work.

At t=7 s, pod A resumes as if nothing happened and writes. Pod B writes too, so both act on the resource.

The phase's own timeline. Illustration, not measured.

Predict: you add if time.Now().Before(lease.Until) { deductCredits() } right before the write. Can the deduction still land after the lease has ended? Name two ways.
Yes. First, the pause can start after the check returns true and before the write is sent. The check passed at a moment when the lease was valid, and the write left much later. Second, the write can be delayed after it leaves the pod, in a busy network or in a queue inside the database client. It then reaches the resource after the lease has ended, whatever the pod checked. The check looks like the last safe moment, so the guess "no" is reasonable. But there is always some time between any check and the write landing.

The mechanism is a gap between knowing and acting, in four steps.

- The pod learns that it holds the lock at time t0, when SET NX PX returns OK.

- The pod acts at a later time t1, when its write reaches the credits table.

- Anything between t0 and t1 can stretch with no fixed limit. Examples are a garbage collection pause, a page fault, CPU steal on a shared host, a slow disk, or a packet held in the network.

- If the stretch passes the TTL, another pod acquires at the deadline, and two holders act. No error appears anywhere, because each step worked as written.

Martin Kleppmann states the limit in one line. He writes that you cannot fix this "by inserting a check on the lock expiry just before writing back to storage". In the running case, the risky step is the LLM call. It usually takes 2 seconds, and this lesson assumes that one call in ten thousand takes 15 seconds, past the 10-second TTL. That number is an illustration, but the shape is general: a stall that is rare per call becomes routine at millions of calls a week.

GitHub saw this failure in many fileserver pairs at once, with a heartbeat timeout in the role of the lease. During a switch upgrade, traffic between access switches was blocked for about 90 seconds. The nodes in each fileserver pair exceeded their heartbeat timeouts, so each node decided that its partner was dead. Each node then sent STONITH, a command to cut power to its partner, and some of those commands never arrived. After the network recovered, both nodes in some pairs expected to be active for the same storage. The nodes then shut each other down, so both nodes of many pairs stopped. Recovery took over five hours. The problem was widespread, and for each pair the team had to find the node that was active last, mostly from logs.

Evidence
GitHub, "Downtime last Saturday", Mark Imbriaco, 2012-12-26, about the outage of 2012-12-22. Quotes: traffic was "blocked for roughly a minute and a half", the pairs "exceeded their heartbeat timeouts", and "both nodes expected to be active for the same resource". Recovery "took over five hours". Kleppmann's post uses this outage as its example of a long network delay. The quote on the expiry check is from that post.

Go deeper: garbage collection pauses in a real system, and why the gap scales with traffic
Kleppmann writes that "HBase used to have this problem". HBase is a database on the JVM, and stop-the-world garbage collection pauses there lasted "several minutes" while a process held a lease. The primary HBase source for this was not read: its blog link now redirects to an index page. So treat it as Kleppmann's report, not as a checked incident.

The gap does not need a bug in your code. A pause, a page fault, CPU steal on a shared host, a slow disk and a held packet all happen outside the program's logic. So the program cannot see one coming, and it cannot measure one that hits between its last check and its write.

The arithmetic is what turns a rare event into a routine one. If one call in 10,000 stalls past the TTL, as this lesson assumes, a job that runs 5 million times a week sees about 500 overlaps every week. This is an illustration, not a measurement.

The lock cannot close this gap, but it can make it smaller. The next section measures how far a longer TTL and a watchdog narrow it, and what each one costs.

## How far do a longer TTL and a watchdog narrow the gap?

Both make overlaps rarer, and neither makes them impossible.

The last section showed that any stall longer than the TTL gives two holders, so the next question is how much the lock itself can do. There are four answers, and only the last two remove the harm of an overlap.

- Size the TTL well above the slowest work. A longer TTL makes overruns rarer. But a pod that crashes then blocks every other pod for the whole TTL, so a short TTL recovers fast and a long one is safer for slow work.

- Add a watchdog, a background task that extends the lease while the work runs. Each extension must be a compare-and-extend, as the release section showed. The window becomes smaller, but the watchdog runs in the same process, so a process pause stops the watchdog too.

- Make the protected write idempotent. An overlap then leaves the same result as one run, which is why the credits table got its unique key.

- Add a fencing token at the resource. The resource then refuses the late writer, which the fencing sections cover.

A client library also shortens the lease it reports, to leave room for the time the acquire took. redsync computes how long the lock stays valid as the expiry, minus the time the acquire took, minus 1% of the expiry for clock drift. Move the sliders to see how much margin the summary job has.

How long redsync says the lock is valid, against the slowest work

Lock expiry, ms
Time the acquire took, ms
Slowest work you expect, ms
Valid for , margin , so

Formula from redsync v4.18.0 mutex.go. The work numbers are yours to choose, and the defaults are an illustration.

Real systems either narrow the window like this or say openly that they cannot close it. Kubernetes leader election, in the client-go library, uses a lease to pick one leader. Its source says it "does not guarantee that only one client is acting as a leader (a.k.a. fencing)". So Kubernetes leaves the fencing to the code that uses it.

In Go, you can tie the work to the lease. Give the work a context whose deadline is earlier than mutex.Until(), and check it before every side effect. A pod that misses the deadline then stops before it sends the email or the deduction. This practice is inferred and has no published source. It narrows the window without closing it, because the pause can still hit after the check.

The lock also needs its own metrics, so that overruns show up before customers see them. Track the time pods wait for the lock, the time they hold it, and the count of ErrLockAlreadyExpired at release. These metrics are inferred practice. The error itself exists, and a non-zero count means a lease ran out while a pod still worked.

A trap in redsync. With the option WithSetNXOnExtend(), an extend recreates the key with SET ... NX when it is gone. So "extend succeeded" does not prove that you held the lock with no gap. Another pod may have acquired, acted and released in between. This reading is inferred from the script.

Evidence
redsync v4.18.0: the validity formula is in mutex.go, lines 115 to 116, and the defaults are in redsync.go, lines 12 to 40. Redisson's watchdog default is lockWatchdogTimeout = 30 * 1000 in Config.java at tag redisson-4.8.0, line 82. Kubernetes client-go tools/leaderelection/leaderelection.go at tag v0.34.1, lines 19 to 20.

Go deeper: watchdog defaults, TTLs seen in one codebase, and the lab runs

- Redisson, the Java client, has a lock watchdog whose default timeout is 30 seconds. The watchdog runs inside the client process, so a pause of that process stops the extensions too. The lease then runs out like any other.

- redsync's Extend() runs the touch script on every pool and counts the lock as extended on a quorum. It then recomputes the validity with the same formula as the acquire. You call it yourself, for example from a goroutine on a timer shorter than the expiry.

- The shared platform of Phase 0 had lock TTLs from 500 milliseconds for a chat session start up to 180 seconds for a content sync. Every one assumed that the work finishes before the lease. The 500-millisecond lock guarded a session start that calls other services. One slow call to another service is enough to overrun it, so that lock gives less protection than its presence suggests.

- No TTL is safe against a pause of any length. A TTL only says how long a pause has to be before two holders appear.

- Lab exercises E5, E6 and E9 change the TTL and the work time. The lab notes explain that their program cannot show the overlap as written, and what to expect instead.

A lease only says how long a pause must last to give two holders.

A short TTL for fast crash recovery on an LLM call makes overruns routine.

Find your slowest locked job's p99, the time that 99% of runs finish within, and compare it with that lock's TTL.

Every failure so far needed a slow client, so the next section asks how the lock can vanish when no client paused at all.

## How can the lock vanish when no client paused?

Replication and the wall clock can both end a lease early, on the server.

Every failure so far needed a pod that was slow, and a faster pod or a longer TTL made it rarer. This section shows two failures that happen inside Redis, so a perfect client cannot prevent them. The summary lock now lives on a primary with one replica and automatic failover.

Predict: no pod pauses, and every pod uses the correct lock from the release section. Name the sequence that gives two holders of lock:summary:42. Then say what changes if pod A runs WAIT 1 100 right after it acquires.
Pod A acquires on the primary. The primary crashes before it sends that write to the replica. The replica is promoted and has no lock key, so pod B's SET NX succeeds, and both pods hold the lock. WAIT 1 100 blocks pod A for up to 100 milliseconds until one replica confirms the write. A reply of 1 makes this loss less likely, and a reply of 0 tells A that its lock is at risk. It does not make the failover safe, which is inferred: WAIT only reports how many replicas acknowledged, and with several replicas, the promoted one can still be one that did not. The guess "a correct client is enough" is reasonable, because every step of the client was correct.

- Pod A: SET lock:summary:42 tokA NX PX 10000The primary answers OK, and pod A starts the job.

- The primary crashesReplication is asynchronous, so the replica never got the lock key.

- The replica is promotedIt becomes the new primary, without the key.

- Pod B: SET ... NX succeedsPods A and B both hold the lock, and neither paused.

The official Redis lock page lists this race and calls it a "SAFETY VIOLATION". The window is the time between the primary's reply and the replica receiving the write. Phase 4 explains that window and the failover sequence. For a lock, what matters is that any write in that window can disappear, and the lock key is a write like any other.

The second failure is in how Redis decides that a key has expired. It uses the wall clock, the system time that an administrator or a time daemon can step forward or back. The steps below follow the Redis 8.10.2 source.

- SET ... PX 10000 turns the TTL into an absolute time: the current time in milliseconds plus 10,000.

- Redis sends the command to replicas and to the append-only file as SET key value PXAT <absolute-ms>, so they keep the same absolute deadline.

- When a command touches the key, Redis compares that deadline with its current time, which comes from gettimeofday, the wall clock.

- So if the server's clock steps forward by 5 seconds, every lease on that server ends 5 seconds early.

- A promoted replica checks the old primary's deadline against its own clock, so clock skew between the two machines moves every lease at failover. This step is inferred from the code paths above.

Correction. The phase says antirez "conceded" the monotonic clock, which reads as if Redis now uses one. It does not. The current official lock page says that "Redis is not using monotonic clock for TTL expiration mechanism". The Redis 8.10.2 source and the Valkey 9.1.2 source both decide expiry from the wall clock.

Redlock is antirez's algorithm that takes the same lock on several independent Redis primaries and needs a majority of them. A Redlock library does not protect against either failure when it talks to one endpoint. redsync computes its quorum as half the number of Redis pools plus one, and with one pool the quorum is 1. So the library gives single-node behaviour, with a safe compare-and-delete and a nicer API. The phase's former employer ran its Redlock-library locks this way, against one managed Redis cluster. All its locks therefore lived on the same primaries, so one failover could affect all of them at once.

Evidence
The four-step race and the monotonic-clock warning are on the redis.io page "Distributed Locks with Redis". Source at Redis tag 8.10.2: *milliseconds += commandTimeSnapshot() in t_string.c, line 259, and the PXAT rewrite in t_string.c, lines 194 to 205. keyIsExpired compares with commandTimeSnapshot() in db.c, line 2946, and that time comes from ustime(), which calls gettimeofday, in server.c, lines 242 to 249. Valkey 9.1.2: src/util.c, lines 1601 to 1621. The redsync quorum is in redsync.go, line 40, at v4.18.0. antirez wrote "I'll implement this in the next weeks" in his 2016 post.

Go deeper: Valkey's clock, WAIT and WAITAOF, and when an expired key frees the lock

- Valkey's ustime() adds a monotonic delta for at most 1 millisecond, and then calls gettimeofday again. So Valkey expiry still follows the wall clock.

- WAIT n timeout blocks the client until n replicas acknowledge its write offset. Replicas send that acknowledgement once a second, and a waiting WAIT also asks for one in the same event-loop turn. WAIT does not make the write durable, because it only reports how many replicas received it.

- WAITAOF numlocal numreplicas timeout, since Redis 7.2.0, waits until the write is fsynced to the append-only file on the primary and on replicas. It makes a loss less likely too. Whether it makes a lock safe at failover was not tested, and the reasoning above says it does not.

- Expiry has two paths. Each access to a key checks its deadline, and a background cycle samples keys with a TTL. On a primary, an access after the deadline deletes the key at once. So a SET NX sent right after a lease ends succeeds even if the background cycle has not reached the key yet. This last point is inferred from the access path.

- On a replica, an expired key reads as missing, but the replica waits for the primary's delete before it frees the memory.

- Real Redlock uses N independent primaries with no replication between them. A lock is held when a majority accepted it within the validity time. So losing one primary does not lose the lock. Kleppmann's point is that a clock step on some of the primaries still can.

A lock on a primary with a replica can vanish at failover.

Trusting a TTL across a failover or a clock step, because the client code was correct.

Ask your Redis host whether failover is automatic, and how much write loss it allows.

A paused pod and a failover both leave a late writer behind, so the next section moves the check to where the write lands.

## What must the resource check before it accepts a write?

The resource, not the lock, refuses the late writer, in the same step as the write.

A paused pod and a failover both leave a late writer that believes it holds the lock, so the check has to sit where the write lands. A fencing token is a number that grows each time the lock is granted. The holder sends its token with every write. The resource rejects any write whose token is lower than the highest token it has already accepted.

- A acquires, token 33Then a pause stops A, and its lease ends.

- B acquires, token 34B writes with 34.

- resource: 34 > 33 seenAccept, and remember 34.

- A wakes, writes with 33A still believes it holds the lock.

- resource: 33 < 34Reject. The late writer is fenced off.

Predict: the summary service checks the token in Go. It reads the highest token from the row, compares, and then sends the UPDATE as a second statement. Pod B holds token 34 and pod A holds the old token 33. Is A's write always rejected?
No. Suppose A reads the row first and sees 32, so its check passes. Then B reads 32, passes, and writes 34. Then A's UPDATE lands with 33 and overwrites B's summary. Each check was correct at the moment it ran, so the guess "always rejected" is reasonable. But the row changed between A's check and A's write, which is the same gap as a GET followed by a DEL. The check and the write must be one atomic step at the resource.

A fence protects only when two conditions hold.

- The issuer never goes backwards. It never hands out the same number twice, or a lower one, even across a crash or a failover. The next section shows why one Redis counter can break this.

- The resource checks and writes in one atomic step. In SQL that is one conditional UPDATE, or a transaction that compares a version.

-- one statement: the compare and the write cannot be separated
UPDATE account_summaries
SET    body = :body, fence = :token
WHERE  account_id = 42 AND fence < :token;
-- 0 rows updated: a newer holder already wrote, so stop and do not email

The check is easy when the resource is a row you control. It is hard when the resource is a third-party API, which does not know your tokens, and it is impossible for a physical action. An object store with no conditional write cannot compare a token either. For those resources, the guard moves to a row you control, such as the idempotency key from the second section.

A token that nobody checks does nothing. A team can add INCR on acquire, pass the number through every call, log it, and still accept every write. Lab exercise E8 shows the result: with no check, the stale writer's data is what remains.

antirez makes one more point about this check. If the resource can already refuse an out-of-date write, you may not need a strong lock at all. A version column does the same job: the UPDATE succeeds only if the version is still the one you read, and it adds one to the version. For the summary row, the version check and the fence are the same SQL with a different number in it.

Evidence
The fencing idea, the 33 and 34 example, and the advice to check at the storage are from Martin Kleppmann's post "How to do distributed locking". The point that a lock with strong properties is unclear when races are resolved another way is from antirez, "Is Redlock safe?". Chubby, Google's lock service, calls its tokens "sequencers", as the Jepsen etcd report notes.

Go deeper: fencing an object store write, and the lab's fencing program
Suppose the job also writes a PDF of the summary to an object store such as S3. The store cannot compare your token, so one design is to make the object key unique per token, for example summaries/42/34.pdf. The writer uploads the object first, and then runs the conditional UPDATE that points the row at that object. A late writer's upload then lands under its own key, and its UPDATE matches 0 rows, so no reader ever sees its file. Old objects can be removed later. This design is a sketch for this lesson, not a published one.

The lab program fencing_tokens deletes its counter and then calls INCR, so it prints tokens 1 and 2, not the 34 and 33 that the phase text says. It never takes a lock, and it shows only the resource's check. Its token comes from a separate INCR, not from the acquire itself, which is a gap the next section explains.

The resource's check is only as good as the numbers it compares, so the next section asks where the fencing token should come from.

## Where should the fencing token come from?

A token that can repeat after a failover lets two writers pass the same check.

The resource now rejects a lower token in one atomic step, so everything depends on the issuer never going backwards. The obvious issuer is a Redis counter: INCR fence:summary:42 on every acquire. That counter lives on the same kind of primary as the lock, and the failover section showed that a primary can lose its last writes.

- Pod A acquires and runs INCR. The primary answers 34.

- The primary crashes before the increment reaches the replica.

- The replica is promoted with the counter still at 33.

- Pod B acquires, runs INCR, and also gets 34.

- A resource that rejects only lower tokens accepts both writes, because 34 is not lower than 34.

- The SQL check above, fence < :token, refuses an equal token, so it accepts only the first write with 34. It cannot tell which writer is newer, so the stale pod A can be the one that wins.

This sequence is inferred from asynchronous replication, and no published incident of it was found. Kleppmann states the conclusion directly. He writes that "simply keeping a counter on one Redis node would not be sufficient, because that node may fail". He adds that you would likely "need a consensus algorithm just to generate the fencing tokens".

Correction. The phase says "In Redis that's trivial: INCR a counter on acquire". A counter on one Redis primary can repeat a token after a failover, so it does not meet the first condition of a fence. Take the token from a source that never goes backwards, or use the resource's own version.

There is a second gap even with no failover. If the token comes from a separate INCR after SET NX, pod A can acquire first and still receive a later token than pod B. Issue the lock and the token in one script, or use the resource's own version column. Both points are inferred from the order of the two commands.

Systems that fence in production take their tokens from a source that is ordered by design.

SystemTokenWho checks it

Kafka transactional producerAn epoch that grows each time a new instance starts with the same transactional.idThe broker rejects a producer with an older epoch

etcdThe revision of the lock key, ordered across the whole clusterA transaction that compares the lock key in the same write

ZooKeeperThe zxid, or the znode versionThe resource, which compares it

ChubbyA "sequencer" handed out with the lockThe server that receives the request

Hazelcast FencedLockA number that only grows, issued through Raft, a consensus algorithmThe caller passes it to the resource

A Redis INCR on one primaryCan repeat after a failoverWhatever resource you add

Kafka uses its epoch to stop "zombie" producers, ones that are paused or cut off but still alive after a replacement has started. The new instance raises the epoch, and the broker, which is the resource, refuses every write that carries an older one.

For the summary job, the clean answer avoids a separate token. The credits row has its unique key, and the summary row has a version column, so both checks come from the database that holds the data.

Evidence
Kleppmann's quotes are from "How to do distributed locking". The Kafka epoch quotes are from Confluent's "Transactions in Apache Kafka": a new instance "increments an epoch", and producers "with same transactional.id and an older epoch are considered zombies and are fenced off". The etcd revision as a "globally ordered fencing token" is from the Jepsen etcd 3.4.3 report. Hazelcast's post of 2019-04-03 by Ensar Basri Kahveci describes FencedLock. Jepsen's Hazelcast 3.8.3 report of 2017 found that its earlier locks "aren't exclusive" under partitions.

Go deeper: Hazelcast's path to fenced locks, and one script for lock and token
Hazelcast first shipped locks that were not safe under a network split. Jepsen's tests found that its locks were not exclusive under partitions, because a split cluster ran as two clusters and each one granted the lock. Hazelcast then built FencedLock on the Raft consensus algorithm, with sessions and tokens that only grow, and tested it with Jepsen. The name comes from Kleppmann's post. Neither page gives incident numbers.

If you must take a token from Redis, issue it in the same script as the lock, so the order of tokens matches the order of grants. The sketch below was not run. It still repeats a token after a failover, so it closes only the second gap.

-- KEYS[1] = lock key, KEYS[2] = fence counter, ARGV[1] = token, ARGV[2] = ttl ms
if redis.call("SET", KEYS[1], ARGV[1], "NX", "PX", ARGV[2]) then
    return redis.call("INCR", KEYS[2])
end
return 0

In Redis Cluster both keys must be in the same hash slot, for example {summary:42}:lock and {summary:42}:fence.

A fence needs a token that never repeats and a check inside the write.

Taking tokens from INCR on one primary, which can repeat a token after failover.

Run E7, then reset the counter to stand in for a failover, and run it again.

You now have every way a lock can fail, so the last teaching section turns them into an audit you can run on any lock.

## How do you audit a lock you find in a codebase?

Eight questions find each failure in this lesson, and the first decides how much the rest matter.

The sections above gave one failure each, so any lock can now be read against all of them. The phase came with an audit of a real codebase. It was the same platform, with eight Redis locks in Go services, all on one managed Redis cluster.

- Four locks used a Redlock library against one endpoint, so their quorum was 1 and they behaved as single-node locks. The library's compare-and-delete made their release safe.

- Four were written by hand with SETNX and a plain DEL, and their values were constants: "1", "locked" and "100". All four can delete the next holder's lock after an overrun.

- TTLs ran from 500 milliseconds to 180 seconds. One helper took its TTL from the caller with no default, so a caller passing 0 got a lock that never expires.

- No lock used a fencing token.

The audit's verdict came from the first question. Every lock guarded a job whose double run is a nuisance, such as a duplicate invitation email or a second share link. So the gaps were real but tolerable. The risk is the day someone copies one of these locks to guard money, because "we already do it this way".

#Ask about each lockA bad answerSection

1What breaks if two holders act?Money, a ledger, or a write that cannot be undonewasted work or wrong data

2Is the value a random token?"1", "locked", a hostname, or a constantSET NX PX

3Is the release a compare-and-delete in one step?A plain DEL, or a GET then DEL from the clientplain DEL

4Is the TTL above the p99 of the work, with margin?A sub-second TTL on a call to another service or to an LLMlonger TTL and watchdog

5Can a caller pass a TTL of 0?Yes, and the client library turns 0 into no expirySET NX PX

6Is the unlock error checked and counted?defer drops ErrLockAlreadyExpiredplain DEL

7Is there a fencing token or an idempotent write at the resource?No, and question 1 said moneywhere the guarantee lives, fencing

8Does the lock live on a primary that can fail over?Yes, and question 1 said moneyfailover

Two lessons from that audit apply to any codebase. A library's compare-and-delete stays safe when the caller drops the unlock error, because the library still refuses to delete a foreign lock. Dropping the error only hides the lease-overrun signal, which is a monitoring gap and not a safety gap.

The second lesson is a comment found next to a removed lock: "we do not need to take a lock here, since redis is always atomic". That comment is half right. One Redis command is atomic, as Phase 0 showed. A read-modify-write across several commands is not, so another client can run between them. When the resource is Redis itself, the fix is not a lock. Put the commands in one Lua script, or use WATCH with MULTI and EXEC, which aborts the transaction if a watched key changed.

Evidence
The eight locks come from the phase's audit of the former employer's private code, so no row can be checked from outside. The "TTL 0 means no expiry" part holds for go-redis at v9.5.1 and v9.23.0, from its string_commands.go.

Go deeper: the eight locks one by one, in general terms

What the lock guardedBuilt withTTLReleaseOwner check

A content sync jobRedlock library180 sLibrary unlock, error dropped by a deferYes, random token

Search indexing of one resourceRedlock library, 1 try2 minLibrary unlock, error only loggedYes. The log line could panic on a nil error.

A folder uploadRedlock library, 1 try2 sLibrary unlock, error only loggedYes

A resumable file uploadRedlock library, 1 try20 sLibrary unlock, error returned and checkedYes, the cleanest of the eight

Invitation email dedupSETNX, retried until a deadline60 sPlain DEL by the callerNone, value "1"

Chat session startSETNX500 ms, set by the callerPlain DELNone

Public share-link creationSETNX10 sPlain DELNone, value "locked"

A trending counterSETNX, call sites removed20 sPlain DELNone, value "100"

- The email-dedup lock had no unlock function. Its comment told callers to delete the key themselves, so every caller wrote its own plain DEL.

- The trending-counter lock was one line from correct. Its acquire stored a value token, but its release never compared that token before deleting.

- The search lock's release logged the error when the unlock returned false. If the unlock returned false with a nil error, the log line read the nil error and panicked. Error-handling code needs the same tests as the main path.

- The chat-session lock had both problems from this lesson's lease sections: a 500 ms TTL on work that calls other services, and a caller-supplied TTL with no default. A double session is still only a nuisance, but this lock was the closest to causing real harm.

- The library locks were all created against one cluster endpoint, so a failover of that one primary affected every one of them at once.

That audit closes the teaching sections, and the next section collects what you can now do.

## What you can do now, and what comes next

c1 to c5 below are the five ideas of "What you must know", in the same order.

- c1. A double run that only wastes work needs one Redis node. A double run that corrupts data needs a check at the resource, and the lock then only saves work. Taught in "Is this lock about wasted work or about wrong data?" and "Where does the guarantee live when a lock is not enough?".

- c2. The acquire is SET key token NX PX ttl with a random token. Release and extend compare that token and act in one step on the server, with DELEX, SET IFEQ or a Lua script. Taught in the two sections on SET NX PX and on plain DEL.

- c3. A pause longer than the TTL gives two acting holders. A longer TTL, a watchdog and a deadline in the work make it rarer, and only an idempotent write or a fence removes the harm. Taught in the two lease sections.

- c4. A lock on a primary with a replica can vanish at failover, and expiry follows the wall clock. A Redlock library on one endpoint is a single-node lock. Taught in "How can the lock vanish when no client paused?".

- c5. A fencing token works only if it never repeats and the resource checks it inside the write. One Redis counter can repeat after failover. Taught in the two fencing sections.

You can now read any lock, say what it protects and what it does not, and choose where its guarantee must live. You saw that a lock key can disappear when a primary fails before its replica has the write. Phase 4 answers how large that window is: how replication works, how much data a failover can lose, and how long the failover takes.

## Lab: the exercises that teach Phase 3

Open the lab: E1 to E12, copied from the phase, not run for this lesson
The lab below is copied from the phase. The only change is that the former employer's service names are replaced with what each service did. This lesson's author ran none of it. Where the study note or the earlier audit found a problem, a note under the exercise says what is wrong and what to expect instead.

What each exercise proves. E1 to E4 prove the acquire and the compare-and-delete release. E5, E6, E9 and E12 are about the lease. E7 and E8 are about fencing. E10 builds a lock with retries by hand, and E11 shows a read-modify-write that needs one atomic step.

Setup:

cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d && docker exec redis-study redis-cli PING   # → PONG

Lab note. The code is at /Users/raghvendra.dhakar/Desktop/project/code/study-material/redis/code, not at the path above. Its docker-compose.yml pins redis:7.2, and DELEX and SET IFEQ need Redis 8.4 or later, so pin an 8.x image. The current release is 8.10.2. The Go programs accept -addr and use port 6379 by default, so a local redis-server works without Docker.

-  E1. The correct lock.

- Run: go run ./phase03_locking/safe_lock

- Expected: A acquires, B denied while A holds, A releases, A's stale token can't release B's later lock.

- Teaches: SET NX PX + random token + Lua CAS unlock, end to end.

Lab note: the study note ran this program and saw the expected result. Add a DELEX version on Redis 8.4 or later, and print the 0 it returns for a missing key.

-  E2. Watch the acquire on the wire.

- Run: docker exec -it redis-study redis-cli MONITOR in one terminal; in another docker exec redis-study redis-cli SET lock:x tokenA NX PX 30000 then again with tokenB.

- Expected: first returns OK, second returns nil (key exists).

- Teaches: NX is the mutual exclusion; the single thread makes it atomic.

Lab note: not run, because it needs Docker as written. Without Docker, run the same commands with redis-cli directly.

-  E3. (Break it) The plain-DEL unlock bug.

- Run: go run ./phase03_locking/unsafe_unlock

- Expected: A's lock expires mid-work, B acquires, A's DEL deletes B's lock, C acquires → B+C both hold.

- Teaches: the exact email-dedup and share-link lock failure mode. This is why value must be random + CAS unlock.

Lab note: the study note ran it, and it printed that A deleted B's lock and that B and C both believe they hold it. The program's comments name the former employer.

-  E4. Prove the Lua CAS unlock refuses a stale release.

- Run: docker exec redis-study redis-cli SET lock:y realowner PX 30000, then run the release script with the WRONG token: docker exec redis-study redis-cli EVAL 'if redis.call("GET",KEYS[1])==ARGV[1] then return redis.call("DEL",KEYS[1]) else return 0 end' 1 lock:y wrongtoken (→ 0, not deleted), then with realowner (→ 1).

- Teaches: compare-and-delete only deletes when you still own it.

Lab note: on Redis 8.4 or later, also run DELEX lock:y IFEQ wrongtoken and DELEX lock:y IFEQ realowner. The study note saw 0 and then 1 on Redis 8.10.1.

-  E5. (Break it) Lease overrun → two holders.

- Run: go run ./phase03_locking/lease_expiry_race -ttl 500ms -work 900ms

- Expected: counter==2, invariant broken, "❌ BROKEN".

- Teaches: a perfect lock still fails if work > TTL. The Redlock-debate crux.

Lab note: this program has a bug, found by reading its code. This lesson reports no run of it. lease_expiry_race/main.go, lines 54 to 87, counts increments, and each of its two workers always increments once. So the final counter is 2 for every flag value, even when the two leases never overlap, and it prints BROKEN every time. Expect counter == 2 here, but it does not prove an overlap. To see real overlap, count the holders inside the critical section with an atomic counter and print the maximum.

-  E6. Tune the lease to fix (and then break) it.

- Run: -ttl 2s -work 900ms (safe: counter==1), then -ttl 2s -work 3s (broken again).

- Teaches: TTL sizing is a bet on worst-case work; there's no value that's safe against an unbounded pause.

Lab note: with the bug from E5, the "safe" run also prints counter == 2 and BROKEN. With -ttl 2s -work 900ms, the code has worker 1 hold from 0 to 900 ms and worker 2 from about 900 ms to 1.8 s, so there is no overlap. These times are read from the code, not measured. Only the fixed program shows the difference between the two runs.

-  E7. Fencing tokens save the day.

- Run: go run ./phase03_locking/fencing_tokens

- Expected: token 34 accepted, stale token 33 rejected.

- Teaches: only the resource-enforced token prevents the lease-overrun double-act.

Lab note: the program deletes its counter first, so it hands out tokens 1 and 2, not 33 and 34. Its code, fencing_tokens/main.go, lines 55 to 72, shows this. The stale write is still rejected. The program never takes a lock, and it calls only INCR. Add a step that resets the counter, to stand in for a failover, and watch a "reject if lower" check accept a repeated token.

-  E8. Fencing without enforcement is theater.

- Reason about it: modify fencing_tokens so the resource does NOT check the token (accept all writes). What's the final value? (A's stale "A's STALE data" wins — the token did nothing.)

- Teaches: the token is worthless unless the resource rejects stale ones.

-  E9. Simulate the chat-session lock's 500ms TTL.

- Run: go run ./phase03_locking/lease_expiry_race -ttl 500ms -work 700ms

- Expected: broken (counter==2) — a 700ms init (one slow gRPC) overruns a 500ms lease.

- Teaches: why a sub-second TTL on variable-latency work is fragile.

Lab note: the same bug as E5 applies, so counter == 2 appears whatever the overlap. From the code's timings, the leases do overlap here, but the output does not prove it.

-  E10. Build the redsync-equivalent by hand.

- Write a tiny Go loop that acquires with SetNX(key, uuid, ttl), retries with backoff on failure (like the trending-counter lock's [1,2,5,10]s jittered backoff), and releases with the Lua CAS. Compare your version to safe_lock.

- Teaches: what redsync does for you, and the retry/backoff dimension.

Lab note: the backoff above copies a private codebase. Use redsync's public defaults instead: up to 32 tries with a random delay of 50 to 250 milliseconds. Also reject a ttl of 0.

-  E11. (Break it) Read-modify-write without a lock.

- Run: 50 concurrent GET counter; increment in your shell; SET counter (the WRONG way) vs 50 INCR counter (right).

- Expected: the GET/SET version loses updates; INCR is exact.

- Teaches: the trending-counter service's "redis is always atomic" comment is only true for single ops, not read-modify-write — sometimes you DO need the lock (or a Lua script).

Lab note: not runnable as written, because it gives no script. Write a small Go program with 50 goroutines for each way. When the resource is Redis itself, the answer is a Lua script or WATCH with MULTI, not a lock.

-  E12. Inspect a live lock's TTL.

- Run: docker exec redis-study redis-cli SET lock:demo tok PX 30000; docker exec redis-study redis-cli PTTL lock:demo repeatedly.

- Expected: PTTL counts down; at 0 the key vanishes (auto-expiry).

- Teaches: the lease is real and observable; PTTL is your debugging tool for "who holds it and for how long."

Lab note: not run, because it needs Docker as written. Run the same two commands with redis-cli directly.

## Checkpoint questions

Open the checkpoint: seven questions, each with an answer sketch
The phase's questions used the former employer's services. They are rewritten here around general jobs, and each keeps its mechanism.

Q1. Say "efficiency" or "correctness" for each lock, and whether SETNX plus a plain DEL is adequate. (a) Deduplicating invitation emails. (b) Charging a subscription exactly once. (c) Preventing a duplicate chat session. (d) Decrementing a ledger balance once.

Answer sketch
(a) Efficiency, since a double email is a nuisance. The pattern is tolerable, though a random token and a compare-and-delete cost nothing. (b) Correctness. No Redis lock is the guarantee. Use an idempotency key with the payment provider and a unique charge row in your database. (c) Efficiency, but watch for a TTL shorter than the session start. (d) Correctness. Use a conditional UPDATE or a version check in the ledger's own database. Only (a) and (c) could use the existing pattern, and (b) and (d) must not.

Q2. A lock is SetNX(key, "1", 60s) with defer Delete(key). Give a timeline in which worker A deletes worker B's lock. Why does a random UUID plus a compare-and-delete fix this bug, and which deeper bug does it not fix?

Answer sketch
A acquires at t=0 s, and its work stalls until t=70 s. The key expires at t=60 s, and B acquires at t=61 s. A finishes at t=70 s, and its deferred Delete removes B's key. C acquires at t=71 s, so B and C overlap. With a random token, A's release finds B's token and deletes nothing. A and B still both worked between t=61 s and t=70 s, which is the lease problem, and only an idempotent write or a fence fixes it.

Q3. A session-start lock has a TTL of 500 ms. The session start makes a gRPC call that normally takes 80 ms but sometimes takes 1.2 s under load. Show the 1.2 s case. Can two session starts run at once? Propose two fixes and say which you would ship.

Answer sketch
Flow 1 acquires at 0 ms, and the lock expires at 500 ms. Flow 2 acquires at, say, 600 ms, so the two flows run at once from 600 ms to 1,200 ms. If the release is a plain DEL, flow 1 then deletes flow 2's lock at 1,200 ms. Fix one: a TTL well above the p99 of the call, such as 5 s, with a watchdog. Fix two: make session creation idempotent with a unique key on user and feature. Ship both, and treat the unique key as the guarantee and the lock as a saving.

Q4. Explain the Redlock argument in four sentences: what Kleppmann claims, what antirez replies, why both are right, and what you do for an efficiency lock and a correctness lock. Then say what a Redlock library gives you when it talks to one Redis endpoint.

Answer sketch
Kleppmann says no lease-based lock is correct against long pauses without fencing, and that Redlock leans on timing assumptions. antirez says a random token with check-and-set at the resource is enough, and that a resource able to resolve races needs no strong lock. Both are right, so you use one Redis node for efficiency and a check at the resource for correctness. On one endpoint the library's quorum is 1, so you get single-node SET NX PX with a safe release. You do not get tolerance of node failures, and the lock can still vanish at failover.

Q5. Design a fencing scheme for "generate exactly one invoice PDF per order", where the PDF goes to S3. Give the acquire with its token, the write with its token, and what the resource must do to reject a stale writer. Then explain why, following antirez, you might not need the distributed lock at all.

Answer sketch
Take the token from the order's database row, for example by adding one to an invoice_fence column and reading it back, because that source does not go backwards. Optionally take a Redis lock to save work. Upload the PDF under a key that includes the token, such as invoices/42/7.pdf. Then run UPDATE invoices SET object_key = :k, fence = :t WHERE order_id = :o AND fence < :t, and treat 0 rows as "a newer writer won". S3 cannot do the check, so the metadata row is the resource. The row already refuses stale writers with its own version, so the lock only saves duplicate rendering work.

Q6. A comment says "we do not need a lock, since redis is always atomic". Use the trending design from Phase 1. It records a view as LPOP the oldest view, ZINCRBY to decrement its item, RPUSH the new view, and ZINCRBY to increment its item. Give one operation where the comment is correct and one where it is wrong. Is that safe without a lock, and what would make it safe?

Answer sketch
Correct: one ZINCRBY or one INCR is atomic. Wrong: the four-command view update, because another client's commands can run between any two of them. Two views can then pop and decrement in an order that leaves the counts wrong. Make the four commands one Lua script, because the decrement needs the value that LPOP returned, which MULTI cannot pass along. WATCH with a retry also works. A distributed lock is the wrong tool, because Redis is the resource.

Q7. A code review adds a SETNX plus plain DEL lock, copied from an email-dedup helper. The lock guards a flow that decrements a customer's remaining AI credits and calls a paid third-party API. Write the review comment: what is wrong, the risk in concrete terms, and three changes you require, in order of importance.

Answer sketch
What is wrong: an efficiency-lock pattern now guards a correctness job, with a constant value, a plain DEL and no check at the resource. The risk: one stall past the TTL deducts the customer's credits twice and bills the provider twice, and no error is logged. Required changes, in order. First, make the credit decrement conditional and idempotent in the database, with a unique key per request. Second, record the paid call in a row before sending, and send the provider an idempotency key if it accepts one. Third, fix the lock itself, with a random token, a DELEX or Lua release, a TTL above the call's p99, and a count of ErrLockAlreadyExpired.

## Cheatsheet

Open the cheatsheet
THE FIRST QUESTION (ask before every lock)
  EFFICIENCY lock  -> "don't do it twice", failure = minor (dup email, wasted LLM $)
                   -> one Redis node: SET NX PX + random token + compare-and-delete
                   -> document that a rare double run can happen
  CORRECTNESS lock -> "two must never both act", failure = wrong data, double charge
                   -> no Redis lock is the guarantee
                   -> idempotent write | fencing token | consensus store + fencing
                   -> keep the Redis lock only to save work

THE CORRECT SINGLE-NODE LOCK
  acquire: SET lock:res <randomToken> NX PX <ttl>
             NX    = mutual exclusion (one command thread)
             PX    = auto-expire, no deadlock after a crash
             token = 16+ random bytes or a UUID, never "1" / "locked"
  release: DELEX lock:res IFEQ <token>                 Redis 8.4+
           EVAL 'if GET(k)==ARGV[1] then DEL(k) else 0'   any version
           Valkey: DELIFEQ lock:res <token>            Valkey 9.0+
  extend:  SET lock:res <token> IFEQ <token> PX <ttl>   Redis 8.4+, Valkey 8.1+
           Lua: if GET==token then PEXPIRE                any version
  never:   SETNX (deprecated, no TTL) | GET then DEL from the client | bare PEXPIRE
  go-redis SetNX(ctx, k, v, 0) = NO TTL. Raw SET ... PX 0 = "ERR invalid expire time"

RELEASE REPLIES
  DELEX / phase Lua : 1 mine, 0 not mine, 0 key gone      (gone = lease ran out)
  redsync script    : 1 mine, 0 not mine, -1 key gone  -> ErrLockAlreadyExpired

THE FAILURE MODES
  1. no TTL          -> crashed holder locks forever      -> always PX/EX, reject ttl 0
  2. plain DEL       -> delete the next holder's lock     -> token + compare-and-delete
  3. work > TTL      -> two live holders, even correct    -> TTL >> p99, watchdog,
     (pause, delay)                                          context deadline, idempotency, fence
  4. failover        -> lock key lost before replication  -> fence at resource; WAIT only narrows
  5. clock step      -> expiry uses the wall clock        -> fence at resource

REDSYNC v4.18.0 DEFAULTS
  expiry 8s | tries 32 | retry delay random 50-250ms | drift factor 0.01
  valid until = now + expiry - acquireTime - expiry*0.01 | quorum = pools/2 + 1 (1 pool -> 1)
  WithSetNXOnExtend: extend can recreate a lost key, so "extended" != "held all along"
REDISSON watchdog default 30s (redisson-4.8.0)

FENCING TOKEN
  rule 1: issuer never goes backwards (not INCR on one primary: repeats after failover)
  rule 2: resource checks in the same atomic step as the write
          UPDATE t SET body=:b, fence=:tok WHERE id=:id AND fence < :tok
  good issuers: Kafka producer epoch | etcd lock-key revision | ZooKeeper zxid |
                Chubby sequencer | Hazelcast FencedLock | the row's own version column
  token with no check at the resource = does nothing

AUDIT ANY LOCK
  1 what breaks if two act?   2 random token?   3 compare-and-delete?
  4 TTL > p99 with margin?   5 can ttl be 0?     6 unlock error counted?
  7 fence or idempotent write at the resource?   8 primary that can fail over?

INVESTIGATE
  PTTL <lockkey>   -> ms left on the lease
  GET <lockkey>    -> whose token holds it now
  MONITOR          -> watch SET NX / DEL / DELEX live (not on a busy primary)
  metrics          -> lock wait time, hold time, count of ErrLockAlreadyExpired

## Sources

Open the sources: the debate, the Redis docs and source, and the production cases
Read Kleppmann first and antirez right after him, because the two posts answer each other. The phase's old link to the Redis lock page now returns 404, so the current page is listed instead.

- Martin Kleppmann, How to do distributed locking: efficiency versus correctness, the pause problem, fencing tokens, why one Redis counter is not enough. About 25 minutes.

- antirez, Is Redlock safe?: the check-and-set answer, the timing model, the monotonic-clock promise. About 20 minutes.

- Redis docs, Distributed Locks with Redis: the single-node recipe with DELEX, the failover race, the wall-clock warning, and Redlock.

- DELEX, SET and SETNX command pages: IFEQ since 8.4.0, SETNX deprecated.

- Redis docs, scripting with EVAL: the atomic compare-and-delete in Lua.

- WAITAOF: wait for fsync on the primary and replicas, since 7.2.0.

- Redis 8.10.2 source, db.c: keyIsExpired and the wall-clock expiry path, with server.c and t_string.c.

- Valkey 9.1.2, DELIFEQ: Valkey's compare-and-delete command.

- redsync and its scripts.go at v4.18.0: release, touch and SetNX-on-extend scripts, defaults, validity and quorum.

- go-redis v9.5.1, string_commands.go: SetNX with expiry 0 sends no TTL.

- Redisson 4.8.0, Config.java: the 30-second watchdog default.

- Kubernetes client-go leader election: a lease-based leader with no fencing guarantee, stated in the source.

- Jepsen, etcd 3.4.3: about 18% of acknowledged updates lost under an etcd lock with 2 s leases and pauses.

- Jepsen, Hazelcast 3.8.3 and Hazelcast, Distributed Locks are Dead; Long Live Distributed Locks!: non-exclusive locks under partitions, then FencedLock on Raft.

- Confluent, Transactions in Apache Kafka: producer epochs that fence off zombie producers.

- GitHub, Downtime last Saturday: a 90-second network stall, expired heartbeats, two active fileservers, over five hours of recovery.

- Brandur Leach, Implementing Stripe-like Idempotency Keys in Postgres: the idempotency-key row with atomic phases and recovery points.

- Shopify Engineering, We replaced Redis with MySQL for inventory reservations: moving the guarantee into the store that holds the data.

- Flipkart Tech, When Good Locks Go Bad: unbounded lock waiting took Redis to 100% CPU, and a gate sized from the time spent in the locked section fixed it.

- Google, The Chubby lock service: the lock service design that calls its fencing tokens sequencers. About 45 minutes.

- Martin Kleppmann, Distributed systems lecture series: the consistency and consensus lectures under the debate. About 50 minutes each.

- Designing Data-Intensive Applications, Martin Kleppmann, chapter 8 on process pauses and fencing, and chapter 9 on consensus. No link.
Phase 0 ended with one shared Redis cluster and one rule. A single thread runs every command, so one slow command makes every service wait. That rule let you explain a stall. But Phase 0 stored each value as one piece, so it did not show what happens when many workers change parts of one value. This lesson adds a new feature to that cluster and asks which Redis type each of its needs should use. The grading service of Phase 0 grows into an AI roleplay coach, on the same platform. The answer decides how many round trips you pay, whether concurrent updates survive, and how much memory you rent.

What you must know, taught below in this order:

- A value's type decides which change Redis can make inside one command, and a client that runs GET and then SET loses updates. You can pick the command that makes a concurrent update safe, and spot code that loses writes.

- Memory follows the internal form of a value, because small collections are stored as one flat block and change to larger structures at fixed sizes. You can predict a memory jump before a deploy, and check it with two commands.

- A collection kept in order by a number you choose can rank, window or schedule, and an exact time window stores one entry per request. You can build a leaderboard, a time window or a delayed job, and price each in bytes.

- Taking a job from a Redis queue deletes it, so a reliable queue moves the job to a second list until the work is done. You can say where a job is after a worker crash, and change one command to keep it.

- A counter that estimates distinct items fits in at most 12,304 bytes with 0.81% standard error, but it cannot list the items. You can count unique users for millions of keys, and know when you need an exact structure instead.

The lab tags these five ideas c1 to c5, in the order of this list.

## What you bring from Phase 0

One thread runs the commands

Redis runs each command to the end before it starts the next one. Commands from all clients wait in one line for that thread.

One command is atomic

Because nothing runs in the middle of a command, a command that reads and changes a value cannot be interrupted. Two separate commands from one client can be, because other clients' commands run between them.

The round trip is the cost

A round trip is one request to Redis and its reply. On a network it costs far more time than the command itself, so the number of round trips sets your latency.

An O(N) command blocks everyone

Some commands do work that grows with the size of the value, such as KEYS. Such a command holds the thread for all of that work. Every other client waits, so Phase 0 replaced KEYS with the cursor-based SCAN.

Keys, values and commands

A key names one value in Redis. A command, such as GET or SET, is one instruction that a client sends. A Lua script is a small program that Redis runs as one step, so it is atomic too.

Primaries and replicas

The primary is the Redis server that takes the writes, and a replica copies them a little later. In a failover, a replica takes the place of a primary that failed.

Redis and Valkey

Valkey is an open-source project that started from the Redis code and keeps its commands. Where Valkey behaves differently, the section says so.

A shared cluster shares memory

All services on one cluster use one maxmemory limit. Keys with no TTL, a time to live after which Redis deletes the key, can fill it and take down a neighbour.

This phase needs all of them. The type you choose decides whether an update is one atomic command or two that can interleave. It decides how many round trips a feature costs, and how much of the shared memory it uses.

The situation for the whole lesson is the platform from Phase 0, where about 34 services share several Redis clusters. Your grading service from Phase 0 grows there into an AI roleplay coach. A learner talks to a simulated buyer, and the coach then runs a scoring job on the conversation. Each of its needs below copies a mechanism that another service on the platform already runs.

### The types that this lesson adds

Phase 0 treated each value as one piece. To change one part of such a value, a client runs GET and changes the value in its own code. Then it runs SET, so the whole value crosses the network twice.

Each home timeline at Twitter was a list of tweet IDs, and its timeline service handled about 30 million queries a second in one data centre. A talk by a Twitter engineer explained why Memcache did not fit this data. With Memcache, each small update read, changed and wrote the whole large timeline, so the network became the limit.

Redis avoids that pattern with types. Every value has a type, and each type has its own commands that change one part of the value inside Redis, in one command. So the type you pick decides which changes are safe, and also how much memory the value takes.

- A String holds one run of bytes, such as a JSON document or a number. The coach caches its buyer persona as a String.

- A Hash keeps named fields, each with its own value, inside one key. The coach keeps each learner's session as a Hash.

- A List keeps strings in the order you push them, and you add or take them at either end. The coach queues transcripts for scoring in a List.

- A Set holds unique strings in no order. The coach keeps the IDs of all sessions of one learner in a Set.

- A sorted set gives each member a number that you choose, called its score, and keeps the members in score order. The coach ranks trending scenarios with one.

- A Stream is a log of entries that Redis keeps in order, and that several workers can share. The queue sections compare it with a List.

- A HyperLogLog estimates how many distinct items it has seen, and it stays small however many it sees. The coach counts unique learners per scenario with one.

These commands come from the lab of this phase, with the results that the lab expects. Each one shows a type at work.

SET s hello                        # a String
LPUSH s x                          # → a WRONGTYPE error, because s is not a List
HINCRBY post:1 views 1             # one field of a Hash, used as a counter
HINCRBY post:1 likes 1
HINCRBY post:1 views 1
HGETALL post:1                     # → views 2, likes 1
ZADD lb 100 raj 250 dana 175 sam   # a sorted set, each score before its member
ZRANGE lb 0 -1 REV WITHSCORES      # → dana first, with the top score

- The LPUSH fails because s holds a String, and a List command cannot touch it. So the type of a value decides which commands are legal on its key.

- Each HINCRBY changes one field of the Hash inside Redis, in one command, so two counters live in one key.

- ZADD gives each member a score, and ZRANGE ... REV reads the members from the highest score down.

Evidence
The commands and results are E3, E4 and E8 of the phase's lab, typed for redis-cli without docker exec. The lab was not run for this lesson, so the results are the ones the lab expects. ZRANGE ... REV is the current form of the lab's ZREVRANGE. The Twitter number and the network cost of a whole-value update in Memcache come from High Scalability's summary of Yao Yue's talk, a secondary source that gives no measurement conditions. The summary gives the 30 million queries a second for the timeline service of one data centre.

Each need of the coach maps to one of these types, and the table shows where the lesson answers it.

What the coach needs | The question it raises | Where the lesson answers it

Cache the buyer persona that the model plays | A JSON String or a Hash? | Strings and Hashes

Keep each learner's session, and log a user out everywhere | Which fields change one at a time? | Hashes and Sets

Count finished scoring jobs across many workers | Can two workers lose a count? | The race between workers

Limit LLM calls per company | A counter or a log of timestamps? | Sliding windows

Queue transcripts for scoring | Where is the job if a worker dies? | Lists and Streams

Show trending scenarios and unique learners per scenario | A sorted set, a Set or a HyperLogLog? | Sorted sets and HyperLogLog

The running case. The coach is the lesson's example. Each mechanism in it comes from a service the platform already runs.

Go deeper: the O(N) commands and their cursor forms, in one place
Phase 0 taught why an O(N) command blocks every client. This lesson gives it one line per type and points back here. The cursor forms return a small batch per call, so the thread is free between batches.

KEYS pattern            → SCAN cursor MATCH pattern
HGETALL on a huge hash  → HSCAN
SMEMBERS on a huge set  → SSCAN
ZRANGE over a huge set  → bound the range; a large LIMIT offset still walks the set
LRANGE 0 -1 on a huge list → read a bounded range

Phase 5 covers big keys in full, including how to find them and delete them without a stall.

## What happens when two clients change the same value?

The type you store decides whether an update can be lost.

Phase 0 showed that one command is atomic and two commands are not. The coach runs many scoring workers, and each one adds 1 to a count of finished jobs. If each worker reads the count and writes back a new one, some of those additions disappear. This pattern, in which a client reads a value, changes it in its own code and writes it back, is called a read-modify-write.

A Redis keyspace is one large map from keys to values. The key is always a string. The value has a type, such as String, Hash, List, Set or sorted set, and the type decides which commands may touch it. Each type also comes with commands that read and change the value inside Redis, in one command. Those commands are why the type matters for safety and not only for convenience.

key (always a string)
value (one type each)
sess:abc
Hash {token, ip, role}
user:u42:sessions
Set {abc, def, ghi}
queue:jobs
List [j1, j2, j3]
ratelimit:c7:/report
sorted set {ts1, ts2, ts3}
persona:m1:u42
String "{json...}"

-
-
-
-
-

The keyspace. A Hash command on a String key returns a WRONGTYPE error, because the value's type decides which commands are legal.

Predict: 8 clients each run GET, add 1 in code, then SET, 2,000 times each. What share of the 16,000 additions survive?
About 20%. In a measured run, the counter ended at 3,234 instead of 16,000, so 79.8% of the additions were lost. With INCR, the same 8 clients ended at exactly 16,000.

The reasonable guess is "almost all survive, because Redis is fast and the gap is small". The gap is small, but 8 clients send commands at full speed, so another client's GET or SET lands inside almost every gap.

The loss follows from Phase 0's single thread. Each command runs to the end, but between two commands of one client, other clients run theirs. An addition that disappears in that gap, with no error, is called a lost update.

Two clients, one counter, GET then SET

Step 1: client A reads 5 and starts to add 1 in its own memory.

Step 2: client B reads 5 too, because A has not written yet.

Step 3: client A writes 6.

Step 4: client B also writes 6, so A's addition is lost and no error appears.

Illustration of the order of commands, not measured.

Each command is atomic. The pair of commands is not, because B's commands run between A's.

INCR counter does the read, the addition and the write inside one command, so no other client's command can run between them.

The loss grows with the number of clients, because more commands from other clients land in each gap.

Clients | Expected | GET then SET result | Lost | INCR result

2 | 4,000 | 2,000 | 50.0% | 4,000

8 | 16,000 | 3,234 | 79.8% | 16,000

32 | 64,000 | 3,766 | 94.1% | 64,000

Measured on Homebrew Redis 8.10.1 under Rosetta on an Apple M4 Pro, libc malloc, one TCP connection per client, no pipelining, loopback. Each client adds 1 to the counter 2,000 times.

Evidence
Measured for this lesson on 2026-10-18 with p1lab/race/main.go, against a fresh server on 127.0.0.1:6481. A first round went to a server on another port, was discarded, and re-run. The two rounds agreed.

Correction. The phase said a field update costs "String = 4 ops, Hash = 1". The String path is 2 round trips, a GET and a SET, plus work in the client. The larger cost is the lost update between those two commands, which the count of operations does not show.

Production code follows this rule. One service on the platform limits requests with INCR and EXPIRE inside one Lua script, and another counts fan-out jobs with HINCRBY. When no single command does the change you need, a transaction or a script can do it. The next section shows what a transaction promises.

Try E3 from the lab now. It runs LPUSH on a String key and shows the WRONGTYPE error, which proves the keyspace is typed.

Go deeper: where the rule stops, key names on a shared cluster, and the string size limit
Why loopback loses the most. The loss is highest on loopback, because the clients run in lock step there. Across a real network, the gap between GET and SET is longer, so each race window is wider. The clients also collide less often per operation. The network effect is inferred, not measured.

Where the rule stops. If a key has only one writer, GET then SET is safe, because no other write can land in the gap. That point is inferred from the single-thread model.

Why names matter here. Keys from dozens of services live in one keyspace on a shared cluster. Without a convention, two services can write the same key, and nobody can say which service owns a key or its memory.

The common style. Colon-separated parts, from general to specific, such as type:sub:id:id. A key like persona:m1:u42 says the type, the scenario and the user. A key prefix is the first part of a key, and a good one names its type or its service. It makes SCAN MATCH persona:* possible, so you can find, count and size one service's keys.

Put the tenant ID in the key. A multi-tenant platform writes the company ID value into each key, such as cache:<companyId>:<userId>. This keeps one customer's cache from being served to another customer, so it is a correctness and security property. The platform writes the ID value itself, with no literal COMPANY_ prefix.

More than one convention exists. The platform has no single standard, and several styles live side by side. One API layer uses pipe-separated keys. CK|<url>|<dataHash> holds a cached response. SK|<scope>|md5(url)|<hash> and MSK|md5(scopes)|md5(url)|... tie a response to one or more invalidation scopes. Scope|<scope> lists the keys of one scope, so a whole scope can be deleted at once. Another service uses game|<eid>|company|<cid>|new. When you edit a service, match the style it already uses.

Keys on one shard. In a cluster, the part of a key inside braces alone decides the slot. So {<companyId>}key puts a tenant's keys on one shard. Then one MGET, the command that reads many keys in one call, can read them all. This is a sharding tool, not a naming style, and Phase 4 explains slots.

The trap. A key with no prefix, such as u42 or count, can collide with another service's key, and you cannot find it with SCAN MATCH.

Size limit. A String value can hold up to 512 MB, set by proto-max-bulk-len 512mb in redis.conf at 8.10.2.

Check it in your services. Search one service for the code that builds Redis keys. Check three things. Is there a type prefix? Is the tenant ID in the key? Could two services build the same key?

One command is safe, and some changes need several. The next section asks what a transaction promises when one command is not enough.

## What does a transaction promise, and what does it not?

A transaction runs its queue with nothing in between, and never undoes a command.

INCR made one change safe in one command. The coach also charges each scoring job to its company's LLM budget. It reads the budget, checks that the job fits, then lowers the budget and logs the charge. No single command does all three steps, so the race from the section above comes back.

A transaction is a queue of commands on one connection. MULTI starts the queue, and each later command replies QUEUED and waits. EXEC runs the whole queue in order, and no other client's command runs in the middle. WATCH, sent before MULTI, makes EXEC run only if no watched key changed after the WATCH. This is optimistic locking: the client takes no lock, checks at the end, and tries again if another client wrote first.

The coach charges a budget with WATCH, and another worker writes first

Step 1: coach A watches the budget key. Redis adds A to the list of clients that watch it.

Step 2: A reads 100 and decides that a job of 30 fits.

Step 3: worker B writes 90. Redis marks every watcher of the key dirty, so A is now dirty.

Step 4: A sends MULTI and SET budget 70. The SET only joins the queue.

Step 5: EXEC sees that A is dirty, replies a null array and runs nothing, so B's 90 stays.

An example order, made up to show the shape of the race. Without WATCH, step 5 would write 70 over B's 90.

A WATCH turns the lost update into an aborted EXEC, which the client sees and can retry.

Predict: the coach queues INCR on a counter, then LPOP on a key that holds a String by mistake, then SET on a log key. EXEC runs. Which of the three writes are still there afterwards?
The INCR and the SET. LPOP fails with WRONGTYPE inside the EXEC reply, and the other two commands still run. In a measured run, EXEC returned [1 | WRONGTYPE ... | OK], and afterwards tx:n was 1 and tx:b was done. Redis has no rollback.

The reasonable guess is "none of them, because the transaction failed". A SQL transaction works that way. Redis checks each command only when it is queued, and an error found later stays inside that one command's reply.

An error can happen at two times, and the time decides what EXEC does.

The error is found | Examples | Reply while queueing | What EXEC does

While queueing | Unknown command, wrong number of arguments, ACL denied, MOVED, out of memory | The error, not QUEUED | Replies EXECABORT and runs nothing

While EXEC runs | WRONGTYPE, a value that is not an integer | QUEUED | Runs every command, and this one replies its error

The two error times. E13 part b measured row one with a wrong number of arguments, and part a measured row two with WRONGTYPE. The other examples are from the source.

- While a client is in MULTI, Redis checks each command before it replies QUEUED. It checks the name, the arguments, ACL, the cluster slot and the memory limit.

- A failed check sets CLIENT_DIRTY_EXEC on the client. Redis then stops storing the rest of the queue, to save memory.

- EXEC on a dirty transaction replies EXECABORT Transaction discarded because of previous errors. and runs nothing.

- A command that passed the checks can still fail on the data. Its error becomes its own entry in the EXEC reply, and the next command runs.

The reason for no rollback is design, not a missing feature. The docs say rollback would hurt "the simplicity and performance of Redis". The cost lands in client code that treats an error as "nothing happened".

Retry on any error. go-redis TxPipelined returns the error of the first failed command. In the measured run it returned WRONGTYPE, yet tx:n went from 1 to 2 and tx:b became again. A loop that retries on that error adds 1 again on every pass.

Retry only on TxFailedErr. That error means a watched key changed and nothing ran. An EXECABORT also means nothing ran, but a retry fails the same way. Any other error from Redis means EXEC ran, so read each command's error and do not send the queue again.

A network error after the client sent EXEC is a third case, because the client cannot know whether it ran. Make the change idempotent, or read the state before you retry.

A watch reacts to any change of the key, not only to a new value. Every command that changes a watched key marks each client that watches it dirty, even a SET of the same value. A command that changes nothing, such as SADD of a member that is already there, does not. EXEC also checks whether a watched key expired. E13 part c ran one row for each kind of change.

Between WATCH and EXEC | EXEC

Nothing changes | commits

B reads the key with GET | commits

B writes another key | commits

B writes the same value | aborts

B sets a TTL with EXPIRE 100 | aborts

The key expires before EXEC | aborts

B runs FLUSHDB | aborts

B runs SWAPDB 14 15 | aborts

Measured with E13 part c on the Homebrew build named under the race table, port 6581. Every row matched the rule in the source.

This surprises most people: a write of the same value aborts the watcher, and so does an EXPIRE. EXEC also drops every watch before it runs, whether it commits or not. So each retry must send WATCH again.

Under contention the WATCH loop stays correct, and it pays for every aborted attempt. E13 part d starts N clients, and each adds 1 to one key 200 times.

- 4,166.5 ms: WATCH loop, 32 clients, 6,400 increments

- 73.5 ms: plain INCR, the same work

- 0 of 100: commits against a plain INCR writer

Measured with E13 part d on the same Homebrew build, port 6581, go-redis v9.5.1, one connection per client, 3 round trips per attempt.

Evidence
Run on 2026-10-19 with code/phase01_data_structures/tx_watch, on the Homebrew 8.10.1 server that E13 names, over loopback. Over five runs, the aborts per commit at 8 clients were 4.00 to 4.87, and at 32 clients 17.48 to 17.81.

- No increment was lost, because the final value equalled the commits in every run.

- When every writer uses the loop, an abort needs another client's commit, so the group always moves forward. That is inferred from the rule that only a write aborts a watch.

- One client can still wait a long time. At 2 clients, one increment needed 201 attempts, because the other client won every round until it finished.

- A writer that does not use WATCH can stop the loop. Against a plain INCR loop, 0 of 100 increments committed. This is livelock: the client keeps working and makes no progress.

The arithmetic for the livelock, inferred from the run:

writer: 3,299 INCR in 472 ms           → one write every 143 µs
one round trip: 71.9 ms / (200 × 3)     → about 120 µs
from WATCH to EXEC: 2 round trips       → about 240 µs
240 µs gap, one write every 143 µs      → a write lands in almost every gap

A retry cap turns the wait into an error. With a cap of 10 at 32 clients, 3,491 of 6,400 increments gave up. redis-py's transaction() retries with no limit, and go-redis leaves the loop to you. So choose a limit and a random wait between attempts, and fail the request when it reaches the limit.

An open-source file system, SwordFS, met this limit in its tests. Writers of unrelated names all watched one parent key, and its default allowed 3 attempts. One create in 40 failed with "Redis transaction retry limit exceeded". The fix raised the default to 8 attempts, with the same random backoff.

Evidence
SwordFS issue #454, closed 2026-10-10, read with its comments. A small open-source project, not a company postmortem. redis-py redis/client.py:628-638 at v8.1.0: while True on WatchError. The cap run used -max-retries 10 on the same server.

In a cluster, every key of one transaction must belong to one slot, or EXEC replies CROSSSLOT. A slot is one of the parts into which a cluster divides its keys. A hash tag, the part of a key inside braces, fixes it, because only that part decides the slot. {c7}:budget and {c7}:log hash only c7, so they share a slot.

So pick the smallest tool that does the change on the server in one step.

- Does one command do the change?

- yes: Use it: INCR, SET ... NX, or SET k new IFEQ old on Redis 8.4 and later.

- no: Ask the next question.

- Do the writes depend on values you read first?

- no: MULTI and EXEC, sent in one round trip.

- yes: Ask the next question.

- Do many clients write the key, or do some write without WATCH?

- no: WATCH with capped retries and a random backoff.

- yes: A Lua script or a Function, which runs once with no abort. Phase 3, section 3.8, teaches both.

Choosing between a command, a transaction and a script. Each step down costs more round trips or more code on the server.

Try E13 from the lab now. Part a ends with tx:n=2 after a call that returned an error, and part c prints one row per kind of change.

EXEC isolates the queue, but it never undoes a command.

Retrying a transaction on any error runs its finished writes again.

Run E13 part c and see which changes abort a WATCH.

Go deeper: the AOF and replicas, pipelining, the 8.10.2 ACL fix, cluster clients, and Valkey
Isolation, not atomicity. elite-storage 3.1 separates two promises. Atomicity is about what a failure leaves behind, and isolation is about other clients. EXEC gives isolation. It gives all or nothing only before it starts, because a client that disconnects before EXEC runs nothing. elite-storage 3.6 shows optimistic locking with a version column in PostgreSQL, and WATCH is the same idea with the version kept by the server.

What else invalidates a watch. FLUSHALL and the end of a diskless replica sync also mark watchers dirty, but only for keys that existed. Before Redis 6.0.9, a key that expired did not abort the transaction. A key that was already expired at WATCH time is ignored. Eviction counts as a change too. The eviction code calls keyModified(), which touches the watch, in src/evict.c:686 and src/db.c:2877. A run on the lab server confirmed it. With volatile-lru, evicted_keys went from 0 to 1, and EXEC replied a null array.

The AOF and the replicas. The AOF, the append-only file, is the log of writes that Redis replays at start, and Phase 4 covers it.

- One command, one EXEC or one script is one execution unit. When a unit makes more than one write, Redis wraps those writes in MULTI and EXEC for the AOF and the replicas.

- Only the writes that happened are sent, so the failed LPOP of part a is not in the file.

- A single write is sent alone, with no wrapper.

- A crash can cut the file inside a transaction. With aof-load-truncated yes, the default, Redis cuts the file and starts. Where it cuts depends on where the crash cut, as shown below.

*2 $6 SELECT $1 0
*3 $3 SET $4 tx:a $3 abc
*1 $5 MULTI
*2 $4 INCR $4 tx:n
*3 $3 SET $4 tx:b $4 done
*1 $4 EXEC
*2 $4 INCR $9 tx:single

That is the AOF after part a and one plain INCR, with appendonly yes set on the lab server for this check.

If the file ends after a whole command, Redis goes back to the offset before the open MULTI. If it ends in the middle of a command, Redis 8.10.2 cuts it after the last whole command, and the open MULTI stays in the file. The data is right after that start. But Redis appends new writes after the open MULTI, and the next start removes them with it.

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

That is the output of tx_watch/aof_cut.sh midcmd, with its last log line left out. The Homebrew 8.10.1 build and a Redis 8.10.2 compiled from source printed the same lines. With boundary, it printed start 2: tx:after=1. The first draft of this lesson said that Redis always goes back to the MULTI, and this run corrected it. After a short-read warning in the log, run BGREWRITEAOF before the next restart. In the same test, a rewrite after start 1 kept the later write. With aof-load-truncated no, Redis stops at the cut and asks for redis-check-aof, which is what the docs describe.

Pipelining. A pipeline sends many commands before it reads the replies. A pipeline alone is not a transaction, because other clients' commands can run between its commands.

- Clients send MULTI, the queue and EXEC in one write. go-redis does this in TxPipelined, and redis-py pipeline() does it by default, with transaction=True.

- The WATCH and the read cannot go into that same write, because the client needs the value before it builds the queue. So a WATCH loop costs at least 2 round trips per attempt, and E13 uses 3.

- MULTI and WATCH are allowed while a slow script holds the server, and EXEC is not. Redis accepts a pipelined MULTI and rejects the next commands with BUSY, which marks the transaction dirty. If Redis refused the MULTI too, the commands sent after the script ended would run alone.

- A watch belongs to one connection, so a reconnect loses it. node-redis fixed a bug where exec() after a reconnect committed over another client's write. Check how your client handles a reconnect between WATCH and EXEC.

The 8.10.2 ACL fix. ACL, the access control list, decides which commands and keys each user may use. Redis checks it when it queues a command and again at EXEC, so a removed permission applies to a queued transaction too.

- From Redis 8.4.0 to 8.10.1, the check at EXEC read the keys of the current command, which is EXEC itself and has no keys. So key permissions were not checked again, and command permissions still were.

- Redis 8.10.2 passes each queued command to the check. Its release note is security fix #15673, and the bug came with the lookahead pre-fetching commit.

- Valkey 9.1.2 checks with ACLCheckAllPerm(c, &acl_errpos) and has no such key cache, so the bug likely does not apply there. That is inferred from the source and was not run.

e. ACL AT EXEC on redis_version 8.10.1: access removed after GET was queued
   MULTI                      → OK
   GET tx:acl:secret          → QUEUED
   (admin) ACL SETUSER p1tx resetkeys ~other:*
   EXEC                       → [s3cret]
   GET tx:acl:secret          → (error) NOPERM No permissions to access a key

That is E13 part e on this machine's 8.10.1 build. With Redis 8.10.2, compiled from its source tag on the same Mac, the same EXEC refused the queued GET:

e. ACL AT EXEC on redis_version 8.10.2: access removed after GET was queued
   EXEC                       → [(error) NOPERM ACLs rules changed between the moment the transaction was accumulated and the EXEC call. This command is no longer allowed for the following reason: no permission to touch the specified keys]
   EXEC re-checked the key: the queued GET was refused.

Until you upgrade, also close a user's connections after a revoke, with CLIENT KILL USER <name>.

Cluster details. Each queued command is checked for its own key as it arrives. A key whose slot lives on another node gets MOVED, which marks the transaction dirty, so EXEC replies EXECABORT. At EXEC, Redis checks all queued keys together and replies CROSSSLOT Keys in request don't hash to the same slot for two slots. WATCH has the same one-slot rule. The client can hide this: go-redis v9.5.1 ClusterClient splits a TxPipeline by slot and sends one MULTI and EXEC per slot. Keys in two slots then become two transactions with no error. Its Watch checks the slots first and returns redis: Watch requires all keys to be in the same slot. Both were read in the source and not run, because the lab server is one node.

Valkey. Valkey 9.1.2 keeps the same transaction rules, read from its source and not run. It stores watched keys per database in a hash table, for an O(1) check of a duplicate WATCH. It also goes back to the MULTI when the AOF is cut inside a command, from PR #4342, so it does not lose the later writes. Valkey has SET ... IFEQ since 8.1.0 and DELIFEQ since 9.0.0. Redis has IFEQ, IFNE, IFDEQ, IFDNE and DELEX since 8.4.0.

Scripts. A Lua script or a Function runs whole on the server, with nothing in between, so it needs no WATCH and no retry. Phase 3, section 3.8 "Lua scripts and Functions in production", covers the script cache, the time limit and how each is replicated.

Evidence
Redis 8.10.2 source: src/multi.c:139-246 for EXEC, 389-428 for touchWatchedKey, 430-486 for flushes and SWAPDB, 192-223 for the ACL re-check. src/server.c:3848-3891 for propagatePendingCommands, 4277-4287 for rejectCommand, 4793-4811 for the BUSY rule, which names PR #7022. src/aof.c:1970, 2016-2026 and 2041-2056, default at src/config.c:3422. src/evict.c:686, src/db.c:2877 and 1190-1196 for eviction and keyModified(). src/cluster.c:1261-1300 and 1366-1372. Release notes at 8.10.2, lines 24-31, and PR #15673, which names commit 235e688b0. Valkey 9.1.2 src/multi.c:250-271, release notes for PRs #3360 and #4342. go-redis v9.5.1 tx.go:124, osscluster.go:1424-1425 and 1599-1605. node-redis PR #3506, merged 2026-10-13. set.json at Redis 8.10.2 and Valkey 9.1.2, delifeq.json at Valkey 9.1.2. The AOF and ACL outputs were run on 2026-10-19 on port 6581. The cut-AOF runs, the eviction run and the 8.10.2 ACL run were made on 2026-10-19 on port 6591.

A transaction joins several commands into one step. The next section shows what a String can do inside one command, and where the JSON-in-a-String habit starts to cost you.

## What can a String do in one command?

A String is a blob, a counter or a claim, and two are atomic.

INCR kept the count of finished jobs safe because it reads and writes inside one command. The coach has two more String needs. It caches the buyer persona that the model plays, and it must make sure only one worker scores each transcript.

A Redis String is a binary-safe sequence of bytes, up to 512 MB. Binary-safe means Redis does not read the bytes, so a String can hold UTF-8 text, JSON, a protobuf, an image or an integer. Production code uses a String in three ways, and each way has its own commands.

Use | Commands | Atomic inside Redis? | Coach example

Cache blob | SET k v EX s, GET k | The whole value only | The buyer persona as JSON

Counter | INCR, INCRBY, DECR | Yes, read and write in one command | Requests in this minute

Claim, or flag | SET k v NX EX s | Yes, check and set in one command | "This worker scores transcript t9"

Three uses of one type. The counter and the claim are safe under concurrency for the reason the race section showed.

Each use works like this.

- The cache blob. The service marshals the persona to JSON and runs SET persona:m1:u42 '{"name":"Dana","tone":"skeptical"}' EX 259200, a 3-day TTL. GET persona:m1:u42 returns the whole blob in one round trip.

- The cost of the blob. To change one field, the service must GET the whole value, unmarshal it, change it, marshal it and SET it. The whole object crosses the network twice, and the GET then SET pair has the race from the section above.

- The counter. INCR, INCRBY and DECR work on a String that holds an integer. Redis reads, adds and writes inside one command, so no lock is needed. A fixed-window rate limiter is INCR plus EXPIRE on a key per window. On Redis 8.8 and later, INCREX key EX 60 ENX does both in one command. On older Redis and on Valkey, a Lua script runs the two.

- The claim. SET key val NX EX 30 means "set this only if the key does not exist, and expire it in 30 seconds". The first caller gets OK and every later caller gets nil, so exactly one worker wins.

The claim is the whole idempotency pattern. An AI service on the platform claims a key with SET ... NX before it creates content, so a retried request does not create it twice. Another service wraps the same command in a helper for its own duplicate checks. The same command is also the start of a distributed lock, which Phase 3 builds and then shows where it breaks.

Correction. The phase listed SETNX as a current atomic command. SETNX is deprecated since Redis 2.6.12. Use SET key value NX EX seconds, which also sets the TTL in the same command.

One String bug is common. A plain SET on an existing key removes its TTL, so a cache entry that should expire stays forever. KEEPTTL is an option of SET that changes the value and keeps the expiry, as in SET key val KEEPTTL.

So is the persona right as a JSON String? Yes, because the coach reads and writes it whole and never changes one field. The cache layer also has no reason to look inside it. The learner's session is different, because the coach changes its fields one at a time.

Try E1 from the lab now. The second SET flag ... NX returns nil, because the first call already holds the claim.

Go deeper: the TTL bug, two newer commands, JSON inside Redis 8, and byte-level commands
The KEEPTTL bug, side by side.

The TTL is lost. SET persona:m1:u42 '{...}' EX 259200, then later SET persona:m1:u42 '{...new...}'. TTL now returns -1, so the key never expires.

The TTL is kept. The second write is SET persona:m1:u42 '{...new...}' KEEPTTL. The key still expires at the original time.

Two newer commands remove a round trip from common pairs. GETEX reads a value and changes its TTL, and GETDEL reads a value and deletes it. Both arrived in Redis 6.2.

JSON as a type. The Redis 8.0 release notes say RedisJSON and the other former modules are now part of Redis. With JSON as a type, the coach could change one field of the persona with a path update, instead of a full GET and SET. But the build decides what you get. The Homebrew Redis 8.10.1 server used for this lesson's measurements had only the vectorset module, and JSON.SET returned ERR unknown command. Whether the official Docker image includes JSON was not checked. Before you design on JSON paths, run JSON.SET on your own build.

Byte-level commands. APPEND adds bytes to the end of a String in place. GETRANGE and SETRANGE read and write a byte range, so a String can act as a random-access buffer. They rarely change a design decision.

Where JSON and Hashes meet. The Hash section next shows the other way to store an object with fields. JSON in Redis 8 adds a third choice when your build has it.

Evidence
Redis 8.0.0 release notes, line 5: "Stand alone RediSearch, RedisJSON, RedisTimeSeries, and RedisBloom are no longer needed as they are now part of Redis." The JSON.SET result was measured on 2026-10-18. setnx.json at tag 8.10.2 carries "deprecated_since": "2.6.12". getex.json and getdel.json carry "since": "6.2.0".

The next section shows when an object belongs in a Hash instead, and what a Hash changes about TTLs.

## When does an object belong in a Hash?

A Hash changes one field in one command, so field updates do not race.

The persona stays a String because the coach always reads and writes it whole. A learner's session is different. The coach updates the role, deletes the IP address on logout and reads one token on each request.

A Hash is a map inside one value, with fields and their values under one key. It matches an object with named fields. Each field can be read, written or deleted on its own, inside Redis, without moving the rest of the object.

Key u42|c7, a user and company pair

field | value

token | "abc123"

ip | "10.0.0.1"

role | "manager"

sess-index | "c7|sess-a", a field used as a secondary index

HGETALL u42|c7               → the whole object
HGET    u42|c7 role          → one field, no unmarshal
HSET    u42|c7 role manager  → change one field in place
HDEL    u42|c7 ip            → drop one field

A session as a Hash. The same object as a JSON String would need a GET and a SET for each of these changes.

The commands you will use most are HSET, HGET, HGETALL, HDEL, HEXISTS, HKEYS and HVALS. The one that matters most for safety is HINCRBY. It adds to one field inside one command, so it is a counter that lives inside an object.

Correction. The phase's examples use HMSET. It is deprecated since Redis 4.0.0, because HSET now takes many field and value pairs in one call.

A worker service on the platform uses HINCRBY as a fan-out counter. A job splits into many subtasks, and each one runs HINCRBY <jobKey> completed 1 when it finishes. The service then reads HMGET <jobKey> total completed and starts the next workflow step when the two are equal. The coach can count finished scoring subtasks the same way, with no lock.

- split: HSET job total 10 completed 0.

- each subtask ends: HINCRBY job completed 1 returns the new count.

- last one: The call that returns 10 starts the next step.

A fan-out counter in one Hash. Act on the value that HINCRBY returns, for the reason in the Go deeper block.

The session on the platform shows a second lesson, about TTLs. One service creates the session hash with HMSET and then sends a separate EXPIRE, and a second service only reads it. If the writer crashes between those two commands, the hash never expires. It becomes the no-TTL key from Phase 0 that fills a shared cluster. Send HSET and EXPIRE inside one MULTI and EXEC, or one script, so both apply together.

Hash fields can also expire one by one now, and a TTL on one field is called a field TTL. HEXPIRE, the command that sets one, arrived in Redis 7.4.0, and HSETEX, HGETEX and HGETDEL in 8.0.0. So you no longer need one String key per field to give fields their own TTL.

One line from Phase 0 applies here. HGETALL is O(N) in the number of fields, so on a hash that grew to millions of fields it blocks the thread. Bound the field count, or read with HSCAN.

Try E4 from the lab now. Two HINCRBY fields in one key end at views=2, likes=1, two independent atomic counters in one object.

Go deeper: the session contract, field TTLs in Redis and Valkey, and the old trade-off
Acting on the count. One detail of that pattern can start the next step twice. Two subtasks can each increment, and then both read the final count with a later HMGET. If each worker acts on the value its own HINCRBY returned, exactly one worker sees 10. This is inferred from the order of the commands, not seen in an incident.

The session contract in detail. The writer is a Node service. It runs hmset(key, {email, attempt, company, expiryTime, lastActivityTrackedTime, ...}) and then a separate EXPIRE. The reader runs HGETALL on a userId|companyId key, and deletes secondary-index fields with HDEL. So the Hash is a contract between two services, and a change of field names on one side breaks the other. That last point is inferred.

A measured field TTL. HEXPIRE sess 60 FIELDS 1 token followed by HTTL returned 60 -1. The command that prints a key's internal form, taught in the memory sections below, then returned listpackex.

Memory. Memory is the other reason to group fields. A small Hash is stored as one flat array, so 20 fields in one Hash cost far less than 20 top-level String keys. It also returns all of them in one round trip with HGETALL. The memory sections below measure this.

Check it in your services. Find a session or profile that a service stores as a JSON String. Ask what breaks when two requests change two different fields at the same time. Each one rewrites the whole blob, so the later write removes the earlier change.

The old trade-off. Before Redis 7.4, a TTL applied only to a whole key. DoorDash's feature store stored one Hash per entity and read it with HMGET. Their write-up names the cost, that a TTL works on the whole key and not on fields. Field TTLs remove that cost.

Valkey. Valkey has HEXPIRE, HSETEX and HGETEX since 9.0.0, and HGETDEL since 9.1.0. Whether Valkey's HSETEX and HGETEX take exactly the same arguments as Redis 8 was not checked. In Valkey, a Hash with any field TTL is converted to a hashtable, so it loses the compact form. In Redis, a small Hash with field TTLs keeps a compact form called listpackex, which stores field, value and TTL together.

How Redis finds expired fields. Each database keeps an index of hashes ordered by their next field expiry. Active field expiry deletes up to 10000/hz fields per call, and does more when it falls behind. Whole keys use a different method. Active expiry of keys scans the keys that have a TTL in batches, and it keeps no order by expiry time.

The separate-keys argument. One checkpoint question in the phase asked when 6 separate String keys per session beat one Hash. The usual answer was "when fields need their own TTL". On Redis 7.4 or later and Valkey 9.0 or later, a Hash gives you that too.

Evidence
src/commands/hexpire.json at Redis tag 8.10.2: "since": "7.4.0". hsetex.json: "since": "8.0.0". Same files at Valkey tag 9.1.2. hmset.json: deprecated since 4.0.0. The HEXPIRE run was measured on 2026-10-18. Valkey's conversion to hashtable: src/t_hash.c:375 and 556-560 at 9.1.2. Redis listpackex: src/server.h:3941-3948 at 8.10.2. Field expiry limit: src/expire.c:101 and 228-275 at 8.10.2. DoorDash, 2020-11-19, from the archived post.

A Hash groups the fields of one object. The next section covers a group of objects, such as all sessions of one user, which a Set holds.

## What do Sets compute on the server?

A Set removes duplicates and compares groups inside Redis.

A Hash holds the fields of one session. To log a learner out on every device, the coach needs the group of all that learner's session IDs. It also needs to find learners who are in two cohorts at once, without pulling both lists into the service.

A Set is an unordered collection of unique strings. Adding a member that is already there changes nothing, so a Set removes duplicates for you. Redis also computes intersections, unions and differences of Sets on the server, so the members never cross the network.

SADD  user:u42:sessions sess-a sess-b sess-c   → 3
SADD  user:u42:sessions sess-b                 → 0, already present
SCARD user:u42:sessions                        → 3, not 4

Log u42 out everywhere:
SMEMBERS user:u42:sessions   → [sess-a, sess-b, sess-c]
DEL sess:sess-a ; DEL sess:sess-b ; DEL sess:sess-c
DEL user:u42:sessions        ← drop the index itself

A Set as the index of one user's sessions. The session service on the platform logs a user out everywhere in this way.

The Set commands follow the rule of the race section, because each one does its check inside Redis.

- SADD returns how many members it added, so its reply tells you whether this member is new, with no separate check.

- SISMEMBER tests one member in O(1), such as "does this user have this session?".

- SMISMEMBER tests many members in one round trip, since Redis 6.2.

- SINTER, SUNION and SDIFF return members in both, in either, or in the first but not the second.

- SINTERCARD returns only the size of the intersection, since Redis 7.0, so a count does not send every member back.

"Learners in both cohort A and cohort B" is one SINTER, computed in C on the server. The other way is to pull two lists into your service and loop over them, which costs two large replies and the loop.

The server-side work has a cost on the single thread. The Redis latency docs name big set intersections as an example of a slow command. The O(N) line also applies, because SMEMBERS on a huge set blocks the thread. A session index is a few members. A Set of every user who ever viewed a course can hold millions. Read such a Set with SSCAN, or model it in a different way.

Try E7 from the lab now. It shows the duplicate absorbed with SCARD=3, the log-out-everywhere fan-out, the three set operations and SSCAN over 10,000 members.

Pick the type whose command does your read-modify-write inside Redis.

GET, change, then SET from many clients lost 80% of updates at 8 clients.

Search a service for a GET followed by a SET of the same key.

The type decides which work is atomic. The next section shows that the size of the value decides how Redis stores it, and so how much memory you pay.

## Why can the same data take several times more memory?

Redis stores small collections in a compact form and converts them at fixed sizes.

The first concept decided which work is atomic. The coach's session hash has five short fields today. A deploy adds one field that holds a 100-byte JSON value. Then the cluster's memory climbs for every session at once, with no new users.

Redis stores each Hash, Set, sorted set or List in one of two forms, and the form is called its encoding. A small one is a listpack, one flat block of bytes that holds the entries one after another. A large one uses a structure built from pointers, such as a hash table or a skip list. A skip list is a sorted linked list with shortcut links. A large List uses a quicklist, a chain of small listpacks.

The large form costs more memory for each element. Redis converts from the small form to the large form when the collection passes a size limit, and that conversion is the memory jump.

The command OBJECT ENCODING prints which form a key uses, so you can see the jump before you measure it.

listpack: one block, entries in a row

-
-
-
-
-
hdr token abc1 role mgr end
A lookup scans the block from the start.
hashtable: buckets and pointers
b0
b1
b2
b3
entry: token → abc1
entry: role → mgr

-
-
Each entry is its own allocation, with pointers.
A lookup hashes the field and jumps to it.

The same two fields in the two forms. The block has no pointers and no per-entry allocation, so it is several times smaller.

Predict: your session hashes have 300 short fields, and a colleague read that the limit is 128. What does OBJECT ENCODING print? A deploy then adds one field with a 100-byte value, and later you delete that field. What prints after each step?
First listpack, because the default limit for a Hash in current Redis is 512 fields, not 128. After the 100-byte value, hashtable, because any field or value over 64 bytes converts the whole Hash. After the delete, still hashtable, because a Hash does not convert back when it shrinks.

The guess "hashtable from the start" is reasonable, because the phase gave 128 as the limit. The guess "it goes back after the delete" is also reasonable, and it is true only for Lists.

Redis uses the slow-looking form on purpose, for three reasons.

- A lookup in a listpack is a scan from the start, so it costs O(N). Redis keeps N small, so the average cost of HGET and HSET stays O(1) in practice.

- One block of bytes uses the CPU cache well, because the entries sit next to each other in memory.

- A hash table needs pointers and a separate allocation for each entry, so it costs several times more memory per element.

- An insert can push the count past the entries limit, or a field or value past the value limit. Then Redis converts the whole collection to the large form in that command.

- Hashes, Sets and sorted sets stay in the large form when they shrink. Lists convert back to a listpack, but only below half the limit, so a list near the limit does not convert back and forth.

Type | Listpack limit | Value size limit | Large form

Hash | hash-max-listpack-entries 512 | hash-max-listpack-value 64 | hashtable

Sorted set | zset-max-listpack-entries 128 | zset-max-listpack-value 64 | skiplist

Set of strings | set-max-listpack-entries 128 | set-max-listpack-value 64 | hashtable

Set of integers | set-max-intset-entries 512, an intset form | n/a | hashtable

List | list-max-listpack-size -2, 8 KB per node | n/a | quicklist

Defaults at Redis 8.10.2, from src/config.c and redis.conf. Valkey 9.1.2 has the same defaults.

Correction. The phase gave 128 as the Hash and List limits. The Hash default is 512 in Redis 7.2.0, 8.10.2 and Valkey 9.1.2. The List setting is -2, which means 8 KB per node. Since 7.2, Sets of strings are listpacks too, and Lists convert back when they shrink.

MEMORY USAGE prints how many bytes one key and its value use, and it measured the jump at each limit one key at a time.

MEMORY USAGE per key, measured on the Homebrew build named under the race table, with libc malloc. One element past the limit costs 3.9 to 18 times the memory. A 64-byte Hash value keeps the listpack, and a 65-byte value converts it.

Two commands check any key. OBJECT ENCODING key prints the form, such as listpack or hashtable. MEMORY USAGE key prints the bytes the key and its value use, so you can compare two layouts with numbers, not guesses.

The failure looks like "memory grew several times after a deploy, with the same number of keys". A new field, or a value that grew past 64 bytes, pushed many small hashes into the large form at once. To confirm it, run OBJECT ENCODING and MEMORY USAGE on a sample of keys from before and after the deploy.

The encoding can also change behaviour, not only memory. At Grab, a Lua script ran again on a replica, and HGETALL returned fields in a different order there. One node held the small hash in the compact form, then called a ziplist, and the other held it as a hashtable. So the script made different decisions on each node. The replica drifted from the primary until a failover promoted it, and then it failed under load. Redis 7.0 removed this replication of whole scripts, so a replica now applies only the writes a script makes. The field order still differs between the two forms, so code must not depend on it.

Try E12 from the lab now. A one-field Hash prints listpack, and after a 100-byte value it prints hashtable.

Go deeper: Grab's replica, lists, intsets, the 1 GB cap, hash templates and Twitter's lists
Grab in detail. Grab used Redis on ElastiCache as a message queue, with a primary and replicas. After each deploy, the replica's CPU rose with no read traffic, and a reboot fixed it each time. Then a failover promoted that replica, its CPU reached 100% under reads, and the cluster stopped working. Redis then replicated the script itself, not its effects, so the script ran again on the replica. On an RDB load, a replica can rebuild a small hashtable as a listpack, and the two forms return fields in different orders. The fix was to sort the HKEYS or HGETALL output inside the script. Sorting 100 elements took under 1 ms. They rejected replicating the script's effects, because that would send thousands of writes to replicas.

Lists. A List is a quicklist, a linked list of listpack nodes, or one listpack when it is small. The phase called it a doubly-linked sequence of strings, which was true of old versions. The fill setting -1 to -5 maps to 4, 8, 16, 32 and 64 KB per node, and the default -2 is 8 KB. list-compress-depth 0 means no LZF compression of inner nodes, which is the default. The source says "we don't convert quicklist to listpack until its length or size is below half of the limit". In a measured run, a 5,000-item list cut to 10 items became a listpack again, and a 513-field hash cut to 10 fields stayed a hashtable.

Intsets. A Set of integers is a sorted array of 16-bit, 32-bit or 64-bit integers, the narrowest that fits every member. One string member converts it.

The cap on a listpack. Any listpack is capped at 1 GB by LISTPACK_MAX_SAFETY_SIZE, so a limit raised very high still has a ceiling.

Hash templates, new in 8.10. Redis 8.10 can share field names across hashes that have the same field set. It is off by default, with hash-min-template-entries 0. Hashes with field TTLs are never converted to templates. Valkey 9.1.2 has no template settings.

Twitter's timelines. Twitter kept each timeline as a list of tweet IDs. One ziplist, the older compact form, per timeline tied the list to a low size limit, and each write to a large ziplist needed memmove and realloc. A plain linked list cost two pointers per small ID. Their fix was a "Hybrid List", a linked list of ziplists with a byte limit per node. That is the same shape as today's quicklist. Whether one led to the other was not traced. The timeline service in one data centre used about 40 TB of heap, about 30 million QPS and over 6,000 instances.

Where the switch is checked. The thresholds are read in t_hash.c, t_set.c, t_zset.c and t_list.c. The internals report found no code path that converts a hashtable back to a listpack on delete. One zset path converts back only for store commands. That is inferred from reading the conversion code.

Evidence
Defaults: src/config.c:3511, 3593, 3600-3607 and redis.conf:2215-2332 at Redis 8.10.2. Valkey: src/config.c:3392, 3471-3475 at 9.1.2. Docs quote from the memory-optimization page: "When hashes are small we can instead just encode them in an O(N) data structure ... the amortized time for HGET and HSET commands is still O(1)". Shrink rule: src/t_list.c:58-63. Skip-list constants and the 1 GB cap: src/server.h:656-657, src/listpack.c:126-130. Hash templates: redis.conf:2218-2243 at 8.10.2, absent from redis.conf at 8.8.0 and from valkey.conf at 9.1.2. Grab, 2020-09-07. Redis 7.0.0 release notes: "Remove EVAL script verbatim replication". An RDB load still builds a small hash as a listpack first: src/rdb.c:3129 at 8.10.2. Twitter: High Scalability summary of Yao Yue's talk, 2014-09-08, a secondary source. Measurements on 2026-10-18, Redis 8.10.1, libc malloc.

A single key can jump several times in size. The next section shows how one layout choice uses the small form on purpose, across 100,000 small values.

## How do small hashes hold many small values?

Every top-level key has a fixed cost, and grouping values into hashes removes most of it.

One key can jump several times in size when it passes a limit. The coach also maps each transcript ID to the company that owns it, so it can find the right tenant. That is 100,000 tiny pairs today, and each one as its own String key pays a fixed cost per key.

Every top-level key carries overhead beyond its bytes, such as an entry in the keyspace's hash table and an object header. A Hash under the listpack limit stores its fields with almost none of that. So you can store many small values as fields of a few hashes. You then pay the per-key cost once per hash, not once per value. This is called bucketing.

One key per pair. SET tx:1155315 939, and so on, 100,000 times. Each pair pays the full cost of a top-level key.

Buckets of fields. HSET txbucket:1155 1155315 939. The bucket number is the ID divided by 1,000, so one Hash holds up to 1,000 pairs.

The bucketing layout. The saving holds only while each bucket stays under the Hash listpack limit.

The layout works in four steps.

- Pick a bucket size B. Compute the bucket as the ID divided by B, and use the full ID as the field name, as Instagram did.

- Write with HSET bucket field value and read with HGET bucket field, one round trip each, as before.

- Check that B is at or below hash-max-listpack-entries, 512 by default, and that every value stays at or below 64 bytes.

- If B is above the limit, every bucket becomes a hashtable, and most of the saving is gone.

Step 4 is where a copied design fails. The measured run below shows a bucket size of 1,000 taken from a public post, on the default limit of 512.

Layout for 100,000 id-to-id pairs | Bytes, used_memory change | Encoding

100,000 plain String keys | 4,728,480 | n/a

1,001 hashes of up to 100 fields | 766,880, 6.2 times smaller | listpack

101 hashes of up to 1,000 fields, default config | 2,997,664 | hashtable

101 hashes of up to 1,000 fields, hash-max-listpack-entries 1000 | 824,480 | listpack

Measured on Redis 8.10.1 from Homebrew, an x86_64 build under Rosetta on the M4 Pro, with libc malloc. The 1,000-field buckets lose most of the saving on the default config, because 1,000 is above the limit of 512.

Bucketing: memory against bucket size

Pairs
Bucket size
hash-max-listpack-entries
Encoding , bucketed , plain keys

Illustration, not measured. It scales the bytes per pair from the measured table above: 47.3 for plain keys, about 8 in a listpack, about 30 in a hashtable.

Instagram needed to map about 300 million photo IDs to the ID of the user who owned each photo. As plain String keys, 1 million pairs used about 70 MB, so 300 million would need about 21 GB. That did not fit the 17 GB machine type they wanted. They moved the pairs into hashes of 1,000 fields each, and 1 million pairs then used 16 MB. Their estimate for all 300 million was a little under 5 GB, on an instance that cost about a third as much.

Evidence
Instagram Engineering, "Storing hundreds of millions of simple key-value pairs in Redis", 2011-11-01, read from the web archive copy. These are prototype numbers and an extrapolation on Redis of 2011, which used the older zipmap encoding with hash-zipmap-max-entries set near 1,000. Memcached used about 52 MB for the same million pairs. The bucketing table was measured on 2026-10-18.

Strings have small encodings too, and in Redis 8 a long key name can push a small value into a larger form. The Go deeper block shows the rule.

Try E2 from the lab now. It stores one session as a String and as a Hash, and prints OBJECT ENCODING of the Hash, which is listpack.

Memory follows the encoding, so keep collections under the listpack limits.

A 513th field made one hash 3.9 times larger in memory.

Run OBJECT ENCODING and MEMORY USAGE on one key of each type you store.

Go deeper: the CPU cost of a larger limit, String encodings, DoorDash, and Valkey's per-key saving
The CPU side of a larger limit. A larger limit has a cost too. A listpack lookup is a scan, so a bigger listpack makes each HGET and HSET slower. Instagram stopped at 1,000 entries because higher values made HSET use noticeable CPU. That point was measured on the old encoding, and the CPU point for today's listpack was not measured for this lesson.

String encodings. Strings have small encodings too, and in Redis 8 the length of the key name affects them. OBJECT ENCODING on a String prints one of three forms.

- int means the value is an integer, stored as a number.

- embstr means the value is stored inside the same allocation as its object.

- raw means the value is in a separate allocation, so it costs another allocation and a pointer.

In Redis 8, the key and value sit together in one object. The value stays embedded only when the key, the value and the headers fit in one CPU cache line. A cache line is 64 bytes, or 128 bytes on Apple arm64 builds. In a measured run on an x86_64 build, key k38 with a 38-byte value was embstr. Key k39 with a 39-byte value was raw. A 32-character key with a 20-byte value was also raw, so a long key name can push a small value into the larger form.

DoorDash. Their ML feature store holds billions of feature values, and store ranking makes over 1 million predictions per second. Each entity is one Hash, read with HMGET. They hashed feature names to 32-bit xxHash values, stored values as protocol buffers and compressed lists with Snappy. Memory fell from 298 GB to 112 GB per billion features. CPU fell from 208 to 72 vCPUs per 10 million reads per second. Redis read latency improved 40%, and total API latency about 15%.

The old String rule. In Redis 7.2, a String value of 44 bytes or less was embstr. In Redis 8 the rule depends on the key length too, as the section above shows.

Valkey. An AWS blog says Valkey 8.0 saves 32 bytes per key in cluster mode. It names a dictionary per cluster slot as the cause. In its test, 10 million SET commands with 100-byte values on random keys left about 6.3 million keys. Memory went from 1.39 GB on Valkey 7.2 to 1.11 GB on Valkey 8.0, a 20% drop for that workload. The test ran on ElastiCache, the AWS managed service, so it is a vendor number.

Binary keys. Cloudflare's anomaly detection saved about 30% memory with binary keys instead of readable keys. Short keys help for the same per-key reason.

Evidence
Redis 7.2.0 src/object.c:122. Redis 8.10.2 src/object.c:287-292, "Embed when the sum is less than a cache line", and src/config.h:38-43. Measured on 2026-10-18 on the x86_64 Homebrew build. DoorDash, 2020-11-19, archived copy. AWS blog, 2024-11-21. Cloudflare, 2021-03-12.

Encodings set the bytes per element. The next concept is a structure whose bytes per element decide whether a design fits at all, the sorted set.

## How does a sorted set keep members in order?

You choose the score, so one structure ranks, windows and schedules.

Encodings set the bytes per element, and the next structure stores one element for every event you record. The coach needs three ordered things. It shows trending scenarios, limits LLM calls per company over the last minute, and runs re-scoring jobs at a set time.

A sorted set is a Set where every member carries a number, its score. Redis keeps the members ordered by score at all times. You choose what the score means. Points give a leaderboard, a timestamp gives a time window, and a due time gives a schedule.

ZADD board 4820 dana  980 raj  6510 mei  3100 sam

score:   980     3100     4820     6510
member:  raj  →  sam   →  dana  →  mei      kept in order on every write
rank:    0       1        2        3

ZRANGE   board 0 2 REV WITHSCORES   → top 3: mei, dana, sam
ZREVRANK board dana                 → 1, second from the top
ZSCORE   board dana                 → 4820
ZINCRBY  board 100 dana             → 4920, moved in one atomic command

A leaderboard. ZINCRBY changes a score and its position inside one command, for the reason the first concept gave.

Predict: an API allows 5,000 requests per hour per token, and 200,000 tokens are active. A limiter stores each request as one member, with its timestamp as the score. About how much memory does it need, against one counter per token?
About 100 GB, against about 6 MB for counters. A sorted set of 5,000 members uses the large form, at about 94 to 105 bytes per member in a measured run. So one token's log is about 0.5 MB, and 200,000 of them are about 100 GB. A counter is an integer String of about 30 bytes. This total is inferred from the measured bytes per member, and it ignores key overhead.

The guess "a few hundred MB" is reasonable, because a timestamp is only 8 bytes. Each member also carries the skip-list node, the hash-table entry and the member string itself.

A large sorted set is two structures that hold the same members.

- A hash table maps each member to its score, so ZSCORE is O(1).

- A skip list keeps the members in score order. It is a linked list with extra levels of links that skip ahead, so a search moves down the levels in O(log N) steps.

- Each new node gets one more level with a chance of 1 in 4, up to 32 levels, so the upper levels stay small.

- ZADD, ZINCRBY and ZRANK are O(log N). A range read is O(log N + M) for M members returned.

- So the sorting work happens on each write. A leaderboard that is read far more often than it is written pays the cost on the less frequent path.

- Up to 128 members of at most 64 bytes each, the sorted set is a listpack instead, from the encoding table.

Members in one key | Encoding | Bytes | Bytes per member

100 | listpack | 3,312 | 33

128 | listpack | 4,262 | 33

129 | skiplist | 13,584 | 105

1,000 | skiplist | 94,641 | 94

10,000 | skiplist | 1,048,146 | 104

A fixed-window counter | int String with TTL | 30 | n/a

Measured MEMORY USAGE of one sorted set with a microsecond timestamp as score and the timestamp plus a suffix as member. The Homebrew x86_64 build of 8.10.1, libc malloc.

Correction. The phase used ZREVRANGE and ZRANGEBYSCORE as the main commands. Both are deprecated since Redis 6.2.0. Use ZRANGE ... REV and ZRANGE ... BYSCORE. ZREVRANK is not deprecated. The phase also called every sorted set a skip list, but small ones are listpacks.

One trap applies to every range read. LIMIT offset count limits what Redis returns, but Redis still walks offset members to reach the start. A large offset is O(N) again, so page through a large set by score with BYSCORE and the last score you saw.

Try E8 from the lab now. After ZINCRBY lb 200 raj, raj moves from the bottom to the top with 300 points.

Go deeper: the skip list constants, and a sorted set per map cell at Lyft
Constants. ZSKIPLIST_MAXLEVEL is 32 and ZSKIPLIST_P is 0.25 at Redis 8.10.2. The large form is a struct with one dict and one zskiplist, so every member is stored in both.

Lyft. Lyft's dispatch keeps an index of driver locations in Redis. The final model is one sorted set per geohash cell, scored by the time each driver was last seen and trimmed to about 30 seconds. They rejected Redis GEO commands, because those have no expiry and no metadata. Region names made poor shard keys and created hot shards. Expiring many keys at once also blocked Redis longer than they expected. The fleet grew from 3 instances to about 750.

A number the phase gave. It said a ZRANGEBYSCORE that returns half a million members blocks the thread for tens of milliseconds. That time was not measured for this lesson, so treat it as a rough size, and measure range latency on your own data.

Evidence
src/server.h:656-657 and 1816-1819 at 8.10.2. zrangebyscore.md in the Redis docs, lines 91-92: "if offset is large, the sorted set needs to be traversed for offset elements". Deprecations: zrevrange.json, zrangebyscore.json, zrevrank.json at 8.10.2. Lyft, RedisConf17 slides. The memory table was measured on 2026-10-18.

You now know what each member costs. The next section uses timestamps as scores to build a rate limiter, and compares its bytes with a counter's.

## What does an exact sliding window cost?

An exact window stores every request, and a counter stores one number.

Each sorted-set member costs about 33 bytes small and about 100 bytes large. The coach must stop any one company from sending more than 100 LLM calls a minute, and there are two common ways to count.

A fixed window counts requests in numbered blocks of time, such as one counter per calendar minute, and the count starts again at each boundary. A sliding log keeps the timestamp of every allowed request and counts those in the last 60 seconds, so it is exact at any moment. The first stores one integer per company, and the second stores one sorted-set member per request.

Fixed window, burst at the boundary. INCR rl:c7:<minute> and EXPIRE. A company sends 100 calls at 0:59.99 and 100 more at 1:00.01. Both windows allow 100, so 200 calls pass in about 20 ms.

Sliding log, exact. At 1:00.01 the log still holds the 100 calls from 0:59.99, so the next call is rejected. The cost is one member per allowed call.

The same burst under both designs. The fixed window allows up to twice the limit across one boundary.

The sliding log runs four commands for each request, with the window W.

- ZREMRANGEBYSCORE key 0 (now-W) removes requests older than the window.

- ZADD key now now records this request, with the timestamp as score and member.

- ZCARD key counts the requests in the window, and the service returns 429 when the count is over the limit.

- EXPIRE key W lets an idle company's key delete itself.

Two details decide whether the four steps are correct under load. They must run as one unit, through MULTI and EXEC or a script, or two requests can both count before either adds. The member must also be unique per request, because two clients with the same timestamp would write one member and count once.

Sliding log memory for one cluster

Limit per window
Active clients
Sliding logs , fixed-window counters

Illustration from the measured bytes per member: 33 up to 128 members, about 95 above. A counter is 30 bytes. Key overhead is ignored, so this is inferred, not measured.

With a limit of 1,000 and 100,000 active clients, the logs need about 9.5 GB, against about 3 MB of counters. That number is why large public systems count instead of logging.

Cloudflare rejected one timestamp per request because it "has huge processing and memory requirements". They keep two counters per client, for the current and the previous window. The previous count is weighted by how much of that window still overlaps the last minute. Over 400 million requests from 270,000 distinct sources, 0.003% of requests were wrongly allowed or rate limited.

Evidence
Cloudflare, "Counting things, a lot of different things", 2017-06-07. The same post gives an average difference of 6% between the estimated and the real rate. The memory table and the per-member bytes were measured on 2026-10-18 on Redis 8.10.1.

Correction. The phase called the sliding log "the best rate-limiter shape" that "never double-bursts". It is exact, but it stores one member per allowed request, so memory per client grows with the limit. A counter costs a few bytes and allows a bounded error.

For the coach, a fixed window or a two-counter window fits a shared cluster. The sorted set fits when the limit is small and exactness matters.

Try E9 from the lab now. With -limit 5 -window 2s, five calls pass, the burst is rejected, and calls pass again as old entries leave the window.

Go deeper: the platform's limiters, GitHub's fixed window, Airbnb's counter, and other algorithms
The platform's limiters. The platform runs three limiters, and none is a sorted set. One service uses a fixed window with INCR and EXPIRE in a Lua script. An older one pushes each timestamp with LPUSH and caps the list with LTRIM key 0 43199. It then counts timestamps in the last second, minute and hour, so it is a sliding log on a List. A third keeps its window in process memory, outside Redis.

GitHub. The API rate limiter is a fixed-window counter per client in a Lua script, on shards with one primary and several replicas. Users saw rejections while the response header said X-RateLimit-Remaining: 5000. The check read a replica that still held the old window, while the increment on the primary had already expired the key and started a new one. Their reason was that replicas do not expire data until the primary tells them to. The fix was to manage the window end in the application and reuse the first read for the response. Storing the reset time doubled their storage. Whether a replica read of a logically expired key returns nil in current Redis was not checked, and Phase 4 covers replicas.

Airbnb. The first limiter of their key-value store was a Redis counter per caller, returning HTTP 429 over quota. It counted a 1-row read the same as a 100,000-row scan, and it could not see one hot key that overloaded one shard. The new system adds a cost per request, load shedding based on latency, and hot-key detection.

Other algorithms. Token bucket, used by Stripe, and GCRA are two more choices. The choice is a design discussion. What is true in all of them is that an exact log costs memory per request, and a counter costs a few bytes with a bounded error.

Two details in the lab's limiter. The program sends the four steps in a TxPipeline, which is MULTI and EXEC, so they are atomic, although a code comment says otherwise. A rejected request stays counted until a separate ZREM, so concurrent callers can be wrongly rejected in that gap. The member is the timestamp, which can collide between clients. One Lua script that checks before it adds fixes both. The score is a float64 of nanoseconds, and at about 1.7e18 the spacing between floats is 256 ns, which is fine for this demo.

Evidence
GitHub blog, "How we scaled the GitHub API with a sharded, replicated rate limiter in Redis", 2021-04-05. Redis docs today: replicas "will not expire keys independently (but will wait for the DEL coming from the master)", expire.md lines 277-279. Airbnb tech blog, Mussel post, no date on the page. Lab code: sorted_set_ratelimit/main.go lines 61, 62 and 77, read, not run.

Timestamps as scores give a window over the past. The next section uses scores for the future, due times, and shows the other jobs one sorted set does.

## How do due times and decaying ranks use the same structure?

A score can be a future time, so the set becomes a schedule.

A timestamp score gave a window over the past. The coach also re-scores a transcript ten minutes after a learner edits it. Its trending board must also favour scenarios that are popular now, not last month.

A delayed queue is a sorted set whose score is the time each job should run. Workers read the members whose score is at or below the current time, and those are the due jobs. Because the set is always ordered, the next due job is always the first member.

- schedule: ZADD due <runAt> job:t9 stores the job with its run time.

- poll: A script reads the first member with a score up to now.

- claim: The same script removes it with ZREM.

- run: The worker that removed it runs the job.

A delayed queue. The read and the remove run in one script, so two pollers cannot take the same job.

Sidekiq, a widely used job system for Ruby, keeps its scheduled and retry jobs this way. The score is "the time at which it should be processed". A Lua script runs zrange key -inf now byscore limit 0 1 and then zrem, so the read and the remove are one unit. With two separate commands, two pollers could read the same due job, for the reason the first concept gave.

A score can also be an expiry time. The platform keeps a lock table where each member is a language and each score is the time its lock expires. One ZREMRANGEBYSCORE key -inf now then removes every expired lock at once, and the Go deeper block shows the commands.

The trending board combines a sorted set with a capped List. One service on the platform keeps a sorted set per company, with the asset as member and a running score.

- Each interaction runs ZINCRBY with a positive amount, and pushes the event onto a List that holds the last N events.

- When the List grows past N, the service pops the oldest event with LPOP.

- It then runs ZINCRBY with a negative amount for that event's asset, so old activity stops counting.

- The board reads the top items above a minimum score, with ZRANGE ... REV WITHSCORES.

So the sorted set ranks, and the List decides what "recent" means. The coach can rank scenarios the same way.

A sorted set orders by a score you choose, at O(log N) per write.

A sliding log at 1,000 per window for 100,000 clients needs about 9.5 GB.

Run MEMORY USAGE on your largest sorted set and divide by ZCARD.

Go deeper: the lock table with expiry as score, and where each pattern comes from
The lock table. The platform runs this lock table for translations. One key, such as job:inprogress:<id>, holds one member per language code, and each score is the time that language's lock expires.

key = job:inprogress:42
  member "fr" → score 1720000030    fr is locked until that time
  member "de" → score 1720000030

take or renew a lock    : ZADD key (now+ttl) <lang>
remove expired locks    : ZREMRANGEBYSCORE key -inf <now>
is fr still locked?     : ZSCORE key fr, present and greater than now
which languages are busy: ZRANGE key <now> +inf BYSCORE

A lock table with the expiry as score. One range removal clears every lock that a crashed worker left behind.

The score carries the expiry, so one ZREMRANGEBYSCORE key -inf now removes every expired lock in one atomic command. N separate lock keys would each need their own TTL. Three services on the platform share this layout, one of them in Java through Redisson's RScoredSortedSet. Taking a lock still needs care, because a check followed by a separate ZADD lets two workers both see the language as free. Phase 3 builds locks properly and shows where an expiring lock fails.

Its source. No public source describes the expiry-as-score lock table. It is the platform's own pattern. The phase showed it as a preview of Phase 3, done with a sorted set instead of SET ... NX.

The delayed queue on the platform. The plain delayed-queue form, score as run time, is not used on the platform today. The lock table is the form it runs. Sidekiq is the public example of the delayed queue.

Evidence
Sidekiq lib/sidekiq/scheduled.rb:13-20 at tag v8.1.7. The lock-table source search was done by the course audit and was not repeated.

The sorted set ends here. The coach's last need for ordered data is its scoring queue, and the next concept asks where a job is when a worker dies.

## Where does a job go when a worker pops it?

A pop deletes the job from Redis, so a crash loses it.

Sorted sets ordered the coach's data by a score. Its scoring queue needs order by arrival instead. Its worker pods restart on every deploy, so a pod can die in the middle of a job.

A Redis List is an ordered sequence of strings that you push to and pop from at either end. RPUSH to the tail and LPOP from the head gives a first-in, first-out queue. LPUSH and LPOP on the same end give a stack.

A
B
C
D
head tail
LPUSH → ← LPOP
← RPUSH RPOP →
FIFO queue: RPUSH at the tail, LPOP at the head. Stack: LPUSH and LPOP.

A List used as a queue. The producer pushes at the tail and the worker pops at the head.

Predict: a worker runs BLPOP jobs 5, gets a transcript job, and the pod is killed 2 seconds later. Where is the job now? Which one command change would let you recover it, and what second process do you then need?
The job is nowhere. The pop deleted it from Redis, and the only copy was in the dead pod's memory. Change the pop to BLMOVE jobs jobs:processing LEFT RIGHT, which moves the job into a processing list in the same command. That list holds the jobs a worker has taken but not finished. You then need a reaper, a process that pushes jobs back when they stay in the processing list too long.

The guess "Redis will give it to another worker" is reasonable if you have used Kafka or SQS, which wait for an acknowledgement. A List has no acknowledgement, so a pop is final.

A real worker needs to wait for work without wasting round trips.

- A worker that loops on LPOP gets nil from an empty queue, sleeps 100 ms and tries again. That is 10 wasted round trips per second per worker.

- BLPOP queue 5 blocks the connection inside Redis instead. Redis returns as soon as an item arrives, or nil after 5 seconds.

- In both cases, the pop removes the item from the List in the same command that returns it.

- Between the pop and the end of the work, the job exists only in the worker's memory. A crash, a kill or an out-of-memory error in that window loses it, and Redis has no record that it existed.

Sidekiq's basic fetch takes jobs with BRPOP. Its own documentation says the job is then removed from Redis. It adds, "If Sidekiq crashes while processing that job, it is lost forever." Its paid fetch strategy, called super_fetch, uses LMOVE to fix this.

Evidence
Sidekiq lib/sidekiq/fetch.rb:48 at tag v8.1.7: conn.blocking_call(TIMEOUT, "brpop", *qs, TIMEOUT). The quote is from the Sidekiq wiki page "Reliability".

Try E5 and E6 from the lab now. E5 shows jobs taken in push order, with BLPOP waking the moment job-late arrives. E6 pops one job, pretends the worker crashed, and LLEN returns 2, so j1 cannot be recovered.

Check it in your services. For each List queue, ask what happens if the worker dies between the pop and the end of the work. If losing that job is acceptable, the List is correct.

Go deeper: capped lists, the platform's queues, popping from several lists, and the List's layout
Capped lists. Lists have one more production use. LPUSH followed by LTRIM key 0 999 keeps only the newest 1,000 entries, a capped log of recent events. The trending board and the older rate limiter from the sorted-set sections both use a capped List. Reading the whole list with LRANGE 0 -1 is O(N), so on a huge list read a bounded range.

The platform's queues. One service's cache client on the platform wraps a List queue as three helpers, RPUSH, LPOP and LLEN. No production service uses BLPOP or BRPOP, because its workers drain with LPOP or take work from Kafka. Work that must not be lost runs on Kafka.

Several lists in one call. LMPOP and BLMPOP, since Redis 7.0, pop from the first non-empty list of several, and can pop more than one element. Use them when a worker serves several queues in priority order.

Layout. A List is a quicklist of listpack nodes, or one listpack when small, as the encoding section showed. A push or pop at either end is O(1). An index lookup in the middle walks nodes.

Evidence
lmpop.json at Redis 8.10.2: "since": "7.0.0".

A pop loses the job on a crash. The next section changes one command so the job stays in Redis until the work is done, and shows the case where even that fails.

## How does a List queue keep a job through a crash?

Move the job instead of popping it, and delete it only after the work.

A pop leaves the job only in the worker's memory. The coach cannot lose a scored transcript, so it needs the job to stay in Redis until a worker has finished it.

A processing list is a second List that holds the jobs workers are running now. LMOVE takes a job from the queue and pushes it onto the processing list in one atomic command. The worker deletes the job from the processing list after the work. So a crash leaves the job in Redis, where another process can find it.

- take: BLMOVE jobs jobs:processing LEFT RIGHT 5 moves one job.

- work: The worker scores the transcript.

- done: LREM jobs:processing 1 <job> deletes it.

- reaper: Jobs that stay too long are pushed back to jobs.

The reliable List queue from the Redis docs. A job is always in one of the two lists until a worker deletes it.

- The worker runs BLMOVE jobs jobs:processing LEFT RIGHT 5, so the job leaves the queue and enters the processing list in one command.

- If the worker crashes now, the job is still in jobs:processing.

- After the work, the worker runs LREM jobs:processing 1 <job>.

- A reaper checks the processing list for jobs that have stayed too long, and pushes them back to jobs. The docs describe this as a client that "may monitor the processing list for items that remain there for too much time".

- A job can now run twice, when a worker finishes but dies before its LREM. So this is at-least-once delivery, which means a job runs one or more times but is never lost, and the scoring code must be idempotent. A SET ... NX claim on the job ID, from the Strings section, is one way.

In a measured run, LMOVE q q:processing LEFT RIGHT followed by a simulated crash left q holding j2 j3 and q:processing holding j1. So a reaper could push j1 back. The reaper needs to know how long each job has waited. One way is to record the start time next to the job, which is inferred and not shown in the docs.

Correction. The phase said that "the moment you need don't lose it on crash, you've outgrown Lists". LMOVE or BLMOVE into a processing list is the documented reliable queue on a List. The older RPOPLPUSH and BRPOPLPUSH are deprecated since Redis 6.2.0 and replaced by these two.

The processing list has a cost, because moving a job is a write. Slack ran its job queue on Redis, about 1.4 billion jobs on busy days at a peak of 33,000 per second. Each dequeue moved a job from the pending queue to a list of in-flight jobs. Database contention slowed the jobs, the queue grew, and Redis reached its maximum configured memory, so new jobs could not be enqueued. Dequeue also needed memory to move a job, so the queue stayed stuck after the database recovered. Slack put Kafka in front of Redis as a durable buffer, with a relay that limits the rate of jobs into Redis.

Evidence
Slack Engineering, "Scaling Slack's Job Queue", 2017-12-06, updated 2020-06-25. The post also says that dequeuing "requires work proportional to the length of the queue", because of earlier choices of data structure. The LMOVE run was measured on 2026-10-18 on Redis 8.10.1. Docs: lmove.md lines 171-183.

After E6 in the lab, repeat it by hand with LMOVE in place of LPOP. Then run LRANGE q:processing 0 -1, and j1 is still there.

Go deeper: Discord's Redis queue under backlog
Discord. A Redis queue fed new messages to the workers that index them into Elasticsearch. When Elasticsearch nodes failed, the queue backed up. With too many queued messages, Redis CPU reached its limit and Redis dropped messages. Discord moved the queue to Google Cloud Pub/Sub, which guarantees delivery. After the rebuild, indexing throughput doubled, with no conditions given. Slack and Discord show the same limit from two sides. A queue in memory must stay small, because its memory and CPU are shared with everything else on that Redis.

Evidence
Discord blog, "How Discord Indexes Trillions of Messages", 2025-04-24.

A List can keep a job, but you build the reaper yourself. The next section looks at Streams, which keep delivered jobs for you, and asks what they still leave to you.

## What do Streams keep for you, and what do they leave to you?

A Stream remembers delivered jobs, but another consumer must claim them.

The reliable List needs a reaper that you write and run. The coach's team asks whether Redis Streams remove that work, since they keep a record of every delivered entry.

A Stream is an append-only log of entries, each with an ID that grows with time. A consumer group shares the entries of one Stream among several consumers, so each entry goes to one of them. Redis records each delivered entry in the group's pending entries list, or PEL for short. The entry stays there until the consumer confirms it with XACK, the command that acknowledges an entry. Another consumer can take over an entry that waits too long with XAUTOCLAIM, which claims entries idle for longer than a time you give.

- XADD s * job t9: The producer appends an entry.

- XREADGROUP GROUP g A ... >: Consumer A gets the entry, and the PEL records it as A's.

- A crashes: The entry stays in the PEL, owned by A.

- XREADGROUP GROUP g B ... >: Consumer B gets nothing, because the entry was already delivered.

- XAUTOCLAIM s g B 1000 0: B takes entries idle for over 1,000 ms.

- XACK s g <id>: B finishes and the PEL drops the entry.

A crashed consumer's entry, measured on the same Homebrew 8.10.1 build. It reaches B only through the claim step.

The measured run shows what Streams do and do not do by themselves.

- XREADGROUP ... > returns only "messages never delivered to other consumers so far", in the docs' words.

- So after A read entry 1 and crashed, B's XREADGROUP ... > returned nothing.

- XPENDING showed 1 entry, owned by A, so Redis still had it.

- XAUTOCLAIM s g B 1000 0 gave the entry to B after it had been idle for 1 second. XCLAIM does the same for named IDs.

- A claimed entry runs again, so delivery is at-least-once, and the consumer must be idempotent, as with the List.

So a Stream replaces the processing list, but you still run the claim step. Consumer groups also serve many processes, not one. A Stream is trimmed with MAXLEN or MINID, because it keeps every entry until you trim it. A PEL with entries that nobody acknowledges also grows without a limit.

Correction. The phase's table said Streams "redeliver on crash" and work "in one process". Pending entries are redelivered only when another consumer claims them with XCLAIM, or with XAUTOCLAIM, which arrived in Redis 6.2. Consumer groups work across many processes.

Harness built its event-driven design on Streams. Redis already served caching and locks there, and the expected volume was a few thousand messages per minute, so Kafka seemed too much. They used consumer groups with XACK, and XAUTOCLAIM to redeliver from crashed consumers. They capped memory with MAXLEN or MINID. The problems they named were memory cost and one failing message that blocked the head of the stream. Consumer lag was also hard to check without a custom monitor. Redis 7.0 added a lag field to XINFO GROUPS, which reports it.

A pop deletes the job, so move it to a processing list instead.

Streams keep a crashed consumer's entries pending until someone claims them.

Find your queue's pop command and ask where the job is after a kill.

Go deeper: Streams against Kafka, how a Stream is stored, and new Stream commands
Streams against Kafka. The platform runs durable work that must not be lost on Kafka, which already serves many services. Streams fit a smaller case, a self-contained durable queue that does not justify a Kafka topic. The queues and Kafka courses compare these in depth.

Layout. A Stream is a radix tree of listpack nodes. Each node starts with a master entry that holds the field names. Entries store their IDs as differences from the node's key, and skip the field names when they match the master entry. A new node starts at 4,096 bytes or 100 entries, from stream-node-max-bytes and stream-node-max-entries.

The PEL. Each PEL entry records the delivery time, the delivery count and the consumer. The delivery count lets you send a message that keeps failing to a dead-letter stream, instead of retrying it forever. Redis 8.10 also keeps the PEL in time order for fast claims.

New commands. XACKDEL and XDELEX arrived in Redis 8.2.0, and XNACK in 8.8.0. Valkey 9.1.2 has none of the three. Redis 8.6 added producer deduplication with the IDMP and IDMPAUTO arguments of XADD. They drop a duplicate add from a producer that retries. Deduplication does not change at-least-once delivery to consumers.

Evidence
Docs: develop/data-types/streams/_index.md, lines 443 and 644. xautoclaim.json, xackdel.json, xdelex.json, xnack.json at Redis 8.10.2, absent at Valkey 9.1.2 except xautoclaim. Layout: src/stream.h:36-53, 93-146 and src/t_stream.c:575-622 at 8.10.2. PEL time order: src/stream.h:108-113 at 8.10.2. IDMP: Redis 8.6.0 release notes, "XADD idempotency (at-most-once guarantee) with new IDMPAUTO and IDMP arguments". Harness blog, 2021-11-17. xinfo-groups.json at 8.10.2: 7.0.0 "Added the entries-read and lag fields". The Stream run was measured on 2026-10-18.

The coach now has safe updates, sized memory, ordered data and a queue that keeps its jobs. Its last need is a count of unique learners per scenario, and the next concept counts them without storing them.

## How do you count unique users without storing them?

A HyperLogLog keeps a fixed-size summary, not the members.

The queue now keeps its jobs. The coach's last need is a number on each scenario's page, the unique learners this week. A Set of learner IDs gives the exact number, but its memory grows with every new learner, on every scenario.

A HyperLogLog, or HLL, estimates how many distinct items were added to it. It does not store the items, so its size stops growing at a fixed maximum. You add with PFADD and read the estimate with PFCOUNT. PFMERGE combines counters, for example seven daily counters into one weekly counter.

MEMORY USAGE on the Homebrew 8.10.1 build with libc malloc, members user:1 to user:100000. The HLL estimated 99,471, which is 0.53% low.

Predict: one scenario reaches 1,000,000 unique learners. The Set of their IDs grows to about ten times its size at 100,000. What happens to the HLL's size and to its error?
The HLL stays at 12,304 bytes, and in a measured run its estimate was 999,674, 0.03% low. The Set would be about 44 MB, which is inferred from the measured 100,000-member Set.

The guess "the HLL grows too, more slowly" is reasonable for most data structures. An HLL has a fixed number of registers, so more items change the values in the registers, not their number.

The fixed size comes from a fixed array of small registers.

- Redis hashes each added item. Part of the hash picks one of 16,384 registers.

- Each register keeps the longest run of zero bits it has seen in the rest of the hashes. A long run is rare, so a register that saw one has probably seen many distinct items.

- Each register is 6 bits, so 16,384 registers take 12,288 bytes, plus a 16-byte header, 12,304 bytes in all.

- PFCOUNT combines the registers into one estimate. The standard error is 1.04 divided by the square root of 16,384, which is 0.81%.

- Adding the same item again picks the same register and the same run, so duplicates do not change the count.

A small HLL uses less than 12,304 bytes. Redis stores it in a sparse form, a run-length encoding of mostly empty registers, and converts it to the dense form above hll-sparse-max-bytes 3000.

Items added | STRLEN bytes | PFCOUNT

10 | 46 | 10

100 | 283 | 100

1,000 | 1,911 | 1,007

3,000 | 12,304, dense | 2,995

100,000 | 12,304 | 99,471, 0.53% low

1,000,000 | 12,304 | 999,674, 0.03% low

Measured on that same Homebrew build. The HLL is a plain String, so STRLEN reads its size.

Correction. The phase said an HLL uses "a fixed ~12 KB regardless". The docs say 12 KB in the worst case, and much less for an HLL that has seen few elements. The phase's lab result of 387x and 0.17% came from an earlier run that could not be repeated. A new run gave about 340x and 0.53% at 100,000 members.

Reddit counted unique views per post with HLLs. A post with 1 million unique viewers would need 8 MB as a set of 8-byte IDs. As an HLL it needed 12 KB, 0.15% of that space. The requirement was a count "within a few percentage points". A Kafka consumer filtered view events, a second one ran PFADD, and Cassandra stored each HLL in batches every 10 seconds. When Redis evicted a counter, they loaded it back with SET, which works because an HLL is a String.

Evidence
Reddit, "View Counting at Reddit", 2017-05-24, Krishnan Chandra, read from the web archive copy. Constants: src/hyperloglog.c:43, 68, 103-177, 194-202 and src/config.c:3608 at Redis 8.10.2. The 0.81% figure is in the HLL docs, line 26, and the worst-case wording at line 36. The table was measured on 2026-10-18.

An HLL has three limits. You cannot list its members, remove one, or test whether one was added. The 0.81% is a standard error, so some counters will be off by 2% or more. This is inferred from what a standard error means. Merging many counters also costs time, as the Go deeper block shows.

Try E10 from the lab now. It adds 100,000 unique users to a Set and to an HLL, and prints the memory of each and the error.

Go deeper: the cost of PFMERGE at Cloudflare
Cloudflare kept sliding-window counts per site in HLLs and merged them with PFMERGE. The first launch could not keep up with about 10,000 requests per second, because PFMERGE cost grew with the number of features times the window size. A cache that limited how often detection ran for each site and visitor pair raised throughput about 10 times.

Evidence
Cloudflare blog, "Lessons Learned from Scaling Up Cloudflare's Anomaly Detection Platform", 2021-03-12.

The HLL gives a count and nothing else. The next section shows the exact structures for the cases where you need to list, test or combine members.

## When do you need an exact count instead?

Pick the counting structure by the question the product asks.

An HLL answers "how many" and nothing more. The coach also wants a retention figure, the learners active on both Monday and Tuesday. The product may later ask for the list of those learners too.

A bitmap is a String used as an array of bits, where bit N stands for user number N. Setting a bit marks that user, and counting the set bits gives an exact count. Two bitmaps can be combined bit by bit on the server, so "active on both days" is one command.

- Must the product list, remove or test individual members?

- yes: Use a Set, or a bitmap when IDs are dense integers.

- no: Go to the next question.

- Is an error of about 1% acceptable?

- yes: Use an HLL, at most 12,304 bytes per counter.

- no: Use a bitmap for dense integer IDs, or a Set.

Choosing a counting structure. The first question is the one that decides most designs.

The bitmap commands work like this.

- SETBIT dau:mon 42 1 marks user 42 as active that day, and GETBIT reads one user's bit.

- BITCOUNT dau:mon returns the exact number of active users.

- BITOP AND on two daily bitmaps gives the users active on both days, and BITOP OR gives those active on either.

- The size follows the highest user number, not the number of users. Setting bit 1,000,000 makes the String 1,000,000 / 8 + 1 = 125,001 bytes, even with only 2 bits set.

So a bitmap fits dense integer IDs. For 10 million users, one day is 10 million bits, about 1.25 MB, and the docs give 100 million users in 12 MB. UUIDs or sparse IDs do not fit, because the bit position must be a small integer. A Set fits any ID and can list its members, but it stores every member.

So when someone proposes a large Set that the code only counts, ask the first question of the tree. An HLL or a bitmap usually answers it with far less memory.

Try E11 from the lab now. BITCOUNT returns 2, and STRLEN is about 125 KB, because bit 1,000,000 makes the String grow.

An HLL counts distinct items in at most 12,304 bytes, but cannot list them.

A Set kept only for SCARD used 340 times the memory of an HLL.

Find a Set your code only counts, and check whether anything reads its members.

Go deeper: Bloom filters and the other Redis 8 sketches
New approximate types. Redis 8.0 adds more approximate types. Bloom and Cuckoo filters answer "was this item added?" with a small chance of a wrong yes. Count-min sketch counts how often each item appears, Top-k keeps the most frequent items, and t-digest estimates percentiles. Not every build ships them, and the Homebrew 8.10.1 build used for this lesson did not, so test your own build first.

Razorpay stores the members of experiment segments as Bloom filters. In a test, 1 million IDs at a false-positive rate of about 1 in 100,000 used at most 3.3 MB. In production, at about 15,000 requests per second, the Bloom check had a p99 under 4 ms.

On the platform. The platform's core services use none of HyperLogLog, bitmaps or Streams today. Its unique counts are probably computed in the analytics and warehouse path instead, which is inferred from where they are absent.

Evidence
Redis 8.0.0 release notes, line 19, for the new types. Their absence in the Homebrew build was measured on 2026-10-18. The bitmap sizes are from the memory-optimization docs page. Razorpay Engineering, "Building Splitz", 2021-06-29, read from the blog's RSS feed. The absence of these types on the platform comes from the original phase.

That completes the five ideas. The next section collects them, and says what the next phase answers.

## What you can do now, and what comes next

The coach now has a Redis type for each of its six needs. Each choice has a cost you can state in commands and bytes.

- Atomic work follows the type. INCR, HINCRBY, SADD and SET ... NX read and change a value in one command, while GET then SET lost 79.8% of updates at 8 clients. When no command fits, EXEC runs a queue with nothing in between, but it never undoes a command. The sections on lost updates, transactions, Strings, Hashes and Sets taught it.

- Memory follows the encoding. A Hash stays a listpack up to 512 fields and 64-byte values, and one more field made it 3.9 times larger. The two encoding sections taught it.

- A sorted set orders by your score. It ranks, windows and schedules, and a sliding log costs about 95 bytes per request in the large form. The three sorted-set sections taught it.

- A pop deletes the job. BLMOVE to a processing list keeps it, and a Stream keeps it pending until someone claims it. The three queue sections taught it.

- An HLL counts without storing. It uses at most 12,304 bytes with 0.81% standard error, and a Set or bitmap is the exact choice. The two counting sections taught it.

You can now pick a type for a feature and say what it costs in round trips, safety and memory. You can also check that choice on a live key with OBJECT ENCODING and MEMORY USAGE.

One question is still open. The persona sits in Redis as a copy of data that lives in a database. Phase 2 answers how that copy stays correct when the database changes. It also answers what happens when a popular key expires and many requests miss at once.

## Lab: the exercises that teach Phase 1

The lab proves each idea with commands you run on a local Redis. It was not run for this lesson, so the Expected lines are the phase's own. Where a step is known to be wrong, a note under it says what to expect instead.

Open the lab: setup and E1 to E13
Setup:

cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d && docker exec redis-study redis-cli PING   # → PONG

Note for this lesson. That folder does not exist on this Mac. The lab code is in /Users/raghvendra.dhakar/Desktop/project/code/study-material/redis/code. Its docker-compose.yml pins redis:7.2. On 7.2 the encoding limits in this lesson are the same, but the field-TTL commands, JSON and the newer Stream commands are absent.

-  E1 c1 Strings: the three personalities.

- Run: docker exec redis-study redis-cli SET blob '{"a":1}'; ... INCR counter; ... SET flag 1 NX EX 30; ... SET flag 2 NX EX 30

- Expected: the second SET flag ... NX returns nil (key exists) — the claim was already taken.

- Teaches: blob vs atomic counter vs atomic flag, all on the String type.

-  E2 c1, c2 String vs Hash, measured.

- Run: go run ./phase01_data_structures/string_vs_hash

- Expected: field update = 4 ops (String) vs 1 (Hash); encoding = listpack.

- Teaches: when the JSON-blob-String costs you and the Hash pays off.

Note for this lesson. The program prints "4 ops" for the String update and says the Hash limit is hash-max-listpack-entries=128. Expect the String path to be 2 round trips, a GET and a SET, plus client work, and the real cost is the lost update between them. The real default is 512. The program does not print bytes, so run MEMORY USAGE sess:string:u42 and MEMORY USAGE sess:hash:u42 by hand to compare the two layouts.

-  E3 c1 Break it — WRONGTYPE.

- Run: docker exec redis-study redis-cli SET s hello; docker exec redis-study redis-cli LPUSH s x

- Expected: WRONGTYPE Operation against a key holding the wrong kind of value.

- Teaches: the value's type constrains the legal commands — the keyspace is typed.

-  E4 c1 Hash field counters.

- Run: docker exec redis-study redis-cli HINCRBY post:1 views 1; ... HINCRBY post:1 likes 1; ... HINCRBY post:1 views 1; ... HGETALL post:1

- Expected: views=2, likes=1 — two independent atomic counters in one object.

- Teaches: HINCRBY = per-field atomic counter without separate keys.

-  E5 c4 List FIFO + blocking worker.

- Run: go run ./phase01_data_structures/list_queue -jobs 8

- Expected: jobs consumed in exact push order; BLPOP wakes the instant job-late is pushed.

- Teaches: RPUSH/LPOP FIFO and why BLPOP beats busy-polling.

Note for this lesson. This program does not crash a worker. E6 shows the crash, and the reliable-queue section shows the LMOVE form to try next to it.

-  E6 c4, break-it Break it — the List queue loses a job on crash.

- Run: docker exec redis-study redis-cli RPUSH q j1 j2 j3; docker exec redis-study redis-cli LPOP q (pretend the worker crashes here) then docker exec redis-study redis-cli LLEN q

- Expected: LLEN=2 — j1 is gone, unrecoverable. No ack, no redelivery.

- Teaches: exactly where a List queue's guarantees end (→ Streams/Kafka).

-  E7 c1 Set uniqueness + algebra.

- Run: go run ./phase01_data_structures/set_dedup

- Expected: dup absorbed (SCARD=3), SINTER/SUNION/SDIFF results, SSCAN over 10k.

- Teaches: dedup, the invalidate-all fan-out, server-side set math.

-  E8 c3 Sorted Set leaderboard by hand.

- Run: docker exec redis-study redis-cli ZADD lb 100 raj 250 dana 175 sam; ... ZREVRANGE lb 0 -1 WITHSCORES; ... ZREVRANK lb sam; ... ZINCRBY lb 200 raj; ... ZREVRANGE lb 0 0

- Expected: dana top; after +200, raj (300) becomes top.

- Teaches: ZADD/ZREVRANGE/ZREVRANK/ZINCRBY — the whole leaderboard feature.

Note for this lesson. ZREVRANGE still works, but it is deprecated since 6.2.0. The current form is ZRANGE lb 0 -1 REV WITHSCORES.

-  E9 c3 Sorted Set sliding-window rate limiter.

- Run: go run ./phase01_data_structures/sorted_set_ratelimit -limit 5 -window 2s -n 12 -gap 200ms

- Expected: 5 allowed, burst rejected, then allowed again as the window slides.

- Teaches: score=timestamp = exact sliding window; no boundary double-burst.

Note for this lesson. With one client, the output should match the Expected line, which is inferred from reading the code. With several clients at once, two problems appear. A rejected call keeps its member until the program's later ZREM, which can push other callers over the limit. Two clients with the same timestamp also share one member. The sorted-set limiter section and its Go deeper block explain both.

-  E10 c5 HyperLogLog vs Set memory.

- Run: go run ./phase01_data_structures/hll_vs_set -unique 100000

- Expected: ~0.1–0.8% error, ~387x memory ratio (5442 KB vs 14 KB).

- Teaches: when to trade exactness for a flat 12 KB.

Note for this lesson. Expect a ratio near 340x, not 387x. On Redis 8.10.1 with libc malloc, the Set used 4,361,836 bytes and the HLL 12,822, with 0.53% error. Inside the container the allocator is jemalloc, so expect different bytes and a similar ratio. The program sends about 200,200 commands in one pipeline, and the Redis docs advise batches of about 10,000.

-  E11 c5 Bitmaps for daily-active flags.

- Run: docker exec redis-study redis-cli SETBIT dau:2026-07-13 42 1; ... SETBIT dau:2026-07-13 1000000 1; ... BITCOUNT dau:2026-07-13; ... STRLEN dau:2026-07-13

- Expected: BITCOUNT=2; STRLEN ~125 KB (bit 1,000,000 forces the string to grow).

- Teaches: one bit per user; BITCOUNT = active count; watch the sparse-id memory cost.

Note for this lesson. STRLEN should print exactly 125001, which is 1,000,000 / 8 + 1.

-  E12 c2 Encoding cliff.

- Run: docker exec redis-study redis-cli DEL h; docker exec redis-study redis-cli HSET h f v; docker exec redis-study redis-cli OBJECT ENCODING h (→ listpack). Then add a >64-byte value: docker exec redis-study redis-cli HSET h big "$(python3 -c 'print("x"*100)')"; docker exec redis-study redis-cli OBJECT ENCODING h

- Expected: listpack → hashtable after the big value.

- Teaches: the automatic, one-way encoding upgrade and its memory jump.

-  E13 c1, break-it Transactions: no rollback, EXECABORT, WATCH, and retries under contention.

- Every command in E13 was run on 2026-10-19 against Homebrew Redis 8.10.1 on port 6581, with no persistence. It was an x86_64 build under Rosetta 2 on an Apple M4 Pro. The course container runs redis:7.2 instead.

- Warning: part c empties databases 14 and 15, and part e creates and deletes the ACL user p1tx. Run it on a server you own.

- Run: go run ./phase01_data_structures/tx_watch -self-test

- Expected: seven ok lines and self-test passed, with no server. The lock-step check prints aborts=18 want 18.

- Then run: go run ./phase01_data_structures/tx_watch

- Expected: part a prints tx:n=1 tx:b=done → no rollback: true and then yet tx:n=2 tx:b=again. Part b prints EXECABORT and EXISTS tx:c=0. Part c prints every row matches the rule: true. Part d prints the table from 1.9, with 0 aborts at 1 client and 17.48 aborts per commit at 32 clients. Against the plain INCR writer it prints commits=0 gave up=100. Part e prints EXEC → [s3cret] on Redis 8.4.0 to 8.10.1.

- On Redis 8.10.2, part e printed a NOPERM entry instead. That was run on a native arm64 build of the 8.10.2 tag, as 1.9 shows. On redis:7.2 it should also print NOPERM, because the bug arrived in 8.4.0. That is inferred from the release note and was not run.

- Optional, for the AOF part of 1.9: ./phase01_data_structures/tx_watch/aof_cut.sh <free port> midcmd. It starts its own server with the AOF on, and it refuses port 6379. Expected: start 2: tx:after=, because the write made after the first start is lost. With boundary instead of midcmd, it prints start 2: tx:after=1.

- Break it: delete the s.Watch(c.key) call in step, then run -self-test again. Expected: FAIL d no lost update under contention: final=3 commits=12 want 12.

- If it fails: cannot reach Redis means the container is down, so run docker compose up -d. An error from SWAPDB means the server has fewer than 16 databases.

- Teaches: what EXEC promises, the two times an error can happen, what invalidates a watch, and what retries cost.

Note for this lesson. Unlike E1 to E12, E13 was run, so its Expected lines are measured output. "The table from 1.9" is the retry table in the transactions section above.

## Checkpoint questions

Answer each one in your own words before you open its sketch. Every answer uses only this lesson.

Open the eight questions
Q1. A teammate stores "modules assigned to a user" as a JSON array in a String. Every assignment runs GET, unmarshal, append, marshal and SET. Two assignments race. Walk the exact order that loses one, name the structure that fixes it in one atomic command, and write that command.

Answer sketch
A runs GET and gets [m1]. B runs GET and also gets [m1]. A appends m2 and runs SET [m1, m2]. B appends m3 and runs SET [m1, m3], so m2 is gone. A Set fixes it, because SADD user:u42:modules m2 adds inside one command and also removes duplicates. A List with RPUSH also works if order matters and duplicates are allowed.

Q2. You need a rate limit of 100 requests per minute per company. Compare a fixed window with INCR and EXPIRE against the sorted-set sliding log of E9. Show the input that lets the fixed window allow about 200 requests in about 2 seconds, and explain why the sliding log cannot. Then argue why a team might still choose the fixed window, by counting bytes and commands per request.

Answer sketch
Send 100 requests in the last second of minute 1 and 100 in the first second of minute 2. Each window counts only its own 100, so 200 pass in about 2 seconds. The sliding log counts the real last 60 seconds, so request 101 in that span is rejected. But the log stores up to 100 members per company, about 33 bytes each in the listpack form, and runs four commands per request. The counter is about 30 bytes and two commands. On a shared cluster with many companies, the counter or Cloudflare's two-counter window is often the better trade.

Q3. "How many unique learners opened this course this month?" Design it with a Set and with a HyperLogLog. Give the memory for 5 million uniques in each. State the one question whose answer decides between them.

Answer sketch
A Set used 4,361,836 bytes for 100,000 members, so 5 million is about 218 MB, inferred by scaling. The HLL stays at 12,304 bytes, with about 0.81% standard error. The deciding question is whether the product must list, remove or test individual learners. If it only shows a count, use the HLL.

Q4. Walk through a sorted-set lock table for key job:inprogress:42. French translation starts: which score does ZADD write? A duplicate "translate fr" event arrives: what tells you French is still locked? French finishes. Then a German worker crashes and leaves its de member behind. Which single command removes the stale lock, and why can a plain Set not do it?

Answer sketch
ZADD key (now+ttl) fr, so the score is the time the lock expires. The duplicate event runs ZSCORE key fr, and a score greater than now means French is locked. On finish, ZREM key fr. ZREMRANGEBYSCORE key -inf now removes de once its expiry has passed, together with every other expired lock. A plain Set has no score, so it cannot tell an old member from a live one, and its members cannot expire one by one.

Q5. A colleague wants to store each session as 6 separate String keys, such as sess:u42:token and sess:u42:ip, so fields can expire on their own. Give two reasons one Hash is better. Then say whether the one case where separate keys used to win still exists.

Answer sketch
First, a small Hash is a listpack, so it avoids six top-level key costs. Second, HGETALL reads every field in one round trip, and HSET with several fields writes them in one atomic command. Separate keys used to win when fields needed their own TTL. Since Redis 7.4, HEXPIRE gives fields their own TTL, and Valkey has it since 9.0, so that case is gone on current versions.

Q6. You call HGETALL on a hash in a hot path. Over three months, with no deploys, p99 latency climbs. Name two things that could be growing, how you confirm each, and the fix for each.

Answer sketch
The number of fields can grow, so HGETALL does more O(N) work on the single thread. Confirm with HLEN and SLOWLOG, and fix by bounding the fields, reading only needed fields with HMGET, or using HSCAN. The hash can also cross a listpack limit, more than 512 fields or a value over 64 bytes, and become a hashtable. Confirm with OBJECT ENCODING and MEMORY USAGE, and fix by splitting the hash into buckets under the limit.

Q7. Design a "trending scenarios" feature: the top 10 per company, weighted toward recent activity. Name the structure that holds the ranking, and the commands that record a view and read the top 10. Then say how a scenario's score falls as its activity gets old.

Answer sketch
A sorted set per company, with the scenario as member. A view runs ZINCRBY trend:c7 1 s42, and the board reads ZRANGE trend:c7 0 9 REV WITHSCORES. For decay, push each view onto a List capped at N. When the List grows past N, LPOP the oldest view and run ZINCRBY with -1 for its scenario. Another design scales all scores down on a schedule. Compare which one is simpler to reason about when a view is counted twice.

Q8. A wallet service moves credits between wallet:{u42}:main and wallet:{u42}:bonus with a WATCH loop. It watches both keys, reads both, then sends MULTI, DECRBY main 30, INCRBY bonus 30 and EXEC. (a) In a load test, 16 workers move credits for the same user, and the loop retries forever. p99 rises from 1 ms to 400 ms with no errors. Use E13 part d to explain why, and give two fixes. (b) A teammate wraps the call in "if err != nil, retry". The bonus key once held a Hash by mistake, so INCRBY failed with WRONGTYPE. What did the retry do to main? (c) The keys move to a cluster, and someone drops the hash tag from one key name. What does the client see?

Answer sketch
(a) All 16 workers read, and in each round only one EXEC commits. E13 measured 4.59 aborts per commit at 8 clients and 17.48 at 32. The worst increment at 8 clients needed 316 to 664 attempts. Each attempt is 3 round trips, so p99 grows with the attempts, and no error appears because the loop never gives up. Fix 1: one Lua script or Function that checks the balance and moves the credits on the server, with no retry. Fix 2: cap the retries with a random backoff and return an error at the cap. (b) No rollback: DECRBY main 30 ran, and INCRBY replied WRONGTYPE inside the EXEC array. go-redis then returns that error. Each retry ran DECRBY again, and INCRBY failed again, so the loop never stopped. main lost 30 on every attempt, and bonus gained nothing. Only TxFailedErr means nothing ran. (c) WATCH on keys in two slots fails with CROSSSLOT. Without the watch, EXEC checks all queued keys and replies CROSSSLOT, and Redis discards the transaction. A key whose slot is on another node gets MOVED at queue time, so EXEC replies EXECABORT. With go-redis v9.5.1, ClusterClient.Watch refuses keys in two slots before it sends anything. A TxPipeline with no watch instead splits the commands by slot into two transactions. No error appears, and the move is no longer one unit.

## Cheatsheet

Open the cheatsheet
PICK THE STRUCTURE
  whole opaque object, read and written together  → STRING (JSON blob) + TTL
  atomic counter, fixed-window limit              → STRING: INCR + EXPIRE (one script)
                                                    or INCREX k EX s ENX (Redis 8.8+)
  atomic claim, idempotency, start of a lock      → STRING: SET k v NX EX s   (SETNX is deprecated)
  change value, keep TTL                          → SET k v KEEPTTL
  object with fields changed one at a time        → HASH: HSET / HGET / HDEL / HINCRBY
  a TTL per field                                 → HEXPIRE (7.4), HSETEX / HGETEX (8.0)
  queue where a lost job is acceptable            → LIST: RPUSH + BLPOP
  queue that must keep the job                    → LIST: BLMOVE to processing + LREM + reaper
  durable queue with consumer groups              → STREAM: XREADGROUP + XACK + XAUTOCLAIM
  uniqueness, membership, "the group of X"        → SET: SADD / SISMEMBER / SMISMEMBER
  in both, either, one but not the other          → SET: SINTER / SUNION / SDIFF, SINTERCARD
  ranking, leaderboard                            → ZSET: ZADD + ZRANGE ... REV + ZREVRANK
  exact sliding window, small limits              → ZSET: score = timestamp
  delayed jobs                                    → ZSET: score = run time, pop in one script
  count distinct, about 1% error is fine          → HYPERLOGLOG: PFADD / PFCOUNT / PFMERGE
  one flag per dense integer ID                   → BITMAP: SETBIT / BITCOUNT / BITOP

O(N) COMMANDS THAT BLOCK → CURSOR OR BOUNDED FORM
  KEYS → SCAN      HGETALL (huge) → HSCAN      SMEMBERS (huge) → SSCAN
  ZRANGE (huge) → bound it; a large LIMIT offset still walks the set
  LRANGE 0 -1 (huge) → read a bounded range

ATOMIC INSIDE ONE COMMAND
  INCR / INCRBY / DECR   HINCRBY   ZINCRBY   ZADD   SADD   SET ... NX   LMOVE

ENCODING LIMITS, Redis 8.10.2 and Valkey 9.1.2 defaults
  hash   : hash-max-listpack-entries 512, hash-max-listpack-value 64  → hashtable
  zset   : zset-max-listpack-entries 128, zset-max-listpack-value 64  → skiplist
  set    : set-max-listpack-entries 128, value 64; integers: set-max-intset-entries 512
  list   : list-max-listpack-size -2 (8 KB per node)                   → quicklist
  hashes, sets, zsets never convert back; lists convert back below half the limit
  check  : OBJECT ENCODING key     measure: MEMORY USAGE key
  strings: int / embstr / raw; Redis 8 embeds only if key + value + headers fit 64 B, 128 B on Apple arm64

MEMORY NUMBERS (measured, Redis 8.10.1, libc malloc)
  hash 512 → 513 fields      5,958 → 23,445 B (3.9x)
  zset member                33 B listpack, about 94 to 105 B skiplist
  100,000 pairs as keys      4.7 MB;  as 1,001 listpack hashes 0.77 MB
  HLL                        at most 12,304 B, 0.81% standard error
  Set of 100,000 IDs         4.4 MB, about 340x the HLL

DEPRECATED → CURRENT
  SETNX → SET NX      HMSET → HSET      RPOPLPUSH / BRPOPLPUSH → LMOVE / BLMOVE
  ZREVRANGE → ZRANGE ... REV      ZRANGEBYSCORE → ZRANGE ... BYSCORE

TRANSACTIONS
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
  cluster           every key in one slot, else CROSSSLOT → {tag} keys, see KEY NAMES
  AOF / replicas    writes of one EXEC are wrapped in MULTI/EXEC; failed cmds absent
  AOF cut in a cmd  8.10.2 keeps the open MULTI → later writes lost → BGREWRITEAOF
  ACL               8.4.0-8.10.1 skip the key re-check at EXEC → upgrade to 8.10.2
  pick              one command > SET IFEQ (8.4+) > MULTI > WATCH (capped) > script

KEY NAMES
  type:sub:id, tenant ID value inside the key, one prefix per service
  {tenant} hash tag puts a tenant's keys on one cluster slot (Phase 4)

## Sources

Go deeper: what this phase covered, the versions, and how long it takes
The original phase. It was a survey of eight topics, in this order. Strings, hashes, lists, sets, sorted sets, then Streams with HyperLogLog and bitmaps, then encodings, then key naming. This lesson keeps every part of it that is correct. It groups them under the five ideas above, because one idea connects them. The type decides which work Redis does inside one command, and the size of the value decides how Redis stores it.

Versions. Current Redis is 8.10.2. Valkey 9.1.2 is the main project that continues from the Redis code. The Linux Foundation runs it, and it started from Redis 7.2.4. The lab's container still pins redis:7.2. Where a command or a default differs between these, the section says so.

Time. The phase planned 3 to 5 days for reading and labs. It is the phase you will open most often later, because "which structure?" is a decision you make every week.

How the numbers are labelled. A number that says "measured" comes from a run on Redis 8.10.1 on an Apple M4 Pro, with the libc allocator. Production Linux builds use jemalloc, so absolute byte counts differ there. Ratios and the sizes where an encoding changes do not depend on the allocator. That last point is inferred from how the allocator works, not measured on Linux.

Evidence
Redis 8.10.2 was released on 2026-09-17, from the GitHub release page. Valkey 9.1.2 is the latest stable tag on 2026-10-18. The measurements ran on 2026-10-18 on a fresh Redis 8.10.1 Homebrew server, an x86_64 build under Rosetta, macOS 26.6, port 6481, no persistence, loopback client.

Open the sources
Redis source and docs

- Redis 8.10.2 config.c: the encoding limits, hll-sparse-max-bytes, verified.

- Redis 8.10.2 redis.conf: the encoding settings and list-max-listpack-size -2, verified.

- Redis 8.10.2 t_list.c: lists convert back below half the limit, verified.

- Redis 8.10.2 object.c and config.h: the cache-line rule for embedded strings, verified.

- Redis 7.2.0 object.c: the old 44-byte embstr rule, verified.

- Redis 8.10.2 server.h: skip-list constants, verified.

- Redis 8.10.2 hyperloglog.c: 16,384 registers of 6 bits, the sparse form, verified.

- t_zset.c, t_hash.c and t_set.c at 8.10.2: where each type converts, verified.

- Valkey 9.1.2 config.c: the same encoding defaults in Valkey, verified.

- Redis 8.0.0 release notes: JSON and the probabilistic types in Redis, verified.

- Redis 8.10.2 release: the current version, verified.

- Redis 7.0.0 release notes: scripts are no longer replicated as whole scripts, verified.

- Redis 8.6.0 release notes: IDMP and IDMPAUTO for XADD, verified.

- Memory optimization docs: why small encodings are O(N) and still fast, hash bucketing, bitmap sizes, verified.

- LMOVE docs: the reliable queue pattern with a processing list, verified.

- Transactions docs: MULTI, EXEC and WATCH, and no rollback, verified.

- Streams docs: XREADGROUP >, the PEL, XAUTOCLAIM, verified.

- HyperLogLog docs: 12 KB worst case and 0.81% standard error, verified.

- ZRANGEBYSCORE docs: a large offset still walks the set, verified.

- Sorted sets guide: leaderboards and ranges, from the phase.

- Data types overview and command reference: every command with its cost, from the phase.

Transactions

- Redis 8.10.2 multi.c: EXEC, the dirty flags, what touches a watched key, the ACL re-check, verified.

- Redis 8.10.2 server.c: queue-time rejection, the MULTI wrapper for the AOF and replicas, the BUSY rule, verified.

- Redis 8.10.2 aof.c: a cut MULTI block at load, verified.

- Redis 8.10.2 release notes: security fix #15673, verified.

- Redis PR #15673: why queued commands kept key access, verified.

- Valkey 9.1.2 multi.c: the same rules, the ACL re-check, verified.

- Valkey 9.1.2 release notes: PR #4342, the AOF fix for a cut inside a MULTI block, verified.

- Multi-key operations docs: one slot for MULTI, WATCH and scripts in a cluster, verified.

- Redis blog, no rollbacks: the argument against rollback, a vendor source.

- redis-py v8.1.0 client.py: transaction() retries with no limit, verified.

- redis-py issue #566: a request to cap WATCH retries, closed, verified.

- node-redis PR #3506: a reconnect lost the WATCH, verified.

- SwordFS issue #454: retry limit exceeded under WATCH contention, a small open-source project, verified.

Production cases

- Instagram, hash buckets: 300 million pairs in under 5 GB, verified from the archive copy.

- Reddit, view counting: HLL per post, 12 KB against 8 MB, verified from the archive copy.

- Slack, job queue: a full Redis could not dequeue, verified.

- Cloudflare, counting: two counters instead of a log, 0.003% wrong, verified.

- GitHub, sharded rate limiter: fixed window in Lua, the replica read problem, verified.

- Sidekiq fetch.rb, scheduled.rb and Reliability wiki: BRPOP loses a job on a crash, sorted sets for scheduled jobs, verified.

- Twitter, Hybrid List: a list of small ziplists, from a secondary summary.

- Grab, Lua and field order: two encodings returned fields in different orders, verified.

- DoorDash, feature store: hashes and compression, 298 GB to 112 GB, verified from the archive copy.

- Cloudflare, anomaly detection: PFMERGE cost grew with the window, verified.

- Harness, Redis Streams: consumer groups, XAUTOCLAIM, trimming, verified.

- Discord, message indexing: a Redis queue dropped messages under backlog, verified.

- Lyft, geospatial at scale: a sorted set per geohash cell, verified from the slides.

- Razorpay, Splitz: Bloom filters, 1 million IDs in 3.3 MB, verified.

- AWS, ElastiCache for Valkey 8.0: 32 bytes saved per key, verified, a vendor source.

- Airbnb, adaptive traffic management: a Redis counter per caller and its limits, verified.

From the phase, not checked

- Sorted sets for leaderboards: the leaderboard, limiter and delayed-queue patterns, not checked.

- Hashes for memory-efficient storage: the blob against hash argument, not checked. Its thresholds may be the old ones.

- Phyllo, sorted-set rate limiter: the recipe E9 follows, not checked.

- thoughtbot, HyperLogLogs in Redis: an intuition for HLL, not checked.

- Redis ziplist glossary: the old compact encoding, not checked. Prefer src/listpack.c at a tag.

- Redis in Action, Josiah Carlson, chapters 3 and 4: all structures with use cases, a book from the phase.

Measurements. Every number marked measured came from scripts run for this lesson on Redis 8.10.1, an x86_64 Homebrew build under Rosetta on an Apple M4 Pro, macOS 26.6, libc malloc, a fresh server on loopback, 2026-10-18.
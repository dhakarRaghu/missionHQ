In Phase 3, Distributed locking, you put a lock per account in Redis, so only one worker changes an account at a time. That phase showed that the lock can disappear when the primary fails over, and it did not explain why. This phase studies that failover, and everything around it. The running case is your agent service's Redis, this lesson's own example. It holds the session state of each conversation and a cache of tool results. It also holds a lock for each agent run, built like the lock of Phase 3. It runs as one primary, the node that takes every write, with two replicas, the nodes that keep a copy of its data. When the primary dies, a monitor runs a failover, which promotes one replica to be the new primary.

- 02:10:00 The primary's host loses power. In its last second it acknowledged 40 session writes and one run lock.

- 02:10:00 + Every write to the primary fails. How long this lasts depends on who notices the death and who decides.

- after failover A replica is the new primary. Some writes that clients saw acknowledged are not on it.

- 02:40 The old host comes back as a replica. It reconnects, and the new primary must send it what it missed.

- months later The sessions outgrow one node, so you split them across several primaries. Some requests now fail with redirects.

The running case. Times and counts are an illustration, not measured.

Each line of that night is one question this phase answers. How much did the disk keep, and which acknowledged writes are gone? Why can a reconnecting replica take the primary down? How long did writes fail? After the split, how does a request find its key?

What you must know, in five claims. Each one is taught below, in this order.

- What a crash loses depends on the kind of crash, and an empty restarted primary empties its replicas. State the loss for a process kill, a power loss and a restart.

- WAIT counts the replicas that have your write, but a failover can still lose that write. Bound the loss, and size WAIT for each environment.

- A replica that misses more writes than the primary keeps in memory copies the whole dataset again, and that copy can crash the primary. Size the primary's buffers for your write rate.

- Failover time is mostly the wait before a node may be declared dead, and in a cluster the other primaries vote. Predict how long writes fail, and whether failover happens at all.

- When the keys are split across several primaries, no node passes a command on a key to another node, so the client must know where each key lives. Read the redirect errors, and choose one primary or a cluster.

## What you bring from Phases 0 to 3

  One main thread

Redis runs commands one at a time on one main thread. So one slow step, such as a large copy of memory, delays every client of that node. Phase 0 showed this with a 2-second command.

  A cache entry is a copy

In Phase 2 a cache-aside read went to the database on a miss and stored the result in Redis. Losing that entry costs a miss, not data. A session or a lock kept only in Redis is different, because no other copy exists.

  Hash tags

In Phase 1 you wrote keys such as {<companyId>}key. The part in braces decides where the key is stored in a cluster. This phase gives the mechanism behind that naming rule.

  The lock at failover

In Phase 3 the primary crashed before the lock reached the replica. The replica was promoted, and a second client took the same lock. This phase explains how the copy reaches the replica, and why that race exists.

This phase needs the first idea for the cost of a snapshot, and the second to decide what you may lose. It needs the last two for the copies on the replicas and for routing in a cluster.

### The new words this phase uses

One Redis node keeps every key in the memory of one machine. In the running case that is 40 GB of sessions, locks and cache on a 64 GB host. So one power loss stops every write, and the data survives only if another node holds a copy. One node also caps the data at the memory of one machine.

Redis answers the first problem with copies on other nodes, and the second by splitting the keys across several primaries. Seven words name the parts of those two answers, and almost every section below uses them.

  WordWhat it isWhere you meet it

  replicationThe primary sends every write it runs to each replica, as one stream of bytes. Each replica applies the stream in order.INFO replication on any node

  offsetA position in that stream, counted in bytes. The primary's offset says how much it has sent, and a replica's offset says how much it has applied.master_repl_offset, and offset= for each replica, in INFO replication

  replication lagHow far a replica is behind the primary. Redis reports it in whole seconds since the replica last confirmed its offset.lag= for each replica, in INFO replication

  Redis ClusterThe Redis system that splits the keys across several primaries, so each one holds a share of them.the cluster docs, and CLUSTER INFO

  cluster modeThe setting that makes a node part of a Redis Cluster. ElastiCache names its groups cluster mode enabled or cluster mode disabled.CLUSTER INFO, and the ElastiCache console

  masterThe word Redis Cluster uses for a primary. Redis also prints it as the role of a primary that is not in a cluster.role:master in INFO replication, and CLUSTER NODES

  shardOne master with its replicas. Each shard holds one share of the keys, so each added shard adds memory, writes and CPU.CLUSTER SHARDS, and the ElastiCache console

A first try shows three of these words in real replies. The first command comes from this phase's lab, and the other two come from the local runs behind this lesson.

# the primary of the lab's replication setup, with two replicas
INFO replication
role:master
connected_slaves:2

# one primary and one replica: block until 1 replica has the last write
WAIT 1 1000
(integer) 1                    # returned after 39 ms

# a six-node Redis Cluster, on a node that does not hold the key foo
GET foo
(error) MOVED 12182 127.0.0.1:17103

- The first reply calls the node a master, and connected_slaves:2 counts the replicas that receive its replication stream.

- The second shows a replica confirming its offset. WAIT is the command that blocks until a number of replicas have your writes. It returned 1, because the one replica reported an offset past the write.

- The third shows cluster mode. The node does not hold the key, so it answers with an error that names the node which does. The routing sections below explain that reply.

Evidence
The INFO replication lines are the expected output that the phase's lab gives for its replication setup. That lab needs Docker, and it was not run for this lesson. The WAIT and GET replies come from local runs on redis-server 8.10.1 on 127.0.0.1. The WAIT run used one primary with one replica, and the GET ran on a node that did not own slot 12182. The prompt of redis-cli is left out.

## What does a crash lose, and which crash?

At 02:10 the primary lost power. Before you ask what the replicas have, ask what the primary's own disk kept, because that is what a restart can load.

Redis keeps the whole dataset in memory. Persistence writes a copy of it to disk, so a restarted process can load the data again. Redis has two kinds. How much a crash loses depends on the copy you chose and on what failed: the Redis process only, or the whole machine.

- RDB, short for Redis database, is Redis's compact binary file format for a whole dataset. An RDB snapshot is one such file, with the whole dataset at one moment.

- The AOF, the append-only file, is a log of every write command, which Redis replays at start.

An AOF write survives a power loss only after fsync, the system call that moves the kernel's copy of a file to the disk. The setting appendfsync decides how often Redis calls fsync, and its default value, everysec, means about once a second.

- command runsthe write changes memory

- write(2)AOF bytes go to the kernel page cache, before the reply

- replythe client sees OK

- fsynca background thread, about once a second

- disknow survives a power loss

The path of one write with appendfsync everysec. A process kill after step 2 keeps the write. A power loss before step 4 loses it. From src/server.c and src/aof.c at Redis 8.10.2.

Predict: your primary runs AOF with everysec. You kill the process with kill -9 right after an OK. On another day the machine loses power right after an OK. How much does each crash lose?
The kill loses nothing in the normal case. Redis had already handed the bytes to the kernel before it replied, and the kernel still writes them to disk after the process dies. The power loss can lose about the last second. On a slow disk both crashes can lose more, as the steps below show. The usual guess is "at most one second in every crash", because that is how the docs summarise everysec. That summary is about the machine failing, not the process.

The two kinds of persistence work in these steps.

- For an RDB snapshot, Redis forks, which starts a child process with a copy of its memory. BGSAVE, the command that saves a snapshot in the background, starts the fork, and so does a save <seconds> <changes> rule. The child process writes dump.rdb while the parent keeps serving clients.

- The fork uses copy-on-write: parent and child share memory pages, and the kernel copies a page only when the parent changes it. So memory grows during a save by every page that clients write in that time.

- A crash with RDB only loses every write since the last finished snapshot. With save 60 1000 that can be a minute of writes, or more on a quiet node.

- For the AOF, each write command is added to a buffer in memory. Before Redis sends the replies of a loop turn, one pass of the event loop over all clients, it calls write(2) for that buffer. The code comment says this "must be done before handleClientsWithPendingWrites".

- With everysec, the appendfsync default, a background thread calls fsync about once a second. With always the main thread calls fsync before replies, and with no Linux flushes about every 30 seconds.

- If the previous fsync is still running, Redis postpones the next write(2) for up to 2,000 ms, and then counts it in aof_delayed_fsync. Replies still go out during that time, which is inferred from the order of the code. So on a slow disk even a process kill can lose up to about two seconds of acknowledged writes. Those bytes are still in Redis memory, not in the kernel. A power loss can lose more than two seconds, because no new fsync starts while the slow one runs. Both effects are inferred from src/aof.c and were not measured.

  What failedRDB, save 60 1000AOF, everysecAOF, always

  The process, by kill -9 or a crashevery write since the last snapshotnothing in the normal case, up to about 2 s on a slow disknothing

  The machine, by power loss or a kernel crashevery write since the last snapshotabout 1 s, and 2 s or more on a slow disknothing that was acknowledged

  Cost on each writenone, but a fork per snapshotone fsync a second, in the backgroundone fsync before each reply

A local run showed the first row of the AOF column. With AOF everysec, 50,000 keys and one more SET were written, and the process was killed with kill -9 at once. After the restart all 50,001 keys were there, and aof_delayed_fsync was 0. A process kill cannot show the one-second window, because only a lost page cache shows it.

Evidence
Code order verified in src/server.c at tag 8.10.2, lines 2053 to 2057, before line 2104. The src/aof.c comment at lines 1459 to 1461 says the single write "will save us against the server being killed", but not against "power problems". The 2,000 ms postpone is in src/aof.c lines 1438 to 1452, and the latency docs say Redis will "delay the write(2) call up to two seconds". The local run used redis-server 8.10.1, an x86_64 Homebrew build under Rosetta 2, outside Docker. It ran on one idle local disk on 2026-10-18. A loss under a slow disk was not measured.

The phase said everysec loses at most about one second. True now, at Redis 8.10.2: a process kill loses nothing in the normal case. On a slow disk a process kill can lose up to about two seconds, and a power loss can lose more.

The phase said an AOF restart is slower because Redis replays the log. Since Redis 7.0 the AOF is several files, and its base file is in RDB format by default. So most of the restart loads a snapshot, and only the newer part is replayed.

Go deeper: the defaults, multi-part AOF, rewrite, fork cost, and online backups
Defaults at Redis 8.10.2

- The default save rules are 3600 s and 1 change, 300 s and 100 changes, and 60 s and 10,000 changes, from redis.conf lines 499 to 506.

- appendonly no, appendfsync everysec and appenddirname "appendonlydir" are the AOF defaults.

- stop-writes-on-bgsave-error yes makes the primary refuse writes when a background save fails.

- disable-thp yes turns off transparent huge pages for the Redis process. The latency docs also advise turning them off for the whole machine.

- Redis logs a warning at start if vm.overcommit_memory is not 1, because a fork of a large process can then fail.

Multi-part AOF

Since Redis 7.0 the AOF is a directory with a manifest file. It holds one BASE file, one or more INCR files and some HISTORY files. With aof-use-rdb-preamble yes, the default, the BASE file is in RDB format. A local run created appendonly.aof.1.base.rdb and appendonly.aof.1.incr.aof.

Rewrite

An AOF rewrite first opens a new INCR file and then forks. The child writes a new BASE, and new writes go to the new INCR file. Auto rewrite starts when the AOF grew by 100% since the last rewrite and is at least 64 MB. After three failed rewrites in a row, Redis waits longer before the next try, up to 60 minutes.

What a fork costs

A fork copies the page tables of the process, and the main thread stops while it does. The Redis latency docs measured about 9 to 13 ms per GB on modern machines. Old Xen virtual machines took 239 ms per GB, and Linode took 424 ms per GB. Read latest_fork_usec in INFO stats, and current_cow_peak for the copy-on-write bytes of the last child.

The MemoryDB paper measured the same effect on a 2 vCPU machine with 16 GB of RAM, maxmemory 12 GB and 20 million keys of 500 bytes. A fork took about 12 ms per GB, and the slowest request rose to 67 ms during BGSAVE. When copy-on-write pushed the machine into swap, the slowest request passed 1 second, and throughput fell close to zero past 8% swap. Its advice is a dataset at most half of the RAM, or snapshots at a quiet hour.

Online backups

Redis 8.10 adds the BACKUP command family, which takes an online backup on top of the multi-part AOF. The persistence docs describe it in "Online backups with the BACKUP command family".

Seeing a power loss

A test of the power-loss window needs a tool that drops the page cache, such as LazyFS. The elite-storage course, Phase 1, builds that test for its own log.

One node's disk now has a clear loss window for each crash. The next section asks what happens to the replicas when that node restarts with no disk copy at all.

## Why can a restart empty the replicas as well?

The disk decides what one node keeps after a crash. With replicas, the bigger risk is what the replicas do when the primary comes back before anyone promotes them.

Your primary runs with persistence off, as many caches do, because it saves the fork and the disk writes. Suppose a supervisor such as systemd or Kubernetes restarts the process 2 seconds after it crashes. The monitor in a self-hosted setup is Sentinel, a separate process that watches the primary and promotes a replica. It waits 30 seconds by default before it declares the primary dead, so here it never acts.

Each primary names its history of writes with a replication ID, a random string. A replica that reconnects sends that ID and its offset, and so asks the primary to continue its copy from there. When the primary does not know the ID, the replica asks for a complete copy of the primary's dataset. This copy is a full sync, also called a full resync.

- crashthe primary holds 10,000 keys, and both replicas hold them too

- auto restartno file to load, so the primary starts empty with a new replication ID

- replicas reconnectthe ID is unknown to them, so they ask for a full copy

- full syncthey load the empty dataset and flush their old data

Persistence off plus an automatic restart. All three nodes end with 0 keys, and no failover happened.

The steps run in this order.

- The primary starts with no RDB file and no AOF, so its dataset is empty.

- It also starts a new replication ID, because it keeps no record of its old history.

- The replicas reconnect to the same address. Their copy belongs to the old ID, so the primary cannot continue it, and each replica asks for a full copy.

- A replica that receives a full copy first deletes its own data, and then loads the copy. The copy is empty.

  10,000 → 0keys on the replica

  about 5.3 sfrom restart to empty replica

  0failovers

A local run reproduced it with one primary, save "" and appendonly no, and one replica. After 10,000 keys were written, the primary was killed with kill -9 and restarted at once. The replica kept 10,000 keys for about 4.8 s and then dropped to 0 at about 5.3 s, and its log says "Flushing old data". The 5-second wait matches repl-diskless-sync-delay 5, which the next concept explains.

Evidence
The Redis replication docs describe this case in "Safety of replication when master has persistence turned off". The local run used the same build, port 17001, on 2026-10-18. The delay default is in redis.conf 8.10.2, line 691.

The fix follows from the order of events. Either the primary has persistence, or it must not restart by itself. With persistence off, a dead primary must stay down until the monitor promotes a replica, so the data on the replicas survives.

### What this means on ElastiCache

On ElastiCache you cannot turn the AOF on. Its parameter appendonly is marked "Modifiable: No", and AWS says Multi-AZ and AOF "are mutually exclusive". A reboot of a primary that you start yourself does not fail over. AWS says the primary "is cleared of data", and the replicas clear their copy too. So your protection against a crash is the replica, and a snapshot backup is only for a disaster.

ElastiCache for Valkey 9.0 and later adds clusters with durability enabled. They write to a Multi-AZ transaction log. AWS states zero loss for synchronous writes and up to 10 seconds of loss for asynchronous writes.

The phase said cluster-mode ElastiCache has no AOF. True now: no ElastiCache Redis OSS cluster can set appendonly, in either cluster mode. Valkey 9.0 and later can use durability-enabled clusters instead.

Go deeper: teams that chose no persistence, a managed outage, and the promotion of an empty replica
No persistence on purpose

Lyft ran more than 2,000 Redis instances behind Envoy, at 25 million requests a second at peak, with no replication, no AOF and no RDB. Losing an instance lost its data, and the team accepted that because the data refreshed often. Each service owned its cluster, so one loss stayed inside one service. Source: RedisConf18, "2,000 Instances and Beyond", https://www.slideshare.net/RedisLabs/redisconf18-2000-instances-and-beyond .

GitHub went the other way for data that existed nowhere else. It turned off persistence and moved that data to GitHub::KV, a key-value store on MySQL with expiry. The reasons were the cost of running persistence, the team's MySQL skills and disk latency on large writes. Source: https://github.blog/engineering/infrastructure/moving-persistent-data-out-of-redis/ .

A managed service restarting empty

The Redis Cloud outage showed the same effect at the scale of a service. A weekly software update put a cluster management process into an endless loop, and five nodes failed, a majority. Databases without persistence came back at once but empty. Databases with persistence came back slowly, the largest last. DNS delete throttling also slowed the recovery. Source: https://redis.io/blog/february-8th-outage-post-mortem/ .

An empty replica can be promoted

The MemoryDB paper lists the same risk from the other side. Redis can promote a replica that is behind, and in the worst case it promotes an empty replica, so the shard loses all its data. MemoryDB allows only a replica that has seen the latest log entry to become the leader.

Backups on a managed cluster

Snapshot backups on ElastiCache are set per replication group, with a retention in days and a time window. One platform in this course's use cases ran three groups with retention of 3 days, 1 day and none. On the group with none, a total loss had nothing to restore. Those values come from the phase and were not checked.

  A process kill, a power loss and an empty restart lose different amounts.

  Replicas plus persistence off plus auto restart can wipe every copy in seconds.

  On your staging primary, type CONFIG GET save and CONFIG GET appendonly, then check whether its supervisor restarts it.

A failover that promotes a replica avoids the empty restart. The next section shows that it can still lose writes the primary acknowledged.

## What does an OK from the primary promise?

A failover keeps the replicas' data, unlike the empty restart. The open question is how current that data was at 02:10, when the primary died.

Your agent service writes a run lock with SET, gets OK, and starts the run. Five milliseconds later the primary's host loses power. Whether the lock exists on the new primary decides whether a second worker can start the same run.

Redis replication, the stream of writes from the primary to its replicas, is asynchronous, as the lock race of Phase 3 showed. The primary runs a write, replies OK to the client, and then streams the write to its replicas, which apply it a little later. So for a short time the primary has acknowledged a write that no replica has. If the primary dies in that time and a replica is promoted, the write is gone. The command WAIT lets a client block until a number of replicas have received its writes.

- SET lockthe primary changes memory

- OKthe client is told, before any replica has it

- streamthe write goes to each replica

- ACK offseteach replica reports its position about once a second

- WAIT returnsthe count of replicas that reported a position past the write

One write and its acknowledgements. The loss window is the time between OK and the replica that will be promoted receiving the stream.

Predict: you add WAIT 1 100 after each lock SET, and it returns 1. The primary has two replicas. It dies, and Sentinel promotes a replica. Is the lock now safe?
It is much safer, but not safe. One replica has the lock in memory, and the other may not. Sentinel skips replicas that were disconnected too long, and then sorts by replica-priority before it looks at the replication offset. So a replica without the lock can win if its priority is better. The usual guess is "WAIT returned 1, so the write is on a replica, so it survives", which assumes the promoted replica is the one that answered. The WAIT docs say that a write sent to several replicas can still be lost.

Each part of the guarantee comes from one step of the mechanism.

- The primary adds each write to the replication stream and replies to the client. The reply does not wait for any replica.

- Each replica reports its offset, the number of stream bytes it has applied, with REPLCONF ACK about once a second. That is why the lag field in INFO replication moves in whole seconds.

- WAIT numreplicas timeout blocks only the calling client. It asks the replicas for an ack in the same loop turn. It returns when enough replicas report an offset past its writes, or when the timeout ends.

- WAIT returns a count and changes nothing else. A low count does not undo the write, and other clients can already read the write before any replica has it.

- At failover the promoted replica's history wins. The old primary rejoins as a replica of it, and drops every write the new primary does not have.

The setting that limits the loss is min-replicas-to-write. With min-replicas-to-write N and min-replicas-max-lag M, the primary refuses writes while fewer than N replicas have a lag of at most M seconds. A primary cut off from its replicas stops accepting writes after about M seconds. So it cannot collect many writes that a failover will drop. The docs call this a bound on the loss, and say consistency is "not ensured".

  The belief. OK means the write is safe. WAIT 2 returning 2 means a failover cannot lose it. Replicas plus a monitor keep every acknowledged write.

  What happens. OK means the primary has it in memory. WAIT counts copies at that moment. Only min-replicas-to-write limits the loss, and it does that by refusing writes.

Jepsen measured the size of this loss in a network partition. A five-node Redis setup with Sentinel took 2,000 writes during a partition and acknowledged 1,998 of them. Only 872 survived, so 56% of the acknowledged writes were lost. The old primary on the minority side kept accepting writes, and dropped them when it rejoined as a replica.

Evidence
Kyle Kingsbury, "Jepsen: Redis", 2013-05-18, https://aphyr.com/posts/283-call-me-maybe-redis : "2000 total 1998 acknowledged 872 survivors". The test used the Sentinel of Redis 2.6.13, so the numbers are old. The mechanism is still documented in the cluster spec, section "Write safety", and in the Sentinel docs, which mark a client as "C1 (writes will be lost)". The WAIT page, section "Consistency and WAIT", says "it is possible to still lose a write synchronously replicated to multiple replicas".

A local run checked min-replicas-to-write. With min-replicas-to-write 2 and one replica, SET failed with "NOREPLICAS Not enough good replicas to write.". With min-replicas-to-write 1 and min-replicas-max-lag 2, the replica was frozen with SIGSTOP. SET worked at lag 1 and 2, and failed at lag 3 and 4. Local run, redis-server 8.10.1, 2026-10-18.

The phase said WAIT shrinks the loss window "to near-zero" for that write. True now, in the current WAIT docs: WAIT makes loss less likely, and a write on several replicas can still be lost.

Go deeper: waiting for the disk too, read-only replicas, the minority side of a cluster, and what zero loss costs
Waiting for the disk too

WAITAOF is a command like WAIT that also waits for the fsync of the AOF. Its form WAITAOF numlocal numreplicas timeout exists since Redis 7.2.0. It waits until the write is fsynced to the AOF on the primary, when numlocal is 1, and on numreplicas replicas. numlocal needs appendonly yes. Replicas report the fsynced position in the same message as the offset: REPLCONF ACK <offset> FACK <aof-offset>. It protects against a power loss on the nodes that answered, and it has the same failover limits as WAIT.

Replicas are read-only

By default a replica refuses writes with READONLY You can't write against a read only replica., so every write goes to the primary. A replica can serve reads, and those reads can be up to the replication lag behind.

The minority side of a cluster

The cluster spec describes the same loss for Redis Cluster. A master on the minority side of a partition keeps accepting writes until cluster-node-timeout passes. Those writes are lost when the majority side has promoted its replica. A short Redis University summary says the minority "will not accept any client write requests", which is a simplification. The spec is the source to follow.

What zero loss costs

Amazon MemoryDB sends the replication stream into a multi-AZ transaction log and replies only after the log commits. Reads of keys with uncommitted changes wait too. On r7g.16xlarge, write latency was p50 under 1 ms and p99 up to 3 ms for Redis, against p50 3 ms and p99 up to 6 ms for MemoryDB. Write throughput was about 300K operations a second for Redis and up to 185K for MemoryDB. The setup was Graviton3, engine 7.0.7, 100-byte values, 1 million keys, no pipelining and TLS off. Source: https://www.amazon.science/publications/amazon-memorydb-a-fast-and-durable-memory-first-cloud-database .

Two claims the phase made that have no source

The phase said replication lag is "usually under 1 ms" in one AZ. No source supports it, and the lag field moves in whole seconds, so it cannot show it. The phase also named "unclean promotion". That is not a Redis term, and none of the docs uses it.

WAIT gives more safety only when the replicas you ask for exist. The next section shows what it costs when they do not.

## What does WAIT cost when a replica is missing?

WAIT raises safety only while the replicas you ask for are connected. When fewer exist, nothing but the timeout can end the call.

A use case from the platform of Phase 0 shows the cost. A service called WAIT 2 with a 2-second timeout after each write, so that each write was on two replicas. Production had two replicas, and the call returned in under 100 ms. A test environment had one replica, so WAIT 2 could never be met. Every write there took the full 2 seconds, and the fix brought test latency down to about 15 ms.

  The same code in two environments

  Step 2: both environments get an ack from one replica within 100 ms. Production also gets the second ack and moves on.

  Step 3: the test environment waits, because only the timeout can end a WAIT that asks for more replicas than exist.

  Step 4: at 2,000 ms WAIT returns 1, and the next write starts. This repeats on every write.

  Illustration from the use case's numbers, not measured.

The cost follows from how WAIT ends.

- WAIT returns when the count of replicas past your offset reaches N, or when the timeout ends, whichever comes first.

- With N larger than the number of connected replicas, the count can never reach N, so every call lasts the full timeout.

- The call blocks the client's connection, so a service that writes in a loop runs at one write per timeout.

- The return value shows the problem, because it is lower than N on every call. Code that ignores it never notices.

A local run measured both cases on one primary with one replica. WAIT 1 1000 returned 1 in 39 ms. WAIT 2 1000 returned 1 in 1,058 ms, the timeout plus about 35 ms of process start for redis-cli. The use case's numbers, 2,000 ms and about 15 ms, come from the phase and are internal, so they were not checked.

The fix is to stop assuming the replica count, in one of these ways.

- Read connected_slaves from INFO replication at start, and ask WAIT for at most that many replicas.

- Set N per environment in configuration, so production asks for 2 and a one-replica environment asks for 1 or skips WAIT.

- Log or alert when WAIT returns less than N, because a low count means the safety you designed for is not there.

- Give WAIT a timeout that fits the request's latency budget, because the timeout is the worst case on every call.

The deeper rule is that topology differs between environments, and code must read it. The last section of this phase lists the commands that show the topology of any Redis.

  OK means the primary has it, and WAIT only counts the copies.

  A fixed WAIT 2 where one replica exists adds the full timeout to every write.

  Run E4, then E6, and compare the WAIT time with and without the replicas.

WAIT assumes the replicas are connected and current. The next section asks what a replica must do to become current again after its link drops.

## When does a reconnecting replica copy everything again?

WAIT and the failover both assume the replicas are current. A replica stops being current every time its link to the primary drops, so the cost of catching up matters.

At the evening peak your primary takes about 20 MB of writes a second. A network blip cuts one replica's link for 3 seconds. When the link comes back, the replica must get those 3 seconds of writes, and the primary decides how.

The replication ID from the empty-restart case names the primary's history. The offset, the byte position in the stream, says how far a replica got. The primary also keeps the backlog, a fixed-size buffer with the most recent part of its stream. A reconnecting replica sends its ID and offset with the command PSYNC. If the missing bytes are still in the backlog, the primary sends only those bytes, which is a partial resync. If not, it does a full sync. It forks and sends a whole RDB of the dataset. Until the replica has loaded it, new writes wait in the replica's output buffer, the memory for bytes not yet sent to a client.

- Does the replica's replication ID match the primary's?

- nofull sync: fork, send the whole dataset

- yescheck the offset

- Are the missing bytes still in the backlog?

- yespartial resync: the primary answers +CONTINUE and sends only the gap

- nofull sync

Predict: the primary takes 20 MB/s of writes, the replica's link drops for 3 seconds, and the backlog has its default size. Partial or full sync? What changes on Valkey 9.1.2?
Full sync on both. The gap is 20 MB/s × 3 s = 60 MB. The Redis 8.10.2 default backlog is 1 MB, and the Valkey 9.1.2 default is 10 MB, so neither still holds the start of the gap. The usual guess is "a 3-second blip is harmless, the replica catches up", which is true only while the backlog covers the gap. To survive this blip with a partial resync, the backlog must be larger than 60 MB.

  Partial or full sync?

  Write rate, MB/s
  Link down, seconds
  Backlog, MB
  Missing stream  · result  · backlog needed

The calculator uses the lesson's formula, missing bytes = write rate × time the link was down. It ignores the bytes that were already in the backlog before the drop, so treat the result as a lower bound.

The decision runs in these steps.

- Every write adds bytes to the stream and moves the primary's offset, master_repl_offset in INFO replication.

- The backlog keeps the last repl-backlog-size bytes of the stream. It is 1 MB by default in Redis 8.10.2, and 10 MB in Valkey 9.1.2. The minimum is 16 KB.

- The replica sends PSYNC <replication ID> <offset>. The primary accepts it when the ID matches and the offset is still inside the backlog.

- After a failover the new primary keeps the old ID as a second ID, up to the offset where it took over. So the other replicas can continue with a partial resync from the new primary.

- Any other case is a full sync. It costs a fork on the primary and a transfer of the whole dataset, which the next section measures.

The phase described only the old full sync. Redis 8.0 added RDB channel replication. For a full sync the replica opens a second connection, and the fork child streams the RDB on it. The main connection streams new writes at the same time. The replica buffers those writes, so the primary does not. Valkey has a similar mode, dual-channel-replication-enabled, which is no by default in 9.1.2.

Evidence
Replication docs, sections "How Redis replication works" and "Replication ID explained". Defaults from src/config.c: Redis 8.10.2 line 3585, Valkey 9.1.2 line 3463. The second ID is replid2, valid up to second_replid_offset, in src/replication.c lines 1018 to 1042. RDB channel replication: Redis 8.0.0 release notes lines 111, 202 and 231. A local replica log shows "PSYNC is not possible, initialize RDB channel". Valkey default from valkey.conf 9.1.2, line 846.

Go deeper: diskless sync, the RDB channel in detail, compression, and backlog sizing
Diskless sync

repl-diskless-sync yes is the default, so the fork child streams the RDB to the replica's socket and writes no file on the primary. The primary first waits repl-diskless-sync-delay 5 seconds, so that more replicas can join the same transfer. That is the 5-second pause in the empty-restart run. repl-diskless-load disabled is the default on the replica, so the replica writes the RDB to its disk before it loads it.

The RDB channel in detail

The primary answers +RDBCHANNELSYNC <client-id> to start the second connection. It is used only when the hidden setting repl-rdb-channel and repl-diskless-sync are both on. The replica's buffer limit is replica-full-sync-buffer-limit, and its default 0 means it uses the replica output buffer hard limit. Valkey's dual-channel mode needs diskless sync too. Its primary sends $ENDOFF:<offset> <replid> <db> <client-id> on the RDB channel.

Compression

Redis 8.10 can compress the replication stream with zstd, through repl-compression. Its default is 0, which means off.

Sizing the backlog

Size the backlog for the longest link drop you want to survive: write rate × that time, plus a margin. Measure the write rate by reading master_repl_offset twice, 10 seconds apart. The backlog is one shared buffer for all replicas, so a larger one costs its size once. repl-backlog-ttl 3600 frees it an hour after the last replica disconnects.

History

Redis 2.6 always did a full sync after a disconnect. Partial resync arrived in Redis 2.8. The Twilio case in the next section ran on 2.6.

A full sync looks like a slow catch-up. The next section shows how its fork and its buffers can take the primary down.

## How can a full sync take the primary down?

A full sync costs the primary a fork and a buffer of new writes for the replicas that are syncing. Both use memory, and the primary may not have it.

In the running case the dataset is 40 GB on a node with 64 GB of RAM. A full sync during the evening peak forks that 40 GB process while clients keep writing. The steps below show where the memory goes.

- The fork shares every memory page between the primary and the child. Each page a client changes during the transfer is copied, so the primary's memory grows with the write rate and the transfer time.

- While the RDB is on its way, an older-style primary buffers every new write for that replica in the replica's output buffer.

- The limit client-output-buffer-limit replica 256mb 64mb 60 drops the replica when its buffer passes 256 MB, or stays above 64 MB for 60 seconds. It is the same in Redis 8.10.2 and Valkey 9.1.2.

- A dropped replica asks for a full sync again, which starts a new fork. When each transfer takes longer than the buffer can cover, this repeats. The Redis blog describes this endless replication loop.

- Several replicas that lose the link together need a full sync together. The 5-second diskless delay lets them share one fork. Since Redis 7.0 they also share one replication buffer in memory, but the primary checks the output buffer limit for each replica.

  A 96 GB server during a replication fork

The figure shows the memory of Stack Overflow's Redis server when a planned move started replication to a new server. The fork's copy-on-write pages filled the 6 GB of headroom, and Redis crashed. In the post's words, "all of our websites promptly went offline". The sites came back on the new server with an empty cache.

The Twilio billing incident started with the same path and ended with the empty restart from the first concept.

  StepWhat happenedThe mechanism

  1The network between the billing replicas and the primary failedevery replica lost its link at once

  2All replicas asked for a full sync together, and the primary overloadedfull sync, on Redis 2.6, which had no partial resync

  3Engineers restarted the primary to remove the loada restart, used as the fix for a slow primary

  4It read a wrong config, tried to load an AOF file that did not exist, and "dropped all balance data"a restart with no data to load starts empty

  5The same config made it a replica of itself, so it was read-onlya replica refuses writes

  6Balances read as zero, so auto-recharge charged customer cards again and againthe application trusted Redis as the only copy

Twilio restored balances from a separate relational store, replaced the cluster and fixed the config. It disabled restarts of the primary, so recovery now promotes a replica. If a balance is missing or cannot be written, the system no longer charges or suspends. The post gives 1.4% of customers in its summary and 1.1% in its timeline.

Evidence
Twilio, "Billing Incident Post-Mortem: Breakdown, Analysis and Root Cause", incident on 2013-07-18: https://www.twilio.com/en-us/blog/company/communications/billing-incident-post-mortem-breakdown-analysis-and-root-cause-html . antirez, "Twilio incident and Redis": https://www.antirez.com/news/60 . He thinks memory pressure from many replica buffers is the likely cause of the slowdown, which is his inference.

Nick Craver, "Stack Overflow: How We Do App Caching - 2019 Edition": https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/ . About 70 GB at planning, about 90 GB at the move, 96 GB of RAM, Redis 2.x. The 6 GB of headroom "went fast".

The output buffer default is in redis.conf 8.10.2, line 2475. That a dropped replica asks again is inferred from the config text. Redis blog, "The Endless Redis Replication Loop": https://redis.io/blog/the-endless-redis-replication-loop-what-why-and-how-to-solve-it/ .

Three settings decide whether a full sync is survivable. First, the backlog decides how often a full sync happens. Second, free memory decides whether the fork's copied pages fit. Third, the replica output buffer must hold the writes of one whole transfer. With RDB channel replication in Redis 8, that last buffer moves to the replica, through replica-full-sync-buffer-limit.

Go deeper: the loop seen at GitLab and Snap, and a test of many resyncs
GitLab

At 13:50 UTC the replica output buffer limit was exceeded on GitLab.com's Redis. Both replicas lost their link and started a full sync, and they were back in sync at 13:55. The same happened at 14:52, with sync complete at 14:58. The fix doubled the replica buffer limit with config set client-output-buffer-limit, to 8 GiB hard, 4 GiB soft and 180 seconds. The issue does not state the old limit or the dataset size. Source: https://gitlab.com/gitlab-com/gl-infra/production/-/issues/706 .

Snap

Snap moved its caches from KeyDB to Valkey, about 30 caches a week. For high-memory workloads the replication buffer could fill before the snapshot finished, and the full sync then repeated without end. The source is a vendor summary of a Snap talk: https://www.gomomento.com/blog/why-snap-was-willing-to-fork-and-why-they-still-came-back/ .

A test with many resyncs

antirez tested AOF on, 10 million keys, 70,000 writes a second and four replicas that resynced again and again. He saw no visible latency problem. So a full sync is not always harmful. The harm comes when memory or buffers run out.

Sizing rules

- Keep free memory for copy-on-write. The MemoryDB paper advises a dataset at most half of the RAM, or forks at a quiet hour.

- Set the replica output buffer above write rate × transfer time. At 20 MB/s and a 60-second transfer, that is 1,200 MB, far above the 256 MB default. This is arithmetic, not a measured value.

  A gap longer than the backlog costs a fork and a full copy.

  A short link drop on a 1 MB backlog can overload or crash a busy primary.

  Read master_repl_offset twice, 10 seconds apart, and compare the write rate with repl-backlog-size.

The replicas now hold a recent copy, and a resync can keep them current. The next section asks who decides that the primary is dead, and how long that takes.

## How long do writes fail after the primary dies?

The replicas hold a recent copy, and a resync keeps them current. At 02:10 somebody still has to decide that the primary is dead and choose a replica, and every write fails until that is done.

A failover has four steps. Something detects that the primary stopped answering, the monitors agree that it is dead, one replica is chosen and promoted, and clients move to it. Detection must wait for a timeout, because a slow node and a dead node look the same for a while. So the timeout, not the vote, sets most of the time that writes fail.

The clearest case to measure is Redis Cluster, where each master owns a share of the keys and forms one shard with its replicas. The nodes check each other over the cluster bus, a second TCP port on every node, at the client port plus 10,000. When a master dies, its replicas ask for votes in order of rank, a place set by how recent each copy is.

Predict: an open-source Redis Cluster runs with default settings, three masters with one replica each. You kill one master with kill -9. The vote between the nodes takes milliseconds. How long until a write to that master's keys succeeds?
About 24 seconds in a local run. Writes failed for about 23 s, then the nodes answered CLUSTERDOWN, and the first write succeeded at 24.0 s. The replica's log shows "Start of election delayed for 857 milliseconds (rank #0...)", and then "Failover election won" 24 ms after the election started. The usual guess is 2 to 5 seconds, because that is what a managed service reports. The default cluster-node-timeout of 15 seconds comes first, before any vote.

  Killing one master of a default Redis Cluster

  Step 1: other nodes wait cluster-node-timeout, 15 s, before they mark the master PFAIL. Then their reports must reach a majority of masters by gossip. In this run that took about 8 s more, inferred from the first CLUSTERDOWN reply at about 23 s.

  Step 2: the replica with rank 0 waits 500 ms plus a random 0 to 500 ms, here 857 ms.

  Step 3: the other masters vote, and the replica wins in 24 ms.

  Step 4: the replica owns the dead master's keys, and writes succeed again.

  To scale, from one local run with a poll every 0.25 s. Treat the total as about 20 to 25 s.

Each step of the Redis Cluster failover has a rule in the source.

- Every node pings the others over the cluster bus. It also pings any node that has not answered for half of cluster-node-timeout.

- A node that gets no answer for cluster-node-timeout, 15,000 ms by default, marks the peer PFAIL, a possible failure in its own view.

- Pings carry these reports to other nodes. When a majority of masters report the peer within two times the timeout, a node marks it FAIL and tells every node.

- Each replica of the failed master waits 500 ms plus a random 0 to 500 ms. It adds 1,000 ms for each place in its rank. Rank 0 is the replica with the most recent offset, so it asks first.

- The replica asks every master for a vote, and needs a majority of them. The vote itself takes milliseconds, because it is one message and one answer.

- The winner takes over the dead master's keys and announces it. Clients that ask the old address get an error, and must find the new master.

  15 sCluster detection timeout, default

  30 sSentinel detection timeout, default

  about 24 sfirst good write, local Cluster run

  a few secondsElastiCache, as AWS states

Sentinel, the monitor of the running case, waits down-after-milliseconds, 30,000 ms by default, before it starts. So with default Sentinel settings, writes to a dead self-hosted primary fail for at least 30 seconds. AWS runs the failover itself on ElastiCache, and says writes resume in "typically just a few seconds". AWS does not describe how it detects the failure, so its timeout cannot be compared here.

Evidence
Timeout default: src/config.c 8.10.2 line 3574, the same in Valkey 9.1.2. Election delay: src/cluster_legacy.c 8.10.2 lines 4459 to 4470. Majority and FAIL: lines 1935 to 1961. Sentinel default: sentinel.conf 8.10.2 line 133. AWS: https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/AutoFailover.html . The local run used redis-server 8.10.1, six nodes on 127.0.0.1, all defaults, on 2026-10-18. The Sentinel time was not measured.

The phase titled this "the 2 to 5 seconds after a primary dies". True now: that holds only for ElastiCache. Open-source Redis Cluster defaults gave about 24 s in a local run at 8.10.1, and Sentinel's detection alone is 30 s by default.

Go deeper: the cluster bus timers, stale replicas, and lowering the timeout
Timers

- clusterCron runs every 100 ms. Once in 10 calls it picks 5 random nodes and pings the one with the oldest answer.

- Each ping carries gossip about max(3, nodes/10) other nodes, plus every node in PFAIL.

- Every heartbeat carries a bitmap of the sender's slots, 2 KB in size, which the next concept explains.

- Failure reports stay valid for two times cluster-node-timeout.

- An election times out after max(2000, 2 × cluster-node-timeout) ms and is retried after twice that.

Stale replicas do not stand

A replica whose data is too old does not start an election. The limit is repl-ping-replica-period × 1000 + cluster-node-timeout × cluster-replica-validity-factor, and the factor is 10 by default.

Lowering the timeout

A lower cluster-node-timeout or down-after-milliseconds makes failover faster. It also makes a short pause count as a death, for example a long fork or a slow command on the one main thread. That trade-off is inferred from the mechanism. Measure your longest pause before you lower the timeout.

The time is now explained, but not who may vote. The next section shows why a cluster that lost two of three masters, or a cluster of one shard, does not fail over at all.

## Who votes, and when does no failover happen?

The timeout explains how long a failover takes. Who may vote explains whether a failover happens at all, and the answer is different in Redis Cluster, Sentinel and ElastiCache.

In Redis Cluster the replicas of a shard do not vote for each other. A replica asks the masters of all shards, and only a master that serves part of the keys may vote. It needs (size / 2) + 1 votes, where size counts the masters that serve keys, including the failed one. A master votes for the first valid replica that asks. It does not compare replicas, so the best replica wins only because its rank lets it ask first.

- A master dies. Do enough other masters with keys still answer to give (size / 2) + 1 votes?

- yes3 masters, 1 dies: 2 voters, 2 needed, so its replica is promoted

- no3 masters, 2 die at once: 1 voter, 2 needed, so neither shard fails over

- no1 shard only: the only master is the dead one, so 0 voters

A local run checked the one-shard case: one master, one replica and cluster-node-timeout 3000. Twenty seconds after kill -9, the master was still marked fail? and the replica was still a replica. redis-cli --cluster create also refuses such a layout with "Redis Cluster requires at least 3 master nodes". So Redis Cluster needs at least three masters before it can fail over by itself.

Evidence
Only "a master serving at least 1 slot" may vote: src/cluster_legacy.c 8.10.2, lines 4144 to 4149. The majority is at line 4390. A master votes once per epoch, and not for another replica of the same master for two times the timeout: lines 4165 to 4232. The cluster spec says masters "make no effort to select the best replica". Local run on redis-server 8.10.1, 2026-10-18.

The phase said two replicas per shard give a clean 2-of-3 majority. True now, at Redis 8.10.2: in Cluster the masters of all shards vote, in Sentinel the Sentinels vote, and on ElastiCache AWS decides. The node count of one shard is not the vote.

Sentinel splits the decision into two votes, in this order.

- Each Sentinel marks the primary down for itself after down-after-milliseconds.

- When the quorum, a number of Sentinels you configure, agree, the primary is marked objectively down. The quorum only detects the failure.

- A majority of all Sentinels must then elect one leader Sentinel, and only that leader runs the failover. If the quorum is larger than a majority, the leader needs that many votes. So with three Sentinels, two must be able to talk to each other.

- The leader first skips replicas that were disconnected from the primary for too long. It sorts the rest by replica-priority, then replication offset, then run ID. It promotes it and tells the other replicas and the clients.

The Sentinel docs advise at least three Sentinels on three different machines. With two Sentinels, losing the machine of one leaves no majority, so no failover can run. That last point is inferred from the majority rule.

On ElastiCache AWS runs the failover and documents no vote. It promotes "the read replica with the least replication lag". With cluster mode disabled, it points the DNS name of the primary endpoint to the new primary. So the client keeps the same name, and the time that the client's resolver keeps the old address adds to the outage. That effect of DNS caching was not checked.

  Redis ClusterSentinelElastiCache

  Who detectsevery node, after cluster-node-timeout, 15 seach Sentinel, after down-after-milliseconds, 30 sAWS, not described

  Who decidesa majority of masters that serve keysa majority of all Sentinels elects a leaderAWS

  Which replicathe first valid one that asks, usually rank 0skips long-disconnected ones, then priority, offset, run IDthe least replication lag

  How clients find itredirect errors, then a fresh cluster layoutthey ask Sentinel for the primarythe endpoint's DNS name moves

  When it cannot fail overunder 3 masters, or a majority of masters lostno majority of Sentinels can talka customer reboot of the primary

The phase called Sentinel "cluster-mode DISABLED on ElastiCache" and said "the most up-to-date replica wins". True now: AWS documents a DNS change and the least-lag replica, not Sentinel. Sentinel skips long-disconnected replicas and sorts by priority before the offset.

Go deeper: the partition case, and when a majority is lost
Partitions

The Sentinel docs show a partition where the old primary sits on the minority side with one client. That client's writes are marked "C1 (writes will be lost)", because the majority side promotes a replica. The fix the docs give is min-replicas-to-write from the WAIT section, which makes the cut-off primary refuse writes.

When the majority is gone

The Redis Cloud outage, in the Go deeper block of the first concept, lost five nodes, a majority. So its automatic recovery could not run. The same rule protects against two primaries: a side without a majority cannot promote anyone.

Practising a failover

On ElastiCache the test-failover action starts a real failover on a replication group. It is the managed version of the kill -9 test, and it shows what your clients do.

The cluster now has a new primary. The next section asks what your clients see from the death until they find it.

## What does your client see during the failover?

The server side of a failover ends when a replica is promoted. The outage your users see ends only when each client has found the new primary.

From 02:10 your agent service's clients send commands to an address that does not answer. Each command waits for its timeout or fails at once, and then the client must learn the new primary. The client's own settings decide how long that takes, and whether its retries make the outage longer.

- primary diescommands time out, or the connection is refused

- client retrieswith a delay that grows on each try, plus a random part

- client rediscoversasks Sentinel, resolves the endpoint again, or fetches the cluster layout again

- writes resumeon the new primary, with the same keys

Each client step has its own way to fail.

- A client with a long command timeout holds each request for that long, so a 10-second timeout turns every failed call into a 10-second wait.

- A client that refreshes the cluster layout rarely keeps sending to a dead node until its next refresh.

- A client that retries at once and without limit sends a storm of connections and layout requests when the node returns.

- An application configured with one node's address, not the cluster or primary endpoint, cannot follow a failover at all.

Grab saw the second failure in its driver state service. The data sat in an ElastiCache Redis Cluster with 3 shards and 2 replicas each, and reads went to replicas. One replica failed, and for about 1 minute only about 1 in 21 calls succeeded, so rides dropped. The team's own arithmetic said the cluster should stay up, so they looked at the client. Pipelined reads, which send many commands in one batch, failed on the dead replica. The library returned one error for the whole pipeline if one command failed. The client also refreshed the cluster state only about once a minute.

Evidence
Grab, "Preventing Pipeline Calls from Crashing Redis Clusters", 2019: https://engineering.grab.com/preventing-pipeline-calls-from-crashing-redis-clusters . The incident was on 2019-02-15. The post proposes three fixes. One is a separate client for pipelined reads that routes by latency. The others are a result and error per command, and a reload of the cluster state on a pipeline error. The post does not confirm that all of them shipped.

AWS gives the client rules for ElastiCache, from client outages it has observed.

- Use a bounded connection pool, so a failover cannot open thousands of new connections.

- Retry with exponential backoff and jitter, a random part in each delay, so clients do not retry in step.

- Discover the cluster through the configuration endpoint, not a fixed node address.

- Keep discovery calls rare, because each CLUSTER SLOTS reply costs more as the cluster has more nodes.

Without these rules AWS saw server CPU at 100% and an unresponsive cluster after clients lost their connections. It saw this in redis-py-cluster, Lettuce and Redisson.

Evidence
AWS, "Best practices: Valkey/Redis OSS clients and Amazon ElastiCache": https://aws.amazon.com/blogs/database/best-practices-redis-clients-and-amazon-elasticache-for-redis/ . The post gives no incident numbers. It says AWS "observed multiple client outages".

Go deeper: a client pointed at one node, and two shared Redis outages
One node's address

At Webflow the Redis primary failed over, but the application's Redis URL pointed at one node, not the cluster endpoint. Its errors on the long-lived connection were not caught, so pods crashed in a loop for about 30 minutes. Source: https://status.webflow.com/incidents/7pbl0qlc61kf .

Retries that overload something else

At bsport one shared Redis stopped responding. Services queued requests and filled their pools, and retries and reconnects caused a spike in DNS lookups. CoreDNS overloaded, and then no service could resolve any internal name. The fix split Redis into one Valkey cluster per domain. Source: https://engineering.bsport.io/how-we-eliminated-redis-as-a-single-point-of-failure-2729c22008b5 .

  The timeout and the voters decide a failover, and the client decides the outage.

  Three nodes per shard do not make Redis Cluster fail over, because masters vote.

  Read your client's command timeout, retry backoff and topology refresh interval in its config.

In cluster mode the client also chooses the node for every key. The next section shows how it chooses, and what the server answers when the choice is wrong.

## Where does a key live in cluster mode, and who routes it?

The failover sections showed that clients must find the new primary. In cluster mode a client must also find the right shard for every single key, so routing becomes part of every request.

Months after the night at 02:10, your sessions outgrow the memory of one node. You move them to Redis Cluster with three shards. The same code now sees errors it never saw on one primary.

Redis Cluster divides the keys into 16,384 hash slots. A key's slot is CRC16(key) mod 16384, and each slot belongs to one master. The client keeps a slot map, its copy of the cluster layout as a table from slot to master. It sends each command to the owner of its key's slot. A node never forwards a command to another node. When it does not own the slot, it answers MOVED, an error with the slot and the owner's address. The client must retry there.

Slots can move while the cluster runs. A reshard moves chosen slots to a chosen master, so a client's slot map can be out of date.

- clientslot map says slot 12182 is on node A

- node Adoes not own it: -MOVED 12182 127.0.0.1:17103

- clientupdates its map and retries

- node Cowns slot 12182, returns the value

A request with a stale slot map. The reply text is from a local run on six nodes.

Predict: after a reshard, your client's slot map is stale. It sends GET session:u42 to the node that used to own that key's slot. What comes back: nil, the value, or something else?
Something else: an error, MOVED <slot> <host:port>. The old node does not own the slot any more, so it refuses to answer for it. A correct client follows the redirect and refreshes its map. The usual guess is nil, "the key looks missing", because a missing key is what an application sees most often. A node answers nil only when it owns the slot, or serves a replica read, and the key is not there.

The node chooses its answer with these rules, in getNodeByQuery.

- It computes the slot of every key in the command. If the keys are in different slots, it answers CROSSSLOT, the error for keys in more than one slot. So MGET and transactions across slots fail.

- If another node owns the slot, it answers MOVED. The client should update its map, because the move is permanent.

- If the slot is moving away and the key is no longer here, it answers ASK, a redirect for this one command. The client sends ASKING and the command to the target once, without changing its map.

- If a command with several keys finds some here and some moved, it answers TRYAGAIN, and the client retries a little later.

- Only when this node owns the slot does it run the command. A nil answer then means the key really does not exist.

A hash tag changes which text is hashed. If a key contains {...}, only the text inside the first pair of braces is hashed. So the Phase 1 naming rule puts all of a tenant's keys in one slot, where one MGET can read them.

  KeySlotResult

  company:c7:profile15713three slots, so MGET of profile and sessions gives CROSSSLOT

  company:c7:settings11829

  company:c7:sessions3080

  {company:c7}:profile, {company:c7}:settings, {company:c7}:sessions8819one slot, so one MGET works

  foo12182the key of the local run

A hash tag also has a cost. All of one tenant's keys sit on one master, so a tenant with most of the traffic makes that master hot. Phase 5 deals with a shard that takes most of the traffic.

The same platform gives a use case that shows why the reply matters. After a cluster layout change, one service's error rate rose, and it recovered only when the service restarted. The phase explained it as nil replies for keys that "look missing". A node answers MOVED instead, so the likely cause was a client that failed on MOVED, or refreshed its map too rarely. A restart loaded a fresh slot map. The real cause is internal and was not checked.

The phase said a client with a stale slot map gets nil. True now, in src/cluster.c at 8.10.2: the node replies MOVED, or ASK during a migration. A local run confirmed MOVED 12182 127.0.0.1:17103 on both nodes that did not own the slot.

After a reshard, the old owner answers MOVED for the slots it gave away. Since Redis 8.4 a slot can move atomically. That should shorten the time clients see ASK redirects, which is inferred.

The phase's demo re-split all slots into equal ranges for three and then four shards, so a slot "moved" between two old shards. A real reshard moves only the slots you choose, to the node you choose. The phase also taught only the key-by-key move, which is no longer the only method.

Evidence
Slot rule: cluster spec, "Key distribution model". Reply order: src/cluster.c 8.10.2 lines 1436 to 1487, and CROSSSLOT at line 1500. The slot numbers were computed by the lab's code and match CLUSTER KEYSLOT on 8.10.1. Release notes: 8.4.0 line 104, 8.10.2 line 279, Valkey 9.0.0 line 118. The claim that the ASK window is smaller with atomic migration is inferred, and the design docs were not read.

Go deeper: why 16,384 slots, a measured reshard, and how atomic migration works
Why 16,384

Every heartbeat on the cluster bus carries a bitmap of the sender's slots. With 16,384 slots that bitmap is 2 KB, and with 65,536 it would be 8 KB in every ping. antirez's reason was that a cluster is not expected to pass about 1,000 masters, so 16,384 slots are enough. Source: a comment on https://github.com/redis/redis/issues/2576 .

A reshard, measured

In a local run redis-cli --cluster reshard moved 5,461 slots, and its log says "imported 6660 keys". After the move the old owner answered MOVED 12182 127.0.0.1:17101, and the value was intact. The older method moved keys in batches with CLUSTER SETSLOT and MIGRATE, and clients saw ASK for each moved key during the move. Redis 8.4 added atomic slot migration, CLUSTER MIGRATION, and in 8.10 redis-cli --cluster reshard uses it. Valkey 9.0 added its own.

Atomic migration in Redis

The destination runs CLUSTER MIGRATION IMPORT. The source forks and sends a snapshot of the slot on an RDB channel, and streams new writes on the main channel. It pauses writes when the destination is close, then ownership changes and the source deletes its copy of the keys. The handoff starts when lag is at most 1 MB, and the write pause is at most 10 s.

Atomic migration in Valkey

Valkey runs CLUSTER MIGRATESLOTS on the source, and the nodes talk with CLUSTER SYNCSLOTS subcommands. The source pauses for at most two times cluster-manual-failover-timeout, 10 s with the 5,000 ms default.

Reading the layout

CLUSTER KEYSLOT <key> gives a key's slot. CLUSTER SHARDS lists each shard with its slot ranges and nodes. redis-cli -c follows redirects for you, which hides them when you want to see them.

Keyed commands now have a clear route. The next section shows what cluster mode changes for commands that have no key, such as pub/sub and keyspace events.

## What else changes when you turn on cluster mode?

Keyed commands go to the owner of their slot. Commands without a key, and events that a node raises by itself, follow other rules. Code that worked on one primary can break on them.

Your agent service listens for expired sessions, so it can close each conversation. On one primary it subscribed to keyspace expiry events, the pub/sub messages Redis sends when a key expires, and saw all of them. After the move to three shards it sees about one third. The table shows why, together with the other changes.

  FeatureOne primaryRedis Cluster

  Databasesseveral numbered databases, chosen with SELECTdatabase 0 only, SELECT is refused. Valkey 9.0 allows numbered databases

  Commands with several keysany keysone slot only, or CROSSSLOT

  PUBLISHto local subscriberssent to every node over the cluster bus, so any subscriber gets it

  SPUBLISH, sharded pub/sub, where a channel has a slot like a keynot neededsent only inside the shard that owns the channel's slot

  Keyspace notificationsone node raises all of themeach node raises events only for its own keys, and does not send them to other nodes

  Smallest setup that fails overone primary, one replica, three Sentinelsthree masters

The keyspace case follows from where events start.

- When a key expires, the node that holds the key raises the event, on that node only.

- The keyspace notifications docs say these events "are not broadcasted" in a cluster. A subscriber gets the events of the node it is connected to.

- The configuration endpoint connects your subscriber to one node. With three shards, that node holds about one third of the slots, so you see about one third of the expiries.

- The fix is to subscribe on every master, and to subscribe again when the layout changes.

Plain pub/sub works the other way. A local run sent PUBLISH to node 17102, and a subscriber on node 17101 received it. PUBLISH returned 0, because the count is only the subscribers on the node that received it. A keyspace subscriber on 17101 saw only events for keys in slots that 17101 owns.

Broadcast has a cost that grows with the cluster. Every PUBLISH goes to every node over the cluster bus, which was built for control traffic. Figma moved its Pub/Sub load to a cluster-mode ElastiCache instance. A few weeks later it saw four outages of 7 minutes to 1 hour 20 minutes. Engine CPU on one node sat at 100%, and moving to a larger cluster with more nodes made it worse. AWS found the cause on the cluster bus. When messages could not be sent fast enough, the bus buffer grew. Each send trimmed it with memmove, so CPU grew with the buffer. Figma moved all Pub/Sub off clustered ElastiCache, and gave each main use its own instance.

Evidence
Figma, "Postmortem: Service disruptions on June 6 & 7, 2022": https://www.figma.com/blog/postmortem-service-disruptions-on-june-6-and-7-2022/ . The team first suspected capacity or a bad machine, then ruled out backups, a command spike, slow commands and big keys. AWS rate limits on manual failover blocked one failover. Broadcast: cluster spec, "Publish/Subscribe", and src/cluster_legacy.c 8.10.2 lines 4070 to 4085. Keyspace events: the keyspace notifications page, "Events in a cluster". Database 0: cluster spec. Valkey 9.0.0 release notes line 112. Local run on redis-server 8.10.1, 2026-10-18.

A use case from the same platform fits here. A notification feature that used pub/sub broke after a move to cluster mode. The phase explained it as plain PUBLISH not being routed to the right shard. Plain PUBLISH reaches every node, so that explanation is wrong. A per-node event, such as a keyspace notification, fits the symptom better. So does a client that subscribed on one node and lost it in a layout change. The real cause is internal and was not checked.

The phase said plain pub/sub is not routed in a cluster, and sharded pub/sub exists to fix that. True now, since Redis 7.0: PUBLISH is broadcast to every node, and SPUBLISH exists to cut that broadcast. Keyspace notifications are the events that stay on one node.

Go deeper: sharded pub/sub details, and scripts in a cluster
Sharded pub/sub

SSUBSCRIBE and SPUBLISH arrived in Redis 7.0. A sharded channel has a slot like a key, so SPUBLISH to a node that does not own the slot gets MOVED, as a local run showed. Sharded channels ignore patterns, so there is no sharded PSUBSCRIBE.

Expiry events fire late

A keyspace expired event fires when Redis deletes the key, which can be later than the moment the TTL reached zero. Code that closes a session on this event must accept that delay.

Scripts

A Lua script must receive every key name as an argument, so that the cluster can check that all keys are in one slot. A script that builds key names at run time can work on one primary and fail in a cluster.

Cluster mode now has a clear price. The last section asks when that price is worth paying, and how to check which topology each environment runs.

## One primary or a cluster: which topology fits, and which one runs where?

Cluster mode costs database 0 only, CROSSSLOT errors, per-node events and a three-master minimum. So the choice depends on whether one node can still carry the load.

Your sessions outgrew the memory of one node, and that is one of three reasons to move. Memory is the obvious one. The write rate and the CPU of the one main thread are the other two, and any of the three can run out first.

- Do the data, the write rate and the CPU of one main thread all fit one node, with room for a fork?

- yesone primary with replicas: Sentinel, or ElastiCache with cluster mode disabled. Every command works, and replicas add reads and failover

- noRedis Cluster: shard the keys across masters, and accept slots, hash tags, CROSSSLOT, per-node events and at least three masters

  One primary with replicasRedis Cluster

  What it addsfailover and read replicasfailover, and more memory, writes and CPU per added shard

  Commands with several keysalways workonly inside one slot

  Limitone node's memory, write rate and main threadthe cluster bus and the client's handling of redirects

  What can break code that worked beforenothing newCROSSSLOT, MOVED, SELECT, keyspace events, scripts that build key names

GitLab moved its cache from one primary with Sentinel to Redis Cluster because of CPU, not memory. Its epic names a "chronic risk of CPU saturation" on the cache primary, which could use only one main thread. The team first moved the rate-limiting instance, because it was small and could lose data. Then it moved the cache. The goal was every node "below 70% CPU and memory utilization at their daily peak workload".

Evidence
GitLab epic 878, "Horizontally Scale redis-cache using Redis Cluster": https://gitlab.com/groups/gitlab-com/gl-infra/-/epics/878 , read through the API. It ran from 2023-01-13 to 2023-08-24. The rate-limiting runbook says that losing all its data lets some users get up to double their limit for about one minute: https://runbooks.gitlab.com/redis-cluster-ratelimiting/ .

The platform of the earlier use cases made the opposite choice in one region. It moved that region's groups from cluster mode enabled to cluster mode disabled, because the data fit one node. It gave up horizontal scale, and lost slots, CROSSSLOT errors and the risks of a reshard. A team that sees its data fit one node can make that call.

### Which topology does each environment run?

Every case in this phase came from code that assumed a topology it did not check. The code assumed a replica count for WAIT, a slot map, or the node that raises an event. The platform of the use cases ran four groups that differed in cluster mode, engine, replicas and snapshots, as the Go deeper block below shows.

Before you reason about a behaviour, read the topology of that environment with these commands.

- INFO replication and ROLE show the role, connected_slaves, each replica's offset and lag, and master_link_status on a replica.

- INFO persistence shows rdb_last_save_time, aof_enabled and aof_delayed_fsync.

- CLUSTER INFO and CLUSTER SHARDS show whether cluster mode is on, and which shards own which slots.

- CONFIG GET maxmemory-policy shows the eviction policy.

- aws elasticache describe-replication-groups shows cluster mode, Multi-AZ, automatic failover and snapshot retention for each group.

Go deeper: the four groups of the use case, and Stack Overflow's reasons against Cluster and Sentinel
Four groups on one platform

These values come from the phase and were not checked.

  GroupCluster modeEngineReplicasFailoverSnapshots

  A, production, region 1enabled5.0.62automatic, Multi-AZ not setnone

  B, production, region 1enabled, 1 shard6.22automatic, Multi-AZ3 days

  C, production, region 2disabled6.x1automatic, Multi-AZ1 day

  D, testenabled5.0.61automaticnone

No group used the AOF, and no group replicated to another region. The eviction policy was volatile-lru, which is the ElastiCache default. Group D's single replica is the environment where WAIT 2 took 2 seconds. Groups A and D run 5.0.6, which has no SPUBLISH, because sharded pub/sub arrived in Redis 7.0.

Stack Overflow

Stack Overflow ran 2 physical Redis servers per data center, with 256 GB of RAM and under 96 GB used. It served about 1.59 billion commands a day, with a peak of 86,982 a second. It used no Redis Cluster, because Cluster does not support databases and needs three or more nodes. Stack Overflow keeps one Redis database per site. It used no Sentinel, because Sentinel rewrites its config files, which conflicted with Puppet. So a team can run at that size on one primary per data center, without Cluster or Sentinel.

  In cluster mode the client routes every key, and the server only redirects.

  Moving to cluster mode for scale you do not need adds CROSSSLOT and per-node events.

  Run E9, then type CLUSTER KEYSLOT foo on any cluster and expect 12182.

Cluster mode has a clear price. The next section asks what distance costs you, and the one after it what the network can do to a Redis with no guard.

## What does a region failover lose, and what do cross-AZ reads cost?

A region failover keeps only the writes that crossed the link, and a cross-AZ read is billed in each direction.

You saw that a failover inside one region can lose the acknowledged writes a replica had not received. A whole region can fail the same way, and then the cost is larger and the bill is a second surprise.

Your agent service runs in one region. It keeps a standby, a read-only replica in a second region that copies the primary over a wide-area link. An Availability Zone (AZ) is one or more data centers inside one cloud Region, and a Region has several AZs. Traffic inside one AZ is free. Traffic across AZs in one Region is billed, and traffic across Regions is billed more. The link to the standby is asynchronous, like the replication in this phase, so the standby holds only what reached it.

- same AZ$0.00 per GB

- across AZs, one Regionabout $0.01 per GB, in each direction

- across Regionsabout $0.02 per GB out of us-east-1

AWS data transfer, us-east-1 price list. One GB that crosses AZs costs about $0.02, because it is billed when it leaves and when it enters. That rule is from Corey Quinn's 2019 test.

Predict: the primary region dies. In its last second it acknowledged 40 session writes and 1 run lock that the standby had not received. You promote the standby. What do those 40 users see, and what can happen to the run?
The 40 sessions are not on the standby, so those users are logged out and sign in again. The run lock is also absent, so a second worker in the new region runs SET lock NX, gets it, and runs the same run the first worker still believes it holds. The usual guess is "the standby has everything, so a failover is clean". That is true only for the writes that crossed the link before the region died.

The cost and the loss both follow from asynchronous replication across distance.

1. A read from a replica in another AZ crosses an AZ boundary on every reply. The ElastiCache pricing page says there is no charge for traffic in or out of the cache node itself, so replication between AZs is free. That step is inferred from the page. The charge is on the traffic between your application and the cache. So you read from a replica in the same AZ as the client.

2. AZ-aware reads are a client feature, not a server one. go-redis v9.5.1 has RouteByLatency but no AZ option. Lettuce has ReadFrom.subnet(...). Valkey GLIDE has AZ_AFFINITY and needs a client AZ that matches the AZ the server reports.

3. For the server to report its AZ, Valkey 8.0 added the availability-zone config, shown in INFO and, since Valkey 8.1, in the HELLO reply. Redis 8.10.2 has no such setting.

4. Open-source Redis and Valkey have no multi-primary across Regions. A cross-region replica is an ordinary REPLICAOF over the wide-area link, and you promote it and move clients yourself. This is inferred from the replication docs, and was not checked against every Valkey page.

5. ElastiCache Global Datastore has one writable Region and read-only standbys, which AWS calls secondary clusters. AWS does not fail over across Regions for you. You promote a standby by hand. The AWS product page, not the docs, says this takes less than 1 minute. Writes not yet replicated are lost, which is inferred from the asynchronous link.

6. At a region failover each kind of data loses its unreplicated window, and each loss is different.

  DataWhat a region failover loses

  Sessionsusers whose session was in the window log in again

  Locksa lock in the window is absent, so two workers can run one run

  Rate-limit countersthe count falls back, so users get extra quota in the window

  Cachesthe window's keys are misses, so the standby's database is read

Each loss follows from the writes the standby had not received when the region died.

Uber chose not to replicate its cache values across Regions. CacheFront serves over 40 million requests a second across Uber's Docstore instances. A cold cache in the other Region would add database load at a failover, and that would stop Uber from shrinking its database. Uber copies the key names, not the values, to the other Region, so the other Region reads each row from its own database and fills its own cache. Cloudflare shows the session case: its dashboard sessions lived in Redis and could not move across the ocean without disruption, so moving traffic to the second data center helped the API and hurt the dashboard.

Evidence
AWS data transfer prices: the us-east-1 Price List file for AWSDataTransfer, SKU PNUBVW4CPC8XA46W, publication 2026-09-16. The "each direction" wording: Corey Quinn, Last Week in AWS, 2019-10-21, a 10 GB test billed as 20 cents. The Valkey blog "Reducing application latency and lowering Cloud bill", 2025-01-08, priced cross-AZ transfer at $0.01 per GB counted once, for 250 MB/s of reads with half crossing AZs. It measured a same-AZ read at about 300 µs and a cross-AZ read at about 800 µs, and cut a test from $4,373 to $1,088 a month, of which $3,285 was cross-AZ transfer (vendor source). go-redis v9.5.1 osscluster.go has no AZ field. Valkey availability-zone: valkey.conf 9.1.2 line 541. No cross-region autofailover: the AWS Global Datastore prerequisites page. Under a minute: the AWS Global Datastore product page. Uber: the Uber engineering blog, 2024-02-15, a vendor source, "In case of a region failover, another region must be able to serve all requests" and "By replicating keys instead of values, we always ensure that the data in the cache is consistent with the database". Cloudflare: its blog, 2020-11-27, sessions "cannot currently be moved across the ocean without disruption". A local run of the region-failover lab on 2026-10-19 lost 25 of 125 sessions and let a second worker take the lock.

  A region failover keeps only the replicated writes, and a cross-AZ read is billed in each direction.

  Keeping sessions or locks only in one region's Redis. At a failover users log in again, and one lock can be held by two workers.

  Run E15: promote a standby and watch 25 sessions and a lock vanish. Then run E16 for the cross-AZ bill.

Distance costs money and loses writes. The next section asks what you must set up so the network cannot take the whole server.

## What must you secure before Redis faces the network?

Redis trusts the network, so you add per-service users, TLS, bus authentication, and prompt patching.

Cluster mode changed what your client must do for every key. The network changes what any client can do to the whole server, because Redis is built for trusted clients inside a trusted environment.

Your agent service's Redis holds sessions, locks and a tool cache. If the port is reachable with no password, any client runs every command, including one that erases it.

The defence is three layers. The first is the shipped defaults, such as protected mode, a default guard that limits who may connect. The second is one ACL user per service. An ACL, access control list, is a named user with a password, a set of allowed commands, and a set of allowed key and channel patterns. The third is TLS.

- networkshipped config binds loopback only

- protected modeno password on the default user, so reject non-loopback

- ACL usera password, a command set, a key set

- TLSencrypt the client link, and map a certificate to a user

- dangerous offDEBUG, MODULE LOAD, CONFIG SET dir refused by default

The layers an unauthorized command must pass. Each one is a separate setting.

Predict: you give the cache service one user: ACL SETUSER cache on >pw resetkeys ~cache:* -@all +@read +@write +@connection. It can read and write only cache:* keys. Can it still erase the whole server?
Yes. FLUSHALL, FLUSHDB and SWAPDB take no key, so the ~cache:* pattern never applies to them. The user has +@write, and FLUSHALL is a write command, so it is allowed. The usual guess is "a key pattern limits the user to its keys". A key pattern limits keyed commands only. You must remove the dangerous category by command.

The protection comes from the defaults and from how the rules are read.

1. Protected mode is on by default. When the default user has no password, Redis rejects every connection that is not from loopback, and sends a -DENIED error. It turns off as soon as the default user gets a password, even a weak one.

2. A command belongs to one or more categories, such as @read, @write, @dangerous, @admin and @scripting. You grant and remove categories, and the rules apply left to right.

3. The fix for the cache user is -@dangerous placed after the grants. It removes FLUSHALL, FLUSHDB, SWAPDB, KEYS, SORT, MIGRATE, RESTORE and CLIENT KILL, which the plus rules had granted. A minus rule placed before +@write would be undone by the later grant.

4. Add -@scripting too. EVAL is only in @scripting, so -@all already refuses it. But FUNCTION LOAD and FUNCTION FLUSH are also in @write, so +@write grants them, and FUNCTION LOAD runs Lua code. 8 of the 29 Redis advisories from 2023 to 2026 were Lua engine bugs.

5. A key pattern limits access, not visibility. A SCAN as the cache user still lists key names outside cache:*, although a GET on them is refused. ACL LOG records each refusal with its reason, which is command, key, channel, auth or tls-cert.

6. TLS encrypts the client link and can map a certificate to a user. With tls-auth-clients-user CN the certificate's Common Name picks the ACL user. A Common Name with no matching user leaves the client on the default user, and ACL LOG gets a tls-cert entry. If the default user is nopass, that client has every permission.

```bash
# WRONG: a key pattern, no command limits.
ACL SETUSER cache on >pw resetkeys ~cache:* \
    -@all +@read +@write +@connection
ACL DRYRUN cache FLUSHALL   # -> OK  (wipes the whole server)

# RIGHT: remove the dangerous and scripting categories last.
ACL SETUSER cache on >pw resetkeys ~cache:* \
    -@all +@read +@write +@connection -@dangerous -@scripting
ACL DRYRUN cache FLUSHALL   # -> no permissions to run 'flushall'
```

The cluster bus, from the failover sections, is the second TCP port each cluster node opens, at the client port plus 10000. It has no authentication of its own unless tls-cluster yes. A CLUSTER MEET packet from any host that reaches the bus port adds that host as a node, and its gossip is trusted. In a local run a rogue node sent CLUSTER MEET to a two-node cluster, joined it, replicated the data, and then took every slot with CLUSTER FAILOVER TAKEOVER. The only thing that blocked the rogue from reading data was a client password on the primary, which failed its replication AUTH. The password did not stop the takeover. With it set, the rogue still took all 16384 slots, and clients were sent with MOVED to a node that held no keys. Redis 8.10.2 adds cluster-bus-port-protected-mode, default no, which makes a node refuse to start without tls-cluster when set to yes.

Evidence
Protected mode: src/networking.c:1608-1637 at Redis 8.10.2. Since Redis 7.0 a non-default bind no longer turns it off (7.0.0 release notes #9034). Categories and left-to-right rules: redis.conf:1059-1092; FLUSHALL is in @dangerous and @keyspace (COMMAND INFO on 8.10.1). The cache-user trap and its fix were run on 2026-10-19: ACL DRYRUN returned OK for FLUSHALL on the WRONG user and "no permissions" after adding -@dangerous, on redis-server 8.10.1. Lua CVEs: of 29 Redis advisories read from 2023 to 2026, 8 were Lua bugs, including CVE-2025-49844, scored 10.0, which needs an authenticated user (GitHub advisories API; Wiz blog, 2025-10-06). ACL LOG reasons: src/acl.c:3167-3182. tls-auth-clients-user CN since Redis 8.6; the 8.10.1 release fixed a NUL-byte Common Name bypass. Cluster bus: 8.10.2 release notes #15722; cluster-bus-port-protected-mode default 0 at src/config.c:3434. The rogue MEET run used loopback ports 6583 to 6588 on 2026-10-19. Dangerous commands off since 7.0: src/config.c:3496-3498, release notes #9920.

  Redis trusts the network, so a deployment needs per-service ACL users with -@dangerous -@scripting, TLS, and bus authentication.

  A key pattern with no command limits. The user still runs FLUSHALL, FLUSHDB and SWAPDB, which take no key.

  Run E13: compare the WRONG and RIGHT ACL users, then run it with -break to watch the WRONG user FLUSHALL.

This is the last teaching section. The recall below collects the claims and hands over to Phase 5.

## What you can do now, and what comes next

The night at 02:10 now has an answer for each of its lines.

- The disk. What a crash loses depends on the kind of crash, and an empty restarted primary empties its replicas. A kill -9 with AOF everysec loses nothing in the normal case, and a power loss loses about one second. A slow disk makes both windows longer. From "What does a crash lose, and which crash?" and "Why can a restart empty the replicas as well?".

- The acknowledged writes. WAIT counts the replicas that have your write, but a failover can still lose it. Only min-replicas-to-write bounds the loss, by refusing writes. From "What does an OK from the primary promise?" and "What does WAIT cost when a replica is missing?".

- The reconnect. A replica gap longer than the backlog forces a full sync, which forks the primary and can crash it. From "When does a reconnecting replica copy everything again?" and "How can a full sync take the primary down?".

- The outage. Failover time is mostly the detection timeout, and in Redis Cluster the masters of other shards vote. Your client's timeouts, retries and refresh decide the rest. From the three failover sections.

- The route. In cluster mode no node forwards a keyed command, so the client's slot map decides routing. Keyspace events stay on one node, and PUBLISH goes to all of them. From the three cluster sections.

- The distance. A region failover keeps only the replicated writes, so sessions, locks, rate limits and caches lose the lag window. A cross-AZ read is billed in each direction, so read from a same-AZ replica. From the region and AZ section.

- The guard. Redis trusts the network, so you add per-service ACL users with -@dangerous -@scripting, TLS, cluster-bus authentication, and prompt patching. A key pattern alone does not stop FLUSHALL. From the securing-Redis section.

You can now state the loss window of a Redis setup for each kind of failure, and predict how long its writes fail. You can also read a MOVED or CROSSSLOT error and choose one primary or a cluster for a workload. Phase 5, Performance and failures, asks why a Redis that is up and replicated still answers slowly. It uses the fork, the replica reads and the hash slots from this phase. It applies them to memory headroom, to a shard that takes most of the traffic, and to big keys.

## Lab: the exercises that teach Phase 4

Sixteen of the phase's seventeen exercises, under their own ids and copied from the phase. E11 is left out, because it reads a private repository of the former employer. E1 to E12 use Docker, which was not available for this lesson, so their notes come from a reading of the lab code and from local runs on Redis 8.10.1 under Rosetta 2. E13 to E17 are new in this phase, and every one of them was run on 2026-10-19.

  IdeaExercises

  What a crash losesE1, E2, E3

  WAIT, and acknowledged writesE4, E5, E6, E7

  What clients see when the primary is goneE8

  Slots, hash tags and CROSSSLOTE9, E10, E12

  Multi-region and AZ cost (4.7)E15, E16

  Securing Redis (4.8)E13, E14, E17

Open the lab: setup and E1 to E17
Setup (single node for some, multi-node compose for others):

cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d                                    # single study node
docker-compose -f docker-compose.replication.yml up -d  # primary + 2 replicas (for E5-E8)

This path does not exist on this Mac. The lab code is in /Users/raghvendra.dhakar/Desktop/project/code/study-material/redis/code. The compose files pin redis:7.2. Current releases are Redis 8.10.2 and Valkey 9.1.2, and some defaults differ, such as repl-backlog-size at 1 MB against 10 MB.

-  E1 docker RDB loses since-last-snapshot.

- Run: bash ./phase04_ha/persistence_demo.sh

- Expected: the key written after BGSAVE is gone after the crash+restart; AOF keeps all.

- Teaches: the RDB data-loss window vs AOF-everysec.

The RDB half shows the loss window. The AOF half cannot show the one-second window, because docker kill ends only the process, and the kernel keeps the page cache. The sleep 1.2 "to let fsync flush" is not needed for that reason. The key recent is written before BGSAVE and is never printed. Expect all three AOF keys to survive whatever the fsync timing.

-  E2 docker See the persistence config.

- Run: docker exec redis-study redis-cli CONFIG GET save; docker exec redis-study redis-cli CONFIG GET appendonly

- Expected: the study node's save rules and appendonly no (our sandbox).

- Teaches: how to check what durability you actually have.

Also read aof_delayed_fsync in INFO persistence. A value above 0 means the disk was too slow for everysec at some point.

-  E3 docker Force a snapshot and find it.

- Run: docker exec redis-study redis-cli BGSAVE; docker exec redis-study redis-cli LASTSAVE; docker exec redis-study redis-cli --rdb /tmp/dump.rdb (or check INFO persistence | grep rdb_last_save_time).

- Teaches: BGSAVE/LASTSAVE/INFO persistence — the snapshot toolkit.

-  E4 go The WAIT incident (single node = 0 replicas).
The program connects to localhost:6379 by default. That may be a real Redis on your machine, and the program writes the key ha:key to it. Before you run it, check what answers on port 6379, or pass -addr with the study node's address.

- Run: go run ./phase04_ha/wait_command -replicas 2 -timeout 2s

- Expected: WAIT 2 blocks the full 2s and returns 0 → the staging failure of the use case.

- Teaches: hardcoded replica counts block the full timeout when replicas are missing.

A local run against a throwaway node on port 17301 printed "WAIT 2 replicas (timeout 2s) -> acked=0 in 2.03s". The program's comments and final lines still name the former employer's incident. The phase's own "Try this now" for WAIT is below.

# Single instance (0 replicas): WAIT 2 blocks the full timeout — the incident.
go run ./phase04_ha/wait_command -replicas 2 -timeout 2s
# Real replication (2 replicas): WAIT 2 returns 2 fast.
docker compose -f docker-compose.replication.yml up -d && sleep 5
docker exec redis-primary redis-cli SET k v && docker exec redis-primary redis-cli WAIT 2 1000  # → 2
docker compose -f docker-compose.replication.yml down

-  E5 docker Real replication.

- Run: docker exec redis-primary redis-cli INFO replication (→ role:master, connected_slaves:2).

- Then: docker exec redis-primary redis-cli SET foo bar; docker exec redis-replica-1 redis-cli GET foo (→ bar, replicated).

- Teaches: primary→replica async replication, and replicas serve reads.

-  E6 docker WAIT works when replicas exist.

- Run: docker exec redis-primary redis-cli SET k v; docker exec redis-primary redis-cli WAIT 2 1000

- Expected: 2 (both replicas acked), fast — contrast with E4.

- Teaches: WAIT's contract, and why the replica count must match.

-  E7 docker Replicas are read-only.

- Run: docker exec redis-replica-1 redis-cli SET x 1

- Expected: READONLY You can't write against a read only replica.

- Teaches: writes go to the primary only; replicas reject writes by design.

-  E8 docker (Break it) Simulate failover / replication lag.

- Run: pause the primary mid-writes: docker pause redis-primary, write attempts fail; docker exec redis-replica-1 redis-cli INFO replication | grep master_link_status (→ down). docker unpause redis-primary to recover.

- Teaches: what clients see when the primary is unreachable; the link-status signal.

The expected result is wrong, by reading, not by a run. docker pause freezes the process but keeps its TCP connections open. The replica marks the link down only after repl-timeout, 60 seconds by default, so expect master_link_status:up for about a minute. A docker exec into the paused container fails with a Docker error, which is not what a client sees. The compose file has no Sentinel, so nothing fails over. To see a real failover, use the Redis Cluster tutorial in the sources and kill one master, and expect about 20 to 25 seconds at default settings.

-  E9 go CRC16 slots + hash tags.

- Run: go run ./phase04_ha/cluster_hashslots

- Expected: untagged keys scatter across shards; {company:c7} tags co-locate to one slot (8819).

- Teaches: slot computation, CROSSSLOT, and hash-tag co-location.

A local run printed slots 15713, 11829 and 3080, and 8819 for the tagged keys, which match CLUSTER KEYSLOT. The program also prints a reshard block that re-splits all slots into equal ranges. Ignore it, because a real reshard moves only chosen slots.

-  E10 reason Verify a slot against Redis's own value.

- Reason/verify: the demo prints slot("foo")=12182; Redis documents CLUSTER KEYSLOT foo = 12182. (Our study node isn't cluster mode, but the CRC16 is identical.)

- Teaches: the slot math is deterministic and matches Redis exactly.

The demo's main() never prints foo. The value 12182 is right: a local run of CLUSTER KEYSLOT foo returned it. Run that command on any cluster to check.

-  E12 reason (Break it) CROSSSLOT in your head, then confirm the fix.

- Reason: given the demo's output, why does MGET company:c7:profile company:c7:sessions fail on a real cluster but MGET {company:c7}:profile {company:c7}:sessions succeed?

- Teaches: the exact rule for when multi-key ops are legal in cluster mode.

The exercises below are for the region and security sections. They run against a throwaway server on port 6583 and a Unix socket, never on 6379. Every command below was run on 2026-10-19, on redis-server 8.10.1, an x86_64 Homebrew build under Rosetta 2 on an Apple M4 Pro. E16 is a written exercise. Start a server with:

mkdir -p /tmp/p4lab
redis-server --port 6583 --bind 127.0.0.1 -::1 --dir /tmp/p4lab --save '' --appendonly no --daemonize yes

-  E13 break-it A per-service user that cannot wipe the server.

- Run: go run ./phase04_ha/acl_service_user then go run ./phase04_ha/acl_service_user -break

- Expected: the WRONG user (~session:* with no -@dangerous) runs FLUSHALL, and -break shows DBSIZE before 3 ... FLUSHALL as p4-naive -> OK. DBSIZE after 0. The RIGHT user gets no permissions to run the 'flushall' command. The model agrees with ACL DRYRUN on all 32 checks.

- If it fails: check the server is on 6583 and empty. -break refuses to run if the server holds more than 3 keys.

- Teaches: a key pattern does not limit keyless commands, so you need -@dangerous.

-  E14 offline The ACL rule model self-test.

- Run: go run ./phase04_ha/acl_service_user -self-test

- Expected: all checks passed. Remove -@dangerous from rightRules and re-run: 5 checks fail, because FLUSHALL, FLUSHDB, SWAPDB, KEYS and CLIENT KILL become allowed. Remove -@scripting instead: 2 checks fail, because FUNCTION LOAD and FUNCTION FLUSH become allowed.

- Teaches: the rules apply left to right, and the order of the minus rules decides the result.

-  E15 break-it A region failover loses the unreplicated writes.

- Run: go run ./phase04_ha/region_failover, after starting a second server on a socket.

- Expected: the standby holds 100 of the primary's 125 sessions, so 25 users log in again. The counter falls from 125 to 100. The lock taken after the cut is absent, so SET ... NX by worker-B returns true. The standby matches the model on every row.

- If it fails: check that /tmp/p4b/redis.sock exists and the primary is on 6583. The run takes about 6 seconds, mostly the full sync after the 5-second diskless delay.

- Teaches: asynchronous cross-region replication loses the lag window at a failover, differently for each kind of data.

mkdir -p /tmp/p4b
redis-server --port 0 --unixsocket /tmp/p4b/redis.sock --dir /tmp/p4b --save '' --appendonly no --daemonize yes
go run ./phase04_ha/region_failover

-  E16 written The cross-AZ bill.

- Reason: your service makes 2 TB of cross-AZ reads a month at $0.01 per GB in each direction. Compute the monthly transfer cost, and the cost if you pin reads to a same-AZ replica. Compare with the Valkey test's $3,285 against $1,088.

- Expected: 2 TB = 2,048 GB. Each GB is billed $0.01 when it leaves one AZ and $0.01 when it enters the other, so $0.02 a GB. 2,048 × $0.02 = about $41 a month. A same-AZ read costs $0. The Valkey test counted $0.01 once and got $3,285 against a $1,088 cluster. Billed in each direction, its transfer part would be about twice that.

- Teaches: cross-AZ transfer can cost more than the cluster, and AZ affinity removes it.

-  E17 live A certificate mapped to an ACL user, and TLS replication.

- Run: bash ./phase04_ha/tls_lab.sh

- Expected: a plain TCP client is reset. A client certificate with CN=p4-sessions becomes the default user until that ACL user exists, then becomes p4-sessions. CONFIG SET tls-cert-file serves a new certificate without a restart (the served serial changes). A replica reaches the TLS-only primary only after CONFIG SET tls-replication yes.

- If it fails: this needs a redis-server built with TLS. Check redis-cli --help | grep -i tls lists --tls, and otool -L $(which redis-server) lists libssl. This course's build has TLS. A build without it cannot run this exercise.

- Teaches: TLS client-certificate authentication, the CN-to-user mapping and its default-user fallback, certificate rotation, and tls-replication.

One more check, not in the phase

The empty-restart case can be seen on the compose file, whose primary already runs with --save "". This is inferred from the local run and was not run in Docker. Write some keys to the primary, restart it, and read the replica's key count about 6 seconds later. Expect 0.

for i in $(seq 1 1000); do echo "SET k$i v"; done | docker exec -i redis-primary redis-cli > /dev/null
docker exec redis-replica-1 redis-cli DBSIZE   # 1000
docker restart redis-primary
sleep 6
docker exec redis-replica-1 redis-cli DBSIZE   # expect 0

## Checkpoint questions

Eleven scenario questions with numbers. The phase's nine are rewritten without the former employer's names, and two cover the region and security sections. Each one is answerable from this lesson.

Open the questions

- Loss windows. State the data-loss window for each, precisely. (a) Self-hosted Redis with RDB save 60 1000 only. (b) Self-hosted with AOF appendfsync everysec, once for a kill -9 and once for a power loss. (c) ElastiCache with two replicas and Multi-AZ, on a primary node failure. (d) The same group on a total loss, with daily snapshots, and with no snapshots. Which of these can make Redis a system of record?
Answer sketch(a) Every write since the last finished snapshot, up to a minute or more. (b) Nothing for kill -9 in the normal case, because the bytes are in the page cache. About 1 s for a power loss. On a slow disk a kill can lose up to about 2 s, and a power loss can lose more. (c) The writes the primary acknowledged that the promoted replica had not received. (d) Up to a day of writes with daily snapshots, and everything with none. None of these makes Redis a system of record. Only a durable log, such as Valkey 9 durability-enabled clusters, changes the answer for synchronous writes.

- A fixed WAIT. A service calls WAIT 2 with a 2-second timeout after each write. Walk through why it returns in under 100 ms in production and adds 2 seconds a write in an environment with one replica. Name the INFO replication field the code should read, and give one code fix and one config fix.
Answer sketchWAIT ends when N replicas report an offset past the write, or at the timeout. With one replica the count never reaches 2, so every call waits the full 2 s and returns 1. Read connected_slaves. In code, ask for at most that many replicas and log a return below N. In config, set N for each environment, 2 in production and 1 or none where one replica exists.

- A master dies. An open-source Redis Cluster runs with defaults, three masters with one replica each. One master dies at t=0. Narrate the next 25 seconds: detection, the vote, client recovery and lost data. Then say why two masters dying at the same time stops both failovers.
Answer sketchOther nodes mark it PFAIL after 15 s, and FAIL when a majority of masters report it. Its replica waits 500 ms plus 0 to 500 ms at rank 0, asks every master, and wins with 2 of 3 votes in milliseconds. A local run saw the first good write at about 24 s. Clients get errors, then MOVED or a new slot map. Writes acknowledged by the dead master but not received by the replica are lost. With two masters dead, one voter remains and 2 votes are needed, so neither replica can win.

- Cluster mode for scale. A colleague wants to move to cluster mode "for scale". One region of the SaaS platform in this lesson moved the other way. Argue both sides. Name four costs cluster mode adds that one primary avoids, and the one question that decides it.
Answer sketchCluster mode is right when the data, the write rate or the main thread's CPU no longer fit one node, as at GitLab, where CPU drove the move. Its costs are CROSSSLOT errors and hash-tag discipline, MOVED and ASK handling with slot maps, and database 0 only. It also brings per-node keyspace events, broadcast PUBLISH, at least three masters, and reshard risk. The question is whether one node, with room for a fork, can still carry all three loads.

- After a reshard. After a cluster layout change, one service shows a high error rate until it restarts. Explain the mechanism with CRC16 slots. Say what a correct client does with MOVED that the failing one did not, and why a restart fixed it.
Answer sketchA key's slot is CRC16(key) mod 16384, and the change moved some slots to other masters. The client's map still pointed at the old owners, so they answered MOVED, not nil. A correct client retries at the address in MOVED and updates its map, and follows ASK with ASKING once. The failing client treated MOVED as an error or refreshed its map rarely. A restart loaded a fresh map. The real cause in that use case was not checked.

- One round trip. You need one MGET of a tenant's profile, settings and five session keys on a cluster. Show the key design that makes it legal, name the mechanism, and the risk you accept if one tenant has 90% of the traffic.
Answer sketchPut the tenant in a hash tag, for example {tenant42}:profile, {tenant42}:settings and {tenant42}:session:1. Only the text in braces is hashed, so all seven keys share one slot and one master. The risk is a hot slot: one master carries 90% of the traffic, and adding shards does not spread it.

- Events after the move. A notification feature subscribes to keyspace expiry events through the configuration endpoint. It worked on one primary. After a move to a three-shard cluster, it sees about one third of the events. Why? Then explain why plain PUBLISH does reach a subscriber on another node, and what SPUBLISH changes.
Answer sketchKeyspace events are raised on the node that holds the key and are not sent to other nodes. The endpoint connected the subscriber to one of three masters, so it sees that node's third. Subscribe on every master. Plain PUBLISH is broadcast to every node over the cluster bus. SPUBLISH keeps a message inside the shard of its channel's slot, which cuts that broadcast cost. Turning on cluster mode changes behaviour for code that already works.

- A restart with persistence off. Your primary runs with persistence off and two replicas. A supervisor restarts it 2 seconds after a crash. Sentinel uses down-after-milliseconds 30000. What do the two replicas hold 10 seconds later?
Answer sketchNothing. The primary came back empty with a new replication ID before Sentinel acted. The replicas asked for a full resync, flushed their data and loaded the empty dataset. A local run went from 10,000 keys to 0 in about 5.3 s, after the 5-second diskless delay.

- A 3-second blip. The primary takes 20 MB/s of writes, and a replica's link drops for 3 seconds. The backlog has its default size. Partial or full resync? What changes on Valkey 9.1.2, and what backlog would make it partial?
Answer sketchThe gap is 60 MB. The Redis default backlog is 1 MB, so it is a full resync. Valkey's default of 10 MB still gives a full resync. A backlog above 60 MB, with a margin, keeps it partial.

- A region failover. Your platform keeps session state and a lock per run in one region's Redis, with an async read-only standby in a second region. The region fails. In the last second it acknowledged 40 session writes and 1 run lock that had not replicated. (a) What do those 40 users see after you promote the standby? (b) What can now happen to that run? (c) Your cross-AZ read bill is $3,000 a month on a $1,000 cluster. Which client change removes most of it, and why?
Answer sketch(a) The 40 sessions were not on the standby, so those users are logged out and sign in again. (b) The lock was not replicated, so a second worker in the new region runs SET lock NX, gets it, and runs the same run the first worker still holds. Two workers run one run. (c) Pin reads to a same-AZ replica. Cross-AZ transfer is billed in each direction and same-AZ transfer is free, so a same-AZ read removes the cross-AZ part. The Valkey test cut $4,373 to $1,088 this way.

- One user, one wipe. A teammate creates one cache user: ACL SETUSER cache on >pw resetkeys ~cache:* -@all +@read +@write +@connection. (a) What command still erases every key, and why does ~cache:* not stop it? (b) The one rule you add, and where it must go. (c) A separate cluster runs with no tls-cluster and an attacker can reach the bus port. What single CLUSTER command joins their host, and which Redis 8.10.2 setting would have refused to start the node?
Answer sketch(a) FLUSHALL (also FLUSHDB, SWAPDB). These take no key, so the ~cache:* pattern never applies, and +@write allows them. (b) Add -@dangerous after the plus rules, because rules apply left to right and a minus placed before +@write would be undone. Add -@scripting too, because +@write also grants FUNCTION LOAD. (c) CLUSTER MEET <host> <port> adds the host as a trusted node. cluster-bus-port-protected-mode yes makes the node refuse to start without tls-cluster.

## Cheatsheet

Open the cheatsheet
PERSISTENCE (what a crash loses)
  RDB  = fork + snapshot (save N M). Crash loses SINCE LAST SNAPSHOT.
  AOF  = write(2) before the reply (normal case), fsync later.
    everysec: kill -9 loses ~0; power loss ~1 s.
    slow disk: kill -9 up to ~2 s; power loss 2 s or more.
    always: ~0, one fsync per reply.  no: Linux flushes ~every 30 s.
  multi-part AOF since 7.0: BASE (RDB format) + INCR files + manifest.
  persistence off + auto restart = EMPTY primary -> replicas flush too.
  ElastiCache: appendonly not modifiable. Durability = replica + snapshots.
    Valkey 9.0+ durability-enabled: Multi-AZ log, 0 loss for sync writes.

REPLICATION (async)
  OK = primary has it in memory. Replicas ACK offsets ~1/s (lag in whole s).
  WAIT n timeout     -> count of replicas past your offset. Not a guarantee.
  WAITAOF l r timeout (7.2) -> waits for AOF fsync, local and replicas.
  min-replicas-to-write N + min-replicas-max-lag M -> refuse writes (NOREPLICAS).
  fixed WAIT 2 with 1 replica = full timeout on EVERY write.
  read connected_slaves; set N per environment. Replicas are READONLY.

RESYNC
  PSYNC replid offset -> partial (+CONTINUE) if the gap is in the backlog.
  repl-backlog-size: Redis 1 MB, Valkey 10 MB. Need > rate x gap.
  full resync = fork + whole RDB + buffer.  replica buffer 256mb 64mb 60.
  Redis 8: RDB channel (buffer moves to replica). Valkey: dual-channel, off.
  repl-diskless-sync yes, delay 5 s.

FAILOVER
  Cluster: cluster-node-timeout 15000 -> PFAIL -> FAIL (majority of masters)
    -> delay 500 + rand(500) + 1000 x rank ms -> masters with slots vote,
    need size/2 + 1. Local run: first good write ~24 s.
  >= 3 masters. 2 of 3 masters dead -> no failover. 1 shard -> none.
  Sentinel: down-after-milliseconds 30000. Quorum detects, majority elects
    a leader. Pick: skip long-disconnected, then priority, offset, run ID.
  ElastiCache: AWS decides, least lag, DNS of primary endpoint moves.
  Clients: bounded pool, backoff + jitter, config endpoint, rare discovery.

CLUSTER MODE
  slot = CRC16(key) mod 16384. Only the first {...} is hashed.
  wrong node -> MOVED slot host:port (follow + refresh map). Never nil.
  migrating, key gone -> ASK (send ASKING once). partial multi-key -> TRYAGAIN.
  keys in different slots -> CROSSSLOT.
  database 0 only (Valkey 9.0 allows more). PUBLISH -> every node.
  SPUBLISH (7.0) -> one shard. Keyspace events -> per node, subscribe on all.
  atomic slot migration: Redis 8.4 CLUSTER MIGRATION, Valkey 9.0.
  choose: data, write rate and main-thread CPU fit one node? yes -> 1 primary.

MULTI-REGION & AZ
  cross-AZ transfer billed EACH direction (~$0.01/GB per direction, us-east-1).
    same AZ = $0.00. cross-Region out of us-east-1 ~= $0.02/GB.
  read from a SAME-AZ replica: Valkey test 800us -> 300us, $4,373 -> $1,088.
    go-redis v9.5.1: RouteByLatency only. Lettuce: ReadFrom.subnet().
    Valkey GLIDE: AZ_AFFINITY + client AZ. server AZ: Valkey availability-zone (8.0).
  cross-region: no multi-primary in open source. Global Datastore = 1 writable
    Region, manual promote, no autofailover. Active-Active (CRDT) = Redis Enterprise.
  region failover loses the unreplicated window:
    sessions -> re-login. locks -> two holders. counters -> extra quota. caches -> cold.
  Uber: copy KEYS not values to warm a standby Region.

SECURITY
  trust model: Redis trusts the network. protected-mode yes + default nopass
    -> reject non-loopback. A password on default turns protected mode OFF.
  one ACL user per service: -@all +@read +@write +@connection -@dangerous -@scripting
    key pattern ~x:* does NOT limit FLUSHALL/FLUSHDB/SWAPDB (no key) -> need -@dangerous.
    +@write grants FUNCTION LOAD/FLUSH (Lua) -> -@scripting removes them. EVAL is not in @write.
    SCAN still LISTS names outside the pattern. ACL LOG logs denials.
  TLS: off by default. tls-auth-clients-user CN -> ACL user (no match -> stays DEFAULT + ACL LOG tls-cert).
    tls-replication / tls-cluster separate, default no.
  cluster bus: no auth without tls-cluster. MEET from any host joins it.
    a client password stops the rogue's replication, NOT its slot takeover.
    cluster-bus-port-protected-mode (8.10.2, default NO) -> refuse start without tls-cluster.
  dangerous OFF by default (7.0+): DEBUG, MODULE LOAD, CONFIG SET dir. rename-command deprecated.
  8.10.1 and 8.10.2 are SECURITY releases. 8/29 recent CVEs are Lua -> drop @scripting.

INVESTIGATE
  INFO replication / ROLE  -> role, connected_slaves, offset, lag, link status
  INFO persistence         -> rdb_last_save_time, aof_enabled, aof_delayed_fsync
  INFO stats               -> latest_fork_usec
  CLUSTER INFO / CLUSTER SHARDS / CLUSTER KEYSLOT key
  aws elasticache describe-replication-groups
  ACL LIST / ACL DRYRUN user cmd / ACL LOG   -> what each user may do, and denials
  CONFIG GET availability-zone (Valkey) / tls-* / cluster-bus-port-protected-mode

## Sources

The phase's references, the study note's sources and the production cases. The study note read them on 2026-10-18, and the course research fetched the extra cases on the same day.

Open the sources
Redis documentation

- https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/ RDB, AOF, the appendfsync modes, multi-part AOF and the BACKUP commands. Read it before the first concept.

- https://redis.io/docs/latest/operate/oss_and_stack/management/replication/ Asynchronous replication, the replication ID, partial and full resync, min-replicas-to-write, and the restart with persistence off.

- https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/ Quorum, leader election, replica selection and the partition example with lost writes.

- https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/ Slots, hash tags, MOVED and ASK, replica election, write safety and pub/sub. Read "Key distribution model" and "Redirection".

- https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/ The cluster tutorial: create a cluster, reshard it and kill a master.

- https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/ Fork time per GB, and the AOF write postponed for up to two seconds.

- https://redis.io/commands/wait/ and https://redis.io/commands/waitaof/ What WAIT and WAITAOF count, and "Consistency and WAIT".

- https://redis.io/commands/cluster-keyslot/ Check a key's slot and the hash-tag rule.

- https://redis.io/commands/info/ The INFO replication and INFO persistence fields.

- https://redis.io/docs/latest/develop/pubsub/ and https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/ Sharded pub/sub, and "Events in a cluster".

Source code and release notes

- https://raw.githubusercontent.com/redis/redis/8.10.2/src/server.c and https://raw.githubusercontent.com/redis/redis/8.10.2/src/aof.c The AOF write before replies, and the 2,000 ms postpone.

- https://raw.githubusercontent.com/redis/redis/8.10.2/src/cluster.c and https://raw.githubusercontent.com/redis/redis/8.10.2/src/cluster_legacy.c MOVED, ASK, TRYAGAIN, CROSSSLOT, failure detection, the election delay and who votes.

- https://raw.githubusercontent.com/redis/redis/8.10.2/src/config.c, https://raw.githubusercontent.com/redis/redis/8.10.2/redis.conf and https://raw.githubusercontent.com/redis/redis/8.10.2/sentinel.conf The defaults quoted in this lesson.

- https://raw.githubusercontent.com/redis/redis/8.10.2/00-RELEASENOTES Atomic slot migration in redis-cli --cluster reshard, and the release notes of 8.0.0 and 8.4.0 for RDB channel replication and CLUSTER MIGRATION.

- https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/valkey.conf Valkey defaults, including the 10 MB backlog and dual-channel replication.

- https://github.com/redis/redis/issues/2576 antirez on why there are 16,384 slots.

AWS

- https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/AutoFailover.html Multi-AZ failover, the least-lag replica, the DNS change, the reboot that clears data, and durability-enabled Valkey clusters. The phase linked the older address https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/AutoFailover.html.

- https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/ParameterGroups.Engine.html appendonly not modifiable, and the volatile-lru default.

- https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/Replication.Redis-RedisCluster.html Cluster mode enabled against disabled.

- https://aws.amazon.com/blogs/database/best-practices-redis-clients-and-amazon-elasticache-for-redis/ Client rules: bounded pools, backoff with jitter, discovery through the configuration endpoint.

- https://www.amazon.science/publications/amazon-memorydb-a-fast-and-durable-memory-first-cloud-database MemoryDB: the cost of a durable log, and fork measurements.

Production cases

- https://aphyr.com/posts/283-call-me-maybe-redis Jepsen: 1,998 writes acknowledged and 872 survived.

- https://www.twilio.com/en-us/blog/company/communications/billing-incident-post-mortem-breakdown-analysis-and-root-cause-html and https://www.antirez.com/news/60 Twilio: mass full sync, then an empty restart.

- https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/ Stack Overflow: a replication fork with 6 GB of headroom.

- https://redis.io/blog/the-endless-redis-replication-loop-what-why-and-how-to-solve-it/ Why a large dataset can resync without end.

- https://gitlab.com/gitlab-com/gl-infra/production/-/issues/706 GitLab: replica output buffer limit and two full resyncs.

- https://www.gomomento.com/blog/why-snap-was-willing-to-fork-and-why-they-still-came-back/ Snap: a full sync that repeated, in a vendor summary.

- https://redis.io/blog/february-8th-outage-post-mortem/ Redis Cloud: a majority of nodes lost, and databases without persistence back empty.

- https://engineering.grab.com/preventing-pipeline-calls-from-crashing-redis-clusters Grab: one replica failure, and 1 in 21 calls succeeded.

- https://status.webflow.com/incidents/7pbl0qlc61kf Webflow: an application pointed at one node.

- https://engineering.bsport.io/how-we-eliminated-redis-as-a-single-point-of-failure-2729c22008b5 bsport: retries that overloaded DNS.

- https://www.figma.com/blog/postmortem-service-disruptions-on-june-6-and-7-2022/ Figma: pub/sub on clustered ElastiCache at 100% CPU.

- https://gitlab.com/groups/gitlab-com/gl-infra/-/epics/878 and https://runbooks.gitlab.com/redis-cluster-ratelimiting/ GitLab: from Sentinel to Redis Cluster because of CPU.

- https://www.slideshare.net/RedisLabs/redisconf18-2000-instances-and-beyond Lyft: 2,000 instances with no persistence by choice.

- https://github.blog/engineering/infrastructure/moving-persistent-data-out-of-redis/ GitHub: data that existed only in Redis moved to MySQL.

Multi-region and AZ (4.7)

- https://aws.amazon.com/elasticache/pricing/ No charge for traffic in or out of the node itself, and application traffic across an AZ is billed. The Global Datastore example charges $0.02/GiB out of the primary Region.

- https://valkey.io/blog/az-affinity-strategy/ The 300 us vs 800 us read, and the $4,373 to $1,088 cut with AZ affinity (vendor source).

- https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/Redis-Global-Datastore.html One writable primary Region, read-only secondaries, asynchronous replication, promotion for disaster recovery.

- https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/Redis-Global-Datastores-Getting-Started.html Up to two secondary Regions, and no autofailover across Regions. Read the promotion bullet.

- https://www.uber.com/en-GB/blog/how-uber-serves-over-40-million-reads-per-second-using-an-integrated-cache/ Uber CacheFront: copy keys, not values, across Regions (vendor source).

- https://blog.cloudflare.com/a-byzantine-failure-in-the-real-world/ Cloudflare dashboard sessions in Redis that could not move Regions.

Securing Redis (4.8)

- https://redis.io/docs/latest/operate/oss_and_stack/management/security/ The trust model, protected mode, and the code-security notes on CONFIG and dir.

- https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/ Users, categories, key and channel patterns, selectors, and ACL LOG.

- https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/ tls-auth-clients, tls-replication, tls-cluster, and the certificate files.

- https://www.wiz.io/blog/wiz-research-redis-rce-cve-2025-49844 The Lua RCE CVE-2025-49844, why dropping @scripting reduces risk, and exposed-instance counts (vendor source).
In Phase 4 you kept the order system and the task queue fast on one PostgreSQL 17 server. You read its plans, kept VACUUM ahead of dead rows, and ran migrations without stopping the table. Now that server runs on a managed service, as a primary with two streaming replicas. One replica is the failover standby. The other serves reads: the order status page, reports, and the search over agent run history.

PgBouncer, a connection pooler, sits between about 40 application processes and the database, in transaction mode. A change-data-capture connector, CDC for short, reads every committed change and feeds the search index. Each of these parts can fail on its own, and each failure has a cause you can read before it happens. This lesson follows one bad day of that system.

- 09:00 The search team pauses the CDC connector to rebuild the index. Its replication slot stays on the primary.

- 10:05 An agent run writes its result on the primary. The UI reads it from the read replica 40 ms later and gets 404.

- 11:30 A report on the read replica fails with canceling statement due to conflict with recovery.

- 14:00 A disk alert fires on the primary. pg_wal holds 176 GiB and grows by 10 MiB each second.

- 15:10 The primary's host dies. The standby is promoted after 90 s. About 1 MiB of WAL never reached it.

- 15:12 Every pool reconnects at once. New connections get remaining connection slots are reserved, and the on-call engineer cannot log in.

- 16:40 A migration empties a table by mistake. Can the team restore to 16:39?

The running case. Times and sizes are an illustration, not measured. Each section below explains one line.

Seven failures share two causes. Copies of the WAL lag, are kept too long, or are missing. And connections are opened without a budget. Both causes are numbers you can read: a gap between two WAL positions in bytes, and a count of connection slots. Most failures on that list have also happened to a named company, and the sections below tell those cases. The full disk from a slot is the exception, because no published postmortem of it was found, so that outage is predicted from the docs.

Every default, view, log line and source line here is for PostgreSQL 17.11. Where 16 or 18 differs, one sentence says so. On a managed service you do not run most of the commands yourself. So each section also says where you meet the idea on RDS or Aurora. It says what you see when it goes wrong, and the decision it changes.

What you must know, in five claims. Each one is taught below, in this order.

- A replica read and a failover see the same byte gap, and with no synchronous standby named, OK leaves it open. Read a standby's positions, fix read-after-write, and state what a failover loses.

- A replication slot keeps every WAL byte its reader has not confirmed, so a stopped reader fills the primary's disk. Predict the time to a full disk, set the cap, and keep a CDC slot through a failover.

- On a busy table, a read replica must cancel a long query, delay replay, or bloat the primary. Choose a role for each replica and name what each choice costs.

- Point-in-time recovery needs a base backup, an unbroken WAL archive and a restore you have already timed. Pick the backup and the target, and know your restore time before you need it.

- Every server connection is a process from a fixed budget, and transaction pooling hands session state to the next client. Budget the pools, keep a slot for operators, and keep session state out of the pooler.

## What you bring from Phases 1, 3 and 4

  The WAL and the LSN

In Phase 1, on durability, every change became a record in the write-ahead log, the WAL, before the data files changed. A log sequence number, LSN for short, is a byte position in that log, written as two hex numbers such as 5/3A000000. The difference of two LSNs is a number of bytes.

  The commit order

Phase 1 also gave the commit order. A commit waits until its WAL record is flushed to the local disk. With a synchronous standby it then waits again, in a function named SyncRepWaitForLSN. synchronous_commit = off replies before the flush and can lose up to 600 ms of commits.

  Checkpoints and WAL files

A checkpoint writes changed pages to the data files and moves the start of crash recovery forward. Older WAL files can then be removed or reused. Each file in pg_wal is a segment of 16 MB, and max_wal_size, 1 GB by default, is only a soft target.

  Snapshots and the cleanup horizon

In Phase 3, on transactions, a snapshot decided which row versions a query sees. Phase 4, on vacuum and migrations, showed that VACUUM removes a dead version only when no open snapshot can still see it. So the oldest snapshot anywhere holds cleanup back, and the table bloats.

  Connection slots and the Railway case

Phase 4 also told the Railway case. An index build held a lock, requests queued with a connection each, and the pooler opened more connections than the server allowed. With the defaults, 100 slots minus 3 for superusers leave 97 for every other role.

  Generic plans and pool sizing

In Phase 4 a prepared statement got five custom plans, and then possibly one generic plan. Phase 4 also said that behind a pooler the count is kept per server connection, and the pooling sections show why. The elite-performance course used Little's law for pools. Busy connections equal requests per second times the seconds each request holds its connection.

This phase needs the first three ideas for replicas, slots and backups, and the last three for read replicas and pooling. The Redis course taught asynchronous replication and the writes a failover loses, in its parts on replication and on failover. PostgreSQL has the same window, and this lesson gives its exact size and the settings that close it.

## Where is the standby behind, and in which stage?

At 10:05 the UI read a row that the primary had committed, and the replica said the row did not exist. Nothing was broken. A streaming replica is always somewhat behind the primary, so the useful questions are how far, at which stage, and for which reads that matters.

A physical standby is a second PostgreSQL server that replays the primary's WAL. It holds the same files, byte for byte, so it runs the same major version and cannot take writes. On the standby, a WAL receiver process takes the WAL over the network and writes it to disk. On the primary, a WAL sender process reads the WAL and sends it. The primary streams records as they are written, without waiting for a segment to fill. Streaming is asynchronous by default, so a commit returns to the client before any standby has its record.

- currentthe primary wrote the record. pg_current_wal_lsn()

- sentthe WAL sender sent it. sent_lsn

- writethe standby wrote it to the OS cache. write_lsn

- flushthe standby flushed it to disk. flush_lsn

- replayqueries on the standby can see it. replay_lsn

One commit record on its way to a standby. Each arrow is a gap in bytes. pg_stat_replication on the primary shows the last four positions, and the function gives the first.

Predict: your service writes an order on the primary, and another service reads it from the read replica 5 ms later. synchronous_commit is on, the default. Can the read miss the order?
Yes. With no synchronous standby named in synchronous_standby_names, the default, on waits only for the flush on the primary's own disk. The commit returns, and the record may still sit in any of the four gaps above. So the 5 ms read can run before the replica has replayed it. The guess "no" is reasonable, because on sounds like it covers the replica. For the answer to become no, a synchronous standby must be named and the level must be remote_apply, and the read must go to that standby. A later section gives what each level costs.

The positions always come in one order: current, then sent, then write, then flush, then replay. Each gap between two neighbours points at one part of the system, so you read the largest gap first.

- The standby sends a status reply with its write, flush and replay positions. It sends one each time its write or flush position changes, and at least every 10 seconds.

- The primary keeps the latest reply in pg_stat_replication, one row per standby. So write_lsn and flush_lsn stay fresh while WAL flows, and replay_lsn can be slightly older.

- The gap from current to sent grows when the primary is busy, or when the WAL sender is slow to read WAL.

- The gap from sent to flush grows when the network is slow, or when the standby is slow to receive and write.

- The gap from flush to replay grows when the standby's replay is slow. Replay runs in one process, the startup process, so a primary that writes WAL from many sessions at once can outrun it. Replay also stops while it waits for a query on the standby, which the read-replica sections explain.

The lab's lag.py prints every gap and names the largest. Here the standby has received everything, and its replay is 30 MiB behind.

uv run python phase05_replication/lag.py --current 5/3A000000 --sent 5/39F00000 \
    --write 5/39E00000 --flush 5/39E00000 --replay 5/38000000 --wal-rate-mb 8

stage              bytes behind     where to look
current -> sent        1,048,576  ~0.12 s   primary busy, or the WAL sender is slow to read WAL
sent -> write          1,048,576  ~0.12 s   network, or the standby is slow to receive
write -> flush                 0  ~0.00 s   the standby's disk flush
flush -> replay       31,457,280  ~3.75 s   the standby's startup process: replay is slow or waits on a query conflict
total current -> replay: 33,554,432 bytes
largest gap: flush -> replay, 31,457,280 bytes

The LSNs are an example. The seconds are an estimate, because 31,457,280 bytes is 30 MiB, and at 8 MiB/s of WAL that is 3.75 seconds of the primary's work. The query behind the table runs on the primary. pg_wal_lsn_diff subtracts two LSNs and returns bytes.

-- On the primary, PostgreSQL 17. One row per standby or WAL client.
SELECT application_name, state, sync_state,
       pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn)   AS send_gap_bytes,
       pg_wal_lsn_diff(sent_lsn, flush_lsn)              AS net_and_disk_bytes,
       pg_wal_lsn_diff(flush_lsn, replay_lsn)            AS replay_gap_bytes,
       write_lag, flush_lag, replay_lag, backend_xmin
  FROM pg_stat_replication;

A standby that is missing from this view is not connected at all, and that is a different failure. On the standby, pg_stat_wal_receiver.status then is not streaming, or the view has no row.

Where do you meet it, and what does it change?

You meet this gap the first time a read replica serves a page that must show a fresh write, such as an order status or a run result. On a self-hosted server you read the byte gaps with the query above. On RDS and Aurora you mostly see a lag metric in time, and the next section shows why that number can mislead. The gap you see in bytes is the same gap a failover loses. So one reading answers two questions. Which reads may go to this replica, and how much would a promotion lose right now? A large flush-to-replay gap sends you to the replica's queries and its replay process, not to the network.

A gap in bytes says where the standby is behind. It does not yet say how many seconds of commits that is, and the next section shows why the usual time query gives a wrong answer.

Go deeper: the status reply, the older file transport, settings that must match, and WAL fan-out at scale
The status reply

The standby sends its reply at least every wal_receiver_status_interval, 10 seconds by default, and after each batch of WAL it writes. The docs for that setting add that a reply goes out each time the write or flush position changes. They also warn that the apply position may lag slightly behind the true position. So read replay_lsn as a lower bound on what the standby has applied.

File-based log shipping

A standby can also read whole 16 MB segment files from the WAL archive with restore_command. That is file-based log shipping. It is slower, because a segment ships only when it is full. Streaming uses the archive only to catch up when the primary has already removed the WAL that the standby needs. The slot sections show when that happens.

A physical copy replicates everything

A physical standby copies the whole cluster, every database, and replays every change. Some settings must match the primary. The docs for max_connections say that a standby must have the same or a higher value than the primary, or queries are not allowed on it. Twitch met this rule. Raising max_connections meant raising it on every replica first, which needs a restart, and then failing over to a primary with the new value. Logical replication, which sends row changes per table, is the other kind of replication. The slot sections meet it through its slots.

WAL fan-out to many replicas

OpenAI runs one Azure PostgreSQL primary with nearly 50 read replicas in several regions. They write that the primary must ship WAL to every replica. That adds network and CPU load, and it makes replica lag higher and less stable. They are working with Azure on cascading replication, where some replicas relay WAL to other replicas. So the current-to-sent gap can grow with the number of replicas, not only with the write rate. That is inferred from their post.

Evidence
PostgreSQL 17 docs, section 26.2.5, for streaming "as they're generated" and "asynchronous by default", and section 26.2.5.2 for what the two gaps "might indicate". Section 19.6.3 for wal_receiver_status_interval. guc_tables.c at REL_17_11 for the 10-second default. The column names are from system_views.sql at REL_17_11, lines 893 to 917. lag.py output from the author's run on 2026-10-20. Twitch: "How Twitch uses PostgreSQL", 2016-10-11. OpenAI: "Scaling PostgreSQL to power 800 million ChatGPT users", 2026-01-22, archive copy.

## Why does lag in seconds lie, and how do you read your own write?

The byte gaps say where a standby is behind, but a pager rule and a product decision need seconds. PostgreSQL gives two kinds of time lag, and the common one is wrong whenever the primary is quiet.

pg_stat_replication has three time columns, write_lag, flush_lag and replay_lag. Each one is the time between the primary flushing recent WAL and hearing that the standby wrote, flushed or applied it. They are not predictions of how long the standby needs to catch up. When the primary goes idle, they show their last value for a short time and then show NULL.

The common query on the standby is now() - pg_last_xact_replay_timestamp(). That function returns the commit time of the last transaction the standby replayed. When the primary stops committing, the value stops moving, while the clock keeps running. So the reported lag grows on a standby that has every byte.

  Alert on the time since the last replayed commit.

-- WRONG: grows on an idle primary although nothing is missing
SELECT now() - pg_last_xact_replay_timestamp() AS lag;

primary idle after t=0. received == replayed check: off
   t (s)   byte lag   reported time lag (s)
       1          0          1.0
      10          0         10.0
      60          0         60.0
     290          0        290.0

  Check the bytes first, then the clock.

-- RIGHT: zero when the standby has replayed all it received
SELECT CASE WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn() THEN interval '0'
            ELSE now() - pg_last_xact_replay_timestamp() END AS lag;

primary idle after t=0. received == replayed check: on
   t (s)   byte lag   reported time lag (s)
       1          0          0.0
      10          0          0.0
      60          0          0.0
     290          0          0.0

Both tables come from lag.py --idle-demo, the first with --no-idle-check. The standby has every byte, and the wrong query reports almost 5 minutes, so a pager rule on 60 seconds fires every quiet night. The right query has one blind spot. A standby whose WAL receiver has stopped also shows received equal to replayed. So alert on pg_stat_wal_receiver.status as well, and on the primary's byte gap. That pair of checks is inferred from the function definitions and was not run.

Where do you meet it, and what does it change?

On RDS for PostgreSQL you meet this as the CloudWatch metric ReplicaLag. RDS computes it as the current time minus the time of the last committed transaction, so it has the same flaw. AWS says that with no user transactions on the source, a read replica reports a lag of up to five minutes. The value then resets, because the source switches WAL segments every 5 minutes by default, and the switch writes a record. What you see is a sawtooth of up to 300 seconds on a quiet night, with no missing data. The decision it changes is the alert. Alert on a byte gap, or on time lag only while the source is busy, so the team does not learn to ignore lag pages.

Aurora works differently. Its replicas read the same cluster volume as the writer, which AWS calls a single logical volume. So a replica keeps no copy of the data of its own. That is inferred from that sentence. Its lag metric is AuroraReplicaLag, in milliseconds. AWS says it is usually much less than 100 ms after the writer has written an update, and that it grows with the write rate.

How do you read a row right after writing it?

The 10:05 line of the running case is a published failure. At Dyte, one service created a meeting participant on the primary. A second service then read that participant from a replica to make an auth token. Under high load, replication lag rose, and the create-participant route returned 404 with "participant not found".

- t=0 ms Service A commits INSERT participant on the primary and gets OK.

- t=2 ms Service A calls service B with the participant id.

- t=5 ms Service B reads the id from the replica. The replica's replay_lsn is behind the commit's LSN, so it finds 0 rows and returns 404.

- t=40 ms The replica replays the commit, too late for this request.

Read-after-write across two services. Times are an illustration, not measured. Low lag in development hides the bug.

Dyte made the lag large on purpose in development, with recovery_min_apply_delay on a test replica, so the bug showed up before production did. Their fix was a cache. Each new participant is also written to Redis, with a time-to-live longer than their upper bound on replication lag. An alert fires when the lag passes that bound. The cache only works while the alert does. Here are the other fixes, ordered by how often they fit.

- Read your own recent writes from the primary. Route a session's reads to the primary for a few seconds after it writes. Pick the window above your measured lag. This is common practice, not a PostgreSQL feature.

- Wait for the LSN. After the commit, the writer reads pg_current_wal_lsn() and passes it on. The reader waits until pg_last_wal_replay_lsn() on the replica reaches it, with a short timeout, and then falls back to the primary. This is inferred from the function definitions and was not run.

- Wait at commit. synchronous_commit = remote_apply makes the commit wait until a synchronous standby has applied it. It costs commit time, and only synchronous standbys count. The next section has the numbers.

Phase 3 showed one more limit of replica reads. A replica makes commits visible in WAL order, which can differ from the order clients saw on the primary. That is why a test across the primary and a reader endpoint found anomalies that one server cannot show.

All three fixes trade something for the gap, and the third one moves the wait into the commit itself. The next section asks what an OK means once a standby can be part of the commit.

Go deeper: the lag columns in detail, and a grep for reads that follow a write
The three lag columns are measured on the primary from the standby's replies. They show recent history, so a standby that stops replying keeps its last value until the primary drops it. When the primary is idle they become NULL after a short time, which the docs state, and which E10 in the lab asks you to watch. Use them for a graph of a busy system, and the byte gap for an alert.

To find read-after-write bugs in your own code, look for reads that follow a write in the same request. A grep such as grep -rn "replica\|read_only\|using('replica')" <your repo>/ finds routing code in many frameworks. For each hit, name which of the three fixes it needs. Rails, Django and SQLAlchemy defaults for this routing were not checked, so read your framework's own docs before you rely on one.

Evidence
PostgreSQL 17 docs, section 27.2.4, for the lag columns, "not predictions", and NULL when idle. Section 9.28.4 for pg_last_xact_replay_timestamp. The idle tables are from lag.py, run on 2026-10-20. AWS, "Read replicas for RDS for PostgreSQL", for the five-minute idle lag and the ReplicaLag formula. AWS Aurora replication page for the single logical volume and "usually much less than 100 milliseconds". Dyte, "Learning to Live With Replication Lag", 2023-04-03, archive copy, for the 404, recovery_min_apply_delay and the Redis TTL. The post gives no lag number and no PostgreSQL version. Phase 3 of this course has the Jepsen result on RDS Multi-AZ readers and AWS's reply.

## What does OK mean when the primary has a standby?

The read-after-write fixes ended at a commit that waits for a standby. At 15:10 in the running case the primary died, and about 1 MiB of WAL had not reached the standby. Every commit in that WAL had already returned OK to its client, and with the defaults that loss is expected.

Phase 1 asked you to state your durability boundary for one server. With standbys, two settings move that boundary. synchronous_standby_names, set on the primary, says which standbys a commit may wait for, and its default is empty. synchronous_commit, which each transaction can set, says how far the commit record must travel before the client gets OK.

- offWAL buffer on the primary. No wait

- localflushed to the primary's disk

- remote_writein the standby's OS cache

- onflushed to the standby's disk

- remote_applyreplayed, so standby queries see it

How far the commit record travels before OK, for each level. With synchronous_standby_names empty, local, remote_write, on and remote_apply all stop at the primary's disk.

The lab's commit_levels.py prints the five levels with what a client that got OK can lose in each failure. The loss columns follow the PostgreSQL docs' own table, column by column.

synchronous standby configured: True. Inputs are examples, not measurements.
level         wait ms  primary restart          failover                        failover, standby OS crash              read on standby
off           0.00     up to 600 ms of commits  commits in the replication lag  commits not yet flushed on the standby  may not see it yet
local         1.00     nothing                  commits in the replication lag  commits not yet flushed on the standby  may not see it yet
remote_write  2.05     nothing                  nothing                         commits not yet flushed on the standby  may not see it yet
on            3.00     nothing                  nothing                         nothing                                 may not see it yet
remote_apply  3.50     nothing                  nothing                         nothing                                 sees it

- remote_write keeps the commit if the standby's PostgreSQL crashes, but not if the standby's operating system crashes, because the record may still be only in the OS cache.

- on loses the commit only if the primary and every synchronous standby lose their storage.

- remote_apply waits until the commit is visible to queries on the standby. That is the third read-after-write fix of the section above.

Why is the default the row that matters?

With synchronous_standby_names empty, the docs say remote_apply, remote_write and local all give the same local level as on. That is the default, so synchronous_commit = on there means the same as local. A failover then loses the commits in the replication lag, and the docs say the loss is proportional to the replication delay at the moment of failover. For the running case, 1 MiB of WAL at 10 MiB/s is about 0.1 seconds of commits.

What does a stronger level cost in time?

A physical WAL sender sends only WAL that the primary has already flushed, because sending WAL that is not on the primary's disk would be unsafe. So a synchronous commit pays the local flush, then a network round trip, then the standby's step. The floor is one round trip. The lab's example inputs are a 1 ms local flush, a 1 ms round trip, a 1 ms standby flush and 0.5 ms of replay. With a standby in another region, at a 70 ms round trip, on waits 72 ms per commit.

  What one synchronous commit waits for

  Local flush, microseconds
  Round trip to the standby, ms
  Standby flush, microseconds
  local waits , on waits . One hot row then takes at most  commits per second, against  with local.

Move the inputs. The defaults are the lab's example inputs, not measured. The row limit assumes each commit holds the row's lock until it returns.

The row limit in the box comes from a second cost. The docs say transaction locks stay held until the standby confirms the transfer. So a hot row that every commit updates, such as a counter, stays locked for the round trip too. Its update rate falls as the commit time grows. That bound is inferred from the docs' sentence and was not measured. Read-only transactions and rollbacks do not wait, and neither do subtransaction commits. Both steps of a two-phase commit do wait.

Can each transaction choose its level?

The level can change at any time, and the value at commit decides. The docs' example is a workload where 10% of changes are customer details and 90% are chat messages, and only the 10% needs to wait.

BEGIN;
SET LOCAL synchronous_commit = remote_apply;   -- this payment must be readable on the replica
UPDATE orders SET state = 'paid' WHERE id = 42;
COMMIT;

SET LOCAL ends with the transaction, so it is inferred to be safe behind PgBouncer in transaction mode, which the pooling sections explain. The reverse, SET LOCAL synchronous_commit = off for a low-value job, is the rule from Phase 1 for giving up durability on purpose.

What does a stronger level cost in availability?

A commit that waits for a standby waits for as long as it takes. If the only synchronous standby crashes, such commits may never complete. So name more standbys than you wait for. FIRST 1 (s1, s2) waits for s1, and s2 takes over when s1 is gone. ANY 2 (s1, s2, s3) waits for any two of the three. The lab's model checks both rules.

synchronous_standby_names = 'FIRST 1 (s1, s2)', down: ['s1', 's2']
commits that wait for a standby BLOCK until enough standbys return.
a client that cancels the wait gets:
  WARNING:  canceling wait for synchronous replication due to user request
  DETAIL:  The transaction has already committed locally, but might not have been replicated to the standby.

While a session waits, pg_stat_activity shows wait_event_type IPC and wait_event SyncRep. Read the DETAIL line again, because it describes a commit that is already in the primary's WAL and visible to other sessions. Only the standby may lack it. Patroni's docs say that a transaction can still be lost even in its strictest synchronous mode, for this reason. A failover at that moment loses a commit that other clients have already read. A statement timeout or a driver timeout that cancels the wait is inferred to give the same warning, because both raise a cancel. This was not run.

Where do you meet it, and what does it change?

On a managed service you do not type these settings. The product you buy decides the gap, and each one promises a different sentence.

ServiceWhat the commit waits forReadable standby

RDS Multi-AZ DB instancea synchronous standby in another Availability Zoneno

RDS Multi-AZ DB clusteracknowledgment from at least one reader, not its replayyes, two readers

Aurora4 of the 6 storage copies across three zones, by the 2017 paper. Not a replicayes, up to 15

RDS read replica you promote by handnothing. Plain asynchronous streamingyes

The phase said an Aurora commit waits for "the write to six storage nodes". The 2017 Aurora paper gives a different rule. The writer sends to all six copies and waits for 4 of the 6 to answer, a write quorum of 4 out of 6. The paper describes Aurora MySQL, so the rule is inferred for Aurora PostgreSQL today. The current AWS page says only that Aurora replicates to six storage nodes.

So a Multi-AZ DB instance failover should lose no acknowledged commit, which is inferred from its synchronous standby. The cluster form waits for a reader to receive the change, not to apply it. So a read on that reader right after the commit can still miss it. A read replica in another region that you promote by hand loses its lag, because RDS uses the native PostgreSQL replication for it. That is inferred from the AWS read replica page. AWS also warns of higher write and commit latency on a Multi-AZ instance than on a Single-AZ one. What you see on the wrong choice is a commit latency step after enabling Multi-AZ, or lost writes after a manual promotion. The decision it changes is which product to buy when the requirement says no acknowledged write may be lost.

Here is the boundary sentence for a self-hosted version of the running case. "With synchronous_commit = on and synchronous_standby_names = 'FIRST 1 (s1, s2)', an OK means the commit record is on the primary's disk and on one standby's disk. A failover to that standby loses nothing. If both standbys are down, commits wait. A commit whose wait is canceled may be visible and still lost."

The level decides what the chosen standby has. The next section follows the failover itself, from the dead primary to the clients on the new one.

Go deeper: the restart case, the docs' exact table, and Patroni's synchronous mode
A restart while commits wait

The docs add one more case. If the primary restarts while commits are waiting for a standby's answer, those transactions are marked fully committed when the primary recovers. So a client that lost its connection during the wait cannot assume the commit failed. It must read the row back to learn the outcome.

Reading the table

The docs list four guarantees per level: a primary crash, a standby PostgreSQL crash, a standby operating-system crash, and a consistent read on the standby. The lab's table turns them into what a client loses in each failure. off can lose up to 600 ms of commits on a primary restart, because the reply goes out before the flush, and 600 ms is three times wal_writer_delay at its default of 200 ms. Run commit_levels.py --no-sync-standby to see every level except off collapse to a 1 ms wait and the same failover loss.

Patroni's synchronous mode

Patroni's synchronous_mode promotes only a replica known to be synchronous. Its docs add two limits. When no synchronous standby is available, the primary still accepts writes without one, unless synchronous_mode_strict is on. And a canceled wait can still lose a commit, as above, because the changes become visible to other sessions when the wait is canceled.

Evidence
PostgreSQL 17 docs, section 19.5.1, for the five levels and the empty-names rule. Section 26.2.8 for "proportional to the replication delay", the round-trip floor, locks held, and what does not wait. Section 26.2.8.4 for commits that "may never be completed" and the restart case. walsender.c at REL_17_11, lines 3240 to 3249, for sending only flushed WAL. syncrep.c lines 320 to 322 for the WARNING and DETAIL. wait_event_names.txt line 156 for SyncRep. The model output is from commit_levels.py, run on 2026-10-20 with example inputs. Patroni replication modes page for synchronous_mode_strict. AWS Multi-AZ DB instance and DB cluster pages for the synchronous standby and the semisynchronous reader. The Aurora quorum of 4 out of 6 is from Verbitski and others, "Amazon Aurora: Design Considerations for High Throughput Cloud-Native Relational Databases", SIGMOD 2017. The AWS read replica page says RDS uses the native replication of PostgreSQL. The study note labels the Multi-AZ no-loss reading inferred.

## What happens in the 90 seconds of a failover, and what is lost?

The commit level decides what the standby has when the primary dies. At 15:10 the primary's host died, writes stopped for 90 seconds, and then the standby took over. In those 90 seconds a program decided the primary was dead, chose a replica, promoted it and moved the clients.

PostgreSQL does only one of these steps itself, the promotion. The docs say it does not provide the software that detects a failure on the primary and tells the standby. A failover manager does the rest. Patroni is common on self-hosted clusters, and RDS and Aurora have their own. All of them run the same five steps, and each step has a default you can read and a failure you can predict.

- 1. detectthe leader lock is not renewed for ttl = 30 s

- 2. choosethe most advanced replica within maximum_lag_on_failover = 1,048,576 bytes

- 3. fencethe old primary must stop taking writes

- 4. promotepg_promote(): recovery ends, timeline 1 becomes 2

- 5. redirectclients reconnect through DNS, a proxy or the pooler

Failover step by step, with Patroni 4.1.5 defaults. Writes fail from the loss until step 5. The WAL the new primary never received is lost, about 1 MiB or more with these defaults.

Step 1: how is the failure detected?

Patroni keeps a leader lock in a distributed configuration store, DCS for short. Fly.io, below, uses Kubernetes as its DCS. The primary must renew the lock before its time-to-live, ttl, runs out. The defaults are ttl 30, loop_wait 10 and retry_timeout 10 seconds, and they must keep the rule loop_wait + 2 * retry_timeout <= ttl. A lost host or network makes the race start 20 to 30 seconds after the failure. There is a slower case. If PostgreSQL crashes but Patroni keeps running, Patroni first tries to restart PostgreSQL on the same host, and it waits up to primary_start_timeout, 300 seconds by default.

Patroni ttl 30, loop_wait 10, retry_timeout 10, primary_start_timeout 300
  primary host or network lost         promotion starts 20 to 30 s after the failure
  PostgreSQL crashed, Patroni alive    promotion starts 300 to 320 s after the failure
managed services, failover time as AWS documents it:
  RDS Multi-AZ DB instance                     typically 60-120 seconds
  RDS Multi-AZ DB cluster                      typically under 35 seconds
  Aurora, with an Aurora Replica               typically less than 60 seconds, often less than 30
  Aurora, no replica: a new primary is created typically less than 10 minutes

That is failover.py --detection. The Patroni upper bounds are the docs' formulas, and the lower bounds are inferred from the same rules. AWS adds that large transactions or a long recovery can make an RDS failover take longer.

Step 2: which replica is chosen?

The safest candidate is the replica with the most WAL. Patroni also refuses a replica that is too far behind. A replica joins the race only if its lag is at most maximum_lag_on_failover, 1,048,576 bytes by default.

  r1: 0/4F00000, 1,048,576 bytes behind
  r2: 0/4000000, 16,777,216 bytes behind
promote r1. WAL lost: 1,048,576 bytes. New timeline 2, history file 00000002.history, first WAL file 000000020000000000000004
old primary needs pg_rewind or a new base backup: True

With r2 alone, the model prints that no replica may be promoted. Writes then stay down until the primary returns, or until an operator decides to lose 16 MiB of commits. One setting makes that choice between availability and data. Patroni measures a replica's lag against the leader's last position stored in the DCS, which can be one loop old. So the real loss can be larger than the setting.

Step 3: how is the old primary fenced?

Two primaries at once is split brain, where each one takes writes that the other lacks. The docs call the fence STONITH, short for "shoot the other node in the head". They say that without it both systems may think they are the primary, which leads to data loss. Patroni fences from the inside, because a leader that cannot renew its lock demotes itself. retry_timeout is the grace, so a DCS or network problem shorter than it does not demote the leader. Phase 1 told GitHub's case of split brain on MySQL, where a 43-second network cut led to primaries in another region and writes on both sides.

The fence has its own failure, because a network that is bad but not dead can cause failovers by itself. At Fly.io, packet loss on transit into one region left some nodes unable to reach Patroni's DCS reliably. That caused leadership churn, with primaries demoting and failovers. At Heroku, false or late database health alerts started automatic remediation. A small subset of customer databases began failover and replacement before engineers turned it off by hand.

Step 4: what does promotion change?

Promotion is pg_ctl promote or SELECT pg_promote(), which waits by default up to 60 seconds. The standby's log then shows these lines.

LOG:  received promote request
LOG:  selected new timeline ID: 2
LOG:  archive recovery complete
LOG:  database system is ready to accept connections

A timeline is a numbered branch of WAL history. Every finished archive recovery and every promotion starts a new one. The timeline ID is the first 8 hex digits of every WAL file name, and a history file, 00000002.history, records where timeline 2 branched off.

timeline 1  ──────────────────────┬──────────────►  old primary kept
0/1000000 ... 0/4F00000           │  0/4F00000 to 0/5000000
                                  │  1 MiB only it has. Never replicated
                                  └──────────────►  timeline 2
                                     new primary, from 0/4F00000
                                     files 00000002000000000000000N

The old primary flushed WAL past the fork point, so it cannot replay timeline 2 as it is. Either take a new base backup onto it, or use pg_rewind, which synchronizes a server after the timelines diverged. pg_rewind needs wal_log_hints = on or data checksums, and neither is on by default in PostgreSQL 17. The commits that only the old primary had are gone after the rewind. If you need them, copy them out of its WAL before you rewind.

Step 5: how do clients find the new primary?

RDS changes the DNS record of the instance to point at the standby. AWS says you must re-establish existing connections, and it recommends a JVM DNS cache of no more than 60 seconds. Twitch ran a PgBouncer cluster in front of the primary. Promoting a new primary meant changing that cluster's configuration and restarting PgBouncer, with a brief window of failing writes.

A client also has to notice that the old primary is gone. If the host vanished without closing its sockets, a pooled connection can wait for TCP to give up. RDS for PostgreSQL sets the server keepalives to an idle time of 300 s, an interval of 30 s and a count of 2. Those are server settings. For fast failover, the AWS page for Aurora PostgreSQL recommends client keepalives of idle 1, interval 1 and count 5. AWS says these should notify the application within five seconds. Without such client settings, a pooled connection to a host that vanished can wait far longer than the failover. That is inferred and was not run. PgBouncer caches a DNS answer for at most dns_max_ttl, 15 seconds by default.

Where do you meet it, and what does it change?

On RDS or Aurora you meet failover as an event in the console and a gap of errors in your service. What you see is a burst of connection errors for the failover time, then the reconnect storm that the pooling sections explain. With an asynchronous standby you may also see that some acknowledged writes are gone. The decision it changes is the number you plan for. Plan for the documented failover time plus your clients' time to notice, not for ttl alone, and test it with a planned switchover.

  One byte gap is both the stale replica read and the failover loss.

  Believing on waits for a replica when no synchronous standby is named.

  Run SHOW synchronous_standby_names on a server you own, and write its boundary sentence.

The loss at failover is the byte gap, and the gap had a reader that kept falling behind. The next section turns to a reader that stopped, the paused CDC connector from 09:00, and what its slot does to the primary's disk.

Go deeper: detection formulas, the candidate rule, checksums in PostgreSQL 18, and log line sources
Detection in detail

The Patroni docs call ttl the time before the automatic failover process starts. For a PostgreSQL crash under a live Patroni, they give the worst case as loop_wait + primary_start_timeout + loop_wait, so 10 + 300 + 10 = 320 seconds at the defaults. With primary_start_timeout 0 the worst case becomes one loop_wait, and failover.py --detection --primary-start-timeout 0 prints 0 to 10 s. A lower timeout fails over sooner and gives up the chance of a restart on the same host, which loses nothing.

The candidate rule

Run the model with --max-lag 20000000 and only r2, and r2 is promoted with 16,777,216 bytes lost. The Patroni docs warn that a failover can lose transactions when replication is asynchronous. The model compares each replica with the old primary's last LSN, but in a real failure the primary is gone. Check 4 in the lab asks where a manager gets that LSN, and what an old value means for the loss count.

Split brain in numbers

failover.py --split-brain gives the size of the problem with example numbers. At 50 writes per second and 19 seconds before the old primary is fenced, 950 writes exist only on the old side. E14 in the lab makes a split brain on purpose and shows the old side's row gone after pg_rewind.

PostgreSQL 18 and checksums

PostgreSQL 18 turns on data checksums in initdb by default. So on a new 18 cluster pg_rewind works without wal_log_hints.

Switch over on purpose

The docs advise switching over regularly as a test, so the failover path is not first used in an outage. A planned switchover also checks the client side: DNS caches, keepalives and pool reconnects.

Evidence
PostgreSQL 17 docs, section 26.3, for "does not provide the system software" and STONITH. Section 25.3.6 for timelines. Section 9.28.4 for pg_promote defaults. The log lines are from xlogrecovery.c line 4462, xlog.c lines 5907 and 5940, and postmaster.c line 2472 at REL_17_11. The pg_rewind docs for its requirements. initdb.c line 167 at REL_18_6 for 18's checksums. Patroni 4.1.5: config.py line 90 for the timers, global_config.py line 171 for 1048576, ha.py line 1287 for the lag measured against the DCS. AWS failover pages for RDS Multi-AZ instance and cluster, and the Aurora high availability page, for the failover times, the DNS change and the JVM TTL. AWS "Dead connection handling in PostgreSQL" for the server keepalive defaults, and the Aurora PostgreSQL fast failover page for the client values. PgBouncer config page for dns_max_ttl. Fly.io infra log, 2026-06-11. Heroku incident review of the incident of 2025-10-20. Twitch, 2016. The failover.py output is from runs on 2026-10-20.

## Why did a paused CDC connector fill the primary's disk?

The failover lost the WAL that a standby had not received. A reader can also fail the other way, by keeping WAL that the primary would otherwise delete. At 09:00 the search team paused the CDC connector, and at 14:00 the primary's disk was filling. The connector did nothing wrong, because its slot did what slots are for.

Without help, the primary keeps WAL only for its own needs, and after each checkpoint it removes or reuses older segments. A standby or a CDC tool that falls too far behind then finds its WAL gone, and must be rebuilt from a new copy. A replication slot is a small record on the primary that says how far one reader has confirmed. The primary keeps every WAL segment from that point on, so the reader can always continue. A slot protects the reader and puts the primary's disk at risk.

- reader confirmsthe slot's restart_lsn moves forward

- checkpointremoves only WAL older than every slot's restart_lsn

- reader stopsrestart_lsn stays where it was

- pg_wal growsat the full WAL rate, past max_wal_size

What a slot does to WAL removal. The slot never moves by itself, so a stopped reader keeps all WAL written after it stopped.

Predict: max_wal_size is 1 GB. The connector stops at 09:00, the primary writes 10 MiB of WAL each second, and it has 250 GiB free. How much does pg_wal hold at 14:00, and when does the primary stop?
About 176 GiB at 14:00, because 5 hours × 3,600 s × 10 MiB is 180,000 MiB. The primary stops at about 16:07, when 250 × 1,024 / 10 = 25,600 seconds, or 7.1 hours, have passed. The guess "about 1 GB" is reasonable, because max_wal_size reads like a cap. It is a soft target for checkpoints, and a slot overrides it. With the default settings nothing limits what a slot keeps.

Why do slots exist?

Before slots, a standby that fell behind could find its WAL already removed. The WAL sender then reports requested WAL segment %s has already been removed, and the standby must be rebuilt from a new base backup. That is how the GitLab.com outage began. Replication failed because the primary had already removed WAL segments the secondary needed. GitLab.com did not use WAL archiving, so the secondary had to be re-synchronised by hand. During that work an engineer ran the wipe of the data directory on the primary instead. Phase 1 told the rest of that case, the backups that did not restore.

MethodWhat it keepsDefaultWhat goes wrong

wal_keep_sizea fixed amount of past WAL, always0too small, and the standby is cut off. Too large, and it wastes disk every day

WAL archiveevery segment, in another placeoffthe standby fetches from the archive and needs restore_command

replication slotexactly what each reader has not confirmednonea reader that stops keeps WAL without limit

The docs give the reason slots won. The other methods often keep more WAL than needed, and a slot keeps only the segments known to be needed. The same page warns that slots can keep so many segments that they fill the space for pg_wal.

What does a slot hold?

A slot survives restarts. Its fields are in pg_replication_slots.

- restart_lsn is the oldest WAL the reader may still need, and every segment from there on stays.

- xmin is the oldest snapshot the standby still uses, as a transaction ID. It is set on a physical slot whose standby sends feedback, and VACUUM on the primary then keeps rows newer than it, in every table. Phase 4 taught this hold on the cleanup horizon, and the read-replica sections explain the feedback.

- catalog_xmin is the same hold for the system catalogs only, kept by a logical slot.

- active says whether a reader is connected. PostgreSQL 17 adds inactive_since, the time it stopped.

- wal_status and safe_wal_size say how close the slot is to losing its WAL, which the next section explains.

The docs state one more link. A slot keeps rows that could cause a conflict even when its standby is disconnected. So a dead standby with a slot and feedback holds VACUUM back for the whole cluster.

How fast does the disk fill?

A stopped reader's slot keeps WAL at the rate the primary writes it. The time to a full disk is the free space divided by the WAL rate. The lab's slot_retention.py follows the PostgreSQL 17.11 rules for what a checkpoint keeps, with a constant rate and a checkpoint every 5 minutes.

WAL 10.0 MiB/s, free 250.0 GiB, max_slot_wal_keep_size -1 MB, archive failing: False
no-limit time to full: 25,600 s = 7.1 h
     t (s)   wal_status   retained GiB   pg_wal GiB   safe_wal_size MiB
         0   reserved            0.00         1.00   NULL
       106   extended            1.04         1.04   NULL
pg_wal passes 250.0 GiB at t = 25,600 s (7.1 h). PostgreSQL then PANICs when it cannot write WAL.

  Time until a stopped slot fills the disk

  WAL rate, MiB per second
  Free space, GiB
  The disk is full after , or  seconds.

Free space times 1,024, divided by the WAL rate. Constant rate assumed.

The docs say what a full pg_wal does. PostgreSQL does a PANIC shutdown. No committed transaction is lost, but the database stays offline until you free some space. So a CDC pause that nobody watched turns into a write outage hours later, on a primary that looked healthy in the morning.

The phase's arithmetic assumes WAL segments of 16 MB. That is true for community PostgreSQL. Netflix's RDS for PostgreSQL source used 64 MB, the segment size it was initialized with. The fill time does not depend on the segment size, but archive sizes and the numbers in pg_wal do. The RDS default was not checked on an AWS page.

Where do you meet it, and what does it change?

On a managed service you meet slots in two places. The first is a CDC connector such as Debezium on a logical slot. The second is easy to miss. On RDS for PostgreSQL 14.1 and later, every read replica in the same Region has its own physical slot on the source. RDS keeps the PostgreSQL default of no limit. So a stuck replica can fill the source's storage as a stopped connector can. What you see on RDS is OldestReplicationSlotLag rising in bytes, TransactionLogsDiskUsage rising, and FreeStorageSpace falling in a straight line. The decision it changes is what you alert on. Alert on slot lag in bytes, not only on free disk, because the disk alert fires hours after the cause.

The fill time is predictable, and so is the outage at the end of it. The next section shows the setting that trades that outage for a different failure, and two ways a slot grows while its reader looks healthy.

Go deeper: the slot columns, the AWS warning on logical slots, and the slot of a dead standby
The columns, all of them

PostgreSQL 17 adds three more columns: invalidation_reason, failover and synced. The failover-slot section uses the last two. A logical slot holds WAL from its restart_lsn and holds catalog_xmin, so it can also hold back catalog cleanup. The docs warn that slots prevent removal of required resources even when no connection uses them, and that in extreme cases this could shut the database down to prevent transaction ID wraparound. Phase 4 explained wraparound and its limit.

The AWS warning

The AWS page on logical replication says the same about disk. If you set up a logical slot and do not read from it, data can be written and quickly fill the instance's storage.

Feedback without a slot

The docs add the reverse case. Feedback without a slot gives no protection while the standby is not connected, because the primary forgets its xmin. So a slot plus feedback protects the standby's queries across a disconnect, and holds cleanup back for that whole time.

Measure your own WAL rate

On a server, take two readings of pg_current_wal_lsn() 60 seconds apart, and divide their pg_wal_lsn_diff by 60. Put the result into the box above, or into slot_retention.py --rate-mb.

Evidence
PostgreSQL 17 docs, section 26.2.5, for a standby that "will need to be reinitialized", and section 26.2.6 for the slot reason, the caution box and "even when the standby is disconnected". Section 19.6.1 for wal_keep_size. Section 25.3.1 for the PANIC shutdown. Section 47.2.2 for logical slots and wraparound. walsender.c line 3124 at REL_17_11 for the removed-segment error. system_views.sql lines 1006 to 1029 for the slot columns. GitLab, "Postmortem of database outage of January 31, 2017". The study note did not find a published postmortem in which a slot filled a primary's disk, so this outage is predicted from the docs. AWS "Read replica configuration with PostgreSQL" and its mechanisms-per-version page for the physical slot per replica on 14.1 and later. AWS logical replication page for the storage warning. RDS and Aurora CloudWatch metrics pages for the metric names. Netflix, 2026-02-12, archive copy, for the 64 MB segment. slot_retention.py output from the author's run on 2026-10-20.

## What does max_slot_wal_keep_size trade, and which slots grow anyway?

A stopped reader fills the disk in a time you can compute, and with the defaults nothing stops it. max_slot_wal_keep_size limits how much WAL slots may keep. Its default is -1, which means no limit. With a limit, a slot that falls further behind loses its WAL at the next checkpoint, and its reader must start again from a new copy.

The column wal_status in pg_replication_slots shows where a slot stands. PostgreSQL sets it in a function named GetWALAvailability, and the four states come in a fixed order as the slot falls behind.

- t=0 s reserved. The slot's WAL is within max_wal_size.

- t=106 s extended. The WAL is past max_wal_size and kept only because of the slot.

- t=1,026 s unreserved. The WAL is past the cap, and the next checkpoint removes it. A reader that reconnects now can still recover.

- t=1,200 s lost. The checkpoint removed the WAL, and the slot cannot be used again. pg_wal stops near 10 GiB.

An inactive slot at 10 MiB/s of WAL, a cap of 10 GiB and a checkpoint every 300 s. From slot_retention.py --rate-mb 10 --free-gb 250 --max-slot-mb 10240.

safe_wal_size is the number of bytes that can still be written to WAL before the slot is in danger of becoming lost. It is NULL when the cap is -1, so set the cap first and then alert on this column. The arithmetic for the example works in segments of 16 MiB.

cap                  10,240 MiB / 16 MiB         = 640 segments
the slot's segment   1
limit                1 + 640 + 1                 = segment 642, at 10,272 MiB
current position     16 MiB
safe_wal_size        10,272 - 16                 = 10,256 MiB

When the checkpoint removes the slot's WAL, the server log says so. The LSN and the byte count below are an example.

LOG:  invalidating obsolete replication slot "cdc_search"
DETAIL:  The slot's restart_lsn 2/F4000000 exceeds the limit by 1828716544 bytes.
HINT:  You might need to increase "max_slot_wal_keep_size".

A logical reader then gets can no longer get changes from replication slot "cdc_search". Its detail says the slot was invalidated because it exceeded the maximum reserved size. A physical standby gets the already been removed error from the section above.

Which failure does the cap choose?

Without the cap, a stopped reader stops the primary. With it, a stopped reader is cut off and must be rebuilt. A standby needs a new base backup, and a CDC connector needs a new snapshot of every table. For a primary that serves users, the second failure is the smaller one. Pick the cap from your free space, with room for normal WAL, and alert well before it on safe_wal_size.

The cap does not cover two things that also keep WAL.

- A failing archive_command. A segment that has not been archived is never removed, slot or no slot, because the removal code checks that the archive is done first. The model's --archive-failing run shows the slot go lost on time while pg_wal keeps growing.

- The WAL summarizer. With summarize_wal = on, the primary also keeps WAL that the summarizer has not read yet. The backup sections turn that setting on for incremental backups.

Can an active slot still grow?

A connected reader can still hold WAL. Slots work per database, and Debezium confirms a position only when PostgreSQL passes it a change from the captured database. If one database is busy and the captured database is quiet, Debezium has nothing to confirm. WAL is shared by all databases, so it grows until the captured database emits an event. On RDS the same thing can happen on an idle instance, because RDS writes to its own tables every 5 minutes. The fix is a heartbeat, the Debezium settings heartbeat.interval.ms and heartbeat.action.query, which write a small change the connector can confirm. So active = true does not prove that a slot is safe, which is inferred from the Debezium docs.

Netflix met a slot of the other kind while it moved a fleet of almost 400 clusters from RDS for PostgreSQL to Aurora. The metric OldestReplicationSlotLag was unexpectedly high, and the cause was an inactive logical slot on the source, which they removed. Their migration workflow also stops CDC consumers and drops their slots before cutover, so the slots cannot block WAL recycling. On an idle source they saw the same metric drop to 0 for a moment and then return to 64 MB, one WAL segment of that source. The drop came at each forced segment switch, every 300 seconds, from archive_timeout = 300s, which the backup sections explain.

Where do you meet it, and what does it change?

On RDS you meet the cap as a parameter-group setting, and the trade differs by slot type. RDS also archives WAL to S3, and AWS says a replica can catch up by using archived WAL from S3. So a capped physical replica can recover from the archive, while a capped logical slot cannot. That is inferred from the AWS page and was not run. What you see before the outage is a slot lag that never returns to zero, or a slot with active false and an old inactive_since. The decision it changes is threefold. Set the cap below the free space, add a Debezium heartbeat, and drop the slots of readers you retire.

On self-hosted PostgreSQL, read the slots and the archive together.

SELECT slot_name, slot_type, active, inactive_since, wal_status,
       pg_size_pretty(safe_wal_size)                                   AS safe,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained,
       age(xmin) AS xmin_age, age(catalog_xmin) AS catalog_xmin_age
  FROM pg_replication_slots;
SELECT failed_count, last_failed_wal, last_failed_time, last_archived_time FROM pg_stat_archiver;

A capped slot protects the disk, but a CDC connector also needs its slot to exist on whichever server is primary. The next section follows that slot through the failover at 15:10.

Go deeper: the source of the states, PostgreSQL 18's idle timeout, and the metrics
Where the states come from

The states and their meaning are in the docs for pg_replication_slots. The formula for safe_wal_size is in slotfuncs.c. It takes the slot's segment, adds the larger of the cap and wal_keep_size in segments, adds one, and subtracts the current position. Check 2 in the lab asks what happens when the cap is smaller than max_wal_size. The comment above GetWALAvailability says the extended state is then never returned.

The archive check

RemoveOldXlogFiles checks XLogArchiveCheckDone before it removes a file. So a failing archive keeps every segment from the first failure on. Alert on pg_stat_archiver.failed_count and on an old last_archived_time.

PostgreSQL 18

PostgreSQL 18 adds idle_replication_slot_timeout, off by default. It invalidates a slot after it stays idle that long, which is a time limit where the cap is a size limit.

Metrics on RDS and Aurora

RDS has OldestReplicationSlotLag in bytes, ReplicationSlotDiskUsage, TransactionLogsDiskUsage and FreeStorageSpace. Aurora PostgreSQL has the first two as well.

A step the lab does not have

The lab's slot exercises use one busy database. To see the Debezium case, you would capture a quiet database while a second database on the same server takes writes, and watch the slot's retained grow while active stays true. That step is not in the lab.

Evidence
PostgreSQL 17 docs, section 19.6.1, for the -1 default and "may retain an unlimited amount". Section 52.19 for wal_status and safe_wal_size. xlog.c at REL_17_11 for GetWALAvailability, KeepLogSeg, and RemoveOldXlogFiles at lines 3841 and 3886. slotfuncs.c lines 397 to 408 for safe_wal_size. slot.c lines 1540 to 1590 for the log lines, and logical.c lines 625 to 627 for the reader's error. REL_18_6 guc_tables.c line 3109 for the idle timeout. Debezium PostgreSQL connector docs for the per-database confirmation, the RDS idle case and the heartbeat. AWS read replica page for S3 archived WAL. Netflix, "Automating RDS Postgres to Aurora Postgres Migration", 2026-02-12, archive copy. slot_retention.py output from the author's run on 2026-10-20.

## How does a CDC slot survive a failover?

A slot keeps the reader's WAL, but only on the server where the slot lives. Before PostgreSQL 17, a logical slot lived only on the primary. After the failover at 15:10, the CDC connector would find no slot on the new primary. It would have to take a new snapshot of every table, or risk missing changes. That is inferred from the release note, which lists the failover of logical slots as new in 17.

A failover slot is a logical slot that PostgreSQL 17 copies to a standby and keeps up to date there. When the standby is promoted, the connector reconnects to it and continues from the synchronized position. Six settings make it work, and the last one also protects the connector from changes the standby never got.

- 1. the slotcreate the logical slot with failover set, or the subscription with the failover option

- 2. standbysync_replication_slots = on, off by default

- 3. standbyprimary_slot_name, so a physical slot links the two servers

- 4. standbyhot_standby_feedback = on

- 5. standbya dbname in primary_conninfo

- 6. primarythe standby's physical slot listed in synchronized_standby_slots

The setup of a failover slot in PostgreSQL 17, in the order the docs give it.

Step 6 changes what the connector may see. The primary's logical WAL senders send decoded changes only after the listed physical slots confirm that they received the WAL. So the connector never gets a change that the standby lacks. It costs the connector some latency. The docs also warn that logical replication does not proceed if a slot in synchronized_standby_slots is missing or invalidated. So a dead standby in that list also stops CDC.

Before you switch over, check the slot on the standby. Only a persistent slot that reached synced true on the standby before the failover can be used after it. If the standby could not sync a slot, its log shows a line such as could not synchronize replication slot "failover_slot". Its DETAIL names the LSN and the catalog xmin the slot needs. The standby logs this line at LOG level only while its copy of the slot is still temporary. For a persistent slot the line is DEBUG1, so it does not appear with the default log settings. That is verified from slotsync.c lines 220 to 228 at REL_17_11. So read synced and temporary in pg_replication_slots on the standby, and do not wait for a log line.

-- On the standby: is the CDC slot ready to be used after a promotion?
SELECT slot_name, failover, synced, wal_status
  FROM pg_replication_slots
 WHERE slot_type = 'logical';

Where do you meet it, and what does it change?

On managed PostgreSQL the answer depends on the product. On RDS Multi-AZ DB clusters, versions 14.8-R2 and 15.3-R2 and later, a logical slot made on the writer is copied asynchronously to each reader. AWS also warns that with two consumers on different instances, some changes might be lost in a cluster failover. Whether RDS and Aurora support the PostgreSQL 17 settings above was not checked, so read your service's own page before you rely on them. What you see when the slot is missing is a connector that fails after the failover, or a search index that silently misses the changes made during it. The decision it changes is the cutover plan. Check synced before a planned switchover, and plan a new snapshot for the connector if the product cannot keep the slot.

Patroni has an older form of the same idea, called permanent slots. Its docs warn that after a failover some messages could be received a second time. So the consumer must handle duplicates whichever form you use, for example with an idempotent write keyed by the change's LSN. That example is inferred.

  A slot keeps all unconfirmed WAL, so cap it and alert on safe_wal_size.

  Trusting max_wal_size as a cap, while one paused connector fills the disk.

  Run slot_retention.py --rate-mb 10 --free-gb 250 --max-slot-mb 10240 and read the four states.

Slots and failover explain three lines of the bad day. The next section turns to the 11:30 line, a report that failed on the read replica while the primary was healthy.

Go deeper: what the standby settings cost, and the lab
Steps 3 and 4 give the standby a physical slot and turn on its feedback. The slot sections showed what that pair does when the standby dies. Its slot keeps WAL, and its feedback xmin holds VACUUM back for the whole cluster, until the standby returns or the slot is dropped. So a failover slot adds one more slot to watch with the queries above.

The docs' rule on persistent slots means that a slot created moments before a failover may not be ready. So set up failover slots well before a switchover, and confirm synced as a step of the runbook. That advice is inferred from the rule.

E11 in the lab breaks a physical slot on purpose with the cap, and E14 runs a promotion. Neither one sets up a failover slot. The cheatsheet lists the six settings on one screen.

Evidence
PostgreSQL 17 docs, section 47.2.3, for the six settings, the synced rule and the sync failure message. Section 19.6 for sync_replication_slots and synchronized_standby_slots, with "will send decoded changes to plugins only after the specified replication slots confirm receiving WAL". release-17.sgml line 15413 at REL_17_11 for "Enable the failover of logical slots". The log text is from slotsync.c lines 226 to 228. AWS, "Logical replication for Multi-AZ DB clusters", for the asynchronous copy and the warning on two consumers. Patroni docs for permanent slots and duplicates.

## Why was the report on the read replica canceled?

The slot sections were about WAL that a reader had not taken yet. A read replica has the opposite problem, because it must apply WAL while its own queries still run. At 11:30 a report on the read replica failed after running for a while, and the same query on the primary would have finished.

A standby that runs queries is a hot standby, and hot_standby is on by default. Replay must apply every WAL record in order, because the primary already made the change. The primary does not know which queries run on the standby. So some records remove rows or take locks that a standby query still needs, and either the query or replay must give way. Such a clash is a recovery conflict.

- primaryVACUUM removes a dead row version no primary snapshot can see

- WALa cleanup record for that removal reaches the standby

- standbya report started earlier can still see that version

- choicereplay waits for the report, then cancels it

The most common recovery conflict, early cleanup. The primary's VACUUM is correct for the primary and wrong for an older query on the standby.

Predict: max_standby_streaming_delay is 30 s, the time replay waits before it cancels a query. Two long queries meet two cleanup records that arrive 10 s apart. Can the second query be canceled after less than 30 s of waiting?
Yes. The delay is counted from the moment the standby received the WAL, not from the moment replay reaches the record. A second record that arrives while replay still waits for the first one already has its clock running. In the lab's model the second query gets 15 s of grace, not 30. The guess "each query gets 30 s" is reasonable, because the setting looks like a per-query timeout. The docs say it is not the same as the maximum time a query can run before cancellation.

What conflicts with a standby query?

- An ACCESS EXCLUSIVE lock from the primary, from LOCK or from DDL such as DROP TABLE or ALTER TABLE.

- Dropping a tablespace or a database that a standby session uses.

- A vacuum cleanup record that removes rows a standby snapshot can still see.

- A vacuum cleanup record on a page that a standby query is reading at that moment.

The docs name early cleanup as the most common reason. On the primary, VACUUM removes a dead version when no primary snapshot can see it, and a standby query that started earlier may still see it. The docs add a quieter source. VACUUM that marks a page all-visible can also conflict, even on a table with no updated or deleted rows.

How long does the standby wait?

- A conflicting record arrives, and replay waits for the query.

- It waits at most max_standby_streaming_delay, 30 s by default, or max_standby_archive_delay, also 30 s, for WAL read from the archive.

- The delay counts from when the standby received the WAL. So all queries that wait at once share one budget.

- When the budget runs out, the standby cancels the query, and replay continues.

The client gets this error, with SQLSTATE 40001, the code for a serialization failure.

ERROR:  canceling statement due to conflict with recovery
DETAIL:  User query might have needed to see row versions that must be removed.

Other DETAIL lines name the other cases, such as "User was holding a relation lock for too long". Sometimes the conflict is over a lock held by a session that is idle in a transaction. Then the whole session ends with terminating connection due to conflict with recovery. The docs add that a canceled query may be retried at once, and the retry may succeed. So the retry of 40001 that Phase 3 built for SERIALIZABLE also covers this error.

Why is the grace shared?

- t=0 Query X starts on the standby. It needs 35 s.

- t=10 Record 1 arrives and conflicts with X. Its deadline is 10 + 30 = 40.

- t=15 Query Y starts. It needs 45 s.

- t=20 Record 2 arrives while replay still waits on record 1.

- t=35 X finishes. Replay applies record 1 and reaches record 2, which conflicts with Y. The deadline is 20 + 30 = 50, not 35 + 30.

- t=50 Y is canceled after 35 s, with 15 s of grace, not 30. Replay fell up to 30 s behind.

Two cleanup records and max_standby_streaming_delay = 30 s. From hot_standby.py --shared-grace. The model's self-test turns the shared rule off, and Y then finishes.

Waiting has its own cost. While replay waits, every other query on that standby sees older data, so the flush-to-replay gap from the first section grows by up to the delay. On a replica that is also the failover standby, a waiting replay is WAL that a promotion must still apply. That link is inferred.

Where do you meet it, and what does it change?

On RDS you meet this as a report or an export on a read replica that fails after 30 s or more. AWS says that hot_standby_feedback is off by default on RDS. What you see is SQLSTATE 40001 in the application log, and confl_snapshot rising in pg_stat_database_conflicts on the replica. ReplicaLag also steps up by up to 30 s while replay waits. For Aurora readers no AWS page on these settings was found, so that case is not checked. The decision it changes is the role of each replica, which the next section works out with what each choice costs.

The standby has only two ways out of a conflict, wait or cancel. The next section adds the third, feedback, and prices all three.

Go deeper: when the session ends, and the signals in the log
When the whole session ends

The code ends the session in more cases than the docs name. In postgres.c, any conflict while the session waits for its client inside a transaction ends the session. Most conflicts inside a subtransaction also end it. So a client that holds a transaction open on a replica, between two statements, loses its connection, not only its statement.

Signals on the standby

pg_stat_database_conflicts counts cancels per database and per cause, in confl_snapshot, confl_lock, confl_bufferpin, confl_deadlock, confl_tablespace and confl_active_logicalslot. The last one is new in PostgreSQL 16. Set log_recovery_conflict_waits = on, which is off by default. The standby then logs every replay wait longer than deadlock_timeout, 1 s by default. While replay waits on a cleanup conflict, the startup process shows the wait event RecoveryConflictSnapshot, and for a dropped tablespace RecoveryConflictTablespace. No other wait event has that prefix.

Evidence
PostgreSQL 17 docs, section 26.4.2, for the list of conflicts, "early cleanup", the all-visible case, the delay counted from receipt, "Canceled queries may be retried immediately", and the idle-in-transaction case. Section 19.6.3 for "is not the same as the maximum length of time a query can run before cancellation". guc_tables.c at REL_17_11 for hot_standby on, both delays at 30 s, and feedback off. postgres.c lines 2552, 3195 to 3199 and 3218 for the messages and SQLSTATE, and lines 3154 to 3203 for the wider session rule. system_views.sql lines 1087 to 1097 for the conflict columns. wait_event_names.txt lines 148 and 149. AWS Knowledge Center, "rds-postgresql-error-conflict-recovery", for the RDS default. hot_standby.py output from the author's run on 2026-10-20.

## Cancel, delay or bloat: what does each fix cost?

A standby in conflict either waits or cancels, and the wait is one shared budget. You can change which one happens with two settings, and each choice costs something you will see in another place. The lab's model shows the default first, with three queries and a cleanup record every 60 seconds.

max_standby_streaming_delay 30 s, hot_standby_feedback off, cleanup records at [60.0, 120.0, 180.0, 240.0]
query        start   would end   result
report A         0        200   CANCELED at t=90 s after 90 s
api B           95        115   finished
report C       100        200   CANCELED at t=150 s after 50 s
replay fell behind by up to 30 s

The model assumes a table that is updated all the time, so every cleanup record conflicts with every older query. A quiet table conflicts less. There are three ways out.

OptionWhat it costs

1. Keep the delay short, and cap queries with statement_timeout per roleLong queries fail. Replay stays within 30 s, so the replica is still a good failover target.

2. hot_standby_feedback = onNo cleanup conflicts. The primary keeps the dead rows instead, which is bloat, as if the query ran on the primary.

3. A separate report replica, with a long delay and feedback offNo cancels and no bloat on the primary. That replica can fall hours behind, so it must never be a failover target.

How does feedback move the cost to the primary?

With hot_standby_feedback = on, the standby sends the xmin of its oldest snapshot to the primary, at most once per wal_receiver_status_interval. The primary's VACUUM then keeps every row version that snapshot can see. The docs say this can remove the cancels and can cause bloat on the primary. They also give the fair comparison, that the cleanup is no worse than if the standby's queries ran on the primary.

max_standby_streaming_delay 30 s, hot_standby_feedback on, cleanup records at [60.0, 120.0, 180.0, 240.0]
query        start   would end   result
report A         0        200   finished
api B           95        115   finished
report C       100        200   finished
replay fell behind by up to 0 s
primary holds up to 199,000 dead row versions (t=199 s), at 1000 updates/s. Vacuum cannot remove them until the query ends.

The dead rows held are the update rate times the age of the oldest standby query.

model     1,000 updates/s x 199 s          = 199,000 dead versions
6-hour    1,000 updates/s x 21,600 s       = 21,600,000 dead versions

Phase 4 showed what that does. The table grows, and the space comes back only with a rewrite. On the primary, the feedback shows as backend_xmin in pg_stat_replication. If the standby uses a slot, it shows as the slot's xmin instead, and backend_xmin stays NULL. age() of either one is the number to alert on. A slot also keeps that xmin while the standby is down, as the slot sections showed.

Feedback does not stop lock conflicts, because every ACCESS EXCLUSIVE lock on the primary still conflicts. One source of such locks is VACUUM itself, because truncating the empty pages at the end of a table needs an ACCESS EXCLUSIVE lock. So an ordinary VACUUM on the primary can cancel a long read on the standby. That link is inferred from two docs pages and was not run. If it happens, confl_lock grows, and ALTER TABLE ... SET (vacuum_truncate = off) on that table removes the cause.

How did Twitch split the roles?

Twitch used to see many errors that said canceling statement due to conflict with recovery. On its live read replicas it set a strict statement_timeout for every role, such as alter user team_01 set statement_timeout = '1s', and turned hot_standby_feedback on. After that the cancels were not much of an issue. For ad-hoc analytics, each data center has a host outside the live read set. It runs with feedback off and max_standby_streaming_delay = 6h, so the replication source carries no extra load.

- Is this replica a failover target?

- yeskeep the 30 s delay and a statement_timeout per role. Turn feedback on only if the primary can afford the bloat

- no, it serves long reportsfeedback off and a long delay, such as 6 h. Never promote it

One question decides a replica's settings.

Where do you meet it, and what does it change?

On RDS you choose these settings in the replica's parameter group. AWS warns that turning feedback on means long queries on the read replica might cause table bloat on the primary. After the wrong choice you see a week of growing tables on the primary, with no change in its own workload. Or you see a report replica that a failover promoted with hours of WAL still to apply. The decision it changes is the topology. A failover replica and a report replica are two different servers with two different settings.

  On a busy table, a replica cancels, falls behind, or bloats the primary.

  Turning feedback on everywhere to stop cancels, then finding bloat on the primary.

  Run hot_standby.py --shared-grace, then --max-delay 21600, and read the replay lag line.

Replicas protect against a lost host and serve reads, but at 16:40 they replayed the bad migration within a second. The next section asks which copy can bring the table back.

Go deeper: the code path of feedback, and the long-delay replica in the model
The walsender code decides where the feedback goes. With a slot, the xmin is stored in the slot only, and backend_xmin stays NULL. E12 in the lab checks exactly this on its slot-based standby. With --max-delay 21600, the model's queries all finish, and replay falls up to 140 s behind. On a real report replica with a 6-hour delay, replay can fall up to 6 hours behind during a long report, which is why that replica must never be promoted.

The checkpoint question on a 6-hour analytics job works the same arithmetic at 800 updates per second: 800 × 21,600 = 17,280,000 dead versions held on the primary.

Evidence
PostgreSQL 17 docs, section 19.6.3, for feedback that can "eliminate query cancels" and "cause database bloat on the primary", and section 26.4.2 for "no worse than if the standby queries were running directly on the primary server". walsender.c lines 2740 to 2749 at REL_17_11 for the slot xmin. The CREATE TABLE docs, under vacuum_truncate, for the ACCESS EXCLUSIVE lock. Twitch, "How Twitch uses PostgreSQL", 2016-10-11. The post is old and gives no count of cancels, and the mechanism is the same in 17. AWS Knowledge Center for the RDS bloat warning. hot_standby.py output from the author's runs on 2026-10-20.

## Which backup can bring the table back to 16:39?

Replicas copy every change within a second, so they also copied the migration that emptied the table at 16:40. Only a copy taken earlier, plus a record of every change since, can bring the table back to 16:39. This section shows which kind of backup can do that, and the next section runs the restore. Phase 4, on rollback, ended at migration steps that had no reverse and needed a restore from backup. These sections are that restore.

PostgreSQL has three kinds of backup, and only one of them can stop at any moment you name. A base backup is a copy of the data files of a running server. The WAL archive is a second place that keeps every WAL segment after the server is done with it. Point-in-time recovery, PITR for short, restores a base backup and then replays archived WAL up to a target time. So it can stop one second before the bad statement.

KindHow it is madeRestores toRestore work

logical dumppg_dump, SQL or custom formatthe moment the dump startedreplay every row and rebuild every index

file-system snapshota storage snapshot of the data directorythe moment of the snapshotcopy back, then crash recovery

base backup + WAL archivepg_basebackup plus archive_commandany moment after the backup endedcopy back, then replay WAL to the target

Predict: your managed service keeps 7 days of point-in-time recovery. A migration empties a table at 16:40. Name three things that must already be true for you to be back at 16:39 within an hour.
First, a base backup must have ended before 16:39, and every WAL segment from its start to 16:39 must be in the archive. Second, someone must know the restore procedure, including how to write the target, and must have run it before. Third, the measured restore time for this database size must be under an hour, including pointing every client at the restored server. The usual answer names only the first, because "backups are enabled" sounds like the whole requirement. The cases in the next section failed at the second and third.

Why is a dump not point-in-time recovery?

The docs say it plainly. pg_dump and pg_dumpall do not make file-system-level backups, so they cannot be part of continuous archiving, and WAL replay cannot start from them. A dump has a second cost, its restore time. Instapaper had to dump and restore a 2.5 TB MySQL database on RDS. The dump took 24 hours, then 10 hours with parallel work, against an estimate of six to eight hours. The estimate used the number of rows, and it was wrong because the first 25 percent of bookmarks held only 10 percent of the data. After the import, each of three secondary indexes took about 16 hours to build. All 10 days of its backups were file-system snapshots with the same 2 TB file limit as the broken database, so none of them could help. The engine was MySQL, but a logical restore does the same work in PostgreSQL. The GitLab case of 2017 adds a quieter failure. Its daily pg_dump used version 9.2 against a 9.6 server, so it failed, and the S3 bucket was empty.

How do one copy and the WAL reach any moment?

02:00 ─ 02:40   base backup runs. Not a valid target
02:40           backup ends. Its backup history file is in the archive

archive  seg 0A │ 0B │ 0C │ ... │ 7E │ 7F │      every segment, no gap
         ──────────────────────────────────────────►  replay
                                      ▲            ▲
                              16:39:00 target      16:40 bad migration

needed: a backup that ENDED before the target, and every segment
from its start to the target. A missing segment ends the replay there

Recovery restores the file copy and then replays the archived WAL to bring the system to a current state. The replay can stop early, at any moment you name, and that is the point in point-in-time. Two conditions decide whether a target works, and both are about the archive's content.

- The base backup must have ended before the target. A backup that was still running at the target time cannot be used for it.

- Every segment from the backup's start to the target must be in the archive. Replay stops at the first missing segment.

What must the archive command promise?

Set archive_mode = on and an archive_command, or an archive library. The command must return zero if and only if it succeeded. On zero, PostgreSQL assumes the segment is archived and removes or reuses its file. So a command that returns zero after a failed copy loses that segment, and every restore past it. The docs' example, test ! -f /mnt/server/archivedir/%f && cp %p /mnt/server/archivedir/%f, is marked as an example and not a recommendation. cp does not flush the copy to disk, so a crash of the archive host can lose a segment that was reported as archived. That is inferred from what cp does. Real systems use a tool built for the job, such as pgBackRest, WAL-G or Barman, or the managed service.

A command that fails keeps the segment in pg_wal, and the slot sections showed where that leads. Watch pg_stat_archiver, its failed_count, last_failed_wal and last_archived_time. It has one blind spot. If the command is killed by a signal or exits with a status above 125, the archiver process restarts. The failure then does not appear in pg_stat_archiver. So also alert when last_archived_time is older than a few segments' worth of time.

How much can an archive lose?

The archive gets a segment only when it is full, and a quiet server can take a long time to fill 16 MB. archive_timeout forces a switch to a new segment after that many seconds. The docs call a minute or so reasonable. They warn that a very short value bloats the archive, because a segment closed early is still as large as a full one. So the archive can lose up to one segment of time. On a quiet server that is archive_timeout, and on a busy one it is the time to fill 16 MB. Netflix's 0-to-64 MB pattern in the slot sections was this switch, every 300 seconds.

Where do you meet it, and what does it change?

On a managed service you do not run pg_basebackup. You pick a restore time in a console. RDS takes a daily snapshot and uploads transaction logs to S3 every five minutes, so the newest restorable time can be minutes old. It shows that time as LatestRestorableTime. On self-hosted PostgreSQL you see pg_stat_archiver.failed_count and an old last_archived_time. Before the incident you see nothing else, because an untested restore looks healthy on every dashboard. The decision it changes is how you prove the backup works. Only a timed restore does, which the next section runs.

A base backup and an unbroken archive make the restore possible. The next section runs it in order, and shows why the two published cases took hours longer than they needed.

Go deeper: the base backup's files, and the restore work of a dump
What pg_basebackup writes

pg_basebackup copies the data directory from a running server. -X stream is the default. With it, the tool opens a second connection and streams the WAL in parallel, so the backup carries the WAL it needs to be consistent. It writes a backup_manifest with a checksum of every file, and pg_verifybackup checks a backup against it. The archive also gets a backup history file named after the first segment the backup needs, such as 0000000100001234000055CD.007C9330.backup.

Why a dump restore is slow

A dump holds SQL or a compact form of it. Restoring it inserts every row again and rebuilds every index. So the time grows with the data size and the number of indexes. Instapaper's three 16-hour index builds were that work. The docs on SQL dumps give tips for large databases, such as the custom format and parallel restore.

Evidence
PostgreSQL 17 docs, sections 25.1, 25.2 and 25.3, for the three kinds, and section 25.3 for the note that dumps "cannot be used as part of a continuous-archiving solution". Section 25.3.1 for the exit-status rule, the example command and the blind spot of pg_stat_archiver. Section 19.5.3 for archive_timeout. Section 25.3.2 and the pg_basebackup page for -X stream, the manifest and the history file. Instapaper, "Outage Cause & Recovery", 2017-02-14, archive copy. GitLab postmortem of 2017-01-31 for the version mismatch. AWS PITR page for the five-minute upload and LatestRestorableTime. The five-minute sentence was re-read on the page on 2026-10-20 for this review.

## How do you run the restore, and how long does it take?

A base backup that ended before 16:39 and an unbroken archive make the restore possible. Whether it finishes in an hour depends on the steps, the target you write, and a restore time that nobody measures until the day it matters.

What are the restore steps?

- Stop the server. If you can, copy its data directory aside, or at least its pg_wal, because it may hold segments that never reached the archive.

- Restore the base backup into an empty data directory, owned by the database user.

- Remove the files in pg_wal that came from the backup.

- Copy into pg_wal the unarchived segments you saved in step 1, because recovery uses them before the archive.

- Set restore_command, and a recovery target such as recovery_target_time.

- Create the file recovery.signal in the data directory.

- Do not let users connect yet. Change pg_hba.conf, or use another port.

- Start the server. Recovery reads the archive, and a normal recovery ends with a "file not found" message, which is expected.

- Check the data before you promote.

recovery_target_time takes a time stamp, but not with a time zone abbreviation such as EST. Write it with a numeric offset from UTC. The lab's pitr.py refuses the abbreviation for that reason, and the real server would read one only if timezone_abbreviations was set earlier in the file.

  A target with a zone abbreviation.

uv run python phase05_replication/pitr.py --target "2024-01-24 07:00:59 EST" --demo linear

  REFUSED: time zone abbreviation 'EST' is not allowed. Use a numeric offset such as +00

  A numeric offset, before the bad statement.

uv run python phase05_replication/pitr.py --target "2024-01-24 07:00:59+00" --demo linear

Linear, 2024-01-24, UTC: full backup 04:47, bad migration 07:01, maintenance 09:56
  restore the full backup: changes lost from 04:47 to 09:56 = 5:09:00
  point-in-time to just before 07:01: changes lost from 07:01 to 09:56 = 2:55:00, to be replayed by the application
  base backup: daily
  restore_command = 'cp /tmp/storage_lab_p5/archive/%f %p'
  recovery_target_time = '2024-01-24 07:00:59+00'
  recovery_target_action = 'pause'   # the default: inspect, then pg_wal_replay_resume()
  # then: touch $PGDATA/recovery.signal, and start the server

The output shows a default that protects you. recovery_target_action is pause, so the server stops at the target and waits for pg_wal_replay_resume(). The docs give the reason, which is to let you run queries and check that this target is the right one. If hot_standby is off, pause acts like shutdown. Before a risky migration, run SELECT pg_create_restore_point('before_migration_42'). Then the target can be recovery_target_name, and you do not need to know a time at all.

Why did two restores take hours longer than needed?

At Linear, a migration ran TRUNCATE ... CASCADE, and CASCADE emptied every table with a foreign key to the new one. The last full backup was from 04:47 UTC, and the bad commit landed at 07:01 UTC. Linear took daily full backups and also had point-in-time recovery. But the engineering team had never tested point-in-time recovery or built tools for it, so that option was not considered. The full restore won because it was a frequently tested procedure. They restored the 04:47 backup and rebuilt the lost changes from their sync log, and over 99% were back within 36 hours. The lab's arithmetic shows what the untested option would have saved. The team would have rebuilt 2 hours 55 minutes of changes instead of 5 hours 9 minutes.

At Resend, a migration run locally pointed at production and dropped all tables. The first restore took 6 hours and failed, because the wrong backup timestamp was selected. The second, from an older backup, took 5 more hours. The service was down for about 12 hours, and about six and a half minutes of data were lost. One of its follow-ups was to run disaster-recovery tests more often. The report does not name its database engine, and the lesson does not depend on it. A target is a fact you check before a long restore, not after it.

Why does a restore start a new timeline?

A completed point-in-time restore starts a new timeline, as promotion does in the failover section. So the restored server never overwrites the WAL of the history you left. If the first target was wrong, you can restore again to a later moment of the old timeline.

How long does the restore take?

A restore copies the base backup and then replays the WAL since it. The time is the base size divided by the copy rate, plus the WAL size divided by the replay rate. The WAL part grows with the time since the base backup, which is why the interval between base backups matters.

  How long a restore takes

  Base backup, GiB
  Copy rate, MiB/s
  WAL since the base backup, GiB
  Replay rate, MiB/s
  Copy , replay , total , before any check that the data is right.

Base size over copy rate, plus WAL size over replay rate.

The defaults in the box are the lab's example rates, not measured. Copying a 2.5 TiB base at 200 MiB/s and replaying 300 GiB of WAL at 60 MiB/s takes 3.6 h plus 1.4 h, 5.1 h in all. GitHub gave a real number of the same kind for MySQL. Its backups ran every four hours, and restoring multiple terabytes took hours. Most of the time went to the transfer from remote storage, and to decompressing, checking, preparing and loading the files. Measure your own numbers in a drill, then compare them with how long the business can be down.

Where do you meet it, and what does it change?

On RDS a restore creates a new DB instance and does not modify the source. So the restored database has a new endpoint, and every client and pooler must be pointed at it, which adds to the restore time. A read replica cannot be the source of a point-in-time restore. Aurora backups are continuous and incremental, the retention is 1 to 35 days, the default is one day, and automated backups cannot be turned off. So with the default, an error found on day two cannot be undone from the automated backups. What you see when you have not drilled is a team that picks the restore it knows, as Linear did. The decision it changes is the drill. Write down three numbers for each database: the newest restorable time right now, the restore time you last measured, and the date of that drill.

A full base backup of a large database is slow to take and slow to copy back. The next section shows what PostgreSQL 17 adds to shorten it, and the new way it can fail.

Go deeper: the base-backup interval, and a restore inside shared stores
The interval between base backups

The docs name the trade. The interval between base backups sets how much WAL you must keep, and how much the system must replay at a restore. A daily base backup at 3 MiB/s of WAL means up to 26 hours × 3,600 s × 3 MiB, about 274 GiB, to replay. The checkpoint asks you to work that number.

A restore inside shared data stores

Atlassian deleted 883 sites of 775 customers by mistake, because a script got site IDs instead of app IDs and the API accepted both. Its backups allowed point-in-time recovery within 30 days, and the data loss was capped at five minutes before the deletion. The hard part was that the deleted sites shared data stores with live customers, so the team could not restore a whole store to an earlier time. They had to extract and restore pieces by hand, which took about 48 hours per batch of sites at first and about 12 hours per site later. The outage lasted up to 14 days for some customers, and all sites were back by April 18. The post does not name the database engine. PITR restores a whole server to one moment, so a partial restore needs its own tooling and its own drill.

Evidence
PostgreSQL 17 docs, section 25.3.5, for the restore steps, the "file not found" message, and "You cannot use a base backup to recover to a time when that backup was in progress". Section 19.5.6 for the abbreviation rule and recovery_target_action. Section 9.28.3 for pg_create_restore_point. Section 25.3.2 for the base-backup interval. Linear, "Linear incident on Jan 24th, 2024", post of 2024-01-30. Resend, "Incident report for February 21, 2024": down 05:01 to 17:05 UTC, data from 04:50:00 to 04:56:27 lost. GitHub, October 21 post-incident analysis, 2018. AWS PITR, read replica and Aurora backup pages. Atlassian, "Post-Incident Review on the Atlassian April 2022 outage", read in full with curl on 2026-10-20 for this review. The pitr.py outputs are from the author's runs on 2026-10-20.

## What does PostgreSQL 17 incremental backup add, and what breaks it?

The restore time has two parts, and both grow with the size and age of the full base backup. PostgreSQL 17 can back up only the blocks that changed since an earlier backup, so a recent backup is cheaper to take. The cost is a chain of backups, where every link must survive.

An incremental backup holds only the blocks that changed since the backup it names. PostgreSQL learns which blocks changed from WAL summaries, small files that a background process, the WAL summarizer, writes as WAL passes. To restore, a tool combines the full backup and each incremental one, from oldest to newest, into one full copy, and recovery then runs as before.

- Sun fullall blocks

- Mon incrementalblocks changed since Sun

- Tue incrementalblocks changed since Mon

- pg_combinebackupone full copy, then recovery

An incremental chain. pg_combinebackup needs every link, so a retention job that deletes Monday makes Tuesday impossible to restore.

- Set summarize_wal = on, which is off by default. The summarizer writes summaries to pg_wal/summaries and keeps them for wal_summary_keep_time, 10 days by default.

- Take a full backup as usual.

- Later, run pg_basebackup --incremental=<full>/backup_manifest. Without the summaries, an incremental backup fails.

- To restore, run pg_combinebackup -o <target> <full> <inc1> <inc2>, from oldest to newest. Then recover as in the section above.

The lab's model shows the broken chain.

cannot restore inc-tue: inc-tue needs inc-mon, which is not kept

PostgreSQL does not track the chain for you, so you must record which incremental backup depends on which. pg_combinebackup checks only that the backups fit together, not that each one is intact, and pg_verifybackup does that second check. The docs say incremental backups make sense for large databases where much of the data does not change. For a small database, take full backups.

The summarizer also keeps WAL, as the slot sections noted. With summarize_wal = on, the primary keeps WAL that the summarizer has not read yet. So a stalled summarizer is one more thing that can grow pg_wal.

The feature is young, and two of its bugs were fixed in minor releases. Release 17.8 fixed incremental backups of a table over 1 GB that VACUUM had truncated, which pg_combinebackup could not restore. Release 17.11 fixed visibility-map changes that the WAL summarizer missed, which could lead to incorrect incremental backups. So run the newest 17 minor release if you use it, and restore-test the chain, not only the full backup.

Where do you meet it, and what does it change?

On Aurora you do not see a chain, because AWS describes its backups as continuous and incremental and manages them for you. On RDS you see daily snapshots and a log upload every five minutes. You meet pg_basebackup --incremental on self-hosted PostgreSQL, or inside a backup tool that uses it. What you see when a link is missing is a restore that fails at pg_combinebackup, often on the day you need it. The decision it changes is retention. A retention rule must delete whole chains, never a middle link, and a drill must restore from the newest incremental backup.

  A backup is proven only by a restore you have timed.

  Calling a replica, a nightly pg_dump or untested PITR a backup plan.

  Run pitr.py --demo gap and --demo chain, and read where each restore stops.

Backups answer the 16:40 line. The last line of the bad day is 15:12, when every pool reconnected to the new primary at once. The next section explains why the healthy database refused them.

Go deeper: the gap demo, and the order of the chain
pitr.py --demo gap shows a missing archive segment. In the demo, replay stops at 03:59:59 UTC, before the gap, and every target after that point is out of reach. E8 in the lab runs both demos and a third failure, a target after the bad migration, which restores the empty tables.

The order of arguments to pg_combinebackup is the order of the chain, from the full backup to the newest incremental one. E15 in the lab takes a full and an incremental backup, combines them, and times a restore to a moment before a bad DELETE.

Evidence
PostgreSQL 17 docs, section 25.3.3, for the incremental steps, "an attempt to take an incremental backup will fail", "You must keep track of the relationships", and when incremental backups make sense. The pg_combinebackup page for the argument order and "not that each individual backup is intact". guc_tables.c at REL_17_11 for summarize_wal off and wal_summary_keep_time 10 days. xlog.c KeepLogSeg, line 8028, for the summarizer's WAL. release-17.sgml lines 5246 to 5257, inside 17.8, and lines 1954 to 1966, inside 17.11 of 2026-08-13. AWS Aurora backups page for "continuous and incremental". pitr.py output from the author's runs on 2026-10-20.

## Why did the new primary refuse connections after the failover?

Backups and replicas protect the data. The last line of the bad day was about connections. At 15:12, two minutes after the failover, every pool reconnected at once, and the new primary refused new connections while it was healthy. The pools that can reach it added up to more than its connection slots.

PostgreSQL runs one operating-system process per client connection. The postmaster, its first process, starts a new backend process every time a connection is requested, and each client talks to exactly one backend. So a connection is a whole process with its own memory, and max_connections, 100 by default, caps them. The server also sizes some shared memory from max_connections, so raising it has a cost of its own. A connection pooler keeps a small set of server connections open and lends them to many clients.

- 40 app processesapi, jobs and agents

- ORM pools10 client connections each, 400 in all

- PgBouncer400 client connections in, pool_size 40 out

- PostgreSQL40 backends of 97 normal slots

The connection path of the running case, as planned. Without the pooler, 400 backends are wanted against 97 normal slots, and 303 are refused.

Predict: three PgBouncer processes each serve 4 database and user pairs, at the default pool size of 20. max_connections is 200, with the default reserved settings. After a failover, every pool refills at once. Can an on-call engineer who is not a superuser log in?
No. The pools can open 3 × 4 × 20 = 240 server connections, against 200 − 3 = 197 slots for normal roles. They fill every normal slot, and the 3 superuser slots stay free only for superusers. reserved_connections is 0 by default, so no slot is kept for anyone else. The guess "PgBouncer protects the database" is reasonable, because a pooler exists to limit connections. PgBouncer limits each pool, not the sum, unless you set max_db_connections.

How many slots does each role get?

Phase 4 did the basic arithmetic, where 100 slots minus 3 for superusers leave 97. PostgreSQL 16 added a second layer of reserved slots, and it decides who can log in during a storm.

- superuser_reserved_connections, 3 by default, keeps the last slots for superusers.

- reserved_connections, new in PostgreSQL 16 and 0 by default, keeps slots for roles with the privileges of pg_use_reserved_connections.

- WAL senders do not use these slots, because the server adds max_wal_senders on top.

- A normal role gets an error as soon as only reserved slots are left, and the error text says which layer it hit.

  max_connections = 100 with reserved_connections = 5. Example

The slot layers with five reserved slots. Example.

the error a normal role gets depends on how many slots are free:
  ≤ 8 free  "remaining connection slots are reserved for roles with
             privileges of the "pg_use_reserved_connections" role"
  ≤ 3 free  "... reserved for roles with the SUPERUSER attribute"
  0 free    "sorry, too many clients already"

All three errors carry SQLSTATE 53300, too_many_connections. Give pg_use_reserved_connections to the role your operators use, and never to the application's or the pooler's role. Then a connection storm cannot lock the operators out. That rule is inferred from the docs' description and from the incidents in this section. Phase 4's Railway case showed the other side, where engineers trying to stop an index build got the first error because their role lacked the privilege.

What did Buttondown see?

Buttondown had two outages of about 7 and 13 minutes from one cause. It hit the ceiling on the number of connections its database was configured to accept. The database itself was healthy, with fast queries, normal CPU and memory, and normal replication lag. The health check mostly passed, because its requests happened to land on workers that already held open connections. In the second outage the team could not even connect to the database to kill queries, so they restarted it. The first of their five fixes was reserved administrative connections. The second was an alert on connection count as a percentage of the configured maximum.

How do you budget before the incident?

Add up every pool that can open a server connection, and compare the total with the normal slots. The lab's pool_model.py --budget does it.

  Every process opens its own pool against the database.

40 app instances x pool 10, direct = 400 server connections
slots for normal roles: 100 - 3 superuser - 0 reserved - 0 planned = 97
OVER by 303: new connections fail with SQLSTATE 53300 when the pool fills

  The pools talk to PgBouncer, and PgBouncer's pools fit the slots.

2 PgBouncer x 1 pool(s) x (40 + 0 reserve) = 80 server connections
slots for normal roles: 100 - 3 superuser - 0 reserved - 0 planned = 97
within budget, spare 17

  Server connections against the normal slots

  PgBouncer processes
  Database and user pairs per process
  Pool size per pair
  max_connections
  reserved_connections
  Pools can open  connections against  normal slots: .

Processes times pairs times pool size, against max_connections minus 3 superuser slots and the reserved slots.

Three things make the real total larger than the plan.

- A deploy that runs old and new processes side by side doubles the client side for a while.

- Every distinct database and user pair is its own PgBouncer pool, with up to default_pool_size connections, 20 by default.

- max_db_connections is 0 by default, which means unlimited, so nothing in PgBouncer caps the sum unless you set it. Each PgBouncer process counts on its own, so three processes may open three times that limit, which is inferred from the configuration page.

Where do you meet it, and what does it change?

You meet the budget when you add a service, raise an ORM pool size, or survive a failover. After a failover every pool reconnects at once, and a deploy at the same time makes it worse. What you see is a database that looks healthy while the application gets SQLSTATE 53300 or pool timeouts, and PgBouncer's SHOW POOLS shows cl_waiting and maxwait rising. On RDS the metric is DatabaseConnections. The decision it changes is to write the budget down. Set max_db_connections in each PgBouncer, keep the sum below the normal slots with a margin, and grant the reserved role to operators only.

The budget says how many connections the pools may open. The next section asks how many the work needs, and why one habit of agent code multiplies that number.

Go deeper: the error sources, and what the RDS metric leaves out
The three messages come from postinit.c and proc.c. The thresholds follow the docs' rule for reserved_connections, counted before the connection attempt. With max_connections = 100, reserved_connections = 5 and 3 superuser slots, a normal role is refused when 8 or fewer slots are free, and a reserved role when 3 or fewer are free.

The RDS metrics page notes that the number of database sessions can be higher than DatabaseConnections, because the metric leaves some sessions out. So alert below the limit, not at it. On a self-hosted server, count the client backends by state and compare them with the normal slots.

SELECT state, count(*) FROM pg_stat_activity
 WHERE backend_type = 'client backend' GROUP BY 1;

A large idle in transaction count in that result is a client that holds transactions open, which the next section prices.

Evidence
PostgreSQL 17 docs, section 50.2, for the process-per-user model. Section 19.3.1 for max_connections, its shared-memory note, both reserved settings and their rule. guc_tables.c at REL_17_11, lines 2215, 2226 and 2236, for the defaults. The PostgreSQL 16 release notes for reserved_connections. postinit.c lines 582 and 583 for WAL senders on top, and lines 962 and 968 for the messages, with proc.c line 357. Buttondown, "Public postmortem: database connection exhaustion", incident of 2026-03-31, post of 2026-04-01. The post gives no connection numbers and no engine version. PgBouncer configuration page for default_pool_size and max_db_connections. RDS metrics page for DatabaseConnections. pool_model.py output from the author's runs on 2026-10-20. Railway's report is told in Phase 4.

## How many server connections does the work need?

The budget caps what the pools may open. The other half is how many connections the work keeps busy, and the agent code in the running case has a habit that multiplies that number.

Little's law gives the number. The elite-performance course used it for client pools, and it holds for server connections as well. Busy connections equal the transactions per second times the seconds each transaction holds its connection. A transaction pooler can lend a server connection to another client only between transactions, so the hold time is the whole transaction, including any wait inside it.

2,000 transactions/s x 0.005 s held     = 10 busy server connections
2,000 transactions/s x 0.205 s held     = 410 busy server connections

Both lines are pool_model.py --busy. The second one holds the transaction open across a 200 ms call to a model API or another service. So an agent step that opens a transaction, calls an LLM and then commits needs 41 times the connections. 410 is above the 97 normal slots of a default server. Commit before the call, and start a new transaction for the result. Phase 3 gave the same rule for row locks held across a slow call.

  Busy server connections

  Transactions per second
  Time each transaction holds its connection, ms
  Busy connections: .

Little's law: busy connections equal the rate times the hold time.

Why does a pooler save time?

A new PostgreSQL connection starts a process, so it costs time before the first query. OpenAI runs one Azure PostgreSQL primary behind PgBouncer in statement or transaction pooling mode. In their tests this cut the average connection time from 50 ms to 5 ms. Azure limits an instance to 5,000 connections, and they had incidents from connection storms before. A pooler in front of the database keeps the number of server processes fixed while client connections come and go.

When is the pooler the limit?

PgBouncer is one process with one thread. At Twitch, CPU hit 100% on a PgBouncer process, which made connections stall, so they ran two processes per host behind HAProxy, a TCP load balancer. The PgBouncer configuration page now names a simpler way. With so_reuseport, several PgBouncer processes listen on the same port.

At Notion, the pooler's arithmetic appeared in a test before a re-shard. About 100 PgBouncer instances, each with up to 6 connections per shard, made 600 connections per shard. Pointing three new shard entries at each old shard would make 18 per instance, 1,800 per old shard.

today      100 PgBouncer x 6 per shard            = 600 per shard
re-shard   100 PgBouncer x (3 x 6) per old shard  = 1,800 per old shard

That is pool_model.py --notion. They split PgBouncer into clusters instead, four groups with 24 databases behind each PgBouncer shard, so each instance pointed at fewer databases.

Where do you meet it, and what does it change?

You meet this in agent code that calls a model, a tool or another service inside a database transaction. Often an ORM opened the transaction for the whole request. What you see is idle in transaction sessions in pg_stat_activity, and clients waiting in PgBouncer while the database's CPU is low. PgBouncer's query_wait_timeout, 120 seconds by default, disconnects a client that waits longer, so the default lets a request wait two minutes in the pooler. The decision it changes is where the transaction ends. Close it before any external call, and set query_wait_timeout below your request deadline.

A transaction pooler fixes the count, but it changes what a session is. The next section shows what breaks when consecutive transactions of one client run on different server connections.

Go deeper: reading SHOW POOLS, and the checkpoint arithmetic
In PgBouncer's SHOW POOLS, cl_waiting counts clients that have sent queries but have not yet got a server connection. maxwait is how long the oldest one has waited. The docs say that if it starts increasing, the current pool of servers does not handle requests quickly enough. Compare sv_active, the server connections in use, with the busy number from Little's law. A big gap suggests that transactions hold connections longer than their queries need. That reading is inferred.

The checkpoint has one more case. An agent service runs 50 steps per second, and each holds a transaction open for 1.2 s across an LLM call, so 50 × 1.2 = 60 connections are busy. If the transaction closes before the call and lasts 8 ms, 50 × 0.008 = 0.4, so one connection serves them all.

Evidence
pool_model.py --busy and --notion output from the author's runs on 2026-10-20. OpenAI, "Scaling PostgreSQL to power 800 million ChatGPT users", 2026-01-22, archive copy, for the 50 ms to 5 ms change in their benchmarks and the 5,000 limit. Twitch, 2016, for the 100% CPU and HAProxy. PgBouncer configuration page for so_reuseport and query_wait_timeout, and the usage page for SHOW POOLS. Notion, "The Great Re-shard", 2023-07-17, for the 600 and 1,800 connections and the four groups. Little's law in the elite-performance course, Phase 5B.

## What does transaction pooling break, and what does RDS Proxy do instead?

Transaction pooling is what lets 400 client connections share 40 server connections. The price is that two transactions from the same client may run on two different server connections. So anything that lives in the session, not in the transaction, goes wrong.

PgBouncer has three modes. In session pooling, the default, a client keeps one server connection for as long as it stays connected. So every PostgreSQL feature works, and only the connect cost is saved. In transaction pooling, a server connection is assigned to a client only during a transaction. Statement pooling is transaction pooling where transactions of more than one statement are not allowed. Only the last two let many clients share few server connections.

  One server connection, two clients, transaction mode

  Step 1: client 1 sets a timeout. The setting stays on the server connection, not on client 1.

  Step 2: PgBouncer lends the same server connection to client 2. No reset query runs in transaction mode.

  Step 3: client 2 inherits the 1 ms timeout, and its query is canceled with no error at the place of the cause.

  The shape of E16 in the lab, with a pool of one server connection. Illustration, not measured.

A session setting that leaks through transaction pooling.

What does transaction mode break?

PgBouncer's feature table marks these as never working in transaction pooling.

- SET and RESET of a setting PgBouncer does not track, because the value stays on the server connection.

- LISTEN, because the notification arrives on a server connection the client no longer holds.

- WITH HOLD cursors, SQL PREPARE and DEALLOCATE, and LOAD.

- Temporary tables with PRESERVE or DELETE ROWS, which outlive the transaction.

- Session-level advisory locks, which Phase 3 showed outlive the transaction. pg_advisory_xact_lock is the form that works.

The worst failure is silent. A SET statement_timeout sent by one client stays on that server connection, and the next client that gets it inherits the timeout. PgBouncer does not run server_reset_query in transaction mode, because its docs say clients there must not use session-based features at all. The setting server_reset_query_always exists for broken setups, and the docs say it turns non-deterministic breakage into deterministic breakage. Put per-request settings in SET LOCAL inside the transaction, or on the role with ALTER ROLE ... SET. A worker that waits with LISTEN needs its own direct connection, or a session-mode pool.

The phase said a note to PgBouncer's feature table names six startup parameters that PgBouncer tracks itself, so a SET of those six is safe. True now: since PgBouncer 1.26.0, PgBouncer tracks all parameters that PostgreSQL reports by default. On PostgreSQL 17 that list is application_name, client_encoding, DateStyle, default_transaction_read_only, IntervalStyle, scram_iterations, session_authorization, standard_conforming_strings and TimeZone. search_path joins it only on PostgreSQL 18. So on PostgreSQL 17, SET search_path and SET statement_timeout still leak to the next client. The feature page's note still shows the old six, so the PgBouncer site disagrees with itself.

The lab's pool_model.py --lint checks statements against the feature table and against the RDS Proxy list below. These are the first five of its eleven lines.

BREAKS pgbouncer-txn PINS rds-proxy  SET statement_timeout = '5s'                                SET or RESET
ok pgbouncer-txn     ?? rds-proxy    SET LOCAL statement_timeout = '5s'                          SET LOCAL: inferred safe in PgBouncer: it ends with the transaction. RDS Proxy: not checked
BREAKS pgbouncer-txn PINS rds-proxy  SELECT pg_advisory_lock(42)                                 session advisory lock
ok pgbouncer-txn     ok rds-proxy    SELECT pg_advisory_xact_lock(42)                            transaction advisory lock: RDS Proxy does not pin on these. Phase 3, section 3.6, uses this form
BREAKS pgbouncer-txn PINS rds-proxy  LISTEN task_ready                                           LISTEN

The lint still uses the old list of six tracked parameters. With PgBouncer 1.26 on PostgreSQL 17, SET default_transaction_read_only and SET session_authorization are also tracked, so the lint can flag those two where PgBouncer handles them. The lint code was not changed or run again for this lesson.

Do prepared statements work behind the pooler?

Drivers prepare statements at the protocol level, without SQL PREPARE. Before PgBouncer 1.21.0, that failed in transaction mode. Version 1.21.0 added support for protocol-level named prepared statements, and version 1.24.0 set max_prepared_statements to 200 by default. Three details matter.

- It does not cover SQL-level PREPARE, because PgBouncer forwards PREPARE, EXECUTE and DEALLOCATE straight to PostgreSQL.

- PgBouncer prepares each distinct query once per server connection, not once per client. With a pool size of 20 and 100 clients that prepare the same query, it is parsed only 20 times.

- After a migration that changes a column, you may see ERROR: cached plan must not change result type. Run RECONNECT on the PgBouncer admin console to force a re-prepare.

Detail 2 is the PgBouncer side of a rule from Phase 4, on generic plans. There, the first five executions of a prepared statement got custom plans, and then a generic plan could take over. That count lives in the server's plan cache, per backend. So behind PgBouncer, each server connection counts its own five executions, whichever clients sent them. This is inferred from the plan cache being per backend and from detail 2. It was not run.

How does RDS Proxy pin a session?

RDS Proxy also reuses a database connection at the end of each transaction. When it sees session state, it pins the session, which means each later transaction of that client uses the same database connection until the session ends. For PostgreSQL the AWS page lists these causes.

- SET, and PREPARE, DISCARD, DEALLOCATE and EXECUTE.

- Temporary sequences, tables and views, and cursors.

- LISTEN, and loading a module such as auto_explain.

- nextval and setval, pg_advisory_lock and pg_try_advisory_lock.

- Any statement whose text is larger than 16 KB, for every engine.

It does not pin on pg_advisory_xact_lock and its variants. A pool library that sends DISCARD ALL when it releases a connection pins every connection. The difference from PgBouncer matters. PgBouncer in transaction mode breaks session state in a way you may not notice, while RDS Proxy keeps it correct and stops multiplexing that client. A pinned session costs a whole database connection, as a direct connection does.

Where do you meet it, and what does it change?

You meet this through your driver and ORM. An async Python service behind PgBouncer may get prepared statement "__asyncpg_stmt_xx__" does not exist or already exists. The asyncpg FAQ says that error means you are most likely connecting through PgBouncer, and it suggests statement_cache_size=0 or session mode. The FAQ does not mention PgBouncer 1.21 and later with max_prepared_statements, so its advice is older than PgBouncer's fix, which is inferred. On RDS Proxy you see DatabaseConnectionsCurrentlySessionPinned rise, and DatabaseConnectionsBorrowLatency with it. An ORM that sends long generated SQL can pin through the 16 KB rule, which is inferred. The decision it changes is how session state is set. Use SET LOCAL or role settings, transaction advisory locks, and a direct connection for LISTEN.

  Keep every pool's sum below the normal slots, and session state out of the pooler.

  Trusting PgBouncer to cap max_connections when max_db_connections is unset.

  Run pool_model.py --lint phase05_replication/sample_session.sql, then grep your code for SET.

Every line of the bad day now has its mechanism and its number. The recall section below puts the five claims together.

Go deeper: Twitch's fork, what the AWS page does not say, and the grep
Before protocol-level support

Twitch wrote a fork of PgBouncer that held the back-end until the parameters were provided for execution. Its case was an unnamed statement from Go's lib/pq driver. Whether PgBouncer 1.21.0 and later also cover that unnamed case was not checked.

What the AWS page does not say

The AWS pinning page does not say whether a protocol-level prepared statement pins, and it documents SET LOCAL only for MySQL. Both are not checked for PostgreSQL. Test them on your own proxy before you depend on them.

Find session state in your code

A grep such as grep -rn "SET \|LISTEN\|advisory_lock\|PREPARE\|WITH HOLD" <your repo>/ finds most of it. Mark each hit as safe or not for your pooler, using the lists above.

Evidence
PgBouncer features page for the three modes and the table of what transaction pooling never supports. PgBouncer configuration page for server_reset_query, server_reset_query_always, max_prepared_statements, RECONNECT and track_extra_parameters with the 1.26 list of tracked parameters. PgBouncer changelog for 1.21.0 of 2023-10-16, 1.24.0 of 2025-01-10, and 1.26.0 of 2026-09-23. AWS "Avoiding pinning an RDS Proxy" for the PostgreSQL list, the 16 KB rule, transaction advisory locks and DISCARD ALL, and the RDS Proxy monitoring page for the metrics. asyncpg FAQ for the prepared-statement errors. Twitch, 2016. pool_model.py --lint output from the author's run on 2026-10-20.

## What you can do now, and what comes next

The bad day now has an answer for each of its lines.

- 10:05 and 15:10, the gap. A replica read and a failover see the same byte gap, and with no synchronous standby named, OK leaves it open. You can read a standby's four positions, fix read-after-write three ways, state what each synchronous_commit level waits for, and walk through the five steps of a failover. From the four sections on positions, lag in seconds, the meaning of OK, and the 90 seconds of a failover.

- 09:00 and 14:00, the slot. A replication slot keeps every WAL byte its reader has not confirmed, so a stopped reader fills the primary's disk. You can compute the time to a full disk, set max_slot_wal_keep_size and alert on safe_wal_size. You can spot an active slot that still grows, and keep a CDC slot through a failover. From the three slot sections.

- 11:30, the report. On a busy table, a read replica must cancel a long query, delay replay, or bloat the primary. You can explain the shared grace, and give a failover replica and a report replica their own settings. From the two read-replica sections.

- 16:40, the restore. Point-in-time recovery needs a base backup, an unbroken WAL archive and a restore you have already timed. You can choose the backup and the target, write the target with a numeric offset, estimate the restore time, and keep an incremental chain whole. From the three backup sections.

- 15:12, the connections. Every server connection is a process from a fixed budget, and transaction pooling hands session state to the next client. You can budget the pools against the normal slots, keep a reserved slot for operators, size connections with Little's law, and keep session state out of the pooler. From the three pooling sections.

You can now write one sentence for each server you run. It says what an OK survives and what a stopped reader does to its disk. It says which replica serves which reads, how far back and how fast you can restore, and how many connections can reach it. This is the last phase of the course. Course 5 of the curriculum exists only as a plan, and it keeps the general theory of replication. This phase applied that theory to one PostgreSQL 17 system.

## Lab: build a standby, break it, and restore

The phase's sixteen exercises, under their own ids and copied from the phase. E1 to E9 run offline and were run on the author's machine, so their Expected lines are real output. E10 to E16 need PostgreSQL 17 on your laptop and were not run by the author yet, and their Expected lines say so. No code was run for this lesson.

Where an exercise says "section 5.N", it means a section of the phase. In this lesson, 5.1 is the two sections on a standby's positions and on lag in seconds, and 5.4 is the section on what OK means. 5.5 is the failover section and the failover-slot section. 5.2 is the slot sections, 5.3 the read-replica sections, 5.6 the backup sections and 5.7 the pooling sections.

The lab builds a throwaway primary on port 5433 and a standby on port 5434, with a WAL archive, all under /tmp/storage_lab_p5. two_node.py holds every command, and its database is storage_lab_p5, so the labs of earlier phases keep working. Everything runs on your laptop and costs nothing. The model scripts and every --self-test need no server. The live exercises need the PostgreSQL 17 binaries on your PATH and about 200 MB under /tmp. Run all commands from elite-storage/code/, which on this Mac is /Users/raghvendra.dhakar/Desktop/project/code/study-material/elite-storage/code.

IdeaExercises

The byte gap: positions, lag, OK and failoverE2, E3, E6, E7, E10, E13, E14

Slots and the full diskE4, E11

Read replicas: cancel, delay or bloatE5, E12

Backups and the timed restoreE8, E15

Connections and the poolerE9, E16

Every rule, as a self-testE1

Open the lab: setup notes and E1 to E16
Run status. Every offline command below, E1 to E9, was executed on 2026-10-20 on the author's machine, with Python 3.12.14 from the course's .venv. Their "Expected" lines are the real output. The live exercises, E10 to E16, were written and reviewed but not run, by the owner's choice for this course. Each of their "Expected" lines says "Not run by the author yet." and gives the expected shape from the PostgreSQL 17 docs and source. No database server was started for this phase.

What you build. Eight files and one SQL sample in phase05_replication/. They use only the Python standard library, so pyproject.toml needs no new pin. failover.py imports lag.py, and two_node.py imports pitr.py. No earlier file changes.

FileWhat it holdsSelf-test checks

lag.pyLSN parsing, WAL file names, the four stage gaps, time lag with and without the idle checkthe docs' LSN and WAL-file examples, the stage gaps, the idle false alarm with the rule removed

slot_retention.pywhat a checkpoint keeps for a slot, wal_status, safe_wal_size, a failing archivethe time to full, the extended, unreserved and lost times, the cap removed

hot_standby.pyreplay that waits, cancels, and feedback that holds dead rowsthe cancel times, the shared grace with the rule removed, the dead rows held

commit_levels.pythe docs' table of five levels, latency, loss per failure, FIRST and ANYthe docs' bullets, the waits, blocking with the alive rule removed

failover.pythe candidate rule, detection windows, timelines, split-brain writesPatroni's defaults, the lag rule removed, the history file name

pitr.pythe backup that ended before the target, archive gaps, the incremental chain, target textLinear's times, the end rule removed, abbreviations, a missing link

pool_model.pythe slot budget, Little's law, the transaction-mode and pinning lint97 slots, Notion's 600 and 1,800, each lint rule

two_node.pyevery command of the live exercises, with a safe-path guardthe setup and restore commands, the refused paths

For each rule the text calls important, the self-test has a check that fails when the rule is removed. A mutation run on 2026-10-20 removed 16 such rules one at a time. Each removal failed its self-test. The first run missed one: pitr.py still refused "EST" without the abbreviation rule, because the date parser failed on it anyway. The check now requires the word "abbreviation" in the error. The review removed 17 more rules, 33 in all, and every removal failed. Its first run missed one in the same way: pitr.py raised KeyError for a missing chain link even without the rule. That check now reads the message too.

The demonstration of this phase is E10, E13 and E15. E10 shows a standby's positions. E13 shows a synchronous commit that blocks and a canceled wait that leaves a visible commit. E15 is a timed point-in-time restore to a moment before a bad statement.

-  E1 offline Run every self-test of this phase, then those of the earlier phases.

- Run: for f in phase05_replication/*.py; do echo "$f"; uv run python "$f" --self-test; done
- Then run: for f in shared/*.py phase0[1-4]_*/*.py; do echo "$f"; uv run python "$f" --self-test; done
- Expected: self-test passed after each of the 8 Phase 5 files, with check counts from 9 to 20. The earlier phases' scripts all passed on 2026-10-20 too. shared/__init__.py is empty and prints nothing.
- If it fails: the assertion message names the rule. Compare it with the section before you change any code.
- Teaches: each rule in the text has a check that fails without it.

-  E2 offline Find the slow stage of a standby.

- First predict which gap is largest for these positions: current 5/3A000000, sent 5/39F00000, write and flush 5/39E00000, replay 5/38000000.
- Run: uv run python phase05_replication/lag.py --current 5/3A000000 --sent 5/39F00000 --write 5/39E00000 --flush 5/39E00000 --replay 5/38000000 --wal-rate-mb 8
- Expected: four rows. flush -> replay is 31,457,280 bytes, about 3.75 s at 8 MiB/s, and is named the largest gap. The total is 33,554,432 bytes.
- Then run: uv run python phase05_replication/lag.py --walfile 0/D3DA3C8. Expected: file 00000001000000000000000D  offset 4039624, the docs' own example of section 9.28.3.
- Teaches: section 5.1, a byte gap names a stage.

-  E3 break-it, offline The idle-primary false alarm.

- Run: uv run python phase05_replication/lag.py --idle-demo --no-idle-check, then without the flag.
- Expected: with the flag, the reported lag is 1.0, 10.0, 60.0 and 290.0 s while the byte lag is 0. Without it, every row is 0.0.
- Teaches: section 5.1, check received against replayed before you trust the clock.

-  E4 offline How long until a stopped CDC slot fills the disk.

- Run: uv run python phase05_replication/slot_retention.py --rate-mb 10 --free-gb 250, then add --max-slot-mb 10240, then add --archive-failing as well.
- Expected: without the cap, pg_wal passes 250.0 GiB at t = 25,600 s (7.1 h). With the cap, the states are reserved at 0 s, extended at 106 s, unreserved at 1,026 s and lost at 1,200 s. pg_wal stays below 250 GiB. With a failing archive, the slot is still lost at 1,200 s, but the disk is full at 25,600 s again.
- Then put in your own WAL rate and free space.
- Teaches: section 5.2, the cap trades a full disk for a reader to rebuild, and does not cover the archive.

-  E5 offline Cancel, wait or hold back VACUUM.

- Run: uv run python phase05_replication/hot_standby.py, then --feedback, then --shared-grace, then --max-delay 21600.
- Expected: default, report A canceled at t=90 s and report C at t=150 s, and replay up to 30 s behind. --feedback: all three finish, and the primary holds up to 199,000 dead row versions. --shared-grace: Y canceled at t=50 s after 35 s. --max-delay 21600: all finish, and replay falls up to 140 s behind.
- Teaches: section 5.3, the three options and what each costs.

-  E6 offline What OK means at each level.

- Run: uv run python phase05_replication/commit_levels.py, then --rtt-ms 70, then --no-sync-standby.
- Expected: waits of 0.00, 1.00, 2.05, 3.00 and 3.50 ms by default. At 70 ms, remote_write waits 71.05 ms and on 72.00 ms. With no synchronous standby, every level except off waits 1.00 ms and loses "commits in the replication lag" at failover.
- Then run: uv run python phase05_replication/commit_levels.py --standbys "ANY 2 (s1, s2, s3)" --down s3. Expected: commits wait for: s1, s2. Add s2 to --down, and the commit blocks.
- Teaches: section 5.4.

-  E7 offline Which replica wins, and when.

- Run: uv run python phase05_replication/failover.py --primary 0/5000000 --replica r1=0/4F00000 --replica r2=0/4000000, then with only r2, then --detection.
- Expected: r1 is promoted, 1,048,576 bytes lost, timeline 2, history file 00000002.history. With only r2, no replica is promoted. --detection prints 20 to 30 s and 300 to 320 s.
- Then run with --max-lag 20000000 and only r2. Expected: r2 is promoted, and 16,777,216 bytes are lost.
- Teaches: section 5.5, one setting chooses between availability and data.

-  E8 break-it, offline A restore target that brings the bug back.

- Run: uv run python phase05_replication/pitr.py --target "2024-01-24 07:05:00+00" --demo linear.
- Expected: the line WRONG TARGET: it is at or after the bad migration, so the restore contains it, and settings that would restore the empty tables.
- Then run --demo gap and --demo chain. Expected: replay reaches only 2026-10-20 03:59:59+00:00, and cannot restore inc-tue: inc-tue needs inc-mon, which is not kept.
- Teaches: section 5.6, three ways a restore fails that a test drill finds.

-  E9 offline The connection budget.

- Run: uv run python phase05_replication/pool_model.py --budget --app-instances 40 --app-pool 10, then add --via-pgbouncer 2 --pool-size 40, then --busy --tps 2000 --hold-ms 205, then --notion, then --lint phase05_replication/sample_session.sql.
- Expected: OVER by 303, then within budget, spare 17, then 410 busy connections, then 600 and 1,800. The lint flags 7 of the 11 statements for at least one pooler.
- Teaches: section 5.7.

The lint uses the phase's list of six parameters that PgBouncer tracks. Since PgBouncer 1.26.0 the tracked list is longer, so with 1.26 on PostgreSQL 17 SET default_transaction_read_only and SET session_authorization are also tracked. If the sample file has such a line, the lint flags it where PgBouncer 1.26 handles it. The lint code was not changed or run again for this lesson.

-  E10 local Part of the demonstration: build a standby and read its positions.

- Read the plan first: uv run python phase05_replication/two_node.py --plan setup. Then run it: uv run python phase05_replication/two_node.py --run setup.
- Then run uv run python phase05_replication/lag.py --sql and paste the two queries into psql -h /tmp -p 5433 -d storage_lab_p5 and psql -h /tmp -p 5434 -d storage_lab_p5.
- Expected: Not run by the author yet. One row in pg_stat_replication with application_name standby1, state streaming and sync_state async, and all byte gaps 0 or a few hundred bytes. On the standby, status streaming and slot_name standby1. write_lag, flush_lag and replay_lag show small times while you write. They show NULL a short time after you stop, as section 27.2.4 of the docs says.
- Then measure read-after-write: on the primary run INSERT INTO t VALUES (1) after CREATE TABLE t (x int), and on the standby run SELECT count(*) FROM t at once. On a laptop the lag is short, so the row is usually there. Set recovery_min_apply_delay = '5s' on the standby, reload, and repeat. Expected: Not run by the author yet. The row appears about 5 s later, as in the test setup Dyte suggests.
- If it fails: read /tmp/storage_lab_p5/standby.log. A missing pg_hba.conf line for replication is the usual cause. The default initdb file allows local replication.
- Teaches: section 5.1.

-  E11 break-it, local An inactive slot, then the cap.

- Run: uv run python phase05_replication/two_node.py --run break-slot.
- Expected: Not run by the author yet. The slot standby1 shows active false, a recent inactive_since, and retained of more than 100 MB after pgbench -i -s 10. wal_status is reserved or extended.
- Then run: uv run python phase05_replication/two_node.py --run cap-slot.
- Expected: Not run by the author yet. Before the CHECKPOINT, wal_status unreserved and a negative safe_wal_size. After it, wal_status lost and invalidation_reason wal_removed. The log shows invalidating obsolete replication slot "standby1", with the DETAIL and HINT of section 5.2. If you now start the standby, its log shows that the WAL it needs has been removed, from the already been removed message of walsender.c.
- After this exercise the standby cannot recover. Run two_node.py --run teardown and --run setup before E12.
- Teaches: section 5.2.

-  E12 break-it, local A query conflict, then feedback.

- In one terminal, on the primary: pgbench -T 120 -c 4 -h /tmp -p 5433 storage_lab_p5, after a pgbench -i -s 10. In a second terminal, every 10 s: psql -h /tmp -p 5433 -d storage_lab_p5 -c "VACUUM pgbench_accounts".
- In a third terminal, on the standby: psql -h /tmp -p 5434 -d storage_lab_p5 -c "BEGIN ISOLATION LEVEL REPEATABLE READ" -c "SELECT count(*) FROM pgbench_accounts" -c "SELECT pg_sleep(90)" -c "SELECT count(*) FROM pgbench_accounts".
- Expected: Not run by the author yet. Within about 30 s of the first VACUUM after the snapshot, the standby session gets ERROR: canceling statement due to conflict with recovery with the DETAIL "User query might have needed to see row versions that must be removed". SELECT confl_snapshot FROM pg_stat_database_conflicts WHERE datname = 'storage_lab_p5' on the standby rises by 1. The standby log shows a recovery conflict wait line, because the setup set log_recovery_conflict_waits = on.
- Then on the standby: ALTER SYSTEM SET hot_standby_feedback = on, SELECT pg_reload_conf(), and repeat. Expected: Not run by the author yet. No cancel. On the primary, the xmin of slot standby1 in pg_replication_slots is set. backend_xmin stays NULL, because the lab standby uses a slot, as section 5.3 says. And n_dead_tup of pgbench_accounts in pg_stat_user_tables keeps growing until the standby query ends.
- Teaches: section 5.3.

-  E13 local Part of the demonstration: a synchronous commit that blocks.

- Run: uv run python phase05_replication/two_node.py --run sync. Expected: Not run by the author yet. sync_state of standby1 becomes sync.
- First, while the standby still runs, create the table on the primary: CREATE TABLE IF NOT EXISTS s (x int). That statement commits too, so it would block once the standby is gone.
- Stop the standby: pg_ctl -D /tmp/storage_lab_p5/standby -m fast stop. On the primary, run INSERT INTO s VALUES (1).
- Expected: Not run by the author yet. The INSERT does not return. In another session, SELECT wait_event_type, wait_event FROM pg_stat_activity WHERE query LIKE 'INSERT INTO s%' shows IPC and SyncRep. Press Ctrl-C in the first session. It prints the WARNING and DETAIL of section 5.4: "The transaction has already committed locally, but might not have been replicated to the standby". Then SELECT count(*) FROM s in a new session shows the row.
- Start the standby again. Set synchronous_standby_names back to '' with ALTER SYSTEM and reload, or the next exercises block too.
- Teaches: section 5.4, a canceled wait leaves a visible commit.

-  E14 break-it, local Promote, make a split brain on purpose, then rewind.

- First, on port 5433, run CREATE TABLE IF NOT EXISTS t (x int), so both servers have the table. The teardown in E11 removed the one from E10.
- Run: uv run python phase05_replication/two_node.py --run promote.
- Expected: Not run by the author yet. pg_is_in_recovery false on port 5434, and timeline 00000002, the first 8 hex digits of the current WAL file name. pg_control_checkpoint() can show timeline 1 for some minutes, until the checkpoint that promotion requests has finished. pg_wal of the standby holds 00000002.history. Its log has selected new timeline ID: 2.
- Now write on both: INSERT INTO t VALUES (100) on port 5433, the old primary, which still runs, and INSERT INTO t VALUES (200) on port 5434. That is split brain. Both accept the write.
- Run: uv run python phase05_replication/two_node.py --run rewind. It first creates the slot standby1 on port 5434. pg_rewind copies the configuration files from the new primary, and they name that slot.
- Expected: Not run by the author yet. pg_rewind prints its progress and "Done!". The old primary starts as a standby of port 5434. SELECT x FROM t on port 5433 shows 200 and not 100. The row only the old primary had is gone.
- Teaches: section 5.5, fencing exists to stop the write of 100 from ever being accepted.

-  E15 local Part of the demonstration: a timed point-in-time restore.

- Start from a fresh setup. Run: uv run python phase05_replication/two_node.py --run backup. Note the time: psql -h /tmp -p 5433 -d storage_lab_p5 -Atc "SELECT now()". Wait 5 seconds, then run the bad statement: DELETE FROM pgbench_accounts WHERE aid <= 1000. Then run SELECT pg_switch_wal(), so the segment reaches the archive.
- Run: time uv run python phase05_replication/two_node.py --run restore --target "<the time you noted, with the offset psql printed>".
- Expected: Not run by the author yet. pg_combinebackup writes a full backup from full and inc1. The restored server on port 5435 reports pg_is_in_recovery true and pg_get_wal_replay_pause_state paused, because recovery_target_action is pause. SELECT count(*) FROM pgbench_accounts WHERE aid <= 1000 on port 5435 is 1000. Run SELECT pg_wal_replay_resume() to end recovery. The log then shows selected new timeline ID. Write down the elapsed time.
- If recovery stops early: pg_stat_archiver on the primary shows the last archived segment. Section 5.6 explains a gap.
- Teaches: section 5.6, the drill that Linear had not run.

-  E16 break-it, local, optional A session setting that leaks through PgBouncer.

- Needs PgBouncer 1.26: brew install pgbouncer. Write /tmp/storage_lab_p5/pgbouncer.ini with a [databases] line storage_lab_p5 = host=/tmp port=5433, and in [pgbouncer]: listen_port = 6432, listen_addr = 127.0.0.1, pool_mode = transaction, default_pool_size = 1, auth_type = trust, and an auth_file that lists your user. Start it with pgbouncer -d /tmp/storage_lab_p5/pgbouncer.ini.
- Client 1: psql -h 127.0.0.1 -p 6432 -d storage_lab_p5 -c "SET statement_timeout = '1ms'". Client 2, a new connection: psql -h 127.0.0.1 -p 6432 -d storage_lab_p5 -c "SHOW statement_timeout" -c "SELECT pg_sleep(0.1)".
- Expected: Not run by the author yet. With a pool of one server connection, client 2 gets the same backend. It shows 1ms and its sleep fails with canceling statement due to statement timeout. Then clear the leaked value. Run RESET statement_timeout through PgBouncer, or restart PgBouncer. Repeat with SET LOCAL inside BEGIN ... COMMIT. Client 2 now shows the default 0. This follows from the PgBouncer docs: no reset query runs in transaction mode.
- Teaches: section 5.7, transaction mode breaks session state without an error at the place of the cause.

Use PgBouncer 1.26.1, not 1.26.0. Version 1.26.1 fixes three security bugs. In 1.17.0 through 1.26.0, a client that knows one user's password can log in as another user who uses SCRAM. In another, an unauthenticated client can make 1.20.0 through 1.26.0 spin forever on a CPU core. To see what 1.26 still does not track on PostgreSQL 17, repeat the two clients with SET search_path = pg_catalog and SHOW search_path. Expect client 2 to show the leaked value, by reading of the PgBouncer configuration page, not by a run.

When you finish, run uv run python phase05_replication/two_node.py --run teardown.

Check it yourself

- Check 1. Open phase05_replication/lag.py:139, time_lag(). Line 147 returns 0 when the received and replayed LSNs are equal. Name the failure this check hides: a standby whose WAL receiver has stopped. Which column of which view, from section 5.1, catches it instead?

- Check 2. Open phase05_replication/slot_retention.py:78, wal_status(). The cap rule is at line 85. Suppose max_slot_wal_keep_size is smaller than max_wal_size. Work out from the code which state the slot skips. Then compare your answer with the comment above GetWALAvailability in xlog.c at REL_17_11: "If max_slot_wal_keep_size is smaller than max_wal_size, this state is not returned."

- Check 3. Open phase05_replication/hot_standby.py:83, replay(). Line 103 sets the base of the deadline. Change it to at and run --shared-grace. Which query now finishes, and which sentence of the docs, section 26.4.2, says the change is wrong?

- Check 4. Open phase05_replication/failover.py:71, pick_candidate(). It compares each replica with the old primary's last LSN. In a real failure the primary is gone. Where does a failover manager get that LSN, and what does it mean for the loss count if the last known value is old? The model does not answer this. Patroni's docs, "maximum_lag_on_failover", give the starting point.

- Check 5. In any repository you own that talks to PostgreSQL, run grep -rn "pool_size\|max_overflow\|maxPoolSize\|pool_max\|connection_limit" <your repo>/. Add up the pools of every process that runs at the peak of a deploy. Compare the total with max_connections minus the reserved slots of the server it reaches, as in section 5.7.

## Checkpoint questions

The phase's seven scenario questions, each with numbers and an answer sketch. The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

Open the questions

- Test-out, explain. pg_stat_replication on the primary shows pg_current_wal_lsn() 9/12000000, sent_lsn 9/12000000, write_lsn and flush_lsn 9/11F00000, and replay_lsn 9/E000000. The primary writes 20 MiB/s of WAL. Which stage is behind, by how many bytes and about how many seconds of the primary's work? Name the two likely causes from sections 5.1 and 5.3, and the signal that tells them apart.
Answer sketchWrite and flush are 9/12000000 − 9/11F00000 = 0x100000 = 1,048,576 bytes behind sent. That is small, network and disk are fine. Replay is 0x11F00000 − 0xE000000 = 0x3F00000 = 66,060,288 bytes behind flush. At 20 MiB/s that is 63 / 20 = 3.15 s of the primary's work. lag.py prints the same. Cause one: replay is a single process and cannot keep up with a primary that writes from many sessions. Cause two: replay is waiting for a standby query to finish, up to max_standby_streaming_delay. Three signals point to the conflict. pg_stat_database_conflicts rises, and the startup process shows the RecoveryConflictSnapshot wait event. With log_recovery_conflict_waits = on, there is also a log line for each wait longer than 1 s. Without them, and with high CPU on the startup process, it is replay speed.

- Test-out, predict. A CDC connector stops at 09:00. The primary writes 6 MiB/s of WAL and has 120 GiB free. max_slot_wal_keep_size is 20480 MB, and a checkpoint runs every 5 minutes. When does the slot become unreserved, and when lost? Does the disk fill? Now the archive command has also been failing since 09:00. What changes?
Answer sketchThe cap is 20,480 MB = 1,280 segments of 16 MiB. The slot is unreserved once the current segment is more than 1,280 past the slot's, after 1,281 × 16 = 20,496 MiB. At 6 MiB/s that is 20,496 / 6 = 3,416 s, about 09:57. The next checkpoint, at 3,600 s, 10:00, makes it lost. The connector must take a new snapshot. pg_wal stops near 20 GiB, so the disk does not fill. Without a cap it would be full at 120 × 1,024 / 6 = 20,480 s = 5.7 h, about 14:41. With a failing archive, the slot is still lost at 10:00, but no unarchived segment is removed. So the disk is full at 14:41 again, and pg_stat_archiver.failed_count is the alert you needed. slot_retention.py prints these times.

- Test-out, demonstrate. Run E10, E13 and E15. Show the standby's positions and lag columns. Show the blocked commit with its wait event, and the WARNING after the cancel. Show the restored row count and the time the restore took. Explain why each result follows from the sections, and not from timing luck.
Answer sketchFrom the runs. E10: one row in pg_stat_replication, state streaming, and gaps near 0. The lag columns go NULL when idle, which follows from section 27.2.4 of the docs. E13: with the only synchronous standby down, a commit waits in IPC / SyncRep without a timeout. Ctrl-C ends the wait, not the commit, which is already in the primary's WAL. So the row is visible, which is the DETAIL text of syncrep.c. E15: the target is before the DELETE, the backup ended before the target, and the archive has every segment. So replay stops before the DELETE and pauses, because recovery_target_action is pause. The count is 1000. Each result follows from a rule, not from timing.

- (a) A colleague says: "The report replica keeps canceling our 6-hour analytics job. Turn on hot_standby_feedback on every replica and the problem is gone." Argue for or against, with numbers. The busiest table takes 800 updates per second. (b) A second colleague says: "Set synchronous_commit = remote_apply everywhere and read-after-write is fixed". What must also be true? What does each commit pay with a 2.5 ms round trip? What happens when both standbys are down?
Answer sketch(a) Against, for every replica. Feedback makes the primary keep every row version the oldest standby query can see. 800 updates per second for 6 hours is 800 × 21,600 = 17,280,000 dead versions held on the primary, on the failover replica too. Lock conflicts, such as VACUUM truncation, still cancel queries. Better: a separate report replica with feedback off and a long max_standby_streaming_delay, as Twitch ran at 6 h. It is never a failover target. The failover replica keeps the 30 s default and a statement_timeout per role. (b) remote_apply waits only if synchronous_standby_names names a standby, and it covers only reads on synchronous standbys. Each commit pays at least the 2.5 ms round trip, plus the standby's flush and replay. With FIRST 1 (s1, s2) and both down, every commit that waits blocks. A canceled wait leaves a visible commit that a failover can lose.

- This is broken. After a failover at 03:10, the API fails for 4 minutes. PgBouncer's SHOW POOLS shows cl_waiting at 380 and maxwait at 95 seconds. The PostgreSQL log shows remaining connection slots are reserved for roles with the SUPERUSER attribute, and the on-call engineer, who is not a superuser, cannot log in to look. The server has max_connections = 200 and the default reserved settings. Three PgBouncer processes each serve 4 database and user pairs with the default default_pool_size. What is the cause, how do you confirm it, and what do you change so the engineer can always log in?
Answer sketchThe budget: 3 × 4 × 20 = 240 server connections against 200 − 3 = 197 normal slots, over by 43. pool_model.py --budget prints it. After the failover every pool refilled at once and hit the limit. Clients queued in PgBouncer, which shows as cl_waiting and maxwait. The on-call role is not a superuser, and reserved_connections is 0, so no slot was left for it. That message means 3 or fewer slots were free when the engineer connected, by the rule of section 5.7. Confirm: count pg_stat_activity rows by usename from a superuser session, which the 3 superuser slots still allow, or read PgBouncer's SHOW SERVERS. Then add up the pool settings. Fix: lower the pool sizes, or set max_db_connections in each PgBouncer. Each process keeps its own count, so three processes may open three times that limit. That is inferred from the configuration page. Keep the sum below the normal slots with a margin. Set reserved_connections = 5 and grant pg_use_reserved_connections to the operators' role, never to the pooler's role. Alert on connections as a percentage of the limit, as Buttondown now does.

- Show the arithmetic. (a) Two LSNs are 2/A0000000 and 2/9E800000. How many bytes apart are they, and how long is that at 4 MiB/s? (b) A synchronous commit has a 0.8 ms local flush, a 2.5 ms round trip and a 0.8 ms standby flush. What does on wait for each commit? Every order updates one counter row. At most how many commits per second can that row take, against local? (c) A restore copies an 800 GiB base backup at 250 MiB/s. The base backup is 26 hours old, and the primary writes 3 MiB/s of WAL. Replay runs at 50 MiB/s. How long until the data is back, and what would cut it? (d) An agent service runs 50 steps per second. Each step holds a transaction open for 1.2 s across an LLM call. How many server connections are busy? What is it if the transaction closes before the call and lasts 8 ms?
Answer sketch(a) 0x2A0000000 − 0x29E800000 = 0x1800000 = 25,165,824 bytes = 24 MiB. At 4 MiB/s, 6 s. (b) on waits 0.8 + 2.5 + 0.8 = 4.1 ms, which commit_levels.py with those inputs prints. If each commit holds the counter row's lock until it returns, the row takes at most 1 / 0.0041 = 243.9 commits per second. With local, 1 / 0.0008 = 1,250. That bound is inferred from the docs' sentence that locks are held until the transfer is confirmed. (c) The base: 800 × 1,024 / 250 = 3,276.8 s = 0.9 h. The WAL: 26 × 3,600 × 3 = 280,800 MiB = 274.2 GiB, at 50 MiB/s = 5,616 s = 1.6 h. Total about 2.5 h, before you check the data. pitr.py --restore-hours prints 0.9 and 1.6 h. More frequent base backups, or PostgreSQL 17 incremental backups, cut the replay part. (d) 50 × 1.2 = 60 busy connections. At 8 ms, 50 × 0.008 = 0.4, so one connection serves them.

- Given these constraints, design. An agent platform keeps its task queue and run history on managed PostgreSQL 17. No task result that returned OK may be lost when one zone fails. The UI must show a run's result right after the run writes it. Analysts run 2-hour queries. A CDC connector feeds a search index and must survive a failover. You must restore to any minute of the last 7 days. 60 application processes connect. Give the topology, the settings of each server, the pooler and its budget, the backup setup, and the drills. Say what each choice costs.
Answer sketchOne design among several. Run the primary with a synchronous standby in a second zone. On RDS that is a Multi-AZ deployment. Self-hosted, use two standbys in other zones and synchronous_standby_names = 'ANY 1 (s1, s2)', so one standby down blocks nothing. synchronous_commit = on for task results. A cheaper level, set per transaction with SET LOCAL, for logs and traces. Read-after-write: the UI reads a run's own results from the primary for a few seconds after the write. Or it waits for the LSN on the replica. A separate report replica for analysts: feedback off, long delay, not a failover target. CDC: on self-hosted 17, a logical slot with failover set, sync_replication_slots = on on the standby, the standby's slot in synchronized_standby_slots. Check that the managed service supports it before you rely on it. max_slot_wal_keep_size set below the free space, and an alert on safe_wal_size. Backups: base backups plus continuous archiving with at least 7 days of retention, or the managed equivalent. Restore points before migrations. A monthly timed restore drill. Pooling: PgBouncer in transaction mode, or RDS Proxy, sized by Little's law with transactions closed before LLM calls. The pool total stays below the normal slots, and reserved_connections is kept for operators. No session state through the pooler. Costs: a round trip on every synchronous commit, and writes that wait when no synchronous standby answers. Also a replica that only serves reports, and a CDC rebuild if the slot cap is reached.

## Cheatsheet

The phase's cheatsheet, with the Aurora quorum and the PgBouncer 1.26 lines corrected.

Open the cheatsheet
POSITIONS AND LAG (PostgreSQL 17)
  LSN               byte position, X/Y hex. a - b = bytes. pg_wal_lsn_diff(a, b)
  primary view      pg_stat_replication: sent, write, flush, replay _lsn,
                    write/flush/replay _lag, sync_state, backend_xmin
  gaps              current->sent primary busy | sent->write network
                    write->flush standby disk | flush->replay replay or conflict
  standby view      pg_stat_wal_receiver.status = streaming
  time lag          now() - pg_last_xact_replay_timestamp() grows when idle.
                    Check receive_lsn = replay_lsn first
  RDS ReplicaLag    up to 5 min on an idle source. Aurora lag usually < 100 ms
  status reply      wal_receiver_status_interval 10 s
  read-after-write  read own writes from the primary, wait for the LSN, or
                    remote_apply. Test with recovery_min_apply_delay

SLOTS
  keep WAL          slot: from restart_lsn, unlimited by default
                    wal_keep_size 0 | archive: unarchived WAL is never removed
  cap               max_slot_wal_keep_size -1 = unlimited. Checked at checkpoint
  wal_status        reserved -> extended (> max_wal_size) -> unreserved (> cap)
                    -> lost (next checkpoint). Alert on safe_wal_size
  fill time         free GiB x 1024 / WAL MiB/s. 250 GiB at 10 MiB/s = 7.1 h
  full pg_wal       PANIC shutdown, no committed data lost, offline
  log line          invalidating obsolete replication slot "x"
  17 columns        inactive_since, invalidation_reason, failover, synced
  18                idle_replication_slot_timeout (0 = off)
  RDS metrics       OldestReplicationSlotLag, ReplicationSlotDiskUsage,
                    TransactionLogsDiskUsage, FreeStorageSpace

HOT STANDBY
  conflict          cleanup record vs older snapshot, ACCESS EXCLUSIVE lock,
                    drop database/tablespace, buffer pin
  wait              max_standby_streaming_delay 30 s, archive delay 30 s.
                    Counted from WAL receipt: grace is shared
  error             canceling statement due to conflict with recovery, 40001
  feedback          hot_standby_feedback off. On: no cleanup cancels, bloat on
                    primary = update rate x oldest standby query age
  still conflicts   locks, incl. VACUUM truncation (vacuum_truncate = off)
  signals           pg_stat_database_conflicts, log_recovery_conflict_waits
  split roles       failover standby: short delay + statement_timeout
                    report replica: long delay, feedback off, never promoted

SYNCHRONOUS COMMIT
  names empty       every level except off = flushed on primary only
  levels            off < local < remote_write (standby OS) < on (standby disk)
                    < remote_apply (visible on standby)
  wait              local flush + RTT + standby step. Floor = one RTT
  locks             held during the wait
  standbys          FIRST n (a, b, c) or ANY n (...). Fewer than n alive: block
  cancel            WARNING ... committed locally, but might not have been
                    replicated. Visible now, lost at failover
  wait event        IPC / SyncRep
  per transaction   SET LOCAL synchronous_commit = ...
  RDS               Multi-AZ instance: sync, standby not readable
                    Multi-AZ cluster: ack from 1 of 2 readers, readable
                    Aurora: writer waits for 4 of 6 storage copies in 3 AZs
                    (4/6 inferred for Aurora PostgreSQL)

FAILOVER
  steps             detect, choose, fence, promote, redirect
  Patroni 4.1.5     ttl 30, loop_wait 10, retry_timeout 10:
                    loop_wait + 2 x retry_timeout <= ttl. Lost host: 20-30 s
                    PG crash, Patroni alive: up to 10 + 300 + 10 = 320 s
                    maximum_lag_on_failover 1048576 bytes
  managed           RDS Multi-AZ 60-120 s, Multi-AZ cluster < 35 s,
                    Aurora < 60 s (often < 30), no replica < 10 min
  promote           pg_promote(wait true, 60 s). New timeline + N.history
  old primary       fence it (STONITH). pg_rewind needs wal_log_hints or
                    checksums (off in 17, on by default in 18 initdb)
  clients           RDS changes DNS: reconnect, JVM DNS TTL <= 60 s
  failover slots 17 slot failover = true; standby sync_replication_slots on,
                    primary_slot_name, hot_standby_feedback on, dbname in
                    primary_conninfo; primary synchronized_standby_slots.
                    Usable only if synced = true before failover

BACKUPS AND PITR
  PITR              base backup + every WAL segment. pg_dump is not PITR
  archive_command   exit 0 if and only if the copy is safe. pg_stat_archiver
  archive_timeout   0 = off. "a minute or so". RDS ships logs every 5 min
  target            after the backup ENDED, before the bad commit, numeric
                    offset ('... 16:39:00+00'), no 'EST'
  action            recovery_target_action pause (default) ->
                    pg_wal_replay_resume(). inclusive on
  restore           restore files, empty pg_wal, saved WAL back,
                    restore_command + target,
                    recovery.signal, start, check, then promote
  restore point     pg_create_restore_point('before_x') -> recovery_target_name
  incremental 17    summarize_wal on (off), wal_summary_keep_time 10 days,
                    pg_basebackup --incremental=<prev>/backup_manifest,
                    pg_combinebackup -o out full inc1 inc2 (oldest first),
                    pg_verifybackup. Keep the whole chain. Use >= 17.11
  restore time      base GiB x 1024 / MiB/s + WAL GiB x 1024 / replay MiB/s
  managed           RDS PITR -> new instance, new endpoint, not for replicas
                    Aurora: continuous, 1-35 days, default 1

POOLING
  model             one OS process per connection
  slots             max_connections 100 - superuser_reserved 3
                    - reserved_connections 0 = 97 for normal roles.
                    WAL senders are extra. Errors: SQLSTATE 53300
  reserve           reserved_connections + grant pg_use_reserved_connections
                    to operators only
  budget            sum of all pools at deploy peak < normal slots
  Little's law      busy = tps x hold time. Commit before an LLM call
  PgBouncer         session (default) | transaction | statement.
                    default_pool_size 20 per (db, user), max_db_connections
                    0 = unlimited, query_wait_timeout 120 s
  txn mode breaks   SET/RESET, LISTEN, WITH HOLD, SQL PREPARE, temp tables
                    that outlive the txn, LOAD, session advisory locks
  safe in txn mode  SET LOCAL (inferred), pg_advisory_xact_lock, ON COMMIT DROP,
                    SET of a parameter PgBouncer tracks: since 1.26.0 every one
                    PostgreSQL reports. On 17 search_path and statement_timeout
                    still leak
  prepared stmts    protocol level since 1.21.0, max_prepared_statements 200
                    since 1.24.0. Not SQL PREPARE. After DDL: RECONNECT
  version           1.26.1 (security fixes for 1.17.0 to 1.26.0)
  signals           SHOW POOLS cl_waiting, maxwait. pg_stat_activity by state
  RDS Proxy pins    SET, PREPARE/EXECUTE/DISCARD, temp objects, cursors,
                    LISTEN, LOAD, nextval/setval, pg_advisory_lock, > 16 KB.
                    Metric DatabaseConnectionsCurrentlySessionPinned

## Sources

The phase's references, then the sources the study note added and the lesson uses. Every phase source was fetched while the phase was written, and the study note read its own sources again.

Open the sources
Every source below was fetched on 2026-10-20 while this phase was written. PostgreSQL source files were read at tag REL_17_11, the 17.11 release of 2026-08-13, from a local clone. Every URL was checked again with check_urls.py on 2026-10-20. Primary sources come first in each group. Vendor pages are marked.

PostgreSQL 17 documentation: replication

- 26.2 Log-Shipping Standby Servers. https://www.postgresql.org/docs/17/warm-standby.html Focus on: 26.2.5 for streaming and its "typically under one second", and 26.2.5.2 for the monitoring gaps. Then 26.2.6 for slots and the caution box, and 26.2.8 for synchronous replication, its costs and its availability rules. Read it before E10.

- 26.3 Failover. https://www.postgresql.org/docs/17/warm-standby-failover.html Focus on: STONITH, the degenerate state after a failover, and the advice to switch over regularly as a test. Short. Read it with section 5.5.

- 26.4 Hot Standby. https://www.postgresql.org/docs/17/hot-standby.html Focus on: 26.4.2, the list of conflicts, the shared grace, early cleanup, and the remedies. Read it before E12.

- 19.6 Replication settings. https://www.postgresql.org/docs/17/runtime-config-replication.html Focus on: max_slot_wal_keep_size, wal_keep_size, wal_sender_timeout, synchronous_standby_names, synchronized_standby_slots, hot_standby_feedback, max_standby_streaming_delay, recovery_min_apply_delay and sync_replication_slots.

- 19.5 Write Ahead Log settings. https://www.postgresql.org/docs/17/runtime-config-wal.html Focus on: synchronous_commit and its table of modes in 19.5.1, archive_timeout in 19.5.3, the recovery targets and recovery_target_action in 19.5.6, and summarize_wal in 19.5.7.

- 19.3 Connections and Authentication. https://www.postgresql.org/docs/17/runtime-config-connection.html Focus on: max_connections, reserved_connections and superuser_reserved_connections, and the rule that a standby needs the same or a higher max_connections.

- 47.2 Logical Decoding Concepts. https://www.postgresql.org/docs/17/logicaldecoding-explanation.html Focus on: 47.2.2 for what a slot prevents and the wraparound warning. Then 47.2.3 for failover slots in 17: the six settings, the synced rule and the sync failure message.

- 52.19 pg_replication_slots. https://www.postgresql.org/docs/17/view-pg-replication-slots.html Focus on: wal_status with its four states, safe_wal_size, inactive_since and invalidation_reason.

- 27.2 The Cumulative Statistics System. https://www.postgresql.org/docs/17/monitoring-stats.html Focus on: 27.2.4 pg_stat_replication and the note on lag times, 27.2.6 pg_stat_wal_receiver, 27.2.12 pg_stat_archiver and 27.2.18 pg_stat_database_conflicts.

- 9.28 System Administration Functions. https://www.postgresql.org/docs/17/functions-admin.html Focus on: pg_walfile_name_offset and pg_split_walfile_name examples in 9.28.3, used by lag.py's self-test. pg_promote, pg_last_wal_replay_lsn and pg_last_xact_replay_timestamp in 9.28.4. pg_create_restore_point in 9.28.3.

- 8.20 pg_lsn Type. https://www.postgresql.org/docs/17/datatype-pg-lsn.html Focus on: the format and the subtraction rule. One paragraph.

- Release notes for 16. https://www.postgresql.org/docs/16/release-16.html Focus on: the item that adds reserved_connections and pg_use_reserved_connections. Section 5.7 relies on it.

- 50.2 How Connections Are Established. https://www.postgresql.org/docs/17/connect-estab.html Focus on: the process-per-user model. The reason poolers exist, in one page.

PostgreSQL 17 documentation: backups

- 25.3 Continuous Archiving and Point-in-Time Recovery. https://www.postgresql.org/docs/17/continuous-archiving.html Focus on: the note that pg_dump cannot be used for PITR, and the exit-status rule of 25.3.1. Then 25.3.3 on incremental backups, the restore steps of 25.3.5, and 25.3.6 on timelines. The core reading for section 5.6.

- 25.1 SQL Dump. https://www.postgresql.org/docs/17/backup-dump.html Focus on: what a dump is, and the large-database tips. Read it to see what a dump restore must redo.

- pg_basebackup. https://www.postgresql.org/docs/17/app-pgbasebackup.html Focus on: -X stream as the default, -R, -S, --incremental and --checkpoint.

- pg_combinebackup. https://www.postgresql.org/docs/17/app-pgcombinebackup.html Focus on: the order of the arguments, and what it does not verify.

- pg_verifybackup. https://www.postgresql.org/docs/17/app-pgverifybackup.html Focus on: what the manifest check covers. Use it on every backup you keep.

- pg_rewind. https://www.postgresql.org/docs/17/app-pgrewind.html Focus on: the requirement of wal_log_hints or checksums, and how it finds the point of divergence. Read it before E14.

- Release notes for 17. https://www.postgresql.org/docs/17/release-17.html Focus on: the 17.0 items on incremental backup and failover slots. The 17.8 and 17.11 fixes for incremental backup are in release-17.sgml at REL_17_11, lines 5246 to 5257 and 1954 to 1966.

PostgreSQL source, REL_17_11

- src/backend/access/transam/xlog.c. https://raw.githubusercontent.com/postgres/postgres/REL_17_11/src/backend/access/transam/xlog.c Focus on: KeepLogSeg, GetWALAvailability, the slot invalidation call in CreateCheckPoint, and RemoveOldXlogFiles. slot_retention.py follows them.

- src/backend/replication/slot.c and slotfuncs.c. https://raw.githubusercontent.com/postgres/postgres/REL_17_11/src/backend/replication/slot.c Focus on: ReportSlotInvalidation for the log lines. slotfuncs.c lines 397 to 408 compute safe_wal_size.

- src/backend/replication/syncrep.c. https://raw.githubusercontent.com/postgres/postgres/REL_17_11/src/backend/replication/syncrep.c Focus on: SyncRepWaitForLSN and the two cancel warnings at lines 302 to 322.

- src/backend/tcop/postgres.c. https://raw.githubusercontent.com/postgres/postgres/REL_17_11/src/backend/tcop/postgres.c Focus on: errdetail_recovery_conflict and the cancel path with SQLSTATE 40001.

Failover managers and managed services

- Patroni 4.1.5: dynamic configuration and replication modes. https://patroni.readthedocs.io/en/latest/dynamic_configuration.html https://patroni.readthedocs.io/en/latest/replication_modes.html Focus on: ttl, loop_wait, retry_timeout, primary_start_timeout, maximum_lag_on_failover, synchronous_mode, and the note that a canceled wait can still lose a transaction. The default of 1048576 is in patroni/global_config.py line 171 at v4.1.5.

- AWS: Failing over a Multi-AZ DB instance, vendor. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZ.Failover.html Focus on: "typically 60–120 seconds", the DNS change and the JVM TTL.

- AWS: Multi-AZ DB instance and Multi-AZ DB cluster deployments, vendor. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZSingleStandby.html https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/multi-az-db-clusters-concepts.html Focus on: the synchronous standby that cannot serve reads, and the semisynchronous cluster with two readers. The failover page of the cluster form says "typically under 35 seconds": https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/multi-az-db-clusters-concepts-failover.html

- AWS: Read replicas for RDS for PostgreSQL, vendor. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PostgreSQL.Replication.ReadReplicas.html Focus on: the idle lag of "up to five minutes", and that a read replica cannot be the source of a point-in-time restore.

- AWS: Aurora replication, storage and high availability, vendor. https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Replication.html https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.StorageReliability.html https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.AuroraHighAvailability.html Focus on: the shared cluster volume, lag "usually much less than 100 milliseconds", six storage nodes, and failover times.

- AWS: Restoring to a point in time, and Aurora backups, vendor. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PIT.html https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Managing.Backups.html Focus on: logs every five minutes, LatestRestorableTime, the new instance, and Aurora's 1 to 35 days with a default of one.

- AWS: CloudWatch metrics for RDS and Aurora, vendor. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-metrics.html https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.AuroraMonitoring.Metrics.html Focus on: ReplicaLag, OldestReplicationSlotLag, ReplicationSlotDiskUsage, TransactionLogsDiskUsage, DatabaseConnections and AuroraReplicaLag.

- AWS: logical replication on RDS for PostgreSQL, vendor. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.FeatureSupport.LogicalReplication.html Focus on: the warning that an unread logical slot can "quickly fill up your DB instance's storage".

Connection pooling

- PgBouncer features. https://www.pgbouncer.org/features.html Focus on: the three modes and the feature table for transaction pooling. One page that answers most pooling bugs.

- PgBouncer configuration. https://www.pgbouncer.org/config.html Focus on: pool_mode, default_pool_size, max_db_connections, reserve_pool_size, query_wait_timeout, server_reset_query, server_reset_query_always and max_prepared_statements with its notes on reuse and cached plan must not change result type.

- PgBouncer usage: SHOW POOLS. https://www.pgbouncer.org/usage.html Focus on: cl_waiting, sv_active, sv_idle and maxwait.

- PgBouncer changelog. https://www.pgbouncer.org/changelog.html Focus on: 1.21.0 of 2023-10-16 for protocol-level prepared statements, 1.24.0 of 2025-01-10 for the default of 200, and 1.26.1 of 2026-10-14, the current release, for its three security fixes.

- AWS: Avoiding pinning an RDS Proxy, vendor. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-pinning.html Focus on: the PostgreSQL list, the 16 KB rule, the transaction-level advisory locks that do not pin, and DISCARD ALL. The metrics are on https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.monitoring.html

Production reports

- GitLab: Postmortem of database outage of January 31, 2017. https://about.gitlab.com/blog/postmortem-of-database-outage-of-january-31/ Focus on: the replication that failed because WAL was removed and there was no archive, then the pg_dump version mismatch. Sections 5.2 and 5.6.

- Dyte: Learning to Live With Replication Lag, 2023-04-03, archived. https://web.archive.org/web/20250119071551id_/https://dyte.io/blog/mitigating-replication-lag/ Focus on: the 404 from a replica read, recovery_min_apply_delay in development, and the cache with a TTL above the lag bound. The live URL redirects, so this is the archive copy.

- Netflix: Automating RDS Postgres to Aurora Postgres Migration, 2026-02-12, archived. https://web.archive.org/web/20260718004553id_/https://netflixtechblog.com/automating-rds-postgres-to-aurora-postgres-migration-261ca045447f?gi=ffb22d8d38e2 Focus on: "Unexpected Replication Slot Behavior", the 0-to-64 MB pattern of OldestReplicationSlotLag, and how CDC slots are dropped before cutover.

- Twitch: How Twitch uses PostgreSQL, 2016-10-11. https://blog.twitch.tv/en/2016/10/11/how-twitch-uses-postgresql-c34aa9e56f58 Focus on: the ad-hoc replicas with a 6-hour delay, statement_timeout per role, the PgBouncer CPU limit, the prepared-statement fork and the max_connections rule. Old. The PostgreSQL facts still hold on 17. PgBouncer 1.21.0 later added support for named prepared statements.

- GitHub: October 21 post-incident analysis, 2018. https://github.blog/news-insights/company-news/oct21-post-incident-analysis/ Focus on: the cross-region promotion, the 954 writes, the four-hour backups and their restore time, and the change to Orchestrator. MySQL, not PostgreSQL. Phase 1, section 1.7, uses the same post.

- Fly.io: ORD transit loss destabilized Managed Postgres clusters, 2026-06-11. https://fly.io/infra-log/transit-loss-ord/ Focus on: failovers caused by nodes that could not reach Patroni's DCS. A short log entry.

- Heroku: Incident review, October 2025. https://www.heroku.com/blog/incident-review-intermittent-disruption-of-services-on-october-2025/ Focus on: false health alerts and the auto-failover they started.

- Linear: incident on Jan 24th, 2024. https://linear.app/now/linear-incident-on-jan-24th-2024 Focus on: the timeline, the TRUNCATE ... CASCADE, and the paragraph on the untested point-in-time recovery.

- Resend: Incident report for February 21, 2024. https://www.resend.com/blog/incident-report-for-february-21-2024 Focus on: the wrong backup timestamp and the two restore times.

- Instapaper: Outage Cause & Recovery, 2017-02-14, archived. https://web.archive.org/web/20170216165223id_/https://medium.com/making-instapaper/instapaper-outage-cause-recovery-3c32a7e9cc5f Focus on: "Backups", the dump times, the row-count estimate, and the monthly restore test. MySQL on RDS.

- Railway: Incident Report, October 28, 2025. https://blog.railway.com/p/incident-report-oct-28th-2025 Focus on: the pooler limit above the database limit and the reserved-slot error.

- Buttondown: Public postmortem, database connection exhaustion, 2026-04-01. https://buttondown.com/blog/incident-0024 Focus on: the health check that passed, and the five fixes in order.

- Notion: The Great Re-shard, 2023-07-17. https://www.notion.com/blog/the-great-re-shard Focus on: "An important detour to shard our PgBouncer connection-pooling layer", for the 600 and 1,800 connections.

- OpenAI: Scaling PostgreSQL to power 800 million ChatGPT users, 2026-01-22, archived. https://web.archive.org/web/20261010101204id_/https://openai.com/index/scaling-postgresql/ Focus on: "Connection pooling" and "Scaling read replicas". The live page returned 403 to scripts, so this is the archive copy of 2026-10-10.

Added by the study note and the lesson

- Amazon Aurora: Design Considerations for High Throughput Cloud-Native Relational Databases, SIGMOD 2017. https://www.amazon.science/publications/amazon-aurora-design-considerations-for-high-throughput-cloud-native-relational-databases https://cdn.amazon.science/dc/2b/4ef2b89649f9a393d37d3e042f4e/amazon-aurora-design-considerations-for-high-throughput-cloud-native-relational-databases.pdf The write quorum of 4 out of 6 copies, for Aurora MySQL. The lesson's Aurora correction.

- AWS: Read replica configuration with PostgreSQL, mechanisms per version, vendor. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PostgreSQL.Replication.ReadReplicas.Mechanisms-versions.html Each in-Region read replica has its own physical slot on the source from 14.1.

- AWS: Logical replication for Multi-AZ DB clusters, vendor. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_MultiAZDBCluster_LogicalRepl.html Logical slots copied asynchronously to each reader, and the warning on two consumers.

- AWS: Dead connection handling in PostgreSQL, vendor. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.DeadConnectionHandling.html The RDS server keepalive defaults.

- AWS: Aurora PostgreSQL fast failover, vendor. https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.BestPractices.FastFailover.html Client keepalive values that notify the application within five seconds.

- AWS Knowledge Center: conflict with recovery on RDS for PostgreSQL, vendor. https://repost.aws/knowledge-center/rds-postgresql-error-conflict-recovery hot_standby_feedback off by default on RDS, and the bloat warning.

- Debezium PostgreSQL connector documentation. https://debezium.io/documentation/reference/stable/connectors/postgresql.html The per-database confirmation, the RDS idle case and the heartbeat settings.

- asyncpg FAQ. https://magicstack.github.io/asyncpg/current/faq.html The prepared-statement errors behind PgBouncer, and statement_cache_size=0.

- Atlassian: Post-Incident Review on the April 2022 outage. https://www.atlassian.com/blog/atlassian-engineering/post-incident-review-april-2022-outage PITR within 30 days, and partial restores inside shared data stores that took about 48 hours per batch of sites at first, then about 12 hours per site.
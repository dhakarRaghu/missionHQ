# Phase 5 — Replication, failover, backups and pooling

**The question this phase answers:** your database runs as a primary with replicas, a backup system and a connection pooler. When one of them fails, which writes survive, how long do clients wait, and how far back can you restore?

**The promises this phase pays.** Phases 1, 3 and 4 point here for replicas. Phase 4 also points here for pooling from section 4.2, the connection budget from section 4.7, and restores from section 4.8. Phase 1, section 1.7, said its durability sentence covers one node only. Phase 4, section 4.5, named the replication slot as a holder of the cleanup horizon and stopped there. Course 5 exists only as a plan, and its Phase 3 replicates a toy store, not PostgreSQL. So this phase teaches what PostgreSQL 17 does when it has replicas, slots, a WAL archive and a pooler. Course 5 keeps the general theory of replication. Phase 1, section 1.7, also listed a case its sentence leaves out: the GitLab.com outage of 2017-01-31. Data was deleted, and the backups did not restore. Section 5.6 is that case.

## Why you're here

Here is the situation this phase follows. It is an example. The times and sizes are invented to fit the mechanisms, and each section explains one row.

The order system and the task queue of Phases 1 to 4 now run on a managed PostgreSQL 17 primary. Two streaming replicas follow it. One is the failover standby. The other serves reads: the order status page, reports, and the search over agent run history. PgBouncer sits between about 40 application processes and the database, in transaction mode. A change-data-capture connector, CDC for short, reads every change through a logical replication slot. It feeds the search index.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The running case: one bad day. Times and sizes are an example            │
├──────────────────────────────────────────────────────────────────────────┤
│ 09:00  the search team pauses the CDC connector to rebuild the index.    │
│        Its logical slot stays on the primary                       5.2   │
│ 10:05  an agent run writes its result on the primary. The UI reads it    │
│        from the read replica 40 ms later and gets 404              5.1   │
│ 11:30  a report on the read replica fails: "canceling statement due      │
│        to conflict with recovery"                                  5.3   │
│ 14:00  disk alert on the primary: pg_wal is 176 GiB, growing 10 MiB/s    │
│                                                                    5.2   │
│ 15:10  the primary's host dies. The standby is promoted after 90 s.      │
│        About 1 MiB of WAL never reached it                   5.4, 5.5    │
│ 15:12  every pool reconnects at once: "remaining connection slots are    │
│        reserved". The on-call engineer cannot log in               5.7   │
│ 16:40  a migration empties a table by mistake. Restore to 16:39?   5.6   │
├──────────────────────────────────────────────────────────────────────────┤
│ seven failures, one cause: copies of the WAL that lag, are kept, or      │
│ are missing, and connections that are not budgeted                       │
└──────────────────────────────────────────────────────────────────────────┘
```

None of these is rare. The production reports in this phase show each of them at a named company. They come from Dyte, Netflix, Twitch, GitHub, Linear, Resend, Instapaper, Railway, Buttondown, Notion and OpenAI. Each one is predictable from a small number of positions in the WAL and a small number of connection slots. This phase teaches you to read both.

## What you can do after this phase

1. Read `pg_stat_replication` and say which of four stages a lagging replica is stuck in, from LSN differences in bytes.
2. Tell a real lag in seconds from the false lag that an idle primary shows, and fix a read-after-write bug on a replica.
3. Predict how fast an inactive slot fills `pg_wal`, set `max_slot_wal_keep_size`, and read `wal_status` and `safe_wal_size`.
4. Explain why a long query on a replica is canceled, choose between `max_standby_streaming_delay` and `hot_standby_feedback`, and name what each one costs.
5. For each `synchronous_commit` level, say what a client that got OK can lose in each failure, and what it waits for.
6. Walk through a failover: detection, the choice of replica, promotion, the new timeline and fencing. Keep a CDC slot through it with the failover slots of PostgreSQL 17.
7. Choose a base backup and a recovery target for a point-in-time restore. Use the incremental backup of PostgreSQL 17. Explain why `pg_dump` is not point-in-time recovery.
8. Say what PgBouncer transaction mode breaks, how prepared statements pass through it, and what pins an RDS Proxy session.
9. Size a connection budget against `max_connections` with the reserved slots, so that an operator can still log in during a connection storm.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PHASE 5: Replication, failover, backups and pooling                      │
├──────────────────────────────────────────────────────────────────────────┤
│ 5.1 What a replica has     four LSNs, lag in bytes and in seconds,       │
│                            read-after-write                              │
│ 5.2 Slots and retention    the WAL a slot keeps, the cap, logical slots  │
│ 5.3 Replicas for reads     query conflicts, delay, feedback and bloat    │
│ 5.4 Synchronous commit     what "committed" means with a standby         │
│ 5.5 Failover               promotion, timelines, fencing, failover slots │
│ 5.6 Backups and PITR       base backup, archive, target, incremental     │
│ 5.7 Connection pooling     process per connection, PgBouncer, RDS Proxy  │
│ Lab: E1 to E16. The demonstration: E10, E13 and E15                      │
└──────────────────────────────────────────────────────────────────────────┘
```

## What this phase assumes

Five ideas from this course and two from other courses are used here and not taught again.

- **The WAL and the LSN, from Phase 1, section 1.2.** Every change is a WAL record. A log sequence number, LSN for short, is a byte position in the WAL. The difference of two LSNs is a number of bytes. A commit waits for the local WAL flush. With a synchronous standby, it then waits in `SyncRepWaitForLSN`, step 4 of the commit order in section 1.2.
- **Checkpoints and WAL removal, from Phase 1, section 1.5.** A checkpoint moves the REDO point forward. After it, older WAL segment files can be removed or recycled. A segment is one file in `pg_wal`, 16 MB by default. `max_wal_size` is 1 GB, a soft limit.
- **The durability boundary, from Phase 1, sections 1.6 and 1.7.** `synchronous_commit = off` replies before the flush. It can lose up to three times `wal_writer_delay`, 600 ms at the default. The level can be set per transaction.
- **Snapshots and the cleanup horizon, from Phase 3, section 3.2, and Phase 4, section 4.5.** Here is the rule. VACUUM removes a dead row version only if no open snapshot can still see it. The oldest snapshot sets the horizon. A long transaction holds it back and causes bloat.
- **Generic plans, from Phase 4, section 4.2.** A prepared statement gets five custom plans, then maybe a generic one. Phase 4, section 4.2, says behind a pooler the count is kept per server connection. Section 5.7 shows why.
- **Pool sizing with Little's law, from elite-performance, Phase 5B, section 5.5.** Busy connections equal rate times hold time. That section measured the wait inside a client pool. This phase adds the database side: the server's slots and the pooler between.
- **Replication and failover in Redis, from the Redis course, Phase 4, sections 4.2, "Replication", and 4.3, "Failover".** They teach asynchronous replication and the lost-write window at failover. They also show why a majority is needed to promote. PostgreSQL has the same window. This phase shows its exact size and the settings that close it.

**The running system.** The lab builds a throwaway primary on port 5433 and a standby on port 5434. It adds a WAL archive. All of it lives under `/tmp/storage_lab_p5`. `two_node.py` holds every command. Its database is `storage_lab_p5`, so the labs of earlier phases keep working.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. The seven model scripts and every `--self-test` run with no server. The live exercises need the PostgreSQL 17 binaries on your PATH and about 200 MB under `/tmp`. Run all commands from `elite-storage/code/`.

Time: 3 hours for the reading. The labs take about 3 hours more.

---

## 5.1 — What a replica has (WAL shipping, the four positions of a standby, lag in bytes and in seconds, and read-after-write)

Why this matters: at 10:05 the UI read a row that the primary had committed, and the replica said it did not exist. Nothing was broken. A streaming replica is always somewhat behind, and the question is how far, at which stage, and for which reads it matters. PostgreSQL tells you exactly, in bytes, if you read the right columns.

**The mental model.** A physical standby is a second PostgreSQL server that replays the primary's WAL. It has the same files, byte for byte, so it runs the same major version and cannot take writes. Each standby has a WAL receiver process. On the primary, a WAL sender process serves it. The PostgreSQL 17 docs, section 26.2.5, say the primary "streams WAL records to the standby as they're generated, without waiting for the WAL file to be filled". They add that streaming replication "is asynchronous by default". So a commit returns to the client before any standby has the record.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One commit record on its way to a standby. Each arrow is a gap in bytes  │
├──────────────────────────────────────────────────────────────────────────┤
│ PRIMARY                                    STANDBY                       │
│ ┌──────────────────────┐   network   ┌──────────────────────────────┐    │
│ │ backend writes WAL   │             │ WAL receiver                 │    │
│ │ pg_current_wal_lsn() │             │  write_lsn   in the OS cache │    │
│ │        │             │             │  flush_lsn   on the disk     │    │
│ │        ▼             │             │        │                     │    │
│ │ WAL sender reads it  ├────────────►│        ▼                     │    │
│ │  sent_lsn            │             │ startup process replays it   │    │
│ └──────────────────────┘             │  replay_lsn  queries see it  │    │
│                                      └──────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────────────┤
│ current ≥ sent ≥ write ≥ flush ≥ replay. pg_stat_replication shows the   │
│ last four, from the standby's status replies. pg_current_wal_lsn()       │
│ gives the first                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

The standby sends a status reply at least every `wal_receiver_status_interval`, 10 seconds by default, and after each batch of WAL it writes. Verified from `guc_tables.c` at REL_17_11 and the docs, section 26.2.8.1. The docs for `wal_receiver_status_interval`, section 19.6.3, add that a reply goes out each time the write or flush position changes. So `write_lsn` and `flush_lsn` stay fresh while WAL flows. `replay_lsn` can be older. The same docs say "the apply position may lag slightly behind the true position".

There is also an older transport. A standby can read whole 16 MB segment files from the WAL archive with `restore_command`. That is file-based log shipping. It is slower, because a segment ships only when it is full. Streaming uses the archive only to catch up when the primary has already removed the WAL it needs. Section 5.2 shows when that happens.

**Two facts about a physical copy.** It replicates the whole cluster, every database, and it replays every change. And some settings must match. The docs for `max_connections` say: "When running a standby server, you must set this parameter to the same or higher value than on the primary server. Otherwise, queries will not be allowed in the standby server." Twitch hit this. Its post "How Twitch uses PostgreSQL", 2016, says raising `max_connections` meant raising it on every replica first, which needs a restart, and then failing over to a primary with the new value. Logical replication, which sends row changes per table, is the other kind. Section 5.2 meets it through its slots.

**Reading the gap, in bytes.** Each gap between two positions points at one part of the system. The docs, section 26.2.5.2, name two of them. A large gap between `pg_current_wal_lsn()` and `sent_lsn` "might indicate that the primary server is under heavy load". A gap after `sent_lsn` "might indicate network delay, or that the standby is under heavy load". `lag.py` prints every gap and names the largest:

```bash
uv run python phase05_replication/lag.py --current 5/3A000000 --sent 5/39F00000 \
    --write 5/39E00000 --flush 5/39E00000 --replay 5/38000000 --wal-rate-mb 8
```

```text
stage              bytes behind     where to look
current -> sent        1,048,576  ~0.12 s   primary busy, or the WAL sender is slow to read WAL
sent -> write          1,048,576  ~0.12 s   network, or the standby is slow to receive
write -> flush                 0  ~0.00 s   the standby's disk flush
flush -> replay       31,457,280  ~3.75 s   the standby's startup process: replay is slow or waits on a query conflict
total current -> replay: 33,554,432 bytes
largest gap: flush -> replay, 31,457,280 bytes
```

Output of a run on 2026-10-20. The LSNs are an example. The seconds are an estimate: 31,457,280 bytes is 30 MiB, and at 8 MiB/s of WAL that is 3.75 seconds of the primary's work. Here the standby has received everything. Its startup process is behind. Replay is one process, so a primary that writes WAL from many sessions at once can outrun it. Section 5.3 shows a second cause of a replay gap: replay that waits for a query.

The query behind the table, from `lag.py --sql`. `pg_wal_lsn_diff` subtracts two LSNs:

```sql
-- On the primary, PostgreSQL 17. One row per standby or WAL client.
SELECT application_name, state, sync_state,
       pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn)   AS send_gap_bytes,
       pg_wal_lsn_diff(sent_lsn, flush_lsn)              AS net_and_disk_bytes,
       pg_wal_lsn_diff(flush_lsn, replay_lsn)            AS replay_gap_bytes,
       write_lag, flush_lag, replay_lag, backend_xmin
  FROM pg_stat_replication;
```

The column names are verified from `system_views.sql` at REL_17_11, lines 893 to 917. A standby that is missing from this view is not connected at all. That is a different failure. On the standby, `pg_stat_wal_receiver.status` then is not `streaming`, or the view has no row.

**Reading the gap, in seconds.** Three columns give time: `write_lag`, `flush_lag` and `replay_lag`. Each one is the "time elapsed between flushing recent WAL locally and receiving notification" that the standby wrote, flushed or applied it. Verified from the docs, section 27.2.4. The same section warns that they "are not predictions of how long it will take for the standby to catch up". When the primary goes idle, they "continue to be displayed for a short time and then show NULL".

The common query on the standby is `now() - pg_last_xact_replay_timestamp()`. That function returns "the time stamp of the last transaction replayed", from the docs, section 9.28.4. It is a commit time. When the primary stops committing, the value stops, and the clock keeps running.

**WRONG: alert on the time since the last replayed commit.**

```sql
-- WRONG: grows on an idle primary although nothing is missing
SELECT now() - pg_last_xact_replay_timestamp() AS lag;
```

```text
primary idle after t=0. received == replayed check: off
   t (s)   byte lag   reported time lag (s)
       1          0          1.0
      10          0         10.0
      60          0         60.0
     290          0        290.0
```

That is `lag.py --idle-demo --no-idle-check`, run on 2026-10-20. The standby has every byte, and the query reports almost 5 minutes. A pager rule on 60 seconds fires every quiet night.

**RIGHT: check the bytes first, then the clock.**

```sql
-- RIGHT: zero when the standby has replayed all it received
SELECT CASE WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn() THEN interval '0'
            ELSE now() - pg_last_xact_replay_timestamp() END AS lag;
```

```text
primary idle after t=0. received == replayed check: on
   t (s)   byte lag   reported time lag (s)
       1          0          0.0
      10          0          0.0
      60          0          0.0
     290          0          0.0
```

This query has one blind spot. A standby whose WAL receiver has stopped also shows received equal to replayed. So alert on `pg_stat_wal_receiver.status` as well, and on the primary's byte gap. Both checks are inferred from the function definitions above and were not run.

**Managed services show the same false alarm.** The AWS page for RDS for PostgreSQL read replicas says so. "If no user transactions are running on the source DB instance, the associated PostgreSQL read replica reports a replication lag of up to five minutes". RDS computes `ReplicaLag` as the current time minus the last committed transaction's time. Its source switches WAL segments every 5 minutes by default, which writes a record and resets the value. Verified from the AWS page, fetched 2026-10-20. Netflix met the byte version of this. Its post "Automating RDS Postgres to Aurora Postgres Migration", 2026-02-12, says `OldestReplicationSlotLag` "never settles at a steady zero". On an idle source it dropped to 0 at each empty segment switch, about every 300 seconds, and then went back to 64 MB. 64 MB was one WAL segment of that RDS source. The switch came from `archive_timeout = 300s`. Section 5.6 explains that setting.

Aurora works differently. The AWS Aurora replication page says the replicas "all see the data in the cluster volume as a single logical volume". So a replica keeps no copy of the data of its own. That is inferred from the sentence. The same page says their lag "is usually much less than 100 milliseconds after the primary instance has written an update", and that it grows with the write rate. The metric is `AuroraReplicaLag`, in milliseconds. Verified from the page, fetched 2026-10-20.

**Read-after-write on a replica.** The 10:05 row is the Dyte case. Dyte's post "Learning to Live With Replication Lag", 2023-04-03, describes it. After a participant was written, a separate service read it from a replica to make an auth token. Under load, replication lag rose, and the route returned 404 with "participant not found". Verified from the archived copy of the post.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Read-after-write across two services. Times are an example               │
├──────────────────────────────────────────────────────────────────────────┤
│ t=0 ms     service A commits INSERT participant on the primary. OK       │
│ t=2 ms     service A calls service B with the participant id             │
│ t=5 ms     service B reads the id from the replica                       │
│            replica replay_lsn is behind the commit's LSN                 │
│            → 0 rows → 404 "participant not found"                        │
│ t=40 ms    the replica replays the commit. Too late for this request     │
├──────────────────────────────────────────────────────────────────────────┤
│ low lag in development hides it. Dyte suggests recovery_min_apply_delay  │
│ on a test replica to make the lag large on purpose                       │
└──────────────────────────────────────────────────────────────────────────┘
```

Dyte's fix was a cache. Each write also goes to Redis, with a time-to-live "greater than our replication lag upper bound", and an alert fires when the lag passes that bound. Verified from the post. The cache only works if the alert does. Here are the other fixes, ordered by how often they fit:

1. **Read your own recent writes from the primary.** Route a session's reads to the primary for a few seconds after it writes. Pick the window above your measured lag. This is inferred practice, not a PostgreSQL feature.
2. **Wait for the LSN.** After the commit, the writer reads `pg_current_wal_lsn()` and passes it on. The reader waits until `pg_last_wal_replay_lsn()` on the replica has reached it, with a short timeout, and falls back to the primary. Inferred from the function definitions in the docs, section 9.28. Not run.
3. **Wait at commit.** `synchronous_commit = remote_apply` makes the commit wait until a synchronous standby has applied it. It costs commit time, and only synchronous standbys count. Section 5.4 has the numbers.

Phase 3, part "Why you're here", shows one more limit of replica reads. Jepsen found Long Fork cycles when a test read through the primary and the reader endpoint of an RDS Multi-AZ cluster. AWS's reply, also in Phase 3, says a replica makes commits visible in WAL order, which can differ from the primary's order.

**The sentence to remember:** a standby has four positions: the primary's `sent`, then `write`, `flush` and `replay`. The byte gap between neighbours tells you which part is slow. Time lag from the last commit is only true while the primary is busy.

**The trap:** alerting on `now() - pg_last_xact_replay_timestamp()` or on RDS `ReplicaLag` alone. Both rise on an idle primary, up to five minutes on RDS, and teach the team to ignore lag pages. The second trap is reading a row from a replica right after writing it, as in the Dyte case.

**Try this now:** run `uv run python phase05_replication/lag.py --idle-demo` and then with `--no-idle-check`. Then grep your own code for reads that follow a write in the same request: `grep -rn "replica\|read_only\|using('replica')" <your repo>/`. For each hit, name the fix from the list above that it needs.

---

## 5.2 — Replication slots and WAL retention (why slots exist, the disk an inactive slot fills, the cap, and logical slots)

Why this matters: at 09:00 the CDC connector stopped, and at 14:00 the primary's disk was filling. The connector did nothing wrong. Its slot did what slots are for: it kept every byte of WAL the connector had not read yet. A slot protects the reader and puts the primary's disk at risk. This section shows how fast, and the setting that chooses between the two.

**The problem slots solve.** Without a slot, the primary keeps WAL only for its own needs. After a checkpoint, older segments are removed or recycled. The docs, section 26.2.5, say a standby that falls too far behind then "will need to be reinitialized from a new base backup". The WAL sender reports `requested WAL segment %s has already been removed`, from `walsender.c` line 3124 at REL_17_11.

That is how the GitLab.com outage of 2017-01-31 began. GitLab's postmortem says: "The replication failed as WAL segments needed by the secondary were already removed from the primary. As GitLab.com was not using WAL archiving, the secondary had to be re-synchronised manually." The re-sync meant wiping the secondary's data directory and running `pg_basebackup`. During that work an engineer ran the wipe on the primary instead. Phase 1, section 1.7, covers the rest: the backups that did not restore. Verified from the postmortem, fetched 2026-10-20.

There are three ways to keep WAL for a standby:

| Method | What it keeps | Default | What goes wrong |
|---|---|---|---|
| `wal_keep_size` | a fixed amount of past WAL, always | 0 | too small, and the standby is cut off. Too large, and it wastes disk every day |
| WAL archive | every segment, in another place | off | the standby fetches from the archive and needs `restore_command` |
| replication slot | exactly what each reader has not confirmed | none | a reader that stops keeps WAL without limit |

Verified from the docs, sections 19.6.1 and 26.2.6. The docs give the reason for slots: the other methods "often result in retaining more WAL segments than required, whereas replication slots retain only the number of segments known to be needed". The same page has a caution box: "Beware that replication slots can cause the server to retain so many WAL segments that they fill up the space allocated for pg_wal."

**What a slot holds.** A slot is a small record on the primary. It survives restarts. Its fields are in `pg_replication_slots`:

- `restart_lsn`: the oldest WAL the reader may still need. Every segment from here on stays.
- `xmin`: for a physical slot whose standby sends `hot_standby_feedback`, the oldest snapshot the standby still uses. VACUUM on the primary keeps rows newer than it, for every table. Section 5.3 explains feedback.
- `catalog_xmin`: for a logical slot, the same for the system catalogs only.
- `active`, and from PostgreSQL 17 `inactive_since`: is a reader connected, and since when not.
- `wal_status` and `safe_wal_size`: how close the slot is to losing its WAL. Below.
- `invalidation_reason`, `failover` and `synced`: also new in 17. Section 5.5 uses the last two.

The column list is verified from `system_views.sql` at REL_17_11, lines 1006 to 1029. The docs, section 26.2.6, state the link that Phase 4, section 4.5, uses. A slot keeps rows that could cause a conflict "even when the standby is disconnected". Feedback without a slot "provides no protection during any time period when the standby is not connected". So a dead standby with a slot and feedback holds VACUUM back for the whole cluster.

**How fast the disk fills.** The slot keeps WAL at the rate the primary writes it. `slot_retention.py` follows the PostgreSQL 17.11 rules for what a checkpoint keeps. It assumes a constant rate and a checkpoint every 5 minutes. For the running case, 10 MiB/s of WAL and 250 GiB free:

```text
WAL 10.0 MiB/s, free 250.0 GiB, max_slot_wal_keep_size -1 MB, archive failing: False
no-limit time to full: 25,600 s = 7.1 h
     t (s)   wal_status   retained GiB   pg_wal GiB   safe_wal_size MiB
         0   reserved            0.00         1.00   NULL
       106   extended            1.04         1.04   NULL
pg_wal passes 250.0 GiB at t = 25,600 s (7.1 h). PostgreSQL then PANICs when it cannot write WAL.
```

That is `slot_retention.py --rate-mb 10 --free-gb 250`, run on 2026-10-20. The arithmetic is 250 × 1,024 / 10 = 25,600 seconds. A connector paused at 09:00 stops the primary at about 16:07. At 14:00 it holds 5 × 3,600 × 10 MiB, about 176 GiB. The docs, section 25.3.1, say what a full `pg_wal` does: "PostgreSQL will do a PANIC shutdown. No committed transactions will be lost, but the database will remain offline until you free some space."

**The cap, and the states of a slot.** `max_slot_wal_keep_size` limits what slots may keep. The default is -1, and the docs say that then "replication slots may retain an unlimited amount of WAL files". With a limit, a slot that falls further behind loses its WAL at the next checkpoint. The function `GetWALAvailability` in `xlog.c` at REL_17_11 sets `wal_status`:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ wal_status of an inactive slot. 10 MiB/s, cap 10 GiB, checkpoint 300 s   │
├──────────────────────────────────────────────────────────────────────────┤
│ t=0 s        reserved     the slot's WAL is within max_wal_size          │
│ t=106 s      extended     past max_wal_size, kept only because of slot   │
│ t=1,026 s    unreserved   past the cap. The next checkpoint removes it.  │
│                           A reader that reconnects now can still recover │
│ t=1,200 s    lost         the checkpoint removed the WAL. Gone for good  │
│                                                                          │
│ pg_wal stops near 10 GiB. The reader must be rebuilt from scratch        │
└──────────────────────────────────────────────────────────────────────────┘
```

From `slot_retention.py --rate-mb 10 --free-gb 250 --max-slot-mb 10240`, run on 2026-10-20. The states and their meaning are verified from the docs for `pg_replication_slots`, section 52.19. `safe_wal_size` is the number of bytes that can still be written to WAL before the slot is in danger of becoming lost. That is the docs' definition, paraphrased. It is NULL when the cap is -1. Its formula is in `slotfuncs.c` lines 397 to 408. At t=0 the slot is in segment 1. The limit is the start of segment 1 + 640 + 1 = 642, at 10,272 MiB. Minus the current position, 16 MiB, that leaves 10,256 MiB. Alert on it.

When the checkpoint invalidates the slot, the server log says so. The text is from `ReportSlotInvalidation` in `slot.c` at REL_17_11, lines 1540 to 1590. The LSN and the byte count below are an example:

```text
LOG:  invalidating obsolete replication slot "cdc_search"
DETAIL:  The slot's restart_lsn 2/F4000000 exceeds the limit by 1828716544 bytes.
HINT:  You might need to increase "max_slot_wal_keep_size".
```

A logical reader then gets `can no longer get changes from replication slot "cdc_search"`, with the detail "This slot has been invalidated because it exceeded the maximum reserved size." That is `logical.c` lines 625 to 627. A physical standby gets the `already been removed` error from above.

So the cap is a choice between two failures. Without it, a stopped reader stops the primary. With it, a stopped reader is cut off and must be rebuilt. A standby needs a new base backup. A CDC connector needs a new snapshot. For a primary that serves users, the second failure is the smaller one. Pick the cap from your free space, and alert well before it on `safe_wal_size`.

**Two things the cap does not cover.** First, a failing `archive_command`. A segment that has not been archived is never removed, slot or no slot. `RemoveOldXlogFiles` checks `XLogArchiveCheckDone` before it removes a file, at `xlog.c` lines 3841 and 3886, REL_17_11. `--archive-failing` shows the slot go lost on time while `pg_wal` keeps growing. Second, with `summarize_wal = on`, `KeepLogSeg` also keeps WAL that the summarizer has not read yet. Section 5.6 turns that setting on for incremental backups.

**Logical slots.** A logical slot is what a CDC tool such as Debezium reads. It decodes WAL into row changes. It holds WAL from its `restart_lsn`, and it holds `catalog_xmin`. The docs, section 47.2.2, warn that slots "will prevent removal of required resources even when there is no connection using them". They add: "In extreme cases this could cause the database to shut down to prevent transaction ID wraparound". The AWS page on RDS logical replication says the same about disk. "If you set up a logical replication slot and don't read from the slot, data can be written and quickly fill up your DB instance's storage". Verified from both pages, fetched 2026-10-20.

Netflix met an inactive logical slot while it moved its fleet of almost 400 clusters from RDS PostgreSQL to Aurora. The post of 2026-02-12 says `OldestReplicationSlotLag` was "unexpectedly high" because of "an inactive logical replication slot on the source". They removed it. Their migration workflow also stops CDC consumers and drops their slots before cutover, so the slots cannot block WAL recycling. Verified from the archived copy.

**Signals.** On self-hosted PostgreSQL, read the slots and the archive together:

```sql
SELECT slot_name, slot_type, active, inactive_since, wal_status,
       pg_size_pretty(safe_wal_size)                                   AS safe,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained,
       age(xmin) AS xmin_age, age(catalog_xmin) AS catalog_xmin_age
  FROM pg_replication_slots;
SELECT failed_count, last_failed_wal, last_failed_time, last_archived_time FROM pg_stat_archiver;
```

On RDS, the CloudWatch metrics are `OldestReplicationSlotLag` in bytes, `ReplicationSlotDiskUsage`, `TransactionLogsDiskUsage` and `FreeStorageSpace`. Aurora PostgreSQL has the first two as well. Verified from the RDS and Aurora metrics pages, fetched 2026-10-20. PostgreSQL 18 adds `idle_replication_slot_timeout`, off by default, which invalidates a slot after it stays idle that long. Verified from `guc_tables.c` line 3109 at REL_18_6.

**The sentence to remember:** a slot keeps all WAL its reader has not confirmed. So an inactive slot grows `pg_wal` at the full WAL rate until the disk is full. `max_slot_wal_keep_size` trades that outage for a reader you must rebuild.

**The trap:** leaving `max_slot_wal_keep_size` at -1 and alerting only on disk. At 10 MiB/s, 250 GiB is gone in 7.1 hours, on a night when nobody reads the alert. The second trap is a feedback slot of a dead standby, which also stops VACUUM on every table.

**Try this now:** run `uv run python phase05_replication/slot_retention.py --rate-mb 10 --free-gb 250 --max-slot-mb 10240`. Then put your own WAL rate in. On a server, take two readings of `pg_current_wal_lsn()` 60 seconds apart and divide the `pg_wal_lsn_diff` by 60.

---

## 5.3 — Replicas that serve reads (query conflicts, the replay delay, hot_standby_feedback and the bloat it moves to the primary)

Why this matters: at 11:30 a report on the read replica failed after running for a while. The same query on the primary would have finished. A read replica is not a quiet copy. It replays the primary's cleanup while your query runs, and one of the two must give way. You choose which, with two settings, and each choice costs something you will see elsewhere.

**The mental model.** A standby that runs queries is a hot standby. `hot_standby` is on by default. Verified from `guc_tables.c` at REL_17_11. Replay must apply every WAL record in order, because the primary already did the change. The primary does not know which queries run on the standby. So some records conflict with standby queries. The docs, section 26.4.2, list the cases:

- an `ACCESS EXCLUSIVE` lock from the primary, from `LOCK` or from DDL such as `DROP TABLE` or `ALTER TABLE`
- dropping a tablespace or a database that a standby session uses
- "a vacuum cleanup record" that removes rows a standby snapshot "can still see"
- a vacuum cleanup record on a page that a standby query is reading at that moment

The docs name the most common one: "The most common reason for conflict between standby queries and WAL replay is early cleanup". On the primary, VACUUM removes a dead row version when no snapshot on the primary can see it. A standby query started earlier may still see it.

**The standby's choice: wait, then cancel.** When a conflicting record arrives, replay waits for the query. It waits at most `max_standby_streaming_delay`, 30 seconds by default, or `max_standby_archive_delay` for WAL read from the archive, also 30 seconds. Then it cancels the query. Verified from `guc_tables.c` at REL_17_11. The client gets this, with SQLSTATE 40001, the code for a serialization failure:

```text
ERROR:  canceling statement due to conflict with recovery
DETAIL:  User query might have needed to see row versions that must be removed.
```

The message and the code are from `postgres.c` lines 2552 and 3195 to 3199 at REL_17_11. Other details name the other cases, such as "User was holding a relation lock for too long". If the conflict is over a lock held by an idle transaction, the whole session ends with `terminating connection due to conflict with recovery`. Verified from the docs, section 26.4.2, and `postgres.c` line 3218. The code ends the session in more cases than the docs name. `postgres.c` lines 3154 to 3203 end it for any conflict while the session waits for its client inside a transaction. They also end it for most conflicts inside a subtransaction. The docs add that "Canceled queries may be retried immediately", and the retry may succeed. So the retry of 40001 from Phase 3, section 3.5, part "The retry, done right", also covers this error.

**The grace is shared.** You might expect each query to get 30 seconds. It does not. The docs, section 26.4.2: "the delay parameters are compared to the elapsed time since the WAL data was received by the standby server". A second record that arrives while replay waits for the first has its clock running already. `hot_standby.py --shared-grace` models the case:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Two cleanup records, max_standby_streaming_delay = 30 s                  │
├──────────────────────────────────────────────────────────────────────────┤
│ t=0    query X starts on the standby. It needs 35 s                      │
│ t=10   record 1 arrives. It conflicts with X. Deadline 10 + 30 = 40      │
│ t=15   query Y starts. It needs 45 s                                     │
│ t=20   record 2 arrives. Replay is still waiting on record 1             │
│ t=35   X finishes. Replay applies record 1, reaches record 2             │
│        record 2 conflicts with Y. Deadline 20 + 30 = 50, not 35 + 30     │
│ t=50   Y is CANCELED after 35 s. It got 15 s of grace, not 30            │
│                                                                          │
│ replay fell up to 30 s behind: record 2 arrived at 20, applied at 50     │
└──────────────────────────────────────────────────────────────────────────┘
```

From a run of `hot_standby.py --shared-grace` on 2026-10-20. The model's rule is the docs' sentence above. Its self-test turns the rule off, `shared_grace=False`, and Y then finishes. That is the wrong belief, and the docs say so. `max_standby_streaming_delay` "is not the same as the maximum length of time a query can run before cancellation". Also note the cost of waiting: while replay waits, every other query on that standby sees older data. The flush-to-replay gap of section 5.1 grows by up to the delay.

**What you can change, and what each costs.** The default run of the model has three queries and a cleanup record every 60 seconds:

```text
max_standby_streaming_delay 30 s, hot_standby_feedback off, cleanup records at [60.0, 120.0, 180.0, 240.0]
query        start   would end   result
report A         0        200   CANCELED at t=90 s after 90 s
api B           95        115   finished
report C       100        200   CANCELED at t=150 s after 50 s
replay fell behind by up to 30 s
```

Output of `hot_standby.py`, run on 2026-10-20. The model assumes a table updated all the time, so every cleanup record conflicts with every older query. A quiet table conflicts less. Three ways out:

```
┌────────────────────────────────┬─────────────────────────────────────────┐
│ option                         │ what it costs                           │
├────────────────────────────────┼─────────────────────────────────────────┤
│ 1. keep the delay short, and   │ long queries fail. Replay stays within  │
│    cap queries with            │ 30 s, so the replica is still a good    │
│    statement_timeout per role  │ failover target                         │
├────────────────────────────────┼─────────────────────────────────────────┤
│ 2. hot_standby_feedback = on   │ no cleanup conflicts. The primary keeps │
│                                │ the dead rows instead: bloat, as if the │
│                                │ query ran on the primary                │
├────────────────────────────────┼─────────────────────────────────────────┤
│ 3. a separate report replica,  │ no cancels and no bloat on the primary. │
│    long delay, feedback off    │ That replica can fall hours behind. It  │
│                                │ must never be a failover target         │
└────────────────────────────────┴─────────────────────────────────────────┘
```

**Option 2, in detail.** With `hot_standby_feedback = on`, the standby sends the xmin of its oldest snapshot to the primary, at most once per `wal_receiver_status_interval`. The primary's VACUUM then keeps every row version that snapshot can see. The docs, 19.6.3, say it can "eliminate query cancels caused by cleanup records, but can cause database bloat on the primary for some workloads". The docs, 26.4.2, add the fair comparison: "the cleanup situation will be no worse than if the standby queries were running directly on the primary server". The model, with feedback on:

```text
max_standby_streaming_delay 30 s, hot_standby_feedback on, cleanup records at [60.0, 120.0, 180.0, 240.0]
query        start   would end   result
report A         0        200   finished
api B           95        115   finished
report C       100        200   finished
replay fell behind by up to 0 s
primary holds up to 199,000 dead row versions (t=199 s), at 1000 updates/s. Vacuum cannot remove them until the query ends.
```

From `hot_standby.py --feedback`, run on 2026-10-20. The arithmetic is 1,000 updates per second times the age of the oldest standby query, 199 seconds at the last second it runs. A 6-hour report would hold 21.6 million versions. Phase 4, section 4.5, showed what that does: the table grows, and the space comes back only with a rewrite. On the primary, the feedback shows as `backend_xmin` in `pg_stat_replication`. If the standby uses a slot, it shows as the slot's `xmin` instead, and `backend_xmin` stays NULL. Verified from `walsender.c` lines 2740 to 2749 at REL_17_11. `age()` of either one is the number to alert on. Section 5.2 showed that a slot keeps this xmin while the standby is down.

Feedback does not stop lock conflicts. Every `ACCESS EXCLUSIVE` lock on the primary still conflicts. One source of such locks is VACUUM itself. The `CREATE TABLE` docs, under `vacuum_truncate`, say truncating the empty pages at the end of a table "requires ACCESS EXCLUSIVE lock on the table". So an ordinary VACUUM on the primary can cancel a long read on the standby. That link is inferred from the two docs pages and was not run. If it happens, `confl_lock` grows, and `ALTER TABLE ... SET (vacuum_truncate = off)` on that table removes the cause.

**How Twitch split it.** Twitch's post of 2016 describes all three options in one fleet. The live read replicas used a strict `statement_timeout` per role, such as `alter user team_01 set statement_timeout = '1s'`, and `hot_standby_feedback = on`. After that, the errors "canceling statement due to conflict with recovery" have "not been much of an issue". For ad-hoc analytics, each data center has a host outside the live read set, with `hot_standby_feedback = off and max_standby_streaming_delay = 6h`, "so that the replication source isn't burdened". Verified from the post, fetched 2026-10-20.

**Signals.** On the standby, `pg_stat_database_conflicts` counts cancels per database and per cause. The columns are `confl_snapshot`, `confl_lock`, `confl_bufferpin`, `confl_deadlock`, `confl_tablespace` and `confl_active_logicalslot`. The last one is new in PostgreSQL 16. Verified from `system_views.sql` at REL_17_11, lines 1087 to 1097. Set `log_recovery_conflict_waits = on`, off by default. Then the standby logs every replay wait longer than `deadlock_timeout`, 1 second by default. While replay waits on a cleanup conflict, the startup process shows the wait event `RecoveryConflictSnapshot`. For a dropped tablespace it is `RecoveryConflictTablespace`. No other wait event has that prefix. Verified from `wait_event_names.txt` at REL_17_11, lines 148 and 149.

**The sentence to remember:** on a busy table, a standby must choose between canceling your long query and pausing replay. Feedback moves the cost to the primary as bloat. The grace of `max_standby_streaming_delay` is shared by all queries waiting at once.

**The trap:** turning on `hot_standby_feedback` on every replica to stop the errors, and finding bloat on the primary a week later. The second trap is using a 6-hour report replica as a failover target.

**Try this now:** run `uv run python phase05_replication/hot_standby.py --shared-grace`. Then run it with `--max-delay 21600` and read the replay lag line. Name which of your replicas is a failover target and which serves long reads.

---

## 5.4 — Synchronous replication and what "committed" means with replicas (the five synchronous_commit levels, what each can lose, and what each waits for)

Why this matters: at 15:10 the primary died, and about 1 MiB of WAL had not reached the standby. Every commit in that WAL had already returned OK to its client. With the defaults, that loss is expected. Phase 1, section 1.7, asked you to state your durability boundary for one node. This section extends the sentence to a primary with standbys, and shows the price of each stronger promise.

**The mental model.** Phase 1, section 1.2, gave the commit order. The commit record is flushed locally, and then step 4, `SyncRepWaitForLSN`, waits for standbys if any are synchronous. Which standbys are synchronous is set on the primary by `synchronous_standby_names`. Its default is empty. How far the record must travel is set by `synchronous_commit`, per transaction. The docs, section 19.5.1, give the five levels:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ How far the commit record travels before the client gets OK              │
├──────────────────────────────────────────────────────────────────────────┤
│ primary                       network        synchronous standby         │
│ WAL buffer ──► local disk ─────────────► OS cache ──► disk ──► replayed  │
│     ▲              ▲                         ▲          ▲         ▲      │
│    off           local                 remote_write    on   remote_apply │
├──────────────────────────────────────────────────────────────────────────┤
│ with synchronous_standby_names empty, local, remote_write, on and        │
│ remote_apply all stop at the local disk                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

The docs' own table lists four guarantees. `commit_levels.py` prints them with what a client that got OK can lose in each failure:

```text
synchronous standby configured: True. Inputs are examples, not measurements.
level         wait ms  primary restart          failover                        failover, standby OS crash              read on standby
off           0.00     up to 600 ms of commits  commits in the replication lag  commits not yet flushed on the standby  may not see it yet
local         1.00     nothing                  commits in the replication lag  commits not yet flushed on the standby  may not see it yet
remote_write  2.05     nothing                  nothing                         commits not yet flushed on the standby  may not see it yet
on            3.00     nothing                  nothing                         nothing                                 may not see it yet
remote_apply  3.50     nothing                  nothing                         nothing                                 sees it
```

Output of a run on 2026-10-20. The loss columns follow the docs' table, column by column. Two lines of the docs explain the middle rows. `remote_write` "ensures data preservation if a standby instance of PostgreSQL crashes, but not if the standby suffers an operating-system-level crash". `on` "ensures the transaction will not be lost unless both the primary and all synchronous standbys suffer corruption of their database storage". And `remote_apply` waits until the commit "has become visible to queries on the standby(s)". That is the fix 3 for read-after-write in section 5.1.

**The default is the first row that matters.** With `synchronous_standby_names` empty, the docs say `remote_apply`, `remote_write` and `local` "all provide the same local synchronization level as on". That is the default. So `synchronous_commit = on` there means the same as `local`. A failover loses the commits in the replication lag. The docs, section 26.2.8: "The amount of data loss is proportional to the replication delay at the time of failover". For the running case, 1 MiB of WAL at 10 MiB/s is about 0.1 seconds of commits.

**What the stronger levels cost: latency.** A physical WAL sender sends only WAL the primary has flushed. The comment in `walsender.c`, lines 3240 to 3249 at REL_17_11, gives the reason: "it's unsafe to send WAL that is not securely down to disk on the primary". So a synchronous commit pays the local flush, then a round trip, then the standby's step. The docs give the floor: "The minimum wait time is the round-trip time between primary and standby". The wait column above uses example inputs. The local flush is 1 ms, the round trip 1 ms, the standby flush 1 ms and replay 0.5 ms. With a standby in another region, at a 70 ms round trip, `on` waits 72 ms per commit. That is `commit_levels.py --rtt-ms 70`.

The docs, section 26.2.8.3, name the second cost: "transaction locks continue to be held until the transfer is confirmed". So a hot row that each commit updates stays locked for the round trip too. Its update rate then falls as the commit time grows. That is inferred from the quote and was not measured. Some commits do not wait at all. "Read-only transactions and transaction rollbacks need not wait." Subtransaction commits do not wait. Both steps of a two-phase commit do. Verified from the docs, section 26.2.8.

**Choose per transaction.** The level "can be changed at any time", and the setting at commit time decides. The docs' example is a workload where 10% of changes are customer details and 90% are chat messages. Only the 10% needs to wait. In SQL:

```sql
BEGIN;
SET LOCAL synchronous_commit = remote_apply;   -- this payment must be readable on the replica
UPDATE orders SET state = 'paid' WHERE id = 42;
COMMIT;
```

`SET LOCAL` ends with the transaction. So it is inferred to be safe behind PgBouncer in transaction mode. Section 5.7 gives the details. The reverse, `SET LOCAL synchronous_commit = off` for a low-value job, is rule 1 of Phase 1, section 1.6.

**What the stronger levels cost: availability.** A commit that waits for a standby waits for as long as it takes. The docs, section 26.2.8.4: "Such transaction commits may never be completed if any one of the synchronous standbys should crash." So name more standbys than you wait for. `FIRST 1 (s1, s2)` waits for s1, and s2 takes over when s1 is gone. `ANY 2 (s1, s2, s3)` waits for any two. The model checks both rules:

```text
synchronous_standby_names = 'FIRST 1 (s1, s2)', down: ['s1', 's2']
commits that wait for a standby BLOCK until enough standbys return.
a client that cancels the wait gets:
  WARNING:  canceling wait for synchronous replication due to user request
  DETAIL:  The transaction has already committed locally, but might not have been replicated to the standby.
```

That is `commit_levels.py --standbys "FIRST 1 (s1, s2)" --down s1,s2`, run on 2026-10-20. The warning text is from `syncrep.c` lines 320 to 322 at REL_17_11. While a session waits, `pg_stat_activity` shows `wait_event_type` IPC and `wait_event` SyncRep. Verified from `wait_event_names.txt` line 156 at REL_17_11.

**A canceled wait leaves a visible commit.** Read the DETAIL line again. The commit is already in the primary's WAL and visible to other sessions. Only the standby may lack it. Patroni's docs on replication modes say: "it is still possible to lose transactions even when using synchronous_mode_strict". The reason: when the backend is cancelled while it waits, "transaction changes become visible for other backends". A failover at that moment loses a commit that others have already read. A statement timeout or a driver timeout that cancels the wait is inferred to give the same warning, since both raise a cancel. That was not run. The docs add one more case. "If primary restarts while commits are waiting for acknowledgment, those waiting transactions will be marked fully committed once the primary database recovers."

**On managed PostgreSQL.** Each service gives a different sentence. All three are verified from the AWS pages, fetched 2026-10-20:

| Service | What the commit waits for | Readable standby | Source |
|---|---|---|---|
| RDS Multi-AZ DB instance | a "synchronous standby replica in a different Availability Zone" | no | Multi-AZ DB instance page |
| RDS Multi-AZ DB cluster | "acknowledgment from at least one reader DB instance", not its replay | yes, two readers | Multi-AZ DB cluster page |
| Aurora | the write to "six storage nodes" across three zones, not a replica | yes, up to 15 | Aurora high availability and replication pages |

The Multi-AZ DB instance page also warns of "increased write and commit latency compared to a Single-AZ deployment". The cluster form waits for a reader to receive the change, not to apply it. So a read on that reader right after the commit can still miss it, as in section 5.1. Phase 3 has the Jepsen and AWS posts on what its readers show.

**The boundary sentence, with standbys.** Here is one for the running case after this section. "With `synchronous_commit = on` and `synchronous_standby_names = 'FIRST 1 (s1, s2)'`, an OK means the commit record is on the primary's disk and on one standby's disk. A failover to that standby loses nothing. If both standbys are down, commits wait. A commit whose wait is canceled may be visible and still lost."

**The sentence to remember:** with no synchronous standby named, every level except `off` waits only for the flush on the primary. A failover then loses the replication lag. A synchronous level adds at least one round trip per commit and blocks writes when too few standbys answer.

**The trap:** setting `synchronous_commit = remote_apply` and believing replicas now show every commit, while `synchronous_standby_names` is empty. Nothing waits. The second trap is a client timeout shorter than the standby round trip. It cancels the wait and leaves a visible commit that a failover can lose.

**Try this now:** run `uv run python phase05_replication/commit_levels.py --no-sync-standby` and compare it with the default run. Then on any server you own: `psql -c "SHOW synchronous_standby_names" -c "SHOW synchronous_commit"`. Write the boundary sentence for that server.

---

## 5.5 — Failover (detection, choosing the replica, promotion and timelines, fencing the old primary, and failover slots in PostgreSQL 17)

Why this matters: at 15:10 the primary's host died, and writes stopped for 90 seconds. Then the standby took over. In those 90 seconds a program decided the primary was dead, chose a replica, promoted it and moved the clients. Each step has a default that you can read, a failure you can predict, and a log line that shows it happened. The Redis course, Phase 4, section 4.3, "Failover", taught the same steps for Redis. This section gives the PostgreSQL facts.

**The mental model.** PostgreSQL does only one step itself: promotion. The docs, section 26.3, say it "does not provide the system software required to identify a failure on the primary and notify the standby database server". A failover manager does the rest. Patroni is common on self-hosted clusters. RDS and Aurora have their own. All of them run the same five steps:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Failover, step by step. Patroni 4.1.5 defaults. Times are from the docs  │
├──────────────────────────────────────────────────────────────────────────┤
│ 1. detect     the leader lock is not renewed for ttl = 30 s              │
│               → race starts 20 to 30 s after the primary is lost         │
│ 2. choose     the most advanced replica within                           │
│               maximum_lag_on_failover = 1,048,576 bytes                  │
│ 3. fence      the old primary must stop taking writes. Patroni demotes   │
│               a leader that cannot renew its lock                        │
│ 4. promote    pg_promote(): recovery ends, timeline 1 → 2                │
│ 5. redirect   clients reconnect: DNS, a proxy, or PgBouncer config       │
├──────────────────────────────────────────────────────────────────────────┤
│ writes fail from the loss until step 5. The WAL the new primary never    │
│ received is lost: about 1 MiB or more with these defaults. Check 4 asks  │
│ why it can be more                                                       │
└──────────────────────────────────────────────────────────────────────────┘
```

**Step 1, detection.** Patroni keeps a leader lock in a distributed configuration store, DCS for short. Fly.io, below, uses Kubernetes as its DCS. The primary must renew the lock before its time-to-live runs out. Patroni's defaults are `ttl` 30, `loop_wait` 10 and `retry_timeout` 10 seconds, from `patroni/config.py` line 90 at v4.1.5. The docs call `ttl` "the length of time before initiation of the automatic failover process". They also give a rule the three must keep: "loop_wait + 2 * retry_timeout <= ttl". There is a slower case. If PostgreSQL crashes but Patroni keeps running, Patroni first tries to restart PostgreSQL on the same host. The docs give the worst case as "loop_wait + primary_start_timeout + loop_wait", and `primary_start_timeout` defaults to 300 seconds. `failover.py --detection` prints both cases, with the managed services as AWS documents them:

```text
Patroni ttl 30, loop_wait 10, retry_timeout 10, primary_start_timeout 300
  primary host or network lost         promotion starts 20 to 30 s after the failure
  PostgreSQL crashed, Patroni alive    promotion starts 300 to 320 s after the failure
managed services, failover time as AWS documents it:
  RDS Multi-AZ DB instance                     typically 60-120 seconds
  RDS Multi-AZ DB cluster                      typically under 35 seconds
  Aurora, with an Aurora Replica               typically less than 60 seconds, often less than 30
  Aurora, no replica: a new primary is created typically less than 10 minutes
```

From a run on 2026-10-20. The Patroni upper bounds are the docs' formulas. The lower bounds are inferred from the same rules. The AWS lines are quoted from the RDS failover pages and the Aurora high availability page, fetched 2026-10-20. The RDS page adds that "large transactions or a lengthy recovery process can increase failover time".

**Step 2, choosing the replica.** The safest candidate is the one with the most WAL. Patroni also refuses a replica that is too far behind. A replica joins the race only if its lag is at most `maximum_lag_on_failover`. The default, 1048576 bytes, is in `patroni/global_config.py` line 171 at v4.1.5. The docs warn: "When using asynchronous replication a failover can cause lost transactions." The model:

```text
  r1: 0/4F00000, 1,048,576 bytes behind
  r2: 0/4000000, 16,777,216 bytes behind
promote r1. WAL lost: 1,048,576 bytes. New timeline 2, history file 00000002.history, first WAL file 000000020000000000000004
old primary needs pg_rewind or a new base backup: True
```

That is `failover.py --primary 0/5000000 --replica r1=0/4F00000 --replica r2=0/4000000`, run on 2026-10-20. With r2 alone, the script prints that no replica may be promoted. Writes then stay down until the primary returns or an operator decides to lose 16 MiB of commits. That is the choice between availability and data, made by one setting. Patroni's `synchronous_mode` promotes only a replica known to be synchronous. Its docs add two limits. When no synchronous standby is available, the primary still accepts writes without one, unless `synchronous_mode_strict` is on. And a canceled wait can still lose a commit, as section 5.4 showed. Verified from Patroni's replication modes page, fetched 2026-10-20.

**Step 3, fencing.** Two primaries at once is split brain. Each takes writes the other lacks. The docs, section 26.3, call the fence STONITH, "Shoot The Other Node In The Head". They say it is "necessary to avoid situations where both systems think they are the primary, which will lead to confusion and ultimately data loss". Patroni fences from the inside: a leader that cannot renew its lock demotes itself. `retry_timeout` is the grace: "DCS or network issues shorter than this will not cause Patroni to demote the leader."

That fence has its own failure. Fly.io's infra log of 2026-06-11 reports packet loss on transit into its ORD region. Some nodes were "unable to reliably reach Patroni's DCS". That "triggered leadership churn", with "primaries demoting / failovers". Verified from the log entry, fetched 2026-10-20. So a network that is bad but not dead can cause failovers by itself. Heroku's review of its incident of 2025-10-20 reports the same pattern in its automation. It lists "False positive or delayed Postgres, Key-Value Store, and Kafka database health alerts". Then: "Before autoremediation was manually disabled, a small subset of customer databases began autofailover and replacement." Verified from the review, fetched 2026-10-20.

Phase 1, section 1.7, told the GitHub case of 2018-10-21. After a 43-second network cut, Orchestrator, GitHub's failover manager for MySQL, promoted primaries in another region, and both sides then held writes the other lacked. GitHub's fix was to "prevent the promotion of database primaries across regional boundaries". Verified from GitHub's post. `failover.py --split-brain` gives the size of the problem with example numbers. At 50 writes per second and 19 seconds before the old primary is fenced, 950 writes exist only on the old side.

**Step 4, promotion and the new timeline.** Promotion is `pg_ctl promote` or `SELECT pg_promote()`. The function waits by default, `wait` true and `wait_seconds` 60. Verified from the docs, section 9.28.4. The standby's log then shows these lines, from `xlogrecovery.c` line 4462, `xlog.c` lines 5907 and 5940, and `postmaster.c` line 2472 at REL_17_11:

```text
LOG:  received promote request
LOG:  selected new timeline ID: 2
LOG:  archive recovery complete
LOG:  database system is ready to accept connections
```

A timeline is a numbered branch of WAL history. The docs, section 25.3.6: "Whenever an archive recovery completes, a new timeline is created". The timeline ID is the first 8 hex digits of every WAL file name. A history file, `00000002.history`, records where timeline 2 branched off.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Timelines after a failover. LSNs are an example                          │
├──────────────────────────────────────────────────────────────────────────┤
│ timeline 1  ──────────────────────┬──────────────►  old primary kept     │
│ 0/1000000 ... 0/4F00000           │  0/4F00000 to 0/5000000              │
│                                   │  1 MiB only it has. Never replicated │
│                                   │                                      │
│                                   └──────────────►  timeline 2           │
│                                      new primary, from 0/4F00000         │
│                                      files 00000002000000000000000N      │
├──────────────────────────────────────────────────────────────────────────┤
│ the old primary cannot follow timeline 2 until its extra WAL is undone   │
└──────────────────────────────────────────────────────────────────────────┘
```

**Bringing the old primary back.** It flushed WAL past the fork point. So it cannot replay timeline 2 as it is. Either take a new base backup onto it, or use `pg_rewind`. The docs say `pg_rewind` synchronizes a cluster "after the clusters' timelines have diverged". It needs `wal_log_hints = on` or data checksums, and "Neither of these are currently on by default" in PostgreSQL 17. PostgreSQL 18 turns on checksums in `initdb` by default: `data_checksums = true` at `initdb.c` line 167, REL_18_6. The commits that only the old primary had are gone after the rewind. If you need them, copy them out of its WAL before you rewind.

**Step 5, redirect the clients.** RDS changes the DNS record of the instance to point at the standby. The failover page says "you need to re-establish any existing connections", and it recommends a JVM DNS cache of "no more than 60 seconds". Twitch, in its post of 2016, ran a PgBouncer cluster in front of the primary. "Promoting a new master is a matter of changing this cluster's configuration and restarting the PGBouncers". That gave "a brief window of failing writes". Either way, every client reconnects within a few seconds of each other. Section 5.7 shows what that does to `max_connections`.

**Failover slots, new in PostgreSQL 17.** Before 17, a logical slot lived only on the primary. After a failover the CDC connector found no slot on the new primary. It had to take a new snapshot or risk missing changes. That is inferred from the release note, which lists "Enable the failover of logical slots" as new in 17, `release-17.sgml` line 15413 at REL_17_11. Now a logical slot can follow the standby. The docs, section 47.2.3, give the setup:

1. Create the logical slot with `failover` set, or create the subscription with the `failover` option.
2. On the standby, set `sync_replication_slots = on`. It is off by default.
3. On the standby, set `primary_slot_name`, so a physical slot links the two servers.
4. On the standby, set `hot_standby_feedback = on`.
5. On the standby, put a `dbname` in `primary_conninfo`.
6. On the primary, list the standby's physical slot in `synchronized_standby_slots`.

Step 6 stops the CDC reader from getting changes the standby does not have yet. The docs say that logical WAL senders "will send decoded changes to plugins only after the specified replication slots confirm receiving WAL". It costs some latency for CDC, and the docs warn that "logical replication will not proceed if the slots specified in the synchronized_standby_slots do not exist or are invalidated". So a dead standby in that list also stops CDC.

Before you switch over, check the slot on the standby. The docs: "Only persistent slots that have attained synced state as true on the standby before failover can be used for logical replication after failover". If the standby could not sync a slot, its log shows a line such as `could not synchronize replication slot "failover_slot"`. Its DETAIL names the LSN and catalog xmin the slot needs. The standby logs this line at LOG level only while its copy of the slot is still temporary. For a persistent slot the line is DEBUG1, so it does not appear with the default log settings. Verified from `slotsync.c` at REL_17_11, lines 220 to 228. So read `synced` and `temporary` in `pg_replication_slots` on the standby, and do not wait for a log line. Patroni has its own older form, "permanent slots". Its docs warn that after a failover "some messages could be received the second time", so the consumer must handle duplicates.

**The sentence to remember:** failover is detect, choose, fence, promote and redirect. PostgreSQL does only the promotion. With asynchronous replication, what the chosen replica lacked is lost. The old primary must be fenced, and rewound or rebuilt, before it rejoins.

**The trap:** trusting the 30-second `ttl` as your failover time, when a PostgreSQL crash under a live Patroni can take up to 320 seconds. The second trap is a CDC slot that does not exist on the new primary. Use the PostgreSQL 17 failover slots, and check `synced` before a planned switchover.

**Try this now:** run `uv run python phase05_replication/failover.py --detection --primary-start-timeout 0`. Then, for each database you run, write down its failover manager and its detection time from that manager's documentation.

---

## 5.6 — Backups and point-in-time recovery (base backups, the WAL archive, choosing the target, PostgreSQL 17 incremental backup, and restore testing)

Why this matters: at 16:40 a migration emptied a table, and the question was whether the team could restore to 16:39. Replicas cannot help. They replayed the same statement within a second. Only a backup and a continuous WAL archive can, and only if the restore procedure has been run before. Three published incidents in this section, at Linear, Resend and Instapaper, show what happens when it has not been run.

**Three kinds of backup, and what each can restore.**

| Kind | How it is made | Restores to | Restore work |
|---|---|---|---|
| logical dump | `pg_dump`, SQL or custom format | the moment the dump started | replay every row and rebuild every index |
| file-system snapshot | a storage snapshot of the data directory | the moment of the snapshot | copy back, then crash recovery |
| base backup + WAL archive | `pg_basebackup` plus `archive_command` | any moment after the backup ended | copy back, then replay WAL to the target |

Verified from the docs, sections 25.1, 25.2 and 25.3. Only the third one is point-in-time recovery, PITR for short. The docs, section 25.3, say it plainly: "pg_dump and pg_dumpall do not produce file-system-level backups and cannot be used as part of a continuous-archiving solution. Such dumps are logical and do not contain enough information to be used by WAL replay."

A dump has a second cost: restore time. Instapaper's outage of 2017-02-09, on MySQL in RDS, shows it. Its 2.5 TB database had to be dumped and restored. The postmortem says the dump took 24 hours, then 10 hours with parallel work. The estimate had been six to eight hours, made "using the number of rows". It was wrong because "the first 25 percent of Instapaper bookmarks account for only 10 percent of overall data". After the import, each of three secondary indexes took about 16 hours. All 10 days of its backups were file-system snapshots with the same 2 TB file limit as the broken database. Verified from the archived postmortem. The engine was MySQL, but the work of a logical restore is the same in PostgreSQL. The GitLab case of 2017 adds a quieter failure. Its daily `pg_dump` used version 9.2 against a 9.6 server, so it failed, and the S3 bucket "was empty". Verified from GitLab's postmortem.

**The mechanism: one copy of the files, then every WAL record since.** The docs, section 25.3: "we can combine a file-system-level backup with backup of the WAL files. If recovery is needed, we restore the file system backup and then replay from the backed-up WAL files to bring the system to a current state". The replay can stop early, at any moment you name. That is the point in point-in-time.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ What a point-in-time restore uses. Times are an example                  │
├──────────────────────────────────────────────────────────────────────────┤
│ 02:00 ─ 02:40   base backup runs. Not a valid target                     │
│ 02:40           backup ends. Its backup history file is in the archive   │
│                                                                          │
│ archive  seg 0A │ 0B │ 0C │ ... │ 7E │ 7F │      every segment, no gap   │
│          ──────────────────────────────────────────►  replay             │
│                                       ▲            ▲                     │
│                               16:39:00 target      16:40 bad migration   │
├──────────────────────────────────────────────────────────────────────────┤
│ needed: a backup that ENDED before the target, and every segment from    │
│ its start to the target. A missing segment ends the replay there         │
└──────────────────────────────────────────────────────────────────────────┘
```

**The archive.** Set `archive_mode = on` and an `archive_command`, or an archive library. The docs, section 25.3.1, give the rule the command must keep: "It is important that the archive command return zero exit status if and only if it succeeds". On zero, PostgreSQL "will assume that the file has been successfully archived, and will remove or recycle it". A command that returns zero after a failed copy loses that segment, and every restore past it. The docs' example is `test ! -f /mnt/server/archivedir/%f && cp %p /mnt/server/archivedir/%f`, with the warning that it is "an example, not a recommendation". `cp` does not flush the copy to disk, so a crash of the archive host can lose a segment that was reported as archived. That is inferred from what `cp` does. Real systems use a tool built for the job, such as pgBackRest, WAL-G or Barman, or the managed service.

A command that fails keeps the segment in `pg_wal`, and section 5.2 showed where that leads. Watch `pg_stat_archiver`: `failed_count`, `last_failed_wal` and `last_archived_time`. The docs warn of one blind spot. If the command is killed by a signal or returns an exit status above 125, "the archiver process aborts and gets restarted by the postmaster. In such cases, the failure is not reported in pg_stat_archiver." So also alert when `last_archived_time` is older than a few segments' worth of time.

**How much an archive can lose.** The archive gets a segment only when it is full. A quiet server can take a long time to fill 16 MB. `archive_timeout` forces a switch. The docs: "archive_timeout settings of a minute or so are usually reasonable". A very short one bloats the archive, because "archived files that are closed early due to a forced switch are still the same length as completely full files". So the archive can lose up to one segment of time. On a quiet server that is `archive_timeout`. On a busy one it is the time to fill 16 MB. RDS states its own number. The PITR page says "RDS uploads transaction logs for DB instances to Amazon S3 every five minutes", and `LatestRestorableTime` shows the newest moment you can restore to. Verified from the AWS page, fetched 2026-10-20. Netflix's 64 MB oscillation in section 5.1 was this switch, every 300 seconds.

**The base backup.** `pg_basebackup` copies the data directory from a running server. `-X stream` "is the default". With it, the tool "will open a second connection to the server and start streaming the write-ahead log in parallel". So the backup carries the WAL it needs to be consistent. It writes a `backup_manifest` with a checksum of every file. `pg_verifybackup` checks a backup against it. The archive also gets a backup history file named after the first segment the backup needs, such as `0000000100001234000055CD.007C9330.backup`. Verified from the docs, sections 25.3.2 and the `pg_basebackup` page.

**The restore, in order.** These steps follow the docs, section 25.3.5:

1. Stop the server. If you can, copy its data directory aside, or at least its `pg_wal`. It may hold segments that never reached the archive.
2. Restore the base backup into an empty data directory, owned by the database user.
3. Remove the files in `pg_wal` that came from the backup.
4. Copy into `pg_wal` the unarchived segments you saved in step 1. Recovery uses them before the archive.
5. Set `restore_command`, and a recovery target such as `recovery_target_time`.
6. Create the file `recovery.signal` in the data directory.
7. Do not let users connect yet. Change `pg_hba.conf`, or use another port.
8. Start the server. Recovery reads the archive. The docs say a normal recovery ends with a "file not found" message. That is expected.
9. Check the data before you promote.

Two rules decide whether the target works. The docs, 25.3.5: "You cannot use a base backup to recover to a time when that backup was in progress". And the docs, 19.5.6, say `recovery_target_time` takes a time stamp "except that you cannot use a time zone abbreviation". Write it with a numeric offset from UTC.

**WRONG: a target with a zone abbreviation.**

```bash
uv run python phase05_replication/pitr.py --target "2024-01-24 07:00:59 EST" --demo linear
```

```text
  REFUSED: time zone abbreviation 'EST' is not allowed. Use a numeric offset such as +00
```

**RIGHT: a numeric offset, before the bad statement.**

```bash
uv run python phase05_replication/pitr.py --target "2024-01-24 07:00:59+00" --demo linear
```

```text
Linear, 2024-01-24, UTC: full backup 04:47, bad migration 07:01, maintenance 09:56
  restore the full backup: changes lost from 04:47 to 09:56 = 5:09:00
  point-in-time to just before 07:01: changes lost from 07:01 to 09:56 = 2:55:00, to be replayed by the application
  base backup: daily
  restore_command = 'cp /tmp/storage_lab_p5/archive/%f %p'
  recovery_target_time = '2024-01-24 07:00:59+00'
  recovery_target_action = 'pause'   # the default: inspect, then pg_wal_replay_resume()
  # then: touch $PGDATA/recovery.signal, and start the server
```

Both from runs on 2026-10-20. The script refuses the abbreviation for the docs' reason. The real server would read it only if `timezone_abbreviations` was set earlier in the file. The output also shows a default. `recovery_target_action` is `pause`, so the server stops at the target and waits for `pg_wal_replay_resume()`. The docs, 19.5.6, explain why: "to allow queries to be executed against the database to check if this recovery target is the most desirable point for recovery". If `hot_standby` is off, pause acts like shutdown. Before a risky migration, run `SELECT pg_create_restore_point('before_migration_42')`. Then the target can be `recovery_target_name`, and you do not need a time at all. Verified from the docs, section 9.28.3.

**The Linear case.** Linear's postmortem of the incident of 2024-01-24 is the source of the times above. A migration ran `TRUNCATE ... CASCADE`, and CASCADE emptied every table with a foreign key to the new one. Linear "takes daily full backups in addition to having point-in-time recovery". But "the engineering team had never tested point-in-time recovery, nor had engineering developed tooling to quickly restore the database using point-in-time recovery, so that option wasn't considered". They restored the 04:47 full backup and rebuilt the lost changes from their sync log. Over 99% were back within 36 hours. Verified from the postmortem, fetched 2026-10-20. The arithmetic in `pitr.py` shows what the untested option would have saved. The team would have rebuilt 2 hours 55 minutes of changes instead of 5 hours 9 minutes.

**The Resend case.** Resend's report of 2024-02-21 says a migration run locally pointed at production and dropped all tables. The first restore "took 6 hours but failed due to a wrong selection of the backup timestamp". The second, from an older backup, took 5 more hours. The service was down from 05:01 to 17:05 UTC, about 12 hours, and data from 04:50:00 to 04:56:27 was lost. One of its follow-ups: "Increase cadence for disaster recovery tests." Verified from the report, fetched 2026-10-20. The report does not name its database engine. The lesson does not depend on it: a target is a fact you must check before a long restore, not after.

A completed point-in-time restore starts a new timeline, as section 5.5 showed for promotion. So the restored server never overwrites the WAL of the history you left. You can restore again to a later moment of the old timeline.

**Incremental backup, new in PostgreSQL 17.** A full base backup of a large database is slow and large. PostgreSQL 17 can back up only the blocks that changed since an earlier backup. The steps:

1. Set `summarize_wal = on`. It is off by default. The WAL summarizer then writes summaries to `pg_wal/summaries` and keeps them for `wal_summary_keep_time`, 10 days by default. Verified from `guc_tables.c` at REL_17_11.
2. Take a full backup as usual.
3. Later, run `pg_basebackup --incremental=<full>/backup_manifest`. The docs, 25.3.3: without the summaries, "an attempt to take an incremental backup will fail".
4. To restore, run `pg_combinebackup -o <target> <full> <inc1> <inc2>`, from oldest to newest. Then recover as above.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ An incremental chain. pg_combinebackup needs every link                  │
├──────────────────────────────────────────────────────────────────────────┤
│ Sun full ──► Mon incremental ──► Tue incremental                         │
│    ▲               ▲                    ▲                                │
│ all blocks    blocks changed       blocks changed                        │
│               since Sun            since Mon                             │
│                                                                          │
│ a retention job deletes Mon:  Tue cannot be restored                     │
│ "cannot restore inc-tue: inc-tue needs inc-mon, which is not kept"       │
└──────────────────────────────────────────────────────────────────────────┘
```

The last line is the output of `pitr.py --demo chain`, run on 2026-10-20. PostgreSQL does not track the chain for you. The docs, 25.3.3: "You must keep track of the relationships between your full and incremental backups on your own". And `pg_combinebackup` checks only that the backups fit together, "not that each individual backup is intact; for that, use pg_verifybackup". The docs also say incremental backups make sense "for relatively large databases where a significant portion of the data does not change". For a small database, take full backups.

The feature is young, and two of its bugs were fixed in minor releases. Release 17.8 fixed incremental backups of a table over 1 GB that VACUUM had truncated, which `pg_combinebackup` could not restore. Release 17.11, of 2026-08-13, fixed visibility-map changes that "were missed by the WAL summarizer, potentially leading to incorrect incremental backups". Verified from `release-17.sgml` lines 5246 to 5257 and 1954 to 1966 at REL_17_11. So run the newest 17 minor if you use it, and restore-test the chain, not only the full backup.

**Restore time is the number nobody measures.** Here is the arithmetic, with example rates. Copying a 2.5 TiB base at 200 MiB/s and replaying 300 GiB of WAL at 60 MiB/s:

```text
copy the base: 3.6 h. replay the WAL: 1.4 h. total 5.1 h, before any check that the data is right. Example rates, not measured.
```

That is `pitr.py --restore-hours --base-gb 2560 --restore-mbps 200 --wal-gb 300 --replay-mbps 60`. The replay part grows with the time since the base backup. The docs, 25.3.2, name the trade: the interval between base backups sets how much WAL to keep, and "the system will have to replay all those WAL segments". GitHub's report of 2018 adds a real number of the same kind. Its MySQL backups ran every four hours, and restoring "multiple terabytes" took hours. The time went to the transfer from remote storage and to decompressing, checking and loading the files. Verified from GitHub's post. Measure your own numbers in a drill. Then compare them with how long the business can be down.

**On managed PostgreSQL.** RDS takes a daily snapshot and ships logs every five minutes. The PITR page says a restore means "creating a new DB instance without modifying the source DB instance". The read replica page adds: "Point-in-time recovery (PITR) isn't supported for read replicas". So the restored database has a new endpoint, and every client and pooler must be pointed at it. Aurora backups "are continuous and incremental", the retention is 1 to 35 days, the default is one day, and "You can't disable automated backups on Aurora". All verified from the AWS pages, fetched 2026-10-20. A one-day default means an error found on day two cannot be undone from the automated backups.

**The sentence to remember:** only a base backup plus an unbroken WAL archive gives point-in-time recovery. The target must be after the backup ended, before the bad statement, and written with a numeric offset. A backup is proven only by a restore you have timed.

**The trap:** believing that a replica, a nightly `pg_dump` or an untested PITR setting is a backup plan. Linear had PITR and did not use it, because nobody had ever run it. The second trap is an incremental chain whose middle link a retention job deleted.

**Try this now:** run `uv run python phase05_replication/pitr.py --demo gap` and then `--demo chain`. Then, for one database you own, write down three numbers. They are the newest restorable time right now, the restore time you last measured, and the date of that drill.

---

## 5.7 — Connection pooling (a process per connection, PgBouncer modes and what transaction mode breaks, prepared statements, RDS Proxy pinning, and the connection budget)

Why this matters: at 15:12, two minutes after the failover, every pool reconnected at once and the new primary refused new connections. The database was healthy. The pools that can reach it added up to more than its connection slots. Among the production reports in this phase, this is the most common outage. Railway, Buttondown and OpenAI each report an outage of this kind. Notion found the same limit in a test before its re-shard. It is also the easiest one to prevent, with arithmetic you can do before the incident.

**The mental model.** PostgreSQL "implements a process per user client/server model". Every client "connects to exactly one backend process", and the postmaster "spawns a new backend process every time a connection is requested". Verified from the docs, section 50.2. So a connection is a whole operating-system process. `max_connections` caps them, 100 by default, and the docs add that the server "sizes certain resources based directly on the value of max_connections", shared memory among them. A pooler keeps a small set of server connections open and lends them to many clients.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The connection path of the running case                                  │
├──────────────────────────────────────────────────────────────────────────┤
│ 40 app processes      ORM pool      PgBouncer           PostgreSQL       │
│ ┌──────────┐  10 each ┌────────┐    ┌───────────┐ 40  ┌───────────────┐  │
│ │ api, jobs├─────────►│ client ├───►│ 400 client├────►│ 40 backends   │  │
│ │ agents   │          │ conns  │    │ conns     │     │ of 97 normal  │  │
│ └──────────┘          └────────┘    └───────────┘     │ slots         │  │
│                                     pool_size 40      └───────────────┘  │
├──────────────────────────────────────────────────────────────────────────┤
│ without the pooler: 400 backends wanted, 97 normal slots. 303 refused    │
└──────────────────────────────────────────────────────────────────────────┘
```

The diagram is the path as planned. The budget below lists three ways the real total grows past the slots.

**The slots, exactly.** Not all of `max_connections` is for your application. The last ones are reserved. `superuser_reserved_connections`, default 3, is for superusers. `reserved_connections`, new in PostgreSQL 16 and 0 by default, is for roles with the privileges of `pg_use_reserved_connections`. Verified from `guc_tables.c` at REL_17_11, the docs, section 19.3.1, and the PostgreSQL 16 release notes. WAL senders do not use these slots. `MaxBackends` adds `max_wal_senders` on top, at `postinit.c` lines 582 and 583. So with defaults, a normal role has 97 slots.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ max_connections = 100, reserved_connections = 5. Example                 │
├──────────────────────────────────────────────────────────────────────────┤
│ slots  1 .. 92  ████████████████████████████████████████  any role       │
│ slots 93 .. 97  ██                     pg_use_reserved_connections roles │
│ slots 98 .. 100 █                                          superusers    │
├──────────────────────────────────────────────────────────────────────────┤
│ the error a normal role gets depends on how many slots are free:         │
│   ≤ 8 free  "remaining connection slots are reserved for roles with      │
│              privileges of the "pg_use_reserved_connections" role"       │
│   ≤ 3 free  "... reserved for roles with the SUPERUSER attribute"        │
│   0 free    "sorry, too many clients already"                            │
└──────────────────────────────────────────────────────────────────────────┘
```

The messages are from `postinit.c` lines 962 and 968 and `proc.c` line 357 at REL_17_11. All three carry SQLSTATE 53300, `too_many_connections`. The thresholds are the docs' rule for `reserved_connections` in 19.3.1. Give `pg_use_reserved_connections` to the role your operators use, and never to the application's or the pooler's role. Then a connection storm cannot lock the operators out. That rule is inferred from the docs' description and the two incidents below.

**Two incidents of the same shape.** Railway's report of 2025-10-28 starts with a `CREATE INDEX` without `CONCURRENTLY`. It ran on a table of about a billion rows and held a lock for about 30 minutes. Requests queued and each one held a connection. Then "our PgBouncer configuration exceeded the underlying Postgres connection limit, exhausting all available connection slots including administrative ones". The engineers' attempts to stop the index build failed with `FATAL: remaining connection slots are reserved for roles with privileges of the "pg_use_reserved_connections" role`. The fixes: CI enforces `CONCURRENTLY`, pool limits below the database limit, and per-user limits "to guarantee administrative access". Verified from the report, fetched 2026-10-20. Phase 4, section 4.7, covers the lock half of this case. The error text says the free slots were the reserved ones and the engineers' role did not have the privilege. That reading is inferred.

Buttondown's postmortem of its incident of 2026-03-31 tells a smaller version. Two outages of about 7 and 13 minutes came from one cause: "we hit the ceiling on the number of connections our database was configured to accept". The health check mostly passed, because its requests "happened to land on workers that already held open connections". In the second outage "we couldn't even connect to the database to kill queries", so they restarted the database. The first of their five fixes is reserved administrative connections, and the second is an alert on "connection count as a percentage of the configured maximum". Verified from the postmortem, fetched 2026-10-20.

**The budget, before the incident.** Add up every pool that can open a server connection, and compare the total with the normal slots. `pool_model.py --budget` does it.

**WRONG: every process opens its own pool against the database.**

```text
40 app instances x pool 10, direct = 400 server connections
slots for normal roles: 100 - 3 superuser - 0 reserved - 0 planned = 97
OVER by 303: new connections fail with SQLSTATE 53300 when the pool fills
```

**RIGHT: the pools talk to PgBouncer, and PgBouncer's pools fit the slots.**

```text
2 PgBouncer x 1 pool(s) x (40 + 0 reserve) = 80 server connections
slots for normal roles: 100 - 3 superuser - 0 reserved - 0 planned = 97
within budget, spare 17
```

Both from runs on 2026-10-20, with `--app-instances 40 --app-pool 10`, the second with `--via-pgbouncer 2 --pool-size 40`. Three things change the real total. A deploy that runs old and new processes side by side doubles the client side. Every distinct database and user pair is its own PgBouncer pool, with up to `default_pool_size` connections, 20 by default. And `max_db_connections`, 0 by default, means unlimited, so nothing in PgBouncer caps the sum unless you set it. Verified from the PgBouncer configuration page, fetched 2026-10-20.

**How many server connections you need.** Little's law gives it. elite-performance, Phase 5B, section 5.5, taught it for client pools. Busy connections equal transactions per second times the seconds each one holds its connection. At 2,000 transactions per second and 5 ms each, `pool_model.py --busy` prints 10. Now hold the transaction open across a 200 ms call to a model API or another service. At 205 ms per transaction it prints 410. The pooler can lend a connection only between transactions. So an agent step that opens a transaction, calls an LLM and then commits needs 41 times the connections. Commit before the call. Phase 3, section 3.6, gave the same rule for locks.

**PgBouncer's three modes.** The PgBouncer features page:

- **Session pooling**, the default: "a server connection will be assigned to it for the whole duration it stays connected". It supports all PostgreSQL features and saves only the connect cost.
- **Transaction pooling**: "A server connection is assigned to a client only during a transaction." This is the mode that makes 400 clients fit in 40 backends.
- **Statement pooling**: transaction pooling where "Multi-statement transactions are disallowed".

Verified from the page, fetched 2026-10-20. OpenAI runs PgBouncer "in statement or transaction pooling mode". Its post of 2026-01-22 says this cut the average connection time "from 50 milliseconds (ms) to 5 ms" in their benchmarks, against Azure's limit of 5,000 connections per instance. Verified from the archived copy of the post.

**What transaction mode breaks.** Each transaction may run on a different server connection. So anything that lives in the session, not in the transaction, goes wrong. The features table marks these "Never" for transaction pooling: `SET`/`RESET`, `LISTEN`, `WITH HOLD` cursors, SQL `PREPARE`/`DEALLOCATE`, temporary tables with `PRESERVE` or `DELETE ROWS`, `LOAD`, and session-level advisory locks. A note to the table names six startup parameters that PgBouncer tracks itself, such as `TimeZone` and `application_name`. A `SET` of one of those is safe. `pool_model.py --lint` checks statements against that table and against the RDS Proxy list below:

```text
BREAKS pgbouncer-txn PINS rds-proxy  SET statement_timeout = '5s'                                SET or RESET
ok pgbouncer-txn     ?? rds-proxy    SET LOCAL statement_timeout = '5s'                          SET LOCAL: inferred safe in PgBouncer: it ends with the transaction. RDS Proxy: not checked
BREAKS pgbouncer-txn PINS rds-proxy  SELECT pg_advisory_lock(42)                                 session advisory lock
ok pgbouncer-txn     ok rds-proxy    SELECT pg_advisory_xact_lock(42)                            transaction advisory lock: RDS Proxy does not pin on these. Phase 3, section 3.6, uses this form
BREAKS pgbouncer-txn PINS rds-proxy  LISTEN task_ready                                           LISTEN
```

The first five of eleven lines of `pool_model.py --lint phase05_replication/sample_session.sql`, run on 2026-10-20. The worst failure is silent. A `SET statement_timeout` sent by one client stays on that server connection, and the next client that gets it inherits the timeout. PgBouncer does not run `server_reset_query` in transaction mode. Its docs explain that clients there "must not use any session-based features". The setting `server_reset_query_always` exists for broken setups. It "changes non-deterministic breakage to deterministic breakage". Verified from the PgBouncer configuration page. Put per-request settings in `SET LOCAL` inside the transaction, or in the role with `ALTER ROLE ... SET`. A worker that waits with `LISTEN` needs its own direct connection, or a session-mode pool.

**Prepared statements behind the pooler.** Drivers prepare statements at the protocol level, without SQL `PREPARE`. Before PgBouncer 1.21.0, released 2023-10-16, that failed in transaction mode. Twitch's post of 2016 describes its fork of PgBouncer that held "the back-end until the parameters are provided for execution". Twitch's case was an unnamed statement from Go's `lib/pq` driver. Version 1.21.0 added "support for protocol-level named prepared statements". Whether that also covers Twitch's unnamed case is not checked. Version 1.24.0, of 2025-01-10, set `max_prepared_statements` to 200 by default. Verified from the PgBouncer changelog. Three details matter:

1. It does not cover SQL-level `PREPARE`. "PREPARE, EXECUTE and DEALLOCATE are forwarded straight to Postgres."
2. PgBouncer prepares each distinct query once per server connection, not per client. In the docs' example, "if you have a pool_size of 20 and you have 100 clients that all prepare the exact same query, then the query is prepared (and thus parsed) only 20 times".
3. After a migration that changes a column, you may see `ERROR: cached plan must not change result type`. The docs say to run `RECONNECT` on the PgBouncer admin console "to force a re-prepare".

Detail 2 is the PgBouncer side of a rule in Phase 4, section 4.2. There, the first five executions of a prepared statement got custom plans, and then a generic plan could take over. That count lives in the server's plan cache, per backend. So behind PgBouncer, each server connection counts its own five executions, whichever clients sent them. This is inferred from the plan cache being per backend and from detail 2. It was not run.

**RDS Proxy pins instead.** RDS Proxy reuses a database connection "at the conclusion of each transaction", like transaction mode. When it sees session state, it pins: "each later transaction uses the same underlying database connection until the session ends". For PostgreSQL the AWS page lists these causes:

- `SET`, and `PREPARE`, `DISCARD`, `DEALLOCATE` and `EXECUTE`
- temporary sequences, tables and views, and cursors
- `LISTEN`, and loading a module such as `auto_explain`
- `nextval` and `setval`, `pg_advisory_lock` and `pg_try_advisory_lock`

 For every engine, "Any statement with a text size greater than 16 KB causes the proxy to pin the session." It does not pin on `pg_advisory_xact_lock` and its variants. A pool library that sends `DISCARD ALL` on release pins every connection. Verified from the AWS page, fetched 2026-10-20. The page does not say whether a protocol-level prepared statement pins. That is not checked.

The difference matters. PgBouncer in transaction mode breaks session state in a way you may not notice. RDS Proxy keeps it correct, and stops multiplexing that client. A pinned proxy is a direct connection that costs more. Watch `DatabaseConnectionsCurrentlySessionPinned` and `DatabaseConnectionsBorrowLatency` in CloudWatch.

**When the pooler is the limit.** PgBouncer is one process with one thread. Twitch's post: "CPU was hitting 100% running PGBouncer as a single threaded application which causes connections to stall". They ran two processes per host behind HAProxy, a TCP load balancer. Today the PgBouncer configuration page names a simpler way: with `so_reuseport`, several PgBouncer processes listen on the same port. Notion's re-shard of 2023 hit the arithmetic of section 5.7's budget. About 100 PgBouncer instances, each with up to 6 connections per shard, made 600 per shard. Pointing three new shard entries at each old shard would make 18 per instance, 1,800 per old shard. That is `pool_model.py --notion`. They split PgBouncer into clusters instead, "4 groups, with 24 databases downstream of each PgBouncer shard". Verified from both posts, fetched 2026-10-20.

**Signals.**

- PgBouncer: `SHOW POOLS`. `cl_waiting` counts clients that "have sent queries but have not yet got a server connection". `maxwait` is how long the oldest one has waited. The docs: "If this starts increasing, then the current pool of servers does not handle requests quickly enough." `query_wait_timeout`, 120 seconds by default, disconnects a client that waits longer. So the default lets a request wait 2 minutes in the pooler. Set it below your request deadline.
- PostgreSQL: `SELECT state, count(*) FROM pg_stat_activity WHERE backend_type = 'client backend' GROUP BY 1`, against `max_connections` minus the reserved slots. A large `idle in transaction` count is a client holding transactions open.
- RDS: `DatabaseConnections`. The RDS metrics page notes that the number of database sessions "can be higher than the metric value", because the metric leaves some sessions out.

**The sentence to remember:** every server connection is a process taken from `max_connections` minus the reserved slots. Budget the sum of all pools below that number, reserve slots for operators, and keep session state out of transaction-pooled connections.

**The trap:** a set of pools whose total is above the server's slots. It works until a failover or a lock makes every client connect at once. The second trap is a session `SET` through PgBouncer transaction mode, which leaks to the next client without an error.

**Try this now:** run `uv run python phase05_replication/pool_model.py --lint phase05_replication/sample_session.sql`. Then grep your own code: `grep -rn "SET \|LISTEN\|advisory_lock\|PREPARE\|WITH HOLD" <your repo>/`. Mark each hit as safe or not for your pooler.

---

## 🧪 Hands-on lab

**Run status.** Every offline command below, E1 to E9, was executed on 2026-10-20 on the author's machine, with Python 3.12.14 from the course's `.venv`. Their "Expected" lines are the real output. The live exercises, E10 to E16, were written and reviewed but not run, by the owner's choice for this course. Each of their "Expected" lines says "Not run by the author yet." and gives the expected shape from the PostgreSQL 17 docs and source. No database server was started for this phase.

**What you build.** Eight files and one SQL sample in `phase05_replication/`. They use only the Python standard library, so `pyproject.toml` needs no new pin. `failover.py` imports `lag.py`, and `two_node.py` imports `pitr.py`. No earlier file changes.

| File | What it holds | Self-test checks |
|---|---|---|
| `lag.py` | LSN parsing, WAL file names, the four stage gaps, time lag with and without the idle check | the docs' LSN and WAL-file examples, the stage gaps, the idle false alarm with the rule removed |
| `slot_retention.py` | what a checkpoint keeps for a slot, `wal_status`, `safe_wal_size`, a failing archive | the time to full, the extended, unreserved and lost times, the cap removed |
| `hot_standby.py` | replay that waits, cancels, and feedback that holds dead rows | the cancel times, the shared grace with the rule removed, the dead rows held |
| `commit_levels.py` | the docs' table of five levels, latency, loss per failure, FIRST and ANY | the docs' bullets, the waits, blocking with the alive rule removed |
| `failover.py` | the candidate rule, detection windows, timelines, split-brain writes | Patroni's defaults, the lag rule removed, the history file name |
| `pitr.py` | the backup that ended before the target, archive gaps, the incremental chain, target text | Linear's times, the end rule removed, abbreviations, a missing link |
| `pool_model.py` | the slot budget, Little's law, the transaction-mode and pinning lint | 97 slots, Notion's 600 and 1,800, each lint rule |
| `two_node.py` | every command of the live exercises, with a safe-path guard | the setup and restore commands, the refused paths |

For each rule the text calls important, the self-test has a check that fails when the rule is removed. A mutation run on 2026-10-20 removed 16 such rules one at a time. Each removal failed its self-test. The first run missed one: `pitr.py` still refused "EST" without the abbreviation rule, because the date parser failed on it anyway. The check now requires the word "abbreviation" in the error. The review removed 17 more rules, 33 in all, and every removal failed. Its first run missed one in the same way: `pitr.py` raised `KeyError` for a missing chain link even without the rule. That check now reads the message too.

**The demonstration of this phase** is E10, E13 and E15. E10 shows a standby's positions. E13 shows a synchronous commit that blocks and a canceled wait that leaves a visible commit. E15 is a timed point-in-time restore to a moment before a bad statement.

- [ ] **E1 (offline).** Run every self-test of this phase, then those of the earlier phases.
  - Run: `for f in phase05_replication/*.py; do echo "$f"; uv run python "$f" --self-test; done`
  - Then run: `for f in shared/*.py phase0[1-4]_*/*.py; do echo "$f"; uv run python "$f" --self-test; done`
  - Expected: `self-test passed` after each of the 8 Phase 5 files, with check counts from 9 to 20. The earlier phases' scripts all passed on 2026-10-20 too. `shared/__init__.py` is empty and prints nothing.
  - If it fails: the assertion message names the rule. Compare it with the section before you change any code.
  - Teaches: each rule in the text has a check that fails without it.

- [ ] **E2 (offline).** Find the slow stage of a standby.
  - First predict which gap is largest for these positions: current `5/3A000000`, sent `5/39F00000`, write and flush `5/39E00000`, replay `5/38000000`.
  - Run: `uv run python phase05_replication/lag.py --current 5/3A000000 --sent 5/39F00000 --write 5/39E00000 --flush 5/39E00000 --replay 5/38000000 --wal-rate-mb 8`
  - Expected: four rows. `flush -> replay` is 31,457,280 bytes, about 3.75 s at 8 MiB/s, and is named the largest gap. The total is 33,554,432 bytes.
  - Then run: `uv run python phase05_replication/lag.py --walfile 0/D3DA3C8`. Expected: `file 00000001000000000000000D  offset 4039624`, the docs' own example of section 9.28.3.
  - Teaches: section 5.1, a byte gap names a stage.

- [ ] **E3 (break-it, offline).** The idle-primary false alarm.
  - Run: `uv run python phase05_replication/lag.py --idle-demo --no-idle-check`, then without the flag.
  - Expected: with the flag, the reported lag is 1.0, 10.0, 60.0 and 290.0 s while the byte lag is 0. Without it, every row is 0.0.
  - Teaches: section 5.1, check received against replayed before you trust the clock.

- [ ] **E4 (offline).** How long until a stopped CDC slot fills the disk.
  - Run: `uv run python phase05_replication/slot_retention.py --rate-mb 10 --free-gb 250`, then add `--max-slot-mb 10240`, then add `--archive-failing` as well.
  - Expected: without the cap, `pg_wal passes 250.0 GiB at t = 25,600 s (7.1 h)`. With the cap, the states are reserved at 0 s, extended at 106 s, unreserved at 1,026 s and lost at 1,200 s. pg_wal stays below 250 GiB. With a failing archive, the slot is still lost at 1,200 s, but the disk is full at 25,600 s again.
  - Then put in your own WAL rate and free space.
  - Teaches: section 5.2, the cap trades a full disk for a reader to rebuild, and does not cover the archive.

- [ ] **E5 (offline).** Cancel, wait or hold back VACUUM.
  - Run: `uv run python phase05_replication/hot_standby.py`, then `--feedback`, then `--shared-grace`, then `--max-delay 21600`.
  - Expected: default, report A canceled at t=90 s and report C at t=150 s, and replay up to 30 s behind. `--feedback`: all three finish, and the primary holds up to 199,000 dead row versions. `--shared-grace`: Y canceled at t=50 s after 35 s. `--max-delay 21600`: all finish, and replay falls up to 140 s behind.
  - Teaches: section 5.3, the three options and what each costs.

- [ ] **E6 (offline).** What OK means at each level.
  - Run: `uv run python phase05_replication/commit_levels.py`, then `--rtt-ms 70`, then `--no-sync-standby`.
  - Expected: waits of 0.00, 1.00, 2.05, 3.00 and 3.50 ms by default. At 70 ms, `remote_write` waits 71.05 ms and `on` 72.00 ms. With no synchronous standby, every level except `off` waits 1.00 ms and loses "commits in the replication lag" at failover.
  - Then run: `uv run python phase05_replication/commit_levels.py --standbys "ANY 2 (s1, s2, s3)" --down s3`. Expected: `commits wait for: s1, s2`. Add s2 to `--down`, and the commit blocks.
  - Teaches: section 5.4.

- [ ] **E7 (offline).** Which replica wins, and when.
  - Run: `uv run python phase05_replication/failover.py --primary 0/5000000 --replica r1=0/4F00000 --replica r2=0/4000000`, then with only r2, then `--detection`.
  - Expected: r1 is promoted, 1,048,576 bytes lost, timeline 2, history file `00000002.history`. With only r2, no replica is promoted. `--detection` prints 20 to 30 s and 300 to 320 s.
  - Then run with `--max-lag 20000000` and only r2. Expected: r2 is promoted, and 16,777,216 bytes are lost.
  - Teaches: section 5.5, one setting chooses between availability and data.

- [ ] **E8 (break-it, offline).** A restore target that brings the bug back.
  - Run: `uv run python phase05_replication/pitr.py --target "2024-01-24 07:05:00+00" --demo linear`.
  - Expected: the line `WRONG TARGET: it is at or after the bad migration, so the restore contains it`, and settings that would restore the empty tables.
  - Then run `--demo gap` and `--demo chain`. Expected: replay reaches only `2026-10-20 03:59:59+00:00`, and `cannot restore inc-tue: inc-tue needs inc-mon, which is not kept`.
  - Teaches: section 5.6, three ways a restore fails that a test drill finds.

- [ ] **E9 (offline).** The connection budget.
  - Run: `uv run python phase05_replication/pool_model.py --budget --app-instances 40 --app-pool 10`, then add `--via-pgbouncer 2 --pool-size 40`, then `--busy --tps 2000 --hold-ms 205`, then `--notion`, then `--lint phase05_replication/sample_session.sql`.
  - Expected: `OVER by 303`, then `within budget, spare 17`, then 410 busy connections, then 600 and 1,800. The lint flags 7 of the 11 statements for at least one pooler.
  - Teaches: section 5.7.

- [ ] **E10 (local).** Part of the demonstration: build a standby and read its positions.
  - Read the plan first: `uv run python phase05_replication/two_node.py --plan setup`. Then run it: `uv run python phase05_replication/two_node.py --run setup`.
  - Then run `uv run python phase05_replication/lag.py --sql` and paste the two queries into `psql -h /tmp -p 5433 -d storage_lab_p5` and `psql -h /tmp -p 5434 -d storage_lab_p5`.
  - Expected: Not run by the author yet. One row in `pg_stat_replication` with `application_name` standby1, `state` streaming and `sync_state` async, and all byte gaps 0 or a few hundred bytes. On the standby, `status` streaming and `slot_name` standby1. `write_lag`, `flush_lag` and `replay_lag` show small times while you write. They show NULL a short time after you stop, as section 27.2.4 of the docs says.
  - Then measure read-after-write: on the primary run `INSERT INTO t VALUES (1)` after `CREATE TABLE t (x int)`, and on the standby run `SELECT count(*) FROM t` at once. On a laptop the lag is short, so the row is usually there. Set `recovery_min_apply_delay = '5s'` on the standby, reload, and repeat. Expected: Not run by the author yet. The row appears about 5 s later, as in the test setup Dyte suggests.
  - If it fails: read `/tmp/storage_lab_p5/standby.log`. A missing `pg_hba.conf` line for replication is the usual cause. The default `initdb` file allows local replication.
  - Teaches: section 5.1.

- [ ] **E11 (break-it, local).** An inactive slot, then the cap.
  - Run: `uv run python phase05_replication/two_node.py --run break-slot`.
  - Expected: Not run by the author yet. The slot `standby1` shows `active` false, a recent `inactive_since`, and `retained` of more than 100 MB after `pgbench -i -s 10`. `wal_status` is reserved or extended.
  - Then run: `uv run python phase05_replication/two_node.py --run cap-slot`.
  - Expected: Not run by the author yet. Before the CHECKPOINT, `wal_status` unreserved and a negative `safe_wal_size`. After it, `wal_status` lost and `invalidation_reason` wal_removed. The log shows `invalidating obsolete replication slot "standby1"`, with the DETAIL and HINT of section 5.2. If you now start the standby, its log shows that the WAL it needs has been removed, from the `already been removed` message of `walsender.c`.
  - After this exercise the standby cannot recover. Run `two_node.py --run teardown` and `--run setup` before E12.
  - Teaches: section 5.2.

- [ ] **E12 (break-it, local).** A query conflict, then feedback.
  - In one terminal, on the primary: `pgbench -T 120 -c 4 -h /tmp -p 5433 storage_lab_p5`, after a `pgbench -i -s 10`. In a second terminal, every 10 s: `psql -h /tmp -p 5433 -d storage_lab_p5 -c "VACUUM pgbench_accounts"`.
  - In a third terminal, on the standby: `psql -h /tmp -p 5434 -d storage_lab_p5 -c "BEGIN ISOLATION LEVEL REPEATABLE READ" -c "SELECT count(*) FROM pgbench_accounts" -c "SELECT pg_sleep(90)" -c "SELECT count(*) FROM pgbench_accounts"`.
  - Expected: Not run by the author yet. Within about 30 s of the first VACUUM after the snapshot, the standby session gets `ERROR: canceling statement due to conflict with recovery` with the DETAIL "User query might have needed to see row versions that must be removed". `SELECT confl_snapshot FROM pg_stat_database_conflicts WHERE datname = 'storage_lab_p5'` on the standby rises by 1. The standby log shows a recovery conflict wait line, because the setup set `log_recovery_conflict_waits = on`.
  - Then on the standby: `ALTER SYSTEM SET hot_standby_feedback = on`, `SELECT pg_reload_conf()`, and repeat. Expected: Not run by the author yet. No cancel. On the primary, the `xmin` of slot `standby1` in `pg_replication_slots` is set. `backend_xmin` stays NULL, because the lab standby uses a slot, as section 5.3 says. And `n_dead_tup` of `pgbench_accounts` in `pg_stat_user_tables` keeps growing until the standby query ends.
  - Teaches: section 5.3.

- [ ] **E13 (local).** Part of the demonstration: a synchronous commit that blocks.
  - Run: `uv run python phase05_replication/two_node.py --run sync`. Expected: Not run by the author yet. `sync_state` of standby1 becomes sync.
  - First, while the standby still runs, create the table on the primary: `CREATE TABLE IF NOT EXISTS s (x int)`. That statement commits too, so it would block once the standby is gone.
  - Stop the standby: `pg_ctl -D /tmp/storage_lab_p5/standby -m fast stop`. On the primary, run `INSERT INTO s VALUES (1)`.
  - Expected: Not run by the author yet. The INSERT does not return. In another session, `SELECT wait_event_type, wait_event FROM pg_stat_activity WHERE query LIKE 'INSERT INTO s%'` shows IPC and SyncRep. Press Ctrl-C in the first session. It prints the WARNING and DETAIL of section 5.4: "The transaction has already committed locally, but might not have been replicated to the standby". Then `SELECT count(*) FROM s` in a new session shows the row.
  - Start the standby again. Set `synchronous_standby_names` back to `''` with `ALTER SYSTEM` and reload, or the next exercises block too.
  - Teaches: section 5.4, a canceled wait leaves a visible commit.

- [ ] **E14 (break-it, local).** Promote, make a split brain on purpose, then rewind.
  - First, on port 5433, run `CREATE TABLE IF NOT EXISTS t (x int)`, so both servers have the table. The teardown in E11 removed the one from E10.
  - Run: `uv run python phase05_replication/two_node.py --run promote`.
  - Expected: Not run by the author yet. `pg_is_in_recovery` false on port 5434, and `timeline` 00000002, the first 8 hex digits of the current WAL file name. `pg_control_checkpoint()` can show timeline 1 for some minutes, until the checkpoint that promotion requests has finished. `pg_wal` of the standby holds `00000002.history`. Its log has `selected new timeline ID: 2`.
  - Now write on both: `INSERT INTO t VALUES (100)` on port 5433, the old primary, which still runs, and `INSERT INTO t VALUES (200)` on port 5434. That is split brain. Both accept the write.
  - Run: `uv run python phase05_replication/two_node.py --run rewind`. It first creates the slot `standby1` on port 5434. `pg_rewind` copies the configuration files from the new primary, and they name that slot.
  - Expected: Not run by the author yet. `pg_rewind` prints its progress and "Done!". The old primary starts as a standby of port 5434. `SELECT x FROM t` on port 5433 shows 200 and not 100. The row only the old primary had is gone.
  - Teaches: section 5.5, fencing exists to stop the write of 100 from ever being accepted.

- [ ] **E15 (local).** Part of the demonstration: a timed point-in-time restore.
  - Start from a fresh setup. Run: `uv run python phase05_replication/two_node.py --run backup`. Note the time: `psql -h /tmp -p 5433 -d storage_lab_p5 -Atc "SELECT now()"`. Wait 5 seconds, then run the bad statement: `DELETE FROM pgbench_accounts WHERE aid <= 1000`. Then run `SELECT pg_switch_wal()`, so the segment reaches the archive.
  - Run: `time uv run python phase05_replication/two_node.py --run restore --target "<the time you noted, with the offset psql printed>"`.
  - Expected: Not run by the author yet. `pg_combinebackup` writes a full backup from `full` and `inc1`. The restored server on port 5435 reports `pg_is_in_recovery` true and `pg_get_wal_replay_pause_state` paused, because `recovery_target_action` is pause. `SELECT count(*) FROM pgbench_accounts WHERE aid <= 1000` on port 5435 is 1000. Run `SELECT pg_wal_replay_resume()` to end recovery. The log then shows `selected new timeline ID`. Write down the elapsed time.
  - If recovery stops early: `pg_stat_archiver` on the primary shows the last archived segment. Section 5.6 explains a gap.
  - Teaches: section 5.6, the drill that Linear had not run.

- [ ] **E16 (break-it, local, optional).** A session setting that leaks through PgBouncer.
  - Needs PgBouncer 1.26: `brew install pgbouncer`. Write `/tmp/storage_lab_p5/pgbouncer.ini` with a `[databases]` line `storage_lab_p5 = host=/tmp port=5433`, and in `[pgbouncer]`: `listen_port = 6432`, `listen_addr = 127.0.0.1`, `pool_mode = transaction`, `default_pool_size = 1`, `auth_type = trust`, and an `auth_file` that lists your user. Start it with `pgbouncer -d /tmp/storage_lab_p5/pgbouncer.ini`.
  - Client 1: `psql -h 127.0.0.1 -p 6432 -d storage_lab_p5 -c "SET statement_timeout = '1ms'"`. Client 2, a new connection: `psql -h 127.0.0.1 -p 6432 -d storage_lab_p5 -c "SHOW statement_timeout" -c "SELECT pg_sleep(0.1)"`.
  - Expected: Not run by the author yet. With a pool of one server connection, client 2 gets the same backend. It shows `1ms` and its sleep fails with `canceling statement due to statement timeout`. Then clear the leaked value. Run `RESET statement_timeout` through PgBouncer, or restart PgBouncer. Repeat with `SET LOCAL` inside `BEGIN ... COMMIT`. Client 2 now shows the default `0`. This follows from the PgBouncer docs: no reset query runs in transaction mode.
  - Teaches: section 5.7, transaction mode breaks session state without an error at the place of the cause.

When you finish, run `uv run python phase05_replication/two_node.py --run teardown`.

---

## 🔍 Check it yourself

- **Check 1.** Open `phase05_replication/lag.py:139`, `time_lag()`. Line 147 returns 0 when the received and replayed LSNs are equal. Name the failure this check hides: a standby whose WAL receiver has stopped. Which column of which view, from section 5.1, catches it instead?

- **Check 2.** Open `phase05_replication/slot_retention.py:78`, `wal_status()`. The cap rule is at line 85. Suppose `max_slot_wal_keep_size` is smaller than `max_wal_size`. Work out from the code which state the slot skips. Then compare your answer with the comment above `GetWALAvailability` in `xlog.c` at REL_17_11: "If max_slot_wal_keep_size is smaller than max_wal_size, this state is not returned."

- **Check 3.** Open `phase05_replication/hot_standby.py:83`, `replay()`. Line 103 sets the base of the deadline. Change it to `at` and run `--shared-grace`. Which query now finishes, and which sentence of the docs, section 26.4.2, says the change is wrong?

- **Check 4.** Open `phase05_replication/failover.py:71`, `pick_candidate()`. It compares each replica with the old primary's last LSN. In a real failure the primary is gone. Where does a failover manager get that LSN, and what does it mean for the loss count if the last known value is old? The model does not answer this. Patroni's docs, "maximum_lag_on_failover", give the starting point.

- **Check 5.** In any repository you own that talks to PostgreSQL, run `grep -rn "pool_size\|max_overflow\|maxPoolSize\|pool_max\|connection_limit" <your repo>/`. Add up the pools of every process that runs at the peak of a deploy. Compare the total with `max_connections` minus the reserved slots of the server it reaches, as in section 5.7.

---

## ✅ Checkpoint 5 — answer in your own words

The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

1. **Test-out, explain.** `pg_stat_replication` on the primary shows `pg_current_wal_lsn()` 9/12000000, `sent_lsn` 9/12000000, `write_lsn` and `flush_lsn` 9/11F00000, and `replay_lsn` 9/E000000. The primary writes 20 MiB/s of WAL. Which stage is behind, by how many bytes and about how many seconds of the primary's work? Name the two likely causes from sections 5.1 and 5.3, and the signal that tells them apart.

2. **Test-out, predict.** A CDC connector stops at 09:00. The primary writes 6 MiB/s of WAL and has 120 GiB free. `max_slot_wal_keep_size` is 20480 MB, and a checkpoint runs every 5 minutes. When does the slot become unreserved, and when lost? Does the disk fill? Now the archive command has also been failing since 09:00. What changes?

3. **Test-out, demonstrate.** Run E10, E13 and E15. Show the standby's positions and lag columns. Show the blocked commit with its wait event, and the WARNING after the cancel. Show the restored row count and the time the restore took. Explain why each result follows from the sections, and not from timing luck.

4. (a) **A colleague says:** "The report replica keeps canceling our 6-hour analytics job. Turn on `hot_standby_feedback` on every replica and the problem is gone." Argue for or against, with numbers. The busiest table takes 800 updates per second. (b) A second colleague says: "Set `synchronous_commit = remote_apply` everywhere and read-after-write is fixed". What must also be true? What does each commit pay with a 2.5 ms round trip? What happens when both standbys are down?

5. **This is broken.** After a failover at 03:10, the API fails for 4 minutes. PgBouncer's `SHOW POOLS` shows `cl_waiting` at 380 and `maxwait` at 95 seconds. The PostgreSQL log shows `remaining connection slots are reserved for roles with the SUPERUSER attribute`, and the on-call engineer, who is not a superuser, cannot log in to look. The server has `max_connections = 200` and the default reserved settings. Three PgBouncer processes each serve 4 database and user pairs with the default `default_pool_size`. What is the cause, how do you confirm it, and what do you change so the engineer can always log in?

6. **Show the arithmetic.** (a) Two LSNs are 2/A0000000 and 2/9E800000. How many bytes apart are they, and how long is that at 4 MiB/s? (b) A synchronous commit has a 0.8 ms local flush, a 2.5 ms round trip and a 0.8 ms standby flush. What does `on` wait for each commit? Every order updates one counter row. At most how many commits per second can that row take, against `local`? (c) A restore copies an 800 GiB base backup at 250 MiB/s. The base backup is 26 hours old, and the primary writes 3 MiB/s of WAL. Replay runs at 50 MiB/s. How long until the data is back, and what would cut it? (d) An agent service runs 50 steps per second. Each step holds a transaction open for 1.2 s across an LLM call. How many server connections are busy? What is it if the transaction closes before the call and lasts 8 ms?

7. **Given these constraints, design.** An agent platform keeps its task queue and run history on managed PostgreSQL 17. No task result that returned OK may be lost when one zone fails. The UI must show a run's result right after the run writes it. Analysts run 2-hour queries. A CDC connector feeds a search index and must survive a failover. You must restore to any minute of the last 7 days. 60 application processes connect. Give the topology, the settings of each server, the pooler and its budget, the backup setup, and the drills. Say what each choice costs.

<details>
<summary>Answer sketches</summary>

1. Write and flush are 9/12000000 − 9/11F00000 = 0x100000 = 1,048,576 bytes behind sent. That is small, network and disk are fine. Replay is 0x11F00000 − 0xE000000 = 0x3F00000 = 66,060,288 bytes behind flush. At 20 MiB/s that is 63 / 20 = 3.15 s of the primary's work. `lag.py` prints the same. Cause one: replay is a single process and cannot keep up with a primary that writes from many sessions. Cause two: replay is waiting for a standby query to finish, up to `max_standby_streaming_delay`. Three signals point to the conflict. `pg_stat_database_conflicts` rises, and the startup process shows the `RecoveryConflictSnapshot` wait event. With `log_recovery_conflict_waits = on`, there is also a log line for each wait longer than 1 s. Without them, and with high CPU on the startup process, it is replay speed.

2. The cap is 20,480 MB = 1,280 segments of 16 MiB. The slot is unreserved once the current segment is more than 1,280 past the slot's, after 1,281 × 16 = 20,496 MiB. At 6 MiB/s that is 20,496 / 6 = 3,416 s, about 09:57. The next checkpoint, at 3,600 s, 10:00, makes it lost. The connector must take a new snapshot. pg_wal stops near 20 GiB, so the disk does not fill. Without a cap it would be full at 120 × 1,024 / 6 = 20,480 s = 5.7 h, about 14:41. With a failing archive, the slot is still lost at 10:00, but no unarchived segment is removed. So the disk is full at 14:41 again, and `pg_stat_archiver.failed_count` is the alert you needed. `slot_retention.py` prints these times.

3. From the runs. E10: one row in `pg_stat_replication`, state streaming, and gaps near 0. The lag columns go NULL when idle, which follows from section 27.2.4 of the docs. E13: with the only synchronous standby down, a commit waits in IPC / SyncRep without a timeout. Ctrl-C ends the wait, not the commit, which is already in the primary's WAL. So the row is visible, which is the DETAIL text of `syncrep.c`. E15: the target is before the DELETE, the backup ended before the target, and the archive has every segment. So replay stops before the DELETE and pauses, because `recovery_target_action` is pause. The count is 1000. Each result follows from a rule, not from timing.

4. (a) Against, for every replica. Feedback makes the primary keep every row version the oldest standby query can see. 800 updates per second for 6 hours is 800 × 21,600 = 17,280,000 dead versions held on the primary, on the failover replica too. Lock conflicts, such as VACUUM truncation, still cancel queries. Better: a separate report replica with feedback off and a long `max_standby_streaming_delay`, as Twitch ran at 6 h. It is never a failover target. The failover replica keeps the 30 s default and a `statement_timeout` per role. (b) `remote_apply` waits only if `synchronous_standby_names` names a standby, and it covers only reads on synchronous standbys. Each commit pays at least the 2.5 ms round trip, plus the standby's flush and replay. With `FIRST 1 (s1, s2)` and both down, every commit that waits blocks. A canceled wait leaves a visible commit that a failover can lose.

5. The budget: 3 × 4 × 20 = 240 server connections against 200 − 3 = 197 normal slots, over by 43. `pool_model.py --budget` prints it. After the failover every pool refilled at once and hit the limit. Clients queued in PgBouncer, which shows as `cl_waiting` and `maxwait`. The on-call role is not a superuser, and `reserved_connections` is 0, so no slot was left for it. That message means 3 or fewer slots were free when the engineer connected, by the rule of section 5.7. Confirm: count `pg_stat_activity` rows by `usename` from a superuser session, which the 3 superuser slots still allow, or read PgBouncer's `SHOW SERVERS`. Then add up the pool settings. Fix: lower the pool sizes, or set `max_db_connections` in each PgBouncer. Each process keeps its own count, so three processes may open three times that limit. That is inferred from the configuration page. Keep the sum below the normal slots with a margin. Set `reserved_connections = 5` and grant `pg_use_reserved_connections` to the operators' role, never to the pooler's role. Alert on connections as a percentage of the limit, as Buttondown now does.

6. (a) 0x2A0000000 − 0x29E800000 = 0x1800000 = 25,165,824 bytes = 24 MiB. At 4 MiB/s, 6 s. (b) `on` waits 0.8 + 2.5 + 0.8 = 4.1 ms, which `commit_levels.py` with those inputs prints. If each commit holds the counter row's lock until it returns, the row takes at most 1 / 0.0041 = 243.9 commits per second. With `local`, 1 / 0.0008 = 1,250. That bound is inferred from the docs' sentence that locks are held until the transfer is confirmed. (c) The base: 800 × 1,024 / 250 = 3,276.8 s = 0.9 h. The WAL: 26 × 3,600 × 3 = 280,800 MiB = 274.2 GiB, at 50 MiB/s = 5,616 s = 1.6 h. Total about 2.5 h, before you check the data. `pitr.py --restore-hours` prints 0.9 and 1.6 h. More frequent base backups, or PostgreSQL 17 incremental backups, cut the replay part. (d) 50 × 1.2 = 60 busy connections. At 8 ms, 50 × 0.008 = 0.4, so one connection serves them.

7. One design among several. Run the primary with a synchronous standby in a second zone. On RDS that is a Multi-AZ deployment. Self-hosted, use two standbys in other zones and `synchronous_standby_names = 'ANY 1 (s1, s2)'`, so one standby down blocks nothing. `synchronous_commit = on` for task results. A cheaper level, set per transaction with `SET LOCAL`, for logs and traces. Read-after-write: the UI reads a run's own results from the primary for a few seconds after the write. Or it waits for the LSN on the replica. A separate report replica for analysts: feedback off, long delay, not a failover target. CDC: on self-hosted 17, a logical slot with `failover` set, `sync_replication_slots = on` on the standby, the standby's slot in `synchronized_standby_slots`. Check that the managed service supports it before you rely on it. `max_slot_wal_keep_size` set below the free space, and an alert on `safe_wal_size`. Backups: base backups plus continuous archiving with at least 7 days of retention, or the managed equivalent. Restore points before migrations. A monthly timed restore drill. Pooling: PgBouncer in transaction mode, or RDS Proxy, sized by Little's law with transactions closed before LLM calls. The pool total stays below the normal slots, and `reserved_connections` is kept for operators. No session state through the pooler. Costs: a round trip on every synchronous commit, and writes that wait when no synchronous standby answers. Also a replica that only serves reports, and a CDC rebuild if the slot cap is reached.

</details>

---

## References & Further Learning

Every source below was fetched on 2026-10-20 while this phase was written. PostgreSQL source files were read at tag REL_17_11, the 17.11 release of 2026-08-13, from a local clone. Every URL was checked again with `check_urls.py` on 2026-10-20. Primary sources come first in each group. Vendor pages are marked.

### PostgreSQL 17 documentation: replication

- **26.2 Log-Shipping Standby Servers** — https://www.postgresql.org/docs/17/warm-standby.html
  Focus on: 26.2.5 for streaming and its "typically under one second", and 26.2.5.2 for the monitoring gaps. Then 26.2.6 for slots and the caution box, and 26.2.8 for synchronous replication, its costs and its availability rules. Read it before E10.
- **26.3 Failover** — https://www.postgresql.org/docs/17/warm-standby-failover.html
  Focus on: STONITH, the degenerate state after a failover, and the advice to switch over regularly as a test. Short. Read it with section 5.5.
- **26.4 Hot Standby** — https://www.postgresql.org/docs/17/hot-standby.html
  Focus on: 26.4.2, the list of conflicts, the shared grace, early cleanup, and the remedies. Read it before E12.
- **19.6 Replication settings** — https://www.postgresql.org/docs/17/runtime-config-replication.html
  Focus on: `max_slot_wal_keep_size`, `wal_keep_size`, `wal_sender_timeout`, `synchronous_standby_names`, `synchronized_standby_slots`, `hot_standby_feedback`, `max_standby_streaming_delay`, `recovery_min_apply_delay` and `sync_replication_slots`.
- **19.5 Write Ahead Log settings** — https://www.postgresql.org/docs/17/runtime-config-wal.html
  Focus on: `synchronous_commit` and its table of modes in 19.5.1, `archive_timeout` in 19.5.3, the recovery targets and `recovery_target_action` in 19.5.6, and `summarize_wal` in 19.5.7.
- **19.3 Connections and Authentication** — https://www.postgresql.org/docs/17/runtime-config-connection.html
  Focus on: `max_connections`, `reserved_connections` and `superuser_reserved_connections`, and the rule that a standby needs the same or a higher `max_connections`.
- **47.2 Logical Decoding Concepts** — https://www.postgresql.org/docs/17/logicaldecoding-explanation.html
  Focus on: 47.2.2 for what a slot prevents and the wraparound warning. Then 47.2.3 for failover slots in 17: the six settings, the `synced` rule and the sync failure message.
- **52.19 pg_replication_slots** — https://www.postgresql.org/docs/17/view-pg-replication-slots.html
  Focus on: `wal_status` with its four states, `safe_wal_size`, `inactive_since` and `invalidation_reason`.
- **27.2 The Cumulative Statistics System** — https://www.postgresql.org/docs/17/monitoring-stats.html
  Focus on: 27.2.4 `pg_stat_replication` and the note on lag times, 27.2.6 `pg_stat_wal_receiver`, 27.2.12 `pg_stat_archiver` and 27.2.18 `pg_stat_database_conflicts`.
- **9.28 System Administration Functions** — https://www.postgresql.org/docs/17/functions-admin.html
  Focus on: `pg_walfile_name_offset` and `pg_split_walfile_name` examples in 9.28.3, used by `lag.py`'s self-test. `pg_promote`, `pg_last_wal_replay_lsn` and `pg_last_xact_replay_timestamp` in 9.28.4. `pg_create_restore_point` in 9.28.3.
- **8.20 pg_lsn Type** — https://www.postgresql.org/docs/17/datatype-pg-lsn.html
  Focus on: the format and the subtraction rule. One paragraph.
- **Release notes for 16** — https://www.postgresql.org/docs/16/release-16.html
  Focus on: the item that adds `reserved_connections` and `pg_use_reserved_connections`. Section 5.7 relies on it.
- **50.2 How Connections Are Established** — https://www.postgresql.org/docs/17/connect-estab.html
  Focus on: the process-per-user model. The reason poolers exist, in one page.

### PostgreSQL 17 documentation: backups

- **25.3 Continuous Archiving and Point-in-Time Recovery** — https://www.postgresql.org/docs/17/continuous-archiving.html
  Focus on: the note that `pg_dump` cannot be used for PITR, and the exit-status rule of 25.3.1. Then 25.3.3 on incremental backups, the restore steps of 25.3.5, and 25.3.6 on timelines. The core reading for section 5.6.
- **25.1 SQL Dump** — https://www.postgresql.org/docs/17/backup-dump.html
  Focus on: what a dump is, and the large-database tips. Read it to see what a dump restore must redo.
- **pg_basebackup** — https://www.postgresql.org/docs/17/app-pgbasebackup.html
  Focus on: `-X stream` as the default, `-R`, `-S`, `--incremental` and `--checkpoint`.
- **pg_combinebackup** — https://www.postgresql.org/docs/17/app-pgcombinebackup.html
  Focus on: the order of the arguments, and what it does not verify.
- **pg_verifybackup** — https://www.postgresql.org/docs/17/app-pgverifybackup.html
  Focus on: what the manifest check covers. Use it on every backup you keep.
- **pg_rewind** — https://www.postgresql.org/docs/17/app-pgrewind.html
  Focus on: the requirement of `wal_log_hints` or checksums, and how it finds the point of divergence. Read it before E14.
- **Release notes for 17** — https://www.postgresql.org/docs/17/release-17.html
  Focus on: the 17.0 items on incremental backup and failover slots. The 17.8 and 17.11 fixes for incremental backup are in `release-17.sgml` at REL_17_11, lines 5246 to 5257 and 1954 to 1966.

### PostgreSQL source, REL_17_11

- **`src/backend/access/transam/xlog.c`** — https://raw.githubusercontent.com/postgres/postgres/REL_17_11/src/backend/access/transam/xlog.c
  Focus on: `KeepLogSeg`, `GetWALAvailability`, the slot invalidation call in `CreateCheckPoint`, and `RemoveOldXlogFiles`. `slot_retention.py` follows them.
- **`src/backend/replication/slot.c` and `slotfuncs.c`** — https://raw.githubusercontent.com/postgres/postgres/REL_17_11/src/backend/replication/slot.c
  Focus on: `ReportSlotInvalidation` for the log lines. `slotfuncs.c` lines 397 to 408 compute `safe_wal_size`.
- **`src/backend/replication/syncrep.c`** — https://raw.githubusercontent.com/postgres/postgres/REL_17_11/src/backend/replication/syncrep.c
  Focus on: `SyncRepWaitForLSN` and the two cancel warnings at lines 302 to 322.
- **`src/backend/tcop/postgres.c`** — https://raw.githubusercontent.com/postgres/postgres/REL_17_11/src/backend/tcop/postgres.c
  Focus on: `errdetail_recovery_conflict` and the cancel path with SQLSTATE 40001.

### Failover managers and managed services

- **Patroni 4.1.5: dynamic configuration and replication modes** — https://patroni.readthedocs.io/en/latest/dynamic_configuration.html and https://patroni.readthedocs.io/en/latest/replication_modes.html
  Focus on: `ttl`, `loop_wait`, `retry_timeout`, `primary_start_timeout`, `maximum_lag_on_failover`, `synchronous_mode`, and the note that a canceled wait can still lose a transaction. The default of 1048576 is in `patroni/global_config.py` line 171 at v4.1.5.
- **AWS: Failing over a Multi-AZ DB instance**, vendor — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZ.Failover.html
  Focus on: "typically 60–120 seconds", the DNS change and the JVM TTL.
- **AWS: Multi-AZ DB instance and Multi-AZ DB cluster deployments**, vendor — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZSingleStandby.html and https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/multi-az-db-clusters-concepts.html
  Focus on: the synchronous standby that cannot serve reads, and the semisynchronous cluster with two readers. The failover page of the cluster form says "typically under 35 seconds": https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/multi-az-db-clusters-concepts-failover.html
- **AWS: Read replicas for RDS for PostgreSQL**, vendor — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PostgreSQL.Replication.ReadReplicas.html
  Focus on: the idle lag of "up to five minutes", and that a read replica cannot be the source of a point-in-time restore.
- **AWS: Aurora replication, storage and high availability**, vendor — https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Replication.html, https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.StorageReliability.html and https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.AuroraHighAvailability.html
  Focus on: the shared cluster volume, lag "usually much less than 100 milliseconds", six storage nodes, and failover times.
- **AWS: Restoring to a point in time, and Aurora backups**, vendor — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PIT.html and https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Managing.Backups.html
  Focus on: logs every five minutes, `LatestRestorableTime`, the new instance, and Aurora's 1 to 35 days with a default of one.
- **AWS: CloudWatch metrics for RDS and Aurora**, vendor — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-metrics.html and https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.AuroraMonitoring.Metrics.html
  Focus on: `ReplicaLag`, `OldestReplicationSlotLag`, `ReplicationSlotDiskUsage`, `TransactionLogsDiskUsage`, `DatabaseConnections` and `AuroraReplicaLag`.
- **AWS: logical replication on RDS for PostgreSQL**, vendor — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.FeatureSupport.LogicalReplication.html
  Focus on: the warning that an unread logical slot can "quickly fill up your DB instance's storage".

### Connection pooling

- **PgBouncer features** — https://www.pgbouncer.org/features.html
  Focus on: the three modes and the feature table for transaction pooling. One page that answers most pooling bugs.
- **PgBouncer configuration** — https://www.pgbouncer.org/config.html
  Focus on: `pool_mode`, `default_pool_size`, `max_db_connections`, `reserve_pool_size`, `query_wait_timeout`, `server_reset_query`, `server_reset_query_always` and `max_prepared_statements` with its notes on reuse and `cached plan must not change result type`.
- **PgBouncer usage: SHOW POOLS** — https://www.pgbouncer.org/usage.html
  Focus on: `cl_waiting`, `sv_active`, `sv_idle` and `maxwait`.
- **PgBouncer changelog** — https://www.pgbouncer.org/changelog.html
  Focus on: 1.21.0 of 2023-10-16 for protocol-level prepared statements, 1.24.0 of 2025-01-10 for the default of 200, and 1.26.1 of 2026-10-14, the current release.
- **AWS: Avoiding pinning an RDS Proxy**, vendor — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-pinning.html
  Focus on: the PostgreSQL list, the 16 KB rule, the transaction-level advisory locks that do not pin, and `DISCARD ALL`. The metrics are on https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.monitoring.html

### Production reports

- **GitLab: Postmortem of database outage of January 31, 2017** — https://about.gitlab.com/blog/postmortem-of-database-outage-of-january-31/
  Focus on: the replication that failed because WAL was removed and there was no archive, then the `pg_dump` version mismatch. Sections 5.2 and 5.6.
- **Dyte: Learning to Live With Replication Lag, 2023-04-03**, archived — https://web.archive.org/web/20250119071551id_/https://dyte.io/blog/mitigating-replication-lag/
  Focus on: the 404 from a replica read, `recovery_min_apply_delay` in development, and the cache with a TTL above the lag bound. The live URL redirects, so this is the archive copy.
- **Netflix: Automating RDS Postgres to Aurora Postgres Migration, 2026-02-12**, archived — https://web.archive.org/web/20260718004553id_/https://netflixtechblog.com/automating-rds-postgres-to-aurora-postgres-migration-261ca045447f?gi=ffb22d8d38e2
  Focus on: "Unexpected Replication Slot Behavior", the 0-to-64 MB pattern of `OldestReplicationSlotLag`, and how CDC slots are dropped before cutover.
- **Twitch: How Twitch uses PostgreSQL, 2016-10-11** — https://blog.twitch.tv/en/2016/10/11/how-twitch-uses-postgresql-c34aa9e56f58
  Focus on: the ad-hoc replicas with a 6-hour delay, `statement_timeout` per role, the PgBouncer CPU limit, the prepared-statement fork and the `max_connections` rule. Old. The PostgreSQL facts still hold on 17. PgBouncer 1.21.0 later added support for named prepared statements.
- **GitHub: October 21 post-incident analysis, 2018** — https://github.blog/news-insights/company-news/oct21-post-incident-analysis/
  Focus on: the cross-region promotion, the 954 writes, the four-hour backups and their restore time, and the change to Orchestrator. MySQL, not PostgreSQL. Phase 1, section 1.7, uses the same post.
- **Fly.io: ORD transit loss destabilized Managed Postgres clusters, 2026-06-11** — https://fly.io/infra-log/transit-loss-ord/
  Focus on: failovers caused by nodes that could not reach Patroni's DCS. A short log entry.
- **Heroku: Incident review, October 2025** — https://www.heroku.com/blog/incident-review-intermittent-disruption-of-services-on-october-2025/
  Focus on: false health alerts and the auto-failover they started.
- **Linear: incident on Jan 24th, 2024** — https://linear.app/now/linear-incident-on-jan-24th-2024
  Focus on: the timeline, the `TRUNCATE ... CASCADE`, and the paragraph on the untested point-in-time recovery.
- **Resend: Incident report for February 21, 2024** — https://www.resend.com/blog/incident-report-for-february-21-2024
  Focus on: the wrong backup timestamp and the two restore times.
- **Instapaper: Outage Cause & Recovery, 2017-02-14**, archived — https://web.archive.org/web/20170216165223id_/https://medium.com/making-instapaper/instapaper-outage-cause-recovery-3c32a7e9cc5f
  Focus on: "Backups", the dump times, the row-count estimate, and the monthly restore test. MySQL on RDS.
- **Railway: Incident Report, October 28, 2025** — https://blog.railway.com/p/incident-report-oct-28th-2025
  Focus on: the pooler limit above the database limit and the reserved-slot error.
- **Buttondown: Public postmortem, database connection exhaustion, 2026-04-01** — https://buttondown.com/blog/incident-0024
  Focus on: the health check that passed, and the five fixes in order.
- **Notion: The Great Re-shard, 2023-07-17** — https://www.notion.com/blog/the-great-re-shard
  Focus on: "An important detour to shard our PgBouncer connection-pooling layer", for the 600 and 1,800 connections.
- **OpenAI: Scaling PostgreSQL to power 800 million ChatGPT users, 2026-01-22**, archived — https://web.archive.org/web/20261010101204id_/https://openai.com/index/scaling-postgresql/
  Focus on: "Connection pooling" and "Scaling read replicas". The live page returned 403 to scripts, so this is the archive copy of 2026-10-10.

---

## Cheatsheet

```
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
                    Aurora: 6 storage nodes in 3 AZs

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
                    SET of the 6 startup parameters PgBouncer tracks
  prepared stmts    protocol level since 1.21.0, max_prepared_statements 200
                    since 1.24.0. Not SQL PREPARE. After DDL: RECONNECT
  signals           SHOW POOLS cl_waiting, maxwait. pg_stat_activity by state
  RDS Proxy pins    SET, PREPARE/EXECUTE/DISCARD, temp objects, cursors,
                    LISTEN, LOAD, nextval/setval, pg_advisory_lock, > 16 KB.
                    Metric DatabaseConnectionsCurrentlySessionPinned
```

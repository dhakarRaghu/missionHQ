# Phase 1 — Durability and the write path

**The question this phase answers:** when the database says "committed", what exactly has happened on disk? And what can a crash one millisecond later still lose?

## Why you're here

Here is the situation this whole phase follows. It is an example, built from measured numbers, and every part of it happens in this phase's lab.

A small order store runs on a Mac. A client sends `put order:1041`, and the store replies OK. The client sends `put order:1042`, and the store replies OK. One millisecond later the power fails. On restart, both orders are gone. The client holds a receipt for each one.

The store's code was not careless. It wrote each entry, called `os.fsync`, and only then replied. On an Apple M2, the earlier course measured that call at about 0.1 ms. So both replies were sent within about a quarter of a millisecond. But on macOS, `os.fsync` hands the data to the drive and returns. The drive may keep the data in its own cache and write it to flash later. Nobody had tested a crash between "the operating system accepted the write" and "the device has it".

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The running case. Times are an example from the M2 numbers of            │
│ elite-performance section 5.6: os.fsync about 0.1 ms                     │
├──────────────────────────────────────────────────────────────────────────┤
│ t = 0.00 ms   put order:1041  write ──► page cache ──fsync──► drive cache│
│ t = 0.11 ms   OK sent for order:1041                                     │
│ t = 0.11 ms   put order:1042  write ──► page cache ──fsync──► drive cache│
│ t = 0.22 ms   OK sent for order:1042                                     │
│ t = 1.22 ms   power fails. The drive cache is volatile and is erased     │
│ restart       the log on flash ends before order:1041. Both are gone     │
└──────────────────────────────────────────────────────────────────────────┘
```

Real systems have also replied OK before the data was durable, in their recommended or default settings. Both cases below come from Jepsen. Jepsen is Kyle Kingsbury's project that tests databases under crashes and network faults, and publishes each analysis.

- **MariaDB Galera Cluster.** Galera Cluster is a MariaDB setup that copies each write to several nodes. Jepsen published "MariaDB Galera Cluster 12.1.2", by Kyle Kingsbury, on 2026-03-16. The facts, in order:
  1. At that time, MariaDB's own Galera configuration page recommended `innodb_flush_log_at_trx_commit=0`. That setting does not flush the log at commit.
  2. In section 3.1 of the report, all nodes crashed at about the same time. It was a crash of the database processes, not a power loss.
  3. One one-minute run lost nine acknowledged values in three rows. With the setting at 1, the loss became much rarer. Verified from the report, section 3.1.
  4. MariaDB later changed the page to recommend the default of 1. The new page warns that 0 and 2 can lose acknowledged transactions. Verified from two archived copies of the page, dated 2026-03-08 and 2026-06-11.

  That the change followed the report is inferred from the timing only.
- **NATS.** NATS is a message system, and JetStream is its part that stores messages on disk. Jepsen published its analysis "NATS 2.12.1" on 2025-12-08. By default, JetStream calls fsync only once every two minutes, but acknowledges each message at once. Simulated power failures in one test run lost 131,418 of 930,005 messages, about thirty seconds of writes. Verified from the report, section 3.4.

The Galera report's second loss, in its section 3.2, happened with the setting at 1. The report gives no root cause for it, so this phase does not use it.

So "committed" means something narrower than it sounds. It holds for some kinds of crash, on some devices, after some system calls. This phase finds out which.

**The version this phase uses.** PostgreSQL 17 is the base. Every PostgreSQL default, view, log line and source line in this phase is from PostgreSQL 17.11, source tag `REL_17_11`, unless the text names another version. 17.11 is the latest 17 minor release. Where 14 behaves differently and you may still meet it, one clause says so. Where 18 differs, one line says so. Rogov's book, used often below, runs PostgreSQL 14.7. Its examples are labelled with that version.

## What you can do after this phase

1. Say where a write is at each step of a commit, and which kind of crash erases it.
2. Name the system call that makes data durable on macOS and on Linux, and say what it does not promise. Follow it down to the NVMe flush command on a Linux server.
3. Detect a torn write with a checksum, and make recovery stop at the right place.
4. Explain what a PostgreSQL checkpoint bounds, what a restart runs, and read both in the PostgreSQL 17 log and the statistics views.
5. Use group commit to get throughput back without giving up durability. Count the commits your ORM makes, and find the commit-flush wait in `pg_stat_activity`, on RDS and on Aurora.
6. Choose where to give up durability on purpose: an UNLOGGED table, `synchronous_commit = off` for one transaction, or an agent checkpointer mode.
7. Say what moves out of the database host on Aurora, Neon and AlloyDB, and which rules of this phase still apply there.
8. Write the one-sentence durability boundary of a store, and test it with a crash matrix.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: Durability and the write path                                   │
├──────────────────────────────────────────────────────────────────────────┤
│ 1.1 Memory, page cache, disk  — three places a write can be              │
│ 1.2 The write-ahead log       — log first, data later, replay on restart │
│ 1.3 fsync                     — the promise, and disks that report early │
│ 1.4 Torn writes and checksums — the half-written entry, and the CRC      │
│ 1.5 Checkpoints and recovery  — what runs on restart, and what bounds it │
│ 1.6 Group commit              — one sync shared by many commits          │
│ 1.7 The durability boundary   — the sentence, and the tests behind it    │
│ Lab: E1 to E15. The demonstration: a crash matrix with 231 recoveries    │
└──────────────────────────────────────────────────────────────────────────┘
```

## What this phase assumes

Two ideas from the earlier course are used here and not taught again. That course is "Performance, concurrency and the machine", in the folder `elite-performance`.

- **Section 5.6, "Syscalls, buffers and the page cache".** The page cache is the kernel's copy of recently used file pages. On the Apple M2 that the earlier course measured, a page-cache read took 1.5 µs at the median. A read from the SSD took 88.7 to 89.8 µs. A page there is 16 KiB. After a 4 KiB write, `os.fsync` took 95 to 110 µs, and `fcntl(F_FULLFSYNC)` took 2.85 to 2.88 ms. Those are medians per run, measured on 2026-09-25.
- **Phase 1, parts 01a and 01b, "Measurement before optimisation".** Latency is a distribution, not one number. A closed-loop load generator hides stalls, because it waits for each reply. Two runs are compared only with their spread. A prediction is written down before the run.

**The commitment this phase pays.** Section 5.6 of the earlier course measured the cost of `os.fsync` and `F_FULLFSYNC`. It said that what each call promises was left for a later course. Section 1.3 of this phase gives that answer.

This course's research measured the same calls on a second Mac, an Apple M4 Pro, and section 1.3 keeps each machine's numbers separate. In this phase, "the M2" always means the earlier course's machine, and "the M4 Pro" means this course's research machine.

**Left for later.** Phase 5 of this course, "Replication, failover, backups and pooling", teaches replicas. Its section 5.1 says what a replica has when the primary acknowledges a write. Its section 5.4 says what each `synchronous_commit` level waits for when the server has standbys. Course 5, "Distributed systems and verification", exists only as a plan, and its Phase 3 replicates a toy store, not PostgreSQL. Verified from the course 5 plan, `missionHq/learning/courses/05-distributed/course.md`, lines 105 to 131. So this phase names the PostgreSQL facts it needs about replicas, and no more. Phase 2 of this course covers the structures built on the log, such as B-trees and LSM trees.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. The labs use Python 3.12 or later and the standard library only. Two exercises read your local PostgreSQL 17 at `/tmp:5432`, in a new database named `storage_lab`. Three exercises, E13 to E15, start a separate throwaway PostgreSQL 17 cluster on port 54329, and two of them crash it on purpose. They never touch your main cluster. Run all commands from `elite-storage/code/`.

Time: about 3 hours for the reading. The labs take longer, about 2.5 to 3.5 hours.

---
## 1.1 — Memory, page cache, disk (the three places a write can be, and which of them a crash erases)

Why this matters: a write is not in one place. At any moment, your bytes can be in the process, in the kernel, or on the device. Each kind of crash erases a different set of those places. If you do not know where your bytes are, you cannot say what a crash loses.

**Answer this first.** The order store calls `os.write` for `order:1041` and returns OK, with no sync at all. Three crashes are possible: `kill -9` of the store, a kernel panic, or a power failure. Which of them loses the order? Write your answer down before you read on.

**The three places.** A write moves through three places on its way down:

1. **Process memory.** Python's `f.write()` often only copies into a buffer the program owns, until `flush()`.
2. **The page cache.** `os.write`, a system call into the kernel, copies the bytes there. A page with bytes not yet on the device is a dirty page, and the kernel writes it later.
3. **The disk.** It has a volatile cache inside the drive, and the flash behind it, called stable media, which keeps data without power.

A crash erases the places above a certain line, and keeps the places below it:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Where a write can be, and what each crash kind keeps                     │
├──────────────────────────────────────────────────────────────────────────┤
│  place              erased by                 kept by                    │
│                                                                          │
│  process memory  ── process crash, OS crash,  nothing                    │
│   f.write() buffer  power loss                                           │
│        │ os.write / flush                                                │
│        ▼                                                                 │
│  page cache      ── OS crash, power loss      process crash              │
│   kernel memory                                                          │
│        │ fsync, or the kernel's own write-back                           │
│        ▼                                                                 │
│  disk            ── nothing in this table     process crash, OS crash,   │
│   the device                                  power loss                 │
└──────────────────────────────────────────────────────────────────────────┘
```

So the answer to the question above: `kill -9` does not lose the order. The page cache belongs to the kernel, and the kernel did not crash. A kernel panic or a power failure can lose it. Whether it does depends on whether the kernel had already written that page back.

**Three kinds of crash.** This phase uses three names, and the lab tests each one:

| Crash kind | Example | What survives |
|---|---|---|
| process crash | `kill -9`, an out-of-memory kill, a segfault | page cache and disk |
| OS crash | a kernel panic, a hard reset with power still on the drive | disk, including the drive's cache |
| power loss | the power cord, a failed power supply, a cloud host that dies | only what the drive wrote to stable media |

The OS crash row is the general model. Apple documents a weaker rule for a Mac, and section 1.3 gives it.

**Two words that differ.** An acknowledged write is one the store has told the client is done. A durable write is one that survives the crash kinds you name. The durability boundary of a store is the line between two sets of crash kinds. An acknowledged write survives the first set and not the second. Section 1.7 writes that boundary down as one sentence and tests it.

**The failure: a kill test that proves nothing.** A common first test kills the store during a write load. Then it restarts the store and counts the entries. With `kill -9`, the page cache survives, so the test passes for a store that never calls fsync at all. E3 runs this test with `--sync none`. Worked out from the code, and not run: 57 kills lose 0 acknowledged puts. The test is correct about process crashes, and says nothing about power loss.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The same store, sync=none, two tests. Worked out from the code, not run  │
├──────────────────────────────────────────────────────────────────────────┤
│ kill -9 at each of 57 write steps    page cache kept   0 puts lost       │
│ power loss at each of 57 steps       page cache gone   every put that    │
│                                                        was not synced    │
│ the code is the same. Only the crash kind differs                        │
└──────────────────────────────────────────────────────────────────────────┘
```

In the running case, the store did call `os.fsync`. So the two orders left the page cache and reached the drive.

**Where you meet the three crash kinds in production.** The names above map onto events you see at work. The mapping below is inferred from the definitions in this section. The event names are examples:

| Event in production | Crash kind | What survives |
|---|---|---|
| the Linux OOM killer kills a PostgreSQL backend, or a container hits its memory limit | process crash | page cache and disk |
| a kernel panic, or a node that hangs and is hard-reset | OS crash | disk, including the drive's cache |
| a host loses power, or a cloud instance's hardware fails | power loss | only what the device wrote to stable media |

**What PostgreSQL does when one backend dies.** One killed backend restarts the whole server. The postmaster is the first process of the server, and it starts all the others. It cannot know whether the dead process damaged shared memory. So it stops every session and runs crash recovery. Here is the sequence in the PostgreSQL 17 log. The message texts are the format strings in the source, and the PID and SQL are an example:

```
LOG:  server process (PID 4711) was terminated by signal 9: Killed
DETAIL:  Failed process was running: UPDATE orders SET status = 'paid' WHERE id = 1041
LOG:  terminating any other active server processes
LOG:  all server processes terminated; reinitializing
LOG:  database system was interrupted; last known up at 2026-10-20 10:00:00 UTC
LOG:  database system was not properly shut down; automatic recovery in progress
```

The lines come from `postmaster.c` lines 3091, 3094, 2882 and 3363, `xlog.c` line 5461 and `xlogrecovery.c` line 948, at REL_17_11. The text after the colon comes from the C library's `strsignal`, through `pg_strsignal`. glibc on Linux prints `Killed`, and macOS prints `Killed: 9`. Every other client gets the warning "terminating connection because of crash of another server process", with SQLSTATE `57P02`, and then loses its connection. Verified from `postgres.c` lines 2960 to 2962 and `errcodes.txt` line 430. The setting `restart_after_crash`, default `on`, makes the server restart by itself. Verified from the 17 sample configuration file, line 823.

So after a crash like this, no commit made with `synchronous_commit = on` is lost, because its WAL was flushed before the reply and the kernel kept the page cache. A commit made with `off` can be lost, because its WAL may still be in shared memory. Verified from the comment at `xact.c` lines 1504 and 1505 at REL_17_11. But every connection breaks at once, and your connection pool sees a wave of errors. The PostgreSQL 17 docs, section 18.4.4, "Linux Memory Overcommit", show the kernel's side: `Out of Memory: Killed process 12345 (postgres).` They suggest `vm.overcommit_memory=2` to make the OOM killer much less likely. So when every connection fails at once, look for this kernel line before you look for a disk fault.

**A managed database can add a place.** On Aurora, AWS states that "each DB instance's page cache is managed in a separate process from the database". So the cache can survive a crash of the database process. Verified from the AWS page "Amazon Aurora reliability", section "Survivable page cache". It is a vendor page. That cache keeps reads fast after a restart. It is not where durability comes from. Section 1.5 shows where Aurora keeps the durable copy.

The next question is why the store writes a log at all, and in which order it writes and syncs.

**The sentence to remember:** a write lives in process memory, the page cache or the disk. A process crash keeps the page cache, and a power loss does not.

**The trap:** testing durability with `kill -9` only. A store with no sync at all passes it, and the first power cut in production finds the missing sync.

**Try this now:** run `uv run python phase01_durability/crash_matrix.py --real-kill --sync none`. Check the `process` row against the failure paragraph above, and read the note line under the table.

---
## 1.2 — The write-ahead log (why the log is written before the data, and what recovery replays)

Why this matters: a database changes many pages for one transaction. A crash in the middle would leave some pages new and some old. The write-ahead log turns every change into one append, so a commit becomes one small write and one sync.

**Answer this first.** In PostgreSQL, a transaction updates one row and commits. The client gets the success reply. At that moment, which bytes must be on stable storage? Is it the changed table page, the log record, or both?

**The mental model.** A write-ahead log, WAL for short, is a file that the database only appends to. Each record describes one change. The database follows two rules:

1. **The WAL rule.** The log record of a change reaches stable storage first. Only then may the changed page replace the old page on disk. Verified from the ARIES paper, Mohan and others, ACM TODS 1992, section 1.1, journal page 97.
2. **The commit rule.** A transaction is complete only when its commit record is on stable storage. All log records before it must be there too. The database forces the log up to that record at commit. Verified from the same paper, journal page 98.

So the answer is: only the log record must be durable at commit. The table page can reach the disk minutes later. If a crash comes first, recovery reads the log and applies the change again. That is called replay, or redo.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One UPDATE and COMMIT in a WAL database. Order of events                 │
├──────────────────────────────────────────────────────────────────────────┤
│  1  change the page in memory          data page: dirty, in memory       │
│  2  append a WAL record                WAL buffer, in memory             │
│  3  COMMIT: write and sync the WAL     WAL on stable storage             │
│  4  reply "COMMIT" to the client       ◄── the acknowledgment            │
│  ·                                                                       │
│  ·  any time, even before step 3                                         │
│  5  a background process or a backend  data page on disk                 │
│     writes the data page                                                 │
│                                                                          │
│  crash between 4 and 5: recovery redoes the change from the WAL          │
│  crash between 2 and 3: no reply was sent, and recovery treats the       │
│  transaction as not committed                                            │
└──────────────────────────────────────────────────────────────────────────┘
```

**A data page can reach the disk before its commit.** Step 5 has no fixed time. Three kinds of PostgreSQL process write dirty pages. A checkpoint, defined in section 1.5, is a point that bounds how much log a restart must read:

| Process | What it is | When it writes a dirty page |
|---|---|---|
| checkpointer | the process that runs checkpoints | during a checkpoint |
| bgwriter | a background process | when the page is likely to be evicted soon |
| backend | the server process of one client connection | when it must evict the page itself |

Verified from Rogov, "PostgreSQL 14 Internals", section 10.5, page 176. The same three processes write pages in PostgreSQL 17. So a page with an uncommitted change can be on disk.

The CMU 15-445 Fall 2025 notes for Lecture 21 name two policies:

- STEAL lets the database write uncommitted changes to disk before the transaction completes.
- NO-FORCE means changes are not required to be on disk at commit.

The WAL rule makes STEAL safe. Before the server writes a changed page, it flushes the WAL up to that page's last change. That flush does not need the commit record. Verified from `bufmgr.c` lines 3910 to 3927 at REL_17_11, the comment "Force XLOG flush up to buffer's LSN" and the call `XLogFlush(recptr)`. Phase 2 comes back to this line in the buffer manager.

**What PostgreSQL waits for.** The parameter `synchronous_commit` has the default `on` in PostgreSQL 17, as in 14 and 18. With it, a commit waits for the local WAL flush. With `off`, the commit replies at once, and the WAL writer flushes later. The WAL writer is a background process that flushes WAL that no commit has flushed yet. The docs give the maximum delay as three times `wal_writer_delay`. The default `wal_writer_delay` is 200 ms, so the window is 3 × 200 ms = 600 ms. A crash in that window can lose recent commits. The database stays consistent, as if those transactions had been aborted. Verified from the PostgreSQL 17 docs, section 19.5 and section 28.4, and the 17 sample configuration file, lines 231 and 249. A fresh 14.24 cluster in this course's research also showed 200 ms. Section 1.6 uses this window for one transaction at a time.

**The LSN, the address of a WAL record.** A log sequence number, LSN for short, is a byte offset into the WAL. It grows with each new record. So the difference of two LSNs is the number of WAL bytes between them. Verified from the PostgreSQL 17 docs, section 28.6. PostgreSQL prints an LSN as two hexadecimal numbers with a slash, such as `0/3DF708D8`. Three functions show the current positions, per the PostgreSQL 17 docs, section 9.28:

| Function | Position |
|---|---|
| `pg_current_wal_insert_lsn()` | insert |
| `pg_current_wal_lsn()` | write |
| `pg_current_wal_flush_lsn()` | flush |

Rogov ran one `UPDATE` and `COMMIT` on PostgreSQL 14.7. The insert LSN moved from `0/3DF708D8` to `0/3DF70948`, which is 112 bytes. `pg_waldump`, the tool that prints WAL records, showed two records in that range. Here they are, shortened to the fields this phase uses. Verified from Rogov, section 10.2, pages 168 and 169:

```
rmgr: Heap len (rec/tot): 69/ 69, tx: 886, lsn: 0/3DF708D8, prev 0/3DF708B0, desc: HOT_UPDATE ...
rmgr: Transaction len (rec/tot): 34/ 34, tx: 886, lsn: 0/3DF70920, prev 0/3DF708D8, desc: COMMIT ...
```

Each record names its resource manager, the code that replays it, and its length and transaction. Each record's `prev` field holds the LSN of the record before it, so the WAL is a chain. The two records start 0x3DF70920 − 0x3DF708D8 = 0x48 = 72 bytes apart, and the second ends 0x28 = 40 bytes later. So the 69-byte record takes 72 bytes and the 34-byte record takes 40, and 72 + 40 = 112. Each record is padded to a multiple of 8 bytes on a 64-bit machine. Verified from `xlog.c` line 1117 at REL_17_11, `size = MAXALIGN(size);`.

**The same numbers without shell access.** On a managed database you cannot run `pg_waldump`, because you have no shell on the server. Since PostgreSQL 15, the extension `pg_walinspect` gives the same facts in SQL. On 17, `select * from pg_get_wal_stats('0/3DF708D8', '0/3DF70948')` returns one row per resource manager, with record bytes and full page image bytes. Execute is granted to the role `pg_read_server_files`. Verified from `contrib/pg_walinspect/pg_walinspect--1.0.sql`, lines 78 to 96, at REL_17_11. Whether RDS and Aurora offer this extension was not checked. Check it with `select * from pg_available_extensions where name = 'pg_walinspect'`.

**The commit inside PostgreSQL.** The first diagram of this section shows the order in principle. Here is the order in the PostgreSQL 17 source. `pg_xact` is the set of files that holds each transaction's outcome, and Phase 3 shows how readers use it:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ COMMIT inside PostgreSQL 17. From RecordTransactionCommit and            │
│ CommitTransaction in xact.c at tag REL_17_11                             │
├──────────────────────────────────────────────────────────────────────────┤
│  step  function                 what it does                     line    │
│  1     XactLogCommitRecord      commit record into WAL buffers   1431    │
│  2     XLogFlush                WAL flushed up to that record.   1491    │
│                                 The durability point                     │
│  3     TransactionIdCommitTree  "committed" written in pg_xact   1497    │
│  4     SyncRepWaitForLSN        wait for a standby, if one is    1546    │
│                                 configured                               │
│  5     ProcArrayEndTransaction  other sessions now see the rows  2349    │
│  6     reply to the client      the acknowledgment                       │
│                                                                          │
│ synchronous_commit = off: step 2 becomes XLogSetAsyncXactLSN at line     │
│ 1512, and the WAL writer flushes later. Step 5 still runs at once        │
│ PostgreSQL 18.0: the same order, at lines 1442, 1502, 1508, 1557, 2389   │
└──────────────────────────────────────────────────────────────────────────┘
```

Step 4 waits only when a standby, a server that replays this server's WAL, must confirm the commit. Phase 5, section 5.4, covers that wait. Right before step 1, at line 1426, the backend sets the flag `DELAY_CHKPT_START`. It clears the flag after step 3, at line 1529. A checkpoint that starts in that window waits. Otherwise it could set its recovery start point, which section 1.5 calls the REDO point, between the commit record and the `pg_xact` update. A crash a little later would then lose the commit. Verified from the comment at lines 1407 to 1422. In 14 the same guard is a boolean, `delayChkpt`, at `xact.c` line 1350 of REL_14_24.

PostgreSQL 17 also shows this wait. A checkpointer that waits for the flag reports the wait event `CheckpointDelayStart` or `CheckpointDelayComplete`, of type `IPC`. Verified from `wait_event_names.txt` lines 113 and 114 at REL_17_11, and the 17.0 release notes. A wait event is the name a session reports in `pg_stat_activity` while it waits. Section 1.6 shows how to read them.

`synchronous_commit = off` has a consequence that its docs entry does not state. Step 5 runs before the WAL flush, so other sessions can read the new rows before they are durable. A crash in the next 600 ms can then remove rows that another session already read. That order is inferred from the code, and not run. The docs give the rule that follows. Asynchronous commit "should not be used if the client will take external actions" that rely on the commit. Verified from the PostgreSQL 17 docs, section 28.4. A webhook or a queue message sent after such a read is that kind of external action.

**Where your code takes external actions.** Django's `transaction.on_commit()` runs a callback "only if the transaction successfully commits". Django's docs name the examples: "a background task, an email notification, or a cache invalidation". Verified from the Django 5.2 page "Database transactions". With `synchronous_commit = off`, that callback can run before the commit is durable. A crash can then remove the row after the email went out. That combination is inferred from the order above, and not run. So keep `synchronous_commit = on` for any transaction that has an `on_commit` hook, a webhook or a queued job. An AI agent that saves its state and then calls a tool is the same case. Section 1.7 writes the boundary for it.

**What MariaDB's setting 0 does.** `innodb_flush_log_at_trx_commit` controls the same moment in InnoDB. The MariaDB InnoDB system variables page lists four values, 0 to 3. With 1, the default, the log is written and flushed at each commit. With 2, it is written at each commit and flushed on a timer. With 0, nothing happens at commit, and the log is written and flushed about once a second. With 3, the log is flushed at both the prepare and the commit phase, which is slower than 1 and keeps the same guarantee. The page warns that with 0 a server crash can erase the last second of transactions. Verified from the MariaDB docs page, fetched on 2026-10-17. So with 0, the reply comes before the log is durable. That breaks the commit rule, and the Galera report says the loss "seemed to be caused" by this setting. A crash of the server process alone is enough, because the log is not yet in the page cache. That last point is inferred from the definition of value 0.

**When the log is the data.** In the store of this lab, there is no separate data file. The log is the data. This is the Bitcask design: Sheehy and Smith, Basho Technologies, 2010. Bitcask appends every put to a data file and keeps an in-memory index called the keydir. The keydir maps each key to the file, offset and size of its newest entry. A delete is a put of a special tombstone value. The paper says recovery needs no replay, because the data files are the log. But the keydir still has to be rebuilt by reading the log after a restart. Section 1.5 covers that read. The Bitcask paper is a company paper, not peer reviewed.

The lab's entry layout follows the paper's figure on page 2. Its first field is a CRC, a cyclic redundancy check. A CRC is a kind of checksum, a short value computed from the bytes, and section 1.4 explains how recovery uses it. The CRC covers every byte after itself:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One log entry in kvlog.py. Big-endian. The header is 20 bytes            │
├────────┬────────┬────────┬────────┬────────────┬─────────────────────────┤
│ crc32  │ seq    │ ksz    │ vsz    │ key        │ value                   │
│ 4 B    │ 8 B    │ 4 B    │ 4 B    │ ksz bytes  │ vsz bytes               │
├────────┴────────┴────────┴────────┴────────────┴─────────────────────────┤
│        ◄──────────────── covered by the crc ───────────────────────────► │
│ vsz = 0xFFFFFFFF marks a tombstone, which has no value                   │
│ put order:1041 with a 1,200-byte value: 20 + 10 + 1,200 = 1,230 bytes    │
│ delete order:1042:                      20 + 10         =    30 bytes    │
└──────────────────────────────────────────────────────────────────────────┘
```

The lab differs from the paper in two places, on purpose. It stores a 64-bit sequence number in place of the paper's 32-bit timestamp. So recovery can refuse an entry out of order. The paper also does not say how to handle a half-written last entry. The lab defines that rule in section 1.4. The paper does not name its CRC algorithm. The lab uses `zlib.crc32`, the IEEE CRC-32.

**An append is cheap only if nothing else is written with it.** Roblox's outage of 2021-10-28 to 10-31 lasted 73 hours. Roblox uses Consul for service discovery and as a key-value store. Consul stores its Raft log, the replicated log of its operations, in BoltDB, an embedded key-value library. HashiCorp and Roblox engineers found that "This 4.2GB log store is only storing 489MB of actual data". BoltDB tracks free pages in a freelist, and that list had grown to 7.8 MB. So for every log append, "a new 7.8MB freelist was also being written out to disk". Verified from Roblox's post "Roblox Return to Service", about the outage of 10/28-10/31 2021. The lesson for a log: measure the bytes written per append, not only the bytes appended. The lab entry writes 20 header bytes plus the key and value, and nothing else.

**The order of steps in one put.** Here is the store's `put`, from `kvlog.py:409`. The comments are changed, and the size checks and the error handler around the append are removed. The order of steps is unchanged:

```python
# from phase01_durability/kvlog.py:409, put(). Comments changed, checks and error handler removed
        with self._write_lock:
            self._check_failed()
            seq = self._seq + 1
            buf = encode(seq, k, value)
            self.hook("put.encoded")
            offset = self.fs.append(LOG, buf)       # into the page cache
            self._seq = seq
            self._written_to = offset + len(buf)
            loc = Loc(offset, len(buf), seq, tomb=value is None)
            self._written[k] = loc
            self.hook("put.written")
            if not self.group_commit:
                self._sync_log_locked()             # durable from here
        if self.group_commit and self.rules.ack_after_sync:
            self._wait_durable(offset + len(buf))   # section 1.6
        self.hook("put.synced")
        with self._index_lock:
            cur = self.keydir.get(k)
            if cur is None or loc.seq > cur.seq:
                self.keydir[k] = loc                # visible to readers
        self.hook("put.indexed")
        return Receipt(seq, offset, offset + len(buf))
```

Each `self.hook(...)` line is a crash point. Section 1.7 crashes the store at every one of them. The index is updated after the sync, not before. So a reader never sees a value that a crash can still take back.

**The failure: reply first, log later.** Both real cases in the header broke the commit rule. Each did it in a recommended or default setting. In both, the log existed and recovery replayed it correctly. What was lost was the part of the log that never reached the disk.

So the commit rule says "force the log to stable storage". The next section asks what that system call is, and what it really promises.

**The sentence to remember:** at commit, only the log must be durable. The data pages can follow later, because recovery replays the log.

**The trap:** a setting that replies before the log flush, such as `innodb_flush_log_at_trx_commit=0` or `synchronous_commit=off`. The database stays consistent after a crash, so nothing looks wrong. The lost commits are found only by a client that kept its receipts.

**Try this now:** run `uv run python phase01_durability/crash_matrix.py --list`. Find crash points 3 to 7, the five steps of the first put. Say for each one whether the client has its OK yet, and whether the entry is durable.

---
## 1.3 — fsync (what it promises, what it does not, and the disks and file systems that report a write as durable before it is)

Why this matters: every durable store ends its commit with one system call. On a Mac, the obvious call in Python does not do what its name suggests. On Linux, the right call can still fail in a way that a retry hides.

**Answer this first.** The running case called `os.fsync` after each put, on a Mac. Does that survive a power loss? Now move the same code to a Linux server with ext4. Does it survive there? Write both answers down.

**The mental model.** fsync is a system call. It asks the kernel to write a file's dirty pages and metadata to the device. It returns when the device has them. The open question is what "the device has them" means. The disk has the two parts from section 1.1. They are a volatile cache inside the drive, and the stable media behind it. A sync call either stops at the drive's cache, or also asks the drive to flush that cache.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ How far each call moves the bytes. The disk has two parts                │
├──────────────────────────────────────────────────────────────────────────┤
│                     page cache ──► drive cache ──► stable media          │
│                                    volatile        keeps data without    │
│                                                    power                 │
│ macOS  os.fsync     ════════════════►│             stops at the drive    │
│ macOS  F_FULLFSYNC  ═══════════════════════════════►│ the drive flushes  │
│ Linux  os.fsync     ═══════════════════════════════►│ ext4 sends the     │
│        on ext4                                        flush command when │
│                                                       barriers are on    │
│                                                                          │
│ survives:            process crash   OS crash        power loss          │
│                                                                          │
│ The OS crash column is the general model. Apple's fsync(2) says that     │
│ on a Mac an OS crash can also lose data that plain fsync handed over     │
└──────────────────────────────────────────────────────────────────────────┘
```

**macOS: fsync stops at the drive.** Apple's `fsync(2)` page says fsync moves the data from the host to the drive. It then says the drive may not physically write that data to the media for quite some time. The drive may also write it to the media out of order. The page then names the result. After a power loss or an OS crash, an application may find only some or none of its data written. The page tells databases that need a strict write order to use `F_FULLFSYNC`. Verified from the man page in Apple's xnu source at tag `xnu-12377.121.6`, and in the macOS 26.5 SDK. The page also warns: "This is not a theoretical edge case."

`F_FULLFSYNC` is a command of `fcntl(2)`. It does what fsync does, and then asks the drive to flush all of its buffered data to permanent storage. The current man page names APFS among the file systems that support it. The same page describes `F_BARRIERFSYNC`, which sends a barrier instead of a flush. A barrier keeps the order of writes, but it does not make them durable. Verified from `fcntl.2` at the same xnu tag, lines 207 to 245.

So the answer for the Mac: the running case survives a process crash. Survival of a power loss is not promised, because the orders may still be in the drive's cache. Apple's page says an OS crash can lose them too. So the lab store does not promise that case for plain fsync on a Mac. The answer for Linux with ext4 is yes, on three conditions. Write barriers are on. The kernel sees the drive's volatile cache, or the drive really has none. The drive honours the flush command. The rest of this section gives the evidence for each.

**What each language calls.** The same function name means different system calls in different runtimes:

| Runtime, version | Call | What it does on macOS | Source |
|---|---|---|---|
| CPython 3.14.8, `os.fsync` | `fsync()` | stops at the drive cache | `Modules/posixmodule.c` line 3993, `os_fsync_impl` |
| CPython, `fcntl.fcntl(fd, fcntl.F_FULLFSYNC)` | `F_FULLFSYNC` | flushes the drive | `Modules/fcntlmodule.c` lines 639 to 640 export the constant |
| Go 1.24.0 and 1.27.2, `os.File.Sync` | `F_FULLFSYNC` | flushes the drive | `internal/poll/fd_fsync_darwin.go` line 22 |
| Go, `syscall.Fsync` | `fsync()` | stops at the drive cache | `syscall/zsyscall_darwin_arm64.go` lines 710 to 716 |

All four rows were verified from the source at the named tags by this course's research. If `F_FULLFSYNC` returns `ENOTSUP`, for example on an SMB mount, Go falls back to plain fsync. The history of both Go changes, and an open CPython request to change `os.fsync`, are in the references.

**This is why the lab uses two calls.** `shared/durable.py` makes every durable sync of the course. On macOS it calls `fcntl(fd, F_FULLFSYNC)`. On Linux it calls `os.fsync`, because Linux has no `F_FULLFSYNC`, and the file system sends the drive's flush command itself. On Linux, write barriers are the file system option that makes it send that command. They are not the Apple barrier described above. The PostgreSQL 17 docs, section 28.1, name ZFS and ext4 as examples of file systems that can send it. The same section says that behind a controller with a battery-backed cache, turning write barriers off can regain speed, and that the battery must then remain functional. XFS is not named there, and this course did not check it. Here is the decision, from `durable.py:92`:

```python
# from shared/durable.py:92, plan(). Docstring removed, logic unchanged
    if mode not in SYNC_MODES:
        raise ValueError(f"unknown sync mode {mode!r}, expected one of {SYNC_MODES}")
    platform = platform or sys.platform
    if mode == "none":
        return "none"
    if mode == "full" and platform == "darwin":
        return "F_FULLFSYNC"
    return "fsync"
```

`durable_sync` follows Go's rule for `ENOTSUP` and falls back to plain fsync. Unlike Go, it prints a warning once, because the guarantee is now weaker.

**Other software on your Mac makes the same choice.** Two examples you may run every day:

- **SQLite.** `PRAGMA fullfsync` decides whether SQLite uses `F_FULLFSYNC`. "The default value of the fullfsync flag is off." `PRAGMA checkpoint_fullfsync` does the same for checkpoints only, and is also off by default. Verified from sqlite.org, "Pragma statements". So upstream SQLite with default settings uses plain fsync on a Mac, per `full_fsync()` in its `os_unix.c`. The build that Apple ships with macOS was not checked.
- **A Linux virtual machine.** Docker Desktop and similar tools run Linux containers inside a virtual machine on the Mac. A guest's fsync reaches the Mac's drive only as far as the virtual disk lets it. Apple's Virtualization framework offers three modes for a disk image. `full` "Synchronizes data to the permanent storage holding the disk image". `fsync` uses "the system's best-effort synchronization mode". `none` "Disables data synchronization". Verified from Apple's developer documentation for `VZDiskImageSynchronizationMode`. Which mode Docker Desktop and other tools choose was not checked. So a PostgreSQL container on a Mac has a boundary that depends on that tool's choice. Treat it as a development database.

**What it costs.** The two calls differ by more than an order of magnitude on both Macs. Each machine's numbers are given with its own conditions:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One small write, then a sync. Median per run. Log scale: 10 characters   │
│ per factor of 10, starting at 1 µs                                       │
├──────────────────────────────────────────────────────────────────────────┤
│                    1 µs      10 µs     100 µs    1 ms                    │
│ M2, os.fsync       ████████████████████                   95 to 110 µs   │
│ M2, F_FULLFSYNC    ███████████████████████████████████    2.85-2.88 ms   │
│ M4 Pro, os.fsync   ██████████████                         25.1, 31.2 µs  │
│ M4 Pro F_FULLFSYNC ████████████████████████████████████   about 4.0 ms   │
│                                                                          │
│ M2: elite-performance 5.6, 4 KiB write, 2026-09-25. Ratio 26 to 30x      │
│ M4 Pro: this course's research, Python 3.9.6, 8 KB pwrite, macOS 26.6,   │
│ 2026-10-17.                                                              │
│ 4,001 / 31.2 = 128x and 4,012 / 25.1 = 160x                              │
└──────────────────────────────────────────────────────────────────────────┘
```

The research also measured Go's `os.File.Sync` on the M4 Pro at 3,981 to 4,078 µs per operation. That matches `F_FULLFSYNC`, as the Go source predicts.

**PostgreSQL on a Mac.** PostgreSQL chooses its WAL sync call with `wal_sync_method`. It has five values:

| Value | What PostgreSQL does after a WAL write |
|---|---|
| `open_datasync` | opens the WAL file with `O_DSYNC`, so each write returns only when the data is synced |
| `fdatasync` | calls `fdatasync()`, which skips file metadata that is not needed to read the data back |
| `fsync` | calls `fsync()` |
| `fsync_writethrough` | asks the drive to write through its cache. On macOS that is `fcntl(fd, F_FULLFSYNC)` |
| `open_sync` | opens the WAL file with `O_SYNC`, which also waits for all of the file's metadata |

Verified from the PostgreSQL 17 docs, section 19.5, and `issue_xlog_fsync` and `get_sync_bit` in `xlog.c` at REL_17_11, from lines 8739 and 8649. The `F_FULLFSYNC` call is in `pg_fsync_writethrough`, `fd.c` line 466. The notes on metadata come from the Linux `open(2)` man page for `O_SYNC`, and the MySQL 8.4 manual's entry for `innodb_use_fdatasync`. The default is the first supported method in a fixed list, except that Linux and FreeBSD use `fdatasync`. On macOS that rule picks `open_datasync`. Verified from the docs and from `xlogdefs.h` lines 75 to 81 at REL_17_11. A fresh PostgreSQL 14.24 cluster on the M4 Pro showed `open_datasync` with source `default`. That was a Homebrew x86_64 build under Rosetta. The same source logic gives `open_datasync` on 17. That is inferred from the code, and not run on 17. The PostgreSQL 17 docs, section 28.1, say that on macOS you set `fsync_writethrough` to prevent write caching. `pg_test_fsync -s 3` from PostgreSQL 14.24 on the same Mac measured this, one 8 kB write per operation:

| `wal_sync_method` | ops/sec | µs per op | flushes the drive cache |
|---|---|---|---|
| `open_datasync`, the macOS default | 45,480 | 22 | no, inferred |
| `fdatasync` | 42,027 | 24 | no, inferred |
| `fsync` | 40,138 | 25 | no |
| `fsync_writethrough` | 250 | 3,994 | yes, inferred |
| `open_sync` | 42,435 | 24 | no, inferred |
| write, no sync | 333,548 | 3 | no |

The "yes, inferred" comes from `HAVE_FSYNC_WRITETHROUGH` in PostgreSQL's `darwin.h`, line 6, and from the 3,994 µs, which matches `F_FULLFSYNC`. The `fsync` row is backed by Apple's `fsync(2)`. The three "no, inferred" rows come from their timing, which is close to plain fsync. Apple's `open(2)` page does not describe `O_DSYNC` or `O_SYNC`. The PostgreSQL 18 default on macOS is also `open_datasync`, verified from the same macro logic in `xlogdefs.h` at REL_18_6, and not run.

Two details change how you read this table on PostgreSQL 17:

1. **The setting reaches the data files too.** At a checkpoint, PostgreSQL syncs the data files with `pg_fsync`. On macOS, `pg_fsync` uses `F_FULLFSYNC` only when `wal_sync_method = fsync_writethrough`. Otherwise it calls plain `fsync()`. Verified from `fd.c` lines 426 to 431 at REL_17_11. So with the default, the checkpoint's data file syncs do not flush the drive cache. That the WAL writes with `O_DSYNC` also do not is inferred from the 22 µs timing.
2. **The 17 tool tests a slightly different path.** On macOS, `pg_test_fsync` 17 opens its file for the `open_datasync` and `open_sync` rows with `F_NOCACHE`, which bypasses the macOS file cache. Verified from `pg_test_fsync.c` lines 269 to 277 at REL_17_11. The server itself uses that flag for WAL only with the developer setting `debug_io_direct`. Verified from `get_sync_bit`, `xlog.c` line 8659. So on 17 those two rows may differ from the server's real WAL path. The size of the difference was not measured. The 14.24 tool in the table above did not use the flag on macOS.

So a default PostgreSQL 17 on your Mac commits in microseconds, about 22 µs on the M4 Pro with the 14.24 tool. Those commits are not promised to survive a power cut. That is fine for a development laptop. It is a wrong model for a production server.

**Disks that report early.** `F_FULLFSYNC` asks the drive to flush. It cannot make the drive do it. The PostgreSQL 17 docs, section 28.1, warn that consumer IDE and SATA drives are particularly likely to have write-back caches that do not survive a power failure. They add that many SSDs do not honor cache flush commands by default. The best measurement is older. Zheng, Qin, Tucek and Lillibridge published it at USENIX FAST 2013. They cut the power to 15 SSDs of 10 models from 5 vendors, with flushes issued. 13 of the 15 showed failures. Only two SSDs of one model, and one enterprise hard disk, behaved as the flush promised. Verified from the paper, abstract and section 1. The drives date from about 2012, and modern NVMe drives were not tested. So a flush is a request, and only a power-cut test of the device you own shows what it does.

**From fsync to the device on a Linux server.** Production runs on Linux, so here is what one fsync becomes on the way down. The Linux block layer gives a file system two tools. `REQ_PREFLUSH` asks the device to flush its volatile cache before a write starts. `REQ_FUA`, forced unit access, marks a write that may complete only when the data is on non-volatile storage. Verified from the kernel document `block/writeback_cache_control` at tag v6.12. Here is the path for ext4 on an NVMe drive:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One fsync on ext4 with barriers on, no async_commit and no fast_commit,  │
│ NVMe drive. Linux v6.12 source                                           │
├──────────────────────────────────────────────────────────────────────────┤
│ fsync(fd)                                                                │
│   │  ext4_sync_file: wait for the journal commit                         │
│   ▼                                                                      │
│ jbd2 commit block    written with REQ_PREFLUSH | REQ_FUA                 │
│   │                  fs/jbd2/commit.c 152-154                            │
│   │  if that commit will send no flush: an empty flush instead,          │
│   │  blkdev_issue_flush, fs/ext4/fsync.c 111-113 and 171                 │
│   ▼                                                                      │
│ block layer          drive reports a volatile write cache?               │
│   ├── yes: send a separate flush first, then the write with FUA          │
│   └── no:  finish an empty flush at once, strip PREFLUSH and FUA         │
│   ▼                                                                      │
│ NVMe driver          a flush becomes the NVMe Flush command, core.c 812  │
│                      REQ_FUA sets the FUA bit of the write, core.c 981   │
│   ▼                                                                      │
│ drive                writes its cache to flash, then completes           │
└──────────────────────────────────────────────────────────────────────────┘
```

The branch in the middle is set by one test in the NVMe driver. The driver tells the block layer that the drive has a write cache and supports FUA only if the drive reports a volatile write cache:

```c
/* drivers/nvme/host/core.c, lines 2188 to 2191, Linux v6.12 */
	if (ns->ctrl->vwc & NVME_CTRL_VWC_PRESENT)
		lim.features |= BLK_FEAT_WRITE_CACHE | BLK_FEAT_FUA;
	else
		lim.features &= ~(BLK_FEAT_WRITE_CACHE | BLK_FEAT_FUA);
```

For a device with no volatile cache, "the block layer completes empty REQ_PREFLUSH requests before entering the driver and strips off the REQ_PREFLUSH and REQ_FUA bits". For a device with a cache but no FUA support, the block layer sends a flush after the write instead. Verified from the same kernel document. So the journal commit costs one flush and one FUA write on a drive with a cache. It costs no flush at all on a drive that reports none.

What this means for you:

- **fsync is cheaper on a drive that reports no cache, because no flush is sent.** That is inferred from the block layer code, and not measured. It is safe only if that drive really keeps written data through a power loss.
- **Power-loss protection.** Enterprise SSDs with power-loss protection, PLP for short, are sold as keeping their cache through a power loss. Whether a PLP drive reports a volatile write cache was not checked. The driver code only shows what the kernel does with that report. The PLP claim itself was not checked either. Check a drive with `nvme id-ctrl -H /dev/nvme0` from the `nvme-cli` package, and read bit 0 of `vwc`. With `-H` it prints "Volatile Write Cache Present" or "Not Present". The other bits of `vwc` describe the Flush command, so a nonzero value alone does not mean a cache.
- **A RAID controller** with a battery-backup unit, BBU, keeps its cache in a power loss too. Section 1.4 gives the limit of that promise for torn pages.
- **ext4 needs barriers on.** The flush and FUA flags above are sent only when the journal has `JBD2_BARRIER` set, which is the `barrier` mount option, and no `async_commit`. Verified from `commit.c` lines 152 to 154. With `fast_commit` on, ext4 takes another path, per `fs/ext4/fast_commit.c` lines 1214 and 1215. This phase does not follow that path.

These are the checks, all for Linux:

| What you check | Command | What it tells you | Source |
|---|---|---|---|
| the kernel's view of the drive cache | `cat /sys/block/nvme0n1/queue/write_cache` | `write back` or `write through`. Writing to the file changes only the kernel's view, not the device | kernel ABI, `sysfs-block` |
| what an NVMe drive reports | `nvme id-ctrl -H /dev/nvme0`, bit 0 of `vwc` | whether the drive says it has a volatile write cache | `nvme-cli` source, `nvme-print-stdout.c` at v2.11. The driver test above reads the same bit 0 |
| a SATA drive's cache | `hdparm -I /dev/sda` | a `*` next to "Write cache" means it is on | PG 17 docs, 28.1 |
| a SCSI or SAS drive's cache | `sdparm --get=WCE /dev/sdb` | whether the write cache is enabled | PG 17 docs, 28.1 |
| the real flush cost | `pg_test_fsync -f /path/on/the/wal/disk/test.out` | the time per sync method, on the WAL file system | PG 17 docs, `pg_test_fsync` |
| whether flushed data survives | `diskchecker.pl`, with a real power cut | the docs name it as a test of reliable I/O | PG 17 docs, 28.1 |

The `sysfs-block` ABI file warns about one change. Setting `write_cache` from `write back` to `write through` "will also eliminate cache flushes issued by the kernel." Verified from the `sysfs-block` ABI file. So a drive with a volatile cache then gets no flush commands, and fsync can return while the data is still in that cache.

**Network file systems, direct I/O and cloud volumes.** These places hide a weaker flush, or change which call does the work:

- **NFS.** The PostgreSQL 17 docs, section 18.2.2.1, require the `hard` mount option. They also recommend the `sync` export option on the server. Without it, an fsync on the client "is not actually guaranteed to reach permanent storage on the server". The docs compare that to running with `fsync` off.
- **`O_DIRECT`.** It moves data straight between user memory and the device, past the page cache. The Linux `open(2)` man page says it "does not give the guarantees of the O_SYNC flag". So direct I/O alone is not a durable write. A store that uses it still needs a sync.
- **PostgreSQL and direct I/O.** Only one case used direct I/O for WAL: the `open_sync` and `open_datasync` methods with `wal_level=minimal`. PostgreSQL 16 stopped that. Direct I/O is now behind the developer setting `debug_io_direct=wal`. Verified from the 16.0 release notes, from `get_sync_bit` at REL_14_0 for the old case, and from `get_sync_bit` in `xlog.c`, line 8659 at REL_17_11, for the new rule. PostgreSQL 18 added asynchronous I/O, set by `io_method`. The 18.0 release notes list reads only, such as sequential scans and vacuum. So it does not change the commit path. That is inferred from that list. PostgreSQL 17 has no `io_method`.
- **MySQL 8.4 and direct I/O.** MySQL 8.4 changed the Linux default of `innodb_flush_method` from `fsync` to `O_DIRECT`, "if supported". With `O_DIRECT`, InnoDB "uses O_DIRECT ... to open the data files, and uses fsync() to flush both the data and log files". 8.4 also turned `innodb_use_fdatasync` on, which "permits using fdatasync() instead of fsync()". Verified from the MySQL 8.4 manual, "What Is New in MySQL 8.4", Table 1.1, and "InnoDB Startup Options and System Variables". So InnoDB 8.4 skips the page cache and still syncs, which is the rule of the bullet above.
- **Cloud block volumes.** What a flush on a cloud volume promises was not checked. No first-party statement was found for Amazon EBS or Google Persistent Disk. Treat it as a question for your provider, and test it. Its cost is documented. Amazon EBS gp3 gives "single-digit millisecond latency", with 3,000 IOPS included. IOPS means I/O operations per second. io2 Block Express is "designed to deliver an average latency of under 500 microseconds for 16KiB I/O operations". Verified from the AWS EBS User Guide pages "Amazon EBS volume types" and "General Purpose SSD volumes". So one WAL flush on gp3 likely takes 1 to 9 ms. This phase uses 1 ms, the best case of that range. That is about 45 times the 22 µs default commit on the M4 Pro: 1,000 / 22 = 45. That is inferred from the latency statement, and not measured. Section 1.6 shows why that makes group commit matter more on a cloud volume. Run `pg_test_fsync` on the volume to get the real number.

**MySQL 8.4 defaults that touch durability.** If you run MySQL, these are the InnoDB defaults to read with this phase. MySQL 8.4 is the long-term support release that follows 8.0:

| Variable | 8.0 default | 8.4 default | What it changes | Section |
|---|---|---|---|---|
| `innodb_flush_log_at_trx_commit` | 1, inferred | 1 | "The default setting of 1 is required for full ACID compliance." | 1.2 |
| `sync_binlog` | 1, inferred | 1 | sync of the binary log at each commit | 1.6 |
| `innodb_flush_method` on Linux | `fsync` | `O_DIRECT` if supported | data files skip the page cache, and are still synced | 1.3 |
| `innodb_use_fdatasync` | `OFF` | `ON` | `fdatasync()` in place of `fsync()` | 1.3 |
| `innodb_log_buffer_size` | 16 MiB | 64 MiB | the memory buffer for redo before it is written | 1.2 |
| `innodb_doublewrite_files`, `innodb_doublewrite_pages` | two per buffer pool instance, 4 | 2, 128 | the torn page copy | 1.4 |
| `innodb_io_capacity` | 200 | 10000 | the I/O rate InnoDB assumes for background page flushing | 1.5 |

Verified from the MySQL 8.4 manual, "What Is New in MySQL 8.4", Table 1.1, and "InnoDB Startup Options and System Variables". `sync_binlog` is from "Binary Logging Options and Variables". The two 8.0 values marked inferred are not in Table 1.1, which lists the changed defaults, so they are taken as unchanged. The commit settings did not change. The flush path did. So an 8.4 server on Linux uses direct I/O plus a sync for its data files, where 8.0 used the page cache plus a sync.

**Linux: the error that a retry hides.** Craig Ringer reported a problem on the pgsql-hackers list in March 2018. PostgreSQL retried fsync after an I/O error. On Linux that error is `EIO`, the error code for a failed read or write on the device. He found that the retry succeeded because the first failed fsync had cleared the error flag. The data was gone, and the second fsync reported success. Verified from the thread, sent 2018-03-28. This became known as fsyncgate. Rebello and others measured it at USENIX ATC 2020, on Linux 5.2.11. After a failed fsync, ext4, XFS and Btrfs all mark the failed pages clean. So a retry does not write them again. ext4 and XFS keep the new data in the page cache. So a read still returns it, while the disk does not have it. Btrfs goes back to the old data. ext4 in `data=journal` mode reports the error one fsync late. Verified from the paper, Table 1 and section 3.3. In the same study, Redis 5.0.7 did not check the return code of fsync at all.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ fsyncgate, the sequence that loses an acknowledged write on Linux        │
├──────────────────────────────────────────────────────────────────────────┤
│ 1  write B          B in the page cache, page dirty                      │
│ 2  fsync            the device fails the write: EIO                      │
│                     the kernel marks the page clean, B is not on disk    │
│ 3  fsync again      nothing dirty, returns 0: "success"                  │
│ 4  reply OK for B   ◄── an acknowledgment for data the disk lacks        │
│ 5  reads of B       still served from the page cache, until eviction     │
│ 6  reboot           B is gone                                            │
└──────────────────────────────────────────────────────────────────────────┘
```

**The fix.** PostgreSQL fixed this in five releases on 2019-02-14: 11.2, 10.7, 9.6.12, 9.5.16 and 9.4.21. A PANIC is PostgreSQL's most severe error level. It stops the whole server at once, and the next start runs crash recovery.

- By default, the server now raises a PANIC on a failed data file flush. It does not retry.
- A new parameter, `data_sync_retry`, restores the old behaviour. Its default is `off`. The docs for versions 14, 17 and 18 describe it the same way.
- After the PANIC, crash recovery replays the WAL and rewrites the data pages.

Verified from the five release notes and the docs pages. A fresh 14.24 cluster on the M4 Pro showed `data_sync_retry = off`, source `default`. The PostgreSQL 17 sample file has the same default, line 824.

**Why the rule still applies.** Linux changed in version 4.13. Since then, a write-back error is reported to every file descriptor that might have written the data. Verified from the Linux `fsync(2)` man page. But Rebello's tests ran on Linux 5.2.11, after this change. They still found the clean pages. So the PANIC rule still applies.

**What you see in the log.** Two code paths raise this PANIC on PostgreSQL 17:

| What failed | Message | Raised when | Source at REL_17_11 |
|---|---|---|---|
| a data file sync, at a checkpoint | `could not fsync file "%s": %m` | at level PANIC while `data_sync_retry = off` | `sync.c` lines 444 to 447, `data_sync_elevel` in `fd.c` line 3938 |
| a WAL sync, at a commit | `could not fsync file "%s": %m`, `could not fdatasync file "%s": %m`, or with `fsync_writethrough` `could not fsync write-through file "%s": %m` | always PANIC, whatever `data_sync_retry` says | `issue_xlog_fsync`, `xlog.c` lines 8790 to 8800 |

`%m` is replaced by the system's error text, such as "Input/output error" for `EIO`. That text is inferred from the C library, and not run. So this line points at the device or the file system, not at PostgreSQL. That is inferred from the code path. Look at `dmesg` on the host for the device error at the same time. On RDS or Aurora you cannot run `dmesg`, and the provider handles the device. What RDS logs for a storage fault was not checked.

The lab store follows the PANIC rule. Here is the wrong way, kept in the code only for its self-test, and the right way, from `kvlog.py:460`:

```python
# from phase01_durability/kvlog.py:460, _sync_log_locked(). Comments changed, logic unchanged
        try:
            self.fs.sync(LOG, self.sync_mode)
        except OSError as exc:
            if self.rules.panic_on_sync_error:
                # RIGHT: never retry, never acknowledge, stop the store.
                self._fail(exc)
                raise StoreFailed(f"sync failed: {exc}") from exc
            # WRONG: the old PostgreSQL behaviour. The retry "succeeds".
            self.fs.sync(LOG, self.sync_mode)
        self.synced_to = self._written_to
        self.syncs += 1
```

E9 runs both on the simulated Linux file system of `fsim.py`. Three puts of 1,230 bytes each, and the second put's sync fails. The expected result comes from the arithmetic of the entry sizes. It was not run:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ kvlog.py --fsync-error-demo, expected shape. Not run by the author yet   │
├──────────────────────────────────────────────────────────────────────────┤
│ WRONG, retry after EIO                                                   │
│   acknowledged: order:1041, order:1042, order:1043                       │
│   after power loss: order:1041 only                                      │
│   the disk holds 1,230 good bytes, 1,230 zero bytes, then order:1043     │
│   recovery stops at offset 1230: impossible lengths ksz=0 vsz=0,         │
│   2460 bytes dropped. Two acknowledged puts are lost                     │
│                                                                          │
│ RIGHT, stop after EIO                                                    │
│   acknowledged: order:1041. order:1042 and order:1043 get StoreFailed    │
│   after power loss: order:1041. Nothing acknowledged is lost             │
└──────────────────────────────────────────────────────────────────────────┘
```

One limit stays. In the RIGHT case, a restart without a reboot reads the log through the page cache. The page cache still shows `order:1042`, which the disk does not have. The demo prints that line too. The lab's recovery trusts what the operating system returns, so it would accept `order:1042` until the page is evicted. This follows from Rebello's Table 1 for ext4 and XFS. Rebello also found that PostgreSQL lost data under the ext4 `data=journal` behaviour, because that error came one fsync late. A store that must survive this case needs to rewrite or verify the log tail it cannot prove durable. The lab does not do that.

**One more sync: the directory.** A file's name lives in its directory, and the directory is a file too. fsync on a file does not promise that the file's name is durable. The ALICE study, Pillai and others, OSDI 2014, tested 11 applications on Linux file systems. Developers acted on five of the problems it found. Three of the five were a missing fsync on the parent directory after a file was created. Verified from page 12 of the paper. So the store syncs its directory after it creates the log, at `kvlog.py:348`. It does the same after each checkpoint rename, in `checkpoint()`. Section 1.7 shows what the crash matrix finds without the first of those syncs.

Now the sync has returned, and the whole entry is on stable media. But a crash can also come while the entry is still being written. The next section is about that half-written entry.

**The sentence to remember:** on macOS only `F_FULLFSYNC` asks the drive to flush. On Linux, a retry after a failed fsync can report success for lost data, so stop instead.

**The trap:** calling `os.fsync` in Python on a Mac and calling the result durable. Every benchmark then looks fast, and a power cut loses the last writes.

**Try this now:** run `uv run python shared/durable.py --measure 200`. Predict the ratio of `full` to `fsync` at the median first. Then compare it with the row for your machine in the cost diagram above.

---
## 1.4 — Torn writes and checksums (the page written halfway, and how the recovery code notices)

Why this matters: a sync makes a whole write durable once it returns. But a power loss can come while the write is still on its way to the media. Then part of the write is on disk and part is not. If recovery reads that half-written entry as data, the store serves bytes that nobody wrote.

**Answer this first.** The store writes a second version of `order:1041`. The entry is 1,230 bytes, at file offsets 1230 to 2460. The power fails while it is in flight. The drive wrote every 512-byte sector of the entry except the one in the middle, which still reads as zeros. The file length covers the whole entry. What does recovery return for `order:1041` if it checks only the lengths?

**The mental model.** A torn write, also called a partial write, is a write that only partly reached the disk. The device writes in units called sectors, and a large write spans many of them. The PostgreSQL 17 docs, section 28.1, say sectors are commonly 512 bytes. They add that PostgreSQL usually writes 8,192 bytes, or 16 sectors, at once. A power loss can leave some of those sectors written and others not. SQLite's document on atomic commit, section 2, says SQLite has long assumed that a single sector write is not atomic.

A torn write has two shapes, and they need different checks:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The second put of order:1041, 1,230 bytes at offsets 1230 to 2460.       │
│ The short cut at 1930 is an example: 700 of the 1,230 bytes arrived      │
├──────────────────────────────────────────────────────────────────────────┤
│ intact     │hdr│key│ value ................................... │         │
│            1230                                               2460       │
│                                                                          │
│ short      │hdr│key│ value .........│        the file ends early         │
│            1230                    1930     a length check catches it    │
│                                                                          │
│ hole       │hdr│key│ value ...│ 0 0 0 0 0 0 │ value ......... │          │
│            1230              1536          2048              2460        │
│            the length is right. Only a checksum catches it               │
└──────────────────────────────────────────────────────────────────────────┘
```

**The details of the hole.** `fsim.py` zeroes the sector that holds the middle byte of the in-flight write. For this entry the middle byte is at 1230 + 1230 / 2 = 1845. That sector starts at 1845 // 512 × 512 = 3 × 512 = 1536. It ends at 2048. The value starts after the 20-byte header and the 10-byte key, at offset 1260. So the 512 zero bytes fall inside the value, and the header is intact. A reader that checks only the lengths sees a valid entry with the right key.

Real drives produce both shapes. In the FAST 2013 study by Zheng and others, three SSDs showed shorn writes. In a shorn write, only part of a 4 KB record reached the disk. Three SSDs showed bit corruption. Verified from the paper, Table 5 and section 5.3.

**A checksum.** A checksum is a short value computed from a block of bytes and stored next to it. A reader computes it again and compares. If one byte changed, the values differ. The lab stores a CRC-32 in each entry's first 4 bytes, computed over every byte after it. Suppose the damage looks random to the CRC. Then the chance that a damaged entry still matches is 1 in 2^32, or 1 in 4,294,967,296. That figure assumes random damage. It is inferred from the size of the CRC, and not checked against a model of real drive failures.

The parser checks in a fixed order. It checks the lengths before it uses them, so a damaged length cannot make it read gigabytes. Then it checks the CRC. From `kvlog.py:206`:

```python
# from phase01_durability/kvlog.py:206, parse(). Docstring and the last three lines removed, checks unchanged
    if len(buf) - pos < HEADER_SIZE:
        return None, f"short header, {len(buf) - pos} of {HEADER_SIZE} bytes"
    crc, seq, ksz, vsz = HEADER.unpack_from(buf, pos)
    if ksz == 0 or ksz > MAX_KEY or (vsz != TOMBSTONE and vsz > MAX_VALUE):
        return None, f"impossible lengths ksz={ksz} vsz={vsz}"
    vlen = 0 if vsz == TOMBSTONE else vsz
    end = pos + HEADER_SIZE + ksz + vlen
    if end > len(buf):
        return None, f"short entry, {len(buf) - pos} of {end - pos} bytes"
    if verify_crc and zlib.crc32(buf[pos + 4:end]) != crc:
        return None, "checksum mismatch"
```

**The recovery rule.** Recovery reads entries from the start of the scan. At the first entry that fails any check, it stops. It treats that point as the end of the log, cuts the file there, and syncs the cut. It also refuses an entry whose sequence number is not the next one. A put that was in flight was never acknowledged, so dropping it breaks no promise.

E8 runs this case twice in memory, with the CRC check off and on. Its output answers the question at the start of this section. The expected output comes from the offsets above. It was not run:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ kvlog.py --torn-demo, expected shape. Not run by the author yet          │
├──────────────────────────────────────────────────────────────────────────┤
│ WRONG verify_crc off: get(order:1041) returned 1200 bytes, 512 of them   │
│       zero, served as data. 2 entries replayed                           │
│ RIGHT verify_crc on:  stopped at offset 1230: checksum mismatch,         │
│       1230 bytes dropped. get(order:1041) returned the earlier value,    │
│       starting 'order:1041:v1:'                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**How PostgreSQL handles a torn data page.** PostgreSQL protects its 8 kB data pages in a different way. `full_page_writes = on` is the default in versions 14, 17 and 18. With it, the first change to a page after a checkpoint writes the whole page into the WAL. That copy is called a full page image. If a crash tears that page on disk, replay writes the full image back. Verified from the PostgreSQL 17 docs, section 19.5, and the 17 sample file, line 240. The docs allow turning it off only on a file system that prevents partial page writes. Their example is ZFS.

Two places where you meet this setting:

- **A battery-backed controller is not enough.** The docs warn: "Battery-Backed Unit (BBU) disk controllers do not prevent partial page writes unless they guarantee that data is written to the BBU as full (8kB) pages." Verified from the PostgreSQL 17 docs, section 28.1, `wal.sgml` lines 178 to 180 at REL_17_11. So a BBU is not a reason to turn `full_page_writes` off.
- **On RDS you cannot turn it off.** AWS states: "In RDS for PostgreSQL, full page writes are always "on."" Verified from the AWS page "IO:WALWrite" for RDS for PostgreSQL. It is a vendor page. So on RDS the page-image cost of section 1.5 is fixed. Your only levers are the checkpoint interval and `wal_compression`. That is inferred.

There is direct evidence of what happens when it is off. Ramos and others built LazyFS, a file system that runs as a normal program. It uses FUSE, the interface that lets a user program act as a file system. It has its own page cache, and it can lose or tear writes on command. They tore a PostgreSQL data page write, with the full page setting off and on, on PostgreSQL 12.11 and 15.2. The paper describes the setting and cites the `full_page_writes` docs. In both cases the server restarted without an error. With the setting off, the `amcheck` module, which checks the structure of tables and indexes, then reported corruption. Verified from "When Amnesia Strikes", PVLDB volume 17, issue 11, 2024, the paragraph "Protection and recovery" and the table of systems. Section 1.7 uses LazyFS again as a test tool.

**The same problem in InnoDB.** MySQL's InnoDB solves the torn page in another way. It writes each page that leaves the buffer pool to a doublewrite buffer first. Only then does it write the page to its place in the data file. After a crash during a page write, InnoDB "can find a good copy of the page" in that buffer. Verified from the MySQL 8.4 manual's page "Doublewrite Buffer".

| Engine | Where the extra copy goes | Extra cost |
|---|---|---|
| PostgreSQL | into the WAL | one extra page write |
| InnoDB | into a second file, the doublewrite buffer | one extra page write |

**The InnoDB defaults in MySQL 8.4.** `innodb_doublewrite` has the default `ON`. Its value `DETECT_ONLY` writes only metadata and does not repair a torn page. Verified from the MySQL 8.4 manual, "InnoDB Startup Options and System Variables" and "Doublewrite Buffer". The earlier version of this phase said the manual gives no exact default. The parameters page does give it, so that sentence was wrong. 8.4 also changed how the buffer is laid out. `innodb_doublewrite_files` became 2, where 8.0 used two per buffer pool instance. `innodb_doublewrite_pages` became 128, where 8.0 used the value of `innodb_write_io_threads`, 4 by default. Verified from "What Is New in MySQL 8.4", Table 1.1. Since 2026-04-21, MySQL 8.0 has only Oracle Sustaining Support, per the MySQL end-of-life notice. So 8.4 is the version to read these defaults for.

**A device can remove the problem.** AWS documents torn write prevention for EC2. With it, the device writes a block all or nothing. AWS says this removes the need for the doublewrite buffer. AWS also states two gains: transactions per second can rise by up to 30 percent, and write latency can fall by up to 50 percent. Verified from the EC2 User Guide page "Torn write prevention". It is a vendor page. The supported block sizes and volume types were not checked, because that sub-page did not load. Linux 6.11 added a matching write flag, `RWF_ATOMIC`, per this course's currency research. Whether PostgreSQL 17 or MySQL 8.4 use it was not checked.

**A storage service can remove the problem too.** On Aurora and AlloyDB, the database host does not write data pages at all. It sends only WAL records to a storage service, and that service builds the pages:

- The Aurora paper says: "In Aurora, the only writes that cross the network are redo log records. No pages are ever written from the database tier". Verified from Verbitski and others, SIGMOD 2017, section 3.2. The paper describes the MySQL-compatible engine.
- Google says that in AlloyDB "the compute layer only communicates the WAL records to the storage layer". So there is no reason "to send complete database blocks to the storage layer", and the post names the torn pages problem as one such reason. Verified from the Google Cloud blog post of 2022-05-12 on AlloyDB storage. It is a vendor post.

So on these systems the torn page problem moves into the storage service. It still exists there, and you cannot test it. That move is inferred from the two sources. Section 1.5 shows what else moves.

**Data checksums.** Data checksums are a separate feature. They detect a damaged data page when it is read. Their default depends on the version that ran `initdb`:

| Version | `initdb` default | Evidence |
|---|---|---|
| 14 and 17 | off, unless `initdb -k` | `initdb.c` line 167: `static bool data_checksums = false;` at REL_17_11. PG 17 docs, section 28.2 |
| 18 | on. `--no-data-checksums` turns them off | `initdb.c` line 167 is `true` at REL_18_6. The 18.0 release notes list it under incompatibilities |

The 18.0 release notes, dated 2025-09-25, also say that `pg_upgrade` needs matching checksum settings in the old and new clusters. So a 17 cluster made with default settings needs a decision before it moves to 18. There are two ways out:

1. Make the new 18 cluster with `initdb --no-data-checksums`.
2. Turn checksums on in the old cluster with `pg_checksums --enable`. It refuses a running server with the message "cluster must be shut down". Verified from `pg_checksums.c` lines 439 and 570 at REL_17_11. It rewrites every data page, so the downtime grows with the cluster size. That cost is inferred, and not measured.

The same holds for a 14 cluster. PostgreSQL 14 reaches its final release on 2026-11-12, per the PostgreSQL versioning page. Run `show data_checksums;` to see your cluster's setting. E11 does it. Whether RDS and Aurora clusters have checksums on was not checked. The same `show` command answers it on your instance.

Two facts decide that choice: what checksums cover, and what they cost.

**What they cover.** In versions 14, 17 and 18, checksums cover data pages only. "Only data pages are protected by checksums; internal data structures and temporary files are not." Verified from the PostgreSQL 17 docs, section 28.2, and the 14 and 18 docs. Rogov, section 11.2, page 187, names three more limits:

- A page is checked only when it is read. So damage can sit unseen until it reaches every backup.
- A zeroed page counts as valid.
- Rogov says only the main fork of each table is covered. In the 17 source, `FlushBuffer` sets a checksum on every page it writes, at `bufmgr.c` line 3941, so free space map and visibility map pages are covered too. Files outside relations, such as `pg_xact`, are not.

**What they cost.** A hint bit is a cached flag in a row. It saves later readers a lookup, and Phase 3 explains it. With checksums on, "hint bit updates are always WAL-logged", per the PostgreSQL 17 docs, section 19.5. So the 18 default writes more full page images than the 17 default. That is inferred from the docs line. Its size is not measured here.

**How a failure shows.**

- `pg_stat_database.checksum_failures` counts failures, per the PostgreSQL 17 docs, section 27.2.
- The log shows a warning that starts "page verification failed, calculated checksum". An error "invalid page in block 0 of relation" follows. This is Rogov's example on page 188. The same texts are in PostgreSQL 17, `bufpage.c` line 152 and `bufmgr.c` line 1556. PostgreSQL 18 puts the relation path in double quotes, and can report several invalid blocks in one message.

**A torn page bug fixed in your minor release.** PostgreSQL 17.11 fixed a gap in this protection. The release note says: "We also failed to log full-page images of such VM pages when needed, potentially allowing torn page writes to go uncorrected." A VM page here is a page of the visibility map, which Phase 4 uses. Verified from `release-17.sgml` lines 1953 to 1966, in the 17.11 section. So run the latest 17 minor release. Check yours with `select version();`.

**The lab entry against a PostgreSQL WAL record.** A PostgreSQL WAL record solves the same problems as the lab's entry, with different fields. The header fields are from `xlogrecord.h` at tag REL_17_11, lines 41 to 53. The header is 24 bytes, against the lab's 20:

| The job | Lab entry, `kvlog.py` | PostgreSQL WAL record | Source |
|---|---|---|---|
| length | `ksz` and `vsz`, 4 bytes each | `xl_tot_len`, the length of the whole record | `xlogrecord.h` |
| checksum | `crc32`, IEEE CRC-32 over the bytes after it | `xl_crc`, a CRC-32C on every record | `xlogrecord.h`, PG 17 docs 28.1 |
| order | `seq` must be the next number | `xl_prev` must be the LSN of the record before. Else "record with incorrect prev-link" | `xlogreader.c` REL_17_11 line 1165 |
| end of log | `impossible lengths ksz=0 vsz=0` | "invalid record length at ...: expected at least 24, got 0" on 17. 14 and 15 print "wanted 24, got 0" | `xlogreader.c` REL_17_11 line 669. Rogov p. 175 for 14 |

The order check matters for one reason the lab does not have. PostgreSQL recycles old WAL files by renaming them, per Rogov, page 178. A recycled file still holds old records with valid CRCs. The reader refuses them by the `xl_prev` check, and by the page address check, at line 1330 of `xlogreader.c` at REL_17_11. On 17 it prints "unexpected pageaddr %X/%X in WAL segment %s, LSN %X/%X, offset %u". 14 says "in log segment %s, offset %u". The lab's sequence check does the same job for its own log. That match is inferred from the reader code. The wording change of the end-of-log message in the table was verified by comparing `xlogreader.c` at REL_15_0 and REL_16_0.

**Where the rule fails: damage in the middle.** "Stop at the first bad entry" is right for a torn tail. It is wrong for a bit flip in the middle of data that was already synced. Then recovery stops at the flipped entry, and drops every later entry, acknowledged ones too. This store's design cannot tell those two cases apart during the scan. Two things limit the damage. Reads check the CRC too, so a damaged synced entry is never served as data. And the boundary in section 1.7 says plainly that damage to synced data is not covered. PostgreSQL's redo also stops at the first invalid record and treats it as the end of the WAL. So it has the same blind spot. That is inferred from the reader logic. No PostgreSQL text read for this course says it.

The torn write is now caught, and the store knows where its log really ends. But it found that out by reading the whole log. The next section asks how long that read takes, and what makes it shorter.

**The sentence to remember:** a length check catches a short write. Only a checksum catches a write with the right length and the wrong bytes.

**The trap:** recovery that checks lengths only. A torn entry with an intact header passes, and the store serves bytes that no client wrote.

**Try this now:** run `uv run python phase01_durability/kvlog.py --torn-demo`. Match each number on the two output lines to an offset in the hole diagram above.

---
## 1.5 — Checkpoints and recovery (what runs on restart, how long it takes, and what bounds it)

Why this matters: after a crash, the store cannot serve a single read until recovery ends. Recovery time is downtime. A log that is never trimmed makes every restart slower than the one before. A checkpoint puts an upper limit on that time.

**Answer this first.** A PostgreSQL server crashes with about 1 GB of WAL written after the REDO point of its last completed checkpoint. The REDO point is where recovery starts, and this section defines it. Guess how long the redo takes: under a second, about 5 to 10 seconds, or several minutes.

**The mental model.** Crash recovery is the work a store does on restart. It builds a correct state from what is on disk. In a WAL database it is mostly replay: read the log and apply each change again. A checkpoint is a point in the log with a guarantee: every change before it is already saved outside the log. In this store, the saved copy is one index file. Recovery starts at the newest checkpoint, not at the start of the log. So the log written since that point bounds the recovery time. The second half of this section shows how PostgreSQL changes this rule.

PostgreSQL states the rule this way. Crash recovery looks at the latest checkpoint record to find the redo point in the WAL, and starts there. Changes made before that point are already on disk. Verified from the PostgreSQL 17 docs, section 28.5. The 14 docs give the same rule in section 30.5. The ARIES paper, section 6, describes a restart as three passes in order: analysis, redo and undo. Undo removes the changes of transactions that never committed. The lab store has no undo pass. One put is one entry, and it either passes its CRC or it is not there. PostgreSQL has no undo pass either, per Rogov, section 10.4, page 174. An unfinished transaction never gets a commit bit in `pg_xact`, so readers treat its rows as aborted. Phase 3 shows how they do that.

**What the lab store does on restart.** `Store.open` at `kvlog.py:331`, with `_recover` at `kvlog.py:356`, runs these steps in order:

- **Step 1.** Delete `keydir.ckpt.tmp` if it exists. A crash during a checkpoint left it, and the log has the same data.
- **Step 2.** If `keydir.ckpt` exists and its own CRC is good, load the keydir from it. The file also holds the log offset it covers and the last sequence number.
- **Step 3.** If the checkpoint covers more bytes than the log has, stop with `CorruptionError`. Only a broken WAL rule leads here.
- **Step 4.** Read the log from the covered offset to the end, and apply each entry to the keydir.
- **Step 5.** Stop at the first bad entry. Cut the file there and sync the cut.
- **Step 6.** Start accepting writes.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The lab's workload log after all 10 operations. Offsets in bytes         │
├──────────────────────────────────────────────────────────────────────────┤
│ 0                                   4920                            9900 │
│ ├── op 1 to op 4: four puts ────────┼── op 5 to op 10 ──────────────────┤│
│ │   4 × 1,230 = 4,920 bytes         │   2 deletes × 30 + 4 puts × 1,230 ││
│ │                                   │   = 4,980 bytes                   ││
│ │ in keydir.ckpt, not read again    │ read and replayed on restart      ││
│                                     ▲                                    │
│                         the checkpoint covers 0 to 4920                  │
│ restart reads 4,980 of 9,900 bytes: 50.3%. Without a checkpoint: 100%    │
└──────────────────────────────────────────────────────────────────────────┘
```

**Writing a checkpoint without breaking anything.** The checkpoint is a new file that replaces an old one. A crash can come at any step, so the order of steps matters. From `checkpoint()` at `kvlog.py:511`:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ checkpoint(): five steps, and what a power loss right after each leaves  │
├──────────────────────────────────────────────────────────────────────────┤
│ step                      why                       power loss after it  │
│ 1 sync the log            the WAL rule: the log     old checkpoint or    │
│                           is durable before the     none. Full scan      │
│                           file that depends on it                        │
│ 2 write keydir.ckpt.tmp   never overwrite the       same. The tmp file   │
│                           good file in place        is not durable       │
│ 3 sync the tmp file       its bytes are durable     same. Its name is    │
│                           before its name moves     not durable yet      │
│ 4 rename tmp to ckpt      one step replaces it      same, or new: the    │
│                                                     rename is not        │
│                                                     durable yet          │
│ 5 sync the directory      the rename is durable     new checkpoint       │
│                                                                          │
│ every row: the log holds all acknowledged puts, so no data is lost       │
└──────────────────────────────────────────────────────────────────────────┘
```

Each step protects against one failure. Skip step 3, and the rename can reach the disk before the file's bytes. Then the checkpoint is short or zero, its CRC fails, and recovery scans from offset 0. That costs time, not data, because the log is the source of truth. Skip step 5, and a power loss can bring back the old checkpoint. That also costs only time. Skip step 1, and the checkpoint can point past the end of the durable log. That is the one failure that the store cannot repair, so recovery refuses with `CorruptionError`. The self-test of `kvlog.py` removes step 1 with `sync="none"` and checks that the power image fails to open.

The checkpoint always uses the full sync, even when the store commits with `--sync none`. Checkpoints are rare, one per many puts, so their cost is small. A wrong checkpoint is corruption, while a slow one is only slow.

**Why recovery must cut the bad tail.** Suppose recovery stops at a torn entry but does not cut it. The next put lands after the garbage. The next recovery stops at the same garbage, and drops the new put, which was acknowledged. The self-test of `kvlog.py` runs exactly this double crash, with `truncate_tail` off. The cut is at `kvlog.py:402`, and it is synced before any new write.

**Where the lab model stops matching PostgreSQL.** The lab's checkpoint is one small file, written and renamed in a few steps. A PostgreSQL checkpoint must write every dirty page in shared memory to the data files. That can be gigabytes, and the server cannot stop for it. So PostgreSQL spreads the work over minutes, and that changes where recovery starts. The table lists the differences, and the paragraphs after it explain each row:

| Question | The lab store | PostgreSQL |
|---|---|---|
| what a checkpoint saves | the keydir, in one file | every page that was dirty when the checkpoint started |
| how it writes | five steps, three of them syncs | spread over `checkpoint_timeout` × `checkpoint_completion_target`, 4.5 minutes at the defaults |
| where recovery starts | the log offset stored in `keydir.ckpt` | the REDO point of the last completed checkpoint |
| work on restart | replay the log tail | redo from the REDO point, then one immediate checkpoint |

**A spread checkpoint, and its REDO point.** The checkpointer, from section 1.2, runs each checkpoint in three stages. Verified from Rogov, "PostgreSQL 14 Internals", section 10.3, pages 170 and 171:

- **Start.** The checkpointer fixes the checkpoint's REDO point at the current WAL position. On 17 it does so by writing a `CHECKPOINT_REDO` record, and the start of that record is the REDO point. Then it tags every buffer that is dirty at that moment. Tagging needs no I/O, so it is fast.
- **Writing.** It writes the tagged buffers to the data files, at a rate that ends the work after the configured fraction of the interval. Pages dirtied after the start are not tagged, so this checkpoint ignores them. A backend that writes a tagged buffer first also clears its tag.
- **Completion.** When every tagged buffer is written, the checkpointer writes a checkpoint record to the WAL, which holds the REDO point. Then it updates `pg_control`, the small file in `global/` that tells the startup process where to begin. The postmaster is the first process of the server. At start it launches the startup process, which runs recovery, per Rogov, page 173. Until then, `pg_control` keeps the previous checkpoint.

So the guarantee is narrower than "every change before the checkpoint is on disk". Every change before the REDO point is on disk, and that counts only once the checkpoint has completed. Rogov states the second half plainly: only from completion does the start of the checkpoint become the new starting point of recovery. CMU 15-445 calls this design a fuzzy checkpoint, because transactions keep running during it. Its Fall 2025 notes for Lecture 22 mark the two ends with a CHECKPOINT-BEGIN and a CHECKPOINT-END record. PostgreSQL 14 to 16 wrote no record at the start, so the REDO point could be the LSN of a record of any type, per Rogov, page 171. Since 17, an online checkpoint first writes a `CHECKPOINT_REDO` record, and its start LSN is the REDO point. Verified from `xlog.c` lines 7022 to 7035 at REL_17_11. A shutdown checkpoint writes no such record, because no WAL can come between its REDO point and its checkpoint record.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One spread checkpoint. checkpoint_timeout = 5 min, completion target     │
│ 0.9. The times are an example. The rules are from Rogov, 10.3 and 10.6   │
├──────────────────────────────────────────────────────────────────────────┤
│  -5:00   checkpoint P starts. Its REDO point is the WAL position then    │
│  -0:30   P completes. pg_control now names P's REDO point                │
│   0:00   checkpoint A starts. REDO point A = the WAL insert position.    │
│          The checkpointer tags every buffer that is dirty now            │
│   0:00 to 4:30  the checkpointer writes the tagged buffers, spread       │
│          over 0.9 × 5 min. Buffers dirtied after 0:00 wait for the next  │
│   4:30   A completes. It writes its checkpoint record, then pg_control.  │
│          From now on, recovery starts at REDO point A                    │
│   5:00   checkpoint B starts                                             │
│                                                                          │
│  crash at 4:29, before A completes: redo starts at P's REDO point,       │
│    -5:00. That is 9.5 minutes of WAL, 1.9 intervals, the worst case      │
│  crash at 4:31, after A completes: redo starts at REDO point A, 0:00.    │
│    That is 4.5 minutes of WAL                                            │
└──────────────────────────────────────────────────────────────────────────┘
```

The worst case is the crash at 4:29, right before a checkpoint completes. At the defaults that is up to 1 + 0.9 = 1.9 intervals of WAL. Rogov gives the same multiplier for the WAL a server must keep: the WAL between two checkpoints times 1 + `checkpoint_completion_target`. Verified from Rogov, section 10.6, page 177. The docs name the cost of the long spread. Prolonging checkpoints "affects recovery time", because more WAL must be kept for recovery. Verified from the PostgreSQL 17 docs, section 28.5, `wal.sgml` line 586.

**When a checkpoint starts.** PostgreSQL starts a checkpoint every `checkpoint_timeout`. It also requests one early when the WAL grows too fast. The defaults are the same in versions 14, 17 and 18:

| Setting | Default | What it does |
|---|---|---|
| `checkpoint_timeout` | 5 min | time between automatic checkpoints |
| `max_wal_size` | 1 GB | the WAL size that the size trigger is computed from |
| `min_wal_size` | 80 MB | WAL kept for reuse |
| `checkpoint_completion_target` | 0.9 | spread checkpoint writes over 90% of the interval |
| `checkpoint_warning` | 30 s | log a warning if size-triggered checkpoints come closer than this |

Verified from the 17 sample configuration file, lines 258 to 263, and from a fresh 14.24 cluster for the first four. The size trigger is not `max_wal_size` itself. `CalculateCheckpointSegments` at `xlog.c` line 2163, REL_17_11, divides it by 1 + `checkpoint_completion_target`. The same division is at line 2342 of REL_14_24. Here is the arithmetic at the defaults:

- **Step 1.** `max_wal_size` is 1,024 MB, or 64 WAL segments of 16 MB each. A WAL segment is one file in `pg_wal`.
- **Step 2.** 64 / 1.9 = 33.7, which the code rounds down to 33 segments.
- **Step 3.** So a checkpoint is requested after about 33 × 16 = 528 MB of WAL since the last REDO point.
- **Step 4.** While it runs, the server writes about 0.9 × 528 = 475 MB more.
- **Step 5.** So when it completes, the WAL since the old REDO point is about 528 + 475 = 1,003 MB, close to `max_wal_size`.

That is the reason for the division, as the code comment explains. The docs also call `max_wal_size` "a soft limit". Heavy load, a failing archive command, or a high `wal_keep_size` can push the WAL past it. Verified from the PostgreSQL 17 docs, section 19.5.2, `config.sgml` line 3711.

**The other side of the trade: full page images.** Section 1.4 showed why the first change to a page after a checkpoint writes the whole page into the WAL. That rule turns a short checkpoint interval into a cost, because more changes become first changes. The docs say that a smaller checkpoint interval "increases the volume of output to the WAL". That partly cancels the goal of the smaller interval, and it causes more disk I/O. Verified from the PostgreSQL 17 docs, section 28.5, `wal.sgml` line 547. Rogov measured the size with `pgbench`, PostgreSQL's benchmark tool, right after a checkpoint, when every page change is a first change:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ WAL written by pgbench -t 20000 after a CHECKPOINT. Rogov, PostgreSQL    │
│ 14.7, section 11.2, pp. 189 to 191. Hardware not stated                  │
├──────────────────────────────────────────────────────────────────────────┤
│                        WAL, 1 character per MB         MB   page images  │
│  wal_compression off   █████████████████████████████   29   71.54%       │
│    page images in it   ████████████████████            20                │
│  wal_compression on    ██████████                      10   23.86%       │
│    page images in it   ██                               2                │
│                                                                          │
│  MB = 2^20 bytes, as pg_size_pretty prints. Page image bytes, from       │
│  pg_waldump --stats: 21,134,168 and 2,453,755, so 8.6 times smaller.     │
│  Total WAL: 29 / 10 = 2.9 times less                                     │
└──────────────────────────────────────────────────────────────────────────┘
```

Rogov's cluster had data checksums on, as his section 11.2 shows. In the first run, 93.78% of the page image bytes were in records of the XLOG resource manager, not of the table resource manager. Those are likely the hint-bit images that checksums cause, from section 1.4. That is inferred from the record type, and not checked. `wal_compression` compresses page images only, and it is off by default. On PostgreSQL 17 it accepts `off`, `pglz`, `lz4` and `zstd`, if the server was built with them. In 14 it is only on or off, and on means `pglz`. Verified from the 17 docs, section 19.5, the 17 sample file, lines 243 and 244, and the 15.0 release notes. The view `pg_stat_wal`, since PostgreSQL 14, counts page images in `wal_fpi` and WAL bytes in `wal_bytes`. Phase 2 computes the page image cost per change for a B-tree, so this phase does not repeat that model.

So the checkpoint interval trades three costs. A long interval means a longer redo. A short one means more page images, more WAL to archive and send to replicas, and more page writes.

**Restart time is redo plus one more checkpoint.** After crash recovery, PostgreSQL runs one immediate checkpoint before it opens. The details differ by version:

- **PostgreSQL 17.** The startup process asks the checkpointer for `CHECKPOINT_END_OF_RECOVERY | CHECKPOINT_IMMEDIATE | CHECKPOINT_WAIT`. This is in `PerformRecoveryXLogAction`, from `xlog.c` line 6262 at REL_17_11, with the request at line 6297. The source says the checkpoint is "created before anyone is allowed to write WAL", at line 6959. PostgreSQL 18 has the same code, at lines 6323, 6358 and 7024 of REL_18_0.
- **PostgreSQL 14.** The startup process runs it itself, with `CreateCheckPoint` at line 8064 of `xlog.c` at REL_14_24. The checkpointer runs during crash recovery only since PostgreSQL 15, per the 15.0 release notes.
- **After a standby is promoted.** PostgreSQL writes only an end-of-recovery record, and the checkpoint comes later.

Rogov describes the same step: the checkpoint secures the recovered state on disk, section 10.4, page 174. The checkpoint is immediate, so it is not spread out. Its length grows with the pages that redo dirtied. That is inferred from the `CHECKPOINT_IMMEDIATE` flag, and not measured. So a recovery-time target has two parts: the redo, and this checkpoint.

**How long the redo takes.** One measurement gives WAL size and redo time together. Christophe Pettus published it on 2026-09-29, on PostgreSQL 18.6. The crash was a kill of the postmaster. He gives no hardware details, and the post was three weeks old on 2026-10-20:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Redo time against WAL since the last checkpoint. Pettus, 2026-09-29.     │
│ 3 characters per second                                                  │
├──────────────────────────────────────────────────────────────────────────┤
│ 1,080 MB ordinary WAL  ██████████████████                      6.0 s     │
│ 1,627 MB ordinary WAL  ██████████████████████████████████████  12.5 s    │
│   682 MB full pages    █████                                   1.5 s     │
│                                                                          │
│ per GB: 6.0 / 1.08 = 5.6 s and 12.5 / 1.627 = 7.7 s                      │
│ his own estimate, 10 to 12 s per GB, does not match his table            │
└──────────────────────────────────────────────────────────────────────────┘
```

So the answer to the question above is about 5 to 10 seconds, on that unnamed machine. WAL made of full page images replayed faster per megabyte in his test. 682 MB in 1.5 s is 455 MB per second. 1,080 MB in 6.0 s is 180 MB per second. Pettus gives the reason: "restoring a page image is a copy while an ordinary record has to read the page first". His runs were "single-threaded, with the data in cache". Pettus does not say whether his times include the end-of-recovery checkpoint, and this course did not test it. Redo time also depends on `recovery_prefetch`, added in PostgreSQL 15 with the default `try`. It reads ahead the blocks that the next WAL records need. Verified from the 15.0 release notes, the PostgreSQL 17 docs, section 19.5.4, and the 17 sample file, line 267. So a redo timing means something only with its version and this setting.

Stormatics published a production postmortem on 2026-07-01, about PostgreSQL 16.8 on Kubernetes. The checkpointer stayed active for more than four hours without finishing. After a forced restart, the server had to replay several hours of WAL. The bug was fixed in 16.10. On 17, the matching fix is in 17.6: "Limit the checkpointer process's fsync request queue size". The note says that with very large `shared_buffers` the checkpointer could try to allocate more than 1 GB, "leading to failure and an infinite loop". Verified from `release-17.sgml` lines 8218 to 8228, inside the 17.6 section. That it is the same bug is inferred from the matching symptom. The post gives no WAL size and no replay time. It shows the REDO point rule from the other side. A checkpoint that never completes never moves the starting point of recovery, so nothing bounds the redo.

**A large index build is also WAL.** pgvector, the PostgreSQL extension for vector search, says it "uses the write-ahead log (WAL), which allows for replication and point-in-time recovery". Verified from the pgvector README. So building a vector index on a large table likely writes WAL, including page images. That is inferred from the README sentence, and not checked in the pgvector source. It can then trigger size-based checkpoints. The WAL volume of such a build was not checked. Watch the `checkpoint_warning` line during the build, and `wal_bytes` in `pg_stat_wal` before and after it.

**Recovery on managed and cloud PostgreSQL.** Everything above assumes one server that writes its own pages and replays its own WAL. RDS for PostgreSQL works that way. Aurora, Neon and AlloyDB do not. They move page building and redo into a storage service. Aurora and AlloyDB also have no checkpoint in the database layer:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Who writes pages, and who replays WAL after a crash                      │
├────────────────────────┬─────────────────────────────────────────────────┤
│ RDS for PostgreSQL     │ database host ──WAL + pages──► EBS volume       │
│ and your own server    │ checkpoints and redo run on the database host   │
├────────────────────────┼─────────────────────────────────────────────────┤
│ Aurora, AlloyDB        │ database host ──WAL only──► storage service     │
│                        │ the storage service builds pages from the WAL   │
│                        │ no database-layer checkpoint                    │
├────────────────────────┼─────────────────────────────────────────────────┤
│ Neon                   │ compute ──WAL──► safekeepers, a Paxos quorum    │
│                        │ the pageserver builds pages from the WAL        │
│                        │ checkpoints on the compute: not checked         │
└────────────────────────┴─────────────────────────────────────────────────┘
```

| System | What the database host sends | What happens at a crash | Source |
|---|---|---|---|
| RDS for PostgreSQL | WAL and pages, to an EBS volume | normal redo, as in this section. "full page writes are always "on."" `log_checkpoints` is on by default, and `checkpoint_warning` "isn't set" by default | AWS page "IO:WALWrite", vendor |
| Aurora | redo log records only. "No pages are ever written from the database tier, not for background writes, not for checkpointing, and not for cache eviction" | "Nothing is required at database startup." AWS says Aurora "recovers asynchronously on parallel threads, so that your database is open and available immediately" | Aurora paper, SIGMOD 2017, section 3.2, which describes the MySQL-compatible engine. AWS page "Amazon Aurora reliability", vendor |
| AlloyDB | WAL records only. "there is no need to checkpoint the database layer" | the storage service keeps replaying WAL. The post says restarts are faster | Google Cloud blog, 2022-05-12, vendor |
| Neon | WAL, to safekeepers, the servers that store the WAL. A commit counts once "a quorum of safekeepers has acknowledged the WAL record via the Paxos protocol" | "Compute nodes do not own durable state and can be replaced freely." A starting compute "simply attaches to existing database history rather than reconstructing local state". What that start runs in detail was not checked | Neon docs, "The lakebase architecture", vendor |

The decisions that change:

- **On RDS, the redo arithmetic of this section holds.** Your levers are `max_wal_size`, `checkpoint_timeout` and `wal_compression` in a custom parameter group. Set `checkpoint_warning` yourself if you want the warning line. That is inferred from the AWS defaults above.
- **On RDS, redo reads from EBS.** Pettus's machine was not named. On gp3, each random read costs 1 to 9 ms, and 3,000 IOPS are included, from section 1.3. So redo on gp3 is likely slower per GB than in his table, and `recovery_prefetch` matters more. That is inferred, and not measured.
- **On Aurora, `max_wal_size` does not set your restart time.** Aurora's restart does not replay WAL on the database host. That is inferred for Aurora PostgreSQL from the paper, which describes the MySQL engine, and from the AWS page, which covers both. Whether Aurora uses `max_wal_size` at all was not checked.
- **What still applies everywhere.** The commit rule of section 1.2 still holds. A commit waits until the WAL is durable, now in a storage service. Section 1.6 shows the wait event for that. The torn page and checkpoint problems still exist inside the storage service, where you cannot test them. That is inferred from the sources above.
- **Old numbers.** The six copies and the 4-of-6 write quorum of Aurora come from the 2017 paper. The current AWS page says only that copies are kept "in three Availability Zones". Whether Aurora still uses 10 GB segments and the same quorum was not checked.

**The signals to read on a real server.** The lab prints `RecoveryReport.seconds`. A PostgreSQL server gives the same facts in its log, in several views, and in one tool:

| Signal | What it shows | Version | Source |
|---|---|---|---|
| `log_checkpoints` | a "checkpoint starting" line, then a "checkpoint complete" line with buffers written, write, sync and total seconds, `distance`, `estimate`, `lsn` and `redo lsn` | on by default since 15, and on RDS. Off by default in 14. The `lsn` fields since 16 | 17 sample file line 583, `xlog.c` REL_17_11 lines 6732 to 6737, 16.0 release notes, AWS "IO:WALWrite" page |
| `checkpoint_warning` | "checkpoints are occurring too frequently (N seconds apart)", with the hint to raise `max_wal_size` | default 30 s. Not set by default on RDS | `checkpointer.c` REL_17_11 lines 444 and 445, PG 17 docs 19.5 |
| `pg_stat_checkpointer` | `num_timed` counts scheduled checkpoints, completed and skipped. `num_requested` counts requested checkpoints that were performed. Many requested ones mean `max_wal_size` is too small. Also `write_time`, `sync_time` and `buffers_written` | since 17. 18 adds `num_done`, completed only, and `slru_written` | `system_views.sql` REL_17_11 line 1141, PG 17 docs Table 27.25, `monitoring.sgml` lines 2978 to 2995 |
| `pg_stat_bgwriter` | on 17 only `buffers_clean`, `maxwritten_clean`, `buffers_alloc` and `stats_reset`. The checkpoint columns `checkpoints_timed` and `checkpoints_req` exist only up to 16 | 14 to 16 for the checkpoint columns | `system_views.sql` REL_17_11 lines 1134 to 1139, Rogov pp. 180 and 181 for 14 |
| `pg_stat_io` | `writes` and `fsyncs` per `backend_type`. "Large numbers of fsyncs by client backends could indicate a misconfiguration of shared buffers or of the checkpointer" | since 16 | `system_views.sql` REL_17_11 line 1153, PG 17 docs Table 27.23, `monitoring.sgml` line 2847 |
| `pg_stat_wal` | `wal_fpi`, `wal_bytes`, and on 14 to 17 `wal_write`, `wal_sync` and their times | since 14. 18 moves the write and sync columns to `pg_stat_io` | `system_views.sql` REL_17_11 line 1175, PG 17 docs Table 27.26 |
| `pg_controldata` | "Database cluster state", "Latest checkpoint location" and "Latest checkpoint's REDO location". Needs a shell on the server | all versions | Rogov pp. 172 to 175 |
| startup log | "redo starts at", "redo done at" with elapsed time, the end-of-WAL line, and since 15 "redo in progress, elapsed time" every `log_startup_progress_interval`, default 10 s | all versions. The progress line since 15 | `xlogrecovery.c` REL_17_11 lines 1750, 1763 and 1885, 15.0 release notes |

Here are the queries for PostgreSQL 17. Both only read:

```sql
-- How often checkpoints run, and why. A high num_requested share means
-- max_wal_size is too small for the write rate.
select num_timed, num_requested, write_time, sync_time,
       buffers_written, stats_reset
from pg_stat_checkpointer;

-- Who writes and syncs pages. Many writes or fsyncs by 'client backend'
-- mean the checkpointer and bgwriter are not keeping up.
select backend_type, object, context, writes, fsyncs
from pg_stat_io
where writes > 0 or fsyncs > 0
order by writes desc;
```

The column names are from `system_views.sql` at REL_17_11. The queries were not run. On RDS and Aurora the same views exist, because the engine is PostgreSQL. That is inferred, and not checked on an instance. On RDS the log lines go to the instance's PostgreSQL log, which you read in the RDS console. How to export it to CloudWatch Logs was not checked here.

Here is what the lines look like. These recovery lines are from Rogov's PostgreSQL 14.7 example, page 175, after `pg_ctl stop -m immediate`. `log_checkpoints` was off there, so the end-of-recovery checkpoint does not appear:

```
LOG: database system was interrupted; last known up at 2023-03-06 14:01:49 MSK
LOG: database system was not properly shut down; automatic recovery in progress
LOG: redo starts at 0/3E7EF7E0
LOG: invalid record length at 0/3E7EF890: wanted 24, got 0
LOG: redo done at 0/3E7EF818 system usage: CPU: user: 0.00 s, system: 0.00 s, elapsed: 0.00 s
LOG: database system is ready to accept connections
```

The "invalid record length" line is the normal end of the WAL, not an error, as the table in section 1.4 showed. On 17 it reads "expected at least 24, got 0", from `xlogreader.c` line 669. "redo starts at" names the REDO point from `pg_control`. Here is Rogov's checkpoint line on PostgreSQL 14.7, page 180, after a manual `CHECKPOINT`:

```
LOG: checkpoint starting: immediate force wait
LOG: checkpoint complete: wrote 4100 buffers (25.0%); 0 WAL file(s) added, 1 removed, 0 recycled; write=0.076 s, sync=0.009 s, total=0.099 s; sync files=3, longest=0.007 s, average=0.003 s; distance=9213 kB, estimate=9213 kB
```

On PostgreSQL 17 the complete line ends with two more fields: `distance=%d kB, estimate=%d kB; lsn=%X/%X, redo lsn=%X/%X`. Verified from `xlog.c` lines 6732 to 6737 at REL_17_11. `distance` is the WAL between the starts of the last two checkpoints, in kB. `redo lsn` is the REDO point of the checkpoint that just completed. In PostgreSQL 18 the same line also prints SLRU buffers written, which are the cached pages of small files such as `pg_xact`. Verified from the 18.0 release notes and `xlog.c` at REL_18_6, line 6796.

An end-of-recovery checkpoint logs "checkpoint starting: end-of-recovery immediate wait" on 17. The startup process requests it with `CHECKPOINT_WAIT`, at `xlog.c` lines 6297 to 6299. `LogCheckpointStart` prints " wait" for that flag, at lines 6644 to 6652. Verified from the code, and not run. On 14 the line is "end-of-recovery immediate", because the startup process runs the checkpoint itself, without that flag. The earlier version of this phase said " wait" first appears in 18. The 17 source shows it already in 17, so that was wrong. Whether 15 and 16 print it was not checked.

**The lab store's recovery time.** It is not measured. The design reads every byte after the checkpoint once, and computes one CRC per entry. So its time grows with those bytes. That is inferred from the code. `RecoveryReport.seconds` prints it on each open, so you can measure it.

Bitcask has a similar file, the hint file. The paper's merge step writes it. It holds each key's position and no values, so a restart can read it instead of the data file. Merge is a form of compaction, and compaction is Phase 2.

Recovery is now bounded, and every put pays one full sync. The next section asks what that does to throughput, and how to share one sync among many puts.

**The sentence to remember:** PostgreSQL replays the WAL from the REDO point of the last completed checkpoint, up to 1.9 intervals at the defaults. Then it runs one immediate checkpoint before it opens.

**The trap:** a checkpoint written before the log it depends on is durable. After a power loss it points at log bytes that do not exist. The store cannot repair that and refuses to open.

**Try this now:** run `uv run python phase01_durability/crash_matrix.py --list`. Find crash points 23 to 27, the five checkpoint steps. For each one, say which checkpoint a power loss leaves, using the five-step diagram of `checkpoint()` above.

---
## 1.6 — Group commit and the durability–throughput trade (why one fsync per transaction is the wrong default at scale)

Why this matters: with one full sync per put, the store commits at most one put per sync time. Adding writers does not help, because they wait in line for the device. Many teams then turn durability off to get speed. Group commit gets most of the speed back and keeps durability.

**Answer this first.** On the M2, `F_FULLFSYNC` takes about 2.85 ms. Sixteen writers each put in a loop. With one sync per put, what is the most puts per second the store can do? With one sync shared by all sixteen, what is the most?

**The mental model.** Group commit means that one sync covers the log entries of many commits. Each commit still returns only after a sync that covers its own entry. While one sync runs, new puts append to the log and wait. When the sync returns, one of the waiting writers becomes the leader and syncs everything appended so far. The others wait for that sync, and then return together.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Group commit, 3 writers. One sync takes 2.85 ms, the M2 F_FULLFSYNC      │
│ median. Times are an example                                             │
├──────────────────────────────────────────────────────────────────────────┤
│ time ms    0          2.85       5.70       8.55                         │
│ device     [ sync 1  ][ sync 2   ][ sync 3   ]                           │
│ writer A   put 1 ────►OK put 2 ─────────────►OK                          │
│ writer B     put, waits ─────────►OK                                     │
│ writer C       put, waits ───────►OK                                     │
│                                                                          │
│ sync 1 covers A's put 1. B and C append during sync 1, and sync 2        │
│ covers both. A's put 2 appends during sync 2, so sync 3 covers it        │
│ 4 puts, 3 syncs. One sync per put needs 4 syncs, one after another       │
└──────────────────────────────────────────────────────────────────────────┘
```

**The arithmetic.** With one sync per put, the syncs run one after another. So the upper limit is 1 / 2.85 ms, about 351 puts per second. The number of writers does not change it. With group commit and 16 writers, one sync can cover at most 16 puts. The upper limit is then 16 × 351 = 5,616 puts per second. Python's own cost per put lowers both numbers. These are upper limits from arithmetic, not measurements. E10 measures the real numbers on your machine.

The trade is latency. A put that arrives right after a sync started waits for that sync, and then for its own. So one put can take up to 2 × 2.85 = 5.7 ms instead of 2.85 ms. Writer B in the diagram is that case. Throughput rises, and the time of each put rises a little.

**The lab's implementation.** In `kvlog.py`, the flag `group_commit=True` switches `put` from `_sync_log_locked` to `_wait_durable`. The core of `_wait_durable`, from `kvlog.py:475`, without its error handling and with the comments changed:

```python
# from phase01_durability/kvlog.py:475, _wait_durable(). Error handling removed, comments changed
        with self._sync_cv:
            while True:
                self._check_failed()
                if self.synced_to >= end:
                    return                      # an earlier sync covered this put
                if not self._flushing:
                    self._flushing = True       # this thread leads the next sync
                    break
                self._sync_cv.wait()            # another thread is syncing
        if self.group_delay_us:
            time.sleep(self.group_delay_us / 1_000_000)
        with self._write_lock:
            target = self._written_to           # everything appended so far
        self.fs.sync(LOG, self.sync_mode)
        with self._sync_cv:
            self._flushing = False
            self.synced_to = max(self.synced_to, target)
            self.syncs += 1
            self._sync_cv.notify_all()
```

The leader reads `target` before it syncs. A put that appends after that line is not counted as covered. That holds even if the sync happens to include its bytes. That rule keeps the claim exact: a put returns only when a sync that started after its append has returned.

One assumption is not checked. The design needs `fcntl.fcntl` and `os.fsync` to release Python's global interpreter lock while the device works. If they did not, no other thread could append during a sync, and every batch would hold one put.

**PostgreSQL's version.** PostgreSQL forms groups inside `XLogFlush`, the function of step 2 in the commit order of section 1.2. A committer tries to take `WALWriteLock` with `LWLockAcquireOrWait`, at `xlog.c` line 2852, REL_17_11. It is line 2855 at REL_18_0. If another backend holds the lock, this one waits until the lock is free. Then it does not take the lock at once. It first checks whether the holder already flushed past its own commit record. If so, it returns without a sync. That is the lab's `_wait_durable`, where a follower returns when `synced_to` covers its entry. Verified from the code and its comment, which says this "helps to maintain a good rate of group committing". PostgreSQL 17 also lists "Improve performance of heavily-contended WAL writes" in its release notes, `release-17.sgml` lines 14781 to 14783. The commit behind that note, at line 14776, changes the WAL insertion locks, not `WALWriteLock`. So it is not a group commit change. How much it changes the group size was not checked.

Two settings make groups larger. `commit_delay`, default 0 µs, makes the leader sleep before it flushes, if at least `commit_siblings` other transactions are active. `commit_siblings` defaults to 5. Since PostgreSQL 9.3, only the leader waits for the delay, and the others wait for its flush. Verified from the docs of versions 14, 17 and 18, and the 17 sample file, lines 253 and 254. The PostgreSQL 17 docs, section 28.5, add two points. At higher client counts a "gangway effect" forms groups even with a delay of 0, so the setting helps less there. And a good first value is half the time that `pg_test_fsync` reports for one flush after an 8 kB write. The lab's `--group-delay-us` flag is the same idea.

**Measured, on two machines from two sources.** Laurenz Albe of CYBERTEC measured `commit_delay` on PostgreSQL 17 in January 2025. The machine was an ASUS ZenBook notebook with NVMe and Fedora 40. The disk was limited to 1,000 write IOPS on purpose. The load was `pgbench -b simple-update -c 10` for 1,200 seconds. TPS below means transactions per second:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PostgreSQL 17 commit_delay. CYBERTEC, disk limited to 1,000 write IOPS   │
├──────────────────────────────────────────────────────────────────────────┤
│ delay      TPS, 36 characters = 2,738              TPS    IOPS           │
│ 0 µs       █████████████████████                 1,576   1,000           │
│ 500 µs     █████████████████████████████         2,183   1,000           │
│ 1,000 µs   ████████████████████████████████████  2,738     600           │
│ 2,000 µs   ███████████████████████████           2,051     430           │
│                                                                          │
│ 2,738 / 1,576 = 1.74 times. Past 1,000 µs the wait costs more than it    │
│ saves                                                                    │
└──────────────────────────────────────────────────────────────────────────┘
```

The docs' rule and this test agree once the flush is measured, not guessed. A disk limited to 1,000 write IOPS suggests about 1 ms per write, which would give about 500 µs. But in a reply under his post, dated 2025-06-28, Albe ran `pg_test_fsync` on the same throttled disk, and `fdatasync` took around 2,000 µs per operation. Half of that is the best value he measured, 1,000 µs. Verified from the reply. So start from half of the measured flush time of your `wal_sync_method`, and measure.

Vadim Tkachenko of Percona measured the InnoDB group commit fix in July 2011, on 8 disks in RAID 10. RAID 10 mirrors pairs of disks and spreads the data across the pairs. Without a controller cache, the fix raised throughput to 1,669.11 at 256 threads, against 57.62 without the fix at the same thread count, about 29 times. Without the fix, the best value was 60.05, at 64 threads. With a battery-backed cache, one thread already reached 352.83 without the fix, so group commit matters most when each sync is slow. The article does not state the unit, which is probably transactions per second.

**Where the commit count comes from: your ORM.** Group commit helps when many commits wait at once. But the number of commits is set by your application code, often by a default you did not choose:

- **Django.** "Django's default behavior is to run in autocommit mode. Each query is immediately committed to the database, unless a transaction is active." `transaction.atomic`, or `ATOMIC_REQUESTS = True` for a whole view, makes one transaction. Inside it, an inner `atomic` block "creates a savepoint", not a second commit. Verified from the Django 5.2 page "Database transactions".
- **psycopg 3.** The default is the opposite. "By default even a simple SELECT will start a transaction", which lasts until your code commits. Verified from the psycopg 3 page "Transactions management". Django turns autocommit on for its own connections: "Django overrides this default and turns autocommit on." Verified from the same Django page.

Here is the arithmetic for one Django view that makes 10 writes. It assumes one session alone, so no other commit shares its flush:

| Mode | Commits | Flush waits at 2.85 ms, M2 `F_FULLFSYNC` | Flush waits at about 1 ms, gp3, inferred in 1.3 |
|---|---|---|---|
| autocommit, the Django default | 10 | 10 × 2.85 = 28.5 ms | 10 × 1 = 10 ms |
| one `transaction.atomic` block | 1 | 2.85 ms | 1 ms |

Group commit can share flushes across sessions, so a busy server pays less per commit. It cannot merge the 10 commits of one session, because each waits for its own flush before the next statement runs. That is inferred from the commit order of section 1.2.

**A real case: the commits were the limit.** Disney+ Hotstar ran its payment service on Aurora MySQL with one writer. A load test could not reach the target rate. The pods' CPU and memory stayed well below 50% of capacity at peak load. Performance Insights, the AWS tool that samples what each database session waits for, showed most active sessions waiting on `wait/io/aurora_redo_log_flush` and on the binary log mutex. The team found "a fan out of 1:10 for a payment transaction API to a DML operation", each its own commit. DML means a statement that changes data, such as INSERT, UPDATE or DELETE. The post lists ways to make fewer commits, such as "Turning off auto-commit around multiple DML operations". The team judged that this would "require significant changes in the codebase", and did not apply it. The fix it applied was the binlog I/O cache, by a minor version upgrade of Aurora MySQL. The results of that upgrade were a "~30% uptick in TPS" and a "7x drop in P99 Latency" at 30% higher load. Verified from Ishank Gulati's post "De-bottlenecking Aurora MySQL for 19 Million concurrent users", January 2023, read from the Wayback Machine copy. The first wrong theory was slow reads. The reads were the three busiest queries, so they competed most for a pool connection. Most of their time was spent waiting for one, not running on the database.

**How to see the commit-flush wait.** A session that waits reports a wait event in `pg_stat_activity`. Sample it during load:

```sql
-- Run it several times during load. Each row is one kind of wait.
select wait_event_type, wait_event, count(*)
from pg_stat_activity
where state = 'active'
group by 1, 2
order by 3 desc;
```

The query was not run. The names you can see for a commit on PostgreSQL 17:

| `wait_event_type` / `wait_event` | Meaning | When you see it |
|---|---|---|
| `IO` / `WalSync` | "Waiting for a WAL file to reach durable storage." | Linux, with `fdatasync`, the default there |
| `IO` / `WalWrite` | "Waiting for a write to a WAL file." | also the sync wait with `open_datasync`, the macOS default, because the sync happens inside the write |
| `LWLock` / `WALWrite` | "Waiting for WAL buffers to be written to disk." | another backend holds `WALWriteLock`, so this one waits for its flush. This is a group commit follower |

The descriptions are verified from `wait_event_names.txt` lines 268, 270 and 314 at REL_17_11. `issue_xlog_fsync` reports `WalSync` at `xlog.c` line 8761. The display names follow the rule in `generate-wait_event_types.pl` lines 122 to 126. Which event a macOS commit shows is inferred from where the sync happens, and not run.

On managed PostgreSQL the same wait has a vendor name in Performance Insights:

| Service | Wait event | What AWS says | AWS's action on commits |
|---|---|---|---|
| RDS for PostgreSQL | `IO:WALWrite` | the session "is waiting for the WAL data to complete writing to disk so that it can release the transaction's COMMIT call" | "combine statements into transaction blocks" |
| Aurora PostgreSQL | `IO:XactSync` | "the database is waiting for the Aurora storage subsystem to acknowledge the commit" | "combine statements into transaction blocks". It is the last of four actions. AWS names network saturation and CPU pressure as the likely causes |

Verified from the AWS pages "IO:WALWrite" and "IO:XactSync", fetched on 2026-10-20. They are vendor pages. Both name the fix that the Hotstar team named but did not apply: fewer commits. For `IO:WALWrite` it is the first action. That `IO:WALWrite` on RDS is the native `WalSync` or `WalWrite` event under another name is inferred, and not checked.

**How long one flush takes, measured by the server.** On PostgreSQL 14 to 17, `pg_stat_wal` counts WAL syncs. It also adds up their time, when `track_wal_io_timing = on`:

```sql
-- Needs track_wal_io_timing = on, a superuser setting. Times are in ms.
select wal_sync, wal_sync_time,
       wal_sync_time / nullif(wal_sync, 0) as ms_per_sync,
       wal_write, wal_write_time
from pg_stat_wal;
```

`ms_per_sync` is the server's own time for one flush. Call it `t_sync`. It is the sync time that sets every limit in the arithmetic of this section. One trap: `wal_sync_time` counts only for `fdatasync`, `fsync` and `fsync_writethrough`. With `open_datasync` or `open_sync`, the sync time is inside `wal_write_time`, and `wal_sync` stays 0. Verified from the PostgreSQL 17 docs, Table 27.26, `monitoring.sgml` lines 3150 to 3185. So on a Mac with the default, read `wal_write_time / wal_write` instead. `track_wal_io_timing` has the context `PGC_SUSET`, so only a superuser can set it. Verified from `guc_tables.c` line 1430 at REL_17_11. Whether RDS allows it in a parameter group was not checked. PostgreSQL 18 removes these four columns from `pg_stat_wal` and reports the WAL rows in `pg_stat_io`, per the 18.0 release notes.

**On a cloud volume group commit matters more.** The upper limit of one sync per commit is 1 / `t_sync`. With 1 ms per flush on gp3, the best case of section 1.3, one session can commit at most about 1,000 times per second. The M4 Pro default commit of 22 µs allows about 45,000. That 1 ms is inferred from "single-digit millisecond latency", and not measured. So the same code that looks fast on a laptop meets the flush limit sooner on gp3. Group commit and fewer commits per request are the two fixes, and both are in this section.

**The other way: give up durability.** Each store below can reply before the log is durable. Each one names its own loss window:

| System and setting | When it replies | What a crash can lose | Source |
|---|---|---|---|
| PostgreSQL `synchronous_commit=off` | before the WAL flush | up to 3 × `wal_writer_delay`, 600 ms at the default | PG 17 docs, 19.5 |
| PostgreSQL `fsync=off` | never syncs | not a window: "unrecoverable data corruption in the event of a power failure or system crash" | PG 17 docs, 19.5 |
| PostgreSQL `UNLOGGED` table | the table writes no WAL at all | the whole table: it "is automatically truncated after a crash or unclean shutdown" | PG 17 docs, CREATE TABLE |
| MySQL `sync_binlog=0` | without a sync of the binary log | committed transactions missing from the binary log, after a power failure or OS crash | MySQL 8.4 manual |
| MariaDB `innodb_flush_log_at_trx_commit=0` | before the log write | about the last second | MariaDB docs |
| MariaDB `innodb_flush_log_at_trx_commit=2` | after the log write, before the flush | about the last second, on an OS crash or power loss | MariaDB docs |
| Redis `appendfsync everysec`, the default | before the fsync | about 1 second, per the docs | Redis persistence docs. The Redis course, Phase 4, teaches the detail |
| NATS JetStream, the default `sync_interval` | before the fsync | up to 2 minutes | Jepsen NATS 2.12.1, 3.4 |

The Redis row has one more detail. The Redis course teaches Redis durability in full, in its Phase 4 lesson, part "What does a crash lose, and which crash?". The file is `missionHq/learning/lessons/2026-10-18-redis-phase-04-architecture-ha.md`. In short, the docs say one second. The source in `src/aof.c` on the unstable branch can postpone a write for up to two seconds. It does so while a background fsync is still running. So the window can be longer than one second. That is inferred from the code and not tested. One more measurement shows the size of the gain. Kaarel Moppel of CYBERTEC measured, in 2016, 4,256 TPS with `synchronous_commit=on` and 6,211 TPS with `off`. The setup was two AWS i2.xlarge instances with asynchronous streaming replication, and `pgbench` with 8 clients for 10 minutes. With asynchronous replication the primary does not wait for the standby, so the setting changed only the local WAL wait. That last point is inferred from the PostgreSQL docs on `synchronous_commit`. The PostgreSQL version is not named.

So turning durability off gave 6,211 / 4,256 = 1.46 times in that test. Rogov ran a smaller test on PostgreSQL 14.7, with `pgbench`, 1 client and 30 seconds. He measured 670.8 TPS with `synchronous_commit` on and 2,060.4 TPS with it off, which is 3.07 times. Verified from Rogov, section 11.1, pages 184 and 185. His hardware is not stated in those pages. These ratios and the group commit ratio of 1.74 come from different machines and tests, so they are not compared.

Three rules make this choice less coarse than one global switch.

**Rule 1: per transaction.** `synchronous_commit` can be set for one transaction. "The mode used for any one transaction depends on the value of synchronous_commit when transaction commit begins." Verified from the PostgreSQL 17 docs, section 28.4. Any user can change it, because its context is `PGC_USERSET`, at `guc_tables.c` line 4926. So a service can commit a payment with `on` and a page-view log with `off`, in the same database:

```sql
-- One low-value transaction. Every other transaction keeps the default, on.
BEGIN;
SET LOCAL synchronous_commit = off;
INSERT INTO page_views (path, viewed_at) VALUES ('/pricing', now());
COMMIT;
```

`SET LOCAL` lasts until the end of the transaction. This is an example, and it was not run. A crash can lose up to 600 ms of these rows, and the database stays consistent. Use it for rows that a client never sees acknowledged as stored: traces, page views, telemetry. Do not use it for a transaction with an external action, from section 1.2.

**Rule 2: per table, with UNLOGGED.** An UNLOGGED table gives up more than async commit. It writes no WAL at all. The PostgreSQL 17 docs say: "Data written to unlogged tables is not written to the write-ahead log ... which makes them considerably faster than ordinary tables. However, they are not crash-safe: an unlogged table is automatically truncated after a crash or unclean shutdown. The contents of an unlogged table are also not replicated to standby servers." Verified from the PostgreSQL 17 docs, CREATE TABLE.

Here is the mechanism, one level below the docs:

- **Step 1: no WAL, so nothing to replay.** Each unlogged table has an initialization fork, an empty copy of the table. "When an unlogged table must be reset to empty due to a crash, the initialization fork is copied over the main fork". Verified from the PostgreSQL 17 docs, section 65.5. Crash recovery calls `ResetUnloggedRelations` at `xlog.c` lines 5724 and 5873 at REL_17_11.
- **Step 2: a checkpoint does not save it.** `BufferSync` writes unlogged buffers only for a shutdown, an end-of-recovery or a flush-all checkpoint. They "are otherwise skipped". Verified from `bufmgr.c` lines 2924 to 2927 at REL_17_11. So a clean shutdown keeps the data, and a crash empties it, whatever checkpoints ran before.
- **Step 3: such a commit does not wait for the WAL flush.** This holds for a transaction that wrote only to unlogged or temporary tables. The comment in `RecordTransactionCommit` says a transaction can have an xid and write no WAL "if it only wrote to temporary and/or unlogged tables". Verified from `xact.c` line 1467 at REL_17_11. Then `wrote_xlog` is false, and the commit takes the asynchronous path at line 1512. That is inferred from the condition at line 1487, and not run.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Three durability levels in one PostgreSQL 17 database                    │
├───────────────────────────┬───────────────────┬──────────────────────────┤
│ table and setting         │ commit waits for  │ after a crash            │
├───────────────────────────┼───────────────────┼──────────────────────────┤
│ logged, sync_commit on    │ the WAL flush     │ every acknowledged row   │
│ logged, sync_commit off   │ nothing           │ all but the last 600 ms  │
│ UNLOGGED                  │ nothing           │ the table is empty       │
├───────────────────────────┴───────────────────┴──────────────────────────┤
│ UNLOGGED rows are also missing on every standby, so after a failover too │
└──────────────────────────────────────────────────────────────────────────┘
```

Where it fits in your systems: a cache table, embeddings you can compute again from the source text, scratch state of an agent run, or a rate-limit counter. Each can be rebuilt, so losing it costs time, not data. Zerodha runs a whole cache database this way: "We turn off fsync and write-ahead logs as we can afford to throw away the cached data if the cache DB needs to be restarted for any reason." They also turn off replication for it. Verified from Zerodha's post "Working with PostgreSQL", 2021. Note that Zerodha uses a separate server with `fsync` off, while UNLOGGED keeps the rest of your database safe. `ALTER TABLE ... SET LOGGED` changes an unlogged table back, per the PostgreSQL 17 docs, ALTER TABLE.

The trap: an UNLOGGED table on a primary with a standby is empty on the standby. After a failover, for example on RDS Multi-AZ, the new primary has an empty table and no error. That RDS behaves this way is inferred from the docs sentence on standbys, and not checked. So your code must treat an empty unlogged table as a cold cache, never as "no data".

**Rule 3: `fsync=off` is a different risk.** Asynchronous commit loses at most the last 600 ms, and the database stays consistent. An UNLOGGED table loses only itself. `fsync=off` can corrupt the database beyond repair, per the docs row above. Rogov makes the same point on page 187. A CI database often runs with `fsync=off`, so its crash behaviour says nothing about production.

MySQL needs two settings for a durable commit, because the binary log is a second log next to the InnoDB log. `sync_binlog` defaults to 1. For the greatest durability "in a replication setup that uses InnoDB with transactions", the MySQL 8.4 manual lists `sync_binlog=1` together with `innodb_flush_log_at_trx_commit=1`. Verified from the manual's page "Binary Logging Options and Variables". Replicas read the binary log, which this course does not teach.

Now the store has a precise answer to "what does OK mean". The last section writes that answer down as one sentence and tests it.

**The sentence to remember:** group commit shares one sync among the commits that wait for it. Throughput grows with writers, and every reply still follows a sync.

**The trap:** replying before the sync to get speed, as the NATS default does. The store looks fast and consistent, and a power loss removes every write of the last interval.

**Try this now:** run `uv run python phase01_durability/group_commit.py --writers 16 --puts 50 --repeat 3`. Predict both rates first from the arithmetic above, then compare.

---
## 1.7 — Stating the durability boundary (the one sentence a storage system owes its users, and the tests that back it)

Why this matters: every earlier section added one condition to the word "committed". A user of the store cannot read the code to learn them. So the store owes its users one sentence that states them. It also owes a test that would fail if the sentence were wrong.

**Answer this first.** Write the sentence for the order store with `--sync full` on a Mac. Say which crash kinds an OK survives, what the store returns after recovery, and what is not covered. Then say which single test would show that your sentence is false.

**The mental model.** A durability boundary has four parts:

- **Part 1, the moment of the promise.** What has happened when the store replies OK. Here: the entry passed a sync that covers it.
- **Part 2, the crash kinds it survives.** Process crash, OS crash, power loss, from section 1.1.
- **Part 3, what recovery returns.** Here: a prefix of the puts in log order. It never returns an entry that fails its CRC.
- **Part 4, what is not covered.** These are conditions the store cannot check by itself. Examples are a drive that ignores flushes, damage to synced data, and loss of the device.

The lab store prints its own sentence, from `boundary_statement` at `kvlog.py:286`. For `--sync full` on a Mac it reads:

> A put that returned OK, after its own sync, with sync=full on darwin, survives a process crash, an OS crash and a power loss. A put that did not return may or may not survive. Recovery returns a prefix of the puts in log order and never returns an entry that fails its CRC. Not covered: damage to data that was already synced, a drive that ignores flush commands, and loss of the device.

The second sentence matters at the edge of every database. A client whose connection drops during COMMIT cannot tell which case it is in. Phase 3 shows how a PostgreSQL client finds out.

The sentence changes with the sync mode. `promises` at `kvlog.py:263` is the same rule in code, and the crash matrix checks the code against it:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The boundary of the lab store. Does an acknowledged put survive?         │
├───────────────────────────┬───────────────┬────────────┬─────────────────┤
│ mode, platform            │ process crash │ OS crash   │ power loss      │
├───────────────────────────┼───────────────┼────────────┼─────────────────┤
│ full, macOS: F_FULLFSYNC  │ yes           │ yes        │ yes             │
│ full, Linux: fsync        │ yes           │ yes        │ yes             │
│ fsync, macOS              │ yes           │ NO, note 1 │ NO              │
│ fsync, Linux              │ yes           │ yes        │ yes             │
│ none, any                 │ yes           │ NO         │ NO              │
├───────────────────────────┴───────────────┴────────────┴─────────────────┤
│ every "yes" for power loss assumes a drive that honours flush commands   │
│ note 1: not promised, because Apple's fsync(2) says an OS crash can      │
│ lose data after plain fsync. The fsim.py model still keeps it            │
└──────────────────────────────────────────────────────────────────────────┘
```

**How other systems state it.** Each sentence below covers one node only. That limit matters. In GitHub's incident of 2018-10-21, a network cut of 43 seconds led to a failover between data centers. The old primaries still held writes that had not been replicated. One of the busiest clusters "had 954 writes in the affected window", and the service was degraded for 24 hours and 11 minutes. Verified from GitHub's post "October 21 post-incident analysis". So a single-node sentence says nothing about what a failover keeps. This phase does not cover replicas. Phase 5, section 5.4, extends the sentence to a primary with standbys, and section 5.5 covers failover.

| System | The documented boundary, paraphrased | Source |
|---|---|---|
| PostgreSQL 17, `synchronous_commit=on` | every mode except `off` waits for the local WAL flush before it replies | PG 17 docs, 19.5 |
| SQLite, WAL mode, `synchronous=NORMAL` | stays consistent, but a commit can roll back after a power loss or OS crash. Commits survive an application crash in every mode | sqlite.org, `PRAGMA synchronous` |
| SQLite, WAL mode, `synchronous=FULL` | durable: one more sync of the WAL file after each commit | same page |
| MySQL 8.4, InnoDB with binary logging | durable with both settings of section 1.6 at 1. Other values of `innodb_flush_log_at_trx_commit` can lose commits. Other values of `sync_binlog` can leave committed transactions out of the binary log, in a power failure or OS crash | MySQL 8.4 manual |

The Redis and NATS defaults are in the table of section 1.6. The SQLite rows depend on the journal mode, so the mode must be in the sentence. The default journal mode is the rollback journal, not WAL. Verified from sqlite.org, "Write-Ahead Logging". WAL mode is chosen with `PRAGMA journal_mode=WAL`.

**The boundary for AI agent state.** An agent framework that saves its state to PostgreSQL makes the same choice as the stores above. LangGraph saves a checkpoint of the graph state at each step, through a checkpointer such as `PostgresSaver`. It "supports three durability modes", passed as `durability=` to each run. Verified from the LangGraph docs page "Checkpointers". Here is each mode, with the boundary sentence it implies:

| Mode | When LangGraph writes the checkpoint, per its docs | The boundary sentence for one finished step |
|---|---|---|
| `exit` | "only when graph execution exits": on success, on an error, or at a human-in-the-loop interrupt | survives nothing until the run exits. A process crash mid-run loses every step of the run |
| `async` | "asynchronously while the next step executes", with "a small risk" of a missing checkpoint if the process crashes | survives a process crash, except possibly the step whose write had not committed yet |
| `sync` | "synchronously before the next step starts" | survives a crash of the agent process, if the database commit was durable |

The quotes are verified from the same page. The sentences in the third column are inferred from them, and not tested. Two facts that the page does not state:

- **The default is `async`.** The code reads `durability = config.get(CONF, {}).get(CONFIG_KEY_DURABILITY, "async")`. Verified from `libs/langgraph/langgraph/pregel/main.py` line 2696 at tag `1.2.16`, and the docstring at line 2798, "defaults to `"async"`".
- **One checkpoint is one commit.** `PostgresSaver.from_conn_string` opens its connection with `autocommit=True`. But `put` runs its statements inside `self._cursor(pipeline=True)`, which uses a psycopg pipeline, or `conn.transaction()` when pipelines are not supported. Verified from `libs/checkpoint-postgres/langgraph/checkpoint/postgres/__init__.py`, lines 82, 326 and 477 to 515, at tag `checkpointpostgres==3.2.0`. The psycopg docs say: "even in autocommit, the server wraps the statements sent in pipeline mode in an implicit transaction, which will be only committed when the Sync is received." Verified from the psycopg 3 page "Pipeline mode support". So one `put` is one commit and one WAL flush, and each `put_writes` call is one more. That count is inferred, and not run. Check it with `xact_commit` in `pg_stat_database` before and after one step. The first draft of this section said each statement of a `put` was its own commit, because of `autocommit=True`. The pipeline paragraph of the psycopg docs showed that was wrong.

So the database half of the sentence comes from sections 1.2 and 1.6. In `sync` mode, every step waits for those flushes, so the arithmetic of section 1.6 applies to agent steps. If the checkpoint tables were UNLOGGED, or the role ran with `synchronous_commit = off`, the `sync` sentence would be false after a database crash. And a tool call that runs before its step's checkpoint commits can run again after a restart. The Redis course, Phase 7, part "How does a tool call run twice, and what stops a second payment?", teaches the fix. The file is `missionHq/learning/lessons/2026-10-19-redis-phase-07-ai-agents.md`.

**The test: a crash matrix.** A crash matrix runs a fixed workload and stops the store at every step. Then it checks recovery against the sentence. `crash_matrix.py` runs one with 10 operations on the keys `order:1041` to `order:1046`, and one checkpoint after the fourth.

Each crash point is one call of the store's hook. The count:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Crash points in the default workload                                     │
├──────────────────────────────────────────────────────────────────────────┤
│ open a new store      2   open.created, open.dir-synced         #1-#2    │
│ ops 1 to 4            4 × 5 = 20   encoded, written, synced,    #3-#22   │
│                                    indexed, acked                        │
│ checkpoint            5   log-synced, tmp-written, tmp-synced,  #23-#27  │
│                           renamed, dir-synced                            │
│ ops 5 to 10           6 × 5 = 30                                #28-#57  │
│ total                 2 + 10 × 5 + 5 = 57                                │
└──────────────────────────────────────────────────────────────────────────┘
```

At each crash point, the script builds five images in `fsim.py` and runs recovery on each:

- **process**, **os** and **power**: one recovery each, so 3 × 57 = 171.
- **torn-short**: only where log bytes are in flight. With `--sync full` that is the `put.written` step of each of the 10 operations. Five cuts each, at 1, 19, 20, half and all but one byte, give 10 × 5 = 50.
- **torn-hole**: one per in-flight point, 10.

The total is 171 + 50 + 10 = 231 recoveries. The check is the same for each one. Let S(m) be the store's contents after the first m operations. The recovered contents must equal S(m) for some m. That m must be at least the number of acknowledged operations, if the sentence promises this crash kind. And it must be at most the number of operations started. From `crash_matrix.py:204`:

```python
# from phase01_durability/crash_matrix.py:204, check(). Logic unchanged
    base = "power" if kind.startswith("torn") else kind
    try:
        st = Store.open(img, sync=cfg.sync, rules=cfg.rules)
        state = st.snapshot()
    except StoreError as exc:
        return Verdict(False, f"recovery failed: {exc}")
    detected = st.report.stop_reason is not None
    promised = prog.acked if (promises(cfg.sync, cfg.platform_model, base) or cfg.claim_power_safe) else 0
    matches = [m for m in range(prog.started + 1) if STATES[m] == state]
    if not matches:
        return Verdict(False, "recovered state is not S(m) for any m: damaged data was served", detected)
    if max(matches) < promised:
        return Verdict(False, f"acknowledged puts lost: recovered S({max(matches)}), "
                              f"acknowledged {promised}", detected)
    return Verdict(True, "", detected)
```

The expected result for the default run is 0 violations in 231 recoveries, with all 60 torn cases detected. The self-test of `crash_matrix.py` asserts these counts, at lines 381 to 383. It passed on 2026-10-20 on the M4 Pro, with Python 3.12.14. So the arithmetic is checked. The full printed table of E5 was not run. The earlier version of this phase said no lab code had run. That is no longer true for the self-tests.

**The one place the boundary does not hold.** Remove the directory sync after the log is created, with `--skip-dir-sync`. The log file's bytes are synced, but its name is not. In `fsim.py`, a name becomes durable only through a directory sync. The checkpoint's step 5 is the first one. A power loss or OS crash between the first acknowledgment and that step finds no log. Recovery then starts an empty store. That window is crash points #7 to #26: 26 − 7 + 1 = 20 points. So the expected result is 20 power violations and 20 OS violations. The self-test asserts both counts at line 397, and it passed on 2026-10-20.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ --skip-dir-sync: where the boundary breaks. Expected, not run            │
├──────────────────────────────────────────────────────────────────────────┤
│ #1 ─ #6     no put acknowledged yet          nothing promised  ok        │
│ #7 ─ #26    1 to 4 puts acknowledged, the    log name not      VIOLATION │
│             log's name is not durable        durable           20 + 20   │
│ #27 ─ #57   the checkpoint synced the        log name durable  ok        │
│             directory                                                    │
│ first line: #7 put.acked, os: acknowledged puts lost: recovered S(0),    │
│             acknowledged 1                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

This is the ALICE failure from section 1.3. It is also silent: the store opens without an error, and it is empty. Whether a real file system shows it depends on that file system. ALICE's Table 1 lists which persistence properties each Linux file system has. The model in `fsim.py` takes the strict reading. So a store that passes does not depend on one file system's extra ordering. APFS was not part of that study, and its behaviour here was not checked.

**A second break, from a wrong sentence.** Run the store with `--sync fsync` on the darwin model, and add `--claim-power-safe`. That flag checks the sentence most Python code would claim: an acknowledged put survives a power loss. The expected result is 42 power violations and 0 OS violations. The self-test asserts both at line 407, and it passed on 2026-10-20. There are 0 OS violations because the model keeps the drive cache in an OS crash. The 42 come from crash points #7 to #22, which is 16, and #32 to #57, which is 26. Between them, the checkpoint's full syncs made the log durable up to operation 4. That is the running case of this phase, found by a test.

**What a kill test can and cannot show.** `--real-kill` runs the same workload in a child process on real files. It sends `SIGKILL` at each of the 57 crash points. The expected result is 0 violations in every sync mode, `--sync none` too. Section 1.1 gave the reason. The count is worked out, not run. A real kill test is still worth running. It tests the real file calls, the real `O_APPEND` writes and the real rename, which the model does not. `O_APPEND` is the open flag that makes every write go to the current end of the file. It cannot test power.

**A real postmortem about crash testing.** The etcd project published the "v3.5 data inconsistency postmortem" on 2022-04-20. A refactor in v3.5.0 stopped saving the consistent index atomically with the data it describes. A crash between the two writes left a member inconsistent. The maintainers reproduced it under heavy load by killing one member with SIGKILL at random. The postmortem notes that it was reproduced only because one maintainer had `/tmp` on a normal disk. The bug was merged on 2021-05-08 and fixed in v3.5.3 on 2022-04-24, which is 351 days. Verified from the postmortem's dates, and the day count is arithmetic. The postmortem does not say why the disk mattered. A likely reason is that a real device makes each write slower, which widens the window between the two writes. That reason is inferred, not checked. A test on a memory file system, such as a tmpfs `/tmp` on Linux, never reaches a device at all. So `shared/durable.py` refuses to measure there.

**Testing a real system's boundary.** The crash matrix tests a model, and a kill test tests only process crashes. These tools sit between the two. Each one runs the real program on a device or file system that can lose writes on command. Device-mapper is the Linux layer that builds virtual block devices on top of real ones, and two of the tools are device-mapper targets:

| Tool | What it does | Source |
|---|---|---|
| LazyFS | a FUSE file system with its own page cache. A `clear-cache` fault drops unsynced data at a chosen call, and `torn-op` and `torn-seq` tear writes | LazyFS README, GitHub `dsrhaslab/lazyfs` |
| LazyFS, results | used on seven systems, PostgreSQL, etcd, ZooKeeper, Redis, LevelDB, PebblesDB and Lightning Network. It found eight new bugs | Ramos and others, PVLDB volume 17, issue 11, 2024, abstract |
| `dm-log-writes` | a device-mapper target that logs each write in order of completion. It logs a write only at the next flush, so a replay shows what was on disk, not in cache | kernel docs, device-mapper "log-writes" |
| `dm-flakey` | a device-mapper target with `drop_writes`, `error_writes` and `corrupt_bio_byte`. `error_writes` is a real kernel version of the failed fsync in E9 | kernel docs, device-mapper "dm-flakey" |
| `diskchecker.pl` | the device test of section 1.3, with a real power cut | named in PG 17 docs, 28.1 |

LazyFS, `dm-log-writes` and `dm-flakey` are Linux tools. The LazyFS README says it was tested with ext4 on Debian 11 and Ubuntu 20.04. On a Mac they need a Linux virtual machine. Whether LazyFS works with macFUSE was not checked, and neither was the platform support of `diskchecker.pl`. With these tools, the crash matrix of this phase becomes a test plan for a real service. Run the service on LazyFS or `dm-log-writes`, crash it at each write step, and check recovery against the sentence.

**What the boundary leaves out, on purpose.** The sentence covers crashes, not an operator who deletes data or backups that do not restore. The GitLab.com outage of 2017-01-31 was that case: an engineer wiped the primary database's data directory, and the backups had failed, per GitLab's postmortem of 2017-02-10. Recovery from deletion needs its own plan. A second case shows that a limit below the database belongs in part 4 of the sentence. Instapaper ran MySQL on RDS. Its `bookmarks` table "exceeded the 2TB file size limit" on 2017-02-09, because "MySQL RDS instances created before April 2014 used an ext3 filesystem which has a 2TB file size limit". Its 10 days of backups were "all filesystem snapshots", so "they're also subject to the 2TB file size limit". Limited service came back after 31 hours of downtime. Verified from Instapaper's post "Instapaper Outage Cause & Recovery", 2017-02-14, read from the Wayback Machine copy. So write the file system and the backup method into the "not covered" part, and test a restore.

**The sentence to remember:** state what an OK survives, what recovery returns and what is not covered. Back each part with a crash matrix that fails if the part is false.

**The trap:** a boundary that nobody tested. The store with `--skip-dir-sync` passes every kill test. It loses everything in a 20-step window that only an OS-crash or power-loss model, a tool such as LazyFS, or a real power cut shows.

**Try this now:** run `uv run python phase01_durability/crash_matrix.py --skip-dir-sync`. Predict the first violation line before you run it, then compare it with the diagram above.

---
## 🧪 Hands-on lab

The labs below are written and reviewed, but were not run by the author. The owner chose this on 2026-10-17. One exception: on 2026-10-20, the five self-tests were run with `uv run python <file> --self-test`, on the M4 Pro, macOS 26.6, Python 3.12.14. Each printed `self-test passed`. The self-test of `crash_matrix.py` asserts the counts of E5 to E8, so those counts are checked. Every other "Expected" line says "Not run by the author yet." and then gives the expected shape. The PostgreSQL exercises E11 to E15 target PostgreSQL 17. Their expected lines come from the 17 source and docs, not from a run. Each number in it comes from arithmetic in this phase, or from a cited measurement. The measurements are the earlier course's M2 runs and this course's M4 Pro research. Your timings will differ. The counts from the simulated file system should match exactly, because that part has no randomness and no timing.

**What you build.** The lab is a Bitcask-style store with a stated durability boundary, in five files:

| File | What it holds | Self-test checks |
|---|---|---|
| `shared/durable.py` | `durable_sync`: `F_FULLFSYNC` on macOS, `fsync` on Linux, and the directory sync | the decision table for both platforms, a real sync in every mode |
| `phase01_durability/fsim.py` | `RealFS`, and `SimFS` with three layers: page cache, drive cache, stable media | each layer rule, the fsyncgate rule, directory entries, both torn shapes |
| `phase01_durability/kvlog.py` | the store: entries with CRC, the keydir, group commit, checkpoint, recovery | each rule of `Rules`, removed one at a time, fails a check |
| `phase01_durability/crash_matrix.py` | crash injection at all 57 steps, five crash kinds, the S(m) check | the counts of section 1.7, and each break below |
| `phase01_durability/group_commit.py` | one sync per put against group commit, on real files | sync counts on a simulated device with a 2 ms sync |

The demonstration of this phase is E5, E6 and E8 together. They show the store and its stated boundary, and the crash matrix across every write step. They also show a torn write that the checksum detects instead of serving it.

All commands run from `elite-storage/code/`. E13 and E14 are the only exercises that crash PostgreSQL. They use a throwaway cluster that E13 creates itself.

- [ ] **E1 (offline).** See which system call each sync mode makes on your machine.
  - Run: `uv run python shared/durable.py --self-test`, then `uv run python shared/durable.py --explain`.
  - Expected: Not run by the author yet. `self-test passed`. Then on a Mac: `mode full  -> F_FULLFSYNC`, `mode fsync -> fsync`, `mode none  -> none`, and the file system `apfs`. On Linux, both `full` and `fsync` map to `fsync`.
  - If it fails: a line `F_FULLFSYNC is not supported here, falling back to fsync` means the directory is on a network or SMB mount. Use a local folder.
  - Teaches: the same Python call means a different guarantee on macOS and Linux.

- [ ] **E2 (local).** Measure the cost of each sync mode.
  - First write your prediction for the median of `full` and `fsync`.
  - Run: `uv run python shared/durable.py --measure 200`.
  - Expected: Not run by the author yet. Three lines with p50, p99 and max per mode. On a Mac, a fourth line gives the ratio of `full` to `fsync`. Compare your medians with the cost diagram in section 1.3, one machine at a time. The `none` line should be a few microseconds. The M4 Pro table in section 1.3 shows 3 µs for "write, no sync".
  - Teaches: a durable commit on a Mac costs milliseconds, and `os.fsync` hides that.

- [ ] **E3 (break-it, local).** Kill the store at every write step, with no sync at all.
  - Run: `uv run python phase01_durability/crash_matrix.py --real-kill --sync none`.
  - Expected: Not run by the author yet. `Dry run: 57 crash points`, and a `process` row of 57 cases with `0` violations. Then the note that a killed process leaves the page cache in place. Then run it with `--sync full`. The result should be the same.
  - If it fails with "child exited with 3": the crash point was never reached. Check that the hook count in `--list` is 57.
  - Teaches: a kill test cannot tell a store that syncs from one that does not.

- [ ] **E4 (offline).** Run every self-test, and use the store by hand.
  - Run: `uv run python phase01_durability/fsim.py --self-test`, then the same for `kvlog.py`, `crash_matrix.py` and `group_commit.py`.
  - Then run: `uv run python phase01_durability/kvlog.py --put order:1041=paid --put order:1042=paid --report`, and then `uv run python phase01_durability/kvlog.py --get order:1041 --report`.
  - Expected: the four self-tests print `self-test passed`. Verified on 2026-10-20. The store runs were not run by the author yet. The first store run prints `recovery: new store, log created`, the boundary sentence, and two `OK put` lines. The first is `bytes 0..34`: 20 header bytes, 10 key bytes and 4 value bytes. The second run prints `2 entries replayed` and `get order:1041: paid`.
  - Teaches: the boundary sentence is printed by the code that the matrix tests.

- [ ] **E5 (offline).** The crash matrix with the stated boundary. This is the main demonstration.
  - First write your prediction: the number of crash points, the number of recoveries, and the number of violations.
  - Run: `uv run python phase01_durability/crash_matrix.py`.
  - Expected: Not run by the author yet. `Dry run: 57 crash points`. Rows `process 57`, `os 57`, `power 57`, `torn-short 50`, `torn-hole 10`, each with `0` violations. The torn rows show `50` and `10` in the `torn detected` column. Last line: `RESULT: 0 violations in 231 recoveries. The stated boundary held.` Section 1.7 shows the arithmetic. The self-test asserts these row counts, and it passed on 2026-10-20.
  - Teaches: a boundary is backed by a test that checks every write step against it.

- [ ] **E6 (break-it, offline).** Remove the directory sync after the log is created.
  - Run: `uv run python phase01_durability/crash_matrix.py --skip-dir-sync`.
  - Expected: Not run by the author yet. `process` 0 violations, `os` 20, `power` 20. The torn rows have fewer cases, 30 and 6, because the log's name is not durable until crash point #27. The first violation line: `#7 put.acked, os: acknowledged puts lost: recovered S(0), acknowledged 1`. The self-test asserts the counts 20, 20, 30 and 6, and it passed on 2026-10-20. The violation line itself was not printed.
  - Teaches: a synced file whose name is not durable can vanish with all its data.

- [ ] **E7 (break-it, offline).** Check the claim that plain fsync is durable on a Mac.
  - Run: `uv run python phase01_durability/crash_matrix.py --sync fsync --claim-power-safe`, then `uv run python phase01_durability/crash_matrix.py --sync fsync`, then `uv run python phase01_durability/crash_matrix.py --sync fsync --platform-model linux`.
  - Expected: Not run by the author yet. With the claim: `power` 42 violations, `os` 0, and violations in the torn rows too. Without the claim: 0 violations, because the honest sentence for `fsync` on macOS promises a process crash only. On the linux model: 0 violations in 231 recoveries, as in E5. The self-test asserts the 42, the 0 and the linux result.
  - Teaches: the same code has a different boundary on each platform, and the sentence must say which.

- [ ] **E8 (break-it, offline).** A torn write, with and without the checksum.
  - Run: `uv run python phase01_durability/kvlog.py --torn-demo`, then `uv run python phase01_durability/crash_matrix.py --no-crc`.
  - Expected: Not run by the author yet. The demo prints the WRONG and RIGHT lines of section 1.4. First 1,200 bytes with 512 zeros, then a stop at offset 1230 with `checksum mismatch`. The matrix with `--no-crc` shows `torn-hole` with 8 violations of 10, and `torn-short` with 0. The 8 are the puts. The 2 deletes are 30 bytes long, and each hole zeroes the whole entry, so the length check stops them. The self-test asserts the 8 and the 0.
  - Teaches: only a checksum catches a write with the right length and the wrong bytes.

- [ ] **E9 (break-it, offline).** A failed fsync, retried and not retried.
  - Run: `uv run python phase01_durability/kvlog.py --fsync-error-demo`.
  - Expected: Not run by the author yet. WRONG: three puts acknowledged, and only `order:1041` after the power loss. Recovery stopped at offset 1230 with `impossible lengths ksz=0 vsz=0`, and 2460 bytes dropped. RIGHT: one put acknowledged and none lost. Both cases print that a restart without power loss sees `order:1042` through the page cache.
  - Teaches: after an fsync error the only safe action is to stop. The page cache can still show data the disk lacks.

- [ ] **E10 (local).** One sync per put against group commit, on your SSD.
  - First write your prediction for both rates with 16 writers, from section 1.6.
  - Run: `uv run python phase01_durability/group_commit.py --writers 16 --puts 50 --repeat 3`, then `uv run python phase01_durability/group_commit.py --writers 1 --puts 200 --repeat 3`.
  - Expected: Not run by the author yet. With 16 writers, the `per-put` lines show `puts/sync 1.0`. Their rate is at or below the M2 limit of 351 per second from section 1.6. The `group` lines show puts per sync well above 1, a rate several times higher, and a higher p50 latency. With 1 writer, both modes are about the same. Compare runs only with their spread, as the earlier course's Phase 1 taught.
  - If the group rate equals the per-put rate: the sync call may not release the interpreter lock. Section 1.6 names this as not checked.
  - Teaches: group commit trades a little latency per put for a large gain in throughput.

- [ ] **E11 (local, PostgreSQL 17).** Read your own cluster's durability settings.
  - Run: `createdb -h /tmp -p 5432 storage_lab`.
  - Then run: `psql -h /tmp -p 5432 -d storage_lab -c "select name, setting, unit, source from pg_settings where name in ('wal_sync_method','synchronous_commit','full_page_writes','data_checksums','data_sync_retry','commit_delay','commit_siblings','checkpoint_timeout','max_wal_size','wal_writer_delay','checkpoint_completion_target','checkpoint_warning','log_checkpoints','wal_compression','track_wal_io_timing') order by name"`.
  - Then run the counters. All three only read: `psql -h /tmp -p 5432 -d storage_lab -c "select num_timed, num_requested, write_time, sync_time, buffers_written, stats_reset from pg_stat_checkpointer"`, then `psql -h /tmp -p 5432 -d storage_lab -c "select checkpoint_lsn, redo_lsn, redo_wal_file, checkpoint_time from pg_control_checkpoint()"`, then `pg_controldata "$(psql -h /tmp -p 5432 -d storage_lab -Atc 'show data_directory')" | grep -E "cluster state|REDO location"`.
  - Expected: Not run by the author yet. From the PostgreSQL 17 sample file and `initdb.c`: `synchronous_commit on`, `full_page_writes on`, `data_checksums off`, `data_sync_retry off`, `commit_delay 0`, `commit_siblings 5`, `checkpoint_timeout 300` with unit `s`, `max_wal_size 1024` with unit `MB`, `wal_writer_delay 200` with unit `ms`, `checkpoint_completion_target 0.9`, `checkpoint_warning 30`, `log_checkpoints on`, `wal_compression off` and `track_wal_io_timing off`. `wal_sync_method` shows `open_datasync` on macOS and `fdatasync` on Linux, inferred from `xlogdefs.h`. Homebrew's `postgresql@17` formula makes its cluster with `initdb --locale=en_US.UTF-8 -E UTF-8`, without `-k`, so checksums are off there. A row whose source is not `default` was changed by your configuration. `pg_stat_checkpointer` shows how many checkpoints ran on the timer and on request since `stats_reset`. `pg_control_checkpoint()` gives the REDO point in SQL, with no shell. `pg_controldata` shows `in production` for a running server, and the REDO location of its last checkpoint.
  - If it fails: `column "checkpoints_timed" does not exist` means you ran the PostgreSQL 14 query on 17. The 14 query was `select checkpoints_timed, checkpoints_req from pg_stat_bgwriter`. `relation "pg_stat_checkpointer" does not exist` means your server is 16 or older. Use the 14 query there.
  - On RDS or Aurora: the first two queries work the same way, which is inferred. `pg_controldata` needs a shell, so it does not.
  - Teaches: your laptop's PostgreSQL acknowledges commits that a power cut can remove, and has no data checksums. Since 15 it does log its checkpoints.

- [ ] **E12 (local).** Time each WAL sync method of PostgreSQL.
  - Run: `"$(brew --prefix postgresql@17)/bin/pg_test_fsync" -s 3 -f ./pg_test_fsync.tmp`, then delete `./pg_test_fsync.tmp` if it is still there. On Linux, run the `pg_test_fsync` of your 17 install.
  - Expected: Not run by the author yet. Compare each line with the M4 Pro table in section 1.3, which this course's research measured with the 14.24 tool. On macOS the 17 tool prints "F_NOCACHE supported on this platform for open_datasync and open_sync.", from `pg_test_fsync.c` line 224. The 14 tool printed "Direct I/O is not supported on this platform." The `open_datasync` and `open_sync` rows may differ from the 14.24 table for the reason in section 1.3.
  - Teaches: the one method that flushes the drive cache on macOS is about 180 times slower than the default. 45,480 / 250 = 182, from the 14.24 table.

- [ ] **E13 (break-it, local, PostgreSQL 17).** Crash a throwaway PostgreSQL cluster, and read its real recovery.
  - Get the tools. Homebrew's `postgresql@17` formula is at 17.11 and is keg-only, so its programs are not on your `PATH` by default. Verified from formulae.brew.sh on 2026-10-20. Run: `brew install postgresql@17`, then `export PATH="$(brew --prefix postgresql@17)/bin:$PATH"`, then `pg_waldump --version`.
  - Expected: a line that starts `pg_waldump (PostgreSQL) 17.`. If it shows 14, your `PATH` still finds the old tools first.
  - Warning: every command below uses the throwaway directory in `$LAB` and port 54329. `pg_ctl stop -m immediate` crashes whichever cluster it names, so never point `-D` at your main cluster.
  - Run: `psql -h /tmp -p 5432 -Atc "show data_directory"`. Write the path down. It is the main cluster, and no step below may use it.
  - Run: `export LAB="$HOME/pg17-crash-lab"`, then `test ! -e "$LAB" && echo free`.
  - Expected: `free`. If nothing prints, the directory exists. Choose a new name. Do not reuse a directory that you did not create for this exercise.
  - Run: `initdb -D "$LAB"`.
  - Run: `pg_ctl -D "$LAB" -l "$LAB/server.log" -o "-p 54329 -k /tmp" start`. On 17, `log_checkpoints` is already on.
  - Run: `pgbench -h /tmp -p 54329 -i postgres`.
  - Run: `psql -h /tmp -p 54329 -d postgres -At -c "checkpoint" -c "select pg_current_wal_insert_lsn()"`. Write the LSN down as START.
  - Run: `pgbench -h /tmp -p 54329 -t 2000 postgres`, then `psql -h /tmp -p 54329 -d postgres -Atc "select pg_current_wal_insert_lsn()"`. Write it down as END.
  - Run: `psql -h /tmp -p 54329 -d postgres -Atc "select pg_size_pretty('END'::pg_lsn - 'START'::pg_lsn)"`, with your two values in place of END and START.
  - Run: `echo "$LAB"`.
  - Expected: your throwaway path, not the main cluster path you wrote down. If it prints anything else, stop here.
  - Warning: the next step crashes the cluster that `-D` names.
  - Run: `pg_ctl -D "$LAB" stop -m immediate`. The PostgreSQL 17 docs for `pg_ctl` say this mode aborts all server processes "without a clean shutdown". In the terms of section 1.1 it is a process crash, so the page cache survives and power loss is not tested.
  - Run: `pg_controldata "$LAB" | grep -E "cluster state|Latest checkpoint location|REDO location"`.
  - Run: `pg_waldump --stats -p "$LAB/pg_wal" -s START -e END`, with your two values.
  - Run: `pg_ctl -D "$LAB" -l "$LAB/server.log" -o "-p 54329 -k /tmp" start`, then `tail -n 12 "$LAB/server.log"`.
  - Expected: Not run by the author yet. `pg_controldata` shows `Database cluster state: in production`. On a stopped server that means it did not shut down cleanly, per Rogov, page 173. The REDO location is your manual checkpoint's REDO point, right before START, unless a timed checkpoint ran during the test. The `--stats` table ends with a `Total` line that gives the share of page image bytes. Rogov's 71.54% came from a cluster with data checksums on. Your 17 `initdb` used the default of off, so expect a smaller share. That is inferred, not measured. On 18, where checksums are on by default, expect the share to be closer to Rogov's. No source ran this exact test, so no WAL size is predicted. The log should show these lines in this order, from the 17 source:
    - `database system was interrupted`
    - `database system was not properly shut down; automatic recovery in progress`
    - `redo starts at`, with the REDO location
    - `invalid record length at ...: expected at least 24, got 0`
    - `redo done at`
    - `last completed transaction was at log time`, from `xlogrecovery.c` line 1891, because pgbench committed transactions
    - `checkpoint starting: end-of-recovery immediate wait`, then `checkpoint complete`, which ends with `lsn=` and `redo lsn=`
    - `database system is ready to accept connections`
  - The source lines are in section 1.5: `xlogreader.c` line 669, `xlog.c` lines 6297 and 6644 to 6652, and lines 6732 to 6737.
  - Keep the cluster running if you go on to E14 and E15. To clean up later: `pg_ctl -D "$LAB" stop`, then `echo "$LAB"`. If it prints your throwaway path and nothing else, run `rm -rf "$LAB"`.
  - If it fails: if `pg_ctl start` reports that port 54329 is in use, choose another free port in both start commands and every `psql` and `pgbench` command. If `pg_waldump` cannot find a WAL file, a checkpoint removed old segments. Run the test again with a smaller `-t`.
  - Teaches: a real redo starts at the REDO point, ends at the first invalid record, and is followed by one immediate checkpoint. These are the lines you will meet in a production log.

- [ ] **E14 (break-it, local, PostgreSQL 17).** Crash the throwaway cluster with an UNLOGGED table, and see what is left.
  - This uses the throwaway cluster of E13, at `$LAB` and port 54329. The same warnings apply. Run `echo "$LAB"` first, and check that it prints your throwaway path.
  - Run: `psql -h /tmp -p 54329 -d postgres -c "create table logged_t (id int)" -c "create unlogged table unlogged_t (id int)"`.
  - Run: `psql -h /tmp -p 54329 -d postgres -At -c "select pg_current_wal_insert_lsn()" -c "insert into logged_t select generate_series(1, 100000)" -c "select pg_current_wal_insert_lsn()" -c "insert into unlogged_t select generate_series(1, 100000)" -c "select pg_current_wal_insert_lsn()"`. You get three LSNs: A, B and C.
  - Run: `psql -h /tmp -p 54329 -d postgres -Atc "select pg_wal_lsn_diff('B', 'A') as logged_bytes, pg_wal_lsn_diff('C', 'B') as unlogged_bytes" -c "checkpoint"`, with your three values.
  - The last part of that command forces a checkpoint. It writes the pages of `logged_t` to the data files and skips the pages of `unlogged_t`, per section 1.6.
  - Warning: the crash below acts on `-D "$LAB"`. If `echo "$LAB"` did not print your throwaway path, stop now.
  - Run: `pg_ctl -D "$LAB" -l "$LAB/server.log" -m immediate restart`. It aborts every server process, as the E13 crash did, and then starts the server, which runs crash recovery.
  - Run: `psql -h /tmp -p 54329 -d postgres -Atc "select (select count(*) from logged_t), (select count(*) from unlogged_t)"`.
  - Then test a clean shutdown. Fill the unlogged table again with `psql -h /tmp -p 54329 -d postgres -c "insert into unlogged_t select generate_series(1, 100000)"`. Then run `pg_ctl -D "$LAB" -l "$LAB/server.log" -m fast restart`, which shuts the server down cleanly and starts it again. Then run the count query of the step before.
  - Expected: Not run by the author yet. `logged_bytes` is several megabytes, and `unlogged_bytes` is a few hundred bytes or less, mostly the commit record. That shape is inferred from the docs line "not written to the write-ahead log", and the sizes are not predicted. After the crash: `100000|0`. The logged table kept its rows, because the checkpoint wrote its pages and the WAL holds every change. The unlogged table is empty, though the checkpoint ran first. After the clean shutdown: `unlogged_t` has 100000 rows, because a shutdown checkpoint writes unlogged buffers too. These results are from the PostgreSQL 17 docs for CREATE TABLE and `bufmgr.c` lines 2924 to 2927.
  - If it fails: if the crash case shows rows in `unlogged_t`, check that you ran `-m immediate restart`, not `-m fast restart`.
  - Teaches: UNLOGGED gives up the table, not the database. It is safe only for data you can rebuild.

- [ ] **E15 (local, PostgreSQL 17).** Count the commits of one request: autocommit against one transaction, as in a Django view.
  - This uses the throwaway cluster of E13. Restart it with WAL timing on: `pg_ctl -D "$LAB" -l "$LAB/server.log" -o "-p 54329 -k /tmp -c track_wal_io_timing=on" restart`.
  - Create the table that both scripts insert into, with one integer column: `psql -h /tmp -p 54329 -d postgres -c "create table ev (v int)"`.
  - Write two pgbench script files. In `auto.sql`, put ten lines `insert into ev values (1);`. That is ten commits, like Django's autocommit. In `tx.sql`, put `begin;`, the same ten lines, then `commit;`. That is one commit, like `transaction.atomic`.
  - Run, for each file in turn: `psql -h /tmp -p 54329 -d postgres -Atc "select pg_stat_reset_shared('wal')"`, then `pgbench -h /tmp -p 54329 -n -f auto.sql -c 1 -T 20 postgres`, then `psql -h /tmp -p 54329 -d postgres -c "select wal_write, wal_sync, wal_write_time, wal_sync_time from pg_stat_wal"`. Repeat with `tx.sql`.
  - Expected: Not run by the author yet. pgbench counts one run of the script as one transaction in its `tps` line. So compare scripts per second. The `auto.sql` run should flush about ten times per script, and `tx.sql` about once. On Linux with `fdatasync`, the flushes count in `wal_sync`. On macOS with `open_datasync`, `wal_sync` stays 0 and the flushes count in `wal_write`, as section 1.6 explains. These shapes are inferred from the code and docs of section 1.6.
  - Then repeat both runs with the drive flush on: add `-c wal_sync_method=fsync_writethrough` to the restart command. Expected on the M4 Pro: at about 250 flushes per second from the 14.24 `pg_test_fsync` table, `auto.sql` can reach at most about 250 / 10 = 25 scripts per second. `tx.sql` can reach at most about 250. That is arithmetic, not a run.
  - Teaches: the ORM's commit mode sets the number of WAL flushes per request. One transaction per request costs one flush.

---

## 🔍 Check it yourself

- **Check 1.** Open `phase01_durability/kvlog.py:348`. This is the directory sync after the log is created, inside `Store.open`. With `--sync none`, this line does nothing. Why does that not break the boundary that `--sync none` states? Which row of the boundary table in section 1.7 shows it?

- **Check 2.** Open `phase01_durability/kvlog.py:402`. Recovery cuts the torn tail here and then syncs the cut. Suppose the sync on the next line were removed. Describe a second power loss, during the next put, that brings the torn bytes back. Is an acknowledged put lost, or only an unacknowledged one?

- **Check 3.** Open `phase01_durability/kvlog.py:495`. The group commit leader reads `target` before it calls the sync. Suppose it read `target` after the sync returned. Which puts could then return OK before their bytes were covered by a sync? Would any assertion in the self-test of `kvlog.py` catch this change? If not, describe a check that would.

- **Check 4.** Open `phase01_durability/fsim.py:451`. This is where the torn hole is placed. For the 30-byte delete of `order:1042` at offsets 4920 to 4950, compute the sector that this line zeroes. Then explain why `--no-crc` in E8 gives 8 violations and not 10.

- **Check 5.** Open `xact.c` at tag REL_17_11, line 1487, in `RecordTransactionCommit`. It is line 1498 at REL_18_0. This is the test that decides between `XLogFlush` and the asynchronous path. Name the two conditions that force a synchronous flush even with `synchronous_commit = off`. Read the comment above the test, and say why deleting a table's files is one of them. Then say why a transaction that wrote only to an UNLOGGED table takes the asynchronous path even with `synchronous_commit = on`.

- **Check 6.** In any service you own that uses PostgreSQL through an ORM, count the commits of one request. On a quiet development database, run `select xact_commit from pg_stat_database where datname = current_database()`. Send one request, and run it again. If the difference is larger than the number of business operations in the request, find where autocommit splits them. In Django, look for views without `transaction.atomic` or `ATOMIC_REQUESTS`.

- **Check 7.** In any repository you own that writes files it must not lose, run `grep -rn "fsync\|F_FULLFSYNC\|\.Sync()" <your repo>/`. For each hit, answer two questions. On macOS, does the call flush the drive cache? And what does the code do when the call returns an error?

---
## ✅ Checkpoint 1 — answer in your own words

The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

1. **Test-out, explain.** Walk through what happens when the store runs `put order:1041` with `--sync full` on a Mac. Name the five crash points of the put in order. For each one, say where the entry is and whether the client has its OK. Also say what a power loss there leaves after recovery. Then say what `F_FULLFSYNC` does not guarantee, even after it returns. Finally, match the steps of the put to the PostgreSQL commit order of section 1.2.

2. **Test-out, predict.** The default workload crashes at point #29, which is `put.written` of operation 5, the delete of `order:1042`. The crash is a power loss, and the drive kept the first 15 bytes of the 30-byte entry. Predict what recovery reads from the checkpoint, and where it starts the log scan. Then predict how many log entries it replays, and where it stops. Then give the recovered contents.

3. **Test-out, demonstrate.** Run E5 and E6. Show that the stated boundary holds in all 231 recoveries. Then explain each of the 40 violations that `--skip-dir-sync` produces, with the arithmetic of the crash points. Finally, run E8 and show the one torn write that the checksum detects and that `--no-crc` serves.

4. **A colleague says:** "Our CI runs on Macs and production runs on Linux with ext4. Both call `os.fsync`, and the crash tests pass on CI. So production is covered." Argue for or against, with the numbers and sources of this phase. Say which crash kind the CI test cannot cover and why, and which one it covers well.

5. **This is broken.** A Linux service writes events to an append-only log and syncs after each event. Its log shows one `EIO` from fsync on Tuesday at 10:00, then a retry that succeeded. The service ran normally. After a reboot on Friday, every event from Tuesday 10:00 onwards is missing, though all of them were acknowledged. What is the cause, and how do you check it? Why are the later events lost too, and not only the one at 10:00?
   **Part b.** A second case. After a release, a Django service on RDS for PostgreSQL 17 shows `IO:WALWrite` as its top wait in Performance Insights. p99 latency doubled, and CPU is below 40%. What is the likely cause, how do you check it with the views of this phase, and what is the fix?

6. **Show the arithmetic.** On the M4 Pro, `F_FULLFSYNC` took about 4.0 ms. A store has 32 concurrent writers. Compute the upper limit of puts per second with one sync per put, and with group commit. Compute the longest wait of one put with group commit, first with no delay, then with a 1 ms delay. With the delay, what is the new throughput limit, if every batch holds all 32 writers?
   **Part b.** A Django view makes 10 writes in autocommit mode on RDS with gp3. Take one WAL flush as 1 ms, the inferred figure of section 1.3. Compute the flush wait per request in autocommit and inside one `transaction.atomic` block. Then compute the most requests per second one worker can serve, if the flushes were the only cost.

7. **Given these constraints, design.** An example: a single-node audit log runs on a Linux server. It must survive a power loss, take 3,000 events per second at peak, and restart within 30 seconds. The SSD's flush takes about 2 ms. Choose the commit mode, the checkpoint rule, and the recovery rule, and write the durability boundary sentence. Show why one sync per event cannot meet the rate.
   **Part b.** The same team runs an AI agent runner on PostgreSQL 17, with LangGraph's `PostgresSaver`. One agent approves refunds and calls a payment API. Another summarizes documents and keeps an embeddings cache. Choose the LangGraph durability mode for each, say which tables may be UNLOGGED, and write the boundary sentence for each agent. Say what breaks the refund agent's sentence if someone sets `synchronous_commit = off` for its database role.

8. **Recovery time.** Your PostgreSQL 17 server on RDS must be back within 20 seconds after a crash. It runs the default checkpoint settings and writes WAL at a peak of 6 MB per second. Compute when a checkpoint is triggered, and the worst-case WAL to replay. Explain why it is more than one checkpoint's worth. Use Pettus's table from section 1.5, with its limits, to estimate the redo time at 5.6 and at 7.7 seconds per GB. Then say what else runs before the server opens, how far you could raise `max_wal_size`, and which signal shows how often size-triggered checkpoints happen.
   **Part b.** A colleague says: "We are moving to Aurora PostgreSQL, so we must keep the same `max_wal_size` limit to keep restarts under 20 seconds." Argue for or against, with the sources of section 1.5.

<details>
<summary>Answer sketches</summary>

1. `put.encoded`: nothing written, no OK, recovery gives the state before the put. `put.written`: the entry is in the page cache, no OK. A power loss loses it, or tears it, and recovery drops it by length or CRC. `put.synced`: `F_FULLFSYNC` returned, so the drive was asked to flush, and the entry survives. No OK yet. `put.indexed`: the same, now visible to readers. `put.acked`: the client has its OK and the entry survives. `F_FULLFSYNC` does not guarantee that the drive honours the flush. Zheng and others found 13 of 15 SSDs that did not behave. It also does not make the file's name durable, which needs the directory sync. In PostgreSQL, `put.written` matches the commit record in the WAL buffers, `put.synced` matches `XLogFlush`, and `put.indexed` matches `ProcArrayEndTransaction`, when other sessions see the rows. PostgreSQL also writes the outcome to `pg_xact` between the last two. With `synchronous_commit = off`, PostgreSQL makes rows visible before the flush, which the lab store never does.

2. The checkpoint is valid and covers 0 to 4920, so the keydir comes from it with the last sequence 4. The log scan starts at 4920 and finds 15 bytes. That is less than the 20-byte header, so `short header, 15 of 20 bytes`. 0 entries are replayed. Recovery stops at 4920, drops 15 bytes, cuts the file and syncs the cut. Contents: S(4), which is `order:1041` v2, `order:1042` v1 and `order:1043` v1. Operation 5 was not acknowledged, so nothing promised is lost.

3. The counts are asserted by the self-test of `crash_matrix.py`, which passed on 2026-10-20. The printed tables were not run. E5: 57 crash points, 171 + 50 + 10 = 231 recoveries, 0 violations, 60 torn cases detected. E6: from #7, the first acknowledgment, to #26, before the checkpoint's directory sync, the log's name is not durable. That is 26 − 7 + 1 = 20 points. Each fails for the OS crash and for the power loss, so 20 + 20 = 40. E8: the hole in the second put of `order:1041` lies at 1536 to 2048. The CRC catches it. `--no-crc` serves 512 zero bytes.

4. Against. On the Mac, `os.fsync` stops at the drive cache: Apple's `fsync(2)` page. On Linux ext4 with barriers on, fsync makes the file system flush the drive: PostgreSQL 17 docs, 28.1, and section 1.3's NVMe path. So the two platforms have different boundaries for an OS crash and a power loss. A crash test that kills processes covers the process kind on both, and nothing more. In E7, with `--claim-power-safe`, the Mac model with `os.fsync` shows 42 power violations, and the Linux model shows 0. The self-test of `crash_matrix.py` asserts both counts. The CI test is right about process crashes and says nothing about power. CI timings also come from a different system call than production, so they do not predict production timings.

5. fsyncgate. The failed fsync marked the pages clean, and the retry reported success for data that was never written. Rebello and others, ATC 2020, Table 1, found this on ext4, XFS and Btrfs. Check: search the service log and `dmesg` for the I/O error at 10:00. Then read the log file at the offset written at that time, and look for zeros or old data. The later events are lost because recovery stops at the first bad entry. Everything after the damaged range is dropped, though it was synced. Fix: stop the process at the first fsync error, never retry, and let recovery run on restart. PostgreSQL has done this by default since 2019-02-14. Part b: Likely cause: the release added commits per request. A new code path saves rows one by one in autocommit. AWS's first action for `IO:WALWrite` is "combine statements into transaction blocks". Check: the commit rate, from `xact_commit` in `pg_stat_database` sampled twice, before and after the release, divided by the request rate. Run the wait event query of section 1.6 to confirm the flush wait. Also check `num_requested` in `pg_stat_checkpointer` and the `log_checkpoints` lines, because AWS names frequent checkpoints as the other cause, and RDS does not set `checkpoint_warning` by default. Fix: wrap the request's writes in `transaction.atomic`, then compare commits per request again.

6. One sync per put: 1 / 4.0 ms = 250 puts per second. Group commit: at most 32 per sync, so 32 × 250 = 8,000 per second. Longest wait without delay: one sync in progress plus its own, 2 × 4.0 = 8.0 ms. With a 1 ms delay: 1 + 4.0 + 4.0 = 9.0 ms in the worst case. Throughput with the delay: one batch per 1 + 4.0 = 5.0 ms. So 32 / 5.0 ms = 6,400 per second. The delay only helps when batches would otherwise be small. Part b: Autocommit: 10 commits × 1 ms = 10 ms of flush wait per request. One `atomic` block: 1 commit × 1 ms = 1 ms. One worker, flush-bound: 1 / 10 ms = 100 requests per second in autocommit, against 1 / 1 ms = 1,000 with `atomic`. Group commit does not merge the ten commits of one session, because each waits for its own flush. The 1 ms is inferred from "single-digit millisecond latency". Measure it with `pg_stat_wal` as in section 1.6.

7. One sync per event: 1 / 2 ms = 500 per second, far below 3,000. Group commit: at 3,000 per second and 2 ms per sync, a batch holds 3,000 × 0.002 = 6 events. That is enough. Commit mode: group commit with the full sync, which is `fsync` on Linux with barriers on. Checkpoint: write the index often enough that the log since the checkpoint replays well within 30 seconds. Measure the scan rate first with `RecoveryReport.seconds`. Recovery: a CRC per entry, and a stop at the first bad entry. Cut and sync the cut. Sync the directory after create and rename. Stop on any fsync error. Boundary: an OK means the event passed a sync that covers it. It survives a process crash, an OS crash and a power loss, on a drive that honours flushes. Recovery returns a prefix and never a damaged entry. Not covered: damage to synced data and loss of the device. This is an example, not measured. Part b: Refund agent: `durability="sync"`, logged checkpoint tables, `synchronous_commit = on`, and an idempotency key on the payment call, because a tool call before its step's commit can run again after a restart. Sentence: a finished step survives a crash of the agent process and of the database, on a drive that honours flushes. A step whose checkpoint had not committed may run again. Not covered: loss of the database volume. Summarizer: the default `async` is fine, because a lost step costs one model call, not money. The embeddings cache can be an UNLOGGED table, because it can be computed again. Sentence: a step may be lost in a process crash, and the cache is empty after a database crash. If the refund agent's role runs with `synchronous_commit = off`, its checkpoints can vanish in the 600 ms window after the step continued. So the `sync` sentence is false after a database crash, and the payment can run twice without the idempotency key.

8. The size trigger at the defaults is about 528 MB of WAL since the last REDO point: 64 segments / 1.9 = 33, and 33 × 16 MB = 528 MB. At 6 MB per second that is 528 / 6 = 88 seconds, sooner than the 5-minute timer, so checkpoints are size-triggered. 88 s is more than the 30 s `checkpoint_warning`, so no warning appears. The worst case is a crash right before a checkpoint completes. Recovery then starts at the previous REDO point, because the REDO point counts only after completion. The WAL since then is about 528 + 0.9 × 528 = 1,003 MB, about 1 GB. `max_wal_size` is a soft limit, so a load spike can push it higher. Redo: 1.0 × 5.6 = 5.6 s and 1.0 × 7.7 = 7.7 s. Then the end-of-recovery checkpoint runs, immediate, with a length not measured here. So the target holds with room. Raising `max_wal_size` would cut page images. At 7.7 s per GB, 20 s is 20 / 7.7 = 2.6 GB of replay. So about 2 GB leaves room for that checkpoint and the soft limit. Signals: `num_requested` against `num_timed` in `pg_stat_checkpointer`, and the `distance` of each "checkpoint complete" line. This is a starting point only, with the limits of Pettus's table in section 1.5. Measure on your own hardware, first on a throwaway cluster as in E13. On RDS this arithmetic holds, because RDS replays WAL on the database host. RDS keeps `full_page_writes` on, so the page-image cost of a short interval is fixed. Part b: Against. Aurora sends only redo records to its storage tier, and the Aurora paper says "Nothing is required at database startup". AWS says Aurora is "open and available immediately after an unplanned restart". So `max_wal_size` does not set Aurora's restart time. What still matters there is the commit wait, `IO:XactSync`. Whether Aurora uses `max_wal_size` at all was not checked. The paper describes the MySQL-compatible engine, and the AWS page covers Aurora as a whole.

</details>

---

## References & Further Learning

This course's research fetched every URL below on 2026-10-17. The depth revision of 2026-10-18 added the entries for the PostgreSQL write path, checkpoints, Linux testing, MySQL and AWS, fetched that day. The PostgreSQL 17 revision of 2026-10-20 moved the docs links to version 17. It added the entries for managed and cloud PostgreSQL, the Linux NVMe path, MySQL 8.4, ORMs, agent state and the new cases, fetched that day. Each URL was checked again with `check_urls.py` on 2026-10-20. Primary sources come first in each group. Vendor pages are marked.

### The original designs

- **ARIES: A Transaction Recovery Method Supporting Fine-Granularity Locking and Partial Rollbacks Using Write-Ahead Logging, Mohan and others, ACM TODS, 1992** — https://cs.stanford.edu/people/chrismre/cs345/rl/aries.pdf
  Focus on: section 1.1, journal pages 97 and 98, for the WAL rule and the commit rule. Section 6 for the three restart passes. PDF page N is journal page N + 93. This copy is a scan with OCR text, so check any new quote against the page image. Read it before section 1.2 and 1.5.
- **Bitcask: A Log-Structured Hash Table for Fast Key/Value Data, Sheehy and Smith, Basho, 2010** — https://riak.com/assets/bitcask-intro.pdf
  Focus on: page 2 for the entry layout and the tombstone, page 3 for the keydir, page 5 for recovery. A company paper, not peer reviewed. 15 minutes. Read it before the lab.

### What fsync promises, and how it fails

- **Can Applications Recover from fsync Failures?, Rebello and others, USENIX ATC, 2020** — https://www.usenix.org/system/files/atc20-rebello.pdf
  Focus on: Table 1 on page 6, which shows each file system after a failed fsync. Section 5 gives the lessons. All tests are on Linux 5.2.11. Read it after section 1.3.
- **All File Systems Are Not Created Equal, Pillai and others, USENIX OSDI, 2014** — https://www.usenix.org/system/files/conference/osdi14/osdi14-paper-pillai.pdf
  Focus on: Table 1 for persistence properties per file system, and page 12 for the missing directory fsync. Linux file systems of 2014, no APFS. Read it before E6.
- **PostgreSQL's handling of fsync() errors is unsafe and risks data loss at least on XFS, Craig Ringer, pgsql-hackers, 2018** — https://www.postgresql.org/message-id/CAMsr%2BYHh%2B5Oq4xziwwoEfhoTZgr07vdGG%2Bhu%3D1adXx59aTeaoQ%40mail.gmail.com
  Focus on: the first message. It explains the cleared error flag in a few paragraphs. The primary source of fsyncgate.
- **PostgreSQL 11.2 release notes, 2019-02-14** — https://www.postgresql.org/docs/release/11.2/
  Focus on: the item about PANIC instead of retrying after fsync failure, and `data_sync_retry`. The same item is in 10.7, 9.6.12, 9.5.16 and 9.4.21.
- **Fsync Errors, PostgreSQL wiki** — https://wiki.postgresql.org/wiki/Fsync_Errors
  Focus on: the list of platforms and kernel versions. A community page. Its macOS line is not from Apple.
- **PostgreSQL's fsync() surprise, Jonathan Corbet, LWN.net, 2018** — https://lwn.net/Articles/752063/
  Focus on: the explanation of why the checkpointer did not see errors from before it opened the file. A short second account of the same bug.

### Disks, operating systems and runtimes

- **Understanding the Robustness of SSDs under Power Fault, Zheng, Qin, Tucek and Lillibridge, USENIX FAST, 2013** — https://www.usenix.org/system/files/conference/fast13/fast13-final80.pdf
  Focus on: section 4 for the test method, Table 5 for the failures by drive. Drives from about 2012. The one study here that cut real power.
- **fsync(2), Apple xnu source, tag xnu-12377.121.6** — https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.121.6/bsd/man/man2/fsync.2
  Focus on: the paragraph about the drive cache, the sentence about power loss or an OS crash, and `F_FULLFSYNC`. Use this copy, not the older archive page.
- **fcntl(2), Apple xnu source, tag xnu-12377.121.6** — https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.121.6/bsd/man/man2/fcntl.2
  Focus on: lines 207 to 245, `F_BARRIERFSYNC` and `F_FULLFSYNC`. Apple's older archive copy of this page does not list APFS, so use this copy.
- **fd_fsync_darwin.go, Go source, tag go1.27.2** — https://github.com/golang/go/blob/go1.27.2/src/internal/poll/fd_fsync_darwin.go
  Focus on: line 22, the `F_FULLFSYNC` call, and the `ENOTSUP` fallback after it. History: Go has used `F_FULLFSYNC` on darwin since Go issue 26650, closed on 2018-08-22 for Go 1.12. The fallback comes from Go issue 64215. That it first shipped in Go 1.23 is inferred from the issue's milestone.
- **drivers/nvme/host/core.c, Linux source, tag v6.12** — https://github.com/torvalds/linux/blob/v6.12/drivers/nvme/host/core.c
  Focus on: lines 2188 to 2191, the volatile write cache test, line 812 for the Flush command, and lines 980 and 981 for the FUA bit.
- **fs/jbd2/commit.c and fs/ext4/fsync.c, Linux source, tag v6.12** — https://github.com/torvalds/linux/blob/v6.12/fs/jbd2/commit.c
  Focus on: lines 152 to 154, the commit block with `REQ_PREFLUSH | REQ_FUA`. The fsync side is at https://github.com/torvalds/linux/blob/v6.12/fs/ext4/fsync.c, lines 111 to 113 and 171.
- **nvme-id-ctrl, nvme-cli documentation** — https://github.com/linux-nvme/nvme-cli/blob/master/Documentation/nvme-id-ctrl.txt
  Focus on: the command that prints the controller fields, and the `-H` option for readable output. The page does not describe `vwc`. Current nvme-cli calls `nvme id-ctrl` a deprecated alias of `nvme id ctrl`.
- **nvme-print-stdout.c, nvme-cli source, tag v2.11** — https://github.com/linux-nvme/nvme-cli/blob/v2.11/nvme-print-stdout.c
  Focus on: lines 2246 to 2264 and 3043, the `vwc` output and its bit 0, "Volatile Write Cache Present".
- **posixmodule.c, CPython source, tag v3.14.8** — https://github.com/python/cpython/blob/v3.14.8/Modules/posixmodule.c
  Focus on: `os_fsync_impl` near line 3993, which calls the plain `fsync`. CPython issue 56086 asks `os.fsync` to flush the drive. It was still open on 2026-10-17.

### PostgreSQL documentation, version 17

- **19.5 Write Ahead Log, PostgreSQL 17** — https://www.postgresql.org/docs/17/runtime-config-wal.html
  Focus on: `wal_sync_method`, `full_page_writes`, `synchronous_commit`, `commit_delay`, the checkpoint settings in 19.5.2 and `recovery_prefetch` in 19.5.4. Replace 17 with 14 in the URL for an old server, where the chapter is 20.5.
- **28.1 Reliability, PostgreSQL 17** — https://www.postgresql.org/docs/17/wal-reliability.html
  Focus on: drive caches, the macOS `fsync_writethrough` advice, the 512-byte sectors, and the sentence on BBU controllers and partial page writes.
- **28.2 Data Checksums, PostgreSQL 17** — https://www.postgresql.org/docs/17/checksums.html
  Focus on: the default of off, what checksums cover, and `pg_checksums` for an offline cluster.
- **28.4 Asynchronous Commit, PostgreSQL 17** — https://www.postgresql.org/docs/17/wal-async-commit.html
  Focus on: the loss window of `synchronous_commit=off`, the per-transaction rule, and the warning about external actions.
- **28.5 WAL Configuration, PostgreSQL 17** — https://www.postgresql.org/docs/17/wal-configuration.html
  Focus on: how crash recovery finds the redo point from the latest checkpoint, the spread checkpoint, the full page cost of short intervals, the "gangway effect" and the `commit_delay` starting value.
- **19.14 Error Handling, PostgreSQL 17** — https://www.postgresql.org/docs/17/runtime-config-error-handling.html
  Focus on: `data_sync_retry`, and why a retry after a write-back failure is unsafe.
- **CREATE TABLE, PostgreSQL 17** — https://www.postgresql.org/docs/17/sql-createtable.html
  Focus on: the `UNLOGGED` entry. Read it before you make a table unlogged.
- **65.5 The Initialization Fork, PostgreSQL 17** — https://www.postgresql.org/docs/17/storage-init.html
  Focus on: how an unlogged table is reset after a crash. One short paragraph.
- **18.4 Managing Kernel Resources, PostgreSQL 17** — https://www.postgresql.org/docs/17/kernel-resources.html
  Focus on: "Linux Memory Overcommit", the OOM killer line, and `vm.overcommit_memory=2`.
- **pg_checksums, PostgreSQL 17** — https://www.postgresql.org/docs/17/app-pgchecksums.html
  Focus on: `--enable` on a stopped cluster, before a move to 18.
- **PostgreSQL 18.0 release notes, 2025-09-25** — https://www.postgresql.org/docs/release/18.0/
  Focus on: the `initdb` change that enables data checksums by default, listed under incompatibilities, and the move of WAL I/O columns from `pg_stat_wal` to `pg_stat_io`.
- **Versioning Policy, PostgreSQL** — https://www.postgresql.org/support/versioning/
  Focus on: the final release dates. Version 14 ends on 2026-11-12, version 17 on 2029-11-08.

### The PostgreSQL write path, checkpoints and recovery

- **PostgreSQL 14 Internals, Egor Rogov, Postgres Professional, 2023** — https://edu.postgrespro.com/postgresql_internals-14_en.pdf
  Focus on: chapter 10, pages 164 to 181, for the LSN, `pg_waldump`, the spread checkpoint and its REDO point, recovery after `pg_ctl stop -m immediate`, and checkpoint monitoring. Chapter 11, pages 182 to 191, for asynchronous commit with `pgbench`, checksums, full page images and `wal_compression`. Every example runs on PostgreSQL 14.7, and the hardware is not stated. A free book, not peer reviewed. Read chapter 10 with section 1.5. Its view and log examples are 14 output, so compare them with the 17 tables of section 1.5.
- **PostgreSQL source, tag REL_17_11, `src/backend/access/transam`** — https://github.com/postgres/postgres/tree/REL_17_11/src/backend/access/transam
  Focus on: `xact.c`, `RecordTransactionCommit` from line 1304, for the commit order, and the comment at line 1467 on transactions that write no WAL. `xlog.c`: `CalculateCheckpointSegments` at line 2163, the `LWLockAcquireOrWait` call in `XLogFlush` at line 2852, `PerformRecoveryXLogAction` at line 6262, `LogCheckpointStart` at line 6627, the checkpoint log line at 6732, and `issue_xlog_fsync` at line 8739. `xlogrecovery.c` lines 1750 to 1885 for the redo log lines. `xlogreader.c` lines 669, 1165 and 1330 for the end-of-WAL and prev-link checks. The whole tree is at the same tag, for `fd.c`, `bufmgr.c`, `sync.c` and `system_views.sql`.
- **PostgreSQL 17 release notes, source file** — https://github.com/postgres/postgres/blob/REL_17_11/doc/src/sgml/release-17.sgml
  Focus on: lines 1953 to 1966, the 17.11 fix for missing full page images of visibility map pages. Lines 8218 to 8228, the 17.6 checkpointer fsync queue fix. Lines 14781 to 14783, faster contended WAL writes. Line 14841, `pg_stat_checkpointer`.
- **9.28 System Administration Functions, PostgreSQL 17** — https://www.postgresql.org/docs/17/functions-admin.html
  Focus on: `pg_current_wal_insert_lsn`, `pg_current_wal_lsn` and `pg_current_wal_flush_lsn`.
- **28.6 WAL Internals, PostgreSQL 17** — https://www.postgresql.org/docs/17/wal-internals.html
  Focus on: the LSN as a byte offset, and how two LSNs give the WAL between them.
- **27.2 The Cumulative Statistics System, PostgreSQL 17** — https://www.postgresql.org/docs/17/monitoring-stats.html
  Focus on: Table 27.23 `pg_stat_io`, Table 27.25 `pg_stat_checkpointer`, Table 27.26 `pg_stat_wal` and its note on `open_datasync`, the wait event tables, and `checksum_failures` in `pg_stat_database`. For version 14, `pg_stat_bgwriter` is Table 28.21 in the same chapter of the 14 docs.
- **19.8 Error Reporting and Logging, PostgreSQL 17** — https://www.postgresql.org/docs/17/runtime-config-logging.html
  Focus on: `log_checkpoints`, default on, and `log_startup_progress_interval`. The 14 page, section 20.8, gives `log_checkpoints` the default off.
- **pg_walinspect, PostgreSQL 17** — https://www.postgresql.org/docs/17/pgwalinspect.html
  Focus on: `pg_get_wal_stats`, which gives `pg_waldump --stats` in SQL. Useful where you have no shell.
- **pg_waldump, PostgreSQL 17** — https://www.postgresql.org/docs/17/pgwaldump.html
  Focus on: `-p`, `-s`, `-e` and `--stats`, the options E13 uses.
- **pg_ctl, PostgreSQL 17** — https://www.postgresql.org/docs/17/app-pg-ctl.html
  Focus on: the three stop modes. Immediate mode leads to crash recovery at the next start.
- **pg_test_fsync, PostgreSQL 17** — https://www.postgresql.org/docs/17/pgtestfsync.html
  Focus on: the `-f` option, to test the file system that holds the WAL.
- **PostgreSQL 15.0 release notes** — https://www.postgresql.org/docs/release/15.0/
  Focus on: `log_checkpoints` on by default, startup progress messages, `recovery_prefetch`, the checkpointer during crash recovery, and LZ4 and Zstandard for `wal_compression`.
- **PostgreSQL 17.0 release notes** — https://www.postgresql.org/docs/release/17.0/
  Focus on: the new view `pg_stat_checkpointer`, which took the checkpoint columns from `pg_stat_bgwriter`, and the new checkpoint delay wait events.
- **18.2 Creating a Database Cluster, PostgreSQL 17** — https://www.postgresql.org/docs/17/creating-cluster.html
  Focus on: section 18.2.2.1, "NFS", for the `hard` mount option and the `sync` export option.
- **postgresql@17, Homebrew formula** — https://formulae.brew.sh/formula/postgresql@17
  Focus on: the version, 17.11 on 2026-10-20, and that it is keg-only, so E13 adds it to `PATH`.

### Managed and cloud PostgreSQL

- **IO:WALWrite, Amazon RDS User Guide** — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/wait-event.iowalwrite.html
  Focus on: the context of the wait, "full page writes are always "on."", the `log_checkpoints` and `checkpoint_warning` defaults on RDS, and "Reduce the number of commits". A vendor page.
- **IO:XactSync, Amazon Aurora User Guide** — https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/apg-waits.xactsync.html
  Focus on: what the wait means on Aurora storage, and the metrics `CommitThroughput` and `CommitLatency`. A vendor page.
- **Amazon Aurora reliability, Amazon Aurora User Guide** — https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.Reliability.html
  Focus on: "Survivable page cache" and "Recovery from unplanned restarts". A vendor page.
- **Amazon Aurora: Design Considerations for High Throughput Cloud-Native Relational Databases, Verbitski and others, SIGMOD, 2017** — https://www.cs.purdue.edu/homes/csjgwang/CS592DisaggregatedDB/AuroraSIGMOD17.pdf
  Focus on: section 2.1 for the 4-of-6 quorum, and section 2.2 for 10 GB segments. Then read section 3.2, "Offloading Redo Processing to Storage", for why no pages leave the database tier and why startup needs no recovery. It describes the MySQL-compatible engine of 2017. A course copy of the paper.
- **AlloyDB for PostgreSQL under the hood: Intelligent, database-aware storage, Google Cloud blog, 2022-05-12** — https://cloud.google.com/blog/products/databases/alloydb-for-postgresql-intelligent-scalable-storage/
  Focus on: the three parts of the storage layer, and the paragraph on why there is no database-layer checkpoint. A vendor post.
- **The lakebase architecture, Neon docs** — https://neon.com/docs/introduction/architecture-overview
  Focus on: safekeepers and the Paxos quorum for commits, the pageserver, and stateless compute. A vendor page.
- **Amazon EBS volume types, Amazon EBS User Guide** — https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html
  Focus on: the comparison table for gp3 and io2 Block Express: durability, IOPS and latency. A vendor page.
- **General Purpose SSD volumes, Amazon EBS User Guide** — https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html
  Focus on: gp3's "single-digit millisecond latency" and the 3,000 IOPS baseline. A vendor page.

### Applications and agent state

- **Database transactions, Django 5.2 documentation** — https://docs.djangoproject.com/en/5.2/topics/db/transactions/
  Focus on: "Django's default behavior is to run in autocommit mode", `ATOMIC_REQUESTS`, savepoints in nested `atomic`, and `on_commit()`.
- **Transactions management, psycopg 3 documentation** — https://www.psycopg.org/psycopg3/docs/basic/transactions.html
  Focus on: the warning that a simple SELECT starts a transaction by default.
- **Pipeline mode support, psycopg 3 documentation** — https://www.psycopg.org/psycopg3/docs/advanced/pipeline.html
  Focus on: the note that even in autocommit, statements sent in pipeline mode form one implicit transaction until the Sync.
- **Checkpointers, LangGraph documentation** — https://docs.langchain.com/oss/python/langgraph/checkpointers
  Focus on: "Durability modes", the three modes `exit`, `async` and `sync`. The page does not give the default.
- **pregel/main.py, LangGraph source, tag 1.2.16** — https://github.com/langchain-ai/langgraph/blob/1.2.16/libs/langgraph/langgraph/pregel/main.py
  Focus on: line 2696, the default durability `"async"`, and the docstring at line 2798.
- **PostgresSaver, LangGraph source, tag checkpointpostgres==3.2.0** — https://github.com/langchain-ai/langgraph/blob/checkpointpostgres%3D%3D3.2.0/libs/checkpoint-postgres/langgraph/checkpoint/postgres/__init__.py
  Focus on: line 82, `autocommit=True`, and `put` from line 268.
- **README, pgvector** — https://github.com/pgvector/pgvector
  Focus on: the answer to "Is replication supported?", which says pgvector uses the WAL.
- **VZDiskImageSynchronizationMode, Apple developer documentation** — https://developer.apple.com/documentation/virtualization/vzdiskimagesynchronizationmode
  Focus on: the three modes `full`, `fsync` and `none` for a virtual disk on a Mac.

### Testing durability on a real system

- **When Amnesia Strikes: Understanding and Reproducing Data Loss Bugs with Fault Injection, Ramos and others, PVLDB volume 17, issue 11, 2024** — https://www.vldb.org/pvldb/vol17/p3017-ramos.pdf
  Focus on: the abstract, the table of systems and versions, and the paragraph "Protection and recovery" for the PostgreSQL torn page test. Read it before you plan a crash test of a real service.
- **LazyFS, GitHub `dsrhaslab/lazyfs`** — https://github.com/dsrhaslab/lazyfs
  Focus on: the fault types `clear-cache`, `torn-op` and `torn-seq`, and the tested platforms, ext4 on Debian 11 and Ubuntu 20.04.
- **dm-log-writes, Linux kernel docs** — https://docs.kernel.org/admin-guide/device-mapper/log-writes.html
  Focus on: "Log Ordering". Writes are logged only at the next flush, so a replay shows what was on disk.
- **dm-flakey, Linux kernel docs** — https://docs.kernel.org/admin-guide/device-mapper/dm-flakey.html
  Focus on: `drop_writes`, `error_writes` and `corrupt_bio_byte`.
- **Explicit volatile write back cache control, Linux kernel docs** — https://docs.kernel.org/block/writeback_cache_control.html
  Focus on: `REQ_PREFLUSH`, `REQ_FUA`, and what the block layer does for a device with no volatile cache.
- **sysfs-block, Linux kernel ABI** — https://www.kernel.org/doc/Documentation/ABI/stable/sysfs-block
  Focus on: the entry `/sys/block/<disk>/queue/write_cache` and its warning about switching to "write through".
- **diskchecker.pl, Brad Fitzpatrick, LiveJournal** — https://brad.livejournal.com/2116715.html
  Focus on: how the client and server check that flushed data survives a power cut. This is the link the PostgreSQL 28.1 docs give. A personal blog post.
- **open(2) and fsync(2), Linux man-pages** — https://man7.org/linux/man-pages/man2/open.2.html
  Focus on: `O_DIRECT` and its note that it does not give the guarantees of `O_SYNC`. The `fsync(2)` page at https://man7.org/linux/man-pages/man2/fsync.2.html gives the Linux 4.13 change to error reporting.

### MySQL and cloud devices

- **What Is New in MySQL 8.4 since MySQL 8.0, MySQL 8.4 Reference Manual** — https://dev.mysql.com/doc/refman/8.4/en/mysql-nutshell.html
  Focus on: Table 1.1, the changed InnoDB defaults: `innodb_flush_method`, `innodb_use_fdatasync`, `innodb_doublewrite_files`, `innodb_doublewrite_pages` and `innodb_log_buffer_size`.
- **InnoDB Startup Options and System Variables, MySQL 8.4 Reference Manual** — https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html
  Focus on: `innodb_flush_method` and what `O_DIRECT` does, `innodb_use_fdatasync`, `innodb_doublewrite` and its default `ON`, and `innodb_flush_log_at_trx_commit`.
- **Doublewrite Buffer, MySQL 8.4 Reference Manual** — https://dev.mysql.com/doc/refman/8.4/en/innodb-doublewrite-buffer.html
  Focus on: why InnoDB writes each page twice, and the `DETECT_ONLY` mode.
- **MySQL Product Support EOL Announcements, Oracle** — https://www.mysql.com/support/eol-notice.html
  Focus on: the line on MySQL 8.0 and Sustaining Support from 2026-04-21.
- **Binary Logging Options and Variables, MySQL 8.4 Reference Manual** — https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html
  Focus on: `sync_binlog`, its default of 1, and the pair of settings for the greatest durability.
- **Torn write prevention, Amazon EC2 User Guide** — https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/storage-twp.html
  Focus on: the first section, which says all-or-nothing writes remove the need for the doublewrite buffer. A vendor page, so its percentages are vendor claims.

### SQLite

- **Atomic Commit In SQLite** — https://www.sqlite.org/atomiccommit.html
  Focus on: section 2 for the hardware assumptions, and section 9.2 for drives that report a flush early.
- **Pragma statements** — https://www.sqlite.org/pragma.html
  Focus on: `PRAGMA synchronous` for the durability of each mode, and `fullfsync` and `checkpoint_fullfsync` for macOS, both off by default.
- **Write-Ahead Logging** — https://www.sqlite.org/wal.html
  Focus on: the first paragraph. The default is the rollback journal.

### Incidents and analyses

- **Jepsen: MariaDB Galera Cluster 12.1.2, Kyle Kingsbury, 2026** — https://jepsen.io/analyses/mariadb-galera-cluster-12.1.2
  Focus on: section 3.1 for the loss under the recommended setting, and section 4. Section 3.2 is a separate loss with no root cause.
- **Configuring MariaDB Galera Cluster, MariaDB docs** — https://mariadb.com/docs/galera-cluster/galera-management/configuration/configuring-mariadb-galera-cluster
  Focus on: the current advice on `innodb_flush_log_at_trx_commit`. Compare it with the Wayback copy of 2026-03-08.
- **InnoDB System Variables, MariaDB docs** — https://mariadb.com/docs/server/server-usage/storage-engines/innodb/innodb-system-variables
  Focus on: `innodb_flush_log_at_trx_commit` and its values 0 to 3.
- **Jepsen: NATS 2.12.1, Kyle Kingsbury, 2025** — https://jepsen.io/analyses/nats-2.12.1
  Focus on: section 3.4, the two-minute fsync default. LazyFS is the tool that models power loss there.
- **v3.5 data inconsistency postmortem, etcd project, 2022** — https://github.com/etcd-io/etcd/blob/main/Documentation/postmortems/v3.5-data-inconsistency.md
  Focus on: the root cause and the line about `/tmp` on a normal disk. A first-party postmortem with dates.
- **Postmortem of database outage of January 31, GitLab, 2017** — https://about.gitlab.com/blog/postmortem-of-database-outage-of-january-31/
  Focus on: the timeline. It is an operator deletion and failed backups, not a sync failure.
- **De-bottlenecking Aurora MySQL for 19 Million concurrent users, Ishank Gulati, Disney+ Hotstar, 2023** — https://web.archive.org/web/20230131210030id_/https://blog.hotstar.com/de-bottlenecking-aurora-mysql-for-19-million-concurrent-users-ee98d6247cfe
  Focus on: "Root Cause" for the 1:10 fan-out of commits, and "Impact" for the 30% and 7x numbers. The live page returned 403, so this is the Wayback Machine copy.
- **Working with PostgreSQL, Satya Sarangi, Zerodha, 2021** — https://zerodha.tech/blog/working-with-postgresql/
  Focus on: the paragraph on the cache database with fsync and WAL off.
- **Roblox Return to Service, Roblox, 2022, about the outage of 10/28-10/31 2021** — https://about.roblox.com/newsroom/2022/01/roblox-return-to-service-10-28-10-31-2021
  Focus on: the BoltDB freelist analysis, the 4.2 GB store with 489 MB of data and the 7.8 MB written per append.
- **October 21 post-incident analysis, GitHub, 2018** — https://github.blog/news-insights/company-news/oct21-post-incident-analysis/
  Focus on: the 954 writes not replicated in one cluster. It shows why a single-node boundary says nothing about a failover.
- **Instapaper Outage Cause & Recovery, Brian Donohue, 2017** — https://web.archive.org/web/20170216165223id_/https://medium.com/making-instapaper/instapaper-outage-cause-recovery-3c32a7e9cc5f
  Focus on: "Root cause" for the ext3 2 TB limit and the snapshot backups with the same limit. The Wayback Machine copy, because the live page returned 403.
- **Inside a PostgreSQL Checkpointer Bug: A Production Postmortem, Warda Bibi, Stormatics, 2026** — https://stormatics.tech/blogs/postgresql-checkpointer-bug-causing-infinite-retry-loop
  Focus on: why a stuck checkpointer leaves hours of WAL to replay. No numbers for the replay itself. Read it with the 17.6 release note.

### Measurements of group commit and recovery

- **commit_delay for better performance: a PostgreSQL benchmark, Laurenz Albe, CYBERTEC, 2025** — https://www.cybertec-postgresql.com/en/commit_delay-performance-postgresql-benchmark/
  Focus on: the results table and the hardware setup, with the disk limited to 1,000 IOPS.
- **Testing the Group Commit Fix, Vadim Tkachenko, Percona, 2011** — https://www.percona.com/blog/testing-the-group-commit-fix/
  Focus on: the two test tables, with and without the controller's write cache. The unit is not stated.
- **The synchronous_commit parameter and streaming replication, Kaarel Moppel, CYBERTEC, 2016** — https://www.cybertec-postgresql.com/en/the-synchronous_commit-parameter/
  Focus on: the two rows with asynchronous replication, `on` and `off`. Phase 5, section 5.4, covers the synchronous replication rows.
- **All Your GUCs in a Row: max_wal_size, Christophe Pettus, 2026** — https://thebuild.com/blog/all-your-gucs-in-a-row-max_wal_size/
  Focus on: the redo time table. New, not peer reviewed, no hardware given.
- **Redis persistence, Redis docs** — https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/
  Focus on: the `appendfsync` policies and their stated loss windows.

### Lectures

- **CMU 15-445/645 Fall 2025, Lecture 21: Database Logging, Andy Pavlo** — https://www.youtube.com/watch?v=CedEy54pe3g
  Focus on these times:
    - 0:17:32 steal and force policies
    - 0:19:40 force defined
    - 0:24:21 shadow paging
    - 0:39:25 SQLite rollback journal
    - 0:44:41 write-ahead logging
    - 0:48:46 WAL implementation
    - 0:51:30 log record contents
    - 0:55:02 group commit
    - 1:10:32 checkpoints
    - 1:19:10 summary

  The times are YouTube's auto-generated chapters, and five were checked against the auto-generated captions. Two spoken claims disagree with the docs. At about 1:19:10 the captions show him saying that synchronous commit is not on by default in PostgreSQL. The PostgreSQL 14, 17 and 18 docs, and a fresh 14.24 cluster, say `on`. At about 0:39:25 they show him saying that SQLite now uses the WAL by default. The SQLite docs say the default is the rollback journal. This phase teaches the docs.
- **Lecture 21 slides** — https://15445.courses.cs.cmu.edu/fall2025/slides/21-logging.pdf
  Focus on: the group commit and checkpoint slides, to read with the video.
- **Lecture 21 notes, CMU 15-445 Fall 2025** — https://15445.courses.cs.cmu.edu/fall2025/notes/21-logging.pdf
  Focus on: section 2, the STEAL and FORCE policies, which section 1.2 uses.
- **Lecture 22 notes, Database Crash Recovery, CMU 15-445 Fall 2025** — https://15445.courses.cs.cmu.edu/fall2025/notes/22-recovery.pdf
  Focus on: the LSN types, non-fuzzy and fuzzy checkpoints with CHECKPOINT-BEGIN and CHECKPOINT-END, and the ARIES passes. Read it after section 1.5, to compare ARIES with PostgreSQL.

---

## Cheatsheet

```
BASE VERSION: PostgreSQL 17.11, source tag REL_17_11. 18 differences marked "18:"

WHERE A WRITE IS, AND WHAT KEEPS IT
  process memory    lost by every crash         f.write() buffer
  page cache        kept by a process crash     after os.write
  drive cache       kept by an OS crash in      after fsync on macOS
                    the model only. Apple: an OS crash can lose it
  stable media      kept by a power loss        after F_FULLFSYNC on macOS,
                                                fsync on Linux ext4, barriers on
  one killed backend  whole server restarts, crash recovery, 57P02 to clients

THE TWO RULES (ARIES 1992, section 1.1)
  WAL rule          log record durable before the data page it describes
  commit rule       log durable up to the commit record before the reply
  STEAL, NO-FORCE   pages may reach disk before commit, need not at commit

POSTGRESQL COMMIT ORDER (xact.c REL_17_11)
  commit record 1431 -> XLogFlush 1491 -> pg_xact 1497 -> sync standby 1546
  -> visible 2349 -> reply
  LSN               byte offset into the WAL. lsn2 - lsn1 = WAL bytes
  sync_commit off   visible before durable: no external action on it
  no shell          pg_walinspect: pg_get_wal_stats(start, end)

SYNC CALLS
  macOS durable     fcntl.fcntl(fd, fcntl.F_FULLFSYNC)   Go: os.File.Sync
  macOS not         os.fsync(fd), SQLite default, PG default for WAL and data
  PG on macOS       wal_sync_method=fsync_writethrough: F_FULLFSYNC for WAL
                    and for checkpoint data file syncs (fd.c 426-431)
  Linux durable     os.fsync(fd)
  new file, rename  also sync the directory
  M2 cost           os.fsync 95-110 us, F_FULLFSYNC 2.85-2.88 ms   (elite-performance 5.6)
  M4 Pro cost       os.fsync 25-31 us,  F_FULLFSYNC about 4.0 ms   (this course's research)
  after fsync EIO   stop. Never retry. PostgreSQL PANICs since 2019-02-14
  PANIC text        could not fsync file "...": %m   (data: sync.c, WAL: xlog.c)
  NVMe path         ext4 fsync -> jbd2 commit REQ_PREFLUSH|REQ_FUA ->
                    NVMe Flush + FUA bit, only if the drive reports a cache
  Linux checks      /sys/block/<disk>/queue/write_cache, nvme id-ctrl -H (vwc bit 0),
                    hdparm -I, sdparm --get=WCE, pg_test_fsync -f, diskchecker.pl
  NFS               mount hard, export sync. O_DIRECT is not O_SYNC
  EBS               gp3 single-digit ms, 3,000 IOPS; io2 BX < 500 us at 16 KiB

POSTGRESQL 17 DEFAULTS (same in 14 and 18 unless noted)
  synchronous_commit on       off loses up to 3 x wal_writer_delay = 600 ms
  wal_sync_method             fdatasync on Linux, open_datasync on macOS
  macOS, flush the drive      fsync_writethrough: 250 ops/s against 45,480 (M4 Pro, 14.24 tool)
  full_page_writes on         torn data pages restored from WAL. Always on in RDS
  data_checksums              off in 14 and 17 initdb. 18: on
  data_sync_retry off         PANIC on a failed data flush
  log_checkpoints on          off in 14. lsn fields since 16
  checkpoint_timeout 5min, max_wal_size 1GB, checkpoint_completion_target 0.9
  commit_delay 0 us, commit_siblings 5
  PostgreSQL 14 final release 2026-11-12, 17 final release 2029-11-08

TORN WRITES
  sector 512 B, PostgreSQL page 8,192 B = 16 sectors
  short write       caught by the length check
  hole, right size  caught only by the CRC. Random damage passes 1 in 2^32
  recovery          stop at the first bad entry, cut, sync the cut
  PG WAL record     24-byte header, CRC-32C, xl_prev chain
  BBU controller    no protection unless it writes full 8 kB pages
  InnoDB 8.4        doublewrite ON, 2 files, 128 pages. AWS torn write
                    prevention removes it
  Aurora, AlloyDB   no page writes from the database host: torn pages move
                    into the storage service
  17.11             fix: full page images of visibility map pages

RECOVERY
  lab               replay the log after the offset in keydir.ckpt
  lab ckpt steps    sync log, write tmp, sync tmp, rename, sync directory
  PG starts at      REDO point = WAL insert position at checkpoint START,
                    valid only after that checkpoint COMPLETES
  PG worst replay   (1 + checkpoint_completion_target) intervals = 1.9
  PG size trigger   max_wal_size / 1.9: 1 GB -> 33 segments = 528 MB
  max_wal_size      a soft limit
  PG restart        redo + one end-of-recovery immediate wait checkpoint
  PG redo (Pettus)  5.6 to 7.7 s per GB of ordinary WAL, no hardware given
  page images       29 MB WAL, 71.54% images; wal_compression on: 10 MB,
                    23.86% (Rogov, PG 14.7, pgbench -t 20000)
  RDS               same redo as your own server
  Aurora            "Nothing is required at database startup"
  17.6              fix: checkpointer fsync queue over 1 GB, infinite loop

CHECKPOINT SIGNALS ON 17
  log_checkpoints   complete line ends "lsn=..., redo lsn=..."
  warning           "checkpoints are occurring too frequently", < 30 s.
                    Not set by default on RDS
  counters          pg_stat_checkpointer num_timed, num_requested.
                    pg_stat_bgwriter has no checkpoint columns on 17
                    18: num_done, slru_written
  who writes        pg_stat_io writes and fsyncs per backend_type
  no shell          pg_control_checkpoint(): redo_lsn
  startup log       redo starts at / invalid record length ... expected at
                    least 24, got 0 / redo done at

GROUP COMMIT
  one sync per put  max = 1 / t_sync        2.85 ms -> 351/s
  group, W writers  max = W / t_sync        16 writers -> 5,616/s
  latency cost      up to 2 x t_sync        5.7 ms
  ack only after a sync that started after the append
  PG commit_delay   start at half the pg_test_fsync flush time
  MySQL durable     sync_binlog=1 and innodb_flush_log_at_trx_commit=1
  fsync=off         corruption, not a loss window

COMMITS IN YOUR CODE
  Django            autocommit: one commit per query. atomic: one per block
  psycopg 3         a transaction from the first statement until commit()
  10 writes, 1 ms   autocommit 10 ms of flush wait, atomic 1 ms
  wait events       IO/WalSync (Linux fdatasync), IO/WalWrite (macOS
                    open_datasync), LWLock/WALWrite (group follower)
  RDS, Aurora       IO:WALWrite, IO:XactSync. Fix: fewer commits
  flush time        pg_stat_wal wal_sync_time / wal_sync, track_wal_io_timing
                    on. open_datasync: read wal_write_time. 18: pg_stat_io

DURABILITY YOU GIVE UP ON PURPOSE
  SET LOCAL synchronous_commit = off    one transaction, up to 600 ms lost
  CREATE UNLOGGED TABLE                 no WAL, empty after a crash, empty
                                        on standbys, kept on clean shutdown
  LangGraph durability                  exit, async (default), sync
  PostgresSaver                         one commit per put, one per put_writes, inferred

TEST TOOLS (LINUX)
  LazyFS, dm-log-writes, dm-flakey, diskchecker.pl

THE BOUNDARY SENTENCE
  when OK is sent, which crash kinds it survives, what recovery returns,
  what is not covered. Back it with a crash matrix: 57 points, 231 recoveries,
  counts asserted by the self-test, which passed on 2026-10-20
```

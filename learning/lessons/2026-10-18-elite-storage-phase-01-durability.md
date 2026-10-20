A small order store runs on your Mac. It appends each put as one entry, a log record, to the end of one file, the log. A client sends put order:1041, and the store replies OK. It sends put order:1042, and the store replies OK again. One millisecond later the power fails, and on restart both orders are gone. The client holds a receipt for each one.

The store wrote each entry, called os.fsync, and only then replied. On the Apple M2 that the earlier course measured, that call took about 0.1 ms. But on macOS os.fsync hands the data to the drive and returns. The drive may write it to flash later. This lesson follows those two orders down to the disk and back through recovery.

The same questions come up in the PostgreSQL behind your services, so each part also shows where you meet the idea at work, what you see when it goes wrong, and the decision it changes. Every PostgreSQL default, view, log line and source line here is from PostgreSQL 17.11, unless the text names another version. Where 14 or 18 differs, one sentence says so.

### What you must know

- An OK is safe once its log record reaches storage that keeps data without power. Other writes can wait. Say what must be durable at commit.

- Not every sync call reaches flash. Plain fsync on a Mac does not. One slow sync can serve many waiting commits. Pick the sync call, stop on its error, and keep throughput.

- A length check catches a short write. Only a checksum, a value computed from the bytes, catches wrong bytes. Make recovery stop at the right place.

- Recovery replays the log since the last finished checkpoint began. That checkpoint wrote all older changes to disk. Predict restart time and read a checkpoint.

- Killing the process tests only a process crash. A durability promise needs its own test for each crash kind. Write and test your store's promise.

## Where can a write be when the crash comes?

A write moves down through three places: the process, the kernel's page cache and the disk. The disk itself has two parts, so the figure shows four steps. Each kind of crash erases a different set of them.

- process memory Python's f.write() often only fills the program's own buffer until flush()

- page cache os.write copies the bytes into the kernel's memory

- disk: drive cache volatile memory inside the drive

- disk: stable media the flash, which keeps data without power

The three places a write moves through. The disk has two parts.

The page cache is the kernel's copy of recently used file pages. A page that holds bytes not yet on the device is a dirty page, and the kernel writes it back later. The disk has a volatile cache inside the drive and the stable media behind it.

| Crash kind | Example | What survives |
| process crash | kill -9, an out-of-memory kill, a segfault | page cache and disk |
| OS crash | a kernel panic, a hard reset with power still on the drive | the disk, including the drive's cache |
| power loss | a pulled cord, a failed power supply, a dead cloud host | only what reached stable media |

The OS crash row is the general model. Apple documents a weaker rule for a Mac, and the sync part below quotes its fsync(2) page. So the lab store does not promise the OS crash case for plain fsync on a Mac.

Two words now mean different things. An acknowledged write is one the store has told the client is done. A durable write is one that survives the crash kinds you name. The line between those crash kinds is the store's durability boundary, and the last part of this lesson writes it down and tests it.

Suppose the store calls os.write for order:1041 and replies OK with no sync at all. A kill -9 of the store does not lose the order, because the page cache belongs to the kernel and the kernel did not crash. A kernel panic or a power failure can lose it. Whether it does depends on whether the kernel had already written that page back.

In the running case, os.fsync moved both orders out of the page cache into the drive cache. The power loss then erased the drive cache, so both orders were lost.

### Where you meet the three crash kinds at work

The three names map onto events you see in production. This mapping follows from the definitions above, and the event names are examples.

| Event in production | Crash kind | What survives |
| the Linux OOM killer kills a PostgreSQL backend, or a container hits its memory limit | process crash | page cache and disk |
| a kernel panic, or a node that hangs and is hard-reset | OS crash | disk, including the drive's cache |
| a host loses power, or a cloud instance's hardware fails | power loss | only what the device wrote to stable media |

One killed backend restarts the whole PostgreSQL server. The postmaster is the first process of the server, and it starts all the others. It cannot know whether the dead process damaged shared memory, so it stops every session and runs crash recovery. This is the sequence in the PostgreSQL 17 log. The texts are the format strings in the source, and the PID and SQL are an example.

LOG:  server process (PID 4711) was terminated by signal 9: Killed
DETAIL:  Failed process was running: UPDATE orders SET status = 'paid' WHERE id = 1041
LOG:  terminating any other active server processes
LOG:  all server processes terminated; reinitializing
LOG:  database system was interrupted; last known up at 2026-10-20 10:00:00 UTC
LOG:  database system was not properly shut down; automatic recovery in progress

Every other client gets the warning "terminating connection because of crash of another server process", with SQLSTATE 57P02, and then loses its connection. The setting restart_after_crash, on by default, makes the server restart by itself. So no commit made with synchronous_commit = on is lost, because its WAL was flushed before the reply and the kernel kept the page cache. A commit made with off can be lost, because its WAL may still be in shared memory, per the comment at xact.c lines 1504 and 1505. But every connection breaks at once, and your connection pool sees a wave of errors.

The PostgreSQL docs show the kernel's side of this event: Out of Memory: Killed process 12345 (postgres). They suggest vm.overcommit_memory=2 to make the OOM killer much less likely. So when every connection fails at the same moment, look for this kernel line before you look for a disk fault.

Evidence
The log lines: postmaster.c lines 3091, 3094, 2882 and 3363, xlog.c line 5461 and xlogrecovery.c line 948, at REL_17_11. The text after the colon comes from the C library's strsignal, through pg_strsignal. glibc on Linux prints Killed, and macOS prints Killed: 9. The client warning: postgres.c lines 2960 to 2962 and errcodes.txt line 430. restart_after_crash: the 17 sample configuration file, line 823. The kernel line and vm.overcommit_memory=2: PostgreSQL 17 docs, section 18.4.4, "Linux Memory Overcommit". The production mapping is inferred from the crash-kind definitions.

Go deeper: the running case as times, the measured costs from the earlier course, a managed database's extra cache, and what this lesson leaves for later
The running case, as times. They are an example built from the M2 cost of os.fsync, about 0.1 ms:

- t = 0.00 ms put order:1041: write to the page cache, then fsync to the drive cache.

- t = 0.11 ms OK sent for order:1041, and put order:1042 starts the same way.

- t = 0.22 ms OK sent for order:1042.

- t = 1.22 ms The power fails. The drive cache is volatile and is erased.

- restart The log on flash ends before order:1041, so both orders are gone.

The earlier course, "Performance, concurrency and the machine", measured what each step down costs on its Apple M2, as medians per run. A page-cache read took 1.5 µs. A read from the SSD took 88.7 to 89.8 µs, and a page there is 16 KiB. After a 4 KiB write, os.fsync took 95 to 110 µs and fcntl(F_FULLFSYNC) took 2.85 to 2.88 ms. That course's Phase 1 also taught that latency is a distribution, that a closed-loop load generator hides stalls, and that you write a prediction before each run. In this lesson, "the M2" always means that course's machine. This course's research measured the same sync calls on a second Mac, "the M4 Pro", and keeps each machine's numbers separate.

A managed database can add a place. On Aurora, AWS states that "each DB instance's page cache is managed in a separate process from the database". So that cache can survive a crash of the database process. It keeps reads fast after a restart, and it is not where durability comes from. The part on managed PostgreSQL below shows where Aurora keeps the durable copy. This is a vendor page.

Every promise in this lesson is about one machine. Phase 5 of this course, "Replication, failover, backups and pooling", teaches replicas. Its section 5.1 says what a replica has when the primary acknowledges a write. Its section 5.4 says what each synchronous_commit level waits for when the server has standbys. So this lesson names the PostgreSQL facts it needs about replicas, and no more. Phase 2 of this course covers the structures built on the log, such as B-trees and LSM trees.

## What must be durable before the store replies OK?

One transaction changes many pages, and a crash in the middle would leave some new and some old. A write-ahead log, WAL for short, is a file the database only appends to, one record per change. It turns every change into one append, so a commit needs one small write and one sync.

Predict: in PostgreSQL a transaction updates one row and commits. When the client gets its reply, which bytes must be on stable media: the changed table page, the log record, or both?
Only the log record, because recovery can apply the change again from the log. Most people answer both, because a later read returns the table page.

Two rules make that safe.

- The WAL rule: the log record of a change reaches stable media before the changed page may replace the old page on disk.

- The commit rule: a transaction is complete only when its commit record, and every log record before it, is on stable media. So the database forces the log up to that record at commit.

If a crash comes before the page is written, recovery reads the log and applies the change again. That replay is called redo.

- 1 change the page the data page is dirty, in memory

- 2 append a WAL record into the WAL buffer, in memory

- 3 write and sync the WAL the log reaches stable media

- 4 reply COMMIT the acknowledgment

- 5 write the data page at any time, even before step 3

One UPDATE and COMMIT in a WAL database, in order.

A crash after step 4 is repaired by redo. A crash before step 3 sent no reply, so recovery treats the transaction as not committed.

### A data page can reach the disk before its commit

Step 5 has no fixed time, and it can even come before step 3. That is safe because of the WAL rule. Before the server writes a changed page, it flushes the WAL up to that page's last change. That flush does not need the commit record. In PostgreSQL three kinds of process write dirty pages.

| Process | What it is | When it writes a dirty page |
| checkpointer | the process that runs checkpoints, which a later part defines | during a checkpoint |
| bgwriter | a background process | when the page is likely to be evicted soon |
| backend | the server process of one client connection | when it must evict the page itself |

So a page with an uncommitted change can be on disk. Two names describe this design. STEAL lets the database write uncommitted changes to disk before the transaction completes. NO-FORCE means changes are not required to be on disk at commit. The WAL rule is what makes STEAL safe, and Phase 2 comes back to the line in the buffer manager that enforces it.

A log sequence number, LSN for short, is a byte offset into the WAL, so two LSNs give the WAL bytes between them. PostgreSQL prints an LSN as two hexadecimal numbers with a slash, such as 0/3DF708D8. In PostgreSQL 17 the durability point is XLogFlush, which flushes the WAL up to the commit record's LSN. Three functions show the current positions, so you can read them on any server.

| Function | Position |
| pg_current_wal_insert_lsn() | insert |
| pg_current_wal_lsn() | write |
| pg_current_wal_flush_lsn() | flush |

### A reply before the flush: what PostgreSQL lets you choose

The parameter synchronous_commit is on by default in PostgreSQL 17, as in 14 and 18. With it, a commit waits for the local WAL flush. With off, the commit replies at once. The WAL writer, a background process that flushes WAL that no commit has flushed yet, flushes it later. The maximum delay is three times wal_writer_delay, which is 200 ms by default, so the window is 3 × 200 ms = 600 ms. A crash in that window can lose recent commits, and the database stays consistent, as if those transactions had been aborted.

That setting has a consequence that its docs entry does not state. In PostgreSQL, with off, the step that makes new rows visible to other sessions does not wait for the flush. This follows from the order of steps in xact.c, and was not run. So other sessions can read the new rows before they are durable. A crash in the next 600 ms can then remove rows that another session already read. The docs give the rule that follows: asynchronous commit "should not be used if the client will take external actions" that rely on the commit. A webhook or a queue message sent after such a read is that kind of external action.

You meet those external actions in your own code. Django's transaction.on_commit() runs a callback "only if the transaction successfully commits". Django names "a background task, an email notification, or a cache invalidation" as the examples. With synchronous_commit = off, that callback can run before the commit is durable. That combination was not run. A crash can then remove the row after the email went out. So keep synchronous_commit = on for any transaction that has an on_commit hook, a webhook or a queued job. An AI agent that saves its state and then calls a tool is the same case, and the last part writes its boundary.

### The failure: reply first, log later

A setting that replies before the log flush keeps the database consistent after a crash, so nothing looks wrong. MariaDB's innodb_flush_log_at_trx_commit=0 flushes the log about once a second, and a Galera cluster with it lost nine acknowledged values in a one-minute test. Galera Cluster is a MariaDB setup that copies each write to several nodes, and MariaDB's own Galera page recommended that setting at the time. NATS JetStream, the part of the NATS message system that stores messages on disk, calls fsync every two minutes by default, but acknowledges each message at once. Simulated power failures in one test run lost 131,418 of 930,005 messages, about thirty seconds of writes. Recovery replayed both logs correctly, and only the part that never reached the disk was lost. The lost commits are found only by a client that kept its receipts.

### The lab store: the log is the data

The store of this lab has no separate data file. The log is the data. This is the Bitcask design of Sheehy and Smith at Basho Technologies, a company paper, not peer reviewed. Bitcask appends every put to a data file and keeps an in-memory index called the keydir. The keydir maps each key to the file, offset and size of its newest entry. A delete is a put of a special tombstone value. The paper says recovery needs no replay, because the data files are the log. But the keydir still has to be rebuilt by reading the log after a restart, which the checkpoint parts below cover.

The lab differs from the paper in two places, on purpose. It stores a 64-bit sequence number in place of the paper's 32-bit timestamp, so recovery can refuse an entry out of order. The paper also does not say how to handle a half-written last entry, and the lab defines that rule in the torn-write part. The paper does not name its CRC algorithm. The lab uses zlib.crc32, the IEEE CRC-32. A CRC, a cyclic redundancy check, is a kind of checksum, and the torn-write part explains how recovery uses it.

Here is the store's put, from kvlog.py:409. The comments are changed, and the size checks and the error handler around the append are removed. The order of steps is unchanged:

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
            self._wait_durable(offset + len(buf))   # group commit
        self.hook("put.synced")
        with self._index_lock:
            cur = self.keydir.get(k)
            if cur is None or loc.seq > cur.seq:
                self.keydir[k] = loc                # visible to readers
        self.hook("put.indexed")
        return Receipt(seq, offset, offset + len(buf))

Each self.hook(...) line is a crash point, and the crash matrix of the last part crashes the store at every one of them. The index is updated after the sync, not before. So a reader never sees a value that a crash can still take back.

  At commit only the log must be durable, because recovery replays it.

  A reply before the log flush stays consistent after a crash and still loses commits.

  Run uv run python phase01_durability/crash_matrix.py --list, and find crash points 3 to 7.

Evidence
The two rules: ARIES, Mohan and others, ACM TODS 1992, section 1.1, journal pages 97 and 98. The three processes: Rogov, "PostgreSQL 14 Internals", section 10.5, page 176. The same three write pages in PostgreSQL 17. STEAL and NO-FORCE: CMU 15-445 Fall 2025 notes for Lecture 21. The WAL flush before a page write: bufmgr.c lines 3910 to 3927 at REL_17_11, the comment "Force XLOG flush up to buffer's LSN" and the call XLogFlush(recptr). LSN as a byte offset: PostgreSQL 17 docs, section 28.6. The three functions: section 9.28. synchronous_commit and the 600 ms window: PostgreSQL 17 docs, sections 19.5 and 28.4, and the 17 sample configuration file, lines 231 and 249. The visibility order is inferred from xact.c, and not run. Django: the 5.2 page "Database transactions". The combination with asynchronous commit is inferred, and not run. Galera: Jepsen "MariaDB Galera Cluster 12.1.2", Kyle Kingsbury, 2026-03-16, section 3.1. The report's second loss, in its section 3.2, happened with the setting at 1 and has no root cause, so this lesson does not use it. MariaDB later changed its Galera page to recommend the default of 1, seen in archived copies dated 2026-03-08 and 2026-06-11. The new page warns that 0 and 2 can lose acknowledged transactions. That the change followed the report is inferred from the timing only. NATS: Jepsen "NATS 2.12.1", 2025-12-08, section 3.4.

Go deeper: the LSN in pg_waldump and pg_walinspect, PostgreSQL 17's commit order, MariaDB's values, and a log that writes too much per append

The LSN, seen in the WAL

Rogov ran one UPDATE and COMMIT on PostgreSQL 14.7. The insert LSN moved from 0/3DF708D8 to 0/3DF70948, which is 112 bytes. pg_waldump, the tool that prints WAL records, showed two records in that range, here shortened to the fields this lesson uses. The source is Rogov, section 10.2, pages 168 and 169.

rmgr: Heap len (rec/tot): 69/ 69, tx: 886, lsn: 0/3DF708D8, prev 0/3DF708B0, desc: HOT_UPDATE ...
rmgr: Transaction len (rec/tot): 34/ 34, tx: 886, lsn: 0/3DF70920, prev 0/3DF708D8, desc: COMMIT ...

Each record names its resource manager, the code that replays it, and its length and transaction. Each record's prev field holds the LSN of the record before it, so the WAL is a chain. The arithmetic of the two records:

start of second − start of first = 0x3DF70920 − 0x3DF708D8 = 0x48 = 72 bytes
second record ends 0x28 = 40 bytes later
69-byte record takes 72, 34-byte record takes 40, and 72 + 40 = 112

So each record is padded to a multiple of 8 bytes on a 64-bit machine. Verified from xlog.c line 1117 at REL_17_11, size = MAXALIGN(size);.

On a managed database you cannot run pg_waldump, because you have no shell on the server. Since PostgreSQL 15, the extension pg_walinspect gives the same facts in SQL. On 17, select * from pg_get_wal_stats('0/3DF708D8', '0/3DF70948') returns one row per resource manager, with record bytes and full page image bytes. Execute is granted to the role pg_read_server_files, per pg_walinspect--1.0.sql, lines 78 to 96, at REL_17_11. Whether RDS and Aurora offer this extension was not checked. Check it with select * from pg_available_extensions where name = 'pg_walinspect'.

The commit inside PostgreSQL 17

Only after XLogFlush does the server make the rows visible and reply. pg_xact is the set of files that holds each transaction's outcome, and Phase 3 shows how readers use it. The order, from RecordTransactionCommit and CommitTransaction in xact.c at tag REL_17_11:

| Step | Function | What it does | Line |
| 1 | XactLogCommitRecord | commit record into the WAL buffers | 1431 |
| 2 | XLogFlush | WAL flushed up to that record. The durability point | 1491 |
| 3 | TransactionIdCommitTree | "committed" written in pg_xact | 1497 |
| 4 | SyncRepWaitForLSN | wait for a standby, if one is configured | 1546 |
| 5 | ProcArrayEndTransaction | other sessions now see the rows | 2349 |
| 6 | reply to the client | the acknowledgment |  |

PostgreSQL 18.0 has the same order, at lines 1442, 1502, 1508, 1557 and 2389. With synchronous_commit = off, step 2 becomes XLogSetAsyncXactLSN at line 1512, and the WAL writer flushes later. Step 5 still runs at once. Step 4 waits only when a standby, a server that replays this server's WAL, must confirm the commit.

Right before step 1, at line 1426, the backend sets the flag DELAY_CHKPT_START, and it clears the flag after step 3, at line 1529. A checkpoint that starts in that window waits. Otherwise it could set its recovery start point, the REDO point of the checkpoint parts below, between the commit record and the pg_xact update. A crash a little later would then lose the commit. The source is the comment at lines 1407 to 1422. In 14 the same guard is a boolean, delayChkpt, at xact.c line 1350 of REL_14_24.

PostgreSQL 17 also shows this wait. A checkpointer that waits for the flag reports the wait event CheckpointDelayStart or CheckpointDelayComplete, of type IPC, per wait_event_names.txt lines 113 and 114 at REL_17_11 and the 17.0 release notes. A wait event is the name a session reports in pg_stat_activity while it waits, and the commit-count part below shows how to read them.

What MariaDB's setting 0 does

In the Galera test, Jepsen crashed the database processes of every node at about the same time, which is not a power loss. With the setting at 1 the loss became much rarer. innodb_flush_log_at_trx_commit controls the same moment in InnoDB. The MariaDB InnoDB system variables page describes four values, 0 to 3. With 1, the default, the log is written and flushed at each commit. With 2, it is written at each commit and flushed on a timer. With 0, nothing happens at commit, and the log is written and flushed about once a second. With 3, the log is flushed at both the prepare step and the commit, which is slower than 1 and keeps the same guarantee. The page warns that with 0 a server crash can erase the last second of transactions. So with 0 the reply comes before the log is durable, which breaks the commit rule. A crash of the server process alone is enough, because the log is not yet in the page cache. That last point is inferred from the definition of value 0.

An append is cheap only if nothing else is written with it

Roblox's outage of October 2021 lasted 73 hours. Roblox uses Consul for service discovery and as a key-value store. Consul stores its Raft log, the replicated log of its operations, in BoltDB, an embedded key-value library. HashiCorp and Roblox engineers found that "This 4.2GB log store is only storing 489MB of actual data". BoltDB tracks free pages in a freelist, and that list had grown to 7.8 MB. So for every log append, "a new 7.8MB freelist was also being written out to disk". The lesson for a log: measure the bytes written per append, not only the bytes appended. The lab entry writes 20 header bytes plus the key and value, and nothing else.

## How far does one sync call move the bytes?

The commit rule says to force the log to stable media. fsync is the system call that asks the kernel to write a file's dirty pages to the device. It either stops at the drive's cache, or it also asks the drive to flush that cache.

Predict: the running case called os.fsync after each put, on a Mac. Does that survive a power loss? Now move the same code to a Linux server with ext4. Does it survive there?
On the Mac, it is not promised. On Linux with ext4, yes, if three conditions hold. Barriers are on. The kernel sees the drive's cache, or the drive has none. The drive honours the flush. Most people give the same answer twice, because the code and the call name are the same.

| Call | How far it moves the bytes | Survives a power loss |
| macOS os.fsync | to the drive cache, then it returns | no |
| macOS fcntl(fd, F_FULLFSYNC) | to the drive, then asks the drive to flush | yes, if the drive honours the flush |
| Linux os.fsync on ext4 | the file system sends the drive's flush command | yes, with barriers on, a cache the kernel sees, and a drive that honours the flush |

The mechanism differs by platform:

- Apple's fsync(2) page says the drive may not physically write the data to the media for quite some time. So after a power loss or an OS crash, some or none of it may be written.

- F_FULLFSYNC, a command of fcntl(2), does what fsync does and then asks the drive to flush to permanent storage.

- The name does not tell you the call. CPython's os.fsync is plain fsync(), while Go's os.File.Sync is F_FULLFSYNC on macOS.

- Linux has no F_FULLFSYNC, because the file system sends the flush itself when write barriers are on.

So a Python service on a Mac must call F_FULLFSYNC itself, and a Go service there already asks for the flush. The lab's shared/durable.py makes this choice for every durable sync of the course: F_FULLFSYNC on macOS, os.fsync on Linux.

On Linux the lab calls os.fsync, because Linux has no F_FULLFSYNC and the file system sends the drive's flush command itself. The PostgreSQL 17 docs, section 28.1, name ZFS and ext4 as examples of file systems that can send it. The same section says that behind a controller with a battery-backed cache, turning write barriers off can regain speed, and that the battery must then remain functional. XFS is not named there, and this course did not check it. The decision, from durable.py:92:

# from shared/durable.py:92, plan(). Docstring removed, logic unchanged
    if mode not in SYNC_MODES:
        raise ValueError(f"unknown sync mode {mode!r}, expected one of {SYNC_MODES}")
    platform = platform or sys.platform
    if mode == "none":
        return "none"
    if mode == "full" and platform == "darwin":
        return "F_FULLFSYNC"
    return "fsync"

durable_sync follows Go's rule for ENOTSUP and falls back to plain fsync. Unlike Go, it prints a warning once, because the guarantee is now weaker.

  95 to 110 µs M2, os.fsync, stops at the drive cache

  2.85 to 2.88 ms M2, F_FULLFSYNC, flushes the drive

  26 to 30 times the price of the durable call

Medians per run of one 4 KiB write and a sync on the M2, from the earlier course.

### Where you meet it on your own Mac

Other software on your Mac makes the same choice, and its default is the fast one:

- SQLite. PRAGMA fullfsync decides whether SQLite uses F_FULLFSYNC, and the flag is off by default. PRAGMA checkpoint_fullfsync does the same for checkpoints only, and is also off by default. So upstream SQLite with default settings uses plain fsync on a Mac, per full_fsync() in its os_unix.c. The build that Apple ships with macOS was not checked.

- A Linux virtual machine. Docker Desktop and similar tools run Linux containers inside a virtual machine on the Mac. A guest's fsync reaches the Mac's drive only as far as the virtual disk lets it. Apple's Virtualization framework offers three modes for a disk image. Which mode Docker Desktop chooses was not checked, so treat a PostgreSQL container on a Mac as a development database.

- full "Synchronizes data to the permanent storage holding the disk image".

- fsync uses "the system's best-effort synchronization mode".

- none "Disables data synchronization".

- PostgreSQL itself. Its WAL sync call is the setting wal_sync_method, and on macOS the default is open_datasync. Its 22 µs timing suggests that it does not flush the drive cache, which is inferred. The method that does, fsync_writethrough, calls F_FULLFSYNC. The 14.24 pg_test_fsync measured it on the M4 Pro. It managed 250 syncs per second against 45,480 for the default, so it is 45,480 / 250 = 182 times slower. With the default, the checkpoint's syncs of the data files do not flush the drive either, per fd.c lines 426 to 431.

So a default PostgreSQL 17 on your Mac commits in about 22 µs on the M4 Pro, measured with the 14.24 tool. Those commits are not promised to survive a power cut. That is fine for a development laptop, and it is the wrong model of a production server.

### From fsync to the device on a Linux server

Production runs on Linux, so here is what one fsync becomes on the way down. The Linux block layer gives a file system two tools. REQ_PREFLUSH asks the device to flush its volatile cache before a write starts. REQ_FUA, forced unit access, marks a write that may complete only when the data is on non-volatile storage. This is the path for ext4 on an NVMe drive, in Linux v6.12.

- fsync(fd) ext4_sync_file waits for the journal commit

- jbd2 commit block written with REQ_PREFLUSH | REQ_FUA, only when the barrier mount option is on

- block layer does the drive report a volatile write cache? If no, an empty flush finishes at once

- NVMe driver a flush becomes the NVMe Flush command, and FUA sets the FUA bit of the write

- drive writes its cache to flash, then completes

One fsync on ext4 with barriers on, down to an NVMe drive.

The branch in the middle is set by one test in the NVMe driver. The driver tells the block layer that the drive has a write cache, and supports FUA, only if the drive reports a volatile write cache. For a device with no volatile cache, the block layer finishes empty flush requests itself and strips the flush and FUA flags. So on a drive with a cache, the journal commit costs one flush and one FUA write. On a drive that reports no cache, it costs no flush at all.

- A fast fsync can mean that no flush was sent. That fsync is cheaper on such a drive is inferred from the block layer code, and not measured. Such a drive is safe only if it really keeps written data through a power loss.

- Power-loss protection. Enterprise SSDs with power-loss protection, PLP for short, are sold as keeping their cache through a power loss. Check what a drive reports with nvme id-ctrl -H /dev/nvme0, from the nvme-cli package, and read bit 0 of vwc. With -H it prints "Volatile Write Cache Present" or "Not Present". The other bits describe the Flush command, so a nonzero value alone does not mean a cache.

These are the checks on a Linux server.

| What you check | Command | What it tells you | Source |
| the kernel's view of the drive cache | cat /sys/block/nvme0n1/queue/write_cache | write back or write through. Writing to the file changes only the kernel's view, not the device | kernel ABI, sysfs-block |
| what an NVMe drive reports | nvme id-ctrl -H /dev/nvme0, bit 0 of vwc | whether the drive says it has a volatile write cache | nvme-cli source, nvme-print-stdout.c at v2.11. The driver test above reads the same bit 0 |
| a SATA drive's cache | hdparm -I /dev/sda | a * next to "Write cache" means it is on | PG 17 docs, 28.1 |
| a SCSI or SAS drive's cache | sdparm --get=WCE /dev/sdb | whether the write cache is enabled | PG 17 docs, 28.1 |
| the real flush cost | pg_test_fsync -f /path/on/the/wal/disk/test.out | the time per sync method, on the WAL file system | PG 17 docs, pg_test_fsync |
| whether flushed data survives | diskchecker.pl, with a real power cut | the docs name it as a test of reliable I/O | PG 17 docs, 28.1 |

The sysfs-block ABI file warns about one change. Setting write_cache from write back to write through "will also eliminate cache flushes issued by the kernel." So a drive with a volatile cache then gets no flush commands, and fsync can return while the data is still in that cache.

### On a cloud volume

What a flush on a cloud volume promises was not checked. No first-party statement was found for Amazon EBS or Google Persistent Disk. Treat it as a question for your provider, and test it. Its cost is documented. Amazon EBS gp3 gives "single-digit millisecond latency", with 3,000 I/O operations per second, IOPS, included. io2 Block Express is "designed to deliver an average latency of under 500 microseconds for 16KiB I/O operations". So one WAL flush on gp3 likely takes 1 to 9 ms. This lesson uses 1 ms, the best case of that range. That is about 45 times the 22 µs default commit on the M4 Pro, because 1,000 / 22 = 45. That figure is inferred, and not measured. The group commit part shows why that makes the number of commits matter more on a cloud volume. Run pg_test_fsync on the volume to get the real number.

### A flush is a request

Even F_FULLFSYNC only asks the drive to flush. A test cut the power to 15 SSDs while flushes were issued, and 13 of them failed in some way. So only a power-cut test of your own device shows what its flush does.

LiveJournal lost power to every machine in its data center, as its post-mortem of January 2005 reports. Another customer there had pressed the emergency power-off button by accident. After the restart, the team restored a couple of database machines from backup, because their data was damaged. Their disk controller cards had write caches with battery backup. But the drives behind those cards still had their own drive caches on. The post links the damage to those drive caches and calls them a mistake. The team had also not turned on the option to sync MySQL's binary log, a second log, to disk. So the restored clusters lost a few transactions from right before the power loss. The team then planned to turn off the drive caches. It also planned to cut power during heavy writes on all its hardware, and then check the disks.

Evidence
Apple fsync(2) and fcntl(2) man pages in the xnu source at tag xnu-12377.121.6, and in the macOS 26.5 SDK. The fcntl.2 lines are 207 to 245. The page also warns: "This is not a theoretical edge case." CPython and Go call sites: verified from the source at the tags in the table below by this course's research. M2 costs: the earlier course, elite-performance section 5.6, 2026-09-25. SQLite: sqlite.org, "Pragma statements". The virtual disk modes: Apple's developer documentation for VZDiskImageSynchronizationMode. PostgreSQL on the M4 Pro: pg_test_fsync -s 3 from PostgreSQL 14.24, run by this course's research on 2026-10-17. The 17 default and the data-file syncs: xlogdefs.h lines 75 to 81 and fd.c lines 426 to 431 at REL_17_11. That a 17 server picks open_datasync on macOS is inferred from that code, and not run on 17. The NVMe path: Linux v6.12, drivers/nvme/host/core.c lines 812, 980 to 981 and 2188 to 2191, fs/jbd2/commit.c lines 152 to 154, fs/ext4/fsync.c lines 111 to 113 and 171, and the kernel document block/writeback_cache_control. Whether a PLP drive reports a volatile write cache was not checked, because the driver code only shows what the kernel does with that report. The PLP claim itself was not checked either. The path holds for a journal without async_commit and without fast_commit, per fs/jbd2/commit.c line 152 and fs/ext4/fast_commit.c lines 1214 and 1215. The write_cache warning: the kernel ABI file sysfs-block. EBS: the AWS EBS User Guide pages "Amazon EBS volume types" and "General Purpose SSD volumes", vendor pages. SSD power cuts: Zheng, Qin, Tucek and Lillibridge, USENIX FAST 2013, abstract and section 1. Linux barriers: PostgreSQL 17 docs, section 28.1. LiveJournal: Brad Fitzpatrick, "Power-loss post-mortem", LiveJournal lj_dev, 2005-01-20. The post gives no date for the power cut itself, so the lesson gives the month of the post.

Go deeper: each runtime's call, the M4 Pro numbers, PostgreSQL's five sync methods, the NVMe driver test, drives that report early, and NFS, direct I/O and MySQL 8.4

What each runtime calls

| Runtime, version | Call | On macOS | Source |
| CPython 3.14.8, os.fsync | fsync() | stops at the drive cache | Modules/posixmodule.c line 3993, os_fsync_impl |
| CPython, fcntl.fcntl(fd, fcntl.F_FULLFSYNC) | F_FULLFSYNC | flushes the drive | Modules/fcntlmodule.c lines 639 to 640 export the constant |
| Go 1.24.0 and 1.27.2, os.File.Sync | F_FULLFSYNC | flushes the drive | internal/poll/fd_fsync_darwin.go line 22 |
| Go, syscall.Fsync | fsync() | stops at the drive cache | syscall/zsyscall_darwin_arm64.go lines 710 to 716 |

If F_FULLFSYNC returns ENOTSUP, for example on an SMB mount, Go falls back to plain fsync. The history of both Go changes, and an open CPython request to change os.fsync, are in the sources list.

Apple's fcntl(2) page names APFS among the file systems that support F_FULLFSYNC. The same page describes F_BARRIERFSYNC, which sends a barrier instead of a flush. A barrier keeps the order of writes, but it does not make them durable. The Linux write barriers above are a different thing with the same word.

The cost on two Macs

| Machine and call | Median per run | Conditions |
| M2, os.fsync | 95 to 110 µs | 4 KiB write, earlier course |
| M2, F_FULLFSYNC | 2.85 to 2.88 ms | ratio 26 to 30 times |
| M4 Pro, os.fsync | 25.1 and 31.2 µs | Python 3.9.6, 8 KB pwrite, macOS 26.6 |
| M4 Pro, F_FULLFSYNC | about 4.0 ms | 4,001 / 31.2 = 128 times, 4,012 / 25.1 = 160 times |

The research also measured Go's os.File.Sync on the M4 Pro at 3,981 to 4,078 µs per operation. That matches F_FULLFSYNC, as the Go source predicts. Keep each machine's numbers separate, because the two runs used different write sizes and machines.

PostgreSQL's five sync methods

| Value | What PostgreSQL does after a WAL write |
| open_datasync | opens the WAL file with O_DSYNC, so each write returns only when the data is synced |
| fdatasync | calls fdatasync(), which skips file metadata that is not needed to read the data back |
| fsync | calls fsync() |
| fsync_writethrough | asks the drive to write through its cache. On macOS that is fcntl(fd, F_FULLFSYNC) |
| open_sync | opens the WAL file with O_SYNC, which also waits for all of the file's metadata |

The default is the first supported method in a fixed list, except that Linux and FreeBSD use fdatasync. On macOS that rule picks open_datasync. These are from the PostgreSQL 17 docs, section 19.5, and from issue_xlog_fsync, get_sync_bit and xlogdefs.h at REL_17_11. The F_FULLFSYNC call is in pg_fsync_writethrough, fd.c line 466. A fresh PostgreSQL 14.24 cluster on the M4 Pro showed open_datasync with source default. That was a Homebrew x86_64 build under Rosetta. The PostgreSQL docs, section 28.1, say that on macOS you set fsync_writethrough to prevent write caching. pg_test_fsync -s 3 from 14.24 measured each method on the same Mac, one 8 kB write per operation:

| wal_sync_method | ops/sec | µs per op | flushes the drive cache |
| open_datasync, the macOS default | 45,480 | 22 | no, inferred |
| fdatasync | 42,027 | 24 | no, inferred |
| fsync | 40,138 | 25 | no |
| fsync_writethrough | 250 | 3,994 | yes, inferred |
| open_sync | 42,435 | 24 | no, inferred |
| write, no sync | 333,548 | 3 | no |

The "yes, inferred" comes from HAVE_FSYNC_WRITETHROUGH in PostgreSQL's darwin.h, line 6, and from the 3,994 µs, which matches F_FULLFSYNC. The 17 and 18 defaults on macOS are inferred to be open_datasync too, from the same source logic, and not run. Two details change how you read this table on PostgreSQL 17:

- The setting reaches the data files too. At a checkpoint, PostgreSQL syncs the data files with pg_fsync. On macOS, pg_fsync uses F_FULLFSYNC only when wal_sync_method = fsync_writethrough. Otherwise it calls plain fsync(), per fd.c lines 426 to 431.

- The 17 tool tests a slightly different path. On macOS, pg_test_fsync 17 opens its file for the open_datasync and open_sync rows with F_NOCACHE, which bypasses the macOS file cache, per pg_test_fsync.c lines 269 to 277. The server itself uses that flag for WAL only with the developer setting debug_io_direct, per get_sync_bit, xlog.c line 8659. So on 17 those two rows may differ from the server's real WAL path. The size of the difference was not measured. The 14.24 tool in the table did not use the flag on macOS.

The NVMe driver test

This is the test that sets the branch in the figure above:

/* drivers/nvme/host/core.c, lines 2188 to 2191, Linux v6.12 */
	if (ns->ctrl->vwc & NVME_CTRL_VWC_PRESENT)
		lim.features |= BLK_FEAT_WRITE_CACHE | BLK_FEAT_FUA;
	else
		lim.features &= ~(BLK_FEAT_WRITE_CACHE | BLK_FEAT_FUA);

For a device with no volatile cache, "the block layer completes empty REQ_PREFLUSH requests before entering the driver and strips off the REQ_PREFLUSH and REQ_FUA bits". For a device with a cache but no FUA support, the block layer sends a flush after the write instead. Both are from the kernel document block/writeback_cache_control. When a journal commit will send no flush, ext4's fsync sends an empty flush instead, with blkdev_issue_flush, at fs/ext4/fsync.c line 171. The flush and FUA flags are sent only when the journal has JBD2_BARRIER set, which is the barrier mount option, per commit.c line 152. A RAID controller with a battery-backup unit, BBU, keeps its cache in a power loss too. The torn-write part gives the limit of that promise for torn pages.

Drives that report early

The PostgreSQL 17 docs, section 28.1, warn that consumer IDE and SATA drives are particularly likely to have write-back caches that do not survive a power failure, and that many SSDs do not honor cache flush commands by default. The power-cut test above cut the power to 15 SSDs of 10 models from 5 vendors, with flushes issued, and 13 of the 15 showed failures. Only two SSDs of one model, and one enterprise hard disk, behaved as the flush promised. The drives date from about 2012, and modern NVMe drives were not tested.

Network file systems and direct I/O

- NFS. The PostgreSQL 17 docs, section 18.2.2.1, require the hard mount option. They also recommend the sync export option on the server. Without it, an fsync on the client "is not actually guaranteed to reach permanent storage on the server". The docs compare that to running with fsync off.

- O_DIRECT. It moves data straight between user memory and the device, past the page cache. The Linux open(2) man page says it "does not give the guarantees of the O_SYNC flag". So direct I/O alone is not a durable write, and a store that uses it still needs a sync.

- PostgreSQL and direct I/O. Only one case used direct I/O for WAL: the open_sync and open_datasync methods with wal_level=minimal. PostgreSQL 16 stopped that, and direct I/O is now behind the developer setting debug_io_direct=wal, per the 16.0 release notes and get_sync_bit in xlog.c, line 8659 at REL_17_11. PostgreSQL 18 added asynchronous I/O, set by io_method. The 18.0 release notes list reads only, such as sequential scans and vacuum, so it does not change the commit path. That is inferred from that list. PostgreSQL 17 has no io_method.

- MySQL 8.4 and direct I/O. MySQL 8.4 changed the Linux default of innodb_flush_method from fsync to O_DIRECT, "if supported". With O_DIRECT, InnoDB "uses O_DIRECT ... to open the data files, and uses fsync() to flush both the data and log files". 8.4 also turned innodb_use_fdatasync on, which "permits using fdatasync() instead of fsync()". So InnoDB 8.4 skips the page cache and still syncs, which is the rule of the bullet above.

MySQL 8.4 defaults that touch durability

If you run MySQL, these are the InnoDB defaults to read with this lesson. MySQL 8.4 is the long-term support release that follows 8.0, and since April 2026 8.0 has only Oracle Sustaining Support:

| Variable | 8.0 default | 8.4 default | What it changes |
| innodb_flush_log_at_trx_commit | 1, inferred | 1 | "The default setting of 1 is required for full ACID compliance." |
| sync_binlog | 1, inferred | 1 | sync of the binary log at each commit |
| innodb_flush_method on Linux | fsync | O_DIRECT if supported | data files skip the page cache, and are still synced |
| innodb_use_fdatasync | OFF | ON | fdatasync() in place of fsync() |
| innodb_log_buffer_size | 16 MiB | 64 MiB | the memory buffer for redo before it is written |
| innodb_doublewrite_files, innodb_doublewrite_pages | two per buffer pool instance, 4 | 2, 128 | the torn page copy |
| innodb_io_capacity | 200 | 10000 | the I/O rate InnoDB assumes for background page flushing |

The two 8.0 values marked inferred are not in the 8.4 manual's list of changed defaults, so they are taken as unchanged. The commit settings did not change, and the flush path did. So an 8.4 server on Linux uses direct I/O plus a sync where 8.0 used the page cache plus a sync.

## What must the store do when a sync fails?

On Linux the right call can fail, and a retry can then report success. PostgreSQL lost data this way, in a bug known as fsyncgate:

- 1 write B B is in the page cache, and its page is dirty.

- 2 fsync The device fails the write, and fsync returns EIO, the error code for a failed disk read or write. The kernel marks the page clean, so B is not on disk.

- 3 fsync again Nothing is dirty, so the call returns 0, which reads as success.

- 4 reply OK The store acknowledges B, which the disk does not have.

- 5 read B Reads still return B from the page cache, until the page is evicted.

- 6 reboot B is gone.

After a failed fsync, ext4, XFS and Btrfs all mark the failed pages clean, so a retry does not write them again. So the store cannot know which writes reached the disk. The only safe action is to stop: never retry, never acknowledge, and let recovery replay the log on restart. PostgreSQL now raises a PANIC on a failed data file flush. PANIC is its top error level, which stops all server processes so recovery runs on restart. Its setting data_sync_retry keeps the old retry and is off by default. After the PANIC, crash recovery replays the WAL and rewrites the data pages.

ext4 and XFS keep the new data in the page cache after a failed fsync, so reads return it while the disk lacks it. Btrfs goes back to the old data. ext4 in data=journal mode reports the error one fsync late. In the same measurement, Redis 5.0.7 did not check the return code of fsync at all.

Linux changed in version 4.13, and since then a write-back error is reported to every file descriptor that might have written the data. But the measurement of ext4, XFS and Btrfs ran on Linux 5.2.11, after that change, and still found the clean pages. So the PANIC rule still applies after that change.

  Retry after EIO. In the lab demo three puts are acknowledged, and after a power loss only order:1041 is left. Two acknowledged puts are lost.

  Stop after EIO. Only order:1041 is acknowledged, and the next two puts get StoreFailed. Nothing acknowledged is lost.

### What you see in the PostgreSQL log

Two code paths raise this PANIC on PostgreSQL 17. Both print the same kind of line.

| What failed | Message | When it is a PANIC |
| a data file sync, at a checkpoint | could not fsync file "%s": %m | while data_sync_retry = off, the default |
| a WAL sync, at a commit | could not fsync file "%s": %m, could not fdatasync file "%s": %m, or with fsync_writethrough could not fsync write-through file "%s": %m | always, whatever data_sync_retry says |

%m is replaced by the system's error text, such as "Input/output error" for EIO. So this line points at the device or the file system, not at PostgreSQL. Both points are inferred, the first from the C library and the second from the code path, and not run. Look at dmesg on the host for the device error at the same time. On RDS or Aurora you cannot run dmesg, and the provider handles the device. What RDS logs for a storage fault was not checked.

### The lab store's sync

The lab store follows the PANIC rule. Here is the wrong way, kept in the code only for its self-test, and the right way, from kvlog.py:460:

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

E9 runs both on the simulated Linux file system of fsim.py. Three puts of 1,230 bytes each, and the second put's sync fails. The expected result comes from the arithmetic of the entry sizes. It was not run:

kvlog.py --fsync-error-demo, expected shape. Not run by the author yet

WRONG, retry after EIO
  acknowledged: order:1041, order:1042, order:1043
  after power loss: order:1041 only
  the disk holds 1,230 good bytes, 1,230 zero bytes, then order:1043
  recovery stops at offset 1230: impossible lengths ksz=0 vsz=0,
  2460 bytes dropped. Two acknowledged puts are lost

RIGHT, stop after EIO
  acknowledged: order:1041. order:1042 and order:1043 get StoreFailed
  after power loss: order:1041. Nothing acknowledged is lost

The gap a restart leaves. Stopping still leaves one gap. A store that must survive it needs to rewrite or verify the log tail it cannot prove durable, and the lab store does not do that. In the RIGHT case, a restart without a reboot reads the log through the page cache. The page cache still shows order:1042, which the disk does not have, and the demo prints that line too. The lab's recovery trusts what the operating system returns, so it would accept order:1042 until the page is evicted. This follows from what ext4 and XFS do after a failed fsync. The same measurement found that PostgreSQL lost data under the ext4 data=journal behaviour, because that error came one fsync late.

fsync on a file also does not make the file's name durable. A name lives in its directory, which is a file too. In a crash test of 11 applications, three of the five problems that developers acted on were a missing directory fsync. So the lab store syncs its directory after it creates the log and after each checkpoint rename.

Where the directory sync sits. That crash test of 11 applications ran on Linux file systems. The store syncs its directory after it creates the log, at kvlog.py:348, and after each checkpoint rename, in checkpoint(). The crash matrix of the last part shows what goes wrong without the first of those syncs.

Evidence
The bug report: Craig Ringer, pgsql-hackers, sent 2018-03-28. File system behaviour: Rebello and others, USENIX ATC 2020, Table 1 and section 3.3, on Linux 5.2.11. The fix: PostgreSQL 11.2, 10.7, 9.6.12, 9.5.16 and 9.4.21, released 2019-02-14, from the five release notes. data_sync_retry: the docs of versions 14, 17 and 18 describe it the same way, and the 17 sample file has the default off at line 824. A fresh 14.24 cluster on the M4 Pro showed data_sync_retry = off, source default. The Linux 4.13 change: the Linux fsync(2) man page. The two PANIC paths: sync.c lines 444 to 447 with data_sync_elevel in fd.c line 3938, and issue_xlog_fsync in xlog.c lines 8790 to 8800, at REL_17_11. The "Input/output error" text is inferred from the C library, and not run. Directory fsync: the ALICE study, Pillai and others, OSDI 2014, page 12.

Go deeper: why the retry reported success, and the fix

The bug report found that the PostgreSQL retry succeeded because the first failed fsync had cleared the error flag. The data was gone, and the second fsync reported success.

The fix

PostgreSQL fixed this in five releases on the same day: 11.2, 10.7, 9.6.12, 9.5.16 and 9.4.21. By default the server raises a PANIC on a failed data file flush and does not retry, and the new parameter data_sync_retry restores the old behaviour.

## How does group commit win back the throughput?

Each put now waits for one full sync of about 2.85 ms on the M2. The syncs run one after another, so the store commits at most 1 / 2.85 ms, about 351 puts per second. Adding writers does not help, because they wait in line for the device.

Group commit means that one sync covers the log entries of many commits. Each commit still returns only after a sync that covers its own entry. While one sync runs, new puts append and wait. Then one waiting writer becomes the leader and syncs everything appended so far, and the others return with it.

  Group commit with 3 writers, one sync of 2.85 ms

  Sync 1 covers writer A's first put. B and C append during sync 1 and wait.

  Sync 2 covers both B and C. A's second put appends during sync 2.

  Sync 3 covers A's second put, and the syncs end at 2.85, 5.70 and 8.55 ms. Four puts took three syncs instead of four.

  Times are an example built from the M2 median of 2.85 ms, not measured.

With 16 writers, one sync can cover at most 16 puts. So the upper limit becomes 16 × 351 = 5,616 puts per second. The price is latency. A put that arrives right after a sync started waits for that sync and then for its own. So it can take up to 2 × 2.85 = 5.7 ms.

  Upper limits from one sync time

  Sync time, µs
  Writers
  One sync per put , group commit , longest wait

These are limits from arithmetic. Python's cost per put lowers both, and E10 measures the real rates. Move the sync time to 1,000 µs, the best case of one flush on a gp3 volume. Then one sync per put allows only 1,000 commits per second. That gp3 time is inferred, and not measured.

### The lab's leader and followers

In kvlog.py, the flag group_commit=True switches put from _sync_log_locked to _wait_durable. The core of _wait_durable, from kvlog.py:475, without its error handling and with the comments changed:

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

The leader reads target before it syncs. A put that appends after that line is not counted as covered, even if the sync happens to include its bytes. That rule keeps the claim exact: a put returns only when a sync that started after its append has returned.

One assumption is not checked. The design needs fcntl.fcntl and os.fsync to release Python's global interpreter lock while the device works. If they did not, no other thread could append during a sync, and every batch would hold one put.

PostgreSQL forms its groups inside XLogFlush, the durability point of the commit order. A committer tries to take WALWriteLock with LWLockAcquireOrWait. If another backend holds the lock, this one waits until the lock is free. Then it does not take the lock at once. It first checks whether the holder already flushed past its own commit record, and if so, it returns without a sync. That is the lab's _wait_durable, where a follower returns when synced_to covers its entry. PostgreSQL 17 also lists "Improve performance of heavily-contended WAL writes" in its release notes, and how much that changes the group size was not checked.

The setting commit_delay, 0 µs by default, makes the leader sleep first so more commits join. It does so only if at least commit_siblings other transactions are active, 5 by default. On a disk limited to 1,000 write IOPS, a delay of 1,000 µs gave 1.74 times the throughput. A good first value is half the time that pg_test_fsync reports for one flush after an 8 kB write, and then you measure the throughput.

The other way to get speed is to reply before the sync, and every such setting has a loss window. NATS replies before its two-minute fsync, as the commit part showed. fsync=off is worse, because it can corrupt the database beyond repair. The next two parts show where the commits come from in your code, and where you can give up durability on purpose.

  Only F_FULLFSYNC asks a Mac drive to flush, and group commit shares that slow sync.

  Calling os.fsync durable on a Mac makes every benchmark fast and loses writes.

  Run uv run python shared/durable.py --measure 200, and predict the ratio of full to fsync first.

Evidence
PostgreSQL's group forming: LWLockAcquireOrWait at xlog.c line 2852, REL_17_11, line 2855 at REL_18_0, and its comment, which says this "helps to maintain a good rate of group committing". commit_delay and commit_siblings: the docs of versions 14, 17 and 18, and the 17 sample file, lines 253 and 254. The starting value: PostgreSQL 17 docs, section 28.5. The 1.74 times: Laurenz Albe, CYBERTEC, January 2025, PostgreSQL 17 on an ASUS ZenBook notebook with NVMe and Fedora 40, the disk limited to 1,000 write IOPS on purpose, pgbench -b simple-update -c 10 for 1,200 seconds. The flush time of about 2,000 µs: Albe's reply on the same post, 2025-06-28. fsync=off: PostgreSQL 17 docs, section 19.5. The 1,000 µs gp3 flush is inferred from the EBS latency statement in the sync part.

Go deeper: commit_delay in detail, and older measurements

PostgreSQL's group forming, more detail

Since PostgreSQL 9.3, only the leader waits for the commit_delay, and the others wait for its flush. The PostgreSQL 17 docs, section 28.5, add that at higher client counts a "gangway effect" forms groups even with a delay of 0, so the setting helps less there. The lab's --group-delay-us flag is the same idea.

The bars run from 1,576 to 2,738 TPS, transactions per second, which is 1.74 times. Past 1,000 µs the wait costs more than it saves. A disk limited to 1,000 write IOPS suggests about 1 ms per write, which would give a first value of about 500 µs. But Albe ran pg_test_fsync on the throttled disk, and fdatasync took about 2,000 µs per operation. Half of 2,000 µs is 1,000 µs, his best value. So start from half the measured flush time of your wal_sync_method, not a guessed one.

Vadim Tkachenko of Percona measured the InnoDB group commit fix in July 2011, on 8 disks in RAID 10, which mirrors pairs of disks and spreads the data across the pairs. Without a controller cache, the fix raised throughput to 1,669.11 at 256 threads, against 57.62 without the fix at the same thread count, about 29 times. Without the fix, the best value was 60.05, at 64 threads. With a battery-backed cache, one thread already reached 352.83 without the fix. So group commit matters most when each sync is slow. The article does not state the unit, which is probably transactions per second.

## How many commits does one request make, and where do you see the flush wait?

Group commit shares flushes among commits that wait at the same moment. But the number of commits comes from your application code, often from a default you did not choose.

- Django. "Django's default behavior is to run in autocommit mode. Each query is immediately committed to the database, unless a transaction is active". transaction.atomic, or ATOMIC_REQUESTS = True for a whole view, makes one transaction. Inside it, an inner atomic block "creates a savepoint", not a second commit.

- psycopg 3. The default is the opposite: "By default even a simple SELECT will start a transaction", which lasts until your code commits. Django turns autocommit on for its own connections: "Django overrides this default and turns autocommit on."

Here is the arithmetic for one Django view that makes 10 writes. It assumes one session alone, so no other commit shares its flush.

| Mode | Commits | Flush waits at 2.85 ms, M2 F_FULLFSYNC | Flush waits at about 1 ms, gp3, inferred |
| autocommit, the Django default | 10 | 10 × 2.85 = 28.5 ms | 10 × 1 = 10 ms |
| one transaction.atomic block | 1 | 2.85 ms | 1 ms |

Group commit can share flushes across sessions, so a busy server pays less per commit. The 10 commits of one session still pay 10 flushes, since the next statement starts only after the previous commit's flush returns. That follows from the commit order of the first concept. So one worker that only waits for flushes serves at most 1 / 10 ms = 100 requests per second in autocommit on gp3. With one transaction it serves 1,000.

### A real case: the commits were the limit

Disney+ Hotstar ran its payment service on Aurora MySQL with one writer. A load test could not reach the target rate. The pods' CPU and memory stayed well below 50% of capacity at peak load. The first wrong theory was slow reads. The reads were the three busiest queries, so they competed most for a pool connection. Most of their time was spent waiting for one, not running on the database. Performance Insights is the AWS tool that samples what each database session waits for. It showed most active sessions waiting on wait/io/aurora_redo_log_flush and on the binary log mutex. The team found "a fan out of 1:10 for a payment transaction API to a DML operation", each its own commit. DML means a statement that changes data, such as INSERT, UPDATE or DELETE. The post lists ways to make fewer commits, such as "Turning off auto-commit around multiple DML operations". The team judged that this would "require significant changes in the codebase", and did not apply it. The fix it applied was the binlog I/O cache, by a minor version upgrade of Aurora MySQL. The results of that upgrade were a "~30% uptick in TPS" and a "7x drop in P99 Latency" at 30% higher load.

### How to see the commit-flush wait

A session that waits reports a wait event, the name of what it waits for, in pg_stat_activity. Sample it several times during load:

-- Run it several times during load. Each row is one kind of wait.
select wait_event_type, wait_event, count(*)
from pg_stat_activity
where state = 'active'
group by 1, 2
order by 3 desc;

The query was not run. These are the names you can see for a commit on PostgreSQL 17.

| wait_event_type / wait_event | Meaning | When you see it |
| IO / WalSync | "Waiting for a WAL file to reach durable storage." | Linux, with fdatasync, the default there |
| IO / WalWrite | "Waiting for a write to a WAL file." | also the sync wait with open_datasync, the macOS default, because the sync happens inside the write |
| LWLock / WALWrite | "Waiting for WAL buffers to be written to disk." | another backend holds WALWriteLock, so this one waits for its flush. This is a group commit follower |

On managed PostgreSQL the same wait has a vendor name in Performance Insights, and AWS names the same action on commits for both.

| Service | Wait event | What AWS says | AWS's action on commits |
| RDS for PostgreSQL | IO:WALWrite | the session "is waiting for the WAL data to complete writing to disk so that it can release the transaction's COMMIT call" | "combine statements into transaction blocks" |
| Aurora PostgreSQL | IO:XactSync | "the database is waiting for the Aurora storage subsystem to acknowledge the commit" | "combine statements into transaction blocks". It is the last of four actions. AWS names network saturation and CPU pressure as the likely causes |

That is the fix the Hotstar team named but did not apply: fewer commits. For IO:WALWrite it is the first action. So when one of these waits tops the list and CPU is low, count the commits per request first, and then check how often checkpoints run.

### How long one flush takes, measured by the server

On PostgreSQL 14 to 17, pg_stat_wal counts WAL syncs. It adds up their time only with track_wal_io_timing = on, and that time gives the server's own sync time for the formula of the group commit part.

-- Needs track_wal_io_timing = on, a superuser setting. Times are in ms.
select wal_sync, wal_sync_time,
       wal_sync_time / nullif(wal_sync, 0) as ms_per_sync,
       wal_write, wal_write_time
from pg_stat_wal;

One trap: wal_sync_time counts only for fdatasync, fsync and fsync_writethrough. With open_datasync or open_sync, the sync time is inside wal_write_time, and wal_sync stays 0. So on a Mac with the default, read wal_write_time / wal_write instead. PostgreSQL 18 removes these four columns from pg_stat_wal and reports the WAL rows in pg_stat_io.

Evidence
Django: the 5.2 page "Database transactions". psycopg: the psycopg 3 page "Transactions management". The single-session limit is inferred from the commit order, and not run. Hotstar: Ishank Gulati, "De-bottlenecking Aurora MySQL for 19 Million concurrent users", January 2023, read from the Wayback Machine copy. The wait event descriptions: wait_event_names.txt lines 268, 270 and 314 at REL_17_11. issue_xlog_fsync reports WalSync at xlog.c line 8761. The display names follow the rule in generate-wait_event_types.pl lines 122 to 126. Which event a macOS commit shows is inferred from where the sync happens, and not run. AWS: the pages "IO:WALWrite" and "IO:XactSync", vendor pages. That IO:WALWrite is the native WalSync or WalWrite event under another name is inferred, and not checked. pg_stat_wal: PostgreSQL 17 docs, Table 27.26, monitoring.sgml lines 3150 to 3185. The 18 move: the 18.0 release notes.

Go deeper: who may turn on WAL timing
track_wal_io_timing has the context PGC_SUSET, so only a superuser can set it, per guc_tables.c line 1430 at REL_17_11. Whether RDS allows it in a parameter group was not checked.

## Where can you give up durability on purpose?

Fewer commits and group commit keep every acknowledged write. The other choice is to reply before the log is durable. Each store that allows it names its own loss window.

| System and setting | When it replies | What a crash can lose |
| PostgreSQL synchronous_commit=off | before the WAL flush | up to 3 × wal_writer_delay, 600 ms at the default |
| PostgreSQL fsync=off | never syncs | not a window: "unrecoverable data corruption in the event of a power failure or system crash" |
| PostgreSQL UNLOGGED table | the table writes no WAL at all | the whole table: it "is automatically truncated after a crash or unclean shutdown" |
| MySQL sync_binlog=0 | without a sync of the binary log | committed transactions missing from the binary log, after a power failure or OS crash |
| MariaDB innodb_flush_log_at_trx_commit=0 | before the log write | about the last second |
| MariaDB innodb_flush_log_at_trx_commit=2 | after the log write, before the flush | about the last second, on an OS crash or power loss |
| Redis appendfsync everysec, the default | before the fsync | about 1 second, per the docs |
| NATS JetStream, the default sync_interval | before the fsync | up to 2 minutes |

PostgreSQL gives you three rules that make this choice smaller than one global switch.

### Rule 1: per transaction

"The mode used for any one transaction depends on the value of synchronous_commit when transaction commit begins". Any user can change it, because its context is PGC_USERSET. So a service can commit a payment with on and a page-view log with off, in the same database.

-- One low-value transaction. Every other transaction keeps the default, on.
BEGIN;
SET LOCAL synchronous_commit = off;
INSERT INTO page_views (path, viewed_at) VALUES ('/pricing', now());
COMMIT;

SET LOCAL lasts until the end of the transaction. This is an example, and it was not run. A crash can lose up to 600 ms of these rows, and the database stays consistent. Use it for rows that a client never sees acknowledged as stored, such as traces, page views and telemetry. Do not use it for a transaction with an external action, from the first concept.

### Rule 2: per table, with UNLOGGED

An UNLOGGED table gives up more than async commit, because it writes no WAL at all. The PostgreSQL 17 docs say that its data "is not written to the write-ahead log ... which makes them considerably faster than ordinary tables. However, they are not crash-safe: an unlogged table is automatically truncated after a crash or unclean shutdown. The contents of an unlogged table are also not replicated to standby servers". Here is the mechanism, one level below the docs.

- No WAL, so nothing to replay. Each unlogged table has an initialization fork, an empty copy of the table. After a crash, crash recovery copies that fork over the table's main file.

- A checkpoint does not save it. The checkpoint writes unlogged buffers only for a shutdown, an end-of-recovery or a flush-all checkpoint, and skips them otherwise. So a clean shutdown keeps the data, and a crash empties it, whatever checkpoints ran before.

- Such a commit does not wait for the WAL flush. A transaction that wrote only to unlogged or temporary tables writes no WAL. So its commit takes the asynchronous path, even with synchronous_commit = on. That step is inferred from the source, and not run.

| Table and setting | Commit waits for | After a crash |
| logged, synchronous_commit on | the WAL flush | every acknowledged row |
| logged, synchronous_commit off | nothing | all but the last 600 ms |
| UNLOGGED | nothing | the table is empty |

UNLOGGED fits data you can rebuild. Examples are a cache table, embeddings you can compute again from the source text, scratch state of an agent run, and a rate-limit counter. Each can be rebuilt, so losing it costs time, not data. Zerodha runs a whole cache database this way: "We turn off fsync and write-ahead logs as we can afford to throw away the cached data if the cache DB needs to be restarted for any reason". They also turn off replication for it. Zerodha uses a separate server with fsync off, while UNLOGGED keeps the rest of your database safe. ALTER TABLE ... SET LOGGED changes an unlogged table back.

The trap is a standby. An UNLOGGED table on a primary with a standby is empty on the standby. So after a failover, the new primary has an empty table and no error. That RDS Multi-AZ behaves this way is inferred from the docs sentence on standbys, and not checked. So your code must treat an empty unlogged table as a cold cache, never as "no data".

### Rule 3: fsync=off is a different risk

Asynchronous commit loses at most the last 600 ms, and the database stays consistent. An UNLOGGED table loses only itself. fsync=off can corrupt the database beyond repair. A CI database often runs with fsync=off, so its crash behaviour says nothing about production.

Evidence
The loss windows: PostgreSQL 17 docs, section 19.5, and CREATE TABLE. MySQL: the 8.4 manual, "Binary Logging Options and Variables". MariaDB: the InnoDB system variables page. Redis: the Redis persistence docs. NATS: Jepsen NATS 2.12.1, section 3.4. The per-transaction rule: PostgreSQL 17 docs, section 28.4, and guc_tables.c line 4926 at REL_17_11. UNLOGGED: PostgreSQL 17 docs, CREATE TABLE and section 65.5. ResetUnloggedRelations is called from crash recovery at xlog.c lines 5724 and 5873. The checkpoint skip: bufmgr.c lines 2924 to 2927. The commit path: the comment at xact.c line 1467, "if it only wrote to temporary and/or unlogged tables", and the condition at line 1487, all at REL_17_11. Zerodha: "Working with PostgreSQL", 2021. SET LOGGED: PostgreSQL 17 docs, ALTER TABLE. The fsync=off point: Rogov, page 187.

Go deeper: the Redis window, two measurements of what async commit buys, and MySQL's two settings
The Redis row has one more detail. The Redis course teaches Redis durability in full, in its Phase 4 lesson, part "What does a crash lose, and which crash?". In short, the docs say one second. The source in src/aof.c on the unstable branch can postpone a write for up to two seconds, while a background fsync is still running. So the window can be longer than one second. That is inferred from the code and not tested.

Kaarel Moppel of CYBERTEC measured, in 2016, 4,256 TPS with synchronous_commit=on and 6,211 TPS with off, which is 1.46 times. The setup was two AWS i2.xlarge instances with asynchronous streaming replication, and pgbench with 8 clients for 10 minutes. With asynchronous replication the primary does not wait for the standby, so the setting changed only the local WAL wait. That last point is inferred from the PostgreSQL docs on synchronous_commit. The PostgreSQL version is not named. Rogov ran a smaller test on PostgreSQL 14.7, with pgbench, 1 client and 30 seconds. He measured 670.8 TPS with synchronous_commit on and 2,060.4 TPS with it off, which is 3.07 times, in section 11.1, pages 184 and 185. His hardware is not stated in those pages. These ratios and the group commit ratio of 1.74 come from different machines and tests, so they are not compared.

MySQL needs two settings for a durable commit, because the binary log is a second log next to the InnoDB log. sync_binlog defaults to 1. For the greatest durability "in a replication setup that uses InnoDB with transactions", the MySQL 8.4 manual lists sync_binlog=1 together with innodb_flush_log_at_trx_commit=1, on its page "Binary Logging Options and Variables". Replicas read the binary log, which this course does not teach.

## How does recovery notice a half-written entry?

A sync makes a write durable once it returns, but a power loss can come while the write is still in flight. A torn write is a write that only partly reached the disk. The device writes in sectors, commonly 512 bytes, so a power loss can leave some sectors of one write new and others not.

The lab's log entry has a 20-byte header, the key and the value. The header holds a CRC-32, a 4-byte value computed from every byte after it. It also holds a sequence number and two lengths. So put order:1041 with a 1,200-byte value takes 20 + 10 + 1,200 = 1,230 bytes.

The header is big-endian, and the CRC covers every byte after itself.

| crc32 | seq | ksz | vsz | key | value |
| 4 B | 8 B | 4 B | 4 B | ksz bytes | vsz bytes |

Predict: a power loss tears the second version of order:1041, 1,230 bytes at offsets 1230 to 2460. One 512-byte sector in the middle reads as zeros, and the file length covers the whole entry. If recovery checks only the lengths, what does it return for order:1041?
It returns the new value, with 512 zero bytes inside it, served as data under the right key. Every length in the header is correct.

  The torn entry

A torn write has two shapes, and each needs its own check.

| Shape | What the disk holds | What catches it |
| short | the file ends inside the entry | a length check |
| hole | the right length, with a sector of wrong bytes inside | only a checksum |

A checksum is a short value computed from a block of bytes and stored next to it. A reader computes it again and compares, so a changed byte gives a different value. The parser checks the lengths first, so a damaged length cannot make it read gigabytes, and then the CRC.

### Where the hole falls, and how the parser catches it

fsim.py zeroes the sector that holds the middle byte of the in-flight write:

middle byte     1230 + 1230 / 2 = 1845
sector start    1845 // 512 × 512 = 3 × 512 = 1536
sector end      1536 + 512 = 2048
value starts    1230 + 20 header + 10 key = 1260

So the 512 zero bytes fall inside the value, and the header is intact. A reader that checks only the lengths sees a valid entry with the right key. A delete is shorter: delete order:1042 is 20 + 10 = 30 bytes, and a tombstone is marked by vsz = 0xFFFFFFFF, with no value.

A short write has the other shape. In the example of the lab's figure, only 700 of the 1,230 bytes arrived, so the file ends at 1930 and a length check catches it.

Real drives produce both shapes. In the power-cut test of 15 SSDs, three SSDs showed shorn writes, in which only part of a 4 KB record reached the disk. Three SSDs showed bit corruption. SQLite's document on atomic commit, section 2, says SQLite has long assumed that a single sector write is not atomic.

Suppose the damage looks random to the CRC. Then the chance that a damaged entry still matches is 1 in 2^32, or 1 in 4,294,967,296. That figure is inferred from the size of the CRC, and not checked against a model of real drive failures.

The parser runs its checks in the order given above, lengths first and the CRC last.

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

E8 runs the hole case twice in memory, with the CRC check off and on. The expected output comes from the offsets above. It was not run:

kvlog.py --torn-demo, expected shape. Not run by the author yet
WRONG verify_crc off: get(order:1041) returned 1200 bytes, 512 of them
      zero, served as data. 2 entries replayed
RIGHT verify_crc on:  stopped at offset 1230: checksum mismatch,
      1230 bytes dropped. get(order:1041) returned the earlier value,
      starting 'order:1041:v1:'

Amazon S3 went down in July 2008, with problems in the messages between its servers. A few of those messages each had one wrong bit, but the servers could still read each one. S3 checked customer data with MD5 checksums, but these internal state messages had no such check. So the wrong state went unnoticed and spread through the whole system. Amazon stopped all traffic between S3 servers and cleared the system state. By 2:20 pm PDT, the servers talked to each other again, and request processing began to restart. The fix added checksums to the state messages, and monitoring with an alarm for that state. A flipped bit leaves every length correct, so a length check alone would miss it too.

Recovery stops at the first entry that fails any check, including a sequence number that is not the next one. It treats that point as the end of the log, cuts the file there and syncs the cut. The put in flight was never acknowledged, so dropping it breaks no promise.

The rule fails for a bit flip in the middle of data that was already synced. Recovery stops there and drops every later entry, acknowledged ones too, because the scan cannot tell that damage from a torn tail. Reads check the CRC too, so a damaged synced entry is never served as data. So the store's promise says that damage to synced data is not covered. PostgreSQL's redo also stops at the first invalid record and treats it as the end of the WAL, so it has the same blind spot. That is inferred from the reader logic.

### A torn data page in PostgreSQL

PostgreSQL also repairs a torn 8 kB data page, which a checksum can only detect. full_page_writes = on is the default in 14, 17 and 18. With it, the first change to a page after a checkpoint copies the whole page into the WAL. Replay writes that full page image back over a torn page. The docs allow turning the setting off only on a file system that prevents partial page writes, and their example is ZFS. Two places where you meet this setting:

- A battery-backed controller is not enough. The docs warn: "Battery-Backed Unit (BBU) disk controllers do not prevent partial page writes unless they guarantee that data is written to the BBU as full (8kB) pages". So a BBU is not a reason to turn full_page_writes off.

- On RDS you cannot turn it off. AWS states that RDS for PostgreSQL always keeps full page writes on. So on RDS the page-image cost of the checkpoint part is fixed, and your only levers are the checkpoint interval and wal_compression, which is inferred.

Aurora and AlloyDB remove the torn page from the database host, because the host writes no data pages at all. It sends only WAL records to a storage service, and that service builds the pages. So on these systems the torn page problem moves into the storage service, where it still exists and you cannot test it. That move is inferred from the two vendors' own descriptions.

### Data checksums: a decision before you move to 18

Data checksums are a separate feature. They detect a damaged data page when it is read, and their default depends on the version that ran initdb.

| Version | initdb default |
| 14 and 17 | off, unless initdb -k |
| 18 | on. --no-data-checksums turns them off |

pg_upgrade needs matching checksum settings in the old and new clusters. So a 17 cluster made with default settings needs a decision before it moves to 18. There are two ways out.

- Make the new 18 cluster with initdb --no-data-checksums.

- Turn checksums on in the old cluster with pg_checksums --enable. It refuses a running server with the message "cluster must be shut down". It rewrites every data page, so the downtime grows with the cluster size. That cost is inferred, and not measured.

In versions 14, 17 and 18, checksums cover data pages only: "Only data pages are protected by checksums; internal data structures and temporary files are not." Rogov names three more limits.

- A page is checked only when it is read, so damage can sit unseen until it reaches every backup.

- A zeroed page counts as valid.

- Rogov says only the main fork of each table is covered. In the 17 source, FlushBuffer sets a checksum on every page it writes, at bufmgr.c line 3941, so free space map and visibility map pages are covered too. Files outside relations, such as pg_xact, are not.

Checksums also cost WAL. With them on, "hint bit updates are always WAL-logged", per the PostgreSQL 17 docs, section 19.5. A hint bit is a cached flag in a row that saves later readers a lookup, and Phase 3 explains it. So the 18 default writes more full page images than the 17 default. That is inferred from the docs line, and its size is not measured here.

The same holds for a 14 cluster, and PostgreSQL 14 reaches its final release in November 2026. Run show data_checksums; to see your cluster's setting, and E11 does it. Whether RDS and Aurora clusters have checksums on was not checked, and the same command answers it on your instance. A checksum failure shows in two places. pg_stat_database.checksum_failures counts failures. The log shows a warning that starts "page verification failed, calculated checksum", and then an error "invalid page in block 0 of relation".

PostgreSQL 17.11 also fixed a gap in this protection. Its release note says: "We also failed to log full-page images of such VM pages when needed, potentially allowing torn page writes to go uncorrected". A VM page here is a page of the visibility map, which Phase 4 uses. So run the latest 17 minor release, and check yours with select version();.

  A length check catches a short write, and only a checksum catches a hole.

  Recovery that checks lengths only serves bytes that no client ever wrote.

  Run uv run python phase01_durability/kvlog.py --torn-demo and match each output number to an offset above.

Evidence
Sectors of 512 bytes and PostgreSQL's 8,192-byte writes: PostgreSQL 17 docs, section 28.1. The entry layout follows the Bitcask paper's figure on page 2. The offsets of the hole come from fsim.py, and the demo output was worked out from them, not run. Amazon S3: Rich Miller, "S3 Downtime: More Missing Bites", Data Center Knowledge, 2008-07-26, which quotes Amazon's postmortem. full_page_writes: PostgreSQL 17 docs, section 19.5, and the 17 sample file, line 240. The BBU sentence: PostgreSQL 17 docs, section 28.1, wal.sgml lines 178 to 180 at REL_17_11. RDS: the AWS page "IO:WALWrite", a vendor page. Aurora: Verbitski and others, SIGMOD 2017, section 3.2. AlloyDB: Google Cloud blog, 2022-05-12, "the compute layer only communicates the WAL records to the storage layer", a vendor post. Checksum defaults: initdb.c line 167, false at REL_17_11 and true at REL_18_6, and the 18.0 release notes, dated 2025-09-25, under incompatibilities. pg_checksums: lines 439 and 570 at REL_17_11. What checksums cover: PostgreSQL 17 docs, section 28.2, and the 14 and 18 docs. The three limits: Rogov, section 11.2, page 187. checksum_failures: PostgreSQL 17 docs, section 27.2. The log texts: Rogov's example on page 188, and the same texts in 17 at bufpage.c line 152 and bufmgr.c line 1556. PostgreSQL 18 puts the relation path in double quotes, and can report several invalid blocks in one message. The 17.11 fix: release-17.sgml lines 1953 to 1966. PostgreSQL 14 reaches its final release on 2026-11-12, per the PostgreSQL versioning page.

Go deeper: the LazyFS test, InnoDB and cloud devices, and the PostgreSQL WAL record

What happens with full_page_writes off

There is direct evidence. Ramos and others built LazyFS, a file system that runs as a normal program. It uses FUSE, the interface that lets a user program act as a file system. It has its own page cache, and it can lose or tear writes on command. They tore a PostgreSQL data page write, with the setting off and on, on PostgreSQL 12.11 and 15.2. In both cases the server restarted without an error. With the setting off, the amcheck module, which checks the structure of tables and indexes, then reported corruption. The last part uses LazyFS again as a test tool.

The same problem in InnoDB

MySQL's InnoDB writes each page flushed from the buffer pool to a doublewrite buffer first, and only then to its place in the data file. After a crash during a page write, InnoDB "can find a good copy of the page" in that buffer.

| Engine | Where the extra copy goes | Extra cost |
| PostgreSQL | into the WAL | one extra page write |
| InnoDB | into a second file, the doublewrite buffer | one extra page write |

In MySQL 8.4, innodb_doublewrite has the default ON. Its value DETECT_ONLY writes only metadata and does not repair a torn page. An earlier version of this lesson said the manual gives no exact default. The parameters page does give it, so that sentence was wrong. 8.4 also changed how the buffer is laid out. innodb_doublewrite_files became 2, where 8.0 used two per buffer pool instance. innodb_doublewrite_pages became 128, where 8.0 used the value of innodb_write_io_threads, 4 by default.

A device can remove the problem

AWS documents torn write prevention for EC2, which writes a block all or nothing. AWS says this removes the need for the doublewrite buffer. It states that transactions per second can rise by up to 30 percent, and write latency can fall by up to 50 percent. These are vendor claims. The supported block sizes and volume types were not checked, because that sub-page did not load. Linux 6.11 added a matching write flag, RWF_ATOMIC, per this course's currency research. Whether PostgreSQL 17 or MySQL 8.4 use it was not checked.

The Aurora paper says: "In Aurora, the only writes that cross the network are redo log records. No pages are ever written from the database tier". It describes the MySQL-compatible engine. Google says that in AlloyDB there is no reason "to send complete database blocks to the storage layer", and the post names the torn pages problem as one such reason.

The lab entry against a PostgreSQL WAL record

A PostgreSQL WAL record solves the same problems with different fields. Its header is 24 bytes, against the lab's 20, from xlogrecord.h at tag REL_17_11, lines 41 to 53:

| The job | Lab entry, kvlog.py | PostgreSQL WAL record | Source |
| length | ksz and vsz, 4 bytes each | xl_tot_len, the length of the whole record | xlogrecord.h |
| checksum | crc32, IEEE CRC-32 over the bytes after it | xl_crc, a CRC-32C on every record | xlogrecord.h, PG 17 docs 28.1 |
| order | seq must be the next number | xl_prev must be the LSN of the record before. Else "record with incorrect prev-link" | xlogreader.c REL_17_11 line 1165 |
| end of log | impossible lengths ksz=0 vsz=0 | "invalid record length at ...: expected at least 24, got 0" on 17. 14 and 15 print "wanted 24, got 0" | xlogreader.c REL_17_11 line 669. Rogov p. 175 for 14 |

The order check matters for one reason the lab does not have. PostgreSQL recycles old WAL files by renaming them, per Rogov, page 178. A recycled file still holds old records with valid CRCs. The reader refuses them by the xl_prev check, and by the page address check at line 1330 of xlogreader.c. On 17 that check prints "unexpected pageaddr %X/%X in WAL segment %s, LSN %X/%X, offset %u", where 14 says "in log segment %s, offset %u". The lab's sequence check does the same job for its own log, which is inferred from the reader code. The wording change of the end-of-log message was found by comparing xlogreader.c at REL_15_0 and REL_16_0.

## Where does recovery start, and what does a checkpoint bound?

The torn tail is now caught, but recovery found it by reading the whole log, and the store serves no read until recovery ends. Crash recovery is the work a store does on restart to build a correct state from disk. In a WAL store it is mostly replay. A checkpoint is a point in the log with a guarantee: every change before it is already saved outside the log. Recovery starts there, so the log written since that point bounds recovery time.

Predict: a PostgreSQL server crashes with about 1 GB of WAL written since recovery's start point, which the next part defines exactly. Guess how long the redo takes: under a second, about 5 to 10 seconds, or several minutes.
About 5 to 10 seconds, on one measured machine whose hardware is not named. Many people guess minutes. Treat it as an order of size, because the time depends on the version and on a read-ahead setting.

The lab's checkpoint is one file, keydir.ckpt. It holds the keydir, the in-memory map from each key to its newest entry, and the log offset it covers. The workload writes 10 operations, with a checkpoint after the fourth.

  The workload log after 10 operations: 9,900 bytes

So a restart reads 4,980 of 9,900 bytes, or 50.3%. Without a checkpoint it reads all of them.

Tarsnap, a backup service, lost its central server in July 2023, most likely to a hardware fault. After a restart, the server's logs showed a damaged file system. Tarsnap stores its data in Amazon S3 as a log. Each stored object starts with a header that holds the metadata of its log entries. Colin Percival, who runs Tarsnap, chose to build a new server instead of repairing the old one. So the new server first read all the metadata headers from S3. Then it replayed all of those operations locally, on the new server. The postmortem says that both steps were slower than they could be. The read used only 250 parallel requests to S3, and disk throughput limited the replay. The replay also failed twice, and he fixed the recovery code each time. The service came back about 26 hours after it went down.

### What the lab store does on restart

Store.open at kvlog.py:331, with _recover at kvlog.py:356, runs these steps in order.

- Delete keydir.ckpt.tmp if it exists. A crash during a checkpoint left it, and the log has the same data.

- If keydir.ckpt exists and its own CRC is good, load the keydir from it. The file also holds the log offset it covers and the last sequence number.

- If the checkpoint covers more bytes than the log has, stop with CorruptionError. Only a broken WAL rule leads here.

- Read the log from the covered offset to the end, and apply each entry to the keydir.

- Stop at the first bad entry. Cut the file there and sync the cut.

- Start accepting writes.

### How the lab writes its checkpoint

A crash can come at any step of writing keydir.ckpt, so checkpoint() runs five steps in a fixed order.

- Sync the log, so the log is durable before the file that depends on it.

- Write keydir.ckpt.tmp, so the good file is never overwritten in place.

- Sync the tmp file, so its bytes are durable before its name moves.

- Rename it to keydir.ckpt, which replaces the old file in one step.

- Sync the directory, so the rename is durable.

Skip step 3 or step 5, and a crash leaves a broken or an old checkpoint, which costs only a longer scan. Skip step 1, and the checkpoint can point past the end of the durable log. The store cannot repair that, so recovery refuses to open with CorruptionError.

This is what a power loss right after each checkpoint step leaves.

| Step | Why | A power loss right after it leaves |
| 1 sync the log | the WAL rule | the old checkpoint or none. Full scan |
| 2 write keydir.ckpt.tmp | never overwrite the good file in place | the same. The tmp file is not durable |
| 3 sync the tmp file | its bytes are durable before its name moves | the same. Its name is not durable yet |
| 4 rename tmp to ckpt | one step replaces it | the same, or new: the rename is not durable yet |
| 5 sync the directory | the rename is durable | the new checkpoint |

In every row the log holds all acknowledged puts, so no data is lost. Skip step 3, and the rename can reach the disk before the file's bytes. Then the checkpoint is short or zero, its CRC fails, and recovery scans from offset 0. Skip step 5, and a power loss can bring back the old checkpoint. Both cost time, not data, because the log is the source of truth.

The checkpoint always uses the full sync, even when the store commits with --sync none. Checkpoints are rare, one per many puts, so their cost is small. A wrong checkpoint is corruption, while a slow one is only slow.

Recovery must also cut the bad tail it finds. Suppose recovery stops at a torn entry but does not cut it. The next put lands after the garbage, and the next recovery stops at the same garbage and drops the new put, which was acknowledged. The self-test of kvlog.py runs exactly this double crash, with truncate_tail off. The cut is at kvlog.py:402, and it is synced before any new write.

Evidence
The steps and offsets come from checkpoint() at kvlog.py:511, Store.open at kvlog.py:331 and _recover at kvlog.py:356. The self-test of kvlog.py removes step 1 with sync="none" and checks that the power image fails to open. The redo time in the predict answer is Christophe Pettus's measurement on PostgreSQL 18.6, in the next part. Tarsnap: Colin Percival, "2023-07-02 -- 2023-07-03 Tarsnap outage post-mortem", tarsnap-announce, 2023-07-26.

Go deeper: the three passes of ARIES, and the lab store's recovery time

Redo and undo

PostgreSQL states the rule this way. Crash recovery looks at the latest checkpoint record to find the redo point in the WAL, and starts there. Changes made before that point are already on disk. This is the PostgreSQL 17 docs, section 28.5, and the version 14 docs, section 30.5. The ARIES paper, section 6, describes a restart as three passes in order: analysis, redo and undo. Undo removes the changes of transactions that never committed. The lab store has no undo pass. One put is one entry, and it either passes its CRC or it is not there. PostgreSQL has no undo pass either, per Rogov, section 10.4, page 174. An unfinished transaction never gets a commit bit in pg_xact, so readers treat its rows as aborted. Phase 3 shows how they do that.

The lab store's recovery time

It is not measured. The design reads every byte after the checkpoint once, and computes one CRC per entry. So its time grows with those bytes, which is inferred from the code. RecoveryReport.seconds prints it on each open, so you can measure it.

Bitcask has a similar file, the hint file. The paper's merge step writes it. It holds each key's position and no values, so a restart can read it instead of the data file. Merge is a form of compaction, and compaction is Phase 2.

## How does a PostgreSQL checkpoint decide where redo starts?

A PostgreSQL checkpoint must write every dirty page in shared memory, which can be gigabytes. So it spreads the work over minutes, and it is not a snapshot taken at one instant. The checkpointer, the background process that writes checkpoints, runs each one in three stages.

- Start. It fixes the checkpoint's REDO point at the current WAL position. On 17 it writes a CHECKPOINT_REDO record, and the start of that record is the REDO point. Then it tags every buffer that is dirty at that moment. Tagging needs no I/O, so the start is fast.

- Writing. It writes the tagged buffers over checkpoint_completion_target × checkpoint_timeout, 0.9 × 5 min = 4.5 minutes at the defaults. Pages dirtied after the start are not tagged, so this checkpoint ignores them.

- Completion. It writes a checkpoint record, then updates pg_control, the small file that tells recovery where to begin.

Every change before the REDO point is on disk, but that counts only after completion. Until then, pg_control names the previous checkpoint.

The table lists where the lab model stops matching PostgreSQL.

| Question | The lab store | PostgreSQL |
| what a checkpoint saves | the keydir, in one file | every page that was dirty when the checkpoint started |
| how it writes | five steps, three of them syncs | spread over checkpoint_timeout × checkpoint_completion_target, 4.5 minutes at the defaults |
| where recovery starts | the log offset stored in keydir.ckpt | the REDO point of the last completed checkpoint |
| work on restart | replay the log tail | redo from the REDO point, then one immediate checkpoint |

- −5:00 Checkpoint P starts. Its REDO point is the WAL position then.

- 0:00 Checkpoint A starts and notes REDO point A.

- 4:29 A crash here, before A completes, starts redo at P's REDO point. That is 9.5 minutes of WAL, 1.9 intervals.

- 4:30 A completes and updates pg_control.

- 4:31 A crash here starts redo at REDO point A, 4.5 minutes of WAL.

A checkpoint starts early when the WAL grows fast. PostgreSQL stores the WAL in 16 MB files called segments. The size trigger works like this:

- max_wal_size is 1 GB, which is 64 segments.

- PostgreSQL divides it by 1 + checkpoint_completion_target. 64 / 1.9 rounds down to 33 segments, about 528 MB.

- The checkpoint itself takes about 475 MB more while it runs.

- So the worst redo is about 1,003 MB, close to a full max_wal_size.

One measurement on PostgreSQL 18.6 replayed 1,080 MB in 6.0 s, so the predict answer was about 5 to 10 seconds. To size the setting, divide your recovery-time budget by your measured seconds per GB.

  When a size-triggered checkpoint comes, and the worst redo

  max_wal_size, MB
  WAL rate, MB per second
  Trigger after , every . Worst WAL to replay , redo about

This is an illustration, not a forecast. It keeps the target at 0.9, ignores the timer, and uses 5.6 to 7.7 s per GB.

A short interval has its own cost, because the first change to a page after each checkpoint writes a full page image. In the same test, max_wal_size 1GB forced 7 checkpoints in three minutes and wrote 3,815 MB of WAL, about 90% page images. At 8GB there were none, and the WAL was 1,080 MB. So the interval trades redo time against WAL to write, archive and send to replicas. A large index build is WAL too. pgvector, the PostgreSQL extension for vector search, "uses the write-ahead log (WAL)". So building a vector index on a large table likely writes WAL, including page images, which is inferred from the README sentence. It can then trigger size-based checkpoints. The WAL volume of such a build was not checked, so watch the warning line and wal_bytes in pg_stat_wal before and after it.

Restart time is redo plus one immediate checkpoint, which PostgreSQL runs before it accepts connections. In one production case on PostgreSQL 16.8, the checkpointer ran for more than four hours without finishing, and the restart replayed several hours of WAL. A checkpoint that never completes never moves the start of recovery, so nothing bounds the redo. On 17 the likely matching fix, judged by the symptom, is in 17.6. The note reads "Limit the checkpointer process's fsync request queue size". It is for a checkpointer that could try to allocate more than 1 GB, "leading to failure and an infinite loop".

### What you see on a PostgreSQL 17 server

The lab prints RecoveryReport.seconds. A PostgreSQL server gives the same facts in its log and in several views.

| Signal | What it shows |
| log_checkpoints, on by default since 15 | a "checkpoint starting" line, then a "checkpoint complete" line with buffers written, write, sync and total seconds, distance, estimate, lsn and redo lsn |
| checkpoint_warning, 30 s | "checkpoints are occurring too frequently (N seconds apart)", with the hint to raise max_wal_size |
| pg_stat_checkpointer | num_timed counts scheduled checkpoints, completed and skipped. num_requested counts requested checkpoints that were performed. Many requested ones mean max_wal_size is too small |
| pg_stat_bgwriter | on 17 only buffers_clean, maxwritten_clean, buffers_alloc and stats_reset. Its checkpoint columns exist only up to 16 |
| pg_stat_io | writes and fsyncs per backend_type. "Large numbers of fsyncs by client backends could indicate a misconfiguration of shared buffers or of the checkpointer" |
| pg_control_checkpoint() | returns checkpoint_lsn and redo_lsn as a query result, with no shell on the server |
| startup log | "redo starts at", "redo done at" with elapsed time, the end-of-WAL line, and "redo in progress, elapsed time" every log_startup_progress_interval, 10 s by default |

Two read-only queries for PostgreSQL 17 cover the views.

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

The queries were not run. On RDS and Aurora the same views exist, because the engine is PostgreSQL, which is inferred and not checked on an instance.

After a crash, a 17 server logs these lines. They come from the 17 source and were not run.

| Line | What it tells you |
| database system was interrupted and database system was not properly shut down; automatic recovery in progress | The server did not stop cleanly, so it starts crash recovery. |
| redo starts at | The replay begins at the REDO location from pg_control. |
| invalid record length at ...: expected at least 24, got 0 | This is the normal end of the WAL and not an error. |
| redo done at | The replay finished, and the line gives the elapsed time. |
| checkpoint starting: end-of-recovery immediate wait | The one immediate checkpoint runs before the server opens. Its complete line ends with lsn= and redo lsn=. |
| database system is ready to accept connections | Clients can connect again. |

distance in the complete line is the WAL between the starts of the last two checkpoints, in kB, and redo lsn is the REDO point of the checkpoint that completed last. E13 crashes a throwaway cluster so you can read these lines yourself.

  Redo starts at the REDO point of the last completed checkpoint, up to 1.9 intervals back.

  Reading a checkpoint as one instant snapshot hides up to 0.9 intervals of redo.

  Run uv run python phase01_durability/crash_matrix.py --list and say which checkpoint a power loss leaves at points 23 to 27.

Evidence
The three stages: Rogov, "PostgreSQL 14 Internals", section 10.3, pages 170 and 171. The worst case of 1 + checkpoint_completion_target: Rogov, section 10.6, page 177, who gives the same multiplier for the WAL a server must keep. The size trigger: CalculateCheckpointSegments at xlog.c line 2163, REL_17_11, with the same division at line 2342 of REL_14_24. Redo times and the 1GB against 8GB runs: Christophe Pettus, PostgreSQL 18.6, a kill of the postmaster, published 2026-09-29. pgvector: its README. The stuck checkpointer: Stormatics postmortem, 2026-07-01, about PostgreSQL 16.8 on Kubernetes, fixed in 16.10. The 17.6 fix: release-17.sgml lines 8218 to 8228, inside the 17.6 section. That it is the same bug is inferred from the matching symptom. The signals: the 17 sample file line 583 for log_checkpoints, xlog.c REL_17_11 lines 6732 to 6737 for the complete line, checkpointer.c lines 444 and 445 for the warning, system_views.sql lines 1134 to 1175 for the views, PostgreSQL 17 docs Tables 27.23 and 27.25, monitoring.sgml lines 2847 and 2978 to 2995, and xlogrecovery.c lines 1750, 1763 and 1885 for the startup lines. The log line order: xlogreader.c line 669, and xlog.c lines 6297 to 6299 and 6644 to 6652 for " wait".

Go deeper: the settings, page images and wal_compression, the end-of-recovery checkpoint by version, redo time, and the 14 log lines

The three stages in detail

pg_control lives in global/. At the defaults the worst case is 1 + 0.9 = 1.9 intervals of WAL. The times in the timeline are an example at checkpoint_timeout = 5 min and a completion target of 0.9. Checkpoint P completed at −0:30, and checkpoint B would start at 5:00. In the writing stage, a backend that writes a tagged buffer first also clears its tag. The postmaster, the first process of the server, launches the startup process at start, and the startup process runs recovery, per Rogov, page 173. Rogov states the rule plainly: only from completion does the start of the checkpoint become the new starting point of recovery.

CMU 15-445 calls this design a fuzzy checkpoint, because transactions keep running during it. Its Fall 2025 notes for Lecture 22 mark the two ends with a CHECKPOINT-BEGIN and a CHECKPOINT-END record. PostgreSQL 14 to 16 wrote no record at the start, so the REDO point could be the LSN of a record of any type, per Rogov, page 171. Since 17, an online checkpoint first writes a CHECKPOINT_REDO record, and its start LSN is the REDO point, per xlog.c lines 7022 to 7035 at REL_17_11. A shutdown checkpoint writes no such record. The docs name the cost of the long spread. Prolonging checkpoints "affects recovery time", because more WAL must be kept for recovery, per the PostgreSQL 17 docs, section 28.5.

When a checkpoint starts

The defaults are the same in versions 14, 17 and 18, from the 17 sample configuration file, lines 258 to 263, and from a fresh 14.24 cluster for the first four:

| Setting | Default | What it does |
| checkpoint_timeout | 5 min | time between automatic checkpoints |
| max_wal_size | 1 GB | the WAL size that the size trigger is computed from |
| min_wal_size | 80 MB | WAL kept for reuse |
| checkpoint_completion_target | 0.9 | spread checkpoint writes over 90% of the interval |
| checkpoint_warning | 30 s | log a warning if size-triggered checkpoints come closer than this |

The size trigger in five steps at the defaults:

- max_wal_size is 1,024 MB, or 64 WAL segments of 16 MB each. A WAL segment is one file in pg_wal.

- 64 / 1.9 = 33.7, which the code rounds down to 33 segments.

- So a checkpoint is requested after about 33 × 16 = 528 MB of WAL since the last REDO point.

- While it runs, the server writes about 0.9 × 528 = 475 MB more.

- So when it completes, the WAL since the old REDO point is about 528 + 475 = 1,003 MB, close to max_wal_size.

That is the reason for the division, as the code comment explains. The docs also call max_wal_size "a soft limit". Heavy load, a failing archive command, or a high wal_keep_size can push the WAL past it, per the PostgreSQL 17 docs, section 19.5.2.

Full page images and wal_compression

The docs say that a smaller checkpoint interval "increases the volume of output to the WAL". That partly cancels the goal of the smaller interval, and it causes more disk I/O, per the PostgreSQL 17 docs, section 28.5. Rogov measured the size with pgbench, PostgreSQL's load tool, right after a checkpoint, when every page change is a first change:

MB here is 2^20 bytes, as pg_size_pretty prints. The page image bytes from pg_waldump --stats were 21,134,168 and 2,453,755, so 8.6 times smaller. The total WAL was 29 / 10 = 2.9 times less.

Rogov's cluster had data checksums on. In the first run, 93.78% of the page image bytes were in records of the XLOG resource manager, not of the table resource manager. Those are likely the hint-bit images that checksums cause, which is inferred from the record type and not checked. wal_compression compresses page images only, and it is off by default. On PostgreSQL 17 it accepts off, pglz, lz4 and zstd, if the server was built with them. In 14 it is only on or off, and on means pglz. This is from the 17 docs, section 19.5, the 17 sample file, lines 243 and 244, and the 15.0 release notes. The view pg_stat_wal, since PostgreSQL 14, counts page images in wal_fpi and WAL bytes in wal_bytes. Phase 2 computes the page image cost per change for a B-tree, so this lesson does not repeat that model.

The end-of-recovery checkpoint by version

- PostgreSQL 17. The startup process asks the checkpointer for CHECKPOINT_END_OF_RECOVERY | CHECKPOINT_IMMEDIATE | CHECKPOINT_WAIT. This is in PerformRecoveryXLogAction, from xlog.c line 6262 at REL_17_11, with the request at line 6297. The source says the checkpoint is "created before anyone is allowed to write WAL", at line 6959. PostgreSQL 18 has the same code, at lines 6323, 6358 and 7024 of REL_18_0.

- PostgreSQL 14. The startup process runs it itself, with CreateCheckPoint at line 8064 of xlog.c at REL_14_24. The checkpointer runs during crash recovery only since PostgreSQL 15, per the 15.0 release notes. So the 14 line is "end-of-recovery immediate", without " wait".

- After a standby is promoted. PostgreSQL writes only an end-of-recovery record, and the checkpoint comes later.

An earlier version of this lesson said " wait" first appears in 18. The 17 source shows it already in 17, so that was wrong. Whether 15 and 16 print it was not checked. Rogov describes the same step: the checkpoint secures the recovered state on disk, section 10.4, page 174. The checkpoint is immediate, so it is not spread out, and its length grows with the pages that redo dirtied. That length is inferred from the CHECKPOINT_IMMEDIATE flag, and not measured. So a recovery-time target has two parts, the redo and this checkpoint.

The 1GB against 8GB test

Pettus ran PostgreSQL 18.6 with pgbench, four clients, scale 50, 512 MB of shared_buffers, three minutes per run and checkpoint_timeout 15min:

| max_wal_size | TPS | WAL written | checkpoints | wal_fpi |
| 1GB | 3,700 | 3,815 MB | 7, requested | 447,963 |
| 8GB | 4,131 | 1,080 MB | 0 | 91,335 |

At 1GB, page images were "about 90% of the bytes" with wal_compression off. The log warned "checkpoints are occurring too frequently (23 seconds apart)" seven times. A log_checkpoints line showed distance=540676 kB, the 528 MB size trigger. Pettus argues for 8GB with a 15-minute timeout, while the PostgreSQL docs only state the trade.

How long the redo takes

| WAL since the last checkpoint | Redo time | Per GB, or per second |
| 1,080 MB of ordinary WAL | 6.0 s | 6.0 / 1.08 = 5.6 s per GB, 180 MB per second |
| 1,627 MB of ordinary WAL | 12.5 s | 12.5 / 1.627 = 7.7 s per GB |
| 682 MB of full pages | 1.5 s | 455 MB per second |

He describes the redo as "single-threaded, with the data in cache". Pettus gives no hardware details, and his own estimate of 10 to 12 seconds per GB does not match his table. WAL made of full page images replayed faster per megabyte in his test. Pettus gives the reason: "restoring a page image is a copy while an ordinary record has to read the page first". Pettus does not say whether his times include the end-of-recovery checkpoint, and this course did not test it. Redo time also depends on recovery_prefetch, added in PostgreSQL 15 with the default try. It reads ahead the blocks that the next WAL records need, per the 15.0 release notes, the PostgreSQL 17 docs, section 19.5.4, and the 17 sample file, line 267. So a redo timing means something only with its version and this setting. Do not size a production target on these numbers alone.

The stuck-checkpointer postmortem gives no WAL size and no replay time. Its first symptom was ERROR: invalid memory alloc request size, which looked like a memory problem.

More signals, and the lines on PostgreSQL 14

pg_stat_checkpointer also has write_time, sync_time and buffers_written, and 18 adds num_done, completed checkpoints only, and slru_written. pg_stat_wal has wal_fpi, wal_bytes, and on 14 to 17 wal_write, wal_sync and their times. pg_controldata shows "Database cluster state", "Latest checkpoint location" and "Latest checkpoint's REDO location", but it needs a shell on the server. On RDS the log lines go to the instance's PostgreSQL log, which you read in the RDS console. How to export it to CloudWatch Logs was not checked.

These recovery lines are from Rogov's PostgreSQL 14.7 example, page 175, after pg_ctl stop -m immediate. log_checkpoints was off there, so the end-of-recovery checkpoint does not appear:

LOG: database system was interrupted; last known up at 2023-03-06 14:01:49 MSK
LOG: database system was not properly shut down; automatic recovery in progress
LOG: redo starts at 0/3E7EF7E0
LOG: invalid record length at 0/3E7EF890: wanted 24, got 0
LOG: redo done at 0/3E7EF818 system usage: CPU: user: 0.00 s, system: 0.00 s, elapsed: 0.00 s
LOG: database system is ready to accept connections

Here is Rogov's checkpoint line on PostgreSQL 14.7, page 180, after a manual CHECKPOINT:

LOG: checkpoint starting: immediate force wait
LOG: checkpoint complete: wrote 4100 buffers (25.0%); 0 WAL file(s) added, 1 removed, 0 recycled; write=0.076 s, sync=0.009 s, total=0.099 s; sync files=3, longest=0.007 s, average=0.003 s; distance=9213 kB, estimate=9213 kB

On PostgreSQL 17 the complete line ends with two more fields: distance=%d kB, estimate=%d kB; lsn=%X/%X, redo lsn=%X/%X. In PostgreSQL 18 the same line also prints SLRU buffers written, which are the cached pages of small files such as pg_xact, per the 18.0 release notes and xlog.c at REL_18_6, line 6796.

## What changes on RDS, Aurora, Neon and AlloyDB?

Everything above assumes one server that writes its own pages and replays its own WAL. RDS for PostgreSQL works that way. Aurora, Neon and AlloyDB do not, because they move page building and redo into a storage service. Aurora and AlloyDB also have no checkpoint in the database layer.

  RDS for PostgreSQL, and your own server

The database host writes WAL and pages to an EBS volume. Checkpoints and redo run on the database host, as in the parts above.

  Aurora, AlloyDB

The database host sends WAL only to a storage service, and that service builds pages from the WAL. There is no database-layer checkpoint.

  Neon

The compute sends WAL to safekeepers, a Paxos quorum, and the pageserver builds pages from it. Whether the compute runs checkpoints was not checked.

| System | What the database host sends | What happens at a crash |
| RDS for PostgreSQL | WAL and pages, to an EBS volume | normal redo, as above. "full page writes are always "on."" log_checkpoints is on by default, and checkpoint_warning "isn't set" by default |
| Aurora | redo log records only. "No pages are ever written from the database tier, not for background writes, not for checkpointing, and not for cache eviction" | "Nothing is required at database startup." AWS says Aurora "recovers asynchronously on parallel threads, so that your database is open and available immediately" |
| AlloyDB | WAL records only. "there is no need to checkpoint the database layer" | the storage service keeps replaying WAL, and Google says restarts are faster |
| Neon | WAL, to safekeepers, the servers that store the WAL. A commit counts once "a quorum of safekeepers has acknowledged the WAL record via the Paxos protocol" | "Compute nodes do not own durable state and can be replaced freely." A starting compute "simply attaches to existing database history rather than reconstructing local state". What that start runs in detail was not checked |

The decisions that change:

- On RDS, the redo arithmetic above holds. Your levers are max_wal_size, checkpoint_timeout and wal_compression in a custom parameter group. Set checkpoint_warning yourself if you want the warning line, which is inferred from the AWS defaults above.

- On RDS, redo reads from EBS. On gp3, each random read costs 1 to 9 ms, and 3,000 IOPS are included. So redo on gp3 is likely slower per GB than in the measured table, and recovery_prefetch matters more. That is inferred, and not measured.

- On Aurora, max_wal_size does not set your restart time, because Aurora's restart does not replay WAL on the database host. That is inferred for Aurora PostgreSQL from AWS's page, which covers both engines. This lesson did not check whether Aurora uses that setting at all.

- What still applies everywhere. The commit rule still holds. A commit waits until the WAL is durable, now in a storage service, and that wait is IO:XactSync on Aurora. The torn page and checkpoint problems still exist inside the storage service, where you cannot test them.

Evidence
RDS: the AWS page "IO:WALWrite" for RDS for PostgreSQL, a vendor page. Aurora: Verbitski and others, "Amazon Aurora: Design Considerations for High Throughput Cloud-Native Relational Databases", SIGMOD 2017, section 3.2, which describes the MySQL-compatible engine, and the AWS page "Amazon Aurora reliability", section "Recovery from unplanned restarts", a vendor page. AlloyDB: the Google Cloud blog post of 2022-05-12 on AlloyDB storage, a vendor post. Neon: the Neon docs, "The lakebase architecture", at the path architecture-overview, a vendor page. The gp3 numbers: the AWS EBS User Guide. The decisions are inferred from these sources, as each bullet says.

Go deeper: the Aurora numbers that may be old
The six copies and the 4-of-6 write quorum of Aurora come from the 2017 paper, sections 2.1 and 2.2, together with 10 GB segments. The current AWS page says only that copies are kept "in three Availability Zones". Whether Aurora still uses 10 GB segments and the same quorum was not checked. Keep in mind that the 2017 paper is about the MySQL-compatible engine.

## What does OK promise, and which test proves it?

Each part above added a condition to "committed". So the store owes its users one sentence that states them, and a test that fails if it is wrong. The sentence has four parts:

- The moment of the promise. Here, the entry passed a sync that covers it.

- The crash kinds it survives. Process crash, OS crash or power loss.

- What recovery returns. Here, a prefix of the puts in log order.

- What is not covered. These are conditions the store cannot check, such as a drive that ignores flushes.

For --sync full on a Mac, the lab store prints this sentence.

A put that returned OK, after its own sync, with sync=full on darwin, survives a process crash, an OS crash and a power loss. A put that did not return may or may not survive. Recovery returns a prefix of the puts in log order and never returns an entry that fails its CRC. Not covered: damage to data that was already synced, a drive that ignores flush commands, and loss of the device.

The second sentence of the callout matters at the edge of every database. A client whose connection drops during COMMIT cannot tell which case it is in, and Phase 3 shows how a PostgreSQL client finds out.

A crash matrix runs a fixed workload, stops the store at every write step, and checks recovery against the sentence. Each self.hook(...) line in the store is one crash point. The lab's 10 operations, with a checkpoint after the fourth, pass 57 of them.

The workload uses the keys order:1041 to order:1046. The --claim-power-safe run checks the sentence most Python code would claim, that plain os.fsync on a Mac survives a power loss.

Predict: you remove the directory sync after the log is created. A kill -9 at each of the 57 crash points finds no lost put. Under an OS crash or a power loss, at how many crash points does the store lose acknowledged puts?
At 20 crash points for each crash kind, so 40 violations in all. Most people expect 0, because every kill test passed. The kill test cannot see this failure, because a killed process leaves the kernel's copy of the directory in place.

At each crash point the matrix runs recovery on a process, an OS and a power image, which is 171 recoveries. At the 10 points with log bytes in flight it adds five short tears and one hole, which is 60 more. Let S(m) be the contents after the first m operations. The recovered contents must equal S(m) for some m, at most the started count. If the sentence promises that crash kind, m must also be at least the acknowledged count.

These are the expected violations. The self-test of crash_matrix.py asserts the counts of the first, third and fourth rows, and the printed tables were not run.

| Run | process | OS | power |
| default, --sync full, 231 recoveries | 0 | 0 | 0 |
| --real-kill --sync none, 57 kills | 0 | not tested | not tested |
| --skip-dir-sync | 0 | 20 | 20 |
| --sync fsync --claim-power-safe, darwin model | 0 | 0 | 42 |

A kill test passes for a store that never syncs, because kill -9 keeps the page cache. Without the directory sync, the log's name stays not durable until the checkpoint. So a crash from point #7, the first OK, to #26 finds no log, and the store opens empty with no error. The last row is this lesson's running case, found by a test.

### How the matrix counts, and where the two breaks come from

| Stage | Crash points | Hooks | Numbers |
| open a new store | 2 | open.created, open.dir-synced | #1 to #2 |
| ops 1 to 4 | 4 × 5 = 20 | encoded, written, synced, indexed, acked | #3 to #22 |
| checkpoint | 5 | log-synced, tmp-written, tmp-synced, renamed, dir-synced | #23 to #27 |
| ops 5 to 10 | 6 × 5 = 30 | the same five | #28 to #57 |
| total | 2 + 10 × 5 + 5 = 57 |  |  |

The torn-short image appears only where log bytes are in flight. With --sync full that is the put.written step of each of the 10 operations. The five cuts are at 1, 19, 20, half and all but one byte. The expected result for the default run is 0 violations in 231 recoveries, with all 60 torn cases detected. The check, from crash_matrix.py:204, follows.

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

The self-test of crash_matrix.py asserts these counts, so the arithmetic is checked. The full printed table of E5 was not run. An earlier version of this lesson said no lab code had run, and that is no longer true for the self-tests.

The directory sync window. In fsim.py, a name becomes durable only through a directory sync, and the checkpoint's step 5 is the first one. So the window is crash points #7 to #26: 26 − 7 + 1 = 20 points, each failing for the OS crash and the power loss.

--skip-dir-sync: where the boundary breaks. Expected, not run
#1 - #6     no put acknowledged yet          nothing promised  ok
#7 - #26    1 to 4 puts acknowledged, the    log name not      VIOLATION
            log's name is not durable        durable           20 + 20
#27 - #57   the checkpoint synced the        log name durable  ok
            directory
first line: #7 put.acked, os: acknowledged puts lost: recovered S(0),
            acknowledged 1

This is the missing directory fsync of the sync-failure part, and it is silent: the store opens without an error, and it is empty. Whether a real file system shows it depends on that file system. ALICE's Table 1 lists which persistence properties each Linux file system has. The model in fsim.py takes the strict reading, so a store that passes does not depend on one file system's extra ordering. APFS was not part of that study, and its behaviour here was not checked.

The 42 power violations. With --sync fsync on the darwin model and --claim-power-safe, the 42 come from crash points #7 to #22, which is 16, and #32 to #57, which is 26. Between them, the checkpoint's full syncs made the log durable up to operation 4. There are 0 OS violations because the model keeps the drive cache in an OS crash.

What a real kill test adds. --real-kill runs the same workload in a child process on real files. It sends SIGKILL at each of the 57 crash points. The expected result is 0 violations in every sync mode, --sync none too. The count is worked out, and not run. A real kill test is still worth running. It tests the real file calls, the real O_APPEND writes and the real rename, which the model does not. O_APPEND is the open flag that makes every write go to the current end of the file. It cannot test power.

### The sentence changes with the sync mode

promises is the same rule in code, and the crash matrix checks the code against it. The table asks whether an acknowledged put survives.

| Mode, platform | process crash | OS crash | power loss |
| full, macOS: F_FULLFSYNC | yes | yes | yes |
| full, Linux: fsync | yes | yes | yes |
| fsync, macOS | yes | NO, note 1 | NO |
| fsync, Linux | yes | yes | yes |
| none, any | yes | NO | NO |

Every "yes" for power loss assumes a drive that honours flush commands. Note 1: not promised, because Apple's fsync(2) says an OS crash can lose data after plain fsync, even though fsim.py does not model that loss. The Redis and NATS defaults are in the loss-window table of the part on giving up durability.

### How other systems state it

Other systems document such a sentence too. Each one below covers one node only.

| System | The documented boundary, paraphrased |
| PostgreSQL 17, synchronous_commit=on | every mode except off waits for the local WAL flush before it replies |
| SQLite, WAL mode, synchronous=NORMAL | stays consistent, but a commit can roll back after a power loss or OS crash. Commits survive an application crash in every mode |
| SQLite, WAL mode, synchronous=FULL | durable: one more sync of the WAL file after each commit |
| MySQL 8.4, InnoDB with binary logging | durable with sync_binlog=1 and innodb_flush_log_at_trx_commit=1. Other values of innodb_flush_log_at_trx_commit can lose commits. Other values of sync_binlog can leave committed transactions out of the binary log, in a power failure or OS crash |

The SQLite rows depend on the journal mode, so the mode must be in the sentence. The default journal mode is the rollback journal, not WAL, and WAL mode is chosen with PRAGMA journal_mode=WAL. The one-node limit matters. In GitHub's incident of October 2018, a network cut of 43 seconds led to a failover between data centers. The old primaries still held writes that had not been replicated. One of the busiest clusters "had 954 writes in the affected window", and the service was degraded for 24 hours and 11 minutes. So a single-node sentence says nothing about what a failover keeps. Phase 5, section 5.4, extends the sentence to a primary with standbys, and section 5.5 covers failover.

### The boundary for AI agent state

An agent framework that saves its state to PostgreSQL makes the same choice as the stores above. LangGraph saves a checkpoint of the graph state at each step, through a checkpointer such as PostgresSaver. It "supports three durability modes", passed as durability= to each run.

| Mode | When LangGraph writes the checkpoint | The boundary sentence for one finished step |
| exit | "only when graph execution exits": on success, on an error, or at a human-in-the-loop interrupt | survives nothing until the run exits. A process crash mid-run loses every step of the run |
| async, the default | "asynchronously while the next step executes", with "a small risk" of a missing checkpoint if the process crashes | survives a process crash, except possibly the step whose write had not committed yet |
| sync | "synchronously before the next step starts" | survives a crash of the agent process, if the database commit was durable |

The sentences in the third column are inferred from LangGraph's own descriptions, and not tested. The docs page does not give the default, and the source does: async. One put of PostgresSaver is one commit and one WAL flush. Its statements run in a psycopg pipeline, and the server wraps them in one implicit transaction. Each put_writes call is one more. That count is inferred, and not run, so check it with xact_commit in pg_stat_database before and after one step.

So the database half of the agent's sentence comes from the commit and group commit parts. In sync mode, every step waits for those flushes, so the group commit arithmetic applies to agent steps. If the checkpoint tables were UNLOGGED, or the role ran with synchronous_commit = off, the sync sentence would be false after a database crash. And a tool call that runs before its step's checkpoint commits can run again after a restart. The Redis course, Phase 7, part "How does a tool call run twice, and what stops a second payment?", teaches the fix.

### What the boundary leaves out

The sentence covers crashes, not an operator who deletes data or backups that do not restore. The GitLab.com database outage was that case: an engineer wiped the primary database's data directory, and the backups had failed. Recovery from deletion needs its own plan. A limit below the database belongs in the "not covered" part too. Instapaper ran MySQL on RDS, and its bookmarks table "exceeded the 2TB file size limit". The reason was that "MySQL RDS instances created before April 2014 used an ext3 filesystem which has a 2TB file size limit". Its 10 days of backups were "all filesystem snapshots", so "they're also subject to the 2TB file size limit". Limited service came back after 31 hours of downtime. So write the file system and the backup method into the "not covered" part, and test a restore.

### How to test a real service

The crash matrix tests a model, and a kill test tests only process crashes. These tools sit between the two, because each one runs the real program on a device or file system that can lose writes on command. Device-mapper is the Linux layer that builds virtual block devices on top of real ones, and two of the tools are device-mapper targets.

| Tool | What it does |
| LazyFS | a FUSE file system with its own page cache. A clear-cache fault drops unsynced data at a chosen call, and torn-op and torn-seq tear writes. Used on seven systems, PostgreSQL, etcd, ZooKeeper, Redis, LevelDB, PebblesDB and Lightning Network, it found eight new bugs |
| dm-log-writes | a device-mapper target that logs each write in order of completion. It logs a write only at the next flush, so a replay shows what was on disk, not in cache |
| dm-flakey | a device-mapper target with drop_writes, error_writes and corrupt_bio_byte. error_writes is a real kernel version of the failed fsync in E9 |
| diskchecker.pl | the device test of the sync part, with a real power cut |

With these tools, the crash matrix of this lesson becomes a test plan for a real service. Run the service on LazyFS or dm-log-writes, crash it at each write step, and check recovery against the sentence. They are Linux tools, so on a Mac they need a Linux virtual machine.

  State what an OK survives, and back each crash kind with its own test.

  A boundary nobody tested passes every kill test and loses data on an OS crash or power loss.

  Run uv run python phase01_durability/crash_matrix.py --skip-dir-sync and predict its first violation line first.

Evidence
The sentence comes from boundary_statement at kvlog.py:286. The rule in code is promises at kvlog.py:263, and the check is check() at crash_matrix.py:204. The self-test asserts the counts at lines 381 to 383, 397 and 407, and it passed on 2026-10-20 on the M4 Pro with Python 3.12.14. PostgreSQL: PG 17 docs, 19.5. SQLite: sqlite.org, PRAGMA synchronous and "Write-Ahead Logging". MySQL: the 8.4 manual. GitHub: "October 21 post-incident analysis", 2018. LangGraph: the docs page "Checkpointers". The default: libs/langgraph/langgraph/pregel/main.py line 2696 at tag 1.2.16, and the docstring at line 2798. PostgresSaver: __init__.py lines 82, 326 and 477 to 515 at tag checkpointpostgres==3.2.0, with autocommit=True and self._cursor(pipeline=True). The pipeline rule: the psycopg 3 page "Pipeline mode support", "even in autocommit, the server wraps the statements sent in pipeline mode in an implicit transaction, which will be only committed when the Sync is received." The etcd postmortem was published on 2022-04-20. The bug was merged on 2021-05-08 and fixed in v3.5.3 on 2022-04-24, so the 351 days are arithmetic on those dates. An earlier version of this lesson said the bug "was merged in v3.5.0 and fixed in v3.5.3, 351 days later", which read as 351 days between the two releases, so the sentence was changed. GitLab: postmortem of 2017-02-10, outage of 2017-01-31. Instapaper: "Instapaper Outage Cause & Recovery", 2017-02-14, read from the Wayback Machine copy, outage on 2017-02-09. LazyFS: the README at GitHub dsrhaslab/lazyfs, tested with ext4 on Debian 11 and Ubuntu 20.04, and Ramos and others, PVLDB volume 17, issue 11, 2024. dm-log-writes and dm-flakey: the kernel device-mapper docs. diskchecker.pl: named in PG 17 docs, 28.1. Whether LazyFS works with macFUSE was not checked, and neither was the platform support of diskchecker.pl.

Go deeper: the etcd postmortem

A real postmortem about crash testing

The etcd project published the "v3.5 data inconsistency postmortem". A refactor in v3.5.0 stopped saving the consistent index atomically with the data it describes. A crash between the two writes left a member inconsistent. The maintainers reproduced it under heavy load by killing one member with SIGKILL at random. It was reproduced only because one maintainer had /tmp on a normal disk. The fix in v3.5.3 came 351 days after the bug was merged. The postmortem does not say why the disk mattered. A likely reason is that a real device makes each write slower, which widens the window between the two writes. That reason is inferred, not checked. A test on a memory file system, such as a tmpfs /tmp on Linux, never reaches a device at all. So shared/durable.py refuses to measure there.

## What you can do now, and what comes next

You can now say which crash erases a put at each step, and pick and test the durable sync on a Mac and on a Linux server. You can read the PANIC line of a failed sync, count the commits of one request and find the flush wait in pg_stat_activity or Performance Insights. You can choose where to give up durability on purpose, with an UNLOGGED table, one asynchronous transaction or an agent checkpointer mode. You can say where recovery starts and stops, read it in the PostgreSQL 17 log and views, and say what moves out of the host on Aurora, Neon and AlloyDB. And you can write a store's promise with a crash matrix behind it.

Phase 2 answers why one workload runs ten times faster on one storage structure than on another. It also builds the compaction step, which Bitcask calls merge, that this store left out.

Run the lab first, then answer the checkpoint questions without looking back.

## Lab: build the store and break it

Fifteen exercises from the phase. The five self-tests ran, and the rest were not run by the author.

Everything runs on your laptop and costs nothing. The labs use Python 3.12 or later and the standard library only. Two exercises read your local PostgreSQL 17 at /tmp:5432, in a new database named storage_lab. Three exercises, E13 to E15, start a separate throwaway PostgreSQL 17 cluster on port 54329, and two of them crash it on purpose, so they never touch your main cluster. Run all commands from elite-storage/code/. The reading takes about 3 hours, and the labs take about 2.5 to 3.5 hours.

Section numbers used below: 1.1 Where can a write be. 1.2 What must be durable. 1.3 How far one sync call moves the bytes, and when a sync fails. 1.4 A half-written entry. 1.5 Where recovery starts, the PostgreSQL checkpoint, and managed PostgreSQL. 1.6 Group commit, the commits of one request, and giving up durability. 1.7 What OK promises.

Practice: open the lab, E1 to E15
The labs below are written and reviewed, but were not run by the author. The owner chose this on 2026-10-17. One exception: on 2026-10-20, the five self-tests were run with uv run python <file> --self-test, on the M4 Pro, macOS 26.6, Python 3.12.14. Each printed self-test passed. The self-test of crash_matrix.py asserts the counts of E5 to E8, so those counts are checked. Every other "Expected" line says "Not run by the author yet." and then gives the expected shape. The PostgreSQL exercises E11 to E15 target PostgreSQL 17. Their expected lines come from the 17 source and docs, not from a run. Each number in it comes from arithmetic in this phase, or from a cited measurement. The measurements are the earlier course's M2 runs and this course's M4 Pro research. Your timings will differ. The counts from the simulated file system should match exactly, because that part has no randomness and no timing.

What you build. The lab is a Bitcask-style store with a stated durability boundary, in five files:

| File | What it holds | Self-test checks |
| shared/durable.py | durable_sync: F_FULLFSYNC on macOS, fsync on Linux, and the directory sync | the decision table for both platforms, a real sync in every mode |
| phase01_durability/fsim.py | RealFS, and SimFS with three layers: page cache, drive cache, stable media | each layer rule, the fsyncgate rule, directory entries, both torn shapes |
| phase01_durability/kvlog.py | the store: entries with CRC, the keydir, group commit, checkpoint, recovery | each rule of Rules, removed one at a time, fails a check |
| phase01_durability/crash_matrix.py | crash injection at all 57 steps, five crash kinds, the S(m) check | the counts of section 1.7, and each break below |
| phase01_durability/group_commit.py | one sync per put against group commit, on real files | sync counts on a simulated device with a 2 ms sync |

The demonstration of this phase is E5, E6 and E8 together. They show the store and its stated boundary, and the crash matrix across every write step. They also show a torn write that the checksum detects instead of serving it.

All commands run from elite-storage/code/. E13 and E14 are the only exercises that crash PostgreSQL. They use a throwaway cluster that E13 creates itself.

-  E1 (offline). See which system call each sync mode makes on your machine.

- Run: uv run python shared/durable.py --self-test, then uv run python shared/durable.py --explain.

- Expected: Not run by the author yet. self-test passed. Then on a Mac: mode full  -> F_FULLFSYNC, mode fsync -> fsync, mode none  -> none, and the file system apfs. On Linux, both full and fsync map to fsync.

- If it fails: a line F_FULLFSYNC is not supported here, falling back to fsync means the directory is on a network or SMB mount. Use a local folder.

- Teaches: the same Python call means a different guarantee on macOS and Linux.

-  E2 (local). Measure the cost of each sync mode.

- First write your prediction for the median of full and fsync.

- Run: uv run python shared/durable.py --measure 200.

- Expected: Not run by the author yet. Three lines with p50, p99 and max per mode. On a Mac, a fourth line gives the ratio of full to fsync. Compare your medians with the cost diagram in section 1.3, one machine at a time. The none line should be a few microseconds. The M4 Pro table in section 1.3 shows 3 µs for "write, no sync".

- Teaches: a durable commit on a Mac costs milliseconds, and os.fsync hides that.

-  E3 (break-it, local). Kill the store at every write step, with no sync at all.

- Run: uv run python phase01_durability/crash_matrix.py --real-kill --sync none.

- Expected: Not run by the author yet. Dry run: 57 crash points, and a process row of 57 cases with 0 violations. Then the note that a killed process leaves the page cache in place. Then run it with --sync full. The result should be the same.

- If it fails with "child exited with 3": the crash point was never reached. Check that the hook count in --list is 57.

- Teaches: a kill test cannot tell a store that syncs from one that does not.

-  E4 (offline). Run every self-test, and use the store by hand.

- Run: uv run python phase01_durability/fsim.py --self-test, then the same for kvlog.py, crash_matrix.py and group_commit.py.

- Then run: uv run python phase01_durability/kvlog.py --put order:1041=paid --put order:1042=paid --report, and then uv run python phase01_durability/kvlog.py --get order:1041 --report.

- Expected: the four self-tests print self-test passed. Verified on 2026-10-20. The store runs were not run by the author yet. The first store run prints recovery: new store, log created, the boundary sentence, and two OK put lines. The first is bytes 0..34: 20 header bytes, 10 key bytes and 4 value bytes. The second run prints 2 entries replayed and get order:1041: paid.

- Teaches: the boundary sentence is printed by the code that the matrix tests.

-  E5 (offline). The crash matrix with the stated boundary. This is the main demonstration.

- First write your prediction: the number of crash points, the number of recoveries, and the number of violations.

- Run: uv run python phase01_durability/crash_matrix.py.

- Expected: Not run by the author yet. Dry run: 57 crash points. Rows process 57, os 57, power 57, torn-short 50, torn-hole 10, each with 0 violations. The torn rows show 50 and 10 in the torn detected column. Last line: RESULT: 0 violations in 231 recoveries. The stated boundary held. Section 1.7 shows the arithmetic. The self-test asserts these row counts, and it passed on 2026-10-20.

- Teaches: a boundary is backed by a test that checks every write step against it.

-  E6 (break-it, offline). Remove the directory sync after the log is created.

- Run: uv run python phase01_durability/crash_matrix.py --skip-dir-sync.

- Expected: Not run by the author yet. process 0 violations, os 20, power 20. The torn rows have fewer cases, 30 and 6, because the log's name is not durable until crash point #27. The first violation line: #7 put.acked, os: acknowledged puts lost: recovered S(0), acknowledged 1. The self-test asserts the counts 20, 20, 30 and 6, and it passed on 2026-10-20. The violation line itself was not printed.

- Teaches: a synced file whose name is not durable can vanish with all its data.

-  E7 (break-it, offline). Check the claim that plain fsync is durable on a Mac.

- Run: uv run python phase01_durability/crash_matrix.py --sync fsync --claim-power-safe, then uv run python phase01_durability/crash_matrix.py --sync fsync, then uv run python phase01_durability/crash_matrix.py --sync fsync --platform-model linux.

- Expected: Not run by the author yet. With the claim: power 42 violations, os 0, and violations in the torn rows too. Without the claim: 0 violations, because the honest sentence for fsync on macOS promises a process crash only. On the linux model: 0 violations in 231 recoveries, as in E5. The self-test asserts the 42, the 0 and the linux result.

- Teaches: the same code has a different boundary on each platform, and the sentence must say which.

-  E8 (break-it, offline). A torn write, with and without the checksum.

- Run: uv run python phase01_durability/kvlog.py --torn-demo, then uv run python phase01_durability/crash_matrix.py --no-crc.

- Expected: Not run by the author yet. The demo prints the WRONG and RIGHT lines of section 1.4. First 1,200 bytes with 512 zeros, then a stop at offset 1230 with checksum mismatch. The matrix with --no-crc shows torn-hole with 8 violations of 10, and torn-short with 0. The 8 are the puts. The 2 deletes are 30 bytes long, and each hole zeroes the whole entry, so the length check stops them. The self-test asserts the 8 and the 0.

- Teaches: only a checksum catches a write with the right length and the wrong bytes.

-  E9 (break-it, offline). A failed fsync, retried and not retried.

- Run: uv run python phase01_durability/kvlog.py --fsync-error-demo.

- Expected: Not run by the author yet. WRONG: three puts acknowledged, and only order:1041 after the power loss. Recovery stopped at offset 1230 with impossible lengths ksz=0 vsz=0, and 2460 bytes dropped. RIGHT: one put acknowledged and none lost. Both cases print that a restart without power loss sees order:1042 through the page cache.

- Teaches: after an fsync error the only safe action is to stop. The page cache can still show data the disk lacks.

-  E10 (local). One sync per put against group commit, on your SSD.

- First write your prediction for both rates with 16 writers, from section 1.6.

- Run: uv run python phase01_durability/group_commit.py --writers 16 --puts 50 --repeat 3, then uv run python phase01_durability/group_commit.py --writers 1 --puts 200 --repeat 3.

- Expected: Not run by the author yet. With 16 writers, the per-put lines show puts/sync 1.0. Their rate is at or below the M2 limit of 351 per second from section 1.6. The group lines show puts per sync well above 1, a rate several times higher, and a higher p50 latency. With 1 writer, both modes are about the same. Compare runs only with their spread, as the earlier course's Phase 1 taught.

- If the group rate equals the per-put rate: the sync call may not release the interpreter lock. Section 1.6 names this as not checked.

- Teaches: group commit trades a little latency per put for a large gain in throughput.

-  E11 (local, PostgreSQL 17). Read your own cluster's durability settings.

- Run: createdb -h /tmp -p 5432 storage_lab.

- Then run: psql -h /tmp -p 5432 -d storage_lab -c "select name, setting, unit, source from pg_settings where name in ('wal_sync_method','synchronous_commit','full_page_writes','data_checksums','data_sync_retry','commit_delay','commit_siblings','checkpoint_timeout','max_wal_size','wal_writer_delay','checkpoint_completion_target','checkpoint_warning','log_checkpoints','wal_compression','track_wal_io_timing') order by name".

- Then run the counters. All three only read: psql -h /tmp -p 5432 -d storage_lab -c "select num_timed, num_requested, write_time, sync_time, buffers_written, stats_reset from pg_stat_checkpointer", then psql -h /tmp -p 5432 -d storage_lab -c "select checkpoint_lsn, redo_lsn, redo_wal_file, checkpoint_time from pg_control_checkpoint()", then pg_controldata "$(psql -h /tmp -p 5432 -d storage_lab -Atc 'show data_directory')" | grep -E "cluster state|REDO location".

- Expected: Not run by the author yet. From the PostgreSQL 17 sample file and initdb.c: synchronous_commit on, full_page_writes on, data_checksums off, data_sync_retry off, commit_delay 0, commit_siblings 5, checkpoint_timeout 300 with unit s, max_wal_size 1024 with unit MB, wal_writer_delay 200 with unit ms, checkpoint_completion_target 0.9, checkpoint_warning 30, log_checkpoints on, wal_compression off and track_wal_io_timing off. wal_sync_method shows open_datasync on macOS and fdatasync on Linux, inferred from xlogdefs.h. Homebrew's postgresql@17 formula makes its cluster with initdb --locale=en_US.UTF-8 -E UTF-8, without -k, so checksums are off there. A row whose source is not default was changed by your configuration. pg_stat_checkpointer shows how many checkpoints ran on the timer and on request since stats_reset. pg_control_checkpoint() gives the REDO point in SQL, with no shell. pg_controldata shows in production for a running server, and the REDO location of its last checkpoint.

- If it fails: column "checkpoints_timed" does not exist means you ran the PostgreSQL 14 query on 17. The 14 query was select checkpoints_timed, checkpoints_req from pg_stat_bgwriter. relation "pg_stat_checkpointer" does not exist means your server is 16 or older. Use the 14 query there.

- On RDS or Aurora: the first two queries work the same way, which is inferred. pg_controldata needs a shell, so it does not.

- Teaches: your laptop's PostgreSQL acknowledges commits that a power cut can remove, and has no data checksums. Since 15 it does log its checkpoints.

-  E12 (local). Time each WAL sync method of PostgreSQL.

- Run: "$(brew --prefix postgresql@17)/bin/pg_test_fsync" -s 3 -f ./pg_test_fsync.tmp, then delete ./pg_test_fsync.tmp if it is still there. On Linux, run the pg_test_fsync of your 17 install.

- Expected: Not run by the author yet. Compare each line with the M4 Pro table in section 1.3, which this course's research measured with the 14.24 tool. On macOS the 17 tool prints "F_NOCACHE supported on this platform for open_datasync and open_sync.", from pg_test_fsync.c line 224. The 14 tool printed "Direct I/O is not supported on this platform." The open_datasync and open_sync rows may differ from the 14.24 table for the reason in section 1.3.

- Teaches: the one method that flushes the drive cache on macOS is about 180 times slower than the default. 45,480 / 250 = 182, from the 14.24 table.

-  E13 (break-it, local, PostgreSQL 17). Crash a throwaway PostgreSQL cluster, and read its real recovery.

- Get the tools. Homebrew's postgresql@17 formula is at 17.11 and is keg-only, so its programs are not on your PATH by default. Verified from formulae.brew.sh on 2026-10-20. Run: brew install postgresql@17, then export PATH="$(brew --prefix postgresql@17)/bin:$PATH", then pg_waldump --version.

- Expected: a line that starts pg_waldump (PostgreSQL) 17.. If it shows 14, your PATH still finds the old tools first.

- Warning: every command below uses the throwaway directory in $LAB and port 54329. pg_ctl stop -m immediate crashes whichever cluster it names, so never point -D at your main cluster.

- Run: psql -h /tmp -p 5432 -Atc "show data_directory". Write the path down. It is the main cluster, and no step below may use it.

- Run: export LAB="$HOME/pg17-crash-lab", then test ! -e "$LAB" && echo free.

- Expected: free. If nothing prints, the directory exists. Choose a new name. Do not reuse a directory that you did not create for this exercise.

- Run: initdb -D "$LAB".

- Run: pg_ctl -D "$LAB" -l "$LAB/server.log" -o "-p 54329 -k /tmp" start. On 17, log_checkpoints is already on.

- Run: pgbench -h /tmp -p 54329 -i postgres.

- Run: psql -h /tmp -p 54329 -d postgres -At -c "checkpoint" -c "select pg_current_wal_insert_lsn()". Write the LSN down as START.

- Run: pgbench -h /tmp -p 54329 -t 2000 postgres, then psql -h /tmp -p 54329 -d postgres -Atc "select pg_current_wal_insert_lsn()". Write it down as END.

- Run: psql -h /tmp -p 54329 -d postgres -Atc "select pg_size_pretty('END'::pg_lsn - 'START'::pg_lsn)", with your two values in place of END and START.

- Run: echo "$LAB".

- Expected: your throwaway path, not the main cluster path you wrote down. If it prints anything else, stop here.

- Warning: the next step crashes the cluster that -D names.

- Run: pg_ctl -D "$LAB" stop -m immediate. The PostgreSQL 17 docs for pg_ctl say this mode aborts all server processes "without a clean shutdown". In the terms of section 1.1 it is a process crash, so the page cache survives and power loss is not tested.

- Run: pg_controldata "$LAB" | grep -E "cluster state|Latest checkpoint location|REDO location".

- Run: pg_waldump --stats -p "$LAB/pg_wal" -s START -e END, with your two values.

- Run: pg_ctl -D "$LAB" -l "$LAB/server.log" -o "-p 54329 -k /tmp" start, then tail -n 12 "$LAB/server.log".

- Expected: Not run by the author yet. pg_controldata shows Database cluster state: in production. On a stopped server that means it did not shut down cleanly, per Rogov, page 173. The REDO location is your manual checkpoint's REDO point, right before START, unless a timed checkpoint ran during the test. The --stats table ends with a Total line that gives the share of page image bytes. Rogov's 71.54% came from a cluster with data checksums on. Your 17 initdb used the default of off, so expect a smaller share. That is inferred, not measured. On 18, where checksums are on by default, expect the share to be closer to Rogov's. No source ran this exact test, so no WAL size is predicted. The log should show these lines in this order, from the 17 source:

- database system was interrupted

- database system was not properly shut down; automatic recovery in progress

- redo starts at, with the REDO location

- invalid record length at ...: expected at least 24, got 0

- redo done at

- last completed transaction was at log time, from xlogrecovery.c line 1891, because pgbench committed transactions

- checkpoint starting: end-of-recovery immediate wait, then checkpoint complete, which ends with lsn= and redo lsn=

- database system is ready to accept connections

- The source lines are in section 1.5: xlogreader.c line 669, xlog.c lines 6297 and 6644 to 6652, and lines 6732 to 6737.

- Keep the cluster running if you go on to E14 and E15. To clean up later: pg_ctl -D "$LAB" stop, then echo "$LAB". If it prints your throwaway path and nothing else, run rm -rf "$LAB".

- If it fails: if pg_ctl start reports that port 54329 is in use, choose another free port in both start commands and every psql and pgbench command. If pg_waldump cannot find a WAL file, a checkpoint removed old segments. Run the test again with a smaller -t.

- Teaches: a real redo starts at the REDO point, ends at the first invalid record, and is followed by one immediate checkpoint. These are the lines you will meet in a production log.

-  E14 (break-it, local, PostgreSQL 17). Crash the throwaway cluster with an UNLOGGED table, and see what is left.

- This uses the throwaway cluster of E13, at $LAB and port 54329. The same warnings apply. Run echo "$LAB" first, and check that it prints your throwaway path.

- Run: psql -h /tmp -p 54329 -d postgres -c "create table logged_t (id int)" -c "create unlogged table unlogged_t (id int)".

- Run: psql -h /tmp -p 54329 -d postgres -At -c "select pg_current_wal_insert_lsn()" -c "insert into logged_t select generate_series(1, 100000)" -c "select pg_current_wal_insert_lsn()" -c "insert into unlogged_t select generate_series(1, 100000)" -c "select pg_current_wal_insert_lsn()". You get three LSNs: A, B and C.

- Run: psql -h /tmp -p 54329 -d postgres -Atc "select pg_wal_lsn_diff('B', 'A') as logged_bytes, pg_wal_lsn_diff('C', 'B') as unlogged_bytes" -c "checkpoint", with your three values.

- The last part of that command forces a checkpoint. It writes the pages of logged_t to the data files and skips the pages of unlogged_t, per section 1.6.

- Warning: the crash below acts on -D "$LAB". If echo "$LAB" did not print your throwaway path, stop now.

- Run: pg_ctl -D "$LAB" -l "$LAB/server.log" -m immediate restart. It aborts every server process, as the E13 crash did, and then starts the server, which runs crash recovery.

- Run: psql -h /tmp -p 54329 -d postgres -Atc "select (select count(*) from logged_t), (select count(*) from unlogged_t)".

- Then test a clean shutdown. Fill the unlogged table again with psql -h /tmp -p 54329 -d postgres -c "insert into unlogged_t select generate_series(1, 100000)". Then run pg_ctl -D "$LAB" -l "$LAB/server.log" -m fast restart, which shuts the server down cleanly and starts it again. Then run the count query of the step before.

- Expected: Not run by the author yet. logged_bytes is several megabytes, and unlogged_bytes is a few hundred bytes or less, mostly the commit record. That shape is inferred from the docs line "not written to the write-ahead log", and the sizes are not predicted. After the crash: 100000|0. The logged table kept its rows, because the checkpoint wrote its pages and the WAL holds every change. The unlogged table is empty, though the checkpoint ran first. After the clean shutdown: unlogged_t has 100000 rows, because a shutdown checkpoint writes unlogged buffers too. These results are from the PostgreSQL 17 docs for CREATE TABLE and bufmgr.c lines 2924 to 2927.

- If it fails: if the crash case shows rows in unlogged_t, check that you ran -m immediate restart, not -m fast restart.

- Teaches: UNLOGGED gives up the table, not the database. It is safe only for data you can rebuild.

-  E15 (local, PostgreSQL 17). Count the commits of one request: autocommit against one transaction, as in a Django view.

- This uses the throwaway cluster of E13. Restart it with WAL timing on: pg_ctl -D "$LAB" -l "$LAB/server.log" -o "-p 54329 -k /tmp -c track_wal_io_timing=on" restart.

- Create the table that both scripts insert into, with one integer column: psql -h /tmp -p 54329 -d postgres -c "create table ev (v int)".

- Write two pgbench script files. In auto.sql, put ten lines insert into ev values (1);. That is ten commits, like Django's autocommit. In tx.sql, put begin;, the same ten lines, then commit;. That is one commit, like transaction.atomic.

- Run, for each file in turn: psql -h /tmp -p 54329 -d postgres -Atc "select pg_stat_reset_shared('wal')", then pgbench -h /tmp -p 54329 -n -f auto.sql -c 1 -T 20 postgres, then psql -h /tmp -p 54329 -d postgres -c "select wal_write, wal_sync, wal_write_time, wal_sync_time from pg_stat_wal". Repeat with tx.sql.

- Expected: Not run by the author yet. pgbench counts one run of the script as one transaction in its tps line. So compare scripts per second. The auto.sql run should flush about ten times per script, and tx.sql about once. On Linux with fdatasync, the flushes count in wal_sync. On macOS with open_datasync, wal_sync stays 0 and the flushes count in wal_write, as section 1.6 explains. These shapes are inferred from the code and docs of section 1.6.

- Then repeat both runs with the drive flush on: add -c wal_sync_method=fsync_writethrough to the restart command. Expected on the M4 Pro: at about 250 flushes per second from the 14.24 pg_test_fsync table, auto.sql can reach at most about 250 / 10 = 25 scripts per second. tx.sql can reach at most about 250. That is arithmetic, not a run.

- Teaches: the ORM's commit mode sets the number of WAL flushes per request. One transaction per request costs one flush.

## Checkpoint questions

Answer each question before you open the sketches.

Check it yourself: 7 code-reading tasks, in the lab code and in your own services.

- Check 1. Open phase01_durability/kvlog.py:348. This is the directory sync after the log is created, inside Store.open. With --sync none, this line does nothing. Why does that not break the boundary that --sync none states? Which row of the boundary table in section 1.7 shows it?

- Check 2. Open phase01_durability/kvlog.py:402. Recovery cuts the torn tail here and then syncs the cut. Suppose the sync on the next line were removed. Describe a second power loss, during the next put, that brings the torn bytes back. Is an acknowledged put lost, or only an unacknowledged one?

- Check 3. Open phase01_durability/kvlog.py:495. The group commit leader reads target before it calls the sync. Suppose it read target after the sync returned. Which puts could then return OK before their bytes were covered by a sync? Would any assertion in the self-test of kvlog.py catch this change? If not, describe a check that would.

- Check 4. Open phase01_durability/fsim.py:451. This is where the torn hole is placed. For the 30-byte delete of order:1042 at offsets 4920 to 4950, compute the sector that this line zeroes. Then explain why --no-crc in E8 gives 8 violations and not 10.

- Check 5. Open xact.c at tag REL_17_11, line 1487, in RecordTransactionCommit. It is line 1498 at REL_18_0. This is the test that decides between XLogFlush and the asynchronous path. Name the two conditions that force a synchronous flush even with synchronous_commit = off. Read the comment above the test, and say why deleting a table's files is one of them. Then say why a transaction that wrote only to an UNLOGGED table takes the asynchronous path even with synchronous_commit = on.

- Check 6. In any service you own that uses PostgreSQL through an ORM, count the commits of one request. On a quiet development database, run select xact_commit from pg_stat_database where datname = current_database(). Send one request, and run it again. If the difference is larger than the number of business operations in the request, find where autocommit splits them. In Django, look for views without transaction.atomic or ATOMIC_REQUESTS.

- Check 7. In any repository you own that writes files it must not lose, run grep -rn "fsync\|F_FULLFSYNC\|\.Sync()" <your repo>/. For each hit, answer two questions. On macOS, does the call flush the drive cache? And what does the code do when the call returns an error?

Checkpoint 1, eight questions. The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

- Test-out, explain. Walk through what happens when the store runs put order:1041 with --sync full on a Mac. Name the five crash points of the put in order. For each one, say where the entry is and whether the client has its OK. Also say what a power loss there leaves after recovery. Then say what F_FULLFSYNC does not guarantee, even after it returns. Finally, match the steps of the put to the PostgreSQL commit order of section 1.2.

- Test-out, predict. The default workload crashes at point #29, which is put.written of operation 5, the delete of order:1042. The crash is a power loss, and the drive kept the first 15 bytes of the 30-byte entry. Predict what recovery reads from the checkpoint, and where it starts the log scan. Then predict how many log entries it replays, and where it stops. Then give the recovered contents.

- Test-out, demonstrate. Run E5 and E6. Show that the stated boundary holds in all 231 recoveries. Then explain each of the 40 violations that --skip-dir-sync produces, with the arithmetic of the crash points. Finally, run E8 and show the one torn write that the checksum detects and that --no-crc serves.

- A colleague says: "Our CI runs on Macs and production runs on Linux with ext4. Both call os.fsync, and the crash tests pass on CI. So production is covered." Argue for or against, with the numbers and sources of this phase. Say which crash kind the CI test cannot cover and why, and which one it covers well.

- This is broken. A Linux service writes events to an append-only log and syncs after each event. Its log shows one EIO from fsync on Tuesday at 10:00, then a retry that succeeded. The service ran normally. After a reboot on Friday, every event from Tuesday 10:00 onwards is missing, though all of them were acknowledged. What is the cause, and how do you check it? Why are the later events lost too, and not only the one at 10:00? Part b. A second case. After a release, a Django service on RDS for PostgreSQL 17 shows IO:WALWrite as its top wait in Performance Insights. p99 latency doubled, and CPU is below 40%. What is the likely cause, how do you check it with the views of this phase, and what is the fix?

- Show the arithmetic. On the M4 Pro, F_FULLFSYNC took about 4.0 ms. A store has 32 concurrent writers. Compute the upper limit of puts per second with one sync per put, and with group commit. Compute the longest wait of one put with group commit, first with no delay, then with a 1 ms delay. With the delay, what is the new throughput limit, if every batch holds all 32 writers? Part b. A Django view makes 10 writes in autocommit mode on RDS with gp3. Take one WAL flush as 1 ms, the inferred figure of section 1.3. Compute the flush wait per request in autocommit and inside one transaction.atomic block. Then compute the most requests per second one worker can serve, if the flushes were the only cost.

- Given these constraints, design. An example: a single-node audit log runs on a Linux server. It must survive a power loss, take 3,000 events per second at peak, and restart within 30 seconds. The SSD's flush takes about 2 ms. Choose the commit mode, the checkpoint rule, and the recovery rule, and write the durability boundary sentence. Show why one sync per event cannot meet the rate. Part b. The same team runs an AI agent runner on PostgreSQL 17, with LangGraph's PostgresSaver. One agent approves refunds and calls a payment API. Another summarizes documents and keeps an embeddings cache. Choose the LangGraph durability mode for each, say which tables may be UNLOGGED, and write the boundary sentence for each agent. Say what breaks the refund agent's sentence if someone sets synchronous_commit = off for its database role.

- Recovery time. Your PostgreSQL 17 server on RDS must be back within 20 seconds after a crash. It runs the default checkpoint settings and writes WAL at a peak of 6 MB per second. Compute when a checkpoint is triggered, and the worst-case WAL to replay. Explain why it is more than one checkpoint's worth. Use Pettus's table from section 1.5, with its limits, to estimate the redo time at 5.6 and at 7.7 seconds per GB. Then say what else runs before the server opens, how far you could raise max_wal_size, and which signal shows how often size-triggered checkpoints happen. Part b. A colleague says: "We are moving to Aurora PostgreSQL, so we must keep the same max_wal_size limit to keep restarts under 20 seconds." Argue for or against, with the sources of section 1.5.

Answer sketches for the eight questions

- put.encoded: nothing written, no OK, recovery gives the state before the put. put.written: the entry is in the page cache, no OK. A power loss loses it, or tears it, and recovery drops it by length or CRC. put.synced: F_FULLFSYNC returned, so the drive was asked to flush, and the entry survives. No OK yet. put.indexed: the same, now visible to readers. put.acked: the client has its OK and the entry survives. F_FULLFSYNC does not guarantee that the drive honours the flush. Zheng and others found 13 of 15 SSDs that did not behave. It also does not make the file's name durable, which needs the directory sync. In PostgreSQL, put.written matches the commit record in the WAL buffers, put.synced matches XLogFlush, and put.indexed matches ProcArrayEndTransaction, when other sessions see the rows. PostgreSQL also writes the outcome to pg_xact between the last two. With synchronous_commit = off, PostgreSQL makes rows visible before the flush, which the lab store never does.

- The checkpoint is valid and covers 0 to 4920, so the keydir comes from it with the last sequence 4. The log scan starts at 4920 and finds 15 bytes. That is less than the 20-byte header, so short header, 15 of 20 bytes. 0 entries are replayed. Recovery stops at 4920, drops 15 bytes, cuts the file and syncs the cut. Contents: S(4), which is order:1041 v2, order:1042 v1 and order:1043 v1. Operation 5 was not acknowledged, so nothing promised is lost.

- The counts are asserted by the self-test of crash_matrix.py, which passed on 2026-10-20. The printed tables were not run. E5: 57 crash points, 171 + 50 + 10 = 231 recoveries, 0 violations, 60 torn cases detected. E6: from #7, the first acknowledgment, to #26, before the checkpoint's directory sync, the log's name is not durable. That is 26 − 7 + 1 = 20 points. Each fails for the OS crash and for the power loss, so 20 + 20 = 40. E8: the hole in the second put of order:1041 lies at 1536 to 2048. The CRC catches it. --no-crc serves 512 zero bytes.

- Against. On the Mac, os.fsync stops at the drive cache: Apple's fsync(2) page. On Linux ext4 with barriers on, fsync makes the file system flush the drive: PostgreSQL 17 docs, 28.1, and section 1.3's NVMe path. So the two platforms have different boundaries for an OS crash and a power loss. A crash test that kills processes covers the process kind on both, and nothing more. In E7, with --claim-power-safe, the Mac model with os.fsync shows 42 power violations, and the Linux model shows 0. The self-test of crash_matrix.py asserts both counts. The CI test is right about process crashes and says nothing about power. CI timings also come from a different system call than production, so they do not predict production timings.

- fsyncgate. The failed fsync marked the pages clean, and the retry reported success for data that was never written. Rebello and others, ATC 2020, Table 1, found this on ext4, XFS and Btrfs. Check: search the service log and dmesg for the I/O error at 10:00. Then read the log file at the offset written at that time, and look for zeros or old data. The later events are lost because recovery stops at the first bad entry. Everything after the damaged range is dropped, though it was synced. Fix: stop the process at the first fsync error, never retry, and let recovery run on restart. PostgreSQL has done this by default since 2019-02-14. Part b: Likely cause: the release added commits per request. A new code path saves rows one by one in autocommit. AWS's first action for IO:WALWrite is "combine statements into transaction blocks". Check: the commit rate, from xact_commit in pg_stat_database sampled twice, before and after the release, divided by the request rate. Run the wait event query of section 1.6 to confirm the flush wait. Also check num_requested in pg_stat_checkpointer and the log_checkpoints lines, because AWS names frequent checkpoints as the other cause, and RDS does not set checkpoint_warning by default. Fix: wrap the request's writes in transaction.atomic, then compare commits per request again.

- One sync per put: 1 / 4.0 ms = 250 puts per second. Group commit: at most 32 per sync, so 32 × 250 = 8,000 per second. Longest wait without delay: one sync in progress plus its own, 2 × 4.0 = 8.0 ms. With a 1 ms delay: 1 + 4.0 + 4.0 = 9.0 ms in the worst case. Throughput with the delay: one batch per 1 + 4.0 = 5.0 ms. So 32 / 5.0 ms = 6,400 per second. The delay only helps when batches would otherwise be small. Part b: Autocommit: 10 commits × 1 ms = 10 ms of flush wait per request. One atomic block: 1 commit × 1 ms = 1 ms. One worker, flush-bound: 1 / 10 ms = 100 requests per second in autocommit, against 1 / 1 ms = 1,000 with atomic. Group commit does not merge the ten commits of one session, because each waits for its own flush. The 1 ms is inferred from "single-digit millisecond latency". Measure it with pg_stat_wal as in section 1.6.

- One sync per event: 1 / 2 ms = 500 per second, far below 3,000. Group commit: at 3,000 per second and 2 ms per sync, a batch holds 3,000 × 0.002 = 6 events. That is enough. Commit mode: group commit with the full sync, which is fsync on Linux with barriers on. Checkpoint: write the index often enough that the log since the checkpoint replays well within 30 seconds. Measure the scan rate first with RecoveryReport.seconds. Recovery: a CRC per entry, and a stop at the first bad entry. Cut and sync the cut. Sync the directory after create and rename. Stop on any fsync error. Boundary: an OK means the event passed a sync that covers it. It survives a process crash, an OS crash and a power loss, on a drive that honours flushes. Recovery returns a prefix and never a damaged entry. Not covered: damage to synced data and loss of the device. This is an example, not measured. Part b: Refund agent: durability="sync", logged checkpoint tables, synchronous_commit = on, and an idempotency key on the payment call, because a tool call before its step's commit can run again after a restart. Sentence: a finished step survives a crash of the agent process and of the database, on a drive that honours flushes. A step whose checkpoint had not committed may run again. Not covered: loss of the database volume. Summarizer: the default async is fine, because a lost step costs one model call, not money. The embeddings cache can be an UNLOGGED table, because it can be computed again. Sentence: a step may be lost in a process crash, and the cache is empty after a database crash. If the refund agent's role runs with synchronous_commit = off, its checkpoints can vanish in the 600 ms window after the step continued. So the sync sentence is false after a database crash, and the payment can run twice without the idempotency key.

- The size trigger at the defaults is about 528 MB of WAL since the last REDO point: 64 segments / 1.9 = 33, and 33 × 16 MB = 528 MB. At 6 MB per second that is 528 / 6 = 88 seconds, sooner than the 5-minute timer, so checkpoints are size-triggered. 88 s is more than the 30 s checkpoint_warning, so no warning appears. The worst case is a crash right before a checkpoint completes. Recovery then starts at the previous REDO point, because the REDO point counts only after completion. The WAL since then is about 528 + 0.9 × 528 = 1,003 MB, about 1 GB. max_wal_size is a soft limit, so a load spike can push it higher. Redo: 1.0 × 5.6 = 5.6 s and 1.0 × 7.7 = 7.7 s. Then the end-of-recovery checkpoint runs, immediate, with a length not measured here. So the target holds with room. Raising max_wal_size would cut page images. At 7.7 s per GB, 20 s is 20 / 7.7 = 2.6 GB of replay. So about 2 GB leaves room for that checkpoint and the soft limit. Signals: num_requested against num_timed in pg_stat_checkpointer, and the distance of each "checkpoint complete" line. This is a starting point only, with the limits of Pettus's table in section 1.5. Measure on your own hardware, first on a throwaway cluster as in E13. On RDS this arithmetic holds, because RDS replays WAL on the database host. RDS keeps full_page_writes on, so the page-image cost of a short interval is fixed. Part b: Against. Aurora sends only redo records to its storage tier, and the Aurora paper says "Nothing is required at database startup". AWS says Aurora is "open and available immediately after an unplanned restart". So max_wal_size does not set Aurora's restart time. What still matters there is the commit wait, IO:XactSync. Whether Aurora uses max_wal_size at all was not checked. The paper describes the MySQL-compatible engine, and the AWS page covers Aurora as a whole.

## Cheatsheet

Practice: open the cheatsheet
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

## Sources

Practice: open the sources
This course's research fetched every URL below on 2026-10-17. The depth revision of 2026-10-18 added the entries for the PostgreSQL write path, checkpoints, Linux testing, MySQL and AWS, fetched that day. The PostgreSQL 17 revision of 2026-10-20 moved the docs links to version 17. It added the entries for managed and cloud PostgreSQL, the Linux NVMe path, MySQL 8.4, ORMs, agent state and the new cases, fetched that day. Each URL was checked again with check_urls.py on 2026-10-20. Primary sources come first in each group. Vendor pages are marked. The three postmortems that only the lesson tells, LiveJournal, Amazon S3 and Tarsnap, were fetched on 2026-10-18.

The original designs

- ARIES: A Transaction Recovery Method Supporting Fine-Granularity Locking and Partial Rollbacks Using Write-Ahead Logging, Mohan and others, ACM TODS, 1992: https://cs.stanford.edu/people/chrismre/cs345/rl/aries.pdf Focus on: section 1.1, journal pages 97 and 98, for the WAL rule and the commit rule. Section 6 for the three restart passes. PDF page N is journal page N + 93. This copy is a scan with OCR text, so check any new quote against the page image. Read it before section 1.2 and 1.5.

- Bitcask: A Log-Structured Hash Table for Fast Key/Value Data, Sheehy and Smith, Basho, 2010: https://riak.com/assets/bitcask-intro.pdf Focus on: page 2 for the entry layout and the tombstone, page 3 for the keydir, page 5 for recovery. A company paper, not peer reviewed. 15 minutes. Read it before the lab.

What fsync promises, and how it fails

- Can Applications Recover from fsync Failures?, Rebello and others, USENIX ATC, 2020: https://www.usenix.org/system/files/atc20-rebello.pdf Focus on: Table 1 on page 6, which shows each file system after a failed fsync. Section 5 gives the lessons. All tests are on Linux 5.2.11. Read it after section 1.3.

- All File Systems Are Not Created Equal, Pillai and others, USENIX OSDI, 2014: https://www.usenix.org/system/files/conference/osdi14/osdi14-paper-pillai.pdf Focus on: Table 1 for persistence properties per file system, and page 12 for the missing directory fsync. Linux file systems of 2014, no APFS. Read it before E6.

- PostgreSQL's handling of fsync() errors is unsafe and risks data loss at least on XFS, Craig Ringer, pgsql-hackers, 2018: https://www.postgresql.org/message-id/CAMsr%2BYHh%2B5Oq4xziwwoEfhoTZgr07vdGG%2Bhu%3D1adXx59aTeaoQ%40mail.gmail.com Focus on: the first message. It explains the cleared error flag in a few paragraphs. The primary source of fsyncgate.

- PostgreSQL 11.2 release notes, 2019-02-14: https://www.postgresql.org/docs/release/11.2/ Focus on: the item about PANIC instead of retrying after fsync failure, and data_sync_retry. The same item is in 10.7, 9.6.12, 9.5.16 and 9.4.21.

- Fsync Errors, PostgreSQL wiki: https://wiki.postgresql.org/wiki/Fsync_Errors Focus on: the list of platforms and kernel versions. A community page. Its macOS line is not from Apple.

- PostgreSQL's fsync() surprise, Jonathan Corbet, LWN.net, 2018: https://lwn.net/Articles/752063/ Focus on: the explanation of why the checkpointer did not see errors from before it opened the file. A short second account of the same bug.

Disks, operating systems and runtimes

- Understanding the Robustness of SSDs under Power Fault, Zheng, Qin, Tucek and Lillibridge, USENIX FAST, 2013: https://www.usenix.org/system/files/conference/fast13/fast13-final80.pdf Focus on: section 4 for the test method, Table 5 for the failures by drive. Drives from about 2012. The one study here that cut real power.

- fsync(2), Apple xnu source, tag xnu-12377.121.6: https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.121.6/bsd/man/man2/fsync.2 Focus on: the paragraph about the drive cache, the sentence about power loss or an OS crash, and F_FULLFSYNC. Use this copy, not the older archive page.

- fcntl(2), Apple xnu source, tag xnu-12377.121.6: https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.121.6/bsd/man/man2/fcntl.2 Focus on: lines 207 to 245, F_BARRIERFSYNC and F_FULLFSYNC. Apple's older archive copy of this page does not list APFS, so use this copy.

- fd_fsync_darwin.go, Go source, tag go1.27.2: https://github.com/golang/go/blob/go1.27.2/src/internal/poll/fd_fsync_darwin.go Focus on: line 22, the F_FULLFSYNC call, and the ENOTSUP fallback after it. History: Go has used F_FULLFSYNC on darwin since Go issue 26650, closed on 2018-08-22 for Go 1.12. The fallback comes from Go issue 64215. That it first shipped in Go 1.23 is inferred from the issue's milestone.

- drivers/nvme/host/core.c, Linux source, tag v6.12: https://github.com/torvalds/linux/blob/v6.12/drivers/nvme/host/core.c Focus on: lines 2188 to 2191, the volatile write cache test, line 812 for the Flush command, and lines 980 and 981 for the FUA bit.

- fs/jbd2/commit.c and fs/ext4/fsync.c, Linux source, tag v6.12: https://github.com/torvalds/linux/blob/v6.12/fs/jbd2/commit.c Focus on: lines 152 to 154, the commit block with REQ_PREFLUSH | REQ_FUA. The fsync side is at https://github.com/torvalds/linux/blob/v6.12/fs/ext4/fsync.c, lines 111 to 113 and 171.

- nvme-id-ctrl, nvme-cli documentation: https://github.com/linux-nvme/nvme-cli/blob/master/Documentation/nvme-id-ctrl.txt Focus on: the command that prints the controller fields, and the -H option for readable output. The page does not describe vwc. Current nvme-cli calls nvme id-ctrl a deprecated alias of nvme id ctrl.

- nvme-print-stdout.c, nvme-cli source, tag v2.11: https://github.com/linux-nvme/nvme-cli/blob/v2.11/nvme-print-stdout.c Focus on: lines 2246 to 2264 and 3043, the vwc output and its bit 0, "Volatile Write Cache Present".

- posixmodule.c, CPython source, tag v3.14.8: https://github.com/python/cpython/blob/v3.14.8/Modules/posixmodule.c Focus on: os_fsync_impl near line 3993, which calls the plain fsync. CPython issue 56086 asks os.fsync to flush the drive. It was still open on 2026-10-17.

PostgreSQL documentation, version 17

- 19.5 Write Ahead Log, PostgreSQL 17: https://www.postgresql.org/docs/17/runtime-config-wal.html Focus on: wal_sync_method, full_page_writes, synchronous_commit, commit_delay, the checkpoint settings in 19.5.2 and recovery_prefetch in 19.5.4. Replace 17 with 14 in the URL for an old server, where the chapter is 20.5.

- 28.1 Reliability, PostgreSQL 17: https://www.postgresql.org/docs/17/wal-reliability.html Focus on: drive caches, the macOS fsync_writethrough advice, the 512-byte sectors, and the sentence on BBU controllers and partial page writes.

- 28.2 Data Checksums, PostgreSQL 17: https://www.postgresql.org/docs/17/checksums.html Focus on: the default of off, what checksums cover, and pg_checksums for an offline cluster.

- 28.4 Asynchronous Commit, PostgreSQL 17: https://www.postgresql.org/docs/17/wal-async-commit.html Focus on: the loss window of synchronous_commit=off, the per-transaction rule, and the warning about external actions.

- 28.5 WAL Configuration, PostgreSQL 17: https://www.postgresql.org/docs/17/wal-configuration.html Focus on: how crash recovery finds the redo point from the latest checkpoint, the spread checkpoint, the full page cost of short intervals, the "gangway effect" and the commit_delay starting value.

- 19.14 Error Handling, PostgreSQL 17: https://www.postgresql.org/docs/17/runtime-config-error-handling.html Focus on: data_sync_retry, and why a retry after a write-back failure is unsafe.

- CREATE TABLE, PostgreSQL 17: https://www.postgresql.org/docs/17/sql-createtable.html Focus on: the UNLOGGED entry. Read it before you make a table unlogged.

- 65.5 The Initialization Fork, PostgreSQL 17: https://www.postgresql.org/docs/17/storage-init.html Focus on: how an unlogged table is reset after a crash. One short paragraph.

- 18.4 Managing Kernel Resources, PostgreSQL 17: https://www.postgresql.org/docs/17/kernel-resources.html Focus on: "Linux Memory Overcommit", the OOM killer line, and vm.overcommit_memory=2.

- pg_checksums, PostgreSQL 17: https://www.postgresql.org/docs/17/app-pgchecksums.html Focus on: --enable on a stopped cluster, before a move to 18.

- PostgreSQL 18.0 release notes, 2025-09-25: https://www.postgresql.org/docs/release/18.0/ Focus on: the initdb change that enables data checksums by default, listed under incompatibilities, and the move of WAL I/O columns from pg_stat_wal to pg_stat_io.

- Versioning Policy, PostgreSQL: https://www.postgresql.org/support/versioning/ Focus on: the final release dates. Version 14 ends on 2026-11-12, version 17 on 2029-11-08.

The PostgreSQL write path, checkpoints and recovery

- PostgreSQL 14 Internals, Egor Rogov, Postgres Professional, 2023: https://edu.postgrespro.com/postgresql_internals-14_en.pdf Focus on: chapter 10, pages 164 to 181, for the LSN, pg_waldump, the spread checkpoint and its REDO point, recovery after pg_ctl stop -m immediate, and checkpoint monitoring. Chapter 11, pages 182 to 191, for asynchronous commit with pgbench, checksums, full page images and wal_compression. Every example runs on PostgreSQL 14.7, and the hardware is not stated. A free book, not peer reviewed. Read chapter 10 with section 1.5. Its view and log examples are 14 output, so compare them with the 17 tables of section 1.5.

- PostgreSQL source, tag REL_17_11, src/backend/access/transam: https://github.com/postgres/postgres/tree/REL_17_11/src/backend/access/transam Focus on: xact.c, RecordTransactionCommit from line 1304, for the commit order, and the comment at line 1467 on transactions that write no WAL. xlog.c: CalculateCheckpointSegments at line 2163, the LWLockAcquireOrWait call in XLogFlush at line 2852, PerformRecoveryXLogAction at line 6262, LogCheckpointStart at line 6627, the checkpoint log line at 6732, and issue_xlog_fsync at line 8739. xlogrecovery.c lines 1750 to 1885 for the redo log lines. xlogreader.c lines 669, 1165 and 1330 for the end-of-WAL and prev-link checks. The whole tree is at the same tag, for fd.c, bufmgr.c, sync.c and system_views.sql.

- PostgreSQL 17 release notes, source file: https://github.com/postgres/postgres/blob/REL_17_11/doc/src/sgml/release-17.sgml Focus on: lines 1953 to 1966, the 17.11 fix for missing full page images of visibility map pages. Lines 8218 to 8228, the 17.6 checkpointer fsync queue fix. Lines 14781 to 14783, faster contended WAL writes. Line 14841, pg_stat_checkpointer.

- 9.28 System Administration Functions, PostgreSQL 17: https://www.postgresql.org/docs/17/functions-admin.html Focus on: pg_current_wal_insert_lsn, pg_current_wal_lsn and pg_current_wal_flush_lsn.

- 28.6 WAL Internals, PostgreSQL 17: https://www.postgresql.org/docs/17/wal-internals.html Focus on: the LSN as a byte offset, and how two LSNs give the WAL between them.

- 27.2 The Cumulative Statistics System, PostgreSQL 17: https://www.postgresql.org/docs/17/monitoring-stats.html Focus on: Table 27.23 pg_stat_io, Table 27.25 pg_stat_checkpointer, Table 27.26 pg_stat_wal and its note on open_datasync, the wait event tables, and checksum_failures in pg_stat_database. For version 14, pg_stat_bgwriter is Table 28.21 in the same chapter of the 14 docs.

- 19.8 Error Reporting and Logging, PostgreSQL 17: https://www.postgresql.org/docs/17/runtime-config-logging.html Focus on: log_checkpoints, default on, and log_startup_progress_interval. The 14 page, section 20.8, gives log_checkpoints the default off.

- pg_walinspect, PostgreSQL 17: https://www.postgresql.org/docs/17/pgwalinspect.html Focus on: pg_get_wal_stats, which gives pg_waldump --stats in SQL. Useful where you have no shell.

- pg_waldump, PostgreSQL 17: https://www.postgresql.org/docs/17/pgwaldump.html Focus on: -p, -s, -e and --stats, the options E13 uses.

- pg_ctl, PostgreSQL 17: https://www.postgresql.org/docs/17/app-pg-ctl.html Focus on: the three stop modes. Immediate mode leads to crash recovery at the next start.

- pg_test_fsync, PostgreSQL 17: https://www.postgresql.org/docs/17/pgtestfsync.html Focus on: the -f option, to test the file system that holds the WAL.

- PostgreSQL 15.0 release notes: https://www.postgresql.org/docs/release/15.0/ Focus on: log_checkpoints on by default, startup progress messages, recovery_prefetch, the checkpointer during crash recovery, and LZ4 and Zstandard for wal_compression.

- PostgreSQL 17.0 release notes: https://www.postgresql.org/docs/release/17.0/ Focus on: the new view pg_stat_checkpointer, which took the checkpoint columns from pg_stat_bgwriter, and the new checkpoint delay wait events.

- 18.2 Creating a Database Cluster, PostgreSQL 17: https://www.postgresql.org/docs/17/creating-cluster.html Focus on: section 18.2.2.1, "NFS", for the hard mount option and the sync export option.

- postgresql@17, Homebrew formula: https://formulae.brew.sh/formula/postgresql@17 Focus on: the version, 17.11 on 2026-10-20, and that it is keg-only, so E13 adds it to PATH.

Managed and cloud PostgreSQL

- IO:WALWrite, Amazon RDS User Guide: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/wait-event.iowalwrite.html Focus on: the context of the wait, "full page writes are always "on."", the log_checkpoints and checkpoint_warning defaults on RDS, and "Reduce the number of commits". A vendor page.

- IO:XactSync, Amazon Aurora User Guide: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/apg-waits.xactsync.html Focus on: what the wait means on Aurora storage, and the metrics CommitThroughput and CommitLatency. A vendor page.

- Amazon Aurora reliability, Amazon Aurora User Guide: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.Reliability.html Focus on: "Survivable page cache" and "Recovery from unplanned restarts". A vendor page.

- Amazon Aurora: Design Considerations for High Throughput Cloud-Native Relational Databases, Verbitski and others, SIGMOD, 2017: https://www.cs.purdue.edu/homes/csjgwang/CS592DisaggregatedDB/AuroraSIGMOD17.pdf Focus on: section 2.1 for the 4-of-6 quorum, and section 2.2 for 10 GB segments. Then read section 3.2, "Offloading Redo Processing to Storage", for why no pages leave the database tier and why startup needs no recovery. It describes the MySQL-compatible engine of 2017. A course copy of the paper.

- AlloyDB for PostgreSQL under the hood: Intelligent, database-aware storage, Google Cloud blog, 2022-05-12: https://cloud.google.com/blog/products/databases/alloydb-for-postgresql-intelligent-scalable-storage/ Focus on: the three parts of the storage layer, and the paragraph on why there is no database-layer checkpoint. A vendor post.

- The lakebase architecture, Neon docs: https://neon.com/docs/introduction/architecture-overview Focus on: safekeepers and the Paxos quorum for commits, the pageserver, and stateless compute. A vendor page.

- Amazon EBS volume types, Amazon EBS User Guide: https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html Focus on: the comparison table for gp3 and io2 Block Express: durability, IOPS and latency. A vendor page.

- General Purpose SSD volumes, Amazon EBS User Guide: https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html Focus on: gp3's "single-digit millisecond latency" and the 3,000 IOPS baseline. A vendor page.

Applications and agent state

- Database transactions, Django 5.2 documentation: https://docs.djangoproject.com/en/5.2/topics/db/transactions/ Focus on: "Django's default behavior is to run in autocommit mode", ATOMIC_REQUESTS, savepoints in nested atomic, and on_commit().

- Transactions management, psycopg 3 documentation: https://www.psycopg.org/psycopg3/docs/basic/transactions.html Focus on: the warning that a simple SELECT starts a transaction by default.

- Pipeline mode support, psycopg 3 documentation: https://www.psycopg.org/psycopg3/docs/advanced/pipeline.html Focus on: the note that even in autocommit, statements sent in pipeline mode form one implicit transaction until the Sync.

- Checkpointers, LangGraph documentation: https://docs.langchain.com/oss/python/langgraph/checkpointers Focus on: "Durability modes", the three modes exit, async and sync. The page does not give the default.

- pregel/main.py, LangGraph source, tag 1.2.16: https://github.com/langchain-ai/langgraph/blob/1.2.16/libs/langgraph/langgraph/pregel/main.py Focus on: line 2696, the default durability "async", and the docstring at line 2798.

- PostgresSaver, LangGraph source, tag checkpointpostgres==3.2.0: https://github.com/langchain-ai/langgraph/blob/checkpointpostgres%3D%3D3.2.0/libs/checkpoint-postgres/langgraph/checkpoint/postgres/__init__.py Focus on: line 82, autocommit=True, and put from line 268.

- README, pgvector: https://github.com/pgvector/pgvector Focus on: the answer to "Is replication supported?", which says pgvector uses the WAL.

- VZDiskImageSynchronizationMode, Apple developer documentation: https://developer.apple.com/documentation/virtualization/vzdiskimagesynchronizationmode Focus on: the three modes full, fsync and none for a virtual disk on a Mac.

Testing durability on a real system

- When Amnesia Strikes: Understanding and Reproducing Data Loss Bugs with Fault Injection, Ramos and others, PVLDB volume 17, issue 11, 2024: https://www.vldb.org/pvldb/vol17/p3017-ramos.pdf Focus on: the abstract, the table of systems and versions, and the paragraph "Protection and recovery" for the PostgreSQL torn page test. Read it before you plan a crash test of a real service.

- LazyFS, GitHub dsrhaslab/lazyfs: https://github.com/dsrhaslab/lazyfs Focus on: the fault types clear-cache, torn-op and torn-seq, and the tested platforms, ext4 on Debian 11 and Ubuntu 20.04.

- dm-log-writes, Linux kernel docs: https://docs.kernel.org/admin-guide/device-mapper/log-writes.html Focus on: "Log Ordering". Writes are logged only at the next flush, so a replay shows what was on disk.

- dm-flakey, Linux kernel docs: https://docs.kernel.org/admin-guide/device-mapper/dm-flakey.html Focus on: drop_writes, error_writes and corrupt_bio_byte.

- Explicit volatile write back cache control, Linux kernel docs: https://docs.kernel.org/block/writeback_cache_control.html Focus on: REQ_PREFLUSH, REQ_FUA, and what the block layer does for a device with no volatile cache.

- sysfs-block, Linux kernel ABI: https://www.kernel.org/doc/Documentation/ABI/stable/sysfs-block Focus on: the entry /sys/block/<disk>/queue/write_cache and its warning about switching to "write through".

- diskchecker.pl, Brad Fitzpatrick, LiveJournal: https://brad.livejournal.com/2116715.html Focus on: how the client and server check that flushed data survives a power cut. This is the link the PostgreSQL 28.1 docs give. A personal blog post.

- open(2) and fsync(2), Linux man-pages: https://man7.org/linux/man-pages/man2/open.2.html Focus on: O_DIRECT and its note that it does not give the guarantees of O_SYNC. The fsync(2) page at https://man7.org/linux/man-pages/man2/fsync.2.html gives the Linux 4.13 change to error reporting.

MySQL and cloud devices

- What Is New in MySQL 8.4 since MySQL 8.0, MySQL 8.4 Reference Manual: https://dev.mysql.com/doc/refman/8.4/en/mysql-nutshell.html Focus on: Table 1.1, the changed InnoDB defaults: innodb_flush_method, innodb_use_fdatasync, innodb_doublewrite_files, innodb_doublewrite_pages and innodb_log_buffer_size.

- InnoDB Startup Options and System Variables, MySQL 8.4 Reference Manual: https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html Focus on: innodb_flush_method and what O_DIRECT does, innodb_use_fdatasync, innodb_doublewrite and its default ON, and innodb_flush_log_at_trx_commit.

- Doublewrite Buffer, MySQL 8.4 Reference Manual: https://dev.mysql.com/doc/refman/8.4/en/innodb-doublewrite-buffer.html Focus on: why InnoDB writes each page twice, and the DETECT_ONLY mode.

- MySQL Product Support EOL Announcements, Oracle: https://www.mysql.com/support/eol-notice.html Focus on: the line on MySQL 8.0 and Sustaining Support from 2026-04-21.

- Binary Logging Options and Variables, MySQL 8.4 Reference Manual: https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html Focus on: sync_binlog, its default of 1, and the pair of settings for the greatest durability.

- Torn write prevention, Amazon EC2 User Guide: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/storage-twp.html Focus on: the first section, which says all-or-nothing writes remove the need for the doublewrite buffer. A vendor page, so its percentages are vendor claims.

SQLite

- Atomic Commit In SQLite: https://www.sqlite.org/atomiccommit.html Focus on: section 2 for the hardware assumptions, and section 9.2 for drives that report a flush early.

- Pragma statements: https://www.sqlite.org/pragma.html Focus on: PRAGMA synchronous for the durability of each mode, and fullfsync and checkpoint_fullfsync for macOS, both off by default.

- Write-Ahead Logging: https://www.sqlite.org/wal.html Focus on: the first paragraph. The default is the rollback journal.

Incidents and analyses

- Jepsen: MariaDB Galera Cluster 12.1.2, Kyle Kingsbury, 2026: https://jepsen.io/analyses/mariadb-galera-cluster-12.1.2 Focus on: section 3.1 for the loss under the recommended setting, and section 4. Section 3.2 is a separate loss with no root cause.

- Configuring MariaDB Galera Cluster, MariaDB docs: https://mariadb.com/docs/galera-cluster/galera-management/configuration/configuring-mariadb-galera-cluster Focus on: the current advice on innodb_flush_log_at_trx_commit. Compare it with the Wayback copy of 2026-03-08.

- InnoDB System Variables, MariaDB docs: https://mariadb.com/docs/server/server-usage/storage-engines/innodb/innodb-system-variables Focus on: innodb_flush_log_at_trx_commit and its values 0 to 3.

- Jepsen: NATS 2.12.1, Kyle Kingsbury, 2025: https://jepsen.io/analyses/nats-2.12.1 Focus on: section 3.4, the two-minute fsync default. LazyFS is the tool that models power loss there.

- v3.5 data inconsistency postmortem, etcd project, 2022: https://github.com/etcd-io/etcd/blob/main/Documentation/postmortems/v3.5-data-inconsistency.md Focus on: the root cause and the line about /tmp on a normal disk. A first-party postmortem with dates.

- Postmortem of database outage of January 31, GitLab, 2017: https://about.gitlab.com/blog/postmortem-of-database-outage-of-january-31/ Focus on: the timeline. It is an operator deletion and failed backups, not a sync failure.

- De-bottlenecking Aurora MySQL for 19 Million concurrent users, Ishank Gulati, Disney+ Hotstar, 2023: https://web.archive.org/web/20230131210030id_/https://blog.hotstar.com/de-bottlenecking-aurora-mysql-for-19-million-concurrent-users-ee98d6247cfe Focus on: "Root Cause" for the 1:10 fan-out of commits, and "Impact" for the 30% and 7x numbers. The live page returned 403, so this is the Wayback Machine copy.

- Working with PostgreSQL, Satya Sarangi, Zerodha, 2021: https://zerodha.tech/blog/working-with-postgresql/ Focus on: the paragraph on the cache database with fsync and WAL off.

- Roblox Return to Service, Roblox, 2022, about the outage of 10/28-10/31 2021: https://about.roblox.com/newsroom/2022/01/roblox-return-to-service-10-28-10-31-2021 Focus on: the BoltDB freelist analysis, the 4.2 GB store with 489 MB of data and the 7.8 MB written per append.

- October 21 post-incident analysis, GitHub, 2018: https://github.blog/news-insights/company-news/oct21-post-incident-analysis/ Focus on: the 954 writes not replicated in one cluster. It shows why a single-node boundary says nothing about a failover.

- Instapaper Outage Cause & Recovery, Brian Donohue, 2017: https://web.archive.org/web/20170216165223id_/https://medium.com/making-instapaper/instapaper-outage-cause-recovery-3c32a7e9cc5f Focus on: "Root cause" for the ext3 2 TB limit and the snapshot backups with the same limit. The Wayback Machine copy, because the live page returned 403.

- Inside a PostgreSQL Checkpointer Bug: A Production Postmortem, Warda Bibi, Stormatics, 2026: https://stormatics.tech/blogs/postgresql-checkpointer-bug-causing-infinite-retry-loop Focus on: why a stuck checkpointer leaves hours of WAL to replay. No numbers for the replay itself. Read it with the 17.6 release note.

- Power-loss post-mortem, Brad Fitzpatrick, LiveJournal lj_dev, 2005: https://lj-dev.livejournal.com/670215.html Focus on: the list of what failed after the power cut, and the plan to turn off the drive caches and test power cuts. A first-party post. Fetched on 2026-10-18.

- S3 Downtime: More Missing Bites, Rich Miller, Data Center Knowledge, 2008: https://www.datacenterknowledge.com/outages/s3-downtime-more-missing-bites Focus on: Amazon's quoted account of the single-bit errors and the missing checksum. Amazon's own page, status.aws.amazon.com/s3-20080720.html, returned 404 on 2026-10-18, so this is a second-hand report.

- 2023-07-02 -- 2023-07-03 Tarsnap outage post-mortem, Colin Percival, Tarsnap, 2023: https://mail.tarsnap.com/tarsnap-announce/msg00050.html Focus on: the two recovery steps, and the two things that slowed the replay. A first-party post. Fetched on 2026-10-18.

Measurements of group commit and recovery

- commit_delay for better performance: a PostgreSQL benchmark, Laurenz Albe, CYBERTEC, 2025: https://www.cybertec-postgresql.com/en/commit_delay-performance-postgresql-benchmark/ Focus on: the results table and the hardware setup, with the disk limited to 1,000 IOPS.

- Testing the Group Commit Fix, Vadim Tkachenko, Percona, 2011: https://www.percona.com/blog/testing-the-group-commit-fix/ Focus on: the two test tables, with and without the controller's write cache. The unit is not stated.

- The synchronous_commit parameter and streaming replication, Kaarel Moppel, CYBERTEC, 2016: https://www.cybertec-postgresql.com/en/the-synchronous_commit-parameter/ Focus on: the two rows with asynchronous replication, on and off. Phase 5, section 5.4, covers the synchronous replication rows.

- All Your GUCs in a Row: max_wal_size, Christophe Pettus, 2026: https://thebuild.com/blog/all-your-gucs-in-a-row-max_wal_size/ Focus on: the redo time table. New, not peer reviewed, no hardware given.

- Redis persistence, Redis docs: https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/ Focus on: the appendfsync policies and their stated loss windows.

Lectures

- CMU 15-445/645 Fall 2025, Lecture 21: Database Logging, Andy Pavlo: https://www.youtube.com/watch?v=CedEy54pe3g Focus on these times: 0:17:32 steal and force policies 0:19:40 force defined 0:24:21 shadow paging 0:39:25 SQLite rollback journal 0:44:41 write-ahead logging 0:48:46 WAL implementation 0:51:30 log record contents 0:55:02 group commit 1:10:32 checkpoints 1:19:10 summary The times are YouTube's auto-generated chapters, and five were checked against the auto-generated captions. Two spoken claims disagree with the docs. At about 1:19:10 the captions show him saying that synchronous commit is not on by default in PostgreSQL. The PostgreSQL 14, 17 and 18 docs, and a fresh 14.24 cluster, say on. At about 0:39:25 they show him saying that SQLite now uses the WAL by default. The SQLite docs say the default is the rollback journal. This phase teaches the docs.

- Lecture 21 slides: https://15445.courses.cs.cmu.edu/fall2025/slides/21-logging.pdf Focus on: the group commit and checkpoint slides, to read with the video.

- Lecture 21 notes, CMU 15-445 Fall 2025: https://15445.courses.cs.cmu.edu/fall2025/notes/21-logging.pdf Focus on: section 2, the STEAL and FORCE policies, which section 1.2 uses.

- Lecture 22 notes, Database Crash Recovery, CMU 15-445 Fall 2025: https://15445.courses.cs.cmu.edu/fall2025/notes/22-recovery.pdf Focus on: the LSN types, non-fuzzy and fuzzy checkpoints with CHECKPOINT-BEGIN and CHECKPOINT-END, and the ARIES passes. Read it after section 1.5, to compare ARIES with PostgreSQL.

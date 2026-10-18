A small order store runs on your Mac. It appends each put as one entry, a *log record*, to the end of one file, the log. A client sends `put order:1041`, and the store replies OK. It sends `put order:1042`, and the store replies OK again. One millisecond later the power fails, and on restart both orders are gone. The client holds a receipt for each one.

The store wrote each entry, called `os.fsync`, and only then replied. On your Apple M2 that call took about 0.1 ms, because on macOS `os.fsync` hands the data to the drive and returns. The drive writes it to flash later. This lesson follows those two orders down to the disk and back through recovery.

### What you must know

1. **An OK is safe once its log record reaches storage that keeps data without power. Other writes can wait.**Say what must be durable at commit.
2. **Only some calls like fsync make the drive write to flash. One slow call can serve many waiting commits.**Pick the sync call, stop on its error, keep throughput.
3. **A length check catches a short write. Only a checksum, a value computed from the bytes, catches wrong bytes.**Make recovery stop at the right place.
4. **Recovery replays the log since the last finished checkpoint began. That checkpoint wrote all older changes to disk.**Predict restart time and read a checkpoint.
5. **Killing the process tests only a process crash. A durability promise needs its own test for each crash kind.**Write and test your store's promise.

## Where can a write be when the crash comes?

A write moves down through four places, and each kind of crash erases a different set of them.

1. **process memory**Python's `f.write()` often only fills the program's own buffer until `flush()`
2. **page cache**`os.write` copies the bytes into the kernel's memory
3. **drive cache**volatile memory inside the drive
4. **stable media**the flash, which keeps data without power

The *page cache* is the kernel's copy of recently used file pages. A page that holds bytes not yet on the device is a *dirty page*, and the kernel writes it back later. The disk itself has two parts, a volatile cache inside the drive and the *stable media* behind it.

| Crash kind | Example | What survives |
|---|---|---|
| process crash | `kill -9`, a segfault | page cache and disk |
| OS crash | a kernel panic, a hard reset with power still on the drive | the disk, including the drive's cache |
| power loss | a pulled cord, a dead cloud host | only what reached stable media |

Two words now mean different things. An *acknowledged write* is one the store has told the client is done. A *durable write* is one that survives the crash kinds you name. The line between those crash kinds is the store's *durability boundary*, and the last part of this lesson writes it down and tests it.

In the running case, `os.fsync` moved both orders out of the page cache into the drive cache. The power loss then erased the drive cache, so both orders were lost.

**Go deeper: a write with no sync, and the weaker rule on a Mac**

Suppose the store calls `os.write` for `order:1041` and replies OK with no sync at all. A `kill -9` of the store does not lose the order. The page cache belongs to the kernel, and the kernel did not crash. A kernel panic or a power failure can lose it. Whether it does depends on whether the kernel had already written that page back.

More examples: an out-of-memory kill is a process crash. A failed power supply is a power loss. The OS crash row of the table is the general model. Apple documents a weaker rule for a Mac. The sync part below quotes its `fsync(2)` page. So the lab store does not promise the OS crash case for plain fsync on a Mac.

The running case, as times. They are an example built from the M2 cost of `os.fsync`, about 0.1 ms:

1. **t = 0.00 ms**  `put order:1041`: write to the page cache, then fsync to the drive cache.
2. **t = 0.11 ms**  OK sent for `order:1041`, and `put order:1042` starts the same way.
3. **t = 0.22 ms**  OK sent for `order:1042`.
4. **t = 1.22 ms**  The power fails. The drive cache is volatile and is erased.
5. **restart**  The log on flash ends before `order:1041`, so both orders are gone.

The earlier course, "Performance, concurrency and the machine", measured what each step down costs on the author's Apple M2, as medians per run. A page-cache read took 1.5 µs. A read from the SSD took 88.7 to 89.8 µs, and a page there is 16 KiB. After a 4 KiB write, `os.fsync` took 95 to 110 µs and `fcntl(F_FULLFSYNC)` took 2.85 to 2.88 ms. That course's Phase 1 also taught that latency is a distribution, that a closed-loop load generator hides stalls, and that you write a prediction before each run. This course's research measured the same sync calls on a second Mac, an Apple M4 Pro, and keeps each machine's numbers separate.

Course 5, "Distributed systems and verification", covers replicas in its Phase 3. That phase says what a replica has when the leader acknowledges a write. Every promise in this lesson is about one machine. Phase 2 of this course covers the structures built on the log, such as B-trees and LSM trees.

## What must be durable before the store replies OK?

One transaction changes many pages, and a crash in the middle would leave some new and some old. A *write-ahead log*, WAL for short, is a file the database only appends to, one record per change. It turns every change into one append, so a commit needs one small write and one sync.

**Predict: in PostgreSQL a transaction updates one row and commits. When the client gets its reply, which bytes must be on stable media: the changed table page, the log record, or both?**

Only the log record, because recovery can apply the change again from the log. Most people answer both, because a later read returns the table page.

Two rules make that safe:

1. The **WAL rule**: the log record of a change reaches stable media before the changed page may replace the old page on disk.
2. The **commit rule**: a transaction is complete only when its *commit record*, and every log record before it, is on stable media. So the database forces the log up to that record at commit.

If a crash comes before the page is written, recovery reads the log and applies the change again. That replay is called *redo*.

1. **1 change the page**the data page is dirty, in memory
2. **2 append a WAL record**into the WAL buffer, in memory
3. **3 write and sync the WAL**the log reaches stable media
4. **4 reply COMMIT**the acknowledgment
5. **5 write the data page**at any time, even before step 3

A crash after step 4 is repaired by redo. A crash before step 3 sent no reply, so recovery treats the transaction as not committed.

A *log sequence number*, LSN for short, is a byte offset into the WAL, so two LSNs give the WAL bytes between them. In PostgreSQL 18 the durability point is `XLogFlush`, which flushes the WAL up to the commit record's LSN.

The failure is a setting that replies before the log flush. MariaDB's `innodb_flush_log_at_trx_commit=0` flushes the log about once a second, and a Galera cluster with it lost nine acknowledged values in a one-minute test. MariaDB's own Galera page recommended that setting at the time. NATS JetStream calls fsync every two minutes by default, and a simulated power failure lost 131,418 of 930,005 messages. Recovery replayed both logs correctly. Only the part that never reached the disk was lost.

**Remember:** At commit only the log must be durable, because recovery replays it.

**Trap:** A reply before the log flush stays consistent after a crash and still loses commits.

**Try:** Run `uv run python phase01_durability/crash_matrix.py --list`, and find crash points 3 to 7.

**Evidence**

The two rules: ARIES, Mohan and others, ACM TODS 1992, section 1.1, journal pages 97 and 98. The PostgreSQL order: `RecordTransactionCommit` and `CommitTransaction` in `xact.c` at tag REL_18_0. LSN as a byte offset: PostgreSQL 18 docs, section 28.6. Galera: Jepsen "MariaDB Galera Cluster 12.1.2", Kyle Kingsbury, 2026-03-16, section 3.1. The report's second loss, in its section 3.2, happened with the setting at 1 and has no root cause, so this lesson does not use it. MariaDB later changed its Galera page to recommend the default of 1, seen in archived copies dated 2026-03-08 and 2026-06-11. The current page says: "For maximum durability, the default value of 1 is recommended." The four values of `innodb_flush_log_at_trx_commit`: the MariaDB InnoDB system variables page, read by the study note on 2026-10-18. That the change followed the report is inferred from the timing only. NATS: Jepsen "NATS 2.12.1", 2025-12-08, section 3.4.

**Go deeper: STEAL and NO-FORCE, asynchronous commit, the LSN in pg_waldump, PostgreSQL's commit order, MariaDB's values, and the lab's log entry**

#### Who writes the data page, and when

Step 5 may even come before step 3, because the log record of every change on disk is on disk first. Step 5 has no fixed time. In PostgreSQL the *checkpointer*, the process that runs checkpoints, writes dirty pages. So does the bgwriter, a background process that writes pages likely to be evicted soon. A backend, the server process of one client connection, writes a dirty page itself when it must evict it. So a page with an uncommitted change can be on disk. These are the source pages: Rogov, "PostgreSQL 14 Internals", section 10.5, page 176.

The CMU 15-445 Fall 2025 notes for Lecture 21 name the two policies. STEAL lets the database write uncommitted changes to disk before the transaction completes. NO-FORCE means changes are not required to be on disk at commit. The WAL rule is what makes STEAL safe. Phase 2 shows the line in the buffer manager that enforces it.

#### What PostgreSQL waits for

The parameter `synchronous_commit` has the default `on` in PostgreSQL 14 and 18. With it, a commit waits for the local WAL flush. With `off`, the commit replies at once and the WAL writer flushes later. The docs give the maximum delay as three times `wal_writer_delay`. The default `wal_writer_delay` is 200 ms, so the window is 3 × 200 ms = 600 ms. A crash in that window can lose recent commits. The database stays consistent, as if those transactions had been aborted. The sources are the PostgreSQL 18 docs, sections 19.5 and 28.4. This course's research read the 200 ms default on a fresh PostgreSQL 14.24 cluster.

#### The LSN, seen in the WAL

PostgreSQL prints an LSN as two hexadecimal numbers with a slash, such as `0/3DF708D8`. Three functions show the current positions. `pg_current_wal_insert_lsn()` gives the insert location, `pg_current_wal_lsn()` the write location, and `pg_current_wal_flush_lsn()` the flush location, per the PostgreSQL 18 docs, section 9.28.

Rogov ran one `UPDATE` and `COMMIT` on PostgreSQL 14.7. The insert LSN moved from `0/3DF708D8` to `0/3DF70948`, which is 112 bytes. `pg_waldump`, the tool that prints WAL records, showed two records in that range, here shortened to the fields this lesson uses. The source is Rogov, section 10.2, pages 168 and 169.

```
rmgr: Heap len (rec/tot): 69/ 69, tx: 886, lsn: 0/3DF708D8, prev 0/3DF708B0, desc: HOT_UPDATE ...
rmgr: Transaction len (rec/tot): 34/ 34, tx: 886, lsn: 0/3DF70920, prev 0/3DF708D8, desc: COMMIT ...
```

Each record names its resource manager, the code that replays it, and its length and transaction. Each record's `prev` field holds the LSN of the record before it, so the WAL is a chain. The arithmetic of the two records:

```
start of second − start of first = 0x3DF70920 − 0x3DF708D8 = 0x48 = 72 bytes
second record ends 0x28 = 40 bytes later
69-byte record takes 72, 34-byte record takes 40, and 72 + 40 = 112
```

So each record is padded to a multiple of 8 bytes. That rule is inferred from this arithmetic, and not checked in the source code.

#### The commit inside PostgreSQL 18

Only after `XLogFlush` does the server make the rows visible and reply. `pg_xact` is the set of files that holds each transaction's outcome, and Phase 3 shows how readers use it. The order, from `RecordTransactionCommit` and `CommitTransaction` in `xact.c` at tag REL_18_0:

| Step | Function | What it does | Line |
|---|---|---|---|
| 1 | `XactLogCommitRecord` | commit record into the WAL buffers | 1442 |
| 2 | `XLogFlush` | WAL flushed up to that record. The durability point | 1502 |
| 3 | `TransactionIdCommitTree` | "committed" written in `pg_xact` | 1508 |
| 4 | `SyncRepWaitForLSN` | wait for a standby, if one is configured. Course 5 | 1557 |
| 5 | `ProcArrayEndTransaction` | other sessions now see the rows | 2389 |
| 6 | reply to the client | the acknowledgment |  |

With `synchronous_commit = off`, step 2 becomes `XLogSetAsyncXactLSN` at line 1523, and the WAL writer flushes later. Step 5 still runs at once. Step 4 waits only when a standby, a server that replays this server's WAL, must confirm the commit.

Right before step 1, the backend sets the flag `DELAY_CHKPT_START`, and it clears the flag after step 3. A checkpoint that starts in that window waits. Otherwise it could set its recovery start point, the REDO point of the checkpoint parts below, between the commit record and the `pg_xact` update. A crash a little later would then lose the commit. The source is the comment before line 1442.

`synchronous_commit = off` has a consequence that its docs entry does not state. Step 5 runs before the WAL flush, so other sessions can read the new rows before they are durable. A crash in the next 600 ms can then remove rows that another session already read. That order is inferred from the code, and not run. The docs give the rule that follows. Asynchronous commit "should not be used if the client will take external actions" that rely on the commit, per the PostgreSQL 18 docs, section 28.4. A webhook or a queue message sent after such a read is that kind of external action.

#### What MariaDB's setting 0 does

In the Galera test, Jepsen crashed the database processes of every node at about the same time, which is not a power loss. With the setting at 1 the loss became much rarer. `innodb_flush_log_at_trx_commit` controls the same moment in InnoDB. The MariaDB InnoDB system variables page describes four values, 0 to 3. With 1, the default, the log is written and flushed at each commit. With 2, it is written at each commit and flushed on a timer. With 0, nothing happens at commit, and the log is written and flushed about once a second. With 3, the log is flushed at both the prepare step and the commit. The page warns that with 0 a server crash can erase the last second of transactions. So with 0 the reply comes before the log is durable, which breaks the commit rule. A crash of the server process alone is enough, because the log is not yet in the page cache. That last point is inferred from the definition of value 0.

#### When the log is the data: the lab store

The store of this lab has no separate data file. The log is the data. This is the Bitcask design of Sheehy and Smith at Basho Technologies, a company paper, not peer reviewed. Bitcask appends every put to a data file and keeps an in-memory index called the *keydir*. The keydir maps each key to the file, offset and size of its newest entry. A delete is a put of a special tombstone value. The paper says recovery needs no replay, because the data files are the log. But the keydir still has to be rebuilt by reading the log after a restart, which the checkpoint parts below cover.

The lab differs from the paper in two places, on purpose. It stores a 64-bit sequence number in place of the paper's 32-bit timestamp, so recovery can refuse an entry out of order. The paper also does not say how to handle a half-written last entry, and the lab defines that rule in the torn-write part. The paper does not name its CRC algorithm. The lab uses `zlib.crc32`, the IEEE CRC-32.

Here is the store's `put`, from `kvlog.py:409`. The comments are changed, and the size checks and the error handler around the append are removed. The order of steps is unchanged:

```
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
```

Each `self.hook(...)` line is a crash point, and the crash matrix of the last part crashes the store at every one of them. The index is updated after the sync, not before. So a reader never sees a value that a crash can still take back.

## How far does one sync call move the bytes?

The commit rule says to force the log to stable media. *fsync* is the system call that asks the kernel to write a file's dirty pages to the device. It either stops at the drive's cache, or it also asks the drive to flush that cache.

**Predict: the running case called os.fsync after each put, on a Mac. Does that survive a power loss? Now move the same code to a Linux server with ext4. Does it survive there?**

On the Mac, no. On Linux with ext4, yes, if two conditions hold. Most people give the same answer twice, because the code and the call name are the same.

| Call | How far it moves the bytes | Survives a power loss |
|---|---|---|
| macOS `os.fsync` | to the drive cache, then it returns | no |
| macOS `fcntl(fd, F_FULLFSYNC)` | to the drive, then asks the drive to flush | yes, if the drive honours the flush |
| Linux `os.fsync` on ext4 | the file system sends the drive's flush command | yes, with barriers on and a drive that honours the flush |

The mechanism differs by platform:

1. Apple's `fsync(2)` page says the drive may keep the data in its cache a long time. So after a power loss or an OS crash, some or none of it may be written.
2. `F_FULLFSYNC`, a command of `fcntl(2)`, does what fsync does and then asks the drive to flush to permanent storage.
3. The name does not tell you the call. CPython's `os.fsync` is plain `fsync()`, while Go's `os.File.Sync` is `F_FULLFSYNC` on macOS.
4. Linux has no `F_FULLFSYNC`, because the file system sends the flush itself when *write barriers* are on.
  **95 to 110 µs**M2, `os.fsync`, stops at the drive cache **2.85 to 2.88 ms**M2, `F_FULLFSYNC`, flushes the drive **26 to 30 times**the price of the durable call

These are medians per run of one 4 KiB write and a sync, from the earlier course.

Even `F_FULLFSYNC` only asks the drive to flush. A test cut the power to 15 SSDs while flushes were issued, and 13 of them failed in some way. So only a power-cut test of your own device shows what its flush does.

**LiveJournal** lost power to every machine in its data center, as its post-mortem of January 2005 reports. Another customer there had pressed the emergency power-off button by accident. After the restart, the team restored a couple of database machines from backup, because their data was damaged. Their disk controller cards had write caches with battery backup. But the drives behind those cards still had their own drive caches on. The post links the damage to those drive caches and calls them a mistake. The team had also not turned on the option to sync MySQL's binary log, a second log, to disk. So the restored clusters lost a few transactions from just before the power loss. The team then planned to turn off the drive caches. It also planned to cut power during heavy writes on all its hardware, and then check the disks.

**Evidence**

Apple `fsync(2)` and `fcntl(2)` man pages in the xnu source at tag `xnu-12377.121.6`, and in the macOS 26.5 SDK. The `fcntl.2` lines are 207 to 245. The page also warns: "This is not a theoretical edge case." CPython and Go call sites: verified from the source at the tags in the table below by this course's research. M2 costs: the earlier course, elite-performance section 5.6, 2026-09-25. SSD power cuts: Zheng, Qin, Tucek and Lillibridge, USENIX FAST 2013, abstract and section 1. PostgreSQL on the M4 Pro: `pg_test_fsync -s 3` from PostgreSQL 14.24, run by this course's research on 2026-10-17. Linux barriers: PostgreSQL 18 docs, section 28.1. LiveJournal: Brad Fitzpatrick, "Power-loss post-mortem", LiveJournal lj_dev, 2005-01-20. The post gives no date for the power cut itself, so the lesson gives the month of the post.

**Go deeper: each runtime's call, the lab's sync, the M4 Pro numbers, PostgreSQL's sync methods, drives that report early, and how to check a Linux server**

#### What each runtime calls

| Runtime, version | Call | On macOS | Source |
|---|---|---|---|
| CPython 3.14.8, `os.fsync` | `fsync()` | stops at the drive cache | `Modules/posixmodule.c` line 3993, `os_fsync_impl` |
| CPython, `fcntl.fcntl(fd, fcntl.F_FULLFSYNC)` | `F_FULLFSYNC` | flushes the drive | `Modules/fcntlmodule.c` lines 639 to 640 export the constant |
| Go 1.24.0 and 1.27.2, `os.File.Sync` | `F_FULLFSYNC` | flushes the drive | `internal/poll/fd_fsync_darwin.go` line 22 |
| Go, `syscall.Fsync` | `fsync()` | stops at the drive cache | `syscall/zsyscall_darwin_arm64.go` lines 710 to 716 |

If `F_FULLFSYNC` returns `ENOTSUP`, for example on an SMB mount, Go falls back to plain fsync. The history of both Go changes, and an open CPython request to change `os.fsync`, are in the sources list. So a Python service on a Mac must call `F_FULLFSYNC` itself. A Go service there already asks for the flush.

Apple's `fcntl(2)` page names APFS among the file systems that support `F_FULLFSYNC`. The same page describes `F_BARRIERFSYNC`, which sends a barrier instead of a flush. A barrier keeps the order of writes, but it does not make them durable. The Linux write barriers above are a different thing with the same word.

#### Why the lab uses two calls

`shared/durable.py` makes every durable sync of the course. On macOS it calls `fcntl(fd, F_FULLFSYNC)`. On Linux it calls `os.fsync`, because Linux has no `F_FULLFSYNC` and the file system sends the drive's flush command itself. The PostgreSQL 18 docs, section 28.1, name ZFS and ext4 as examples of file systems that can send it. The same section says to turn write barriers off only behind a controller with a working battery-backed cache. XFS is not named there, and this course did not check it. The decision, from `durable.py:92`:

```
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

#### The cost on two Macs

| Machine and call | Median per run | Conditions |
|---|---|---|
| M2, `os.fsync` | 95 to 110 µs | 4 KiB write, earlier course |
| M2, `F_FULLFSYNC` | 2.85 to 2.88 ms | ratio 26 to 30 times |
| M4 Pro, `os.fsync` | 25.1 and 31.2 µs | Python 3.9.6, 8 KB pwrite, macOS 26.6 |
| M4 Pro, `F_FULLFSYNC` | about 4.0 ms | 4,001 / 31.2 = 128 times, 4,012 / 25.1 = 160 times |

The research also measured Go's `os.File.Sync` on the M4 Pro at 3,981 to 4,078 µs per operation. That matches `F_FULLFSYNC`, as the Go source predicts. Keep each machine's numbers separate, because the two runs used different write sizes and Python versions.

#### PostgreSQL on a Mac

PostgreSQL chooses its WAL sync call with `wal_sync_method`. The default is the first supported method in a fixed list, except that Linux and FreeBSD use `fdatasync`. On macOS that rule picks `open_datasync`. This is from the PostgreSQL 14 and 18 docs, sections 20.5 and 19.5, and from `xlogdefs.h` at REL_14_0. A fresh PostgreSQL 14.24 cluster on the M4 Pro showed `open_datasync` with source `default`. That was a Homebrew x86_64 build under Rosetta. The PostgreSQL docs, section 28.1, say that on macOS you set `fsync_writethrough` to prevent write caching. `pg_test_fsync -s 3` measured each method on the same Mac, one 8 kB write per operation:

| `wal_sync_method` | ops/sec | µs per op | flushes the drive cache |
|---|---|---|---|
| `open_datasync`, the macOS default | 45,480 | 22 | no |
| `fdatasync` | 42,027 | 24 | no |
| `fsync` | 40,138 | 25 | no |
| `fsync_writethrough` | 250 | 3,994 | yes, inferred |
| `open_sync` | 42,435 | 24 | no |
| write, no sync | 333,548 | 3 | no |

The "yes, inferred" comes from `HAVE_FSYNC_WRITETHROUGH` in PostgreSQL's `darwin.h` and from the 3,994 µs, which matches `F_FULLFSYNC`. The PostgreSQL 18 default on macOS is inferred to be `open_datasync` too, from the same source logic at REL_18_0, and not run. The one method that flushes is 45,480 / 250 = 182 times slower than the default. So a default PostgreSQL 14 on your Mac commits in about 22 µs, and those commits do not survive a power cut. That is fine for a development laptop, and it is the wrong model of a production server.

#### Drives that report early

The PostgreSQL 18 docs, section 28.1, warn about consumer drives. Their write-back caches often do not survive a power failure, and many SSDs do not honor cache flush commands by default. The power-cut test above cut the power to 15 SSDs of 10 models from 5 vendors, with flushes issued, and 13 of the 15 showed failures. Only two SSDs of one model, and one enterprise hard disk, behaved as the flush promised. The drives date from about 2012, and modern NVMe drives were not tested.

#### Checking the flush path on a Linux server

The Linux block layer marks a cache flush as `REQ_PREFLUSH`. It marks a write that must reach stable media as `REQ_FUA`, forced unit access. For a device that reports no volatile write cache, the block layer completes empty `REQ_PREFLUSH` requests itself, before the driver. This is from the kernel document `block/writeback_cache_control`. So fsync is cheap on such a device, and it is safe only if the device really keeps its cache through a power loss.

Enterprise SSDs with power-loss protection, PLP for short, are sold as keeping their cache through a power loss. That claim, and that PLP drives report no volatile cache to Linux, were not checked. A RAID controller with a battery-backup unit, BBU, keeps its cache in a power loss too. These are the checks, all for Linux:

| What you check | Command | What it tells you | Source |
|---|---|---|---|
| the kernel's view of the drive cache | `cat /sys/block/nvme0n1/queue/write_cache` | `write back` or `write through`. Writing to the file changes only the kernel's view, not the device | kernel ABI, `sysfs-block` |
| a SATA drive's cache | `hdparm -I /dev/sda` | a `*` next to "Write cache" means it is on | PG 18 docs, 28.1 |
| a SCSI or SAS drive's cache | `sdparm --get=WCE /dev/sdb` | whether the write cache is enabled | PG 18 docs, 28.1 |
| the real flush cost | `pg_test_fsync -f /path/on/the/wal/disk/test.out` | the time per sync method, on the WAL file system | PG 18 docs, `pg_test_fsync` |
| whether flushed data survives | `diskchecker.pl`, with a real power cut | the docs name it as a test of reliable I/O | PG 18 docs, 28.1 |

The kernel document warns about one change. Setting `write_cache` from `write back` to `write through` "will also eliminate cache flushes issued by the kernel." So a drive with a volatile cache then gets no flush commands, and fsync returns while the data is still in that cache.

#### Network file systems, direct I/O and cloud volumes

- **NFS.** The PostgreSQL 18 docs, section 18.2.2.1, require the `hard` mount option. They also recommend the `sync` export option on the server. Without it, an fsync on the client "is not actually guaranteed to reach permanent storage on the server". The docs compare that to running with `fsync` off.
- **`O_DIRECT`.** It moves data straight between user memory and the device, past the page cache. The Linux `open(2)` man page says it "does not give the guarantees of the O_SYNC flag". So direct I/O alone is not a durable write, and a store that uses it still needs a sync. PostgreSQL 16 stopped using direct I/O for the `open_sync` and `open_datasync` methods with `wal_level=minimal`, the only case that used it. It is now behind the developer setting `debug_io_direct=wal`, per the 16.0 release notes and `get_sync_bit` in `xlog.c` at REL_14_0. PostgreSQL 18 added asynchronous I/O, set by `io_method`. The 18.0 release notes list reads only, such as sequential scans and vacuum. So it does not change the commit path, which is inferred from that list.
- **Cloud block volumes.** What a flush on a cloud volume promises was not checked. No first-party statement was found for Amazon EBS or Google Persistent Disk. Treat it as a question for your provider, and test it.

## What must the store do when a sync fails?

On Linux the right call can fail, and a retry can then report success. PostgreSQL lost data this way, in a bug known as fsyncgate:

1. **1 write B**  B is in the page cache, and its page is dirty.
2. **2 fsync**  The device fails the write, and fsync returns `EIO`, the error code for a failed disk read or write. The kernel marks the page clean, so B is not on disk.
3. **3 fsync again**  Nothing is dirty, so the call returns 0, which reads as success.
4. **4 reply OK**  The store acknowledges B, which the disk does not have.
5. **5 read B**  Reads still return B from the page cache, until the page is evicted.
6. **6 reboot**  B is gone.

After a failed fsync, ext4, XFS and Btrfs all mark the failed pages clean, so a retry does not write them again. So the store cannot know which writes reached the disk. The only safe action is to stop: never retry, never acknowledge, and let recovery replay the log on restart. PostgreSQL now raises a PANIC on a failed data file flush. PANIC is its top error level, which stops all server processes so recovery runs on restart. Its setting `data_sync_retry` keeps the old retry and is `off` by default.

Retry after `EIO`. In the lab demo three puts are acknowledged, and after a power loss only `order:1041` is left. Two acknowledged puts are lost.

Stop after `EIO`. Only `order:1041` is acknowledged, and the next two puts get `StoreFailed`. Nothing acknowledged is lost.

fsync on a file also does not make the file's name durable. A name lives in its directory, which is a file too. In a crash test of 11 applications, three of the five problems that developers acted on were a missing directory fsync. So the lab store syncs its directory after it creates the log and after each checkpoint rename.

**Evidence**

The bug report: Craig Ringer, pgsql-hackers, sent 2018-03-28. File system behaviour: Rebello and others, USENIX ATC 2020, Table 1 and section 3.3, on Linux 5.2.11. The fix: PostgreSQL 11.2, 10.7, 9.6.12, 9.5.16 and 9.4.21, released 2019-02-14, from the five release notes. `data_sync_retry`: the docs of versions 14 and 18 describe it the same way. A fresh 14.24 cluster on the M4 Pro showed `data_sync_retry = off`, source `default`. Directory fsync: the ALICE study, Pillai and others, OSDI 2014, page 12.

**Go deeper: what each file system does after a failed fsync, the Linux 4.13 change, the lab's sync code and its demo, and the gap a restart leaves**

#### The rest of the measurement

ext4 and XFS keep the new data in the page cache after a failed fsync, so reads return it while the disk lacks it. Btrfs goes back to the old data. ext4 in `data=journal` mode reports the error one fsync late. In the same measurement, Redis 5.0.7 did not check the return code of fsync at all.

The bug report found that the PostgreSQL retry succeeded because the first failed fsync had cleared the error flag. The data was gone, and the second fsync reported success.

#### The fix, and the kernel change

PostgreSQL fixed this in five releases on the same day: 11.2, 10.7, 9.6.12, 9.5.16 and 9.4.21. After the PANIC, crash recovery replays the WAL and rewrites the data pages.

Linux also changed in version 4.13. Since then, a write-back error is reported to every file descriptor that might have written the data, per the Linux `fsync(2)` man page. The file system tests ran on Linux 5.2.11, after this change, and still found the clean pages. So the PANIC rule still applies.

#### The lab store's sync

The lab store follows the PANIC rule. Here is the wrong way, kept in the code only for its self-test, and the right way, from `kvlog.py:460`:

```
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
```

#### The gap a restart leaves

Stopping still leaves one gap. A store that must survive it needs to rewrite or verify the log tail it cannot prove durable, and the lab store does not do that. In the RIGHT case, a restart without a reboot reads the log through the page cache. The page cache still shows `order:1042`, which the disk does not have, and the demo prints that line too. The lab's recovery trusts what the operating system returns, so it would accept `order:1042` until the page is evicted. This follows from the ext4 and XFS rows above. The same measurement found that PostgreSQL lost data under the ext4 `data=journal` behaviour, because that error came one fsync late.

#### The directory sync

The crash test of 11 applications ran on Linux file systems. The store syncs its directory after it creates the log, at `kvlog.py:348`, and after each checkpoint rename, in `checkpoint()`. The crash matrix of the last part shows what goes wrong without the first of those syncs.

## How does group commit win back the throughput?

Each put now waits for one full sync of about 2.85 ms on the M2. The syncs run one after another, so the store commits at most 1 / 2.85 ms, about 351 puts per second. Adding writers does not help, because they wait in line for the device.

*Group commit* means that one sync covers the log entries of many commits. Each commit still returns only after a sync that covers its own entry. While one sync runs, new puts append and wait. Then one waiting writer becomes the leader and syncs everything appended so far, and the others return with it.

#### Group commit with 3 writers, one sync of 2.85 ms
- device:  [sync 1] [sync 2] [sync 3]
- writer A:  [put 1, OK at the end] [put 2 waits] [put 2 OK]
- writer B:  [appends, waits] [OK]
- writer C:  [appends, waits] [OK]

- Sync 1 covers writer A's first put. B and C append during sync 1 and wait.

- Sync 2 covers both B and C. A's second put appends during sync 2.

- Sync 3 covers A's second put, and the syncs end at 2.85, 5.70 and 8.55 ms. Four puts took three syncs instead of four.

- Times are an example built from the M2 median of 2.85 ms, not measured.

With 16 writers, one sync can cover at most 16 puts. So the upper limit becomes 16 × 351 = 5,616 puts per second. The price is latency. A put that arrives right after a sync started waits for that sync and then for its own, so it can take up to 2 × 2.85 = 5.7 ms.

#### Upper limits from one sync time Sync time, µs  (slider 20 to 5000, default 2850)  Writers  (slider 1 to 64, default 16)  One sync per put (computed), group commit (computed), longest wait (computed)

These are limits from arithmetic. Python's cost per put lowers both, and E10 measures the real rates.

PostgreSQL forms its groups inside `XLogFlush`: a committer returns without a sync if another backend's flush covered its commit record. The setting `commit_delay`, 0 µs by default, makes the leader sleep first so more commits join. On a disk limited to 1,000 write IOPS, a delay of 1,000 µs gave 1.74 times the throughput.

The other way to get speed is to reply before the sync, and every such setting has a loss window. NATS replies before its two-minute fsync, as the commit part showed. `fsync=off` is worse, because it can corrupt the database beyond repair.

**Remember:** Only `F_FULLFSYNC` flushes a Mac drive, and group commit shares that slow sync.

**Trap:** Calling `os.fsync` durable on a Mac makes every benchmark fast and loses writes.

**Try:** Run `uv run python shared/durable.py --measure 200`, and predict the ratio of `full` to `fsync` first.

**Evidence**

PostgreSQL's group forming: `LWLockAcquireOrWait` at `xlog.c` line 2855, REL_18_0, and its comment, which says this "helps to maintain a good rate of group committing". `commit_delay` and `commit_siblings`: the docs of versions 14 and 18. The 1.74 times: Laurenz Albe, CYBERTEC, January 2025, PostgreSQL 17 on an ASUS ZenBook notebook with NVMe and Fedora 40, the disk limited to 1,000 write IOPS on purpose, `pgbench -b simple-update -c 10` for 1,200 seconds. The flush time of about 2,000 µs: Albe's reply on the same post, 2025-06-28. The loss windows: PostgreSQL 18 docs, section 19.5.

**Go deeper: the lab's leader code, PostgreSQL's commit_delay, older measurements, every loss window, and per-transaction durability**

#### The lab's implementation

In `kvlog.py`, the flag `group_commit=True` switches `put` from `_sync_log_locked` to `_wait_durable`. The core of `_wait_durable`, from `kvlog.py:475`, without its error handling and with the comments changed:

```
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

The leader reads `target` before it syncs. A put that appends after that line is not counted as covered, even if the sync happens to include its bytes. That rule keeps the claim exact: a put returns only when a sync that started after its append has returned.

One assumption is not checked. The design needs `fcntl.fcntl` and `os.fsync` to release Python's global interpreter lock while the device works. If they did not, no other thread could append during a sync, and every batch would hold one put.

#### PostgreSQL's version, in detail

A committer tries to take `WALWriteLock` with `LWLockAcquireOrWait`. If another backend holds the lock, this one waits until the lock is free. Then it does not take the lock at once. It first checks whether the holder already flushed past its own commit record. If so, it returns without a sync. That is the lab's `_wait_durable`, where a follower returns when `synced_to` covers its entry.

Two settings make groups larger. `commit_delay`, default 0 µs, makes the leader sleep before it flushes, if at least `commit_siblings` other transactions are active. `commit_siblings` defaults to 5. Since PostgreSQL 9.3, only the leader waits for the delay, and the others wait for its flush. The PostgreSQL 18 docs, section 28.5, add two points. At higher client counts a "gangway effect" forms groups even with a delay of 0, so the setting helps less there. And a good first value is half the time that `pg_test_fsync` reports for one flush after an 8 kB write. The lab's `--group-delay-us` flag is the same idea.
- commit_delay 0 µs: 1,576 TPS, 1,000 IOPS
- 500 µs: 2,183 TPS, 1,000 IOPS
- 1,000 µs: 2,738 TPS, 600 IOPS
- 2,000 µs: 2,051 TPS, 430 IOPS

The bars run from 1,576 to 2,738 TPS, which is 1.74 times. Past 1,000 µs the wait costs more than it saves. The docs' rule matches this test once the flush time is measured. Albe ran `pg_test_fsync` on the throttled disk, and `fdatasync` took about 2,000 µs per operation. Half of 2,000 µs is 1,000 µs, his best value. So start from half the measured flush time, and then measure the throughput.

Vadim Tkachenko of Percona measured the InnoDB group commit fix in July 2011, on 8 spinning disks in RAID 10. Without a controller cache, the fix raised throughput to 1,669.11 at 256 threads, against at most 57.62 before, about 29 times. With a battery-backed cache, one thread already reached 352.83 without the fix. So group commit matters most when each sync is slow. The article does not state the unit, which is probably transactions per second.

#### Every loss window

| System and setting | When it replies | What a crash can lose | Source |
|---|---|---|---|
| PostgreSQL `synchronous_commit=off` | before the WAL flush | up to 3 × `wal_writer_delay`, 600 ms at the default | PG 18 docs, 19.5 |
| PostgreSQL `fsync=off` | never syncs | not a window: "unrecoverable data corruption in the event of a power failure or system crash" | PG 18 docs, 19.5 |
| MySQL `sync_binlog=0` | without a sync of the binary log | committed transactions missing from the binary log, after a power failure or OS crash | MySQL 8.4 manual |
| MariaDB `innodb_flush_log_at_trx_commit=0` | before the log write | about the last second | MariaDB docs |
| MariaDB `innodb_flush_log_at_trx_commit=2` | after the log write, before the flush | about the last second, on an OS crash or power loss | MariaDB docs |
| Redis `appendfsync everysec`, the default | before the fsync | about 1 second, per the docs | Redis persistence docs |
| NATS JetStream, the default `sync_interval` | before the fsync | up to 2 minutes | Jepsen NATS 2.12.1, 3.4 |

The Redis row has one more detail. The docs say one second. The source in `src/aof.c` on the unstable branch can postpone a write for up to two seconds, while a background fsync is still running. So the window can be longer than one second. That is inferred from the code and not tested.

Kaarel Moppel of CYBERTEC measured, in 2016, 4,256 TPS with `synchronous_commit=on` and 6,211 TPS with `off`, which is 1.46 times. The setup was two AWS i2.xlarge instances with asynchronous streaming replication, and `pgbench` with 8 clients for 10 minutes. With asynchronous replication the primary does not wait for the standby, so the setting changed only the local WAL wait. That last point is inferred from the PostgreSQL docs on `synchronous_commit`. The PostgreSQL version is not named. Rogov ran a smaller test on PostgreSQL 14.7, with `pgbench`, 1 client and 30 seconds. He measured 670.8 TPS with `synchronous_commit` on and 2,060.4 TPS with it off, which is 3.07 times, in section 11.1, pages 184 and 185. His hardware is not stated in those pages. These ratios and the group commit ratio of 1.74 come from different machines and tests, so they are not compared.

#### A finer choice than one global switch

- **Per transaction.** `synchronous_commit` can be set for one transaction. "The mode used for any one transaction depends on the value of synchronous_commit when transaction commit begins," per the PostgreSQL 18 docs, section 28.4. So a service can commit a payment with `on` and a page-view log with `off`, in the same database.
- **`fsync=off` is a different risk.** Asynchronous commit loses at most the last 600 ms, and the database stays consistent. `fsync=off` can corrupt the database beyond repair. Rogov makes the same point on page 187. A CI database often runs with `fsync=off`, so its crash behaviour says nothing about production.

MySQL needs two settings for a durable commit, because the binary log is a second log next to the InnoDB log. `sync_binlog` defaults to 1. For the greatest durability with InnoDB, the MySQL 8.4 manual lists `sync_binlog=1` together with `innodb_flush_log_at_trx_commit=1`, on its page "Binary Logging Options and Variables". Replicas read the binary log, which is course 5.

## How does recovery notice a half-written entry?

A sync makes a write durable once it returns, but a power loss can come while the write is still in flight. A *torn write* is a write that only partly reached the disk. The device writes in *sectors*, commonly 512 bytes, so a power loss can leave some sectors of one write new and others not.

The lab's log entry has a 20-byte header, the key and the value. The header holds a CRC-32, a 4-byte value computed from every byte after it. It also holds a sequence number and two lengths. So `put order:1041` with a 1,200-byte value takes 20 + 10 + 1,200 = 1,230 bytes.

**Predict: a power loss tears the second version of order:1041, 1,230 bytes at offsets 1230 to 2460. One 512-byte sector in the middle reads as zeros, and the file length covers the whole entry. If recovery checks only the lengths, what does it return for order:1041?**

It returns the new value, with 512 zero bytes inside it, served as data under the right key. Every length in the header is correct.

#### The torn entry
- header and key: 30 B, 1230 to 1260, intact
- value: 276 B, 1260 to 1536, arrived
- zero sector: 512 B, 1536 to 2048, never written
- value: 412 B, 2048 to 2460, arrived

A torn write has two shapes, and each needs its own check:

| Shape | What the disk holds | What catches it |
|---|---|---|
| short | the file ends inside the entry | a length check |
| hole | the right length, with a sector of wrong bytes inside | only a checksum |

A *checksum* is a short value computed from a block of bytes and stored next to it. A reader computes it again and compares, so a changed byte gives a different value. The parser checks the lengths first, so a damaged length cannot make it read gigabytes, and then the CRC.

**Amazon S3** went down in July 2008, with problems in the messages between its servers. A few of those messages each had one wrong bit, but the servers could still read each one. S3 checked customer data with MD5 checksums. These internal state messages had no such check, so the wrong state went unnoticed and spread through the whole system. Amazon stopped all traffic between S3 servers and cleared the system state. By 2:20 pm PDT, the servers talked to each other again, and request processing began to restart. The fix added checksums to the state messages, and monitoring with an alarm for that state. A flipped bit leaves every length correct, so a length check alone would miss it too.

Recovery stops at the first entry that fails any check, including a sequence number that is not the next one. It treats that point as the end of the log, cuts the file there and syncs the cut. The put in flight was never acknowledged, so dropping it breaks no promise.

The rule fails for a bit flip in the middle of data that was already synced. Recovery stops there and drops every later entry, acknowledged ones too, because the scan cannot tell that damage from a torn tail. So the store's promise says that damage to synced data is not covered.

PostgreSQL also repairs a torn 8 kB data page, which a checksum can only detect. With `full_page_writes = on`, the default, the first change to a page after a checkpoint copies the whole page into the WAL. Replay writes that *full page image* back over a torn page.

**Remember:** A length check catches a short write, and only a checksum catches a hole.

**Trap:** Recovery that checks lengths only serves bytes that no client ever wrote.

**Try:** Run `uv run python phase01_durability/kvlog.py --torn-demo` and match each output number to an offset above.

**Evidence**

Sectors of 512 bytes and PostgreSQL's 8,192-byte writes: PostgreSQL 18 docs, section 28.1. The entry layout follows the Bitcask paper's figure on page 2. `full_page_writes`: the PostgreSQL 14 and 18 docs, `runtime-config-wal`. PostgreSQL 14's final release is on 2026-11-12, per the PostgreSQL versioning page. The offsets of the hole come from `fsim.py`, and the demo output was worked out from them, not run. Amazon S3: Rich Miller, "S3 Downtime: More Missing Bites", Data Center Knowledge, 2008-07-26, which quotes Amazon's postmortem.

**Go deeper: where the hole falls, the parser code, real drives, the LazyFS test, InnoDB and cloud devices, data checksums, and the PostgreSQL WAL record**

#### The entry layout

The header is big-endian, and the CRC covers every byte after itself:

| crc32 | seq | ksz | vsz | key | value |
|---|---|---|---|---|---|
| 4 B | 8 B | 4 B | 4 B | ksz bytes | vsz bytes |

#### Where the hole falls

Reads check the CRC too, so a damaged synced entry is never served as data.

`fsim.py` zeroes the sector that holds the middle byte of the in-flight write:

```
middle byte     1230 + 1230 / 2 = 1845
sector start    1845 // 512 × 512 = 3 × 512 = 1536
sector end      1536 + 512 = 2048
value starts    1230 + 20 header + 10 key = 1260
```

So the 512 zero bytes fall inside the value, and the header is intact. A reader that checks only the lengths sees a valid entry with the right key. A delete is shorter: `delete order:1042` is 20 + 10 = 30 bytes, and a tombstone is marked by `vsz = 0xFFFFFFFF`, with no value.

A short write has the other shape. In the example of the lab's figure, only 700 of the 1,230 bytes arrived, so the file ends at 1930 and a length check catches it.

Real drives produce both shapes. In the power-cut test of 15 SSDs, three SSDs showed shorn writes, in which only part of a 4 KB record reached the disk. Three SSDs showed bit corruption. SQLite's document on atomic commit, section 2, says SQLite has long assumed that a single sector write is not atomic.

Suppose the damage looks random to the CRC. Then the chance that a damaged entry still matches is 1 in 2^32, or 1 in 4,294,967,296. That figure is inferred from the size of the CRC, and not checked against a model of real drive failures.

#### The parser

```
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

E8 runs the hole case twice in memory, with the CRC check off and on. The expected output comes from the offsets above. It was not run:

```
kvlog.py --torn-demo, expected shape. Not run by the author yet
WRONG verify_crc off: get(order:1041) returned 1200 bytes, 512 of them
      zero, served as data. 2 entries replayed
RIGHT verify_crc on:  stopped at offset 1230: checksum mismatch,
      1230 bytes dropped. get(order:1041) returned the earlier value,
      starting 'order:1041:v1:'
```

#### A torn data page in PostgreSQL

The docs allow turning `full_page_writes` off only on a file system that prevents partial page writes, and their example is ZFS. There is direct evidence of what happens when it is off. Ramos and others built LazyFS, a file system that runs as a normal program. It uses FUSE, the interface that lets a user program act as a file system. It has its own page cache, and it can lose or tear writes on command. They tore a PostgreSQL data page write, with the setting off and on, on PostgreSQL 12.11 and 15.2. In both cases the server restarted without an error. With the setting off, the `amcheck` module, which checks the structure of tables and indexes, then reported corruption. The last part uses LazyFS again as a test tool.

#### The same problem in InnoDB and on cloud devices

MySQL's InnoDB writes each page flushed from the buffer pool to a doublewrite buffer first, and only then to its place in the data file. After a crash during a page write, InnoDB "can find a good copy of the page" in that buffer. The MySQL 8.4 manual says it is enabled by default in most cases, and it does not give the exact default per platform. So PostgreSQL copies the page into the WAL, and InnoDB copies it into a second file. Both pay one extra page write.

Some cloud devices remove the problem at the device. AWS documents torn write prevention for EC2, which writes a block all or nothing. AWS says this removes the need for the doublewrite buffer. It states that transactions per second can rise by up to 30 percent, and write latency can fall by up to 50 percent. These are vendor claims. The supported block sizes and volume types were not checked, because that sub-page did not load.

#### Data checksums

Data checksums are a separate feature. They detect a damaged data page when it is read. PostgreSQL 18 turned them on by default in `initdb`, listed under incompatibilities in the 18.0 release notes, with `--no-data-checksums` to turn them off. PostgreSQL 14 has them off by default. PostgreSQL 14 gets its final release in November 2026, per the PostgreSQL versioning page. This section's Evidence box gives the exact day. The release notes also say that `pg_upgrade` needs matching checksum settings in the old and new clusters. So a 14 cluster made with default settings needs a decision before it moves to 18. E11 shows how to check your cluster.

In both versions, only data pages are covered, and internal structures and temporary files are not. Rogov, section 11.2, page 187, names three more limits:

- A page is checked only when it is read, so damage can sit unseen until it reaches every backup.
- A zeroed page counts as valid.
- Only the main fork of each table is covered, not files such as `pg_xact`.

Checksums also cost WAL. With them on, "hint bit updates are always WAL-logged", per the PostgreSQL 18 docs, section 19.5. A hint bit is a cached flag in a row that saves later readers a lookup, and Phase 3 explains it. So the 18 default writes more full page images than the 14 default. That is inferred from the docs line, and its size is not measured here. A checksum failure shows in two places. `pg_stat_database.checksum_failures` counts them, per the PostgreSQL 18 docs, section 27.2. The log shows a warning that starts "page verification failed, calculated checksum", then an error "invalid page in block 0 of relation", in Rogov's example on page 188.

#### The lab entry against a PostgreSQL WAL record

A PostgreSQL WAL record solves the same problems with different fields. Its header is 24 bytes, against the lab's 20, from `xlogrecord.h` at tag REL_18_0, lines 41 to 53:

| The job | Lab entry, `kvlog.py` | PostgreSQL WAL record | Source |
|---|---|---|---|
| length | `ksz` and `vsz`, 4 bytes each | `xl_tot_len`, the length of the whole record | `xlogrecord.h` |
| checksum | `crc32`, IEEE CRC-32 over the bytes after it | `xl_crc`, a CRC-32C on every record | `xlogrecord.h`, PG 18 docs 28.1 |
| order | `seq` must be the next number | `xl_prev` must be the LSN of the record before. Else "record with incorrect prev-link" | `xlogreader.c` REL_18_0 line 1166 |
| end of log | `impossible lengths ksz=0 vsz=0` | "invalid record length at ...: wanted 24, got 0" in 14 and 15. "expected at least 24, got 0" since 16 | Rogov p. 175, `xlogreader.c` at REL_15_0 and REL_16_0 |

The order check matters for one reason the lab does not have. PostgreSQL recycles old WAL files by renaming them, per Rogov, page 178. A recycled file still holds old records with valid CRCs. The reader refuses them by the `xl_prev` check, and by the page address check, "unexpected pageaddr", at line 1331 of `xlogreader.c`. The lab's sequence check does the same job for its own log, which is inferred from the reader code. The wording change of the end-of-log message was found by comparing `xlogreader.c` at REL_15_0 and REL_16_0.

PostgreSQL's redo also stops at the first invalid record and treats it as the end of the WAL. So it has the same blind spot for damage in the middle. That is inferred from the reader logic, and no PostgreSQL text read for this course says it.

## Where does recovery start, and what does a checkpoint bound?

The torn tail is now caught, but recovery found it by reading the whole log, and the store serves no read until recovery ends. *Crash recovery* is the work a store does on restart to build a correct state from disk, and in a WAL store it is mostly replay. A *checkpoint* is a point in the log with a guarantee: every change before it is already saved outside the log. Recovery starts there, so the log written since that point bounds recovery time.

**Predict: a PostgreSQL server crashes with about 1 GB of WAL written since recovery's start point, which the next part defines exactly. Guess how long the redo takes: under a second, about 5 to 10 seconds, or several minutes.**

About 5 to 10 seconds, on one measured machine whose hardware is not named. Many people guess minutes. Treat it as an order of size, because the time depends on the version and on a read-ahead setting.

The lab's checkpoint is one file, `keydir.ckpt`, holding the keydir, the in-memory map from each key to its newest entry, and the log offset it covers. The workload writes 10 operations, with a checkpoint after the fourth:

#### The workload log after 10 operations: 9,900 bytes
- ops 1 to 4: 4,920 B, 4 puts × 1,230, in keydir.ckpt, not read again
- ops 5 to 10: 4,980 B, 2 deletes × 30 + 4 puts × 1,230, replayed on restart

So a restart reads 4,980 of 9,900 bytes, or 50.3%. Without a checkpoint it reads all of them.

**Tarsnap**, a backup service, lost its central server in July 2023, most likely to a hardware fault. After a restart, the server's logs showed a damaged file system. Tarsnap stores its data in Amazon S3 as a log. Each stored object starts with a header that holds the metadata of its log entries. Colin Percival, who runs Tarsnap, chose to build a new server instead of repairing the old one. So the new server first read all the metadata headers from S3. Then it replayed all of those operations locally. The postmortem says that both steps were slower than they could be. The read used only 250 parallel requests to S3, and disk throughput limited the replay. The replay also failed twice, and he fixed the recovery code each time. The service came back about 26 hours after it went down.

A crash can come at any step of writing that file, so `checkpoint()` runs five steps in a fixed order:

1. Sync the log, so the log is durable before the file that depends on it.
2. Write `keydir.ckpt.tmp`, so the good file is never overwritten in place.
3. Sync the tmp file, so its bytes are durable before its name moves.
4. Rename it to `keydir.ckpt`, which replaces the old file in one step.
5. Sync the directory, so the rename is durable.

Skip step 3 or step 5, and a crash leaves a broken or an old checkpoint, which costs only a longer scan. Skip step 1, and the checkpoint can point past the end of the durable log. The store cannot repair that, so recovery refuses to open with `CorruptionError`.

**Evidence**

The steps and offsets come from `checkpoint()` at `kvlog.py:511`, `Store.open` at `kvlog.py:331` and `_recover` at `kvlog.py:356`. The self-test of `kvlog.py` removes step 1 with `sync="none"` and checks that the power image fails to open. The redo time in the predict answer is Christophe Pettus's measurement on PostgreSQL 18.6, in the next part. Tarsnap: Colin Percival, "2023-07-02 -- 2023-07-03 Tarsnap outage post-mortem", tarsnap-announce, 2023-07-26.

**Go deeper: the lab's restart steps, the three passes of ARIES, what a power loss leaves after each checkpoint step, and why recovery must cut the tail**

#### What the lab store does on restart

`Store.open` at `kvlog.py:331`, with `_recover` at `kvlog.py:356`, runs these steps in order:

1. Delete `keydir.ckpt.tmp` if it exists. A crash during a checkpoint left it, and the log has the same data.
2. If `keydir.ckpt` exists and its own CRC is good, load the keydir from it. The file also holds the log offset it covers and the last sequence number.
3. If the checkpoint covers more bytes than the log has, stop with `CorruptionError`. Only a broken WAL rule leads here.
4. Read the log from the covered offset to the end, and apply each entry to the keydir.
5. Stop at the first bad entry. Cut the file there and sync the cut.
6. Start accepting writes.

#### Redo and undo

PostgreSQL states the rule this way. Crash recovery looks at the latest checkpoint record to find the redo point in the WAL, and starts there. Changes made before that point are already on disk. This is the PostgreSQL 18 docs, section 28.5, and the version 14 docs, section 30.5. The ARIES paper, section 6, describes a restart as three passes in order: analysis, redo and undo. Undo removes the changes of transactions that never committed. The lab store has no undo pass. One put is one entry, and it either passes its CRC or it is not there. PostgreSQL has no undo pass either, per Rogov, section 10.4, page 174. An unfinished transaction never gets a commit bit in `pg_xact`, so readers treat its rows as aborted. Phase 3 shows how they do that.

#### A power loss right after each checkpoint step

| Step | Why | A power loss right after it leaves |
|---|---|---|
| 1 sync the log | the WAL rule | the old checkpoint or none. Full scan |
| 2 write `keydir.ckpt.tmp` | never overwrite the good file in place | the same. The tmp file is not durable |
| 3 sync the tmp file | its bytes are durable before its name moves | the same. Its name is not durable yet |
| 4 rename tmp to ckpt | one step replaces it | the same, or new: the rename is not durable yet |
| 5 sync the directory | the rename is durable | the new checkpoint |

In every row the log holds all acknowledged puts, so no data is lost. Skip step 3, and the rename can reach the disk before the file's bytes. Then the checkpoint is short or zero, its CRC fails, and recovery scans from offset 0. Skip step 5, and a power loss can bring back the old checkpoint. Both cost time, not data, because the log is the source of truth.

The checkpoint always uses the full sync, even when the store commits with `--sync none`. Checkpoints are rare, one per many puts, so their cost is small. A wrong checkpoint is corruption, while a slow one is only slow.

#### Why recovery must cut the bad tail

Suppose recovery stops at a torn entry but does not cut it. The next put lands after the garbage. The next recovery stops at the same garbage, and drops the new put, which was acknowledged. The self-test of `kvlog.py` runs exactly this double crash, with `truncate_tail` off. The cut is at `kvlog.py:402`, and it is synced before any new write.

#### The lab store's recovery time

It is not measured. The design reads every byte after the checkpoint once, and computes one CRC per entry. So its time grows with those bytes, which is inferred from the code. `RecoveryReport.seconds` prints it on each open, so you can measure it.

Bitcask has a similar file, the hint file. The paper's merge step writes it. It holds each key's position and no values, so a restart can read it instead of the data file. Merge is a form of compaction, and compaction is Phase 2.

## How does a PostgreSQL checkpoint decide where redo starts?

A PostgreSQL checkpoint must write every dirty page in shared memory, which can be gigabytes. So it spreads the work over minutes, and it is not a snapshot taken at one instant. The checkpointer, the background process that writes checkpoints, runs each one in three stages:

1. **Start.** It notes the current WAL insert position, and that LSN is the checkpoint's *REDO point*. Then it tags every buffer that is dirty at that moment.
2. **Writing.** It writes the tagged buffers over `checkpoint_completion_target` × `checkpoint_timeout`, 0.9 × 5 min = 4.5 minutes at the defaults.
3. **Completion.** It writes a checkpoint record, then updates `pg_control`, the small file that tells recovery where to begin.

Every change before the REDO point is on disk, but that counts only after completion. Until then, `pg_control` names the previous checkpoint.

1. **−5:00**  Checkpoint P starts. Its REDO point is the WAL position then.
2. **0:00**  Checkpoint A starts and notes REDO point A.
3. **4:29**  A crash here, before A completes, starts redo at P's REDO point. That is 9.5 minutes of WAL, 1.9 intervals.
4. **4:30**  A completes and updates `pg_control`.
5. **4:31**  A crash here starts redo at REDO point A, 4.5 minutes of WAL.

A checkpoint starts early when the WAL grows fast. PostgreSQL divides `max_wal_size` by 1 + `checkpoint_completion_target`. It stores the WAL in 16 MB files called segments. So 1 GB / 1.9 gives 33 segments, about 528 MB. With 475 MB more during the checkpoint, the worst redo is about 1,003 MB, close to a full `max_wal_size`. One measurement on PostgreSQL 18.6 replayed 1,080 MB in 6.0 s, so the predict answer was about 5 to 10 seconds. To size the setting, divide your recovery-time budget by your measured seconds per GB.

#### When a size-triggered checkpoint comes, and the worst redo max_wal_size, MB  (slider 256 to 8192, default 1024)  WAL rate, MB per second  (slider 1 to 100, default 6)  Trigger after (computed), every (computed). Worst WAL to replay (computed), redo about (computed)

An illustration, not a forecast: it keeps the target at 0.9, ignores the timer, and uses 5.6 to 7.7 s per GB.

A short interval has its own cost, because the first change to a page after each checkpoint writes a full page image. In the same test, `max_wal_size` 1GB forced 7 checkpoints in three minutes and wrote 3,815 MB of WAL, about 90% page images. At 8GB there were none, and the WAL was 1,080 MB. So the interval trades redo time against WAL to write, archive and send to replicas.

Restart time is redo plus one immediate checkpoint, which PostgreSQL runs before it accepts connections. In one production case on PostgreSQL 16.8, the checkpointer ran for more than four hours without finishing, and the restart replayed several hours of WAL. A checkpoint that never completes never moves the start of recovery.

**Remember:** Redo starts at the REDO point of the last completed checkpoint, up to 1.9 intervals back.

**Trap:** Reading a checkpoint as one instant snapshot hides up to 0.9 intervals of redo.

**Try:** Run `uv run python phase01_durability/crash_matrix.py --list` and say which checkpoint a power loss leaves at points 23 to 27.

**Evidence**

The three stages: Rogov, "PostgreSQL 14 Internals", section 10.3, pages 170 and 171. The worst case of 1 + `checkpoint_completion_target`: Rogov, section 10.6, page 177, who gives the same multiplier for the WAL a server must keep. The size trigger: `CalculateCheckpointSegments` at `xlog.c` line 2172, REL_18_0, with the same division in REL_14_0. Page images: Rogov, PostgreSQL 14.7, section 11.2, pages 189 to 191, `pgbench -t 20000`, hardware not stated. The end-of-recovery checkpoint: `xlog.c` at REL_18_0 and REL_14_0. Redo times and the 1GB against 8GB runs: Christophe Pettus, PostgreSQL 18.6, a kill of the postmaster, published 2026-09-29. The stuck checkpointer: Stormatics postmortem, 2026-07-01, fixed in 16.10.

**Go deeper: the settings, the size trigger step by step, page images and wal_compression, the end-of-recovery checkpoint by version, redo time, and the signals to read on a server**

#### The three stages in detail

Tagging needs no I/O, so the start is fast. Pages dirtied after the start are not tagged, so this checkpoint ignores them. `pg_control` lives in `global/`. At the defaults the worst case is 1 + 0.9 = 1.9 intervals of WAL. The times in the timeline are an example at `checkpoint_timeout` = 5 min and a completion target of 0.9. Checkpoint P completed at −0:30, and checkpoint B would start at 5:00. A size-triggered checkpoint at the defaults ends with about 528 + 475 = 1,003 MB since the old REDO point.

The end-of-recovery checkpoint is immediate, so it is not spread out, and its length grows with the pages that redo dirtied. So a recovery-time target has two parts, the redo and this checkpoint. The stuck checkpointer stayed active on PostgreSQL 16.8 on Kubernetes, and the forced restart came after it. The symptom came first as `ERROR: invalid memory alloc request size`, which looked like a memory problem.

#### The lab store against PostgreSQL

| Question | The lab store | PostgreSQL |
|---|---|---|
| what a checkpoint saves | the keydir, in one file | every page that was dirty when the checkpoint started |
| how it writes | five steps, three of them syncs | spread over `checkpoint_timeout` × `checkpoint_completion_target`, 4.5 minutes at the defaults |
| where recovery starts | the log offset stored in `keydir.ckpt` | the REDO point of the last completed checkpoint |
| work on restart | replay the log tail | redo from the REDO point, then one immediate checkpoint |

In the writing stage, a backend that writes a tagged buffer first also clears its tag. The postmaster is the first process of the server. At start it launches the startup process, which runs recovery, per Rogov, page 173. Rogov states the rule plainly: only from completion does the start of the checkpoint become the new starting point of recovery.

CMU 15-445 calls this design a fuzzy checkpoint, because transactions keep running during it. Its Fall 2025 notes for Lecture 22 mark the two ends with a CHECKPOINT-BEGIN and a CHECKPOINT-END record. PostgreSQL writes no record at the start. So its REDO point can be the LSN of a record of any type, per Rogov, page 171. The docs name the cost of the long spread. Prolonging checkpoints "affects recovery time", because more WAL must be kept for recovery, per the PostgreSQL 18 docs, section 28.5.

#### When a checkpoint starts

The defaults are the same in versions 14 and 18, from the docs of both versions and from a fresh 14.24 cluster for the first four:

| Setting | Default | What it does |
|---|---|---|
| `checkpoint_timeout` | 5 min | time between automatic checkpoints |
| `max_wal_size` | 1 GB | the WAL size that the size trigger is computed from |
| `min_wal_size` | 80 MB | WAL kept for reuse |
| `checkpoint_completion_target` | 0.9 | spread checkpoint writes over 90% of the interval |
| `checkpoint_warning` | 30 s | log a warning if size-triggered checkpoints come closer than this |

The arithmetic of the size trigger at the defaults:

1. `max_wal_size` is 1,024 MB, or 64 WAL segments of 16 MB each. A WAL segment is one file in `pg_wal`.
2. 64 / 1.9 = 33.7, which the code rounds down to 33 segments.
3. So a checkpoint is requested after about 33 × 16 = 528 MB of WAL since the last REDO point.
4. While it runs, the server writes about 0.9 × 528 = 475 MB more.
5. So when it completes, the WAL since the old REDO point is about 528 + 475 = 1,003 MB, close to `max_wal_size`.

That is the reason for the division, as the code comment explains. The docs also call `max_wal_size` "a soft limit". Heavy load, a failing archive command, or a high `wal_keep_size` can push the WAL past it, per the PostgreSQL 18 docs, section 19.5.2.

#### Full page images and wal_compression

The docs say that a smaller checkpoint interval "increases the volume of output to the WAL". That partly cancels the goal of the smaller interval, and it causes more disk I/O, per the PostgreSQL 18 docs, section 28.5. Rogov measured the size with `pgbench`, PostgreSQL's load tool, right after a checkpoint, when every page change is a first change:
- wal_compression off, WAL: 29 MB, 71.54% page images
- page images in it: 20 MB
- wal_compression on, WAL: 10 MB, 23.86% page images
- page images in it: 2 MB

MB here is 2^20 bytes, as `pg_size_pretty` prints. The page image bytes from `pg_waldump --stats` were 21,134,168 and 2,453,755, so 8.6 times smaller. The total WAL was 29 / 10 = 2.9 times less.

Rogov's cluster had data checksums on. In the first run, 93.78% of the page image bytes were in records of the XLOG resource manager, not of the table resource manager. Those are likely the hint-bit images that checksums cause, which is inferred from the record type and not checked. `wal_compression` is off by default. In PostgreSQL 14 it is on or off, and on means `pglz`. Since PostgreSQL 15 it accepts `pglz`, `lz4` and `zstd`, if the server was built with them, per the 14 and 18 docs, sections 20.5 and 19.5, and the 15.0 release notes. The view `pg_stat_wal`, since PostgreSQL 14, counts page images in `wal_fpi` and WAL bytes in `wal_bytes`. Phase 2 computes the page image cost per change for a B-tree, so this lesson does not repeat that model.

#### The end-of-recovery checkpoint by version

- **PostgreSQL 18.** The startup process requests `CHECKPOINT_END_OF_RECOVERY | CHECKPOINT_IMMEDIATE | CHECKPOINT_WAIT`. This is in `PerformRecoveryXLogAction`, `xlog.c` line 6358 at REL_18_0. The source says the checkpoint is "created before anyone is allowed to write WAL", at line 7024.
- **PostgreSQL 14.** The startup process runs it itself, with `CreateCheckPoint` at line 7923 of `xlog.c` at REL_14_0. The checkpointer runs during crash recovery only since PostgreSQL 15, per the 15.0 release notes.
- **After a standby is promoted.** PostgreSQL writes only an end-of-recovery record, and the checkpoint comes later.

Rogov describes the same step: the checkpoint secures the recovered state on disk, section 10.4, page 174. That its length grows with the pages redo dirtied is inferred from the `CHECKPOINT_IMMEDIATE` flag, and not measured.

#### The 1GB against 8GB test

Pettus ran PostgreSQL 18.6 with `pgbench`, four clients, scale 50, 512 MB of `shared_buffers`, three minutes per run and `checkpoint_timeout` 15min:

| `max_wal_size` | TPS | WAL written | checkpoints | `wal_fpi` |
|---|---|---|---|---|
| 1GB | 3,700 | 3,815 MB | 7, requested | 447,963 |
| 8GB | 4,131 | 1,080 MB | 0 | 91,335 |

At 1GB, page images were "about 90% of the bytes" with `wal_compression` off. The log warned "checkpoints are occurring too frequently (23 seconds apart)" seven times. A `log_checkpoints` line showed `distance=540676 kB`, the 528 MB size trigger. Pettus argues for 8GB with a 15-minute timeout, while the PostgreSQL docs only state the trade.

#### How long the redo takes

| WAL since the last checkpoint | Redo time | Per GB, or per second |
|---|---|---|
| 1,080 MB of ordinary WAL | 6.0 s | 6.0 / 1.08 = 5.6 s per GB, 180 MB per second |
| 1,627 MB of ordinary WAL | 12.5 s | 12.5 / 1.627 = 7.7 s per GB |
| 682 MB of full pages | 1.5 s | 455 MB per second |

He describes the redo as "single-threaded, with the data in cache". Pettus gives no hardware details, and his own estimate of 10 to 12 seconds per GB does not match his table. WAL made of full page images replayed faster per megabyte in his test. The likely reason is that each record is a plain page copy, which is inferred from the record type and not checked. Pettus does not say whether his times include the end-of-recovery checkpoint, and this course did not test it. Redo time also depends on `recovery_prefetch`, added in PostgreSQL 15 with the default `try`. It reads ahead the blocks that the next WAL records need, per the 15.0 release notes and the PostgreSQL 18 docs, section 19.5.4. So a redo timing means something only with its version and this setting. Do not size a production target on these numbers alone.

The stuck-checkpointer postmortem gives no WAL size and no replay time.

#### The signals to read on a real server

The lab prints `RecoveryReport.seconds`. A PostgreSQL server gives the same facts in its log, in its statistics views, and in one tool:

| Signal | What it shows | Version | Source |
|---|---|---|---|
| `log_checkpoints` | a "checkpoint starting" line, then a "checkpoint complete" line with buffers written, write, sync and total seconds, `distance` and `estimate` | off by default in 14, on since 15. `lsn` and `redo lsn` fields since 16 | PG 14 docs 20.8, PG 18 docs 19.8, 15.0 and 16.0 release notes, `xlog.c` REL_18_0 line 6794 |
| `checkpoint_warning` | "checkpoints are occurring too frequently (N seconds apart)", with the hint to raise `max_wal_size` | 14 and 18 | `checkpointer.c` REL_18_0 line 458, PG 18 docs 19.5 |
| `pg_stat_bgwriter` | `checkpoints_timed` and `checkpoints_req`: scheduled and requested checkpoints that completed. Many requested ones mean `max_wal_size` is too small | 14 to 16 | PG 14 docs Table 28.21, Rogov p. 181 |
| `pg_stat_checkpointer` | `num_timed`, `num_requested` and `num_done`. The first two also count skipped checkpoints, and `num_done` counts completed ones only | view since 17, `num_done` since 18 | 17.0 and 18.0 release notes, PG 18 docs Table 27.25 |
| `pg_stat_wal` | `wal_fpi` and `wal_bytes` since the last reset | since 14 | PG 14 docs Table 28.22 |
| `pg_controldata` | "Database cluster state", "Latest checkpoint location" and "Latest checkpoint's REDO location" | all versions | Rogov pp. 172 to 175 |
| startup log | "redo starts at", "redo done at" with elapsed time, the end-of-WAL line, and since 15 "redo in progress, elapsed time" every `log_startup_progress_interval`, default 10 s | 14 and 18 | `xlogrecovery.c` REL_18_0 lines 1748, 1761 and 1883, 15.0 release notes |

These recovery lines are from Rogov's PostgreSQL 14.7 example, page 175, after `pg_ctl stop -m immediate`. `log_checkpoints` was off there, so the end-of-recovery checkpoint does not appear:

```
LOG: database system was interrupted; last known up at 2023-03-06 14:01:49 MSK
LOG: database system was not properly shut down; automatic recovery in progress
LOG: redo starts at 0/3E7EF7E0
LOG: invalid record length at 0/3E7EF890: wanted 24, got 0
LOG: redo done at 0/3E7EF818 system usage: CPU: user: 0.00 s, system: 0.00 s, elapsed: 0.00 s
LOG: database system is ready to accept connections
```

The "invalid record length" line is the normal end of the WAL, not an error, as the table of the torn-write part showed. "redo starts at" names the REDO point from `pg_control`. Here is Rogov's checkpoint line on PostgreSQL 14.7, page 180, after a manual `CHECKPOINT`:

```
LOG: checkpoint starting: immediate force wait
LOG: checkpoint complete: wrote 4100 buffers (25.0%); 0 WAL file(s) added, 1 removed, 0 recycled; write=0.076 s, sync=0.009 s, total=0.099 s; sync files=3, longest=0.007 s, average=0.003 s; distance=9213 kB, estimate=9213 kB
```

`distance` is the WAL between the starts of the last two checkpoints, in kB. In PostgreSQL 18 the same line also prints SLRU buffers written, which are the cached pages of small files such as `pg_xact`, per the 18.0 release notes and `xlog.c` at REL_18_0, line 6794. An end-of-recovery checkpoint logs "checkpoint starting: end-of-recovery immediate" on 14, and adds " wait" on 18. That is inferred from the flag names in `LogCheckpointStart` of both versions, and not run. E13 crashes a throwaway cluster so you can read these lines yourself.

## What does OK promise, and which test proves it?

Each part above added a condition to "committed". So the store owes its users one sentence that states them, and a test that fails if it is wrong. The sentence has four parts:

1. **The moment of the promise.** Here, the entry passed a sync that covers it.
2. **The crash kinds it survives.** Process crash, OS crash or power loss.
3. **What recovery returns.** Here, a prefix of the puts in log order.
4. **What is not covered.** Such as a drive that ignores flushes.

For `--sync full` on a Mac, the lab store prints this sentence:

A put that returned OK, after its own sync, with sync=full on darwin, survives a process crash, an OS crash and a power loss. A put that did not return may or may not survive. Recovery returns a prefix of the puts in log order and never returns an entry that fails its CRC. Not covered: damage to data that was already synced, a drive that ignores flush commands, and loss of the device.

A *crash matrix* runs a fixed workload, stops the store at every write step, and checks recovery against the sentence. Each `self.hook(...)` line in the store is one *crash point*. The lab's 10 operations, with a checkpoint after the fourth, pass 57 of them.

**Predict: you remove the directory sync after the log is created. A kill -9 at each of the 57 crash points finds no lost put. Under an OS crash or a power loss, at how many crash points does the store lose acknowledged puts?**

At 20 crash points for each crash kind, so 40 violations in all. Most people expect 0, because every kill test passed. The kill test cannot see this failure, because a killed process leaves the kernel's copy of the directory in place.

At each crash point the matrix runs recovery on a process, an OS and a power image, which is 171 recoveries. At the 10 points with log bytes in flight it adds five short tears and one hole, which is 60 more. Let S(m) be the contents after the first m operations. The recovered contents must equal S(m) for some m, at most the started count. If the sentence promises that crash kind, m must also be at least the acknowledged count.

These are the expected violations, worked out from the code and not run:

| Run | process | OS | power |
|---|---|---|---|
| default, `--sync full`, 231 recoveries | 0 | 0 | 0 |
| `--real-kill --sync none`, 57 kills | 0 | not tested | not tested |
| `--skip-dir-sync` | 0 | 20 | 20 |
| `--sync fsync --claim-power-safe`, darwin model | 0 | 0 | 42 |

A kill test passes for a store that never syncs, because `kill -9` keeps the page cache. Without the directory sync, the log's name stays not durable until the checkpoint. So a crash from point #7, the first OK, to #26 finds no log, and the store opens empty with no error. The last row is this lesson's running case, found by a test.

**Remember:** State what an OK survives, and back each crash kind with its own test.

**Trap:** A boundary nobody tested passes every kill test and loses data on an OS crash or power loss.

**Try:** Run `uv run python phase01_durability/crash_matrix.py --skip-dir-sync` and predict its first violation line first.

**Evidence**

The sentence comes from `boundary_statement` at `kvlog.py:286`. The rule in code is `promises` at `kvlog.py:263`, and the check is `check()` at `crash_matrix.py:204`. LazyFS: the README at GitHub `dsrhaslab/lazyfs`, and Ramos and others, PVLDB volume 17, issue 11, 2024. The etcd postmortem was published on 2022-04-20. The bug was merged on 2021-05-08 and fixed in v3.5.3 on 2022-04-24, so the 351 days are arithmetic on those dates. The GitLab.com outage was on 2017-01-31, per GitLab's postmortem of 2017-02-10.

**Go deeper: the boundary per mode and platform, other systems' sentences, the crash point count, the check code, the etcd postmortem, and tools that test a real system**

#### The workload and the power-safe claim

The workload uses the keys `order:1041` to `order:1046`. The `--claim-power-safe` run checks the sentence most Python code would claim, that plain `os.fsync` on a Mac survives a power loss.

#### The second sentence

"A put that did not return may or may not survive" matters at the edge of every database. A client whose connection drops during COMMIT cannot tell which case it is in. Phase 3 shows how a PostgreSQL client finds out.

#### The boundary changes with the sync mode

`promises` is the same rule in code, and the crash matrix checks the code against it. Does an acknowledged put survive?

| Mode, platform | process crash | OS crash | power loss |
|---|---|---|---|
| full, macOS: `F_FULLFSYNC` | yes | yes | yes |
| full, Linux: `fsync` | yes | yes | yes |
| fsync, macOS | yes | NO, note 1 | NO |
| fsync, Linux | yes | yes | yes |
| none, any | yes | NO | NO |

Every "yes" for power loss assumes a drive that honours flush commands. Note 1: not promised, because Apple's `fsync(2)` says an OS crash can lose data after plain fsync. The `fsim.py` model still keeps the drive cache in an OS crash.

#### How other systems state it

Each sentence below covers one node only. What a replica has when the leader replies is in Phase 3 of course 5.

| System | The documented boundary, paraphrased | Source |
|---|---|---|
| PostgreSQL 18, `synchronous_commit=on` | every mode except `off` waits for the local WAL flush before it replies | PG 18 docs, 19.5 |
| SQLite, WAL mode, `synchronous=NORMAL` | stays consistent, but a commit can roll back after a power loss or OS crash. Commits survive an application crash in every mode | sqlite.org, `PRAGMA synchronous` |
| SQLite, WAL mode, `synchronous=FULL` | durable: one more sync of the WAL file after each commit | same page |
| MySQL 8.4, InnoDB with binary logging | durable with `sync_binlog=1` and `innodb_flush_log_at_trx_commit=1`. Other values can lose commits in a power failure or OS crash | MySQL 8.4 manual |

The Redis and NATS defaults are in the loss-window table of the group commit part. The SQLite rows depend on the journal mode, so the mode must be in the sentence. The default journal mode is the rollback journal, not WAL, per sqlite.org, "Write-Ahead Logging". WAL mode is chosen with `PRAGMA journal_mode=WAL`.

#### The crash point count

| Stage | Crash points | Hooks | Numbers |
|---|---|---|---|
| open a new store | 2 | open.created, open.dir-synced | #1 to #2 |
| ops 1 to 4 | 4 × 5 = 20 | encoded, written, synced, indexed, acked | #3 to #22 |
| checkpoint | 5 | log-synced, tmp-written, tmp-synced, renamed, dir-synced | #23 to #27 |
| ops 5 to 10 | 6 × 5 = 30 | the same five | #28 to #57 |
| total | 2 + 10 × 5 + 5 = 57 |  |  |

The torn-short image appears only where log bytes are in flight. With `--sync full` that is the `put.written` step of each of the 10 operations. The five cuts are at 1, 19, 20, half and all but one byte. The expected result for the default run is 0 violations in 231 recoveries, with all 60 torn cases detected. The check, from `crash_matrix.py:204`:

```
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

#### The directory sync window

In `fsim.py`, a name becomes durable only through a directory sync, and the checkpoint's step 5 is the first one. So the window is crash points #7 to #26: 26 − 7 + 1 = 20 points, each failing for the OS crash and the power loss.

```
--skip-dir-sync: where the boundary breaks. Expected, not run
#1 - #6     no put acknowledged yet          nothing promised  ok
#7 - #26    1 to 4 puts acknowledged, the    log name not      VIOLATION
            log's name is not durable        durable           20 + 20
#27 - #57   the checkpoint synced the        log name durable  ok
            directory
first line: #7 put.acked, os: acknowledged puts lost: recovered S(0),
            acknowledged 1
```

This is the missing directory fsync of the sync-failure part, and it is silent: the store opens without an error, and it is empty. Whether a real file system shows it depends on that file system. ALICE's Table 1 lists which persistence properties each Linux file system has. The model in `fsim.py` takes the strict reading, so a store that passes does not depend on one file system's extra ordering. APFS was not part of that study, and its behaviour here was not checked.

#### The 42 power violations

With `--sync fsync` on the darwin model and `--claim-power-safe`, the 42 come from crash points #7 to #22, which is 16, and #32 to #57, which is 26. Between them, the checkpoint's full syncs made the log durable up to operation 4. There are 0 OS violations because the model keeps the drive cache in an OS crash.

#### What a real kill test adds

`--real-kill` runs the same workload in a child process on real files. It sends `SIGKILL` at each of the 57 crash points. The expected result is 0 violations in every sync mode, `--sync none` too. A real kill test is still worth running. It tests the real file calls, the real `O_APPEND` writes and the real rename, which the model does not. It cannot test power.

#### A real postmortem about crash testing

The etcd project published the "v3.5 data inconsistency postmortem". A refactor in v3.5.0 stopped saving the consistent index atomically with the data it describes. A crash between the two writes left a member inconsistent. The maintainers reproduced it under heavy load by killing one member with SIGKILL at random. It was reproduced only because one maintainer had `/tmp` on a normal disk. The bug was merged in v3.5.0 and fixed in v3.5.3, 351 days later. The postmortem does not say why the disk mattered. A likely reason is that a real device makes each write slower, which widens the window between the two writes. That reason is inferred, not checked. A test on a memory file system, such as a tmpfs `/tmp` on Linux, never reaches a device at all. So `shared/durable.py` refuses to measure there.

#### Tools that test a real system's boundary

The matrix tests a model. For a real service, run it on a layer that loses writes on command, and check recovery against the sentence at each write step. These tools sit between the model and a kill test. Each tool runs the real program on such a layer, a device or a file system. Device-mapper is the Linux layer that builds virtual block devices on top of real ones, and two of the tools are device-mapper targets:

| Tool | What it does | Source |
|---|---|---|
| LazyFS | a FUSE file system with its own page cache. A `clear-cache` fault drops unsynced data at a chosen call, and `torn-op` and `torn-seq` tear writes | LazyFS README, GitHub `dsrhaslab/lazyfs` |
| LazyFS, results | used on seven systems, PostgreSQL, etcd, ZooKeeper, Redis, LevelDB, PebblesDB and Lightning Network. It found eight new bugs | Ramos and others, PVLDB volume 17, issue 11, abstract |
| `dm-log-writes` | a device-mapper target that logs each write in order of completion. It logs a write only at the next flush, so a replay shows what was on disk, not in cache | kernel docs, device-mapper "log-writes" |
| `dm-flakey` | a device-mapper target with `drop_writes`, `error_writes` and `corrupt_bio_byte`. `error_writes` is a real kernel version of the failed fsync in E9 | kernel docs, device-mapper "dm-flakey" |
| `diskchecker.pl` | the device test of the sync part, with a real power cut | named in PG 18 docs, 28.1 |

LazyFS, `dm-log-writes` and `dm-flakey` are Linux tools. The LazyFS README says it was tested with ext4 on Debian 11 and Ubuntu 20.04. On a Mac they need a Linux virtual machine. Whether LazyFS works with macFUSE was not checked, and neither was the platform support of `diskchecker.pl`.

#### What the boundary leaves out, on purpose

The sentence covers crashes, not an operator who deletes data or backups that do not restore. The GitLab.com database outage was that case. An engineer wiped the primary database's data directory, and the backups had failed, per GitLab's postmortem. Recovery from deletion needs its own plan.

## What you can do now, and what comes next

You can now say which crash erases a put at each step, and pick and test the durable sync. You can say where recovery starts and stops, and write a store's promise with a crash matrix behind it.

Phase 2 answers why one workload runs ten times faster on one storage structure than on another. It also builds the compaction step, which Bitcask calls merge, that this store left out.

Run the lab first, then answer the checkpoint questions without looking back.

## Lab: build the store and break it

Thirteen exercises from the phase, not yet run by the author.

Section numbers used below: 1.1 Where can a write be. 1.2 What must be durable. 1.3 How far one sync call moves the bytes, and when a sync fails. 1.4 A half-written entry. 1.5 Where recovery starts, and the PostgreSQL checkpoint. 1.6 Group commit. 1.7 What OK promises.

**Practice: where it runs, what it costs, and how long it takes**

Everything runs on your laptop and costs nothing. The labs use Python 3.12 or later and the standard library only. Two exercises read your local PostgreSQL 14 at `/tmp:5432`, in a new database named `storage_lab`. One exercise, E13, crashes PostgreSQL on purpose. It uses a separate throwaway cluster on port 54329, never your main cluster. Run all commands from `elite-storage/code/`. The reading takes about 3 hours, and the labs take about 2.5 to 3.5 hours.

**Practice: open the lab, E1 to E13**

The labs below are written and reviewed, but were not run by the author. Each script was checked with `python3 -m py_compile` only. Every "Expected" line says "Not run by the author yet." and then gives the expected shape. Each number in it comes from arithmetic in this phase, or from a cited measurement. The measurements are the earlier course's M2 runs and this course's M4 Pro research. Your timings will differ. The counts from the simulated file system should match exactly, because that part has no randomness and no timing.

**What you build.** The lab is a Bitcask-style store with a stated durability boundary, in five files:

| File | What it holds | Self-test checks |
|---|---|---|
| `shared/durable.py` | `durable_sync`: `F_FULLFSYNC` on macOS, `fsync` on Linux, and the directory sync | the decision table for both platforms, a real sync in every mode |
| `phase01_durability/fsim.py` | `RealFS`, and `SimFS` with three layers: page cache, drive cache, stable media | each layer rule, the fsyncgate rule, directory entries, both torn shapes |
| `phase01_durability/kvlog.py` | the store: entries with CRC, the keydir, group commit, checkpoint, recovery | each rule of `Rules`, removed one at a time, fails a check |
| `phase01_durability/crash_matrix.py` | crash injection at all 57 steps, five crash kinds, the S(m) check | the counts of section 1.7, and each break below |
| `phase01_durability/group_commit.py` | one sync per put against group commit, on real files | sync counts on a simulated device with a 2 ms sync |

The demonstration of this phase is E5, E6 and E8 together. They show the store and its stated boundary, and the crash matrix across every write step. They also show a torn write that the checksum detects instead of serving it.

All commands run from `elite-storage/code/`. E13 is the only exercise that crashes PostgreSQL, and it uses a throwaway cluster that it creates itself.

-  **E1 (offline).** See which system call each sync mode makes on your machine.

  - Run: `uv run python shared/durable.py --self-test`, then `uv run python shared/durable.py --explain`.
  - Expected: Not run by the author yet. `self-test passed`. Then on a Mac: `mode full -> F_FULLFSYNC`, `mode fsync -> fsync`, `mode none -> none`, and the file system `apfs`. On Linux, both `full` and `fsync` map to `fsync`.
  - If it fails: a line `F_FULLFSYNC is not supported here, falling back to fsync` means the directory is on a network or SMB mount. Use a local folder.
  - Teaches: the same Python call means a different guarantee on macOS and Linux.

-  **E2 (local).** Measure the cost of each sync mode.

  - First write your prediction for the median of `full` and `fsync`.
  - Run: `uv run python shared/durable.py --measure 200`.
  - Expected: Not run by the author yet. Three lines with p50, p99 and max per mode. On a Mac, a fourth line gives the ratio of `full` to `fsync`. Compare your medians with the cost diagram in section 1.3, one machine at a time. The `none` line should be a few microseconds. The M4 Pro table in section 1.3 shows 3 µs for "write, no sync".
  - Teaches: a durable commit on a Mac costs milliseconds, and `os.fsync` hides that.

-  **E3 (break-it, local).** Kill the store at every write step, with no sync at all.

  - Run: `uv run python phase01_durability/crash_matrix.py --real-kill --sync none`.
  - Expected: Not run by the author yet. `Dry run: 57 crash points`, and a `process` row of 57 cases with `0` violations. Then the note that a killed process leaves the page cache in place. Then run it with `--sync full`. The result should be the same.
  - If it fails with "child exited with 3": the crash point was never reached. Check that the hook count in `--list` is 57.
  - Teaches: a kill test cannot tell a store that syncs from one that does not.

-  **E4 (offline).** Run every self-test, and use the store by hand.

  - Run: `uv run python phase01_durability/fsim.py --self-test`, then the same for `kvlog.py`, `crash_matrix.py` and `group_commit.py`.
  - Then run: `uv run python phase01_durability/kvlog.py --put order:1041=paid --put order:1042=paid --report`, and then `uv run python phase01_durability/kvlog.py --get order:1041 --report`.
  - Expected: Not run by the author yet. Four lines `self-test passed`. The first store run prints `recovery: new store, log created`, the boundary sentence, and two `OK put` lines. The first is `bytes 0..34`: 20 header bytes, 10 key bytes and 4 value bytes. The second run prints `2 entries replayed` and `get order:1041: paid`.
  - Teaches: the boundary sentence is printed by the code that the matrix tests.

-  **E5 (offline).** The crash matrix with the stated boundary. This is the main demonstration.

  - First write your prediction: the number of crash points, the number of recoveries, and the number of violations.
  - Run: `uv run python phase01_durability/crash_matrix.py`.
  - Expected: Not run by the author yet. `Dry run: 57 crash points`. Rows `process 57`, `os 57`, `power 57`, `torn-short 50`, `torn-hole 10`, each with `0` violations. The torn rows show `50` and `10` in the `torn detected` column. Last line: `RESULT: 0 violations in 231 recoveries. The stated boundary held.` Section 1.7 shows the arithmetic.
  - Teaches: a boundary is backed by a test that checks every write step against it.

-  **E6 (break-it, offline).** Remove the directory sync after the log is created.

  - Run: `uv run python phase01_durability/crash_matrix.py --skip-dir-sync`.
  - Expected: Not run by the author yet. `process` 0 violations, `os` 20, `power` 20. The torn rows have fewer cases, 30 and 6, because the log's name is not durable until crash point #27. The first violation line: `#7 put.acked, os: acknowledged puts lost: recovered S(0), acknowledged 1`.
  - Teaches: a synced file whose name is not durable can vanish with all its data.

-  **E7 (break-it, offline).** Check the claim that plain fsync is durable on a Mac.

  - Run: `uv run python phase01_durability/crash_matrix.py --sync fsync --claim-power-safe`, then `uv run python phase01_durability/crash_matrix.py --sync fsync`, then `uv run python phase01_durability/crash_matrix.py --sync fsync --platform-model linux`.
  - Expected: Not run by the author yet. With the claim: `power` 42 violations, `os` 0, and violations in the torn rows too. Without the claim: 0 violations, because the honest sentence for `fsync` on macOS promises a process crash only. On the linux model: 0 violations in 231 recoveries, as in E5.
  - Teaches: the same code has a different boundary on each platform, and the sentence must say which.

-  **E8 (break-it, offline).** A torn write, with and without the checksum.

  - Run: `uv run python phase01_durability/kvlog.py --torn-demo`, then `uv run python phase01_durability/crash_matrix.py --no-crc`.
  - Expected: Not run by the author yet. The demo prints the WRONG and RIGHT lines of section 1.4. First 1,200 bytes with 512 zeros, then a stop at offset 1230 with `checksum mismatch`. The matrix with `--no-crc` shows `torn-hole` with 8 violations of 10, and `torn-short` with 0. The 8 are the puts. The 2 deletes are 30 bytes long, and each hole zeroes the whole entry, so the length check stops them.
  - Teaches: only a checksum catches a write with the right length and the wrong bytes.

-  **E9 (break-it, offline).** A failed fsync, retried and not retried.

  - Run: `uv run python phase01_durability/kvlog.py --fsync-error-demo`.
  - Expected: Not run by the author yet. WRONG: three puts acknowledged, and only `order:1041` after the power loss. Recovery stopped at offset 1230 with `impossible lengths ksz=0 vsz=0`, and 2460 bytes dropped. RIGHT: one put acknowledged and none lost. Both cases print that a restart without power loss sees `order:1042` through the page cache.
  - Teaches: after an fsync error the only safe action is to stop. The page cache can still show data the disk lacks.

-  **E10 (local).** One sync per put against group commit, on your SSD.

  - First write your prediction for both rates with 16 writers, from section 1.6.
  - Run: `uv run python phase01_durability/group_commit.py --writers 16 --puts 50 --repeat 3`, then `uv run python phase01_durability/group_commit.py --writers 1 --puts 200 --repeat 3`.
  - Expected: Not run by the author yet. With 16 writers, the `per-put` lines show `puts/sync 1.0`. Their rate is at or below the M2 limit of 351 per second from section 1.6. The `group` lines show puts per sync well above 1, a rate several times higher, and a higher p50 latency. With 1 writer, both modes are about the same. Compare runs only with their spread, as the earlier course's Phase 1 taught.
  - If the group rate equals the per-put rate: the sync call may not release the interpreter lock. Section 1.6 names this as not checked.
  - Teaches: group commit trades a little latency per put for a large gain in throughput.

-  **E11 (local, PostgreSQL 14).** Read your own cluster's durability settings.

  - Run: `createdb -h /tmp -p 5432 storage_lab`.
  - Then run: `psql -h /tmp -p 5432 -d storage_lab -c "select name, setting, source from pg_settings where name in ('wal_sync_method','synchronous_commit','full_page_writes','data_checksums','data_sync_retry','commit_delay','commit_siblings','checkpoint_timeout','max_wal_size','wal_writer_delay','checkpoint_completion_target','checkpoint_warning','log_checkpoints','wal_compression') order by name"`.
  - Then run: `psql -h /tmp -p 5432 -d storage_lab -c "select checkpoints_timed, checkpoints_req, stats_reset from pg_stat_bgwriter"`, and `pg_controldata "$(psql -h /tmp -p 5432 -d storage_lab -Atc 'show data_directory')" | grep -E "cluster state|REDO location"`. Both only read.
  - Expected: Not run by the author yet. The research's fresh 14.24 cluster showed `wal_sync_method open_datasync`, `synchronous_commit on`, `full_page_writes on`, `data_checksums off`, `data_sync_retry off`, `commit_delay 0`, `commit_siblings 5`, `checkpoint_timeout 300`, `max_wal_size 1024`, `wal_writer_delay 200` and `checkpoint_completion_target 0.9`. The PostgreSQL 14 docs give `checkpoint_warning 30`, `log_checkpoints off` and `wal_compression off`. A row whose source is not `default` was changed by your configuration. The counters show how many checkpoints were scheduled and requested since `stats_reset`. `pg_controldata` shows `in production` for a running server, and the REDO point of its last checkpoint.
  - Teaches: your laptop's PostgreSQL acknowledges commits that a power cut can remove, has no data checksums, and does not log its checkpoints.

-  **E12 (local).** Time each WAL sync method of PostgreSQL.

  - Run: `pg_test_fsync -s 3 -f ./pg_test_fsync.tmp`, then delete `./pg_test_fsync.tmp` if it is still there.
  - Expected: Not run by the author yet. Compare each line with the M4 Pro table in section 1.3, which this course's research measured with the same command. The line "Direct I/O is not supported on this platform" is expected on macOS.
  - Teaches: the one method that flushes the drive cache on macOS is about 180 times slower than the default. 45,480 / 250 = 182.

-  **E13 (break-it, local, PostgreSQL 14).** Crash a throwaway PostgreSQL cluster, and read its real recovery.

  - The tools are there. Homebrew's `postgresql@14` 14.24 ships `initdb`, `pg_ctl`, `pgbench`, `pg_controldata` and `pg_waldump`. Verified on the owner's machine on 2026-10-18: `pg_waldump --version` printed `pg_waldump (PostgreSQL) 14.24 (Homebrew)`.
  - Warning: every command below uses the throwaway directory in `$LAB` and port 54329. `pg_ctl stop -m immediate` crashes whichever cluster it names, so never point `-D` at your main cluster.
  - Run: `psql -h /tmp -p 5432 -Atc "show data_directory"`. Write the path down. It is the main cluster, and no step below may use it.
  - Run: `export LAB="$HOME/pg14-crash-lab"`, then `test ! -e "$LAB" && echo free`.
  - Expected: `free`. If nothing prints, the directory exists. Choose a new name. Do not reuse a directory that you did not create for this exercise.
  - Run: `initdb -D "$LAB"`.
  - Run: `pg_ctl -D "$LAB" -l "$LAB/server.log" -o "-p 54329 -k /tmp -c log_checkpoints=on" start`.
  - Run: `pgbench -h /tmp -p 54329 -i postgres`.
  - Run: `psql -h /tmp -p 54329 -d postgres -At -c "checkpoint" -c "select pg_current_wal_insert_lsn()"`. Write the LSN down as START.
  - Run: `pgbench -h /tmp -p 54329 -t 2000 postgres`, then `psql -h /tmp -p 54329 -d postgres -Atc "select pg_current_wal_insert_lsn()"`. Write it down as END.
  - Run: `psql -h /tmp -p 54329 -d postgres -Atc "select pg_size_pretty('END'::pg_lsn - 'START'::pg_lsn)"`, with your two values in place of END and START.
  - Run: `echo "$LAB"`.
  - Expected: your throwaway path, not the main cluster path you wrote down. If it prints anything else, stop here.
  - Warning: the next step crashes the cluster that `-D` names.
  - Run: `pg_ctl -D "$LAB" stop -m immediate`. The PostgreSQL 14 docs say this mode aborts all server processes "without a clean shutdown". In the terms of section 1.1 it is a process crash, so the page cache survives and power loss is not tested.
  - Run: `pg_controldata "$LAB" | grep -E "cluster state|Latest checkpoint location|REDO location"`.
  - Run: `pg_waldump --stats -p "$LAB/pg_wal" -s START -e END`, with your two values.
  - Run: `pg_ctl -D "$LAB" -l "$LAB/server.log" -o "-p 54329 -k /tmp -c log_checkpoints=on" start`, then `tail -n 12 "$LAB/server.log"`.
  - Expected: Not run by the author yet. `pg_controldata` shows `Database cluster state: in production`. On a stopped server that means it did not shut down cleanly, per Rogov, page 173. The REDO location is your manual checkpoint's REDO point, right before START, unless a timed checkpoint ran during the test. The `--stats` table ends with a `Total` line that gives the share of page image bytes. Rogov's 71.54% came from a cluster with data checksums on. Your `initdb` used the 14 default of off, so expect a smaller share. That is inferred, not measured. No source ran this exact test, so no WAL size is predicted. The log should show these lines in this order:

    - `database system was interrupted`
    - `database system was not properly shut down; automatic recovery in progress`
    - `redo starts at`, with the REDO location
    - `invalid record length at ...: wanted 24, got 0`
    - `redo done at`
    - `checkpoint starting: end-of-recovery immediate`, then `checkpoint complete`
    - `database system is ready to accept connections`

  - The two checkpoint lines are inferred from the PostgreSQL 14 source, as section 1.5 explains.
  - Run, to clean up: `pg_ctl -D "$LAB" stop`, then `echo "$LAB"`. If it prints your throwaway path and nothing else, run `rm -rf "$LAB"`.
  - If it fails: if `pg_ctl start` reports that port 54329 is in use, choose another free port in both start commands and every `psql` and `pgbench` command. If `pg_waldump` cannot find a WAL file, a checkpoint removed old segments. Run the test again with a smaller `-t`.
  - Teaches: a real redo starts at the REDO point, ends at the first invalid record, and is followed by one immediate checkpoint. These are the lines you will meet in a production log.

## Checkpoint questions

Answer each question before you open the sketches.

**Practice: check it yourself, six code-reading tasks**

- **Check 1.** Open `phase01_durability/kvlog.py:348`. This is the directory sync after the log is created, inside `Store.open`. With `--sync none`, this line does nothing. Why does that not break the boundary that `--sync none` states? Which row of the boundary table in section 1.7 shows it?
- **Check 2.** Open `phase01_durability/kvlog.py:402`. Recovery cuts the torn tail here and then syncs the cut. Suppose the sync on the next line were removed. Describe a second power loss, during the next put, that brings the torn bytes back. Is an acknowledged put lost, or only an unacknowledged one?
- **Check 3.** Open `phase01_durability/kvlog.py:495`. The group commit leader reads `target` before it calls the sync. Suppose it read `target` after the sync returned. Which puts could then return OK before their bytes were covered by a sync? Would any assertion in the self-test of `kvlog.py` catch this change? If not, describe a check that would.
- **Check 4.** Open `phase01_durability/fsim.py:451`. This is where the torn hole is placed. For the 30-byte delete of `order:1042` at offsets 4920 to 4950, compute the sector that this line zeroes. Then explain why `--no-crc` in E8 gives 8 violations and not 10.
- **Check 5.** Open `xact.c` at tag REL_18_0, line 1498, in `RecordTransactionCommit`. This is the test that decides between `XLogFlush` and the asynchronous path. Name the two conditions that force a synchronous flush even with `synchronous_commit = off`. Read the comment above the test, and say why deleting a table's files is one of them.
- **Check 6.** In any repository you own that writes files it must not lose, run `grep -rn "fsync\|F_FULLFSYNC\|\.Sync()" <your repo>/`. For each hit, answer two questions. On macOS, does the call flush the drive cache? And what does the code do when the call returns an error?

**Practice: checkpoint 1, eight questions**

The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

1. **Test-out, explain.** Walk through what happens when the store runs `put order:1041` with `--sync full` on a Mac. Name the five crash points of the put in order. For each one, say where the entry is and whether the client has its OK. Also say what a power loss there leaves after recovery. Then say what `F_FULLFSYNC` does not guarantee, even after it returns. Finally, match the steps of the put to the PostgreSQL commit order of section 1.2.
2. **Test-out, predict.** The default workload crashes at point #29, which is `put.written` of operation 5, the delete of `order:1042`. The crash is a power loss, and the drive kept the first 15 bytes of the 30-byte entry. Predict what recovery reads from the checkpoint, and where it starts the log scan. Then predict how many log entries it replays, and where it stops. Then give the recovered contents.
3. **Test-out, demonstrate.** Run E5 and E6. Show that the stated boundary holds in all 231 recoveries. Then explain each of the 40 violations that `--skip-dir-sync` produces, with the arithmetic of the crash points. Finally, run E8 and show the one torn write that the checksum detects and that `--no-crc` serves.
4. **A colleague says:** "Our CI runs on Macs and production runs on Linux with ext4. Both call `os.fsync`, and the crash tests pass on CI. So production is covered." Argue for or against, with the numbers and sources of this phase. Say which crash kind the CI test cannot cover and why, and which one it covers well.
5. **This is broken.** A Linux service writes events to an append-only log and syncs after each event. Its log shows one `EIO` from fsync on Tuesday at 10:00, then a retry that succeeded. The service ran normally. After a reboot on Friday, every event from Tuesday 10:00 onwards is missing, though all of them were acknowledged. What is the cause, and how do you check it? Why are the later events lost too, and not only the one at 10:00?
6. **Show the arithmetic.** On the M4 Pro, `F_FULLFSYNC` took about 4.0 ms. A store has 32 concurrent writers. Compute the upper limit of puts per second with one sync per put, and with group commit. Compute the longest wait of one put with group commit, first with no delay, then with a 1 ms delay. With the delay, what is the new throughput limit, if every batch holds all 32 writers?
7. **Given these constraints, design.** An example: a single-node audit log runs on a Linux server. It must survive a power loss, take 3,000 events per second at peak, and restart within 30 seconds. The SSD's flush takes about 2 ms. Choose the commit mode, the checkpoint rule, and the recovery rule, and write the durability boundary sentence. Show why one sync per event cannot meet the rate.
8. **Recovery time.** Your PostgreSQL 18 server must be back within 20 seconds after a crash. It runs the default checkpoint settings and writes WAL at a peak of 6 MB per second. Compute when a checkpoint is triggered, and the worst-case WAL to replay. Explain why it is more than one checkpoint's worth. Use Pettus's table from section 1.5, with its limits, to estimate the redo time at 5.6 and at 7.7 seconds per GB. Then say what else runs before the server opens, how far you could raise `max_wal_size`, and which signal shows how often size-triggered checkpoints happen.

**Answer sketches for the eight questions**

1. `put.encoded`: nothing written, no OK, recovery gives the state before the put. `put.written`: the entry is in the page cache, no OK. A power loss loses it, or tears it, and recovery drops it by length or CRC. `put.synced`: `F_FULLFSYNC` returned, so the drive was asked to flush, and the entry survives. No OK yet. `put.indexed`: the same, now visible to readers. `put.acked`: the client has its OK and the entry survives. `F_FULLFSYNC` does not guarantee that the drive honours the flush. Zheng and others found 13 of 15 SSDs that did not behave. It also does not make the file's name durable, which needs the directory sync. In PostgreSQL, `put.written` matches the commit record in the WAL buffers, `put.synced` matches `XLogFlush`, and `put.indexed` matches `ProcArrayEndTransaction`, when other sessions see the rows. PostgreSQL also writes the outcome to `pg_xact` between the last two. With `synchronous_commit = off`, PostgreSQL makes rows visible before the flush, which the lab store never does.
2. The checkpoint is valid and covers 0 to 4920, so the keydir comes from it with the last sequence 4. The log scan starts at 4920 and finds 15 bytes. That is less than the 20-byte header, so `short header, 15 of 20 bytes`. 0 entries are replayed. Recovery stops at 4920, drops 15 bytes, cuts the file and syncs the cut. Contents: S(4), which is `order:1041` v2, `order:1042` v1 and `order:1043` v1. Operation 5 was not acknowledged, so nothing promised is lost.
3. Expected from the code, not run. E5: 57 crash points, 171 + 50 + 10 = 231 recoveries, 0 violations, 60 torn cases detected. E6: from #7, the first acknowledgment, to #26, before the checkpoint's directory sync, the log's name is not durable. That is 26 − 7 + 1 = 20 points. Each fails for the OS crash and for the power loss, so 20 + 20 = 40. E8: the hole in the second put of `order:1041` lies at 1536 to 2048. The CRC catches it. `--no-crc` serves 512 zero bytes.
4. Against. On the Mac, `os.fsync` stops at the drive cache: Apple's `fsync(2)` page. On Linux ext4 with barriers on, fsync makes the file system flush the drive: PostgreSQL 18 docs, 28.1. So the two platforms have different boundaries for an OS crash and a power loss. A crash test that kills processes covers the process kind on both, and nothing more. In E7, the power-loss model of a Mac with `os.fsync` is expected to show 42 violations. The Linux model is expected to show 0. Those counts are worked out from the code, not run. The CI test is right about process crashes and says nothing about power. CI timings also come from a different system call than production, so they do not predict production timings.
5. fsyncgate. The failed fsync marked the pages clean, and the retry reported success for data that was never written. Rebello and others, ATC 2020, Table 1, found this on ext4, XFS and Btrfs. Check: search the service log and `dmesg` for the I/O error at 10:00. Then read the log file at the offset written at that time, and look for zeros or old data. The later events are lost because recovery stops at the first bad entry. Everything after the damaged range is dropped, though it was synced. Fix: stop the process at the first fsync error, never retry, and let recovery run on restart. PostgreSQL has done this by default since 2019-02-14.
6. One sync per put: 1 / 4.0 ms = 250 puts per second. Group commit: at most 32 per sync, so 32 × 250 = 8,000 per second. Longest wait without delay: one sync in progress plus its own, 2 × 4.0 = 8.0 ms. With a 1 ms delay: 1 + 4.0 + 4.0 = 9.0 ms in the worst case. Throughput with the delay: one batch per 1 + 4.0 = 5.0 ms. So 32 / 5.0 ms = 6,400 per second. The delay only helps when batches would otherwise be small.
7. One sync per event: 1 / 2 ms = 500 per second, far below 3,000. Group commit: at 3,000 per second and 2 ms per sync, a batch holds 3,000 × 0.002 = 6 events. That is enough. Commit mode: group commit with the full sync, which is `fsync` on Linux with barriers on. Checkpoint: write the index often enough that the log since the checkpoint replays well within 30 seconds. Measure the scan rate first with `RecoveryReport.seconds`. Recovery: a CRC per entry, and a stop at the first bad entry. Cut and sync the cut. Sync the directory after create and rename. Stop on any fsync error. Boundary: an OK means the event passed a sync that covers it. It survives a process crash, an OS crash and a power loss, on a drive that honours flushes. Recovery returns a prefix and never a damaged entry. Not covered: damage to synced data and loss of the device. This is an example, not measured.
8. The size trigger at the defaults is about 528 MB of WAL since the last REDO point: 64 segments / 1.9 = 33, and 33 × 16 MB = 528 MB. At 6 MB per second that is 528 / 6 = 88 seconds, sooner than the 5-minute timer, so checkpoints are size-triggered. 88 s is more than the 30 s `checkpoint_warning`, so no warning appears. The worst case is a crash right before a checkpoint completes. Recovery then starts at the previous REDO point, because the REDO point counts only after completion. The WAL since then is about 528 + 0.9 × 528 = 1,003 MB, about 1 GB. `max_wal_size` is a soft limit, so a load spike can push it higher. Redo: 1.0 × 5.6 = 5.6 s and 1.0 × 7.7 = 7.7 s. Then the end-of-recovery checkpoint runs, immediate, with a length not measured here. So the target holds with room. Raising `max_wal_size` would cut page images. At 7.7 s per GB, 20 s is 20 / 7.7 = 2.6 GB of replay. So about 2 GB leaves room for that checkpoint and the soft limit. Signals: `num_requested` against `num_timed` in `pg_stat_checkpointer`, and the `distance` of each "checkpoint complete" line. This is a starting point only, with the limits of Pettus's table in section 1.5. Measure on your own hardware, first on a throwaway cluster as in E13.

## Cheatsheet

**Practice: open the cheatsheet**

```
WHERE A WRITE IS, AND WHAT KEEPS IT
  process memory    lost by every crash         f.write() buffer
  page cache        kept by a process crash     after os.write
  drive cache       kept by an OS crash in      after fsync on macOS
                    the model only. Apple: an OS crash can lose it
  stable media      kept by a power loss        after F_FULLFSYNC on macOS,
                                                fsync on Linux ext4, barriers on

THE TWO RULES (ARIES 1992, section 1.1)
  WAL rule          log record durable before the data page it describes
  commit rule       log durable up to the commit record before the reply
  STEAL, NO-FORCE   pages may reach disk before commit, need not at commit

POSTGRESQL COMMIT ORDER (xact.c REL_18_0)
  commit record -> XLogFlush -> pg_xact -> sync standby -> visible -> reply
  LSN               byte offset into the WAL. lsn2 - lsn1 = WAL bytes
  sync_commit off   visible before durable: no external action on it

SYNC CALLS
  macOS durable     fcntl.fcntl(fd, fcntl.F_FULLFSYNC)   Go: os.File.Sync
  macOS not         os.fsync(fd)                          Go: syscall.Fsync
  Linux durable     os.fsync(fd)
  new file, rename  also sync the directory
  M2 cost           os.fsync 95-110 us, F_FULLFSYNC 2.85-2.88 ms   (elite-performance 5.6)
  M4 Pro cost       os.fsync 25-31 us,  F_FULLFSYNC about 4.0 ms   (this course's research)
  after fsync EIO   stop. Never retry. PostgreSQL PANICs since 2019-02-14
  Linux checks      /sys/block/<disk>/queue/write_cache, hdparm -I,
                    sdparm --get=WCE, pg_test_fsync -f, diskchecker.pl
  NFS               mount hard, export sync. O_DIRECT is not O_SYNC

POSTGRESQL DEFAULTS, 14 AND 18
  synchronous_commit on       off loses up to 3 x wal_writer_delay = 600 ms
  wal_sync_method             fdatasync on Linux, open_datasync on macOS
  macOS, flush the drive      fsync_writethrough: 250 ops/s against 45,480 (M4 Pro)
  full_page_writes on         torn data pages restored from WAL
  data_checksums              off in 14, on in 18 initdb
  data_sync_retry off         PANIC on a failed data flush
  checkpoint_timeout 5min, max_wal_size 1GB, checkpoint_completion_target 0.9
  commit_delay 0 us, commit_siblings 5
  PostgreSQL 14 final release 2026-11-12

TORN WRITES
  sector 512 B, PostgreSQL page 8,192 B = 16 sectors
  short write       caught by the length check
  hole, right size  caught only by the CRC. Random damage passes 1 in 2^32
  recovery          stop at the first bad entry, cut, sync the cut
  PG WAL record     24-byte header, CRC-32C, xl_prev chain
  InnoDB            doublewrite buffer. AWS torn write prevention removes it

RECOVERY
  lab               replay the log after the offset in keydir.ckpt
  lab ckpt steps    sync log, write tmp, sync tmp, rename, sync directory
  PG starts at      REDO point = WAL insert position at checkpoint START,
                    valid only after that checkpoint COMPLETES
  PG worst replay   (1 + checkpoint_completion_target) intervals = 1.9
  PG size trigger   max_wal_size / 1.9: 1 GB -> 33 segments = 528 MB
  max_wal_size      a soft limit
  PG restart        redo + one immediate end-of-recovery checkpoint
  PG redo (Pettus)  5.6 to 7.7 s per GB of ordinary WAL, no hardware given
  page images       29 MB WAL, 71.54% images; wal_compression on: 10 MB,
                    23.86% (Rogov, PG 14.7, pgbench -t 20000)

CHECKPOINT SIGNALS
  log_checkpoints   off in 14, on since 15. lsn fields since 16
  warning           "checkpoints are occurring too frequently", < 30 s
  counters          pg_stat_bgwriter 14-16, pg_stat_checkpointer 17+
  pg_controldata    cluster state, Latest checkpoint's REDO location
  startup log       redo starts at / invalid record length / redo done at

GROUP COMMIT
  one sync per put  max = 1 / t_sync        2.85 ms -> 351/s
  group, W writers  max = W / t_sync        16 writers -> 5,616/s
  latency cost      up to 2 x t_sync        5.7 ms
  ack only after a sync that started after the append
  PG commit_delay   start at half the pg_test_fsync flush time
  MySQL durable     sync_binlog=1 and innodb_flush_log_at_trx_commit=1
  fsync=off         corruption, not a loss window

TEST TOOLS (LINUX)
  LazyFS, dm-log-writes, dm-flakey, diskchecker.pl

THE BOUNDARY SENTENCE
  when OK is sent, which crash kinds it survives, what recovery returns,
  what is not covered. Back it with a crash matrix: 57 points, 231 recoveries,
  counts worked out from the code and not run
```

## Sources

**Practice: open the sources**

This course's research fetched every URL below on 2026-10-17. The depth revision of 2026-10-18 added the entries for the PostgreSQL write path, checkpoints, Linux testing, MySQL and AWS, fetched that day. Each URL was checked again with `check_urls.py`. Primary sources come first in each group.

#### The original designs

- **ARIES: A Transaction Recovery Method Supporting Fine-Granularity Locking and Partial Rollbacks Using Write-Ahead Logging, Mohan and others, ACM TODS, 1992**: https://cs.stanford.edu/people/chrismre/cs345/rl/aries.pdf
    Focus on: section 1.1, journal pages 97 and 98, for the WAL rule and the commit rule. Section 6 for the three restart passes. PDF page N is journal page N + 93. This copy is a scan with OCR text, so check any new quote against the page image. Read it before section 1.2 and 1.5.
- **Bitcask: A Log-Structured Hash Table for Fast Key/Value Data, Sheehy and Smith, Basho, 2010**: https://riak.com/assets/bitcask-intro.pdf
    Focus on: page 2 for the entry layout and the tombstone, page 3 for the keydir, page 5 for recovery. A company paper, not peer reviewed. 15 minutes. Read it before the lab.

#### What fsync promises, and how it fails

- **Can Applications Recover from fsync Failures?, Rebello and others, USENIX ATC, 2020**: https://www.usenix.org/system/files/atc20-rebello.pdf
    Focus on: Table 1 on page 6, which shows each file system after a failed fsync. Section 5 gives the lessons. All tests are on Linux 5.2.11. Read it after section 1.3.
- **All File Systems Are Not Created Equal, Pillai and others, USENIX OSDI, 2014**: https://www.usenix.org/system/files/conference/osdi14/osdi14-paper-pillai.pdf
    Focus on: Table 1 for persistence properties per file system, and page 12 for the missing directory fsync. Linux file systems of 2014, no APFS. Read it before E6.
- **PostgreSQL's handling of fsync() errors is unsafe and risks data loss at least on XFS, Craig Ringer, pgsql-hackers, 2018**: https://www.postgresql.org/message-id/CAMsr%2BYHh%2B5Oq4xziwwoEfhoTZgr07vdGG%2Bhu%3D1adXx59aTeaoQ%40mail.gmail.com
    Focus on: the first message. It explains the cleared error flag in a few paragraphs. The primary source of fsyncgate.
- **PostgreSQL 11.2 release notes, 2019-02-14**: https://www.postgresql.org/docs/release/11.2/
    Focus on: the item about PANIC instead of retrying after fsync failure, and `data_sync_retry`. The same item is in 10.7, 9.6.12, 9.5.16 and 9.4.21.
- **Fsync Errors, PostgreSQL wiki**: https://wiki.postgresql.org/wiki/Fsync_Errors
    Focus on: the list of platforms and kernel versions. A community page. Its macOS line is not from Apple.
- **PostgreSQL's fsync() surprise, Jonathan Corbet, LWN.net, 2018**: https://lwn.net/Articles/752063/
    Focus on: the explanation of why the checkpointer did not see errors from before it opened the file. A short second account of the same bug.

#### Disks, operating systems and runtimes

- **Understanding the Robustness of SSDs under Power Fault, Zheng, Qin, Tucek and Lillibridge, USENIX FAST, 2013**: https://www.usenix.org/system/files/conference/fast13/fast13-final80.pdf
    Focus on: section 4 for the test method, Table 5 for the failures by drive. Drives from about 2012. The one study here that cut real power.
- **fsync(2), Apple xnu source, tag xnu-12377.121.6**: https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.121.6/bsd/man/man2/fsync.2
    Focus on: the paragraph about the drive cache, the sentence about power loss or an OS crash, and `F_FULLFSYNC`. Use this copy, not the older archive page.
- **fcntl(2), Apple xnu source, tag xnu-12377.121.6**: https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.121.6/bsd/man/man2/fcntl.2
    Focus on: lines 207 to 245, `F_BARRIERFSYNC` and `F_FULLFSYNC`. Apple's older archive copy of this page does not list APFS, so use this copy.
- **fd_fsync_darwin.go, Go source, tag go1.27.2**: https://github.com/golang/go/blob/go1.27.2/src/internal/poll/fd_fsync_darwin.go
    Focus on: line 22, the `F_FULLFSYNC` call, and the `ENOTSUP` fallback after it. History: Go has used `F_FULLFSYNC` on darwin since Go issue 26650, closed on 2018-08-22 for Go 1.12. The fallback comes from Go issue 64215. That it first shipped in Go 1.23 is inferred from the issue's milestone.
- **posixmodule.c, CPython source, tag v3.14.8**: https://github.com/python/cpython/blob/v3.14.8/Modules/posixmodule.c
    Focus on: `os_fsync_impl` near line 3993, which calls the plain `fsync`. CPython issue 56086 asks `os.fsync` to flush the drive. It was still open on 2026-10-17.

#### PostgreSQL documentation

- **19.5 Write Ahead Log, PostgreSQL 18**: https://www.postgresql.org/docs/18/runtime-config-wal.html
    Focus on: `wal_sync_method`, `full_page_writes`, `synchronous_commit`, `commit_delay` and the checkpoint settings. Replace 18 with 14 in the URL for your local version, where the chapter is 20.5.
- **28.1 Reliability, PostgreSQL 18**: https://www.postgresql.org/docs/18/wal-reliability.html
    Focus on: drive caches, the macOS `fsync_writethrough` advice, and the 512-byte sectors.
- **28.4 Asynchronous Commit, PostgreSQL 18**: https://www.postgresql.org/docs/18/wal-async-commit.html
    Focus on: the loss window of `synchronous_commit=off`.
- **28.5 WAL Configuration, PostgreSQL 18**: https://www.postgresql.org/docs/18/wal-configuration.html
    Focus on: how crash recovery finds the redo point from the latest checkpoint, the spread checkpoint, the full page cost of short intervals, the "gangway effect" and the `commit_delay` starting value.
- **Error Handling, PostgreSQL 14**: https://www.postgresql.org/docs/14/runtime-config-error-handling.html
    Focus on: `data_sync_retry`.
- **Data Checksums, PostgreSQL 14**: https://www.postgresql.org/docs/14/checksums.html
    Focus on: the default of off, and what checksums cover.
- **PostgreSQL 18.0 release notes, 2025-09-25**: https://www.postgresql.org/docs/release/18.0/
    Focus on: the `initdb` change that enables data checksums by default, listed under incompatibilities.
- **Versioning Policy, PostgreSQL**: https://www.postgresql.org/support/versioning/
    Focus on: the final release date of version 14, 2026-11-12.

#### The PostgreSQL write path, checkpoints and recovery

- **PostgreSQL 14 Internals, Egor Rogov, Postgres Professional, 2023**: https://edu.postgrespro.com/postgresql_internals-14_en.pdf
    Focus on: chapter 10, pages 164 to 181, for the LSN, `pg_waldump`, the spread checkpoint and its REDO point, recovery after `pg_ctl stop -m immediate`, and checkpoint monitoring. Chapter 11, pages 182 to 191, for asynchronous commit with `pgbench`, checksums, full page images and `wal_compression`. Every example runs on PostgreSQL 14.7, and the hardware is not stated. A free book, not peer reviewed. Read chapter 10 with section 1.5.
- **PostgreSQL source, tag REL_18_0, `src/backend/access/transam`**: https://github.com/postgres/postgres/tree/REL_18_0/src/backend/access/transam
    Focus on: `xact.c`, `RecordTransactionCommit` from line 1315, for the commit order. `xlog.c`: `CalculateCheckpointSegments` at line 2172, `XLogFlush` at line 2855, `PerformRecoveryXLogAction` at line 6323 and the checkpoint log line at 6794. `xlogrecovery.c` lines 1748 to 1883 for the redo log lines. `xlogreader.c` lines 670, 1166 and 1331 for the end-of-WAL and prev-link checks.
- **9.28 System Administration Functions, PostgreSQL 18**: https://www.postgresql.org/docs/18/functions-admin.html
    Focus on: `pg_current_wal_insert_lsn`, `pg_current_wal_lsn` and `pg_current_wal_flush_lsn`.
- **28.6 WAL Internals, PostgreSQL 18**: https://www.postgresql.org/docs/18/wal-internals.html
    Focus on: the LSN as a byte offset, and how two LSNs give the WAL between them.
- **27.2 The Cumulative Statistics System, PostgreSQL 18**: https://www.postgresql.org/docs/18/monitoring-stats.html
    Focus on: Table 27.25 `pg_stat_checkpointer`, Table 27.26 `pg_stat_wal`, and `checksum_failures` in `pg_stat_database`. For version 14, `pg_stat_bgwriter` is Table 28.21 in the same chapter of the 14 docs.
- **19.8 Error Reporting and Logging, PostgreSQL 18**: https://www.postgresql.org/docs/18/runtime-config-logging.html
    Focus on: `log_checkpoints`, default on, and `log_startup_progress_interval`. The 14 page, section 20.8, gives `log_checkpoints` the default off.
- **pg_waldump, PostgreSQL 14**: https://www.postgresql.org/docs/14/pgwaldump.html
    Focus on: `-p`, `-s`, `-e` and `--stats`, the options E13 uses.
- **pg_ctl, PostgreSQL 14**: https://www.postgresql.org/docs/14/app-pg-ctl.html
    Focus on: the three stop modes. Immediate mode leads to crash recovery at the next start.
- **PostgreSQL 15.0 release notes**: https://www.postgresql.org/docs/release/15.0/
    Focus on: `log_checkpoints` on by default, startup progress messages, `recovery_prefetch`, the checkpointer during crash recovery, and LZ4 and Zstandard for `wal_compression`.
- **PostgreSQL 17.0 release notes**: https://www.postgresql.org/docs/release/17.0/
    Focus on: the new view `pg_stat_checkpointer`, which took the checkpoint columns from `pg_stat_bgwriter`.
- **18.2 Creating a Database Cluster, PostgreSQL 18**: https://www.postgresql.org/docs/18/creating-cluster.html
    Focus on: section 18.2.2.1, "NFS", for the `hard` mount option and the `sync` export option.

#### Testing durability on a real system

- **When Amnesia Strikes: Understanding and Reproducing Data Loss Bugs with Fault Injection, Ramos and others, PVLDB volume 17, issue 11, 2024**: https://www.vldb.org/pvldb/vol17/p3017-ramos.pdf
    Focus on: the abstract, the table of systems and versions, and the paragraph "Protection and recovery" for the PostgreSQL torn page test. Read it before you plan a crash test of a real service.
- **LazyFS, GitHub `dsrhaslab/lazyfs`**: https://github.com/dsrhaslab/lazyfs
    Focus on: the fault types `clear-cache`, `torn-op` and `torn-seq`, and the tested platforms, ext4 on Debian 11 and Ubuntu 20.04.
- **dm-log-writes, Linux kernel docs**: https://docs.kernel.org/admin-guide/device-mapper/log-writes.html
    Focus on: "Log Ordering". Writes are logged only at the next flush, so a replay shows what was on disk.
- **dm-flakey, Linux kernel docs**: https://docs.kernel.org/admin-guide/device-mapper/dm-flakey.html
    Focus on: `drop_writes`, `error_writes` and `corrupt_bio_byte`.
- **Explicit volatile write back cache control, Linux kernel docs**: https://docs.kernel.org/block/writeback_cache_control.html
    Focus on: `REQ_PREFLUSH`, `REQ_FUA`, and what the block layer does for a device with no volatile cache.
- **sysfs-block, Linux kernel ABI**: https://www.kernel.org/doc/Documentation/ABI/stable/sysfs-block
    Focus on: the entry `/sys/block/<disk>/queue/write_cache` and its warning about switching to "write through".
- **diskchecker.pl, Brad Fitzpatrick, LiveJournal**: https://brad.livejournal.com/2116715.html
    Focus on: how the client and server check that flushed data survives a power cut. This is the link the PostgreSQL 28.1 docs give. A personal blog post.
- **open(2) and fsync(2), Linux man-pages**: https://man7.org/linux/man-pages/man2/open.2.html
    Focus on: `O_DIRECT` and its note that it does not give the guarantees of `O_SYNC`. The `fsync(2)` page at https://man7.org/linux/man-pages/man2/fsync.2.html gives the Linux 4.13 change to error reporting.

#### MySQL and cloud devices

- **Doublewrite Buffer, MySQL 8.4 Reference Manual**: https://dev.mysql.com/doc/refman/8.4/en/innodb-doublewrite-buffer.html
    Focus on: why InnoDB writes each page twice, and the default.
- **Binary Logging Options and Variables, MySQL 8.4 Reference Manual**: https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html
    Focus on: `sync_binlog`, its default of 1, and the pair of settings for the greatest durability.
- **Torn write prevention, Amazon EC2 User Guide**: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/storage-twp.html
    Focus on: the first section, which says all-or-nothing writes remove the need for the doublewrite buffer. A vendor page, so its percentages are vendor claims.

#### SQLite

- **Atomic Commit In SQLite**: https://www.sqlite.org/atomiccommit.html
    Focus on: section 2 for the hardware assumptions, and section 9.2 for drives that report a flush early.
- **Pragma statements**: https://www.sqlite.org/pragma.html
    Focus on: `PRAGMA synchronous` for the durability of each mode, and `fullfsync` for macOS.
- **Write-Ahead Logging**: https://www.sqlite.org/wal.html
    Focus on: the first paragraph. The default is the rollback journal.

#### Incidents and analyses

- **Jepsen: MariaDB Galera Cluster 12.1.2, Kyle Kingsbury, 2026**: https://jepsen.io/analyses/mariadb-galera-cluster-12.1.2
    Focus on: section 3.1 for the loss under the recommended setting, and section 4. Section 3.2 is a separate loss with no root cause.
- **Configuring MariaDB Galera Cluster, MariaDB docs**: https://mariadb.com/docs/galera-cluster/galera-management/configuration/configuring-mariadb-galera-cluster
    Focus on: the current advice on `innodb_flush_log_at_trx_commit`. Compare it with the Wayback copy of 2026-03-08.
- **InnoDB System Variables, MariaDB docs**: https://mariadb.com/docs/server/server-usage/storage-engines/innodb/innodb-system-variables
    Focus on: `innodb_flush_log_at_trx_commit` and its values 0 to 3.
- **Jepsen: NATS 2.12.1, Kyle Kingsbury, 2025**: https://jepsen.io/analyses/nats-2.12.1
    Focus on: section 3.4, the two-minute fsync default. LazyFS is the tool that models power loss there.
- **v3.5 data inconsistency postmortem, etcd project, 2022**: https://github.com/etcd-io/etcd/blob/main/Documentation/postmortems/v3.5-data-inconsistency.md
    Focus on: the root cause and the line about `/tmp` on a normal disk. A first-party postmortem with dates.
- **Postmortem of database outage of January 31, GitLab, 2017**: https://about.gitlab.com/blog/postmortem-of-database-outage-of-january-31/
    Focus on: the timeline. It is an operator deletion and failed backups, not a sync failure.
- **Power-loss post-mortem, Brad Fitzpatrick, LiveJournal lj_dev, 2005**: https://lj-dev.livejournal.com/670215.html
    Focus on: the list of what failed after the power cut, and the plan to turn off the drive caches and test power cuts. A first-party post. Fetched on 2026-10-18.
- **S3 Downtime: More Missing Bites, Rich Miller, Data Center Knowledge, 2008**: https://www.datacenterknowledge.com/outages/s3-downtime-more-missing-bites
    Focus on: Amazon's quoted account of the single-bit errors and the missing checksum. Amazon's own page, status.aws.amazon.com/s3-20080720.html, returned 404 on 2026-10-18, so this is a second-hand report.
- **2023-07-02 -- 2023-07-03 Tarsnap outage post-mortem, Colin Percival, Tarsnap, 2023**: https://mail.tarsnap.com/tarsnap-announce/msg00050.html
    Focus on: the two recovery steps, and the two things that slowed the replay. A first-party post. Fetched on 2026-10-18.

#### Measurements of group commit and recovery

- **commit_delay for better performance: a PostgreSQL benchmark, Laurenz Albe, CYBERTEC, 2025**: https://www.cybertec-postgresql.com/en/commit_delay-performance-postgresql-benchmark/
    Focus on: the results table and the hardware setup, with the disk limited to 1,000 IOPS.
- **Testing the Group Commit Fix, Vadim Tkachenko, Percona, 2011**: https://www.percona.com/blog/testing-the-group-commit-fix/
    Focus on: the two test tables, with and without the controller's write cache. The unit is not stated.
- **The synchronous_commit parameter and streaming replication, Kaarel Moppel, CYBERTEC, 2016**: https://www.cybertec-postgresql.com/en/the-synchronous_commit-parameter/
    Focus on: the two rows with asynchronous replication, `on` and `off`. The synchronous replication rows belong to course 5.
- **All Your GUCs in a Row: max_wal_size, Christophe Pettus, 2026**: https://thebuild.com/blog/all-your-gucs-in-a-row-max_wal_size/
    Focus on: the redo time table. New, not peer reviewed, no hardware given.
- **Inside a PostgreSQL Checkpointer Bug: A Production Postmortem, Warda Bibi, Stormatics, 2026**: https://stormatics.tech/blogs/postgresql-checkpointer-bug-causing-infinite-retry-loop
    Focus on: why a stuck checkpointer leaves hours of WAL to replay. No numbers for the replay itself.
- **Redis persistence, Redis docs**: https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/
    Focus on: the `appendfsync` policies and their stated loss windows.

#### Lectures

- **CMU 15-445/645 Fall 2025, Lecture 21: Database Logging, Andy Pavlo**: https://www.youtube.com/watch?v=CedEy54pe3g
    Focus on these times:
    0:17:32 steal and force policies
    0:19:40 force defined
    0:24:21 shadow paging
    0:39:25 SQLite rollback journal
    0:44:41 write-ahead logging
    0:48:46 WAL implementation
    0:51:30 log record contents
    0:55:02 group commit
    1:10:32 checkpoints
    1:19:10 summary
    The times are YouTube's auto-generated chapters, and five were checked against the auto-generated captions. Two spoken claims disagree with the docs. At about 1:19:10 the captions show him saying that synchronous commit is not on by default in PostgreSQL. The PostgreSQL 14 and 18 docs, and a fresh 14.24 cluster, say `on`. At about 0:39:25 they show him saying that SQLite now uses the WAL by default. The SQLite docs say the default is the rollback journal. This phase teaches the docs.
- **Lecture 21 slides**: https://15445.courses.cs.cmu.edu/fall2025/slides/21-logging.pdf
    Focus on: the group commit and checkpoint slides, to read with the video.
- **Lecture 21 notes, CMU 15-445 Fall 2025**: https://15445.courses.cs.cmu.edu/fall2025/notes/21-logging.pdf
    Focus on: section 2, the STEAL and FORCE policies, which section 1.2 uses.
- **Lecture 22 notes, Database Crash Recovery, CMU 15-445 Fall 2025**: https://15445.courses.cs.cmu.edu/fall2025/notes/22-recovery.pdf
    Focus on: the LSN types, non-fuzzy and fuzzy checkpoints with CHECKPOINT-BEGIN and CHECKPOINT-END, and the ARIES passes. Read it after section 1.5, to compare ARIES with PostgreSQL.
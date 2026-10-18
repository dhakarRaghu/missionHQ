# Phase 1 — Durability and the write path

**The question this phase answers:** when the database says "committed", what exactly has happened on disk? And what can a crash one millisecond later still lose?

## Why you're here

Here is the situation this whole phase follows. It is an example, built from measured numbers, and every part of it happens in this phase's lab.

A small order store runs on a Mac. A client sends `put order:1041`, and the store replies OK. The client sends `put order:1042`, and the store replies OK. One millisecond later the power fails. On restart, both orders are gone. The client holds a receipt for each one.

The store's code was not careless. It wrote each entry, called `os.fsync`, and only then replied. On an Apple M2, the earlier course measured that call at about 0.1 ms. So both replies were sent within about a quarter of a millisecond. But on macOS, `os.fsync` hands the data to the drive and returns. The drive keeps the data in its own cache and writes it to flash later. Nobody had tested a crash between "the operating system accepted the write" and "the device has it".

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

Real systems have also replied OK before the data was durable, in their recommended or default settings.

- **MariaDB Galera Cluster.** Jepsen's analysis "MariaDB Galera Cluster 12.1.2", by Kyle Kingsbury, was published on 2026-03-16. At that time, MariaDB's own Galera configuration page recommended `innodb_flush_log_at_trx_commit=0`. That setting does not flush the log at commit. In section 3.1 of the report, all nodes crashed at about the same time. That was a crash of the database processes, not a power loss. One one-minute run lost nine acknowledged values in three rows. With the setting at 1, the loss became much rarer. Verified from the report, section 3.1. MariaDB later changed the page to recommend the default of 1. The new page warns that 0 and 2 can lose acknowledged transactions. Verified from two archived copies of the page, dated 2026-03-08 and 2026-06-11. That the change followed the report is inferred from the timing only.
- **NATS.** Jepsen published its analysis "NATS 2.12.1" on 2025-12-08. By default, NATS JetStream calls fsync only once every two minutes, but acknowledges each message at once. A simulated power failure lost 131,418 of 930,005 messages, about thirty seconds of writes. Verified from the report, section 3.4.

The report's second loss, in its section 3.2, happened with the setting at 1 and has no root cause, so this phase does not use it.

So "committed" means something narrower than it sounds. It holds for some kinds of crash, on some devices, after some system calls. This phase finds out which.

## What you can do after this phase

1. Say where a write is at each step of a commit, and which kind of crash erases it.
2. Name the system call that makes data durable on macOS and on Linux, and say what it does not promise.
3. Detect a torn write with a checksum, and make recovery stop at the right place.
4. Explain what a PostgreSQL checkpoint bounds, what a restart runs, and read both in the server log and the statistics views.
5. Use group commit to get throughput back without giving up durability.
6. Write the one-sentence durability boundary of a store, and test it with a crash matrix.

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
│ Lab: E1 to E13. The demonstration: a crash matrix with 231 recoveries    │
└──────────────────────────────────────────────────────────────────────────┘
```

## What this phase assumes

Two ideas from the earlier course are used here and not taught again. That course is "Performance, concurrency and the machine", in the folder `elite-performance`.

- **Section 5.6, "Syscalls, buffers and the page cache".** The page cache is the kernel's copy of recently used file pages. On the author's Apple M2, a page-cache read took 1.5 µs at the median. A read from the SSD took 88.7 to 89.8 µs. A page there is 16 KiB. After a 4 KiB write, `os.fsync` took 95 to 110 µs, and `fcntl(F_FULLFSYNC)` took 2.85 to 2.88 ms. Those are medians per run, measured on 2026-09-25.
- **Phase 1, parts 01a and 01b, "Measurement before optimisation".** Latency is a distribution, not one number. A closed-loop load generator hides stalls, because it waits for each reply. Two runs are compared only with their spread. A prediction is written down before the run.

**The commitment this phase pays.** Section 5.6 of the earlier course measured the cost of `os.fsync` and `F_FULLFSYNC`. It said that what each call promises was left for a later course. Section 1.3 of this phase gives that answer.

This course's research measured the same calls on a second Mac, an Apple M4 Pro, and section 1.3 keeps each machine's numbers separate.

**Left for later.** Course 5, "Distributed systems and verification", covers replicas in its Phase 3. That phase says what a replica has when the leader acknowledges a write. Phase 2 of this course covers the structures built on the log, such as B-trees and LSM trees.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. The labs use Python 3.12 or later and the standard library only. Two exercises read your local PostgreSQL 14 at `/tmp:5432`, in a new database named `storage_lab`. One exercise, E13, crashes PostgreSQL on purpose. It uses a separate throwaway cluster on port 54329, never your main cluster. Run all commands from `elite-storage/code/`.

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

In the running case, the store did call `os.fsync`. So the two orders left the page cache and reached the drive. The next question is why the store writes a log at all, and in which order it writes and syncs.

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

**A data page can reach the disk before its commit.** Step 5 has no fixed time. In PostgreSQL the checkpointer, the process that runs checkpoints, writes dirty pages. So does the bgwriter, a background process that writes pages likely to be evicted soon. A backend, the server process of one client connection, writes a dirty page itself when it must evict it. Verified from Rogov, "PostgreSQL 14 Internals", section 10.5, page 176. So a page with an uncommitted change can be on disk. The CMU 15-445 Fall 2025 notes for Lecture 21 name the two policies. STEAL lets the database write uncommitted changes to disk before the transaction completes. NO-FORCE means changes are not required to be on disk at commit. The WAL rule is what makes STEAL safe, because the log record of every change on disk is on disk first. Phase 2 shows the line in the buffer manager that enforces it.

**What PostgreSQL waits for.** The parameter `synchronous_commit` has the default `on` in PostgreSQL 14 and 18. With it, a commit waits for the local WAL flush. With `off`, the commit replies at once and the WAL writer flushes later. The docs give the maximum delay as three times `wal_writer_delay`. The default `wal_writer_delay` is 200 ms, so the window is 3 × 200 ms = 600 ms. A crash in that window can lose recent commits. The database stays consistent, as if those transactions had been aborted. Verified from the PostgreSQL 18 docs, section 19.5, and section 28.4. The 200 ms default was measured on a fresh PostgreSQL 14.24 cluster by this course's research.

**The LSN, the address of a WAL record.** A log sequence number, LSN for short, is a byte offset into the WAL. It grows with each new record. So the difference of two LSNs is the number of WAL bytes between them. Verified from the PostgreSQL 18 docs, section 28.6. PostgreSQL prints an LSN as two hexadecimal numbers with a slash, such as `0/3DF708D8`. Three functions show the current positions. `pg_current_wal_insert_lsn()` gives the insert location, `pg_current_wal_lsn()` the write location, and `pg_current_wal_flush_lsn()` the flush location. Verified from the PostgreSQL 18 docs, section 9.28. Rogov ran one `UPDATE` and `COMMIT` on PostgreSQL 14.7. The insert LSN moved from `0/3DF708D8` to `0/3DF70948`, which is 112 bytes. `pg_waldump`, the tool that prints WAL records, showed two records in that range. Here they are, shortened to the fields this phase uses. Verified from Rogov, section 10.2, pages 168 and 169:

```
rmgr: Heap len (rec/tot): 69/ 69, tx: 886, lsn: 0/3DF708D8, prev 0/3DF708B0, desc: HOT_UPDATE ...
rmgr: Transaction len (rec/tot): 34/ 34, tx: 886, lsn: 0/3DF70920, prev 0/3DF708D8, desc: COMMIT ...
```

Each record names its resource manager, the code that replays it, and its length and transaction. Each record's `prev` field holds the LSN of the record before it, so the WAL is a chain. The two records start 0x3DF70920 − 0x3DF708D8 = 0x48 = 72 bytes apart, and the second ends 0x28 = 40 bytes later. So the 69-byte record takes 72 bytes and the 34-byte record takes 40, and 72 + 40 = 112. Each record is padded to a multiple of 8 bytes. That rule is inferred from this arithmetic, and not checked in the source.

**The commit inside PostgreSQL.** The first diagram of this section shows the order in principle. Here is the order in the PostgreSQL 18 source. `pg_xact` is the set of files that holds each transaction's outcome, and Phase 3 shows how readers use it:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ COMMIT inside PostgreSQL 18. From RecordTransactionCommit and            │
│ CommitTransaction in xact.c at tag REL_18_0                              │
├──────────────────────────────────────────────────────────────────────────┤
│  step  function                 what it does                     line    │
│  1     XactLogCommitRecord      commit record into WAL buffers   1442    │
│  2     XLogFlush                WAL flushed up to that record.   1502    │
│                                 The durability point                     │
│  3     TransactionIdCommitTree  "committed" written in pg_xact   1508    │
│  4     SyncRepWaitForLSN        wait for a standby, if one is    1557    │
│                                 configured. Course 5                     │
│  5     ProcArrayEndTransaction  other sessions now see the rows  2389    │
│  6     reply to the client      the acknowledgment                       │
│                                                                          │
│ synchronous_commit = off: step 2 becomes XLogSetAsyncXactLSN at line     │
│ 1523, and the WAL writer flushes later. Step 5 still runs at once        │
└──────────────────────────────────────────────────────────────────────────┘
```

Step 4 waits only when a standby, a server that replays this server's WAL, must confirm the commit. Course 5 covers it. Right before step 1, the backend sets the flag `DELAY_CHKPT_START`, and it clears the flag after step 3. A checkpoint that starts in that window waits. Otherwise it could set its recovery start point, which section 1.5 calls the REDO point, between the commit record and the `pg_xact` update. A crash a little later would then lose the commit. Verified from the comment before line 1442.

`synchronous_commit = off` has a consequence that its docs entry does not state. Step 5 runs before the WAL flush, so other sessions can read the new rows before they are durable. A crash in the next 600 ms can then remove rows that another session already read. That order is inferred from the code, and not run. The docs give the rule that follows. Asynchronous commit "should not be used if the client will take external actions" that rely on the commit. Verified from the PostgreSQL 18 docs, section 28.4. A webhook or a queue message sent after such a read is that kind of external action.

**What MariaDB's setting 0 does.** `innodb_flush_log_at_trx_commit` controls the same moment in InnoDB. The MariaDB InnoDB system variables page lists four values, 0 to 3. With 1, the default, the log is written and flushed at each commit. With 2, it is written at each commit and flushed on a timer. With 0, nothing happens at commit, and the log is written and flushed about once a second. With 3, the log is flushed at both the prepare and the commit phase, which is slower than 1 and keeps the same guarantee. The page warns that with 0 a server crash can erase the last second of transactions. Verified from the MariaDB docs page, fetched on 2026-10-17. So with 0, the reply comes before the log is durable. That breaks the commit rule, and it is the mechanism in the Galera report. A crash of the server process alone is enough, because the log is not yet in the page cache. That last point is inferred from the definition of value 0.

**When the log is the data.** In the store of this lab, there is no separate data file. The log is the data. This is the Bitcask design: Sheehy and Smith, Basho Technologies, 2010. Bitcask appends every put to a data file and keeps an in-memory index called the keydir. The keydir maps each key to the file, offset and size of its newest entry. A delete is a put of a special tombstone value. The paper says recovery needs no replay, because the data files are the log. But the keydir still has to be rebuilt by reading the log after a restart. Section 1.5 covers that read. The Bitcask paper is a company paper, not peer reviewed.

The lab's entry layout follows the paper's figure on page 2. The CRC covers every byte after itself:

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

**macOS: fsync stops at the drive.** Apple's `fsync(2)` page says fsync moves the data from the host to the drive. It then says the drive may keep that data in its cache for a long time. The drive may also write it to the media out of order. The page then names the result. After a power loss or an OS crash, an application may find only some or none of its data written. The page tells databases that need a strict write order to use `F_FULLFSYNC`. Verified from the man page in Apple's xnu source at tag `xnu-12377.121.6`, and in the macOS 26.5 SDK. The page also warns: "This is not a theoretical edge case."

`F_FULLFSYNC` is a command of `fcntl(2)`. It does what fsync does, and then asks the drive to flush all of its buffered data to permanent storage. The current man page names APFS among the file systems that support it. The same page describes `F_BARRIERFSYNC`, which sends a barrier instead of a flush. A barrier keeps the order of writes, but it does not make them durable. Verified from `fcntl.2` at the same xnu tag, lines 207 to 245.

So the answer for the Mac: the running case survives a process crash. It does not survive a power loss, because the orders were in the drive's cache. Apple's page says an OS crash can lose them too. So the lab store does not promise that case for plain fsync on a Mac. The answer for Linux with ext4 is yes, on two conditions. Write barriers are on, and the drive honours the flush command. The rest of this section gives the evidence for both.

**What each language calls.** The same function name means different system calls in different runtimes:

| Runtime, version | Call | What it does on macOS | Source |
|---|---|---|---|
| CPython 3.14.8, `os.fsync` | `fsync()` | stops at the drive cache | `Modules/posixmodule.c` line 3993, `os_fsync_impl` |
| CPython, `fcntl.fcntl(fd, fcntl.F_FULLFSYNC)` | `F_FULLFSYNC` | flushes the drive | `Modules/fcntlmodule.c` lines 639 to 640 export the constant |
| Go 1.24.0 and 1.27.2, `os.File.Sync` | `F_FULLFSYNC` | flushes the drive | `internal/poll/fd_fsync_darwin.go` line 22 |
| Go, `syscall.Fsync` | `fsync()` | stops at the drive cache | `syscall/zsyscall_darwin_arm64.go` lines 710 to 716 |

All four rows were verified from the source at the named tags by this course's research. If `F_FULLFSYNC` returns `ENOTSUP`, for example on an SMB mount, Go falls back to plain fsync. The history of both Go changes, and an open CPython request to change `os.fsync`, are in the references.

**This is why the lab uses two calls.** `shared/durable.py` makes every durable sync of the course. On macOS it calls `fcntl(fd, F_FULLFSYNC)`. On Linux it calls `os.fsync`, because Linux has no `F_FULLFSYNC`, and the file system sends the drive's flush command itself. On Linux, write barriers are the file system option that makes it send that command. They are not the Apple barrier described above. The PostgreSQL 18 docs, section 28.1, name ZFS and ext4 as examples of file systems that can send it. The same section says to turn write barriers off only behind a controller with a working battery-backed cache. XFS is not named there, and this course did not check it. Here is the decision, from `durable.py:92`:

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

**PostgreSQL on a Mac.** PostgreSQL chooses its WAL sync call with `wal_sync_method`. The default is the first supported method in a fixed list, except that Linux and FreeBSD use `fdatasync`. On macOS that rule picks `open_datasync`. Verified from the PostgreSQL 14 and 18 docs, section 20.5 and 19.5, and from `xlogdefs.h` at REL_14_0. A fresh PostgreSQL 14.24 cluster on the M4 Pro showed `open_datasync` with source `default`. That was a Homebrew x86_64 build under Rosetta. The PostgreSQL docs, section 28.1, say that on macOS you set `fsync_writethrough` to prevent write caching. `pg_test_fsync -s 3` from PostgreSQL 14.24 on the same Mac measured this, one 8 kB write per operation:

| `wal_sync_method` | ops/sec | µs per op | flushes the drive cache |
|---|---|---|---|
| `open_datasync`, the macOS default | 45,480 | 22 | no |
| `fdatasync` | 42,027 | 24 | no |
| `fsync` | 40,138 | 25 | no |
| `fsync_writethrough` | 250 | 3,994 | yes, inferred |
| `open_sync` | 42,435 | 24 | no |
| write, no sync | 333,548 | 3 | no |

The "yes, inferred" comes from `HAVE_FSYNC_WRITETHROUGH` in PostgreSQL's `darwin.h` and from the 3,994 µs, which matches `F_FULLFSYNC`. The PostgreSQL 18 default on macOS is inferred to be `open_datasync` too, from the same source logic at REL_18_0, and not run.

So a default PostgreSQL 14 on your Mac commits in about 22 µs. Those commits do not survive a power cut. That is fine for a development laptop. It is a wrong model for a production server.

**Disks that report early.** `F_FULLFSYNC` asks the drive to flush. It cannot make the drive do it. The PostgreSQL 18 docs, section 28.1, warn about consumer drives. Their write-back caches often do not survive a power failure. They add that many SSDs do not honor cache flush commands by default. The best measurement is older. Zheng, Qin, Tucek and Lillibridge published it at USENIX FAST 2013. They cut the power to 15 SSDs of 10 models from 5 vendors, with flushes issued. 13 of the 15 showed failures. Only two SSDs of one model, and one enterprise hard disk, behaved as the flush promised. Verified from the paper, abstract and section 1. The drives date from about 2012, and modern NVMe drives were not tested. So a flush is a request, and only a power-cut test of the device you own shows what it does.

**Checking the flush path on a Linux server.** Production runs on Linux, so here are the checks for the case above. The Linux block layer marks a cache flush as `REQ_PREFLUSH`. It marks a write that must reach stable media as `REQ_FUA`, forced unit access. For a device that reports no volatile write cache, the block layer completes empty `REQ_PREFLUSH` requests itself, before the driver. Verified from the kernel document `block/writeback_cache_control`. So fsync is cheap on such a device, and it is safe only if the device really keeps its cache through a power loss. Enterprise SSDs with power-loss protection, PLP for short, are sold as keeping their cache through a power loss. That claim, and that PLP drives report no volatile cache to Linux, were not checked. A RAID controller with a battery-backup unit, BBU, keeps its cache in a power loss too. These are the checks, all for Linux:

| What you check | Command | What it tells you | Source |
|---|---|---|---|
| the kernel's view of the drive cache | `cat /sys/block/nvme0n1/queue/write_cache` | `write back` or `write through`. Writing to the file changes only the kernel's view, not the device | kernel ABI, `sysfs-block` |
| a SATA drive's cache | `hdparm -I /dev/sda` | a `*` next to "Write cache" means it is on | PG 18 docs, 28.1 |
| a SCSI or SAS drive's cache | `sdparm --get=WCE /dev/sdb` | whether the write cache is enabled | PG 18 docs, 28.1 |
| the real flush cost | `pg_test_fsync -f /path/on/the/wal/disk/test.out` | the time per sync method, on the WAL file system | PG 18 docs, `pg_test_fsync` |
| whether flushed data survives | `diskchecker.pl`, with a real power cut | the docs name it as a test of reliable I/O | PG 18 docs, 28.1 |

The kernel document warns about one change. Setting `write_cache` from `write back` to `write through` "will also eliminate cache flushes issued by the kernel." Verified from the `sysfs-block` ABI file. So a drive with a volatile cache then gets no flush commands, and fsync returns while the data is still in that cache.

**Network file systems, direct I/O and cloud volumes.** Three more places hide a weaker flush:

- **NFS.** The PostgreSQL 18 docs, section 18.2.2.1, require the `hard` mount option. They also recommend the `sync` export option on the server. Without it, an fsync on the client "is not actually guaranteed to reach permanent storage on the server". The docs compare that to running with `fsync` off.
- **`O_DIRECT`.** It moves data straight between user memory and the device, past the page cache. The Linux `open(2)` man page says it "does not give the guarantees of the O_SYNC flag". So direct I/O alone is not a durable write, and a store that uses it still needs a sync. PostgreSQL 16 stopped using direct I/O for the `open_sync` and `open_datasync` methods with `wal_level=minimal`, the only case that used it. It is now behind the developer setting `debug_io_direct=wal`. Verified from the 16.0 release notes and from `get_sync_bit` in `xlog.c` at REL_14_0. PostgreSQL 18 added asynchronous I/O, set by `io_method`. The 18.0 release notes list reads only, such as sequential scans and vacuum. So it does not change the commit path, which is inferred from that list.
- **Cloud block volumes.** What a flush on a cloud volume promises was not checked. No first-party statement was found for Amazon EBS or Google Persistent Disk. Treat it as a question for your provider, and test it.

**Linux: the error that a retry hides.** Craig Ringer reported a problem on the pgsql-hackers list in March 2018. PostgreSQL retried fsync after an I/O error. He found that the retry succeeded because the first failed fsync had cleared the error flag. The data was gone, and the second fsync reported success. Verified from the thread, sent 2018-03-28. This became known as fsyncgate. Rebello and others measured it at USENIX ATC 2020, on Linux 5.2.11. After a failed fsync, ext4, XFS and Btrfs all mark the failed pages clean. So a retry does not write them again. ext4 and XFS keep the new data in the page cache. So a read still returns it, while the disk does not have it. Btrfs goes back to the old data. ext4 in `data=journal` mode reports the error one fsync late. Verified from the paper, Table 1 and section 3.3. In the same study, Redis 5.0.7 did not check the return code of fsync at all.

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

PostgreSQL fixed this in five releases on 2019-02-14: 11.2, 10.7, 9.6.12, 9.5.16 and 9.4.21. By default, the server now raises a PANIC on a failed data file flush instead of retrying. A new parameter, `data_sync_retry`, restores the old behaviour. Its default is `off`, and the docs for versions 14 and 18 describe it the same way. Verified from the five release notes and both docs pages. A fresh 14.24 cluster on the M4 Pro showed `data_sync_retry = off`, source `default`. After the PANIC, crash recovery replays the WAL and rewrites the data pages. Linux also changed in version 4.13. Since then, a write-back error is reported to every file descriptor that might have written the data. Verified from the Linux `fsync(2)` man page. Rebello's tests ran on Linux 5.2.11, after this change, and still found the clean pages. So the PANIC rule still applies.

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

**The mental model.** A torn write, also called a partial write, is a write that only partly reached the disk. The device writes in units called sectors, and a large write spans many of them. The PostgreSQL 18 docs, section 28.1, say sectors are commonly 512 bytes. They add that PostgreSQL usually writes 8,192 bytes, or 16 sectors, at once. A power loss can leave some of those sectors written and others not. SQLite's document on atomic commit, section 2, says SQLite has long assumed that a single sector write is not atomic.

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

**How PostgreSQL handles a torn data page.** PostgreSQL protects its 8 kB data pages in a different way. `full_page_writes = on` is the default in versions 14 and 18. With it, the first change to a page after a checkpoint writes the whole page into the WAL. That copy is called a full page image. If a crash tears that page on disk, replay writes the full image back. Verified from the PostgreSQL 14 and 18 docs, `runtime-config-wal`. The docs allow turning it off only on a file system that prevents partial page writes. Their example is ZFS.

There is direct evidence of what happens when it is off. Ramos and others built LazyFS, a file system that runs as a normal program. It uses FUSE, the interface that lets a user program act as a file system. It has its own page cache, and it can lose or tear writes on command. They tore a PostgreSQL data page write, with the full page setting off and on, on PostgreSQL 12.11 and 15.2. The paper describes the setting and cites the `full_page_writes` docs. In both cases the server restarted without an error. With the setting off, the `amcheck` module, which checks the structure of tables and indexes, then reported corruption. Verified from "When Amnesia Strikes", PVLDB volume 17, issue 11, 2024, the paragraph "Protection and recovery" and the table of systems. Section 1.7 uses LazyFS again as a test tool.

**The same problem in InnoDB.** MySQL's InnoDB solves the torn page differently. It writes each page flushed from the buffer pool to a doublewrite buffer first, and only then to its place in the data file. After a crash during a page write, InnoDB "can find a good copy of the page" in that buffer. The MySQL 8.4 manual says it is enabled by default in most cases, and it does not give the exact default per platform. Verified from the manual's page "Doublewrite Buffer". So PostgreSQL copies the page into the WAL, and InnoDB copies it into a second file. Both pay one extra page write. Some cloud devices remove the problem at the device. AWS documents torn write prevention for EC2, which writes a block all or nothing. AWS says this removes the need for the doublewrite buffer. It states that transactions per second can rise by up to 30 percent, and write latency can fall by up to 50 percent. Verified from the EC2 User Guide page "Torn write prevention". The supported block sizes and volume types were not checked, because that sub-page did not load.

Data checksums are a separate feature. They detect a damaged data page when it is read. PostgreSQL 18 turned them on by default in `initdb`. The 18.0 release notes, dated 2025-09-25, list this change under incompatibilities, with `--no-data-checksums` to turn them off. PostgreSQL 14 has them off by default. PostgreSQL 14 reaches its final release on 2026-11-12, per the PostgreSQL versioning page. The release notes also say that `pg_upgrade` needs matching checksum settings in the old and new clusters. So a 14 cluster made with default settings needs a decision before it moves to 18. E11 shows how to check your cluster.

What checksums cover, and what they cost, decides that choice. In both versions, only data pages are covered, and internal structures and temporary files are not. Verified from the docs of both versions and the 18.0 release notes. Rogov, section 11.2, page 187, names three more limits. A page is checked only when it is read, so damage can sit unseen until it reaches every backup. A zeroed page counts as valid. And only the main fork of each table is covered, not files such as `pg_xact`. Checksums also cost WAL. With them on, "hint bit updates are always WAL-logged", per the PostgreSQL 18 docs, section 19.5. A hint bit is a cached flag in a row that saves later readers a lookup, and Phase 3 explains it. So the 18 default writes more full page images than the 14 default. That is inferred from the docs line, and its size is not measured here. A checksum failure shows in two places. `pg_stat_database.checksum_failures` counts them, per the PostgreSQL 18 docs, section 27.2. The log shows a warning that starts "page verification failed, calculated checksum", then an error "invalid page in block 0 of relation", in Rogov's example on page 188.

**The lab entry against a PostgreSQL WAL record.** A PostgreSQL WAL record solves the same problems as the lab's entry, with different fields. The header fields are from `xlogrecord.h` at tag REL_18_0, lines 41 to 53. The header is 24 bytes, against the lab's 20:

| The job | Lab entry, `kvlog.py` | PostgreSQL WAL record | Source |
|---|---|---|---|
| length | `ksz` and `vsz`, 4 bytes each | `xl_tot_len`, the length of the whole record | `xlogrecord.h` |
| checksum | `crc32`, IEEE CRC-32 over the bytes after it | `xl_crc`, a CRC-32C on every record | `xlogrecord.h`, PG 18 docs 28.1 |
| order | `seq` must be the next number | `xl_prev` must be the LSN of the record before. Else "record with incorrect prev-link" | `xlogreader.c` REL_18_0 line 1166 |
| end of log | `impossible lengths ksz=0 vsz=0` | "invalid record length at ...: wanted 24, got 0" in 14 and 15. "expected at least 24, got 0" since 16 | Rogov p. 175, `xlogreader.c` at REL_15_0 and REL_16_0 |

The order check matters for one reason the lab does not have. PostgreSQL recycles old WAL files by renaming them, per Rogov, page 178. A recycled file still holds old records with valid CRCs. The reader refuses them by the `xl_prev` check, and by the page address check, "unexpected pageaddr", at line 1331 of `xlogreader.c`. The lab's sequence check does the same job for its own log. That match is inferred from the reader code. The wording change of the end-of-log message in the table was verified by comparing `xlogreader.c` at REL_15_0 and REL_16_0.

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

PostgreSQL states the rule this way. Crash recovery looks at the latest checkpoint record to find the redo point in the WAL, and starts there. Changes made before that point are already on disk. Verified from the PostgreSQL 18 docs, section 28.5, and the version 14 docs, section 30.5. The ARIES paper, section 6, describes a restart as three passes in order: analysis, redo and undo. Undo removes the changes of transactions that never committed. The lab store has no undo pass. One put is one entry, and it either passes its CRC or it is not there. PostgreSQL has no undo pass either, per Rogov, section 10.4, page 174. An unfinished transaction never gets a commit bit in `pg_xact`, so readers treat its rows as aborted. Phase 3 shows how they do that.

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

- **Start.** The checkpointer notes the current WAL insert position. That LSN is the checkpoint's REDO point. Then it tags every buffer that is dirty at that moment. Tagging needs no I/O, so it is fast.
- **Writing.** It writes the tagged buffers to the data files, at a rate that ends the work after the configured fraction of the interval. Pages dirtied after the start are not tagged, so this checkpoint ignores them. A backend that writes a tagged buffer first also clears its tag.
- **Completion.** When every tagged buffer is written, the checkpointer writes a checkpoint record to the WAL, which holds the REDO point. Then it updates `pg_control`, the small file in `global/` that tells the startup process where to begin. The postmaster is the first process of the server. At start it launches the startup process, which runs recovery, per Rogov, page 173. Until then, `pg_control` keeps the previous checkpoint.

So the guarantee is narrower than "every change before the checkpoint is on disk". Every change before the REDO point is on disk, and that counts only once the checkpoint has completed. Rogov states the second half plainly: only from completion does the start of the checkpoint become the new starting point of recovery. CMU 15-445 calls this design a fuzzy checkpoint, because transactions keep running during it. Its Fall 2025 notes for Lecture 22 mark the two ends with a CHECKPOINT-BEGIN and a CHECKPOINT-END record. PostgreSQL writes no record at the start. So its REDO point can be the LSN of a record of any type, per Rogov, page 171.

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

The worst case is the crash at 4:29, right before a checkpoint completes. At the defaults that is up to 1 + 0.9 = 1.9 intervals of WAL. Rogov gives the same multiplier for the WAL a server must keep: the WAL between two checkpoints times 1 + `checkpoint_completion_target`. Verified from Rogov, section 10.6, page 177. The docs name the cost of the long spread. Prolonging checkpoints "affects recovery time", because more WAL must be kept for recovery. Verified from the PostgreSQL 18 docs, section 28.5.

**When a checkpoint starts.** PostgreSQL starts a checkpoint every `checkpoint_timeout`. It also requests one early when the WAL grows too fast. The defaults are the same in versions 14 and 18:

| Setting | Default | What it does |
|---|---|---|
| `checkpoint_timeout` | 5 min | time between automatic checkpoints |
| `max_wal_size` | 1 GB | the WAL size that the size trigger is computed from |
| `min_wal_size` | 80 MB | WAL kept for reuse |
| `checkpoint_completion_target` | 0.9 | spread checkpoint writes over 90% of the interval |
| `checkpoint_warning` | 30 s | log a warning if size-triggered checkpoints come closer than this |

Verified from the docs of both versions, and from a fresh 14.24 cluster for the first four. The size trigger is not `max_wal_size` itself. `CalculateCheckpointSegments` at `xlog.c` line 2172, REL_18_0, divides it by 1 + `checkpoint_completion_target`. The same division is in REL_14_0. Here is the arithmetic at the defaults:

- **Step 1.** `max_wal_size` is 1,024 MB, or 64 WAL segments of 16 MB each. A WAL segment is one file in `pg_wal`.
- **Step 2.** 64 / 1.9 = 33.7, which the code rounds down to 33 segments.
- **Step 3.** So a checkpoint is requested after about 33 × 16 = 528 MB of WAL since the last REDO point.
- **Step 4.** While it runs, the server writes about 0.9 × 528 = 475 MB more.
- **Step 5.** So when it completes, the WAL since the old REDO point is about 528 + 475 = 1,003 MB, close to `max_wal_size`.

That is the reason for the division, as the code comment explains. The docs also call `max_wal_size` "a soft limit". Heavy load, a failing archive command, or a high `wal_keep_size` can push the WAL past it. Verified from the PostgreSQL 18 docs, section 19.5.2.

**The other side of the trade: full page images.** Section 1.4 showed why the first change to a page after a checkpoint writes the whole page into the WAL. That rule turns a short checkpoint interval into a cost, because more changes become first changes. The docs say that a smaller checkpoint interval "increases the volume of output to the WAL". That partly cancels the goal of the smaller interval, and it causes more disk I/O. Verified from the PostgreSQL 18 docs, section 28.5. Rogov measured the size with `pgbench`, PostgreSQL's benchmark tool, right after a checkpoint, when every page change is a first change:

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

Rogov's cluster had data checksums on, as his section 11.2 shows. In the first run, 93.78% of the page image bytes were in records of the XLOG resource manager, not of the table resource manager. Those are likely the hint-bit images that checksums cause, from section 1.4. That is inferred from the record type, and not checked. `wal_compression` compresses page images only, and it is off by default. In PostgreSQL 14 it is on or off, and on means `pglz`. Since PostgreSQL 15 it accepts `pglz`, `lz4` and `zstd`, if the server was built with them. Verified from the 14 and 18 docs, sections 20.5 and 19.5, and the 15.0 release notes. The view `pg_stat_wal`, since PostgreSQL 14, counts page images in `wal_fpi` and WAL bytes in `wal_bytes`. Phase 2 computes the page image cost per change for a B-tree, so this phase does not repeat that model.

So the checkpoint interval trades three costs. A long interval means a longer redo. A short one means more page images, more WAL to archive and send to replicas, and more page writes.

**Restart time is redo plus one more checkpoint.** After crash recovery, PostgreSQL runs one immediate checkpoint before it opens. The details differ by version:

- **PostgreSQL 18.** The startup process requests `CHECKPOINT_END_OF_RECOVERY | CHECKPOINT_IMMEDIATE | CHECKPOINT_WAIT`. This is in `PerformRecoveryXLogAction`, `xlog.c` line 6358 at REL_18_0. The source says the checkpoint is "created before anyone is allowed to write WAL", at line 7024.
- **PostgreSQL 14.** The startup process runs it itself, with `CreateCheckPoint` at line 7923 of `xlog.c` at REL_14_0. The checkpointer runs during crash recovery only since PostgreSQL 15, per the 15.0 release notes.
- **After a standby is promoted.** PostgreSQL writes only an end-of-recovery record, and the checkpoint comes later.

Rogov describes the same step: the checkpoint secures the recovered state on disk, section 10.4, page 174. The checkpoint is immediate, so it is not spread out. Its length grows with the pages that redo dirtied. That is inferred from the `CHECKPOINT_IMMEDIATE` flag, and not measured. So a recovery-time target has two parts: the redo, and this checkpoint.

**How long the redo takes.** One measurement gives WAL size and redo time together. Christophe Pettus published it on 2026-09-29, on PostgreSQL 18.6. The crash was a kill of the postmaster. He gives no hardware details, and the post is less than three weeks old:

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

So the answer to the question above is about 5 to 10 seconds, on that unnamed machine. WAL made of full page images replayed faster per megabyte in his test. 682 MB in 1.5 s is 455 MB per second. 1,080 MB in 6.0 s is 180 MB per second. The likely reason is that each record is a plain page copy. That reason is inferred from the record type, and not checked. Pettus does not say whether his times include the end-of-recovery checkpoint, and this course did not test it. Redo time also depends on `recovery_prefetch`, added in PostgreSQL 15 with the default `try`. It reads ahead the blocks that the next WAL records need. Verified from the 15.0 release notes and the PostgreSQL 18 docs, section 19.5.4. So a redo timing means something only with its version and this setting.

Stormatics published a production postmortem on 2026-07-01, about PostgreSQL 16.8 on Kubernetes. The checkpointer stayed active for more than four hours without finishing. After a forced restart, the server had to replay several hours of WAL. The bug was fixed in 16.10. The post gives no WAL size and no replay time. It shows the REDO point rule from the other side. A checkpoint that never completes never moves the starting point of recovery, so nothing bounds the redo.

**The signals to read on a real server.** The lab prints `RecoveryReport.seconds`. A PostgreSQL server gives the same facts in its log, in two views, and in one tool:

| Signal | What it shows | Version | Source |
|---|---|---|---|
| `log_checkpoints` | a "checkpoint starting" line, then a "checkpoint complete" line with buffers written, write, sync and total seconds, `distance` and `estimate` | off by default in 14, on since 15. `lsn` and `redo lsn` fields since 16 | PG 14 docs 20.8, PG 18 docs 19.8, 15.0 and 16.0 release notes, `xlog.c` REL_18_0 line 6794 |
| `checkpoint_warning` | "checkpoints are occurring too frequently (N seconds apart)", with the hint to raise `max_wal_size` | 14 and 18 | `checkpointer.c` REL_18_0 line 458, PG 18 docs 19.5 |
| `pg_stat_bgwriter` | `checkpoints_timed` and `checkpoints_req`: scheduled and requested checkpoints that completed. Many requested ones mean `max_wal_size` is too small | 14 to 16 | PG 14 docs Table 28.21, Rogov p. 181 |
| `pg_stat_checkpointer` | `num_timed`, `num_requested` and `num_done`. The first two also count skipped checkpoints, and `num_done` counts completed ones only | view since 17, `num_done` since 18 | 17.0 and 18.0 release notes, PG 18 docs Table 27.25 |
| `pg_stat_wal` | `wal_fpi` and `wal_bytes` since the last reset | since 14 | PG 14 docs Table 28.22 |
| `pg_controldata` | "Database cluster state", "Latest checkpoint location" and "Latest checkpoint's REDO location" | all versions | Rogov pp. 172 to 175 |
| startup log | "redo starts at", "redo done at" with elapsed time, the end-of-WAL line, and since 15 "redo in progress, elapsed time" every `log_startup_progress_interval`, default 10 s | 14 and 18 | `xlogrecovery.c` REL_18_0 lines 1748, 1761 and 1883, 15.0 release notes |

Here is what the lines look like. These recovery lines are from Rogov's PostgreSQL 14.7 example, page 175, after `pg_ctl stop -m immediate`. `log_checkpoints` was off there, so the end-of-recovery checkpoint does not appear:

```
LOG: database system was interrupted; last known up at 2023-03-06 14:01:49 MSK
LOG: database system was not properly shut down; automatic recovery in progress
LOG: redo starts at 0/3E7EF7E0
LOG: invalid record length at 0/3E7EF890: wanted 24, got 0
LOG: redo done at 0/3E7EF818 system usage: CPU: user: 0.00 s, system: 0.00 s, elapsed: 0.00 s
LOG: database system is ready to accept connections
```

The "invalid record length" line is the normal end of the WAL, not an error, as the table in section 1.4 showed. "redo starts at" names the REDO point from `pg_control`. Here is Rogov's checkpoint line on PostgreSQL 14.7, page 180, after a manual `CHECKPOINT`:

```
LOG: checkpoint starting: immediate force wait
LOG: checkpoint complete: wrote 4100 buffers (25.0%); 0 WAL file(s) added, 1 removed, 0 recycled; write=0.076 s, sync=0.009 s, total=0.099 s; sync files=3, longest=0.007 s, average=0.003 s; distance=9213 kB, estimate=9213 kB
```

`distance` is the WAL between the starts of the last two checkpoints, in kB. In PostgreSQL 18 the same line also prints SLRU buffers written, which are the cached pages of small files such as `pg_xact`. Verified from the 18.0 release notes and `xlog.c` at REL_18_0, line 6794. An end-of-recovery checkpoint logs "checkpoint starting: end-of-recovery immediate" on 14, and adds " wait" on 18. That is inferred from the flag names in `LogCheckpointStart` of both versions, and not run.

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

**PostgreSQL's version.** PostgreSQL forms groups inside `XLogFlush`, the function of step 2 in the commit order of section 1.2. A committer tries to take `WALWriteLock` with `LWLockAcquireOrWait`, at `xlog.c` line 2855, REL_18_0. If another backend holds the lock, this one waits until the lock is free. Then it does not take the lock at once. It first checks whether the holder already flushed past its own commit record. If so, it returns without a sync. That is the lab's `_wait_durable`, where a follower returns when `synced_to` covers its entry. Verified from the code and its comment, which says this "helps to maintain a good rate of group committing".

Two settings make groups larger. `commit_delay`, default 0 µs, makes the leader sleep before it flushes, if at least `commit_siblings` other transactions are active. `commit_siblings` defaults to 5. Since PostgreSQL 9.3, only the leader waits for the delay, and the others wait for its flush. Verified from the docs of versions 14 and 18. The PostgreSQL 18 docs, section 28.5, add two points. At higher client counts a "gangway effect" forms groups even with a delay of 0, so the setting helps less there. And a good first value is half the time that `pg_test_fsync` reports for one flush after an 8 kB write. The lab's `--group-delay-us` flag is the same idea.

**Measured, on two machines from two sources.** Laurenz Albe of CYBERTEC measured `commit_delay` on PostgreSQL 17 in January 2025. The machine was an ASUS ZenBook notebook with NVMe and Fedora 40. The disk was limited to 1,000 write IOPS on purpose. The load was `pgbench -b simple-update -c 10` for 1,200 seconds:

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

Vadim Tkachenko of Percona measured the InnoDB group commit fix in July 2011, on 8 spinning disks in RAID 10. Without a controller cache, the fix raised throughput to 1,669.11 at 256 threads, against at most 57.62 before, about 29 times. With a battery-backed cache, one thread already reached 352.83 without the fix, so group commit matters most when each sync is slow. The article does not state the unit, which is probably transactions per second.

**The other way: give up durability.** Each store below can reply before the log is durable. Each one names its own loss window:

| System and setting | When it replies | What a crash can lose | Source |
|---|---|---|---|
| PostgreSQL `synchronous_commit=off` | before the WAL flush | up to 3 × `wal_writer_delay`, 600 ms at the default | PG 18 docs, 19.5 |
| PostgreSQL `fsync=off` | never syncs | not a window: "unrecoverable data corruption in the event of a power failure or system crash" | PG 18 docs, 19.5 |
| MySQL `sync_binlog=0` | without a sync of the binary log | committed transactions missing from the binary log, after a power failure or OS crash | MySQL 8.4 manual |
| MariaDB `innodb_flush_log_at_trx_commit=0` | before the log write | about the last second | MariaDB docs |
| MariaDB `innodb_flush_log_at_trx_commit=2` | after the log write, before the flush | about the last second, on an OS crash or power loss | MariaDB docs |
| Redis `appendfsync everysec`, the default | before the fsync | about 1 second, per the docs | Redis persistence docs |
| NATS JetStream, the default `sync_interval` | before the fsync | up to 2 minutes | Jepsen NATS 2.12.1, 3.4 |

The Redis row has one more detail. The docs say one second. The source in `src/aof.c` on the unstable branch can postpone a write for up to two seconds. It does so while a background fsync is still running. So the window can be longer than one second. That is inferred from the code and not tested. One more measurement shows the size of the gain. Kaarel Moppel of CYBERTEC measured, in 2016, 4,256 TPS with `synchronous_commit=on` and 6,211 TPS with `off`. The setup was two AWS i2.xlarge instances with asynchronous streaming replication, and `pgbench` with 8 clients for 10 minutes. With asynchronous replication the primary does not wait for the standby, so the setting changed only the local WAL wait. That last point is inferred from the PostgreSQL docs on `synchronous_commit`. The PostgreSQL version is not named.

So turning durability off gave 6,211 / 4,256 = 1.46 times in that test. Rogov ran a smaller test on PostgreSQL 14.7, with `pgbench`, 1 client and 30 seconds. He measured 670.8 TPS with `synchronous_commit` on and 2,060.4 TPS with it off, which is 3.07 times. Verified from Rogov, section 11.1, pages 184 and 185. His hardware is not stated in those pages. These ratios and the group commit ratio of 1.74 come from different machines and tests, so they are not compared.

Two rules make this choice less coarse than one global switch:

- **Per transaction.** `synchronous_commit` can be set for one transaction. "The mode used for any one transaction depends on the value of synchronous_commit when transaction commit begins." Verified from the PostgreSQL 18 docs, section 28.4. So a service can commit a payment with `on` and a page-view log with `off`, in the same database.
- **`fsync=off` is a different risk.** Asynchronous commit loses at most the last 600 ms, and the database stays consistent. `fsync=off` can corrupt the database beyond repair, per the docs row above. Rogov makes the same point on page 187. A CI database often runs with `fsync=off`, so its crash behaviour says nothing about production.

MySQL needs two settings for a durable commit, because the binary log is a second log next to the InnoDB log. `sync_binlog` defaults to 1. For the greatest durability with InnoDB, the MySQL 8.4 manual lists `sync_binlog=1` together with `innodb_flush_log_at_trx_commit=1`. Verified from the manual's page "Binary Logging Options and Variables". Replicas read the binary log, which is course 5.

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

**How other systems state it.** Each sentence below covers one node only. What a replica has when the leader replies is in Phase 3 of course 5.

| System | The documented boundary, paraphrased | Source |
|---|---|---|
| PostgreSQL 18, `synchronous_commit=on` | every mode except `off` waits for the local WAL flush before it replies | PG 18 docs, 19.5 |
| SQLite, WAL mode, `synchronous=NORMAL` | stays consistent, but a commit can roll back after a power loss or OS crash. Commits survive an application crash in every mode | sqlite.org, `PRAGMA synchronous` |
| SQLite, WAL mode, `synchronous=FULL` | durable: one more sync of the WAL file after each commit | same page |
| MySQL 8.4, InnoDB with binary logging | durable with both settings of section 1.6 at 1. Other values can lose commits in a power failure or OS crash | MySQL 8.4 manual |

The Redis and NATS defaults are in the table of section 1.6. The SQLite rows depend on the journal mode, so the mode must be in the sentence. The default journal mode is the rollback journal, not WAL. Verified from sqlite.org, "Write-Ahead Logging". WAL mode is chosen with `PRAGMA journal_mode=WAL`.

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

The expected result for the default run is 0 violations in 231 recoveries, with all 60 torn cases detected. These counts are worked out from the code and were not run. The self-test asserts them, so the first run of `--self-test` checks this arithmetic.

**The one place the boundary does not hold.** Remove the directory sync after the log is created, with `--skip-dir-sync`. The log file's bytes are synced, but its name is not. In `fsim.py`, a name becomes durable only through a directory sync. The checkpoint's step 5 is the first one. A power loss or OS crash between the first acknowledgment and that step finds no log. Recovery then starts an empty store. That window is crash points #7 to #26: 26 − 7 + 1 = 20 points. So the expected result, worked out from the code and not run, is 20 power violations and 20 OS violations.

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

**A second break, from a wrong sentence.** Run the store with `--sync fsync` on the darwin model, and add `--claim-power-safe`. That flag checks the sentence most Python code would claim: an acknowledged put survives a power loss. The expected result, worked out from the code and not run, is 42 power violations and 0 OS violations. There are 0 OS violations because the model keeps the drive cache in an OS crash. The 42 come from crash points #7 to #22, which is 16, and #32 to #57, which is 26. Between them, the checkpoint's full syncs made the log durable up to operation 4. That is the running case of this phase, found by a test.

**What a kill test can and cannot show.** `--real-kill` runs the same workload in a child process on real files. It sends `SIGKILL` at each of the 57 crash points. The expected result is 0 violations in every sync mode, `--sync none` too. Section 1.1 gave the reason. The count is worked out, not run. A real kill test is still worth running. It tests the real file calls, the real `O_APPEND` writes and the real rename, which the model does not. It cannot test power.

**A real postmortem about crash testing.** The etcd project published the "v3.5 data inconsistency postmortem" on 2022-04-20. A refactor in v3.5.0 stopped saving the consistent index atomically with the data it describes. A crash between the two writes left a member inconsistent. The maintainers reproduced it under heavy load by killing one member with SIGKILL at random. The postmortem notes that it was reproduced only because one maintainer had `/tmp` on a normal disk. The bug was merged on 2021-05-08 and fixed in v3.5.3 on 2022-04-24, which is 351 days. Verified from the postmortem's dates, and the day count is arithmetic. The postmortem does not say why the disk mattered. A likely reason is that a real device makes each write slower, which widens the window between the two writes. That reason is inferred, not checked. A test on a memory file system, such as a tmpfs `/tmp` on Linux, never reaches a device at all. So `shared/durable.py` refuses to measure there.

**Testing a real system's boundary.** The crash matrix tests a model, and a kill test tests only process crashes. These tools sit between the two. Each one runs the real program on a device or file system that can lose writes on command. Device-mapper is the Linux layer that builds virtual block devices on top of real ones, and two of the tools are device-mapper targets:

| Tool | What it does | Source |
|---|---|---|
| LazyFS | a FUSE file system with its own page cache. A `clear-cache` fault drops unsynced data at a chosen call, and `torn-op` and `torn-seq` tear writes | LazyFS README, GitHub `dsrhaslab/lazyfs` |
| LazyFS, results | used on seven systems, PostgreSQL, etcd, ZooKeeper, Redis, LevelDB, PebblesDB and Lightning Network. It found eight new bugs | Ramos and others, PVLDB volume 17, issue 11, 2024, abstract |
| `dm-log-writes` | a device-mapper target that logs each write in order of completion. It logs a write only at the next flush, so a replay shows what was on disk, not in cache | kernel docs, device-mapper "log-writes" |
| `dm-flakey` | a device-mapper target with `drop_writes`, `error_writes` and `corrupt_bio_byte`. `error_writes` is a real kernel version of the failed fsync in E9 | kernel docs, device-mapper "dm-flakey" |
| `diskchecker.pl` | the device test of section 1.3, with a real power cut | named in PG 18 docs, 28.1 |

LazyFS, `dm-log-writes` and `dm-flakey` are Linux tools. The LazyFS README says it was tested with ext4 on Debian 11 and Ubuntu 20.04. On a Mac they need a Linux virtual machine. Whether LazyFS works with macFUSE was not checked, and neither was the platform support of `diskchecker.pl`. With these tools, the crash matrix of this phase becomes a test plan for a real service. Run the service on LazyFS or `dm-log-writes`, crash it at each write step, and check recovery against the sentence.

**What the boundary leaves out, on purpose.** The sentence covers crashes, not an operator who deletes data or backups that do not restore. The GitLab.com outage of 2017-01-31 was that case: an engineer wiped the primary database's data directory, and the backups had failed, per GitLab's postmortem of 2017-02-10. Recovery from deletion needs its own plan.

**The sentence to remember:** state what an OK survives, what recovery returns and what is not covered. Back each part with a crash matrix that fails if the part is false.

**The trap:** a boundary that nobody tested. The store with `--skip-dir-sync` passes every kill test. It loses everything in a 20-step window that only an OS-crash or power-loss model, a tool such as LazyFS, or a real power cut shows.

**Try this now:** run `uv run python phase01_durability/crash_matrix.py --skip-dir-sync`. Predict the first violation line before you run it, then compare it with the diagram above.

---
## 🧪 Hands-on lab

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
  - Expected: Not run by the author yet. Four lines `self-test passed`. The first store run prints `recovery: new store, log created`, the boundary sentence, and two `OK put` lines. The first is `bytes 0..34`: 20 header bytes, 10 key bytes and 4 value bytes. The second run prints `2 entries replayed` and `get order:1041: paid`.
  - Teaches: the boundary sentence is printed by the code that the matrix tests.

- [ ] **E5 (offline).** The crash matrix with the stated boundary. This is the main demonstration.
  - First write your prediction: the number of crash points, the number of recoveries, and the number of violations.
  - Run: `uv run python phase01_durability/crash_matrix.py`.
  - Expected: Not run by the author yet. `Dry run: 57 crash points`. Rows `process 57`, `os 57`, `power 57`, `torn-short 50`, `torn-hole 10`, each with `0` violations. The torn rows show `50` and `10` in the `torn detected` column. Last line: `RESULT: 0 violations in 231 recoveries. The stated boundary held.` Section 1.7 shows the arithmetic.
  - Teaches: a boundary is backed by a test that checks every write step against it.

- [ ] **E6 (break-it, offline).** Remove the directory sync after the log is created.
  - Run: `uv run python phase01_durability/crash_matrix.py --skip-dir-sync`.
  - Expected: Not run by the author yet. `process` 0 violations, `os` 20, `power` 20. The torn rows have fewer cases, 30 and 6, because the log's name is not durable until crash point #27. The first violation line: `#7 put.acked, os: acknowledged puts lost: recovered S(0), acknowledged 1`.
  - Teaches: a synced file whose name is not durable can vanish with all its data.

- [ ] **E7 (break-it, offline).** Check the claim that plain fsync is durable on a Mac.
  - Run: `uv run python phase01_durability/crash_matrix.py --sync fsync --claim-power-safe`, then `uv run python phase01_durability/crash_matrix.py --sync fsync`, then `uv run python phase01_durability/crash_matrix.py --sync fsync --platform-model linux`.
  - Expected: Not run by the author yet. With the claim: `power` 42 violations, `os` 0, and violations in the torn rows too. Without the claim: 0 violations, because the honest sentence for `fsync` on macOS promises a process crash only. On the linux model: 0 violations in 231 recoveries, as in E5.
  - Teaches: the same code has a different boundary on each platform, and the sentence must say which.

- [ ] **E8 (break-it, offline).** A torn write, with and without the checksum.
  - Run: `uv run python phase01_durability/kvlog.py --torn-demo`, then `uv run python phase01_durability/crash_matrix.py --no-crc`.
  - Expected: Not run by the author yet. The demo prints the WRONG and RIGHT lines of section 1.4. First 1,200 bytes with 512 zeros, then a stop at offset 1230 with `checksum mismatch`. The matrix with `--no-crc` shows `torn-hole` with 8 violations of 10, and `torn-short` with 0. The 8 are the puts. The 2 deletes are 30 bytes long, and each hole zeroes the whole entry, so the length check stops them.
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

- [ ] **E11 (local, PostgreSQL 14).** Read your own cluster's durability settings.
  - Run: `createdb -h /tmp -p 5432 storage_lab`.
  - Then run: `psql -h /tmp -p 5432 -d storage_lab -c "select name, setting, source from pg_settings where name in ('wal_sync_method','synchronous_commit','full_page_writes','data_checksums','data_sync_retry','commit_delay','commit_siblings','checkpoint_timeout','max_wal_size','wal_writer_delay','checkpoint_completion_target','checkpoint_warning','log_checkpoints','wal_compression') order by name"`.
  - Then run: `psql -h /tmp -p 5432 -d storage_lab -c "select checkpoints_timed, checkpoints_req, stats_reset from pg_stat_bgwriter"`, and `pg_controldata "$(psql -h /tmp -p 5432 -d storage_lab -Atc 'show data_directory')" | grep -E "cluster state|REDO location"`. Both only read.
  - Expected: Not run by the author yet. The research's fresh 14.24 cluster showed `wal_sync_method open_datasync`, `synchronous_commit on`, `full_page_writes on`, `data_checksums off`, `data_sync_retry off`, `commit_delay 0`, `commit_siblings 5`, `checkpoint_timeout 300`, `max_wal_size 1024`, `wal_writer_delay 200` and `checkpoint_completion_target 0.9`. The PostgreSQL 14 docs give `checkpoint_warning 30`, `log_checkpoints off` and `wal_compression off`. A row whose source is not `default` was changed by your configuration. The counters show how many checkpoints were scheduled and requested since `stats_reset`. `pg_controldata` shows `in production` for a running server, and the REDO point of its last checkpoint.
  - Teaches: your laptop's PostgreSQL acknowledges commits that a power cut can remove, has no data checksums, and does not log its checkpoints.

- [ ] **E12 (local).** Time each WAL sync method of PostgreSQL.
  - Run: `pg_test_fsync -s 3 -f ./pg_test_fsync.tmp`, then delete `./pg_test_fsync.tmp` if it is still there.
  - Expected: Not run by the author yet. Compare each line with the M4 Pro table in section 1.3, which this course's research measured with the same command. The line "Direct I/O is not supported on this platform" is expected on macOS.
  - Teaches: the one method that flushes the drive cache on macOS is about 180 times slower than the default. 45,480 / 250 = 182.

- [ ] **E13 (break-it, local, PostgreSQL 14).** Crash a throwaway PostgreSQL cluster, and read its real recovery.
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

---

## 🔍 Check it yourself

- **Check 1.** Open `phase01_durability/kvlog.py:348`. This is the directory sync after the log is created, inside `Store.open`. With `--sync none`, this line does nothing. Why does that not break the boundary that `--sync none` states? Which row of the boundary table in section 1.7 shows it?

- **Check 2.** Open `phase01_durability/kvlog.py:402`. Recovery cuts the torn tail here and then syncs the cut. Suppose the sync on the next line were removed. Describe a second power loss, during the next put, that brings the torn bytes back. Is an acknowledged put lost, or only an unacknowledged one?

- **Check 3.** Open `phase01_durability/kvlog.py:495`. The group commit leader reads `target` before it calls the sync. Suppose it read `target` after the sync returned. Which puts could then return OK before their bytes were covered by a sync? Would any assertion in the self-test of `kvlog.py` catch this change? If not, describe a check that would.

- **Check 4.** Open `phase01_durability/fsim.py:451`. This is where the torn hole is placed. For the 30-byte delete of `order:1042` at offsets 4920 to 4950, compute the sector that this line zeroes. Then explain why `--no-crc` in E8 gives 8 violations and not 10.

- **Check 5.** Open `xact.c` at tag REL_18_0, line 1498, in `RecordTransactionCommit`. This is the test that decides between `XLogFlush` and the asynchronous path. Name the two conditions that force a synchronous flush even with `synchronous_commit = off`. Read the comment above the test, and say why deleting a table's files is one of them.

- **Check 6.** In any repository you own that writes files it must not lose, run `grep -rn "fsync\|F_FULLFSYNC\|\.Sync()" <your repo>/`. For each hit, answer two questions. On macOS, does the call flush the drive cache? And what does the code do when the call returns an error?

---
## ✅ Checkpoint 1 — answer in your own words

The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

1. **Test-out, explain.** Walk through what happens when the store runs `put order:1041` with `--sync full` on a Mac. Name the five crash points of the put in order. For each one, say where the entry is and whether the client has its OK. Also say what a power loss there leaves after recovery. Then say what `F_FULLFSYNC` does not guarantee, even after it returns. Finally, match the steps of the put to the PostgreSQL commit order of section 1.2.

2. **Test-out, predict.** The default workload crashes at point #29, which is `put.written` of operation 5, the delete of `order:1042`. The crash is a power loss, and the drive kept the first 15 bytes of the 30-byte entry. Predict what recovery reads from the checkpoint, and where it starts the log scan. Then predict how many log entries it replays, and where it stops. Then give the recovered contents.

3. **Test-out, demonstrate.** Run E5 and E6. Show that the stated boundary holds in all 231 recoveries. Then explain each of the 40 violations that `--skip-dir-sync` produces, with the arithmetic of the crash points. Finally, run E8 and show the one torn write that the checksum detects and that `--no-crc` serves.

4. **A colleague says:** "Our CI runs on Macs and production runs on Linux with ext4. Both call `os.fsync`, and the crash tests pass on CI. So production is covered." Argue for or against, with the numbers and sources of this phase. Say which crash kind the CI test cannot cover and why, and which one it covers well.

5. **This is broken.** A Linux service writes events to an append-only log and syncs after each event. Its log shows one `EIO` from fsync on Tuesday at 10:00, then a retry that succeeded. The service ran normally. After a reboot on Friday, every event from Tuesday 10:00 onwards is missing, though all of them were acknowledged. What is the cause, and how do you check it? Why are the later events lost too, and not only the one at 10:00?

6. **Show the arithmetic.** On the M4 Pro, `F_FULLFSYNC` took about 4.0 ms. A store has 32 concurrent writers. Compute the upper limit of puts per second with one sync per put, and with group commit. Compute the longest wait of one put with group commit, first with no delay, then with a 1 ms delay. With the delay, what is the new throughput limit, if every batch holds all 32 writers?

7. **Given these constraints, design.** An example: a single-node audit log runs on a Linux server. It must survive a power loss, take 3,000 events per second at peak, and restart within 30 seconds. The SSD's flush takes about 2 ms. Choose the commit mode, the checkpoint rule, and the recovery rule, and write the durability boundary sentence. Show why one sync per event cannot meet the rate.

8. **Recovery time.** Your PostgreSQL 18 server must be back within 20 seconds after a crash. It runs the default checkpoint settings and writes WAL at a peak of 6 MB per second. Compute when a checkpoint is triggered, and the worst-case WAL to replay. Explain why it is more than one checkpoint's worth. Use Pettus's table from section 1.5, with its limits, to estimate the redo time at 5.6 and at 7.7 seconds per GB. Then say what else runs before the server opens, how far you could raise `max_wal_size`, and which signal shows how often size-triggered checkpoints happen.

<details>
<summary>Answer sketches</summary>

1. `put.encoded`: nothing written, no OK, recovery gives the state before the put. `put.written`: the entry is in the page cache, no OK. A power loss loses it, or tears it, and recovery drops it by length or CRC. `put.synced`: `F_FULLFSYNC` returned, so the drive was asked to flush, and the entry survives. No OK yet. `put.indexed`: the same, now visible to readers. `put.acked`: the client has its OK and the entry survives. `F_FULLFSYNC` does not guarantee that the drive honours the flush. Zheng and others found 13 of 15 SSDs that did not behave. It also does not make the file's name durable, which needs the directory sync. In PostgreSQL, `put.written` matches the commit record in the WAL buffers, `put.synced` matches `XLogFlush`, and `put.indexed` matches `ProcArrayEndTransaction`, when other sessions see the rows. PostgreSQL also writes the outcome to `pg_xact` between the last two. With `synchronous_commit = off`, PostgreSQL makes rows visible before the flush, which the lab store never does.

2. The checkpoint is valid and covers 0 to 4920, so the keydir comes from it with the last sequence 4. The log scan starts at 4920 and finds 15 bytes. That is less than the 20-byte header, so `short header, 15 of 20 bytes`. 0 entries are replayed. Recovery stops at 4920, drops 15 bytes, cuts the file and syncs the cut. Contents: S(4), which is `order:1041` v2, `order:1042` v1 and `order:1043` v1. Operation 5 was not acknowledged, so nothing promised is lost.

3. Expected from the code, not run. E5: 57 crash points, 171 + 50 + 10 = 231 recoveries, 0 violations, 60 torn cases detected. E6: from #7, the first acknowledgment, to #26, before the checkpoint's directory sync, the log's name is not durable. That is 26 − 7 + 1 = 20 points. Each fails for the OS crash and for the power loss, so 20 + 20 = 40. E8: the hole in the second put of `order:1041` lies at 1536 to 2048. The CRC catches it. `--no-crc` serves 512 zero bytes.

4. Against. On the Mac, `os.fsync` stops at the drive cache: Apple's `fsync(2)` page. On Linux ext4 with barriers on, fsync makes the file system flush the drive: PostgreSQL 18 docs, 28.1. So the two platforms have different boundaries for an OS crash and a power loss. A crash test that kills processes covers the process kind on both, and nothing more. In E7, the power-loss model of a Mac with `os.fsync` is expected to show 42 violations. The Linux model is expected to show 0. Those counts are worked out from the code, not run. The CI test is right about process crashes and says nothing about power. CI timings also come from a different system call than production, so they do not predict production timings.

5. fsyncgate. The failed fsync marked the pages clean, and the retry reported success for data that was never written. Rebello and others, ATC 2020, Table 1, found this on ext4, XFS and Btrfs. Check: search the service log and `dmesg` for the I/O error at 10:00. Then read the log file at the offset written at that time, and look for zeros or old data. The later events are lost because recovery stops at the first bad entry. Everything after the damaged range is dropped, though it was synced. Fix: stop the process at the first fsync error, never retry, and let recovery run on restart. PostgreSQL has done this by default since 2019-02-14.

6. One sync per put: 1 / 4.0 ms = 250 puts per second. Group commit: at most 32 per sync, so 32 × 250 = 8,000 per second. Longest wait without delay: one sync in progress plus its own, 2 × 4.0 = 8.0 ms. With a 1 ms delay: 1 + 4.0 + 4.0 = 9.0 ms in the worst case. Throughput with the delay: one batch per 1 + 4.0 = 5.0 ms. So 32 / 5.0 ms = 6,400 per second. The delay only helps when batches would otherwise be small.

7. One sync per event: 1 / 2 ms = 500 per second, far below 3,000. Group commit: at 3,000 per second and 2 ms per sync, a batch holds 3,000 × 0.002 = 6 events. That is enough. Commit mode: group commit with the full sync, which is `fsync` on Linux with barriers on. Checkpoint: write the index often enough that the log since the checkpoint replays well within 30 seconds. Measure the scan rate first with `RecoveryReport.seconds`. Recovery: a CRC per entry, and a stop at the first bad entry. Cut and sync the cut. Sync the directory after create and rename. Stop on any fsync error. Boundary: an OK means the event passed a sync that covers it. It survives a process crash, an OS crash and a power loss, on a drive that honours flushes. Recovery returns a prefix and never a damaged entry. Not covered: damage to synced data and loss of the device. This is an example, not measured.

8. The size trigger at the defaults is about 528 MB of WAL since the last REDO point: 64 segments / 1.9 = 33, and 33 × 16 MB = 528 MB. At 6 MB per second that is 528 / 6 = 88 seconds, sooner than the 5-minute timer, so checkpoints are size-triggered. 88 s is more than the 30 s `checkpoint_warning`, so no warning appears. The worst case is a crash right before a checkpoint completes. Recovery then starts at the previous REDO point, because the REDO point counts only after completion. The WAL since then is about 528 + 0.9 × 528 = 1,003 MB, about 1 GB. `max_wal_size` is a soft limit, so a load spike can push it higher. Redo: 1.0 × 5.6 = 5.6 s and 1.0 × 7.7 = 7.7 s. Then the end-of-recovery checkpoint runs, immediate, with a length not measured here. So the target holds with room. Raising `max_wal_size` would cut page images. At 7.7 s per GB, 20 s is 20 / 7.7 = 2.6 GB of replay. So about 2 GB leaves room for that checkpoint and the soft limit. Signals: `num_requested` against `num_timed` in `pg_stat_checkpointer`, and the `distance` of each "checkpoint complete" line. This is a starting point only, with the limits of Pettus's table in section 1.5. Measure on your own hardware, first on a throwaway cluster as in E13.

</details>

---

## References & Further Learning

This course's research fetched every URL below on 2026-10-17. The depth revision of 2026-10-18 added the entries for the PostgreSQL write path, checkpoints, Linux testing, MySQL and AWS, fetched that day. Each URL was checked again with `check_urls.py`. Primary sources come first in each group.

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
- **posixmodule.c, CPython source, tag v3.14.8** — https://github.com/python/cpython/blob/v3.14.8/Modules/posixmodule.c
  Focus on: `os_fsync_impl` near line 3993, which calls the plain `fsync`. CPython issue 56086 asks `os.fsync` to flush the drive. It was still open on 2026-10-17.

### PostgreSQL documentation

- **19.5 Write Ahead Log, PostgreSQL 18** — https://www.postgresql.org/docs/18/runtime-config-wal.html
  Focus on: `wal_sync_method`, `full_page_writes`, `synchronous_commit`, `commit_delay` and the checkpoint settings. Replace 18 with 14 in the URL for your local version, where the chapter is 20.5.
- **28.1 Reliability, PostgreSQL 18** — https://www.postgresql.org/docs/18/wal-reliability.html
  Focus on: drive caches, the macOS `fsync_writethrough` advice, and the 512-byte sectors.
- **28.4 Asynchronous Commit, PostgreSQL 18** — https://www.postgresql.org/docs/18/wal-async-commit.html
  Focus on: the loss window of `synchronous_commit=off`.
- **28.5 WAL Configuration, PostgreSQL 18** — https://www.postgresql.org/docs/18/wal-configuration.html
  Focus on: how crash recovery finds the redo point from the latest checkpoint, the spread checkpoint, the full page cost of short intervals, the "gangway effect" and the `commit_delay` starting value.
- **Error Handling, PostgreSQL 14** — https://www.postgresql.org/docs/14/runtime-config-error-handling.html
  Focus on: `data_sync_retry`.
- **Data Checksums, PostgreSQL 14** — https://www.postgresql.org/docs/14/checksums.html
  Focus on: the default of off, and what checksums cover.
- **PostgreSQL 18.0 release notes, 2025-09-25** — https://www.postgresql.org/docs/release/18.0/
  Focus on: the `initdb` change that enables data checksums by default, listed under incompatibilities.
- **Versioning Policy, PostgreSQL** — https://www.postgresql.org/support/versioning/
  Focus on: the final release date of version 14, 2026-11-12.

### The PostgreSQL write path, checkpoints and recovery

- **PostgreSQL 14 Internals, Egor Rogov, Postgres Professional, 2023** — https://edu.postgrespro.com/postgresql_internals-14_en.pdf
  Focus on: chapter 10, pages 164 to 181, for the LSN, `pg_waldump`, the spread checkpoint and its REDO point, recovery after `pg_ctl stop -m immediate`, and checkpoint monitoring. Chapter 11, pages 182 to 191, for asynchronous commit with `pgbench`, checksums, full page images and `wal_compression`. Every example runs on PostgreSQL 14.7, and the hardware is not stated. A free book, not peer reviewed. Read chapter 10 with section 1.5.
- **PostgreSQL source, tag REL_18_0, `src/backend/access/transam`** — https://github.com/postgres/postgres/tree/REL_18_0/src/backend/access/transam
  Focus on: `xact.c`, `RecordTransactionCommit` from line 1315, for the commit order. `xlog.c`: `CalculateCheckpointSegments` at line 2172, `XLogFlush` at line 2855, `PerformRecoveryXLogAction` at line 6323 and the checkpoint log line at 6794. `xlogrecovery.c` lines 1748 to 1883 for the redo log lines. `xlogreader.c` lines 670, 1166 and 1331 for the end-of-WAL and prev-link checks.
- **9.28 System Administration Functions, PostgreSQL 18** — https://www.postgresql.org/docs/18/functions-admin.html
  Focus on: `pg_current_wal_insert_lsn`, `pg_current_wal_lsn` and `pg_current_wal_flush_lsn`.
- **28.6 WAL Internals, PostgreSQL 18** — https://www.postgresql.org/docs/18/wal-internals.html
  Focus on: the LSN as a byte offset, and how two LSNs give the WAL between them.
- **27.2 The Cumulative Statistics System, PostgreSQL 18** — https://www.postgresql.org/docs/18/monitoring-stats.html
  Focus on: Table 27.25 `pg_stat_checkpointer`, Table 27.26 `pg_stat_wal`, and `checksum_failures` in `pg_stat_database`. For version 14, `pg_stat_bgwriter` is Table 28.21 in the same chapter of the 14 docs.
- **19.8 Error Reporting and Logging, PostgreSQL 18** — https://www.postgresql.org/docs/18/runtime-config-logging.html
  Focus on: `log_checkpoints`, default on, and `log_startup_progress_interval`. The 14 page, section 20.8, gives `log_checkpoints` the default off.
- **pg_waldump, PostgreSQL 14** — https://www.postgresql.org/docs/14/pgwaldump.html
  Focus on: `-p`, `-s`, `-e` and `--stats`, the options E13 uses.
- **pg_ctl, PostgreSQL 14** — https://www.postgresql.org/docs/14/app-pg-ctl.html
  Focus on: the three stop modes. Immediate mode leads to crash recovery at the next start.
- **PostgreSQL 15.0 release notes** — https://www.postgresql.org/docs/release/15.0/
  Focus on: `log_checkpoints` on by default, startup progress messages, `recovery_prefetch`, the checkpointer during crash recovery, and LZ4 and Zstandard for `wal_compression`.
- **PostgreSQL 17.0 release notes** — https://www.postgresql.org/docs/release/17.0/
  Focus on: the new view `pg_stat_checkpointer`, which took the checkpoint columns from `pg_stat_bgwriter`.
- **18.2 Creating a Database Cluster, PostgreSQL 18** — https://www.postgresql.org/docs/18/creating-cluster.html
  Focus on: section 18.2.2.1, "NFS", for the `hard` mount option and the `sync` export option.

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

- **Doublewrite Buffer, MySQL 8.4 Reference Manual** — https://dev.mysql.com/doc/refman/8.4/en/innodb-doublewrite-buffer.html
  Focus on: why InnoDB writes each page twice, and the default.
- **Binary Logging Options and Variables, MySQL 8.4 Reference Manual** — https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html
  Focus on: `sync_binlog`, its default of 1, and the pair of settings for the greatest durability.
- **Torn write prevention, Amazon EC2 User Guide** — https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/storage-twp.html
  Focus on: the first section, which says all-or-nothing writes remove the need for the doublewrite buffer. A vendor page, so its percentages are vendor claims.

### SQLite

- **Atomic Commit In SQLite** — https://www.sqlite.org/atomiccommit.html
  Focus on: section 2 for the hardware assumptions, and section 9.2 for drives that report a flush early.
- **Pragma statements** — https://www.sqlite.org/pragma.html
  Focus on: `PRAGMA synchronous` for the durability of each mode, and `fullfsync` for macOS.
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

### Measurements of group commit and recovery

- **commit_delay for better performance: a PostgreSQL benchmark, Laurenz Albe, CYBERTEC, 2025** — https://www.cybertec-postgresql.com/en/commit_delay-performance-postgresql-benchmark/
  Focus on: the results table and the hardware setup, with the disk limited to 1,000 IOPS.
- **Testing the Group Commit Fix, Vadim Tkachenko, Percona, 2011** — https://www.percona.com/blog/testing-the-group-commit-fix/
  Focus on: the two test tables, with and without the controller's write cache. The unit is not stated.
- **The synchronous_commit parameter and streaming replication, Kaarel Moppel, CYBERTEC, 2016** — https://www.cybertec-postgresql.com/en/the-synchronous_commit-parameter/
  Focus on: the two rows with asynchronous replication, `on` and `off`. The synchronous replication rows belong to course 5.
- **All Your GUCs in a Row: max_wal_size, Christophe Pettus, 2026** — https://thebuild.com/blog/all-your-gucs-in-a-row-max_wal_size/
  Focus on: the redo time table. New, not peer reviewed, no hardware given.
- **Inside a PostgreSQL Checkpointer Bug: A Production Postmortem, Warda Bibi, Stormatics, 2026** — https://stormatics.tech/blogs/postgresql-checkpointer-bug-causing-infinite-retry-loop
  Focus on: why a stuck checkpointer leaves hours of WAL to replay. No numbers for the replay itself.
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

  The times are YouTube's auto-generated chapters, and five were checked against the auto-generated captions. Two spoken claims disagree with the docs. At about 1:19:10 the captions show him saying that synchronous commit is not on by default in PostgreSQL. The PostgreSQL 14 and 18 docs, and a fresh 14.24 cluster, say `on`. At about 0:39:25 they show him saying that SQLite now uses the WAL by default. The SQLite docs say the default is the rollback journal. This phase teaches the docs.
- **Lecture 21 slides** — https://15445.courses.cs.cmu.edu/fall2025/slides/21-logging.pdf
  Focus on: the group commit and checkpoint slides, to read with the video.
- **Lecture 21 notes, CMU 15-445 Fall 2025** — https://15445.courses.cs.cmu.edu/fall2025/notes/21-logging.pdf
  Focus on: section 2, the STEAL and FORCE policies, which section 1.2 uses.
- **Lecture 22 notes, Database Crash Recovery, CMU 15-445 Fall 2025** — https://15445.courses.cs.cmu.edu/fall2025/notes/22-recovery.pdf
  Focus on: the LSN types, non-fuzzy and fuzzy checkpoints with CHECKPOINT-BEGIN and CHECKPOINT-END, and the ARIES passes. Read it after section 1.5, to compare ARIES with PostgreSQL.

---

## Cheatsheet

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

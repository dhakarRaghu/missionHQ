# Phase 2 — Storage structures

**The question this phase answers:** why does one workload run ten times faster on one storage structure than another? And how do you tell which one you need before you have built the wrong one?

**The promise this phase pays.** Phase 1 left one step of its store for later. It is the compaction step, which Bitcask calls merge, with the hint files it writes. Section 2.4 builds both.

**Versions.** PostgreSQL 17 is the base of this phase. Source citations are at tag REL_17_11, the latest 17 minor release. Docs citations are to the PostgreSQL 17 manual. Where PostgreSQL 14 behaves differently and you may still meet it, one clause says so. Where 18 differs, one line says so. MySQL facts come from the 8.4 manual, RocksDB facts from tag v11.8.1, and pgvector facts from tag v0.8.7.

## Why you're here

Here is the situation this phase follows. It is an example, and its numbers are arithmetic that later sections show.

The order store of Phase 1 works, and it keeps its durability promise. Now it holds 10 million orders, and each order was written three times: created, paid and shipped. Three limits appear, and none of them is a bug:

1. **Memory.** The keydir is the store's hash table in memory. It maps each key to the offset of its newest entry, so it holds every key. At about 30 bytes per key, that is 300 MB for 10 million orders. A billion orders would need 30 GB of memory before the store could serve one read. Section 2.2 shows where the 30 bytes come from.
2. **Space.** Every old version stays in the log. 30 million entries of 1,230 bytes fill 36.9 GB, for 12.3 GB of current orders.
3. **Order.** A report asks for orders `order:1041` to `order:2040`. The keydir is a hash table, so it has no key order. The store must check all 10 million keys, then read 1,000 entries at 1,000 scattered offsets.

The same team also runs a write-heavy event store on PostgreSQL. A colleague proposes a move to a database built on a log-structured merge tree, or LSM tree. The reason given is that "it is faster for writes". Section 2.3 explains the structure. Suppose the team does it. Writes get faster. Reads get slower. Disk usage can reach three times the data before compaction removes the old versions. Compaction is the background work of section 2.4. A burst of that work each night becomes the new p99 problem. p99 is the latency that 99% of requests stay under. Nothing is wrong with either database. The workload was matched to the wrong structure, and nobody had a way to say so before the move.

The same team then adds an agent feature that stores one embedding per document, with the pgvector extension. An embedding is a list of numbers that a model computes for a text. The table holds a million of them, and nobody has asked what it costs the database. Section 2.9 answers that with the tools of this phase.

Every structure in this phase lowers one cost by raising another. This phase shows how to estimate each cost for your workload before a migration, and which measurement confirms the estimate.

## What you can do after this phase

1. Compute what a cache miss costs, from the page cache and SSD numbers of the earlier course.
2. Compute a B-tree's height, and the memory that holds a lookup to one cache miss. Count the pages one PostgreSQL row change writes.
3. Explain why an LSM tree writes fast and reads across several runs.
4. Explain what compaction does, why it can stall writes, and build Bitcask's merge with hint files.
5. Size a Bloom filter for a target false-positive rate, with the arithmetic.
6. Estimate read, write and space amplification of a workload on each structure.
7. Choose a structure from a decision table, and name the measurement that would prove the choice wrong.
8. Explain why LRU fails during a table scan, and what PostgreSQL and InnoDB do about it. Name the PostgreSQL scans that still flood the pool.
9. Size `shared_buffers` on RDS and on Aurora, and price a cache miss on an EBS gp3 volume against the laptop SSD.
10. Look inside the buffer pool and at the I/O of one query on PostgreSQL 17, with `pg_buffercache`, `pg_stat_statements` and `pg_stat_io`.
11. Estimate what a pgvector table and its HNSW or IVFFlat index cost in heap pages, TOAST, index pages, build memory and WAL. Say what VACUUM does after deletes.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: Storage structures                                              │
├──────────────────────────────────────────────────────────────────────────┤
│ 2.1 Pages and the buffer pool  the unit of I/O, and the price of a miss  │
│ 2.2 B-trees                    sorted pages, read and changed in place   │
│ 2.3 LSM trees                  memtable, sorted runs, reads across runs  │
│ 2.4 Compaction                 Bitcask merge, leveled and tiered, stalls │
│ 2.5 Bloom filters              "not in this run" from one memory check   │
│ 2.6 Amplification              read, write and space, as three ratios    │
│ 2.7 Matching structure         the decision table and its measurements   │
│ 2.8 Eviction                   LRU, LFU, 2Q, ARC, and real buffer pools  │
│ 2.9 Vectors as storage         pgvector: TOAST, index size, build cost   │
│ Lab: E1 to E16. The demonstration: E6, E8, E9 and E10                    │
└──────────────────────────────────────────────────────────────────────────┘
```

## What this phase assumes

Three ideas from earlier are used here and not taught again.

- **The write-ahead log, Phase 1, section 1.2.** A write-ahead log, or WAL, is an append-only file. A changed page may reach the disk only after the log record that describes the change is durable. A commit waits for its log record, not for the page, and recovery replays the log after a crash.
- **Checkpoints and full page images, Phase 1, sections 1.2, 1.4 and 1.5.** An LSN is a byte offset into the WAL. So two LSNs differ by the WAL bytes between them. A dirty page reaches its data file when the checkpointer, the bgwriter or a backend writes it. A backend is the server process of one client connection. After a crash, recovery starts at the REDO point of the last completed checkpoint. After a checkpoint, the first change to a page writes a full page image into the WAL. A full page image is a copy of the whole page. It is written because `full_page_writes` is on by default.
- **The page cache, elite-performance section 5.6.** That section is "Syscalls, buffers and the page cache". The page cache is the kernel's copy of recently used file pages. On the author's Apple M2, a read from the page cache took 1.5 µs at the median. A read from the SSD took 88.7 to 89.8 µs. A page there is 16 KiB. These are medians per run, measured on 2026-09-25.

**The running case, from Phase 1.** The order store is a Bitcask-style store. Every put appends one entry to a log: a 20-byte header with a CRC, then the key and the value. An `order:1041` entry with a 1,200-byte value is 1,230 bytes. The keydir is a hash table in memory that maps each key to the offset of its newest entry. A delete appends a tombstone, an entry that marks the key as deleted. On restart, the store rebuilds the keydir by reading the log after its last checkpoint.

**Left for later.** Phase 4 covers indexes as the query planner sees them, and table partitioning.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. The labs use Python 3.12 or later and the standard library only. They run in memory on the simulated file system of Phase 1. Four exercises, E12, E13, E14 and E16, use a local PostgreSQL 17 server at `/tmp:5432`, in the database `storage_lab` that Phase 1 created. E13 also uses the `pageinspect` and `pgstattuple` extensions, and E14 uses `pg_buffercache` and `pg_stat_statements`. All four ship with PostgreSQL. E16 needs the pgvector extension. Use 0.8.7, and nothing older than 0.8.4, for the reasons in section 2.9. The PostgreSQL exercises were not run by the author yet. Run all commands from `elite-storage/code/`.

Time: about 3 hours for the reading. The labs take about 3 hours more.

---

## 2.1 — Pages and the buffer pool (the unit of I/O, and what a cache miss costs in the numbers of the earlier course)

Why this matters: the first limit of the order store is that every key must fit in memory. A structure that holds more data than memory must keep most of it on disk. It then reads the data in fixed-size pieces. From here on, the speed of every structure depends on one ratio. It is how often a read finds its piece in memory.

**Answer this first.** A store serves reads at the M2 numbers from the recap. A read takes 1.5 µs from memory and 89 µs from the SSD. Its hit rate falls from 99% to 90%. Does the average read get 10% slower, 2 times slower, or about 4 times slower? Write your answer down.

**The mental model.** A page is the fixed-size unit in which a database reads, writes and caches its files. A PostgreSQL page is 8,192 bytes by default. A buffer pool is the database's own cache of pages, in its own memory. It is an array of slots called frames, each the size of one page. A page table maps each page number to the frame that holds it. A read first asks the buffer pool. On a hit, the page is already in a frame. On a miss, the pool picks a frame to reuse and reads the page from the file into it. Picking that frame is called eviction.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One page read in PostgreSQL. Times are the M2 medians of                 │
│ elite-performance 5.6                                                    │
├──────────────────────────────────────────────────────────────────────────┤
│  query needs page 7 of orders_pkey                                       │
│        │                                                                 │
│        ▼                                                                 │
│  buffer pool       page table: page 7 ──► frame 3?                       │
│  shared_buffers    hit: use frame 3. No system call                      │
│        │ miss: evict a frame, then read(8,192 bytes)                     │
│        ▼                                                                 │
│  OS page cache     hit: about 1.5 µs                                     │
│        │ miss                                                            │
│        ▼                                                                 │
│  SSD               about 89 µs                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

Each frame also carries two flags that matter for the rest of this phase. A pin count says how many processes are using the page now. A pinned page cannot be evicted. A dirty flag says the page changed in memory and must be written back before its frame is reused. Andy Pavlo's CMU lecture on buffer pools covers these fields at about 15:39.

**The arithmetic of a miss.** Let h be the hit rate. An average read costs h × hit cost + (1 − h) × miss cost. With the two M2 numbers:

- At a 99% hit rate: 0.99 × 1.5 + 0.01 × 89 = 1.485 + 0.89 = 2.375 µs.
- At a 90% hit rate: 0.90 × 1.5 + 0.10 × 89 = 1.35 + 8.9 = 10.25 µs.

So the answer is about 4 times slower: 10.25 / 2.375 = 4.3. The hit rate fell by 9 points, but the miss rate grew 10 times, from 1% to 10%. The misses decide the average, because one miss costs as much as 59 hits. A hit in a database's own buffer pool skips even the system call, so it costs less than 1.5 µs. That cost was not measured in this course. It makes the ratio between a hit and a miss larger, not smaller.

**PostgreSQL's buffer pool.** The setting is `shared_buffers`. Its default is 16,384 buffers of 8 kB, which is 128 MB. Verified from `guc_tables.c` lines 2267 to 2268 at tag REL_17_11, and from the PostgreSQL 17 docs, section 19.4. The docs say "a reasonable starting value for `shared_buffers` is 25% of the memory in your system". They add a limit: "it is unlikely that an allocation of more than 40% of RAM to `shared_buffers` will work better than a smaller amount". The page size of 8,192 bytes is the default of the build option `blocksize`, at `meson_options.txt` lines 5 to 8, REL_17_11. E12 shows the value on your own server.

**Two prices for one miss.** PostgreSQL reads its files through the kernel, so the page cache sits below `shared_buffers`. Rogov, "PostgreSQL 14 Internals", page 147, says PostgreSQL "reads and writes all data via buffered file operations". The CMU 15-445 Fall 2025 notes for lecture #04 name PostgreSQL as a system "that uses the OS's page cache". Both are verified. So one page can sit in memory twice, once in each cache. That is the likely reason for the 40% limit above. The reason is inferred, because the docs do not state it.

A miss in `shared_buffers` therefore has two prices. It costs about 1.5 µs when the page cache holds the page. It costs about 89 µs when the SSD must serve it. Take a 99% hit rate in `shared_buffers`. If every miss finds the page cache, the misses add 0.01 × 1.5 = 0.015 µs to the average read. If every miss goes to the SSD, they add 0.01 × 89 = 0.89 µs. So one hit rate covers miss costs that differ by 59 times.

PostgreSQL's counters cannot tell these two cases apart. The PostgreSQL 17 docs, section 27.2.2, say its I/O statistics "do not differentiate between data which had to be fetched from disk and that which already resided in the kernel page cache". The PostgreSQL 14 docs, section 28.2.2, say the same in other words. Both are verified. Here are the counters, and what each one calls a read:

| Where | A hit | A read, which may be a page-cache hit | Version |
|---|---|---|---|
| `EXPLAIN (ANALYZE, BUFFERS)` | `shared hit` | `read` | 14 to 18 |
| `pg_statio_user_tables` | `heap_blks_hit`, `idx_blks_hit` | `heap_blks_read`, `idx_blks_read`. The 14 docs call it "Number of disk blocks read" | 14 to 18 |
| `pg_stat_io` | `hits` | `reads`, per process type and context | since 16 |
| `pg_stat_statements` | `shared_blks_hit` | `shared_blks_read`, per statement | 14 to 18 |

The `pg_statio` columns are verified from the PostgreSQL 17 docs, Table 27.31. In their names, `heap` means the table's own pages and `idx` its indexes. Section 2.2 explains the heap. `pg_stat_io` is verified from the 16.0 release notes and the 17 docs, Table 27.23. Its `context` column says why the process did the I/O. The value `normal` covers most reads. `bulkread` is a large read done through a small ring of buffers, such as a sequential scan of a large table. `bulkwrite` covers COPY and table rewrites, and `vacuum` covers VACUUM. Section 2.8 explains rings. The `pg_stat_statements` columns are verified from its 1.11 SQL file at REL_17_11 and from the 1.9 file at REL_14_24. Two other sources tell the cases apart. `iostat` on the host counts the reads that reached the device. `track_io_timing`, off by default at `postgresql.conf.sample` line 645, REL_17_11, makes `pg_stat_database.blk_read_time` count read time in milliseconds. Divide it by `blks_read` for the time per block. On 17 a sequential scan reads up to 16 blocks in one call, and the call's time is counted once, at `bufmgr.c` lines 1518 to 1521. So the average is lower than the device time of one call. Compare it on index lookups, which read one page per call. There, a few microseconds means the page cache served most reads, and about 89 µs means the SSD did. That reading of the average is inferred from the M2 numbers.

**On 17 and on 18.** PostgreSQL 17 reads a sequential scan through streaming I/O. It can group up to `io_combine_limit` of pages into one read call. The default is 128kB, which is 16 pages, at `postgresql.conf.sample` line 211, REL_17_11. The 17.0 release notes list the change. So a cold sequential scan may read 16 pages per call, while an index lookup still reads one page. That reading is inferred from the setting and the note. PostgreSQL 18 adds asynchronous reads, with `io_method = worker` by default. Its docs keep the sentence about the page cache. On 18, `EXPLAIN ANALYZE` also prints the buffer lines without the BUFFERS option, at `explain_state.c` lines 179 and 180, REL_18_6.

**The WAL rule, inside the buffer pool.** Phase 1 stated the WAL rule as a principle. Here is the line of PostgreSQL that enforces it. Every page header holds `pd_lsn`, the position in the WAL just after the record of the page's last change. Before the buffer manager writes a dirty page, it forces the WAL to disk up to that position. From `bufmgr.c` at tag REL_17_11, copied from the source, with lines cut where marked:

```c
/* src/backend/storage/buffer/bufmgr.c, FlushBuffer(), REL_17_11, lines 3909 to 3927. Cut: ... */
	/*
	 * Force XLOG flush up to buffer's LSN.  This implements the basic WAL
	 * rule that log updates must hit disk before any of the data-file changes
	 * they describe do.
	 * ...
	 */
	if (buf_state & BM_PERMANENT)
		XLogFlush(recptr);
```

This is also why a database keeps its own buffer pool instead of mapping its files into memory with `mmap`. With `mmap`, the kernel decides when a dirty page goes to disk. It could write the page before its WAL record, which breaks the WAL rule. That reason is inferred from the WAL rule. The CMU lecture discusses `mmap` at about 22:52.

**The failure: every buffer pinned.** A pinned page cannot leave its frame. If every frame is pinned when a miss needs one, PostgreSQL cannot read the page at all. If its clock sweep passes every buffer in a row and finds each one pinned, it raises the error `no unpinned buffers available`. Verified at `freelist.c` line 353, REL_17_11. A pool that is too small for the number of pages that queries hold at once fails this way. A pool that is too small for the hot data fails more quietly. The hit rate falls, and the average read gets several times slower, as the arithmetic above shows.

`shared_buffers` is not the only fixed-size cache. PostgreSQL also keeps small caches, called SLRU caches, for commit status and for subtransactions. PostgreSQL 17 lets you size them, with settings such as `subtransaction_buffers`, at `postgresql.conf.sample` line 170, REL_17_11. Phase 3, section 3.2, tells the GitLab case where one of them was too small.

### Managed PostgreSQL: the pool size and the price of a miss

Why this matters: most backend teams run PostgreSQL on RDS or Aurora. Both change the two numbers of this section, the pool size and the miss price. The 25% advice above is right on one of them and wrong on the other.

**RDS for PostgreSQL.** The RDS memory page gives the default as `{DBInstanceClassMemory/32768}`. That page calls the unit bytes. The RDS parameters page says RDS uses "the default PostgreSQL units for all parameters", and gives `shared_buffers` in 8 KB. So the formula gives 8,192 / 32,768 of `DBInstanceClassMemory`, which is 25%. `DBInstanceClassMemory` is a little less than the instance memory, because RDS subtracts the memory it reserves. Verified from the two AWS pages. Check the value with `show shared_buffers` on your instance. Below the pool sits the operating system and its page cache, as on your laptop. That is inferred from the buffered I/O of this section, because the AWS page does not say. RDS stores the files on General Purpose SSD, gp2 and gp3, or on Provisioned IOPS SSD, io1 and io2 Block Express. Verified from the RDS storage page, fetched 2026-10-20.

**Aurora PostgreSQL.** Sameer Kumar and Gopalakrishnan Subramanian wrote the AWS blog post "Amazon Aurora PostgreSQL parameters, Part 1", on 12 April 2021. It says: "There is no file system or secondary level of caching for tables or indexes." The default is `SUM({DBInstanceClassMemory/12038},-50003)`, "which is about 75% of the available memory". The unit is again 8 kB, so the formula itself gives 8,192 / 12,038, about 68%, minus 50,003 buffers, about 390 MiB. That arithmetic is this course's. The post reports one test of `shared_buffers`, a select-only pgbench run on a db.r5.2xlarge with 500 clients at scale 1,000. With `shared_buffers` at 15% of memory, it "showed a 14% reduction in performance and 14% increase in VolumeReadIOPS". This is a vendor source, verified from the post.

So on Aurora a miss in `shared_buffers` has no OS page cache below it. It is a read from the storage service, and the 1.5 µs page-cache price does not exist there. One exception exists. On NVMe instances in an I/O-Optimized cluster, Aurora Optimized Reads adds a tiered cache on the local NVMe, per the AWS Optimized Reads page. Each storage read counts in the CloudWatch metric `VolumeReadIOPs`, a count per 5 minutes, which the post calls "[Billed] Volume Read IOPS". On Aurora Standard each read is billed per I/O. On Aurora I/O-Optimized, reads have no I/O charge, per the Aurora pricing page.

| | Self-managed on a VM or laptop | RDS for PostgreSQL | Aurora PostgreSQL |
|---|---|---|---|
| default `shared_buffers` | 128 MB | 25% of `DBInstanceClassMemory` | "about 75%" per AWS. The formula gives about 68%, minus about 390 MiB |
| cache below the pool | the OS page cache | the OS page cache | no OS page cache. Optimized Reads adds an NVMe cache on some instances |
| a miss in `shared_buffers` costs | 1.5 µs or a device read | a page-cache hit, not measured on RDS, or an EBS read | a storage read. Billed per I/O on Aurora Standard |
| the hit-rate signal | `pg_statio`, `pg_stat_io` | the same, plus Performance Insights | the same, plus `BufferCacheHitRatio` and `VolumeReadIOPs` |

**The price of a miss on EBS.** The M2 laptop's 89 µs is not a cloud number. The EBS docs say gp3 volumes "provide single-digit millisecond latency". On plain EBS, a gp3 volume has a baseline of 3,000 IOPS, and you can buy up to 80,000. RDS for PostgreSQL differs: below 400 GiB, gp3 gives a fixed 3,000 IOPS, and from 400 GiB it gives 12,000 to 64,000, per the RDS storage page. io2 Block Express gives an "average latency of under 500 microseconds for 16KiB I/O operations". All are verified from the EBS and RDS docs, fetched 2026-10-20. Take 1 ms per miss as an example inside "single-digit millisecond":

- At a 99% hit rate, the misses add 0.01 × 1,000 = 10 µs to the average read. On the M2 they added 0.89 µs.
- At a 90% hit rate, they add 0.10 × 1,000 = 100 µs.
- At 3,000 IOPS, the volume serves at most 3,000 misses a second, whatever the latency.

So on a cloud volume, each point of hit rate costs about 11 times more than on the laptop. The lab's latency model takes that price with `--latency --read-us 1000`. The flag changes only the latency model, at `amplification.py:314`, so it needs `--latency`. In the write-heavy workload about 10% of the 20,000 operations a second are gets, from E6. At about one block per get and 1 ms per block, the gets alone need about 2 seconds of device time each second. So expect the queue to grow without limit. Add `--rate 5000` for a load that one device can serve. That outcome is this course's arithmetic, not run.

**What you see when the pool is too small.** A backend that waits for a page read shows the wait event `DataFileRead` of type `IO` in `pg_stat_activity`. The source spells it `DATA_FILE_READ`, at `wait_event_names.txt` line 211, REL_17_11. Performance Insights on RDS and Aurora shows the same wait as `IO:DataFileRead`. The current AWS docs show that dashboard as part of CloudWatch Database Insights. The AWS page for that event gives the reading. "If the IO:DataFileRead event occurs frequently, your shared buffer pool might be too small to accommodate your workload." Run this a few times during the slow period:

```sql
-- Which waits do the active sessions spend their time in?
select wait_event_type, wait_event, count(*)
from pg_stat_activity
where state = 'active'
group by 1, 2
order by 3 desc;
```

**Two real cases of a cold pool.** A cold pool is one that holds few of the hot pages, such as right after a restart.

- **GitHub, September 2012.** Jesse Newland's post "GitHub availability this week" describes a failover to a MySQL replica. The new active database "had a cold InnoDB buffer pool and performed rather poorly". The load on the cold cache made the health checks fail again, so the cluster failed back. Verified from the post. Phase 5, section 5.5, covers failover itself.
- **Canva, post of 2022.** Canva ran its media metadata on MySQL on RDS, before it moved to DynamoDB. Its post "From Zero to 50 Million Uploads per Day" lists the limits it hit. One of them: "Servicing our normal production traffic required a hot buffer pool, so instance restarts and version upgrades weren't possible without accepting some downtime." Verified from the post.

In PostgreSQL, the `pg_prewarm` module can reload the pool after a restart. With `pg_prewarm` in `shared_preload_libraries`, the module will, "using 2 background workers, reload those same blocks after a restart". Verified from the PostgreSQL 17 docs, F.28. The AWS extension pages list `pg_prewarm` 1.2 for RDS and for Aurora PostgreSQL 17.11. The Aurora blog post above adds that Aurora "maintains shared buffers contents during restarts and potentially during failovers". Both are vendor sources, fetched 2026-10-20.

### Looking inside the pool, and the I/O of one query

Why this matters: the counters above give one hit rate for the whole server. A slow query or a flooded pool needs two finer views. The first is which tables hold the pool now. The second is which statements cause the reads.

**`pg_buffercache`: what the pool holds.** This extension ships with PostgreSQL. It has two summary functions, `pg_buffercache_summary()` and `pg_buffercache_usage_counts()`, since its version 1.4 in PostgreSQL 16. `pg_buffercache_usage_counts()` returns one row per usage count, 0 to 5, with the number of buffers, dirty buffers and pinned buffers. Section 2.8 explains usage counts. Verified from `pg_buffercache--1.3--1.4.sql` lines 6 to 21 at REL_17_11, and the 17 docs, F.25. The docs give this query for the relations that hold the most buffers:

```sql
create extension if not exists pg_buffercache;
select * from pg_buffercache_usage_counts();
-- The docs' per-relation query, from pgbuffercache.sgml lines 385 to 393:
select n.nspname, c.relname, count(*) as buffers
from pg_buffercache b join pg_class c
  on b.relfilenode = pg_relation_filenode(c.oid) and
     b.reldatabase in (0, (select oid from pg_database
                          where datname = current_database()))
join pg_namespace n on n.oid = c.relnamespace
group by n.nspname, c.relname
order by 3 desc
limit 10;
```

The functions need a superuser or a role with the privileges of `pg_monitor`, per the docs. RDS for PostgreSQL 17.11 lists `pg_buffercache` 1.5 in its extension versions page, verified on 2026-10-20. Version 1.5 adds `pg_buffercache_evict()`. The 17.0 release notes say that it "is useful for testing".

**`pg_stat_statements`: which statements read.** It counts hits and reads per statement. On PostgreSQL 17 the read time column is `shared_blk_read_time`. On 14 to 16 it was `blk_read_time`, and the 17.0 release notes record the rename. The time columns stay zero unless `track_io_timing` is on, per the 17 docs, F.30. The module must be in `shared_preload_libraries`, so adding it needs a restart. On RDS, PostgreSQL 11 and later load it by default, per the AWS Performance Insights page for PostgreSQL. That page names the same counter `db.sql_tokenized.stats.shared_blks_read_per_sec`.

```sql
-- The ten statements that read the most pages that were not in shared_buffers
select queryid, calls, shared_blks_hit, shared_blks_read,
       round(shared_blk_read_time::numeric, 1) as read_ms,
       round(100.0 * shared_blks_read
             / nullif(shared_blks_hit + shared_blks_read, 0), 1) as miss_pct,
       left(query, 60) as query
from pg_stat_statements
order by shared_blks_read desc
limit 10;
```

**`pg_stat_io`: reads by process type and reason.** It splits the server's I/O by `backend_type`, `object` and `context`. Run `select pg_stat_reset_shared('io');` before a test to start from zero. The reset target `io` is at `pgstatfuncs.c` line 1740, REL_17_11. Then read it:

```sql
select backend_type, context, reads, hits, evictions, reuses
from pg_stat_io
where object = 'relation' and reads > 0
order by reads desc;
```

On PostgreSQL 18, `pg_stat_io` drops `op_bytes` and adds byte columns such as `read_bytes`, per the 18.0 release notes. E14 runs all three tools on the tables of E12.

A page is now the unit of every read. That says how data moves. It does not say how a store finds the one page that holds `order:1041` among millions. The next section is the structure that does that, with very few misses.

**The sentence to remember:** a buffer pool's miss rate decides the average read time. Going from 1% to 10% misses makes reads about 4 times slower. On the laptop a PostgreSQL miss costs 1.5 µs or 89 µs, on EBS gp3 about a millisecond, and the counters do not say which.

**The trap:** reading the hit rate instead of the miss rate, or reading PostgreSQL's `read` counter as disk reads. A 90% hit rate means 10 times the misses of 99%. A `read` may be a page-cache hit, so sizing `shared_buffers` from that counter alone sizes it for the wrong cache. Another trap is copying the 25% rule to Aurora, which has no OS page cache below the pool. AWS's own test at 15% of memory lost 14% of throughput.

**Try this now:** run `psql -h /tmp -p 5432 -d storage_lab -c "show shared_buffers" -c "show block_size" -c "select sum(heap_blks_read) as read, sum(heap_blks_hit) as hit from pg_statio_user_tables"`. Compare the first two values with the defaults above. Then say which cache could have served the `read` count, and which tool would tell you. On a managed instance, run the `pg_stat_activity` wait query above and look for `IO` / `DataFileRead`.

---

## 2.2 — B-trees (how a read finds a row, what a write updates, and why they read fast and write in place)

Why this matters: the B-tree is the default index type of PostgreSQL, and InnoDB stores every table inside one. It removes two limits of the order store at once. It keeps keys in sorted order, so a range is one walk. And it keeps only a small part of itself in memory, so RAM no longer limits the key count. But PostgreSQL and InnoDB put the row in different places, and that changes what each read and write costs.

**Answer this first.** An index holds 10 million order ids in 8 kB pages. How many pages does one lookup read? How much memory keeps every page of the lookup cached except the last one? Guess the order of size: kilobytes, megabytes or gigabytes.

**The mental model.** A B-tree is a tree of pages, kept sorted by key. A leaf page holds keys in order, each with a pointer to its row. It also links to the next leaf. An inner page holds separator keys and the page numbers of its children. A lookup reads one page per level, from the root down to a leaf. A range scan finds its first leaf, then follows the leaf links to the right. A write changes the leaf in place, in the buffer pool.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ A B-tree on 10 million keys. Page counts are the arithmetic below        │
├──────────────────────────────────────────────────────────────────────────┤
│ level 2  root      1 page        separators for 96 children              │
│             │                                                            │
│             ▼                                                            │
│ level 1  inner    96 pages       each up to 285 children                 │
│             │                                                            │
│             ▼                                                            │
│ level 0  leaves   27,323 pages   each up to 366 keys                     │
│                   leaf ◄──► leaf ◄──► leaf     sibling links             │
├──────────────────────────────────────────────────────────────────────────┤
│ lookup order:1041   root, inner, leaf: 3 page reads                      │
│ range 1041 to 2040  find the first leaf, then follow the next links      │
└──────────────────────────────────────────────────────────────────────────┘
```

**Where the row lives: a heap, or the tree itself.** The two databases answer this differently. Each answer has a cost.

- **PostgreSQL keeps rows in a heap.** A heap is the table's own file of 8 kB pages. Its rows are in no key order. One row version in it is a tuple. A line pointer is a 4-byte slot near the start of a page. It gives the offset and length of one tuple. A TID, or tuple ID, is a page number and a line pointer number, 6 bytes in all. Every index is a separate B-tree, and its leaf entries hold a key and the TID of a heap tuple. The primary key is one more index of this kind. Verified from Rogov, "PostgreSQL 14 Internals", section 3.1, pages 63 and 64, and the PostgreSQL 17 docs, section 65.6.
- **InnoDB keeps rows inside the primary-key B-tree.** The MySQL 8.4 manual describes it: "Each `InnoDB` table has a special index called the clustered index that stores row data". Its leaves hold whole rows, in primary-key order. And "each record in a secondary index contains the primary key columns for the row". So a lookup through a secondary index walks two trees. Verified from the manual's page "Clustered and Secondary Indexes".

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Where the row lives. Names, pages and TIDs are examples                  │
├──────────────────────────────────────────────────────────────────────────┤
│ POSTGRESQL: a heap, and indexes     │ INNODB: the clustered index        │
│                                     │                                    │
│ orders_pkey, a B-tree               │ PRIMARY, a B-tree on the order id  │
│   leaf: order:1041 ─► TID (7,3)     │   leaf: order:1041 + the whole row │
│                │                    │                                    │
│                ▼                    │ idx_customer, a secondary index    │
│ heap page 7, line pointer 3         │   leaf: cust:88 + order:1041       │
│   the row, in arrival order         │         │ walk PRIMARY again       │
│                ▲                    │         ▼                          │
│ idx_customer: cust:88 ─► TID (7,3)  │   leaf of PRIMARY: the row         │
├──────────────────────────────────────────────────────────────────────────┤
│ point read: leaf, then heap page    │ primary-key read: one leaf         │
│ every index entry holds a TID       │ secondary entries hold the key     │
└──────────────────────────────────────────────────────────────────────────┘
```

The CMU 15-445 Fall 2025 notes for lecture #05 call the InnoDB layout index-organized storage, in their section 4. Here is what the difference changes:

1. **A PostgreSQL point lookup reads two pages that can miss.** It reads the leaf. Then it reads the heap page that the TID names. An index-only scan can skip the heap page, and Phase 4, section 4.3, says when. In InnoDB, the primary-key leaf holds the row, so one page miss is the most a primary-key lookup pays.
2. **A long primary key costs more in InnoDB.** Each secondary entry repeats it. The manual says: "If the primary key is long, the secondary indexes use more space". In PostgreSQL every index entry holds a 6-byte TID, whatever the primary key is.
3. **A random primary key splits the table itself in InnoDB.** The manual's page "The Physical Structure of an InnoDB Index" covers this. It says random inserts leave pages "from 1/2 to 15/16 full", and sequential ones about 15/16. In PostgreSQL a random key splits only index pages, and new rows still fill the heap in arrival order. That last point is inferred from the heap layout, and not measured here.
4. **A row that moves.** A PostgreSQL update writes a new tuple with a new TID. Phase 3 explains why. So each index needs a new entry. The exception is a heap-only tuple update, HOT for short. It puts the new version on the same heap page and adds no index entries. Its conditions are below. InnoDB secondary entries hold the primary key, so they stay valid when a row moves inside the clustered tree. That is inferred from the two layouts. It is the difference that the Uber post below argues from.

PostgreSQL also has hash, GiST, GIN, SP-GiST and BRIN indexes, in Rogov's chapters 24 to 29. In this phase, "index" means a B-tree index.

**A row in the heap.** A heap tuple starts with a fixed header, "occupying 23 bytes on most machines". Each tuple also takes a line pointer, "4 bytes per item". Verified from the PostgreSQL 17 docs, section 65.6.1 and Table 65.2. Phase 3 explains the header's fields. An order of the running case has 1,210 bytes of key and value. With its header and length bytes, it takes about 1,250 bytes of a page. So about 6 orders fit on one heap page of 8,192 − 24 = 8,168 usable bytes. That count is inferred from the docs' sizes, and was not checked with `pageinspect`.

A row wider than `TOAST_TUPLE_THRESHOLD`, "normally 2 kB", has its large values compressed or moved out of line. TOAST is PostgreSQL's name for this out-of-line storage. The moved values go to a separate TOAST table in chunks of "about 2000 bytes". Verified from the PostgreSQL 17 docs, section 65.2, "TOAST". For 8 kB pages the exact numbers are a threshold of 2,032 bytes and chunks of at most 1,996 bytes. Both follow from the macros in `heaptoast.h`, lines 23 to 26, 46 to 48 and 84 to 89, at REL_17_11, and `vector_storage.py` repeats the arithmetic. Rogov, page 157, adds that these values "are always accessed via an index". So reading a large JSON payload costs a lookup in a second B-tree and reads of a second heap. An UPDATE "incurs no TOAST costs if none of the out-of-line values change", per the same docs page. The 1,230-byte order of the running case stays inline, because it is under 2,032 bytes. An embedding of 1,536 dimensions takes 6,152 bytes, so it moves out of line. Section 2.9 works out what that costs.

**The arithmetic of height.** The number of entries a page holds decides the height, and the height decides the reads. Here are the inputs, from PostgreSQL 17 at tag REL_17_11. They are the same at REL_18_6:

- A page is 8,192 bytes. The page header is 24 bytes, from `PageHeaderData` in `bufpage.h` and Table 65.2 of the 17 docs. The B-tree's own data at the end of the page, `BTPageOpaqueData` in `nbtree.h`, is 16 bytes. So 8,192 − 24 − 16 = 8,152 bytes hold entries.
- A leaf is filled to 90% when the index is built, and an inner page to 70%. These are `BTREE_DEFAULT_FILLFACTOR` and `BTREE_NONLEAF_FILLFACTOR` at `nbtree.h` lines 200 and 201.
- One entry for an 8-byte key is 20 bytes. The index tuple header is `IndexTupleData` at `itup.h` lines 35 to 51. It is a 6-byte TID and a 2-byte `t_info`, so 8 bytes. The key adds 8 bytes, and the line pointer 4. Verified from the source and the docs.

So a leaf holds 8,152 × 0.9 / 20 = 366 entries, rounded down. An inner page holds 8,152 × 0.7 / 20 = 285. For 10 million keys:

- leaves: 10,000,000 / 366 = 27,323 pages, rounded up
- inner level: 27,323 / 285 = 96 pages
- root: 96 / 285 rounds up to 1 page

That is a height of 3. The pages above the leaves are 96 + 1 = 97 pages, or 97 × 8 KiB = 776 KiB. Once those are cached, a lookup misses the buffer pool at most once, on the leaf. For a billion keys, the same arithmetic gives 4 levels and 9,622 pages above the leaves, about 75 MiB. `btree_model.py` repeats this arithmetic with your own inputs.

A real index agrees. Rogov, pages 428 and 429, inspects `bookings_pkey` on PostgreSQL 14, an index on 6-character booking codes. Its inner page holds 285 entries. Its leaf holds 367: 366 keys and the high key, an upper bound for the keys on the page. Verified from the book. The 7 bytes of key data round up to the same 16-byte index tuple. That rounding is inferred from 8-byte alignment.

Now compare the keydir of the order store. A compact keydir entry needs the 10-byte key, an 8-byte offset, a 4-byte size and an 8-byte sequence number. That is 30 bytes per key before any hash-table overhead, the figure the opening situation used. The Phase 1 store in Python uses much more per key, and that was not measured. So the B-tree needs about 776 KiB of memory where the keydir needs 300 MB. The price is one more page read per lookup. The keydir knew the exact offset, and the B-tree must read a leaf to find it.

**The page itself.** Every PostgreSQL page, heap and B-tree pages alike, is a slotted page. The source draws it at `bufpage.h` lines 29 to 42, REL_17_11:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ A PostgreSQL B-tree page, 8,192 bytes. Offsets are from the text         │
├──────────────────────────────────────────────────────────────────────────┤
│ 0      24                                                    8,176 8,192 │
│ ├──────┼──────────────┬─────────────────────┬────────────────┼──────┤    │
│ │header│ line pointers│     free space      │ index tuples   │ BT   │    │
│ │      │ grow ──►     │                     │   ◄── grow     │ data │    │
│ └──────┴──────────────┴─────────────────────┴────────────────┴──────┘    │
│                       ▲ pd_lower            ▲ pd_upper                   │
├──────────────────────────────────────────────────────────────────────────┤
│ header   pd_lsn: the WAL position of the last change, 2.1                │
│ BT data  BTPageOpaqueData: left and right sibling, level, flags          │
│ offset 1 the high key: an upper bound for keys on this page              │
│ offset 2 the first data key, P_FIRSTKEY at nbtree.h line 368             │
└──────────────────────────────────────────────────────────────────────────┘
```

A TID names a line pointer, not a byte offset. So a tuple can move inside its page without any change to the index entries that reach it.

**What a write updates.** A PostgreSQL insert changes one heap page and one leaf in every index of the table. Each change appends its own WAL record, and each page is now dirty in the buffer pool. The page reaches its data file later, through one of the three writers in this phase's recap. If the server crashes first, recovery replays the change from the WAL, starting at the REDO point. When a leaf is full, it splits into two pages, and the parent gets one more separator. The fill factor applies only in some splits, as this comment in the source says:

```c
/* src/include/access/nbtree.h, REL_17_11, lines 190 to 201. Copied from the source */
 * The leaf-page fillfactor defaults to 90% but is user-adjustable.
 * For pages above the leaf level, we use a fixed 70% fillfactor.
 * The fillfactor is applied during index build and when splitting
 * a rightmost page; when splitting non-rightmost pages we try to
 * divide the data equally.  When splitting a page that's entirely
 * filled with a single value (duplicates), the effective leaf-page
 * fillfactor is 96%, regardless of whether the page is a rightmost
 * page.
 */
#define BTREE_MIN_FILLFACTOR		10
#define BTREE_DEFAULT_FILLFACTOR	90
#define BTREE_NONLEAF_FILLFACTOR	70
```

So keys that always grow, such as a time or a sequence, fill the rightmost page to 90%. They leave full pages behind. Keys in random order split pages in the middle, into two halves. Dong and others measured the result in Facebook's production databases. B-tree pages were "only 1/2 to 2/3 full". So the B-tree used more than 1.5 times the space of its data. Verified from "Optimizing Space Amplification in RocksDB", CIDR 2017, section 3.

**What a split writes.** A leaf split changes up to four pages:

1. The full page keeps the lower keys.
2. A new right sibling gets the upper keys.
3. The old right neighbour, if there is one, gets a new left link.
4. The parent gets the new separator, in a separate WAL record.

The comment in `nbtxlog.h` at REL_17_11, lines 90 to 95, says what the split's record holds: "On insert with split, we save all the items going into the right sibling". And: "The left page, however, is handled in the normal incremental-update fashion". So the new right page never takes a full page image. `nbtinsert.c` registers it with `REGBUF_WILL_INIT` at line 1985, REL_17_11. The left page, the old neighbour and the parent each take an image if this is their first change since the checkpoint. Verified from the two files. So a leaf split logs about half a page of tuples, plus those images. That size is inferred from the comment. A `pg_waldump` of one split would confirm it.

**What never shrinks, and what VACUUM gives back.** PostgreSQL does not merge half-empty pages. Rogov, page 425: "once split, nodes can never be merged together, even if they contain very few elements after vacuuming". VACUUM does delete a leaf that has become completely empty, unless it is the rightmost page of its level, README line 239. The nbtree README at REL_17_11 has a section "Deleting entire pages during VACUUM", at lines 232 to 240. It says that VACUUM deletes a page "only when it's become completely empty of items". The deleted page goes into the free space map later, and a later split reuses it. That is the README section "Placing deleted pages in the FSM", at line 383. InnoDB tries to merge a page that falls below `MERGE_THRESHOLD`, "50% by default", per the MySQL 8.4 manual.

So after a mass delete, a PostgreSQL index file keeps its size on disk:

- Its emptied pages are reused by later inserts.
- Its half-empty pages stay half empty, unless new keys fall into their key range. Only a REINDEX packs them.
- The tree stays balanced the whole time.

So an index does not need regular rebuilds. It needs one when its half-empty pages cost memory or I/O that you measured. That follows from the quotes and is inferred. VACUUM VERBOSE on 17 prints one line for each index that it scanned, such as `index "orders_pkey": pages: 27323 in total, 0 newly deleted, 0 currently deleted, 0 reusable`. The format is at `vacuumlazy.c` line 726, REL_17_11, and the numbers here are an example. `pgstatindex` shows `avg_leaf_density`, `empty_pages` and `deleted_pages`. Measure with both before you rebuild. Phase 4, section 4.7, gives the locks a REINDEX takes.

**A case of a file that never shrinks.** Roblox's 73-hour outage, 28 to 31 October 2021, had one cause in BoltDB. Consul uses BoltDB to store its Raft log. The Roblox post says: "even when the oldest log entries are deleted, the space BoltDB uses on disk never shrinks". Freed 4 kB pages went on a "freelist". One "4.2GB log store is only storing 489MB of actual data". Its freelist was 7.8 MB. Each log append wrote that whole freelist, "even though the actual raw data being appended was 16kB or less". The fix was to compact the file. Verified from the post "Roblox Return to Service 10/28-10/31 2021", fetched 2026-10-20. PostgreSQL keeps its free space in a separate free space map, so this exact failure is not one it has. That is inferred. The lesson still holds: reused pages keep the file large, and only a rebuild returns the space.

**Write amplification.** Write amplification is the number of bytes the device writes for each byte the application changes. For one B-tree page, it depends on one number: how many changes the page collects between two writes of it. Call it c. Each change writes one WAL record. After a checkpoint, the first change to a page also writes the whole page into the WAL. Phase 1, section 1.4, explained why. Then the page itself is written once. So each change to a page costs the WAL record plus two pages shared by c changes:

    bytes per page change = WAL record + 2 × 8,192 / c

Take a 100-byte change and a 150-byte WAL record, both examples:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Bytes written per byte changed, for one page. 100-byte change, 150-byte  │
│ WAL record                                                               │
├──────────────────────────────────────────────────────────────────────────┤
│ c = 1     150 + 16,384   = 16,534    165.3 per byte   ████████████████   │
│ c = 10    150 +  1,638   =  1,788     17.9 per byte   █████████          │
│ c = 100   150 +    164   =    314      3.1 per byte   ███                │
├──────────────────────────────────────────────────────────────────────────┤
│ bar length is log scale: 7 characters per factor of 10, from 1           │
│ the full page term is an upper bound: PostgreSQL leaves the free space   │
│ out of a full page image                                                 │
└──────────────────────────────────────────────────────────────────────────┘
```

A page that collects 100 changes before it is written costs 53 times less per change. So c decides most of a B-tree's write cost. Fewer checkpoints let each page collect more changes. But recovery then has more WAL to replay, as Phase 1, section 1.5 showed. Mark Callaghan measured the same effect in InnoDB in 2017. The redo log is InnoDB's WAL. His insert benchmark used InnoDB from MySQL 5.7.17, with the data in memory. It wrote 5.31 KB per insert with a 4 GB redo log, and 1.66 KB with a 32 GB one. In his words, "A larger redo log reduces the InnoDB write rate per insert by more than half". With the data larger than memory, the gain was smaller. Section 2.6 gives those numbers beside an LSM's, with the server they ran on.

**A row change writes several pages.** A PostgreSQL row change pays that cost once for each page it changes. Each page has its own c:

    bytes per row change = sum over its pages of (WAL record + 2 × 8,192 / c of that page)

- An INSERT changes one heap page and one leaf in each index.
- An UPDATE that is not HOT does the same. When the new version goes to another heap page, the old version's page changes too. That follows from Phase 3's row versions, and is inferred here.
- A HOT update changes only the heap page.

New rows fill the heap in arrival order, so one heap page collects about 6 inserts of the running case. Its share is 150 + 16,384 / 6 = 2,881 bytes per insert. A leaf of a random-key index has c near 1, so it costs 16,534 bytes. A table with two random-key indexes then writes about 2,881 + 2 × 16,534 = 35,949 bytes per insert. That is 30 bytes per byte of a 1,210-byte order. These are examples from the model, not measurements. `btree_model.py --indexes 2 --heap-changes-per-page 6` prints the same sum.

The model uses one 150-byte WAL record for every page. Two details of the heap page move its share in opposite directions. Its insert record holds the whole new tuple, so it is about 1,300 bytes here. And the first insert on a fresh heap page sets `XLOG_HEAP_INIT_PAGE`, so that page takes no full page image. That is at `heapam.c` lines 2218 to 2222, REL_17_11, verified. With both, the heap share is about 1,300 + 8,192 / 6 = 2,665 bytes. The total is then about 35,700 bytes, still about 30 bytes per byte. The 1,300 is inferred from the tuple size, and not checked with `pg_waldump`.

**The measurement: a random key wrote 20 times the WAL.** Tomas Vondra measured this on PostgreSQL. His post is "On the impact of full-page writes", 2016. His table had only a primary key. He ran "a 1h benchmark, throttled to 5000 inserts per second". His result: "With BIGSERIAL primary key this produces ~2GB of WAL, while with UUID it’s more than 40GB." Then: "Clearly, vast majority of the records are full-page images". A sequence puts each new key on the same rightmost leaf, so few changes are first changes. A random UUID lands on a different leaf on almost every insert. Verified from the post. The factor of about 20 is this course's arithmetic from his two numbers.

The run made 5,000 × 3,600 = 18 million inserts. So each insert wrote about 110 to 120 bytes of WAL with BIGSERIAL. With UUID it wrote about 2.2 to 2.4 kB. The ranges exist because the post does not say whether a GB is 10^9 or 2^30 bytes. 2.2 kB is about a quarter of an 8 kB page image. So his leaves collected a few inserts between checkpoints, or his page images were smaller than 8 kB. A page image leaves out the free space, and half-full leaves have much of it. Both readings are inferred. The c = 1 row above is the worst case.

His limits matter. The text of the post does not give the PostgreSQL version, the hardware or the checkpoint settings. Its charts are images, and this course did not read them. For uniform random UPDATEs, the key type stopped mattering. Most of the WAL was then for the heap, not the indexes. The HOT case, he wrote, "pretty much eliminates all index-related WAL traffic". He also warned that "in practice there will be secondary indexes, foreign keys etc.". Each of those adds a leaf per row change, by the sum above.

**When the pool is smaller than the hot leaves.** c counts changes between two writes of a page. The checkpointer is not the only writer. Suppose the buffer pool is smaller than the set of leaves that receive changes. Then a dirty leaf is evicted long before the next checkpoint. The bgwriter or a backend writes it, and a later change reads it back. So c is bounded by how long a page stays in the pool, not by the checkpoint interval. The full page image still comes once per checkpoint. So early eviction adds page writes, not WAL. This is inferred from eviction, section 2.1, and Phase 1's write path.

Each version shows who wrote the pages in a different place:

| Writer | PostgreSQL 14 | PostgreSQL 17 and 18 |
|---|---|---|
| checkpointer | `pg_stat_bgwriter.buffers_checkpoint` | `pg_stat_checkpointer.buffers_written` |
| bgwriter | `pg_stat_bgwriter.buffers_clean` | `pg_stat_bgwriter.buffers_clean` |
| a backend | `pg_stat_bgwriter.buffers_backend`, "buffers written directly by a backend" | `pg_stat_io.writes` where `backend_type = 'client backend'` and `context = 'normal'` |

The 14 columns are from the PostgreSQL 14 docs, Table 28.21. The 17.0 release notes record the removal of `buffers_backend`. The 17 columns are verified from `system_views.sql` at REL_17_11, lines 1134 to 1173. On 17, run:

```sql
-- Who wrote the table and index pages since the last reset?
select backend_type, context, writes, evictions, reuses
from pg_stat_io
where object = 'relation' and writes > 0
order by writes desc;
select buffers_written from pg_stat_checkpointer;
```

A large `client backend` share of the writes in context `normal` is the sign of the c near 1 case. That reading is inferred. To find the statement that writes the page images, read `pg_stat_statements`. It has `wal_records`, `wal_fpi` and `wal_bytes` per statement, since its version 1.8. Verified from `pg_stat_statements--1.7--1.8.sql` at REL_17_11.

**Every index pays its own write.** Item 4 above gave the rule. An update that is not HOT adds an entry to every index. The PostgreSQL 17 docs, section 65.7, "Heap-Only Tuples", give two conditions for HOT. The update must not modify any columns referenced by the table's indexes. And there must be sufficient free space on the page that holds the old row. Then "New index entries are not needed". Since PostgreSQL 16, a change to a column that only BRIN indexes cover still allows HOT. The 16.0 release notes say so. The docs call BRIN a summarizing index. Uber's 2016 post "Why Uber Engineering Switched from Postgres to MySQL" described one such update. For it, "we had to issue at least four physical updates". Its example changed an indexed column, so HOT could not apply. The post gives no measured byte counts. It is a design argument, and its conditions matter.

PostgreSQL has lowered that index cost since 2016, in three releases. Each line is verified from the release notes:

- **12.0.** "Improve performance and space utilization of btree indexes with many duplicates". Before, duplicates were "stored unordered within their duplicate groups". Now they are "sorted in heap-storage order". So equal keys are ordered by their TID. That reading is inferred from the quote.
- **13.0.** "More efficiently store duplicates in B-tree indexes". This deduplication keeps one key with a list of TIDs. The 17 docs, section 64.1.4.3, say when it runs. It "occurs lazily, when a new item is inserted that cannot fit on an existing leaf page".
- **14.0.** "Allow btree index additions to remove expired index entries to prevent page splits". The 17 docs, section 64.1.4.2, call it bottom-up deletion. A pass "is triggered in reaction to an anticipated 'version churn page split'".

So on version 14 and later, non-HOT updates grow an index less than they did when Uber wrote. That is inferred from the dates, and the size of the change is not measured here. `pg_stat_user_tables` shows how often HOT happens, in `n_tup_upd` and `n_tup_hot_upd`. Since PostgreSQL 16, `n_tup_newpage_upd` counts updates whose new version went to another page. The 17 docs say: "These are always non-HOT updates". Phase 4, section 4.5, explains the table `fillfactor` that leaves room for HOT.

**InnoDB in MySQL 8.4: three defaults that touch this section.** MySQL 8.4 changed defaults that move the write and lookup costs above. Verified from the MySQL 8.4 manual, "What Is New in MySQL 8.4 since MySQL 8.0", fetched 2026-10-20:

| Setting | 8.0 default | 8.4 default | What it does |
|---|---|---|---|
| `innodb_change_buffering` | `all` | `none` | the change buffer "caches changes to secondary index pages when those pages are not in the buffer pool", and merges them later when a read loads the page |
| `innodb_adaptive_hash_index` | `ON` | `OFF` | a hash index that InnoDB builds "on demand for the pages of the index that are accessed often", so a lookup can skip the tree walk |
| `innodb_io_capacity` | 200 | 10000 | how fast InnoDB flushes dirty pages, which bounds how many changes a page collects |

The change buffer was InnoDB's answer to the random-leaf writes of this section. It let an uncached secondary leaf collect changes before InnoDB read it, so c rose. With `none`, each such change reads its leaf first, as PostgreSQL does. That consequence is inferred from the manual's description. The manual names the costs of the two features. A change buffer merge "may take several hours" when many rows and many secondary indexes are affected. And "Access to the adaptive hash index can sometimes become a source of contention under heavy workloads". The effect of `innodb_io_capacity` on c is inferred. After an upgrade from 8.0, compare secondary-index reads before and after, on a copy of production. The sql-mysql course, Phase 1, section 1.1, teaches the InnoDB B+tree in more depth.

**The failure: random keys.** Suppose the order id is a random value, such as a version 4 UUID. A UUID is a 128-bit identifier. A version 4 UUID is random, so two inserts in a row get unrelated values. `gen_random_uuid()` has been in core since PostgreSQL 13, per its release notes. Each insert lands on a random leaf. Every leaf is then part of the working set, so the buffer pool must hold the whole index or miss. Each leaf collects few changes before it is written, so c is near 1. Almost every insert then pays a full page image. Splits in the middle leave pages half full, and in InnoDB they split the table itself. A key that grows with time avoids all of this. PostgreSQL 18 adds `uuidv7()`, "for generating timestamp-ordered UUIDs", per its release notes. PostgreSQL 17 has no such function, so on 17 generate a version 7 UUID in the application, or use a bigint identity column. Python 3.14 adds `uuid.uuid7()`, per its uuid docs.

**Where the random key comes from.** Your ORM often chooses it for you. The Django 5.2 docs show a UUID primary key as `models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`. Python's docs say "uuid4() creates a random UUID". The Rails guide for PostgreSQL shows `create_table :devices, id: :uuid`, and says that `gen_random_uuid()` "is assumed if no" `:default` option was passed. All three are verified from the pages, fetched 2026-10-20. So a model that switches to UUID keys with the documented example gets the random-key write cost of this section. Check your migrations for `UUIDField(` and `id: :uuid` before a table grows large.

**A case of sorted inserts.** Stripe moves data between shards of DocDB, its database built on MongoDB Community. Its bulk loads were slow at first. The team then sorted the data "based on the most common index attributes in the collections". It inserted the data in that order, "taking advantage of the fact that DocDB arranges its data using a B-tree". The result was "boosting write throughput by 10x". Verified from the stripe.dev post of 2024-06-06 on zero-downtime data migrations. The mechanism is this section's c: sorted inserts land on the same few leaves, so each leaf collects many changes before it is written. The post itself says DocDB is "an extension of MongoDB Community".

The next section keeps the sorted order and writes the way the Phase 1 log does: by appending.

**The sentence to remember:** a B-tree reads one page per level, and its inner levels fit in a few megabytes. A PostgreSQL row change writes the heap page and a leaf in every index. Each page pays its own full page image after a checkpoint.

**The trap:** a random key on a large, write-heavy table. Every leaf becomes hot, pages split half full, and Vondra measured about 20 times the WAL of a sequence key.

**Try this now:** predict the height and the memory above the leaves for a billion keys. Then run `uv run python phase02_structures/btree_model.py --keys 1000000000 --indexes 2`, and compare. Then run `psql -h /tmp -p 5432 -d storage_lab -c "select relname, n_tup_upd, n_tup_hot_upd, n_tup_newpage_upd, n_tup_upd - n_tup_hot_upd as not_hot from pg_stat_user_tables order by n_tup_upd desc limit 5"`. Each `not_hot` update wrote a new entry in every index of its table. E13 shows a real page and the WAL per insert.

---

## 2.3 — LSM trees (memtable, sorted runs and compaction: why they write fast and read across levels)

Why this matters: a log-structured merge tree appends every write like the Phase 1 log, and keeps keys sorted like the B-tree. A read pays for this design, because it may have to look in several places.

Several systems in this phase are built this way:

- **RocksDB** is a key-value storage library that a program links in. Facebook built it, and MyRocks is MySQL on top of it.
- **Cassandra** and **ScyllaDB** are distributed databases that store each node's data in an LSM tree. Discord ran both, section 2.4.
- **Pebble** is the storage engine under **CockroachDB**, a distributed SQL database. The 2020 post of section 2.4 describes CockroachDB on RocksDB, with the fix in Pebble.

You may never run one of them directly. You meet an LSM tree when a system you depend on is built on one, as in the cases of sections 2.4 and 2.7. The questions of this section then decide its latency.

**Answer this first.** An LSM store has a memtable, three runs in level 0, and one run in level 1. It has no Bloom filters. The index of each run is in memory. How many data blocks does a get read for a key that sits in level 1? And for a key that does not exist?

**The mental model.** A put does two things. It appends the entry to a write-ahead log, exactly as the Phase 1 store does. Then it inserts the entry into the memtable, a sorted map in memory. When the memtable reaches its size limit, the store writes it out as one sorted run. A sorted run, also called an SSTable, is a file of entries in key order. It is never changed after it is written. New runs go to level 0, L0. Compaction, the subject of section 2.4, later merges runs into larger runs in L1, L2 and below. A get looks in the newest place first. It checks the memtable, then each L0 run from newest to oldest, then L1, L2 and below. The first version it finds is the answer.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The two paths of an LSM tree. Sizes are the RocksDB defaults             │
├──────────────────────────────────────────────────────────────────────────┤
│ WRITE                              READ, newest first                    │
│ put(k, v)                          get(k)                                │
│   │                                  │                                   │
│   ├──► WAL: append                   ├──► memtable      in memory        │
│   ▼                                  ├──► L0 run 3      L0 runs may      │
│ memtable, sorted, 64 MB              ├──► L0 run 2      overlap          │
│   │ full                             ├──► L0 run 1                       │
│   ▼                                  ├──► L1 run        one run per      │
│ flush: one sorted run to L0          └──► L2 run        level, no        │
│   │ 4 runs in L0                                        overlap          │
│   ▼                                the first version found wins.         │
│ compaction into L1, L2, ...        A tombstone found first means         │
│                                    "deleted"                             │
└──────────────────────────────────────────────────────────────────────────┘
```

**Why appending wins: the original argument.** O'Neil, Cheng, Gawlick and O'Neil designed the LSM tree for disks with moving arms. Their cost model compares a page written at a random place with a page written inside a long sequential write. On the disks of that time, the sequential page cost about 1/10 as much. They used an IBM 3380 figure. A random page took 20 ms, and a page inside a 64-page transfer took 2 ms. A B-tree insert pays a random page write. An LSM insert pays a share of a large sequential merge. Their Equation 3.4 multiplies the two savings. The paper concludes: "Typically the product of the two ratios will give a cost ratio improvement of nearly two orders of magnitude". Verified from the paper, sections 3.1 and 3.2, pages 11 to 14. That model is for disks of 1995. On an NVMe SSD, a random write costs much less compared with a sequential one, so the advantage is smaller. That last point is inferred, and not measured here.

The paper also gives the shape of a good LSM tree. Its Theorem 3.1 says the cost is lowest when each level is the same multiple of the level above. That ratio is called the fanout. RocksDB uses one fanout for every level, 10 by default.

**One run on disk.** A run in this course's lab has four parts, like RocksDB's block-based table. Data blocks of about 4 KB hold entries in key order, in the Phase 1 entry format with its CRC. An index holds one entry per block: its first key, offset and length. A filter, which section 2.5 explains, covers every key in the run. A footer says where the index and the filter start. After a run is written, its index and filter stay in memory. So a get reads at most one block per run.

**The RocksDB defaults.** These names and values come from the RocksDB source at tag v11.8.1, `include/rocksdb/options.h` and `advanced_options.h`:

| Option | Default | What it does |
|---|---|---|
| `write_buffer_size` | 64 MB | memtable size that starts a flush |
| `max_write_buffer_number` | 2 | memtables in memory, the full one included |
| `level0_file_num_compaction_trigger` | 4 | L0 runs that start a compaction into L1 |
| `max_bytes_for_level_base` | 256 MB | target size of L1 |
| `max_bytes_for_level_multiplier` | 10 | the fanout: each level 10 times the one above |
| `level_compaction_dynamic_level_bytes` | true | sizes levels from the last level upward |
| `compaction_style` | `kCompactionStyleLevel` | leveled compaction |

The RocksDB tuning guide states the shape. Runs in L0 may overlap each other, and runs in L1 and below do not. So a get checks every L0 run whose key range covers the key. It checks at most one run in each deeper level.

**RocksDB's caches.** RocksDB keeps recently read blocks in its block cache. The wiki page "Block Cache" says "The block cache stores uncompressed blocks". Out of the box it is an LRU cache of 32 MB, "8MB before version 8.2". RocksDB also reads its files through the kernel by default, because `use_direct_reads` is false at `options.h` line 1153, v11.8.1. So by default the page cache holds compressed blocks of the files. The block cache holds uncompressed copies of some of them. That is inferred from the two facts. It is the same double caching as PostgreSQL's in section 2.1, so a RAM budget must count both caches.

**The read path in code.** This is the lab's `get`, from `lsm.py:386`, with the counter lines removed:

```python
# from phase02_structures/lsm.py:386, get(). Counter lines removed, logic unchanged
        hit = self.mem.get(key)
        if hit is not None:
            return self._found(hit[1])            # memtable: no I/O
        for run in self.runs_newest_first():      # L0 newest first, then L1, L2
            if not run.min_key <= key <= run.max_key:
                continue                          # outside this run's keys: no I/O
            if run.bloom is not None and not run.bloom.may_contain(key):
                continue                          # the filter says "not here": no I/O
            i = run.block_for(key)                # the index is in memory
            if i is None:
                continue
            off, ln = run.blocks[i]
            with self.fs.charge("get"):
                buf = self.fs.read(run.name, off, ln)   # one block read
            found, value = _search_block(buf, off, key)
            if found:
                return self._found(value)         # a tombstone returns None
        return None
```

**Read amplification.** Read amplification is the work a read does beyond the data it returns. This lab counts it in two ways. One is the number of blocks a get reads from the device. The other is those bytes divided by the bytes of the value. In the question above, each L0 run covers nearly the whole key range. That is because each one is a memtable of keys from everywhere. So without filters, a key in L1 costs 3 wasted block reads in L0, then 1 useful read in L1. That is 4 blocks. A key that does not exist costs the same 4 blocks, all wasted. The Phase 1 store reads exactly 1 block for a present key, and none for an absent one. Its keydir knows every key.

A range scan has no shortcut. It reads every run that overlaps the range and merges the results, newest version first. The RocksDB tuning guide gives its read amplification as `number_of_level0_files + number_of_non_empty_levels`. Still, an LSM answers a range far better than the Phase 1 store. Take the lab's defaults: 20,000 keys of 133-byte entries in 4,096-byte blocks, and a range of 100 keys. A block holds 30 entries, because 30 × 133 = 3,990 bytes and a 31st entry would pass 4,096. In L1, 100 entries fill 100 / 30 = 3.3 blocks, so 4 or 5 block reads. An L0 run holds a few keys of the range, usually in one block. The Phase 1 store must check all 20,000 keys in its keydir, then make 100 separate reads at scattered offsets. E6 runs this with `--range-demo`, right after the load. The load ends with 40 flushes and 10 compactions, so L0 is empty. The expected result is 103 blocks for the log and 4 for the LSM. Both counts are worked out from the code and its seed, and were not run.

**Deletes are writes.** An LSM delete is a put of a tombstone, the entry type of Phase 1. The tombstone must stay as long as an older value of its key may exist in a deeper run. Otherwise a get would skip the missing tombstone and find the old value. Section 2.4 gives the rule for when a tombstone may go. Section 2.5 adds one more place where it must stay.

**The failure: the write is cheap only now.** A put costs one log append and one memory insert. That is why an LSM tree writes fast. But every entry will be read and written again each time compaction moves it down one level. A benchmark that ends before compaction has caught up measures only the cheap part. That conclusion is inferred from the design, and section 2.6 puts numbers on the full cost. Even the cheap part holds only for a raw key-value `Put`, which reads nothing. A SQL engine on an LSM reads the old row first, as section 2.7 shows.

An LSM tree trades an in-place write for later work, and a single read for several. The next section is about that later work.

**The sentence to remember:** an LSM tree appends every write and sorts it in memory. A read checks the memtable, then each overlapping run, newest first.

**The trap:** comparing an LSM tree and a B-tree on a short write benchmark. The LSM looks fast because the compaction of those writes has not run yet.

**Try this now:** run `uv run python phase02_structures/lsm.py --demo`. Count the flush lines before each compaction line, and find the option in the table above that sets that count.

---

## 2.4 — Compaction (the work that happens later, and the p99 storm it causes when it happens at once)

Why this matters: the Phase 1 log and the LSM tree both make writes cheap by putting off work. Compaction is that work. It reads old files, keeps the newest version of each key, and writes new files. It decides how much space the store uses and how many bytes it writes in total. When it falls behind, it decides the latency too.

**Answer this first.** The Phase 1 store holds 200 orders, each written three times with a 1,200-byte value. Then 10 orders are deleted. How many bytes are on disk? How many after a merge that keeps only the newest live entry of each key? Each merged file also gets a hint file that holds every key without its value. How many bytes must a restart read?

**The mental model.** Compaction merges old files into new files that hold only the live data. An entry is live when it is the newest version of its key and is not a tombstone. Everything else is garbage: older versions, tombstones, and the values they deleted. Compaction rewrites the live entries, so it trades write bytes now for less space and fewer files to read later.

### Bitcask merge and hint files

This is the step the Phase 1 store left out. The Bitcask paper, page 4, describes it. The log is split into data files. Only the newest, the active file, takes appends. When it reaches a size limit, it becomes immutable and a new active file starts. A merge reads all the immutable files. It writes new data files that hold only the newest live entry of each key. Next to each new data file it writes a hint file. A hint file holds, for each key, its position and sizes, and no value. On open, Bitcask reads a hint file in place of its data file when one exists.

A hint file plays the role of the checkpoint of Phase 1, section 1.5. But there is one hint file per merged data file, and the merge writes it, not a timer.

`bitcask_merge.py` builds this on the Phase 1 entry format. A hint entry is a 4-byte CRC, an 8-byte sequence number, two 4-byte sizes, an 8-byte offset and the key. That is 28 bytes plus the key. The paper's hint entry has no CRC. The lab adds one for the same reason as Phase 1: a damaged hint must be detected. A damaged hint costs time and not data, because the store then reads the data file instead.

Here is the arithmetic for the question above. A put entry is 1,230 bytes, and a delete is 20 + 10 = 30 bytes.

- Before the merge: 600 puts × 1,230 + 10 deletes × 30 = 738,300 bytes.
- Live data: 190 orders, each a 10-byte key and a 1,200-byte value, 190 × 1,210 = 229,900 bytes.
- After the merge: 190 entries × 1,230 = 233,700 bytes of data. Add 190 hint entries × 38 = 7,220 bytes of hints.

So after the merge the disk holds 233,700 + 7,220 = 240,920 bytes. A restart that uses the hints reads 7,220 bytes, 32 times fewer than the 233,700 bytes of merged data. That is because a hint entry is 38 bytes and a data entry is 1,230. A restart reads keys, not values. These numbers are worked out by hand. The self-test of `bitcask_merge.py` asserts each of them, and it passes, as E1 records.

**The merge must be crash-safe.** A merge replaces files, so the order of its steps matters. The Phase 1 checkpoint had the same problem. The new files must be durable before the old ones are removed. Here is the right order and the wrong one, from `bitcask_merge.py:314`:

```python
# from phase02_structures/bitcask_merge.py:314, merge(). Comments changed, logic unchanged
        self.hook("merge.written")              # new data and hint files, not durable yet
        if self.rules.sync_before_remove:
            # RIGHT: new bytes durable, then new names, then remove the old files.
            self._sync_outputs(out_files)
            self.fs.sync_dir("full")
            self.hook("merge.dir-synced")
            self._switch(new_locs, dropped)
            self._remove_old(old)
            self.fs.sync_dir("full")
            self.hook("merge.dir-synced-2")
        else:
            # WRONG: the removal is made durable while the new bytes are only
            # in the page cache.
            self._remove_old(old)
            self.fs.sync_dir("full")
            self.hook("merge.dir-synced")
            self._sync_outputs(out_files)
            self._switch(new_locs, dropped)
```

`--crash-test` stops the merge at each step. Then it builds the process, OS and power images of Phase 1's simulated file system. Every recovery must return every acknowledged order. In the right order, the old and the new files both exist between the directory sync and the removal. They hold the same entries with the same sequence numbers. Open keeps the highest sequence number per key, so the copies do no harm. In the wrong order, at `merge.dir-synced`, the old names are gone for good. The new files have durable names but no durable bytes. An OS crash or a power loss there loses every order. E4 gives the expected counts, and the self-test asserts them.

The merge may drop a tombstone because it reads every immutable file. Every older version of that key is in one of them, since the active file only holds newer entries. A merge of only some files could not drop it, as the LSM rule below shows.

### LSM compaction: leveled and tiered

An LSM tree compacts runs, not log files, and it does it by levels. The RocksDB wiki page "Compaction" names two main styles. RocksDB calls the first "Level" compaction and the second "Universal":

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Two compaction styles. Write amplification per level: RocksDB wiki       │
├──────────────────────────────────────────────────────────────────────────┤
│ LEVELED                               │ TIERED, "universal" in RocksDB   │
│ each level is one sorted run,         │ each level holds several runs of │
│ 10 times larger than the level above  │ about the same size              │
│                                       │                                  │
│ L0 ▓▓ ▓▓ ▓▓ ▓▓                        │ L0 ▓▓ ▓▓ ▓▓ ▓▓                   │
│ L1 ▓▓▓▓▓▓▓▓▓▓                         │ L1 ▓▓▓▓▓▓▓▓ ▓▓▓▓▓▓▓▓ ▓▓▓▓▓▓▓▓    │
│ L2 ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓     │ L2 one large run                 │
│                                       │                                  │
│ merging into Ln rewrites Ln too:      │ merging writes each byte once    │
│ per-level write amp = fanout,         │ per level: write amp 1 per level │
│ worst case                            │                                  │
│ space: little garbage, about 1.1      │ space: up to 3 times the data    │
│                                       │ by default, then a full merge.   │
│                                       │ A merge needs up to 2 times the  │
│                                       │ space of the files it rewrites   │
│ reads: few runs to check              │ reads: more runs to check        │
└──────────────────────────────────────────────────────────────────────────┘
```

The wiki describes leveled compaction this way. Its per-level write amplification "is equal to the fanout in the worst case, but it tends to be less than the fanout in practice". For tiered compaction, the wiki says "The per-level write amplification is 1 which is much less than for leveled where it was fanout". It also notes that RocksDB merges only the overlapping part of each level. It calls this "some-to-some". The original LSM paper merged all of it.

**A worked example from the RocksDB tuning guide.** L1 is 512 MB and the fanout is 10. The database is 500 GB. So L2 is 5 GB, L3 is 51 GB and L4 is 512 GB.

Write amplification, step by step:

1. Each byte is written once to L0. That counts 1.
2. L0 to L1 writes it again, with about the same amount of L1. That counts 2.
3. Each deeper step merges it with 10 times its size. Each counts 10.

The guide's total: "Total write amplification is therefore approximately `1 + 2 + 10 + 10 + 10 = 33`". The guide counts from L0, so the WAL write comes on top. That is inferred.

Space amplification has three numbers:

| Number | Value | Source |
|---|---|---|
| leveled, this example | "`(512 MB + 512 MB + 5GB + 51GB + 512GB) / (500GB) = 1.14`" | tuning guide |
| leveled, worst case | 1.111, with a full last level and fanout 10. The upper levels hold 11.1% of the last | Dong and others, CIDR 2017, section 3 |
| universal, old versions | `max_size_amplification_percent` defaults to 200. "a 100 byte database could require up to 300 bytes of storage" | `include/rocksdb/universal_compaction.h` lines 45 to 48 and 137, v11.8.1, and the tuning guide |

Universal compaction has a fourth number: the room a merge needs while it runs. Past the 200% limit, RocksDB compacts all files into one sorted run. The wiki page "Universal Compaction", section "Compaction Triggered by Space Amplification", says so. During that full compaction, the input files and the output file both stay. So "the DB will be temporarily double the disk space usage". The tuning guide says a compaction "may temporarily increase size amplification by a factor of two". So a large merge needs free space up to the size of the files it rewrites. The 300 bytes is the tripled disk of this phase's opening.

**The lab's two levels.** The lab LSM has only L0 and L1. Each compaction merges the L0 runs with the whole of L1, so it rewrites all the live data each time. Its write amplification therefore grows with the data, because L1 grows while the L0 batch does not. More levels with one fanout keep the cost per level fixed. That is why real LSM trees have them, as O'Neil's Theorem 3.1 says. E5 gives the lab's numbers.

### When compaction falls behind

Compaction shares the device with reads and writes. If it runs as one large job, every request that arrives during the job waits for it. If it runs slower than the writes arrive, unmerged runs pile up in L0. Reads then check more runs, and the store must slow the writes down or stop them.

RocksDB decides this in one function, `ColumnFamilyData::GetWriteStallConditionAndCause`, at `db/column_family.cc` lines 1011 to 1046, tag v11.8.1. It checks these conditions in this order, and the first match wins:

| # | Condition, with the default | Result |
|---|---|---|
| 1 | unflushed memtables ≥ `max_write_buffer_number`, 2 | writes stop |
| 2 | L0 runs ≥ `level0_stop_writes_trigger`, 36 | writes stop |
| 3 | pending compaction bytes ≥ `hard_pending_compaction_bytes_limit`, 256 GB | writes stop |
| 4 | `max_write_buffer_number` > 3 and unflushed memtables ≥ that number − 1 | writes slow down |
| 5 | L0 runs ≥ `level0_slowdown_writes_trigger`, 20 | writes slow down |
| 6 | pending compaction bytes ≥ `soft_pending_compaction_bytes_limit`, 64 GB | writes slow down |

Notes on the table:

- Conditions 2, 3, 5 and 6 apply only when automatic compaction is on.
- With the default of 2 memtables, condition 4 can never apply. So a flush that falls behind stops writes without slowing them first. That is inferred from the order of the checks, and was not tested.
- In a slowdown, writes are held to `delayed_write_rate`. Its default of 0 means 16 MB per second, unless a rate limiter is set. That is at `options.h` lines 1367 to 1383.
- The Write Stalls wiki page says each delayed write sleeps "typically 1ms". This course did not find that sleep in the source.
- The same page warns that a stall in one column family stalls the whole database. A column family is RocksDB's name for a separate key space inside one database.
- Flushes and compactions share a pool of background threads, `max_background_jobs`, 2 by default at `options.h` line 900.
- The wiki writes the two pending-bytes options without the `_limit` suffix. The table uses the names in the source.

**What a stall looks like in production.** RocksDB writes each stall to its LOG file. The wiki page "Write Stalls" gives these lines. The file counts are from the wiki's own example, not from the defaults:

```
Stalling writes because we have 4 level-0 files
Stopping writes because we have 20 level-0 files
Stalling writes because of estimated pending compaction bytes 500000000
```

The source at v11.8.1 adds two parts that the wiki leaves out. Each line starts with the column family name in square brackets. A slowdown line also ends with `rate` and the delayed write rate in bytes per second. The format strings are at `db/column_family.cc` lines 1087 and 1130, verified.

RocksDB also dumps compaction statistics into the LOG every `stats_dump_period_sec`, 600 seconds by default at `options.h` line 1217, v11.8.1. `db->GetProperty("rocksdb.stats")` returns the same text. Here is the wiki's example from the page "Compaction Stats and DB Status". This course cut eleven columns, the `Int` row and two summary lines. The wiki gives no version or workload for it:

```
** Compaction Stats **  (cut: Rn, Rnp1, Moved, Rd, Wr, Comp(sec), Comp(cnt), Avg(sec), Avg(ms), KeyIn, KeyDrop)
Level   Files  Size(MB)  Score  Read(GB)  Write(GB)  Wnew(GB)  W-Amp  Stall(sec)  Stall(cnt)
L0        2/0        15    0.5       0.0       32.8      32.8    0.0        0.00           0
L1       22/0       125    1.0     163.7      165.5      34.6    5.1        0.00           0
L2      227/0      1276    1.0     262.7      262.7      34.3    7.6        0.00           0
L3     1634/0     12794    1.0     259.7      254.1      26.1    8.0        0.00           0
L4     1819/0     15132    0.1       3.9        3.6       1.6    1.8        0.00           0
Sum    3704/0     29342    0.0     690.1      718.7     129.4   21.9        0.00           0
Stalls(count): 0 level0_slowdown, 0 level0_numfiles, 0 memtable_compaction, 0 leveln_slowdown_soft, 0 leveln_slowdown_hard
```

Three columns answer this section's questions on a live store:

- **`Score`.** For levels below L0, it is the level's size over its target size. The wiki says "any value greater than 1 means that level needs to be compacted". For L0 it counts files against the compaction trigger.
- **`W-Amp`.** The wiki defines it as "(total bytes written to level N+1) / (total bytes read from level N)". In the `Sum` row it is 21.9. That is 718.7 GB written over the 32.8 GB that flushes wrote into L0. This course checked the division, and it matches.
- **`Stall(sec)` and `Stall(cnt)`.** They count how long, and how often, writes waited because the level was not compacted. The `Stalls(count)` line splits the stalls by cause.

So the `Sum` row's `W-Amp` is the measured write amplification of compaction. Section 2.6 asks you to estimate that number. Here it is 21.9, against the 33 of the tuning guide's arithmetic above. The tuning guide also credits the default `compaction_pri = kMinOverlappingRatio`, at `advanced_options.h` line 725. The guide reports it for two Facebook databases, UDB and msgdb. There, write amplification "dropped by more than half, compared to previous default". It links to a Facebook internal post for that claim, so its conditions are not checked.

**Pacing compaction in production.** The lab's `--compaction paced` flag has a real counterpart. `rate_limiter` is null by default, at `options.h` line 734, v11.8.1. You set it with `NewGenericRateLimiter(rate_bytes_per_sec)`. The wiki page "Rate Limiter" says this "controls the total write rate of compaction and flush in bytes per second". It adds that RocksDB "does not enforce rate limit for anything other than flush and compaction, e.g. write to WAL". A limit below the rate that compaction must keep only moves the problem into L0 and the stall table above. That is inferred from the stall conditions. A write that must never wait can set `no_slowdown = true` in `WriteOptions`. It then returns `Status::Incomplete()` instead of blocking, per the Write Stalls page.

**Two production reports.** Bilal Akhtar and David Taylor described a compaction storm in a 2020 CockroachDB post, "Faster bulk-data loading in CockroachDB". Cockroach Labs wrote it about its own product, so it is a vendor source.

- **The problem.** Imports filled L0 faster than RocksDB could compact it. RocksDB then started "a giant compaction from L0 to LBase". LBase is the highest level below L0 that holds data. The compaction "could take it minutes, sometimes ten or more, to complete". While it ran, no other L0 compaction could start. When L0 reached its limit, the write backpressure would "bring the entire job to a standstill".
- **The fix, in Pebble.** Pebble arranged L0 runs into sublevels. A sublevel is a set of L0 runs whose key ranges do not overlap. So a read checks at most one run in each. 847 L0 runs fit into 13 sublevels, so a read checks 13 places instead of 847.
- **The test.** It imported TPC-C, a standard order-processing benchmark whose size is set in warehouses. It loaded 50,000 warehouses, about 5 TB, on 10 AWS c5d.4xlarge nodes with local SSDs.
- **The result.** Before the fix: 6.5 to 10 hours, plus 3 to 6 hours of compaction. After it: 1 hour 15 minutes to 1 hour 30 minutes, plus 30 minutes.

A 2022 CockroachDB post by Sumeer Bhola describes admission control. It keeps read amplification at or below a threshold, 20 by default. It notes overload situations where read amplification reached 1,000.

Bo Ingram's 2023 post "How Discord Stores Trillions of Messages" describes its Cassandra cluster. "We were prone to falling behind on compactions", it says. Nodes then showed "cascading latency as a node tried to compact". The team's workaround took a node "out of rotation to let it compact without taking traffic". The same post found ranges full of tombstones "that were never compacted away in Cassandra". Those tombstones held the data migration at 99.9999% for a while. Section 2.7 gives what Discord measured after it moved.

**Range reads over deletes.** A tombstone costs more than space. A range scan must read each tombstone in its range and skip it. That goes on until compaction drops the tombstone at the last level. The RocksDB wiki page "Implement Queue Service Using RocksDB" shows the failure. A queue deletes its oldest items first, so "there can be a large amount of 'tombstones' in the beginning of each `queue_id`". Then `Seek(<queue_id, 0>)` and the `Next()` past the last item "might be exceptionally slow". The page's fix is `ReadOptions.iterate_upper_bound`, which stops a scan at the end of its range. Discord's tombstones above look like the same problem in Cassandra. That link is inferred. RocksDB has three tools for it, each verified from its wiki page:

- **`DeleteRange`** deletes a whole key range with one entry. The wiki says it "creates a range tombstone represented as a single kv".
- **`SingleDelete`** removes a key's entry and its tombstone together when compaction lines them up. It is correct only for a key written once since its last delete, per the page "Single Delete".
- **`CompactOnDeletionCollectorFactory`** starts a compaction for key ranges dense with tombstones. The tuning guide says this "helped to reduce range scan performance skews caused by scanning excessed number of tombstones".

**The same shape in PostgreSQL.** A queue table in PostgreSQL meets the same problem through its B-tree. A worker claims the oldest job by walking the index from the head of the queue. It steps over entries of jobs that are done but that VACUUM has not removed yet. Brandur Leach measured this in 2015, with about 50 jobs a second and one long transaction open. The time to lock a job grew "until it's 15x that level at times of 0.1 s and above". Verified from his post "Postgres Job Queues & Failure By MVCC". VACUUM can remove those entries only when no open snapshot can still see the rows. A B-tree page goes back for reuse only when it is completely empty, section 2.2. Phase 3, section 3.7, gives the claim query and the rest of that measurement. Phase 4, section 4.5, explains the cleanup horizon. Agent runners and background-job libraries that keep their jobs in PostgreSQL have this shape.

The opening situation's event store deletes old events in key order, and Phase 3's outbox has the same queue shape. So for those stores, retention deletes are normal daily work. That judgement is inferred. Section 2.7 adds a decision-table row for this shape.

**The storm in the lab.** `amplification.py --latency` runs the write-heavy workload at 20,000 arrivals per second. The arrivals do not wait for replies. Such an open-loop load shows a stall as latency, as elite-performance Phase 1, "Measurement before optimisation", taught. A closed loop would hide it as a lower rate. In the model's defaults, one L0 to L1 merge holds the device for about 4.2 ms in every 111 ms. That is 3.8% of the time, so the p99 of puts falls inside the merge, at a few milliseconds. With `--compaction paced`, the same work runs in 0.25 ms slices in idle time. The longest wait is then about one slice. E9 gives the timeline and the arithmetic, worked out from the model and not run. The model has limits. It has one queue, and it changes the data at once while it charges the compaction time later.

**The failure: compaction at one time of day.** The opening situation ran heavy compaction at night. The aim was a fast day. The work does not shrink when it waits. The runs of the whole day are merged in one long job. Spreading compaction out with a rate limit keeps each wait short. The cost is that more runs exist at any moment, so reads check more places. This is inferred from the model above and the reports, and the lab's `--compaction` flag shows the two shapes. In RocksDB the rate limit is `rate_limiter`, above.

Compaction removes garbage and keeps the run count down. The next section removes almost all of the block reads that a get still makes in each run.

**The sentence to remember:** compaction rewrites live data to remove garbage. Leveled compaction writes more and keeps less, and tiered writes less and keeps more. Both must keep up with the writes.

**The trap:** letting compaction work collect and then running it as one large job. Every request during that job waits for it, and the p99 is set by the job's length.

**Try this now:** run `uv run python phase02_structures/bitcask_merge.py --demo`. Check each printed number against the merge arithmetic above.

---

## 2.5 — Bloom filters (turning "is it in this level?" into one memory read, with the false-positive arithmetic)

Why this matters: in section 2.3, a missing key cost a block read in each run that covers it. A get for a present key paid the same in each run above the one that holds it. A Bloom filter per run answers "the key is not here" from memory. So the store skips almost all of those block reads.

**Answer this first.** A filter uses 10 bits of memory per key. What fraction of absent keys will it wrongly report as "maybe here"? And how much memory does it need for the 10 million orders of the running case?

**The mental model.** A Bloom filter is an array of m bits and k hash functions. All bits start at 0. To add a key, set the k bits that its hashes point to. To test a key, read its k bits. If any of them is 0, the key was never added. If all are 1, the key may have been added, or its bits may have been set by other keys. So the filter can say "no" or "maybe". It never says "no" for a key that was added. A "maybe" for a key that was not added is a false positive. The share of absent keys that get one is the false-positive rate, FPR.

**The false-positive arithmetic.** Take n keys, m bits and k hashes. Bloom's 1970 paper, equations 16 and 17, gives the FPR in modern form: FPR = (1 − e^(−kn/m))^k. The lowest FPR comes at k = (m/n) × ln 2, when half of the bits are 1. Bloom puts it this way: "the smallest hash area for which method 2 can be used occurs when half the bits are 1 and half are 0". At that k, FPR = e^(−(m/n) × (ln 2)²), which is about 0.6185^(m/n). Monkey, SIGMOD 2017, gives this form as its Equation 2.

So for the question above, m/n = 10. The best k is 10 × 0.693 = 6.93, so 7 hashes. Then e^(−0.7) = 0.4966, so a bit is 1 with chance 0.5034, and FPR = 0.5034^7 = 0.0082, or 0.82%. For 10 million keys, 10 bits each is 100 million bits, which is 12.5 MB. That is 24 times less memory than the 300 MB keydir. But the filter does not say where the key is.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ FPR by bits per key, best integer k. Theory, from the FPR formula        │
├──────────────────────────────────────────────────────────────────────────┤
│ bits/key  k   FPR        log scale: 6 chars per factor of 10, from 100%  │
│  5        3   9.18%      ██████                                          │
│  8        6   2.16%      ██████████                                      │
│ 10        7   0.82%      █████████████                                   │
│ 16       11   0.046%     ████████████████████                            │
├──────────────────────────────────────────────────────────────────────────┤
│ bits per key for a target FPR p:                                         │
│   m/n = −ln(p) / (ln 2)² = 1.44 × log2(1/p)                              │
│ 1%: 9.6 bits per key.   0.1%: 14.4 bits per key                          │
│ each 4.8 more bits per key divide the FPR by 10                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**RocksDB's number is a little higher, and both are right.** The RocksDB header `filter_policy.h` is at tag v11.8.1. It says: "A good choice is 9.9, which yields a filter with ~ 1% false positive rate". Theory gives 0.86% at 9.9 bits. The difference comes from the layout. RocksDB puts all probes of one key into one 512-bit block. That is one 64-byte CPU cache line, so a test reads one cache line. But blocks get uneven numbers of keys, and a block with more keys has a much higher FPR. The RocksDB wiki page "RocksDB Bloom Filter" works it out for 10 bits per key and k = 6:

- Each block gets n/s = 512 / 10 = 51.2 keys on average. The standard deviation is √51.2 = 7.16.
- The FPR at 51.2 − 7.16 keys is 0.43%. At 51.2 + 7.16 keys it is 1.48%.
- Their average is 0.95%. The same filter without blocks gives 0.84%, so the blocks cost a factor of 1.13.

So "10 bits per key is about 1%" is true for RocksDB's filter. And 0.82% is true for the textbook filter with the best k. `bloom.py --blocked` measures both side by side. The same wiki page lists the bits per key that RocksDB's filter needs. They are 4.9 for 10%, 9.9 for 1% and 15.5 for 0.1%. The header `filter_policy.h` also describes the Ribbon filter, a different filter structure that RocksDB offers in place of Bloom. It saves about 30% of the space for the same FPR. Its query time is similar, but building it takes about 3 to 4 times the CPU.

**Where the filter bits should go.** Dayan, Athanassoulis and Idreos wrote Monkey, SIGMOD 2017. It showed that the "worst-case lookup cost is proportional to the sum of the false positive rates of the Bloom filters across all levels". The deepest level holds most of the keys, so it holds most of the filter memory. Giving every level the same bits per key is therefore not the best use of memory. Monkey sets each level's FPR in proportion to its capacity. In their tests, lookup latency fell by "50% −80% for the data sizes we experimented with". Their conditions were a worst case for lookups. Monkey was built on LevelDB, on a 7,200 RPM disk, with the block cache off. The data was 1 GB of 1 KB entries, and the lookups asked for keys that did not exist.

**Where the filters live.** A filter is memory, and so is the index of each run. The wiki page "Partitioned Index Filters" says that for a 256 MB run, "the index/filter block of size 0.5/5MB is typical". The wiki page "Block Cache" says these blocks are kept "outside of block cache" by default. Then only `max_open_files` bounds their memory. These four options decide where they go:

| Option | Default, v11.8.1 | What it changes |
|---|---|---|
| `cache_index_and_filter_blocks` | false, `table.h` line 238 | true puts index and filter blocks into the block cache, where they compete with data blocks |
| `max_open_files` | −1, `options.h` line 776 | −1 keeps every run open, so every run's index and filter stay in memory |
| `partition_filters` | false, `table.h` line 519 | true splits a run's filter into small blocks that are cached one at a time |
| `optimize_filters_for_hits` | false, `advanced_options.h` line 816 | true stores no filters for the last level |

The `max_open_files` row is inferred from the wiki's sentence and the default. The last row is a shipped form of Monkey's point above. The last level holds most keys. The source comment says: "For keys which are hits, the filters in this level are not useful because we will search for the data anyway". So a store whose gets almost always find their key can drop most of its filter memory. The wiki measured partitioned filters on two old setups, from about RocksDB 5.x. On an 86 GB database on HDD with a 60 MB block cache, "Partitioning improves throughput by 11x from 5 op/s to 55 op/s". LinkBench is a benchmark from Facebook that models a social-graph workload. In LinkBench on 300 GB of SSD with 2 GB of cache, it was 30k tps with partitions. Without them it was 23k. The wiki pages have no release tag, so treat these numbers as old.

**What this does to the lab LSM.** With filters, an absent key costs a block only on a false positive. It checks 1 to 4 runs, L1 and up to 3 L0 runs, so 2.5 runs on average. At 0.82% each, that is about 2.5 × 0.0082 = 0.02 blocks per get. Without filters, the same get reads one block in each run that covers the key: about 2.5 blocks on average. These numbers are worked out from the code and were not run. A get for a present key in L1 reads 1 block. Now and then it adds a false positive in an L0 run above it. E7 removes the filters and shows the difference.

**The failure: a filter without the tombstones.** After a delete, a new run holds the tombstone. An older run holds the old value. A get must find the tombstone first. If the filter of the new run leaves out deleted keys, it answers "no" for the tombstone's key. The get then skips that run and returns the old value from the run below. The deleted order is back. The lab keeps every key in the filter, tombstones included, at `lsm.py:268`. The self-test turns that rule off and shows the deleted key coming back.

A whole-key filter does not help a range scan, because a range does not name single keys. A prefix Bloom filter does help a range inside one key prefix. The wiki page "Prefix Seek" says that if "many sorted runs don't contain any entry for this prefix, it can be filtered out by a bloom filter". An event store keyed by stream id and sequence number reads ranges inside one stream, so it fits that case. That use is inferred. A filter helps every point read, and it costs memory in proportion to the number of keys.

**Where you see a filter at work.** RocksDB counts filter results in its statistics. The wiki page "RocksDB Bloom Filter" names them: `rocksdb.bloom.filter.useful` counts "[true] negatives", `rocksdb.bloom.filter.full.positive` counts "positives", and `rocksdb.bloom.filter.full.true.positive` counts "true positives". It gives the observed FPR of point lookups as "(positives - true positives) / (positives - true positives + true negatives)". A rate well above the table's value for your bits per key means the setting in production is not the one you think. PostgreSQL has Bloom filters too, in other places. The `bloom` extension is an index access method "based on Bloom filters". BRIN indexes have bloom operator classes, which "build a Bloom filter for all values in the range". Both are verified from the PostgreSQL 17 docs, F.6 and section 64.5. Neither is the per-run filter of an LSM tree.

Each structure now has its costs in reads, writes, space and memory. The next section turns those costs into three ratios that can be compared.

**The sentence to remember:** at 10 bits per key, a Bloom filter says "maybe" for about 1% of absent keys. It never says "no" for a present one. The FPR falls by 10 for each 4.8 more bits per key.

**The trap:** building a run's filter from its live keys only. The filter then hides the run's tombstones, and deleted keys come back from older runs. Or sizing RAM for the filters alone, when each run's index blocks also stay in memory by default.

**Try this now:** first predict the measured FPR at 4 bits per key from the table above. Then run `uv run python phase02_structures/bloom.py --keys 100000 --blocked` and compare both measured columns with theory.

---

## 2.6 — Read, write and space amplification (the three numbers to estimate for any workload)

Why this matters: "faster for writes" is the claim that started the migration in this phase's opening situation. It names one cost and hides two. Three ratios describe what a structure does with every byte you give it. With them, two structures can be compared on your workload before you move any data.

**Answer this first.** Take the Phase 1 store with no merge. Each of its 10 million orders was written three times. Compute its write amplification and its space amplification. Then say which of the three numbers a leveled LSM tree makes worse here, and by roughly how much.

**The mental model.** The RUM paper by Athanassoulis and others, EDBT 2016, defines three overheads as ratios. Its words, from section 2:

- Read overhead is "the ratio between the total amount of data read including auxiliary and base data, divided by the amount of retrieved data".
- Update overhead is "the ratio between the size of the physical updates performed for one logical update, divided by the size of the logical update".
- Memory overhead is "the ratio between the space utilized for auxiliary and base data, divided by the space utilized for base data".

This course calls them read, write and space amplification. Base data is the live keys and values. Auxiliary data is everything else: headers, indexes, filters, old versions and free space. The paper then states its conjecture, which it does not prove:

> "An access method that can set an upper bound for two out of the read, update, and memory overheads, also sets a lower bound for the third overhead."

Every structure in this phase is one choice of that trade.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Where each structure spends. Numbers from this phase                     │
├──────────────────────────────────────────────────────────────────────────┤
│                      write amp      cold point read   space amp          │
│ Phase 1 log          1.02           1 block, 0 if     3.05 after 3       │
│ no merge                            absent            writes per key     │
├──────────────────────────────────────────────────────────────────────────┤
│ Bitcask with merge   1.02 + merge   1 block           about 1.05 right   │
│                      rewrites                         after a merge      │
├──────────────────────────────────────────────────────────────────────────┤
│ B-tree               3.1 to 165     1 miss, inner     over 1.5 with      │
│                      per page, by   pages cached.     pages 1/2 to 2/3   │
│                      changes per    PostgreSQL adds   full               │
│                      page. Times    the heap page                        │
│                      pages per row                                       │
├──────────────────────────────────────────────────────────────────────────┤
│ leveled LSM          33 in the      1 block plus      1.11 to 1.14       │
│                      RocksDB guide. the filter FPRs                      │
│                      21.9 in the                                         │
│                      wiki's stats,                                       │
│                      section 2.4                                         │
├──────────────────────────────────────────────────────────────────────────┤
│ tiered LSM           1 per level    more runs to      up to 3 by default │
│                                     check             before a full      │
│                                                       merge. A merge     │
│                                                       needs up to 2x the │
│                                                       space of the files │
│                                                       it rewrites        │
├──────────────────────────────────────────────────────────────────────────┤
│ memory: the log keeps every key in RAM. The B-tree keeps 776 KiB of      │
│ inner pages per 10 million keys. The LSM keeps 10 bits of filter per key │
│ plus each run's index, about 0.5 MB per 256 MB run, section 2.5          │
└──────────────────────────────────────────────────────────────────────────┘
```

**How to estimate each number.** Do this for one logical operation of your workload, in four steps:

1. **Write.** List every write that one logical change causes. Include the WAL record, the data write, and each later rewrite by compaction or a checkpoint. In PostgreSQL, count each page the change touches: the heap page and a leaf per index. Add their bytes and divide by the bytes of the change.
2. **Read.** Count the blocks a point read touches with a cold cache. Then count them with the inner pages or filters cached. Do the same for one range read. Divide the bytes by the bytes returned.
3. **Space.** Divide the bytes on disk, in steady state, by the bytes of the live keys and values.
4. **Memory.** Write down what must stay in RAM for the read estimate to hold. That is a keydir, inner pages, or filters and run indexes.

For the question above, the logical bytes of an order are its 10-byte key and 1,200-byte value, 1,210 bytes. The device writes a 1,230-byte entry, so the write amplification is 1,230 / 1,210 = 1.02. The disk holds 30 million entries for 10 million live orders. The disk bytes are 30,000,000 × 1,230 = 36.9 GB. The live bytes are 10,000,000 × 1,210 = 12.1 GB. So the ratio is 36.9 / 12.1 = 3.05. A leveled LSM tree makes the write amplification worse. With the tuning guide's 33, it writes about 33 / 1.02 = 32 times as many bytes per order. It makes space better, about 1.1, and needs far less memory.

**Measured numbers.** The ratios differ by workload, so each measurement below comes with its conditions. Mark Callaghan ran his insert benchmark in 2017 on two MySQL engines. MyRocks is built on RocksDB, and InnoDB on B-trees. These are his rows for the load that did not fit in memory, on his "fast SSD" server:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Bytes written per insert. Callaghan, Small Datum, 2017-05-11             │
├──────────────────────────────────────────────────────────────────────────┤
│ engine              1 char = 0.5 KB                 KB/ins   GB    ins/s │
│ InnoDB, redo 4 GB   █████████████████████████████    14.65  402   61,711 │
│ InnoDB, redo 32 GB  ████████████████████             10.11  402   63,959 │
│ MyRocks, no zstd    ████                              2.07  226  126,727 │
│ MyRocks, zstd       ███                               1.64  101  128,816 │
├──────────────────────────────────────────────────────────────────────────┤
│ InnoDB from MySQL 5.7.17. Insert-only load, data larger than memory,     │
│ block cache 10 GB, the server he calls "fast SSD". Its hardware is in an │
│ earlier post that this course did not fetch                              │
└──────────────────────────────────────────────────────────────────────────┘
```

So in that test, InnoDB wrote 4.9 to 8.9 times as many bytes per insert as MyRocks. It also inserted about half as fast. The author adds a warning: "Be wary about drawing too many conclusions from an insert-only workload."

Part of InnoDB's bytes is its doublewrite buffer, its answer to torn pages from Phase 1, section 1.4. The MySQL 8.4 manual says pages flushed from the buffer pool go there "before writing the pages to their proper positions". The page says it "is enabled by default in most cases". MySQL 8.4 also changed two of its defaults: `innodb_doublewrite_files` is now 2, and `innodb_doublewrite_pages` is now 128. Verified from the 8.4 "What Is New" page. So InnoDB writes each flushed page twice. The page adds that this "does not require twice as much I/O overhead or twice as many I/O operations". The copies go out "in a large sequential chunk". Whether it was on in Callaghan's 2017 runs is not checked.

Two more sources point the same way, under their own conditions:

- **Dong and others, CIDR 2017.** The paper reviewed Facebook production databases. It found that "the amount of data written to storage by RocksDB is between 10% and 15% of what InnoDB writes out". The space used by RocksDB was about 50% lower than compressed InnoDB. In LinkBench, section 2.5, with 1 billion vertices and 50 GB of DRAM, RocksDB was "3%-16% better than InnoDB" in throughput. It wrote less than 20% of InnoDB's bytes per transaction. The hardware was a 24-core Xeon E5-2678v3 with 256 GB of RAM and about 5 TB of NVMe SSD. The authors work at Facebook, and the workload is Facebook's.
- **Yoshinori Matsunobu, Facebook engineering blog, 2016.** Facebook built MyRocks, so this is a vendor source. He ran LinkBench for more than 24 hours on PCI-Express flash. The MyRocks instance "was 3.5 times smaller than InnoDB uncompressed, and two times smaller than InnoDB compressed". On spinning disks, "MyRocks was more than six times faster than InnoDB". The post shows write volume only in a chart image, so this course does not quote a number for it. It also gives one cause of InnoDB's space: "A 16 KB in-memory page compressed to 5 KB still uses 8 KB on storage". That is space amplification from a fixed compressed page size.

**The lab's expected numbers.** E6 runs two layouts and two workloads on 20,000 keys with 100-byte values. It lists the expected values. Both layouts read about 4,096 bytes to return 100. So their read amplification in bytes is about 41 for the LSM and 42 for the log. The difference between them is in writes and space, not in reads. These values are worked out from the code and its seed, and were not run.

**The failure: one number alone.** The Phase 1 log has the best write amplification in E6, 1.18. On the write-heavy workload, it also uses about 11.8 times its live data on disk. That number grows with every put. A comparison that looks only at write amplification picks it, and the disk fills.

**The sentence to remember:** write amplification is bytes written per byte changed. Read amplification is bytes read per byte returned. Space amplification is bytes stored per live byte. Lowering one raises another.

**The trap:** picking a structure by one ratio. The Phase 1 log wins on write amplification and loses on space by a factor that grows with every overwrite.

**Try this now:** write down your prediction for the four rows of E6, then run `uv run python phase02_structures/amplification.py`. Compare every column, and look for the row furthest from the table.

---

## 2.7 — Matching structure to workload (the decision table, with the measurements that fill it in)

Why this matters: the three ratios of section 2.6 decide nothing until you multiply them by your own workload. This section turns the ratios into device time, so two structures can be compared in seconds per second.

**Answer this first.** The order store must take 10,000 updates per second, each changing 100 bytes of a random order. The index is ten times larger than RAM, so a random leaf is almost never cached. Estimate the device bytes written per second for a B-tree and for a leveled LSM tree. Then say which wins, and by roughly what factor.

**The mental model.** A device has a budget of one second of work per second. Each structure spends that budget on three things. They are the reads its gets cause, the writes its changes cause, and its background work. So for each structure, estimate four numbers from the workload:

1. **Write load.** User bytes per second times write amplification gives device bytes written per second.
2. **Read load.** Gets per second times blocks per get that miss the cache, times the cost of one miss.
3. **Space.** Live bytes times space amplification, at the peak, gives the disk you need.
4. **Memory.** What must stay cached for the read estimate to hold.

Then compare each load with what the device can do. A structure that needs more than the device's budget will stall. A structure that needs less wins by the ratio of the two loads.

**The worked answer.** The user writes 10,000 × 100 bytes = 1 MB per second. Take PostgreSQL for the B-tree side, and MyRocks, MySQL on RocksDB, for the LSM side.

**PostgreSQL.**

- **The read.** Each update first finds its row. The leaf misses. So does the heap page that the TID names, because the heap is larger still. At the M2 SSD cost: 10,000 × 2 × 89 µs = 1.78 seconds of device time each second.
- **A HOT update.** Each page collects about one change before it is written, so c is near 1. A HOT update changes only the heap page. Section 2.2's model gives up to 16,534 bytes per update, 165 MB per second.
- **An update that is not HOT.** It can change the old heap page, a new heap page and the primary-key leaf. That is up to 3 × 16,534 = 49,602 bytes, about 496 MB per second.
- **What kind of bytes.** Half of those bytes are full page images, appended to the WAL. The other half are random 8 kB page writes.

**MyRocks, a leveled LSM.** A raw RocksDB `Put` is a blind write: the new version hides the old one. A SQL row update is not blind.

- **The read.** The MyRocks wiki page "Read Free Replication" says INSERT, UPDATE and DELETE "all need GetForUpdate() to read by primary keys". "On cache miss, GetForUpdate() reads RocksDB data block from storage, and decompresses it". The engine needs the old row to check unique keys. It likely also needs it to remove old secondary index entries. That second reason is inferred from the page's examples. So each update reads one data block, which misses: 10,000 × 89 µs = 0.89 seconds per second.
- **The write.** Each update writes a new version of the whole row, not of the 100 changed bytes. This is inferred from the same page, which says the binary log's row images hold all that is needed to compose the RocksDB write calls. With the 1,230-byte entry, that is 10,000 × 1,230 bytes = 12.3 MB per second.
- **Compaction.** The tuning guide's 33 turns 12.3 MB into about 406 MB per second of writes, before compression, in large sequential runs. Compaction also reads about as many bytes.

The page has no release tag. This course read it on 2026-10-18.

The read-free mode on that wiki page works only on replicas. It gives up "almost all real time consistency checks", and "Primary still checks uniqueness". Verified from the page. InnoDB, the third design, reads one clustered leaf per update, because the leaf holds the row. That is 0.89 seconds per second, like the LSM. That last figure is inferred from section 2.2's layout.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One second of the update workload: 10,000 updates of 100 bytes           │
├──────────────────────────────────────────────────────────────────────────┤
│                PostgreSQL, heap and B-tree     MyRocks, leveled LSM      │
│ reads          leaf and heap page both miss    GetForUpdate reads the    │
│                10,000 × 2 × 89 µs = 1.78 s     row first: 0.89 s         │
│ writes, HOT    heap page only: up to 165 MB    the whole 1,230-byte row  │
│ writes, not    two heap pages and the leaf:    × 33: about 406 MB, in    │
│ HOT            up to about 496 MB              long sequential runs      │
│ background     the page writes are inside      compaction also reads     │
│                the totals above                about as many bytes       │
├──────────────────────────────────────────────────────────────────────────┤
│ both spend about one device second or more per second on reads alone     │
│ estimates from sections 2.1 to 2.4, not measured                         │
└──────────────────────────────────────────────────────────────────────────┘
```

**What the estimate shows.** For this workload the LSM does not write fewer bytes. It writes about 406 / 165 = 2.5 times the bytes of HOT updates. It writes a little less than the non-HOT worst case, 406 against 496 MB. Its bytes are sequential, and half of PostgreSQL's are random page writes. The cause is the size of the change against the size of the row. A B-tree page costs about 16.5 kB per change at c near 1, whatever the change. An LSM costs about 33 times the whole row. So the LSM writes fewer bytes only when 33 times the row is less than 16.5 kB per dirtied page. A 100-byte row costs 3.3 kB against 16.5 kB for each page.

Neither design removes the reads. Both need about one device second or more per second for reads alone, so neither fits one device queue. More memory, or a device that serves many reads in parallel, comes before the choice of structure. In Callaghan's insert test in section 2.6, InnoDB wrote 4.9 to 8.9 times the bytes of MyRocks. His post does not give the row size, so this course cannot compare those bytes with this model. A reply by the author under the post says "Inserts are in PK order, but random for secondary indexes". So the B-tree's extra bytes there come from secondary index leaves at c near 1. That link is inferred. The estimate is inferred from the models of sections 2.1, 2.2 and 2.4, and was not measured.

A first draft of this answer multiplied 33 by the 100 changed bytes, not by the row. So it gave the LSM five times fewer bytes. That was wrong, because an LSM writes a new version of the whole row.

**The same workload on a cloud volume.** The device model above is one laptop SSD that serves one read at a time. Move the PostgreSQL side to a gp3 volume:

1. It makes 20,000 random reads a second, the leaf and the heap page for each of 10,000 updates.
2. That is about 6.7 times the 3,000 IOPS baseline of section 2.1. So you must buy at least 20,000 IOPS.
3. On plain EBS, gp3 allows 500 IOPS per GiB, so that needs a volume of at least 40 GiB. On RDS for PostgreSQL, 20,000 IOPS needs a gp3 volume of at least 400 GiB, section 2.1.
4. The reads move 20,000 × 8 KiB = 156 MiB per second. That is more than the gp3 baseline of 125 MiB per second, so you must also buy throughput. The writes of the model above need more.
5. At about 1 ms each, 20,000 reads are 20 seconds of waiting per second. So about 20 reads must be in flight at once.

The MyRocks side makes half as many reads. On Aurora Standard, each PostgreSQL read that misses the pool is a billed storage I/O, counted in `VolumeReadIOPs`, so the read load is also a line on the bill. The IOPS arithmetic is this course's, from the EBS numbers of section 2.1. `amplification.py --layouts lsm --latency --read-us 1000` reruns the lab's latency model at a 1 ms miss, as section 2.1 shows.

Now change one fact: the keys always grow, as a timestamp does. The B-tree then writes to its rightmost leaf, which collects many changes. So c is large. The write amplification falls toward the 3.1 that section 2.2 gives for c = 100, or lower. The RocksDB wiki page "Compaction" notes that leveled compaction is also cheaper for keys inserted in order. RocksDB has an optimization for that case. So with growing keys, neither structure writes much, and any write advantage of the LSM mostly goes away. Only the reads and the space then decide.

**Fix the B-tree first.** A move to an LSM is the last lever, not the first. These PostgreSQL levers lower the write cost of section 2.2 without a migration. Each default is verified from the PostgreSQL 17 docs or from `postgresql.conf.sample` at REL_17_11:

| Lever | Default | What it lowers |
|---|---|---|
| a key that grows with time: a sequence or an identity column. `uuidv7()` exists only from PostgreSQL 18 | `gen_random_uuid()` gives random version 4 UUIDs, and so do the Django and Rails examples of section 2.2 | full page images per insert, as Vondra measured in section 2.2 |
| fewer indexes, and room for HOT with a table `fillfactor` below 100 | `fillfactor` 100, per the CREATE TABLE docs | index leaves written per update. Phase 4, section 4.5 |
| checkpoints further apart: `max_wal_size` and `checkpoint_timeout` | 1GB and 5min, lines 262 and 258 | raises c. Recovery then replays more, as Phase 1, section 1.5, showed |
| `wal_compression` | off, line 243. It accepts `pglz`, `lz4` or `zstd`, and `on` means `pglz`. In 14 it was only on or off | page image bytes: 8.6 times smaller in Rogov's test, Phase 1, section 1.5 |

Measure each lever with `wal_fpi` and `wal_bytes` in `pg_stat_wal`, which E13 uses. The opening situation moved the event store without trying any of them.

**The decision table.** Each row starts from one trait of the workload. It names the structure the trait favors and the number to estimate. The last column is the measurement that would show the choice is wrong:

| Workload trait | Favors | Estimate | Measurement that would prove it wrong |
|---|---|---|---|
| random-key writes of rows much smaller than a page, data much larger than RAM | leveled LSM, if the B-tree levers above are not enough | write load: about 33 × row bytes for the LSM, against 16.5 kB for the heap page and every index leaf at c near 1. On a SQL engine, both read before they write | device bytes written per second on a copy of production, `iostat` |
| write cost on PostgreSQL, before any migration | B-tree, with the levers above | full page images per row change | `wal_fpi` and `wal_bytes` per insert after each change |
| point reads, hot set fits in RAM | B-tree | miss rate, section 2.1 | buffer pool hit rate under the real mix, with `iostat` beside it |
| range scans over sorted keys | B-tree, or leveled LSM | runs or pages per range | blocks read per range scan |
| keys that always grow | either | c for the B-tree | page writes per insert |
| deletes of old keys in key order: a queue, an outbox, event retention | B-tree with a partition drop, Phase 4, section 4.6, or an LSM with `DeleteRange` and delete-triggered compaction | tombstones each range scan must skip, section 2.4 | latency of the first read at the oldest live key |
| many gets for keys that do not exist | LSM with filters, or a keydir | sum of filter FPRs | filter "maybe" rate against true hits |
| tight disk budget | leveled LSM | space amp 1.1 against B-tree's over 1.5 | bytes on disk over live bytes after a week |
| all keys fit in RAM, large values, no ranges | Bitcask log with merge | keydir bytes per key | resident memory per million keys |
| strict p99 during heavy writes | B-tree, or LSM with paced compaction and spare device time | compaction share of device time | p99 while a compaction runs |
| similarity search over embeddings, section 2.9 | HNSW in PostgreSQL while the index fits in the pool, or a smaller quantized index with re-ranking | index pages against `shared_buffers`, and the build's memory against `maintenance_work_mem` | buffers read per query in `EXPLAIN (ANALYZE, BUFFERS)`, and `pg_relation_size` of the index |
| analytics: sums and counts over a few columns of many rows | a column store, outside the OLTP database | bytes read per report: rows × row width in a row store, against rows × column width | bytes read per report, from `EXPLAIN (ANALYZE, BUFFERS)` |

The queue row is inferred from the RocksDB sources of section 2.4, not measured. The embeddings row is inferred from section 2.9. Two rules apply to every row. Estimate the loads before you trust any row. And measure on a copy of your own data, with your read mix and your key order. Run long enough for compaction or checkpoints to reach a steady state.

**Columnar storage, at the depth of one number.** Every structure in this phase is a row store: it keeps all the columns of a row together. The CMU 15-445 Fall 2025 notes for lecture #06 describe the other layout. In the decomposition storage model, "the DBMS stores a single attribute (column) for all tuples contiguously in a block of data. Thus, it is also known as a column store." The notes give its gain: it "Reduces the amount of I/O wasted per query". They also give its cost: it is "Slow for point queries, inserts, updates, and deletes".

Here is the number for the running case. A report sums one 8-byte amount over 10 million orders.

- The heap holds about 6 orders per page, section 2.2. So the scan reads 10,000,000 / 6 = 1,666,667 pages, about 13.7 GB.
- A column store reads 10,000,000 × 8 bytes = 80 MB of that column, before compression.
- That is about 170 times fewer bytes.

The arithmetic is this course's. It leaves out compression and the column store's own metadata. So a report of this shape belongs in a column store, or in a summary table, not in a larger buffer pool. The nosql course, Phase 5, section 5.3, teaches analytical stores.

**Where "ten times" comes from.** This phase's question asked why one workload can run ten times faster on one structure. The sources in this phase show several such factors, each with a different cause:

| Factor | Cause | Source |
|---|---|---|
| nearly two orders of magnitude | sequential against random page writes, on 1995 disks | O'Neil and others, section 3.2 |
| about 20 times, WAL bytes | a random UUID primary key against a sequence: full page images | Vondra, 2016 |
| 53 times, per change | how many changes a page collects between writes | section 2.2, arithmetic |
| 4.9 to 8.9 times, bytes written | B-tree against LSM on random inserts | Callaghan, 2017 |
| 10 times, read throughput | the engine's implementation, not its structure: both engines are LSM trees | Instagram, 2018, below |

So a factor of ten usually means one thing. One structure's unit of work matches the workload's access pattern, and the other's does not. Vondra's row shows that the same structure can differ by twenty times through its key alone. It can also mean the cause was somewhere else.

**When the structure was not the cause.** Instagram ran Cassandra, an LSM database on the Java virtual machine. Dikang Gu's 2018 post is titled "Open-sourcing a 10x reduction in Apache Cassandra tail latency". The fix replaced Cassandra's storage engine with RocksDB, which is also an LSM tree. Instagram calls the result Rocksandra. The "10x" of the title is a drop in garbage collection stalls. Their share of the time fell "from 2.5% to 0.3%". By the arithmetic, that is 8.3 times. The production p99 read latency "dropped from 60ms to 20ms", which is 3 times. So the tail came from Java memory management, not from the LSM shape. The post also ran a read-only benchmark on three AWS i3.8xlarge instances. There, Rocksandra gave "10X higher read throughput" at a similar p99 of 2 ms. That was 300,000 reads per second against 30,000 for Cassandra 3.0. Discord's move, whose compaction problem section 2.4 quoted, also went from one LSM database to another, Cassandra to ScyllaDB. Its post reports a p99 for reading old messages of "between 40-125ms on Cassandra", against 15 ms on ScyllaDB. The same project added a service in front of the database that merges identical requests. So that change had more than one cause, which is inferred from the post's own description.

**The failure: a benchmark that does not match the workload.** The opening situation moved the event store for faster writes. A write-only benchmark that ends before compaction reaches its steady state confirms that claim. It does not show the range reads that now check many runs. It does not show the old versions that triple the disk under universal compaction. It does not show the extra room each large merge needs, or the compaction at night. This phase estimates a number for each of those. They are read amplification for ranges, space amplification at the peak, and the compaction share of device time.

**The sentence to remember:** multiply each ratio by your workload's rate to get device seconds per second. The structure whose total fits the device budget, with room to spare, wins.

**The trap:** choosing a structure on a write benchmark, before trying the B-tree levers. It hides the read mix, the key order and the compaction cycle. It also hides the reads that a SQL engine on an LSM still makes before each write.

**Try this now:** run `uv run python phase02_structures/amplification.py --workloads read-heavy`. Before you run it, predict which column changes most from the write-heavy rows of section 2.6, and why.

---

## 2.8 — Eviction (why LRU collapses under a scan, LFU, 2Q and ARC, and what a real buffer pool uses)

Why this matters: in section 2.1, the miss rate decided the average read time. Section 2.7 put the read load into every decision. The eviction policy decides which page leaves the buffer pool on a miss, so it decides the miss rate.

**Answer this first.** A buffer pool holds 1,000 pages and evicts the least recently used page. The application keeps 800 hot pages in constant use. Then one report query reads a 2,000-page table once, from start to end, while no other query runs. How many of the 800 hot pages are still in the pool when the scan ends?

**The mental model.** LRU, least recently used, evicts the page whose last access is oldest. That works when recent use predicts the next use. A scan breaks the prediction. It touches each page once, and every scan page is newer than every hot page. After the scan has read as many pages as the pool holds, the pool holds only scan pages. None of them will be read again soon. This is called sequential flooding. Andy Pavlo's CMU lecture on buffer pools discusses it at about 47:40.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ LRU, 1,000 frames: 800 hot pages, then one scan of 2,000 pages           │
├──────────────────────────────────────────────────────────────────────────┤
│ after 1,000 scan pages, every hot page has gone. 0 hot pages are left    │
│ the next 800 hot reads all miss: 800 × 89 µs = 71 ms of reads            │
└──────────────────────────────────────────────────────────────────────────┘
```

So the answer is none. Every policy below tries to keep a page used again and again over a page used once.

**LFU.** LFU, least frequently used, evicts the page with the fewest accesses. A scan page has one access, so it leaves first, and the hot pages stay. The cost is the opposite failure. A page that was hot an hour ago keeps its high count after it stops being used. So it stays in the pool. That follows from the definition, and the lab does not measure it.

**2Q.** Johnson and Shasha published 2Q at VLDB 1994. It keeps three queues:

- **A1in** is a first-in, first-out queue of pages seen once. Its target size Kin is 25% of the frames.
- **A1out** holds only page numbers, not pages, for pages that recently left A1in. Its size Kout is the page numbers of 50% of the frames. A list of numbers like this is often called a ghost list.
- **Am** is an LRU queue for pages that were seen again after they left A1in.

The paper gives these sizes in its words:

> "Kin should be 25% of the page slots and Kout should hold identifiers for as many pages as would fit on 50% of the buffer."

A page enters Am only when it is requested again while its number is still in A1out. So it must be used twice, with time between the two uses. A scan page is used once, goes through A1in and A1out, and never reaches Am. A second access while a page is still in A1in does not count. It is often part of the same short burst, such as several rows read from one page. `cache_sim.py:181` follows the paper's pseudocode, and E10 runs it.

The paper measured 2Q against LRU on traces, by hit rate. 2Q helped most when the pool was small compared with the data. One test mixed one third scan references into Zipf references, where a few pages get most of the accesses. The result: "The hit rate of 2Q is about 70% of its no-scan hit rate, while the hit rate of LRU is about 60% of its no-scan hit rate". Verified from the paper, Tables 1 to 4 and page 443. The PDF is a scanned image, and the research read the tables from the page images.

**ARC.** Megiddo and Modha published ARC, the adaptive replacement cache, at FAST 2003. It keeps two lists of pages, T1 for pages seen once recently and T2 for pages seen at least twice. It also keeps two ghost lists, B1 and B2, for pages that recently left T1 and T2. A target size p decides how much of the pool belongs to T1. A request that hits B1 means T1 was too small, so p grows. A hit in B2 means T2 was too small, so p shrinks. So ARC tunes the split between recency and frequency by itself, while 2Q needs Kin and Kout. The lab implements the paper's Figure 4 case by case.

The paper's Table VI uses SPC1, a trace with long sequential scans, and a cache of 1,048,576 pages. Its hit ratios were 9.19% for LRU and 20.00% for ARC. All of the paper's traces are reads only, filtered by caches above them, and counted from a cold start.

### What real buffer pools use

**PostgreSQL: clock sweep and a ring.** PostgreSQL uses neither LRU nor 2Q. Each buffer has a usage count. Each access raises it by one, up to `BM_MAX_USAGE_COUNT`, which is 5 at `buf_internals.h` line 79, REL_17_11. A clock hand moves around the buffers. It lowers each count it passes by one. It takes the first buffer whose count is 0 and that nobody has pinned. From `freelist.c` at REL_17_11, copied with the locking and statistics lines cut. The same lines are identical at REL_18_6:

```c
/* src/backend/storage/buffer/freelist.c, StrategyGetBuffer(), REL_17_11, lines 314 to 353. Cut lines marked ... */
	/* Nothing on the freelist, so run the "clock sweep" algorithm */
	trycounter = NBuffers;
	for (;;)
	{
		buf = GetBufferDescriptor(ClockSweepTick());
		...
		if (BUF_STATE_GET_REFCOUNT(local_buf_state) == 0)
		{
			if (BUF_STATE_GET_USAGECOUNT(local_buf_state) != 0)
			{
				local_buf_state -= BUF_USAGECOUNT_ONE;

				trycounter = NBuffers;
			}
			else
			{
				/* Found a usable buffer */
				...
				return buf;
			}
		}
		else if (--trycounter == 0)
		{
			...
			elog(ERROR, "no unpinned buffers available");
		}
		...
```

A page used often keeps a count near 5. So the hand must pass it five times before it can be taken. A page used once has a count of 1. The next pass lowers it to 0, and the pass after that takes it. The comment above the cap explains why it is only 5: "A large value (comparable to NBuffers) would approximate LRU semantics". But a large cap could make the hand go round many times before it finds a buffer.

The clock alone does not stop a large scan from flooding the pool. PostgreSQL handles sequential scans with a separate rule. A sequential scan of a table larger than a quarter of `shared_buffers` uses a ring. A ring is a small, fixed set of buffers that the scan reuses. Verified at `heapam.c` lines 445 to 452, REL_17_11. Two details keep the ring from hurting other queries. A page read through the ring gets a usage count of at most 1. The source says: "Ring buffers shouldn't evict others from pool. Thus we don't make usagecount more than 1". And the scan takes back a ring buffer only if its count is still 0 or 1. A higher count means another query used the page. So the scan leaves it and takes a new buffer from the clock. Verified at `freelist.c` line 727, REL_17_11.

The ring's size depends on the version.

| Version | Ring for a large Seq Scan | Evidence |
|---|---|---|
| 14 | 256 kB, 32 pages | Rogov, page 156 |
| 15 to 17 | 256 kB, 32 buffers of 8 kB | `GetAccessStrategy` in `freelist.c`, lines 541 to 573 at REL_17_11. The same 256 in REL_15_14 and REL_16_10 |
| 18 | about 752 kB with default settings | arithmetic below, inferred, not measured |

On 17 the same function gives the bulk write ring 16 MB and the VACUUM ring 2,048 kB. The README at REL_17_11, line 218, says "For sequential scans, a 256KB ring is used".

The 18 code is at `freelist.c` lines 557 to 601, REL_18_6. It starts at 256 kB. It adds room for its asynchronous reads: 8 kB × 16 × 16 = 2,048 kB. The two 16s are the 18 defaults of `io_combine_limit`, 128kB or 16 pages, and `effective_io_concurrency`. On 17, `io_combine_limit` is also 128kB, but `effective_io_concurrency` is 1, at `postgresql.conf.sample` lines 211 and 209. So the 18 code wants 2,304 kB. It caps the ring at the number of buffers one process may pin. With 128 MB of `shared_buffers`, that cap is 16,384 buffers / 174 processes = 94 buffers, or 752 kB. The 174 is 136 backends plus 38 auxiliary processes, from the default settings. The README in the 18 tree still says 256 kB. E12 shows the ring's effect on your own server.

**Which operations use a ring.** The ring protects the pool only from operations that ask for one. A bitmap heap scan does not. A bitmap heap scan collects the matching rows from an index, then reads their table pages in physical order. Phase 4, section 4.3, explains when the planner picks it. In `tableam.h` at REL_17_11, lines 959 to 967, `table_beginscan_bm` sets `SO_TYPE_BITMAPSCAN | SO_ALLOW_PAGEMODE`, and `SO_NEED_TUPLES` when the scan needs the tuples. It sets no `SO_ALLOW_STRAT` flag. REL_14_24 sets the same flags. `heapam.c` gives a scan the ring only when that flag is set, at the lines above. Rogov showed the index scan case on PostgreSQL 14, page 158. After a Seq Scan of his table, it held 32 buffers. After an Index Scan of the same table, "the buffer cache ends up containing the whole table and the whole index". Here is the whole picture. Rogov, pages 156 and 157, gives it for PostgreSQL 14, unless the row says otherwise. The ring sizes and the cap of 1/8 of the pool are the same in the 17 source, `freelist.c` lines 541 to 599:

| Uses a ring | Uses the normal pool |
|---|---|
| Seq Scan of a table larger than `shared_buffers` / 4: the bulk read ring, 256 kB | Index Scan, Rogov p. 158 |
| a second Seq Scan of the same table. A synchronized scan starts where the first scan is, so it finds those pages in the first scan's ring buffers. It still has its own 256 kB ring, `heapam.c` lines 453 to 458 | Bitmap Heap Scan, `tableam.h` at REL_14_24 and REL_17_11 |
| COPY FROM, CREATE TABLE AS SELECT and other table rewrites: the bulk write ring, 16 MB, at most 1/8 of the pool | UPDATE or DELETE of many rows. The scan uses a ring, but changed pages leave it, so rings "virtually become useless" |
| VACUUM: 256 kB in 14 and 15. 256 kB by default in 16, set by the new `vacuum_buffer_usage_limit`, at `postgresql.conf.sample` line 161 of REL_16_10. 2 MB since 17, at line 160 of REL_17_11 | TOAST values, which "are always accessed via an index, so they bypass buffer rings" |

Two notes apply. The bitmap row is verified in the 14, 17 and 18 sources. The 16 default of `vacuum_buffer_usage_limit` is verified from the REL_16_10 sample file. Rogov's PDF prints digits as special glyphs, which this course's research decoded by context. A nightly report with a date filter often runs as a Bitmap Heap Scan. So it can flood the pool even on PostgreSQL. That is inferred from the table. Read the report's plan first, in `EXPLAIN (ANALYZE, BUFFERS)`. On version 16 and later, `pg_stat_io` rows with the context `bulkread` count ring reads. Their `reuses` column counts buffers reused inside a ring. Verified from the PostgreSQL 17 docs, section 27.2.13.

`pg_buffercache_usage_counts()`, from section 2.1, shows the other side. Run it before and after the report. A report that flooded the pool leaves many buffers of its own table, at low usage counts, where the hot tables were. The per-relation query of section 2.1 names that table. That reading is inferred from the clock rules above. To log the report's real plan each night, load `auto_explain` and set `auto_explain.log_min_duration`, `log_analyze` and `log_buffers`. The 17 docs, F.3, say the module does nothing by default. `log_min_duration` is -1 by default, which disables logging, and `log_analyze` and `log_buffers` are off by default. On RDS, `shared_preload_libraries` is a static parameter, so this needs a custom parameter group and a reboot. Phase 4, section 4.1, teaches auto_explain. On Aurora the morning's misses go to the storage service. On Aurora Standard they count as billed reads, section 2.1. E14 runs both checks.

**InnoDB: an LRU with a midpoint.** MySQL 8.4's InnoDB keeps one LRU list in two parts. The MySQL 8.4 manual says "3/8 of the buffer pool is devoted to the old sublist". It also says: "When `InnoDB` reads a page into the buffer pool, it initially inserts it at the midpoint (the head of the old sublist)". A page moves to the young part only when it is accessed again. The setting `innodb_old_blocks_time` adds a condition. It is a time window in milliseconds after the first access. During it, a page "can be accessed without being moved to the front". The default is 1000. `innodb_old_blocks_pct` defaults to 37, which is 100 × 3 / 8 rounded down. Both defaults are verified in `ha_innodb.cc` at tag mysql-8.4.11, lines 23017 to 23027.

This design is close to 2Q, but it is not the same. The old part plays the role of A1in, and the young part plays the role of Am. The time window plays the role of 2Q's rule that a second access inside A1in does not count. InnoDB has no ghost list like A1out. So a page that leaves the old part is forgotten, and its next access starts from the old part again. This comparison is inferred from the two designs. The InnoDB manual does not cite 2Q.

**The failure: a time window of zero.** Set `innodb_old_blocks_time` to 0. A scan that reads several rows per page touches each page twice in a row. The second touch moves the page to the young part. So every scan page is promoted, and the scan pushes the hot pages out, as LRU would. The lab's self-test traces this by hand in a pool of 10 frames. With a window of 5 references, three hot pages survive a 15-page scan. With a window of 0, all three are evicted. The self-test asserts both traces, and it passes, as E1 records. E11 runs the same case at full size.

**The sentence to remember:** LRU loses every hot page to a scan larger than the pool. 2Q, ARC, InnoDB's midpoint and PostgreSQL's ring all keep a page used once from pushing out a page used often. PostgreSQL's ring guards against sequential scans, not index or bitmap scans.

**The trap:** setting `innodb_old_blocks_time` to 0. Or trusting PostgreSQL's ring with a report that runs as a Bitmap Heap Scan or an Index Scan. Each nightly report can then flood the buffer pool, and the morning's reads miss until the hot pages return.

**Try this now:** first predict which keeps a larger share of its no-scan hit rate. Then run `uv run python phase02_structures/cache_sim.py --policies lru,2q` and read the `kept` column.

---

## 2.9 — Vectors as a storage workload (pgvector: value size, TOAST, index size, build cost and vacuum)

Why this matters: agent features keep embeddings in PostgreSQL with pgvector. The retrieval-internals and advanced-retrieval courses teach search quality: recall, filters and quantization. This section teaches what the same table costs the database. Every tool it uses comes from sections 2.1 to 2.8.

**Answer this first.** A table holds 1 million embeddings of 1,536 dimensions, one per row, with a bigint id. How many bytes is one value? Does it stay in the heap row? How large is an HNSW index on the column: under 1 GB, about 8 GB, or about 60 GB? How much WAL does the index build write?

**The mental model.** pgvector is an extension. It adds the types `vector`, `halfvec` and `sparsevec`, and two index types, HNSW and IVFFlat. Its indexes also accept PostgreSQL's built-in `bit` type. HNSW is a graph index. Each vector links to its nearest neighbours, and a search walks the links. IVFFlat splits the vectors into lists around centres, and a search reads the closest lists. Two facts decide the storage cost. A row over 2,032 bytes moves its value to TOAST, section 2.2. And each index stores its own copy of every vector. So the vector bytes are paid at least twice, once in the table and once in the index.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One row of items, with a vector(1536). Sizes from vector_storage.py      │
├──────────────────────────────────────────────────────────────────────────┤
│ HEAP page of items   row = 24 header + 8 id + 18 TOAST pointer = 50      │
│         │ the pointer names the value in the TOAST table                 │
│         ▼                                                                │
│ TOAST table          4 chunk rows: 1,996 + 1,996 + 1,996 + 160 bytes,    │
│                      which fill most of one 8 kB TOAST page              │
│                      = the 6,148 data bytes of a 6,152-byte value        │
│                                                                          │
│ HNSW index page      element tuple 6,224 = 72 header + 6,152 value copy  │
│                      neighbour tuple 200 = 4 header + 32 links of 6,     │
│                      aligned to 8. m = 16                                │
│                      so one element fits on each 8 kB page               │
├──────────────────────────────────────────────────────────────────────────┤
│ 1 million rows: TOAST about 8.2 GB, index at least 1,000,001 pages,      │
│ 7.6 GiB. The vector bytes are paid twice. Inferred from the source       │
└──────────────────────────────────────────────────────────────────────────┘
```

### The value and the row

**Value sizes.** The pgvector README at v0.8.7 gives the size of each type, at lines 960, 998 and 1036, and the largest indexable value, at lines 252 to 254:

| Type | Bytes per value | At 1,536 dimensions | Largest value an index takes |
|---|---|---|---|
| `vector`, 4-byte floats | 4 × dimensions + 8 | 6,152 | 2,000 dimensions |
| `halfvec`, 2-byte floats | 2 × dimensions + 8 | 3,080 | 4,000 dimensions |
| `bit` | dimensions / 8 + 8 | 200 | 64,000 dimensions |

**TOAST.** pgvector declares `vector` and `halfvec` with `STORAGE = external`, at `sql/vector.sql` lines 39 and 483. External means out of line without compression, per the PostgreSQL 17 docs, section 65.2. A row of a bigint and a vector(1536) is 24 + 8 + 6,152 = 6,184 bytes. That is over the threshold, which `heapam.c` tests at line 2359, REL_17_11. So the value moves to the TOAST table in 4 chunks, and the heap row keeps an 18-byte pointer. The 4 chunk rows take 6,312 bytes of an 8,168-byte page. The 1,856 bytes left are too few for the next value's first chunk, so each value fills one TOAST page, from `hio.c`. A million rows then need about 1,000,000 TOAST pages, about 8.2 GB. The largest vector that stays inline next to a bigint has 498 dimensions. These numbers come from `vector_storage.py`. They are inferred from the source and were not measured.

Two things follow from TOAST:

1. **Reads.** Reading an embedding means a lookup in the TOAST table's index, then reads of its chunk pages. TOAST reads "bypass buffer rings", section 2.8. So a scan over the embeddings fills the normal pool. That is inferred.
2. **Plans.** The README says: "The planner doesn't consider out-of-line storage in cost estimates, which can make a serial scan look cheaper." It gives two fixes. The first lowers `min_parallel_table_scan_size` and `parallel_setup_cost` for one transaction, with `SET LOCAL`. The second is `ALTER TABLE items ALTER COLUMN embedding SET STORAGE PLAIN`.

**What PLAIN costs.** PLAIN keeps the value in the heap row. Each point below is inferred from the source, and `vector_storage.py` computes it:

- A vector(1536) row is then 6,184 bytes, so one row fits on each 8 kB heap page. A million rows are a million heap pages, 7.6 GiB, and every sequential scan reads them all.
- A halfvec(1536) row fits twice on a page.
- A vector(3072) row is 12,328 bytes. That is over `MaxHeapTupleSize`, 8,160 bytes. So an insert fails with `row is too big: size 12328, maximum size 8160`, from `hio.c` lines 532 to 536. Not run.
- The PostgreSQL 17 docs for ALTER TABLE say that "SET STORAGE doesn't itself change anything in the table". It only sets the strategy for future writes. So old rows stay in TOAST until they are written again.

**A real case.** Instacart moved its semantic search from FAISS, a vector search library, to pgvector. Its post of 29 May 2025, "How Instacart Built a Modern Search Infrastructure on Postgres", lists its index design changes. One is a storage change. It "Updated the embedding column to use inline storage instead of TOAST". Another is a tuning change. It raised `max_parallel_workers_per_gather` and `max_parallel_workers` to 8, which "speeds up the scans where Postgres decides not to use a pgvector index". The same post reports "a 10x reduction in write workload" from a normalized data model, against its earlier denormalized Elasticsearch model. Verified from the post. It does not give the table's size or the embedding's dimension count.

### The index

**Index size.** An HNSW element tuple holds a 72-byte header with ten heap TIDs, then a copy of the vector. That is `HnswElementTupleData`, `src/hnsw.h` lines 373 to 383, v0.8.7. Its neighbour tuple holds (level + 2) × m links of 6 bytes each, `HNSW_NEIGHBOR_TUPLE_SIZE` at line 82. `m` is 16 by default, at line 54. The build keeps an element and its neighbours on one page when both fit, at `hnswbuild.c` lines 192 to 229. So for a million vectors of 1,536 dimensions:

| Index | Elements per 8 kB page | Index size, lower bound |
|---|---|---|
| HNSW on `vector(1536)`, m = 16 | 1 | 1,000,001 pages, 7.6 GiB |
| HNSW on the expression `embedding::halfvec(1536)` | 2 | 500,001 pages, 3.8 GiB |
| HNSW on `binary_quantize(embedding)::bit(1536)` | 17 | 58,825 pages, 0.45 GiB |

Upper-level elements have larger neighbour tuples, so these sizes are lower bounds. They are inferred from the struct sizes. The self-test of `vector_storage.py` checks the first two. For bit it measures over 1,000 elements and gets 59 pages, so it prints 16.9 per page, where whole pages hold 17. They were not measured on a server.

The index is at least as large as the vectors, so section 2.1 decides its speed. Each graph step loads the unvisited neighbours of one candidate, up to 2 × m = 32 at the lowest level, at `hnswutils.c` lines 891 to 933. At one element per page, each neighbour is a page read when it misses the pool: 89 µs on the laptop, about 1 ms on gp3. So one search can pay hundreds of reads. That count is inferred from the code and the layout. The README gives two ways to shrink the working set. The first is "Use the halfvec type instead of vector for a smaller working set". The second is "Use binary quantization with re-ranking to keep indexes in-memory at scale". The retrieval-internals course, Phase 2, section 2.2, and Phase 4, section 4.4, measure memory per vector and the recall that quantization costs.

### The build: memory and WAL

**Build memory.** The comment at the top of `hnswbuild.c` says the build "happens in two phases". In the first, "the graph is held completely in memory". When it runs out of the memory "determined by maintenance_work_mem", it writes the graph to disk. Then it inserts each remaining vector "one by one, just like on INSERT". That second phase is much slower, and the README shows the notice it prints:

```text
NOTICE:  hnsw graph no longer fits into maintenance_work_mem after 100000 tuples
DETAIL:  Building will take significantly more time.
HINT:  Increase maintenance_work_mem to speed up builds.
```

The graph holds each vector plus a list of 2 × m candidate neighbours of 16 bytes each. So it needs at least 6,152 + 512 = 6,664 bytes per element for vector(1536), and at least 6.7 GB for a million. That is a lower bound inferred from the structs. `maintenance_work_mem` is 64MB by default, at `postgresql.conf.sample` line 142, REL_17_11. Two AWS pages disagree for RDS. The memory page says 64 MB. The autovacuum page gives `GREATEST({DBInstanceClassMemory/63963136*1024},65536)` in kB, about 500 MB on 32 GiB. Check yours with `show maintenance_work_mem`.

Since pgvector 0.8.4, IVFFlat fails instead of slowing down. Older versions, such as 0.8.2 on RDS 17.11, use more memory than `maintenance_work_mem` and do not stop, per the 0.8.4 CHANGELOG entry. Its build holds the list centres and 50 samples per list, at least 10,000 samples. Since 0.8.5 the samples are also capped at the heap's pages times 291, at `ivfbuild.c` lines 400 and 456 to 466. When that passes `maintenance_work_mem`, `ivfutils.c` lines 126 to 133 raise an error. A million vectors with the README's starting point of 1,000 lists need 51,000 × 6,152 bytes, about 300 MB. So at the default:

```text
ERROR:  memory required is 300 MB, maintenance_work_mem is 64 MB
```

That message is computed by `vector_storage.py` from the source. It was not run. Raise the memory for one session only, as the README does with `SET maintenance_work_mem = '8GB'`. The README also warns: "Do not set `maintenance_work_mem` so high that it exhausts the memory on the server". On Aurora, about 75% of memory already belongs to `shared_buffers`, section 2.1. So less room is left for a build. That is inferred. A parallel HNSW build holds its graph in shared memory, per the same comment in `hnswbuild.c`. In Docker, the README says to make `--shm-size` at least `maintenance_work_mem` "to avoid an error with parallel HNSW index builds".

**WAL of a build.** After the graph is built, the comment says, "we perform one more scan through the index and write all the pages to the WAL". The call is `log_newpage_range`, at `hnswbuild.c` lines 1142 to 1143. IVFFlat registers each new page with `GENERIC_XLOG_FULL_IMAGE`, at `ivfutils.c` line 166. Each page image leaves out the page's free space, at `xloginsert.c` lines 655 to 669, REL_17_11. A vector(1536) HNSW page has about 1,728 free bytes, so its image is about 6,464 bytes. So a build writes about 79% of the index size into the WAL, about 6.0 GiB for 1M vector(1536) rows. For HNSW most of it comes at the end, at once. The total is inferred from the code, and it ignores compression and record headers.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ What a vector index build does to the server, 1M vector(1536) rows       │
├──────────────────────────────────────────────────────────────────────────┤
│ t=0     CREATE INDEX starts. The graph grows in maintenance_work_mem     │
│         at least 6,664 bytes per vector: 6,152 value + 512 links         │
│ t=1     past 64 MB, about 10,000 vectors in: the NOTICE. The rest of     │
│         the vectors go in one by one, as INSERTs do, and run slower      │
│ t=end   log_newpage_range writes every index page into the WAL,          │
│         without its free space: about 6.0 GiB in one burst               │
│ after   checkpoints come early, replicas replay 6.0 GiB, archive grows   │
├──────────────────────────────────────────────────────────────────────────┤
│ times are steps, not seconds. 10,000 is 64 MiB / 6,664 bytes, from a     │
│ lower bound on memory, so the real count is lower. All inferred          │
└──────────────────────────────────────────────────────────────────────────┘
```

What that burst does to a server, each point inferred from the WAL volume:

- With `max_wal_size` at 1GB, the burst requests checkpoints early, as Phase 1, section 1.5, explained.
- Every streaming replica must receive and replay the same bytes, so replica lag rises. Phase 5, section 5.1, measures that lag in bytes and in seconds.
- The WAL archive and the next backup grow by the same amount. Phase 5, section 5.6, covers the archive and base backups.

Measure it with `pg_current_wal_lsn()` before and after the build, as E16 does. The README also says: "In production environments, create indexes concurrently to avoid blocking writes", with `CREATE INDEX CONCURRENTLY`.

### Deletes, VACUUM and versions

**Deletes and VACUUM.** A delete leaves a dead heap tuple and a dead element in the index. HNSW's VACUUM makes four passes, at `hnswvacuum.c` lines 785 to 792. It removes heap TIDs, repairs the graph, then confirms the repair and marks elements deleted. The repair pass finds new neighbours for every element that lost some, so it runs graph searches, not only page writes. Its page scans read through a 256 kB bulk-read ring, set at `hnswvacuum.c` line 747. The graph searches of the repair pass use the normal pool, at `hnswutils.c` line 546. So a large repair can still fill the pool. The README says: "Vacuuming can take a while for HNSW indexes. Speed it up by reindexing first", with `REINDEX INDEX CONCURRENTLY` and then `VACUUM`.

A deleted element's slot is reused by a later insert, at `hnswinsert.c` line 212. So the index file keeps its size, as a B-tree does in section 2.2. VACUUM VERBOSE prints the page line of section 2.2 for this index too. pgvector's cleanup function fills in only the page count, at `hnswvacuum.c` line 815. So the other three numbers print as 0. That is inferred from the code.

**Versions.** pgvector 0.8.3 "Fixed possible index corruption with HNSW vacuuming". 0.8.4 "Fixed `hnsw graph not repaired` error with HNSW vacuuming". 0.8.4 also "Fixed memory exceeding `maintenance_work_mem` with IVFFlat index builds", and 0.8.7 "Fixed buffer overflow with IVFFlat index build". All are verified from the CHANGELOG at v0.8.7. RDS for PostgreSQL 17.11 lists pgvector 0.8.2 on the AWS extension versions page, read on 2026-10-20. So that RDS version has none of these fixes. That follows from the version order. Check yours with `select extversion from pg_extension where extname = 'vector';`. The retrieval-internals course, Phase 7, sections 7.1 and 7.3, covers deletes from the search side.

**SERIALIZABLE.** HNSW and IVFFlat set `ampredlocks = false`, at `src/hnsw.c` line 348 and `src/ivfflat.c` line 265. For such an index, PostgreSQL 17 takes a predicate lock on the whole index at the start of a scan, `indexam.c` lines 319 to 320. It checks the whole index for conflicts on every insert, lines 225 to 228. So a serializable vector search conflicts with every concurrent insert into that index by another serializable transaction, `predicate.c` line 4330. Each conflict is one rw-dependency, not an abort. An abort needs the dangerous structure of section 3.5. The code is verified. The abort rate is inferred and not measured. Phase 3, section 3.5, explains predicate locks.

**Where you see it.** The signals for this workload:

| Question | Command or signal | Expected for 1M vector(1536) rows |
|---|---|---|
| how large is one value | `select pg_column_size(embedding) from items limit 1` | 6,148 bytes. For a TOASTed value it counts the stored bytes without the 4-byte header, `detoast.c` lines 606 to 616, REL_17_11. A PLAIN row shows 6,152 |
| where do the bytes sit | `select pg_size_pretty(pg_relation_size('items')), pg_size_pretty(pg_table_size('items'))` | a small heap, and a table size that includes about 8.2 GB of TOAST |
| how large is the index | `select pg_size_pretty(pg_relation_size('items_embedding_idx'))` | at least 7.6 GiB for HNSW |
| does the build fit | the NOTICE above, and `pg_stat_progress_create_index` | the NOTICE at 64 MB |
| does a search miss the pool | `EXPLAIN (ANALYZE, BUFFERS)` of one search, as the README advises | `read` counts close to the graph steps |
| on RDS or Aurora | Performance Insights `IO:DataFileRead` during searches | rises when the index outgrows the pool |

The expected column is inferred from this section and was not run. The 8.2 GB of TOAST is this course's arithmetic. Three full chunk rows of 2,032 bytes, one short row of about 200, and four line pointers are about 6,312 bytes per vector. The rest of the page cannot hold the next value's first chunk, so each vector takes one 8 kB page.

**The sentence to remember:** a pgvector table pays for every vector twice, once in TOAST or the heap and once in the index. An HNSW index of vector(1536) holds one element per page, so it is at least as large as the vectors.

**The trap:** building an HNSW index on a large table at the default `maintenance_work_mem` of 64 MB. The build leaves memory after about 10,000 vectors, or fewer, and runs much slower. Its end then writes the whole index into the WAL at once, and every replica must replay it, Phase 5, section 5.1.

**Try this now:** run `uv run python phase02_structures/vector_storage.py --rows 4000000`, then the same with `--type halfvec`. Compare each index size with your `shared_buffers`. Then say which of the three index rows above you would build, and what recall test you would run first.

---

## 🧪 Hands-on lab

**Run status, 2026-10-20.** The author ran every self-test of Phases 1 and 2, and the commands of E15, on an Apple M4 Pro with macOS 26.6 and Python 3.12.14 under uv. Those outputs are real, and E1 and E15 quote them. The first run of the self-tests failed in `cache_sim.py`, and E1 gives the cause and the fix. Every other exercise was written and reviewed, but not run by the author. Its "Expected" line says "Not run by the author yet." and then gives the expected shape. Each number in it comes from arithmetic in this phase or from a cited source. Some come from working through the code and its seed by hand. None of them is a measurement. The byte and block counts have no randomness that depends on time. With the same flags and seed, they should match the arithmetic exactly or closely, as each exercise says. The latency numbers come from a model, not from your SSD.

**What you build.** The lab extends the Phase 1 store in two directions. `bitcask_merge.py` adds segments, merge and hint files to the Phase 1 log. `lsm.py` builds an LSM tree on the Phase 1 entry format. Both run on the simulated file system of Phase 1, `fsim.py`, through a wrapper that counts every byte:

| File | What it holds | Self-test checks |
|---|---|---|
| `phase02_structures/counting.py` | `CountingFS`: bytes written and read, and blocks touched, per category | block counts against hand-worked offsets |
| `phase02_structures/btree_model.py` | the height, memory and write arithmetic of section 2.2, with the heap page and each index leaf of a row change | the numbers of section 2.2, and a row change that counts more than one page |
| `phase02_structures/bitcask_merge.py` | segments, merge, hint files, and a crash test of the merge | the merge numbers of section 2.4, both crash-test counts |
| `phase02_structures/lsm.py` | memtable, WAL, flush, L0 and L1, compaction, a Bloom filter per run. Each data block starts on a 4,096-byte boundary, as RocksDB's `block_align` option does. That option is false by default, at `table.h` line 772, v11.8.1 | each rule of `Rules`, removed one at a time, fails a check. A get that probes one run reads one device block |
| `phase02_structures/bloom.py` | the standard and the blocked Bloom filter, theory and measurement | the FPR formula against section 2.5, no false negatives |
| `phase02_structures/amplification.py` | the two layouts under two workloads, the range demo, the latency model | log write amplification 133 / 113, LSM against log, at-once against paced |
| `phase02_structures/cache_sim.py` | LRU, LFU, 2Q, ARC, PostgreSQL's clock and ring, InnoDB's midpoint | hand-worked traces of section 2.8, ARC's invariants |
| `phase02_structures/vector_storage.py` | the storage arithmetic of section 2.9: value sizes, TOAST, PLAIN rows per page, HNSW elements per page, build memory, the IVFFlat error | the PostgreSQL 17 and pgvector 0.8.7 constants, the sizes of section 2.9, and the keep-together rule, which a mutant without it fails |

The demonstration of this phase is four exercises. E6 gives read, write and space amplification for two layouts under two workloads. E9 shows the compaction storm in the latency histogram. E8 gives the Bloom filter's measured FPR against its memory. E10 gives the LRU and 2Q hit rates under a scan.

All commands run from `elite-storage/code/`.

- [ ] **E1 (offline).** Run every self-test of this phase and of Phase 1. This phase imports Phase 1's code.
  - Run: `for f in phase02_structures/*.py phase01_durability/*.py shared/durable.py; do echo "$f"; uv run python "$f" --self-test; done`
  - Expected, run by the author on 2026-10-20: `self-test passed` after each of the 13 files. The Phase 2 self-tests assert the numbers of sections 2.2, 2.4, 2.5 and 2.9, so a pass also checks that arithmetic.
  - The first run failed. `cache_sim.py --self-test` stopped with `KeyError: 99` in `TwoQ.access`, on the mixed trace near its end. The cause: when a page whose number is in A1out comes back, `_reclaimfor` may first page out the tail of A1in and trim A1out. If the returning page's own number was the oldest entry of a full A1out, that trim dropped it, and the next line's `del` failed. The fix keeps the paper's order, reclaim and then add to Am, and removes the number only if it is still there. It is at `cache_sim.py:191`. The earlier "every self-test passes" was never run, so this bug sat in a file that only `py_compile` had checked.
  - If it fails: the assertion message names the number that differs. Compare it with the section that the test names before you change any code.
  - Teaches: each rule the text calls important has a check that fails without it.

- [ ] **E2 (offline).** The height and memory of a B-tree.
  - First write your prediction for 10 million and for 1 billion keys: height, and memory above the leaves.
  - Run: `uv run python phase02_structures/btree_model.py --keys 10000000`, then the same with `--keys 1000000000`, then `uv run python phase02_structures/btree_model.py --leaf-fill 0.67`.
  - Expected: Not run by the author yet. For 10 million keys: levels of 27,323, 96 and 1 pages, height 3, and 776 KiB above the leaves. For a billion: height 4, and 9,622 pages above the leaves. The write model prints 165.3, 17.9 and 3.1 bytes per byte changed. With `--leaf-fill 0.67`, a leaf holds 273 entries, so 10 million keys need 36,631 leaves. That is about 1.34 times as many, close to 0.90 / 0.67.
  - Then run: `uv run python phase02_structures/btree_model.py --indexes 2 --heap-changes-per-page 6`.
  - Expected: Not run by the author yet. The row-change line for leaves at c = 1 prints 35,949 bytes. That is 2,881 for the heap page and 16,534 for each of the two leaves, from section 2.2.
  - Teaches: a B-tree needs memory for its inner levels only, which is a few hundred pages per million keys. A PostgreSQL row change writes more than one page.

- [ ] **E3 (offline).** Bitcask merge and hint files.
  - Run: `uv run python phase02_structures/bitcask_merge.py --demo`.
  - Expected: Not run by the author yet. Live data 229,900 bytes. Before the merge, 738,300 bytes on disk, space amplification 3.21. The merge reads 12 files and writes 233,700 bytes of data and 7,220 bytes of hints. After it, 240,920 bytes on disk, space amplification 1.05. A restart reads 738,300 bytes before the merge, 233,700 after it without hints, and 7,220 with them.
  - Teaches: merge turns space amplification back to about 1, and hint files make a restart read keys without values.

- [ ] **E4 (break-it, offline).** Crash the merge at every step, in the right order and the wrong one.
  - Run: `uv run python phase02_structures/bitcask_merge.py --crash-test`, then add `--unsafe-remove-first`.
  - Expected: Not run by the author yet. The right order has 6 crash steps, each tried with three crash kinds, so 18 recoveries. It prints `RESULT: 0 violations in 18 recoveries`. The wrong order has 5 steps, so 15 recoveries. It prints two lines for `merge.dir-synced`, one for `os` and one for `power`. Each says all 36 live orders were lost. Then `RESULT: 2 violations in 15 recoveries`.
  - If it fails with "step ... was never reached": a hook name in `merge` changed. Compare `MERGE_STEPS_SAFE` with the hook calls.
  - Teaches: compaction replaces files, so it needs the checkpoint's order. New data is durable first, then new names, then the removal.

- [ ] **E5 (offline).** Watch an LSM tree flush and compact.
  - Run: `uv run python phase02_structures/lsm.py --demo`.
  - Expected: Not run by the author yet. 23 `flush` lines and 5 `compaction` lines. There are five groups of four flushes, each followed by one compaction into L1 with `tombstones dropped`. Then come three more flushes. The levels then show a memtable of 192 keys and three L0 runs of 126 keys. L1 holds one run of 2,000 keys. These counts are worked out from the code. Then the counters: device bytes for `wal`, `flush` and `compaction`, with `compaction` the largest. Write amplification is well above the log's 1.18.
  - The arithmetic behind the compaction cost: L1 holds 20,000 entries of 133 bytes, 30 to a 4,096-byte block. That is 667 blocks, about 2.73 MB, and the run's index and filter add about 0.04 MB. A memtable flushes at 64 KiB, which is 493 distinct keys and about 499 puts, because some keys repeat. So 4 L0 runs bring about 4 × 499 × 113 bytes = 0.23 MB of new data. Each compaction then writes about 2.78 MB for it, about 12.3 bytes per byte. Worked out from the code, not run.
  - Teaches: the cheap part of an LSM write happens at once, and the expensive part happens at compaction.

- [ ] **E6 (offline).** The main demonstration: amplification of two layouts under two workloads.
  - First write your prediction for each cell of the table in section 2.6.
  - Run: `uv run python phase02_structures/amplification.py`, then `uv run python phase02_structures/amplification.py --range-demo`.
  - Expected: Not run by the author yet. Four rows. The `log` rows show write amplification 1.18. They read about 1.03 blocks per present get and 0 per absent get. Their space amplification is 11.77 on write-heavy and 2.35 on read-heavy. The `lsm` rows show write amplification about 14.7. They read about 1.0 block per present get and 0.02 per absent get. Their space amplification is about 1.25. The range demo shows 103 blocks and 20,000 keys checked for `log`, and 4 blocks for `lsm`. The byte counts and the range counts are worked out from the code and its seed. The block counts per get are estimates, because they depend on Bloom filter false positives.
  - Where the numbers come from, worked out from the code, its defaults and seed 1, not run. An entry is 20 + 13 + 100 = 133 bytes for 113 bytes of key and value. So the log writes 133 / 113 = 1.18. Seed 1 makes 179,952 of the 200,000 write-heavy operations puts, and 19,883 of the read-heavy ones. So the log's space is 199,952 × 133 / 2,260,000 = 11.77, and 39,883 × 133 / 2,260,000 = 2.35. Its 1.03 blocks per get comes from entries that cross a block boundary: 132 of every 4,096 start offsets do. The LSM's 14.7 adds the WAL, 1.18, the flush, about 1.22, and the compaction, about 12.3 from E5. A flush and a compaction write a little more than their entries. Each run also holds its index, its filter and its block padding. The LSM's space is L1 plus a few L0 runs and the log.
  - If a row is far from the table: check the header line against the defaults. The table in section 2.6 assumes 20,000 keys, 100-byte values, 200,000 operations and 10 bits per key.
  - Teaches: the log and the LSM read alike with filters on. They differ in write and space amplification, in opposite directions.

- [ ] **E7 (break-it, offline).** Remove the Bloom filters.
  - Run: `uv run python phase02_structures/amplification.py --layouts lsm --bloom-bits 0`.
  - Expected: Not run by the author yet. Blocks per absent get rise from about 0.02 to about 2.5. That is one block per run that covers the key, and there are 1 to 4 runs. Blocks per present get rise above 1, because L0 runs above L1 are now read too. Write amplification falls a little, because no filter bytes are written.
  - Teaches: a filter costs a few bits per key of memory and removes almost every wasted block read.

- [ ] **E8 (offline).** Part of the demonstration: the measured FPR against the filter's memory.
  - First predict the measured FPR at 4 and at 10 bits per key, from the table in section 2.5.
  - Run: `uv run python phase02_structures/bloom.py --keys 100000 --probes 200000 --blocked`.
  - Expected: Not run by the author yet. Seven rows from 2 to 16 bits per key. The memory column is 100,000 × bits / 8 bytes, so 125,000 bytes at 10 bits. The measured standard FPR sits within a few standard errors of theory, near 0.82% at 10 bits. The blocked column is a little higher, near the wiki's 0.95% at 10 bits.
  - The code is at `bloom.py:111`. `add` sets the k bits of a key, and `may_contain` returns False at the first zero bit. `_positions` computes all k positions from one BLAKE2b hash as h1 + i × h2, which is called double hashing. The theory assumes k independent hashes, so a measurement can differ a little from it.
  - Teaches: FPR falls by about 10 for each 4.8 bits per key. A cache-line layout costs a factor of about 1.13.

- [ ] **E9 (break-it, offline).** Part of the demonstration: the compaction storm in the latency histogram.
  - Run: `uv run python phase02_structures/amplification.py --layouts lsm --workloads write-heavy --latency --compaction at-once`, then the same with `--compaction paced`.
  - Expected: Not run by the author yet. The at-once run prints 451 background jobs: 361 flushes and 90 compactions, the largest about 4.2 ms. The job counts are worked out from the code and its seed. Its put p50, the median, is under 1 µs, and its put p99 is a few milliseconds. Its histogram has a group of operations between 1,000 and 5,000 µs. The paced run has the same jobs, and a put p99 well under 1 ms. Its largest latencies stay under about 1 ms, with `0 write stops`.
  - The timeline behind it: four flushes come about 27.7 ms apart. The L0 to L1 merge starts at about 110.8 ms. The merge reads about 2.92 MB at 2,000 MB/s, which is 1.5 ms. It writes about 2.78 MB at 1,000 MB/s, which is 2.8 ms. That is 4.2 ms in all. Gets, puts and flushes keep the device busy about 17% of the time. If the background work grows past `--stall-ms`, 50 ms by default, the next put waits for all of it. That is the model's write stop. These numbers are worked out from the model's defaults and the seed, not run.
  - Then break it: run the paced command again with `--rate 60000 --write-mbps 150`. The device then needs about 1.1 seconds of work per second. Compactions of about 20 ms each, 27 per second, need about 0.54. Gets need 0.48, and puts and flushes 0.1. That arithmetic uses the defaults of section 2.4. The backlog grows without limit, so expect a non-zero `write stops` count and puts that wait tens of milliseconds.
  - Teaches: compaction run at once causes a storm. Compaction that cannot keep up causes a stall.

- [ ] **E10 (offline).** Part of the demonstration: LRU against 2Q under a scan.
  - First predict which keeps the larger share of its no-scan hot hit rate.
  - Run: `uv run python phase02_structures/cache_sim.py --policies lru,2q`.
  - Expected: Not run by the author yet. A header line with scans at 33% of 450,000 references. Two rows. LRU's `kept` value is lower than 2Q's. The 2Q paper's own test kept about 60% for LRU and about 70% for 2Q. Its trace was different, so expect the same direction, not the same numbers.
  - The code is `TwoQ.access` at `cache_sim.py:181`. `_reclaimfor`, at `cache_sim.py:166`, frees a frame. It takes the oldest page of A1in when A1in is over Kin, and puts its number into A1out. Otherwise it takes the oldest page of Am, without a ghost entry. The self-test traces a pool of 4 frames by hand. A hot page reaches Am. Then a scan of 6 new pages passes through A1in and A1out, and the hot page still hits afterwards. The self-test asserts that trace, and it passes, as E1 records.
  - Teaches: a policy that waits for a second access keeps hot pages through a scan.

- [ ] **E11 (break-it, offline).** All seven policies, and two ways to break scan resistance.
  - Run: `uv run python phase02_structures/cache_sim.py --policies all`.
  - Then run: `uv run python phase02_structures/cache_sim.py --policies midpoint --scan-touches 4`, then the same with `--old-time 0`.
  - Expected: Not run by the author yet. In the first table, `clock-ring` keeps more of its hit rate than `clock`, because the scan cycles through 32 buffers. `arc` and `2q` keep more than `lru`. In the midpoint pair, the window of 1,000 references keeps the hot hit rate near its no-scan value. With `--old-time 0`, every scan page is promoted on its second touch, and `kept` falls toward LRU's.
  - Teaches: InnoDB's time window and PostgreSQL's ring are the parts that make each system resist scans.

- [ ] **E12 (local, PostgreSQL 17).** See PostgreSQL's ring with `EXPLAIN`, and the scan that does not use it.
  - If `storage_lab` does not exist, run `createdb -h /tmp -p 5432 storage_lab` first.
  - Run: `psql -h /tmp -p 5432 -d storage_lab -c "create table scan_big as select g as id, repeat('x', 200) as pad from generate_series(1, 400000) g" -c "create table scan_small as select g as id, repeat('x', 200) as pad from generate_series(1, 50000) g"`.
  - Then run: `psql -h /tmp -p 5432 -d storage_lab -c "show shared_buffers" -c "select relname, pg_relation_size(oid) / 8192 as pages from pg_class where relname in ('scan_big', 'scan_small')"`.
  - Then run this twice, and read the second output: `psql -h /tmp -p 5432 -d storage_lab -c "explain (analyze, buffers) select count(*) from scan_big" -c "explain (analyze, buffers) select count(*) from scan_small"`.
  - Expected: Not run by the author yet. With the default 128 MB, the ring threshold is a quarter of 16,384 buffers: 4,096 pages. A row here is about 236 bytes, so about 34 rows fit on a page. That is an estimate from the row layout of section 2.2, not checked. So `scan_big` has about 11,800 pages, and `scan_small` about 1,500. On the second run, `scan_small` should show `shared hit` for almost every page and no `read`. `scan_big` should show mostly `read`, although its 92 MiB would fit in the 128 MB pool. Expect up to about 2,000 `shared hit` pages too. CREATE TABLE AS writes through a 16 MB ring, and its last pages stay in the pool. That is inferred from `freelist.c` lines 541 to 599. The ring keeps the scan to a few buffers. Its reads come from the OS page cache, so the scan is still fast. That last point is inferred, not measured.
  - The planner may choose a `Parallel Seq Scan` for `scan_big`. Each worker then gets its own ring, because the ring rule runs for each process that scans. That is inferred from `heapam.c` lines 445 to 452, REL_17_11. Read the plan before you read the counts. On 18, the ring is about 94 buffers, and a fresh 18 cluster has data checksums on. So if a checkpoint runs between `create table ... as` and the first scan, that scan writes hint-bit page images. Either way, only the second run is clean. Both 18 points are inferred.
  - Then break the ring: `psql -h /tmp -p 5432 -d storage_lab -c "create index on scan_big (id)" -c "vacuum analyze scan_big"`. Run this twice, and read the second output: `psql -h /tmp -p 5432 -d storage_lab -c "set enable_seqscan = off" -c "set enable_indexscan = off" -c "explain (analyze, buffers) select count(pad) from scan_big where id <= 300000"`.
  - Expected: Not run by the author yet. The plan is a `Bitmap Heap Scan` over about 300,000 / 34 = 8,800 heap pages. On the second run, it should show `shared hit` for almost all of them. The Seq Scan of the same table did not. So the bitmap scan kept its pages in the normal pool, as section 2.8's table says. The page count is the estimate above, not checked.
  - Clean up: `psql -h /tmp -p 5432 -d storage_lab -c "drop table scan_big, scan_small"`.
  - Teaches: PostgreSQL protects its buffer pool from large sequential scans with a ring. A bitmap heap scan of the same table fills the normal pool.

- [ ] **E13 (local, PostgreSQL 17).** A real B-tree page, and the WAL of inserts with a sequence key and a random key.
  - Run: `psql -h /tmp -p 5432 -d storage_lab -c "create extension if not exists pageinspect" -c "create extension if not exists pgstattuple"`. Both ship with PostgreSQL. The PostgreSQL 17 pageinspect docs say: "All of these functions may be used only by superusers". Your local role is normally a superuser, which is not checked.
  - Run: `psql -h /tmp -p 5432 -d storage_lab -c "create table k_seq (id bigint generated always as identity primary key, pad text)" -c "create table k_uuid (id uuid primary key default gen_random_uuid(), pad text)"`. Both tables have only a primary key, as in Vondra's test.
  - Load each table in 20 batches of 50,000 rows, with a checkpoint after each batch. So every batch starts a new cycle of full page images, and each leaf a batch touches pays one. This shell loop does it, and prints `pg_stat_wal`, verified in the PostgreSQL 17 docs, Table 27.26. The reset target `wal` is accepted at `pgstatfuncs.c` line 1746, REL_17_11:

    ```bash
    for t in k_seq k_uuid
    do
      psql -h /tmp -p 5432 -d storage_lab -q -c "checkpoint" -c "select pg_stat_reset_shared('wal')"
      for i in $(seq 1 20)
      do
        psql -h /tmp -p 5432 -d storage_lab -q \
          -c "insert into $t (pad) select repeat('x', 100) from generate_series(1, 50000)" -c "checkpoint"
      done
      psql -h /tmp -p 5432 -d storage_lab -c "select pg_sleep(1)" \
        -c "select '$t' as tab, wal_records, wal_fpi, pg_size_pretty(wal_bytes) as wal from pg_stat_wal"
    done
    ```

  - Then read both indexes: `psql -h /tmp -p 5432 -d storage_lab -c "select 'seq' as k, level from bt_metap('k_seq_pkey') union all select 'uuid', level from bt_metap('k_uuid_pkey')" -c "select 'seq' as k, leaf_pages, avg_leaf_density from pgstatindex('k_seq_pkey') union all select 'uuid', leaf_pages, avg_leaf_density from pgstatindex('k_uuid_pkey')" -c "select live_items, avg_item_size, free_size from bt_page_stats('k_seq_pkey', 1)" -c "select itemoffset, ctid from bt_page_items('k_seq_pkey', 1) limit 3"`.
  - Expected: Not run by the author yet. `wal_fpi` for `k_uuid` should be many times that of `k_seq`, because each batch touches nearly every UUID leaf. The heap pages cost both tables about the same, since both fill the heap in arrival order. The direction is inferred from section 2.2 and Vondra's result, and the counts are not predicted. `pg_stat_wal` counts the whole cluster, so other activity on the server adds to both rows. `pg_stat_reset_shared('wal')` also clears it for the whole cluster, so run E13 only on your laptop. The `pg_sleep` gives the statistics a moment to arrive. Since PostgreSQL 15 a backend sends its statistics when it exits, at `pgstat.c` lines 504 to 518, REL_17_11. So on 17 the sleep is only a margin. On 18, data checksums are on in a new cluster, so hint-bit changes from other activity can add page images to both rows. That is inferred from the 18 default. `bt_metap` should show level 2, a height of 3, for both. `k_seq_pkey` should show an `avg_item_size` of 16, as the docs' example does for a 4-byte key. Its leaf density should be near 90. `k_uuid_pkey` has 24-byte items and a lower density, because random keys split pages in the middle. `bt_page_items` shows each entry's `ctid`, the heap TID that the leaf points to.
  - Clean up: `psql -h /tmp -p 5432 -d storage_lab -c "drop table k_seq, k_uuid"`.
  - Teaches: one schema decision, the key type, changes the WAL volume of the same inserts. The counters to watch are `wal_fpi` and `wal_bytes`.

- [ ] **E14 (local, PostgreSQL 17).** Look inside the pool, and at the I/O of one scan.
  - Needs `scan_big` from E12, with its index. Create them again if you cleaned up. Then restart your server, so that the pool no longer holds the pages that E12's bitmap scan and CREATE TABLE AS left there. Without the restart, `scan_big` holds thousands of buffers, not the ring.
  - Run: `psql -h /tmp -p 5432 -d storage_lab -c "create extension if not exists pg_buffercache" -c "select pg_stat_reset_shared('io')" -c "explain (analyze, buffers) select count(*) from scan_big"`.
  - Then run: `psql -h /tmp -p 5432 -d storage_lab -c "select * from pg_buffercache_usage_counts()" -c "select c.relname, count(*) as buffers from pg_buffercache b join pg_class c on b.relfilenode = pg_relation_filenode(c.oid) where c.relname like 'scan_big%' group by 1" -c "select backend_type, context, reads, hits, reuses from pg_stat_io where object = 'relation' and reads > 0 order by reads desc"`.
  - Expected: Not run by the author yet. `scan_big` holds about 32 buffers, the ring of section 2.8. Rogov saw 32 after a Seq Scan on 14, page 158. A Parallel Seq Scan can hold up to 32 per process. In `pg_stat_io`, a row with context `bulkread` holds most of the scan's 11,800 reads, and its `reuses` is close to that count minus the ring. With parallel workers, `background worker` rows share the reads.
  - Then run the bitmap scan of E12 again, and repeat the second command. Expected: `scan_big` now holds about 8,800 buffers, and the reads appear under context `normal`. That is the flood of section 2.8, seen from inside the pool.
  - If `pg_stat_statements` is in `shared_preload_libraries`, run `create extension if not exists pg_stat_statements`, then the top-reads query of section 2.1. Expected: the two `explain (analyze, buffers) select count(*) ...` entries lead by `shared_blks_read`. They are tracked as utility statements, at `pg_stat_statements.c` line 1106, REL_17_11. If the module is not loaded, the query fails with `pg_stat_statements must be loaded via "shared_preload_libraries"`, from `pg_stat_statements.c` line 1657, REL_17_11.
  - If it fails: `pg_buffercache` needs a superuser or `pg_monitor`. `pg_stat_reset_shared` needs a superuser or a grant, because `system_functions.sql` line 674, REL_17_11, revokes it from public.
  - Teaches: which table holds the pool, which kind of read filled it, and which statement caused it.

- [ ] **E15 (offline).** What one embedding costs, in heap pages, TOAST, index pages, build memory and WAL.
  - First predict for 1 million vector(1536) rows: the value size, whether it is TOASTed, and the HNSW index size.
  - Run: `uv run python phase02_structures/vector_storage.py`, then the same with `--dims 3072`, then with `--rows 4000000`, then with `--rows 4000000 --type halfvec`.
  - Expected, run by the author on 2026-10-20. The first command prints, among its lines:

    ```
    value: 6,152 bytes. row before TOAST: 6,184 bytes, threshold 2,032
    TOAST: the value moves out of line in 4 chunks of up to 1,996 bytes. The heap row keeps 50 bytes
    largest vector that stays inline here: 498 dimensions
    SET STORAGE PLAIN: rows per heap page 1, 1,000,000 pages = 7.6 GiB of heap
    HNSW m=16: element tuple 6,224 bytes, neighbour tuple 200 bytes, 1.0 elements per page
    HNSW index: at least 1,000,001 pages = 7.6 GiB. The end of the build writes every page to the WAL once, so about 7.6 GiB of WAL
    HNSW graph in memory: at least 6.7 GB against maintenance_work_mem 64 MB, does not fit: expect the notice
    IVFFlat lists=1,000: build memory 299 MiB. ERROR: "memory required is 300 MB, maintenance_work_mem is 64 MB"
    ```

  - With `--dims 3072`, the PLAIN line says `inserts fail with "row is too big: size 12328, maximum size 8160"`, and the index line says `column cannot have more than 2000 dimensions for hnsw index`. With 4 million rows, the HNSW index is at least 30.5 GiB, and at least 15.3 GiB as halfvec. The script's WAL line overstates the WAL: a page image leaves out the page's free space, so expect about 6.0 GiB for the first command, section 2.9.
  - Where the numbers stop matching a server: the model counts only level-0 neighbour tuples, and only the lower bound of the build's memory. Section 2.9 lists what it leaves out.
  - Teaches: the vector bytes are paid in the table and again in the index, and the build's memory and WAL follow from the index size.

- [ ] **E16 (break-it, local, PostgreSQL 17 with pgvector).** Build an index past `maintenance_work_mem`, measure its WAL, and break an IVFFlat build.
  - First install pgvector in `storage_lab`, and print the version that your server has: `psql -h /tmp -p 5432 -d storage_lab -c "create extension if not exists vector" -c "select extversion from pg_extension where extname = 'vector'"`. Expected: 0.8.7, or at least 0.8.4. If it is older than 0.8.4, the HNSW vacuum fixes and the IVFFlat memory check of section 2.9 are missing. 0.8.7 fixes a buffer overflow in IVFFlat index builds, which this exercise runs.
  - Load 20,000 random vectors. The `where g > 0` makes the inner query run once per row: `psql -h /tmp -p 5432 -d storage_lab -c "create table items (id bigint generated always as identity primary key, embedding vector(1536))" -c "insert into items (embedding) select (select array_agg(random()) from generate_series(1, 1536) where g > 0)::vector from generate_series(1, 20000) g"`.
  - Then run: `psql -h /tmp -p 5432 -d storage_lab -c "select pg_column_size(embedding) from items limit 1" -c "select pg_size_pretty(pg_relation_size('items')) as heap, pg_size_pretty(pg_table_size('items')) as with_toast"`.
  - Expected: Not run by the author yet. `pg_column_size` prints 6148, the stored bytes without the header. The heap is about 150 pages, about 1.2 MB, because each row keeps only a 50-byte pointer. The table with TOAST is about 160 MiB: about 20,000 TOAST pages, one per value, plus the heap and the TOAST index. Both sizes are this course's arithmetic from section 2.9.
  - Build the index with the default memory, and measure its WAL. This needs `psql` variables, so use one session: `psql -h /tmp -p 5432 -d storage_lab`, then `select pg_current_wal_lsn() as before \gset`, then `set maintenance_work_mem = '64MB';`, then `create index items_embedding_idx on items using hnsw (embedding vector_l2_ops);`, then `select pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), :'before')) as wal, pg_size_pretty(pg_relation_size('items_embedding_idx')) as index;`.
  - Expected: Not run by the author yet. The build prints `NOTICE:  hnsw graph no longer fits into maintenance_work_mem after N tuples`, with N below 10,000. The index is at least 20,001 pages, about 156 MiB. The WAL is about 125 MiB, because the build logs every page once, without its free space. Run it again with `set maintenance_work_mem = '512MB'`, after `drop index items_embedding_idx`. Expected: no notice, and a shorter build. The times are not predicted.
  - Then break IVFFlat. Run `set maintenance_work_mem = '64MB';` again, then `create index on items using ivfflat (embedding vector_l2_ops) with (lists = 300);`. Expected: `ERROR:  memory required is 90 MB, maintenance_work_mem is 64 MB`. That is 15,300 vectors of 6,152 bytes, from `vector_storage.py --rows 20000 --lists 300`. With `lists = 20`, the README's starting point for 20,000 rows, it needs about 59 MiB and fits.
  - Then delete half and vacuum: `delete from items where id % 2 = 0;` then `vacuum (verbose) items;`. Expected: a line `index "items_embedding_idx": pages: 20001 in total, 0 newly deleted, 0 currently deleted, 0 reusable`. The index keeps its size, as section 2.9 says. The page count is from the model, not run.
  - Clean up: `drop table items;`.
  - If it fails: `create extension vector` needs pgvector installed for your server's version. On Homebrew it is a separate package, which is not checked here.
  - Teaches: an index build has a memory cliff and a WAL burst, and both follow from the index size.

---

## 🔍 Check it yourself

- **Check 1.** Open `phase02_structures/lsm.py:268`. This line decides which keys go into a run's Bloom filter. Suppose it read `if bloom is not None and value is not None:`. Write the shortest sequence of puts, deletes and flushes that returns a deleted value. Then find the self-test check that would fail, and say which line of it fails.

- **Check 2.** Open `phase02_structures/lsm.py:330`. A compaction drops tombstones only when `_deeper_levels_empty` is true. A simpler rule would drop them whenever the output is the last level. With three levels, `Config(levels=3)` or `amplification.py --levels 3`, describe a state where the two rules give different answers. Which rule removes more garbage, and is it still safe?

- **Check 3.** Open `phase02_structures/bitcask_merge.py:202`. Open keeps the entry with the highest sequence number when two files hold the same key. After a crash in the middle of a merge, the old and the new copy have equal sequence numbers. Explain why it does not matter which copy wins. Then suppose the merge gave each copied entry a new, higher sequence number. The store's own counter stays where it was. An order is deleted after the merge. What does the next restart return for that order, and why?

- **Check 4.** Open `phase02_structures/cache_sim.py:327` and compare it with PostgreSQL's `GetBufferFromRing` at `freelist.c` line 727, REL_17_11. Both reuse a ring buffer only if its usage count is 0 or 1. Suppose the condition allowed any count up to 5. Which pages would a large scan then evict? What would the hit rate look like on the morning after a nightly report?

- **Check 5.** In any repository you own that configures a database, run `grep -rn "fillfactor\|shared_buffers\|innodb_old_blocks\|innodb_buffer_pool\|innodb_change_buffering\|level0_\|write_buffer_size\|bloom\|gen_random_uuid\|UUIDField(\|id: :uuid\|wal_compression\|rate_limiter" <your repo>/`. For each hit, name the amplification it changes, and the measurement that would show whether the value is right.

- **Check 6.** Open `phase02_structures/vector_storage.py` and find `hnsw_elements_per_page`. Compare its loop with `hnswbuild.c` lines 192 to 229 at pgvector v0.8.7. The self-test shows that the keep-together rule changes the count for vector(100). Explain why it changes nothing for vector(1536). Then, in any repository with pgvector, run `grep -rn "vector(\|halfvec\|hnsw\|ivfflat\|maintenance_work_mem\|SET STORAGE" <your repo>/`. For each index, compute its size with the script, and compare it with `shared_buffers` on the server that runs it.

---

## ✅ Checkpoint 2 — answer in your own words

The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

### Part A: the structures, sections 2.1 to 2.8

1. **Test-out, explain.** Walk through one put and one get on a B-tree and on a leveled LSM tree. For each, list what is read from the device and what is written, now and later. Use these words: leaf, heap page, page, checkpoint, WAL, memtable, run, compaction, filter. Then explain in two sentences why the LSM tree writes faster and reads slower.

2. **Test-out, predict.** A service holds 200 GB of rows. The database has 32 GB of cache. It serves 5,000 point reads and 500 updates per second, each to a random row. An update changes 200 bytes. Estimate the device load of a B-tree and of a leveled LSM tree. Use the M2's 89 µs per miss and the write amplifications of this phase. Which structure wins, and by roughly how much? Would a migration from one to the other be worth it?

3. **Test-out, demonstrate.** Run E6, E8, E9 and E10. Show the four-row amplification table and explain each column. Show the latency histogram with the compaction storm, and the paced run beside it. Show the measured FPR against memory at 4 and 10 bits per key. Show the `kept` column for LRU and 2Q, and explain why they differ.

4. **A colleague says:** "Our audit log is write-heavy, and LSM trees are faster for writes. Let's move it from PostgreSQL to RocksDB". The log's key is a timestamp followed by an id. Reads ask for one hour of entries. Argue for or against, with the numbers of this phase. Which fact about the keys changes the write comparison? Which number decides the read comparison?

5. **This is broken.** A service on RocksDB uses default options. Its put latency jumps to tens of milliseconds for a minute at a time. Its LOG file shows lines saying writes are stalled because of the number of level-0 files. The CPU is mostly idle, and the disk is busy. What is the cause, and how do you check it? Name the default trigger values involved, and two changes that would help.

6. **Show the arithmetic.** You need a Bloom filter for 500 million keys at an FPR of 0.1%. Compute the bits per key and the memory with the textbook formula. Then compute the memory with RocksDB's figure of 15.5 bits per key for 0.1%. What does each 4.8 more bits per key buy?

7. **Given these constraints, design.** A PostgreSQL server has 16 GB of `shared_buffers`. OLTP, online transaction processing, is the short reads and writes of the application. Its OLTP hot set is about 10 GB. Each night a report reads most of a 60 GB table, filtered by a date range. A colleague wants to raise `shared_buffers` to 64 GB "so the report fits". Explain what protects the hot set, when it does not, and what the larger setting would change. Then say what you would measure the next morning. Then answer the same question for MySQL with InnoDB, and name the setting that matters there.

8. **Show the arithmetic.** An index holds a billion 8-byte keys, with the layout of section 2.2. The server's buffer pool has 4 GB for it. Lookups are uniform over all keys, at 20,000 per second. Compute the height, the memory above the leaves, and the leaves' total size. Then compute the hit rate on leaves, and the device time per second at 89 µs per miss. Does one SSD with one queue keep up?

<details>
<summary>Answer sketches</summary>

1. B-tree put, in PostgreSQL: find the leaf, a miss unless cached. Change the heap page and one leaf per index in the buffer pool, and append a WAL record for each. Later, the checkpointer, the bgwriter or a backend writes each 8 kB page. The first change to each page after a checkpoint also puts a full page image into the WAL. B-tree get: inner pages from the cache, one leaf read, then the heap page that the TID names. In InnoDB, the primary-key leaf holds the row. LSM put: append to the WAL and insert into the memtable. A raw `Put` reads nothing, but a SQL engine such as MyRocks first reads the old row by primary key. Later, a flush writes the run, and each compaction rewrites it once per level. LSM get: memtable, then each run whose range and filter allow it, one block per run. The LSM writes faster because it turns writes into long sequential runs and pays no page image per page. It reads slower because a key can be in several runs, and filters only lower that cost.

2. Reads are uniform over 200 GB with 32 GB of cache. Assume rows of about 1 KB, an example, so about 200 million rows. The primary-key index then has 200,000,000 / 366 = 546,449 leaves, rounded up, about 4.5 GB. Each leaf covers far more rows than a heap page, so assume the cache keeps the leaves. That is inferred, not checked. The heap then gets about 32 − 4.5 = 27.5 GB of cache, so about 86% of heap reads miss. PostgreSQL reads: 5,000 × 0.86 × 89 µs = 0.38 s of device time per second, on heap pages. InnoDB and the LSM read one page or block per get, and miss at about the same rate. So they need about 0.37 to 0.38 s too. Updates read their row first on every engine, MyRocks included: 500 × 0.86 × 89 µs = 0.04 s. B-tree writes, with c near 1: a HOT update changes only the heap page. That is 150 + 2 × 8,192 = 16.5 KB, so 8.3 MB per second. A non-HOT update adds up to 16.5 KB for the new heap page and for each index leaf. LSM writes: an update writes the whole new row, not the 200 changed bytes. So about 33 × 1,000 bytes × 500 = 16.5 MB per second, sequential, plus compaction reads. So both need about 0.42 s per second for reads. The two write bytes of the same order. PostgreSQL writes 8.3 MB per second or more, and the LSM about 16.5 MB. Half of PostgreSQL's bytes are random page writes. The reads decide the load, and they cost the same on both. So a migration is not worth it for speed. The LSM's 1.1 against the B-tree's over 1.5 in space could still matter for disk cost. These are estimates from this phase's models, not measurements.

3. From the runs. Expected shapes are in E6, E8, E9 and E10. The key explanations: the log and the LSM read alike with filters, and differ in write and space amplification. The at-once storm puts p99 inside a 4.2 ms compaction, and pacing spreads it into 0.25 ms slices. FPR falls by about 10 for each 4.8 bits per key. 2Q keeps more because a page needs a second, separate access to enter Am.

4. Against, mostly. Keys that always grow make the B-tree write to its rightmost leaf. So each page collects many changes, and c is large. In PostgreSQL the heap fills in arrival order too, so its pages also collect many inserts. Write amplification then falls toward 3, from section 2.2. Vondra's sequence key wrote about 2 GB of WAL in an hour where a random UUID wrote over 40 GB. The RocksDB wiki notes that leveled compaction is also cheaper for keys in order. So the LSM's write advantage mostly goes away. Reads of one hour are range scans. A B-tree walks adjacent leaves. An LSM reads every overlapping run, and whole-key filters do not help ranges. The number that decides the reads is blocks per range. Retention deletes of old hours have the queue shape of section 2.4. On PostgreSQL, a partition per day can be dropped whole, as Phase 4, section 4.6, shows. On RocksDB, `DeleteRange` and delete-triggered compaction keep the scans fast. Measure both on a copy, with real key order, past a full compaction cycle.

5. Compaction cannot keep up with writes. The LOG lines have the format of section 2.4. Each starts with the column family in square brackets. Then come "Stalling writes because we have", the count of level-0 files, and the rate. At `level0_slowdown_writes_trigger`, 20, writes are held to `delayed_write_rate`, 16 MB per second by default. At 36, `level0_stop_writes_trigger`, writes stop, and the line says "Stopping writes" instead. The idle CPU and busy disk say the device, not the CPU, limits compaction. Check the Compaction Stats block of the LOG. Read L0's `Files` and `Score`, the `Stall(sec)` column and the `Stalls(count)` line. Compare the device's write throughput, from `iostat`, with what compaction needs. Help: give compaction more device time or more parallel jobs, since `max_background_jobs` defaults to 2. Lower the write amplification, which the `Sum` row's `W-Amp` measures. Or lower the write rate at the source, or use a faster device. A bigger L0 trigger only delays the stop and raises read amplification. A `rate_limiter` set too low makes the stalls worse.

6. Bits per key = −ln(0.001) / (ln 2)² = 6.908 / 0.4805 = 14.4. Memory = 500,000,000 × 14.4 / 8 = 900 MB. With RocksDB's 15.5 bits: 500,000,000 × 15.5 / 8 = 969 MB. Each 4.8 more bits per key divides the FPR by 10, because 0.6185^4.8 = 0.1. So 1% needs 9.6 bits, 600 MB, and 0.01% needs 19.2 bits, 1.2 GB.

7. Read the report's plan first. If it is a Seq Scan, PostgreSQL reads a table larger than a quarter of `shared_buffers` through a small ring. Then the report does not flood the pool. The ring is 256 kB in versions 14 to 17. The arithmetic of the 18 code gives about 752 kB. Its pages get a usage count of at most 1. At 64 GB, a quarter is 16 GB, so the 60 GB table still uses the ring. But a date filter often gives a Bitmap Heap Scan, and an Index Scan is also possible. Neither uses a ring. So either can push the 10 GB hot set out of 16 GB of `shared_buffers`. The morning's reads then miss. A 64 GB pool would leave room for the hot set and much of the report. But it takes that memory from the OS page cache, which every miss goes through. That trade is inferred. Measure the next morning: `EXPLAIN (ANALYZE, BUFFERS)` of the report, and the hit rate of the hot tables in `pg_statio_user_tables` beside `iostat`. On 16 or later, read the `bulkread` rows of `pg_stat_io`. Run `pg_buffercache_usage_counts()` and the per-relation query of section 2.1 in the evening and in the morning, to see which table took the pool. With InnoDB, the report's pages enter the old sublist at the midpoint. `innodb_old_blocks_time`, 1000 ms by default, keeps a page read several times in quick succession from moving to the young part. Keep it above 0.

8. Height 4, and 9,622 pages above the leaves, about 75 MiB, from section 2.2. Leaves: 2,732,241 × 8 KiB = about 20.8 GiB. The inner pages fit in the 4 GB, which leaves about 3.9 GB for leaves. Hit rate on leaves = 3.9 / 20.8 = about 19%, so 81% miss. Device time: 20,000 × 0.81 × 89 µs = 1.44 s per second. That is more than one device's second, so one SSD with one queue cannot keep up. If the query needs the row, PostgreSQL also reads the heap page that the TID names. The heap is at least as large as the index, so its pages miss at least as often. That is inferred. Then the device time is at least 2 × 1.44 = 2.9 s per second. An index-only scan, Phase 4, section 4.3, can skip the heap read. In InnoDB, a primary-key lookup ends at the leaf that holds the row. Real SSDs serve many reads in parallel, which this model does not include. Measure the device's throughput at your queue depth before you buy memory or disks.

</details>

### Part B: managed PostgreSQL, the pool from inside, vectors and columns

Part B tests the real-systems parts of sections 2.1, 2.2, 2.7, 2.8 and the new section 2.9.

9. **Show the arithmetic, on managed PostgreSQL.** Your service moves from PostgreSQL 17 on a VM with 64 GB of memory to Aurora PostgreSQL with 64 GB. On the VM, `shared_buffers` was 16 GB, its hit rate was 99%, and most misses found the page cache at 1.5 µs. A colleague sets `shared_buffers` to 16 GB on Aurora too, "because 25% is the rule". (a) What does Aurora's default give, and why does the rule not hold there? (b) Keep the 99% hit rate, and take 1 ms per storage read as an example. How much do the misses add to the average read, against the VM? (c) Which two metrics and which wait event do you watch in the first week?

10. **Given these constraints, design.** An agent memory table on RDS for PostgreSQL 17.11 holds 4 million embeddings of 1,536 dimensions, with an HNSW index. The instance has 32 GB of memory and default parameters. (a) Compute the value size, where the value is stored, and the index size. (b) Does the index fit in `shared_buffers`? What does a search pay when it does not? (c) What does a rebuild of the index need in memory, and what does it write to the WAL? (d) Propose two changes, and say what each gives up. (e) Which version check do you run first, and why?

11. **This is broken.** Each night a job deletes the embeddings of deleted documents, about 30% of 2 million rows. Since then, autovacuum on `items` runs for hours, and the HNSW index never gets smaller. What is the cause, and how do you check it? What would you change in the design?

12. **A colleague says:** "The finance dashboard sums `amount` over all 50 million orders every minute. Let's raise `shared_buffers` until the orders table fits." The rows are the running case's orders, about 6 to a heap page. Argue for or against, with numbers. Which structure fits this query?

13. **Walk through what happens when** you look for the cause of a slow morning on RDS for PostgreSQL 17. You have SQL access only. Last night a batch job ran, and since then the hit rate of the orders tables is low. Name the three views or functions you query, the query for each, and what each result would show if the batch job flooded the pool.

<details>
<summary>Answer sketches, part B</summary>

9. (a) AWS calls it about 75% of memory. The formula gives about 68% of `DBInstanceClassMemory`, minus about 390 MiB, so at most about 43 GiB on 64 GiB. AWS sets `SUM({DBInstanceClassMemory/12038},-50003)`, because Aurora has "no file system or secondary level of caching for tables or indexes". So the page cache that caught the VM's misses does not exist. A 16 GB pool is less than half of the default. AWS's own test at 15% of memory lost 14% of throughput and added 14% to the volume read I/O. (b) VM: 0.01 × 1.5 = 0.015 µs per read. Aurora, still at 99%: 0.01 × 1,000 = 10 µs, about 670 times more. The hit rate is also likely to fall with less than half of the pool, which is inferred. (c) `BufferCacheHitRatio` and `VolumeReadIOPs` in CloudWatch, and `IO:DataFileRead` in Performance Insights. On Aurora Standard the read count is also on the I/O bill.

10. (a) 4 × 1,536 + 8 = 6,152 bytes. The row is 6,184 bytes, over 2,032, so the value goes to TOAST in 4 chunks, and the heap row keeps 50 bytes. HNSW at one element per page: at least 4,000,001 pages, 30.5 GiB, from `vector_storage.py --rows 4000000`. (b) RDS gives `shared_buffers` 25% of `DBInstanceClassMemory`, a little under 8 GiB. The index needs at least 30.5 GiB, about 95% of the instance's 32 GiB, so most of it stays out of the pool. Each graph step can read up to 32 element pages. So one search can pay hundreds of reads of about 1 ms on gp3. That count is inferred from section 2.9. (c) The graph needs at least 26.7 GB. The RDS default `maintenance_work_mem` is 64 MB by one AWS page and about 500 MB on this instance by another, so check it. Either way the build prints the notice and runs slowly. It ends by writing about 24 GiB of WAL, the page images without their free space, which every replica replays, Phase 5, section 5.1. Both sizes are inferred. (d) An HNSW index on `embedding::halfvec(1536)`: 2 per page, at least 15.3 GiB, at the price of half-precision distances. Or `binary_quantize` to bit with re-ranking: 17 per page, at least about 1.8 GiB, at the price of recall and extra TOAST reads to re-rank. Test recall first, as the retrieval-internals course does. Partitioning by tenant or time also makes each index smaller, Phase 4, section 4.6. (e) `select extversion from pg_extension where extname = 'vector'`. RDS 17.11 lists 0.8.2, which is older than the HNSW vacuum fixes of 0.8.3 and 0.8.4, the IVFFlat memory check of 0.8.4 and the IVFFlat overflow fix of 0.8.7.

11. Cause: HNSW's VACUUM does four passes over the index, and its repair pass runs a graph search for every element that lost neighbours. 30% of 2 million is 600,000 deleted elements, so many survivors need repair. The index keeps its size because deleted slots are reused by inserts, not returned to the file system. Check: `pg_stat_progress_vacuum` shows the phase and the dead items. On 17 the columns are `dead_tuple_bytes` and `num_dead_item_ids`, at `system_views.sql` lines 1223 to 1224, REL_17_11. `pg_stat_activity` shows the autovacuum worker and its wait events. VACUUM VERBOSE prints the index's page line, with 0 reusable pages, which is inferred from the code. `extversion` shows whether you have the 0.8.3 and 0.8.4 vacuum fixes. The README's advice is `REINDEX INDEX CONCURRENTLY`, then `VACUUM`. Design: this is the queue shape of section 2.4. Partition the table by time or by tenant, so that a whole partition and its index can be dropped instead of deleted row by row. That design is inferred from sections 2.4 and 2.9.

12. Against. The table is 50,000,000 / 6 = 8,333,334 heap pages, about 68 GB. A Seq Scan of a table larger than a quarter of `shared_buffers` uses the 256 kB ring, section 2.8. So the pool would need more than 4 × 68 = 273 GB before the scan stops using the ring and keeps its pages. Each minute the dashboard reads 68 GB, which is about 1.1 GB per second of reads. A column store reads 50,000,000 × 8 bytes = 400 MB of `amount`, about 170 times less, before compression. Better still, a summary table that the order path keeps up to date, so the dashboard reads one row. Measure the bytes per run with `EXPLAIN (ANALYZE, BUFFERS)`.

13. First `pg_buffercache`: the per-relation query of section 2.1 shows which relations hold the most buffers now. If the batch job's table holds a large share, it took the pool. `pg_buffercache_usage_counts()` shows many buffers at count 1 or 0, which pages used once leave. Second `pg_stat_statements`, ordered by `shared_blks_read`: the batch job's statement leads, with a high `miss_pct`. Third `pg_stat_io`: if its reads sit in context `normal`, not `bulkread`, the job did not use a ring. Its plan was then an Index Scan or a Bitmap Heap Scan, section 2.8. Confirm with `EXPLAIN (ANALYZE, BUFFERS)` of that statement. In Performance Insights the morning shows `IO:DataFileRead` waits, and the per-statement metric `db.sql_tokenized.stats.shared_blks_read_per_sec` points at the same statement. The reading is inferred from sections 2.1 and 2.8.

</details>

---

## References & Further Learning

This course's research fetched the first URLs below on 2026-10-17, and the depth revision added more on 2026-10-18. The PostgreSQL 17 revision of 2026-10-20 fetched every new entry, and `check_urls.py` checked all of them again on 2026-10-20. Primary sources come first in each group.

### The original designs

- **The Log-Structured Merge-Tree, O'Neil, Cheng, Gawlick and O'Neil, Acta Informatica** — https://www.cs.umb.edu/~poneil/lsmtree.pdf
  Focus on: section 3 only, Equations 3.2 to 3.4, Theorem 3.1, and Examples 3.3 and 3.4. The cost model uses 1995 disk prices, so read the ratios, not the dollars. The PDF says "To be published", and the volume and year were not checked. Read it before section 2.3.
- **Space/Time Trade-offs in Hash Coding with Allowable Errors, Burton Bloom, Communications of the ACM, 1970** — https://people.cs.umass.edu/~emery/classes/cmpsci691st/readings/Misc/p422-bloom.pdf
  Focus on: "Analysis of Method 2", equations 16 and 17, and the half-full result on page 426. A course mirror, not the publisher's copy. The last row of Table I looks like a typo, so do not use it.
- **2Q: A Low Overhead High Performance Buffer Management Replacement Algorithm, Johnson and Shasha, VLDB 1994** — https://www.vldb.org/conf/1994/P439.PDF
  Focus on: section 2, "2Q, Full Version", with the pseudocode on page 441, and Tables 1 to 4. A scanned PDF. The tables were read from page images, and the text from OCR.
- **ARC: A Self-Tuning, Low Overhead Replacement Cache, Megiddo and Modha, USENIX FAST 2003** — https://www.usenix.org/legacy/events/fast03/tech/full_papers/megiddo/megiddo.pdf
  Focus on: Figure 4 for the algorithm, and Table VI for the trace with long scans. In Tables IV and V, 2Q has offline-tuned parameters. Read it after 2Q.
- **Bitcask: A Log-Structured Hash Table for Fast Key/Value Data, Sheehy and Smith, Basho, 2010** — https://riak.com/assets/bitcask-intro.pdf
  Focus on: page 4, merge and the hint file figure. A company paper, not peer reviewed. Phase 1 used its pages 2 to 5.

### Amplification

- **Designing Access Methods: The RUM Conjecture, Athanassoulis and others, EDBT 2016** — https://openproceedings.org/2016/conf/edbt/paper-12.pdf
  Focus on: section 2 for the three definitions, and section 3 with Figure 1 for the conjecture. Table 1 gives asymptotic costs. Short. The conjecture is not proved.
- **Monkey: Optimal Navigable Key-Value Store, Dayan, Athanassoulis and Idreos, SIGMOD 2017** — https://cs-people.bu.edu/mathan/publications/sigmod17-dayan.pdf
  Focus on: Equation 2 in section 3, the allocation in section 4.1, and Figure 11. Built on LevelDB, not RocksDB. The tests used a spinning disk with the block cache off, a worst case. Appendix F, with a cache, was not read for this course.
- **Optimizing Space Amplification in RocksDB, Dong and others, CIDR 2017** — https://www.cidrdb.org/cidr2017/papers/p82-dong-cidr17.pdf
  Focus on: section 3 for B-tree page fill and the LSM bound of 1.111. Section 5 with Figure 3 covers LinkBench. The authors work at Facebook.
- **InnoDB, MyRocks and TokuDB on the insert benchmark, Mark Callaghan, Small Datum, 2017** — https://smalldatum.blogspot.com/2017/05/innodb-myrocks-and-tokudb-on-insert.html
  Focus on: the "Fast SSD" tables, columns `wkb/i` and `size`. Insert-only, and the hardware is in an earlier post. The author's reply under the post says the primary key is inserted in order and the secondary indexes at random.
- **On the impact of full-page writes, Tomas Vondra, EDB blog, 2016** — https://www.enterprisedb.com/blog/impact-full-page-writes
  Focus on: "UUID vs. BIGSERIAL keys", about 2 GB against more than 40 GB of WAL in one hour at 5,000 inserts per second. The text gives no version, hardware or checkpoint settings, and the charts are images.
- **Read, write & space amplification - pick 2, Mark Callaghan, Small Datum, 2015** — https://smalldatum.blogspot.com/2015/11/read-write-space-amplification-pick-2_23.html
  Focus on: the definitions. No numbers. A short read before section 2.6.

### PostgreSQL source, tag REL_17_11, and docs

- **PostgreSQL 14 Internals, Egor Rogov, Postgres Professional, 2023** — https://edu.postgrespro.com/postgresql_internals-14_en.pdf
  Focus on: chapter 3, pages 62 to 66, for pages, line pointers and TIDs. Chapter 9, sections 9.1 and 9.5, for buffered I/O and the rings. Chapter 25, pages 425 to 431, for a real B-tree page, no merging and deduplication. The PDF prints digits as special glyphs. The book is about 14. This phase checks each fact it uses against 17.
- **PostgreSQL 17.0 release notes** — https://www.postgresql.org/docs/release/17.0/
  Focus on: `buffers_backend` removed from `pg_stat_bgwriter`, `pg_stat_checkpointer`, `io_combine_limit` and streaming reads, `vacuum_buffer_usage_limit` at 2MB, the rename to `shared_blk_read_time`, and `pg_buffercache_evict()`.
- **tableam.h** — https://github.com/postgres/postgres/blob/REL_17_11/src/include/access/tableam.h
  Focus on: `table_beginscan_bm` at lines 959 to 967, which asks for no ring.
- **nbtxlog.h** — https://github.com/postgres/postgres/blob/REL_17_11/src/include/access/nbtxlog.h
  Focus on: lines 90 to 95, what a split's WAL record holds.
- **nbtree README** — https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/nbtree/README
  Focus on: "Deleting entire pages during VACUUM" at lines 232 to 240, and "Placing deleted pages in the FSM" at line 383. They correct the belief that an index needs regular rebuilds.
- **itup.h** — https://github.com/postgres/postgres/blob/REL_17_11/src/include/access/itup.h
  Focus on: `IndexTupleData` at lines 35 to 51, the 8-byte index tuple header with its heap TID.
- **heaptoast.h** — https://github.com/postgres/postgres/blob/REL_17_11/src/include/access/heaptoast.h
  Focus on: lines 23 to 26 and 46 to 48 for the 2,032-byte threshold, and 84 to 89 for the 1,996-byte chunk.
- **postgresql.conf.sample** — https://github.com/postgres/postgres/blob/REL_17_11/src/backend/utils/misc/postgresql.conf.sample
  Focus on: `shared_buffers` at line 129, `maintenance_work_mem` at 142, `vacuum_buffer_usage_limit` at 160 and `subtransaction_buffers` at 170. Then `effective_io_concurrency` at 209, `io_combine_limit` at 211, `wal_compression` at 243, `checkpoint_timeout` at 258, `max_wal_size` at 262 and `track_io_timing` at 645.
- **system_views.sql** — https://github.com/postgres/postgres/blob/REL_17_11/src/backend/catalog/system_views.sql
  Focus on: `pg_stat_bgwriter`, `pg_stat_checkpointer` and `pg_stat_io` at lines 1134 to 1173, and `pg_stat_progress_vacuum` at 1223 to 1224. They show which columns exist on 17.
- **vacuumlazy.c** — https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/heap/vacuumlazy.c
  Focus on: line 726, the per-index line of VACUUM VERBOSE and of the autovacuum log.
- **hio.c** — https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/heap/hio.c
  Focus on: lines 520 and 532 to 536, the `row is too big` check.
- **detoast.c** — https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/common/detoast.c
  Focus on: `toast_datum_size` at lines 601 to 616, which explains what `pg_column_size` returns for a TOASTed value.
- **65.6 Database Page Layout, PostgreSQL 17** — https://www.postgresql.org/docs/17/storage-page-layout.html
  Focus on: Table 65.2 and section 65.6.1: the 24-byte page header, the 4-byte line pointer and the 23-byte tuple header.
- **27.2 The Cumulative Statistics System, PostgreSQL 17** — https://www.postgresql.org/docs/17/monitoring-stats.html
  Focus on: section 27.2.2 on the kernel page cache, 27.2.13 for `pg_stat_io` with its contexts and `reuses`, and `n_tup_newpage_upd`.
- **28.2 The Statistics Collector, PostgreSQL 14** — https://www.postgresql.org/docs/14/monitoring-stats.html
  Focus on: Table 28.21, for the 14 `pg_stat_bgwriter` columns that 17 removed. Read only if you still run 14.
- **F.25 pg_buffercache, PostgreSQL 17** — https://www.postgresql.org/docs/17/pgbuffercache.html
  Focus on: `pg_buffercache_usage_counts()`, the access rule, and the per-relation sample query.
- **F.30 pg_stat_statements, PostgreSQL 17** — https://www.postgresql.org/docs/17/pgstatstatements.html
  Focus on: `shared_blks_read`, `shared_blk_read_time`, `wal_fpi`, and the `shared_preload_libraries` rule.
- **F.28 pg_prewarm, PostgreSQL 17** — https://www.postgresql.org/docs/17/pgprewarm.html
  Focus on: the autoprewarm worker that reloads the pool after a restart.
- **F.23 pageinspect, PostgreSQL 17** — https://www.postgresql.org/docs/17/pageinspect.html
  Focus on: `bt_metap`, `bt_page_stats` and `bt_page_items`. Superusers only.
- **F.31 pgstattuple, PostgreSQL 17** — https://www.postgresql.org/docs/17/pgstattuple.html
  Focus on: `pgstatindex`, with `leaf_pages`, `empty_pages`, `deleted_pages` and `avg_leaf_density`.
- **64.1 B-Tree Indexes, PostgreSQL 17** — https://www.postgresql.org/docs/17/btree.html
  Focus on: section 64.1.4.2, bottom-up deletion, and 64.1.4.3, deduplication.
- **65.2 TOAST, PostgreSQL 17** — https://www.postgresql.org/docs/17/storage-toast.html
  Focus on: the 2 kB threshold, the chunk size, the four strategies, and the UPDATE rule.
- **ALTER TABLE, PostgreSQL 17** — https://www.postgresql.org/docs/17/sql-altertable.html
  Focus on: SET STORAGE, which changes only future writes.
- **CREATE TABLE, PostgreSQL 17** — https://www.postgresql.org/docs/17/sql-createtable.html
  Focus on: the table `fillfactor`, default 100.
- **F.6 bloom and 64.5 BRIN Indexes, PostgreSQL 17** — https://www.postgresql.org/docs/17/bloom.html
  Focus on: the first paragraph. Read with https://www.postgresql.org/docs/17/brin.html for the bloom operator classes.
- **PostgreSQL 12.0 release notes** — https://www.postgresql.org/docs/release/12.0/
  Focus on: B-tree indexes with many duplicates.
- **PostgreSQL 13.0 release notes** — https://www.postgresql.org/docs/release/13.0/
  Focus on: deduplication, and `gen_random_uuid()` in core.
- **PostgreSQL 14.0 release notes** — https://www.postgresql.org/docs/release/14.0/
  Focus on: B-tree additions that remove expired entries, which the docs call bottom-up deletion.
- **PostgreSQL 16.0 release notes** — https://www.postgresql.org/docs/release/16.0/
  Focus on: `pg_stat_io`, `n_tup_newpage_upd`, and HOT with BRIN.
- **PostgreSQL 18.0 release notes** — https://www.postgresql.org/docs/release/18.0/
  Focus on: `uuidv7()`, asynchronous I/O, and checksums on by default.

- **freelist.c** — https://github.com/postgres/postgres/blob/REL_17_11/src/backend/storage/buffer/freelist.c
  Focus on: the clock sweep at lines 314 to 353, `GetAccessStrategy` at 541 to 573, and the ring reuse rule at line 727. In tag REL_19_RC1 the free list is gone and the sweep uses one atomic compare-and-swap. The cap is still 5. Version 19 is a release candidate.
- **freelist.c at REL_18_6** — https://github.com/postgres/postgres/blob/REL_18_6/src/backend/storage/buffer/freelist.c
  Focus on: lines 557 to 601, the ring that 18 sizes from the pin limit. Only for the 18 line of section 2.8.
- **bufmgr.c** — https://github.com/postgres/postgres/blob/REL_17_11/src/backend/storage/buffer/bufmgr.c
  Focus on: the usage count rule at lines 2703 to 2713, and the WAL flush in `FlushBuffer` at lines 3909 to 3927.
- **Buffer manager README** — https://github.com/postgres/postgres/blob/REL_17_11/src/backend/storage/buffer/README
  Focus on: line 218, the 256 kB ring for sequential scans.
- **buf_internals.h** — https://github.com/postgres/postgres/blob/REL_17_11/src/include/storage/buf_internals.h
  Focus on: `BM_MAX_USAGE_COUNT` and the comment above it, lines 72 to 79.
- **nbtree.h** — https://github.com/postgres/postgres/blob/REL_17_11/src/include/access/nbtree.h
  Focus on: `BTPageOpaqueData` at lines 62 to 69, and the fill factors at lines 189 to 202.
- **bufpage.h** — https://github.com/postgres/postgres/blob/REL_17_11/src/include/storage/bufpage.h
  Focus on: the slotted page drawing at lines 29 to 42, and `PageHeaderData`.
- **heapam.c** — https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/heap/heapam.c
  Focus on: lines 445 to 452, where a scan of a table larger than a quarter of `shared_buffers` gets the ring. Lines 2218 to 2222 log the first insert on a fresh page with no page image. Line 2359 tests the TOAST threshold.
- **nbtinsert.c** — https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/nbtree/nbtinsert.c
  Focus on: lines 1978 to 1990, the pages a split registers in its WAL record.
- **19.4 Resource Consumption, PostgreSQL 17** — https://www.postgresql.org/docs/17/runtime-config-resource.html
  Focus on: `shared_buffers`, its default and the 25% and 40% advice.
- **65.7 Heap-Only Tuples, PostgreSQL 17** — https://www.postgresql.org/docs/17/storage-hot.html
  Focus on: the two conditions. Read it with the Uber post.
- **CREATE INDEX, PostgreSQL 17** — https://www.postgresql.org/docs/17/sql-createindex.html
  Focus on: `fillfactor` for B-trees, default 90, and `deduplicate_items`, default on.
- **PostgreSQL 8.0.2 release notes** — https://www.postgresql.org/docs/release/8.0.2/
  Focus on: "New cache management algorithm 2Q replaces ARC", done "to avoid a pending US patent on ARC". History, not needed for the lessons.
- **PostgreSQL 8.1.0 release notes** — https://www.postgresql.org/docs/release/8.1.0/
  Focus on the line: "The buffer manager has also been changed to use a "clock sweep" replacement policy." With the 8.0.2 notes, it shows two replacements. First 2Q replaced ARC, and then the clock sweep replaced 2Q. History, not needed for the lessons.

### Managed PostgreSQL and cloud storage

All AWS pages were fetched on 2026-10-20. They are vendor sources.

- **Amazon Aurora PostgreSQL parameters, Part 1: Memory and query plan management, Kumar and Subramanian, AWS Database Blog, 2021-04-12** — https://aws.amazon.com/blogs/database/amazon-aurora-postgresql-parameters-part-1-memory-and-query-plan-management/
  Focus on: the `shared_buffers` section: no file system cache, the 75% formula, the pgbench test at 15%, and the volume read I/O. Also the line that Aurora keeps the pool through restarts.
- **RDS for PostgreSQL memory, Amazon RDS User Guide** — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Tuning.concepts.memory.html
  Focus on: the `{DBInstanceClassMemory/32768}` default, and the 64 MB `maintenance_work_mem`.
- **Amazon RDS DB instance storage** — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Storage.html
  Focus on: the two storage types, and the gp3 table for PostgreSQL: 3,000 IOPS below 400 GiB, 12,000 to 64,000 from 400 GiB.
- **Working with parameters on RDS for PostgreSQL** — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Parameters.html
  Focus on: "the default PostgreSQL units for all parameters", and `shared_buffers` in 8 KB.
- **Aurora PostgreSQL Optimized Reads** — https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.optimized.reads.html
  Focus on: the tiered cache on local NVMe, and which instances and clusters get it.
- **Amazon Aurora pricing** — https://aws.amazon.com/rds/aurora/pricing/
  Focus on: Aurora Standard, billed per I/O, against I/O-Optimized, with no I/O charge.
- **Amazon Aurora metrics** — https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.AuroraMonitoring.Metrics.html
  Focus on: `VolumeReadIOPs`, billed read I/O per 5 minutes, and `BufferCacheHitRatio`.
- **Autovacuum memory on RDS for PostgreSQL** — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Autovacuum.html
  Focus on: the `maintenance_work_mem` default formula, which differs from the memory page's 64 MB.
- **Amazon EBS General Purpose SSD volumes** — https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html
  Focus on: gp3 latency, the 3,000 IOPS baseline, and 500 IOPS per GiB up to 80,000.
- **Amazon EBS Provisioned IOPS SSD volumes** — https://docs.aws.amazon.com/ebs/latest/userguide/provisioned-iops.html
  Focus on: io2 Block Express, under 500 microseconds for 16 KiB.
- **IO:DataFileRead, Aurora PostgreSQL wait events** — https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/apg-waits.iodatafileread.html
  Focus on: the context and the likely causes. The RDS page of the same name is at https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/wait-event.iodatafileread.html
- **SQL statistics for RDS PostgreSQL, Performance Insights** — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PerfInsights.UsingDashboard.AnalyzeDBLoad.AdditionalMetrics.PostgreSQL.html
  Focus on: `pg_stat_statements` loaded by default from 11, and the `shared_blks_read` metric names.
- **Parameter groups for Amazon RDS** — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/parameter-groups-overview.html
  Focus on: static parameters need a reboot, and default groups cannot be changed.
- **Extension versions for Amazon RDS for PostgreSQL** — https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html
  Focus on: the PostgreSQL 17 table: `pg_buffercache` 1.5 and `pgvector` 0.8.2 on 17.11. The table changes with each release.

### pgvector, tag v0.8.7

- **pgvector README** — https://github.com/pgvector/pgvector/blob/v0.8.7/README.md
  Focus on: "Index Build Time" for HNSW, the IVFFlat lists rule, "Storing", "Approximate Search", "Vacuuming", the FAQ on parallel scans and `SET STORAGE PLAIN`, and the value sizes of each type.
- **pgvector CHANGELOG** — https://github.com/pgvector/pgvector/blob/v0.8.7/CHANGELOG.md
  Focus on: 0.8.3 and 0.8.4, the HNSW vacuum fixes.
- **hnsw.h** — https://github.com/pgvector/pgvector/blob/v0.8.7/src/hnsw.h
  Focus on: lines 54 and 69 for `m` and the heap TIDs, 81 to 82 for the tuple sizes, and 364 to 393 for the page and tuple structs.
- **hnswbuild.c** — https://github.com/pgvector/pgvector/blob/v0.8.7/src/hnswbuild.c
  Focus on: the comment at lines 1 to 35, the placement loop at 192 to 229, the notice at 533 to 545, and `log_newpage_range` at 1142 to 1143.
- **hnswvacuum.c** — https://github.com/pgvector/pgvector/blob/v0.8.7/src/hnswvacuum.c
  Focus on: the four passes at lines 785 to 792, the ring at line 747, and the zeroed vector at line 688.
- **hnswutils.c** — https://github.com/pgvector/pgvector/blob/v0.8.7/src/hnswutils.c
  Focus on: line 546, where each element is read from its page, and lines 891 to 933, the neighbours a search step loads.
- **hnsw.c and ivfflat.c** — https://github.com/pgvector/pgvector/blob/v0.8.7/src/hnsw.c
  Focus on: `ampredlocks = false` at line 348. The same flag is at line 265 of https://github.com/pgvector/pgvector/blob/v0.8.7/src/ivfflat.c
- **sql/vector.sql** — https://github.com/pgvector/pgvector/blob/v0.8.7/sql/vector.sql
  Focus on: `STORAGE = external` for `vector` at line 39 and for `halfvec` at line 483.
- **ivfbuild.c** — https://github.com/pgvector/pgvector/blob/v0.8.7/src/ivfbuild.c
  Focus on: the centres and samples at lines 400 and 456 to 466. Read with `ivfutils.c` lines 126 to 133 and 166, at https://github.com/pgvector/pgvector/blob/v0.8.7/src/ivfutils.c

### RocksDB source, tag v11.8.1, and wiki

- **advanced_options.h** — https://github.com/facebook/rocksdb/blob/v11.8.1/include/rocksdb/advanced_options.h
  Focus on: the L0 triggers at lines 547 and 554, and the fanout at line 671. The pending-bytes limits are at lines 709 and 717, `compaction_pri` at 725, and `optimize_filters_for_hits` at 816.
- **options.h** — https://github.com/facebook/rocksdb/blob/v11.8.1/include/rocksdb/options.h
  Focus on: `write_buffer_size` at line 191, `level0_file_num_compaction_trigger` at line 255, and `delayed_write_rate` at lines 1367 to 1383. Then `rate_limiter` at 734, `max_open_files` at 776, `use_direct_reads` at 1153 and `stats_dump_period_sec` at 1217.
- **column_family.cc** — https://github.com/facebook/rocksdb/blob/v11.8.1/db/column_family.cc
  Focus on: `GetWriteStallConditionAndCause`, lines 1011 to 1046, for the order of the stall checks. The LOG format strings follow, at lines 1072 to 1159.
- **filter_policy.h** — https://github.com/facebook/rocksdb/blob/v11.8.1/include/rocksdb/filter_policy.h
  Focus on: lines 140 to 149 on bits per key, and 169 to 173 on Ribbon filters.
- **table.h** — https://github.com/facebook/rocksdb/blob/v11.8.1/include/rocksdb/table.h
  Focus on: `cache_index_and_filter_blocks` at line 238, `partition_filters` at line 519, and `block_align` at line 772, all false by default. The lab's runs align their blocks as `block_align` does.
- **RocksDB wiki: Compaction** — https://github.com/facebook/rocksdb/wiki/Compaction
  Focus on: "Classic Leveled" and "Tiered", for write amplification per level. The wiki has no release tag, so it may change.
- **RocksDB wiki: RocksDB Tuning Guide** — https://github.com/facebook/rocksdb/wiki/RocksDB-Tuning-Guide
  Focus on: the worked example with write amplification 33 and space 1.14, and `max_size_amplification_percent`.
- **RocksDB wiki: Write Stalls** — https://github.com/facebook/rocksdb/wiki/Write-Stalls
  Focus on: the causes and log lines. Its option names differ from the source, as section 2.4 says.
- **RocksDB wiki: RocksDB Bloom Filter** — https://github.com/facebook/rocksdb/wiki/RocksDB-Bloom-Filter
  Focus on: the bits-per-key list, and the cache-local arithmetic that gives 0.95%.
- **RocksDB wiki: Leveled Compaction** — https://github.com/facebook/rocksdb/wiki/Leveled-Compaction
  Focus on: dynamic level sizes, with 90% of the data in the last level.
- **RocksDB wiki: Compaction Stats and DB Status** — https://github.com/facebook/rocksdb/wiki/Compaction-Stats-and-DB-Status
  Focus on: the example table and the column list, especially `Score`, `W-Amp` and `Stall(sec)`. No version is given for the example.
- **RocksDB wiki: Rate Limiter** — https://github.com/facebook/rocksdb/wiki/Rate-Limiter
  Focus on: `rate_bytes_per_sec`, and what the limiter does not cover.
- **RocksDB wiki: Implement Queue Service Using RocksDB** — https://github.com/facebook/rocksdb/wiki/Implement-Queue-Service-Using-RocksDB
  Focus on: "Old Item Deletion Problem", and `iterate_upper_bound`.
- **RocksDB wiki: DeleteRange** — https://github.com/facebook/rocksdb/wiki/DeleteRange
  Focus on: one range tombstone in place of a scan and many deletes.
- **RocksDB wiki: Single Delete** — https://github.com/facebook/rocksdb/wiki/Single-Delete
  Focus on: the condition that a key was written once.
- **RocksDB wiki: Partitioned Index Filters** — https://github.com/facebook/rocksdb/wiki/Partitioned-Index-Filters
  Focus on: the index and filter sizes per run, and the two benchmarks. They date from about RocksDB 5.x.
- **RocksDB wiki: Block Cache** — https://github.com/facebook/rocksdb/wiki/Block-Cache
  Focus on: the 32 MB default, uncompressed blocks, and index and filter blocks outside the cache.
- **RocksDB wiki: Prefix Seek** — https://github.com/facebook/rocksdb/wiki/Prefix-Seek
  Focus on: "Why Prefix Seek?", the prefix Bloom filter for ranges.
- **MyRocks wiki: Read Free Replication** — https://github.com/facebook/mysql-5.6/wiki/Read-Free-Replication
  Focus on: the first two paragraphs, on `GetForUpdate()` before each write, and the last note on the primary.
- **RocksDB wiki: Universal Compaction** — https://github.com/facebook/rocksdb/wiki/Universal-Compaction
  Focus on: "Compaction Triggered by Space Amplification", and the temporary doubling of space. Its write amplification example of 9 is called "a wild unproven estimation" by the page itself.

### InnoDB

- **Clustered and Secondary Indexes, MySQL 8.4 manual** — https://dev.mysql.com/doc/refman/8.4/en/innodb-index-types.html
  Focus on: the clustered index holds the rows, and each secondary record holds the primary key.
- **The Physical Structure of an InnoDB Index, MySQL 8.4 manual** — https://dev.mysql.com/doc/refman/8.4/en/innodb-physical-structure.html
  Focus on: page fill after random and sequential inserts, and `MERGE_THRESHOLD`.
- **Doublewrite Buffer, MySQL 8.4 manual** — https://dev.mysql.com/doc/refman/8.4/en/innodb-doublewrite-buffer.html
  Focus on: the first paragraph. Phase 1, section 1.4, used the same page.

- **The InnoDB Buffer Pool, MySQL 8.4 manual** — https://dev.mysql.com/doc/refman/8.4/en/innodb-buffer-pool.html
  Focus on: the old and young sublists, and the midpoint.
- **Making the Buffer Pool Scan Resistant, MySQL 8.4 manual** — https://dev.mysql.com/doc/refman/8.4/en/innodb-performance-midpoint_insertion.html
  Focus on: `innodb_old_blocks_pct` and `innodb_old_blocks_time`.
- **ha_innodb.cc, tag mysql-8.4.11** — https://github.com/mysql/mysql-server/blob/mysql-8.4.11/storage/innobase/handler/ha_innodb.cc
  Focus on: lines 23017 to 23027, the two defaults and their ranges.
- **What Is New in MySQL 8.4 since MySQL 8.0, MySQL 8.4 manual** — https://dev.mysql.com/doc/refman/8.4/en/mysql-nutshell.html
  Focus on: Table 1.1 of changed InnoDB defaults: `innodb_change_buffering`, `innodb_adaptive_hash_index` and `innodb_io_capacity`.
- **Change Buffer, MySQL 8.4 manual** — https://dev.mysql.com/doc/refman/8.4/en/innodb-change-buffer.html
  Focus on: the first three paragraphs, and the warning about long merges.
- **Adaptive Hash Index, MySQL 8.4 manual** — https://dev.mysql.com/doc/refman/8.4/en/innodb-adaptive-hash.html
  Focus on: when it helps, and the contention warning.

### Production reports

- **Faster bulk-data loading in CockroachDB, Akhtar and Taylor, Cockroach Labs, 2020** — https://www.cockroachlabs.com/blog/bulk-data-import/
  Focus on: the giant L0 compaction, the 847 runs in 13 sublevels, and the import times with their hardware.
- **Here's how CockroachDB keeps your database from collapsing under load, Sumeer Bhola, Cockroach Labs, 2022** — https://www.cockroachlabs.com/blog/admission-control-in-cockroachdb/
  Focus on: the read amplification threshold of 20, and the overload at 1,000. The latency graphs give no workload or hardware.
- **How Discord Stores Trillions of Messages, Bo Ingram, Discord, 2023** — https://discord.com/blog/how-discord-stores-trillions-of-messages
  Focus on: the compaction and tombstone problems, and the p99 numbers before and after. The date comes from the page and was not checked separately.
- **Open-sourcing a 10x reduction in Apache Cassandra tail latency, Dikang Gu, Instagram, 2018** — https://web.archive.org/web/20221221164348/https://instagram-engineering.com/open-sourcing-a-10x-reduction-in-apache-cassandra-tail-latency-d64f86b43589
  Focus on: which number the "10x" is, and the production p99. An archived copy, because the live site refused the connection.
- **Why Uber Engineering Switched from Postgres to MySQL, Evan Klitzke, Uber, 2016** — https://www.uber.com/blog/postgres-to-mysql-migration/
  Focus on: the write amplification argument. No measured byte counts, and the example changes an indexed column.
- **MyRocks: A space- and write-optimized MySQL database, Yoshinori Matsunobu, Facebook, 2016** — https://engineering.fb.com/2016/08/31/core-infra/myrocks-a-space-and-write-optimized-mysql-database/
  Focus on: the LinkBench size results, and the fixed compressed page size. The write results are only in a chart image.
- **GitHub availability this week, Jesse Newland, GitHub, 2012-09-14** — https://github.blog/news-insights/the-library/github-availability-this-week/
  Focus on: the failover to a server with a cold InnoDB buffer pool, and the failback it caused.
- **From Zero to 50 Million Uploads per Day: Scaling Media at Canva, Chen and Sharp, Canva, 2022-11-29** — https://www.canva.dev/blog/engineering/from-zero-to-50-million-uploads-per-day-scaling-media-at-canva/
  Focus on: the list of MySQL on RDS limits, including the hot buffer pool.
- **Roblox Return to Service 10/28-10/31 2021, Roblox, 2022** — https://about.roblox.com/newsroom/2022/01/roblox-return-to-service-10-28-10-31-2021
  Focus on: the BoltDB section: a file that never shrinks, the freelist, and the 4.2 GB file with 489 MB of data.
- **How Stripe's document databases supported 99.999% uptime with zero-downtime data migrations, Morzaria and Narkhede, Stripe, 2024-06-06** — https://stripe.dev/blog/how-stripes-document-databases-supported-99.999-uptime-with-zero-downtime-data-migrations
  Focus on: the bulk import step, where sorted inserts raised write throughput 10 times.
- **How Instacart Built a Modern Search Infrastructure on Postgres, Mittal and others, Instacart, 2025-05-29** — https://company.instacart.com/tech-innovation/how-instacart-built-a-modern-search-infrastructure-on-postgres
  Focus on: "ANN Index Design in Postgres", with inline storage instead of TOAST and the parallel workers. The tech.instacart.com copy returned 403.
- **Postgres Job Queues & Failure By MVCC, Brandur Leach, 2015-05-18** — https://brandur.org/postgres-queues
  Focus on: "Slow lock time" and "Dead tuples". Phase 3, section 3.7, uses the rest of the post.

### Lectures and notes

- **CMU 15-445/645 Fall 2025 notes, #04 buffer pools** — https://15445.courses.cs.cmu.edu/fall2025/notes/04-bufferpool.pdf
  Focus on: section 5, the OS page cache, and "Dirty Pages". Written notes, for reading instead of watching.
- **CMU 15-445/645 Fall 2025 notes, #05 "Database Storage II"** — https://15445.courses.cs.cmu.edu/fall2025/notes/05-storage2.pdf
  Focus on: section 4, "Index-Organized Storage". The course schedule uses this title. The video titles below may differ, which was not checked.
- **CMU 15-445/645 Fall 2025 notes, #08 "Indexes & Filters I"** — https://15445.courses.cs.cmu.edu/fall2025/notes/08-indexes1.pdf
  Focus on: "Clustered Indexes", and the merge threshold.
- **CMU 15-445/645 Fall 2025 notes, #06 "Storage Models & Compression"** — https://15445.courses.cs.cmu.edu/fall2025/notes/06-storage3.pdf
  Focus on: section 2, the row store and the column store with their advantages and disadvantages. Read it before the columnar paragraph of section 2.7.
- **CMU 15-445/645 Fall 2025, Lecture 04: Memory Management and Buffer Pools, Andy Pavlo** — https://www.youtube.com/watch?v=8-2yv4z0VZc
  Focus on these times:
    - 0:04:29 buffer pool overview, auto-chapter
    - 0:15:39 page table, dirty flag, pin count, auto-chapter
    - 0:22:52 why not `mmap`, caption
    - 0:36:20 replacement policies, auto-chapter
    - 0:40:30 clock, an approximate LRU, caption
    - 0:47:40 sequential flooding, caption
    - 0:50:43 LRU-K and ghost caches, auto-chapter
    - 0:58:07 MySQL's young and old regions, caption
    - 0:59:58 ARC, PostgreSQL and the patent, caption
    - 1:03:00 PostgreSQL's ring for scans, caption
    - 1:06:56 flushing and I/O scheduling, auto-chapter
    - 1:12:35 `O_DIRECT`, caption

  "Caption" times were checked against YouTube's auto-generated captions. "Auto-chapter" times are YouTube's chapter marks and were not checked. At 0:59:58 the captions show the claim about "little tweaks", which the release notes above contradict.
- **CMU 15-445/645 Fall 2025, Lecture 05: Log-Structured Database Storage, Andy Pavlo** — https://www.youtube.com/watch?v=2_sTdS4h-bY
  Focus on: 0:32:34 LSM trees, caption. 0:45:08 tombstones and compaction, caption. 0:50:11 leveled compaction, caption. 0:59:07 universal compaction, caption. 1:01:03 RocksDB's default style, caption.
- **CMU 15-445/645 Fall 2025, Lecture 08: B+Trees, Andy Pavlo** — https://www.youtube.com/watch?v=u7ii_Lvm9rM
  Focus on: 0:17:02 introduction, 0:37:11 insertion, 0:45:35 deletion, 1:07:57 optimizations. Auto-chapters only, because the captions did not load.

### ORMs and drivers

- **Model field reference, Django 5.2** — https://docs.djangoproject.com/en/5.2/ref/models/fields/
  Focus on: `UUIDField` and its `default=uuid.uuid4` example.
- **uuid, Python 3 standard library** — https://docs.python.org/3/library/uuid.html
  Focus on: the line that `uuid4()` creates a random UUID.
- **Active Record and PostgreSQL, Rails Guides** — https://guides.rubyonrails.org/active_record_postgresql.html
  Focus on: "UUID Primary Keys", where `gen_random_uuid()` is the default.

### The owner's other courses

These are files in `study-material/`, not URLs.

- **retrieval-internals, Phase 2, section 2.2, and Phase 4, section 4.4.** Memory per vector and quantization. Phase 7, sections 7.1 and 7.3, for deletes.
- **advanced-retrieval, Phase 7, section 7.3.** The planner's choice between a B-tree and HNSW under a filter.
- **nosql, Phase 5, section 5.3.** Analytical stores, for the columnar paragraph of section 2.7.
- **sql-mysql, Phase 1, section 1.1.** The InnoDB B+tree in more depth.

---

## Cheatsheet

```
A MISS
  average read      h × t_hit + (1 − h) × t_miss
  M2 numbers        1.5 µs page cache, 89 µs SSD   (elite-performance 5.6)
  99% -> 90% hits   2.375 µs -> 10.25 µs, 4.3 times slower
  PostgreSQL        shared_buffers 128 MB = 16,384 x 8 kB; start at 25% of RAM
  WAL rule          FlushBuffer forces WAL up to the page's pd_lsn first
  PG miss           1.5 us page cache or 89 us SSD. The counters cannot tell which
  PG read counters  EXPLAIN BUFFERS read, pg_statio *_blks_read, pg_stat_io reads (16+)
  tell them apart   iostat, or track_io_timing: blk_read_time / blks_read per block
                    (on 17 a seq scan reads 16 blocks per call: use index lookups)
  17 seq scans      streaming reads, up to io_combine_limit 128kB = 16 pages per call

MANAGED POSTGRESQL (AWS docs and blog, vendor sources)
  RDS               shared_buffers {DBInstanceClassMemory/32768} x 8 kB = 25%, page cache below
  Aurora            SUM({DBInstanceClassMemory/12038},-50003): "about 75%" per AWS,
                    about 68% minus 390 MiB by the formula; no OS page cache below
  Aurora at 15%     14% less throughput, 14% more volume read I/O (pgbench, db.r5.2xlarge)
  Aurora billing    reads billed per I/O on Standard, not on I/O-Optimized (VolumeReadIOPs)
  EBS gp3           single-digit ms; 3,000 IOPS base; 500 IOPS/GiB up to 80,000
  RDS gp3           3,000 IOPS below 400 GiB; 12,000 to 64,000 from 400 GiB
  EBS io2 BE        under 500 us for 16 KiB
  99% hits at 1 ms  misses add 10 us per read, against 0.89 us on the M2 SSD
  wait event        IO / DataFileRead in pg_stat_activity = IO:DataFileRead in Perf. Insights

LOOK INSIDE (PostgreSQL 17)
  pool contents     pg_buffercache_usage_counts(); per relation: join on relfilenode
  per statement     pg_stat_statements shared_blks_hit, shared_blks_read,
                    shared_blk_read_time (blk_read_time before 17), wal_fpi
  per process       pg_stat_io backend_type, context (normal, bulkread, bulkwrite,
                    vacuum), reads, hits, writes, evictions, reuses
  reset             pg_stat_reset_shared('io')  or  ('wal')

WHERE THE ROW LIVES
  PostgreSQL        heap of pages + line pointers. Every index, primary key too,
                    holds TIDs (page, line pointer). Lookup = leaf + heap page
  InnoDB            rows inside the clustered primary-key B-tree. Secondary
                    entries hold the primary key. Merges pages below 50%
  heap tuple        23-byte header + 4-byte line pointer. TOAST above 2 kB

B-TREE (PostgreSQL 17 layout, same in 18. 20-byte entries: 8 header + 8 key + 4 pointer)
  per page          leaf 366 at 90% fill, inner 285 at 70%
  10 million keys   3 levels, 776 KiB above the leaves
  1 billion keys    4 levels, about 75 MiB above the leaves
  write per change  WAL record + 2 x 8,192 / c    (c = changes per page between two writes)
                    c=1: 165 per byte   c=10: 17.9   c=100: 3.1
  random keys       pages split in half, 1/2 to 2/3 full (Dong, CIDR 2017)
  row change        heap page + one leaf per index; HOT: heap page only
  UUID vs sequence  Vondra 2016: >40 GB vs ~2 GB WAL, 1 h at 5,000 inserts/s
  no merge          PostgreSQL never merges half-empty pages. VACUUM deletes
                    empty pages for reuse. The file keeps its size; REINDEX shrinks
  who wrote, 17     pg_stat_checkpointer.buffers_written; pg_stat_io writes of
                    client backend, context normal (buffers_backend is gone)
  watch             pg_stat_wal wal_fpi, wal_bytes; n_tup_hot_upd; pgstatindex
  levers first      sequence or identity, uuidv7() only from 18, fewer indexes,
                    fillfactor, max_wal_size, wal_compression
  ORM UUID keys     Django default=uuid.uuid4 and Rails id: :uuid are random keys
  MySQL 8.4         innodb_change_buffering none, adaptive_hash_index OFF,
                    innodb_io_capacity 10000

LSM TREE (RocksDB v11.8.1 defaults)
  write_buffer_size 64 MB    max_write_buffer_number 2
  L0 trigger 4    slowdown 20    stop 36    fanout 10    L1 target 256 MB
  pending bytes     soft 64 GB, hard 256 GB    delayed_write_rate 16 MB/s
  read path         memtable, L0 newest first, one run per deeper level
  range read amp    L0 files + non-empty levels
  SQL on an LSM     MyRocks reads by primary key before each write (GetForUpdate)
  update bytes      a new version of the whole row: about 33 x row bytes, not 33 x changed bytes
  memory            filters + run indexes (0.5 / 5 MB per 256 MB run), outside the
                    block cache by default. Block cache 32 MB, uncompressed

COMPACTION
  leveled           write amp per level = fanout, worst case. Guide: 33. Space 1.11-1.14
                    measured: Sum W-Amp 21.9 in the wiki's Compaction Stats example
  tiered            write amp 1 per level. Space up to 3x by default (200%), then a
                    full merge. A merge needs up to 2x the space of the files it rewrites
  Bitcask merge     newest live entry per key; hint = 28 B + key, no value
  safe order        write new, sync new, sync dir, remove old, sync dir
  LOG               "[cf] Stalling writes because we have N level-0 files rate R"
  stats             every 600 s: Score > 1 needs compaction, Sum W-Amp, Stall(sec)
  pacing            rate_limiter, null by default: flush and compaction only
  range deletes     DeleteRange, SingleDelete, CompactOnDeletionCollectorFactory

BLOOM FILTER
  FPR               (1 − e^(−k n / m))^k, best k = (m/n) ln 2, half the bits set
  bits per key      −ln(p) / (ln 2)^2:  1% -> 9.6,  0.1% -> 14.4
  10 bits per key   0.82% textbook, 0.95% RocksDB cache-local, factor 1.13
  rule              +4.8 bits per key -> FPR / 10. Tombstones go in the filter
  ranges            whole-key filters do not help. A prefix filter helps one prefix

AMPLIFICATION (RUM, EDBT 2016)
  read              bytes read / bytes returned
  write             bytes written / bytes changed
  space             bytes stored / live bytes
  decide by         rate x ratio = device seconds per second
  cloud volume      20,000 random reads/s = 6.7 x the gp3 baseline, 156 MiB/s > 125 MiB/s
  columnar          sum of 8 bytes over 10 M orders: 13.7 GB row store, 80 MB column

EVICTION
  LRU               one scan larger than the pool removes every hot page
  2Q                A1in 25% FIFO, A1out 50% page numbers, Am LRU
  ARC               T1, T2, ghosts B1, B2, target p adapts
  PostgreSQL        clock sweep, usage count cap 5. Ring for Seq Scans of
                    tables > 1/4 shared_buffers, 256 kB in 14 to 17, ~752 kB in 18
  VACUUM ring       2 MB since 17 (vacuum_buffer_usage_limit)
  no ring           Index Scan, Bitmap Heap Scan, TOAST reads
  InnoDB            old sublist 37%, insert at midpoint,
                    innodb_old_blocks_time 1000 ms; no ghost list

VECTORS (pgvector 0.8.7 on PostgreSQL 17. HNSW sizes and HNSW build memory are lower bounds,
         inferred from struct sizes. The IVFFlat memory is what the code checks)
  value bytes       vector 4d+8, halfvec 2d+8, bit d/8+8; 1,536 dims: 6,152 / 3,080 / 200
  TOAST             row > 2,032 bytes moves the value out, STORAGE external, 1,996-byte
                    chunks; vector(1536): 4 chunks; inline only up to 498 dims
  PLAIN             vector(1536): 1 row per heap page; vector(3072): "row is too big"
  HNSW element      72 + value bytes; neighbours 4 + 6 x (level+2) x m, aligned to 8; m = 16
  index size        vector(1536) 1 per page, halfvec 2, bit 17; 1M rows >= 7.6 GiB
  TOAST             vector(1536): about one 8 kB TOAST page per value, 1M rows about 8.2 GB
  search reads      up to 32 neighbour pages per graph step at the lowest level
  build memory      HNSW: graph >= value + 512 B per vector, else NOTICE, slow
                    IVFFlat: (lists + max(50 x lists, 10,000)) x value bytes, else ERROR
                    (the ERROR since 0.8.4; samples capped at heap pages x 291 since 0.8.5)
  build WAL         every index page once, without free space: about 79% of the index
  VACUUM            4 passes with graph repair; slots reused, file keeps its size
  versions          HNSW vacuum fixes 0.8.3, 0.8.4; IVFFlat memory check 0.8.4;
                    IVFFlat overflow fix 0.8.7; RDS 17.11 lists 0.8.2
```

At 10 million orders, the Phase 1 order store meets three limits. A second team moves a database for the wrong reason, and then stores embeddings without pricing them. This lesson explains why one workload runs ten times faster on one structure, and how to choose first.

What you must know, taught below in this order:

- When misses go from 1% to 10% of reads, the average read gets about 4 times slower.

- A PostgreSQL row change writes the table page and one page in every index, and each pays a full page image after a checkpoint.

- An LSM tree makes a write cheap now and pays later, when compaction rewrites it at each level.

- Price each structure in device time for your own workload, because an LSM update rewrites the whole row and a vector index copies every vector.

- One scan larger than the cache removes every hot page from an LRU cache, unless a second rule stops it.

## Where does the order store stand after Phase 1?

- The WAL. A changed page may reach the disk only after its log record is durable.

- Dirty pages. The checkpointer, the bgwriter or a backend, the server process of one client, writes them later.

- A full page image. After a checkpoint, the first change to a page copies the whole page into the WAL.

- The page cache. The kernel's copy of file pages. On an Apple M2, a read took 1.5 µs from it and 89 µs from the SSD.

- The order store. Each put appends a 20-byte header with a CRC, the key and the value, 1,230 bytes for order:1041.

- The keydir. A hash table in memory from each key to the offset of its newest entry, rebuilt from the log on restart. A delete appends a tombstone.

Each order was written three times: created, paid and shipped. Three limits appear, and none of them is a bug.

- Memory. At about 30 bytes per key, the keydir needs 300 MB now, and 30 GB for a billion orders.

- Space. Old versions stay in the log, so 30 million entries fill 36.9 GB for 12.3 GB of current orders.

- Order. A hash table has no key order. A report on order:1041 to order:2040 checks all 10 million keys, then reads 1,000 scattered entries.

That team moves a write-heavy event store off PostgreSQL to an LSM tree, because "it is faster for writes". Writes get faster and reads slower. Disk use can reach three times the data before background merges remove the old versions. A nightly burst of merges becomes the new p99 problem, the latency 99% of requests stay under. Neither database is broken. Nobody could say before the move that the structure did not fit the workload.

The same team then adds an agent feature that stores one embedding per document, with the pgvector extension. An embedding is a list of numbers that a model computes for a text, and pgvector adds a column type and indexes for them to PostgreSQL. The table holds a million embeddings, and nobody has asked what they cost the database. The last section answers that with the tools of this lesson.

Go deeper: versions, where the labs run, the time, and what comes later
Versions. PostgreSQL 17 is the base of this lesson, and its source lines are at tag REL_17_11, the latest 17 minor release. Docs references are to the PostgreSQL 17 manual. Where PostgreSQL 14 behaves differently and you may still meet it, one clause says so. Where 18 differs, one line says so. MySQL facts come from the 8.4 manual, RocksDB facts from tag v11.8.1, and pgvector facts from tag v0.8.7.

The step Phase 1 left out. Phase 1 left one step of its store for later. It is the compaction step, which Bitcask calls merge, with the hint files it writes. The compaction section of this lesson builds both.

Where the page cache numbers come from. They are from the earlier course, elite-performance, in its part "Syscalls, buffers and the page cache". A page there is 16 KiB. A read from the page cache took 1.5 µs at the median, and a read from the SSD took 88.7 to 89.8 µs. These are medians per run.

Evidence
Measured on the author's Apple M2 on 2026-09-25, in elite-performance section 5.6. Hunter's study note could not re-open that run, so treat it as his own recorded measurement.

Where it runs, and what it costs. Everything runs on your laptop and costs nothing. The labs use Python 3.12 or later and the standard library only. They run in memory on the simulated file system of Phase 1. Four exercises, E12, E13, E14 and E16, use a local PostgreSQL 17 server at /tmp:5432, in the database storage_lab that Phase 1 created. E13 also uses the pageinspect and pgstattuple extensions, and E14 uses pg_buffercache and pg_stat_statements. All four ship with PostgreSQL. E16 needs the pgvector extension. Use 0.8.7, and nothing older than 0.8.4, for the reasons in the last section. The PostgreSQL exercises were not run by the author yet. Run all commands from elite-storage/code/.

Time. The reading takes about 3 hours in the full phase. The labs take about 3 hours more.

Left for later. Phase 4 covers indexes as the query planner sees them, and table partitioning.

Why the lesson estimates costs. Every structure in this lesson lowers one cost by raising another. The lesson shows how to estimate each cost for your workload before a migration, and which measurement confirms the estimate.

Three more ideas from Phase 1. The write-ahead log is an append-only file. A commit waits for its log record, not for the page, and recovery replays the log after a crash. Recovery starts at the REDO point of the last completed checkpoint. An LSN is a byte offset into the WAL, so two LSNs differ by the WAL bytes between them. The full page image is written because full_page_writes is on by default.

## 2.1 What does a cache miss cost?

The miss rate, not the hit rate, decides how fast reads are.

The first limit of the order store is that every key must fit in memory. When the data is larger than memory, a structure keeps most of it on disk and reads it in fixed-size pieces. Its speed then depends on how often a read finds its piece in memory.

A page is that piece, 8,192 bytes in PostgreSQL. A buffer pool is the database's own cache of pages, an array of page-sized frames in its own memory. A page table maps each page number to its frame. On a miss, the pool reads the page into a frame it chose to reuse, which is eviction.

- query needs page 7 of orders_pkey: the buffer pool, shared_buffers, checks its page table

- hit in the buffer pool: use frame 3, with no system call

- miss: evict a frame, read 8,192 bytes: the read goes to the kernel

- hit in the OS page cache: about 1.5 µs

- miss: the SSD serves it: about 89 µs

Predict: a store reads at 1.5 µs from memory and 89 µs from the SSD. Its hit rate falls from 99% to 90%. Is the average read 10% slower, 2 times slower, or about 4 times slower?
About 4 times slower. The hit rate fell by 9 points, but the miss rate grew 10 times, from 1% to 10%. One miss costs as much as 59 hits, so the misses decide the average.

For a hit rate h, a read costs h × hit cost + (1 − h) × miss cost on average. At 99% hits that is 0.99 × 1.5 + 0.01 × 89 = 2.375 µs. At 90% hits it is 1.35 + 8.9 = 10.25 µs, which is 4.3 times slower.

Average read time from the hit rate and the miss cost

Hit rate, %
Miss cost, µs
Average read , which is  the 2.375 µs at 99% hits

Move the miss cost to 1,000 µs to see a cloud volume, which the managed part below explains.

In PostgreSQL, one miss has two prices. It reads files through the kernel, so a miss in shared_buffers costs 1.5 µs from the page cache. It costs 89 µs from the SSD. Its own counters cannot tell the two apart, because a read may be a page-cache hit. iostat can, and so can the time per read with track_io_timing on.

The failure is a pool too small for the hot data. Nothing errors. The hit rate falls, and the average read gets several times slower.

### Which counter shows a miss?

Every PostgreSQL counter has a hit column and a read column. The read column counts pages that were not in shared_buffers, wherever the kernel found them.

Where | A hit | A read, which may be a page-cache hit | Version

EXPLAIN (ANALYZE, BUFFERS) | shared hit | read | 14 to 18

pg_statio_user_tables | heap_blks_hit, idx_blks_hit | heap_blks_read, idx_blks_read. The 14 docs call it "Number of disk blocks read" | 14 to 18

pg_stat_io | hits | reads, per process type and context | since 16

pg_stat_statements | shared_blks_hit | shared_blks_read, per statement | 14 to 18

In the pg_statio names, heap means the table's own pages and idx its indexes. The B-tree section explains the heap. So the miss rate of one table is heap_blks_read over the sum of both columns, and one statement's miss rate comes from pg_stat_statements the same way.

### What changes on RDS and Aurora?

Most backend teams run PostgreSQL on RDS or Aurora, the two managed PostgreSQL services of AWS. Both change the two numbers of this section, the pool size and the price of a miss. The usual advice of 25% of memory for shared_buffers holds on one of them and is wrong on the other.

- RDS for PostgreSQL. The default is {DBInstanceClassMemory/32768}, and RDS gives shared_buffers in 8 KB units. So the formula gives 8,192 / 32,768 of DBInstanceClassMemory, which is 25%. DBInstanceClassMemory is a little less than the instance memory, because RDS subtracts the memory it reserves. Check the value with show shared_buffers on your instance. Below the pool sits the operating system and its page cache, as on your laptop.

- Aurora PostgreSQL. Aurora keeps no file system cache, or any second cache, below the pool for tables and indexes. The default is SUM({DBInstanceClassMemory/12038},-50003), "which is about 75% of the available memory". The unit is again 8 kB, so the formula itself gives about 68%, minus 50,003 buffers, about 390 MiB, by this course's arithmetic. In an AWS test, a pool at 15% of memory "showed a 14% reduction in performance and 14% increase in VolumeReadIOPS".

Evidence
The RDS formula is from the RDS memory page of the Amazon RDS User Guide, and the 8 KB unit from the RDS page on PostgreSQL parameters, which says RDS uses "the default PostgreSQL units for all parameters". The Aurora quotes and the test are from Sameer Kumar and Gopalakrishnan Subramanian, "Amazon Aurora PostgreSQL parameters, Part 1", AWS Database Blog, 2021-04-12. The test was a select-only pgbench run on a db.r5.2xlarge with 500 clients at scale 1,000. These are vendor sources, read on 2026-10-20. That RDS has the OS page cache below the pool is inferred from PostgreSQL's buffered I/O, because the AWS page does not say.

So on Aurora a miss in shared_buffers has no OS page cache below it. It is a read from the storage service, and the 1.5 µs page-cache price does not exist there. One exception exists: on NVMe instances in an I/O-Optimized cluster, Aurora Optimized Reads adds a tiered cache on the local NVMe. Each storage read counts in the CloudWatch metric VolumeReadIOPs, a count per 5 minutes, which AWS calls "[Billed] Volume Read IOPS". On Aurora Standard each read is billed per I/O. On Aurora I/O-Optimized, reads have no I/O charge.

 | Self-managed on a VM or laptop | RDS for PostgreSQL | Aurora PostgreSQL

default shared_buffers | 128 MB | 25% of DBInstanceClassMemory | "about 75%" per AWS. The formula gives about 68%, minus about 390 MiB

cache below the pool | the OS page cache | the OS page cache | no OS page cache. Optimized Reads adds an NVMe cache on some instances

a miss in shared_buffers costs | 1.5 µs or a device read | a page-cache hit, not measured on RDS, or an EBS read | a storage read. Billed per I/O on Aurora Standard

the hit-rate signal | pg_statio, pg_stat_io | the same, plus Performance Insights | the same, plus BufferCacheHitRatio and VolumeReadIOPs

The price of a miss on EBS. RDS keeps its files on EBS, the block storage of AWS, and the M2 laptop's 89 µs is not a cloud number. EBS gp3 volumes "provide single-digit millisecond latency". On plain EBS, a gp3 volume has a baseline of 3,000 IOPS, and you can buy up to 80,000. RDS for PostgreSQL differs: below 400 GiB, gp3 gives a fixed 3,000 IOPS, and from 400 GiB it gives 12,000 to 64,000. io2 Block Express gives an "average latency of under 500 microseconds for 16KiB I/O operations". Take 1 ms per miss as an example inside "single-digit millisecond":

- At 99% hits on gp3, misses put 0.01 × 1,000 = 10 µs on each read, against 0.89 µs on the M2.

- At 90% hits on gp3, misses put 0.10 × 1,000 = 100 µs on each read.

- At 3,000 IOPS, the volume serves at most 3,000 misses a second, whatever the latency.

So on a cloud volume, each point of hit rate costs about 11 times more than on the laptop. The lab's latency model takes that price with --latency --read-us 1000. The flag changes only the latency model, at amplification.py:314, so it needs --latency. In the write-heavy workload about 10% of the 20,000 operations a second are gets, from E6. At about one block per get and 1 ms per block, the gets alone need about 2 seconds of device time each second. So expect the queue to grow without limit. Add --rate 5000 for a load that one device can serve. That outcome is this course's arithmetic, not run.

Evidence
The latency and IOPS figures are from the Amazon EBS user guide pages "General Purpose SSD volumes" and "Provisioned IOPS SSD volumes", read on 2026-10-20, and the RDS storage page for the RDS gp3 limits. The arithmetic at 1 ms is this course's. The --read-us flag exists at amplification.py:517.

### What do you see when the pool is too small?

A backend that waits for a page read shows the wait event DataFileRead of type IO in pg_stat_activity. Performance Insights on RDS and Aurora shows the same wait as IO:DataFileRead. The current AWS docs show that dashboard as part of CloudWatch Database Insights. The AWS page for that event says: "If the IO:DataFileRead event occurs frequently, your shared buffer pool might be too small to accommodate your workload." Run this a few times during the slow period:

-- Which waits do the active sessions spend their time in?
select wait_event_type, wait_event, count(*)
from pg_stat_activity
where state = 'active'
group by 1, 2
order by 3 desc;

Evidence
The source spells the event DATA_FILE_READ, at wait_event_names.txt line 211, REL_17_11. The quote is from the AWS page "IO:DataFileRead" for Aurora PostgreSQL wait events, read on 2026-10-20.

A cold pool is one that holds few of the hot pages, such as right after a restart or a failover. Two published cases show what it costs.

- GitHub. A schema migration loaded its main MySQL database so much that health checks failed. The failover tool then made another server the active database. That server's InnoDB buffer pool was cold, and the server performed poorly. The load on the cold pool made its health checks fail too, so the role moved back. The team then turned off the health checks and automatic failover. Performance came back slowly, as the pool filled with the hot pages again. GitHub reported 1 hour 46 minutes of downtime and another hour of degraded performance that week, for this outage and a second one on the next day. Phase 5, section 5.5, covers failover itself.

- Canva. Canva ran its media metadata on MySQL on RDS, before it moved to DynamoDB. One limit it hit: "Servicing our normal production traffic required a hot buffer pool, so instance restarts and version upgrades weren't possible without accepting some downtime."

Evidence
Jesse Newland, "GitHub availability this week", GitHub blog, 2012-09-14, https://github.blog/news-insights/the-library/github-availability-this-week/, verified from the post. The Canva quote is from a post by Chen and Sharp on the Canva engineering blog of 2022-11-29, https://www.canva.dev/blog/engineering/from-zero-to-50-million-uploads-per-day-scaling-media-at-canva/, verified from the post.

In PostgreSQL, the pg_prewarm module can reload the pool after a restart. With pg_prewarm in shared_preload_libraries, the module will, "using 2 background workers, reload those same blocks after a restart". The AWS extension pages list pg_prewarm 1.2 for RDS and for Aurora PostgreSQL 17.11. The Aurora post above adds that Aurora "maintains shared buffers contents during restarts and potentially during failovers".

### What does the pool hold, and which statement filled it?

The counters above give one hit rate for the whole server. A slow query or a flooded pool needs two finer views: which tables hold the pool now, and which statements cause the reads.

- pg_buffercache: what the pool holds. This extension ships with PostgreSQL. It has two summary functions, pg_buffercache_summary() and pg_buffercache_usage_counts(), since its version 1.4 in PostgreSQL 16. pg_buffercache_usage_counts() returns one row per usage count, 0 to 5, with the number of buffers, dirty buffers and pinned buffers. The eviction section explains usage counts.

- pg_stat_statements: which statements read. It counts hits and reads per statement. On PostgreSQL 17 the read time column is shared_blk_read_time, and it stays zero unless track_io_timing is on.

- pg_stat_io: reads by process type and reason. It splits the server's I/O by backend_type, object and context. The context says why the process did the I/O. normal covers most reads, and bulkread is a large read through a small ring of buffers, which the eviction section explains.

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

-- The ten statements that read the most pages that were not in shared_buffers
select queryid, calls, shared_blks_hit, shared_blks_read,
       round(shared_blk_read_time::numeric, 1) as read_ms,
       round(100.0 * shared_blks_read
             / nullif(shared_blks_hit + shared_blks_read, 0), 1) as miss_pct,
       left(query, 60) as query
from pg_stat_statements
order by shared_blks_read desc
limit 10;

The first query names the tables that took the pool, and the second names the statement that read them. E14 runs all three tools on the tables of E12.

Run psql -h /tmp -p 5432 -d storage_lab -c "show shared_buffers" -c "show block_size" -c "select sum(heap_blks_read) as read, sum(heap_blks_hit) as hit from pg_statio_user_tables". Compare the first two values with the defaults below. Then say which cache could have served the read count, and which tool would tell you. On a managed instance, run the pg_stat_activity wait query above and look for IO / DataFileRead.

The miss rate decides the average read, and 1% to 10% misses is about 4 times slower.

Reading read as a disk read, or copying 25% to Aurora, sizes the wrong cache.

A page is now the unit of every read, but the next section shows how a store finds the one page that holds order:1041 among millions.

Go deeper: frame flags, shared_buffers defaults, read counters, reads on 17 and 18, the WAL rule in code, the tools in detail
Two flags on every frame. A pin count says how many processes are using the page now. A pinned page cannot be evicted. A dirty flag says the page changed in memory and must be written back before its frame is reused.

Evidence
Andy Pavlo's CMU lecture on buffer pools covers the page table, the dirty flag and the pin count at about 15:39.

A buffer pool hit is cheaper still. A hit in a database's own buffer pool skips even the system call, so it costs less than 1.5 µs. That cost was not measured in this course. It makes the ratio between a hit and a miss larger, not smaller.

PostgreSQL's buffer pool. The setting is shared_buffers. Its default is 16,384 buffers of 8 kB, which is 128 MB. The docs say "a reasonable starting value for shared_buffers is 25% of the memory in your system". They add a limit: "it is unlikely that an allocation of more than 40% of RAM to shared_buffers will work better than a smaller amount". The page size of 8,192 bytes is the default of the build option blocksize, at meson_options.txt lines 5 to 8, REL_17_11. E12 shows the value on your own server.

Evidence
The default is verified from guc_tables.c lines 2267 to 2268 at tag REL_17_11, and from the PostgreSQL 17 docs, section 19.4, which also give the two quotes.

One page, two caches. One page can sit in memory twice, once in shared_buffers and once in the page cache. That is the likely reason for the 40% limit above. The reason is inferred, because the docs do not state it.

Evidence
Rogov, "PostgreSQL 14 Internals", page 147, says PostgreSQL "reads and writes all data via buffered file operations". The CMU 15-445 Fall 2025 notes for lecture #04 name PostgreSQL as a system "that uses the OS's page cache". Both are verified.

The arithmetic in full. At 99% hits: 0.99 × 1.5 + 0.01 × 89 = 1.485 + 0.89 = 2.375 µs. At 90% hits: 0.90 × 1.5 + 0.10 × 89 = 1.35 + 8.9 = 10.25 µs. And 10.25 / 2.375 = 4.3.

The two prices at a 99% hit rate. If every miss finds the page cache, the misses add 0.01 × 1.5 = 0.015 µs to the average read. If every miss goes to the SSD, they add 0.01 × 89 = 0.89 µs. So one hit rate covers miss costs that differ by 59 times.

What the docs admit. PostgreSQL's I/O statistics "do not differentiate between data which had to be fetched from disk and that which already resided in the kernel page cache". The PostgreSQL 14 docs say the same in other words. track_io_timing is off by default, at postgresql.conf.sample line 645, REL_17_11. With it on, pg_stat_database.blk_read_time counts read time in milliseconds.

The other values of the pg_stat_io context column are bulkwrite, for COPY and table rewrites, and vacuum, for VACUUM.

Evidence
The quote is from the PostgreSQL 17 docs, section 27.2.2. The PostgreSQL 14 docs, section 28.2.2, say the same in other words. Both are verified. The pg_statio columns are verified from the PostgreSQL 17 docs, Table 27.31. pg_stat_io is verified from the 16.0 release notes and the 17 docs, Table 27.23, and its contexts from pgstat_io.c lines 226 to 232, REL_17_11. The pg_stat_statements columns are verified from its 1.11 SQL file at REL_17_11 and from the 1.9 file at REL_14_24.

Reads on 17 and on 18. PostgreSQL 17 reads a sequential scan through streaming I/O. It can group up to io_combine_limit of pages into one read call. The default is 128kB, which is 16 pages, at postgresql.conf.sample line 211, REL_17_11. So a cold sequential scan may read 16 pages per call, while an index lookup still reads one page. That reading is inferred from the setting and the 17.0 release notes. PostgreSQL 18 adds asynchronous reads, with io_method = worker by default, and its docs keep the sentence about the page cache. On 18, EXPLAIN ANALYZE also prints the buffer lines without the BUFFERS option, at explain_state.c lines 179 and 180, REL_18_6.

The WAL rule, inside the buffer pool. Phase 1 stated the WAL rule as a principle. Here is the line of PostgreSQL that enforces it. Every page header holds pd_lsn, the position in the WAL just after the record of the page's last change. Before the buffer manager writes a dirty page, it forces the WAL to disk up to that position. Copied from the source, with lines cut where marked:

/* src/backend/storage/buffer/bufmgr.c, FlushBuffer(), REL_17_11, lines 3909 to 3927. Cut: ... */
	/*
	 * Force XLOG flush up to buffer's LSN.  This implements the basic WAL
	 * rule that log updates must hit disk before any of the data-file changes
	 * they describe do.
	 * ...
	 */
	if (buf_state & BM_PERMANENT)
		XLogFlush(recptr);

Why a database does not use mmap. This rule is also why a database keeps its own buffer pool instead of mapping its files into memory with mmap. With mmap, the kernel decides when a dirty page goes to disk. It could write the page before its WAL record, which breaks the WAL rule. That reason is inferred from the WAL rule. The CMU lecture discusses mmap at about 22:52.

Two tools that tell the caches apart. iostat on the host counts the reads that reached the device. With track_io_timing on, blk_read_time / blks_read in pg_stat_database gives the time per block. On 17 a sequential scan reads up to 16 blocks in one call, and the call's time is counted once, at bufmgr.c lines 1518 to 1521. So compare it on index lookups, which read one page per call. There, a few microseconds means the page cache served most reads, and about 89 µs means the SSD did. That reading of the average is inferred from the M2 numbers.

A pool too small for the pages in use. A pinned page, one that a process is using now, cannot leave its frame. If every frame is pinned when a miss needs one, PostgreSQL cannot read the page at all. If the clock passes every buffer in a row and finds each one pinned, it raises no unpinned buffers available. A pool that is too small for the number of pages that queries hold at once fails this way. The clock sweep, which the eviction section explains, raises the error at freelist.c line 353, REL_17_11.

Other fixed-size caches. shared_buffers is not the only fixed-size cache. PostgreSQL also keeps small caches, called SLRU caches, for commit status and for subtransactions. PostgreSQL 17 lets you size them, with settings such as subtransaction_buffers, at postgresql.conf.sample line 170, REL_17_11. Phase 3 tells the GitLab case where one of them was too small.

RDS storage. RDS stores the files on General Purpose SSD, gp2 and gp3, or on Provisioned IOPS SSD, io1 and io2 Block Express. The RDS memory page calls the unit of its formula bytes, but shared_buffers counts 8 kB buffers, which is why this lesson reads the formula as 25%.

Evidence
The storage types are from the RDS page "Amazon RDS DB instance storage", read on 2026-10-20.

The three tools in detail. The pg_buffercache functions need a superuser or a role with the privileges of pg_monitor, per the docs. RDS for PostgreSQL 17.11 lists pg_buffercache 1.5 in its extension versions page. Version 1.5 adds pg_buffercache_evict(). The 17.0 release notes say that it "is useful for testing". On 14 to 16 the pg_stat_statements read time column was blk_read_time, and the 17.0 release notes record the rename. The module must be in shared_preload_libraries, so adding it needs a restart. On RDS, PostgreSQL 11 and later load it by default, per the AWS Performance Insights page for PostgreSQL. That page names the same counter db.sql_tokenized.stats.shared_blks_read_per_sec.

For pg_stat_io, run select pg_stat_reset_shared('io'); before a test to start from zero. The reset target io is at pgstatfuncs.c line 1740, REL_17_11. Then read it:

select backend_type, context, reads, hits, evictions, reuses
from pg_stat_io
where object = 'relation' and reads > 0
order by reads desc;

On PostgreSQL 18, pg_stat_io drops op_bytes and adds byte columns such as read_bytes, per the 18.0 release notes.

Evidence
pg_buffercache_usage_counts() is verified from pg_buffercache--1.3--1.4.sql lines 6 to 21 at REL_17_11, and the 17 docs, F.25, which also give the access rule and the per-relation query. The pg_stat_statements facts are from the 17 docs, F.30, and the 17.0 release notes. pg_prewarm is from the 17 docs, F.28. The RDS extension list and the Performance Insights page were read on 2026-10-20.

## 2.2 Where does a B-tree keep the row, and what does a write cost?

A B-tree write costs pages, not the bytes that changed.

A B-tree is a tree of pages kept sorted by key. A leaf holds sorted keys with pointers to their rows, and a link to the next leaf. An inner page holds separator keys and child page numbers. A lookup reads one page per level, and a range scan follows the leaf links.

PostgreSQL and InnoDB, the MySQL storage engine, put the row in different places.

PostgreSQL keeps rows in a heap, the table's own file of 8 kB pages, in no key order. One row version is a tuple. A line pointer is a 4-byte slot with a tuple's offset and length. A TID, or tuple ID, is a page number and a line pointer number, 6 bytes in all. Every index, the primary key included, is a separate B-tree whose leaf entries hold a key and a TID.

- orders_pkey leaf: order:1041 → TID (7,3)

- heap page 7: line pointer 3 gives the row

- idx_customer leaf: cust:88 → the same TID (7,3)

InnoDB keeps rows inside the primary-key B-tree, the clustered index, whose leaves hold whole rows. A secondary index record holds the row's primary key, so a lookup through it walks two trees.

- idx_customer leaf: cust:88 → order:1041

- PRIMARY, walked again: from the root, by order:1041

- PRIMARY leaf: holds the whole row

Predict: a 1,210-byte order is inserted into a PostgreSQL table with two indexes on random keys, just after a checkpoint. How many pages change? About how many bytes reach the WAL and the data files: 1.2 kB, 5 kB, or 36 kB?
Three pages change: one heap page and one leaf in each index. The bytes are near 36 kB, about 30 bytes for each byte of the order. Each changed page pays a full page image in the WAL and a page write later, and a random-key leaf shares that cost with almost no other change.

### What does a lookup read?

An 8 kB leaf holds 366 entries of an 8-byte key, and an inner page 285. So 10 million keys need a height of 3. The 97 pages above the leaves take 776 KiB, against 300 MB for the keydir. With those cached, a lookup misses at most on the leaf, and PostgreSQL then on the heap page.

What the heap against the clustered index changes. The CMU 15-445 Fall 2025 notes for lecture #05 call the InnoDB layout index-organized storage. Here is what the difference changes:

- A PostgreSQL point lookup reads two pages that can miss. It reads the leaf, then the heap page that the TID names. An index-only scan can skip the heap page, and Phase 4 says when the planner uses one. In InnoDB, the primary-key leaf holds the row, so one page miss is the most a primary-key lookup pays.

- A long primary key costs more in InnoDB. Each secondary entry repeats it. The manual says: "If the primary key is long, the secondary indexes use more space". In PostgreSQL every index entry holds a 6-byte TID, whatever the primary key is.

- A random primary key splits the table itself in InnoDB. Random inserts leave pages "from 1/2 to 15/16 full", and sequential ones about 15/16. In PostgreSQL a random key splits only index pages, and new rows still fill the heap in arrival order. That last point is inferred from the heap layout, and not measured here.

- A row that moves. A PostgreSQL update writes a new tuple with a new TID, and Phase 3 explains why. So each index needs a new entry, unless the update is HOT. InnoDB secondary entries hold the primary key, so they stay valid when a row moves inside the clustered tree. That is inferred from the two layouts. It is the difference that Uber's post, below, argues from.

PostgreSQL also has hash, GiST, GIN, SP-GiST and BRIN indexes, in Rogov's chapters 24 to 29. In this lesson, "index" means a B-tree index.

Evidence
The heap, line pointers and TIDs are verified from Rogov, "PostgreSQL 14 Internals", section 3.1, pages 63 and 64, and the PostgreSQL 17 docs, section 65.6. The InnoDB layout is verified from the MySQL 8.4 manual's page "Clustered and Secondary Indexes": "Each InnoDB table has a special index called the clustered index that stores row data", and "each record in a secondary index contains the primary key columns for the row". The page fill numbers come from the manual's page "The Physical Structure of an InnoDB Index".

TOAST. A row wider than TOAST_TUPLE_THRESHOLD, "normally 2 kB", has its large values compressed or moved out of line. TOAST is PostgreSQL's name for this out-of-line storage. The moved values go to a separate TOAST table in chunks of "about 2000 bytes". For 8 kB pages the exact numbers are a threshold of 2,032 bytes and chunks of at most 1,996 bytes. These values "are always accessed via an index", per Rogov, page 157. So reading a large JSON payload costs a lookup in a second B-tree and reads of a second heap. An UPDATE "incurs no TOAST costs if none of the out-of-line values change". The 1,230-byte order of the running case stays inline, because it is under 2,032 bytes. An embedding of 1,536 dimensions takes 6,152 bytes, so it moves out of line, and the last section works out what that costs.

Evidence
The tuple and line pointer sizes are verified from the PostgreSQL 17 docs, section 65.6.1 and Table 65.2. The TOAST rules are verified from the PostgreSQL 17 docs, section 65.2, "TOAST". The 2,032 and 1,996 follow from the macros in heaptoast.h, lines 23 to 26, 46 to 48 and 84 to 89, at REL_17_11, and vector_storage.py repeats the arithmetic.

### What does a write cost?

Write amplification is the bytes the device writes per byte the application changes. For a B-tree page, it depends on c, the changes the page collects between two writes.

- An insert changes one heap page and one leaf in every index. Each change appends a WAL record and leaves its page dirty.

- The first change to each page after a checkpoint also writes a full page image into the WAL.

- Later, each page is written once. So one page change costs WAL record + 2 × 8,192 / c bytes. A row change adds this up over its pages.

Bytes per byte changed, for a 100-byte change and a 150-byte WAL record, both examples. From the model, not measured.

A page with 100 changes costs 53 times less per change, so c decides the cost. A heap page collects about 6 inserts, and a random-key leaf about 1.

Bytes one INSERT writes, from the model

Indexes on the table
Changes each leaf collects, c
Per insert , or  per byte of a 1,210-byte order

With two random-key indexes, the model gives 35,949 bytes per insert, 30 bytes per byte of the order. A HOT update, a heap-only tuple update, keeps the new version on the same heap page. It adds no index entries. It applies when no indexed column changes and the page has room. Any other update writes the same pages as an insert.

Every index pays its own write. An update that is not HOT adds an entry to every index. The docs give the two HOT conditions: the update must not modify any columns referenced by the table's indexes, and there must be sufficient free space on the page that holds the old row. Then "New index entries are not needed". Since PostgreSQL 16, a change to a column that only BRIN indexes cover still allows HOT, and the docs call BRIN a summarizing index. Uber's post "Why Uber Engineering Switched from Postgres to MySQL" described one such update: "we had to issue at least four physical updates". Its example changed an indexed column, so HOT could not apply. The post gives no measured byte counts. It is a design argument, and its conditions matter.

The key type decides c. A UUID is a 128-bit identifier, and a version 4 UUID is random, so two inserts in a row get unrelated values. In one test, a table with only a primary key took 5,000 inserts per second for an hour. A sequence key wrote about 2 GB of WAL. A random UUID key wrote over 40 GB, mostly page images.

Buildkite used integer primary keys, and random UUIDv4 values as a second key for external use. The post says random keys spread recent rows over many index pages and lower the cache hit rate. Around 2022, the team started to put a timestamp in the first 48 bits of each new UUID. With this and other changes over 6 weeks, the WAL rate of the primary database fell by 50%. Write I/O to the disks fell by about the same amount. The post does not say how much of the 50% came from the UUID change. In 2023 the team chose UUIDv7, a time-ordered UUID, as the primary key for all new tables.

Evidence
Tomas Vondra, "On the impact of full-page writes", EDB blog, 2016: "a 1h benchmark, throttled to 5000 inserts per second". "With BIGSERIAL primary key this produces ~2GB of WAL, while with UUID it’s more than 40GB." And: "Clearly, vast majority of the records are full-page images". Verified from the post. The factor of about 20 is this course's arithmetic from his two numbers. The post does not give the PostgreSQL version, the hardware or the checkpoint settings. Gordon Chan, "Goodbye integers. Hello UUIDv7!", Buildkite, 2023-09-25, https://buildkite.engineering/goodbye-integers-hello-uuids/, verified from the post.

The failure is a random key, such as gen_random_uuid(), on a large write-heavy table. Every leaf joins the working set, and almost every insert pays a page image. A key that grows with time avoids this.

### Where does the random key come from?

Your ORM often chooses the key for you. The Django docs show a UUID primary key as models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False), and Python's docs say "uuid4() creates a random UUID". The Rails guide for PostgreSQL shows create_table :devices, id: :uuid. It says that gen_random_uuid() "is assumed if no" :default option was passed. So a model that switches to UUID keys with the documented example gets the random-key write cost of this section.

- Check. Search your migrations for UUIDField( and id: :uuid before a table grows large.

- On PostgreSQL 17. It has no uuidv7(), so generate a version 7 UUID in the application, or use a bigint identity column. Python 3.14 adds uuid.uuid7().

- On PostgreSQL 18. uuidv7() generates "timestamp-ordered UUIDs", per its release notes.

Evidence
The Django 5.2 model field reference, the Python uuid docs and the Rails guide "Active Record and PostgreSQL", read on 2026-10-20. The absence of uuidv7 in 17 is from a search of pg_proc.dat at REL_17_11, which found no such function.

Stripe shows the opposite effect. It moves data between shards of DocDB, its document database built on MongoDB Community, and its bulk loads were slow at first. The team then sorted the data "based on the most common index attributes in the collections" and inserted it in that order. The post says this took "advantage of the fact that DocDB arranges its data using a B-tree", "boosting write throughput by 10x". Sorted inserts land on a few neighbouring leaves, so each leaf takes many changes between two writes, and c is large.

Evidence
The Stripe quotes are from a post by Morzaria and Narkhede on stripe.dev of 2024-06-06, about data migrations with no downtime, verified from the post. The post itself says DocDB is "an extension of MongoDB Community".

### What do you see when c is near 1?

c counts changes between two writes of a page, and the checkpointer is not the only writer. Suppose the buffer pool is smaller than the set of leaves that receive changes. Then a dirty leaf is evicted long before the next checkpoint. The bgwriter or a backend writes it, and a later change reads it back. So c is bounded by how long a page stays in the pool, not by the checkpoint interval. The full page image still comes once per checkpoint, so early eviction adds page writes, not WAL. This is inferred from eviction and Phase 1's write path.

Each version shows who wrote the pages in a different place:

Writer | PostgreSQL 14 | PostgreSQL 17 and 18

checkpointer | pg_stat_bgwriter.buffers_checkpoint | pg_stat_checkpointer.buffers_written

bgwriter | pg_stat_bgwriter.buffers_clean | pg_stat_bgwriter.buffers_clean

a backend | pg_stat_bgwriter.buffers_backend, "buffers written directly by a backend" | pg_stat_io.writes where backend_type = 'client backend' and context = 'normal'

-- Who wrote the table and index pages since the last reset? PostgreSQL 17
select backend_type, context, writes, evictions, reuses
from pg_stat_io
where object = 'relation' and writes > 0
order by writes desc;
select buffers_written from pg_stat_checkpointer;

A large client backend share of the writes in context normal is the sign of the c near 1 case. That reading is inferred. To find the statement that writes the page images, read pg_stat_statements, which has wal_records, wal_fpi and wal_bytes per statement. pg_stat_user_tables shows how often HOT happens, in n_tup_upd and n_tup_hot_upd. n_tup_newpage_upd counts updates whose new version went to another page: "These are always non-HOT updates".

Evidence
The 14 columns are from the PostgreSQL 14 docs, Table 28.21. The 17.0 release notes record the removal of buffers_backend and the new view pg_stat_checkpointer. The 17 columns are verified from system_views.sql at REL_17_11, lines 1134 to 1173. The wal_fpi column of pg_stat_statements exists since its version 1.8, at pg_stat_statements--1.7--1.8.sql. n_tup_newpage_upd exists since PostgreSQL 16, and the quote is from the 17 docs.

### Does an index shrink after a mass delete?

No, but it does not decay either. PostgreSQL never merges half-empty pages. VACUUM does delete a leaf that has become completely empty, unless it is the rightmost page of its level. A later split reuses that page through the free space map. InnoDB is different, because it tries to merge a page that falls below MERGE_THRESHOLD, "50% by default". So after a mass delete, a PostgreSQL index file keeps its size on disk:

- Its emptied pages are reused by later inserts.

- Its half-empty pages stay half empty, unless new keys fall into their key range. Only a REINDEX packs them.

- The tree stays balanced the whole time.

So an index does not need regular rebuilds. It needs one when its half-empty pages cost memory or I/O that you measured. VACUUM VERBOSE on 17 prints one line for each index that it scanned, with the pages of the index in total, and how many are newly deleted, currently deleted and reusable. pgstatindex shows avg_leaf_density, empty_pages and deleted_pages. Measure with both before you rebuild. Phase 4 gives the locks a REINDEX takes.

Evidence
No merging: Rogov, page 425, "once split, nodes can never be merged together, even if they contain very few elements after vacuuming". Page deletion: the nbtree README at REL_17_11, section "Deleting entire pages during VACUUM", lines 232 to 240, which says VACUUM deletes a page "only when it's become completely empty of items". Reuse: the same README, "Placing deleted pages in the FSM", line 383. The VACUUM VERBOSE format is at vacuumlazy.c line 726, REL_17_11. The InnoDB threshold is from the MySQL 8.4 manual. "No regular rebuilds" follows from the quotes and is inferred.

Predict the height and the memory above the leaves for a billion keys. Then run uv run python phase02_structures/btree_model.py --keys 1000000000 --indexes 2, and compare. Then run psql -h /tmp -p 5432 -d storage_lab -c "select relname, n_tup_upd, n_tup_hot_upd, n_tup_newpage_upd, n_tup_upd - n_tup_hot_upd as not_hot from pg_stat_user_tables order by n_tup_upd desc limit 5". Each not_hot update wrote a new entry in every index of its table. E13 shows a real page and the WAL per insert.

A row change writes the heap page and a leaf per index, each with a page image after a checkpoint.

A random key makes every leaf hot, and costs about 20 times the WAL of a sequence.

A B-tree changes each page in place, so the next section asks what a store gains when it appends every write instead.

Go deeper: the two layouts, TOAST, the page, splits, the full write model, InnoDB 8.4 defaults, HOT history
Why the B-tree is the common choice. The B-tree is the default index type of PostgreSQL, and InnoDB stores every table inside one. Its keys are sorted, so the report's range is one walk along the leaves. And only its top levels must stay in memory, so RAM no longer limits the number of keys. A write changes the leaf in place, in the buffer pool.

The height, in five steps. For PostgreSQL 17 and an 8-byte key:

- A page has 8,192 − 24 − 16 = 8,152 bytes for entries, after the page header and the B-tree's own data.

- One entry is 20 bytes: an 8-byte header holding the TID, the 8-byte key, and a 4-byte line pointer.

- An index build fills a leaf to 90% and an inner page to 70%. So a leaf holds 8,152 × 0.9 / 20 = 366 entries, rounded down, and an inner page 8,152 × 0.7 / 20 = 285.

- 10 million keys need 27,323 leaves, 96 inner pages and 1 root. That is a height of 3.

- The 97 pages above the leaves take 97 × 8 KiB = 776 KiB.

So the B-tree needs 776 KiB of memory where the keydir needs 300 MB. The price is one more page read per lookup, because the keydir knew the exact offset and the tree must read a leaf to find it.

What a write does to the page, and after a crash. Each change leaves its page dirty in the buffer pool, and the page reaches its data file later through one of the three writers. If the server crashes first, recovery replays the change from the WAL, starting at the REDO point. The heap share of 2,881 bytes per insert is 150 + 16,384 / 6, and a random-key leaf at c near 1 costs 150 + 16,384 = 16,534 bytes. 35,949 bytes is 30 bytes per byte of a 1,210-byte order.

The random-key failure, in more words. Suppose the order id is a version 4 UUID. Each insert lands on a random leaf, so every leaf is part of the working set. The buffer pool must then hold the whole index or miss. Splits in the middle leave pages half full, and in InnoDB they split the table itself. gen_random_uuid() has been in core since PostgreSQL 13.

The random-key measurement, explained. A sequence puts each new key on the same rightmost leaf, so few changes are first changes after a checkpoint. A random UUID lands on a different leaf on almost every insert. That is why most of its WAL was full page images, about 20 times the sequence key's WAL. With random keys, each leaf collects few changes before it is written, so c is near 1.

A row in the heap. A heap tuple starts with a fixed header, "occupying 23 bytes on most machines". Each tuple also takes a line pointer, "4 bytes per item". Phase 3 explains the header's fields. An order of the running case has 1,210 bytes of key and value. With its header and length bytes, it takes about 1,250 bytes of a page. So about 6 orders fit on one heap page of 8,192 − 24 = 8,168 usable bytes. That count is inferred from the docs' sizes, and was not checked with pageinspect.

Where the height inputs come from. All are from PostgreSQL 17 at tag REL_17_11, and they are the same at REL_18_6. The page header is 24 bytes, from PageHeaderData in bufpage.h and Table 65.2 of the 17 docs. The B-tree's own data at the end of the page, BTPageOpaqueData in nbtree.h, is 16 bytes. The fill factors are BTREE_DEFAULT_FILLFACTOR and BTREE_NONLEAF_FILLFACTOR at nbtree.h lines 200 and 201. The index tuple header is IndexTupleData at itup.h lines 35 to 51: a 6-byte TID and a 2-byte t_info. The leaves round up from 10,000,000 / 366 = 27,323, the inner level is 27,323 / 285 = 96 pages, and the root is 96 / 285 rounded up to 1 page. For a billion keys, the same arithmetic gives 4 levels and 9,622 pages above the leaves, about 75 MiB. btree_model.py repeats this arithmetic with your own inputs.

A real index agrees. Rogov inspects bookings_pkey on PostgreSQL 14, an index on 6-character booking codes. Its inner page holds 285 entries. Its leaf holds 367: 366 keys and the high key, an upper bound for the keys on the page. The 7 bytes of key data round up to the same 16-byte index tuple. That rounding is inferred from 8-byte alignment.

Evidence
Rogov, "PostgreSQL 14 Internals", pages 428 and 429. Verified from the book.

The keydir's 30 bytes. A compact keydir entry needs the 10-byte key, an 8-byte offset, a 4-byte size and an 8-byte sequence number. That is 30 bytes per key before any hash-table overhead, the figure the opening used. The Phase 1 store in Python uses much more per key, and that was not measured.

The page itself. Every PostgreSQL page, heap and B-tree pages alike, is a slotted page. The source draws it at bufpage.h lines 29 to 42, REL_17_11:

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

A TID names a line pointer, not a byte offset. So a tuple can move inside its page without any change to the index entries that reach it.

When a leaf is full. A full leaf splits into two pages, and the parent gets one more separator. The fill factor applies only in some splits, as this comment in the source says:

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

So keys that always grow, such as a time or a sequence, fill the rightmost page to 90%. They leave full pages behind. Keys in random order split pages in the middle, into two halves. In Facebook's production databases, B-tree pages were "only 1/2 to 2/3 full". So the B-tree used more than 1.5 times the space of its data.

Evidence
Dong and others, "Optimizing Space Amplification in RocksDB", CIDR 2017, section 3. Verified from the paper.

What a split writes. A leaf split changes up to four pages:

- The full page keeps the lower keys.

- A new right sibling gets the upper keys.

- The old right neighbour, if there is one, gets a new left link.

- The parent gets the new separator, in a separate WAL record.

The split's WAL record holds the items that go to the new right page: "On insert with split, we save all the items going into the right sibling". And: "The left page, however, is handled in the normal incremental-update fashion". So the new right page never takes a full page image. The left page, the old neighbour and the parent each take an image if this is their first change since the checkpoint. So a leaf split logs about half a page of tuples, plus those images. That size is inferred from the comment. A pg_waldump of one split would confirm it.

Evidence
The WAL quotes are from the comment in nbtxlog.h at REL_17_11, lines 90 to 95. nbtinsert.c registers the new right page with REGBUF_WILL_INIT at line 1985, REL_17_11. Both verified.

A case of a file that never shrinks. Roblox had a 73-hour outage with one cause in BoltDB, the file store that Consul uses for its Raft log. The Roblox post says: "even when the oldest log entries are deleted, the space BoltDB uses on disk never shrinks". Freed 4 kB pages went on a "freelist". One "4.2GB log store is only storing 489MB of actual data". Its freelist was 7.8 MB. Each log append wrote that whole freelist, "even though the actual raw data being appended was 16kB or less". The fix was to compact the file. PostgreSQL keeps its free space in a separate free space map, so this exact failure is not one it has. That is inferred. The rule still holds that reused pages keep the file large, and only a rebuild returns the space.

Evidence
Roblox, "Roblox Return to Service 10/28-10/31 2021", read on 2026-10-20. The outage ran from 28 to 31 October 2021.

The write model, step by step. Each change writes one WAL record. After a checkpoint, the first change to a page also writes the whole page into the WAL, for the torn-page reason Phase 1 explained. Then the page itself is written once. So each change to a page costs the WAL record plus two pages shared by c changes:

bytes per page change = WAL record + 2 × 8,192 / c
bytes per row change  = sum over its pages of (WAL record + 2 × 8,192 / c of that page)

c | bytes per page change | bytes per byte changed

1 | 150 + 16,384 = 16,534 | 165.3

10 | 150 + 1,638 = 1,788 | 17.9

100 | 150 + 164 = 314 | 3.1

The full page term is an upper bound, because PostgreSQL leaves the free space out of a full page image. Fewer checkpoints let each page collect more changes. But recovery then has more WAL to replay, as Phase 1 showed. Mark Callaghan measured the same effect in InnoDB, whose WAL is called the redo log. With the data in memory, his insert benchmark wrote 5.31 KB per insert with a 4 GB redo log, and 1.66 KB with a 32 GB one. In his words, "A larger redo log reduces the InnoDB write rate per insert by more than half". With the data larger than memory, the gain was smaller. The amplification section gives those numbers beside an LSM's.

Evidence
Mark Callaghan, Small Datum, 2017, InnoDB from MySQL 5.7.17, insert benchmark.

Which pages a row change touches. An INSERT changes one heap page and one leaf in each index. An UPDATE that is not HOT does the same. When the new version goes to another heap page, the old version's page changes too. That follows from Phase 3's row versions, and is inferred here. A HOT update changes only the heap page. The heap share of 2,881 bytes is 150 + 16,384 / 6. btree_model.py --indexes 2 --heap-changes-per-page 6 prints the 35,949-byte sum.

Two details of the heap page. The model uses one 150-byte WAL record for every page. Two details of the heap page move its share in opposite directions. Its insert record holds the whole new tuple, so it is about 1,300 bytes here. And the first insert on a fresh heap page sets XLOG_HEAP_INIT_PAGE, so that page takes no full page image. That is at heapam.c lines 2218 to 2222, REL_17_11. With both, the heap share is about 1,300 + 8,192 / 6 = 2,665 bytes. The total is then about 35,700 bytes, still about 30 bytes per byte. The 1,300 is inferred from the tuple size, and not checked with pg_waldump.

The random-key measurement, per insert. The run made 5,000 × 3,600 = 18 million inserts. So each insert wrote about 110 to 120 bytes of WAL with the sequence key. With UUID it wrote about 2.2 to 2.4 kB. The ranges exist because the post does not say whether a GB is 10^9 or 2^30 bytes. 2.2 kB is about a quarter of an 8 kB page image. So the leaves collected a few inserts between checkpoints, or the page images were smaller than 8 kB. A page image leaves out the free space, and half-full leaves have much of it. Both readings are inferred. The c = 1 row above is the worst case.

The test's limits matter. Its charts are images, and this course did not read them. For uniform random UPDATEs, the key type stopped mattering, because most of the WAL was then for the heap, not the indexes. The HOT case "pretty much eliminates all index-related WAL traffic". The same post warns that "in practice there will be secondary indexes, foreign keys etc.". Each of those adds a leaf per row change, by the sum above.

InnoDB in MySQL 8.4: three defaults that touch this section. MySQL 8.4 changed defaults that move the write and lookup costs above:

Setting | 8.0 default | 8.4 default | What it does

innodb_change_buffering | all | none | the change buffer "caches changes to secondary index pages when those pages are not in the buffer pool", and merges them later when a read loads the page

innodb_adaptive_hash_index | ON | OFF | a hash index that InnoDB builds "on demand for the pages of the index that are accessed often", so a lookup can skip the tree walk

innodb_io_capacity | 200 | 10000 | how fast InnoDB flushes dirty pages, which bounds how many changes a page collects

The change buffer was InnoDB's answer to the random-leaf writes of this section. It let an uncached secondary leaf collect changes before InnoDB read it, so c rose. With none, each such change reads its leaf first, as PostgreSQL does. That consequence is inferred from the manual's description. The manual names the costs of the two features. A change buffer merge "may take several hours" when many rows and many secondary indexes are affected. And "Access to the adaptive hash index can sometimes become a source of contention under heavy workloads". The effect of innodb_io_capacity on c is inferred. After an upgrade from 8.0, compare secondary-index reads before and after, on a copy of production.

Evidence
The 8.4 defaults come from the manual's page on changes since 8.0. The costs come from its pages on the change buffer and on the adaptive hash index. All were read on 2026-10-20.

PostgreSQL has lowered that index cost in three releases:

- 12.0. "Improve performance and space utilization of btree indexes with many duplicates". Before, duplicates were "stored unordered within their duplicate groups". Now they are "sorted in heap-storage order". So equal keys are ordered by their TID. That reading is inferred from the quote.

- 13.0. "More efficiently store duplicates in B-tree indexes". This deduplication keeps one key with a list of TIDs. It "occurs lazily, when a new item is inserted that cannot fit on an existing leaf page".

- 14.0. "Allow btree index additions to remove expired index entries to prevent page splits". The docs call it bottom-up deletion. A pass "is triggered in reaction to an anticipated 'version churn page split'".

So on version 14 and later, non-HOT updates grow an index less than they did when Uber wrote. That is inferred from the release order, and the size of the change is not measured here. Phase 4 explains the table fillfactor that leaves room for HOT.

Evidence
The HOT conditions are from the PostgreSQL 17 docs, section 65.7, "Heap-Only Tuples". BRIN and HOT are from the 16.0 release notes. The Uber post is from 2016. Each release line is verified from the 12.0, 13.0 and 14.0 release notes. Deduplication and bottom-up deletion are from the PostgreSQL 17 docs, sections 64.1.4.3 and 64.1.4.2. gen_random_uuid() in core is from the 13.0 release notes, and uuidv7() from the 18.0 release notes.

## 2.3 Why does an LSM tree write fast and read across runs?

An LSM write is cheap now because its real cost comes later.

A B-tree changes pages in place, and a random key makes almost every change pay a page image. A log-structured merge tree, or LSM tree, appends every write and still keeps keys sorted.

A put appends to a WAL, then inserts into the memtable, a sorted map in memory. A full memtable becomes one sorted run, or SSTable, a file in key order that never changes. New runs go to level 0, L0. Compaction later merges them into larger runs in L1, L2 and below. A get looks in the newest place first, and the first version it finds wins. A tombstone found first means the key was deleted.

- put(k, v): append to the WAL

- memtable, 64 MB: sorted, in memory

- flush: one run into L0

- compaction: at 4 L0 runs, into L1 and below

- memtable: no I/O

- each L0 run: newest first, they may overlap

- L1 run: one per level

- L2 run: first version found wins

Predict: a store has a memtable, three L0 runs and one L1 run, no filters, and each run's index in memory. How many data blocks does a get read for a key in L1, and for a missing key?
Four blocks in both cases. Each L0 run was a memtable of keys from everywhere, so each one covers nearly the whole key range. The get reads one wasted block in each L0 run, then one block in L1. A missing key pays the same four blocks, all wasted. The Phase 1 store reads one block for a present key and none for an absent one, because its keydir knows every key.

Each run keeps its block index in memory, so a get reads at most one block per run. Runs in L0 may overlap, and deeper runs do not. So a get checks every L0 run that covers its key, and at most one run per deeper level. Read amplification is the work a read does beyond the data it returns, here blocks per get. A range scan reads every overlapping run. Still, a 100-key range in the lab costs the LSM 4 blocks and the Phase 1 log 103.

A delete puts a tombstone, which must stay while an older value may exist deeper. The failure is that the write is cheap only now. A put is one append and one memory insert, but compaction rewrites the entry at every level. A benchmark that ends before compaction catches up measures only the cheap part.

### Where do you meet an LSM tree?

Several systems in this lesson are built this way:

- RocksDB is a key-value storage library that a program links in. Facebook built it, and MyRocks is MySQL on top of it.

- Cassandra and ScyllaDB are distributed databases that store each node's data in an LSM tree. Discord ran both, as the compaction section tells.

- Pebble is the storage engine under CockroachDB, a distributed SQL database. The compaction section tells a CockroachDB storm on RocksDB, with the fix in Pebble.

You may never run one of them directly. You meet an LSM tree when a system you depend on is built on one, and then the questions of this section decide its latency.

The cheap part, and its limits. The cheap part holds only for a raw key-value Put, which reads nothing. A SQL engine on an LSM reads the old row first, as the workload section shows. So an LSM tree trades an in-place write for later work, and a single read for several. That a short benchmark measures only the cheap part is inferred from the design, and the amplification section puts numbers on the full cost.

Count both caches. RocksDB keeps recently read blocks in its block cache: "The block cache stores uncompressed blocks". Out of the box it is an LRU cache of 32 MB, "8MB before version 8.2". RocksDB also reads its files through the kernel by default, because use_direct_reads is false at options.h line 1153, v11.8.1. So by default the page cache holds compressed blocks of the files, and the block cache holds uncompressed copies of some of them. That is inferred from the two facts. It is the same double caching as PostgreSQL's, so a RAM budget must count both caches.

Evidence
The quotes are from the RocksDB wiki page "Block Cache".

Run uv run python phase02_structures/lsm.py --demo. Count the flush lines before each compaction line, and find the option in the defaults table below that sets that count.

The rewrite at each level is compaction, and the next section shows what it does and when it stalls writes.

Go deeper: why appending wins, RocksDB defaults, get() in code, range arithmetic
The read and write paths in more words. A put does two things. It appends the entry to a write-ahead log, exactly as the Phase 1 store does. Then it inserts the entry into the memtable. When the memtable reaches its size limit, the store writes it out as one sorted run. A get checks the memtable, then each L0 run from newest to oldest, then L1, L2 and below. Sizes in the figure are the RocksDB defaults. A read pays for this design, because it may have to look in several places.

Read amplification in two units. This lab counts it in two ways. One is the number of blocks a get reads from the device. The other is those bytes divided by the bytes of the value. The range counts are worked out from the code and were not run, as the arithmetic below shows.

Why a tombstone must stay. If a tombstone left before an older value of its key in a deeper run, a get would skip the missing tombstone and find the old value.

Why appending wins, in the original design. The LSM tree was designed for disks with moving arms. Its cost model compares a page written at a random place with a page written inside a long sequential write. On the disks of that time, the sequential page cost about 1/10 as much. A B-tree insert pays a random page write, and an LSM insert pays a share of a large sequential merge. The model multiplies the two savings, and concludes: "Typically the product of the two ratios will give a cost ratio improvement of nearly two orders of magnitude". On an NVMe SSD, a random write costs much less compared with a sequential one, so the advantage is smaller. That last point is inferred, and not measured here.

The same design gives the shape of a good LSM tree. The cost is lowest when each level is the same multiple of the level above. That ratio is called the fanout. RocksDB uses one fanout for every level, 10 by default.

Evidence
O'Neil, Cheng, Gawlick and O'Neil, "The Log-Structured Merge-Tree", sections 3.1 and 3.2, pages 11 to 14, Equation 3.4 and Theorem 3.1. They used an IBM 3380 figure: a random page took 20 ms, and a page inside a 64-page transfer took 2 ms. The model is for disks of 1995. Verified from the paper.

One run in the lab. A run in this course's lab has four parts, like RocksDB's block-based table. Data blocks of about 4 KB hold entries in key order, in the Phase 1 entry format with its CRC. The index holds one entry per block: its first key, offset and length. The filter, which the next sections explain, covers every key in the run. The footer says where the index and the filter start.

The RocksDB defaults. These names and values come from the RocksDB source at tag v11.8.1, include/rocksdb/options.h and advanced_options.h:

Option | Default | What it does

write_buffer_size | 64 MB | memtable size that starts a flush

max_write_buffer_number | 2 | memtables in memory, the full one included

level0_file_num_compaction_trigger | 4 | L0 runs that start a compaction into L1

max_bytes_for_level_base | 256 MB | target size of L1

max_bytes_for_level_multiplier | 10 | the fanout: each level 10 times the one above

level_compaction_dynamic_level_bytes | true | sizes levels from the last level upward

compaction_style | kCompactionStyleLevel | leveled compaction

The RocksDB tuning guide states the overlap rule above: L0 runs may overlap, and deeper runs do not.

The read path in code. This is the lab's get, from lsm.py:386, with the counter lines removed:

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

Range reads, in numbers. The RocksDB tuning guide gives the read amplification of a range as number_of_level0_files + number_of_non_empty_levels. Take the lab's defaults: 20,000 keys of 133-byte entries in 4,096-byte blocks, and a range of 100 keys. A block holds 30 entries, because 30 × 133 = 3,990 bytes and a 31st entry would pass 4,096. In L1, 100 entries fill 100 / 30 = 3.3 blocks, so 4 or 5 block reads. An L0 run holds a few keys of the range, usually in one block. The Phase 1 store must check all 20,000 keys in its keydir, then make 100 separate reads at scattered offsets. E6 runs this with --range-demo, right after the load. The load ends with 40 flushes and 10 compactions, so L0 is empty. The expected result is 103 blocks for the log and 4 for the LSM. Both counts are worked out from the code and its seed, and were not run.

When a tombstone may go. The compaction section gives the rule for when a tombstone may be dropped. The Bloom filter section adds one more place where it must stay.

## 2.4 What does compaction do, and when does it stall writes?

An LSM put is cheap because its rewrite waits. Compaction is that rewrite: it reads old files and writes new ones that hold only the live data. An entry is live when it is the newest version of its key and not a tombstone. Everything else is garbage. Compaction decides the space and the total bytes written, and when it falls behind, the latency. A range scan must also read past every tombstone in its range until compaction drops them.

### How does Bitcask merge its log?

This is the step Phase 1 left out. A merge reads the immutable data files of the log. It writes the newest live entry of each key into new files. Beside each it writes a hint file: each key with its position and sizes, but no value. A restart reads the hints instead of the data.

738,300 B: 200 orders written 3 times, 10 deleted

240,920 B: after the merge, hints included

7,220 B: what a restart reads with the hints

The merge replaces files, so its new files must be durable before the old ones are removed. If the removal is made durable first, a power loss there loses every order.

### How do leveled and tiered compaction differ?

 | Leveled | Tiered, "universal" in RocksDB

Shape | one sorted run per level, each 10 times the level above | several runs of about the same size per level

Write amplification per level | up to the fanout, the size ratio between levels, because the merge rewrites the level below too | 1, because each byte is written once per level

Space | about 1.1 times the data | up to 3 times the data by default, then a full merge. Each merge also needs room for its output

Reads | few runs to check | more runs to check

RocksDB's leveled example writes each byte of a 500 GB database 1 + 2 + 10 + 10 + 10 = 33 times. Its universal default lets a 100-byte database need up to 300 bytes of storage. Past that, RocksDB merges all files into one sorted run. That is the opening's tripled disk. The merge itself needs up to 2 times the space of the files it rewrites.

### What happens when compaction falls behind?

When compaction runs slower than writes arrive, runs pile up in L0, and RocksDB slows or stops writes.

- 4 runs in L0: a compaction into L1 starts

- 20 runs in L0: writes slow to 16 MB per second

- 36 runs in L0: writes stop

The failure is compaction run at one time of day. The opening's team ran it at night, but waiting does not shrink the work. In the lab's model, one merge holds the device for 4.2 ms in every 111 ms. So the p99 of puts falls inside the merge. Paced in 0.25 ms slices, the same work keeps waits short, but more runs exist to read.

### What do you see when it falls behind?

RocksDB writes each stall to its LOG file. The Write Stalls wiki page gives these lines. The file counts are from the wiki's own example, not from the defaults:

Stalling writes because we have 4 level-0 files
Stopping writes because we have 20 level-0 files
Stalling writes because of estimated pending compaction bytes 500000000

The source at v11.8.1 adds two parts that the wiki leaves out. Each line starts with the column family name in square brackets. A slowdown line also ends with rate and the delayed write rate in bytes per second. The format strings are at db/column_family.cc lines 1087 and 1130.

RocksDB also dumps compaction statistics into the LOG every stats_dump_period_sec, 600 seconds by default at options.h line 1217, v11.8.1. db->GetProperty("rocksdb.stats") returns the same text. Here is the wiki's example from the page "Compaction Stats and DB Status". This course cut eleven columns, the Int row and two summary lines. The wiki gives no version or workload for it:

** Compaction Stats **  (cut: Rn, Rnp1, Moved, Rd, Wr, Comp(sec), Comp(cnt), Avg(sec), Avg(ms), KeyIn, KeyDrop)
Level   Files  Size(MB)  Score  Read(GB)  Write(GB)  Wnew(GB)  W-Amp  Stall(sec)  Stall(cnt)
L0        2/0        15    0.5       0.0       32.8      32.8    0.0        0.00           0
L1       22/0       125    1.0     163.7      165.5      34.6    5.1        0.00           0
L2      227/0      1276    1.0     262.7      262.7      34.3    7.6        0.00           0
L3     1634/0     12794    1.0     259.7      254.1      26.1    8.0        0.00           0
L4     1819/0     15132    0.1       3.9        3.6       1.6    1.8        0.00           0
Sum    3704/0     29342    0.0     690.1      718.7     129.4   21.9        0.00           0
Stalls(count): 0 level0_slowdown, 0 level0_numfiles, 0 memtable_compaction, 0 leveln_slowdown_soft, 0 leveln_slowdown_hard

Three columns answer this section's questions on a live store:

- Score. For levels below L0, it is the level's size over its target size: "any value greater than 1 means that level needs to be compacted". For L0 it counts files against the compaction trigger.

- W-Amp. The wiki defines it as "(total bytes written to level N+1) / (total bytes read from level N)". In the Sum row it is 21.9. That is 718.7 GB written over the 32.8 GB that flushes wrote into L0. This course checked the division, and it matches.

- Stall(sec) and Stall(cnt). They count how long, and how often, writes waited because the level was not compacted. The Stalls(count) line splits the stalls by cause.

So the Sum row's W-Amp is the measured write amplification of compaction. The amplification section asks you to estimate that number. Here it is 21.9, against the 33 of the tuning guide's arithmetic above.

A compaction storm in a bulk load. Two CockroachDB engineers described one in a post on faster bulk loading. Cockroach Labs wrote it about its own product, so it is a vendor source:

- The problem. Imports filled L0 faster than RocksDB could compact it. RocksDB then started "a giant compaction from L0 to LBase". LBase is the highest level below L0 that holds data. The compaction "could take it minutes, sometimes ten or more, to complete". While it ran, no other L0 compaction could start. When L0 reached its limit, the write backpressure would "bring the entire job to a standstill".

- The fix, in Pebble. Pebble arranged L0 runs into sublevels. A sublevel is a set of L0 runs whose key ranges do not overlap. So a read checks at most one run in each. 847 L0 runs fit into 13 sublevels, so a read checks 13 places instead of 847.

- The test. It imported TPC-C, a standard order-processing benchmark whose size is set in warehouses. It loaded 50,000 warehouses, about 5 TB, on 10 AWS c5d.4xlarge nodes with local SSDs.

- The result. Before the fix: 6.5 to 10 hours, plus 3 to 6 hours of compaction. After it: 1 hour 15 minutes to 1 hour 30 minutes, plus 30 minutes.

A later CockroachDB post describes admission control. It keeps read amplification at or below a threshold, 20 by default. It notes overload situations where read amplification reached 1,000.

Evidence
Bilal Akhtar and David Taylor, "Faster bulk-data loading in CockroachDB", Cockroach Labs, 2020. Sumeer Bhola, "Here's how CockroachDB keeps your database from collapsing under load", Cockroach Labs, 2022.

Pacing compaction in production. The lab's --compaction paced flag has a real counterpart. rate_limiter is null by default, at options.h line 734, v11.8.1. You set it with NewGenericRateLimiter(rate_bytes_per_sec). The wiki page "Rate Limiter" says this "controls the total write rate of compaction and flush in bytes per second". It adds that RocksDB "does not enforce rate limit for anything other than flush and compaction, e.g. write to WAL". A limit below the rate that compaction must keep only moves the problem into L0 and the stall table below. That is inferred from the stall conditions. A write that must never wait can set no_slowdown = true in WriteOptions. It then returns Status::Incomplete() instead of blocking, per the Write Stalls page.

### What do deletes cost a range read?

A tombstone costs more than space. A range scan must read each tombstone in its range and skip it, until compaction drops the tombstone at the last level. A queue shows the failure. It deletes its oldest items first, so "there can be a large amount of 'tombstones' in the beginning of each queue_id". Then Seek(<queue_id, 0>) and the Next() past the last item "might be exceptionally slow". The fix is ReadOptions.iterate_upper_bound, which stops a scan at the end of its range. Discord's tombstones, in the cases below, look like the same problem in Cassandra. That link is inferred. RocksDB has three tools for it:

- DeleteRange deletes a whole key range with one entry. It "creates a range tombstone represented as a single kv".

- SingleDelete removes a key's entry and its tombstone together when compaction lines them up. It is correct only for a key written once since its last delete.

- CompactOnDeletionCollectorFactory starts a compaction for key ranges dense with tombstones. It "helped to reduce range scan performance skews caused by scanning excessed number of tombstones".

Evidence
The queue quotes are from the RocksDB wiki page "Implement Queue Service Using RocksDB". The three tools are verified from the wiki pages "DeleteRange", "Single Delete" and the RocksDB Tuning Guide.

The same shape in PostgreSQL. A queue table in PostgreSQL meets the same problem through its B-tree. A worker claims the oldest job by walking the index from the head of the queue. It steps over entries of jobs that are done but that VACUUM has not removed yet. Brandur Leach measured this with about 50 jobs a second and one long transaction open. The time to lock a job grew "until it's 15x that level at times of 0.1 s and above". VACUUM can remove those entries only when no open snapshot can still see the rows. A B-tree page goes back for reuse only when it is completely empty, as the B-tree section showed. Phase 3 gives the claim query and the rest of that measurement, and Phase 4 explains the cleanup horizon. Agent runners and background-job libraries that keep their jobs in PostgreSQL have this shape.

Evidence
Brandur Leach, "Postgres Job Queues & Failure By MVCC", 2015-05-18, https://brandur.org/postgres-queues, verified from the post, sections "Slow lock time" and "Dead tuples".

The opening's event store deletes old events in key order, and Phase 3's outbox has the same queue shape. So for those stores, retention deletes are normal daily work. That judgement is inferred. The workload section adds a decision-table row for this shape.

Run uv run python phase02_structures/bitcask_merge.py --demo. Check each printed number against the merge arithmetic below.

Compaction keeps the number of runs small, and the next section removes almost every block read that a get still makes in each run.

Go deeper: the merge in code, the guide's arithmetic, stall conditions, the storm in numbers, more cases
What compaction trades. The Phase 1 log and the LSM tree both make writes cheap by putting off work, and compaction is that work. Garbage is older versions, tombstones, and the values they deleted. Compaction rewrites the live entries, so it trades write bytes now for less space and fewer files to read later.

The merge, step by step.

- The log is split into data files. Only the newest, the active file, takes appends.

- When the active file reaches a size limit, it becomes immutable and a new active file starts.

- A merge reads all the immutable files. It writes new data files that hold only the newest live entry of each key.

- Next to each new data file, it writes a hint file. On open, Bitcask reads a hint file in place of its data file when one exists.

The crash-safe merge, in words. A merge replaces files, so the order of its steps matters, as it did for the Phase 1 checkpoint. In the wrong order, an OS crash or a power loss at the bad moment loses every order. E4 crashes the merge at every step to show it.

The guide's arithmetic, in words. RocksDB calls the two styles "Level" and "Universal". In the leveled example, L1 is 512 MB and the database is 500 GB. Each byte is written once to L0. L0 to L1 counts 2, because it also rewrites about as much of L1. Each deeper step merges the byte with 10 times its size.

Falling behind, in more words. If compaction runs as one large job, every request that arrives during the job waits for it. If it runs slower than the writes arrive, unmerged runs pile up in L0. Reads then check more runs, and the store must slow the writes down or stop them. Writes also stop when both memtables wait for a flush, or when 256 GB of compaction work is pending. Each stall appears in RocksDB's LOG file, so it can be seen in production.

The storm, in numbers. The 4.2 ms in every 111 ms is 3.8% of the time, so the p99 of puts falls inside the merge, at a few milliseconds. With pacing, the longest wait is about one 0.25 ms slice. The cost is that more runs exist at any moment, so reads check more places. This is inferred from the model and the reports above, and the lab's --compaction flag shows the two shapes in E9. Compaction removes garbage and keeps the run count down. Both styles must keep up with the writes.

The hint file and the checkpoint. A hint file plays the role of the checkpoint of Phase 1. But there is one hint file per merged data file, and the merge writes it, not a timer.

The lab's hint entry. bitcask_merge.py builds the merge on the Phase 1 entry format. A hint entry is a 4-byte CRC, an 8-byte sequence number, two 4-byte sizes, an 8-byte offset and the key. That is 28 bytes plus the key. The original hint entry has no CRC. The lab adds one for the same reason as Phase 1: a damaged hint must be detected. A damaged hint costs time and not data, because the store then reads the data file instead.

Evidence
The merge and the hint file are described in the Bitcask paper, Sheehy and Smith, page 4.

The merge arithmetic.

- Before the merge: 600 puts × 1,230 + 10 deletes × 30 = 738,300 bytes.

- Live data: 190 orders, each a 10-byte key and a 1,200-byte value, 190 × 1,210 = 229,900 bytes.

- After the merge: 190 entries × 1,230 = 233,700 bytes of data. Add 190 hint entries × 38 = 7,220 bytes of hints.

So after the merge the disk holds 233,700 + 7,220 = 240,920 bytes. A restart that uses the hints reads 7,220 bytes, 32 times fewer than the 233,700 bytes of merged data. That is because a hint entry is 38 bytes and a data entry is 1,230, and a restart reads keys, not values. These numbers are worked out by hand. The self-test of bitcask_merge.py asserts each of them, and it passes, as E1 records.

The crash-safe order in code. Here is the right order and the wrong one, from bitcask_merge.py:314:

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

--crash-test stops the merge at each step. Then it builds the process, OS and power images of Phase 1's simulated file system. Every recovery must return every acknowledged order. In the right order, the old and the new files both exist between the directory sync and the removal. They hold the same entries with the same sequence numbers. Open keeps the highest sequence number per key, so the copies do no harm. In the wrong order, at merge.dir-synced, the old names are gone for good. The new files have durable names but no durable bytes. An OS crash or a power loss there loses every order. E4 gives the expected counts, and the self-test asserts them.

When the merge may drop a tombstone. The merge may drop a tombstone because it reads every immutable file. Every older version of that key is in one of them, since the active file only holds newer entries. A merge of only some files could not drop it, as the LSM rule below shows.

Leveled and tiered, in the wiki's words. For leveled compaction, per-level write amplification "is equal to the fanout in the worst case, but it tends to be less than the fanout in practice". For tiered: "The per-level write amplification is 1 which is much less than for leveled where it was fanout". RocksDB merges only the overlapping part of each level, which it calls "some-to-some". The original LSM design merged all of it.

Evidence
The quotes are from the RocksDB wiki page "Compaction".

A worked example from the RocksDB tuning guide. L1 is 512 MB and the fanout is 10. The database is 500 GB. So L2 is 5 GB, L3 is 51 GB and L4 is 512 GB.

Write amplification, step by step:

- Each byte is written once to L0. That counts 1.

- L0 to L1 writes it again, with about the same amount of L1. That counts 2.

- Each deeper step merges it with 10 times its size. Each counts 10.

The guide's total: "Total write amplification is therefore approximately 1 + 2 + 10 + 10 + 10 = 33". The guide counts from L0, so the WAL write comes on top. That is inferred.

Space amplification has three numbers:

Number | Value | Source

leveled, this example | "(512 MB + 512 MB + 5GB + 51GB + 512GB) / (500GB) = 1.14" | tuning guide

leveled, worst case | 1.111, with a full last level and fanout 10. The upper levels hold 11.1% of the last | Dong and others, CIDR 2017, section 3

universal, old versions | max_size_amplification_percent defaults to 200. "a 100 byte database could require up to 300 bytes of storage" | include/rocksdb/universal_compaction.h lines 45 to 48 and 137, v11.8.1, and the tuning guide

Universal compaction has a fourth number: the room a merge needs while it runs. Past the 200% limit, RocksDB compacts all files into one sorted run. The wiki page "Universal Compaction", section "Compaction Triggered by Space Amplification", says so. During that full compaction, the input files and the output file both stay. So "the DB will be temporarily double the disk space usage". The tuning guide says a compaction "may temporarily increase size amplification by a factor of two". So a large merge needs free space up to the size of the files it rewrites. The 300 bytes is the tripled disk of this lesson's opening.

The lab's two levels. The lab LSM has only L0 and L1. Each compaction merges the L0 runs with the whole of L1, so it rewrites all the live data each time. Its write amplification therefore grows with the data, because L1 grows while the L0 batch does not. More levels with one fanout keep the cost per level fixed. That is why real LSM trees have them, as the original design's level rule says. E5 gives the lab's numbers.

Every stall condition, in order. RocksDB decides stalls in one function, ColumnFamilyData::GetWriteStallConditionAndCause, at db/column_family.cc lines 1011 to 1046, tag v11.8.1. It checks these conditions in this order, and the first match wins:

# | Condition, with the default | Result

1 | unflushed memtables ≥ max_write_buffer_number, 2 | writes stop

2 | L0 runs ≥ level0_stop_writes_trigger, 36 | writes stop

3 | pending compaction bytes ≥ hard_pending_compaction_bytes_limit, 256 GB | writes stop

4 | max_write_buffer_number > 3 and unflushed memtables ≥ that number − 1 | writes slow down

5 | L0 runs ≥ level0_slowdown_writes_trigger, 20 | writes slow down

6 | pending compaction bytes ≥ soft_pending_compaction_bytes_limit, 64 GB | writes slow down

Notes on the table:

- Conditions 2, 3, 5 and 6 apply only when automatic compaction is on.

- With the default of 2 memtables, condition 4 can never apply. So a flush that falls behind stops writes without slowing them first. That is inferred from the order of the checks, and was not tested.

- In a slowdown, writes are held to delayed_write_rate. Its default of 0 means 16 MB per second, unless a rate limiter is set. That is at options.h lines 1367 to 1383.

- The Write Stalls wiki page says each delayed write sleeps "typically 1ms". This course did not find that sleep in the source.

- The same page warns that a stall in one column family stalls the whole database. A column family is RocksDB's name for a separate key space inside one database.

- Flushes and compactions share a pool of background threads, max_background_jobs, 2 by default at options.h line 900.

- The wiki writes the two pending-bytes options without the _limit suffix. The table uses the names in the source.

The tuning guide's default priority. The tuning guide also credits the default compaction_pri = kMinOverlappingRatio, at advanced_options.h line 725. It reports that for two Facebook databases, UDB and msgdb, write amplification "dropped by more than half, compared to previous default". It links to a Facebook internal post for that claim, so its conditions are not checked.

Compaction that falls behind on Cassandra. Discord's Cassandra cluster was "prone to falling behind on compactions". Nodes then showed "cascading latency as a node tried to compact". The team's workaround took a node "out of rotation to let it compact without taking traffic". The same team found ranges full of tombstones "that were never compacted away in Cassandra". Those tombstones held a data migration at 99.9999% for a while. The workload section gives what Discord measured after it moved.

Evidence
Bo Ingram, "How Discord Stores Trillions of Messages", Discord, 2023.

The storm in the lab. amplification.py --latency runs the write-heavy workload at 20,000 arrivals per second. The arrivals do not wait for replies. Such an open-loop load shows a stall as latency, as elite-performance Phase 1, "Measurement before optimisation", taught. A closed loop would hide it as a lower rate. E9 gives the timeline and the arithmetic, worked out from the model and not run. The model has limits. It has one queue, and it changes the data at once while it charges the compaction time later. In RocksDB, the rate limit is rate_limiter, above.

## 2.5 How does a Bloom filter skip a run?

A get still reads a block in every run that covers its key. A Bloom filter per run answers "not here" from memory. It is an array of m bits and k hash functions. Adding a key sets the k bits its hashes point to. A test reads those bits: any 0 means the key was never added, and all 1 means maybe. A "maybe" for an absent key is a false positive, and their share is the false-positive rate, FPR.

The FPR is (1 − e^(−kn/m))^k for n keys. It is lowest at k = (m/n) × ln 2, with half the bits set. Then it is about 0.6185^(m/n). At 10 bits per key, 7 hashes give 0.82%. Each 4.8 more bits per key divide the FPR by 10.

A Bloom filter for the 10 million orders

Bits per key
Best whole k , FPR , memory  against the keydir's 300 MB

For 10 million orders, 10 bits per key is 12.5 MB, 24 times less than the keydir. In the lab LSM, filters cut an absent key's reads from about 2.5 blocks to 0.02. RocksDB quotes 9.9 bits for about 1%, because it packs each key's bits into one 64-byte cache line.

The failure is a filter built without the tombstones. After a delete, a new run holds the tombstone and an older run holds the value. If that run's filter leaves the deleted key out, the get skips the run. The deleted order comes back from the run below. The lab keeps tombstones in the filter at lsm.py:268.

### Where do you see a filter at work?

RocksDB counts filter results in its statistics. The wiki page "RocksDB Bloom Filter" names them:

- rocksdb.bloom.filter.useful counts "[true] negatives", the reads the filter saved.

- rocksdb.bloom.filter.full.positive counts "positives", the times it said maybe.

- rocksdb.bloom.filter.full.true.positive counts "true positives", the maybes that found the key.

The wiki gives the observed FPR of point lookups as "(positives - true positives) / (positives - true positives + true negatives)". A rate well above the table's value for your bits per key means the setting in production is not the one you think.

PostgreSQL has Bloom filters too, in other places. The bloom extension is an index access method "based on Bloom filters". BRIN indexes have bloom operator classes, which "build a Bloom filter for all values in the range". Neither is the per-run filter of an LSM tree.

Evidence
The metric names and the formula are from the RocksDB wiki page "RocksDB Bloom Filter", read on 2026-10-20. The PostgreSQL quotes are from the PostgreSQL 17 docs, F.6 and section 64.5.

Where the filters live. A filter is memory, and so is the index of each run. For a 256 MB run, "the index/filter block of size 0.5/5MB is typical". By default these blocks are kept "outside of block cache". Then only max_open_files bounds their memory. These four options decide where they go:

Option | Default, v11.8.1 | What it changes

cache_index_and_filter_blocks | false, table.h line 238 | true puts index and filter blocks into the block cache, where they compete with data blocks

max_open_files | −1, options.h line 776 | −1 keeps every run open, so every run's index and filter stay in memory

partition_filters | false, table.h line 519 | true splits a run's filter into small blocks that are cached one at a time

optimize_filters_for_hits | false, advanced_options.h line 816 | true stores no filters for the last level

The max_open_files row is inferred from the wiki's sentence and the default. The last row is a shipped form of Monkey's point, below, because the last level holds most keys. The source comment says: "For keys which are hits, the filters in this level are not useful because we will search for the data anyway". So a store whose gets almost always find their key can drop most of its filter memory. Partitioned filters were measured on two old setups, from about RocksDB 5.x. On an 86 GB database on HDD with a 60 MB block cache, "Partitioning improves throughput by 11x from 5 op/s to 55 op/s". LinkBench is a benchmark from Facebook that models a social-graph workload. In LinkBench on 300 GB of SSD with 2 GB of cache, it was 30k tps with partitions and 23k without. The wiki pages have no release tag, so treat these numbers as old.

Evidence
The sizes and the measurements are from the RocksDB wiki page "Partitioned Index Filters". The block cache sentence is from the wiki page "Block Cache".

Filters and ranges. A whole-key filter does not help a range scan, because a range does not name single keys. A prefix Bloom filter does help a range inside one key prefix. If "many sorted runs don't contain any entry for this prefix, it can be filtered out by a bloom filter". An event store keyed by stream id and sequence number reads ranges inside one stream, so it fits that case. That use is inferred. A filter helps every point read, and it costs memory in proportion to the number of keys.

Evidence
The quote is from the RocksDB wiki page "Prefix Seek".

First predict the measured FPR at 4 bits per key from the table below. Then run uv run python phase02_structures/bloom.py --keys 100000 --blocked and compare both measured columns with theory.

An LSM appends now and rewrites at each level later, and filters keep reads near one block.

A short write benchmark ends before compaction runs, so the LSM looks faster than it is.

The next section turns these read, write, space and memory costs into three ratios you can compare across structures.

Go deeper: the FPR table, RocksDB's blocked filter, Monkey, the lab's numbers
What the filter removes. In the run-by-run read path, a missing key cost a block read in each run that covers it. A get for a present key paid the same in each run above the one that holds it. A filter per run answers "the key is not here" from memory, so the store skips almost all of those block reads. All bits start at 0. The filter never says "no" for a key that was added, because that key's bits were all set. If all k bits are 1, the key may have been added, or other keys may have set its bits.

Sizing. For 10 million keys, 10 bits each is 100 million bits, which is 12.5 MB. That is 24 times less memory than the 300 MB keydir.

The lab LSM with filters. An absent key checks 1 to 4 runs, L1 and up to 3 L0 runs, so 2.5 runs on average. At 0.82% each, that is about 2.5 × 0.0082 = 0.02 blocks per get. Without filters, the same get reads one block in each run that covers the key: about 2.5 blocks on average. These numbers are worked out from the code and were not run. E7 removes the filters and shows the difference.

The tombstone rule in the lab. A get must find the tombstone first. The lab keeps every key in the filter, tombstones included. The self-test turns that rule off and shows the deleted key coming back.

Where the formula comes from. Bloom's 1970 paper gives the FPR, in modern form, as its equations 16 and 17. It puts the half-full result this way: "the smallest hash area for which method 2 can be used occurs when half the bits are 1 and half are 0". Monkey, SIGMOD 2017, gives the 0.6185^(m/n) form as its Equation 2.

Evidence
Burton Bloom, "Space/Time Trade-offs in Hash Coding with Allowable Errors", Communications of the ACM, 1970, page 426. Dayan, Athanassoulis and Idreos, "Monkey", SIGMOD 2017.

The 10-bit arithmetic. m/n = 10, and the best k is 10 × 0.693 = 6.93, so 7 hashes. Then e^(−0.7) = 0.4966, so a bit is 1 with chance 0.5034, and FPR = 0.5034^7 = 0.0082, or 0.82%.

Bits per key | k | FPR, theory with the best whole k

5 | 3 | 9.18%

8 | 6 | 2.16%

10 | 7 | 0.82%

16 | 11 | 0.046%

Bits per key for a target FPR p: m/n = −ln(p) / (ln 2)² = 1.44 × log2(1/p). So 1% needs 9.6 bits per key, and 0.1% needs 14.4.

RocksDB's blocked filter, worked out. The header says: "A good choice is 9.9, which yields a filter with ~ 1% false positive rate". Theory gives 0.86% at 9.9 bits. The difference comes from the layout. RocksDB puts all probes of one key into one 512-bit block. That is one 64-byte CPU cache line, so a test reads one cache line. But blocks get uneven numbers of keys, and a block with more keys has a much higher FPR. For 10 bits per key and k = 6, the arithmetic goes like this:

- Each block gets n/s = 512 / 10 = 51.2 keys on average. The standard deviation is √51.2 = 7.16.

- The FPR at 51.2 − 7.16 keys is 0.43%. At 51.2 + 7.16 keys it is 1.48%.

- Their average is 0.95%. The same filter without blocks gives 0.84%, so the blocks cost a factor of 1.13.

So "10 bits per key is about 1%" is true for RocksDB's filter. And 0.82% is true for the textbook filter with the best k. bloom.py --blocked measures both side by side. RocksDB's filter needs 4.9 bits per key for 10%, 9.9 for 1% and 15.5 for 0.1%. The same header also describes the Ribbon filter, a different filter structure that RocksDB offers in place of Bloom. It saves about 30% of the space for the same FPR. Its query time is similar, but building it takes about 3 to 4 times the CPU.

Evidence
The header is filter_policy.h at tag v11.8.1, lines 140 to 149 and 169 to 173. The blocked arithmetic and the bits-per-key list are from the RocksDB wiki page "RocksDB Bloom Filter".

Where the filter bits should go. The worst-case lookup cost of an LSM tree "is proportional to the sum of the false positive rates of the Bloom filters across all levels". The deepest level holds most of the keys, so it holds most of the filter memory. Giving every level the same bits per key is therefore not the best use of memory. Monkey sets each level's FPR in proportion to its capacity. Lookup latency fell by "50% −80% for the data sizes we experimented with". The conditions were a worst case for lookups: LevelDB on a 7,200 RPM disk, with the block cache off, 1 GB of 1 KB entries, and lookups for keys that did not exist.

Evidence
Dayan, Athanassoulis and Idreos, "Monkey: Optimal Navigable Key-Value Store", SIGMOD 2017.

A second trap. Sizing RAM for the filters alone is also wrong, because each run's index blocks stay in memory by default as well.

A present key. A get for a present key in L1 reads 1 block. Now and then it adds a false positive in an L0 run above it.

## 2.6 Which three numbers describe any structure?

"Faster for writes" names one cost and hides the other two.

Each structure now has a price in reads, writes, space and memory. Three ratios describe what it does with every byte you give it.

- Read amplification: bytes read divided by the bytes a read returns.

- Write amplification: bytes written divided by the bytes a change changes.

- Space amplification: bytes stored divided by the bytes of the live keys and values.

The RUM conjecture, for read, update and memory, says these trade against each other. A structure that bounds two of them sets a lower bound on the third. Every structure in this lesson is one choice of that trade.

Predict: the order store must take 10,000 updates per second, each changing 100 bytes of a random 1,230-byte order. Which writes more bytes per second: PostgreSQL with HOT updates, or a SQL engine on a leveled LSM tree?
The LSM engine, about 2.5 times as many. A SQL update on an LSM writes a new version of the whole row, not of the 100 changed bytes, and compaction rewrites that row about 33 times. The next section works the numbers out.

The Phase 1 store writes a 1,230-byte entry for 1,210 bytes of order, so write amplification is 1.02. The disk holds 36.9 GB for 12.1 GB of live orders, so space amplification is 3.05. A leveled LSM writes about 32 times as many bytes per order, but brings space down to about 1.1.

1.02: Phase 1 log, write amplification

3.05: Phase 1 log, space amplification

about 33: leveled LSM, write amplification

1.1: leveled LSM, space amplification

The failure is one number alone. In E6, with 100-byte values, the Phase 1 log has the best write amplification, 1.18. On the write-heavy workload, it also stores 11.8 times its live data. That grows with every put, so a choice made on write amplification alone fills the disk.

### Where does each structure spend?

These are the numbers of this lesson, side by side.

Structure | Write amplification | Cold point read | Space amplification

Phase 1 log, no merge | 1.02 | 1 block, 0 if absent | 3.05 after 3 writes per key

Bitcask with merge | 1.02 plus merge rewrites | 1 block | about 1.05 right after a merge

B-tree | 3.1 to 165 per page, by changes per page, times pages per row | 1 miss with inner pages cached. PostgreSQL adds the heap page | over 1.5 with pages 1/2 to 2/3 full

leveled LSM | 33 in the RocksDB guide, 21.9 in the wiki's stats example | 1 block plus the filter FPRs | 1.11 to 1.14

tiered LSM | 1 per level | more runs to check | up to 3 by default before a full merge, plus temporary room for each merge's output

Memory differs too. The log keeps every key in RAM. The B-tree keeps 776 KiB of inner pages per 10 million keys. The LSM keeps 10 bits of filter per key, plus each run's index, about 0.5 MB per 256 MB run.

To estimate the numbers for one logical operation of your workload, take four steps.

- Write. List every write one logical change causes: the WAL record, the data write, and each later rewrite by compaction or a checkpoint. In PostgreSQL, count the heap page and a leaf per index. Add the bytes and divide by the bytes of the change.

- Read. Count the blocks a point read touches with a cold cache, then with the inner pages or filters cached. Do the same for one range read, and divide by the bytes returned.

- Space. Divide the bytes on disk in steady state by the bytes of the live keys and values.

- Memory. Write down what must stay in RAM for the read estimate to hold: a keydir, inner pages, or filters and run indexes.

A measurement on inserts. Measured numbers point the same way on inserts. In one insert-only test, with the data larger than memory, InnoDB wrote 10.11 to 14.65 KB per insert. MyRocks, MySQL on RocksDB, wrote 1.64 to 2.07 KB. That is 4.9 to 8.9 times fewer bytes, at about twice the insert rate.

Evidence
Mark Callaghan, "InnoDB, MyRocks and TokuDB on the insert benchmark", Small Datum, 2017-05-11. InnoDB from MySQL 5.7.17, insert-only load, data larger than memory, block cache 10 GB, on the server he calls "fast SSD". Its hardware is in an earlier post that this course did not fetch. His warning: "Be wary about drawing too many conclusions from an insert-only workload."

Write down your prediction for the four rows of E6, then run uv run python phase02_structures/amplification.py. Compare every column, and look for the row furthest from the table.

The next section multiplies these ratios by the order store's update rate to choose a structure.

Go deeper: the definitions, the Phase 1 numbers, more measurements, the lab's numbers
Why the ratios exist. With the three ratios, two structures can be compared on your workload before you move any data. Base data is the live keys and values. Auxiliary data is everything else: headers, indexes, filters, old versions and free space. The conjecture is not proved.

The Phase 1 store, worked out. The logical bytes of an order are its 10-byte key and 1,200-byte value, 1,210 bytes. The device writes a 1,230-byte entry, so the write amplification is 1,230 / 1,210 = 1.02. The disk bytes are 30,000,000 × 1,230 = 36.9 GB. The live bytes are 10,000,000 × 1,210 = 12.1 GB. So the ratio is 36.9 / 12.1 = 3.05. With the tuning guide's 33, a leveled LSM tree writes about 33 / 1.02 = 32 times as many bytes per order. It makes space better, about 1.1, and needs far less memory.

The three definitions, quoted.

- Read overhead is "the ratio between the total amount of data read including auxiliary and base data, divided by the amount of retrieved data".

- Update overhead is "the ratio between the size of the physical updates performed for one logical update, divided by the size of the logical update".

- Memory overhead is "the ratio between the space utilized for auxiliary and base data, divided by the space utilized for base data".

This course calls them read, write and space amplification. The conjecture, in its own words: "An access method that can set an upper bound for two out of the read, update, and memory overheads, also sets a lower bound for the third overhead."

Evidence
Athanassoulis and others, "Designing Access Methods: The RUM Conjecture", EDBT 2016, section 2 for the definitions and section 3 for the conjecture. Hunter's study note could not extract the PDF, so the quotes rest on the phase's own reading.

The insert test in full.

Engine | KB written per insert | GB on disk | Inserts per second

InnoDB, redo 4 GB | 14.65 | 402 | 61,711

InnoDB, redo 32 GB | 10.11 | 402 | 63,959

MyRocks, no zstd | 2.07 | 226 | 126,727

MyRocks, zstd | 1.64 | 101 | 128,816

InnoDB's doublewrite buffer. Part of InnoDB's bytes is its doublewrite buffer, its answer to torn pages from Phase 1. Pages flushed from the buffer pool go there "before writing the pages to their proper positions". It "is enabled by default in most cases". MySQL 8.4 also changed two of its defaults: innodb_doublewrite_files is now 2, and innodb_doublewrite_pages is now 128. So InnoDB writes each flushed page twice. But this "does not require twice as much I/O overhead or twice as many I/O operations", because the copies go out "in a large sequential chunk". Whether it was on in the insert test's runs is not checked.

Evidence
MySQL 8.4 manual, "Doublewrite Buffer", and its page on changes since 8.0 for the two defaults.

Two more sources, under their own conditions.

- Facebook production databases. "the amount of data written to storage by RocksDB is between 10% and 15% of what InnoDB writes out". The space RocksDB used was about 50% lower than compressed InnoDB. In LinkBench, the social-graph benchmark of the Bloom filter section, with 1 billion vertices and 50 GB of DRAM, RocksDB was "3%-16% better than InnoDB" in throughput. It wrote less than 20% of InnoDB's bytes per transaction. The hardware was a 24-core Xeon E5-2678v3 with 256 GB of RAM and about 5 TB of NVMe SSD. The authors work at Facebook, and the workload is Facebook's.

- A day of LinkBench on flash. Facebook built MyRocks, so this is a vendor source. The MyRocks instance "was 3.5 times smaller than InnoDB uncompressed, and two times smaller than InnoDB compressed". On spinning disks, "MyRocks was more than six times faster than InnoDB". The post shows write volume only in a chart image, so this course does not quote a number for it. It also gives one cause of InnoDB's space: "A 16 KB in-memory page compressed to 5 KB still uses 8 KB on storage". That is space amplification from a fixed compressed page size.

Evidence
Dong and others, "Optimizing Space Amplification in RocksDB", CIDR 2017. Yoshinori Matsunobu, "MyRocks: A space- and write-optimized MySQL database", Facebook engineering blog, 2016, LinkBench for more than 24 hours on PCI-Express flash.

The lab's expected numbers. E6 runs two layouts and two workloads on 20,000 keys with 100-byte values, and lists the expected values. Both layouts read about 4,096 bytes to return 100. So their read amplification in bytes is about 41 for the LSM and 42 for the log. The difference between them is in writes and space, not in reads. These values are worked out from the code and its seed, and were not run.

## 2.7 Which structure fits your workload, in device seconds?

The ratios decide nothing until you multiply them by your workload's rate. A device has one second of work per second. A structure that needs more will stall.

Take 10,000 updates per second, each changing 100 bytes of a random 1,230-byte order. The index is ten times larger than RAM. Compare PostgreSQL with MyRocks, MySQL on RocksDB.

- PostgreSQL reads. Each update finds its row, and the leaf and heap page both miss. That is 10,000 × 2 × 89 µs = 1.78 s per second.

- PostgreSQL writes. With c near 1, a HOT update writes up to 16,534 bytes, 165 MB per second. A non-HOT update can change two heap pages and the primary-key leaf, about 496 MB per second.

- MyRocks reads. A SQL update is not a blind put. MyRocks reads the old row by primary key first, to check unique keys. That is 10,000 × 89 µs = 0.89 s per second.

- MyRocks writes. It writes a new version of the whole row, 12.3 MB per second. Compaction multiplies that by about 33. That is about 406 MB per second, in long sequential runs.

Bytes written per second for this workload. Estimates from this lesson's models, not measured.

So for small updates the LSM writes 2.5 times the bytes of HOT updates, though its writes are sequential. A B-tree page costs about 16.5 kB per change, and an LSM about 33 times the row. The LSM writes less only when 33 times the row is under 16.5 kB per dirtied page.

Wrong: multiply 33 by the 100 changed bytes. The LSM then writes 33 MB per second, five times fewer bytes than HOT updates.

Right: multiply 33 by the whole 1,230-byte row, because an LSM update writes a new version of the row. The LSM writes about 406 MB per second.

Neither design removes the reads, which take a device second or more each second. More memory or a more parallel device comes first. With keys that always grow, c is large and any write advantage of the LSM mostly goes away. So a migration comes after these PostgreSQL levers.

- Is the key random?
- yes: use a sequence or an identity column. uuidv7() exists only from PostgreSQL 18

- Do updates miss HOT?
- yes: fewer indexes, table fillfactor below 100

- Do pages collect few changes?
- yes: raise max_wal_size and checkpoint_timeout

- Are page images most of the WAL?
- yes: turn on wal_compression

Measure each lever with wal_fpi and wal_bytes in pg_stat_wal. The opening's team tried none. Its short write benchmark hid the range reads, the tripled disk and the nightly compaction.

### What changes on a cloud volume?

The device model above is one laptop SSD that serves one read at a time. Move the PostgreSQL side to an EBS gp3 volume, whose numbers the cache-miss section gave:

- It makes 20,000 random reads a second, the leaf and the heap page for each of 10,000 updates.

- That is about 6.7 times the 3,000 IOPS baseline of gp3. So you must buy at least 20,000 IOPS.

- On plain EBS, gp3 allows 500 IOPS per GiB, so that needs a volume of at least 40 GiB. On RDS for PostgreSQL, 20,000 IOPS needs a gp3 volume of at least 400 GiB.

- The reads move 20,000 × 8 KiB = 156 MiB per second. That is more than the gp3 baseline of 125 MiB per second, so you must also buy throughput. The writes of the model above need more.

- At about 1 ms each, 20,000 reads are 20 seconds of waiting per second. So about 20 reads must be in flight at once.

The MyRocks side makes half as many reads. On Aurora Standard, each PostgreSQL read that misses the pool is a billed storage I/O, counted in VolumeReadIOPs, so the read load is also a line on the bill. The IOPS arithmetic is this course's, from the EBS numbers. amplification.py --layouts lsm --latency --read-us 1000 reruns the lab's latency model at a 1 ms miss, as the cache-miss section shows.

### What about a report over every row?

Every structure in this lesson is a row store: it keeps all the columns of a row together. In the other layout, the decomposition storage model, "the DBMS stores a single attribute (column) for all tuples contiguously in a block of data. Thus, it is also known as a column store." Its gain is that it "Reduces the amount of I/O wasted per query", and its cost is that it is "Slow for point queries, inserts, updates, and deletes". Here is the number for the running case, where a report sums one 8-byte amount over 10 million orders:

- The heap holds about 6 orders per page. So the scan reads 10,000,000 / 6 = 1,666,667 pages, about 13.7 GB.

- A column store reads 10,000,000 × 8 bytes = 80 MB of that column, before compression.

- That is about 170 times fewer bytes.

The arithmetic is this course's, and it leaves out compression and the column store's own metadata. So a report of this shape belongs in a column store, or in a summary table, not in a larger buffer pool. OLTP, online transaction processing, is the short reads and writes of the application, and the table below keeps analytics outside the OLTP database.

Evidence
The quotes are from the CMU 15-445/645 Fall 2025 notes for lecture #06, "Storage Models & Compression", section 2, read with pypdf.

### Which structure does each trait favor?

Each row starts from one trait of the workload. It names the structure the trait favors and the number to estimate. The last column is the measurement that would show the choice is wrong.

Workload trait | Favors | Estimate | Measurement that would prove it wrong

random-key writes of rows much smaller than a page, data much larger than RAM | leveled LSM, if the B-tree levers above are not enough | write load: about 33 × row bytes for the LSM, against 16.5 kB for the heap page and every index leaf at c near 1. On a SQL engine, both read before they write | device bytes written per second on a copy of production, iostat

write cost on PostgreSQL, before any migration | B-tree, with the levers above | full page images per row change | wal_fpi and wal_bytes per insert after each change

point reads, hot set fits in RAM | B-tree | miss rate, from the cache-miss arithmetic | buffer pool hit rate under the real mix, with iostat beside it

range scans over sorted keys | B-tree, or leveled LSM | runs or pages per range | blocks read per range scan

keys that always grow | either | c for the B-tree | page writes per insert

deletes of old keys in key order: a queue, an outbox, event retention | B-tree with a partition drop, which Phase 4 explains, or an LSM with DeleteRange and delete-triggered compaction | tombstones or dead index entries each range scan must skip | latency of the first read at the oldest live key

many gets for keys that do not exist | LSM with filters, or a keydir | sum of filter FPRs | filter "maybe" rate against true hits

tight disk budget | leveled LSM | space amp 1.1 against B-tree's over 1.5 | bytes on disk over live bytes after a week

all keys fit in RAM, large values, no ranges | Bitcask log with merge | keydir bytes per key | resident memory per million keys

strict p99 during heavy writes | B-tree, or LSM with paced compaction and spare device time | compaction share of device time | p99 while a compaction runs

similarity search over embeddings, the last section | HNSW in PostgreSQL while the index fits in the pool, or a smaller quantized index with re-ranking | index pages against shared_buffers, and the build's memory against maintenance_work_mem | buffers read per query in EXPLAIN (ANALYZE, BUFFERS), and pg_relation_size of the index

analytics: sums and counts over a few columns of many rows | a column store, outside the OLTP database | bytes read per report: rows × row width in a row store, against rows × column width | bytes read per report, from EXPLAIN (ANALYZE, BUFFERS)

The queue row is inferred from the RocksDB sources of the compaction section and Brandur's queue measurement, not measured here. The embeddings row is inferred from the last section. Two rules apply to every row. Estimate the loads before you trust any row. And measure on a copy of your own data, with your read mix and your key order. Run long enough for compaction or checkpoints to reach a steady state.

Run uv run python phase02_structures/amplification.py --workloads read-heavy. Before you run it, predict which column changes most from the write-heavy rows of E6, and why.

Multiply each ratio by your rate, and pick the structure that fits the device budget.

Multiplying the LSM's 33 by the changed bytes, not the whole row, hides its real write cost.

Every row of the table depends on the read load, and the next section shows how one scan can raise it for everyone.

Go deeper: the full worked answer, levers with defaults, where "ten times" comes from
The four estimates. For each structure, estimate four numbers from the workload.

- Write load. User bytes per second times write amplification gives device bytes written per second.

- Read load. Gets per second, times the blocks per get that miss the cache, times the cost of one miss.

- Space. Live bytes times space amplification, at the peak, gives the disk you need.

- Memory. What must stay cached for the read estimate to hold.

Then compare each load with what the device can do. A structure that needs less than the budget wins by the ratio of the two loads.

The device budget. A device has a budget of one second of work per second. Each structure spends that budget on the reads its gets cause, the writes its changes cause, and its background work. The index is ten times larger than RAM, so a random leaf is almost never cached. Half of PostgreSQL's bytes are random page writes. Neither design fits one device queue on reads alone.

The worked answer in full. The user writes 10,000 × 100 bytes = 1 MB per second. Here is each side, step by step.

PostgreSQL.

- The read. Each update first finds its row. The leaf misses. So does the heap page that the TID names, because the heap is larger still. At the M2 SSD cost: 10,000 × 2 × 89 µs = 1.78 seconds of device time each second.

- A HOT update. Each page collects about one change before it is written, so c is near 1. Only the heap page changes, and the B-tree model gives up to 16,534 bytes per update, 165 MB per second.

- An update that is not HOT. It can change the old heap page, a new heap page and the primary-key leaf. That is up to 3 × 16,534 = 49,602 bytes, about 496 MB per second.

- What kind of bytes. Half of those bytes are full page images, appended to the WAL. The other half are random 8 kB page writes.

MyRocks, a leveled LSM. A raw RocksDB Put is a blind write, because the new version hides the old one. A SQL row update is not blind.

- The read. The MyRocks wiki page "Read Free Replication" says INSERT, UPDATE and DELETE "all need GetForUpdate() to read by primary keys". "On cache miss, GetForUpdate() reads RocksDB data block from storage, and decompresses it". The engine needs the old row to check unique keys. It likely also needs it to remove old secondary index entries. That second reason is inferred from the page's examples. So each update reads one data block, which misses: 10,000 × 89 µs = 0.89 seconds per second.

- The write. The new version holds the whole 1,230-byte row, not only the 100 bytes that changed. This is inferred from the same page, which says the binary log's row images hold all that is needed to compose the RocksDB write calls. With the 1,230-byte entry, that is 10,000 × 1,230 bytes = 12.3 MB per second.

- Compaction. The tuning guide's 33 turns 12.3 MB into about 406 MB per second of writes, before compression, in large sequential runs. Compaction also reads about as many bytes.

The page's read-free mode works only on replicas. It gives up "almost all real time consistency checks", and "Primary still checks uniqueness".

Evidence
MyRocks wiki page "Read Free Replication", which has no release tag. The phase read it on 2026-10-18, and hunter's study note quotes the same page.

What the estimate shows, in numbers. 406 / 165 = 2.5 times the bytes of HOT updates. It is a little less than the non-HOT worst case, 406 against 496 MB. A 100-byte row costs 3.3 kB against 16.5 kB for each page. Both designs need about one device second or more per second for reads alone, so neither fits one device queue. InnoDB, the third design, reads one clustered leaf per update, because the leaf holds the row. That is 0.89 seconds per second, like the LSM. That last figure is inferred from the B-tree section's layout.

A longer recovery. Checkpoints further apart raise c, but recovery then replays more WAL, as Phase 1 showed. Measure each lever as E13 does.

Growing keys, in more words. Now change one fact: the keys always grow, as a timestamp does. The B-tree then writes to its rightmost leaf, which collects many changes. So c is large. The write amplification falls toward the 3.1 of c = 100, or lower. So with growing keys, neither structure writes much, and only the reads and the space then decide.

The benchmark that did not match. The opening moved the event store for faster writes. A write-only benchmark that ends before compaction reaches its steady state confirms that claim. It does not show the range reads that now check many runs. It does not show the old versions that triple the disk under universal compaction. It does not show the extra room each large merge needs, or the compaction at night. This lesson estimates a number for each of those: read amplification for ranges, space amplification at the peak, and the compaction share of device time.

Try the break-even. Redo the write estimate for 200-byte and 1,000-byte rows, with HOT updates. By this lesson's arithmetic, the LSM writes fewer bytes below about 500 bytes a row, because 33 × 500 is 16.5 kB.

Why the insert test does not settle this. In the insert test of the amplification section, InnoDB wrote 4.9 to 8.9 times the bytes of MyRocks. That post does not give the row size, so this course cannot compare those bytes with this model. A reply by the author under the post says "Inserts are in PK order, but random for secondary indexes". So the B-tree's extra bytes there come from secondary index leaves at c near 1. That link is inferred. The whole estimate above is inferred from the models of the earlier sections, and was not measured.

A correction. A first draft of this answer multiplied 33 by the 100 changed bytes, not by the row. So it gave the LSM five times fewer bytes. That was wrong, because an LSM writes a new version of the whole row.

Growing keys in an LSM. The RocksDB wiki page "Compaction" notes that leveled compaction is cheaper for keys inserted in order, and RocksDB has an optimization for that case. So with growing keys, any write advantage of the LSM mostly goes away.

The levers, with their defaults. A move to an LSM is the last lever, not the first. These PostgreSQL levers lower the write cost of the B-tree section without a migration:

Lever | Default | What it lowers

a key that grows with time: a sequence or an identity column. uuidv7() exists only from PostgreSQL 18 | gen_random_uuid() gives random version 4 UUIDs, and so do the Django and Rails examples of the B-tree section | full page images per insert, as the random-key test of the B-tree section measured

fewer indexes, and room for HOT with a table fillfactor below 100 | fillfactor 100, per the CREATE TABLE docs | index leaves written per update. Phase 4 explains the setting

checkpoints further apart: max_wal_size and checkpoint_timeout | 1GB and 5min, lines 262 and 258 | raises c. Recovery then replays more, as Phase 1 showed

wal_compression | off, line 243. It accepts pglz, lz4 or zstd, and on means pglz. In 14 it was only on or off | page image bytes: 8.6 times smaller in Rogov's test, which Phase 1 used

Evidence
Each default is verified from the PostgreSQL 17 docs or from postgresql.conf.sample at REL_17_11.

Where "ten times" comes from. This phase asked why one workload can run ten times faster on one structure. The sources show several such factors, each with a different cause:

Factor | Cause | Source

nearly two orders of magnitude | sequential against random page writes, on old disks with moving arms | the original LSM design

about 20 times, WAL bytes | a random UUID primary key against a sequence: full page images | Vondra

53 times, per change | how many changes a page collects between writes | the B-tree write model

4.9 to 8.9 times, bytes written | B-tree against LSM on random inserts | Callaghan

10 times, read throughput | the engine's implementation, not its structure: both engines are LSM trees | Instagram, below

So a factor of ten usually means one structure's unit of work matches the workload's access pattern, and the other's does not. The random-key row shows that the same structure can differ by twenty times through its key alone. A factor of ten can also mean the cause was somewhere else.

When the structure was not the cause. Instagram ran Cassandra, an LSM database on the Java virtual machine. Its fix replaced Cassandra's storage engine with RocksDB, which is also an LSM tree. Instagram calls the result Rocksandra. The "10x" of the post's title is a drop in garbage collection stalls. Their share of the time fell "from 2.5% to 0.3%", which by the arithmetic is 8.3 times. The production p99 read latency "dropped from 60ms to 20ms", which is 3 times. So the tail came from Java memory management, not from the LSM shape. A read-only test on three AWS i3.8xlarge instances gave Rocksandra "10X higher read throughput" at a similar p99 of 2 ms. That was 300,000 reads per second against 30,000 for Cassandra 3.0.

Discord's move, whose compaction problem the compaction section quoted, also went from one LSM database to another, Cassandra to ScyllaDB. It reports a p99 for reading old messages of "between 40-125ms on Cassandra", against 15 ms on ScyllaDB. The same project added a service in front of the database that merges identical requests. So that change had more than one cause, which is inferred from the post's own description.

Evidence
The ten-times factors come from five sources. The first is O'Neil and others, section 3.2, with 1995 disks. The second is Tomas Vondra, 2016. The third is this lesson's B-tree arithmetic. The fourth is Mark Callaghan, 2017. The fifth is Dikang Gu, "Open-sourcing a 10x reduction in Apache Cassandra tail latency", Instagram, 2018, read from an archived copy. Discord's numbers are from Bo Ingram's 2023 post.

## 2.8 Why can one scan empty the cache?

The eviction policy decides the miss rate, and a scan tests it hardest.

On a miss, the eviction policy picks the page that leaves. LRU, least recently used, evicts the page whose last access is oldest. Every scan page is newer than every hot page. So after a scan as large as the pool, only scan pages are left. This is sequential flooding.

Predict: an LRU pool holds 1,000 pages, and 800 hot pages are in constant use. One report reads a 2,000-page table once, while no other query runs. How many hot pages are left when the scan ends?
None. After 1,000 scan pages, every hot page has gone. The next 800 hot reads all miss: 800 × 89 µs = 71 ms of reads.

Each fix adds a second rule that protects pages used often.

Policy | The second rule | What still goes wrong

LFU | evict the page with the fewest accesses | a page hot an hour ago stays

2Q and ARC | a page counts as hot only when it is used a second time. In 2Q, that use must come after the page left a first queue | 2Q needs two sizes set by hand

PostgreSQL | a clock with usage counts up to 5, and a small ring for large sequential scans | index and bitmap heap scans get no ring

InnoDB | a new page enters the old 3/8 of the list, and moves up only if used again after 1,000 ms | a window of 0 promotes every scan page

MySQL bug 45015, filed by Harrison Fisk in May 2009, reported this failure in InnoDB. It says that large full table scans can push many useful pages out of the buffer pool. He named mysqldump, the backup tool, as very bad at this, because it runs many full table scans. His steps to repeat it run mysqldump on a large, busy database. They expect the hit rate to fall a great deal and disk I/O to rise. The report gives no measured numbers for the hit rate or the I/O. The changelog note on the bug explains why scan pages pushed out the hot ones. A scan reads several rows from each page, so it uses each page again at once. That second use moved every scan page to the head of the list. The InnoDB Plugin in MySQL 5.1.41 added innodb_old_blocks_time in late 2009. MySQL 5.6 later raised its default from 0 to 1,000 ms.

Evidence
The report and its 5.1.41 changelog note are verified from the bug page, filed on 2009-05-21, https://bugs.mysql.com/bug.php?id=45015. The two defaults are verified from a table in Peter Zaitsev's Percona post of 2013-02-21 that compares 5.5.30 with 5.6.10, https://www.percona.com/blog/2013/02/21/mysql-5-5-and-mysql-5-6-default-variable-values-differences/.

In PostgreSQL, a sequential scan of a table over a quarter of shared_buffers reuses a small ring of buffers, 256 kB on every version up to 17. Its pages get a usage count of at most 1, so they leave before pages used often.

The failure is the scan the protection leaves out. A bitmap heap scan collects matching rows from an index, then reads their table pages in physical order. Neither it nor an Index Scan asks for a ring. A nightly report with a date filter often runs as one, so it can flood the pool. That is inferred from which scans get a ring.

### Which operations get a ring?

The ring protects the pool only from operations that ask for one. Rogov gives the whole picture for PostgreSQL 14, and the ring sizes and the cap of 1/8 of the pool are the same in the 17 source:

Uses a ring | Uses the normal pool

Seq Scan of a table larger than shared_buffers / 4: the bulk read ring, 256 kB | Index Scan, Rogov p. 158

a second Seq Scan of the same table. A synchronized scan starts where the first scan is, so it finds those pages in the first scan's ring buffers. It still has its own 256 kB ring, heapam.c lines 453 to 458 | Bitmap Heap Scan, tableam.h at REL_14_24 and REL_17_11

COPY FROM, CREATE TABLE AS SELECT and other table rewrites: the bulk write ring, 16 MB, at most 1/8 of the pool | UPDATE or DELETE of many rows. The scan uses a ring, but changed pages leave it, so rings "virtually become useless"

VACUUM: 256 kB in 14 and 15. 256 kB by default in 16, set by the new vacuum_buffer_usage_limit. 2 MB since 17 | TOAST values, which "are always accessed via an index, so they bypass buffer rings"

So read the report's plan first, in EXPLAIN (ANALYZE, BUFFERS). The plan says which pool a report uses:

- What does the report's plan show in EXPLAIN (ANALYZE, BUFFERS)?

- Seq Scan of a table larger than a quarter of the pool: a ring holds the scan to a few buffers

- Index Scan: the normal pool

- Bitmap Heap Scan: the normal pool

On version 16 and later, pg_stat_io rows with the context bulkread count ring reads. Their reuses column counts buffers reused inside a ring. Reads of the report's table under context normal mean that it did not use a ring.

### What do you see after a flood?

pg_buffercache_usage_counts(), from the cache-miss section, shows the other side. Run it before and after the report. A report that flooded the pool leaves many buffers of its own table, at low usage counts, where the hot tables were. The per-relation query of the cache-miss section names that table. That reading is inferred from the clock rules below.

- Log the real plan. To log the report's plan each night, load auto_explain and set auto_explain.log_min_duration, log_analyze and log_buffers. The module does nothing by default. log_min_duration is -1 by default, which disables logging, and log_analyze and log_buffers are off by default. Phase 4 teaches auto_explain.

- On RDS. shared_preload_libraries is a static parameter, so loading auto_explain needs a custom parameter group and a reboot.

- On Aurora. The morning's misses go to the storage service. On Aurora Standard they count as billed reads, as the cache-miss section showed.

Evidence
The pg_stat_io contexts and reuses are verified from the PostgreSQL 17 docs, section 27.2.13. The auto_explain defaults are from the PostgreSQL 17 docs, F.3. The static parameter rule is from the AWS page "Parameter groups for Amazon RDS", read on 2026-10-20. The 16 default of vacuum_buffer_usage_limit is at postgresql.conf.sample line 161 of REL_16_10. The 2 MB is at line 160 of REL_17_11.

E14 runs both checks, the ring and the flood, on your own server.

First predict which keeps a larger share of its no-scan hit rate. Then run uv run python phase02_structures/cache_sim.py --policies lru,2q and read the kept column.

A scan larger than an LRU pool removes every hot page, so engines add a second rule.

Trusting the ring with a report that runs as a Bitmap Heap Scan, or setting the InnoDB window to 0.

The last section uses the tools of this lesson on a new kind of table, one that holds embeddings.

Go deeper: LFU, 2Q, ARC, the clock in code, the ring by version, InnoDB's midpoint
Evidence
Andy Pavlo's CMU lecture on buffer pools discusses sequential flooding at about 47:40.

The clock, in brief. PostgreSQL's clock hand lowers each buffer's usage count as it passes and takes the first unpinned buffer at 0, so a page used often survives five passes. An Index Scan or a Bitmap Heap Scan through the normal pool can push out the hot set, and the morning's reads miss until the hot pages return.

Why LRU fails, in more words. LRU works when recent use predicts the next use. A scan breaks the prediction, because it touches each page once. None of the scan pages will be read again soon. In the last section, the read load entered every decision, and here the policy decides how large that load is.

The policies side by side, in full.

Policy | The second rule | What still goes wrong

LFU, least frequently used | evict the page with the fewest accesses, so a scan page leaves first | a page hot an hour ago keeps its high count and stays

2Q | a page enters the main LRU queue only on a second request, after it left a small first queue | needs two sizes set by hand, Kin and Kout

ARC, the adaptive replacement cache | keeps pages seen once and pages seen twice in two lists, and moves the split between them by itself | more bookkeeping per access

PostgreSQL clock sweep | each buffer has a usage count up to 5, and the clock hand takes only a buffer at 0 | alone, it does not stop a large scan

PostgreSQL ring | a large sequential scan reuses a small fixed set of buffers | index scans and bitmap heap scans get no ring

InnoDB midpoint | a new page enters the old 3/8 of the LRU list, and moves up only if used again after a time window | a window of 0 promotes every scan page

PostgreSQL in four steps.

- Each access to a buffer raises its usage count by one, up to 5.

- A clock hand moves around the buffers and lowers each count it passes by one.

- It takes the first buffer whose count is 0 and that nobody has pinned. So a page used often needs five passes of the hand before it can go, and a page used once needs two.

- A ring, a small fixed set of buffers, serves each sequential scan of a table over a quarter of shared_buffers. A page read through the ring gets a usage count of at most 1. The scan reuses a ring buffer only while its count is still 0 or 1, because a higher count means another query used the page.

InnoDB in brief. Its LRU list has an old part, 3/8 of the pool, and a young part. A new page enters at the midpoint, the head of the old part. It moves to the young part only if it is accessed again after innodb_old_blocks_time, 1,000 ms by default. With the window at 0, a scan that reads several rows per page touches each page twice in a row, so every scan page is promoted. The scan then pushes the hot pages out, as LRU would.

LFU. LFU evicts the page with the fewest accesses. A scan page has one access, so it leaves first, and the hot pages stay. The cost is the opposite failure. A page that was hot an hour ago keeps its high count after it stops being used, so it stays in the pool. That follows from the definition, and the lab does not measure it.

2Q. 2Q keeps three queues:

- A1in is a first-in, first-out queue of pages seen once. Its target size Kin is 25% of the frames.

- A1out holds only page numbers, not pages, for pages that recently left A1in. Its size Kout is the page numbers of 50% of the frames. A list of numbers like this is often called a ghost list.

- Am is an LRU queue for pages that were seen again after they left A1in.

In the original words: "Kin should be 25% of the page slots and Kout should hold identifiers for as many pages as would fit on 50% of the buffer."

A page enters Am only when it is requested again while its number is still in A1out. So it must be used twice, with time between the two uses. A scan page is used once, goes through A1in and A1out, and never reaches Am. A second access while a page is still in A1in does not count. It is often part of the same short burst, such as several rows read from one page. cache_sim.py:181 follows the original pseudocode, and E10 runs it.

2Q was measured against LRU on traces, by hit rate. 2Q helped most when the pool was small compared with the data. One test mixed one third scan references into Zipf references, where a few pages get most of the accesses. The result: "The hit rate of 2Q is about 70% of its no-scan hit rate, while the hit rate of LRU is about 60% of its no-scan hit rate".

Evidence
Johnson and Shasha, "2Q", VLDB 1994, Tables 1 to 4 and page 443. The PDF is a scanned image, and the phase's research read the tables from the page images. Hunter's study note could not extract the PDF, so these numbers are as the phase reports them.

ARC. ARC keeps two lists of pages, T1 for pages seen once recently and T2 for pages seen at least twice. It also keeps two ghost lists, B1 and B2, for pages that recently left T1 and T2. A target size p decides how much of the pool belongs to T1. A request that hits B1 means T1 was too small, so p grows. A hit in B2 means T2 was too small, so p shrinks. So ARC tunes the split between recency and frequency by itself, while 2Q needs Kin and Kout. The lab implements the algorithm case by case. On SPC1, a trace with long sequential scans, and a cache of 1,048,576 pages, the hit ratios were 9.19% for LRU and 20.00% for ARC. All of those traces are reads only, filtered by caches above them, and counted from a cold start.

Evidence
Megiddo and Modha, "ARC", USENIX FAST 2003, Figure 4 for the algorithm and Table VI for SPC1. Hunter's study note could not extract the PDF, so the numbers are as the phase reports them.

The clock sweep in code. Copied from freelist.c, with the locking and statistics lines cut. The same lines are identical at REL_18_6:

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

The cap is BM_MAX_USAGE_COUNT, 5 at buf_internals.h line 79, REL_17_11. A page used often keeps a count near 5, so the hand must pass it five times before it can be taken. A page used once has a count of 1. The next pass lowers it to 0, and the pass after that takes it. The comment above the cap explains why it is only 5: "A large value (comparable to NBuffers) would approximate LRU semantics". But a large cap could make the hand go round many times before it finds a buffer.

The ring in the source. The ring threshold of a quarter of shared_buffers is at heapam.c lines 445 to 452, REL_17_11. The source says: "Ring buffers shouldn't evict others from pool. Thus we don't make usagecount more than 1". The rule that the scan takes back a ring buffer only at count 0 or 1 is at freelist.c line 727, REL_17_11. If a ring buffer has a higher count, the scan leaves it and takes a new buffer from the clock.

The ring's size by version.

Version | Ring for a large Seq Scan | Evidence

14 | 256 kB, 32 pages | Rogov, page 156

15 to 17 | 256 kB, 32 buffers of 8 kB | GetAccessStrategy in freelist.c, lines 541 to 573 at REL_17_11. The same 256 in REL_15_14 and REL_16_10

18 | about 752 kB with default settings | arithmetic below, inferred, not measured

On 17 the same function gives the bulk write ring 16 MB and the VACUUM ring 2,048 kB. The README at REL_17_11, line 218, says "For sequential scans, a 256KB ring is used".

The 18 code is at freelist.c lines 557 to 601, REL_18_6. It starts at 256 kB. It adds room for its asynchronous reads: 8 kB × 16 × 16 = 2,048 kB. The two 16s are the 18 defaults of io_combine_limit, 128kB or 16 pages, and effective_io_concurrency. On 17, io_combine_limit is also 128kB, but effective_io_concurrency is 1, at postgresql.conf.sample lines 211 and 209. So the 18 code wants 2,304 kB. It caps the ring at the number of buffers one process may pin. With 128 MB of shared_buffers, that cap is 16,384 buffers / 174 processes = 94 buffers, or 752 kB. The 174 is 136 backends plus 38 auxiliary processes, from the default settings. The README in the 18 tree still says 256 kB. E12 shows the ring's effect on your own server.

Which operations use a ring, in the source. In tableam.h at REL_17_11, lines 959 to 967, table_beginscan_bm sets SO_TYPE_BITMAPSCAN | SO_ALLOW_PAGEMODE, and SO_NEED_TUPLES when the scan needs the tuples. It sets no SO_ALLOW_STRAT flag, and REL_14_24 sets the same flags. heapam.c gives a scan the ring only when that flag is set. Rogov showed the index scan case on PostgreSQL 14, page 158. After a Seq Scan of his table, the cache held 32 of its buffers. After an Index Scan of the same table, "the buffer cache ends up containing the whole table and the whole index". Rogov's PDF prints digits as special glyphs, which this course's research decoded by context. The ring sizes and the cap of 1/8 of the pool in the table above are in the 17 source at freelist.c lines 541 to 599.

InnoDB's midpoint, in the manual's words. MySQL 8.4's InnoDB keeps one LRU list in two parts: "3/8 of the buffer pool is devoted to the old sublist". And: "When InnoDB reads a page into the buffer pool, it initially inserts it at the midpoint (the head of the old sublist)". A page moves to the young part only when it is accessed again. During the innodb_old_blocks_time window after the first access, a page "can be accessed without being moved to the front". The default is 1000. innodb_old_blocks_pct defaults to 37, which is 100 × 3 / 8 rounded down. Both defaults are verified in ha_innodb.cc at tag mysql-8.4.11, lines 23017 to 23027.

This design is close to 2Q, but it is not the same. The old part plays the role of A1in, and the young part plays the role of Am. The time window plays the role of 2Q's rule that a second access inside A1in does not count. InnoDB has no ghost list like A1out. So a page that leaves the old part is forgotten, and its next access starts from the old part again. This comparison is inferred from the two designs. The InnoDB manual does not cite 2Q.

The window of zero, traced. The lab's self-test traces the failure by hand in a pool of 10 frames. With a window of 5 references, three hot pages survive a 15-page scan. With a window of 0, all three are evicted. The self-test asserts both traces, and it passes, as E1 records. E11 runs the same case at full size.

## 2.9 What does a table of embeddings cost the database?

The decision table has a row for similarity search, and this section works that row out for the agent team's table with the tools of the sections above. The table holds 1 million embeddings of 1,536 dimensions, one per row, with a bigint id. The section gives four numbers for it: the bytes of one value, where the value is stored, the size of an HNSW index, and the WAL its build writes.

pgvector is a PostgreSQL extension. It adds the types vector, halfvec and sparsevec, and two index types. Its indexes also accept PostgreSQL's built-in bit type. HNSW is a graph index, where each vector links to its nearest neighbours and a search walks the links. IVFFlat splits the vectors into lists around centres, and a search reads the closest lists. Two facts decide the storage cost. A row over 2,032 bytes moves its large value to TOAST, PostgreSQL's separate table for out-of-line values. And each index stores its own copy of every vector, so the vector bytes are paid at least twice.

Where the bytes of one vector(1536) row go

Sizes from vector_storage.py, inferred from the source and not measured on a server. For 1 million rows: about 8.2 GB of TOAST and at least 7.6 GiB of index.

### Does the value stay in the row?

The pgvector README gives the size of each type, and the largest value an index takes:

Type | Bytes per value | At 1,536 dimensions | Largest value an index takes

vector, 4-byte floats | 4 × dimensions + 8 | 6,152 | 2,000 dimensions

halfvec, 2-byte floats | 2 × dimensions + 8 | 3,080 | 4,000 dimensions

bit | dimensions / 8 + 8 | 200 | 64,000 dimensions

pgvector declares vector and halfvec with STORAGE = external, which means out of line without compression. A row of a bigint and a vector(1536) is 24 + 8 + 6,152 = 6,184 bytes. That is over the threshold, so the value moves to the TOAST table in 4 chunks, and the heap row keeps an 18-byte pointer. The 4 chunk rows take 6,312 bytes of an 8,168-byte page. The 1,856 bytes left are too few for the next value's first chunk, so each value fills one TOAST page. A million rows then need about 1,000,000 TOAST pages, about 8.2 GB. The largest vector that stays inline next to a bigint has 498 dimensions. These numbers come from vector_storage.py, and they are inferred from the source, not measured.

Evidence
The sizes are from the pgvector README at v0.8.7, lines 960, 998 and 1036, and the index limits from lines 252 to 254. STORAGE = external is at sql/vector.sql lines 39 and 483. "External" is defined in the PostgreSQL 17 docs, section 65.2. heapam.c tests the threshold at line 2359, REL_17_11.

Two things follow from TOAST:

- Reads. Reading an embedding means a lookup in the TOAST table's index, then reads of its chunk pages. TOAST reads bypass buffer rings, as the eviction section showed. So a scan over the embeddings fills the normal pool. That is inferred.

- Plans. The README says: "The planner doesn't consider out-of-line storage in cost estimates, which can make a serial scan look cheaper." It gives two fixes. The first lowers min_parallel_table_scan_size and parallel_setup_cost for one transaction, with SET LOCAL. The second is ALTER TABLE items ALTER COLUMN embedding SET STORAGE PLAIN.

What PLAIN costs. PLAIN keeps the value in the heap row. Each point below is inferred from the source, and vector_storage.py computes it:

- A vector(1536) row is then 6,184 bytes, so one row fits on each 8 kB heap page. A million rows are a million heap pages, 7.6 GiB, and every sequential scan reads them all.

- A halfvec(1536) row fits twice on a page.

- A vector(3072) row is 12,328 bytes, over MaxHeapTupleSize of 8,160 bytes. So an insert fails with row is too big: size 12328, maximum size 8160. Not run.

- The ALTER TABLE docs say that "SET STORAGE doesn't itself change anything in the table". It only sets the strategy for future writes, so old rows stay in TOAST until they are written again.

Instacart moved its semantic search from FAISS, a vector search library, to pgvector. Its post lists its index design changes. One is a storage change: it "Updated the embedding column to use inline storage instead of TOAST". Another is a tuning change: it raised max_parallel_workers_per_gather and max_parallel_workers to 8, which "speeds up the scans where Postgres decides not to use a pgvector index". The same post reports "a 10x reduction in write workload" from a normalized data model, against its earlier denormalized Elasticsearch model. It does not give the table's size or the embedding's dimension count.

Evidence
The Instacart quotes are from a post by Mittal and others on the Instacart company blog of 2025-05-29, https://company.instacart.com/tech-innovation/how-instacart-built-a-modern-search-infrastructure-on-postgres, verified from the post. The row-size error is at hio.c lines 532 to 536, REL_17_11.

### How large is the index?

An HNSW element holds a 72-byte header with ten heap TIDs, then a copy of the vector. Its neighbour list holds (level + 2) × m links of 6 bytes each, and m is 16 by default. The build keeps an element and its neighbours on one page when both fit. So for a million vectors of 1,536 dimensions:

Index | Elements per 8 kB page | Index size, lower bound

HNSW on vector(1536), m = 16 | 1 | 1,000,001 pages, 7.6 GiB

HNSW on the expression embedding::halfvec(1536) | 2 | 500,001 pages, 3.8 GiB

HNSW on binary_quantize(embedding)::bit(1536) | 17 | 58,825 pages, 0.45 GiB

Upper-level elements have larger neighbour lists, so these sizes are lower bounds. They are inferred from the struct sizes. The self-test of vector_storage.py checks the first two. For bit it measures over 1,000 elements and gets 59 pages, so it prints 16.9 per page, where whole pages hold 17. None was measured on a server.

The index is at least as large as the vectors, so the cache-miss arithmetic decides its speed. Each graph step loads the unvisited neighbours of one candidate, up to 2 × m = 32 at the lowest level. At one element per page, each neighbour is a page read when it misses the pool: 89 µs on the laptop, about 1 ms on gp3. So one search can pay hundreds of reads. That count is inferred from hnswutils.c lines 891 to 933 and the layout. The README gives two ways to shrink the working set: "Use the halfvec type instead of vector for a smaller working set", and "Use binary quantization with re-ranking to keep indexes in-memory at scale". The retrieval-internals course, in its Phases 2 and 4, measures memory per vector and the recall that quantization costs.

### What does a build need?

An HNSW build "happens in two phases". In the first, "the graph is held completely in memory". When it runs out of the memory "determined by maintenance_work_mem", it writes the graph to disk. Then it inserts each remaining vector "one by one, just like on INSERT". That second phase is much slower, and the README shows the notice it prints:

NOTICE:  hnsw graph no longer fits into maintenance_work_mem after 100000 tuples
DETAIL:  Building will take significantly more time.
HINT:  Increase maintenance_work_mem to speed up builds.

The graph holds each vector plus a list of 2 × m candidate neighbours of 16 bytes each. So it needs at least 6,152 + 512 = 6,664 bytes per element for vector(1536), and at least 6.7 GB for a million. That is a lower bound inferred from the structs. maintenance_work_mem is 64MB by default. Two AWS pages disagree for RDS: the memory page says 64 MB, and the autovacuum page gives a formula, about 500 MB on 32 GiB. Check yours with show maintenance_work_mem.

Since pgvector 0.8.4, IVFFlat fails instead of slowing down. Older versions, such as 0.8.2 on RDS 17.11, use more memory than maintenance_work_mem and do not stop. Its build holds the list centres and 50 samples per list, at least 10,000 samples. Since 0.8.5 the samples are also capped at the heap's pages times 291. When that passes maintenance_work_mem, the build raises an error. A million vectors with the README's starting point of 1,000 lists need 51,000 × 6,152 bytes, about 300 MB. So at the default:

ERROR:  memory required is 300 MB, maintenance_work_mem is 64 MB

That message is computed by vector_storage.py from the source, and it was not run. Raise the memory for one session only, as the README does with SET maintenance_work_mem = '8GB'. The README also warns: "Do not set maintenance_work_mem so high that it exhausts the memory on the server". On Aurora, about 75% of memory already belongs to shared_buffers, so less room is left for a build. That is inferred.

After the graph is built, the code comment says: "we perform one more scan through the index and write all the pages to the WAL". IVFFlat logs each new page as a full page image. Each page image leaves out the page's free space. A vector(1536) HNSW page has about 1,728 free bytes, so its image is about 6,464 bytes. So a build writes about 79% of the index size into the WAL, about 6.0 GiB for 1M vector(1536) rows, and for HNSW most of it comes at the end, at once. The total is inferred from the code, and it ignores compression and record headers.

- start CREATE INDEX starts, and the graph grows in maintenance_work_mem, at least 6,664 bytes per vector.

- 64 MB About 10,000 vectors in, the NOTICE prints. The rest of the vectors go in one by one, as INSERTs do, and run slower.

- end Every index page goes into the WAL, without its free space: about 6.0 GiB in one burst.

- after Checkpoints come early, replicas replay 6.0 GiB, and the WAL archive grows.

One million vector(1536) rows. The times are steps, not seconds. 10,000 is 64 MiB / 6,664 bytes, from a lower bound on memory, so the real count is lower. All inferred.

What that burst does to a server, each point inferred from the WAL volume:

- With max_wal_size at 1GB, the burst requests checkpoints early, as Phase 1 explained.

- Every streaming replica must receive and replay the same bytes, so replica lag rises. Phase 5, section 5.1, measures that lag in bytes and in seconds.

- The WAL archive and the next backup grow by the same amount. Phase 5, section 5.6, covers the archive and base backups.

Measure it with pg_current_wal_lsn() before and after the build, as E16 does. The README also says: "In production environments, create indexes concurrently to avoid blocking writes", with CREATE INDEX CONCURRENTLY.

Evidence
The two-phase build, the in-memory graph and the final WAL scan are from the comment at the top of hnswbuild.c, lines 1 to 35, pgvector v0.8.7. The notice is at lines 533 to 545 and in the README's "Index Build Time". log_newpage_range is at lines 1142 to 1143. IVFFlat's samples are at ivfbuild.c lines 400 and 456 to 466, the error at ivfutils.c lines 126 to 133, and GENERIC_XLOG_FULL_IMAGE at ivfutils.c line 166. maintenance_work_mem is at postgresql.conf.sample line 142, REL_17_11, and the RDS value is from the RDS memory page.

### What happens after deletes?

A delete leaves a dead heap tuple and a dead element in the index. HNSW's VACUUM makes four passes. It removes heap TIDs, repairs the graph, then confirms the repair and marks elements deleted. The repair pass finds new neighbours for every element that lost some, so it runs graph searches, not only page writes. Its page scans read through a 256 kB bulk-read ring. The graph searches of the repair pass use the normal pool, so a large repair can still fill it. The README says: "Vacuuming can take a while for HNSW indexes. Speed it up by reindexing first", with REINDEX INDEX CONCURRENTLY and then VACUUM.

A deleted element's slot is reused by a later insert, so the index file keeps its size, as a B-tree does. VACUUM VERBOSE prints the B-tree section's page line for this index too. pgvector's cleanup function fills in only the page count, so the other three numbers print as 0. That is inferred from the code.

Check the pgvector version before you trust VACUUM on a large index. pgvector 0.8.3 "Fixed possible index corruption with HNSW vacuuming", and 0.8.4 "Fixed hnsw graph not repaired error with HNSW vacuuming". 0.8.4 also fixed IVFFlat builds that used more than maintenance_work_mem, and 0.8.7 "Fixed buffer overflow with IVFFlat index build". RDS for PostgreSQL 17.11 lists pgvector 0.8.2 on its extension versions page, so that RDS version has none of these fixes. That follows from the version order. The extversion column of pg_extension, in the row for the vector extension, shows your version.

Evidence
The four passes are at hnswvacuum.c lines 785 to 792, v0.8.7, the ring at line 747, and the page count at line 815. Slot reuse is at hnswinsert.c line 212. The fixes are from the pgvector CHANGELOG at v0.8.7. The RDS version list was read on 2026-10-20 from the AWS page of extension versions for RDS.

### Where do you see it?

Question | Command or signal | Expected for 1M vector(1536) rows

how large is one value | select pg_column_size(embedding) from items limit 1 | 6,148 bytes, the stored bytes without the 4-byte header. A PLAIN row shows 6,152

where do the bytes sit | select pg_size_pretty(pg_relation_size('items')), pg_size_pretty(pg_table_size('items')) | a small heap, and a table size that includes about 8.2 GB of TOAST

how large is the index | select pg_size_pretty(pg_relation_size('items_embedding_idx')) | at least 7.6 GiB for HNSW

does the build fit | the NOTICE above, and pg_stat_progress_create_index | the NOTICE at 64 MB

does a search miss the pool | EXPLAIN (ANALYZE, BUFFERS) of one search, as the README advises | read counts close to the graph steps

on RDS or Aurora | Performance Insights IO:DataFileRead during searches | rises when the index outgrows the pool

The expected column is inferred from this section and was not run. The 8.2 GB of TOAST is this course's arithmetic. Three full chunk rows of 2,032 bytes, one short row of about 200, and four line pointers are about 6,312 bytes per vector. The rest of the page cannot hold the next value's first chunk, so each vector takes one 8 kB page.

Do not build an HNSW index on a large table at the default maintenance_work_mem of 64 MB. The build leaves memory after about 10,000 vectors, or fewer, and runs much slower. Its end writes the whole index into the WAL at once, which every replica must replay, as Phase 5, section 5.1, explains.

Run uv run python phase02_structures/vector_storage.py --rows 4000000, then the same with --type halfvec. Compare each index size with your shared_buffers. Then say which of the three index rows above you would build, and what recall test you would run first.

So a pgvector table pays for every vector twice, once in TOAST or the heap and once in the index.

Go deeper: the row in a figure, the structs, parallel builds, SERIALIZABLE
The row, drawn. Here is the same row as the figure above, with the page each part lives on:

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

The structs. The element is HnswElementTupleData, at src/hnsw.h lines 373 to 383, v0.8.7. The neighbour tuple size is HNSW_NEIGHBOR_TUPLE_SIZE at line 82, and m defaults to 16 at line 54. The keep-together rule is the placement loop at hnswbuild.c lines 192 to 229. For a TOASTed value, pg_column_size counts the stored bytes without the 4-byte header, at detoast.c lines 606 to 616, REL_17_11, which is why it shows 6,148 and not 6,152.

Parallel builds. A parallel HNSW build holds its graph in shared memory, per the same comment in hnswbuild.c. In Docker, the README says to make --shm-size at least maintenance_work_mem "to avoid an error with parallel HNSW index builds".

SERIALIZABLE. HNSW and IVFFlat set ampredlocks = false, at src/hnsw.c line 348 and src/ivfflat.c line 265. For such an index, PostgreSQL 17 takes a predicate lock on the whole index at the start of a scan, at indexam.c lines 319 to 320. It checks the whole index for conflicts on every insert, at lines 225 to 228. So a serializable vector search conflicts with every concurrent insert into that index by another serializable transaction, at predicate.c line 4330. Each conflict is one rw-dependency, not an abort, and an abort needs the dangerous structure that Phase 3 explains. The code is verified. The abort rate is inferred and not measured. Phase 3 explains predicate locks.

Deletes from the search side. The retrieval-internals course, in its Phase 7, covers deletes from the side of search quality.

## What can you do now, and what comes next?

You can now price a miss, a B-tree write, an LSM write, a scan and a vector index before you choose. These are the eleven skills of this phase:

- Compute what a cache miss costs, from the page cache and SSD numbers of the earlier course.

- Compute a B-tree's height, and the memory that holds a lookup to one cache miss. Count the pages one PostgreSQL row change writes.

- Explain why an LSM tree writes fast and reads across several runs.

- Explain what compaction does and why it can stall writes, and build Bitcask's merge with hint files.

- Size a Bloom filter for a target false-positive rate, with the arithmetic.

- Estimate read, write and space amplification of a workload on each structure.

- Choose a structure from the decision table, and name the measurement that would prove the choice wrong.

- Explain why LRU fails during a table scan, what PostgreSQL and InnoDB do about it, and which PostgreSQL scans still flood the pool.

- Size shared_buffers on RDS and on Aurora, and price a cache miss on an EBS gp3 volume against the laptop SSD.

- Look inside the buffer pool and at the I/O of one query on PostgreSQL 17, with pg_buffercache, pg_stat_statements and pg_stat_io.

- Work out what a table of embeddings stores in its heap, its TOAST table and its HNSW or IVFFlat index. Then say what a build of that index needs in memory and writes to the WAL, and what VACUUM does after deletes.

One fact is still unexplained. A PostgreSQL update writes a new row version with a new TID, and this lesson did not say why. Phase 3 answers that through one question. Two transactions both commit without error, and the result is one neither would produce alone. Which isolation level allowed that, and which would have stopped it?

## Lab: E1 to E16

The lab proves each idea on your laptop. E6, E8, E9 and E10 are the demonstration. The self-tests and E15 were run by the author, and every other exercise was not, as the text inside says.

Open the lab: E1 to E16
Run status, 2026-10-20. The author ran every self-test of Phases 1 and 2, and the commands of E15, on an Apple M4 Pro with macOS 26.6 and Python 3.12.14 under uv. Those outputs are real, and E1 and E15 quote them. The first run of the self-tests failed in cache_sim.py, and E1 gives the cause and the fix. Every other exercise was written and reviewed, but not run by the author. Its "Expected" line says "Not run by the author yet." and then gives the expected shape. Each number in it comes from arithmetic in this phase or from a cited source. Some come from working through the code and its seed by hand. None of them is a measurement. The byte and block counts have no randomness that depends on time. With the same flags and seed, they should match the arithmetic exactly or closely, as each exercise says. The latency numbers come from a model, not from your SSD.

What you build. The lab extends the Phase 1 store in two directions. bitcask_merge.py adds segments, merge and hint files to the Phase 1 log. lsm.py builds an LSM tree on the Phase 1 entry format. Both run on the simulated file system of Phase 1, fsim.py, through a wrapper that counts every byte:

File | What it holds | Self-test checks

phase02_structures/counting.py | CountingFS: bytes written and read, and blocks touched, per category | block counts against hand-worked offsets

phase02_structures/btree_model.py | the height, memory and write arithmetic of section 2.2, with the heap page and each index leaf of a row change | the numbers of section 2.2, and a row change that counts more than one page

phase02_structures/bitcask_merge.py | segments, merge, hint files, and a crash test of the merge | the merge numbers of section 2.4, both crash-test counts

phase02_structures/lsm.py | memtable, WAL, flush, L0 and L1, compaction, a Bloom filter per run. Each data block starts on a 4,096-byte boundary, as RocksDB's block_align option does. That option is false by default, at table.h line 772, v11.8.1 | each rule of Rules, removed one at a time, fails a check. A get that probes one run reads one device block

phase02_structures/bloom.py | the standard and the blocked Bloom filter, theory and measurement | the FPR formula against section 2.5, no false negatives

phase02_structures/amplification.py | the two layouts under two workloads, the range demo, the latency model | log write amplification 133 / 113, LSM against log, at-once against paced

phase02_structures/cache_sim.py | LRU, LFU, 2Q, ARC, PostgreSQL's clock and ring, InnoDB's midpoint | hand-worked traces of section 2.8, ARC's invariants

phase02_structures/vector_storage.py | the storage arithmetic of section 2.9: value sizes, TOAST, PLAIN rows per page, HNSW elements per page, build memory, the IVFFlat error | the PostgreSQL 17 and pgvector 0.8.7 constants, the sizes of section 2.9, and the keep-together rule, which a mutant without it fails

The demonstration of this phase is four exercises. E6 gives read, write and space amplification for two layouts under two workloads. E9 shows the compaction storm in the latency histogram. E8 gives the Bloom filter's measured FPR against its memory. E10 gives the LRU and 2Q hit rates under a scan.

All commands run from elite-storage/code/.

-  E1 offline Run every self-test of this phase and of Phase 1. This phase imports Phase 1's code.

- Run: for f in phase02_structures/*.py phase01_durability/*.py shared/durable.py; do echo "$f"; uv run python "$f" --self-test; done

- Expected, run by the author on 2026-10-20: self-test passed after each of the 13 files. The Phase 2 self-tests assert the numbers of sections 2.2, 2.4, 2.5 and 2.9, so a pass also checks that arithmetic.

- The first run failed. cache_sim.py --self-test stopped with KeyError: 99 in TwoQ.access, on the mixed trace near its end. The cause: when a page whose number is in A1out comes back, _reclaimfor may first page out the tail of A1in and trim A1out. If the returning page's own number was the oldest entry of a full A1out, that trim dropped it, and the next line's del failed. The fix keeps the paper's order, reclaim and then add to Am, and removes the number only if it is still there. It is at cache_sim.py:191. The earlier "every self-test passes" was never run, so this bug sat in a file that only py_compile had checked.

- If it fails: the assertion message names the number that differs. Compare it with the section that the test names before you change any code.

- Teaches: each rule the text calls important has a check that fails without it.

-  E2 offline The height and memory of a B-tree.

- First write your prediction for 10 million and for 1 billion keys: height, and memory above the leaves.

- Run: uv run python phase02_structures/btree_model.py --keys 10000000, then the same with --keys 1000000000, then uv run python phase02_structures/btree_model.py --leaf-fill 0.67.

- Expected: Not run by the author yet. For 10 million keys: levels of 27,323, 96 and 1 pages, height 3, and 776 KiB above the leaves. For a billion: height 4, and 9,622 pages above the leaves. The write model prints 165.3, 17.9 and 3.1 bytes per byte changed. With --leaf-fill 0.67, a leaf holds 273 entries, so 10 million keys need 36,631 leaves. That is about 1.34 times as many, close to 0.90 / 0.67.

- Then run: uv run python phase02_structures/btree_model.py --indexes 2 --heap-changes-per-page 6.

- Expected: Not run by the author yet. The row-change line for leaves at c = 1 prints 35,949 bytes. That is 2,881 for the heap page and 16,534 for each of the two leaves, from section 2.2.

- Teaches: a B-tree needs memory for its inner levels only, which is a few hundred pages per million keys. A PostgreSQL row change writes more than one page.

-  E3 offline Bitcask merge and hint files.

- Run: uv run python phase02_structures/bitcask_merge.py --demo.

- Expected: Not run by the author yet. Live data 229,900 bytes. Before the merge, 738,300 bytes on disk, space amplification 3.21. The merge reads 12 files and writes 233,700 bytes of data and 7,220 bytes of hints. After it, 240,920 bytes on disk, space amplification 1.05. A restart reads 738,300 bytes before the merge, 233,700 after it without hints, and 7,220 with them.

- Teaches: merge turns space amplification back to about 1, and hint files make a restart read keys without values.

-  E4 break-it, offline Crash the merge at every step, in the right order and the wrong one.

- Run: uv run python phase02_structures/bitcask_merge.py --crash-test, then add --unsafe-remove-first.

- Expected: Not run by the author yet. The right order has 6 crash steps, each tried with three crash kinds, so 18 recoveries. It prints RESULT: 0 violations in 18 recoveries. The wrong order has 5 steps, so 15 recoveries. It prints two lines for merge.dir-synced, one for os and one for power. Each says all 36 live orders were lost. Then RESULT: 2 violations in 15 recoveries.

- If it fails with "step ... was never reached": a hook name in merge changed. Compare MERGE_STEPS_SAFE with the hook calls.

- Teaches: compaction replaces files, so it needs the checkpoint's order. New data is durable first, then new names, then the removal.

-  E5 offline Watch an LSM tree flush and compact.

- Run: uv run python phase02_structures/lsm.py --demo.

- Expected: Not run by the author yet. 23 flush lines and 5 compaction lines. There are five groups of four flushes, each followed by one compaction into L1 with tombstones dropped. Then come three more flushes. The levels then show a memtable of 192 keys and three L0 runs of 126 keys. L1 holds one run of 2,000 keys. These counts are worked out from the code. Then the counters: device bytes for wal, flush and compaction, with compaction the largest. Write amplification is well above the log's 1.18.

- The arithmetic behind the compaction cost: L1 holds 20,000 entries of 133 bytes, 30 to a 4,096-byte block. That is 667 blocks, about 2.73 MB, and the run's index and filter add about 0.04 MB. A memtable flushes at 64 KiB, which is 493 distinct keys and about 499 puts, because some keys repeat. So 4 L0 runs bring about 4 × 499 × 113 bytes = 0.23 MB of new data. Each compaction then writes about 2.78 MB for it, about 12.3 bytes per byte. Worked out from the code, not run.

- Teaches: the cheap part of an LSM write happens at once, and the expensive part happens at compaction.

-  E6 offline The main demonstration: amplification of two layouts under two workloads.

- First write your prediction for each cell of the table in section 2.6.

- Run: uv run python phase02_structures/amplification.py, then uv run python phase02_structures/amplification.py --range-demo.

- Expected: Not run by the author yet. Four rows. The log rows show write amplification 1.18. They read about 1.03 blocks per present get and 0 per absent get. Their space amplification is 11.77 on write-heavy and 2.35 on read-heavy. The lsm rows show write amplification about 14.7. They read about 1.0 block per present get and 0.02 per absent get. Their space amplification is about 1.25. The range demo shows 103 blocks and 20,000 keys checked for log, and 4 blocks for lsm. The byte counts and the range counts are worked out from the code and its seed. The block counts per get are estimates, because they depend on Bloom filter false positives.

- Where the numbers come from, worked out from the code, its defaults and seed 1, not run. An entry is 20 + 13 + 100 = 133 bytes for 113 bytes of key and value. So the log writes 133 / 113 = 1.18. Seed 1 makes 179,952 of the 200,000 write-heavy operations puts, and 19,883 of the read-heavy ones. So the log's space is 199,952 × 133 / 2,260,000 = 11.77, and 39,883 × 133 / 2,260,000 = 2.35. Its 1.03 blocks per get comes from entries that cross a block boundary: 132 of every 4,096 start offsets do. The LSM's 14.7 adds the WAL, 1.18, the flush, about 1.22, and the compaction, about 12.3 from E5. A flush and a compaction write a little more than their entries. Each run also holds its index, its filter and its block padding. The LSM's space is L1 plus a few L0 runs and the log.

- If a row is far from the table: check the header line against the defaults. The table in section 2.6 assumes 20,000 keys, 100-byte values, 200,000 operations and 10 bits per key.

- Teaches: the log and the LSM read alike with filters on. They differ in write and space amplification, in opposite directions.

-  E7 break-it, offline Remove the Bloom filters.

- Run: uv run python phase02_structures/amplification.py --layouts lsm --bloom-bits 0.

- Expected: Not run by the author yet. Blocks per absent get rise from about 0.02 to about 2.5. That is one block per run that covers the key, and there are 1 to 4 runs. Blocks per present get rise above 1, because L0 runs above L1 are now read too. Write amplification falls a little, because no filter bytes are written.

- Teaches: a filter costs a few bits per key of memory and removes almost every wasted block read.

-  E8 offline Part of the demonstration: the measured FPR against the filter's memory.

- First predict the measured FPR at 4 and at 10 bits per key, from the table in section 2.5.

- Run: uv run python phase02_structures/bloom.py --keys 100000 --probes 200000 --blocked.

- Expected: Not run by the author yet. Seven rows from 2 to 16 bits per key. The memory column is 100,000 × bits / 8 bytes, so 125,000 bytes at 10 bits. The measured standard FPR sits within a few standard errors of theory, near 0.82% at 10 bits. The blocked column is a little higher, near the wiki's 0.95% at 10 bits.

- The code is at bloom.py:111. add sets the k bits of a key, and may_contain returns False at the first zero bit. _positions computes all k positions from one BLAKE2b hash as h1 + i × h2, which is called double hashing. The theory assumes k independent hashes, so a measurement can differ a little from it.

- Teaches: FPR falls by about 10 for each 4.8 bits per key. A cache-line layout costs a factor of about 1.13.

-  E9 break-it, offline Part of the demonstration: the compaction storm in the latency histogram.

- Run: uv run python phase02_structures/amplification.py --layouts lsm --workloads write-heavy --latency --compaction at-once, then the same with --compaction paced.

- Expected: Not run by the author yet. The at-once run prints 451 background jobs: 361 flushes and 90 compactions, the largest about 4.2 ms. The job counts are worked out from the code and its seed. Its put p50, the median, is under 1 µs, and its put p99 is a few milliseconds. Its histogram has a group of operations between 1,000 and 5,000 µs. The paced run has the same jobs, and a put p99 well under 1 ms. Its largest latencies stay under about 1 ms, with 0 write stops.

- The timeline behind it: four flushes come about 27.7 ms apart. The L0 to L1 merge starts at about 110.8 ms. The merge reads about 2.92 MB at 2,000 MB/s, which is 1.5 ms. It writes about 2.78 MB at 1,000 MB/s, which is 2.8 ms. That is 4.2 ms in all. Gets, puts and flushes keep the device busy about 17% of the time. If the background work grows past --stall-ms, 50 ms by default, the next put waits for all of it. That is the model's write stop. These numbers are worked out from the model's defaults and the seed, not run.

- Then break it: run the paced command again with --rate 60000 --write-mbps 150. The device then needs about 1.1 seconds of work per second. Compactions of about 20 ms each, 27 per second, need about 0.54. Gets need 0.48, and puts and flushes 0.1. That arithmetic uses the defaults of section 2.4. The backlog grows without limit, so expect a non-zero write stops count and puts that wait tens of milliseconds.

- Teaches: compaction run at once causes a storm. Compaction that cannot keep up causes a stall.

-  E10 offline Part of the demonstration: LRU against 2Q under a scan.

- First predict which keeps the larger share of its no-scan hot hit rate.

- Run: uv run python phase02_structures/cache_sim.py --policies lru,2q.

- Expected: Not run by the author yet. A header line with scans at 33% of 450,000 references. Two rows. LRU's kept value is lower than 2Q's. The 2Q paper's own test kept about 60% for LRU and about 70% for 2Q. Its trace was different, so expect the same direction, not the same numbers.

- The code is TwoQ.access at cache_sim.py:181. _reclaimfor, at cache_sim.py:166, frees a frame. It takes the oldest page of A1in when A1in is over Kin, and puts its number into A1out. Otherwise it takes the oldest page of Am, without a ghost entry. The self-test traces a pool of 4 frames by hand. A hot page reaches Am. Then a scan of 6 new pages passes through A1in and A1out, and the hot page still hits afterwards. The self-test asserts that trace, and it passes, as E1 records.

- Teaches: a policy that waits for a second access keeps hot pages through a scan.

-  E11 break-it, offline All seven policies, and two ways to break scan resistance.

- Run: uv run python phase02_structures/cache_sim.py --policies all.

- Then run: uv run python phase02_structures/cache_sim.py --policies midpoint --scan-touches 4, then the same with --old-time 0.

- Expected: Not run by the author yet. In the first table, clock-ring keeps more of its hit rate than clock, because the scan cycles through 32 buffers. arc and 2q keep more than lru. In the midpoint pair, the window of 1,000 references keeps the hot hit rate near its no-scan value. With --old-time 0, every scan page is promoted on its second touch, and kept falls toward LRU's.

- Teaches: InnoDB's time window and PostgreSQL's ring are the parts that make each system resist scans.

-  E12 local, PostgreSQL 17 See PostgreSQL's ring with EXPLAIN, and the scan that does not use it.

- If storage_lab does not exist, run createdb -h /tmp -p 5432 storage_lab first.

- Run: psql -h /tmp -p 5432 -d storage_lab -c "create table scan_big as select g as id, repeat('x', 200) as pad from generate_series(1, 400000) g" -c "create table scan_small as select g as id, repeat('x', 200) as pad from generate_series(1, 50000) g".

- Then run: psql -h /tmp -p 5432 -d storage_lab -c "show shared_buffers" -c "select relname, pg_relation_size(oid) / 8192 as pages from pg_class where relname in ('scan_big', 'scan_small')".

- Then run this twice, and read the second output: psql -h /tmp -p 5432 -d storage_lab -c "explain (analyze, buffers) select count(*) from scan_big" -c "explain (analyze, buffers) select count(*) from scan_small".

- Expected: Not run by the author yet. With the default 128 MB, the ring threshold is a quarter of 16,384 buffers: 4,096 pages. A row here is about 236 bytes, so about 34 rows fit on a page. That is an estimate from the row layout of section 2.2, not checked. So scan_big has about 11,800 pages, and scan_small about 1,500. On the second run, scan_small should show shared hit for almost every page and no read. scan_big should show mostly read, although its 92 MiB would fit in the 128 MB pool. Expect up to about 2,000 shared hit pages too. CREATE TABLE AS writes through a 16 MB ring, and its last pages stay in the pool. That is inferred from freelist.c lines 541 to 599. The ring keeps the scan to a few buffers. Its reads come from the OS page cache, so the scan is still fast. That last point is inferred, not measured.

- The planner may choose a Parallel Seq Scan for scan_big. Each worker then gets its own ring, because the ring rule runs for each process that scans. That is inferred from heapam.c lines 445 to 452, REL_17_11. Read the plan before you read the counts. On 18, the ring is about 94 buffers, and a fresh 18 cluster has data checksums on. So if a checkpoint runs between create table ... as and the first scan, that scan writes hint-bit page images. Either way, only the second run is clean. Both 18 points are inferred.

- Then break the ring: psql -h /tmp -p 5432 -d storage_lab -c "create index on scan_big (id)" -c "vacuum analyze scan_big". Run this twice, and read the second output: psql -h /tmp -p 5432 -d storage_lab -c "set enable_seqscan = off" -c "set enable_indexscan = off" -c "explain (analyze, buffers) select count(pad) from scan_big where id <= 300000".

- Expected: Not run by the author yet. The plan is a Bitmap Heap Scan over about 300,000 / 34 = 8,800 heap pages. On the second run, it should show shared hit for almost all of them. The Seq Scan of the same table did not. So the bitmap scan kept its pages in the normal pool, as section 2.8's table says. The page count is the estimate above, not checked.

- Clean up: psql -h /tmp -p 5432 -d storage_lab -c "drop table scan_big, scan_small".

- Teaches: PostgreSQL protects its buffer pool from large sequential scans with a ring. A bitmap heap scan of the same table fills the normal pool.

-  E13 local, PostgreSQL 17 A real B-tree page, and the WAL of inserts with a sequence key and a random key.

- Run: psql -h /tmp -p 5432 -d storage_lab -c "create extension if not exists pageinspect" -c "create extension if not exists pgstattuple". Both ship with PostgreSQL. The PostgreSQL 17 pageinspect docs say: "All of these functions may be used only by superusers". Your local role is normally a superuser, which is not checked.

- Run: psql -h /tmp -p 5432 -d storage_lab -c "create table k_seq (id bigint generated always as identity primary key, pad text)" -c "create table k_uuid (id uuid primary key default gen_random_uuid(), pad text)". Both tables have only a primary key, as in Vondra's test.

- Load each table in 20 batches of 50,000 rows, with a checkpoint after each batch. So every batch starts a new cycle of full page images, and each leaf a batch touches pays one. This shell loop does it, and prints pg_stat_wal, verified in the PostgreSQL 17 docs, Table 27.26. The reset target wal is accepted at pgstatfuncs.c line 1746, REL_17_11:
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

- Then read both indexes: psql -h /tmp -p 5432 -d storage_lab -c "select 'seq' as k, level from bt_metap('k_seq_pkey') union all select 'uuid', level from bt_metap('k_uuid_pkey')" -c "select 'seq' as k, leaf_pages, avg_leaf_density from pgstatindex('k_seq_pkey') union all select 'uuid', leaf_pages, avg_leaf_density from pgstatindex('k_uuid_pkey')" -c "select live_items, avg_item_size, free_size from bt_page_stats('k_seq_pkey', 1)" -c "select itemoffset, ctid from bt_page_items('k_seq_pkey', 1) limit 3".

- Expected: Not run by the author yet. wal_fpi for k_uuid should be many times that of k_seq, because each batch touches nearly every UUID leaf. The heap pages cost both tables about the same, since both fill the heap in arrival order. The direction is inferred from section 2.2 and Vondra's result, and the counts are not predicted. pg_stat_wal counts the whole cluster, so other activity on the server adds to both rows. pg_stat_reset_shared('wal') also clears it for the whole cluster, so run E13 only on your laptop. The pg_sleep gives the statistics a moment to arrive. Since PostgreSQL 15 a backend sends its statistics when it exits, at pgstat.c lines 504 to 518, REL_17_11. So on 17 the sleep is only a margin. On 18, data checksums are on in a new cluster, so hint-bit changes from other activity can add page images to both rows. That is inferred from the 18 default. bt_metap should show level 2, a height of 3, for both. k_seq_pkey should show an avg_item_size of 16, as the docs' example does for a 4-byte key. Its leaf density should be near 90. k_uuid_pkey has 24-byte items and a lower density, because random keys split pages in the middle. bt_page_items shows each entry's ctid, the heap TID that the leaf points to.

- Clean up: psql -h /tmp -p 5432 -d storage_lab -c "drop table k_seq, k_uuid".

- Teaches: one schema decision, the key type, changes the WAL volume of the same inserts. The counters to watch are wal_fpi and wal_bytes.

-  E14 local, PostgreSQL 17 Look inside the pool, and at the I/O of one scan.

- Needs scan_big from E12, with its index. Create them again if you cleaned up. Then restart your server, so that the pool no longer holds the pages that E12's bitmap scan and CREATE TABLE AS left there. Without the restart, scan_big holds thousands of buffers, not the ring.

- Run: psql -h /tmp -p 5432 -d storage_lab -c "create extension if not exists pg_buffercache" -c "select pg_stat_reset_shared('io')" -c "explain (analyze, buffers) select count(*) from scan_big".

- Then run: psql -h /tmp -p 5432 -d storage_lab -c "select * from pg_buffercache_usage_counts()" -c "select c.relname, count(*) as buffers from pg_buffercache b join pg_class c on b.relfilenode = pg_relation_filenode(c.oid) where c.relname like 'scan_big%' group by 1" -c "select backend_type, context, reads, hits, reuses from pg_stat_io where object = 'relation' and reads > 0 order by reads desc".

- Expected: Not run by the author yet. scan_big holds about 32 buffers, the ring of section 2.8. Rogov saw 32 after a Seq Scan on 14, page 158. A Parallel Seq Scan can hold up to 32 per process. In pg_stat_io, a row with context bulkread holds most of the scan's 11,800 reads, and its reuses is close to that count minus the ring. With parallel workers, background worker rows share the reads.

- Then run the bitmap scan of E12 again, and repeat the second command. Expected: scan_big now holds about 8,800 buffers, and the reads appear under context normal. That is the flood of section 2.8, seen from inside the pool.

- If pg_stat_statements is in shared_preload_libraries, run create extension if not exists pg_stat_statements, then the top-reads query of section 2.1. Expected: the two explain (analyze, buffers) select count(*) ... entries lead by shared_blks_read. They are tracked as utility statements, at pg_stat_statements.c line 1106, REL_17_11. If the module is not loaded, the query fails with pg_stat_statements must be loaded via "shared_preload_libraries", from pg_stat_statements.c line 1657, REL_17_11.

- If it fails: pg_buffercache needs a superuser or pg_monitor. pg_stat_reset_shared needs a superuser or a grant, because system_functions.sql line 674, REL_17_11, revokes it from public.

- Teaches: which table holds the pool, which kind of read filled it, and which statement caused it.

-  E15 offline What one embedding costs, in heap pages, TOAST, index pages, build memory and WAL.

- First predict for 1 million vector(1536) rows: the value size, whether it is TOASTed, and the HNSW index size.

- Run: uv run python phase02_structures/vector_storage.py, then the same with --dims 3072, then with --rows 4000000, then with --rows 4000000 --type halfvec.

- Expected, run by the author on 2026-10-20. The first command prints, among its lines:
value: 6,152 bytes. row before TOAST: 6,184 bytes, threshold 2,032
TOAST: the value moves out of line in 4 chunks of up to 1,996 bytes. The heap row keeps 50 bytes
largest vector that stays inline here: 498 dimensions
SET STORAGE PLAIN: rows per heap page 1, 1,000,000 pages = 7.6 GiB of heap
HNSW m=16: element tuple 6,224 bytes, neighbour tuple 200 bytes, 1.0 elements per page
HNSW index: at least 1,000,001 pages = 7.6 GiB. The end of the build writes every page to the WAL once, so about 7.6 GiB of WAL
HNSW graph in memory: at least 6.7 GB against maintenance_work_mem 64 MB, does not fit: expect the notice
IVFFlat lists=1,000: build memory 299 MiB. ERROR: "memory required is 300 MB, maintenance_work_mem is 64 MB"

- With --dims 3072, the PLAIN line says inserts fail with "row is too big: size 12328, maximum size 8160", and the index line says column cannot have more than 2000 dimensions for hnsw index. With 4 million rows, the HNSW index is at least 30.5 GiB, and at least 15.3 GiB as halfvec. The script's WAL line overstates the WAL: a page image leaves out the page's free space, so expect about 6.0 GiB for the first command, section 2.9.

- Where the numbers stop matching a server: the model counts only level-0 neighbour tuples, and only the lower bound of the build's memory. Section 2.9 lists what it leaves out.

- Teaches: the vector bytes are paid in the table and again in the index, and the build's memory and WAL follow from the index size.

-  E16 break-it, local, PostgreSQL 17 with pgvector Build an index past maintenance_work_mem, measure its WAL, and break an IVFFlat build.

- First install pgvector in storage_lab, and print the version that your server has: psql -h /tmp -p 5432 -d storage_lab -c "create extension if not exists vector" -c "select extversion from pg_extension where extname = 'vector'". Expected: 0.8.7, or at least 0.8.4. If it is older than 0.8.4, the HNSW vacuum fixes and the IVFFlat memory check of section 2.9 are missing. 0.8.7 fixes a buffer overflow in IVFFlat index builds, which this exercise runs.

- Load 20,000 random vectors. The where g > 0 makes the inner query run once per row: psql -h /tmp -p 5432 -d storage_lab -c "create table items (id bigint generated always as identity primary key, embedding vector(1536))" -c "insert into items (embedding) select (select array_agg(random()) from generate_series(1, 1536) where g > 0)::vector from generate_series(1, 20000) g".

- Then run: psql -h /tmp -p 5432 -d storage_lab -c "select pg_column_size(embedding) from items limit 1" -c "select pg_size_pretty(pg_relation_size('items')) as heap, pg_size_pretty(pg_table_size('items')) as with_toast".

- Expected: Not run by the author yet. pg_column_size prints 6148, the stored bytes without the header. The heap is about 150 pages, about 1.2 MB, because each row keeps only a 50-byte pointer. The table with TOAST is about 160 MiB: about 20,000 TOAST pages, one per value, plus the heap and the TOAST index. Both sizes are this course's arithmetic from section 2.9.

- Build the index with the default memory, and measure its WAL. This needs psql variables, so use one session: psql -h /tmp -p 5432 -d storage_lab, then select pg_current_wal_lsn() as before \gset, then set maintenance_work_mem = '64MB';, then create index items_embedding_idx on items using hnsw (embedding vector_l2_ops);, then select pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), :'before')) as wal, pg_size_pretty(pg_relation_size('items_embedding_idx')) as index;.

- Expected: Not run by the author yet. The build prints NOTICE:  hnsw graph no longer fits into maintenance_work_mem after N tuples, with N below 10,000. The index is at least 20,001 pages, about 156 MiB. The WAL is about 125 MiB, because the build logs every page once, without its free space. Run it again with set maintenance_work_mem = '512MB', after drop index items_embedding_idx. Expected: no notice, and a shorter build. The times are not predicted.

- Then break IVFFlat. Run set maintenance_work_mem = '64MB'; again, then create index on items using ivfflat (embedding vector_l2_ops) with (lists = 300);. Expected: ERROR:  memory required is 90 MB, maintenance_work_mem is 64 MB. That is 15,300 vectors of 6,152 bytes, from vector_storage.py --rows 20000 --lists 300. With lists = 20, the README's starting point for 20,000 rows, it needs about 59 MiB and fits.

- Then delete half and vacuum: delete from items where id % 2 = 0; then vacuum (verbose) items;. Expected: a line index "items_embedding_idx": pages: 20001 in total, 0 newly deleted, 0 currently deleted, 0 reusable. The index keeps its size, as section 2.9 says. The page count is from the model, not run.

- Clean up: drop table items;.

- If it fails: create extension vector needs pgvector installed for your server's version. On Homebrew it is a separate package, which is not checked here.

- Teaches: an index build has a memory cliff and a WAL burst, and both follow from the index size.

Open the six code checks

- Check 1. Open phase02_structures/lsm.py:268. This line decides which keys go into a run's Bloom filter. Suppose it read if bloom is not None and value is not None:. Write the shortest sequence of puts, deletes and flushes that returns a deleted value. Then find the self-test check that would fail, and say which line of it fails.

- Check 2. Open phase02_structures/lsm.py:330. A compaction drops tombstones only when _deeper_levels_empty is true. A simpler rule would drop them whenever the output is the last level. With three levels, Config(levels=3) or amplification.py --levels 3, describe a state where the two rules give different answers. Which rule removes more garbage, and is it still safe?

- Check 3. Open phase02_structures/bitcask_merge.py:202. Open keeps the entry with the highest sequence number when two files hold the same key. After a crash in the middle of a merge, the old and the new copy have equal sequence numbers. Explain why it does not matter which copy wins. Then suppose the merge gave each copied entry a new, higher sequence number. The store's own counter stays where it was. An order is deleted after the merge. What does the next restart return for that order, and why?

- Check 4. Open phase02_structures/cache_sim.py:327 and compare it with PostgreSQL's GetBufferFromRing at freelist.c line 727, REL_17_11. Both reuse a ring buffer only if its usage count is 0 or 1. Suppose the condition allowed any count up to 5. Which pages would a large scan then evict? What would the hit rate look like on the morning after a nightly report?

- Check 5. In any repository you own that configures a database, run grep -rn "fillfactor\|shared_buffers\|innodb_old_blocks\|innodb_buffer_pool\|innodb_change_buffering\|level0_\|write_buffer_size\|bloom\|gen_random_uuid\|UUIDField(\|id: :uuid\|wal_compression\|rate_limiter" <your repo>/. For each hit, name the amplification it changes, and the measurement that would show whether the value is right.

- Check 6. Open phase02_structures/vector_storage.py and find hnsw_elements_per_page. Compare its loop with hnswbuild.c lines 192 to 229 at pgvector v0.8.7. The self-test shows that the keep-together rule changes the count for vector(100). Explain why it changes nothing for vector(1536). Then, in any repository with pgvector, run grep -rn "vector(\|halfvec\|hnsw\|ivfflat\|maintenance_work_mem\|SET STORAGE" <your repo>/. For each index, compute its size with the script, and compare it with shared_buffers on the server that runs it.

## Checkpoint questions

The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

### Part A: the structures

- Test-out, explain. Walk through one put and one get on a B-tree and on a leveled LSM tree. For each, list what is read from the device and what is written, now and later. Use these words: leaf, heap page, page, checkpoint, WAL, memtable, run, compaction, filter. Then explain in two sentences why the LSM tree writes faster and reads slower.Answer sketch
B-tree put, in PostgreSQL: find the leaf, a miss unless cached. Change the heap page and one leaf per index in the buffer pool, and append a WAL record for each. Later, the checkpointer, the bgwriter or a backend writes each 8 kB page. The first change to each page after a checkpoint also puts a full page image into the WAL. B-tree get: inner pages from the cache, one leaf read, then the heap page that the TID names. In InnoDB, the primary-key leaf holds the row. LSM put: append to the WAL and insert into the memtable. A raw Put reads nothing, but a SQL engine such as MyRocks first reads the old row by primary key. Later, a flush writes the run, and each compaction rewrites it once per level. LSM get: memtable, then each run whose range and filter allow it, one block per run. The LSM writes faster because it turns writes into long sequential runs and pays no page image per page. It reads slower because a key can be in several runs, and filters only lower that cost.

- Test-out, predict. A service holds 200 GB of rows. The database has 32 GB of cache. It serves 5,000 point reads and 500 updates per second, each to a random row. An update changes 200 bytes. Estimate the device load of a B-tree and of a leveled LSM tree. Use the M2's 89 µs per miss and the write amplifications of this phase. Which structure wins, and by roughly how much? Would a migration from one to the other be worth it?Answer sketch
Reads are uniform over 200 GB with 32 GB of cache. Assume rows of about 1 KB, an example, so about 200 million rows. The primary-key index then has 200,000,000 / 366 = 546,449 leaves, rounded up, about 4.5 GB. Each leaf covers far more rows than a heap page, so assume the cache keeps the leaves. That is inferred, not checked. The heap then gets about 32 − 4.5 = 27.5 GB of cache, so about 86% of heap reads miss. PostgreSQL reads: 5,000 × 0.86 × 89 µs = 0.38 s of device time per second, on heap pages. InnoDB and the LSM read one page or block per get, and miss at about the same rate. So they need about 0.37 to 0.38 s too. Updates read their row first on every engine, MyRocks included: 500 × 0.86 × 89 µs = 0.04 s. B-tree writes, with c near 1: a HOT update changes only the heap page. That is 150 + 2 × 8,192 = 16.5 KB, so 8.3 MB per second. A non-HOT update adds up to 16.5 KB for the new heap page and for each index leaf. LSM writes: an update writes the whole new row, not the 200 changed bytes. So about 33 × 1,000 bytes × 500 = 16.5 MB per second, sequential, plus compaction reads. So both need about 0.42 s per second for reads. The two write bytes of the same order. PostgreSQL writes 8.3 MB per second or more, and the LSM about 16.5 MB. Half of PostgreSQL's bytes are random page writes. The reads decide the load, and they cost the same on both. So a migration is not worth it for speed. The LSM's 1.1 against the B-tree's over 1.5 in space could still matter for disk cost. These are estimates from this phase's models, not measurements.

- Test-out, demonstrate. Run E6, E8, E9 and E10. Show the four-row amplification table and explain each column. Show the latency histogram with the compaction storm, and the paced run beside it. Show the measured FPR against memory at 4 and 10 bits per key. Show the kept column for LRU and 2Q, and explain why they differ.Answer sketch
From the runs. Expected shapes are in E6, E8, E9 and E10. The key explanations: the log and the LSM read alike with filters, and differ in write and space amplification. The at-once storm puts p99 inside a 4.2 ms compaction, and pacing spreads it into 0.25 ms slices. FPR falls by about 10 for each 4.8 bits per key. 2Q keeps more because a page needs a second, separate access to enter Am.

- A colleague says: "Our audit log is write-heavy, and LSM trees are faster for writes. Let's move it from PostgreSQL to RocksDB". The log's key is a timestamp followed by an id. Reads ask for one hour of entries. Argue for or against, with the numbers of this phase. Which fact about the keys changes the write comparison? Which number decides the read comparison?Answer sketch
Against, mostly. Keys that always grow make the B-tree write to its rightmost leaf. So each page collects many changes, and c is large. In PostgreSQL the heap fills in arrival order too, so its pages also collect many inserts. Write amplification then falls toward 3, from section 2.2. Vondra's sequence key wrote about 2 GB of WAL in an hour where a random UUID wrote over 40 GB. The RocksDB wiki notes that leveled compaction is also cheaper for keys in order. So the LSM's write advantage mostly goes away. Reads of one hour are range scans. A B-tree walks adjacent leaves. An LSM reads every overlapping run, and whole-key filters do not help ranges. The number that decides the reads is blocks per range. Retention deletes of old hours have the queue shape of section 2.4. On PostgreSQL, a partition per day can be dropped whole, as Phase 4, section 4.6, shows. On RocksDB, DeleteRange and delete-triggered compaction keep the scans fast. Measure both on a copy, with real key order, past a full compaction cycle.

- This is broken. A service on RocksDB uses default options. Its put latency jumps to tens of milliseconds for a minute at a time. Its LOG file shows lines saying writes are stalled because of the number of level-0 files. The CPU is mostly idle, and the disk is busy. What is the cause, and how do you check it? Name the default trigger values involved, and two changes that would help.Answer sketch
Compaction cannot keep up with writes. The LOG lines have the format of section 2.4. Each starts with the column family in square brackets. Then come "Stalling writes because we have", the count of level-0 files, and the rate. At level0_slowdown_writes_trigger, 20, writes are held to delayed_write_rate, 16 MB per second by default. At 36, level0_stop_writes_trigger, writes stop, and the line says "Stopping writes" instead. The idle CPU and busy disk say the device, not the CPU, limits compaction. Check the Compaction Stats block of the LOG. Read L0's Files and Score, the Stall(sec) column and the Stalls(count) line. Compare the device's write throughput, from iostat, with what compaction needs. Help: give compaction more device time or more parallel jobs, since max_background_jobs defaults to 2. Lower the write amplification, which the Sum row's W-Amp measures. Or lower the write rate at the source, or use a faster device. A bigger L0 trigger only delays the stop and raises read amplification. A rate_limiter set too low makes the stalls worse.

- Show the arithmetic. You need a Bloom filter for 500 million keys at an FPR of 0.1%. Compute the bits per key and the memory with the textbook formula. Then compute the memory with RocksDB's figure of 15.5 bits per key for 0.1%. What does each 4.8 more bits per key buy?Answer sketch
Bits per key = −ln(0.001) / (ln 2)² = 6.908 / 0.4805 = 14.4. Memory = 500,000,000 × 14.4 / 8 = 900 MB. With RocksDB's 15.5 bits: 500,000,000 × 15.5 / 8 = 969 MB. Each 4.8 more bits per key divides the FPR by 10, because 0.6185^4.8 = 0.1. So 1% needs 9.6 bits, 600 MB, and 0.01% needs 19.2 bits, 1.2 GB.

- Given these constraints, design. A PostgreSQL server has 16 GB of shared_buffers. Its OLTP hot set is about 10 GB. Each night a report reads most of a 60 GB table, filtered by a date range. A colleague wants to raise shared_buffers to 64 GB "so the report fits". Explain what protects the hot set, when it does not, and what the larger setting would change. Then say what you would measure the next morning. Then answer the same question for MySQL with InnoDB, and name the setting that matters there.Answer sketch
Read the report's plan first. If it is a Seq Scan, PostgreSQL reads a table larger than a quarter of shared_buffers through a small ring. Then the report does not flood the pool. The ring is 256 kB in versions 14 to 17. The arithmetic of the 18 code gives about 752 kB. Its pages get a usage count of at most 1. At 64 GB, a quarter is 16 GB, so the 60 GB table still uses the ring. But a date filter often gives a Bitmap Heap Scan, and an Index Scan is also possible. Neither uses a ring. So either can push the 10 GB hot set out of 16 GB of shared_buffers. The morning's reads then miss. A 64 GB pool would leave room for the hot set and much of the report. But it takes that memory from the OS page cache, which every miss goes through. That trade is inferred. Measure the next morning: EXPLAIN (ANALYZE, BUFFERS) of the report, and the hit rate of the hot tables in pg_statio_user_tables beside iostat. On 16 or later, read the bulkread rows of pg_stat_io. Run pg_buffercache_usage_counts() and the per-relation query of section 2.1 in the evening and in the morning, to see which table took the pool. With InnoDB, the report's pages enter the old sublist at the midpoint. innodb_old_blocks_time, 1000 ms by default, keeps a page read several times in quick succession from moving to the young part. Keep it above 0.

- Show the arithmetic. An index holds a billion 8-byte keys, with the layout of section 2.2. The server's buffer pool has 4 GB for it. Lookups are uniform over all keys, at 20,000 per second. Compute the height, the memory above the leaves, and the leaves' total size. Then compute the hit rate on leaves, and the device time per second at 89 µs per miss. Does one SSD with one queue keep up?Answer sketch
Height 4, and 9,622 pages above the leaves, about 75 MiB, from section 2.2. Leaves: 2,732,241 × 8 KiB = about 20.8 GiB. The inner pages fit in the 4 GB, which leaves about 3.9 GB for leaves. Hit rate on leaves = 3.9 / 20.8 = about 19%, so 81% miss. Device time: 20,000 × 0.81 × 89 µs = 1.44 s per second. That is more than one device's second, so one SSD with one queue cannot keep up. If the query needs the row, PostgreSQL also reads the heap page that the TID names. The heap is at least as large as the index, so its pages miss at least as often. That is inferred. Then the device time is at least 2 × 1.44 = 2.9 s per second. An index-only scan, Phase 4, section 4.3, can skip the heap read. In InnoDB, a primary-key lookup ends at the leaf that holds the row. Real SSDs serve many reads in parallel, which this model does not include. Measure the device's throughput at your queue depth before you buy memory or disks.

### Part B: managed PostgreSQL, the pool from inside, vectors and columns

Part B tests the real-systems parts of sections 2.1, 2.2, 2.7, 2.8 and the new section 2.9.

- Show the arithmetic, on managed PostgreSQL. Your service moves from PostgreSQL 17 on a VM with 64 GB of memory to Aurora PostgreSQL with 64 GB. On the VM, shared_buffers was 16 GB, its hit rate was 99%, and most misses found the page cache at 1.5 µs. A colleague sets shared_buffers to 16 GB on Aurora too, "because 25% is the rule". (a) What does Aurora's default give, and why does the rule not hold there? (b) Keep the 99% hit rate, and take 1 ms per storage read as an example. How much do the misses add to the average read, against the VM? (c) Which two metrics and which wait event do you watch in the first week?Answer sketch
(a) AWS calls it about 75% of memory. The formula gives about 68% of DBInstanceClassMemory, minus about 390 MiB, so at most about 43 GiB on 64 GiB. AWS sets SUM({DBInstanceClassMemory/12038},-50003), because Aurora has "no file system or secondary level of caching for tables or indexes". So the page cache that caught the VM's misses does not exist. A 16 GB pool is less than half of the default. AWS's own test at 15% of memory lost 14% of throughput and added 14% to the volume read I/O. (b) VM: 0.01 × 1.5 = 0.015 µs per read. Aurora, still at 99%: 0.01 × 1,000 = 10 µs, about 670 times more. The hit rate is also likely to fall with less than half of the pool, which is inferred. (c) BufferCacheHitRatio and VolumeReadIOPs in CloudWatch, and IO:DataFileRead in Performance Insights. On Aurora Standard the read count is also on the I/O bill.

- Given these constraints, design. An agent memory table on RDS for PostgreSQL 17.11 holds 4 million embeddings of 1,536 dimensions, with an HNSW index. The instance has 32 GB of memory and default parameters. (a) Compute the value size, where the value is stored, and the index size. (b) Does the index fit in shared_buffers? What does a search pay when it does not? (c) What does a rebuild of the index need in memory, and what does it write to the WAL? (d) Propose two changes, and say what each gives up. (e) Which version check do you run first, and why?Answer sketch
(a) 4 × 1,536 + 8 = 6,152 bytes. The row is 6,184 bytes, over 2,032, so the value goes to TOAST in 4 chunks, and the heap row keeps 50 bytes. HNSW at one element per page: at least 4,000,001 pages, 30.5 GiB, from vector_storage.py --rows 4000000. (b) RDS gives shared_buffers 25% of DBInstanceClassMemory, a little under 8 GiB. The index needs at least 30.5 GiB, about 95% of the instance's 32 GiB, so most of it stays out of the pool. Each graph step can read up to 32 element pages. So one search can pay hundreds of reads of about 1 ms on gp3. That count is inferred from section 2.9. (c) The graph needs at least 26.7 GB. The RDS default maintenance_work_mem is 64 MB by one AWS page and about 500 MB on this instance by another, so check it. Either way the build prints the notice and runs slowly. It ends by writing about 24 GiB of WAL, the page images without their free space, which every replica replays, Phase 5, section 5.1. Both sizes are inferred. (d) An HNSW index on embedding::halfvec(1536): 2 per page, at least 15.3 GiB, at the price of half-precision distances. Or binary_quantize to bit with re-ranking: 17 per page, at least about 1.8 GiB, at the price of recall and extra TOAST reads to re-rank. Test recall first, as the retrieval-internals course does. Partitioning by tenant or time also makes each index smaller, Phase 4, section 4.6. (e) select extversion from pg_extension where extname = 'vector', because RDS 17.11 lists 0.8.2, which is older than the HNSW vacuum fixes of 0.8.3 and 0.8.4, the IVFFlat memory check of 0.8.4 and the IVFFlat overflow fix of 0.8.7.

- This is broken. Each night a job deletes the embeddings of deleted documents, about 30% of 2 million rows. Since then, autovacuum on items runs for hours, and the HNSW index never gets smaller. What is the cause, and how would you confirm it? What would you change in the design?Answer sketch
Cause: HNSW's VACUUM does four passes over the index, and its repair pass runs a graph search for every element that lost neighbours. 30% of 2 million is 600,000 deleted elements, so many survivors need repair. The index keeps its size because deleted slots are reused by inserts, not returned to the file system. Check: pg_stat_progress_vacuum shows the phase and the dead items. On 17 the columns are dead_tuple_bytes and num_dead_item_ids, at system_views.sql lines 1223 to 1224, REL_17_11. pg_stat_activity shows the autovacuum worker and its wait events. VACUUM VERBOSE prints the index's page line, with 0 reusable pages, which is inferred from the code. extversion shows whether you have the 0.8.3 and 0.8.4 vacuum fixes. The README's advice is REINDEX INDEX CONCURRENTLY, then VACUUM. Design: this is the queue shape of section 2.4. Partition the table by time or by tenant, so that a whole partition and its index can be dropped instead of deleted row by row. That design is inferred from sections 2.4 and 2.9.

- A colleague says: "The finance dashboard sums amount over all 50 million orders every minute. Let's raise shared_buffers until the orders table fits." The rows are the running case's orders, about 6 to a heap page. Argue for or against, with numbers. Which structure fits this query?Answer sketch
Against. The table is 50,000,000 / 6 = 8,333,334 heap pages, about 68 GB. A Seq Scan of a table larger than a quarter of shared_buffers uses the 256 kB ring, section 2.8. So the pool would need more than 4 × 68 = 273 GB before the scan stops using the ring and keeps its pages. Each minute the dashboard reads 68 GB, which is about 1.1 GB per second of reads. A column store reads 50,000,000 × 8 bytes = 400 MB of amount, about 170 times less, before compression. Better still, a summary table that the order path keeps up to date, so the dashboard reads one row. Measure the bytes per run with EXPLAIN (ANALYZE, BUFFERS).

- Walk through what happens when you look for the cause of a slow morning on RDS for PostgreSQL 17. You have SQL access only. Last night a batch job ran, and since then the hit rate of the orders tables is low. Name the three views or functions you query, the query for each, and what each result would show if the batch job flooded the pool.Answer sketch
First pg_buffercache: the per-relation query of section 2.1 shows which relations hold the most buffers now. If the batch job's table holds a large share, it took the pool. pg_buffercache_usage_counts() shows many buffers at count 1 or 0, which pages used once leave. Second pg_stat_statements, ordered by shared_blks_read: the batch job's statement leads, with a high miss_pct. Third pg_stat_io: if its reads sit in context normal, not bulkread, the job did not use a ring. Its plan was then an Index Scan or a Bitmap Heap Scan, section 2.8. Confirm with EXPLAIN (ANALYZE, BUFFERS) of that statement. In Performance Insights the morning shows IO:DataFileRead waits, and the per-statement metric db.sql_tokenized.stats.shared_blks_read_per_sec points at the same statement. The reading is inferred from sections 2.1 and 2.8.

## Cheatsheet

Open the cheatsheet
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

## Sources

Open the sources
This course's research fetched the first URLs below on 2026-10-17, and the depth revision added more on 2026-10-18. The PostgreSQL 17 revision of 2026-10-20 fetched every new entry, and check_urls.py checked all of them again on 2026-10-20. Primary sources come first in each group.

### The original designs

- The Log-Structured Merge-Tree, O'Neil, Cheng, Gawlick and O'Neil, Acta Informatica. https://www.cs.umb.edu/~poneil/lsmtree.pdf Focus on: section 3 only, Equations 3.2 to 3.4, Theorem 3.1, and Examples 3.3 and 3.4. The cost model uses 1995 disk prices, so read the ratios, not the dollars. The PDF says "To be published", and the volume and year were not checked. Read it before section 2.3.

- Space/Time Trade-offs in Hash Coding with Allowable Errors, Burton Bloom, Communications of the ACM, 1970. https://people.cs.umass.edu/~emery/classes/cmpsci691st/readings/Misc/p422-bloom.pdf Focus on: "Analysis of Method 2", equations 16 and 17, and the half-full result on page 426. A course mirror, not the publisher's copy. The last row of Table I looks like a typo, so do not use it.

- 2Q: A Low Overhead High Performance Buffer Management Replacement Algorithm, Johnson and Shasha, VLDB 1994. https://www.vldb.org/conf/1994/P439.PDF Focus on: section 2, "2Q, Full Version", with the pseudocode on page 441, and Tables 1 to 4. A scanned PDF. The tables were read from page images, and the text from OCR.

- ARC: A Self-Tuning, Low Overhead Replacement Cache, Megiddo and Modha, USENIX FAST 2003. https://www.usenix.org/legacy/events/fast03/tech/full_papers/megiddo/megiddo.pdf Focus on: Figure 4 for the algorithm, and Table VI for the trace with long scans. In Tables IV and V, 2Q has offline-tuned parameters. Read it after 2Q.

- Bitcask: A Log-Structured Hash Table for Fast Key/Value Data, Sheehy and Smith, Basho, 2010. https://riak.com/assets/bitcask-intro.pdf Focus on: page 4, merge and the hint file figure. A company paper, not peer reviewed. Phase 1 used its pages 2 to 5.

### Amplification

- Designing Access Methods: The RUM Conjecture, Athanassoulis and others, EDBT 2016. https://openproceedings.org/2016/conf/edbt/paper-12.pdf Focus on: section 2 for the three definitions, and section 3 with Figure 1 for the conjecture. Table 1 gives asymptotic costs. Short. The conjecture is not proved.

- Monkey: Optimal Navigable Key-Value Store, Dayan, Athanassoulis and Idreos, SIGMOD 2017. https://cs-people.bu.edu/mathan/publications/sigmod17-dayan.pdf Focus on: Equation 2 in section 3, the allocation in section 4.1, and Figure 11. Built on LevelDB, not RocksDB. The tests used a spinning disk with the block cache off, a worst case. Appendix F, with a cache, was not read for this course.

- Optimizing Space Amplification in RocksDB, Dong and others, CIDR 2017. https://www.cidrdb.org/cidr2017/papers/p82-dong-cidr17.pdf Focus on: section 3 for B-tree page fill and the LSM bound of 1.111. Section 5 with Figure 3 covers LinkBench. The authors work at Facebook.

- InnoDB, MyRocks and TokuDB on the insert benchmark, Mark Callaghan, Small Datum, 2017. https://smalldatum.blogspot.com/2017/05/innodb-myrocks-and-tokudb-on-insert.html Focus on: the "Fast SSD" tables, columns wkb/i and size. Insert-only, and the hardware is in an earlier post. The author's reply under the post says the primary key is inserted in order and the secondary indexes at random.

- On the impact of full-page writes, Tomas Vondra, EDB blog, 2016. https://www.enterprisedb.com/blog/impact-full-page-writes Focus on: "UUID vs. BIGSERIAL keys", about 2 GB against more than 40 GB of WAL in one hour at 5,000 inserts per second. The text gives no version, hardware or checkpoint settings, and the charts are images.

- Read, write & space amplification - pick 2, Mark Callaghan, Small Datum, 2015. https://smalldatum.blogspot.com/2015/11/read-write-space-amplification-pick-2_23.html Focus on: the definitions. No numbers. A short read before section 2.6.

### PostgreSQL source, tag REL_17_11, and docs

- PostgreSQL 14 Internals, Egor Rogov, Postgres Professional, 2023. https://edu.postgrespro.com/postgresql_internals-14_en.pdf Focus on: chapter 3, pages 62 to 66, for pages, line pointers and TIDs. Chapter 9, sections 9.1 and 9.5, for buffered I/O and the rings. Chapter 25, pages 425 to 431, for a real B-tree page, no merging and deduplication. The PDF prints digits as special glyphs. The book is about 14. This phase checks each fact it uses against 17.

- PostgreSQL 17.0 release notes. https://www.postgresql.org/docs/release/17.0/ Focus on: buffers_backend removed from pg_stat_bgwriter, pg_stat_checkpointer, io_combine_limit and streaming reads, vacuum_buffer_usage_limit at 2MB, the rename to shared_blk_read_time, and pg_buffercache_evict().

- tableam.h. https://github.com/postgres/postgres/blob/REL_17_11/src/include/access/tableam.h Focus on: table_beginscan_bm at lines 959 to 967, which asks for no ring.

- nbtxlog.h. https://github.com/postgres/postgres/blob/REL_17_11/src/include/access/nbtxlog.h Focus on: lines 90 to 95, what a split's WAL record holds.

- nbtree README. https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/nbtree/README Focus on: "Deleting entire pages during VACUUM" at lines 232 to 240, and "Placing deleted pages in the FSM" at line 383. They correct the belief that an index needs regular rebuilds.

- itup.h. https://github.com/postgres/postgres/blob/REL_17_11/src/include/access/itup.h Focus on: IndexTupleData at lines 35 to 51, the 8-byte index tuple header with its heap TID.

- heaptoast.h. https://github.com/postgres/postgres/blob/REL_17_11/src/include/access/heaptoast.h Focus on: lines 23 to 26 and 46 to 48 for the 2,032-byte threshold, and 84 to 89 for the 1,996-byte chunk.

- postgresql.conf.sample. https://github.com/postgres/postgres/blob/REL_17_11/src/backend/utils/misc/postgresql.conf.sample Focus on: shared_buffers at line 129, maintenance_work_mem at 142, vacuum_buffer_usage_limit at 160 and subtransaction_buffers at 170. Then effective_io_concurrency at 209, io_combine_limit at 211, wal_compression at 243, checkpoint_timeout at 258, max_wal_size at 262 and track_io_timing at 645.

- system_views.sql. https://github.com/postgres/postgres/blob/REL_17_11/src/backend/catalog/system_views.sql Focus on: pg_stat_bgwriter, pg_stat_checkpointer and pg_stat_io at lines 1134 to 1173, and pg_stat_progress_vacuum at 1223 to 1224. They show which columns exist on 17.

- vacuumlazy.c. https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/heap/vacuumlazy.c Focus on: line 726, the per-index line of VACUUM VERBOSE and of the autovacuum log.

- hio.c. https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/heap/hio.c Focus on: lines 520 and 532 to 536, the row is too big check.

- detoast.c. https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/common/detoast.c Focus on: toast_datum_size at lines 601 to 616, which explains what pg_column_size returns for a TOASTed value.

- 65.6 Database Page Layout, PostgreSQL 17. https://www.postgresql.org/docs/17/storage-page-layout.html Focus on: Table 65.2 and section 65.6.1: the 24-byte page header, the 4-byte line pointer and the 23-byte tuple header.

- 27.2 The Cumulative Statistics System, PostgreSQL 17. https://www.postgresql.org/docs/17/monitoring-stats.html Focus on: section 27.2.2 on the kernel page cache, 27.2.13 for pg_stat_io with its contexts and reuses, and n_tup_newpage_upd.

- 28.2 The Statistics Collector, PostgreSQL 14. https://www.postgresql.org/docs/14/monitoring-stats.html Focus on: Table 28.21, for the 14 pg_stat_bgwriter columns that 17 removed. Read only if you still run 14.

- F.25 pg_buffercache, PostgreSQL 17. https://www.postgresql.org/docs/17/pgbuffercache.html Focus on: pg_buffercache_usage_counts(), the access rule, and the per-relation sample query.

- F.30 pg_stat_statements, PostgreSQL 17. https://www.postgresql.org/docs/17/pgstatstatements.html Focus on: shared_blks_read, shared_blk_read_time, wal_fpi, and the shared_preload_libraries rule.

- F.28 pg_prewarm, PostgreSQL 17. https://www.postgresql.org/docs/17/pgprewarm.html Focus on: the autoprewarm worker that reloads the pool after a restart.

- F.23 pageinspect, PostgreSQL 17. https://www.postgresql.org/docs/17/pageinspect.html Focus on: bt_metap, bt_page_stats and bt_page_items. Superusers only.

- F.31 pgstattuple, PostgreSQL 17. https://www.postgresql.org/docs/17/pgstattuple.html Focus on: pgstatindex, with leaf_pages, empty_pages, deleted_pages and avg_leaf_density.

- 64.1 B-Tree Indexes, PostgreSQL 17. https://www.postgresql.org/docs/17/btree.html Focus on: section 64.1.4.2, bottom-up deletion, and 64.1.4.3, deduplication.

- 65.2 TOAST, PostgreSQL 17. https://www.postgresql.org/docs/17/storage-toast.html Focus on: the 2 kB threshold, the chunk size, the four strategies, and the UPDATE rule.

- ALTER TABLE, PostgreSQL 17. https://www.postgresql.org/docs/17/sql-altertable.html Focus on: SET STORAGE, which changes only future writes.

- CREATE TABLE, PostgreSQL 17. https://www.postgresql.org/docs/17/sql-createtable.html Focus on: the table fillfactor, default 100.

- F.6 bloom and 64.5 BRIN Indexes, PostgreSQL 17. https://www.postgresql.org/docs/17/bloom.html Focus on: the first paragraph. Read with https://www.postgresql.org/docs/17/brin.html for the bloom operator classes.

- PostgreSQL 12.0 release notes. https://www.postgresql.org/docs/release/12.0/ Focus on: B-tree indexes with many duplicates.

- PostgreSQL 13.0 release notes. https://www.postgresql.org/docs/release/13.0/ Focus on: deduplication, and gen_random_uuid() in core.

- PostgreSQL 14.0 release notes. https://www.postgresql.org/docs/release/14.0/ Focus on: B-tree additions that remove expired entries, which the docs call bottom-up deletion.

- PostgreSQL 16.0 release notes. https://www.postgresql.org/docs/release/16.0/ Focus on: pg_stat_io, n_tup_newpage_upd, and HOT with BRIN.

- PostgreSQL 18.0 release notes. https://www.postgresql.org/docs/release/18.0/ Focus on: uuidv7(), asynchronous I/O, and checksums on by default.

- freelist.c. https://github.com/postgres/postgres/blob/REL_17_11/src/backend/storage/buffer/freelist.c Focus on: the clock sweep at lines 314 to 353, GetAccessStrategy at 541 to 573, and the ring reuse rule at line 727. In tag REL_19_RC1 the free list is gone and the sweep uses one atomic compare-and-swap. The cap is still 5. Version 19 is a release candidate.

- freelist.c at REL_18_6. https://github.com/postgres/postgres/blob/REL_18_6/src/backend/storage/buffer/freelist.c Focus on: lines 557 to 601, the ring that 18 sizes from the pin limit. Only for the 18 line of section 2.8.

- bufmgr.c. https://github.com/postgres/postgres/blob/REL_17_11/src/backend/storage/buffer/bufmgr.c Focus on: the usage count rule at lines 2703 to 2713, and the WAL flush in FlushBuffer at lines 3909 to 3927.

- Buffer manager README. https://github.com/postgres/postgres/blob/REL_17_11/src/backend/storage/buffer/README Focus on: line 218, the 256 kB ring for sequential scans.

- buf_internals.h. https://github.com/postgres/postgres/blob/REL_17_11/src/include/storage/buf_internals.h Focus on: BM_MAX_USAGE_COUNT and the comment above it, lines 72 to 79.

- nbtree.h. https://github.com/postgres/postgres/blob/REL_17_11/src/include/access/nbtree.h Focus on: BTPageOpaqueData at lines 62 to 69, and the fill factors at lines 189 to 202.

- bufpage.h. https://github.com/postgres/postgres/blob/REL_17_11/src/include/storage/bufpage.h Focus on: the slotted page drawing at lines 29 to 42, and PageHeaderData.

- heapam.c. https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/heap/heapam.c Focus on: lines 445 to 452, where a scan of a table larger than a quarter of shared_buffers gets the ring. Lines 2218 to 2222 log the first insert on a fresh page with no page image. Line 2359 tests the TOAST threshold.

- nbtinsert.c. https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/nbtree/nbtinsert.c Focus on: lines 1978 to 1990, the pages a split registers in its WAL record.

- 19.4 Resource Consumption, PostgreSQL 17. https://www.postgresql.org/docs/17/runtime-config-resource.html Focus on: shared_buffers, its default and the 25% and 40% advice.

- 65.7 Heap-Only Tuples, PostgreSQL 17. https://www.postgresql.org/docs/17/storage-hot.html Focus on: the two conditions. Read it with the Uber post.

- CREATE INDEX, PostgreSQL 17. https://www.postgresql.org/docs/17/sql-createindex.html Focus on: fillfactor for B-trees, default 90, and deduplicate_items, default on.

- PostgreSQL 8.0.2 release notes. https://www.postgresql.org/docs/release/8.0.2/ Focus on: "New cache management algorithm 2Q replaces ARC", done "to avoid a pending US patent on ARC". History, not needed for the lessons.

- PostgreSQL 8.1.0 release notes. https://www.postgresql.org/docs/release/8.1.0/ Focus on the line: "The buffer manager has also been changed to use a "clock sweep" replacement policy." With the 8.0.2 notes, it shows two replacements. First 2Q replaced ARC, and then the clock sweep replaced 2Q. History, not needed for the lessons.

### Managed PostgreSQL and cloud storage

All AWS pages were fetched on 2026-10-20. They are vendor sources.

- Amazon Aurora PostgreSQL parameters, Part 1: Memory and query plan management, Kumar and Subramanian, AWS Database Blog, 2021-04-12. https://aws.amazon.com/blogs/database/amazon-aurora-postgresql-parameters-part-1-memory-and-query-plan-management/ Focus on: the shared_buffers section: no file system cache, the 75% formula, the pgbench test at 15%, and the volume read I/O. Also the line that Aurora keeps the pool through restarts.

- RDS for PostgreSQL memory, Amazon RDS User Guide. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Tuning.concepts.memory.html Focus on: the {DBInstanceClassMemory/32768} default, and the 64 MB maintenance_work_mem.

- Amazon RDS DB instance storage. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Storage.html Focus on: the two storage types, and the gp3 table for PostgreSQL: 3,000 IOPS below 400 GiB, 12,000 to 64,000 from 400 GiB.

- Working with parameters on RDS for PostgreSQL. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Parameters.html Focus on: "the default PostgreSQL units for all parameters", and shared_buffers in 8 KB.

- Aurora PostgreSQL Optimized Reads. https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.optimized.reads.html Focus on: the tiered cache on local NVMe, and which instances and clusters get it.

- Amazon Aurora pricing. https://aws.amazon.com/rds/aurora/pricing/ Focus on: Aurora Standard, billed per I/O, against I/O-Optimized, with no I/O charge.

- Amazon Aurora metrics. https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.AuroraMonitoring.Metrics.html Focus on: VolumeReadIOPs, billed read I/O per 5 minutes, and BufferCacheHitRatio.

- Autovacuum memory on RDS for PostgreSQL. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Autovacuum.html Focus on: the maintenance_work_mem default formula, which differs from the memory page's 64 MB.

- Amazon EBS General Purpose SSD volumes. https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html Focus on: gp3 latency, the 3,000 IOPS baseline, and 500 IOPS per GiB up to 80,000.

- Amazon EBS Provisioned IOPS SSD volumes. https://docs.aws.amazon.com/ebs/latest/userguide/provisioned-iops.html Focus on: io2 Block Express, under 500 microseconds for 16 KiB.

- IO:DataFileRead, Aurora PostgreSQL wait events. https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/apg-waits.iodatafileread.html Focus on: the context and the likely causes. The RDS page of the same name is at https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/wait-event.iodatafileread.html

- SQL statistics for RDS PostgreSQL, Performance Insights. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PerfInsights.UsingDashboard.AnalyzeDBLoad.AdditionalMetrics.PostgreSQL.html Focus on: pg_stat_statements loaded by default from 11, and the shared_blks_read metric names.

- Parameter groups for Amazon RDS. https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/parameter-groups-overview.html Focus on: static parameters need a reboot, and default groups cannot be changed.

- Extension versions for Amazon RDS for PostgreSQL. https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html Focus on: the PostgreSQL 17 table: pg_buffercache 1.5 and pgvector 0.8.2 on 17.11. The table changes with each release.

### pgvector, tag v0.8.7

- pgvector README. https://github.com/pgvector/pgvector/blob/v0.8.7/README.md Focus on: "Index Build Time" for HNSW, the IVFFlat lists rule, "Storing", "Approximate Search", "Vacuuming", the FAQ on parallel scans and SET STORAGE PLAIN, and the value sizes of each type.

- pgvector CHANGELOG. https://github.com/pgvector/pgvector/blob/v0.8.7/CHANGELOG.md Focus on: 0.8.3 and 0.8.4, the HNSW vacuum fixes.

- hnsw.h. https://github.com/pgvector/pgvector/blob/v0.8.7/src/hnsw.h Focus on: lines 54 and 69 for m and the heap TIDs, 81 to 82 for the tuple sizes, and 364 to 393 for the page and tuple structs.

- hnswbuild.c. https://github.com/pgvector/pgvector/blob/v0.8.7/src/hnswbuild.c Focus on: the comment at lines 1 to 35, the placement loop at 192 to 229, the notice at 533 to 545, and log_newpage_range at 1142 to 1143.

- hnswvacuum.c. https://github.com/pgvector/pgvector/blob/v0.8.7/src/hnswvacuum.c Focus on: the four passes at lines 785 to 792, the ring at line 747, and the zeroed vector at line 688.

- hnswutils.c. https://github.com/pgvector/pgvector/blob/v0.8.7/src/hnswutils.c Focus on: line 546, where each element is read from its page, and lines 891 to 933, the neighbours a search step loads.

- hnsw.c and ivfflat.c. https://github.com/pgvector/pgvector/blob/v0.8.7/src/hnsw.c Focus on: ampredlocks = false at line 348. The same flag is at line 265 of https://github.com/pgvector/pgvector/blob/v0.8.7/src/ivfflat.c

- sql/vector.sql. https://github.com/pgvector/pgvector/blob/v0.8.7/sql/vector.sql Focus on: STORAGE = external for vector at line 39 and for halfvec at line 483.

- ivfbuild.c. https://github.com/pgvector/pgvector/blob/v0.8.7/src/ivfbuild.c Focus on: the centres and samples at lines 400 and 456 to 466. Read with ivfutils.c lines 126 to 133 and 166, at https://github.com/pgvector/pgvector/blob/v0.8.7/src/ivfutils.c

### RocksDB source, tag v11.8.1, and wiki

- advanced_options.h. https://github.com/facebook/rocksdb/blob/v11.8.1/include/rocksdb/advanced_options.h Focus on: the L0 triggers at lines 547 and 554, and the fanout at line 671. The pending-bytes limits are at lines 709 and 717, compaction_pri at 725, and optimize_filters_for_hits at 816.

- options.h. https://github.com/facebook/rocksdb/blob/v11.8.1/include/rocksdb/options.h Focus on: write_buffer_size at line 191, level0_file_num_compaction_trigger at line 255, and delayed_write_rate at lines 1367 to 1383. Then rate_limiter at 734, max_open_files at 776, use_direct_reads at 1153 and stats_dump_period_sec at 1217.

- column_family.cc. https://github.com/facebook/rocksdb/blob/v11.8.1/db/column_family.cc Focus on: GetWriteStallConditionAndCause, lines 1011 to 1046, for the order of the stall checks. The LOG format strings follow, at lines 1072 to 1159.

- filter_policy.h. https://github.com/facebook/rocksdb/blob/v11.8.1/include/rocksdb/filter_policy.h Focus on: lines 140 to 149 on bits per key, and 169 to 173 on Ribbon filters.

- table.h. https://github.com/facebook/rocksdb/blob/v11.8.1/include/rocksdb/table.h Focus on: cache_index_and_filter_blocks at line 238, partition_filters at line 519, and block_align at line 772, all false by default. The lab's runs align their blocks as block_align does.

- RocksDB wiki: Compaction. https://github.com/facebook/rocksdb/wiki/Compaction Focus on: "Classic Leveled" and "Tiered", for write amplification per level. The wiki has no release tag, so it may change.

- RocksDB wiki: RocksDB Tuning Guide. https://github.com/facebook/rocksdb/wiki/RocksDB-Tuning-Guide Focus on: the worked example with write amplification 33 and space 1.14, and max_size_amplification_percent.

- RocksDB wiki: Write Stalls. https://github.com/facebook/rocksdb/wiki/Write-Stalls Focus on: the causes and log lines. Its option names differ from the source, as section 2.4 says.

- RocksDB wiki: RocksDB Bloom Filter. https://github.com/facebook/rocksdb/wiki/RocksDB-Bloom-Filter Focus on: the bits-per-key list, and the cache-local arithmetic that gives 0.95%.

- RocksDB wiki: Leveled Compaction. https://github.com/facebook/rocksdb/wiki/Leveled-Compaction Focus on: dynamic level sizes, with 90% of the data in the last level.

- RocksDB wiki: Compaction Stats and DB Status. https://github.com/facebook/rocksdb/wiki/Compaction-Stats-and-DB-Status Focus on: the example table and the column list, especially Score, W-Amp and Stall(sec). No version is given for the example.

- RocksDB wiki: Rate Limiter. https://github.com/facebook/rocksdb/wiki/Rate-Limiter Focus on: rate_bytes_per_sec, and what the limiter does not cover.

- RocksDB wiki: Implement Queue Service Using RocksDB. https://github.com/facebook/rocksdb/wiki/Implement-Queue-Service-Using-RocksDB Focus on: "Old Item Deletion Problem", and iterate_upper_bound.

- RocksDB wiki: DeleteRange. https://github.com/facebook/rocksdb/wiki/DeleteRange Focus on: one range tombstone in place of a scan and many deletes.

- RocksDB wiki: Single Delete. https://github.com/facebook/rocksdb/wiki/Single-Delete Focus on: the condition that a key was written once.

- RocksDB wiki: Partitioned Index Filters. https://github.com/facebook/rocksdb/wiki/Partitioned-Index-Filters Focus on: the index and filter sizes per run, and the two benchmarks. They date from about RocksDB 5.x.

- RocksDB wiki: Block Cache. https://github.com/facebook/rocksdb/wiki/Block-Cache Focus on: the 32 MB default, uncompressed blocks, and index and filter blocks outside the cache.

- RocksDB wiki: Prefix Seek. https://github.com/facebook/rocksdb/wiki/Prefix-Seek Focus on: "Why Prefix Seek?", the prefix Bloom filter for ranges.

- MyRocks wiki: Read Free Replication. https://github.com/facebook/mysql-5.6/wiki/Read-Free-Replication Focus on: the first two paragraphs, on GetForUpdate() before each write, and the last note on the primary.

- RocksDB wiki: Universal Compaction. https://github.com/facebook/rocksdb/wiki/Universal-Compaction Focus on: "Compaction Triggered by Space Amplification", and the temporary doubling of space. Its write amplification example of 9 is called "a wild unproven estimation" by the page itself.

### InnoDB

- Clustered and Secondary Indexes, MySQL 8.4 manual. https://dev.mysql.com/doc/refman/8.4/en/innodb-index-types.html Focus on: the clustered index holds the rows, and each secondary record holds the primary key.

- The Physical Structure of an InnoDB Index, MySQL 8.4 manual. https://dev.mysql.com/doc/refman/8.4/en/innodb-physical-structure.html Focus on: page fill after random and sequential inserts, and MERGE_THRESHOLD.

- Doublewrite Buffer, MySQL 8.4 manual. https://dev.mysql.com/doc/refman/8.4/en/innodb-doublewrite-buffer.html Focus on: the first paragraph. Phase 1, section 1.4, used the same page.

- The InnoDB Buffer Pool, MySQL 8.4 manual. https://dev.mysql.com/doc/refman/8.4/en/innodb-buffer-pool.html Focus on: the old and young sublists, and the midpoint.

- Making the Buffer Pool Scan Resistant, MySQL 8.4 manual. https://dev.mysql.com/doc/refman/8.4/en/innodb-performance-midpoint_insertion.html Focus on: innodb_old_blocks_pct and innodb_old_blocks_time.

- ha_innodb.cc, tag mysql-8.4.11. https://github.com/mysql/mysql-server/blob/mysql-8.4.11/storage/innobase/handler/ha_innodb.cc Focus on: lines 23017 to 23027, the two defaults and their ranges.

- What Is New in MySQL 8.4 since MySQL 8.0, MySQL 8.4 manual. https://dev.mysql.com/doc/refman/8.4/en/mysql-nutshell.html Focus on: Table 1.1 of changed InnoDB defaults: innodb_change_buffering, innodb_adaptive_hash_index and innodb_io_capacity.

- Change Buffer, MySQL 8.4 manual. https://dev.mysql.com/doc/refman/8.4/en/innodb-change-buffer.html Focus on: the first three paragraphs, and the warning about long merges.

- Adaptive Hash Index, MySQL 8.4 manual. https://dev.mysql.com/doc/refman/8.4/en/innodb-adaptive-hash.html Focus on: when it helps, and the contention warning.

### Production reports

- Faster bulk-data loading in CockroachDB, Akhtar and Taylor, Cockroach Labs, 2020. https://www.cockroachlabs.com/blog/bulk-data-import/ Focus on: the giant L0 compaction, the 847 runs in 13 sublevels, and the import times with their hardware.

- Here's how CockroachDB keeps your database from collapsing under load, Sumeer Bhola, Cockroach Labs, 2022. https://www.cockroachlabs.com/blog/admission-control-in-cockroachdb/ Focus on: the read amplification threshold of 20, and the overload at 1,000. The latency graphs give no workload or hardware.

- How Discord Stores Trillions of Messages, Bo Ingram, Discord, 2023. https://discord.com/blog/how-discord-stores-trillions-of-messages Focus on: the compaction and tombstone problems, and the p99 numbers before and after. The date comes from the page and was not checked separately.

- Open-sourcing a 10x reduction in Apache Cassandra tail latency, Dikang Gu, Instagram, 2018. https://web.archive.org/web/20221221164348/https://instagram-engineering.com/open-sourcing-a-10x-reduction-in-apache-cassandra-tail-latency-d64f86b43589 Focus on: which number the "10x" is, and the production p99. An archived copy, because the live site refused the connection.

- Why Uber Engineering Switched from Postgres to MySQL, Evan Klitzke, Uber, 2016. https://www.uber.com/blog/postgres-to-mysql-migration/ Focus on: the write amplification argument. No measured byte counts, and the example changes an indexed column.

- MyRocks: A space- and write-optimized MySQL database, Yoshinori Matsunobu, Facebook, 2016. https://engineering.fb.com/2016/08/31/core-infra/myrocks-a-space-and-write-optimized-mysql-database/ Focus on: the LinkBench size results, and the fixed compressed page size. The write results are only in a chart image.

- GitHub availability this week, Jesse Newland, GitHub, 2012-09-14. https://github.blog/news-insights/the-library/github-availability-this-week/ Focus on: the failover to a server with a cold InnoDB buffer pool, and the failback it caused.

- From Zero to 50 Million Uploads per Day: Scaling Media at Canva, Chen and Sharp, Canva, 2022-11-29. https://www.canva.dev/blog/engineering/from-zero-to-50-million-uploads-per-day-scaling-media-at-canva/ Focus on: the list of MySQL on RDS limits, including the hot buffer pool.

- Roblox Return to Service 10/28-10/31 2021, Roblox, 2022. https://about.roblox.com/newsroom/2022/01/roblox-return-to-service-10-28-10-31-2021 Focus on: the BoltDB section: a file that never shrinks, the freelist, and the 4.2 GB file with 489 MB of data.

- How Stripe's document databases supported 99.999% uptime with zero-downtime data migrations, Morzaria and Narkhede, Stripe, 2024-06-06. https://stripe.dev/blog/how-stripes-document-databases-supported-99.999-uptime-with-zero-downtime-data-migrations Focus on: the bulk import step, where sorted inserts raised write throughput 10 times.

- How Instacart Built a Modern Search Infrastructure on Postgres, Mittal and others, Instacart, 2025-05-29. https://company.instacart.com/tech-innovation/how-instacart-built-a-modern-search-infrastructure-on-postgres Focus on: "ANN Index Design in Postgres", with inline storage instead of TOAST and the parallel workers. The tech.instacart.com copy returned 403.

- Postgres Job Queues & Failure By MVCC, Brandur Leach, 2015-05-18. https://brandur.org/postgres-queues Focus on: "Slow lock time" and "Dead tuples". Phase 3, section 3.7, uses the rest of the post.

- Goodbye integers. Hello UUIDv7!, Gordon Chan, Buildkite, 2023. https://buildkite.engineering/goodbye-integers-hello-uuids/ Focus on: the time-ordered UUID experiment and the 50% drop in WAL rate. Other changes went out in the same 6 weeks.

- MySQL bug 45015: InnoDB buffer pool can be severely affected by table scans, Harrison Fisk, 2009. https://bugs.mysql.com/bug.php?id=45015 Focus on: the report on mysqldump, and the changelog note that explains why a scan page moved to the head of the list.

- MySQL 5.5 and MySQL 5.6 default variable values differences, Peter Zaitsev, Percona, 2013. https://www.percona.com/blog/2013/02/21/mysql-5-5-and-mysql-5-6-default-variable-values-differences/ Focus on: the innodb_old_blocks_time row, 0 in 5.5.30 and 1000 in 5.6.10.

### Lectures and notes

- CMU 15-445/645 Fall 2025 notes, #04 buffer pools. https://15445.courses.cs.cmu.edu/fall2025/notes/04-bufferpool.pdf Focus on: section 5, the OS page cache, and "Dirty Pages". Written notes, for reading instead of watching.

- CMU 15-445/645 Fall 2025 notes, #05 "Database Storage II". https://15445.courses.cs.cmu.edu/fall2025/notes/05-storage2.pdf Focus on: section 4, "Index-Organized Storage". The course schedule uses this title. The video titles below may differ, which was not checked.

- CMU 15-445/645 Fall 2025 notes, #08 "Indexes & Filters I". https://15445.courses.cs.cmu.edu/fall2025/notes/08-indexes1.pdf Focus on: "Clustered Indexes", and the merge threshold.

- CMU 15-445/645 Fall 2025 notes, #06 "Storage Models & Compression". https://15445.courses.cs.cmu.edu/fall2025/notes/06-storage3.pdf Focus on: section 2, the row store and the column store with their advantages and disadvantages. Read it before the columnar paragraph of section 2.7.

- CMU 15-445/645 Fall 2025, Lecture 04: Memory Management and Buffer Pools, Andy Pavlo. https://www.youtube.com/watch?v=8-2yv4z0VZc Focus on these times: "Caption" times were checked against YouTube's auto-generated captions. "Auto-chapter" times are YouTube's chapter marks and were not checked. At 0:59:58 the captions show the claim about "little tweaks", which the release notes above contradict.
- 0:04:29 buffer pool overview, auto-chapter
- 0:15:39 page table, dirty flag, pin count, auto-chapter
- 0:22:52 why not mmap, caption
- 0:36:20 replacement policies, auto-chapter
- 0:40:30 clock, an approximate LRU, caption
- 0:47:40 sequential flooding, caption
- 0:50:43 LRU-K and ghost caches, auto-chapter
- 0:58:07 MySQL's young and old regions, caption
- 0:59:58 ARC, PostgreSQL and the patent, caption
- 1:03:00 PostgreSQL's ring for scans, caption
- 1:06:56 flushing and I/O scheduling, auto-chapter
- 1:12:35 O_DIRECT, caption

- CMU 15-445/645 Fall 2025, Lecture 05: Log-Structured Database Storage, Andy Pavlo. https://www.youtube.com/watch?v=2_sTdS4h-bY Focus on: 0:32:34 LSM trees, caption. 0:45:08 tombstones and compaction, caption. 0:50:11 leveled compaction, caption. 0:59:07 universal compaction, caption. 1:01:03 RocksDB's default style, caption.

- CMU 15-445/645 Fall 2025, Lecture 08: B+Trees, Andy Pavlo. https://www.youtube.com/watch?v=u7ii_Lvm9rM Focus on: 0:17:02 introduction, 0:37:11 insertion, 0:45:35 deletion, 1:07:57 optimizations. Auto-chapters only, because the captions did not load.

### ORMs and drivers

- Model field reference, Django 5.2. https://docs.djangoproject.com/en/5.2/ref/models/fields/ Focus on: UUIDField and its default=uuid.uuid4 example.

- uuid, Python 3 standard library. https://docs.python.org/3/library/uuid.html Focus on: the line that uuid4() creates a random UUID.

- Active Record and PostgreSQL, Rails Guides. https://guides.rubyonrails.org/active_record_postgresql.html Focus on: "UUID Primary Keys", where gen_random_uuid() is the default.

### The owner's other courses

These are files in study-material/, not URLs.

- retrieval-internals, Phase 2, section 2.2, and Phase 4, section 4.4. Memory per vector and quantization. Phase 7, sections 7.1 and 7.3, for deletes.

- advanced-retrieval, Phase 7, section 7.3. The planner's choice between a B-tree and HNSW under a filter.
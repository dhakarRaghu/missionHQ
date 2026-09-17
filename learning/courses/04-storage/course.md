# Course 4 — Storage and database internals
slug: elite-storage
order: 4
source: local
language: Go for the KV-store lab, SQL against real Postgres

## Why this course

He uses Postgres, MySQL and Redis every day. This course is about the part
of them that use does not teach: what "committed" actually promises when the
power goes out, which anomalies a transaction level lets through, why the
planner chose the plan it chose, and what a migration does to a live table.
Courses 5 and 6 build on this — a replica cannot be reasoned about without
knowing what the write path guarantees on one node.

No posting in the sampled market asks for storage-engine internals. This
course exists for the long-term standard, not the next interview: an engineer
who does not know what fsync promises will one day discover it in a
postmortem. It is kept to four phases for that reason — the mechanisms that
change what you build, and no more.

## What you will be able to do

Build a small store that survives being killed mid-write and prove it.
Reproduce lost update and write skew in real Postgres and show which
isolation level prevents each. Read a query plan and fix a bad one. Change a
live schema under load without a failed request.

---

## Phase 1 — Durability and the write path
question: When the database says "committed", what exactly has happened on disk — and what can a crash one millisecond later still lose?
minutes: 150
assumes: page cache and fsync cost (1.5), honest measurement (1.1)
introduces: write-ahead log, fsync semantics and what it does not guarantee, torn and partial writes, checksums, checkpoint, crash recovery and replay, the durability boundary, group commit
leaves-for-later: replication and what a replica has (5.3), storage structures on top of the log (4.2)

### Why you're here
The insert returned success. The server lost power. On restart the row is gone, and so is the row before it. The application had a receipt for both. The database was configured correctly — the disk was lying about what it had written, and nobody had tested a crash between "the OS accepted the write" and "the platter has it". An independent analysis found a widely used database cluster losing committed transactions in its recommended configuration; the mechanism was in this phase.

"Committed" is a contract with conditions. This phase reads the conditions.

### Sections
1.1 — Memory, page cache, disk: the three places a write can be, and which of them a crash erases
1.2 — The write-ahead log: why the log is written before the data, and what recovery replays
1.3 — fsync: what it promises, what it does not, and the disks and file systems that report a write as durable before it is
1.4 — Torn writes and checksums: the page written halfway, and how the recovery code notices
1.5 — Checkpoints and recovery: what runs on restart, how long it takes, and what bounds it
1.6 — Group commit and the durability–throughput trade: why one fsync per transaction is the wrong default at scale
1.7 — Stating the durability boundary: the one sentence a storage system owes its users, and the tests that back it

### Lab
Build a Bitcask-style key–value store in Go: append-only log, in-memory index (compaction comes in phase 2). Add checksums. Kill the process at every write step with a crash-injection wrapper. Recover. Prove the durability boundary you wrote down holds, and find the one place it did not.

### Demonstrate
The store, its stated durability boundary, a crash matrix across every write step with recovery verified, and one torn write detected by the checksum rather than served as data.

### Test out
- Explain: the order of operations in a WAL-backed write and what fsync at each point does and does not guarantee.
- Predict: for a described crash point, whether the last transaction is recoverable, and what recovery will replay.
- Demonstrate: the store with its crash matrix.

---

## Phase 2 — Storage structures
question: Why does the same workload run ten times faster on one storage structure than another, and how do you tell which one you need before you have built the wrong one?
minutes: 120
assumes: the write-ahead log (4.1), the page cache (1.5)
introduces: pages and the buffer pool, B-tree, LSM tree, compaction, Bloom filter, read/write/space amplification, matching structure to workload, cache eviction policies (LRU, LFU, 2Q, ARC)
leaves-for-later: indexes as the planner sees them (4.4), partitioning (4.4)

### Why you're here
A team moved a write-heavy event store from Postgres to an LSM-based database because "it is faster for writes". Writes did get faster. Reads got slower, disk usage tripled during compaction, and a nightly compaction storm became the new p99 problem. Nothing was wrong with either database. The workload had been matched to the wrong structure, and nobody had a way to say so before migrating.

Every structure trades one amplification for another. This phase is knowing the trade before you pay it.

### Sections
2.1 — Pages and the buffer pool: the unit of I/O, and what a cache miss costs in the numbers from phase 1.5
2.2 — B-trees: how a read finds a row, what a write updates, and why they read fast and write in place
2.3 — LSM trees: memtable, sorted runs, compaction — why they write fast and read across levels
2.4 — Compaction: the work that happens later, and the p99 storm it causes when it happens at once
2.5 — Bloom filters: turning "is it in this level" into one memory read, with the false-positive arithmetic
2.6 — Read, write and space amplification: the three numbers to estimate for any workload
2.7 — Matching structure to workload: the decision table, with the measurements that fill it in
2.8 — Eviction: why LRU collapses under a scan, LFU, 2Q and ARC, and what a real buffer pool uses

### Lab
Extend the KV store from phase 1 with an LSM-style layout: memtable, flush, two levels, compaction, a Bloom filter per run. Measure read, write and space amplification under two workloads (write-heavy, read-heavy). Compare with the phase-1 layout. Then put a bounded cache in front of it and measure hit rate for LRU against 2Q under a scan-heavy workload.

### Demonstrate
Measured read/write/space amplification for two layouts under two workloads, with the compaction storm shown in the latency histogram, the Bloom filter's measured false-positive rate against its memory, and the LRU-versus-2Q hit rates under a scan.

### Test out
- Explain: why LSM trees write faster and read slower than B-trees, in terms of what each does per operation.
- Predict: for a described workload and read/write ratio, which structure wins and by roughly how much.
- Demonstrate: the two-layout comparison.

---

## Phase 3 — Transactions and concurrency control
question: Two transactions both read, both write, both commit without error — and the result is one neither of them would have produced alone. Which isolation level allowed that, and which would have stopped it?
minutes: 180
assumes: the write path (4.1), concurrency correctness on one process (1.4)
introduces: atomicity, isolation levels, MVCC and snapshots, lost update, write skew, phantom reads, locks and deadlocks, snapshot isolation vs serializable, optimistic vs pessimistic concurrency, serialization failures and retry, the transactional outbox as a same-transaction write
leaves-for-later: cross-node transactions and sagas (5.2)

### Why you're here
Two on-call doctors each check that at least one doctor is on call, then each removes themselves. Both transactions commit. Nobody is on call. No error was raised, no lock was contended, and the database was at its default isolation level, which permits exactly this. An independent analysis found a managed Postgres offering delivering weaker guarantees than its documentation implied — the anomalies in this phase, in production, at a cloud provider.

Isolation levels are a menu of anomalies you have agreed to accept. This phase reads the menu.

### Sections
3.1 — Atomicity and isolation: what each one promises, and the difference between "all or nothing" and "as if alone"
3.2 — MVCC: how snapshots work, why readers do not block writers, and what a snapshot cannot see
3.3 — The anomalies: lost update, write skew, phantoms — each one reproduced with two sessions
3.4 — Locks and deadlocks: row locks, the wait graph, how the database chooses a victim, and how to read a deadlock report
3.5 — Snapshot isolation versus serializable: what SSI adds, what it costs, and the serialization failure you must retry
3.6 — Optimistic versus pessimistic: SELECT FOR UPDATE, version columns, and choosing by contention
3.7 — Isolation in Mission HQ: the task state transitions, approvals and the outbox, and which anomaly each would suffer at READ COMMITTED

### Lab
Write scripts that reproduce lost update and write skew against real Postgres at REPEATABLE READ. Show SERIALIZABLE prevents each, and what the serialization failure looks like. Then audit one Mission HQ transaction (task claim, approval, outbox write) for the anomaly it is exposed to, and fix it.

### Demonstrate
Two anomalies reproduced on demand, prevented by a named mechanism, plus one real Mission HQ transaction hardened with a test that fails at the old isolation level.

### Test out
- Explain: write skew, why snapshot isolation allows it, and what serializable does differently.
- Predict: for a described pair of transactions and an isolation level, whether they can produce a wrong result.
- Demonstrate: the reproductions and the Mission HQ fix.

---

## Phase 4 — Query planning and production evolution
question: Why did the planner choose a sequential scan over your index, and what will your migration do to the table while it runs?
minutes: 150
assumes: pages and B-trees (4.2), locks (4.3)
introduces: EXPLAIN and EXPLAIN ANALYZE, cardinality estimation and statistics, access paths and index selectivity, join strategies, vacuum and bloat, table partitioning, migration locks, expand/contract schema changes, rollback and compatibility
leaves-for-later: safe change as a release discipline (6.3), schema evolution across services (7.2)

### Why you're here
The query took 20 ms in staging and 9 seconds in production. Same query, same index. Production has a hundred times the rows, the statistics were stale, and the planner estimated 40 rows where there were four million. Then the fix — a new index — was deployed with a migration that took an exclusive lock, and the service was down for the 11 minutes it took to build.

The planner is a cost model working from statistics you control, and a migration is a workload you schedule. Both are predictable once you can read them.

### Sections
4.1 — Reading EXPLAIN: nodes, estimated versus actual rows, and the one column that tells you the statistics are wrong
4.2 — Cardinality and statistics: how estimates are made, when they go stale, and what ANALYZE fixes
4.3 — Access paths: sequential scan, index scan, index-only scan, bitmap scan — and the selectivity at which each wins
4.4 — Joins: nested loop, hash, merge — how the planner picks, and how to see it picked wrong
4.5 — Vacuum and bloat: MVCC's garbage, transaction-ID wraparound, and the table that keeps growing after deletes
4.6 — Partitioning: when it helps, when it hurts the planner, and pruning
4.7 — Migrations under load: which DDL takes which lock, expand/contract, backfilling in batches, and the compatibility window
4.8 — Rollback: the schema change you cannot undo, and how to structure one so you can

### Lab
On Mission HQ's database, find one query with a bad plan (or construct one by breaking the statistics). Diagnose it with EXPLAIN (ANALYZE, BUFFERS). Fix it. Then add a NOT NULL column with a backfill to a table under load, with zero failed requests and lock waits bounded, using expand/contract.

### Demonstrate
One plan diagnosed and fixed with the before/after buffers and time, and one live migration under load with the lock waits measured and no request failed.

### Test out
- Explain: why the planner might prefer a sequential scan over an index, and which statistic would change its mind.
- Predict: which lock a given DDL statement takes and what it blocks while it holds it.
- Demonstrate: the plan fix and the zero-downtime migration.

---

## Integrated lab for the course

The KV store with crash recovery and a stated durability boundary, two storage layouts measured against two workloads, write skew reproduced and prevented in real Postgres, and one Mission HQ migration run under load without a failed request. Write the one-page storage note: what this system guarantees, what it does not, and how you know.

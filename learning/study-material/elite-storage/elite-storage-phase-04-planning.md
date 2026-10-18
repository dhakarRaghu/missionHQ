# Phase 4 — Query planning and production evolution

**The question this phase answers:** why did the planner choose a sequential scan over your index? And what will your migration do to the table while it runs?

**The promises this phase pays.** Phase 3 made two promises to this phase. Section 4.5 covers vacuum and bloat. That is the cleanup of the dead row versions that MVCC, multiversion concurrency control, leaves behind. Section 4.7 covers the locks that schema changes take in migrations, beyond the row locks of Phase 3, section 3.4. This is the last phase of the course, so its lab closes with the course's storage note.

## Why you're here

Here is the situation this phase follows. It is an example, and the lab reproduces its shape at a smaller size.

The order data of Phases 1 and 2 now also lives in PostgreSQL 14, because reports need SQL. The table `orders` holds 10 million orders. The table `order_events` holds three events per order: created, paid and shipped. A dashboard runs one report: count the events of every pending order, per tenant. In staging, with 100,000 orders, the report takes 20 ms. In production it takes 9 seconds.

Nothing in the query changed. Earlier that day, a payment provider failed, and 4 million orders became `pending` in one hour. PostgreSQL's statistics still described the table before that hour. The plan said it expected 42 pending orders. The real count was 4,000,000.

The team's first fix was a new index on `orders (status)`. The migration ran `CREATE INDEX` without `CONCURRENTLY`. The build took 11 minutes, and during those 11 minutes every INSERT and UPDATE on `orders` waited. Checkout was down. Reads kept working, which made the outage harder to understand. When the index was ready, the report was still slow.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The running case. Times and counts are an example                        │
├──────────────────────────────────────────────────────────────────────────┤
│ 09:00  last ANALYZE of orders: almost no order is pending                │
│ 10:00  payment provider fails. 4,000,000 orders become pending           │
│ 11:00  the report: plan expects 42 pending rows, gets 4,000,000. 9 s     │
│ 11:20  CREATE INDEX on orders (status) starts, no CONCURRENTLY           │
│ 11:20  every INSERT and UPDATE on orders waits. SELECTs still run        │
│ 11:31  index built. Writes resume. The report is still 9 s               │
├──────────────────────────────────────────────────────────────────────────┤
│ two problems: an estimate from old statistics, and a lock nobody planned │
└──────────────────────────────────────────────────────────────────────────┘
```

Both problems are predictable. The planner is a cost model that works from statistics you control. A migration is a workload you schedule. Each of its statements takes a lock you can name before it runs. This phase teaches you to read both.

## What you can do after this phase

1. Find the slow query in production with `pg_stat_statements` and `auto_explain`. Then read its plan from `EXPLAIN (ANALYZE, BUFFERS)`, and find the node where the estimate went wrong.
2. Read a parallel plan and a JIT block, which the lab turns off and your server does not.
3. Compute a row estimate from `pg_stats`, and say when the statistics go stale.
4. Tell a generic plan of a prepared statement from a custom plan, and say when the switch hurts.
5. Explain why the planner chose a sequential scan over an index, with the cost arithmetic.
6. Say which join method a plan uses, and why a low estimate makes a nested loop dangerous. Say when a sort or hash spills to disk.
7. Explain what vacuum removes, what stops it, and why autovacuum falls behind on a large table. Explain how transaction ID wraparound stops a database.
8. Decide whether partitioning helps a table or hurts its plans.
9. Name the lock each DDL statement takes. Run a NOT NULL migration on a busy table with no failed request.
10. Order a schema change so that every step before the last one can be undone.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PHASE 4: Query planning and production evolution                         │
├──────────────────────────────────────────────────────────────────────────┤
│ 4.1 Reading EXPLAIN        estimated against actual rows, parallel, JIT, │
│                            and finding the slow query in production      │
│ 4.2 Cardinality            estimates, stale statistics, generic plans    │
│ 4.3 Access paths           seq, index, index-only, bitmap: who wins when │
│ 4.4 Joins                  nested loop, hash, merge, Memoize, spills     │
│ 4.5 Vacuum and bloat       dead versions, the throttle, wraparound       │
│ 4.6 Partitioning           pruning, and where it hurts the planner       │
│ 4.7 Migrations under load  DDL locks, the lock queue, expand/contract    │
│ 4.8 Rollback               the change you cannot undo, and the fix       │
│ Lab: E1 to E16. The demonstration: E4, E10 and E11                       │
│ The course's storage note                                                │
└──────────────────────────────────────────────────────────────────────────┘
```

## What this phase assumes

Two ideas from this course are used here and not taught again.

- **Pages and B-trees, from Phase 2, sections 2.1 and 2.2.** PostgreSQL reads and caches its files in pages of 8,192 bytes. Its buffer pool is `shared_buffers`. A B-tree index finds a key in one page read per level. For 10 million keys that is 3 levels, and the levels above the leaves fit in 776 KiB. A row lives in the heap, the table's own file. An index entry points at the row's page and line pointer.
- **Locks, from Phase 3, section 3.4.** A row lock lasts until the transaction ends. A second writer of the row waits for it. Every statement also takes a lock on each table it uses. A SELECT takes `ACCESS SHARE`, which only `ACCESS EXCLUSIVE` blocks. A request that waits also blocks later requests that conflict with it, which `pg_blocking_pids` reports as a soft block. `lock_timeout` is 0 by default, which means no limit.

Section 4.5 also uses two ideas from Phase 3 and recaps each in one sentence where it is used. They are snapshots, from section 3.2, and multixacts, from section 3.4.

**The running system.** The lab tables carry the prefix `p4_`, so the labs of earlier phases keep working. `p4_orders`, `p4_order_events` and `p4_tenants` hold the order data of the opening case at 1 million orders. `p4_tasks` has the columns of Phase 3's `tq_tasks`, the course's own task queue.

**Left for later.** Safe change as a release discipline is course 6, "Reliability, security and change", Phase 3. It covers canaries, feature flags and rollout gates. Schema evolution across services, where one service's change breaks another's contract, is course 7, "System design and architecture", Phase 2. Splitting a table across servers is course 5, Phase 3.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. The labs need your local PostgreSQL 14 at `/tmp:5432`, in the database `storage_lab`, with psycopg 3.3.6 from `pyproject.toml`. `cost_model.py`, `locks.py --predict` and every `--self-test` run with no server. Run all commands from `elite-storage/code/`.

Time: 3 hours for the reading. The labs take longer, about 3.5 hours.

---

## 4.1 — Reading EXPLAIN (nodes, estimated versus actual rows, and the one column that tells you the statistics are wrong)

Why this matters: the 9-second report has a plan, and the plan says exactly where the time went. Most people read the cost numbers first, and those numbers are not time. The fastest diagnosis compares two numbers on every node: the rows the planner expected and the rows that came out. At work, two more steps come around it. First you find the slow query among thousands. Then you read a plan that your server ran with parallel workers and JIT, which this phase's lab turns off.

**Answer this first.** Here is the report's plan in production, as `EXPLAIN (ANALYZE, BUFFERS)` printed it. It is an example plan, not a run. Its numbers follow the opening case. Answer three questions before you read on:

1. How many times did the Index Scan on `order_events` run, and how many rows did it return in total?
2. Which node has the worst estimate, and by what factor?
3. Is the Index Scan's estimate of `rows=3` wrong?

```text
HashAggregate  (cost=325612.40..325622.40 rows=126 width=12) (actual time=9010.2..9011.0 rows=1000 loops=1)
  Group Key: o.tenant_id
  Buffers: shared hit=15400246 read=812004
  ->  Nested Loop  (cost=0.56..325611.77 rows=126 width=4) (actual time=0.06..7900.4 rows=12000000 loops=1)
        Buffers: shared hit=15400246 read=812004
        ->  Seq Scan on orders o  (cost=0.00..325250.00 rows=42 width=12) (actual time=0.02..2100.3 rows=4000000 loops=1)
              Filter: (status = 'pending'::text)
              Rows Removed by Filter: 6000000
              Buffers: shared hit=200246 read=4
        ->  Index Scan using order_events_order_id_idx on order_events e  (cost=0.56..8.59 rows=3 width=8) (actual time=0.0011..0.0014 rows=3 loops=4000000)
              Index Cond: (order_id = o.id)
              Buffers: shared hit=15200000 read=812000
Planning Time: 0.410 ms
Execution Time: 9012.551 ms
```

**The mental model.** A plan is a tree of nodes. The leaves are scans that read a table or an index. The nodes above them join, sort or aggregate the rows that the scans return. Each node prints two groups of numbers:

- **The estimate**, from plain `EXPLAIN`: `cost=startup..total`, `rows` and `width`. The cost is in arbitrary units, where reading one page in sequence costs 1.0 by convention. The docs, section 14.1.1, say "the cost of an upper-level node includes the cost of all its child nodes".
- **The measurement**, added by `ANALYZE`: `actual time=startup..total` in milliseconds, `rows` and `loops`. `ANALYZE` runs the query for real.

`loops` is the number of times the node ran. The docs, section 14.1.2, say that for such a node "the actual time and rows values shown are averages per-execution". `explain.c` at tag REL_14_24, line 1619, divides the row count by the loop count before it prints it. So a node's total is its printed rows times its loops.

**The one column.** The docs, section 14.1.2, name it. "The thing that's usually most important to look for is whether the estimated row counts are reasonably close to reality." To compare the two, use the **q-error**. Cardinality here means the number of rows a node returns. Leis and others define the q-error in "How Good Are Query Optimizers, Really?", PVLDB 2015, section 3.1. It is "the factor by which an estimate differs from the true cardinality". An estimate of 10 or of 1,000 for a true count of 100 both have a q-error of 10.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The report's plan, read bottom up. est = expected rows per execution     │
├──────────────────────────────────────────────────────────────────────────┤
│ HashAggregate        est 126        actual 1,000                         │
│   └─ Nested Loop     est 126        actual 12,000,000                    │
│        ├─ Seq Scan orders           est 42   actual 4,000,000  loops 1   │
│        │    q-error 4,000,000 / 42 = 95,238  ◄── the error enters here   │
│        └─ Index Scan order_events   est 3    actual 3   loops 4,000,000  │
│             q-error 1: right per loop. Run 95,238 times too often        │
├──────────────────────────────────────────────────────────────────────────┤
│ an error low in the tree is carried into every node above it             │
└──────────────────────────────────────────────────────────────────────────┘
```

So here are the answers. The Index Scan ran 4,000,000 times and returned 3 × 4,000,000 = 12,000,000 rows. The worst node is the Seq Scan on `orders`, where the diagram shows the error entering. The Index Scan's `rows=3` is right, because every order has three events. The error is in how often the scan ran, and that came from the node below the join.

**The details: what the numbers mean.** The cost formula of a sequential scan is the simplest one. The docs, section 14.1.1, give it for their table `tenk1`. It has 358 pages and 10,000 rows: "(358 * 1.0) + (10000 * 0.01) = 458". The 1.0 is `seq_page_cost` and the 0.01 is `cpu_tuple_cost`. A WHERE clause adds `cpu_operator_cost`, 0.0025, per row. So the same scan with a filter costs 458 + 10,000 × 0.0025 = 483. Section 4.3 uses these formulas to answer the phase's first question.

`BUFFERS` adds the page counts of each node. A hit is a page found in `shared_buffers`. A read is a page that missed and came from the operating system. The OS may still have it in its page cache, as Phase 2, section 2.1, showed. The PostgreSQL 14 docs for EXPLAIN add one rule. "The number of blocks shown for an upper-level node includes those used by all its child nodes." Two version facts matter here:

- PostgreSQL 14: `BUFFERS` "defaults to FALSE". You must ask for it, as `EXPLAIN (ANALYZE, BUFFERS)`.
- PostgreSQL 18: "Buffers information is automatically included when ANALYZE is used."

Both are verified from the EXPLAIN pages of the PostgreSQL 14 and 18 docs. In the example plan, the inner scan made 15,200,000 + 812,000 = 16,012,000 page accesses. That is about 4 per loop. It fits three B-tree levels, as Phase 2, section 2.2, computed for 10 million keys, plus one heap page. These are example numbers. If an order's three events sit on three pages, as in the lab, a probe reads three heap pages.

The lab reads plans as JSON, so that a script can compare the two numbers on every node. From `phase04_planning/explain_tools.py:113`:

```python
# from phase04_planning/explain_tools.py:113, q_error(). Docstring cut, logic unchanged
def q_error(est: float, actual: float) -> float:
    e, a = max(est, 1.0), max(actual, 1.0)
    return max(e / a, a / e)
```

Both sides are floored at 1, because the planner never estimates fewer than one row. That rule is `clamp_row_est` in `costsize.c`, REL_14_24, lines 199 to 215. Section 4.2 shows a case where it decides the estimate. The `Node` class compares `Plan Rows` with `Actual Rows`, which are both per loop, and multiplies by `Actual Loops` only for the total.

**Four readings that are not estimation errors.** The docs, section 14.1.3, list them:

1. A node under `LIMIT` stops early. Its actual rows are lower than its estimate, and nothing is wrong.
2. A merge join can stop reading one input early, and can count re-read inner rows twice.
3. `BitmapAnd` and `BitmapOr` nodes "always report their actual row counts as zero".
4. Timing has its own cost. "The measurement overhead added by EXPLAIN ANALYZE can be significant", and network transfer to the client is not included.

**Two timing options.** A `read` in BUFFERS can come from the OS page cache or from the disk. The count cannot tell them apart. `track_io_timing` can. It is off by default, because it reads the clock on every I/O. The docs say that "may cause significant overhead on some platforms". When it is on, EXPLAIN with BUFFERS adds a line `I/O Timings: read=...`, from `explain.c` at REL_14_24, line 3582. Many reads with a small read time came from the page cache. The other option goes the opposite way. `EXPLAIN (ANALYZE, TIMING FALSE)` keeps the actual rows and drops the clock reads of every node. Both are verified from the PostgreSQL 14 docs, section 20.9 and the EXPLAIN page. The docs name `pg_test_timing` as the tool that measures the clock's cost on your machine.

**What the lab turns off: parallel query and JIT.** Every lab plan in this phase runs with two session settings. `lab_settings()`, at `phase04_planning/explain_tools.py:318`, sets `max_parallel_workers_per_gather = 0` and `jit = off`. Parallel query splits one scan across several processes, which changes how rows and loops read. JIT, just-in-time compilation, turns parts of a query into machine code when it starts. Its compile time would blur a before-and-after timing. So the lab's plans are serial and uncompiled. Your server's plans are not, because PostgreSQL 14 turns both on by default. `max_parallel_workers_per_gather` is 2, and `jit` is on. Verified from the PostgreSQL 14 docs, sections 20.4 and 20.7.

**What parallel query changes in a plan.** A Gather node starts worker processes. Each worker runs the plan below the Gather on its own part of the table. The leader, the session's own process, also runs that part when it is not busy. The rows flow up to the Gather, which passes them on. Three rules decide whether the planner uses it. They are verified from `costsize.c` and `allpaths.c` at REL_14_24, and from the docs, section 20.7:

1. The table must reach `min_parallel_table_scan_size`, 8MB, which is 1,024 pages. Each factor of 3 above that allows one more worker, up to `max_parallel_workers_per_gather`. That is `compute_parallel_worker`, `allpaths.c` lines 3776 to 3823.
2. Only the CPU part of a scan is divided. The divisor is the worker count plus a leader share of 1 − 0.3 × workers. With 2 workers it is 2 + 0.4 = 2.4, from `get_parallel_divisor`, `costsize.c` lines 6060 to 6085. The disk part is not divided, because "most operating systems already do aggressive prefetching", lines 279 and 280.
3. The Gather adds `parallel_setup_cost`, 1000, plus `parallel_tuple_cost`, 0.1, for each row it passes up.

Apply these rules to the example plan above. Its Seq Scan costs 325,250. The CPU part is 10,000,000 × 0.0125 = 125,000, so the disk part is 200,250 pages. Over 2.4 processes, the CPU part becomes 52,083. The parallel scan then costs 200,250 + 52,083 = 252,333. The Gather adds 1,000, plus 0.1 × 42 rows, which is 4. The total is about 253,337, below the serial 325,250. The table has 200,250 pages, far above 1,024, so 2 workers are allowed. So at the defaults, this scan would most likely run as a Parallel Seq Scan under a Gather. That is inferred from the formulas and was not run.

A real parallel plan shows how to read one. It comes from PostgreSQL BUG #19076, reported on PostgreSQL 17.6 on 2025-10-07, and section 4.2 returns to that report. Lines are removed, and the numbers are copied from the report:

```text
Gather  (cost=44906.68..46937.80 rows=19344 width=24) (actual time=102.801..103.506 rows=2326 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  ->  Partial HashAggregate  (cost=43906.68..44003.40 rows=9672 width=24) (actual time=93.682..93.757 rows=775 loops=3)
        ->  Hash Join  (cost=6066.79..43819.26 rows=17484 width=32) (actual time=12.902..92.674 rows=11509 loops=3)
              ->  Parallel Seq Scan on contacts  (cost=0.00..36177.50 rows=373366 width=16) (actual time=0.435..55.023 rows=288122 loops=3)
              ->  Hash  (cost=5275.46..5275.46 rows=63307 width=32) (actual time=12.053..12.054 rows=37282 loops=3)
```

Five rules read it:

- `loops=3` is the leader plus 2 workers. A node's actual rows are an average per process. So the parallel scan returned 288,122 × 3 = 864,366 rows in total.
- Its estimate is per process too. But `costsize.c` line 288 divides it by 2.4, not by 3. So compare 373,366 × 2.4 = 896,078 with 864,366. The q-error is 1.04. Read naively, 373,366 against 288,122 looks 1.30 off.
- The Gather's own estimate depends on the node below it. Above a scan or a join, it is the total estimate. Above a partial aggregate, it is the per-process estimate times the workers, without the leader share. Here that is 9,672 × 2 = 19,344. Verified from `cost_gather`, `costsize.c` lines 386 to 391, and `allpaths.c` lines 2631 and 2632, all at REL_14_24.
- The Hash node here is not parallel aware, and it shows the full 37,282 rows with `loops=3`. So each of the three processes built its own full hash table, which is inferred from those two facts. Its rows are not split, so compare them directly: 63,307 / 37,282 = 1.70.
- `work_mem` applies to each process on its own. The docs, section 20.4, give an example. A query with 4 workers "may use up to 5 times as much CPU time, memory, I/O bandwidth" as one with none. So this plan held three hash tables at once, one per process. And if `Workers Launched` is below `Workers Planned`, the pool of worker processes was full. The docs say the plan then runs "with fewer workers than expected, which may be inefficient".

`explain_tools.py` applies the first two rules to every node under a Gather. They fit scans and joins. A partial aggregate estimates groups per process, and one group can appear in every process. So read its q-error as rough, which is inferred from the planner's rules. Its `--server-defaults` flag keeps your server's settings, so E15 shows a parallel plan on the lab's own `p4_orders`.

**What JIT changes in a plan.** JIT compiles the expressions of a plan into machine code when the query starts. The WHERE clause is one such expression. The planner decides from the total estimated cost of the plan. Verified from the PostgreSQL 14 docs, sections 32.2 and 20.7:

| Total cost above | What JIT adds | Default |
|---|---|---|
| `jit_above_cost` | compile the expressions | 100000 |
| `jit_inline_above_cost` | also inline small functions and operators | 500000 |
| `jit_optimize_above_cost` | also apply expensive optimizations | 500000 |

The example plan costs 325,612, which is above 100,000 and below 500,000. So its EXPLAIN ANALYZE would most likely end with a JIT block, without inlining or optimization. That is inferred from the thresholds, not run. JIT also needs a server compiled `--with-llvm`. This course did not check whether the owner's Homebrew PostgreSQL 14 has it. Without it, JIT never runs. The docs' own sample, from section 32.2, shows the block that EXPLAIN ANALYZE prints at the end:

```text
 JIT:
 Functions: 3
 Options: Inlining false, Optimization false, Expressions true, Deforming true
 Timing: Generation 1.259 ms, Inlining 0.000 ms, Optimization 0.797 ms, Emission 5.048 ms, Total 7.104 ms
```

The failure is a cost that a bad estimate inflated. The plan passes `jit_above_cost`, and the compile takes longer than the query itself. Adam Johnson reported this on PostgreSQL 14, in his post of 2023-11-09. A Django query joined many tables, and PostgreSQL expected many rows where each join added few. The comment in his fix says "3.5 seconds with JIT vs 10 milliseconds without". The fix was the connection option `-c jit=off` for the application. The cause is the one this phase keeps returning to, a wrong row estimate. JIT only made it cost more. The docs, section 32.2, add one rule for prepared statements, which section 4.2 explains. When a statement reuses one plan, the JIT decision uses the settings in effect when it was prepared.

**The failure: EXPLAIN ANALYZE on a write.** `ANALYZE` runs the statement. On an UPDATE or DELETE, the rows change for real. The docs, section 14.1.2, give the safe form: run it inside `BEGIN` and `ROLLBACK`. The statement still takes its row locks while it runs. So do it on a copy, not on a busy table.

WRONG and RIGHT, on the example plan:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ WRONG reading                       │ RIGHT reading                      │
├──────────────────────────────────────────────────────────────────────────┤
│ "cost=325612 means 325 s"           │ cost is in page units. Time is     │
│                                     │ actual time: 9,012 ms here         │
│ "the slow node is the one with the  │ the wrong node is where est and    │
│  largest time, the Nested Loop"     │ actual first differ: the Seq Scan  │
│ "plain EXPLAIN shows the problem"   │ plain EXPLAIN shows rows=42 and    │
│                                     │ nothing to compare it with         │
└──────────────────────────────────────────────────────────────────────────┘
```

**Finding the plan in production.** Everything above starts from a query you already have. At work you must first find it. And the plan you get by hand in psql may differ from the plan that the application got. Two contrib modules of PostgreSQL 14 close that gap. Both are verified from the PostgreSQL 14 docs, sections F.30 and F.4.

`pg_stat_statements` keeps one row per normalized statement. That is the statement's text with its constants replaced by parameter symbols. The module needs shared memory, so it must be listed in `shared_preload_libraries`. So "a server restart is needed" to add it. From PostgreSQL 14 it also needs a query identifier. `compute_query_id = auto`, the default, turns that on when the module loads. Then run `CREATE EXTENSION pg_stat_statements` in the database you read from. Two rankings answer two different questions:

```sql
-- Where does the server spend its time? This follows the docs' example.
SELECT calls, total_exec_time, mean_exec_time, stddev_exec_time,
       shared_blks_read, temp_blks_written, left(query, 60)
  FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10;

-- Which statement changes speed from call to call? A plan that flips,
-- such as the generic plan of section 4.2, gives a stddev far above the mean.
SELECT calls, mean_exec_time,
       stddev_exec_time / nullif(mean_exec_time, 0) AS cv, left(query, 60)
  FROM pg_stat_statements WHERE calls >= 100 ORDER BY cv DESC LIMIT 10;
```

The columns are verified from the docs. The second ranking is this course's own rule of thumb, and no source tests it. `temp_blks_written` above 0 means a sort or a hash spilled to disk, as section 4.4 shows.

`auto_explain` then gives you the plan. It logs the plan of every statement slower than `auto_explain.log_min_duration`, whose default of −1 logs nothing. With `log_analyze` on, it logs EXPLAIN ANALYZE output, so you get actual rows. The docs warn about the cost. Per-node timing then runs for every statement, logged or not, and it "can have an extremely negative impact on performance". So turn the per-node clock off and sample:

```text
# postgresql.conf. Verified setting names, PostgreSQL 14 docs F.4.1
session_preload_libraries = 'auto_explain'
auto_explain.log_min_duration = '500ms'
auto_explain.log_analyze = on
auto_explain.log_buffers = on
auto_explain.log_timing = off      # actual rows and buffers, no per-node clock
auto_explain.sample_rate = 0.1     # explain one statement in ten
```

`session_preload_libraries` "only takes effect at the start of the connection", from the docs, section 20.11. So it needs no restart. Connections that are already open, such as a pool's, keep running without it. That is inferred from the same sentence. The same docs warn that a connection fails if the library is not found. The logged plan is the plan that ran, with the parameter values it ran with. E14 sets up both modules, and `find_slow.py` prints both rankings.

The next section shows where the estimate of 42 came from.

**The sentence to remember:** read every node's estimated rows against its actual rows times loops. The lowest node where they differ by a large factor is where the plan went wrong. Under a Gather, multiply the estimate by the parallel divisor first.

**The trap:** reading per-loop rows as totals. The Index Scan above shows `rows=3` at a cost of 8.59, and it made 16 million page accesses. The second trap is diagnosing the plan you made in psql instead of the plan the application ran. Take that plan from `auto_explain`.

**Try this now:** run `uv run python phase04_planning/explain_tools.py --sql "select count(*) from pg_class c join pg_attribute a on a.attrelid = c.oid"`. Find the node with the most loops, and multiply its rows by its loops.

---

## 4.2 — Cardinality and statistics (how estimates are made, when they go stale, and what ANALYZE fixes)

Why this matters: every cost in a plan is built on a row estimate. The planner computes that estimate from a small sample of the table, taken at the last ANALYZE. With the formula, you can predict the estimate from `pg_stats` before you run the query. You also know which command changes it.

**Answer this first.** At 09:00 in the opening case, ANALYZE stored this row for `orders.status`. It is an example row:

```text
 null_frac | n_distinct | most_common_vals         | most_common_freqs
-----------+------------+--------------------------+---------------------------
         0 |         11 | {shipped,paid,created}   | {0.6,0.25,0.1499667}
```

`pg_class.reltuples` for `orders` is 10,000,000. Answer three questions:

1. What row estimate does `WHERE status = 'paid'` get?
2. What estimate does `WHERE status = 'pending'` get? `pending` is not in the list.
3. At 10:00, 4,000,000 orders become pending. Which of the numbers above change, and when does PostgreSQL change them by itself?

**The mental model.** An estimate is a row count times a selectivity. A selectivity is the fraction of rows that a condition keeps.

- **The row count** comes from `pg_class`: `reltuples` for the rows and `relpages` for the pages. Both are as of the last VACUUM, ANALYZE or CREATE INDEX. The docs, section 72.1, add one step. The planner reads the table's current page count, and "if that is different from relpages then reltuples is scaled accordingly".
- **The selectivity** comes from `pg_stats`, which ANALYZE fills from a random sample. The sample has 300 × the statistics target rows. That is `stats->minrows = 300 * attr->attstattarget;` at `analyze.c` line 1919, tag REL_14_0. With `default_statistics_target` at 100, the sample is 30,000 rows, however large the table is.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Where rows=42 comes from                                                 │
├──────────────────────────────────────────────────────────────────────────┤
│ orders, 10,000,000 rows                                                  │
│    │ ANALYZE reads a random sample of 300 x 100 = 30,000 rows            │
│    ▼                                                                     │
│ pg_stats, per column: null_frac, n_distinct, most_common_vals and freqs, │
│    │                  histogram_bounds, correlation. Up to 100 entries   │
│    │ the operator's selectivity function: eqsel for =, scalarltsel for < │
│    ▼                                                                     │
│ selectivity, by the formulas below  x  pg_class rows, scaled to pages    │
│    ▼                                                                     │
│ EXPLAIN: rows=42                                                         │
└──────────────────────────────────────────────────────────────────────────┘
```

**The formulas.** Three terms first. The MCV list, for most common values, holds a column's most frequent values. Next to each one, it stores its fraction of the rows. n_distinct is the estimated number of distinct values. A histogram here has buckets of equal frequency, so a value's position inside its bucket gives the fraction below it. The formulas are verified from the PostgreSQL 14 docs, section 72.1. The second row is also checked in `selfuncs.c`, REL_14_24, lines 405 to 432. The worked numbers are the docs' own, on the table `tenk1`:

| Condition | Formula | Docs example |
|---|---|---|
| `col = v`, v in the MCV list | the stored frequency of v | `stringu1 = 'CRAAAA'`: 0.003 x 10,000 = 30 rows |
| `col = v`, v not in the list | (1 − sum of MCV frequencies − null_frac) / (n_distinct − number of MCVs) | `'xxx'`: 0.96966667 / 666 = 0.0014559, so 15 rows |
| `col < v` | (whole histogram buckets below v + the linear fraction of v's bucket) / buckets | `unique1 < 1000`: (1 + 7 / 1004) / 10 = 0.100697, so 1007 rows |
| `a AND b` | the product of the two selectivities | 0.100697 x 0.0014559 = 0.0001466, so 1 row |
| `t1.x = t2.y`, no MCV lists | (1 − nf1)(1 − nf2) x min(1 / nd1, 1 / nd2) | 50 x 10,000 x 0.0001 = 50 rows |
| no statistics at all | 0.005 for `=`, 0.3333 for `<` | `selfuncs.h`, REL_14_0, lines 34 and 37 |

The histogram leaves out the values in the MCV list. Its bounds are null when "the most_common_vals list accounts for the entire population", from the docs for `pg_stats`. The code adds two rules to the second row. It divides only when n_distinct minus the MCV count is above 1. And the result is never more than the frequency of the least common MCV.

So here are the answers. `paid` is in the list: 0.25 × 10,000,000 = 2,500,000 rows. `pending` is not. The MCV frequencies add up to 0.6 + 0.25 + 0.1499667 = 0.9999667. So 1 − 0.9999667 = 0.0000333 is left for the 11 − 3 = 8 other values. That is 0.0000333 / 8 = 0.00000417, and 0.00000417 × 10,000,000 = 41.7, which EXPLAIN rounds to 42. The 0.0000333 is 1 / 30,000: one sampled row in 30,000 had a status outside the list. `cost_model.py --self-test` checks this arithmetic, and the docs' own examples.

**When statistics go stale.** The answer to question 3 is that nothing in `pg_stats` changes until an ANALYZE runs. Three ways one runs:

1. **Autovacuum's ANALYZE.** It starts when the rows changed since the last ANALYZE pass 50 + 0.1 × `reltuples`. That is `autovacuum_analyze_threshold` 50 and `autovacuum_analyze_scale_factor` 0.1, from the PostgreSQL 14 docs, sections 20.10 and 25.1.6. For `orders`: 50 + 0.1 × 10,000,000 = 1,000,050 changed rows. The incident passed that.
2. **But autovacuum must reach the table.** One launcher starts a worker per database every `autovacuum_naptime`, 1 minute. At most `autovacuum_max_workers`, 3, run at once. The docs, section 25.1.6, warn that several large tables can keep "all autovacuum workers" busy "for a long period". That is the inferred reason the opening case stayed stale for an hour. The docs also note that the daemon "has no knowledge of whether that will lead to meaningful statistical changes".
3. **A manual ANALYZE.** It takes a `SHARE UPDATE EXCLUSIVE` lock, which blocks neither reads nor writes, from the docs, section 13.3.1. It reads only the sample, so it is fast on a large table. This course did not time it.

`CREATE INDEX` is not on that list. The docs, section 14.2, say that `reltuples` and `relpages` "are updated by VACUUM, ANALYZE, and a few DDL commands such as CREATE INDEX". Column statistics come only from ANALYZE. So the opening case's new index changed the row count the planner starts from, and left 42 where it was. That is why the report stayed slow.

**The lab's version is more extreme.** `plan_lab.py` loads orders with three statuses only, `shipped`, `paid` and `created`. ANALYZE then puts all three in the MCV list, and their frequencies add up to 1. For `pending`, the code computes 1 − 1 − 0 = 0. The division is skipped, because 3 − 3 is not above 1. Then `clamp_row_est` raises the 0 to 1 row. So any count of pending orders, however large, gets `rows=1`, until the next ANALYZE. That is inferred from the source, and the lab prints the estimate so you can see it.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The lab, --rows 1,000,000. Expected, worked out from the source, not run │
├──────────────────────────────────────────────────────────────────────────┤
│ build      ANALYZE: MCV {shipped 0.60, paid 0.25, created 0.15}, sum 1   │
│ incident   UPDATE 400,000 orders to 'pending'. No ANALYZE                │
│            the file grows: new versions go to new pages, section 4.5     │
│ diagnose   'pending': 1 - 1 = 0, clamped to rows=1. Actual 400,000       │
│            the row count is scaled up by the larger file, see 72.1       │
│ team-fix   CREATE INDEX on status: rows=1 still                          │
│ fix        ANALYZE: 'pending' enters the MCV list at about 0.4, and      │
│            the estimate is close to the real 400,000                     │
└──────────────────────────────────────────────────────────────────────────┘
```

After the UPDATE, the file holds about 1,400,000 row versions, and 1,000,000 of them are live. Before ANALYZE, the planner scales the old `reltuples` of 1,000,000 by the larger page count. So it counts about 1,400,000 rows. The dead versions inflate the count. ANALYZE counts live rows only, so it stores `reltuples` near 1,000,000 and a frequency near 0.4 for `pending`. Both values are inferred from the docs' rules, not run. `plan_lab.py` prints `reltuples`, the scaled count and `most_common_freqs`, so you can check them.

**Correlated columns.** The AND row of the formula table multiplies selectivities. The docs, section 14.2.2, state the assumption behind it. The planner treats the conditions as independent, "an assumption that does not hold when column values are correlated". The docs' example, in section 72.2, has 10,000 rows with `a = b = i % 100`:

- `WHERE a = 1 AND b = 1` gets 1% × 1% = 0.01%, so `rows=1`. The actual count is 100.
- After `CREATE STATISTICS ... (dependencies) ON a, b` and ANALYZE, the estimate is `rows=100`.
- `GROUP BY a, b` estimates 1000 groups against an actual 100, until the statistics object also has `ndistinct`.

The course research repeated this on PostgreSQL 14.24 on 2026-10-17. It got the same numbers: 1 became 100, and 1000 became 100. One limit is verified from the same section. Functional dependencies help only with equality to constants and with IN lists of constants. They do not help ranges, LIKE, or comparisons of two columns. In the order data, `tenant_id` decides `region`, so the same fix applies to a filter on both.

**Three more controls of the statistics.** ANALYZE and CREATE STATISTICS are not the only levers. Three more decide how good an estimate is:

1. **An n_distinct override.** ANALYZE estimates n_distinct from its 30,000-row sample. A column whose values each appear only a few times can come out far too low. `ALTER TABLE order_events ALTER COLUMN order_id SET (n_distinct = -0.3333)` sets it by hand. A negative value is a fraction of the rows, so −0.3333 means one distinct order id per three events. The option overrides the estimates "made by subsequent ANALYZE operations", so it takes effect at the next ANALYZE. It takes only SHARE UPDATE EXCLUSIVE. Verified from the PostgreSQL 14 ALTER TABLE page, and from Rogov, "PostgreSQL 14 Internals", page 277. Join estimates divide by n_distinct, as the join row of the formula table shows. Whether the sample under-counts `order_id` here is inferred, not measured.
2. **A per-table analyze threshold.** The counter that autovacuum compares with 50 + 0.1 × reltuples is `n_mod_since_analyze` in `pg_stat_user_tables`. In the code it is `changes_since_analyze`. `system_views.sql` line 647 and `pgstatfuncs.c` line 196 map the column to it. `autovacuum.c` line 3255 compares it. All three are at REL_14_24. `ALTER TABLE orders SET (autovacuum_analyze_scale_factor = 0.01)` lowers the trigger for `orders` from 1,000,050 to 50 + 0.01 × 10,000,000 = 100,050 changed rows. The incident passed even that within minutes. So the setting shortens the stale window and does not remove it, which is inferred from the arithmetic.
3. **The ends of the histogram.** A range condition can reach the first or last histogram bound. Then the planner does not trust the stale bound. `selfuncs.c` at REL_14_24, lines 1082 to 1088, replaces "that endpoint with the true column min or max". It reads them from a plain B-tree index on the column, and line 6031 skips every other kind of index. The comment says this "ameliorates misestimates when the min or max is moving". So `created_at >= now() - interval '1 hour'`, with an index on `created_at`, gets a sensible estimate an hour after the last ANALYZE. The opening case's `status = 'pending'` gets no such help, because it is an equality on a value outside the MCV list. That comparison is inferred from the code, not run.

**How wrong estimates are in practice.** Leis and others ran 113 join queries on an IMDB data set of 3.6 GB. They used PostgreSQL 9.4, with all data in memory. Verified from the paper, Table 1 and section 3.2:

- For single-table conditions, PostgreSQL's q-error had a median of 1.00 and a 90th percentile of 2.08. The 95th was 6.10, and the maximum 207.
- For joins, 16% of PostgreSQL's estimates with 1 join were off by a factor of 10 or more. That grew to 32% with 2 joins and 52% with 3. The paper reports that the errors grow exponentially with the number of joins. Most of the estimates were too low.

So most single-table estimates are close, and errors multiply through joins. The research did not repeat them on PostgreSQL 14. Treat them as the shape of the problem, not as your numbers.

**The plan the application gets: custom and generic plans.** So far the planner could see every value in the query. An application often sends something else. A prepared statement is a query that the server parses once and then runs many times with new parameter values. Drivers create them without being asked. psycopg 3 prepares a query on the server after it has run more than `prepare_threshold` times on one connection. The default is 5. Verified from the psycopg 3 documentation. The reporter of PostgreSQL BUG #17540 used pgx, a Go driver. He wrote that he "wasn't even aware I was using prepared statements".

A prepared statement runs with one of two kinds of plan. Verified from the PostgreSQL 14 docs for PREPARE:

- A **custom plan** is made for one execution, with the parameter values of that call.
- A **generic plan** is made once and reused for every value. It saves the planning time.

`choose_custom_plan()` in `plancache.c` picks between them:

```c
/* from plancache.c, REL_14_24, lines 1059 to 1077. Comments cut, logic unchanged */
	if (plansource->num_custom_plans < 5)
		return true;                     /* true: make a custom plan */
	avg_custom_cost = plansource->total_custom_cost / plansource->num_custom_plans;
	if (plansource->generic_cost < avg_custom_cost)
		return false;                    /* false: use the generic plan */
	return true;
```

So the first five executions get custom plans. From the sixth, the server uses the generic plan if its estimated cost is below the average custom cost. Each custom cost also carries a planning charge, at lines 1125 to 1127. It is 1000 × `cpu_operator_cost` × (range-table entries + 1). The range table is the plan's list of tables, plus one entry for each `JOIN` clause. So a two-table query written with `JOIN ... ON` has three entries, and its charge is 2.5 × 4 = 10. The join's entry is kept by `setrefs.c` at REL_14_24, line 369. Once the generic plan wins, the average of the five custom plans no longer changes. So the generic plan keeps winning, which is inferred from the code.

**Why a generic plan misestimates.** It cannot see the value of `$1`. So `var_eq_non_const()`, in `selfuncs.c` at REL_14_24, lines 508 to 522, estimates `col = $1` as (1 − null_frac) / n_distinct. The result is capped at the most common value's frequency. That is the average over all values. Take the opening case's report as an application would send it, with `WHERE o.tenant_id = $1`. With 1,000 tenants and 10,000,000 orders, the generic estimate is 10,000 orders for every tenant. Suppose one tenant holds 10% of the orders, which is an example. It really has 1,000,000, and it gets the plan of an average tenant. By the arithmetic of section 4.4, that can be a nested loop.

| | Custom plan | Generic plan |
|---|---|---|
| Made | for each execution, with its values | once, for any value |
| Estimate for `tenant_id = ...` | the MCV list or the leftover formula | (1 − null_frac) / n_distinct |
| In EXPLAIN | the value, such as `tenant_id = 7` | the symbol `$1` |
| In `pg_prepared_statements`, new in 14 | counted in `custom_plans` | counted in `generic_plans` |
| Planning time | paid on every execution | paid once |

**A real case, with its conditions.** PostgreSQL BUG #19076 was reported on 2025-10-07, on PostgreSQL 17.6. The application's driver created prepared statements. The query joined two tables and filtered on `tenant_id = $1` and `status = $2`. Verified from the report:

- Executions 1 to 5 used a custom plan, the parallel Hash Join shown in section 4.1. Its top node took 103.8 ms.
- From execution 6, the generic plan ran, "even if I do not change the parameters". It was a Nested Loop, and its top node took 7,179.9 ms.
- The generic plan's scan of `contacts` estimated 354 rows and returned 864,365. Its inner index scan ran 864,365 loops.
- An ANALYZE and a statistics target of 1,000 did not help.

Laurenz Albe answered on the list that the choice of plan "is a heuristic". He guessed that the first five executions used values with few rows, which the report does not show. He suggested `plan_cache_mode = force_custom_plan` for that statement. BUG #17540, on PostgreSQL 14.4 in 2022, has the same shape. Its reporter measured the generic plan as "over 6500x slower", and set `force_custom_plan` for the whole database. So this is the opening case's failure, a nested loop picked from a low estimate, with a different cause. The statistics were fresh. The generic plan's average estimate was wrong for this value.

**The signals and the fixes.**

1. `EXPLAIN EXECUTE name(values)` shows the plan that the cache chose. A `$1` in it means generic, by the PREPARE docs.
2. `SELECT name, generic_plans, custom_plans FROM pg_prepared_statements` counts each kind in the session. The columns are new in PostgreSQL 14, from its release notes.
3. PostgreSQL 16 adds `EXPLAIN (GENERIC_PLAN)`. It shows the generic plan of a query that has `$1` and no values. Verified from the 16 release notes.
4. `plan_cache_mode` is `auto` by default. `force_custom_plan` plans every execution, and `force_generic_plan` never replans. The docs, section 20.7, say it "is considered when a cached plan is to be executed". So `ALTER ROLE reporting SET plan_cache_mode = force_custom_plan` fixes the report's role. The rest of the application keeps its planning savings. That use is inferred from the setting's scope.
5. A partitioned table needs this too. A generic plan prunes partitions only at executor start, as section 4.6 shows.

Put psycopg's threshold of 5 together with the server's five custom plans. Then a query on one connection would first meet a generic plan around its eleventh execution. That is inferred from the two documents and not run. E13 shows the switch on the lab's data with `plan_cache.py`, which uses SQL PREPARE.

**The failure: a bulk change between two ANALYZEs.** A backfill fills a new or changed column for existing rows. It can change a column's values in minutes. So can an import or an incident. Autovacuum reaches the table later, or never, if it is off for that table. Every plan in between uses the old distribution. The fix is part of the change itself: run `ANALYZE <table>` right after any bulk load or bulk update. A per-table `autovacuum_analyze_scale_factor`, the second control above, makes the automatic ANALYZE come sooner on a large table. Raise the detail for a column with `ALTER TABLE ... ALTER COLUMN ... SET STATISTICS`, which also takes only `SHARE UPDATE EXCLUSIVE`.

The next section asks what the planner does with a correct estimate when it picks how to read the table.

**The sentence to remember:** an estimate is the row count times a selectivity from `pg_stats`. And `pg_stats` changes only at ANALYZE. A value missing from the MCV list gets the leftover fraction, shared by the other values. A generic plan gets the average over all values, whatever the value is.

**The trap:** answering a bad estimate with a new index, as the opening team did. The estimate stays wrong, and the build blocks writes while it runs.

**Try this now:** run `psql -h /tmp -p 5432 -d storage_lab -c "select attname, n_distinct, most_common_vals, most_common_freqs from pg_stats where tablename = 'p4_orders'"` after E4. Compute the estimate for one value by hand, then compare it with `EXPLAIN select * from p4_orders where status = 'paid'`.

---

## 4.3 — Access paths (sequential scan, index scan, index-only scan, bitmap scan, and the selectivity at which each wins)

Why this matters: after ANALYZE, the planner knows that 40% of the orders are pending. It then reads `orders` with a sequential scan and ignores the new index on `status`. A teammate calls that a bug. It is the cheapest plan by the planner's own arithmetic, and you can repeat that arithmetic by hand.

**Answer this first.** The course research built a table on PostgreSQL 14.24 on 2026-10-17. It has 1,000,000 narrow rows in 9,346 pages. A B-tree of 19 MB indexes a column `x` of random values. All settings were defaults, and the data was in memory. For `SELECT * FROM r WHERE x < k`, guess the plan when the condition selects:

1. one row
2. 1% of the rows
3. 40%
4. 45%

Then guess what changes when `x` is stored in index order.

**The mental model.** The planner has four ways to read one table, and it prices each one:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Four access paths. ─► is the order in which heap pages are read          │
├──────────────────────────────────────────────────────────────────────────┤
│ Seq Scan          heap: page 1 ─► 2 ─► 3 ─► ... ─► last. Every page,     │
│                   in file order. Each row is checked against the filter  │
│ Index Scan        index leaf ─► heap page 7 ─► page 2 ─► page 7 ─► ...   │
│                   rows in index order. A page can be read many times     │
│ Bitmap Heap Scan  index ─► a bitmap of matching pages, sorted            │
│                   heap: page 2 ─► 7 ─► 9. Each needed page once          │
│ Index Only Scan   index leaf only, when the index holds every column     │
│                   the query needs and the page is marked all-visible     │
└──────────────────────────────────────────────────────────────────────────┘
```

A plain index scan fetches rows in index order. For a column whose values are in random places on disk, that means a random heap page per row. A bitmap scan first collects the matching rows, then sorts their locations into physical order. The docs, section 14.1.1, call the bitmap "the mechanism that does the sorting". An index-only scan skips the heap for pages that the visibility map marks all-visible. VACUUM maintains that map, from the PostgreSQL 14 docs, section 25.1.4.

**The cost of each path.** Here are the formulas from `costsize.c` and `selfuncs.c` at REL_14_24. The defaults are from the PostgreSQL 14 docs, section 20.7.2. `cost_model.py` implements them, and its docstring names each line:

| Path | Heap pages read | Cost per heap page | CPU per row |
|---|---|---|---|
| Seq Scan | all T pages | `seq_page_cost` 1.0 | `cpu_tuple_cost` 0.01 + 0.0025 per condition |
| Index Scan | from the Mackert and Lohman formula, up to T | `random_page_cost` 4.0, moved toward 1.0 by correlation² | 0.01, plus 0.0075 per index entry |
| Bitmap Heap Scan | each needed page once, at most T | 4.0 − 3.0 × √(pages read / T) | 0.0125, plus 0.0075 per index entry |
| Index Only Scan | as Index Scan, times the share of pages not all-visible | as Index Scan | as Index Scan |

The Mackert and Lohman formula estimates how many distinct pages N random row fetches touch, given the cache size `effective_cache_size`. When the table fits in that cache, it is `2TN / (2T + N)`, capped at T. The bitmap formula charges almost `random_page_cost` for a few scattered pages, and only `seq_page_cost` once it reads every page. From `phase04_planning/cost_model.py:195`:

```python
# from phase04_planning/cost_model.py:195, the body of bitmap_scan(). A two-line comment removed, logic unchanged
    tuples, idx = _index_part(sel, t, p)
    idx += 0.1 * p.cpu_operator_cost * tuples              # line 1069
    T = max(t.pages, 1.0)
    pf = (2.0 * T * tuples) / (2.0 * T + tuples)           # compute_bitmap_pages
    pf = T if pf >= T else math.ceil(pf)
    if pf >= 2.0:
        per_page = p.random_page_cost - (p.random_page_cost - p.seq_page_cost) * math.sqrt(pf / T)
    else:
        per_page = p.random_page_cost
    return idx + pf * per_page + tuples * (p.cpu_tuple_cost + quals * p.cpu_operator_cost)
```

**The arithmetic at 40% and 45%.** Use the research's table. T is 9,346 pages and N is 1,000,000 rows. The index has about 2,432 pages, which is 19 MB in 8 kB pages.

- **Seq Scan:** 9,346 × 1.0 + 1,000,000 × 0.0125 = 21,846. PostgreSQL 14.24 printed exactly `cost 21846.00` for it, measured by the course research.
- **Bitmap at 40%:** 400,000 rows. The index part is 973 pages × 4.0 = 3,892. Add 400,000 × 0.0075 = 3,000, and 100 for the bitmap. Mackert and Lohman gives more than T, so all 9,346 pages are read. Each costs 4.0 − 3.0 × √1 = 1.0. The rows cost 400,000 × 0.0125 = 5,000. The total is 3,892 + 3,000 + 100 + 9,346 + 5,000 = 21,338, plus 0.4 for the B-tree descent.
- **Bitmap at 45%:** 4,380 + 3,375 + 112.5 + 9,346 + 5,625 = 22,839.
- **Index Scan at 40%:** the heap part alone is 9,346 pages × 4.0 = 37,384. The correlation is near 0.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Estimated cost, research table. 1 char = 1,000. By hand from the model   │
├──────────────────────────────────────────────────────────────────────────┤
│ 40%  Seq Scan     ██████████████████████              21,846             │
│      Bitmap       █████████████████████               21,338  ◄ cheapest │
│      Index Scan   ████████████████████████████████████████████ 48,276 ►  │
│ 45%  Seq Scan     ██████████████████████              21,846  ◄ cheapest │
│      Bitmap       ███████████████████████             22,839             │
├──────────────────────────────────────────────────────────────────────────┤
│ the bitmap reads every page once at 1.0, then pays more CPU per row than │
│ the seq scan. Between 40% and 45% the CPU decides                        │
└──────────────────────────────────────────────────────────────────────────┘
```

The Index Scan's 48,276 is 37,384 for the heap, 3,892 + 3,000 for the index and 4,000 for the rows. Its bar is cut to fit.

**What the research measured.** These are the planner's choices by estimated cost, on the table above. It has about 107 rows per page and `correlation(x) = 0.0004`:

| Rows selected | Plan |
|---|---|
| 1 row | Index Scan |
| 0.001% to 40% | Bitmap Heap Scan |
| 45% and above | Seq Scan |
| `SELECT x` only, 0.1% to 50% | Index Only Scan |
| `random_page_cost = 1.1`, at 30% and 50% | Index Scan |

So the answers are: Index Scan, Bitmap Heap Scan, Bitmap Heap Scan, and Seq Scan. The model reproduces the first three rows by hand, and `cost_model.py --self-test` asserts each of them. At `random_page_cost = 1.1` and 50%, the model also picks the Index Scan, at 20,369 against 20,809 for the bitmap. The model leaves out small terms, so treat any gap under a few percent as a tie. At 30% it puts the bitmap 0.7% below the Index Scan that the research saw.

These switch points are this table's result. They are not general percentages. The research did not time the queries, so the cheapest cost was not shown to be the fastest plan. It inferred that row width, correlation and the cache settings move the switch, and E3 lets you change each one.

The research ran at all defaults, so parallel plans were allowed, and none won. Section 4.1's third rule explains why. A Gather charges `parallel_tuple_cost`, 0.1, for each row it passes up. At 40%, a parallel scan would cost 9,346 + 12,500 / 2.4 = 14,554. The Gather adds 1,000, and 400,000 × 0.1 = 40,000. That is 55,554 against the bitmap's 21,338. So a parallel plan wins when the work below the Gather removes most rows. A count or a selective filter does that. That is inferred from the formulas, not run.

**What moves the switch.** Four things:

1. **Correlation.** The docs for `pg_stats` define `correlation` as the "statistical correlation between physical row ordering and logical ordering of the column values". Near 1 or −1, an index scan is "estimated to be cheaper". In the model, `x` in index order at 10% costs 3,664 as an Index Scan against 12,347 for the bitmap. That answers the last question. The Index Scan wins at 10%, because its heap reads become one sequential run.
2. **`random_page_cost`.** The PostgreSQL 14 and 18 docs keep the default at 4.0. It is that low "because the majority of random accesses to storage, such as indexed reads, are assumed to be in cache". The "90%" cached and the SSD value "1.1" that many blogs quote come from the PostgreSQL 10 docs. The research did not find that text in 13, 14 or 18.
3. **`effective_cache_size`.** Default 4GB. It enters the Mackert and Lohman formula for index scans. The research set it to 64MB and saw no plan change from 0.1% to 30% on this table.
4. **Row width.** Wider rows mean more pages for the same rows. The seq scan cost grows with pages, and the index cost grows with rows, so the switch moves.

**Two signals in the plan: heap fetches and lossy pages.** Both show in EXPLAIN ANALYZE. Both explain an index path that is slower than its cost. Verified from Rogov, "PostgreSQL 14 Internals", sections 20.2 and 20.3, on PostgreSQL 14:

- An Index Only Scan prints `Heap Fetches`. It counts the rows the scan checked in the heap, because their page was not marked all-visible. Rogov's run shows `Heap Fetches: 132109` on a new table, and `Heap Fetches: 0` after VACUUM, for the same 132,109 rows. So an index-only scan on a table that VACUUM has not reached reads the heap like an index scan.
- A Bitmap Heap Scan prints `Heap Blocks: exact=... lossy=...`. When the bitmap does not fit in `work_mem`, some of its parts keep only the page and not the row. Every row on a lossy page is checked again, and the plan counts the rejects as `Rows Removed by Index Recheck`. Rogov's run with `work_mem = '512kB'` shows `Heap Blocks: exact=5178 lossy=8269` and `Rows Removed by Index Recheck: 1145721`. With more memory, the same query showed `exact=13447`.

`explain_tools.py` prints all three keys for every node that has them.

**The failure: forcing the index.** The planner's `enable_*` settings make a path look very expensive. The docs, section 14.1.1, call this "a crude tool, but useful" for seeing other plans. It is not a fix.

```sql
-- WRONG: for the whole application, because one report used a seq scan.
-- At 40% the forced plan is the Index Scan, with a random heap read per row.
-- At random_page_cost 1.0 the model prices it at about 17,319: 973 + 3,000
-- for the index, 9,346 for the heap and 4,000 for the rows. That is below
-- the Seq Scan's 21,846. If those reads are not cached, the default 4.0
-- prices the same plan at 48,276, as in the diagram.
ALTER DATABASE app SET enable_seqscan = off;
ALTER DATABASE app SET random_page_cost = 1.0;

-- RIGHT: fix the input that was wrong, then let the planner choose.
ANALYZE orders;                         -- the estimate of section 4.2
-- and, if the column is stored in index order and the cost model says so,
-- check the plan per query with EXPLAIN (ANALYZE, BUFFERS), on one session:
SET enable_seqscan = off;               -- only to compare, then RESET
```

A low-selectivity index also has a write cost. Phase 2, section 2.2, showed the reason. An UPDATE adds an entry to every index of the table. The exception is a heap-only tuple update, HOT, which stays on its page and changes no indexed column. An index on `status` that no plan uses still pays that cost on every order change.

So the planner chose the sequential scan for a reason. The condition kept 40% of a table whose order is unrelated to `status`, so every plan reads almost every page. On the research's table, 40% is just below the switch. The bitmap costs 21,338 there, 2.3% below the sequential scan's 21,846. The `orders` table has wider rows and its own index size, so its switch can fall below 40%. That is inferred from the formulas, and not computed for `orders`. The statistic that would change the planner's mind is the selectivity: at 1% the bitmap wins. Correlation would also change it, if the pending orders sat together on disk. The next section moves from one table to two: how the planner joins `orders` to `order_events`.

**The sentence to remember:** the planner prices every path from pages, rows and correlation. A plain index scan pays a random page per row on an uncorrelated column. Beyond a few tens of percent, a bitmap or a sequential scan is cheaper.

**The trap:** forcing an index with `enable_seqscan = off` or a low `random_page_cost` for everyone. The one report improves, and every query that needed a sequential scan gets a random read per row.

**Try this now:** run `uv run python phase04_planning/cost_model.py --sweep`, then `uv run python phase04_planning/access_paths.py`. Compare the model column with the planner column, and find the row where they disagree, if any.

---

## 4.4 — Joins (nested loop, hash, merge: how the planner picks, and how to see it picked wrong)

Why this matters: the report joins `orders` to `order_events`. The join method is chosen from the row estimates of section 4.2. With 42 expected pending orders, one method is cheapest. With 4,000,000, another is cheaper by a wide margin. The 9 seconds came from the join, not from the scan.

**Answer this first.** The PostgreSQL 14 docs, section 14.1.1, join `tenk1` to `tenk2`, two tables of 10,000 rows, on `unique2`. Both have an index on `unique2`. Guess the join method for each filter on `tenk1`:

1. `unique1 < 10`, which keeps 10 rows of `tenk1`
2. `unique1 < 100`, which keeps 100 rows
3. the same `unique1 < 100`, joined to `onek`, a table of 1,000 rows

And one number: the outer side costs 39.47 and returns 10 rows, and one inner index lookup costs 7.91. What does a nested loop cost, before CPU time for the join itself?

**The mental model.** There are three join methods. Each one fits a different shape of input:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Three join methods                                                       │
├──────────────────────────────────────────────────────────────────────────┤
│ NESTED LOOP   for each outer row ──► run the inner scan once             │
│               cost = outer + rows(outer) x inner                         │
│               good: few outer rows, an index on the inner join key       │
├──────────────────────────────────────────────────────────────────────────┤
│ HASH JOIN     build: read one input into a hash table in memory          │
│               probe: read the other input, look up each row              │
│               cost: one pass over each input. Memory: work_mem x         │
│               hash_mem_multiplier, or batches that spill to disk         │
├──────────────────────────────────────────────────────────────────────────┤
│ MERGE JOIN    both inputs sorted on the key ──► walk them side by side   │
│               the order comes from an index scan or from a Sort node     │
└──────────────────────────────────────────────────────────────────────────┘
```

The docs' three plans, verified from section 14.1.1, are the answers:

1. `unique1 < 10`: Nested Loop, `cost=4.65..118.62`. The docs explain the cost. It is the outer scan, "plus one repetition of the inner scan for each outer row (10 * 7.91, here), plus a little CPU time for join processing". So 39.47 + 10 × 7.91 = 118.57, and the CPU time makes 118.62.
2. `unique1 < 100`: Hash Join, `cost=230.47..713.98`. The 100 outer rows go into the hash table, and a sequential scan of `tenk2` probes it.
3. `tenk1` joined to `onek`: Merge Join, `cost=198.11..268.19`. `tenk1` arrives in key order from an index scan, and `onek` is sorted. With `enable_sort = off`, both sides use index scans, and the docs note the planner thinks that is "about 12% more expensive".

**A cache inside nested loops: Memoize, new in PostgreSQL 14.** A nested loop runs its inner scan once per outer row. It does so even when many outer rows carry the same key. A Memoize node keeps the inner scan's rows for each key it has already seen. The 14 release notes say it "can be disabled via server parameter enable_memoize". Rogov, page 361, shows it on PostgreSQL 14. A nested loop over 113 flights looks up each flight's aircraft, and all 113 have the same aircraft type. Here are his lines, with the spacing that `explain.c` prints:

```text
->  Memoize (actual rows=1 loops=113)
      Cache Key: f.aircraft_code
      Cache Mode: logical
      Hits: 112  Misses: 1  Evictions: 0  Overflows: 0  Memory Usage: 1kB
```

One miss read the row, and the 112 hits came from the cache. The cache is a hash table, and the docs, section 20.4, count memoize nodes against `work_mem`. Rogov adds that large `Evictions` numbers mean the cache was too small. A wrong estimate of the distinct keys can cause that. In the opening case each order is its own key, so a Memoize over `order_events` would miss on every row. That is inferred.

**How the planner picks.** It estimates the join's output first. Then it prices every method for every join order it considers, and keeps the cheapest. The docs, section 72.1, say "the join relation size is estimated before any particular join plan has been considered". The search builds larger joins from smaller ones by dynamic programming, the bottom-up method of IBM's System R optimizer. CMU 15-445's notes for lecture 15, section 11, teach that method. Three settings limit the search, from the PostgreSQL 14 docs, section 20.7:

| Setting | Default | What it does |
|---|---|---|
| `from_collapse_limit` | 8 | subqueries are merged into the upper query up to this many FROM items |
| `join_collapse_limit` | the same as `from_collapse_limit`, 8 | explicit JOINs are reordered up to this many items. 1 keeps the written order |
| `geqo_threshold` | 12 | at this many FROM items, a genetic search replaces the exhaustive one |
| `work_mem` | 4MB | memory per sort or hash before it spills to temporary files |
| `hash_mem_multiplier` | 1.0 in PostgreSQL 14 | a hash table gets work_mem x 1.0. PostgreSQL 15 raised the default to 2.0, from its release notes |

The `work_mem` and `hash_mem_multiplier` rows are from section 20.4 of the same docs.

**How a low estimate picks the nested loop.** Put the opening case's numbers into the nested-loop formula. The sizes of `order_events` are an example: 30,000,000 rows in 150,000 pages.

- **Nested loop, as planned:** the scan of `orders`, 325,250, plus 42 × 8.59 = 361 for the lookups. About 325,611, the cost in the plan of section 4.1.
- **Hash join, as planned:** the same scan of `orders`, plus a full scan of `order_events`. That scan is 150,000 + 30,000,000 × 0.01 = 450,000. About 775,250 before hashing. So at 42 rows the nested loop is cheaper by about 450,000.
- **Nested loop, with the true 4,000,000 rows:** 325,250 + 4,000,000 × 8.59 = 34,685,250. The hash join's cost barely moves, because it reads `order_events` once either way.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The same join priced at two estimates. Example sizes, model arithmetic   │
├──────────────────────────────────────────────────────────────────────────┤
│ estimate 42      nested loop  325,611     ◄ chosen                       │
│                  hash join    775,250+                                   │
│ estimate 4 M     nested loop  34,685,250                                 │
│                  hash join    775,250+    ◄ would be chosen              │
├──────────────────────────────────────────────────────────────────────────┤
│ at 4 M rows the plan that ran costs 34,685,250 / 775,250 = 45 times the  │
│ alternative, by the planner's own model                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

The nested loop's cost grows with the outer rows times the inner cost. The hash join's grows with the sum of the two inputs. So an underestimate on the outer side favors the nested loop, and the true count punishes it the most.

**What the research paper found.** Leis and others traced the worst plans in their study to this mistake. Verified from the paper, section 4.1 and Figure 6, on PostgreSQL 9.4. Their timeouts came from nested-loop joins without an index lookup, which a very low estimate had picked. They disabled those joins and added the hash-table resizing of 9.5. Then fewer than 4% of the queries were more than 2 times slower than with true cardinalities. PostgreSQL 14 has that resizing, so the research inferred that Figure 6 looks different there. It did not measure it.

**How to see it picked wrong.** In `EXPLAIN (ANALYZE, BUFFERS)`:

1. Find the join node, and its outer input, the first child.
2. Compare the outer input's estimated rows with its actual rows.
3. Multiply the inner node's actual rows by its loops. A nested loop whose inner `loops` is far above the outer estimate is the signature.
4. For a hash join, look at `Batches` on the Hash node. More than 1 means the hash table did not fit. The docs, section 14.1.2, say that then "there will also be disk space usage involved".

Then fix the estimate, as section 4.2 showed. Do not turn off `enable_nestloop` for the application. As section 4.3 said, these settings are for comparing plans. `plan_lab.py --case join-methods` uses them that way. It prices one join with each method forced, at three outer sizes. The planner's choice should be the cheapest of the three.

**When a sort or a hash does not fit in `work_mem`.** The table above gives the limits: `work_mem` for a sort, and `work_mem` × `hash_mem_multiplier` for a hash table. Beyond its limit, the operation writes temporary files. The docs, section 20.4, add the warning that matters in production. One query can run several such operations, and "several running sessions could be doing such operations concurrently". So the total memory can be many times `work_mem`. The plan shows a spill in four lines. They are from Rogov, "PostgreSQL 14 Internals", pages 374, 386 and 393, on PostgreSQL 14. The spacing is the one `explain.c` prints:

```text
Sort Method: external merge  Disk: 17136kB
Buckets: 65536  Batches: 64  Memory Usage: 2277kB
Buffers: shared hit=7236 read=6211, temp written=10858
Batches: 5  Memory Usage: 4145kB  Disk Usage: 98184kB
```

- **The first line is a Sort that spilled.** `external merge` wrote sorted runs to disk and merged them. A sort in memory prints `quicksort` and `Memory` instead.
- **The second and third lines are one Hash node.** `Batches: 64` means the input was split into 64 parts. All but the first part went to temporary files. The docs, section 14.1.2, say this disk use "is not shown" on the Hash line. The `temp written` count of BUFFERS shows it.
- **The fourth line is a HashAggregate that spilled.** HashAggregate can spill since PostgreSQL 13. The 13 release notes say that before, a chosen hash table "would be kept in memory no matter how large it got". So on PostgreSQL 12, a low estimate of the groups could use memory without a limit. That last step is inferred from the note.

Across the server, `temp_files` and `temp_bytes` in `pg_stat_database` count every temporary file. `log_temp_files`, −1 by default, logs each one when it is deleted. Verified from the PostgreSQL 14 docs, sections 20.8 and 28.2. So raise `work_mem` for the one report that needs it, with `SET work_mem = '64MB'` in its session. A raise for the whole server is multiplied by every concurrent sort and hash. CMU 15-445's notes for lectures 11 and 12 teach the algorithms behind these lines. They are external merge sort, and hash joins that partition an input that does not fit. Try it with `explain_tools.py --set work_mem=64kB`, as E15 does.

**The failure: a plan that was right yesterday.** At 09:00, almost no order was pending. The nested loop was the right plan then. Nothing in the query or the indexes changed. Only the data did. A plan is a function of the statistics. So a plan regression after a bulk change is a statistics problem first.

The incident's UPDATE of 4,000,000 rows also did something else. Each updated row left its old version behind. The next section is about those versions.

**The sentence to remember:** a nested loop costs the outer rows times the inner lookup. A hash join costs one pass over each side. So a low outer estimate makes the nested loop look cheap, and the true count makes it expensive.

**The trap:** reading only the slowest node. The time shows up in the join's inner scan, while the cause is the outer scan's estimate one level below.

**Try this now:** run `uv run python phase04_planning/plan_lab.py --case join-methods`. For each outer size, check that the planner's row matches the cheapest forced row. Note the outer size where the method changes.

---

## 4.5 — Vacuum and bloat (MVCC's garbage, transaction-ID wraparound, and the table that keeps growing after deletes)

Why this matters: Phase 3, section 3.2, showed that an UPDATE writes a new row version. The old one stays in place, with its `xmax` set to the updating transaction. Something must remove the old versions, or the table grows without limit. The same machinery also keeps a 32-bit transaction counter from stopping the database.

**Answer this first.** Three questions about `orders`, 10 million rows, autovacuum at its defaults:

1. After the incident's UPDATE of 4,000,000 rows, how many dead row versions are there? Does the file grow? After how many dead rows does autovacuum start a VACUUM of this table?
2. A nightly job deletes the oldest 1,000,000 orders, and the new day inserts 1,000,000. VACUUM runs every night. Yet the file is larger every morning. Name two causes that are not "VACUUM did not run".
3. A database shows `age(datfrozenxid)` = 1,900,000,000 on PostgreSQL 14. How many more transaction IDs can it assign before it refuses new ones?
4. An autovacuum of `orders` "to prevent wraparound" has run for an hour. A deploy runs `DROP TRIGGER` on `orders` with no `lock_timeout`. What happens to the checkout's INSERTs and SELECTs?

**The mental model.** A snapshot records which transactions had finished when a statement or transaction began, as Phase 3, section 3.2, showed. A dead version is a row version that no snapshot can still see. VACUUM finds dead versions and removes them from the table and from every index. It marks their space free for new rows. The PostgreSQL 14 docs, section 25.1.2, add the limit that surprises people. Standard VACUUM "will not return the space to the operating system". The one exception is empty pages at the end of the table. So VACUUM stops growth. It does not shrink a file. Bloat is the name for that extra space. It is the dead versions, plus the free space that the table holds and does not use.

A version is removable only when it died before the oldest snapshot that any open transaction still holds. Call that point the cleanup horizon. One old snapshot holds back the horizon for every table in the database.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One order's versions, and what VACUUM may remove. Times are an example   │
├──────────────────────────────────────────────────────────────────────────┤
│ 10:00  v1 status=created   replaced by v2 at 10:05 ─► dead               │
│ 10:05  v2 status=pending   replaced by v3 at 11:00 ─► dead               │
│ 11:00  v3 status=paid      live                                          │
├──────────────────────────────────────────────────────────────────────────┤
│ no old snapshot           VACUUM removes v1 and v2. Their space is free  │
│ a report began 10:30      v1 removable. v2 kept: the report's snapshot   │
│ and is still open         may still read it. Kept until the report ends  │
├──────────────────────────────────────────────────────────────────────────┤
│ removable = died before the oldest open snapshot                         │
└──────────────────────────────────────────────────────────────────────────┘
```

**When autovacuum runs.** The PostgreSQL 14 docs, section 25.1.6, give the rule. A table is vacuumed when its dead rows pass 50 + 0.2 × `reltuples`. The two numbers are `autovacuum_vacuum_threshold` and `autovacuum_vacuum_scale_factor`, section 20.10. Inserts have their own trigger in PostgreSQL 14, with a threshold of 1,000 and the same 0.2. Other defaults from the same sections:

| Setting | Default in 14 | What it means |
|---|---|---|
| `autovacuum_naptime` | 1min | one worker start per database per minute |
| `autovacuum_max_workers` | 3 | at most three tables vacuumed at once. In 14 it changes only at server start |
| `autovacuum_work_mem` | −1, so `maintenance_work_mem`, 64MB | memory for the list of dead rows. Up to PostgreSQL 16, vacuum used at most 1GB of it. PostgreSQL 17 removed that limit, from its release notes |

So the first answer is: 4,000,000 dead versions, and the file grows. The pages were full, so most new versions went to new pages. Autovacuum starts after 50 + 0.2 × 10,000,000 = 2,000,050 dead rows, so this UPDATE passed the trigger. On a very large table the 0.2 is a long wait. A table of 1,000,000,000 rows waits for 200,000,050 dead rows. PostgreSQL 18 adds `autovacuum_vacuum_max_threshold` as a cap on that sum, with a default of 100,000,000. Verified from the PostgreSQL 18 docs, section 19.10.1.

**The throttle: why autovacuum falls behind on a large table.** Autovacuum does not run at full speed. It spends a budget of cost units, then naps, then goes on. Three settings give each page its cost:

- `vacuum_cost_page_hit` is 1, for a page found in `shared_buffers`.
- `vacuum_cost_page_miss` is 2, for a page read from outside. PostgreSQL 14 lowered it.
- `vacuum_cost_page_dirty` is 20 more, for a clean page that vacuum dirties.

The budget is `autovacuum_vacuum_cost_limit`. It is −1 by default, so it uses `vacuum_cost_limit`, 200. When a worker has spent it, it naps for `autovacuum_vacuum_cost_delay`, 2 ms since PostgreSQL 12, from its release notes. The docs, section 20.10, add one more rule. The limit "is distributed proportionally among the running autovacuum workers", so the sum of their budgets never passes it. Verified from the PostgreSQL 14 docs, sections 20.4.4 and 20.10, and from `vacuum.c` at REL_14_24, lines 2221 to 2231. A delay without its limit says nothing, because the limit sets how much work happens between two naps.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The autovacuum budget at PostgreSQL 14 defaults. Arithmetic, not run     │
├──────────────────────────────────────────────────────────────────────────┤
│ 200 units, then a 2 ms nap. Shared by every running worker               │
│                                                                          │
│ every page is   cost  pages per nap   ceiling for all workers together   │
│ cached             1          200     100,000 pages/s    781.3 MB/s      │
│ read               2          100      50,000 pages/s    390.6 MB/s      │
│ read + dirtied    22            9       4,545 pages/s     35.5 MB/s      │
│                                                                          │
│ 3 workers: about 66 units each. 6 workers: about 33 each. Same ceiling   │
│ a table with its own cost_limit 1000 leaves the sharing: 5x the ceiling  │
└──────────────────────────────────────────────────────────────────────────┘
```

The ceilings are upper bounds. They count only the naps, not the time of the work itself. The nine pages per nap in the worst case match Rogov, "PostgreSQL 14 Internals", page 118. Take a table of 500 GB whose pages all need reading and dirtying, an example size. One pass over its heap then takes at least 512,000 MB / 35.5 MB/s, about 14,400 seconds, or 4 hours. Its indexes come on top. Four rules follow:

1. **Raising `autovacuum_max_workers` alone does not speed vacuum up.** More workers split the same budget. Rogov, page 118, says to raise the workers and the cost limit "proportionally".
2. **Tune the large table, not the server.** A table's own storage parameters override the server's. `autovacuum.c` at REL_14_24, lines 3003 to 3009, also leaves a table with its own cost setting out of the sharing. Each storage parameter below takes only SHARE UPDATE EXCLUSIVE, from the ALTER TABLE page.
3. **A manual VACUUM is not throttled by default.** `vacuum_cost_delay` is 0 by default. Section 20.4.4 says that "disables the cost-based vacuum delay feature".
4. **A running autovacuum keeps its settings in 14.** Before 16, autovacuum honoured changed delay settings "only at the start of each relation". That is from the PostgreSQL 16 release notes. So a reload does not speed up the table that is being vacuumed now.

```sql
-- For one large, busy table. Values are an example.
ALTER TABLE orders SET (
  autovacuum_vacuum_scale_factor = 0.01,  -- 50 + 0.01 x 10,000,000 = 100,050 dead rows
  autovacuum_vacuum_cost_limit   = 1000   -- 5 times the budget, for this table only
);
```

**What vacuum tells you: one log line and three views.** By default, PostgreSQL 14's autovacuum writes nothing to the log. `log_autovacuum_min_duration` is −1, which "disables logging autovacuum actions", from the docs, section 20.8. PostgreSQL 15 changed the default to 10 minutes, from its release notes. On 14, set it to `'10s'` or lower, and each longer run writes one entry. Its format is in `vacuumlazy.c` at REL_14_24, lines 773 to 861. These are the format strings in the order they print, with a `%` field where each number goes:

```text
automatic vacuum of table "%s.%s.%s": index scans: %d
pages: %u removed, %u remain, %u skipped due to pins, %u skipped frozen
tuples: %lld removed, %lld remain, %lld are dead but not yet removable, oldest xmin: %u
index scan needed: %u pages from table (%.2f%% of total) had %lld dead item identifiers removed
index "%s": pages: %u in total, %u newly deleted, %u currently deleted, %u reusable
avg read rate: %.3f MB/s, avg write rate: %.3f MB/s
buffer usage: %lld hits, %lld misses, %lld dirtied
WAL usage: %lld records, %lld full page images, %llu bytes
system usage: %s
```

The `index "%s"` line repeats once for each index. The fourth line can also start `index scan not needed:` or `index scan bypassed:`. An `I/O timings:` line comes before the read rates when `track_io_timing` is on. Rogov, page 122, prints a whole entry in this shape on PostgreSQL 14.

Three fields answer the questions of this section:

- **`are dead but not yet removable, oldest xmin: N`** is the held cleanup horizon, in one line. A large count with an old `oldest xmin` points at the causes in the next part.
- **`index scans: N`** above 1 means the list of dead rows did not fit in memory. Each dead row takes a 6-byte TID in that list, the row address of Phase 2, section 2.2. That is `ItemPointerData`, from `vacuumlazy.c` lines 193 and 194. So 64MB holds about 64 × 1,048,576 / 6 = 11.18 million dead rows per pass. Every extra pass reads every index again. Rogov, page 122, shows `index scans: 3` on PostgreSQL 14, for 500,000 dead rows with `maintenance_work_mem` set to 1MB.
- **The first line names the kind of run.** Lines 773 to 782 print `automatic aggressive vacuum` for a freezing scan. They add `to prevent wraparound` for the forced run, which the wraparound part below explains.

| View | What to read |
|---|---|
| `pg_stat_progress_vacuum` | one row per running VACUUM: `phase`, `heap_blks_scanned` of `heap_blks_total`, `index_vacuum_count`, and `num_dead_tuples` of `max_dead_tuples` |
| `pg_stat_user_tables` | per table: `n_dead_tup`, `n_mod_since_analyze`, `n_ins_since_vacuum`, `last_autovacuum` and `autovacuum_count` |
| `pg_stat_activity` | an autovacuum's `query`, such as `autovacuum: VACUUM public.orders`, and `wait_event = VacuumDelay` while it naps |

The columns are verified from the PostgreSQL 14 docs, sections 28.2 and 28.4. The query text is from `autovacuum.c` at REL_14_24, lines 3314 to 3329. Many workers in `VacuumDelay` mean the budget limits vacuum, not the disk. That reading is inferred. `bloat.py --vacuum-signals` prints all of these for the lab's tables.

**Why a table keeps growing after deletes.** Four causes. The first three are verified from the PostgreSQL 14 docs, section 25.1.5. The fourth is inferred from section 25.1.2:

1. **A snapshot held open.** A long report, or a session left `idle in transaction`, keeps the horizon in the past. VACUUM runs and can remove nothing newer. Phase 3, section 3.2, gave the setting that ends such sessions, `idle_in_transaction_session_timeout`, off by default.
2. **A replication slot whose reader is gone.** The docs tell you to drop "old replication slots" before a wraparound VACUUM. A slot's `xmin` holds back VACUUM for every table. A physical slot gets an `xmin` only from a standby that has `hot_standby_feedback = on`, which is off by default. A logical slot sets `catalog_xmin` instead, which holds back only "catalog tuples". The more common harm of an abandoned slot is WAL. `max_slot_wal_keep_size` is −1 by default, so a slot "may retain an unlimited amount of WAL files". Verified from the PostgreSQL 14 docs for `pg_replication_slots` and section 20.6. The link between feedback and a physical slot's `xmin` is inferred. Replication itself is course 5.
3. **An old prepared transaction.** A two-phase commit that was never finished holds it too.
4. **Freed space in the wrong place.** VACUUM's free space lets later inserts reuse old pages. But if the deletes and the inserts happen faster than VACUUM, the inserts extend the file first.

The first three show up in one query each. Read `age(backend_xmin)` in `pg_stat_activity`, and `age(xmin)` and `age(catalog_xmin)` in `pg_replication_slots`. Then read `age(transaction)` in `pg_prepared_xacts`. `bloat.py --xid` prints all three. That answers question 2.

**Shrinking a file.** `VACUUM FULL`, `CLUSTER` and the table-rewriting forms of `ALTER TABLE` write a new copy without dead space. The docs, section 25.1.2, say they all require an ACCESS EXCLUSIVE lock. They also use extra disk "approximately equal to the size of the table" until they finish. So every read and write of the table waits for the whole rewrite. For a table that will grow again, the docs recommend moderately frequent standard VACUUMs instead. For a table emptied on a schedule, `TRUNCATE` frees the space at once. The price is that "strict MVCC semantics are violated".

**Index bloat, and rebuilding without blocking writes.** A B-tree also keeps the space of dead entries. Two releases lowered it. PostgreSQL 13 stores duplicate keys once, and PostgreSQL 14 removes expired entries "to prevent page splits", from their release notes. A low-cardinality index such as the one on `status` gains the most, which is inferred. When a table or an index must still be rebuilt, four tools exist:

| Tool | What it does | Lock and cost |
|---|---|---|
| `pgstattuple`, `pgstattuple_approx` | measure dead rows and free space | `pgstattuple` "always performs a full-table scan". `pgstattuple_approx` skips pages that the visibility map marks all-visible. Docs F.31 |
| `REINDEX INDEX CONCURRENTLY`, PostgreSQL 12 and later | builds a new index beside the old one, then swaps them | takes no locks "that prevent concurrent inserts, updates, or deletes". Two scans, a wait for older transactions, and no transaction block. Only `REINDEX INDEX` can rebuild an invalid index concurrently |
| `pg_repack`, an extension outside core | rewrites a table and its indexes while traffic runs | needs a primary key, or a unique index on NOT NULL columns, and free disk about twice the table and its indexes. It takes "one exclusive lock at the beginning as well as one exclusive lock at the end" |
| `VACUUM FULL`, `CLUSTER` | rewrite the table in core | ACCESS EXCLUSIVE for the whole rewrite, as above |

The REINDEX rows are verified from the PostgreSQL 14 REINDEX page and the 12 release notes. A failed `REINDEX CONCURRENTLY` leaves an invalid index whose name ends in `_ccnew`. The docs say to drop it and run the command again. The pg_repack row is verified from its documentation.

Two ideas from Phase 2, section 2.2, reduce the garbage itself. A HOT update, defined in section 4.3, adds no index entries. It also needs free space on the row's page. A table's `fillfactor` below 100 leaves that free space on each page. An index on `status`, as in section 4.3, makes every status change a non-HOT update.

**The lab.** `bloat.py` makes the growth visible on 100,000 rows with autovacuum off for its table. Expected, worked out from the rules above, not measured:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ bloat.py, heap pages. 1 char = one table's worth of pages. Not run       │
├──────────────────────────────────────────────────────────────────────────┤
│ after load                  █          1x                                │
│ UPDATE every row            ██         about 2x: the pages were full     │
│ VACUUM                      ██         2x: space freed, file unchanged   │
│ UPDATE again                ██         2x: the new versions reuse it     │
│ H holds a snapshot, then                                                 │
│   UPDATE + VACUUM           ███        about 3x. VACUUM still frees the  │
│                                        versions that died before H       │
│   UPDATE + VACUUM           ███        about 3x: reuses that space. Now  │
│                                        nothing is removable              │
│ H commits, VACUUM, UPDATE   ███        3x: reused, still not returned    │
│ VACUUM FULL                 █          about 1x. A SELECT waits for it   │
└──────────────────────────────────────────────────────────────────────────┘
```

**Transaction ID wraparound.** A transaction ID is 32 bits. The docs, section 25.1.5, explain the consequence. IDs are compared modulo 2^32, so for every ID, two billion IDs count as older and two billion as newer. A row whose inserting ID falls more than two billion behind would look as if it came from the future. It would become invisible. So "it is necessary to vacuum every table in every database at least once every two billion transactions". VACUUM prevents it by freezing old rows, which marks them as older than every normal ID.

PostgreSQL 14 enforces this with fixed limits. The limits are verified from `varsup.c` at REL_14_0, and the settings from the PostgreSQL 14 docs, sections 20.10 and 20.11:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ age(datfrozenxid), PostgreSQL 14. Wrap limit = oldest + 2,147,483,647    │
├──────────────────────────────────────────────────────────────────────────┤
│ 0              200 M            1.6 B        2,107 M      2,144 M        │
│ ├────────────────┼────────────────┼────────────┼────────────┤            │
│                  │                │            │            └ new IDs    │
│                  │                │            │              refused    │
│                  │                │            └ WARNING: must be        │
│                  │                │              vacuumed within N       │
│                  │                └ vacuum_failsafe_age: vacuum stops    │
│                  │                  its cost naps and skips index        │
│                  │                  vacuuming. New in 14                 │
│                  └ autovacuum_freeze_max_age: a forced vacuum, even if   │
│                    autovacuum is off                                     │
├──────────────────────────────────────────────────────────────────────────┤
│ warning at wrap − 40,000,000, line 392. Stop at wrap − 3,000,000, 378    │
│ PostgreSQL 13 used 11,000,000 and 1,000,000                              │
└──────────────────────────────────────────────────────────────────────────┘
```

The failsafe is not the aggressive freezing scan described below. The PostgreSQL 14 docs, section 20.11, call it "VACUUM's strategy of last resort". When it triggers, vacuum no longer applies the cost-based delay, so it stops its naps. It also skips non-essential work, such as index vacuuming.

The stop limit is at an age of 2,147,483,647 − 3,000,000 = 2,144,483,647. So for question 3: 2,144,483,647 − 1,900,000,000 = 244,483,647 more IDs. The warning starts at 2,107,483,647, which is 207,483,647 away. Take an example rate of 1,000 write transactions per second. That gives 207,484 seconds, or 2.4 days, to the warning, and 2.8 days to the stop. Read-only transactions get no ID and do not count.

The 200 million default has a reason. The docs say it "translates to about 50MB of pg_xact storage", because the commit status takes two bits per transaction.

**Why a quiet table suddenly gets a full scan.** VACUUM freezes a row once its inserting transaction is older than `vacuum_freeze_min_age`, 50 million. A normal VACUUM skips pages that hold no dead rows, so it can leave old rows unfrozen. When the age of a table's `relfrozenxid` reaches `vacuum_freeze_table_age`, 150 million, VACUUM turns aggressive. The visibility map of section 4.3 keeps a second bit per page, besides all-visible. This all-frozen bit marks a page whose rows are all frozen. Rogov, page 126, shows both bits with the `pg_visibility` extension. An aggressive scan reads every page that is not marked all-frozen. Verified from the PostgreSQL 14 docs, sections 20.11 and 25.1.5. So a large table that only receives inserts can one day get a scan of every unfrozen page. Nothing in it changed, and the scan still reads it all. That is inferred from the two rules. The log line's word `aggressive` names such a run.

**Multixacts need freezing too.** Phase 3, section 3.4, showed the case. A row locked by several transactions at once stores a multixact ID in its `xmax`. A foreign-key check is the usual cause. Multixact IDs are also a 32-bit counter, so they wrap in the same way. The same settings exist with `multixact` in their names. `vacuum_multixact_freeze_min_age` is 5 million, `vacuum_multixact_freeze_table_age` is 150 million, and `autovacuum_multixact_freeze_max_age` is 400 million. Verified from the PostgreSQL 14 docs, sections 20.10, 20.11 and 25.1.5.1. Watch `mxid_age(datminmxid)` in `pg_database` beside `age(datfrozenxid)`. One difference changes the recovery steps. The docs say "replication slots do not directly hold back multixact cleanup". So for a multixact problem, look at old transactions and prepared transactions first. `bloat.py --xid` prints both ages.

**The forced vacuum does not give way to DDL.** A normal autovacuum gives way. The docs, section 25.1.6, say a conflicting lock request "will interrupt the autovacuum". `proc.c` at REL_14_24 shows how. The waiting process runs its deadlock check after `deadlock_timeout`, 1 s. If an autovacuum blocks it, line 1433, it sends the worker SIGINT at line 1489. The worker then logs `canceling autovacuum task`, from `postgres.c` line 3314. But line 1460 skips the signal when the worker vacuums to prevent wraparound. The docs say the same thing. Such an autovacuum "is not automatically interrupted", and its query in `pg_stat_activity` ends with `(to prevent wraparound)`. Two results follow:

- A table that receives DDL often may never finish a normal autovacuum, because each DDL statement cancels it. That is inferred from the rule.
- The forced vacuum holds SHARE UPDATE EXCLUSIVE for its whole run. Under the throttle above, that run can take hours on a large table.

**One outage: Joyent Manta, 2015-07-27.** Joyent's postmortem gives this sequence. It is verified from the archived copy, which does not name the PostgreSQL version. Only the times shown come from the post:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Joyent Manta, 2015-07-27, one metadata shard. UTC, from the postmortem   │
├──────────────────────────────────────────────────────────────────────────┤
│ 10:30:09  an autovacuum "to prevent wraparound" starts. It holds         │
│           SHARE UPDATE EXCLUSIVE on the table                            │
│           a component reconnects and runs DROP TRIGGER. It wants an      │
│           exclusive lock and waits behind the autovacuum                 │
│           every data-path query on the table waits behind DROP TRIGGER   │
│ 10:30     about 22% of all requests fail, near 27% at the peak           │
│ 14:11     PostgreSQL restarted. Service returns for 5 to 10 minutes,     │
│           then a new wraparound autovacuum and the same queue            │
│ hours     the vacuum scans the table and all its indexes, twice. The     │
│           team patches the process to skip the cost-based sleeps         │
│           it ends, and a few minutes later another one starts            │
│ 20:45     the error rate is back to zero                                 │
├──────────────────────────────────────────────────────────────────────────┤
│ the lock queue of section 4.7, held for hours by a vacuum that never     │
│ gives way                                                                │
└──────────────────────────────────────────────────────────────────────────┘
```

Three lessons, in order:

1. **The vacuum did not block the queries.** SHARE UPDATE EXCLUSIVE does not conflict with them. The post says "the autovacuum itself wasn't blocking all the data path queries". The waiting DROP TRIGGER blocked them. In PostgreSQL 14, DROP TRIGGER takes ACCESS EXCLUSIVE, from `trigger.c` at REL_14_24, line 1280. This is the soft block of the lock queue, which section 4.7 measures.
2. **The fix is section 4.7's rule.** Give every DDL statement a `lock_timeout`, so it leaves the queue and retries. Joyent ended the outage by making its wraparound settings less aggressive. Its lasting fix was to stop dropping and recreating the trigger.
3. **Check before a migration.** Look in `pg_stat_activity` for a query that ends in `(to prevent wraparound)` on the table. `locks.py --scenario wraparound` replays the sequence offline.

So the fourth answer: the DROP TRIGGER waits for the whole vacuum. Every INSERT and SELECT queues behind it, until the vacuum ends or the DROP TRIGGER gives up.

**What the error says, and a disagreement.** At the stop limit, PostgreSQL 14 prints `ERROR: database is not accepting commands to avoid wraparound data loss in database "mydb"`, from `varsup.c` line 129. Its hint, line 131, says to stop the postmaster and vacuum in single-user mode. The PostgreSQL 14 docs page was updated later and says the opposite. It is "not necessary or desirable to stop the postmaster or enter single user-mode". The docs' steps instead are:

1. Resolve old prepared transactions.
2. End long-running open transactions.
3. Drop old replication slots.
4. Run VACUUM in the database, not VACUUM FULL and not VACUUM FREEZE.

Follow the docs, not the hint. PostgreSQL 17 changed both the message and the hint, and 18 keeps the new text. REL_16_0 still has the old hint, at `varsup.c` lines 131 and 138. It reads "Stop the postmaster and vacuum that database in single-user mode". REL_17_0 has the new hint at lines 158 and 165. It reads "Execute a database-wide VACUUM in that database". The new message is at lines 156 and 163. REL_18_0 has the same text at the same lines.

**Two outages.** Both are first-party reports. Neither names its PostgreSQL version, which this course did not check:

- **Sentry, 2015-07-23.** Sentry was down for most of a US working day. Its post blames too high an `autovacuum_freeze_max_age` with the default of 3 workers. After hours of vacuum, the team truncated one large table and recovered within minutes. The post gives the stop margin as one million transactions, which matches PostgreSQL 13's limit, not 14's. Its new settings read as the throttle lesson above. `autovacuum_vacuum_cost_delay = 0` turns the throttle off, and `autovacuum_max_workers = 6` with `autovacuum_naptime = '15s'` adds workers. The post's own correction says `maintenance_work_mem = '10GB'` met a 1GB internal limit. PostgreSQL 17 removed that limit. It also set `autovacuum_freeze_max_age = 500000000` and `vacuum_freeze_min_age = 10000000`. These settings were checked in the saved text of the post.
- **Mandrill, by Mailchimp, 2019.** The outage ran from 05:35 UTC on February 4 to 22:09 UTC on February 5. That is about 40.5 hours. In November 2018, engineers had seen the transaction IDs climb to about half the limit at peak load. Their highest estimate for the vacuum was 40 days.

**The failure: alerting on the error instead of the age.** The first sign in the server log is the WARNING. It starts 37 million IDs before the stop, because the limits are 40 million and 3 million before wraparound. At an example rate of 3,000 IDs per second, that is about 3.4 hours. A VACUUM of a large table can take longer. Alert on `age(datfrozenxid)` against `autovacuum_freeze_max_age` instead, with the query of the docs, section 25.1.5. `bloat.py --xid` prints the distance to every limit.

The next section removes old data without leaving dead versions behind.

**The sentence to remember:** VACUUM removes versions that died before the oldest open snapshot. It frees their space without shrinking the file. Freezing keeps rows older than every transaction ID, and PostgreSQL 14 stops assigning IDs 3 million before wraparound.

**The trap:** looking for the cause of bloat in VACUUM's settings. The usual cause is one open transaction, slot or prepared transaction that holds the cleanup horizon back. VACUUM reports success while it removes nothing. When the cause really is speed, the second trap is raising `autovacuum_max_workers` alone. The workers share one budget, so the ceiling stays the same.

**Try this now:** run `uv run python phase04_planning/bloat.py --xid`. Find your oldest database age, and compute the transactions left before the forced autovacuum. Then run `bloat.py --vacuum-signals`, and find the budget per worker and the worst-case ceiling it prints.

---

## 4.6 — Partitioning (when it helps, when it hurts the planner, and pruning)

Why this matters: a nightly job that deletes old events creates the dead versions of section 4.5, every night. Partitioning `order_events` by month turns that delete into dropping one table. It also changes every plan on the table. Queries that name the partition key get faster, and queries that do not can get slower.

**Answer this first.** `order_events` is now partitioned by month on `created_at`, with 12 partitions and 30,000,000 rows. There is an index on `order_id` in every partition. Answer four questions:

1. `WHERE created_at >= '2026-03-01' AND created_at < '2026-04-01'`: how many partitions does the plan read?
2. `WHERE order_id = 123`: how many?
3. A prepared statement has `WHERE created_at >= $1 AND created_at < $2`, and runs with a generic plan, one plan for every parameter value. When can PostgreSQL skip the other months?
4. Can you add `PRIMARY KEY (id)` to the partitioned table?

**The mental model.** A partitioned table is a parent that holds no rows itself. Each row goes to the one partition whose bounds contain its partition key. Partition pruning is the planner or the executor removing the partitions whose bounds cannot match the query. The PostgreSQL 14 docs, section 5.11.4, give the rule that decides most answers. Pruning "is driven only by the constraints defined implicitly by the partition keys, not by the presence of indexes".

```
┌──────────────────────────────────────────────────────────────────────────┐
│ order_events, partitioned by month on created_at                         │
├──────────────────────────────────────────────────────────────────────────┤
│ WHERE created_at in March         Jan  Feb [Mar] Apr ... Dec             │
│                                   1 partition read: pruned at plan time  │
│ WHERE order_id = 123             [Jan][Feb][Mar][Apr]...[Dec]            │
│                                   12 index lookups: no key, no pruning   │
│ EXECUTE with $1 = March, generic [Mar]   Subplans Removed: 11            │
│                                   pruned at executor start               │
└──────────────────────────────────────────────────────────────────────────┘
```

**When pruning happens.** The docs, section 5.11.4, name three moments:

1. **At plan time,** when the values are constants in the query.
2. **At executor start,** for parameter values known then, such as those of a generic plan. Section 4.2 showed when an application gets one: from the sixth execution of a prepared statement. These partitions vanish from the plan, and EXPLAIN prints a `Subplans Removed` line. The docs add a warning: "any partitions removed by the partition pruning done at this stage are still locked at the beginning of execution".
3. **During execution,** for values that change while the query runs, such as the inner side of a nested loop. Then EXPLAIN ANALYZE shows the pruned partitions with fewer loops, or as `(never executed)`.

So the three rows of the diagram are the answers to the first three questions. For the fourth, the answer is no. The docs, section 5.11.2.3, cover keys. A unique or primary key on a partitioned table must include "all of the partition key columns". Each partition's index can only enforce uniqueness inside that partition. `PRIMARY KEY (id, created_at)` is allowed.

**When it helps.** The docs, section 5.11.1, list the benefits:

- The heavily used rows sit in one or a few partitions. Partitioning "effectively substitutes for the upper tree levels of indexes". So the hot parts of the indexes are more likely to fit in memory.
- A query that reads most of one partition can scan that partition in sequence. It avoids random index reads across the whole table.
- Bulk loads and deletes become adding or removing a partition. Dropping a partition avoids "the VACUUM overhead caused by a bulk DELETE".

The same section gives a rule of thumb. The benefits are worthwhile when the table "would otherwise be very large", larger than the server's memory. For the order events, removing a month is the main gain. A DELETE of one month leaves 30,000,000 / 12 = 2,500,000 dead versions for VACUUM. A DROP of that month's partition leaves none.

**When it hurts the planner.** Five costs, each verified from the PostgreSQL 14 docs:

1. **Queries without the key read every partition.** `order_id = 123` becomes twelve index lookups instead of one. The report of the running case joins on `order_id`, so it touches every partition unless it also filters on `created_at`.
2. **Planning time and memory grow with the partitions that remain after pruning.** Section 5.11.6 says the planner handles "up to a few thousand partitions fairly well". That holds if typical queries prune all but a few. Each partition a session touches also loads its metadata into that session's memory. The older inheritance method works "with up to perhaps a hundred child tables", section 5.11.5.
3. **Statistics of the parent.** The docs, section 25.1.3, say "the autovacuum daemon does not issue ANALYZE commands for partitioned tables". The partitions get their own statistics. A query planned against the whole parent needs a manual ANALYZE of the parent.
4. **Uniqueness only with the key,** as the fourth answer showed.
5. **No concurrent index build on the parent.** The CREATE INDEX docs of 14 and 18 both say: "Concurrent builds for indexes on partitioned tables are currently not supported". The workaround in section 5.11.2.2 is `CREATE INDEX ON ONLY` the parent, then `CREATE INDEX CONCURRENTLY` on each partition, then `ALTER INDEX ... ATTACH PARTITION` for each one.

**The locks of partition maintenance.** Adding and removing months is DDL, so it takes locks. Verified from the PostgreSQL 14 docs, section 5.11.2.2 and ALTER TABLE:

| Statement | Lock on the parent | Lock on the partition |
|---|---|---|
| `CREATE TABLE ... PARTITION OF` | ACCESS EXCLUSIVE | the new table |
| `ALTER TABLE ... ATTACH PARTITION` | SHARE UPDATE EXCLUSIVE | ACCESS EXCLUSIVE, and a scan unless a matching CHECK exists |
| `ALTER TABLE ... DETACH PARTITION` | ACCESS EXCLUSIVE | not stated in the pages read, not checked |
| `... DETACH PARTITION ... CONCURRENTLY`, new in 14 | SHARE UPDATE EXCLUSIVE, in two transactions | ACCESS EXCLUSIVE in the second |

A DEFAULT partition adds one more lock. The ALTER TABLE page says ATTACH also takes ACCESS EXCLUSIVE on the default partition, "if any". It also scans the default partition, to check that none of its rows belong in the new one. A CHECK constraint on the default partition that excludes the new bounds lets ATTACH skip that scan. Verified from the PostgreSQL 14 ALTER TABLE page.

So the routine that never blocks traffic on the parent has four steps:

1. Create next month's table on its own, and load it if needed.
2. Add a CHECK constraint that matches the month's bounds, so ATTACH can skip its scan. The docs recommend this.
3. `ATTACH PARTITION`, which takes only SHARE UPDATE EXCLUSIVE on the parent. Then drop the CHECK, which the docs call redundant once the attach is complete.
4. For the oldest month, `DETACH PARTITION ... CONCURRENTLY`, then `DROP TABLE`.

**The failure: a partition key that queries do not use.** A team gives each customer its own partition, because the largest customers are slow. Most queries filter by order id, so most plans touch every partition. Years later the customers number in the thousands, and planning time grows with them. The docs, section 5.11.6, warn about this case. They suggest a fixed number of HASH partitions instead of one LIST partition per customer. Choose the key from the WHERE clauses of the hot queries. Measure planning time with the partition count you expect in three years.

`partitions.py` checks each claim above on your server, and `--planning-sweep` measures the planning time at 12, 120 and 1,200 partitions. The next section asks what DDL like these changes does to a busy table.

**The sentence to remember:** pruning works only from conditions on the partition key. Partitioning pays when queries name the key and old data leaves by whole partitions. When they do not, it costs planning time and lookups.

**The trap:** removing an old month with `DROP TABLE` while it is still attached. The docs, section 5.11.2.2, say this takes an ACCESS EXCLUSIVE lock on the parent. Every query on `order_events` then waits for it. Detach the month `CONCURRENTLY` first, then drop it.

**Try this now:** run `uv run python phase04_planning/partitions.py`. Check the `partitions scanned` line of `prune` and of `no-key`, and the `Subplans Removed` count of `generic`.

---

## 4.7 — Migrations under load (which DDL takes which lock, expand/contract, backfilling in batches, and the compatibility window)

Why this matters: the opening case's index build stopped every write for 11 minutes. The task queue now needs a new column, `queue text NOT NULL`, on a table that workers write all day. This section names the lock that each statement of such a migration takes. It also shows how to bound the time each statement waits for its lock.

**Answer this first.** Three questions about `p4_tasks`, the task-queue table, with 200,000 rows and steady traffic:

1. Which lock does `CREATE INDEX` without `CONCURRENTLY` take, and which statements does it block?
2. Session A opened a transaction, read `p4_tasks`, and is still open. You run `ALTER TABLE p4_tasks ADD COLUMN queue text`, a change to the catalog only. One second later, a plain `SELECT` on `p4_tasks` arrives. What happens to it?
3. On PostgreSQL 14, does `ADD COLUMN queue text NOT NULL DEFAULT 'default'` rewrite the 200,000 rows?

**The mental model.** Every statement takes one of eight table-level lock modes, and two modes either conflict or do not. The PostgreSQL 14 docs, section 13.3.1, give each mode's list of conflicts. Here is the table rebuilt from those lists, with X for a conflict:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Table lock conflicts, PostgreSQL 14 docs 13.3.1. X = the two conflict    │
├──────────────────────────────────────────────────────────────────────────┤
│ requested \ held          AS   RS   RX  SUX    S  SRX    X   AX          │
│ ACCESS SHARE  SELECT       .    .    .    .    .    .    .    X          │
│ ROW SHARE  SELECT FOR UPD  .    .    .    .    .    .    X    X          │
│ ROW EXCLUSIVE  writes      .    .    .    .    X    X    X    X          │
│ SHARE UPDATE EXCL  VACUUM  .    .    .    X    X    X    X    X          │
│ SHARE  CREATE INDEX        .    .    X    X    .    X    X    X          │
│ SHARE ROW EXCL  ADD FK     .    .    X    X    X    X    X    X          │
│ EXCLUSIVE                  .    X    X    X    X    X    X    X          │
│ ACCESS EXCL  most ALTER    X    X    X    X    X    X    X    X          │
└──────────────────────────────────────────────────────────────────────────┘
```

A schema change costs the table two things. The first is the time it holds the lock. That is its work: a catalog change, a scan or a rewrite. The second is the time it waits for the lock, because a waiting request also blocks later ones. That is the soft block of the Phase 3 recap above.

**Which DDL takes which lock.** The ALTER TABLE page of the PostgreSQL 14 docs sets the default. "An ACCESS EXCLUSIVE lock is acquired unless explicitly noted". The rows below are verified from that page, from section 13.3.1, from CREATE INDEX and from REINDEX. `locks.py --predict` prints the same facts for any statement:

| Statement | Lock | What it blocks | Its work while it holds the lock |
|---|---|---|---|
| `CREATE INDEX` | SHARE | writes | a full scan to build the index |
| `CREATE INDEX CONCURRENTLY` | SHARE UPDATE EXCLUSIVE | other DDL and VACUUM, no traffic | two scans, and waits for older transactions |
| `ANALYZE`, `VACUUM`, `CREATE STATISTICS` | SHARE UPDATE EXCLUSIVE | other DDL and VACUUM | a sample, or one pass |
| `ADD COLUMN`, constant or no default | ACCESS EXCLUSIVE | everything | the catalog only. For a constant default, since PostgreSQL 11 |
| `ADD COLUMN ... DEFAULT random()` | ACCESS EXCLUSIVE | everything | a rewrite of the table and its indexes |
| `ADD CONSTRAINT ... CHECK ... NOT VALID` | ACCESS EXCLUSIVE | everything | the catalog only. New rows are checked from now on |
| `VALIDATE CONSTRAINT` | SHARE UPDATE EXCLUSIVE | other DDL and VACUUM | one scan of the existing rows |
| `ALTER COLUMN ... SET NOT NULL` | ACCESS EXCLUSIVE | everything | a full scan, skipped if a valid CHECK proves no NULL, since 12 |
| `ADD FOREIGN KEY` | SHARE ROW EXCLUSIVE, on both tables | writes on both tables | a scan to check rows, unless NOT VALID |
| `ALTER COLUMN ... TYPE` | ACCESS EXCLUSIVE | everything | a rewrite, unless the old type is binary coercible |
| `VACUUM FULL`, `CLUSTER` | ACCESS EXCLUSIVE | everything | a rewrite |
| `REINDEX` | SHARE on the table, ACCESS EXCLUSIVE on the index | writes, and reads that would use the index | a rebuild of the index |

The REINDEX row needs a note. Section 13.3.1 lists REINDEX under ACCESS EXCLUSIVE. The REINDEX page says instead that it "locks out writes but not reads of the index's parent table". `index.c` at REL_14_24 opens the table in SHARE mode, at line 3602. It opens the index in ACCESS EXCLUSIVE mode, at line 3641. Both were fetched on 2026-10-18.

So the first answer is: SHARE, which conflicts with ROW EXCLUSIVE. Every INSERT, UPDATE and DELETE waits for the whole build, and SELECTs go on. That is the opening case's 11 minutes, and why reads still worked. The course outline tells this story as a migration that "took an exclusive lock". That is not the mode it took, because SHARE blocks writes only. An ACCESS EXCLUSIVE lock would also have stopped the reads.

**The lock queue.** The lock manager grants a request only if it conflicts with nothing granted and nothing already waiting. The lmgr README at REL_14_0, line 364, states it. "A lock request is granted immediately if it does not conflict with any existing or waiting lock request". Line 386 adds that conflicting requests "are granted in order of arrival". So a waiting ACCESS EXCLUSIVE request blocks even a plain SELECT.

The course research ran this with three sessions on PostgreSQL 14.24 on 2026-10-17. These times were measured:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The lock queue, measured by the course research, PostgreSQL 14.24        │
├──────────────────────────────────────────────────────────────────────────┤
│ t = 0 s  A: BEGIN, SELECT from t, then waits 6 s     ACCESS SHARE held   │
│ t = 1 s  B: ALTER TABLE t ADD COLUMN ...             ACCESS EXCL waiting │
│ t = 2 s  C: SELECT count(*) FROM t WHERE id = 2      ACCESS SHARE waiting│
│                                                      blocked by B, not A │
│ t = 6 s  A commits. B gets the lock, adds the column in milliseconds,    │
│          commits. C runs                                                 │
├──────────────────────────────────────────────────────────────────────────┤
│ C took 4.04 s for a one-row SELECT. B took 5.03 s                        │
│ with SET lock_timeout = '100ms' on B: B failed after 0.18 s with         │
│ "canceling statement due to lock timeout", and C took 0.07 s             │
│ C started at t = 2 s, after B had already left the queue                 │
└──────────────────────────────────────────────────────────────────────────┘
```

That is the second answer. The SELECT waits behind the ALTER for as long as A stays open, although the ALTER itself needs milliseconds. Every request on the table queues the same way. So the table is down for as long as the longest open transaction lasts. Session A does not have to be a transaction of yours. Section 4.5 put an autovacuum "to prevent wraparound" in A's place. It never gives way, and section 4.5 shows the Joyent outage it caused.

**One real outage, and one claim corrected.** GoCardless reported about 15 seconds of unexpected API downtime during a planned migration. A long `SELECT` ran on a busy parent table. Meanwhile, a migration added a foreign key `NOT VALID` from an empty child table. On a restored backup, with no traffic, the same migrations finished in a few hundred milliseconds. The post says that adding the foreign key takes ACCESS EXCLUSIVE on both tables. That was true up to PostgreSQL 9.4, the version the post discusses. The 9.5 release notes reduced the lock levels of foreign-key commands. The PostgreSQL 14 docs say `ADD FOREIGN KEY` "requires only a SHARE ROW EXCLUSIVE lock", on both tables. The course research measured the difference on 14.24 on 2026-10-17. A transaction held a write lock on the parent for 5 s, and the foreign-key addition queued behind it. A SELECT on the parent then finished in 0.18 s, and an INSERT waited 2.98 s.

**lock_timeout and retries.** The PostgreSQL 14 docs, section 20.11.1, define `lock_timeout`. "Abort any statement that waits longer than the specified amount of time while attempting to acquire a lock". It "applies separately to each lock acquisition attempt". The error is SQLSTATE 55P03, `lock_not_available`, from `postgres.c` at REL_14_24, line 3299. A statement that gives up leaves the queue, so the requests behind it run. Then the migration waits and tries again. The lab's runner does this for every DDL statement. From `phase04_planning/migrate_lab.py:376`:

```python
# from phase04_planning/migrate_lab.py:376, run_statement(). Copied
def run_statement(conn, sql: str, retry: bool, args, rng: random.Random, res: StepResult) -> None:
    for attempt in range(args.max_attempts):
        res.attempts += 1
        try:
            conn.execute(sql)
            return
        except Exception as exc:
            if retry and sqlstate_of(exc) == LOCK_NOT_AVAILABLE and attempt + 1 < args.max_attempts:
                res.lock_timeouts += 1
                time.sleep(backoff(attempt, args.backoff_base_ms / 1000, args.backoff_cap_ms / 1000, rng))
                continue
            raise
    raise LabError(f"gave up after {args.max_attempts} attempts: {sql[:60]}")
```

`backoff` waits a random time up to `min(cap, base × 2^attempt)`. That is capped exponential backoff with jitter. The random part spreads retries that failed together.

**How long to wait for a lock.** Teams choose very different values, verified from each source:

| Source | `lock_timeout` | Retries |
|---|---|---|
| postgres.ai, Nikolay Samokhvalov, 2021 | 50 ms | exponential backoff with jitter, 30 attempts in its example |
| GitLab, `with_lock_retries.rb` at master | 0.1 s, rising to 2 s | 615 attempts, about 44.6 minutes in the worst case |
| GoCardless, `ActiveRecord::SaferMigrations` | 750 ms | none by default, plus a 1,500 ms statement limit |
| Braintree, 2019 draft by James Coleman | locks held at most about 2 seconds | not stated |
| strong_migrations, Andrew Kane | 10 s | 3, 10 s apart, marked experimental |

The trade-off is plain. Each attempt can block the table's traffic for up to `lock_timeout`, so a short value keeps each pause short. A short value also fails more often on a busy table, so it needs more retries. The postgres.ai post works through one thought experiment. Its SELECTs take 0.1 ms, and its migration retries 50 ms waits with no pause between them. The average SELECT then approaches 50 ms. That is why the pause between attempts matters as much as the timeout.

GitLab's documentation and its code disagree. The style guide says the helper tries 50 times, then runs once more without `lock_timeout`. The code at master, fetched on 2026-10-18, retries 615 times over about 44.6 minutes. Its timeouts run from 0.1 s to 2 s. In migrations, `lock_retries_helpers.rb` line 43 sets `raise_on_exhaustion` to true, so the migration fails when the retries run out. This course teaches the code. It did not search for places where GitLab overrides the schedule.

**A timeout policy, beyond `lock_timeout`.** Phase 3, section 3.4, gave the timeout settings, their defaults and the `log_lock_waits` line formats. All are off by default. Here is the role of each in a migration:

| Setting | Its role in a migration | Where to set it |
|---|---|---|
| `lock_timeout` | bounds each wait for one lock, so the queue behind it moves | every DDL statement, `SET lock_timeout = '100ms'`, with retries |
| `statement_timeout` | stops a scan or a rewrite that runs longer than planned | per migration with `SET LOCAL`, and per role. Not in `postgresql.conf`, which the docs advise against |
| `idle_in_transaction_session_timeout`, and `transaction_timeout` from 17 | ends the session whose open transaction a migration would wait behind | per role, for application sessions |
| `log_lock_waits` | logs every lock wait longer than `deadlock_timeout`, 1 s | on, in `postgresql.conf` |

With `log_lock_waits` on, a migration that waits writes `process %d still waiting for %s on %s after %ld.%03d ms`, from `proc.c` at REL_14_24, line 1624. Its detail line lists the holders and the wait queue. That pair of lines shows the lock queue of this section in a production log.

**What each statement's work costs.** The course research measured these on PostgreSQL 14.24 on 2026-10-17, on a table of 1,000,000 rows:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Time holding ACCESS EXCLUSIVE, 1,000,000 rows. Measured by the research  │
├──────────────────────────────────────────────────────────────────────────┤
│ ADD COLUMN d1 int DEFAULT 42                      2.5 ms   no rewrite    │
│     the file number stayed 16401                                         │
│ ADD COLUMN d2 float8 DEFAULT random()           996.7 ms   rewrite       │
│     the file number changed 16401 ─► 16434                               │
│ SET NOT NULL, after a valid CHECK (n IS NOT NULL) 0.68 ms  scan skipped  │
│ SET NOT NULL, no CHECK                           48.2 ms   full scan     │
└──────────────────────────────────────────────────────────────────────────┘
```

With `client_min_messages = debug1`, the skipped scan printed `existing constraints on column "t.n" are sufficient to prove that it does not contain nulls`. The 48 ms is for 1 million narrow rows in memory. It grows with the table, and all of it is spent under ACCESS EXCLUSIVE. So the third answer is no. A constant default is stored in the catalog, from the PostgreSQL 11 release notes and the 14 ALTER TABLE page.

**CREATE INDEX CONCURRENTLY.** It is the answer to the opening case. The PostgreSQL 14 docs for CREATE INDEX give four conditions:

1. It scans the table twice. It also "must wait for all existing transactions that could potentially modify or use the index to terminate".
2. If it fails, it leaves an index marked invalid. That index is "ignored for querying purposes" but "will still consume update overhead". Drop it and build again, or use `REINDEX INDEX CONCURRENTLY`.
3. It cannot run inside a transaction block, and only one concurrent build can run on a table at a time.
4. While it runs, it holds a snapshot. James Coleman's Braintree draft notes the result. Vacuum cannot remove dead rows in any table, by the horizon of section 4.5.

Three checks belong before and during such a build:

1. **Before:** `SELECT pid, now() - xact_start, query FROM pg_stat_activity WHERE xact_start < now() - interval '1 minute' ORDER BY xact_start`. A concurrent build waits for such transactions, by condition 1 above. Other DDL waits for the ones that hold a lock on its table. A query that ends in `(to prevent wraparound)` is the case of section 4.5.
2. **During:** `pg_stat_progress_create_index` shows the build's `phase`, verified from the PostgreSQL 14 docs, section 28.4.
3. **After a failure:** `SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid` lists invalid indexes. The REINDEX page names `pg_index.indisvalid` as the flag a concurrent build switches.

A unique constraint can be added the same way. The ALTER TABLE page's own example builds `CREATE UNIQUE INDEX CONCURRENTLY` first. Then `ADD CONSTRAINT ... USING INDEX` turns the index into the constraint, which the page calls "a fast operation" for a UNIQUE constraint. Its lock is not stated there, so assume ACCESS EXCLUSIVE, the page's default, held briefly. That lock level is inferred.

**Expand and contract.** The expand/contract pattern changes a schema in steps. Each step keeps the old code and the new code working. Expand adds what the new code needs without removing anything. The code then moves to the new shape. Contract removes the old shape once nothing uses it. Here is the NOT NULL column as the lab runs it, with the lock of each step:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ queue text NOT NULL on p4_tasks: migrate_lab.py, expand-contract         │
├──────────────────────────────────────────────────────────────────────────┤
│ 1 expand    ADD COLUMN queue text            ACCESS EXCL, catalog only   │
│ 2 switch    deploy: new code writes queue    no lock. Old code drains    │
│ 3 backfill  UPDATE ... WHERE id in a batch   row locks on 1,000 rows     │
│             AND queue IS NULL, then pause    per transaction             │
│ 4 check     ADD CHECK (queue IS NOT NULL)    ACCESS EXCL, catalog only   │
│             NOT VALID                                                    │
│ 5 validate  VALIDATE CONSTRAINT              SHARE UPDATE EXCL, one scan │
│ 6 not null  SET NOT NULL                     ACCESS EXCL, scan skipped   │
│ 7 contract  DROP CONSTRAINT the CHECK        ACCESS EXCL, catalog only   │
├──────────────────────────────────────────────────────────────────────────┤
│ every ACCESS EXCLUSIVE step: lock_timeout 100 ms and retries with backoff│
└──────────────────────────────────────────────────────────────────────────┘
```

The strong_migrations README gives the same order for NOT NULL. First a CHECK `NOT VALID`, then a validation in a separate migration. Then `NOT NULL`, then dropping the CHECK. It names "three keys to backfilling safely: batching, throttling, and running it outside a transaction". Its example updates 10,000 rows per batch with a 0.01 s sleep. GitLab's batched background migrations use batches of 1,000 with sub-batches of 100. Its guide keeps "any single query" under 1 second. Stripe's post "Online migrations at scale", by Jacqueline Xu, 2017, describes the same idea for moving data between models. It has four phases: write to both, move the reads, move the writes, remove the old data. The post does not name its database engine. Moving a very large table to new storage, with dual writes or logical replication, is course 5.

WRONG and RIGHT, as SQL:

```sql
-- WRONG: one transaction. ACCESS EXCLUSIVE is taken at the ALTER and held
-- until COMMIT, so every read and write waits for the whole UPDATE. With no
-- lock_timeout, a long transaction ahead of it queues the table first.
BEGIN;
ALTER TABLE p4_tasks ADD COLUMN queue text;
UPDATE p4_tasks SET queue = CASE WHEN state IN ('awaiting_approval', 'approved',
    'rejected') THEN 'approvals' ELSE 'default' END;
ALTER TABLE p4_tasks ALTER COLUMN queue SET NOT NULL;
COMMIT;

-- RIGHT: short steps, each with a bounded wait for its lock.
SET lock_timeout = '100ms';            -- retry on SQLSTATE 55P03
ALTER TABLE p4_tasks ADD COLUMN queue text;
-- deploy the code that writes queue, then backfill in batches:
UPDATE p4_tasks SET queue = CASE ... END
 WHERE id > 0 AND id <= 1000 AND queue IS NULL;    -- and so on, with a pause
ALTER TABLE p4_tasks ADD CONSTRAINT p4_tasks_queue_not_null
  CHECK (queue IS NOT NULL) NOT VALID;
ALTER TABLE p4_tasks VALIDATE CONSTRAINT p4_tasks_queue_not_null;
ALTER TABLE p4_tasks ALTER COLUMN queue SET NOT NULL;   -- no scan, since 12
ALTER TABLE p4_tasks DROP CONSTRAINT p4_tasks_queue_not_null;
```

`migrate_lab.py --plan` prints the plan of the chosen `--strategy`, with a lint that encodes these rules. It reports three faults for the naive plan. The first is ACCESS EXCLUSIVE with no `lock_timeout`. The second is an UPDATE inside the DDL transaction. The third is SET NOT NULL with no valid CHECK first. The self-test checks that count, and that the expand/contract plan has none.

**The compatibility window.** Between the expand and the contract, two versions of the code run against one schema. Each step must work for both:

- **New code, old schema.** Code that writes `queue` must not deploy before step 1. Otherwise every write fails with an unknown column.
- **Old code, new schema.** Old code never writes `queue`. Its rows stay NULL after the backfill passes them. Once step 4 adds the CHECK, the docs say the constraint is "enforced against subsequent inserts or updates". So the old code's inserts start failing with SQLSTATE 23514, `check_violation`. Step 5 then fails on the NULL rows it left. `--break-compat` shows both. Without the CHECK, step 6 would make the same inserts fail with 23502, `not_null_violation`.

So the switch must finish, with every old instance gone, before the backfill reaches its last batch. In the lab, the switch step waits `--settle-s` seconds to stand for that deploy. A column DEFAULT is the other way to keep old inserts working. `--strategy constant-default` adds the column with `DEFAULT 'default'`. It backfills only the rows that need another value.

**What the lab should show.** Worked out from the flags and the rules above, not measured. The defaults are 4 readers and 4 writers at 50 requests per second each, so 400 per second. Each request's deadline is 1,000 ms:

- `--strategy naive --hold-lock-s 5`: the ALTER waits 5 s with no timeout, and every request queues behind it. About 400 × 5 = 2,000 requests are scheduled in that window. Most of them pass their 1-second deadline and fail with 57014 or `late`. After the commit, the old code's inserts fail with 23502. Inserts are half of the writers' requests, so about 4 × 50 × 0.5 = 100 fail per second.
- `--strategy expand-contract --hold-lock-s 5`: the expand step times out and retries until A's 5 seconds end. The default `--seed 1` fixes the random backoff waits. Python's `random.Random(1)` gives 7, 85, 153, 102, 396, 719, 1,303 and 1,577 ms. With 100 ms per failed attempt, the ninth attempt starts at about 5.14 s, after A has committed. So expect 9 attempts and 8 lock timeouts. That was computed from the generator, not from a run of the lab. No request waits much longer than 100 ms, so none fails.

**The failure: a migration tested on an idle copy.** GoCardless's migrations took a few hundred milliseconds on a restored backup. The outage came from one long transaction in production that the copy did not have. A lock wait depends on the traffic, not on the statement. So test a migration with a run under load, and measure the lock waits, as E10 and E11 do.

A step that went wrong must sometimes be undone. The next section asks which of these steps can be undone, and which cannot.

**The sentence to remember:** a DDL statement costs the time it holds its lock plus the time it waits in the queue. While it waits, it blocks every conflicting request behind it. Set `lock_timeout`, retry with backoff, and split the change so that each step holds ACCESS EXCLUSIVE for milliseconds.

**The trap:** trusting a migration because its statement is instant, and running it with no `lock_timeout`. In the research's run, an ADD COLUMN that needs milliseconds kept a one-row SELECT waiting 4.04 s.

**Try this now:** run `uv run python phase04_planning/locks.py --predict "CREATE INDEX p4_tasks_state ON p4_tasks (state)"`, then the same with `CONCURRENTLY`. Compare the lock modes and the `blocks` lines.

---

## 4.8 — Rollback (the schema change you cannot undo, and how to structure one so you can)

Why this matters: a deploy goes wrong, and the first instinct is to roll back. The code can go back to its previous version in minutes. The schema often cannot, because some changes destroy the data that the old version needs. Whether a rollback is possible is decided when the migration is designed, not when it fails.

**Answer this first.** For each change, say whether it can be undone without losing data:

1. `ADD COLUMN queue text`, before any code writes it.
2. The batched backfill of `queue`.
3. `ALTER COLUMN queue SET NOT NULL`.
4. `DROP COLUMN old_status`, a week after the code stopped reading it.
5. `ALTER COLUMN amount_cents TYPE integer`, from `bigint`.
6. A backfill that rewrites `status` in place, from `paid` to the new value `settled`.

**The mental model.** A change can be undone only while the data the old shape needs still exists. A reverse statement does not bring data back. It only changes the shape. So sort every step into one of two kinds:

- **Additive steps** add a column, a table, an index or a constraint, or copy data into a new place. Their reverse drops what they added, and the old shape still has all of its data.
- **Destructive steps** drop, narrow, overwrite or rename what the old code uses. Their reverse cannot restore the data, or the old code fails at once.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The compatibility window. Each row must work with the schema above it    │
├──────────────────────────────────────────────────────────────────────────┤
│ schema    old      │ + queue nullable │ + backfill, NOT NULL │ old col   │
│                    │ expand           │                      │ dropped   │
├──────────────────────────────────────────────────────────────────────────┤
│ code v1   ok       │ ok: ignores it   │ needs a DEFAULT or   │ fails if  │
│                    │                  │ it fails on insert   │ it reads  │
│ code v2   fails:   │ ok: writes it    │ ok                   │ ok        │
│           no col   │                  │                      │           │
├──────────────────────────────────────────────────────────────────────────┤
│ rolling code back from v2 to v1 is safe in the middle columns only       │
└──────────────────────────────────────────────────────────────────────────┘
```

**Why DROP COLUMN is one way.** The ALTER TABLE docs say DROP COLUMN "does not physically remove the column". It makes the column invisible to SQL. The bytes stay on disk until rows are rewritten. No SQL statement makes them visible again. So the only way back is a restore from a backup, which also loses every write made after it. The same holds for `DROP TABLE` and `TRUNCATE`. A type change that narrows a column fails, or with a `USING` expression it converts and loses the original values. A rewrite in place replaces the old values, and the new values do not say what the old ones were.

So the answers are: 1 yes, drop the column. 2 yes, because the column is still nullable and no old code reads it. 3 yes, with `DROP NOT NULL`. 4 no. 5 no, unless every value fits, and even then the reverse is a rewrite under ACCESS EXCLUSIVE. 6 no: the rows that were `paid` and the rows that were already `settled` cannot be told apart afterwards.

**Structure a change so that it can be undone.** Five rules follow from the two kinds:

1. **Expand only adds.** New columns and tables next to the old ones, never in place of them.
2. **Write new data beside old data.** To change a column's type or meaning, add a new column. Write both, and backfill the new one. That is strong_migrations' six-step recipe for a type change and a rename. Create, write both, backfill, move reads, stop writing the old one, drop it.
3. **Pair every step with its reverse in the plan,** and say what the reverse loses. `migrate_lab.py --plan` prints both for every step.
4. **Undo in reverse order, code before schema.** Move the code back first, then drop what the expand added. Code that still writes `queue` fails with SQLSTATE 42703, `undefined_column`, once the column is gone. `--rollback-after` follows this order.
5. **Contract last, after a waiting period.** Drop the old shape only when no running code uses it. You must also be able to restore it. James Coleman's Braintree draft states the policy in one line. "Rollback strategies do not involve reverting the database schema to its previous version." Before a DROP COLUMN reaches production, the same draft requires proof that no code references the column.

GitLab works the same way. Its migration guide says that on its production environments, "a roll-forward strategy is used instead of rolling back migrations". Roll forward means you fix a bad change with a new change, while the schema keeps the expanded shape.

Here are the expand/contract steps of section 4.7, with their reverses, as `migrate_lab.py --plan` prints them:

| Step | Reverse | What the reverse loses |
|---|---|---|
| expand: ADD COLUMN queue | DROP COLUMN queue | the queue values, which the backfill can compute again |
| switch: new code writes queue | deploy the old code | nothing |
| backfill | none needed | nothing: the column is still nullable |
| check: CHECK NOT VALID | DROP CONSTRAINT | nothing |
| validate | dropping the CHECK undoes it | nothing |
| not null: SET NOT NULL | DROP NOT NULL | nothing |
| contract: DROP the CHECK | ADD the CHECK NOT VALID again | nothing |

Every step of this plan is additive, so the whole plan can be undone. A plan that renames or retypes a column has a destructive last step: dropping the old column. Keep it as a separate migration, released after the waiting period.

**The failure: a down migration that never ran.** Many frameworks generate a "down" step for each migration. Nobody runs it until the day it is needed. By then the table holds data the down step was not written for. An example is rows that only the new code wrote. Test the reverse of each step the way you test the step, under load, as E11 does with `--rollback-after`. Treat a destructive step as having no reverse at all.

**The sentence to remember:** a reverse statement changes the shape and never brings data back. Keep every step additive until the contract. Release the contract on its own, after the code that needs the old shape is gone.

**The trap:** dropping or overwriting a column in the same release that stops using it. If that release must roll back, the old code needs data that no longer exists. Only a backup restore brings it back.

**Try this now:** run `uv run python phase04_planning/migrate_lab.py --plan --strategy naive`, then the same with `--strategy expand-contract`. For each step of the naive plan, say what its reverse would lose.

---

## 🧪 Hands-on lab

The labs below are written and reviewed, but were not run by the author. Each script was checked with `python3 -m py_compile` only. Every "Expected" line says "Not run by the author yet." and then gives the expected shape. Each number in it has one of three sources. It is a cited source, or arithmetic in this phase. Or it is a measurement by the course research on PostgreSQL 14.24, with its conditions. Plan choices and counts should match closely. Times depend on your machine, and none of them is claimed.

**What you build.** Ten files in `phase04_planning/`. They reuse `shared/pglab.py` from Phase 3 and change no earlier file:

| File | What it holds | Self-test checks |
|---|---|---|
| `explain_tools.py` | EXPLAIN JSON as nodes: est, actual × loops, q-error, buffers, before and after. Parallel nodes, the JIT block, spill lines. `--server-defaults` and `--set` | the docs' nested-loop plan, Leis's q-error example, a bad plan's worst node, BUG #19076's parallel plan, the divisor 2.4 |
| `find_slow.py` | `pg_stat_statements` rankings, a setup check, and an `auto_explain` demo | the missing setup steps, the plan-changer ranking, the auto_explain settings |
| `plan_cache.py` | a prepared statement's custom plans, then its generic plan, on skewed tenants | the five-execution rule, the planning charge, the generic estimate, the data's skew |
| `cost_model.py` | the row-estimate and scan-cost formulas of `selfuncs.c` and `costsize.c` | every worked number of docs 72.1, the 458 and 483 of 14.1, the research's 21846.00 and switch points |
| `access_paths.py` | the selectivity sweep of section 4.3 on your server | the bound k, the build SQL |
| `plan_lab.py` | stale statistics, the diagnosis, the fix, extended statistics, join methods | the 400,000 pending rows, the 1-row estimate, the analyze threshold |
| `bloat.py` | dead versions, a held snapshot, VACUUM FULL's lock, transaction ID and multixact ages, the autovacuum budget and signals | the PostgreSQL 14 limits from `varsup.c`, the vacuum threshold and its 18 cap, the shared budget, nine pages per nap |
| `partitions.py` | pruning at plan time and executor start, parent statistics, DROP against DELETE | month bounds, which partitions a range keeps |
| `locks.py` | the conflict table, `--predict`, the lock queue offline and live, Joyent's wraparound queue | the docs' conflict lists, 14 statements, the queue scenarios, a normal against a wraparound autovacuum |
| `migrate_lab.py` | three NOT NULL plans under an open-loop load, with lock_timeout and retries | the lint finds the naive plan's 3 faults, each rule removed fails a check |

Every PostgreSQL lab refuses a database whose name does not start with `storage_lab`, through `shared/pglab.py`. It creates and drops only tables that start with `p4_`. The demonstration of this phase has two parts. E4 diagnoses and fixes a plan, with buffers and time before and after. E10 and E11 run the migration under load, with the lock waits measured.

- [ ] **E1 (offline).** Run every self-test of this phase, then those of the earlier phases.
  - Run: `for f in phase04_planning/*.py; do echo "$f"; uv run python "$f" --self-test; done`
  - Then run: `for f in shared/*.py phase01_durability/*.py phase02_structures/*.py phase03_transactions/*.py; do echo "$f"; uv run python "$f" --self-test; done`
  - Expected: Not run by the author yet. `self-test passed` after each of the 10 Phase 4 files, and after each of the 20 earlier scripts. The loop also runs `shared/__init__.py`, which is empty and prints nothing.
  - If it fails: the assertion message names the formula or the rule. Compare it with the section it comes from before you change any code.
  - Teaches: each rule that the text calls important has a check that fails without it.

- [ ] **E2 (offline).** The planner's arithmetic, by the model.
  - First write your prediction for the research table at 1 row, 1%, 40% and 45%, from section 4.3.
  - Run: `uv run python phase04_planning/cost_model.py --sweep`, then add `--random-page-cost 1.1`, then run it with `--correlation 1.0`.
  - Expected: Not run by the author yet. The default sweep picks Index Scan at 0.0001%, Bitmap Heap Scan from 0.001% to 40%, and Seq Scan from 45%. The Seq Scan cost is 21846.00. At 40% the bitmap row shows about 21,338, and at 45% about 22,839. With 1.1, the Index Scan wins at 50%. With correlation 1.0, the Index Scan wins at 10%, about 3,664 against 12,347.
  - Teaches: the switch points come from pages, rows and correlation, and the model shows which term decides.

- [ ] **E3 (local).** The same sweep on your PostgreSQL 14.
  - Run: `uv run python phase04_planning/access_paths.py`, then `--skip-build --random-page-cost 1.1`, then `--correlated`, then `--covering --analyze`, then `--pad-bytes 400`.
  - Expected: Not run by the author yet. The header shows your page count. With the default 40-byte pad, the arithmetic below gives about 10,300 pages, close to the research's 9,346. Expect the same order of plans: Index Scan, Bitmap Heap Scan, Seq Scan. The `model` column agrees, except where two costs are within a few percent. `--correlated` shows Index Scan over a wide range. `--covering` shows Index Only Scan, and its `read` column stays low after VACUUM. With 400-byte pads, a row takes about 444 bytes of its page instead of about 84. So the table has about five times the pages, and the switch should move. These sizes are inferred from the PostgreSQL 14 docs, section 70.6. A row header is 23 bytes, padded to 24, and each row adds a 4-byte line pointer. They were not measured.
  - If the switch differs from the research's: compare your rows per page and correlation with section 4.3 first.
  - Teaches: the research's switch points belong to its table, not to PostgreSQL.

- [ ] **E4 (break-it, local).** Part of the demonstration: break the statistics, diagnose, fix.
  - First predict the estimate for `pending` after the incident, from section 4.2.
  - Run: `uv run python phase04_planning/plan_lab.py`.
  - Expected: Not run by the author yet. `400,000 orders are now pending (expected 400,000)`. `pg_stats` shows three values whose frequencies add up to 1, and the formula line gives a selectivity of 0. The plan's scan of `p4_orders` shows est 1 and actual 400,000. The plan is expected to be a Nested Loop whose inner Index Scan on `p4_order_events` shows 400,000 loops. `team-fix` still shows est 1. After `fix`, the estimate is near 400,000 and the join is expected to be a Hash Join. The before-and-after table shows the plan shapes, the worst q-error, the buffers and the execution time. The last line is `RESULT: worst q-error 400,000 before`, then a value under 10 after, and `Fixed`. The plan choices are expected from the cost model, not run.
  - If the first plan is already a Hash Join: your cost settings differ from the defaults. Check `show random_page_cost` and `show work_mem`, and note it. The estimate of 1 row is still the lesson.
  - Teaches: one stale MCV list turns 400,000 rows into 1, and ANALYZE, not an index, fixes it.

- [ ] **E5 (local).** Correlated columns and the three join methods.
  - Run: `uv run python phase04_planning/plan_lab.py --case correlated`, then `uv run python phase04_planning/plan_lab.py --case join-methods --skip-build --analyze`.
  - Expected: Not run by the author yet. Correlated: est 1 and actual 100 before, est 100 after, and the GROUP BY estimate 1000 before and 100 after. The course research saw exactly these on 14.24. Join methods: three outer sizes, each with four rows. The `planner` row's cost equals the lowest of the three forced rows. At 10 outer rows, expect a nested loop to be cheapest. At the full table, expect a hash join.
  - Teaches: the independence assumption and its fix. The planner's join is the cheapest by its own estimates.

- [ ] **E6 (break-it, local).** Bloat behind one open transaction.
  - Run: `uv run python phase04_planning/bloat.py --held-rounds 3 --pgstattuple`.
  - Expected: Not run by the author yet. The page counts follow the bar chart of section 4.5. They are about 1x at the load, and 2x after the first UPDATE, the VACUUM and the second UPDATE. The first held round grows the file to about 3x. Its VACUUM still frees the versions that died before H's snapshot, so the second held round reuses that space. The third held round grows the file to about 4x. After H commits, VACUUM frees space, and the next UPDATE does not grow the file. VACUUM FULL brings it back to about 1x. The SELECT during VACUUM FULL takes about as long as VACUUM FULL itself, because ACCESS EXCLUSIVE blocks it.
  - If `pgstattuple` is missing: the script says so and uses `pg_stat_user_tables` only.
  - Teaches: VACUUM removes only what died before the oldest snapshot, and it never shrinks the file.

- [ ] **E7 (local).** Transaction ID ages and the limits.
  - Run: `uv run python phase04_planning/bloat.py --xid`.
  - Expected: Not run by the author yet. The settings line shows `autovacuum_freeze_max_age 200000000` and `vacuum_failsafe_age 1600000000`, the PostgreSQL 14 defaults. A laptop cluster shows small ages, so each distance is close to its limit. For an age near 0, the stop is about 2,144 million away. The lists of old sessions, slots and prepared transactions are short or empty.
  - Teaches: what to alert on, long before the WARNING.

- [ ] **E8 (local).** Pruning, and what partitioning costs the planner.
  - Run: `uv run python phase04_planning/partitions.py --planning-sweep 12,120,1200`.
  - Expected: Not run by the author yet. `prune`: 1 partition scanned, expected 1. `no-key`: 12 of 12. `generic`: `Subplans Removed: 11`. `parent-stats`: 0 rows before ANALYZE and some after. `unique`: an ERROR line from the server. `drop`: the DELETE leaves about 100,000 dead rows, one twelfth of 1,200,000, and the DROP none. The planning sweep is expected to grow with the partition count. No time is claimed.
  - Teaches: pruning comes from the partition key only, and unpruned partitions cost planning time.

- [ ] **E9 (break-it, offline, then local).** The lock queue, predicted and then reproduced.
  - First run: `uv run python phase04_planning/locks.py --table`, then `--scenario queue`, then `--scenario queue-timeout`, then `--scenario fk`.
  - Then run: `uv run python phase04_planning/locks.py --live queue --lock-timeout 0`, then `--live queue --lock-timeout 100ms`, then `--live fk --hold-s 5`.
  - Expected: Not run by the author yet. The offline queue shows C `granted=False` behind B, and A's commit waking B first. With the timeout, B's exit wakes C. The fk scenario grants the SELECT and queues the INSERT. Live, with a timeout of 0, the later SELECT takes about 4 s, close to the research's 4.04 s. The `obs` lines show B `granted=false` with ACCESS EXCLUSIVE, and C blocked by B. With 100ms: B fails with 55P03 after about 0.1 to 0.2 s, and C takes well under a second. The research measured 0.18 s and 0.07 s. The fk run: the SELECT is fast, and the INSERT takes about 3 s.
  - Teaches: a queued request blocks every later conflicting request, and lock_timeout bounds that block.

- [ ] **E10 (break-it, local).** Part of the demonstration: the naive migration under load.
  - First predict the failed requests, with the arithmetic of section 4.7.
  - Run: `uv run python phase04_planning/migrate_lab.py --plan --strategy naive`, then `uv run python phase04_planning/migrate_lab.py --strategy naive --hold-lock-s 5; echo "exit $?"`.
  - Expected: Not run by the author yet. The plan's lint lists 3 problems. The run's `all-in-one` row shows failures with 57014 and `late`. They are most of the about 2,000 requests scheduled during the hold. The lock wait max is near 1,000 ms, because each request gives up at its 1-second deadline. The `after` row shows 23502 failures, about 100 per second, because the old code inserts no `queue`. The RESULT line counts the failures, and the exit code is 1.
  - Teaches: one instant ALTER behind one open transaction stops the table. A NOT NULL column breaks the code that does not write it.

- [ ] **E11 (local).** Part of the demonstration: expand/contract with no failed request. Then two ways to break it, and a rollback.
  - Run: `uv run python phase04_planning/migrate_lab.py --strategy expand-contract --hold-lock-s 5; echo "exit $?"`.
  - Expected: Not run by the author yet. The `expand` step shows about 9 attempts and 8 lock timeouts, from the backoff arithmetic of section 4.7. Every phase row shows 0 failed. The max latency stays near 100 ms plus the request's own time, and the lock wait max near 100 ms. The backfill shows 201 or 202 batches. 200 cover the loaded rows. The rest cover about 1,000 rows that the writers inserted first, at about 100 per second for about 10 s. `RESULT: ... 0 failed. queue NOT NULL: True. Rows without a queue: 0. Rows with the wrong queue: 0`, and the exit code is 0.
  - Then run: `uv run python phase04_planning/migrate_lab.py --strategy expand-contract --old-writers 2 --break-compat; echo "exit $?"`. Expected: 23514 failures from the `check` phase on, the old code's inserts. Then `step validate failed` with 23514, and exit 1.
  - Then run: `uv run python phase04_planning/migrate_lab.py --strategy expand-contract --rollback-after check`. Expected: three reverse lines, the CHECK dropped, the writers switched back and the column dropped, then `Column present: False`, with 0 failed.
  - Teaches: bounded lock waits and a compatibility window add a NOT NULL column with no failed request. Undo runs code first, schema second.

- [ ] **E12 (written).** Write the course's storage note.
  - Do: fill in the template of the next section for a system you own. Or check the filled note against your own lab results.
  - Expected: one page. Every "how you know" cell names a test and says whether you ran it.
  - Teaches: a guarantee is a sentence plus the test that would show it false.

The four exercises below cover the production signals of sections 4.1, 4.2, 4.4 and 4.5. They come after the storage note because none of them is part of the demonstration.

- [ ] **E13 (break-it, local).** A prepared statement switches to a generic plan.
  - First predict, from section 4.2, at which execution the plan changes. Also predict the generic plan's estimate for the largest tenant.
  - Run: `uv run python phase04_planning/plan_cache.py`, then `uv run python phase04_planning/plan_cache.py --skip-build --mode force_custom_plan`.
  - Expected: Not run by the author yet. The header prints the generic estimate, about 1,000 orders, which is 1,000,000 / 1,000 tenants. It also prints tenant 1's real count, about 100,300. Executions 1 to 5 show `custom`, with est close to actual, about 1,600 to 2,900 orders. Executions 6 and 7 show `generic`, with est about 1,000 and actual about 100,300 for tenant 1. The counters end at 2 generic and 5 custom. The generic plan is expected to be a Nested Loop, and `force_custom_plan` a Hash Join. Those plan shapes are inferred from the join arithmetic of section 4.4. With `--mode force_custom_plan`, every row shows `custom`.
  - If no generic plan appears: the script prints that the generic cost was not below the custom average. Compare the printed estimates, and note it. The estimate of the generic plan is still the lesson.
  - Teaches: a generic plan uses the average over all values, and `plan_cache_mode` controls it.

- [ ] **E14 (local).** Find the slow query, then its plan, the way you would at work.
  - Run: `uv run python phase04_planning/find_slow.py --check`. Add the line it prints to `postgresql.conf`, the file that `psql -h /tmp -d storage_lab -c "show config_file"` names. Restart the server the way you started it, then run `psql -h /tmp -d storage_lab -c "create extension pg_stat_statements"`. To undo the setup later, remove the line and restart again.
  - Then run: `uv run python phase04_planning/plan_lab.py`, then `uv run python phase04_planning/find_slow.py --top 5`, then `uv run python phase04_planning/find_slow.py --auto-explain-demo`.
  - Expected: Not run by the author yet. `--check` lists `shared_preload_libraries` as missing on a default install. After the restart and the CREATE EXTENSION, it prints `pg_stat_statements is ready`. The first ranking shows the lab's build statements and its report near the top by `total_exec_time`. The demo prints a line that starts with `duration:`, then the plan of the report. It has buffers and no per-node times, because `log_timing` is off.
  - If LOAD fails: your role is not a superuser. The demo needs one, and the rankings do not.
  - Teaches: find the query by its server time, then take the plan it really ran.

- [ ] **E15 (local).** The plan your server makes, with parallel workers, JIT and a spill.
  - Run, after E4: `uv run python phase04_planning/explain_tools.py --server-defaults --sql "select tenant_id, count(*) from p4_orders group by tenant_id"`. Then run the same without `--server-defaults`. Then run `uv run python phase04_planning/explain_tools.py --set work_mem=64kB --sql "select * from p4_orders order by amount_cents"`.
  - Expected: Not run by the author yet. With `--server-defaults`, expect a Gather with `Workers Planned: 2`. Below it, expect a partial aggregate and a Seq Scan marked `per process, divisor 2.4`, with 3 loops. Without the flag, the same query has no Gather. A `JIT:` line appears only if the plan's cost passes 100,000 and the server has LLVM. `p4_orders` at 1,000,000 rows is about a tenth of the opening case, so its cost may stay below that. With `work_mem=64kB`, the Sort's line shows `Sort Method: external merge` and `Sort Space Type: Disk`. These shapes are inferred from sections 4.1 and 4.4.
  - Teaches: the lab's serial plans are a choice, and your server's plans read differently.

- [ ] **E16 (break-it, offline, then local).** The autovacuum budget, and the forced vacuum that does not give way.
  - Run: `uv run python phase04_planning/locks.py --scenario autovacuum`, then `--scenario wraparound`. Then run `uv run python phase04_planning/bloat.py --vacuum-signals`.
  - Expected: Not run by the author yet. `autovacuum`: D and S queue, then the deadlock check cancels the autovacuum, D runs, then S. `wraparound`: the autovacuum is not cancelled, and S runs only after it finishes. `--vacuum-signals` prints the settings of section 4.5 and a budget of about 66 per worker when 3 run. It prints the ceilings of 781.3 and 35.5 MB/s. It notes that `log_autovacuum_min_duration` is −1 on 14. The p4_ tables appear with their dead-row counts, and no vacuum is running on a quiet laptop.
  - Teaches: more workers share one budget. A wraparound vacuum turns any DDL without a `lock_timeout` into an outage.

---

## 🗒 The course's storage note (the integrated lab)

The course spec closes with one page: what this system guarantees, what it does not, and how you know. "This system" is the course's own. It is the order store of Phases 1 and 2. It is also the order data and the task queue in PostgreSQL 14, from Phases 3 and 4. A guarantee belongs in the note only with the test that would show it false. Every test below was written for this course and was not run by the author. So every "how you know" cell gives the result to expect, not a result that was seen.

**The template.** Use it for any storage system you own:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ STORAGE NOTE: <system>, <version>, <date>                                │
├──────────────────────────────────────────────────────────────────────────┤
│ 1 Durability   when OK is sent, the crashes it survives, what recovery   │
│                returns, what is not covered                              │
│ 2 Structure    the layout, its read, write and space amplification on    │
│                our workload, and the number that would make us move      │
│ 3 Isolation    the level, each invariant, the anomaly it allows, and     │
│                the fix in code                                           │
│ 4 Plans        what keeps the statistics current, and the alert          │
│ 5 Change       the lock rules every migration follows, and its reverse   │
│ 6 Not covered  the failures this note does not protect against           │
│ each line: the claim, the test that would show it false, and its status  │
└──────────────────────────────────────────────────────────────────────────┘
```

**The note for the course's system.**

| Area | What it guarantees | What it does not | How you know, and status |
|---|---|---|---|
| Durability, Phase 1 | A put that returned OK with `--sync full` survives a process crash, an OS crash and a power loss. Recovery returns a prefix of the puts in log order, and never an entry that fails its CRC | Damage to data already synced, a drive that ignores flush commands, loss of the device. With plain `os.fsync` on macOS, a power loss, from Apple's `fsync(2)` | `crash_matrix.py`: 0 violations in 231 recoveries, and 42 power violations for the false claim of `--sync fsync --claim-power-safe`. Worked out from the code, not run |
| Structure, Phase 2 | The log layout writes 1.18 bytes per byte. With filters, both layouts read about one block per present key | The log's space grows with every overwrite: 11.77 times the live data on the write-heavy mix. The LSM writes about 14.7 bytes per byte | `amplification.py`, E6 of Phase 2. Worked out from the code and its seed, not run. Move to the LSM when disk, not write volume, is the limit |
| Isolation, Phase 3 | The task claim, the approval and the outbox write keep their invariants at READ COMMITTED, with one conditional statement each. The approvers' rule holds at SERIALIZABLE with a retry of the whole transaction on 40001 | REPEATABLE READ allows write skew: 0 approvers on call. No level fixes a relay that tracks ids. The outbox delivers at least once, so consumers drop duplicates | `write_skew.py` and `taskqueue.py`, E5, E10 and E11 of Phase 3. Each check exits 1 at the old level, and the relay check at every level. Not run |
| Plans, Phase 4 | Every bulk load, backfill or bulk update ends with `ANALYZE` of its table. A slow query is found with `pg_stat_statements`, and its plan is taken from `auto_explain`. A plan regression is first checked by comparing estimated and actual rows | Autovacuum's ANALYZE comes only after 50 + 0.1 × reltuples changed rows, and only when a worker reaches the table. Partitioned parents are never analyzed by it. A prepared statement can switch to a generic plan after five executions, unless `plan_cache_mode` forbids it | `plan_lab.py`, E4: est 1 against 400,000 before ANALYZE, close after. `plan_cache.py`, E13: generic from execution 6. `find_slow.py`, E14. Not run |
| Change, Phase 4 | Every DDL statement runs with `lock_timeout` and retries. A NOT NULL column goes in by expand/contract, and every step before the contract has a reverse that loses no data | A destructive step, such as DROP COLUMN, has no reverse. A transaction left open still delays every migration on its tables | `migrate_lab.py`, E10 and E11: failures with the naive plan, 0 failed requests and lock waits near 100 ms with expand/contract. Not run |
| Not covered | | Operator deletion and failed backups, the GitLab case of Phase 1, section 1.7. Replicas, and what a replica has: course 5. Transaction ID and multixact wraparound, unless `age(datfrozenxid)` and `mxid_age(datminmxid)` are alerted on, section 4.5 | the alert queries of `bloat.py --xid`. Not run |

The note is one page because each line points to its evidence instead of repeating it. When a test runs and disagrees with its cell, the cell changes, not the test.

---

## 🔍 Check it yourself

- **Check 1.** Open `phase04_planning/cost_model.py:195`, the body of `bitmap_scan()`. Compute the cost per page when the scan reads a quarter of the table's pages. Then use this line to explain a rule. A bitmap scan that reads every page is never cheaper per page than a sequential scan.

- **Check 2.** Open `phase04_planning/explain_tools.py:235`, `worst_node()`. It breaks a tie in q-error in favor of the deeper node. In the bad plan of its self-test, the Nested Loop and the Seq Scan have the same q-error of 400,000. Which node would a tie-break toward the top report, and why would that send you to the wrong fix?

- **Check 3.** Open `phase04_planning/locks.py:226`, `LockQueue.request()`. Suppose it checked only the granted locks and not the waiting ones. Which line of `scenario_queue` changes, and which self-test check fails? Is the model then closer to PostgreSQL or further from it, by the lmgr README's rule?

- **Check 4.** Open `phase04_planning/migrate_lab.py:376`, `run_statement()`. It retries only SQLSTATE 55P03. Suppose it also retried 57014, the statement timeout. Which step of the expand/contract plan could then run far longer than planned? Why is a statement timeout a different signal from a lock timeout?

- **Check 5.** In any repository you own that has database migrations, run `grep -rn "lock_timeout\|CONCURRENTLY\|NOT VALID\|DROP COLUMN" <your repo>/`. Find each migration that adds an index without `CONCURRENTLY`, or drops a column in the release that stopped using it. Name the lock it takes and the traffic it blocks.

---

## ✅ Checkpoint 4 — answer in your own words

The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

1. **Test-out, explain.** On the research's table of section 4.3, `WHERE x < k` selects 45% of the rows. The planner chooses a Seq Scan over the B-tree on `x`. Explain why with the cost arithmetic of both paths. Then name the statistic that would change its mind, and show with numbers how it would.

2. **Test-out, predict.** For each statement, give the lock it takes on `p4_tasks`. Say what it blocks while it waits and while it holds the lock. (a) `CREATE INDEX ON p4_tasks (state)`. (b) `CREATE INDEX CONCURRENTLY ON p4_tasks (state)`. (c) `ALTER TABLE p4_tasks ADD COLUMN note text DEFAULT 'none'`. (d) `ALTER TABLE p4_tasks VALIDATE CONSTRAINT p4_tasks_queue_not_null`. (e) `ALTER TABLE p4_tasks ALTER COLUMN attempts TYPE bigint`. Then take (c) with no `lock_timeout`, queued behind a transaction that has been open for 30 seconds. What happens to SELECTs?

3. **Test-out, demonstrate.** Run E4, E10 and E11. Show the plan before and after ANALYZE, with its estimated and actual rows, buffers and time. Then show the naive migration failing requests and the expand/contract migration failing none, with the lock waits measured. Explain why each result follows from the sections, and not from timing luck.

4. **A colleague says:** "We are on SSDs, so we set `random_page_cost = 1.1` for the whole cluster. The docs say so." Argue for or against. What do the PostgreSQL 14 docs say about this setting, and where does the 1.1 come from? What did the research's table show at 1.1? What should be measured before a cluster-wide change? (b) A second colleague says: "Autovacuum cannot keep up with `orders`. Raise `autovacuum_max_workers` from 3 to 6." Argue for or against, with the budget arithmetic of section 4.5.

5. **This is broken.** `tq_outbox` gets 2 million inserts a day, and a job deletes sent rows every hour. VACUUM runs often, and `n_dead_tup` stays high. The table file grows by about 1 GB a day. `pg_stat_activity` shows one session `idle in transaction` since three days ago. What is the cause, how do you confirm it, and what is the fix? What do you do about the 3 days of growth?

6. **Show the arithmetic.** (a) The autovacuum ANALYZE and VACUUM thresholds of a 50,000,000-row table, at the defaults. (b) `pg_stats` for a column shows `n_distinct` 20 and `null_frac` 0.02. Its MCV list has 4 values whose frequencies add up to 0.92. The table has 8,000,000 rows. Estimate `WHERE col = 'x'` for a value not in the list. (c) A PostgreSQL 14 database has `age(datfrozenxid)` = 1,500,000,000 and assigns 3,000 transaction IDs per second. How long until the WARNING, and until new IDs are refused? (d) A migration uses `lock_timeout = 200ms` and fails 6 times before it gets its lock. At most how long were the table's queries blocked by its attempts? (e) Take PostgreSQL 14 defaults, and a table whose every page is read and dirtied. How many pages can autovacuum process per nap? What is the ceiling in MB/s for all workers together? How long does one pass over a 200 GB heap take at least? (f) `orders` has 10,000,000 rows. For `tenant_id`, `n_distinct` is 1,000 and `null_frac` is 0. The most common tenant has a frequency of 0.1. Estimate `tenant_id = $1` for a generic plan, and for a custom plan with that most common tenant.

7. **Given these constraints, design.** Rename `owner` to `worker_id` in `tq_tasks`. Workers claim tasks all day, and two versions of the worker code run during every deploy. No request may fail, and each step must be undoable until the last. Give the steps and the lock of each. Say which code version must run at each step, and which step cannot be undone.

<details>
<summary>Answer sketches</summary>

1. Seq Scan: 9,346 pages × 1.0 + 1,000,000 × 0.0125 = 21,846, which PostgreSQL 14.24 printed. Bitmap at 45%: the index part is 1,095 pages × 4.0 = 4,380, plus 450,000 × 0.0075 = 3,375. The bitmap adds 112.5. For the heap, Mackert and Lohman gives more than T. So all 9,346 pages are read, at 4.0 − 3.0 × √1 = 1.0 each. The rows: 450,000 × 0.0125 = 5,625. Total 22,839, above 21,846. A plain Index Scan pays 9,346 × 4.0 = 37,384 for the heap alone, because the correlation is 0.0004. Two statistics change the decision. Selectivity: at 40% the bitmap costs 21,338 and wins. Correlation: near 1, the Index Scan's heap cost moves toward 4.0 + 4,205 × 1.0, about 4,209 at 45%. Its total is then about 16,464, far below 21,846. At 10% the model gives 3,664 for the Index Scan against 12,347 for the bitmap.

2. (a) SHARE: blocks INSERT, UPDATE and DELETE for the whole build, and lets SELECTs through. (b) SHARE UPDATE EXCLUSIVE: blocks no reads or writes, only other DDL and VACUUM. It waits for older transactions and scans twice. (c) ACCESS EXCLUSIVE, catalog only since PostgreSQL 11: it holds the lock for milliseconds. (d) SHARE UPDATE EXCLUSIVE: one scan, and reads and writes go on. (e) ACCESS EXCLUSIVE with a rewrite of the table and its indexes, because integer to bigint is not binary coercible. Everything waits for the whole rewrite. That coercibility point is inferred from the docs' rule and was not checked for this type pair. If (c) waits behind a 30-second transaction with no `lock_timeout`, later SELECTs queue behind it. They wait until that transaction ends, by the lmgr README's rule. The research measured 4.04 s for a one-row SELECT behind a 5-second wait.

3. From the runs. E4: est 1 against actual 400,000 on `p4_orders`, and a nested loop with 400,000 inner loops. After ANALYZE, est near 400,000 and a hash join. The plan follows from the formula of section 4.2. All values are in the MCV list, so 1 − 1 = 0, clamped to 1 row. E10: the naive plan holds ACCESS EXCLUSIVE behind the 5-second holder, so requests pass their 1-second deadline. Then old inserts fail with 23502. E11: each lock attempt waits at most 100 ms, so no request passes 1 second. The CHECK lets SET NOT NULL skip its scan. The order is deterministic, because the holder opens before the migration starts. The load is open loop: every request has a fixed start time, so a stall is counted, not hidden.

4. (a) Mostly against a cluster-wide change. The PostgreSQL 14 and 18 docs keep 4.0 because most random reads are assumed to be in cache. They suggest lowering it when the data is likely to be completely in cache. The "SSD 1.1" text is in the PostgreSQL 10 docs. The research's grep did not find it in 13, 14 or 18. On the research's table at 1.1, Index Scans won at 30% and 50%. At 4.0, a bitmap scan won at 30%, and a Seq Scan at 50%. That is correct only if those random reads really are cheap. Before a change, run the hot queries under `EXPLAIN (ANALYZE, BUFFERS)` at both values on one session, and compare time and buffers. If only part of the data is cached, change it per tablespace or per role. (b) Against, on its own. The cost limit of 200 "is distributed proportionally among the running autovacuum workers". Six workers get about 33 units each instead of 66. The worst-case ceiling stays at about 35.5 MB/s. Raise the limit with the workers, or better, give `orders` its own `autovacuum_vacuum_cost_limit`, which also leaves the sharing. Lower its `autovacuum_vacuum_scale_factor`, so each run has less to do. On 14, a change of `autovacuum_max_workers` also needs a restart. First check `wait_event = VacuumDelay` in `pg_stat_activity`, which shows that the budget, not the disk, is the limit.

5. The idle transaction holds the cleanup horizon three days in the past. VACUUM runs and removes nothing that died after its snapshot. So every hourly delete leaves dead rows, and new inserts extend the file. Confirm: `age(backend_xmin)` of that session in `pg_stat_activity` is the largest, and `n_dead_tup` stops falling when VACUUM runs. Fix: end the session with `pg_terminate_backend`, set `idle_in_transaction_session_timeout`, and run VACUUM. The 3 days of growth stay in the file as free space, which new rows reuse. To return it to the system, VACUUM FULL or a rewrite takes ACCESS EXCLUSIVE for the whole copy. Plan it like a migration. The table is append-and-delete, so the free space is likely reused within days.

6. (a) ANALYZE: 50 + 0.1 × 50,000,000 = 5,000,050 changed rows. VACUUM: 50 + 0.2 × 50,000,000 = 10,000,050 dead rows. (b) 1 − 0.92 − 0.02 = 0.06 is left for the 20 − 4 = 16 other values. So 0.06 / 16 = 0.00375. Rows: 8,000,000 × 0.00375 = 30,000. One check remains: the code caps the result at the least common MCV's frequency. If that MCV holds less than 0.00375, the estimate is its frequency times 8,000,000 instead. (c) WARNING at 2,107,483,647: 607,483,647 more IDs, / 3,000 = 202,495 s = 2.3 days. Stop at 2,144,483,647: 644,483,647 / 3,000 = 214,828 s = 2.5 days. (d) Each failed attempt can block the queue for up to 200 ms. That is 6 × 200 = 1,200 ms in total, spread over the backoff pauses. No single pause is longer than 200 ms. The seventh attempt then holds the lock for its own work. (e) A read costs 2 and a dirtied page 20 more, so 22 per page. That gives 200 / 22 = 9 pages per nap. The ceiling is 200 / 0.002 s / 22 = 4,545 pages per second. At 8 kB a page that is 35.5 MB/s, shared by all workers. 200 GB is 204,800 MB. So the heap alone takes at least 204,800 / 35.5 = 5,769 s, about 1.6 hours. (f) Generic: (1 − 0) / 1,000 = 0.001, below the cap of 0.1, so 10,000 rows for any tenant. Custom, for the most common tenant: its MCV frequency, 0.1 × 10,000,000 = 1,000,000 rows. The generic plan is 100 times too low for that tenant.

7. One design, among several. (1) Expand: `ADD COLUMN worker_id text`, ACCESS EXCLUSIVE for milliseconds, with `lock_timeout` and retries. Old code is running. (2) Deploy code that writes both `owner` and `worker_id`, and reads `owner`. The claim UPDATE sets both columns in one statement, so the two stay equal under row locks. (3) Backfill `worker_id = owner` in batches of ids, each its own transaction, with a pause. Row locks only. (4) Deploy code that reads `worker_id`, still writing both. (5) Deploy code that writes only `worker_id`. Every step so far is additive. Undo means going back one code version. The reverse of step 1 drops `worker_id`, which loses only copied data. (6) Contract, in its own later release: `DROP COLUMN owner`, ACCESS EXCLUSIVE for milliseconds. This step cannot be undone. So it waits until no running or rollback-target code reads `owner`, and until a backup exists. A `RENAME COLUMN` would break the old code at once, so it is not used.

</details>

---

## References & Further Learning

The course research fetched these sources on 2026-10-17. The writing, review and depth revision of this phase fetched the rest on 2026-10-18. Every URL was checked again with `check_urls.py` on 2026-10-18. Primary sources come first in each group.

### PostgreSQL 14 documentation: plans and statistics

- **14.1 Using EXPLAIN** — https://www.postgresql.org/docs/14/using-explain.html
  Focus on: 14.1.1 for the cost formula of 458 and the plan change with selectivity, then the three join examples. 14.1.2 for `loops` and BUFFERS, and 14.1.3 for the readings that are not errors. Read it before E4. The examples come from 9.3 sources, so your numbers differ a little.
- **EXPLAIN, PostgreSQL 14 and 18** — https://www.postgresql.org/docs/14/sql-explain.html and https://www.postgresql.org/docs/current/sql-explain.html
  Focus on: the BUFFERS option in each. Off by default in 14, included with ANALYZE in 18.
- **72.1 Row Estimation Examples** — https://www.postgresql.org/docs/14/row-estimation-examples.html
  Focus on: every formula of section 4.2, worked on `tenk1`. The page says its outputs come from version 8.3, so check the method, not the digits.
- **14.2 Statistics Used by the Planner** — https://www.postgresql.org/docs/14/planner-stats.html
  Focus on: `reltuples` and `relpages`, the 100-entry limit, and 14.2.2 on extended statistics and its limits.
- **72.2 Multivariate Statistics Examples** — https://www.postgresql.org/docs/14/multivariate-statistics-examples.html
  Focus on: the `a = b = i % 100` table, before and after CREATE STATISTICS.
- **pg_stats** — https://www.postgresql.org/docs/14/view-pg-stats.html
  Focus on: `null_frac`, `n_distinct`, the MCV columns, `histogram_bounds` and `correlation`.
- **20.7 Query Planning** — https://www.postgresql.org/docs/14/runtime-config-query.html
  Focus on: the cost constants and the text on `random_page_cost`, then `geqo_threshold`, `from_collapse_limit` and `join_collapse_limit`.
- **20.7 Query Planning, PostgreSQL 10** — https://www.postgresql.org/docs/10/runtime-config-query.html
  Focus on: the old `random_page_cost` text with "90%" and the SSD value 1.1. It is the source of a claim many posts still repeat. Read it only to see what changed.
- **20.4 Resource Consumption** — https://www.postgresql.org/docs/14/runtime-config-resource.html
  Focus on: `work_mem`, `hash_mem_multiplier`, `maintenance_work_mem` and `autovacuum_work_mem`.
- **ANALYZE** — https://www.postgresql.org/docs/14/sql-analyze.html
  Focus on: the note that the largest statistics target decides the sample size.
- **PREPARE** — https://www.postgresql.org/docs/14/sql-prepare.html
  Focus on: the Notes, with the five custom plans, the cost comparison, and the `$n` symbols of a generic plan. Read it before E13.
- **pg_prepared_statements** — https://www.postgresql.org/docs/14/view-pg-prepared-statements.html
  Focus on: `generic_plans` and `custom_plans`, new in 14.
- **15.1 How Parallel Query Works** — https://www.postgresql.org/docs/14/how-parallel-query-works.html
  Focus on: the Gather node and its workers, and "Workers Planned" in a plan. Then section 20.4 for `max_parallel_workers_per_gather` and `work_mem` per worker.
- **32.2 When to JIT?** — https://www.postgresql.org/docs/14/jit-decision.html
  Focus on: the three cost thresholds, the JIT block in EXPLAIN, and the rule for generic plans.
- **F.30 pg_stat_statements** — https://www.postgresql.org/docs/14/pgstatstatements.html
  Focus on: the setup with `shared_preload_libraries` and `compute_query_id`, the columns, and the example ranking. Read it before E14.
- **F.4 auto_explain** — https://www.postgresql.org/docs/14/auto-explain.html
  Focus on: `log_min_duration`, `log_analyze` and its warning, `log_timing`, `sample_rate` and `log_level`.
- **20.9 Run-time Statistics** — https://www.postgresql.org/docs/14/runtime-config-statistics.html
  Focus on: `track_io_timing` and `compute_query_id`.

### PostgreSQL 14 documentation: maintenance, locks and DDL

- **25.1 Routine Vacuuming** — https://www.postgresql.org/docs/14/routine-vacuuming.html
  Focus on: 25.1.2 on space, and 25.1.3 on statistics and partitioned tables. Then 25.1.5 on wraparound, with its updated recovery steps, and 25.1.6 on the autovacuum thresholds. It is the most important page for section 4.5.
- **20.10 Automatic Vacuuming** — https://www.postgresql.org/docs/14/runtime-config-autovacuum.html
  Focus on: the threshold, scale factor, worker and freeze settings, with their defaults. Then `autovacuum_vacuum_cost_limit`, and the sentence on sharing it among workers.
- **20.11 Client Connection Defaults** — https://www.postgresql.org/docs/14/runtime-config-client.html
  Focus on: `lock_timeout`, `statement_timeout` and `idle_in_transaction_session_timeout`. Then the freeze ages, `vacuum_freeze_min_age`, `vacuum_freeze_table_age`, their multixact forms and `vacuum_failsafe_age`, and `session_preload_libraries`.
- **19.11 Client Connection Defaults, PostgreSQL 17** — https://www.postgresql.org/docs/17/runtime-config-client.html
  Focus on: `transaction_timeout`, new in 17, and its warning about `postgresql.conf`.
- **20.8 Error Reporting and Logging** — https://www.postgresql.org/docs/14/runtime-config-logging.html
  Focus on: `log_autovacuum_min_duration`, −1 in 14, `log_lock_waits` and `log_temp_files`.
- **20.12 Lock Management** — https://www.postgresql.org/docs/14/runtime-config-locks.html
  Focus on: `deadlock_timeout`, the delay before a waiter checks for deadlock and cancels a normal autovacuum.
- **19.10 Vacuuming, PostgreSQL 18** — https://www.postgresql.org/docs/18/runtime-config-vacuum.html
  Focus on: `autovacuum_vacuum_max_threshold`, new in 18, and `autovacuum_worker_slots`.
- **28.2 The Statistics Collector, and 28.4 Progress Reporting** — https://www.postgresql.org/docs/14/monitoring-stats.html and https://www.postgresql.org/docs/14/progress-reporting.html
  Focus on: `pg_stat_user_tables`, `pg_stat_database`'s temp columns, the `VacuumDelay` wait event, then `pg_stat_progress_vacuum` and `pg_stat_progress_create_index`.
- **pg_replication_slots, and 20.6 Replication** — https://www.postgresql.org/docs/14/view-pg-replication-slots.html and https://www.postgresql.org/docs/14/runtime-config-replication.html
  Focus on: `xmin` against `catalog_xmin`, then `hot_standby_feedback` and `max_slot_wal_keep_size`.
- **F.31 pgstattuple** — https://www.postgresql.org/docs/14/pgstattuple.html
  Focus on: `pgstattuple_approx`, and how it uses the visibility map to skip pages.
- **13.3 Explicit Locking** — https://www.postgresql.org/docs/14/explicit-locking.html
  Focus on: 13.3.1, each mode with the commands that take it and its conflicts. `locks.py` rebuilds its table from this page.
- **ALTER TABLE** — https://www.postgresql.org/docs/14/sql-altertable.html
  Focus on: the lock of each subcommand, `ADD COLUMN` with a default, and `SET NOT NULL` with a CHECK. Then `NOT VALID`, `VALIDATE CONSTRAINT`, and the notes on rewrites and DROP COLUMN.
- **CREATE INDEX** — https://www.postgresql.org/docs/14/sql-createindex.html
  Focus on: "Building Indexes Concurrently": the two scans, the wait, the invalid index, and the limit on partitioned tables.
- **REINDEX** — https://www.postgresql.org/docs/14/sql-reindex.html
  Focus on: the paragraph that compares REINDEX with dropping and creating the index. It gives the table lock and the index lock, which section 13.3.1 summarizes as ACCESS EXCLUSIVE.
- **5.11 Table Partitioning** — https://www.postgresql.org/docs/14/ddl-partitioning.html
  Focus on: 5.11.1 for the benefits, 5.11.2.2 for ATTACH and DETACH, and 5.11.2.3 for the limitations. Then 5.11.4 for pruning, and 5.11.6 for the number of partitions.
- **Release notes 9.5.0, 11.0, 12.0 and 14.0** — https://www.postgresql.org/docs/release/9.5.0/ , https://www.postgresql.org/docs/release/11.0/ , https://www.postgresql.org/docs/release/12.0/ , https://www.postgresql.org/docs/release/14.0/
  Focus on: the lower foreign-key lock in 9.5, and the constant default without a rewrite in 11. Then `SET NOT NULL` without a scan and `REINDEX CONCURRENTLY` in 12. In 14: the wider wraparound margins, `vacuum_failsafe_age`, Memoize, the lower `vacuum_cost_page_miss`, B-tree bottom-up deletion and the `pg_prepared_statements` counters.
- **Release notes 13.0, 15.0, 16.0, 17.0 and 18.0** — https://www.postgresql.org/docs/release/13.0/ , https://www.postgresql.org/docs/release/15.0/ , https://www.postgresql.org/docs/release/16.0/ , https://www.postgresql.org/docs/release/17.0/ , https://www.postgresql.org/docs/release/18.0/
  Focus on: HashAggregate spilling and B-tree deduplication in 13. `hash_mem_multiplier` 2.0 and `log_autovacuum_min_duration` 10min in 15. `EXPLAIN (GENERIC_PLAN)` and delay settings honoured per block in 16. The 1GB vacuum memory limit removed, and `transaction_timeout`, in 17. `autovacuum_vacuum_max_threshold` in 18.

### PostgreSQL source

- **costsize.c, REL_14_24** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/optimizer/path/costsize.c
  Focus on: `clamp_row_est` at lines 199 to 215, and `cost_seqscan` from 226. Then the index heap cost at 662 to 729, and Mackert and Lohman at 840 to 900. The bitmap cost per page is at 1006 to 1008. `cost_model.py` cites each line.
- **selfuncs.c, REL_14_24** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/utils/adt/selfuncs.c
  Focus on: `var_eq_const` from line 292. Its branch for a value outside the MCV list is at lines 405 to 432. Then `genericcostestimate` from line 6464.
- **explain.c, REL_14_24** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/commands/explain.c
  Focus on: line 1619, where rows are divided by loops, and the JSON key names that `explain_tools.py` reads.
- **analyze.c, REL_14_0** — https://github.com/postgres/postgres/blob/REL_14_0/src/backend/commands/analyze.c
  Focus on: line 1919, `stats->minrows = 300 * attr->attstattarget;`.
- **selfuncs.h and cost.h, REL_14_0** — https://github.com/postgres/postgres/blob/REL_14_0/src/include/utils/selfuncs.h and https://github.com/postgres/postgres/blob/REL_14_0/src/include/optimizer/cost.h
  Focus on: the default selectivities at lines 34 and 37, and the cost defaults at lines 24 to 32.
- **varsup.c, REL_14_0** — https://github.com/postgres/postgres/blob/REL_14_0/src/backend/access/transam/varsup.c
  Focus on: the error and its old hint at lines 129 and 131. Then the limits at lines 362, 378 and 392. Compare REL_13_0 for the older limits, and REL_17_0 for the new message and hint, by changing the tag.
- **index.c, REL_14_24** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/catalog/index.c
  Focus on: `reindex_index`. It locks the table in SHARE mode at line 3602, and the index in ACCESS EXCLUSIVE at line 3641.
- **lmgr README, REL_14_0** — https://github.com/postgres/postgres/blob/REL_14_0/src/backend/storage/lmgr/README
  Focus on: lines 364 and 386, the two rules of the lock queue.
- **postgres.c, REL_14_24** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/tcop/postgres.c
  Focus on: lines 3298 to 3307, the lock timeout and statement timeout errors with their SQLSTATEs, and line 3314, `canceling autovacuum task`.
- **plancache.c and prepare.c, REL_14_24** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/utils/cache/plancache.c and https://github.com/postgres/postgres/blob/REL_14_24/src/backend/commands/prepare.c
  Focus on: `choose_custom_plan` at lines 1047 to 1077 and the planning charge at 1125 to 1127. Then `prepare.c` line 655, where EXPLAIN EXECUTE uses the same cache. `setrefs.c`, https://github.com/postgres/postgres/blob/REL_14_24/src/backend/optimizer/plan/setrefs.c , keeps every range-table entry at line 369.
- **allpaths.c, REL_14_24** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/optimizer/path/allpaths.c
  Focus on: `compute_parallel_worker`, lines 3750 to 3826. Read `costsize.c`'s `get_parallel_divisor`, lines 6060 to 6085, beside it.
- **vacuumlazy.c and vacuum.c, REL_14_24** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/access/heap/vacuumlazy.c and https://github.com/postgres/postgres/blob/REL_14_24/src/backend/commands/vacuum.c
  Focus on: the autovacuum log line at lines 773 to 861, and the 6-byte dead-row list at 193. Then `vacuum_delay_point` in `vacuum.c`, lines 2205 to 2251.
- **autovacuum.c and proc.c, REL_14_24** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/postmaster/autovacuum.c and https://github.com/postgres/postgres/blob/REL_14_24/src/backend/storage/lmgr/proc.c
  Focus on: the thresholds at lines 3226 to 3255 and the cost balancing at 3003 to 3009. Then the activity text at 3314 to 3329. In `proc.c`, the autovacuum cancel at 1433 to 1489, and the lock-wait log line at 1624.
- **trigger.c, REL_14_24** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/commands/trigger.c
  Focus on: line 1280, where DROP TRIGGER locks the table in ACCESS EXCLUSIVE mode.

### The paper

- **How Good Are Query Optimizers, Really?, Leis, Gubichev, Mirchev, Boncz, Kemper and Neumann, PVLDB 9(3), 2015** — https://www.vldb.org/pvldb/vol9/p204-leis.pdf
  Focus on: section 2 for the setup, Table 1 for single-table q-errors, and Figure 3 with section 3.2 for joins. Then section 4.1 and Figure 6 for the nested-loop timeouts, and section 5 for the cost model. Its section 5 finds a median cost-model error of 38%, and 30% after tuning. All on PostgreSQL 9.4, with the data in memory. About 60 minutes. Read it after E4.

### Books and course notes

- **PostgreSQL 14 Internals, Egor Rogov, Postgres Professional, 2023** — https://edu.postgrespro.com/postgresql_internals-14_en.pdf
  Focus on: 6.6 and 6.7 for the throttle and the vacuum log. Then 7.2 and 7.3 for freezing, and 16.3 for generic plans. Then 20.2 and 20.3 for heap fetches and lossy bitmaps, 21.2 for Memoize, and 22 and 23 for spills. It is free, and every example ran on PostgreSQL 14.
- **CMU 15-445/645, Fall 2025, lecture notes 11, 12 and 15** — https://15445.courses.cs.cmu.edu/fall2025/notes/11-sorting.pdf , https://15445.courses.cs.cmu.edu/fall2025/notes/12-joins.pdf and https://15445.courses.cs.cmu.edu/fall2025/notes/15-optimization1.pdf
  Focus on: external merge sort and hash aggregation in 11, and the partitioned hash join in 12. Then section 11 of 15, the System R join search.

### Production reports and migration guides

- **Manta postmortem of 2015-07-27, Joyent, archived copy** — https://web.archive.org/web/20220528044329/https://www.joyent.com/blog/manta-postmortem-7-27-2015
  Focus on: the timeline, the three-way lock interaction, and the cost-based delay during the outage. It does not name its PostgreSQL version.
- **BUG #19076: Generic query plan is extremely slow, pgsql-bugs, 2025-10-07** — https://www.postgresql.org/message-id/19076-4d897c04a44a9627%40postgresql.org
  Focus on: the two plans, and Laurenz Albe's reply on `plan_cache_mode`. PostgreSQL 17.6.
- **BUG #17540: Prepared statement: PG switches to a generic query plan which is consistently much slower, pgsql-bugs, 2022** — https://www.postgresql.org/message-id/17540-7aa1855ad5ec18b4@postgresql.org
  Focus on: the reporter's note on pgx and `PQexecPrepared`, and the database-wide workaround. PostgreSQL 14.4.
- **Django: Maybe disable PostgreSQL's JIT to speed up many-joined queries, Adam Johnson, 2023-11-09** — https://adamj.eu/tech/2023/11/09/django-disable-postgresql-jit/
  Focus on: the cost estimate that triggered JIT, and the `-c jit=off` fix. PostgreSQL 14. A personal blog, not peer reviewed.
- **Prepared statements, psycopg 3** — https://www.psycopg.org/psycopg3/docs/advanced/prepare.html
  Focus on: `prepare_threshold`, and when psycopg prepares a query by itself.
- **pg_repack documentation** — https://reorg.github.io/pg_repack/
  Focus on: the requirements, the disk space, and the two short exclusive locks.

- **Zero-downtime Postgres migrations, the hard parts, Chris Sinjakli, GoCardless** — https://gocardless.com/blog/zero-downtime-postgres-migrations-the-hard-parts/
  Focus on: the 15-second outage and its three-transaction reproduction. Its foreign-key lock claim is for 9.4, as section 4.7 explains. The earliest archive copy is from 2015-10-09, and the page says it was edited in June 2024.
- **Zero-downtime Postgres migrations, a little help, GoCardless** — https://gocardless.com/blog/zero-downtime-postgres-migrations-a-little-help/
  Focus on: the defaults of `ActiveRecord::SaferMigrations`, 750 ms and 1,500 ms.
- **Zero-downtime Postgres schema migrations need this: lock_timeout and retries, Nikolay Samokhvalov, postgres.ai, 2021-09-23** — https://postgres.ai/blog/20210923-zero-downtime-postgres-schema-migrations-lock-timeout-and-retries
  Focus on: the three-session reproduction, the 50 ms timeout, and the thought experiment on retries without backoff.
- **Schema changes and the Postgres lock queue, Xata, 2024** — https://xata.io/blog/migrations-and-exclusive-locks
  Focus on: the lock_timeout section. Its author was not recorded by the research.
- **Migration style guide, GitLab** — https://docs.gitlab.com/development/migration_style_guide/
  Focus on: the duration limits, the roll-forward rule, and the lock retry section. Read it beside the code below, because the two disagree.
- **with_lock_retries.rb, GitLab, master** — https://gitlab.com/gitlab-org/gitlab/-/blob/master/lib/gitlab/database/with_lock_retries.rb
  Focus on: `DEFAULT_TIMING_CONFIGURATION`, 41 pairs of a timeout and a pause, repeated 15 times. That is 615 attempts, whose timeouts and pauses add up to 2,673.75 s. The file's own comment says about 40 minutes.
- **Batched background migrations, GitLab** — https://docs.gitlab.com/development/database/batched_background_migrations/
  Focus on: batch sizes, throttling on database health, and the estimate formula.
- **strong_migrations, Andrew Kane** — https://github.com/ankane/strong_migrations
  Focus on: the list of unsafe operations, "Setting NOT NULL on an existing column", "Backfilling data", and the timeout settings.
- **Online migrations at scale, Jacqueline Xu, Stripe, 2017** — https://stripe.com/blog/online-migrations
  Focus on: the four phases of dual writing. The post does not name its database.
- **Safe operations for high volume PostgreSQL, 2019 draft, James Coleman** — https://gist.github.com/jcoleman/1e6ad1bf8de454c166da94b67537758b
  Focus on: the goals at the top, the ~2-second lock limit and the rollback rule, and the DROP COLUMN process. A draft gist. The published version returned HTTP 403 to the research.
- **Transaction ID Wraparound in Postgres, David Cramer, Sentry, 2015-07-23** — https://blog.sentry.io/transaction-id-wraparound-in-postgres/
  Focus on: the timeline and the recovery by TRUNCATE. Its one-million margin is PostgreSQL 13 era, and its single-user advice is out of date.
- **What we learned from the recent Mandrill outage, Mailchimp, 2019** — https://mailchimp.com/what-we-learned-from-the-recent-mandrill-outage/
  Focus on: the warning in November 2018 and the vacuum estimates. By Eric Muntz, dated 2019-03-26.

### A talk

- **Explaining the Postgres Query Optimizer, Bruce Momjian, Citus Con 2022** — https://www.youtube.com/watch?v=wLpcVM9qxV0
  Focus on: scan methods from 0:04:19, and join methods from 0:12:13 to 0:21:18. The times come from the video's chapter list, because the captions did not load.
- **Explaining the Postgres Query Optimizer, slides, Bruce Momjian** — https://momjian.us/main/writings/pgsql/optimizer.pdf
  Focus on: slides 13 to 29 for the plan per letter, and slides 30 to 37 for the three joins. The slide table has only 410 rows, so use the course research's 1,000,000-row table for switch points.

---

## Cheatsheet

```
READ A PLAN (EXPLAIN (ANALYZE, BUFFERS); BUFFERS is off by default in PG 14)
  per node: est rows vs actual rows; total = actual rows x loops
  q-error = max(est/actual, actual/est), both floored at 1 (Leis 2015)
  the error enters at the lowest node where est and actual diverge
  cost units: 1.0 = one sequential page. Not milliseconds
  buffers of a node include its children. hit = shared_buffers, read = OS
  track_io_timing (off) adds I/O Timings. TIMING FALSE drops per-node clock

FIND IT (PG 14)
  pg_stat_statements  shared_preload_libraries + restart, compute_query_id
                      auto. Rank total_exec_time; stddev/mean for flips
  auto_explain        log_min_duration, log_analyze, log_buffers,
                      log_timing off, sample_rate. Logs the plan that ran

PARALLEL AND JIT (lab: max_parallel_workers_per_gather 0, jit off)
  defaults 14         2 workers per Gather, jit on, table >= 8MB
  divisor             workers + (1 - 0.3 x workers): 2 workers = 2.4
  partial node        est x 2.4 vs actual x loops (loops = 3)
  Gather              +1000 setup, +0.1 per row passed up
  JIT                 cost > 100000 compile, > 500000 inline + optimize
  work_mem            per process and per sort or hash

ESTIMATES (docs 72.1, selfuncs.c REL_14_24)
  rows = reltuples scaled to current pages x selectivity
  = v in MCV        its frequency
  = v not in MCV    (1 - sum(mcf) - null_frac) / (n_distinct - #mcv), capped
                    at the least common MCV. All values in MCV -> 0 -> 1 row
  a AND b           product (independence). Fix: CREATE STATISTICS
  no statistics     = 0.005    < 0.3333
  ANALYZE sample    300 x default_statistics_target 100 = 30,000 rows
  autoanalyze after 50 + 0.1 x reltuples changed rows (n_mod_since_analyze)
  CREATE INDEX      updates reltuples/relpages, NOT pg_stats
  n_distinct        ALTER COLUMN ... SET (n_distinct = -0.3333), next ANALYZE
  histogram ends    a B-tree index supplies the real min or max

GENERIC PLANS (plancache.c REL_14_24)
  executions 1-5 custom. Then generic if its cost < average custom cost
  generic estimate  col = $1: (1 - null_frac) / n_distinct, capped at top MCV
  signals           $1 in EXPLAIN EXECUTE; pg_prepared_statements counters
  fix               plan_cache_mode = force_custom_plan, per role or session
  psycopg 3         prepares after prepare_threshold 5 executions

COSTS (defaults, PG 14 docs 20.7.2)
  seq_page_cost 1.0  random_page_cost 4.0  cpu_tuple_cost 0.01
  cpu_index_tuple_cost 0.005  cpu_operator_cost 0.0025  effective_cache_size 4GB
  seq scan          pages x 1.0 + rows x (0.01 + 0.0025 per qual)
  bitmap page cost  4.0 - 3.0 x sqrt(pages read / table pages)
  index heap I/O    Mackert-Lohman pages x 4.0, toward 1.0 by correlation^2
  research table    1 M rows, 9,346 pages: index 1 row, bitmap to 40%, seq 45%+
                    (measured 2026-10-17, PG 14.24, narrow rows, corr 0.0004)

JOINS
  nested loop  outer + rows(outer) x inner      hash  one pass over each side
  merge        sorted inputs. work_mem 4MB, hash_mem_multiplier 1.0 (PG 14,
               2.0 from PG 15)
  from_collapse_limit 8, join_collapse_limit 8, geqo_threshold 12
  danger       low outer estimate -> nested loop, cost grows with the product
  Memoize      new in 14: Hits, Misses, Evictions. enable_memoize
  spills       Sort Method: external merge; Hash Batches > 1; HashAgg
               Disk Usage (since 13). temp_files, log_temp_files

VACUUM AND WRAPAROUND (PG 14)
  removable    died before the oldest open snapshot. File never shrinks
  autovacuum   50 + 0.2 x reltuples dead rows. 3 workers, naptime 1min
               PG 18 caps it: autovacuum_vacuum_max_threshold 100 M
  throttle     200 units, then 2 ms nap, SHARED by workers. hit 1 miss 2
               dirty 20: worst 9 pages/nap, 35.5 MB/s ceiling for all
  more speed   per-table autovacuum_vacuum_cost_limit, not more workers
  signals      log_autovacuum_min_duration (-1 in 14, 10min in 15),
               pg_stat_progress_vacuum, wait_event VacuumDelay
  dead tids    6 bytes each: 64MB = 11.18 M per pass ("index scans: N")
  horizon held by  idle in transaction, slots (xmin), prepared xacts
  VACUUM FULL  ACCESS EXCLUSIVE, extra disk = table size
  online       REINDEX INDEX CONCURRENTLY (12+), pg_repack (2 short locks)
  wrap         oldest datfrozenxid + 2,147,483,647
  forced vacuum 200 M   failsafe 1.6 B   WARNING at wrap - 40 M   stop at - 3 M
  freezing     freeze_min_age 50 M, aggressive at freeze_table_age 150 M
  multixact    min 5 M, table 150 M, forced 400 M. mxid_age(datminmxid)
  wraparound   "(to prevent wraparound)" autovacuum is NOT cancelled by
               DDL. A queued DDL then blocks all traffic (Joyent 2015)
  recovery     docs: no single-user mode. The PG 14 binary's hint still says so

PARTITIONING
  pruning      only from the partition key: plan time, executor start
               ("Subplans Removed"), execution
  costs        no key -> every partition. PK must include the key.
               autovacuum never ANALYZEs the parent. No CIC on the parent
  attach       SHARE UPDATE EXCLUSIVE on parent; add a matching CHECK first
  detach       CONCURRENTLY (new in 14), then DROP: no dead rows

LOCKS (docs 13.3.1)
  SELECT AS   writes RX   CREATE INDEX S (blocks writes)   CIC, VACUUM,
  ANALYZE, VALIDATE SUX   ADD FK SRX on both tables   most ALTER: AX
  REINDEX      S on the table, AX on the index (13.3.1 says AX)
  queue        a waiting AX blocks every later request, SELECTs included
  measured     SELECT behind a queued ALTER 4.04 s; lock_timeout 100ms:
               ALTER failed at 0.18 s, SELECT 0.07 s (research, PG 14.24)
  lock_timeout postgres.ai 50 ms, GitLab 0.1-2 s, GoCardless 750 ms,
               strong_migrations 10 s. Retry 55P03 with backoff and jitter
  timeouts     statement_timeout per role, not in postgresql.conf;
               idle_in_transaction_session_timeout; transaction_timeout 17+
  log_lock_waits  off by default: "still waiting for ... after N ms"
  before DDL   long xacts and wraparound vacuums in pg_stat_activity;
               invalid indexes: pg_index WHERE NOT indisvalid

ADD A NOT NULL COLUMN UNDER LOAD
  1 ADD COLUMN c (no default, or a constant: no rewrite since PG 11)
  2 deploy code that writes c        3 backfill in batches, pause, no txn
  4 ADD CHECK (c IS NOT NULL) NOT VALID   5 VALIDATE CONSTRAINT (SUX)
  6 SET NOT NULL (scan skipped since PG 12)   7 DROP the CHECK
  measured     ADD COLUMN DEFAULT 42 2.5 ms; DEFAULT random() 997 ms rewrite;
               SET NOT NULL 0.68 ms with CHECK, 48 ms without (1 M rows)
  errors       55P03 lock timeout  57014 statement timeout  23514 CHECK
               23502 NOT NULL  42703 undefined column

ROLLBACK
  additive steps have a reverse that loses nothing; DROP, narrow, overwrite,
  rename do not. Undo code first, schema second. Contract in its own release
```

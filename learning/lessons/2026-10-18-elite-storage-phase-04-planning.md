In Phase 3 you made the course's task queue keep its rules while many transactions ran at once. The order data of Phases 1 and 2 now also lives in PostgreSQL 14, because the reports need SQL. The table `orders` holds 10 million orders, and `order_events` holds three events per order. A dashboard report counts the events of every pending order, per tenant. It takes 20 ms in staging, with 100,000 orders, and 9 seconds in production.

1. **09:00** The last ANALYZE of `orders` runs, and almost no order is pending.
2. **10:00** A payment provider fails, and 4,000,000 orders become pending in one hour.
3. **11:00** The report's plan expects 42 pending rows, gets 4,000,000 and takes 9 s.
4. **11:20** `CREATE INDEX` on `orders (status)` starts without `CONCURRENTLY`. Every write on `orders` waits, and SELECTs still run.
5. **11:31** The index is built and writes resume. The report still takes 9 s.

The running case. Times and counts are an example, and the lab reproduces its shape at a smaller size.

Nothing in the query changed. The statistics still described the table before 10:00, and the new index stopped checkout without fixing the report. Both problems can be predicted. The planner works from statistics you control, and each migration statement takes a lock you can name in advance. This last phase ends with the course's one-page storage note.

What you must know, in five claims. Each one is taught below, in this order.

1. **A plan goes wrong at the lowest node where the expected row count and the real row count differ.** Find the slow query and its wrong node.
2. **Row estimates use the statistics of the last ANALYZE, so a bulk change leaves them wrong until the next ANALYZE.** Predict an estimate, and fix a plan that slows after five runs.
3. **The planner prices scans and joins from row estimates, so a low estimate makes a slow join look cheap.** Explain a scan choice and a 9-second join with arithmetic.
4. **VACUUM removes only row versions that died before the oldest open snapshot, and frees their space without shrinking the file.** Find what holds cleanup back, and how far wraparound is.
5. **A schema change also blocks traffic while it waits for its lock, so every one needs a lock_timeout.** Add a NOT NULL column with no failed request.

## What you bring from Phases 2 and 3

- **Pages.** PostgreSQL reads and caches its files in pages of 8,192 bytes, in `shared_buffers`.
- **B-trees.** A B-tree index finds a key with one page read per level, 3 levels for 10 million keys, with the upper levels in 776 KiB.
- **The heap.** A row lives in the heap, the table's own file, and an index entry points at its page.
- **Row locks.** A row lock lasts until its transaction ends, and a second writer of the row waits.
- **Table locks.** Every statement locks each table it uses, and a SELECT's `ACCESS SHARE` waits only for `ACCESS EXCLUSIVE`.
- **The soft block.** A request that waits for a lock also blocks later conflicting requests. `lock_timeout` is 0, no limit, by default.

The first three come from Phase 2 and the last three from Phase 3. Snapshots and multixacts from Phase 3 come back where they are used.

## Which node in the plan went wrong?

A plan is a tree of nodes. The leaves are scans of a table or an index, and the nodes above them join, sort or count rows. `EXPLAIN` prints each node's estimate: a *cost*, in units where reading one page in order costs 1.0, and the rows it expects. `EXPLAIN ANALYZE` also runs the query. It adds the time, the rows that came out and *loops*, the number of times the node ran.

```
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

The report's plan from `EXPLAIN (ANALYZE, BUFFERS)`. It is an example plan, not a run, and its numbers follow the opening case.

<details><summary>Predict: the Index Scan on order_events prints rows=3. How many rows did it return, and is 3 wrong?</summary>

It returned 3 × 4,000,000 = 12,000,000 rows, because it ran 4,000,000 times. Its estimate of 3 per run is right, because every order has three events. The wrong number is how often it ran, and another node decided that.

</details>

1. Read each node's rows as an average per loop, so its total is rows times loops.
2. Measure each gap with the *q-error*, the factor between the estimate and the true count. An estimate of 10 or of 1,000 for a true 100 both have a q-error of 10.
3. Start at the leaves. The Seq Scan on `orders` expected 42 rows and returned 4,000,000, a q-error of 95,238.
4. Stop at the lowest node with a large q-error, because every node above it inherits the error.

```
The report's plan, read bottom up. est = expected rows per execution
HashAggregate        est 126        actual 1,000
  └─ Nested Loop     est 126        actual 12,000,000
       ├─ Seq Scan orders           est 42   actual 4,000,000  loops 1
       │    q-error 4,000,000 / 42 = 95,238  ◄── the error enters here
       └─ Index Scan order_events   est 3    actual 3   loops 4,000,000
            q-error 1: right per loop. Run 95,238 times too often
```

Two readings send you to the wrong fix. One reads per-loop rows as totals, although the Index Scan's `rows=3` hides about 16 million page accesses. The other starts from the node with the largest time, the Nested Loop, while the cause sits one level below it.

<details><summary>Go deeper: what cost and BUFFERS mean, how the lab computes the q-error, and four readings that are not errors</summary>

#### Rows per loop, and running EXPLAIN ANALYZE safely

PostgreSQL divides a node's row count by its loops before it prints it, which is why the total is rows times loops. `EXPLAIN ANALYZE` runs the statement, so on an UPDATE or DELETE the rows change for real. Run it inside `BEGIN` and `ROLLBACK`, on a copy, because it still takes its row locks while it runs.

Each node prints two pairs, `cost=startup..total` and `actual time=startup..total`. The startup value is spent before the node returns its first row, and the total after its last row. Actual time is in milliseconds, and `width` is the expected average row size in bytes.

#### The cost formula of a sequential scan

The cost of an upper node includes the cost of all its child nodes. The simplest formula is the one for a sequential scan. The PostgreSQL docs compute it for their table `tenk1`, which has 358 pages and 10,000 rows: (358 × 1.0) + (10,000 × 0.01) = 458. The 1.0 is `seq_page_cost` and the 0.01 is `cpu_tuple_cost`. A WHERE clause adds `cpu_operator_cost`, 0.0025, per row. So the same scan with a filter costs 458 + 10,000 × 0.0025 = 483. The access-path section below uses these formulas to answer why the planner chose a sequential scan.

#### BUFFERS

`BUFFERS` adds the page counts of each node. A hit is a page found in `shared_buffers`. A read is a page that missed and came from the operating system, which may still have it in its page cache, as Phase 2 showed. The count of an upper node includes the pages of all its child nodes. Two version facts matter:

- In PostgreSQL 14, `BUFFERS` is off by default. You must ask for it, as `EXPLAIN (ANALYZE, BUFFERS)`.
- In PostgreSQL 18, buffers information is included automatically when ANALYZE is used.

In the example plan, the inner scan made 15,200,000 + 812,000 = 16,012,000 page accesses. That is about 4 per loop. It fits three B-tree levels for 10 million keys, as Phase 2 computed, plus one heap page. These are example numbers. If an order's three events sit on three pages, as in the lab, a probe reads three heap pages.

#### The q-error in the lab's code

The lab reads plans as JSON, so that a script can compare the two numbers on every node. From `phase04_planning/explain_tools.py:113`:

```
# from phase04_planning/explain_tools.py:113, q_error(). Docstring cut, logic unchanged
def q_error(est: float, actual: float) -> float:
    e, a = max(est, 1.0), max(actual, 1.0)
    return max(e / a, a / e)
```

Both sides are floored at 1, because the planner never estimates fewer than one row. That rule is `clamp_row_est` in `costsize.c`, and the estimates section shows a case where it decides the estimate. The `Node` class compares `Plan Rows` with `Actual Rows`, which are both per loop, and multiplies by `Actual Loops` only for the total.

#### Four readings that are not estimation errors

1. A node under `LIMIT` stops early. Its actual rows are lower than its estimate, and nothing is wrong.
2. A merge join can stop reading one input early, and it can count re-read inner rows twice.
3. `BitmapAnd` and `BitmapOr` nodes always report their actual row counts as zero.
4. Timing has its own cost. The overhead that EXPLAIN ANALYZE adds can be significant, and network transfer to the client is not included.

#### Two timing options

A `read` in BUFFERS can come from the OS page cache or from the disk, and the count cannot tell them apart. `track_io_timing` can. It is off by default, because it reads the clock on every I/O, and that may cause significant overhead on some platforms. When it is on, EXPLAIN with BUFFERS adds a line `I/O Timings: read=...`. Many reads with a small read time came from the page cache. The other option goes the opposite way. `EXPLAIN (ANALYZE, TIMING FALSE)` keeps the actual rows and drops the clock reads of every node. The tool `pg_test_timing` measures the clock's cost on your machine.

#### Wrong and right readings of the example plan

"cost=325612 means 325 s."

"The slow node is the one with the largest time, the Nested Loop."

"Plain EXPLAIN shows the problem."

Cost is in page units. Time is actual time: 9,012 ms here.

The wrong node is where est and actual first differ: the Seq Scan.

Plain EXPLAIN shows rows=42 and nothing to compare it with.

</details>

<details><summary>Evidence</summary>

PostgreSQL 14 docs, section 14.1.1 for the cost units, the 458 formula and "the cost of an upper-level node includes the cost of all its child nodes". Section 14.1.2 for loops: "the actual time and rows values shown are averages per-execution", and for the safe BEGIN and ROLLBACK form. Section 14.1.3 for the four readings that are not errors. `explain.c` at tag REL_14_24, line 1619, divides the rows by the loops before printing, and line 3582 prints the I/O Timings line. The EXPLAIN pages of the PostgreSQL 14 and 18 docs give the BUFFERS defaults. `clamp_row_est` is in `costsize.c`, REL_14_24, lines 199 to 215. The q-error is defined by Leis and others in "How Good Are Query Optimizers, Really?", PVLDB 2015, section 3.1. `track_io_timing` and `TIMING FALSE` are from the PostgreSQL 14 docs, section 20.9 and the EXPLAIN page.

</details>

## How do you find that plan in production?

At work you must first find the query among thousands. Its plan in psql may also differ from the plan the application got. Two modules that ship with PostgreSQL 14 close that gap.

1. **pg_stat_statements**which statement costs the most server time
2. **auto_explain**the plan that statement really ran, with its values
3. **est against actual**the lowest node where they differ
4. **fix the input**the statistics, not the plan

1. Load `pg_stat_statements`, which keeps totals per *normalized statement*, the query text with its constants replaced by symbols. It needs `shared_preload_libraries` and a server restart.
2. Rank its rows by `total_exec_time` to see where the server spends its time.
3. Load `auto_explain`, which logs the plan of every statement slower than `auto_explain.log_min_duration`. With `log_analyze` on, the log holds the plan that ran, with actual rows.
4. Set `auto_explain.log_timing = off` and a `sample_rate`, because per-node timing slows every statement, logged or not.

Your server's plans also read differently from the lab's, because PostgreSQL 14 turns on two features that the lab turns off.

- *Parallel query* splits a scan across a leader and 2 worker processes under a Gather node. So `loops=3`, and rows are an average per process. Compare the estimate times 2.4, not 3, with the actual rows times loops.
- *JIT*, just-in-time compilation, turns the plan's expressions into machine code once the plan's cost passes 100,000. A wrong estimate can push the cost past that. One many-join query took 3.5 seconds with JIT and 10 milliseconds without it.

Compare expected rows with actual rows times loops, and fix the lowest node that differs.

Reading per-loop rows as totals, or diagnosing your psql plan instead of the logged one.

<details><summary>Go deeper: the two rankings, the auto_explain settings, and the rules of parallel plans and JIT</summary>

#### Try this now

Run `uv run python phase04_planning/explain_tools.py --sql "select count(*) from pg_class c join pg_attribute a on a.attrelid = c.oid"`. Find the node with the most loops, and multiply its rows by its loops.

#### Why the lab turns parallel query and JIT off

Every lab plan in this phase runs with `max_parallel_workers_per_gather = 0` and `jit = off`. Parallel query changes how rows and loops read, and JIT's compile time would blur a before-and-after timing. So the lab's plans are serial and uncompiled, and your server's plans are not. The leader's share is 1 − 0.3 × 2 = 0.4, which is where the 2.4 comes from. The JIT case was a Django application on PostgreSQL 14. Its fix was the connection option `-c jit=off` for the application, and its cause was again a wrong row estimate. JIT only made it cost more.

#### Setting up pg_stat_statements

From PostgreSQL 14 the module also needs a query identifier. `compute_query_id = auto`, the default, turns that on when the module loads. Run `CREATE EXTENSION pg_stat_statements` in the database you read from. Two rankings answer two different questions:

```
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

The second ranking is this course's own rule of thumb, and no source tests it. Section 4.2 in the comment is the estimates section of this lesson, where the generic plan is taught. `temp_blks_written` above 0 means a sort or a hash spilled to disk, as the join section shows.

#### The auto_explain settings

The default of `auto_explain.log_min_duration` is −1, which logs nothing. With `log_analyze` on, per-node timing runs for every statement, and the docs say it "can have an extremely negative impact on performance". So turn the per-node clock off and sample:

```
# postgresql.conf. Verified setting names, PostgreSQL 14 docs F.4.1
session_preload_libraries = 'auto_explain'
auto_explain.log_min_duration = '500ms'
auto_explain.log_analyze = on
auto_explain.log_buffers = on
auto_explain.log_timing = off      # actual rows and buffers, no per-node clock
auto_explain.sample_rate = 0.1     # explain one statement in ten
```

`session_preload_libraries` only takes effect at the start of the connection, so it needs no restart. Connections that are already open, such as a pool's, keep running without it. That is inferred from the same rule. A connection fails if the library is not found. The logged plan is the plan that ran, with the parameter values it ran with. E14 sets up both modules, and `find_slow.py` prints both rankings.

#### When the planner uses a parallel plan

A Gather node starts worker processes. Each worker runs the plan below the Gather on its own part of the table. The leader also runs that part when it is not busy, and the rows flow up to the Gather, which passes them on. Three rules decide whether the planner uses it:

1. The table must reach `min_parallel_table_scan_size`, 8MB, which is 1,024 pages. Each factor of 3 above that allows one more worker, up to `max_parallel_workers_per_gather`, which is 2 by default.
2. Only the CPU part of a scan is divided. The divisor is the worker count plus a leader share of 1 − 0.3 × workers, so 2 workers give 2 + 0.4 = 2.4. The disk part is not divided, because most operating systems already prefetch pages read in order.
3. The Gather adds `parallel_setup_cost`, 1000, plus `parallel_tuple_cost`, 0.1, for each row it passes up.

Apply these rules to the report's Seq Scan, which costs 325,250 serial:

```
CPU part     10,000,000 rows x 0.0125           = 125,000
disk part    325,250 - 125,000                   = 200,250 pages
parallel     200,250 + 125,000 / 2.4 (52,083)    = 252,333
Gather       + 1,000 + 0.1 x 42 rows (4)         = about 253,337
serial                                            = 325,250
workers      200,250 pages, far above 1,024       = 2 allowed
```

So at the defaults this scan would most likely run as a Parallel Seq Scan under a Gather. That is inferred from the formulas and was not run.

#### Reading a real parallel plan

This plan comes from PostgreSQL BUG #19076, reported on PostgreSQL 17.6. The estimates section returns to that report. Lines are removed, and the numbers are copied from the report:

```
Gather  (cost=44906.68..46937.80 rows=19344 width=24) (actual time=102.801..103.506 rows=2326 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  ->  Partial HashAggregate  (cost=43906.68..44003.40 rows=9672 width=24) (actual time=93.682..93.757 rows=775 loops=3)
        ->  Hash Join  (cost=6066.79..43819.26 rows=17484 width=32) (actual time=12.902..92.674 rows=11509 loops=3)
              ->  Parallel Seq Scan on contacts  (cost=0.00..36177.50 rows=373366 width=16) (actual time=0.435..55.023 rows=288122 loops=3)
              ->  Hash  (cost=5275.46..5275.46 rows=63307 width=32) (actual time=12.053..12.054 rows=37282 loops=3)
```

Five rules read it:

- `loops=3` is the leader plus 2 workers. A node's actual rows are an average per process, so the parallel scan returned 288,122 × 3 = 864,366 rows in total.
- Its estimate is per process too, but it was divided by 2.4, not by 3. So compare 373,366 × 2.4 = 896,078 with 864,366. The q-error is 1.04. Read naively, 373,366 against 288,122 looks 1.30 off.
- The Gather's own estimate depends on the node below it. Above a scan or a join, it is the total estimate. Above a partial aggregate, it is the per-process estimate times the workers, without the leader share. Here that is 9,672 × 2 = 19,344.
- The Hash node here is not parallel aware, and it shows the full 37,282 rows with `loops=3`. So each of the three processes built its own full hash table, which is inferred from those two facts. Its rows are not split, so compare them directly: 63,307 / 37,282 = 1.70.
- `work_mem` applies to each process on its own. A query with 4 workers may use up to 5 times as much CPU time, memory and I/O bandwidth as one with none. So this plan held three hash tables at once, one per process. If `Workers Launched` is below `Workers Planned`, the pool of worker processes was full, and the plan runs with fewer workers than expected, which may be inefficient.

`explain_tools.py` applies the first two rules to every node under a Gather. They fit scans and joins. A partial aggregate estimates groups per process, and one group can appear in every process, so read its q-error as rough. That is inferred from the planner's rules. Its `--server-defaults` flag keeps your server's settings, so E15 shows a parallel plan on the lab's own `p4_orders`.

#### When JIT runs, and what it prints

The WHERE clause is one of the expressions JIT compiles. The planner decides from the total estimated cost of the plan:

| Total cost above | What JIT adds | Default |
|---|---|---|
| `jit_above_cost` | compile the expressions | 100000 |
| `jit_inline_above_cost` | also inline small functions and operators | 500000 |
| `jit_optimize_above_cost` | also apply expensive optimizations | 500000 |

The example plan costs 325,612, which is above 100,000 and below 500,000. So its EXPLAIN ANALYZE would most likely end with a JIT block, without inlining or optimization. That is inferred from the thresholds, not run. JIT also needs a server compiled `--with-llvm`. This course did not check whether the owner's Homebrew PostgreSQL 14 has it, and without it JIT never runs. The docs' own sample shows the block that EXPLAIN ANALYZE prints at the end:

```
 JIT:
 Functions: 3
 Options: Inlining false, Optimization false, Expressions true, Deforming true
 Timing: Generation 1.259 ms, Inlining 0.000 ms, Optimization 0.797 ms, Emission 5.048 ms, Total 7.104 ms
```

In the Django case, PostgreSQL expected many rows where each join added few, and the cost passed `jit_above_cost`. One more rule matters for prepared statements, which the estimates section explains. When a statement reuses one plan, the JIT decision uses the settings in effect when it was prepared.

</details>

<details><summary>Evidence</summary>

pg_stat_statements: PostgreSQL 14 docs, section F.30, including that "a server restart is needed" to add it. auto_explain: section F.4 and F.4.1, with the warning quoted above. `session_preload_libraries`: section 20.11. The lab's settings are in `lab_settings()`, `phase04_planning/explain_tools.py:318`. The parallel defaults are from sections 20.4 and 20.7. The worker rule is `compute_parallel_worker`, `allpaths.c` lines 3776 to 3823. The divisor is `get_parallel_divisor`, `costsize.c` lines 6060 to 6085, and the prefetching comment is at lines 279 and 280. The Gather estimate is `cost_gather`, `costsize.c` lines 386 to 391, and `allpaths.c` lines 2631 and 2632, all at REL_14_24. The per-process estimate is divided at `costsize.c` line 288. The parallel plan is from BUG #19076, reported on 2025-10-07. The JIT thresholds and the sample block are from sections 32.2 and 20.7. The Django case is Adam Johnson's post of 2023-11-09, whose fix comment says "3.5 seconds with JIT vs 10 milliseconds without".

</details>

## Where did rows=42 come from?

An estimate is a row count times a *selectivity*, the fraction of rows a condition keeps. The row count is `reltuples` in `pg_class`. The selectivity comes from `pg_stats`, which *ANALYZE* fills from a sample of 30,000 rows, however large the table is. Per column it keeps the *MCV list*, the most common values with each one's fraction of rows. It also keeps `n_distinct`, the number of distinct values. At 09:00 it stored this example row for `orders.status`.

```
 null_frac | n_distinct | most_common_vals         | most_common_freqs
-----------+------------+--------------------------+---------------------------
         0 |         11 | {shipped,paid,created}   | {0.6,0.25,0.1499667}
```

<details><summary>Predict: reltuples is 10,000,000. What does WHERE status = 'paid' expect, and what does WHERE status = 'pending' expect? pending is not in the list.</summary>

For `paid`, 0.25 × 10,000,000 = 2,500,000 rows. For `pending`, about 42 rows, the number in the bad plan, because the list leaves almost nothing for the values outside it.

</details>

For a value outside the list, the planner spreads what the list leaves evenly over the other distinct values.

```
MCV sum        0.6 + 0.25 + 0.1499667          = 0.9999667
left over      1 - 0.9999667 - null_frac 0     = 0.0000333   (1 / 30,000)
other values   n_distinct 11 - 3 MCVs          = 8
selectivity    0.0000333 / 8                   = 0.00000417
estimate       0.00000417 x 10,000,000         = 41.7, printed as rows=42
```

Nothing in `pg_stats` changes until the next ANALYZE. Autovacuum runs one after 50 + 0.1 × `reltuples` changed rows, 1,000,050 here. Only 3 of its workers run at once, so a busy server can leave the table stale for an hour. `CREATE INDEX` updates the row count and leaves the column statistics alone, so the team's index left the estimate at 42. So run `ANALYZE` on the table right after every bulk load, backfill or bulk update.

<details><summary>Go deeper: every estimate formula, the lab's extreme case, correlated columns, three more controls, and how wrong estimates are in practice</summary>

#### Where the inputs come from, in more detail

The sample has 300 × the statistics target rows, and the default target is 100, so 30,000 rows. `null_frac` is the fraction of NULLs. The 0.0000333 left over is 1 / 30,000, so one sampled row in 30,000 had a status outside the list.

Three ways an ANALYZE runs, and why the case stayed stale:

- Autovacuum runs ANALYZE on a table after 50 + 0.1 × `reltuples` rows changed since the last one. For `orders` that is 1,000,050 rows, and the incident passed it.
- But autovacuum must reach the table. A launcher starts one worker per database each minute, and at most 3 run at once. Several large tables can keep all of them busy for a long time, which is the likely reason the case stayed stale. The daemon also has no knowledge of whether the changes will move the statistics.
- A manual `ANALYZE orders` reads only the sample, so it is fast on a large table. This course did not time it. It takes a `SHARE UPDATE EXCLUSIVE` lock, which blocks neither reads nor writes.

`CREATE INDEX` is not on that list. It updates `reltuples` and `relpages`, and column statistics come only from ANALYZE. So the new index changed the row count the planner starts from, left 42 where it was, and the report stayed slow.

#### The estimate formulas

A histogram here has buckets of equal frequency, so a value's position inside its bucket gives the fraction of rows below it. The worked numbers are the docs' own, on the table `tenk1`:

| Condition | Formula | Docs example |
|---|---|---|
| `col = v`, v in the MCV list | the stored frequency of v | `stringu1 = 'CRAAAA'`: 0.003 x 10,000 = 30 rows |
| `col = v`, v not in the list | (1 − sum of MCV frequencies − null_frac) / (n_distinct − number of MCVs) | `'xxx'`: 0.96966667 / 666 = 0.0014559, so 15 rows |
| `col < v` | (whole histogram buckets below v + the linear fraction of v's bucket) / buckets | `unique1 < 1000`: (1 + 7 / 1004) / 10 = 0.100697, so 1007 rows |
| `a AND b` | the product of the two selectivities | 0.100697 x 0.0014559 = 0.0001466, so 1 row |
| `t1.x = t2.y`, no MCV lists | (1 − nf1)(1 − nf2) x min(1 / nd1, 1 / nd2) | 50 x 10,000 x 0.0001 = 50 rows |
| no statistics at all | 0.005 for `=`, 0.3333 for `<` | `selfuncs.h`, REL_14_0, lines 34 and 37 |

The histogram leaves out the values in the MCV list. Its bounds are null when the MCV list accounts for the entire population. The code adds two rules to the second row. It divides only when n_distinct minus the MCV count is above 1. And the result is never more than the frequency of the least common MCV. `cost_model.py --self-test` checks the 42 arithmetic and the docs' own examples.

#### The row count before ANALYZE

Both `reltuples` and `relpages` are as of the last VACUUM, ANALYZE or CREATE INDEX. The planner reads the table's current page count, and if it differs from `relpages`, it scales `reltuples` to match.

#### The lab's version is more extreme

`plan_lab.py` loads orders with three statuses only: `shipped`, `paid` and `created`. ANALYZE then puts all three in the MCV list, and their frequencies add up to 1. For `pending`, the code computes 1 − 1 − 0 = 0. The division is skipped, because 3 − 3 is not above 1. Then `clamp_row_est` raises the 0 to 1 row. So any count of pending orders, however large, gets `rows=1` until the next ANALYZE. That is inferred from the source, and the lab prints the estimate so you can see it.

```
The lab, --rows 1,000,000. Expected, worked out from the source, not run
build      ANALYZE: MCV {shipped 0.60, paid 0.25, created 0.15}, sum 1
incident   UPDATE 400,000 orders to 'pending'. No ANALYZE
           the file grows: new versions go to new pages (the VACUUM section)
diagnose   'pending': 1 - 1 = 0, clamped to rows=1. Actual 400,000
           the row count is scaled up by the larger file
team-fix   CREATE INDEX on status: rows=1 still
fix        ANALYZE: 'pending' enters the MCV list at about 0.4, and
           the estimate is close to the real 400,000
```

After the UPDATE, the file holds about 1,400,000 row versions, and 1,000,000 of them are live. Before ANALYZE, the planner scales the old `reltuples` of 1,000,000 by the larger page count, so it counts about 1,400,000 rows. The dead versions inflate the count. ANALYZE counts live rows only, so it stores `reltuples` near 1,000,000 and a frequency near 0.4 for `pending`. Both values are inferred from the docs' rules, not run. `plan_lab.py` prints `reltuples`, the scaled count and `most_common_freqs`, so you can check them.

#### Correlated columns

The AND row of the formula table multiplies selectivities. The planner treats the conditions as independent, an assumption that does not hold when column values are correlated. The docs' example has 10,000 rows with `a = b = i % 100`:

- `WHERE a = 1 AND b = 1` gets 1% × 1% = 0.01%, so `rows=1`. The actual count is 100.
- After `CREATE STATISTICS ... (dependencies) ON a, b` and ANALYZE, the estimate is `rows=100`.
- `GROUP BY a, b` estimates 1000 groups against an actual 100, until the statistics object also has `ndistinct`.

The course research repeated this on PostgreSQL 14.24 and got the same numbers: 1 became 100, and 1000 became 100. Functional dependencies help only with equality to constants and with IN lists of constants. They do not help ranges, LIKE, or comparisons of two columns. In the order data, `tenant_id` decides `region`, so the same fix applies to a filter on both.

#### Three more controls of the statistics

1. **An n_distinct override.** ANALYZE estimates n_distinct from its 30,000-row sample. A column whose values each appear only a few times can come out far too low. `ALTER TABLE order_events ALTER COLUMN order_id SET (n_distinct = -0.3333)` sets it by hand. A negative value is a fraction of the rows, so −0.3333 means one distinct order id per three events. The option overrides the estimates of later ANALYZE runs, so it takes effect at the next ANALYZE, and it takes only SHARE UPDATE EXCLUSIVE. Join estimates divide by n_distinct, as the join row of the formula table shows. Whether the sample under-counts `order_id` here is inferred, not measured.
2. **A per-table analyze threshold.** The counter that autovacuum compares with 50 + 0.1 × reltuples is `n_mod_since_analyze` in `pg_stat_user_tables`. In the code it is `changes_since_analyze`. `ALTER TABLE orders SET (autovacuum_analyze_scale_factor = 0.01)` lowers the trigger for `orders` from 1,000,050 to 50 + 0.01 × 10,000,000 = 100,050 changed rows. The incident passed even that within minutes. So the setting shortens the stale window and does not remove it, which is inferred from the arithmetic.
3. **The ends of the histogram.** A range condition can reach the first or last histogram bound. Then the planner does not trust the stale bound, and replaces that endpoint with the true column minimum or maximum. It reads them from a plain B-tree index on the column, and it skips every other kind of index. The code's comment says this helps when the min or max is moving. So `created_at >= now() - interval '1 hour'`, with an index on `created_at`, gets a sensible estimate an hour after the last ANALYZE. The opening case's `status = 'pending'` gets no such help, because it is an equality on a value outside the MCV list. That comparison is inferred from the code, not run.

#### How wrong estimates are in practice

One well-known measurement ran 113 join queries on an IMDB data set of 3.6 GB, on PostgreSQL 9.4, with all data in memory:

- For single-table conditions, PostgreSQL's q-error had a median of 1.00 and a 90th percentile of 2.08. The 95th was 6.10, and the maximum 207.
- For joins, 16% of PostgreSQL's estimates with 1 join were off by a factor of 10 or more. That grew to 32% with 2 joins and 52% with 3, so the errors grow exponentially with the number of joins. Most of the estimates were too low.

So most single-table estimates are close, and errors multiply through joins. These numbers were not repeated on PostgreSQL 14. Treat them as the shape of the problem, not as your numbers.

#### A bulk change between two ANALYZEs

A backfill fills a new or changed column for existing rows, and it can change a column's values in minutes. So can an import or an incident. Autovacuum reaches the table later, or never if it is off for that table, and every plan in between uses the old distribution. A per-table `autovacuum_analyze_scale_factor` makes the automatic ANALYZE come sooner on a large table. Raise the detail for one column with `ALTER TABLE ... ALTER COLUMN ... SET STATISTICS`, which also takes only `SHARE UPDATE EXCLUSIVE`.

</details>

<details><summary>Evidence</summary>

The sample size is `stats->minrows = 300 * attr->attstattarget;` at `analyze.c` line 1919, tag REL_14_0. The formulas are from the PostgreSQL 14 docs, section 72.1, whose examples say they came from version 8.3. The out-of-list branch is also checked in `selfuncs.c`, REL_14_24, lines 405 to 432. The even-spread assumption and the page scaling of `reltuples` are from section 72.1. The autovacuum analyze defaults are from sections 20.10 and 25.1.6, which also warn that several large tables can keep "all autovacuum workers" busy "for a long period". The ANALYZE lock is from section 13.3.1. That CREATE INDEX updates only `reltuples` and `relpages` is from section 14.2. The correlated example is from sections 14.2.2 and 72.2, and the course research ran it on 2026-10-17. The n_distinct override is from the PostgreSQL 14 ALTER TABLE page and Rogov, "PostgreSQL 14 Internals", page 277. The counter mapping is at `system_views.sql` line 647, `pgstatfuncs.c` line 196 and `autovacuum.c` line 3255, all REL_14_24. The histogram end rule is `selfuncs.c` REL_14_24, lines 1082 to 1088 and line 6031. The practice numbers are from Leis and others, PVLDB 2015, Table 1 and section 3.2. The hunter's note could not read that paper this run, and the source phase verified them.

</details>

## Why does the sixth execution get a different plan?

ANALYZE fixes an estimate only when the planner can see the value. A *prepared statement* hides it: the server parses the query once and runs it many times with new values. Drivers create them without being asked. Each run uses a *custom plan*, made for its values, or a *generic plan*, made once for every value.

1. The first five executions get custom plans, and the server keeps their average estimated cost.
2. From the sixth, it uses the generic plan if that plan's cost is below the average. Then the generic plan keeps winning.
3. The generic plan cannot see `$1`, so it estimates `col = $1` as (1 − null_frac) / n_distinct, an average.

Send the report with `WHERE o.tenant_id = $1`, over 1,000 tenants and 10,000,000 orders. Every tenant then gets an estimate of 10,000 orders. A tenant with 10% of the orders, an example, really has 1,000,000.

PostgreSQL BUG #19076, on PostgreSQL 17.6, shows the failure. Executions 1 to 5 ran a parallel Hash Join in 103.8 ms. From execution 6, the generic plan ran a Nested Loop in 7,179.9 ms, with the same parameters. ANALYZE did not help, because the statistics were fresh. The fix is `ALTER ROLE reporting SET plan_cache_mode = force_custom_plan`. It plans every run of the report's role, and other roles keep their planning savings.

- runs 1 to 5, custom: 103.8 ms
- run 6 on, generic: 7,179.9 ms
Top node time from BUG #19076 on PostgreSQL 17.6, copied from the report and not run.

An estimate comes from pg_stats at the last ANALYZE, and a generic plan uses an average.

Answering a bad estimate with a new index: the estimate stays wrong, and the build blocks writes.

<details><summary>Go deeper: the plan cache code, the planning charge, two bug reports, and what else changes a cached plan</summary>

#### Try this now

After E4, run `psql -h /tmp -p 5432 -d storage_lab -c "select attname, n_distinct, most_common_vals, most_common_freqs from pg_stats where tablename = 'p4_orders'"`. Compute one value's estimate by hand, then compare it with `EXPLAIN select * from p4_orders where status = 'paid'`.

#### The rule and the failure, in more detail

psycopg 3 prepares a query on the server after it has run `prepare_threshold` times on one connection, 5 by default. A generic plan saves the planning time. Once the generic plan wins, the average of the five custom plans no longer changes, so the generic plan keeps winning. The generic estimate is capped at the most common value's frequency. By the join arithmetic later in this lesson, an average tenant's plan can be a nested loop.

In BUG #19076, the query joined two tables and filtered on `tenant_id = $1` and `status = $2`. The custom plan's top node took 103.8 ms, and the generic plan's top node took 7,179.9 ms. The generic plan's scan expected 354 rows and returned 864,365. An ANALYZE and a statistics target of 1,000 did not help.

Three signals show a generic plan:

- `EXPLAIN EXECUTE name(values)` shows the plan the cache chose, and a `$1` in it means the plan is generic.
- `SELECT name, generic_plans, custom_plans FROM pg_prepared_statements` counts each kind in the session. The columns are new in PostgreSQL 14.
- `plan_cache_mode` is `auto` by default, and a high stddev in `pg_stat_statements` can point at a statement whose plan flips.

#### The choice in the code

`choose_custom_plan()` in `plancache.c` picks between the two plans:

```
/* from plancache.c, REL_14_24, lines 1059 to 1077. Comments cut, logic unchanged */
	if (plansource->num_custom_plans < 5)
		return true;                     /* true: make a custom plan */
	avg_custom_cost = plansource->total_custom_cost / plansource->num_custom_plans;
	if (plansource->generic_cost < avg_custom_cost)
		return false;                    /* false: use the generic plan */
	return true;
```

Each custom cost also carries a planning charge, at lines 1125 to 1127. It is 1000 × `cpu_operator_cost` × (range-table entries + 1). The range table is the plan's list of tables, plus one entry for each `JOIN` clause. So a two-table query written with `JOIN ... ON` has three entries, and its charge is 2.5 × 4 = 10. The join's entry is kept by `setrefs.c` at REL_14_24, line 369. The claim that the generic plan keeps winning is inferred from this code.

#### Custom and generic plans side by side

|  | Custom plan | Generic plan |
|---|---|---|
| Made | for each execution, with its values | once, for any value |
| Estimate for `tenant_id = ...` | the MCV list or the leftover formula | (1 − null_frac) / n_distinct |
| In EXPLAIN | the value, such as `tenant_id = 7` | the symbol `$1` |
| In `pg_prepared_statements`, new in 14 | counted in `custom_plans` | counted in `generic_plans` |
| Planning time | paid on every execution | paid once |

#### The two bug reports

In BUG #19076, the generic plan ran "even if I do not change the parameters", and its inner index scan ran 864,365 loops. Laurenz Albe answered on the list that the choice of plan "is a heuristic". He guessed that the first five executions used values with few rows, which the report does not show. He suggested `plan_cache_mode = force_custom_plan` for that statement. BUG #17540, on PostgreSQL 14.4, has the same shape. Its reporter used pgx, a Go driver, and wrote that he "wasn't even aware I was using prepared statements". He measured the generic plan as "over 6500x slower", and set `force_custom_plan` for the whole database. So this is the opening case's failure, a nested loop picked from a low estimate, with a different cause.

#### More about the setting and the signals

- `force_custom_plan` plans every execution, and `force_generic_plan` never replans. The setting is considered when a cached plan is to be executed, so a role-level setting applies to that role's sessions. That use is inferred from the setting's scope.
- PostgreSQL 16 adds `EXPLAIN (GENERIC_PLAN)`. It shows the generic plan of a query that has `$1` and no values.
- A partitioned table needs this too. A generic plan prunes partitions only at executor start, as the partitioning section shows.
- Put psycopg's threshold of 5 together with the server's five custom plans. A query on one connection would then first meet a generic plan around its eleventh execution. That is inferred from the two documents and not run. E13 shows the switch on the lab's data with `plan_cache.py`, which uses SQL PREPARE.

#### Two facts from the study note

- A prepared statement lasts only for the current database session. A connection pooler therefore decides which sessions count the five executions. What a transaction-mode pooler does here was not checked.
- The server re-plans a cached statement when its tables had a DDL change or new planner statistics since the last use. So an ANALYZE after a backfill can also change an application's cached plans at that moment. What this does to the five-custom-plans counter was not checked.

</details>

<details><summary>Evidence</summary>

The two kinds of plan and the five-execution rule are from the PostgreSQL 14 docs for PREPARE, which also give the per-session lifetime and the re-planning rule quoted in the study note. psycopg 3's `prepare_threshold` of 5 is from the psycopg 3 documentation. The generic estimate is `var_eq_non_const()` in `selfuncs.c`, REL_14_24, lines 508 to 522. BUG #19076 was reported on 2025-10-07, and BUG #17540 in 2022. The `pg_prepared_statements` counters are from the PostgreSQL 14 release notes, `EXPLAIN (GENERIC_PLAN)` from the 16 release notes, and `plan_cache_mode` from the PostgreSQL 14 docs, section 20.7.

</details>

## Why did the planner choose a sequential scan over the index?

After ANALYZE, the planner knows that 40% of the orders are pending. It still ignores the new index on `status`, and it prices four ways to read a table. A page read in order costs `seq_page_cost`, 1.0, and a page read out of order costs `random_page_cost`, 4.0.

| Path | What it reads |
|---|---|
| Seq Scan | every heap page in file order, and checks each row against the filter |
| Index Scan | index entries in key order, then each row's heap page, so a page can be read many times |
| *Bitmap Heap Scan* | the index first, then the matching pages sorted into file order, each needed page once |
| *Index Only Scan* | the index only, for pages that the *visibility map*, a per-page flag kept by VACUUM, marks all-visible |

<details><summary>Predict: 1,000,000 narrow rows sit in 9,346 pages, with a B-tree on a column x of random values. For WHERE x < k, which plan wins at one row, 1%, 40% and 45%?</summary>

Index Scan, Bitmap Heap Scan, Bitmap Heap Scan, then Seq Scan at 45%. The course research measured this on PostgreSQL 14.24 at the defaults, with the data in memory.

</details>

Each row costs 0.0125 of CPU in both scans: 0.01 for the row and 0.0025 for the filter.

1. The Seq Scan reads every page once: 9,346 × 1.0 + 1,000,000 × 0.0125 = 21,846.
2. At 40%, the bitmap reads all 9,346 pages at 1.0 each, plus CPU for its index and rows: 21,338.
3. At 45%, it pays CPU for more rows: 22,839, now above the Seq Scan.
4. A plain Index Scan pays a random page per row on an uncorrelated column, 48,276 at 40%.

- 40% Seq Scan: 21,846
- 40% Bitmap: 21,338
- 40% Index Scan: 48,276
- 45% Seq Scan: 21,846
- 45% Bitmap: 22,839
Estimated cost by the lesson's cost model, worked by hand and not timed.

These switch points belong to this table. The column's *correlation*, how closely the physical row order follows the column's order, moves them most. In index order, the Index Scan at 10% costs 3,664 against 12,347 for the bitmap.

Force the index for the whole application, because one report used a sequential scan.

```
ALTER DATABASE app SET enable_seqscan = off;
ALTER DATABASE app SET random_page_cost = 1.0;
```

At 40% the forced plan is the Index Scan, with a random heap read per row. At `random_page_cost` 1.0 the model prices it at 17,319, below the Seq Scan's 21,846. If those reads are not cached, the default 4.0 prices the same plan at 48,276.

Fix the input that was wrong, then let the planner choose. Compare other plans in one session only.

```
ANALYZE orders;
SET enable_seqscan = off;   -- only to compare, then RESET
```

<details><summary>Go deeper: the cost of each path, the research's full results, what moves the switch, heap fetches and lossy pages</summary>

#### The predict, in more detail

The research's B-tree on `x` is 19 MB, and all settings were defaults. PostgreSQL 14.24 printed exactly `cost 21846.00` for the Seq Scan. The bitmap reads each of the 9,346 pages at 4.0 − 3.0 × √1 = 1.0. The Index Scan's heap part alone at 40% is 9,346 × 4.0 = 37,384. When `x` is stored in index order, the Index Scan wins at 10% as well, because its heap reads become one sequential run. Between 40% and 45% the CPU per row decides. A lower `random_page_cost` also favors the index, and wider rows mean more pages for the same rows.

#### The cost of each path

The formulas are from `costsize.c` and `selfuncs.c` at REL_14_24, and the defaults from the PostgreSQL 14 docs. `cost_model.py` implements them, and its docstring names each line:

| Path | Heap pages read | Cost per heap page | CPU per row |
|---|---|---|---|
| Seq Scan | all T pages | `seq_page_cost` 1.0 | `cpu_tuple_cost` 0.01 + 0.0025 per condition |
| Index Scan | from the Mackert and Lohman formula, up to T | `random_page_cost` 4.0, moved toward 1.0 by correlation² | 0.01, plus 0.0075 per index entry |
| Bitmap Heap Scan | each needed page once, at most T | 4.0 − 3.0 × √(pages read / T) | 0.0125, plus 0.0075 per index entry |
| Index Only Scan | as Index Scan, times the share of pages not all-visible | as Index Scan | as Index Scan |

The Mackert and Lohman formula estimates how many distinct pages N random row fetches touch, given the cache size `effective_cache_size`. When the table fits in that cache, it is 2TN / (2T + N), capped at T. The bitmap formula charges almost `random_page_cost` for a few scattered pages, and only `seq_page_cost` once it reads every page. From `phase04_planning/cost_model.py:195`:

```
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

#### The arithmetic in full

T is 9,346 pages and N is 1,000,000 rows. The index has about 2,432 pages, which is 19 MB in 8 kB pages.

```
Seq Scan       9,346 x 1.0 + 1,000,000 x 0.0125                 = 21,846
Bitmap 40%     index 973 pages x 4.0 = 3,892, + 400,000 x 0.0075 = 3,000,
               + 100 for the bitmap. Mackert and Lohman gives more than T,
               so all 9,346 pages at 4.0 - 3.0 x sqrt(1) = 1.0. Rows 400,000 x 0.0125 = 5,000
               3,892 + 3,000 + 100 + 9,346 + 5,000                = 21,338 (+0.4 B-tree descent)
Bitmap 45%     4,380 + 3,375 + 112.5 + 9,346 + 5,625               = 22,839
Index Scan 40% heap 9,346 x 4.0 = 37,384 (correlation near 0)
               + 3,892 + 3,000 for the index + 4,000 for the rows  = 48,276
```

#### What the research measured

These are the planner's choices by estimated cost, on the table above. It has about 107 rows per page and `correlation(x) = 0.0004`:

| Rows selected | Plan |
|---|---|
| 1 row | Index Scan |
| 0.001% to 40% | Bitmap Heap Scan |
| 45% and above | Seq Scan |
| `SELECT x` only, 0.1% to 50% | Index Only Scan |
| `random_page_cost = 1.1`, at 30% and 50% | Index Scan |

The model reproduces the first three rows by hand, and `cost_model.py --self-test` asserts each of them. At `random_page_cost = 1.1` and 50%, the model also picks the Index Scan, at 20,369 against 20,809 for the bitmap. The model leaves out small terms, so treat any gap under a few percent as a tie. At 30% it puts the bitmap 0.7% below the Index Scan that the research saw. The research did not time the queries, so the cheapest cost was not shown to be the fastest plan. It inferred that row width, correlation and the cache settings move the switch, and E3 lets you change each one.

#### Why no parallel plan won

The research ran at all defaults, so parallel plans were allowed, and none won. A Gather charges `parallel_tuple_cost`, 0.1, for each row it passes up. At 40%, a parallel scan would cost 9,346 + 12,500 / 2.4 = 14,554. The Gather adds 1,000, and 400,000 × 0.1 = 40,000. That is 55,554 against the bitmap's 21,338. So a parallel plan wins when the work below the Gather removes most rows, as a count or a selective filter does. That is inferred from the formulas, not run.

#### What moves the switch, in detail

1. **Correlation.** `pg_stats.correlation` is the statistical correlation between the physical row order and the logical order of the column values. Near 1 or −1, an index scan is estimated to be cheaper, because its heap reads become one sequential run.
2. **`random_page_cost`.** The PostgreSQL 14 and 18 docs keep the default at 4.0. It is that low because most random reads, such as indexed reads, are assumed to be in cache. The "90%" cached and the SSD value "1.1" that many blogs quote come from the PostgreSQL 10 docs. The research did not find that text in 13, 14 or 18.
3. **`effective_cache_size`.** The default is 4GB, and it enters the Mackert and Lohman formula for index scans. The research set it to 64MB and saw no plan change from 0.1% to 30% on this table.
4. **Row width.** Wider rows mean more pages for the same rows. The seq scan cost grows with pages, and the index cost grows with rows, so the switch moves.

#### Two signals in the plan: heap fetches and lossy pages

Both show in EXPLAIN ANALYZE, and both explain an index path that is slower than its cost:

- An Index Only Scan prints `Heap Fetches`. It counts the rows the scan checked in the heap, because their page was not marked all-visible. One run shows `Heap Fetches: 132109` on a new table, and `Heap Fetches: 0` after VACUUM, for the same 132,109 rows. So an index-only scan on a table that VACUUM has not reached reads the heap like an index scan.
- A Bitmap Heap Scan prints `Heap Blocks: exact=... lossy=...`. When the bitmap does not fit in `work_mem`, some of its parts keep only the page and not the row. Every row on a lossy page is checked again, and the plan counts the rejects as `Rows Removed by Index Recheck`. With `work_mem = '512kB'` one run shows `Heap Blocks: exact=5178 lossy=8269` and `Rows Removed by Index Recheck: 1145721`. With more memory, the same query showed `exact=13447`.

`explain_tools.py` prints all three keys for every node that has them.

#### Forcing a path, and what an unused index costs

The planner's `enable_*` settings make a path look very expensive. They are a crude tool, useful for seeing other plans, and not a fix. A low-selectivity index also has a write cost, for the reason Phase 2 showed. An UPDATE adds an entry to every index of the table. The exception is a heap-only tuple update, **HOT**, which stays on its page and changes no indexed column. An index on `status` that no plan uses still pays that cost on every order change.

#### So why the sequential scan

The condition kept 40% of a table whose order is unrelated to `status`, so every plan reads almost every page. On the research's table, 40% is just below the switch. The bitmap costs 21,338 there, 2.3% below the sequential scan's 21,846. The `orders` table has wider rows and its own index size, so its switch can fall below 40%. That is inferred from the formulas, and not computed for `orders`. The statistic that would change the planner's mind is the selectivity: at 1% the bitmap wins. Correlation would also change it, if the pending orders sat together on disk.

</details>

<details><summary>Evidence</summary>

The research table was built by the course research on PostgreSQL 14.24 on 2026-10-17, at all defaults with the data in memory, and its plan table is that run. The bitmap sorting is from the PostgreSQL 14 docs, section 14.1.1, which call the bitmap "the mechanism that does the sorting". The visibility map is from section 25.1.4. The cost defaults are from section 20.7.2. The correlation definition is from the `pg_stats` docs. The `random_page_cost` text is from the PostgreSQL 14, 18 and 10 docs. Heap fetches and lossy pages are from Rogov, "PostgreSQL 14 Internals", sections 20.2 and 20.3. The `enable_*` wording is from section 14.1.1.

</details>

## Why did the nested loop take 9 seconds?

The Seq Scan took 2.1 of the 9 seconds, and the join took most of the rest. The planner chose its method from the estimate of 42 rows.

#### Nested loop

For each outer row, run the inner scan once. It is cheap for few outer rows with an index on the inner key.

#### Hash join

Load one input into a hash table in memory, then probe it with each row of the other. It reads each input once.

#### Merge join

Walk two inputs side by side, both sorted on the join key by an index or a Sort node.

The planner prices every method and keeps the cheapest. The sizes of `order_events` are an example: 30,000,000 rows in 150,000 pages.

1. Nested loop at 42 rows: the scan of `orders`, 325,250, plus 42 × 8.59 per lookup, which gives 325,611.
2. Hash join at 42 rows: the same scan plus a full scan of `order_events`, about 775,250 before hashing.
3. Nested loop at the true 4,000,000 rows: 325,250 + 4,000,000 × 8.59 = 34,685,250, which is 45 times the hash join.

#### The same join, priced at any outer estimate

Outer estimate, on a log scale

Outer rows ****

Nested loop ****

Hash join ****

Cheaper by the model ****

Model arithmetic with the example sizes, not measured. Slider step 16 is about 40 rows, and 66 about 4,000,000.

A nested loop's cost grows with outer rows times the lookup, and a hash join's with the sum of its inputs. So a low outer estimate favors the nested loop. At 09:00 the nested loop was the right plan, and only the data changed since. So treat a plan regression after a bulk change as a statistics problem, and do not turn off `enable_nestloop`.

A nested loop costs outer rows times the inner lookup, so a low outer estimate makes it look cheap.

Reading only the slowest node, while the cause is the outer estimate one level below it.

<details><summary>Go deeper: the docs' three join plans, Memoize, the join search limits, the nested-loop finding, and spills to disk</summary>

#### Try this now

Run `uv run python phase04_planning/plan_lab.py --case join-methods`. For each outer size, check that the planner's row matches the cheapest forced row, and note where the method changes.

#### The arithmetic and the signature, in more detail

A nested loop costs the outer scan plus the outer rows times one inner lookup. A hash join spills to disk when its table outgrows `work_mem` × `hash_mem_multiplier`. The planner estimates the join's output first, then prices every method for every join order it considers. The 42 lookups add 42 × 8.59 = 361. The hash join's full scan of `order_events` is 150,000 + 30,000,000 × 0.01 = 450,000, so at 42 rows the nested loop is cheaper by about 450,000. The hash join's cost barely moves at 4,000,000 rows, because it reads `order_events` once either way. Nothing in the query or the indexes changed between 09:00 and 11:00. A plan is a function of the statistics.

In `EXPLAIN (ANALYZE, BUFFERS)`, the signature takes four steps to see:

1. Find the join node and its outer input, the first child.
2. Compare the outer input's expected rows with its actual rows.
3. Multiply the inner node's actual rows by its loops. Inner loops far above the outer estimate are the signature of this failure.
4. For a hash join, read `Batches` on the Hash node. More than 1 means the hash table did not fit in memory and used disk.

Then fix the estimate. The `enable_*` settings are for comparing plans, not for the application.

#### Three plans from the docs, worked

The PostgreSQL 14 docs join `tenk1` to `tenk2`, two tables of 10,000 rows, on `unique2`. Both have an index on `unique2`. Try them before you read the answers:

1. `unique1 < 10`, which keeps 10 rows of `tenk1`: Nested Loop, `cost=4.65..118.62`. The cost is the outer scan, plus one repetition of the inner scan for each outer row, plus a little CPU time for join processing. So 39.47 + 10 × 7.91 = 118.57, and the CPU time makes 118.62.
2. `unique1 < 100`, which keeps 100 rows: Hash Join, `cost=230.47..713.98`. The 100 outer rows go into the hash table, and a sequential scan of `tenk2` probes it.
3. The same `unique1 < 100`, joined to `onek`, a table of 1,000 rows: Merge Join, `cost=198.11..268.19`. `tenk1` arrives in key order from an index scan, and `onek` is sorted. With `enable_sort = off`, both sides use index scans, and the planner thinks that is about 12% more expensive.

#### A cache inside nested loops: Memoize, new in PostgreSQL 14

A nested loop runs its inner scan once per outer row, even when many outer rows carry the same key. A Memoize node keeps the inner scan's rows for each key it has already seen, and `enable_memoize` turns it off. One PostgreSQL 14 example runs a nested loop over 113 flights that looks up each flight's aircraft, and all 113 have the same aircraft type:

```
->  Memoize (actual rows=1 loops=113)
      Cache Key: f.aircraft_code
      Cache Mode: logical
      Hits: 112  Misses: 1  Evictions: 0  Overflows: 0  Memory Usage: 1kB
```

One miss read the row, and the 112 hits came from the cache. The cache is a hash table, and it counts against `work_mem`. Large `Evictions` numbers mean the cache was too small, and a wrong estimate of the distinct keys can cause that. In the opening case each order is its own key, so a Memoize over `order_events` would miss on every row. That is inferred.

#### How far the join search goes

The search builds larger joins from smaller ones by dynamic programming, the bottom-up method of IBM's System R optimizer. Three settings limit the search, and two more set the memory of sorts and hashes:

| Setting | Default | What it does |
|---|---|---|
| `from_collapse_limit` | 8 | subqueries are merged into the upper query up to this many FROM items |
| `join_collapse_limit` | the same as `from_collapse_limit`, 8 | explicit JOINs are reordered up to this many items. 1 keeps the written order |
| `geqo_threshold` | 12 | at this many FROM items, a genetic search replaces the exhaustive one |
| `work_mem` | 4MB | memory per sort or hash before it spills to temporary files |
| `hash_mem_multiplier` | 1.0 in PostgreSQL 14 | a hash table gets work_mem x 1.0. PostgreSQL 15 raised the default to 2.0 |

#### Where the worst plans came from

The same 113-query measurement on PostgreSQL 9.4 traced its worst plans to this mistake. Its timeouts came from nested-loop joins without an index lookup, which a very low estimate had picked. With those joins disabled and the hash-table resizing of 9.5 added, fewer than 4% of the queries were more than 2 times slower than with true row counts. PostgreSQL 14 has that resizing, so the result likely looks different there. That was inferred and not measured. `plan_lab.py --case join-methods` uses the `enable_*` settings the way they are meant: it prices one join with each method forced, at three outer sizes.

#### When a sort or a hash does not fit in work_mem

A sort may use `work_mem`, and a hash table `work_mem` × `hash_mem_multiplier`. Beyond its limit, the operation writes temporary files. One query can run several such operations, and several sessions can run them at once, so the total memory can be many times `work_mem`. A plan shows a spill in four lines, from PostgreSQL 14 examples:

```
Sort Method: external merge  Disk: 17136kB
Buckets: 65536  Batches: 64  Memory Usage: 2277kB
Buffers: shared hit=7236 read=6211, temp written=10858
Batches: 5  Memory Usage: 4145kB  Disk Usage: 98184kB
```

- The first line is a Sort that spilled. `external merge` wrote sorted runs to disk and merged them. A sort in memory prints `quicksort` and `Memory` instead.
- The second and third lines are one Hash node. `Batches: 64` means the input was split into 64 parts, and all but the first part went to temporary files. The Hash line does not show this disk use, and the `temp written` count of BUFFERS does.
- The fourth line is a HashAggregate that spilled. HashAggregate can spill since PostgreSQL 13. Before that, a chosen hash table was kept in memory however large it got. So on PostgreSQL 12, a low estimate of the groups could use memory without a limit, which is inferred from the release note.

Across the server, `temp_files` and `temp_bytes` in `pg_stat_database` count every temporary file. `log_temp_files`, −1 by default, logs each one when it is deleted. So raise `work_mem` for the one report that needs it, with `SET work_mem = '64MB'` in its session. A raise for the whole server is multiplied by every concurrent sort and hash. The algorithms behind these lines are external merge sort, and hash joins that partition an input that does not fit. Try it with `explain_tools.py --set work_mem=64kB`, as E15 does.

</details>

<details><summary>Evidence</summary>

The three plans and the nested-loop cost sentence are from the PostgreSQL 14 docs, section 14.1.1. The join size rule, "the join relation size is estimated before any particular join plan has been considered", is from section 72.1. Batches and disk use are from section 14.1.2. Memoize is from the PostgreSQL 14 release notes and Rogov, "PostgreSQL 14 Internals", page 361, and its memory from section 20.4. The search limits are from section 20.7, the memory settings from section 20.4, and the 2.0 default from the 15 release notes. System R's method is taught in CMU 15-445, lecture 15 notes, section 11. The nested-loop finding is from Leis and others, PVLDB 2015, section 4.1 and Figure 6. The spill lines are from Rogov, pages 374, 386 and 393. HashAggregate spilling is from the 13 release notes. `temp_files` and `log_temp_files` are from sections 20.8 and 28.2. External merge sort and the partitioned hash join are in CMU 15-445 lecture notes 11 and 12.

</details>

## What does VACUUM remove, and what stops it?

In Phase 3 you saw that an UPDATE writes a new row version and keeps the old one. A *snapshot*, from Phase 3, records which transactions had finished when a statement began. A *dead version* is one no snapshot can still see. VACUUM removes dead versions and marks their space free for new rows. It keeps that space in the file, and the extra space is called *bloat*. A version is removable only when it died before the oldest snapshot any open transaction holds, the *cleanup horizon*.

| One order's versions | No old snapshot | A report began at 10:30 and is still open |
|---|---|---|
| v1 status=created, replaced at 10:05 | removed | removed: it died before the report began |
| v2 status=pending, replaced at 11:00 | removed | kept: the report's snapshot may still read it |
| v3 status=paid, live | kept | kept |

<details><summary>Predict: each night a job deletes 1,000,000 old orders, the day inserts 1,000,000, and VACUUM runs. Why is the file larger every morning?</summary>

Something holds the cleanup horizon in the past, such as a session left idle in a transaction. VACUUM runs and reports success, but it removes nothing that died after that snapshot.

</details>

Four causes are common.

- A long report, or a session left `idle in transaction`, keeps an old snapshot open.
- A replication slot whose reader is gone holds the horizon through its `xmin`.
- A prepared transaction of a two-phase commit that was never finished holds it too.
- Deletes and inserts faster than VACUUM extend the file before the space is freed.

Autovacuum starts on `orders` after 50 + 0.2 × `reltuples` = 2,000,050 dead rows, and then a budget sets its speed.

1. A worker spends 200 cost units, then naps 2 ms. A cached page costs 1, a page read costs 2, and a page it dirties costs 20 more.
2. The 200 units are shared by all running workers, so 3 workers get about 66 each.
3. When every page is read and dirtied, 9 pages fit in one nap. That is 35.5 MB/s for all workers together.

#### The autovacuum budget, every page read and dirtied

Cost limit Workers Heap size in GB

Units per worker ****

Ceiling for all workers ****

One pass over the heap, at least ****

Arithmetic from the PostgreSQL 14 defaults, not run. It counts only the naps, and the indexes come on top.

So one pass over a 500 GB heap takes at least 4 hours, whatever the worker count. Give the large table its own `autovacuum_vacuum_cost_limit`, which also takes it out of the sharing.

<details><summary>Go deeper: the settings, the throttle rules, the vacuum log line and views, slots, shrinking a file, index bloat, and the bloat lab</summary>

#### The core, in more detail

VACUUM finds dead versions, removes them from the table and from every index, and marks their space free. The one exception to keeping the space is empty pages at the end of the table, which it can return. So VACUUM stops growth and does not shrink a file. Bloat is the dead versions plus the free space that the table holds and does not use. One old snapshot holds the horizon back for every table in the database.

The incident left 4,000,000 dead versions, and the file grew. The pages were full, so most new versions went to new pages. The 2,000,050 trigger was passed. A clean page that vacuum dirties costs `vacuum_cost_page_dirty`, 20 more, so a page read and dirtied costs 22. That gives 9 pages per nap, about 4,545 pages a second. Six workers get about 33 units each, for the same total. Also lower the large table's `autovacuum_vacuum_scale_factor`, so each run has less to do.

The first three causes show up in one query each: `age(backend_xmin)` in `pg_stat_activity`, `age(xmin)` and `age(catalog_xmin)` in `pg_replication_slots`, and `age(transaction)` in `pg_prepared_xacts`. `bloat.py --xid` prints all three. To shrink a file, `VACUUM FULL` writes a new copy, but it holds `ACCESS EXCLUSIVE` for the whole rewrite, so every read and write waits.

#### Autovacuum's settings in PostgreSQL 14

The 50 and the 0.2 are `autovacuum_vacuum_threshold` and `autovacuum_vacuum_scale_factor`. Inserts have their own trigger in PostgreSQL 14, with a threshold of 1,000 and the same 0.2. Other defaults:

| Setting | Default in 14 | What it means |
|---|---|---|
| `autovacuum_naptime` | 1min | one worker start per database per minute |
| `autovacuum_max_workers` | 3 | at most three tables vacuumed at once. In 14 it changes only at server start |
| `autovacuum_work_mem` | −1, so `maintenance_work_mem`, 64MB | memory for the list of dead rows. Up to PostgreSQL 16, vacuum used at most 1GB of it. PostgreSQL 17 removed that limit |

On a very large table the 0.2 is a long wait. A table of 1,000,000,000 rows waits for 200,000,050 dead rows. PostgreSQL 18 adds `autovacuum_vacuum_max_threshold` as a cap on that sum, with a default of 100,000,000.

#### The throttle in numbers

`vacuum_cost_page_miss` is 2 since PostgreSQL 14 lowered it. The budget is `autovacuum_vacuum_cost_limit`, −1 by default, so it uses `vacuum_cost_limit`, 200. The nap is `autovacuum_vacuum_cost_delay`, 2 ms since PostgreSQL 12. A delay without its limit says nothing, because the limit sets how much work happens between two naps.

```
The autovacuum budget at PostgreSQL 14 defaults. Arithmetic, not run
200 units, then a 2 ms nap. Shared by every running worker

every page is   cost  pages per nap   ceiling for all workers together
cached             1          200     100,000 pages/s    781.3 MB/s
read               2          100      50,000 pages/s    390.6 MB/s
read + dirtied    22            9       4,545 pages/s     35.5 MB/s

3 workers: about 66 units each. 6 workers: about 33 each. Same ceiling
a table with its own cost_limit 1000 leaves the sharing: 5x the ceiling
```

The 500 GB example is 512,000 MB / 35.5 MB/s, about 14,400 seconds, or 4 hours. Four rules follow:

1. **Raising `autovacuum_max_workers` alone does not speed vacuum up.** More workers split the same budget, so raise the workers and the cost limit in proportion.
2. **Tune the large table, not the server.** A table's own storage parameters override the server's, and a table with its own cost setting is left out of the sharing. Each storage parameter below takes only SHARE UPDATE EXCLUSIVE.
3. **A manual VACUUM is not throttled by default.** `vacuum_cost_delay` is 0 by default, which disables the cost-based delay.
4. **A running autovacuum keeps its settings in 14.** Before PostgreSQL 16, autovacuum read changed delay settings only at the start of each table. So a reload does not speed up the table that is being vacuumed now.

```
-- For one large, busy table. Values are an example.
ALTER TABLE orders SET (
  autovacuum_vacuum_scale_factor = 0.01,  -- 50 + 0.01 x 10,000,000 = 100,050 dead rows
  autovacuum_vacuum_cost_limit   = 1000   -- 5 times the budget, for this table only
);
```

#### What vacuum tells you: one log line and three views

By default, PostgreSQL 14's autovacuum writes nothing to the log, because `log_autovacuum_min_duration` is −1. PostgreSQL 15 changed the default to 10 minutes. On 14, set it to `'10s'` or lower, and each longer run writes one entry. These are its format strings in the order they print, with a `%` field where each number goes:

```
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

The `index "%s"` line repeats once for each index. The fourth line can also start `index scan not needed:` or `index scan bypassed:`. An `I/O timings:` line comes before the read rates when `track_io_timing` is on. Three fields answer the questions of this section:

- **`are dead but not yet removable, oldest xmin: N`** is the held cleanup horizon, in one line. A large count with an old `oldest xmin` points at the four causes above.
- **`index scans: N`** above 1 means the list of dead rows did not fit in memory. Each dead row takes a 6-byte TID in that list, the row address from Phase 2. So 64MB holds about 64 × 1,048,576 / 6 = 11.18 million dead rows per pass, and every extra pass reads every index again. One PostgreSQL 14 run shows `index scans: 3` for 500,000 dead rows with `maintenance_work_mem` set to 1MB.
- **The first line names the kind of run.** It prints `automatic aggressive vacuum` for a freezing scan, and adds `to prevent wraparound` for the forced run of the next section.

| View | What to read |
|---|---|
| `pg_stat_progress_vacuum` | one row per running VACUUM: `phase`, `heap_blks_scanned` of `heap_blks_total`, `index_vacuum_count`, and `num_dead_tuples` of `max_dead_tuples` |
| `pg_stat_user_tables` | per table: `n_dead_tup`, `n_mod_since_analyze`, `n_ins_since_vacuum`, `last_autovacuum` and `autovacuum_count` |
| `pg_stat_activity` | an autovacuum's `query`, such as `autovacuum: VACUUM public.orders`, and `wait_event = VacuumDelay` while it naps |

Many workers in `VacuumDelay` mean the budget limits vacuum, not the disk. That reading is inferred. `bloat.py --vacuum-signals` prints all of these for the lab's tables.

#### The four causes, in more detail

- Phase 3 gave the setting that ends idle sessions, `idle_in_transaction_session_timeout`, which is off by default.
- Drop old replication slots before a wraparound VACUUM. A physical slot gets an `xmin` only from a standby that has `hot_standby_feedback = on`, which is off by default. A logical slot sets `catalog_xmin` instead, which holds back only catalog tuples. The more common harm of an abandoned slot is WAL. `max_slot_wal_keep_size` is −1 by default, so a slot may keep an unlimited amount of WAL files. The link between feedback and a physical slot's `xmin` is inferred. Replication itself is course 5.
- The fourth cause is inferred from how VACUUM frees space. Its free space lets later inserts reuse old pages, but only once it has run.

#### Shrinking a file

`VACUUM FULL`, `CLUSTER` and the table-rewriting forms of `ALTER TABLE` write a new copy without dead space. They all take an ACCESS EXCLUSIVE lock, and they use extra disk about equal to the size of the table until they finish. For a table that will grow again, moderately frequent standard VACUUMs are the better choice. For a table emptied on a schedule, `TRUNCATE` frees the space at once, and the price is that strict MVCC rules are broken for it.

#### Index bloat, and rebuilding without blocking writes

A B-tree also keeps the space of dead entries. Two releases lowered it. PostgreSQL 13 stores duplicate keys once, and PostgreSQL 14 removes expired entries to prevent page splits. A low-cardinality index such as the one on `status` gains the most, which is inferred. When a table or an index must still be rebuilt, four tools exist:

| Tool | What it does | Lock and cost |
|---|---|---|
| `pgstattuple`, `pgstattuple_approx` | measure dead rows and free space | `pgstattuple` always performs a full-table scan. `pgstattuple_approx` skips pages that the visibility map marks all-visible |
| `REINDEX INDEX CONCURRENTLY`, PostgreSQL 12 and later | builds a new index beside the old one, then swaps them | takes no locks that prevent concurrent inserts, updates or deletes. Two scans, a wait for older transactions, and no transaction block. Only `REINDEX INDEX` can rebuild an invalid index concurrently |
| `pg_repack`, an extension outside core | rewrites a table and its indexes while traffic runs | needs a primary key, or a unique index on NOT NULL columns, and free disk about twice the table and its indexes. It takes one exclusive lock at the beginning and one at the end |
| `VACUUM FULL`, `CLUSTER` | rewrite the table in core | ACCESS EXCLUSIVE for the whole rewrite |

A failed `REINDEX CONCURRENTLY` leaves an invalid index whose name ends in `_ccnew`. Drop it and run the command again. Two ideas from Phase 2 reduce the garbage itself. A HOT update adds no index entries, and it needs free space on the row's page. A table's `fillfactor` below 100 leaves that free space on each page. An index on `status` makes every status change a non-HOT update.

#### The bloat lab

`bloat.py` makes the growth visible on 100,000 rows with autovacuum off for its table. Expected, worked out from the rules above, not measured:

```
bloat.py, heap pages. 1 char = one table's worth of pages. Not run
after load                  █          1x
UPDATE every row            ██         about 2x: the pages were full
VACUUM                      ██         2x: space freed, file unchanged
UPDATE again                ██         2x: the new versions reuse it
H holds a snapshot, then
  UPDATE + VACUUM           ███        about 3x. VACUUM still frees the
                                       versions that died before H
  UPDATE + VACUUM           ███        about 3x: reuses that space. Now
                                       nothing is removable
H commits, VACUUM, UPDATE   ███        3x: reused, still not returned
VACUUM FULL                 █          about 1x. A SELECT waits for it
```

</details>

<details><summary>Evidence</summary>

The space rule, "will not return the space to the operating system", is from the PostgreSQL 14 docs, section 25.1.2, which also give the rewrite locks, the extra disk and the TRUNCATE warning that "strict MVCC semantics are violated". The thresholds are from sections 20.10 and 25.1.6. The cost settings are from sections 20.4.4 and 20.10, which say the limit "is distributed proportionally among the running autovacuum workers", and from `vacuum.c` REL_14_24, lines 2221 to 2231. The table override and the sharing exception are at `autovacuum.c` REL_14_24, lines 3003 to 3009. The nine pages per nap and the advice to raise workers and limit "proportionally" are from Rogov, "PostgreSQL 14 Internals", page 118. The 2 ms default is from the 12 release notes, the per-table rule before 16 from the 16 release notes, the 1GB limit from the 17 release notes, and the cap from the PostgreSQL 18 docs, section 19.10.1. The log format is `vacuumlazy.c` REL_14_24, lines 773 to 861, and the 6-byte TID is at lines 193 and 194. Rogov page 122 prints a whole entry and the `index scans: 3` run. The views are from sections 28.2 and 28.4, and the activity text from `autovacuum.c`, lines 3314 to 3329. The growth causes are from section 25.1.5, and the slot facts from the `pg_replication_slots` page and section 20.6. The index tools are from the REINDEX page, the 12, 13 and 14 release notes, section F.31 and the pg_repack documentation.

</details>

## How does transaction ID wraparound stop a database?

VACUUM has a second job. A transaction ID is 32 bits, so for every ID, two billion IDs count as older and two billion as newer. A row whose ID fell more than two billion behind would look as if it came from the future, so it would become invisible. VACUUM prevents this by *freezing* old rows, which marks them as older than every normal ID. PostgreSQL 14 enforces it with fixed limits on `age(datfrozenxid)`, the age of a database's oldest unfrozen ID.

#### age(datfrozenxid) in PostgreSQL 14, up to wraparound

- normal: 0 to 200 M, no forced vacuum yet
- forced vacuum: 200 M to 1.6 B, from autovacuum_freeze_max_age, a forced vacuum runs, even with autovacuum off
- failsafe: 1.6 B to 2,107 M, from vacuum_failsafe_age, new in 14, vacuum stops its cost naps and skips index vacuuming
- warning: 2,107 M to 2,144 M, 40 million before wraparound, every session sees WARNING: must be vacuumed within N transactions
- stopped: last 3 M, new IDs are refused, so no write can start
So a database at an age of 1,900,000,000 can assign 244,483,647 more IDs before it stops. At an example 1,000 write transactions per second, that is 2.4 days to the warning and 2.8 days to the stop.

The forced vacuum also refuses to give way. A normal autovacuum is cancelled when a conflicting lock request has waited 1 s. A vacuum `(to prevent wraparound)` is not, and it can run for hours under the throttle. At Joyent's Manta service, a `DROP TRIGGER` waited behind such a vacuum. Every query on the table then waited behind the `DROP TRIGGER`, by the soft block from Phase 3. About 22% of all requests failed, near 27% at the peak, for about ten hours.

So alert on the age, not on the error. The WARNING comes only 37 million IDs before the stop, about 3.4 hours at 3,000 IDs a second. A large VACUUM can take longer.

<details><summary>Go deeper: the freeze settings, aggressive scans, multixacts, how the cancel works, the full Joyent timeline, the wrong hint, and two more outages</summary>

#### The core, in more detail

IDs are compared modulo 2^32. So every table in every database must be vacuumed at least once every two billion transactions. The wraparound point is 2,147,483,647 IDs past the oldest unfrozen ID, and the stop is at an age of 2,147,483,647 − 3,000,000 = 2,144,483,647. The warning starts at an age of 2,107,483,647. From an age of 1,900,000,000, the warning is 207,483,647 IDs away, which is 207,484 seconds at 1,000 per second. Read-only transactions get no ID and do not count.

A normal autovacuum gives way when a conflicting lock request has waited for `deadlock_timeout`, 1 s, because the waiter cancels it. The wraparound vacuum's query in `pg_stat_activity` ends with `(to prevent wraparound)`, and it holds `SHARE UPDATE EXCLUSIVE` for its whole run. At Joyent, the `DROP TRIGGER` takes `ACCESS EXCLUSIVE`, and the outage ran from about 10:30 to 20:45 UTC. The vacuum did not block the queries, because its lock does not conflict with them. The waiting `DROP TRIGGER` did.

Compare `age(datfrozenxid)` with `autovacuum_freeze_max_age`. If a database stops, follow the docs' steps in order: resolve old prepared transactions, end long open transactions, drop old replication slots, then run VACUUM in that database.

#### The limits in the code

The warning starts at the wrap limit minus 40,000,000, and the stop at minus 3,000,000. PostgreSQL 13 used 11,000,000 and 1,000,000. The 200 million default for `autovacuum_freeze_max_age` has a reason. It translates to about 50MB of `pg_xact` storage, because the commit status takes two bits per transaction.

#### Why a quiet table suddenly gets a full scan

VACUUM freezes a row once its inserting transaction is older than `vacuum_freeze_min_age`, 50 million. A normal VACUUM skips pages that hold no dead rows, so it can leave old rows unfrozen. When the age of a table's `relfrozenxid` reaches `vacuum_freeze_table_age`, 150 million, VACUUM turns aggressive. The visibility map keeps a second bit per page, besides all-visible. This all-frozen bit marks a page whose rows are all frozen, and the `pg_visibility` extension shows both bits. An aggressive scan reads every page that is not marked all-frozen. So a large table that only receives inserts can one day get a scan of every unfrozen page, although nothing in it changed. That is inferred from the two rules. The log line's word `aggressive` names such a run.

#### Multixacts need freezing too

Phase 3 showed the case. A row locked by several transactions at once stores a multixact ID in its `xmax`, and a foreign-key check is the usual cause. Multixact IDs are also a 32-bit counter, so they wrap in the same way. The same settings exist with `multixact` in their names. `vacuum_multixact_freeze_min_age` is 5 million, `vacuum_multixact_freeze_table_age` is 150 million, and `autovacuum_multixact_freeze_max_age` is 400 million. Watch `mxid_age(datminmxid)` in `pg_database` beside `age(datfrozenxid)`. One difference changes the recovery steps: replication slots do not directly hold back multixact cleanup. So for a multixact problem, look at old transactions and prepared transactions first. `bloat.py --xid` prints both ages.

#### How the cancel works, and what skips it

A conflicting lock request interrupts a normal autovacuum. The waiting process runs its deadlock check after `deadlock_timeout`. If an autovacuum blocks it, it sends the worker SIGINT, and the worker logs `canceling autovacuum task`. The code skips the signal when the worker vacuums to prevent wraparound. Two results follow:

- A table that receives DDL often may never finish a normal autovacuum, because each DDL statement cancels it. That is inferred from the rule.
- The forced vacuum holds SHARE UPDATE EXCLUSIVE for its whole run, which can take hours on a large table under the throttle.

#### The Joyent timeline

The postmortem does not name the PostgreSQL version. Only the times shown come from the post:

1. **10:30:09** An autovacuum "to prevent wraparound" starts on one metadata shard. It holds SHARE UPDATE EXCLUSIVE on the table. A component reconnects and runs DROP TRIGGER, which waits behind the autovacuum, and every data-path query waits behind DROP TRIGGER.
2. **10:30** About 22% of all requests fail, near 27% at the peak.
3. **14:11** PostgreSQL is restarted. Service returns for 5 to 10 minutes, then a new wraparound autovacuum starts and the same queue forms.
4. **hours** The vacuum scans the table and all its indexes, twice. The team patches the process to skip the cost-based sleeps. It ends, and a few minutes later another one starts.
5. **20:45** The error rate is back to zero.

Three lessons, in order:

1. **The vacuum did not block the queries.** The post says the autovacuum itself was not blocking all the data-path queries. In PostgreSQL 14, DROP TRIGGER takes ACCESS EXCLUSIVE. This is the soft block of the lock queue, which the migrations section measures.
2. **The fix is the migrations rule.** Give every DDL statement a `lock_timeout`, so it leaves the queue and retries. Joyent ended the outage by making its wraparound settings less aggressive. Its lasting fix was to stop dropping and recreating the trigger.
3. **Check before a migration.** Look in `pg_stat_activity` for a query that ends in `(to prevent wraparound)` on the table. `locks.py --scenario wraparound` replays the sequence offline.

#### What the error says, and a disagreement

At the stop limit, PostgreSQL 14 prints `ERROR: database is not accepting commands to avoid wraparound data loss in database "mydb"`. Its hint says to stop the postmaster and vacuum in single-user mode. The PostgreSQL 14 docs page was updated later and says the opposite: it is not necessary or desirable to stop the postmaster or enter single-user mode. The docs' four steps are the ones above, and the last is a plain VACUUM, not VACUUM FULL and not VACUUM FREEZE. Follow the docs, not the hint. PostgreSQL 17 changed both the message and the hint, and 18 keeps the new text.

#### Two more outages

Both are first-party reports. Neither names its PostgreSQL version, which this course did not check:

- **Sentry.** Sentry was down for most of a US working day. Its post blames too high an `autovacuum_freeze_max_age` with the default of 3 workers. After hours of vacuum, the team truncated one large table and recovered within minutes. The post gives the stop margin as one million transactions, which matches PostgreSQL 13's limit, not 14's. Its new settings read as the throttle lesson. `autovacuum_vacuum_cost_delay = 0` turns the throttle off, and `autovacuum_max_workers = 6` with `autovacuum_naptime = '15s'` adds workers. The post's own correction says `maintenance_work_mem = '10GB'` met a 1GB internal limit, which PostgreSQL 17 removed. It also set `autovacuum_freeze_max_age = 500000000` and `vacuum_freeze_min_age = 10000000`.
- **Mandrill, by Mailchimp.** The outage ran from 05:35 UTC on February 4 to 22:09 UTC on February 5, about 40.5 hours. In the November before it, engineers had seen the transaction IDs climb to about half the limit at peak load. Their highest estimate for the vacuum was 40 days.

#### The alert arithmetic

The limits are 40 million and 3 million before wraparound, so the WARNING starts 37 million IDs before the stop. At 3,000 IDs per second, 37,000,000 / 3,000 = 12,333 seconds, about 3.4 hours. Use the age query of the docs' wraparound section. `bloat.py --xid` prints the distance to every limit.

</details>

<details><summary>Evidence</summary>

The two-billion rule and "it is necessary to vacuum every table in every database at least once every two billion transactions" are from the PostgreSQL 14 docs, section 25.1.5, with the updated recovery steps. The limits are from `varsup.c` at REL_14_0, lines 362, 378 and 392, and the error and hint at lines 129 and 131. The settings are from sections 20.10 and 20.11, and the change from `varsup.c` at REL_17_0 and REL_18_0, lines 156 and 158. REL_16_0 still has the old text at lines 129 and 131. The interruption rule is from section 25.1.6. The cancel path is in `proc.c` REL_14_24, lines 1433, 1460 and 1489, and the log line at `postgres.c` line 3314. DROP TRIGGER's lock is at `trigger.c` REL_14_24, line 1280. Freezing and the all-frozen bit are from sections 20.11 and 25.1.5 and Rogov, page 126. Multixacts are from sections 20.10, 20.11 and 25.1.5.1. The Joyent sequence is from its postmortem of 2015-07-27, archived copy, which says "the autovacuum itself wasn't blocking all the data path queries". Sentry's post is of 2015-07-23, and the settings were checked in its saved text. The Mandrill post is by Eric Muntz, dated 2019-03-26.

</details>

## When does partitioning remove the cleanup, and what does it cost the plans?

A nightly DELETE of old events creates dead versions every night. A *partitioned table* is a parent with no rows of its own. Each row goes to the partition whose bounds hold its *partition key*, here the month of `created_at`. *Partition pruning* skips partitions whose bounds cannot match the query. It uses only conditions on the key, never the indexes.

```
order_events, partitioned by month on created_at, 12 partitions
WHERE created_at in March         Jan  Feb [Mar] Apr ... Dec
                                  1 partition read: pruned at plan time
WHERE order_id = 123             [Jan][Feb][Mar][Apr]...[Dec]
                                  12 index lookups: no key, no pruning
EXECUTE with $1 = March, generic [Mar]   Subplans Removed: 11
                                  pruned at executor start
```

1. A query on March reads 1 of 12 partitions, pruned at plan time.
2. A query on `order_id = 123` makes 12 index lookups instead of one, because it does not name the key. The report joins on `order_id`, so it touches every partition.
3. A generic plan prunes at executor start, and EXPLAIN prints `Subplans Removed: 11`.
4. Dropping a month's partition leaves no dead versions, where a DELETE of that month leaves 2,500,000 for VACUUM.

The price is planning time, which grows with the partitions left after pruning. So partition when the hot queries name the key and old data leaves by whole months. Remove a month with `DETACH PARTITION ... CONCURRENTLY` first, because `DROP TABLE` on an attached month locks the parent with `ACCESS EXCLUSIVE`.

VACUUM frees only what died before the oldest open snapshot, and does not give space back.

Tuning VACUUM settings while one open transaction, slot or prepared transaction holds the horizon back.

<details><summary>Go deeper: when the pruning happens, the benefits and costs in full, the locks of partition maintenance, and a key nobody queries</summary>

#### Try this now

Run `uv run python phase04_planning/bloat.py --xid`. Find your oldest database age, and compute the transactions left before the forced autovacuum.

#### The core, in more detail

The example is `order_events` partitioned by month, with 30,000,000 rows and an index on `order_id` in every partition. The report touches every partition unless it also filters on `created_at`. A generic plan cannot prune at planning time, because it does not know `$1`. A DELETE of one month leaves 30,000,000 / 12 = 2,500,000 dead versions. Planning memory grows with the partitions too, and autovacuum never runs ANALYZE on the parent. A primary key on the parent must include the partition key columns, and `CREATE INDEX CONCURRENTLY` does not work on the parent. While the month is attached, its `DROP TABLE` makes every query on `order_events` wait. After the detach, drop the detached table.

#### Three moments of pruning

1. **At plan time,** when the values are constants in the query.
2. **At executor start,** for parameter values known then, such as those of a generic plan from the sixth execution of a prepared statement. These partitions vanish from the plan, and EXPLAIN prints a `Subplans Removed` line. The partitions removed at this stage are still locked at the beginning of execution.
3. **During execution,** for values that change while the query runs, such as the inner side of a nested loop. Then EXPLAIN ANALYZE shows the pruned partitions with fewer loops, or as `(never executed)`.

A unique or primary key on a partitioned table must include all of the partition key columns, because each partition's index can only enforce uniqueness inside that partition. So `PRIMARY KEY (id)` is refused, and `PRIMARY KEY (id, created_at)` is allowed.

#### When it helps

- The heavily used rows sit in one or a few partitions. Partitioning then takes the place of the upper tree levels of indexes, so the hot parts of the indexes are more likely to fit in memory.
- A query that reads most of one partition can scan that partition in sequence. It avoids random index reads across the whole table.
- Bulk loads and deletes become adding or removing a partition. Dropping a partition avoids the VACUUM work that a bulk DELETE causes.

The benefits are worth it when the table would otherwise be very large, larger than the server's memory. For the order events, removing a month is the main gain.

#### When it hurts the planner, in full

1. **Queries without the key read every partition,** as the `order_id` case showed.
2. **Planning time and memory grow with the partitions that remain after pruning.** The planner handles up to a few thousand partitions fairly well, if typical queries prune all but a few. Each partition a session touches also loads its metadata into that session's memory. The older inheritance method works with up to perhaps a hundred child tables.
3. **Statistics of the parent.** The partitions get their own statistics. A query planned against the whole parent needs a manual ANALYZE of the parent.
4. **Uniqueness only with the key,** as above.
5. **No concurrent index build on the parent.** Concurrent builds for indexes on partitioned tables are not supported, in PostgreSQL 14 and 18. The workaround is `CREATE INDEX ON ONLY` the parent, then `CREATE INDEX CONCURRENTLY` on each partition, then `ALTER INDEX ... ATTACH PARTITION` for each one.

#### The locks of partition maintenance

| Statement | Lock on the parent | Lock on the partition |
|---|---|---|
| `CREATE TABLE ... PARTITION OF` | ACCESS EXCLUSIVE | the new table |
| `ALTER TABLE ... ATTACH PARTITION` | SHARE UPDATE EXCLUSIVE | ACCESS EXCLUSIVE, and a scan unless a matching CHECK exists |
| `ALTER TABLE ... DETACH PARTITION` | ACCESS EXCLUSIVE | not stated in the pages read, not checked |
| `... DETACH PARTITION ... CONCURRENTLY`, new in 14 | SHARE UPDATE EXCLUSIVE, in two transactions | ACCESS EXCLUSIVE in the second |

A DEFAULT partition adds one more lock. ATTACH also takes ACCESS EXCLUSIVE on the default partition, if there is one, and scans it to check that none of its rows belong in the new partition. A CHECK constraint on the default partition that excludes the new bounds lets ATTACH skip that scan. So the routine that never blocks traffic on the parent has four steps:

1. Create next month's table on its own, and load it if needed.
2. Add a CHECK constraint that matches the month's bounds, so ATTACH can skip its scan.
3. Run `ATTACH PARTITION`, which takes only SHARE UPDATE EXCLUSIVE on the parent. Then drop the CHECK, which is redundant once the attach is complete.
4. For the oldest month, run `DETACH PARTITION ... CONCURRENTLY`, then `DROP TABLE`.

#### The failure: a partition key that queries do not use

A team gives each customer its own partition, because the largest customers are slow. Most queries filter by order id, so most plans touch every partition. Years later the customers number in the thousands, and planning time grows with them. The docs warn about this case, and suggest a fixed number of HASH partitions instead of one LIST partition per customer. Choose the key from the WHERE clauses of the hot queries. Measure planning time with the partition count you expect in three years. `partitions.py` checks each claim above on your server, and `--planning-sweep` measures the planning time at 12, 120 and 1,200 partitions.

</details>

<details><summary>Evidence</summary>

All partitioning facts are from the PostgreSQL 14 docs, section 5.11: the pruning rule, "driven only by the constraints defined implicitly by the partition keys, not by the presence of indexes", and the three moments, from 5.11.4. The benefits and the rule of thumb are from 5.11.1, the key rule from 5.11.2.3, the planning limits from 5.11.6 and the inheritance limit from 5.11.5. That autovacuum does not analyze partitioned tables is from section 25.1.3. The concurrent build limit is from the CREATE INDEX docs of 14 and 18, and its workaround and the locks of ATTACH and DETACH from 5.11.2.2 and the ALTER TABLE page. That DROP TABLE of an attached partition takes ACCESS EXCLUSIVE on the parent is also from 5.11.2.2.

</details>

## Why does an instant ALTER stop every SELECT?

Every statement takes one of eight table lock modes, and two modes either conflict or do not. A schema change can block the table during two periods. One is the time it holds its lock to do its work. The other is the time it waits, because a waiting request blocks later ones.

| Requested \ held | ACCESS SHARE | ROW EXCLUSIVE | SHARE UPDATE EXCL | SHARE | ACCESS EXCLUSIVE |
|---|---|---|---|---|---|
| ACCESS SHARE, a SELECT | ok | ok | ok | ok | waits |
| ROW EXCLUSIVE, a write | ok | ok | ok | waits | waits |
| SHARE UPDATE EXCL, VACUUM or CREATE INDEX CONCURRENTLY | ok | ok | waits | waits | waits |
| SHARE, CREATE INDEX | ok | waits | waits | ok | waits |
| ACCESS EXCLUSIVE, most ALTER TABLE | waits | waits | waits | waits | waits |

Five of the eight modes. The full table is in Go deeper.

<details><summary>Predict: session A opened a transaction, read p4_tasks, and is still open. You run ALTER TABLE p4_tasks ADD COLUMN queue text, a change to the catalog only. One second later a plain SELECT on p4_tasks arrives. What happens to it?</summary>

The SELECT waits behind the ALTER for as long as A stays open, although A and the SELECT do not conflict and the ALTER needs milliseconds.

</details>

The lock manager grants a request only if it conflicts with nothing granted and nothing already waiting, in order of arrival. The course research ran the predict case on PostgreSQL 14.24.

#### The lock queue, three sessions, one step per second

- A: reader: BEGIN, SELECT | open | open | open | open | open | commits
- B: ALTER:  | ACCESS EXCLUSIVE waiting | waiting | waiting | waiting | waiting | adds the column, commits
- C: SELECT:  |  | blocked by B, not A | blocked | blocked | blocked | runs
t = 0 s: A reads the table and holds ACCESS SHARE.

t = 1 s: B asks for ACCESS EXCLUSIVE, which conflicts with A, so B waits.

t = 2 s: C does not conflict with A, but it conflicts with B, which is waiting, so C waits too.

t = 6 s: A commits. B gets its lock, adds the column in milliseconds and commits, then C runs.

Times from the course research's run on PostgreSQL 14.24. C took 4.04 s for a one-row SELECT, and B took 5.03 s.

So the table is down while the longest open transaction lasts. With `SET lock_timeout = '100ms'` on B, B failed after 0.18 s. C started at t = 2 s, after B had left the queue, and took 0.07 s. A statement that gives up leaves the queue. The migration then retries on SQLSTATE 55P03 after a random pause.

The opening case's `CREATE INDEX` took `SHARE`, which conflicts with the `ROW EXCLUSIVE` of every write. So writes waited 11 minutes, and SELECTs went on. `CREATE INDEX CONCURRENTLY` takes `SHARE UPDATE EXCLUSIVE` and blocks no reads or writes.

<details><summary>Go deeper: all eight modes, the lock of each DDL statement, the GoCardless outage, retry policies, the timeout settings, and the checks around a concurrent build</summary>

#### The core, in more detail

A schema change's work, while it holds its lock, is a catalog change, a scan or a rewrite. The waiting request blocks later ones by the soft block from Phase 3. In the three-session run, C asked for ACCESS SHARE at t = 2 s. Session A does not have to be yours, and in the Joyent outage it was a wraparound vacuum that never gives way. B's error read `canceling statement due to lock timeout`, and the requests behind it ran. The opening case's SHARE lock covers every INSERT, UPDATE and DELETE. `CREATE INDEX CONCURRENTLY` scans the table twice and waits for older transactions. If it fails, it leaves an invalid index that still costs every write, so drop it and build again.

#### All eight modes

```
Table lock conflicts, PostgreSQL 14 docs 13.3.1. X = the two conflict
requested \ held          AS   RS   RX  SUX    S  SRX    X   AX
ACCESS SHARE  SELECT       .    .    .    .    .    .    .    X
ROW SHARE  SELECT FOR UPD  .    .    .    .    .    .    X    X
ROW EXCLUSIVE  writes      .    .    .    .    X    X    X    X
SHARE UPDATE EXCL  VACUUM  .    .    .    X    X    X    X    X
SHARE  CREATE INDEX        .    .    X    X    .    X    X    X
SHARE ROW EXCL  ADD FK     .    .    X    X    X    X    X    X
EXCLUSIVE                  .    X    X    X    X    X    X    X
ACCESS EXCL  most ALTER    X    X    X    X    X    X    X    X
```

#### Which DDL takes which lock

An ACCESS EXCLUSIVE lock is taken unless the ALTER TABLE page notes otherwise. `locks.py --predict` prints the same facts for any statement:

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

The REINDEX row needs a note. The lock-mode list puts REINDEX under ACCESS EXCLUSIVE. The REINDEX page says instead that it locks out writes but not reads of the index's parent table. The code opens the table in SHARE mode and the index in ACCESS EXCLUSIVE mode.

The course outline tells the opening story as a migration that "took an exclusive lock". That is not the mode it took, because SHARE blocks writes only. An ACCESS EXCLUSIVE lock would also have stopped the reads.

One more fact from the study note belongs here. The rewriting forms of ALTER TABLE are not MVCC-safe. After a table rewrite, the table appears empty to concurrent transactions that use a snapshot taken before the rewrite. So a type change that rewrites the table during a deploy can show an empty table to an old-snapshot reader. The docs limit this to a transaction that had not read the table before the rewrite started. Section 13.5 lists only TRUNCATE and the rewriting forms of ALTER TABLE. VACUUM FULL is not on that list, because it also copies the recently dead versions. That is inferred from `heapam_handler.c` REL_14_24, line 848.

#### One real outage, and one claim corrected

GoCardless reported about 15 seconds of unexpected API downtime during a planned migration. A long `SELECT` ran on a busy parent table. Meanwhile, a migration added a foreign key `NOT VALID` from an empty child table. On a restored backup, with no traffic, the same migrations finished in a few hundred milliseconds. The post says that adding the foreign key takes ACCESS EXCLUSIVE on both tables. That was true up to PostgreSQL 9.4, the version the post discusses, and 9.5 reduced the lock levels of foreign-key commands. In PostgreSQL 14, `ADD FOREIGN KEY` requires only a SHARE ROW EXCLUSIVE lock, on both tables. The course research measured the difference on 14.24. A transaction held a write lock on the parent for 5 s, and the foreign-key addition queued behind it. A SELECT on the parent then finished in 0.18 s, and an INSERT waited 2.98 s.

#### lock_timeout and retries

`lock_timeout` stops any statement that waits longer than the given time while it tries to take a lock. It applies separately to each lock attempt. The error is SQLSTATE 55P03, `lock_not_available`. The lab's runner retries every DDL statement on that error. From `phase04_planning/migrate_lab.py:376`:

```
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

`backoff` waits a random time up to `min(cap, base × 2^attempt)`. That is capped exponential backoff with jitter, and the random part spreads retries that failed together.

#### How long to wait for a lock

| Source | `lock_timeout` | Retries |
|---|---|---|
| postgres.ai, Nikolay Samokhvalov | 50 ms | exponential backoff with jitter, 30 attempts in its example |
| GitLab, `with_lock_retries.rb` at master | 0.1 s, rising to 2 s | 615 attempts, about 44.6 minutes in the worst case |
| GoCardless, `ActiveRecord::SaferMigrations` | 750 ms | none by default, plus a 1,500 ms statement limit |
| Braintree draft by James Coleman | locks held at most about 2 seconds | not stated |
| strong_migrations, Andrew Kane | 10 s | 3, 10 s apart, marked experimental |

Each attempt can block the table's traffic for up to `lock_timeout`, so a short value keeps each pause short. A short value also fails more often on a busy table, so it needs more retries. The postgres.ai post works through one thought experiment. Its SELECTs take 0.1 ms, and its migration retries 50 ms waits with no pause between them. The average SELECT then approaches 50 ms. That is why the pause between attempts matters as much as the timeout.

GitLab's documentation and its code disagree. The style guide says the helper tries 50 times, then runs once more without `lock_timeout`. The code at master retries 615 times over about 44.6 minutes, with timeouts from 0.1 s to 2 s. In migrations, `lock_retries_helpers.rb` line 43 sets `raise_on_exhaustion` to true, so the migration fails when the retries run out. This course teaches the code, and it did not search for places where GitLab overrides the schedule.

#### A timeout policy, beyond lock_timeout

Phase 3 gave the timeout settings, their defaults and the `log_lock_waits` line formats, and all are off by default. Here is the role of each in a migration:

| Setting | Its role in a migration | Where to set it |
|---|---|---|
| `lock_timeout` | bounds each wait for one lock, so the queue behind it moves | every DDL statement, `SET lock_timeout = '100ms'`, with retries |
| `statement_timeout` | stops a scan or a rewrite that runs longer than planned | per migration with `SET LOCAL`, and per role. Not in `postgresql.conf`, which the docs advise against |
| `idle_in_transaction_session_timeout`, and `transaction_timeout` from 17 | ends the session whose open transaction a migration would wait behind | per role, for application sessions |
| `log_lock_waits` | logs every lock wait longer than `deadlock_timeout`, 1 s | on, in `postgresql.conf` |

With `log_lock_waits` on, a migration that waits writes `process %d still waiting for %s on %s after %ld.%03d ms`. Its detail line lists the holders and the wait queue. That pair of lines shows the lock queue in a production log.

#### CREATE INDEX CONCURRENTLY in full

1. It scans the table twice. It also must wait for all existing transactions that could modify or use the index to end.
2. If it fails, it leaves an index marked invalid. That index is ignored for queries but still costs every update. Drop it and build again, or use `REINDEX INDEX CONCURRENTLY`.
3. It cannot run inside a transaction block, and only one concurrent build can run on a table at a time.
4. While it runs, it holds a snapshot. So vacuum cannot remove dead rows in any table, by the cleanup horizon of the VACUUM section.

Three checks belong before and during such a build:

1. **Before:** run `SELECT pid, now() - xact_start, query FROM pg_stat_activity WHERE xact_start < now() - interval '1 minute' ORDER BY xact_start`. A concurrent build waits for such transactions. Other DDL waits for the ones that hold a lock on its table. A query that ends in `(to prevent wraparound)` is the Joyent case.
2. **During:** `pg_stat_progress_create_index` shows the build's `phase`.
3. **After a failure:** `SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid` lists invalid indexes. `pg_index.indisvalid` is the flag a concurrent build switches.

A unique constraint can be added the same way. Build `CREATE UNIQUE INDEX CONCURRENTLY` first. Then `ADD CONSTRAINT ... USING INDEX` turns the index into the constraint, which is a fast operation for a UNIQUE constraint. Its lock is not stated on that page, so assume ACCESS EXCLUSIVE, the page's default, held briefly. That lock level is inferred.

</details>

<details><summary>Evidence</summary>

The conflict lists are from the PostgreSQL 14 docs, section 13.3.1. The two queue rules are in the lmgr README at REL_14_0, line 364, "A lock request is granted immediately if it does not conflict with any existing or waiting lock request", and line 386, conflicting requests "are granted in order of arrival". The three-session run, the 4.04 s, 5.03 s, 0.18 s and 0.07 s, and the foreign-key run are the course research's, on PostgreSQL 14.24 on 2026-10-17. The DDL lock rows are from the ALTER TABLE, CREATE INDEX and REINDEX pages. The REINDEX locks are in `index.c` REL_14_24, lines 3602 and 3641, fetched on 2026-10-18. The MVCC-safety rule is from the ALTER TABLE page, as quoted in the study note, and from section 13.5. The GoCardless outage is from its post "Zero-downtime Postgres migrations, the hard parts", and the foreign-key change from the 9.5 release notes. `lock_timeout` is from section 20.11.1, and the 55P03 error from `postgres.c` REL_14_24, line 3299. The retry values are from each source in the sources list, and GitLab's code was fetched on 2026-10-18. The log line is at `proc.c` REL_14_24, line 1624. The concurrent build rules are from the CREATE INDEX page, the snapshot point from James Coleman's Braintree draft, and the progress view from section 28.4.

</details>

## How do you add a NOT NULL column with no failed request?

The task queue now needs `queue text NOT NULL` on `p4_tasks`, which workers write all day. The *expand/contract* pattern changes a schema in steps that keep the old and the new code working. Expand adds what the new code needs. Contract removes the old shape once nothing uses it.

1. **1 expand: ADD COLUMN queue text**ACCESS EXCLUSIVE, catalog only
2. **2 switch: deploy code that writes queue**no lock. The old code drains
3. **3 backfill: UPDATE a batch of ids WHERE queue IS NULL, then pause**row locks on 1,000 rows per transaction
4. **4 check: ADD CHECK (queue IS NOT NULL) NOT VALID**ACCESS EXCLUSIVE, catalog only
5. **5 validate: VALIDATE CONSTRAINT**SHARE UPDATE EXCLUSIVE, one scan
6. **6 not null: SET NOT NULL**ACCESS EXCLUSIVE, scan skipped
7. **7 contract: DROP CONSTRAINT the CHECK**ACCESS EXCLUSIVE, catalog only

Every ACCESS EXCLUSIVE step runs with `lock_timeout` 100 ms and retries. This is the plan of `migrate_lab.py`, strategy expand-contract.

Each ACCESS EXCLUSIVE step holds its lock for milliseconds. On 1,000,000 rows the course research measured `ADD COLUMN ... DEFAULT 42` at 2.5 ms, because a constant default changes only the catalog. `SET NOT NULL` took 0.68 ms after a valid CHECK and 48.2 ms without one, because the CHECK lets it skip its scan. `VALIDATE CONSTRAINT` does that scan under `SHARE UPDATE EXCLUSIVE`, so traffic goes on.

Between expand and contract, two code versions run against one schema. New code must not deploy before step 1, or its writes fail. Old code never writes `queue`, so after step 4 its inserts fail with SQLSTATE 23514. So the switch must finish before the backfill's last batch.

**Naive:** one transaction, no `lock_timeout`, behind a transaction open for 5 s. Most of the about 2,000 requests in that window pass their 1-second deadline and fail.

**Expand/contract:** the expand step retries at 100 ms until the open transaction ends, so no request fails.

Expected from the lab's rules at 400 requests a second, not measured. A migration tested on an idle copy proves little, because lock waits depend on traffic. GoCardless's migrations took a few hundred milliseconds on a restored backup, and production still had 15 seconds of downtime.

<details><summary>Go deeper: what other teams do, the wrong and right SQL, the lab's lint, and the arithmetic behind the lab's numbers</summary>

#### The core, in more detail

A bounded wait makes each statement safe to queue. Expand removes nothing. `ADD COLUMN` with no default also changes only the catalog, while `DEFAULT random()` took 996.7 ms, because it rewrote the table. `ADD CHECK ... NOT VALID` changes only the catalog, and checks new rows from then on. The 48.2 ms of `SET NOT NULL` without the CHECK is spent under ACCESS EXCLUSIVE.

New code that writes `queue` before step 1 fails on every write with an unknown column. The 23514 error is `check_violation`. Every old instance must be gone before the backfill's last batch.

The lab runs 4 readers and 4 writers at 50 requests a second each, with a 1,000 ms deadline per request. In the naive run, the old code's inserts fail with 23502 after the commit, about 100 per second. In the expand/contract run, the expand step makes about 9 attempts with 8 lock timeouts, and no request waits much longer than 100 ms. The GoCardless outage came from one long transaction in production that the copy did not have. So test a migration under load and measure the lock waits, as E10 and E11 do.

#### What other teams do

The strong_migrations README gives the same order for NOT NULL. First a CHECK `NOT VALID`, then a validation in a separate migration, then `NOT NULL`, then dropping the CHECK. It names three keys to backfilling safely: batching, throttling, and running it outside a transaction. Its example updates 10,000 rows per batch with a 0.01 s sleep. GitLab's batched background migrations use batches of 1,000 with sub-batches of 100, and its guide keeps any single query under 1 second. Stripe's post "Online migrations at scale", by Jacqueline Xu, describes the same idea for moving data between models. It has four phases: write to both, move the reads, move the writes, remove the old data. The post does not name its database engine. Moving a very large table to new storage, with dual writes or logical replication, is course 5.

#### Wrong and right, as SQL

```
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

#### The research's measurements, in full

```
Time holding ACCESS EXCLUSIVE, 1,000,000 rows. Measured by the research
ADD COLUMN d1 int DEFAULT 42                      2.5 ms   no rewrite
    the file number stayed 16401
ADD COLUMN d2 float8 DEFAULT random()           996.7 ms   rewrite
    the file number changed 16401 ─► 16434
SET NOT NULL, after a valid CHECK (n IS NOT NULL) 0.68 ms  scan skipped
SET NOT NULL, no CHECK                           48.2 ms   full scan
```

With `client_min_messages = debug1`, the skipped scan printed `existing constraints on column "t.n" are sufficient to prove that it does not contain nulls`. The 48 ms is for 1 million narrow rows in memory. It grows with the table, and all of it is spent under ACCESS EXCLUSIVE. So `ADD COLUMN queue text NOT NULL DEFAULT 'default'` does not rewrite the rows on PostgreSQL 14, because a constant default is stored in the catalog.

#### The compatibility window, in detail

After the CHECK of step 4, the constraint is enforced against later inserts or updates. So step 5 also fails on the NULL rows that the old code left, and `--break-compat` shows both failures. Without the CHECK, step 6 would make the same inserts fail with 23502, `not_null_violation`. In the lab, the switch step waits `--settle-s` seconds to stand for the deploy. A column DEFAULT is the other way to keep old inserts working. `--strategy constant-default` adds the column with `DEFAULT 'default'`, and it backfills only the rows that need another value.

#### The lab's arithmetic

- `--strategy naive --hold-lock-s 5`: the ALTER waits 5 s with no timeout, and every request queues behind it. About 400 × 5 = 2,000 requests are scheduled in that window, and most of them fail with 57014 or `late`. Inserts are half of the writers' requests, so about 4 × 50 × 0.5 = 100 old-code inserts fail per second after the commit.
- `--strategy expand-contract --hold-lock-s 5`: the default `--seed 1` fixes the random backoff waits. Python's `random.Random(1)` gives 7, 85, 153, 102, 396, 719, 1,303 and 1,577 ms. With 100 ms per failed attempt, the ninth attempt starts at about 5.14 s, after the open transaction has committed. So expect 9 attempts and 8 lock timeouts. That was computed from the generator, not from a run of the lab.

</details>

<details><summary>Evidence</summary>

The measurements are the course research's, on PostgreSQL 14.24 on 2026-10-17, on a table of 1,000,000 rows. The constant default without a rewrite is from the PostgreSQL 11 release notes and the 14 ALTER TABLE page, and the skipped scan of SET NOT NULL from the 12 release notes and the same page. The CHECK enforcement wording, "enforced against subsequent inserts or updates", is from the ALTER TABLE page. The strong_migrations quotes are from its README, GitLab's sizes from its batched background migrations guide, and the four phases from Stripe's post of 2017. The GoCardless test on a restored backup is from its post "Zero-downtime Postgres migrations, the hard parts".

</details>

## Which schema changes can you undo?

Every step of the NOT NULL plan can be reversed, and not every migration can. A reverse statement changes the schema's shape, and it does not bring data back. So sort every step into one of two kinds. *Additive steps* add a column, a table, an index or a constraint, or copy data, and their reverse loses nothing. *Destructive steps* drop, narrow, overwrite or rename what the old code uses, and their reverse cannot restore the data.

| Change | Can you undo it without losing data? |
|---|---|
| `ADD COLUMN queue text`, before any code writes it | yes: drop the column |
| The batched backfill of `queue` | yes: the column is still nullable, and no old code reads it |
| `ALTER COLUMN queue SET NOT NULL` | yes: `DROP NOT NULL` |
| `DROP COLUMN old_status`, a week after the code stopped reading it | no |
| `ALTER COLUMN amount_cents TYPE integer`, from `bigint` | no, unless every value fits, and even then the reverse is a rewrite under ACCESS EXCLUSIVE |
| A backfill that rewrites `status` in place, from `paid` to the new value `settled` | no: the rows that were `paid` and the rows already `settled` look the same afterwards |

DROP COLUMN only makes the column invisible to SQL, and no statement makes it visible again. The only way back is a backup restore, which also loses every later write. So structure a change to stay additive.

1. Expand only adds, next to the old shape and never in its place.
2. To change a column's type or meaning, add a new column, write both, and backfill the new one.
3. Pair every step with its reverse in the plan, and say what the reverse loses.
4. Undo code before schema, because code that still writes `queue` fails with 42703 once the column is gone.
5. Contract last, in its own release, once no running code uses the old shape.

A down migration that never ran is the usual failure. By the day it is needed, the table holds data it was not written for. Test each reverse under load, as E11 does with `--rollback-after`.

Bound every lock wait with lock_timeout, and keep each step additive until a separate contract release.

Trusting an instant statement with no lock_timeout: an ADD COLUMN kept a one-row SELECT waiting 4.04 s.

<details><summary>Go deeper: the compatibility window as a grid, the reverse of each step, and two team policies</summary>

#### Try this now

Run `uv run python phase04_planning/locks.py --predict "CREATE INDEX p4_tasks_state ON p4_tasks (state)"`, then the same with `CONCURRENTLY`. Compare the lock modes and the `blocks` lines. Then run `uv run python phase04_planning/migrate_lab.py --plan --strategy naive`, then the same with `--strategy expand-contract`. For each step of the naive plan, say what its reverse would lose.

#### The core, in more detail

Code goes back to its previous version in minutes, and the schema often cannot. When a deploy goes wrong, the first instinct is to roll back, and some changes destroy the data that the old version needs. Whether a rollback is possible is decided when the migration is designed, not when it fails. A destructive step's reverse either cannot restore the data, or the old code fails at once. DROP COLUMN does not physically remove the column, and its bytes stay on disk until rows are rewritten. The same holds for `DROP TABLE` and `TRUNCATE`. A type change that narrows a column fails, or with a `USING` expression it converts and loses the original values. The error 42703 is `undefined_column`. Contract only once a backup exists as well.

Many teams roll forward instead of back: they fix a bad change with a new change, while the schema keeps its expanded shape. Many frameworks generate a down step for each migration, and nobody runs it until the day it is needed. The data it was not written for includes rows that only the new code wrote.

#### The compatibility window

```
The compatibility window. Each row must work with the schema above it
schema    old      │ + queue nullable │ + backfill, NOT NULL │ old col
                   │ expand           │                      │ dropped
code v1   ok       │ ok: ignores it   │ needs a DEFAULT or   │ fails if
                   │                  │ it fails on insert   │ it reads
code v2   fails:   │ ok: writes it    │ ok                   │ ok
          no col   │                  │                      │
rolling code back from v2 to v1 is safe in the middle columns only
```

#### The expand/contract steps with their reverses

This is what `migrate_lab.py --plan` prints for every step:

| Step | Reverse | What the reverse loses |
|---|---|---|
| expand: ADD COLUMN queue | DROP COLUMN queue | the queue values, which the backfill can compute again |
| switch: new code writes queue | deploy the old code | nothing |
| backfill | none needed | nothing: the column is still nullable |
| check: CHECK NOT VALID | DROP CONSTRAINT | nothing |
| validate | dropping the CHECK undoes it | nothing |
| not null: SET NOT NULL | DROP NOT NULL | nothing |
| contract: DROP the CHECK | ADD the CHECK NOT VALID again | nothing |

Every step of this plan is additive, so the whole plan can be undone. A plan that renames or retypes a column has a destructive last step: dropping the old column. Keep it as a separate migration, released after the waiting period. `--rollback-after` follows the code-first order.

#### Two team policies

strong_migrations has a six-step recipe for a type change and a rename. Create the new column, write both, backfill, move reads, stop writing the old one, then drop it. James Coleman's Braintree draft states the rollback policy in one line: "Rollback strategies do not involve reverting the database schema to its previous version." Before a DROP COLUMN reaches production, the same draft requires proof that no code references the column. GitLab works the same way. Its migration guide says that on its production environments, "a roll-forward strategy is used instead of rolling back migrations". A rewrite in place replaces the old values, and the new values do not say what the old ones were, so treat a destructive step as having no reverse at all.

</details>

<details><summary>Evidence</summary>

That DROP COLUMN "does not physically remove the column" is from the PostgreSQL 14 ALTER TABLE page. The six-step recipe is from the strong_migrations README. The rollback line and the DROP COLUMN proof are from James Coleman's 2019 draft gist. The roll-forward rule is from GitLab's migration style guide. The 4.04 s in the trap is the course research's three-session run on PostgreSQL 14.24.

</details>

## What the course leaves you with

The 9-second report and the 11-minute outage now each have a cause you can name in advance. The report's estimate came from statistics older than the incident, so ANALYZE fixed it and an index could not. The outage came from a SHARE lock held for a whole build. `CREATE INDEX CONCURRENTLY` with a `lock_timeout` would most likely have kept checkout running.

This is the last phase of the course. Safe rollout, with canaries, feature flags and rollout gates, is course 6, "Reliability, security and change", Phase 3. Schema changes that break another service's contract are course 7, "System design and architecture", Phase 2. Splitting a table across servers, and replicas, are course 5.

### The course's storage note

The course closes with one page. It says what the course's system guarantees, what it does not, and how you know. The system is the order store of Phases 1 and 2, and the order data and task queue in PostgreSQL 14. A guarantee belongs in the note only with the test that would show it false. No test below was run by the author, so each "how you know" cell gives the result to expect.

The template, for any storage system you own, then the note for the course's system.

```
STORAGE NOTE: <system>, <version>, <date>
1 Durability   when OK is sent, the crashes it survives, what recovery
               returns, what is not covered
2 Structure    the layout, its read, write and space amplification on
               our workload, and the number that would make us move
3 Isolation    the level, each invariant, the anomaly it allows, and
               the fix in code
4 Plans        what keeps the statistics current, and the alert
5 Change       the lock rules every migration follows, and its reverse
6 Not covered  the failures this note does not protect against
each line: the claim, the test that would show it false, and its status
```

| Area | What it guarantees | What it does not | How you know, and status |
|---|---|---|---|
| Durability, Phase 1 | A put that returned OK with `--sync full` survives a process crash, an OS crash and a power loss. Recovery returns a prefix of the puts in log order, and never an entry that fails its CRC | Damage to data already synced, a drive that ignores flush commands, loss of the device. With plain `os.fsync` on macOS, a power loss, from Apple's `fsync(2)` | `crash_matrix.py`: 0 violations in 231 recoveries, and 42 power violations for the false claim of `--sync fsync --claim-power-safe`. Worked out from the code, not run |
| Structure, Phase 2 | The log layout writes 1.18 bytes per byte. With filters, both layouts read about one block per present key | The log's space grows with every overwrite: 11.77 times the live data on the write-heavy mix. The LSM writes about 14.7 bytes per byte | `amplification.py`, E6 of Phase 2. Worked out from the code and its seed, not run. Move to the LSM when disk, not write volume, is the limit |
| Isolation, Phase 3 | The task claim, the approval and the outbox write keep their invariants at READ COMMITTED, with one conditional statement each. The approvers' rule holds at SERIALIZABLE with a retry of the whole transaction on 40001 | REPEATABLE READ allows write skew: 0 approvers on call. No level fixes a relay that tracks ids. The outbox delivers at least once, so consumers drop duplicates | `write_skew.py` and `taskqueue.py`, E5, E10 and E11 of Phase 3. Each check exits 1 at the old level, and the relay check at every level. Not run |
| Plans, Phase 4 | Every bulk load, backfill or bulk update ends with `ANALYZE` of its table. A slow query is found with `pg_stat_statements`, and its plan is taken from `auto_explain`. A plan regression is first checked by comparing estimated and actual rows | Autovacuum's ANALYZE comes only after 50 + 0.1 × reltuples changed rows, and only when a worker reaches the table. Partitioned parents are never analyzed by it. A prepared statement can switch to a generic plan after five executions, unless `plan_cache_mode` forbids it | `plan_lab.py`, E4: est 1 against 400,000 before ANALYZE, close after. `plan_cache.py`, E13: generic from execution 6. `find_slow.py`, E14. Not run |
| Change, Phase 4 | Every DDL statement runs with `lock_timeout` and retries. A NOT NULL column goes in by expand/contract, and every step before the contract has a reverse that loses no data | A destructive step, such as DROP COLUMN, has no reverse. A transaction left open still delays every migration on its tables | `migrate_lab.py`, E10 and E11: failures with the naive plan, 0 failed requests and lock waits near 100 ms with expand/contract. Not run |
| Not covered |  | Operator deletion and failed backups, the GitLab case of Phase 1. Replicas, and what a replica has: course 5. Transaction ID and multixact wraparound, unless `age(datfrozenxid)` and `mxid_age(datminmxid)` are alerted on, as the wraparound section showed | the alert queries of `bloat.py --xid`. Not run |

The note is one page because each line points to its evidence instead of repeating it. When a test runs and disagrees with its cell, the cell changes, not the test. E12 in the lab asks you to fill in the template for a system you own.

## Lab

Sixteen exercises, in the phase's own order and copied from it. E4, E10 and E11 are the phase's demonstration. They were written and reviewed, and not run by the author. Each idea of the lesson has its exercises:

| Idea | Exercises |
|---|---|
| Where a plan went wrong, and finding it in production | E14, E15 |
| Estimates from the last ANALYZE, and generic plans | E4, the correlated case of E5, E13 |
| Scans and joins priced from estimates | E2, E3, the join methods of E5 |
| VACUUM, wraparound and partitioning | E6, E7, E8, E16 |
| Lock waits, expand/contract and rollback | E9, E10, E11 |
| The whole course | E1, the self-tests, and E12, the storage note |

<details><summary>Open the lab: setup, the files, and E1 to E16</summary>

The lab text is copied from the phase, which numbers its sections. They are 4.1 reading plans, 4.2 estimates and generic plans, 4.3 access paths, 4.4 joins, 4.5 VACUUM and wraparound, 4.6 partitioning, 4.7 migrations and 4.8 rollback.

**The running system.** The lab tables carry the prefix `p4_`, so the labs of earlier phases keep working. `p4_orders`, `p4_order_events` and `p4_tenants` hold the order data of the opening case at 1 million orders. `p4_tasks` has the columns of Phase 3's `tq_tasks`, the course's own task queue.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. The labs need your local PostgreSQL 14 at `/tmp:5432`, in the database `storage_lab`, with psycopg 3.3.6 from `pyproject.toml`. `cost_model.py`, `locks.py --predict` and every `--self-test` run with no server. Run all commands from `elite-storage/code/`.

Time: 3 hours for the reading. The labs take longer, about 3.5 hours.

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

**E1** offline Run every self-test of this phase, then those of the earlier phases.

  - Run: `for f in phase04_planning/*.py; do echo "$f"; uv run python "$f" --self-test; done`
  - Then run: `for f in shared/*.py phase01_durability/*.py phase02_structures/*.py phase03_transactions/*.py; do echo "$f"; uv run python "$f" --self-test; done`
  - Expected: Not run by the author yet. `self-test passed` after each of the 10 Phase 4 files, and after each of the 20 earlier scripts. The loop also runs `shared/__init__.py`, which is empty and prints nothing.
  - If it fails: the assertion message names the formula or the rule. Compare it with the section it comes from before you change any code.
  - Teaches: each rule that the text calls important has a check that fails without it.

**E2** offline The planner's arithmetic, by the model.

  - First write your prediction for the research table at 1 row, 1%, 40% and 45%, from section 4.3.
  - Run: `uv run python phase04_planning/cost_model.py --sweep`, then add `--random-page-cost 1.1`, then run it with `--correlation 1.0`.
  - Expected: Not run by the author yet. The default sweep picks Index Scan at 0.0001%, Bitmap Heap Scan from 0.001% to 40%, and Seq Scan from 45%. The Seq Scan cost is 21846.00. At 40% the bitmap row shows about 21,338, and at 45% about 22,839. With 1.1, the Index Scan wins at 50%. With correlation 1.0, the Index Scan wins at 10%, about 3,664 against 12,347.
  - Teaches: the switch points come from pages, rows and correlation, and the model shows which term decides.

**E3** local The same sweep on your PostgreSQL 14.

  - Run: `uv run python phase04_planning/access_paths.py`, then `--skip-build --random-page-cost 1.1`, then `--correlated`, then `--covering --analyze`, then `--pad-bytes 400`.
  - Expected: Not run by the author yet. The header shows your page count. With the default 40-byte pad, the arithmetic below gives about 10,300 pages, close to the research's 9,346. Expect the same order of plans: Index Scan, Bitmap Heap Scan, Seq Scan. The `model` column agrees, except where two costs are within a few percent. `--correlated` shows Index Scan over a wide range. `--covering` shows Index Only Scan, and its `read` column stays low after VACUUM. With 400-byte pads, a row takes about 444 bytes of its page instead of about 84. So the table has about five times the pages, and the switch should move. These sizes are inferred from the PostgreSQL 14 docs, section 70.6. A row header is 23 bytes, padded to 24, and each row adds a 4-byte line pointer. They were not measured.
  - If the switch differs from the research's: compare your rows per page and correlation with section 4.3 first.
  - Teaches: the research's switch points belong to its table, not to PostgreSQL.

**E4** break-it, local Part of the demonstration: break the statistics, diagnose, fix.

  - First predict the estimate for `pending` after the incident, from section 4.2.
  - Run: `uv run python phase04_planning/plan_lab.py`.
  - Expected: Not run by the author yet. `400,000 orders are now pending (expected 400,000)`. `pg_stats` shows three values whose frequencies add up to 1, and the formula line gives a selectivity of 0. The plan's scan of `p4_orders` shows est 1 and actual 400,000. The plan is expected to be a Nested Loop whose inner Index Scan on `p4_order_events` shows 400,000 loops. `team-fix` still shows est 1. After `fix`, the estimate is near 400,000 and the join is expected to be a Hash Join. The before-and-after table shows the plan shapes, the worst q-error, the buffers and the execution time. The last line is `RESULT: worst q-error 400,000 before`, then a value under 10 after, and `Fixed`. The plan choices are expected from the cost model, not run.
  - If the first plan is already a Hash Join: your cost settings differ from the defaults. Check `show random_page_cost` and `show work_mem`, and note it. The estimate of 1 row is still the lesson.
  - Teaches: one stale MCV list turns 400,000 rows into 1, and ANALYZE, not an index, fixes it.

**E5** local Correlated columns and the three join methods.

  - Run: `uv run python phase04_planning/plan_lab.py --case correlated`, then `uv run python phase04_planning/plan_lab.py --case join-methods --skip-build --analyze`.
  - Expected: Not run by the author yet. Correlated: est 1 and actual 100 before, est 100 after, and the GROUP BY estimate 1000 before and 100 after. The course research saw exactly these on 14.24. Join methods: three outer sizes, each with four rows. The `planner` row's cost equals the lowest of the three forced rows. At 10 outer rows, expect a nested loop to be cheapest. At the full table, expect a hash join.
  - Teaches: the independence assumption and its fix. The planner's join is the cheapest by its own estimates.

**E6** break-it, local Bloat behind one open transaction.

  - Run: `uv run python phase04_planning/bloat.py --held-rounds 3 --pgstattuple`.
  - Expected: Not run by the author yet. The page counts follow the bar chart of section 4.5. They are about 1x at the load, and 2x after the first UPDATE, the VACUUM and the second UPDATE. The first held round grows the file to about 3x. Its VACUUM still frees the versions that died before H's snapshot, so the second held round reuses that space. The third held round grows the file to about 4x. After H commits, VACUUM frees space, and the next UPDATE does not grow the file. VACUUM FULL brings it back to about 1x. The SELECT during VACUUM FULL takes about as long as VACUUM FULL itself, because ACCESS EXCLUSIVE blocks it.
  - If `pgstattuple` is missing: the script says so and uses `pg_stat_user_tables` only.
  - Teaches: VACUUM removes only what died before the oldest snapshot, and it never shrinks the file.

**E7** local Transaction ID ages and the limits.

  - Run: `uv run python phase04_planning/bloat.py --xid`.
  - Expected: Not run by the author yet. The settings line shows `autovacuum_freeze_max_age 200000000` and `vacuum_failsafe_age 1600000000`, the PostgreSQL 14 defaults. A laptop cluster shows small ages, so each distance is close to its limit. For an age near 0, the stop is about 2,144 million away. The lists of old sessions, slots and prepared transactions are short or empty.
  - Teaches: what to alert on, long before the WARNING.

**E8** local Pruning, and what partitioning costs the planner.

  - Run: `uv run python phase04_planning/partitions.py --planning-sweep 12,120,1200`.
  - Expected: Not run by the author yet. `prune`: 1 partition scanned, expected 1. `no-key`: 12 of 12. `generic`: `Subplans Removed: 11`. `parent-stats`: 0 rows before ANALYZE and some after. `unique`: an ERROR line from the server. `drop`: the DELETE leaves about 100,000 dead rows, one twelfth of 1,200,000, and the DROP none. The planning sweep is expected to grow with the partition count. No time is claimed.
  - Teaches: pruning comes from the partition key only, and unpruned partitions cost planning time.

**E9** break-it, offline, then local The lock queue, predicted and then reproduced.

  - First run: `uv run python phase04_planning/locks.py --table`, then `--scenario queue`, then `--scenario queue-timeout`, then `--scenario fk`.
  - Then run: `uv run python phase04_planning/locks.py --live queue --lock-timeout 0`, then `--live queue --lock-timeout 100ms`, then `--live fk --hold-s 5`.
  - Expected: Not run by the author yet. The offline queue shows C `granted=False` behind B, and A's commit waking B first. With the timeout, B's exit wakes C. The fk scenario grants the SELECT and queues the INSERT. Live, with a timeout of 0, the later SELECT takes about 4 s, close to the research's 4.04 s. The `obs` lines show B `granted=false` with ACCESS EXCLUSIVE, and C blocked by B. With 100ms: B fails with 55P03 after about 0.1 to 0.2 s, and C takes well under a second. The research measured 0.18 s and 0.07 s. The fk run: the SELECT is fast, and the INSERT takes about 3 s.
  - Teaches: a queued request blocks every later conflicting request, and lock_timeout bounds that block.

**E10** break-it, local Part of the demonstration: the naive migration under load.

  - First predict the failed requests, with the arithmetic of section 4.7.
  - Run: `uv run python phase04_planning/migrate_lab.py --plan --strategy naive`, then `uv run python phase04_planning/migrate_lab.py --strategy naive --hold-lock-s 5; echo "exit $?"`.
  - Expected: Not run by the author yet. The plan's lint lists 3 problems. The run's `all-in-one` row shows failures with 57014 and `late`. They are most of the about 2,000 requests scheduled during the hold. The lock wait max is near 1,000 ms, because each request gives up at its 1-second deadline. The `after` row shows 23502 failures, about 100 per second, because the old code inserts no `queue`. The RESULT line counts the failures, and the exit code is 1.
  - Teaches: one instant ALTER behind one open transaction stops the table. A NOT NULL column breaks the code that does not write it.

**E11** local Part of the demonstration: expand/contract with no failed request. Then two ways to break it, and a rollback.

  - Run: `uv run python phase04_planning/migrate_lab.py --strategy expand-contract --hold-lock-s 5; echo "exit $?"`.
  - Expected: Not run by the author yet. The `expand` step shows about 9 attempts and 8 lock timeouts, from the backoff arithmetic of section 4.7. Every phase row shows 0 failed. The max latency stays near 100 ms plus the request's own time, and the lock wait max near 100 ms. The backfill shows 201 or 202 batches. 200 cover the loaded rows. The rest cover about 1,000 rows that the writers inserted first, at about 100 per second for about 10 s. `RESULT: ... 0 failed. queue NOT NULL: True. Rows without a queue: 0. Rows with the wrong queue: 0`, and the exit code is 0.
  - Then run: `uv run python phase04_planning/migrate_lab.py --strategy expand-contract --old-writers 2 --break-compat; echo "exit $?"`. Expected: 23514 failures from the `check` phase on, the old code's inserts. Then `step validate failed` with 23514, and exit 1.
  - Then run: `uv run python phase04_planning/migrate_lab.py --strategy expand-contract --rollback-after check`. Expected: three reverse lines, the CHECK dropped, the writers switched back and the column dropped, then `Column present: False`, with 0 failed.
  - Teaches: bounded lock waits and a compatibility window add a NOT NULL column with no failed request. Undo runs code first, schema second.

**E12** written Write the course's storage note.

  - Do: fill in the template of the next section for a system you own. Or check the filled note against your own lab results.
  - Expected: one page. Every "how you know" cell names a test and says whether you ran it.
  - Teaches: a guarantee is a sentence plus the test that would show it false.

The four exercises below cover the production signals of sections 4.1, 4.2, 4.4 and 4.5. They come after the storage note because none of them is part of the demonstration.

**E13** break-it, local A prepared statement switches to a generic plan.

  - First predict, from section 4.2, at which execution the plan changes. Also predict the generic plan's estimate for the largest tenant.
  - Run: `uv run python phase04_planning/plan_cache.py`, then `uv run python phase04_planning/plan_cache.py --skip-build --mode force_custom_plan`.
  - Expected: Not run by the author yet. The header prints the generic estimate, about 1,000 orders, which is 1,000,000 / 1,000 tenants. It also prints tenant 1's real count, about 100,300. Executions 1 to 5 show `custom`, with est close to actual, about 1,600 to 2,900 orders. Executions 6 and 7 show `generic`, with est about 1,000 and actual about 100,300 for tenant 1. The counters end at 2 generic and 5 custom. The generic plan is expected to be a Nested Loop, and `force_custom_plan` a Hash Join. Those plan shapes are inferred from the join arithmetic of section 4.4. With `--mode force_custom_plan`, every row shows `custom`.
  - If no generic plan appears: the script prints that the generic cost was not below the custom average. Compare the printed estimates, and note it. The estimate of the generic plan is still the lesson.
  - Teaches: a generic plan uses the average over all values, and `plan_cache_mode` controls it.

**E14** local Find the slow query, then its plan, the way you would at work.

  - Run: `uv run python phase04_planning/find_slow.py --check`. Add the line it prints to `postgresql.conf`, the file that `psql -h /tmp -d storage_lab -c "show config_file"` names. Restart the server the way you started it, then run `psql -h /tmp -d storage_lab -c "create extension pg_stat_statements"`. To undo the setup later, remove the line and restart again.
  - Then run: `uv run python phase04_planning/plan_lab.py`, then `uv run python phase04_planning/find_slow.py --top 5`, then `uv run python phase04_planning/find_slow.py --auto-explain-demo`.
  - Expected: Not run by the author yet. `--check` lists `shared_preload_libraries` as missing on a default install. After the restart and the CREATE EXTENSION, it prints `pg_stat_statements is ready`. The first ranking shows the lab's build statements and its report near the top by `total_exec_time`. The demo prints a line that starts with `duration:`, then the plan of the report. It has buffers and no per-node times, because `log_timing` is off.
  - If LOAD fails: your role is not a superuser. The demo needs one, and the rankings do not.
  - Teaches: find the query by its server time, then take the plan it really ran.

**E15** local The plan your server makes, with parallel workers, JIT and a spill.

  - Run, after E4: `uv run python phase04_planning/explain_tools.py --server-defaults --sql "select tenant_id, count(*) from p4_orders group by tenant_id"`. Then run the same without `--server-defaults`. Then run `uv run python phase04_planning/explain_tools.py --set work_mem=64kB --sql "select * from p4_orders order by amount_cents"`.
  - Expected: Not run by the author yet. With `--server-defaults`, expect a Gather with `Workers Planned: 2`. Below it, expect a partial aggregate and a Seq Scan marked `per process, divisor 2.4`, with 3 loops. Without the flag, the same query has no Gather. A `JIT:` line appears only if the plan's cost passes 100,000 and the server has LLVM. `p4_orders` at 1,000,000 rows is about a tenth of the opening case, so its cost may stay below that. With `work_mem=64kB`, the Sort's line shows `Sort Method: external merge` and `Sort Space Type: Disk`. These shapes are inferred from sections 4.1 and 4.4.
  - Teaches: the lab's serial plans are a choice, and your server's plans read differently.

**E16** break-it, offline, then local The autovacuum budget, and the forced vacuum that does not give way.

  - Run: `uv run python phase04_planning/locks.py --scenario autovacuum`, then `--scenario wraparound`. Then run `uv run python phase04_planning/bloat.py --vacuum-signals`.
  - Expected: Not run by the author yet. `autovacuum`: D and S queue, then the deadlock check cancels the autovacuum, D runs, then S. `wraparound`: the autovacuum is not cancelled, and S runs only after it finishes. `--vacuum-signals` prints the settings of section 4.5 and a budget of about 66 per worker when 3 run. It prints the ceilings of 781.3 and 35.5 MB/s. It notes that `log_autovacuum_min_duration` is −1 on 14. The p4_ tables appear with their dead-row counts, and no vacuum is running on a quiet laptop.
  - Teaches: more workers share one budget. A wraparound vacuum turns any DDL without a `lock_timeout` into an outage.

</details>

<details><summary>Open "Check it yourself": five readings of the lab's code</summary>

- **Check 1.** Open `phase04_planning/cost_model.py:195`, the body of `bitmap_scan()`. Compute the cost per page when the scan reads a quarter of the table's pages. Then use this line to explain a rule. A bitmap scan that reads every page is never cheaper per page than a sequential scan.
- **Check 2.** Open `phase04_planning/explain_tools.py:235`, `worst_node()`. It breaks a tie in q-error in favor of the deeper node. In the bad plan of its self-test, the Nested Loop and the Seq Scan have the same q-error of 400,000. Which node would a tie-break toward the top report, and why would that send you to the wrong fix?
- **Check 3.** Open `phase04_planning/locks.py:226`, `LockQueue.request()`. Suppose it checked only the granted locks and not the waiting ones. Which line of `scenario_queue` changes, and which self-test check fails? Is the model then closer to PostgreSQL or further from it, by the lmgr README's rule?
- **Check 4.** Open `phase04_planning/migrate_lab.py:376`, `run_statement()`. It retries only SQLSTATE 55P03. Suppose it also retried 57014, the statement timeout. Which step of the expand/contract plan could then run far longer than planned? Why is a statement timeout a different signal from a lock timeout?
- **Check 5.** In any repository you own that has database migrations, run `grep -rn "lock_timeout\|CONCURRENTLY\|NOT VALID\|DROP COLUMN" <your repo>/`. Find each migration that adds an index without `CONCURRENTLY`, or drops a column in the release that stopped using it. Name the lock it takes and the traffic it blocks.

</details>

## Checkpoint

Seven scenario questions with numbers, from the phase. Each one is answerable from this lesson.

<details><summary>Open the questions</summary>

The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

1. **Test-out, explain.** On the research's table of the access-path section, `WHERE x < k` selects 45% of the rows. The planner chooses a Seq Scan over the B-tree on `x`. Explain why with the cost arithmetic of both paths. Then name the statistic that would change its mind, and show with numbers how it would.
2. **Test-out, predict.** For each statement, give the lock it takes on `p4_tasks`. Say what it blocks while it waits and while it holds the lock. (a) `CREATE INDEX ON p4_tasks (state)`. (b) `CREATE INDEX CONCURRENTLY ON p4_tasks (state)`. (c) `ALTER TABLE p4_tasks ADD COLUMN note text DEFAULT 'none'`. (d) `ALTER TABLE p4_tasks VALIDATE CONSTRAINT p4_tasks_queue_not_null`. (e) `ALTER TABLE p4_tasks ALTER COLUMN attempts TYPE bigint`. Then take (c) with no `lock_timeout`, queued behind a transaction that has been open for 30 seconds. What happens to SELECTs?
3. **Test-out, demonstrate.** Run E4, E10 and E11. Show the plan before and after ANALYZE, with its estimated and actual rows, buffers and time. Then show the naive migration failing requests and the expand/contract migration failing none, with the lock waits measured. Explain why each result follows from the lesson, and not from timing luck.
4. **A colleague says:** "We are on SSDs, so we set `random_page_cost = 1.1` for the whole cluster. The docs say so." Argue for or against. What do the PostgreSQL 14 docs say about this setting, and where does the 1.1 come from? What did the research's table show at 1.1? What should be measured before a cluster-wide change? (b) A second colleague says: "Autovacuum cannot keep up with `orders`. Raise `autovacuum_max_workers` from 3 to 6." Argue for or against, with the budget arithmetic of the VACUUM section.
5. **This is broken.** `tq_outbox` gets 2 million inserts a day, and a job deletes sent rows every hour. VACUUM runs often, and `n_dead_tup` stays high. The table file grows by about 1 GB a day. `pg_stat_activity` shows one session `idle in transaction` since three days ago. What is the cause, how do you confirm it, and what is the fix? What do you do about the 3 days of growth?
6. **Show the arithmetic.** (a) The autovacuum ANALYZE and VACUUM thresholds of a 50,000,000-row table, at the defaults. (b) `pg_stats` for a column shows `n_distinct` 20 and `null_frac` 0.02. Its MCV list has 4 values whose frequencies add up to 0.92. The table has 8,000,000 rows. Estimate `WHERE col = 'x'` for a value not in the list. (c) A PostgreSQL 14 database has `age(datfrozenxid)` = 1,500,000,000 and assigns 3,000 transaction IDs per second. How long until the WARNING, and until new IDs are refused? (d) A migration uses `lock_timeout = 200ms` and fails 6 times before it gets its lock. At most how long were the table's queries blocked by its attempts? (e) Take PostgreSQL 14 defaults, and a table whose every page is read and dirtied. How many pages can autovacuum process per nap? What is the ceiling in MB/s for all workers together? How long does one pass over a 200 GB heap take at least? (f) `orders` has 10,000,000 rows. For `tenant_id`, `n_distinct` is 1,000 and `null_frac` is 0. The most common tenant has a frequency of 0.1. Estimate `tenant_id = $1` for a generic plan, and for a custom plan with that most common tenant.
7. **Given these constraints, design.** Rename `owner` to `worker_id` in `tq_tasks`. Workers claim tasks all day, and two versions of the worker code run during every deploy. No request may fail, and each step must be undoable until the last. Give the steps and the lock of each. Say which code version must run at each step, and which step cannot be undone.

</details>

<details><summary>Answer sketches</summary>

1. Seq Scan: 9,346 pages × 1.0 + 1,000,000 × 0.0125 = 21,846, which PostgreSQL 14.24 printed. Bitmap at 45%: the index part is 1,095 pages × 4.0 = 4,380, plus 450,000 × 0.0075 = 3,375. The bitmap adds 112.5. For the heap, Mackert and Lohman gives more than T. So all 9,346 pages are read, at 4.0 − 3.0 × √1 = 1.0 each. The rows: 450,000 × 0.0125 = 5,625. Total 22,839, above 21,846. A plain Index Scan pays 9,346 × 4.0 = 37,384 for the heap alone, because the correlation is 0.0004. Two statistics change the decision. Selectivity: at 40% the bitmap costs 21,338 and wins. Correlation: near 1, the Index Scan's heap cost moves toward 4.0 + 4,205 × 1.0, about 4,209 at 45%. Its total is then about 16,464, far below 21,846. At 10% the model gives 3,664 for the Index Scan against 12,347 for the bitmap.
2. (a) SHARE: blocks INSERT, UPDATE and DELETE for the whole build, and lets SELECTs through. (b) SHARE UPDATE EXCLUSIVE: blocks no reads or writes, only other DDL and VACUUM. It waits for older transactions and scans twice. (c) ACCESS EXCLUSIVE, catalog only since PostgreSQL 11: it holds the lock for milliseconds. (d) SHARE UPDATE EXCLUSIVE: one scan, and reads and writes go on. (e) ACCESS EXCLUSIVE with a rewrite of the table and its indexes, because integer to bigint is not binary coercible. Everything waits for the whole rewrite. That coercibility point is inferred from the docs' rule and was not checked for this type pair. If (c) waits behind a 30-second transaction with no `lock_timeout`, later SELECTs queue behind it. They wait until that transaction ends, by the lmgr README's rule. The research measured 4.04 s for a one-row SELECT behind a 5-second wait.
3. From the runs. E4: est 1 against actual 400,000 on `p4_orders`, and a nested loop with 400,000 inner loops. After ANALYZE, est near 400,000 and a hash join. The plan follows from the formula of the estimates section. All values are in the MCV list, so 1 − 1 = 0, clamped to 1 row. E10: the naive plan holds ACCESS EXCLUSIVE behind the 5-second holder, so requests pass their 1-second deadline. Then old inserts fail with 23502. E11: each lock attempt waits at most 100 ms, so no request passes 1 second. The CHECK lets SET NOT NULL skip its scan. The order is deterministic, because the holder opens before the migration starts. The load is open loop: every request has a fixed start time, so a stall is counted, not hidden.
4. (a) Mostly against a cluster-wide change. The PostgreSQL 14 and 18 docs keep 4.0 because most random reads are assumed to be in cache. They suggest lowering it when the data is likely to be completely in cache. The "SSD 1.1" text is in the PostgreSQL 10 docs. The research's grep did not find it in 13, 14 or 18. On the research's table at 1.1, Index Scans won at 30% and 50%. At 4.0, a bitmap scan won at 30%, and a Seq Scan at 50%. That is correct only if those random reads really are cheap. Before a change, run the hot queries under `EXPLAIN (ANALYZE, BUFFERS)` at both values on one session, and compare time and buffers. If only part of the data is cached, change it per tablespace or per role. (b) Against, on its own. The cost limit of 200 "is distributed proportionally among the running autovacuum workers". Six workers get about 33 units each instead of 66. The worst-case ceiling stays at about 35.5 MB/s. Raise the limit with the workers, or better, give `orders` its own `autovacuum_vacuum_cost_limit`, which also leaves the sharing. Lower its `autovacuum_vacuum_scale_factor`, so each run has less to do. On 14, a change of `autovacuum_max_workers` also needs a restart. First check `wait_event = VacuumDelay` in `pg_stat_activity`, which shows that the budget, not the disk, is the limit.
5. The idle transaction holds the cleanup horizon three days in the past. VACUUM runs and removes nothing that died after its snapshot. So every hourly delete leaves dead rows, and new inserts extend the file. Confirm: `age(backend_xmin)` of that session in `pg_stat_activity` is the largest, and `n_dead_tup` stops falling when VACUUM runs. Fix: end the session with `pg_terminate_backend`, set `idle_in_transaction_session_timeout`, and run VACUUM. The 3 days of growth stay in the file as free space, which new rows reuse. To return it to the system, VACUUM FULL or a rewrite takes ACCESS EXCLUSIVE for the whole copy. Plan it like a migration. The table is append-and-delete, so the free space is likely reused within days.
6. (a) ANALYZE: 50 + 0.1 × 50,000,000 = 5,000,050 changed rows. VACUUM: 50 + 0.2 × 50,000,000 = 10,000,050 dead rows. (b) 1 − 0.92 − 0.02 = 0.06 is left for the 20 − 4 = 16 other values. So 0.06 / 16 = 0.00375. Rows: 8,000,000 × 0.00375 = 30,000. One check remains: the code caps the result at the least common MCV's frequency. If that MCV holds less than 0.00375, the estimate is its frequency times 8,000,000 instead. (c) WARNING at 2,107,483,647: 607,483,647 more IDs, / 3,000 = 202,495 s = 2.3 days. Stop at 2,144,483,647: 644,483,647 / 3,000 = 214,828 s = 2.5 days. (d) Each failed attempt can block the queue for up to 200 ms. That is 6 × 200 = 1,200 ms in total, spread over the backoff pauses. No single pause is longer than 200 ms. The seventh attempt then holds the lock for its own work. (e) A read costs 2 and a dirtied page 20 more, so 22 per page. That gives 200 / 22 = 9 pages per nap. The ceiling is 200 / 0.002 s / 22 = 4,545 pages per second. At 8 kB a page that is 35.5 MB/s, shared by all workers. 200 GB is 204,800 MB. So the heap alone takes at least 204,800 / 35.5 = 5,769 s, about 1.6 hours. (f) Generic: (1 − 0) / 1,000 = 0.001, below the cap of 0.1, so 10,000 rows for any tenant. Custom, for the most common tenant: its MCV frequency, 0.1 × 10,000,000 = 1,000,000 rows. The generic plan is 100 times too low for that tenant.
7. One design, among several. (1) Expand: `ADD COLUMN worker_id text`, ACCESS EXCLUSIVE for milliseconds, with `lock_timeout` and retries. Old code is running. (2) Deploy code that writes both `owner` and `worker_id`, and reads `owner`. The claim UPDATE sets both columns in one statement, so the two stay equal under row locks. (3) Backfill `worker_id = owner` in batches of ids, each its own transaction, with a pause. Row locks only. (4) Deploy code that reads `worker_id`, still writing both. (5) Deploy code that writes only `worker_id`. Every step so far is additive. Undo means going back one code version. The reverse of step 1 drops `worker_id`, which loses only copied data. (6) Contract, in its own later release: `DROP COLUMN owner`, ACCESS EXCLUSIVE for milliseconds. This step cannot be undone. So it waits until no running or rollback-target code reads `owner`, and until a backup exists. A `RENAME COLUMN` would break the old code at once, so it is not used.

</details>

## Cheatsheet

One screen to keep open while you work.

<details><summary>Open the cheatsheet</summary>

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

</details>

## Sources

Every source the phase used, grouped as the phase groups them.

<details><summary>Open the sources</summary>

The course research fetched these sources on 2026-10-17. The writing, review and depth revision of this phase fetched the rest on 2026-10-18. Every URL was checked again with `check_urls.py` on 2026-10-18. Primary sources come first in each group.

#### PostgreSQL 14 documentation: plans and statistics

- **14.1 Using EXPLAIN** [https://www.postgresql.org/docs/14/using-explain.html](https://www.postgresql.org/docs/14/using-explain.html) Focus on: 14.1.1 for the cost formula of 458 and the plan change with selectivity, then the three join examples. 14.1.2 for `loops` and BUFFERS, and 14.1.3 for the readings that are not errors. Read it before E4. The examples come from 9.3 sources, so your numbers differ a little.
- **EXPLAIN, PostgreSQL 14 and 18** [https://www.postgresql.org/docs/14/sql-explain.html](https://www.postgresql.org/docs/14/sql-explain.html) [https://www.postgresql.org/docs/current/sql-explain.html](https://www.postgresql.org/docs/current/sql-explain.html) Focus on: the BUFFERS option in each. Off by default in 14, included with ANALYZE in 18.
- **72.1 Row Estimation Examples** [https://www.postgresql.org/docs/14/row-estimation-examples.html](https://www.postgresql.org/docs/14/row-estimation-examples.html) Focus on: every formula of section 4.2, worked on `tenk1`. The page says its outputs come from version 8.3, so check the method, not the digits.
- **14.2 Statistics Used by the Planner** [https://www.postgresql.org/docs/14/planner-stats.html](https://www.postgresql.org/docs/14/planner-stats.html) Focus on: `reltuples` and `relpages`, the 100-entry limit, and 14.2.2 on extended statistics and its limits.
- **72.2 Multivariate Statistics Examples** [https://www.postgresql.org/docs/14/multivariate-statistics-examples.html](https://www.postgresql.org/docs/14/multivariate-statistics-examples.html) Focus on: the `a = b = i % 100` table, before and after CREATE STATISTICS.
- **pg_stats** [https://www.postgresql.org/docs/14/view-pg-stats.html](https://www.postgresql.org/docs/14/view-pg-stats.html) Focus on: `null_frac`, `n_distinct`, the MCV columns, `histogram_bounds` and `correlation`.
- **20.7 Query Planning** [https://www.postgresql.org/docs/14/runtime-config-query.html](https://www.postgresql.org/docs/14/runtime-config-query.html) Focus on: the cost constants and the text on `random_page_cost`, then `geqo_threshold`, `from_collapse_limit` and `join_collapse_limit`.
- **20.7 Query Planning, PostgreSQL 10** [https://www.postgresql.org/docs/10/runtime-config-query.html](https://www.postgresql.org/docs/10/runtime-config-query.html) Focus on: the old `random_page_cost` text with "90%" and the SSD value 1.1. It is the source of a claim many posts still repeat. Read it only to see what changed.
- **20.4 Resource Consumption** [https://www.postgresql.org/docs/14/runtime-config-resource.html](https://www.postgresql.org/docs/14/runtime-config-resource.html) Focus on: `work_mem`, `hash_mem_multiplier`, `maintenance_work_mem` and `autovacuum_work_mem`.
- **ANALYZE** [https://www.postgresql.org/docs/14/sql-analyze.html](https://www.postgresql.org/docs/14/sql-analyze.html) Focus on: the note that the largest statistics target decides the sample size.
- **PREPARE** [https://www.postgresql.org/docs/14/sql-prepare.html](https://www.postgresql.org/docs/14/sql-prepare.html) Focus on: the Notes, with the five custom plans, the cost comparison, and the `$n` symbols of a generic plan. Read it before E13.
- **pg_prepared_statements** [https://www.postgresql.org/docs/14/view-pg-prepared-statements.html](https://www.postgresql.org/docs/14/view-pg-prepared-statements.html) Focus on: `generic_plans` and `custom_plans`, new in 14.
- **15.1 How Parallel Query Works** [https://www.postgresql.org/docs/14/how-parallel-query-works.html](https://www.postgresql.org/docs/14/how-parallel-query-works.html) Focus on: the Gather node and its workers, and "Workers Planned" in a plan. Then section 20.4 for `max_parallel_workers_per_gather` and `work_mem` per worker.
- **32.2 When to JIT?** [https://www.postgresql.org/docs/14/jit-decision.html](https://www.postgresql.org/docs/14/jit-decision.html) Focus on: the three cost thresholds, the JIT block in EXPLAIN, and the rule for generic plans.
- **F.30 pg_stat_statements** [https://www.postgresql.org/docs/14/pgstatstatements.html](https://www.postgresql.org/docs/14/pgstatstatements.html) Focus on: the setup with `shared_preload_libraries` and `compute_query_id`, the columns, and the example ranking. Read it before E14.
- **F.4 auto_explain** [https://www.postgresql.org/docs/14/auto-explain.html](https://www.postgresql.org/docs/14/auto-explain.html) Focus on: `log_min_duration`, `log_analyze` and its warning, `log_timing`, `sample_rate` and `log_level`.
- **20.9 Run-time Statistics** [https://www.postgresql.org/docs/14/runtime-config-statistics.html](https://www.postgresql.org/docs/14/runtime-config-statistics.html) Focus on: `track_io_timing` and `compute_query_id`.

#### PostgreSQL 14 documentation: maintenance, locks and DDL

- **25.1 Routine Vacuuming** [https://www.postgresql.org/docs/14/routine-vacuuming.html](https://www.postgresql.org/docs/14/routine-vacuuming.html) Focus on: 25.1.2 on space, and 25.1.3 on statistics and partitioned tables. Then 25.1.5 on wraparound, with its updated recovery steps, and 25.1.6 on the autovacuum thresholds. It is the most important page for section 4.5.
- **20.10 Automatic Vacuuming** [https://www.postgresql.org/docs/14/runtime-config-autovacuum.html](https://www.postgresql.org/docs/14/runtime-config-autovacuum.html) Focus on: the threshold, scale factor, worker and freeze settings, with their defaults. Then `autovacuum_vacuum_cost_limit`, and the sentence on sharing it among workers.
- **20.11 Client Connection Defaults** [https://www.postgresql.org/docs/14/runtime-config-client.html](https://www.postgresql.org/docs/14/runtime-config-client.html) Focus on: `lock_timeout`, `statement_timeout` and `idle_in_transaction_session_timeout`. Then the freeze ages, `vacuum_freeze_min_age`, `vacuum_freeze_table_age`, their multixact forms and `vacuum_failsafe_age`, and `session_preload_libraries`.
- **19.11 Client Connection Defaults, PostgreSQL 17** [https://www.postgresql.org/docs/17/runtime-config-client.html](https://www.postgresql.org/docs/17/runtime-config-client.html) Focus on: `transaction_timeout`, new in 17, and its warning about `postgresql.conf`.
- **20.8 Error Reporting and Logging** [https://www.postgresql.org/docs/14/runtime-config-logging.html](https://www.postgresql.org/docs/14/runtime-config-logging.html) Focus on: `log_autovacuum_min_duration`, −1 in 14, `log_lock_waits` and `log_temp_files`.
- **20.12 Lock Management** [https://www.postgresql.org/docs/14/runtime-config-locks.html](https://www.postgresql.org/docs/14/runtime-config-locks.html) Focus on: `deadlock_timeout`, the delay before a waiter checks for deadlock and cancels a normal autovacuum.
- **19.10 Vacuuming, PostgreSQL 18** [https://www.postgresql.org/docs/18/runtime-config-vacuum.html](https://www.postgresql.org/docs/18/runtime-config-vacuum.html) Focus on: `autovacuum_vacuum_max_threshold`, new in 18, and `autovacuum_worker_slots`.
- **28.2 The Statistics Collector, and 28.4 Progress Reporting** [https://www.postgresql.org/docs/14/monitoring-stats.html](https://www.postgresql.org/docs/14/monitoring-stats.html) [https://www.postgresql.org/docs/14/progress-reporting.html](https://www.postgresql.org/docs/14/progress-reporting.html) Focus on: `pg_stat_user_tables`, `pg_stat_database`'s temp columns, the `VacuumDelay` wait event, then `pg_stat_progress_vacuum` and `pg_stat_progress_create_index`.
- **pg_replication_slots, and 20.6 Replication** [https://www.postgresql.org/docs/14/view-pg-replication-slots.html](https://www.postgresql.org/docs/14/view-pg-replication-slots.html) [https://www.postgresql.org/docs/14/runtime-config-replication.html](https://www.postgresql.org/docs/14/runtime-config-replication.html) Focus on: `xmin` against `catalog_xmin`, then `hot_standby_feedback` and `max_slot_wal_keep_size`.
- **F.31 pgstattuple** [https://www.postgresql.org/docs/14/pgstattuple.html](https://www.postgresql.org/docs/14/pgstattuple.html) Focus on: `pgstattuple_approx`, and how it uses the visibility map to skip pages.
- **13.3 Explicit Locking** [https://www.postgresql.org/docs/14/explicit-locking.html](https://www.postgresql.org/docs/14/explicit-locking.html) Focus on: 13.3.1, each mode with the commands that take it and its conflicts. `locks.py` rebuilds its table from this page.
- **ALTER TABLE** [https://www.postgresql.org/docs/14/sql-altertable.html](https://www.postgresql.org/docs/14/sql-altertable.html) Focus on: the lock of each subcommand, `ADD COLUMN` with a default, and `SET NOT NULL` with a CHECK. Then `NOT VALID`, `VALIDATE CONSTRAINT`, and the notes on rewrites and DROP COLUMN.
- **CREATE INDEX** [https://www.postgresql.org/docs/14/sql-createindex.html](https://www.postgresql.org/docs/14/sql-createindex.html) Focus on: "Building Indexes Concurrently": the two scans, the wait, the invalid index, and the limit on partitioned tables.
- **REINDEX** [https://www.postgresql.org/docs/14/sql-reindex.html](https://www.postgresql.org/docs/14/sql-reindex.html) Focus on: the paragraph that compares REINDEX with dropping and creating the index. It gives the table lock and the index lock, which section 13.3.1 summarizes as ACCESS EXCLUSIVE.
- **5.11 Table Partitioning** [https://www.postgresql.org/docs/14/ddl-partitioning.html](https://www.postgresql.org/docs/14/ddl-partitioning.html) Focus on: 5.11.1 for the benefits, 5.11.2.2 for ATTACH and DETACH, and 5.11.2.3 for the limitations. Then 5.11.4 for pruning, and 5.11.6 for the number of partitions.
- **Release notes 9.5.0, 11.0, 12.0 and 14.0** [https://www.postgresql.org/docs/release/9.5.0/](https://www.postgresql.org/docs/release/9.5.0/) [https://www.postgresql.org/docs/release/11.0/](https://www.postgresql.org/docs/release/11.0/) [https://www.postgresql.org/docs/release/12.0/](https://www.postgresql.org/docs/release/12.0/) [https://www.postgresql.org/docs/release/14.0/](https://www.postgresql.org/docs/release/14.0/) Focus on: the lower foreign-key lock in 9.5, and the constant default without a rewrite in 11. Then `SET NOT NULL` without a scan and `REINDEX CONCURRENTLY` in 12. In 14: the wider wraparound margins, `vacuum_failsafe_age`, Memoize, the lower `vacuum_cost_page_miss`, B-tree bottom-up deletion and the `pg_prepared_statements` counters.
- **Release notes 13.0, 15.0, 16.0, 17.0 and 18.0** [https://www.postgresql.org/docs/release/13.0/](https://www.postgresql.org/docs/release/13.0/) [https://www.postgresql.org/docs/release/15.0/](https://www.postgresql.org/docs/release/15.0/) [https://www.postgresql.org/docs/release/16.0/](https://www.postgresql.org/docs/release/16.0/) [https://www.postgresql.org/docs/release/17.0/](https://www.postgresql.org/docs/release/17.0/) [https://www.postgresql.org/docs/release/18.0/](https://www.postgresql.org/docs/release/18.0/) Focus on: HashAggregate spilling and B-tree deduplication in 13. `hash_mem_multiplier` 2.0 and `log_autovacuum_min_duration` 10min in 15. `EXPLAIN (GENERIC_PLAN)` and delay settings honoured per block in 16. The 1GB vacuum memory limit removed, and `transaction_timeout`, in 17. `autovacuum_vacuum_max_threshold` in 18.

#### PostgreSQL source

- **costsize.c, REL_14_24** [https://github.com/postgres/postgres/blob/REL_14_24/src/backend/optimizer/path/costsize.c](https://github.com/postgres/postgres/blob/REL_14_24/src/backend/optimizer/path/costsize.c) Focus on: `clamp_row_est` at lines 199 to 215, and `cost_seqscan` from 226. Then the index heap cost at 662 to 729, and Mackert and Lohman at 840 to 900. The bitmap cost per page is at 1006 to 1008. `cost_model.py` cites each line.
- **selfuncs.c, REL_14_24** [https://github.com/postgres/postgres/blob/REL_14_24/src/backend/utils/adt/selfuncs.c](https://github.com/postgres/postgres/blob/REL_14_24/src/backend/utils/adt/selfuncs.c) Focus on: `var_eq_const` from line 292. Its branch for a value outside the MCV list is at lines 405 to 432. Then `genericcostestimate` from line 6464.
- **explain.c, REL_14_24** [https://github.com/postgres/postgres/blob/REL_14_24/src/backend/commands/explain.c](https://github.com/postgres/postgres/blob/REL_14_24/src/backend/commands/explain.c) Focus on: line 1619, where rows are divided by loops, and the JSON key names that `explain_tools.py` reads.
- **analyze.c, REL_14_0** [https://github.com/postgres/postgres/blob/REL_14_0/src/backend/commands/analyze.c](https://github.com/postgres/postgres/blob/REL_14_0/src/backend/commands/analyze.c) Focus on: line 1919, `stats->minrows = 300 * attr->attstattarget;`.
- **selfuncs.h and cost.h, REL_14_0** [https://github.com/postgres/postgres/blob/REL_14_0/src/include/utils/selfuncs.h](https://github.com/postgres/postgres/blob/REL_14_0/src/include/utils/selfuncs.h) [https://github.com/postgres/postgres/blob/REL_14_0/src/include/optimizer/cost.h](https://github.com/postgres/postgres/blob/REL_14_0/src/include/optimizer/cost.h) Focus on: the default selectivities at lines 34 and 37, and the cost defaults at lines 24 to 32.
- **varsup.c, REL_14_0** [https://github.com/postgres/postgres/blob/REL_14_0/src/backend/access/transam/varsup.c](https://github.com/postgres/postgres/blob/REL_14_0/src/backend/access/transam/varsup.c) Focus on: the error and its old hint at lines 129 and 131. Then the limits at lines 362, 378 and 392. Compare REL_13_0 and REL_18_0 by changing the tag.
- **index.c, REL_14_24** [https://github.com/postgres/postgres/blob/REL_14_24/src/backend/catalog/index.c](https://github.com/postgres/postgres/blob/REL_14_24/src/backend/catalog/index.c) Focus on: `reindex_index`. It locks the table in SHARE mode at line 3602, and the index in ACCESS EXCLUSIVE at line 3641.
- **lmgr README, REL_14_0** [https://github.com/postgres/postgres/blob/REL_14_0/src/backend/storage/lmgr/README](https://github.com/postgres/postgres/blob/REL_14_0/src/backend/storage/lmgr/README) Focus on: lines 364 and 386, the two rules of the lock queue.
- **postgres.c, REL_14_24** [https://github.com/postgres/postgres/blob/REL_14_24/src/backend/tcop/postgres.c](https://github.com/postgres/postgres/blob/REL_14_24/src/backend/tcop/postgres.c) Focus on: lines 3298 to 3307, the lock timeout and statement timeout errors with their SQLSTATEs, and line 3314, `canceling autovacuum task`.
- **plancache.c and prepare.c, REL_14_24** [https://github.com/postgres/postgres/blob/REL_14_24/src/backend/utils/cache/plancache.c](https://github.com/postgres/postgres/blob/REL_14_24/src/backend/utils/cache/plancache.c) [https://github.com/postgres/postgres/blob/REL_14_24/src/backend/commands/prepare.c](https://github.com/postgres/postgres/blob/REL_14_24/src/backend/commands/prepare.c) Focus on: `choose_custom_plan` at lines 1047 to 1077 and the planning charge at 1125 to 1127. Then `prepare.c` line 655, where EXPLAIN EXECUTE uses the same cache. `setrefs.c`, https://github.com/postgres/postgres/blob/REL_14_24/src/backend/optimizer/plan/setrefs.c , keeps every range-table entry at line 369.
- **allpaths.c, REL_14_24** [https://github.com/postgres/postgres/blob/REL_14_24/src/backend/optimizer/path/allpaths.c](https://github.com/postgres/postgres/blob/REL_14_24/src/backend/optimizer/path/allpaths.c) Focus on: `compute_parallel_worker`, lines 3750 to 3826. Read `costsize.c`'s `get_parallel_divisor`, lines 6060 to 6085, beside it.
- **vacuumlazy.c and vacuum.c, REL_14_24** [https://github.com/postgres/postgres/blob/REL_14_24/src/backend/access/heap/vacuumlazy.c](https://github.com/postgres/postgres/blob/REL_14_24/src/backend/access/heap/vacuumlazy.c) [https://github.com/postgres/postgres/blob/REL_14_24/src/backend/commands/vacuum.c](https://github.com/postgres/postgres/blob/REL_14_24/src/backend/commands/vacuum.c) Focus on: the autovacuum log line at lines 773 to 861, and the 6-byte dead-row list at 193. Then `vacuum_delay_point` in `vacuum.c`, lines 2205 to 2251.
- **autovacuum.c and proc.c, REL_14_24** [https://github.com/postgres/postgres/blob/REL_14_24/src/backend/postmaster/autovacuum.c](https://github.com/postgres/postgres/blob/REL_14_24/src/backend/postmaster/autovacuum.c) [https://github.com/postgres/postgres/blob/REL_14_24/src/backend/storage/lmgr/proc.c](https://github.com/postgres/postgres/blob/REL_14_24/src/backend/storage/lmgr/proc.c) Focus on: the thresholds at lines 3226 to 3255 and the cost balancing at 3003 to 3009. Then the activity text at 3314 to 3329. In `proc.c`, the autovacuum cancel at 1433 to 1489, and the lock-wait log line at 1624.
- **trigger.c, REL_14_24** [https://github.com/postgres/postgres/blob/REL_14_24/src/backend/commands/trigger.c](https://github.com/postgres/postgres/blob/REL_14_24/src/backend/commands/trigger.c) Focus on: line 1280, where DROP TRIGGER locks the table in ACCESS EXCLUSIVE mode.

#### The paper

- **How Good Are Query Optimizers, Really?, Leis, Gubichev, Mirchev, Boncz, Kemper and Neumann, PVLDB 9(3), 2015** [https://www.vldb.org/pvldb/vol9/p204-leis.pdf](https://www.vldb.org/pvldb/vol9/p204-leis.pdf) Focus on: section 2 for the setup, Table 1 for single-table q-errors, and Figure 3 with section 3.2 for joins. Then section 4.1 and Figure 6 for the nested-loop timeouts, and section 5 for the cost model. Its section 5 finds a median cost-model error of 38%, and 30% after tuning. All on PostgreSQL 9.4, with the data in memory. About 60 minutes. Read it after E4.

#### Books and course notes

- **PostgreSQL 14 Internals, Egor Rogov, Postgres Professional, 2023** [https://edu.postgrespro.com/postgresql_internals-14_en.pdf](https://edu.postgrespro.com/postgresql_internals-14_en.pdf) Focus on: 6.6 and 6.7 for the throttle and the vacuum log. Then 7.2 and 7.3 for freezing, and 16.3 for generic plans. Then 20.2 and 20.3 for heap fetches and lossy bitmaps, 21.2 for Memoize, and 22 and 23 for spills. It is free, and every example ran on PostgreSQL 14.
- **CMU 15-445/645, Fall 2025, lecture notes 11, 12 and 15** [https://15445.courses.cs.cmu.edu/fall2025/notes/11-sorting.pdf](https://15445.courses.cs.cmu.edu/fall2025/notes/11-sorting.pdf) [https://15445.courses.cs.cmu.edu/fall2025/notes/12-joins.pdf](https://15445.courses.cs.cmu.edu/fall2025/notes/12-joins.pdf) [https://15445.courses.cs.cmu.edu/fall2025/notes/15-optimization1.pdf](https://15445.courses.cs.cmu.edu/fall2025/notes/15-optimization1.pdf) Focus on: external merge sort and hash aggregation in 11, and the partitioned hash join in 12. Then section 11 of 15, the System R join search.

#### Production reports and migration guides

- **Manta postmortem of 2015-07-27, Joyent, archived copy** [https://web.archive.org/web/20220528044329/https://www.joyent.com/blog/manta-postmortem-7-27-2015](https://web.archive.org/web/20220528044329/https://www.joyent.com/blog/manta-postmortem-7-27-2015) Focus on: the timeline, the three-way lock interaction, and the cost-based delay during the outage. It does not name its PostgreSQL version.
- **BUG #19076: Generic query plan is extremely slow, pgsql-bugs, 2025-10-07** [https://www.postgresql.org/message-id/19076-4d897c04a44a9627%40postgresql.org](https://www.postgresql.org/message-id/19076-4d897c04a44a9627%40postgresql.org) Focus on: the two plans, and Laurenz Albe's reply on `plan_cache_mode`. PostgreSQL 17.6.
- **BUG #17540: Prepared statement: PG switches to a generic query plan which is consistently much slower, pgsql-bugs, 2022** [https://www.postgresql.org/message-id/17540-7aa1855ad5ec18b4@postgresql.org](https://www.postgresql.org/message-id/17540-7aa1855ad5ec18b4@postgresql.org) Focus on: the reporter's note on pgx and `PQexecPrepared`, and the database-wide workaround. PostgreSQL 14.4.
- **Django: Maybe disable PostgreSQL's JIT to speed up many-joined queries, Adam Johnson, 2023-11-09** [https://adamj.eu/tech/2023/11/09/django-disable-postgresql-jit/](https://adamj.eu/tech/2023/11/09/django-disable-postgresql-jit/) Focus on: the cost estimate that triggered JIT, and the `-c jit=off` fix. PostgreSQL 14. A personal blog, not peer reviewed.
- **Prepared statements, psycopg 3** [https://www.psycopg.org/psycopg3/docs/advanced/prepare.html](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html) Focus on: `prepare_threshold`, and when psycopg prepares a query by itself.
- **pg_repack documentation** [https://reorg.github.io/pg_repack/](https://reorg.github.io/pg_repack/) Focus on: the requirements, the disk space, and the two short exclusive locks.
- **Zero-downtime Postgres migrations, the hard parts, Chris Sinjakli, GoCardless** [https://gocardless.com/blog/zero-downtime-postgres-migrations-the-hard-parts/](https://gocardless.com/blog/zero-downtime-postgres-migrations-the-hard-parts/) Focus on: the 15-second outage and its three-transaction reproduction. Its foreign-key lock claim is for 9.4, as section 4.7 explains. The earliest archive copy is from 2015-10-09, and the page says it was edited in June 2024.
- **Zero-downtime Postgres migrations, a little help, GoCardless** [https://gocardless.com/blog/zero-downtime-postgres-migrations-a-little-help/](https://gocardless.com/blog/zero-downtime-postgres-migrations-a-little-help/) Focus on: the defaults of `ActiveRecord::SaferMigrations`, 750 ms and 1,500 ms.
- **Zero-downtime Postgres schema migrations need this: lock_timeout and retries, Nikolay Samokhvalov, postgres.ai, 2021-09-23** [https://postgres.ai/blog/20210923-zero-downtime-postgres-schema-migrations-lock-timeout-and-retries](https://postgres.ai/blog/20210923-zero-downtime-postgres-schema-migrations-lock-timeout-and-retries) Focus on: the three-session reproduction, the 50 ms timeout, and the thought experiment on retries without backoff.
- **Schema changes and the Postgres lock queue, Xata, 2024** [https://xata.io/blog/migrations-and-exclusive-locks](https://xata.io/blog/migrations-and-exclusive-locks) Focus on: the lock_timeout section. Its author was not recorded by the research.
- **Migration style guide, GitLab** [https://docs.gitlab.com/development/migration_style_guide/](https://docs.gitlab.com/development/migration_style_guide/) Focus on: the duration limits, the roll-forward rule, and the lock retry section. Read it beside the code below, because the two disagree.
- **with_lock_retries.rb, GitLab, master** [https://gitlab.com/gitlab-org/gitlab/-/blob/master/lib/gitlab/database/with_lock_retries.rb](https://gitlab.com/gitlab-org/gitlab/-/blob/master/lib/gitlab/database/with_lock_retries.rb) Focus on: `DEFAULT_TIMING_CONFIGURATION`, 41 pairs of a timeout and a pause, repeated 15 times. That is 615 attempts, whose timeouts and pauses add up to 2,673.75 s. The file's own comment says about 40 minutes.
- **Batched background migrations, GitLab** [https://docs.gitlab.com/development/database/batched_background_migrations/](https://docs.gitlab.com/development/database/batched_background_migrations/) Focus on: batch sizes, throttling on database health, and the estimate formula.
- **strong_migrations, Andrew Kane** [https://github.com/ankane/strong_migrations](https://github.com/ankane/strong_migrations) Focus on: the list of unsafe operations, "Setting NOT NULL on an existing column", "Backfilling data", and the timeout settings.
- **Online migrations at scale, Jacqueline Xu, Stripe, 2017** [https://stripe.com/blog/online-migrations](https://stripe.com/blog/online-migrations) Focus on: the four phases of dual writing. The post does not name its database.
- **Safe operations for high volume PostgreSQL, 2019 draft, James Coleman** [https://gist.github.com/jcoleman/1e6ad1bf8de454c166da94b67537758b](https://gist.github.com/jcoleman/1e6ad1bf8de454c166da94b67537758b) Focus on: the goals at the top, the ~2-second lock limit and the rollback rule, and the DROP COLUMN process. A draft gist. The published version returned HTTP 403 to the research.
- **Transaction ID Wraparound in Postgres, David Cramer, Sentry, 2015-07-23** [https://blog.sentry.io/transaction-id-wraparound-in-postgres/](https://blog.sentry.io/transaction-id-wraparound-in-postgres/) Focus on: the timeline and the recovery by TRUNCATE. Its one-million margin is PostgreSQL 13 era, and its single-user advice is out of date.
- **What we learned from the recent Mandrill outage, Mailchimp, 2019** [https://mailchimp.com/what-we-learned-from-the-recent-mandrill-outage/](https://mailchimp.com/what-we-learned-from-the-recent-mandrill-outage/) Focus on: the warning in November 2018 and the vacuum estimates. By Eric Muntz, dated 2019-03-26.

#### A talk

- **Explaining the Postgres Query Optimizer, Bruce Momjian, Citus Con 2022** [https://www.youtube.com/watch?v=wLpcVM9qxV0](https://www.youtube.com/watch?v=wLpcVM9qxV0) Focus on: scan methods from 0:04:19, and join methods from 0:12:13 to 0:21:18. The times come from the video's chapter list, because the captions did not load.
- **Explaining the Postgres Query Optimizer, slides, Bruce Momjian** [https://momjian.us/main/writings/pgsql/optimizer.pdf](https://momjian.us/main/writings/pgsql/optimizer.pdf) Focus on: slides 13 to 29 for the plan per letter, and slides 30 to 37 for the three joins. The slide table has only 410 rows, so use the course research's 1,000,000-row table for switch points.

</details>
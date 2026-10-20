In Phase 3 you made the course's task queue keep its rules while many transactions ran at once. The order data of Phases 1 and 2 now also lives in PostgreSQL 17, the version you run at work, because the reports need SQL. The table `orders` holds 10 million orders, and `order_events` holds three events per order. A dashboard report counts the events of every pending order, per tenant. It takes 20 ms in staging, with 100,000 orders, and 9 seconds in production.

- 09:00  The last ANALYZE of `orders` runs, and almost no order is pending.

- 10:00  A payment provider fails, and 4,000,000 orders become pending in one hour.

- 11:00  The report's plan expects 42 pending rows, gets 4,000,000 and takes 9 s.

- 11:20  `CREATE INDEX` on `orders (status)` starts without `CONCURRENTLY`. Every write on `orders` waits, and SELECTs still run.

- 11:31  The index is built and writes resume. The report still takes 9 s.

The running case. Times and counts are an example, and the lab reproduces its shape at a smaller size.

Nothing in the query changed. The statistics still described the table before 10:00, and the new index stopped checkout without fixing the report. Both problems can be predicted. The planner works from statistics you control, and each migration statement takes a lock you can name in advance. Each half has also happened to a real team. Railway ran an index build without `CONCURRENTLY` on about 1 billion rows, and its pooler then filled every connection slot. RevenueCat moved to a new Aurora cluster without ANALYZE, and its statements got bad plans. This phase ends with the course's one-page storage note.

Every fact, default, log line and plan shape below is for PostgreSQL 17. Where 14 behaved differently and you may still meet it, one clause says so. Where 18 changes a recipe, one line says so.

What you must know, in five claims. Each one is taught below, in this order.

- **A plan goes wrong at the lowest node where the expected row count and the real row count differ.** Find the slow query, take the plan it really ran, and find its wrong node.

- **Row estimates use the statistics of the last ANALYZE, so a bulk change or a move leaves them wrong until the next ANALYZE.** Predict an estimate, and say when your driver's statement switches to a generic plan.

- **The planner prices scans, indexes and joins from row estimates, so a low estimate makes a slow join look cheap.** Explain a scan choice, pick an index shape, and price a 9-second join.

- **VACUUM removes only row versions that died before the oldest open snapshot, and frees their space without shrinking the file.** Find what holds cleanup back in the 17 log, see how far wraparound is, and drop old data by partition.

- **A schema change also blocks traffic while it waits for its lock, so every one needs a lock_timeout.** Run a NOT NULL migration with no failed request, and widen a key before it runs out.

## What you bring from Phases 2 and 3

- **Pages.** PostgreSQL reads and caches its files in pages of 8,192 bytes, in `shared_buffers`.

- **B-trees.** A B-tree index finds a key with one page read per level, 3 levels for 10 million keys, with the upper levels in 776 KiB.

- **The heap.** A row lives in the heap, the table's own file, and an index entry points at its page.

- **HOT updates.** A *HOT update*, a heap-only tuple update, stays on the row's page and adds no index entry. It works only when no indexed column changes and the page has free space.

- **Row locks.** A row lock lasts until its transaction ends, and a second writer of the row waits.

- **Table locks.** Every statement locks each table it uses, and a SELECT's `ACCESS SHARE` waits only for `ACCESS EXCLUSIVE`.

- **The soft block.** A request that waits for a lock also blocks later conflicting requests. `lock_timeout` is 0, no limit, by default.

The first four come from Phase 2 and the last three from Phase 3. Snapshots and multixacts from Phase 3 come back where they are used. Replication, backups and pooling are the next phase, Phase 5, and this lesson points to its parts where they meet a plan or a lock.

## Which node in the plan went wrong?

A plan is a tree of nodes. The leaves are scans of a table or an index, and the nodes above them join, sort or count rows. `EXPLAIN` prints each node's estimate: a *cost*, in units where reading one page in order costs 1.0, and the rows it expects. `EXPLAIN ANALYZE` also runs the query. It adds the time, the rows that came out and *loops*, the number of times the node ran.

```text
HashAggregate  (cost=325612.40..325622.40 rows=126 width=12) (actual time=9010.200..9011.000 rows=1000 loops=1)
  Group Key: o.tenant_id
  Buffers: shared hit=15400246 read=812004
  ->  Nested Loop  (cost=0.56..325611.77 rows=126 width=4) (actual time=0.060..7900.400 rows=12000000 loops=1)
        Buffers: shared hit=15400246 read=812004
        ->  Seq Scan on orders o  (cost=0.00..325250.00 rows=42 width=12) (actual time=0.020..2100.300 rows=4000000 loops=1)
              Filter: (status = 'pending'::text)
              Rows Removed by Filter: 6000000
              Buffers: shared hit=200246 read=4
        ->  Index Scan using order_events_order_id_idx on order_events e  (cost=0.56..8.59 rows=3 width=8) (actual time=0.001..0.001 rows=3 loops=4000000)
              Index Cond: (order_id = o.id)
              Buffers: shared hit=15200000 read=812000
Planning Time: 0.410 ms
Execution Time: 9012.551 ms
```

The report's plan from `EXPLAIN (ANALYZE, BUFFERS)`. It is an example plan, not a run, and its numbers follow the opening case. They assume that each updated row's new version fit on its own page, so the table file did not grow.

<details><summary>Predict: the Index Scan on order_events prints rows=3. How many rows did it return, and is 3 wrong?</summary>

It returned 3 × 4,000,000 = 12,000,000 rows, because it ran 4,000,000 times. Its estimate of 3 per run is right, because every order has three events. The wrong number is how often it ran, and another node decided that.

</details>

- Read each node's rows as an average per loop, so its total is rows times loops. PostgreSQL divides the row count by the loops before it prints it.

- Measure each gap with the *q-error*, the factor between the estimate and the true count. An estimate of 10 or of 1,000 for a true 100 both have a q-error of 10.

- Start at the leaves. The Seq Scan on `orders` expected 42 rows and returned 4,000,000, a q-error of 95,238.

- Stop at the lowest node with a large q-error, because every node above it inherits the error.

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

  "cost=325612 means 325 s."

"The slow node is the one with the largest time, the Nested Loop."

"Plain EXPLAIN shows the problem."

  Cost is in page units. Time is actual time: 9,012 ms here.

The wrong node is where est and actual first differ: the Seq Scan.

Plain EXPLAIN shows rows=42 and nothing to compare it with.

### What the numbers on a node mean

The cost of a sequential scan is the simplest formula. It is the pages times `seq_page_cost`, 1.0, plus the rows times `cpu_tuple_cost`, 0.01. A WHERE clause adds `cpu_operator_cost`, 0.0025, for each row it checks. The PostgreSQL 17 docs work it for their table `tenk1`, with 345 pages and 10,000 rows.

```text
no filter      345 x 1.0 + 10,000 x 0.01         = 445
with a filter  445 + 10,000 x 0.0025             = 470, printed as cost=0.00..470.00
```

The cost of an upper node includes the cost of all its children, so the top node carries the whole plan. The access-path section below uses these formulas to answer why the planner chose a sequential scan.

`BUFFERS` adds the page counts of each node. A `hit` is a page found in `shared_buffers`. A `read` missed and came from the operating system, which may still have it in its page cache, as Phase 2 showed. The count of an upper node also includes the pages of its children. On PostgreSQL 17, as on 14, you must ask for it as `EXPLAIN (ANALYZE, BUFFERS)`. PostgreSQL 18 adds it to every `EXPLAIN ANALYZE` by itself.

### Where you meet it, and what you see

You meet this the day a dashboard or an API call slows down while its code stayed the same. You take the query, run `EXPLAIN (ANALYZE, BUFFERS)` on it, and read the plan from the leaves up. A node whose actual rows are thousands of times its estimate is the sign. A second sign is an inner node with millions of loops and a large `hit` count, such as the 15,200,000 hits above. The decision it changes is where you put the fix. You fix the input of the lowest wrong node, its statistics, and not the node that took the most time.

`EXPLAIN ANALYZE` runs the statement for real. On an UPDATE or DELETE the rows change, and the statement takes its row locks while it runs. So run it inside `BEGIN` and `ROLLBACK`, and on a copy of a busy table.

### Two options new in PostgreSQL 17: SERIALIZE and MEMORY

EXPLAIN ANALYZE runs the query, but it throws the result rows away. It does not turn them into text for the client, and that work can be large. A jsonb document of agent state or a 1,536-dimension embedding is stored as *TOAST*, PostgreSQL's out-of-line storage for large values from Phase 2. Each such value must be fetched and converted before the client gets it. So a query can show 5 ms in EXPLAIN ANALYZE and take far longer for your application. Those numbers are an example.

- **EXPLAIN**plan and estimates only. Nothing runs

- **(ANALYZE)**runs the plan. Result rows are thrown away

- **(ANALYZE, SERIALIZE)**also converts every row to text, timed, in kB

- **(MEMORY)**also reports the memory the planner used

- **the application**all of the above, plus the network and the driver

What each EXPLAIN form measures on PostgreSQL 17. The gap between the SERIALIZE time and the application's time is the network and the client.

- `EXPLAIN (ANALYZE, SERIALIZE)` does the conversion and measures it. It adds one line at the end, `Serialization: time=<ms> ms  output=<size>kB  format=text`. It still sends nothing over the network, so network time stays out of it.

- `EXPLAIN (MEMORY)` adds `Memory: used=NkB  allocated=NkB` under `Planning:`. Use it when planning itself costs a lot, such as on a table with many partitions, which the partitioning section explains.

E15 in the lab runs both options on the lab's order table. Compare its `Serialization:` time with its execution time.

A plan you can read is still only the plan you made by hand. The next section finds the slow query among thousands, and takes the plan the application really ran.

<details><summary>Go deeper: the q-error in the lab's code, four readings that are not errors, the timing options, and the details of SERIALIZE</summary>

### The q-error in the lab's code

The lab reads plans as JSON, so that a script can compare the two numbers on every node. From `phase04_planning/explain_tools.py:138`:

```python
# from phase04_planning/explain_tools.py:138, q_error(). Docstring cut, logic unchanged
def q_error(est: float, actual: float) -> float:
    e, a = max(est, 1.0), max(actual, 1.0)
    return max(e / a, a / e)
```

Both sides are floored at 1, because the planner never estimates fewer than one row. That rule is `clamp_row_est` in `costsize.c`, and the estimates section shows a case where it decides the estimate. The `Node` class compares `Plan Rows` with `Actual Rows`, which are both per loop, and multiplies by `Actual Loops` only for the total.

### The numbers on one line

Each node prints two pairs, `cost=startup..total` and `actual time=startup..total`. The startup value is spent before the node returns its first row, and the total after its last row. Actual time is in milliseconds, and `width` is the expected average row size in bytes. PostgreSQL 18 prints the per-loop average with two decimals, such as `rows=0.50`, so a small average no longer rounds to 0.

In the example plan, the inner scan made 15,200,000 + 812,000 = 16,012,000 page accesses. That is about 4 per loop. It fits three B-tree levels for 10 million keys, as Phase 2 computed, plus one heap page. These are example numbers. If an order's three events sit on three pages, as in the lab, a probe reads three heap pages.

The 17 docs print 345 pages and 445 for `tenk1`. The 14 docs printed 358 pages and 458 for the same table, and the 17 docs still use that older copy in their row-estimation chapter. `cost_model.py --self-test` checks both.

### Four readings that are not estimation errors

- A node under `LIMIT` stops early. Its actual rows are lower than its estimate, and nothing is wrong.

- A merge join can stop reading one input early, and it can count re-read inner rows twice.

- `BitmapAnd` and `BitmapOr` nodes always report their actual row counts as zero.

- Timing has its own cost. The overhead that EXPLAIN ANALYZE adds can be significant, and network transfer to the client is not included.

### Two timing options

A `read` in BUFFERS can come from the OS page cache or from the disk, and the count cannot tell them apart. `track_io_timing` can. It is off by default, because it reads the clock on every I/O, and that may cause significant overhead on some platforms. When it is on, EXPLAIN with BUFFERS adds a line that starts `I/O Timings:`. On 17 the line splits the time by kind of buffer, as `I/O Timings: shared read=... write=..., local ..., temp ...`. On 14 it read `I/O Timings: read=... write=...`. Many reads with a small read time came from the page cache.

The other option goes the opposite way. `EXPLAIN (ANALYZE, TIMING FALSE)` keeps the actual rows and drops the clock reads of every node. The tool `pg_test_timing` measures the clock's cost on your machine.

### SERIALIZE and MEMORY in detail

`SERIALIZE` without a value means `TEXT`. `SERIALIZE BINARY` measures the binary format that some drivers ask for. The docs name two causes of a large conversion cost: output functions that are expensive, and TOASTed values that must be fetched from out-of-line storage. With `BUFFERS`, an indented `Buffers:` line under the Serialization line counts the pages that the conversion read, such as TOAST pages.

SERIALIZE needs ANALYZE. Without it, the server stops with `EXPLAIN option SERIALIZE requires ANALYZE`. MEMORY does not need ANALYZE. On 14 both options are unknown, and E15 stops with a lab error that says so.

</details>

<details><summary>Evidence</summary>

PostgreSQL 17 docs, section 14.1.1, for the cost units, the 345 pages, 445 and 470, and "the cost of an upper-level node includes the cost of all its child nodes". That is `perform.sgml` at REL_17_11, lines 182 to 199. Section 14.1.2 gives loops, "the actual time and rows values shown are averages per-execution", and the safe BEGIN and ROLLBACK form. Section 14.1.3 gives the four readings. `explain.c` at REL_17_11 divides rows by loops at line 1847, prints the I/O Timings line at lines 3819 to 3859, the Serialization line at line 1128 and the memory counters at line 3950. The SERIALIZE error is at lines 293 to 297. The EXPLAIN pages of the 17 and 18 docs give the BUFFERS defaults and the SERIALIZE wording, and `release-17.sgml` lines 15807 and 15818 add both options. `clamp_row_est` is `costsize.c` REL_17_11, lines 202 to 218. The q-error is from Leis and others, PVLDB 2015, section 3.1. `track_io_timing` is in section 19.9.

</details>

## How do you find that plan in production?

At work you must first find the query among thousands. Its plan in psql may also differ from the plan the application got, because the application sends other values and runs on other sessions. Two modules that ship with PostgreSQL 17 close that gap.

- **pg_stat_statements**which statement costs the most server time

- **auto_explain**the plan that statement really ran, with its values

- **est against actual**the lowest node where they differ

- **fix the input**the statistics, not the plan

### Step 1: find the statement

`pg_stat_statements` keeps totals per *normalized statement*, the query text with its constants replaced by symbols. It needs shared memory, so it must be listed in `shared_preload_libraries`, and a server restart is needed to add it. It also needs a query identifier, which the default `compute_query_id = auto` turns on when the module loads. Then run `CREATE EXTENSION pg_stat_statements` in the database you read from.

On Amazon RDS and Aurora you cannot edit `postgresql.conf`. You set `shared_preload_libraries` in a custom parameter group, because a default group cannot be changed. The parameter is static, so it shows `pending-reboot` until you reboot the instance. The AWS page on SQL statistics for RDS for PostgreSQL says that for PostgreSQL 11 or later "the database loads this library by default". That is vendor documentation for RDS. Aurora was not checked. Run `SHOW shared_preload_libraries` on your instance to confirm.

Two rankings answer two different questions:

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

- The first ranking shows where the server's time goes. The 9-second report would sit near its top.

- The second ranking is this course's own rule of thumb, and no source tests it. A statement whose plan flips between two shapes has a stddev far above its mean. The comment's section 4.2 is the estimates part of this lesson, where generic plans are taught.

- `temp_blks_written` above 0 means a sort or a hash spilled to disk, as the join section shows.

- PostgreSQL 17 adds `stats_since`, the time each row's counters started. Run `SELECT min(stats_since) FROM pg_stat_statements` to see how long a ranking covers before you trust it.

On RDS and Aurora, CloudWatch Database Insights shows the same server time from another side. Older pages and posts call this tool Performance Insights. It samples the active sessions every second, and its unit is the average number of active sessions. Each active session is on CPU or in a *wait event*, the named thing it waits for, such as a lock or a disk read. So the statement with the most load there is usually near the top of the `total_exec_time` ranking. That link between the two is inferred.

### Step 2: take the plan it ran

`auto_explain` logs the plan of every statement slower than `auto_explain.log_min_duration`, whose default of −1 logs nothing. With `log_analyze` on, it logs EXPLAIN ANALYZE output, so you get actual rows. Per-node timing then runs for every statement, logged or not, and the docs warn it "can have an extremely negative impact on performance". So turn the per-node clock off and sample:

```text
# postgresql.conf, or a custom parameter group on RDS. Verified setting names, PostgreSQL 17 docs F.3.1
session_preload_libraries = 'auto_explain'
auto_explain.log_min_duration = '500ms'
auto_explain.log_analyze = on
auto_explain.log_buffers = on
auto_explain.log_timing = off      # actual rows and buffers, no per-node clock
auto_explain.sample_rate = 0.1     # explain one statement in ten
```

The logged plan is the plan that ran. Since PostgreSQL 16 it also has a `Query Parameters` line with the values of `$1`, `$2` and so on. So you can replay the exact call. On 14 the log has no parameter values. `session_preload_libraries` takes effect only when a connection starts, so it needs no restart. Connections that are already open, such as a pool's, keep running without it, which is inferred from the same rule.

### Step 3: read a plan that ran with parallel workers and JIT

The lab turns two features off, so its plans stay serial and uncompiled. Your server has both on by default. So a plan from `auto_explain` looks different from the lab's.

- *Parallel query* splits a scan across a leader and 2 worker processes under a Gather node. Each node then shows `loops=3`, and its rows are an average per process. Compare its estimate times 2.4, not 3, with its actual rows times loops, because the leader does only part of a worker's share.

- A Gather above a partial aggregate is the one exception. On PostgreSQL 14 to 17 its estimate is the per-process estimate times the workers, 2, without the leader share. PostgreSQL 18 uses 2.4 there too.

- *JIT*, just-in-time compilation, turns the plan's expressions into machine code once the plan's cost passes 100,000. A wrong row estimate can push the cost past that, and then the compile can take longer than the query.

Adam Johnson saw this in a Django application on PostgreSQL 14. A query joined many tables, and PostgreSQL expected many rows where each join added few. The comment in his fix says "3.5 seconds with JIT vs 10 milliseconds without". His fix was the connection option `-c jit=off` for the application. The cause was again a wrong row estimate, and JIT only made it cost more.

### What it changes

A slow query report from users now has a fixed path. You find the statement by its server time, take its logged plan with its parameter values, and compare estimate and actual at each node. You do not tune a plan you made by hand in psql, because the application may have run a different one.

  Take the plan auto_explain logged, then fix the lowest node where estimate and actual differ.

  Reading per-loop rows as totals, or diagnosing your psql plan instead of the logged one.

  Run explain_tools.py on a pg_class join, then multiply the busiest node's rows by loops.

The exact command for that try is `uv run python phase04_planning/explain_tools.py --sql "select count(*) from pg_class c join pg_attribute a on a.attrelid = c.oid"`. The estimate of 42 itself is still unexplained, and the next section shows where it came from.

<details><summary>Go deeper: the rules of parallel plans, a real parallel plan read in five rules, the JIT thresholds and block, and more about the two modules</summary>

### Why the lab turns parallel query and JIT off

Every lab plan in this phase runs with `max_parallel_workers_per_gather = 0` and `jit = off`, set by `lab_settings()`. Parallel query changes how rows and loops read, and JIT's compile time would blur a before-and-after timing. So the lab's plans are serial and uncompiled. PostgreSQL 17 turns both on by default, as 14 and 18 do: `max_parallel_workers_per_gather` is 2, and `jit` is on. The release candidate of PostgreSQL 19 turns `jit` off by default, from the course's currency research.

### When the planner uses a parallel plan

A Gather node starts worker processes. Each worker runs the plan below the Gather on its own part of the table. The leader, the session's own process, also runs that part when it is not busy. The rows flow up to the Gather, which passes them on. Three rules decide whether the planner uses it, and they did not change between 14 and 17:

- The table must reach `min_parallel_table_scan_size`, 8MB, which is 1,024 pages. Each factor of 3 above that allows one more worker, up to `max_parallel_workers_per_gather`.

- Only the CPU part of a scan is divided. The divisor is the worker count plus a leader share of 1 − 0.3 × workers, so 2 workers give 2 + 0.4 = 2.4. The disk part is not divided, because most operating systems already prefetch pages read in order.

- The Gather adds `parallel_setup_cost`, 1000, plus `parallel_tuple_cost`, 0.1, for each row it passes up.

Apply these rules to the report's Seq Scan, which costs 325,250 serial:

```text
CPU part     10,000,000 rows x 0.0125           = 125,000
disk part    325,250 - 125,000                   = 200,250 pages
parallel     200,250 + 125,000 / 2.4 (52,083)    = 252,333
Gather       + 1,000 + 0.1 x 42 rows (4)         = about 253,337
serial                                            = 325,250
workers      200,250 pages, far above 1,024       = 2 allowed
```

So at the defaults this scan would most likely run as a Parallel Seq Scan under a Gather. That is inferred from the formulas and was not run.

### Reading a real parallel plan

This plan comes from PostgreSQL BUG #19076, reported on PostgreSQL 17.6. The section on generic plans returns to that report. Lines are removed, and the numbers are copied from the report:

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

- `loops=3` is the leader plus 2 workers. A node's actual rows are an average per process, so the parallel scan returned 288,122 × 3 = 864,366 rows in total.

- Its estimate is per process too, but it was divided by 2.4, not by 3. So compare 373,366 × 2.4 = 896,078 with 864,366. The q-error is 1.04. Read naively, 373,366 against 288,122 looks 1.30 off.

- The Gather sits above a partial aggregate, so on 17 its estimate is 9,672 × 2 = 19,344. PostgreSQL 18 would print 9,672 × 2.4 = 23,213. That 18 number is arithmetic from the code, not a run.

- The Hash node here is not parallel aware, and it shows the full 37,282 rows with `loops=3`. So each of the three processes built its own full hash table, which is inferred from those two facts. Its rows are not split, so compare them directly: 63,307 / 37,282 = 1.70.

- `work_mem` applies to each process on its own. A query with 4 workers may use up to 5 times as much CPU time, memory and I/O bandwidth as one with none. So this plan held three hash tables at once. If `Workers Launched` is below `Workers Planned`, the pool of worker processes was full, and the plan runs with fewer workers than expected, which may be inefficient.

`explain_tools.py` applies the first two rules to every node under a Gather. They fit scans and joins. A partial aggregate estimates groups per process, and one group can appear in every process, so read its q-error as rough. That is inferred from the planner's rules. Its `--server-defaults` flag keeps your server's settings, so E15 shows a parallel plan on the lab's own `p4_orders`.

### When JIT runs, and what it prints

The WHERE clause is one of the expressions JIT compiles. PostgreSQL uses LLVM, a compiler library, to do it. The planner decides from the total estimated cost of the plan:

  Total cost above | What JIT adds | Default

  `jit_above_cost` | compile the expressions | 100000

  `jit_inline_above_cost` | also inline small functions and operators | 500000

  `jit_optimize_above_cost` | also apply expensive optimizations | 500000

The example plan costs 325,612, which is above 100,000 and below 500,000. So its EXPLAIN ANALYZE would most likely end with a JIT block, without inlining or optimization. That is inferred from the thresholds, not run. JIT also needs a server built with LLVM. This course did not check whether your PostgreSQL 17 build has it, and without it JIT never runs. The 17 docs' sample shows the block. Since 17, the generation time also shows the part spent on deforming, the code that unpacks a row's columns:

```text
 JIT:
   Functions: 3
   Options: Inlining false, Optimization false, Expressions true, Deforming true
   Timing: Generation 1.259 ms (Deform 0.000 ms), Inlining 0.000 ms, Optimization 0.797 ms, Emission 5.048 ms, Total 7.104 ms
```

In JSON, 17 nests a `Generation` group with `Deform` and `Total` inside `Timing`. The outer `Total` key is the same as in 14, so `explain_tools.py` reads both. One more rule matters for prepared statements, which the next section explains. When a statement reuses one plan, the JIT decision uses the settings in effect when it was prepared.

### More about the two modules

PostgreSQL 17 renamed the column `blk_read_time` of `pg_stat_statements` to `shared_blk_read_time`. The AWS overview page says "By default, RDS enables Database Insights in Advanced mode". `auto_explain.log_parameter_max_length` is −1 by default, which logs each parameter value in full. A connection fails if a library in `session_preload_libraries` is not found, so check the name before you set it. E14 sets up both modules, and `find_slow.py` prints both rankings.

</details>

<details><summary>Evidence</summary>

pg_stat_statements: PostgreSQL 17 docs, section F.30, including that "a server restart is needed" to add it. The 17 column rename and `stats_since` are `pg_stat_statements--1.10--1.11.sql` at REL_17_11, lines 41 to 61. auto_explain: section F.3 and F.3.1, with the warning quoted above, and the parameter line at `auto_explain.c` REL_17_11, lines 29 and 406. `session_preload_libraries` is in section 19.11. The RDS parameter-group rules and the Performance Insights unit are from the AWS pages "Parameter groups" and "Database load", read by the course review. The lab's settings are in `lab_settings()`, `phase04_planning/explain_tools.py:394`. The parallel and JIT defaults are from sections 19.4 and 19.7. The worker rule is `compute_parallel_worker`, `allpaths.c` lines 4229 to 4276, and the divisor `get_parallel_divisor`, `costsize.c` lines 6380 to 6405, with the prefetching comment at lines 337 and 338 and the per-process division at line 346. The Gather above a partial aggregate is `cost_gather`, `costsize.c` lines 444 to 449, and `allpaths.c` lines 3074 and 3075, all at REL_17_11. The 18 rule is `compute_gather_rows()`. The parallel plan is from BUG #19076, reported on 2025-10-07. The JIT thresholds and the sample block are from section 30.2, and the block's shape from `explain.c` REL_17_11, lines 1011 to 1101. The Django case is Adam Johnson's post of 2023-11-09.

</details>

## Where did rows=42 come from?

An estimate is a row count times a *selectivity*, the fraction of rows a condition keeps. The row count is `reltuples` in `pg_class`. The selectivity comes from `pg_stats`, which *ANALYZE* fills from a random sample of 30,000 rows, however large the table is. Per column it keeps the *MCV list*, the most common values with each one's fraction of rows. It also keeps `n_distinct`, the number of distinct values, and `null_frac`, the fraction of NULLs. At 09:00 it stored this example row for `orders.status`.

```text
 null_frac | n_distinct | most_common_vals         | most_common_freqs
-----------+------------+--------------------------+---------------------------
         0 |         11 | {shipped,paid,created}   | {0.6,0.25,0.1499667}
```

- **orders, 10 M rows**ANALYZE reads a sample of 30,000

- **pg_stats**MCV list, n_distinct, null_frac, histogram

- **selectivity**by the operator's formula

- **rows=42**selectivity times reltuples

Where an estimate comes from. The sample is 300 times the statistics target, and the default target is 100.

<details><summary>Predict: reltuples is 10,000,000. What does WHERE status = 'paid' expect, and what does WHERE status = 'pending' expect? pending is not in the list.</summary>

For `paid`, 0.25 × 10,000,000 = 2,500,000 rows. For `pending`, about 42 rows, the number in the bad plan, because the list leaves almost nothing for the values outside it.

</details>

For a value outside the list, the planner spreads what the list leaves evenly over the other distinct values.

```text
MCV sum        0.6 + 0.25 + 0.1499667          = 0.9999667
left over      1 - 0.9999667 - null_frac 0     = 0.0000333   (1 / 30,000)
other values   n_distinct 11 - 3 MCVs          = 8
selectivity    0.0000333 / 8                   = 0.00000417
estimate       0.00000417 x 10,000,000         = 41.7, printed as rows=42
```

The 0.0000333 is one sampled row in 30,000 with a status outside the list. So the planner believed pending orders were rare, which was true at 09:00. The row assumes that the team set `n_distinct = 11` on `status`, because the application has 11 statuses. From this sample alone, ANALYZE would store about 4, by the Haas and Stokes formula in `analyze.c`, REL_17_11, lines 2584 to 2602.

### When the statistics go stale

Nothing in `pg_stats` changes until the next ANALYZE. One can run in three ways, and the opening case missed all three for an hour.

- **Autovacuum's ANALYZE** starts after 50 + 0.1 × `reltuples` changed rows, 1,000,050 for `orders`. The incident passed that within the hour.

- **But a worker must reach the table.** A launcher starts one worker per database each minute, and at most 3 workers run at once. Several large tables can keep all of them busy for a long period, so the table can wait. That this is why the case stayed stale for an hour is inferred, not shown.

- **A manual `ANALYZE orders`** reads only the sample, so it is fast on a large table, although this course did not time it. It takes a *SHARE UPDATE EXCLUSIVE* lock, a table lock that blocks neither reads nor writes, only other schema changes and VACUUM.

`CREATE INDEX` is not on that list. It updates `reltuples` and `relpages`, and it leaves the column statistics alone. So the team's new index left the estimate at 42, and the report stayed slow.

### Where you meet it, and what you see

You meet stale statistics after any change that moves many rows at once. Examples are a backfill, an import, a bulk status change in an incident, and a move to a new cluster. What you see is a scan node whose actual rows are many thousands of times its estimate, as in the opening plan. `pg_stat_user_tables` then shows a large `n_mod_since_analyze`, the rows changed since the last ANALYZE, and an old `last_autoanalyze`. The decision it changes is simple. Run `ANALYZE` on the table as the last step of every bulk load, backfill or bulk update, and do not wait for autovacuum.

### The same failure after a move to a new cluster

Logical replication and a dump and restore copy the rows. They do not copy `pg_statistic`, the catalog behind `pg_stats`. So the new cluster starts with no column statistics at all. RevenueCat's postmortem of its move shows the result:

- RevenueCat restored a snapshot to a new cluster and upgraded it from Aurora PostgreSQL 10 to 14. Then it replicated the new changes from production into it. The post says that the vacuum of one of the largest tables had not finished at the cutover. A major-version upgrade does not keep the statistics. That link to the upgrade is inferred, because the post does not name pg_upgrade.

- After the switch, its post says "High throughput queries become incredibly inefficient because ANALYZE was not run on our largest tables".

- Statements then used all database connections. The team added a statement timeout to the database user, then shed traffic with HTTP 503 responses.

- It took about one hour to tell cause from effect, and about three hours to find the root cause.

- A second fault came from the same move. Sequence values were not copied, so large tables got duplicate primary keys.

Its dry runs had no write traffic. The rule follows: after any move by logical replication or by dump and restore, run ANALYZE on every table before traffic arrives. The PostgreSQL 17 docs say the same for `pg_upgrade`: "optimizer statistics are not transferred by pg_upgrade". They name `vacuumdb --all --analyze-only`, and `--analyze-in-stages` to produce rough statistics quickly. PostgreSQL 18's `pg_upgrade` keeps the statistics, but its release notes add that "Extended statistics are not preserved". This query lists the tables that no ANALYZE has reached:

```sql
SELECT relname, n_live_tup, n_mod_since_analyze
  FROM pg_stat_user_tables
 WHERE last_analyze IS NULL AND last_autoanalyze IS NULL
 ORDER BY n_live_tup DESC;
```

### Two plan flips that ANALYZE fixed

**Clerk** had an outage in which over 95% of its traffic got HTTP 429 responses. The cause was a routine automatic ANALYZE on one of its tables. One column was 99.9996% NULL, and the sample found only NULLs, so the statistics said 100% NULL. The planner then expected no non-NULL rows from part of the query, but that part returned over 17,000. The query runs often, so those rows took nearly all the database's resources. At 17:27 UTC the team ran ANALYZE by hand, and the old plan came back. They then raised the table's statistics target, the setting that sizes the ANALYZE sample. This course's arithmetic shows why the sample missed the non-NULL values. A default sample of 30,000 rows holds only about 0.12 non-NULL values of such a column.

**Neon**'s control plane runs on PostgreSQL. One scheduled query on its `computes` table changed its plan and used a poor index. The table has tens of millions of rows of history and few active rows. The new plan scanned much of the table and saturated the database CPU. Because of that load, the `fetchEndpointWithCompute` queries went "from a few hundred milliseconds to over 100 seconds". The team "ran ANALYZE computes", and the plan came back. It then wrapped the expensive subquery in a materialized CTE, a WITH query that the planner plans on its own, which the join section explains. Neon's post is a vendor's report on its own system, and it says the cause of the plan change is not known.

### When two columns are correlated

The AND row of the formula table multiplies selectivities. The planner treats the conditions as independent, an assumption that does not hold when column values are correlated. The docs' example has 10,000 rows with `a = b = i % 100`:

- `WHERE a = 1 AND b = 1` gets 1% × 1% = 0.01%, so `rows=1`. The actual count is 100.

- After `CREATE STATISTICS ... (dependencies) ON a, b` and ANALYZE, the estimate is `rows=100`.

- `GROUP BY a, b` estimates 1000 groups against an actual 100, until the statistics object also has `ndistinct`.

The course research repeated this on PostgreSQL 14.24 and got the same numbers. The 17 docs print the same estimates for this example, so 17 is expected to match, although that was not run on 17. Functional dependencies help only with equality to constants and with IN lists of constants, from the docs, section 14.2.2.1.1. They do not help ranges, LIKE, or comparisons of two columns. In the order data, `tenant_id` decides `region`, so the same fix applies to a filter on both.

Try this now, after E4: run `psql -h /tmp -p 5432 -d storage_lab -c "select attname, n_distinct, most_common_vals, most_common_freqs from pg_stats where tablename = 'p4_orders'"`. Compute the estimate for one value by hand, then compare it with `EXPLAIN select * from p4_orders where status = 'paid'`.

All of this assumes the planner sees the value in the query. The next section shows the common case where it does not.

<details><summary>Go deeper: every estimate formula, the lab's extreme case, correlated columns, three more controls, and how wrong estimates are in practice</summary>

### The estimate formulas

A histogram here has buckets of equal frequency, so a value's position inside its bucket gives the fraction of rows below it. The worked numbers are the docs' own, on the table `tenk1`:

  Condition | Formula | Docs example

  `col = v`, v in the MCV list | the stored frequency of v | `stringu1 = 'CRAAAA'`: 0.003 x 10,000 = 30 rows

  `col = v`, v not in the list | (1 − sum of MCV frequencies − null_frac) / (n_distinct − number of MCVs) | `'xxx'`: 0.96966667 / 666 = 0.0014559, so 15 rows

  `col < v` | (whole histogram buckets below v + the linear fraction of v's bucket) / buckets | `unique1 < 1000`: (1 + 7 / 1004) / 10 = 0.100697, so 1007 rows

  `a AND b` | the product of the two selectivities | 0.100697 x 0.0014559 = 0.0001466, so 1 row

  `t1.x = t2.y`, no MCV lists | (1 − nf1)(1 − nf2) x min(1 / nd1, 1 / nd2). The docs show the unique case, max(rows1, rows2). The n_distinct form is selfuncs.c, lines 2630 to 2634 | 50 x 10,000 x 0.0001 = 50 rows

  no statistics at all | 0.005 for `=`, 0.3333 for `<` | `selfuncs.h`, REL_17_11, lines 34 and 37

The histogram leaves out the values in the MCV list. Its bounds are null when the MCV list accounts for the entire population. The code adds two rules to the second row. It divides only when n_distinct minus the MCV count is above 1. And the result is never more than the frequency of the least common MCV. `cost_model.py --self-test` checks the 42 arithmetic and the docs' own examples.

### The row count before ANALYZE

Both `reltuples` and `relpages` are as of the last VACUUM, ANALYZE or CREATE INDEX. The planner reads the table's current page count, and if it differs from `relpages`, it scales `reltuples` to match.

### The lab's version is more extreme

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

### Three more controls of the statistics

- **An n_distinct override.** ANALYZE estimates n_distinct from its 30,000-row sample. A column whose values each appear only a few times can come out far too low. `ALTER TABLE order_events ALTER COLUMN order_id SET (n_distinct = -0.3333)` sets it by hand. A negative value is a fraction of the rows, so −0.3333 means one distinct order id per three events. The option overrides the estimates of later ANALYZE runs, so it takes effect at the next ANALYZE, and it takes only SHARE UPDATE EXCLUSIVE. Join estimates divide by n_distinct, as the join row of the formula table shows. Whether the sample under-counts `order_id` here is inferred, not measured.

- **A per-table analyze threshold.** The counter that autovacuum compares with 50 + 0.1 × reltuples is `n_mod_since_analyze` in `pg_stat_user_tables`. In the 17 code it is `mod_since_analyze`, and in 14 the field was named `changes_since_analyze`. `ALTER TABLE orders SET (autovacuum_analyze_scale_factor = 0.01)` lowers the trigger for `orders` from 1,000,050 to 50 + 0.01 × 10,000,000 = 100,050 changed rows. The incident passed even that within minutes. So the setting shortens the stale window and does not remove it, which is inferred from the arithmetic.

- **The ends of the histogram.** A range condition can reach the first or last histogram bound. Then the planner does not trust the stale bound, and replaces that endpoint with the true column minimum or maximum. It reads the value from a plain B-tree index on the column, and on 17 it skips every other kind of index. PostgreSQL 18 accepts any index that can return values in order.

Here is the third control on an example. `created_at >= now() - interval '1 hour'`, with an index on `created_at`, gets a sensible estimate an hour after the last ANALYZE. The opening case's `status = 'pending'` gets no such help, because it is an equality on a value outside the MCV list. That comparison is inferred from the code, not run.

### A bulk change between two ANALYZEs

A backfill fills a new or changed column for existing rows, and it can change a column's values in minutes. Autovacuum reaches the table later, or never if it is off for that table, and every plan in between uses the old distribution. A per-table `autovacuum_analyze_scale_factor` makes the automatic ANALYZE come sooner on a large table. Raise the detail for one column with `ALTER TABLE ... ALTER COLUMN ... SET STATISTICS`, which also takes only `SHARE UPDATE EXCLUSIVE`. On PostgreSQL 18 a reload can raise `autovacuum_max_workers`, up to `autovacuum_worker_slots`, 16 by default. On 17 that setting changes only at server start. The docs also note that the daemon has no knowledge of whether its ANALYZE will lead to meaningful statistical changes.

### How wrong estimates are in practice

One well-known measurement ran 113 join queries on an IMDB data set of 3.6 GB, on PostgreSQL 9.4, with all data in memory:

- For single-table conditions, PostgreSQL's q-error had a median of 1.00 and a 90th percentile of 2.08. The 95th was 6.10, and the maximum 207.

- For joins, 16% of PostgreSQL's estimates with 1 join were off by a factor of 10 or more. That grew to 32% with 2 joins and 52% with 3, so the errors grow exponentially with the number of joins. Most of the estimates were too low.

So most single-table estimates are close, and errors multiply through joins. These numbers were not repeated on PostgreSQL 14 or 17. Treat them as the shape of the problem, not as your numbers.

</details>

<details><summary>Evidence</summary>

The sample size is `stats->minrows = 300 * stats->attstattarget;` at `analyze.c` line 1894, tag REL_17_11. The formulas are from the PostgreSQL 17 docs, section 68.1, which was 72.1 in the 14 docs. The out-of-list branch is also checked in `selfuncs.c`, REL_17_11, lines 409 to 436. The page scaling of `reltuples` is from section 68.1. The autovacuum analyze defaults are from sections 19.10 and 24.1.6, which also warn that several large tables can keep "all autovacuum workers" busy "for a long period". The ANALYZE lock is from section 13.3.1. That CREATE INDEX updates only `reltuples` and `relpages` is from section 14.2. The correlated example is from sections 14.2.2 and 68.2, and `planstats.sgml` REL_17_11, lines 512, 536, 568 and 581, print the same estimates. The course research ran it on 14.24 on 2026-10-17. The n_distinct override is from the 17 ALTER TABLE page and Rogov, "PostgreSQL 14 Internals", page 277. The counter mapping is at `system_views.sql` line 689, `pgstatfuncs.c` lines 79 and 80, and `autovacuum.c` lines 3068 and 3095, all REL_17_11. The histogram end rule is `selfuncs.c` REL_17_11, lines 1086 to 1092 and line 6197. The practice numbers are from Leis and others, PVLDB 2015, Table 1 and section 3.2. The RevenueCat case is its postmortem of its move on 2022-11-23, fetched on 2026-10-20. The pg_upgrade rule is from the 17 pg_upgrade page, and the 18 change from its release notes, line 8768. The Clerk case is from Clerk's postmortem of 2026-02-19 by Braden Sidoti, which names neither the table nor its statistics target. The figure of 0.12 is 0.000004 × 30,000, which assumes the default target of 100. The Neon case is from its post of 2025-05-30 about an event on 2025-05-16.

</details>

## Why does the sixth execution get a different plan?

ANALYZE fixes an estimate only when the planner can see the value. A *prepared statement* hides it: the server parses the query once and runs it many times with new values. Drivers create them without being asked. Each run uses a *custom plan*, made for its values, or a *generic plan*, made once for every value.

- The first five executions get custom plans, and the server keeps their average estimated cost.

- From the sixth, it uses the generic plan if that plan's cost is below the average. Then the generic plan keeps winning, because the average of the five no longer changes.

- The generic plan cannot see `$1`, so it estimates `col = $1` as (1 − null_frac) / n_distinct, an average over all values.

Send the report with `WHERE o.tenant_id = $1`, over 1,000 tenants and 10,000,000 orders. Every tenant then gets an estimate of 10,000 orders. A tenant with 10% of the orders, an example, really has 1,000,000, and it gets the plan of an average tenant. By the join arithmetic later in this lesson, that plan can be a nested loop.

PostgreSQL BUG #19076, on PostgreSQL 17.6, shows the failure. The application's driver created prepared statements, and the query filtered on `tenant_id = $1` and `status = $2`. Executions 1 to 5 ran a parallel Hash Join in 103.8 ms. From execution 6, the generic plan ran a Nested Loop in 7,179.9 ms, "even if I do not change the parameters". Its scan expected 354 rows and returned 864,365. ANALYZE and a statistics target of 1,000 did not help, because the statistics were fresh.

Top node time from BUG #19076 on PostgreSQL 17.6, copied from the report and not run.

The fix is `ALTER ROLE reporting SET plan_cache_mode = force_custom_plan`. It plans every run of the report's role, and other roles keep their planning savings. That use is inferred from the setting's scope.

### What you see when it happens

- In `pg_stat_statements`, the statement's `stddev_exec_time` is far above its mean, the second ranking of the section above.

- `EXPLAIN EXECUTE name(values)` shows the plan that the cache chose. A `$1` in it means generic.

- `SELECT name, generic_plans, custom_plans, from_sql FROM pg_prepared_statements` counts each kind in your own session. `from_sql` is false for a statement that a driver prepared through the protocol.

- PostgreSQL 16 and later have `EXPLAIN (GENERIC_PLAN)`. It shows the generic plan of a query that has `$1` and no values.

### Where you meet it: the driver and the pooler

The five custom plans are counted per prepared statement, inside one server session. Your code does not hold a server session, because your driver and your pooler do. So three things decide the execution at which your query meets a generic plan. They are the driver's threshold, the server's rule, and how the pooler shares server sessions.

Start with the driver. psycopg 3 prepares a query by itself once it has run more than `prepare_threshold` times on one connection, and the default is 5. So executions 1 to 5 are sent without a name, and execution 6 prepares the statement on the server. pgJDBC, the Java driver, has `prepareThreshold`, also 5 by default, and prepares on the fifth execution. Both drivers prepare through the wire protocol, not with SQL `PREPARE`.

  One query on one server session | psycopg 3, threshold 5 | pgJDBC, prepareThreshold 5

  sent unnamed, planned with the values each time | executions 1 to 5 | executions 1 to 4

  prepared on the server, custom plans 1 to 5 | executions 6 to 10 | executions 5 to 9

  first execution that can use the generic plan | execution 11 | execution 10

The whole table is inferred from the driver docs and the server rule, and was not run. That an unnamed statement gets a custom plan each time is inferred, because each one is parsed again and its plan starts with no history. E18 prints the counters after each execution, so you can check the table on your server.

Now the pooler. PgBouncer is the common pooler in front of PostgreSQL. In transaction mode, a server connection is given to a client only for one transaction. So the next transaction of the same client can run on another server connection.

- **A session `SET` does not survive.** In transaction mode, `SET`, SQL `PREPARE` and `DEALLOCATE`, `LISTEN` and session advisory locks do not work. So `SET plan_cache_mode` at the start of a request reaches one server connection and stays there for the next client.

- **Protocol prepared statements work from PgBouncer 1.21.** With `max_prepared_statements` above 0, PgBouncer prepares each query on the server connection that runs it, under its own name `PGBOUNCER_{unique_id}`. PgBouncer 1.24 turned this on by default, with a value of 200, so older releases had it off.

- **Every server connection keeps its own count.** A pool of 20 server connections makes up to 100 custom plans before every connection has switched. In that time some requests get the custom plan and some the generic one, which shows as the large stddev above. This point is inferred from the PgBouncer docs and the server rule, and was not run.

Amazon RDS Proxy is the managed pooler on AWS. It *pins* a client to one database connection when the session holds state, so that connection cannot be shared. For PostgreSQL the AWS page lists `SET` commands and the SQL commands `PREPARE`, `DISCARD`, `DEALLOCATE` and `EXECUTE`. It also lists temporary tables, cursors, `LISTEN`, loading a library such as `auto_explain`, `nextval` and `setval`, and session advisory locks. For every engine, a statement over 16 KB pins the session. The CloudWatch metric `DatabaseConnectionsCurrentlySessionPinned` counts pinned sessions. Whether protocol prepared statements pin a PostgreSQL session was not checked, because the AWS page says so only for MySQL.

### What it changes

  Goal | Through PgBouncer transaction mode | Through RDS Proxy

  force custom plans for one report | `ALTER ROLE reporting SET plan_cache_mode = force_custom_plan`. A session `SET` stays on one server connection, so the next transaction may miss it and another client may get it | the same `ALTER ROLE`. A session `SET` pins the session

  stop the driver from preparing one query | psycopg: `conn.execute(sql, params, prepare=False)` | the same

  use prepared statements at all | PgBouncer 1.21 or later, `max_prepared_statements` above 0. psycopg needs 1.22 or later | not checked for PostgreSQL. Watch the pinning metric

Two more rules belong to a generic plan. A partitioned table prunes its partitions only at executor start, which the partitioning section shows. A partial index needs the value too. So a generic plan cannot use the partial index of the index section below, while the first five custom plans can. Phase 5 teaches pooling in full in 5.7: the PgBouncer modes, what transaction mode breaks, and RDS Proxy pinning.

  Estimates use pg_stats from the last ANALYZE, and a generic plan uses an average.

  A new index for a bad estimate leaves the estimate wrong and blocks writes.

  Run E18's plan_cache.py with --via-driver, and find the first generic execution.

That try is E18 of the lab, which runs after E13. The estimate decides more than the switch to a generic plan. The next section asks what the planner does with a correct estimate when it picks how to read the table.

<details><summary>Go deeper: the plan cache code, the planning charge, two bug reports, psycopg behind PgBouncer, and Aurora's plan management</summary>

### The choice in the code

`choose_custom_plan()` in `plancache.c` picks between the two plans:

```c
/* from plancache.c, REL_17_11, lines 1082 to 1100. Comments cut, logic unchanged.
   The same code is at REL_14_24, lines 1059 to 1077 */
	if (plansource->num_custom_plans < 5)
		return true;                     /* true: make a custom plan */
	avg_custom_cost = plansource->total_custom_cost / plansource->num_custom_plans;
	if (plansource->generic_cost < avg_custom_cost)
		return false;                    /* false: use the generic plan */
	return true;
```

Each custom cost also carries a planning charge. The charge is 1000 × `cpu_operator_cost` × (range-table entries + 1). The range table is the plan's list of tables, plus one entry for each `JOIN` clause.

```text
two tables with JOIN ... ON   3 range-table entries
1000 x 0.0025                 = 2.5
charge                        2.5 x (3 + 1) = 10
```

Once the generic plan wins, the average of the five custom plans no longer changes. So the generic plan keeps winning, which is inferred from the code.

### Why a generic plan misestimates

It cannot see the value of `$1`. So `var_eq_non_const()` in `selfuncs.c` estimates `col = $1` as (1 − null_frac) / n_distinct, capped at the most common value's frequency. That is the average over all values.

   | Custom plan | Generic plan

  Made | for each execution, with its values | once, for any value

  Estimate for `tenant_id = ...` | the MCV list or the leftover formula | (1 − null_frac) / n_distinct

  In EXPLAIN | the value, such as `tenant_id = 7` | the symbol `$1`

  In `pg_prepared_statements`, since 14 | counted in `custom_plans` | counted in `generic_plans`

  Planning time | paid on every execution | paid once

### The two bug reports

In BUG #19076, the generic plan's inner index scan ran 864,365 loops. Laurenz Albe answered on the list that the choice of plan "is a heuristic". He guessed that the first five executions used values with few rows, which the report does not show. He suggested `plan_cache_mode = force_custom_plan` for that statement. BUG #17540, on PostgreSQL 14.4, has the same shape. Its reporter used pgx, a Go driver, and wrote that he "wasn't even aware I was using prepared statements". He measured the generic plan as "over 6500x slower", and set `force_custom_plan` for the whole database. So this is the opening case's failure, a nested loop picked from a low estimate, with a different cause. The statistics were fresh, and the generic plan's average estimate was wrong for this value.

### The settings

`plan_cache_mode` is `auto` by default. `force_custom_plan` plans every execution, and `force_generic_plan` never replans. The docs say the setting "is considered when a cached plan is to be executed", so a role-level setting applies to every session of that role. E13 shows the switch on the lab's data with `plan_cache.py`, which uses SQL PREPARE.

### The driver rule in psycopg's code

In psycopg 3.3.6, the version in `pyproject.toml`, the rule is `if count >= self.prepare_threshold or prepare:`, at `_preparing.py` line 73, with the default at line 37. pgJDBC's docs say it starts using server side prepared statements on the fifth execution.

### psycopg behind PgBouncer

psycopg needs three things to use prepared statements behind PgBouncer. It needs psycopg 3.2 or later, PgBouncer 1.22 or later with `max_prepared_statements` above 0, and libpq from PostgreSQL 17 or later. Without libpq 17, its docs say to set `prepared_max` to None. PgBouncer names each statement once per query text, so the same query from different clients shares one name.

### Aurora's plan management

On Aurora PostgreSQL, query plan management is the managed answer to a plan that changes. It keeps approved plans. Its overview page names "query parameter bindings" among the causes of plan regression. This course does not teach it further.

</details>

<details><summary>Evidence</summary>

The two kinds of plan and the five-execution rule are from the PostgreSQL 17 docs for PREPARE. The plan cache code and the planning charge are `plancache.c` REL_17_11, lines 1082 to 1100 and 1148 to 1150, and the kept join entry is `setrefs.c` line 411. The generic estimate is `var_eq_non_const()`, `selfuncs.c` REL_17_11, lines 512 to 526. `plan_cache_mode` is in section 19.7. BUG #19076 was reported on 2025-10-07, and BUG #17540 in 2022. The `pg_prepared_statements` counters are from the 14 release notes, and `EXPLAIN (GENERIC_PLAN)` from the 16 release notes. The driver thresholds are from the psycopg 3 docs and source and the pgJDBC docs. PgBouncer released 1.21.0 on 2023-10-16 and 1.24.0 on 2025-01-10, by its changelog. The other PgBouncer facts are from its features and config pages. The RDS Proxy list and metric are from the AWS page "Avoiding pinning an RDS Proxy". The partial-index rule is from the 17 docs, section 11.8. Query plan management is from the AWS Aurora overview page.

</details>

## Why did the planner choose a sequential scan over the index?

After ANALYZE, the planner knows that 40% of the orders are pending. It still ignores the new index on `status`, and a teammate calls that a bug. It is the cheapest plan by the planner's own arithmetic. The planner prices four ways to read a table. A page read in order costs `seq_page_cost`, 1.0, and a page read out of order costs `random_page_cost`, 4.0.

  Path | What it reads

  Seq Scan | every heap page in file order, and checks each row against the filter

  Index Scan | index entries in key order, then each row's heap page, so a page can be read many times

  *Bitmap Heap Scan* | the index first, then the matching pages sorted into file order, each needed page once

  *Index Only Scan* | the index only, for pages that the *visibility map*, a per-page flag kept by VACUUM, marks all-visible

<details><summary>Predict: 1,000,000 narrow rows sit in 9,346 pages, with a B-tree on a column x of random values. For WHERE x < k, which plan wins at one row, 1%, 40% and 45%?</summary>

Index Scan, Bitmap Heap Scan, Bitmap Heap Scan, then Seq Scan at 45%. The course research measured this on PostgreSQL 14.24 at the defaults, with the data in memory. The cost functions have the same logic at the 17 tag. So 17 is expected to choose the same plans, but that was not run on 17.

</details>

Each row costs 0.0125 of CPU in both scans: 0.01 for the row and 0.0025 for the filter.

- The Seq Scan reads every page once: 9,346 × 1.0 + 1,000,000 × 0.0125 = 21,846.

- At 40%, the bitmap reads all 9,346 pages at 1.0 each, plus CPU for its index and rows: 21,338.

- At 45%, it pays CPU for more rows: 22,839, now above the Seq Scan.

- A plain Index Scan pays a random page per row on an uncorrelated column, 48,276 at 40%.

Estimated cost by the lesson's cost model, worked by hand and not timed.

These switch points belong to this table, and not to PostgreSQL. The column's *correlation*, how closely the physical row order follows the column's order, moves them most. In index order, the Index Scan at 10% costs 3,664 against 12,347 for the bitmap, because its heap reads become one run in file order. Wider rows also move the switch, because they mean more pages for the same rows.

So the planner chose the sequential scan for a reason. The condition kept 40% of a table whose order is unrelated to `status`, so every plan reads almost every page. On the research's table, 40% is a little below the switch, and the bitmap costs 2.3% less than the sequential scan. The `orders` table has wider rows and its own index size, so its switch can fall below 40%. That is inferred from the formulas, and not computed for `orders`.

### The failure: forcing the index

  Force the index for the whole application, because one report used a sequential scan.

```sql
ALTER DATABASE app SET enable_seqscan = off;
ALTER DATABASE app SET random_page_cost = 1.0;
```

At 40% the forced plan is the Index Scan, with a random heap read per row. At `random_page_cost` 1.0 the model prices it at 17,319, below the Seq Scan's 21,846. If those reads are not cached, the default 4.0 prices the same plan at 48,276.

  Fix the input that was wrong, then let the planner choose. Compare other plans in one session only.

```sql
ANALYZE orders;
SET enable_seqscan = off;   -- only to compare, then RESET
```

The `enable_*` settings do not remove a path. On 17 they add `disable_cost`, 1.0e10, to its cost, so the path looks very expensive. PostgreSQL 18 counts disabled nodes apart from the cost instead, and EXPLAIN marks such a node `Disabled: true`. The docs call this a crude tool for seeing other plans, and it is not a fix.

### Where you meet it: an index that only costs

An index that no plan uses still has a write cost, for the reason Phase 2 showed. An UPDATE adds an entry to every index of the table, unless it is a HOT update. An index on `status` makes every status change a non-HOT update, so every order change adds an entry to an index the planner ignores. You can find such indexes. `pg_stat_user_indexes` counts the scans of each index since the last statistics reset:

```sql
SELECT indexrelname, idx_scan, last_idx_scan, pg_size_pretty(pg_relation_size(indexrelid)) AS size
  FROM pg_stat_user_indexes
 WHERE idx_scan = 0
 ORDER BY pg_relation_size(indexrelid) DESC;
```

- An index with `idx_scan = 0` over weeks of normal traffic serves no plan. Check first that the counters cover a whole business cycle, such as a month-end report.

- `last_idx_scan`, new in PostgreSQL 16, gives the time of the last scan. So you can also find indexes that were used once and then never again.

- A unique index enforces a rule even with no scans, so keep it.

The reading of these columns is this course's rule, not a documented one.

### Where you meet it in an AI feature

An AI feature often runs `WHERE tenant_id = $1 ORDER BY embedding <=> $2 LIMIT 10` on a table with an HNSW index from pgvector. *HNSW* is a graph index for nearest-neighbour search. The planner then chooses between the B-tree on `tenant_id` and the HNSW index, by the same cost rules. The pgvector README says that with HNSW, "filtering is applied after the index is scanned". At the default `hnsw.ef_search` of 40 and a filter that keeps 10% of rows, "only 4 rows will match on average". So what you see is a search that asked for 10 results and got about 4. Your courses retrieval-internals and advanced-retrieval teach this in depth, with the planner's switch point between the two indexes.

### What you see when an index path is slower than its cost

Both show in EXPLAIN ANALYZE, and both explain an index path that is slower than its cost. They come from Rogov's runs on PostgreSQL 14:

- An Index Only Scan prints `Heap Fetches`. It counts the rows the scan checked in the heap, because their page was not marked all-visible. One run shows `Heap Fetches: 132109` on a new table, and `Heap Fetches: 0` after VACUUM, for the same 132,109 rows. So an index-only scan on a table that VACUUM has not reached reads the heap like an index scan.

- A Bitmap Heap Scan prints `Heap Blocks: exact=... lossy=...`. When the bitmap does not fit in `work_mem`, some of its parts keep only the page and not the row. Every row on a lossy page is checked again, and the plan counts the rejects as `Rows Removed by Index Recheck`. With `work_mem = '512kB'` one run shows `Heap Blocks: exact=5178 lossy=8269` and `Rows Removed by Index Recheck: 1145721`. With more memory, the same query showed `exact=13447`.

`explain_tools.py` prints all three keys for every node that has them.

Try this now: run `uv run python phase04_planning/cost_model.py --sweep`, then `uv run python phase04_planning/access_paths.py`. Compare the model column with the planner column, and find the row where they disagree, if any.

A plain B-tree on `status` was the wrong index for the 40% report. The next section asks which index is right for the queries that do need one.

<details><summary>Go deeper: the cost of each path, the research's full results, what moves the switch, heap fetches and lossy pages</summary>

### The predict, in more detail

The research's B-tree on `x` is 19 MB, and all settings were defaults. PostgreSQL 14.24 printed exactly `cost 21846.00` for the Seq Scan. The bitmap reads each of the 9,346 pages at 4.0 − 3.0 × √1 = 1.0. The Index Scan's heap part alone at 40% is 9,346 × 4.0 = 37,384. Between 40% and 45% the CPU per row decides.

### The cost of each path

The formulas are from `costsize.c` and `selfuncs.c` at REL_17_11, and the defaults from the PostgreSQL 17 docs. `cost_model.py` implements them, and its docstring names each line:

  Path | Heap pages read | Cost per heap page | CPU per row

  Seq Scan | all T pages | `seq_page_cost` 1.0 | `cpu_tuple_cost` 0.01 + 0.0025 per condition

  Index Scan | from the Mackert and Lohman formula, up to T | `random_page_cost` 4.0, moved toward 1.0 by correlation² | 0.01, plus 0.0075 per index entry

  Bitmap Heap Scan | each needed page once, at most T | 4.0 − 3.0 × √(pages read / T) | 0.0125, plus 0.0075 per index entry

  Index Only Scan | as Index Scan, times the share of pages not all-visible | as Index Scan | as Index Scan

The Mackert and Lohman formula estimates how many distinct pages N random row fetches touch, given the cache size `effective_cache_size`. When the table fits in that cache, it is 2TN / (2T + N), capped at T. The bitmap formula charges almost `random_page_cost` for a few scattered pages, and only `seq_page_cost` once it reads every page. From `phase04_planning/cost_model.py:198`:

```python
# from phase04_planning/cost_model.py:198, the body of bitmap_scan(). A two-line comment removed, logic unchanged
    tuples, idx = _index_part(sel, t, p)
    idx += 0.1 * p.cpu_operator_cost * tuples              # line 1127
    T = max(t.pages, 1.0)
    pf = (2.0 * T * tuples) / (2.0 * T + tuples)           # compute_bitmap_pages
    pf = T if pf >= T else math.ceil(pf)
    if pf >= 2.0:
        per_page = p.random_page_cost - (p.random_page_cost - p.seq_page_cost) * math.sqrt(pf / T)
    else:
        per_page = p.random_page_cost
    return idx + pf * per_page + tuples * (p.cpu_tuple_cost + quals * p.cpu_operator_cost)
```

### The arithmetic in full

T is 9,346 pages and N is 1,000,000 rows. The index has about 2,432 pages, which is 19 MB in 8 kB pages.

```text
Seq Scan       9,346 x 1.0 + 1,000,000 x 0.0125                 = 21,846
Bitmap 40%     index 973 pages x 4.0 = 3,892, + 400,000 x 0.0075 = 3,000,
               + 100 for the bitmap. Mackert and Lohman gives more than T,
               so all 9,346 pages at 4.0 - 3.0 x sqrt(1) = 1.0. Rows 400,000 x 0.0125 = 5,000
               3,892 + 3,000 + 100 + 9,346 + 5,000                = 21,338 (+0.4 B-tree descent)
Bitmap 45%     4,380 + 3,375 + 112.5 + 9,346 + 5,625               = 22,839
Index Scan 40% heap 9,346 x 4.0 = 37,384 (correlation near 0)
               + 3,892 + 3,000 for the index + 4,000 for the rows  = 48,276
```

The forced plan of the compare box, at `random_page_cost` 1.0, is 973 + 3,000 for the index, 9,346 for the heap and 4,000 for the rows, so about 17,319.

### What the research measured

These are the planner's choices by estimated cost, on the table above. It has about 107 rows per page and `correlation(x) = 0.0004`:

  Rows selected | Plan

  1 row | Index Scan

  0.001% to 40% | Bitmap Heap Scan

  45% and above | Seq Scan

  `SELECT x` only, 0.1% to 50% | Index Only Scan

  `random_page_cost = 1.1`, at 30% and 50% | Index Scan

The model reproduces the first three rows by hand, and `cost_model.py --self-test` asserts each of them. At `random_page_cost = 1.1` and 50%, the model also picks the Index Scan, at 20,369 against 20,809 for the bitmap. The model leaves out small terms, so treat any gap under a few percent as a tie. At 30% it puts the bitmap 0.7% below the Index Scan that the research saw. The research did not time the queries, so the cheapest cost was not shown to be the fastest plan. It inferred that row width, correlation and the cache settings move the switch, and E3 lets you change each one.

### Why no parallel plan won

The research ran at all defaults, so parallel plans were allowed, and none won. By the third parallel rule of the production section, its Gather node costs 0.1 per row it hands on. At 40%, a parallel scan would cost 9,346 + 12,500 / 2.4 = 14,554. The Gather adds 1,000, and 400,000 × 0.1 = 40,000. That is 55,554 against the bitmap's 21,338. So a parallel plan wins when the work below the Gather removes most rows, as a count or a selective filter does. This conclusion comes from the cost formulas, and nobody ran it.

### What moves the switch, in detail

- **Correlation.** `pg_stats.correlation` is the statistical correlation between the physical row order and the logical order of the column values. Near 1 or −1, an index scan is estimated to be cheaper, because its heap reads become one sequential run.

- **`random_page_cost`.** The PostgreSQL 14, 17 and 18 docs keep the default at 4.0. It is that low because most random reads, such as indexed reads, are assumed to be in cache. The "90%" cached text and the SSD value "1.1" that many blogs quote were in the docs up to 14.19, 17.6 and 18.0. The minor releases 14.20, 17.7 and 18.1 removed that text. At REL_17_11, a grep of config.sgml finds "1.1" only in "TLSv1.1". So the docs of 17.6 and older still give the old advice.

- **`effective_cache_size`.** The default is 4GB, and it enters the Mackert and Lohman formula for index scans. The research set it to 64MB and saw no plan change from 0.1% to 30% on this table.

- **Row width.** The seq scan cost grows with pages, and the index cost grows with rows, so wider rows move the switch.

</details>

<details><summary>Evidence</summary>

The research table was built by the course research on PostgreSQL 14.24 on 2026-10-17, at all defaults with the data in memory, and its plan table is that run. A diff of the cost functions against REL_17_11 found the same logic. The bitmap sorting is from the PostgreSQL 17 docs, section 14.1.1, which call the bitmap "the mechanism that does the sorting". The visibility map is from section 24.1.4. The cost defaults are from section 19.7.2. The correlation definition is from the `pg_stats` docs. The `random_page_cost` text is from the PostgreSQL 14, 17, 18 and 10 docs. `disable_cost` is `costsize.c` REL_17_11, line 130, and `Disabled: true` is `explain.c` REL_18_6, line 1882. The `pg_stat_user_indexes` columns are `system_views.sql` REL_17_11, line 798, and section 27.2, and `last_idx_scan` is new in 16 by `release-16.sgml` REL_16_0, line 680. Heap fetches and lossy pages are from Rogov, "PostgreSQL 14 Internals", sections 20.2 and 20.3. The pgvector quotes are from its README at v0.8.7, lines 450 to 453 and 480 to 487, read by the course review.

</details>

## Which index fits the query, and what does it cost on every write?

The 40% report needs no index, but other queries on `orders` do. The queue query "the oldest pending orders" runs all day, and a plain B-tree on `status` is the wrong shape for it too. A B-tree holds one entry per row, sorted by the key. PostgreSQL has other index shapes, and each one changes one of three things. It changes which rows get an entry, what the entry holds, or how many rows one entry stands for. Each shape wins for one query shape, and each one costs something on every write.

  Shape | What it changes against a plain B-tree

  *partial* | entries only for rows that match a WHERE predicate

  *composite* | one entry per row, sorted by several columns in a fixed order

  *covering* | extra columns stored in the entry, so no heap visit is needed

  *expression* | the entry holds a computed value, such as `lower(email)`

  *GIN* | one entry per element: jsonb keys and values, array items

  *BRIN* | one entry per 128 pages: the minimum and maximum of that block range

On a normal day `orders` has 10,000,000 rows and about 10,000 pending, an example count. Three queries run all day, and this section finds the index for each:

- `SELECT id FROM orders WHERE status = 'pending' ORDER BY created_at LIMIT 100`, the queue query.

- `SELECT count(*) FROM orders WHERE tenant_id = $1 AND status = 'pending'`, per tenant.

- `SELECT * FROM order_events WHERE created_at >= $1 AND created_at < $2`, one hour of events from a table that only receives inserts, in time order.

### Partial: few hot rows, such as a queue

A partial index has entries only for rows that satisfy its predicate, a WHERE clause in `CREATE INDEX`.

```sql
CREATE INDEX CONCURRENTLY orders_status ON orders (status);
```

One entry for each of the 10,000,000 rows, and the planner must still sort or filter by `created_at`.

```sql
CREATE INDEX CONCURRENTLY orders_pending_by_age ON orders (created_at)
  WHERE status = 'pending';
```

Entries only for pending rows, already in `created_at` order. The query reads the first 100 entries and stops.

On the example day the partial index holds about 10,000 entries against 10,000,000, about 1,000 times fewer. That ratio is arithmetic on entries, not a measured size. It also speeds up writes, because rows outside the predicate never touch it. During the incident, though, 4,000,000 rows were pending, so the partial index held 40% of the table and the report still got a sequential scan. A partial index helps the queries that select few rows, and it does not fix a 40% filter. Three limits come with it:

- **The predicate is matched at planning time.** The docs say "parameterized query clauses do not work with a partial index". So a generic plan for `status = $1` cannot use it, although the first five custom plans can. Then the server takes the generic plan only if it looks cheaper than the average custom plan, or when `plan_cache_mode` is `force_generic_plan`. If it does, the queue query falls back to another path, and its plan no longer names the partial index. Write the literal `'pending'` in the query text, as a constant and not a parameter.

- **A status change is never a HOT update.** PostgreSQL counts a column named in a partial-index predicate as indexed. So every UPDATE of `status` is a non-HOT update, even when no index stores `status`. A non-HOT update adds an entry to every index whose predicate the new row version meets. A row that leaves `pending` gets no new entry in the partial index.

- **Many partial indexes are not partitions.** The docs call a set of partial indexes, one per category, "a bad idea", because the planner tests each one. Use one index with the category as its first column, or the partitioning section's method.

Where you meet it: the queue tables of agent runners and job systems. Phase 3's `tq_tasks` claims with `WHERE state = 'queued' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED`. Its lab already builds that claim's index, `tq_tasks_queued ON tq_tasks (id) WHERE state = 'queued'`. A job queue that finds work with a sequential scan reads past every dead row on each claim. The VACUUM section shows a published outage of that kind.

### Composite: the column order is the design

An index on `(tenant_id, status)` sorts by `tenant_id` first, then by `status` inside each tenant. Equality on the leading columns limits the part of the index that is scanned. Conditions on later columns are checked in the index, but they do not make that part smaller.

  Query | (tenant_id, status) | (status, tenant_id)

  `tenant_id = 7 AND status = 'pending'` | both columns bound | both columns bound

  `tenant_id = 7` | leading column bound | whole index

  `status = 'pending'` | whole index | leading column bound

A whole-index scan usually loses to a sequential scan. So choose the order from the queries, not from how selective each column is. "Put the most selective column leftmost" is a common belief. Markus Winand's "Use The Index, Luke" lists it as a myth, on its page "Myth: Put the most selective column leftmost". The docs add that indexes with more than three columns are unlikely to help unless the table's use is very fixed.

### Covering, expression, GIN and BRIN

- **Covering, with `INCLUDE`.** `CREATE INDEX ON orders (tenant_id) INCLUDE (amount_cents)` stores `amount_cents` in each entry, outside the search key. Then `SELECT sum(amount_cents) FROM orders WHERE tenant_id = 7` can run as an Index Only Scan. It helps only on a table that changes slowly, because a page that is not all-visible still sends the scan to the heap. An included column also blocks HOT updates of that column, verified from the HOT rules and `relcache.c`.

- **Expression.** An index on `lower(email)` serves `WHERE lower(email) = 'user77@example.com'`, and a plain index on `email` does not. It computes the expression on every insert and non-HOT update. ANALYZE also gathers statistics on the expression, so run ANALYZE after you create one. Read the SQL that your ORM sends for a case-insensitive filter, in the logs of the production section, before you choose the expression.

- **GIN, the inverted index.** One row adds one entry per element. With `jsonb_ops`, that is each key and each value of a jsonb document. With `jsonb_path_ops`, it is each value. For an array, it is each item. It serves agent state or event metadata filtered with `attrs @> '{"plan": "pro"}'`. Use the operator class `jsonb_path_ops` when you need only `@>`, because it is usually much smaller. The write cost is the part people miss, and the next paragraph explains it.

- **BRIN, the block range index.** It stores the minimum and maximum of each range of 128 pages. It fits a timestamp on a table that only receives inserts in time order, whose `correlation` in `pg_stats` is near 1. A table whose rows are updated and moved does not fit it.

GIN's write cost needs one more step. Inserting or updating one row can cause many inserts into the index. So GIN puts new entries in a pending list first, because `fastupdate` is on by default. The list moves into the main index at VACUUM, at autoanalyze, or when it passes `gin_pending_list_limit`, 4MB by default. What you see is a search that slows as the list grows, and one update that runs the whole cleanup and is much slower than the others. The docs advise turning `fastupdate` off when "consistent response time is more important than update speed".

BRIN's size follows from its rule. `order_events` at 150,000 pages, the example size of the join section, gets 150,000 / 128 = 1,171.9, so 1,172 entries. A B-tree on the same column has 30,000,000, one per row. A query for one hour reads the ranges whose minimum and maximum overlap the hour, then rechecks every row in them. Its plan therefore shows a Bitmap Heap Scan, and a `Rows Removed by Index Recheck` line counts the rows it threw away. New ranges are not summarized until a VACUUM runs, so the newest rows are read in full until then. That reading is inferred from a code comment.

### What each shape costs, side by side

  Shape | Wins for | Cost on writes | Fails when

  partial | a few hot rows, such as a queue | entries only for matching rows. The predicate column blocks HOT | the query sends the value as a parameter of a generic plan

  composite | equality on the leading columns | one index instead of two | the query skips the leading column

  covering | index-only scans on a slowly changing table | wider index. Included columns block HOT | the visibility map is not set, so heap fetches return

  expression | a computed filter, such as `lower(email)` | the expression on every insert and non-HOT update | the query writes the expression differently

  GIN | elements of jsonb and arrays | many entries per row. The pending list makes one write slow and searches slower | the pending list grows between vacuums

  BRIN | ranges on data in physical order | 1 entry per 128 pages. Does not block HOT from 16 | rows are out of physical order, or new ranges are not summarized

Every new index must also be built once, with `CREATE INDEX CONCURRENTLY` on a busy table, as the migrations section explains. On the 8 TB table of the partitioning section, one such build took 12 hours. So an index is a decision with a build time and a write cost, not a free fix.

So here are the indexes for the three queries. The queue query gets the partial index on `(created_at) WHERE status = 'pending'`. The count per tenant gets `(tenant_id, status)`, or `(tenant_id) WHERE status = 'pending'`. The hour of events gets a BRIN index on `created_at`, because the table is insert-only and in time order. If the queue query is sent as a prepared statement with `status = $1`, the partial indexes stop working from its generic plan on.

Try this now: run `uv run python phase04_planning/index_types.py --case partial`. Compare the two index sizes. Then check that the generic plan with `$1` does not name `p4_ix_pending` in its `indexes used` line.

So far each choice was about one table. The report also joins `orders` to `order_events`, and the next section shows where its 9 seconds went.

<details><summary>Go deeper: the docs' exact rules for each shape, the GIN operator classes, BRIN summarization, and what 18 adds</summary>

### Partial indexes, in the docs' words

The docs define a partial index as "an index built over a subset of a table". The docs give one major reason for it, to avoid "indexing common values". They add that it "will also speed up many table update operations because the index does not need to be updated in all cases". Matching the predicate "takes place at query planning time, not at run time". The HOT rule counts "columns that are tested in a partial-index predicate but are not stored in the index" as indexed columns.

### Composite indexes, the exact rule

The docs say: "equality constraints on leading columns, plus any inequality constraints on the first column that does not have an equality constraint, will be used to limit the portion of the index that is scanned." Constraints on later columns "do not reduce the portion of the index that has to be scanned". PostgreSQL 18 adds B-tree skip scan. It can use `(tenant_id, status)` for `status = 'pending'` alone when `tenant_id` has "so few distinct" values. With 1,000 tenants, whether 18 uses it was not checked. The leftmost-prefix rule is the same in InnoDB.

### Covering indexes, the two costs

- Non-key columns "duplicate data from the index's table and bloat the size of the index, thus potentially slowing searches".

- "There is little point in including payload columns in an index unless the table changes slowly enough that an index-only scan is likely to not need to access the heap."

Only B-tree, GiST and SP-GiST support `INCLUDE`. The HOT rules count any column "referenced at all in an index definition" as indexed. `relcache.c` at REL_17_11, lines 5401 to 5409, adds non-key columns to the HOT-blocking set, so an included column blocks HOT. Verified from the code.

### Expression indexes

The docs give the cost: "Index expressions are relatively expensive to maintain, because the derived expression(s) must be computed for each row insertion and non-HOT update." The routine-vacuuming chapter adds that ANALYZE statistics on the expression "can greatly improve query plans".

### GIN operator classes for jsonb

  Operator class | Operators it serves | Size and speed

  `jsonb_ops`, the default | `?`, `?|`, `?&`, `@>`, `@?`, `@@` | larger

  `jsonb_path_ops` | `@>`, `@?`, `@@` only | "usually much smaller", and searches "typically perform better"

For arrays, the default operator class serves `<@`, `@>`, `=` and `&&`. The GIN docs name the two costs of the pending list. "A large list of pending entries will slow searches significantly." And one update "will incur an immediate cleanup cycle and thus be much slower than other updates".

### BRIN, in detail

BRIN stores "summaries about the values stored in consecutive physical block ranges of a table". The size rule, from the BRIN docs, section 64.5.1, is "The number of index entries will be equal to the size of the relation in pages divided by the selected value for pages_per_range". BRIN is "most effective for columns whose values are well-correlated with the physical order of the table rows".

- **New ranges are not summarized at once.** A range filled after the last summary stays unsummarized "until a summarization run is invoked later". A VACUUM summarizes them, and so does `autosummarize`, an index option that is off by default. The code says the pages of an unsummarized range "need to be returned regardless of scan keys".

- **BRIN does not block HOT updates, since PostgreSQL 16.** The HOT rules allow HOT when the changed columns are used only in indexes that keep "summaries of the indexed data by block". The 14.24 rules have no such exception.

### The lab

E17 builds each shape on a lab table with `index_types.py` and prints its size and plan. Its self-test checks the data's 1-in-1,000 pending share, the BRIN entries per 128 pages, the leftmost-column rule on the docs' example, and the partial index with a parameter.

</details>

<details><summary>Evidence</summary>

Every fact on the six shapes is from the PostgreSQL 17 docs, chapter 11, "Indexes", unless named here. The jsonb operator classes are from section 8.14.4. The GIN pending list and `gin_pending_list_limit` are from the GIN chapter, 64.4. The BRIN rules are from 64.5.1. The HOT rules are README.HOT at REL_17_11, lines 36 to 42, and `execIndexing.c` lines 368 to 386 for partial indexes, and the BRIN comment is `brin.c` REL_17_11, lines 553 to 555. The expression statistics are from section 24.1.3. Skip scan is from the 18 docs, section 11.3. The selectivity myth is from Markus Winand's "Use The Index, Luke", page "Myth: Put the most selective column leftmost", read by the review on 2026-10-20. The 12-hour build is from Jeremy Schneider's post of 2024-03-03, the source of the partitioning case.

</details>

## Why did the nested loop take 9 seconds?

The Seq Scan took 2.1 of the 9 seconds, and the join took most of the rest. The planner chose its join method from the estimate of 42 rows.

### Nested loop

For each outer row, run the inner scan once. It is cheap for few outer rows with an index on the inner key.

### Hash join

Load one input into a hash table in memory, then probe it with each row of the other. It reads each input once.

### Merge join

Walk two inputs side by side, both sorted on the join key by an index or a Sort node.

The planner estimates the join's output first. Then it prices every method for every join order it considers, and keeps the cheapest. The sizes of `order_events` are an example: 30,000,000 rows in 150,000 pages.

- Nested loop at 42 rows: the scan of `orders`, 325,250, plus 42 × 8.59 = 361 for the lookups, which gives 325,611.

- Hash join at 42 rows: the same scan plus a full scan of `order_events`, 150,000 + 30,000,000 × 0.01 = 450,000. That is about 775,250 before hashing.

- Nested loop at the true 4,000,000 rows: 325,250 + 4,000,000 × 8.59 = 34,685,250, which is 45 times the hash join.

### The same join, priced at any outer estimate

  Outer estimate, on a log scale
  Outer rows **

  Nested loop **

  Hash join **

  Cheaper by the model **

Model arithmetic with the example sizes, not measured. Slider step 16 is about 40 rows, and 66 about 4,000,000.

A nested loop's cost grows with outer rows times the lookup, and a hash join's with the sum of its inputs. So a low outer estimate favors the nested loop, and the true count makes it cost the most. At 09:00 the nested loop was the right plan, and only the data changed since. So treat a plan regression after a bulk change as a statistics problem first.

### What you see in the plan

In `EXPLAIN (ANALYZE, BUFFERS)`, the signature takes four steps to see:

- Find the join node and its outer input, the first child.

- Compare the outer input's expected rows with its actual rows.

- Multiply the inner node's actual rows by its loops. Inner loops far above the outer estimate are the signature of this failure.

- For a hash join, read `Batches` on the Hash node. More than 1 means the hash table did not fit in memory and used disk.

Then fix the estimate, as the estimates section showed. Do not turn off `enable_nestloop` for the application, because these settings are for comparing plans. When the estimate cannot be fixed, a materialized CTE is a second tool. A *CTE*, common table expression, is a `WITH` query. A CTE used once is normally folded into the parent query and planned with it. `WITH x AS MATERIALIZED (...)` forces a separate calculation. The planner then plans the CTE on its own, and it cannot push the outer filters into it. Neon used a materialized CTE after its plan flip in the estimates section. Its post says this lets the planner "evaluate it once, use an appropriate index, and return a small set of relevant rows". A materialized CTE also blocks good plans, so keep it for a query whose plan has flipped before.

### When a sort or a hash does not fit in work_mem

A sort may use `work_mem`, 4MB by default. A hash table may use `work_mem` × `hash_mem_multiplier`, and that multiplier is 2.0 on 17, so 8MB. It was 1.0 on 14. Beyond its limit, the operation writes temporary files. The plan shows a spill in lines such as these, from PostgreSQL 14 examples whose format 17 keeps:

```text
Sort Method: external merge  Disk: 17136kB
Buckets: 65536  Batches: 64  Memory Usage: 2277kB
Buffers: shared hit=7236 read=6211, temp written=10858
Batches: 5  Memory Usage: 4145kB  Disk Usage: 98184kB
```

- The first line is a Sort that spilled. `external merge` wrote sorted runs to disk and merged them. A sort in memory prints `quicksort` and `Memory` instead.

- The second and third lines are one Hash node. `Batches: 64` means the input was split into 64 parts, and all but the first part went to temporary files. The Hash line does not show this disk use, and the `temp written` count of BUFFERS does.

- The fourth line is a HashAggregate that spilled, which it can do since PostgreSQL 13.

Where you meet it is a report that slows as its data grows, with no plan change. Across the server, `temp_files` and `temp_bytes` in `pg_stat_database` count every temporary file. Per statement, `temp_blks_written` in `pg_stat_statements` names the query that spills. The decision it changes is the scope of the fix. One query can run several such operations, and several sessions can run them at once, so the total memory can be many times `work_mem`. So raise `work_mem` for the one report that needs it, with `SET work_mem = '64MB'` in its session. Behind a transaction-mode pooler, where a session `SET` does not last, use `ALTER ROLE reporting SET work_mem = '64MB'`. Zerodha's engineering blog runs about 600 MB of `work_mem` on its warehouse database, and it warns that `work_mem` times `max_connections` can exhaust memory.

  The planner prices every path from row estimates, so fix the estimate, not the plan.

  Forcing an index or turning off nested loops for everyone, because one report chose badly.

  Run plan_lab.py --case join-methods, and check the planner picks the cheapest forced row.

The try's command is `uv run python phase04_planning/plan_lab.py --case join-methods`. Note the outer size where the method changes. The incident's UPDATE of 4,000,000 rows also did something the plans do not show. Each updated row left its old version behind, and the next section is about those versions.

<details><summary>Go deeper: the docs' three join plans, Memoize, the join search limits, the nested-loop finding, and more on spills</summary>

### Three plans from the docs, worked

The PostgreSQL 17 docs join `tenk1` to `tenk2`, two tables of 10,000 rows, on `unique2`. Both have an index on `unique2`. Try them before you read the answers:

- `unique1 < 10`, which keeps 10 rows of `tenk1`: Nested Loop, `cost=4.65..118.50`. The cost is the outer scan, plus one repetition of the inner scan for each outer row, plus a little CPU time for join processing. So 39.38 + 10 × 7.90 = 118.38, and the CPU time makes 118.50.

- `unique1 < 100`, which keeps 100 rows: Hash Join, `cost=226.23..709.73`. The 100 rows of `tenk1` go into the hash table. A sequential scan of `tenk2`, the outer input, probes it.

- `tenk1` joined to `onek`, a table of 1,000 rows: Merge Join, `cost=0.56..233.49`. Both sides arrive in key order from index scans. With `enable_mergejoin = off`, the planner picks a Hash Join at `cost=226.23..344.08`. The docs say the hash join "would be nearly 50% more expensive than merge join for this case", and 344.08 / 233.49 = 1.47.

The 14 docs showed the same three methods with older numbers, 118.62, 713.98 and 268.19, and a sorted `onek`. If you read the 14 page, check the method, not the digits.

### A cache inside nested loops: Memoize, new in PostgreSQL 14

A nested loop runs its inner scan once per outer row, even when many outer rows carry the same key. A Memoize node keeps the inner scan's rows for each key it has already seen, and `enable_memoize` turns it off. One PostgreSQL 14 example runs a nested loop over 113 flights that looks up each flight's aircraft, and all 113 have the same aircraft type:

```text
->  Memoize (actual rows=1 loops=113)
      Cache Key: f.aircraft_code
      Cache Mode: logical
      Hits: 112  Misses: 1  Evictions: 0  Overflows: 0  Memory Usage: 1kB
```

One miss read the row, and the 112 hits came from the cache. The cache is a hash table, and it counts against `work_mem`. Large `Evictions` numbers mean the cache was too small, and a wrong estimate of the distinct keys can cause that. In the opening case each order is its own key, so a Memoize over `order_events` would miss on every row. That is inferred.

### How far the join search goes

The search builds larger joins from smaller ones by dynamic programming, the bottom-up method of IBM's System R optimizer. Three settings limit the search, and two more set the memory of sorts and hashes:

  Setting | Default | What it does

  `from_collapse_limit` | 8 | subqueries are merged into the upper query up to this many FROM items

  `join_collapse_limit` | the same as `from_collapse_limit`, 8 | explicit JOINs are reordered up to this many items. 1 keeps the written order

  `geqo_threshold` | 12 | at this many FROM items, a genetic search replaces the exhaustive one

  `work_mem` | 4MB | memory per sort or hash before it spills to temporary files

  `hash_mem_multiplier` | 2.0 | a hash table gets work_mem x 2.0, so 8MB at the defaults. It was 1.0 in PostgreSQL 14, and PostgreSQL 15 raised it

### Where the worst plans came from

The 113-query measurement on PostgreSQL 9.4 traced its worst plans to this mistake. Its timeouts came from nested-loop joins without an index lookup, which a very low estimate had picked. With those joins disabled and the hash-table resizing of 9.5 added, fewer than 4% of the queries were more than 2 times slower than with true row counts. PostgreSQL 14 and 17 have that resizing, so the result likely looks different there. That was inferred and not measured. `plan_lab.py --case join-methods` uses the `enable_*` settings the way they are meant: it prices one join with each method forced, at three outer sizes.

### More on spills

HashAggregate could not spill before PostgreSQL 13. A chosen hash table was kept in memory however large it got. So on PostgreSQL 12, a low estimate of the groups could use memory without a limit, which is inferred from the 13 release note. `log_temp_files`, −1 by default, logs each temporary file when it is deleted. The algorithms behind the spill lines are external merge sort, and hash joins that partition an input that does not fit. Try it with `explain_tools.py --set work_mem=64kB`, as E15 does.

</details>

<details><summary>Evidence</summary>

The three plans and the nested-loop cost sentence are from the PostgreSQL 17 docs, section 14.1.1, `perform.sgml` REL_17_11, lines 402 to 575. The join size rule, "the join relation size is estimated before any particular join plan has been considered", is from section 68.1. Batches and disk use are from section 14.1.2. Memoize is from the PostgreSQL 14 release notes and Rogov, "PostgreSQL 14 Internals", page 361. The search limits are from section 19.7, the memory settings from section 19.4, and `hash_mem_multiplier` 2.0 from `postgresql.conf.sample` REL_17_11, lines 140 and 141, and the 15 release notes. The CTE rules are from section 7.8.3. The Neon quote is from its post of 2025-05-30, a vendor's report on its own system. System R's method is taught in CMU 15-445, lecture 15 notes, section 11. The nested-loop finding is from Leis and others, PVLDB 2015, section 4.1 and Figure 6. The spill lines are from Rogov, pages 374, 386 and 393, and the 17 format strings are the same at `explain.c` REL_17_11, lines 2966, 3316, 3524, 3531 and 3806 to 3813. HashAggregate spilling is from the 13 release notes. `temp_files` and `log_temp_files` are from sections 19.8 and 27.2. The Zerodha figures are from its post of 2021-04-22, fetched on 2026-10-20.

</details>

## What does VACUUM remove, and what stops it?

In Phase 3 you saw that an UPDATE writes a new row version and keeps the old one. A *snapshot*, from Phase 3, records which transactions had finished when a statement began. A *dead version* is one no snapshot can still see. VACUUM removes dead versions from the table and every index, and marks their space free for new rows. It keeps that space in the file, except empty pages at the end, and the extra space is called *bloat*. A version is removable only when it died before the oldest snapshot any open transaction holds, the *cleanup horizon*.

  One order's versions | No old snapshot | A report began at 10:30 and is still open

  v1 status=created, replaced at 10:05 | removed | removed: it died before the report began

  v2 status=pending, replaced at 11:00 | removed | kept: the report's snapshot may still read it

  v3 status=paid, live | kept | kept

<details><summary>Predict: each night a job deletes 1,000,000 old orders, the day inserts 1,000,000, and VACUUM runs. Why is the file larger every morning?</summary>

Something holds the cleanup horizon in the past, such as a session left idle in a transaction. VACUUM runs and reports success, but it removes nothing that died after that snapshot. So the inserts cannot reuse the space and extend the file.

</details>

One old snapshot holds the horizon back for every table in the database. Four causes are common:

- **A snapshot held open.** A long report, or a session left `idle in transaction`, keeps the horizon in the past. Phase 3 gave the setting that ends such sessions, `idle_in_transaction_session_timeout`, which is off by default.

- **A replication slot whose reader is gone.** A slot's `xmin` holds back VACUUM for every table. A physical slot gets an `xmin` only from a standby with `hot_standby_feedback = on`, which is off by default. The 17 docs state the link. Feedback "on its own, without also using a replication slot" gives no protection while the standby is not connected. With a slot, the primary keeps the rows while the standby is away. A logical slot sets `catalog_xmin` instead, which holds back only catalog rows.

- **An old prepared transaction.** A two-phase commit that was never finished holds the horizon too.

- **Freed space in the wrong place.** If deletes and inserts run faster than VACUUM, the inserts extend the file before the space is freed. That cause is inferred from how VACUUM frees space.

The first three show up in one query each. Read `age(backend_xmin)` in `pg_stat_activity`, `age(xmin)` and `age(catalog_xmin)` in `pg_replication_slots`, and `age(transaction)` in `pg_prepared_xacts`. `bloat.py --xid` prints all three. The more common harm of an abandoned slot is WAL. `max_slot_wal_keep_size` is −1 by default, so a slot may keep an unlimited amount of WAL files. Phase 5 teaches replication: 5.2 for slots and WAL retention, and 5.3 for `hot_standby_feedback` and the bloat it moves to the primary.

### What you see: the PostgreSQL 17 vacuum log

PostgreSQL 17 logs every autovacuum run that lasts at least `log_autovacuum_min_duration`, 10 minutes by default. On 14 the default was −1, which logged nothing. A run of 10 minutes is already long, so set a lower value, such as `'10s'`, to see the runs that matter. On Amazon RDS, two settings decide what reaches the log:

- `rds.force_autovacuum_logging_level` must allow the lines. Its default is `warning` on PostgreSQL 13 and later.

- `log_autovacuum_min_duration` is 10000 ms by default on RDS for PostgreSQL 11 to 14, and AWS recommends a value "from 1000 to 5000". The AWS page gives no RDS default for 15 and later, so run `SHOW log_autovacuum_min_duration` on your instance.

Each logged run writes one entry. These are the first lines of its 17 format, with a `%` field where each number goes:

```text
automatic vacuum of table "%s.%s.%s": index scans: %d
pages: %u removed, %u remain, %u scanned (%.2f%% of total)
tuples: %lld removed, %lld remain, %lld are dead but not yet removable
removable cutoff: %u, which was %d XIDs old when operation ended
frozen: %u pages from table (%.2f%% of total) had %lld tuples frozen
```

- **`removable cutoff: N, which was X XIDs old when operation ended`** is the held cleanup horizon. N is the oldest transaction ID that VACUUM had to keep, for an open snapshot, a slot or a prepared transaction. VACUUM fixes N when it starts. X is the distance from N to the next transaction ID when the run ended, so X also counts the IDs used during the run. A large count of `dead but not yet removable` with a large X points at the four causes above.

- **`index scans: N`** above 1 means the dead row addresses did not fit in the memory limit, so VACUUM read every index more than once. On 17 the addresses go into a *TID store*, a compact structure for row addresses. Its limit is `autovacuum_work_mem`, or `maintenance_work_mem`, and the old 1 GB cap is gone.

- **The first line names the kind of run.** It prints `automatic aggressive vacuum` for a freezing scan, and adds `to prevent wraparound` for the forced run of the next section.

Posts written on 14 and earlier show a different line, `dead row versions cannot be removed yet, oldest xmin`. Your 17 server never prints it, so read the `removable cutoff` line for the same fact. While a vacuum runs, `pg_stat_progress_vacuum` shows it. On 17 its memory columns are `dead_tuple_bytes` of `max_dead_tuple_bytes` and `num_dead_item_ids`. Before 17 they were `num_dead_tuples` of `max_dead_tuples`, and a script that reads the old names fails on 17.

### Where you meet it: job queues and agent state

A table that works as a queue gets an UPDATE or a DELETE for every job. So it makes dead rows faster than any other table, and a held horizon hurts it first. **Trigger.dev**'s post is a published case, on Amazon RDS:

- 1:45pm UTC  The primary database "spiked to 99%" CPU, while run volume was normal.

- then  Its job queue was the Graphile Worker library, whose table held "600,000 dead tuples (and growing)". The queue "does a sequential scan to find the next job to run", so every claim read past the dead rows.

- then  A manual `VACUUM VERBOSE` reported "662319 dead row versions cannot be removed yet, oldest xmin: 1706280686". That is the 14 format, and on 17 the same fact is the `removable cutoff` line.

- then  The team ended long transactions and checked slots and prepared transactions. None of that released the horizon.

- about 19:00  They promoted a read replica, a copy of the database, to be the primary, and VACUUM worked again. The post never found what held the horizon.

Two design rules for queue tables and agent state follow from this case and from the index section:

- **Find work through an index, not a scan.** A partial index on the waiting jobs, such as `(run_at) WHERE state = 'queued'`, reads only live waiting jobs. It still visits dead index entries until VACUUM removes them, which is inferred.

- **Keep often-updated columns out of indexes.** A claim that changes an indexed `state` column is never a HOT update. So each claim writes new entries into all of the table's indexes, except a partial index whose predicate the claimed row no longer meets. A table of agent steps whose `status` and `updated_at` change on every step has the same cost. A `fillfactor` below 100 leaves room on each page for HOT updates of the other columns. Both rules are inferred from the HOT rule of Phase 2.

### Why autovacuum falls behind on a large table

Autovacuum starts on `orders` after 50 + 0.2 × `reltuples` = 2,000,050 dead rows. The incident's 4,000,000 dead versions passed that, and the file grew, because the pages were full. Then a budget sets the speed:

- A worker spends 200 cost units, then naps 2 ms. A cached page costs 1, a page read costs 2, and a page it dirties costs 20 more.

- The 200 units are shared by all running workers, so 3 workers get about 66 each.

- When every page is read and dirtied, 9 pages fit in one nap. That is 35.5 MB/s for all workers together.

### The autovacuum budget, every page read and dirtied

  Cost limit
  Workers
  Heap size in GB
  Units per worker **

  Ceiling for all workers **

  One pass over the heap, at least **

Arithmetic from the PostgreSQL 17 defaults, not run. It counts only the naps, and the indexes come on top.

So one pass over a 500 GB heap takes at least 4 hours, whatever the worker count. What you see is many autovacuum workers in `pg_stat_activity` with `wait_event_type` `Timeout` and `wait_event` `VacuumDelay`, which means they nap. Many workers in that wait mean the budget limits vacuum, not the disk, which is inferred. The decision it changes is where you tune:

- Raising `autovacuum_max_workers` alone does not speed vacuum up, because more workers split the same budget.

- Give the large table its own `autovacuum_vacuum_cost_limit` and a lower `autovacuum_vacuum_scale_factor`. A table with its own cost setting also leaves the sharing.

- Since PostgreSQL 16, a reload reaches a running autovacuum at its next delay point, a place in its loop where it may nap. So a changed cost limit applies to the table it is vacuuming now. On 14 it applied only from the next table.

```sql
-- For one large, busy table. Values are an example.
ALTER TABLE orders SET (
  autovacuum_vacuum_scale_factor = 0.01,  -- 50 + 0.01 x 10,000,000 = 100,050 dead rows
  autovacuum_vacuum_cost_limit   = 1000   -- 5 times the budget, for this table only
);
```

### Getting the space back

`VACUUM FULL`, `CLUSTER` and the table-rewriting forms of `ALTER TABLE` write a new copy without dead space. They all take an ACCESS EXCLUSIVE lock, and they use extra disk about equal to the size of the table until they finish. So every read and write of the table waits for the whole rewrite. For a table that will grow again, moderately frequent standard VACUUMs are the better choice. For a table emptied on a schedule, `TRUNCATE` frees the space at once, and the price is that strict MVCC rules are broken for it.

### Index bloat, and rebuilding without blocking writes

A B-tree also keeps the space of dead entries. Two releases lowered it. PostgreSQL 13 stores duplicate keys once, and PostgreSQL 14 removes expired entries to prevent page splits. A low-cardinality index such as the one on `status` gains the most, which is inferred. When a table or an index must still be rebuilt, four tools exist:

  Tool | What it does | Lock and cost

  `pgstattuple`, `pgstattuple_approx` | measure dead rows and free space | `pgstattuple` always performs a full-table scan. `pgstattuple_approx` skips pages that the visibility map marks all-visible

  `REINDEX INDEX CONCURRENTLY`, PostgreSQL 12 and later | builds a new index beside the old one, then swaps them | takes no locks that prevent concurrent inserts, updates or deletes. Two scans, a wait for older transactions, and no transaction block. Only `REINDEX INDEX` can rebuild an invalid index concurrently

  `pg_repack`, an extension outside core | rewrites a table and its indexes while traffic runs | needs a primary key, or a unique index on NOT NULL columns, and free disk about twice the table and its indexes. It takes one exclusive lock at the beginning and one at the end

  `VACUUM FULL`, `CLUSTER` | rewrite the table in core | ACCESS EXCLUSIVE for the whole rewrite

A failed `REINDEX CONCURRENTLY` leaves an invalid index whose name ends in `_ccnew`. Drop it and run the command again. One index type has its own rule. For pgvector's HNSW index, the pgvector README says "Vacuuming can take a while for HNSW indexes. Speed it up by reindexing first", with `REINDEX INDEX CONCURRENTLY` before `VACUUM`. Phase 2, section 2.9, shows what HNSW's VACUUM does, and the course retrieval-internals, in its Phase 7, teaches deletes and VACUUM on vector indexes.

Try this now: the `--vacuum-signals` mode of `bloat.py`, from E16, prints the budget per worker and the worst-case ceiling. Find both, and the `log_autovacuum_min_duration` line. On a server whose log you can read, give that log to `bloat.py --parse-log`.

Removing dead versions is only half of VACUUM's job. The next section is the other half, which keeps a 32-bit counter from stopping the database.

<details><summary>Go deeper: the settings, the throttle in numbers, the whole log entry and four views, shrinking a file, index bloat, and the bloat lab</summary>

### Autovacuum's settings in PostgreSQL 17

The 50 and the 0.2 are `autovacuum_vacuum_threshold` and `autovacuum_vacuum_scale_factor`. Inserts have their own trigger, `autovacuum_vacuum_insert_threshold` 1,000 plus its own `autovacuum_vacuum_insert_scale_factor`, also 0.2, times `reltuples`. So an insert-only table is vacuumed too. PostgreSQL 18 multiplies the scale-factor part of that insert trigger by the share of the table that is not yet frozen. Other defaults:

  Setting | Default in 17 | What it means

  `autovacuum_naptime` | 1min | one worker start per database per minute

  `autovacuum_max_workers` | 3 | at most three tables vacuumed at once. On 17, as on 14, it changes only at server start. PostgreSQL 18 lets a reload change it, up to `autovacuum_worker_slots`, 16

  `autovacuum_work_mem` | −1, so `maintenance_work_mem`, 64MB | memory for the dead row addresses of each pass. Each address is a TID, the 6-byte tuple ID of Phase 2, section 2.2. Up to 16 it was an array of 6-byte entries, capped at 1GB. 17 stores them in the TID store, which "reduces memory consumption"

On a very large table the 0.2 is a long wait. A table of 1,000,000,000 rows waits for 200,000,050 dead rows. PostgreSQL 18 adds `autovacuum_vacuum_max_threshold` as a cap on that sum, with a default of 100,000,000.

### The throttle in numbers

`vacuum_cost_page_miss` is 2 since PostgreSQL 14 lowered it. The budget is `autovacuum_vacuum_cost_limit`, −1 by default, so it uses `vacuum_cost_limit`, 200. The nap is `autovacuum_vacuum_cost_delay`, 2 ms since PostgreSQL 12. The limit is distributed proportionally among the running workers, so the sum of their budgets never passes it. A delay without its limit says nothing, because the limit sets how much work happens between two naps.

```
The autovacuum budget at PostgreSQL 17 defaults. Arithmetic, not run
200 units, then a 2 ms nap. Shared by every running worker

every page is   cost  pages per nap   ceiling for all workers together
cached             1          200     100,000 pages/s    781.3 MB/s
read               2          100      50,000 pages/s    390.6 MB/s
read + dirtied    22            9       4,545 pages/s     35.5 MB/s

3 workers: about 66 units each. 6 workers: about 33 each. Same ceiling
a table with its own cost_limit 1000 leaves the sharing: 5x the ceiling
```

The ceilings are upper bounds, because they count only the naps, not the time of the work itself. The 500 GB example is 512,000 MB / 35.5 MB/s, about 14,400 seconds, or 4 hours. Two more rules follow:

- Raise the workers and the cost limit in proportion, if you raise the workers at all.

- A manual VACUUM is not throttled by default, because `vacuum_cost_delay` is 0, which disables the cost-based delay. Each storage parameter in the SQL above takes only SHARE UPDATE EXCLUSIVE.

The code comment of the 16 change says it "allows changes to [autovacuum_]vacuum_cost_limit and [autovacuum_]vacuum_cost_delay to take effect while a table is being vacuumed or analyzed". On 14, a worker honoured changed settings only at the start of each table.

### The rest of the 17 log entry

The core text showed the first five lines. A `new relfrozenxid` line sits between `removable cutoff` and `frozen`, and these lines follow `frozen`:

```text
new relfrozenxid: %u, which is %d XIDs ahead of previous value
index scan needed: %u pages from table (%.2f%% of total) had %lld dead item identifiers removed
index "%s": pages: %u in total, %u newly deleted, %u currently deleted, %u reusable
avg read rate: %.3f MB/s, avg write rate: %.3f MB/s
buffer usage: %lld hits, %lld misses, %lld dirtied
WAL usage: %lld records, %lld full page images, %llu bytes
system usage: %s
```

The `index "%s"` line repeats once for each index. The `new relfrozenxid` line, and a similar `new relminmxid` line, appear only when the run advanced them. `relfrozenxid` is a table's oldest unfrozen transaction ID, which the wraparound part below explains. A `tuples missed:` line appears when VACUUM could not get a page's cleanup lock. The index scan line can also start `index scan not needed:` or `index scan bypassed:`. An `I/O timings:` line comes before the read rates when `track_io_timing` is on. `VACUUM VERBOSE` prints the same block, with the first line `finished vacuuming "%s.%s.%s"`. PostgreSQL 18 adds more lines, among them `visibility map:` and `delay time:`.

The 14 entry had a `tuples:` line that ended `oldest xmin: %u`, and it had no `removable cutoff`, `frozen` or `scanned` fields. On 14 each dead row address took 6 bytes, so 64MB held 64 × 1,048,576 / 6 = 11.18 million rows per pass. The TID store holds more rows in the same memory. How many more depends on how the dead rows spread over pages, and this course did not measure it. One PostgreSQL 14 run shows `index scans: 3` for 500,000 dead rows with `maintenance_work_mem` set to 1MB.

`bloat.py --parse-log`, E16, reads these entries from a server log and prints the dead rows kept and the age of the horizon for each table. It reads the 14 autovacuum log format too. It does not read the 14 VACUUM VERBOSE output, which has no "finished vacuuming" line.

### Four views

  View | What to read

  `pg_stat_progress_vacuum` | one row per running VACUUM: `phase`, `heap_blks_scanned` of `heap_blks_total`, `index_vacuum_count`, `dead_tuple_bytes` of `max_dead_tuple_bytes`, `num_dead_item_ids`, and `indexes_processed` of `indexes_total`

  `pg_stat_user_tables` | per table: `n_dead_tup`, `n_mod_since_analyze`, `n_ins_since_vacuum`, `last_autovacuum` and `autovacuum_count`

  `pg_stat_activity` | an autovacuum's `query`, such as `autovacuum: VACUUM public.orders`, and the `VacuumDelay` wait while it naps

  `pg_stat_io`, new in 16 | rows with `backend_type` `autovacuum worker`, and rows with `context` `vacuum`: reads, writes, hits and reuses of the vacuum's buffer ring

On RDS and Aurora, Performance Insights shows waits as class and event, so the same wait should appear as `Timeout:VacuumDelay`. That name is inferred from the AWS naming of other waits, and was not checked on the AWS pages. `bloat.py --vacuum-signals` prints all of these for the lab's tables, and picks the right progress columns for your server version.

### The bloat lab

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

The space rule, "will not return the space to the operating system", is from the PostgreSQL 17 docs, section 24.1.2, which also give the rewrite locks, the extra disk and the TRUNCATE warning that "strict MVCC semantics are violated". The growth causes are from section 24.1.5. The slot rules are from the `pg_replication_slots` page, section 19.6, and section 26.2.6 of `high-availability.sgml` at REL_17_11. The vacuum trigger values come from the same two docs sections as the analyze ones. The cost settings are from sections 19.4.4 and 19.10, and from `vacuum.c` REL_17_11, lines 2427 to 2437. The reload rule is `vacuum.c` REL_17_11, lines 2401 to 2412, and the 14 behaviour is from the 16 release notes. The sharing exception is at `autovacuum.c` REL_17_11, lines 2856 to 2862. The nine pages per nap are from Rogov, "PostgreSQL 14 Internals", page 118. The 10-minute default is from section 19.8 and `postgresql.conf.sample` REL_17_11, line 578. The RDS settings are from the AWS page "Logging autovacuum and vacuum activities". The log format is `vacuumlazy.c` REL_17_11, lines 626 to 760, with `removable cutoff` at lines 670 to 673 and the index pass at lines 880 and 881. The 14 line is at `vacuumlazy.c` REL_14_24, lines 795 and 1656. The TID store is from `release-17.sgml` lines 14010 and 14730. The progress columns are `system_views.sql` REL_17_11, lines 1209 to 1226, and the 17 release notes. `VacuumDelay` is in the Timeout class of `wait_event_names.txt`, line 180, and the `vacuum` context of `pg_stat_io` is `pgstat_io.c`, line 232. The Trigger.dev case is from Matt Aitken's post of 2024-08-16, about an event on 2024-08-15, read as raw text. The index tools are from the REINDEX page, the 12, 13 and 14 release notes, section F.31 and the pg_repack documentation. The HNSW rule is from the pgvector README at v0.8.7.

</details>

## How does transaction ID wraparound stop a database?

VACUUM has a second job. A transaction ID is 32 bits, and IDs are compared modulo 2^32. So for every ID, two billion IDs count as older and two billion as newer. A row whose ID fell more than two billion behind would look as if it came from the future, so it would become invisible. VACUUM prevents this by *freezing* old rows, which marks them as older than every normal ID. PostgreSQL enforces it with fixed limits on `age(datfrozenxid)`. `datfrozenxid` is a database's oldest unfrozen transaction ID, kept in `pg_database`, and its age is how many IDs ago it was assigned.

### age(datfrozenxid) on PostgreSQL 14 to 18, up to wraparound

The figure has five ranges. Below 200 million, no forced vacuum runs yet. From 200 million, the value of `autovacuum_freeze_max_age`, a forced vacuum runs, even with autovacuum off. From 1.6 billion, the value of `vacuum_failsafe_age`, vacuum stops its cost naps and skips index vacuuming. From 2,107 million, every session sees `WARNING: must be vacuumed within N transactions`. In the last 3 million, new IDs are refused, so no write can start.

Take a database at an age of 1,900,000,000 on PostgreSQL 17 that assigns 1,000 write transactions a second. The stop is at an age of 2,147,483,647 − 3,000,000 = 2,144,483,647, so 244,483,647 more IDs remain. At 1,000 a second that is about 244,484 seconds, or 2.8 days. The warning comes 37 million IDs earlier, at 2.4 days. Read-only transactions get no ID and do not count.

### What you see when it goes wrong

The first sign in the server log is the WARNING, and it comes only 37 million IDs before the stop. At an example 3,000 IDs a second, that is about 3.4 hours, and a VACUUM of a large table can take longer. At the stop, PostgreSQL 17 refuses every command that needs a new ID:

  Version | The error | Its hint

  16 and earlier | `database is not accepting commands to avoid wraparound data loss` | "Stop the postmaster and vacuum that database in single-user mode"

  17 and 18 | `database is not accepting commands that assign new transaction IDs to avoid wraparound data loss` | "Execute a database-wide VACUUM in that database"

Follow the 17 hint and the docs, not the old hint. The docs say it is "not necessary or desirable to stop the postmaster or enter single user-mode". Their steps are these, in order:

- Resolve old prepared transactions.

- End long-running open transactions.

- Drop old replication slots.

- Run VACUUM in the database, not VACUUM FULL and not VACUUM FREEZE.

The decision it changes is what you alert on. Alert on `age(datfrozenxid)` against `autovacuum_freeze_max_age`, 200 million, and do not wait for the error. `bloat.py --xid` prints the distance to every limit.

### Why a quiet table suddenly gets a full scan

An insert-only table can one day get a scan of every unfrozen page, although nothing in it changed. Two rules cause it:

- VACUUM freezes a row once its inserting transaction is older than `vacuum_freeze_min_age`, 50 million. A normal VACUUM skips pages that hold no dead rows, so it can leave old rows unfrozen.

- `relfrozenxid` is a table's oldest unfrozen transaction ID, kept in `pg_class`, and `datfrozenxid` is the oldest of them in a database. When a table's `relfrozenxid` reaches an age of `vacuum_freeze_table_age`, 150 million, VACUUM turns aggressive. An aggressive scan reads every page not marked all-frozen, a second bit per page in the visibility map.

That this hits a quiet table is inferred from the two rules. What you see is the word `aggressive` in the vacuum log line, and a long run on a table that has no dead rows.

### The forced vacuum does not give way

A normal autovacuum gives way to a schema change. It does so in three steps:

- A process that waits for a lock runs its deadlock check after `deadlock_timeout`, 1 s.

- If an autovacuum blocks it, it sends the worker a cancel signal.

- The worker logs `canceling autovacuum task` and stops.

The code skips the signal when the worker vacuums to prevent wraparound. Its query in `pg_stat_activity` ends with `(to prevent wraparound)`, and it holds SHARE UPDATE EXCLUSIVE for its whole run. Under the throttle of the section above, that run can take hours on a large table. A table that receives DDL often may also never finish a normal autovacuum, because each DDL statement cancels it. The docs, section 24.1.6, warn that such commands "can effectively prevent autovacuums from ever completing".

Joyent's Manta service shows what that does. Its postmortem does not name the PostgreSQL version.

- 10:30:09  An autovacuum "to prevent wraparound" starts on one metadata shard. It holds SHARE UPDATE EXCLUSIVE on the table. A component reconnects and runs `DROP TRIGGER`, which asks for an exclusive lock and waits behind the autovacuum. Every data-path query then waits behind `DROP TRIGGER`.

- 10:30  About 22% of all requests fail, near 27% at the peak.

- 14:11  PostgreSQL is restarted. Service returns for 5 to 10 minutes, then a new wraparound autovacuum starts and the same queue forms.

- hours  The vacuum scans the table and all its indexes, twice. The team patches the process to skip the cost-based sleeps. It ends, and a few minutes later another one starts.

- 20:45  The error rate is back to zero.

- **The vacuum did not block the queries.** SHARE UPDATE EXCLUSIVE does not conflict with them, and the post says "the autovacuum itself wasn't blocking all the data path queries". The waiting `DROP TRIGGER` did, by the soft block from Phase 3.

- **The fix is the migrations rule.** Give every DDL statement a `lock_timeout`, so it leaves the queue and retries. Joyent ended the outage by making its wraparound settings less aggressive. Its planned fix was to stop dropping and recreating the trigger. The post says it expects that change to resolve the issue.

- **Check before a migration.** Look in `pg_stat_activity` for a query that ends in `(to prevent wraparound)` on the table. `locks.py --scenario wraparound` replays the sequence offline.

### Multixacts have a second limit

Phase 3 showed the case. A row locked by several transactions at once stores a *multixact* ID in its `xmax`, and a foreign-key check is the usual cause. Multixact IDs are also a 32-bit counter, so they wrap in the same way, and you watch `mxid_age(datminmxid)` in `pg_database`. The ID age is not the only limit. Phase 3, section 3.4, told Metronome's case in full. Here are the facts this section needs:

- The database was Aurora PostgreSQL 13.18, over 30 TB, and it had four write outages over eight days.

- A backfill inserted rows into partitioned tables. Concurrent inserts that referenced the same parent rows through foreign keys created multixacts.

- The members of all multixacts share one storage space of about 4 billion, and that space ran out.

- The team's metrics showed the multixact ID age at "less than 50% utilization", so they thought they had room. The post says "PostgreSQL does not expose metrics for member space consumption".

So alert on `mxid_age(datminmxid)`, and on a self-managed server also watch the size of the member files. They are in pg_multixact/members, from the 17 docs, section 19.10. Section 24.1.5.1 says aggressive vacuums run more often when that storage passes about 10GB, and it wraps at about 20GB. Whether RDS or Aurora show that size was not checked. One difference changes the recovery steps: replication slots do not directly hold back multixact cleanup. So for a multixact problem, look at old transactions and prepared transactions first.

Run `uv run python phase04_planning/bloat.py --xid` on your own server now. Find your oldest database age, and compute the transactions left before the forced autovacuum.

Both halves of VACUUM's job grow with the dead versions a table makes. The next section removes old data without leaving dead versions behind.

<details><summary>Go deeper: the limits in the code, the freeze settings, multixact settings, two more outages, and what 18 changes</summary>

### The limits in the code

The wraparound point is 2,147,483,647 IDs past the oldest unfrozen ID. The warning starts at the wrap limit minus 40,000,000, and the stop at minus 3,000,000. These limits are the same in 14, 17 and 18. PostgreSQL 13 used 11,000,000 and 1,000,000. The failsafe of `vacuum_failsafe_age`, 1.6 billion, is not the aggressive freezing scan. The docs call it "VACUUM's strategy of last resort". When it triggers, vacuum stops applying the cost-based delay, so it stops its naps, and it skips non-essential work such as index vacuuming.

The 200 million default for `autovacuum_freeze_max_age` has a reason. It translates to about 50MB of `pg_xact` storage, because the commit status takes two bits per transaction.

### Freezing in more detail

The all-frozen bit sits beside the all-visible bit in the visibility map of the access-path section. The `pg_visibility` extension shows both bits. PostgreSQL 18 adds eager freezing, which freezes some all-visible pages during normal vacuums. Its setting is `vacuum_max_eager_freeze_failure_rate`, 0.03 by default.

### Multixact settings

The same settings exist with `multixact` in their names. `vacuum_multixact_freeze_min_age` is 5 million, `vacuum_multixact_freeze_table_age` is 150 million, and `autovacuum_multixact_freeze_max_age` is 400 million. `bloat.py --xid` prints both ages. The error and the hint table of the core text are from the 17 source, and the 16 lines are inferred from 14, which has the same text.

### Two more outages

Both are first-party reports. Neither names its PostgreSQL version, which this course did not check:

- **Sentry.** Sentry was down for most of a US working day. Its post blames too high an `autovacuum_freeze_max_age` with the default of 3 workers. After hours of vacuum, the team truncated one large table and recovered within minutes. The post gives the stop margin as one million transactions, which matches the limit of PostgreSQL 13 and earlier, not the 3 million of 14 and later. Its new settings read as the throttle lesson. `autovacuum_vacuum_cost_delay = 0` turns the throttle off, and `autovacuum_max_workers = 6` with `autovacuum_naptime = '15s'` adds workers. The post's own correction says `maintenance_work_mem = '10GB'` met a 1GB internal limit, which PostgreSQL 17 removed. It also set `autovacuum_freeze_max_age = 500000000` and `vacuum_freeze_min_age = 10000000`.

- **Mandrill, by Mailchimp.** The outage ran from 05:35 UTC on February 4 to 22:09 UTC on February 5, about 40.5 hours. In the November before it, engineers had seen the transaction IDs climb to about half the limit at peak load. Their highest estimate for the vacuum was 40 days.

### The alert arithmetic

The limits are 40 million and 3 million before wraparound, so the WARNING starts 37 million IDs before the stop. At 3,000 IDs per second, 37,000,000 / 3,000 = 12,333 seconds, about 3.4 hours. From an age of 1,900,000,000, the warning is 207,483,647 IDs away, which is 207,484 seconds at 1,000 per second. Use the age query of the docs' wraparound section.

</details>

<details><summary>Evidence</summary>

The two-billion rule and "it is necessary to vacuum every table in every database at least once every two billion transactions" are from the PostgreSQL 17 docs, section 24.1.5, with the recovery steps. The limits are from `varsup.c` at REL_17_11, lines 389, 405 and 419, and the 17 error and hint at lines 156 and 158. The REL_14_0 to REL_16_0 text is at lines 129 to 138. The rows are verified at REL_14_0, REL_16_0, REL_17_0, REL_17_11 and REL_18_0, from each tag's own `varsup.c`, fetched on 2026-10-20. REL_13_0 has the old text at lines 127 and 129. The settings are from sections 19.10 and 19.11. The interruption rule is from section 24.1.6. The cancel path is in `proc.c` REL_17_11, lines 1416, 1443 and 1472, and the log line at `postgres.c` line 3415. DROP TRIGGER's lock is at `trigger.c` REL_17_11, line 1323. Freezing and the all-frozen bit are from sections 19.11 and 24.1.5 and Rogov, page 126. Multixacts are from sections 19.10, 19.11 and 24.1.5.1. The Joyent sequence is from its postmortem of 2015-07-27, archived copy. The Metronome case is its RCA of 2025-05-20, about outages from 2025-05-10 to 2025-05-17, fetched on 2026-10-20. Sentry's post is of 2015-07-23, and its settings were checked in its saved text. The Mandrill post is by Eric Muntz, dated 2019-03-26. Eager freezing is from the 18 sample file.

</details>

## When does partitioning remove the cleanup, and what does it cost the plans?

A nightly DELETE of old events creates the dead versions of the VACUUM section, every night. A *partitioned table* is a parent with no rows of its own. Each row goes to the partition whose bounds hold its *partition key*, here the month of `created_at`. *Partition pruning* skips partitions whose bounds cannot match the query. It uses only conditions on the key, never the indexes.

```
order_events, partitioned by month on created_at, 12 partitions
WHERE created_at in March         Jan  Feb [Mar] Apr ... Dec
                                  1 partition read: pruned at plan time
WHERE order_id = 123             [Jan][Feb][Mar][Apr]...[Dec]
                                  12 index lookups: no key, no pruning
EXECUTE with $1 = March, generic [Mar]   Subplans Removed: 11
                                  pruned at executor start
```

- A query on March reads 1 of 12 partitions, pruned at plan time.

- A query on `order_id = 123` reads all 12. The report joins on `order_id`, so it touches every partition unless it also filters on `created_at`.

- A generic plan prunes at executor start, and EXPLAIN prints `Subplans Removed: 11`. The partitions it removes there are still locked at the start of execution.

- Dropping a month's partition leaves no dead versions, where a DELETE of that month leaves 30,000,000 / 12 = 2,500,000 for VACUUM.

Keys are limited too. A unique or primary key on a partitioned table must include every partition key column. The reason is that each partition's index enforces uniqueness only inside that partition. So `PRIMARY KEY (id)` is refused, and `PRIMARY KEY (id, created_at)` is allowed.

So partition when the hot queries name the key and old data leaves by whole months. Partitioning helps when the table would otherwise be larger than the server's memory. It adds planning time and locks to every query.

### What it costs every query: locks

A query takes an ACCESS SHARE lock on the parent and on each index of the parent. It also takes one on every partition it keeps, and on every index of those partitions. How much that costs depends on where the locks go. **Midjourney** partitioned its 8 TB orders table by day. Each partition had 22 indexes. Kyle Hailey managed its PostgreSQL database. He wrote that each query locked every partition and every index. This happened even when he limited the queries to specific partition ranges. At 40 partitions, he worked out about 880 locks per query.

Here is why that count matters:

- A session keeps up to 16 *weak locks* in its own *fast-path slots*. A weak lock is one that rarely conflicts.

- Every further lock goes into the shared lock memory, which all sessions use, and which one short internal lock protects.

- When many sessions need that memory at once, they wait on `LWLock:LockManager`. RDS for PostgreSQL 13 and later shows the wait as `LWLock:lockmanager`.

In May the work queue stalled. About 500 sessions waited on `LWLock:LockManager`, and errors reached 1,000 a second. He detached 7 partitions. He rebuilt the day partitions as week partitions to cut the lock count. His graphs showed the waits starting at about 12 partitions. Adding one index to that 8 TB table with `CONCURRENTLY` also took 12 hours. The posts do not settle why the partition ranges did not reduce the locks. One mechanism fits the docs' warning above: a generic plan locks every partition at executor start, before it prunes. That fit is inferred, not shown in the posts.

  Partitions × indexes | Index locks per query | On 17, 16 slots | On 18, 64 slots

  10 × 22 | 220 | 16 + 204 shared | 64 + 156 shared

  40 × 22 | 880 | 16 + 864 shared | 64 + 816 shared

The tables add one lock each, so 40 partitions add 40 more. The counts are arithmetic, not run. PostgreSQL 18 raises the default to 64 slots, so the same query puts fewer locks in the shared memory. But 880 is still far above 64.

To see the split on your own server, run the query from the AWS page while a session holds its locks:

```sql
SELECT count(*), pid, mode, fastpath
  FROM pg_locks
 WHERE fastpath IS NOT NULL
 GROUP BY 4, 3, 2
 ORDER BY pid, mode;
```

Rows with `fastpath = f` and mode `AccessShareLock` are the locks that went to the shared memory. AWS prints a sample in which one pid holds 16 AccessShareLock locks on the fast path and 336 in the shared table.

### What it costs every query: planning

Planning time and memory grow with the partitions that remain after pruning. The planner handles up to a few thousand partitions fairly well, if typical queries prune all but a few. Each partition a session touches also loads its metadata into that session's memory. So the decision it changes is the choice of key. A team that gives each customer its own LIST partition finds, years later, thousands of partitions and plans that touch them all. The docs suggest a fixed number of HASH partitions instead. Choose the key from the WHERE clauses of the hot queries. Measure planning time at the partition count you expect in three years. Use `EXPLAIN (MEMORY)` for the planner's memory, and count the locks with the query above.

The same rule fits embeddings stored per tenant. The pgvector README suggests LIST partitions by `customer_id` for tenant isolation, because a shared index lets one tenant's vectors change the recall and speed of another's. For filtering by many values, it suggests LIST partitions by `category_id`. Verified from the README at v0.8.7, lines 461 to 475. That fits only when the queries name the tenant, and the tenant count stays small enough for planning.

### Removing a month without blocking traffic

Adding and removing months is DDL, so it takes locks. `DROP TABLE` on a month that is still attached takes ACCESS EXCLUSIVE on the parent, so every query on `order_events` waits for it. The routine that never blocks traffic on the parent has four steps:

- Create next month's table on its own, and load it if needed.

- Add a CHECK constraint that matches the month's bounds, so ATTACH can skip its scan.

- Run `ATTACH PARTITION`, which takes only SHARE UPDATE EXCLUSIVE on the parent. Then drop the CHECK, which is redundant once the attach is complete.

- For the oldest month, run `DETACH PARTITION ... CONCURRENTLY`, then `DROP TABLE`. CONCURRENTLY cannot run in a transaction block. It is also refused when the table has a DEFAULT partition, from the ALTER TABLE page.

  VACUUM frees only rows dead before the oldest snapshot, so drop old months as partitions.

  Tuning VACUUM settings while one open transaction, slot or prepared transaction holds the horizon.

  Run partitions.py --locks --extra-indexes 3, and compare the fastpath f count with the model.

That try is E19 of the lab. Partition maintenance is a schema change on a busy table, and so is the opening case's index. The next section names the lock each schema change takes, and what happens while it waits.

<details><summary>Go deeper: the three moments of pruning, the benefits and costs in full, the maintenance locks, and partitions made in advance</summary>

### Three moments of pruning

- **At plan time,** when the values are constants in the query.

- **At executor start,** for parameter values known then, such as those of a generic plan from the sixth execution of a prepared statement on the server, and later through a driver. These partitions vanish from the plan, and EXPLAIN prints a `Subplans Removed` line. The docs warn that "any partitions removed by the partition pruning done at this stage are still locked at the beginning of execution".

- **During execution,** for values that change while the query runs, such as the inner side of a nested loop. Then EXPLAIN ANALYZE shows the pruned partitions with fewer loops, or as `(never executed)`.

### When it helps

- The heavily used rows sit in one or a few partitions. Partitioning then takes the place of the upper tree levels of indexes, so the hot parts of the indexes are more likely to fit in memory.

- A query that reads most of one partition can scan that partition in sequence. It avoids random index reads across the whole table.

- Bulk loads and deletes become adding or removing a partition. Dropping a partition avoids the VACUUM work that a bulk DELETE causes.

### When it hurts the planner, in full

- **Queries without the key read every partition,** as the `order_id` case showed.

- **Planning cost,** which the core text explains. The older inheritance method works with up to perhaps a hundred child tables.

- **Statistics of the parent.** Autovacuum does not run ANALYZE on partitioned tables. The partitions get their own statistics, and a query planned against the whole parent needs a manual ANALYZE of the parent.

- **Uniqueness only with the key,** as the core text showed.

- **No concurrent index build on the parent.** The CREATE INDEX docs of 14, 17 and 18 all say: "Concurrent builds for indexes on partitioned tables are currently not supported". The workaround is `CREATE INDEX ON ONLY` the parent, then `CREATE INDEX CONCURRENTLY` on each partition, then `ALTER INDEX ... ATTACH PARTITION` for each one.

- **Lock memory for every query,** as the core text showed. The 16 slots are `FP_LOCK_SLOTS_PER_BACKEND` on 17.

### The fast-path slots on 18

At the default `max_locks_per_transaction` of 64, 18 has 4 groups of 16 slots. A relation goes to one group by its OID, so on 18 a query can fill one group before it uses all 64. That last point is inferred from the code. `partitions.py --locks`, E19, runs the AWS query against a session that holds one query's locks on the lab's partitions.

### The locks of partition maintenance

  Statement | Lock on the parent | Lock on the partition

  `CREATE TABLE ... PARTITION OF` | ACCESS EXCLUSIVE | the new table

  `ALTER TABLE ... ATTACH PARTITION` | SHARE UPDATE EXCLUSIVE | ACCESS EXCLUSIVE, and a scan unless a matching CHECK exists

  `ALTER TABLE ... DETACH PARTITION` | ACCESS EXCLUSIVE | ACCESS EXCLUSIVE, from tablecmds.c at REL_17_11, lines 19235 and 19236

  `... DETACH PARTITION ... CONCURRENTLY`, new in 14 | SHARE UPDATE EXCLUSIVE, in two transactions | ACCESS EXCLUSIVE in the second

A DEFAULT partition adds one more lock. ATTACH also takes ACCESS EXCLUSIVE on the default partition, if there is one, and scans it to check that none of its rows belong in the new partition. A CHECK constraint on the default partition that excludes the new bounds lets ATTACH skip that scan.

### Partitions made in advance

Teams that partition by time make the partitions ahead of need. Reddit's media metadata store on Aurora PostgreSQL keeps 30 range partitions made in advance with pg_partman, an extension that manages partitions, and a weekly pg_cron job. That is verified from an archived copy of Reddit's post. Its ranges are on `post_id`, which grows with time. `partitions.py` checks each claim of this section on your server, and `--planning-sweep` measures the planning time at 12, 120 and 1,200 partitions.

</details>

<details><summary>Evidence</summary>

All partitioning facts are from the PostgreSQL 17 docs, section 5.12, which was 5.11 in the 14 docs. The pruning rule, "driven only by the constraints defined implicitly by the partition keys, not by the presence of indexes", and the three moments are from 5.12.4. The benefits and the rule of thumb are from 5.12.1, the key rule from 5.12.2.3, the planning limits from 5.12.6 and the inheritance limit from 5.12.5. That autovacuum does not analyze partitioned tables is from section 24.1.3. The limit on a concurrent build of the parent is quoted from the CREATE INDEX page, in all three versions. The locks of ATTACH and DETACH, and of DROP TABLE on an attached partition, are from 5.12.2.2 and the ALTER TABLE page. The fast-path slots are `proc.h` REL_17_11, line 86, with the test at `lock.c` lines 929 and 930, and 18's groups are `postinit.c` REL_18_6, lines 586 to 596. The RDS names and the `pg_locks` query are from the AWS page "LWLock:lock_manager". The Midjourney case is from Kyle Hailey's post of 2023-06-13, which names no company, and Jeremy Schneider's post of 2024-03-03, which names Midjourney and gives the 12-hour build. The daily partitions began on April 1, 2023, and the waits on April 11. The 500 sessions and 1,000 errors a second come from the headline of Hailey's post, which gives no date beyond May. The pgvector advice is from its README at v0.8.7, lines 462 to 475.

</details>

## Why does an instant ALTER stop every SELECT?

Every statement takes one of eight table lock modes, and two modes either conflict or do not. A schema change can block the table during two periods. One is the time it holds its lock to do its work: a catalog change, a scan or a rewrite. The other is the time it waits, because a waiting request blocks later ones.

  Requested \ held | ACCESS SHARE | ROW EXCLUSIVE | SHARE UPDATE EXCL | SHARE | ACCESS EXCLUSIVE

  ACCESS SHARE, a SELECT | ok | ok | ok | ok | waits

  ROW EXCLUSIVE, a write | ok | ok | ok | waits | waits

  SHARE UPDATE EXCL, VACUUM or CREATE INDEX CONCURRENTLY | ok | ok | waits | waits | waits

  SHARE, CREATE INDEX | ok | waits | waits | ok | waits

  ACCESS EXCLUSIVE, most ALTER TABLE | waits | waits | waits | waits | waits

Five of the eight modes, the same in PostgreSQL 14 and 17. The full table is in Go deeper.

<details><summary>Predict: session A opened a transaction, read p4_tasks, and is still open. You run ALTER TABLE p4_tasks ADD COLUMN queue text, a change to the catalog only. One second later a plain SELECT on p4_tasks arrives. What happens to it?</summary>

The SELECT waits behind the ALTER for as long as A stays open, although A and the SELECT do not conflict and the ALTER needs milliseconds.

</details>

The lock manager grants a request only if it conflicts with nothing granted and nothing already waiting, in order of arrival. The course research ran the predict case on PostgreSQL 14.24, and the lock rules are the same at the 17 tag.

### The lock queue, three sessions, one step per second

  t = 0 s: A reads the table and holds ACCESS SHARE.

  t = 1 s: B asks for ACCESS EXCLUSIVE, which conflicts with A, so B waits.

  t = 2 s: C does not conflict with A, but it conflicts with B, which is waiting, so C waits too.

  t = 6 s: A commits. B gets its lock, adds the column in milliseconds and commits, then C runs.

  Times from the course research's run on PostgreSQL 14.24, not run on 17. C took 4.04 s for a one-row SELECT, and B took 5.03 s.

So the table is down while the longest open transaction lasts. Session A does not have to be yours, and in the Joyent outage it was a wraparound vacuum that never gives way. With `SET lock_timeout = '100ms'` on B, B failed after 0.18 s with `canceling statement due to lock timeout`. C started at t = 2 s, after B had left the queue, and took 0.07 s. The error carries a *SQLSTATE*, the five-character error code that the server sends with every error and drivers expose. This one is 55P03, `lock_not_available`. A statement that gives up leaves the queue, so the requests behind it run, and the migration retries after a random pause.

The opening case's `CREATE INDEX` took `SHARE`, which conflicts with the `ROW EXCLUSIVE` of every write. So writes waited 11 minutes, and SELECTs went on. `CREATE INDEX CONCURRENTLY` takes `SHARE UPDATE EXCLUSIVE` and blocks no reads or writes.

### The same outage at Railway, made worse by the pooler

Railway's incident report tells the opening case with real numbers:

- 18:23  A schema change adds a column with an index, on a table of about 1 billion rows.

- 18:34  The change is live, and the index build has no `CONCURRENTLY`. Queries queue behind the build, and the API keeps accepting requests. PgBouncer opens more connections than Postgres allows, and every slot fills, the reserved slots too. Admins cannot log in.

- 18:56  The root cause is identified.

- about 30 min  The build finishes and releases its lock.

- 19:15  Full service is restored.

The attempt to cancel the build failed with `FATAL: remaining connection slots are reserved for roles with privileges of the "pg_use_reserved_connections" role`. Railway planned three changes. CI would reject an index build without `CONCURRENTLY`. PgBouncer's pool limits would stay below the Postgres limit. Per-user connection limits would keep room for an administrator.

Two details connect to this section. The report says the build caused "an exclusive lock on the entire table" and that "all queries" queued. By the table above, a plain `CREATE INDEX` takes SHARE, which blocks writes and lets reads through. The API's write requests queued and held their connections, so the pool filled with waiting writers. That reading is inferred from the lock table and the report.

The second detail is the arithmetic of connection slots, and it is a decision you make in your own config:

```text
max_connections                  100  (PostgreSQL 17 default)
superuser_reserved_connections     3
reserved_connections               0
left for ordinary roles           97
PgBouncer default_pool_size       20  per user and database pair
five pairs at the default         5 x 20 = 100, more than 97
```

So keep the sum of all pools below `max_connections` minus the reserved slots. The server prints the FATAL message only when `reserved_connections` is above 0, so Railway's server had set it. It means that only superusers and roles with the privileges of `pg_use_reserved_connections` could still connect. That role is new in PostgreSQL 16. Both points are inferred from `postinit.c` at REL_17_11, lines 955 to 969. Phase 5 sets the whole connection budget in 5.7, and elite-performance sizes the pool itself, in Phase 2a part 2.3 and Phase 5b part 5.5.

### The same queue at GoCardless, behind one long SELECT

GoCardless reported about 15 seconds of unexpected API downtime during a planned migration. The sequence was this:

- A long `SELECT` ran on a busy parent table.

- While it ran, a migration added a foreign key `NOT VALID` from an empty child table.

- On a restored backup with no traffic, the same migrations took a few hundred milliseconds.

The post says that adding the foreign key takes ACCESS EXCLUSIVE on both tables. That was true up to PostgreSQL 9.4, the version the post discusses. PostgreSQL 9.5 lowered it, and on 17 `ADD FOREIGN KEY` takes SHARE ROW EXCLUSIVE, on both tables. The course research measured the difference on 14.24. A transaction held a write lock on the parent for 5 s, and the foreign-key addition queued behind it. A SELECT on the parent then finished in 0.18 s, and an INSERT waited 2.98 s.

### What you see, and where you set the limits

With `log_lock_waits` on, a migration that waits writes `process %d still waiting for %s on %s after %ld.%03d ms`. Its detail line lists the holders and the wait queue, so that pair of lines shows the lock queue in a production log. Here is the role of each timeout in a migration:

  Setting | Its role in a migration | Where to set it

  `lock_timeout` | bounds each wait for one lock, so the queue behind it moves | every DDL statement, `SET lock_timeout = '100ms'`, with retries

  `statement_timeout` | stops a scan or a rewrite that runs longer than planned | per migration with `SET LOCAL`, and per role. Not in `postgresql.conf`, which the docs advise against

  `idle_in_transaction_session_timeout`, and `transaction_timeout` from 17 | ends the session whose open transaction a migration would wait behind | per role, for application sessions

  `log_lock_waits` | logs every lock wait longer than `deadlock_timeout`, 1 s | on, in `postgresql.conf` or the RDS parameter group

The same per-role rule fits SQL that an AI agent writes and runs. Give the agent's database role its own short `statement_timeout` and `lock_timeout` with `ALTER ROLE`. Then one bad query from the agent cannot hold a lock queue for long. That use is inferred, because both settings apply per role.

A concurrent build needs three checks, because older transactions delay it and a failed build leaves an invalid index:

- **Before:** run `SELECT pid, now() - xact_start, query FROM pg_stat_activity WHERE xact_start < now() - interval '1 minute' ORDER BY xact_start`. A concurrent build waits for such transactions, and other DDL waits for the ones that hold a lock on its table. Such a wraparound vacuum on the table is the Joyent case.

- **During:** `pg_stat_progress_create_index` shows the build's `phase`.

- **After a failure:** `SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid` lists invalid indexes. An invalid index is ignored for queries but still costs every write, so drop it and build again.

### How long to wait for a lock

  Source | `lock_timeout` | Retries

  postgres.ai, Nikolay Samokhvalov | 50 ms | exponential backoff with jitter, 30 attempts in its example

  GitLab, `with_lock_retries.rb` at master | 0.1 s, rising to 2 s | 615 attempts, about 44.6 minutes in the worst case

  GoCardless, `ActiveRecord::SaferMigrations` | 750 ms | none by default, plus a 1,500 ms statement limit

  Braintree draft by James Coleman | locks held at most about 2 seconds | not stated

  strong_migrations, Andrew Kane | 10 s | 3, 10 s apart, marked experimental

  OpenAI, for the database behind ChatGPT | 5 s on schema changes, setting not named | not stated. Only changes that do not rewrite a table are allowed

The OpenAI row is verified from an archived copy of OpenAI's post. The post says "We enforce a strict 5-second timeout on schema changes". It does not say whether that is `lock_timeout` or `statement_timeout`. Each attempt can block the table's traffic for up to `lock_timeout`, so a short value keeps each pause short. A short value also fails more often on a busy table, so it needs more retries. The postgres.ai post works through one thought experiment. Its SELECTs take 0.1 ms, and its migration retries 50 ms waits with no pause between them. The average SELECT then approaches 50 ms. That is why the pause between attempts matters as much as the timeout.

### A rewrite also gives wrong answers

`TRUNCATE` and the table-rewriting forms of `ALTER TABLE`, such as `ADD COLUMN ... DEFAULT random()`, are not MVCC-safe. After the rewrite commits, the table appears empty to a transaction whose snapshot was taken before the DDL committed. This hits only a transaction that had not yet read the table when the DDL started. An example is a long report at REPEATABLE READ that reaches the table late. That report gets wrong answers with no error. So schedule rewrites away from long reports, as well as away from traffic.

Try this now: run `uv run python phase04_planning/locks.py --predict "CREATE INDEX p4_tasks_state ON p4_tasks (state)"`, then the same with `CONCURRENTLY`. Compare the lock modes and the `blocks` lines.

A bounded wait makes each statement safe to queue. The next section uses it to add a NOT NULL column to the busy task queue.

<details><summary>Go deeper: all eight modes, the lock of each DDL statement, the retry code, the values teams choose, and more about concurrent builds</summary>

### All eight modes

```
Table lock conflicts, PostgreSQL 17 docs 13.3.1. X = the two conflict
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

### Which DDL takes which lock

An ACCESS EXCLUSIVE lock is taken unless the ALTER TABLE page notes otherwise. `locks.py --predict` prints the same facts for any statement:

  Statement | Lock | What it blocks | Its work while it holds the lock

  `CREATE INDEX` | SHARE | writes | a full scan to build the index

  `CREATE INDEX CONCURRENTLY` | SHARE UPDATE EXCLUSIVE | other DDL and VACUUM, no traffic | two scans, and waits for older transactions

  `ANALYZE`, `VACUUM`, `CREATE STATISTICS` | SHARE UPDATE EXCLUSIVE | other DDL and VACUUM | a sample, or one pass

  `ADD COLUMN`, constant or no default | ACCESS EXCLUSIVE | everything | the catalog only. For a constant default, since PostgreSQL 11

  `ADD COLUMN ... DEFAULT random()` | ACCESS EXCLUSIVE | everything | a rewrite of the table and its indexes

  `ADD CONSTRAINT ... CHECK ... NOT VALID` | ACCESS EXCLUSIVE | everything | the catalog only. New rows are checked from now on

  `VALIDATE CONSTRAINT` | SHARE UPDATE EXCLUSIVE | other DDL and VACUUM | one scan of the existing rows

  `ALTER COLUMN ... SET NOT NULL` | ACCESS EXCLUSIVE | everything | a full scan, skipped if a valid CHECK proves no NULL, since 12

  `ADD FOREIGN KEY` | SHARE ROW EXCLUSIVE, on both tables | writes on both tables | a scan to check rows, unless NOT VALID

  `ALTER COLUMN ... TYPE` | ACCESS EXCLUSIVE | everything | a rewrite, unless the old type is binary coercible

  `VACUUM FULL`, `CLUSTER` | ACCESS EXCLUSIVE | everything | a rewrite

  `REINDEX` | SHARE on the table, ACCESS EXCLUSIVE on the index | writes, and reads that would use the index | a rebuild of the index

The REINDEX row needs a note. The lock-mode list puts REINDEX under ACCESS EXCLUSIVE. The REINDEX page says instead that it locks out writes but not reads of the index's parent table. The code opens the table in SHARE mode and the index in ACCESS EXCLUSIVE mode.

The course outline tells the opening story as a migration that "took an exclusive lock". That is not the mode it took, because SHARE blocks writes only. An ACCESS EXCLUSIVE lock would also have stopped the reads.

### lock_timeout and retries

`lock_timeout` stops any statement that waits longer than the given time while it tries to take a lock. It applies separately to each lock attempt. The lab's runner retries every DDL statement on SQLSTATE 55P03. From `phase04_planning/migrate_lab.py:376`:

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

`backoff` waits a random time up to `min(cap, base × 2^attempt)`. That is capped exponential backoff with jitter, and the random part spreads retries that failed together.

### GitLab's two retry schedules

GitLab's documentation and its code disagree. The style guide says the helper tries 50 times, then runs once more without `lock_timeout`. The code at master retries 615 times over about 44.6 minutes, with timeouts from 0.1 s to 2 s. In migrations, `lock_retries_helpers.rb` line 43 sets `raise_on_exhaustion` to true, so the migration fails when the retries run out. This course teaches the code, and it did not search for places where GitLab overrides the schedule.

### CREATE INDEX CONCURRENTLY in full

- It scans the table twice. It also must wait for all existing transactions that could modify or use the index to end.

- If it fails, it leaves an index marked invalid. Drop it and build again, or use `REINDEX INDEX CONCURRENTLY`.

- It cannot run inside a transaction block, and only one concurrent build can run on a table at a time.

- While it runs, it holds a snapshot. So vacuum cannot remove dead rows in any table, by the cleanup horizon of the VACUUM section.

A pgvector HNSW index is built the same way, and its build needs memory. The pgvector README says builds are much faster "when the graph fits into maintenance_work_mem", and the server prints a NOTICE when it no longer fits. Set `maintenance_work_mem` for the build session only, and not so high that it "exhausts the memory on the server", the README warns. Phase 2, section 2.9, measures the build memory and WAL of a vector index.

A unique constraint can be added the same way. Build `CREATE UNIQUE INDEX CONCURRENTLY` first. Then `ADD CONSTRAINT ... USING INDEX` turns the index into the constraint, which is a fast operation for a UNIQUE constraint. It takes ACCESS EXCLUSIVE, held briefly, from AlterTableGetLockLevel in tablecmds.c at REL_17_11, lines 4579 and 4592.

</details>

<details><summary>Evidence</summary>

The conflict lists are from the PostgreSQL 17 docs, section 13.3.1, the same as in 14. The two queue rules are in the lmgr README at REL_17_11, line 364, "A lock request is granted immediately if it does not conflict with any existing or waiting lock request", and line 387, conflicting requests "are granted in order of arrival". The three-session run, the 4.04 s, 5.03 s, 0.18 s and 0.07 s, and the foreign-key run are the course research's, on PostgreSQL 14.24 on 2026-10-17. The DDL lock rows are from the 17 ALTER TABLE, CREATE INDEX and REINDEX pages, and the REINDEX locks are in `index.c` REL_17_11, lines 3614 and 3654. The Railway case is its incident report of 2025-10-28, fetched on 2026-10-20. The connection defaults are `postgresql.conf.sample` REL_17_11, lines 65 to 67, the FATAL message is `postinit.c` line 968, and `default_pool_size` is from the PgBouncer config page. The GoCardless outage is from its post "Zero-downtime Postgres migrations, the hard parts", and the foreign-key change from the 9.5 release notes. `lock_timeout` is from section 19.11.1, and the 55P03 error from `postgres.c` REL_17_11, line 3400, and `errcodes.txt` line 421. The log line is at `proc.c` REL_17_11, line 1603. The MVCC rule is from section 13.6. The retry values are from each source in the sources list, and GitLab's code was fetched on 2026-10-18. The OpenAI row is from an archived copy of its post of 2026-01-22, fetched on 2026-10-20. The concurrent build rules are from the CREATE INDEX page, the snapshot point from James Coleman's Braintree draft, and the progress view from section 27.4. The HNSW build advice is from the pgvector README at v0.8.7.

</details>

## How do you add a NOT NULL column with no failed request?

The task queue now needs `queue text NOT NULL` on `p4_tasks`, which workers write all day. The *expand/contract* pattern changes a schema in steps that keep the old and the new code working. Expand adds what the new code needs and removes nothing. The code then moves to the new shape. Contract removes the old shape once nothing uses it.

- **1 expand: ADD COLUMN queue text**ACCESS EXCLUSIVE, catalog only

- **2 switch: deploy code that writes queue**no lock. The old code drains

- **3 backfill: UPDATE a batch of ids WHERE queue IS NULL, then pause**row locks on 1,000 rows per transaction

- **4 check: ADD CHECK (queue IS NOT NULL) NOT VALID**ACCESS EXCLUSIVE, catalog only

- **5 validate: VALIDATE CONSTRAINT**SHARE UPDATE EXCLUSIVE, one scan

- **6 not null: SET NOT NULL**ACCESS EXCLUSIVE, scan skipped

- **7 contract: DROP CONSTRAINT the CHECK**ACCESS EXCLUSIVE, catalog only

Every ACCESS EXCLUSIVE step runs with `lock_timeout` 100 ms and retries. This is the plan of `migrate_lab.py`, strategy expand-contract.

Each ACCESS EXCLUSIVE step holds its lock for milliseconds. On 1,000,000 rows the course research measured these on PostgreSQL 14.24. Times on 17 were not measured.

Time holding ACCESS EXCLUSIVE on 1,000,000 narrow rows in memory, measured by the course research on 14.24.

A constant default changes only the catalog, so the 2.5 ms does not grow with the table. So `ADD COLUMN queue text NOT NULL DEFAULT 'default'` does not rewrite the rows on 17. A volatile default such as `random()` rewrites the table and its indexes, which took 996.7 ms. `SET NOT NULL` with no CHECK scans the whole table, which took 48.2 ms. That time grows with the table, and all of it is spent under ACCESS EXCLUSIVE. With a valid CHECK in place, `SET NOT NULL` skips its scan and took 0.68 ms. `VALIDATE CONSTRAINT` does that scan under `SHARE UPDATE EXCLUSIVE`, so traffic goes on.

### The compatibility window

Between expand and contract, two code versions run against one schema, so each step must work for both:

- **New code, old schema.** Code that writes `queue` must not deploy before step 1. Otherwise every write fails with an unknown column.

- **Old code, new schema.** Old code never writes `queue`, so its rows stay NULL after the backfill passes them. Once step 4 adds the CHECK, the constraint is enforced against later inserts and updates. So the old code's inserts fail with SQLSTATE 23514, `check_violation`, and step 5 fails on the NULL rows they left.

So the switch must finish, with every old instance gone, before the backfill reaches its last batch. A column DEFAULT is the other way to keep old inserts working. `--strategy constant-default` adds the column with `DEFAULT 'default'`, and it backfills only the rows that need another value.

  **Naive:** one transaction, no `lock_timeout`, behind a transaction open for 5 s. Most of the about 2,000 requests in that window pass their 1-second deadline and fail.

  **Expand/contract:** the expand step retries at 100 ms until the open transaction ends, so no request fails.

Those results are expected from the lab's rules at 400 requests a second, not measured. Where you meet the failure is a migration tested on an idle copy, which proves little, because lock waits depend on traffic. The GoCardless outage of the section above is that case. So test a migration under load and measure the lock waits, as E10 and E11 do.

### PostgreSQL 18 shortens this recipe

In 18 a NOT NULL constraint can be added `NOT VALID`, as a CHECK can on 17. `ALTER TABLE p4_tasks ADD CONSTRAINT p4_tasks_queue_nn NOT NULL queue NOT VALID` changes only the catalog. Then `VALIDATE CONSTRAINT p4_tasks_queue_nn` scans the rows under SHARE UPDATE EXCLUSIVE, which blocks no reads or writes. So steps 4 to 7 of the diagram become those two statements. The two commands were not run.

### The same migration on MySQL

You run MySQL too, so here is the MySQL 8.4 form of the same problem, with InnoDB.

   | PostgreSQL 17 | MySQL 8.4, InnoDB

  add a column | constant default: catalog only, under ACCESS EXCLUSIVE | `ALGORITHM=INSTANT`: metadata only, the default in 8.4

  the queue | a waiting ACCESS EXCLUSIVE blocks later SELECTs | a pending exclusive metadata lock blocks later transactions

  the wait limit | `lock_timeout` 0: wait for ever | `lock_wait_timeout` 31536000 s, one year

  what you see | `pg_stat_activity`, `pg_locks` | `Waiting for table metadata lock` in `SHOW FULL PROCESSLIST`

  a rewrite | `VACUUM FULL`, pg_repack | `COPY` or `INPLACE`, gh-ost

- **The metadata lock queue.** An online DDL may take an exclusive metadata lock briefly while it prepares, and it takes one to commit the new table definition. The manual says "a pending exclusive metadata lock requested by an online DDL operation blocks subsequent transactions on the table". That is the PostgreSQL lock queue again. So set a low limit, such as `SET SESSION lock_wait_timeout = 5`, in every migration.

- **Instant changes have a count.** Each instant add or drop creates a row version, and "The maximum number of row versions permitted is 64 (255 as of MySQL 9.1.0)". After that, MySQL rejects the change with `ERROR 4092`, and the table needs a rebuild.

- **gh-ost** is GitHub's tool for changes that cannot be instant, "a triggerless online schema migration solution for MySQL". It copies the table into a ghost table and follows changes from the binary log. Then it swaps the tables at a cut-over you can postpone, and it can throttle by itself.

Try this now: run `uv run python phase04_planning/migrate_lab.py --plan --strategy naive`, then the same with `--strategy expand-contract`. For each step of the naive plan, say what its reverse would lose.

Every step of this plan can be reversed, and not every migration can. The next section sorts the steps you can undo from the ones you cannot.

<details><summary>Go deeper: what other teams do, the wrong and right SQL, the lab's lint, and the arithmetic behind the lab's numbers</summary>

### What other teams do

The strong_migrations README gives the same order for NOT NULL. First a CHECK `NOT VALID`, then a validation in a separate migration, then `NOT NULL`, then dropping the CHECK. It names "three keys to backfilling safely: batching, throttling, and running it outside a transaction". Its example updates 10,000 rows per batch with a 0.01 s sleep. GitLab's guide to batched background migrations shows batches of 1,000 to 10,000 rows in its examples, with sub-batches of 100 or 500. Its migration style guide says "any single query must stay below 1 second" in a background migration. Stripe's post "Online migrations at scale", by Jacqueline Xu, describes the same idea for moving data between models. It has four phases: write to both, move the reads, move the writes, remove the old data. The post does not name its database engine. Moving a very large table to new storage with dual writes belongs to course 5. Logical replication and its slots are this course's Phase 5, in 5.2.

### Wrong and right, as SQL

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
UPDATE p4_tasks SET queue = CASE WHEN state IN ('awaiting_approval', 'approved',
    'rejected') THEN 'approvals' ELSE 'default' END
 WHERE id > 0 AND id <= 1000 AND queue IS NULL;    -- and so on, with a pause
ALTER TABLE p4_tasks ADD CONSTRAINT p4_tasks_queue_not_null
  CHECK (queue IS NOT NULL) NOT VALID;
ALTER TABLE p4_tasks VALIDATE CONSTRAINT p4_tasks_queue_not_null;
ALTER TABLE p4_tasks ALTER COLUMN queue SET NOT NULL;   -- no scan, since 12
ALTER TABLE p4_tasks DROP CONSTRAINT p4_tasks_queue_not_null;
```

`migrate_lab.py --plan` prints the plan of the chosen `--strategy`, with a lint that encodes these rules. It reports three faults for the naive plan. The first is ACCESS EXCLUSIVE with no `lock_timeout`. The second is an UPDATE inside the DDL transaction. The third is SET NOT NULL with no valid CHECK first. The self-test checks that count, and that the expand/contract plan has none.

### The measurements, in detail

On the research's table, the file number stayed 16401 after `DEFAULT 42`, and changed from 16401 to 16434 after `DEFAULT random()`, which shows the rewrite. With `client_min_messages = debug1`, the skipped scan printed `existing constraints on column "t.n" are sufficient to prove that it does not contain nulls`. The 17 source has the same message. The 48 ms is for 1 million narrow rows in memory.

### The compatibility window, in detail

Without the CHECK, step 6 would make the old code's inserts fail with 23502, `not_null_violation`. `--break-compat` shows both failures. In the lab, the switch step waits `--settle-s` seconds to stand for the deploy.

### The lab's arithmetic

The defaults are 4 readers and 4 writers at 50 requests per second each, so 400 per second. Each request's deadline is 1,000 ms.

- `--strategy naive --hold-lock-s 5`: the ALTER waits 5 s with no timeout, and every request queues behind it. About 400 × 5 = 2,000 requests are scheduled in that window, and most of them fail with 57014 or `late`. Inserts are half of the writers' requests, so about 4 × 50 × 0.5 = 100 old-code inserts fail per second after the commit, with 23502.

- `--strategy expand-contract --hold-lock-s 5`: the expand step times out and retries until the open transaction's 5 seconds end. The default `--seed 1` fixes the random backoff waits. Python's `random.Random(1)` gives 7, 85, 153, 102, 396, 719, 1,303 and 1,577 ms. With 100 ms per failed attempt, the ninth attempt starts at about 5.14 s, after the open transaction has committed. So expect 9 attempts and 8 lock timeouts. That was computed from the generator, not from a run of the lab. No request waits much longer than 100 ms, so none fails.

### MySQL in more detail

The manual says "INSTANT is the default algorithm in MySQL 8.4" for adding a column, and it "can add a column at any position in the table". `SHOW FULL PROCESSLIST` shows both the DDL and the blocked SELECT in the state `Waiting for table metadata lock`. `lock_wait_timeout` bounds the wait, as `lock_timeout` does, and its default of 31536000 seconds is one year. E20 asks you to write the MySQL form of this whole plan.

</details>

<details><summary>Evidence</summary>

The measurements are the course research's, on PostgreSQL 14.24 on 2026-10-17, on a table of 1,000,000 rows. The 17 message is at `tablecmds.c` REL_17_11, line 7903. The constant default without a rewrite is from the PostgreSQL 11 release notes and the 17 ALTER TABLE page, and the skipped scan of SET NOT NULL from the 12 release notes and the same page. The CHECK enforcement wording, "enforced against subsequent inserts or updates", is from the ALTER TABLE page. The 18 NOT NULL `NOT VALID` form is from the PostgreSQL 18 ALTER TABLE page and its release notes. The strong_migrations quotes are from its README, GitLab's sizes from its batched background migrations guide, and the four phases from Stripe's post of 2017. The MySQL facts are from the MySQL 8.4 pages "Online DDL Operations", "Online DDL Performance and Concurrency" and "Server System Variables", and the gh-ost README, all fetched on 2026-10-20 and none run.

</details>

## Which schema changes can you undo?

A deploy goes wrong, and the first instinct is to roll back. The code can go back to its previous version in minutes, and the schema often cannot. A reverse statement changes the schema's shape, and it does not bring data back. So sort every step into one of two kinds. *Additive steps* add a column, a table, an index or a constraint, or copy data, and their reverse loses nothing. *Destructive steps* drop, narrow, overwrite or rename what the old code uses, and their reverse cannot restore the data.

  Change | Can you undo it without losing data?

  `ADD COLUMN queue text`, before any code writes it | yes: drop the column

  The batched backfill of `queue` | yes: the column is still nullable, and no old code reads it

  `ALTER COLUMN queue SET NOT NULL` | yes: `DROP NOT NULL`

  `DROP COLUMN old_status`, a week after the code stopped reading it | no

  `ALTER COLUMN amount_cents TYPE integer`, from `bigint` | no, unless every value fits, and even then the reverse is a rewrite under ACCESS EXCLUSIVE

  A backfill that rewrites `status` in place, from `paid` to the new value `settled` | no: the rows that were `paid` and the rows already `settled` look the same afterwards

DROP COLUMN does not physically remove the column. It makes the column invisible to SQL, and no statement makes it visible again. So the only way back is a restore from a backup, which also loses every write made after it. The same holds for `DROP TABLE` and `TRUNCATE`. So structure a change to stay additive:

- Expand only adds, next to the old shape and never in its place.

- To change a column's type or meaning, add a new column, write both, and backfill the new one.

- Pair every step with its reverse in the plan, and say what the reverse loses.

- Undo code before schema, because code that still writes `queue` fails with SQLSTATE 42703, `undefined_column`, once the column is gone.

- Contract last, in its own release, once no running code uses the old shape and a backup exists.

A down migration that never ran is the usual failure. Many frameworks generate a "down" step for each migration, and nobody runs it until the day it is needed. By then the table holds data it was not written for, such as rows that only the new code wrote. So test each reverse under load, as E11 does with `--rollback-after`. Many teams roll forward instead: they fix a bad change with a new change, while the schema keeps its expanded shape.

### Two destructive steps in production

Two incidents show a step with no reverse. Both are verified from the first-party posts:

- **Linear.** A migration ran `TRUNCATE TABLE <new_table> CASCADE`. The cascade emptied every table with a foreign key to it. The team restored a full backup rather than a point-in-time recovery, because that had never been tested. Over 99% of the data was back within 36 hours. Its planned change is that no user on the production databases has `TRUNCATE` privileges.

- **Resend.** A migration run on a laptop pointed at production and dropped all tables. The first restore used the wrong backup time, and the total downtime was about 12 hours.

Both needed a restore from backup, the case that Phase 1 covers. Phase 5 teaches backups and point-in-time recovery in 5.6, and how to test a restore.

### Keys that run out: the type change you need at the worst time

Narrowing a key is destructive. The opposite change, from `integer` to `bigint`, loses nothing. But it often comes as an emergency on the largest table, because a 32-bit key ran out. `integer` and `serial` stop at 2,147,483,647. `bigint` and `bigserial` go to 9,223,372,036,854,775,807. Two published outages show what the end of the range looks like:

- **GitHub, on MySQL.** A shared table's auto-incrementing id "exceeded the size that can be represented by the MySQL Integer type (Rails int(11)): 2147483647". Inserts failed, Rails raised `ActiveModel::RangeError`, and the API returned HTTP 500 for two hours and 24 minutes. Its report says its monitoring "currently" alerts "when tables hit 70% of the primary key size used". The report does not say whether this table had that alert. Afterwards it added a linter for "int / bigint foreign key mismatches".

- **Basecamp.** Its "very busy events table" hit "the ceiling of 2,147,483,647", and Basecamp 3 was read-only from 7:21am to 12:11pm CST. Rails had changed its default key type in version 5.1, lifting the headroom to 9,223,372,036,854,775,807, and the fix was that same change. The postmortem does not name the database engine.

What you see on PostgreSQL is one of two errors. A `serial` or identity column's sequence stops with `nextval: reached maximum value of sequence "%s" (%lld)`, SQLSTATE 2200H. A larger value written into an `integer` column fails with `integer out of range`, SQLSTATE 22003. Where you meet it is often your ORM's default. Django's `DEFAULT_AUTO_FIELD` defaults to `django.db.models.AutoField`, an IntegerField, 32 bits wide, that increments by itself, and `BigAutoField` is the 64-bit form. A project made with `startproject` sets `BigAutoField` in its own settings file, from the 5.2 project template, `settings.py-tpl` line 122. So the 32-bit key reaches projects whose settings file does not set it. Check the setting in every Django project you own.

Watch the headroom before it is an outage. `pg_sequences` has the last value and the maximum of every sequence:

```sql
SELECT schemaname, sequencename, data_type, last_value, max_value,
       round(100.0 * last_value / max_value, 1) AS pct_used
  FROM pg_sequences
 WHERE last_value IS NOT NULL
 ORDER BY pct_used DESC;
```

An identity column also draws from a sequence, so it appears here too, which is inferred from the docs for identity columns. The arithmetic shows why a percentage alert is needed:

```text
integer key from empty, at an example rate of 1,000 inserts a second
2,147,483,647 / 1,000 / 86,400            = 24.9 days
left after GitHub's 70% alert              0.3 x 24.9 = 7.5 days
```

The fix is slow, which is the decision it changes. `ALTER COLUMN id TYPE bigint` rewrites the table and its indexes under ACCESS EXCLUSIVE. The reason is that the cast from `int4` to `int8` is a function, so it is not binary coercible. Every foreign key column that points at the key needs the same change, which is why GitHub added its linter. So widen a key with the expand/contract steps of the section above:

- Add `id_new bigint`, and write it on every insert and update.

- Backfill `id_new` in batches.

- Build a unique index on `id_new` with `CREATE UNIQUE INDEX CONCURRENTLY`. Then make `id_new` NOT NULL with the CHECK, VALIDATE and SET NOT NULL steps of the NOT NULL section.

- Swap in one short ACCESS EXCLUSIVE step: drop the old primary key, rename the columns, and add the primary key `USING INDEX`.

- Drop the old column in a later release.

Without that NOT NULL, ADD PRIMARY KEY USING INDEX scans the table for NULLs under ACCESS EXCLUSIVE, from the 17 ALTER TABLE page. Steps 1 to 3 are additive. Step 4 needs a reverse plan of its own, and step 5 has none. That plan is inferred from the two sections and was not run. The cheaper rule is for new tables: use `bigint`, or `bigint GENERATED ALWAYS AS IDENTITY`, from the start.

  Bound every lock wait with lock_timeout, and keep each step additive until a separate contract.

  An instant ADD COLUMN with no lock_timeout kept a one-row SELECT waiting 4.04 s.

  Run the pg_sequences query on a database you own, and find the fullest integer key.

You can now explain the 9-second report and the 11-minute outage of the opening case. The next section collects what the course leaves you with.

<details><summary>Go deeper: the compatibility window as a grid, the reverse of each step, two team policies, and the cast behind the key rewrite</summary>

### The compatibility window

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

### The expand/contract steps with their reverses

This is what `migrate_lab.py --plan` prints for every step:

  Step | Reverse | What the reverse loses

  expand: ADD COLUMN queue | DROP COLUMN queue | the queue values, which the backfill can compute again

  switch: new code writes queue | deploy the old code | nothing

  backfill | none needed | nothing: the column is still nullable

  check: CHECK NOT VALID | DROP CONSTRAINT | nothing

  validate | dropping the CHECK undoes it | nothing

  not null: SET NOT NULL | DROP NOT NULL | nothing

  contract: DROP the CHECK | ADD the CHECK NOT VALID again | nothing

Every step of this plan is additive, so the whole plan can be undone. A plan that renames or retypes a column has a destructive last step: dropping the old column. Keep it as a separate migration, released after the waiting period. `--rollback-after` follows the code-first order.

### Why each destructive step has no reverse

A type change that narrows a column fails, or with a `USING` expression it converts and loses the original values. A rewrite in place replaces the old values, and the new values do not say what the old ones were. DROP COLUMN's bytes stay on disk until rows are rewritten, but no SQL reads them. So treat a destructive step as having no reverse at all.

### Two team policies

strong_migrations has a six-step recipe for a type change and a rename. Create the new column, write both, backfill, move reads, stop writing the old one, then drop it. James Coleman's Braintree draft states the rollback policy in one line: "Rollback strategies do not involve reverting the database schema to its previous version." Before a DROP COLUMN reaches production, the same draft requires proof that no code references the column. GitLab works the same way. Its migration guide says that on its production environments, "a roll-forward strategy is used instead of rolling back migrations".

### The cast behind the key rewrite

The ALTER TABLE docs skip the rewrite only when "the old type is either binary coercible to the new type" or a domain over it. The cast from `int4` to `int8` is the function `int8(int4)`, with `castmethod => 'f'`, so it is not binary coercible.

</details>

<details><summary>Evidence</summary>

That DROP COLUMN "does not physically remove the column" is from the PostgreSQL 17 ALTER TABLE page. The six-step recipe is from the strong_migrations README. The rollback line and the DROP COLUMN proof are from James Coleman's 2019 draft gist. The roll-forward rule is from GitLab's migration style guide. The 4.04 s in the trap is the course research's three-session run on PostgreSQL 14.24. The Linear case is its report of 2024-01-24, and the Resend case its report of 2024-02-21. The key ranges are from the 17 docs, section 8.1. The GitHub case is its availability report of 2020-07-08, about an incident on 2020-05-05. The Basecamp case is DHH's postmortem of 2018-11-12, about an outage on 2018-11-09, and the Rails change was in version 5.1 in 2017. The two errors are `sequence.c` REL_17_11, line 748, `int.c` line 807 as one example, and `errcodes.txt` lines 191 and 192. The Django setting is from the Django 5.2 settings and model field pages. The `pg_sequences` columns are `system_views.sql` REL_17_11, lines 167 to 187. The cast is `pg_cast.dat` REL_17_11, lines 41 and 42.

</details>

## What the course leaves you with

The 9-second report and the 11-minute outage now each have a cause you can name in advance. The report's estimate came from statistics older than the incident, so ANALYZE fixed it and an index could not. The outage came from a SHARE lock held for a whole build. `CREATE INDEX CONCURRENTLY` with a `lock_timeout` would most likely have kept checkout running.

- A plan goes wrong at the lowest node where estimate and actual differ, and `auto_explain` gives you the plan that really ran. Taught in the first two sections.

- An estimate comes from `pg_stats` at the last ANALYZE, so every bulk change and every move ends with ANALYZE. On a direct connection, a psycopg statement can get the generic plan from its eleventh run. Behind PgBouncer, each server connection keeps its own count, which is inferred and was not run. Taught in the estimates and generic-plan sections.

- The planner prices every path from estimates, so a low outer estimate makes a nested loop look cheap. Each index shape fits one query, and each costs something on every write. Taught in the scan, index and join sections.

- VACUUM frees only versions that died before the oldest snapshot, and the 17 log names that snapshot in its `removable cutoff` line. Old data leaves cleanly by partition. Taught in the VACUUM, wraparound and partitioning sections.

- Every schema change waits in a queue that blocks traffic, so each one gets a `lock_timeout`. Steps stay additive until the contract, and new keys get 64 bits. Taught in the last three sections.

The next phase, Phase 5, answers what a replica has and what fails over, in 5.1 to 5.3. It also covers backups in 5.6 and pooling in 5.7. Safe rollout, with canaries, feature flags and rollout gates, is course 6, "Reliability, security and change", Phase 3. Schema changes that break another service's contract are course 7, "System design and architecture", Phase 2. Splitting a table across servers is course 5, Phase 3.

### The course's storage note

The course closes with one page. It says what the course's system guarantees, what it does not, and how you know. The system is the order store of Phases 1 and 2, and the order data and task queue in PostgreSQL 17. This note covers Phases 1 to 4. Phase 5 teaches replicas, backups and pooling, so add their rows after that phase. A guarantee belongs in the note only with the test that would show it false. No test below was run by its writer, so each "how you know" cell gives the result to expect.

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

  Area | What it guarantees | What it does not | How you know, and status

  Durability, Phase 1 | A put that returned OK with `--sync full` survives a process crash, an OS crash and a power loss. Recovery returns a prefix of the puts in log order, and never an entry that fails its CRC | Damage to data already synced, a drive that ignores flush commands, loss of the device. With plain `os.fsync` on macOS, a power loss, from Apple's `fsync(2)` | `crash_matrix.py`: 0 violations in 231 recoveries, and 42 power violations for the false claim of `--sync fsync --claim-power-safe`. Worked out from the code, not run

  Structure, Phase 2 | The log layout writes 1.18 bytes per byte. With filters, both layouts read about one block per present key | The log's space grows with every overwrite: 11.77 times the live data on the write-heavy mix. The LSM writes about 14.7 bytes per byte | `amplification.py`, E6 of Phase 2. Worked out from the code and its seed, not run. Move to the LSM when disk, not write volume, is the limit

  Isolation, Phase 3 | The task claim, the approval and the outbox write keep their invariants at READ COMMITTED, with one conditional statement each. The approvers' rule holds at SERIALIZABLE with a retry of the whole transaction on 40001 | REPEATABLE READ allows write skew: 0 approvers on call. No level fixes a relay that tracks ids. The outbox delivers at least once, so consumers drop duplicates | `write_skew.py` and `taskqueue.py`, E5, E10 and E11 of Phase 3. Each check exits 1 at the old level, and the relay check at every level. Not run

  Plans, Phase 4 | Every bulk load, backfill or bulk update ends with `ANALYZE` of its table, and so does every move to a new cluster. A slow query is found with `pg_stat_statements`, and its plan is taken from `auto_explain`. A plan regression is first checked by comparing estimated and actual rows | Autovacuum's ANALYZE comes only after 50 + 0.1 × reltuples changed rows, and only when a worker reaches the table. Partitioned parents are never analyzed by it. A prepared statement can switch to a generic plan after five executions, unless `plan_cache_mode` forbids it | `plan_lab.py`, E4: est 1 against 400,000 before ANALYZE, close after. `plan_cache.py`, E13: generic from execution 6. `find_slow.py`, E14. Not run

  Change, Phase 4 | Every DDL statement runs with `lock_timeout` and retries. A NOT NULL column goes in by expand/contract, and every step before the contract has a reverse that loses no data | A destructive step, such as DROP COLUMN, has no reverse. A transaction left open still delays every migration on its tables. An `integer` key runs out at 2,147,483,647 unless its headroom in `pg_sequences` is alerted on | `migrate_lab.py`, E10 and E11: failures with the naive plan, 0 failed requests and lock waits near 100 ms with expand/contract. Not run

  Not covered |  | Operator deletion and failed backups, the GitLab case of Phase 1. Replicas and what a replica has, Phase 5 in 5.1. Backups and point-in-time recovery, Phase 5 in 5.6. Transaction ID and multixact wraparound, unless `age(datfrozenxid)` and `mxid_age(datminmxid)` are alerted on, as the wraparound section showed | the alert queries of `bloat.py --xid`. Not run

The note is one page because each line points to its evidence instead of repeating it. When a test runs and disagrees with its cell, the cell changes, not the test. E12 in the lab asks you to fill in the template for a system you own.

## Lab

Twenty exercises, in the phase's own order and copied from it. E4, E10 and E11 are the phase's demonstration. They were written and reviewed for PostgreSQL 17, and not run against a server by their writer. Each idea of the lesson has its exercises:

Idea | Exercises

Where a plan went wrong, and finding it in production | E14, E15

Estimates from the last ANALYZE, generic plans, drivers and poolers | E4, the correlated case of E5, E13, E18

Scans, index shapes and joins priced from estimates | E2, E3, E17, the join methods of E5

VACUUM, wraparound and partitioning | E6, E7, E8, E16, E19

Lock waits, expand/contract, MySQL and rollback | E9, E10, E11, E20

The whole course | E1, the self-tests, and E12, the storage note

<details><summary>Open the lab: setup, the files, and E1 to E20</summary>

The lab text is copied from the phase, which numbers its sections. They are 4.1 reading plans, 4.2 estimates, generic plans, drivers and poolers, 4.3 access paths, 4.3b index types, 4.4 joins, 4.5 VACUUM and wraparound, 4.6 partitioning, 4.7 migrations and 4.8 rollback.

**The running system.** The lab tables carry the prefix `p4_`, so the labs of earlier phases keep working. `p4_orders`, `p4_order_events` and `p4_tenants` hold the order data of the opening case at 1 million orders. `p4_tasks` has the columns of Phase 3's `tq_tasks`, the course's own task queue.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. The labs need a local PostgreSQL at `/tmp:5432`, in the database `storage_lab`, with psycopg 3.3.6 from `pyproject.toml`. They are written for PostgreSQL 17. The course review of 2026-10-20 found only Homebrew `postgresql@14` on this Mac, so install `postgresql@17` to match your work servers. Every exercise also runs on 14 and says what differs. The one exception is the SERIALIZE and MEMORY step of E15, which needs 17. `cost_model.py`, `locks.py --predict` and every `--self-test` run with no server. Run all commands from `elite-storage/code/`.

Time: 3.5 hours for the reading. The labs take longer, about 4 hours.

The labs below are written and reviewed, but were not run by the author against a server. They target PostgreSQL 17. Every `--self-test` was run on 2026-10-20 and passed, and those tests use no server. Every "Expected" line says "Not run by the author yet." and then gives the expected shape, written from the 17 source and docs. Each number in it has one of three sources. It is a cited source, or arithmetic in this phase. Or it is a measurement by the course research on PostgreSQL 14.24, with its conditions. Plan choices and counts should match closely. Times depend on your machine, and none of them is claimed. Where 14 prints something different, the exercise says so.

**What you build.** Eleven files in `phase04_planning/`. They reuse `shared/pglab.py` from Phase 3 and change no earlier file:

File | What it holds | Self-test checks

`explain_tools.py` | EXPLAIN JSON as nodes: est, actual × loops, q-error, buffers, before and after. Parallel nodes, the JIT block, spill lines, and the SERIALIZE and MEMORY groups of 17. `--server-defaults`, `--set`, `--serialize`, `--memory` | the 17 docs' nested-loop plan and its 118.38 arithmetic, Leis's q-error example, a bad plan's worst node, BUG #19076's parallel plan, the divisor 2.4, the 17 JIT and SERIALIZE shapes

`find_slow.py` | `pg_stat_statements` rankings, a setup check, and an `auto_explain` demo | the missing setup steps, the plan-changer ranking, the auto_explain settings

`plan_cache.py` | a prepared statement's custom plans, then its generic plan, on skewed tenants. `--via-driver` lets psycopg prepare it | the five-execution rule, the planning charge, the generic estimate, the data's skew, the driver thresholds 11 and 10

`cost_model.py` | the row-estimate and scan-cost formulas of `selfuncs.c` and `costsize.c` | every worked number of docs 68.1, the 445 and 470 of the 17 docs and the 458 and 483 of the 14 docs, the research's 21846.00 and switch points

`access_paths.py` | the selectivity sweep of section 4.3 on your server | the bound k, the build SQL

`index_types.py` | the six index shapes of section 4.3b on one order table: size, plan, buffers | the data's 1-in-1,000 pending share, BRIN entries per 128 pages, the leftmost-column rule on the docs' example, the partial index and a parameter

`plan_lab.py` | stale statistics, the diagnosis, the fix, extended statistics, join methods | the 400,000 pending rows, the 1-row estimate, the analyze threshold

`bloat.py` | dead versions, a held snapshot, VACUUM FULL's lock, transaction ID and multixact ages, the autovacuum budget and signals on 14 and 17, and a reader for VACUUM log entries | the limits from `varsup.c`, the vacuum threshold and its 18 cap, the shared budget, nine pages per nap, the 17 progress columns, the 17 and 14 log formats

`partitions.py` | pruning at plan time and executor start, parent statistics, DROP against DELETE, and the fast-path split of one query's locks | month bounds, which partitions a range keeps, 880 locks at 40 × 22, 16 slots on 17 and 64 on 18

`locks.py` | the conflict table, `--predict`, the lock queue offline and live, Joyent's wraparound queue | the docs' conflict lists, 14 statements, the queue scenarios, a normal against a wraparound autovacuum

`migrate_lab.py` | three NOT NULL plans under an open-loop load, with lock_timeout and retries | the lint finds the naive plan's 3 faults, each rule removed fails a check

Every PostgreSQL lab refuses a database whose name does not start with `storage_lab`, through `shared/pglab.py`. It creates and drops only tables that start with `p4_`. The demonstration of this phase has two parts. E4 diagnoses and fixes a plan, with buffers and time before and after. E10 and E11 run the migration under load, with the lock waits measured.

-  **E1** offline  Run every self-test of this phase, then those of the earlier phases.

- Run: `for f in phase04_planning/*.py; do echo "$f"; uv run python "$f" --self-test; done`

- Then run: `for f in shared/*.py phase01_durability/*.py phase02_structures/*.py phase03_transactions/*.py; do echo "$f"; uv run python "$f" --self-test; done`

- Expected: `self-test passed` after each of the 11 Phase 4 files, and after each of the 28 earlier scripts. The author ran both loops on 2026-10-20, and all 39 passed. The second loop also runs `shared/__init__.py`, which is empty and prints nothing. An earlier version of this exercise said 20 earlier scripts. On 2026-10-20 the four folders hold 29 files: 28 scripts and the empty `shared/__init__.py`.

- If it fails: the assertion message names the formula or the rule. Compare it with the section it comes from before you change any code.

- Teaches: each rule that the text calls important has a check that fails without it.

-  **E2** offline  The planner's arithmetic, by the model.

- First write your prediction for the research table at 1 row, 1%, 40% and 45%, from section 4.3.

- Run: `uv run python phase04_planning/cost_model.py --sweep`, then add `--random-page-cost 1.1`, then run it with `--correlation 1.0`.

- Expected: Not run by the author yet. The default sweep picks Index Scan at 0.0001%, Bitmap Heap Scan from 0.001% to 40%, and Seq Scan from 45%. The Seq Scan cost is 21846.00. At 40% the bitmap row shows about 21,338, and at 45% about 22,839. With 1.1, the Index Scan wins at 50%. With correlation 1.0, the Index Scan wins at 10%, about 3,664 against 12,347.

- Teaches: the switch points come from pages, rows and correlation, and the model shows which term decides.

-  **E3** local  The same sweep on your PostgreSQL 17.

- Run: `uv run python phase04_planning/access_paths.py`, then `--skip-build --random-page-cost 1.1`, then `--correlated`, then `--covering --analyze`, then `--pad-bytes 400`.

- Expected: Not run by the author yet. The header shows your page count. With the default 40-byte pad, the arithmetic below gives about 10,300 pages, close to the research's 9,346. Expect the same order of plans: Index Scan, Bitmap Heap Scan, Seq Scan. The `model` column agrees, except where two costs are within a few percent. `--correlated` shows Index Scan over a wide range. `--covering` shows Index Only Scan, and its `read` column stays low after VACUUM. With 400-byte pads, a row takes about 444 bytes of its page instead of about 84. So the table has about five times the pages, and the switch should move. These sizes are inferred from the PostgreSQL 17 docs, section 65.6, which was 70.6 in 14. A row header is 23 bytes, padded to 24, and each row adds a 4-byte line pointer. They were not measured.

- If the switch differs from the research's: compare your rows per page and correlation with section 4.3 first.

- Teaches: the research's switch points belong to its table, not to PostgreSQL.

-  **E4** break-it, local  Part of the demonstration: break the statistics, diagnose, fix.

- First predict the estimate for `pending` after the incident, from section 4.2.

- Run: `uv run python phase04_planning/plan_lab.py`.

- Expected: Not run by the author yet. `400,000 orders are now pending (expected 400,000)`. `pg_stats` shows three values whose frequencies add up to 1, and the formula line gives a selectivity of 0. The plan's scan of `p4_orders` shows est 1 and actual 400,000. The plan is expected to be a Nested Loop whose inner Index Scan on `p4_order_events` shows 400,000 loops. `team-fix` still shows est 1. After `fix`, the estimate is near 400,000 and the join is expected to be a Hash Join. The before-and-after table shows the plan shapes, the worst q-error, the buffers and the execution time. The last line is `RESULT: worst q-error 400,000 before`, then a value under 10 after, and `Fixed`. The plan choices are expected from the cost model, not run.

- If the first plan is already a Hash Join: your cost settings differ from the defaults. Check `show random_page_cost` and `show work_mem`, and note it. The estimate of 1 row is still the lesson.

- Teaches: one stale MCV list turns 400,000 rows into 1, and ANALYZE, not an index, fixes it.

-  **E5** local  Correlated columns and the three join methods.

- Run: `uv run python phase04_planning/plan_lab.py --case correlated`, then `uv run python phase04_planning/plan_lab.py --case join-methods --skip-build --analyze`.

- Expected: Not run by the author yet. Correlated: est 1 and actual 100 before, est 100 after, and the GROUP BY estimate 1000 before and 100 after. The course research saw exactly these on 14.24. Join methods: three outer sizes, each with four rows. The `planner` row's cost equals the lowest of the three forced rows. At 10 outer rows, expect a nested loop to be cheapest. At the full table, expect a hash join.

- Teaches: the independence assumption and its fix. The planner's join is the cheapest by its own estimates.

-  **E6** break-it, local  Bloat behind one open transaction.

- Run: `uv run python phase04_planning/bloat.py --held-rounds 3 --pgstattuple`.

- Expected: Not run by the author yet. The page counts follow the bar chart of section 4.5. They are about 1x at the load, and 2x after the first UPDATE, the VACUUM and the second UPDATE. The first held round grows the file to about 3x. Its VACUUM still frees the versions that died before H's snapshot, so the second held round reuses that space. The third held round grows the file to about 4x. After H commits, VACUUM frees space, and the next UPDATE does not grow the file. VACUUM FULL brings it back to about 1x. The SELECT during VACUUM FULL takes about as long as VACUUM FULL itself, because ACCESS EXCLUSIVE blocks it.

- If `pgstattuple` is missing: the script says so and uses `pg_stat_user_tables` only.

- Teaches: VACUUM removes only what died before the oldest snapshot, and it never shrinks the file.

-  **E7** local  Transaction ID ages and the limits.

- Run: `uv run python phase04_planning/bloat.py --xid`.

- Expected: Not run by the author yet. The settings line shows `autovacuum_freeze_max_age 200000000` and `vacuum_failsafe_age 1600000000`, the PostgreSQL 17 defaults, which are the same as 14's. A laptop cluster shows small ages, so each distance is close to its limit. For an age near 0, the stop is about 2,144 million away. The lists of old sessions, slots and prepared transactions are short or empty.

- Teaches: what to alert on, long before the WARNING.

-  **E8** local  Pruning, and what partitioning costs the planner.

- Run: `uv run python phase04_planning/partitions.py --planning-sweep 12,120,1200`.

- Expected: Not run by the author yet. `prune`: 1 partition scanned, expected 1. `no-key`: 12 of 12. `generic`: `Subplans Removed: 11`. `parent-stats`: 0 rows before ANALYZE and some after. `unique`: an ERROR line from the server. `drop`: the DELETE leaves about 100,000 dead rows, one twelfth of 1,200,000, and the DROP none. The planning sweep is expected to grow with the partition count. No time is claimed.

- Teaches: pruning comes from the partition key only, and unpruned partitions cost planning time.

-  **E9** break-it, offline, then local  The lock queue, predicted and then reproduced.

- First run: `uv run python phase04_planning/locks.py --table`, then `--scenario queue`, then `--scenario queue-timeout`, then `--scenario fk`.

- Then run: `uv run python phase04_planning/locks.py --live queue --lock-timeout 0`, then `--live queue --lock-timeout 100ms`, then `--live fk --hold-s 5`.

- Expected: Not run by the author yet. The offline queue shows C `granted=False` behind B, and A's commit waking B first. With the timeout, B's exit wakes C. The fk scenario grants the SELECT and queues the INSERT. Live, with a timeout of 0, the later SELECT takes about 4 s, close to the research's 4.04 s. The `obs` lines show B `granted=false` with ACCESS EXCLUSIVE, and C blocked by B. With 100ms: B fails with 55P03 after about 0.1 to 0.2 s, and C takes well under a second. The research measured 0.18 s and 0.07 s. The fk run: the SELECT is fast, and the INSERT takes about 3 s.

- Teaches: a queued request blocks every later conflicting request, and lock_timeout bounds that block.

-  **E10** break-it, local  Part of the demonstration: the naive migration under load.

- First predict the failed requests, with the arithmetic of section 4.7.

- Run: `uv run python phase04_planning/migrate_lab.py --plan --strategy naive`, then `uv run python phase04_planning/migrate_lab.py --strategy naive --hold-lock-s 5; echo "exit $?"`.

- Expected: Not run by the author yet. The plan's lint lists 3 problems. The run's `all-in-one` row shows failures with 57014 and `late`. They are most of the about 2,000 requests scheduled during the hold. The lock wait max is near 1,000 ms, because each request gives up at its 1-second deadline. The `after` row shows 23502 failures, about 100 per second, because the old code inserts no `queue`. The RESULT line counts the failures, and the exit code is 1.

- Teaches: one instant ALTER behind one open transaction stops the table. A NOT NULL column breaks the code that does not write it.

-  **E11** local  Part of the demonstration: expand/contract with no failed request. Then two ways to break it, and a rollback.

- Run: `uv run python phase04_planning/migrate_lab.py --strategy expand-contract --hold-lock-s 5; echo "exit $?"`.

- Expected: Not run by the author yet. The `expand` step shows about 9 attempts and 8 lock timeouts, from the backoff arithmetic of section 4.7. Every phase row shows 0 failed. The max latency stays near 100 ms plus the request's own time, and the lock wait max near 100 ms. The backfill shows 201 or 202 batches. 200 cover the loaded rows. The rest cover about 1,000 rows that the writers inserted first, at about 100 per second for about 10 s. `RESULT: ... 0 failed. queue NOT NULL: True. Rows without a queue: 0. Rows with the wrong queue: 0`, and the exit code is 0.

- Then run: `uv run python phase04_planning/migrate_lab.py --strategy expand-contract --old-writers 2 --break-compat; echo "exit $?"`. Expected: 23514 failures from the `check` phase on, the old code's inserts. Then `step validate failed` with 23514, and exit 1.

- Then run: `uv run python phase04_planning/migrate_lab.py --strategy expand-contract --rollback-after check`. Expected: three reverse lines, the CHECK dropped, the writers switched back and the column dropped, then `Column present: False`, with 0 failed.

- Teaches: bounded lock waits and a compatibility window add a NOT NULL column with no failed request. Undo runs code first, schema second.

-  **E12** written  Write the course's storage note.

- Do: fill in the template of the next section for a system you own. Or check the filled note against your own lab results.

- Expected: one page. Every "how you know" cell names a test and says whether you ran it.

- Teaches: a guarantee is a sentence plus the test that would show it false.

The four exercises below cover the production signals of sections 4.1, 4.2, 4.4 and 4.5. They come after the storage note because none of them is part of the demonstration.

-  **E13** break-it, local  A prepared statement switches to a generic plan.

- First predict, from section 4.2, at which execution the plan changes. Also predict the generic plan's estimate for the largest tenant.

- Run: `uv run python phase04_planning/plan_cache.py`, then `uv run python phase04_planning/plan_cache.py --skip-build --mode force_custom_plan`.

- Expected: Not run by the author yet. The header prints the generic estimate, about 1,000 orders, which is 1,000,000 / 1,000 tenants. It also prints tenant 1's real count, about 100,300. Executions 1 to 5 show `custom`, with est close to actual, about 1,600 to 2,900 orders. Executions 6 and 7 show `generic`, with est about 1,000 and actual about 100,300 for tenant 1. The counters end at 2 generic and 5 custom. The generic plan is expected to be a Nested Loop, and `force_custom_plan` a Hash Join. Those plan shapes are inferred from the join arithmetic of section 4.4. With `--mode force_custom_plan`, every row shows `custom`.

- If no generic plan appears: the script prints that the generic cost was not below the custom average. Compare the printed estimates, and note it. The estimate of the generic plan is still the lesson.

- Teaches: a generic plan uses the average over all values, and `plan_cache_mode` controls it.

-  **E14** local  Find the slow query, then its plan, the way you would at work.

- Run: `uv run python phase04_planning/find_slow.py --check`. Add the line it prints to `postgresql.conf`, the file that `psql -h /tmp -d storage_lab -c "show config_file"` names. Restart the server the way you started it, then run `psql -h /tmp -d storage_lab -c "create extension pg_stat_statements"`. To undo the setup later, remove the line and restart again.

- Then run: `uv run python phase04_planning/plan_lab.py`, then `uv run python phase04_planning/find_slow.py --top 5`, then `uv run python phase04_planning/find_slow.py --auto-explain-demo`.

- Expected: Not run by the author yet. `--check` lists `shared_preload_libraries` as missing on a default install. After the restart and the CREATE EXTENSION, it prints `pg_stat_statements is ready`. The first ranking shows the lab's build statements and its report near the top by `total_exec_time`. The demo prints a line that starts with `duration:`, then the plan of the report. It has buffers and no per-node times, because `log_timing` is off.

- If LOAD fails: your role is not a superuser. The demo needs one, and the rankings do not.

- On RDS or Aurora: you cannot edit `postgresql.conf`. On RDS for PostgreSQL 11 or later, AWS says the library is loaded by default, so run only the CREATE EXTENSION step. If `SHOW shared_preload_libraries` does not list it, add it in a custom parameter group and reboot, as section 4.1 says. Then the `--check` and `--top` steps work the same. Not run on RDS.

- Teaches: find the query by its server time, then take the plan it really ran.

-  **E15** local  The plan your server makes, with parallel workers, JIT and a spill.

- Run, after E4: `uv run python phase04_planning/explain_tools.py --server-defaults --sql "select tenant_id, count(*) from p4_orders group by tenant_id"`. Then run the same without `--server-defaults`. Then run `uv run python phase04_planning/explain_tools.py --set work_mem=64kB --sql "select * from p4_orders order by amount_cents"`.

- Then run, on 17: `uv run python phase04_planning/explain_tools.py --serialize --memory --sql "select * from p4_orders"`.

- Expected: Not run by the author yet. With `--server-defaults`, expect a Gather with `Workers Planned: 2`. Below it, expect a partial aggregate and a Seq Scan marked `per process, divisor 2.4`, with 3 loops. Without the flag, the same query has no Gather. A `JIT:` line appears only if the plan's cost passes 100,000 and the server has LLVM. `p4_orders` at 1,000,000 rows is about a tenth of the opening case, so its cost may stay below that. With `work_mem=64kB`, the Sort's line shows `Sort Method: external merge` and `Sort Space Type: Disk`. The `--serialize --memory` run ends with a `Serialization:` line, with a time and an output size in kB, and a `Planning memory:` line. On 14, that run stops with `LAB ERROR: SERIALIZE and MEMORY are new in PostgreSQL 17`. These shapes are inferred from sections 4.1 and 4.4 and the 17 source.

- Teaches: the lab's serial plans are a choice, your server's plans read differently, and the output conversion has its own cost.

-  **E16** break-it, offline, then local  The autovacuum budget, the forced vacuum that does not give way, and the 17 signals.

- Run: `uv run python phase04_planning/locks.py --scenario autovacuum`, then `--scenario wraparound`. Then run `uv run python phase04_planning/bloat.py --vacuum-signals`.

- Then, after E6: `psql -h /tmp -d storage_lab -c "VACUUM (VERBOSE) p4_bloat" 2> vacuum_verbose.txt`, and `uv run python phase04_planning/bloat.py --parse-log vacuum_verbose.txt`. VERBOSE sends its block to the client as INFO messages, which psql writes to stderr. To read autovacuum entries instead, give `--parse-log` the server log that `SELECT pg_current_logfile()` names.

- Expected: Not run by the author yet. `autovacuum`: D and S queue, then the deadlock check cancels the autovacuum, D runs, then S. `wraparound`: the autovacuum is not cancelled, and S runs only after it finishes. `--vacuum-signals` prints `server_version_num 170011` or your minor, the settings of section 4.5, and a budget of "67 each when all 3 run", which is 200 / 3 rounded. It prints the ceilings of 781.2 and 35.5 MB/s. On 17 it prints that `log_autovacuum_min_duration` is 600,000 ms, so only runs of 600 s or longer are logged. The p4_ tables appear with their dead-row counts. No vacuum is running on a quiet laptop, so the `pg_stat_progress_vacuum` list is empty, and the query runs with the 17 columns. The `pg_stat_io` lines show the vacuum I/O since the last reset. `--parse-log` prints two rows: one for `p4_bloat`, and one for its TOAST table `pg_toast.pg_toast_<oid>`. Each row has a horizon age from the `removable cutoff` line. Then a `RESULT` line counts 2 entries. On 14, VACUUM VERBOSE prints a different block, so the script finds no entries. On a 14 autovacuum log, the age column says `n/a (14)`.

- If it fails with `column p.max_dead_tuples does not exist`: you run an old copy of `bloat.py`. The 17 server renamed that column, as section 4.5 says.

- Teaches: more workers share one budget. A wraparound vacuum turns any DDL without a `lock_timeout` into an outage. On 17 the horizon has its own log line, with its age.

The four exercises below cover the new topics of sections 4.2, 4.3b, 4.6 and 4.7.

-  **E17** local  Six index shapes on one table.

- First predict, from section 4.3b, which index each of the six cases uses, and which query of the partial case gets none.

- Run: `uv run python phase04_planning/index_types.py`, then `uv run python phase04_planning/index_types.py --skip-build --case brin`.

- Expected: Not run by the author yet. `partial`: `p4_ix_status` points to 1,000,000 rows and `p4_ix_pending` to about 1,000. B-tree deduplication, on by default, stores each status value once per posting list. So `p4_ix_status` is near 800 pages, and its page count is likely more than a hundred times that of `p4_ix_pending`. That is inferred. The queue query uses `p4_ix_pending` with a Limit. The generic plan for `$1` does not list `p4_ix_pending` among its indexes. `composite`: while only `(tenant_id, status)` exists, the status-only query likely reads all of `p4_ix_ts` with an Index Only Scan. The index is narrow and the table is wide, so the full index scan costs less than a Seq Scan. That is inferred from the cost formulas. Then it lists `p4_ix_st`, with far fewer buffers. `covering`: an Index Only Scan with `Heap Fetches: 0`, then above 0 after the UPDATE. `expression`: no index used with the plain index on `email`, then `p4_ix_lower_email`. `gin`: a Bitmap Index Scan on each GIN index. `brin`: the BRIN index is a few pages against thousands for the B-tree. With only BRIN, the plan is a Bitmap Heap Scan with `Rows Removed by Index Recheck` above 0. These shapes are inferred from the docs and the cost rules of section 4.3.

- If the composite case shows `p4_ix_ts` for status alone: the planner chose a full index scan, which the docs allow. The node can be an Index Only Scan or a Bitmap Index Scan. Compare its buffers with the `p4_ix_st` run.

- Teaches: each index shape wins for one query shape, and the planner proves a partial index's predicate at planning time only.

-  **E18** break-it, local  The driver prepares the statement, and the plan changes later than you think.

- First predict, from section 4.2, the execution at which psycopg's statement first uses the generic plan.

- Run, after E13: `uv run python phase04_planning/plan_cache.py --skip-build --via-driver`, then the same with `--driver-threshold 1`.

- Expected: Not run by the author yet. With the default threshold of 5: executions 1 to 5 print `not prepared`. Execution 6 prints a statement named `_pg3_0` with `custom_plans 1`. Executions 7 to 10 raise `custom_plans` to 5. Execution 11 is expected to show `generic_plans 1`, as in E13, and the `RESULT` line names it. With `--driver-threshold 1`, the statement is prepared at execution 2, and the first generic plan is expected at execution 7. Those executions follow from psycopg 3.3.6's source and the server rule of section 4.2.

- If execution 11 still shows a custom plan: the server kept custom plans, because the generic plan did not cost less than their average. Compare with E13 on the same data.

- Teaches: the five custom plans count per server session, after the driver's own threshold.

-  **E19** local  Count one query's locks on the partitions.

- First compute, from section 4.6, the relation locks of a query that keeps 12 partitions with 4 indexes each, and how many fit in the fast-path slots on 17.

- Run: `uv run python phase04_planning/partitions.py --locks --extra-indexes 3`.

- Expected: Not run by the author yet. The model line says 61 relation locks, 16 fast path and 45 in the shared lock table, at `max_locks_per_transaction` 64 on 17. The `pg_locks` lines show `AccessShareLock` with `fastpath` true 16 times, and the rest false. The `RESULT` line compares the count with the model. The planner also locks the parent's 4 partitioned indexes, which the model does not count. So expect 65 relation locks: 16 with fastpath true and about 49 with fastpath false. That count is inferred from plancat.c at REL_17_11, lines 215 to 253, and was not run. On 18, the fast-path count is expected up to 64.

- Teaches: a query on a partitioned table pays one lock per partition and per index, and only 16 of them are cheap on 17.

-  **E20** written  The same migration on MySQL.

- Do: write the MySQL 8.4 form of the expand/contract plan of section 4.7 for `queue NOT NULL`. For each step, say whether `ALGORITHM=INSTANT` can do it, which metadata lock it takes, and what `lock_wait_timeout` you set. Then say which step you would hand to gh-ost on a table of 1 billion rows, and why.

- Expected: one page. Every claim names the MySQL 8.4 manual page or the gh-ost README it rests on, as the box of section 4.7 does.

- Teaches: the lock queue rule holds in both engines. Only the names and the defaults change.

</details>

<details><summary>Open "Check it yourself": six readings of the lab's code</summary>

- **Check 1.** Open `phase04_planning/cost_model.py:198`, the body of `bitmap_scan()`. Compute the cost per page when the scan reads a quarter of the table's pages. Then use this line to explain a rule. A bitmap scan that reads every page is never cheaper per page than a sequential scan.

- **Check 2.** Open `phase04_planning/explain_tools.py:285`, `worst_node()`. It breaks a tie in q-error in favor of the deeper node. In the bad plan of its self-test, the Nested Loop and the Seq Scan have the same q-error of 400,000. Which node would a tie-break toward the top report, and why would that send you to the wrong fix?

- **Check 3.** Open `phase04_planning/locks.py:227`, `LockQueue.request()`. Suppose it checked only the granted locks and not the waiting ones. Which line of `scenario_queue` changes, and which self-test check fails? Is the model then closer to PostgreSQL or further from it, by the lmgr README's rule?

- **Check 4.** Open `phase04_planning/migrate_lab.py:376`, `run_statement()`. It retries only SQLSTATE 55P03. Suppose it also retried 57014, the statement timeout. Which step of the expand/contract plan could then run far longer than planned? Why is a statement timeout a different signal from a lock timeout?

- **Check 5.** In any repository you own that has database migrations, run `grep -rn "lock_timeout\|CONCURRENTLY\|NOT VALID\|DROP COLUMN" <your repo>/`. Find each migration that adds an index without `CONCURRENTLY`, or drops a column in the release that stopped using it. Name the lock it takes and the traffic it blocks. Then run `grep -rn "DEFAULT_AUTO_FIELD\|AutoField\|serial\b\|integer PRIMARY KEY" <your repo>/` and list every key that is 32 bits wide.

- **Check 6.** Open `phase04_planning/bloat.py:177`, `progress_vacuum_sql()`, and `bloat.py:231`, `parse_vacuum_log()`. Which line of the old E16 query fails on 17, and with which error? Then remove the regular expression for the `removable cutoff` line from `parse_vacuum_log()`, run `--self-test`, and name the check that fails. What would an operator lose on 17 if a log parser knew only the 14 format?

</details>

## Checkpoint

Eight scenario questions with numbers, from the phase. Each one is answerable from this lesson. Section numbers in them are the phase's, listed at the top of the lab.

<details><summary>Open the questions</summary>

The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

- **Test-out, explain.** On the research's table of section 4.3, `WHERE x < k` selects 45% of the rows. The planner chooses a Seq Scan over the B-tree on `x`. Explain why with the cost arithmetic of both paths. Then name the statistic that would change its mind, and show with numbers how it would.

- **Test-out, predict.** For each statement, give the lock it takes on `p4_tasks`. Say what it blocks while it waits and while it holds the lock. (a) `CREATE INDEX ON p4_tasks (state)`. (b) `CREATE INDEX CONCURRENTLY ON p4_tasks (state)`. (c) `ALTER TABLE p4_tasks ADD COLUMN note text DEFAULT 'none'`. (d) `ALTER TABLE p4_tasks VALIDATE CONSTRAINT p4_tasks_queue_not_null`. (e) `ALTER TABLE p4_tasks ALTER COLUMN attempts TYPE bigint`. Then take (c) with no `lock_timeout`, queued behind a transaction that has been open for 30 seconds. What happens to SELECTs?

- **Test-out, demonstrate.** Run E4, E10 and E11. Show the plan before and after ANALYZE, with its estimated and actual rows, buffers and time. Then show the naive migration failing requests and the expand/contract migration failing none, with the lock waits measured. Explain why each result follows from the sections, and not from timing luck.

- **A colleague says:** "We are on SSDs, so we set `random_page_cost = 1.1` for the whole cluster. The docs say so." Argue for or against. What do the PostgreSQL 17 docs say about this setting, and where does the 1.1 come from? What did the research's table show at 1.1? What should be measured before a cluster-wide change? (b) A second colleague says: "Autovacuum cannot keep up with `orders`. Raise `autovacuum_max_workers` from 3 to 6." Argue for or against, with the budget arithmetic of section 4.5. (c) A third colleague says: "Our report gets a bad generic plan. The service runs psycopg 3 behind PgBouncer 1.24 in transaction mode. I added `SET plan_cache_mode = force_custom_plan` at the start of the request, so it is fixed." Argue for or against, and give the change that does fix it.

- **This is broken.** `tq_outbox` gets 2 million inserts a day, and a job deletes sent rows every hour. VACUUM runs often, and `n_dead_tup` stays high. The table file grows by about 1 GB a day. `pg_stat_activity` shows one session `idle in transaction` since three days ago. What is the cause, how do you confirm it, and what is the fix? What do you do about the 3 days of growth? (b) On PostgreSQL 17, the autovacuum log for `tq_outbox` shows `tuples: 0 removed, 2100000 remain, 900000 are dead but not yet removable` and `removable cutoff: 812345, which was 25000000 XIDs old when operation ended`. The server assigns about 1,000 transaction IDs a second. Roughly how old is the snapshot that holds the horizon, and which query names its session?

- **Show the arithmetic.** (a) The autovacuum ANALYZE and VACUUM thresholds of a 50,000,000-row table, at the defaults. (b) `pg_stats` for a column shows `n_distinct` 20 and `null_frac` 0.02. Its MCV list has 4 values whose frequencies add up to 0.92. The table has 8,000,000 rows. Estimate `WHERE col = 'x'` for a value not in the list. (c) A PostgreSQL 17 database has `age(datfrozenxid)` = 1,500,000,000 and assigns 3,000 transaction IDs per second. How long until the WARNING, and until new IDs are refused? (d) A migration uses `lock_timeout = 200ms` and fails 6 times before it gets its lock. At most how long were the table's queries blocked by its attempts? (e) Take PostgreSQL 17 defaults, which are the same as 14's, and a table whose every page is read and dirtied. How many pages can autovacuum process per nap? What is the ceiling in MB/s for all workers together? How long does one pass over a 200 GB heap take at least? (f) `orders` has 10,000,000 rows. For `tenant_id`, `n_distinct` is 1,000 and `null_frac` is 0. The most common tenant has a frequency of 0.1. Estimate `tenant_id = $1` for a generic plan, and for a custom plan with that most common tenant. (g) An insert-only `events` table has 2,000,000 pages. How many entries does a BRIN index at the default `pages_per_range` hold? (h) `pg_sequences` shows an `integer` sequence at `last_value` 1,503,238,553. The table gets 2,000 inserts a second. What share of the range is used, and how many days are left? (i) A query keeps 30 partitions with 5 indexes each. How many relation locks does it take, counting the parent, and how many go to the shared lock table on 17 and on 18 at the defaults?

- **Given these constraints, design.** Rename `owner` to `worker_id` in `tq_tasks`. Workers claim tasks all day, and two versions of the worker code run during every deploy. No request may fail, and each step must be undoable until the last. Give the steps and the lock of each. Say which code version must run at each step, and which step cannot be undone.

- **Given these constraints, design.** An agent runner keeps its jobs in `agent_jobs`: 50,000,000 rows, an `integer` primary key, `state` text, `run_at` timestamptz and a jsonb `meta`. About 2,000 jobs are `queued` at any time. Workers claim with `SELECT ... WHERE state = 'queued' ORDER BY run_at LIMIT 10 FOR UPDATE SKIP LOCKED`, through psycopg 3 and PgBouncer in transaction mode. Support filters with `meta @> '{"tool": "browser"}'`. Give the indexes, with their write cost. Say how the claim query must be written so that its index is used after the driver prepares it. Say which signal of section 4.5 you watch, and what you do about the key.

</details>

<details><summary>Answer sketches</summary>

- Seq Scan: 9,346 pages × 1.0 + 1,000,000 × 0.0125 = 21,846, which PostgreSQL 14.24 printed. Bitmap at 45%: the index part is 1,095 pages × 4.0 = 4,380, plus 450,000 × 0.0075 = 3,375. The bitmap adds 112.5. For the heap, Mackert and Lohman gives more than T. So all 9,346 pages are read, at 4.0 − 3.0 × √1 = 1.0 each. The rows: 450,000 × 0.0125 = 5,625. Total 22,839, above 21,846. A plain Index Scan pays 9,346 × 4.0 = 37,384 for the heap alone, because the correlation is 0.0004. Two statistics change the decision. Selectivity: at 40% the bitmap costs 21,338 and wins. Correlation: near 1, the Index Scan's heap cost moves toward 4.0 + 4,205 × 1.0, about 4,209 at 45%. Its total is then about 16,464, far below 21,846. At 10% the model gives 3,664 for the Index Scan against 12,347 for the bitmap.

- (a) SHARE: blocks INSERT, UPDATE and DELETE for the whole build, and lets SELECTs through. (b) SHARE UPDATE EXCLUSIVE: blocks no reads or writes, only other DDL and VACUUM. It waits for older transactions and scans twice. (c) ACCESS EXCLUSIVE, catalog only since PostgreSQL 11: it holds the lock for milliseconds. (d) SHARE UPDATE EXCLUSIVE: one scan, and reads and writes go on. (e) ACCESS EXCLUSIVE with a rewrite of the table and its indexes, because integer to bigint is not binary coercible. The cast is the function `int8(int4)`, `castmethod => 'f'`, in `pg_cast.dat` at REL_17_11, lines 41 and 42. Everything waits for the whole rewrite. If (c) waits behind a 30-second transaction with no `lock_timeout`, later SELECTs queue behind it. They wait until that transaction ends, by the lmgr README's rule. The research measured 4.04 s for a one-row SELECT behind a 5-second wait.

- From the runs. E4: est 1 against actual 400,000 on `p4_orders`, and a nested loop with 400,000 inner loops. After ANALYZE, est near 400,000 and a hash join. The plan follows from the formula of section 4.2. All values are in the MCV list, so 1 − 1 = 0, clamped to 1 row. E10: the naive plan holds ACCESS EXCLUSIVE behind the 5-second holder, so requests pass their 1-second deadline. Then old inserts fail with 23502. E11: each lock attempt waits at most 100 ms, so no request passes 1 second. The CHECK lets SET NOT NULL skip its scan. The order is deterministic, because the holder opens before the migration starts. The load is open loop: every request has a fixed start time, so a stall is counted, not hidden.

- (a) Mostly against a cluster-wide change. The PostgreSQL 14, 17 and 18 docs keep 4.0 because most random reads are assumed to be in cache. They suggest lowering it when the data is likely to be completely in cache. Older minor releases still print the "SSD 1.1" advice. 14.19, 17.6 and 18.0 have it, and the next minor release of each dropped it. So the colleague may have read it in the docs of an older 17 release. On the research's table at 1.1, Index Scans won at 30% and 50%. At 4.0, a bitmap scan won at 30%, and a Seq Scan at 50%. That is correct only if those random reads really are cheap. Before a change, run the hot queries under `EXPLAIN (ANALYZE, BUFFERS)` at both values on one session, and compare time and buffers. If only part of the data is cached, change it per tablespace or per role. (b) Against, on its own. The cost limit of 200 "is distributed proportionally among the running autovacuum workers". Six workers get about 33 units each instead of 66. The worst-case ceiling stays at about 35.5 MB/s. Raise the limit with the workers, or better, give `orders` its own `autovacuum_vacuum_cost_limit`, which also leaves the sharing. Lower its `autovacuum_vacuum_scale_factor`, so each run has less to do. On 17, as on 14, a change of `autovacuum_max_workers` also needs a restart. 18 allows a reload up to `autovacuum_worker_slots`. First check `wait_event = VacuumDelay` in `pg_stat_activity`, which shows that the budget, not the disk, is the limit. (c) Against. In transaction mode, PgBouncer gives the client a server connection only for one transaction, so a session `SET` reaches one server connection and stays there for the next client. PgBouncer's features page lists `SET` among the things that never work in that mode. And each server connection counts its own five custom plans. The fix that holds is `ALTER ROLE reporting SET plan_cache_mode = force_custom_plan` for the report's own role, which every new server connection applies. Or stop the driver from preparing that one query, with `prepare=False` in psycopg.

- The idle transaction holds the cleanup horizon three days in the past. VACUUM runs and removes nothing that died after its snapshot. So every hourly delete leaves dead rows, and new inserts extend the file. Confirm: `age(backend_xmin)` of that session in `pg_stat_activity` is the largest, and `n_dead_tup` stops falling when VACUUM runs. Fix: end the session with `pg_terminate_backend`, set `idle_in_transaction_session_timeout`, and run VACUUM. The 3 days of growth stay in the file as free space, which new rows reuse. To return it to the system, VACUUM FULL or a rewrite takes ACCESS EXCLUSIVE for the whole copy. Plan it like a migration. The table is append-and-delete, so the free space is likely reused within days. (b) 900,000 rows died after the horizon, so VACUUM kept them. The horizon was 25,000,000 IDs behind the newest ID. At about 1,000 IDs a second that is 25,000 s, about 7 hours, so the horizon was about 7 hours old when the run ended. That age includes the run's own time. The holder can be a session, a slot or a prepared transaction. That is arithmetic from the example rate. `SELECT pid, state, xact_start, age(backend_xmin) FROM pg_stat_activity ORDER BY age(backend_xmin) DESC NULLS LAST LIMIT 5` names the session. Check `pg_replication_slots` and `pg_prepared_xacts` too, as section 4.5 says.

- (a) ANALYZE: 50 + 0.1 × 50,000,000 = 5,000,050 changed rows. VACUUM: 50 + 0.2 × 50,000,000 = 10,000,050 dead rows. (b) 1 − 0.92 − 0.02 = 0.06 is left for the 20 − 4 = 16 other values. So 0.06 / 16 = 0.00375. Rows: 8,000,000 × 0.00375 = 30,000. One check remains: the code caps the result at the least common MCV's frequency. If that MCV holds less than 0.00375, the estimate is its frequency times 8,000,000 instead. (c) WARNING at 2,107,483,647: 607,483,647 more IDs, / 3,000 = 202,495 s = 2.3 days. Stop at 2,144,483,647: 644,483,647 / 3,000 = 214,828 s = 2.5 days. (d) Each failed attempt can block the queue for up to 200 ms. That is 6 × 200 = 1,200 ms in total, spread over the backoff pauses. No single pause is longer than 200 ms. The seventh attempt then holds the lock for its own work. (e) A read costs 2 and a dirtied page 20 more, so 22 per page. That gives 200 / 22 = 9 pages per nap. The ceiling is 200 / 0.002 s / 22 = 4,545 pages per second. At 8 kB a page that is 35.5 MB/s, shared by all workers. 200 GB is 204,800 MB. So the heap alone takes at least 204,800 / 35.5 = 5,769 s, about 1.6 hours. (f) Generic: (1 − 0) / 1,000 = 0.001, below the cap of 0.1, so 10,000 rows for any tenant. Custom, for the most common tenant: its MCV frequency, 0.1 × 10,000,000 = 1,000,000 rows. The generic plan is 100 times too low for that tenant. (g) 2,000,000 / 128 = 15,625 entries. (h) 1,503,238,553 / 2,147,483,647 = 70.0% used. 2,147,483,647 − 1,503,238,553 = 644,245,094 IDs left. / 2,000 = 322,123 s = 3.7 days. That is GitHub's alert level with under four days to act, at this rate. (i) 1 + 30 × (1 + 5) = 181 relation locks. If the 5 indexes were created on the parent, the planner also locks its 5 partitioned indexes, which gives 186. On 17, 16 fit in the fast-path slots and 186 − 16 = 170 go to the shared table. On 18 at `max_locks_per_transaction` 64 there are 64 slots, so at most 64 are fast and at least 122 are shared. Fewer are fast if one group of 16 fills first.

- One design, among several. (1) Expand: `ADD COLUMN worker_id text`, ACCESS EXCLUSIVE for milliseconds, with `lock_timeout` and retries. Old code is running. (2) Deploy code that writes both `owner` and `worker_id`, and reads `owner`. The claim UPDATE sets both columns in one statement, so the two stay equal under row locks. (3) Backfill `worker_id = owner` in batches of ids, each its own transaction, with a pause. Row locks only. (4) Deploy code that reads `worker_id`, still writing both. (5) Deploy code that writes only `worker_id`. Every step so far is additive. Undo means going back one code version. The reverse of step 1 drops `worker_id`, which loses only copied data. (6) Contract, in its own later release: `DROP COLUMN owner`, ACCESS EXCLUSIVE for milliseconds. This step cannot be undone. So it waits until no running or rollback-target code reads `owner`, and until a backup exists. A `RENAME COLUMN` would break the old code at once, so it is not used.

- Indexes: a partial index `(run_at) WHERE state = 'queued'`, about 2,000 entries. A GIN index `USING gin (meta jsonb_path_ops)` for `@>`, which is smaller than the default class and serves `@>`. Write cost: every claim changes `state`, which the partial index's predicate names, so no claim is a HOT update. Every claim is a non-HOT update. So every claim adds one GIN item for each value in the new row's `meta`, because `jsonb_path_ops` makes items only for values. GIN's pending list grows until VACUUM. Build both with `CREATE INDEX CONCURRENTLY` and a `lock_timeout`. The claim query must keep `'queued'` as a literal in its text. If the driver sends `state = %s`, a generic plan cannot use the partial index. With a direct connection, psycopg lets the server consider the generic plan from execution 11. The server takes it only if its estimated cost is below the average custom plan. Behind PgBouncer, the server keeps the custom-plan count per server connection, for every client that uses it. So one client can meet the generic plan earlier or later. That is inferred from the plan cache being per backend, as Phase 5, section 5.7, says. It was not run. Signals: `pg_stat_user_tables.n_dead_tup` for `agent_jobs`, and the `removable cutoff` age in the autovacuum log, with `log_autovacuum_min_duration` lowered from its 10-minute default. The key: an `integer` primary key on a table of 50,000,000 rows that grows with every job. Watch `pg_sequences` against a 70% alert, and widen it to `bigint` by the expand/contract steps of section 4.8 before that alert fires.

</details>

## Cheatsheet

One screen to keep open while you work.

<details><summary>Open the cheatsheet</summary>

```
READ A PLAN (PG 17: EXPLAIN (ANALYZE, BUFFERS); BUFFERS is on with ANALYZE in 18)
  per node: est rows vs actual rows; total = actual rows x loops
  q-error = max(est/actual, actual/est), both floored at 1 (Leis 2015)
  the error enters at the lowest node where est and actual diverge
  cost units: 1.0 = one sequential page. Not milliseconds
  buffers of a node include its children. hit = shared_buffers, read = OS
  track_io_timing (off) adds "I/O Timings: shared read=...". TIMING FALSE
  drops the per-node clock
  SERIALIZE (17+)     converts the output: "Serialization: time= output=kB"
  MEMORY (17+)        planner memory: "Memory: used=kB allocated=kB"

FIND IT (PG 17)
  pg_stat_statements  shared_preload_libraries + restart (RDS: parameter
                      group + reboot), compute_query_id auto. Rank
                      total_exec_time; stddev/mean for flips; stats_since
  auto_explain        log_min_duration, log_analyze, log_buffers,
                      log_timing off, sample_rate. "Query Parameters" (16+)

PARALLEL AND JIT (lab: max_parallel_workers_per_gather 0, jit off)
  defaults 17         2 workers per Gather, jit on, table >= 8MB
  divisor             workers + (1 - 0.3 x workers): 2 workers = 2.4
  partial node        est x 2.4 vs actual x loops (loops = 3)
  Gather over partial agg: rows x workers (x 2) in 14-17, x 2.4 in 18
  Gather              +1000 setup, +0.1 per row passed up
  JIT                 cost > 100000 compile, > 500000 inline + optimize
  work_mem            per process and per sort or hash

ESTIMATES (docs 68.1, selfuncs.c REL_17_11)
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
  histogram ends    a B-tree index supplies the real min or max (18: any ordered index)
  after a move      logical replication, dump/restore, pg_upgrade <= 17:
                    no statistics. vacuumdb --analyze-in-stages. 18 keeps them
  never analyzed    pg_stat_user_tables: last_analyze, last_autoanalyze NULL

GENERIC PLANS (plancache.c REL_17_11)
  executions 1-5 custom. Then generic if its cost < average custom cost
  generic estimate  col = $1: (1 - null_frac) / n_distinct, capped at top MCV
  signals           $1 in EXPLAIN EXECUTE; pg_prepared_statements counters
  fix               ALTER ROLE ... SET plan_cache_mode = force_custom_plan
  psycopg 3         prepares at execution 6 (threshold 5): generic from 11
  pgJDBC            prepares at execution 5 (prepareThreshold 5): from 10
  PgBouncer         transaction mode: max_prepared_statements (200, 1.24+)
                    counts per server connection. No SET, no SQL PREPARE
  RDS Proxy         pins on SET, SQL PREPARE/EXECUTE, statements > 16 KB
  partial index     never matched by a $1 of a generic plan

COSTS (defaults, PG 17 docs 19.7.2)
  seq_page_cost 1.0  random_page_cost 4.0  cpu_tuple_cost 0.01
  cpu_index_tuple_cost 0.005  cpu_operator_cost 0.0025  effective_cache_size 4GB
  seq scan          pages x 1.0 + rows x (0.01 + 0.0025 per qual)
  bitmap page cost  4.0 - 3.0 x sqrt(pages read / table pages)
  index heap I/O    Mackert-Lohman pages x 4.0, toward 1.0 by correlation^2
  research table    1 M rows, 9,346 pages: index 1 row, bitmap to 40%, seq 45%+
                    (measured 2026-10-17, PG 14.24, narrow rows, corr 0.0004)
  unused index      pg_stat_user_indexes idx_scan = 0, last_idx_scan (16+)

INDEX TYPES (docs chapter 11)
  partial      WHERE pred: few hot rows (queue). Pred column blocks HOT
  composite    equality on leading columns bounds the scan. Order by query
  covering     INCLUDE (col): index-only scan; wider; needs visibility map
  expression   (lower(email)): cost on every insert and non-HOT update
  GIN          jsonb_path_ops for @> (smaller); pending list 4MB; fastupdate
  BRIN         1 entry per 128 pages; needs correlation; new ranges unsummarized
               until VACUUM or autosummarize; does not block HOT (16+)

JOINS
  nested loop  outer + rows(outer) x inner      hash  one pass over each side
  merge        sorted inputs. work_mem 4MB, hash_mem_multiplier 2.0 (1.0 in 14)
  from_collapse_limit 8, join_collapse_limit 8, geqo_threshold 12
  danger       low outer estimate -> nested loop, cost grows with the product
  Memoize      new in 14: Hits, Misses, Evictions. enable_memoize
  spills       Sort Method: external merge; Hash Batches > 1; HashAgg
               Disk Usage (since 13). temp_files, log_temp_files
  fence        WITH x AS MATERIALIZED (...): planned on its own

VACUUM AND WRAPAROUND (PG 17)
  removable    died before the oldest open snapshot. File never shrinks
  autovacuum   50 + 0.2 x reltuples dead rows. 3 workers, naptime 1min
               PG 18 caps it: autovacuum_vacuum_max_threshold 100 M
  throttle     200 units, then 2 ms nap, SHARED by workers. hit 1 miss 2
               dirty 20: worst 9 pages/nap, 35.5 MB/s ceiling for all
  more speed   per-table autovacuum_vacuum_cost_limit, not more workers.
               A reload reaches a running worker since 16
  log          log_autovacuum_min_duration 10min (-1 in 14). RDS 11-14:
               10000 ms. rds.force_autovacuum_logging_level warning (13+)
  horizon      "removable cutoff: N, which was X XIDs old" (14: oldest xmin)
  progress     pg_stat_progress_vacuum: dead_tuple_bytes of
               max_dead_tuple_bytes, num_dead_item_ids (17 renamed them)
  dead tids    17: TID store, no 1GB cap. 14: 6 bytes each, 11.18 M per 64MB
  waits        Timeout / VacuumDelay. pg_stat_io context 'vacuum' (16+)
  horizon held by  idle in transaction, slots (xmin), prepared xacts
  VACUUM FULL  ACCESS EXCLUSIVE, extra disk = table size
  online       REINDEX INDEX CONCURRENTLY (12+), pg_repack (2 short locks)
  wrap         oldest datfrozenxid + 2,147,483,647
  forced vacuum 200 M   failsafe 1.6 B   WARNING at wrap - 40 M   stop at - 3 M
  freezing     freeze_min_age 50 M, aggressive at freeze_table_age 150 M
  multixact    min 5 M, table 150 M, forced 400 M. mxid_age(datminmxid).
               Member space (about 4 B) has no metric (Metronome 2025)
  wraparound   "(to prevent wraparound)" autovacuum is NOT cancelled by
               DDL. A queued DDL then blocks all traffic (Joyent 2015)
  recovery     17 hint: "Execute a database-wide VACUUM". No single-user mode

PARTITIONING
  pruning      only from the partition key: plan time, executor start
               ("Subplans Removed"), execution
  costs        no key -> every partition. PK must include the key.
               autovacuum never ANALYZEs the parent. No CIC on the parent
  locks        1 per table and per index, parent included. 16 fast-path slots
               (64 on 18 at defaults). Rest: shared table, LWLock:LockManager
  fast path    SELECT count(*), pid, mode, fastpath FROM pg_locks
               WHERE fastpath IS NOT NULL GROUP BY 4,3,2
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
  slots        max_connections 100 - superuser_reserved 3 = 97. Keep the sum
               of pooler pools below it (PgBouncer default_pool_size 20)
  rewrite      TRUNCATE and rewriting ALTER are not MVCC-safe (docs 13.6)
  MySQL 8.4    ALGORITHM=INSTANT default for ADD COLUMN; 64 row versions;
               pending exclusive MDL blocks later queries;
               lock_wait_timeout 31536000 s: set it low; gh-ost for rebuilds

ADD A NOT NULL COLUMN UNDER LOAD
  1 ADD COLUMN c (no default, or a constant: no rewrite since PG 11)
  2 deploy code that writes c        3 backfill in batches, pause, no txn
  4 ADD CHECK (c IS NOT NULL) NOT VALID   5 VALIDATE CONSTRAINT (SUX)
  6 SET NOT NULL (scan skipped since PG 12)   7 DROP the CHECK
  PG 18        ADD CONSTRAINT nn NOT NULL c NOT VALID, then VALIDATE (SUX)
  measured     ADD COLUMN DEFAULT 42 2.5 ms; DEFAULT random() 997 ms rewrite;
               SET NOT NULL 0.68 ms with CHECK, 48 ms without (1 M rows, 14.24)
  errors       55P03 lock timeout  57014 statement timeout  23514 CHECK
               23502 NOT NULL  42703 undefined column

ROLLBACK
  additive steps have a reverse that loses nothing; DROP, narrow, overwrite,
  rename do not. Undo code first, schema second. Contract in its own release
  keys         integer/serial max 2,147,483,647. 2200H sequence limit,
               22003 integer out of range. Alert at 70% (GitHub): pg_sequences
  int->bigint  a rewrite under AX (cast is a function). Use a new bigint
               column, backfill, swap. New tables: bigint identity
```

</details>

## Sources

Every source the phase used, grouped as the phase groups them, and the one case only the lesson tells.

<details><summary>Open the sources</summary>

The course research fetched the first sources on 2026-10-17, and the first revision of this phase fetched more on 2026-10-18. This PostgreSQL 17 revision fetched the 17 docs, the new cases and the vendor pages on 2026-10-20, and read the source at REL_17_11 from a local clone of that tag. Every URL below was checked with `check_urls.py` on 2026-10-20. Primary sources come first in each group. The docs section numbers are those of the PostgreSQL 17 docs.

### PostgreSQL 17 documentation: plans and statistics

- **14.1 Using EXPLAIN** https://www.postgresql.org/docs/17/using-explain.html
Focus on: 14.1.1 for the cost formula, 345 pages and 445, and the three join examples with their 17 costs. 14.1.2 for `loops` and BUFFERS, and 14.1.3 for the readings that are not errors. Read it before E4. The 14 page shows older numbers for the same plans.

- **EXPLAIN, PostgreSQL 17 and 18** https://www.postgresql.org/docs/17/sql-explain.html https://www.postgresql.org/docs/18/sql-explain.html
Focus on: BUFFERS, off by default in 17 and included with ANALYZE in 18. In the 17 page, `SERIALIZE` and `MEMORY`, with the sentence that network costs "cannot be investigated this way".

- **68.1 Row Estimation Examples** https://www.postgresql.org/docs/17/row-estimation-examples.html
Focus on: every formula of section 4.2, worked on `tenk1`. The page warns that "the results will change slightly after any new ANALYZE", so check the method, not the digits. It was 72.1 in the 14 docs.

- **14.2 Statistics Used by the Planner** https://www.postgresql.org/docs/17/planner-stats.html
Focus on: `reltuples` and `relpages`, the 100-entry limit, and 14.2.2 on extended statistics and its limits.

- **68.2 Multivariate Statistics Examples** https://www.postgresql.org/docs/17/multivariate-statistics-examples.html
Focus on: the `a = b = i % 100` table, before and after CREATE STATISTICS.

- **pg_stats** https://www.postgresql.org/docs/17/view-pg-stats.html
Focus on: `null_frac`, `n_distinct`, the MCV columns, `histogram_bounds` and `correlation`. Read `correlation` before you choose BRIN.

- **19.7 Query Planning** https://www.postgresql.org/docs/17/runtime-config-query.html
Focus on: the cost constants and the text on `random_page_cost`, then `geqo_threshold`, `from_collapse_limit`, `join_collapse_limit` and `plan_cache_mode`.

- **20.7 Query Planning, PostgreSQL 10** https://www.postgresql.org/docs/10/runtime-config-query.html
Focus on: the old `random_page_cost` text with "90%" and the SSD value 1.1. It is the source of a claim many posts still repeat. Read it only to see what changed.

- **19.4 Resource Consumption** https://www.postgresql.org/docs/17/runtime-config-resource.html
Focus on: `work_mem`, `hash_mem_multiplier` at 2.0, `maintenance_work_mem` and `autovacuum_work_mem`, and 19.4.4 on the vacuum cost delay.

- **ANALYZE** https://www.postgresql.org/docs/17/sql-analyze.html
Focus on: the note that the largest statistics target decides the sample size.

- **pg_upgrade** https://www.postgresql.org/docs/17/pgupgrade.html
Focus on: the "Statistics" step: statistics are not transferred, and `vacuumdb --all --analyze-only` or `--analyze-in-stages` rebuild them. Read it before any upgrade or move.

- **PREPARE** https://www.postgresql.org/docs/17/sql-prepare.html
Focus on: the Notes, with the five custom plans, the cost comparison, and the `$n` symbols of a generic plan. Read it before E13.

- **pg_prepared_statements** https://www.postgresql.org/docs/17/view-pg-prepared-statements.html
Focus on: `generic_plans`, `custom_plans` and `from_sql`. Read it before E18.

- **15.1 How Parallel Query Works** https://www.postgresql.org/docs/17/how-parallel-query-works.html
Focus on: the Gather node and its workers, and "Workers Planned" in a plan. Then section 19.4 for `max_parallel_workers_per_gather` and `work_mem` per worker.

- **30.2 When to JIT?** https://www.postgresql.org/docs/17/jit-decision.html
Focus on: the three cost thresholds, the JIT block with its 17 `Deform` field, and the rule for generic plans. It was 32.2 in the 14 docs.

- **7.8 WITH Queries** https://www.postgresql.org/docs/17/queries-with.html
Focus on: 7.8.3, when a CTE is folded into the parent query and what `MATERIALIZED` changes.

- **F.30 pg_stat_statements** https://www.postgresql.org/docs/17/pgstatstatements.html
Focus on: the setup with `shared_preload_libraries` and `compute_query_id`, the columns with `shared_blk_read_time` and `stats_since`, and the example ranking. Read it before E14.

- **F.3 auto_explain** https://www.postgresql.org/docs/17/auto-explain.html
Focus on: `log_min_duration`, `log_analyze` and its warning, `log_timing`, `sample_rate`, `log_parameter_max_length` and `log_level`. It was F.4 in the 14 docs.

- **19.9 Run-time Statistics** https://www.postgresql.org/docs/17/runtime-config-statistics.html
Focus on: `track_io_timing` and `compute_query_id`.

### PostgreSQL 17 documentation: index types

- **11.2 Index Types** https://www.postgresql.org/docs/17/indexes-types.html
Focus on: GIN as an inverted index, and BRIN for values "well-correlated with the physical order". Read it before section 4.3b.

- **11.3 Multicolumn Indexes** https://www.postgresql.org/docs/17/indexes-multicolumn.html
Focus on: the exact rule for leading columns, and the example on `(a, b, c)`. Then the 18 page, https://www.postgresql.org/docs/18/indexes-multicolumn.html , for skip scan.

- **11.7 Indexes on Expressions** https://www.postgresql.org/docs/17/indexes-expressional.html
Focus on: the last paragraph, on the cost of each insert and non-HOT update.

- **11.8 Partial Indexes** https://www.postgresql.org/docs/17/indexes-partial.html
Focus on: the unbilled-orders example, the sentence on parameterized clauses, and the warning against partial indexes as partitions.

- **11.9 Index-Only Scans and Covering Indexes** https://www.postgresql.org/docs/17/indexes-index-only-scans.html
Focus on: `INCLUDE`, and the paragraph on when payload columns are worth their size.

- **8.14 JSON Types** https://www.postgresql.org/docs/17/datatype-json.html
Focus on: 8.14.4, "jsonb Indexing", for `jsonb_ops` against `jsonb_path_ops`.

- **64.4 GIN Indexes** https://www.postgresql.org/docs/17/gin.html
Focus on: the fast update technique and its pending list, and the tip on `fastupdate`.

- **64.5 BRIN Indexes** https://www.postgresql.org/docs/17/brin.html
Focus on: 64.5.1, the size rule for `pages_per_range` and the summarization of new ranges.

- **8.1 Numeric Types** https://www.postgresql.org/docs/17/datatype-numeric.html
Focus on: the ranges of `integer`, `bigint`, `serial` and `bigserial`. Read it before section 4.8's key part.

- **pg_sequences** https://www.postgresql.org/docs/17/view-pg-sequences.html
Focus on: `last_value` and `max_value`, for the headroom query.

### PostgreSQL 17 documentation: maintenance, locks and DDL

- **24.1 Routine Vacuuming** https://www.postgresql.org/docs/17/routine-vacuuming.html
Focus on: 24.1.2 on space, and 24.1.3 on statistics and partitioned tables. Then 24.1.5 on wraparound, with its recovery steps, and 24.1.6 on the autovacuum thresholds. It is the most important page for section 4.5.

- **19.10 Automatic Vacuuming** https://www.postgresql.org/docs/17/runtime-config-autovacuum.html
Focus on: the threshold, scale factor, worker and freeze settings, with their defaults. Then `autovacuum_vacuum_cost_limit`, and the sentence on sharing it among workers.

- **19.11 Client Connection Defaults** https://www.postgresql.org/docs/17/runtime-config-client.html
Focus on: `lock_timeout`, `statement_timeout`, `idle_in_transaction_session_timeout` and `transaction_timeout`, new in 17, with its warning about `postgresql.conf`. Then the freeze ages, their multixact forms, `vacuum_failsafe_age`, and `session_preload_libraries`.

- **19.8 Error Reporting and Logging** https://www.postgresql.org/docs/17/runtime-config-logging.html
Focus on: `log_autovacuum_min_duration`, 10min by default, `log_lock_waits` and `log_temp_files`.

- **19.12 Lock Management** https://www.postgresql.org/docs/17/runtime-config-locks.html
Focus on: `deadlock_timeout`, the delay before a waiter checks for deadlock and cancels a normal autovacuum.

- **19.10 Vacuuming, PostgreSQL 18** https://www.postgresql.org/docs/18/runtime-config-vacuum.html
Focus on: `autovacuum_vacuum_max_threshold`, new in 18, and `autovacuum_worker_slots`.

- **27.2 The Cumulative Statistics System, and 27.4 Progress Reporting** https://www.postgresql.org/docs/17/monitoring-stats.html https://www.postgresql.org/docs/17/progress-reporting.html
Focus on: `pg_stat_user_tables`, `pg_stat_user_indexes`, `pg_stat_io`, `pg_stat_database`'s temp columns and the `VacuumDelay` wait event. Then `pg_stat_progress_vacuum` with its 17 columns, and `pg_stat_progress_create_index`.

- **pg_replication_slots, and 19.6 Replication** https://www.postgresql.org/docs/17/view-pg-replication-slots.html https://www.postgresql.org/docs/17/runtime-config-replication.html
Focus on: `xmin` against `catalog_xmin`, then `hot_standby_feedback` and `max_slot_wal_keep_size`.

- **F.31 pgstattuple** https://www.postgresql.org/docs/17/pgstattuple.html
Focus on: `pgstattuple_approx`, and how it uses the visibility map to skip pages.

- **13.3 Explicit Locking, and 13.6 Caveats** https://www.postgresql.org/docs/17/explicit-locking.html https://www.postgresql.org/docs/17/mvcc-caveats.html
Focus on: 13.3.1, each mode with the commands that take it and its conflicts. `locks.py` rebuilds its table from this page. Then 13.6, on why a rewrite is not MVCC-safe.

- **ALTER TABLE, PostgreSQL 17 and 18** https://www.postgresql.org/docs/17/sql-altertable.html https://www.postgresql.org/docs/18/sql-altertable.html
Focus on: the lock of each subcommand, `ADD COLUMN` with a default, and `SET NOT NULL` with a CHECK. Then `NOT VALID`, `VALIDATE CONSTRAINT`, and the notes on rewrites and DROP COLUMN. In the 18 page, not-null constraints that allow `NOT VALID`.

- **CREATE INDEX** https://www.postgresql.org/docs/17/sql-createindex.html
Focus on: "Building Indexes Concurrently": the two scans, the wait, the invalid index, and the limit on partitioned tables. Then the storage parameters `fastupdate`, `pages_per_range` and `autosummarize`.

- **REINDEX** https://www.postgresql.org/docs/17/sql-reindex.html
Focus on: the paragraph that compares REINDEX with dropping and creating the index. It gives the table lock and the index lock, which section 13.3.1 summarizes as ACCESS EXCLUSIVE.

- **5.12 Table Partitioning** https://www.postgresql.org/docs/17/ddl-partitioning.html
Focus on: 5.12.1 for the benefits, 5.12.2.2 for ATTACH and DETACH, and 5.12.2.3 for the limitations. Then 5.12.4 for pruning, with the warning on locks at executor start, and 5.12.6 for the number of partitions.

- **Release notes 9.5.0, 11.0, 12.0 and 14.0** https://www.postgresql.org/docs/release/9.5.0/ https://www.postgresql.org/docs/release/11.0/ https://www.postgresql.org/docs/release/12.0/ https://www.postgresql.org/docs/release/14.0/
Focus on: the lower foreign-key lock in 9.5, and the constant default without a rewrite in 11. Then `SET NOT NULL` without a scan and `REINDEX CONCURRENTLY` in 12. In 14: the wider wraparound margins, `vacuum_failsafe_age`, Memoize, the lower `vacuum_cost_page_miss`, B-tree bottom-up deletion and the `pg_prepared_statements` counters.

- **Release notes 13.0, 15.0, 16.0, 17.0 and 18.0** https://www.postgresql.org/docs/release/13.0/ https://www.postgresql.org/docs/release/15.0/ https://www.postgresql.org/docs/release/16.0/ https://www.postgresql.org/docs/release/17.0/ https://www.postgresql.org/docs/release/18.0/
Focus on: HashAggregate spilling and B-tree deduplication in 13. `hash_mem_multiplier` 2.0 and `log_autovacuum_min_duration` 10min in 15. `EXPLAIN (GENERIC_PLAN)`, `pg_stat_io`, `last_idx_scan` and delay settings honoured per block in 16. In 17: the TID store, the renamed `pg_stat_progress_vacuum` columns, `EXPLAIN (SERIALIZE)` and `(MEMORY)`, and `transaction_timeout`. In 18: `autovacuum_vacuum_max_threshold`, NOT NULL `NOT VALID`, statistics kept by `pg_upgrade`, and more fast-path lock slots.

### PostgreSQL source, REL_17_11

- **costsize.c** https://github.com/postgres/postgres/blob/REL_17_11/src/backend/optimizer/path/costsize.c
Focus on: `clamp_row_est` at lines 202 to 218, and `cost_seqscan` from 284. Then the index heap cost at 720 to 787, and Mackert and Lohman at 898 to 958. The bitmap cost per page is at 1064 to 1066, and `get_parallel_divisor` at 6380. `cost_model.py` cites each line.

- **selfuncs.c** https://github.com/postgres/postgres/blob/REL_17_11/src/backend/utils/adt/selfuncs.c
Focus on: `var_eq_const` from line 296. Its branch for a value outside the MCV list is at lines 409 to 436. Then `var_eq_non_const` at 512 to 526, the histogram ends at 1086 to 1092, and `genericcostestimate` from 6627.

- **explain.c** https://github.com/postgres/postgres/blob/REL_17_11/src/backend/commands/explain.c
Focus on: line 1847, where rows are divided by loops, the JIT group at 1011 to 1101, `ExplainPrintSerialize` at 1109, the `I/O Timings` line at 3818 to 3858, and `show_memory_counters` at 3950.

- **analyze.c** https://github.com/postgres/postgres/blob/REL_17_11/src/backend/commands/analyze.c
Focus on: line 1894, `stats->minrows = 300 * stats->attstattarget;`.

- **selfuncs.h and cost.h** https://github.com/postgres/postgres/blob/REL_17_11/src/include/utils/selfuncs.h https://github.com/postgres/postgres/blob/REL_17_11/src/include/optimizer/cost.h
Focus on: the default selectivities at lines 34 and 37, and the cost defaults at lines 24 to 34.

- **varsup.c** https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/transam/varsup.c
Focus on: the error and its new hint at lines 156 and 158. Then the limits at lines 389, 405 and 419. Compare REL_14_24 for the old message and hint, by changing the tag.

- **vacuumlazy.c and vacuum.c** https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/heap/vacuumlazy.c https://github.com/postgres/postgres/blob/REL_17_11/src/backend/commands/vacuum.c
Focus on: the log entry at lines 626 to 760, with `removable cutoff` at 672, and the TID store at 187 and 2877 to 2881. Then `vacuum_delay_point` in `vacuum.c` from line 2390, with the config reload at 2401 to 2412.

- **system_views.sql** https://github.com/postgres/postgres/blob/REL_17_11/src/backend/catalog/system_views.sql
Focus on: `pg_stat_progress_vacuum` at lines 1209 to 1226, `pg_stat_io` at 1153, and `pg_sequences` at 167.

- **autovacuum.c and proc.c** https://github.com/postgres/postgres/blob/REL_17_11/src/backend/postmaster/autovacuum.c https://github.com/postgres/postgres/blob/REL_17_11/src/backend/storage/lmgr/proc.c
Focus on: the thresholds at lines 3068 to 3095, the cost balancing at 2856 to 2862, and the activity text at 3168 to 3183. In `proc.c`, the autovacuum cancel at 1416 to 1472, and the lock-wait log line at 1603.

- **plancache.c, prepare.c and setrefs.c** https://github.com/postgres/postgres/blob/REL_17_11/src/backend/utils/cache/plancache.c https://github.com/postgres/postgres/blob/REL_17_11/src/backend/commands/prepare.c https://github.com/postgres/postgres/blob/REL_17_11/src/backend/optimizer/plan/setrefs.c
Focus on: `choose_custom_plan` at lines 1054 to 1100 and the planning charge at 1148 to 1150. Then `prepare.c` line 631, where EXPLAIN EXECUTE uses the same cache, and `setrefs.c` line 411, which keeps every range-table entry.

- **allpaths.c** https://github.com/postgres/postgres/blob/REL_17_11/src/backend/optimizer/path/allpaths.c
Focus on: `compute_parallel_worker` from line 4203, and the Gather rows above a partial aggregate at 3074 and 3075.

- **index.c, trigger.c, postgres.c and errcodes.txt** https://github.com/postgres/postgres/blob/REL_17_11/src/backend/catalog/index.c https://github.com/postgres/postgres/blob/REL_17_11/src/backend/commands/trigger.c https://github.com/postgres/postgres/blob/REL_17_11/src/backend/tcop/postgres.c https://github.com/postgres/postgres/blob/REL_17_11/src/backend/utils/errcodes.txt
Focus on: REINDEX's SHARE on the table at `index.c` line 3614 and ACCESS EXCLUSIVE on the index at 3654. DROP TRIGGER's ACCESS EXCLUSIVE at `trigger.c` line 1323. The timeout errors and `canceling autovacuum task` at `postgres.c` lines 3396 to 3416. SQLSTATEs 55P03, 57014, 23514, 23502, 22003 and 2200H in `errcodes.txt`.

- **lmgr README and README.HOT** https://github.com/postgres/postgres/blob/REL_17_11/src/backend/storage/lmgr/README https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/heap/README.HOT
Focus on: lines 364 and 387 of the lmgr README, the two rules of the lock queue. Then README.HOT lines 36 to 42, on which columns count as indexed and why BRIN does not block HOT.

- **brin.c, lock.c and proc.h** https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/brin/brin.c https://github.com/postgres/postgres/blob/REL_17_11/src/backend/storage/lmgr/lock.c https://github.com/postgres/postgres/blob/REL_17_11/src/include/storage/proc.h
Focus on: the comment on unsummarized ranges at `brin.c` lines 553 to 555. Then the fast-path test at `lock.c` lines 929 and 930, and the 16 slots at `proc.h` line 86.

- **postinit.c, REL_18_6** https://github.com/postgres/postgres/blob/REL_18_6/src/backend/utils/init/postinit.c
Focus on: lines 586 to 596, where 18 sizes the fast-path lock groups from `max_locks_per_transaction`.

### The paper

- **How Good Are Query Optimizers, Really?, Leis, Gubichev, Mirchev, Boncz, Kemper and Neumann, PVLDB 9(3), 2015** https://www.vldb.org/pvldb/vol9/p204-leis.pdf
Focus on: section 2 for the setup, Table 1 for single-table q-errors, and Figure 3 with section 3.2 for joins. Then section 4.1 and Figure 6 for the nested-loop timeouts, and section 5 for the cost model. Its section 5 finds a median cost-model error of 38%, and 30% after tuning. All on PostgreSQL 9.4, with the data in memory. About 60 minutes. Read it after E4.

### Books and course notes

- **PostgreSQL 14 Internals, Egor Rogov, Postgres Professional, 2023** https://edu.postgrespro.com/postgresql_internals-14_en.pdf
Focus on: 6.6 and 6.7 for the throttle and the vacuum log. Then 7.2 and 7.3 for freezing, and 16.3 for generic plans. Then 20.2 and 20.3 for heap fetches and lossy bitmaps, 21.2 for Memoize, and 22 and 23 for spills. It is free, and every example ran on PostgreSQL 14.

- **CMU 15-445/645, Fall 2025, lecture notes 11, 12 and 15** https://15445.courses.cs.cmu.edu/fall2025/notes/11-sorting.pdf https://15445.courses.cs.cmu.edu/fall2025/notes/12-joins.pdf https://15445.courses.cs.cmu.edu/fall2025/notes/15-optimization1.pdf
Focus on: external merge sort and hash aggregation in 11, and the partitioned hash join in 12. Then section 11 of 15, the System R join search.

### Production reports and migration guides

- **Manta postmortem of 2015-07-27, Joyent, archived copy** https://web.archive.org/web/20220528044329/https://www.joyent.com/blog/manta-postmortem-7-27-2015
Focus on: the timeline, the three-way lock interaction, and the cost-based delay during the outage. It does not name its PostgreSQL version.

- **BUG #19076: Generic query plan is extremely slow, pgsql-bugs, 2025-10-07** https://www.postgresql.org/message-id/19076-4d897c04a44a9627%40postgresql.org
Focus on: the two plans, and Laurenz Albe's reply on `plan_cache_mode`. PostgreSQL 17.6.

- **BUG #17540: Prepared statement: PG switches to a generic query plan which is consistently much slower, pgsql-bugs, 2022** https://www.postgresql.org/message-id/17540-7aa1855ad5ec18b4@postgresql.org
Focus on: the reporter's note on pgx and `PQexecPrepared`, and the database-wide workaround. PostgreSQL 14.4.

- **Django: Maybe disable PostgreSQL's JIT to speed up many-joined queries, Adam Johnson, 2023-11-09** https://adamj.eu/tech/2023/11/09/django-disable-postgresql-jit/
Focus on: the cost estimate that triggered JIT, and the `-c jit=off` fix. PostgreSQL 14. A personal blog, not peer reviewed.

- **pg_repack documentation** https://reorg.github.io/pg_repack/
Focus on: the requirements, the disk space, and the two short exclusive locks.

- **Zero-downtime Postgres migrations, the hard parts, Chris Sinjakli, GoCardless** https://gocardless.com/blog/zero-downtime-postgres-migrations-the-hard-parts/
Focus on: the 15-second outage and its three-transaction reproduction. Its foreign-key lock claim is for 9.4, as section 4.7 explains. The earliest archive copy is from 2015-10-09, and the page says it was edited in June 2024.

- **Zero-downtime Postgres migrations, a little help, GoCardless** https://gocardless.com/blog/zero-downtime-postgres-migrations-a-little-help/
Focus on: the defaults of `ActiveRecord::SaferMigrations`, 750 ms and 1,500 ms.

- **Zero-downtime Postgres schema migrations need this: lock_timeout and retries, Nikolay Samokhvalov, postgres.ai, 2021-09-23** https://postgres.ai/blog/20210923-zero-downtime-postgres-schema-migrations-lock-timeout-and-retries
Focus on: the three-session reproduction, the 50 ms timeout, and the thought experiment on retries without backoff.

- **Schema changes and the Postgres lock queue, Andrew Farries, Xata, 2024-06-18** https://xata.io/blog/migrations-and-exclusive-locks
Focus on: the lock_timeout section. The page says it was updated on 2025-05-02.

- **Migration style guide, GitLab** https://docs.gitlab.com/development/migration_style_guide/
Focus on: the duration limits, the roll-forward rule, and the lock retry section. Read it beside the code below, because the two disagree.

- **with_lock_retries.rb, GitLab, master** https://gitlab.com/gitlab-org/gitlab/-/blob/master/lib/gitlab/database/with_lock_retries.rb
Focus on: `DEFAULT_TIMING_CONFIGURATION`, 41 pairs of a timeout and a pause, repeated 15 times. That is 615 attempts, whose timeouts and pauses add up to 2,673.75 s. The file's own comment says about 40 minutes.

- **Batched background migrations, GitLab** https://docs.gitlab.com/development/database/batched_background_migrations/
Focus on: batch sizes, throttling on database health, and the estimate formula.

- **strong_migrations, Andrew Kane** https://github.com/ankane/strong_migrations
Focus on: the list of unsafe operations, "Setting NOT NULL on an existing column", "Backfilling data", and the timeout settings.

- **Online migrations at scale, Jacqueline Xu, Stripe, 2017** https://stripe.com/blog/online-migrations
Focus on: the four phases of dual writing. The post does not name its database.

- **Safe operations for high volume PostgreSQL, 2019 draft, James Coleman** https://gist.github.com/jcoleman/1e6ad1bf8de454c166da94b67537758b
Focus on: the goals at the top, the ~2-second lock limit and the rollback rule, and the DROP COLUMN process. A draft gist. The published version returned HTTP 403 to the research.

- **Transaction ID Wraparound in Postgres, David Cramer, Sentry, 2015-07-23** https://blog.sentry.io/transaction-id-wraparound-in-postgres/
Focus on: the timeline and the recovery by TRUNCATE. Its one-million margin is PostgreSQL 13 era, and its single-user advice is out of date.

- **What we learned from the recent Mandrill outage, Mailchimp, 2019** https://mailchimp.com/what-we-learned-from-the-recent-mandrill-outage/
Focus on: the warning in November 2018 and the vacuum estimates. By Eric Muntz, dated 2019-03-26.

### Production cases added for PostgreSQL 17, managed services, drivers and poolers

- **Incident Report: October 28, 2025, Ray Chen, Railway** https://blog.railway.com/p/incident-report-oct-28th-2025
Focus on: the timeline, the `pg_use_reserved_connections` error, and the three changes: CONCURRENTLY in CI, pool limits, per-user limits. Section 4.7. A first-party report.

- **Postmortem for Aurora Postgres Migration November 23 2022, Guillermo Pérez, RevenueCat** https://www.revenuecat.com/blog/engineering/postmortem-aurora-postgres-migration
Focus on: the root cause, ANALYZE not run on the largest tables, and the sequences that were not copied. Section 4.2.

- **Delayed Start Compute Operations: Triggering Event, Mihai Bojin and Matt Sherman, Neon, 2025-05-30** https://neon.com/blog/delayed-start-compute-operations-triggering-event
Focus on: the plan change on `computes`, the `ANALYZE` fix and the materialized CTE. A vendor's report on its own system. Sections 4.2 and 4.4.

- **How we stopped xmin horizon blocking Postgres vacuuming: a deepdive, Matt Aitken, Trigger.dev, 2024-08-16** https://trigger.dev/blog/stopping-xmin-horizon-blocking-postgres-vacuuming
Focus on: the dead-tuple query, the `VACUUM VERBOSE` output in the 14 format, and the failed fixes. Section 4.5.

- **Root Cause Analysis: PostgreSQL MultiXact member exhaustion incidents (May 2025), Cosmo Wolfe, Metronome, 2025-05-20** https://metronome.com/blog/root-cause-analysis-postgresql-multixact-member-exhaustion-incidents-may-2025
Focus on: the member space limit and why the ID age looked safe. Aurora PostgreSQL 13.18. Section 4.5.

- **Postgres Partition Pains - LockManager Waits, Kyle Hailey, 2023-06-13** https://www.kylehailey.com/post/postgres-partition-pains-lockmanager-waits
Focus on: the 880 locks per query at 40 partitions, and the move to weekly partitions. A personal blog that names no company. Section 4.6.

- **Postgres Indexes, Partitioning and LWLock:LockManager Scalability, Jeremy Schneider, 2024-03-03** https://ardentperf.com/2024/03/03/postgres-indexes-partitioning-and-lwlocklockmanager-scalability/
Focus on: the Midjourney section, which names the company, the 8 TB table and the 12-hour concurrent index build. A personal blog. Sections 4.3b and 4.6.

- **Introducing the GitHub Availability Report, Keith Ballinger, GitHub, 2020-07-08** https://github.blog/news-insights/company-news/introducing-the-github-availability-report/
Focus on: the incident of May 5, the int limit, the 70% alert and the foreign key linter. Section 4.8.

- **Postmortem on the read-only outage of Basecamp on November 9th, 2018, DHH** https://signalvnoise.com/svn3/postmortem-on-the-read-only-outage-of-basecamp-on-november-9th-2018/
Focus on: the events table at 2,147,483,647 and the Rails 5.1 default. Section 4.8.

- **Linear incident on Jan 24th, 2024, and Resend's incident report for February 21, 2024** https://linear.app/now/linear-incident-on-jan-24th-2024 https://www.resend.com/blog/incident-report-for-february-21-2024
Focus on: a `TRUNCATE CASCADE` in a migration, and a migration run against the wrong environment. Both are first-party posts, fetched again on 2026-10-20. Linear's post is dated 2024-01-30 and Resend's 2024-02-22. Section 4.8.

- **Scaling PostgreSQL to power 800 million ChatGPT users, Bohan Zhang, OpenAI, 2026-01-22, archived copy** https://web.archive.org/web/20261010101204id_/https://openai.com/index/scaling-postgresql/
Focus on: the schema rules and the 5-second timeout on schema changes. The archived copy is served gzip-compressed. After decompression it shows the schema rules. Fetched again on 2026-10-20.

- **Working with PostgreSQL, Satya Sarangi, Zerodha, 2021-04-22** https://zerodha.tech/blog/working-with-postgresql/
Focus on: `work_mem` against `max_connections`, and vacuum after the nightly load. Fetched again on 2026-10-20. Section 4.4.

- **The Reddit Media Metadata Store, r/RedditEng, archived copy** https://web.archive.org/web/20250731133400id_/https://www.reddit.com/r/RedditEng/comments/1avlywv/the_reddit_media_metadata_store/
Focus on: range partitions made in advance with pg_partman. Fetched again on 2026-10-20. Section 4.6.

- **Postmortem: Clerk System Outage (February 19, 2026), Braden Sidoti, Clerk, 2026** https://clerk.com/blog/2026-02-19-system-outage-postmortem
Focus on: the root cause section, the 99.9996% NULL column and the manual ANALYZE at 17:27 UTC. The post names no table. Only the lesson tells this case, in the estimates section, and it was fetched on 2026-10-18.

### Managed PostgreSQL: Amazon RDS and Aurora

- **Logging autovacuum and vacuum activities, Amazon RDS User Guide** https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Autovacuum.Logging.html
Focus on: `rds.force_autovacuum_logging_level`, the 10000 ms default on 11 to 14, and the 1000 to 5000 recommendation. Vendor documentation. Section 4.5.

- **LWLock:lock_manager, Amazon RDS User Guide** https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/wait-event.lw-lock-manager.html
Focus on: the fast-path criteria, the `pg_locks` query, and the names of the wait before and after 13. Vendor documentation. Section 4.6.

- **Avoiding pinning an RDS Proxy, Amazon RDS User Guide** https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-pinning.html
Focus on: the PostgreSQL list of pinning conditions, the 16 KB rule and the pinning metric. Vendor documentation. Section 4.2.

- **Parameter groups, Amazon RDS User Guide** https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/parameter-groups-overview.html
Focus on: default groups that cannot be changed, and `pending-reboot` for static parameters. The page does not name `shared_preload_libraries`. That setting needs a restart in PostgreSQL, so it is static. Vendor documentation. Section 4.1.
- **SQL statistics for RDS for PostgreSQL, Amazon RDS User Guide** https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PerfInsights.UsingDashboard.AnalyzeDBLoad.AdditionalMetrics.PostgreSQL.html
Focus on: `pg_stat_statements` loaded by default on PostgreSQL 11 and later. Vendor documentation. Section 4.1.

- **Database load, CloudWatch Database Insights, Amazon RDS User Guide** https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PerfInsights.Overview.ActiveSessions.html
Focus on: average active sessions, sampled each second, split by wait event. Vendor documentation. Section 4.1.

- **Overview of Aurora PostgreSQL query plan management** https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Optimize.overview.html
Focus on: the list of causes of plan regression, with "query parameter bindings". Vendor documentation. Section 4.2.

### Drivers, poolers and frameworks

- **Prepared statements, psycopg 3** https://www.psycopg.org/psycopg3/docs/advanced/prepare.html
Focus on: `prepare_threshold`, when psycopg prepares a query by itself, and the PgBouncer caveats of 3.2. The rule is in psycopg's `_preparing.py`, lines 37 and 73, in version 3.3.6 of `pyproject.toml`.

- **Initializing the Driver, pgJDBC** https://jdbc.postgresql.org/documentation/use/
Focus on: `prepareThreshold`, "Default 5", and `preparedStatementCacheQueries`. Section 4.2.

- **PgBouncer configuration and changelog** https://www.pgbouncer.org/config.html https://www.pgbouncer.org/changelog.html
Focus on: `max_prepared_statements`, default 200, and how it names statements on server connections. Then `default_pool_size`, 20. In the changelog, 1.21.0 of 2023-10-16 and 1.24.0 of 2025-01-10. Sections 4.2 and 4.7.

- **PgBouncer features** https://www.pgbouncer.org/features.html
Focus on: the table of session features that transaction pooling breaks.

- **Django 5.2 settings and model field reference** https://docs.djangoproject.com/en/5.2/ref/settings/ https://docs.djangoproject.com/en/5.2/ref/models/fields/
Focus on: `DEFAULT_AUTO_FIELD`, `AutoField` and `BigAutoField`. Section 4.8.

- **pgvector README** https://github.com/pgvector/pgvector
Focus on: filtering with HNSW, vacuuming HNSW indexes, and partitions per tenant. Read with retrieval-internals, Phase 3 and Phase 7.

### MySQL

- **Online DDL Operations, MySQL 8.4 Reference Manual** https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html
Focus on: `ALGORITHM=INSTANT` for columns, the row version limit and `ERROR 4092`. Section 4.7.

- **Online DDL Performance and Concurrency, MySQL 8.4 Reference Manual** https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-performance.html
Focus on: the three phases of metadata locking, and the three-session example with `Waiting for table metadata lock`. Section 4.7.

- **Server System Variables, MySQL 8.4 Reference Manual** https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html
Focus on: `lock_wait_timeout`, default 31536000 seconds.

- **Metadata Locking, MySQL 8.4 Reference Manual** https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html
Focus on: why a transaction's metadata locks last until it ends, and the priority of write lock requests.

- **gh-ost README, GitHub** https://github.com/github/gh-ost
Focus on: "How?", the triggerless design from the binary log, throttling and the postponed cut-over.

### A talk

- **Explaining the Postgres Query Optimizer, Bruce Momjian, Citus Con 2022** https://www.youtube.com/watch?v=wLpcVM9qxV0
Focus on: scan methods from 0:04:19, and join methods from 0:12:13 to 0:21:18. The times come from the video's chapter list, because the captions did not load.

- **Explaining the Postgres Query Optimizer, slides, Bruce Momjian** https://momjian.us/main/writings/pgsql/optimizer.pdf
Focus on: slides 13 to 29 for the plan per letter, and slides 30 to 37 for the three joins. The slide table has only 410 rows, so use the course research's 1,000,000-row table for switch points.

</details>

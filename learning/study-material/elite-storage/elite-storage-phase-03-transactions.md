# Phase 3 — Transactions and concurrency control

**The question this phase answers:** two transactions both read, both write, and both commit without error. The result is one that neither of them would have produced alone. Which isolation level allowed that, and which would have stopped it?

**The promise this phase pays.** Phase 2, section 2.2, said that an update writes a new version of the row. It left the reasons for this phase, and section 3.2 gives them.

## Why you're here

Here is the situation this phase follows. It is an example, and every step of it happens in this phase's lab.

A task queue on PostgreSQL 14 needs a human approver on call at all times. Alice and Bob are both on call. Each of them opens the same screen at the same moment. The screen runs one transaction that counts the approvers on call. If the count is at least 2, the transaction sets its user off call. Both transactions count 2, so both set their user off call and commit. Now nobody is on call.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The running case. Two sessions at READ COMMITTED, the default            │
├──────────────────────────────────────────────────────────────────────────┤
│ time   Alice's transaction            Bob's transaction                  │
│ t1     BEGIN                          BEGIN                              │
│ t2     count on call -> 2                                                │
│ t3                                    count on call -> 2                 │
│ t4     UPDATE alice off call                                             │
│ t5                                    UPDATE bob off call                │
│ t6     COMMIT: ok                                                        │
│ t7                                    COMMIT: ok                         │
├──────────────────────────────────────────────────────────────────────────┤
│ after t7: 0 approvers on call. The rule needs at least 1                 │
└──────────────────────────────────────────────────────────────────────────┘
```

No error was raised, and no lock wait happened. The database ran at its default isolation level, READ COMMITTED, which permits exactly this. The next level up, REPEATABLE READ, permits it too.

This example comes from Cahill, Röhm and Fekete, SIGMOD 2008, Example 1, where the rows are doctors on duty. Ports and Grittner, VLDB 2012, retell it with Alice and Bob, who count first and then update. This phase uses that order, with approvers in place of doctors, so that one task-queue system carries every example.

The same kind of gap appears in managed databases. Jepsen's analysis "Amazon RDS for PostgreSQL 17.4" was published on 2025-04-29. It found Long Fork cycles in Multi-AZ clusters read through a primary and a reader endpoint, with no faults injected. In a Long Fork, two readers see two independent writes in opposite orders. So the clusters did not give snapshot isolation across their endpoints. AWS answered on 2025-05-02. Its post says a replica makes commits visible in the order of the write-ahead log, and the primary uses its own order. So the effect needs a replica, and replicas are the subject of course 5, Phase 3. The references give both positions with their setups. This course did not check what AWS's own documentation promised before these posts.

So an isolation level is a list of anomalies that the database is allowed to produce. This phase names each anomaly, reproduces it in PostgreSQL, and shows which level and which change of code prevents it.

## What you can do after this phase

1. Say what atomicity promises and what isolation promises, and give a failure of each.
2. Read a row version's `xmin` and `xmax` and a snapshot, and say which version a statement sees.
3. Reproduce a lost update, write skew and a phantom with two sessions in a fixed order.
4. Read a deadlock report, and say which transaction PostgreSQL cancels and why.
5. Explain what serializable snapshot isolation adds to snapshot isolation, what it costs, and how to retry its failures.
6. Choose between a lock taken before the read and a check made at the write, from the contention.
7. Audit a task claim, an approval and an outbox write at READ COMMITTED. Fix each one, with a test that fails at the old level.
8. Say when a unique index, a lease or an advisory lock is the right fix, and what each one does not cover.
9. Recognise lock trouble and subtransaction trouble in `pg_stat_activity`, `pg_locks` and the server log.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: Transactions and concurrency control                            │
├──────────────────────────────────────────────────────────────────────────┤
│ 3.1 Atomicity and isolation   all or nothing, against as if alone        │
│ 3.2 MVCC                      row versions, snapshots, what they miss    │
│ 3.3 The anomalies             lost update, write skew, phantoms          │
│ 3.4 Locks and deadlocks       row locks, the wait graph, the victim      │
│ 3.5 SI against serializable   what SSI adds, what it costs, the retry    │
│ 3.6 Optimistic, pessimistic   FOR UPDATE, version columns, contention    │
│ 3.7 Isolation in the queue    claim, approval, outbox at READ COMMITTED  │
│ Lab: E1 to E16. The demonstration: E4, E5 and E10                        │
└──────────────────────────────────────────────────────────────────────────┘
```

## What this phase assumes

Three ideas from earlier are used here and not taught again.

- **The write path.** From this course's Phase 1, sections 1.2 and 1.7. A commit is durable once its commit record is on stable storage, in the WAL. The data pages follow later, and recovery replays the log after a crash. Section 1.7 wrote the store's promise down as one sentence, the durability boundary.
- **The heap and the TID.** From this course's Phase 2, section 2.2. PostgreSQL keeps a table's rows in a heap, a file of 8 kB pages in no key order. A TID, a page number and a line pointer number, names one row version, and every index entry holds one.
- **Concurrency correctness in one process.** From elite-performance Phase 4, parts 04a "Shared state" and 04b "Lifetimes and tests". A logical race is a result that depends on the order of steps, even when each step is atomic. Its common form is check-then-act: code checks a value, then acts on it, and the value changes in between. Section 4.8 of that course added the rule that this phase's labs follow. A concurrency test proves something only when it chooses the order of steps.

**The running system.** This phase uses the course's own small task-queue schema, which section 3.7 audits. Workers claim queued tasks, and a human approves or rejects some of them. Every change produces an event for other services. Its tables are `tq_tasks`, `tq_approvals`, `tq_outbox` and `tq_oncall`, plus `tq_budget`, which holds each tenant's credits. A tenant is a customer account, such as `acme`.

**Left for later.** Course 5, "Distributed systems and verification", covers transactions across services, and sagas, in its Phase 2. It also covers replicas, so this phase keeps to one server. Phase 4 of this course covers vacuum, the cleanup of old row versions, freezing, and the locks that schema changes take.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. The labs need your local PostgreSQL 14 at `/tmp:5432`, in the database `storage_lab`, which Phase 1 created. They use Python 3.12 or later with psycopg 3.3.6, which `pyproject.toml` pins. The model `mvcc_model.py` and every `--self-test` run with no server. Run all the commands from `elite-storage/code/`.

Time: about 3.5 hours for the reading, a little over the spec's 3 hours, because of the production signals. The labs take 3 to 4 hours.

---

## 3.1 — Atomicity and isolation (what each one promises: "all or nothing" against "as if alone")

Why this matters: in the running case, each approver's transaction was atomic, and the rule still broke. Atomicity and isolation are two separate promises, kept by two separate mechanisms. A design that relies on the wrong one passes every test that runs one session at a time.

**Answer this first.** A transfer moves 80 credits from `acme` to `beta` with two UPDATEs in one transaction. Both rows start at 100 credits. Answer three questions before you read on:

1. The server crashes after the first UPDATE. What do `acme` and `beta` hold after recovery?
2. While the transfer is open, a report runs one `SELECT sum(credits)` over both rows at READ COMMITTED. Can the sum it returns be 120?
3. The report instead reads `acme` and then `beta` with two SELECTs, and the transfer commits between them. What total can the report print?

**The mental model.** A transaction is the group of statements between BEGIN and COMMIT. Two separate promises apply to a transaction:

- **Atomicity** is about what a failure leaves behind. Either every change of the transaction takes effect, or none does. The PostgreSQL 14 tutorial, section 3.4, says a transaction "bundles multiple steps into a single, all-or-nothing operation". A crash, an error or a ROLLBACK must leave no part of it behind.
- **Isolation** is about other transactions that run at the same time. The strongest form is called serializable. The result is then the same as if the transactions had run one at a time, in some order. An **isolation level** is a weaker form that the database offers for speed. It names the anomalies it allows. An **anomaly** is a result that no one-at-a-time order of the same transactions could produce.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Two promises, two mechanisms, two kinds of failure                       │
├──────────────────────────────────────────────────────────────────────────┤
│                 ATOMICITY                  │ ISOLATION                   │
│ protects from   a crash, an error, or a    │ other transactions running  │
│                 ROLLBACK in the middle     │ at the same time            │
│ the promise     all changes or none        │ as if each ran alone, at    │
│                                            │ the level you chose         │
│ PostgreSQL      one commit record in the   │ row versions and snapshots, │
│ mechanism       WAL, and one status entry  │ 3.2, plus row locks, 3.4,   │
│                 per transaction in pg_xact │ plus SSI checks, 3.5        │
│ breaks when     the client cannot tell     │ two correct transactions    │
│                 whether COMMIT happened    │ produce a wrong result      │
└──────────────────────────────────────────────────────────────────────────┘
```

**How PostgreSQL makes a transaction atomic.** Four facts work together:

1. A transaction that writes gets a transaction ID, an `xid`. You can read it with `pg_current_xact_id()`. Verified from the PostgreSQL 14 docs, section 9.26. Until its first write, a transaction has only a virtual ID, which never reaches a data page. Calling `pg_current_xact_id()` assigns a real ID, and `pg_current_xact_id_if_assigned()` does not. Verified from Rogov, "PostgreSQL 14 Internals", section 3.6, page 75.
2. Every row version it writes carries that ID in the header field `t_xmin`. The docs call it the "insert XID stamp". Verified from the PostgreSQL 14 docs, section 70.6, Table 70.4.
3. At COMMIT the server writes one commit record to the WAL and flushes it, as Phase 1, section 1.2, showed. It also records the outcome in `pg_xact`, the "Subdirectory containing transaction commit status data". Verified from the PostgreSQL 14 docs, section 70.1.
4. A reader decides about each row version by asking whether its `xid` committed. So every version of one transaction becomes visible at the same moment, when the status changes. The tutorial says the updates "become visible simultaneously".

After a ROLLBACK or a crash, the versions stay in the table. Every reader finds their `xid` aborted, or never committed, and skips them. In the visibility code, `heapam_visibility.c` line 1060 at tag REL_14_24, the comment says "it must have aborted or crashed". The function then returns false, so the version is invisible. So PostgreSQL needs no undo pass for table rows. The ARIES design of Phase 1, section 1.5, needs one: its restart undoes the changes of transactions that never committed. Rogov, page 72, confirms it for PostgreSQL 14: on ROLLBACK, "no actual data rollback is happening". The skipped versions take space until vacuum removes them, which is Phase 4.

**How isolation is defined.** The SQL standard defines its levels by four phenomena that must not occur. The PostgreSQL 14 docs, section 13.2, list them. A dirty read sees another transaction's uncommitted data. A nonrepeatable read finds a row changed and committed since the first read. A phantom read finds a different set of rows for the same search condition. A serialization anomaly is a result that no one-at-a-time order produces. Table 13.1 of the same docs gives what each PostgreSQL level allows. It is the same in PostgreSQL 14 and 18:

| Level | Dirty read | Nonrepeatable read | Phantom read | Serialization anomaly |
|---|---|---|---|---|
| Read uncommitted | allowed, but not in PG | possible | possible | possible |
| Read committed, the default | not possible | possible | possible | possible |
| Repeatable read | not possible | not possible | allowed, but not in PG | possible |
| Serializable | not possible | not possible | not possible | not possible |

PostgreSQL's READ UNCOMMITTED behaves like READ COMMITTED, so PostgreSQL has three real levels. The default level is READ COMMITTED. Verified from the PostgreSQL 14 docs, sections 13.2 and 20.11.

The table has no row for the opening case. Lost updates and write skew both fall inside "serialization anomaly". Berenson and five co-authors wrote "A Critique of ANSI SQL Isolation Levels", SIGMOD 1995. They named the standard's three phenomena P1, P2 and P3. They showed that these three miss other anomalies, and named those too. Two of them are the lost update, P4, and write skew, A5B. Sections 3.2 to 3.4 use those names.

**The answers.** For question 1, `acme` and `beta` both hold 100. The commit record never reached the WAL, so recovery treats the transfer as not committed. For question 2, the answer is no. The SELECT reads one snapshot, and an uncommitted debit is never visible in PostgreSQL, at any level. So the SELECT returns 200. For question 3, the report can print 280 at READ COMMITTED. It reads `acme` as 100 before the commit, then `beta` as 180 after it. Each read was correct, and the total is one that never existed. Section 3.2 shows why REPEATABLE READ prints 200 here.

**The failure: atomic is not isolated.** The opening case is the plain form. A second form is at the edge of the database. ROLLBACK undoes rows, and nothing else. A message sent to another service, or an HTTP call, inside a transaction stays sent when the transaction rolls back. Section 3.7 builds the fix, the transactional outbox.

A third form hides in COMMIT itself. If the connection drops while COMMIT is in progress, the client does not know whether the transaction committed. Sending it again can apply it twice. The PostgreSQL 14 docs, section 9.26, describe `pg_xact_status(xid8)` for this case. It returns "in progress", "committed" or "aborted" for a recent transaction ID. So a client that saved its `xid` before COMMIT can ask afterwards.

**Part of a transaction: savepoints.** A savepoint marks a point inside a transaction. You can roll back to it without losing the rest of the transaction. `SAVEPOINT s` sets it, and `ROLLBACK TO SAVEPOINT s` undoes only the work after it. PostgreSQL builds this from subtransactions. A subtransaction is a part of a transaction with its own transaction ID and its own status in `pg_xact`. Rogov, pages 76 and 77, prints one PostgreSQL 14 transaction whose rows carry three `xmin` values. They are 782 for the transaction, and 783 and 784 for two subtransactions. The row of the subtransaction that rolled back stays on the page, and readers skip it.

You create subtransactions more often than you write SAVEPOINT:

| What you write | What PostgreSQL runs | Source |
|---|---|---|
| `SAVEPOINT s` | one subtransaction | Rogov, page 76 |
| a PL/pgSQL block with `EXCEPTION` | a subtransaction for the block | Rogov, page 78 |
| psql with `\set ON_ERROR_ROLLBACK on` | "an implicit savepoint before each command" | Rogov, page 79 |
| Rails `transaction(requires_new: true)` inside a transaction | `SAVEPOINT active_record_1` | GitLab's post of 2021-09-29, "Why would you use a SAVEPOINT?" |

The PostgreSQL 14 docs, section 43.6.8, warn about the cost. A block with EXCEPTION "is significantly more expensive to enter and exit than a block without one". Rogov, page 79, says that savepoints incur "significant overhead" even when nobody rolls back to them. Section 3.2 shows where that cost comes from, once snapshots are defined. Section 3.5 shows what a savepoint can rescue after an error.

The next section shows the mechanism behind isolation in PostgreSQL: what a statement sees, and why.

**The sentence to remember:** atomicity decides what a failure leaves behind. Isolation decides what concurrent transactions see of each other. Two atomic transactions can still break a rule together.

**The trap:** treating one transaction as protection from other sessions. At READ COMMITTED, a transaction protects its writes from failure. It does nothing to stop other writers from changing what it read.

**Try this now:** run `psql -h /tmp -p 5432 -d storage_lab -c "show default_transaction_isolation" -c "select pg_current_xact_id()" -c "select pg_current_xact_id()"`. You should see `read committed` and two different IDs, because each statement ran in its own transaction. Then run it with `-c "begin" -c "select pg_current_xact_id_if_assigned()"` before the two SELECTs. The new SELECT returns an empty value, NULL, because the transaction has only a virtual ID. The two IDs after it are the same.

---

## 3.2 — MVCC (how snapshots work, why readers do not block writers, and what a snapshot cannot see)

Why this matters: every PostgreSQL statement reads through a snapshot. The snapshot decided question 3 of section 3.1, and it decides every anomaly of section 3.3. From its three numbers and the IDs on a row, you can say what a statement will see.

**Answer this first.** Transaction 700 wrote the row `acme` with 100 credits and committed long ago. Transaction 801 runs `UPDATE tq_budget SET credits = 20 WHERE tenant = 'acme'` and has not committed yet.

1. How many versions of the row are now on the page? Give each one's `xmin` and `xmax`.
2. A statement takes the snapshot `801:803:801`. Which credits value does it see?
3. Next, transaction 801 commits its UPDATE. A REPEATABLE READ transaction that took the snapshot `801:803:801` earlier reads the row again. What does that transaction see now? What does a READ COMMITTED transaction see?

**The mental model.** MVCC, multiversion concurrency control, keeps several versions of a row at once. An UPDATE does not change a row in place. It writes a new version and marks the old one as replaced. A DELETE only marks the version as deleted. A snapshot records which transactions had finished when it was taken. For each row, a statement sees one version. Its snapshot counts that version's writer as committed, and its replacer as not. A reader reads an old version while a writer adds a new one, so neither waits for the other. The PostgreSQL 14 docs, section 13.1, put it this way: "reading never blocks writing and writing never blocks reading".

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One row of tq_budget after transaction 801's UPDATE. A worked example    │
├──────────────────────────────────────────────────────────────────────────┤
│ line pointer 1   credits 100   xmin 700   xmax 801   t_ctid (0,2) ──┐    │
│ line pointer 2   credits 20    xmin 801   xmax 0     t_ctid (0,2) ◄─┘    │
├──────────────────────────────────────────────────────────────────────────┤
│ snapshot 801:803:801    xmin 801    xmax 803    in progress: 801         │
├──────────────────────────────────────────────────────────────────────────┤
│ version 1: writer 700 < 801, finished and committed     -> written       │
│            replacer 801 is in progress for this snapshot -> not replaced │
│            so version 1 is visible: credits 100                          │
│ version 2: writer 801 is in progress for this snapshot   -> not visible  │
└──────────────────────────────────────────────────────────────────────────┘
```

**The fields on each version.** The header of every row version holds the fields that the diagram shows. Verified from the PostgreSQL 14 docs, sections 5.5 and 70.6:

- `xmin` is "The identity (transaction ID) of the inserting transaction for this row version". The docs add that "each update of a row creates a new row version for the same logical row".
- `xmax` is the ID of the deleting transaction, "or zero for an undeleted row version". It can be set on a version that is still visible, when the deleter has not committed or rolled back.
- `t_ctid` is the "current TID of this or newer row version". A TID is the page number and line pointer number of Phase 2, section 2.2. So the old version points to its replacement, and the versions of one row form a chain.
- The fixed header is "23 bytes on most machines", and every version pays it.

This is the reason that Phase 2 promised. PostgreSQL writes a new version on UPDATE because the old version must stay readable. Every snapshot that counts the updater as unfinished must still find it. That is also why each index in Phase 2 needed a new entry for the new version. The exception was a heap-only tuple update. It needs no new index entries when no indexed column changes and the page has free space. The link between the two is inferred from the visibility rule below.

**The snapshot.** A snapshot has three parts. Verified from the PostgreSQL 14 docs, section 9.26, Table 9.77, and from `src/include/utils/snapshot.h` at REL_14_24, lines 157 to 169:

- **xmin**, the "Lowest transaction ID that was still active". Every lower ID had finished by then.
- **xmax**, "One past the highest completed transaction ID". Every ID at or above it had not finished, "and thus are invisible".
- **xip_list**, the list of transactions still in progress. An ID between xmin and xmax that is not in the list had finished.

The text form is `xmin:xmax:xip_list`, and the docs' example is `10:20:10,14,15`. The function `pg_current_snapshot()` returns the current snapshot. Sessions can also share one snapshot. `pg_export_snapshot()` returns an ID, and another REPEATABLE READ transaction adopts it with `SET TRANSACTION SNAPSHOT` before its first statement. Parallel `pg_dump` uses this, so all its processes read one state. Verified from Rogov, section 4.7, pages 90 and 91.

**The visibility rule.** A version is visible to a snapshot when two things hold:

1. Its `xmin` is the reader's own transaction, or a transaction the snapshot counts as finished that committed.
2. Its `xmax` is zero, or belongs to a transaction that aborted, or that the snapshot counts as unfinished.

One case needs care. A `SELECT ... FOR UPDATE` also writes its ID into `xmax`, as section 3.4 shows, but only as a lock. Such an `xmax` never hides the version. The check is at `heapam_visibility.c` line 1079, tag REL_14_24, where `HEAP_XMAX_IS_LOCKED_ONLY` returns true.

Here are the two halves in the source. `XidInMVCCSnapshot` answers whether an ID was unfinished for this snapshot. `TransactionIdDidCommit` looks the outcome up in `pg_xact`:

```c
/* src/backend/access/heap/heapam_visibility.c, HeapTupleSatisfiesMVCC(), REL_14_24.
   Lines 1053 to 1063, then 1119 to 1128. Copied from the source, cut at ... */
		else if (XidInMVCCSnapshot(HeapTupleHeaderGetRawXmin(tuple), snapshot))
			return false;
		else if (TransactionIdDidCommit(HeapTupleHeaderGetRawXmin(tuple)))
			SetHintBits(tuple, buffer, HEAP_XMIN_COMMITTED,
						HeapTupleHeaderGetRawXmin(tuple));
		else
		{
			/* it must have aborted or crashed */
			...
			return false;
		}
	...
		if (XidInMVCCSnapshot(HeapTupleHeaderGetRawXmax(tuple), snapshot))
			return true;

		if (!TransactionIdDidCommit(HeapTupleHeaderGetRawXmax(tuple)))
		{
			/* it must have aborted or crashed */
			...
			return true;
		}
```

`SetHintBits` stores the outcome in the version's header, so later readers skip the `pg_xact` lookup. The comment above the function, lines 937 to 956, explains one rule. It does not set them while the writer still counts as running for the reader. Hint bits have a cost that surprises people. The first readers after a bulk load set them. So a plain SELECT can leave "a trail of dirtied pages in the buffer cache". Verified from Rogov, page 71. Whether setting them also writes WAL when data checksums are on was not checked.

**When a snapshot overflows.** A snapshot must also count the subtransactions of section 3.1 as running. A backend is the server process of one session. Each backend advertises up to 64 subtransaction IDs of its current transaction. That is `PGPROC_MAX_CACHED_SUBXIDS` at `proc.h` line 36, REL_14_24, and its comment calls 64 a "guessed-at value". Past 64, the cache overflows, and snapshots taken while that transaction runs are marked `suboverflowed`. Then `XidInMVCCSnapshot` cannot search the snapshot's list of subtransaction IDs. It first reads `pg_subtrans` to map each ID to its top-level transaction. Verified from `snapmgr.c`, lines 2285 to 2320, REL_14_24.

`pg_subtrans` is read through an SLRU, a small cache of pages in shared memory, like the one for `pg_xact`. In PostgreSQL 14 it has 32 pages, `NUM_SUBTRANS_BUFFERS` at `subtrans.h` line 15. PostgreSQL 17 added the setting `subtransaction_buffers` to size it. The current docs give its default as `shared_buffers`/512, up to 1024 blocks and at least 16. The setting is absent from the version 16 docs. The view `pg_stat_activity` shows what each session waits for, in the columns `wait_event_type` and `wait_event`. A wait for this cache shows there as type `LWLock`, a lightweight lock on a shared-memory structure, with the event `SubtransSLRU`. The 14 docs, Table 28.12, describe it as "Waiting to access the sub-transaction SLRU cache".

GitLab described this failure on 2021-09-29, in "Why we spent the last month eliminating PostgreSQL subtransactions". The database on GitLab.com stalled for minutes, and queries waited on `SubtransControlLock`. PostgreSQL 13 renamed that wait `SubtransSLRU`. Only the replicas stalled, and each time a long transaction was open. A test by Nikolay Samokhvalov fell from about 360,000 to 50,000 transactions per second on the replicas. It fell when a long transaction started on the primary. The post found that "a single SAVEPOINT during a long-transaction could initiate this problem if many writes also occurred simultaneously". GitLab's code never nested more than 10 savepoints, so the replica path into `pg_subtrans` differs from the 64-entry overflow. The post explains that path, and course 5 owns replicas. GitLab then removed every SAVEPOINT from its code. For this phase, keep two facts. A savepoint is not free on a busy server. And `SubtransSLRU` is the wait event that names the cost.

**When the snapshot is taken.** This is the one difference between the two lower levels. Verified from the PostgreSQL 14 docs, sections 13.2.1 and 13.2.2:

- READ COMMITTED: a SELECT sees "a snapshot of the database as of the instant the query begins to run". Each statement takes a new one.
- REPEATABLE READ: the snapshot is "as of the start of the first non-transaction-control statement in the transaction". BEGIN does not take it, and the first SELECT or UPDATE does.

So the answers to the questions above are these. There are two versions: 100 with `xmin` 700 and `xmax` 801, and 20 with `xmin` 801 and `xmax` 0. The snapshot `801:803:801` sees 100, as the diagram works out. After 801 commits, the REPEATABLE READ transaction still sees 100, because it keeps its snapshot. A READ COMMITTED statement takes a new snapshot, for example `803:803:`, counts 801 as finished, and sees 20.

The same rule explains the report of section 3.1, step by step:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The report reads acme, then beta. The transfer moves 80 between them     │
├──────────────────────────────────────────────────────────────────────────┤
│ step                          READ COMMITTED    │ REPEATABLE READ        │
│ report: SELECT acme           new snapshot: 100 │ snapshot taken: 100    │
│ transfer: UPDATE acme - 80                      │                        │
│ transfer: UPDATE beta + 80                      │                        │
│ transfer: COMMIT                                │                        │
│ report: SELECT beta           new snapshot: 180 │ same snapshot: 100     │
│ report total                  280, never real   │ 200, a real state      │
├──────────────────────────────────────────────────────────────────────────┤
│ read skew, A5A in Berenson et al. 1995: r1[x] w2[x] w2[y] c2 r1[y]       │
└──────────────────────────────────────────────────────────────────────────┘
```

This anomaly is called **read skew**. Berenson and others write it as the history `r1[x]...w2[x]...w2[y]...c2...r1[y]`. A history is the order of reads `r`, writes `w` and commits `c` of numbered transactions. Their Table 4 lists it as not possible under snapshot isolation. Verified from the paper, section 4.2 and Table 4.

**Snapshot isolation** is the name for this design. Each transaction reads from one snapshot taken at its start. Its writes are checked against the writes of concurrent transactions, and the second writer of the same row fails. Section 3.3 shows that check at work. PostgreSQL uses it for REPEATABLE READ. The docs, section 13.2.2, say the level "is implemented using a technique known in academic database literature and in some other database products as Snapshot Isolation".

So PostgreSQL's "repeatable read" is not the repeatable read of a locking database. Berenson and others, Remark 9, state that the two are incomparable. Each one allows an anomaly that the other forbids. Snapshot isolation allows write skew, which locking repeatable read forbids. Locking repeatable read allows phantoms in the strict sense, a re-read that finds new rows, which snapshot isolation forbids. Verified from the paper, section 4.2, page 9. Jepsen's PostgreSQL 12.3 report, section 3.1, found the same. Its histories at PostgreSQL's repeatable read were "consistent with strong snapshot isolation". They also had anomalies that formal repeatable read forbids.

The same level name means different things in other engines, and they also store versions differently. CMU 15-445, Fall 2025, lecture 20, slide 33, compares the designs:

| Engine | Protocol | Where versions live | Cleanup | Index entries point to |
|---|---|---|---|---|
| PostgreSQL | MV-2PL/MV-TO | append-only: each version is a whole row in the table | vacuum | the physical version |
| MySQL InnoDB | MV-2PL | delta: the row is overwritten, and changed values are copied to a delta area | vacuum | the logical row |
| Oracle | MV2PL | delta | vacuum | the logical row |

Append-only storage with physical pointers is why each PostgreSQL index needs a new entry for a new version, as Phase 2 found. Hermitage's README table shows that the level names differ too. MySQL InnoDB's default "repeatable read" allows the lost update, P4, which PostgreSQL's "repeatable read" prevents. So code that relies on PostgreSQL's 40001 at that level can lose updates on MySQL. The README links the MySQL 5.7 manual and does not state the version it tested. MySQL 8 was not checked.

One thing MVCC does not remove: writers of the same row still wait for each other. An UPDATE that finds the newest version replaced by a transaction still in progress waits for it. Section 3.4 covers that wait and its rules.

**What a snapshot cannot see.** Four limits follow from the rule. Section 3.3 is built on the second and the third.

1. **Commits after it was taken.** A REPEATABLE READ transaction keeps reading the old state, by design. The PostgreSQL 14 docs, section 13.2.2, give an example. A read-only transaction there can see a batch marked complete, without one of its detail records.
2. **Rows that concurrent transactions insert.** A transaction decides that no such row exists. Another transaction then inserts one and commits, and the decision does not change.
3. **Writes to what it read.** A snapshot takes no lock. So nothing stops another transaction from changing a row you read and committing. A decision made on the old value is then out of date.
4. **Its own cost.** While a snapshot may still need a replaced version, vacuum cannot remove it. Phase 4, section 4.5, calls the oldest such snapshot the cleanup horizon, and measures what it does to a table.

**The failure: one snapshot held for hours.** A session runs BEGIN, then waits for a user or a slow call. It keeps its snapshot all that time. The PostgreSQL 14 docs, section 20.11, say that "an open transaction prevents vacuuming away recently-dead tuples that may be visible only to this transaction". A recently-dead tuple is a replaced version that some open snapshot might still need. The docs add that "remaining idle for a long time can contribute to table bloat". The setting `idle_in_transaction_session_timeout` ends such sessions, and its default is 0, which means off. This is verified from the same section. In `pg_stat_activity`, such a session shows the state `idle in transaction`.

The next section uses those gaps to break three invariants of the task queue.

**The sentence to remember:** an UPDATE writes a new row version. A snapshot picks one version per row by transaction IDs. READ COMMITTED takes a snapshot per statement, and REPEATABLE READ one per transaction.

**The trap:** a report of several statements at READ COMMITTED. Each statement sees a different moment. So its totals can mix states from before and after a commit, such as the 280 above.

**Try this now:** run `psql -h /tmp -p 5432 -d storage_lab -c "create table p3_demo (k text primary key, v int)" -c "insert into p3_demo values ('acme', 100)" -c "select xmin, xmax, ctid, * from p3_demo" -c "update p3_demo set v = 20" -c "select xmin, xmax, ctid, * from p3_demo" -c "select pg_current_snapshot()" -c "drop table p3_demo"`. Look for the `ctid` moving, for example from `(0,1)` to `(0,2)`. Then look for `xmin` changing to the ID of the UPDATE's transaction.

---

## 3.3 — The anomalies (lost update, write skew and phantoms, each reproduced with two sessions)

Why this matters: each of the three anomalies is a pattern of reads and writes. You can spot it in code review. PostgreSQL's two lower levels allow at least one of them each. Each one needs a different fix, so naming the pattern names the fix.

**Answer this first.** Here are three transaction pairs from the task queue. For each one, say whether its invariant can break at READ COMMITTED, and at REPEATABLE READ.

1. Two workers each read `acme`'s 100 credits, check that 100 is at least 80, and write 20. Invariant: credits = 100 − 80 × the number of committed spends.
2. Alice and Bob each count the approvers on call, see 2, and set themselves off call. Invariant: at least 1 on call.
3. Two workers each count `acme`'s running tasks, see 0, and each move a different queued task to running. Invariant: at most 1 running task per tenant.

**The mental model.** All three are the check-then-act of elite-performance section 4.2, between two sessions instead of two tasks. Pair 1 is that section's wallet, two spends of 80 from 100. Each transaction reads, decides, and writes. They differ in where the write lands:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Read, decide, write. Where the write lands decides the anomaly           │
├──────────────────────────────────────────────────────────────────────────┤
│ anomaly        what both read          what each writes                  │
│ lost update    one row                 that same row                     │
│ write skew     a set of rows           a different row of that set       │
│ phantom        a set of rows defined   a new member of that set: a row   │
│                by a condition          that did not match when they read │
└──────────────────────────────────────────────────────────────────────────┘
```

The lab drives each pair in a fixed order with two psycopg connections. A third connection watches `pg_stat_activity` and `pg_blocking_pids()`. So the script knows that a session waits for a lock before it takes the next step. This is the rule from elite-performance section 4.8, applied to a database: the test chooses the order. From `shared/pglab.py:326`, with the docstring cut:

```python
# from shared/pglab.py:326, wait_until_waiting(). Docstring cut, logic unchanged
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = observer.execute(
            "SELECT wait_event_type, wait_event, pg_blocking_pids(pid) "
            "FROM pg_stat_activity WHERE pid = %s", (pid,)).fetchone()
        if row and row[0] == "Lock" and row[2]:
            return list(row[2])
        time.sleep(poll)
    raise LabError(f"backend {pid} did not start waiting for a lock within {timeout}s. "
                   "The order of steps this lab promises did not happen")
```

A test without this check can pass because the two sessions never overlapped. The wait event type `Lock` means that the backend waits for a heavyweight lock. A heavyweight lock lives in PostgreSQL's lock manager. Table locks and transaction ID locks are of this kind. `pg_blocking_pids` lists the sessions that block it. Verified from the PostgreSQL 14 docs, section 28.2, Table 28.4, and section 9.26.

### Lost update

A **lost update** happens when two transactions read the same row. Each one then writes a new value based on its own read. The second write replaces the first, as if the first never happened. Berenson and others, SIGMOD 1995, section 4.1, call it P4 and write it as `r1[x]...w2[x]...w1[x]...c1`. Hermitage, a test suite by Martin Kleppmann, ran PostgreSQL 9.3.5 against this pattern and the others of this section. Here is pair 1, in the order that its test "Lost Update (P4)" uses:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ lost_update.py --strategy naive. Expected, not run by the author yet     │
├──────────────────────────────────────────────────────────────────────────┤
│ step                         READ COMMITTED       │ REPEATABLE READ      │
│ T1 SELECT credits            100                  │ 100                  │
│ T2 SELECT credits            100                  │ 100                  │
│ T1 UPDATE credits = 20       1 row, row locked    │ 1 row, row locked    │
│ T2 UPDATE credits = 20       waits for T1         │ waits for T1         │
│ T1 COMMIT                    ok                   │ ok                   │
│ T2, after the wait           1 row: writes 20     │ ERROR 40001          │
│ T2 COMMIT                    ok                   │ ROLLBACK             │
├──────────────────────────────────────────────────────────────────────────┤
│ result                       160 spent from 100   │ 80 spent, credits 20 │
│                              BROKEN               │ holds                │
└──────────────────────────────────────────────────────────────────────────┘
```

At READ COMMITTED, T2 waits for T1's row lock, then goes on. The PostgreSQL 14 docs, section 13.2.1, give the rule. When the first updater commits, the second "will attempt to apply its operation to the updated version of the row". The WHERE clause "is re-evaluated to see if the updated version of the row still matches the search condition". T2's WHERE clause is `tenant = 'acme'`, which still matches. So T2 writes 20 again, a value it computed from a read that is now old. Two tasks ran on a budget that paid for one.

At REPEATABLE READ, T2 cannot change a row version that a concurrent transaction replaced. The same docs, section 13.2.2, say the transaction "will be rolled back with the message" `ERROR: could not serialize access due to concurrent update`. Its SQLSTATE is 40001, which is `serialization_failure`. The check is the branch for `TM_Updated` in `ExecUpdate`, at `nodeModifyTable.c` line 2006, tag REL_14_24. It raises the error only when `IsolationUsesXactSnapshot()` is true, which means REPEATABLE READ or SERIALIZABLE. This course calls the rule first-updater-wins: the second writer of a row fails. Berenson and others, and Cahill and others, name the same idea first-committer-wins. PostgreSQL applies it when the second writer tries the write, not at its commit.

The docs then say what to do: "abort the current transaction and retry the whole transaction from the beginning". The retry reads 20, sees that 20 is less than 80, and refuses the spend. Section 3.5 builds that retry in code.

READ COMMITTED has its own fix, with no retry. Put the check inside the UPDATE, so the server re-checks it after the wait. The WRONG and RIGHT forms are two entries of the lab's SQL table, from `phase03_transactions/lost_update.py:90`:

```python
# from phase03_transactions/lost_update.py:90, the SQL table. Copied, two entries
    # WRONG: the new value is computed in Python from an earlier read. After a
    # lock wait, READ COMMITTED re-checks only "tenant = 'acme'", which still
    # matches, so the second worker writes 100 - 80 again.
    "write_value": "UPDATE tq_budget SET credits = %s WHERE tenant = 'acme'",
    # RIGHT: the arithmetic and the check run on the row version the UPDATE
    # locks. After the wait, the server re-checks "credits >= 80" against 20.
    "write_atomic": ("UPDATE tq_budget SET credits = credits - %s "
                     "WHERE tenant = 'acme' AND credits >= %s RETURNING credits"),
```

The RIGHT form at READ COMMITTED is expected to go like this, from the docs' rule, not run. T2 waits, then returns 0 rows, and the worker refuses the task. The balance is 20 after one spend.

### What the re-check does not see

The atomic UPDATE is safe because of one mechanism, and that mechanism has a limit. PostgreSQL calls the re-check after a wait EvalPlanQual. The executor README, REL_14_24, lines 311 to 345, describes it. The server takes the newest version of the row it waited for, and runs the query's conditions again against it. The README adds: "In UPDATE/DELETE, only the target relation needs to be handled this way." So every other table in the statement, and every subquery, keeps the statement's old snapshot.

The PostgreSQL 14 docs, section 13.2.1, give the result. An updating command can "see an inconsistent snapshot". It sees the effects of concurrent commands "on the same rows it is trying to update". But "it does not see effects of those commands on other rows in the database". The docs conclude: "This behavior makes Read Committed mode unsuitable for commands that involve complex search conditions". Two failures follow from it.

**1. A subquery reads the old state.** Rogov, pages 50 and 51, ran this on PostgreSQL 14. Bob has two accounts, 200 and 800, so 1,000 in total. An interest UPDATE pays 1% to every client whose total is at least 1,000. Its condition is a subquery with `GROUP BY client HAVING sum(amount) >= 1000`.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One UPDATE reads two states. Rogov pp. 50-51, PostgreSQL 14, printed     │
├──────────────────────────────────────────────────────────────────────────┤
│ T1  BEGIN. UPDATE account 3 SET amount = amount - 100    800 -> 700      │
│ T2  interest UPDATE. Its subquery sees bob's total, 1,000: he qualifies  │
│ T2  updates bob's rows one by one. Account 3 is locked by T1: T2 waits   │
│ T1  COMMIT                                                               │
│ T2  re-checks account 3 only, and updates it from 700                    │
│     result: account 2 is 202, account 3 is 707, total 909                │
├──────────────────────────────────────────────────────────────────────────┤
│ Bob got 9 of interest on 900, but with 900 he did not qualify            │
└──────────────────────────────────────────────────────────────────────────┘
```

Rogov names the result read skew inside one statement: "different rows have been read from different snapshots". At REPEATABLE READ, the same interest UPDATE fails with 40001 instead, page 54.

**2. A row that starts to match is not seen.** The docs' own example uses a table `website` with two rows, `hits` 9 and 10. One session runs `UPDATE website SET hits = hits + 1` and has not committed. Another runs `DELETE FROM website WHERE hits = 10`. The docs say: "The DELETE will have no effect". Yet a row with 10 exists before the UPDATE and after it. The DELETE skipped the row that held 9, because 9 did not match in its snapshot. It waited on the row that held 10, and then re-checked 11.

So here is the rule that every READ COMMITTED fix in this phase relies on. A one-statement fix is safe when its condition reads only columns of the row it changes. `credits >= 80`, `state = 'queued'` and `running < max_running` all meet it. A condition with a subquery, a join or an aggregate over other rows does not meet it. Use SERIALIZABLE, a lock taken first, or a constraint for those. Rogov adds one more trap at this level, pages 49 and 50. A query that calls a VOLATILE function which runs its own query can see data that does not match the main query.

### Write skew

**Write skew** happens when two transactions read an overlapping set of rows. Each one then writes a different row of that set, based on what it read. No row is written twice, so first-updater-wins sees nothing. Berenson and others, section 4.2, call it A5B and write it as `r1[x]...r2[y]...w1[y]...w2[x]...(c1 and c2 occur)`. Their history H5 gives an example with numbers. The rule is x + y > 0, and both start at 50. Each transaction reads both, sees a sum of 100, and subtracts 90 from a different one. Both commit, and x + y = −80. Table 4 of the paper lists A5B as possible under snapshot isolation.

Pair 2, the opening case, is write skew. Alice read Bob's row and wrote her own. Bob read Alice's row and wrote his own. At REPEATABLE READ each still reads from its snapshot, and neither UPDATE touches a row that the other replaced. So both commit, with no error and no wait. The lab's expected output at REPEATABLE READ is two successful COMMITs and `RESULT: BROKEN. 0 approver(s) on call`. Not run by the author yet.

A CHECK constraint cannot hold this rule either. The rule that at least one row has `on_call` true is a statement about several rows. The PostgreSQL 14 docs, section 5.4, say so. "PostgreSQL does not support CHECK constraints that reference table data other than the new or updated row being checked." A unique index holds rules of the form "at most one", as section 3.6 shows. "At least one" is not of that form.

### Phantoms

A **phantom** is a row that matches a query's condition, but that the query did not see. When the query ran, the row did not exist or did not match yet. It comes in two forms with different outcomes in PostgreSQL.

The first form is the phantom read of section 3.1. One transaction runs the same count twice, and another transaction inserts a matching row in between. The lab command `phantom.py --case reread` shows it. Expected, not run by the author yet: at READ COMMITTED the counts are 2 and 3. At REPEATABLE READ they are 2 and 2, because the snapshot does not change. Table 13.1 lists the phantom read as "Allowed, but not in PG" at repeatable read.

The second form is pair 3, and the snapshot does not help there:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ phantom.py --case limit, REPEATABLE READ. Expected, not run yet          │
├──────────────────────────────────────────────────────────────────────────┤
│ W1 SELECT count(*) running for acme     0                                │
│ W2 SELECT count(*) running for acme     0                                │
│ W1 UPDATE task 7 SET state = 'running'  1 row                            │
│ W2 UPDATE task 8 SET state = 'running'  1 row, no wait: another row      │
│ W1 COMMIT                               ok                               │
│ W2 COMMIT                               ok                               │
├──────────────────────────────────────────────────────────────────────────┤
│ 2 running tasks for acme. The limit is 1. BROKEN                         │
└──────────────────────────────────────────────────────────────────────────┘
```

Each worker decided on a set that was empty, and then added a row to it. Berenson's section 4.2 gives the same shape with hours: both transactions see 7 of 8 hours, and each adds 1. Hermitage uses the names of Atul Adya's 1999 thesis. G-single is read skew, and G2-item is write skew on rows. G2 is the form with a search condition. Its table marks G2-item and G2 as possible at "repeatable read" and prevented at "serializable".

Here is the whole picture, as the course's model predicts it. Its rows `lost-update`, `write-skew` and `phantom-limit` answer the three questions at the start of this section:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ mvcc_model.py, the invariant at each level. Expected, not run            │
├──────────────────────────────────────────────────────────────────────────┤
│ history              READ COMMITTED   REPEATABLE READ   SERIALIZABLE     │
│ lost-update          BROKEN           holds, T2 40001   holds, T2 40001  │
│ lost-update-atomic   holds            holds, T2 40001   holds, T2 40001  │
│ write-skew           BROKEN           BROKEN            holds, T2 40001  │
│ phantom-limit        BROKEN           BROKEN            holds, T2 40001  │
│ read-skew            BROKEN           holds             holds            │
│ deadlock             holds, T2 40P01  holds, T2 40P01   holds, T2 40P01  │
├──────────────────────────────────────────────────────────────────────────┤
│ agrees with Hermitage's PostgreSQL rows, P4, G-single, G2-item and G2,   │
│ and with Berenson Table 4 for snapshot isolation: P4 and A5A not         │
│ possible, A5B possible                                                   │
└──────────────────────────────────────────────────────────────────────────┘
```

`mvcc_model.py` is a small pure-Python model of the rules in section 3.2 and of first-updater-wins. Its self-test asserts this matrix, then removes one rule at a time and asserts that the matrix changes. The model's limits are in its docstring. One of those limits matters here. A predicate lock is the record that SERIALIZABLE keeps of what a transaction read, which section 3.5 explains. The model puts one predicate lock on the whole table for every scan, as PostgreSQL does for a sequential scan.

### The read-only anomaly

Snapshot isolation allows one more anomaly, and the transaction that sees it writes nothing. Rogov, page 55, says snapshot isolation allows only two anomalies: write skew, and the read-only transaction anomaly. In the second, a transaction that only reads sees a state that no one-at-a-time order produces. Rogov's example on PostgreSQL 14, pages 56 to 58, runs three REPEATABLE READ transactions on Bob's accounts, 900 and 100:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The read-only anomaly. Rogov pp. 56-58, PostgreSQL 14, printed           │
├──────────────────────────────────────────────────────────────────────────┤
│ T1  adds 1% of bob's total to account 2. It reads 900 + 100. Open        │
│ T2  takes 100 from account 3, and commits. Account 3 is now 0            │
│ T3  read-only. Its snapshot includes T2 and not T1                       │
│ T1  COMMIT. Account 2 is now 910                                         │
│ T3  reads bob's accounts: 900 and 0                                      │
├──────────────────────────────────────────────────────────────────────────┤
│ T1 read account 3 before T2 changed it, so T1 must come before T2.       │
│ T3 saw T2 without T1. No one-at-a-time order matches what T3 saw         │
└──────────────────────────────────────────────────────────────────────────┘
```

Each transaction alone was correct. The PostgreSQL 14 docs, section 13.2.2, say that at this level "read-only transactions will never have serialization conflicts". That is true, and it is why this anomaly raises no error. The docs' batch example of section 3.2 has the same shape. That match is inferred, because the docs do not name the anomaly. Section 3.5 shows how SERIALIZABLE catches it.

The next section looks at the waits in the lost-update timeline. The level that stops write skew and the phantom comes after it.

**The sentence to remember:** a lost update writes the row it read. Write skew writes another row of the set it read. A phantom adds a row to the set it read. REPEATABLE READ stops the first, and only SERIALIZABLE stops the other two. READ COMMITTED's re-check covers only the row being changed.

**The trap:** adding `FOR UPDATE` to a query whose answer depends on rows that do not exist yet. It is the natural fix for pair 3: run `SELECT ... FOR UPDATE` before the count. At that moment acme has no running task, so the SELECT returns no rows and locks none. Both workers go on and claim, and the phantom passes every test that runs one session. `phantom.py --fix for-update` shows this result, not run by the author yet. A row lock can only cover a row that exists. Section 3.6 gives a fix that works at READ COMMITTED: it keeps the count in a row that always exists.

**Try this now:** run `uv run python phase03_transactions/mvcc_model.py`. Compare each cell with the diagram above. Then run it with `--history write-skew --level serializable --trace` and find the line where one transaction is doomed.

---

## 3.4 — Locks and deadlocks (row locks, the wait graph, how PostgreSQL chooses a victim, and how to read a deadlock report)

Why this matters: in the lost-update timeline, T2 stopped at its UPDATE until T1 committed. Every row a transaction writes stays locked until it ends. Two transactions that lock two rows in opposite orders wait for each other forever, unless the server breaks the cycle. The rules tell you which one fails, after how long, and how to make the cycle impossible.

**Answer this first.** T1 moves 10 credits from `acme` to `beta`. T2 moves 10 credits from `beta` to `acme`. The steps run in this order: T1 updates `acme`, T2 updates `beta`, T2 updates `acme`, T1 updates `beta`. The server runs with default settings. Which of the two gets an error? About how long after its wait began? What happens to the other one?

**The mental model.** A row lock in PostgreSQL has two parts:

1. **A mark on the row.** UPDATE, DELETE and `SELECT ... FOR UPDATE` write their transaction ID into the row's `xmax`. So the lock lives on the page, not in memory. The PostgreSQL 14 docs, section 13.3.2, say there is "no limit on the number of rows locked at one time". They add that "locking a row might cause a disk write".
2. **A wait on the holder's transaction.** Each transaction holds an exclusive lock on its own ID until it ends. `XactLockTableInsert` takes it, and its comment says "The lock can then be used to wait for the transaction to finish". Verified at `lmgr.c` lines 585 to 600, tag REL_14_24. A second writer may find the row marked by a running transaction. It then requests a `ShareLock` on that transaction's ID, at `lmgr.c` line 668. So it sleeps until the holder commits or aborts.

This wait is what stops a dirty write, P0 in Berenson and others: `w1[x]...w2[x]` before the first transaction ends. Their Remark 3 says every level should forbid it. Hermitage's G0 test, "Write Cycles", shows PostgreSQL's read committed blocks the second write until the first transaction commits.

**The queue of waiters is not a fair queue.** A row lock lives in the row. So the server needs one more lock to order several waiters. `README.tuplock`, REL_14_24, lines 14 to 37, gives the steps that each writer of a locked row follows:

1. Take a heavyweight lock on the tuple. A tuple lock names one row version by its TID.
2. Wait on the holder's transaction ID, with the `ShareLock` above.
3. Write its own ID into `xmax`.
4. Release the tuple lock.

The README gives the reason for step 1. A wait on the transaction ID alone "will release all waiters concurrently". That leads to "indefinite starvation of some waiters". So the first waiter holds the tuple lock and waits on the transaction ID. Every later waiter waits on the tuple lock. Rogov, page 219, printed this from `pg_stat_activity` on PostgreSQL 14, with four sessions updating one row:

```text
  pid  | wait_event_type |  wait_event   | pg_blocking_pids
-------+-----------------+---------------+------------------
 30723 | Client          | ClientRead    | {}
 30794 | Lock            | transactionid | {30723}
 30865 | Lock            | tuple         | {30794}
 30936 | Lock            | tuple         | {30794,30865}
```

The order holds for the first hand-over only. When 30723 commits, 30794 gets the row and releases the tuple lock. At READ COMMITTED, 30865 and 30936 then find a new `xmax`, and wait on 30794's transaction ID with no tuple lock. Rogov, page 220, says they now risk a race, and "The queue has virtually fallen apart." So under one hot row, a writer can wait longer than its place in line suggests. At REPEATABLE READ, the woken waiters fail with 40001 instead, page 219. `lockwatch.py --case queue` prints both pictures and the order it saw, E13.

The **wait graph** has one node per transaction. It has an edge from A to B when A waits for a lock that B holds. A **deadlock** is a cycle in that graph. No transaction in a cycle can move, so the server must cancel one.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ deadlock.py until the cycle closes. Example times, not run               │
├──────────────────────────────────────────────────────────────────────────┤
│ t        T1                          T2                                  │
│          UPDATE acme - 10: locked                                        │
│                                      UPDATE beta - 10: locked            │
│ 0.00 s                               UPDATE acme + 10: waits for T1      │
│ 0.01 s   UPDATE beta + 10: waits                                         │
│          for T2. The cycle is closed                                     │
├──────────────────────────────────────────────────────────────────────────┤
│ wait graph at 0.01 s:   T1 ──waits for──► T2 ──waits for──► T1           │
└──────────────────────────────────────────────────────────────────────────┘
```

**How PostgreSQL finds the cycle.** It does not search the graph at every wait. The search is costly, and most waits end soon. The lmgr README at REL_14_24, lines 340 to 360, describes the design:

1. A process that cannot get a lock goes to sleep. It sets a timer of `deadlock_timeout`.
2. If the timer fires before the lock is granted, that process runs the deadlock check.
3. If a deadlock exists, it "will be resolved, usually by aborting the detecting process' transaction".

The default `deadlock_timeout` is "one second (1s), which is probably about the smallest value you would want in practice". In PostgreSQL 14, only superusers can change it. Verified from the PostgreSQL 14 docs, section 20.12.

**Which transaction is the victim.** The README, lines 553 to 555, adds a rule. "If earlier waiters in the cycle have not yet run CheckDeadLock, then the first one to do so will be the victim." The first waiter's timer fires first. In this schedule T2 waited first, so T2 is the expected victim. That is inferred from the README, not from a run. Three exceptions are verified from the same source:

- Before it cancels anyone, the check tries to reorder wait queues. This breaks some cycles without an abort. See the README, lines 518 to 524.
- Some waits fail at once, with no timer. This happens when the new waiter and a waiter in the same lock's queue each need the other. The code is `RememberSimpleDeadLock`, at `proc.c` line 1209.
- An autovacuum worker that blocks the waiter is cancelled instead. The log then says "sending cancel to blocking autovacuum PID %d". The code is at `proc.c` line 1480.

The PostgreSQL 14 docs, section 13.3.4, say not to build on any of this. "Exactly which transaction will be aborted is difficult to predict and should not be relied upon."

In textbook terms, PostgreSQL detects deadlocks and does not prevent them. The CMU 15-445 notes, Fall 2025, lecture 18, describe both approaches. Detection builds the waits-for graph and breaks a cycle by choosing a victim. Prevention schemes, such as wait-die and wound-wait, abort a transaction by priority before a cycle can form. The notes name the trade-off that `deadlock_timeout` sets: the cost of checks against the time until a deadlock is broken.

Rogov's run on PostgreSQL 14, page 227, agrees with the rule. The transaction that waited first ran the check "and gets aborted by the server". So here is the expected answer, inferred and not run. T2's timer fires about 1 second after it began to wait. T2 runs the check, finds the cycle, and gets SQLSTATE 40P01, `deadlock_detected`. Its transaction is rolled back. T1's waiting UPDATE is granted next, and T1 commits. The total of the two balances stays 200.

**Reading the report.** `DeadLockReport` in `deadlock.c`, REL_14_24, lines 1089 to 1153, builds the error. The parts are verified from that source:

- the message: `deadlock detected`
- one DETAIL line per process in the cycle: `Process %d waits for %s on %s; blocked by process %d.`
- the HINT: `See server log for query details.`
- in the server log only, one more line per process: `Process %d: %s`, with the text of its query.

For this lab, the printed error should look like the lines below. The lock mode comes from the `ShareLock` request above, and `transaction %u` is how `DescribeLockTag` names a transaction ID. The CONTEXT line comes from the error context of the row wait, `while updating tuple (%u,%u) in relation "%s"`, at `lmgr.c` line 831. Rogov, page 227, printed this form on PostgreSQL 14 for two transfers. His lines include `DETAIL: Process 30423 waits for ShareLock on transaction 122877; blocked by process 30723.` and `CONTEXT: while updating tuple (0,2) in relation "accounts"`. So the form is verified. The process and transaction numbers below are an example, and the lab was not run:

```
ERROR 40P01: deadlock detected
      DETAIL: Process 41022 waits for ShareLock on transaction 901; blocked by process 41018.
              Process 41018 waits for ShareLock on transaction 902; blocked by process 41022.
      HINT: See server log for query details.
      CONTEXT: while updating tuple (0,1) in relation "tq_budget"
```

Read it as the wait graph. Each DETAIL line is one edge. The process numbers are the process IDs of the backends, which `pg_stat_activity.pid` shows. Every lab session sets `application_name` to `storage_lab`, so you can find them there. The transaction numbers are the IDs each process waits for. The CONTEXT line names the row the victim wanted. The queries themselves are only in the server log, which is why the HINT points there.

**Settings that decide how waits look, and when they end.** Without a deadlock, a wait has no limit. The docs, section 13.3.4, say a transaction seeking a lock "will wait indefinitely for conflicting locks to be released". So it is "a bad idea" to hold transactions open for a long time. These settings put limits on it. The first five rows are verified from the PostgreSQL 14 docs, sections 20.8, 20.11 and 20.12. The version column comes from the docs of each version:

| Setting | Default | What it does | Exists since |
|---|---|---|---|
| `deadlock_timeout` | 1s | the wait before the deadlock check, and before a `log_lock_waits` line | before 14 |
| `log_lock_waits` | off, also in 18 | logs each wait longer than `deadlock_timeout` | before 14 |
| `lock_timeout` | 0, off | cancels a statement that waits longer for one lock | before 14 |
| `statement_timeout` | 0, off | cancels a statement that runs longer | before 14 |
| `idle_in_transaction_session_timeout` | 0, off | ends a session idle inside an open transaction | before 14 |
| `idle_session_timeout` | 0, off | ends a session idle outside a transaction | 14, absent from the 13 docs |
| `transaction_timeout` | 0, off | ends a session whose transaction lasts longer | 17, absent from the 16 docs |

Set them per role with `ALTER ROLE ... SET`, or per transaction with `SET LOCAL`, as the claim check of section 3.7 does. That is this course's advice, and the docs point the same way. They say that setting `statement_timeout` or `lock_timeout` in `postgresql.conf` "is not recommended because it would affect all sessions". The current docs say the same of `transaction_timeout`. They also warn against `idle_session_timeout` on connections from "connection-pooling software", which "may not react well to unexpected connection closure".

**Row locks are not the only locks.** Every statement also takes a lock on each table it uses. A SELECT takes `ACCESS SHARE`, which "Conflicts with the ACCESS EXCLUSIVE lock mode only". The docs add: "Only an ACCESS EXCLUSIVE lock blocks a SELECT". A waiting request also blocks later requests that conflict with it. `pg_blocking_pids` reports this as a "soft block", by a session that is "ahead of it in the wait queue". Verified from the PostgreSQL 14 docs, sections 13.3.1 and 9.26. Phase 4, section 4.7, builds the schema-change rules on these two facts.

**The row-lock modes.** There are four. Table 13.3 of the docs gives their conflicts, X for a conflict:

| Requested, held → | FOR KEY SHARE | FOR SHARE | FOR NO KEY UPDATE | FOR UPDATE |
|---|---|---|---|---|
| FOR KEY SHARE | | | | X |
| FOR SHARE | | | X | X |
| FOR NO KEY UPDATE | | X | X | X |
| FOR UPDATE | X | X | X | X |

An UPDATE takes `FOR NO KEY UPDATE`, unless it changes a column with a unique index that a foreign key can use. Then it takes `FOR UPDATE`, as every DELETE does. Verified from the docs, section 13.3.2. The docs add one more rule for REPEATABLE READ and SERIALIZABLE. There, "an error will be thrown if a row to be locked has changed since the transaction started". That is the 40001 of section 3.3 again, now for `SELECT ... FOR UPDATE`.

**When several transactions lock one row: multixacts.** `xmax` has room for one transaction ID. When several transactions hold compatible locks on one row, PostgreSQL stores a multixact ID there instead. A multixact is a group of transaction IDs with their lock modes, kept in `pg_multixact`. Verified from the PostgreSQL 14 docs, section 25.1.5.1. The usual source is a foreign key. Rogov, page 213, says that of the shared modes, the core "uses only Key Share", for foreign key checks.

The course's own schema creates this case. `tq_tasks.tenant` references `tq_tenants`, so inserting a task for `acme` takes FOR KEY SHARE on acme's row. The slot reservation of section 3.6 updates that row with FOR NO KEY UPDATE. The table above shows no conflict between the two, so neither waits, and the row's `xmax` becomes a multixact. That is inferred from Table 13.3. Rogov, page 214, prints `pgrowlocks` for the same pair of modes on PostgreSQL 14. There `multi` is `t`, and the modes are `{"Key Share","No Key Update"}`. `lockwatch.py --case multixact` shows it on the course schema, not run by the author yet.

Multixacts have their own wraparound, as transaction IDs do. The docs say the member storage "can grow up to about 20GB before reaching wraparound". When it "exceeds about 10GB", aggressive vacuum scans "will occur more often for all tables". One report shows the failure, pgsql-bugs #12990, on PostgreSQL 9.3.5 in 2015. Its workload ran `SELECT ... FOR SHARE` on one row from 26 connections. The member files grew until the newest overtook the oldest, and the server then raised `ERROR: could not access status of transaction`. That report is from an old version, and this course found no recent post-mortem with numbers. Phase 4, section 4.5, teaches freezing for transaction IDs and for multixacts, with settings such as `vacuum_multixact_freeze_min_age`.

**The fix: one order for every transaction.** The docs, section 13.3.4, say to "acquire locks on multiple objects in a consistent order". For the transfers, both transactions first lock both rows in tenant order. From `phase03_transactions/deadlock.py:75`:

```python
# from phase03_transactions/deadlock.py:75, the SQL table. Copied
SQL = {
    "move": "UPDATE tq_budget SET credits = credits + %s WHERE tenant = %s",
    "lock_both": "SELECT tenant FROM tq_budget WHERE tenant IN ('acme', 'beta') ORDER BY tenant FOR UPDATE",
    "total": "SELECT sum(credits) FROM tq_budget",
}
```

With `--ordered`, T2's lock read waits for T1 at `acme`, the first row in the order. It holds nothing that T1 needs. T1 finishes, and T2 goes on. A wait still happens, but a cycle cannot. The docs add a second defense for orders you cannot control: retry the transactions "that abort due to deadlocks". `run_with_retry` treats 40P01 as retryable for that reason.

**One order inside a statement, too.** A single UPDATE locks its rows one by one, in the order its plan reads them. So two single statements can deadlock. Rogov, pages 228 to 230, shows it on PostgreSQL 14. One `UPDATE accounts SET amount = inc_slow(amount)` reads the table with a sequential scan, rows 1, 2 and 3. Another adds `WHERE amount > 100.00`. With sequential scans turned off, it uses a descending index on `amount`, so it reads rows 3 and 2. One of them gets `ERROR: deadlock detected`, with the report form shown above. Rogov adds that such deadlocks "do occur in high-load systems when batch row updates are performed". The fix is the same rule: lock first with `SELECT ... ORDER BY id FOR UPDATE`, then update. That fix is inferred from the rule, and Rogov does not run it.

**How lock trouble looks in production.** The lab watches sessions it started. At work, you see the same waits as rows in views and as lines in the log:

| Signal | Where | What it tells you | Version |
|---|---|---|---|
| `wait_event_type` `Lock`, with `wait_event` | `pg_stat_activity` | `transactionid`: waits for a row's writer to end. `tuple`: waits behind another waiter for the same row. `relation`: waits for a table lock | 14 docs, Table 28.11 |
| `pg_blocking_pids(pid)` | a function | the sessions that block this one, including waiters ahead of it. A prepared transaction shows as process 0 | 14 docs, 9.26 |
| `waitstart` | `pg_locks` | "Time when the server process started waiting for this lock" | new in 14, absent from the 13 docs |
| `deadlocks` | `pg_stat_database` | "Number of deadlocks detected in this database" | 14 docs, 28.2.13 |
| the log lines below | the server log | each lock wait longer than `deadlock_timeout` | `log_lock_waits = on` |

Here is the "who blocks whom" query to keep. It shows each session's blockers, its wait, and how long its transaction has been open:

```sql
-- from phase03_transactions/lockwatch.py, WHO_BLOCKS. Copied. At work, drop the pid filter
SELECT a.pid,
       pg_blocking_pids(a.pid)            AS blocked_by,
       a.wait_event_type, a.wait_event, a.state,
       round(extract(epoch FROM now() - a.xact_start)::numeric, 1) AS xact_s,
       left(a.query, 50)                  AS query
FROM pg_stat_activity a
WHERE a.pid = ANY(%s)
ORDER BY a.xact_start
```

Start from the session that blocks others and waits for nobody. It is often `idle in transaction`, with the largest `xact_s`. The docs warn that frequent calls to `pg_blocking_pids` "could have some impact on database performance". It needs "exclusive access to the lock manager's shared state for a short time". So run it when something is stuck, not every second. An empty `wait_event` does not prove that a session is not waiting. Rogov, page 244, says the view shows only the waits that the source code reports. Any other wait time is "unaccounted for".

With `log_lock_waits = on`, a wait longer than `deadlock_timeout` writes a LOG line. The formats are in `proc.c`, REL_14_24, lines 1600 to 1631:

```text
process %d still waiting for %s on %s after %ld.%03d ms
process %d acquired %s on %s after %ld.%03d ms
process %d detected deadlock while waiting for %s on %s after %ld.%03d ms
process %d avoided deadlock for %s on %s by rearranging queue order after %ld.%03d ms
```

Every line except the "acquired" line has a DETAIL in the log: `Process holding the lock: %s. Wait queue: %s.` It starts `Processes holding the lock` when several sessions hold it. For a row wait, the first `%s` of the message is the mode, such as `ShareLock`. The second names the lock, such as `transaction 901`. The "acquired" line gives the whole wait once it ends. The last line is the queue reordering of the README, a cycle broken without an abort. A fifth form, `process %d failed to acquire ...`, at line 1648, covers a rare case. No real sample from a fetched source is shown here, and E13 prints where your server writes them. Like `deadlock_timeout`, `log_lock_waits` needs a superuser to change in PostgreSQL 14.

The next section is the level that detects write skew and the phantom.

**The sentence to remember:** a row lock lasts until the transaction ends. A cycle of waits is broken after `deadlock_timeout` by cancelling, usually, the first waiter. Lock rows in one fixed order, and retry 40P01. Waiters for one row are not served in arrival order.

**The trap:** raising `deadlock_timeout` to make deadlock errors rarer. It makes the check rarer, and the cycle stays. Every victim now waits the longer time before its error, and the survivor waits as long for its lock. At the default, each deadlock already costs the victim at least 1 second of waiting and a full redo. That last point is inferred from the timer rule above.

**Try this now:** run `uv run python phase03_transactions/deadlock.py`. Compare the time between T2's "sent" line and its ERROR line with `show deadlock_timeout`. Then run it with `--ordered` and check that no ERROR line appears.

---

## 3.5 — Snapshot isolation versus serializable (what SSI adds, what it costs, and the serialization failure you must retry)

Why this matters: write skew and the phantom passed REPEATABLE READ with no error and no wait. PostgreSQL's SERIALIZABLE level stops both, and adds no lock wait to do it. It cancels one transaction with 40001 instead. So the client must run the whole transaction again. Some of those cancels happen where no anomaly would have occurred.

**Answer this first.** Run the approvers' pair at SERIALIZABLE, in the order of the opening diagram. Which session gets an error, and at which statement? Does either session wait for a lock? What does the failed transaction do when it runs again?

**The mental model.** Serializable snapshot isolation, SSI, is snapshot isolation plus one more check. It records a kind of dependency that snapshot isolation ignores:

- T1 **rw→** T2 is an rw-antidependency. T1 read some data, and T2, running at the same time, wrote a newer version of it. T1's snapshot does not show that version. So in any one-at-a-time order that matches what happened, T1 comes before T2.

Snapshot isolation already handles the other kinds of dependency. Its snapshot shows a reader what committed before it, and first-updater-wins stops two writes to one row. A cycle of dependencies means that no one-at-a-time order exists, which is an anomaly. Cahill, Röhm and Fekete, SIGMOD 2008, section 2.2, use a result of Fekete and others. Under snapshot isolation, every such cycle has two rw edges in a row, each between concurrent transactions. They call that "a dangerous structure", and the transaction in the middle a "pivot". SSI watches for the dangerous structure, which is cheaper than searching for whole cycles. When it finds one, it cancels a transaction.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The approvers at SERIALIZABLE. Expected from mvcc_model.py, not run      │
├──────────────────────────────────────────────────────────────────────────┤
│ A: count on call -> 2     reads alice and bob                            │
│ B: count on call -> 2     reads alice and bob                            │
│ A: UPDATE alice off       B read alice, A wrote it:  B rw→ A             │
│ B: UPDATE bob off         A read bob, B wrote it:    A rw→ B             │
├──────────────────────────────────────────────────────────────────────────┤
│         ┌──── rw ────►┐                                                  │
│         A             B      two rw edges in a row: A and B are pivots   │
│         └◄──── rw ────┘                                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

**How PostgreSQL records reads.** It uses predicate locks, which it calls SIREAD locks. Ports and Grittner describe the implementation in "Serializable Snapshot Isolation in PostgreSQL", VLDB 2012. Section 5.2 says: "The SSI lock manager stores only SIREAD locks. It does not support any other lock modes, and hence cannot block." The PostgreSQL 14 docs, section 13.2.3, say the same. These locks "do not cause any blocking and therefore can not play any part in causing a deadlock". They appear in `pg_locks` "with a mode of SIReadLock". Four more rules decide how many false alarms you get:

1. **Granularity.** A lock covers a tuple, a page or a whole table. Ports and Grittner, section 5.2, say that B-tree index reads are locked at page level.
2. **Sequential scans.** The docs say: "A sequential scan will always necessitate a relation-level predicate lock." Every later write to that table then conflicts with the scan. PostgreSQL 14 docs, section 13.2.3.
3. **Promotion.** Too many fine locks are combined into coarse ones. `max_pred_locks_per_page`, default 2, is the number of rows on one page before the lock becomes a page lock. The setting `max_pred_locks_per_relation` has the default −2. It means `max_pred_locks_per_transaction` divided by 2, so 64 / 2 = 32 pages or tuples of one table. Past that, the lock covers the table. The docs warn that combining locks can raise "the rate of serialization failures". Verified from the PostgreSQL 14 docs, sections 20.12 and 13.2.3.
4. **Lifetime.** The same section says that SIREAD locks "often need to be kept past transaction commit, until overlapping read write transactions complete".

When the write comes before the read, PostgreSQL needs no SIREAD lock. The reader finds a newer version whose `xmin` its snapshot hides, and records the edge from that. This is from Ports and Grittner, section 5.2.

Here are the answers to the questions. Neither session waits, because both UPDATEs touch different rows, and SIREAD locks cannot block. One session gets 40001, expected at B's COMMIT. When A commits, B is a pivot whose out-edge points to a committed transaction, so B cannot commit. Hermitage saw the error at the second COMMIT for this shape. When B runs again, its new snapshot shows Alice off call, so it counts 1 and stays on call.

**The error.** The message is verified at `predicate.c` line 4125, tag REL_14_24, with its hint at line 4127. The lab is expected to print it in this form. Not run by the author yet:

```
ERROR 40001: could not serialize access due to read/write dependencies among transactions
      DETAIL: Reason code: Canceled on identification as a pivot, during commit attempt.
      HINT: The transaction might succeed if retried.
```

The DETAIL line varies with the case. `predicate.c` at REL_14_24 has ten reason-code lines, such as "during write" at line 4821 and "during commit attempt" at line 4880. Rogov, page 59, printed exactly this DETAIL on PostgreSQL 14, at the second COMMIT. His case has the same shape: two sums, then two UPDATEs of different rows. So the line above is expected with good reason, but the lab itself was not run. The SQLSTATE, on the other hand, never varies. The PostgreSQL 14 docs, section 13.2.3, say serialization failures "always return with an SQLSTATE value of '40001'".

**What SERIALIZABLE costs, measured by others.** Ports and Grittner measured their code in PostgreSQL 9.1, on their 2012 hardware. The numbers describe that version and those machines, and this course did not measure PostgreSQL 14:

| Workload | Result | Conditions | Source |
|---|---|---|---|
| SIBENCH, a table of key-value pairs, half updates and half full scans | SSI used 10% to 20% more CPU than snapshot isolation | in memory, tmpfs, Core 2 Quad Q9550, 8 GB | section 8.1, Figure 4 |
| DBT-2++, a TPC-C-like workload with a "credit check" transaction, 25 warehouses | SSI 5% slower than snapshot isolation | in memory, 4 threads | section 8.2, Figure 5a |
| DBT-2++, 150 warehouses, 19 GB | throughput "indistinguishable from that of SI", serialization failures under 0.25% | disk-bound, 36 threads, 16-core Xeon E7310 | section 8.2, Figure 5b |
| deferrable read-only transactions during that run | median wait for a safe snapshot 1.98 s, 90% within 6 s, all within 20 s | 1,200 tries | section 8.4 |
| RUBiS, an auction-site benchmark, 85% read-only, 6 GB | SI 435 requests per second, SSI 422, S2PL 208. Failures 0.004%, 0.03% and 0.76% | Core 2 Quad Q9550, 8 GB, one 7,200 RPM disk | section 8.3, Figure 6 |

S2PL is strict two-phase locking, the classic way to serializable. Every lock is held until commit, so readers and writers block each other. On RUBiS, SSI kept 422 / 435 = 97% of SI's throughput, and S2PL kept 208 / 435 = 48%. So in their tests, SSI cost little next to locking. Its cost came as retries, not as waits. A deferrable transaction is one more option. `BEGIN ISOLATION LEVEL SERIALIZABLE, READ ONLY, DEFERRABLE` may wait for a safe snapshot at the start. Ports and Grittner, section 4.2, say that after the wait it "cannot be aborted, and does not need to take SIREAD locks". The PostgreSQL 14 docs for SET TRANSACTION say the mode "is well suited for long-running reports or backups". The wait in the table above is its price. It also answers the read-only anomaly of section 3.3. Rogov, page 59, reports that the anomaly's three transactions at SERIALIZABLE end in the same 40001. With `READ ONLY DEFERRABLE`, his third transaction instead blocked until T1 committed, and then read 910 and 0, pages 59 and 60. That is a state of the order T1, T2.

**The guarantee depends on the implementation.** Jepsen's analysis "PostgreSQL 12.3", by Kyle Kingsbury, was published on 2020-06-12. Under SERIALIZABLE, a two-minute test found "six cases of G2-item". Each one "involved at least one read-write conflict for a freshly inserted row". The fix is commit `e620a38c`, "Avoid update conflict out serialization anomalies.", dated 2020-06-11, released in PostgreSQL 12.4 on 2020-08-13. Verified from the report, section 3.2, and the 12.4 release notes. Jepsen notes that Hermitage did not catch this bug. The commit message says "Backpatch: All supported versions". Every PostgreSQL 14 release came after it, so your 14.24 should include the fix. That is inferred from the dates, and was not checked in the 14 source.

**Only serializable transactions are protected.** The docs, section 13.2.3, give the guarantee for "any set of successfully committed concurrent Serializable transactions". A transaction at READ COMMITTED takes no SIREAD locks, so its reads form no edges. If Bob's screen ran at READ COMMITTED and Alice's at SERIALIZABLE, the pair could still break the rule. Rogov states it for PostgreSQL 14, page 60: mixed with other levels, Serializable "behaves as Repeatable Read without any notice". Page 236 gives the reason: a transaction at another level "will not set (or check) predicate locks". So set `default_transaction_isolation` for the whole application, not per screen.

**Running SERIALIZABLE in production.** The PostgreSQL 14 docs, section 13.2.3, end with a list of advice "For optimal performance when relying on Serializable transactions". Here it is, with the reason for each item. The reasons come from the same section, except where the row says inferred:

| Advice | Why |
|---|---|
| "Declare transactions as READ ONLY when possible." | read-only transactions "will often be able to establish" at startup that they need no predicate locks |
| control the number of active connections, with a pool if needed | fewer concurrent transactions form fewer rw edges. Inferred |
| "Don't put more into a single transaction than needed for integrity purposes." | each read adds SIREAD locks, which can outlive the commit. Inferred from the lifetime rule above |
| do not leave connections "idle in transaction" longer than needed | the docs name `idle_in_transaction_session_timeout` for it |
| remove `FOR UPDATE`, `FOR SHARE` and explicit locks that SSI made unneeded | they add waits that SSI does not need. Inferred |
| raise the `max_pred_locks_*` settings when page locks get combined into a table lock | combining can cause "an increase in the rate of serialization failures" |
| encourage index scans, by lowering `random_page_cost` or raising `cpu_tuple_cost` | "A sequential scan will always necessitate a relation-level predicate lock" |

Two more errors belong to this level. When the predicate lock table is full, PostgreSQL 14 raises `ERROR: out of shared memory`, with `HINT: You might need to increase max_pred_locks_per_transaction.`. That is at `predicate.c` lines 2487 to 2489, REL_14_24. And a replica refuses the level. The 14 docs, section 27.4, say serializable "is not yet available in hot standby", and setting it "will generate an error".

### The retry, done right

A serialization failure means: run the transaction again from the start. The PostgreSQL 14 docs, section 13.2.2, say to "retry the whole transaction from the beginning". PostgreSQL 15 added a docs section on this, "Serialization Failure Handling". Section 13.5 of the current docs, version 18, says:

- the error "will always have the SQLSTATE code 40001 (serialization_failure)"
- "It may also be advisable to retry deadlock failures. These have the SQLSTATE code 40P01 (deadlock_detected)."
- in some cases, a retry of `23505`, `unique_violation`, or `23P01`, `exclusion_violation`, also makes sense
- "PostgreSQL does not offer an automatic retry facility, since it cannot do so with any guarantee of correctness."

The client must do it, and the obvious way is wrong. After an error, PostgreSQL accepts only the statements that end the transaction or roll back to a savepoint. `IsTransactionExitStmt` in `postgres.c`, lines 2752 to 2765, REL_14_24, lists them: COMMIT, PREPARE TRANSACTION, ROLLBACK and ROLLBACK TO SAVEPOINT. Every other statement gets "current transaction is aborted, commands ignored until end of transaction block", SQLSTATE 25P02, at line 1046. A COMMIT there does not commit. Rogov, pages 78 and 79, prints the server's reply to it on PostgreSQL 14: `ROLLBACK`. So a retry of the failed statement can never succeed. An earlier version of this phase said that only ROLLBACK is accepted, and the source above corrected it. The lab's helper keeps the wrong way behind a flag, so the self-test can prove that it fails. From `shared/pglab.py:411`, the loop of `run_with_retry()`:

```python
# from shared/pglab.py:411, the loop of run_with_retry(). Copied
    while True:
        attempt += 1
        try:
            if not (retry_statement_only and began):
                conn.execute(begin_sql(level))       # RIGHT: a new transaction, a new snapshot
                began = True
            value = body(conn, attempt)
            conn.execute("COMMIT")                   # SERIALIZABLE can raise 40001 here
            return RetryResult(value, attempt, errors)
        except Exception as exc:
            code = sqlstate_of(exc)
            errors.append(code or type(exc).__name__)
            if not retry_statement_only:
                _safe_rollback(conn)
            if code not in RETRYABLE or attempt >= policy.max_attempts:
                if retry_statement_only:
                    _safe_rollback(conn)
                raise
            wait = delays[attempt - 1]
            if on_retry:
                on_retry(attempt, exc, wait)
            sleep(wait)
```

With `retry_statement_only=True`, the WRONG way, the second attempt sends the body into the failed transaction. The self-test of `pglab.py` expects 25P02 there, from a fake connection that follows the server's rule. With the default, the RIGHT way, every attempt starts with BEGIN. The new snapshot then shows the change that caused the conflict. `lost_update.py --wrong-retry` shows the same 25P02 against the real server. Not run by the author yet.

**What a savepoint can rescue, and what it cannot.** `ROLLBACK TO SAVEPOINT` returns the transaction to a working state. Drivers and ORMs use it to go on after one failed statement. That fits an error such as 23505 on one insert, when the rest of the transaction is still valid. It does not fit 40001. At REPEATABLE READ and SERIALIZABLE, the transaction keeps the snapshot of its first statement. So a retry from a savepoint reads the same old data and meets the same conflict. That is inferred from the snapshot rule of section 3.2, and was not run. Each savepoint is also a subtransaction, with the cost section 3.2 showed. For "insert, and if the row exists, use it", `INSERT ... ON CONFLICT` needs no savepoint, as section 3.6 shows. E16 shows the aborted state, the COMMIT that rolls back, and the savepoint, in psql.

Four rules make a retry safe:

1. **Retry only 40001 and 40P01.** Other errors, such as a CHECK violation, fail again the same way.
2. **Put COMMIT inside the loop.** At SERIALIZABLE, COMMIT itself can fail with 40001, as in the approvers' case.
3. **Keep the body free of side effects.** An email or an HTTP call inside it happens once per attempt. The docs, section 13.2.3, add a rule for reads. Data read in a serializable transaction should not be "considered valid until the transaction which read it has successfully committed".
4. **Cap the attempts and add jitter.** `RetryPolicy` in `pglab.py` allows 5 attempts by default. It waits a random time before each retry, up to 10, 20, 40 and 80 ms. The cap on any wait is 500 ms. `contention.py` raises the attempt cap to 50. Those values are this course's choice, not a measured optimum. The random wait spreads transactions that failed together, so they do not collide again at the same moment.

**The failure: SERIALIZABLE without the loop.** A team switches `default_transaction_isolation` to serializable to stop write skew. The anomalies of section 3.3 stop. Users now see 40001 errors, which the application reports as server errors, because nothing retries them. The rate depends on the workload: under 0.25% of transactions in one of the tests above, and 0.03% in another. Each failed transaction is a failed request until the loop exists.

The next section compares this approach, checking at the end, with taking locks at the start.

**The sentence to remember:** PostgreSQL's SERIALIZABLE is snapshot isolation plus a check for two rw-antidependencies in a row. It adds no new lock waits. It cancels one transaction with 40001, and the client runs the whole transaction again.

**The trap:** retrying only the statement that failed. The transaction is already aborted, so every retry gets 25P02, and the request fails after the last attempt.

**Try this now:** run `uv run python phase03_transactions/write_skew.py --level serializable --retry --show-locks`. Find the SIReadLock rows printed after the two counts. Then find the 40001 line, the statement it came from, and the retry's count.

---

## 3.6 — Optimistic versus pessimistic (SELECT FOR UPDATE, version columns, and choosing by contention)

Why this matters: every fix so far is one of two kinds. Some take a lock before the read, so that other transactions wait. Others read freely and check at the write, so that the loser starts again. Which one costs less depends on how often transactions collide, and on how long each one holds what it touched.

**Answer this first.** Ten workers each increment one counter row once, in their own transactions. All of them start at the same moment. Suppose each round of attempts lets exactly one worker commit.

1. With an optimistic check at the write, how many attempts do the ten workers make in total? How many does the unluckiest worker make?
2. With `SELECT ... FOR UPDATE` before the read, how many attempts are there? What does the last worker pay instead?

**The mental model.** Two families of concurrency control:

- **Pessimistic** control takes a lock before it reads. `SELECT ... FOR UPDATE` locks the row, and every other writer of that row waits until the transaction ends. In this case no work is thrown away. The cost is waiting, and the risk is the deadlock of section 3.4.
- **Optimistic** control reads without a lock and checks at the write that nothing changed. If something did, the transaction starts again. A version column does this in the application. The 40001 of REPEATABLE READ and SERIALIZABLE is the same idea, done by the server. Nobody waits at the read in this case. The cost is the work that is redone.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Three workers increment one row. Steps in order, an example              │
├──────────────────────────────────────────────────────────────────────────┤
│ PESSIMISTIC: FOR UPDATE          │ OPTIMISTIC: version check             │
│ W1 lock, read 0, write 1, commit │ W1, W2, W3 read 0, version 0          │
│ W2 waits ... lock, read 1,       │ W1 writes 1 WHERE version = 0: ok     │
│    write 2, commit               │ W2, W3: 0 rows. Start again           │
│ W3 waits ......... lock, read 2, │ W2, W3 read 1, version 1              │
│    write 3, commit               │ W2 writes 2: ok. W3: 0 rows           │
│                                  │ W3 reads 2, writes 3: ok              │
├──────────────────────────────────────────────────────────────────────────┤
│ 3 attempts, waits add up         │ 3 + 2 + 1 = 6 attempts, no waits      │
│ W2 is next: it holds the tuple   │                                       │
│ lock. A 4th waiter would race W3 │                                       │
│ after W2, section 3.4            │                                       │
└──────────────────────────────────────────────────────────────────────────┘
```

**The arithmetic.** Two results decide the choice, and `contention.py --self-test` checks both:

- Let each optimistic attempt conflict with probability p. The number of attempts until a success then has a mean of 1 / (1 − p). At p = 0.1 that is 1.11 attempts. At p = 0.5 it is 2, and at p = 0.9 it is 10.
- Let n workers start together on one row, with one commit per round. The attempts then add up to n + (n − 1) + ... + 1 = n × (n + 1) / 2.

So for the question above, optimistic control makes 10 × 11 / 2 = 55 attempts for 10 commits. The unluckiest worker makes 10 of them. Pessimistic control makes only 10 attempts. The last worker to get the row instead waits for the nine before it, each for its whole transaction. Which worker is last is not decided by arrival, as section 3.4 showed. Neither number was measured in this course. `contention.py` measures both on your laptop, and its expected shape is in E9.

**Pessimistic, in PostgreSQL.** `SELECT ... FOR UPDATE` has two options that change what happens when the row is locked. Verified from the PostgreSQL 14 docs for SELECT, "The Locking Clause":

- `NOWAIT`: "the statement reports an error, rather than waiting". The error is SQLSTATE 55P03, `lock_not_available`, with the message `could not obtain lock on row in relation "%s"`. Verified from `errcodes.txt` line 419 and `heapam.c` line 4941, tag REL_14_24.
- `SKIP LOCKED`: "any selected rows that cannot be immediately locked are skipped". The docs warn that this "provides an inconsistent view of the data". They add that it "can be used to avoid lock contention with multiple consumers accessing a queue-like table".

A task queue is that queue-like table. Section 3.7 claims tasks with `SKIP LOCKED`, so two workers never wait for the same row. At READ COMMITTED, a `FOR UPDATE` that waited returns the row as the other transaction left it. The docs say it will "lock and return the updated row". At REPEATABLE READ it raises 40001 instead, as section 3.4 showed.

**Advisory locks: a lock on a name.** Sometimes the thing to lock is not a row. An example is "the scheduler for tenant acme". PostgreSQL's advisory locks are "locks that have application-defined meanings". You lock a number, often a hash of a name, as Rogov does on page 234. Verified from the PostgreSQL 14 docs, sections 13.3.5 and 9.27.10:

```sql
SELECT pg_advisory_xact_lock(hashtext('scheduler:acme'));  -- waits if needed, held until the transaction ends
SELECT pg_try_advisory_lock(hashtext('scheduler:acme'));   -- session level: true or false at once, never waits
```

The docs give three rules. Session-level locks "do not honor transaction semantics", so a lock taken in a transaction that rolls back is still held. All advisory locks use the shared lock table sized by `max_locks_per_transaction` and `max_connections`. So leaked locks can stop the server from granting any lock. And `pg_advisory_lock(id)` in a query with `LIMIT` is marked "danger!", because the LIMIT may apply after the function ran. Prefer the transaction-level form, which ends with the transaction. A session-level lock under a pooler in transaction mode can stay on a server connection that another client gets next. That last point is inferred, because this course did not read the PgBouncer docs.

**Optimistic, in the application.** A version column changes on every write. The writer adds the version it read to the WHERE clause, and checks the row count. From `phase03_transactions/contention.py:116`:

```python
# from phase03_transactions/contention.py:116, make_body(), the "version" strategy. Copied
        elif strategy == "version":
            n, v = conn.execute(SQL["read_version"], (row,)).fetchone()
            work()
            # 0 rows: another worker changed the row after our read. Ignoring
            # the count would report success for a write that never happened.
            if conn.execute(SQL["cas"], (n + 1, row, v)).rowcount == 0:
                raise _Conflict()
```

The entry `SQL["cas"]` holds `UPDATE tq_counters SET n = %s, version = version + 1 WHERE id = %s AND version = %s`. At READ COMMITTED, the second writer waits for the first one's row lock. It then re-checks `version = %s` on the new row, which no longer matches, so it updates 0 rows. `_Conflict` carries SQLSTATE 40001, so `run_with_retry` starts the whole transaction again.

**A third way: one statement.** Sometimes the read, the check and the write fit in one SQL statement. The server then does all three under the row lock. The atomic spend of section 3.3 is this kind: `SET credits = credits - 80 WHERE ... AND credits >= 80`. It needs no retry at READ COMMITTED, and it holds the lock only from that statement to COMMIT. Its limit is that the whole decision must be expressible in SQL.

**Fixing the phantom: lock a row that always exists.** In section 3.3, `FOR UPDATE` could not lock tasks that did not exist yet. So give the rule a row of its own. `phantom.py --fix parent-row` keeps a counter on the tenant's row in `tq_tenants`, and reserves a slot with one conditional UPDATE. From `phase03_transactions/phantom.py:98`:

```sql
-- from phase03_transactions/phantom.py:98, SQL["reserve_slot"]. Copied, joined onto two lines
UPDATE tq_tenants SET running = running + 1
WHERE tenant = 'acme' AND running < max_running
```

The second worker waits for the first one's row lock. At READ COMMITTED it then re-checks `running < max_running` against 1 < 1 and updates 0 rows. At REPEATABLE READ it gets 40001. Either way, at most one task runs. The same move fixes the approvers. Put the count of approvers on call into one row, and change it with a conditional UPDATE. The trade-off is that the counter is now a copy of a fact that the task rows also hold. Every transaction that starts or ends a task must change both, or they drift apart.

**A fourth way: let a constraint hold the rule.** For a rule of the form "at most one", reach first for a unique index. It holds at every isolation level, and at READ COMMITTED it needs no retry loop. It also holds for code written later by someone who never read this phase. Rogov's first fix for check-then-act, page 47, is the same idea: "Replace procedural code with declarative one".

| Rule | Constraint | What the second writer gets |
|---|---|---|
| at most 1 running task per tenant, pair 3 | `CREATE UNIQUE INDEX ON tq_tasks (tenant) WHERE state = 'running'` | waits for the first writer, then 23505 `unique_violation` |
| one decision per task, the approval of section 3.7 | `CREATE UNIQUE INDEX ON tq_approvals (task_id)` | waits for the first writer, then 23505 |
| insert a row, or update it if it exists | a unique key, and `INSERT ... ON CONFLICT (key) DO UPDATE` | at READ COMMITTED, no error: its UPDATE runs on the row the first writer inserted. At REPEATABLE READ and SERIALIZABLE, 40001 when its snapshot cannot see that row |

The first row is a partial unique index. The PostgreSQL 14 docs, section 11.8, Example 11.3, use one so that each subject and target has only one successful entry. Its definition is `CREATE UNIQUE INDEX tests_success_constraint ON tests (subject, target) WHERE success;`. Such an index "enforces uniqueness among the rows that satisfy the index predicate".

Here is why the second writer waits. Its B-tree insert finds the first writer's entry while that transaction is still open. `_bt_doinsert` then waits for it with `XactLockTableWait`, at `nbtinsert.c` line 224, REL_14_24. If the first writer commits, the check finds a live duplicate. It raises `duplicate key value violates unique constraint "%s"`, line 665, with the DETAIL `Key %s already exists.`. If the first writer rolls back, the insert goes on. So no second claim can succeed while the first may still commit. That is verified from the source. At SERIALIZABLE, the code checks for an SSI conflict first, line 636, so 40001 may come instead of 23505. `phantom.py --fix unique-index` shows the first row, not run by the author yet.

For upserts, the INSERT page of the PostgreSQL 14 docs says that "ON CONFLICT DO UPDATE guarantees an atomic INSERT or UPDATE outcome". Unless an unrelated error occurs, one of the two outcomes holds "even under high concurrency". It needs no savepoint, so it pays no subtransaction. At the two higher levels, `ExecCheckTupleVisible` in `nodeModifyTable.c`, line 232, REL_14_24, raises `could not serialize access due to concurrent update` instead. It does so when the conflicting row was committed after the transaction's snapshot. So an upsert at those levels still needs the retry loop of section 3.5.

The limits matter as much as the fix:

- A unique index holds a limit of 1 only. A limit of 3 running tasks per tenant still needs the counter row above.
- A rule of "at least one", such as the approvers on call, is not a uniqueness rule. It still needs SERIALIZABLE, or a counter row that a conditional UPDATE keeps above 0.
- A unique violation is an error. The code must catch 23505 and treat it as "another writer won", not as a server fault. The current docs, section 13.5, list 23505 among the errors that a retry can sometimes fix.

**How to choose.** Each row gives a situation, the choice it favors, and the measurement that proves it wrong:

| Situation | Prefer | Why | Measure to check it |
|---|---|---|---|
| the decision fits in one UPDATE whose condition reads only that row | one conditional statement | no retry and no explicit lock | rows updated, 0 or 1 |
| the rule is "at most one" | a unique index, partial if needed | holds at every level, and for later code | count of 23505 |
| conflicts are rare, p under about 0.1 | optimistic | about 1.11 attempts at p = 0.1, and nobody waits | retries per commit |
| many writers on few rows | pessimistic | 1 / (1 − p) grows fast: 10 attempts at p = 0.9 | lock waits, p99 of the transaction |
| workers take items from a queue | `FOR UPDATE SKIP LOCKED` | each worker takes a different row | claims per second, rows skipped |
| the rule spans many rows or a condition | SERIALIZABLE and a retry, or a parent row | row locks cannot cover rows that are not there | 40001 rate |
| the thing to serialize is not a row | `pg_advisory_xact_lock` | one holder per key until the transaction ends | lock waits on `advisory` |
| the work between read and write is slow, such as a network call | neither inside one transaction | split it into two short transactions, see below | time a lock is held |

The thresholds in the table are this course's example from the formula, not measured limits.

**The failure: a lock held across a slow call.** A worker locks a task with `SELECT ... FOR UPDATE`. Then it calls a language model that takes 20 seconds, as an example, and writes the result. Every other transaction that touches that row waits the full 20 seconds. The open transaction also keeps its snapshot for that long, which section 3.2 warned about. The fix is two short transactions with a state change between them. The first claims the task and commits, so the row now says `running` with an owner. The call happens outside any transaction. The second records the result only if the claim still holds: `UPDATE ... WHERE id = %s AND state = 'running' AND owner = %s`. The task queue of section 3.7 is built this way. The design leaves one hole, a worker that dies between the two transactions. Section 3.7 closes it with a lease.

The last section applies all of this to the three transactions of the task queue.

**The sentence to remember:** pessimistic control makes the later transaction wait, and optimistic control makes it redo its work. With conflict probability p, an optimistic transaction needs 1 / (1 − p) attempts on average. So choose by contention and by the cost of the work.

**The trap:** a version-checked UPDATE whose row count nobody checks. It matches 0 rows, raises no error, and the code reports success for a write that never happened.

**Try this now:** first predict the retries for `version` at one hot row, from the formula above. Then run `uv run python phase03_transactions/contention.py --workers 8 --increments 200 --hot-rows 1,64 --strategies naive,for-update,version`. Read the `lost` and `retries` columns for each hot-row count.

---

## 3.7 — Isolation in the task queue (the task claim, the approval and the outbox, and which anomaly each suffers at READ COMMITTED)

Why this matters: the course's task-queue schema mirrors a typical agent task system. Workers claim tasks, humans approve some of them, and every change is announced to other services. This section audits its three central transactions. Each one is correct when one session runs it. The audit asks what each one suffers when two sessions run it at READ COMMITTED.

**Answer this first.** Here are the three transactions as a first version would write them. For each one, name the anomaly at READ COMMITTED, or say that there is none:

1. **Claim.** It runs `SELECT id FROM tq_tasks WHERE state = 'queued' ORDER BY id LIMIT 1`, then `UPDATE tq_tasks SET state = 'running', owner = %s WHERE id = %s`.
2. **Approval.** It counts the task's rows in `tq_approvals`. If the count is 0, it inserts an `approve` or a `reject`.
3. **Outbox.** Complete a task and insert its event into `tq_outbox` in the same transaction. A relay polls `WHERE id > last_id`, publishes, and moves `last_id`.

**The mental model.** Audit each transaction by its invariant. Write down the rule it must keep, and find the reads that its decision depends on. Then ask which other transaction can change those reads before the commit. Then fix it with the smallest change from this phase, and keep a test that fails without the fix.

One check comes before all of these: the scope. Do the read and the write run in one transaction at all? An ORM in autocommit mode breaks the rule at every level. So does a read in one request and a write in the next. Warszawski and Bailis, "ACIDRain", SIGMOD 2017, audited 12 eCommerce applications. They found 22 attacks, which together span over 2M websites. "All 22 vulnerabilities manifest under the default isolation guarantees" of popular databases. And 17 of them, due to incorrect transaction usage, "manifest even under the strongest transactional guarantees". So review the scope first, then the level. The paper opens with the Flexcoin Bitcoin exchange. After a concurrency attack on 2014-03-02, all its stored Bitcoins were stolen, and it shut down.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ The task queue, the course's own schema. Arrows are writes               │
├──────────────────────────────────────────────────────────────────────────┤
│  worker A ──┐                     ┌──► tq_tasks      state, owner        │
│  worker B ──┼── claim, complete ──┤                                      │
│  approver ──┴── decide ───────────┼──► tq_approvals  a row per decision  │
│                                   └──► tq_outbox     a row per event     │
│                                             │                            │
│                   relay: poll, publish, mark sent                        │
│                                             ▼                            │
│                                   broker ──► consumer, drops duplicates  │
├──────────────────────────────────────────────────────────────────────────┤
│ claim and decide change tq_tasks and tq_outbox in ONE transaction        │
└──────────────────────────────────────────────────────────────────────────┘
```

### The claim

Both workers read task 1 as the first queued task. Worker A updates it and commits. Worker B's UPDATE waited for A's row lock, and then re-checks its WHERE clause, `id = 1`, which still matches. So B overwrites the owner, and both workers run the task. This is the lost update of section 3.3, on the `owner` column. The expected output of `taskqueue.py --check claim --variant naive`, not run by the author yet, is:

```
FAIL claim: 2 worker(s) believe they claimed task 1. The row says owner B, attempts 2. 2 task.claimed event(s)
```

The fix is one statement that finds and claims the task under its row lock. It skips rows that another worker holds. From `phase03_transactions/taskqueue.py:134`:

```python
# from phase03_transactions/taskqueue.py:134, SQL["claim_fixed"]. Copied
    "claim_fixed": ("UPDATE tq_tasks SET state = 'running', owner = %s, attempts = attempts + 1 "
                    "WHERE id = (SELECT id FROM tq_tasks WHERE state = 'queued' "
                    "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING id"),
```

Worker B's subquery skips task 1, which A holds, and finds no other queued task. So B is expected to update 0 rows at once, with no wait. The check sets `lock_timeout = '2s'` for B, so a query that waited by mistake would fail instead of hanging. Two other fixes also work here. `AND state = 'queued'` in the naive UPDATE makes B wait and then update 0 rows. REPEATABLE READ with a retry makes B fail with 40001 and find no queued task on its second attempt. `taskqueue.py --self-test` checks both of these in the model, `mvcc_model.py`. It expects 2 claims for the naive form at READ COMMITTED, and 1 for each fix.

### After the claim: a lease, and the cost of the queue table

The claim sets `state = 'running'` and commits, as section 3.6 advised. Now suppose the worker dies after that commit. Nothing ever moves the task back, so no worker takes it again. `taskqueue.py --check lease --variant naive` is expected to print `FAIL lease: task 1 is running, owner A. Its worker is dead, and nothing will ever run it`. Not run by the author yet. There are three designs, and each one pays in a different place. The second uses a lease, a claim that ends at a stated time unless its worker renews it:

| Design | When the worker dies | What it costs |
|---|---|---|
| hold the row lock of `FOR UPDATE SKIP LOCKED` for the whole job | the transaction ends with the connection, so the task is free again | one open transaction per running job. It holds a connection, and it holds back the cleanup horizon of section 3.2 |
| claim with a lease, `lease_until`, and run a reaper that requeues expired leases | another worker runs the task once the lease has expired | at least once: a slow worker and its replacement can both run it. The work must be idempotent, and attempts need a cap |
| a session-level advisory lock per task | the lock goes when the session ends | the claim lives on one connection, and session locks ignore COMMIT and ROLLBACK, section 3.6 |

The lab uses the lease. Its claim, `SQL["claim_lease"]`, is `claim_fixed` with `lease_until = now() + %s * interval '1 millisecond'` added. The reaper is one statement, from `phase03_transactions/taskqueue.py:144`:

```sql
-- from phase03_transactions/taskqueue.py:144, SQL["reap"]. Copied, joined onto two lines
UPDATE tq_tasks SET state = 'queued', owner = NULL, lease_until = NULL
WHERE state = 'running' AND lease_until < now() AND attempts < %s RETURNING id
```

Two details make it safe. The completion names its owner, `... AND owner = %s`. So a worker that was only slow may wake after its task went to B. Its completion then updates 0 rows, and it must drop its result. The reaper, the completion and a new claim all change the same row. So the row lock orders them, and each re-checks its condition on that row, by the rule of section 3.3. The check is safe only while an owner name is never used for two claims of one task. Suppose slow worker A loses the task to the reaper and then claims it again. Its old completion would then pass the owner check. Checking `attempts` as well makes each claim unique. That last point is inferred from the SQL, and the lab does not test it. And `attempts < %s` stops a task that kills every worker from running for ever. A long job also needs a heartbeat, an UPDATE that moves `lease_until` forward with the same owner check. The heartbeat is a design note, not part of the lab. The owner check guards writes to this database only. A slow worker's calls to other systems still happen. A fencing token that those systems check is the subject of course 5, Phase 4, section 4.6. `--check lease --variant fixed` is expected to print `PASS lease: task 1 is done, owner B`. It also shows the late completion as 0 rows. Not run by the author yet.

**A long transaction anywhere slows the queue.** A busy queue table makes dead row versions fast. Each claim replaces a queued version, and each finished job leaves one more. VACUUM can remove a dead version only once no open snapshot might need it, which is the cleanup horizon. So one long transaction anywhere in the database lets dead versions pile up in the queue table. Each claim's index scan then steps over more dead entries before it finds a live queued task.

Brandur Leach measured this in "Postgres Job Queues & Failure By MVCC", 2015-05-18. His conditions were Heroku Postgres, the Que library, which claimed jobs with advisory locks, and about 50 jobs a second. With one long-lived transaction open, the time to lock a job grew from under 0.01 s. It reached 15 times that, 0.1 s and more. One hour in, 60k jobs were queued. By the end of his test, the jobs table approached 100,000 dead rows. His VACUUM VERBOSE printed `DETAIL: 247311 dead row versions cannot be removed yet.`. In PostgreSQL 14 that line ends with `, oldest xmin: %u`, at `vacuumlazy.c` line 1656, REL_14_24. The xmin names the snapshot to look for.

His queue did not use SKIP LOCKED. That the same decay hits a SKIP LOCKED queue is inferred from the mechanism. `queue_horizon.py`, E15, is the check: it holds one REPEATABLE READ snapshot and runs the claim loop. Three defenses follow:

1. Index the claim's filter. The lab schema now has `CREATE INDEX tq_tasks_queued ON tq_tasks (id) WHERE state = 'queued'`. So a claim does not scan the whole table. The scan still steps over dead entries, so the index alone is not enough.
2. Watch the horizon. `age(backend_xmin)` in `pg_stat_activity` names the session that holds it, and Phase 4, section 4.5, alerts on it.
3. End idle transactions with `idle_in_transaction_session_timeout`, and long ones with `transaction_timeout` in PostgreSQL 17 and later, set per role as section 3.4 advised.

Rogov adds a caution about SKIP LOCKED itself, page 224. It suits batches and "parallel processing of event queues". "However, avoid inventing other use cases for this command".

### The approval

The approval reads a set, the decisions for task 2, and finds it empty. Alice inserts `approve` and Bob inserts `reject`. Neither insert touches a row that the other wrote, so this is the phantom form of write skew. It passes READ COMMITTED and REPEATABLE READ. The task now has two decisions, and the outbox holds both `task.approved` and `task.rejected`. A consumer may act on both. The expected line, not run, is `FAIL approval: task 2 has decision(s) ['approve', 'reject'], state awaiting_approval`.

The fix turns the decision into a write on one row, the task's own:

```sql
-- from phase03_transactions/taskqueue.py:148, SQL["decide_task"], run first. Copied
UPDATE tq_tasks SET state = %s WHERE id = %s AND state = 'awaiting_approval'
```

Only when it updates 1 row does the transaction insert the decision and the event. Bob's UPDATE waits for Alice's row lock. At READ COMMITTED it then re-checks `state = 'awaiting_approval'`, which is now false, and updates 0 rows. At REPEATABLE READ it gets 40001, and its retry updates 0 rows. SERIALIZABLE with a retry also fixes the naive version: `taskqueue.py --check approval --variant naive --level serializable --retry` is expected to pass. A unique index on `tq_approvals (task_id)` also stops the second insert, with no change to the naive code. Bob's INSERT waits for Alice's commit, then fails with 23505, as section 3.6 traced in `nbtinsert.c`. `taskqueue.py --check approval --variant naive --unique-decision` is expected to pass. Not run by the author yet. In production, keep both. The state change on the task row carries the logic, and the index is the rule that later code cannot break.

### The outbox: the write and the relay

**The write.** The transactional outbox is a pattern that Chris Richardson describes on microservices.io. The service should "first store the message in the database as part of the transaction that updates the business entities". A separate process, the relay, then sends the stored messages to the broker. The benefit, in his words: "Messages are guaranteed to be sent if and only if the database transaction commits". The other way, a dual write, commits the change and then publishes from the application. A crash between the two loses the event. `taskqueue.py --check dual-write` stops the worker right after COMMIT. The naive version then has a done task and no event. The outbox version has its event row, which the relay publishes.

Now the audit of the write. Its invariant is that the event commits if and only if the change does. That is a promise of atomicity, which section 3.1 described, so isolation does not enter it. The INSERT reads nothing that a decision depends on, so it adds no anomaly at READ COMMITTED. The change itself is one conditional UPDATE, `... WHERE id = %s AND state = 'running' AND owner = %s`. It re-checks its condition after any wait, as section 3.3 showed.

**The relay.** The naive relay keeps the highest id it has published. An id comes from a sequence when the row is inserted. The PostgreSQL 14 docs, section 13.2, say that sequence changes "are immediately visible to all other transactions and are not rolled back". The page for CREATE SEQUENCE says that "nextval and setval calls are never rolled back". A row becomes visible only at its commit. So ids are in insert order, while rows appear in commit order:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ outbox check, naive relay. Expected, not run by the author yet           │
├──────────────────────────────────────────────────────────────────────────┤
│ W1  completes task 3, INSERT event        gets id 1, not committed       │
│ W2  completes task 4, INSERT event        gets id 2                      │
│ W2  COMMIT                                                               │
│ R   pass 1: WHERE id > 0                  sees id 2 only. last_id = 2    │
│ W1  COMMIT                                id 1 is now visible            │
│ R   pass 2: WHERE id > 2                  sees nothing                   │
├──────────────────────────────────────────────────────────────────────────┤
│ event 1 committed and is never published. FAIL                           │
└──────────────────────────────────────────────────────────────────────────┘
```

This is the one failure in the audit that no isolation level fixes. `--relay-level serializable` is expected to give the same FAIL. The history is serializable: the order W2, relay pass 1, W1 explains every read. The flaw is the relay's own assumption that ids appear in order. That is inferred from the definition of serializable in section 3.1, and E11 tests it.

The fix stops tracking ids at all. From `phase03_transactions/taskqueue.py:173`, the body of `relay_pass()`:

```python
# from phase03_transactions/taskqueue.py:173, the body of relay_pass(). Copied, first 17 lines
    conn.execute(begin_sql(level))
    if variant == "naive":
        # WRONG: a high-water mark on ids. An id is taken at INSERT and becomes
        # visible at COMMIT, so a lower id can appear after the mark passed it.
        last = conn.execute(SQL["relay_cursor"]).fetchone()[0]
        rows = conn.execute(SQL["relay_after"], (last,)).fetchall()
        for r in rows:
            broker.append(r[0])              # publish
        if rows:
            conn.execute(SQL["relay_move"], (rows[-1][0],))
        conn.execute("COMMIT")
    else:
        # RIGHT: every unsent row, whatever its id, marked sent in the same
        # transaction. SKIP LOCKED lets several relays run at once.
        rows = conn.execute(SQL["relay_unsent"]).fetchall()
        for r in rows:
            broker.append(r[0])              # publish before marking: at least once
```

The entry `SQL["relay_unsent"]` holds `SELECT id, task_id, event_type FROM tq_outbox WHERE sent_at IS NULL ORDER BY id LIMIT 100 FOR UPDATE SKIP LOCKED`. Event 1 is unsent when pass 2 runs, so pass 2 publishes it. Two limits come with the fix:

- **At least once.** The relay publishes, then marks the rows sent and commits. If it dies in between, the next pass publishes the same events again. `--crash-before-mark` is expected to show this as one "delivered twice" line. Richardson's page says the relay "might publish a message more than once", so "a message consumer must be idempotent". Debezium's outbox event router puts the event id in a header. Its documentation says: "You can use this ID, for example, to remove duplicate messages."
- **No global order.** Event 2 was published before event 1. A consumer may need the order of one task's events. Then give each event a sequence number within its task, and let the consumer reorder or reject. That design is inferred, and not part of this lab.

**A cursor that never skips.** Some relays must keep a cursor, for example to replay from a position. Oskar Dudycz, "How Postgres sequences issues can impact your messaging guarantees", 2022-10-28, gives a cursor that cannot skip. Each outbox row stores the ID of the transaction that wrote it. The column has type `xid8`, the 64-bit form of a transaction ID, and its default is `pg_current_xact_id()`. The relay reads only rows whose ID is below the snapshot's xmin, in transaction ID order:

```sql
-- after Dudycz 2022, with this schema's names, as a row comparison. A design, not the lab's SQL.
-- pg_cast.dat at REL_14_24 has no cast from bigint to xid8, so the saved cursor goes in as text.
SELECT id, task_id, event_type FROM tq_outbox
WHERE (xid, id) > (%(last_xid)s::text::xid8, %(last_id)s)
  AND xid < pg_snapshot_xmin(pg_current_snapshot())
ORDER BY xid, id LIMIT 100;
```

Every transaction with an ID below the snapshot's xmin has ended, by the definition in section 3.2. So no row can appear behind the cursor later. Three conditions make this hold. Each row must carry the ID of its own top-level transaction. `pg_current_xact_id()` returns that ID even inside a savepoint, Rogov, page 77. The cursor must move only to a row that the same query returned. And `pg_current_snapshot()` must be the snapshot that the query reads with. In PostgreSQL 14 it returns the active snapshot, at `xid8funcs.c` line 411, REL_14_24. The order is the order in which transactions got their IDs, not their commit order. Its cost is that one long transaction that has written stops the relay at its ID. Transaction IDs are shared by every database of the server, so that transaction can be anywhere on it. That cost is inferred from the same definition. `taskqueue.py --self-test` checks the rule on a simulated outbox, in `simulate_xid_relay`. The lab's relay does not use it.

**The consumer drops duplicates.** At-least-once delivery needs a consumer that applies each event once. Record the event id in the same transaction as the effect:

```sql
-- the consumer's own database. A design, not part of the lab
BEGIN;
INSERT INTO processed_events (event_id) VALUES (%s) ON CONFLICT DO NOTHING;
-- 0 rows inserted: this event was applied before. ROLLBACK, and acknowledge it
-- 1 row inserted: apply the effect here, then COMMIT
```

The primary key on `event_id` turns a second delivery into 0 rows, with no error. The record and the effect commit together, so a crash leaves both or neither, which is the atomicity of section 3.1. The design is inferred. Its parts are verified: the ON CONFLICT rule of section 3.6, and Debezium's event id header above.

**Measured relays.** This course found no production post about a PostgreSQL outbox with measured throughput or latency. SeatGeek, 2025-02-07, writes events into the WAL with `pg_logical_emit_message()` for Debezium, instead of an outbox table. Shopify, 2021-03-12, reads MySQL's change log with Debezium, so neither is an outbox table with numbers, and the references give their details.

The consumer may be another service with its own database. What happens when one side fails halfway is in course 5, Phase 2.

Here is the whole audit in one table. Each row has a check in `taskqueue.py` that exits with 1 when the invariant is broken:

| Transaction | Invariant | Anomaly at READ COMMITTED | Fix | Level after the fix |
|---|---|---|---|---|
| claim | one worker owns a claimed task | lost update on `owner`, section 3.3 | one `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED)` | READ COMMITTED |
| claim, after its commit | a claimed task runs again if its worker dies | not an isolation anomaly: a crash leaves it `running` for ever | a lease, a reaper, and an owner check on completion | READ COMMITTED |
| approval | one decision per task | write skew on an empty set, the phantom form, section 3.3 | a conditional state change on the task row first, and `UNIQUE (task_id)` | READ COMMITTED |
| outbox write | the event commits if and only if the change does | none: the INSERT reads nothing, and atomicity ties the event to the change | none needed | READ COMMITTED |
| outbox relay | every committed event is published | not an isolation anomaly: ids are not in commit order | mark rows sent, poll unsent rows | any |

**The failure: a test in commit order.** The naive relay passes every test in which transactions commit in id order. `taskqueue.py --self-test` checks exactly that: with event 1 committed before event 2, the naive relay publishes both. Only a test that commits the higher id first, while the lower one is still open, shows the skip. That needs two connections and a fixed order, as every lab in this phase uses.

**The sentence to remember:** check the scope first, then audit each transaction by its invariant and the reads it decides on. At READ COMMITTED, the claim suffers a lost update, and the approval write skew on an empty set. The outbox write needs no isolation, because atomicity ties the event to the change. A claim also needs a lease, because a crash after it leaves the task running for ever.

**The trap:** a relay that remembers the highest id it published. Ids are given at insert and become visible at commit. So a slow transaction's event is skipped for ever, and a higher isolation level does not help.

**Try this now:** run `uv run python phase03_transactions/taskqueue.py --check all --variant naive --level read-committed`, then the same with `--variant fixed`. Check the exit code with `echo $?`: 1 for the first run and 0 for the second.

---

## 🧪 Hands-on lab

The labs below are written and reviewed, but were not run by the author. Each script was checked with `python3 -m py_compile` only. Every "Expected" line says "Not run by the author yet." and then gives the expected shape. Each value comes from the docs or source that this phase cites, or from reading the code by hand. None of them is a measurement. Each script fixes the order of steps. So the results that do not depend on time should match exactly. Times, such as the deadlock wait, depend on your machine.

**What you build.** You build three things. First, two-session reproductions of every anomaly of this phase, on your PostgreSQL 14. Second, an offline model of the same rules. Third, the audit of the task queue:

| File | What it holds | Self-test checks |
|---|---|---|
| `shared/pglab.py` | sessions driven step by step, the lock-wait probe, `run_with_retry`, the database guard | retry of the whole transaction, a 40001 at COMMIT, the attempt cap, 25P02 for the WRONG retry |
| `phase03_transactions/mvcc_model.py` | row versions, snapshots, first-updater-wins, SSI, waits and deadlocks, six histories | the snapshot example of Table 9.77, the matrix of section 3.3, each rule removed in turn |
| `phase03_transactions/lost_update.py` | the budget spend, four strategies, two schedules, `--retry`, `--wrong-retry` | the invariant, the SQL of each strategy |
| `phase03_transactions/write_skew.py` | the approvers on call, `--fix lock-rows`, `--show-locks` | the rule and the invariant |
| `phase03_transactions/phantom.py` | the phantom read, the running limit, three fixes, one a partial unique index | the limit arithmetic, the SQL of each fix |
| `phase03_transactions/deadlock.py` | two transfers in opposite order, `--ordered`, `--retry` | that opposite order forms a cycle and one order does not |
| `phase03_transactions/contention.py` | five strategies under 1 to 64 hot rows | 1 / (1 − p), n (n + 1) / 2, the percentile method |
| `phase03_transactions/taskqueue.py` | the schema, five checks with the lease, `--unique-decision`, exit code 1 on a broken invariant | the claim in the model, both relays and the xid8 cursor on a simulated outbox, the lease and reaper SQL |
| `phase03_transactions/lockwatch.py` | a queue of waiters on one row, the "who blocks whom" query, `pg_locks.waitstart`, `log_lock_waits`, a multixact | the head of a wait chain on Rogov's printed rows, the log-line format |
| `phase03_transactions/queue_horizon.py` | a claim loop with and without one open snapshot | the percentile method, the claim and index SQL |

Every PostgreSQL lab refuses a database whose name does not start with `storage_lab`. It drops and creates only tables that start with `tq_`. The demonstration of this phase is E4, E5 and E10. E4 and E5 reproduce two anomalies on demand, and stop each with a named mechanism. E10 hardens the task queue's three transactions, each with a check that fails at the old level.

The first `uv run` installs psycopg 3.3.6, so it needs the network once.

- [ ] **E1 (offline).** Run every self-test of this phase, then the earlier phases' self-tests.
  - Run: `for f in shared/pglab.py phase03_transactions/*.py; do echo "$f"; uv run python "$f" --self-test; done`
  - Then run: `for f in shared/durable.py phase01_durability/*.py phase02_structures/*.py; do echo "$f"; uv run python "$f" --self-test; done`
  - Expected: Not run by the author yet. `self-test passed` after each of the 10 Phase 3 files, and after each of the 12 earlier files. This phase added `shared/pglab.py` and a dependency, and changed no earlier file.
  - If it fails: the assertion message names the rule or the number. Compare it with the section it comes from before you change any code.
  - Teaches: each rule that the text calls important has a check that fails without it.

- [ ] **E2 (offline).** The model's matrix, and the model with one rule removed.
  - First write your prediction for every cell of the matrix in section 3.3.
  - Run: `uv run python phase03_transactions/mvcc_model.py`, then the same with `--no-ssi`, then with `--no-first-updater-wins`.
  - Expected: Not run by the author yet. The first run prints the matrix of section 3.3, with its `deadlock` row. With `--no-ssi`, `write-skew` and `phantom-limit` become `BROKEN` under serializable. With `--no-first-updater-wins`, `lost-update` becomes `BROKEN` under repeatable-read. Under serializable it still holds, with `T2 40001`. The SSI check catches the pair, because each transaction read the row that the other wrote. Add `--history lost-update --level serializable --trace` to see the check doom T2 at its UPDATE and fail it at COMMIT.
  - Teaches: snapshot isolation stops lost updates with one rule, and serializable stops write skew with one more.

- [ ] **E3 (local).** Check the server and its settings.
  - Run: `uv run python shared/pglab.py --setup`.
  - Expected: Not run by the author yet. `created database storage_lab` only if Phase 1 did not create it. Then `server_version 14.24`, `default_transaction_isolation read committed`, `deadlock_timeout 1000ms`, `lock_timeout 0ms`, `idle_in_transaction_session_timeout 0ms`, `max_pred_locks_per_transaction 64`, `max_pred_locks_per_relation -2` and `max_pred_locks_per_page 2`. These are the defaults that sections 3.4 and 3.5 cite.
  - If it fails with a connection error: check that the server runs, with `pg_isready -h /tmp -p 5432`.
  - Teaches: your server's defaults, before any lab depends on them.

- [ ] **E4 (break-it, local).** Part of the demonstration: the lost update, and three ways to stop it.
  - Run: `uv run python phase03_transactions/lost_update.py --level read-committed`, then `--level repeatable-read`, then `--level repeatable-read --retry`, then `--level read-committed --strategy atomic`.
  - Expected: Not run by the author yet. Read committed: an `obs` line names T1's pid in `pg_blocking_pids(T2)`. T2's UPDATE returns 1 row after its wait, then `RESULT: BROKEN. credits 20 after 2 committed spend(s) of 80 from 100`. Repeatable read: T2's UPDATE ends in `ERROR 40001: could not serialize access due to concurrent update`, and `RESULT: holds. credits 20 after 1 committed spend(s) of 80 from 100`. With `--retry`, one more line says `attempt 1: refused, 20 < 80`. With `--strategy atomic`, T2's UPDATE returns 0 rows after its wait, and the result holds.
  - Then try `--schedule commit-first` at read committed. That order is Berenson's history H4. No `obs` line appears, because T2 never waits, and the result is still BROKEN.
  - Teaches: READ COMMITTED re-checks the WHERE clause after a wait, and REPEATABLE READ refuses to change a replaced row.

- [ ] **E5 (break-it, local).** Part of the demonstration: write skew, and SERIALIZABLE.
  - Run: `uv run python phase03_transactions/write_skew.py --level repeatable-read`, then `uv run python phase03_transactions/write_skew.py --level serializable --retry`.
  - Expected: Not run by the author yet. Repeatable read: two UPDATEs of 1 row each, two successful COMMITs, no wait, and `RESULT: BROKEN. 0 approver(s) on call`. Serializable: one `ERROR 40001: could not serialize access due to read/write dependencies among transactions`, expected at B's COMMIT, with a `DETAIL: Reason code:` line and `HINT: The transaction might succeed if retried.`. Then `count 1, bob stays on call`, and `RESULT: holds. 1 approver(s) on call`.
  - Then run `--level read-committed --fix lock-rows`. B's lock read waits for A, returns only Bob's row, and the result holds.
  - Teaches: write skew raises no error below SERIALIZABLE, and SERIALIZABLE turns it into a 40001 that a retry absorbs.

- [ ] **E6 (break-it, local).** Phantoms: the read that PostgreSQL stops, and the decision it does not.
  - Run: `uv run python phase03_transactions/phantom.py --case reread --level read-committed`, then `--case reread --level repeatable-read`.
  - Then run: `uv run python phase03_transactions/phantom.py --case limit --level repeatable-read`, then `--case limit --level read-committed --fix for-update`, then `--case limit --level read-committed --fix parent-row`, then `--case limit --level read-committed --fix unique-index`.
  - Expected: Not run by the author yet. `first count 2, second count 3` at read committed, and `first count 2, second count 2` at repeatable read. The limit case at repeatable read: `RESULT: BROKEN. 2 running task(s) for acme, limit 1`. With `--fix for-update`, both lock reads print `0 row(s)`, and the result is still BROKEN. With `--fix parent-row`, W2's slot reservation waits, then updates 0 rows, and the result holds. With `--fix unique-index`, W2's claim waits for W1, then ends in `ERROR 23505: duplicate key value violates unique constraint "tq_one_running_per_tenant"`, and the result holds.
  - Teaches: a snapshot hides new rows from a re-read. A decision about an empty set needs SERIALIZABLE, a parent row, or for a limit of 1 a unique index.

- [ ] **E7 (break-it, local).** A deadlock, its report, and the fix.
  - First predict which session fails, and after how long.
  - Run: `uv run python phase03_transactions/deadlock.py`, then `--retry`, then `--ordered`.
  - Expected: Not run by the author yet. Two "sent, waiting for the server" lines. About 1 second after T2's line, T2 ends with `ERROR 40P01: deadlock detected`, two DETAIL lines that each start with `Process`, and `HINT: See server log for query details.`. The victim is inferred from the lmgr README, so T1 may be the victim on your server. `RESULT: total credits 200, unchanged`. With `--retry`, the victim's transfer runs again and succeeds. With `--ordered`, no ERROR line appears.
  - If it prints LAB ERROR about a wait: another session holds a lock on `tq_budget`. Close other psql sessions on `storage_lab`.
  - Teaches: a cycle is broken after `deadlock_timeout`, and a fixed lock order prevents it.

- [ ] **E8 (local).** See SIREAD locks and lock waits from a third session.
  - Run: `uv run python phase03_transactions/write_skew.py --level serializable --show-locks`.
  - Expected: Not run by the author yet. After the two counts, `obs` lines with `SIReadLock` for both sessions. The table has two rows, so the planner should use a sequential scan. The docs say that a sequential scan takes a relation-level predicate lock. So expect `locktype relation` on the table `tq_oncall`. That is inferred, and was not run.
  - Teaches: SIREAD locks are visible in `pg_locks`, and a sequential scan locks the whole table.

- [ ] **E9 (local).** Optimistic against pessimistic, by contention.
  - First predict the retries of `version` at 1 hot row and at 64, from section 3.6.
  - Run: `uv run python phase03_transactions/contention.py --workers 8 --increments 200 --hot-rows 1,64`, then the same with `--think-ms 2`.
  - Expected: Not run by the author yet. No numbers are given, because none were measured. The shape: `naive` shows `lost` above 0 at 1 hot row, and the other strategies show 0. `version` and `serializable` show many retries at 1 hot row and few at 64. The `for-update` rows show 0 retries. With `--think-ms 2`, the p99 of `for-update` at 1 hot row grows. A waiting worker waits for each earlier worker's 2 ms of work. Waiters are not served in arrival order, section 3.4. So the p99 can pass the 7 × 2 = 14 ms of a fair queue of 8 workers. That is inferred, and not run.
  - Teaches: contention decides whether waiting or redoing costs less.

- [ ] **E10 (local).** Part of the demonstration: the task-queue audit, with checks that fail at the old level.
  - Run: `uv run python phase03_transactions/taskqueue.py --check all --variant naive --level read-committed; echo "exit $?"`.
  - Then run: `uv run python phase03_transactions/taskqueue.py --check all --variant fixed --level read-committed; echo "exit $?"`.
  - Expected: Not run by the author yet. The naive run prints `FAIL` for `claim`, `approval`, `outbox`, `lease` and `dual-write`, and `exit 1`. The claim line is the one in section 3.7. The fixed run prints `PASS` for all five, and `exit 0`. The lease check sleeps for its lease of 300 ms and 0.2 s more.
  - Then run `--check claim --variant naive --level repeatable-read --retry`. Expected: worker B gets 40001, its retry finds no queued task, and the check prints `PASS`.
  - Then run `--check approval --variant naive --unique-decision`. Expected: Bob's INSERT waits, then ends in `ERROR 23505`, and `PASS approval: task 2 has decision(s) ['approve'], state awaiting_approval`.
  - Then run `--check lease --variant fixed`. Expected: the reaper line says `requeued [1]`, worker B claims task 1, worker A's late completion updates `0 row(s)`, and `PASS lease: task 1 is done, owner B`.
  - Teaches: each fix changes one statement, at the default level. Each one has a test that fails without it.

- [ ] **E11 (break-it, local).** The relay that no isolation level fixes, and at-least-once delivery.
  - Run: `uv run python phase03_transactions/taskqueue.py --check outbox --variant naive --relay-level serializable`.
  - Then run: `uv run python phase03_transactions/taskqueue.py --check outbox --variant fixed --crash-before-mark`.
  - Expected: Not run by the author yet. The naive relay at serializable: `FAIL outbox: committed events [1, 2], published [2], never published [1]`. The fixed relay with the crash: `delivered twice: [2]`, then `PASS outbox: committed events [1, 2], published [2, 1, 2], never published []`.
  - Teaches: a relay that tracks ids is wrong at every level, and the fixed relay needs an idempotent consumer.

- [ ] **E12 (break-it, local).** The WRONG retry against the real server.
  - Run: `uv run python phase03_transactions/lost_update.py --level repeatable-read --wrong-retry`.
  - Expected: Not run by the author yet. T2's first UPDATE ends in `ERROR 40001`. Its resent UPDATE ends in `ERROR 25P02: current transaction is aborted, commands ignored until end of transaction block`. The result holds, because T2 spent nothing.
  - Teaches: after a 40001, only ROLLBACK and a new transaction help. E16 shows what else the aborted state accepts.

- [ ] **E13 (live).** Lock waits as you see them at work.
  - Run: `uv run python phase03_transactions/lockwatch.py --case queue`, then the same with `--log-lock-waits`, then `--case multixact`.
  - Expected: Not run by the author yet. The first table shows the holder with `Client`, `ClientRead` and `{}`. The first waiter shows `Lock`, `transactionid` and the holder's pid. The two later waiters show `Lock` and `tuple`, as in Rogov's page 219. `pg_locks` shows one row per waiter with `granted` f and a `waited_s` value from `waitstart`. After the holder commits, the remaining waiters show `transactionid`. The last two lines give the arrival order, the order that got the row, and the RESULT. They may differ, and either result agrees with section 3.4. With `--log-lock-waits` as a superuser, the server log gets at least one `still waiting for` line per waiter. A waiter that waits twice, first on the tuple and then on a transaction ID, can write two. Each logged wait gets one `acquired` line when it ends. As another role, the script says that the settings need a superuser, and exits with 2. With `--case multixact`, B's INSERT returns with no wait. If the extension can be created, `pgrowlocks` shows `multi` t and the two modes Key Share and No Key Update. Expect `{"No Key Update","Key Share"}`, the reverse of Rogov's order. PostgreSQL 14 sorts the members of a multixact by transaction ID, at `multixact.c` line 1637, and A got its ID first. That order is inferred from the source.
  - If it fails with LAB ERROR about a wait: another session holds a lock on `tq_lw_row`. Close other psql sessions on `storage_lab`.
  - Teaches: the `transactionid` and `tuple` waits, `waitstart`, and the log lines that name them.

- [ ] **E14 (local).** A deadlock as a counter and as log lines.
  - Run: `psql -h /tmp -p 5432 -d storage_lab -Atc "select deadlocks from pg_stat_database where datname = current_database()"`, then `uv run python phase03_transactions/deadlock.py`, then the psql command again.
  - Expected: Not run by the author yet. The second number is one higher than the first. PostgreSQL 14 sends statistics from each backend with a short delay. So if the number did not change, wait a second and read it again. That delay was not checked. Then find the deadlock's ERROR in the server log. There, its DETAIL has one more line per process, `Process %d: %s`, with each query, from `deadlock.c` line 1140. If `log_lock_waits` is on, the victim's log also has a `detected deadlock while waiting for ShareLock on transaction` line. `proc.c` line 1516 writes these lines only when `log_lock_waits` is on.
  - Teaches: a deadlock shows as a counter and as log lines before anyone reports it.

- [ ] **E15 (break-it, local).** One open snapshot slows every claim.
  - First predict how many dead row versions 5,000 worked jobs leave while a snapshot is held.
  - Run: `uv run python phase03_transactions/queue_horizon.py`, then the same with `--index pkey`.
  - Expected: Not run by the author yet. No times are given, because none were measured. In the baseline, the median claim time stays about flat over its 10 batches. During the hold it grows from batch to batch. `n_dead_tup` grows by about 2 × 500 = 1,000 per batch. Each job leaves two dead versions: the replaced queued version and the deleted running version. The statistics lag, so that column may trail by a batch. The VACUUM VERBOSE line reports about 2 × 5,000 = 10,000 dead row versions that "cannot be removed yet". Its oldest xmin equals the holder's `backend_xmin`. After the release and a VACUUM, the median falls back toward the baseline. With `--index pkey`, expect the same shape. Which index degrades faster was not checked.
  - If it fails with "the queue ran empty": raise `--backlog`.
  - Teaches: one snapshot held anywhere slows a busy queue, and the VACUUM line names the snapshot.

- [ ] **E16 (local).** What an aborted transaction accepts.
  - Run this, which sends two transactions to one psql session:

```bash
psql -h /tmp -p 5432 -d storage_lab <<'SQL'
BEGIN;
SELECT 1/0;
SELECT 1;
COMMIT;
BEGIN;
SAVEPOINT s;
SELECT 1/0;
ROLLBACK TO SAVEPOINT s;
SELECT 1 AS after_savepoint;
COMMIT;
SQL
```

  - Expected: Not run by the author yet. The first transaction prints `ERROR:  division by zero`, then `ERROR:  current transaction is aborted, commands ignored until end of transaction block`, then `ROLLBACK` as the reply to COMMIT. Rogov, pages 78 and 79, prints these three replies on PostgreSQL 14. The second transaction prints the division error, then `ROLLBACK` for the ROLLBACK TO SAVEPOINT, then `after_savepoint` with 1, then `COMMIT`.
  - Teaches: COMMIT in an aborted transaction rolls it back, and ROLLBACK TO SAVEPOINT is the way to go on inside it.

---

## 🔍 Check it yourself

- **Check 1.** Open `phase03_transactions/mvcc_model.py:298`, the conflict branch of `update()`. It raises `Blocked` while the other writer is still running, and raises 40001 only after that writer has committed. Suppose the two checks were swapped. What would a REPEATABLE READ transaction do when the other writer later rolls back? What does the PostgreSQL 14 docs' text in section 13.2.2 say should happen?

- **Check 2.** Open `shared/pglab.py:411`, the retry loop. In it, COMMIT sits inside the `try`. Move it outside, after the loop, in your head. Which history of section 3.5 would then end in an error that reaches the caller? Which line of the self-test of `pglab.py` would fail?

- **Check 3.** Open `phase03_transactions/taskqueue.py:134`, `claim_fixed`. Replace `SKIP LOCKED` with `NOWAIT`, the option of section 3.6 that raises 55P03. Which worker now gets the error, and at which step of the claim check? Is the queue still correct then? Take ten workers and one queued task. How many fail on each poll, and what must each one do next?

- **Check 4.** Open `phase03_transactions/phantom.py:98`, the slot reservation. A task that finishes must give its slot back. Write the UPDATE that does it. Say which transaction it must share, and what goes wrong if it runs in a transaction of its own.

- **Check 5.** In any repository you own that uses PostgreSQL, run `grep -rn "FOR UPDATE\|isolation\|SERIALIZABLE\|40001\|40P01" <your repo>/`. Then find three places that read a value and write based on it. For each one, write its invariant and name the anomaly it can suffer at its level. Then say which check would show it.

- **Check 6.** Open `phase03_transactions/taskqueue.py:144`, the reaper, and `SQL["complete"]` below it. Suppose `complete` checked only `id = %s AND state = 'running'`, without the owner. Walk through `--check lease --variant fixed` with worker A paused, not dead. How many workers would record a result for task 1? Which line of `check_lease` would then show it?

---

## ✅ Checkpoint 3 — answer in your own words

The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

1. **Test-out, explain.** Use the approvers' case. Explain write skew: what each transaction reads and writes. Explain why snapshot isolation allows it, in terms of first-updater-wins. Then explain what SERIALIZABLE in PostgreSQL does differently. Say which edges it records and which structure it looks for. Say what the client must do when it finds one.

2. **Test-out, predict.** `tq_budget` holds `acme` 100 and `beta` 100, and has no CHECK constraint on credits. The rule is that their sum stays at or above 0. Each transaction reads `SELECT sum(credits)` over both rows, and if the sum is at least 150, debits 150.
   (a) T1 debits `acme` and T2 debits `beta`, both at REPEATABLE READ, both reading the sum before either writes. Can the rule break, and what are the final balances?
   (b) Both debit `acme` with `SET credits = credits - 150`, at READ COMMITTED. Can the rule break, and does any session wait?
   (c) Case (b) at REPEATABLE READ.
   (d) Case (a) at SERIALIZABLE.

3. **Test-out, demonstrate.** Run E4, E5 and E10. Show the lost update and the write skew breaking, and the named mechanism that stops each one. Then show the claim check failing with the naive code at READ COMMITTED and passing with the fix. Explain why the check is deterministic and not a lucky timing.

4. **A colleague says:** "We set `default_transaction_isolation` to repeatable read, so race conditions are gone." Argue for or against. Which of this phase's failures does that change stop, and which does it leave? What new error must the application now handle, and how?

5. **This is broken.** A nightly job renews subscriptions. For each customer, it moves credits between that customer's tenants, in the order the billing API returns them. The log shows `ERROR: deadlock detected` five to ten times a night. Each failed renewal waited about one second. What is the cause, how do you confirm it from the DETAIL lines, and what is the fix? Is raising `deadlock_timeout` a fix for it?

6. **Show the arithmetic.** (a) An optimistic claim conflicts with probability 0.3 per attempt. How many attempts does it need on average? (b) Twenty workers start together on one hot row, and each round lets one commit. How many attempts do they make in total, and how many does the last one make? (c) In Ports and Grittner's RUBiS run, SSI served 422 requests per second with 0.03% failures. S2PL served 208 requests per second with 0.76%. How many failures per hour is each, and what conditions limit what those numbers say about your server?

7. **Given these constraints, design.** A reminder service emails about each task that has waited 24 hours in `awaiting_approval`. It must send exactly one email per task. Three scheduler instances run at once, and any of them can be killed at any moment. Design the claim, the state change, the event, and what the email consumer does. Say what each step costs at READ COMMITTED. Name the check from this phase's lab that you would copy to test it.

8. **This is broken.** These numbers are an example. The task queue's claim p99 rose from 2 ms to 300 ms over two hours. The queued count grew from 200 to 9,000. Database CPU is up, and nothing was deployed. `pg_stat_activity` shows one session `idle in transaction`, with `xact_start` two hours ago. What is the cause? How do you confirm it with one query and one VACUUM line? What do you change so it cannot recur? At 50 claims per second, how many dead row versions has the queue table gained in those two hours, at two per job?

<details>
<summary>Answer sketches</summary>

1. Each approver reads both rows and writes only its own. First-updater-wins fails a transaction only when it changes a row that a concurrent transaction replaced. No row was written twice, so both commit, and the rule breaks with no error. SERIALIZABLE in PostgreSQL also records rw-antidependencies. A rw→ B, because A read Bob's row and B wrote a newer version of it. B rw→ A in the same way. Two rw edges in a row between concurrent transactions are the dangerous structure of Cahill and others, 2008. When A commits, B is a pivot whose out-edge points to a committed transaction, so B fails with 40001. The client must roll back and run B's whole transaction again. The retry counts 1 and stays on call.

2. (a) Yes, the rule can break. Both read 200 from their snapshots, and each debits a different row. Final: `acme` −50, `beta` −50, sum −100. That is write skew, the shape of Berenson's H5. No session waits in this case. (b) Yes, it breaks, and T2 waits. T2's UPDATE waits for T1's row lock. Then it re-checks `tenant = 'acme'` on the new row, which still matches. It debits again: 100 − 150 − 150 = −200, and the sum is −100. No update is lost, because both debits apply. But T2 decided on a sum that was out of date. (c) T2 waits, then gets 40001 when T1 commits. Its retry reads a sum of −50 + 100 = 50, which is below 150. So it does not debit, and the rule holds. (d) One transaction gets 40001, expected at the second COMMIT. Its retry reads 200 − 150 = 50 and does not debit, and the rule holds.

3. From the runs. Expected shapes are in E4, E5 and E10. Lost update at READ COMMITTED: 160 spent from 100. Stopped by REPEATABLE READ's first-updater-wins, with 40001, or by the atomic UPDATE, with 0 rows. Write skew: 0 on call at REPEATABLE READ, stopped by SSI with 40001 and a retry. The check is deterministic because of the lock-wait probe. The script waits until `pg_stat_activity` shows the second session waiting, with `pg_blocking_pids` naming the first. Only then does it commit the first. The order is chosen by the test, not by the timing.

4. Partly for it, and mostly against it. REPEATABLE READ stops the lost update: E4 at repeatable read gets 40001 instead of 160 spent. It stops read skew, the report that printed 280. It leaves write skew: 0 approvers on call in E5. It leaves the phantoms: 2 running tasks in E6, and 2 decisions in E10. It also does not fix the outbox relay, which no level fixes. The new error is 40001, which every transaction that writes can now raise. The application needs a retry loop of the whole transaction, with COMMIT inside it. It retries only 40001 and 40P01, with a cap and jitter. Without the loop, each 40001 becomes a failed request. On MySQL InnoDB the same level name would not even stop the lost update, by Hermitage's table.

5. Cause: two renewals lock the same two tenant rows in opposite orders, because the API returns tenants in different orders. The DETAIL lines of each error show the cycle. One says that process P waits for `ShareLock on transaction` X, blocked by process Q. The next one says the reverse. The CONTEXT line names the row of `tq_budget` each one wanted. Check `log_lock_waits` and the server log, where each process's query appears. Fix: lock all of one customer's tenant rows first, in one order, with `SELECT ... ORDER BY tenant FOR UPDATE`, as `deadlock.py --ordered` does. Keep a retry for 40P01 as a second defense. Raising `deadlock_timeout` is not a fix. The cycles stay, and each one holds both renewals for longer before one fails. The one-second wait is the default `deadlock_timeout`. The server confirms it too. `pg_stat_database.deadlocks` rises by 5 to 10 a night. With `log_lock_waits = on`, each victim's log has `process %d detected deadlock while waiting for ShareLock on transaction %u after %ld.%03d ms`. Suppose the job moves credits with one UPDATE over many tenants. Then the cycle can also sit inside two statements' scan orders, as in section 3.4. The same fix holds: lock the rows first, in key order.

6. (a) 1 / (1 − 0.3) = 1 / 0.7 = 1.43 attempts. (b) 20 × 21 / 2 = 210 attempts for 20 commits. The last worker makes 20 of those attempts. (c) This takes one transaction per request, which the paper does not state. SSI: 422 × 3,600 × 0.0003 = 455.8, about 456 failures per hour. S2PL: 208 × 3,600 × 0.0076 = 5,690.9, about 5,691 per hour. Limits: PostgreSQL 9.1, measured in 2012. One 7,200 RPM disk and a Core 2 Quad Q9550 with 8 GB. The RUBiS bidding mix, 85% read-only. Your rate depends on your transactions' read and write sets. Measure the 40001 rate on your own workload.

7. Here is one possible design among several. Each scheduler runs a short transaction: `UPDATE tq_tasks SET reminder_state = 'claimed' ... WHERE id = (SELECT id FROM tq_tasks WHERE state = 'awaiting_approval' AND <waited 24 hours> AND reminder_state IS NULL ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING id`. The same transaction inserts a `task.reminder_due` event into `tq_outbox`. Two schedulers never take the same task, and nobody waits. The state change and the event commit together, so a killed scheduler leaves either both or neither. The relay polls unsent rows with `SKIP LOCKED` and marks them sent, so a late commit is not skipped. It delivers at least once, so the email consumer keeps the event ids it has handled and drops a repeat. At READ COMMITTED this costs no retries and no long locks. The email itself happens outside any transaction. Exactly one email then needs one more step. The consumer records the id before it sends, or the email provider accepts an idempotency key. That last part is outside the database and needs its own check. Tests to copy: the claim check and the outbox check with `--crash-before-mark` from `taskqueue.py`. `reminder_state` is a new column this design adds. It is an example, not part of the lab schema. Two more tools fit. A partial unique index, `CREATE UNIQUE INDEX ON tq_outbox (task_id) WHERE event_type = 'task.reminder_due'`, makes one reminder event per task a rule that later code cannot break. If only one scheduler may work at a time, each can start with `pg_advisory_xact_lock(hashtext('reminders'))`. The claim needs no lease here, because the state change and the event commit together, and no slow work happens in between.

8. Cause: the idle transaction holds the cleanup horizon two hours in the past. VACUUM cannot remove the queue's dead versions. So every claim's index scan steps over more of them, as in Brandur Leach's 2015 measurements. Claims get slower than jobs arrive, so the queue grows. Confirm: `SELECT pid, age(backend_xmin), state, now() - xact_start FROM pg_stat_activity ORDER BY 2 DESC` puts that session first. `VACUUM VERBOSE tq_tasks` reports many dead row versions that "cannot be removed yet", with an `oldest xmin` equal to that `backend_xmin`. Fix now: end the session with `pg_terminate_backend(pid)`, then let VACUUM run. Prevent it in three ways. Set `idle_in_transaction_session_timeout` per role, and add `transaction_timeout` on PostgreSQL 17 and later. Keep the partial index on queued rows. Alert on `age(backend_xmin)`, as Phase 4, section 4.5, does. Arithmetic: 50 × 7,200 seconds = 360,000 jobs, and 2 × 360,000 = 720,000 dead row versions.

</details>

---

## References & Further Learning

This course's research fetched the papers, analyses and outbox sources below on 2026-10-17. For this phase, more pages were fetched on 2026-10-18. They are the PostgreSQL 14 docs beyond chapter 13, more source files at REL_14_24, and the psycopg docs. Every URL was checked again with `check_urls.py` when this phase was written. Primary sources come first in each group.

### The original papers

- **A Critique of ANSI SQL Isolation Levels, Berenson, Bernstein, Gray, Melton, E. O'Neil and P. O'Neil, ACM SIGMOD 1995** — https://arxiv.org/pdf/cs/0701157
  Focus on: sections 2.2 and 3 for P0 to P3, and section 4.1 for P4 and history H4. Section 4.2 has snapshot isolation, A5A, A5B, history H5, the 8-hour example and Remark 9. Table 4 is on page 10. It takes about 45 minutes. This is the arXiv copy of MSR-TR-95-51. Its extracted text has broken spacing, so copy formulas from the PDF pages. Read it before you run E4.
- **Serializable Isolation for Snapshot Databases, Cahill, Röhm and Fekete, ACM SIGMOD 2008** — https://people.eecs.berkeley.edu/~kubitron/courses/cs262a-F13/handouts/papers/p729-cahill.pdf
  Focus on: section 1, Example 1 and Figure 1, the doctors on duty. It is the origin of this phase's opening case. Section 2.2 for the dangerous structure and the pivot. Section 5 measures the first SSI, in Berkeley DB 4.6.21 with page-level locks, on 2008 hardware. So do not compare its numbers with PostgreSQL's. A course mirror of the paper.
- **Serializable Snapshot Isolation in PostgreSQL, Ports and Grittner, PVLDB 5(12), VLDB 2012** — https://vldb.org/pvldb/vol5/p1850_danrkports_vldb2012.pdf
  Focus on: section 2.1 for the doctors example in PostgreSQL's terms. Sections 4 and 5.2 for SIREAD locks and safe snapshots, and 5.4 for which transaction to cancel. Section 8 for every number in section 3.5, on PostgreSQL 9.1 and the paper's 2012 hardware. The paper also notes some history. For years the docs did not say that the old SERIALIZABLE mode was not truly serializable. It takes about 70 minutes, and is best read before E5.
- **Generalized Isolation Level Definitions, Adya, Liskov and O'Neil, IEEE ICDE 2000** — https://web.archive.org/web/20210122030451/http://pmg.csail.mit.edu/papers/icde00.pdf
  Focus on: section 5, the phenomena G0 to G2 and G2-item. Jepsen and Hermitage use these names. A Wayback copy, because the original host refused connections.
- **Weak Consistency: A Generalized Theory and Optimistic Implementations for Distributed Transactions, Atul Adya, MIT PhD thesis, 1999** — https://publications.csail.mit.edu/lcs/pubs/pdf/MIT-LCS-TR-786.pdf
  Focus on: section 4.1 for G-single, the read skew of Hermitage, and section 4.3 for the definition of snapshot isolation. Read only those two sections, because the rest goes far beyond this phase.

### Books and lectures

- **PostgreSQL 14 Internals, Egor Rogov, Postgres Professional, 2022 to 2023, free PDF** — https://edu.postgrespro.com/postgresql_internals-14_en.pdf
  Focus on: section 2.3, pages 47 to 60, for the READ COMMITTED re-check, the read-only anomaly and DEFERRABLE. Section 3.7, pages 76 to 79, for subtransactions and the aborted state. Chapter 13, pages 211 to 230, for the tuple-lock queue, multixacts, SKIP LOCKED and deadlocks inside two UPDATEs. Every output in these pages was printed on PostgreSQL 14, the version you run. The book's home page is https://postgrespro.com/community/books/internals.
- **CMU 15-445/645 Database Systems, Fall 2025, lecture 18 notes, Two-Phase Locking** — https://15445.courses.cs.cmu.edu/fall2025/notes/18-twophaselocking.pdf
  Focus on: deadlock detection against prevention, wait-die and wound-wait. It takes about 20 minutes.
- **CMU 15-445/645, Fall 2025, lecture 20 slides, Multi-Version Concurrency Control** — https://15445.courses.cs.cmu.edu/fall2025/slides/20-multiversioning.pdf
  Focus on: version storage, append-only against delta, and slide 33, the table of engines.

### Production reports

- **ACIDRain: Concurrency-Related Attacks on Database-Backed Web Applications, Warszawski and Bailis, SIGMOD 2017** — https://www.bailis.org/papers/acidrain-sigmod2017.pdf
  Focus on: the introduction, for the 22 attacks, the 17 that come from transaction scope, and Flexcoin. Then section 2, which separates level-based and scope-based anomalies.
- **Postgres Job Queues & Failure By MVCC, Brandur Leach, 2015-05-18** — https://brandur.org/postgres-queues
  Focus on: "Slow lock time" and "Dead tuples", for the lock time and the 100,000 dead rows, and the VACUUM VERBOSE output. Heroku Postgres, the Que library with advisory locks, about 50 jobs a second. No SKIP LOCKED.
- **Why we spent the last month eliminating PostgreSQL subtransactions, GitLab, 2021-09-29** — https://about.gitlab.com/blog/why-we-spent-the-last-month-eliminating-postgresql-subtransactions/
  Focus on: "What is SubtransControlLock?" and "Reproducing the problem with replicas", for the drop from about 360,000 to 50,000 transactions per second. Replicas only, with a long transaction on the primary.
- **How Postgres sequences issues can impact your messaging guarantees, Oskar Dudycz, 2022-10-28** — https://event-driven.io/en/ordering_in_postgres_outbox/
  Focus on: the `xid8` column and `pg_snapshot_xmin(pg_current_snapshot())`, and the final query that orders by transaction ID. A design post, with no measurements.
- **pgsql-bugs #12990, multixact member files, PostgreSQL 9.3.5, 2015** — https://www.postgresql.org/message-id/20150406192130.2573.22545%40wrigleys.postgresql.org
  Focus on: the workload of `SELECT ... FOR SHARE` from 26 connections, and the table of members files over one day. An old version, so read it for the mechanism only.

### PostgreSQL 14 documentation

- **13.2 Transaction Isolation** — https://www.postgresql.org/docs/14/transaction-iso.html
  Focus on: Table 13.1, and the rule for an UPDATE after a wait at READ COMMITTED. Then the 40001 at REPEATABLE READ, and the advice list for SERIALIZABLE. The most important page of this phase.
- **13.1 Introduction to concurrency control** — https://www.postgresql.org/docs/14/mvcc-intro.html
  Focus on: the sentence on reading and writing never blocking each other.
- **13.3 Explicit Locking** — https://www.postgresql.org/docs/14/explicit-locking.html
  Focus on: 13.3.1 table-level locks, Table 13.3 for row locks, 13.3.4 Deadlocks, and 13.3.5 Advisory Locks with its three warnings.
- **9.27.10 Advisory Lock Functions** — https://www.postgresql.org/docs/14/functions-admin.html
  Focus on: Table 9.98, the `xact` and `try` forms.
- **52.74 pg_locks** — https://www.postgresql.org/docs/14/view-pg-locks.html
  Focus on: `waitstart`, new in version 14, and the `locktype` values `transactionid` and `tuple`.
- **11.8 Partial Indexes** — https://www.postgresql.org/docs/14/indexes-partial.html
  Focus on: Example 11.3, the partial unique index.
- **INSERT** — https://www.postgresql.org/docs/14/sql-insert.html
  Focus on: the ON CONFLICT clause, and the sentence on the atomic outcome.
- **25.1.5.1 Multixacts and Wraparound** — https://www.postgresql.org/docs/14/routine-vacuuming.html
  Focus on: the 10GB and 20GB limits of the member storage.
- **27.4 Hot Standby** — https://www.postgresql.org/docs/14/hot-standby.html
  Focus on: the sentence that serializable is not available on a standby.
- **43.6.8 Trapping Errors** — https://www.postgresql.org/docs/14/plpgsql-control-structures.html
  Focus on: the tip on the cost of a block with EXCEPTION.
- **SAVEPOINT** — https://www.postgresql.org/docs/14/sql-savepoint.html
  Focus on: the examples of rolling back to a savepoint.
- **13.5 Serialization Failure Handling, current version 18** — https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html
  Focus on: which SQLSTATEs to retry, and why the server does not retry for you. The page does not exist in the PostgreSQL 14 docs. The research found it in the version 15 docs.
- **20.12 Lock Management** — https://www.postgresql.org/docs/14/runtime-config-locks.html
  Focus on: `deadlock_timeout` and the three `max_pred_locks_*` settings.
- **20.11 Client Connection Defaults** — https://www.postgresql.org/docs/14/runtime-config-client.html
  Focus on: `default_transaction_isolation`, `statement_timeout`, `lock_timeout`, `idle_in_transaction_session_timeout` and `idle_session_timeout`.
- **19.11 Client Connection Defaults, current version 18** — https://www.postgresql.org/docs/current/runtime-config-client.html
  Focus on: `transaction_timeout`, new in version 17.
- **19.4 Resource Consumption, current version 18** — https://www.postgresql.org/docs/current/runtime-config-resource.html
  Focus on: `subtransaction_buffers`, new in version 17.
- **20.8 Error Reporting and Logging** — https://www.postgresql.org/docs/14/runtime-config-logging.html
  Focus on: `log_lock_waits`.
- **5.5 System Columns** — https://www.postgresql.org/docs/14/ddl-system-columns.html
  Focus on: `xmin`, `xmax` and `ctid`.
- **70.6 Database Page Layout** — https://www.postgresql.org/docs/14/storage-page-layout.html
  Focus on: Table 70.4, the row version header, with `t_xmin`, `t_xmax` and `t_ctid`.
- **9.26 System Information Functions** — https://www.postgresql.org/docs/14/functions-info.html
  Focus on: Table 9.77, the snapshot components, and `pg_xact_status`, `pg_current_snapshot` and `pg_blocking_pids`.
- **SELECT, The Locking Clause** — https://www.postgresql.org/docs/14/sql-select.html
  Focus on: `NOWAIT` and `SKIP LOCKED`, and the warning on the inconsistent view.
- **SET TRANSACTION** — https://www.postgresql.org/docs/14/sql-set-transaction.html
  Focus on: `DEFERRABLE`.
- **28.2 The Statistics Collector** — https://www.postgresql.org/docs/14/monitoring-stats.html
  Focus on: Table 28.4, wait event types, and the `idle in transaction` state. Table 28.11 for the `transactionid` and `tuple` waits, Table 28.12 for `SubtransSLRU`, and 28.2.13 for `pg_stat_database.deadlocks`.
- **5.4 Constraints** — https://www.postgresql.org/docs/14/ddl-constraints.html
  Focus on: the note that CHECK constraints see only the row being checked.
- **CREATE SEQUENCE** — https://www.postgresql.org/docs/14/sql-createsequence.html
  Focus on: the note that `nextval` is never rolled back, which is why outbox ids arrive out of commit order.
- **3.4 Transactions, tutorial** — https://www.postgresql.org/docs/14/tutorial-transactions.html
  Focus on: the all-or-nothing paragraph. It takes two minutes.
- **70.1 Database File Layout** — https://www.postgresql.org/docs/14/storage-file-layout.html
  Focus on: the `pg_xact` row.
- **Appendix A, Error Codes** — https://www.postgresql.org/docs/14/errcodes-appendix.html
  Focus on: class 40, Transaction Rollback.
- **PostgreSQL 12.4 release notes, 2020-08-13** — https://www.postgresql.org/docs/release/12.4/
  Focus on: "Fix conflict-checking anomalies in SERIALIZABLE isolation mode".

### PostgreSQL source, tag REL_14_24

- **heapam_visibility.c** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/access/heap/heapam_visibility.c
  Focus on: `HeapTupleSatisfiesMVCC` from line 937, the visibility rule of section 3.2.
- **snapshot.h** — https://github.com/postgres/postgres/blob/REL_14_24/src/include/utils/snapshot.h
  Focus on: lines 157 to 169, the snapshot fields.
- **nodeModifyTable.c** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/executor/nodeModifyTable.c
  Focus on: line 2006 in `ExecUpdate`, the 40001 of first-updater-wins.
- **predicate.c** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/storage/lmgr/predicate.c
  Focus on: lines 4125 to 4127 for the message and hint, and the reason codes around lines 4821 and 4880.
- **lmgr README** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/storage/lmgr/README
  Focus on: lines 340 to 360, the timer. Lines 518 to 524, soft cycles. Lines 553 to 555, the victim.
- **README-SSI** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/storage/lmgr/README-SSI
  Focus on: the overview of SSI in PostgreSQL by its authors. Read it after Ports and Grittner, for the details the paper leaves out.
- **deadlock.c** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/storage/lmgr/deadlock.c
  Focus on: `DeadLockReport`, lines 1089 to 1153.
- **lmgr.c** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/storage/lmgr/lmgr.c
  Focus on: `XactLockTableInsert` at lines 585 to 600, the wait at line 668, and the context text at line 831.
- **postgres.c** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/tcop/postgres.c
  Focus on: line 1046, the 25P02 message, and `IsTransactionExitStmt` at lines 2752 to 2765.
- **executor README** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/executor/README
  Focus on: "EvalPlanQual (READ COMMITTED Update Checking)", lines 311 to 345.
- **README.tuplock** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/access/heap/README.tuplock
  Focus on: lines 14 to 37, the tuple lock and the steps of a row wait.
- **proc.c** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/storage/lmgr/proc.c
  Focus on: lines 1516 to 1631, the `log_lock_waits` lines.
- **nbtinsert.c** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/access/nbtree/nbtinsert.c
  Focus on: line 224, the wait of a unique insert, line 636, the SSI check, and line 665, the 23505 message.
- **proc.h and subtrans.h** — https://github.com/postgres/postgres/blob/REL_14_24/src/include/storage/proc.h
  Focus on: `PGPROC_MAX_CACHED_SUBXIDS` at line 36. `NUM_SUBTRANS_BUFFERS` is at line 15 of https://github.com/postgres/postgres/blob/REL_14_24/src/include/access/subtrans.h
- **snapmgr.c** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/utils/time/snapmgr.c
  Focus on: `XidInMVCCSnapshot` from line 2259, and the `suboverflowed` branch.
- **vacuumlazy.c** — https://github.com/postgres/postgres/blob/REL_14_24/src/backend/access/heap/vacuumlazy.c
  Focus on: line 1656, the "cannot be removed yet" line with its oldest xmin.
- **Commit e620a38c, "Avoid update conflict out serialization anomalies.", 2020-06-11** — https://github.com/postgres/postgres/commit/e620a38c23b9f7338d93ffd4c51bacc31973ac35
  Focus on: the commit message, with "Reported-By: Kyle Kingsbury", and the new isolation test `update-conflict-out.spec`.

### Independent analyses and test suites

- **Jepsen: PostgreSQL 12.3, Kyle Kingsbury, 2020-06-12** — https://jepsen.io/analyses/postgresql-12.3
  Focus on: section 3.1 for repeatable read as snapshot isolation, section 3.2 for G2-item under serializable, and section 4. Read it after E5, in about 25 minutes.
- **Jepsen: Amazon RDS for PostgreSQL 17.4, Kyle Kingsbury, 2025-04-29, updated 2025-05-03** — https://jepsen.io/analyses/amazon-rds-for-postgresql-17.4
  Focus on: section 1, the update on the cause, and section 4 for the Long Fork cycle. Section 5 gives the advice to use the writer endpoint. Multi-AZ clusters, no faults injected, every version from 13.15 to 17.4. With about 150 write and 1,600 read-only transactions per second, cycles appeared "every few minutes". Jepsen did not observe the cycle in standard PostgreSQL at REPEATABLE READ.
- **Understanding transaction visibility in PostgreSQL clusters with read replicas, Sergey Melnik, AWS Database Blog, 2025-05-02** — https://aws.amazon.com/blogs/database/understanding-transaction-visibility-in-postgresql-clusters-with-read-replicas/
  Focus on: "Understanding the Long Fork behavior", the ProcArray and the WAL order. Then the proposed fix with commit sequence numbers. AWS's position, read beside Jepsen's. AWS says "the visibility order of transactions doesn't always match their logged commit order", and that it "affects all isolation levels". The order differs "between the primary and replicas in cluster configurations". The issue "isn't present in Single-AZ PostgreSQL deployments". Both posts can be true, because they describe different setups. That reading is inferred, and a test with one self-managed replica would confirm it.
- **Hermitage, Martin Kleppmann** — https://github.com/ept/hermitage
  Focus on: the README table, and `postgres.md`. It has two-session psql scripts for "Lost Update (P4)", "Write Skew (G2-item)" and "Anti-Dependency Cycles (G2)". Run on PostgreSQL 9.3.5. You can paste the scripts into two psql windows.
- **Hermitage: Testing the "I" in ACID, Martin Kleppmann, 2014-11-25** — https://martin.kleppmann.com/2014/11/25/hermitage-testing-the-i-in-acid.html
  Focus on: why the level names of different databases do not match. It takes ten minutes.

### The transactional outbox

- **Pattern: Transactional outbox, Chris Richardson, microservices.io** — https://microservices.io/patterns/data/transactional-outbox.html
  Focus on: the solution, the at-least-once note, and the two relay patterns, log tailing and polling. The page has no date.
- **Outbox Event Router, Debezium 3.7 documentation** — https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html
  Focus on: the default table columns, and the rule that only INSERTs are expected. Then the event id header for removing duplicates. The page gives no numbers.
- **Transactional outbox pattern, SeatGeek Data Platform team, 2025-02-07** — https://chairnerd.seatgeek.com/transactional-outbox-pattern/
  Focus on: `pg_logical_emit_message()` in place of an outbox table, and Debezium heartbeats. It reports a load test without numbers.
- **Capturing every change from Shopify's sharded monolith, John Martin and Adam Bellemare, Shopify, 2021-03-12** — https://shopify.engineering/capturing-every-change-shopify-sharded-monolith
  Focus on: the p99 and the throughput of a log-reading relay. It is change data capture of MySQL, not an outbox on PostgreSQL.

### The client library

- **psycopg 3, Errors** — https://www.psycopg.org/psycopg3/docs/api/errors.html
  Focus on: `SerializationFailure`, `DeadlockDetected`, `Error.sqlstate` and the `Diagnostic` fields the labs print.
- **psycopg 3, Transactions management** — https://www.psycopg.org/psycopg3/docs/basic/transactions.html
  Focus on: autocommit and how the labs send BEGIN and COMMIT themselves.

### A talk

- **Transactions: myths, surprises and opportunities, Martin Kleppmann, Strange Loop 2015** — https://www.youtube.com/watch?v=5ZjhNTM8XU8
  Focus on: read skew at 0:15:00, write skew with an on-call example at 0:18:40, two-phase locking at 0:21:53, and serializable snapshot isolation at 0:25:45. The times come from YouTube's chapter marks and its machine captions, correct to about 10 seconds. The captions are not his exact words, so do not quote them.

---

## Cheatsheet

```
LEVELS, POSTGRESQL 14 (default READ COMMITTED)
  READ COMMITTED     snapshot per statement. Allows lost update, read skew,
                     write skew, phantoms
  REPEATABLE READ    one snapshot per transaction = snapshot isolation.
                     Stops lost update (40001), read skew, phantom re-reads.
                     Allows write skew, phantom decisions, read-only anomaly.
                     Reports that must match a serial order: SERIALIZABLE
                     READ ONLY DEFERRABLE
  SERIALIZABLE       SSI = SI + rw-antidependency checks. Stops all of them
                     with 40001. Adds no lock waits. Protects only SER txns:
                     mixed with other levels it acts as REPEATABLE READ.
                     Not on a hot standby
  MySQL InnoDB       its default "repeatable read" allows lost update (Hermitage)

READ COMMITTED RE-CHECK (EvalPlanQual)
  after a row-lock wait, re-runs the WHERE on the new version of THAT row only.
  Subqueries, joins, aggregates keep the old snapshot. Safe one-statement fix:
  the condition reads only columns of the row it changes

ROW VERSIONS AND SNAPSHOTS
  xmin   inserting xid      xmax   deleting or locking xid, 0 if none
  ctid   (page, line pointer). UPDATE = new version, old one keeps xmax
  snapshot xmin:xmax:xip    visible = writer committed before the snapshot
                                      AND replacer did not

ANOMALIES (Berenson et al. 1995)
  P4  lost update   r1[x] .. w2[x] .. w1[x] .. c1
  A5A read skew     r1[x] .. w2[x] .. w2[y] .. c2 .. r1[y]
  A5B write skew    r1[x] .. r2[y] .. w1[y] .. w2[x] .. c1 and c2
  phantom           decide on a set by condition, add a row to that set

ERRORS
  40001  could not serialize access due to concurrent update         RR, SER
  40001  could not serialize access due to read/write dependencies
         among transactions    HINT: The transaction might succeed if retried.
  40P01  deadlock detected     DETAIL: Process %d waits for %s on %s;
                               blocked by process %d.
  25P02  current transaction is aborted, commands ignored until end of
         transaction block
  55P03  NOWAIT: could not obtain lock on row in relation "%s"

DEFAULTS (docs 20.8, 20.11, 20.12)
  deadlock_timeout 1s    log_lock_waits off    lock_timeout 0
  statement_timeout 0    idle_in_transaction_session_timeout 0
  idle_session_timeout 0 (new in 14)   transaction_timeout 0 (new in 17)
  set per role or SET LOCAL, not in postgresql.conf
  max_pred_locks_per_transaction 64, per_relation -2 = 64/2 = 32, per_page 2
  full predicate lock table: ERROR out of shared memory, HINT increase
  max_pred_locks_per_transaction

LOCK WAITS AT WORK
  pg_stat_activity  wait_event_type Lock: transactionid = waits for the row's
                    writer, tuple = queued behind another waiter (not FIFO)
  pg_blocking_pids(pid)   pg_locks.waitstart (new in 14)
  pg_stat_database.deadlocks
  log_lock_waits on: "process %d still waiting for %s on %s after %ld.%03d ms"
  multixact in xmax: several lockers, often FK KEY SHARE + NO KEY UPDATE

SUBTRANSACTIONS
  SAVEPOINT, PL/pgSQL EXCEPTION, psql ON_ERROR_ROLLBACK, ORM nested txns.
  > 64 per backend: snapshots suboverflowed, lookups read pg_subtrans
  (32 SLRU pages in 14, subtransaction_buffers in 17). Wait: SubtransSLRU
  aborted txn accepts COMMIT (= ROLLBACK), ROLLBACK, ROLLBACK TO SAVEPOINT,
  PREPARE TRANSACTION

DEADLOCK
  check after deadlock_timeout. Victim: usually the first waiter to check
  fix: one lock order (SELECT ... ORDER BY key FOR UPDATE), retry 40P01

RETRY
  whole transaction from BEGIN, COMMIT inside the loop, only 40001 and 40P01,
  capped attempts with jitter, no side effects inside the body

FIXES
  scope first   read and write in ONE transaction, or no level helps (ACIDRain)
  lost update   UPDATE .. SET x = x - n WHERE .. AND x >= n   (READ COMMITTED)
  at most one   UNIQUE index, partial if needed: 23505 at every level,
                or 40001 first at SERIALIZABLE
  upsert        INSERT .. ON CONFLICT DO UPDATE, atomic, no savepoint.
                RR and SER: 40001 if the snapshot misses the row
  write skew    SERIALIZABLE + retry, or one parent row updated conditionally
  phantom       same. FOR UPDATE cannot lock rows that do not exist yet
  queue claim   UPDATE .. WHERE id = (SELECT .. FOR UPDATE SKIP LOCKED) RETURNING id
  lease         lease_until on claim, reaper requeues expired, owner check
                on completion, attempts cap. Partial index WHERE queued
  long txn      holds the cleanup horizon: queue claims slow down
  outbox        event row in the change's transaction. Relay: WHERE sent_at
                IS NULL FOR UPDATE SKIP LOCKED. Or xid8 cursor below
                pg_snapshot_xmin. Consumer: processed_events ON CONFLICT
  name lock     pg_advisory_xact_lock(key), not the session form

CONTENTION
  optimistic attempts = 1 / (1 - p)     p 0.5 -> 2, p 0.9 -> 10
  n workers, one row, one commit per round: n (n + 1) / 2 attempts

SSI COST (Ports and Grittner 2012, PostgreSQL 9.1, 2012 hardware)
  CPU +10 to 20% (SIBENCH)   5% slower in memory (DBT-2++)
  same as SI disk-bound, failures < 0.25%    RUBiS 435 / 422 / 208 req/s
```

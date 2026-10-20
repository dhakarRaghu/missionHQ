### What you must know

- Inside one transaction, a plain read blocks no writer, so another commit can change the facts you decided on. Name an anomaly, the level that stops it, and the transaction your ORM really opens.

- A writer that finds a row locked waits for its holder, then re-checks its condition on that row only. Write safe one-statement fixes, and read lock waits in PostgreSQL and on RDS.

- SERIALIZABLE, the strictest level, adds no lock waits and cancels one transaction, so your code must run it again. Retry correctly, and keep savepoints off busy paths.

- A unique index or a counter row holds a rule at every level, but a row lock misses rows not yet written. Pick a constraint, a lock or a version check, and know which locks a pooler breaks.

- A claim or an event that must outlive COMMIT needs an expiry time or an unsent flag, not a lock. Build a leased claim and a relay that never skips, and give both what a dashboard needs.

In Phase 2 an UPDATE wrote a new version of the row and kept the old one. This lesson gives the reason, and shows what two sessions can do to each other through those versions.

The running case is the course's task queue on PostgreSQL 17. Workers claim tasks in tq_tasks, humans approve some in tq_approvals, and every change writes an event into tq_outbox. tq_budget holds each tenant's credits, where a tenant is a customer account such as acme. tq_oncall lists the approvers, and at least one must be on call. Alice and Bob are both on call and open the same screen at once. Its transaction counts the approvers on call, and if the count is at least 2, sets its own user off call.

time | Alice's transaction | Bob's transaction

t1 | BEGIN, count on call: 2 | BEGIN

t2 |  | count on call: 2

t3 | UPDATE alice off call | UPDATE bob off call

t4 | COMMIT: ok | COMMIT: ok

after | 0 approvers on call, at the default settings

No statement raised an error, and no session waited. This lesson shows which setting allowed it, and which setting or code change stops it.

The same kind of gap appears in a managed database. An analysis by Jepsen, an independent database testing project, of Amazon RDS for PostgreSQL 17.4 found Long Fork cycles in Multi-AZ clusters. The test read through a primary and a reader endpoint, with no faults injected. In a Long Fork, two readers see two independent writes in opposite orders. So those clusters did not give one consistent snapshot across their endpoints. AWS answered that a replica makes commits visible in the order of the write-ahead log, while the primary uses its own order. So the effect needs a replica. The decision for your code is the analysis's advice: a read that must agree with your own writes goes to the writer endpoint.

Go deeper: the rates, the versions, and what each side claims
The cycles appeared every few minutes at about 150 write and 1,600 read-only transactions per second, in every version from 13.15 to 17.4. The same analysis did not see the cycle in standard PostgreSQL at REPEATABLE READ. AWS says the effect touches all isolation levels in cluster setups, and that Single-AZ deployments do not have it. Replicas are the subject of this course's Phase 5, and its section 5.1 returns to this case, so this lesson stays on one server. Both positions can be true, because they describe different setups. That reading is inferred, and a test with one self-managed replica would confirm it. This course did not check what AWS's own documentation promised before these posts.

This lesson describes PostgreSQL 17, from the source tag REL_17_11. Every default, view, message and source line is the 17 one. PostgreSQL 14 reaches its end of life on 2026-11-12, by the PostgreSQL versioning page. Where 14 behaved differently and you may still meet it, one clause says so. Where 18 differs, one line says so.

Evidence
The on-call case comes from Cahill, Röhm and Fekete, SIGMOD 2008, Example 1, where the rows are doctors on duty. Ports and Grittner, VLDB 2012, retell it with Alice and Bob, who count first and then update. This lesson uses that order, with approvers in place of doctors. The managed-database case is Jepsen's analysis "Amazon RDS for PostgreSQL 17.4", published 2025-04-29 and updated 2025-05-03, and the AWS Database Blog answer of 2025-05-02. The end-of-life date is from the PostgreSQL versioning page.

## What this lesson builds on

- The write path, from Phase 1. A commit is durable once its commit record is on stable storage in the WAL, the write-ahead log. Phase 1 also showed group commit, where one flush of the WAL covers several commits at once.

- The heap and the TID, from Phase 2. A table's rows sit in a heap of 8 kB pages, and a TID, a page and line number, names one row version.

- Check-then-act, from elite-performance Phase 4. Code checks a value, the value changes, then code acts, so a concurrency test must choose the order of steps.

Phase 4 covers vacuum, the cleanup of old row versions, freezing, and schema-change locks. Phase 5 of this course covers replicas, backups and connection pooling. Course 5 covers transactions across services. So this lesson stays on one server. Other courses teach three related topics, and this lesson links to them without teaching them again. The queues course, Phase 5, and the Kafka course, Phase 6, teach the outbox pattern and change data capture. The Redis course, Phase 3, teaches fencing tokens. The sql-mysql course, Phase 2, teaches InnoDB's row versions, gap locks and locking in MySQL.

## Why did both approvers commit without an error?

Atomicity and isolation are two promises, and the approvers needed the second one.

A transaction, the statements between BEGIN and COMMIT, makes two promises. Atomicity means that after a crash or a ROLLBACK, every change is there or none is. Isolation covers transactions running at the same time, and its strongest form matches some one-at-a-time order. An isolation level is a weaker form, defined by the anomalies it allows, results no one-at-a-time order could produce. Each approver's transaction was atomic, so the rule broke through isolation.

 | Atomicity | Isolation

protects from | a crash, an error or a ROLLBACK in the middle | other transactions running at the same time

the promise | all changes or none | as if each ran alone, at the level you chose

PostgreSQL's mechanism | one commit record in the WAL, one status entry per transaction in pg_xact | row versions and snapshots, row locks, and SERIALIZABLE's checks

breaks when | the client cannot tell whether COMMIT happened | two correct transactions produce a wrong result

Predict: three pairs from the task queue. Which break at READ COMMITTED, the default, and which at REPEATABLE READ?
One: two workers each read acme's 100 credits, check 100 against 80, and write 20. Two: the approvers. Three: two workers each count 0 running tasks for acme and each start one, with a limit of 1.

All three break at READ COMMITTED. REPEATABLE READ stops only the first, because only there do both transactions write the same row. Pairs two and three write different rows, so they pass REPEATABLE READ with no error. Most people expect it to stop all three, because the name sounds like full protection.

PostgreSQL keeps isolation with MVCC, multiversion concurrency control, so several versions of a row exist at once.

- A transaction that writes gets a transaction ID, an xid. Every row version it writes carries that ID in a header field, xmin.

- An UPDATE writes a new version and puts its xid into the old version's xmax, so the old one stays readable. That is why Phase 2 saw a new version on every UPDATE.

- At COMMIT, the server flushes one commit record to the WAL and records the outcome in pg_xact, the store of transaction statuses. All the transaction's versions become visible at that moment, and that is atomicity.

- A statement reads through a snapshot, a record of which transactions had finished when it was taken. It sees a version whose writer had committed and whose replacer had not.

- READ COMMITTED takes a new snapshot for each statement. REPEATABLE READ takes one at the first statement and keeps it.

- A snapshot takes no lock, so another transaction can change a row you read and commit before you write.

Here is one row after an UPDATE that has not committed yet. Transaction 700 wrote acme with 100 credits long ago. Transaction 801 runs UPDATE tq_budget SET credits = 20 WHERE tenant = 'acme' and is still open. t_ctid is the TID of the newer version, so the old version points to its replacement.

line pointer | credits | xmin | xmax | t_ctid | for snapshot 801:803:801

1 | 100 | 700 | 801 | (0,2) | writer 700 committed, replacer 801 still running: visible

2 | 20 | 801 | 0 | (0,2) | writer 801 still running: not visible

A snapshot has three parts, written xmin:xmax:xip_list. Its xmin is the lowest transaction ID still active, so every lower ID had finished. Its xmax is one past the highest completed ID, so every ID at or above it had not finished. The in-progress list names the IDs between the two that were still running. So the snapshot 801:803:801 sees 100. After 801 commits, a REPEATABLE READ transaction that took that snapshot earlier still sees 100, because it keeps its snapshot. A READ COMMITTED statement takes a new snapshot, for example 803:803:, counts 801 as finished, and sees 20.

Step 5 decides what a report of acme then beta sees while a transfer of 80 commits.

step | READ COMMITTED | REPEATABLE READ

report: SELECT acme | new snapshot: 100 | snapshot taken: 100

transfer: acme minus 80, beta plus 80, COMMIT |  |

report: SELECT beta | new snapshot: 180 | same snapshot: 100

report total | 280, never a real state | 200, a real state

This anomaly is read skew, where each read is correct and the total mixes two states. The approvers broke the rule through step 6, which neither lower level changes.

Atomicity has two gaps at its edges. ROLLBACK undoes rows and nothing else. A message sent to another service, or an HTTP call, inside a transaction stays sent when the transaction rolls back. The outbox at the end of this lesson fixes that. And if the connection drops while COMMIT runs, the client does not know whether the transaction committed. Sending it again can apply it twice. pg_xact_status(xid8) returns "in progress", "committed" or "aborted" for a recent transaction ID. So a client that saved its xid before COMMIT can ask afterwards. In practice, few applications save the xid. The common defense is an idempotency key, a unique key that the client sends with the write, so a second attempt inserts 0 rows. The constraint section shows the unique index that enforces such a key.

Where your code opens a transaction. Before you choose a level, find the transaction, because no level protects a read and a write that run in two transactions. An ORM, an object-relational mapper such as Django or Rails' Active Record, turns your model objects into SQL. It also decides where BEGIN and COMMIT go. Autocommit is the mode in which every statement is its own transaction. Here is what the common defaults do.

Library | Default | What it means for this lesson

Django | autocommit: "Each query is immediately committed to the database, unless a transaction is active" | a read in one ORM call and a write in the next are two transactions, so no level can protect the check-then-act

Django | ATOMIC_REQUESTS = True wraps each request in one transaction | the scope is now the whole request, including any slow call inside the view

Django | select_for_update() outside atomic() | raises TransactionManagementError, "because the rows are not locked in that case"

Rails | a nested transaction joins the outer one | ActiveRecord::Rollback raised inside it issues no ROLLBACK, and the outer transaction commits both blocks' rows. requires_new: true makes a savepoint instead

psycopg 3 | not autocommit: "By default even a simple SELECT will start a transaction" | a script that reads and then waits leaves the session idle in transaction, which the next section shows

So in a Django view, a read and a write that must agree belong in one atomic() block. Nest a second atomic() only when you will catch an error inside it. Each nested block is a savepoint, and the savepoint section later shows what one costs on a busy server. The labs open every connection with autocommit=True and send BEGIN and COMMIT themselves, so you see every transaction boundary in their output.

To see these rules on your server, run psql -h /tmp -p 5432 -d storage_lab -c "show default_transaction_isolation" -c "select pg_current_xact_id()" -c "select pg_current_xact_id()". You should see read committed and two different IDs, because each statement ran in its own transaction. Then add -c "begin" -c "select pg_current_xact_id_if_assigned()" before the two SELECTs. The new SELECT returns NULL, because the transaction has only a virtual ID until its first write. The two IDs after it are the same.

Next, watch the row versions. Run psql -h /tmp -p 5432 -d storage_lab -c "create table p3_demo (k text primary key, v int)" -c "insert into p3_demo values ('acme', 100)" -c "select xmin, xmax, ctid, * from p3_demo" -c "update p3_demo set v = 20" -c "select xmin, xmax, ctid, * from p3_demo" -c "select pg_current_snapshot()" -c "drop table p3_demo". Then look for the ctid moving, for example from (0,1) to (0,2), and for xmin changing to the ID of the UPDATE's transaction.

The approvers' rule broke through a snapshot that showed a fixed state. The next section shows what else that fixed state leaves out, and what it costs to hold one open.

Go deeper: IDs, the visibility rule in the source, hint bits, level tables, and other engines
How PostgreSQL makes a transaction atomic. You can read a transaction's ID with pg_current_xact_id(). Until its first write, a transaction has only a virtual ID, which never reaches a data page. Calling pg_current_xact_id() assigns a real ID, and pg_current_xact_id_if_assigned() does not. The docs call t_xmin the "insert XID stamp". pg_xact is the "Subdirectory containing transaction commit status data". A reader decides about each version by asking whether its xid committed, so all versions of one transaction become visible at the same moment.

After a ROLLBACK or a crash, the versions stay in the table. Every reader finds their xid aborted, or never committed, and skips them. The comment in the visibility code says "it must have aborted or crashed", and the function returns false. So PostgreSQL needs no undo pass for table rows. The ARIES design of Phase 1 needs one, because its restart undoes the changes of transactions that never committed. Rogov confirms it for PostgreSQL 14: on ROLLBACK, "no actual data rollback is happening". The skipped versions take space until vacuum removes them in Phase 4.

The fields on each version. xmin is the ID of the inserting transaction, and "each update of a row creates a new row version for the same logical row". xmax is the ID of the deleting transaction, "or zero for an undeleted row version". It can be set on a version that is still visible. The docs give two cases: the deleter has not committed yet, or its deletion was rolled back. t_ctid is the "current TID of this or newer row version", so the versions of one row form a chain. The fixed header is "23 bytes on most machines", and every version pays it. A DELETE only marks the version as deleted.

The one exception to "new index entries on every UPDATE" is a heap-only tuple update from Phase 2. It needs no new index entries when no indexed column changes and the page has free space. The link between that rule and the visibility rule is inferred.

The visibility rule, exactly. A version is visible when two things hold. Its xmin is the reader's own transaction, or a transaction the snapshot counts as finished that committed. Its xmax is zero, or belongs to a transaction that aborted, or that the snapshot counts as unfinished. A SELECT ... FOR UPDATE also writes its ID into xmax, but only as a lock, and such an xmax never hides the version. The source checks HEAP_XMAX_IS_LOCKED_ONLY for that case. XidInMVCCSnapshot answers whether an ID was unfinished for this snapshot, and TransactionIdDidCommit looks the outcome up in pg_xact. The docs' example of a snapshot's text form is 10:20:10,14,15, and pg_current_snapshot() returns the current one.

/* src/backend/access/heap/heapam_visibility.c, HeapTupleSatisfiesMVCC(), REL_17_11.
   Lines 1054 to 1065, then 1120 to 1129. Copied from the source, cut at ... */
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

Hint bits. SetHintBits stores the outcome in the version's header, so later readers skip the pg_xact lookup. It does not set them while the writer still counts as running for the reader. The first readers after a bulk load set them, so a plain SELECT can leave "a trail of dirtied pages in the buffer cache". Setting a hint bit can also write WAL. XLogHintBitIsNeeded() is true when data checksums or wal_log_hints are on, and then XLogSaveBufferForHint can log a full-page image. PostgreSQL 17's initdb leaves checksums off unless you pass -k. PostgreSQL 18 turns them on by default. Inferred from the code: only the first hint change to a page after a checkpoint writes the image. Check it with pg_waldump after a SELECT on a fresh bulk load.

Sharing one snapshot. pg_export_snapshot() returns an ID, and another REPEATABLE READ transaction adopts it with SET TRANSACTION SNAPSHOT before its first statement. Parallel pg_dump uses this, so all its processes read one state. At REPEATABLE READ the snapshot is taken at "the start of the first non-transaction-control statement", so BEGIN does not take it and the first SELECT or UPDATE does.

How the SQL standard defines the levels. It defines four levels. The docs list four phenomena that the levels prohibit. The standard names the first three, and the docs add the fourth. A dirty read sees another transaction's uncommitted data. A nonrepeatable read finds a row changed and committed since the first read. A phantom read finds a different set of rows for the same search condition. A serialization anomaly is a result that no one-at-a-time order produces. PostgreSQL 14, 17 and 18 give the same table.

Level | Dirty read | Nonrepeatable read | Phantom read | Serialization anomaly

Read uncommitted | allowed, but not in PG | possible | possible | possible

Read committed, the default | not possible | possible | possible | possible

Repeatable read | not possible | not possible | allowed, but not in PG | possible

Serializable | not possible | not possible | not possible | not possible

PostgreSQL's READ UNCOMMITTED behaves like READ COMMITTED, so PostgreSQL has three real levels. The table has no row for the opening case. Lost updates and write skew both fall inside "serialization anomaly". Berenson and five co-authors named the standard's three phenomena P1, P2 and P3, and showed that they miss other anomalies. Two of those are the lost update, P4, and write skew, A5B. Read skew is A5A, the history r1[x]...w2[x]...w2[y]...c2...r1[y]. A history is the order of reads r, writes w and commits c of numbered transactions. Read skew is not possible under snapshot isolation.

A worked answer on atomicity. A transfer moves 80 credits from acme to beta with two UPDATEs, and both rows start at 100. If the server crashes after the first UPDATE, both hold 100 after recovery, because the commit record never reached the WAL. A report that runs one SELECT sum(credits) while the transfer is open never sees 120. It reads one snapshot, and an uncommitted debit is never visible in PostgreSQL, at any level, so the sum is 200.

Other engines store versions differently, and use the names differently.

Engine | Protocol | Where versions live | Cleanup | Index entries point to

PostgreSQL | MV-2PL/MV-TO | append-only: each version is a whole row in the table | vacuum | the physical version

MySQL InnoDB | MV-2PL | delta: the row is overwritten, and changed values are copied to a delta area | vacuum | the logical row

Oracle | MV2PL | delta | vacuum | the logical row

Append-only storage with physical pointers is why each PostgreSQL index needs a new entry for a new version. MySQL InnoDB's default "repeatable read" allows the lost update, which PostgreSQL's "repeatable read" prevents. So code that relies on PostgreSQL's 40001 at that level can lose updates on MySQL. Hermitage linked the MySQL 5.7 manual, and its README does not state the MySQL version it tested. Jepsen then checked MySQL 8.0.34, and its summary says that "MySQL’s Repeatable Read still allows G2-item, G-single, and lost update". G2-item is write skew. MySQL 8.4 keeps REPEATABLE READ as its default, by this course's currency research, which read the MySQL 8.4 manual's isolation page.

InnoDB keeps old versions in undo logs. Its form of the long-snapshot cost of the next section is the history list length, the count of undo records that purge cannot remove yet. Shopify reported it past 1 million in about 15 minutes during a Vitess VDiff, by this course's companies research, which read the post with a summarising fetch. The sql-mysql course, Phase 2, teaches InnoDB's read views and gap locks.

Writers still wait for writers. MVCC removes waits between readers and writers: "reading never blocks writing and writing never blocks reading". An UPDATE that finds the newest version replaced by a transaction still in progress still waits for it. The lock-wait section below covers that wait.

Evidence
The two promises: PostgreSQL 17 tutorial, section 3.4, a transaction "bundles multiple steps into a single, all-or-nothing operation" and its updates "become visible simultaneously". IDs: PostgreSQL 17 docs 9.27, and Rogov, "PostgreSQL 14 Internals", section 3.6, page 75. t_xmin: docs 65.6, Table 65.4. pg_xact: docs 65.1. No undo: heapam_visibility.c line 1061 at REL_17_11, and Rogov page 72. Header fields: docs 5.6 and 65.6. Snapshot parts: docs 9.27, Table 9.83, and snapshot.h lines 157 to 169 at REL_17_11. Lock-only xmax: heapam_visibility.c line 1080. Hint bits: comment at lines 937 to 957, and Rogov page 71. Hint-bit WAL: xlog.h line 118 and bufmgr.c line 5140 at REL_17_11, and initdb.c line 167 at REL_17_11 and REL_18_6. Snapshot export: Rogov section 4.7, pages 90 and 91. When each level takes its snapshot: docs 13.2.1 and 13.2.2. The level table: docs 13.2, Table 13.1, and 19.11 for the default. Anomaly names: Berenson, Bernstein, Gray, Melton, E. O'Neil and P. O'Neil, "A Critique of ANSI SQL Isolation Levels", SIGMOD 1995, sections 4.1 and 4.2, Table 4 and Remark 9. REPEATABLE READ as snapshot isolation: docs 13.2.2, and Jepsen "PostgreSQL 12.3", section 3.1. The engine table: CMU 15-445, Fall 2025, lecture 20, slide 33. MySQL: Hermitage README, and Jepsen "MySQL 8.0.34", 2023-12-19. Shopify's history list length: a 2024 post, from the companies research. ORM defaults: Django 5.2 docs "Managing database transactions" and the QuerySet reference, the Rails API page DatabaseStatements, and psycopg 3 "Transactions management".

## What does an old snapshot miss, and what does holding one cost?

A snapshot shows the database as it was when the snapshot was taken, and it takes no lock to do that. So everything that happens after that moment is outside it. In the task queue, the on-call screen, a worker waiting on a model call and a long report each hold a snapshot. Each one can decide from a state that has moved on. Five limits follow from the snapshot rule.

- Commits after it was taken. A REPEATABLE READ transaction keeps reading the old state, by design. The docs show a read-only transaction that sees a batch marked complete without one of its detail records.

- Rows that concurrent transactions insert. A transaction decides that no such row exists, another transaction inserts one and commits, and the decision does not change.

- Writes to what it read. Nothing stops another writer from changing a row you read, so a decision made on the old value is then out of date.

- Its own cost. Vacuum cannot remove a replaced version while an open snapshot may still need it. Phase 4 calls the oldest such snapshot the cleanup horizon.

- DDL that replaces the table's file. TRUNCATE and the table-rewriting forms of ALTER TABLE "are not MVCC-safe", so an old snapshot can see such a table as empty.

Limits 2 and 3 are where the predict pairs break, and the next section names those anomalies. This section covers limits 4 and 5, because each one fails at work with no error message.

One snapshot held for minutes or hours. A session runs BEGIN, then waits for a user or a slow call, and keeps its snapshot all that time. The docs say that "an open transaction prevents vacuuming away recently-dead tuples that may be visible only to this transaction". A recently-dead tuple is a replaced version that some open snapshot might still need. The docs add that "remaining idle for a long time can contribute to table bloat". In pg_stat_activity, the view of every session, such a session shows the state idle in transaction. You meet it in three forms in the code you write.

- psycopg 3 without autocommit. Its docs warn that even a plain SELECT starts a transaction. So a worker that reads a row and then calls a model API for 20 seconds is idle in transaction for those 20 seconds.

- An async ORM session held across an await. A handler opens a session, reads, runs await llm(...), then writes, so the transaction is open across the call. That form is inferred from the psycopg rule above.

- A migration or replication tool. A tool that holds transactions open for its own reasons holds the horizon for the whole server. The Go deeper box below has one such case.

What you see is not a wait. A session in the state idle in transaction waits on Client / ClientRead, the wait event of a server that waits for the client's next command. A healthy idle session shows the same wait. AWS's page for Client:ClientRead names an idle-in-transaction connection as one cause of that wait. So on a wait-event chart, such as RDS Database Insights, it looks like a slow client, not like a lock. It shows by its state and age in this query, and in its effects: dead tuples that rise, and scans that slow down. The query runs on any version.

-- The sessions that hold back vacuum, oldest snapshot first.
SELECT pid, state, now() - xact_start AS xact_age, age(backend_xmin) AS xmin_age,
       wait_event_type, wait_event, left(query, 60) AS last_query
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY age(backend_xmin) DESC
LIMIT 5;

The decision is to end such sessions and to keep slow calls out of transactions. The setting idle_in_transaction_session_timeout ends a session that sits idle inside a transaction, and its default is 0, which means off. OpenAI's post on running ChatGPT on one PostgreSQL primary says they set it, so idle transactions do not block autovacuum. The queue sections at the end show what one open snapshot does to a busy queue table.

A TRUNCATE that an old snapshot cannot see. After a TRUNCATE commits, the table "will appear empty to concurrent transactions, if they are using a snapshot taken before the DDL command committed". The docs also give the boundary. A transaction that already read the table holds an ACCESS SHARE lock on it, so the TRUNCATE waits for that transaction. So the risk is a transaction that reads one table, and only later reads a table that a job truncated in between.

session | ddl_snapshot.py --ddl truncate, expected and not run

R | BEGIN ISOLATION LEVEL REPEATABLE READ

R | SELECT count(*) FROM tq_ds_other, and the snapshot is taken here

J | BEGIN, TRUNCATE tq_ds_target, INSERT the same 3 rows, COMMIT

R | SELECT count(*) FROM tq_ds_target returns 0, with no error

result | the table had 3 rows when R's snapshot was taken, and has 3 now

The cause is the new file. TRUNCATE gives the table a new, empty file, and the reloaded rows carry J's transaction ID, which R's snapshot cannot see. A type change such as ALTER COLUMN v TYPE bigint copies every row into a new file the same way. So R also counts 0 after it. DELETE only sets xmax on the old versions, so after a DELETE and reload R still counts 3. The explanation is inferred from the source, and the result is the docs' own statement.

You meet it in a nightly job that reloads a lookup table with TRUNCATE and INSERT. Meanwhile a long report runs at REPEATABLE READ and reads tables one by one. A migration tool that rewrites a table, such as a column type change, has the same effect on such readers. The decision is to reload with DELETE and INSERT in one transaction when readers may hold old snapshots. DELETE leaves dead versions for vacuum, and that is the price of the safety. E18 runs TRUNCATE, DELETE and the rewrite against one old snapshot.

Limits 2 and 3 remain, and the next section shows the three predict pairs breaking through them.

Go deeper: a migration tool's outage, pg_dump, and TRUNCATE CASCADE
A migration tool that held the horizon. Retool's first upgrade attempt used Azure DMS. DMS held transactions open, blocked autovacuum, and dead tuples piled up until Retool's cloud had an outage. Retool now monitors unvacuumed tuple counts.

The rewrite in the source. The table-rewriting ALTER copies rows with table_tuple_insert in ATRewriteTable. Both DDL forms give the table a new file. TRUNCATE's new file is empty, and the rewrite copies every row into its new file under the new transaction's ID. Either way the old snapshot finds no row it can see. That is inferred from the source.

pg_dump. pg_dump also reads every table in one snapshot. It locks its tables early in the run, so a TRUNCATE after that point waits for it. Whether a TRUNCATE can commit between its snapshot and its locks was not checked here.

A second TRUNCATE trap. TRUNCATE ... CASCADE empties every table that has a foreign key to the target, which has nothing to do with snapshots. Linear ran TRUNCATE TABLE <new_table> CASCADE in a migration, and it emptied tables with live data. Caching hid the loss for about 30 minutes. Linear's change afterwards: no production user has the TRUNCATE privilege.

Evidence
The long snapshot: PostgreSQL 17 docs 19.11, which also give the timeout default. psycopg 3 docs, "Transactions management". The query: pg_stat_activity.backend_xmin, system_views.sql line 885 at REL_17_11. OpenAI's post of 2026, read from a web archive copy, and Retool's post of 2022: this course's companies research, cases 1 and 5, each read with a summarising fetch. DDL that is not MVCC-safe: PostgreSQL 17 docs 13.6, "Caveats". The rewrite: tablecmds.c line 6339 at REL_17_11. Linear's migration of 2024-01-24: read by the companies research with a summarising fetch.

## Which anomaly is it, and which level stops it?

The three predict pairs break through limits 2 and 3, and all three are check-then-act between two sessions. Where the second write lands names the anomaly.

anomaly | what both read | what each writes | first level that stops it

lost update | one row | that same row | REPEATABLE READ

write skew | a set of rows | a different row of that set | SERIALIZABLE only

phantom | a set defined by a condition | a new member of that set | SERIALIZABLE only

- A lost update is pair one. At READ COMMITTED the second worker waits for the first one's row lock, then writes 20 again, so 160 credits are spent from 100.

- At REPEATABLE READ the second worker cannot change a row version that a concurrent transaction replaced. It gets ERROR 40001: could not serialize access due to concurrent update. This course calls the rule first-updater-wins.

- Write skew is the approvers. Each read the other's row and wrote its own, so no row was written twice and both commit at REPEATABLE READ.

- A phantom is pair three. Each worker decided that no task was running, then added a row to that empty set, so acme ends with 2 running tasks.

Here is pair one step by step at both levels, the expected output of lost_update.py --strategy naive, not run by the author yet.

step | READ COMMITTED | REPEATABLE READ

T1 SELECT credits | 100 | 100

T2 SELECT credits | 100 | 100

T1 UPDATE credits = 20 | 1 row, row locked | 1 row, row locked

T2 UPDATE credits = 20 | waits for T1 | waits for T1

T1 COMMIT | ok | ok

T2, after the wait | 1 row: writes 20 | ERROR 40001

T2 COMMIT | ok | ROLLBACK

result | 160 spent from 100, BROKEN | 80 spent, credits 20, holds

So REPEATABLE READ is PostgreSQL's form of snapshot isolation, one snapshot per transaction plus first-updater-wins. A CHECK constraint cannot hold the approvers' rule either. "At least one row has on_call true" is a statement about several rows, and a CHECK sees only the row being checked.

So PostgreSQL's "repeatable read" is not the repeatable read of a locking database. The two are incomparable, because each allows an anomaly that the other forbids. Snapshot isolation allows write skew, which locking repeatable read forbids. Locking repeatable read allows a re-read that finds new rows, which snapshot isolation forbids. Jepsen's PostgreSQL 12.3 histories at repeatable read were "consistent with strong snapshot isolation".

The two forms of phantom. The first form is the phantom read, a re-read that finds new rows. One transaction runs the same count twice, and another inserts a matching row in between. phantom.py --case reread is expected to print counts 2 and 3 at READ COMMITTED, and 2 and 2 at REPEATABLE READ, because the snapshot does not change. That is why the docs' level table marks the phantom read at REPEATABLE READ as "allowed, but not in PG". The second form is the running limit, and the snapshot does not help there.

phantom.py --case limit, REPEATABLE READ, expected | result

W1 SELECT count(*) running for acme | 0

W2 SELECT count(*) running for acme | 0

W1 UPDATE task 7 SET state = 'running' | 1 row

W2 UPDATE task 8 SET state = 'running' | 1 row, no wait, another row

W1 COMMIT, then W2 COMMIT | ok, ok

2 running tasks for acme, the limit is 1 | BROKEN

The natural fix, SELECT ... FOR UPDATE before the count, fails here. The constraint section's predict asks why, and gives fixes that work at READ COMMITTED.

Check the scope before the level. If the read and the write do not run in one transaction, no level protects the decision. A Django view in autocommit mode does this, and so does a read in one request and a write in the next. One audit of 12 self-hosted shop applications, which together run on over 2M websites, found 22 attacks. All 22 work under the default isolation of popular databases. And 17 of them work "even under the strongest transactional guarantees", because of incorrect transaction usage, so no setting fixes them. A scope check can also run in production. GitHub groups its tables in "schema domains" and runs a transaction linter that blocks a transaction across domains, by this course's companies research.

How the lab fixes the order of steps. Each pair runs in the lab with two psycopg connections, and a third connection watches pg_stat_activity and pg_blocking_pids(). So the script knows that a session waits for a lock before it takes the next step. This is the rule of elite-performance Phase 4, applied to a database: the test chooses the order.

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

A test without this check can pass because the two sessions never overlapped. The wait event type Lock means the backend waits for a heavyweight lock. A heavyweight lock lives in PostgreSQL's lock manager, and table locks and transaction ID locks are of this kind. pg_blocking_pids lists the sessions that block it.

How you find an anomaly in production. None of these anomalies raises an error or writes a log line, so the broken state is the only trace. The check that finds one is a query for the broken state, run by a job every few minutes and alerted on. Here are the invariants of the course's schema as such queries, and each returns the rows that break its rule.

-- Run from a job every few minutes. Any row is an alert.
-- at most 1 running task per tenant, pair 3
SELECT tenant, count(*) FROM tq_tasks WHERE state = 'running' GROUP BY tenant HAVING count(*) > 1;
-- one decision per task, the approval of the queue sections
SELECT task_id, count(*) FROM tq_approvals GROUP BY task_id HAVING count(*) > 1;
-- at least 1 approver on call, pair 2
SELECT 'nobody on call' WHERE NOT EXISTS (SELECT 1 FROM tq_oncall WHERE on_call);

A lost update from pair one leaves no row to find, because the balance looks valid. Its check compares two records of the same fact, such as the budget against the sum of the spends in a ledger table. The course's schema has no ledger, so that query is a design note. In tests, Jepsen uses a checker named Elle, which reads the history of many transactions and searches it for these cycles. A query job finds the damage after it happens, and Elle finds the cause before release.

REPEATABLE READ stops two writes to one row, and only SERIALIZABLE stops the rest.

Setting REPEATABLE READ everywhere leaves write skew and phantoms passing with no error.

Run uv run python phase03_transactions/mvcc_model.py and find the write-skew row.

The lost update showed a second worker that waited and then wrote, and the next section explains what it checks after that wait.

Go deeper: the histories, the whole matrix, phantom reads and the read-only anomaly
The whole matrix. The course's model of these rules predicts this matrix, with its rows for the atomic spend, read skew and a deadlock. It was not run against a server by the author yet.

history | READ COMMITTED | REPEATABLE READ | SERIALIZABLE

lost-update | BROKEN | holds, T2 40001 | holds, T2 40001

lost-update-atomic | holds | holds, T2 40001 | holds, T2 40001

write-skew | BROKEN | BROKEN | holds, T2 40001

phantom-limit | BROKEN | BROKEN | holds, T2 40001

read-skew | BROKEN | holds | holds

deadlock | holds, T2 40P01 | holds, T2 40P01 | holds, T2 40P01

mvcc_model.py is a small pure-Python model of the visibility rule and of first-updater-wins. Its self-test asserts the matrix above, then removes one rule at a time and asserts that the matrix changes. It agrees with Hermitage's PostgreSQL rows, P4, G-single, G2-item and G2, and with the snapshot isolation rules. Its limits are in its docstring. One matters here: it puts one predicate lock on the whole table for every scan, as PostgreSQL does for a sequential scan. A predicate lock is SERIALIZABLE's record of what a transaction read. Try uv run python phase03_transactions/mvcc_model.py --history write-skew --level serializable --trace and find the line where one transaction is doomed.

The histories by name. The lost update is P4, written r1[x]...w2[x]...w1[x]...c1. Write skew is A5B, written r1[x]...r2[y]...w1[y]...w2[x]...(c1 and c2 occur). Its history H5 has numbers. The rule is x + y > 0, and both start at 50. Each transaction reads both, sees a sum of 100, and subtracts 90 from a different one. Both commit, and x + y = −80. Snapshot isolation allows A5B and forbids P4 and A5A. The phantom has the same shape with hours: both transactions see 7 of 8 hours booked, and each adds 1.

Hermitage, a test suite by Martin Kleppmann, uses the names of Atul Adya's work. G-single is read skew, G2-item is write skew on rows, and G2 is the form with a search condition. Its table marks G2-item and G2 as possible at "repeatable read" and prevented at "serializable" in PostgreSQL. Three more of its columns are G1a, G1b and G1c: aborted reads, intermediate reads and circular information flow, three forms of dirty read. The table also has columns for G0, OTV and PMP. Hermitage marks all three as prevented at PostgreSQL's "read committed", because a snapshot never shows a write that has not committed.

Why the lost update looks like this. The docs give the READ COMMITTED rule: after the first updater commits, the second "will attempt to apply its operation to the updated version of the row". Its WHERE clause, tenant = 'acme', still matches, so it writes 20 from an old read. At REPEATABLE READ the transaction "will be rolled back with the message" ERROR: could not serialize access due to concurrent update. Its SQLSTATE 40001 is serialization_failure. The check raises the error only when the level is REPEATABLE READ or SERIALIZABLE, and PostgreSQL 17 raises the same message for MERGE. The papers name the same idea first-committer-wins. PostgreSQL applies it when the second writer tries the write, not at its commit. The docs then say to "abort the current transaction and retry the whole transaction from the beginning". The retry reads 20, sees that 20 is less than 80, and refuses the spend.

A similar case: two concurrent withdraw(99) calls against a balance of 100 both pass, and 198 leaves the account.

Write skew in the lab. At REPEATABLE READ the expected output is two successful COMMITs and RESULT: BROKEN. 0 approver(s) on call, not run by the author yet. The docs state the CHECK limit: "PostgreSQL does not support CHECK constraints that reference table data other than the new or updated row being checked." A unique index holds rules of the form "at most one", and "at least one" is not of that form. The docs also warn about this level: "Attempts to enforce business rules by transactions running at this isolation level are not likely to work correctly without careful use of explicit locks to block conflicting transactions."

The read-only anomaly. Snapshot isolation allows one more anomaly, and the transaction that sees it writes nothing. Snapshot isolation allows only two anomalies: write skew, and this one. Three REPEATABLE READ transactions run on Bob's accounts, 900 and 100.

- T1 adds 1% of Bob's total to account 2. It reads 900 + 100 and stays open.

- T2 takes 100 from account 3 and commits, so account 3 is now 0.

- T3 is read-only. Its snapshot includes T2 and not T1.

- T1 commits, so account 2 is now 910.

- T3 reads Bob's accounts as 900 and 0.

T1 read account 3 before T2 changed it, so T1 must come before T2 in any serial order. T3 saw T2 without T1, so no one-at-a-time order matches what T3 saw. Each transaction alone was correct. The docs say that at this level "read-only transactions will never have serialization conflicts", which is why this anomaly raises no error. The docs' batch example has the same shape. That match is inferred, because the docs do not name the anomaly. The SERIALIZABLE section shows how that level catches it.

The audit, in full. The audit tool read the SQL traces of the 12 applications in four languages. The opening case of that work is the Flexcoin Bitcoin exchange. An attacker sent thousands of simultaneous requests and moved coins until the sending account was overdrawn. All stored Bitcoins were stolen, so the exchange shut down.

Evidence
Histories and names: Berenson and others, SIGMOD 1995, sections 4.1 and 4.2, H4, H5 and Table 4. Hermitage README and postgres.md, run on PostgreSQL 9.3.5. The READ COMMITTED and REPEATABLE READ rules and quotes: PostgreSQL 17 docs, sections 13.2.1 and 13.2.2. The 40001 check: the TM_Updated branch of ExecUpdate, nodeModifyTable.c line 2408 with the message at line 2417, at REL_17_11, under IsolationUsesXactSnapshot(). The MERGE copy: lines 3173 to 3184. The CHECK limit: docs 5.5. The read-only anomaly: Rogov, pages 55 to 58, PostgreSQL 14. Wait types: docs 27.2, Table 27.4, and 9.27. The withdraw example: ACIDRain, Figure 1, from the study note. Scope: Warszawski and Bailis, "ACIDRain", SIGMOD 2017, introduction and section 2. Flexcoin's attack was on 2014-03-02. The schema-domain linter is case 10 of the companies research, from GitHub's engineering blog of 2021. Elle: Jepsen's MySQL 8.0.34 analysis. No lab output on this page was run by the author.

## What does READ COMMITTED re-check after a wait?

One statement fixes a lost update at the default level, but only on one row.

The lost update broke because the second worker wrote a value it had computed from an old read. The fix moves the arithmetic and the check into the UPDATE. A writer that finds the row locked waits for the holder to end. Then READ COMMITTED runs the statement's conditions again on the newest version of that row, a re-check that PostgreSQL calls EvalPlanQual.

Wrong: the value comes from an earlier read.

UPDATE tq_budget SET credits = %s WHERE tenant = 'acme'

Right: the check runs on the locked version.

UPDATE tq_budget SET credits = credits - %s
WHERE tenant = 'acme' AND credits >= %s RETURNING credits

After the wait, 20 fails the check, so 0 rows change.

Predict: an interest UPDATE checks each client's total in a subquery. Does Bob get interest he should not?
It pays 1% to every client whose accounts total at least 1,000, with GROUP BY client HAVING sum(amount) >= 1000. Bob has 200 and 800. Another transaction takes 100 from the 800 account and commits while the UPDATE waits on that row.

Yes. The subquery saw 1,000, and the re-check ran only on the 800 account's columns. Bob ends with 202 and 707, so he got 9 of interest on 900.

- T2 finds the newest version of a row locked by T1, and sleeps until T1 ends.

- T1 commits, and T2 takes the version that T1 wrote.

- T2 runs the statement's conditions again, on that one version only. In an UPDATE, DELETE or MERGE, only the target table is handled this way.

- Every other table, join and subquery in the statement keeps the old snapshot.

- If the conditions still match, T2 updates the new version, and otherwise it reports 0 rows.

step | what happens

T1 BEGIN, UPDATE account 3 SET amount = amount - 100 | 800 becomes 700, not committed

T2 interest UPDATE | its subquery sees Bob's total 1,000, so he qualifies

T2 updates Bob's rows one by one | account 3 is locked by T1, so T2 waits

T1 COMMIT |

T2 re-checks account 3 only | updates it from 700

result | account 2 is 202, account 3 is 707, total 909

The docs describe the result from the outside. An updating command sees the effects of concurrent commands "on the same rows it is trying to update". But "it does not see effects of those commands on other rows in the database". They conclude: "This behavior makes Read Committed mode unsuitable for commands that involve complex search conditions". So the interest UPDATE is read skew inside one statement. At REPEATABLE READ the same UPDATE fails with 40001 instead, which a retry can absorb.

So a one-statement fix is safe at READ COMMITTED when its condition reads only columns of the row it changes. credits >= 80, state = 'queued' and running < max_running meet it. A subquery, a join or an aggregate over other rows does not, so use SERIALIZABLE, a lock taken first, or a constraint.

Where you meet it: a claim, an approval or a spend whose WHERE clause holds a count or a sum over other rows. What you see when it goes wrong is nothing at first. The statement succeeds, the error log stays empty, and Bob's 909 appears only when a commit lands during the wait. So the check is the invariant query job of the anomaly section, run against the rule the statement was meant to keep. The decision runs the other way too. "READ COMMITTED can never be made safe" is also a wrong belief. It leads to retry loops and 40001 handling where one statement was enough.

The re-check runs only after a wait, and the next section shows who waits for whom, and how you see it.

Go deeper: the README text, a row that starts to match, and functions that read
The design note. The executor README describes EvalPlanQual. "The basic idea in READ COMMITTED mode is to take the modified tuple committed by the concurrent transaction (after waiting for it to commit, if need be) and re-evaluate the query qualifications to see if it would still meet the quals." It adds the boundary: "In UPDATE/DELETE/MERGE, only the target relation needs to be handled this way." PostgreSQL 14 wrote "In UPDATE/DELETE", because MERGE came in 15. For the other relations, the executor uses "the same rows from these relations that were joined to the locked rows". The docs' own words for the result are that the command can "see an inconsistent snapshot", and Rogov's are that "different rows have been read from different snapshots".

A row that starts to match is not seen. The docs' own example uses a table website with two rows, hits 9 and 10. One session runs UPDATE website SET hits = hits + 1 and has not committed. Another runs DELETE FROM website WHERE hits = 10. "The DELETE will have no effect even though there is a website.hits = 10 row before and after the UPDATE." The DELETE skipped the row that held 9, because 9 did not match in its snapshot. It waited on the row that held 10, and then re-checked 11.

One more trap at this level. A query that calls a VOLATILE function which runs its own query can see data that does not match the main query.

The atomic spend, expected. The wrong and right forms are two entries of the lab's SQL table at phase03_transactions/lost_update.py:90. At READ COMMITTED the right form is expected to go like this, from the docs' rule, not run. T2 waits, then returns 0 rows, and the worker refuses the task. The balance is 20 after one spend.

Evidence
The re-check: the EvalPlanQual part of src/backend/executor/README at REL_17_11, from line 350, with the boundary at line 381 and the other relations at lines 386 to 390. The docs' rule, the inconsistent snapshot and the website example: PostgreSQL 17 docs, section 13.2.1. The interest example and the VOLATILE trap: Rogov, "PostgreSQL 14 Internals", pages 49 to 51 and 54, printed on PostgreSQL 14. The study note and the phase review found no production report of this boundary, so the evidence is documented behaviour, not a measured number.

## Who waits for whom, and how do you see it?

The re-check runs after a wait, so the wait decides who goes first and who fails. A row lock has two parts. The writer's xid goes into the row's xmax, so the lock lives on the page. The writer also holds an ExclusiveLock on its own xid until it ends. A second writer that finds the row marked requests a ShareLock on that xid and sleeps. ShareLock and ExclusiveLock are two of the eight heavyweight lock modes, and they conflict, so a row lock lasts until the holder's COMMIT or ROLLBACK.

Waiters for one hot row are not served in arrival order. A row lock lives in the row, so the server needs one more lock to order several waiters. A tuple lock is a heavyweight lock on one row version, named by its TID. Each writer of a locked row follows four steps.

- Take the tuple lock.

- Wait on the holder's xid, with the ShareLock above.

- Write its own xid into xmax.

- Release the tuple lock.

So the first waiter holds the tuple lock and waits on the xid, and every later waiter waits on the tuple lock. Here is how pg_stat_activity shows four sessions updating one row.

  pid  | wait_event_type |  wait_event   | pg_blocking_pids
-------+-----------------+---------------+------------------
 30723 | Client          | ClientRead    | {}
 30794 | Lock            | transactionid | {30723}
 30865 | Lock            | tuple         | {30794}
 30936 | Lock            | tuple         | {30794,30865}

The holder 30723 waits for its client, the first waiter waits on the holder's xid, and the two later waiters wait on the tuple lock. The order holds for the first hand-over only. When 30723 commits, 30794 gets the row and releases the tuple lock. At READ COMMITTED, 30865 and 30936 then find a new xmax and race for the row with no tuple lock. So under one hot row, a row that many sessions update at once, a writer can wait longer than its place in line suggests. At REPEATABLE READ the woken waiters fail with 40001 instead.

The wait graph has an edge from A to B when A waits for a lock that B holds. A deadlock is a cycle in that graph. Two transfers in opposite order make one: T1 updates acme, T2 updates beta, T2 updates acme, T1 updates beta.

- T2 waits for T1 for acme, from 0.00 s.

- T1 waits for T2 for beta, so the cycle closes.

- T2's timer fires after 1 s: 40P01, rollback.

- T1 commits The total stays 200.

- PostgreSQL does not search the wait graph at every wait, because the search costs time and most waits end sooner. A waiter sleeps with a timer of deadlock_timeout, 1 second by default.

- If the lock is not granted by then, that waiter runs the deadlock check. The first waiter's timer fires first, so the detecting waiter is usually the victim.

- The victim gets SQLSTATE 40P01, deadlock_detected, and its transaction rolls back. The docs say not to rely on which one is chosen.

- The fix is one lock order, so a cycle cannot form. Lock both rows first with SELECT tenant FROM tq_budget WHERE tenant IN ('acme', 'beta') ORDER BY tenant FOR UPDATE. Retry 40P01 as well, for orders you cannot control.

The victim's error reads as the wait graph, one edge per DETAIL line. For this lab it should look like the lines below. The numbers are an example, and the lab was not run.

ERROR 40P01: deadlock detected
      DETAIL: Process 41022 waits for ShareLock on transaction 901; blocked by process 41018.
              Process 41018 waits for ShareLock on transaction 902; blocked by process 41022.
      HINT: See server log for query details.
      CONTEXT: while updating tuple (0,1) in relation "tq_budget"

The process numbers are backend process IDs, which pg_stat_activity.pid shows. The transaction numbers are the IDs each process waits for, and the CONTEXT line names the row the victim wanted. The queries themselves are only in the server log, which is why the HINT points there. Raising deadlock_timeout removes no cycle, and every victim then waits longer before its error.

How lock trouble looks at work. The lab watches sessions it started. At work, you see the same waits as rows in views and as lines in the log.

Signal | Where | What it tells you

wait_event_type Lock, with wait_event | pg_stat_activity | transactionid: waits for a row's writer to end. tuple: waits behind another waiter for the same row. relation: waits for a table lock. object: waits for a lock on something that is not a table, such as the NOTIFY lock of the next section

pg_wait_events, new in 17 | a view | the type, name and description of every wait event, to join with pg_stat_activity

pg_blocking_pids(pid) | a function | the sessions that block this one, including waiters ahead of it. A prepared transaction shows as process 0

waitstart | pg_locks | "Time when the server process started waiting for this lock"

deadlocks | pg_stat_database | "Number of deadlocks detected in this database"

the log lines below | the server log | each lock wait longer than deadlock_timeout, when log_lock_waits = on

The same waits on RDS and Aurora. Database Insights shows database load in average active sessions, collected every second and split by wait event. It names a wait as type and name, so the two row-lock waits appear as Lock:transactionid and Lock:tuple. AWS has a page for each, for both RDS for PostgreSQL and Aurora PostgreSQL.

AWS name | What AWS says it means | Causes AWS lists | In this lesson

Lock:transactionid | "a transaction is waiting for a row-level lock" | "A highly concurrent workload contends for the same rows", idle in transaction, long-running transactions | the first waiter above

Lock:tuple | "a backend is waiting to acquire a lock on a tuple while another backend holds a conflicting lock on the same tuple" | many sessions updating one row, SELECT ... FOR UPDATE on one row, pools that open more sessions | the later waiters above

The Lock:transactionid page adds a foreign-key case. A SELECT … FOR KEY SHARE lock "can block INSERT, UPDATE, and DELETE commands on other tables that reference the row". The Lock:tuple page advises idle_in_transaction_session_timeout. The Lock:transactionid page advises "Turn on autocommit wherever possible". Read that with the scope rule of the anomaly section in mind. Autocommit ends the waits, and it also removes the transaction that a check-then-act needs, so fix the scope first and then shorten it.

Here is the "who blocks whom" query to keep. Start from the session that blocks others and waits for nobody, which is often idle in transaction with the largest xact_s.

-- from phase03_transactions/lockwatch.py, WHO_BLOCKS. Copied. At work, drop the pid filter
SELECT a.pid,
       pg_blocking_pids(a.pid)            AS blocked_by,
       a.wait_event_type, a.wait_event, a.state,
       round(extract(epoch FROM now() - a.xact_start)::numeric, 1) AS xact_s,
       left(a.query, 50)                  AS query
FROM pg_stat_activity a
WHERE a.pid = ANY(%s)
ORDER BY a.xact_start

Two more queries complete the set on PostgreSQL 17. The first joins the new view, so each wait comes with the server's own description. The second lists every lock wait, oldest first.

-- The waits of every active session, counted, with descriptions. PostgreSQL 17.
SELECT a.wait_event_type, a.wait_event, count(*) AS sessions, w.description
FROM pg_stat_activity a
LEFT JOIN pg_wait_events w ON w.type = a.wait_event_type AND w.name = a.wait_event
WHERE a.state <> 'idle' AND a.wait_event IS NOT NULL
GROUP BY 1, 2, 4 ORDER BY 3 DESC;

-- Every lock wait, oldest first, with what it waits for and who blocks it.
SELECT l.pid, l.locktype, l.mode, l.relation::regclass AS rel, l.transactionid,
       now() - l.waitstart AS waited, pg_blocking_pids(l.pid) AS blocked_by
FROM pg_locks l
WHERE NOT l.granted
ORDER BY l.waitstart;

Run them when something is stuck, not every second, because pg_blocking_pids needs "exclusive access to the lock manager's shared state for a short time". With log_lock_waits = on, a wait longer than deadlock_timeout writes a LOG line in one of these forms.

process %d still waiting for %s on %s after %ld.%03d ms
process %d acquired %s on %s after %ld.%03d ms
process %d detected deadlock while waiting for %s on %s after %ld.%03d ms
process %d avoided deadlock for %s on %s by rearranging queue order after %ld.%03d ms

For a row wait, the first %s is the mode, such as ShareLock, and the second names the lock, such as transaction 901. The "acquired" line gives the whole wait once it ends, and the last line is a cycle broken without an abort. log_lock_waits is off by default in 17, and it and deadlock_timeout are superuser settings. On RDS and Aurora you set them in a custom DB parameter group, because the default groups cannot be changed.

The timeouts that end long waits and idle sessions follow the same rule of scope. Set them per role with ALTER ROLE ... SET, or per transaction with SET LOCAL, as the claim check does. The Go deeper box lists each one with its default. That is this course's advice, and the docs point the same way. Setting statement_timeout or lock_timeout in postgresql.conf "is not recommended because it would affect all sessions". The 17 docs say the same of transaction_timeout. They also warn against idle_session_timeout on connections from "connection-pooling software", which "may not react well to unexpected connection closure".

A blocked writer waits for the holder's commit, then re-checks only that row.

A subquery or count in the WHERE clause decides on the old snapshot.

Run uv run python phase03_transactions/deadlock.py, then compare T2's wait with show deadlock_timeout.

Every wait so far was on a row that two writers both touch. The next section shows two locks that PostgreSQL takes for you, on rows and objects your code never names.

Go deeper: lock internals, the victim's exceptions, timeouts by version, table locks and MySQL
The two parts in the source. The docs say there is "no limit on the number of rows locked at one time", and that "locking a row might cause a disk write". XactLockTableInsert takes the lock on a transaction's own ID, and its comment says "The lock can then be used to wait for the transaction to finish". This wait stops a dirty write, P0, w1[x]...w2[x] before the first transaction ends, which every level should forbid. Hermitage's G0 test, "Write Cycles", shows PostgreSQL's read committed blocks the second write until the first commits. Phase 4 lists all eight heavyweight lock modes for tables.

Why the tuple lock exists. A wait on the xid alone "will release all waiters concurrently", which leads to "indefinite starvation of some waiters". After the first hand-over, "The queue has virtually fallen apart." lockwatch.py --case queue prints both pictures and the order it saw, in E13.

How the victim is chosen. If a deadlock exists, it "will be resolved, usually by aborting the detecting process' transaction". "If earlier waiters in the cycle have not yet run CheckDeadLock, then the first one to do so will be the victim." The default timeout is "one second (1s), which is probably about the smallest value you would want in practice". In the transfers, T2 waited first, so T2 is the expected victim, which is inferred from the README and not from a run. Three exceptions are in the source.

- Before it cancels anyone, the check tries to reorder wait queues, which breaks some cycles without an abort.

- Some waits fail at once, with no timer, when the new waiter and a waiter in the same lock's queue each need the other. The code is RememberSimpleDeadLock.

- An autovacuum worker that blocks the waiter is cancelled instead, unless it vacuums to prevent wraparound. The server logs "sending cancel to blocking autovacuum PID %d" only at the DEBUG1 level, so a default log does not show it.

The docs: "Exactly which transaction will be aborted is difficult to predict and should not be relied upon." In textbook terms, PostgreSQL detects deadlocks and does not prevent them. Detection builds the waits-for graph and breaks a cycle by choosing a victim. Prevention schemes, such as wait-die and wound-wait, abort a transaction by priority before a cycle can form. deadlock_timeout sets the trade-off between the cost of checks and the time until a deadlock is broken. At the default, each deadlock costs the victim at least 1 second of waiting and a full retry of its transaction, which is inferred from the timer rule.

Reading the report. The parts are the message deadlock detected, one DETAIL line per process, Process %d waits for %s on %s; blocked by process %d., and the HINT See server log for query details.. The server log adds one more line per process, Process %d: %s, with the text of its query. The CONTEXT line comes from the row wait, while updating tuple (%u,%u) in relation "%s". transaction %u is how DescribeLockTag names a transaction ID. Every lab session sets application_name to storage_lab, so you can find its pids. A printed PostgreSQL 14 example has the lines DETAIL: Process 30423 waits for ShareLock on transaction 122877; blocked by process 30723. and CONTEXT: while updating tuple (0,2) in relation "accounts".

# from phase03_transactions/deadlock.py:75, the SQL table. Copied
SQL = {
    "move": "UPDATE tq_budget SET credits = credits + %s WHERE tenant = %s",
    "lock_both": "SELECT tenant FROM tq_budget WHERE tenant IN ('acme', 'beta') ORDER BY tenant FOR UPDATE",
    "total": "SELECT sum(credits) FROM tq_budget",
}

With --ordered, T2's lock read waits for T1 at acme, the first row in the order. It holds nothing that T1 needs, so T1 finishes and T2 goes on. The docs' advice is to "acquire locks on multiple objects in a consistent order", and to retry the transactions "that abort due to deadlocks". run_with_retry treats 40P01 as retryable for that reason.

One order inside a statement, too. A single UPDATE locks its rows one by one, in the order its plan reads them, so two single statements can deadlock. One UPDATE accounts SET amount = inc_slow(amount) reads rows 1, 2 and 3 with a sequential scan. Another adds WHERE amount > 100.00 and, with sequential scans turned off, reads rows 3 and 2 through a descending index on amount. One of them gets ERROR: deadlock detected. Such deadlocks "do occur in high-load systems when batch row updates are performed". The fix is the same rule: lock first with SELECT ... ORDER BY id FOR UPDATE, then update. That fix is inferred, not run.

Settings that limit waits. Without a deadlock, a wait has no limit: a transaction "will wait indefinitely for conflicting locks to be released", so it is "a bad idea" to hold transactions open long.

Setting | Default | What it does | Exists since

deadlock_timeout | 1s | the wait before the deadlock check, and before a log_lock_waits line | before 14

log_lock_waits | off in 17 and 18 | logs each wait longer than deadlock_timeout | before 14. On by default in 19, by the 19 RC1 release notes

lock_timeout | 0, off | cancels a statement that waits longer for one lock | before 14

statement_timeout | 0, off | cancels a statement that runs longer | before 14

idle_in_transaction_session_timeout | 0, off | ends a session idle inside an open transaction | before 14

idle_session_timeout | 0, off | ends a session idle outside a transaction | 14, absent from the 13 docs

transaction_timeout | 0, off | ends a session whose transaction lasts longer | 17, absent from the 16 docs

log_lock_failures | off | logs a lock that NOWAIT could not get | new in 18, by the 18 release notes

Who may change the lock settings. deadlock_timeout and log_lock_waits are PGC_SUSET settings, so only superusers can change them. Since PostgreSQL 15, a superuser can give one role that right, with GRANT SET ON PARAMETER deadlock_timeout TO app_admin. Whether the rds_superuser role can SET them in a session was not checked.

Table locks. Every statement also locks each table it uses. A SELECT takes ACCESS SHARE, which "Conflicts with the ACCESS EXCLUSIVE lock mode only", and "Only an ACCESS EXCLUSIVE lock blocks a SELECT". A waiting request also blocks later requests that conflict with it. pg_blocking_pids reports this as a "soft block", by a session "ahead of it in the wait queue". Phase 4 builds its schema-change rules on these two facts.

Two limits of the views. Frequent calls to pg_blocking_pids "could have some impact on database performance". An empty wait_event does not prove that a session is not waiting. The view shows only the waits that the source code reports, and any other wait time is "unaccounted for".

The log lines, in full. Every line except the "acquired" line has a DETAIL in the log, Process holding the lock: %s. Wait queue: %s., which starts Processes holding the lock when several sessions hold it. A fifth form, process %d failed to acquire ..., covers a rare case. E13, with --log-lock-waits, makes the server write these lines to its log.

The MySQL contrast. When Meta moved from MySQL 5.6 to 8.0, deadlocks at REPEATABLE READ on insert ... on duplicate key became more likely. Lowering the isolation level fixed them. The reason is InnoDB's gap locks, which the sql-mysql course teaches in Phase 2.

Evidence
Row locks: PostgreSQL 17 docs 13.3.2, and lmgr.c lines 613 to 624 and 691 at REL_17_11. P0 and Remark 3: Berenson and others, 1995. The tuple-lock steps: README.tuplock, lines 14 to 37. The four-session output and the broken queue: Rogov, pages 219 and 220, PostgreSQL 14. The timer and the victim: lmgr README, lines 340 to 360, 518 to 524 and 553 to 555, and proc.c lines 1193 and 1463. Detection against prevention: CMU 15-445, Fall 2025, lecture 18 notes. The report: DeadLockReport, deadlock.c lines 1072 to 1135, the context text at lmgr.c line 854, and Rogov page 227. Deadlocks in one statement: Rogov, pages 228 to 230. Settings: docs 19.8, 19.11 and 19.12, guc_tables.c lines 2149 and 1514 at REL_17_11, and the release notes of 15, 18 and 19 RC1. Table locks and soft blocks: docs 13.3.1 and 9.27. Monitoring: docs Table 27.11, 9.27, 52.12 and 27.2.17, system_views.sql line 1376 for pg_wait_events, and Rogov page 244. Log formats: proc.c lines 1579 to 1627. AWS: the Aurora and RDS user guide pages for Lock:transactionid and Lock:tuple, and the Database Insights overview. Meta's move to MySQL 8.0: case 19 of the companies research, a post of 2021 read with a summarising fetch.

## What do foreign keys and NOTIFY lock for you?

The waits above came from rows that your code wrote, and two more locks come from statements that look harmless. A foreign key check locks the parent row, and a NOTIFY locks one object for the whole server at COMMIT. In the task queue, tq_tasks.tenant references tq_tenants, and a relay may be woken with NOTIFY, so both apply to it.

Four row-lock modes. A row lock comes in four modes, and X marks a conflict between a mode requested and a mode held.

Requested, held | FOR KEY SHARE | FOR SHARE | FOR NO KEY UPDATE | FOR UPDATE

FOR KEY SHARE |  |  |  | X

FOR SHARE |  |  | X | X

FOR NO KEY UPDATE |  | X | X | X

FOR UPDATE | X | X | X | X

An UPDATE takes FOR NO KEY UPDATE, unless it changes a column with a unique index that a foreign key can use. Then it takes FOR UPDATE, as every DELETE does. A foreign key check takes FOR KEY SHARE on the parent row. At REPEATABLE READ and SERIALIZABLE, "an error will be thrown if a row to be locked has changed since the transaction started". That is the 40001 again, now for SELECT ... FOR UPDATE.

Many lockers of one row make a multixact. xmax has room for one transaction ID. When several transactions hold compatible locks on one row, PostgreSQL stores a multixact ID there instead. A multixact is a group of transaction IDs with their lock modes, kept in pg_multixact. The course's own schema creates this case. Inserting a task for acme takes FOR KEY SHARE on acme's row in tq_tenants. The slot reservation of the constraint section updates that row with FOR NO KEY UPDATE. The table shows no conflict between the two, so neither waits, and the row's xmax becomes a multixact. That is inferred from the table, and lockwatch.py --case multixact, in E13, shows it. On PostgreSQL 17, pg_get_multixact_members(xmax) returns one row per member, with modes such as nokeyupd and keysh.

Multixacts never change. A new locker makes a new multixact with every old member plus itself. So n backends that share-lock one row make n − 1 multixacts and n(n + 1)/2 − 1 members. The members grow with the square of the lockers.

Lockers of one parent row, before any vacuum

Concurrent lockers n
Multixacts . Members .

Member space is "approximately 4 billion total members", because the member offset is 32 bits. Metronome ran out of it in production, on Aurora PostgreSQL, and published a root-cause analysis.

- The system. "an AWS Aurora PostgreSQL cluster exceeding 30TB in size running version 13.18".

- The trigger. A migration from a monolithic invoice table of nearly 10 TB to partitioned tables, with dual writes and a large backfill. Concurrent inserts that referenced the same parent rows through foreign keys created multixacts, as tq_tasks.tenant does here.

- The error. "This command would create a multixact with %u members, but the remaining space is only enough for %u member".

- Why the dashboards looked fine. Their alert watched multixact ID age against autovacuum_multixact_freeze_max_age of 400 million, and it showed under 50%. The post says "PostgreSQL does not expose metrics for member space consumption".

- Impact. Four write outages in one week, each over an hour. A failover to the standby restarted the running vacuums. Pausing the backfill job did not pause its queue consumers, so the load went on.

- Changes. Alerts on member and offset storage, more autovacuum workers, and an audit of foreign keys, "especially on low cardinality tables".

There is no view for member space on PostgreSQL 17, and these two queries come close. The second one's use for this is inferred from its column names, and whether Aurora reports a useful value there is not checked.

-- The age of the oldest multixact per database, the number most dashboards show.
SELECT datname, mxid_age(datminmxid) FROM pg_database ORDER BY 2 DESC;

-- The next member offset as of the last checkpoint. Sample it twice. The
-- difference is how many members the server made in between, out of 2^32.
SELECT next_multixact_id, next_multi_offset FROM pg_control_checkpoint();

On a self-managed server, the member files are in pg_multixact/members, so their size on disk is the direct signal. The decision follows from the formula. A hot parent row referenced by many concurrent inserts makes multixacts fast, such as a tenant row or a row of an enum-like table. Batch such inserts per parent. For a small enum-like table, a CHECK constraint on the value can replace the foreign key. A CHECK reads only the new row, so it locks no parent row. The cost is that the parent table is no longer the one list of allowed values.

NOTIFY takes one lock for the whole server at COMMIT. NOTIFY sends a message to sessions that ran LISTEN on a channel, and the messages are delivered only after the transaction commits. Recall.ai's post prints these lines from its production log, on a busy writer path that used NOTIFY, in this order. The log prefix is cut, and the wait queue is cut after three of its many entries.

LOG:  process 20841 acquired AccessExclusiveLock on object 0 of class 1262 of database 0 after 1015.921 ms
STATEMENT:  COMMIT
LOG:  process 61596 still waiting for AccessExclusiveLock on object 0 of class 1262 of database 0 after 1000.192 ms
DETAIL:  Process holding the lock: 20841. Wait queue: 17474, 20898, 1931, ...
STATEMENT:  COMMIT

Read it with the log formats of the section above. The waits are about 1,000 ms because deadlock_timeout was 1 s, so each line marks a wait that passed 1 s. The waiting statement is COMMIT. The lock is not on a table or a row: class 1262 is pg_database, and object 0 is no database.

The cause is in the commit path. To deliver messages in commit order, PreCommit_Notify takes AccessExclusiveLock on that object. Its comment says "Serialize writers by acquiring a special lock that we hold till after commit". CommitTransaction calls it before RecordTransactionCommit flushes the commit record. So the lock is held across the WAL flush, and the lock is taken even when no session listens.

Three writers commit, each with a NOTIFY

Step 1: W1 takes the NOTIFY lock and flushes its commit record, and W2 and W3 wait.

Step 2: W2 gets the lock only after W1's flush, so its flush cannot share W1's.

Step 3: W3 commits last, so one commit runs at a time for the whole server.

The order of steps from xact.c, an illustration and not measured. Without NOTIFY, the three flushes can overlap, and group commit lets one flush cover all three.

That the NOTIFY run cannot share flushes is inferred from the lock order, and E20 measures the shape. Recall.ai's case shows the scale.

- The workload. "tens of thousands of simultaneous writers", each a meeting bot.

- Impact. Three periods of downtime in four days.

- Symptoms. Database load and waiting sessions spiked, while CPU, disk I/O and network traffic all fell. A lock was the cause, and turning on log_lock_waits showed which one.

- Fix. They "decided to migrate away from LISTEN/NOTIFY" and moved the logic into the application.

What you see is Lock / object in pg_stat_activity. In pg_locks you see rows with locktype = 'object', classid = 1262, objid = 0 and granted = false. On RDS and Aurora the same wait is Lock:object, by the naming rule of the section above, which is inferred. The decision: do not send NOTIFY from many concurrent writers. To wake an outbox relay or a job worker, poll the table with the partial index of the outbox section. Or send NOTIFY from one process only. PostgreSQL 19 changes which listeners are woken, and its code still takes the same commit lock.

Both locks so far make writers wait or fail, and the next section shows the level that prevents write skew and adds no new lock waits.

Go deeper: member wraparound, the freeze clamp, an old bug report, and the PostgreSQL 19 changes
Multixact wraparound. Multixacts have their own wraparound, as transaction IDs do. The docs say the member storage "can grow up to about 20GB before reaching wraparound". When it "exceeds about 10GB", aggressive vacuum scans "will occur more often for all tables". An aggressive vacuum scans every page that is not already marked all-frozen, so that it can advance the table's oldest ID. Phase 4 teaches freezing for transaction IDs and multixacts, with settings such as vacuum_multixact_freeze_min_age.

Why Metronome's emergency vacuums began near 200 million IDs. The post reports it, and the source explains it, which is inferred and not run. When members pass half the space, the threshold MULTIXACT_MEMBER_SAFE_THRESHOLD applies, and MultiXactMemberFreezeThreshold lowers the effective freeze age below the number of multixacts in use. The member-limit error comes after the message multixact "members" limit exceeded. The post quotes Thomas Munro for the member formula. For 5 lockers it gives 4 multixacts and 5 × 6 / 2 − 1 = 14 members.

An old report of the same failure. pgsql-bugs #12990, on PostgreSQL 9.3.5, ran SELECT ... FOR SHARE on one row from 26 connections. The member files grew until the newest overtook the oldest. The server then raised ERROR: could not access status of transaction.

Members on 14. A printed pgrowlocks for the same pair of modes on PostgreSQL 14 shows multi as t and the modes {"Key Share","No Key Update"}. E13 explains why the course schema should print them in the reverse order.

PostgreSQL 19. PostgreSQL 19 RC1 makes multixact members 64-bit, by its release notes, and adds pg_get_multixact_stats(), so this limit moves far away. For NOTIFY, Recall.ai's post was updated to say that a PostgreSQL commit removed the problem. That commit is 282b1cde9, whose title is in the sources. It is in the 19 RC1 release notes as "Improve NOTIFY to only wake up backends that are listening to specified notifications". At REL_19_RC1, async.c line 1309 still takes the same commit lock. So 19 changes who is woken, and whether it also shortens the time under the lock is not checked.

Evidence
Row-lock modes: PostgreSQL 17 docs, Table 13.3 and section 13.3.2. Multixacts: docs 24.1.5.1, Rogov pages 213 and 214, and pgsql-bugs #12990 from 2015. Members: multixact.c lines 1902 to 1913 for the mode names, line 1771 for the sort, line 1362 for the member-limit error, line 215 and line 3144 for the threshold, and multixact.h line 30 for MaxMultiXactOffset, all at REL_17_11. Metronome: the root-cause analysis by Cosmo Wolfe, published 2025-05-20 and read in full. The outages were between 2025-05-10 and 2025-05-17. pg_control_checkpoint: the 17 docs 9.27. NOTIFY: async.c line 921 at REL_17_11, and xact.c lines 2289 and 2325. Recall.ai: "Postgres LISTEN/NOTIFY does not scale", Elliot Levin, published 2025-07-01 and updated 2026-05-08, read in full. The log sample is from 2025-03-22, and the downtime was between 2025-03-19 and 2025-03-22. PostgreSQL 19: the 19 RC1 release notes and async.c at REL_19_RC1.

## What does SERIALIZABLE add to stop write skew?

SERIALIZABLE watches who read what another wrote, and cancels one transaction.

Write skew passed REPEATABLE READ because the writes landed on different rows. PostgreSQL's SERIALIZABLE is SSI, serializable snapshot isolation, which adds one check to snapshot isolation. T1 rw→ T2, an rw-antidependency, means T1 read data that a concurrent T2 then wrote, so T1 must come first in any serial order. Two such edges in a row are the dangerous structure, and SSI cancels one transaction with 40001 when it sees one.

A: Alice's screen
read both, wrote alice

B: Bob's screen
read both, wrote bob

A rw→ B: A read bob, B wrote it

B rw→ A: B read alice, A wrote it

Two rw edges in a row. A and B are both pivots: each has an rw edge in and an rw edge out. Expected from the course's model, not run.

Predict: the approvers run at SERIALIZABLE, in the opening order. Does anyone wait, and who fails where?
Neither session waits, because the UPDATEs touch different rows and SSI's read records never block. B gets 40001 at its COMMIT, because A's commit marks B as doomed. The reason "during write" at B's UPDATE needs a committed transaction in the structure, so it would come only if A had committed before that UPDATE. On the retry its new snapshot shows Alice off call, so it counts 1 and Bob stays on call. Most people expect a lock wait, because "serializable" sounds like locking.

- Each read takes a SIREAD lock, PostgreSQL's name for a predicate lock: a record of what was read that never blocks anyone. pg_locks shows it with the mode SIReadLock.

- Both counts read both approver rows.

- A updates Alice's row, which B read, so B rw→ A. B updates Bob's row, which A read, so A rw→ B.

- When A commits, B sits in the middle with an edge to a committed transaction, so B cannot commit.

- B's COMMIT fails with the error below, and B runs again.

ERROR 40001: could not serialize access due to read/write dependencies among transactions
      DETAIL: Reason code: Canceled on identification as a pivot, during commit attempt.
      HINT: The transaction might succeed if retried.

The lab is expected to print the error in this form, and the lab was not run. The DETAIL line varies with the case, and the SQLSTATE never varies: serialization failures "always return with an SQLSTATE value of '40001'".

How many false alarms you get. SSI cancels some transactions that would have been fine, and four rules decide how many.

- Granularity. A SIREAD lock covers a tuple, a page or a whole table. B-tree index reads are locked at page level.

- Sequential scans. "A sequential scan will always necessitate a relation-level predicate lock." Every later write to that table then conflicts with the scan.

- Promotion. Too many fine locks are combined into coarse ones. max_pred_locks_per_page, default 2, is the number of rows on one page before the lock becomes a page lock. max_pred_locks_per_relation has the default −2, which means max_pred_locks_per_transaction divided by 2, so 64 / 2 = 32 pages or tuples of one table. Past that, the lock covers the table.

- Lifetime. SIREAD locks "often need to be kept past transaction commit, until overlapping read write transactions complete".

A vector index locks the whole index. Rule 1 depends on the index type. Each index type says whether it can take fine predicate locks, with the flag ampredlocks. B-tree, hash, GiST and GIN set it to true. pgvector's two index types, HNSW and IVFFlat, set it to false, so PostgreSQL falls back to the whole index.

- At every scan, the index scan start takes one SIREAD lock on the whole index.

- At every insert by a SERIALIZABLE transaction, index_insert checks for a conflict against the whole index. An insert at a lower level skips the check.

So a nearest-neighbour search at SERIALIZABLE conflicts with every concurrent insert into that index that a SERIALIZABLE transaction makes. An insert at READ COMMITTED or REPEATABLE READ creates no conflict. Two agents that each search their memory and then save one new memory form two rw edges, the dangerous structure above. One of them gets 40001, even when they never touch each other's rows. This follows from the code, and the 40001 rate it causes on a real workload is not measured here.

You meet it with agent memory or retrieval in PostgreSQL, under a SERIALIZABLE default for the whole application, which this section advises below. What you see is 40001 on transactions that search and write vectors, and SIReadLock rows in pg_locks with locktype relation on the vector index. The decision is to run the vector search outside the serializable transaction, at READ COMMITTED, and pass its result into the transaction as input. The search then decides nothing that the database must protect. E21 compares a B-tree read and an HNSW read in the same two-agent order. The retrieval-internals course teaches what the HNSW search returns, and this lesson adds only what it locks.

The cost comes as retries, not waits. On an auction-site workload, PostgreSQL 9.1 on one disk served these rates, where S2PL is classic locking.

snapshot isolation: 435 req/s, 0.004% failures

SSI: 422 req/s, 0.03% failures

S2PL locking: 208 req/s, 0.76% failures

SSI kept 97% of the throughput and locking kept 48%, so measure your own 40001 rate. S2PL, strict two-phase locking, holds every lock until commit, so readers and writers block each other.

Only serializable transactions are protected. The guarantee covers "any set of successfully committed concurrent Serializable transactions". A transaction at READ COMMITTED takes no SIREAD locks, so its reads form no edges. If Bob's screen ran at READ COMMITTED and Alice's at SERIALIZABLE, the pair could still break the rule. Mixed with other levels, Serializable "behaves as Repeatable Read without any notice". So set default_transaction_isolation for the whole application, not per screen.

Running SERIALIZABLE in production. The docs end their section with advice "For optimal performance when relying on Serializable transactions".

Advice | Why

"Declare transactions as READ ONLY when possible." | read-only transactions "will often be able to establish" at startup that they need no predicate locks

control the number of active connections, with a pool if needed | fewer concurrent transactions form fewer rw edges. Inferred

"Don't put more into a single transaction than needed for integrity purposes." | each read adds SIREAD locks, which can outlive the commit. Inferred from the lifetime rule

do not leave connections "idle in transaction" longer than needed | the docs name idle_in_transaction_session_timeout for it

remove FOR UPDATE, FOR SHARE and explicit locks that SSI made unneeded | they add waits that SSI does not need. Inferred

raise the max_pred_locks_* settings when page locks get combined into a table lock | combining can cause "an increase in the rate of serialization failures"

encourage index scans, by lowering random_page_cost or raising cpu_tuple_cost | "A sequential scan will always necessitate a relation-level predicate lock"

A long report has one more choice. BEGIN ISOLATION LEVEL SERIALIZABLE, READ ONLY, DEFERRABLE may wait for a safe snapshot at the start. After the wait it "cannot be aborted, and does not need to take SIREAD locks". The docs say the mode "is well suited for long-running reports or backups".

What you see, and what you do not. The server log records each failed statement, because log_min_error_statement defaults to error. pg_stat_database counts xact_rollback and deadlocks, but it has no counter for 40001. So the rate you need comes from the application. Count 40001 per transaction name, and count the retries that succeeded. A rate that grows with load means contention, which the constraint section measures. A rate that jumps after a deploy often means a new sequential scan, rule 2 above.

SERIALIZABLE turns write skew into a 40001, and the next section shows how the client must run the transaction again.

Go deeper: the pivot, the measured costs, deferrable reports, a past bug, and two errors
The pivot. A cycle of rw-antidependencies means that no serial order exists. Under snapshot isolation every cycle has two rw edges in a row, each between concurrent transactions, which is why watching the pair is enough. Watching for the two-edge structure is cheaper than searching for whole cycles. Snapshot isolation already handles the other kinds of dependency. Its snapshot shows a reader what committed before it, and first-updater-wins stops two writes to one row. When the write comes before the read, PostgreSQL needs no SIREAD lock. The reader finds a newer version whose xmin its snapshot hides, and records the edge from that. PostgreSQL also tries to cancel the pivot so that an immediate retry will not fail again with the same serialization failure. The documented exception is a prepared transaction in the structure.

The error, in the source. The source has ten reason-code lines, such as "during write" and "during commit attempt". A printed PostgreSQL 14 run of the same shape, two sums then two UPDATEs of different rows, shows exactly this DETAIL at the second COMMIT. So the line above is expected with good reason, but the lab was not run. SIREAD locks "do not cause any blocking and therefore can not play any part in causing a deadlock". The SSI lock manager stores only SIREAD locks, "and hence cannot block".

The vector index, in the source. B-tree sets ampredlocks true at nbtree.c line 118. HNSW sets it false at src/hnsw.c line 348, and IVFFlat at src/ivfflat.c line 265, on pgvector's master branch. index_beginscan_internal, the common code of index_beginscan and index_beginscan_bitmap, calls PredicateLockRelation on the index, and index_insert calls CheckForSerializableConflictIn for the whole index.

The measured costs, with their conditions. These are PostgreSQL 9.1 on the paper's hardware, and this course did not measure PostgreSQL 17.

Workload | Result | Conditions

SIBENCH, key-value pairs, half updates and half full scans | SSI used 10% to 20% more CPU than snapshot isolation | in memory, tmpfs, Core 2 Quad Q9550, 8 GB

DBT-2++, TPC-C-like with a "credit check" transaction, 25 warehouses | SSI 5% slower than snapshot isolation | in memory, 4 threads

DBT-2++, 150 warehouses, 19 GB | throughput "indistinguishable from that of SI", failures under 0.25% | disk-bound, 36 threads, 16-core Xeon E7310

deferrable read-only transactions in that run | median wait for a safe snapshot 1.98 s, 90% within 6 s, all within 20 s | 1,200 tries

RUBiS, auction site, 85% read-only, 6 GB | SI 435, SSI 422, S2PL 208 requests per second. Failures 0.004%, 0.03% and 0.76% | Core 2 Quad Q9550, 8 GB, one 7,200 RPM disk

Where the core's 97% and 48% come from. On RUBiS, 422 / 435 = 97% and 208 / 435 = 48%. Both numbers come from one machine. The RUBiS setup had 225,000 active auctions, 1 million completed ones and 1.35 million users, with several PHP application servers so the database was the limit. The SSI failure rate of 0.03% is about 1 retry in 3,300 transactions.

Deferrable reports, and the read-only anomaly. The wait in the table above is the price of a deferrable report. The mode also answers the read-only anomaly of the anomaly section. At SERIALIZABLE, that anomaly's three transactions end in the same 40001. With READ ONLY DEFERRABLE, the third transaction instead blocked until T1 committed, and then read 910 and 0. That is a state of the order T1, T2.

The guarantee depends on the implementation. A Jepsen test of PostgreSQL 12.3 under SERIALIZABLE found "six cases of G2-item" in two minutes, with no process crashes needed. Each one "involved at least one read-write conflict for a freshly inserted row". The cause was tuple versions attributed to the wrong transaction ID. The fix is commit e620a38c, "Avoid update conflict out serialization anomalies.", released in PostgreSQL 12.4. Hermitage did not catch this bug. The commit says "Backpatch: All supported versions". The isolation test that the commit added, update-conflict-out.spec, is in the REL_17_11 tree and in REL_14_24, so both carry the fix. An earlier version of this lesson said this was not checked in the source, and the test file settles it. A variant that cuts false aborts, PSSI, was argued for and not adopted, for its memory cost.

Two more errors belong to this level. When the predicate lock table is full, PostgreSQL 17 raises ERROR: out of shared memory with HINT: You might need to increase "max_pred_locks_per_transaction".. PostgreSQL 14 printed the setting name without the double quotes. And a replica refuses the level: serializable "is not yet available in hot standby", and setting it "will generate an error".

Try this now. Run uv run python phase03_transactions/write_skew.py --level serializable --retry --show-locks. Find the SIReadLock rows printed after the two counts, then the 40001 line, the statement it came from, and the retry's count.

Evidence
The dangerous structure and the pivot: Cahill, Röhm and Fekete, SIGMOD 2008, section 2.2, using a result of Fekete and others. SIREAD locks, safe snapshots, safe retry and costs: Ports and Grittner, "Serializable Snapshot Isolation in PostgreSQL", PVLDB 5(12), VLDB 2012, sections 4, 5.2, 5.4, 7.1 and 8.1 to 8.4, Figures 4 to 6, measured on 2012 hardware. The docs' rules, settings and advice: PostgreSQL 17 docs 13.2.3, 19.12 and SET TRANSACTION. The error text: predicate.c at REL_17_11, with the message at line 3991, its hint at 3993, two of the reason codes at 4657 and 4716, and the hint for a full lock table at 2469. pgvector: src/hnsw.c and src/ivfflat.c on master, fetched for the phase. The whole-index calls: indexam.c at REL_17_11, the scan lock at lines 319 and 320, and the insert check from line 225. The missing 40001 counter: system_views.sql, the definition of pg_stat_database, and guc_tables.c line 4890 for log_min_error_statement. Printed runs: Rogov, pages 59, 60 and 236. The bug: Jepsen "PostgreSQL 12.3", 2020-06-12, section 3.2, commit e620a38c of 2020-06-11, and the 12.4 release notes of 2020-08-13. The test file: src/test/isolation/specs/update-conflict-out.spec, run by isolation_schedule line 21. PSSI and the bug's cause: the study note. Hot standby: docs 26.4.

## How do you retry, and what can a savepoint rescue?

SERIALIZABLE turns write skew into a 40001, so the rule now holds only if the client retries correctly. After any error the transaction is aborted. PostgreSQL then accepts only COMMIT, ROLLBACK, ROLLBACK TO SAVEPOINT and PREPARE TRANSACTION. Every other statement gets 25P02, current transaction is aborted, and a COMMIT there replies ROLLBACK.

Wrong: send the failed statement again, and every attempt gets 25P02.

Right: ROLLBACK, BEGIN, and run the whole body, so a new snapshot shows the conflict's change.

What the docs say to retry. The PostgreSQL 17 docs say to "retry the whole transaction from the beginning". Since version 15, the docs have a section on this. In PostgreSQL 17 it is section 13.5, "Serialization Failure Handling".

Code | What the docs say | This course's rule

40001 serialization_failure | The error "will always have the SQLSTATE code 40001". Retry it "unconditionally" | always retry

40P01 deadlock_detected | "It may also be advisable to retry deadlock failures" | retry

23505 unique_violation, 23P01 exclusion_violation | In some cases a retry is right. An example: a client reads the stored keys and picks a new primary key, and another client picks the same key. "More care is needed when retrying these other error codes" | do not retry by default. Expect to see 23505 from a race

Two more rules from the same page. "It is important to retry the complete transaction, including all logic that decides which SQL to issue and/or which values to use."

And "PostgreSQL does not offer an automatic retry facility, since it cannot do so with any guarantee of correctness."

One rule from section 13.2.3. Data read in a serializable transaction should not be "considered valid until the transaction which read it has successfully committed".

Who retries for you. Mostly nobody, so check the library you use.

Library | Retries 40001?

psycopg 3 | no. It raises psycopg.errors.SerializationFailure, with sqlstate 40001

Django | no. Its transactions page describes no retry

Rails | no. allow_retry covers only connection errors, and "should only be enabled for known idempotent queries"

DBOS 2.31.0 | yes, for @DBOS.transaction. It retries 40001 and 40P01 with backoff from 1 ms, times 1.5, up to 2 s, with no attempt cap. It also retries a lost connection and the SQLSTATE classes 08, 53 and 57

Four rules make a retry safe. DBOS's retry differs from rule 4, because it has no cap and no jitter.

- Retry only 40001 and 40P01, because other errors, such as a CHECK violation, fail again the same way.

- Put COMMIT inside the loop, because at SERIALIZABLE COMMIT itself can fail with 40001, as in the approvers' case.

- Keep side effects out of the body, because an email or an HTTP call inside it happens once per attempt.

- Cap the attempts and wait a random time. The lab allows 5 attempts, and waits up to 10, 20, 40 and 80 ms before each retry. The random wait spreads transactions that failed together, so they do not collide again at the same moment.

The lab's helper follows the four rules, and keeps the wrong way behind a flag so its self-test can prove that it fails.

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

The common failure is SERIALIZABLE without the loop. A team switches default_transaction_isolation to serializable to stop write skew, and the anomalies stop. Users then see 40001 as server errors, because nothing retries them. In the measured runs that was under 0.25% of transactions in one test and 0.03% in another. Each one is a failed request until the loop exists.

A savepoint marks a point inside a transaction, and ROLLBACK TO SAVEPOINT undoes only the work after it. Drivers and ORMs use it to go on after one failed statement. It rescues a 23505 duplicate key on one insert, when the rest of the transaction is still valid. A Django nested atomic() around one insert that may raise IntegrityError is this pattern. A savepoint cannot rescue a 40001, because the transaction keeps the snapshot of its first statement and meets the same conflict. That is inferred and not run. E16 shows the aborted state, the COMMIT that rolls back, and the savepoint, in psql.

On 40001, roll back and run the whole transaction again from BEGIN.

Resending only the failed statement gets 25P02 on every attempt.

Run the lab's aborted-transaction psql script, E16, and watch COMMIT reply ROLLBACK.

Each savepoint is also a subtransaction, and the next section shows what that costs every other session on a busy server.

Go deeper: the aborted state in the source, and the lab's two retry modes
The aborted state, exactly. IsTransactionExitStmt lists COMMIT, PREPARE TRANSACTION, ROLLBACK and ROLLBACK TO SAVEPOINT. An earlier version of this phase said that only ROLLBACK is accepted, and the source corrected it. The printed PostgreSQL 14 reply to COMMIT in an aborted transaction is ROLLBACK.

The two modes of the helper. With retry_statement_only=True, the wrong way, the second attempt sends the body into the failed transaction. The self-test of pglab.py expects 25P02 there, from a fake connection that follows the server's rule. With the default, every attempt starts with BEGIN, and the new snapshot shows the change that caused the conflict. lost_update.py --wrong-retry shows the same 25P02 against the real server, not run by the author yet. RetryPolicy caps any one wait at 500 ms, and contention.py raises the attempt cap to 50. Those values are this course's choice, not a measured optimum.

DBOS's retry, in its source. The retry of @DBOS.transaction is in _core.py, and its error test is in _app_db.py, in DBOS 2.31.0. The list of connection errors it retries is in _utils.py lines 154 to 183. Class 57 includes 57014, the error of statement_timeout. DBOS's own queue does not retry a 40001 at once. In the partitioned loop it skips that partition until the next poll, _queue.py lines 943 to 950. Without partitions it doubles the polling interval, lines 960 to 965.

Evidence
The aborted state: postgres.c lines 1143 and 1144, and 2831 to 2844, at REL_17_11, and Rogov pages 78 and 79. Retry rules: PostgreSQL 17 docs 13.2.2, 13.2.3 and 13.5, "Serialization Failure Handling", which first appeared in the version 15 docs. Libraries: psycopg 3 docs, Errors. Django 5.2 docs, "Managing database transactions". Rails API, DatabaseStatements. DBOS 2.31.0 source, _core.py lines 2190 to 2193 and 2272 to 2287, and _app_db.py lines 353 to 362. Failure rates: Ports and Grittner 2012, sections 8.2 and 8.3.

## What does a savepoint cost on a busy server?

A savepoint rescues a 23505, and each savepoint is a subtransaction. A subtransaction is a part of a transaction with its own xid and its own status in pg_xact. You create subtransactions more often than you write SAVEPOINT, because frameworks create them for you.

What you write | What PostgreSQL runs

SAVEPOINT s | one subtransaction

a PL/pgSQL block with EXCEPTION | a subtransaction for the block

psql with \set ON_ERROR_ROLLBACK on | "an implicit savepoint before each command"

Rails transaction(requires_new: true) inside a transaction | SAVEPOINT active_record_1

Rails transaction inside a transaction, without requires_new | nothing. The block joins the open transaction

Django transaction.atomic() inside another atomic() | one savepoint per inner block

psycopg 3 with conn.transaction(): inside another one | one savepoint per inner block

A snapshot must count the subtransactions of a running transaction as running, and that is where the cost comes from. A backend, the server process of one session, advertises up to 64 subtransaction IDs of its current transaction. The 65th sets an overflow flag, and every snapshot taken while that transaction runs is then marked suboverflowed.

- over 64 that wrote One backend's cache of their IDs is full.

- snapshots marked suboverflowed A snapshot can no longer list them all.

- checks read pg_subtrans Each check maps a subtransaction to its parent through a small shared cache.

- waits on SubtransSLRU Other sessions queue for that cache.

- Then a visibility check cannot search the snapshot's list of subtransaction IDs. It first reads pg_subtrans to map each ID to its top-level transaction.

- pg_subtrans is read through an SLRU, a small cache of pages in shared memory, like the one for pg_xact. Its size is subtransaction_buffers, new in PostgreSQL 17. The default 0 means automatic: shared_buffers/512, between 16 and 1,024 pages, so 32 pages at the default shared_buffers of 128 MB.

- A wait for this cache shows in pg_stat_activity as type LWLock, a lightweight lock on a shared-memory structure, with the event SubtransSLRU. A second event, SubtransBuffer, is the wait for a page that is not in the cache. PostgreSQL 14 had both events.

- The flag stays set until the transaction ends, even after its savepoints are released.

GitLab met this in production and wrote it up on its blog.

- Symptom. The database on GitLab.com stalled for minutes, and queries waited on SubtransControlLock, which PostgreSQL 13 renamed SubtransSLRU.

- Where. Only the replicas stalled, and each time a long transaction was open on the primary.

- Measurement. A test by Nikolay Samokhvalov fell from about 360,000 to 50,000 transactions per second on the replicas when a long transaction started on the primary.

- Cause. The post found that "a single SAVEPOINT during a long-transaction could initiate this problem if many writes also occurred simultaneously".

- Not the 64 limit. GitLab's code never nested more than 10 savepoints, so the replica path into pg_subtrans differs from the 64-entry overflow. Phase 5 of this course, section 5.3, covers replicas that serve reads.

- The code that made them. A Rails find_or_create_by inside transaction(requires_new: true), which sends SAVEPOINT active_record_1.

- Fix. GitLab removed every SAVEPOINT from its code. Where a savepoint caught a duplicate key, it used INSERT ... ON CONFLICT instead, and it added an alert on any use of a SAVEPOINT.

How to see it on PostgreSQL 17. Two queries find the session and the cost, and the first needs PostgreSQL 16 or later.

-- One row per backend. The third column is true for a session whose open
-- transaction has given IDs to more than 64 subtransactions, that is, more
-- than 64 that wrote. Every snapshot taken while it runs is suboverflowed.
SELECT pg_stat_get_backend_pid(b) AS pid, (pg_stat_get_backend_subxact(b)).*
FROM pg_stat_get_backend_idset() AS b
ORDER BY 3 DESC, 2 DESC;

-- The cache that suboverflowed snapshots read. A rising blks_read means misses.
SELECT name, blks_hit, blks_read FROM pg_stat_slru WHERE name = 'subtransaction';

Where you meet it | What creates the savepoints | What you see

a Django service with nested atomic() blocks, for example a helper that wraps its own writes | one savepoint per inner block entered, per transaction | the overflow flag true for that pid, and LWLock / SubtransSLRU on other sessions

a Rails app with requires_new: true, or find_or_create_by inside one | SAVEPOINT active_record_1 | the same. GitLab saw it on replicas first

a PL/pgSQL function with EXCEPTION, called once per row in a batch | one subtransaction per call that writes | 65 rows are enough to overflow the cache

an agent runner that saves each tool step in its own nested block, inside one long run transaction | one per step | the run transaction overflows after 64 steps that write, and every new snapshot on the server then reads pg_subtrans

On RDS and Aurora, by the naming rule of the lock-wait section, this wait should appear as LWLock:SubtransSLRU. That form is inferred from the AWS pages for Lock:transactionid and Lock:tuple, because the AWS page for this wait returned no content.

The decision: keep the savepoint count per transaction under 64, or better, at 0 on a hot path. Replace "insert, and catch the duplicate in a savepoint" with INSERT ... ON CONFLICT, which the constraint section shows. Keep transactions short, because the flag lasts until the transaction ends. E17 shows the overflow and another session's extra cache reads.

A retry and a savepoint both handle a conflict after it happens. The next section compares that with taking a lock first, or letting a constraint refuse the second writer.

Go deeper: the overflow in the source, the cache arithmetic, and a printed subtransaction
The overflow, in the source. The 64 is PGPROC_MAX_CACHED_SUBXIDS, whose comment calls it a "guessed-at value". The 65th subtransaction sets the overflow flag in varsup.c. XidInMVCCSnapshot then takes its suboverflowed branch and calls SubTransGetTopmostTransaction.

The cache arithmetic. The 17 docs give the default as "shared_buffers/512 up to 1024 blocks, but not fewer than 16 blocks". At the default shared_buffers of 128 MB there are 16,384 buffers, and 16,384 / 512 = 32 pages. At 8 GB there are 1,048,576 buffers, and 1,048,576 / 512 = 2,048, capped at 1,024 pages, which is 8 MB. The setting needs a restart. PostgreSQL 14 had a fixed 32 pages, NUM_SUBTRANS_BUFFERS, so on a small server 17 behaves the same as 14. transaction_buffers, the pg_xact cache, has the same automatic default, and serializable_buffers defaults to 32 blocks.

The column name. The docs and the C code call the second field of pg_stat_get_backend_subxact subxact_overflow. The catalog declares the OUT parameter subxact_overflowed. For a function with OUT parameters, PostgreSQL builds the result columns from the catalog, so the query prints subxact_overflowed. This is verified from the source and was not run. The second query uses the 17 name of the cache: versions 14 to 16 name that pg_stat_slru row Subtrans.

The cost, in the docs. A block with EXCEPTION "is significantly more expensive to enter and exit than a block without one", and savepoints incur "significant overhead" even when nobody rolls back to them.

A printed subtransaction. One printed PostgreSQL 14 transaction has rows with three xmin values: 782 for the transaction, and 783 and 784 for two subtransactions. The row of the subtransaction that rolled back stays on the page, and readers skip it.

Evidence
Where subtransactions come from: Rogov pages 76 to 79, GitLab's post of 2021-09-29, the Rails API page DatabaseStatements, Django 5.2 "Managing database transactions", and psycopg 3 "Transactions management". The overflow: proc.h line 39, varsup.c lines 269 to 276, and snapmgr.c line 1856 with its branch from line 1886, at REL_17_11. The cache: subtrans.c lines 201 to 207, guc_tables.c line 2361, and the 17 docs 19.4. The waits: docs Table 27.12, and wait_event_names.txt line 360. The function: the 16 release notes and pg_proc.dat line 5532 at REL_17_11. The cost of EXCEPTION: docs 41.6.8. The GitLab case: its blog post of 2021-09-29, listed in the sources.

## Which fix holds a rule: a lock, a version check, or a constraint?

A constraint holds its rule for every writer, at every level, without a retry.

Every fix so far made the later transaction wait or start again. Pessimistic control locks before it reads, with FOR UPDATE, so it costs waiting. Optimistic control checks at the write, with a version column or 40001, so it costs redone work. A constraint is a third way, because the database refuses the second writer.

Predict: the rule is at most one running task per tenant. Does a FOR UPDATE before the count hold it?
Two workers poll when none is running. No, the rule breaks. The SELECT returns no rows, so it locks none, and both workers claim, because a row lock covers only rows that exist. The trap passes every test that runs one session.

A partial unique index is unique only among rows that match its condition. CREATE UNIQUE INDEX ON tq_tasks (tenant) WHERE state = 'running' holds this rule.

- W1 starts task 7, which adds an index entry for acme.

- W2 starts task 8, finds W1's entry while W1 is open, and waits.

- If W1 commits, W2 gets 23505, duplicate key value violates unique constraint. If W1 rolls back, W2 goes on.

- At SERIALIZABLE, a 40001 may come first instead.

The index holds at every level and needs no retry at READ COMMITTED, so catch 23505 as "another writer won", not as a server fault. It also holds for code written later by someone who never read this lesson. UNIQUE (task_id) on tq_approvals stops a second approval decision the same way.

A row that always exists. A unique index holds a limit of 1 only. "At most 3" or "at least one approver" needs a counter row instead, one row that always exists, which a conditional UPDATE changes. phantom.py --fix parent-row keeps the counter on the tenant's row.

-- from phase03_transactions/phantom.py:98, SQL["reserve_slot"]. Copied, joined onto two lines
UPDATE tq_tenants SET running = running + 1
WHERE tenant = 'acme' AND running < max_running

The second worker waits for the first one's row lock, re-checks 1 < 1, and updates 0 rows. The cost is a copy of a fact, so every transaction that starts or ends a task must change both, or they drift apart.

One statement. Sometimes the read, the check and the write fit in one SQL statement. The server then does all three under the row lock. The atomic spend is this kind: SET credits = credits - 80 WHERE ... AND credits >= 80. It needs no retry at READ COMMITTED. It holds the lock only from that statement to COMMIT. Its limit is that the whole decision must be expressible in SQL.

Declare the rule. Rogov's first fix for check-then-act is the same idea: "Replace procedural code with declarative one". Ports and Grittner state the principle for constraints. A constraint that "can be expressed to the DBMS (e.g. using a foreign key, uniqueness, or exclusion constraint)" is one "the DBMS can enforce ... regardless of isolation level". Where no constraint can express it, "the conflict can be materialized by creating a dummy row". The counter row is that dummy row.

The counter row at other levels. At REPEATABLE READ the slot reservation gets 40001 instead of 0 rows. Either way, at most one task runs. The same move fixes the approvers. Keep the count of approvers on call in one row. Change it with a conditional UPDATE that keeps it above 0.

Constraints that hold rules.

Rule | Constraint | What the second writer gets

at most 1 running task per tenant | CREATE UNIQUE INDEX ON tq_tasks (tenant) WHERE state = 'running' | waits for the first writer, then 23505 unique_violation

one decision per task | CREATE UNIQUE INDEX ON tq_approvals (task_id) | waits for the first writer, then 23505

insert a row, or update it if it exists | a unique key, and INSERT ... ON CONFLICT (key) DO UPDATE | at READ COMMITTED, no error: its UPDATE runs on the row the first writer inserted. At REPEATABLE READ and SERIALIZABLE, 40001 when its snapshot cannot see that row

the same rule, written as MERGE | a unique key, and MERGE ... WHEN MATCHED THEN UPDATE ... WHEN NOT MATCHED THEN INSERT | 23505 at READ COMMITTED, when the first writer inserted the row after the MERGE's snapshot. At SERIALIZABLE, 40001 may come first. Not an upsert under concurrency

For upserts, "ON CONFLICT DO UPDATE guarantees an atomic INSERT or UPDATE outcome". Unless an unrelated error occurs, one of the two outcomes holds "even under high concurrency". It needs no savepoint, so it pays no subtransaction. At the two higher levels it can still raise could not serialize access due to concurrent update. So an upsert there still needs the retry loop.

MERGE is not that upsert. MERGE came in PostgreSQL 15, and 17 added RETURNING and WHEN NOT MATCHED BY SOURCE to it. It reads like an upsert, and the 17 docs say it is not one under concurrency.

- A MERGE with INSERT and UPDATE branches "looks similar to INSERT with an ON CONFLICT DO UPDATE clause but does not guarantee that either INSERT or UPDATE will occur".

- "If MERGE attempts an INSERT and a unique index is present and a duplicate row is concurrently inserted, then a uniqueness violation error is raised".

- MERGE "does not attempt to avoid such errors by restarting evaluation of MATCHED conditions".

So when two workers count the first event of a tenant with MERGE, one inserts and the other gets 23505. That second count is lost unless the code retries it. You meet it in a migration from SQL Server or Oracle, where MERGE is the usual upsert. You also meet it in an ORM that offers a "merge" method, so check what SQL it sends. The decision: use MERGE for batch synchronisation that runs alone, and INSERT ... ON CONFLICT for any write that can race. E19 runs both forms in the same order.

The approval, fixed two ways. The naive approval counts the task's rows in tq_approvals, and inserts a decision if the count is 0. Alice inserts approve and Bob inserts reject after both found no decision, which is the phantom form of write skew. The first fix turns the decision into a write on the task's own row, run first.

-- from phase03_transactions/taskqueue.py:188, SQL["decide_task"], run first. Copied
UPDATE tq_tasks SET state = %s WHERE id = %s AND state = 'awaiting_approval'

Only when it updates 1 row does the transaction insert the decision and the event. Bob's UPDATE waits for Alice's row lock, re-checks state = 'awaiting_approval', now false, and updates 0 rows. The second fix is the unique index, which makes Bob's insert wait and then fail. In production, keep both. The state change carries the logic, and the index is the rule that later code cannot break.

When you lock or check instead, contention decides. With conflict probability p, optimistic control needs 1 / (1 − p) attempts on average. And n workers that start together on one row, with one commit per round, make n × (n + 1) / 2 attempts. Pessimistic control makes n attempts, and the last worker waits for every one before it.

Optimistic attempts

Conflict probability p, in %
Workers on one row
Mean attempts . Total , against  with FOR UPDATE.

At p = 0.1 the mean is 1.11 attempts, at p = 0.5 it is 2, and at p = 0.9 it is 10. Ten workers on one counter row make 10 × 11 / 2 = 55 optimistic attempts for 10 commits. Neither number was measured in this course, and contention.py measures both on your laptop.

Here are three workers on one row, round by round, so you can see where each form pays.

Three workers increment one row | Pessimistic: FOR UPDATE | Optimistic: version check

round 1 | W1 locks, reads 0, writes 1, commits. W2 and W3 wait | all read 0, version 0. W1 writes 1. W2 and W3 update 0 rows and start again

round 2 | W2 locks, reads 1, writes 2, commits | W2 and W3 read 1. W2 writes 2. W3 updates 0 rows

round 3 | W3 locks, reads 2, writes 3, commits | W3 reads 2 and writes 3

total | 3 attempts, and the waits add up. A 4th waiter would race W3 after W2 | 3 + 2 + 1 = 6 attempts, no waits

The two forms in your code. SELECT ... FOR UPDATE has two options for a locked row. NOWAIT reports an error, SQLSTATE 55P03, instead of waiting. SKIP LOCKED skips the rows it cannot lock at once. The docs say it "provides an inconsistent view of the data", and that it suits "a queue-like table". Django's select_for_update(nowait=False, skip_locked=False, of=(), no_key=False) maps to these options. no_key=True gives FOR NO KEY UPDATE, the weaker mode, which does not block foreign-key checks. The optimistic form is a version column, and the writer must check the row count.

# from phase03_transactions/contention.py:116, make_body(), the "version" strategy. Copied
        elif strategy == "version":
            n, v = conn.execute(SQL["read_version"], (row,)).fetchone()
            work()
            # 0 rows: another worker changed the row after our read. Ignoring
            # the count would report success for a write that never happened.
            if conn.execute(SQL["cas"], (n + 1, row, v)).rowcount == 0:
                raise _Conflict()

You meet it with agent state kept as one row per conversation or per workflow, such as a JSON document of the run so far. Two tool calls that finish in parallel each read the state, add their result, and write it back, which is a lost update. A version column turns it into a retry. The inferred cost is one retry for each pair of results that land within one read-and-write of each other.

How to choose. Each row gives a situation, the choice it favors, and the measurement that would prove it wrong. The thresholds are this course's example from the formula, not measured limits.

Situation | Prefer | Why | Measure to check it

the decision fits in one UPDATE whose condition reads only that row | one conditional statement | no retry and no explicit lock | rows updated, 0 or 1

the rule is "at most one" | a unique index, partial if needed | holds at every level, and for later code | count of 23505

conflicts are rare, p under about 0.1 | optimistic | about 1.11 attempts at p = 0.1, and nobody waits | retries per commit

many writers on few rows | pessimistic | 1 / (1 − p) grows fast: 10 attempts at p = 0.9 | lock waits, p99 of the transaction

workers take items from a queue | FOR UPDATE SKIP LOCKED | each worker takes a different row | claims per second, rows skipped

insert or update a row that may not exist yet | INSERT ... ON CONFLICT, not MERGE | the unique index decides, and the loser takes the UPDATE branch | count of 23505 from MERGE

the rule spans many rows or a condition | SERIALIZABLE and a retry, or a parent row | row locks cannot cover rows that are not there | 40001 rate

the thing to serialize is not a row | pg_advisory_xact_lock | one holder per key until the transaction ends | lock waits on advisory

the work between read and write is slow, such as a network call | neither inside one transaction | split it into two short transactions, which the next section shows | time a lock is held

For "at most one", add a unique index, because it holds at every level.

A version-checked UPDATE whose row count nobody checks reports success for a lost write.

Predict the version retries at one hot row, then run the E9 contention command.

Every lock in this section ended at COMMIT. The next section shows two locks that do not, one held by a session and one held across a slow call.

Go deeper: NOWAIT and SKIP LOCKED in full, the B-tree wait, the arithmetic worked, and the lab's approval
NOWAIT and SKIP LOCKED, from the docs. NOWAIT: "the statement reports an error, rather than waiting". The error is SQLSTATE 55P03, lock_not_available, with the message could not obtain lock on row in relation "%s". PostgreSQL 18 adds log_lock_failures, which writes these failures to the server log. SKIP LOCKED: "any selected rows that cannot be immediately locked are skipped". The docs add that it "can be used to avoid lock contention with multiple consumers accessing a queue-like table". At READ COMMITTED, a FOR UPDATE that waited returns the row as the other transaction left it: it will "lock and return the updated row". At REPEATABLE READ it raises 40001 instead.

Pessimistic in a real design. Pinterest's MySQL design stores objects as JSON blobs and edits each one with SELECT ... FOR UPDATE in a transaction, by this course's companies research.

The version column, in SQL. SQL["cas"] holds UPDATE tq_counters SET n = %s, version = version + 1 WHERE id = %s AND version = %s. At READ COMMITTED, the second writer waits for the first one's row lock. It then re-checks version = %s on the new row, which no longer matches, so it updates 0 rows. _Conflict carries SQLSTATE 40001, so run_with_retry starts the whole transaction again.

Why the second writer waits on a unique index. The docs' own partial unique index lets each subject and target have only one successful entry: CREATE UNIQUE INDEX tests_success_constraint ON tests (subject, target) WHERE success;. Such an index "enforces uniqueness among the rows that satisfy the index predicate". W2's insert is a B-tree insert. In the B-tree code, _bt_doinsert waits for the open first writer with XactLockTableWait. So no second claim can succeed while the first may still commit. If the first writer commits, the check finds a live duplicate and raises duplicate key value violates unique constraint "%s" with the DETAIL Key %s already exists.. At SERIALIZABLE, the code checks for an SSI conflict first, which is why 40001 may come instead, and why MERGE can get 40001 there. The docs show the same thing from outside: "it is possible to see unique constraint violations caused by conflicts with overlapping Serializable transactions even after explicitly checking that the key isn't present before attempting to insert it." phantom.py --fix unique-index shows the first row, not run by the author yet. The docs list 23505 among the errors that a retry can sometimes fix.

The upsert at the higher levels. ExecCheckTupleVisible raises the 40001 when the conflicting row was committed after the transaction's snapshot.

The approval in the lab. The expected naive line, not run, is FAIL approval: task 2 has decision(s) ['approve', 'reject'], state awaiting_approval, and the outbox holds both task.approved and task.rejected. A consumer may act on both. At REPEATABLE READ the fixed approval gets 40001, and its retry updates 0 rows. SERIALIZABLE with a retry also fixes the naive version, and taskqueue.py --check approval --variant naive --level serializable --retry is expected to pass. The unique index fixes it with no change to the naive code, and taskqueue.py --check approval --variant naive --unique-decision is expected to pass.

The arithmetic, worked. Of the 55 optimistic attempts, the unluckiest worker makes 10. Pessimistic control makes only 10 attempts, and the last worker to get the row waits for the nine before it, each for its whole transaction. Which worker is last is not decided by arrival, as the lock-wait section showed.

The E9 command is uv run python phase03_transactions/contention.py --workers 8 --increments 200 --hot-rows 1,64. A longer form adds the strategies: uv run python phase03_transactions/contention.py --workers 8 --increments 200 --hot-rows 1,64 --strategies naive,for-update,version. Read the lost and retries columns for each hot-row count.

Evidence
NOWAIT and SKIP LOCKED: PostgreSQL 17 docs, SELECT, "The Locking Clause", and errcodes.txt line 421 and heapam.c line 5220 at REL_17_11. The "lock and return the updated row" quote: docs 13.3.2. log_lock_failures: the 18 release notes. Django: the 5.2 QuerySet reference. Declarative fixes: Rogov page 47. The constraint principle and the dummy row: Ports and Grittner 2012, section 2.2, from the study note. Partial unique indexes: docs 11.8, Example 11.3. The unique-insert wait: nbtinsert.c lines 227, 639 and 668 at REL_17_11. The serializable unique violation: docs 13.2.3, from the study note. Upserts: docs, INSERT, and nodeModifyTable.c lines 309 and 335. MERGE: docs 13.2.1 and the MERGE page. Pinterest: a 2015 post, from the companies research. The contention formulas are checked by contention.py --self-test.

## Which locks outlive the transaction, behind a pooler or across a slow call?

Row locks and constraints end at COMMIT, and that is what makes them safe to use. Two kinds of lock break that rule in practice. One belongs to a session, and the other is held while its transaction waits for something slow. Both appear in the task queue. A scheduler for one tenant needs a lock on a name, and a worker calls a model for 20 seconds.

Advisory locks, a lock on a name. Sometimes the thing to lock is not a row, such as "the scheduler for tenant acme". Advisory locks are "locks that have application-defined meanings". You lock a number, often a hash of a name.

SELECT pg_advisory_xact_lock(hashtext('scheduler:acme'));  -- waits if needed, held until the transaction ends
SELECT pg_try_advisory_lock(hashtext('scheduler:acme'));   -- session level: true or false at once, never waits

The docs give three rules.

- Session-level locks "do not honor transaction semantics", so a lock taken in a transaction that rolls back is still held.

- All advisory locks use the shared lock table, which max_locks_per_transaction and max_connections size, so leaked locks can stop the server from granting any lock.

- pg_advisory_lock(id) in a query with LIMIT is marked "danger!", because the LIMIT may apply after the function ran.

Behind a pooler. A pooler such as PgBouncer keeps a few server connections and lends them to many clients. In transaction mode it lends a server connection for one transaction only. So a session-level lock stays on a server connection that the client no longer has. Phase 5 of this course, section 5.7, teaches pooler modes and what transaction mode breaks.

Wrong behind a pooler: pg_advisory_lock. PgBouncer's feature table lists "Session-level advisory locks" as "Never" supported in transaction pooling. RDS Proxy, AWS's pooler, pins a client to one server connection when it calls pg_advisory_lock, so the pooling stops for that client.

Right: pg_advisory_xact_lock. It ends with the transaction, so the pooler can lend the connection on. RDS Proxy "does not pin on transaction level advisory locks".

Mattermost met this in production. Their migration library, golang-migrate, took pg_advisory_lock so that two servers never ran one migration at once, and PgBouncer ran in transaction mode. In the post's words, "there was an initial lock-in the DB for pg_advisory_lock and the session was lost". The library could not release the lock, so the application hung and restarted, and each restart added more locks. The midterm fix was the PgBouncer setting server_reset_query_always, and the long-term fix was another migration library.

The same tool fits an agent system, as a design note that is inferred: let only one agent turn run per conversation. Start each turn's transaction with SELECT pg_advisory_xact_lock(hashtext('thread:' || %s)). A second turn for the same thread waits, and turns of other threads do not. The lock ends at COMMIT, so a pooler in transaction mode keeps working.

A lock held across a slow call. A worker locks a task with SELECT ... FOR UPDATE, calls a language model that takes 20 seconds, as an example, and writes the result. Every other transaction that touches that row waits the full 20 seconds. The open transaction also keeps its snapshot for that long, so it holds back vacuum as the snapshot section showed. The fix is two short transactions with a state change between them.

- The first transaction claims the task and commits, so the row now says running with an owner.

- The model call happens outside any transaction.

- The second transaction records the result only if the claim still holds: UPDATE ... WHERE id = %s AND state = 'running' AND owner = %s, which re-checks its condition after any wait.

The same rule applies to any slow call inside a transaction: an HTTP request, a broker publish or a user's reply. The outbox relay at the end of this lesson follows it too.

The two short transactions leave one hole, a worker that dies between them, and the next section closes it with a lease.

Go deeper: the lock table limit in PostgreSQL 19, and what Mattermost confirmed
The lock table. PostgreSQL 19 RC1 changes the default max_locks_per_transaction from 64 to 128, by its release notes. The same note says that lock size allocation changed, so a setting must be doubled to keep its old capacity. So 128 in 19 is about the capacity of 64 before.

What the post confirms. The post confirms that the lock could not be released behind the pooler. It does not say which client got that server connection next. The PgBouncer and RDS Proxy facts above come from the vendors' pages, fetched for the phase.

Advisory functions. The xact forms end with the transaction, and the try forms return true or false at once instead of waiting. Rogov locks a hash of a name the same way.

Evidence
Advisory locks: PostgreSQL 17 docs 13.3.5 and 9.28.10, Table 9.106, and Rogov page 234. PgBouncer: its features page, vendor. RDS Proxy: "Avoiding pinning", AWS, vendor. The lock lost behind the pooler: a Mattermost blog post by Angelos Kyratzakos, 2022-01-11, its migrations part. The agent turn lock: the phase, inferred. PostgreSQL 19: the 19 RC1 release notes.

## What happens to a claimed task when its worker dies?

A lock ends at COMMIT, so a claim that must last needs an expiry time.

After the first of two short transactions commits, a claim is only a value in a row. The first version of a claim would run two statements. It runs SELECT id FROM tq_tasks WHERE state = 'queued' ORDER BY id LIMIT 1, and then UPDATE tq_tasks SET state = 'running', owner = %s WHERE id = %s. Both workers SELECT task 1, and B's UPDATE waits for A's row lock. It then re-checks id = 1, which still matches, so B overwrites the owner and both workers run the task. That is the lost update, on the owner column. The fixed claim finds and claims in one statement, and skips rows another worker holds.

# from phase03_transactions/taskqueue.py:169, SQL["claim_fixed"]. Copied
    "claim_fixed": ("UPDATE tq_tasks SET state = 'running', owner = %s, attempts = attempts + 1 "
                    "WHERE id = (SELECT id FROM tq_tasks WHERE state = 'queued' "
                    "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING id"),

Worker B's subquery skips task 1, which A holds, and finds no other queued task. So B is expected to update 0 rows at once, with no wait. The libraries you may use make the same claim, and they differ in what happens next.

Library | How it claims | What happens when a worker dies

this lab | one UPDATE with a FOR UPDATE SKIP LOCKED subquery | the lease expires, and the reaper requeues the task, up to a cap

Solid Queue, the Rails default queue | FOR UPDATE SKIP LOCKED. Its README says it "was designed for the highest throughput when used with MySQL 8+, MariaDB 10.6+, or PostgreSQL 9.5+". Workers poll every 0.1 s by default | its README says a job claimed by a process whose heartbeat expired is marked as failed. The heartbeat is every 60 s, and a process counts as dead after 5 minutes, by default

Django | no queue of its own. select_for_update(skip_locked=True) inside atomic() gives the same claim | whatever your code does

DBOS 2.31.0 | SKIP LOCKED, or NOWAIT for a shared budget | see the optional reading example at the end of the outbox section

Solid Queue's choice. It does not requeue a job whose process died. Its README gives the reason: "the job itself might be what's killing the process". The lab requeues up to a cap, then marks the task failed. From the two defaults, a job of a dead Solid Queue worker waits about 5 minutes before anything happens. That figure is inferred.

Predict: a worker claims a task this way, commits, starts a 30-second model call, and is killed. What does the queue show a minute later?
The task still says running with the dead worker as owner, and it will for ever. SKIP LOCKED only chose who got the row at the claim, and the row lock ended at COMMIT.

A dead worker can be handled in three ways, and each one pays in a different place. The second uses a lease, a claim that ends at a stated time unless its worker renews it.

Design | When the worker dies | What it costs

hold the row lock of FOR UPDATE SKIP LOCKED for the whole job | the transaction ends with the connection, so the task is free again | one open transaction per running job. It holds a connection, and it holds back the cleanup horizon

claim with a lease, lease_until, and run a reaper that requeues expired leases | another worker runs the task once the lease has expired | at least once: a slow worker and its replacement can both run it. The work must be idempotent, and attempts need a cap

a session-level advisory lock per task | the lock goes when the session ends | the claim lives on one connection, and session locks ignore COMMIT and ROLLBACK

The lab uses the lease. A reaper is the statement that hands expired leases back to the queue.

- The claim also sets lease_until = now() + %s * interval '1 millisecond', and the worker commits and works outside any transaction.

- The reaper sets state = 'queued' and clears the owner and lease_until WHERE state = 'running' AND lease_until < now() AND attempts < %s.

- Another worker claims the task, and attempts grows by 1.

Five rules make the lease safe.

- The completion names its owner: ... AND owner = %s. A worker that was only slow can wake after its task went to B. Its completion then updates 0 rows, and it must drop its result.

- The reaper, the completion and a new claim all change the same row. The row lock puts them in order, and each re-checks its condition on that row.

- The owner check is safe only while one owner name is never used for two claims of one task. If slow worker A loses the task and then claims it again, A's old completion passes the owner check. Check attempts too, so that each claim is unique. This fix is inferred from the SQL, and the lab does not test it.

- attempts < %s stops a task that kills every worker. Without it, that task runs for ever.

- A long job needs a heartbeat, an UPDATE that moves lease_until forward with the same owner check. The heartbeat is a design note, not part of the lab.

The lease and the reaper read now(), the database clock, so the lease does not depend on how well the workers' clocks agree. That is inferred from the SQL.

The lease protects the row, not the call. The owner check guards writes to this database only, and a slow worker's calls to other systems still happen. Those systems must check a fencing token, a number that grows with each claim, so that they can refuse an older one. They are taught in Phase 3 of the Redis course. For a call to a model API or a payment provider, send an idempotency key built from the task id and attempts. A provider that supports such keys then runs the call once per claim. That use is inferred.

A task that kills every worker needs a terminal state. Rule 4 stops the retries, but it leaves the task running, with a lease in the past. A dashboard that counts running tasks then counts it for ever, and nobody is told. So the reaper runs a second statement.

-- from phase03_transactions/taskqueue.py:184, SQL["fail_over_cap"]. Copied, joined onto two lines
UPDATE tq_tasks SET state = 'failed', owner = NULL, lease_until = NULL
WHERE state = 'running' AND lease_until < now() AND attempts >= %s RETURNING id

Alert on any row in failed. The reaper reads running rows by their lease, so it gets its own partial index, CREATE INDEX tq_tasks_running_lease ON tq_tasks (lease_until) WHERE state = 'running'. Without it, each pass reads every task, done ones included, which is inferred from the filter. taskqueue.py --check poison, in E10, claims one task five times with a worker that dies each time.

A long transaction anywhere slows the queue. A busy queue table makes dead row versions fast. Each claim replaces a queued version, and each finished job leaves one more. VACUUM can remove a dead version only once no open snapshot might need it. So one long transaction anywhere in the database lets dead versions pile up in the queue table. Each claim's index scan then steps over more dead entries before it finds a live queued task. One measured queue ran at about 50 jobs a second. There, one open transaction made the time to lock a job grow from under 0.01 s to 0.1 s and more.

On PostgreSQL 17, two lines of the VACUUM VERBOSE report name the problem.

tuples: %lld removed, %lld remain, %lld are dead but not yet removable
removable cutoff: %u, which was %d XIDs old when operation ended

The removable cutoff is the oldest xmin that VACUUM must keep. So find the session whose backend_xmin equals it, with the query of the snapshot section. If no session matches, the holder is a replication slot or a prepared transaction, which Phase 4 covers. The second number says how far behind it is. Autovacuum writes the same report to the server log when a run takes longer than log_autovacuum_min_duration, 10 minutes by default in 17. Three defenses follow.

- Index the claim's filter, with CREATE INDEX tq_tasks_queued ON tq_tasks (id) WHERE state = 'queued', so a claim does not scan the whole table. The scan still steps over dead entries, so the index alone is not enough.

- Watch the horizon. age(backend_xmin) in pg_stat_activity names the session that holds it, and Phase 4 alerts on it.

- End idle transactions with idle_in_transaction_session_timeout, and long ones with transaction_timeout, set per role.

E15 holds one REPEATABLE READ snapshot, runs the claim loop, and prints whether the removable cutoff equals the holder's backend_xmin.

The claim and the lease keep a task's state correct, and the next section asks how the events that announce each change reach other services.

Go deeper: other claim fixes, three lease designs, the queue measurement, and the 14 report line
The naive claim in the lab. taskqueue.py --check claim --variant naive is expected to print the line below, not run by the author yet.

FAIL claim: 2 worker(s) believe they claimed task 1. The row says owner B, attempts 2. 2 task.claimed event(s)

The check sets lock_timeout = '2s' for B, so a query that waited by mistake would fail instead of hanging. Two other fixes also work. AND state = 'queued' in the naive UPDATE makes B wait and then update 0 rows. REPEATABLE READ with a retry makes B fail with 40001 and find no queued task on its second attempt. taskqueue.py --self-test checks both in the model. It expects 2 claims for the naive form at READ COMMITTED, and 1 for each fix. Rogov says SKIP LOCKED suits batches and "parallel processing of event queues". "However, avoid inventing other use cases for this command".

The reaper SQL. The lab's lease claim, SQL["claim_lease"], is claim_fixed with lease_until added. The reaper is one statement, SQL["reap"] at taskqueue.py:180, with the SET and WHERE clauses of step 2 and RETURNING id.

PostgreSQL 18 adds RETURNING OLD and NEW, by its release notes. So a reaper on 18 can return the owner it took the task from, in the same statement, for the log.

Expected lease output. taskqueue.py --check lease --variant naive is expected to print FAIL lease: task 1 is running, owner A. Its worker is dead, and nothing will ever run it. --check lease --variant fixed is expected to print PASS lease: task 1 is done, owner B, with the late completion shown as 0 rows. Neither was run by the author yet.

The queue measurement, with its conditions. Indexes carry no visibility information, so each candidate entry needs a heap fetch and a visibility check, and the claim loop walked the same dead rows each time. The queue ran on Heroku Postgres with the Que library, which claimed jobs with advisory locks in a recursive query, not with SKIP LOCKED. One producer, one worker and one transaction held open processed about 50 jobs a second. The lock time grew to "15x that level at times of 0.1 s and above". One hour in, 60k jobs were queued. By the end of the test, the table approached 100,000 dead rows. Its VACUUM VERBOSE printed DETAIL: 247311 dead row versions cannot be removed yet.. The original problem was one idle-in-transaction session opened for analytics by another team. That the same slowdown hits a SKIP LOCKED queue is inferred from the shared index-scan mechanism.

The report on older versions. PostgreSQL 14 printed one line instead of the two 17 lines, %lld dead row versions cannot be removed yet, oldest xmin: %u. PostgreSQL 15 and later use the two-line form. The first version of the lab's E15 matched only the 14 text, so on 15 and later it printed nothing, and the script now matches both. An autovacuum run's report starts with automatic vacuum of table.

Evidence
The claim, lease, reaper and failed-state SQL: phase03_transactions/taskqueue.py lines 169, 180 and 184, and the reaper index at line 134. Solid Queue: its README, fetched for the phase. Django: the 5.2 QuerySet reference. The queue measurement: Brandur Leach, "Postgres Job Queues & Failure By MVCC", 2015-05-18, sections "Slow lock time" and "Dead tuples". The VACUUM lines: vacuumlazy.c lines 646, 660 and 672 at REL_17_11, line 1656 at REL_14_24, and guc_tables.c line 3049 for the autovacuum log default. The SKIP LOCKED caution: Rogov page 224. RETURNING OLD: the 18 release notes. Fencing tokens and idempotency keys: inferred, with fencing taught in the Redis course.

## How does every committed event reach the broker?

Every event the queue writes must also outlive COMMIT. The broker is the message system that other services read, such as Kafka or RabbitMQ. The transactional outbox stores each event as a row in tq_outbox, in the transaction that makes the change. A relay process reads stored events, publishes them to the broker and marks them. A dual write instead commits and then publishes from your code, so a crash between the two loses the event.

The outbox INSERT reads nothing, so atomicity alone ties the event to the change. The bug is in the relay. The naive relay keeps the highest id it has published and polls WHERE id > last_id. An id comes from a sequence at INSERT and is never rolled back, while a row becomes visible only at COMMIT. So ids follow insert order, and rows appear in commit order.

The naive relay skips an event

Step 1: W1 inserts id 1 and stays open.

Step 2: W2 inserts id 2.

Step 3: W2 commits, so only id 2 is visible.

Step 4: the relay sees only id 2 and sets last_id to 2.

Step 5: W1 commits, so id 1 appears.

Step 6: the relay asks for ids above 2, so event 1 is never published.

The lab's fixed order, expected and not run. The widths show order, not time.

Precision Nutrition had this skip in production, with readers that polled an events table by id. After a few weeks, many errors appeared, because some earlier events had never been processed. The logs showed that a reader processed events 185, 186 and 189, and a later query found events 187 and 188 in the table. Their xmin values were 10679 for 187 and 188, and 10680 for 189. The transaction that wrote 187 and 188 started before the one that wrote 189, but it committed after that one. So the reader passed 187 and 188 while they were invisible. Waiting for each next id would stop the reader, because some ids are never used. In that table about 0.6% of the ids were missing. The fix took ids from a counter row that every writer updates, so the ids follow commit order.

No isolation level fixes this. The order W2, relay pass 1, W1 explains every read, so the history is serializable. The relay at SERIALIZABLE is expected to fail the same way, which is inferred and tested by E11. And only a test that commits the higher id first, while the lower one is open, shows the skip. A test in commit order passes the naive relay.

The fixed relay. It stops tracking ids, and it keeps its own transactions short. A relay that publishes inside its open transaction holds row locks and a snapshot while the broker answers. That is the lock across a slow call of the pooler section. So the relay claims its rows with a short lease and commits, then publishes, then marks the rows sent.

# from phase03_transactions/taskqueue.py:230, the body of relay_pass(). Copied, all 26 lines
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
        # RIGHT: every unsent row, whatever its id. The claim commits before
        # the publish, so no transaction, row lock or snapshot waits for the
        # broker. That is the rule of section 3.6 for a slow call.
        rows = sorted(conn.execute(SQL["relay_claim"], (owner, lease_ms)).fetchall())
        conn.execute("COMMIT")
        for r in rows:
            broker.append(r[0])              # publish before marking: at least once
        if crash_before_mark:
            return [r[0] for r in rows]      # the relay died after publishing. Its claim expires
        if rows:
            conn.execute(begin_sql(level))
            conn.execute(SQL["relay_mark"], ([r[0] for r in rows], owner))
            conn.execute("COMMIT")
    return [r[0] for r in rows]

SQL["relay_claim"] sets relay_owner and a short relay_lease_until on up to 100 unsent rows. It picks them with WHERE sent_at IS NULL AND (relay_lease_until IS NULL OR relay_lease_until < now()) ... FOR UPDATE SKIP LOCKED. That is the claim and the lease of the task queue, applied to events, and the mark names its owner as the task completion does. Event 1 is unsent when pass 2 runs, so pass 2 publishes it.

Delivery is now at least once, because a relay that dies between publishing and marking sends the rows again after its claim expires. So the consumer records each event id in the same transaction as the effect.

-- the consumer's own database. A design, not part of the lab
BEGIN;
INSERT INTO processed_events (event_id) VALUES (%s) ON CONFLICT DO NOTHING;
-- 0 rows inserted: this event was applied before. ROLLBACK, and acknowledge it
-- 1 row inserted: apply the effect here, then COMMIT

The primary key on event_id turns a second delivery into 0 rows with no error, and the record and the effect commit together. The fixed relay also has no global order, because event 2 was published before event 1. A consumer may need the order of one task's events. Then give each event a sequence number within its task, and let the consumer reorder or reject. That design is inferred, and not part of this lab. Change data capture, CDC, is a relay that reads the database's change log, the WAL in PostgreSQL, instead of polling a table. Debezium is a widely used CDC tool, and the Kafka course, Phase 6, teaches it as an outbox relay.

The outbox is a queue table too. Every event row is inserted, updated once by the claim and once by the mark, and deleted later. So it needs what tq_tasks needs, and a dashboard can watch all four.

- A partial index on the rows the relay reads, CREATE INDEX tq_outbox_unsent ON tq_outbox (id) WHERE sent_at IS NULL. Without it, each poll walks the primary key over every sent row that retention has not deleted yet.

- Retention. SQL["outbox_retention"] deletes sent rows older than a limit, in batches of a few thousand. So one DELETE does not lock many rows or make one large burst of dead versions. The lab runs it with a limit of 0 seconds to show it, and production keeps days, for replay.

- A backlog signal. SQL["outbox_backlog"] returns the count of unsent rows and the age of the oldest one. Alert on the age. A growing count with a flat age points to a relay that runs but falls behind. A growing age points to a stuck one. That reading is inferred, not measured.

- The slowdown of the claim section applies here too. Each published event leaves two dead versions, one per UPDATE, so one long transaction anywhere slows the relay's index scan as it slows the claim. That is inferred from the same mechanism as E15, and not measured for the outbox.

-- The backlog query, as taskqueue.py runs it. Any version.
SELECT count(*), coalesce(round(extract(epoch FROM now() - min(created_at))::numeric, 1), 0)
FROM tq_outbox WHERE sent_at IS NULL;

To wake the relay sooner than its poll, do not send NOTIFY from every writer. Each such COMMIT queues for the one server-wide NOTIFY lock. Poll with the partial index above, or let one process send the NOTIFY.

The whole audit. Each row has a check in taskqueue.py that exits with 1 when the rule is broken. The method is the same for any transaction. Write down the rule it must keep, and find the reads that its decision depends on. Ask which other transaction can change those reads before the commit. Fix it with the smallest change, and keep a test that fails without the fix. Check the scope first, then the level.

Transaction | Rule | Anomaly at READ COMMITTED | Fix | Level after the fix

claim | one worker owns a claimed task | lost update on owner | one UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED) | READ COMMITTED

claim, after its commit | a claimed task runs again if its worker dies | not an isolation anomaly: a crash leaves it running for ever | a lease, a reaper, and an owner check on completion | READ COMMITTED

claim, at the attempt cap | a task that kills every worker ends where monitoring can count it | not an anomaly: it stays running for ever | the reaper's second statement, state failed | READ COMMITTED

approval | one decision per task | write skew on an empty set, the phantom form | a conditional state change on the task row first, and UNIQUE (task_id) | READ COMMITTED

outbox write | the event commits if and only if the change does | none: the INSERT reads nothing | none needed | READ COMMITTED

outbox relay | every committed event is published | not an isolation anomaly: ids are not in commit order | mark rows sent, poll unsent rows | any

outbox relay, its transactions | no transaction waits for the broker | not an anomaly: a lock and a snapshot held across a slow call | claim with a lease and COMMIT, publish, then mark with an owner check | any

A relay polls unsent rows, because events appear in commit order, not id order.

A relay that keeps the highest id skips a slow transaction's event for ever.

Run E10's taskqueue.py check naive, then fixed, and compare the exit codes.

Optional reading example: the queue under Mission HQ. This box is a reading example only. It assigns no work on Mission HQ, and nothing in it needs to change. Mission HQ runs its durable workflows on DBOS 2.31.0, a Python library that keeps workflow and queue state in PostgreSQL. Its dequeue makes three of this lesson's choices, read from dbos/_sys_db.py, dbos/_queue.py, dbos/_dbos.py and dbos/_core.py in Mission HQ's virtual environment.

- SKIP LOCKED, unless workers share a budget. start_queued_workflows selects enqueued workflows with .with_for_update(skip_locked=skip_locks, nowait=(not skip_locks)). skip_locks is false when the queue has any concurrency limit or rate limit, global or per partition. The comment gives the reason: SKIP LOCKED "would hand a peer disjoint rows, letting it spend the same budget against its own pre-claim snapshot". That is write skew on a shared budget. With NOWAIT, a second dequeuer gets 55P03 at once, and _queue.py catches it as LockNotAvailable and tries again at the next poll.

- A higher level for the budget. With a shared budget, the dequeue runs SET TRANSACTION ISOLATION LEVEL REPEATABLE READ. It uses SERIALIZABLE when the queue is partitioned and a global concurrency or rate limit covers all partitions. In the partitioned loop, a 55P03 or a 40001 skips that partition until the next poll. In the queue without partitions, a 40001 doubles the polling interval, up to at least 120 s.

- SERIALIZABLE by default for application transactions. @DBOS.transaction defaults to isolation_level = "SERIALIZABLE", and its runner retries 40001, 40P01 and connection errors, as the retry section showed, with no attempt cap.

Questions to answer by reading, not by changing anything.

- Which anomaly does choice 1 prevent, and what does NOWAIT cost when ten workers poll one queue?

- Why is REPEATABLE READ enough without partitions, and not with them? Use the dangerous structure of the SERIALIZABLE section.

- What would choice 3 do to a transaction that also runs a pgvector search?

That completes the five ideas, and the recall section below lists them with the section that taught each.

Go deeper: the pattern's promise, the sequence rule, a cursor that never skips, and measured relays
The pattern's promise. The service should "first store the message in the database as part of the transaction that updates the business entities". The benefit: "Messages are guaranteed to be sent if and only if the database transaction commits". taskqueue.py --check dual-write stops the worker right after COMMIT. The naive version then has a done task and no event, and the outbox version has its event row, which the relay publishes. The change itself is one conditional UPDATE with the owner check of the claim section.

The sequence rule, from the docs. Sequence changes "are immediately visible to all other transactions and are not rolled back", and "nextval and setval calls are never rolled back". In the post's words, "the transaction that created events 187 and 188 started before the transaction that created 189", and "it committed afterwards".

Duplicates, from the sources. --crash-before-mark is expected to show the repeat as one "delivered twice" line, after the check waits out the relay's lease, --relay-lease-ms, default 1,000. The pattern's own page says the relay "might publish a message more than once", so "a message consumer must be idempotent". Debezium's outbox event router puts the event id in a header: "You can use this ID, for example, to remove duplicate messages." The consumer table's design is inferred, and its parts are the ON CONFLICT rule of the constraint section and Debezium's id header.

A cursor that never skips. Some relays must keep a cursor, for example to replay from a position. Each outbox row then stores the ID of the transaction that wrote it, in a column of type xid8, the 64-bit form of a transaction ID, with the default pg_current_xact_id(). The relay reads only rows whose ID is below the snapshot's xmin, in transaction ID order.

-- after Dudycz 2022, with this schema's names, as a row comparison. A design, not the lab's SQL.
-- pg_cast.dat at REL_17_11, lines 96 to 97, has no cast from bigint to xid8, so the saved cursor goes in as text.
SELECT id, task_id, event_type FROM tq_outbox
WHERE (xid, id) > (%(last_xid)s::text::xid8, %(last_id)s)
  AND xid < pg_snapshot_xmin(pg_current_snapshot())
ORDER BY xid, id LIMIT 100;

Every transaction with an ID below the snapshot's xmin has ended, by the snapshot rule, so no row can appear behind the cursor later. Three conditions make this hold.

- Each row carries the ID of its own top-level transaction, and pg_current_xact_id() returns that ID even inside a savepoint.

- The cursor moves only to a row that the same query returned.

- pg_current_snapshot() is the snapshot that the query reads with, which it is in PostgreSQL 17.

The order is the order in which transactions got their IDs, not their commit order. Its cost is that one long transaction that has written stops the relay at its ID. Transaction IDs are shared by every database of the server, so that transaction can be anywhere on it. That cost is inferred from the same rule. taskqueue.py --self-test checks the rule on a simulated outbox, in simulate_xid_relay, and the lab's relay does not use it.

Measured relays. This course found no production post about a PostgreSQL outbox with measured throughput or latency. One team writes events into the WAL with pg_logical_emit_message() for Debezium, instead of an outbox table. Another reads MySQL's change log with Debezium. So neither is an outbox table with numbers. What happens when the consumer is another service and one side fails halfway is in course 5, Phase 2.

Expected outputs. --check outbox --variant naive --relay-level serializable: FAIL outbox: committed events [1, 2], published [2], never published [1]. The fixed run with --crash-before-mark publishes [2, 1, 2] and passes, after one "delivered twice" line. Neither was run by the author yet.

DBOS's line numbers. The reading example reads _sys_db.py lines 4215, 4229 to 4234, 4236 to 4242, 4372 and 4391, _queue.py lines 943 to 950, 954 and 960 to 965, _dbos.py line 1173, and _utils.py lines 154 to 183, in DBOS 2.31.0. If Mission HQ upgrades DBOS, these line numbers will move.

Evidence
The pattern: Chris Richardson, "Pattern: Transactional outbox", microservices.io. Sequences: PostgreSQL 17 docs 13.2 and CREATE SEQUENCE. The relay code: phase03_transactions/taskqueue.py line 230, and the outbox index at line 154. The event id header: Debezium 3.7 documentation, Outbox Event Router. The cursor: Oskar Dudycz, "How Postgres sequences issues can impact your messaging guarantees", 2022-10-28, and xid8funcs.c line 378 at REL_17_11, with Rogov page 77 for savepoints. The other relays: SeatGeek, 2025-02-07, and Shopify, 2021-03-12. The skipped events in production: Justin Giancola, PN Tech blog, "Fun with Multiversion Concurrency Control", part 1 of 2020-03-06 and part 2 of 2020-05-15, dates from the page addresses. DBOS: version 2.31.0 from the installed package's METADATA, and the source in Mission HQ's virtual environment.

## What you can do now, and what comes next

- A read takes no lock. So a decision can rest on a state that another commit has already changed. The first three sections showed where your ORM opens the transaction and what an old snapshot misses. They also showed how the place of the second write names the anomaly.

- After a wait for a locked row, READ COMMITTED tests the WHERE clause again on the newest version of that one row. The re-check section and the two lock sections showed it, with the waits you see in pg_stat_activity, on RDS, and in the log.

- The strictest level adds no new lock waits. It ends one transaction of a dangerous pair with 40001, so the client starts it again from BEGIN. The SERIALIZABLE, retry and savepoint sections showed it.

- A constraint or a row that always exists keeps a rule for every writer. FOR UPDATE cannot lock a row that nobody has inserted yet. The constraint section and the pooler section showed it.

- Locks end at COMMIT. So a claim needs a lease and a reaper, and an event needs a relay that polls the rows not yet sent. The two task-queue sections showed it, with the indexes, retention and signals a dashboard watches.

You can now name an anomaly and pick what stops it, and read a lock wait at work. You can also build a queue whose claims and events survive a crash. Phase 4 asks why the planner chose a sequential scan over your index, and what a migration does to a table. It also shows how vacuum removes the dead versions this lesson left.

## Lab: reproduce each anomaly, then stop it

Open the lab: E1 to E21, written and reviewed, self-tests run, server labs not run by the author yet
The lab and the checkpoint come from the phase word for word, so they name the phase's sections by number. Sections 3.1 and 3.2 are the first two sections of this lesson, with the savepoint parts in "What does a savepoint cost on a busy server?". Section 3.3 is "Which anomaly is it, and which level stops it?" and the re-check section after it. Section 3.4 is "Who waits for whom, and how do you see it?" and "What do foreign keys and NOTIFY lock for you?". Section 3.5 is the SERIALIZABLE section and the retry section. Section 3.6 is "Which fix holds a rule: a lock, a version check, or a constraint?" and the pooler section after it. Section 3.7 is the two task-queue sections at the end. Two parts of 3.7 sit earlier: its approval is in the constraint section, and its scope check is in "Which anomaly is it, and which level stops it?".

Where it runs, and what it costs. Everything runs on your laptop and costs nothing. The labs need your local PostgreSQL 17 at /tmp:5432, in the database storage_lab, which Phase 1 created. E21 also needs the pgvector extension. They use Python 3.12 or later with psycopg 3.3.6, which pyproject.toml pins. The model mvcc_model.py and every --self-test run with no server. Run all the commands from elite-storage/code/. Time: about 4.5 hours for the reading in the phase, and the labs take 4 to 5 hours.

The labs below are written and reviewed for PostgreSQL 17, but were not run against a server by the author. The owner chose to keep them unrun. Every --self-test was run offline on the author's machine on 2026-10-20, and each one passed. Every other "Expected" line says "Not run by the author yet." and then gives the expected shape. Each value comes from the docs or source that this phase cites, or from reading the code by hand. None of them is a measurement. Each script fixes the order of steps. So the results that do not depend on time should match exactly. Times, such as the deadlock wait, depend on your machine.

What you build. You build three things. First, two-session reproductions of every anomaly of this phase, on your PostgreSQL 17. Second, an offline model of the same rules. Third, the audit of the task queue:

File | What it holds | Self-test checks

shared/pglab.py | sessions driven step by step, the lock-wait probe, run_with_retry, the database guard | retry of the whole transaction, a 40001 at COMMIT, the attempt cap, 25P02 for the WRONG retry

phase03_transactions/mvcc_model.py | row versions, snapshots, first-updater-wins, SSI, waits and deadlocks, six histories | the snapshot example of Table 9.83, the matrix of section 3.3, each rule removed in turn

phase03_transactions/lost_update.py | the budget spend, four strategies, two schedules, --retry, --wrong-retry | the invariant, the SQL of each strategy

phase03_transactions/write_skew.py | the approvers on call, --fix lock-rows, --show-locks | the rule and the invariant

phase03_transactions/phantom.py | the phantom read, the running limit, three fixes, one a partial unique index | the limit arithmetic, the SQL of each fix

phase03_transactions/deadlock.py | two transfers in opposite order, --ordered, --retry | that opposite order forms a cycle and one order does not

phase03_transactions/contention.py | five strategies under 1 to 64 hot rows | 1 / (1 − p), n (n + 1) / 2, the percentile method

phase03_transactions/taskqueue.py | the schema, six checks with the lease and the poison task, --unique-decision, a relay that commits before it publishes, the outbox index, retention and backlog query, exit code 1 on a broken invariant | the claim in the model, both relays and the xid8 cursor on a simulated outbox, no open transaction during a publish, the lease, reaper and failed-state SQL, the three partial indexes

phase03_transactions/lockwatch.py | a queue of waiters on one row, the "who blocks whom" query, pg_locks.waitstart, the pg_wait_events summary, log_lock_waits, a multixact and its members | the head of a wait chain on Rogov's printed rows, the log-line format, the 17 view join

phase03_transactions/queue_horizon.py | a claim loop with and without one open snapshot, and the 17 VACUUM VERBOSE lines | the percentile method, the claim and index SQL, the 17 and 14 report lines parsed

phase03_transactions/subxact.py | 70 or 10 subtransactions in one session, its cache, and another session's extra cache reads | 64 cached, the 65th overflows, two lookups per row, the DO block refuses a string

phase03_transactions/ddl_snapshot.py | TRUNCATE, DELETE and a rewriting ALTER against an old REPEATABLE READ snapshot | which DDL empties the old snapshot's view, and that a prior read makes the DDL wait

phase03_transactions/upsert_race.py | MERGE against INSERT ... ON CONFLICT for a row that does not exist yet | the predicted SQLSTATE and count for each form and level

phase03_transactions/notify_commit.py | commits per second with and without NOTIFY, and waiters on the NOTIFY lock | the lock tag in pg_locks, the wait event name, the report arithmetic

phase03_transactions/vector_ssi.py | two agents at SERIALIZABLE, through a B-tree or an HNSW index | the prediction from ampredlocks, the queries each agent sends

Every PostgreSQL lab refuses a database whose name does not start with storage_lab. It drops and creates only tables that start with tq_. The demonstration of this phase is E4, E5 and E10. E4 and E5 reproduce two anomalies on demand, and stop each with a named mechanism. E10 hardens the task queue's three transactions, each with a check that fails at the old level.

The first uv run installs psycopg 3.3.6, so it needs the network once. E21 also needs the pgvector extension in your server. The script says so and exits with 2 if it is missing.

-
 E1 (offline). Run every self-test of this phase, then the earlier phases' self-tests.

-
Run: for f in shared/pglab.py phase03_transactions/*.py; do echo "$f"; uv run python "$f" --self-test; done

-
Then run: for f in shared/durable.py phase01_durability/*.py phase02_structures/*.py; do echo "$f"; uv run python "$f" --self-test; done

-
Expected, run by the author on 2026-10-20: self-test passed after each of the 15 Phase 3 files, and after each of the 13 earlier files. The new files print, for example, subxact: 9 checks and taskqueue: 26 checks. This phase added shared/pglab.py and a dependency, and changed no earlier file.

-
If it fails: the assertion message names the rule or the number. Compare it with the section it comes from before you change any code.

-
Teaches: the offline checks cover the SQL text and the models. The invariant of each --check needs a server, so the server runs are the real test of those rules.

-
 E2 (offline). The model's matrix, and the model with one rule removed.

-
First write your prediction for every cell of the matrix in section 3.3.

-
Run: uv run python phase03_transactions/mvcc_model.py, then the same with --no-ssi, then with --no-first-updater-wins.

-
Expected: Not run by the author yet. The first run prints the matrix of section 3.3, with its deadlock row. With --no-ssi, write-skew and phantom-limit become BROKEN under serializable. With --no-first-updater-wins, lost-update becomes BROKEN under repeatable-read. Under serializable it still holds, with T2 40001. The SSI check catches the pair, because each transaction read the row that the other wrote. Add --history lost-update --level serializable --trace to see the check doom T2 at its UPDATE and fail it at COMMIT.

-
Teaches: snapshot isolation stops lost updates with one rule, and serializable stops write skew with one more.

-
 E3 (local). Check the server and its settings.

-
Run: uv run python shared/pglab.py --setup.

-
Expected: Not run by the author yet. created database storage_lab only if Phase 1 did not create it. Then the settings in name order: deadlock_timeout 1000ms, default_transaction_isolation read committed, idle_in_transaction_session_timeout 0ms, lock_timeout 0ms, max_pred_locks_per_page 2, max_pred_locks_per_relation -2, max_pred_locks_per_transaction 64, server_version 17.x and transaction_timeout 0ms. A packaged server may add text to the version, such as "(Homebrew)". These are the defaults that sections 3.4 and 3.5 cite, from guc_tables.c at REL_17_11. On PostgreSQL 14 the transaction_timeout line is missing.

-
If it fails with a connection error: check that the server runs, with pg_isready -h /tmp -p 5432.

-
Teaches: your server's defaults, before any lab depends on them.

-
 E4 (break-it, local). Part of the demonstration: the lost update, and three ways to stop it.

-
Run: uv run python phase03_transactions/lost_update.py --level read-committed, then --level repeatable-read, then --level repeatable-read --retry, then --level read-committed --strategy atomic.

-
Expected: Not run by the author yet. Read committed: an obs line names T1's pid in pg_blocking_pids(T2). T2's UPDATE returns 1 row after its wait, then RESULT: BROKEN. credits 20 after 2 committed spend(s) of 80 from 100. Repeatable read: T2's UPDATE ends in ERROR 40001: could not serialize access due to concurrent update, and RESULT: holds. credits 20 after 1 committed spend(s) of 80 from 100. With --retry, one more line says attempt 1: refused, 20 < 80. With --strategy atomic, T2's UPDATE returns 0 rows after its wait, and the result holds.

-
Then try --schedule commit-first at read committed. That order is Berenson's history H4. No obs line appears, because T2 never waits, and the result is still BROKEN.

-
Teaches: READ COMMITTED re-checks the WHERE clause after a wait, and REPEATABLE READ refuses to change a replaced row.

-
 E5 (break-it, local). Part of the demonstration: write skew, and SERIALIZABLE.

-
Run: uv run python phase03_transactions/write_skew.py --level repeatable-read, then uv run python phase03_transactions/write_skew.py --level serializable --retry.

-
Expected: Not run by the author yet. Repeatable read: two UPDATEs of 1 row each, two successful COMMITs, no wait, and RESULT: BROKEN. 0 approver(s) on call. Serializable: one ERROR 40001: could not serialize access due to read/write dependencies among transactions, expected at B's COMMIT, because A commits before it, by section 3.5, with a DETAIL: Reason code: line and HINT: The transaction might succeed if retried.. Then count 1, bob stays on call, and RESULT: holds. 1 approver(s) on call.

-
Then run --level read-committed --fix lock-rows. B's lock read waits for A, returns only Bob's row, and the result holds.

-
Teaches: write skew raises no error below SERIALIZABLE, and SERIALIZABLE turns it into a 40001 that a retry absorbs.

-
 E6 (break-it, local). Phantoms: the read that PostgreSQL stops, and the decision it does not.

-
Run: uv run python phase03_transactions/phantom.py --case reread --level read-committed, then --case reread --level repeatable-read.

-
Then run: uv run python phase03_transactions/phantom.py --case limit --level repeatable-read, then --case limit --level read-committed --fix for-update, then --case limit --level read-committed --fix parent-row, then --case limit --level read-committed --fix unique-index.

-
Expected: Not run by the author yet. first count 2, second count 3 at read committed, and first count 2, second count 2 at repeatable read. The limit case at repeatable read: RESULT: BROKEN. 2 running task(s) for acme, limit 1. With --fix for-update, both lock reads print 0 row(s), and the result is still BROKEN. With --fix parent-row, W2's slot reservation waits, then updates 0 rows, and the result holds. With --fix unique-index, W2's claim waits for W1, then ends in ERROR 23505: duplicate key value violates unique constraint "tq_one_running_per_tenant", and the result holds.

-
Teaches: a snapshot hides new rows from a re-read. A decision about an empty set needs SERIALIZABLE, a parent row, or for a limit of 1 a unique index.

-
 E7 (break-it, local). A deadlock, its report, and the fix.

-
First predict which session fails, and after how long.

-
Run: uv run python phase03_transactions/deadlock.py, then --retry, then --ordered.

-
Expected: Not run by the author yet. Two "sent, waiting for the server" lines. About 1 second after T2's line, T2 ends with ERROR 40P01: deadlock detected, two DETAIL lines that each start with Process, and HINT: See server log for query details.. The victim is inferred from the lmgr README, so T1 may be the victim on your server. RESULT: total credits 200, unchanged. With --retry, the victim's transfer runs again and succeeds. With --ordered, no ERROR line appears.

-
If it prints LAB ERROR about a wait: another session holds a lock on tq_budget. Close other psql sessions on storage_lab.

-
Teaches: a cycle is broken after deadlock_timeout, and a fixed lock order prevents it.

-
 E8 (local). See SIREAD locks and lock waits from a third session.

-
Run: uv run python phase03_transactions/write_skew.py --level serializable --show-locks.

-
Expected: Not run by the author yet. After the two counts, obs lines with SIReadLock for both sessions. The table has two rows, so the planner should use a sequential scan. The docs say that a sequential scan takes a relation-level predicate lock. So expect locktype relation on the table tq_oncall. That is inferred, and was not run. Both sessions print the application name storage_lab, so the lines do not say which session holds which lock.

-
Teaches: SIREAD locks are visible in pg_locks, and a sequential scan locks the whole table.

-
 E9 (local). Optimistic against pessimistic, by contention.

-
First predict the retries of version at 1 hot row and at 64, from section 3.6.

-
Run: uv run python phase03_transactions/contention.py --workers 8 --increments 200 --hot-rows 1,64, then the same with --think-ms 2.

-
Expected: Not run by the author yet. No numbers are given, because none were measured. The shape: naive shows lost above 0 at 1 hot row, and the other strategies show 0. version and serializable show many retries at 1 hot row and few at 64. The for-update rows show 0 retries. With --think-ms 2, the p99 of for-update at 1 hot row grows. A waiting worker waits for each earlier worker's 2 ms of work. Waiters are not served in arrival order, section 3.4. So the p99 can pass the 7 × 2 = 14 ms of a fair queue of 8 workers. That is inferred, and not run.

-
Teaches: contention decides whether waiting or redoing costs less.

-
 E10 (local). Part of the demonstration: the task-queue audit, with checks that fail at the old level.

-
Run: uv run python phase03_transactions/taskqueue.py --check all --variant naive --level read-committed; echo "exit $?".

-
Then run: uv run python phase03_transactions/taskqueue.py --check all --variant fixed --level read-committed; echo "exit $?".

-
Expected: Not run by the author yet. The naive run prints FAIL for claim, approval, outbox, lease, dual-write and poison, and exit 1. The claim line is the one in section 3.7. The fixed run prints PASS for all six, and exit 0. The lease check sleeps for its lease of 300 ms and 0.2 s more. The poison check sleeps that long five times, about 2.5 s. The fixed outbox check also prints backlog: 0 unsent, oldest 0 s and a retention: line.

-
Then run --check claim --variant naive --level repeatable-read --retry. Expected: worker B gets 40001, its retry finds no queued task, and the check prints PASS.

-
Then run --check approval --variant naive --unique-decision. Expected: Bob's INSERT waits, then ends in ERROR 23505, and PASS approval: task 2 has decision(s) ['approve'], state awaiting_approval.

-
Then run --check lease --variant fixed. Expected: the reaper line says requeued [1], worker B claims task 1, worker A's late completion updates 0 row(s), and PASS lease: task 1 is done, owner B.

-
Then run --check poison --variant naive, then --variant fixed. Expected: five claims by w1 to w5. The naive reaper says requeued [] after the fifth, and FAIL poison: task 1 is running after 5 attempt(s). The fixed reaper says failed [1], and PASS poison: task 1 is failed after 5 attempt(s).

-
Teaches: each fix changes one statement, at the default level. Each one has a test that fails without it.

-
 E11 (break-it, local). The relay that no isolation level fixes, and at-least-once delivery.

-
Run: uv run python phase03_transactions/taskqueue.py --check outbox --variant naive --relay-level serializable.

-
Then run: uv run python phase03_transactions/taskqueue.py --check outbox --variant fixed --crash-before-mark.

-
Expected: Not run by the author yet. The naive relay at serializable: FAIL outbox: committed events [1, 2], published [2], never published [1]. The fixed relay with the crash: pass 1 publishes [2] and dies before its mark. Pass 2 publishes [1], because event 2's relay lease has not expired. After the lease, pass 3 publishes [2] again. Then delivered twice: [2], the backlog line with 0 unsent, and PASS outbox: committed events [1, 2], published [2, 1, 2], never published [].

-
Then add --level serializable to the first command, so the workers run at SERIALIZABLE too. Expected: the same FAIL, by section 3.7. That is inferred.

-
Teaches: a relay that tracks ids is wrong at every level, and the fixed relay needs an idempotent consumer.

-
 E12 (break-it, local). The WRONG retry against the real server.

-
Run: uv run python phase03_transactions/lost_update.py --level repeatable-read --wrong-retry.

-
Expected: Not run by the author yet. T2's first UPDATE ends in ERROR 40001. Its resent UPDATE ends in ERROR 25P02: current transaction is aborted, commands ignored until end of transaction block. The result holds, because T2 spent nothing.

-
Teaches: after a 40001, only ROLLBACK and a new transaction help. E16 shows what else the aborted state accepts.

-
 E13 (live). Lock waits as you see them at work.

-
Run: uv run python phase03_transactions/lockwatch.py --case queue, then the same with --log-lock-waits, then --case multixact.

-
Expected: Not run by the author yet.

- --case queue: the first table shows the holder with Client, ClientRead and []. The script prints each list of pids as a Python list. The first waiter shows Lock, transactionid and the holder's pid. The two later waiters show Lock and tuple, as on Rogov's page 219. In pg_locks, each waiter has one row with granted f and a waited_s value from waitstart. The table also lists granted rows, such as each session's lock on its own transaction ID. The pg_wait_events table shows Lock | tuple | 2 and Lock | transactionid | 1, each with its description, and Client | ClientRead | 1 for the holder. After the holder commits, the remaining waiters show transactionid, as in Rogov's PostgreSQL 14 run, page 220. Whether a tuple wait appears again on 17 was not checked. The last two lines give the arrival order, the order that got the row, and the RESULT. The two orders may differ. Either result agrees with section 3.4.
- --log-lock-waits, as a superuser or a role given GRANT SET ON PARAMETER: the server log gets at least one still waiting for line per waiter. A waiter that waits twice can write two. Its first wait is on the tuple, and its second wait is on a transaction ID. Each logged wait gets one acquired line when it ends. As another role, the script says that the settings need a superuser, and it exits with 2.
- --case multixact: B's INSERT returns with no wait. If the extension can be created, pgrowlocks shows multi t and the two modes. On PostgreSQL 17 expect {"For No Key Update","For Key Share"}, the reverse of Rogov's order. Rogov's 14 printed Key Share and No Key Update, and 17 adds For, pgrowlocks.c lines 200 and 206. PostgreSQL 17 sorts the members of a multixact by transaction ID, multixact.c line 1771. A got its ID first. That order is inferred from the source. pg_get_multixact_members(xmax) then prints two rows, A's xid with nokeyupd and B's xid with keysh.

-
If it fails with LAB ERROR about a wait: another session holds a lock on tq_lw_row. Close other psql sessions on storage_lab.

-
Teaches: the transactionid and tuple waits, waitstart, and the log lines that name them.

-
 E14 (local). A deadlock as a counter and as log lines.

-
Run: psql -h /tmp -p 5432 -d storage_lab -Atc "select deadlocks from pg_stat_database where datname = current_database()", then uv run python phase03_transactions/deadlock.py, then the psql command again.

-
Expected: Not run by the author yet. The second number is one higher than the first. A backend adds the deadlock to its pending counts, pgstat_database.c lines 125 to 134, REL_17_11, and flushes them at most once a second when idle, PGSTAT_MIN_INTERVAL 1000 ms at pgstat.c line 118. The victim's session closes when deadlock.py ends, which flushes its counts. So the new value should be there at once. If it is not, wait a second and read it again. That timing is inferred from the source. PostgreSQL 14 sent the counts to a separate statistics collector process, which 15 removed. Then find the deadlock's ERROR in the server log. There, its DETAIL has one more line per process, Process %d: %s, with each query, from deadlock.c line 1123. If log_lock_waits is on, the victim's log also has a detected deadlock while waiting for ShareLock on transaction line. proc.c line 1499 writes these lines only when log_lock_waits is on.

-
Teaches: a deadlock shows as a counter and as log lines before anyone reports it.

-
 E15 (break-it, local). One open snapshot slows every claim.

-
First predict how many dead row versions 5,000 worked jobs leave while a snapshot is held.

-
Run: uv run python phase03_transactions/queue_horizon.py, then the same with --index pkey.

-
Expected: Not run by the author yet. No times are given, because none were measured. In the baseline, the median claim time stays about flat over its 10 batches. During the hold it grows from batch to batch. n_dead_tup grows by about 2 × 500 = 1,000 per batch. Each job leaves two dead versions: the replaced queued version and the deleted running version. The statistics lag, so that column may trail by a batch.

-
The VACUUM VERBOSE lines on PostgreSQL 17, with example numbers where the run decides them. The format is from vacuumlazy.c lines 660 and 672, REL_17_11:
  VACUUM VERBOSE: tuples: 0 removed, 10100 remain, 10000 are dead but not yet removable
  VACUUM VERBOSE: removable cutoff: 7421, which was 10005 XIDs old when operation ended
  removable cutoff 7421 equals the holder's backend_xmin 7421

-
The third number of the first line is about 2 × 5,000 = 10,000. The "remain" count includes those dead versions, by vacuumlazy.c lines 1043 to 1045. The "removed" count can be above 0 if the baseline's dead versions were still there. The cutoff equals the holder's backend_xmin, and the script prints that comparison. After the release and a VACUUM, the median falls back toward the baseline. With --index pkey, expect the same shape. Which index degrades faster was not checked.

-
The first version of this lab matched only the PostgreSQL 14 text "cannot be removed yet". On 15 and later that text does not exist, so the VACUUM line was never printed, with no error. The script now matches both forms, and its self-test parses a 17 report and a 14 line.

-
If it fails with "the queue ran empty": raise --backlog.

-
Teaches: one snapshot held anywhere slows a busy queue, and the removable cutoff names the snapshot.

-
 E16 (local). What an aborted transaction accepts.

-
Run this, which sends two transactions to one psql session:
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

-
Expected: Not run by the author yet. The first transaction prints ERROR:  division by zero, then ERROR:  current transaction is aborted, commands ignored until end of transaction block, then ROLLBACK as the reply to COMMIT. Rogov, pages 78 and 79, prints these three replies on PostgreSQL 14. The second transaction prints the division error, then ROLLBACK for the ROLLBACK TO SAVEPOINT, then after_savepoint with 1, then COMMIT.

-
Teaches: COMMIT in an aborted transaction rolls it back, and ROLLBACK TO SAVEPOINT is the way to go on inside it.

-
 E17 (break-it, local). One session's savepoints change every other session's snapshots.

-
First predict: after 70 subtransactions, what do subxact_count and the overflow flag show?

-
Run: uv run python phase03_transactions/subxact.py --subxacts 70, then --subxacts 10.

-
Expected: Not run by the author yet. With 70: A's cache: subxact_count 64, overflowed True. The at-work query prints A's pid with 64 and true. O counts 0 visible row(s), and the subtransaction SLRU blks_hit grows by about 2 × 70 = 140. With 10: count 10, overflowed False, and blks_hit grows by about 0. The SLRU numbers are inferred from XidInMVCCSnapshot and SubTransGetTopmostTransaction.

-
If it fails with an error about pg_stat_get_backend_subxact: the server is older than 16.

-
Teaches: the 65th subtransaction makes other sessions read pg_subtrans, and PostgreSQL 16 and later show which session did it.

-
 E18 (break-it, local). An old snapshot sees an empty table after a TRUNCATE.

-
First predict which of truncate, delete and rewrite keep the 3 rows visible to the old snapshot.

-
Run: uv run python phase03_transactions/ddl_snapshot.py --ddl truncate, then --ddl delete, then --ddl rewrite, then --ddl truncate --touch-first.

-
Expected: Not run by the author yet. truncate: RESULT: BROKEN. R's old snapshot saw 0 row(s), and exit 1. delete: RESULT: holds, 3 rows. rewrite: 0 rows, BROKEN. With --touch-first, the obs line says J waits: Lock / relation, R reads 3 rows, and the result holds. No run raises an error.

-
Teaches: TRUNCATE and table rewrites are not MVCC-safe, and the ACCESS SHARE lock of a prior read is the only protection.

-
 E19 (break-it, local). MERGE loses a count that ON CONFLICT keeps.

-
Run: uv run python phase03_transactions/upsert_race.py --form merge, then --form on-conflict, then --form on-conflict --level repeatable-read.

-
Expected: Not run by the author yet. merge: B's statement waits, then ERROR 23505: duplicate key value violates unique constraint "tq_ur_counts_pkey", and RESULT: BROKEN. n = 1 after 2 counts. on-conflict: B waits, then returns 1 row, and RESULT: holds. n = 2. At repeatable-read, B fails with the concurrent-update form of 40001, because A's new row is not in B's snapshot. So n stays 1, and that run needs the retry loop of section 3.5.

-
Teaches: MERGE decides INSERT or UPDATE once, from its snapshot. ON CONFLICT lets the unique index decide.

-
 E20 (local). NOTIFY in each transaction makes commits take turns.

-
Run: uv run python phase03_transactions/notify_commit.py, then --workers 32.

-
Expected: Not run by the author yet. This exercise gives only a shape, because nobody measured its rates. The plain line shows waiters on object 0 of class 1262 in about 0% of samples. The notify line shows them in most samples, with a max near the worker count, and fewer commits per second. The RESULT ratio is below 1, and lower at 32 workers than at 16. The lower ratio at 32 is inferred from group commit, Phase 1, section 1.6.

-
If it fails with too many clients: lower --workers below max_connections, default 100.

-
Teaches: the NOTIFY lock serializes every committing writer that sent a NOTIFY, and pg_locks shows it as an object lock.

-
 E21 (break-it, local, needs pgvector). A vector search at SERIALIZABLE conflicts with every serializable insert.

-
Run: uv run python phase03_transactions/vector_ssi.py --path btree, then --path hnsw.

-
Expected: Not run by the author yet. btree: the SIReadLock rows show page on tq_vs_memory_agent_id and tuple on tq_vs_memory for each pid. Both commit, RESULT: holds. 40001 for nobody. hnsw: the rows show relation on tq_vs_memory_embedding_idx for each pid. One session fails with the read/write-dependency form of 40001, and the script prints RESULT: BROKEN. Where the error comes is inferred.

-
If it fails with "pgvector is not available": install the extension, or skip this exercise. Its result follows from indexam.c lines 225 to 228 and 319 to 320.

-
Teaches: an index without fine predicate locks turns every search into a table-wide read for SSI.

Open the eight code-reading checks

-
Check 1. Open phase03_transactions/mvcc_model.py:298, the conflict branch of update(). It raises Blocked while the other writer is still running, and raises 40001 only after that writer has committed. Suppose the two checks were swapped. What would a REPEATABLE READ transaction do when the other writer later rolls back? What does the PostgreSQL 17 docs' text in section 13.2.2 say should happen?

-
Check 2. Open shared/pglab.py:411, the retry loop. In it, COMMIT sits inside the try. Move it outside, after the loop, in your head. Which history of section 3.5 would then end in an error that reaches the caller? Which line of the self-test of pglab.py would fail?

-
Check 3. Open phase03_transactions/taskqueue.py:169, claim_fixed. Replace SKIP LOCKED with NOWAIT, the option of section 3.6 that raises 55P03. Which worker now gets the error, and at which step of the claim check? Is the queue still correct then? Take ten workers and one queued task. How many fail on each poll, and what must each one do next?

-
Check 4. Open phase03_transactions/phantom.py:98, the slot reservation. A task that finishes must give its slot back. Write the UPDATE that does it. Say which transaction it must share, and what goes wrong if it runs in a transaction of its own.

-
Check 5. In any repository you own that uses PostgreSQL, run grep -rn "FOR UPDATE\|isolation\|SERIALIZABLE\|40001\|40P01" <your repo>/. Then find three places that read a value and write based on it. For each one, write its invariant and name the anomaly it can suffer at its level. Then say which check would show it.

-
Check 6. Open phase03_transactions/taskqueue.py:180, the reaper, and SQL["complete"] below it. Suppose complete checked only id = %s AND state = 'running', without the owner. Walk through --check lease --variant fixed with worker A paused, not dead. How many workers would record a result for task 1? Which line of check_lease would then show it?

-
Check 7. Open phase03_transactions/taskqueue.py:230, the body of relay_pass(). Move the first conn.execute("COMMIT") below the publish loop, in your head. Which check of _self_test fails, and why? What would a broker that takes 20 seconds then do to age(backend_xmin) on the server?

-
Check 8. Search your own PostgreSQL code for the statements of this phase's production layer: grep -rn "requires_new\|atomic(\|SAVEPOINT\|MERGE INTO\|NOTIFY\|pg_notify\|TRUNCATE\|ISOLATION LEVEL" <your repo>/. For each hit, name the section of this phase it belongs to. Then say whether it runs on a hot path, inside a long transaction, or from many writers at once. Those three are the cases where this phase's costs appear.

## Checkpoint: ten questions with answer sketches

Open the checkpoint. Answer each question before you open its sketch
The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

1. Test-out, explain. Use the approvers' case. Explain write skew: what each transaction reads and writes. Explain why snapshot isolation allows it, in terms of first-updater-wins. Then explain what SERIALIZABLE in PostgreSQL does differently. Say which edges it records and which structure it looks for. Say what the client must do when it finds one.

Answer sketchEach approver reads both rows and writes only its own. First-updater-wins fails a transaction only when it changes a row that a concurrent transaction replaced. No row was written twice, so both commit, and the rule breaks with no error. SERIALIZABLE in PostgreSQL also records rw-antidependencies. A rw→ B, because A read Bob's row and B wrote a newer version of it. B rw→ A in the same way. Two rw edges in a row between concurrent transactions are the dangerous structure of Cahill and others, 2008. When A commits, B is a pivot whose out-edge points to a committed transaction, so B fails with 40001. The client must roll back and run B's whole transaction again. The retry counts 1 and stays on call.

2. Test-out, predict. tq_budget holds acme 100 and beta 100, and has no CHECK constraint on credits. The rule is that their sum stays at or above 0. Each transaction reads SELECT sum(credits) over both rows, and if the sum is at least 150, debits 150.(a) T1 debits acme and T2 debits beta, both at REPEATABLE READ, both reading the sum before either writes. Can the rule break, and what are the final balances?(b) Both debit acme with SET credits = credits - 150, at READ COMMITTED. Can the rule break, and does any session wait?(c) Case (b) at REPEATABLE READ.(d) Case (a) at SERIALIZABLE.

Answer sketch(a) Yes, the rule can break. Both read 200 from their snapshots, and each debits a different row. Final: acme −50, beta −50, sum −100. That is write skew, the shape of Berenson's H5. No session waits in this case. (b) Yes, it breaks, and T2 waits. T2's UPDATE waits for T1's row lock. Then it re-checks tenant = 'acme' on the new row, which still matches. It debits again: 100 − 150 − 150 = −200, and the sum is −100. No update is lost, because both debits apply. But T2 decided on a sum that was out of date. (c) T2 waits, then gets 40001 when T1 commits. Its retry reads a sum of −50 + 100 = 50, which is below 150. So it does not debit, and the rule holds. (d) One transaction gets 40001, expected at the second COMMIT. Its retry reads 200 − 150 = 50 and does not debit, and the rule holds.

3. Test-out, demonstrate. Run E4, E5 and E10. Show the lost update and the write skew breaking, and the named mechanism that stops each one. Then show the claim check failing with the naive code at READ COMMITTED and passing with the fix. Explain why the check is deterministic and not a lucky timing.

Answer sketchFrom the runs. Expected shapes are in E4, E5 and E10. Lost update at READ COMMITTED: 160 spent from 100. Stopped by REPEATABLE READ's first-updater-wins, with 40001, or by the atomic UPDATE, with 0 rows. Write skew: 0 on call at REPEATABLE READ, stopped by SSI with 40001 and a retry. The check is deterministic because of the lock-wait probe. The script waits until pg_stat_activity shows the second session waiting, with pg_blocking_pids naming the first. Only then does it commit the first. The order is chosen by the test, not by the timing.

4. A colleague says: "We set default_transaction_isolation to repeatable read, so race conditions are gone." Argue for or against. Which of this phase's failures does that change stop, and which does it leave? What new error must the application now handle, and how?

Answer sketchPartly for it, and mostly against it. REPEATABLE READ stops the lost update: E4 at repeatable read gets 40001 instead of 160 spent. It stops read skew, the report that printed 280. It leaves write skew: 0 approvers on call in E5. It leaves the phantoms: 2 running tasks in E6, and 2 decisions in E10. It also does not fix the outbox relay, which no level fixes. It adds a new trap: a TRUNCATE between two reads gives an empty table, E18. The new error is 40001, which every transaction that writes can now raise. The application needs a retry loop of the whole transaction, with COMMIT inside it. It retries only 40001 and 40P01, with a cap and jitter. Without the loop, each 40001 becomes a failed request. Neither Django nor Rails retries it for you. On MySQL InnoDB the same level name would not even stop the lost update, by Hermitage and by Jepsen's MySQL 8.0.34 analysis.

5. This is broken. A nightly job renews subscriptions. For each customer, it moves credits between that customer's tenants, in the order the billing API returns them. The log shows ERROR: deadlock detected five to ten times a night. Each failed renewal waited about one second. What is the cause, how do you confirm it from the DETAIL lines, and what is the fix? Is raising deadlock_timeout a fix for it?

Answer sketchCause: two renewals lock the same two tenant rows in opposite orders, because the API returns tenants in different orders. The DETAIL lines of each error show the cycle. One says that process P waits for ShareLock on transaction X, blocked by process Q. The next one says the reverse. The CONTEXT line names the row of tq_budget each one wanted. Check log_lock_waits and the server log, where each process's query appears. Fix: lock all of one customer's tenant rows first, in one order, with SELECT ... ORDER BY tenant FOR UPDATE, as deadlock.py --ordered does. Keep a retry for 40P01 as a second defense. Raising deadlock_timeout is not a fix. The cycles stay, and each one holds both renewals for longer before one fails. The one-second wait is the default deadlock_timeout. The server confirms it too. pg_stat_database.deadlocks rises by 5 to 10 a night. With log_lock_waits = on, each victim's log has process %d detected deadlock while waiting for ShareLock on transaction %u after %ld.%03d ms. Suppose the job moves credits with one UPDATE over many tenants. Then the cycle can also sit inside two statements' scan orders, as in section 3.4. The same fix holds: lock the rows first, in key order.

6. Show the arithmetic. (a) An optimistic claim conflicts with probability 0.3 per attempt. How many attempts does it need on average? (b) Twenty workers start together on one hot row, and each round lets one commit. How many attempts do they make in total, and how many does the last one make? (c) In Ports and Grittner's RUBiS run, SSI served 422 requests per second with 0.03% failures. S2PL served 208 requests per second with 0.76%. How many failures per hour is each, and what conditions limit what those numbers say about your server?

Answer sketch(a) 1 / (1 − 0.3) = 1 / 0.7 = 1.43 attempts. (b) 20 × 21 / 2 = 210 attempts for 20 commits. The last worker makes 20 of those attempts. (c) This takes one transaction per request, which the paper does not state. SSI: 422 × 3,600 × 0.0003 = 455.8, about 456 failures per hour. S2PL: 208 × 3,600 × 0.0076 = 5,690.9, about 5,691 per hour. Limits: PostgreSQL 9.1, measured in 2012. One 7,200 RPM disk and a Core 2 Quad Q9550 with 8 GB. The RUBiS bidding mix, 85% read-only. Your rate depends on your transactions' read and write sets. Measure the 40001 rate on your own workload.

7. Given these constraints, design. A reminder service emails about each task that has waited 24 hours in awaiting_approval. It must send exactly one email per task. Three scheduler instances run at once, and any of them can be killed at any moment. Design the claim, the state change, the event, and what the email consumer does. Say what each step costs at READ COMMITTED. Name the check from this phase's lab that you would copy to test it.

Answer sketchHere is one possible design among several. Each scheduler runs a short transaction: UPDATE tq_tasks SET reminder_state = 'claimed' ... WHERE id = (SELECT id FROM tq_tasks WHERE state = 'awaiting_approval' AND <waited 24 hours> AND reminder_state IS NULL ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING id. The same transaction inserts a task.reminder_due event into tq_outbox. Two schedulers never take the same task, and nobody waits. The state change and the event commit together, so a killed scheduler leaves either both or neither. The relay claims unsent rows with SKIP LOCKED and a short lease, commits, publishes, and then marks them sent. So a late commit is not skipped, and no transaction waits for the email provider. It delivers at least once, so the email consumer keeps the event ids it has handled and drops a repeat. At READ COMMITTED this costs no retries and no long locks. The email itself happens outside any transaction. Exactly one email then needs one more step. The consumer records the id before it sends, or the email provider accepts an idempotency key. That last part is outside the database and needs its own check. Tests to copy: the claim check and the outbox check with --crash-before-mark from taskqueue.py. reminder_state is a new column this design adds. It is an example, not part of the lab schema. Two more tools fit. A partial unique index, CREATE UNIQUE INDEX ON tq_outbox (task_id) WHERE event_type = 'task.reminder_due', makes one reminder event per task a rule that later code cannot break. If only one scheduler may work at a time, each can start with pg_advisory_xact_lock(hashtext('reminders')). The claim needs no lease here, because the state change and the event commit together, and no slow work happens in between.

8. This is broken. These numbers are an example. The task queue's claim p99 rose from 2 ms to 300 ms over two hours. The queued count grew from 200 to 9,000. Database CPU is up, and nothing was deployed. pg_stat_activity shows one session idle in transaction, with xact_start two hours ago. What is the cause? How do you confirm it with one query and one VACUUM line? What do you change so it cannot recur? At 50 claims per second, how many dead row versions has the queue table gained in those two hours, at two per job?

Answer sketchCause: the idle transaction holds the cleanup horizon two hours in the past. VACUUM cannot remove the queue's dead versions. So every claim's index scan steps over more of them, as in Brandur Leach's 2015 measurements. Claims get slower than jobs arrive, so the queue grows. Confirm: SELECT pid, age(backend_xmin), state, now() - xact_start FROM pg_stat_activity ORDER BY 2 DESC puts that session first. On PostgreSQL 17, VACUUM VERBOSE tq_tasks reports many tuples that "are dead but not yet removable", and a removable cutoff equal to that backend_xmin. PostgreSQL 14 printed "cannot be removed yet" with an oldest xmin instead. Fix now: end the session with pg_terminate_backend(pid), then let VACUUM run. Prevent it in three ways. Set idle_in_transaction_session_timeout per role, and add transaction_timeout on PostgreSQL 17 and later. Keep the partial index on queued rows. Alert on age(backend_xmin), as Phase 4, section 4.5, does. Arithmetic: 50 × 7,200 seconds = 360,000 jobs, and 2 × 360,000 = 720,000 dead row versions.

The production layer. These two questions test the PostgreSQL 17 and managed-service additions of this phase.

9. This is broken. These numbers are an example. Writes fail on Aurora PostgreSQL with This command would create a multixact with 3 members, but the remaining space is only enough for 2 members. The dashboard shows mxid_age at 45% of autovacuum_multixact_freeze_max_age, which is 400 million. A backfill runs 64 workers. Each one inserts child rows that reference the same 40 tenant rows through a foreign key. (a) What is the cause, and why did the dashboard not warn? (b) If all 64 workers lock one tenant row before any vacuum, how many multixacts and members does that row make? (c) Name three changes.

Answer sketch(a) Multixact member space ran out, not multixact IDs. The foreign-key checks take FOR KEY SHARE on the tenant rows, and concurrent lockers of one row make multixacts. The dashboard watched ID age, and PostgreSQL has no metric for member space, as Metronome found. (b) n = 64 lockers make n − 1 = 63 multixacts. They hold n × (n + 1) / 2 − 1 members. That is 64 × 65 / 2 − 1 = 2,079 members for that one row. Across 40 rows that is up to 40 × 2,079 = 83,160 members per round, before vacuum can free the old ones. (c) Lower the concurrency per parent row, or sort the backfill so each worker owns its own tenants. Alert on member storage: the size of pg_multixact/members where you can see it, or the growth of next_multi_offset in pg_control_checkpoint(). Add autovacuum workers. For an enum-like parent, consider a CHECK in place of the foreign key. On 19, members become 64-bit.

10. A colleague says: "Our agents keep memory in pgvector. We set the whole app to SERIALIZABLE, as section 3.5 advises. To wake the relay, a trigger on tq_outbox runs pg_notify for every event." Twenty agents write at once. Argue against both choices, with the mechanism of each. What do you change, and which lab shows each problem?

Answer sketchSERIALIZABLE with pgvector: HNSW and IVFFlat have ampredlocks false, so every serializable search takes a predicate lock on the whole index, and every serializable insert checks the whole index. Twenty agents that search and then save a memory form rw edges with each other, and some get 40001 although they touch different rows. E21 shows it with two agents. Fix: run the vector search at READ COMMITTED, outside the serializable transaction, and pass its result in. pg_notify from every writer: each committing transaction that sent a NOTIFY takes one AccessExclusiveLock on object 0 of class 1262, held across its WAL flush. So the twenty writers commit one at a time, server-wide, and group commit cannot help. E20 shows the shape, and Recall.ai's outage shows the scale. Fix: poll tq_outbox with the partial index on unsent rows, or let one process send the NOTIFY.

## Cheatsheet

Open the one-screen cheatsheet
LEVELS, POSTGRESQL 17 (default READ COMMITTED, same table in 14, 17 and 18)
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
                     Not on a hot standby. pgvector HNSW/IVFFlat: whole-index
                     predicate lock, every SER search conflicts with every
                     SER insert
  MySQL InnoDB       "repeatable read" allows lost update and write skew
                     (Hermitage, Jepsen 8.0.34)

READ COMMITTED RE-CHECK (EvalPlanQual)
  after a row-lock wait, re-runs the WHERE on the new version of THAT row only.
  Subqueries, joins, aggregates keep the old snapshot. Safe one-statement fix:
  the condition reads only columns of the row it changes

ROW VERSIONS AND SNAPSHOTS
  xmin   inserting xid      xmax   deleting or locking xid, 0 if none
  ctid   (page, line pointer). UPDATE = new version, old one keeps xmax
  snapshot xmin:xmax:xip    visible = writer committed before the snapshot
                                      AND replacer did not
  NOT MVCC-SAFE  TRUNCATE, table-rewriting ALTER: old snapshot sees EMPTY table

WHERE THE TRANSACTION IS
  Django   autocommit: one transaction per query. atomic() = BEGIN,
           nested atomic() = SAVEPOINT. select_for_update outside atomic: error
  Rails    nested transaction joins the outer one. requires_new: SAVEPOINT
  psycopg  not autocommit: a SELECT starts a transaction (idle in transaction)

ANOMALIES (Berenson et al. 1995)
  P4  lost update   r1[x] .. w2[x] .. w1[x] .. c1
  A5A read skew     r1[x] .. w2[x] .. w2[y] .. c2 .. r1[y]
  A5B write skew    r1[x] .. r2[y] .. w1[y] .. w2[x] .. c1 and c2
  phantom           decide on a set by condition, add a row to that set
  none of them errors: find them with an invariant query job

ERRORS (17 text)
  40001  could not serialize access due to concurrent update         RR, SER
  40001  could not serialize access due to read/write dependencies
         among transactions    HINT: The transaction might succeed if retried.
  40P01  deadlock detected     DETAIL: Process %d waits for %s on %s;
                               blocked by process %d.
  25P02  current transaction is aborted, commands ignored until end of
         transaction block
  55P03  NOWAIT: could not obtain lock on row in relation "%s"
  23505  MERGE racing an insert: duplicate key. Use INSERT .. ON CONFLICT
  full predicate lock table: ERROR out of shared memory,
         HINT: You might need to increase "max_pred_locks_per_transaction".
  members full: This command would create a multixact with %u members, but
         the remaining space is only enough for %u member

DEFAULTS (docs 19.8, 19.11, 19.12, guc_tables.c REL_17_11)
  deadlock_timeout 1s    log_lock_waits off (on in 19)    lock_timeout 0
  statement_timeout 0    idle_in_transaction_session_timeout 0
  idle_session_timeout 0 (new in 14)   transaction_timeout 0 (new in 17)
  set per role or SET LOCAL, not in postgresql.conf
  deadlock_timeout, log_lock_waits: superuser, or GRANT SET ON PARAMETER (15+)
  max_pred_locks_per_transaction 64, per_relation -2 = 64/2 = 32, per_page 2

LOCK WAITS AT WORK
  pg_stat_activity  wait_event_type Lock: transactionid = waits for the row's
                    writer, tuple = queued behind another waiter (not FIFO),
                    object = e.g. the NOTIFY commit lock
  RDS / Aurora      Lock:transactionid, Lock:tuple (Database Insights)
  pg_wait_events (17) join on type + name for descriptions
  pg_blocking_pids(pid)   pg_locks.waitstart (new in 14)
  pg_stat_database.deadlocks   (no counter for 40001: count it in the app)
  log_lock_waits on: "process %d still waiting for %s on %s after %ld.%03d ms"
  multixact in xmax: several lockers, often FK KEY SHARE + NO KEY UPDATE.
    n lockers of a row: n-1 multixacts, n(n+1)/2 - 1 members. ~4 billion
    members total, no metric (Metronome). pg_get_multixact_members(xmax)

NOTIFY
  COMMIT of a txn that ran NOTIFY takes AccessExclusiveLock on "object 0 of
  class 1262 of database 0", held across the WAL flush: one such commit at a
  time, server-wide (async.c:921). Still taken in 19 RC1. Poll instead

SUBTRANSACTIONS
  SAVEPOINT, PL/pgSQL EXCEPTION, psql ON_ERROR_ROLLBACK, Django nested
  atomic(), Rails requires_new, psycopg nested transaction().
  > 64 per txn: every new snapshot suboverflowed, lookups read pg_subtrans.
  subtransaction_buffers 0 = shared_buffers/512, 16..1024 pages (17; 14: 32)
  Waits: LWLock SubtransSLRU, SubtransBuffer (both also in 14)
  Find it (16+): (pg_stat_get_backend_subxact(b)).* over pg_stat_get_backend_idset()
  aborted txn accepts COMMIT (= ROLLBACK), ROLLBACK, ROLLBACK TO SAVEPOINT,
  PREPARE TRANSACTION

DEADLOCK
  check after deadlock_timeout. Victim: usually the first waiter to check
  fix: one lock order (SELECT ... ORDER BY key FOR UPDATE), retry 40P01

RETRY
  whole transaction from BEGIN, COMMIT inside the loop, only 40001 and 40P01,
  capped attempts with jitter, no side effects inside the body.
  Django, Rails, psycopg: no retry. DBOS @DBOS.transaction: retries, no cap

FIXES
  scope first   read and write in ONE transaction, or no level helps (ACIDRain)
  lost update   UPDATE .. SET x = x - n WHERE .. AND x >= n   (READ COMMITTED)
  at most one   UNIQUE index, partial if needed: 23505 at every level,
                or 40001 first at SERIALIZABLE
  upsert        INSERT .. ON CONFLICT DO UPDATE, atomic, no savepoint.
                RR and SER: 40001 if the snapshot misses the row. NOT MERGE
  write skew    SERIALIZABLE + retry, or one parent row updated conditionally
  phantom       same. FOR UPDATE cannot lock rows that do not exist yet
  queue claim   UPDATE .. WHERE id = (SELECT .. FOR UPDATE SKIP LOCKED) RETURNING id
  lease         lease_until on claim (db clock), reaper requeues expired,
                owner check on completion, attempts cap, then state 'failed'.
                Partial indexes WHERE queued, and (lease_until) WHERE running
  long txn      holds the cleanup horizon: queue claims slow down.
                VACUUM VERBOSE 17: "are dead but not yet removable",
                "removable cutoff: %u" = the holder's backend_xmin
  outbox        event row in the change's transaction. Relay: claim with a
                lease + COMMIT, publish, mark with owner check. Partial index
                WHERE sent_at IS NULL, retention delete, alert on the age of
                the oldest unsent row. Or xid8 cursor below pg_snapshot_xmin.
                Consumer: processed_events ON CONFLICT
  name lock     pg_advisory_xact_lock(key), not the session form (PgBouncer
                transaction mode: never. RDS Proxy: pins)
  vector + SSI  run the vector search outside the serializable transaction

CONTENTION
  optimistic attempts = 1 / (1 - p)     p 0.5 -> 2, p 0.9 -> 10
  n workers, one row, one commit per round: n (n + 1) / 2 attempts

SSI COST (Ports and Grittner 2012, PostgreSQL 9.1, 2012 hardware)
  CPU +10 to 20% (SIBENCH)   5% slower in memory (DBT-2++)
  same as SI disk-bound, failures < 0.25%    RUBiS 435 / 422 / 208 req/s

## Sources

Open the sources, with what to read in each
This course's research fetched the papers, analyses and outbox sources below on 2026-10-17, and more pages for this phase on 2026-10-18. The PostgreSQL 17 revision of 2026-10-20 fetched the 17 docs, the REL_17_11 source, the release notes from 15 to 19 RC1, and the new production, ORM, pooler and AWS sources. Every URL below was checked with check_urls.py on 2026-10-20. Primary sources come first in each group. Vendor pages are marked "vendor": treat their claims about their own product as the vendor's claims.

### The original papers

- A Critique of ANSI SQL Isolation Levels, Berenson, Bernstein, Gray, Melton, E. O'Neil and P. O'Neil, ACM SIGMOD 1995. Focus on: sections 2.2 and 3 for P0 to P3, and section 4.1 for P4 and history H4. Section 4.2 has snapshot isolation, A5A, A5B, history H5, the 8-hour example and Remark 9. Table 4 is on page 10. It takes about 45 minutes. This is the arXiv copy of MSR-TR-95-51. Its extracted text has broken spacing, so copy formulas from the PDF pages. Read it before you run E4.

- Serializable Isolation for Snapshot Databases, Cahill, Röhm and Fekete, ACM SIGMOD 2008. Focus on: section 1, Example 1 and Figure 1, the doctors on duty. It is the origin of this phase's opening case. Section 2.2 for the dangerous structure and the pivot. Section 5 measures the first SSI, in Berkeley DB 4.6.21 with page-level locks, on 2008 hardware. So do not compare its numbers with PostgreSQL's. A course mirror of the paper.

- Serializable Snapshot Isolation in PostgreSQL, Ports and Grittner, PVLDB 5(12), VLDB 2012. Focus on: section 2.1 for the doctors example in PostgreSQL's terms. Sections 4 and 5.2 for SIREAD locks and safe snapshots, and 5.4 for which transaction to cancel. Section 8 for every number in section 3.5, on PostgreSQL 9.1 and the paper's 2012 hardware. The paper also notes some history. For years the docs did not say that the old SERIALIZABLE mode was not truly serializable. It takes about 70 minutes, and is best read before E5.

- Generalized Isolation Level Definitions, Adya, Liskov and O'Neil, IEEE ICDE 2000. Focus on: section 5, the phenomena G0 to G2 and G2-item. Jepsen and Hermitage use these names. A Wayback copy, because the original host refused connections.

- Weak Consistency: A Generalized Theory and Optimistic Implementations for Distributed Transactions, Atul Adya, MIT PhD thesis, 1999. Focus on: section 4.1 for G-single, the read skew of Hermitage, and section 4.3 for the definition of snapshot isolation. Read only those two sections, because the rest goes far beyond this phase.

### Books and lectures

- PostgreSQL 14 Internals, Egor Rogov, Postgres Professional, 2022 to 2023, free PDF. Focus on: section 2.3, pages 47 to 60, for the READ COMMITTED re-check, the read-only anomaly and DEFERRABLE. Section 3.7, pages 76 to 79, for subtransactions and the aborted state. Chapter 13, pages 211 to 230, for the tuple-lock queue, multixacts, SKIP LOCKED and deadlocks inside two UPDATEs. Every output in these pages was printed on PostgreSQL 14. The mechanisms they show are the same at REL_17_11, by the source lines this phase cites. The process IDs and transaction IDs will differ on your server. The book's home page is https://postgrespro.com/community/books/internals.

- CMU 15-445/645 Database Systems, Fall 2025, lecture 18 notes, Two-Phase Locking. Focus on: deadlock detection against prevention, wait-die and wound-wait. It takes about 20 minutes.

- CMU 15-445/645, Fall 2025, lecture 20 slides, Multi-Version Concurrency Control. Focus on: version storage, append-only against delta, and slide 33, the table of engines.

### Production reports

- ACIDRain: Concurrency-Related Attacks on Database-Backed Web Applications, Warszawski and Bailis, SIGMOD 2017. Focus on: the introduction, for the 22 attacks, the 17 that come from transaction scope, and Flexcoin. Then section 2, which separates level-based and scope-based anomalies.

- Postgres Job Queues & Failure By MVCC, Brandur Leach, 2015-05-18. Focus on: "Slow lock time" and "Dead tuples", for the lock time and the 100,000 dead rows, and the VACUUM VERBOSE output. Heroku Postgres, the Que library with advisory locks, about 50 jobs a second. No SKIP LOCKED.

- Why we spent the last month eliminating PostgreSQL subtransactions, GitLab, 2021-09-29. Focus on: "What is SubtransControlLock?" and "Reproducing the problem with replicas", for the drop from about 360,000 to 50,000 transactions per second. Replicas only, with a long transaction on the primary.

- How Postgres sequences issues can impact your messaging guarantees, Oskar Dudycz, 2022-10-28. Focus on: the xid8 column and pg_snapshot_xmin(pg_current_snapshot()), and the final query that orders by transaction ID. A design post, with no measurements.

- pgsql-bugs #12990, multixact member files, PostgreSQL 9.3.5, 2015. Focus on: the workload of SELECT ... FOR SHARE from 26 connections, and the table of members files over one day. An old version, so read it for the mechanism only.

- Root Cause Analysis: PostgreSQL MultiXact member exhaustion incidents (May 2025), Cosmo Wolfe, Metronome, 2025-05-20. Focus on: "PostgreSQL MultiXact IDs: Technical foundation and our misunderstanding" for the quadratic member growth and the foreign-key case, then "Our monitoring misunderstanding". Aurora PostgreSQL 13.18, over 30 TB, four write outages in one week. Read it before E13's multixact case. It takes about 15 minutes.

- Postgres LISTEN/NOTIFY does not scale, Elliot Levin, Recall.ai, 2025-07-01, updated 2026-05-08. Focus on: "How we discovered it" for the log_lock_waits output, and the PreCommit_Notify excerpt. The update at the top names a fix in PostgreSQL 19. Read section 3.4 of this phase for what that fix changes. Tens of thousands of concurrent writers. Read it before E20.

- Optimizing database connection loads with PgBouncer and Testwick, Angelos Kyratzakos, Mattermost, 2022-01-11. Focus on: the part on migrations, where a session-level advisory lock taken by golang-migrate could not be released through PgBouncer in transaction mode.

- Fun with Multiversion Concurrency Control, Precision Nutrition, 2020-03-06. Focus on: "MVCC breaks our simple loop", with events 185 to 189 and their xmin values. It is the id high-water bug of section 3.7, in production. Its part 2, https://tech.precisionnutrition.com/postgres/databases/2020/05/15/fun-with-mvcc-2, gives the fix with a one-row counter table, so that ids follow commit order.

### PostgreSQL 17 documentation

- 13.2 Transaction Isolation. Focus on: Table 13.1, and the rule for an UPDATE after a wait at READ COMMITTED. Then the MERGE paragraph of 13.2.1, the 40001 at REPEATABLE READ, and the advice list for SERIALIZABLE. The most important page of this phase.

- 13.1 Introduction. Focus on: the sentence on reading and writing never blocking each other.

- 13.3 Explicit Locking. Focus on: 13.3.1 table-level locks, 13.3.2 and Table 13.3 for row locks, 13.3.4 Deadlocks, and 13.3.5 Advisory Locks with its three warnings.

- 13.5 Serialization Failure Handling. Focus on: which SQLSTATEs to retry, and why the server does not retry for you. The page exists from version 15.

- 13.6 Caveats. Focus on: the first paragraph, TRUNCATE and table rewrites against old snapshots. Two minutes. Read it before E18.

- MERGE. Focus on: the synopsis with RETURNING and WHEN NOT MATCHED BY SOURCE, new in 17. Then read the MERGE paragraph of 13.2.1 for its concurrency rule.

- 9.28.10 Advisory Lock Functions. Focus on: Table 9.106, the xact and try forms.

- 52.12 pg_locks. Focus on: waitstart, new in version 14, and the locktype values transactionid, tuple and object.

- 52.36 pg_wait_events. Focus on: the three columns, and the join with pg_stat_activity of section 3.4. New in 17.

- 11.8 Partial Indexes. Focus on: Example 11.3, the partial unique index.

- INSERT. Focus on: the ON CONFLICT clause, and the sentence on the atomic outcome.

- 24.1.5.1 Multixacts and Wraparound. Focus on: the 10GB and 20GB limits of the member storage.

- 26.4 Hot Standby. Focus on: the sentence that serializable is not available on a standby.

- 41.6.8 Trapping Errors. Focus on: the tip on the cost of a block with EXCEPTION.

- SAVEPOINT. Focus on: the examples of rolling back to a savepoint.

- 19.12 Lock Management. Focus on: deadlock_timeout and the three max_pred_locks_* settings.

- 19.11 Client Connection Defaults. Focus on: default_transaction_isolation, statement_timeout, lock_timeout, idle_in_transaction_session_timeout, idle_session_timeout and transaction_timeout, new in 17.

- 19.4 Resource Consumption. Focus on: subtransaction_buffers, new in 17, and its automatic default.

- 19.8 Error Reporting and Logging. Focus on: log_lock_waits and log_min_error_statement.

- 5.6 System Columns. Focus on: xmin, xmax and ctid.

- 65.6 Database Page Layout. Focus on: Table 65.4, the row version header, with t_xmin, t_xmax and t_ctid.

- 9.27 System Information Functions and Operators. Focus on: Table 9.83, the snapshot components, and pg_xact_status, pg_current_snapshot and pg_blocking_pids. Also pg_control_checkpoint and its next_multi_offset column.

- SELECT, The Locking Clause. Focus on: NOWAIT and SKIP LOCKED, and the warning on the inconsistent view.

- SET TRANSACTION. Focus on: DEFERRABLE.

- 27.2 The Cumulative Statistics System. Focus on: Table 27.4, wait event types, and the idle in transaction state. Table 27.11 for the transactionid, tuple and object waits, Table 27.12 for SubtransSLRU, 27.2.17 for pg_stat_database.deadlocks, 27.2.25 for pg_stat_slru, and 27.2.26 for pg_stat_get_backend_subxact.

- 5.5 Constraints. Focus on: the note that CHECK constraints see only the row being checked.

- CREATE SEQUENCE. Focus on: the note that nextval is never rolled back, which is why outbox ids arrive out of commit order.

- 3.4 Transactions, tutorial. Focus on: the all-or-nothing paragraph. It takes two minutes.

- 65.1 Database File Layout. Focus on: the pg_xact row.

- Appendix A, Error Codes. Focus on: class 40, Transaction Rollback.

- Versioning policy. Focus on: the table of final release dates. 14 ends on 2026-11-12, and 17 on 2029-11-08.

### PostgreSQL release notes

- PostgreSQL 12.4 release notes, 2020-08-13. Focus on: "Fix conflict-checking anomalies in SERIALIZABLE isolation mode".

- PostgreSQL 15 release notes. Focus on: GRANT on server variables, and MERGE.

- PostgreSQL 16 release notes. Focus on: pg_stat_get_backend_subxact().

- PostgreSQL 17 release notes. Focus on: transaction_timeout, pg_wait_events, the configurable SLRU caches, and MERGE RETURNING.

- PostgreSQL 18 release notes. Focus on: log_lock_failures, and checksums on by default.

- PostgreSQL 19 RC1 release notes source. Focus on: 64-bit multixact members, log_lock_waits on by default, and the NOTIFY wake-up change. A release candidate: items can still change.

- Commit 282b1cde9, "Optimize LISTEN/NOTIFY via shared channel map and direct advancement", 2026-01-15. Focus on: the commit message, which describes waking fewer listeners. Compare async.c at REL_19_RC1 line 1309, where the commit lock is still taken.

### PostgreSQL source, tag REL_17_11

- heapam_visibility.c. Focus on: HeapTupleSatisfiesMVCC at line 960, with its comment from line 937, the visibility rule of section 3.2.

- snapshot.h. Focus on: lines 157 to 169, the snapshot fields.

- nodeModifyTable.c. Focus on: ExecUpdate from line 2292, with the 40001 of first-updater-wins at line 2417. ExecCheckTupleVisible at line 309, and the MERGE branch at lines 3173 to 3184.

- predicate.c. Focus on: lines 3991 to 3993 for the message and hint, the reason codes at lines 4657 and 4716, and the full-table hint at line 2469.

- indexam.c. Focus on: lines 225 to 228 and 319 to 320, the whole-index predicate lock for an index without ampredlocks.

- lmgr README. Focus on: lines 340 to 360, the timer. Lines 518 to 524, soft cycles. Lines 553 to 555, the victim.

- README-SSI. Focus on: the overview of SSI in PostgreSQL by its authors. Read it after Ports and Grittner, for the details the paper leaves out.

- deadlock.c. Focus on: DeadLockReport, lines 1072 to 1135.

- lmgr.c. Focus on: XactLockTableInsert at lines 613 to 624, the wait at line 691, and the context text at line 854.

- postgres.c. Focus on: lines 1143 and 1144, the 25P02 message, and IsTransactionExitStmt at lines 2831 to 2844.

- executor README. Focus on: "EvalPlanQual (READ COMMITTED Update Checking)", lines 350 to 384.

- README.tuplock. Focus on: lines 14 to 37, the tuple lock and the steps of a row wait.

- proc.c. Focus on: lines 1499 to 1627, the log_lock_waits lines.

- nbtinsert.c. Focus on: line 227, the wait of a unique insert, line 639, the SSI check, and line 668, the 23505 message.

- proc.h. Focus on: PGPROC_MAX_CACHED_SUBXIDS at line 39.

- subtrans.c. Focus on: SubTransGetTopmostTransaction at line 163, and the automatic buffer count at lines 201 to 207.

- snapmgr.c. Focus on: XidInMVCCSnapshot at line 1856, and the suboverflowed branch from line 1886.

- varsup.c. Focus on: lines 269 to 276, where the 65th subtransaction ID sets the overflow flag.

- multixact.c. Focus on: the member-limit error at line 1362, the member thresholds at lines 215 to 217, MultiXactMemberFreezeThreshold at line 3144, and the member sort at line 1771.

- async.c. Focus on: PreCommit_Notify at line 860, and the commit lock at line 921 with the comment above it.

- xact.c. Focus on: the order inside CommitTransaction: PreCommit_Notify at line 2289, then RecordTransactionCommit at line 2325.

- vacuumlazy.c. Focus on: lines 626 to 672, the VERBOSE report, with "are dead but not yet removable" at line 660 and "removable cutoff" at line 672.

- tablecmds.c. Focus on: ATRewriteTable at line 5997, and the row copy with table_tuple_insert at line 6339.

- Commit e620a38c, "Avoid update conflict out serialization anomalies.", 2020-06-11. Focus on: the commit message, with "Reported-By: Kyle Kingsbury", and the new isolation test update-conflict-out.spec.

### pgvector

- pgvector, src/hnsw.c, master. Focus on: ampredlocks = false, at lines 289 and 348 when this phase was written.

- pgvector, src/ivfflat.c, master. Focus on: ampredlocks = false, at lines 206 and 265 when this phase was written.

### Independent analyses and test suites

- Jepsen: PostgreSQL 12.3, Kyle Kingsbury, 2020-06-12. Focus on: section 3.1 for repeatable read as snapshot isolation, section 3.2 for G2-item under serializable, and section 4. Read it after E5, in about 25 minutes.

- Jepsen: Amazon RDS for PostgreSQL 17.4, Kyle Kingsbury, 2025-04-29, updated 2025-05-03. Focus on: section 1, the update on the cause, and section 4 for the Long Fork cycle. Section 5 gives the advice to use the writer endpoint. Multi-AZ clusters, no faults injected, every version from 13.15 to 17.4. With about 150 write and 1,600 read-only transactions per second, cycles appeared "every few minutes". Jepsen did not observe the cycle in standard PostgreSQL at REPEATABLE READ.

- Understanding transaction visibility in PostgreSQL clusters with read replicas, Sergey Melnik, AWS Database Blog, 2025-05-02. Focus on: "Understanding the Long Fork behavior", the ProcArray and the WAL order. Then the proposed fix with commit sequence numbers. AWS's position, read beside Jepsen's. AWS says "the visibility order of transactions doesn't always match their logged commit order", and that it "affects all isolation levels". The order differs "between the primary and replicas in cluster configurations". The issue "isn't present in Single-AZ PostgreSQL deployments". Both posts can be true, because they describe different setups. That reading is inferred, and a test with one self-managed replica would confirm it.

- Hermitage, Martin Kleppmann. Focus on: the README table, and postgres.md. It has two-session psql scripts for "Lost Update (P4)", "Write Skew (G2-item)" and "Anti-Dependency Cycles (G2)". Run on PostgreSQL 9.3.5. You can paste the scripts into two psql windows.

- Hermitage: Testing the "I" in ACID, Martin Kleppmann, 2014-11-25. Focus on: why the level names of different databases do not match. It takes ten minutes.

- Jepsen: MySQL 8.0.34, Kyle Kingsbury, 2023-12-19. Focus on: the summary, and section 3.3 "Lost Update at Repeatable Read". It uses the Elle checker of section 3.3 of this phase.

### The transactional outbox

- Pattern: Transactional outbox, Chris Richardson, microservices.io. Focus on: the solution, the at-least-once note, and the two relay patterns, log tailing and polling. The page has no date.

- Outbox Event Router, Debezium 3.7 documentation. Focus on: the default table columns, and the rule that only INSERTs are expected. Then the event id header for removing duplicates. The page gives no numbers.

- Transactional outbox pattern, SeatGeek Data Platform team, 2025-02-07. Focus on: pg_logical_emit_message() in place of an outbox table, and Debezium heartbeats. It reports a load test without numbers.

- Capturing every change from Shopify's sharded monolith, John Martin and Adam Bellemare, Shopify, 2021-03-12. Focus on: the p99 and the throughput of a log-reading relay. It is change data capture of MySQL, not an outbox on PostgreSQL.

### Drivers, ORMs, poolers and queues

- psycopg 3, Errors. Focus on: SerializationFailure, DeadlockDetected, Error.sqlstate and the Diagnostic fields the labs print.

- psycopg 3, Transactions management. Focus on: the warning that "even a simple SELECT will start a transaction", nested transaction() blocks as SAVEPOINT, and autocommit.

- Django 5.2, Database transactions. Focus on: "Django's default transaction behavior", ATOMIC_REQUESTS, and the four steps of atomic that create savepoints for inner blocks.

- Django 5.2, QuerySet API reference. Focus on: select_for_update(), its four options, and the TransactionManagementError in autocommit.

- Rails API, ActiveRecord DatabaseStatements. Focus on: "Nested transactions support" and requires_new, and allow_retry for connection errors only.

- Solid Queue README, rails/solid_queue. Focus on: FOR UPDATE SKIP LOCKED, polling_interval, and "Jobs that were claimed by processes with an expired heartbeat will be marked as failed". The project's own description of itself.

- PgBouncer features, vendor. Focus on: the table of SQL features per pool mode, with session-level advisory locks "Never" in transaction pooling.

- RDS Proxy, Avoiding pinning, AWS, vendor. Focus on: the PostgreSQL list, pg_advisory_lock pins and pg_advisory_xact_lock does not.

- DBOS 2.31.0 on PyPI. Focus on: the version that the reading example of section 3.7 reads. The code itself was read from the installed package.

### Managed PostgreSQL: RDS and Aurora

- Lock:transactionid, Amazon Aurora user guide, AWS, vendor. Focus on: "Likely causes of increased waits", and the SELECT … FOR KEY SHARE note. The RDS for PostgreSQL page has the same text: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/wait-event.locktransactionid.html

- Lock:tuple, Amazon Aurora user guide, AWS, vendor. Focus on: the three-session table, and "Find the blocker session". The RDS page: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/wait-event.locktuple.html

- Parameter groups for Amazon RDS, AWS, vendor. Focus on: the rule that a default parameter group cannot be changed, which is why deadlock_timeout and log_lock_waits go in a custom group.

- Client:ClientRead, Amazon RDS user guide, AWS, vendor. Focus on: "Idle client connection", the cause that matches an idle in transaction session of section 3.2.

- Database load and average active sessions, AWS, vendor. Focus on: what one unit of DB load means, and how wait events split it.

- Overview of Database Insights on Amazon RDS, AWS, vendor. Focus on: the default Advanced mode and its lock diagnostics.

### A talk

- Transactions: myths, surprises and opportunities, Martin Kleppmann, Strange Loop 2015. Focus on: read skew at 0:15:00, write skew with an on-call example at 0:18:40, two-phase locking at 0:21:53, and serializable snapshot isolation at 0:25:45. The times come from YouTube's chapter marks and its machine captions, correct to about 10 seconds. The captions are not his exact words, so do not quote them.

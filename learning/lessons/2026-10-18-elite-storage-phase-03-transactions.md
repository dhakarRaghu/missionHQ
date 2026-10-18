### What you must know

- Inside one transaction, a plain read blocks no writer, so another commit can change the facts you decided on.Name an anomaly and the level that stops it.

- A writer that finds a row locked waits for its holder, then re-checks its condition on that row only.Write safe one-statement fixes, and read lock waits.

- SERIALIZABLE, the strictest level, adds no lock waits and cancels one transaction, so your code must run it again.Retry correctly, and keep savepoints off busy paths.

- A unique index or a counter row holds a rule at every level, but a row lock misses rows not yet written.Pick a constraint, a lock or a version check.

- A claim or an event that must outlive COMMIT needs an expiry time or an unsent flag, not a lock.Build a leased claim and a relay that never skips.

In Phase 2 an UPDATE wrote a new version of the row and kept the old one. This lesson gives the reason, and shows what two sessions can do to each other through those versions.

The running case is the course's task queue on PostgreSQL 14. Workers claim tasks in tq_tasks, humans approve some in tq_approvals, and every change writes an event into tq_outbox. tq_budget holds each tenant's credits, where a tenant is a customer account such as acme. tq_oncall lists the approvers, and at least one must be on call. Alice and Bob are both on call and open the same screen at once. Its transaction counts the approvers on call, and if the count is at least 2, sets its own user off call.

timeAlice's transactionBob's transaction

t1BEGIN, count on call: 2BEGIN

t2count on call: 2

t3UPDATE alice off callUPDATE bob off call

t4COMMIT: okCOMMIT: ok

after0 approvers on call, at the default settings

No statement raised an error, and no session waited. This lesson shows which setting allowed it, and which setting or code change stops it.

Go deeper: the same kind of gap in a managed database
An analysis of Amazon RDS for PostgreSQL 17.4 found Long Fork cycles in Multi-AZ clusters, read through a primary and a reader endpoint, with no faults injected. In a Long Fork, two readers see two independent writes in opposite orders. So those clusters did not give one consistent snapshot across their endpoints. With about 150 write and 1,600 read-only transactions per second, cycles appeared every few minutes, in every version from 13.15 to 17.4. The same analysis did not see the cycle in standard PostgreSQL at REPEATABLE READ, and it advised using the writer endpoint.

AWS answered that a replica makes commits visible in the order of the write-ahead log, while the primary uses its own order. AWS says the effect touches all isolation levels in cluster setups, and that Single-AZ deployments do not have it. So the effect needs a replica, and replicas are the subject of course 5, Phase 3. Both positions can be true, because they describe different setups. That reading is inferred, and a test with one self-managed replica would confirm it. This course did not check what AWS's own documentation promised before these posts.

Evidence
The on-call case comes from Cahill, Röhm and Fekete, SIGMOD 2008, Example 1, where the rows are doctors on duty. Ports and Grittner, VLDB 2012, retell it with Alice and Bob, who count first and then update. This lesson uses that order, with approvers in place of doctors. The managed-database case is Jepsen's analysis "Amazon RDS for PostgreSQL 17.4", published 2025-04-29 and updated 2025-05-03, and the AWS Database Blog answer of 2025-05-02.

## What this lesson builds on

- The write path, from Phase 1. A commit is durable once its commit record is on stable storage in the WAL, the write-ahead log.

- The heap and the TID, from Phase 2. A table's rows sit in a heap of 8 kB pages, and a TID, a page and line number, names one row version.

- Check-then-act, from elite-performance Phase 4. Code checks a value, the value changes, then code acts, so a concurrency test must choose the order of steps.

Phase 4 covers vacuum, the cleanup of old row versions, and schema-change locks. Course 5 covers replicas and services, so this lesson stays on one server.

## Why did both approvers commit without an error?

Atomicity and isolation are two promises, and the approvers needed the second one.

A transaction, the statements between BEGIN and COMMIT, makes two promises. Atomicity means that after a crash or a ROLLBACK, every change is there or none is. Isolation covers transactions running at the same time, and its strongest form matches some one-at-a-time order. An isolation level is a weaker form, defined by the anomalies it allows, results no one-at-a-time order could produce. Each approver's transaction was atomic, so the rule broke through isolation.

Predict: three pairs from the task queue. Which break at READ COMMITTED, the default, and which at REPEATABLE READ?
One: two workers each read acme's 100 credits, check 100 against 80, and write 20. Two: the approvers. Three: two workers each count 0 running tasks for acme and each start one, with a limit of 1.

All three break at READ COMMITTED. REPEATABLE READ stops only the first, because only there do both transactions write the same row. Most people expect it to stop all three, because the name sounds like full protection.

PostgreSQL keeps isolation with MVCC, multiversion concurrency control, so several versions of a row exist at once.

- A transaction that writes gets a transaction ID, an xid. Every row version it writes carries that ID in a header field, xmin.

- An UPDATE writes a new version and puts its xid into the old version's xmax, so the old one stays readable. That is why Phase 2 saw a new version on every UPDATE.

- At COMMIT, the server flushes one commit record to the WAL and records the outcome in pg_xact. All the transaction's versions become visible at that moment, and that is atomicity.

- A statement reads through a snapshot, a record of which transactions had finished when it was taken. It sees a version whose writer had committed and whose replacer had not.

- READ COMMITTED takes a new snapshot for each statement. REPEATABLE READ takes one at the first statement and keeps it.

- A snapshot takes no lock, so another transaction can change a row you read and commit before you write.

Step 5 decides what a report of acme then beta sees while a transfer of 80 commits.

stepREAD COMMITTEDREPEATABLE READ

report: SELECT acmenew snapshot: 100snapshot taken: 100

transfer: acme minus 80, beta plus 80, COMMIT

report: SELECT betanew snapshot: 180same snapshot: 100

report total280, never a real state200, a real state

This anomaly is read skew, where each read is correct and the total mixes two states. The approvers broke the rule through step 6, which neither lower level changes.

Go deeper: IDs, the visibility rule in the source, level tables, and other engines
The two promises side by side.

AtomicityIsolation

protects froma crash, an error or a ROLLBACK in the middleother transactions running at the same time

the promiseall changes or noneas if each ran alone, at the level you chose

PostgreSQL's mechanismone commit record in the WAL, one status entry per transaction in pg_xactrow versions and snapshots, row locks, and SERIALIZABLE's checks

breaks whenthe client cannot tell whether COMMIT happenedtwo correct transactions produce a wrong result

In the predict pairs, pairs two and three write different rows, so they pass REPEATABLE READ with no error. PostgreSQL uses READ COMMITTED unless you choose another level. pg_xact is the store of transaction statuses.

One snapshot held for hours. A session that runs BEGIN and then waits for a user or a slow call keeps its snapshot all that time. Vacuum cannot remove an old version that an open snapshot may still need, so tables grow. "An open transaction prevents vacuuming away recently-dead tuples that may be visible only to this transaction." pg_stat_activity shows such a session in the state idle in transaction. The setting idle_in_transaction_session_timeout ends it, and its default is 0, which means off. The queue sections at the end show what this does to a busy queue.

How PostgreSQL makes a transaction atomic. You can read a transaction's ID with pg_current_xact_id(). Until its first write, a transaction has only a virtual ID, which never reaches a data page. Calling pg_current_xact_id() assigns a real ID, and pg_current_xact_id_if_assigned() does not. The docs call t_xmin the "insert XID stamp". pg_xact is the subdirectory that holds the commit status of each transaction. A reader decides about each version by asking whether its xid committed, so all versions of one transaction become visible at the same moment.

After a ROLLBACK or a crash, the versions stay in the table. Every reader finds their xid aborted, or never committed, and skips them. The comment in the visibility code says "it must have aborted or crashed", and the function returns false. So PostgreSQL needs no undo pass for table rows. The ARIES design of Phase 1 needs one, because its restart undoes the changes of transactions that never committed. On ROLLBACK in PostgreSQL 14, "no actual data rollback is happening". The skipped versions take space until vacuum removes them in Phase 4.

Two more failures of atomicity at its edges. ROLLBACK undoes rows and nothing else. A message sent to another service, or an HTTP call, inside a transaction stays sent when the transaction rolls back. The outbox at the end of this lesson fixes that. And if the connection drops while COMMIT runs, the client does not know whether the transaction committed. Sending it again can apply it twice. pg_xact_status(xid8) returns "in progress", "committed" or "aborted" for a recent transaction ID. So a client that saved its xid before COMMIT can ask afterwards.

The fields on each version. xmin is the ID of the inserting transaction, and "each update of a row creates a new row version for the same logical row". xmax is the ID of the deleting transaction, "or zero for an undeleted row version". It can be set on a version that is still visible, when the deleter has not committed or rolled back. t_ctid is the "current TID of this or newer row version", so an old version points to its replacement and the versions of one row form a chain. The fixed header is "23 bytes on most machines", and every version pays it. A DELETE only marks the version as deleted.

The one exception to "new index entries on every UPDATE" is a heap-only tuple update from Phase 2. It needs no new index entries when no indexed column changes and the page has free space. The link between that rule and the visibility rule is inferred.

A worked example. Transaction 700 wrote acme with 100 credits and committed long ago. Transaction 801 runs UPDATE tq_budget SET credits = 20 WHERE tenant = 'acme' and has not committed.

line pointercreditsxminxmaxt_ctidfor snapshot 801:803:801

1100700801(0,2)writer 700 committed, replacer 801 still running: visible

2208010(0,2)writer 801 still running: not visible

The snapshot has three parts. Its xmin is the lowest transaction ID still active, so every lower ID had finished. Its xmax is one past the highest completed ID, so every ID at or above it had not finished. Its in-progress list, xip_list, names the IDs between the two that were still running. The text form is xmin:xmax:xip_list, and the docs' example is 10:20:10,14,15. pg_current_snapshot() returns the current one.

So the snapshot 801:803:801 sees 100. After 801 commits, a REPEATABLE READ transaction that took that snapshot earlier still sees 100, because it keeps its snapshot. A READ COMMITTED statement takes a new snapshot, for example 803:803:, counts 801 as finished, and sees 20.

The visibility rule, exactly. A version is visible when two things hold. Its xmin is the reader's own transaction, or a transaction the snapshot counts as finished that committed. Its xmax is zero, or belongs to a transaction that aborted, or that the snapshot counts as unfinished. A SELECT ... FOR UPDATE also writes its ID into xmax, but only as a lock, and such an xmax never hides the version. The source checks HEAP_XMAX_IS_LOCKED_ONLY for that case. XidInMVCCSnapshot answers whether an ID was unfinished for this snapshot, and TransactionIdDidCommit looks the outcome up in pg_xact.

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

Hint bits. SetHintBits stores the outcome in the version's header, so later readers skip the pg_xact lookup. It does not set them while the writer still counts as running for the reader. The first readers after a bulk load set them, so a plain SELECT can leave "a trail of dirtied pages in the buffer cache". Whether setting them also writes WAL when data checksums are on was not checked.

Sharing one snapshot. pg_export_snapshot() returns an ID, and another REPEATABLE READ transaction adopts it with SET TRANSACTION SNAPSHOT before its first statement. Parallel pg_dump uses this, so all its processes read one state. At REPEATABLE READ the snapshot is taken at "the start of the first non-transaction-control statement", so BEGIN does not take it and the first SELECT or UPDATE does.

How the SQL standard defines the levels. It names four phenomena that a level must not allow. A dirty read sees another transaction's uncommitted data. A nonrepeatable read finds a row changed and committed since the first read. A phantom read finds a different set of rows for the same search condition. A serialization anomaly is a result that no one-at-a-time order produces. PostgreSQL 14 and 18 give the same table:

LevelDirty readNonrepeatable readPhantom readSerialization anomaly

Read uncommittedallowed, but not in PGpossiblepossiblepossible

Read committed, the defaultnot possiblepossiblepossiblepossible

Repeatable readnot possiblenot possibleallowed, but not in PGpossible

Serializablenot possiblenot possiblenot possiblenot possible

PostgreSQL's READ UNCOMMITTED behaves like READ COMMITTED, so PostgreSQL has three real levels. The table has no row for the opening case. Lost updates and write skew both fall inside "serialization anomaly". Berenson and five co-authors named the standard's three phenomena P1, P2 and P3, and showed that they miss other anomalies. Two of those are the lost update, P4, and write skew, A5B. Read skew is A5A, the history r1[x]...w2[x]...w2[y]...c2...r1[y]. A history is the order of reads r, writes w and commits c of numbered transactions. Read skew is not possible under snapshot isolation.

A worked answer on atomicity. A transfer moves 80 credits from acme to beta with two UPDATEs, and both rows start at 100. If the server crashes after the first UPDATE, both hold 100 after recovery, because the commit record never reached the WAL. A report that runs one SELECT sum(credits) while the transfer is open never sees 120. It reads one snapshot, and an uncommitted debit is never visible in PostgreSQL, at any level, so the sum is 200.

PostgreSQL's REPEATABLE READ is snapshot isolation, not locking repeatable read. The two are incomparable, because each allows an anomaly that the other forbids. Snapshot isolation allows write skew, which locking repeatable read forbids. Locking repeatable read allows a re-read that finds new rows, which snapshot isolation forbids. Jepsen's PostgreSQL 12.3 histories at repeatable read were "consistent with strong snapshot isolation".

Other engines store versions differently, and use the names differently.

EngineProtocolWhere versions liveCleanupIndex entries point to

PostgreSQLMV-2PL/MV-TOappend-only: each version is a whole row in the tablevacuumthe physical version

MySQL InnoDBMV-2PLdelta: the row is overwritten, and changed values are copied to a delta areavacuumthe logical row

OracleMV2PLdeltavacuumthe logical row

Append-only storage with physical pointers is why each PostgreSQL index needs a new entry for a new version. MySQL InnoDB's default "repeatable read" allows the lost update, which PostgreSQL's "repeatable read" prevents. More exactly, Hermitage lists that level as "monotonic atomic view", and marks the lost update as not prevented. So code that relies on PostgreSQL's error at that level can lose updates on MySQL. Hermitage links the MySQL 5.7 manual and does not state the version it tested, and MySQL 8 was not checked.

What a snapshot cannot see. Four limits follow from the rule. First, commits after it was taken: a REPEATABLE READ transaction keeps reading the old state by design, and the docs show a read-only transaction that sees a batch marked complete without one of its detail records. Second, rows that concurrent transactions insert. Third, writes to what it read, because a snapshot takes no lock. Fourth, its own cost: vacuum cannot remove a replaced version while a snapshot may still need it. Phase 4 calls the oldest such snapshot the cleanup horizon and measures what it does to a table. A version that only such a snapshot can still need is a recently-dead tuple. The docs say that "remaining idle for a long time can contribute to table bloat".

Writers still wait for writers. MVCC removes waits between readers and writers: "reading never blocks writing and writing never blocks reading". An UPDATE that finds the newest version replaced by a transaction still in progress still waits for it. The lock-wait section below covers that wait.

Try this now. Run psql -h /tmp -p 5432 -d storage_lab -c "show default_transaction_isolation" -c "select pg_current_xact_id()" -c "select pg_current_xact_id()". You should see read committed and two different IDs, because each statement ran in its own transaction. Then add -c "begin" -c "select pg_current_xact_id_if_assigned()" before the two SELECTs. The new SELECT returns NULL, because the transaction has only a virtual ID, and the two IDs after it are the same.

Then run psql -h /tmp -p 5432 -d storage_lab -c "create table p3_demo (k text primary key, v int)" -c "insert into p3_demo values ('acme', 100)" -c "select xmin, xmax, ctid, * from p3_demo" -c "update p3_demo set v = 20" -c "select xmin, xmax, ctid, * from p3_demo" -c "select pg_current_snapshot()" -c "drop table p3_demo". Look for the ctid moving, for example from (0,1) to (0,2), and for xmin changing to the ID of the UPDATE's transaction.

Evidence
The two promises: PostgreSQL 14 tutorial, section 3.4, a transaction "bundles multiple steps into a single, all-or-nothing operation" and its updates "become visible simultaneously". IDs: PostgreSQL 14 docs 9.26, and Rogov, "PostgreSQL 14 Internals", section 3.6, page 75. t_xmin: docs 70.6, Table 70.4. pg_xact: docs 70.1. No undo: heapam_visibility.c line 1060 at REL_14_24, and Rogov page 72. Header fields: docs 5.5 and 70.6. Snapshot parts: docs 9.26, Table 9.77, and snapshot.h lines 157 to 169 at REL_14_24. Lock-only xmax: heapam_visibility.c line 1079. Hint bits: comment at lines 937 to 956, and Rogov page 71. Snapshot export: Rogov section 4.7, pages 90 and 91. When each level takes its snapshot: docs 13.2.1 and 13.2.2. The level table: docs 13.2, Table 13.1, and 20.11 for the default. Anomaly names: Berenson, Bernstein, Gray, Melton, E. O'Neil and P. O'Neil, "A Critique of ANSI SQL Isolation Levels", SIGMOD 1995, sections 4.1 and 4.2, Table 4 and Remark 9. REPEATABLE READ as snapshot isolation: docs 13.2.2, and Jepsen "PostgreSQL 12.3", section 3.1. The engine table: CMU 15-445, Fall 2025, lecture 20, slide 33. MySQL: Hermitage README, with the level name from its table. Long snapshots: docs 20.11, which also give the timeout default.

## Which anomaly is it, and which level stops it?

The three predict pairs are all check-then-act between two sessions, and where the second write lands names the anomaly.

anomalywhat both readwhat each writesfirst level that stops it

lost updateone rowthat same rowREPEATABLE READ

write skewa set of rowsa different row of that setSERIALIZABLE only

phantoma set defined by a conditiona new member of that setSERIALIZABLE only

- A lost update is pair one. At READ COMMITTED the second worker waits for the first one's row lock, then writes 20 again, so 160 credits are spent from 100.

- At REPEATABLE READ the second worker cannot change a row version that a concurrent transaction replaced. It gets ERROR 40001: could not serialize access due to concurrent update. This course calls the rule first-updater-wins.

- Write skew is the approvers. Each read the other's row and wrote its own, so no row was written twice and both commit at REPEATABLE READ.

- A phantom is pair three. Each worker decided that no task was running, then added a row to that empty set, so acme ends with 2 running tasks.

So REPEATABLE READ is PostgreSQL's form of snapshot isolation, one snapshot per transaction plus first-updater-wins. Check one thing before the level. If the read and the write do not run in one transaction, no level protects the decision. An ORM in autocommit mode does this. One audit of 12 shop applications found 22 attacks, and 17 came from wrong transaction scope, which no setting fixes.

REPEATABLE READ stops two writes to one row, and only SERIALIZABLE stops the rest.

Setting REPEATABLE READ everywhere leaves write skew and phantoms passing with no error.

Run uv run python phase03_transactions/mvcc_model.py and find the write-skew row.

Go deeper: the histories, the lab's ordering probe, phantom reads and the read-only anomaly
The whole matrix.

The course's model of these rules predicts this matrix, with its rows for the atomic spend, read skew and a deadlock. It was not run against a server by the author yet.

historyREAD COMMITTEDREPEATABLE READSERIALIZABLE

lost-updateBROKENholds, T2 40001holds, T2 40001

lost-update-atomicholdsholds, T2 40001holds, T2 40001

write-skewBROKENBROKENholds, T2 40001

phantom-limitBROKENBROKENholds, T2 40001

read-skewBROKENholdsholds

deadlockholds, T2 40P01holds, T2 40P01holds, T2 40P01

The histories by name. The lost update is P4, written r1[x]...w2[x]...w1[x]...c1. Write skew is A5B, written r1[x]...r2[y]...w1[y]...w2[x]...(c1 and c2 occur). Its history H5 has numbers. The rule is x + y > 0, and both start at 50. Each transaction reads both, sees a sum of 100, and subtracts 90 from a different one. Both commit, and x + y = −80. Snapshot isolation allows A5B and forbids P4 and A5A. The phantom has the same shape with hours: both transactions see 7 of 8 hours booked, and each adds 1. Hermitage, a test suite by Martin Kleppmann, uses the names of Atul Adya's work. G-single is read skew, G2-item is write skew on rows, and G2 is the form with a search condition. Its table marks G2-item and G2 as possible at "repeatable read" and prevented at "serializable" in PostgreSQL.

Why the lost update looks like this. The docs give the READ COMMITTED rule: after the first updater commits, the second "will attempt to apply its operation to the updated version of the row". Its WHERE clause, tenant = 'acme', still matches, so it writes 20 from an old read. At REPEATABLE READ the transaction "will be rolled back with the message" ERROR: could not serialize access due to concurrent update. Its SQLSTATE 40001 is serialization_failure. The check raises the error only when the level is REPEATABLE READ or SERIALIZABLE. The papers name the same idea first-committer-wins. PostgreSQL applies it when the second writer tries the write, not at its commit. The docs then say to "abort the current transaction and retry the whole transaction from the beginning". The retry reads 20, sees that 20 is less than 80, and refuses the spend.

stepREAD COMMITTEDREPEATABLE READ

T1 SELECT credits100100

T2 SELECT credits100100

T1 UPDATE credits = 201 row, row locked1 row, row locked

T2 UPDATE credits = 20waits for T1waits for T1

T1 COMMITokok

T2, after the wait1 row: writes 20ERROR 40001

T2 COMMITokROLLBACK

result160 spent from 100, BROKEN80 spent, credits 20, holds

That table is the expected output of lost_update.py --strategy naive, not run by the author yet. A similar case: two concurrent withdraw(99) calls against a balance of 100 both pass, and 198 leaves the account.

Write skew in the lab. At REPEATABLE READ the expected output is two successful COMMITs and RESULT: BROKEN. 0 approver(s) on call, not run by the author yet. A CHECK constraint cannot hold this rule, because "at least one row has on_call true" is a statement about several rows. The docs say: "PostgreSQL does not support CHECK constraints that reference table data other than the new or updated row being checked." A unique index holds rules of the form "at most one", and "at least one" is not of that form. The docs also warn about this level: "Attempts to enforce business rules by transactions running at this isolation level are not likely to work correctly without careful use of explicit locks to block conflicting transactions."

The two forms of phantom. The first form is the phantom read. One transaction runs the same count twice, and another inserts a matching row in between. phantom.py --case reread is expected to print counts 2 and 3 at READ COMMITTED, and 2 and 2 at REPEATABLE READ, because the snapshot does not change. That is why the level table says "allowed, but not in PG". The second form is the running limit, and the snapshot does not help there:

phantom.py --case limit, REPEATABLE READ, expectedresult

W1 SELECT count(*) running for acme0

W2 SELECT count(*) running for acme0

W1 UPDATE task 7 SET state = 'running'1 row

W2 UPDATE task 8 SET state = 'running'1 row, no wait, another row

W1 COMMIT, then W2 COMMITok, ok

2 running tasks for acme, the limit is 1BROKEN

The trap, in full. The natural fix for the phantom is SELECT ... FOR UPDATE before the count. At that moment acme has no running task, so the SELECT returns no rows and locks none. Both workers go on and claim, and the phantom passes every test that runs one session. phantom.py --fix for-update shows this, not run by the author yet. A row lock can only cover a row that exists. The constraint section below gives fixes that work at READ COMMITTED.

The read-only anomaly. Snapshot isolation allows one more anomaly, and the transaction that sees it writes nothing. Snapshot isolation allows only two anomalies: write skew, and this one. Three REPEATABLE READ transactions run on Bob's accounts, 900 and 100:

- T1 adds 1% of Bob's total to account 2. It reads 900 + 100 and stays open.

- T2 takes 100 from account 3 and commits, so account 3 is now 0.

- T3 is read-only. Its snapshot includes T2 and not T1.

- T1 commits, so account 2 is now 910.

- T3 reads Bob's accounts as 900 and 0.

T1 read account 3 before T2 changed it, so T1 must come before T2 in any serial order. T3 saw T2 without T1, so no one-at-a-time order matches what T3 saw. Each transaction alone was correct. The docs say that at this level "read-only transactions will never have serialization conflicts", which is why this anomaly raises no error. The docs' batch example has the same shape. That match is inferred, because the docs do not name the anomaly. The SERIALIZABLE section shows how that level catches it.

How the lab fixes the order of steps. The lab drives each pair with two psycopg connections, and a third connection watches pg_stat_activity and pg_blocking_pids(). So the script knows that a session waits for a lock before it takes the next step. This is the rule of elite-performance Phase 4, applied to a database: the test chooses the order.

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

The model. mvcc_model.py is a small pure-Python model of the visibility rule and of first-updater-wins. Its self-test asserts the matrix above, then removes one rule at a time and asserts that the matrix changes. It agrees with Hermitage's PostgreSQL rows, P4, G-single, G2-item and G2, and with the snapshot isolation rules above. Its limits are in its docstring. One matters here: it puts one predicate lock on the whole table for every scan, as PostgreSQL does for a sequential scan. A predicate lock is SERIALIZABLE's record of what a transaction read. Try uv run python phase03_transactions/mvcc_model.py --history write-skew --level serializable --trace and find the line where one transaction is doomed.

Scope, in full. The audit tool read the SQL traces of 12 self-hosted shop applications in four languages, which together run on over 2M websites. All 22 attacks work under the default isolation of popular databases, and 17 work "even under the strongest transactional guarantees" because of incorrect transaction usage. So review the scope first, then the level. The opening case of that work is the Flexcoin Bitcoin exchange. An attacker sent thousands of simultaneous requests, moved coins until the sending account was overdrawn, and all stored Bitcoins were stolen, so the exchange shut down.

Evidence
Histories and names: Berenson and others, SIGMOD 1995, sections 4.1 and 4.2, H4, H5 and Table 4. Hermitage README and postgres.md, run on PostgreSQL 9.3.5. The READ COMMITTED and REPEATABLE READ rules and quotes: PostgreSQL 14 docs, sections 13.2.1 and 13.2.2. The 40001 check: the TM_Updated branch of ExecUpdate, nodeModifyTable.c line 2006 at REL_14_24, under IsolationUsesXactSnapshot(). The CHECK limit: docs 5.4. The read-only anomaly: Rogov, pages 55 to 58, PostgreSQL 14. Wait types: docs 28.2, Table 28.4, and 9.26. The withdraw example: ACIDRain, Figure 1, from the study note. Scope: Warszawski and Bailis, "ACIDRain", SIGMOD 2017, introduction and section 2. Flexcoin's attack was on 2014-03-02. No lab output on this page was run by the author.

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

- T2 runs the statement's conditions again, on that one version only.

- Every other table, join and subquery in the statement keeps the old snapshot.

- If the conditions still match, T2 updates the new version, and otherwise it reports 0 rows.

So a one-statement fix is safe at READ COMMITTED when its condition reads only columns of the row it changes. credits >= 80, state = 'queued' and running < max_running meet it. A subquery, a join or an aggregate over other rows does not, so use SERIALIZABLE, a lock taken first, or a constraint. Bob's 909 raised no error, and it appears only when a commit lands during the wait.

Go deeper: the README text, a row that starts to match, and functions that read
Why the bug is intermittent. The statement succeeds and the error log stays empty. A count or a sum in the condition of a claim or an approval statement behaves the same way under load. The atomic-UPDATE trick cannot save the interest UPDATE, because its condition reads other rows.

The design note. The executor README describes EvalPlanQual. "The basic idea in READ COMMITTED mode is to take the modified tuple committed by the concurrent transaction (after waiting for it to commit, if need be) and re-evaluate the query qualifications to see if it would still meet the quals." It adds the boundary: "In UPDATE/DELETE, only the target relation needs to be handled this way." For the other relations, the executor uses "the same rows from these relations that were joined to the locked rows".

The docs give the result from the outside. An updating command can "see an inconsistent snapshot". It sees the effects of concurrent commands "on the same rows it is trying to update", but "it does not see effects of those commands on other rows in the database". They conclude: "This behavior makes Read Committed mode unsuitable for commands that involve complex search conditions". The interest example is read skew inside one statement: "different rows have been read from different snapshots". At REPEATABLE READ the same interest UPDATE fails with 40001 instead.

stepwhat happens

T1 BEGIN, UPDATE account 3 SET amount = amount - 100800 becomes 700, not committed

T2 interest UPDATEits subquery sees Bob's total 1,000, so he qualifies

T2 updates Bob's rows one by oneaccount 3 is locked by T1, so T2 waits

T1 COMMIT

T2 re-checks account 3 onlyupdates it from 700

resultaccount 2 is 202, account 3 is 707, total 909

A row that starts to match is not seen. The docs' own example uses a table website with two rows, hits 9 and 10. One session runs UPDATE website SET hits = hits + 1 and has not committed. Another runs DELETE FROM website WHERE hits = 10. "The DELETE will have no effect even though there is a website.hits = 10 row before and after the UPDATE." The DELETE skipped the row that held 9, because 9 did not match in its snapshot. It waited on the row that held 10, and then re-checked 11.

One more trap at this level. A query that calls a VOLATILE function which runs its own query can see data that does not match the main query.

The atomic spend, expected. The wrong and right forms are two entries of the lab's SQL table at phase03_transactions/lost_update.py:90. At READ COMMITTED the right form is expected to go like this, from the docs' rule, not run. T2 waits, then returns 0 rows, and the worker refuses the task. The balance is 20 after one spend. The mirror belief also costs: "READ COMMITTED can never be made safe" leads to retry loops and 40001 handling where one statement was enough.

Evidence
The re-check: src/backend/executor/README at REL_14_24, "EvalPlanQual (READ COMMITTED Update Checking)", lines 311 to 345. The docs' rule, the inconsistent snapshot and the website example: PostgreSQL 14 docs, section 13.2.1. The interest example and the VOLATILE trap: Rogov, "PostgreSQL 14 Internals", pages 49 to 51 and 54, printed on PostgreSQL 14. The study note found no production report of this boundary, so the evidence is documented behaviour, not a measured number.

## Who waits for whom, and how do you see it?

The re-check runs after a wait, so the wait decides who goes first and who fails. A row lock has two parts. The writer's xid goes into the row's xmax, so the lock lives on the page. The writer also holds a lock on its own xid until it ends, and a second writer sleeps on that lock. So a row lock lasts until the holder's COMMIT or ROLLBACK.

Waiters for one hot row are not served in arrival order. The first waiter holds a tuple lock on that row version, and after the first hand-over the later waiters race for it.

The wait graph has an edge from A to B when A waits for a lock that B holds. A deadlock is a cycle in that graph. Two transfers in opposite order make one.

- T2 waits for T1for acme, from 0.00 s.

- T1 waits for T2for beta, so the cycle closes.

- T2's timer firesafter 1 s: 40P01, rollback.

- T1 commitsThe total stays 200.

- A waiter sleeps with a timer of deadlock_timeout, 1 second by default. If the lock is not granted by then, that waiter runs the deadlock check.

- The detecting waiter is usually the victim. It gets SQLSTATE 40P01, deadlock_detected, but the docs say not to rely on which one.

- The fix is one lock order, SELECT ... ORDER BY tenant FOR UPDATE on both rows first, so a cycle cannot form. Retry 40P01 as well.

At work, pg_stat_activity shows a row wait as wait_event_type Lock, with transactionid or tuple. In this "who blocks whom" query, start from the session that blocks others and waits for nobody, often idle in transaction.

-- from phase03_transactions/lockwatch.py, WHO_BLOCKS. Copied. At work, drop the pid filter
SELECT a.pid,
       pg_blocking_pids(a.pid)            AS blocked_by,
       a.wait_event_type, a.wait_event, a.state,
       round(extract(epoch FROM now() - a.xact_start)::numeric, 1) AS xact_s,
       left(a.query, 50)                  AS query
FROM pg_stat_activity a
WHERE a.pid = ANY(%s)
ORDER BY a.xact_start

With log_lock_waits = on, each wait longer than deadlock_timeout writes a still waiting for line, and pg_stat_database.deadlocks counts cycles. Raising deadlock_timeout removes no cycle, and every victim waits longer.

A blocked writer waits for the holder's commit, then re-checks only that row.

A subquery or count in the WHERE clause decides on the old snapshot.

Run uv run python phase03_transactions/deadlock.py, then compare T2's wait with show deadlock_timeout.

Go deeper: lock internals, the deadlock report, timeouts, lock modes, multixacts and the log lines
Four sessions on one row. The core said that arrival order does not decide who gets a hot row next. Here is how pg_stat_activity shows four sessions updating one row on PostgreSQL 14. The holder waits for its client, the first waiter waits on the holder's xid, and the two later waiters wait on the tuple lock.

  pid  | wait_event_type |  wait_event   | pg_blocking_pids
-------+-----------------+---------------+------------------
 30723 | Client          | ClientRead    | {}
 30794 | Lock            | transactionid | {30723}
 30865 | Lock            | tuple         | {30794}
 30936 | Lock            | tuple         | {30794,30865}

When 30723 commits, 30794 gets the row and releases the tuple lock. The tuple-lock steps below show what the two later waiters do next.

The two parts in the source. The core named the two parts of a row lock, and the source shows both. The docs say there is "no limit on the number of rows locked at one time", and that "locking a row might cause a disk write". XactLockTableInsert takes the lock on a transaction's own ID, and its comment says "The lock can then be used to wait for the transaction to finish". A second writer that finds the row marked by a running transaction requests a ShareLock on that ID. This wait stops a dirty write, P0, w1[x]...w2[x] before the first transaction ends, which every level should forbid. Hermitage's G0 test, "Write Cycles", shows PostgreSQL's read committed blocks the second write until the first commits.

The tuple-lock steps. Each writer of a locked row follows four steps. It takes a heavyweight lock on the tuple, waits on the holder's xid with the ShareLock, writes its own ID into xmax, and releases the tuple lock. The reason for the first step: a wait on the xid alone "will release all waiters concurrently", which leads to "indefinite starvation of some waiters". After the first hand-over, at READ COMMITTED, the later waiters find a new xmax and wait on the new holder's xid with no tuple lock. "The queue has virtually fallen apart." So under one hot row, a writer can wait longer than its place in line suggests. At REPEATABLE READ the woken waiters fail with 40001 instead. lockwatch.py --case queue prints both pictures and the order it saw, in E13.

The two transfers, in full. The core showed the deadlock in short form. The full transfer order is: T1 updates acme, T2 updates beta, T2 updates acme, T1 updates beta. PostgreSQL does not search the wait graph at every wait, because the search costs time and most waits end sooner. So each waiter first sleeps for deadlock_timeout. T2 waited first, so T2 is the expected victim. That is inferred from the README, not from a run. The core's fix locks both rows first, in one order: SELECT tenant FROM tq_budget WHERE tenant IN ('acme', 'beta') ORDER BY tenant FOR UPDATE.

How the victim is chosen. If a deadlock exists, it "will be resolved, usually by aborting the detecting process' transaction". "If earlier waiters in the cycle have not yet run CheckDeadLock, then the first one to do so will be the victim." The default timeout is "one second (1s), which is probably about the smallest value you would want in practice", and in PostgreSQL 14 only superusers can change it. Three exceptions are verified in the source:

- Before it cancels anyone, the check tries to reorder wait queues, which breaks some cycles without an abort.

- Some waits fail at once, with no timer, when the new waiter and a waiter in the same lock's queue each need the other. The code is RememberSimpleDeadLock.

- An autovacuum worker that blocks the waiter is cancelled instead, and the log says "sending cancel to blocking autovacuum PID %d".

The docs: "Exactly which transaction will be aborted is difficult to predict and should not be relied upon." In textbook terms, PostgreSQL detects deadlocks and does not prevent them. Detection builds the waits-for graph and breaks a cycle by choosing a victim. Prevention schemes, such as wait-die and wound-wait, abort a transaction by priority before a cycle can form. deadlock_timeout sets the trade-off between the cost of checks and the time until a deadlock is broken. On PostgreSQL 14, the transaction that waited first ran the check "and gets aborted by the server". At the default, each deadlock costs the victim at least 1 second of waiting and a full redo, which is inferred from the timer rule.

Reading the report. The error has the message deadlock detected, one DETAIL line per process in the cycle, Process %d waits for %s on %s; blocked by process %d., and the HINT See server log for query details.. The server log only adds one more line per process, Process %d: %s, with the text of its query. The CONTEXT line comes from the row wait, while updating tuple (%u,%u) in relation "%s". For this lab the error should look like this. The numbers are an example, and the lab was not run:

ERROR 40P01: deadlock detected
      DETAIL: Process 41022 waits for ShareLock on transaction 901; blocked by process 41018.
              Process 41018 waits for ShareLock on transaction 902; blocked by process 41022.
      HINT: See server log for query details.
      CONTEXT: while updating tuple (0,1) in relation "tq_budget"

The lock mode comes from the ShareLock request, and transaction %u is how DescribeLockTag names a transaction ID. Read it as the wait graph, one edge per DETAIL line. The process numbers are backend process IDs, which pg_stat_activity.pid shows, and every lab session sets application_name to storage_lab. The transaction numbers are the IDs each process waits for. The CONTEXT line names the row the victim wanted. A printed PostgreSQL 14 example has the lines DETAIL: Process 30423 waits for ShareLock on transaction 122877; blocked by process 30723. and CONTEXT: while updating tuple (0,2) in relation "accounts".

# from phase03_transactions/deadlock.py:75, the SQL table. Copied
SQL = {
    "move": "UPDATE tq_budget SET credits = credits + %s WHERE tenant = %s",
    "lock_both": "SELECT tenant FROM tq_budget WHERE tenant IN ('acme', 'beta') ORDER BY tenant FOR UPDATE",
    "total": "SELECT sum(credits) FROM tq_budget",
}

With --ordered, T2's lock read waits for T1 at acme, the first row in the order. It holds nothing that T1 needs, so T1 finishes and T2 goes on. The docs' advice is to "acquire locks on multiple objects in a consistent order", and to retry the transactions "that abort due to deadlocks". run_with_retry treats 40P01 as retryable for that reason.

One order inside a statement, too. A single UPDATE locks its rows one by one, in the order its plan reads them, so two single statements can deadlock. One UPDATE accounts SET amount = inc_slow(amount) reads rows 1, 2 and 3 with a sequential scan. Another adds WHERE amount > 100.00 and, with sequential scans turned off, reads rows 3 and 2 through a descending index on amount. One of them gets ERROR: deadlock detected. Such deadlocks "do occur in high-load systems when batch row updates are performed". The fix is the same rule: lock first with SELECT ... ORDER BY id FOR UPDATE, then update. That fix is inferred, not run.

Settings that limit waits. Without a deadlock, a wait has no limit: a transaction "will wait indefinitely for conflicting locks to be released", so it is "a bad idea" to hold transactions open long.

SettingDefaultWhat it doesExists since

deadlock_timeout1sthe wait before the deadlock check, and before a log_lock_waits linebefore 14

log_lock_waitsoff, also in 18logs each wait longer than deadlock_timeoutbefore 14

lock_timeout0, offcancels a statement that waits longer for one lockbefore 14

statement_timeout0, offcancels a statement that runs longerbefore 14

idle_in_transaction_session_timeout0, offends a session idle inside an open transactionbefore 14

idle_session_timeout0, offends a session idle outside a transaction14, absent from the 13 docs

transaction_timeout0, offends a session whose transaction lasts longer17, absent from the 16 docs

Set them per role with ALTER ROLE ... SET, or per transaction with SET LOCAL, as the claim check does. That is this course's advice, and the docs point the same way. Setting statement_timeout or lock_timeout in postgresql.conf "is not recommended because it would affect all sessions", and the current docs say the same of transaction_timeout. They also warn against idle_session_timeout on connections from "connection-pooling software", which "may not react well to unexpected connection closure". Like deadlock_timeout, log_lock_waits needs a superuser to change in PostgreSQL 14.

Table locks. Every statement also locks each table it uses. A SELECT takes ACCESS SHARE, which "Conflicts with the ACCESS EXCLUSIVE lock mode only", and "Only an ACCESS EXCLUSIVE lock blocks a SELECT". A waiting request also blocks later requests that conflict with it. pg_blocking_pids reports this as a "soft block", by a session "ahead of it in the wait queue". Phase 4 builds its schema-change rules on these two facts.

The four row-lock modes. X marks a conflict.

Requested, heldFOR KEY SHAREFOR SHAREFOR NO KEY UPDATEFOR UPDATE

FOR KEY SHAREX

FOR SHAREXX

FOR NO KEY UPDATEXXX

FOR UPDATEXXXX

An UPDATE takes FOR NO KEY UPDATE, unless it changes a column with a unique index that a foreign key can use. Then it takes FOR UPDATE, as every DELETE does. At REPEATABLE READ and SERIALIZABLE, "an error will be thrown if a row to be locked has changed since the transaction started". That is the 40001 again, now for SELECT ... FOR UPDATE.

Multixacts. xmax has room for one transaction ID. When several transactions hold compatible locks on one row, PostgreSQL stores a multixact ID there instead, a group of transaction IDs with their lock modes, kept in pg_multixact. The usual source is a foreign key: of the shared modes, the core "uses only Key Share", for foreign key checks. The course's schema creates this case. tq_tasks.tenant references tq_tenants, so inserting a task for acme takes FOR KEY SHARE on acme's row. The slot reservation of the constraint section updates that row with FOR NO KEY UPDATE. The two do not conflict, so neither waits, and the row's xmax becomes a multixact. That is inferred from the table. A printed pgrowlocks for the same pair on PostgreSQL 14 shows multi as t and the modes {"Key Share","No Key Update"}. lockwatch.py --case multixact shows it on the course schema, not run by the author yet.

Multixacts have their own wraparound, as transaction IDs do. The member storage "can grow up to about 20GB before reaching wraparound". When it "exceeds about 10GB", aggressive vacuum scans "will occur more often for all tables". One old report shows the failure on PostgreSQL 9.3.5. Its workload ran SELECT ... FOR SHARE on one row from 26 connections, the member files grew until the newest overtook the oldest, and the server raised ERROR: could not access status of transaction. This course found no recent post-mortem with numbers. Phase 4 teaches freezing for transaction IDs and multixacts, with settings such as vacuum_multixact_freeze_min_age.

Lock signals at work.

SignalWhereWhat it tells youVersion

wait_event_type Lock, with wait_eventpg_stat_activitytransactionid: waits for a row's writer to end. tuple: waits behind another waiter for the same row. relation: waits for a table lock14 docs, Table 28.11

pg_blocking_pids(pid)a functionthe sessions that block this one, including waiters ahead of it. A prepared transaction shows as process 014 docs, 9.26

waitstartpg_locks"Time when the server process started waiting for this lock"new in 14

deadlockspg_stat_database"Number of deadlocks detected in this database"14 docs, 28.2.13

the log lines belowthe server logeach lock wait longer than deadlock_timeoutlog_lock_waits = on

In the core's who-blocks query, the session to start from usually has the largest xact_s. Frequent calls to pg_blocking_pids "could have some impact on database performance", because it needs "exclusive access to the lock manager's shared state for a short time". So run it when something is stuck, not every second. An empty wait_event does not prove that a session is not waiting. The view shows only the waits that the source code reports, and any other wait time is "unaccounted for".

process %d still waiting for %s on %s after %ld.%03d ms
process %d acquired %s on %s after %ld.%03d ms
process %d detected deadlock while waiting for %s on %s after %ld.%03d ms
process %d avoided deadlock for %s on %s by rearranging queue order after %ld.%03d ms

Every line except the "acquired" line has a DETAIL in the log, Process holding the lock: %s. Wait queue: %s., which starts Processes holding the lock when several sessions hold it. For a row wait, the first %s is the mode, such as ShareLock, and the second names the lock, such as transaction 901. The "acquired" line gives the whole wait once it ends. The last line is the queue reordering, a cycle broken without an abort. A fifth form, process %d failed to acquire ..., covers a rare case. No real sample from a fetched source is shown here, and E13 prints where your server writes them.

Evidence
Row locks: PostgreSQL 14 docs 13.3.2, and lmgr.c lines 585 to 600 and 668 at REL_14_24. P0 and Remark 3: Berenson and others, 1995. The tuple-lock steps: README.tuplock, lines 14 to 37. The four-session output and the broken queue: Rogov, pages 219 and 220, PostgreSQL 14. The timer and the victim: lmgr README, lines 340 to 360, 518 to 524 and 553 to 555, and proc.c lines 1209 and 1480. Detection against prevention: CMU 15-445, Fall 2025, lecture 18 notes. The report: DeadLockReport, deadlock.c lines 1089 to 1153, the context text at lmgr.c line 831, and Rogov page 227. Deadlocks in one statement: Rogov, pages 228 to 230. Settings: docs 20.8, 20.11 and 20.12, and the docs of each version. Table locks and soft blocks: docs 13.3.1 and 9.26. Row-lock modes: docs Table 13.3. Multixacts: docs 25.1.5.1, Rogov pages 213 and 214, and pgsql-bugs #12990 from 2015. Monitoring: docs Table 28.11, 9.26, 52.74 and 28.2.13, and Rogov page 244. Log formats: proc.c lines 1600 to 1631 and 1648.

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
Neither session waits, because the UPDATEs touch different rows and SSI's read records never block. B gets 40001, expected at its COMMIT. On the retry its new snapshot shows Alice off call, so it counts 1 and Bob stays on call. Most people expect a lock wait, because "serializable" sounds like locking.

- Each read takes a SIREAD lock, a record of what was read that never blocks anyone. pg_locks shows it with the mode SIReadLock.

- Both counts read both approver rows.

- A updates Alice's row, which B read, so B rw→ A. B updates Bob's row, which A read, so A rw→ B.

- When A commits, B sits in the middle with an edge to a committed transaction, so B cannot commit.

- B's COMMIT fails with ERROR 40001: could not serialize access due to read/write dependencies among transactions, and B runs again.

The cost comes as retries, not waits. On an auction-site workload, PostgreSQL 9.1 on one disk served these rates, where S2PL is classic locking.

SSI kept 97% of the throughput and locking kept 48%, so measure your own 40001 rate. A screen at READ COMMITTED takes no SIREAD locks, so set default_transaction_isolation for the whole application.

Go deeper: false alarms, the measured costs, deferrable reports, a past bug, and production advice
The pivot and the full error. The core's figure showed two rw edges in a row. A cycle of rw-antidependencies means that no serial order exists. Watching for the two-edge structure is cheaper than searching for whole cycles. The lab is expected to print the error in this form, not run by the author yet:

ERROR 40001: could not serialize access due to read/write dependencies among transactions
      DETAIL: Reason code: Canceled on identification as a pivot, during commit attempt.
      HINT: The transaction might succeed if retried.

How many false alarms you get. SIREAD locks "do not cause any blocking and therefore can not play any part in causing a deadlock". The SSI lock manager stores only SIREAD locks, "and hence cannot block". Four rules decide how often SSI cancels a transaction that would have been fine:

- Granularity. A lock covers a tuple, a page or a whole table. B-tree index reads are locked at page level.

- Sequential scans. "A sequential scan will always necessitate a relation-level predicate lock." Every later write to that table then conflicts with the scan.

- Promotion. Too many fine locks are combined into coarse ones. max_pred_locks_per_page, default 2, is the number of rows on one page before the lock becomes a page lock. max_pred_locks_per_relation has the default −2, which means max_pred_locks_per_transaction divided by 2, so 64 / 2 = 32 pages or tuples of one table. Past that, the lock covers the table. Combining locks can raise "the rate of serialization failures".

- Lifetime. SIREAD locks "often need to be kept past transaction commit, until overlapping read write transactions complete".

When the write comes before the read, PostgreSQL needs no SIREAD lock. The reader finds a newer version whose xmin its snapshot hides, and records the edge from that. Snapshot isolation already handles the other kinds of dependency. Its snapshot shows a reader what committed before it, and first-updater-wins stops two writes to one row. Under snapshot isolation every cycle has two rw edges in a row, each between concurrent transactions, which is why watching the pair is enough. PostgreSQL also tries to cancel the pivot so that an immediate retry will not fail again with the same serialization failure. The documented exception is a prepared transaction in the structure.

The error. The DETAIL line varies with the case. The source has ten reason-code lines, such as "during write" and "during commit attempt". A printed PostgreSQL 14 run of the same shape, two sums then two UPDATEs of different rows, shows exactly this DETAIL at the second COMMIT. So the line above is expected with good reason, but the lab was not run. The SQLSTATE never varies: serialization failures "always return with an SQLSTATE value of '40001'".

The measured costs, with their conditions. These are PostgreSQL 9.1 on 2012 hardware, and this course did not measure PostgreSQL 14.

WorkloadResultConditions

SIBENCH, key-value pairs, half updates and half full scansSSI used 10% to 20% more CPU than snapshot isolationin memory, tmpfs, Core 2 Quad Q9550, 8 GB

DBT-2++, TPC-C-like with a "credit check" transaction, 25 warehousesSSI 5% slower than snapshot isolationin memory, 4 threads

DBT-2++, 150 warehouses, 19 GBthroughput "indistinguishable from that of SI", failures under 0.25%disk-bound, 36 threads, 16-core Xeon E7310

deferrable read-only transactions in that runmedian wait for a safe snapshot 1.98 s, 90% within 6 s, all within 20 s1,200 tries

RUBiS, auction site, 85% read-only, 6 GBSI 435, SSI 422, S2PL 208 requests per second. Failures 0.004%, 0.03% and 0.76%Core 2 Quad Q9550, 8 GB, one 7,200 RPM disk

Where the core's 97% and 48% come from. On RUBiS, 422 / 435 = 97% and 208 / 435 = 48%. S2PL, strict two-phase locking, holds every lock until commit, so readers and writers block each other. Both numbers come from one machine of 2012. The RUBiS setup had 225,000 active auctions, 1 million completed ones and 1.35 million users, with several PHP application servers so the database was the limit. The SSI failure rate of 0.03% is about 1 retry in 3,300 transactions.

Deferrable reports, and the read-only anomaly. BEGIN ISOLATION LEVEL SERIALIZABLE, READ ONLY, DEFERRABLE may wait for a safe snapshot at the start. After the wait it "cannot be aborted, and does not need to take SIREAD locks". The SET TRANSACTION docs say the mode "is well suited for long-running reports or backups", and the wait in the table above is its price. It also answers the read-only anomaly of the anomaly section. At SERIALIZABLE, that anomaly's three transactions end in the same 40001. With READ ONLY DEFERRABLE, the third transaction instead blocked until T1 committed, and then read 910 and 0. That is a state of the order T1, T2.

The guarantee depends on the implementation. A Jepsen test of PostgreSQL 12.3 under SERIALIZABLE found "six cases of G2-item" in two minutes, with no process crashes needed. Each one "involved at least one read-write conflict for a freshly inserted row". The cause was tuple versions attributed to the wrong transaction ID. The fix is commit e620a38c, "Avoid update conflict out serialization anomalies.", released in PostgreSQL 12.4. Hermitage did not catch this bug. The commit says "Backpatch: All supported versions". Every PostgreSQL 14 release came after it, so your 14.24 should include the fix. That is inferred from the dates and was not checked in the 14 source. A variant that cuts false aborts, PSSI, was argued for and not adopted, for its memory cost.

Mixed levels. The core said to set the level for the whole application, and this is the reason. The guarantee covers "any set of successfully committed concurrent Serializable transactions". If Bob's screen ran at READ COMMITTED and Alice's at SERIALIZABLE, the pair could still break the rule. Mixed with other levels, Serializable "behaves as Repeatable Read without any notice", because a transaction at another level "will not set (or check) predicate locks".

Running SERIALIZABLE in production. The docs end their section with advice "For optimal performance when relying on Serializable transactions":

AdviceWhy

"Declare transactions as READ ONLY when possible."read-only transactions "will often be able to establish" at startup that they need no predicate locks

control the number of active connections, with a pool if neededfewer concurrent transactions form fewer rw edges. Inferred

"Don't put more into a single transaction than needed for integrity purposes."each read adds SIREAD locks, which can outlive the commit. Inferred from the lifetime rule

do not leave connections "idle in transaction" longer than neededthe docs name idle_in_transaction_session_timeout for it

remove FOR UPDATE, FOR SHARE and explicit locks that SSI made unneededthey add waits that SSI does not need. Inferred

raise the max_pred_locks_* settings when page locks get combined into a table lockcombining can cause "an increase in the rate of serialization failures"

encourage index scans, by lowering random_page_cost or raising cpu_tuple_cost"A sequential scan will always necessitate a relation-level predicate lock"

Two more errors belong to this level. When the predicate lock table is full, PostgreSQL 14 raises ERROR: out of shared memory with HINT: You might need to increase max_pred_locks_per_transaction.. And a replica refuses the level: serializable "is not yet available in hot standby", and setting it "will generate an error".

Try this now. Run uv run python phase03_transactions/write_skew.py --level serializable --retry --show-locks. Find the SIReadLock rows printed after the two counts, then the 40001 line, the statement it came from, and the retry's count.

Evidence
The dangerous structure and the pivot: Cahill, Röhm and Fekete, SIGMOD 2008, section 2.2, using a result of Fekete and others. SIREAD locks, safe snapshots, safe retry and costs: Ports and Grittner, "Serializable Snapshot Isolation in PostgreSQL", PVLDB 5(12), VLDB 2012, sections 4, 5.2, 5.4, 7.1 and 8.1 to 8.4, Figures 4 to 6. The docs' rules, settings and advice: PostgreSQL 14 docs 13.2.3, 20.12 and SET TRANSACTION. The error text: predicate.c lines 4125 and 4127 at REL_14_24, reason codes near lines 4821 and 4880, and the full-table error at lines 2487 to 2489. Printed runs: Rogov, pages 59, 60 and 236. The bug: Jepsen "PostgreSQL 12.3", 2020-06-12, section 3.2, commit e620a38c of 2020-06-11, and the 12.4 release notes of 2020-08-13. PSSI and the bug's cause: the study note. Hot standby: docs 27.4.

## How do you retry, and what can a savepoint rescue?

SERIALIZABLE turns write skew into a 40001, so the rule now holds only if the client retries correctly. After any error the transaction is aborted. PostgreSQL then accepts only COMMIT, ROLLBACK, ROLLBACK TO SAVEPOINT and PREPARE TRANSACTION. Every other statement gets 25P02, current transaction is aborted, and a COMMIT there replies ROLLBACK.

Wrong: send the failed statement again, and every attempt gets 25P02.

Right: ROLLBACK, BEGIN, and run the whole body, so a new snapshot shows the conflict's change.

The server cannot know that a retry is correct, so the client must do it. Four rules make the retry safe.

- Retry only 40001 and 40P01, because other errors fail again the same way.

- Put COMMIT inside the loop, because at SERIALIZABLE COMMIT itself can fail.

- Keep side effects out of the body, because an email inside it is sent once per attempt.

- Cap the attempts and wait a random time, 5 attempts and up to 10, 20, 40 and 80 ms in the lab.

A savepoint marks a point inside a transaction, and ROLLBACK TO SAVEPOINT undoes only the work after it. It rescues a 23505 duplicate key on one insert. It cannot rescue a 40001, because the transaction keeps its first snapshot and meets the same conflict, which is inferred and not run. Each savepoint is a subtransaction with its own xid, and PL/pgSQL EXCEPTION blocks and ORM nested transactions create them too.

- over 64 open subtransactionsA backend, the server process of one session, advertises at most 64 of them.

- snapshots marked suboverflowedA snapshot can no longer list them all.

- checks read pg_subtransEach check goes through a 32-page shared cache.

- waits on SubtransSLRUpg_stat_activity shows type LWLock, a lightweight lock on shared memory.

In one public case, a test reproduced the problem. Its replicas fell from about 360,000 to 50,000 transactions per second while the primary ran a long transaction. The team then removed every SAVEPOINT. A savepoint is not free on a busy server, and SubtransSLRU names its cost.

On 40001, roll back and run the whole transaction again from BEGIN.

Resending only the failed statement gets 25P02 on every attempt.

Run the lab's aborted-transaction psql script, E16, and watch COMMIT reply ROLLBACK.

Go deeper: the retry loop in code, which codes to retry, and subtransaction internals
The two failures the core's rules prevent. The first is the wrong retry, which resends only the failed statement. Every attempt then gets 25P02, whose full text is current transaction is aborted, commands ignored until end of transaction block. The request fails after the last attempt. The second is the common failure, SERIALIZABLE without a loop. A team switches the default level to stop write skew, and users then see 40001 as server errors, because nothing retries them. In the measured runs that was under 0.25% of transactions in one test and 0.03% in another. Each one is a failed request until the loop exists.

Why the wait is random, and what a savepoint rescues. The core's fourth rule waits a random time before each retry. The random wait spreads transactions that failed together, so they do not collide again at the same moment. The core's savepoint rescue works because ROLLBACK TO SAVEPOINT returns an aborted transaction to a working state. That fits a 23505 when the rest of the transaction is still valid. A subtransaction also has its own status, and the table below shows where subtransactions come from.

The loop. The lab's helper keeps the wrong way behind a flag, so its self-test can prove that it fails:

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

With retry_statement_only=True, the wrong way, the second attempt sends the body into the failed transaction. The self-test of pglab.py expects 25P02 there, from a fake connection that follows the server's rule. With the default, every attempt starts with BEGIN. lost_update.py --wrong-retry shows the same 25P02 against the real server, not run by the author yet. RetryPolicy caps any one wait at 500 ms, and contention.py raises the attempt cap to 50. Those values are this course's choice, not a measured optimum.

What the docs say to retry. The PostgreSQL 14 docs say to "retry the whole transaction from the beginning". The current docs, version 18, have a section on serialization failure handling. The error "will always have the SQLSTATE code 40001 (serialization_failure)". "It may also be advisable to retry deadlock failures. These have the SQLSTATE code 40P01 (deadlock_detected)." In some cases a retry of unique-key and exclusion failures, 23505 unique_violation and 23P01 exclusion_violation, is also right. An example is a new primary key chosen after reading the stored keys, while another client chose the same key. The docs recommend retrying 40001 "unconditionally", and say "more care is needed when retrying these other error codes". It is important "to retry the complete transaction, including all logic that decides which SQL to issue and/or which values to use". And "PostgreSQL does not offer an automatic retry facility, since it cannot do so with any guarantee of correctness." So "retry only 40001 and 40P01" stays the safe default, and you will still see 23505 raised by a race. Data read in a serializable transaction should not be "considered valid until the transaction which read it has successfully committed".

The aborted state, exactly. IsTransactionExitStmt lists COMMIT, PREPARE TRANSACTION, ROLLBACK and ROLLBACK TO SAVEPOINT. An earlier version of this phase said that only ROLLBACK is accepted, and the source corrected it. The printed PostgreSQL 14 reply to COMMIT in an aborted transaction is ROLLBACK.

Where subtransactions come from.

What you writeWhat PostgreSQL runs

SAVEPOINT sone subtransaction

a PL/pgSQL block with EXCEPTIONa subtransaction for the block

psql with \set ON_ERROR_ROLLBACK on"an implicit savepoint before each command"

Rails transaction(requires_new: true) inside a transactionSAVEPOINT active_record_1

A block with EXCEPTION "is significantly more expensive to enter and exit than a block without one", and savepoints incur "significant overhead" even when nobody rolls back to them. One printed PostgreSQL 14 transaction has rows with three xmin values: 782 for the transaction, and 783 and 784 for two subtransactions. The row of the subtransaction that rolled back stays on the page, and readers skip it. For "insert, and if the row exists, use it", INSERT ... ON CONFLICT needs no savepoint, as the constraint section shows.

The overflow, in the source. The 64 is PGPROC_MAX_CACHED_SUBXIDS, whose comment calls it a "guessed-at value". Past 64, snapshots taken while that transaction runs are marked suboverflowed. Then XidInMVCCSnapshot cannot search the snapshot's list of subtransaction IDs, and first reads pg_subtrans to map each ID to its top-level transaction. pg_subtrans is read through an SLRU, a small cache of pages in shared memory like the one for pg_xact. In PostgreSQL 14 it has 32 pages, NUM_SUBTRANS_BUFFERS. PostgreSQL 17 added subtransaction_buffers to size it. Its default is 0, which requests shared_buffers/512 up to 1024 blocks and not fewer than 16, and it can only be set at server start. transaction_buffers, the pg_xact cache, has the same default, and serializable_buffers defaults to 32 blocks. The 14 docs describe SubtransSLRU as "Waiting to access the sub-transaction SLRU cache".

The GitLab case, in full. Queries waited on SubtransControlLock, which PostgreSQL 13 renamed SubtransSLRU. The database on GitLab.com stalled for minutes. Only the replicas stalled, each time a long transaction was open, and course 5 covers replicas. The test by Nikolay Samokhvalov fell from about 360,000 to 50,000 transactions per second on the replicas when a long transaction started on the primary. The post found that "a single SAVEPOINT during a long-transaction could initiate this problem if many writes also occurred simultaneously". GitLab's code never nested more than 10 savepoints, so the replica path into pg_subtrans differs from the 64-entry overflow.

Try the aborted state. E16 sends two transactions to one psql session. The first prints the division error, the "current transaction is aborted" error, and ROLLBACK as the reply to COMMIT. The second sets a savepoint, fails, rolls back to the savepoint, and goes on to commit.

Evidence
The aborted state: postgres.c lines 1046 and 2752 to 2765 at REL_14_24, and Rogov pages 78 and 79. Retry rules: PostgreSQL 14 docs 13.2.2 and 13.2.3, and current docs 13.5, "Serialization Failure Handling", added in version 15 by this course's research. Subtransactions: Rogov pages 76 to 79, docs 43.6.8, and GitLab's post of 2021-09-29, "Why we spent the last month eliminating PostgreSQL subtransactions". Overflow: proc.h line 36, snapmgr.c lines 2285 to 2320, subtrans.h line 15, all at REL_14_24. Buffer settings: current docs, Resource Consumption, and docs 14 Table 28.12. Failure rates: Ports and Grittner 2012, sections 8.2 and 8.3.

## Which fix holds a rule: a lock, a version check, or a constraint?

A constraint holds its rule for every writer, at every level, without a retry.

Every fix so far made the later transaction wait or start again. Pessimistic control locks before it reads, with FOR UPDATE, so it costs waiting. Optimistic control checks at the write, with a version column or 40001, so it costs redone work. A constraint is a third way, because the database refuses the second writer.

Predict: the rule is at most one running task per tenant. Does a FOR UPDATE before the count hold it?
Two workers poll when none is running. No, the rule breaks. The SELECT returns no rows, so it locks none, and both workers claim, because a row lock covers only rows that exist.

A partial unique index is unique only among rows that match its condition. CREATE UNIQUE INDEX ON tq_tasks (tenant) WHERE state = 'running' holds this rule.

- W1 starts task 7, which adds an index entry for acme.

- W2 starts task 8, finds W1's entry while W1 is open, and waits.

- If W1 commits, W2 gets 23505, duplicate key value violates unique constraint. If W1 rolls back, W2 goes on.

- At SERIALIZABLE, a 40001 may come first instead.

The index holds at every level and needs no retry at READ COMMITTED, so catch 23505 as "another writer won". UNIQUE (task_id) on tq_approvals stops a second approval decision the same way. "At most 3" or "at least one approver" needs a counter row instead, one row that always exists. One conditional UPDATE changes it, running = running + 1 WHERE ... running < max_running, and the re-check makes it safe.

For a hot row, contention decides. With conflict probability p, optimistic control needs 1 / (1 − p) attempts on average. And n workers that start together on one row, with one commit per round, make n × (n + 1) / 2 attempts.

Optimistic attempts

Conflict probability p, in %
Workers on one row
Mean attempts . Total , against  with FOR UPDATE.

The common failure is a lock held across a 20-second model call. Every writer of that row then waits 20 seconds. Use two short transactions instead. Claim and commit, call outside, then record the result only if owner = %s still holds.

For "at most one", add a unique index, because it holds at every level.

A version-checked UPDATE whose row count nobody checks reports success for a lost write.

Predict the version retries at one hot row, then run the E9 contention command.

Go deeper: NOWAIT and SKIP LOCKED, advisory locks, version columns, upserts, and a table for choosing
The predict's idea, and the counter row in the lab. The core's predict tested a colleague's idea, SELECT ... FOR UPDATE on acme's running tasks before the count. It passes every test with one session. The core's counter row holds the rule instead, with this statement:

-- from phase03_transactions/phantom.py:98, SQL["reserve_slot"]. Copied, joined onto two lines
UPDATE tq_tenants SET running = running + 1
WHERE tenant = 'acme' AND running < max_running

phantom.py --fix parent-row keeps this counter on the tenant's row in tq_tenants. The second worker waits, re-checks 1 < 1, and updates 0 rows. The cost is a copy of a fact, so every transaction that starts or ends a task must change both, or they drift apart.

Two options of FOR UPDATE. NOWAIT: "the statement reports an error, rather than waiting". The error is SQLSTATE 55P03, lock_not_available, with the message could not obtain lock on row in relation "%s". SKIP LOCKED: "any selected rows that cannot be immediately locked are skipped". The docs warn that this "provides an inconsistent view of the data", and add that it "can be used to avoid lock contention with multiple consumers accessing a queue-like table". At READ COMMITTED, a FOR UPDATE that waited returns the row as the other transaction left it: it will "lock and return the updated row". At REPEATABLE READ it raises 40001 instead.

Advisory locks, a lock on a name. Sometimes the thing to lock is not a row, such as "the scheduler for tenant acme". Advisory locks are "locks that have application-defined meanings". You lock a number, often a hash of a name:

SELECT pg_advisory_xact_lock(hashtext('scheduler:acme'));  -- waits if needed, held until the transaction ends
SELECT pg_try_advisory_lock(hashtext('scheduler:acme'));   -- session level: true or false at once, never waits

The docs give three rules. Session-level locks "do not honor transaction semantics", so a lock taken in a transaction that rolls back is still held. All advisory locks use the shared lock table sized by max_locks_per_transaction and max_connections, so leaked locks can stop the server from granting any lock. And pg_advisory_lock(id) in a query with LIMIT is marked "danger!", because the LIMIT may apply after the function ran. Prefer the transaction-level form, which ends with the transaction. A session-level lock belongs to the server session, and a pooler in transaction mode hands that session to the next client. So the lock can stay on a server connection that another client gets next, while the xact form cannot. That is inferred, because this course did not read the PgBouncer docs.

Mattermost hit this problem with PostgreSQL behind PgBouncer, a pooler, in transaction mode. During load tests, some new workspaces failed to start, because their database migrations failed. Their migration library took pg_advisory_lock, so that two servers never ran one migration at once. That lock is session-level, and the library then lost the session that held it. Without that session, the library had no way to release the lock. The application hung and restarted, and each restart added more locks. As a midterm fix, the team set the PgBouncer option server_reset_query_always. For the long term, it chose to move to another migration library. The post confirms that the lock could not be released behind the pooler. It does not say which client got that server connection next, so that part above stays inferred.

A version column, in code.

# from phase03_transactions/contention.py:116, make_body(), the "version" strategy. Copied
        elif strategy == "version":
            n, v = conn.execute(SQL["read_version"], (row,)).fetchone()
            work()
            # 0 rows: another worker changed the row after our read. Ignoring
            # the count would report success for a write that never happened.
            if conn.execute(SQL["cas"], (n + 1, row, v)).rowcount == 0:
                raise _Conflict()

SQL["cas"] holds UPDATE tq_counters SET n = %s, version = version + 1 WHERE id = %s AND version = %s. At READ COMMITTED, the second writer waits for the first one's row lock. It then re-checks version = %s on the new row, which no longer matches, so it updates 0 rows. _Conflict carries SQLSTATE 40001, so run_with_retry starts the whole transaction again.

One statement. Sometimes the read, the check and the write fit in one SQL statement, and the server does all three under the row lock. The atomic spend is this kind, SET credits = credits - 80 WHERE ... AND credits >= 80. It needs no retry at READ COMMITTED, and it holds the lock only from that statement to COMMIT. Its limit is that the whole decision must be expressible in SQL. The first fix for check-then-act is the same idea: "Replace procedural code with declarative one". A design principle states it for constraints. If a constraint "can be expressed to the DBMS (e.g. using a foreign key, uniqueness, or exclusion constraint), then the DBMS can enforce it regardless of isolation level". Where it cannot, "the conflict can be materialized by creating a dummy row", which is the counter row. At REPEATABLE READ the slot reservation gets 40001 instead of 0 rows, and either way at most one task runs. The same move fixes the approvers: keep the count of approvers on call in one row, and change it with a conditional UPDATE that keeps it above 0.

Constraints that hold rules.

RuleConstraintWhat the second writer gets

at most 1 running task per tenantCREATE UNIQUE INDEX ON tq_tasks (tenant) WHERE state = 'running'waits for the first writer, then 23505 unique_violation

one decision per taskCREATE UNIQUE INDEX ON tq_approvals (task_id)waits for the first writer, then 23505

insert a row, or update it if it existsa unique key, and INSERT ... ON CONFLICT (key) DO UPDATEat READ COMMITTED, no error: its UPDATE runs on the row the first writer inserted. At REPEATABLE READ and SERIALIZABLE, 40001 when its snapshot cannot see that row

The docs' own partial unique index lets each subject and target have only one successful entry: CREATE UNIQUE INDEX tests_success_constraint ON tests (subject, target) WHERE success;. Such an index "enforces uniqueness among the rows that satisfy the index predicate". The core's W2 waits because its insert is a B-tree insert. In the B-tree code, _bt_doinsert waits for the open first writer with XactLockTableWait. So no second claim can succeed while the first may still commit. If the first writer commits, the check finds a live duplicate and raises duplicate key value violates unique constraint "%s" with the DETAIL Key %s already exists.. Your code must not treat this 23505 as a server fault. At SERIALIZABLE, the code checks for an SSI conflict first, which is why 40001 may come instead. The docs show the same thing from outside: "it is possible to see unique constraint violations caused by conflicts with overlapping Serializable transactions even after explicitly checking that the key isn't present before attempting to insert it." phantom.py --fix unique-index shows the first row, not run by the author yet.

For upserts, "ON CONFLICT DO UPDATE guarantees an atomic INSERT or UPDATE outcome". Unless an unrelated error occurs, one of the two outcomes holds "even under high concurrency". It needs no savepoint, so it pays no subtransaction. At the two higher levels, ExecCheckTupleVisible raises could not serialize access due to concurrent update when the conflicting row was committed after the transaction's snapshot. So an upsert at those levels still needs the retry loop.

The approval, fixed two ways. The core said that UNIQUE (task_id) stops a second decision, and here is the case it stops. The naive approval counts the task's rows in tq_approvals, and inserts a decision if the count is 0. Alice inserts approve and Bob inserts reject after both found no decision, which is the phantom form of write skew. The expected naive line, not run, is FAIL approval: task 2 has decision(s) ['approve', 'reject'], state awaiting_approval, and the outbox holds both task.approved and task.rejected. The first fix turns the decision into a write on the task's own row, run first:

-- from phase03_transactions/taskqueue.py:148, SQL["decide_task"], run first. Copied
UPDATE tq_tasks SET state = %s WHERE id = %s AND state = 'awaiting_approval'

Only when it updates 1 row does the transaction insert the decision and the event. Bob's UPDATE waits for Alice's row lock. At READ COMMITTED it re-checks state = 'awaiting_approval', now false, and updates 0 rows. At REPEATABLE READ it gets 40001, and its retry updates 0 rows. SERIALIZABLE with a retry also fixes the naive version, and taskqueue.py --check approval --variant naive --level serializable --retry is expected to pass. The second fix is the unique index. It makes Bob's insert wait and then fail, and taskqueue.py --check approval --variant naive --unique-decision is expected to pass. In production, keep both. The state change carries the logic, and the index is the rule that later code cannot break.

The arithmetic, worked. At p = 0.1 the mean is 1.11 attempts, at p = 0.5 it is 2, and at p = 0.9 it is 10. Ten workers on one counter row, one commit per round, make 10 × 11 / 2 = 55 optimistic attempts for 10 commits, and the unluckiest makes 10 of them. Pessimistic control makes only 10 attempts, and the last worker to get the row waits for the nine before it, each for its whole transaction. Which worker is last is not decided by arrival, as the lock-wait section showed. Neither number was measured in this course, and contention.py measures both on your laptop.

Three workers increment one rowPessimistic: FOR UPDATEOptimistic: version check

round 1W1 locks, reads 0, writes 1, commits. W2 and W3 waitall read 0, version 0. W1 writes 1. W2 and W3 update 0 rows and start again

round 2W2 locks, reads 1, writes 2, commitsW2 and W3 read 1. W2 writes 2. W3 updates 0 rows

round 3W3 locks, reads 2, writes 3, commitsW3 reads 2 and writes 3

total3 attempts, and the waits add up. A 4th waiter would race W3 after W23 + 2 + 1 = 6 attempts, no waits

How to choose. Each row gives a situation, the choice it favors, and the measurement that would prove it wrong. The thresholds are this course's example from the formula, not measured limits.

SituationPreferWhyMeasure to check it

the decision fits in one UPDATE whose condition reads only that rowone conditional statementno retry and no explicit lockrows updated, 0 or 1

the rule is "at most one"a unique index, partial if neededholds at every level, and for later codecount of 23505

conflicts are rare, p under about 0.1optimisticabout 1.11 attempts at p = 0.1, and nobody waitsretries per commit

many writers on few rowspessimistic1 / (1 − p) grows fast: 10 attempts at p = 0.9lock waits, p99 of the transaction

workers take items from a queueFOR UPDATE SKIP LOCKEDeach worker takes a different rowclaims per second, rows skipped

the rule spans many rows or a conditionSERIALIZABLE and a retry, or a parent rowrow locks cannot cover rows that are not there40001 rate

the thing to serialize is not a rowpg_advisory_xact_lockone holder per key until the transaction endslock waits on advisory

the work between read and write is slow, such as a network callneither inside one transactionsplit it into two short transactionstime a lock is held

The two short transactions, in SQL. The core split the 20-second model call into two short transactions. The second one is UPDATE ... WHERE id = %s AND state = 'running' AND owner = %s. The open snapshot of a slow call also holds back vacuum, so a lock held across it costs more than waits.

The E9 command is uv run python phase03_transactions/contention.py --workers 8 --increments 200 --hot-rows 1,64. The phase's quick version adds the strategies: uv run python phase03_transactions/contention.py --workers 8 --increments 200 --hot-rows 1,64 --strategies naive,for-update,version. Read the lost and retries columns for each hot-row count. The two short transactions leave one hole, a worker that dies between them, and the next section closes it with a lease.

Evidence
NOWAIT and SKIP LOCKED: PostgreSQL 14 docs, SELECT, "The Locking Clause", and errcodes.txt line 419 and heapam.c line 4941 at REL_14_24. Advisory locks: docs 13.3.5 and 9.27.10, Table 9.98, and Rogov page 234. The pooler mechanism: the study note, inferred. The lock lost behind the pooler: a Mattermost blog post by Angelos Kyratzakos, 2022-01-11, its migrations part. Declarative fixes: Rogov page 47. The constraint principle and the dummy row: Ports and Grittner 2012, section 2.2, from the study note. Partial unique indexes: docs 11.8, Example 11.3. The unique-insert wait: nbtinsert.c lines 224, 636 and 665 at REL_14_24. The serializable unique violation: docs 13.2.3, from the study note. Upserts: docs, INSERT, and nodeModifyTable.c line 232. The contention formulas are checked by contention.py --self-test.

## What happens to a claimed task when its worker dies?

A lock ends at COMMIT, so a claim that must last needs an expiry time.

After the first of two short transactions commits, a claim is only a value in a row. The naive claim also loses an update, because both workers UPDATE task 1 WHERE id = 1, which still matches after the wait. The fixed claim finds and claims in one statement, UPDATE ... WHERE id = (SELECT id ... WHERE state = 'queued' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED), which skips rows another worker holds.

Predict: a worker claims a task this way, commits, starts a 30-second model call, and is killed. What does the queue show a minute later?
The task still says running with the dead worker as owner, and it will for ever. SKIP LOCKED only chose who got the row at the claim, and the row lock ended at COMMIT.

The fix is a lease, a claim that ends at a stated time unless its worker renews it. A reaper is the statement that hands expired leases back to the queue.

- The claim also sets lease_until, and the worker commits and works outside any transaction.

- The reaper sets state = 'queued' and clears the owner WHERE state = 'running' AND lease_until < now() AND attempts < %s.

- Another worker claims the task, and attempts grows by 1.

- The completion names its owner, ... AND owner = %s, so a slow worker's late completion updates 0 rows and drops its result. This holds only while an owner name is never reused for two claims of one task. Checking attempts too closes that gap, which is inferred from the SQL.

- The attempts cap stops a task that kills every worker from running for ever.

The reaper, the completion and a new claim all change one row, so its lock orders them and each re-checks that row. The price is at-least-once work, because a slow worker and its replacement can both run the job.

A long transaction anywhere also slows a busy queue, because claims leave dead versions. VACUUM keeps them while an open snapshot might need them, and the oldest such snapshot is the cleanup horizon. In one queue at about 50 jobs a second, one open transaction slowed each claim. The time to lock a job rose from under 0.01 s to 0.1 s and more. Index WHERE state = 'queued', watch age(backend_xmin), and set idle_in_transaction_session_timeout.

Go deeper: other claim fixes, three lease designs, owner reuse, fencing, and the queue measurement
The naive claim, in full. The core said the naive claim loses an update. A first version would write it as two statements. It runs SELECT id FROM tq_tasks WHERE state = 'queued' ORDER BY id LIMIT 1, then UPDATE tq_tasks SET state = 'running', owner = %s WHERE id = %s. Both workers first SELECT task 1 as the first queued task, so both run it. taskqueue.py --check claim --variant naive is expected to print the line below, not run by the author yet:

FAIL claim: 2 worker(s) believe they claimed task 1. The row says owner B, attempts 2. 2 task.claimed event(s)

The fixed claim, copied. This is the core's one-statement claim, as the lab writes it.

# from phase03_transactions/taskqueue.py:134, SQL["claim_fixed"]. Copied
    "claim_fixed": ("UPDATE tq_tasks SET state = 'running', owner = %s, attempts = attempts + 1 "
                    "WHERE id = (SELECT id FROM tq_tasks WHERE state = 'queued' "
                    "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING id"),

With this claim, worker B's subquery skips task 1, finds no other queued task, and updates 0 rows at once with no wait. Rogov says SKIP LOCKED suits batches and "parallel processing of event queues". "However, avoid inventing other use cases for this command".

The check sets lock_timeout = '2s' for B, so a query that waited by mistake would fail instead of hanging. Two other fixes also work. AND state = 'queued' in the naive UPDATE makes B wait and then update 0 rows. REPEATABLE READ with a retry makes B fail with 40001 and find no queued task on its second attempt. taskqueue.py --self-test checks both in the model. It expects 2 claims for the naive form at READ COMMITTED, and 1 for each fix.

The lease SQL. The lab's lease claim, SQL["claim_lease"], is claim_fixed with lease_until added. It sets lease_until = now() + %s * interval '1 millisecond'. The reaper is one statement:

-- from phase03_transactions/taskqueue.py:144, SQL["reap"]. Copied, joined onto two lines
UPDATE tq_tasks SET state = 'queued', owner = NULL, lease_until = NULL
WHERE state = 'running' AND lease_until < now() AND attempts < %s RETURNING id

Three designs for a dead worker. Each one pays in a different place.

DesignWhen the worker diesWhat it costs

hold the row lock of FOR UPDATE SKIP LOCKED for the whole jobthe transaction ends with the connection, so the task is free againone open transaction per running job. It holds a connection, and it holds back the cleanup horizon

claim with a lease, lease_until, and run a reaper that requeues expired leasesanother worker runs the task once the lease has expiredat least once: a slow worker and its replacement can both run it. The work must be idempotent, and attempts need a cap

a session-level advisory lock per taskthe lock goes when the session endsthe claim lives on one connection, and session locks ignore COMMIT and ROLLBACK

When the owner check is not enough. Here is the owner-reuse case that the condition in the core's step 4 rules out. Suppose slow worker A loses the task to the reaper and then claims it again. Its old completion would then pass the owner check. Checking attempts as well makes each claim unique. That point is inferred from the SQL, and the lab does not test it. A long job also needs a heartbeat, an UPDATE that moves lease_until forward with the same owner check. The heartbeat is a design note, not part of the lab.

The lease protects the row, not the call. The owner check guards writes to this database only. A slow worker's calls to a model API, a payment provider or mail still happen. The receiver must be able to reject a stale worker. So each lease renewal raises a token that only grows, the call carries it, and the receiver drops anything older. The effect also needs an idempotency key on the far side. That design is inferred, and fencing tokens are the subject of course 5, Phase 4.

Expected lease output. taskqueue.py --check lease --variant naive is expected to print FAIL lease: task 1 is running, owner A. Its worker is dead, and nothing will ever run it. --check lease --variant fixed is expected to print PASS lease: task 1 is done, owner B, with the late completion shown as 0 rows. Neither was run by the author yet.

The queue measurement, with its conditions. The core gave the measured slowdown. Here is the mechanism, then how it was measured. Each claim replaces a queued version, and each finished job leaves one more dead version. So one long transaction anywhere in the database lets dead versions pile up, and each claim's index scan steps over more of them. Indexes carry no visibility information, so each candidate entry needs a heap fetch and a visibility check. The claim loop walked the same dead rows each time.

The queue ran on Heroku Postgres with the Que library, which claimed jobs with advisory locks in a recursive query, not with SKIP LOCKED. One producer, one worker and one transaction held open processed about 50 jobs a second. The lock time grew to "15x that level at times of 0.1 s and above". One hour in, 60k jobs were queued. By the end of the test, the table approached 100,000 dead rows. Its VACUUM VERBOSE printed DETAIL: 247311 dead row versions cannot be removed yet.. In PostgreSQL 14 that line ends with , oldest xmin: %u, and the xmin names the snapshot to look for. The original problem was one idle-in-transaction session opened for analytics by another team. That the same decay hits a SKIP LOCKED queue is inferred from the shared index-scan mechanism. queue_horizon.py, E15, is the check: it holds one REPEATABLE READ snapshot and runs the claim loop.

The core's three defenses, in full. The full index is CREATE INDEX tq_tasks_queued ON tq_tasks (id) WHERE state = 'queued'. The partial index alone is not enough, because the scan still steps over dead entries. age(backend_xmin) in pg_stat_activity names the session that holds the horizon, and Phase 4 alerts on it. Set the timeouts per role, as the lock-wait section advised. End long transactions with transaction_timeout on PostgreSQL 17 and later.

Evidence
The claim, lease and reaper SQL: phase03_transactions/taskqueue.py lines 134 and 144. The queue measurement: Brandur Leach, "Postgres Job Queues & Failure By MVCC", 2015-05-18, sections "Slow lock time" and "Dead tuples", read in full by the study note. The VACUUM line: vacuumlazy.c line 1656 at REL_14_24. The SKIP LOCKED caution: Rogov page 224. Fencing tokens and idempotency keys: the study note's "Missing" item, inferred.

## How does every committed event reach the broker?

Every event the queue writes must also outlive COMMIT. The transactional outbox stores each event as a row in tq_outbox, in the transaction that makes the change. A relay process reads stored events, publishes them to the broker and marks them. A dual write instead commits and then publishes from your code, so a crash between the two loses the event.

The outbox INSERT reads nothing, so atomicity alone ties the event to the change. The bug hides in the relay. The naive relay keeps the highest id it has published and polls WHERE id > last_id. An id comes from a sequence at INSERT and is never rolled back, while a row becomes visible only at COMMIT. So ids follow insert order, and rows appear in commit order.

The naive relay skips an event

Step 1: W1 inserts id 1 and stays open.

Step 2: W2 inserts id 2.

Step 3: W2 commits, so only id 2 is visible.

Step 4: the relay sees only id 2 and sets last_id to 2.

Step 5: W1 commits, so id 1 appears.

Step 6: the relay asks for ids above 2, so event 1 is never published.

The lab's fixed order, expected and not run. The widths show order, not time.

No isolation level fixes this. The order W2, relay pass 1, W1 explains every read, so the history is serializable. The relay at SERIALIZABLE is expected to fail the same way, which is inferred and tested by E11.

The fix stops tracking ids. Each pass selects WHERE sent_at IS NULL ORDER BY id LIMIT 100 FOR UPDATE SKIP LOCKED, publishes, marks the rows sent and commits. Event 1 is unsent when pass 2 runs, so pass 2 publishes it. Delivery is now at least once, because a relay that dies between publishing and marking sends the rows again. So the consumer inserts each event id with ON CONFLICT DO NOTHING in the effect's transaction. On 0 rows, it skips the effect.

Only a test that commits the higher id first, while the lower is open, shows this skip.

Precision Nutrition had this skip in production, with readers that polled an events table by id. After a few weeks, many errors appeared, because some earlier events had never been processed. The logs showed that a reader processed events 185, 186 and 189. A later query found events 187 and 188 in the table. The team first suspected that one event processor made a wrong assumption about event state. In fact, the transaction that wrote 187 and 188 started before the one that wrote 189. But it committed after that one, so the reader passed 187 and 188 while they were invisible. Waiting for each next id would stop the reader, because some ids are never used. In that table, about 0.6% of the ids were missing. The fix took ids from a counter row that every writer updates, so the ids follow commit order.

A relay polls unsent rows, because events appear in commit order, not id order.

A relay that keeps the highest id skips a slow transaction's event for ever.

Run E10's taskqueue.py check naive, then fixed, and compare the exit codes.

Go deeper: the relay code, a cursor that never skips, delivery order, and the whole audit
The consumer, in full.

-- the consumer's own database. A design, not part of the lab
BEGIN;
INSERT INTO processed_events (event_id) VALUES (%s) ON CONFLICT DO NOTHING;
-- 0 rows inserted: this event was applied before. ROLLBACK, and acknowledge it
-- 1 row inserted: apply the effect here, then COMMIT

The primary key on event_id turns a second delivery into 0 rows with no error. The record and the effect commit together, so a crash leaves both or neither. The outbox write adds no anomaly at READ COMMITTED, because the INSERT reads nothing that a decision depends on. The full relay query is SELECT id, task_id, event_type FROM tq_outbox WHERE sent_at IS NULL ORDER BY id LIMIT 100 FOR UPDATE SKIP LOCKED.

The pattern's promise. The service should "first store the message in the database as part of the transaction that updates the business entities". The benefit: "Messages are guaranteed to be sent if and only if the database transaction commits". taskqueue.py --check dual-write stops the worker right after COMMIT. The naive version then has a done task and no event, and the outbox version has its event row, which the relay publishes. The change itself is one conditional UPDATE, ... WHERE id = %s AND state = 'running' AND owner = %s, which re-checks its condition after any wait. The sequence rule, from the docs: sequence changes "are immediately visible to all other transactions and are not rolled back", and "nextval and setval calls are never rolled back".

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

Duplicates and order. --crash-before-mark is expected to show the repeat as one "delivered twice" line. The pattern's own page says the relay "might publish a message more than once", so "a message consumer must be idempotent". Debezium's outbox event router puts the event id in a header: "You can use this ID, for example, to remove duplicate messages." The fixed relay also has no global order, because event 2 was published before event 1. If a consumer needs the order of one task's events, give each event a sequence number within its task, and let the consumer reorder or reject. That design is inferred, and not part of this lab. The consumer table's design is inferred too, and its parts are verified: the ON CONFLICT rule of the constraint section, and Debezium's id header.

A cursor that never skips. Some relays must keep a cursor, for example to replay from a position. Each outbox row then stores the ID of the transaction that wrote it, in a column of type xid8, the 64-bit form of a transaction ID, with the default pg_current_xact_id(). The relay reads only rows whose ID is below the snapshot's xmin, in transaction ID order:

-- after Dudycz 2022, with this schema's names, as a row comparison. A design, not the lab's SQL.
-- pg_cast.dat at REL_14_24 has no cast from bigint to xid8, so the saved cursor goes in as text.
SELECT id, task_id, event_type FROM tq_outbox
WHERE (xid, id) > (%(last_xid)s::text::xid8, %(last_id)s)
  AND xid < pg_snapshot_xmin(pg_current_snapshot())
ORDER BY xid, id LIMIT 100;

Every transaction with an ID below the snapshot's xmin has ended, by the snapshot rule. So no row can appear behind the cursor later. Three conditions make this hold. Each row must carry the ID of its own top-level transaction, and pg_current_xact_id() returns that ID even inside a savepoint. The cursor must move only to a row that the same query returned. And pg_current_snapshot() must be the snapshot that the query reads with, which in PostgreSQL 14 it is. The order is the order in which transactions got their IDs, not their commit order. Its cost is that one long transaction that has written stops the relay at its ID. Transaction IDs are shared by every database of the server, so that transaction can be anywhere on it. That cost is inferred from the same rule. taskqueue.py --self-test checks the rule on a simulated outbox, in simulate_xid_relay, and the lab's relay does not use it.

Measured relays. This course found no production post about a PostgreSQL outbox with measured throughput or latency. One team writes events into the WAL with pg_logical_emit_message() for Debezium, instead of an outbox table. Another reads MySQL's change log with Debezium. So neither is an outbox table with numbers. What happens when the consumer is another service and one side fails halfway is in course 5, Phase 2.

The whole audit. Each row has a check in taskqueue.py that exits with 1 when the rule is broken.

TransactionRuleAnomaly at READ COMMITTEDFixLevel after the fix

claimone worker owns a claimed tasklost update on ownerone UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED)READ COMMITTED

claim, after its commita claimed task runs again if its worker diesnot an isolation anomaly: a crash leaves it running for evera lease, a reaper, and an owner check on completionREAD COMMITTED

approvalone decision per taskwrite skew on an empty set, the phantom forma conditional state change on the task row first, and UNIQUE (task_id)READ COMMITTED

outbox writethe event commits if and only if the change doesnone: the INSERT reads nothingnone neededREAD COMMITTED

outbox relayevery committed event is publishednot an isolation anomaly: ids are not in commit ordermark rows sent, poll unsent rowsany

The audit method is the same for any transaction. Write down the rule it must keep, and find the reads that its decision depends on. Ask which other transaction can change those reads before the commit. Fix it with the smallest change, and keep a test that fails without the fix. Check the scope first, then the level.

Try the whole audit. Run uv run python phase03_transactions/taskqueue.py --check all --variant naive --level read-committed, then the same with --variant fixed. Check the exit code with echo $?: 1 for the first run and 0 for the second.

Expected outputs. --check outbox --variant naive --relay-level serializable: FAIL outbox: committed events [1, 2], published [2], never published [1]. --check outbox --variant fixed --crash-before-mark: delivered twice: [2], then PASS outbox: committed events [1, 2], published [2, 1, 2], never published []. Neither was run by the author yet.

Evidence
The pattern: Chris Richardson, "Pattern: Transactional outbox", microservices.io. Sequences: PostgreSQL 14 docs 13.2 and CREATE SEQUENCE. The relay code: phase03_transactions/taskqueue.py line 173. The event id header: Debezium 3.7 documentation, Outbox Event Router. The cursor: Oskar Dudycz, "How Postgres sequences issues can impact your messaging guarantees", 2022-10-28, and xid8funcs.c line 411 at REL_14_24, with Rogov page 77 for savepoints. The other relays: SeatGeek, 2025-02-07, and Shopify, 2021-03-12. The skipped events in production: Justin Giancola, PN Tech blog, "Fun with Multiversion Concurrency Control", part 1 of 2020-03-06 and part 2 of 2020-05-15, dates from the page addresses.

## What you can do now, and what comes next

You can now name an anomaly and pick what stops it. You can also build a queue whose claims and events survive a crash. Phase 4 asks why the planner chose a sequential scan over your index, and what a migration does to a table. It also shows how vacuum removes the dead versions this lesson left.

## Lab: reproduce each anomaly, then stop it

Open the lab: E1 to E16, written and reviewed, not run by the author yet
The lab and the checkpoint come from the phase word for word, so they name the phase's sections by number. Sections 3.1 and 3.2 are "Why did both approvers commit without an error?". Section 3.3 is "Which anomaly is it, and which level stops it?" and the re-check section after it. Section 3.4 is "Who waits for whom, and how do you see it?". Section 3.5 is the two SERIALIZABLE sections. Section 3.6 is "Which fix holds a rule: a lock, a version check, or a constraint?". Section 3.7 is the two task-queue sections at the end.

Where it runs, and what it costs. Everything runs on your laptop and costs nothing. The labs need your local PostgreSQL 14 at /tmp:5432, in the database storage_lab, which Phase 1 created. They use Python 3.12 or later with psycopg 3.3.6, which pyproject.toml pins. The model mvcc_model.py and every --self-test run with no server. Run all the commands from elite-storage/code/. Time: about 3.5 hours for the reading in the phase, and the labs take 3 to 4 hours.

The labs below are written and reviewed, but were not run by the author. Each script was checked with python3 -m py_compile only. Every "Expected" line says "Not run by the author yet." and then gives the expected shape. Each value comes from the docs or source that this phase cites, or from reading the code by hand. None of them is a measurement. Each script fixes the order of steps. So the results that do not depend on time should match exactly. Times, such as the deadlock wait, depend on your machine.

What you build. You build three things. First, two-session reproductions of every anomaly of this phase, on your PostgreSQL 14. Second, an offline model of the same rules. Third, the audit of the task queue:

FileWhat it holdsSelf-test checks

shared/pglab.pysessions driven step by step, the lock-wait probe, run_with_retry, the database guardretry of the whole transaction, a 40001 at COMMIT, the attempt cap, 25P02 for the WRONG retry

phase03_transactions/mvcc_model.pyrow versions, snapshots, first-updater-wins, SSI, waits and deadlocks, six historiesthe snapshot example of Table 9.77, the matrix of section 3.3, each rule removed in turn

phase03_transactions/lost_update.pythe budget spend, four strategies, two schedules, --retry, --wrong-retrythe invariant, the SQL of each strategy

phase03_transactions/write_skew.pythe approvers on call, --fix lock-rows, --show-locksthe rule and the invariant

phase03_transactions/phantom.pythe phantom read, the running limit, three fixes, one a partial unique indexthe limit arithmetic, the SQL of each fix

phase03_transactions/deadlock.pytwo transfers in opposite order, --ordered, --retrythat opposite order forms a cycle and one order does not

phase03_transactions/contention.pyfive strategies under 1 to 64 hot rows1 / (1 − p), n (n + 1) / 2, the percentile method

phase03_transactions/taskqueue.pythe schema, five checks with the lease, --unique-decision, exit code 1 on a broken invariantthe claim in the model, both relays and the xid8 cursor on a simulated outbox, the lease and reaper SQL

phase03_transactions/lockwatch.pya queue of waiters on one row, the "who blocks whom" query, pg_locks.waitstart, log_lock_waits, a multixactthe head of a wait chain on Rogov's printed rows, the log-line format

phase03_transactions/queue_horizon.pya claim loop with and without one open snapshotthe percentile method, the claim and index SQL

Every PostgreSQL lab refuses a database whose name does not start with storage_lab. It drops and creates only tables that start with tq_. The demonstration of this phase is E4, E5 and E10. E4 and E5 reproduce two anomalies on demand, and stop each with a named mechanism. E10 hardens the task queue's three transactions, each with a check that fails at the old level.

The first uv run installs psycopg 3.3.6, so it needs the network once.

-
 E1 (offline). Run every self-test of this phase, then the earlier phases' self-tests.

-
Run: for f in shared/pglab.py phase03_transactions/*.py; do echo "$f"; uv run python "$f" --self-test; done

-
Then run: for f in shared/durable.py phase01_durability/*.py phase02_structures/*.py; do echo "$f"; uv run python "$f" --self-test; done

-
Expected: Not run by the author yet. self-test passed after each of the 10 Phase 3 files, and after each of the 12 earlier files. This phase added shared/pglab.py and a dependency, and changed no earlier file.

-
If it fails: the assertion message names the rule or the number. Compare it with the section it comes from before you change any code.

-
Teaches: each rule that the text calls important has a check that fails without it.

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
Expected: Not run by the author yet. created database storage_lab only if Phase 1 did not create it. Then server_version 14.24, default_transaction_isolation read committed, deadlock_timeout 1000ms, lock_timeout 0ms, idle_in_transaction_session_timeout 0ms, max_pred_locks_per_transaction 64, max_pred_locks_per_relation -2 and max_pred_locks_per_page 2. These are the defaults that sections 3.4 and 3.5 cite.

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
Expected: Not run by the author yet. Repeatable read: two UPDATEs of 1 row each, two successful COMMITs, no wait, and RESULT: BROKEN. 0 approver(s) on call. Serializable: one ERROR 40001: could not serialize access due to read/write dependencies among transactions, expected at B's COMMIT, with a DETAIL: Reason code: line and HINT: The transaction might succeed if retried.. Then count 1, bob stays on call, and RESULT: holds. 1 approver(s) on call.

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
Expected: Not run by the author yet. After the two counts, obs lines with SIReadLock for both sessions. The table has two rows, so the planner should use a sequential scan. The docs say that a sequential scan takes a relation-level predicate lock. So expect locktype relation on the table tq_oncall. That is inferred, and was not run.

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
Expected: Not run by the author yet. The naive run prints FAIL for claim, approval, outbox, lease and dual-write, and exit 1. The claim line is the one in section 3.7. The fixed run prints PASS for all five, and exit 0. The lease check sleeps for its lease of 300 ms and 0.2 s more.

-
Then run --check claim --variant naive --level repeatable-read --retry. Expected: worker B gets 40001, its retry finds no queued task, and the check prints PASS.

-
Then run --check approval --variant naive --unique-decision. Expected: Bob's INSERT waits, then ends in ERROR 23505, and PASS approval: task 2 has decision(s) ['approve'], state awaiting_approval.

-
Then run --check lease --variant fixed. Expected: the reaper line says requeued [1], worker B claims task 1, worker A's late completion updates 0 row(s), and PASS lease: task 1 is done, owner B.

-
Teaches: each fix changes one statement, at the default level. Each one has a test that fails without it.

-
 E11 (break-it, local). The relay that no isolation level fixes, and at-least-once delivery.

-
Run: uv run python phase03_transactions/taskqueue.py --check outbox --variant naive --relay-level serializable.

-
Then run: uv run python phase03_transactions/taskqueue.py --check outbox --variant fixed --crash-before-mark.

-
Expected: Not run by the author yet. The naive relay at serializable: FAIL outbox: committed events [1, 2], published [2], never published [1]. The fixed relay with the crash: delivered twice: [2], then PASS outbox: committed events [1, 2], published [2, 1, 2], never published [].

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
Expected: Not run by the author yet. The first table shows the holder with Client, ClientRead and {}. The first waiter shows Lock, transactionid and the holder's pid. The two later waiters show Lock and tuple, as in Rogov's page 219. pg_locks shows one row per waiter with granted f and a waited_s value from waitstart. After the holder commits, the remaining waiters show transactionid. The last two lines give the arrival order, the order that got the row, and the RESULT. They may differ, and either result agrees with section 3.4. With --log-lock-waits as a superuser, the server log gets at least one still waiting for line per waiter. A waiter that waits twice, first on the tuple and then on a transaction ID, can write two. Each logged wait gets one acquired line when it ends. As another role, the script says that the settings need a superuser, and exits with 2. With --case multixact, B's INSERT returns with no wait. If the extension can be created, pgrowlocks shows multi t and the two modes Key Share and No Key Update. Expect {"No Key Update","Key Share"}, the reverse of Rogov's order. PostgreSQL 14 sorts the members of a multixact by transaction ID, at multixact.c line 1637, and A got its ID first. That order is inferred from the source.

-
If it fails with LAB ERROR about a wait: another session holds a lock on tq_lw_row. Close other psql sessions on storage_lab.

-
Teaches: the transactionid and tuple waits, waitstart, and the log lines that name them.

-
 E14 (local). A deadlock as a counter and as log lines.

-
Run: psql -h /tmp -p 5432 -d storage_lab -Atc "select deadlocks from pg_stat_database where datname = current_database()", then uv run python phase03_transactions/deadlock.py, then the psql command again.

-
Expected: Not run by the author yet. The second number is one higher than the first. PostgreSQL 14 sends statistics from each backend with a short delay. So if the number did not change, wait a second and read it again. That delay was not checked. Then find the deadlock's ERROR in the server log. There, its DETAIL has one more line per process, Process %d: %s, with each query, from deadlock.c line 1140. If log_lock_waits is on, the victim's log also has a detected deadlock while waiting for ShareLock on transaction line. proc.c line 1516 writes these lines only when log_lock_waits is on.

-
Teaches: a deadlock shows as a counter and as log lines before anyone reports it.

-
 E15 (break-it, local). One open snapshot slows every claim.

-
First predict how many dead row versions 5,000 worked jobs leave while a snapshot is held.

-
Run: uv run python phase03_transactions/queue_horizon.py, then the same with --index pkey.

-
Expected: Not run by the author yet. No times are given, because none were measured. In the baseline, the median claim time stays about flat over its 10 batches. During the hold it grows from batch to batch. n_dead_tup grows by about 2 × 500 = 1,000 per batch. Each job leaves two dead versions: the replaced queued version and the deleted running version. The statistics lag, so that column may trail by a batch. The VACUUM VERBOSE line reports about 2 × 5,000 = 10,000 dead row versions that "cannot be removed yet". Its oldest xmin equals the holder's backend_xmin. After the release and a VACUUM, the median falls back toward the baseline. With --index pkey, expect the same shape. Which index degrades faster was not checked.

-
If it fails with "the queue ran empty": raise --backlog.

-
Teaches: one snapshot held anywhere slows a busy queue, and the VACUUM line names the snapshot.

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

Open the six code-reading checks

-
Check 1. Open phase03_transactions/mvcc_model.py:298, the conflict branch of update(). It raises Blocked while the other writer is still running, and raises 40001 only after that writer has committed. Suppose the two checks were swapped. What would a REPEATABLE READ transaction do when the other writer later rolls back? What does the PostgreSQL 14 docs' text in section 13.2.2 say should happen?

-
Check 2. Open shared/pglab.py:411, the retry loop. In it, COMMIT sits inside the try. Move it outside, after the loop, in your head. Which history of section 3.5 would then end in an error that reaches the caller? Which line of the self-test of pglab.py would fail?

-
Check 3. Open phase03_transactions/taskqueue.py:134, claim_fixed. Replace SKIP LOCKED with NOWAIT, the option of section 3.6 that raises 55P03. Which worker now gets the error, and at which step of the claim check? Is the queue still correct then? Take ten workers and one queued task. How many fail on each poll, and what must each one do next?

-
Check 4. Open phase03_transactions/phantom.py:98, the slot reservation. A task that finishes must give its slot back. Write the UPDATE that does it. Say which transaction it must share, and what goes wrong if it runs in a transaction of its own.

-
Check 5. In any repository you own that uses PostgreSQL, run grep -rn "FOR UPDATE\|isolation\|SERIALIZABLE\|40001\|40P01" <your repo>/. Then find three places that read a value and write based on it. For each one, write its invariant and name the anomaly it can suffer at its level. Then say which check would show it.

-
Check 6. Open phase03_transactions/taskqueue.py:144, the reaper, and SQL["complete"] below it. Suppose complete checked only id = %s AND state = 'running', without the owner. Walk through --check lease --variant fixed with worker A paused, not dead. How many workers would record a result for task 1? Which line of check_lease would then show it?

## Checkpoint: eight questions with answer sketches

Open the checkpoint. Answer each question before you open its sketch
The first three questions are the phase's Test-out. Passing all three, with the lab, lets you skip the phase.

1. Test-out, explain. Use the approvers' case. Explain write skew: what each transaction reads and writes. Explain why snapshot isolation allows it, in terms of first-updater-wins. Then explain what SERIALIZABLE in PostgreSQL does differently. Say which edges it records and which structure it looks for. Say what the client must do when it finds one.

Answer sketchEach approver reads both rows and writes only its own. First-updater-wins fails a transaction only when it changes a row that a concurrent transaction replaced. No row was written twice, so both commit, and the rule breaks with no error. SERIALIZABLE in PostgreSQL also records rw-antidependencies. A rw→ B, because A read Bob's row and B wrote a newer version of it. B rw→ A in the same way. Two rw edges in a row between concurrent transactions are the dangerous structure of Cahill and others, 2008. When A commits, B is a pivot whose out-edge points to a committed transaction, so B fails with 40001. The client must roll back and run B's whole transaction again. The retry counts 1 and stays on call.

2. Test-out, predict. tq_budget holds acme 100 and beta 100, and has no CHECK constraint on credits. The rule is that their sum stays at or above 0. Each transaction reads SELECT sum(credits) over both rows, and if the sum is at least 150, debits 150.(a) T1 debits acme and T2 debits beta, both at REPEATABLE READ, both reading the sum before either writes. Can the rule break, and what are the final balances?(b) Both debit acme with SET credits = credits - 150, at READ COMMITTED. Can the rule break, and does any session wait?(c) Case (b) at REPEATABLE READ.(d) Case (a) at SERIALIZABLE.

Answer sketch(a) Yes, the rule can break. Both read 200 from their snapshots, and each debits a different row. Final: acme −50, beta −50, sum −100. That is write skew, the shape of Berenson's H5. No session waits in this case. (b) Yes, it breaks, and T2 waits. T2's UPDATE waits for T1's row lock. Then it re-checks tenant = 'acme' on the new row, which still matches. It debits again: 100 − 150 − 150 = −200, and the sum is −100. No update is lost, because both debits apply. But T2 decided on a sum that was out of date. (c) T2 waits, then gets 40001 when T1 commits. Its retry reads a sum of −50 + 100 = 50, which is below 150. So it does not debit, and the rule holds. (d) One transaction gets 40001, expected at the second COMMIT. Its retry reads 200 − 150 = 50 and does not debit, and the rule holds.

3. Test-out, demonstrate. Run E4, E5 and E10. Show the lost update and the write skew breaking, and the named mechanism that stops each one. Then show the claim check failing with the naive code at READ COMMITTED and passing with the fix. Explain why the check is deterministic and not a lucky timing.

Answer sketchFrom the runs. Expected shapes are in E4, E5 and E10. Lost update at READ COMMITTED: 160 spent from 100. Stopped by REPEATABLE READ's first-updater-wins, with 40001, or by the atomic UPDATE, with 0 rows. Write skew: 0 on call at REPEATABLE READ, stopped by SSI with 40001 and a retry. The check is deterministic because of the lock-wait probe. The script waits until pg_stat_activity shows the second session waiting, with pg_blocking_pids naming the first. Only then does it commit the first. The order is chosen by the test, not by the timing.

4. A colleague says: "We set default_transaction_isolation to repeatable read, so race conditions are gone." Argue for or against. Which of this phase's failures does that change stop, and which does it leave? What new error must the application now handle, and how?

Answer sketchPartly for it, and mostly against it. REPEATABLE READ stops the lost update: E4 at repeatable read gets 40001 instead of 160 spent. It stops read skew, the report that printed 280. It leaves write skew: 0 approvers on call in E5. It leaves the phantoms: 2 running tasks in E6, and 2 decisions in E10. It also does not fix the outbox relay, which no level fixes. The new error is 40001, which every transaction that writes can now raise. The application needs a retry loop of the whole transaction, with COMMIT inside it. It retries only 40001 and 40P01, with a cap and jitter. Without the loop, each 40001 becomes a failed request. On MySQL InnoDB the same level name would not even stop the lost update, by Hermitage's table.

5. This is broken. A nightly job renews subscriptions. For each customer, it moves credits between that customer's tenants, in the order the billing API returns them. The log shows ERROR: deadlock detected five to ten times a night. Each failed renewal waited about one second. What is the cause, how do you confirm it from the DETAIL lines, and what is the fix? Is raising deadlock_timeout a fix for it?

Answer sketchCause: two renewals lock the same two tenant rows in opposite orders, because the API returns tenants in different orders. The DETAIL lines of each error show the cycle. One says that process P waits for ShareLock on transaction X, blocked by process Q. The next one says the reverse. The CONTEXT line names the row of tq_budget each one wanted. Check log_lock_waits and the server log, where each process's query appears. Fix: lock all of one customer's tenant rows first, in one order, with SELECT ... ORDER BY tenant FOR UPDATE, as deadlock.py --ordered does. Keep a retry for 40P01 as a second defense. Raising deadlock_timeout is not a fix. The cycles stay, and each one holds both renewals for longer before one fails. The one-second wait is the default deadlock_timeout. The server confirms it too. pg_stat_database.deadlocks rises by 5 to 10 a night. With log_lock_waits = on, each victim's log has process %d detected deadlock while waiting for ShareLock on transaction %u after %ld.%03d ms. Suppose the job moves credits with one UPDATE over many tenants. Then the cycle can also sit inside two statements' scan orders, as in section 3.4. The same fix holds: lock the rows first, in key order.

6. Show the arithmetic. (a) An optimistic claim conflicts with probability 0.3 per attempt. How many attempts does it need on average? (b) Twenty workers start together on one hot row, and each round lets one commit. How many attempts do they make in total, and how many does the last one make? (c) In Ports and Grittner's RUBiS run, SSI served 422 requests per second with 0.03% failures. S2PL served 208 requests per second with 0.76%. How many failures per hour is each, and what conditions limit what those numbers say about your server?

Answer sketch(a) 1 / (1 − 0.3) = 1 / 0.7 = 1.43 attempts. (b) 20 × 21 / 2 = 210 attempts for 20 commits. The last worker makes 20 of those attempts. (c) This takes one transaction per request, which the paper does not state. SSI: 422 × 3,600 × 0.0003 = 455.8, about 456 failures per hour. S2PL: 208 × 3,600 × 0.0076 = 5,690.9, about 5,691 per hour. Limits: PostgreSQL 9.1, measured in 2012. One 7,200 RPM disk and a Core 2 Quad Q9550 with 8 GB. The RUBiS bidding mix, 85% read-only. Your rate depends on your transactions' read and write sets. Measure the 40001 rate on your own workload.

7. Given these constraints, design. A reminder service emails about each task that has waited 24 hours in awaiting_approval. It must send exactly one email per task. Three scheduler instances run at once, and any of them can be killed at any moment. Design the claim, the state change, the event, and what the email consumer does. Say what each step costs at READ COMMITTED. Name the check from this phase's lab that you would copy to test it.

Answer sketchHere is one possible design among several. Each scheduler runs a short transaction: UPDATE tq_tasks SET reminder_state = 'claimed' ... WHERE id = (SELECT id FROM tq_tasks WHERE state = 'awaiting_approval' AND <waited 24 hours> AND reminder_state IS NULL ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING id. The same transaction inserts a task.reminder_due event into tq_outbox. Two schedulers never take the same task, and nobody waits. The state change and the event commit together, so a killed scheduler leaves either both or neither. The relay polls unsent rows with SKIP LOCKED and marks them sent, so a late commit is not skipped. It delivers at least once, so the email consumer keeps the event ids it has handled and drops a repeat. At READ COMMITTED this costs no retries and no long locks. The email itself happens outside any transaction. Exactly one email then needs one more step. The consumer records the id before it sends, or the email provider accepts an idempotency key. That last part is outside the database and needs its own check. Tests to copy: the claim check and the outbox check with --crash-before-mark from taskqueue.py. reminder_state is a new column this design adds. It is an example, not part of the lab schema. Two more tools fit. A partial unique index, CREATE UNIQUE INDEX ON tq_outbox (task_id) WHERE event_type = 'task.reminder_due', makes one reminder event per task a rule that later code cannot break. If only one scheduler may work at a time, each can start with pg_advisory_xact_lock(hashtext('reminders')). The claim needs no lease here, because the state change and the event commit together, and no slow work happens in between.

8. This is broken. These numbers are an example. The task queue's claim p99 rose from 2 ms to 300 ms over two hours. The queued count grew from 200 to 9,000. Database CPU is up, and nothing was deployed. pg_stat_activity shows one session idle in transaction, with xact_start two hours ago. What is the cause? How do you confirm it with one query and one VACUUM line? What do you change so it cannot recur? At 50 claims per second, how many dead row versions has the queue table gained in those two hours, at two per job?

Answer sketchCause: the idle transaction holds the cleanup horizon two hours in the past. VACUUM cannot remove the queue's dead versions. So every claim's index scan steps over more of them, as in Brandur Leach's 2015 measurements. Claims get slower than jobs arrive, so the queue grows. Confirm: SELECT pid, age(backend_xmin), state, now() - xact_start FROM pg_stat_activity ORDER BY 2 DESC puts that session first. VACUUM VERBOSE tq_tasks reports many dead row versions that "cannot be removed yet", with an oldest xmin equal to that backend_xmin. Fix now: end the session with pg_terminate_backend(pid), then let VACUUM run. Prevent it in three ways. Set idle_in_transaction_session_timeout per role, and add transaction_timeout on PostgreSQL 17 and later. Keep the partial index on queued rows. Alert on age(backend_xmin), as Phase 4, section 4.5, does. Arithmetic: 50 × 7,200 seconds = 360,000 jobs, and 2 × 360,000 = 720,000 dead row versions.

## Cheatsheet

Open the one-screen cheatsheet
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

## Sources

Open the sources, with what to read in each
This course's research fetched the papers, analyses and outbox sources below on 2026-10-17. For this phase, more pages were fetched on 2026-10-18. They are the PostgreSQL 14 docs beyond chapter 13, more source files at REL_14_24, and the psycopg docs. Every URL was checked again with check_urls.py when this phase was written. Primary sources come first in each group.

### The original papers

- A Critique of ANSI SQL Isolation Levels, Berenson, Bernstein, Gray, Melton, E. O'Neil and P. O'Neil, ACM SIGMOD 1995. Focus on: sections 2.2 and 3 for P0 to P3, and section 4.1 for P4 and history H4. Section 4.2 has snapshot isolation, A5A, A5B, history H5, the 8-hour example and Remark 9. Table 4 is on page 10. It takes about 45 minutes. This is the arXiv copy of MSR-TR-95-51. Its extracted text has broken spacing, so copy formulas from the PDF pages. Read it before you run E4.
- Serializable Isolation for Snapshot Databases, Cahill, Röhm and Fekete, ACM SIGMOD 2008. Focus on: section 1, Example 1 and Figure 1, the doctors on duty. It is the origin of this phase's opening case. Section 2.2 for the dangerous structure and the pivot. Section 5 measures the first SSI, in Berkeley DB 4.6.21 with page-level locks, on 2008 hardware. So do not compare its numbers with PostgreSQL's. A course mirror of the paper.
- Serializable Snapshot Isolation in PostgreSQL, Ports and Grittner, PVLDB 5(12), VLDB 2012. Focus on: section 2.1 for the doctors example in PostgreSQL's terms. Sections 4 and 5.2 for SIREAD locks and safe snapshots, and 5.4 for which transaction to cancel. Section 8 for every number in section 3.5, on PostgreSQL 9.1 and the paper's 2012 hardware. The paper also notes some history. For years the docs did not say that the old SERIALIZABLE mode was not truly serializable. It takes about 70 minutes, and is best read before E5.
- Generalized Isolation Level Definitions, Adya, Liskov and O'Neil, IEEE ICDE 2000. Focus on: section 5, the phenomena G0 to G2 and G2-item. Jepsen and Hermitage use these names. A Wayback copy, because the original host refused connections.
- Weak Consistency: A Generalized Theory and Optimistic Implementations for Distributed Transactions, Atul Adya, MIT PhD thesis, 1999. Focus on: section 4.1 for G-single, the read skew of Hermitage, and section 4.3 for the definition of snapshot isolation. Read only those two sections, because the rest goes far beyond this phase.

### Books and lectures

- PostgreSQL 14 Internals, Egor Rogov, Postgres Professional, 2022 to 2023, free PDF. Focus on: section 2.3, pages 47 to 60, for the READ COMMITTED re-check, the read-only anomaly and DEFERRABLE. Section 3.7, pages 76 to 79, for subtransactions and the aborted state. Chapter 13, pages 211 to 230, for the tuple-lock queue, multixacts, SKIP LOCKED and deadlocks inside two UPDATEs. Every output in these pages was printed on PostgreSQL 14, the version you run. The book's home page is https://postgrespro.com/community/books/internals.
- CMU 15-445/645 Database Systems, Fall 2025, lecture 18 notes, Two-Phase Locking. Focus on: deadlock detection against prevention, wait-die and wound-wait. It takes about 20 minutes.
- CMU 15-445/645, Fall 2025, lecture 20 slides, Multi-Version Concurrency Control. Focus on: version storage, append-only against delta, and slide 33, the table of engines.

### Production reports

- ACIDRain: Concurrency-Related Attacks on Database-Backed Web Applications, Warszawski and Bailis, SIGMOD 2017. Focus on: the introduction, for the 22 attacks, the 17 that come from transaction scope, and Flexcoin. Then section 2, which separates level-based and scope-based anomalies.
- Postgres Job Queues & Failure By MVCC, Brandur Leach, 2015-05-18. Focus on: "Slow lock time" and "Dead tuples", for the lock time and the 100,000 dead rows, and the VACUUM VERBOSE output. Heroku Postgres, the Que library with advisory locks, about 50 jobs a second. No SKIP LOCKED.
- Why we spent the last month eliminating PostgreSQL subtransactions, GitLab, 2021-09-29. Focus on: "What is SubtransControlLock?" and "Reproducing the problem with replicas", for the drop from about 360,000 to 50,000 transactions per second. Replicas only, with a long transaction on the primary.
- How Postgres sequences issues can impact your messaging guarantees, Oskar Dudycz, 2022-10-28. Focus on: the xid8 column and pg_snapshot_xmin(pg_current_snapshot()), and the final query that orders by transaction ID. A design post, with no measurements.
- pgsql-bugs #12990, multixact member files, PostgreSQL 9.3.5, 2015. Focus on: the workload of SELECT ... FOR SHARE from 26 connections, and the table of members files over one day. An old version, so read it for the mechanism only.
- Optimizing database connection loads with PgBouncer and Testwick, Mattermost, 2022-01-11. https://mattermost.com/blog/optimizing-database-connection-loads-with-pgbouncer-and-testwick/ Focus on: the part on migrations, where a session-level advisory lock could not be released through PgBouncer in transaction mode.
- Fun with Multiversion Concurrency Control, Precision Nutrition, 2020, with part 2. Part 1: https://tech.precisionnutrition.com/postgres/databases/2020/03/06/fun-with-mvcc Part 2: https://tech.precisionnutrition.com/postgres/databases/2020/05/15/fun-with-mvcc-2 Focus on: events 187 and 188 that a reader passed, and the rejected fixes in part 1. Then the counter row of part 2, which gives no numbers.

### PostgreSQL 14 documentation

- 13.2 Transaction Isolation. Focus on: Table 13.1, and the rule for an UPDATE after a wait at READ COMMITTED. Then the 40001 at REPEATABLE READ, and the advice list for SERIALIZABLE. The most important page of this phase.
- 13.1 Introduction to concurrency control. Focus on: the sentence on reading and writing never blocking each other.
- 13.3 Explicit Locking. Focus on: 13.3.1 table-level locks, Table 13.3 for row locks, 13.3.4 Deadlocks, and 13.3.5 Advisory Locks with its three warnings.
- 9.27.10 Advisory Lock Functions. Focus on: Table 9.98, the xact and try forms.
- 52.74 pg_locks. Focus on: waitstart, new in version 14, and the locktype values transactionid and tuple.
- 11.8 Partial Indexes. Focus on: Example 11.3, the partial unique index.
- INSERT. Focus on: the ON CONFLICT clause, and the sentence on the atomic outcome.
- 25.1.5.1 Multixacts and Wraparound. Focus on: the 10GB and 20GB limits of the member storage.
- 27.4 Hot Standby. Focus on: the sentence that serializable is not available on a standby.
- 43.6.8 Trapping Errors. Focus on: the tip on the cost of a block with EXCEPTION.
- SAVEPOINT. Focus on: the examples of rolling back to a savepoint.
- 13.5 Serialization Failure Handling, current version 18. Focus on: which SQLSTATEs to retry, and why the server does not retry for you. The page does not exist in the PostgreSQL 14 docs. The research found it in the version 15 docs.
- 20.12 Lock Management. Focus on: deadlock_timeout and the three max_pred_locks_* settings.
- 20.11 Client Connection Defaults. Focus on: default_transaction_isolation, statement_timeout, lock_timeout, idle_in_transaction_session_timeout and idle_session_timeout.
- 19.11 Client Connection Defaults, current version 18. Focus on: transaction_timeout, new in version 17.
- 19.4 Resource Consumption, current version 18. Focus on: subtransaction_buffers, new in version 17.
- 20.8 Error Reporting and Logging. Focus on: log_lock_waits.
- 5.5 System Columns. Focus on: xmin, xmax and ctid.
- 70.6 Database Page Layout. Focus on: Table 70.4, the row version header, with t_xmin, t_xmax and t_ctid.
- 9.26 System Information Functions. Focus on: Table 9.77, the snapshot components, and pg_xact_status, pg_current_snapshot and pg_blocking_pids.
- SELECT, The Locking Clause. Focus on: NOWAIT and SKIP LOCKED, and the warning on the inconsistent view.
- SET TRANSACTION. Focus on: DEFERRABLE.
- 28.2 The Statistics Collector. Focus on: Table 28.4, wait event types, and the idle in transaction state. Table 28.11 for the transactionid and tuple waits, Table 28.12 for SubtransSLRU, and 28.2.13 for pg_stat_database.deadlocks.
- 5.4 Constraints. Focus on: the note that CHECK constraints see only the row being checked.
- CREATE SEQUENCE. Focus on: the note that nextval is never rolled back, which is why outbox ids arrive out of commit order.
- 3.4 Transactions, tutorial. Focus on: the all-or-nothing paragraph. It takes two minutes.
- 70.1 Database File Layout. Focus on: the pg_xact row.
- Appendix A, Error Codes. Focus on: class 40, Transaction Rollback.
- PostgreSQL 12.4 release notes, 2020-08-13. Focus on: "Fix conflict-checking anomalies in SERIALIZABLE isolation mode".

### PostgreSQL source, tag REL_14_24

- heapam_visibility.c. Focus on: HeapTupleSatisfiesMVCC from line 937, the visibility rule of section 3.2.
- snapshot.h. Focus on: lines 157 to 169, the snapshot fields.
- nodeModifyTable.c. Focus on: line 2006 in ExecUpdate, the 40001 of first-updater-wins.
- predicate.c. Focus on: lines 4125 to 4127 for the message and hint, and the reason codes around lines 4821 and 4880.
- lmgr README. Focus on: lines 340 to 360, the timer. Lines 518 to 524, soft cycles. Lines 553 to 555, the victim.
- README-SSI. Focus on: the overview of SSI in PostgreSQL by its authors. Read it after Ports and Grittner, for the details the paper leaves out.
- deadlock.c. Focus on: DeadLockReport, lines 1089 to 1153.
- lmgr.c. Focus on: XactLockTableInsert at lines 585 to 600, the wait at line 668, and the context text at line 831.
- postgres.c. Focus on: line 1046, the 25P02 message, and IsTransactionExitStmt at lines 2752 to 2765.
- executor README. Focus on: "EvalPlanQual (READ COMMITTED Update Checking)", lines 311 to 345.
- README.tuplock. Focus on: lines 14 to 37, the tuple lock and the steps of a row wait.
- proc.c. Focus on: lines 1516 to 1631, the log_lock_waits lines.
- nbtinsert.c. Focus on: line 224, the wait of a unique insert, line 636, the SSI check, and line 665, the 23505 message.
- proc.h and subtrans.h. Focus on: PGPROC_MAX_CACHED_SUBXIDS at line 36. NUM_SUBTRANS_BUFFERS is at line 15 of https://github.com/postgres/postgres/blob/REL_14_24/src/include/access/subtrans.h
- snapmgr.c. Focus on: XidInMVCCSnapshot from line 2259, and the suboverflowed branch.
- vacuumlazy.c. Focus on: line 1656, the "cannot be removed yet" line with its oldest xmin.
- Commit e620a38c, "Avoid update conflict out serialization anomalies.", 2020-06-11. Focus on: the commit message, with "Reported-By: Kyle Kingsbury", and the new isolation test update-conflict-out.spec.

### Independent analyses and test suites

- Jepsen: PostgreSQL 12.3, Kyle Kingsbury, 2020-06-12. Focus on: section 3.1 for repeatable read as snapshot isolation, section 3.2 for G2-item under serializable, and section 4. Read it after E5, in about 25 minutes.
- Jepsen: Amazon RDS for PostgreSQL 17.4, Kyle Kingsbury, 2025-04-29, updated 2025-05-03. Focus on: section 1, the update on the cause, and section 4 for the Long Fork cycle. Section 5 gives the advice to use the writer endpoint. Multi-AZ clusters, no faults injected, every version from 13.15 to 17.4. With about 150 write and 1,600 read-only transactions per second, cycles appeared "every few minutes". Jepsen did not observe the cycle in standard PostgreSQL at REPEATABLE READ.
- Understanding transaction visibility in PostgreSQL clusters with read replicas, Sergey Melnik, AWS Database Blog, 2025-05-02. Focus on: "Understanding the Long Fork behavior", the ProcArray and the WAL order. Then the proposed fix with commit sequence numbers. AWS's position, read beside Jepsen's. AWS says "the visibility order of transactions doesn't always match their logged commit order", and that it "affects all isolation levels". The order differs "between the primary and replicas in cluster configurations". The issue "isn't present in Single-AZ PostgreSQL deployments". Both posts can be true, because they describe different setups. That reading is inferred, and a test with one self-managed replica would confirm it.
- Hermitage, Martin Kleppmann. Focus on: the README table, and postgres.md. It has two-session psql scripts for "Lost Update (P4)", "Write Skew (G2-item)" and "Anti-Dependency Cycles (G2)". Run on PostgreSQL 9.3.5. You can paste the scripts into two psql windows.
- Hermitage: Testing the "I" in ACID, Martin Kleppmann, 2014-11-25. Focus on: why the level names of different databases do not match. It takes ten minutes.

### The transactional outbox

- Pattern: Transactional outbox, Chris Richardson, microservices.io. Focus on: the solution, the at-least-once note, and the two relay patterns, log tailing and polling. The page has no date.
- Outbox Event Router, Debezium 3.7 documentation. Focus on: the default table columns, and the rule that only INSERTs are expected. Then the event id header for removing duplicates. The page gives no numbers.
- Transactional outbox pattern, SeatGeek Data Platform team, 2025-02-07. Focus on: pg_logical_emit_message() in place of an outbox table, and Debezium heartbeats. It reports a load test without numbers.
- Capturing every change from Shopify's sharded monolith, John Martin and Adam Bellemare, Shopify, 2021-03-12. Focus on: the p99 and the throughput of a log-reading relay. It is change data capture of MySQL, not an outbox on PostgreSQL.

### The client library

- psycopg 3, Errors. Focus on: SerializationFailure, DeadlockDetected, Error.sqlstate and the Diagnostic fields the labs print.
- psycopg 3, Transactions management. Focus on: autocommit and how the labs send BEGIN and COMMIT themselves.

### A talk

- Transactions: myths, surprises and opportunities, Martin Kleppmann, Strange Loop 2015. Focus on: read skew at 0:15:00, write skew with an on-call example at 0:18:40, two-phase locking at 0:21:53, and serializable snapshot isolation at 0:25:45. The times come from YouTube's chapter marks and its machine captions, correct to about 10 seconds. The captions are not his exact words, so do not quote them.
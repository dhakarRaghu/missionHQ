# Course 5 — Distributed systems and verification
slug: elite-distributed
order: 5
source: local
language: Go for the replicated-store lab; a small model in TLA+ or P in phase 6

## Why this course

This is the subject he named as a priority and the one his catalogue had
nothing on. It is cumulative — every phase depends on the one before — which
is why it is a course and not a set of articles. It builds on course 4: a
replica is a second copy of a write path whose guarantees you already
understand, and the question becomes what the two copies can promise
together.

The last phase is verification, because in this subject tests that pass
prove very little. The teams that get this right record histories and check
them, model the protocol before implementing it, and replay failures from a
seed. That is the standard here.

Consensus is taught as a user, not an implementer: what Raft guarantees, what
it does not, and how to use etcd correctly. Implementing Raft is a fine
project and not a required one.

## What you will be able to do

State a system's guarantees precisely and record the histories that test
them. Make delivery correct at the edges — retries, duplicates, reordering.
Add a replica to the course-4 store, kill the primary mid-write, and count
what was lost. Add fencing so a paused process cannot write. Use a checker
and a small model to find the bug before production does.

---

## Phase 1 — Models, guarantees and histories
question: When you say a system is "consistent", which of the seven things that word can mean do you mean, and how would you test it?
minutes: 150
assumes: durability boundary on one node (4.1), isolation levels (4.3)
introduces: partial failure, slow vs failed, safety vs liveness, availability assumptions, consistency models (linearizability, sequential, causal, read-your-writes, monotonic reads, eventual), operation histories, stating guarantees precisely
leaves-for-later: how replicas produce these guarantees (5.3), the checker (5.6)

### Why you're here
A team says their cache is "eventually consistent" and their database is "strongly consistent", and neither statement is precise enough to design against. A customer reads their own write and does not see it; the team says that is expected. Then a different customer sees a value that was never written — the interleaving of two updates — and the team cannot say whether that is a bug, because they never wrote down what the system promises.

Distributed correctness begins with a sentence: this system guarantees X under assumptions Y. This phase is learning to write that sentence and record the evidence for it.

### Sections
1.1 — Partial failure: the property that makes distributed systems different, and why a single-node intuition fails
1.2 — Slow versus failed: why you cannot tell them apart, and what every protocol does about it
1.3 — Safety and liveness: "nothing bad happens" versus "something good eventually happens", and which one you sacrifice under partition
1.4 — The consistency models, laid out as a ladder: what each one allows that the stronger one forbids
1.5 — Linearizability: the one most people mean by "strong", precisely, with a history that violates it
1.6 — Session guarantees: read-your-writes and monotonic reads — the ones users actually notice
1.7 — Histories: recording every operation with its invocation and response time, and what a checker needs from them
1.8 — Writing the guarantee: the sentence, its assumptions, and the test that would falsify it

### Lab
Write the guarantee sentence for Mission HQ's event log and its projections. Instrument one path to record operation histories. Construct by hand one history that the guarantee forbids, then run 10,000 operations under a scripted schedule and check that it never appears — or find that it does.

### Demonstrate
A precise guarantee for one Mission HQ component, a recorded history from real operations, and one forbidden history not produced across a stated number of operations under a scripted schedule (or a bug filed because it was).

### Test out
- Explain: linearizability versus sequential consistency versus causal, with a history that separates each pair.
- Predict: for a described replication setup, which model it actually provides and which session guarantee it breaks.
- Demonstrate: the recorded history and the guarantee sentence.

---

## Phase 2 — Delivery and distributed workflows
question: A message was sent, the acknowledgement was lost, and the sender retried. What did the receiver see — and where exactly does "exactly once" live?
minutes: 150
assumes: idempotent tool execution in one process (2.3), transactions and the outbox (4.3)
introduces: at-most-once and at-least-once, idempotency keys and where they are committed, deduplication boundaries, transactional outbox and inbox, sagas and compensation, ordering guarantees, why exactly-once moves the boundary rather than removing duplicates
leaves-for-later: replication of the log itself (5.3)

### Why you're here
He has built an outbox and idempotency keys. This phase is the edges: the key committed after the side effect, the dedup table that was cleaned up too early, the consumer that processed a message and crashed before committing its offset, the saga whose compensation itself failed. Every one of these is a case where the basic pattern was present and the boundary was one step off.

Exactly-once is not a feature a broker gives you. It is a boundary you choose, and everything outside it is at-least-once.

### Sections
2.1 — The three deliveries: at-most-once, at-least-once, and the one that does not exist end to end
2.2 — Idempotency keys: what they key on, where they are committed relative to the side effect, and how long they live
2.3 — Deduplication boundaries: the receiver's dedup table, its retention, and the duplicate that arrives after cleanup
2.4 — The transactional outbox and inbox: same transaction as the state change, the relay, and its failure modes
2.5 — Consumer commit order: process-then-commit versus commit-then-process, and the duplicate or loss each produces
2.6 — Sagas: compensation, the compensation that fails, and reconciliation as the last line
2.7 — Ordering: per-key ordering, what a retry does to it, and the reorder that breaks a state machine
2.8 — Moving the boundary: where exactly-once can be made true (inside one transaction) and where it cannot (an email, a payment, a webhook)

### Lab
Take Mission HQ's outbox and one consumer. Inject: a lost ack, a duplicate delivery, a reorder, a crash between process and commit, a dedup-table cleanup during a retry. For each, show what the receiver observed. Fix the boundary. Add a reconciliation job that finds what slipped through.

### Demonstrate
Every injected delivery failure with its observed effect before and after the fix, and a reconciliation that catches the one case the boundary cannot cover, with the boundary stated in one sentence.

### Test out
- Explain: why exactly-once cannot be true for an external side effect, and what "moving the boundary" means.
- Predict: for a described commit order and crash point, whether the result is a duplicate, a loss, or neither.
- Demonstrate: the injected-failure matrix.

---

## Phase 3 — Replication and partitioning
question: The primary died with ten writes acknowledged and not yet replicated. Who has them now, what does the new primary serve, and what does the client believe?
minutes: 180
assumes: the write path (4.1), guarantees and histories (5.1), delivery (5.2)
introduces: synchronous vs asynchronous replication, replication lag and its measurement, read-your-writes across replicas, failover and what it loses, quorum reasoning, consistent hashing, hot keys, rebalancing live data
leaves-for-later: leases and fencing for the new primary (5.4), consensus for choosing it (5.5)

### Why you're here
The replica's lag counter read zero for the whole outage — because when the network broke, nothing was arriving, and "nothing behind" and "nothing coming" are the same number. Failover promoted it. Ten acknowledged writes on the old primary were gone. The customers who made them had receipts. Later, one partition became hot enough to pin a node at 100% while the others idled, and rebalancing it moved data through the same overloaded node.

Replication is where course 4's durability boundary meets course 5's partial failure. This phase counts what is lost, and then makes it fewer.

### Sections
3.1 — Sync and async replication: who waits for whom, what each acknowledges, and who pays the latency
3.2 — Measuring lag honestly: what the lag counter measures, the zero that means "nothing arriving", and the write-then-read probe
3.3 — Read-your-writes across replicas: session tokens, sticky reads, and the customer who sees their comment disappear
3.4 — Failover: promotion, the acknowledged writes the old primary had, and what the new primary serves in their place
3.5 — Quorums: reads plus writes greater than replicas — what it guarantees, and the cases it does not (sloppy quorums, hinted handoff)
3.6 — Partitioning: hashing, ranges, consistent hashing and virtual nodes
3.7 — Hot keys: finding them, splitting them, and the write pattern that defeats hashing
3.8 — Rebalancing live: moving a partition without stopping writes, and the double-write window

### Lab
Give the course-4 KV store a replica: ship the log to a second process. Expose a lag counter and a write-then-read probe. Kill the primary mid-stream and count the acknowledged writes that were lost. Add a sync mode and count again. Then partition keys across two primaries, create a hot key, and rebalance it while writes continue.

### Demonstrate
Lost-write counts for async and sync replication after a primary kill, the lag counter reading zero during a partition shown next to the probe that reports the real delay, and a live rebalance with the double-write window measured.

### Test out
- Explain: what a lag counter of zero can mean, and how a probe distinguishes the cases.
- Predict: for a described replication mode and crash, how many acknowledged writes are at risk and who will notice first.
- Demonstrate: the replicated store with its measured losses.

---

## Phase 4 — Time, failure detection, leases and fencing
question: A process holding a lock was paused for 30 seconds, the lock expired, another process took it, and then the first one woke up and wrote. What stops it?
minutes: 150
assumes: slow vs failed (5.1), failover (5.3)
introduces: clock assumptions and skew, timeouts as suspicion, failure detectors (heartbeats, phi-accrual), leases, stale owners, fencing tokens, split-brain prevention, monotonic vs wall-clock time
leaves-for-later: leader election by consensus (5.5)

### Why you're here
A garbage-collection pause, a VM migration, a swap storm: a process stops for longer than its lease and does not know it. When it resumes, it still believes it is the owner. Every distributed lock built on a timeout has this hole, and the standard fix — a fencing token checked by the resource — is the thing most implementations leave out. The same shape appears in leader election, in job schedulers, and in the "exactly one worker" assumption Mission HQ's task runner makes.

You cannot prevent the pause. You can make the resource refuse the stale writer.

### Sections
4.1 — Time in a distributed system: wall clocks, monotonic clocks, skew, and the assumption every timeout makes
4.2 — Timeouts as suspicion: why a timeout is evidence and not proof, and the cost of each kind of mistake
4.3 — Failure detectors: heartbeats, fixed timeouts, phi-accrual — and adapting to a network that changes
4.4 — Leases: ownership with an expiry, renewal, and the window between expiry and the owner noticing
4.5 — The stale owner: the pause that outlives the lease, with the timeline
4.6 — Fencing tokens: a monotonic number the resource checks, and why the check must live at the resource
4.7 — Split-brain: two owners at once, how it happens after a partition heals, and the mechanisms that prevent it
4.8 — Leases in Mission HQ: the task claim, the single worker assumption, and where a fencing token belongs

### Lab
Build a lease-protected worker over the replicated store. Inject a pause longer than the lease (SIGSTOP), a partition, and a crash. Record the history. Show the stale write landing. Add a fencing token checked by the store. Show it refused.

### Demonstrate
A recorded history with a stale write before fencing and none after, under injected pause, partition and crash — plus the fencing token placed in Mission HQ's task claim, with a test.

### Test out
- Explain: why a lease alone cannot prevent a stale write, and where the fencing check must live.
- Predict: for a described pause length, lease length and renewal interval, whether a stale write is possible and when.
- Demonstrate: the lease-protected worker with its history.

---

## Phase 5 — Consensus as a user
question: How do five machines agree on one value when any two can fail, what exactly does that buy you, and what does it not?
minutes: 120
assumes: quorums (5.3), leases and fencing (5.4), guarantees and histories (5.1)
introduces: leader election, replicated log, commit index, Raft's safety guarantees, quorum intersection, membership change, what consensus does not solve, using a consensus store (etcd) correctly
leaves-for-later: verifying any of it (5.6)

### Why you're here
The team's replicated log passed every test, including the ones with random failures. In production, after a membership change during a partition, two nodes each believed they were leader for four minutes. The bug was in the configuration-change protocol — the one part of consensus where the guarantee nearly breaks — and no amount of random testing had reached it.

Consensus is the one part of this subject where reading the proof matters more than reading the code. This phase reads it as a user: what is guaranteed, under what assumptions, and how to hold a consensus store correctly.

### Sections
5.1 — What consensus is for: choosing one value or one leader, and the problems that do not need it
5.2 — Raft as a user reads it: leader election, the replicated log, commit, and the safety properties it guarantees
5.3 — Quorum intersection: the one idea that makes the guarantees hold, and membership change — where it nearly breaks
5.4 — What consensus does not give you: throughput, latency, or exactly-once — and using etcd correctly for leases, locks and configuration

### Lab
Run a three-node etcd. Take a lease and a lock through it for the phase-4 worker. Partition the leader. Record what the worker observed, what etcd guaranteed, and where the two differ. Then perform a membership change during a partition and record whether the guarantee held.

### Demonstrate
A recorded run of the worker against etcd through a leader partition and a membership change, with each observation matched to the guarantee that explains it.

### Test out
- Explain: Raft's safety guarantees and why quorum intersection is what makes them hold.
- Predict: for a described membership change during a partition, whether two leaders are possible.
- Demonstrate: the etcd run with observations matched to guarantees.

---

## Phase 6 — Verification
question: Your distributed store passed every test. How do you find out whether it is actually correct, before production does?
minutes: 180
assumes: histories (5.1), the replicated store and fencing (5.3, 5.4), consensus guarantees (5.5), deterministic and property-based tests on one process (1.4)
introduces: history checking with a linearizability checker, state-machine testing and shrinking, a small formal model in TLA+ or P, deterministic simulation with a controllable clock, fault replay from a seed
leaves-for-later: nothing — this is the end of the course

### Why you're here
A modelling effort at a large cloud provider found a bug in a replication protocol from the model, before the code was written — a bug the tests would not have reached. Their published practice is now a stack: model check the protocol, property-test the implementation, inject faults, and run the whole cluster in a deterministic simulator so any failure can be replayed from a seed. The most reliable storage systems written this decade were built that way.

None of this is exotic any more. This phase builds the small version of that stack on the store you already have.

### Sections
6.1 — History checking: feeding recorded operations to a linearizability checker, and reading its counterexample
6.2 — State-machine and property-based testing: generating operations, shrinking a failing sequence to its smallest form
6.3 — A small formal model: modelling the fencing protocol from phase 4 in TLA+ or P, and letting the model checker find the missing token
6.4 — Deterministic simulation: a controllable clock, scripted faults, and reproducing a failure from a seed

### Lab
Model the phase-4 lease-and-fencing protocol in TLA+ or P. Show the model checker find the stale write when the fencing token is removed, and pass when it is present. Run the replicated store under a deterministic fault schedule with a linearizability checker on its history. Reproduce one failure from its seed.

### Demonstrate
A model that finds the missing-fencing bug, a checked history of the replicated store under scheduled faults, and one failure reproduced from a saved seed — plus a one-page statement of what the store guarantees and the evidence for each claim.

### Test out
- Explain: what a linearizability checker needs from a history, and what a model checker can find that tests cannot.
- Predict: for a described protocol change, whether the model or the checker would catch the resulting bug first, and why.
- Demonstrate: the model, the checker output, and the seed replay.

---

## Integrated lab for the course

The course-4 store, replicated, with acknowledged-write losses counted under primary kill, lease-protected with fencing, checked by a linearizability checker under a deterministic fault schedule, modelled in TLA+ or P for the fencing protocol, and every failure reproducible from a seed. Write the guarantee sheet: each claim, its assumptions, and the artefact that proves it.

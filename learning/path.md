# The path

Not a reading list. A **bar** and a **direction**: what a good article looks
like for me, and which subject to steer at right now. The system goes and
finds articles that clear the bar, every day, from anywhere.

**My file.** Change the bar, reorder the subjects, mark one `[done]`.

---

## The bar — what makes an article worth my hour

I read all 111 essays on arpitbhayani.me and kept 24. The judgement that
produced that ratio is the bar, and it applies to every source, not just his.

**The best article of all** is a real incident: something broke in
production, someone diagnosed it under pressure, they fixed it, and they say
what they changed so it could not happen again. That shape teaches more per
hour than any explainer, because the failure already happened and the price
was already paid by someone else. When one exists for the current subject, it
wins.

What makes an incident writeup worth reading: the symptom as it first
appeared (not as it was later understood), the wrong theory they chased
first, the signal that actually located it, the fix, and the change that
outlived the incident.

**Keep it when:**

- It explains a **mechanism** — how the thing actually works underneath, not
  what it is called.
- It has **numbers**: latency figures, memory math, benchmark results, cost
  per million tokens, real production timeout values I can copy.
- It shows **real code or config** that would run, including the hard part.
- It names a **failure mode** — what breaks, at what scale, and why.
- It is **specific enough to change something I build this month**.

**Cut it when:**

- It is **definitional and short** — names four things, explains none, stops
  where the subject gets interesting. (All four ACID posts went this way.)
- It **restates vendor documentation** that is better and more current.
- It is **opinion with no mechanism** — names a real problem, offers nothing
  to implement or measure.
- It **repeats something I already read** with different examples.
- It is a **listicle, a launch post, or a tutorial introduction** to something
  I already do.

**Prefer the mechanism over the product.** A deep post about one tool counts
only when the mechanism generalises, and the lesson must teach the mechanism
with the tool as the example. I am not learning vLLM. I am learning how
inference serving works, and vLLM is one implementation of it. The same goes
for MySQL, Postgres, Kafka and the rest.

**The one test:** would I change something in how I build, or understand
something I did not understand this morning? If no, it does not qualify,
however well written it is.

---

## The direction — subjects, in this order

Steer here. When one is genuinely covered, mark it `[done]` and the next
becomes current.

### 1. AI systems ← current

Topics, in order. One topic per day. Mark `[done]` when I have it.

1. **How inference actually works** — prefill and decode, the KV cache, why
   batching changes everything, where the time and money go.
2. **Retrieval that works** — embeddings, chunking, hybrid search, reranking,
   and how to tell that retrieval is what is broken.
3. **Evaluating an LLM system** — golden sets, judges and their biases,
   catching regressions before shipping.
4. **Agents in production** — tool calls, retries and idempotency, partial
   failure, approval boundaries, what to log.
5. **Cost and latency** — caching, routing, quantization, budgets per request.
6. **How AI systems fail in production** — real incidents from teams running
   them.

**Build:** a hybrid retrieval pipeline — BM25 plus embeddings, fused with
reciprocal rank fusion, then a reranker. Write the judge harness *before*
tuning anything, or you are guessing at whether changes helped.

### 2. Backend depth

1. **Storage engines and the write path** — append-only logs, compaction,
   what a crash costs.
2. **Query execution** — joins, indexes, what the planner is actually doing.
3. **Caching and eviction** — why LRU collapses, what replaced it.
4. **Concurrency and locking** — deadlocks, isolation, contention.
5. **Queues and rate limiting** — backpressure, shedding, fairness.

**Build:** a Bitcask-style KV store. Append-only file, in-memory hash of key
to offset, compaction. About 200 lines. Then kill it mid-write and prove
recovery works.

### 3. Distributed systems

1. **Replication and lag** — sync, async, and who pays for each.
2. **Consistency models** — what each one actually promises.
3. **Consensus** — what Raft and Paxos guarantee, and what they do not.
4. **Partitioning and rebalancing** — splitting data, moving it while live.
5. **Failover** — detection, promotion, and what gets lost.

**Build:** give that store a replica. Ship the log to a second process,
expose a lag counter, kill the primary mid-stream and count the writes lost.

### 4. Failure and algorithms

1. **Detecting failure** — heartbeats, timeouts, phi-accrual.
2. **Clocks and ordering** — why time is not a number you can trust.
3. **Probabilistic structures** — Bloom filters and friends, in real systems.
4. **Anomaly detection** — finding the bad one without labelling everything.

**Build:** heartbeats between the two nodes, then swap the fixed timeout for
a phi-accrual detector and watch it adapt. Implement a Bloom filter and plot
measured false-positive rate against the memory given.

---

## Exemplars — articles that cleared the bar

Reference, not a queue. Read one if it is the best thing available for the
current subject, or use them to calibrate what "good" means. Something newer
or better on the same subject should win.

**AI systems**
[How LLM Inference Works](https://arpitbhayani.me/blogs/how-llm-inference-works) ·
[Embedding Models Make Or Break Your AI App](https://arpitbhayani.me/blogs/embedding-models-make-or-break-your-ai-app) ·
[BM25](https://arpitbhayani.me/blogs/bm25) ·
[What Matters in Production RAG](https://arpitbhayani.me/blogs/rag-production) ·
[G-Eval, Explained](https://arpitbhayani.me/blogs/g-eval) *(read 2026-09-12)* ·
[Databases Were Not Designed For This](https://arpitbhayani.me/blogs/defensive-databases) ·
[The Curse of Dimensionality](https://arpitbhayani.me/blogs/curse-of-dimensionality)

**Backend depth**
[Why Do Databases Deadlock](https://arpitbhayani.me/blogs/database-deadlocks) ·
[JOIN Algorithms](https://arpitbhayani.me/blogs/join-algorithms) ·
[Sliding Window Rate Limiting](https://arpitbhayani.me/blogs/sliding-window-ratelimiter) ·
[Cache Locality](https://arpitbhayani.me/blogs/cpu-cache-locality) ·
[Bitcask](https://arpitbhayani.me/blogs/bitcask) ·
[The 2Q Algorithm](https://arpitbhayani.me/blogs/2q-cache) ·
[When You Increase Kafka Partitions](https://arpitbhayani.me/blogs/kafka-partitions)

**Distributed systems**
[Replication Strategies](https://arpitbhayani.me/blogs/replication-strategies) ·
[When a Master or Replica Fails](https://arpitbhayani.me/blogs/handling-outages-master-replica) ·
[Read-Your-Writes Consistency](https://arpitbhayani.me/blogs/read-your-write-consistency) ·
[Why Eventual Consistency is Preferred](https://arpitbhayani.me/blogs/eventual-consistency) ·
[Consistent Hashing](https://arpitbhayani.me/blogs/consistent-hashing) ·
[How Writes Work in Apache Cassandra](https://arpitbhayani.me/blogs/cassandra-writes)

**Failure and algorithms**
[Heartbeats in Distributed Systems](https://arpitbhayani.me/blogs/heartbeats-in-distributed-systems) ·
[Clock Synchronization Is a Nightmare](https://arpitbhayani.me/blogs/clock-sync-nightmare) ·
[Bloom Filters](https://arpitbhayani.me/blogs/bloom-filters) ·
[Isolation Forest](https://arpitbhayani.me/blogs/isolation-forest)

**Read only when the condition is true:**
[Multi-Paxos](https://arpitbhayani.me/blogs/multi-paxos) (you want Paxos properly) ·
[MySQL Replication Internals](https://arpitbhayani.me/blogs/mysql-replication-internals) ·
[Redis Replication Internals](https://arpitbhayani.me/blogs/redis-replication) ·
[Product Quantization](https://arpitbhayani.me/blogs/product-quantization) (vector DB at scale) ·
[MinHash](https://arpitbhayani.me/blogs/jaccard-minhash) (deduping for RAG) ·
[NanoLog](https://arpitbhayani.me/blogs/nanolog-a-nanosecond-scale-logging-system) (latency-sensitive work) ·
[Bayesian Averages](https://arpitbhayani.me/blogs/bayesian-average) (ratings or leaderboards)

---

## How the system uses this file

- **One topic a day.** It takes the next unfinished topic from the current
  subject, then searches for the best articles **on that one topic**.
- It reads **up to five a day, all on the one topic**, in full, and writes one
  lesson about **the topic** — not about the articles. Several sources on one
  topic is how the lesson becomes worth more than any of them. Sources on two
  different topics is a forced connection, and I will not be able to follow
  it.
- If only one good article exists on today's topic, that is fine: a short
  honest lesson beats padding it with something unrelated.
- It prefers something **published recently** when quality is equal, because
  the field moves.
- Anything typed into the Learn page's box comes **first**, ahead of all of
  this.
- Each lesson names the subject, what it read, and the build it feeds.

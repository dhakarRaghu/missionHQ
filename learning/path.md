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

## The direction — the course is the spine

The direction used to live here as a list of subjects, and nothing read it:
the morning scan was handed this file as text, and whichever article scored
highest chose the day's subject. On 2026-09-14 the direction moved into seven
courses under `learning/courses/`, in this order:

1. Performance, concurrency and the machine
2. Applied AI systems at scale
3. Inference and AI platform — my `inference-internals` course (unit 1 is read before course 2)
4. Storage and database internals
5. Distributed systems and verification
6. Reliability, security and change
7. System design and architecture

**One course at a time**, marked active on the Courses page. Its phases run in
order, and the next one does not start while the last is unread. Change the
order on the Courses page; change a course's phases in its `course.md`.

## What an article is for

Articles are not a second, unrelated stream. Each one orbits the phase I am
on, and says what it is for relative to it:

- **fails** — a real incident on the phase's mechanism
- **measures** — a benchmark or experiment, with its conditions
- **applies** — the mechanism in a real system people run
- **updates** — a default, version or practice that changed
- **challenges** — a counterexample or disagreement
- **extends** — an adjacent idea the course leaves out on purpose

A phase with no incident yet gets one before it gets another explainer. An
article never re-teaches the course and never unlocks the next phase.

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

- **The bar above goes to the morning scan** as the standard every lead must
  clear.
- **One article a weekday**, Monday to Friday. Weekends belong to the course
  and its lab.
- The scan aims at the active phase and the relationship it still lacks. A
  lead for another subject is not picked, however well it scores.
- It reads **up to three articles on the active phase**, in full — one
  relationship leads, and a second site comes before a second post from the
  same site. Weak ones are never added to reach a number.
- **Every article goes past its sources.** Hunter opens what each article
  points at (pull requests, issues, papers, docs) and finds at least two
  independent sources on other sites that confirm, measure differently, or
  contradict it. A number only the original team reports is labelled as
  theirs. On 2026-09-16 an article was built from one vendor post and could
  only say "all numbers are the post's own" — that is the failure this rule
  prevents.
- **Where to look is per course**, in `sources.md`: the scan gets the active
  course's section, not one list for everything.
- **What expires is news, not knowledge.** A release note goes stale; a
  postmortem does not.
- Anything typed into the Learn page's box still comes **first**.
- If nothing on the phase clears the bar, the morning says so and hunts for
  better sources instead of teaching something random.

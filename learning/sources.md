# Who to read

Re-organised by course on **2026-09-17**. Before that the list followed four
broad lanes, and it had one source for inference: the vLLM blog. Every
inference article therefore cited vLLM and nothing else. Now each course has
its own sources, from different sites, so an article can check one team's
claims against another's.

**How the system uses this.** The morning scan receives the section of the
course that is active, plus the shared sections at the bottom (incidents,
daily surfaces, reserve, rejected). The other courses' sections are left out,
so this file can grow without being cut. A section heading ends with the
course slug; keep that when editing.

Every entry was opened on the date shown; nothing is added from memory.
**Active** means a real engineering post in the last 120 days. **Archive**
means old but still true — a paper, a postmortem, a course — and it never
expires. "Mixed" means the site also posts marketing: pick its posts one at a
time.

## Course 1 — Performance, concurrency and the machine · elite-performance

- **Marc Brooker** — brooker.co.za/blog · 2026-09-09 · tail latency, Little's
  law, queueing with the maths. "Lorenz and Little: How Much Does Your Tail Cost?"
- **Daniel Lemire** — lemire.me/blog · 2026-09-16 · SIMD and CPU cost,
  always benchmarked.
- **Go blog** — go.dev/blog · 2026-09-16 · allocation, leak profiling.
  "Goroutine Leak Profiles".
- **Go GC guide** — go.dev/doc/gc-guide · archive · GOGC and GOMEMLIMIT with
  the formulas.
- **Dan Luu** — danluu.com · 2026-09 · performance culture, real bugs.
- **Mitchell Hashimoto** — mitchellh.com/writing · 2026-07-22 · SIMD in
  practice.
- **Alex Kladov (matklad)** — matklad.github.io · 2026-09-19 · systems
  programming from TigerBeetle: "Static Allocation, Constant Work", "Finding
  Bugs". Also under course 5. Added 2026-09-27.
- **Abhinav Upadhyay (Confessions of a Code Addict)** —
  blog.codingconfessions.com · 2026-08-29 · virtual memory, page tables, CPU
  basics, in plain English. "Demand Paging: What Happens When Linux Handles a
  Page Fault".
- **Polar Signals** — polarsignals.com/blog · 2026-07-28 · profiler internals
  (the company is joining Dash0; the blog may stop).
- **Uber engineering** — uber.com/blog/engineering · 2026-09-11 · Go CPU work
  with numbers. "Zero-Growth Stack, Real Gains".
- **Cloudflare** — blog.cloudflare.com · 2026-09-16 · mixed · memory layout
  with numbers. "How we saved 100 terabytes of memory…".
- **Discord engineering** — discord.com/category/engineering · 2026-06-30 ·
  a connection-pool bottleneck in a reconnect storm (3/25/26 voice outage).
- **Brendan Gregg** — brendangregg.com · archive (2025-11) · off-CPU
  analysis, eBPF method.
- **Travis Downs** — travisdowns.github.io · archive · "A Concurrency Cost
  Hierarchy".

### Papers — the shelf for this course

Verified 2026-09-18. One a week, on the paper day. A paper is durable: age is
not a reason to reject it.

- **The Tail at Scale** — CACM 2013 · barroso.org/publications/TheTailAtScale.pdf · behind: fan-out turns rare slowness into the normal tail · read Tables 1 and 2.
- **Achieving Microsecond-Scale Tail Latency Efficiently** — SOSP 2023 · dslab.epfl.ch/pubs/concord.pdf · behind: queueing and preemption cost · read Figures 2 and 6.
- **Strongly Tail-Optimal Scheduling in the Light-Tailed M/G/1** — arXiv 2024 · arxiv.org/abs/2404.08826 · behind: scheduling shapes the whole distribution · read section 1.4.
- **Scalability! But at what COST?** — HotOS 2015 · usenix.org/system/files/conference/hotos15/hotos15-paper-mcsherry.pdf · behind: scaling curves hide absolute slowness · read Figure 1.
- **Coz: Finding Code that Counts** — SOSP 2015 · sigops.org/s/conferences/sosp/2015/current/2015-Monterey/printable/090-curtsinger.pdf · behind: profiling shows time, not payoff · read Figure 2.
- **Profiling a Warehouse-Scale Computer** — ISCA 2015 · gwern.net/doc/cs/hardware/2015-kanev.pdf · behind: CPU caches and the datacenter tax · read Figures 4 and 11.
- **Characterizing a Memory Allocator at Warehouse Scale** — ASPLOS 2024 · people.csail.mit.edu/delimitrou/papers/2024.asplos.memory.pdf · behind: allocation lifetimes drive memory cost · read Figures 8 and 11.
- **Low-Latency, High-Throughput Garbage Collection** — PLDI 2022 · arxiv.org/abs/2210.17175 · behind: GC pauses set the tail · abstract checked only.
- **Everything You Always Wanted to Know About Synchronization** — SOSP 2013 · infoscience.epfl.ch (bitstream 68bfb25e) · behind: cache coherence sets the cost of sharing · read Tables 2 and 3.
- **Non-scalable locks are dangerous** — Linux Symposium 2012 · people.csail.mit.edu/nickolai/papers/boyd-wickizer-locks.pdf · behind: contention collapse, not slowdown · read Figure 2, then section 3.
- **Huron: Hybrid False Sharing Detection and Repair** — PLDI 2019 · homes.cs.washington.edu/~baris/public/huron.pdf · behind: false sharing on one cache line · read Figure 4, then Table 1.

Thin here: scalability laws. Only COST covers them.

## Course 2 — Applied AI systems at scale · elite-applied-ai

- **Hamel Husain** — hamel.dev · 2026-09-18 · evals and error analysis.
- **Eugene Yan** — eugeneyan.com/writing · 2026-06-21 · eval design.
- **Simon Willison, prompt-injection tag** — simonwillison.net/tags/prompt-injection
  · 2026-08-27 · attacks, defences, links to incidents. Take his own posts
  over the link notes.
- **Sean Goedecke** — seangoedecke.com · 2026-09-10 · how engineering work
  with models actually gets done.
- **Lilian Weng** — lilianweng.github.io · 2026-07-04 · long surveys; agent
  harnesses, reward hacking.
- **UK AISI blog** — aisi.gov.uk/blog · 2026-08-27 · eval method and real
  agent incident reports.
- **Temporal** — temporal.io/blog · 2026-09-15 · mixed · durable execution
  for agents.
- **Braintrust** — braintrust.dev/blog · 2026-08-24 · mixed, vendor · agent
  evals, trace storage.
- **Vespa** — blog.vespa.ai · 2026-09-13 · retrieval quality with measured
  results.
- **Honeycomb** — honeycomb.io/blog · 2026-09-21 · mixed · agent
  observability and OpenTelemetry sampling: "Wide Events vs. Three Pillars:
  AI Observability Costs", "How Adaptive Tail Sampling Works in the
  OpenTelemetry Collector". Also under course 6. Added 2026-09-27.
- **Latent Space** — latent.space · daily · what shipped and why; a finding
  surface more than a source.
- **arXiv cs.CL / cs.CR** — arxiv.org/list/cs.CL/recent · daily · papers.
  Example: CaMeL, "Defeating Prompt Injections by Design".
- **OWASP Top 10 for LLM applications** — genai.owasp.org/llm-top-10 ·
  archive (2025) · the threat list.
- **AI incidents, archive** — Anthropic, "April 23 postmortem" (Claude Code
  quality regressions, 2026-04-23); Anthropic, "A postmortem of three recent
  issues" (2025-09-17).

Gap: cost per successful task. The posts found on it were marketing. A
measured one goes straight into this list.

### Papers — the shelf for this course

Verified 2026-09-18.

- **Hidden Technical Debt in Machine Learning Systems** — NeurIPS 2015 · proceedings.neurips.cc (86df7dcf…-Paper.pdf) · behind: why model changes are hard to roll back · text not extractable, sections not checked.
- **Underspecification Presents Challenges for Credibility in ML** — JMLR 2022 · jmlr.org/papers/v23/20-1335.html · behind: equal test scores, different production behaviour · read section 5.1 and Figure 4.
- **Retrieval-Augmented Generation for Knowledge-Intensive NLP** — NeurIPS 2020 · arxiv.org/abs/2005.11401 · behind: the retrieval design everyone still copies · read Figure 1 and Table 1.
- **Evaluating Retrieval Quality in RAG (eRAG)** — arXiv 2024 · arxiv.org/abs/2404.13781 · behind: relevance labels barely predict answer quality · read section 3.2 and Table 1.
- **τ-bench** — arXiv 2024 · arxiv.org/abs/2406.12045 · behind: agent reliability across repeated runs (pass^k) · read section 5.1 and Figure 4.
- **AgentDojo** — NeurIPS 2024 · arxiv.org/abs/2406.13352 · behind: tool execution over untrusted data · read section 4.3 and Figure 9(b).
- **Formalizing and Benchmarking Prompt Injection Attacks and Defenses** — USENIX Security 2024 · usenix.org/conference/usenixsecurity24/presentation/liu-yupei · behind: measuring guardrails · read section 6.3 and Tables 7 to 8.
- **Defeating Prompt Injections by Design (CaMeL)** — arXiv 2025 · arxiv.org/abs/2503.18813 · behind: guardrails as system design · read section 4.1 and Figure 3.
- **Judging LLM-as-a-Judge** — arXiv 2023 · arxiv.org/abs/2306.05685 · behind: judge bias and agreement · read section 3.3 and Table 5.
- **Lessons from the Trenches on Reproducible Evaluation** — arXiv 2024 · arxiv.org/abs/2405.14782 · behind: benchmark discipline · read section 3.
- **FrugalGPT** — arXiv 2023 · arxiv.org/abs/2305.05176 · behind: cost per successful task through cascades · read section 3 and Figure 5.

Thin here: rollout and rollback of model changes. No paper found on canary or revert of model versions.

## Course 3 — Inference and AI platform · elite-inference, inference-internals

- **vLLM blog** — vllm.ai/blog (blog.vllm.ai redirects here) · 2026-09-24 ·
  engine internals. Vendor's own numbers: pair every vLLM post with a source
  from another site.
- **LMSYS / SGLang** — lmsys.org/blog · 2026-08-07 · SGLang kernels,
  speculative decoding, prefix caching. The index shows only its menu; find
  posts by search.
- **NVIDIA technical blog, inference tag** —
  developer.nvidia.com/blog/tag/inference-performance · 2026-09-02 · mixed ·
  speculative decoding, GPU sizing, cost. Skip product posts.
- **llm-d** — llm-d.ai/blog · 2026-09-14 · KV-aware routing, KV sharing,
  disaggregation on Kubernetes. "Sticky Until Saturated".
- **LMCache** — blog.lmcache.ai · 2026-09-15 · KV transfer, storage tiers,
  disaggregated prefill and decode.
- **Anyscale** — anyscale.com/blog · 2026-09-26 · Ray Serve routing and
  throughput, with hardware and workload stated.
- **Modal** — modal.com/blog · 2026-09-26 · mixed · serving limits and how
  they were removed, with numbers: "Hitting a billion tokens per minute on one
  GPU by combining a query planner and an inference engine". Rejected as
  marketing on 2026-09-17; re-checked through its feed on 2026-09-27. Skip
  the product posts.
- **PyTorch blog** — pytorch.org/blog · 2026-09-16 · mixed · kernels and
  low-precision formats.
- **vLLM bug tracker** —
  github.com/vllm-project/vllm/issues?q=is%3Aissue+label%3Abug+sort%3Aupdated-desc
  · daily · real serving failures, with reproductions.
- **SGLang bug tracker** —
  github.com/sgl-project/sglang/issues?q=is%3Aissue+label%3Abug+sort%3Aupdated-desc
  · daily · the same, for a second engine.
- **vLLM roadmap and RFCs** — github.com/vllm-project/vllm/issues/48168 (Q3
  2026 roadmap, updated 2026-09-24) and the `RFC` label (222 open on
  2026-09-27) · what the maintainers call unsolved, in their own words: an
  unchecked roadmap box is an open problem. Frontier-day material. Added
  2026-09-27.
- **SGLang roadmap** — github.com/sgl-project/sglang/issues/22949 (2026 Q2,
  updated 2026-09-08) · the same for the second engine. Added 2026-09-27.
- **arXiv cs.DC** — arxiv.org/list/cs.DC/recent · daily · serving research.
- **OSDI '26** — usenix.org/conference/osdi26/technical-sessions · papers ·
  KV offloading, scheduling. "Strata".
- **MLSys proceedings** — proceedings.mlsys.org · archive · "Beyond the Buzz:
  A Pragmatic Take on Inference Disaggregation" (2026).
- **Serving incidents, archive** — Anthropic, "A postmortem of three recent
  issues" (routing, TPU and top-k bugs, 2025-09-17); Thinking Machines,
  "Defeating Nondeterminism in LLM Inference" (2025-09-10); DistServe, OSDI
  '24 (goodput and disaggregation).
- **Sebastian Raschka** — magazine.sebastianraschka.com · 2026-09-09 ·
  architecture explained for builders: model literacy, not serving.

### Papers — the shelf for this course

Verified 2026-09-18.

- **Attention Is All You Need** — NeurIPS 2017 · arxiv.org/abs/1706.03762 · behind: the K/V tensors that become the KV cache · read Figure 2 and section 3.2.
- **FlashAttention** — NeurIPS 2022 · arxiv.org/abs/2205.14135 · behind: attention is memory-bound, which sets decode cost · read Figure 1 and section 3.1.
- **Orca** — OSDI 2022 · usenix.org/conference/osdi22/presentation/yu · behind: continuous batching · read section 3 and Figure 5.
- **PagedAttention / vLLM** — SOSP 2023 · arxiv.org/abs/2309.06180 · behind: paged KV memory · read Figure 3, then section 4.1.
- **SGLang** — arXiv 2023 · arxiv.org/abs/2312.07104 · behind: prefix caching across requests · read section 3 and Figure 3.
- **Fast Inference via Speculative Decoding** — ICML 2023 · arxiv.org/abs/2211.17192 · behind: speculative decoding · read Algorithm 1 (2.3) and Figure 2.
- **AWQ** — MLSys 2024 · arxiv.org/abs/2306.00978 · behind: weight quantization · read Table 1 and Figure 2.
- **Megatron-LM** — arXiv 2019 · arxiv.org/abs/1909.08053 · behind: tensor parallelism · read Figure 3.
- **GShard** — arXiv 2020 · arxiv.org/abs/2006.16668 · behind: expert parallelism · read Figure 3 and section 3.2.
- **DistServe** — OSDI 2024 · arxiv.org/abs/2401.09670 · behind: disaggregated prefill and decode · read Figure 2 and section 3.
- **Sarathi-Serve** — OSDI 2024 · arxiv.org/abs/2403.02310 · behind: chunked prefill and SLO-aware scheduling · read Figure 7 and section 4.2.
- **Llumnix** — OSDI 2024 · usenix.org/conference/osdi24/presentation/sun-biao · behind: multi-tenancy and priority · abstract checked only.

Thin here: capacity and multi-tenancy. Only Llumnix, and its full text was not read.

## Course 4 — Storage and database internals · elite-storage

- **Phil Eaton** — notes.eatonphil.com · 2026-09-13 · WAL bugs, Postgres
  internals, data races.
- **PlanetScale** — planetscale.com/blog · 2026-09-16 · mixed · Postgres
  failures, pools, large tables. "The dangers of Postgres subtransactions".
- **Percona** — percona.com/blog · 2026-09-17 · MySQL and Postgres
  operations, measured.
- **Depesz** — depesz.com · 2026-08-25 · new Postgres features, one at a time.
- **Crunchy Data** — crunchydata.com/blog · 2026-09-02 · practical Postgres,
  migrations.
- **pganalyze** — pganalyze.com/blog · 2026-08-13 · Postgres internals read
  from the source.
- **Franck Pachot** — dev.to/franckpachot · 2026-09-24 · execution plans read
  line by line, Postgres 19 and DocumentDB: "NOT IN can be executed as an
  Anti-Join (NOT EXISTS) in PG19". Added 2026-09-27.
- **CedarDB** — cedardb.com/blog · 2026-09-21 · mixed · the Umbra team's
  engine posts: "Encoding or Compression: Why not both?". Skip the demos.
  Added 2026-09-27.
- **ScyllaDB** — scylladb.com/blog · 2026-09-22 · mixed, vendor · engine work
  such as "Bringing QUIC to Seastar"; skip release and customer posts. Added
  2026-09-27.
- **Justin Jaffray (NULL BITMAP)** — buttondown.com/jaffray/archive ·
  2026-06-29 · query engine internals.
- **Neon** — neon.com/blog · 2026-09-09 · mixed · buffer cache deep dives only.
- **antirez** — antirez.com · ~2026-07-29 · systems, from the Redis author.
- **CMU 15-445 (Fall 2025)** — 15445.courses.cs.cmu.edu/fall2025/schedule.html
  · archive · buffer pools, B+trees, MVCC, recovery, with notes and video.
- **USENIX FAST '26** — usenix.org/conference/fast26/technical-sessions ·
  papers · LSM, data integrity.
- **Alex Miller (transactional.blog)** — transactional.blog · archive
  (2025-10) · torn writes, how transactions are built.
- **Zerodha tech** — zerodha.tech · archive (2024-03) · running
  multi-terabyte Postgres, in plain English.

### Papers — the shelf for this course

Verified 2026-09-18, every one by full text.

- **ARIES** — ACM TODS 1992 · web.stanford.edu/class/cs345d-01/rl/aries.pdf · behind: WAL and the durability contract · read 6.1 to 6.3.
- **All File Systems Are Not Created Equal** — OSDI 2014 · usenix.org/system/files/conference/osdi14/osdi14-paper-pillai.pdf · behind: the fsync and ordering assumptions your code makes · read Table 1.
- **Can Applications Recover from fsync Failures?** — ATC 2020 · usenix.org/system/files/atc20-rebello.pdf · behind: what a failed fsync does · read Tables 1 and 2.
- **The RocksDB Experience** — FAST 2021 · usenix.org/system/files/fast21-dong.pdf · behind: compaction and amplification in a real fleet · read section 3, Table 3, Figure 2.
- **Constructing and Analyzing the LSM Compaction Design Space** — PVLDB 2021 · arxiv.org/abs/2202.04522 · behind: compaction as four primitives · read section 3.1 and Table 1.
- **Closing the B-tree vs. LSM-tree Write Amplification Gap** — VLDB 2022 · arxiv.org/pdf/2107.13987 · behind: the default belief, re-measured · read Figures 9 and 10.
- **Virtual-Memory Assisted Buffer Management** — SIGMOD 2023 · ibr.cs.tu-bs.de/vss/Publications/2023/leis_23_sigmod.pdf · behind: buffer pools without a hash table · read Figure 1 and Table 1.
- **LeanStore** — PVLDB 2024 · vldb.org/pvldb/vol17/p4536-leis.pdf · behind: one coherent modern engine · read 2.1, 2.2 and 2.7.
- **An Empirical Evaluation of In-Memory MVCC** — PVLDB 2017 · vldb.org/pvldb/vol10/p781-Wu.pdf · behind: MVCC split into four decisions · read sections 3 to 6.
- **Simple Testing Can Expose Most Critical Transaction Bugs** — PVLDB 2025 · vldb.org/pvldb/vol18/p2547-cui.pdf · behind: isolation tested, not trusted · read Table 1 and Figure 2.
- **Online, Asynchronous Schema Change in F1** — PVLDB 2013 · vldb.org/pvldb/vol6/p1045-rae.pdf · behind: what your migration tool implements · read section 3.3 and Figure 3.
- **Online Schema Evolution is (Almost) Free for Snapshot Databases** — PVLDB 2022 · vldb.org/pvldb/vol16/p140-hu.pdf · behind: DDL as MVCC data modification · read 4.2 and 6.3.

Thin here: index structures themselves.

## Course 5 — Distributed systems and verification · elite-distributed

- **Murat Demirbas** — muratbuffalo.blogspot.com · 2026-09-12 · papers read
  closely, TLA+, metastability.
- **TigerBeetle** — tigerbeetle.com/blog · 2026-09-17 · deterministic
  simulation testing, by the people who built it.
- **Antithesis** — antithesis.com/blog · 2026-08-12 · mixed · real bugs
  found. "Finding bugs in Raft implementations".
- **Jack Vanlightly** — jack-vanlightly.com · 2026-08-28 · log replication
  design, Kafka behaviour. (Not www.vanlightly.com, which does not resolve.)
- **Marc Brooker** — brooker.co.za/blog · 2026-09-09 · distributed OLTP.
  "Aurora DSQL: Scalable, Multi-Region OLTP".
- **Hillel Wayne** — hillelwayne.com/post · 2026-09-01 · formal methods.
- **Decentralized Thoughts** — decentralizedthoughts.github.io · 2026-09-26 ·
  consensus and BFT with the proofs: "Why BFT with Byzantine and Crash Faults
  Needs Three Rounds". Theory; take the posts that explain a bound. Added
  2026-09-27.
- **Alex Kladov (matklad)** — matklad.github.io · 2026-09-19 · deterministic
  simulation testing and finding bugs, from TigerBeetle. Also under course 1.
  Added 2026-09-27.
- **Arpit Bhayani** — arpitbhayani.me/topics/distributed-systems · replication,
  consensus, clocks. Use the topic page: his newest posts are about AI.
- **Jepsen analyses** — jepsen.io/analyses · archive (2026-03) · consistency
  bugs found with history checkers.
- **USENIX NSDI '26** — usenix.org/conference/nsdi26/technical-sessions ·
  papers · failure recovery, consensus.
- **MIT 6.5840 (Spring 2026)** — pdos.csail.mit.edu/6.824/schedule.html ·
  archive · Raft, linearizability, ZooKeeper, Spanner.
- **Aleksey Charapko** — charap.co · archive (2026-05) · metastable failures.
- **Anish Athalye** — anishathalye.com · archive (2017) · "Testing
  Distributed Systems for Linearizability" (the ideas behind Porcupine).
- **Meta engineering** — engineering.fb.com · 2026-09-03 · ZippyDB, RDMA,
  scale.

### Papers — the shelf for this course

Verified 2026-09-18.

- **Linearizability: A Correctness Condition for Concurrent Objects** — TOPLAS 1990 · cs.brown.edu/~mph/HerlihyW90/p463-herlihy.pdf · behind: what a history checker asserts · read Figure 1's four histories.
- **Sagas** — SIGMOD 1987 · sigmodrecord.org/1987/12/09/sagas/ · behind: long transactions as steps plus compensation · landing page only.
- **Life beyond Distributed Transactions** — CIDR 2007 · cidrdb.org/cidr2007/papers/cidr07p15.pdf · behind: idempotence and the outbox · read section 3.
- **Elle: Inferring Isolation Anomalies from Experimental Observations** — VLDB 2020 · arxiv.org/abs/2003.10554 · behind: black-box history checking · abstract checked only.
- **AWDIT: An Optimal Weak Database Isolation Tester** — PLDI 2025 · arxiv.org/abs/2504.06975 · behind: checking weak isolation fast enough for CI · abstract checked only.
- **Spanner** — OSDI 2012 · usenix.org/system/files/conference/osdi12/osdi12-final-16.pdf · behind: clocks as bounded uncertainty · read section 3, then 5.3.
- **Millions of Tiny Databases** — NSDI 2020 · usenix.org/conference/nsdi20/presentation/brooker · behind: partitioning to shrink blast radius · abstract checked only.
- **Bodega: Serving Linearizable Reads via Roster Leases** — arXiv 2025 · arxiv.org/abs/2509.07158 · behind: leases and fencing · abstract checked only.
- **Paxos Made Live** — PODC 2007 · static.googleusercontent.com/media/research.google.com/en//archive/paxos_made_live.pdf · behind: consensus as a user · read the algorithmic-challenges sections.
- **FoundationDB** — SIGMOD 2021 · foundationdb.org/files/fdb-paper.pdf · behind: deterministic simulation testing · read the simulation-testing section.
- **Use of Formal Methods at Amazon Web Services** — 2014 · lamport.azurewebsites.net/tla/formal-methods-amazon.pdf · behind: TLA+ on real services · read the per-service benefit table.
- **Validating Traces of Distributed Programs Against TLA+ Specifications** — SEFM 2024 · arxiv.org/abs/2404.16075 · behind: spec against implementation · abstract checked only.

Thin here: session guarantees. Terry 1994 has no readable free copy.

## Course 6 — Reliability, security and change · elite-reliability

- **Lorin Hochstein (Surfing Complexity)** — surfingcomplexity.blog ·
  2026-09-12 · public incident reports read for the mechanism.
- **Adaptive Capacity Labs** — adaptivecapacitylabs.com/blog · 2026-08-25 ·
  mixed · resilience engineering; take only the posts that analyse a named
  incident, skip the essays. Added 2026-09-27.
- **GitHub availability reports** — github.blog/tag/github-availability-report
  · 2026-09-09 · monthly. Open the individual report; the index is often just
  a count.
- **Uber engineering** — uber.com/blog/engineering · 2026-09-11 · load
  shedding by priority, with before and after numbers.
- **Discord engineering** — discord.com/category/engineering · 2026-06-30 · a
  cascading failure caused by a rollout (3/25/26).
- **Honeycomb** — honeycomb.io/blog · 2026-09-14 · mixed · telemetry design
  and sampling.
- **Charity Majors** — charity.wtf/archive · 2026-09-14 · high-cardinality
  observability.
- **Trail of Bits** — blog.trailofbits.com · 2026-09-15 · real authorization
  bugs.
- **Filippo Valsorda** — words.filippo.io · 2026-07-26 · supply chain,
  cryptography in practice.
- **Shopify engineering** — shopify.engineering · 2026-09-10 · security work
  from fix to merge.
- **Google SRE workbook** — sre.google/workbook · archive · SLOs and
  burn-rate alerts with exact numbers ("Alerting on SLOs").
- **Amazon Builders' Library** — builder.aws.com/learn/topics/builders-library
  · archive (2019) · load shedding, retries, overload. The HTML pages redirect;
  the PDFs work.
- **"Metastable Failures in the Wild" (OSDI '22)** —
  usenix.org/conference/osdi22/presentation/huang-lexiang · archive · the
  paper, with video.
- **CrowdStrike Channel File 291 root cause** — crowdstrike.com (PDF,
  2024-08-06) · archive · a content update pushed everywhere at once.

### Papers — the shelf for this course

Verified 2026-09-18.

- **Dapper** — Google 2010 · research.google/pubs/dapper-a-large-scale-distributed-systems-tracing-infrastructure/ · behind: trace context and sampling · abstract checked only.
- **The Benefit of Hindsight: Tracing Edge-Cases** — NSDI 2023 · usenix.org/system/files/nsdi23-zhang-lei.pdf · behind: keep traces on a trigger, not by head sampling · read 4.3 and Table 3.
- **Metastable Failures in Distributed Systems** — HotOS 2021 · sigops.org/s/conferences/hotos/2021/papers/hotos21-s11-bronson.pdf · behind: trigger plus sustaining loop · read Figure 1 and 2.1.
- **Metastable Failures in the Wild** — OSDI 2022 · usenix.org/system/files/osdi22-huang-lexiang.pdf · behind: the same shape, measured · read Table 1 and Figure 1.
- **Overload Control for Scaling WeChat Microservices** — SoCC 2018 · cs.columbia.edu/~junfeng/papers/dagor-socc18.pdf · behind: shedding by queueing time and priority · read 4.2 and Figure 6.
- **Rajomon: Decentralized Overload Control** — NSDI 2025 · usenix.org/conference/nsdi25/presentation/xing · behind: overload across a service graph · abstract checked only.
- **Making Deployments Safe at Meta** — ISSRE 2026 · arxiv.org/abs/2608.20513 · behind: health checks gating each rollout phase · read section IV.
- **How to Fight Production Incidents?** — SoCC 2022 · microsoft.com/en-us/research/wp-content/uploads/2022/09/3542929.3563482.pdf · behind: where incident time is lost · read Figures 1 and 3.
- **Zanzibar** — ATC 2019 · usenix.org/system/files/atc19-pang.pdf · behind: authorization between services · read 4.2 and Figure 5.
- **in-toto** — USENIX Security 2019 · usenix.org/system/files/sec19-torres-arias.pdf · behind: the build pipeline as attack surface · read 4.1 and Table 4.
- **BeyondCorp** — ;login: 2014 · usenix.org/system/files/login/articles/login_dec14_02_ward.pdf · behind: trust the device and user, not the network · read Figure 1.

Thin here: SLOs and burn-rate alerting. No paper found; the Google SRE workbook chapter stands in.

## Course 7 — System design and architecture · elite-system-design

- **Marc Brooker** — brooker.co.za/blog · 2026-09-09 · cost, tail latency and
  distributed databases, with the maths.
- **AWS cell-based architecture guide** —
  docs.aws.amazon.com/wellarchitected/latest/reducing-scope-of-impact-with-cell-based-architecture
  · archive (2023) · cells and limiting the reach of a failure.
- **Notion engineering** — notion.com/blog/topic/tech · 2026-04 · schema
  evolution checked in CI, data residency.
- **Stripe engineering** — stripe.dev/blog/topic/engineering · 2026-09-14 ·
  automated repair of a database fleet. Payments is the day job: take its
  systems posts only.
- **Meta engineering** — engineering.fb.com · 2026-09-03 · "ZGateway:
  Learnings from Putting a Proxy in Front of ZippyDB".
- **LinkedIn engineering** — linkedin.com/blog/engineering · 2026-09-14 ·
  capacity planning with statistics.
- **Discord engineering** — discord.com/category/engineering · 2026-06-30 ·
  "Cost Attribution in Discord's API".
- **Slack engineering** — slack.engineering · 2026-07-14 · platform design
  with staged rollout and automatic rollback.
- **Spotify engineering** — engineering.atspotify.com · 2026-09-16 · mixed ·
  experiments and quality with numbers: "Why Spotify Is Not Using Bayesian
  A/B Testing". Added 2026-09-27.
- **Fly.io** — fly.io/blog · 2026-09-03 · infrastructure with real numbers.
- **Netflix tech blog** — netflixtechblog.com · 2026-09-25 · "Building
  Service Topology at Scale", a real-time distributed graph in three parts,
  "A Tale of Two Flink Autoscalers". "In-House LLM Serving at Netflix"
  (2026-07-17) serves course 3. The page blocks this system's fetcher; the
  feed works (see Feeds). Added 2026-09-27.
- **Uber engineering** — eng.uber.com · 2026-09-11. Use this host or
  uber.com/blog/engineering; www.uber.com answers 406.
- **InfoQ presentations** — infoq.com/architecture-design/presentations ·
  2026-09-16 · case studies told by the people who run them.
- **SREcon26 Americas** — usenix.org/conference/srecon26americas/program ·
  talks, with video. "Escaping Version Skew".
- **Arpit Bhayani, video breakdowns** — arpitbhayani.me/videos · 186 videos
  with slides and notes · worked walkthroughs of real architectures.

### Papers — the shelf for this course

Verified 2026-09-18.

- **Millions of Tiny Databases (Physalia)** — NSDI 2020 · usenix.org/conference/nsdi20/presentation/brooker · behind: cells as the unit of blast radius · read 2.1 and Figure 4.
- **Amazon DynamoDB** — ATC 2022 · usenix.org/conference/atc22/presentation/elhemali · behind: demand turned into partition capacity · read 1.1, 1.2 and 4.2.
- **Kora: A Cloud-Native Event Streaming Platform for Kafka** — VLDB 2023 · vldb.org/pvldb/vol16/p3822-povzner.pdf · behind: cells plus randomized tenant placement · read Figures 10 and 4.
- **Global Capacity Management With Flux** — OSDI 2023 · usenix.org/system/files/osdi23-eriksen.pdf · behind: capacity planning as optimization · read 3.2, 3.3 and 6.2.
- **Metastable Failures in the Wild** — OSDI 2022 · usenix.org/conference/osdi22/presentation/huang-lexiang · behind: blast radius from feedback loops · read Table 1 and Figure 1.
- **Zanzibar** — ATC 2019 · usenix.org/system/files/atc19-pang.pdf · behind: ownership as an API other services call · read section 2, Figure 1, Table 1.
- **TAO** — ATC 2013 · usenix.org/conference/atc13/technical-sessions/presentation/bronson · behind: one owner for a read-heavy graph · abstract checked only.
- **Borg** — EuroSys 2015 · research.google/pubs/large-scale-cluster-management-at-google-with-borg/ · behind: overcommit and packing as policy · abstract checked only.
- **Autopilot** — EuroSys 2020 · research.google/pubs/autopilot-workload-autoscaling-at-google-scale/ · behind: sizing from history · abstract checked only.
- **The Tail at Scale** — CACM 2013 · research.google/pubs/the-tail-at-scale/ · behind: the arithmetic behind latency targets · abstract checked only.
- **Text Mining and Classification of Architecture Decision Records** — arXiv 2026 · arxiv.org/abs/2609.07375 · behind: what design records actually contain · abstract checked only.

Thin here: shuffle sharding. No paper exists; Physalia and Kora are the closest.

## Course 8 — Production infrastructure: change and proof · elite-production-infra

Added 2026-09-18 with the course. These are hosts already verified elsewhere
in this file, pointed at this course's subjects; the next source hunt fills
the gaps, which are marked at the end.

- **HashiCorp blog** — hashicorp.com/blog · 2026-09-27 (feed checked; its
  newest item is scheduled for 2026-09-29) · Terraform state, plan and drift,
  from the people who build it. Mixed, mostly product news: skip the
  announcements.
- **OpenTofu blog** — opentofu.org/blog · 2026-09-17 · the fork's own changes:
  "A Vision for Built-in Linting", the 1.12 release notes. Take the design
  posts.
- **Gruntwork blog** — gruntwork.io/blog · infrastructure-as-code practice at
  scale, module design and test ladders.
- **Cloudflare** — blog.cloudflare.com · 2026-09-16 · the config change that
  reaches everything at once; their postmortems are the best of that kind.
- **Slack engineering** — slack.engineering · 2026-07-14 · staged rollout and
  automatic rollback of a platform.
- **Meta engineering** — engineering.fb.com · 2026-09-03 · deployment safety
  at fleet scale.
- **Uber engineering** — uber.com/blog/engineering · 2026-09-11 · change
  management and capacity in production.
- **Trail of Bits** — blog.trailofbits.com · 2026-09-15 · build pipelines as
  an attack surface, signing and verification.
- **Filippo Valsorda** — words.filippo.io · 2026-07-26 · supply chain,
  dependencies and signing, in plain terms.
- **The Update Framework and Sigstore blogs** — theupdateframework.io,
  blog.sigstore.dev · 2026-06-28 (Sigstore: "Rekor v2 GA", "Cosign v3"; TUF
  has no feed, its date is not checked) · artifact signing and verification,
  by the projects themselves.
- **Flux CD blog** — fluxcd.io/blog · 2026-08-12 · drift as the project sees
  it: "Selective drift correction with ignore rules", "Flux and OpenBao:
  Secrets and Signatures". Added 2026-09-27.
- **Kubernetes blog** — kubernetes.io/blog · 2026-09-22 · mixed · the primary
  source for what each release changes (the v1.37 feature posts); skip the
  community spotlights. Added 2026-09-27.
- **Chainguard Unchained** — chainguard.dev/unchained · 2026-09-24 · mixed,
  vendor · the "This Shit is Hard" series on FIPS and regulated builds is
  real engineering; skip the announcements. Added 2026-09-27.
- **GitHub availability reports** — github.blog/tag/github-availability-report
  · 2026-09-09 · pipeline and platform failures, monthly.
- **AWS post-event summaries** — aws.amazon.com/premiumsupport/technology/pes/
  · archive · what a control-plane failure does to everyone downstream.

### Papers — the shelf for this course

- **in-toto: farm-to-table guarantees** — USENIX Security 2019 ·
  usenix.org/system/files/sec19-torres-arias.pdf · behind: the pipeline as
  the attack surface · read 4.1 and Table 4.
- **Making Deployments Safe at Meta** — ISSRE 2026 · arxiv.org/abs/2608.20513
  · behind: health checks gating each phase of a rollout · read section IV.
- **How to Fight Production Incidents?** — SoCC 2022 ·
  microsoft.com/en-us/research/wp-content/uploads/2022/09/3542929.3563482.pdf
  · behind: where recovery time is lost · read Figures 1 and 3.
- **The CrowdStrike Channel File 291 root cause** — 2024-08-06 · archive · a
  content update that shipped everywhere without a deploy.

Thin here: infrastructure-as-code has no research shelf worth the name, and
the drift and rehearsal subjects have no paper at all. The next hunt looks for
practitioners rather than papers.

## Engineering craft — any course

- **Julia Evans** — jvns.ca · 2026-07-21 · mechanisms from first principles.
  Recent posts are on Django and CSS; take the systems ones.
- **Thorsten Ball** — registerspill.thorstenball.com/archive · 2026-09-06 ·
  weekly · writing code well with a model in the loop.
- **Armin Ronacher** — lucumr.pocoo.org · 2026-09-07 · long-horizon coding
  models.
- **Arpit Bhayani** — arpitbhayani.me/blogs · 2026-08-21 · **the style
  reference for every lesson** — see "How his writing reads", below.

## Papers he already picked: Arpit Bhayani's shelf

- **Papershelf** — arpitbhayani.me/papershelf · 111 papers, one a week, grouped
  by topic, with his own notes on many of them. Checked 2026-09-18. He is the
  style reference for this whole system, and his taste in papers is close to
  the owner's. Use it as a place to find the paper for a phase.
- **His Paper Notes posts** — arpitbhayani.me/blogs (titles starting "Paper
  Notes") · the shape a paper article should have: a TL;DR with the headline
  numbers, three things worth knowing, then the mechanism explained part by
  part, in plain words.
  Checked through his feed on 2026-09-27: four such posts exist, all from
  2024. Two map to a course. "NanoLog" (2024-08-28,
  arpitbhayani.me/blogs/nanolog-a-nanosecond-scale-logging-system) fits
  course 1. "On-demand Container Loading in AWS Lambda" (2024-09-15,
  arpitbhayani.me/blogs/on-demand-container-loading-in-aws-lambda) fits
  course 7. The other two are "Pipe Syntax in SQL" (2024-09-03) and "The Who
  to Follow Service at Twitter" (2024-08-21). On a paper day for one of these
  papers, read his note first for the shape, then write from the paper itself.
- His shelf links to his own copies. Always find the canonical source (USENIX,
  arXiv, VLDB, ACM open access) and cite that.

Titles from his shelf that map to a course, for the paper day. They are
suggestions, not verified entries: find the paper, then check it fits the
phase.

- **Performance**: The NUMA Experience · The Impact of Thread-Per-Core
  Architecture on Application Tail Latency · NanoLog · In-Memory Performance
  for Big Data · Snapshot-Free Memory Reclamation for Lock-Free Structures.
- **Applied AI**: Lost in the Middle · Language Models are Few-Shot Learners ·
  Improving Language Understanding by Generative Pre-Training · Vector
  Database: Storage and Retrieval · Manu: A Cloud Native Vector Database ·
  Panda: Performance Debugging for Databases using LLM Agents.
- **Inference**: Attention Is All You Need · Lost in the Middle.
- **Storage**: MyRocks · The Bw-Tree · Segcache · SILK · Umbra · Leaper ·
  TreeLine · Designing Access Methods: The RUM Conjecture · SIEVE · Amazon
  Aurora · Predicate Caching · Take Out the TraChe · BonsaiKV · Flajolet-Martin
  probabilistic counting · The Bloom Paradox · Space-Time Trade-offs in Hash
  Coding with Allowable Errors.
- **Distributed**: Spanner · Chubby · Megastore · Dynamo · The Google File
  System · Challenges to Adopting Stronger Consistency at Scale · Distributed
  Transactions at Scale in Amazon DynamoDB · TiDB · Epoxy · PolarDB-SCC ·
  Skip graphs · Kademlia.
- **Reliability**: Gorilla · Zanzibar · Firecracker · Anycast as a Load
  Balancing feature · How to break software · Automated Unit Test Improvement
  using LLMs at Meta.
- **System design**: Kora · Amazon DynamoDB (ATC 2022) · Amazon Redshift
  re-invented · Intelligent Scaling in Amazon Redshift · Web Search for a
  Planet · Real-time Data Infrastructure at Uber · Magnet (Spark shuffle) ·
  The story of AWS Glue · On-demand Container Loading in AWS Lambda.

## About the paper shelves

Each course section above has a `### Papers` shelf, verified 2026-09-18. One
paper a week, on the paper day.

- **Five papers sit on two shelves**: The Tail at Scale, Zanzibar, Millions of
  Tiny Databases, Metastable Failures in the Wild, and the vLLM paper. Read
  each once; the second course links back to it rather than spending another
  paper day.
- **"abstract checked only"** means the landing page opened but the full text
  did not, so the reading hint is a guess. Open the PDF and skim its section
  headings before starting.
- A shelf is not fixed. A paper that turns out to be wrong for the phase goes,
  and the frontier days add new ones.

## Building with AI — tools, products and practice

For his field reading and his posts: what developers who use AI at work
learn, ship and argue about. His posts are for that developer, not for
people who study model serving, and the course sections above feed only
the second. Take the post, never the announcement. All opened 2026-09-29.

- **Simon Willison, the whole blog** — simonwillison.net · 2026-09-28 · new
  models and tools tried the day they ship, with what they cost and where
  they fail. Take his entries; skip the link notes.
- **Addy Osmani** — addyosmani.com/blog · 2026-09-14 · how teams run AI
  coding agents on real codebases. "Brownfield Agentic Engineering".
- **The Pragmatic Engineer (Gergely Orosz)** — newsletter.pragmaticengineer.com
  · 2026-09-24 · mixed · how AI changes engineering work: code review,
  hiring, teams moving simple workloads to open models to cut AI bills. Many
  deepdives are paywalled; use the free parts only.
- **Ben's Bites** — bensbites.com · 2026-09-29 · mixed · what a builder
  learns using agents each week, and tools worth trying. Skip the product
  roundups; take the "how I built this" sessions.
- **Harper Reed** — harper.blog · 2026-09-22 · mixed · working with coding
  agents day to day. "Why Don't My Agents Break Containment?" The notes are
  personal; take the posts.
- **GitHub blog, AI & ML** — github.blog/ai-and-ml · 2026-09-25 · mixed ·
  take the engineering posts ("Rendering huge pull requests in the GitHub
  Copilot app", "Migrating the GitHub Copilot runtime to Rust"), skip the
  feature announcements.
- **Cursor blog** — cursor.com/blog · 2026-09-23 · mixed · how an AI coding
  tool is built: token use in long agent runs, how it picks a model for a
  task. Take the research posts, skip the company news.

## Production incidents — the highest-value reading

Checked 2026-09-12.

- **Cloudflare outage postmortems** — blog.cloudflare.com/tag/outage/ · newest
  2026-02-21. Real root cause and the follow-up work: the Nov 2025 bot-file
  bug, the Dec 2025 config change that became their "Fail Small" programme.
- **SRE Weekly** — sreweekly.com · newest 2026-09-21 · weekly. Links out
  to incident analyses across the industry; follow it to the primary report.
- **OpenAI status history** — status.openai.com/history · newest 2026-09-25 ·
  every incident, as a feed. The feed item is a title; open the incident page
  for the write-up, when there is one: the 2026-09-03 "Elevated errors across
  ChatGPT and Codex" page names "a routing configuration change" (7:43 to
  8:20 a.m. PDT). Titles alone give the failure class. Added 2026-09-27.
- **Claude status history** — status.claude.com/history · newest 2026-09-26 ·
  titles only; the feed carries no root cause. Use it for the failure class
  and the date. Added 2026-09-27.
- **Google Cloud status** — status.cloud.google.com · newest 2026-09-10 · the
  feed holds current incidents only, each with its text and a root-cause
  section once resolved; the history page holds the rest. Azure has no feed.
  Added 2026-09-27.
- **danluu/post-mortems** — github.com/danluu/post-mortems · 200+ incidents,
  still updated. An archive, not a feed: mine it when the current subject
  needs a failure story and nothing recent has one.
- **AWS post-event summaries** — aws.amazon.com/premiumsupport/technology/pes/
  · newest 2025-10-19 (DynamoDB, us-east-1). Rare and deep. Check quarterly,
  like Jepsen.
- **GitHub availability reports** — github.blog · monthly, newest 2026-09-09.
  NOTE: the index is often just "we had five incidents" — open the individual
  report before trusting it to carry root cause.

## Daily surfaces — to FIND primary articles, never to quote

- **lobste.rs/top/1w** — best density. Most of the top fifteen were real
  technical posts on 2026-09-12.
- **huggingface.co/papers** — daily, upvotes as a practitioner signal.
- **arxiv.org/list/cs.DC/recent** and **/list/cs.CL/recent** — ~20 a weekday.
  Also **cs.PF** (performance) and **cs.OS**: about 12 and 2 a weekday on
  2026-09-25, and the systems papers that cs.DC misses. As feeds:
  rss.arxiv.org/rss/cs.DC+cs.PF+cs.OS, refreshed at midnight Eastern, empty
  at weekends, one request every 3 seconds across the whole system.
- **news.ycombinator.com/best** — high volume, low density: ~3 of 15 were
  technical. Filter hard or skip.
- **hnrss.org/newest?q=postmortem&points=20** — Hacker News as RSS, filtered
  to postmortems with 20 or more points. 20 items on 2026-09-27; about half
  are real incident write-ups (a DDoS postmortem, a kernel soundness bug),
  the rest are hacks and startup obituaries. Take the engineering ones. The
  service returned one 502 during testing; try again later rather than
  dropping the day.

Always record the primary article's own URL, never the aggregator's.

## Reserve — verified active, use when a slot frees up

Martin Fowler (2026-09-17, now mostly agentic engineering) · Kent Beck
(2026-09-02) · Vicki Boykis (2026-09-01) · Pinterest engineering
(2026-09-25, recommender systems; the feed works, the page blocks the
fetcher) · Philipp Schmid (2026-09-24; mostly Gemini how-tos, about one post
in four is a real agent post, such as "Evaluating Agents Beyond the First
Prompt") · Yelp engineering (2026-09-16, search ranking and migrations) ·
DuckDB news (2026-09-25, mostly product and integrations) · Import AI
(2026-09-07, weekly
summary) · Nathan Lambert, interconnects.ai (2026-09-11, post-training
commentary) · The Pragmatic Engineer (2026-09-17, mostly AI news and
paywalled) · Dropbox tech (2026-08-31, no example post opened yet) · Dan Luu
(quarterly — check like Jepsen).

## Off-lane

- **Stripe** — payments is the day job. It appears under course 7 for its
  systems posts only.
- **Monzo, Grab** — too far from the seven courses.

## Checked and rejected — do not re-add without a new date

**Stale** (newest post): Chip Huyen 2025-01-16 · Martin Kleppmann 2025-12-08
· materializedview.io 2025-09-11 · avi.im 2026-04-18 · Andy Pavlo 2026-01-04
(news) · Nelson Elhage 2026-03-23 · Camille Fournier 2026-05-31 · Brandur
2026-05-31 · Horace He (thonking.ai) 2025-03-04 · easyperf 2024-11-11 · High
Scalability 2024-05-09 · The Morning Paper 2021-02-08 · FoundationDB blog
2022-04-13 · GeekNarrator blog 2025-06-09 (podcast not checked) · Jepsen
2026-03-16 (kept under course 5 as an archive; check quarterly) · pvk.ca
2025-12-30 · Johnny's Software Lab 2026-02-26 · Bruce Dawson (randomascii)
2025-11-11 · Piotr Kołaczkowski 2023-05-21 · Brendan Gregg's blog 2026-02-07
(career posts; the archive entry under course 1 stays) · Simon Eskildsen
(sirupsen.com) 2024-11-16 · Tanel Poder 2026-04-10 (Oracle). The last seven
were checked 2026-09-27.

**Mostly marketing or off-subject** (checked 2026-09-17): Hugging Face blog ·
Turso · Pulumi and the OpenSSF blog (2026-09-27) · ClickHouse · Sentry · Railway · ByteByteGo · Baseten (no
dates) · Together · Fireworks · Character.ai · Databricks · NVIDIA Dynamo
release notes · CockroachDB · Cybertec · etcd blog (release notes) · Resonate
· S2 · Figma (own agent products) · incident.io ("best tools" lists) ·
Latacora (recent posts are AI advice) · Google Project Zero (exploits, not
service boundaries) · PhonePe · Will Larson (management) · aphyr.com (recent
posts not technical) · Jason Liu (recent posts personal; his 2025 RAG posts
stay good as archives) · AI Incident Database (news, not engineering). Modal
and the OpenAI status feed left this list on 2026-09-27: see course 3 and the
incidents section.

**Other:** Adyen — engineering URL 404s. Ethan Mollick, Zvi Mowshowitz —
not technical enough, or too much overlap with Latent Space.

- **Shreya Shankar** — sh-reya.com/blog · newest post 2026-05-31 (moved by the source hunt 2026-09-28)
- **Cloudflare postmortems (tag page)** — blog.cloudflare.com/tag/post-mortem · newest post 2026-05-01 (moved by the source hunt 2026-09-28)
- **Anthropic engineering** — anthropic.com/engineering · newest post 2026-04-23 (moved by the source hunt 2026-10-03)
- **Small Datum (Mark Callaghan)** — smalldatum.blogspot.com · newest post 2026-06-19 (moved by the source hunt 2026-10-18)

## Could not verify — worth a manual look in the browser

- **Rachel by the Bay** (rachelbythebay.com/w) and **Chris Siebenmann**
  (utcc.utoronto.ca/~cks/space/blog) — both block automated fetches, both
  look active, both in the systems lane.
- **Razorpay**, **Flipkart**, **Hotstar** — 403 to this system's fetcher.
  (Netflix and Pinterest left this list on 2026-09-27: their feeds work.) **Swiggy**
  (bytes.swiggy.com) — fetch failed. These are the Indian engineering blogs
  worth having; a browser check would settle them.
- **Heidi Howard** — blog URL 404. **Tri Dao** — not checked. **Restate** —
  page did not render (Modal: its feed works; see course 3). **Datadog**, **samwho.dev**,
  **Tanya Reilly** (noidea.dog) — no dates on the page.
- **OpenAI, "Expanding on what we missed with sycophancy"** — 403.
- Checked 2026-09-27, no feed found or an HTTP error: **Jamie Brandon**
  (scattered-thoughts.net), **Aleksey Shipilëv** (shipilev.net), **DoorDash**
  and **Airbnb** engineering (HTTP errors), **Learning From Incidents**
  (learningfromincidents.io, DNS), **Canva** (canva.dev/blog).

Operator can open these on a feed day and report the newest post date.

## How his writing reads — the style target, measured

He asked for lessons written the way Arpit writes: "his writing style is
simple, easier to understand — improve it according to that." So it was
measured rather than guessed. Six essays read on 2026-09-13 (bloom-filters,
mysql-replication-internals, how-llm-inference-works,
monolith-is-distributed-system, kafka-partitions, clock-sync-nightmare):

| | his essays | our Kubernetes Phase 0 lesson |
|---|---|---|
| Article length | 1,464–2,626 words (median 2,388) | 4,218 |
| Words between headings | 110–210 | 141 — already in range |
| Headings per article | 7 to 21 | 13 |
| First section | "Why Bloom Filters Matter", "Why Increase Partitions" | "The mental model" |
| Median sentence | 14 words | 13 |
| "you"/"your" per 1k words | 12 | 14 |
| Questions asked of the reader | ~3 per article | 0 |

**The gap is naming, not density.** Our sentences are as short as his and our
sections are as small — the "325" in an earlier version of this table counted
only top-level headings on our side and every heading on his. What differs is
that his headings tell you what question the section answers, while ours were
numbered labels. Four things to copy:

1. **A heading every 150 words or so** — already true of our lessons; keep it
   that way. A section is one idea, and past roughly 250 words it is two.
2. **Name the section after the question it answers**, in plain words: "What
   Happens to Existing Data", "The Key Ordering Problem", "Why Increase
   Partitions". Never a clever title, never a bare label like "Architecture".
3. **The first section is always "why this matters".** He puts the motivation
   in a section of its own, at the top, before any mechanism.
4. **Open with one plain sentence saying what the thing is, then the question
   the piece answers.** Bloom filters: "A Bloom filter is a probabilistic data
   structure that answers a very specific question — have I seen this thing
   before? — while using almost no memory. There is a trade-off, though."
   Kafka: "Partitions sit right in the middle of how Kafka works... But what
   actually happens when you need more of them?"

Re-measure rather than trusting this table: it was true of six essays on one
day, and he keeps writing.

## Feeds — one feed per source that has one

Checked with curl on 2026-09-27. A feed lists every post with its date, so a
code poll can find new posts without a model call and without opening the
page. Sources not listed here have no feed: Anthropic engineering, LMSYS,
Fireworks, Baseten, Uber (406), Gruntwork, TUF. Hunter reads those pages.

| Source | Feed | Items · newest |
|---|---|---|
| Arpit Bhayani | arpitbhayani.me/rss.xml | 111 · 2026-08-21 |
| Marc Brooker | brooker.co.za/blog/rss.xml | 163 · 2026-09-09 |
| Hamel Husain | hamel.dev/index.xml | 20 · 2026-09-18 |
| Eugene Yan | eugeneyan.com/rss/ | 212 · 2026-06-21 |
| Sebastian Raschka | magazine.sebastianraschka.com/feed | 20 · 2026-09-09 |
| Lilian Weng | lilianweng.github.io/index.xml | 53 · 2026-07-04 |
| Simon Willison | simonwillison.net/tags/prompt-injection.atom (tag feed; all posts: simonwillison.net/atom/everything/, newest 2026-09-25) | tag feed newest 2026-09-17 |
| Philipp Schmid | www.philschmid.de/rss | 211 · 2026-09-24 |
| vLLM blog | vllm.ai/blog/rss.xml | 50 · 2026-09-24 |
| Anyscale | anyscale.com/rss.xml | 18 · 2026-09-26 |
| Modal | modal.com/blog/atom.xml | 135 · 2026-09-26 |
| Honeycomb | honeycomb.io/rss/blog.xml | 50 · 2026-09-21 |
| Cloudflare | blog.cloudflare.com/rss/ | 20 · 2026-09-25 |
| Netflix tech blog | netflixtechblog.com/feed | 10 · 2026-09-25 |
| Pinterest engineering | medium.com/feed/pinterest-engineering | 10 · 2026-09-25 |
| Latent Space | latent.space/feed | 20 · 2026-09-25 |
| SRE Weekly | sreweekly.com/feed/ | 5 · 2026-09-21 |
| OpenAI status | status.openai.com/history.rss | 93 · 2026-09-25 |
| Claude status | status.claude.com/history.rss | 25 · 2026-09-26 |
| Abhinav Upadhyay | blog.codingconfessions.com/feed | 16 · 2026-08-29 |
| Alex Kladov (matklad) | matklad.github.io/feed.xml | 10 · 2026-09-19 |
| Franck Pachot | dev.to/feed/franckpachot | 7 · 2026-09-24 |
| CedarDB | cedardb.com/index.xml | 49 · 2026-09-21 |
| ScyllaDB | scylladb.com/feed/ | 20 · 2026-09-22 |
| Decentralized Thoughts | decentralizedthoughts.github.io/feed | 20 · 2026-09-26 |
| Adaptive Capacity Labs | adaptivecapacitylabs.com/feed/ | 10 · 2026-08-25 |
| Spotify engineering | engineering.atspotify.com/feed | 5 · 2026-09-16 |
| HashiCorp | hashicorp.com/blog/feed.xml | 20 · 2026-09-29 (scheduled) |
| OpenTofu | opentofu.org/blog/rss.xml | 19 · 2026-09-17 |
| Sigstore | blog.sigstore.dev/index.xml | 15 · 2026-06-28 |
| Flux CD | fluxcd.io/blog/index.xml | 25 · 2026-08-12 |
| Kubernetes blog | kubernetes.io/feed.xml | 22 · 2026-09-22 |
| Chainguard | chainguard.dev/api/rss | 603 · 2026-09-24 |
| Google Cloud status | status.cloud.google.com/en/feed.atom | current incidents only · 2026-09-10 |

Feeds were also verified for Meta, PyTorch, MLCommons, Character.AI,
Together, LangChain, Stripe, Slack, InfoQ, Lobsters and r/LocalLLaMA (about
one request a minute); add a row when one of them joins a course.

## How this file is maintained

- New sources go under the course they serve, with the date of the newest
  post seen. A source that serves two courses is listed in both.
- A source with a feed also gets one row in the Feeds table, with the item
  count and newest date on the day it was checked. The feed is for the code
  poll; the entry above stays the place hunter reads.
- The weekly hunt adds verified names AND reports sources gone quiet; code
  merges them (`learning_pipeline.merge_roster`): a new name lands under the
  course its topic names, or under "Found by the source hunt", and a quiet
  one moves to the rejected list with its real last date.
- An article should draw on at least two sites. A course section with fewer
  than ten active sources is the next hunt's target.
- When the unread backlog drops below six, a hunt starts on its own.
- Every entry carries the date of the newest post seen.
- The owner's edits win. Cross out anything you do not want to hear from.

## Found by the source hunt

- **Anton Zhiyanov** — antonz.org · 2026-09-26 · rebuilds Go and C concurrency and allocator machinery from first principles with his own benchmark tables (mutexes, channels, pthread vs goroutine costs); newest post 'Go concurrency distilled' dated 2026-09-26, eight posts since June · performance, concurrency and the machine; also storage (SQL/SQLite deep dives) (found 2026-09-28)
- **Colfax Research** — research.colfax-intl.com · 2026-09-07 · optimization diaries with real TFLOP/s vs peak numbers, posted weekly; newest post 2026-09-07 · inference-internals and GPU performance (courses 3 and 1): Blackwell kernel internals, FlashAttention-4, GEMM (found 2026-09-28)
- **Ashwani Jha** — ashwanijha.dev/blog · 2026-08-15 · writes TTFT-vs-TPOT and chunk-size tradeoffs from his own serving cluster; 18 inference posts and 41 paper breakdowns; newest 2026-08-15 · inference-internals: LLM serving, chunked prefill, MoE economics, paper breakdowns (found 2026-09-28)
- **Soil & Silicon (Evan Carlson)** — soilandsilicon.dev · 2026-07-18 · implements, measures, and admits failures (Qwen3 pairing collapse, RNG noise across devices); newest read 2026-07-18 · inference-internals: from-scratch spec decoding, KV cache, local inference, with measured numbers (found 2026-09-28)
- **Chips and Cheese (Chester Lam, George Cozma)** — chipsandcheese.com · 2026-09-29 · Own microbenchmarks and Hot Chips 2026 teardowns of the exact silicon serving lands on; newest post 2026-09-29 · inference-internals and the machine layer: microarchitecture, accelerators, memory systems (found 2026-10-02)
- **Materialize engineering blog** — materialize.com/blog · 2026-09-29 · Engine posts like 'Replacing Swap with a Buffer Pool' carry the system's own numbers; mixed with AI-agent product posts, pick one at a time; newest 2026-09-29 · storage internals and performance: out-of-core execution, buffer pools, compression (found 2026-10-02)
- **Artificial Analysis** — artificialanalysis.ai/articles · 2026-09-30 · The standing external reference for the per-request cost lane — 116 benchmark posts, newest 2026-09-30; an org, not an essayist, so it feeds the cost alarm rather than teaching style · inference cost and latency: independent measured benchmarks across providers (found 2026-10-02)
- **Neal Krawetz — The Hacker Factor Blog** — hackerfactor.com/blog · 2026-09-22 · Reads like Arpit for security: plain language, own experiments, admits systems' failures (C2PA validator divergence, Google 'Won't Fix' story); newest 2026-09-22 · reliability and security in practice: signing protocols, PKI failure modes, earned-in-public exploit write-ups (found 2026-10-02)
- **Hazy Research blog (Stanford, Chris Ré's lab)** — hazyresearch.stanford.edu/blog · 2026-08-05 · lab writing kernel internals with own measurements (ThunderKittens 2.0, megakernel Llama-1B); named authors incl. Tri Dao; newest post 2026-08-05 · @hazyresearch · inference-internals and course 1: GPU kernels, megakernels, ThunderKittens, efficient architectures (found 2026-10-03)
- **MLC blog (mlc.ai)** — blog.mlc.ai · 2026-09-29 · XGrammar-2, TIRx compiler harness, 'Microserving LLM engines'; project team writing engine internals, newest post 2026-09-29 · @mlcaihq · inference-internals: structured generation, GPU compilation, microserving (found 2026-10-03)
- **Thinking Machines Lab - Connectionism** — thinkingmachines.ai/blog · 2026-07-31 · named-author science (Horace He, John Schulman, Kevin Lu); 'Defeating Nondeterminism in LLM Inference' is already an archive entry and the blog keeps publishing; newest post 2026-07-31 · @thinkymachines · applied AI systems and inference: nondeterminism, on-policy distillation, LoRA (found 2026-10-03)
- **Epoch AI** — epoch.ai/blog · 2026-10-02 · 'The plunging price of thought' puts a measured 47%/quarter fall on inference cost - direct fodder for the per-request cost alarm lane; an org not an essayist, hence lower score; newest post 2026-10-02 · @EpochAIResearch · inference cost and capacity: measured price-per-capability trends (found 2026-10-03)
- **Tim Dettmers** — timdettmers.com · 2026-09-21 · LLM.int8() author; 'SERA' post builds a coding agent with 32 GPUs and five researchers with real numbers, but recent posts drift toward academia/AGI essays; newest post 2026-09-21 · @Tim_Dettmers · quantization, GPU hardware for deep learning, building research agents on small compute (found 2026-10-03)
- **Chris Wellons (null program)** — nullprogram.com · 2026-09-20 · Builds the thing then explains the mechanism: concurrent atomic MSI hash tables, a custom 80286 VM to run a Win16 game, self-built code-signing infra; newest post 2026-09-20 · @skeeto · performance, concurrency and the machine; C systems craft; engineering craft with a model in the loop (found 2026-10-04)
- **Gunnar Morling** — morling.dev/blog · 2026-08-31 · First-party deep dives on replication slots, WAL bloat, KIP-932, plus a 2026 series building a fast Parquet reader; newest post 2026-08-31 · @gunnarmorling · storage internals (Postgres, Parquet), Kafka/CDC, JVM performance (found 2026-10-04)
- **Eli Bendersky** — eli.thegreenplace.net · 2026-09-30 · Mechanism essays on concurrent servers in Go and Rust, parse-don't-validate, plugin architecture; newest post 2026-09-30 (book notes; technical posts run Jun-Sep 2026) · @elibendersky · Go and Rust concurrency, compilers, engineering craft (found 2026-10-04)
- **Tailscale blog** — tailscale.com/blog · 2026-09-30 · Mixed company blog: NAT-traversal lineage and Fitzpatrick's Tailcat sit next to agent-integration news; pick posts one at a time; newest post 2026-09-30 · @tailscale · networking internals and production systems; system design (found 2026-10-04)
- **HumanLayer blog** — humanlayer.dev/blog · 2026-09-04 · Vendor but the context-engineering posts (12 Factor Agents, context forking, long-context critique) are concept-first; newest item 2026-09-04 is a resource index, not an essay · engineering craft with a model in the loop: context engineering, agent harnesses (found 2026-10-04)
- **Fabian "ryg" Giesen** — fgiesen.wordpress.com · 2026-08-25 · Mechanism-first posts with his own measured numbers (9x unary decoder speedup, footnoted micro-optimisations) from the Oodle author; newest post 2026-08-25 · performance, compression and CPU architecture: memory ordering, SIMD decoding, bitstream formats (found 2026-10-11)
- **Xe Iaso** — xeiaso.net/blog · 2026-10-04 · Builds the thing (Anubis, git-on-object-storage) then explains it plainly with real failure stories; newest post 2026-10-04; mixed with personal and game posts, pick one at a time · engineering craft with a model in the loop: Go, object storage, security and AI tooling (found 2026-10-11)
- **Jynn Nelson (jyn)** — jyn.dev · 2026-09-16 · First-person essays that argue from mechanism, not news: token economics, 'we have a year to fix security everywhere', a multi-part build-systems series; newest post 2026-09-16 · AI economics and security, build systems, software architecture (found 2026-10-11)
- **Oren Eini (Ayende @ Rahien)** — ayende.com/blog · 2026-09-09 · RavenDB engine posts read from the source (Corax posting-lists, a .NET regex concurrency slowdown with the fix) plus essays on AI-assisted code review; newest seen 2026-09-09; mixed, skip the product launches · storage and database internals; concurrency bugs; writing code with AI in the loop (found 2026-10-11)
- **Karthika Raghavan** — kraghavan.ca · 2026-10-01 · Rent-a-GPU experiment series with prices named ($17.47/$18.31 GH200 days, A100 $1.99/hr), measured results (81% KV hit rate, 16,559 reqs/0 failures) and failures reported as-is; newest post 2026-10-01 · inference-internals: renting cloud GPUs, llm-d and vLLM serving, P/D disaggregation, measured KV-cache and TTFT experime (found 2026-10-13)
- **martinuke0** — martinuke0.github.io · 2026-10-13 · Builds paged-attention engines with LRU/H2O eviction in pure Python and wrote a production-focused LLM inference roadmap (Sep 2) with correct KV math and vLLM configs; three posts dated 2026-10-13 · inference-internals: KV cache, paged attention and MoE built from scratch with the memory math shown (found 2026-10-13)
- **FlashInfer** — flashinfer.ai · 2026-09-22 · Project blog from the kernel library both engines call into; three posts dated 2026-09-22 on its v0.7 autotuner and fused expert-parallel MoE · inference-internals: kernel internals under both vLLM and SGLang — autotuning, MoE fusions, sampling kernels (found 2026-10-13)

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

- **Marc Brooker** — brooker.co.za/blog · 2026-07-29 · tail latency, Little's
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
- **Abhinav Upadhyay (Confessions of a Code Addict)** —
  blog.codingconfessions.com · 2026-06-22 · virtual memory, page tables, CPU
  basics, in plain English.
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

## Course 2 — Applied AI systems at scale · elite-applied-ai

- **Hamel Husain** — hamel.dev · 2026-08-12 · evals and error analysis.
- **Eugene Yan** — eugeneyan.com/writing · 2026-06-21 · eval design.
- **Shreya Shankar** — sh-reya.com/blog · 2026-05-21 · evals, data
  flywheels. Recheck: falls outside 120 days on 2026-09-18.
- **Simon Willison, prompt-injection tag** — simonwillison.net/tags/prompt-injection
  · 2026-08-27 · attacks, defences, links to incidents. Take his own posts
  over the link notes.
- **Sean Goedecke** — seangoedecke.com · 2026-09-10 · how engineering work
  with models actually gets done.
- **Lilian Weng** — lilianweng.github.io · 2026-07-04 · long surveys; agent
  harnesses, reward hacking.
- **Anthropic engineering** — anthropic.com/engineering · 2026-05-25 · agent
  containment, eval noise, postmortems. Borderline on the 120-day rule, kept
  for depth.
- **UK AISI blog** — aisi.gov.uk/blog · 2026-08-27 · eval method and real
  agent incident reports.
- **Temporal** — temporal.io/blog · 2026-09-15 · mixed · durable execution
  for agents.
- **Braintrust** — braintrust.dev/blog · 2026-08-24 · mixed, vendor · agent
  evals, trace storage.
- **Vespa** — blog.vespa.ai · 2026-09-13 · retrieval quality with measured
  results.
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

## Course 3 — Inference and AI platform · elite-inference, inference-internals

- **vLLM blog** — vllm.ai/blog (blog.vllm.ai redirects here) · 2026-09-15 ·
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
- **Anyscale** — anyscale.com/blog · 2026-06-18 · Ray Serve routing and
  throughput, with hardware and workload stated.
- **PyTorch blog** — pytorch.org/blog · 2026-09-16 · mixed · kernels and
  low-precision formats.
- **vLLM bug tracker** —
  github.com/vllm-project/vllm/issues?q=is%3Aissue+label%3Abug+sort%3Aupdated-desc
  · daily · real serving failures, with reproductions.
- **SGLang bug tracker** —
  github.com/sgl-project/sglang/issues?q=is%3Aissue+label%3Abug+sort%3Aupdated-desc
  · daily · the same, for a second engine.
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

## Course 4 — Storage and database internals · elite-storage

- **Phil Eaton** — notes.eatonphil.com · 2026-09-13 · WAL bugs, Postgres
  internals, data races.
- **PlanetScale** — planetscale.com/blog · 2026-09-16 · mixed · Postgres
  failures, pools, large tables. "The dangers of Postgres subtransactions".
- **Percona** — percona.com/blog · 2026-09-17 · MySQL and Postgres
  operations, measured.
- **Small Datum (Mark Callaghan)** — smalldatum.blogspot.com · 2026-06-19 ·
  benchmarks with hardware and settings stated.
- **Depesz** — depesz.com · 2026-08-25 · new Postgres features, one at a time.
- **Crunchy Data** — crunchydata.com/blog · 2026-09-02 · practical Postgres,
  migrations.
- **pganalyze** — pganalyze.com/blog · 2026-08-13 · Postgres internals read
  from the source.
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

## Course 5 — Distributed systems and verification · elite-distributed

- **Murat Demirbas** — muratbuffalo.blogspot.com · 2026-09-12 · papers read
  closely, TLA+, metastability.
- **TigerBeetle** — tigerbeetle.com/blog · 2026-09-17 · deterministic
  simulation testing, by the people who built it.
- **Antithesis** — antithesis.com/blog · 2026-08-12 · mixed · real bugs
  found. "Finding bugs in Raft implementations".
- **Jack Vanlightly** — jack-vanlightly.com · 2026-08-28 · log replication
  design, Kafka behaviour. (Not www.vanlightly.com, which does not resolve.)
- **Marc Brooker** — brooker.co.za/blog · 2026-07-19 · distributed OLTP.
  "Aurora DSQL: Scalable, Multi-Region OLTP".
- **Hillel Wayne** — hillelwayne.com/post · 2026-09-01 · formal methods.
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

## Course 6 — Reliability, security and change · elite-reliability

- **Lorin Hochstein (Surfing Complexity)** — surfingcomplexity.blog ·
  2026-09-12 · public incident reports read for the mechanism.
- **Cloudflare postmortems** — blog.cloudflare.com/tag/post-mortem ·
  2026-05-01 · global config changes; the Nov 2025 feature file, the Dec 2025
  change behind "Fail Small".
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

## Course 7 — System design and architecture · elite-system-design

- **Marc Brooker** — brooker.co.za/blog · 2026-07-29 · cost, tail latency and
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
- **Fly.io** — fly.io/blog · 2026-09-03 · infrastructure with real numbers.
- **Uber engineering** — eng.uber.com · 2026-09-11. Use this host or
  uber.com/blog/engineering; www.uber.com answers 406.
- **InfoQ presentations** — infoq.com/architecture-design/presentations ·
  2026-09-16 · case studies told by the people who run them.
- **SREcon26 Americas** — usenix.org/conference/srecon26americas/program ·
  talks, with video. "Escaping Version Skew".
- **Arpit Bhayani, video breakdowns** — arpitbhayani.me/videos · 186 videos
  with slides and notes · worked walkthroughs of real architectures.

## Engineering craft — any course

- **Julia Evans** — jvns.ca · 2026-07-21 · mechanisms from first principles.
  Recent posts are on Django and CSS; take the systems ones.
- **Thorsten Ball** — registerspill.thorstenball.com/archive · 2026-09-06 ·
  weekly · writing code well with a model in the loop.
- **Armin Ronacher** — lucumr.pocoo.org · 2026-09-07 · long-horizon coding
  models.
- **Arpit Bhayani** — arpitbhayani.me/blogs · 2026-08-21 · **the style
  reference for every lesson** — see "How his writing reads", below.

## Production incidents — the highest-value reading

Checked 2026-09-12.

- **Cloudflare outage postmortems** — blog.cloudflare.com/tag/outage/ · newest
  2026-02-21. Real root cause and the follow-up work: the Nov 2025 bot-file
  bug, the Dec 2025 config change that became their "Fail Small" programme.
- **SRE Weekly** — sreweekly.com · issue #533, 2026-09-06 · weekly. Links out
  to incident analyses across the industry; follow it to the primary report.
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
- **news.ycombinator.com/best** — high volume, low density: ~3 of 15 were
  technical. Filter hard or skip.

Always record the primary article's own URL, never the aggregator's.

## Reserve — verified active, use when a slot frees up

Martin Fowler (2026-09-17, now mostly agentic engineering) · Kent Beck
(2026-09-02) · Vicki Boykis (2026-09-01) · Philipp Schmid (2026-09-01,
hands-on agents, some API announcements) · Import AI (2026-09-07, weekly
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
2026-03-16 (kept under course 5 as an archive; check quarterly).

**Mostly marketing or off-subject** (checked 2026-09-17): Hugging Face blog ·
Modal · Turso · ClickHouse · Sentry · Railway · ByteByteGo · Baseten (no
dates) · Together · Fireworks · Character.ai · Databricks · NVIDIA Dynamo
release notes · CockroachDB · Cybertec · etcd blog (release notes) · Resonate
· S2 · Figma (own agent products) · incident.io ("best tools" lists) ·
Latacora (recent posts are AI advice) · Google Project Zero (exploits, not
service boundaries) · PhonePe · Will Larson (management) · aphyr.com (recent
posts not technical) · Jason Liu (recent posts personal; his 2025 RAG posts
stay good as archives) · OpenAI status page (no root cause) · AI Incident
Database (news, not engineering).

**Other:** Adyen — engineering URL 404s. Ethan Mollick, Zvi Mowshowitz —
not technical enough, or too much overlap with Latent Space.

## Could not verify — worth a manual look in the browser

- **Rachel by the Bay** (rachelbythebay.com/w) and **Chris Siebenmann**
  (utcc.utoronto.ca/~cks/space/blog) — both block automated fetches, both
  look active, both in the systems lane.
- **Netflix** (netflixtechblog.com), **Pinterest**, **Razorpay**,
  **Flipkart**, **Hotstar** — 403 to this system's fetcher. **Swiggy**
  (bytes.swiggy.com) — fetch failed. These are the Indian engineering blogs
  worth having; a browser check would settle them.
- **Heidi Howard** — blog URL 404. **Tri Dao** — not checked. **Restate**
  and **Modal** — pages did not render. **Datadog**, **samwho.dev**,
  **Tanya Reilly** (noidea.dog) — no dates on the page.
- **OpenAI, "Expanding on what we missed with sycophancy"** — 403.

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

## How this file is maintained

- New sources go under the course they serve, with the date of the newest
  post seen. A source that serves two courses is listed in both.
- The weekly hunt adds verified names AND reports sources gone quiet; tutor
  moves those to the rejected list with their real last date.
- An article should draw on at least two sites. A course section with fewer
  than ten active sources is the next hunt's target.
- When the unread backlog drops below six, a hunt starts on its own.
- Every entry carries the date of the newest post seen.
- The owner's edits win. Cross out anything you do not want to hear from.

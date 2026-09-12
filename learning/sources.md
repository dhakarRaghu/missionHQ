# Who to read

Re-lensed on **2026-09-12** to the four lanes in `interests.md`: applied AI
systems, enough model literacy to be useful, distributed systems and system
design, and engineering craft. Payments came off — it is his day job, not what
he reads for — and so did language-specific depth.

Every date below came from opening the page. Nothing goes on this list
unverified: the first version was seeded from memory and carried a blog whose
last post was January 2025.

**Active means a post within 90 days.**

## AI engineering and applied AI systems

- **Simon Willison** — simonwillison.net · 2026-09-12 · near-daily. Take his
  original posts over the link-notes.
- **Sean Goedecke** — seangoedecke.com · 2026-09-10 · near-daily. AI practice
  and how engineering work actually gets done.
- **Latent Space** — latent.space · daily. What shipped and why it matters.
- **Nathan Lambert** — interconnects.ai · 2026-09-11. Post-training and open
  models, from someone doing the work.
- **vLLM** — blog.vllm.ai · 2026-09-10. Serving internals: KV cache, batching,
  kernels. Nobody else here covers inference as a system.
- **Hamel Husain** — hamel.dev · 2026-08-21. Evals, the part teams skip.
- **Jason Liu** — jxnl.co/writing · 2026-08-12. Retrieval in practice.

## Model literacy — what a builder should understand, not the research

- **Sebastian Raschka** — magazine.sebastianraschka.com · 2026-09-09.
  Architecture explained for people who build on it.
- **Eugene Yan** — eugeneyan.com/writing · 2026-06-21. Applied ML and RAG.
  Borderline on the 90-day rule; recheck next hunt.

## Distributed systems and system design

- **Marc Brooker** — brooker.co.za/blog · 2026-07-29. Tail latency, queueing,
  failure under load.
- **Murat Demirbas** — muratbuffalo.blogspot.com · 2026-09-02. Distributed
  systems research, read closely and explained.
- **TigerBeetle** — tigerbeetle.com/blog · 2026-08-20. Database engineering
  and deterministic simulation testing, by the people who built it.
- **Phil Eaton** — notes.eatonphil.com · 2026-09-06. Consensus, storage,
  data races, database internals.
- **Arpit Bhayani** — arpitbhayani.me/blogs · 2026-07-05. Mechanisms from
  first principles; the model for how a lesson should read.
- **antirez** — antirez.com · ~2026-07-29. Systems, from the Redis author.
- **PlanetScale** — planetscale.com/blog · 2026-09-10. Sharding, MVCC,
  connection pools — the mechanism, not the SQL.
- **Fly.io** — fly.io/blog · 2026-09-03. Infrastructure with real numbers;
  recently on running agents on real machines.
- **Cloudflare** — blog.cloudflare.com · 2026-09-11. Deep dives only; about
  40% of the feed is product launches.
- **Meta** — engineering.fb.com · 2026-09-03. ZippyDB, RDMA, scale.
- **Uber** — eng.uber.com · 2026-09-11. NOTE: use this host. www.uber.com
  answers 406 even to a browser user agent.

## Engineering craft

- **Julia Evans** — jvns.ca · 2026-07-21. Explains mechanisms from first
  principles, which is the standard here.
- **Thorsten Ball** — registerspill.thorstenball.com/archive · 2026-09-06 ·
  weekly. Writing code well with a model in the loop.
- **Armin Ronacher** — lucumr.pocoo.org · 2026-09-07. Opinionated, currently
  on long-horizon coding models.
- **The Pragmatic Engineer** — newsletter.pragmaticengineer.com · 2026-09-10.
  What is actually happening inside engineering orgs.

That is 23 of a 25 ceiling.

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

Martin Fowler (2026-09-09, now mostly agentic engineering) · Kent Beck
(2026-09-02) · Hillel Wayne (2026-09-01, formal methods) · Antithesis
(2026-08-18, deterministic testing) · Vicki Boykis (2026-09-01) · Philipp
Schmid (2026-09-01, hands-on agents, some API announcements) · Import AI
(2026-09-07, weekly summary) · Lilian Weng (2026-07-04, long surveys) ·
Netflix (2026-08-28) · Shopify (2026-09-10) · Dan Luu (quarterly — check
like Jepsen).

## Off-lane now that payments and language depth are out

- **Stripe** — stripe.dev/blog/topic/engineering · 2026-08-26. Excellent, but
  payments is the day job. Return it only for a systems lesson.
- **Monzo, Grab, Dropbox** — same reason, or too far from the four lanes.

## Checked and rejected — do not re-add without a new date

- **Chip Huyen** 2025-01-16 · **Martin Kleppmann** 2025-12-08 · **Zerodha**
  2024-03-28 · **materializedview.io** 2025-09-11 · **avi.im** 2026-04-18 ·
  **Alex Miller** 2025-10-13 · **Andy Pavlo** 2026-01-04 · **Nelson Elhage**
  2026-03-23 · **Camille Fournier** 2026-05-31 · **Shreya Shankar**
  2026-05-21 · **Anthropic engineering** 2026-05-25 · **Brandur** 2026-05-31
  · **Jepsen** 2026-03-16 (quarterly check instead).
- **Hugging Face blog, Modal, Neon, Turso, ClickHouse, Sentry, Railway,
  ByteByteGo** — active but majority product marketing.
- **Discord** — undated release notes. **Adyen** — engineering URL 404s.
- **Justin Jaffray** — active but the newest issue announces a hiatus.
- **Ethan Mollick, Zvi Mowshowitz** — good, but not technical enough / too
  much volume overlapping Latent Space.

## Could not verify — worth a manual look in the browser

- **Rachel by the Bay** (rachelbythebay.com/w) and **Chris Siebenmann**
  (utcc.utoronto.ca/~cks/space/blog) — both block automated fetches, both
  look active on Hacker News, and both sit squarely in the systems lane.
- **Netflix** (netflixtechblog.com) and **Razorpay** — 403 to this system's
  fetcher. **Figma engineering** — JavaScript-rendered, no date visible.

Operator can open these on a feed day and report the newest post date.

## How this file is maintained

- The weekly hunt adds verified names AND reports sources gone quiet; tutor
  moves those to the rejected list with their real last date.
- When the unread backlog drops below six, a hunt starts on its own.
- Every entry carries the date of the newest post seen.
- The owner's edits win. Cross out anything you do not want to hear from.

# What I want to read

The filter for the morning run. A post has to serve one of these to be worth
my hour. Good is not enough — it has to be good FOR ME.

This file is mine to edit. Add a line, cross one out, and the next morning
uses it.

## What most days are for (from 2026-10-06)

Only Tuesday is about my course. The other days are about the world around
it, because articles tied only to the course were not interesting or useful
to me:

- **How companies built real products.** Engineering write-ups of how a team
  built, scaled or rebuilt something people use: the first design, why it
  stopped working, what they changed, the numbers before and after.
- **System design stories and engineering decisions.** Why a team chose X
  over Y, what it cost them, and what happened after.
- **What is new in AI.** New tools and models worth trying, shown by someone
  who used them on real work; changes in AI developer tools; optimisations
  people made to AI systems, with numbers; new techniques with a working
  example. A tool counts when someone used it for real, never a "top 10" list.

## 0. How production systems actually fail — first on my course day

Incidents, postmortems, outage reports, and "what we changed afterwards"
writeups. What broke, what the first symptom looked like, which theory was
wrong, what actually located it, what fixed it, and what changed so it could
not recur.

On my course day this outranks every subject below. A good postmortem
teaches the mechanism and the failure mode at the same time, and it is
already paid for out of someone else's bad night. If one exists on the
subject I am working through, that is the course day's reading. On the other
days it is welcome, but it does not outrank what the day is for.

## 1. AI engineering and applied AI systems — the main thing

- Agents that do real work: tool use, orchestration, multi-agent systems,
  approval and safety boundaries, what actually fails in production.
- Retrieval: embeddings, chunking, hybrid search, reranking, and how to tell
  whether retrieval is the thing that is broken.
- Evals: measuring whether an LLM system works, and what to do when it stops.
- Serving and inference as systems: KV cache, batching, caching, routing,
  quantization, where the latency and the money actually go.
- Context engineering as engineering rather than folklore.

## 2. Enough about models to be literate — not the research

What a working engineer should understand about how models behave: attention
and context windows, why long context degrades, what fine-tuning and
distillation buy and cost, why a model regresses after an update.

**Not** the research layer: new loss functions, benchmark chasing,
architecture papers that change nothing downstream. If a paper changes what I
would build, it counts. Otherwise it does not.

## 3. Distributed systems

Consistency and consensus, replication, partitioning, idempotency and
exactly-once, queues and backpressure, tail latency, failure under load,
what breaks at scale and why. Databases count here when the post is about the
mechanism rather than the SQL.

## 4. System design

Architecture with real numbers behind it: how a system at scale is actually
put together, the tradeoffs someone made and regretted, capacity and cost,
how data moves through a company's stack. Write-ups from teams who ran it in
production, not diagrams from a course.

## 5. Better engineering

Testing, debugging, observability, incident analysis, reading someone else's
system, and how all of that changes with a model in the loop — what to
delegate to it and what never to. Tooling that changes how the work is done.

## Not for me

- **Payments as a subject.** It is my day job, not what I read for. A payments
  post counts only when the lesson is a systems lesson that happens to be set
  in payments.
- **Language-specific depth.** I am not reading for Python, Go or Rust
  tutorials. Language material counts only when the point survives the
  language.
- Frontend, CSS, React, mobile UI. Crypto and web3.
- ML research theory with no path to practice.
- Management, hiring, leadership and career advice. I am an engineer, early
  career, and I want the engineering.
- Motivational content, "X lessons from Y years", listicles, "top 10 tools",
  productivity systems.
- Vendor launch posts and anything whose real point is to sell a product.
- Introductions to things I already do: what is an API, what is Docker, what
  is an LLM.

## The test

Would I change something in how I build, or understand something I did not
understand this morning? If the honest answer is no, it does not go on the
list, however well written it is.

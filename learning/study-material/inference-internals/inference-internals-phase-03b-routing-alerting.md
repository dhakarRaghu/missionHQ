# Phase 3B — Routing, batch, and the cost alarm

Part A made your bill smaller. Part B is about spending the savings well, and about keeping them.

Two questions remain from earlier phases. Phase 0's Story 3 was a team that switched everything to a cheap model, lost quality, and had only two options left: expensive everywhere or cheap everywhere. Section 3.4 builds the third option and, more importantly, teaches you to prove it works. Phase 0's Story 1 was a team that lost a cache for four months without noticing. Section 3.5 is the detector that would have caught it in ten requests.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  3.4  Routing cascades and     — quality per dollar, and the control     │
│       batch APIs                 group that most write-ups skip          │
│  3.5  Per-request cost         — the detector Story 1 needed, and why    │
│       alerting                   every enforcement control is late       │
└──────────────────────────────────────────────────────────────────────────┘
```

Part A is a prerequisite. This document uses `pricing.py` and the five token classes without re-explaining them.

Time: 1.5 to 2 hours. Both scripts in this part run with no API key.

---

## 3.4 — Routing cascades (quality per dollar, and the control group)

Why this matters: Phase 0's Story 3 was a team that switched everything to a cheap model, lost quality, and had only two options left. This section builds the third option and, more importantly, teaches you to prove it works.

### Two shapes, and the arithmetic that separates them

```
CASCADE — decide AFTER the cheap model answers

   query ──► cheap model ──► signal says "unsure"? ──yes──► deep model ──► answer
                   │                   │
                   └── no ─────────────┴──────────────────────────────► answer

   cost = cheap x every query + deep x escalated queries


ROUTER — decide BEFORE anyone answers

   query ──► classifier ──┬── easy ──► cheap model ──► answer
                          └── hard ──► deep model ──► answer

   cost = cheap x easy queries + deep x hard queries + classifier
```

Read the two cost lines again. A cascade pays the cheap model for **every** query, including the ones it then escalates. Those queries are billed twice. A router pays once.

That is not a detail. A 2026 decision-theoretic study across five benchmarks and eight models found that a lightweight pre-generation router beat the best cascade policy on four of the five datasets. Its stated cause is exactly this arithmetic: the router "avoids the cheap model's generation cost on queries sent directly to a larger model rather than because of a stronger routing signal". The paper concludes that cascade performance is limited primarily by structural cost.

So the cascade's advantage is not price. It is that the escalation signal can look at the cheap model's actual answer, which a pre-generation classifier cannot.

**The break-even, as arithmetic you can do on paper.** Let `e` be the fraction of queries you escalate, `Cc` the cheap cost, `Cd` the deep cost.

```
cascade cost   = Cc + e x Cd          per query
deep-only cost = Cd                   per query

the cascade is cheaper when     Cc + e x Cd  <  Cd
                                e  <  1 - Cc/Cd
```

With the course price sheet, `gpt-4.1` input costs 5x `gpt-4.1-mini`. Put the ratio at roughly 1/5 and the cascade stops saving money once you escalate more than about 80% of queries. That ceiling is generous. The real constraint is quality, not the ceiling.

### The control group nobody runs

Here is the experiment that decides whether your cascade is real.

Run your cascade. Record the escalation rate. Then run a second configuration that escalates **the same number of queries, chosen at random**. If your cascade does not beat that, your signal carries no information and you are paying escalation costs for noise.

`cascade_lab.py` runs both, plus the two single-model baselines:

```
python phase03_economics/cascade_lab.py --simulate
```

Output on this machine, averaged over 300 trials of 20 items:

```
┌──────────────┬──────────┬────────────┬───────────┬────────────────┐
│ strategy     │ accuracy │ escalated  │ cost      │ $ per correct  │
├──────────────┼──────────┼────────────┼───────────┼────────────────┤
│ cheap-only   │    75.0% │     0/20   │ $ 0.00288 │      $0.000192 │
│ deep-only    │    90.0% │    20/20   │ $ 0.01440 │      $0.000800 │
│ cascade      │    90.0% │     8/20   │ $ 0.00892 │      $0.000495 │
│ random       │    80.0% │     8/20   │ $ 0.00892 │      $0.000557 │
└──────────────┴──────────┴────────────┴───────────┴────────────────┘

signal quality 0.85: the cascade beats the random control by +7.2 accuracy
points on average (standard error 0.41; one trial varies by 7.2).
That is 17 standard errors from zero, so the signal carries real information.
cascade keeps 96.4% of deep-only accuracy for 61.9% of the deep-only cost.
```

Now break the signal and keep everything else:

```
python phase03_economics/cascade_lab.py --simulate --signal-quality 0.5
```

```
signal quality 0.50: the cascade beats the random control by +0.4 accuracy
points on average (standard error 0.43; one trial varies by 7.4).
That is inside two standard errors of zero.
```

Look at what did **not** change. The cascade still shows a respectable accuracy and a lower cost than deep-only. A dashboard with only those two columns would call this a success. Only the control row exposes it.

**The headline metric is dollars per correct answer.** Cost alone rewards a system that is cheap and wrong. Accuracy alone rewards a system that is expensive and slow. The ratio is the only number that moves in the right direction for both.

### Which escalation signal actually works

This is where most implementations pick by intuition. There is measured evidence now, and the ranking is not what people assume.

```
┌────────────────────────────┬──────────────────────────────────────────────┐
│ signal                     │ what the measurements say                    │
├────────────────────────────┼──────────────────────────────────────────────┤
│ cross-model agreement      │ Strongest. Different models make different   │
│ (a jury)                   │ mistakes, so wrong answers scatter and the   │
│                            │ right one accumulates agreement. Costs       │
│                            │ several models per query.                    │
│ calibrated token-level     │ Works, with work. One production study cut   │
│ confidence                 │ calibration error from 0.12 to 0.03 using     │
│                            │ isotonic regression, then cut cost 31% while │
│                            │ holding micro-F1 at 0.91 over 75,000 queries.│
│ self-reported confidence   │ Varies enormously BY MODEL. Measure yours.   │
│                            │ See the warning below.                       │
│ self-consistency: sample   │ Weakest. Correlation with correctness of     │
│ one model many times       │ only 0.20 to 0.59, and worst on the best     │
│                            │ models.                                      │
│ an uncalibrated score at a │ This is the folklore, and it is what most    │
│ hand-tuned threshold       │ shipped cascades use.                        │
└────────────────────────────┴──────────────────────────────────────────────┘
```

**The self-consistency result is worth stating precisely, because it is the trap.** A 2026 audit ran 53 configurations, 50 samples each, 265,000 samples total, on GPQA Diamond and AIME. On GPQA, a frontier model reached an agreement level of 0.8 or higher on 77% of entries. **48% of those high-agreement answers were wrong.** A cascade using self-consistency as its stopping rule would have accepted nearly all of them and escalated none.

The paper's own framing is that self-consistency is a conditional signal, not a standalone one.

**And this explains why a jury beats resampling.** Sampling one model 50 times reproduces that model's own systematic mistakes 50 times. Different models do not share all of the same mistakes. If you are going to spend extra calls on a confidence signal, spend them on different models rather than on more samples from one.

**The self-reported confidence warning.** A 2026 calibration benchmark scored 15 frontier models with the Brier score, where lower is better. The best models scored 0.103. A calibrated-random baseline scores 0.1875. At least one shipped model scored 0.367, which is roughly twice as bad as guessing. The study also found that the most accurate model is not the best calibrated.

Read that as an engineering rule. If you put a badly calibrated model at tier one and trust its self-reported confidence, you have built a random escalator that costs money. That is precisely the `--signal-quality 0.5` row you just ran.

### The two failure modes, both measured

**Under-routing: the router sends a hard query to the cheap model, and nothing tells you.** A January 2026 benchmark re-ran 10 routers over 400,000 instances from 21 datasets and 33 models. On the subset of queries that at most three of the expert models could answer correctly, which was 410 queries or 11.9% of the test set, two leading routers scored 24.6% and 23.2%. Routers are weakest exactly where the routing choice matters most, and strongest where any model would have done.

The same benchmark measured a commercial routing product at **minus 24.7%** against simply always using the best single model.

Nothing in either system raises an error. The answer comes back looking normal.

**Over-routing: the router quietly sends everything to the expensive model.** A February 2026 paper names this routing collapse: as the budget rises, routers select the most powerful model even when a cheaper one was already correct. It proposes a metric you can compute on your own traffic, the Routing Collapse Index, defined as the fraction of queries where the router makes a dominated choice or misses a strictly cheaper model that would have been right. Take that metric even if you take nothing else from the paper.

### The number to put on a dashboard

The routing literature converged on a metric that answers an engineer's question directly. It is called the call-performance threshold, written CPT. It is the minimum percentage of calls to the strong model needed to reach a chosen quality level.

Phrase your goal that way and the whole problem becomes tractable: "hold 95% of deep-only quality" is the target, and CPT tells you what fraction of traffic that costs. In the original router paper, one configuration hit 95% of the strong model's performance on one benchmark using 26% strong-model calls, and a better-trained version reached the same quality at 14%.

**State the benchmark with every routing number you quote.** The same routers in that paper delivered a 3.66x cost saving on an open-ended chat benchmark, 1.41x on a knowledge benchmark, and 1.49x on a maths benchmark. The last one was at 87% quality retained, not 95%. A single "up to" figure from that paper, quoted without its benchmark, is close to meaningless.

### What production actually looks like

Two deployments report both cost and quality, which is the minimum bar for believing a routing claim.

An interactive agentic-coding cascade reported 45.8% lower cost and a median latency of 2,026ms against 3,698ms, with no measured quality regression. Its honest limit is scale: 125 requests and a 20-task benchmark, where the reported quality gap is a difference of one task.

An offline annotation pipeline reported over 150 million annotations across six use cases, where cascading was approximately accuracy-neutral and halved compute cost. Its conclusion is the one to carry with you: fine-tuning drove their accuracy and cascading drove their cost. Cascading did not improve quality and was not asked to. The condition to state is that this is offline batch work with fine-tuned classifiers and loose latency requirements.

**And here is a claim you should reject.** A widely shared engineering post reports a monthly bill falling from $47,000 to $11,000 with a 74% primary resolution rate. It publishes no traffic volume, no quality metric, no threshold value, and no quality score. It says quality "held steady" and gives no number. That post is a story, not evidence. Use the same filter on every routing claim you read, including the ones in this document.

### Gating the swap

A model change is a deploy, and it deserves the same treatment as a code deploy. The clearest published process comes from a vendor telling customers to measure the vendor's own router against their current model before adopting it. Four steps carry most of the value:

1. **Name the decision first**, and set acceptance criteria on four dimensions rather than one: quality, cost per request, latency including a tail percentile, and policy constraints such as permitted models and regions.
2. **Baseline against your current production model**, not a leaderboard, and group prompts by category so an aggregate number cannot hide a regression in one category.
3. **Control for position bias.** Run every pairwise judgement twice with the response order swapped. Agreement in both directions is a verdict; disagreement is a tie. Skipping this inflates whichever answer you show first.
4. **Report a confidence interval**, and respect the sample-size guidance: fewer than 30 prompts is directional only, 100 to 500 is good, and a category with fewer than 5 prompts has high variance.

Steps 3 and 4 are the ones teams skip, and they are the two that decide whether your result is real. You already met step 4's lesson in exercise E14, where a single 20-item trial swung by about 7 accuracy points.

Then watch live traffic before a full rollout: quality per category, real cost, median and tail latency under real concurrency, error and failover rates, and which model actually got selected.

**The sentence to remember:** a cascade is only real if it beats a random control that escalates the same number of queries, and the escalation signal is the part that has to be measured, not assumed.

**The trap:** self-consistency feels like a confidence measure and behaves like one only on weak models. On a frontier model, high agreement was wrong 48% of the time in the 77% of cases where agreement was high.

**Try this now:** run `python phase03_economics/cascade_lab.py --simulate --signal-quality 0.65` and find the point where the gap against the random control stops being convincing. Write the number down. That is the minimum signal quality your production cascade has to clear.

### Batch APIs, the third lever

A batch API trades latency for a flat discount. Both major providers price it at **50% of the synchronous rate**, on input and output.

```
┌──────────────────────┬─────────────────────────┬──────────────────────────┐
│                      │ OpenAI Batch            │ Anthropic Message Batches│
├──────────────────────┼─────────────────────────┼──────────────────────────┤
│ discount             │ 50%                     │ 50%                      │
│ completion window    │ 24h, the only value     │ most within 1 hour,      │
│                      │                         │ expires at 24 hours      │
│ size limit           │ 50,000 requests or      │ 100,000 requests or      │
│                      │ 200 MB                  │ 256 MB                   │
│ on timeout           │ batch expires, finished │ expired requests are     │
│                      │ requests are returned   │ NOT billed               │
│                      │ and billed              │                          │
│ results kept         │ not stated on the page  │ 29 days                  │
│ stacks with caching  │ not documented          │ yes, stated explicitly   │
└──────────────────────┴─────────────────────────┴──────────────────────────┘
```

Use it for work with no user waiting: evaluation runs, backfills, nightly classification, and dataset labelling. Module 11's eval suites are the obvious candidate, and halving that bill is usually the easiest money in the whole phase.

**The one thing a batch API breaks.** You cannot reserve a budget for a batch job before submitting it. The request carries a file reference, not the prompts, so nothing downstream can price the workload at submission time. Every budget system has this hole, including the one in section 3.5. Price batch jobs from the output file after the fact, and cap them by size instead.
---

## 3.5 — Per-request cost alerting (the detector Story 1 needed)

Why this matters: everything before this section makes your bill smaller. This section makes it stay smaller. Savings you cannot monitor are savings you will lose without noticing.

Return to Phase 0, Story 1. A team shipped an agent with an 18,000-token system prompt. A timestamp sat near the top. The cache never matched. They paid full input price on every step for four months.

Ask the useful question. What would have caught it?

**Not a monthly bill.** The provider invoice arrives after the month, and it mixes every route, every tenant, and every experiment. Four months is what that looks like.

**Not a token dashboard.** This is the part that surprises people, so slow down here. When the cache breaks, the token COUNT does not change. The same prompt goes over the wire. Only the billing class changes, from cached to uncached. A dashboard of input tokens per request draws a perfectly flat line through the entire incident.

```
WHAT THE TOKEN DASHBOARD SAW          WHAT THE INVOICE DID
  tokens/request                        $/request
    ▲                                     ▲
    │  ────────────────────────           │           ┌──────────────
    │                                     │           │
    │                                     │───────────┘
    └────────────┬───────────► time       └───────────┬──────────► time
              the break                            the break
```

**Not a per-request budget alone.** No single request was extreme. Each one cost about three times what it should, which is far below any threshold you would set to avoid false alarms. A rule that only catches outliers cannot catch uniform damage.

### The three rules, and what each one is for

`budget_guard.py` implements all three and writes an append-only ledger, one JSON object per request.

```
┌───────────────────┬─────────────────────────────┬─────────────────────────┐
│ rule              │ fires when                  │ what it tells you       │
├───────────────────┼─────────────────────────────┼─────────────────────────┤
│ per-request       │ one call costs more than    │ a runaway single        │
│ budget            │ its route's budget          │ request. Catches loops  │
│                   │                             │ and giant contexts.     │
│ rolling cost      │ the recent window mean rises │ THAT cost went up.      │
│                   │ above a baseline multiple   │ Not why.                │
│ cache hit floor   │ the cached share of input   │ WHY cost went up.       │
│                   │ tokens falls below a floor  │ This is Story 1's rule. │
└───────────────────┴─────────────────────────────┴─────────────────────────┘
```

Run the replay of Story 1:

```
python phase03_economics/budget_guard.py --simulate
```

The cache breaks at request 50. Output on this machine:

```
  request    1: cost $0.002360  hit rate 98%
  request   49: cost $0.002360  hit rate 98%
  request   50: cost $0.007760  hit rate 0%
  request  200: cost $0.007760  hit rate 0%

alerts:
  rolling_cost   request   54  spend at detection $0.1544
  cache_floor    request   59  spend at detection $0.1932
```

Cost per request jumped 3.3x at the break. Both rules fired within ten requests. Four months became seconds.

### The result that should bother you

Look at that output again. The cache rule fired at request **59**. The rolling-cost rule fired at **54**, five requests earlier. The rule designed to catch this fired second.

That is not a law of nature. It is a tuning mistake, and it is in the default settings on purpose so that you find it.

The default floor is 50%. The system's normal hit rate is 98%. A window average has to fall a very long way to cross a floor set that far below normal. Tighten it:

```
python phase03_economics/budget_guard.py --simulate --cache-floor 0.90
    cache_floor fires at request 51

python phase03_economics/budget_guard.py --simulate --cache-floor 0.90 --window 5
    cache_floor fires at request 50
```

One request after the break.

**The rule: set the floor just under your measured normal, not at a round number.** A threshold chosen for how it reads in a config file detects nothing. Measure your hit rate for a week, then put the floor a few points below it.

### Two design decisions in the guard worth stealing

**Each rule fires once per run.** A rule that pages on every request is a rule your on-call engineer mutes, and a muted rule detects nothing. The guard records the first firing with the request index and the spend at that moment, then stays quiet.

**The first full window sets the baseline, which is an assumption you must question.**

```python
if self.baseline_cost is None:
    # If the system was ALREADY broken when the process started, this bakes
    # the broken cost in as normal, and the rolling rule can never fire.
    self.baseline_cost = avg
    return
```

That comment is in the shipped code because it is a real failure. A guard that learns its baseline at startup will happily certify a permanently broken system as healthy. The fix in production is to store the baseline outside the process, next to your price sheet, and to alert on a deploy that changes it.

**The guard never blocks a request.** Blocking on cost is a product decision, and it belongs at the call site where you know whether the user is mid-conversation. The guard's only job is to make cost visible at the moment it happens.

### What to record per request

The ledger the guard writes is the minimum useful schema. Every field earns its place:

```json
{"i": 50, "ts": 1789..., "route": "agent_step", "model": "gpt-4.1-mini",
 "cost": 0.00776, "naive_cost": 0.00776,
 "uncached_in": 18400, "cached_in": 0, "cache_write": 0, "out": 250,
 "cache_hit_rate": 0.0}
```

- `route` separates a chat turn from a summarisation call from a batch job. Without it, one route's regression hides inside another route's average.
- `cached_in` next to `uncached_in` is the whole point. One number without the other tells you nothing.
- `naive_cost` beside `cost` keeps the Phase 1 formula visible, so you can always show what caching is worth.
- `cache_hit_rate` is stored, not derived at query time, so an alert can be a simple threshold on a column.

**The sentence to remember:** measure cost per request and cache hit rate per request, because the failure that costs the most money does not change your token count at all.

**The trap:** a threshold set to a round number instead of to your measured normal. A 50% cache floor on a system that normally runs at 98% is not a detector. It is decoration.

**Try this now:** run `python phase03_economics/budget_guard.py --simulate --no-cache-rule` and confirm which alert is left. Then open `/tmp/budget_ledger.jsonl` and compute the spend before and after the break yourself.

### Alerting is not enforcing, and enforcing is harder than it looks

The guard you just ran reports. It does not stop anything. Stopping is a separate problem, and it has a property that decides your whole design.

**Every cost control in production is enforced against spend that is already out of date.** That is not a criticism of any one product. It is structural, and the vendors say so in their own documentation.

```
┌──────────────────────┬──────────────────────┬──────────────────────────────┐
│ system               │ when it checks       │ its own published caveat     │
├──────────────────────┼──────────────────────┼──────────────────────────────┤
│ a gateway that       │ BEFORE the call      │ it must guess the output     │
│ reserves budget      │                      │ size when max_tokens is      │
│                      │                      │ absent                        │
│ a gateway that       │ after the call       │ "a burst of concurrent       │
│ tracks spend         │ completes            │ requests can briefly exceed  │
│                      │                      │ the limit"                   │
│ provider spend       │ provider side        │ "Enforcement is not          │
│ limits               │                      │ instantaneous"               │
│ one API gateway      │ one request behind   │ cost "is only reflected      │
│                      │                      │ during the next request"     │
│ a provider spend     │ reporting only       │ period-to-date spend is      │
│ report               │                      │ "informational, not          │
│                      │                      │ transactional"               │
│ cloud budget actions │ invoice time         │ actions "fire after the      │
│                      │                      │ money is spent"              │
└──────────────────────┴──────────────────────┴──────────────────────────────┘
```

Read the first row again. Only a pre-call reservation can stop spend before it happens, and it has to estimate.

### The reservation pattern, which is the one good answer

You cannot know the output size before the call. Section 3.5's earlier rule still applies: you meter after. But you can bound it.

```
1. read max_tokens from the request. If absent, use the model's configured limit.
2. price the WORST CASE: full input + max_tokens of output.
3. reserve that amount against the budget.
4. if the reservation would exceed the budget, reject BEFORE calling the provider.
5. after the response, replace the reservation with the actual cost.
```

That is the mechanism one open-source gateway documents, and it is worth copying because it converts an unpredictable quantity into a bounded one. It also explains why `max_tokens` is not optional in a cost-controlled system. Without it, step 1 falls back to the model's maximum, and your reservation becomes so large that legitimate requests get rejected.

**Do not reach for output-length prediction instead.** The research is clear that it is not accurate enough for billing. The seminal work reports a mean error of 63 words and an accuracy-within-50-words of 56%, meaning 44% of requests land more than 50 words from the prediction. Recent work reports a mean absolute error of roughly 93 to 103 tokens. On a 200-token answer that is a 50% cost error. Prediction is good enough to schedule with and not good enough to bill with.

### Three responses to a breach, not two

Most designs consider alert or hard stop. There is a third, and it is often the right one for a user-facing product.

```
┌────────────┬──────────────────────────────────┬──────────────────────────┐
│ response   │ what the caller sees             │ use it when              │
├────────────┼──────────────────────────────────┼──────────────────────────┤
│ alert      │ nothing. Traffic continues.      │ you need a human to      │
│            │                                  │ decide                   │
│ hard stop  │ an error, typically HTTP 429     │ the spend is not yours,  │
│            │ with a specific error code       │ such as a free tier      │
│ degrade    │ a normal answer, produced by a   │ a paying user is         │
│            │ cheaper model. No error at all.  │ mid-conversation         │
└────────────┴──────────────────────────────────┴──────────────────────────┘
```

The third one is a documented gateway feature: when a key crosses its per-model budget, requests are served by a cheaper model without any budget error reaching the caller, and the spend attributes to the fallback model. It is section 3.4's cascade, triggered by money rather than by difficulty.

**The trade is honest and you should state it to your product team.** A silent downgrade protects the conversation and hides a real event from the user. Log it loudly even though the caller never sees it.

### The question nobody documents: what happens mid-stream

A budget can be crossed while tokens are already streaming. At that point the HTTP 200 was sent long ago, so a breach cannot be an HTTP status.

Across the gateways and providers checked on 2026-09-12, exactly **one** documents the behaviour: the error arrives as a stream event carrying `finish_reason: "error"`, while a breach before the stream starts returns HTTP 402. Everyone else is silent.

That silence is the finding. If your design depends on stopping a stream when a budget is crossed, you are depending on undocumented behaviour. Test it against your own provider before you promise it.

### What the providers will and will not do for you

```
┌──────────────────────┬───────────────────────────────────────────────────┐
│ capability           │ reality on 2026-09-12                             │
├──────────────────────┼───────────────────────────────────────────────────┤
│ hard org-level cap   │ exists on one provider: monthly interval only,    │
│                      │ USD only, org or project scope. A blast-radius    │
│                      │ limit, not a budget system.                       │
│ per-user or          │ not offered for application traffic. One          │
│ per-tenant cap       │ provider's spend-limit API covers enterprise      │
│                      │ seats, meaning humans, not your API keys.         │
│ cost reporting       │ daily buckets only, on both providers             │
│ granularity          │                                                   │
│ reporting lag        │ one provider documents about 5 minutes for token  │
│                      │ data. The other documents no reporting lag at all.│
└──────────────────────┴───────────────────────────────────────────────────┘
```

**The conclusion is forced.** Daily-granularity cost data cannot drive a per-request or per-minute alert. Per-tenant budgets do not exist provider-side. So you meter locally, enforce locally, and reconcile against the provider's daily report. That reconciliation is not optional bookkeeping. It is the only control that catches a provider-side billing bug, and those happen: one publicly reported case had a model billing 466,818 output tokens against 21,064 actually generated, under a configured cap of 128,000.

### There is no standard for this yet

If you were hoping to adopt a standard schema and move on, read this first. The OpenTelemetry generative-AI conventions define token attributes for input, output, cache reads, cache writes and reasoning. As of a commit dated 2026-09-10 they define **no cost attribute at all**. Every one of the 118 attributes is marked development stability, and the repository has no released version.

A cost convention exists only as an open pull request proposing `gen_ai.usage.cost.amount`, `gen_ai.usage.cost.currency` and `gen_ai.usage.cost.source`. That last field is the interesting one: it distinguishes a cost the provider returned from one you computed. Adopt those names now and your migration is free later.

Two practical warnings from the same source. The attribute for cache writes is `gen_ai.usage.cache_write.input_tokens`, and anything citing `cache_creation` as an OpenTelemetry name is stale. And the standard token metric carries only an input-or-output dimension, with nothing for cache reads or writes, so **you cannot compute spend from that metric when caching is on**. Use span attributes.

### The honest state of the evidence

One more thing shapes how much to trust anything you read here.

**No company has published a first-party postmortem of an LLM cost spike with a stated time to detect.** A search across many well-known engineering blogs found none. What exists instead is individual bug reports, community self-reports, vendor announcements, and journalism. The large dollar figures that circulate, including a widely quoted $47,000 incident, trace back to posts with no first-party source and details that contradict each other.

The nearest primary account comes from a research organisation disclosing a security incident: roughly $600,000 of API credits consumed over about three weeks by an exposed internal application. Its three stated reasons for the detection gap are the same three most teams have:

1. The anomaly looked normal. High token volume was routine there.
2. The dashboard did not show the signal, in that case rate-limited requests.
3. Nothing could stop it. The credits were free, so no spend ceiling existed.

A 2026 catalog paper that screened 167 candidate incidents and retained 63 across 21 frameworks reaches its conclusion in one sentence: it found no case where a budget overrun was prevented before a user paid for it. Its largest cause clusters are retry loops and missing cost observability.

**Read that as your mandate.** The detector in this section is not a nice addition. It is the only thing that shortens the gap between a mistake and the discovery of a mistake.

---

## 🧪 Hands-on lab — part B

Every exercise here runs offline. There is no API key needed and nothing to spend.

- [ ] **E9 (offline).** Replay Story 1 and time the detection.
  - Run: `python phase03_economics/budget_guard.py --simulate`
  - Expected: cost per request jumps from $0.002360 to $0.007760 at request 50. The rolling-cost rule fires at 54 and the cache rule at 59.
  - Write down the spend at detection for each rule.
  - Teaches: per-request metering turns a four-month incident into a ten-request incident.

- [ ] **E10 (break-it, offline).** Prove the default threshold is badly chosen.
  - Run: `python phase03_economics/budget_guard.py --simulate --cache-floor 0.90`, then add `--window 5`.
  - Expected: the cache rule moves from request 59 to 51, and then to 50.
  - Now the real exercise: explain in one sentence why a 50% floor is nearly useless on a system whose normal hit rate is 98%.
  - Teaches: a threshold must come from your measured normal, not from a round number.

- [ ] **E11 (break-it, offline).** Remove the rule that diagnoses the cause.
  - Run: `python phase03_economics/budget_guard.py --simulate --no-cache-rule`
  - Expected: only `rolling_cost` fires. You now know cost went up and nothing about why.
  - Then answer: name two unrelated changes that would also trip `rolling_cost`, and say how you would tell them apart with the ledger alone.
  - Teaches: an alert that reports a symptom still needs a second signal that reports a cause.

- [ ] **E12 (offline).** Build a cascade and run the control group.
  - Run: `python phase03_economics/cascade_lab.py --simulate`
  - Expected, averaged over 300 trials: the cascade keeps 96.4% of deep-only accuracy for 61.9% of the deep-only cost, and beats the random control by about +7.2 accuracy points at 17 standard errors from zero.
  - Teaches: dollars per correct answer is the metric. Cost alone rewards a system that is cheap and wrong.

- [ ] **E13 (break-it, offline).** Destroy the signal and watch the cascade become theatre.
  - Run: `python phase03_economics/cascade_lab.py --simulate --signal-quality 0.5`
  - Expected: the gap against the random control falls to about +0.4 points, inside two standard errors of zero. The cascade still looks fine on the accuracy and cost columns alone.
  - Then run `--signal-quality 0.65` and find where the gap becomes convincing.
  - Teaches: a cascade with an uncalibrated signal is a random escalator with a good story. Only the control group reveals it.

- [ ] **E14 (offline).** Find out how badly one run can mislead you.
  - Run: `python phase03_economics/cascade_lab.py --simulate --trials 1 --signal-quality 0.5` three times with `--seed 1`, `--seed 2`, `--seed 3`.
  - Expected: the cascade-versus-random gap swings wildly, because one trial of 20 items varies by about 7 accuracy points.
  - Teaches: the eval sets you will build in Module 11 are small, and small sets lie. Report the spread with every number.

---

## 🔍 Check it yourself — questions against the course code

1. Open `phase03_economics/budget_guard.py` and find `_fire`. It records each rule at most once per run. Explain the operational reason for that in one sentence, and name what the method stores alongside the rule so that a later reader can price the incident.

2. In the same file, find where `self.baseline_cost` is set for the first time. Read the comment above it. Describe the exact starting condition under which the rolling-cost rule can never fire, and say where the baseline would have to live to fix it.

3. Open `phase03_economics/cascade_lab.py` and find the line that computes `cascade_cost`. It adds the cheap cost for every item and the deep cost only for escalated ones. Explain which real-world property of a cascade that single line encodes, and name the architecture that avoids it.

4. In any repository you own that calls an LLM in a loop: find the loop. Answer two questions. Is there a hard cap on the number of iterations? Is there any per-request or per-session budget check before the call goes out? If both answers are no, compute the worst case by multiplying your iteration count by your `max_tokens` and your output price.
---

## ✅ Checkpoint 3B — answer in your own words

1. Design it, with the control group. You want to cut spend on a classification workload by routing. Design the experiment that decides whether to ship it. Cover: the four configurations you run, the metric you rank them by, the control group and why it exists, how many items you need before you believe the result, and the one thing you will do to stop an LLM judge from favouring whichever answer you show first.

2. A colleague says: "I set a hard spend limit with our provider, so a runaway loop cannot cost us more than the cap." Give three reasons this is not true. One reason is about the interval, one is about scope, and one is about timing. Then name the one control that would actually bound the damage from a retry loop, and where it has to live.

3. Show the math. Your cheap model costs $1.00 per million input tokens and your deep model costs $5.00, with the same token volumes either way. (a) Derive the escalation rate above which a cascade costs more than sending everything to the deep model. (b) Your measured escalation rate is 35%. Compute the cascade's cost as a fraction of deep-only. (c) A pre-generation router with the same 35% hard-query rate would cost how much? (d) Explain the gap between (b) and (c) in one sentence.

4. This is broken. Your cascade shows 88% accuracy at 55% of deep-only cost, and your team wants to ship it. The escalation signal is the cheap model's self-reported confidence. (a) Name the one experiment that must run before shipping, and what result would block the ship. (b) Give the measured evidence that self-reported confidence can be worse than useless. (c) If the experiment shows the cascade matching the control, name two things you could change rather than abandoning routing.

5. Walk me through what happens. A user is mid-conversation on your product when their tenant crosses its monthly budget, and tokens are already streaming back. (a) Explain why this cannot be signalled with an HTTP status code. (b) State what the documentation says will happen, and how confident you should be. (c) Choose between a hard stop and a silent downgrade for this case, and justify it in one sentence. (d) Name the thing you must log either way.

6. A colleague proposes: "We will predict each request's cost before the call and reject anything over budget." (a) Explain the part of that plan that cannot work, with a number. (b) Describe the mechanism that does work instead, in four steps. (c) Name the request parameter that mechanism depends on, and say what happens when a caller omits it. (d) Name the one request type this mechanism cannot price at all, and why.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. Run cheap-only, deep-only, cascade, and a random control that escalates the same number of items chosen at random. Rank by dollars per correct answer, because cost alone rewards being cheap and wrong. The control exists because a cascade with a useless signal still shows respectable accuracy and lower cost than deep-only, and only the control exposes it. On sample size, published guidance treats under 30 prompts as directional only and 100 to 500 as good, and a 20-item trial was measured swinging about 7 accuracy points, so average over repeated trials and report the standard error. For position bias, run every pairwise judgement twice with the order swapped and count a verdict only when both orders agree.

2. First, the interval: the documented cap is monthly, so a loop can spend a month's budget in an hour and stay inside it. Second, the scope: the cap is organisation or project wide with no per-tenant or per-route dimension, so one broken job removes access for everyone when it trips. Third, the timing: the provider states enforcement is not instantaneous and recorded spend can exceed the configured amount, and a public report describes a user who had limits configured while the surge happened before enforcement. The control that bounds a retry loop is a per-request budget check with a pre-call reservation plus a hard iteration cap on the agent loop, and it has to live in your own code or gateway, because the provider cannot see your loop.

3. (a) Cascade cost per query is cheap + e x deep. That exceeds deep when 1 + 5e > 5, so e > 0.8. Above an 80% escalation rate the cascade is worse than deep-only. (b) 1 + 0.35 x 5 = 2.75 against 5, so 55% of deep-only. (c) A router pays once: 0.65 x 1 + 0.35 x 5 = 2.4, so 48%. (d) The cascade pays the cheap model for the 35% of queries it then escalates, so those queries are billed twice.

4. (a) Run the random control that escalates 35% of items at random. If the cascade does not beat it by more than the noise, the signal carries no information and the ship is blocked. (b) A 2026 calibration benchmark scored 15 frontier models by Brier score, where lower is better: the best scored 0.103, a calibrated-random baseline scores 0.1875, and at least one shipped model scored 0.367, roughly twice as bad as guessing. The most accurate model was not the best calibrated. (c) Replace the signal with a cross-model jury, or calibrate the existing confidence against a labelled set using isotonic regression. A third option is to move from a cascade to a pre-generation router, which removes the double payment.

5. (a) The HTTP 200 was sent when the stream opened, so the status line is already committed and cannot carry the breach. (b) Only one vendor documents it, as a stream event carrying a `finish_reason` of error, with a 402 when the breach happens before the stream starts. Everyone else is silent, so you should have low confidence and must test your own provider. (c) A silent downgrade to a cheaper model is the better choice mid-conversation, because the user did not cause the breach and an error mid-sentence is a worse experience than a slightly weaker answer. (d) Log the downgrade loudly even though the caller never sees it, including the tenant, the original model, the fallback model, and the budget that triggered it.

6. (a) Predicting the cost requires predicting the output length, and that is not accurate enough: the seminal work reports a mean error of 63 words with only 56% of predictions landing within 50 words, and recent work reports a mean absolute error near 100 tokens, which is a 50% error on a 200-token answer. (b) Read `max_tokens` from the request, price the worst case of full input plus that many output tokens, reserve it against the budget and reject before calling if it would breach, then replace the reservation with the actual cost after the response. (c) It depends on `max_tokens`. When a caller omits it, the mechanism falls back to the model's configured maximum, so the reservation becomes so large that legitimate requests get rejected. (d) A batch submission, because the request carries a file reference rather than the prompts, so nothing downstream can price the workload at submission time.

</details>

---

## References & Further Learning

Every URL below was fetched and checked on 2026-09-12. Part A carries the caching, cost-accounting and alerting references. This document carries the routing ones.

### Routing and cascades

**FrugalGPT** — Chen, Zaharia, Zou, May 2023. https://arxiv.org/abs/2305.05176
The paper that defined the LLM cascade, and the baseline every later paper compares against. Focus on section 3 for the two moving parts, a learned answer-scoring function and a learned threshold vector, and section 5 for the limitations.
Numbers with conditions: on a 10,000-example finance task it cut cost 80% against GPT-4 while gaining 1.5% accuracy, and a different operating point on the same task cut cost 98%. On a 2,400-example legal task, 1% accuracy gained at 73% lower cost. Every task is classification or short extraction, each cascade used three APIs, and the models and prices are from 2023. Quote the mechanism freely and the percentages only with all of that attached.

**RouteLLM** — Ong et al., June 2024, revised February 2025. https://arxiv.org/html/2406.18665v4
Read section 3.2 even if you skim the rest. It defines the call-performance threshold, the minimum share of strong-model calls needed to hit a chosen quality level, which is the number that belongs on your dashboard.
Numbers: 95% of the strong model's performance at 26% strong-model calls on an open-ended chat benchmark, and 14% after better training. Section 5.4 gives 3.66x cost saving on that benchmark, 1.41x on a knowledge benchmark, and 1.49x on a maths benchmark at 87% quality rather than 95%. A widely quoted 85% figure comes from the project blog and does not reconcile with the paper's own 3.66x, which is 72.7%. Name the benchmark with any number you quote.

**Is Escalation Worth It? A Decision-Theoretic Characterization of LLM Cascades** — Bouchard, May 2026. https://arxiv.org/abs/2605.06350
The paper to read when choosing between a cascade and a router. Across five benchmarks and eight models it found a lightweight pre-generation router beating the best cascade policy on four of five datasets, with the cause named as structural: a cascade pays the cheap model before any escalation decision.
Honest note: preprint, and these numbers come from the abstract. Open the results section before making one load-bearing.

**LLMRouterBench** — Li et al., January 2026. https://arxiv.org/html/2601.07206v1
The evidence that routers fail silently. Ten routers re-run over 400,000+ instances from 21 datasets and 33 models. Focus on sections 4.2.1 and 4.2.2.
Numbers: on the 410 queries that at most three expert models answered correctly, 11.9% of the test set, two leading routers scored 24.6% and 23.2%. A commercial routing product scored minus 24.7% against always using the best single model. Stated limitations: no long-context, no multimodal, and latency is estimated.

**When Routing Collapses** — Lai and Ye, February 2026. https://arxiv.org/html/2602.03478
The opposite failure. As budgets rise, routers send everything to the most expensive model even when a cheaper one was already correct. Take the Routing Collapse Index from section 5.1 even if you take nothing else: the fraction of queries where the router made a dominated choice or missed a strictly cheaper model that would have been right.

### Escalation signals, ranked by evidence

**When LLMs Agree, Are They Right?** — Ding, July 2026. https://arxiv.org/abs/2607.08065
The strongest citation for the silent failure mode. 53 configurations, 50 samples each, 265,000 samples, on GPQA Diamond and AIME. Agreement predicted correctness only weakly, at correlations of 0.20 to 0.59, and failed worst on frontier models. On GPQA a frontier model reached agreement of 0.8 or higher on 77% of entries and **48% of those were wrong**. Read it before using self-consistency as a stopping rule.

**LLMs as a Jury** — Liu, July 2026. https://arxiv.org/abs/2607.10139
Read it directly after the paper above, because together they resolve an apparent contradiction. Resampling one model reproduces that model's own mistakes. Different models do not share all of them, so wrong answers scatter while the right one accumulates agreement. On competition maths a jury closed the entire gap to an oracle selector while self-scoring closed almost none. Its stated limit is a shared-error floor where every model holds the same misconception.

**ConfidenceBench** — ffrench-Constant et al., July 2026. https://arxiv.org/abs/2607.20526
Why you must measure your specific model before trusting its self-reported confidence. 15 frontier models scored by Brier, where lower is better. Best models 0.103, calibrated-random baseline 0.1875, and at least one shipped model 0.367, roughly twice as bad as guessing. The most accurate model was not the best calibrated. Honest note: 200 multiple-choice questions, small sample.

**UCCI** — Kotte, May 2026. https://arxiv.org/abs/2605.18796
What calibration is worth in production. Isotonic regression over token-level uncertainty on a 75,000-query workload: calibration error fell from 0.12 to 0.03, cost fell 31% with a 95% interval of 27% to 35%, and quality held at 0.91 micro-F1.

### Production and gating

**AutoRelAnnotator** — Rokon et al., June 2026. https://arxiv.org/abs/2606.25871
The largest verified production cascade found: over 150 million annotations across six use cases. Its conclusion is the one to carry: fine-tuning contributed 20 accuracy points, cascading was approximately accuracy-neutral and halved compute cost. Accuracy and cost are separate optimisations.
Condition: offline batch annotation with fine-tuned classifiers and loose latency. Do not transfer it to interactive chat.

**RLM-Cascade** — Wu et al., June 2026. https://arxiv.org/abs/2606.22840
An interactive cascade reporting cost, latency and a quality gate together: 125 production agentic-coding requests, 45.8% lower cost, median latency 2,026ms against 3,698ms. Honest note: 125 requests and a 20-task quality benchmark are small, and the reported 100% against 95% pass rate is a difference of one task.

**Evaluate model router for your workload** — Microsoft Learn, August 2026, with methodology at https://github.com/microsoft-foundry/Model-Router-Auto-Evaluation
https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/evaluate-model-router
The clearest published process for gating a model change. Two details to copy: every pairwise judgement runs twice with the response order swapped and needs agreement in both directions, which controls position bias; and the sample-size guidance, where under 30 prompts is directional only, 100 to 500 is good, and a category with fewer than 5 prompts has high variance. Results use bootstrap resampling with 1,000 resamples and a 95% interval.
The companion concepts page states a routing quality budget explicitly: one mode accepts models within 1% to 2% of the best quality for a prompt, another accepts 5% to 6%. It also warns that the effective context window is limited by the smallest model in the pool.

**Gateway routing vocabulary**, for config key names. Check the version before copying any of these.
https://docs.litellm.ai/docs/routing — `routing_strategy` accepts `simple-shuffle`, `least-busy`, `usage-based-routing`, `latency-based-routing`, `rate-limit-aware`, `rate-limit-aware-v2`, `cost-based-routing`. Note what these are: load balancing and failover, not quality routing. `cost-based-routing` picks the cheapest deployment, not the cheapest adequate model.
https://portkey.ai/docs/product/ai-gateway/conditional-routing — routes on metadata you supply, with `$eq`, `$in`, `$regex` and similar operators. It does not classify difficulty.
https://openrouter.ai/docs/features/model-routing — read next to the LLMRouterBench result above. Its auto router ranks by aggregate spend across users over a trailing window, which is a different objective from answering your query correctly.

---

## Cheatsheet — part B

```
ROUTING
  cascade cost = cheap x ALL + deep x escalated     ← escalated queries pay twice
  router  cost = cheap x easy + deep x hard + classifier
  cascade beats deep-only while   escalation rate < 1 - (cheap/deep)
  RANK BY DOLLARS PER CORRECT ANSWER, never by cost alone
  ALWAYS run the random control: escalate the same COUNT at random
  signal strength: cross-model jury > calibrated token confidence >
                   self-reported (varies by model) > self-consistency (weak)
  CPT = the % of strong-model calls needed to hit your quality target

BATCH
  50% off on both major providers | 24h window
  cannot be budget-reserved: the request carries a file, not the prompts
  inside a batch use the 1-hour cache tier, not the 5-minute one

COST ALERTING
  three rules: per-request budget | rolling cost (THAT it rose)
               cache hit floor (WHY it rose)
  set the floor just under your MEASURED normal, not at a round number
  fire each rule once per run; a rule that pages every request gets muted
  record per request: route, cost, naive_cost, uncached_in, cached_in,
                      cache_write, out, cache_hit_rate
  a broken cache does NOT change your token count. Only the class changes.

ENFORCEMENT
  alert (traffic continues) | hard stop (429) | degrade (cheaper model, no error)
  only a PRE-CALL RESERVATION stops spend before it happens
    reserve worst case from max_tokens → reject → settle to actual
  output length is NOT predictable: best-in-class MAE ~100 tokens
  every other control is enforced against stale spend, by the vendors' own words
  provider caps: monthly only, org or project scope, "not instantaneous"
  mid-stream breach behaviour is undocumented almost everywhere

THE COMMANDS (part B)
  cascade_lab.py --self-test                      → the scorer, offline
  cascade_lab.py --simulate                       → cascade vs the control
  cascade_lab.py --simulate --signal-quality 0.5  → an expensive coin flip
  cascade_lab.py --simulate --trials 1 --seed N   → how badly one run lies
  budget_guard.py --self-test                     → the three rules, offline
  budget_guard.py --simulate                      → Story 1, detected in seconds
  budget_guard.py --simulate --cache-floor 0.90   → a threshold that works
  budget_guard.py --simulate --no-cache-rule      → symptom without cause
```

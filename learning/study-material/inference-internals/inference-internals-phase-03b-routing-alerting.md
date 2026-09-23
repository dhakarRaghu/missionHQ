# Phase 3B — Routing, batch, and the cost alarm

Part A made your bill smaller. Part B is about two things: spending the savings well, and keeping them.

Two questions remain from earlier phases:

- **Phase 0's Story 3.** A team switched everything to a cheap model and lost quality. Its only options were expensive everywhere or cheap everywhere. Section 3.4 builds a third option.
- **Phase 0's Story 1.** A team lost its cache for four months and did not notice. Section 3.5 builds the detector that would have caught it within ten requests.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  3.4  Routing cascades and     — quality per dollar, and the control     │
│       batch APIs                 group that most write-ups skip          │
│  3.5  Per-request cost         — the detector Story 1 needed, and why    │
│       alerting                   every enforcement control is late       │
└──────────────────────────────────────────────────────────────────────────┘
```

Part A is a prerequisite. This document uses `pricing.py` and the five token classes without explaining them again.

Time: 1.5 to 2 hours. Both scripts in this part run with no API key.

---

## 3.4 — Routing cascades (quality per dollar, and the control group)

Why this matters: Story 3's team had only two options. This section builds a third one, and shows how to prove it works.

### Two shapes, and the arithmetic that separates them

A cascade sends every query to a cheap model first. It escalates a query to a deep model when a signal says the cheap answer is unsure. A router decides before any model answers.

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

Read the two cost lines again. A cascade pays the cheap model for **every** query. That includes the queries it then escalates, so you pay twice for those. A router pays once.

This difference matters. A 2026 decision-theoretic study covered five benchmarks and eight models. A lightweight pre-generation router beat the best cascade policy on four of the five datasets. The study names this arithmetic as the cause. The router wins because it "avoids the cheap model's generation cost on queries sent directly to a larger model". The paper says the gain is not "because of a stronger routing signal". The paper concludes that structural cost is the main limit on cascade performance.

So the cascade's advantage is not price. Its escalation signal can look at the cheap model's real answer. A pre-generation classifier cannot do that.

**The break-even, on paper.** Let `e` be the fraction of queries you escalate. Let `Cc` be the cheap cost and `Cd` the deep cost.

```
cascade cost   = Cc + e x Cd          per query
deep-only cost = Cd                   per query

the cascade is cheaper when     Cc + e x Cd  <  Cd
                                e  <  1 - Cc/Cd
```

In the course price sheet, `gpt-4.1` input costs 5x `gpt-4.1-mini` input: $2.00 against $0.40. Output has the same 5x ratio. Put `Cc/Cd` at 1/5. The cascade then stops saving money when you escalate more than 80% of queries. That limit is loose. Quality limits you long before it.

### The control group nobody runs

This experiment decides whether your cascade is real.

1. Run your cascade, and record the escalation rate.
2. Run a second configuration that escalates **the same number of queries, chosen at random**.
3. Compare them. If your cascade does not beat the random one, your signal carries no information. You pay escalation costs for noise.

`cascade_lab.py` runs both, plus the two single-model baselines:

```bash
python phase03_economics/cascade_lab.py --simulate
```

The output on the author's machine, re-run on 2026-09-17. The script averages 300 trials of 20 items:

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
NOTE: one trial of 20 items varies by about 7 points. If you had run this once
you could have concluded anything.
cascade keeps 96.4% of deep-only accuracy for 61.9% of the deep-only cost.
```

Long lines are wrapped here to fit.

Now break the signal and keep everything else the same. Signal quality is how often the signal flags a hard item. A value of 0.5 is a coin flip.

```bash
python phase03_economics/cascade_lab.py --simulate --signal-quality 0.5
```

```
signal quality 0.50: the cascade beats the random control by +0.4 accuracy
points on average (standard error 0.43; one trial varies by 7.4).
That is inside two standard errors of zero. At this signal quality the cascade
is an expensive coin flip. Fix the signal before shipping it.
cascade keeps 90.7% of deep-only accuracy for 69.3% of the deep-only cost.
```

Look at what did **not** change. The cascade still shows 85% accuracy, at 69.3% of the deep-only cost. A dashboard with only those two columns would call this a success. Only the control row shows the problem.

**The main metric is dollars per correct answer.** Cost alone rewards a system that is cheap and wrong. Accuracy alone rewards a system that is expensive and slow. The ratio moves in the right direction for both problems.

### Which escalation signal works

Most implementations pick a signal by intuition. Measured evidence now exists, and the ranking surprises most people.

```
┌────────────────────────────┬──────────────────────────────────────────────┐
│ signal                     │ what the measurements say                    │
├────────────────────────────┼──────────────────────────────────────────────┤
│ cross-model agreement      │ Strongest. Different models make different   │
│ (a jury)                   │ mistakes, so wrong answers scatter and the   │
│                            │ right one accumulates agreement. Costs       │
│                            │ several models per query.                    │
│ calibrated token-level     │ Works, with work. One production study cut   │
│ confidence                 │ calibration error from 0.12 to 0.03 using    │
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

Calibration means that a model's stated confidence matches how often it is right. Isotonic regression is a standard method that fixes the mapping from score to probability.

**The self-consistency result is the trap.** Self-consistency samples one model many times. It measures how often the answers agree.

- A 2026 audit ran 53 configurations with 50 samples each, 265,000 samples in total.
- It used the GPQA Diamond and AIME benchmarks.
- On GPQA, a frontier model reached an agreement level of 0.8 or higher on 77% of entries.
- **48% of those high-agreement answers were wrong.**

A cascade with self-consistency as its stopping rule would accept nearly all of them. It would escalate none. The paper itself calls self-consistency a conditional signal, not a standalone one.

**This explains why a jury beats resampling.** Sampling one model 50 times repeats that model's own systematic mistakes 50 times. Different models do not share all of the same mistakes. So if you spend extra calls on a confidence signal, spend them on different models. Do not spend them on more samples from one model.

**The warning about self-reported confidence.** A 2026 calibration benchmark scored 15 frontier models with the Brier score. Lower is better.

- The best models scored 0.103.
- A calibrated-random baseline scores 0.1875.
- At least one shipped model scored 0.367. That is about twice as bad as guessing.
- The most accurate model was not the best calibrated.

Use this as an engineering rule. Say you put a badly calibrated model at tier one and trust its self-reported confidence. You have then built a random escalator that costs money. That is the `--signal-quality 0.5` run you just did.

### The two failure modes, both measured

**Under-routing: a hard query goes to the cheap model, and nothing tells you**. A January 2026 benchmark re-ran 10 routers over 400,000 instances. The instances came from 21 datasets and 33 models. One subset held the queries that at most three of the expert models answered correctly. That subset had 410 queries, 11.9% of the test set. On it, two leading routers scored 24.6% and 23.2%. Routers are weakest where the routing choice matters most. They are strongest where any model would have been fine.

The same benchmark measured a commercial routing product at **minus 24.7%**. The comparison was against always using the best single model.

Neither system raises an error. The answer comes back looking normal.

**Over-routing: everything goes to the expensive model, and nothing tells you.** A February 2026 paper calls this routing collapse. As the budget rises, routers pick the most powerful model even when a cheaper one was already correct. The paper proposes the Routing Collapse Index, a metric you can compute on your own traffic. It is the fraction of queries where the router makes one of two errors:

- it makes a dominated choice
- it misses a strictly cheaper model that would have been right

If you take one thing from the paper, take that metric.

### The number to put on a dashboard

The routing research agrees on one metric. It is the call-performance threshold, written CPT. CPT is the minimum percentage of calls to the strong model that reaches a chosen quality level.

State your goal in that form, and the problem becomes one you can solve. The target is "hold 95% of deep-only quality". CPT tells you what share of traffic that costs. In the original router paper, one configuration reached 95% of the strong model's performance on one benchmark. It used 26% strong-model calls. A better-trained version reached the same quality at 14%.

**State the benchmark with every routing number you quote.** The same routers in that paper gave three different cost savings:

- 3.66x on an open-ended chat benchmark
- 1.41x on a knowledge benchmark
- 1.49x on a maths benchmark, at 87% quality retained, not 95%

A single "up to" figure from that paper means almost nothing without its benchmark.

### What production looks like

Two deployments report both cost and quality. That is the minimum for believing a routing claim.

**An interactive agentic-coding cascade.** It reported 45.8% lower cost and no measured quality regression. Its median latency was 2,026ms against 3,698ms. Its limit is scale: 125 requests and a 20-task benchmark. The reported quality gap is a difference of one task.

**An offline annotation pipeline.** It reported over 150 million annotations across six use cases. Cascading was about accuracy-neutral, and it halved compute cost. Its conclusion is the one to remember. Fine-tuning drove their accuracy, and cascading drove their cost. Cascading did not improve quality, and nobody asked it to. The condition: this is offline batch work with fine-tuned classifiers and loose latency requirements.

**Reject this kind of claim.** A widely shared engineering post reports a monthly bill that fell from $47,000 to $11,000. It also reports a 74% primary resolution rate. It publishes no traffic volume, no quality metric, no threshold value, and no quality score. It says quality "held steady" and gives no number. That post is a story, not evidence. Apply the same test to every routing claim you read, including the claims in this document.

### Gating the swap

A model change is a deploy. Treat it like a code deploy. The clearest published process comes from Microsoft. It tells customers to measure Microsoft's own router against their current model before they adopt it. Four steps give most of the value:

1. **Name the decision first.** Set acceptance criteria on four dimensions, not one. They are quality, cost per request, and latency with a tail percentile. The fourth is policy limits, such as allowed models and regions.
2. **Compare against your current production model**, not a leaderboard. Group prompts by category. Then an aggregate number cannot hide a regression in one category.
3. **Control for position bias.** An LLM judge tends to prefer the answer it sees first. Run every pairwise judgement twice, with the response order swapped. Agreement in both orders is a verdict. Disagreement is a tie.
4. **Report a confidence interval.** Follow the sample-size guidance. Fewer than 30 prompts is directional only. 100 to 500 prompts is good. A category with fewer than 5 prompts has high variance.

Teams skip steps 3 and 4 most often. Those two steps decide whether your result is real. The `--simulate` output above already shows step 4's lesson: one 20-item trial varies by about 7 accuracy points. Exercise E14 shows it with single runs.

Before a full rollout, watch live traffic. Track quality per category, real cost, and median and tail latency under real concurrency. Also track error and failover rates, and which model the router selected.

**The sentence to remember:** a cascade is real only if it beats a random control with the same escalation count. You must measure the escalation signal. Do not assume it works.

**The trap:** self-consistency feels like a confidence measure, but it works as one only on weak models. On a frontier model, 77% of answers had high agreement, and 48% of those were wrong.

**Try this now:** run `python phase03_economics/cascade_lab.py --simulate` with `--signal-quality 0.55`, then `0.6`, then `0.65`. On 2026-09-17 the gaps were +1.9, +2.7, and +3.6 points, at 4, 6, and 9 standard errors. Over 300 trials, even a weak signal clears two standard errors. So also ask whether the gap is large enough to pay for. Write down the lowest signal quality you would accept.

### Batch APIs, the third option

A batch API gives a flat discount in exchange for latency. Both major providers price it at **50% of the synchronous rate**, on input and output.

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

Use it for work where no user is waiting. Examples are evaluation runs, backfills, nightly classification, and dataset labelling. Eval suites, which a later module of this curriculum builds, are a clear candidate. Halving that bill is often the easiest saving in this phase.

**A batch API breaks one thing.** You cannot reserve a budget for a batch job before you submit it. The request carries a file reference, not the prompts. So nothing downstream can price the workload at submission time. Every budget system has this gap, including the one in section 3.5. Price batch jobs from the output file afterwards. Cap them by size instead.

---

## 3.5 — Per-request cost alerting (the detector Story 1 needed)

Why this matters: everything before this section makes your bill smaller. This section keeps it small. If you cannot monitor a saving, you will lose it without noticing.

Go back to Phase 0, Story 1. A team shipped an agent with an 18,000-token system prompt. A timestamp sat near the top. The cache never matched. They paid full input price on every step for four months.

Ask the useful question: what would have caught it?

**Not a monthly bill.** The provider invoice arrives after the month ends. It mixes every route, every tenant, and every experiment. Four months is what that delay looks like.

**Not a token dashboard.** This part surprises people, so read it slowly. When the cache breaks, the token COUNT does not change. The same prompt goes over the wire. Only the billing class changes, from cached to uncached. A dashboard of input tokens per request shows a flat line through the whole incident.

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

**Not a per-request budget alone.** No single request was extreme. In the replay below, each request after the break costs 5.4x the cost before it. That is still far below any threshold you would set to avoid false alarms. A rule that only catches outliers cannot catch damage that is the same on every request.

### The three rules, and what each one is for

`budget_guard.py` implements all three rules. It writes an append-only ledger, with one JSON object per request.

```
┌───────────────────┬─────────────────────────────┬─────────────────────────┐
│ rule              │ fires when                  │ what it tells you       │
├───────────────────┼─────────────────────────────┼─────────────────────────┤
│ per-request       │ one call costs more than    │ a runaway single        │
│ budget            │ its route's budget          │ request. Catches loops  │
│                   │                             │ and giant contexts.     │
│ rolling cost      │ the recent window mean      │ THAT cost went up.      │
│                   │ rises above a baseline      │ Not why.                │
│                   │ multiple                    │                         │
│ cache hit floor   │ the cached share of input   │ WHY cost went up.       │
│                   │ tokens falls below a floor  │ This is Story 1's rule. │
└───────────────────┴─────────────────────────────┴─────────────────────────┘
```

### Replay Story 1, and see why the price row matters

The replay sends 200 agent steps with an 18,000-token stable prefix. The cache breaks at request 50. Which price row you use changes the result completely. Both runs below are real output from 2026-09-17, trimmed.

```bash
# WRONG: replay with the default role. Its gpt-4.1-mini row has no cached price.
python phase03_economics/budget_guard.py --simulate
#   NOTE: gpt-4.1-mini has no cached_input_per_mtok in the sheet ...
#   request    1: cost $0.007760  hit rate 98%
#   request   50: cost $0.007760  hit rate 0%
#   cache_floor    request   59  spend at detection $0.4578
#   The cost line is flat. rolling_cost never fires.

# RIGHT: replay with a row that has a verified cached price.
python phase03_economics/budget_guard.py --simulate --role cache_demo
#   request    1: cost $0.007400  hit rate 98%
#   request   50: cost $0.039800  hit rate 0%
#   rolling_cost   request   52  spend at detection $0.4820
#   cache_floor    request   59  spend at detection $0.7606
```

The WRONG run is part A's fallback rule at work. A missing cached price is charged at the full input price. That keeps the total safe. It also makes the cost before the break look the same as the cost after it. The cost rule then has nothing to detect. Fill in the cached price before you trust a cost alert.

Everything below uses `--role cache_demo`, the gpt-5.6-terra row. Its cost per request jumped from $0.007400 to $0.039800 at the break. That is 5.4x. Both rules fired within ten requests. Four months became seconds.

### The result that should bother you

Look at the RIGHT output again. The cache rule fired at request **59**. The rolling-cost rule fired at **52**, seven requests earlier. The rule designed to catch this problem fired second.

This order is not fixed. It comes from a tuning mistake. The default settings contain it on purpose, so that you find it.

The default floor is 50%. The system's normal hit rate is 98%. A window average must fall a long way to cross a floor that far below normal. Raise the floor:

```bash
python phase03_economics/budget_guard.py --simulate --role cache_demo --cache-floor 0.90
#   cache_floor    request   51  spend at detection $0.4422
#   rolling_cost   request   52  spend at detection $0.4820

python phase03_economics/budget_guard.py --simulate --role cache_demo --cache-floor 0.90 --window 5
#   rolling_cost   request   50  spend at detection $0.4024
#   cache_floor    request   50  spend at detection $0.4024
```

With a 90% floor, the cache rule now fires first. With a 5-request window, both rules fire on request 50, the first request after the break.

**The rule: set the floor just below your measured normal.** Do not pick a round number. A threshold picked because it looks tidy detects nothing. Measure your hit rate for a week. Then set the floor a few points below it.

### Two design decisions in the guard worth copying

**Each rule fires once per run.** If a rule pages on every request, your on-call engineer mutes it. A muted rule detects nothing. The guard records the first firing, with the request index and the spend at that moment. Then it stays quiet. See `_fire` at `budget_guard.py:121`.

**The first full window sets the baseline. Question that assumption.** This is the shipped code at `budget_guard.py:139`:

```python
if self.baseline_cost is None:
    # The first full window sets the baseline. This is the assumption to
    # question: if the system was already broken at startup, the baseline
    # bakes the problem in and rule 2 can never fire.
    self.baseline_cost = avg
    return
```

That comment describes a real failure. A guard that learns its baseline at startup can report a broken system as healthy forever. The production fix has two parts. Store the baseline outside the process, next to your price sheet. Alert on any deploy that changes it.

**The guard never blocks a request.** Blocking on cost is a product decision. It belongs at the call site, where you know whether the user is mid-conversation. The guard's only job is to make cost visible at the moment it happens.

### What to record per request

The ledger the guard writes is the minimum useful schema. Here is request 50 of the RIGHT run, from `/tmp/budget_ledger.jsonl`:

```json
{"i": 50, "ts": 1789657285.515, "route": "agent_step", "model": "gpt-5.6-terra",
 "cost": 0.0398, "naive_cost": 0.0398,
 "uncached_in": 18400, "cached_in": 0, "cache_write": 0, "out": 250,
 "cache_hit_rate": 0.0}
```

Each field is needed for a reason:

- `route` separates a chat turn from a summarisation call and from a batch job. Without it, one route's regression hides inside another route's average.
- `cached_in` next to `uncached_in` is the main point. One number without the other tells you nothing.
- `naive_cost` next to `cost` keeps the Phase 1 formula visible. You can always show what caching is worth. Request 1 of the same run has `cost` 0.0074 and `naive_cost` 0.0398.
- `cache_hit_rate` is stored, not computed at query time. So an alert can be a plain threshold on a column.

**The sentence to remember:** measure cost per request and cache hit rate per request. The most expensive failure does not change your token count at all.

**The trap:** a threshold set to a round number, not to your measured normal. A 50% cache floor on a system that normally runs at 98% does not detect the failure in time.

**Try this now:** run `python phase03_economics/budget_guard.py --simulate --role cache_demo --no-cache-rule` and confirm which alert is left. Then open `/tmp/budget_ledger.jsonl` and compute the spend before and after the break yourself.

### Alerting is not enforcing, and enforcing is harder

The guard reports. It does not stop anything. Stopping is a separate problem, and one property of it decides your design.

**Every production cost control enforces against spend data that is already out of date**. This is not a criticism of one product. It is how these systems are built, and the vendors say so in their own documentation.

```
┌──────────────────────┬──────────────────────┬──────────────────────────────┐
│ system               │ when it checks       │ its own published caveat     │
├──────────────────────┼──────────────────────┼──────────────────────────────┤
│ a gateway that       │ BEFORE the call      │ it must guess the output     │
│ reserves budget      │                      │ size when max_tokens is      │
│                      │                      │ absent                       │
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

### The reservation pattern, the one good answer

You cannot know the output size before the call. So you meter after the call. But you can put an upper bound on it.

```
1. read max_tokens from the request. If absent, use the model's configured limit.
2. price the WORST CASE: full input + max_tokens of output.
3. reserve that amount against the budget.
4. if the reservation would exceed the budget, reject BEFORE calling the provider.
5. after the response, replace the reservation with the actual cost.
```

LiteLLM, an open-source gateway, documents this mechanism. It is worth copying, because it turns an unknown amount into a bounded one. It also shows why `max_tokens` is required in a cost-controlled system. Without it, step 1 uses the model's maximum. The reservation then becomes so large that valid requests get rejected.

**Do not use output-length prediction instead.** The research shows it is not accurate enough for billing.

- The first well-known work reports a mean error of 63 words.
- Only 56% of its predictions land within 50 words. So 44% of requests land more than 50 words away.
- Recent work reports a mean absolute error of about 93 to 103 tokens. On a 200-token answer, that is a 50% cost error.

Prediction is good enough for scheduling. It is not good enough for billing.

### Three responses to a breach, not two

Most designs consider two responses: alert, or hard stop. A third response exists. It is often the right one for a user-facing product.

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

The third response is a documented gateway feature. A key crosses its per-model budget. The gateway then serves requests with a cheaper model, and no budget error reaches the caller. The spend is recorded against the fallback model. This is section 3.4's cascade, triggered by money, not by difficulty.

**State the trade to your product team.** A silent downgrade protects the conversation. It also hides a real event from the user. Log it loudly, even though the caller never sees it.

### The question nobody documents: what happens mid-stream

A request can cross its budget while tokens are already streaming. The server sent the HTTP 200 when the stream opened. So the breach cannot be an HTTP status.

On 2026-09-12, the author checked several gateways and providers. Exactly **one** documents this behaviour. The error arrives as a stream event with `finish_reason: "error"`. A breach before the stream starts returns HTTP 402. None of the others document it.

That gap is the finding. If your design depends on stopping a stream at a budget limit, it depends on undocumented behaviour. Test it against your own provider before you promise it.

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

**This forces one conclusion.** Daily cost data cannot drive a per-request or per-minute alert. Providers offer no per-tenant budgets. So you meter locally, enforce locally, and reconcile against the provider's daily report.

That reconciliation is a required control. It is the only one that catches a billing bug on the provider side, and those bugs happen. In one public report, a model billed 466,818 output tokens. It had generated 21,064. The configured cap was 128,000.

### There is no standard for this yet

The OpenTelemetry generative-AI conventions define token attributes, including cache reads and writes. At a commit dated 2026-09-10, they define **no cost attribute at all**. All 118 attributes have development stability, and there is no released version. Part A's references give the details.

An open pull request proposes `gen_ai.usage.cost.amount`, `.currency` and `.source`. The `source` field separates a cost the provider returned from a cost you computed. Use those names now.

Two practical warnings from the same source:

1. The cache-write attribute is `gen_ai.usage.cache_write.input_tokens`. A source that gives `cache_creation` as an OpenTelemetry name is out of date.
2. The standard token metric has no dimension for cache reads or writes. So **you cannot compute spend from that metric when caching is on**. Use span attributes.

### The state of the evidence

**No company has published a first-party postmortem of an LLM cost spike with a time to detect**. A search of many well-known engineering blogs found none. The available sources are bug reports, community self-reports, vendor announcements, and journalism. Large dollar figures circulate, such as a $47,000 incident. They lead back to posts with no first-party source, and their details contradict each other.

The nearest primary account is METR's disclosure of a security incident. An exposed internal application used about $600,000 of API credits over about three weeks. METR gives three reasons for the detection gap. Most teams have the same three:

1. The anomaly looked normal. High token volume was routine there.
2. The dashboard did not show the signal. In that case the signal was rate-limited requests.
3. Nothing could stop it. The credits were free, so no spend ceiling existed.

A 2026 catalog of 63 incidents found no case where a budget overrun was stopped before a user paid. Part A lists it.

**Take this as your task.** The detector in this section is required. It is the only thing that shortens the time between a mistake and its discovery.

---

## 🧪 Hands-on lab — part B

Every exercise here runs offline. You need no API key, and nothing costs money. The author re-ran every command below on 2026-09-17. The Expected lines match that run.

- [ ] **E9 (offline).** Replay Story 1 and time the detection.
  - Run: `python phase03_economics/budget_guard.py --simulate --role cache_demo`
  - Expected: cost per request jumps from $0.007400 to $0.039800 at request 50. The rolling-cost rule fires at 52, with $0.4820 spent. The cache rule fires at 59, with $0.7606 spent.
  - Then run it without `--role cache_demo`, and explain the flat cost with part A's fallback rule.
  - Teaches: per-request metering turns a four-month incident into a ten-request incident, if the price sheet is complete.

- [ ] **E10 (break-it, offline).** Prove the default threshold is badly chosen.
  - Run: `python phase03_economics/budget_guard.py --simulate --role cache_demo --cache-floor 0.90`. Then add `--window 5`.
  - Expected: the cache rule moves from request 59 to 51, and then to 50. At 51 it fires before the rolling rule, which stays at 52.
  - Now the real exercise. Explain in one sentence why a 50% floor detects late on a system whose normal hit rate is 98%.
  - Teaches: a threshold must come from your measured normal, not from a round number.

- [ ] **E11 (break-it, offline).** Remove the rule that finds the cause.
  - Run: `python phase03_economics/budget_guard.py --simulate --role cache_demo --no-cache-rule`
  - Expected: only `rolling_cost` fires, at request 52. You now know that cost went up, and nothing about why.
  - Then run it without `--role cache_demo`. The output ends with `no alerts fired`. The incident is now invisible.
  - Then answer this. Name two unrelated changes that would also trigger `rolling_cost`. Say how you would tell them apart with only the ledger.
  - Teaches: an alert that reports a symptom still needs a second signal that reports the cause.

- [ ] **E12 (offline).** Build a cascade and run the control group.
  - Run: `python phase03_economics/cascade_lab.py --simulate`
  - Expected, averaged over 300 trials: the cascade keeps 96.4% of deep-only accuracy for 61.9% of the deep-only cost. It beats the random control by +7.2 accuracy points, 17 standard errors from zero.
  - Teaches: dollars per correct answer is the metric. Cost alone rewards a system that is cheap and wrong.

- [ ] **E13 (break-it, offline).** Break the signal, and watch the cascade still look good.
  - Run: `python phase03_economics/cascade_lab.py --simulate --signal-quality 0.5`
  - Expected: the gap against the random control falls to +0.4 points. That is inside two standard errors of zero. The cascade still shows 85.0% accuracy at 69.3% of the deep-only cost.
  - Then run `--signal-quality 0.55`. The gap is +1.9 points, at 4 standard errors. Decide whether that gap is worth the escalation cost.
  - Teaches: a cascade with an uncalibrated signal is a random escalator with a good-looking dashboard. Only the control group shows this.

- [ ] **E14 (offline).** Find out how much one run can mislead you.
  - Run: `python phase03_economics/cascade_lab.py --simulate --trials 1 --signal-quality 0.5` three times, with `--seed 1`, `--seed 2`, and `--seed 3`.
  - Expected: the gap line reads +10.0, then +0.0, then -5.0 accuracy points. All three runs use the same coin-flip signal.
  - Each run also prints "Only one trial, so there is no standard error." With one trial there is no spread to measure. An earlier version of the script divided by that zero and crashed.
  - Teaches: the eval sets you will build in the eval engineering module are small, and small sets mislead. Report the spread with every number.

---

## 🔍 Check it yourself — questions against the course code

1. Open `phase03_economics/budget_guard.py` at line 121, `_fire`. It records each rule at most once per run. Explain the operational reason in one sentence. Then name what the method stores with the rule, so that a later reader can price the incident.

2. In the same file, go to line 143, where `self.baseline_cost` is set for the first time. Read the comment there. Describe the exact starting condition under which the rolling-cost rule can never fire. Say where the baseline would have to live to fix it.

3. Open `phase03_economics/cascade_lab.py` at line 168, which computes `cascade_cost`. It adds the cheap cost for every item and the deep cost only for escalated items. Which real property of a cascade does that line encode? Name the architecture that avoids it.

4. In any repository you own that calls an LLM in a loop, find the loop. Answer two questions:
   - Is there a hard cap on the number of iterations?
   - Is there a per-request or per-session budget check before the call goes out?

   If both answers are no, compute the worst case. Multiply your iteration count by your `max_tokens` and your output price.

---

## ✅ Checkpoint 3B — answer in your own words

1. Design it, with the control group. You want to cut spend on a classification workload by routing. Design the experiment that decides whether to ship it. Cover these points: the four configurations you run, and the metric you rank them by. The control group, and why it exists. How many items you need before you believe the result. The one thing you do to stop an LLM judge from preferring the answer it sees first.

2. A colleague says: "I set a hard spend limit with our provider. So a runaway loop cannot cost us more than the cap." Give three reasons this is not true. One reason is about the interval, one about scope, and one about timing. Then name the one control that would limit the damage from a retry loop, and where it has to live.

3. Show the math. Your cheap model costs $1.00 per million input tokens. Your deep model costs $5.00. Token volumes are the same either way. (a) Derive the escalation rate above which a cascade costs more than sending everything to the deep model. (b) Your measured escalation rate is 35%. Compute the cascade's cost as a fraction of deep-only. (c) A pre-generation router with the same 35% hard-query rate would cost how much? (d) Explain the gap between (b) and (c) in one sentence.

4. This is broken. Your cascade shows 88% accuracy at 55% of deep-only cost. Your team wants to ship it. The escalation signal is the cheap model's self-reported confidence. (a) Name the one experiment that must run before shipping, and the result that would block the ship. (b) Give the measured evidence that self-reported confidence can be worse than useless. (c) Say the experiment shows the cascade matching the control. Name two things you could change without giving up on routing.

5. Walk me through what happens. A user is mid-conversation on your product. Their tenant crosses its monthly budget while tokens are already streaming back. (a) Explain why an HTTP status code cannot signal this. (b) State what the documentation says will happen, and how confident you should be. (c) Choose between a hard stop and a silent downgrade for this case. Justify it in one sentence. (d) Name what you must log in either case.

6. A colleague proposes: "We will predict each request's cost before the call. We will reject anything over budget." (a) Explain the part of that plan that cannot work, with a number. (b) Describe the mechanism that does work, in four steps. (c) Name the request parameter that mechanism depends on. Say what happens when a caller leaves it out. (d) Name the one request type this mechanism cannot price at all, and why.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. Run four configurations: cheap-only, deep-only, cascade, and a random control. The control escalates the same number of items, chosen at random.
   - Rank by dollars per correct answer. Cost alone rewards being cheap and wrong.
   - The control exists because a cascade with a useless signal still shows good accuracy and lower cost.
   - Sample size: under 30 prompts is directional only, and 100 to 500 is good. One 20-item trial varied by about 7 points, so average many trials and report the standard error.
   - Position bias: run every pairwise judgement twice, with the order swapped. Count a verdict only when both orders agree.

2. Three reasons:
   - Interval: the documented cap is monthly. A loop can spend a month's budget in an hour and stay inside the cap.
   - Scope: the cap covers the whole organisation or project, with no per-tenant dimension. One broken job trips it for everyone.
   - Timing: the provider states that enforcement is not instantaneous. One public report describes a user with limits set, whose surge came before enforcement.

   The control that limits a retry loop has two parts. One is a per-request budget check with a pre-call reservation. The other is a hard iteration cap on the agent loop. It must live in your own code or gateway. The provider cannot see your loop.

3. (a) Cascade cost per query is cheap + e x deep. That is more than deep when 1 + 5e > 5, so e > 0.8. Above an 80% escalation rate, the cascade costs more than deep-only.
   (b) 1 + 0.35 x 5 = 2.75, against 5. That is 55% of deep-only.
   (c) A router pays once: 0.65 x 1 + 0.35 x 5 = 2.4. That is 48%.
   (d) The cascade also pays the cheap model for the 35% of escalated queries. It pays twice for those.

4. (a) Run the random control that escalates 35% of items at random. The cascade must beat it by more than the noise. If it does not, the signal carries no information, and the ship is blocked.
   (b) ConfidenceBench, from section 3.4. By Brier score, the best models scored 0.103 and a calibrated-random baseline 0.1875. One shipped model scored 0.367, about twice as bad as guessing.
   (c) Replace the signal with a cross-model jury. Or calibrate the existing confidence against a labelled set with isotonic regression. A third option: move from a cascade to a pre-generation router. That removes the double payment.

5. (a) The server sent HTTP 200 when the stream opened. The status line is already sent, so it cannot carry the breach.
   (b) Only one vendor documents it: a stream event with a `finish_reason` of error, or 402 before the stream starts. So your confidence should be low. Test your own provider.
   (c) A silent downgrade to a cheaper model is better mid-conversation. The user did not cause the breach, and an error mid-sentence is worse than a slightly weaker answer.
   (d) Log the downgrade loudly, even though the caller never sees it. Include the tenant, the original model, the fallback model, and the budget that triggered it.

6. (a) Predicting the cost means predicting the output length. Recent work reports a mean absolute error near 100 tokens. That is a 50% cost error on a 200-token answer.
   (b) Read `max_tokens` from the request. Price the worst case: full input plus that many output tokens. Reserve it against the budget, and reject before the call if it would go over. After the response, replace the reservation with the actual cost.
   (c) It depends on `max_tokens`. If a caller leaves it out, the mechanism uses the model's configured maximum. The reservation then becomes so large that valid requests get rejected.
   (d) A batch submission. The request carries a file reference, not the prompts, so nothing downstream can price the workload at submission time.

</details>

---

## References & Further Learning

Every URL below was fetched and checked on 2026-09-12. Part A has the caching, cost-accounting, and alerting references. This document has the routing references.

### Routing and cascades

- **FrugalGPT, Chen, Zaharia, Zou, May 2023** — https://arxiv.org/abs/2305.05176
  The paper that defined the LLM cascade. Every later paper compares against it. Focus on section 3 for the two moving parts: a learned answer-scoring function and a learned threshold vector. Section 5 covers the limitations.
  Numbers with conditions: on a 10,000-example finance task, it cut cost 80% against GPT-4 and gained 1.5% accuracy. Another operating point cut cost 98%. On a 2,400-example legal task, it gained 1% accuracy at 73% lower cost. Every task is classification or short extraction. Each cascade used three APIs. The models and prices are from 2023. Quote the mechanism freely. Quote the percentages only with all of those conditions.

- **RouteLLM, Ong et al., June 2024, revised February 2025** — https://arxiv.org/html/2406.18665v4
  Read section 3.2 even if you skim the rest. It defines CPT, the dashboard metric from section 3.4. Section 3.4 also quotes its 26% and 14% results, on an open-ended chat benchmark, and its section 5.4 savings.
  A widely quoted 85% figure comes from the project blog. It does not match the paper's own 3.66x, which is a 72.7% saving. Name the benchmark with any number you quote.

- **Is Escalation Worth It? A Decision-Theoretic Characterization of LLM Cascades, Bouchard, May 2026** — https://arxiv.org/abs/2605.06350
  The paper to read when you choose between a cascade and a router. Section 3.4 quotes its result and its structural cause.
  Honest note: this is a preprint, and these numbers come from the abstract. Read the results section before you rely on one of them.

- **LLMRouterBench, Li et al., January 2026** — https://arxiv.org/html/2601.07206v1
  The evidence that routers fail without any error. Ten routers re-run over 400,000+ instances from 21 datasets and 33 models. Focus on sections 4.2.1 and 4.2.2.
  Section 3.4 quotes its numbers. Stated limitations: no long-context, no multimodal, and estimated latency.

- **When Routing Collapses, Lai and Ye, February 2026** — https://arxiv.org/html/2602.03478
  The opposite failure, described in section 3.4. The Routing Collapse Index is in its section 5.1.

### Escalation signals, ranked by evidence

- **When LLMs Agree, Are They Right?, Ding, July 2026** — https://arxiv.org/abs/2607.08065
  The strongest citation for the silent failure, and the source of section 3.4's self-consistency numbers. Agreement predicted correctness only weakly, at correlations of 0.20 to 0.59. Read it before you use self-consistency as a stopping rule.

- **LLMs as a Jury, Liu, July 2026** — https://arxiv.org/abs/2607.10139
  Read it directly after the paper above. Together, they explain why a jury beats resampling, as section 3.4 describes. On competition maths, a jury closed the whole gap to an oracle selector. Self-scoring closed almost none of it. Its stated limit is a shared-error floor, where every model holds the same misconception.

- **ConfidenceBench, ffrench-Constant et al., July 2026** — https://arxiv.org/abs/2607.20526
  Why you must measure your own model before you trust its self-reported confidence. It scored 15 frontier models by Brier score. Section 3.4 quotes its results. Honest note: it uses 200 multiple-choice questions, a small sample.

- **UCCI, Kotte, May 2026** — https://arxiv.org/abs/2605.18796
  What calibration is worth in production, quoted in the section 3.4 table. Its 31% cost cut has a 95% interval of 27% to 35%.

### Production and gating

- **AutoRelAnnotator, Rokon et al., June 2026** — https://arxiv.org/abs/2606.25871
  The largest verified production cascade found, quoted in section 3.4. Fine-tuning added 20 accuracy points, and cascading halved compute cost. Accuracy and cost are separate optimisations. Do not apply it to interactive chat.

- **RLM-Cascade, Wu et al., June 2026** — https://arxiv.org/abs/2606.22840
  The interactive cascade quoted in section 3.4. It reports cost, latency, and a quality gate together. Honest note: its 100% against 95% pass rate is one task on a 20-task benchmark.

- **Evaluate model router for your workload, Microsoft Learn, August 2026** — https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/evaluate-model-router
  Methodology: https://github.com/microsoft-foundry/Model-Router-Auto-Evaluation
  The clearest published process for gating a model change, and the source of section 3.4's four steps. Results use bootstrap resampling, with 1,000 resamples and a 95% interval.
  The companion concepts page states a routing quality budget. One mode accepts models within 1% to 2% of the best quality for a prompt. Another accepts 5% to 6%. It also warns that the smallest model in the pool limits the effective context window.

- **Gateway routing vocabulary, for config key names.** Check the version before you copy any of these.
  - https://docs.litellm.ai/docs/routing
    `routing_strategy` accepts `simple-shuffle`, `least-busy`, `usage-based-routing`, `latency-based-routing`, `rate-limit-aware`, `rate-limit-aware-v2`, `cost-based-routing`. These do load balancing and failover, not quality routing. `cost-based-routing` picks the cheapest deployment, not the cheapest adequate model.
  - https://portkey.ai/docs/product/ai-gateway/conditional-routing
    Routes on metadata you supply, with `$eq`, `$in`, `$regex`, and similar operators. It does not classify difficulty.
  - https://openrouter.ai/docs/guides/routing/routers/auto-router
    Read it next to the LLMRouterBench result above. Its auto router ranks models by total spend across users over a recent window. That is a different goal from answering your query correctly.

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
  no cached price in the sheet → cost looks flat → rolling rule is blind

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
  budget_guard.py --simulate --role cache_demo    → Story 1: alerts at 52, 59
  budget_guard.py --simulate --role cache_demo --cache-floor 0.90 → fires at 51
  budget_guard.py --simulate --role cache_demo --no-cache-rule    → symptom only
```

# Phase 5B — Measuring it, promising it, and degrading well

Part A kept the client from making things worse. This part is about knowing whether anything is wrong at all.

That is harder for an LLM feature than for an ordinary service, for one reason worth stating before any of the detail. An ordinary service is up or down. An LLM feature can be **up, fast, and wrong**, and every dashboard you already have will be green through it.

This part also pays four debts. Phase 1 promised a telemetry schema, Phase 2 promised the stream-freeze metric, Phase 4 promised the operating-point signals, and Phase 0 promised that the numbers would eventually become an alert.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  5.4  SLOs                     — four indicators, error budgets, burn    │
│  5.5  The run record           — what to store, under which names       │
│  5.6  Fallbacks                — the pattern you will reach for, and    │
│                                  usually should not                      │
└──────────────────────────────────────────────────────────────────────────┘
```

Part A is a prerequisite. Six of the seven exercises run offline.

Time: 2 to 3 hours.

---

## 5.4 — SLOs for a thing that can be up, fast, and wrong

Why this matters: every phase so far produced numbers. This section turns them into a promise you can be held to, and an alert that fires at the right time rather than every time.

### The framework already has a slot for quality

Standard site-reliability practice defines several indicator types, and one of them is **quality**, defined as the proportion of responses served in an undegraded state. There is also a **correctness** indicator: was the right answer returned.

That matters because an LLM feature has a failure mode ordinary services do not. It can be up, fast, and wrong. A truncated answer is a 200 OK. A silently downgraded fallback model is a 200 OK. Your uptime dashboard is green through both.

So Phase 5 uses four indicators, and `slo_report.py` computes all four:

```
┌───────────────┬──────────────────────────────┬────────────────────────────┐
│ indicator     │ good event                   │ what it catches            │
├───────────────┼──────────────────────────────┼────────────────────────────┤
│ availability  │ the call returned            │ outages                    │
│ TTFT          │ first token inside the target│ queueing, prompt bloat,    │
│               │                              │ cache regressions          │
│ smoothness    │ no gap above the target      │ the Phase 2 stream freeze  │
│ completeness  │ finish_reason is not "length"│ truncation, which every    │
│               │                              │ uptime metric calls a win  │
└───────────────┴──────────────────────────────┴────────────────────────────┘
```

Run it:

```
python phase05_operations/slo_report.py --demo
```

```
┌────────────────────────┬─────────┬─────────┬─────────┬──────────────────┐
│ indicator              │ target  │ actual  │ verdict │ budget used      │
├────────────────────────┼─────────┼─────────┼─────────┼──────────────────┤
│ availability           │ 99.50%  │ 99.30%  │  FAIL   │   140% ########## │
│ TTFT <= 1000ms         │ 95.00%  │ 99.60%  │  PASS   │     8%            │
│ no freeze > 500ms      │ 99.00%  │ 89.93%  │  FAIL   │  1007% ########## │
│ answer completed       │ 99.00%  │ 98.19%  │  FAIL   │   181% ########## │
└────────────────────────┴─────────┴─────────┴─────────┴──────────────────┘
```

The demo contains one deliberate incident: a stretch where the stream freezes. Read the TTFT row. It **passes at 99.6%**. The incident is invisible there and barely dents availability, and it is a ten-times budget overrun on the indicator built to catch it.

### Do not set the target to 100%

The published reasons are worth repeating because someone in the room will ask:

- Users cannot experience 100% anyway, because their own network and device fail.
- Each extra nine costs more while the value to the user approaches zero. One source estimates an incremental reliability improvement can cost **100 times** the previous increment.
- The largest source of outages is change, so a 100% target means never shipping.
- A 100% target leaves no budget, which means you can only ever be reactive.

The error budget is simply 100% minus your target, and it is permission to spend. At 99.9% over 30 days you may be bad for about 43 minutes.

### Use several percentiles, not one

The established pattern is a ladder, and it transfers directly to TTFT:

```
  90% of requests under X
  99% of requests under 10X
  99.9% of requests under 100X
```

A single p95 target hides the shape of the tail. A ladder says what the tail is allowed to look like.

**Pair every latency number with a token count.** One provider's own latency guidance is blunt about it:

> A 5-second total time that generates 2,000 tokens is very different from a 5-second total time that generates 50 tokens. Latency without token context isn't actionable.

And the corollary, from the same page: a rise in total latency is often **fully explained** by longer outputs, not by a slower system. Check the token counts before you declare a latency regression. Your run record has both.

The decomposition they publish is the one Phase 1 taught you:

```
  total = TTFT + (time between tokens × tokens generated)
```

### Burn-rate alerting, with the published numbers

An SLO that only reports monthly is a report, not an alert. Burn rate is how fast you are consuming the budget relative to the period.

```
  burn 1     the budget lasts exactly the 30-day window
  burn 10    it is gone in 3 days
  burn 1000  it is gone in 43 minutes
```

The standard recipe uses two windows at once. The long window decides severity; the short window confirms the problem is still happening, so a spike that already ended does not page anyone.

```
┌──────────┬──────────────┬───────────────┬───────────┬─────────────────────┐
│ action   │ long window  │ short window  │ burn rate │ budget consumed     │
├──────────┼──────────────┼───────────────┼───────────┼─────────────────────┤
│ page     │ 1 hour       │ 5 minutes     │ 14.4      │ 2%                  │
│ page     │ 6 hours      │ 30 minutes    │ 6         │ 5%                  │
│ ticket   │ 3 days       │ 6 hours       │ 1         │ 10%                 │
└──────────┴──────────────┴───────────────┴───────────┴─────────────────────┘
```

Those figures are for a 99.9% target over 30 days. The sizing rule is that the short window is **one twelfth** of the long window.

`slo_report.py --window-minutes` gives you the two-window view. In the demo, the freeze indicator fails over the whole period and **passes** over the last 300 minutes, because the incident had already ended. That is the difference between a page and a post-incident note.

### Putting a quality score in the quality slot

This is where LLM practice is actually heading, and one observability product already ships it: an indicator whose good event is **an evaluation score reaching a threshold**, sitting next to availability and latency, alerted with the same 14.4, 6 and 1 burn tiers.

The design detail worth copying: the indicator is not the mean score. It is the **proportion of records that clear a threshold**. A continuous score has no error budget. A good-event ratio does.

**Two limits you must state before anyone promises a number.**

**A judge cannot support a very tight quality SLO.** The best-known study of model-as-judge reports about **85%** agreement with human experts, against **81%** agreement between two humans. A judge that disagrees with people roughly 15% of the time cannot certify a 99.9% quality target on individual requests. It can support a target on an aggregate rate across many requests, which is a different and achievable claim.

**Per-call quality collapses over multi-step tasks.** If each step succeeds independently at 75%, a task needing three consecutive correct steps succeeds about **42%** of the time. Set the SLO on the outcome your user cares about, not on the step.

### The way a latency SLO gets gamed

A 2024 paper points out two ways to improve a naive TTFT and inter-token SLO without helping anyone:

1. **Delay some tokens deliberately.** Smoothing the stream improves the inter-token measurement.
2. **Abandon requests that will miss the target.** Dropping the slow ones improves every percentile.

Both make the dashboard better and the product worse. The defence is to keep availability and completeness beside the latency indicators, which is why `slo_report.py` prints four rows rather than one.

### And faster is not always better

Here is the result that should change how you set a TTFT target. A 2026 controlled study, 240 participants, varied time to first token at 2, 9 and 20 seconds across two task types.

```
  participants who noticed the delay
     2s   29.3%  (creation)   23.7%  (advice)
     9s   60.5%               73.0%
    20s   80.0%               82.9%

  how thoughtful and useful they rated the output
     2s   LOWEST
     9s   higher
    20s   higher
```

Participants who waited 2 seconds rated the answers **less thoughtful and less useful** than those who waited 9 or 20 seconds. The authors conclude that latency is "a tunable design variable", and flag the obvious ethical problem: deliberately slowing a response to seem more considered is manipulation.

Take the engineering lesson and leave the manipulation. Below some point, spending engineering effort on TTFT stops buying user-perceived quality. Find that point for your product instead of assuming lower is always better.

**Two anchors for the other end.** Human conversation has a modal gap between turns of about **200 milliseconds**, which is the right target for a voice product measuring end of speech to first audio. Adults read continuous prose at roughly **238 words per minute**, which puts a floor on how slowly you can stream text before reading becomes uncomfortable.

**No major provider publishes a latency target.** They publish measurement frameworks and decline to guarantee. One provider's status page reports about 99.94% for its APIs over a recent 90-day window, with a disclaimer that the figure aggregates across tiers and models and that your own availability may differ. Treat that as your dependency's floor, not your product's ceiling.

**The sentence to remember:** an LLM feature can be up, fast, and wrong, so an SLO with only availability and latency measures three quarters of nothing.

**The trap:** a single monthly SLO report. It tells you that you failed, never that you are failing. Burn rate over two windows is the difference.

**Try this now:** run `python phase05_operations/slo_report.py --demo --window-minutes 300` and compare the freeze row across the two tables. Then decide which of the two would have paged you.
---

## 5.5 — The run record (what to store, under which names)

Why this matters: four earlier phases ended by telling you to record something. This section is the schema, and it pays those debts. It is also where you find out that the standard exists, defines more than you expect, and is ignored by almost every library that claims to implement it.

### What the standard actually says

The generative-AI semantic conventions define an inference span with 46 attributes. Only **two** are required: the operation name and the provider name. The span is named `{operation} {model}`, for example `chat gpt-4`.

One rule about span lifetime has a consequence nobody expects:

> If a transient issue happened and the request was retried automatically, the corresponding span SHOULD cover the duration of the logical operation with **all retries**.

Combine that with the general rule that errors which were retried and handled should not be recorded, and with your SDK's default of two automatic retries from Phase 5.3, and you get this:

**By default, your 429s are invisible.** The SDK retries twice inside one span, succeeds on the third attempt, and nothing in your telemetry says the provider ever pushed back. If you need rate-limit visibility, set `max_retries=0` and retry yourself, or instrument the HTTP layer beneath the SDK.

### The naming decision that tells you the spec is serious

The spec defines a first-token signal, and the name is the lesson:

```
  client side   gen_ai.response.time_to_first_chunk       seconds, a double
  server side   gen_ai.server.time_to_first_token
```

**Chunk on the client. Token on the server.** A client watching a stream cannot see tokens. It sees chunks, and a chunk may carry several tokens, or none at all. Providers send ping events, empty deltas, and content blocks that open and close with nothing between them. One provider even adds padding to normalise chunk sizes as a side-channel mitigation, so you cannot infer token count from chunk bytes either.

So a client that reports "time to first token" is claiming to measure something it cannot observe. The spec refuses to make that claim, and `run_recorder.py` now follows it.

I got this wrong in the first version of that file. It invented a name, `app.gen_ai.ttft_ms`, on the assumption that the spec had no latency attribute. The spec has one, it is in seconds rather than milliseconds, and the code and its tests are corrected.

There are matching histograms, `gen_ai.client.operation.time_to_first_chunk` and `gen_ai.client.operation.time_per_output_chunk`, both in seconds. One caution if you adopt the second: its recommended buckets start at 10ms and then double, while real inter-chunk gaps cluster between 10 and 50ms, so nearly everything lands in the first two buckets. Override the boundaries.

### The standard is not implemented, and you can check

The specification repository publishes a generated conformance report: 13 real client libraries run against a mock server, with the telemetry captured and validated.

```
  gen_ai.operation.name        12-13 of 13 libraries
  gen_ai.usage.input_tokens    12-13 of 13
  gen_ai.response.finish_reasons  12-13 of 13
  gen_ai.response.time_to_first_chunk        ZERO of 13
  gen_ai.request.stream                      one of 13
  gen_ai.request.temperature                 one of 13
```

This is not "untested". The reference scenario for one provider **does** exercise streaming, with `stream=True` and usage included, and still never sets the first-token attribute. The reference implementation does not follow its own recommendation.

**So plan to instrument latency yourself.** That is what `run_recorder.py` is.

### Everyone means something different by "inter-token latency"

Before you compare any two latency numbers, find out which definition produced them. Reading the benchmark harnesses shipped by the serving engines and the GPU vendor tools, there are two incompatible meanings in circulation, and they share a name.

```
┌────────────────────┬──────────────────────────────────────────────────────┐
│ definition A       │ the gap between two CHUNKS. One sample per chunk.    │
│                    │ Its p99 catches a single slow chunk.                 │
│ definition B       │ (total - ttft) / (tokens - 1). One sample per         │
│                    │ REQUEST, already averaged. Its p99 cannot see a      │
│                    │ single slow chunk, because the average absorbed it.  │
└────────────────────┴──────────────────────────────────────────────────────┘
```

One serving engine's harness calls definition A "ITL". One GPU vendor's tool calls definition A "ICL" and reserves "ITL" for definition B. That vendor's own documentation states the distinction plainly: streaming chunks can contain multiple tokens, so one metric uses token count and the other uses chunk arrival times.

One serving engine contradicts **itself**: its inter-token metric appends one sample per engine iteration even when an iteration emits several tokens under speculative decoding, while its time-per-output-token metric divides by tokens. On that server the mean of the first does not equal the second.

**Pick one definition, write it down beside the metric, and never compare across tools without checking.** This is why Phase 4 insisted on one client against both servers.

### Recording failures so you can tell them apart later

The spec defines `error.type` and enumerates exactly one well-known value, `_OTHER`. You must define your own vocabulary, and the common instrumentation fills it with the exception class name rather than anything semantic.

Four failures, represented three different ways:

```
┌──────────────────┬─────────────────────────────────────────────────────────┐
│ timeout          │ error.type set, span status Error                       │
│ 429              │ usually INVISIBLE: retried inside the span              │
│ truncation       │ NOT an error. finish_reasons = ["length"],              │
│                  │ status "incomplete". A 200 OK.                          │
│ content filter   │ ASYMMETRIC. A filtered PROMPT is an HTTP 400 error.     │
│                  │ A filtered COMPLETION is a 200 with a finish reason.    │
└──────────────────┴─────────────────────────────────────────────────────────┘
```

The truncation row is the one that matters most, and `run_recorder.py` asserts it in a test. If you map `finish_reason == "length"` to an error, your error rate counts every long answer as an outage and your real error rate disappears into the noise. Use the status field: completed, incomplete, or failed.

One more rule worth implementing. If a stream ends before a finish reason arrives, the spec says to report `error` **in that position** rather than omitting it. Silence and failure must not look the same.

### Attribution: four axes, and only three have attribute names

When quality drops, the question is always the same. What changed? There are four possible answers and the standard covers three.

```
  the MODEL      gen_ai.request.model  AND  gen_ai.response.model
  the PROMPT     gen_ai.prompt.name    AND  gen_ai.prompt.version
  the DATA       no attribute exists. Invent one.
  the SERVING    no attribute exists. One provider offers a fingerprint.
  INFRASTRUCTURE
```

**Record both model fields and alert when they diverge.** The request field is what you asked for; the response field is what answered. They differ when the provider routes elsewhere, and that divergence is the cheapest silent-change detector you can build. `run_recorder.py` now takes both, and a test asserts they are recorded separately.

**The fourth axis is real, and one provider documents it with unusual honesty.** Pinning a model id does not pin behaviour:

> Model weights are fixed for a given ID, but the serving infrastructure around the model can change over time. If you notice unexpected behavioral differences on a previously stable model ID, an infrastructure update is the most likely cause.

Phase 5.6 cited a postmortem where exactly that happened: three infrastructure bugs degraded output for weeks with no model, prompt, or data change.

**There is no attribute for which corpus version your retrieval returned.** The spec has a data-source identifier, not a version. If your knowledge base changes, you must invent the key yourself. Do it before you need it.

### Your noise floor

Before attributing any change, subtract the noise. A 2025 investigation ran 1,000 completions at **temperature 0** on a shared endpoint and got **80 unique completions**, with divergence first appearing around the 103rd token. The cause is that batch size varies with load and the kernels are not batch-invariant.

So roughly 8% of your completions can differ from the most common one with nothing changed at all. Any quality alert that fires below that threshold is firing on physics.

And on sample size: to detect a 3 percentage-point difference at 95% confidence with 80% power, published arithmetic puts the requirement near **1,000 independent questions**. A 50-item eval set cannot see a 3-point regression.

### What to record, and what it costs

The spec gives three patterns for prompt and completion content, and is explicit about which belongs where:

1. **Do not record content.** The default.
2. **Record it on span attributes.** Suited to pre-production.
3. **Store content externally and record a reference.** Recommended for production.

I measured the difference on realistic prose, encoded as the wire format, gzipped, averaged over five seeds:

```
┌──────────────────────┬──────────────────┬──────────────────────────────┐
│ prompt size          │ metadata only    │ with prompt and completion   │
├──────────────────────┼──────────────────┼──────────────────────────────┤
│ 500 in / 150 out     │  107 B per span  │  1,210 B per span   (11x)    │
│ 4,000 in / 500 out   │  109 B per span  │  6,932 B per span   (64x)    │
│ 30,000 in / 1,000 out│  110 B per span  │ 47,156 B per span  (430x)    │
└──────────────────────┴──────────────────┴──────────────────────────────┘
```

**Metadata cost is flat at roughly 1,450 uncompressed bytes per span regardless of prompt size.** The span shape does not grow. Only content does, and for a retrieval-sized prompt it costs 430 times more.

At ten requests per second, that is about 2.8 GB a month for metadata against 1,222 GB with content.

**A trap that follows from those sizes.** The default collector receive limit is 4 MiB per request and the default export batch is 512 spans. At 4,000 input tokens with content, 512 spans is roughly 11 MB, which exceeds the limit. Turning on content capture with default batch settings silently fails to export on any retrieval-sized workload. Lower the batch size or raise the limit.

**How much bigger is an LLM span?** Two unrelated codebases, a vendor blog and an open-source tracing project, independently arrive at roughly **50 KB per LLM span** as a working figure. A conventional tracing project documents roughly **500 bytes** for an ordinary span. That is two orders of magnitude.

One vendor prices the difference on a single page, at the same retention window: **$350 per million** LLM spans against **$1.70 per million** ordinary indexed spans. Roughly 206 times, same company, same page. Prompts and completions are a different cost class, and the market has priced it.

### What to sample, and the trap in how

The only published head-sampling recommendation I could find is straightforward:

```
  development and staging          keep everything
  production, low or medium load   keep everything
  production, high load            head sample 10%, then tail sample at the
                                   collector for errors and slow requests
```

Two rules go with it.

**Sample the spans, keep the metrics whole.** One vendor's sampling is explicitly documented as not affecting token and cost metrics, which stay based on 100% of traffic. My measurements say why that split works: metadata is flat at about 1,450 bytes per span no matter how large the prompt is, so counters and latency histograms are cheap enough to keep complete while you sample the expensive content.

**Use parent-based ratio sampling, never bare ratio sampling.** With the plain ratio sampler, each span is sampled independently, which shreds a multi-span agent trace into disconnected fragments. An agent loop is exactly the shape that breaks.

And the sentence to quote when someone objects to sampling at all:

> Sampling 20% of traces doesn't mean you only see 20% of failures. It means you see a statistically representative sample of your application's behaviour.

Note what no tool ships: **a default sample rate for LLM traces**. Every platform I checked defaults to keeping everything and leaves the rate to you. That is a decision delegated, not a decision made.

**And the gap you will hit.** The spec recommends storing content externally and recording a reference, and the section describing how to record that reference is, at the commit I read, literally marked `TODO`. There is no standard attribute for the pointer. Invent one, namespaced, and write down that you did.

### The minimum useful record

Everything above reduces to this. `run_recorder.py` writes it, `slo_report.py` reads it.

```
  identity     model requested, model that answered, provider, route,
               prompt name and version
  latency      time to first chunk, total, time per output token,
               inter-chunk p50 and p99, WORST inter-chunk gap
  tokens       uncached in, cached in, cache write, out, reasoning
  outcome      finish reason, status, error type
  money        true cost, and the naive cost for comparison
  derived      cache hit rate, stored rather than computed at query time
```

One production write-up gives the best reason for the outcome fields, and it is broader than it first appears: record all errors, **not just when the call failed, but when its result was invalid and caused an error downstream**. An LLM call that returns unparseable JSON is a success at the HTTP layer and a failure at the product layer. Only your record can tell those apart.

**The sentence to remember:** the client sees chunks, the server sees tokens, and any metric that confuses the two is comparing numbers that were never the same quantity.

**The trap:** mapping a finish reason of "length" to an error. Truncation is a completed request with an incomplete status, and treating it as an outage buries your real error rate.

**Try this now:** run `python phase05_operations/run_recorder.py --self-test` and read the check named "first-token uses the SPEC name, not an invented one". That test exists because the first version of this file invented one.
---

## 5.6 — Fallbacks (the pattern you will reach for, and usually should not)

Why this matters: when the provider fails, everyone's instinct is the same. Send it somewhere else. That instinct has a well-documented failure history, and the LLM version is worse than the general case because the fallback can succeed and still be wrong.

### Start with the counter-argument

A large cloud engineering organisation publishes a piece arguing against fallback specifically. It is worth reading before you write any, and its central story is from around 2001.

Their retail site cached shipping speeds on each web server, and fell back to the database when the cache failed. One day the caches all failed at about the same time. Every web server went to the database directly, the database locked up, and:

> The fallback turned a partial website outage (not being able to display shipping speeds) into a full-site outage (no pages loaded at all) and took down the entire fulfillment network in the back end.

Their diagnosis is one sentence long and it generalises:

> If hitting the database directly was more reliable than going through the cache, why bother with the cache in the first place?

Their five objections, condensed: fallback paths are harder to test, can themselves fail, often make the outage worse, are frequently not worth the risk, and carry latent bugs that surface years later under an unlikely coincidence.

**The test that makes a fallback trustworthy** is the useful part:

> A service must run both the fallback and the non-fallback logic continuously. It must not merely run the fallback case but also treat it as an equally valid source of data.

If your fallback path only executes during an incident, it is not a fallback. It is an untested branch that runs for the first time on your worst day.

### Failover is not fallback, and that distinction saves you

```
┌─────────────────┬──────────────────────────────────────────────────────┐
│ retry           │ same call, same mechanism, again. Section 5.3.       │
│ failover        │ same mechanism, different instance. Usually SAFE,    │
│                 │ because the code path is identical.                  │
│ fallback        │ DIFFERENT mechanism for the same result. This is the │
│                 │ one with the history.                                │
└─────────────────┴──────────────────────────────────────────────────────┘
```

Routing to a second deployment of the same model is failover. Routing to a cheaper model, a cached answer, or a retrieval-only path is fallback. The first is a configuration change. The second is a second product that you now maintain and rarely exercise.

There is a narrow, bounded form of fallback that is defensible: serving the last known good value from the **same** mechanism when it errors. That is not switching mechanisms, and it is bounded by how stale you allow the value to be.

### The LLM version has a failure mode the general case does not

A general fallback either works or errors. An LLM fallback can return a confident, fluent, wrong answer, and nothing in your monitoring turns red.

One vendor's semantic-cache documentation states the risk more plainly than any third-party article:

> Because semantic caching returns responses based on similarity (not exact match), it can surface responses that are incorrect, outdated, or unsafe for the current request.

Its own guidance: start the similarity threshold at **0.05**, and note that a threshold above **0.2** risks mismatches. Also, a semantic cache without a per-user or per-group key is a cross-tenant data leak, since one user's answer can be served to another.

### The evidence that degraded output is real and hard to detect

In September 2025 a major provider published a postmortem on three overlapping infrastructure bugs that degraded output quality. Not availability. Output.

```
  a routing error sent some requests to servers configured for a
  different context window        5 Aug - 18 Sep 2025
  an optimisation occasionally assigned high probability to tokens
  that should rarely appear       25 Aug - 2 Sep 2025
  a compiler bug in mixed-precision probability arithmetic
                                  25 Aug - 12 Sep 2025
```

At the worst hour, **16%** of one model's requests were affected. Two sentences from that postmortem belong on a wall:

> We never reduce model quality due to demand, time of day, or server load.

> The evaluations we ran simply didn't capture the degradation users were reporting, in part because Claude often recovers well from isolated mistakes.

That second one is the whole argument for section 5.4's quality indicator. The provider's own evaluation suite missed a real, weeks-long quality regression. Yours will too, unless quality is an indicator with a budget rather than a number someone checks occasionally.

### Cross-provider failover is not a configuration change

Four things break when you send the same prompt to a different provider.

**1. The prompt is a different prompt.** A study of meaning-preserving format changes, things like separators and casing, measured differences of **up to 76 accuracy points** on one model. More importantly for failover, it found that format performance correlates only weakly between models, and that the relative ordering of two formats is preserved across models only about **57%** of the time. A prompt tuned on provider A carries no guarantee on provider B.

**2. The token count changes, so your cost model and your context headroom are both wrong.** One provider's own documentation states that its newer models' tokenizer produces about **30% more tokens for the same text** than its older ones. That is inside one provider. Across providers the tokenizer is entirely different. Their recommended method is the only reliable one: count the same request twice, once against each model, and compare.

**3. The output contract differs.** Tool schemas use different field names, one provider returns parsed arguments while another returns a JSON string you must parse, and recursive schemas are supported by one and rejected with a 400 by another. Even the hidden system-prompt overhead for tool use varies from about 286 to 804 tokens across models of a single provider.

**4. Forcing a format changes accuracy, in a direction you must measure.** The same study set from Phase 2 is worth recalling here: constraining output helped classification tasks and hurt reasoning tasks. If provider A gives you JSON through a tool call and provider B through a JSON mode, you have changed the contract as well as the model.

### If you build one anyway, build these four things

**Split the fallback by error class.** A context-window overflow needs a larger-context model. A content-policy refusal needs a different policy, or no fallback at all. A 429 needs a different deployment. One production gateway models exactly this, with separate fallback chains per error type. A single catch-all chain sends a context overflow to a model with the same limit.

**Never catch every exception.** One popular framework's fallback helper defaults to handling `Exception`, which means a bug in your own parsing code silently triggers a fallback. That is precisely the latent-bug failure the cloud article warns about. Name the exceptions you mean.

**Make the degraded path visible in the response.** One gateway returns a header saying which step answered: the primary, or fallback number one. Without something equivalent you cannot measure how often you serve degraded output, which means you cannot put it in section 5.4's quality indicator. Your run record already has a `model` field. Populate it with the model that actually answered, not the one you asked for.

**Know that your circuit breakers do not agree with each other.** One vendor documents it plainly: breaker state is approximate because gateway instances do not synchronise. N replicas means N independent breakers, each seeing a fraction of the traffic and each tripping on its own evidence. A published comparison found that independent per-client breakers trip at roughly half the rate you would predict from the global failure rate.

### The honest decision table

```
┌──────────────────────────┬────────────────────────────────────────────┐
│ situation                │ what to do                                 │
├──────────────────────────┼────────────────────────────────────────────┤
│ one deployment is down   │ FAILOVER to another deployment of the same  │
│                          │ model. Safe, same code path.               │
│ the provider is down     │ Fail the request, or serve a bounded stale │
│                          │ answer from the same mechanism, and say so │
│ rate limited             │ Shed and retry later. Section 5.3.         │
│ context overflow         │ Compact. Phase 2 section 2.6. Not a        │
│                          │ different model.                           │
│ budget exceeded          │ Degrade deliberately and log it loudly.    │
│                          │ Phase 3B.                                  │
│ you want a cheaper model │ That is routing, not fallback. Phase 3B,   │
│                          │ and it needs the control group.            │
└──────────────────────────┴────────────────────────────────────────────┘
```

Most rows are not fallback. That is the point.

**The sentence to remember:** failover keeps the mechanism and changes the instance, fallback changes the mechanism, and only the second one has a history of turning a partial outage into a total one.

**The trap:** a fallback path that only runs during incidents. It is untested code executing for the first time under your worst conditions, and on an LLM it can succeed and still be wrong.

**Try this now:** find any fallback in your own code. Answer two questions. Does it run continuously against real traffic, or only on failure? And can you tell from a stored record which path answered?
---

## 🧪 Hands-on lab — part B

Six of seven exercises are offline. Only E13 needs a key.

- [ ] **E8 (offline).** See what an average hides.
  - Run: `python phase05_operations/run_recorder.py --demo --role cache_demo`
  - Expected: ITL p50 about 24ms, max gap 900ms, and a note saying the worst gap is about 38x the median.
  - Teaches: the freeze is invisible in TTFT, in total latency, and in any mean.

- [ ] **E9 (offline).** Find the incident three indicators miss.
  - Run: `python phase05_operations/slo_report.py --demo`
  - Expected: TTFT **passes** at 99.60% while the freeze indicator fails at 89.93% with a burn rate above 10.
  - Teaches: availability and latency measure three quarters of nothing on an LLM feature.

- [ ] **E10 (offline).** Two windows, two different answers.
  - Run: `python phase05_operations/slo_report.py --demo --window-minutes 300`
  - Expected: the freeze indicator fails over the whole period and **passes** over the last 300 minutes, because the incident had already ended.
  - Teaches: the long window sets severity, the short window says whether it is still happening. That difference is a page versus a note.

- [ ] **E11 (offline).** Do the burn-rate arithmetic yourself.
  - For a 99.9% target over 30 days, compute the burn rate implied by a 1% error rate. Then compute how long the budget lasts at that rate.
  - Check your answer against the table in section 5.4, and against the script's own burn output.
  - Teaches: burn rate is a ratio, not a mystery, and it turns a monthly report into an alert.

- [ ] **E12 (offline).** Read the naming decision.
  - Open `otel_attributes` in `run_recorder.py`. Find the comment explaining chunk against token.
  - Then run the self-test and find the check "first-token uses the SPEC name, not an invented one". That test exists because the first version of this file invented one.
  - Answer: why can a client not honestly report time to first **token**?
  - Teaches: a chunk may carry several tokens or none, so the two quantities were never the same.

- [ ] **E13 (UNVERIFIED against a live provider).** Record a real call.
  - Run: `python phase05_operations/run_recorder.py --model <your-model> --role cheap --ledger runs.jsonl`
  - Then: `python phase05_operations/slo_report.py --ledger runs.jsonl`
  - Expected: one JSON object per call, and an SLO table computed from your own traffic rather than a demo.
  - Costs at most: about $0.01.
  - Teaches: the ledger is the deliverable. Everything else reads it.

- [ ] **E14 (offline).** Price your own telemetry before you turn it on.
  - Take your median prompt and completion sizes. Using the table in section 5.5, estimate bytes per span with content and without.
  - Multiply by your request rate to get a monthly figure. Then compare against the flat metadata cost of about 1,450 bytes per span.
  - Teaches: metadata is flat regardless of prompt size; only content grows, and for retrieval-sized prompts it costs hundreds of times more.
---

## 🔍 Check it yourself

1. Open `otel_attributes` in `run_recorder.py`. Two keys use an `app.` prefix. Name both, explain why each one is not on a standard name, and say what would break if you had used an unprefixed `gen_ai.` name instead.
2. In the same function, find the branch handling `finish_reason == "length"`. State what it sets and what it deliberately does **not** set, and describe the metric that would be wrong if you removed that branch.
3. In `slo_report.py`, find `evaluate`. Three of the four indicators compute their denominator from `served` rather than from all rows. Explain why, and name the indicator that does not.
4. In your own telemetry: find where an LLM call is recorded. Does it store the model you **requested**, the model that **answered**, or only one of them? If only one, work out what silent change you currently cannot detect.

---

## ✅ Checkpoint 5B — answer in your own words

1. Show the math. Your quality SLO is 99% over 30 days, measured as the proportion of answers that clear a judge threshold. In the last hour you measured 4% below threshold. (a) Compute the burn rate. (b) State how long the budget lasts at that rate. (c) Using the published table, say whether this should page someone, and what the confirming short window would be.

2. A colleague proposes: "Our quality SLO is 99.9% of answers rated good by our judge." Give two independent reasons that target cannot be supported, using section 5.4. One reason is about the judge, one is about the task shape.

3. This is broken. Your dashboard shows availability at 99.9%, TTFT p95 well inside target, and users are complaining that answers are worse this week. Nothing deployed. (a) Name the fourth attribution axis that could explain this. (b) Name the two telemetry fields whose divergence would confirm it. (c) State the noise floor you must clear before declaring a regression, and where that number comes from. (d) Say why your existing eval suite may not catch it, citing what a provider said about its own suite.

4. Show the math. Your median request is 4,000 input and 500 output tokens, and you serve 10 requests per second. (a) Using section 5.5, estimate the monthly telemetry volume with content capture on and off. (b) State the ratio. (c) Your collector accepts 4 MiB per request and batches 512 spans. State whether that works with content on, and what you would change.

5. Design it. You must alert on silent quality regressions. Write the design. Cover: the indicator and how a continuous score becomes a good-event ratio, the two windows and burn rates, the noise floor you subtract, the minimum size of your labelled set and why, and the one thing you will record so that a firing alert can be attributed rather than merely observed.

6. A colleague says: "We will fall back to a cheaper model when the primary fails, so we are covered." Give three objections from section 5.6. One is about testing, one is about what a failed fallback looks like on an LLM specifically, and one is about the default behaviour of a popular fallback helper.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) The budget is 1%. A 4% bad rate is a burn rate of 4. (b) At burn 4 the 30-day budget lasts 30/4, about 7.5 days. (c) The published page thresholds are 14.4 and 6. A burn of 4 clears neither, so this is a ticket rather than a page; the ticket tier uses a 3-day long window confirmed by a 6-hour short window. If the rate rose to 6% it would cross the 6x page threshold on the 6-hour window, confirmed over 30 minutes.

2. First, the judge. The best-known study puts model-judge agreement with human experts at about 85%, against 81% agreement between two humans. An instrument that disagrees with people roughly 15% of the time cannot certify 99.9% on individual requests. Second, the task shape. If the user's task needs several steps, per-call quality compounds: at 75% per step, three consecutive steps succeed about 42% of the time. Set the target on the outcome the user experiences, and as an aggregate rate rather than a per-request guarantee.

3. (a) The serving infrastructure. Model weights are fixed for a given id, but routing, classifiers and sampling logic around the model can change. (b) `gen_ai.request.model` against `gen_ai.response.model`. Divergence means the provider answered with something other than what you asked for. (c) About 8%. A study ran 1,000 completions at temperature 0 on a shared endpoint and got 80 unique completions, because batch size varies with load and the kernels are not batch-invariant. (d) A provider published a postmortem on three infrastructure bugs that degraded output for weeks and said plainly that its own evaluations did not capture the degradation users reported, partly because the model recovers well from isolated mistakes and the evaluations were noisy.

4. (a) At 4,000 in and 500 out, roughly 109 bytes per span compressed without content and about 6,932 with. At 10 requests per second that is about 2.8 GB a month against about 179 GB. (b) Roughly 64 times. (c) It does not work. Uncompressed, that span is about 21 KB, so 512 of them is about 11 MB against a 4 MiB limit, and exports fail silently. Lower the batch size to under 200, or raise the receive limit, or move content to external storage and record a reference.

5. The indicator is the proportion of sampled records whose evaluation score clears a stated threshold, not the mean score, because a continuous score has no error budget and a ratio does. Alert on two windows: a fast burn of 14.4 over one hour confirmed over five minutes to page, and a slow burn of 1 over three days confirmed over six hours to file a ticket. Subtract the roughly 8% same-input variation before treating a change as real. The labelled set needs roughly 1,000 independent items to detect a 3 percentage-point difference at 95% confidence with 80% power, so a 50-item set cannot see a small regression. Record the prompt name and version alongside the requested and answering model, so that a firing alert can be attributed to a prompt change, a model swap, or neither.

6. First, a fallback path that only runs during incidents is untested code executing for the first time under your worst conditions; the published rule is that both paths must run continuously against real traffic. Second, on an LLM a fallback can succeed and still be wrong, returning a confident, fluent, incorrect answer with nothing in monitoring turning red, which is why a semantic cache vendor warns its own feature can surface responses that are incorrect, outdated or unsafe. Third, a popular fallback helper defaults to catching `Exception`, so a bug in your own parsing code silently triggers the fallback rather than surfacing as an error.

</details>
---

## References & Further Learning

Part A carries the retry, rate-limit and timeout references. This document carries SLOs, telemetry and fallback. All checked 2026-09-14.

### SLOs and alerting

**Alerting on SLOs** — Google SRE Workbook, chapter 5. https://sre.google/workbook/alerting-on-slos/
The origin of the burn-rate numbers every observability product copies. Read table 5-8 first, then table 5-4, and skip the five approaches that exist to motivate the sixth.
The recommended parameters for a 99.9% target over 30 days: page at burn **14.4** over a 1-hour window confirmed over 5 minutes, page at **6** over 6 hours confirmed over 30 minutes, ticket at **1** over 3 days confirmed over 6 hours. The sizing rule is that the short window is **one twelfth** of the long one.

**Implementing SLOs** — Google SRE Workbook, chapter 2. https://sre.google/workbook/implementing-slos/
The only place in the canon that names **Quality** as an indicator type, defined as the proportion of responses served in an undegraded state. That is the slot an LLM quality metric goes into. It also gives the four reasons a 100% target is wrong, which you will need in the room.

**Service Level Objectives** — Google SRE Book, chapter 4. https://sre.google/sre-book/service-level-objectives/
Read "Indicators in Practice" for the multi-percentile pattern, 90% under X, 99% under 10X, 99.9% under 100X. It transfers directly to time to first token, and it is better than a single p95 because it says what the tail is allowed to look like.

**A product shipping an eval-score SLI** — https://pydantic.dev/docs/logfire/observe/service-levels/
Worth reading as evidence of where practice is going: an indicator whose good event is an evaluation score reaching a threshold, sitting beside availability and latency, alerted on the same 14.4, 6 and 1 tiers. The design detail to copy is that the indicator is a **proportion clearing a threshold**, not a mean score.

**Judging LLM-as-a-Judge** — https://arxiv.org/abs/2306.05685
Read before you put a number on a judge-based SLO. Model-judge agreement with human experts is about **85%**, against **81%** between two humans, and that 85% figure is for a setup that excludes ties; including them it falls to the mid sixties. It also documents position, verbosity and self-preference bias.
The consequence: a judge cannot certify a very tight per-request quality target. It can support an aggregate rate.

**Measuring latency** — https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/latency
The best published statement of how to measure, and the decomposition Phase 1 taught: total equals time to first token plus time between tokens multiplied by tokens generated. Its operational rule is the one to quote: always pair a latency metric with a token count, because a rise in total latency is often fully explained by longer output rather than a slower system.
Verified absence: it states no absolute millisecond target. No major provider publishes a latency SLO.

**Revisiting Service Level Objectives and System Level Metrics in LLM Serving** — https://arxiv.org/abs/2410.14257
Read it for the two ways a naive latency SLO is gamed: deliberately delaying tokens smooths the inter-token metric, and abandoning requests that will miss the target improves every percentile. Both improve the dashboard and hurt the product.

**The Impact of Response Latency and Task Type on Human-LLM Interaction** — https://arxiv.org/abs/2604.06183
The result that should change your TTFT target. 240 participants, time to first token at 2, 9 and 20 seconds. Participants who waited 2 seconds rated the answers **less thoughtful and less useful** than those who waited longer. The authors frame latency as a tunable design variable and flag the ethics of exploiting that. Take the engineering lesson, leave the manipulation.

**The classic thresholds and the two anchors.** 0.1 seconds feels instantaneous, 1 second keeps a train of thought, 10 seconds is the limit of attention: https://www.nngroup.com/articles/response-times-3-important-limits/, and cite the original, Miller 1968, not the popular restatement. For voice, human conversation has a modal gap between turns of about **200 milliseconds** (Levinson 2016, *Trends in Cognitive Sciences*). For text, adults read prose at roughly **238 words per minute** (Brysbaert 2019, a meta-analysis of 190 studies), which floors how slowly you can stream.

### Telemetry

**The GenAI semantic conventions** — https://github.com/open-telemetry/semantic-conventions-genai
Read the YAML models rather than the generated Markdown, and cite a commit, because there is no released version and every attribute is development stability.
What to take: only two attributes are required; the span is named `{operation} {model}`; the span covers **all retries**, which is why your 429s are invisible by default; and the client-side latency attribute is `gen_ai.response.time_to_first_chunk`, in **seconds**.
The naming decision is the lesson. Client side says chunk, server side says token, because a client cannot see tokens.

**The conformance report in the same repository** — `reference/reports/inference-span.md`
The most useful file in the repo, because it is generated by running 13 real client libraries against a mock server. Token counts and finish reasons appear in 12 or 13 of 13. The first-token attribute appears in **zero of 13**, including in a scenario that does exercise streaming. Plan to instrument latency yourself.

**Model identifiers and versions** — https://platform.claude.com/docs/en/build-with-claude/model-ids-and-versions
The most honest provider statement I found, and the reason for the fourth attribution axis: weights are fixed for a given id, but the serving infrastructure around the model can change, and an unexplained behaviour change on a stable id is most likely an infrastructure update.

**A postmortem where quality dropped with no model change** — https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues
Three overlapping infrastructure bugs degraded output for weeks. At the worst hour, 16% of one model's requests were affected. The sentence that justifies a quality indicator: their own evaluations did not capture the degradation users were reporting.

**Defeating Nondeterminism in LLM Inference** — https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/
Your noise floor. 1,000 completions at temperature 0 produced **80 unique completions**, because batch size varies with load and the kernels are not batch-invariant. Subtract this before attributing any change.

**Adding Error Bars to Evals** — https://arxiv.org/abs/2411.00640
How many labelled items you need: roughly **1,000** to detect 3 percentage points at 95% confidence with 80% power. Also warns that changing temperature mid-evaluation can triple the variance of your score.

**A production field list with reasons** — https://www.honeycomb.io/blog/improving-llms-production-observability
The only engineering post I found that shows the attribute-setting code and gives a reason per field. The reason worth copying: record all errors, not just when the call failed, but when its result was invalid and caused an error downstream.

### Fallbacks

**Avoiding fallback in distributed systems** — Amazon Builders' Library.
Read it before writing any fallback. Its 2001 incident is the canonical story: a cache that fell back to the database took the whole site down when all caches failed at once. Its diagnosis generalises in one sentence, and its test is the useful part: both the fallback and the non-fallback path must run continuously against real traffic, or the fallback is untested code that runs for the first time during an incident.
Access note: the canonical URL redirects to a JavaScript site that serves no article text. Read it in a browser.

**A vendor warning about its own feature** — https://learn.microsoft.com/en-us/azure/api-management/azure-openai-semantic-cache-lookup-policy
The strongest published statement that an AI fallback can be worse than an error: a semantic cache returns responses by similarity, so it can surface responses that are incorrect, outdated or unsafe. Its own guidance is to start the threshold at 0.05 and treat above 0.2 as risking mismatches, and to key the cache per user or group unless you want a cross-tenant leak.

**Quantifying sensitivity to spurious features in prompt design** — https://arxiv.org/abs/2310.11324
Why cross-provider failover is not a configuration change. Meaning-preserving format changes produced differences of **up to 76 accuracy points** on one model, and the relative ordering of two formats is preserved across models only about 57% of the time.

**Token counting** — https://platform.claude.com/docs/en/build-with-claude/token-counting
The concrete version of the same problem. One provider's newer models produce about **30% more tokens for the same text** than its older ones. That is inside one provider; across providers the tokenizer is entirely different. Their recommended method is the only reliable one: count the same request twice and compare.

---

## Cheatsheet — part B

```
FOUR INDICATORS (availability + latency measures 3/4 of nothing)
  availability   the call returned
  TTFT           first token inside target
  smoothness     no gap above target      <- the Phase 2 freeze
  completeness   finish_reason != "length" <- a 200 OK every dashboard counts
                                              as a success
  demo result: TTFT PASSES at 99.6% while the freeze SLO fails at 89.9%

ERROR BUDGET AND BURN
  budget = 100% - target. At 99.9%/30d you may be bad ~43 minutes.
  burn 1 -> lasts 30 days | burn 10 -> 3 days | burn 1000 -> 43 minutes
  page    burn 14.4  over 1h   confirmed over 5m    (2% of budget)
  page    burn  6    over 6h   confirmed over 30m   (5%)
  ticket  burn  1    over 3d   confirmed over 6h    (10%)
  short window = 1/12 of the long window
  latency SLO pattern: 90% < X | 99% < 10X | 99.9% < 100X
  ALWAYS PAIR LATENCY WITH A TOKEN COUNT. A latency rise is often just
    longer output.  total = TTFT + (time per token x tokens)

QUALITY AS AN SLI
  good event = proportion of records CLEARING a threshold, never the mean
  judge ceiling: ~85% agreement with humans (81% human-to-human)
    -> a judge cannot certify 99.9% per request. Aggregate rates only.
  pass^k: 75% per step -> ~42% over three steps
  noise floor: ~8% of completions differ at temperature 0 on a shared
    endpoint (1000 runs -> 80 unique). Subtract before attributing.
  sample size: ~1000 items to detect 3 percentage points at 80% power
  a latency SLO is GAMEABLE: delay tokens to smooth ITL, drop slow requests
    to improve every percentile. Keep completeness beside it.
  and faster is not always better: at 2s TTFT users rated answers LESS
    thoughtful than at 9s or 20s (n=240)

TELEMETRY NAMES
  CLIENT says CHUNK. SERVER says TOKEN. A chunk may carry many tokens or none.
    gen_ai.response.time_to_first_chunk     SECONDS, a double
    gen_ai.client.operation.time_per_output_chunk
    gen_ai.server.time_to_first_token
  only TWO attributes are Required: operation.name, provider.name
  span name: "{operation} {model}"
  the span covers ALL RETRIES -> your 429s are INVISIBLE by default
  13 of 13 reference libraries emit ZERO time_to_first_chunk. Instrument it.
  "ITL" means two different things across tools. Write down which you mean.

RECORDING FAILURES
  timeout       error.type + status Error
  429           usually invisible (retried inside the span)
  truncation    NOT an error. finish_reasons ["length"], status "incomplete"
  content filter  ASYMMETRIC: filtered PROMPT = 400, filtered OUTPUT = 200
  stream ended early -> record "error" IN the finish_reasons position

ATTRIBUTION, four axes
  model     gen_ai.request.model AND gen_ai.response.model  <- alert on divergence
  prompt    gen_ai.prompt.name AND .version
  data      NO ATTRIBUTE EXISTS. Invent one.
  serving   NO ATTRIBUTE EXISTS. Pinning a model id does NOT pin behaviour.

TELEMETRY COST (measured, gzipped, per span)
  500/150    metadata 107 B   with content 1,210 B    (11x)
  4k/500     metadata 109 B   with content 6,932 B    (64x)
  30k/1k     metadata 110 B   with content 47,156 B  (430x)
  metadata is FLAT ~1,450 B raw regardless of prompt size
  one vendor prices LLM spans at $350/M against $1.70/M for ordinary spans
  4 MiB collector limit x 512-span default batch FAILS with content on
  sample the SPANS, keep the METRICS at 100%
  use parentbased_traceidratio, never bare traceidratio (it shreds traces)

FALLBACK
  retry    = same call, same mechanism
  failover = same mechanism, different instance      USUALLY SAFE
  fallback = DIFFERENT mechanism                     the one with the history
  the test: does the fallback path run CONTINUOUSLY against real traffic?
  on an LLM a fallback can SUCCEED AND STILL BE WRONG
  split fallback by ERROR CLASS; never catch bare Exception
  record WHICH path answered, or you cannot measure degraded output
  cross-provider is not a config change: format changes move accuracy up to
    76 points, and one provider's newer tokenizer is ~30% more tokens

THE COMMANDS
  run_recorder.py --demo --role cache_demo    see the freeze, offline
  run_recorder.py --model X --ledger runs.jsonl   record real calls
  slo_report.py --demo                        four indicators, offline
  slo_report.py --demo --window-minutes 300   the two-window view
  slo_report.py --ledger runs.jsonl           your own traffic
```

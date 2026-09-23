# Phase 5B — Measuring it, promising it, and degrading well

Part A stopped the client from making an outage worse. This part is about knowing whether anything is wrong at all.

That is harder for an LLM feature than for an ordinary service. An ordinary service is up or down. An LLM feature can be **up, fast, and wrong**, and every dashboard you have stays green.

This part also delivers what earlier phases asked for:

- Phase 1 section 1.6 drafted a target schema for what to log per model call.
- Phase 2 section 2.4 asked you to record inter-token gaps, because an average hides a frozen stream.
- Phase 4 section 4.3 defined the operating point: peak throughput and the TTFT p99 at that load.
- Phase 0 said that Phase 5 covers operations.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  5.4  SLOs                     — four indicators, error budgets, burn    │
│  5.5  The run record           — what to store, under which names        │
│  5.6  Fallbacks                — the pattern you will reach for, and     │
│                                  usually should not                      │
└──────────────────────────────────────────────────────────────────────────┘
```

Part A is a prerequisite, because this part reads the records that the part A client writes. Seven of the eight exercises run offline.

Time: 2 to 3 hours.

---

## 5.4 — SLOs for a thing that can be up, fast, and wrong

Why this matters: every phase so far produced numbers. This section turns them into a promise, and into an alert that fires at the right time.

An SLI, or service level indicator, is a measured ratio of good events to all events. An SLO, or service level objective, is the target for that ratio.

### The framework already has a slot for quality

The Google SRE Workbook defines several SLI types. One is **quality**: the proportion of responses served in an undegraded state. Another is **correctness**: whether the right answer was returned.

An LLM feature needs these types. A truncated answer returns 200 OK. A fallback to a weaker model also returns 200 OK. Your uptime dashboard stays green through both.

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

```bash
python phase05_operations/slo_report.py --demo
```

Output from a run on 2026-09-17:

```
┌────────────────────────┬─────────┬─────────┬─────────┬───────────────────┐
│ indicator              │ target  │ actual  │ verdict │ budget used       │
├────────────────────────┼─────────┼─────────┼─────────┼───────────────────┤
│ availability           │  99.50% │  99.30% │  FAIL   │   140% ########## │
│ TTFT <= 1000ms         │  95.00% │  99.60% │  PASS   │     8%            │
│ no freeze > 500ms      │  99.00% │  89.93% │  FAIL   │  1007% ########## │
│ answer completed       │  99.00% │  98.19% │  FAIL   │   181% ########## │
└────────────────────────┴─────────┴─────────┴─────────┴───────────────────┘
```

The demo ledger has 2,000 records and one deliberate incident, a stretch where the stream freezes. The TTFT row **passes at 99.6%**, so the incident is invisible there. On the freeze indicator, it uses ten times the budget.

The incident does not change availability. Availability fails for another reason. The demo adds a random 0.4% error rate to every record, at `slo_report.py:78`, against a 99.5% target.

### Do not set the target to 100%

The Google SRE Workbook gives four reasons:

- Users cannot experience 100%, because their own network and device fail.
- Each extra nine costs more, and its value to users approaches zero. One source estimates that each step can cost **100 times** the step before it.
- Most outages come from change. A 100% target means you never ship.
- A 100% target leaves no budget, so you can only react.

The error budget is 100% minus your target. It is the failure you are allowed. At 99.9% over 30 days, that is about 43 minutes.

### Use several percentiles, not one

The Google SRE Book uses a ladder of percentiles. It applies to TTFT directly:

```
  90% of requests under X
  99% of requests under 10X
  99.9% of requests under 100X
```

A single p95 target hides the shape of the tail. A ladder states what the tail may look like.

**Pair every latency number with a token count.** Microsoft's Azure OpenAI latency guide says so. It uses TTLT, time to last token, for total response time:

> A 5-second TTLT that generates 2,000 tokens is very different from a 5-second TTLT that generates 50 tokens. Latency without token context isn't actionable.

The same page says a rise in total latency is often **fully explained** by longer outputs, not a slower system. Check the token counts before you declare a regression. Your run record has both. The page uses the decomposition from Phase 1:

```
  total = TTFT + (time between tokens × tokens generated)
```

### Burn-rate alerting, with the published numbers

A monthly SLO report is not an alert. The burn rate is how fast you use the budget, relative to the period. At burn rate 1, the budget lasts exactly the period.

```
  burn 1     the budget lasts exactly the 30-day window
  burn 10    it is gone in 3 days
  burn 1000  it is gone in 43 minutes
```

The burn-rate code, from `burn_lines` at `slo_report.py:342-353`, with indentation removed. `rs` is the list of records for one table:

```python
for r in evaluate(rs, args):
    allowed = 1 - r["target"]
    actual_bad = 1 - (r["good"] / r["total"] if r["total"] else 1)
    if allowed <= 0:
        continue
    burn = actual_bad / allowed
    if burn <= 1:
        print(f"  {r['name']:<22} burn {burn:>5.2f}x  budget lasts the period")
    else:
        frac = 1 / burn
        print(f"  {r['name']:<22} burn {burn:>5.2f}x  budget gone after "
              f"{frac:.0%} of the period")
```

In the demo, the freeze indicator prints `burn 10.07x  budget gone after 10% of the period`.

The Google SRE Workbook recipe uses two windows. The long window decides the severity. The short window checks that the problem is still happening, so an ended spike pages nobody.

```
┌──────────┬──────────────┬───────────────┬───────────┬─────────────────────┐
│ action   │ long window  │ short window  │ burn rate │ budget consumed     │
├──────────┼──────────────┼───────────────┼───────────┼─────────────────────┤
│ page     │ 1 hour       │ 5 minutes     │ 14.4      │ 2%                  │
│ page     │ 6 hours      │ 30 minutes    │ 6         │ 5%                  │
│ ticket   │ 3 days       │ 6 hours       │ 1         │ 10%                 │
└──────────┴──────────────┴───────────────┴───────────┴─────────────────────┘
```

These figures are for 99.9% over 30 days. The short window is **one twelfth** of the long one. Check row one: 14.4 × 1 hour ÷ 720 hours = 2%.

`slo_report.py --window-minutes` adds a table for the most recent window. In the demo, the freeze indicator fails over the whole period. It **passes** over the last 300 minutes, because the incident had ended. That is the difference between a page and a review note. The script prints one burn block for each table. The window block uses only the window's records. There, the freeze burn is `0.17x`. Over the whole period it is `10.07x`.

### Putting a quality score in the quality slot

Pydantic Logfire already ships this. Its SLI counts a good event when **an evaluation score reaches a threshold**. It sits next to availability and latency, with the same 14.4, 6 and 1 burn tiers.

Copy one detail. The indicator is not the mean score. It is the **proportion of records that reach a threshold**. A continuous score has no error budget. A ratio of good events has one.

**Two limits apply before anyone promises a number.**

**A judge cannot support a very tight quality SLO.** A judge is a model that scores another model's output. The best-known study, "Judging LLM-as-a-Judge", reports about **85%** agreement with human experts, and **81%** between two humans. Both numbers leave out ties. With ties counted, the same table gives 66% and 63%. A judge that disagrees with people on 15% or more of cases cannot certify 99.9% on single requests. It can support an aggregate rate across many requests.

**Per-step quality drops fast over multi-step tasks.** Take 75% per independent step. Three correct steps in a row then happen 0.75³ ≈ **42%** of the time. Set the SLO on the outcome the user cares about.

### The way a latency SLO gets gamed

A 2024 paper on SLOs in LLM serving shows two ways to game a naive TTFT and inter-token SLO:

1. **Delay some tokens on purpose.** A smoother stream improves the inter-token number.
2. **Drop requests that will miss the target.** Every percentile then improves.

Both improve the dashboard and harm the product. The defence is to report availability and completeness next to latency. So `slo_report.py` prints four rows.

### Faster is not always better

A 2026 controlled study, for ACM CHI 2026, set TTFT to 2, 9 or 20 seconds on two task types. The paper reports 240 participants.

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

After a 2-second wait, participants rated answers **less thoughtful and less useful** than after 9 or 20 seconds. The authors call latency "a tunable design variable" with ethical implications. Slowing answers on purpose, to seem careful, manipulates users. This review checked only the abstract. The count and percentages come from the paper body.

Use the engineering lesson, and reject the manipulation. Below some point, TTFT work stops improving perceived quality. Find that point for your product.

**Two reference points for the other end:**

- In human conversation, the most common gap between turns is about **200 milliseconds**. That is the target for a voice product, from end of speech to first audio.
- Adults read prose at about **238 words per minute**. A stream much slower than that is uncomfortable to read.

**No major provider publishes a latency target.** One provider's status page reports about 99.94% API availability over a recent 90-day window. It says the figure combines tiers and models, and yours may differ. Treat it as the upper limit for your dependency, not as your product's number.

**The sentence to remember:** an LLM feature can be up, fast, and wrong. An SLO with only availability and latency cannot see the wrong answers.

**The trap:** a single monthly SLO report. It tells you that you failed, never that you are failing now. Burn rate over two windows fixes that.

**Try this now:** run `python phase05_operations/slo_report.py --demo --window-minutes 300`. Compare the freeze row in the two tables. Decide which table would have paged you.

---

## 5.5 — The run record (what to store, under which names)

Why this matters: four earlier phases told you to record something. This section gives the schema. A standard for it exists, and most libraries do not implement it.

### What the standard says

The OpenTelemetry GenAI semantic conventions name the fields for LLM telemetry. OpenTelemetry is the open standard for traces, metrics and logs. A span is one timed operation in a trace, with attributes.

The conventions define an inference span with 46 attributes. Only **two** are required: the operation name and the provider name. The span name is `{operation} {model}`, for example `chat gpt-4`.

One rule about span duration matters:

> If a transient issue happened and the request was retried automatically, the corresponding span SHOULD cover the duration of the logical operation with **all retries**.

Add two facts. OpenTelemetry says not to record errors that were retried and handled. Your SDK retries twice by default, as section 5.3 showed.

So **by default, your 429s are invisible.** The SDK retries inside one span and succeeds on the third attempt. Nothing shows that the provider rejected you. For visibility, set `max_retries=0` and retry in your own code, or instrument the HTTP layer below the SDK.

### The naming decision that shows the spec is careful

The spec's first-token name teaches the lesson:

```
  client side   gen_ai.response.time_to_first_chunk       seconds, a double
  server side   gen_ai.server.time_to_first_token
```

**The client says chunk. The server says token.** A client watching a stream sees chunks, not tokens. A chunk may carry several tokens, or none. Providers send ping events, empty deltas, and empty content blocks. One provider pads chunks to similar sizes against side-channel attacks. So chunk bytes do not give the token count either.

A client that reports "time to first token" claims to measure something it cannot see. The spec avoids that claim, and `run_recorder.py` follows the spec.

The first version of `run_recorder.py` got this wrong. It invented `app.gen_ai.ttft_ms`, because the author assumed no spec attribute existed. One exists, in seconds. The code and tests are corrected.

The matching histograms are `gen_ai.client.operation.time_to_first_chunk` and `gen_ai.client.operation.time_per_output_chunk`, in seconds. For the second, the recommended buckets start at 10 ms and double. Real gaps between chunks are mostly 10 to 50 ms, so nearly all samples land in two buckets. Set your own boundaries.

### The standard is not implemented, and you can check

The specification repository publishes a generated conformance report. It runs 13 real client libraries against a mock server and validates their telemetry.

```
  gen_ai.operation.name        12-13 of 13 libraries
  gen_ai.usage.input_tokens    12-13 of 13
  gen_ai.response.finish_reasons  12-13 of 13
  gen_ai.response.time_to_first_chunk        ZERO of 13
  gen_ai.request.stream                      one of 13
  gen_ai.request.temperature                 one of 13
```

The reference scenario for one provider **does** stream, with `stream=True` and usage included. It still never sets the first-token attribute. So the reference implementation does not follow its own recommendation.

**Plan to instrument latency in your own code.** `run_recorder.py` does that.

### "Inter-token latency" has two meanings

Before you compare two latency numbers, find the definition behind each. Serving-engine benchmarks and a GPU vendor's tool use one name for two things:

```
┌────────────────────┬──────────────────────────────────────────────────────┐
│ definition A       │ the gap between two CHUNKS. One sample per chunk.    │
│                    │ Its p99 catches a single slow chunk.                 │
│ definition B       │ (total - ttft) / (tokens - 1). One sample per        │
│                    │ REQUEST, already averaged. Its p99 cannot see a      │
│                    │ single slow chunk, because the average absorbed it.  │
└────────────────────┴──────────────────────────────────────────────────────┘
```

One serving engine's benchmark calls definition A "ITL". The GPU vendor's tool calls definition A "ICL" and definition B "ITL". Its documentation explains that chunks can hold several tokens, so one metric counts tokens and the other times chunks.

One serving engine even disagrees with **itself**. Its inter-token metric adds one sample per engine iteration. Under speculative decoding, one iteration can emit several tokens. Its time-per-output-token metric divides by tokens. So the two means differ on that server.

**Pick one definition, and write it next to the metric.** For this reason, Phase 4 section 4.3 used one client for both servers.

### Record failures so you can tell them apart later

The spec's `error.type` lists one well-known value, `_OTHER`. You must define your own values. Common instrumentation stores the exception class name, which says little.

Four failures appear in three forms:

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

The truncation row matters most. If you map `finish_reason == "length"` to an error, every long answer counts as an outage, and real errors get lost.

```python
# WRONG: a truncated answer counted as a failure.
if rec.error_kind or rec.finish_reason == "length":
    attrs["error.type"] = rec.error_kind
    attrs["gen_ai.response.status"] = "failed"

# RIGHT: from run_recorder.py:253-259, unchanged.
if rec.error_kind:
    attrs["error.type"] = rec.error_kind
    attrs["gen_ai.response.status"] = "failed"
elif rec.finish_reason == "length":
    attrs["gen_ai.response.status"] = "incomplete"
else:
    attrs["gen_ai.response.status"] = "completed"
```

This review ran the WRONG version in a copy on 2026-09-17. The self-test printed `[FAIL] a truncated answer is 'incomplete', not an error` and `1 FAILED`. The `slo_report.py` demo ledger has 14 errors and 36 truncations in 2,000 records. With the same rule, availability drops from 99.30% to 97.50%. The burn against 99.5% rises from 1.40x to 5.00x. E15 repeats the self-test run.

Use the status field: completed, incomplete, or failed.

If a stream ends before a finish reason arrives, the spec says to report `error` **in the finish-reason field**. Silence and failure must look different.

### Attribution: four axes, and only three have attribute names

When quality drops, ask what changed. There are four possible answers. The standard names three.

```
  the MODEL      gen_ai.request.model  AND  gen_ai.response.model
  the PROMPT     gen_ai.prompt.name    AND  gen_ai.prompt.version
  the DATA       no attribute exists. Invent one.
  the SERVING    no attribute exists. One provider offers a fingerprint.
  INFRASTRUCTURE
```

The two prompt attributes are real. They are defined in `model/gen-ai/registry.yaml` at commit `c88d504`, checked on 2026-09-17. `run_recorder.py` does not emit them yet.

**Record both model fields, and alert when they differ.** The request field is what you asked for. The response field is what answered. They differ when the provider routes elsewhere. That is the cheapest detector of silent changes. `otel_attributes` takes both, and a test checks them. The ledger record itself stores only the requested model.

**Anthropic documents the fourth axis.** Pinning a model ID does not pin behaviour:

> Model weights are fixed for a given ID, but the serving infrastructure around the model can change over time. If you notice unexpected behavioral differences on a previously stable model ID, an infrastructure update is the most likely cause.

Section 5.6 cites a postmortem where this happened. Three infrastructure bugs degraded output for weeks, with no model, prompt, or data change.

**No attribute records the corpus version your retrieval used.** The spec has a data-source identifier, not a version. Invent the key before you need it.

### Your noise floor

Measure the variation that happens with no change. In 2025, Thinking Machines Lab sent one prompt 1,000 times at **temperature 0** to a shared endpoint. Each completion had 1,000 tokens. It got **80 unique completions**. The batch size changes with load, and the GPU kernels are not batch-invariant. A batch-invariant kernel gives the same result at any batch size.

This does not mean that 8% of answers differ. The most common completion appeared only **78 times**, so 922 of 1,000 differed from it. All were identical for 102 tokens. At token 103, 992 went one way and 8 another.

So exact-text comparison of long outputs flags almost every run. A quality alert needs a metric that tolerates this. Measure your floor: send one input many times, and score each output with your quality metric.

For sample size, "Adding Error Bars to Evals" gives the arithmetic. Detecting a 3 percentage-point difference at 95% confidence and 80% power takes about **1,000 independent questions**. A 50-item set cannot see a 3-point regression.

### What to record, and what it costs

The spec gives three options for prompt and completion content:

1. **Do not record content.** The default.
2. **Record content on span attributes.** For pre-production.
3. **Store content outside the trace, and record a reference.** Recommended for production.

The author measured span sizes on realistic prose, in the wire format, gzipped, averaged over five seeds. The script is not in `code/`, so this review could not re-run it.

```
┌──────────────────────┬──────────────────┬──────────────────────────────┐
│ prompt size          │ metadata only    │ with prompt and completion   │
├──────────────────────┼──────────────────┼──────────────────────────────┤
│ 500 in / 150 out     │  107 B per span  │  1,210 B per span   (11x)    │
│ 4,000 in / 500 out   │  109 B per span  │  6,932 B per span   (64x)    │
│ 30,000 in / 1,000 out│  110 B per span  │ 47,156 B per span  (430x)    │
└──────────────────────┴──────────────────┴──────────────────────────────┘
```

**Metadata stays near 1,450 uncompressed bytes per span at every prompt size.** Only content grows. For a retrieval-sized prompt, it makes the span 430 times larger.

At ten requests per second, a month has 25,920,000 spans. For the 30,000-token row, that is about 2.8 GB of metadata, or about 1,222 GB with content.

**These sizes break export.** The default OpenTelemetry Collector limit is 4 MiB per request, and the default export batch is 512 spans. At 4,000 input tokens with content, 512 spans are about 11 MB. With default batch settings, content capture fails to export on any retrieval-sized workload, and no error appears. Lower the batch size, or raise the limit.

**How much larger is an LLM span?** Two unrelated sources, a vendor blog and an open-source tracing project, use about **50 KB** per LLM span. A conventional tracing project documents about **500 bytes** per ordinary span. That is a factor of 100.

One vendor's pricing page, at one retention period, charges **$350 per million** LLM spans and **$1.70 per million** ordinary indexed spans. That is about 206 times more.

### What to sample, and the sampling trap

Head sampling decides whether to keep a trace when it starts. Tail sampling decides after it ends, so it can keep all errors. The only published head-sampling recommendation found:

```
  development and staging          keep everything
  production, low or medium load   keep everything
  production, high load            head sample 10%, then tail sample at the
                                   collector for errors and slow requests
```

**Sample the spans, and keep the metrics complete.** One vendor documents that its token and cost metrics use 100% of traffic, even with sampling. The sizes above show why this works. Metadata stays near 1,450 bytes per span, so counters and histograms are cheap to keep whole.

**Use parent-based ratio sampling, never plain ratio sampling.** The plain sampler decides per span. It splits a multi-span agent trace into disconnected pieces.

When someone objects to sampling, quote this:

> Sampling 20% of traces doesn't mean you only see 20% of failures. It means you see a statistically representative sample of your application's behaviour.

No tool ships **a default sample rate for LLM traces**. Every platform checked keeps everything by default. The rate is your decision.

**One gap remains.** The spec recommends an external reference for content. At the commit the author read, the section on recording that reference was marked `TODO`. Invent a namespaced attribute, and write down that you did.

### The minimum useful record

`run_recorder.py` writes most of this record, and `slo_report.py` reads it. Its ledger has no prompt name, prompt version, or answering model yet. Add them in your own recorder.

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

A Honeycomb write-up gives the reason for the outcome fields. Record all errors, **not just when the call failed, but when its result was invalid and caused an error downstream**. A call that returns JSON you cannot parse succeeds at the HTTP layer and fails at the product layer. Only your record shows that.

**The sentence to remember:** the client sees chunks, and the server sees tokens. A metric that mixes them compares different quantities.

**The trap:** mapping a finish reason of "length" to an error. Truncation is a completed request with an incomplete status. Counting it as an outage hides your real error rate.

**Try this now:** run the self-test. Read the check "first-token uses the SPEC name, not an invented one". It exists because the first version invented a name.

```bash
python phase05_operations/run_recorder.py --self-test
```

---

## 5.6 — Fallbacks (the pattern you will reach for, and usually should not)

Why this matters: when the provider fails, most engineers want to send the request elsewhere. That idea has a long record of failures. On an LLM, the fallback can also succeed with a wrong answer.

### Start with the argument against

The Amazon Builders' Library article "Avoiding fallback in distributed systems" argues against fallback. Its main story is from 2001.

Amazon's retail website cached shipping speeds on each web server. When the cache failed, a server used the database instead. One day, all caches failed at about the same time. Every web server called the database, the database locked up, and:

> The fallback turned a partial website outage (not being able to display shipping speeds) into a full-site outage (no pages loaded at all) and took down the entire Amazon fulfillment network in the back end.

Their diagnosis applies widely:

> If hitting the database directly was more reliable than going through the cache, why bother with the cache in the first place?

The article gives five objections:

1. Fallback is harder to test.
2. The fallback can fail too.
3. It often makes the outage worse.
4. It is often not worth the risk.
5. It hides bugs that appear years later.

**The useful part is the test that makes a fallback safe:**

> A service must run both the fallback and the non-fallback logic continuously. It must not merely run the fallback case but also treat it as an equally valid source of data.

A fallback that runs only during incidents is untested code. It runs for the first time on your worst day.

### Failover is not fallback

```
┌─────────────────┬──────────────────────────────────────────────────────┐
│ retry           │ same call, same mechanism, again. Section 5.3.       │
│ failover        │ same mechanism, different instance. Usually SAFE,    │
│                 │ because the code path is identical.                  │
│ fallback        │ DIFFERENT mechanism for the same result. This is the │
│                 │ one with the history.                                │
└─────────────────┴──────────────────────────────────────────────────────┘
```

A second deployment of the same model is failover, a configuration change. A cheaper model, a cached answer, or a retrieval-only path is fallback. That is a second product you must maintain, and it rarely runs.

One narrow fallback is defensible: serve the last known good value from the **same** mechanism when it fails. The allowed staleness sets the limit.

### The LLM version has a failure mode the general case does not

A general fallback works or returns an error. An LLM fallback can return a confident, fluent, wrong answer, and no monitor turns red.

Microsoft's documentation for the Azure API Management semantic cache states the risk. A semantic cache returns a stored answer for a similar question:

> Because semantic caching returns responses based on similarity (not exact match), it can surface responses that are incorrect, outdated, or unsafe for the current request.

Its guidance: start the score threshold at **0.05**. Above **0.2**, cache mismatches become likely. Without a per-user or per-group key, the cache can serve one user's answer to another.

### The evidence that degraded output is real and hard to detect

In September 2025, Anthropic published a postmortem on three overlapping infrastructure bugs. They degraded output quality, not availability.

```
  a routing error sent some requests to servers configured for a
  different context window        5 Aug - 18 Sep 2025
  an optimisation occasionally assigned high probability to tokens
  that should rarely appear       25 Aug - 2 Sep 2025
  a compiler bug in mixed-precision probability arithmetic
                                  25 Aug - 12 Sep 2025
```

At the worst hour, **16%** of Sonnet 4 requests were affected. Two quotes from the postmortem:

> We never reduce model quality due to demand, time of day, or server load.

> The evaluations we ran simply didn't capture the degradation users were reporting, in part because Claude often recovers well from isolated mistakes.

It also says Anthropic relied too heavily on noisy evaluations. So the provider's own suite missed a regression that lasted weeks. That is the reason for the quality indicator in section 5.4. Your suite will miss one too, unless quality has a budget.

### Cross-provider failover is not a configuration change

Four things break when the same prompt goes to another provider.

**1. The prompt changes meaning.** A study of meaning-preserving format changes measured up to **76 accuracy points** of difference on one model. Format performance correlates weakly between models. Two formats keep their order across models only about **57%** of the time.

**2. The token count changes.** Your cost model and context headroom are then wrong. Anthropic states that its newer tokenizer produces about **30% more tokens for the same text** than its older one. Across providers, tokenizers differ entirely. The reliable method: count the same request against each model, and compare.

**3. The output contract changes.** Tool schemas use different field names. One provider returns parsed arguments, another a JSON string. One supports recursive schemas, and another rejects them with a 400. Hidden tool-use prompt overhead ranges from about 286 to 804 tokens across one provider's models.

**4. Forcing a format changes accuracy.** Phase 2 section 2.5 showed constraints helping classification and hurting reasoning. So a tool call on one provider and a JSON mode on another changes the contract too.

### If you build a fallback anyway, build these four things

**Split the fallback by error class.** A context overflow needs a larger-context model. A content-policy refusal needs a different policy, or no fallback. A 429 needs another deployment. One production gateway has a separate fallback chain per error type. A single chain sends a context overflow to a model with the same limit.

**Never catch every exception.** One popular framework's fallback helper handles `Exception` by default. Then a bug in your parsing code starts a fallback silently. Name the exceptions you mean.

**Show the degraded path in the response.** One gateway returns a header naming the step that answered. Without that, you cannot measure degraded output or put it in the section 5.4 quality indicator. Fill the record's `model` field with the model that answered.

**Your circuit breakers do not agree.** One vendor documents that breaker state is approximate, because gateway instances do not synchronise. N replicas are N breakers, each with part of the traffic. Marc Brooker found that independent breakers trip at about half the rate the global failure rate predicts.

### The decision table

```
┌──────────────────────────┬────────────────────────────────────────────┐
│ situation                │ what to do                                 │
├──────────────────────────┼────────────────────────────────────────────┤
│ one deployment is down   │ FAILOVER to another deployment of the same │
│                          │ model. Safe, same code path.               │
│ the provider is down     │ Fail the request, or serve a bounded stale │
│                          │ answer from the same mechanism, and say so │
│ rate limited             │ Shed and retry later. Section 5.3.         │
│ context overflow         │ Compact. Phase 2 section 2.6. Not a        │
│                          │ different model.                           │
│ budget exceeded          │ Degrade deliberately and log it loudly.    │
│                          │ Phase 3 section 3.5.                       │
│ you want a cheaper model │ That is routing, not fallback. Phase 3     │
│                          │ section 3.4, with its control group.       │
└──────────────────────────┴────────────────────────────────────────────┘
```

Most rows are not fallback.

**The sentence to remember:** failover changes the instance, and fallback changes the mechanism. Only fallback has a record of turning a partial outage into a total one.

**The trap:** a fallback path that runs only during incidents. It is untested code running first in your worst conditions. On an LLM, it can also succeed and be wrong.

**Try this now:** find a fallback in your own code. Does it run all the time against real traffic, or only on failure? Can a stored record show which path answered?

---

## 🧪 Hands-on lab — part B

Seven of the eight exercises are offline. Only E13 needs a key.

**Live-run status:** every offline command below was run on 2026-09-17, and the Expected lines match. No API key was available, so E13 was not run.

- [ ] **E8 (offline).** See what an average hides.
  - Run: `python phase05_operations/run_recorder.py --demo --role cache_demo`
  - Expected: `ITL  p50    24ms  p99    900ms  MAX GAP    900ms`, and a note that the worst gap is 37x the median.
  - Teaches: TTFT, total latency and any mean all hide the freeze.

- [ ] **E9 (offline).** Find the incident that TTFT misses.
  - Run: `python phase05_operations/slo_report.py --demo`
  - Expected: TTFT **passes** at 99.60%. The freeze indicator fails at 89.93%, with `burn 10.07x`.
  - Teaches: availability and latency alone cannot see a frozen stream.

- [ ] **E10 (offline).** Two windows, two answers.
  - Run: `python phase05_operations/slo_report.py --demo --window-minutes 300`
  - Expected: the freeze indicator fails over the whole period. It **passes** at 99.83% over the last 300 minutes, 601 records, because the incident had ended.
  - Expected: the block `BURN RATE, LAST 300 MINUTES (601 records)` shows `burn  0.17x` for the freeze indicator. The whole-period block shows `burn 10.07x`.
  - Teaches: the long window sets severity. The short window shows whether it is still happening.

- [ ] **E11 (offline).** Do the burn-rate arithmetic.
  - For 99.9% over 30 days, compute the burn rate of a 1% error rate, and how long the budget lasts.
  - Check against the section 5.4 table and the formula at `slo_report.py:347`.
  - Expected: 1% ÷ 0.1% = burn 10. The budget lasts 30 ÷ 10 = 3 days.
  - Teaches: burn rate is a ratio that turns a report into an alert.

- [ ] **E12 (offline).** Read the naming decision.
  - Open `otel_attributes` at `run_recorder.py:200`, and read the docstring on chunk and token.
  - Run the self-test, and find "first-token uses the SPEC name, not an invented one".
  - Answer: why can a client not honestly report time to first **token**?
  - Teaches: a chunk may carry several tokens or none.

- [ ] **E13 (UNVERIFIED against a live provider).** Record a real call.
  - Run: `python phase05_operations/run_recorder.py --model <your-model> --role cheap --ledger runs.jsonl`
  - Then: `python phase05_operations/slo_report.py --ledger runs.jsonl`
  - Expected: one JSON object per call, and an SLO table from your own traffic.
  - Costs at most: about $0.01.
  - Teaches: the ledger is the deliverable.

- [ ] **E14 (offline).** Price your telemetry before you turn it on.
  - Use your median prompt and completion sizes and the section 5.5 table to estimate bytes per span, with and without content.
  - Multiply by your request rate for a monthly figure. Compare with the flat 1,450 bytes of metadata.
  - Teaches: only content grows, and for retrieval-sized prompts it costs hundreds of times more.

- [ ] **E15 (break-it, offline).** Count truncation as an error, and watch the test catch it.
  - Name a copy next to the original, so its imports work: `B=phase05_operations/rr_broken.py`
  - Make the WRONG version from section 5.5: `sed 's/    if rec.error_kind:$/    if rec.error_kind or rec.finish_reason == "length":/' phase05_operations/run_recorder.py > $B`
  - Run: `python $B --self-test`
  - Expected: `[FAIL] a truncated answer is 'incomplete', not an error`, then `1 FAILED`, exit code 1. The other 16 checks pass.
  - Clean up: `rm $B`
  - Teaches: on the demo ledger, this one line would drop availability from 99.30% to 97.50% with no new failures.

---

## 🔍 Check it yourself

1. In `otel_attributes` in `run_recorder.py`, two keys use an `app.` prefix, at lines 266 and 267. Name both. Explain why neither has a standard name, and what could break with an unprefixed `gen_ai.` name.
2. In the same function, find the `finish_reason == "length"` branch at line 256. State what it sets, and what it does **not** set. Name the metric that would be wrong without it.
3. In `slo_report.py`, find `evaluate` at line 94. Three indicators take their denominator from `served`, not from all rows. Explain why, and name the indicator that uses all rows.
4. In your own telemetry, does an LLM call store the model you **requested**, the model that **answered**, or one of them? If one, which silent change can you not detect?

---

## ✅ Checkpoint 5B — answer in your own words

1. Show the arithmetic. Your quality SLO is 99% over 30 days, counting answers that reach a judge threshold. In the last hour, 4% were below it. (a) Compute the burn rate. (b) How long does the budget last? (c) Using the published table, should this page someone? Name the confirming short window.

2. A colleague proposes: "Our quality SLO is 99.9% of answers that our judge rates good." Give two reasons from section 5.4 why that cannot hold. One is about the judge, and one is about task shape.

3. This is broken. Availability is 99.9%, and TTFT p95 is well inside target. Users say answers got worse this week. Nothing was deployed. (a) Name the fourth attribution axis. (b) Name the two fields whose difference would confirm it. (c) Using the temperature-0 study, explain how you set a noise floor. (d) Say why your eval suite may miss this, citing a provider's statement about its own suite.

4. Show the arithmetic. Your median request is 4,000 input and 500 output tokens, at 10 requests per second. (a) Use section 5.5 to estimate monthly telemetry volume, with content capture on and off. (b) State the ratio. (c) Your collector accepts 4 MiB per request and batches 512 spans. Does that work with content on? What would you change?

5. Design it. You must alert on silent quality regressions. Cover five points:
   - the indicator, and how a continuous score becomes a ratio of good events
   - the two windows and burn rates
   - how you measure the noise floor
   - the minimum labelled-set size, and why
   - what you record so a firing alert can be attributed

6. A colleague says: "We will fall back to a cheaper model when the primary fails. So we are covered." Give three objections from section 5.6. Cover testing, how a failed LLM fallback looks, and a popular helper's default.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) The budget is 1%, so the burn is 4% ÷ 1% = 4. (b) 30 ÷ 4 = 7.5 days. (c) The page thresholds are 14.4 and 6. A burn of 4 is below both, so it is a ticket: a 3-day window confirmed over 6 hours. A 6% bad rate would give burn 6, the 6-hour page, confirmed over 30 minutes.

2. First, the judge agrees with human experts about 85% of the time, and two humans agree 81%, with ties left out. With ties, the figures are 66% and 63%. A judge that disagrees with people on 15% or more of cases cannot certify 99.9% per request. Second, per-step quality multiplies over steps. At 75% per step, three steps succeed about 42% of the time. Set an aggregate target on the outcome the user sees.

3. (a) The serving infrastructure. Weights are fixed for an ID, but the router, classifiers and sampling logic can change. (b) `gen_ai.request.model` and `gen_ai.response.model`. A difference means another model answered. (c) One prompt sent 1,000 times at temperature 0 gave 80 unique completions. The most common appeared only 78 times. The causes are load-dependent batch sizes and kernels that are not batch-invariant. So exact text is useless as a floor. Send one input many times, score each output with your metric, and use that spread. (d) Anthropic's postmortem said its evaluations missed what users reported. One reason: the model recovers well from isolated mistakes. It also said it relied too heavily on noisy evaluations.

4. (a) About 109 compressed bytes per span without content, and 6,932 with it. A month at 10 requests per second has 25,920,000 spans. That is about 2.8 GB without content and about 180 GB with it. (b) About 64 times. (c) No. One uncompressed span is about 21 KB, so 512 spans are about 11 MB, above 4 MiB. Export fails silently. Lower the batch below 200, raise the limit, or store content outside the trace.

5. The indicator is the proportion of sampled records whose score reaches a threshold. Use a ratio, not the mean, because only a ratio has an error budget. Page on burn 14.4 over one hour, confirmed over five minutes. Ticket on burn 1 over three days, confirmed over six hours. Measure the noise floor first: send the same inputs many times, unchanged, and record the score spread. The labelled set needs about 1,000 independent items for 3 points at 95% confidence and 80% power. 50 items are not enough. Record the prompt name and version, and both model fields. Then an alert points to a prompt change, a model change, or neither.

6. First, a fallback that runs only during incidents is untested code on your worst day. Both paths must run all the time against real traffic. Second, an LLM fallback can succeed with a fluent, wrong answer, and no monitor turns red. A semantic-cache vendor warns its feature can return incorrect, outdated or unsafe responses. Third, a popular helper catches `Exception` by default, so your own parsing bug silently starts the fallback.

</details>

---

## References & Further Learning

Part A holds the references for retries, rate limits and timeouts. This part holds SLOs, telemetry and fallback. All URLs were checked on 2026-09-14. This review fetched every URL again on 2026-09-17. One returned 404 and was replaced by its new location, which returned 200.

### SLOs and alerting

- **Alerting on SLOs, Google SRE Workbook, chapter 5** — https://sre.google/workbook/alerting-on-slos/
  Focus on: table 5-8, then table 5-4. Skip the five approaches that only lead to the sixth. The source of the 14.4, 6 and 1 tiers and the one-twelfth rule.

- **Implementing SLOs, Google SRE Workbook, chapter 2** — https://sre.google/workbook/implementing-slos/
  Focus on: the SLI types, including **Quality**, and the reasons against a 100% target.

- **Service Level Objectives, Google SRE Book, chapter 4** — https://sre.google/sre-book/service-level-objectives/
  Focus on: "Indicators in Practice", for the percentile ladder.

- **Set reliability targets for services and large language model providers, Pydantic Logfire documentation** — https://pydantic.dev/docs/logfire/observe/service-levels/
  Focus on: the "AI quality (eval score)" SLI and its three burn tiers.

- **Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena, Zheng et al., 2023** — https://arxiv.org/abs/2306.05685
  Focus on: the agreement tables. The 85% excludes ties. With ties, agreement falls to the mid sixties. It also documents position, verbosity and self-preference bias.

- **Azure OpenAI in Microsoft Foundry Models performance and latency, Microsoft Learn** — https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/latency
  Focus on: the TTLT formula and the token-count rule. It states no millisecond target. No major provider publishes a latency SLO.

- **Revisiting Service Level Objectives and System Level Metrics in Large Language Model Serving, 2024** — https://arxiv.org/abs/2410.14257
  Focus on: the two ways to game a naive latency SLO.

- **The Impact of Response Latency and Task Type on Human-LLM Interaction, ACM CHI 2026** — https://arxiv.org/abs/2604.06183
  Focus on: the 2, 9 and 20 second results and the ethics discussion. A new paper. This review checked only the abstract.

- **Response Time Limits, Jakob Nielsen, Nielsen Norman Group** — https://www.nngroup.com/articles/response-times-3-important-limits/
  Focus on: 0.1 s feels instant, 1 s keeps a train of thought, 10 s is the limit of attention. Cite the original, Miller 1968. The 200 ms turn gap is from Levinson 2016, *Trends in Cognitive Sciences*. The 238 words per minute is from Brysbaert 2019, a meta-analysis of 190 studies.

### Telemetry

- **OpenTelemetry GenAI semantic conventions** — https://github.com/open-telemetry/semantic-conventions-genai
  Focus on: the YAML models, not the generated Markdown. Cite a commit, because nothing is released and every attribute is development stability. Also read `reference/reports/inference-span.md`, the conformance report with **zero of 13** for the first-token attribute.

- **Model IDs and versioning, Anthropic documentation** — https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions
  Focus on: "Model weights versus serving infrastructure". The old URL, `https://platform.claude.com/docs/en/build-with-claude/model-ids-and-versions`, returned 404 on 2026-09-17.

- **A postmortem of three recent issues, Anthropic, September 2025** — https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues
  Focus on: the timeline, and why detection took so long.

- **Defeating Nondeterminism in LLM Inference, Thinking Machines Lab, 2025** — https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/
  Focus on: the 1,000-completion experiment and its counts.

- **Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations, 2024** — https://arxiv.org/abs/2411.00640
  Focus on: the sample-size arithmetic. It also warns that changing temperature during an evaluation can triple the score variance.

- **Improving LLMs in Production With Observability, Honeycomb** — https://www.honeycomb.io/blog/improving-llms-production-observability
  Focus on: the attribute-setting code, with a reason per field.

### Fallbacks

- **Avoiding fallback in distributed systems, Amazon Builders' Library** — https://web.archive.org/web/20250119023338/https://aws.amazon.com/builders-library/avoiding-fallback-in-distributed-systems/
  Focus on: the 2001 incident and the section on testing fallback. The three quotes in section 5.6 match this archived copy, checked on 2026-09-17. The original URL now redirects to builder.aws.com.

- **Azure API Management policy reference, llm-semantic-cache-lookup, Microsoft Learn** — https://learn.microsoft.com/en-us/azure/api-management/azure-openai-semantic-cache-lookup-policy
  Focus on: the warning note, the 0.05 and 0.2 thresholds, and `vary-by` for per-user keys.

- **Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design, Sclar et al., 2023** — https://arxiv.org/abs/2310.11324
  Focus on: the 76-point spread, and the 57% rate at which format order holds across models.

- **Token counting, Anthropic documentation** — https://platform.claude.com/docs/en/build-with-claude/token-counting
  Focus on: the note on 30% more tokens, and counting one request against each model.

---

## Cheatsheet — part B

```
FOUR INDICATORS (availability + latency cannot see wrong or frozen answers)
  availability   the call returned
  TTFT           first token inside target
  smoothness     no gap above target       <- the Phase 2 freeze
  completeness   finish_reason != "length" <- a 200 OK that dashboards count
  demo: TTFT PASSES 99.6%, freeze FAILS 89.93% (burn 10.07x)
        availability fails from a separate 0.4% background error rate

ERROR BUDGET AND BURN
  budget = 100% - target      99.9%/30d -> ~43 minutes
  burn = bad rate / budget    burn 1 -> 30 days | 10 -> 3 days | 1000 -> 43 min
  page    burn 14.4  over 1h   confirmed over 5m    (2% of budget)
  page    burn  6    over 6h   confirmed over 30m   (5%)
  ticket  burn  1    over 3d   confirmed over 6h    (10%)
  short window = 1/12 of the long window
  latency ladder: 90% < X | 99% < 10X | 99.9% < 100X
  PAIR LATENCY WITH TOKENS.  total = TTFT + (time per token x tokens)

QUALITY AS AN SLI
  good event = record REACHES a threshold, never the mean score
  judge: ~85% agreement, ties excluded (66% with ties) -> aggregate only
  0.75^3 = ~42% for three steps at 75%
  noise: 1000 runs at temp 0 -> 80 unique, most common only 78x
    -> exact text is useless. Measure your floor with your own metric.
  ~1000 items to detect 3 points at 95% confidence, 80% power
  gaming: delay tokens, drop slow requests. Keep completeness beside latency.
  2s TTFT rated LESS thoughtful than 9s or 20s (n=240)

TELEMETRY NAMES
  CLIENT says CHUNK. SERVER says TOKEN.
    gen_ai.response.time_to_first_chunk     SECONDS
    gen_ai.client.operation.time_per_output_chunk
    gen_ai.server.time_to_first_token
  required: operation.name, provider.name   span name "{operation} {model}"
  span covers ALL RETRIES -> 429s INVISIBLE by default
  0 of 13 reference libraries emit time_to_first_chunk
  "ITL" has two meanings across tools. Write down yours.

RECORDING FAILURES
  timeout         error.type + status Error
  429             usually invisible (retried inside the span)
  truncation      NOT an error: finish_reasons ["length"], status "incomplete"
                  as an error on the demo: availability 99.30% -> 97.50%
  content filter  PROMPT = 400, OUTPUT = 200 with a finish reason
  stream ended early -> "error" in the finish_reasons position

ATTRIBUTION
  model     gen_ai.request.model vs gen_ai.response.model  <- alert on diff
  prompt    gen_ai.prompt.name + .version
  data      NO ATTRIBUTE. Invent one.
  serving   NO ATTRIBUTE. A pinned model id does NOT pin behaviour.

TELEMETRY COST (author's measurement, gzipped, per span)
  500/150    metadata 107 B   with content  1,210 B   (11x)
  4k/500     metadata 109 B   with content  6,932 B   (64x)
  30k/1k     metadata 110 B   with content 47,156 B  (430x)
  metadata FLAT ~1,450 B raw.  10 rps = 25.92M spans/month
  one vendor: LLM spans $350/M vs ordinary spans $1.70/M
  4 MiB collector limit x 512-span batch FAILS with content on
  sample SPANS, keep METRICS at 100%; parentbased_traceidratio only

FALLBACK
  retry = same call | failover = same mechanism, other instance (SAFE)
  fallback = DIFFERENT mechanism (the one with the history)
  test: does the fallback run CONTINUOUSLY on real traffic?
  an LLM fallback can SUCCEED AND BE WRONG
  split by ERROR CLASS; never catch bare Exception; record WHICH path answered
  cross-provider: format moves accuracy up to 76 points; tokenizer +30%

THE COMMANDS
  run_recorder.py --demo --role cache_demo    the freeze, offline
  run_recorder.py --self-test                 19 checks, offline
  run_recorder.py --model X --ledger runs.jsonl   real calls
  slo_report.py --demo                        four indicators, offline
  slo_report.py --demo --window-minutes 300   two windows
  slo_report.py --ledger runs.jsonl           your own traffic
```

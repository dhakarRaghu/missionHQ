Phase 5A ended with your client shedding load instead of adding it, so the provider's bad week passed and your success rate held. Then a user writes in: the answers on Tuesday were subtly wrong. You open the dashboard and see 99.9% availability, TTFT inside target, and every wrong answer logged as an HTTP 200 with fluent text. Nothing you measure can see the thing the user is complaining about.

This phase builds the measurement that can. It asks four questions: which numbers would have turned red on Tuesday, how a target becomes a page at the right hour instead of a report at the end of the month, what your traces recorded while the SDK quietly retried, and why the backup model you keep for emergencies is most likely to fail you on the night you need it.

This lesson teaches five ideas. They are listed here so you can see where the lesson is going. They will read more clearly once each has been explained below, so come back to this list at the end.

- An LLM feature can be up, fast and wrong, so quality needs its own SLI as a ratio of threshold-crossing events, never a mean score. Decide which four indicators to put on the dashboard, and predict which incidents each one cannot see.
- An SLO becomes an alert only through burn rate over two windows: the long window sets severity, the short window confirms the problem is still happening. Compute a burn rate from an error rate, decide page versus ticket, and predict when an alert stops after an incident ends.
- The OpenTelemetry GenAI spec defines one span as the whole logical operation, so rejections the SDK retried into success never appear as telemetry data at all. Predict which failures his traces can show, decide max_retries=0 or HTTP-layer instrumentation, and classify truncation as incomplete, not failed.
- The stall timeout from Phase 5A detects a freeze live; the new problem is measuring it afterwards, because a per-gap sample catches one stall while a per-request average absorbs it, and clients see chunks where servers see tokens. Judge whether two latency numbers share a unit before comparing them, and choose the definition that can see a frozen stream.
- A backup path is safe or dangerous by one distinction: failover swaps only the instance and shares the code path, while fallback swaps the mechanism and runs untested on your worst day. Classify a proposed backup path as retry, failover or fallback, and predict which one turns a partial outage into a total one.

## Why everything was green while the answers were wrong

Your client from Phase 5A survived a bad provider week. The four deadlines stopped the hangs, and the load-shedding retry policy stopped your own retries from making the outage worse. Then users reported that answers had been subtly wrong for part of that week. But your availability graph had shown 99.9% the whole time. Nothing you built in 5A was broken. The client you wrote cannot tell you whether the answers were any good. It was built to keep requests alive, not to judge what came back. This phase reads the records that client wrote and builds the measurement that would have turned red.

Three ideas from earlier phases carry this one. Each comes back here doing a new job.

The SSE stream and the stall timeout

Phase 5A showed your answers arrive as an SSE stream, one chunk per event over an open connection. The stall timeout, the longest silence you accept between two chunks, detects a frozen stream live. What it never does is leave a record, so after the week ends you cannot say how often streams froze.

TTFT as a health signal

TTFT, the time from sending the request to the first chunk coming back, was your overload signal in Phase 5A. It is what your circuit breaker watched. It measures how fast the first token arrived. It says nothing about the tokens after it, and nothing about whether they were right.

The finish_reason field

Phase 1 showed every response carries a finish_reason. It uses "stop" for a natural end and "length" when the answer hit your token cap mid-sentence. A truncated answer is a successful HTTP 200. The field that would tell you it happened sits in a response you logged and never read.

Deadlines and the retry budget

Phase 5A's retry policy (one layer, a budget, full jitter) kept the provider's bad week from getting worse. That was because of you. That policy decided which calls to abandon. It never recorded why, so the retrospection this phase needs has no data yet.

The common gap across all four: they are live mechanisms, not records. They act during a request and forget it. To ask "were the answers good last week?" you need a SLI, a service level indicator. It is a number computed from recorded events that stands for one aspect of the service. To say how much of it is enough you need an SLO, a service level objective. It is a target on that indicator over a time window, like "99.9% of requests answered over any 30 days". The indicator is the measurement; the objective is the promise. Your 99.9% availability graph was an accurate SLI with a met SLO. It was also the wrong one for the failure your users saw.

That is the question the next section takes up. It asks which indicators, beside availability, would have seen each failure of that week.

## Which incident can no single indicator see?

Availability, TTFT, smoothness and completeness need four separate budgets, because no single one sees all failures.

The opening left your dashboard green across a week of subtly wrong answers. That week is now the test case. The question is which recorded events, counted as ratios, would have turned each failure red.

Each of the four failures of that week hits a different mechanism. So one indicator per mechanism is the minimum honest set. Each indicator is an SLI, a ratio where a good event is one request that met a stated condition. Four conditions cover the week:

indicatorgood eventwhat it catches

availabilitythe call returnedoutages

TTFTfirst token inside the targetqueueing, prompt bloat, cache regressions

smoothnessno gap above the targetthe stream freeze from Phase 5A

completeness indicatorfinish_reason is not "length"truncation that uptime calls success

TTFT is the time from sending the request to the first token returning. finish_reason is the response field from Phase 1. It says "stop" for a natural end, and "length" when the answer hit the token cap. A truncated answer is a successful HTTP 200, so only the completeness row counts it. The completeness indicator is the good-event share of requests whose finish_reason is not "length". That fourth row is what an uptime dashboard structurally cannot see. To it, truncation and a wrong-but-fluent answer look identical to a good one.

Predict: your provider's status page shows 99.97% uptime and your TTFT p50 is fine. A user says answers got subtly worse this week. Which of your graphs would move?
Most likely only the fourth. In this course's demo, not even that one moved enough for you to notice without looking. Availability counts returned calls, and degraded answers return as 200. TTFT measures when the first token arrives, and a wrong answer can start on time. Smoothness measures gaps between chunks, and fluent wrong text streams smoothly. The failure lives in the content of the events. Three of the four ratios never look inside one.

The demo ledger makes this concrete. It holds 2,000 records with one deliberate incident, a stretch where the stream freezes. A random 0.4% error rate is added to every record:

indicatortargetactualverdictbudget used

availability99.50%99.30%FAIL140%

TTFT ≤ 1000 ms95.00%99.60%PASS8%

no freeze > 500 ms99.00%89.93%FAIL1007%

answer completed99.00%98.19%FAIL181%

One incident, two opposite verdicts on one screen. The TTFT row passes at 99.60% while the freeze indicator fails at 89.93% and consumes about ten times its budget. A dashboard with only availability and TTFT would show one green row and one red row. That row's cause, the added 0.4% errors, is unrelated to the freeze.

The error budget is what makes each target actionable. It is 100% minus the target, so at 99.9% over 30 days it is about 43 minutes of allowed failure. Altering one number, the threshold in the good-event definition, moves which requests burn budget. The threshold is the design decision and the ratio is just its accounting.

Why a ratio and not a mean score? A mean has no denominator, so no budget attaches to it and no alerting arithmetic works on it. A mean is also gameable in both directions. One awful answer can drag a thousand good ones below the line. A thousand safe answers can hide a bad tail. A ratio of threshold-crossing events has a denominator by construction. So burn arithmetic applies to quality exactly as it applies to availability.

Up, fast and wrong is not a client-side curiosity. The provider can produce it too, and did:

Evidence
Anthropic's postmortem of September 2025 (verified against archive, 2026-10-09). Three overlapping infrastructure bugs degraded quality with no availability impact: a context-window routing error (5 August to 4 September), an output corruption misconfiguration (25 August to 2 September), and a TPU miscompilation (25 August to 12 September). At the worst hour, 31 August, 16% of Sonnet 4 requests were affected. Anthropic writes that its own evaluations "didn't capture the degradation users were reporting, in part because Claude often recovers well from isolated mistakes." Model ID and status page stayed green throughout.

Notice what that incident means for your four rows. Your availability SLI measured your provider's behaviour accurately, and it stayed green because the provider's own availability was green. The signal you needed sat in outcome fields of the record, the same place finish_reason lives.

Quality gets a budget only as a ratio of good events. So four indicators, each with its own threshold, stand where one mean score cannot.

Believing existing dashboards cover the product; the Anthropic week ran 16% degraded at the worst hour while availability read green.

Run python phase05_operations/slo_report.py --demo and find the row that passes beside the row that fails at ten times budget.

One question this section skipped: the good event is "score reaches a threshold". Who scores it, and how tight a target can that scorer honestly back? The next section asks what you can promise about quality. It covers the case where no judge agrees with a human 99.9% of the time.

## What can you promise about quality when no judge agrees with a human 99.9% of the time?

The section above put a quality indicator on your dashboard. Its threshold needs a scorer, so this section asks how tight a target that scorer can honestly back.

Your answers were subtly wrong, and each one still returned 200. To count that week you need a judge, a model that scores another model's output against your rubric. The judge becomes the definition of a good event for this indicator, so its accuracy sets the limit on yours.

### How often does the judge agree with a person?

The best-known study, "Judging LLM-as-a-Judge", measured this directly:

- GPT-4 as judge agreed with human experts on 85% of cases, when ties were excluded.

- Two humans agreed with each other on 81% of cases, ties excluded, so people themselves disagree at a similar rate.

- With ties counted, the same tables give 66% for GPT-4 versus humans and 63% for human versus human.

A scorer that disagrees with people on 15% of cases, or on 34%, cannot certify 99.9% quality on single requests. It can support an aggregate rate over many requests, because several score errors partly balance out in a large sample. This is the honest ceiling for a judge-based quality SLI. It is a percentage like 85% or 90% good events, not four nines.

Evidence
The study measured agreement directly, and both readings come from it. They are 85% and 81% excluding ties, 66% and 63% with ties. Either way, per-request 99.9% sits far beyond the judge's grip.

### One request is not one event

A good event can be several model calls plugged into one answer. Suppose each step of a three-step task scores right 75% of the time, and the steps fail independently. Then all three steps land right in only 0.75 × 0.75 × 0.75 ≈ 42% of runs. So a 75% step-rate becomes a 42% task-rate before any step got worse. Set the SLO on the outcome the user cares about, the completed task, not on each step. Otherwise, a passing dashboard will hide that only two tasks in five succeeded.

### Your metric has a floor noise below which moves mean nothing

Predict: Your quality metric scores the same 50 prompts twice, a week apart, with nothing deployed. Twelve of fifty scores move past your threshold. Is this a regression?
No deployed change suggests not, and the mechanism is batching nondeterminism. Deployment surely shifted batch sizes, and batch size changes floating-point order, so the same prompt can land a different answer. Thinking Machines measured it with one prompt run 1,000 times at temperature 0: 80 distinct completions came back. Twelve of fifty moved scores can sit well inside that noise.

The noise floor of a quality metric is the spread of scores it reports when nothing changed between runs. Thinking Machines served one prompt 1,000 times at temperature 0 on their own vLLM with Qwen3-235B. They got 80 unique completions, all identical for the first 102 tokens. Hot serving varies batch sizes between runs. Batch size changes the order of floating-point accumulation, so divergence appears after token 102. A quality signal only beats its floor when its movement is larger than this spread.

The consequence for sample size: a small regression needs a large sample to stand out from that spread. Catching a 3-point drop in a quality rate takes roughly 1,000 scored items. A weekly judgement on 50 prompts cannot see a 3-point regression. So a release decision needs about a thousand independent questions.

Evidence
Thinking Machines ran self-served vLLM with Qwen3-235B at temperature 0, 1,000 completions of 1,000 tokens each. They counted 80 unique outputs, identical until token 103. Their explained cause: batch-size variation changes reduction order in the kernels.

Use this on your own stack. Take the fixed prompt set in your phase's eval files. Score it twice back to back with nothing changed, and count how many scores cross your threshold. That count is your floor, and any real-movement claim smaller than it is noise.

Judge at 85% agreement and a 42% three-step task cap your promise at an aggregate rate, never per-request nines.

Reading 12 moved scores on 50 prompts as a regression, when temperature-zero serving alone crosses thresholds through batching noise.

Score your fixed prompt set twice today, nothing changed, and log how many cross the threshold before any incident debate.

You can now set an honest target. But a pass or fail per month still cannot wake anyone at the right hour. The next section asks how a monthly report becomes a page that fires at the right time.

## How does a monthly report become a page that fires at the right time?

A monthly report says you failed; only burn rate over two windows pages you while it still matters.

The three sections above built four indicators that can each see a different failure. But an indicator alone answers only one question, at the end of the month: pass or fail. Your freeze incident lasted three hours on a Tuesday. The monthly report would tell you about it in week four. This section turns the indicator into an alert that fires during the incident and stops after it.

The idea has two parts. Burn rate is your measured bad rate divided by your allowed bad rate. It says how fast you are spending the error budget. Then you measure that burn rate over two windows at once. The long window, hours to days, sets the severity. The short window, minutes, confirms the problem is still happening right now.

Predict: your alert watches the trailing 24 hours. A freeze incident burned 10x budget for 3 hours and ended 2 hours ago. Does your page stop when the incident stops?
No. The incident still sits inside the 24-hour window, so the window's average stays high for about 21 more hours. A single long window cannot do both jobs. It is good at judging severity but bad at noticing recovery. So the page keeps firing after the problem is over. This is why the standard recipe adds a second, short window.

### The arithmetic: bad rate over allowed rate

Your error budget is 100% minus the target. At 99.9% over 30 days the budget is 0.1% of requests, which is about 43 minutes of full outage. The burn rate divides what is happening by what is allowed:

burn rate = measured bad rate / allowed bad rate

1% bad / 0.1% allowed = burn 10

A burn of 1 spends the budget at exactly the planned pace, so it lasts the whole 30 days. A burn of 10 spends it ten times as fast, so the budget is gone in 3 days. A burn of 1000 empties it in 43 minutes. The number is unit-free, so the same burn value means the same urgency on any indicator, from TTFT to completeness.

How fast the budget drains

Measured bad rate (%)
Burn rate

99.9% monthly budget gone in

Move the slider and notice that even a 1% bad rate sounds small. It is a burn of 10 against a 99.9% target. Three days of it consumes a month of permitted failure. Small percentages against tight targets are exactly what paging is for.

### Two windows, because one window cannot do both jobs

The Google SRE Workbook publishes the two-window recipe with concrete numbers, built for a 99.9% target over 30 days:

actionlong windowshort windowburn ratebudget consumed

page1 hour5 minutes14.42%

page6 hours30 minutes65%

ticket3 days6 hours110%

Read the first row as: page someone when the burn over the last hour is 14.4. The burn over the last 5 minutes is also 14.4. The workbook's guideline is to make the short window one twelfth of the long one. Check the arithmetic on row one: burn 14.4 for 1 hour out of the 720-hour month consumes 14.4 ÷ 720. That is 2% of the budget.

Your own demo ledger shows both jobs in action. The freeze indicator's burn over the whole period is 10.07x. Over the last 300 minutes it is 0.17x, because the incident had ended:

One incident, two windows (demo ledger values)

Same records, two verdicts: the long window keeps the severity, the short window sees the recovery.

The whole-period burn stays elevated after recovery, so a long-window-only alert keeps paging someone whose problem is already fixed. The trailing window drops to 0.17x and the short-window condition fails, so the alert resolves. The long window said how bad it was; the short window said it was over.

Evidence
The tier table and the one-twelfth guideline are Table 5-8 and the text of the Google SRE Workbook. The text is "Alerting on SLOs", verified against the chapter on 2026-10-09. The burn-1000-in-43-minutes figure is its Table 5-4. The two burn values are 10.07x whole-period and 0.17x over the last 300 minutes. They come from running slo_report.py --demo --window-minutes 300 on the lesson's demo ledger.

### Shape the latency targets, and attach token counts

Burn alerting fixes the timing of the alert. Two smaller rules fix what the alert is about. First, a single latency target hides the tail, so the SRE book uses a ladder instead:

90%   of requests under X
99%   of requests under 10X
99.9% of requests under 100X

Applied to TTFT, the time from sending the request to the first token coming back is the setting. The ladder says the tail may be ten times the median but not a hundred. Second, pair every latency number with a token count. Microsoft's Azure latency guide makes the point directly. A 5-second time-to-last-token over 2,000 tokens is a different system from a 5-second time-to-last-token over 50 tokens. A rise in total latency is often fully explained by longer outputs. So check the token counts before you declare a regression.

### When traffic is too low for any of this

Burn arithmetic assumes volume. On a quiet service with a 99.9% target, a single failed request is a burn of 1000. One bad minute pages someone. The SRE chapter's answers are to generate synthetic traffic so the denominator never empties. Another is to aggregate several low-traffic services into one alert. Another is to accept a lower SLO where a lower SLO is honest.

Burn rate is bad rate over allowed rate; the long window sets severity, the short window confirms it continues.

Alerting when the error rate crosses the target pages constantly while the SLO is still met. It can also page hours after it ends.

Run slo_report.py --demo --window-minutes 300 and compare the freeze row's burn in both tables.

The alert now fires while the incident is live, but it fires on the numbers your client records. The next section asks why the 429s your SDK retried into success appear in none of those records.

## Why are the 429s your SDK survived absent from every trace?

Your alert fires on what your client records, and the standard decides what stays unrecorded.

The provider's bad week is over, and the freeze alert has gone quiet. You open the trace store to write down how bad it became. But the worst week of the quarter looks clean.

Phase 5A showed that both SDKs run their own retry loop inside your process. There are two retries by default, before the network. What Phase 5A did not cover is what that loop does to your telemetry. That answer lives in the standard, so start with what the standard defines.

OpenTelemetry is the open standard for traces, metrics and logs. A span is one timed operation in a trace, with attributes as the name-and-value facts on it. The OpenTelemetry GenAI semantic conventions are the standard's agreed field names for LLM calls. Shared names let one dashboard read any library's records. One convention decides everything in this section, because one LLM call produces exactly one span.

  one span, name "chat gpt-4", status success

-

-

  429
  429
  200, success
  what the provider did, inside your process: two rejections, two short waits, then a success

What your trace store receives (top) against what your provider did (bottom) for one call in the bad week. The standard draws the box around everything. Illustration, not measured.

Predict: your provider had a bad week of 429s, and your SDK, on its default settings, retried every rejection into a success. How much of that rejection week appears in your spans?
None of it. Every call ended in success, so every call recorded the green bar above and nothing else. The rejections exist in no attribute of any span.

The reasonable guess was most of the week, because every observability tool you have used records errors per request. This standard is the first one whose unit of work sits above the HTTP request. The attempts below it are internal steps, and internal steps leave no data.

The answer comes from two rules of the standard working together.

- The span covers every retry. The conventions state it directly: "If a transient issue happened and the request was retried automatically, the corresponding span SHOULD cover the duration of the logical operation with all retries." The SDK's retry loop from Phase 5A therefore sits inside the span, not beside it.

- An error records only the final outcome. A rejection the SDK retried automatically and then survived is a handled transient issue, so no error field is written for it.

- One clean span is the result. Three attempts ending in success produce one 8-second span with a success status, and the two 429s exist in no field of it. This is the design, not a bug, so no switch in your tracing backend brings the rejections back.

The rest of the span is sparse. The conventions define 46 attributes on an inference span and require only two of them: gen_ai.operation.name and gen_ai.provider.name. The span's name is the operation and the model joined by a space, so one entry reads chat gpt-4. Everything else is optional, and the standard's own conformance report shows what optional means in practice. The report runs 14 real client libraries against a mock server and checks each library's telemetry against the conventions.

14 of 14libraries emit gen_ai.operation.name

13 of 14emit gen_ai.provider.name

0 of 14emit gen_ai.response.time_to_first_chunk

Every library names its operation, and not one of them emits the first-chunk latency attribute. The reference scenario for one provider streams with stream=True set and usage included, and it still never sets the attribute. So your TTFT indicator is the time from sending a request until the first part of the answer arrives. It has a standard name and no producer. That is why run_recorder.py measures it and writes gen_ai.response.time_to_first_chunk itself, in seconds, rather than trusting any library to do it.

Until you act, the visible record of a 429 storm is a row of successful spans. Each one is two rejections and a success drawn as a single clean bar. The signal Phase 5A trained you to read, the 429 as a capacity report, is gone by design. You meet the storm on the day retries stop succeeding. Then errors appear in every record at once, with no build-up anywhere.

Two exits make the hidden attempts visible again.

- Set max_retries=0 and retry in your own code. Each attempt is then a separate call with its own span, and your retry budget from Phase 5A, the fixed allowance of extra attempts that sheds load when it runs out, still applies.

- Instrument the HTTP layer below the SDK. The SDK keeps its retry loop, but every attempt is a separate request at the transport layer, so each one leaves a span.

Evidence
The retry-folding rule is verbatim from the OpenTelemetry GenAI span conventions document, gen-ai-spans.md, read 2026-10-09. The required-attribute count and the span naming rule come from the conventions' client-inference document, read the same day. The conformance numbers are the repository's own generated report across 14 client libraries, read 2026-10-09. Operation name is 14 of 14, and provider name is 13 of 14. First-chunk latency is 0 of 14, and request temperature is 1 of 14. The default of two in-process retries is Phase 5A's measured SDK behaviour. The 8-second span and the three-attempt week are the lesson's illustration, not measured values.

Exercise E13 in the lab records one real call through run_recorder.py and reads the ledger back as the SLO table. That call succeeds on its first attempt. Read its span and ask which field would change if the SDK had retried silently twice before the success. Only the duration changes. That is why retry visibility is a design decision in your code, not a switch in a vendor console.

One GenAI span covers the whole logical call, so SDK-retried 429s never appear in telemetry.

Traces show only the outcome, so retried rejections appear when retries start failing, not before.

Run python phase05_operations/run_recorder.py --self-test and read the check on the name gen_ai.response.time_to_first_chunk.

The retried failures stay hidden by design, and the failures the span does show still need one honest status each. The next section answers why a truncated 200 is incomplete, not failed. It also answers how four failure kinds fit three record forms.

## A truncated 200 is incomplete, not failed: how do you record four failures in three forms?

A success code is not a success outcome, and your availability number depends on which is which.

The span hides retried failures by design, as the section above showed. The failures a span does show still need one honest status each, or the availability indicator lies. During the provider's bad week your client returned thousands of HTTP 200 results. Some of those 200s were answers cut off mid-sentence, and how you classify them decides what your dashboard says.

Outcome classification lives in two fields on the record. The first is error.type, the OpenTelemetry GenAI attribute that names the error kind, for which the standard defines one well-known value, _OTHER. You define your own values beyond it. The second is the status field, and the new fact is its third state: incomplete status, a call that finished but did not finish its job. The finish_reason, the per-response field that says why generation stopped, is the signal that separates the two.

### Four failure kinds in three record forms

- A timeout sets error.type and marks the span status Error.

- A 429 is usually missing from the record, because the SDK retried it inside the span, as the section above showed.

- A truncation is a 200 with finish_reason of length, and its status is incomplete.

- A content filter is asymmetric: a filtered prompt is an HTTP 400 error, while a filtered completion is a 200 with a finish reason.

The truncation row matters most. A truncated answer is a completed request. The model answered until your token budget ran out, then stopped mid-sentence. Mapping that to an error counts every long answer as an outage. Then real errors get lost among the fake ones. The fix is the third status, and run_recorder.py encodes it directly:

# WRONG: a truncated answer counted as a failure.
if rec.error_kind or rec.finish_reason == "length":
    attrs["error.type"] = rec.error_kind
    attrs["gen_ai.response.status"] = "failed"

# RIGHT: run_recorder.py, lines 253-259, unchanged.
if rec.error_kind:
    attrs["error.type"] = rec.error_kind
    attrs["gen_ai.response.status"] = "failed"
elif rec.finish_reason == "length":
    attrs["gen_ai.response.status"] = "incomplete"
else:
    attrs["gen_ai.response.status"] = "completed"

One more form closes the table. A stream can end before any finish reason arrives, because the connection dropped mid-answer. The spec says to report the value error in the finish-reason field for this case. So a silent cut and a failed call look different in the ledger.

Predict: what does the wrong boolean do to your availability number?
Your recorder counts finish_reason of length as an error. The ledger has 14 real errors and 36 truncations in 2,000 records. What does the availability indicator read, and how many of the counted failures were real?

It reads 97.50%, because 50 of 2,000 records count as failures. Only 14 of those 50 were real failures. The other 36 are completed calls with truncated answers, and the wrong boolean manufactured a regression that never happened.

This is not a hypothetical bug. Someone ran the wrong version of this exact code on a copy of the recorder. The self-test printed [FAIL] a truncated answer is 'incomplete', not an error and 1 FAILED. That is why that test exists. Applied to the demo ledger, one flipped boolean moves the indicators more than many real outages do:

99.30% → 97.50%demo availability, wrong boolean applied

1.40x → 5.00xburn against a 99.5% target

36 of 50counted failures that never happened

Evidence
The wrong-file review ran on 2026-09-17 against a copy of run_recorder.py, with the self-test output recorded. The demo ledger in slo_report.py holds 14 errors and 36 truncations in 2,000 records. For a stream that ends early, the rule is to report error in the finish-reason field. The status values completed, incomplete and failed are the course's own extension of that enum, which ships on the fetch_response span per the note.

Exercise E15 in the lab repeats this review: one sed command maps truncation to an error. The self-test fails, and the availability numbers above fall. The question it answers is which line in the recorder the alert actually depends on.

### Attribution: three axes have names, one has none

The status fields tell the indicator what happened a week ago, but not what changed. One incident from earlier in this lesson shows why the question matters. The Anthropic postmortem described three serving-infrastructure bugs under a pinned model ID. Model same, prompt same, data same. A quality regression needs a way to ask which part of the system moved. The standard gives names for most of the answers:

- The model has two attributes: gen_ai.request.model, what you asked for, and gen_ai.response.model, what answered. Record both and alert when they differ.

- The prompt has two attributes: gen_ai.prompt.name and gen_ai.prompt.version, defined in the registry. The course's recorder does not emit them yet.

- The data version has no attribute. The spec has a data-source identifier, not a version, so you invent one key before you need it.

- The serving infrastructure has no standard field. One provider echoes a serving fingerprint per response, per the phase text, but the study note could not verify that hook. The honest rule is to record whatever each provider's response carries per call.

The two model fields are the cheapest detector on this list. They differ when the provider routes your request to a different model than the one you named. The Anthropic postmortem is the case where even that pair stays quiet. This is because the weights stayed fixed while the infrastructure around them changed. That is why the fourth axis, unstandardised as it is, earns a slot in your record.

Truncation is an incomplete outcome with its own budget, never a failure that burns availability.

Treating every 200 as a success hides truncations, and treating truncation as failure invents outages.

Search your recorder for the line that maps finish_reason to a status. Check which of the three values truncation gets.

These fields tell you what the outcome was and what changed around it. But one latency name on the same record still hides two different measurements. The next section answers why your ITL p99 and a vendor's ITL p99 do not share a unit.

## Why does your 'ITL p99' and the vendor's 'ITL p99' not share a unit?

One latency name can hide two measurements, and only one of them can see a frozen stream.

The recorder from the last section now writes latency under the names the OpenTelemetry GenAI semantic conventions give it. They are the shared naming standard for LLM telemetry. One of those names is usually spoken as "inter-token latency". Vendor benchmarks use the same name. This section asks what the name measures before you compare your number to anyone else's.

In Phase 5A you set a stall timeout, the longest silence you accept between two chunks of the streaming response, and it caught a frozen stream live. That was detection. The question here is measurement afterwards: of the hundreds of gaps in one stream, which number do you store, and what does it still show a week later?

### Two observers, two names

The SSE stream is the server-sent-event format that delivers a response as a series of chunks. It is the only thing your client ever sees. A chunk is a transport unit, not a token. One chunk can carry several tokens, or none, because providers send keep-alive pings and empty deltas between real content. So a client can honestly measure gaps between chunks, and it cannot see tokens at all.

The spec writes this distinction into the names themselves. The client-side metric is time per output chunk. It is the elapsed time from the end of one chunk to the end of the next. It is recorded as one sample per chunk under the name gen_ai.client.inference.time_per_output_chunk. The server-side metric is time per output token. It is the request duration minus the time to the first token, divided by the remaining tokens. It is recorded as one sample per request under gen_ai.server.time_per_output_token. The same split applies to the first byte: the client attribute is gen_ai.response.time_to_first_chunk in seconds. A client that reports "time to first token" claims to measure something it cannot see.

Predict: vendor doc A reports ITL p99 of 30 ms, and your engine reports 80 ms. Before you declare a regression, what two questions decide whether these numbers share a unit?

First: is each sample one gap between two chunks, or one average across a whole request? Second: does the observer see chunks or tokens, meaning is it measured on the client or on the server? A per-chunk p99 and a per-request p99 are different quantities. The 30 ms number may be per-gap samples from a benchmark client, and your 80 ms a per-request average. Then no comparison exists. Ask both questions before the word "regression" is allowed.

### How one stall disappears

The two definitions behave differently on the incident Phase 5A cared about, one frozen stream among healthy ones.

- The stall timeout fires and your client records the stream, including the gap between every pair of chunks. Most gaps sit between 10 and 50 ms, and one gap is 900 ms.

- The per-chunk metric keeps each gap as its own sample, so the 900 ms gap appears in the data as itself. The p99 of those samples lands on it or near it, because a p99 only needs one sample in a hundred to be large.

- The per-request metric divides the whole stream by its token count, so the 900 ms spreads across roughly 500 tokens. Each token inherits about 2 ms, and that average becomes the single sample for this request.

- That one smoothed sample now sits beside hundreds of other requests' averages, and the p99 across them stays near the normal value. The stall left no trace in the number.

One sample per request (server's view)

(total time − time to first token) / (tokens − 1)
= one average for the whole stream
= the 900 ms stall becomes ~2 ms per token

The p99 across requests stays near normal, so the freeze is invisible in the stored metric.

One sample per chunk (client's view)

end of chunk N − end of chunk N−1
= one gap per chunk, stored individually
= the 900 ms stall is one 900 ms sample

The p99 of the gaps lands near 900 ms, so the freeze survives aggregation.

24 msp50 gap between chunks, demo ledger

900 msp99 gap, same stream

37xworst gap over the median

The reading to take from these numbers is that p50 and p99 describe different populations of events. The median gap is healthy at 24 ms. But one gap in a hundred is long enough to trip the 900 ms mark. So a median-based dashboard reads green while some users watch a stream stop for almost a second.

Evidence
The two definitions are quoted from the specification itself, verified on main on 2026-10-09. The client metric is gen_ai.client.inference.time_per_output_chunk. It is "the time elapsed from the end of the previous chunk to the end of the current chunk". That is one sample per chunk. The server metric is gen_ai.server.time_per_output_token. It is "measured by subtracting the time taken to generate the first output token from the request duration". Then comes "dividing the rest of the duration by the number of output tokens generated after the first token". That is one sample per request. The p50 of 24 ms, p99 of 900 ms and the 37x worst gap come from your own demo ledger. That is in exercise E8.

The working rule follows from the mechanism. Pick one definition per metric, and write it next to the metric wherever it is displayed. A dashboard entry named "ITL p99" with no definition invites exactly the comparison the predict box warned against.

### What this record costs to keep

The same care applies to how much you store per call. The metadata on a span covers the model, the tokens, the outcome fields. It stays roughly flat no matter how large the prompt is. The prompt and completion content grows with the prompt itself. A retrieval-sized prompt of around 30,000 tokens inflates its span by a factor of hundreds compared to metadata alone.

That shape has one sharp edge. The OpenTelemetry Collector's default export limit is 4 MiB per request. A batch of a few hundred content-carrying spans crosses it. Then the batch is dropped with no error in your application logs. Keep the shape in mind and the default limit in mind together. Record metadata on every span. Treat full content capture as a development setting, unless you size the exporter for it. The study material could not verify exact per-span byte counts. So the lesson is the shape, not a table of numbers.

### Use it

Exercise E8 makes the disappearing stall concrete on your own machine. Run the gap analysis over the demo ledger. Look for the line that prints p50 24 ms, p99 900 ms and the maximum gap. Then exercise E12 asks you to read the docstring in run_recorder.py. It separates chunk gaps from per-token averages. Then run the self-test that checks the emitted names are the spec's and not invented ones. The question both answer is whether your latency numbers can still see the incident that fired your stall timeout.

A per-chunk p99 keeps one 900 ms stall; a per-request average spreads it into 2 ms per token.

Comparing two "ITL p99" numbers without asking which observer and which sampling. 30 ms and 80 ms may share no unit.

Find one latency metric in your recorder and write its definition beside it, in one line, as per-chunk or per-request.

The recorder now measures honestly what the primary provider did, so it can tell you when the primary is failing. The next section asks what instinct that sight triggers. It also asks why the answer depends on whether your backup swaps the instance or the mechanism.

## Failover swaps the instance, fallback swaps the mechanism: why does only one of them end careers?

Telemetry tells you the primary is failing; this section decides what you do with that signal.

Your recorder can now show, per run, which model answered and whether the call was any good. The moment those numbers turn red, someone will propose sending the traffic somewhere else. This section gives you the three-way distinction that decides whether that proposal helps. It also gives the evidence for when it has hurt before.

### The picture first

When a primary path fails, three different responses are on the table. They look alike because each one answers to "the call failed" with a plan B. Failover moves the same call to another instance of the same mechanism, so the code path running is identical. Fallback swaps in a different mechanism for the same result, so a different product runs. It usually runs for the first time during the incident. Retry, from Phase 5A, is the same call again inside your retry budget. The retry budget is the cap on extra attempts per user request.

retry

same call again
same code, same server, within your retry budget
failover

same code, deployment B
the mechanism is unchanged, so the backup is tested every day
fallback

different model or cache
different prompting, tokenizer and output contract, rarely exercised

Three plan Bs that sound alike; only the middle one keeps the same mechanism running.

Predict: your fallback path to model B last ran in production four months ago. It runs tonight at 3 a.m. under full load, for the first time since you changed your JSON parsing. What is the probability it behaves as the design document says?
Far below what the document implies. The fallback shares none of the four months of changes. It has not processed a request since the JSON parser changed. Its first test is tonight, under the highest stress your system ever sees. That is the condition where latent bugs show up. Amazon's 2001 incident below is this shape at a larger scale.

### Why the mechanism-swap is the dangerous one

A fallback mechanism is only a fallback because it is worse than the primary. It is worse in some way, such as cost, capacity or quality. That difference means it is never in the rotation during normal operation. The consequences arrive in order:

- Normal traffic exercises only the primary, so the fallback's bugs over weeks of routine code changes stay latent, because nothing runs it.

- The outage hits the primary, so traffic moves to the path with the most lag between written code and tested code.

- The fallback runs under the highest concurrent load of its life, because every primary request is now arriving at once.

- The fallback is weaker than the primary by design, so it saturates or errors, and the partial outage becomes a total one.

### Amazon, about 2001

Amazon's retail site cached shipping-speed data on each web server. Every web server could query the database directly if its cache missed. One day the caches failed on all servers at about the same time. Every web server then queried the database. The database locked up, so the failure in one feature took down pages. Those pages had nothing to do with shipping speeds. The clear dashboard reading here is that each server had a backup path, and all of them fired together.

Two kinds of load converging on one database

Step 1: web servers read shipping speeds from their local caches, so almost no database load arrives.

Step 2: every cache fails together, so each server's fallback sends the full web load to the database at once.

Step 3: the database locks up, and the whole site and the fulfilment network stop.

Amazon's own diagnosis was the cut that matters. If hitting the database directly had been more reliable than going through the cache, the cache would not have existed. The fallback was by construction the weaker mechanism, and it was the one that got all the load. Their remedy turns fallback into failover. Run both paths continuously on real traffic, and treat both as equally valid data sources. A path that runs every day is tested every day, and by then it is an alternate, not a fallback.

Evidence
Amazon Builders' Library, "Avoiding fallback in distributed systems": the fallback "turned a partial website outage (not being able to display shipping speeds) into a full-site outage (no pages loaded at all) and took down the entire Amazon fulfillment network". The article lists five objections, including that fallback is harder to test and can make an outage worse, and gives the continuous-exercise remedy. Verified against the archived page, read 2026-10-09.

### The LLM version fails silently

The Amazon fallback failed loudly, because the database locked and pages stopped loading. An LLM fallback to a different model or to cached answers returns HTTP 200 with fluent, plausible text. No availability or latency graph moves while the answers change. The completeness indicator from earlier in this phase is the count of runs with a full finish_reason. It still reports green, because the fallback answers complete. Only the quality indicator or the model-attribution alert from the run record can see it.

One common fallback shape deserves a name. A semantic cache returns a stored answer when a new question is similar enough to a stored one. Similarity is measured as an embedding score. Microsoft's own documentation for the llm-semantic-cache-lookup policy warns it "can surface responses that are incorrect, outdated, or unsafe". Its numbers give the shape of the risk:

- A starting score threshold of 0.05 is the recommendation, and mismatches become likely above 0.2.

- Without a per-user or per-group vary-by key, the cache can serve one user's answer to another user's question.

- The hit answers instantly and returns 200, so a wrong cache hit is invisible on both latency and availability graphs.

Cross-provider "failover" is also fallback in disguise. The prompt reads differently to a different model. The tokenizer changes your token counts, and the tool schemas differ. So the backup is a different product even though the HTTP call looks the same.

### One fallback that survives the test

A bounded stale value from the same mechanism is defensible. An example is serving the last good answer with an explicit age marker when the fresh call fails. It runs every day because readers use it between refreshes. The staleness limit is stated in the design, and the response says it is aged. It is the same mechanism, so the Amazon objection about sharing a code path does not apply.

### The decision table

situationwhat to dowhich of the three

one deployment is downmove traffic to another deployment of the same modelfailover

rate limited (429)shed load and retry within the budget, as Phase 5A sized itretry

context overflowcompact the prompt, as in Phase 2same mechanism

budget exceededdegrade deliberately and log it loudly, as in Phase 3same mechanism, fewer tokens

you want a cheaper model sometimesroute with a control group, as in Phase 3, measured every daychosen routing, not fallback

provider fully downfail the request, or serve a bounded stale answer and mark itanything else is fallback

Most rows in the table are not fallback, which is the point of drawing the table before agreeing to one. Phase 5A also showed why a fleet of gateways cannot share the decision. Each instance's circuit breaker is independent. Independent breakers trip at about half the rate the global failure rate predicts. So the fleet flips to the backup unevenly.

### Use it

Find one plan B in your own client or gateway code. Classify it with the table above in one line. Does it run all the time on real traffic? Does your run record show which path answered the call? If both answers are no, you are holding an untested fallback. The checkpoint questions give you the three objections to raise when a colleague proposes one.

Failover swaps the instance and shares the code path; fallback swaps the mechanism and runs untested on your worst day.

"We will fall back to the cheaper model" returns 200 with a fluent wrong answer. Amazon's 2001 caches-to-database fallback turned a partial outage into a full-site one.

Check whether your client's plan B ran in the last week of production. If it did not, write down what would test it.

This was the last teaching section of Phase 5B. You can now define the four indicators and compute a burn rate over two windows. You can write a run record whose names match the OpenTelemetry GenAI conventions. You can also refuse most fallback designs with evidence. The recall section checks those claims in your own words. The next phase, 6A, asks a different question. It asks how many servers the fleet needs, and how several tenants share it fairly.

## What you can do now, and what comes next

You started this phase with a green dashboard and users reporting wrong answers. Each section answered one part of why nothing turned red. Read the five claims again and check each one in your own words.

- An LLM feature can be up, fast and wrong. Quality needs its own SLI as a ratio of good events, because a mean score has no denominator and no error budget attaches. Anthropic's own postmortem showed 16% of Sonnet 4 requests degraded at the worst hour while availability stayed green. Taught in "Which incident can no single indicator see?" and "What can you promise about quality?"

- An SLO becomes an alert only through burn rate over two windows. The long window sets severity, the short window at 1/12 of it confirms the problem is still happening, so the page stops when the incident stops. Taught in "How does a monthly report become a page that fires at the right time?"

- One span covers the whole logical operation, retries included. A 429 your SDK retried into success never exists as telemetry data, by spec design, and 0 of 14 client libraries emit time_to_first_chunk, so you instrument it yourself. Taught in "Why are the 429s your SDK survived absent from every trace?"

- A client sees chunks and a server sees tokens. "ITL p99" names two different quantities: a per-gap p99 shows a 900 ms stall whole, a per-request average absorbs it as about 2 ms. Check the unit before you compare two numbers. Taught in "Why does your 'ITL p99' and the vendor's 'ITL p99' not share a unit?"

- Failover swaps the instance; fallback swaps the mechanism. A fallback runs untested on your worst day, and on an LLM it returns 200 with a fluent wrong answer, so nothing turns red. Taught in "Failover swaps the instance, fallback swaps the mechanism."

What you can do now: define the four indicators and say which incidents each one cannot see. You can compute a burn rate and choose page versus ticket. You can write a run record whose names match the OpenTelemetry GenAI conventions. You can refuse most fallback designs with evidence. The lab that follows lets you run each mechanism against the demo ledger. The checkpoint tests the arithmetic on new numbers.

The next phase, 6A, asks a different question. Your client survives a bad week and your telemetry would now see one. But how many servers does the fleet need in a good week? And how is that fleet shared fairly when several tenants want it at once?

## Lab: measure it, promise it, break it

Seven of the eight exercises run offline against the demo ledger, a recorded week of model calls with one buried incident. Only E13 needs an API key, and it costs about $0.01. Each exercise is labelled with the concept it proves.

-  E8 offline
Proves the chunk-versus-token lesson. One stream can look healthy in the average and broken in the per-gap samples.

Run: python phase05_operations/run_recorder.py --demo --role cache_demo

Expected: ITL  p50    24ms  p99    900ms  MAX GAP    900ms, and a note that the worst gap is 37x the median.

What to notice: the median says 24 ms. One user watched a 900 ms silence on the same stream, and only the per-gap view shows it.

-  E9 offline
Proves the four-indicator lesson. Availability and TTFT alone cannot see a frozen stream.

Run: python phase05_operations/slo_report.py --demo

Expected: TTFT passes at 99.60%. The freeze indicator fails at 89.93%, with burn 10.07x.

What to notice: one incident, two opposite verdicts on one screen. This is the picture behind the claim that quality and smoothness need their own ratios.

-  E10 offline
Proves the two-window lesson. The long window sets severity; the short window says whether the problem is still happening.

Run: python phase05_operations/slo_report.py --demo --window-minutes 300

Expected: the freeze indicator fails over the whole period. It passes at 99.83% over the last 300 minutes, 601 records, because the incident had ended.

Expected: the block BURN RATE, LAST 300 MINUTES (601 records) shows burn  0.17x for the freeze indicator. The whole-period block shows burn 10.07x.

What to notice: if your page watched only the whole-period number, it would still be firing after the incident ended.

-  E11 offline
Proves the burn-rate arithmetic. A report becomes an alert through one division.

For a 99.9% SLO over 30 days, compute the burn rate of a 1% error rate, and how long the error budget lasts. Check against the chapter table and the formula at slo_report.py:347.

Expected: the budget is 1 minus 0.999, so 0.1%. Then:

burn          = 1% ÷ 0.1%        = 10
budget lasts  = 30 days ÷ 10     = 3 days

What to notice: a "small" 1% error rate empties a monthly budget in three days. That is why burn 6 over 6 hours pages.

-  E12 offline
Proves the naming lesson. A client cannot honestly report time to first token, because a chunk may carry several tokens or none at all.

Open otel_attributes at run_recorder.py:200 and read the docstring on chunk and token. Run the self-test and find "first-token uses the SPEC name, not an invented one".

Answer in your own words: why does the client-side attribute say time_to_first_chunk while the server-side metric says time_per_output_token?

-  E13 needs a key
Proves the whole run-record lesson. The ledger is the deliverable that Phase 5A promised: every call recorded under the spec's names.

Run: python phase05_operations/run_recorder.py --model <your-model> --role cheap --ledger runs.jsonl

Then: python phase05_operations/slo_report.py --ledger runs.jsonl

Expected: one JSON object per call, and an SLO table computed from your own traffic. Costs at most about $0.01.

One caveat from this week's study note: this exercise was not run against a live provider before publication, because no key was available. Treat its Expected line as the intended output, not a measured one.

-  E14 offline
Proves the telemetry-cost shape. Metadata per span stays flat in prompt size while content scales with it.

Take your median prompt and completion sizes and estimate bytes per span, with content capture on and off. Multiply by your request rate for a monthly figure, and compare with the flat metadata cost of about 1,450 bytes per span.

What to notice: only content grows. For a retrieval-sized prompt, the content copy inflates the span by hundreds of times, and a collector export limit against a large span batch drops content spans silently. Think in orders of magnitude; the exact byte table in the source phase could not be verified this week.

-  E15 offline break-it
Proves the incomplete-versus-failed lesson. A truncated 200 is incomplete, not an outage, and one wrong boolean manufactures a regression.

Name a copy next to the original so its imports work: B=phase05_operations/rr_broken.py

Make the wrong version from the truncation section: sed 's/    if rec.error_kind:$/    if rec.error_kind or rec.finish_reason == "length":/' phase05_operations/run_recorder.py > $B

Run: python $B --self-test

Expected: [FAIL] a truncated answer is 'incomplete', not an error, then 1 FAILED, exit code 1. The other 16 checks pass.

Clean up: rm $B

What to notice: on the demo ledger, that one line drops availability from 99.30% to 97.50% with no new failures. The classification rule is what keeps the number honest.

The offline Expected lines were run and matched on 2026-09-17. E13's line is unverified against a live provider, as marked above.

Once the ledger runs and the self-test catches your deliberate break, the checkpoint asks the same five questions with numbers you have not seen.

## Checkpoint 5B

The lab made you run the numbers on the demo ledger. These five scenarios move the same ideas to numbers you have not seen, so answer each in your own words before opening the sketch.

- Page or ticket. Your quality SLO is 99% over 30 days, counting answers that reach a judge threshold. In the last hour, 4% of sampled answers were below it. (a) Compute the burn rate. (b) How long does the budget last at this rate? (c) From the published table, does this page someone? Name the confirming short window.

Answer sketch
(a) The budget is 1 − 99% = 1%, so the burn is 4% ÷ 1% = 4. (b) 30 days ÷ 4 = 7.5 days. (c) The page thresholds are 14.4 (1 hour, confirmed over 5 minutes) and 6 (6 hours, confirmed over 30 minutes). A burn of 4 is below both, so it is a ticket: burn 1 over 3 days, confirmed over 6 hours. A 6% bad rate would be burn 6 and would page.

- The 99.9% judge SLO. A colleague proposes: "our quality SLO is 99.9% of answers that our judge rates good." Give two reasons from this phase why it cannot hold, one about the judge and one about task shape.

Answer sketch
The judge agrees with human experts about 85% of the time with ties excluded and 66% with ties counted, well below 99.9%, so a judge cannot certify a per-request target that tight; only an aggregate rate survives. The task-shape reason is compounding: per-step quality multiplies over steps, so 75% per step is about 42% over three steps, and the honest target sits on the outcome the user sees.

- The green dashboard. Availability is 99.9%, TTFT p95 is inside target, users say answers got worse this week, and nothing was deployed. (a) Name the fourth attribution axis. (b) Name the two fields whose difference would confirm part of it. (c) Using the temperature-0 study, explain how you set a noise floor. (d) Why may your eval suite miss this?

Answer sketch
(a) The serving infrastructure: the model ID pins the weights, but routing, classifiers and sampling logic can change under it, as the Anthropic postmortem showed. (b) gen_ai.request.model and gen_ai.response.model; a difference means another model answered. (c) Thinking Machines sent one prompt 1,000 times at temperature 0 on their own vLLM serving of Qwen3-235B and got 80 unique completions, identical only for the first 102 tokens, because batch sizes vary. Exact text is useless as a floor, so you send one input many times, score each output with your metric, and take the spread as the floor. (d) Anthropic said its own evaluations "didn't capture the degradation users were reporting, in part because Claude often recovers well from isolated mistakes", and that it relied too heavily on noisy evaluations.

- The telemetry bill. Your median request is 4,000 input and 500 output tokens, at 10 requests per second. (a) Estimate monthly telemetry volume with content capture on and off. (b) Your collector accepts 4 MiB per export request and batches 512 spans. Does that work with content on, and what would you change?

Answer sketch
(a) A month at 10 rps is about 26 million spans. Per-span metadata is flat in prompt size, so without content a span is small and the month is a few GB. Content scales with prompt size, so a 4,000-token prompt inflates its span by hundreds of times, and the month lands in the hundreds of GB. The phase's recorder measured roughly 21 KB uncompressed for one content span; treat that figure as an illustration, because the measurement could not be independently verified. (b) Five hundred content spans at that size is far above 4 MiB, so the export is dropped silently. Lower the batch, raise the limit, or store content outside the trace and reference it.

- The colleague's fallback. A colleague says: "We will fall back to a cheaper model when the primary fails, so we are covered." Give three objections from this phase, covering testing, how a failed LLM fallback looks, and a popular helper's default.

Answer sketch
First, a fallback that runs only during incidents is untested code on your worst day; Amazon's remedy was to run both paths continuously as equally valid data sources, which converts fallback into failover. Second, an LLM fallback can succeed with a fluent, wrong answer, so nothing turns red; Microsoft's semantic-cache documentation warns it "can surface responses that are incorrect, outdated, or unsafe." Third, a popular retry helper catches Exception by default, so your own parsing bug silently starts the fallback even when the primary is healthy. Swapping the model also swaps the mechanism, because the prompt format, tokenizer and tool schemas change, so a cross-model "failover" is really a fallback.

When your answers match the sketches, the cheatsheet compresses the whole phase onto one screen.

## Cheatsheet

FOUR INDICATORS (availability + latency cannot see wrong or frozen answers)
  availability   the call returned
  TTFT           first token inside target
  smoothness     no gap above target        ~43 minutes
  burn   = bad rate / budget    burn 1 -> 30 days | 10 -> 3 days | 1000 -> 43 min
  page    burn 14.4 over 1h  confirmed over 5m   (2% of budget)
  page    burn  6   over 6h  confirmed over 30m  (5%)
  ticket  burn  1   over 3d  confirmed over 6h   (10%)
  short window = 1/12 of the long window (SRE Workbook Table 5-8)
  demo: whole-period burn 10.07x, last-300-minutes burn 0.17x
  latency ladder: 90%  aggregate rates only,
         no per-request 99.9% target
  compounding: 0.75^3 ~ 42% for three steps at 75% each
  noise floor: 1,000 runs at temp 0 (self-served vLLM, Qwen3-235B)
         -> 80 unique completions, all identical for the first 102 tokens
         exact-text comparison flags nearly every run; measure YOUR floor
  sample size: ~1,000 items to see a 3-point regression
  gaming defences: completeness indicator BESIDE latency
         (delay tokens or drop doomed requests and a naive latency SLO passes)

TELEMETRY NAMES (client says CHUNK, server says TOKEN)
  gen_ai.response.time_to_first_chunk           span attribute, seconds
  gen_ai.client.inference.time_per_output_chunk one sample PER CHUNK
  gen_ai.server.time_per_output_token           one sample PER REQUEST
    = (duration - first token) / remaining tokens
  gen_ai.server.time_to_first_token             server TTFT histogram
  required attributes: operation.name, provider.name
  span name: "{operation} {model}"
  ONE SPAN COVERS ALL RETRIES -> SDK-retried 429s are invisible BY SPEC DESIGN
    fix: max_retries=0 + app-level retries, or instrument the HTTP layer
  conformance: gen_ai.response.time_to_first_chunk emitted by 0 of 14 libraries,
    operation.name by 14 of 14 -> instrument latency yourself (run_recorder.py)
  same stall, two verdicts: per-gap p99 900 ms, per-request average moves ~2 ms
    (demo stream: p50 24 ms, p99 900 ms, worst gap 37x the median)
  WRITE YOUR OWN DEFINITION next to every "ITL" number

RECORDING FAILURES (four failures, three forms)
  timeout         error.type + status Error
  429             usually invisible (retried inside the span)
  truncation      NOT an error: finish_reason "length", status "incomplete"
                  mapped to error on demo: availability 99.30% -> 97.50%
                  (no new failures; the self-test catches it)
  content filter  ASYMMETRIC: filtered prompt = 400,
                  filtered completion = 200 with a finish reason
  stream ended early -> "error" in the finish-reason position

ATTRIBUTION (the Anthropic bugs sat under a pinned model ID)
  model     gen_ai.request.model vs gen_ai.response.model -> alert on difference
  prompt    gen_ai.prompt.name + .version
  data      NO STANDARD ATTRIBUTE. Invent one.
  serving   NO STANDARD FIELD. Record whatever the provider echoes per call;
            the fingerprint hooks could not be verified - record, alert, say the gap.

TELEMETRY COST (the shape, not the byte table - it could not be verified)
  metadata per span FLAT in prompt size; content scales with prompt size
  a retrieval-sized prompt inflates a span by hundreds of times
  a 4 MiB collector export limit vs a large content batch: silent drops
    -> lower the batch, raise the limit, or reference content outside the trace
  sample SPANS, keep METRICS at 100%

RETRY / FAILOVER / FALLBACK (one distinction: instance or mechanism)
  retry     same call again                 (Phase 5A's budgeted policy)
  failover  SAME mechanism, other instance  usually SAFE: the code path is shared
  fallback  DIFFERENT mechanism             untested on your worst day
  Amazon ~2001: all caches failed, fallback hit the database,
    partial outage -> full-site outage, fulfilment network down
  remedy: run both paths CONTINUOUSLY as equally valid data sources
    (that converts fallback into failover; cross-provider "failover" is not it:
     prompt format, tokenizer and tool schemas change -> really a fallback)
  LLM addition: a fallback can return 200 with a fluent WRONG answer;
    nothing turns red. Semantic cache doc: threshold 0.05, mismatch above 0.2,
    "can surface responses that are incorrect, outdated, or unsafe"
  survives: a BOUNDED STALE value from the SAME mechanism
  split by ERROR CLASS; never catch bare Exception; record WHICH path answered
  decision: dead deployment -> failover | rate limits -> shed and retry
            context overflow -> compact | budget -> degrade loudly
            cheaper model -> routing with a control group, never a 3 a.m. fallback

THE COMMANDS
  run_recorder.py --demo --role cache_demo    the freeze, offline
  run_recorder.py --self-test                 19 checks, offline
  run_recorder.py --model X --ledger runs.jsonl   real calls
  slo_report.py --demo                        four indicators, offline
  slo_report.py --demo --window-minutes 300   two windows
  slo_report.py --ledger runs.jsonl           your own traffic

## Two things you could post

Two posts you could write this week, each one claim you can now defend with a name and a number.

    The green dashboard that missed 16% of requests

    "Your provider's status page can show 99.97% while 16% of requests are degraded. Availability, TTFT, smoothness and completeness need four separate budgets." What makes it yours: you have the demo table where TTFT passes at 99.60% while the freeze indicator fails at burn 10.07x, and the Anthropic postmortem with its worst-hour figure of 16% of Sonnet 4 requests.

    The retries your traces cannot see

    "Your SDK's retries are invisible by spec design, because one OTel GenAI span covers the whole logical operation including all retries. And gen_ai.response.time_to_first_chunk is emitted by 0 of 14 client libraries, so instrument it yourself." What makes it yours: you read the span rule in the spec, you saw the zero in the conformance report, and you read the recorder whose code fills the gap.

The sources for both posts are one section below.

## Sources

- https://sre.google/workbook/alerting-on-slos/ — Google SRE Workbook chapter 5: the burn-rate tiers in Table 5-8 (14.4, 6 and 1), Table 5-4's budget lifetimes, and the rule that the short window is 1/12 of the long one.

- https://github.com/open-telemetry/semantic-conventions-genai — the OpenTelemetry GenAI semantic conventions repository and its structure.

- https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/model/gen-ai/registry.yaml — attribute definitions: gen_ai.response.time_to_first_chunk, the gen_ai.response.status enum, and the prompt name and version attributes. Read on main, unpinned.

- https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/client-inference.md — the client inference span: its name shape, its two required attributes, and the gen_ai.client.inference.* metric names.

- https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/gen-ai-spans.md — the rule that one span covers the whole logical operation including all retries, quoted in the telemetry section.

- https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/gen-ai-metrics.md — the server-side definitions of gen_ai.server.time_to_first_token and gen_ai.server.time_per_output_token, including the per-request average formula.

- https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/reference/reports/inference-span.md — the conformance report across 14 client libraries: gen_ai.response.time_to_first_chunk at 0 of 14, gen_ai.operation.name at 14 of 14.

- https://web.archive.org/web/2026/https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues — Anthropic's postmortem of three overlapping infrastructure bugs, with 16% of Sonnet 4 requests affected at the worst hour. Read through the Wayback capture because the live page timed out.

- https://web.archive.org/web/20250119023338/https://aws.amazon.com/builders-library/avoiding-fallback-in-distributed-systems/ — Amazon Builders' Library: the 2001 cache failure that turned a partial outage into a full-site one, and the remedy of running both paths continuously.

- https://learn.microsoft.com/en-us/azure/api-management/azure-openai-semantic-cache-lookup-policy — the semantic-cache policy, now renamed llm-semantic-cache-lookup: the 0.05 start threshold, the 0.2 mismatch warning, and per-user vary-by keys.

- https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/latency — Microsoft's latency guide, now at /azure/foundry/...: the TTLT formula and the rule to pair every latency number with a token count.

- https://ar5iv.labs.arxiv.org/html/2306.05685 — Zheng et al., the judge paper: 85% agreement with ties excluded, 66% with ties counted, and the position, verbosity and self-preference biases.

- https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/ — Thinking Machines on nondeterminism: 1,000 completions of one prompt at temperature 0 on self-served vLLM with Qwen3-235B produced 80 unique outputs, identical for the first 102 tokens.

All links were opened and checked on 2026-10-09. Two URLs have moved since the phase was written and are listed at their old addresses with the redirect noted.
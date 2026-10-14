Phase 5A left you with a client that fails in seconds on a dead stream, sends less under overload, and writes one record per call into runs.jsonl. Last Tuesday those records contain a two-hour stretch where streams froze for 900ms between chunks and every tenth answer stopped mid-sentence. Your availability graph shows 99.9% green and TTFT p95 inside target for the whole stretch, and the first report of the freeze comes from a user, three days later.

The records saw the incident and the dashboards did not, so the gap is not in the data but in what you chose to count. This phase asks four questions about that choice. Which failures does an availability-and-latency dashboard stay blind to, and what must become its own indicator before you can promise anything? How does an alert page while the incident is happening instead of three hours after it ended? When you record a call, whose names and whose numbers are you actually recording? And when the provider is down, which rescue designs make the day worse?

This lesson teaches five ideas. They are listed here so you can see where the lesson is going. They will read more clearly once each has been explained below, so come back to this list at the end.

- A green availability-and-latency dashboard is consistent with a broken LLM feature, so quality and smoothness each need their own SLI as a ratio of good events, because only a ratio has an error budget. Predict which failures his dashboards cannot see and decide what must be its own indicator.
- An alert that fires at the right time must pair a long window that measures severity with a short window that asks whether the incident is still happening, because neither alone can do both. Compute burn by hand, see why one window must page on noise or on ended incidents, and spot when the math cannot run at all.
- The client sees chunks and the server sees tokens, and SDK retries happen inside the span, so by default the 429s never happened and every client-side 'time to first token' lies. Name his own metrics honestly, and decide where retries become visible.
- Counting a truncated answer as an HTTP-level error corrupts both rates at once: it pumps the error rate and buries the truncation rate, neither of which then means anything. Predict what a one-line classifier change does to his availability and burn numbers, and classify the four failure kinds for the record.
- Failover changes the instance and fallback changes the mechanism: failover is usually safe, while fallback is untested code that runs first on the worst day, and an LLM fallback can succeed and be wrong. Classify any proposed resilience design as retry, failover or fallback, and require the continuous-exercise test before approving a fallback.

## What the records you already have can promise

One record per call

Phase 5A's client writes a run record, one structured row per API call, through run_recorder.py. Each record holds what that call did: its latency, its outcome, its finish reason. This phase reads those records; it does not collect new data.

TTFT measures the queue

Phase 1 showed that TTFT reads the provider's queue depth. It is the time from sending the request to the first chunk coming back. Your 5A client already uses it as the signal that says send less.

The gaps between chunks

Phase 2 recorded the time between chunks of the SSE stream. That is the format that delivers one answer as many small chunks over one open connection. A frozen stream appears there as one very long gap, and the records already carry those gaps.

Measured operating points

Phase 4B ended with targets you measured yourself, not vendor numbers. The same rule applies here: a promise about this feature is built from your own records. So the thresholds come from what your traffic actually does.

These four pieces are the raw material. The records hold latencies, gaps and outcomes. The earlier phases supply what each field means. What is missing is the step from having records to making a promise from them.

The running case shows the cost of that missing step. For two hours, streams froze and answers arrived cut off, and the run records captured all of it. Availability stayed high because truncated and frozen answers still returned 200 OK. Nothing read the records, so nothing noticed. This phase is about reading them: turning them into indicators, promises, alerts and honest names. It starts with the question the incident raises: why was every dashboard green the whole time?

## Why is every dashboard green during the incident?

Green graphs and a broken feature agree with each other, because the graphs watch the wrong events.

For two hours your run records held the freeze and the truncations, and nothing read them. The truncated and frozen answers each returned 200 OK, so the latency indicator stayed green. This section asks why, and it starts with the report your records already produce.

### The report that saw the incident twice

Running slo_report.py --demo over the 2,000-record demo ledger gives four rows. The incident sits in two of them.

indicatortargetactualverdictbudget used

availability99.50%99.30%FAIL140%

TTFT ≤ 1000 ms95.00%99.60%PASS8%

no freeze > 500 ms99.00%89.93%FAIL1007%

answer completed99.00%98.19%FAIL181%

Read the TTFT row first. TTFT is the time from sending the request to the first token coming back. Phase 1 showed it reads the provider's queue depth. It passes at 99.60% during the incident, because a frozen stream still delivers its first token on time. The freeze row fails at 89.93% and spends ten times its budget in the same period. Two indicators measured the same hours, and they disagreed because they counted different events.

Availability fails too, but for an unrelated reason. The demo adds a random 0.4% error rate against a 99.5% target. So of the four rows, only the smoothness row and the completeness row saw your running case. Those are the two rows a standard dashboard does not have.

Predict: availability is 99.9% and TTFT p95 is 800 ms. Ten users say answers were cut off mid-sentence, and one says answers seem dumber. Which graph shows any of that?
Neither graph shows it. A truncated answer returns 200 OK, so availability stays high. It also gets its first token quickly, so TTFT stays low. "Dumber" appears on no graph here either, because nothing in these two indicators reads the answer's content at all. You learn about both failures from the users, weeks in, with little recorded to explain them.

### The vocabulary: indicator, target, budget

Three terms carry the rest of this phase, and each is a ratio or a number built from a ratio.

- An SLI, service level indicator, is the measured ratio of good events to all events of one kind. The smoothness row is a ratio: streams with no gap above 500 ms, over all streams.

- An SLO, service level objective, is the target you set for that ratio. 99.0% on the freeze row is a target, not a measurement.

- The error budget is 100% minus the target: the failure you are allowed. At 99.9% over 30 days the budget is about 43 minutes, and the freeze row spent 1007% of its own.

The ratio form is the point. A count of failures tells you how many, and a ratio tells you how much of your allowance is gone. Alerting on budgets works only because each SLI is a proportion of good events.

### Why the framework expected this failure

The Google SRE Workbook already names indicator types beyond availability and latency. It defines a quality type, the proportion of responses served in an undegraded state. It defines a correctness type, whether the right answer came back. These types exist because some systems can serve degraded results while staying up. An LLM feature is such a system, so each hidden failure mode needs its own indicator of good events.

That gives the four rows of the report, each counting a different good event.

indicatorgood eventwhat it catches

availabilitythe call returnedoutages

TTFTfirst token inside the targetqueueing, prompt bloat, cache regressions

smoothnessno gap above the targetthe stream freeze from your running case

completenessfinish reason is not "length"truncation, which an uptime metric counts as a win

The wrong belief here is reasonable: if the answers turned systematically bad, some existing metric would move. The demo shows it does not, because 200 OK and fast first tokens are compatible with cut-off answers. The belief fails on the definition of the events being counted, not on the quality of the monitoring.

### It happened to the provider, at full scale

Anthropic's postmortem of 17 September 2025 describes three overlapping infrastructure bugs that degraded Claude's output for weeks. A routing error hit 0.8% of Sonnet 4 requests and peaked at 16% on August 31 after a load-balancing change. A TPU misconfiguration corrupted tokens, and a compiler bug affected token selection. Availability dashboards were unaffected throughout. Anthropic's own evaluation suite missed what users reported, in part because Claude often recovers well from isolated mistakes. The provider ran weeks of degraded output that its own monitoring could not see. It had far more monitoring resources than you have.

Evidence
Anthropic, "A postmortem of three recent issues", 17 September 2025, verified 2026-10-10. The routing bug: 0.8% of Sonnet 4 requests, 16% peak on August 31, active August 5 to September 18. The demo report numbers come from slo_report.py --demo on the 2,000-record ledger. The workbook quality and correctness SLI types: Google SRE Workbook, chapter on implementing SLOs, as cited in the phase's references.

The same report shape is what you build in the lab. Exercise E9 runs slo_report.py --demo and asks which row caught the incident, and E8 shows the gap percentiles it reads. The question E9 answers is the one this section opened with: which indicator saw the incident your availability graph missed.

A feature can be up, fast and wrong; quality and smoothness each need their own ratio SLI.

Trusting availability and latency alone costs you weeks of user-reported failures that your records already contained.

Run python phase05_operations/slo_report.py --demo and find the indicator that passes while the freeze row fails at 89.93%.

Four indicators now exist, but the quality row is still a mean score in your head. The next section asks why a mean can never page you.

## Why can a mean score never page you?

A mean quality score cannot spend an error budget, so it can never page you.

The section above gave you four ratio indicators, each a count of good events over all events. This is because only a ratio has an error budget. The quality row is still a score in your head. This section shows what must happen to that score before it can alert. It also shows how much trust the score itself has earned.

Back in the running case: three of the four rows of slo_report.py are ratios by construction. A call either returned or it did not, a gap either exceeded 500 ms or it did not. Quality has no natural dividing line. A model graded one answer 0.82 out of 1.0. Is that good? Until you answer that question per record, you have no fourth row.

### The threshold comes first, the number second

The fix is one step. A judge is a model that scores another model's output against a rubric. The judge's score is a continuous number. A continuous number has no error budget. This is because a budget is the difference between 100% and a target on a proportion. So you threshold the score into a per-record decision: good or bad. The SLI is then the proportion of records that reach the threshold. It sits next to availability and TTFT with the same arithmetic. Pydantic Logfire ships exactly this shape: an evaluation score over a threshold counts as a good event. The same burn tiers apply.

"The mean judge score is 0.87, target 0.85." A mean has no budget. One terrible day moves it by 0.01, and there is no defined point at which anyone must act.

"91.2% of records scored at least 0.8, target 99%." A ratio has a budget: 1% allowed. The month it drops to 98.5%, burn is 1.5x, and the budget is gone after two-thirds of the period.

### Two limits on how tight the quality SLO can be

Once the threshold exists, two facts about judges bound how tight the target may be.

- The judge disagrees with people. The best-known study of LLM judges reports about 85% agreement with human experts when ties are excluded, and 66% with ties counted; two humans agree with each other 81% on the same task. A tool that is wrong at least 15% of the time cannot certify 99.9% on a single request. What it supports is an aggregate rate over many records: you can say "the proportion above threshold fell three points this week", not "request 4,712 was good".

- Per-step quality multiplies down. If each independent step of a multi-step task is good 75% of the time, three good steps in a row happen 0.75 × 0.75 × 0.75, about 42% of the time. A step-level target that looks acceptable composes into an outcome the user calls broken. Set the SLO on the outcome the user cares about, not on the step.

Step quality compounds into outcome quality

Per-step good rate
%
Steps

Outcome good  of the time

Move the slider to 99% per step and ten steps: the outcome is good only 90.4% of the time. This is why the judge's loose accuracy still yields a usable outcome SLO. It is also why a tight per-step promise was never on the table.

### The floor under every quality metric

One more bound sits below the threshold, and it is not about the judge. Even with the same prompt, the same model and every sampling knob off, the output varies. In 2025, Thinking Machines Lab sent one prompt 1,000 times at temperature 0 to a shared endpoint serving Qwen3-235B. It produced 80 unique completions, all identical for 102 tokens and splitting at token 103. The cause is that GPU kernels are not batch-invariant. The batch size changes with server load, so the arithmetic changes with the batch size. This variation with zero intended change is the noise floor of the system.

The noise floor ends a tempting idea: comparing answers text-for-text against a known-good output as a quality floor. Under this finding, exact-text comparison flags nearly every run as a regression. This is because the expected text is only one of 80 honest answers. Your quality metric has to tolerate the floor. The only way to know how much floor you have is to measure it. Send one fixed input many times, score each output with your quality metric, and read the spread. What sits above that spread is signal; what sits inside it is weather.

Evidence
Judge agreement figures: "Judging LLM-as-a-Judge" (Zheng et al., arXiv 2306.05685), cited from the phase and not re-verified. Temperature-0 experiment: Thinking Machines Lab, "Defeating Nondeterminism in LLM Inference", verified 2026-10-10. The post confirms 80 unique completions and divergence at token 103. The threshold-based quality SLI is how Pydantic Logfire implements it.

Threshold the judge score per record, then the proportion of good records is an SLI with a budget.

Alerting on a mean score means the day your quality collapses, the mean drifts down gently and nobody is paged.

Send one fixed prompt five times at temperature 0 and diff the outputs; whatever differs is your noise floor showing.

You can now turn a score into a ratio and say how tight its target may be. What a ratio still cannot do is wake anyone tonight. So the next section asks who gets paged and when.

## Does anyone get paged, and when?

The report tells you the month will fail, and only burn rate tells you whether to wake anyone tonight.

Your four indicators can now say how the month is going, but they read the whole period at once. A report run on day 20 counts the frozen streams from last week. It counts the healthy traffic from this morning in the same pile. That pile is a report, not an alert, because it cannot say whether the bad thing is happening right now.

### The picture: one number for speed, two windows for the verdict

Your error budget, the failure the SLO allows, is a quantity of bad events spread over 30 days. Burn rate is how fast you are consuming that budget. It is computed as the observed bad rate divided by the allowed bad rate. A long window measures the bad rate over hours or days and answers how severe the incident is. A short window, one twelfth of the long one, measures the last few minutes. It answers whether the incident is still happening. An alert fires only when both windows are burning, so severity alone cannot page and noise alone cannot page.

-

  freeze, hours 5 to 8

  long window at hour 8: still burning (10.07x)

  short window: quiet (0.17x)
  hour 0
  hour 10
  Illustration of the demo incident, not measured timing.

The long window still counts the freeze after it ended, and the short window shows the present is clean, so nobody pages.

Predict: the monthly report says the SLO will fail, but the freeze ended three hours ago. Does anyone get paged, and which number decides?
No one is paged, and the short window decides it. The long window still holds the frozen hours, so its burn rate stays high and says the incident was severe. The short window sees only the last few minutes, which are healthy, so its burn rate is near zero. Because the alert needs both windows burning, an ended incident produces a review note instead of a page. If you alert on the long window alone, your phone rings at 3 a.m. for a problem that fixed itself three hours earlier.

### What burn numbers mean

Burn 1 means the bad rate sits exactly on the SLO, so the budget lasts the whole 30 days. Burn 10 means you are failing ten times faster than allowed, so the budget is gone in 3 days. Burn 1000 empties a 99.9% budget in about 43 minutes. In the demo, the freeze indicator computed burn 10.07x over the full ledger. That prints as the budget gone after 10% of the period.

burn 1budget lasts 30 days

burn 10budget gone in 3 days

burn 1000budget gone in 43 min

The same demo over the last 300 minutes gives the freeze indicator a burn of 0.17x. One incident, two honest numbers, because each window answers a different question.

### Why neither window works alone

The wrong belief here is reasonable. You would think one window sized between noise and delay could do both jobs. It cannot, because the two jobs pull the window in opposite directions.

- A pure long window moves slowly by design, so it keeps paging long after the incident resets. The workbook measured a 36-hour reset time for a single-window alert, versus about 5 minutes for the two-window rule.

- A pure short window reacts fast, so a few normal failures cross the threshold and you get paged on noise.

- Requiring both means the page comes only when something severe is happening now, and the two-window design measured a reset time of about 5 minutes.

### The working recipe

The workbook publishes three tiers, and the short window is always one twelfth of the long one. These figures assume a 99.9% target over 30 days.

actionlong windowshort windowburn ratebudget consumed

page1 hour5 minutes14.42%

page6 hours30 minutes65%

ticket3 days6 hours110%

You can check the top row by hand, because burn multiplied by window length gives budget consumed:

14.4 x 1 hour / 720 hours = 2% of the monthly budget in one hour

Burn rate from a bad rate

Bad rate (%)
Burn against a 99.5% target

Budget gone after

Evidence
Tier numbers, the one-twelfth short-window rule, and the 36-hour versus 5-minute reset measurement come from the Google SRE Workbook chapter "Alerting on SLOs", verified 2026-10-10. The demo figures, burn 10.07x over the whole period and 0.17x over the last 300 minutes, come from running python phase05_operations/slo_report.py --demo --window-minutes 300 on 2026-09-17.

### When the math cannot run

This whole recipe assumes traffic, and your first production LLM feature will not have much. The workbook states it plainly: for low-traffic services a single failed request can read as burn rate 1,000. It can page spuriously. Three mitigations exist, and each costs you something different.

- Generate artificial traffic so the denominator is never tiny, at the cost of extra provider bill.

- Group several low-traffic services into one monitored group, at the cost of not knowing which one failed.

- Lower the SLO or lengthen the window, at the cost of slower detection.

Alert on burn rate over two windows: the long one says how bad, the short one says still happening.

One window must choose between paging on noise and paging hours after the incident reset.

Run python phase05_operations/slo_report.py --demo --window-minutes 300 and compare the freeze row across the two tables.

Your indicators and alerts are now honest about what you record. But the records themselves carry names. So the next section asks what your client is actually allowed to call a token.

## What is your client actually allowed to call a token?

The client sees chunks and the server sees tokens, so its field must say chunk.

Your burn alerts now fire at the right time. Every number they read comes from a run record. Each field name in it claims something about what the client saw. In the running case, run_recorder.py writes one latency field per call. If that field says token while the code timed a chunk, every dashboard above it claims something false.

The answer arrives as an SSE stream, the response format that delivers many small chunks over one open connection. A chunk is not a token, because one chunk may carry several tokens and the next may carry none. Only the server sees tokens leave the model. So only it can time TTFT, the wait from request to first token. What your client can time is the time to first chunk. It is the seconds from the request to the first chunk arriving.

gen_ai.response.time_to_first_chunk = 120 ms

-
request sent

ping · 0 tokens

empty delta · 0 tokens

-

-

-
first text, 4 tokens

-

-

-

-
120 ms
340 ms
600 ms
Four tokens share one arrival time at 600 ms, and the stream never says when token 1 was generated.

What the client can honestly name is 120 ms, the first chunk of any kind. Token births are invisible on the wire. Illustration, not measured.

Predict: the ping arrives at 120 ms and the first text at 600 ms. What number does a client-side "time to first token" record?
Nothing honest. If the code times the first chunk of any kind, it records 120 ms, the arrival of a ping with no text in it. If it waits for content, it records 600 ms, the arrival of one chunk carrying four tokens at once. Neither is the moment a token was generated. The client must record time to first chunk and leave token timing to the server.

Nothing in the stream marks a token's birth time, and three chunk behaviours make it unrecoverable on the client side:

- The server may buffer several tokens and send them as one chunk, so one arrival time covers several different generation times.

- Pings and empty deltas arrive with no content, so the first chunk can appear before any token exists.

- One provider pads chunks to similar sizes against side-channel attacks, so chunk bytes cannot stand in for a token count.

So the OpenTelemetry GenAI conventions, the standard vocabulary of field names for LLM telemetry, split the measurement in two. In that vocabulary your call is one span, a single timed operation in a trace. A field on the span claims that the operation itself observed it. The client observes a chunk arrival, and the server observes a token leaving the model. So each side gets its own name.

NameWhere it livesIts own definition

gen_ai.response.time_to_first_chunkclient span attribute, seconds"time to receive the first chunk... in the response stream"

gen_ai.server.time_to_first_tokenserver metric, seconds"time to generate first token for successful responses"

A client that records "time to first token" claims a server-side event it never saw. run_recorder.py follows the spec by naming the chunk. The matching histograms keep the same honesty. On the branch this course read, they are gen_ai.client.inference.time_to_first_chunk and gen_ai.client.inference.time_per_output_chunk, and the whole call is gen_ai.client.inference.duration.

These names move. An earlier draft of this course recorded gen_ai.client.operation.time_to_first_chunk, and the same repository now says gen_ai.client.inference.time_to_first_chunk. There are no release tags and the stability is development, so pin the commit you read and expect renames.

### The libraries do not record it for you

You cannot buy your way out of naming it yourself. The specification repository generates a conformance report. It runs 13 real client libraries against a mock server and validates their telemetry:

AttributeLibraries that emit it

gen_ai.operation.name12 to 13 of 13

gen_ai.usage.input_tokens12 to 13 of 13

gen_ai.response.finish_reasons12 to 13 of 13

gen_ai.response.time_to_first_chunk0 of 13

gen_ai.request.stream1 of 13

gen_ai.request.temperature1 of 13

The reference scenario for one provider does stream, with stream=True and usage included. It still never sets the first-chunk attribute, so the reference client does not follow its own recommendation. Measure chunk timing in your own code, as run_recorder.py does.

Evidence
The two definitions are quoted from registry.yaml (span attribute) and metrics.yaml (server metric) in the open-telemetry/semantic-conventions-genai repository, main branch, read 2026-10-10. The repository has no release tags and every definition carries development stability. On the same date the client histograms were named gen_ai.client.inference.*, an earlier draft of this course used gen_ai.client.operation.*, and gen_ai.client.operation.duration carried a note not to report it for inference operations. The conformance counts are cited from the course phase's reading of the repository's generated report and were not re-verified in this run.

Run python phase05_operations/run_recorder.py --self-test and find the check "first-token uses the SPEC name, not an invented one". It exists because the recorder's first draft invented app.gen_ai.ttft_ms on the assumption that no standard name existed, and one did, in seconds. Check the spec before you invent a name. The lab then continues this: E12 finds the chunk and token names in code, and E13 records one real call through this recorder.

Clients see chunks, servers see tokens, and only servers can time a token.

Trusting auto-instrumentation here means the first-chunk attribute is never recorded at all.

Run python phase05_operations/run_recorder.py --self-test and read the first-token check.

Your latency names are now honest, but the span that carries them still covers the whole retried operation. The rejections the previous lesson counted as load leave no trace in it. So the next section asks where your 429s went.

## Where did your 429s go?

The names on your latency fields are honest now. The second half of the problem uses the same rule that gave you the span: the span is also the container that hides your rejections.

Phase 5A taught you to treat a 429 as a capacity report you must read. The OpenTelemetry span guidance says a span should cover the whole logical operation, meaning the call as your code sees it, with every automatic retry inside it. Add the verified SDK default of two retries, and the common failure shape in a rate-limited month disappears from the record.

Here is what one slow Tuesday afternoon call looks like on the wire, and what the span keeps of it.

  Three wire attempts inside one span (illustration, not measured)

  Step 1: the provider rejects the request with a 429 after 40 ms. The SDK records nothing; it sleeps and tries again.

  Step 3: a second 429, a second backoff. Two capacity reports have arrived and the span shows an empty lane.

  Step 5: the third attempt succeeds. The span covers all three attempts and the two sleeps, and records one success.

  Illustration drawn from the span rule and the SDK default of two retries, not from a measured trace.

The mechanism, step by step:

- The SDK sends your request and gets a 429. It waits, because 429 is on its retry list from Phase 5A.

- The SDK retries up to twice inside the same call. From your code's view, one call is still running.

- The third attempt succeeds. The span, which covers the whole logical operation, closes with a success status.

- OpenTelemetry's guidance says not to record errors that were retried and handled, so the two rejections leave no record.

The cost lands on the signals you built in Phase 5A. Your breaker trips on observed pressure, and your capacity review reads rejection counts. Both now read a month of heavy rate limiting as a month of clean successes. The provider's status page and your own bill will disagree with your traces, and your traces will look wrong for claiming it, because the rejections happened while the span kept one success.

A month of rate limiting under sustained pressure records zero rejections by default. Your 429-based signals are reading an empty set.

Two escapes make rejections visible. Each has a price.

- Set max_retries=0 and retry in your own code. Each attempt becomes its own call, so every 429 is a record you classify with the Phase 5A header-reading rules. The price is that you now own backoff and jitter, which the SDK did competently.

- Instrument the HTTP layer below the SDK. Every wire attempt gets its own low-level span, and the SDK span stays clean on top. The price is trace volume: one logical call now produces more spans, and a retry storm produces many.

This is a real choice, not a bug to patch. If you keep the default, retry logic is tested code but your rejection counts are fiction. If you take either escape, the counts are honest and you own more machinery. The minimum useful record from the last section assumes an honest outcome field: a finish reason and a status per attempt you can see, and latency fields per call you can see. Choose which one that is, and write the choice next to the metric, the same discipline you applied to inter-chunk latency.

Evidence
The span rule ("a span should cover the duration of the logical operation with all retries") is quoted in the phase from the OpenTelemetry span guidance; the hunter did not re-locate the exact passage this run, so treat the wording as phase-cited. The SDK default of two retries is verified from Phase 5A. The guidance not to record errors that were retried and handled is stated in the phase's reading of the OpenTelemetry documentation.

A span covers one logical operation with all retries, so SDK retries make your 429s invisible.

Trusting the default means testing your Phase 5A overload signals against a record with zero rejections in it.

Set max_retries=0 on one call today and count how many attempts a busy hour actually costs you.

Your errors and rejections are now recorded honestly, but the failure that returns 200 OK with a finish reason is still one classifier line away from corrupting both of your rates, and the next section asks that question: when did a one-line change fabricate an incident?

## When did a one-line change fabricate an incident?

One classifier line decides whether truncation is a quality signal or a fabricated outage.

Your errors and rejections are now recorded honestly. But one failure still returns 200 OK with a finish reason. It is one line away from corrupting both of your rates.

Back to the running case. Your demo ledger holds 2,000 run records with 14 real errors and 36 truncated answers. Tonight someone on the team edits the recorder with one idea. The idea is that a truncated answer is a bad answer, so count it as an error. Nothing about the service changes, and tomorrow's report shows an incident.

This phase introduces the finish reason, the provider's own label for why generation stopped. It uses that label to decide whether the answer completed, not the HTTP code. The new part here is only the monitoring consequence. Four failure kinds arrive in three HTTP shapes, and a single "did it raise?" bit cannot represent them.

Failure kindHTTP shapeWhat the record must say

TimeoutNo responseerror.type set, status failed

429 rejectionUsually invisibleRetried inside the SDK span, as the last section showed

Truncated answer200 OK, finish reason lengthStatus incomplete, never an error

Filtered completion200 OK, with a finish reasonStatus incomplete

Filtered promptHTTP 400An error, because the request itself was rejected

The filter row shows the asymmetry. The same content policy produces a 400 when it rejects your prompt and a 200 when it cuts the completion. Only the finish reason separates the second case from a healthy answer.

The OpenTelemetry GenAI spec gives this record its vocabulary through gen_ai.response.status: completed, failed, or incomplete status. The spec defines it as "the response stopped before generation completed". That happens, for example, because a token limit or content filter was reached. Truncation is a completed request with an incomplete answer. It is a quality defect, not an outage.

Predict: The team doubles max_tokens to stop truncations, and the error rate suddenly halves. Nothing else changed. What just happened?
The error rate never measured errors. It measured truncations wearing the error label, because the classifier mapped finish_reason == "length" to a failure. Raising max_tokens removed truncations, so the false errors disappeared too. The corrected rates now show the opposite truth. Availability was always fine. Truncation, which nobody graphed, was the real defect the whole time.

The wrong version is one line different from the right one:

# WRONG: truncation counted as a failure.
if rec.error_kind or rec.finish_reason == "length":
    attrs["error.type"] = rec.error_kind
    attrs["gen_ai.response.status"] = "failed"

# RIGHT: truncation is incomplete, not failed.
if rec.error_kind:
    attrs["error.type"] = rec.error_kind
    attrs["gen_ai.response.status"] = "failed"
elif rec.finish_reason == "length":
    attrs["gen_ai.response.status"] = "incomplete"
else:
    attrs["gen_ai.response.status"] = "completed"

Now the cost, on your demo ledger of 2,000 records, against the 99.5% availability target. The allowed bad rate is 0.5%, and burn rate is the observed bad rate divided by the allowed one:

right mapping   errors = 14 / 2,000          availability = 99.30%   burn = 0.7% / 0.5% = 1.40x
wrong mapping   errors = 14 + 36 = 50 / 2,000 availability = 97.50%   burn = 2.5% / 0.5% = 5.00x

Notice what the one line did to each number. Burn 1.40x is a slow ticket at the workbook's tiers. 5.00x approaches the page tier at 6x, so one sed edit nearly fabricates a page. At the same time the truncation rate vanished. Truncations dissolved into the error count, so they no longer had a row of their own. Both rates now lie in opposite directions.

Evidence
The ledger counts (2,000 records, 14 errors, 36 truncations) come from the phase's slo_report.py demo ledger. The availability and burn arithmetic is the author's, derived from those counts, not independently re-derived (inferred). The wrong-mapping run is dated. The phase's review ran it in a copy on 2026-09-17. The self-test printed [FAIL] a truncated answer is 'incomplete', not an error. The gen_ai.response.status enum and its incomplete definition are verified in registry.yaml, read 2026-10-10.

You reproduce this failure yourself in E15. You run the self-test with the wrong classifier in place and watch the incomplete check fail. On the demo ledger, that one line would fabricate an incident-level burn. The question it answers: can you spot this bug in a diff before it reaches the report?

Truncation is a completed request with an incomplete status, never an error.

Mapping finish_reason == "length" to an error pumps the error rate and buries the truncation rate at once.

Compute both availability numbers on your own ledger today: with and without truncations counted as errors.

Your classification is now honest, so a quality failure can fire. When it fires, the record must answer what changed. The next section asks that question: what made the output worse when nothing was deployed?

## What made the output worse when nothing was deployed?

When quality fails, the record must say which of four things changed.

Your classification is now honest, so a quality failure can fire an alert. Each record holds a span, one timed operation with attributes, and those attributes decide what the alert can tell you. An alert that only says "quality dropped" leaves you with a week of user reports and no suspect. The Anthropic postmortem from earlier in this lesson showed what that looks like at scale. Three infrastructure bugs degraded output for weeks, and nobody had the fields to localise it quickly.

### The four suspects

When answers get worse and you deployed nothing, four things could have changed. The model could differ from what you asked for. The prompt could be an old version. The retrieved data could come from a stale corpus. The provider's serving stack could have changed around a pinned model.

The OpenTelemetry standard names attributes for only the first two. You record the other two yourself.

SuspectAttributeStatus

The modelgen_ai.request.model and gen_ai.response.modelstandard names exist

The promptgen_ai.prompt.name and gen_ai.prompt.versionstandard names exist

The datayour own key, for example app.corpus.versionno version attribute exists

The serving stacknothing reliable; one provider offers a fingerprintno attribute exists

The model row carries the cheapest detector you will build. The request field is what you asked for. The gen_ai.response.model attribute is the model that actually answered. The two differ when the provider routes your call somewhere else, and one alert on "these two fields differ" catches a silent switch the day it starts.

The prompt row matters because prompts change more often than code reviews suggest. The prompt version attribute ties each record to the exact prompt text that produced it. Without it, a bad answer three weeks after a prompt edit has no recorded cause.

The data row has a gap. The spec defines a data-source identifier but no version field, so retrieval over a rebuilt index is invisible. Invent the key before you need it, because adding it after the incident recovers nothing.

The fourth suspect is the one you cannot record directly, and Anthropic documents it in its own model docs. Model weights are fixed for a given ID, but the serving infrastructure around the model can change over time. Anthropic's postmortem is the proof that this reaches users. The 80 unique completions at temperature 0 from the earlier section sit on the same axis: a shared endpoint varies even with the same weights and the same prompt.

A pinned model ID pins the weights, not the behaviour. Record both model fields and alert when they differ. Expect drift you cannot attribute at all, and keep your own noise floor, the output variation you measure with no change, as the baseline any alert must exceed.

### What each recorded field costs

Recording everything is not free, and the cost splits cleanly by kind. Metadata attributes stay flat at about 1,450 uncompressed bytes per span at every prompt size. Only the prompt and completion content grows, and it grows fast.

Prompt sizeMetadata onlyWith prompt and completionGrowth

500 in / 150 out107 B per span1,210 B per span11x

4,000 in / 500 out109 B per span6,932 B per span64x

30,000 in / 1,000 out110 B per span47,156 B per span430x

The failure this table predicts is silent. The default OpenTelemetry Collector accepts 4 MiB per request, and the default export batch is 512 spans. At 4,000 input tokens with content, 512 spans total about 11 MB, so the batch exceeds the limit. The export fails without an error in your logs, and your records stop arriving while the feature looks green.

The rule that survives the table is a split by kind. Sample the spans, because content makes them expensive. Keep the metrics complete, because counters and histograms ride on the flat 1,450 bytes of metadata. Your availability, TTFT, smoothness and completeness ratios cost the same at any prompt size.

Evidence
The attribute names gen_ai.prompt.name, gen_ai.prompt.version and gen_ai.data_source.id are verified in registry.yaml, read 2026-10-10. The Anthropic serving-infrastructure note is from its model documentation as quoted in the phase. The span-size measurements (107 B to 47 KB, gzipped, five seeds) are the author's numbers; the measuring script is not in the course repo, so they could not be re-run (unverified). The 4 MiB collector limit and 512-span batch are OpenTelemetry defaults.

In E13 you record a real call and read it back, and E14 prices the telemetry at your own request rate. The question both answer: can your ledger say which of the four suspects moved, at a cost you accepted on purpose?

Record the model asked for, the model that answered, the prompt version, and a data-version key you invent.

Content in spans grows 430x while metadata stays flat, so one default batch setting drops your records silently.

Check your last run record for a response-model field; if it is absent, a silent model switch is unrecorded.

Attribution now catches a degraded model, and the natural next move is to route around it when it fails. The next section asks what separates failover from fallback, and which one ran for the first time on your worst day.

## What is the difference between failover and fallback, and which one ran for the first time on your worst day?

Attribution can now catch a degraded model. So the natural reflex is to route to another model when the primary fails. This section takes that reflex apart.

A second model feels like insurance, but it is untested code that runs first on your worst day.

Back to the running case. Your provider has a bad afternoon, and someone proposes routing the feature to a second model to keep it up. The decision you make in that meeting has a documented history, and most of it is bad.

The Amazon Builders' Library names four strategies for surviving a failure. A retry is the same call again. A proactive retry is the same call again in parallel. Failover is the same call against a different copy of the endpoint, so only the instance changes. Fallback is a different mechanism for the same result, so the code path itself changes. Failover is usually safe, because the running code is identical. Fallback is a second product that stays idle until the day everything else is on fire.

- request failstimeout, 500, or overload

- failoversame prompt, another deployment of the same model

- fallbacka cheaper model, a cache, a retrieval-only path

Predict: the provider is down and someone proposes routing to a second model. Before you hear anything about testing, name two things that must already be true in production for that design to be safe.
First, the second-model path must already run continuously against real traffic, treated as an equally valid source. Otherwise it is untested code. Second, every run record must stamp which path answered, through gen_ai.response.model. Otherwise the degraded answers are invisible to every indicator you built in this phase. If either is missing, the design is a fallback promise, not a failover.

Why is fallback so reliably harmful? The Builders' Library article gives five reasons, and each is a property of the mechanism, not of the engineer:

- Fallback is harder to test, because the failure it waits for is rare and its inputs are hard to fake.

- The fallback can fail too, and it is usually less tested than the primary it replaces.

- It often makes the outage worse, because it runs exactly when the system is weakest.

- It is often not worth the risk, because a bounded error response serves the user nearly as well.

- It hides bugs, which then surface years later in code nobody remembers writing.

Amazon, 2001. Web servers cached shipping speeds per server, with a fallback to the database. All caches failed at about the same time, every web server hit the database, and the database locked up. "The fallback turned a partial website outage into a full-site outage. The partial outage meant not being able to display shipping speeds. The full-site outage meant no pages loaded at all. It took down the entire Amazon fulfillment network in the back end."

The article's escape hatch is a test, not a ban. A service must run both the fallback and the non-fallback logic continuously. It must treat the fallback as an equally valid source of data. A fallback that meets that bar is exercised code, and at that point it behaves like failover. A fallback that runs only during incidents has its first production run on your worst day.

An LLM adds a failure mode the general case does not have. A classic fallback works or returns an error. An LLM fallback returns a fluent, confident, wrong answer with a clean 200 OK, so no indicator moves. Microsoft's documentation for its semantic cache states the same risk directly. A cache that answers by similarity "can return responses that are incorrect, outdated, or unsafe for the current request". Its guidance is to start the similarity threshold at 0.05, because mismatches become likely above 0.2. Every degraded answer also needs stamping in the record, or your own quality SLI cannot see it.

Routing to another provider is not a configuration change either. Two measurements from the phase show how much moves with the prompt and the tokenizer:

76 pointsaccuracy swing from format changes on one model

~30%token-count difference between two of one provider's own tokenizers

A format change is meaning-preserving and still moves accuracy by up to 76 points. But format rankings transfer between models only about 57% of the time. A tokenizer change re-prices every request and moves your context headroom. That 30% gap is between two tokenizers from the same provider. Crossing providers costs more.

If you build a fallback anyway, the phase sets four conditions:

- Split the chain by error class, because a context overflow needs a larger context and a 429 needs another deployment, not one shared chain.

- Never catch every exception, because a handler for Exception turns your own parsing bug into a silent fallback; name the exceptions you mean.

- Stamp the answering path in the record, filling gen_ai.response.model with the model that actually answered.

- Run it continuously, on a share of real traffic, or do not ship it.

Classified this way, most situations that reach for "fallback" turn out to be something else:

situationwhat it iswhat to do

one deployment downfailoverroute to another deployment of the same model

provider downbounded stalenessfail the request, or serve a stamped stale answer from the same mechanism

rate limitedsheddingshed and retry later, as Phase 5A measured

context overflowcompactioncompact the prompt; a different model keeps the same limit risk

budget exceededdeliberate degradationdegrade on purpose and log it loudly

want a cheaper modelroutinga routing decision with a control group, not an incident response

cross-mechanism fallbackfallbackonly with continuous exercise and the answering path stamped

Evidence
The four-strategy definitions, the 2001 incident quote and the continuous-exercise requirement share one source. They are from the archived Amazon Builders' Library article "Avoiding fallback in distributed systems", read 2026-10-10. The semantic-cache warning and the 0.05 and 0.2 thresholds are from Microsoft's llm-semantic-cache-lookup documentation, read 2026-10-10. The 76-point format swing, the 57% ranking correlation and the 30% tokenizer gap are cited from the phase. The underlying papers were not re-opened.

In the lab you can try the decision yourself. Classify each row of your own error history as failover, shedding, or fallback. Then check whether any fallback path in your code runs today or only on failure. The record answers the second half of that question.

Failover changes the instance, fallback changes the mechanism, and only fallback turns partial outages into total ones.

A fallback that runs only in incidents is untested code, and an LLM fallback can succeed and be wrong.

Find one fallback in your code and check whether a stored record shows which path answered.

You can now define the four indicators and alert on their burn rates. You can record calls under the real names and refuse a fallback with reasons. The recall section gathers these claims. Then Phase 6A asks how many servers hold your TTFT target when tenants share the fleet.

## What you can do now, and what comes next

Five claims carry this phase. Read them again; each should sound like something you would say to a colleague.

- A green availability-and-latency dashboard can hide a broken feature. Truncation, degraded output and frozen streams each return 200 OK, so each needs its own SLI as a ratio of good events, because only a ratio has an error budget. (Why is every dashboard green during the incident?)

- A mean score can never page you, because a mean has no budget. The quality indicator must be a proportion of records past a threshold, and the judge's noise sets how tight that threshold can be. (Why can a mean score never page you?)

- Burn rate measures budget consumption speed, so it turns a monthly report into an alert. The long window says how bad the incident is, and the short window says whether it is still happening. (Does anyone get paged, and when?)

- The client sees chunks and the server sees tokens, so a client-side "time to first token" lies by name. The span covers the logical operation with its retries, so a 429-then-success records as one clean success. (What is your client actually allowed to call a token? and Where did your 429s go?)

- Truncation is incomplete, not an error. Counting it as an error pumps the error rate and buries the truncation rate, so one line of classifier code can fabricate an incident. (When did a one-line change fabricate an incident?)

- Failover changes the instance and fallback changes the mechanism. Failover is usually safe, while fallback is untested code that runs first on your worst day. (What is the difference between failover and fallback?)

You can now define availability, TTFT, smoothness and completeness as ratio SLIs with error budgets. You can alert on burn rate over two windows instead of reading a monthly report. You can record every call under the real OpenTelemetry GenAI names, so the record answers what changed when a quality alert fires. You can also refuse most fallback designs with reasons, because the record shows which path answered.

Your TTFT SLO raises a question this phase did not answer. Holding a target p99 takes a specific number of servers at a specific load, and Phase 6A asks how many it takes when several tenants share the fleet.

## Hands-on lab

Seven exercises come from your phase, plus one new one for the fallback section. Only E13 needs an API key.

-  E8 offline See what an average hides. An SLI must be its own indicator, because a mean hides a frozen stream.
python phase05_operations/run_recorder.py --demo --role cache_demo

Expected: ITL  p50    24ms  p99    900ms  MAX GAP    900ms, and a note that the worst gap is 37x the median.

-  E9 offline Find the incident that TTFT misses. Availability and latency alone cannot see a frozen stream.
python phase05_operations/slo_report.py --demo

Expected: TTFT passes at 99.60%, and the freeze indicator fails at 89.93% with burn 10.07x.

-  E10 offline Two windows, two answers. The long window sets severity, and the short window shows whether it is still happening.
python phase05_operations/slo_report.py --demo --window-minutes 300

Expected: the freeze indicator fails over the whole period but passes at 99.83% over the last 300 minutes, 601 records, because the incident had ended. The block BURN RATE, LAST 300 MINUTES shows burn  0.17x, while the whole-period block shows burn 10.07x.

-  E11 offline Do the burn arithmetic by hand. Burn rate is a ratio, so it turns a monthly report into an alert. For a 99.9% SLO over 30 days, compute the burn rate of a 1% error rate and how long the budget lasts.
allowed bad rate = 0.1%
burn             = 1% ÷ 0.1%        = 10
budget lasts     = 30 days ÷ 10     = 3 days

Check your answer against the formula at slo_report.py:347.

-  E12 offline Read the naming decision, because a chunk may carry several tokens or none. Open otel_attributes at run_recorder.py:200 and read the docstring on chunk and token.
python phase05_operations/run_recorder.py --self-test

Find the line "first-token uses the SPEC name, not an invented one". Then answer why a client cannot honestly report time to first token.

-  E13 live Record a real call, because the ledger is the deliverable.
python phase05_operations/run_recorder.py --model <your-model> --role cheap --ledger runs.jsonl
python phase05_operations/slo_report.py --ledger runs.jsonl

Expected: one JSON object per call, and an SLO table from your own traffic, at a cost of about $0.01.

-  E14 offline Price your telemetry before you turn it on, because metadata is flat while content grows. Use your median prompt and completion sizes with the section 5.5 table to estimate bytes per span, with and without content. Multiply by your request rate for a monthly figure, and compare with the flat 1,450 bytes of metadata.

-  E15 offline Break it: count truncation as an error, and watch the test catch it.
B=phase05_operations/rr_broken.py
sed 's/    if rec.error_kind:$/    if rec.error_kind or rec.finish_reason == "length":/' phase05_operations/run_recorder.py > $B
python $B --self-test

Expected: [FAIL] a truncated answer is 'incomplete', not an error, then 1 FAILED, exit code 1, with the other 16 checks passing. Clean up with rm $B.

-  Fallback simulation offline, new No exercise in your phase touches the fallback section, so this one is new. It shows how a fallback chain can carry one point of congestion onto a second system.

- Write a small simulation with two queues, primary and fallback, each serving 50 requests per second.

- Offer more requests per second to the primary than it can serve, so its queue grows, and mark any request that waits too long as failed.

- Route each failed request to the fallback queue, and count failures there too.

- Run it twice: once with the fallback path live, once with failures simply returned.

without fallback: primary degrades, fallback queue idle
with fallback:    fallback queue now shares the overload

Look for the point where the fallback's own failure rate starts climbing. That is the 2001 pattern in miniature: the fallback did not fail itself, but it carried the congestion into a system that was healthy. The question it answers: when is returning an error cheaper than keeping the feature up?

Evidence
Every offline command (E8 to E12, E14, E15) was run on 2026-09-17 and the Expected lines match. E13 is unverified against a live provider, because no API key was available. The availability shift named in E15 (99.30% to 97.50% on the demo ledger) is the author's arithmetic, not independently re-derived.

With the lab done, the checkpoint asks you to do the arithmetic and the classification without the scripts.

## Checkpoint

The lab scripts did the arithmetic for you. These five questions do it by hand, so you can check the scripts were not the lesson. Answer each one in your own words before opening its sketch.

- Burn arithmetic. Your quality SLO is 99% over 30 days on answers reaching a judge threshold. In the last hour, 4% were below the threshold. (a) Compute the burn rate. (b) How long does the budget last? (c) Should this page someone, and which short window confirms it?
Answer sketch
(a) The allowed bad rate is 1%, so burn is 4 ÷ 1 = 4. (b) At burn 4 the 30-day budget lasts 30 ÷ 4 = 7.5 days. (c) Page thresholds are 14.4 over one hour and 6 over six hours, so burn 4 is below both. It is a ticket: burn 1 over three days, confirmed over six hours as the short window. At 6% bad the burn would be 6, a six-hour page confirmed over 30 minutes.

- The judge ceiling. A colleague proposes "99.9% of answers our judge rates good". Give two reasons this cannot hold: one about the judge, one about task shape.
Answer sketch
The judge agrees with human experts about 85% of the time (66% with ties counted), so it cannot certify 99.9% per request. It can only back an aggregate rate. And per-request quality multiplies over the steps of one task, so even 75% per step gives 0.75 × 0.75 × 0.75 ≈ 42% over three steps. Set the target on the outcome the user sees.

- The classifier change. The team doubles max_tokens to stop truncated answers, and the error rate halves with no other change. Explain what happened, and which two rates the old classifier corrupted.
Answer sketch
The classifier mapped finish_reason == "length" to error. Doubling max_tokens removed truncations, and those records moved from "error" to "success", so the error rate fell. The old mapping counted a truncation as both a failed request and a hidden defect, so it pumped the error rate and buried the truncation rate. On the demo ledger, that one line moves availability from 99.30% to 97.50% and burn from 1.40x to 5.00x. The honest record is HTTP 200 with status incomplete.

- Telemetry volume. Your median request is 4,000 input and 500 output tokens at 10 requests per second. (a) Estimate the monthly telemetry volume with content capture off and on. (b) Your collector accepts 4 MiB per request and batches 512 spans. Does a batch fit with content on?
Answer sketch
(a) A span is about 109 compressed bytes without content and 6,932 bytes with it. A month has about 25.9 million spans at 10 requests per second, so about 2.8 GB without content and about 180 GB with it, roughly 64 times more. (b) No: one uncompressed span with content is about 21 KB, and 512 of them is about 11 MB, over the 4 MiB limit, and the export fails silently. Lower the batch below 200 spans, raise the limit, or store content outside the trace.

- The proposed fallback. A colleague says: "We fall back to a cheaper model when the primary fails, so we are covered." Reject or condition the design with three objections, covering testing, how an LLM fallback fails, and one popular helper's default.
Answer sketch
First, a fallback that runs only during incidents is untested code on the worst day, so approve it only if both paths run continuously against real traffic. Second, a cheaper model that answers still returns a fluent 200 OK, just a worse answer, so it can succeed and be wrong and no monitor turns red; Microsoft's semantic-cache documentation warns such a path can return incorrect, outdated or unsafe responses. Third, the popular retry helper catches a bare Exception by default, so your own parsing bug starts the fallback silently. If it is built anyway, split by error class and stamp which path answered in the record.

If all five felt routine, the phase did its job: the numbers live in your head now, not in the scripts.

## Cheatsheet

FOUR INDICATORS (availability + latency cannot see wrong or frozen answers)
  availability   the call returned
  TTFT           first token inside target
  smoothness     no gap above target        <- the Phase 2 freeze
  completeness   finish_reason != "length"  <- a 200 OK that dashboards count
  demo: TTFT PASSES 99.60%, freeze FAILS 89.93% (burn 10.07x)
        availability fails from a separate 0.4% background error rate

ERROR BUDGET AND BURN
  budget = 100% - target      99.9% / 30d -> about 43 minutes
  burn = bad rate / budget    burn 1 -> 30 days | 10 -> 3 days | 1000 -> 43 min
  page    burn 14.4  over 1h  confirmed over 5m   (2% of budget)
  page    burn  6    over 6h  confirmed over 30m  (5%)
  ticket  burn  1    over 3d  confirmed over 6h   (10%)
  short window = 1/12 of the long window
  tiers read from the SRE workbook, 2026-10-10
  low traffic: one failed request can read as burn 1,000
    -> artificial traffic, group services, or lower the target
  latency ladder: 90% < X | 99% < 10X | 99.9% < 100X
  PAIR LATENCY WITH TOKENS.  total = TTFT + (time per token x tokens)

QUALITY AS AN SLI
  good event = record REACHES a threshold, never the mean score
  judge: about 85% agreement, ties excluded (66% with ties) -> aggregate only
  0.75^3 is about 42% for three steps at 75% -> SLO on the outcome
  noise: 1,000 runs at temp 0 -> 80 unique completions (Thinking Machines)
    -> exact text is useless. Measure your floor with your own metric.
  gaming: delay tokens, drop slow requests. Keep completeness beside latency.

TELEMETRY NAMES  (semantic-conventions-genai, main branch, read 2026-10-10)
  CLIENT says CHUNK. SERVER says TOKEN.
    gen_ai.response.time_to_first_chunk          span attribute, seconds
    gen_ai.server.time_to_first_token            server metric, seconds
    gen_ai.client.inference.time_to_first_chunk
    gen_ai.client.inference.time_per_output_chunk
    gen_ai.client.inference.duration
  no release tags exist: pin and cite a commit
  required: operation.name, provider.name   span name "{operation} {model}"
  span covers ALL RETRIES -> 429s INVISIBLE by default
  0 of 13 reference libraries emit the first-chunk attribute (phase-cited)
  "ITL" has two meanings across tools. Write down yours.

RECORDING FAILURES
  timeout         error.type + status Error
  429             usually invisible (retried inside the span)
  truncation      NOT an error: finish reasons ["length"], status "incomplete"
                  gen_ai.response.status: completed | incomplete | failed
                  as an error on the demo: availability 99.30% -> 97.50%,
                  burn 1.40x -> 5.00x (author's arithmetic, inferred)
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
  metadata FLAT about 1,450 B raw.  10 rps = 25.9M spans/month
  4 MiB collector limit x 512-span batch FAILS with content on
    -> keep the batch under 200 spans or store content outside the trace
  sample SPANS, keep METRICS at 100%; parentbased_traceidratio only

FALLBACK
  retry = same call | failover = same mechanism, other instance (SAFE)
  fallback = DIFFERENT mechanism (the one with the history)
    Amazon 2001: fallback turned a partial outage into a full-site outage
  test: does the fallback run CONTINUOUSLY on real traffic?
  an LLM fallback can SUCCEED AND BE WRONG
  semantic cache: threshold 0.05 to start, above 0.2 mismatches likely
  split by ERROR CLASS; never catch bare Exception; record WHICH path answered
  cross-provider: format moves accuracy up to 76 points; tokenizer +30%

DECISIONS
  one deployment down   failover
  provider down         retry with budget, then shed or fail
  rate limited          read the 429, back off, shed
  context overflow      compact, then send once
  budget exceeded       shed load
  want a cheaper model  a ROUTED change with a quality gate, not a fallback

THE COMMANDS
  run_recorder.py --demo --role cache_demo    the freeze, offline
  run_recorder.py --self-test                 19 checks, offline
  run_recorder.py --model X --ledger runs.jsonl   real calls
  slo_report.py --demo                        four indicators, offline
  slo_report.py --demo --window-minutes 300   two windows
  slo_report.py --ledger runs.jsonl           your own traffic

## Post

Two drafts, ready to edit and post. Each is one claim, and the second line says what makes it yours to tell.

Post 1: four indicators

Anthropic's postmortem: three infra bugs degraded Claude for weeks, peaking at 16% of Sonnet 4 requests. Every availability dashboard stayed green. An LLM feature can be up, fast and wrong. So I measure it on four ratios, not two: availability, TTFT, smoothness, completeness. Only a ratio carries an error budget.

What makes it his: the demo ledger where the freeze indicator fails at 89.93% while TTFT passes at 99.60%. It is reproducible offline with slo_report.py --demo.

Post 2: the fallback you have not shipped

Amazon, 2001: every server cache failed at once. The database fallback turned a missing shipping-speeds widget into a full-site outage. A fallback that runs only during incidents is untested code that starts on your worst day. An LLM fallback adds a worse failure: it can return 200 OK and be wrong. Failover changes the instance; fallback changes the mechanism.

What makes it his: his own decision table. Most "add a fallback" proposals turn out to be failover, retries or shedding instead.

## Sources

Every claim, number and name in this phase traces to one of these. Where the verification of the study note differs from the phase, the newer date is kept.

- Alerting on SLOs, Google SRE Workbook — https://sre.google/workbook/alerting-on-slos/ — the burn tiers this phase uses (page at burn 14.4 over 1 hour confirmed over 5 minutes, page at 6 over 6 hours, ticket at 1 over 3 days), the one-twelfth short-window rule and the low-traffic caveat. Re-verified 2026-10-10.

- A postmortem of three recent issues, Anthropic, September 2025 — https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues — three bugs degraded Claude for weeks while every availability dashboard stayed green and the evaluation suite missed it. Re-verified 2026-10-10.

- Avoiding fallback in distributed systems, Amazon Builders' Library (archived) — https://web.archive.org/web/20250119023338/https://aws.amazon.com/builders-library/avoiding-fallback-in-distributed-systems/ — the four-strategy definitions, the Amazon 2001 quote and the continuous-exercise requirement. The archive link resolves; re-verified 2026-10-10.

- OpenTelemetry GenAI semantic conventions, metrics.yaml — https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/model/gen-ai/metrics.yaml — the current client metric names and gen_ai.server.time_to_first_token. The repo has no release tags, so this is a main-branch read of 2026-10-10, and the phase's two client names were corrected from it.

- OpenTelemetry GenAI semantic conventions, registry.yaml — https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/model/gen-ai/registry.yaml — verified gen_ai.response.time_to_first_chunk and the gen_ai.response.status enum, including incomplete defined as the token-limit or content-filter case. Read 2026-10-10, development stability.

- Defeating Nondeterminism in LLM Inference, Thinking Machines Lab, 2025 — https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/ — 1,000 temperature-0 completions of one prompt produced 80 unique outputs, diverging at token 103; the reason exact-text comparison cannot be a quality floor. Re-verified 2026-10-10.

- llm-semantic-cache-lookup, Microsoft Learn — https://learn.microsoft.com/en-us/azure/api-management/azure-openai-semantic-cache-lookup-policy — the "incorrect, outdated, or unsafe" warning and the 0.05 and 0.2 similarity thresholds. Re-verified 2026-10-10.

Two items the note could not re-verify stay labelled as the phase cited them: the "0 of 13" conformance report and the judge agreement figures (85% without ties, about 66% with). Anything else it could not open is absent from this phase rather than asserted.
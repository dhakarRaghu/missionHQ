Phase 4B ended with a server you sized and gated yourself: a measured operating point, a quantization gate on your own task, a speculative draft sized from measured acceptance. None of that helps on the afternoon the other side starts slowing down, whether that is the provider or your own server under a burst. Phase 0 told this story once: p99 latency spiked, the team added short timeouts and two retries, and the incident got worse. The story had no numbers and no fix, so this phase replays that decision in a closed-loop simulation and measures what the client's retry policy did to the recovery, request by request.

Before the numbers, one belief to test. Your client passes timeout=600 to the SDK, and you believe that bounds every call to ten minutes. A stream can return hundreds of healthy chunks, go silent, and leave your code waiting far longer than you think, because the limit you set does not mean what you think it means. This phase shows what that one number actually controls, why a retry loop stops protecting you the moment the answer starts, and why the measured retry harm is worse than the story: an 89.0% success day becomes a 22.7% outage that never recovers, until the client learns to send less instead of more.

This lesson teaches five ideas. They are listed here so you can see where the lesson is going. They will read more clearly once each has been explained below, so come back to this list at the end.

- A single timeout=N sets connect, read, write and pool independently, and the read timeout, which resets per chunk, is already the stall deadline a stream needs. Configure a stream that dies in 20 seconds on silence and never on a long healthy answer.
- An SDK retry loop protects a call only until the response headers arrive, so a stream that dies mid-answer is a partial response the SDK never sees. Decide fail, return-partial-and-say-so, or continue as a product decision, knowing the SDK chose none.
- Phase 0 asked why retries make an outage worse; the measured answer is 89.0% success falling to 22.7%, because backoff shifts the same load in time and SDK jitter can only shrink the sleep by a quarter. Predict the size of retry harm under a burst, and reject add-backoff-and-jitter as a fix on mechanism grounds.
- A 429 is a capacity report with incompatible headers per provider, Anthropic reports overload as non-standard 529, and a spend-cap 429 with no retry-after must never be retried. Classify errors correctly, read reset headers per provider, and stop hammering a spend-capped organisation.
- Phase 1 showed TTFT is queue depth; used as a shedding signal it drives the only overload policy that sends less, and a breaker that opens must clear the bad window or it latches open. Write a shedding policy that recovers in seconds, drive it with TTFT instead of the error rate, and know why a budget and a breaker are needed together.

## What you already know, and what breaks today

Phase 1: you measured TTFT

Phase 1 taught you to measure TTFT, the time from sending a request to the first token coming back. It is the metric you measured when you timed a working system. This phase reuses the same metric as a warning signal, not just a latency report.

Phase 2A: TTFT is queue depth

Phase 2A showed that TTFT is queue depth: the first token waits behind every request ahead of it. So TTFT rises while the server is still answering everything, well before any error appears. That makes it a signal that leads the failure, and this phase turns it into a policy.

Phase 0, Story 2: the debt this phase pays

Phase 0 told one story without numbers. p99 spiked, the team added short timeouts and two retries, and the incident got worse. It never said how much worse, or what the fix was. This phase replays that decision in a simulation and measures it, request by request.

Phase 3: read what the response tells you

Phase 3 taught you to read the usage object, because the provider reports costs you cannot see from your side. This phase applies the same habit to response headers. The error status and the rate-limit headers are a report the server volunteers, if you read them.

This phase needs all four ideas because the failure moves to the other side of the wire. Phases 1 to 4 measured and tuned a system that was working. Now the provider is overloaded, and your client's timeouts and retries decide whether you recover. The simulation runs one scenario through the whole lesson. It is a server with 20 requests per second of capacity and 12 per second normally. Then comes a burst to 30 per second for 8 seconds. Every section returns to it and asks what your client's policy did to the recovery.

## Your client says timeout=600. What did it actually promise?

One number set four deadlines, and none of them is the one a dead stream needs.

The burst in the simulation overloaded the server, and the team's answer was a short timeout. That decision looked safe because of a belief most client code shares. timeout=600 means no call can take more than ten minutes. It does not mean that, and this section shows what it really promised.

An SSE stream, the response format both providers use, delivers the answer as many small chunks over one open connection. A request can fail in three different places along that connection. The socket may never open. The server may accept the request and never send the first chunk. Or the chunks may start and then stop. One total duration cannot catch all three, because a total also fires on a healthy answer that is simply long. A stream needs what you can call the three deadlines: one per failure, each watching a different wait.

- connectthe socket never opened

- first chunkthe server never started the answer

- chunks flowthe stream may die at any gap

The failure deadline one cannot name is the one between the chunks. After the first chunk, the wait that matters is the gap between two chunks, not the time since the request. TTFT, the wait for the first token that Phase 1 measured, covers the second failure. The third failure has its own deadline, and the question is where it lives.

Predict: a stream returns 390 normal chunks and then goes silent. Your client was built with timeout=600. At what second does your code find out?
At second 600.46, if the last chunk arrived at 0.46 seconds. Here is the reason the belief fails. A single timeout=600 does not set one total limit. It sets four separate limits of 600 seconds each: connect, read, write and pool. The read limit is the wait for one chunk, and it resets on every chunk. Each of the 390 chunks restarted the clock, so the silence accumulates the full 600 seconds before anything fires. Your worker sits blocked for ten minutes and reports nothing.

The mechanism, then. When you pass one number, the transport library builds a Timeout object where every field equals that number. Each field is a separate clock with a separate trigger:

deadlinewhat it catcheswhat it must not do

connectthe socket never openednothing, it ends at connection

first-token deadlinerequest accepted, answer never startedfire because the answer is long

stall deadlinethe stream started and then died mid-answerfire during a normal gap between chunks

totalrunaway cost, as a last resortbe your primary control

write and poolsend and connection-pool waits, rarely fire on an LLM call

Now the same stream on a timeline, with the answer your code would give at each point:

-

t=0 request

chunks 0.40–0.46s

-
silence after chunk 390

stall deadline 20s
fires at t=20.46

timeout=600
fires at t=600.46

The example from the lesson. With a 20-second stall deadline your code learns the stream died at t=20.46. With a bare timeout=600 it waits until t=600.46, because every chunk reset the clock. Illustration from the lesson's model, not measured.

The connection is the same and the chunks are the same in both cases. The only difference is which clock is watching the gap. Notice also what the healthy case does. A two-minute answer with steady chunks keeps resetting the stall deadline and is never interrupted. That is exactly the behaviour a total limit cannot give you.

Use it. Exercise E1 in the lab runs python phase05_operations/run_recorder.py --self-test. It asks you to find the check named "a stall is detected" inside record_stream, at lines 141 to 166. Read which Timeout it raises: the error names the deadline that fired, because "it timed out" is not a diagnosis.

A total timeout cannot tell a long answer from a dead stream, so a stream needs a deadline per failure.

timeout=600 is four independent ten-minute clocks, so a dead stream hangs silently for the full ten minutes.

Open your client code and find where the timeout is set. If it is one number, count the deadlines it cannot name.

This section named the stall deadline but never said where to get one. The next section shows it already exists inside the transport, misnamed read, shipped set to ten minutes.

## Why the stall deadline already exists

The deadline table named the stall deadline but placed it nowhere. It already lives inside the transport, under the name read, and both SDKs ship it set to ten minutes.

Both official Python SDKs transport over httpx2, an HTTP client library that keeps the httpx timeout model. The httpx documentation defines the httpx2 read timeout as the time spent waiting for the next chunk of data to arrive. That definition matters because a stream is chunks. The read clock restarts on every chunk, so it times one gap, and a gap that exceeds it is exactly what the stall deadline watches. The stall deadline you thought you had to build already exists.

- Your code asks httpx2 for the response body as a stream of chunks.

- Each time a chunk arrives, httpx2 starts its read clock over from zero.

- Each time the clock reaches the read value before a chunk, httpx2 raises a read timeout.

- A two-minute answer with steady chunks resets the clock hundreds of times, so a healthy long answer never trips it.

The wrong belief survives because of what you type. Passing one number does not set a total budget. It sets connect, read, write and pool to that value independently, and the shipped default does the same at a size nobody chose:

# The shipped default in openai v3.26.1 and anthropic v1.12.1,
# in each SDK's _constants.py:
DEFAULT_TIMEOUT = httpx2.Timeout(timeout=600.0, connect=5.0)

So out of the box your stall deadline is 600 seconds. A stream that dies after 390 chunks hangs silently for the full ten minutes, because every chunk before the silence reset the clock. This is why the timeline in the section above fired at t=600.46, not t=20.46.

One number

client = OpenAI(timeout=600)

Four independent ten-minute clocks. A dead stream reports nothing for ten minutes, and none of the four is a total ceiling.

Named deadlines

client = OpenAI(timeout=httpx2.Timeout(
    None, connect=5.0, read=20.0,
    write=10.0, pool=5.0))

read=20.0 is the stall deadline, per chunk. The total is None, because a long healthy answer is not a failure.

Both SDKs accept the same object, and you can also pass it per request with with_options(timeout=...).

Evidence
The read-timeout definition is quoted from the httpx timeout documentation. DEFAULT_TIMEOUT = httpx2.Timeout(timeout=600.0, connect=5.0) appears in openai/_constants.py at v3.26.1 and anthropic/_constants.py at v1.12.1, verified at those tags.

Predict: both SDKs ship a working stall deadline, so why did the dead stream hang for ten minutes?
Because a deadline only fires at the value it is set to, and the shipped value is 600 seconds. The mechanism is right and the default is wrong: you keep the per-chunk read clock and change only the number, from 600 to a value like 20.

The read timeout is the stall deadline, because it resets on every chunk and times one gap.

Believing one number is a total budget: timeout=600 is four ten-minute clocks, so a dead stream reports nothing for ten minutes.

Find your client's timeout line. If it passes one number, replace it with a named Timeout and set read to 20.

You set read=20.0 because this section said so, but it never said why 20, and neither SDK has a first-token parameter at all. The next section answers where the first-token deadline lives and where both numbers come from.

## The deadline no SDK has, and where its number comes from

The sections above named three deadlines and gave two of them to the transport. The first-token deadline, the longest wait for the server to start answering, has no parameter in either SDK. It lives in your code, and its number comes from a budget this section defines.

Neither openai v3.26.1 nor anthropic v1.12.1 accepts a first-token argument. The pattern that works has three steps.

- Measure TTFT, the wait from sending a request to its first chunk, on your own traffic, as Phase 1 did. Pick the deadline from a high percentile of that measurement, not from instinct.

- Run the first part of the consume loop under an outer timer that cancels the call when no content event arrives in time. This catches the server that accepted the request and stayed silent.

- Consume the rest of the stream without that timer, because a long healthy answer must finish. Only the transport read timeout, the stall deadline that resets per chunk, stays active underneath.

# the pattern: a first-token deadline around only the start of the loop
deadline = monotonic() + first_token_budget   # sized from measured TTFT
async for event in stream:
    if monotonic() > deadline and not first_chunk_seen:
        raise Timeout("first_token")          # server never started
    first_chunk_seen = True
    handle(event)                              # rest of the stream runs free

This answers where the clock lives. It does not answer what number it gets when one user request turns into many model calls. That is the agent-loop case, and constants fail there.

Picture your multi-agent system: one user request runs a loop of twenty model calls. Give each call a 20 second stall budget. Then the sum can reach 400 seconds behind one request that had 30 seconds to answer. Twenty independently legal deadlines compose past any user-facing limit, so the per-call numbers must come from the request itself.

The fix starts with an outer budget, the total time the whole user request may take. It is set once at the top. Each call inside the request then derives its deadlines from what is left of that budget. It does not read a constant from config. The Google SRE book, chapter 22, states the rule this way. All RPCs in a tree share one absolute deadline set at the top. Carrying that deadline down the call tree is deadline propagation. Each call receives the remaining time and takes its own deadlines as a share of it.

Deriving one call's deadline

Outer budget (s)

Time already spent (s)

Calls still to make

Per-call first-token deadline

With a fixed 20 s constant per call

Move the sliders to 30 seconds of budget, 28 spent, and three calls left. The derived deadline is below one second per call. This is because the request is nearly out of time, and a slow call is not worth waiting for. The fixed 20 second constant still offers 60 seconds of waiting to a request that has 2 seconds left.

The same derivation explains a detail in the phase's run_recorder.py, at lines 141 to 166. The loop checks the first-token and stall deadlines only when a chunk arrives. This is because Python code inside an async for runs only when the stream yields. True silence produces no chunk and no check. So live mode keeps the transport read timeout set underneath, at lines 424 to 427. The application deadline catches a late chunk; the transport deadline catches no chunk at all.

Per-call deadlines are a share of the request's remaining budget, not constants.

Twenty legal 20-second budgets behind one user request can wait 400 seconds on a 30-second request.

Take one endpoint in your system and write its outer budget; then check whether any call inside it receives it.

You can now set deadlines that catch a stream that died, within seconds. What you hold after it dies, with 400 tokens already delivered, is a question of retries. The next section shows where the SDK's retry loop ends.

## The retry loop ends at the response headers. What are you holding?

The SDK's retries stop at the headers, so a dead stream mid-answer is a decision only you can make.

The stall deadline tells you a stream died within 20 seconds. It says nothing about the 400 tokens already delivered. Your client was built with max_retries=2, so the incident plan says the call is resilient. This section reads the SDK control flow and asks whether that is true.

Open the request() method in either SDK, openai v3.26.1 or anthropic v1.12.1. The retry loop wraps two calls: send the request, then check the status. A 2xx status breaks the loop. Only after the loop does _process_response build the Stream object you iterate. Your for chunk in stream sits outside the loop and outside any try that can continue back into it.

retry loop (max_retries=2)

_send_request()

raise_for_status()
retry branch: continue → back to send

_process_response()

status 2xx, break

for chunk in stream:
outside any retry

The retry loop ends at the response headers. The Stream is built after it, and your iteration is protected by no loop at all (source read at openai v3.26.1 and anthropic v1.12.1).

Predict: where exactly does the retry loop end for a streaming request, and which exceptions raised while you iterate can reach it?
The loop ends when the response headers arrive with a 2xx status. An exception raised while you read chunks sits downstream of _process_response, so none of it can reach a retry branch. The headers were fine. Only the body stopped. The loop has no branch for that.

The claim is easy to check in the source, because every retry branch is a continue inside one block.

- In openai v3.26.1's request(), the loop wraps _send_request(...) and response.raise_for_status(), and a successful status breaks out of it.

- Anthropic v1.12.1 has the same shape: _attempt_request inside the loop, an is_success check, then _process_response after.

- _process_response constructs the Stream you iterate, so every continue sits before the Stream exists.

- The streaming modules of both SDKs contain no retry logic, so step 3 is a structural fact at the current versions and not a policy choice.

The failure this leaves you with is partial response, a truncated answer that your code usually treats as complete. It is worse than an exception. An exception stops the pipeline, while fluent text cut off at token 400 of 500 flows into whatever consumed the answer, marked as finished.

Evidence
Loop structure read in openai/_base_client.py at tag v3.26.1 and anthropic/_base_client.py at tag v1.12.1 (both released 2026-10-08). Verified this run: every retry branch (continue) sits before _process_response exists in the control flow, and there is no catch around iteration.

The SDK chose none of the three real options, so the choice is a product decision in your code.

- Fail the request. The caller retries the whole operation or reports an error. This is the safe default when a half answer is useless.

- Return the partial answer and say it is partial. A summary that stops mid-list is often worth showing, with a visible mark.

- Continue with a second call. A continuation call asks the model to resume where the stream stopped.

Anthropic documents the continuation procedure, and it differs by model generation. Older models take the partial text back as an assistant message. Newer models want a user message that tells the model to continue. So option 3 needs a per-generation branch in your code.

Option 3 also has a cost that Phase 3's work can remove. A continuation call sends the whole prompt again, so the provider re-pays the full prefill, the forward pass over every input token before generation can start. Phase 3's prompt-cached prefix is what makes the continuation cheap, because the cached tokens skip that pass. Without the cache, one continuation on a large prompt costs close to a full first call.

SDK retries protect the request up to the response headers, and a dead stream comes after them.

Trusting max_retries=2 for streaming turns an exception into fluent truncated text that reads as complete.

Open either SDK's _base_client.py and find the last continue in request(); then find where the Stream is built.

Now you know when the SDK retries and when it stays silent. What it costs when you add retries of your own, under a server that is the bottleneck, is what the next section measures.

## How much does retrying cost when the server is the bottleneck?

Retries under overload now have measured costs, so you can pick a policy by its number.

The section above showed that the SDK's retry loop stops at the response headers. Phase 0 told the rest only as a story: p99 spiked. The team added short timeouts and two retries, and the incident got worse. What the story could not give you is a number. This section measures that decision and pays Phase 0's debt.

Your p99 latency alarm fires, and the on-call colleague adds two retries to every call. The incident gets worse; in the measured simulation, one burst turned an 89% success day into a 22.7% outage. You need to know whether the retry change caused the fall, and by how much. Then you can pick a fix.

### Measuring the decision instead of retelling it

A closed-loop simulation models the server as a queue that slows down under load. So the client's retries come back as server load. That is what happens in production. The conditions come from the script's defaults, and every row below is the mean of five runs:

- The server processes 20 requests per second, its capacity.

- Normal traffic is 12 requests per second, well inside capacity.

- A burst raises traffic to 30 requests per second for 8 seconds.

Predict: capacity is 20 requests per second and the burst offers 30. Every failed or timed-out call is retried twice. Does success rise or fall, and by roughly how much does the sent request count grow?
Success falls hard, and sent requests grow to about 3.1 times the offered traffic. Each original call can spend up to three attempts, and the measured blind-retry policy sent 3.14x the requests. Each attempt still costs a queue slot, so the queue deepens. TTFT rises past the client timeout, and almost every fresh attempt times out too. The measured result: success falls from 89.0% to 22.7%.

Four client policies ran against the same server. The amplification factor is requests sent divided by requests offered. So 1.00x means the client sent only what callers asked for:

policysentamplifiersuccesswastedrecovers

none1,2291.00x89.0%13518.2 s

blind retry3,8553.14x22.7%3,576not within the run

backoff + jitter3,8963.18x22.7%3,617not within the run

health signal1,0600.86x85.6%85.2 s

Three things to notice. Blind retry turned an 89% day into a 22.7% outage, so doing nothing succeeded about four times as often. Backoff with jitter scored the same 22.7% and sent slightly more requests. Because spreading retries over time does not reduce their count, delayed retries land while the queue is still clearing. The health signal sent less traffic than was offered and recovered in 5.2 seconds.

Evidence
Closed-loop simulation from his own phase, run with the script's defaults above, mean of five runs. He ran it twice, two days apart, and the tables matched. The numbers are his measurement with these conditions, not a universal law of retry harm.

### Why the loop closes

Most retry demonstrations model the server as a fixed delay, and in that model retries look free. They are not free, because your retries are the load. The chain runs in one direction and feeds itself:

- more retrieseach failed call comes back as a new request

- deeper queuethe server cannot tell a retry from a new caller

- higher TTFTTTFT, the wait for the first token, measures queue depth

- more client timeoutswaiting calls pass the client deadline, and the loop restarts at the top

Phase 2's section on queue depth showed that TTFT rises with every request ahead of yours. A retry does not complain about a slow server to anyone. It joins the queue that made the server slow.

The loop gets worse when several layers each retry, because the counts multiply. Two published systems give the size of this:

- The Google SRE Book describes three layers that each make four attempts. One user action then creates 4 x 4 x 4 = 64 attempts on the database.

- The Amazon Builders' Library describes five layers with three retries each and reports 243x load, from 3 x 3 x 3 x 3 x 3 = 243.

The exponent is the number of layers, not the retry count per layer. Both sources give the same rule: retry at one point in the stack only. The Amazon source compresses the whole section into three words, "retries are selfish". This is because a retry spends server capacity to protect one caller's request at the cost of every other caller's.

### Why this bug reaches production

Run the same simulation across load levels, from 30% of capacity up to overload. At 30% of capacity, all four policies score 99.7% success and their rows look the same. A unit test, a staging test and a smoke test all run far below capacity, so the retry defect passes each of them. Near capacity the two retry policies score 14.1% and 14.2% against 17.3% for doing nothing, and only in deep overload do they tie with it at 3.1%. This is why experienced teams ship retry storms: the policy is correct at every load they can test, and wrong at the one load they cannot afford.

### It happens to real systems

GitHub's postmortem for its 20 August 2026 outage, which lasted 7 hours and 47 minutes, names the same mechanism. Errors "triggered a client-side retry loop that increased traffic during recovery". The loop had to be stopped before traffic could be restored. Its remediation list names retry limits, retry budgets and variable timeouts. These are the fixes the sections after this one build. Read the postmortem as confirmation of your table, not as the lesson.

Evidence
GitHub, August 2026 outage postmortem (verified this run). The layering arithmetic is from the Google SRE Book chapter on cascading failures. It is also from the Amazon Builders' Library article on timeouts, retries and backoff. Both were verified this run.

Retries are load; under a burst, two of them took 89% success down to 22.7%.

Trusting backoff with jitter cost the same 22.7% here, because waiting does not shrink the request count.

Run python phase05_operations/health_signal.py and compare the blind row against the none row.

Backoff scored the same as blind retry in this table. The next section takes the SDK's backoff and jitter apart line by line. It shows why neither ingredient could have helped.

## Your SDK's defaults, and why backoff plus jitter is not a fix

The table above showed backoff with jitter tying blind retry at 22.7% success. The reason sits inside the two parts of the retry policy your SDK ships.

Both official Python SDKs ship the same retry policy, so one set of numbers covers whichever client you call. It was read from source at release tags openai v3.26.1 and anthropic v1.12.1, and the defaults are these.

- Attempts: three. max_retries, the count of extra attempts after the first failure, defaults to 2.

- Statuses: 408, 409, 429, and anything at or above 500. Each retried status is handled in the same way.

- Backoff: min(0.5 * 2**attempt, 8.0) seconds. The wait doubles per attempt, and at two retries the 8 s cap never binds.

- Jitter: multiply by 1 - 0.25 * random(). The multiplier therefore sits between 0.75 and 1.0.

The jitter line deserves a second read. The multiplier runs from 0.75 to 1.0, so it can only shrink the wait, by at most a quarter. It can never place a client outside its backoff value. The formula that does spread clients is full jitter. It draws the wait at random from the whole interval between zero and the backoff value.

full jitter:  sleep = random_between(0, min(cap, base * 2**attempt))
both SDKs:    sleep = (0.75 .. 1.0) * min(cap, base * 2**attempt)

The anthropic source still comments this line "Apply some jitter, plus-or-minus half a second". The openai source carried the same comment until v3.26.1, where it was corrected to describe a 0 to 25% reduction. The code never added or subtracted anything, and that comment is one reason the spreading belief survives.

SDK, retry 1

0.375 to 0.5 s
SDK, retry 2

0.75 to 1.0 s
full jitter, retry 1

0 to 0.5 s
full jitter, retry 2

0 to 1.0 s

-

-
0

-
0.25

-
0.5

-
0.75

-
1.0 s

Where each retry sleep can land, under the shipped jitter and under full jitter. The SDK band covers only the top quarter of each interval, so clients that failed together wake together. Illustration from the verified formulas above, not measured.

SDK sleep bandfull jitter sleep range

Predict: two retries at these defaults sit inside a 60-second rate-limit window. What share of the window do the sleeps span?
The usual guess is far more, because exponential backoff sounds like long waiting. Take the worst case, where the jitter multiplier lands at 1.0 on both retries.

retry 1:  0.5 * 2^0 = 0.5 s    jittered range 0.375 .. 0.5 s
retry 2:  0.5 * 2^1 = 1.0 s    jittered range 0.75 .. 1.0 s
worst-case total               1.5 s
share of a 60 s window         1.5 / 60 = 2.5%

So at most 2.5%, and less on average, because the multiplier averages 0.875. A rate-limit window refills at a fixed rate. So the window has recovered only 2.5% of its capacity by the time the last retry fires.

That narrow window is part of the story of the 22.7% tie. The backoff buys the server almost no relief, because the same retries still arrive, only later. The jitter buys no spreading either. Ten workers that time out in the same second all sleep inside the same 125 ms band. So they wake as one wave.

Even perfect spreading has a ceiling. The AWS Architecture Blog simulated 100 clients contending for one resource. Full jitter cut the total call count by more than half. The same source reports that total work still grows with the square of the client count. Jitter improves only the constant factor, never that growth law. The two results agree once you name what jitter protects against, which is clients colliding with each other. When 100 clients contend, collisions dominate, so spreading halves the calls. Your burst is not a collision problem. The server's queue is full whenever a retry arrives. Against a full queue the constant does not move.

Evidence
Defaults read from source at two release tags, openai v3.26.1 and anthropic v1.12.1, both released 2026-10-08. The values come from each SDK's constants file (max_retries 2, INITIAL_RETRY_DELAY 0.5 s, MAX_RETRY_DELAY 8.0 s). They also come from base client (the status set and the jitter line 1 - 0.25 * random()). Verified this run. Anthropic's file still carries the comment "Apply some jitter, plus-or-minus half a second". openai's file now comments the same line accurately. The AWS Architecture Blog was verified as text. Its exact call counts sit inside chart images and could not be confirmed. So "more than half" is the only claim used here.

Both parts fail for one reason. They change when a request happens, never how many requests happen. A request moved in time still exists. The fix must shrink the count itself. The mechanism with that shape is a retry budget, a per-process cap on retries per period.

Your SDK retries twice on 408, 409, 429 and 5xx, with jitter that only shrinks.

Expecting jitter to spread a fleet, though the multiplier wakes everyone within 125 ms.

Add your client's worst-case retry sleeps, and compare the total with 60 seconds.

Which statuses deserve a retry at all is the next section's question. A 429 is a capacity report, and each provider writes it differently.

## A 429 is a capacity report. Can you read yours?

A 429 reports capacity in its headers, and one kind of 429 must never be retried.

The retry budget caps retries at 60 per minute per process, but it cannot tell a congestion 429 from a spend-cap 429. Only the response can. This section reads what the two providers send back.

Rate limits work as a token bucket: a store of tokens that refills at a fixed rate all the time. Each request spends tokens on entry, and the server rejects requests when the bucket is empty. Both providers run several buckets side by side. The buckets cover requests per minute, input tokens per minute, and output tokens per minute. A 429 need not be an emptied bucket; a spend cap or a ramp limit can also produce one.

The headers that travel with each response are that bucket's gauge. They say how many tokens remain and when the bucket resets. Phase 3 taught you to read the usage object. Apply the same habit to the headers and you see exhaustion before the first 429 arrives.

The two providers disagree on almost every field of this report. The status code is the only shared part.

OpenAIAnthropic

Bucket dimensionsrequests, tokens, images, audio minutes; per minute and per dayrequests, input tokens, output tokens, all priced separately

Header prefixx-ratelimit-*anthropic-ratelimit-*

Reset formata duration stringa timestamp format

Cache reads count toward input tokensyesno, Haiku 3.5 excepted

Overload status503 server_is_overloaded529 (not a standard status)

The cache row changes what Phase 3's prompt layout bought you. On OpenAI, a cache hit saves money and nothing else, because cached tokens still spend from the bucket. On Anthropic, cached reads skip the input-token bucket on most models. So the same prompt layout buys extra throughput there, at no extra request cost. Claude Haiku 3.5 counts cache reads like any other tokens, so check the model name before you plan capacity on this rule.

The reset-format row is a parse trap. The two formats differ per provider, and the exact strings are unconfirmed in current documentation. A parser written for one provider misreads the other without raising an error. Every client then wakes at the same wrong moment, or sleeps past recovered capacity.

Predict: you get a 429 with no retry-after header, and every retry fails for hours. Which two fields should you have read before retrying once?
The first field is the retry-after header itself: congestion 429s carry one, and its absence here is a signal. The second field is the nested error code in the response body. On Anthropic, a spend-cap 429 wears the same rate_limit_error type as congestion, so only the nested code separates the two. Reading the status alone gave you no way to tell.

Anthropic calls that case the spend-cap 429: a rejection from the monthly usage-tier spend cap, not from any bucket. Access resumes at 00:00 UTC on the first of the next month, or sooner if you raise the tier. Every retry before then fails, so the nested code enforced_spend_limit_reached is the one string your error handling must check. If Phase 3's budget guard fired minutes earlier, this 429 is the explanation.

A third limit exists above the buckets. OpenAI's ramp limit caps how fast your traffic may grow: past 1 million input tokens per minute, add at most 50% more every 15 minutes. Break it and you receive a 429 with the code slow_down, even while both ordinary buckets still hold tokens. A feature launch that moves all its traffic in one step hits this limit first.

Now the classifier. Anthropic reports overload as 529, a status that sits outside the standard range. A hand-written list like (500, 502, 503, 504) misses it, so retries stop during exactly the incident they exist for. Classify by range instead, which both SDKs do internally.

retryable = status >= 500 or status in (408, 409, 429)
# then branch on the nested code:
# enforced_spend_limit_reached -> stop until the month resets
# slow_down -> cap growth at 50% per 15 minutes

How long a retry sleeps also differs per SDK, and one behaviour changed recently. At anthropic v1.12.1, any positive retry-after is honoured, capped near 49.7 days. A retry-after: 300 holds the worker inside the retry loop for five minutes, and enough of those exhausts your worker pool. OpenAI at v3.26.1 takes the opposite line and refuses to retry when the header asks for more than 120 seconds. Older write-ups say the Anthropic SDK ignored long waits above 60 seconds; that was true at 1.5.0 and is not true now.

Evidence
Anthropic's rate-limits page documents the spend-cap 429 as rate_limit_error with nested code enforced_spend_limit_reached, no retry-after, and resumption at 00:00 UTC next month or on tier increase. The same page documents cache reads exempt from ITPM with the Haiku 3.5 exception. OpenAI's rate-limits guide documents 429 slow_down under the 50%-per-15-minute ramp rule past 1M input TPM, and 503 server_is_overloaded for overload. At anthropic v1.12.1, _calculate_retry_timeout reads if retry_after is not None and retry_after > 0: return min(retry_after, 4_294_967.0). OpenAI v3.26.1 caps retry-after at 120 seconds. Claude documentation opened 2026-10-09 states 529 is overloaded_error. The exact reset-header format strings were not visible in today's documentation and stay unconfirmed.

One hazard sits between you and all of this. A gateway such as LiteLLM, OpenRouter or Bedrock can rewrite headers, map a 529 down to a status your classifier reads differently, or run its own retry layer. Yours plus the SDK plus the gateway makes up to three retry layers, and the previous section showed three layers multiplying attempts to 27 per user request. So audit the gateway before trusting any header you parse. E5 in the lab asks the three audit questions against the gateway you actually run.

Read a 429 as a capacity report: bucket, remaining, reset, and a nested code for the cap.

A spend-cap 429 shares the congestion type and sends no retry-after, so retries fail until the month resets.

Find your 429 handler and check whether it reads any header and any nested code, two greps.

Even a perfect classifier only decides when to send again. The next section builds the policy that sends less, driven by the signal Phase 1 showed rises before the errors: TTFT.

## Turning TTFT into a send-less policy, and the breaker that forgets

Sending less is the only overload fix, and one missing line stops that fix recovering.

The fix list above ended with the health signal, and this section turns it into a policy. In the burst table, blind retry sent 3,855 requests to a server with 20 req/s capacity. It ended at 22.7% success. The health row sent 1,060 requests, kept 85.6% success, and recovered in 5.2 seconds, because it sent less. It sent less because it watched the right signal.

The signal is TTFT, the wait from sending a request to its first token. Phase 2 section 2.1 showed that TTFT is the queue depth, so it climbs before the error rate moves. Errors lag because a request fails only after it has already waited in a deep queue. A policy that waits for errors reacts late, and a policy that watches TTFT acts early.

The actuator on that signal is a circuit breaker, a switch inside the client with three states. Closed is normal operation, where every request goes out and each response adds its TTFT to a small rolling window. Open means the rolling p95 crossed the SLO, the latency target you promise, so the client refuses new requests at once. After a cool-down, the breaker sends a few test requests, the half-open probes, and their results decide the next state.

- CLOSEDsend every request and record each TTFT

- OPENTTFT p95 crossed the SLO, so refuse every request

- HALF-OPENafter the cool-down, let a few probes through

Predict: a breaker opens under load, cools down, lets its probes through, then opens again, in a loop, while the server is healthy. Which single line is missing?
The server is healthy and the probes succeed, so the problem is not the probes. The rolling window still holds the TTFT samples recorded while the server was overloaded. The first p95 check after the cool-down reads them and trips again. The missing line clears the window at the moment the breaker opens. Samples that describe a server state which no longer exists are a stale signal. A decision read from a stale signal opens the breaker again every time.

The shipped policy is this loop, from phase05_operations/health_signal.py:131-157, with comments shortened and the logic unchanged.

if now < circuit_open_until:
    failed += 1                 # OPEN: shed, fast and cheap
    continue
if circuit_open_until > 0 and probes < args.probe_count:
    probes += 1                 # HALF-OPEN: let a few through
    sent += 1
    req["attempt"] += 1
    if prov.submit(req, now):
        inflight += 1
    else:
        failed += 1
    continue
if len(recent_ttft) >= 10:
    p95 = sorted(recent_ttft)[int(len(recent_ttft) * 0.95) - 1]
    if p95 > args.ttft_slo:
        circuit_open_until = now + args.circuit_seconds
        recent_ttft.clear()     # discard the stale signal
        probes = 0
        failed += 1
        continue

- An open breaker sheds, because the first branch fails the request without touching the server.

- After the cool-down, the second branch sends up to --probe-count probes, three by default.

- Once the window holds ten fresh samples, the third branch computes the rolling p95 and compares it with --ttft-slo.

- On a breach it opens the breaker for --circuit-seconds, resets the probe counter, and calls recent_ttft.clear(), so the next decision sees only samples taken after the cool-down.

CLOSED
send every request

OPEN
shed every request

HALF-OPEN
send a few probes

-
TTFT p95 > SLO
and clear the sample window

-
cool-down elapsed

probes still bad

-
fresh samples below the SLO

The shipped logic. The clear happens on the arrow into OPEN, so the first check after the cool-down reads only samples from after the overload. Illustration of the code above, not measured.

The mutation run removes that one line and measures the difference on the same burst, mean of five runs. Recovery stretches from 5.2 to 30.1 seconds and success falls from 85.6% to 57.3%. This is because the probes keep judging the recovered server by its overload window. Removing the half-open branch instead barely moves anything, because the clear already forces ten fresh samples before the next decision.

change to the breakerhealth successrecoveryself-test

none, the shipped code85.6%5.2 spasses

recent_ttft.clear() removed57.3%30.1 s2 checks fail

half-open branch removed85.4%5.2 sstill passes

Evidence
These numbers come from his closed-loop simulation (server 20 req/s capacity, normal 12 req/s, burst to 30 req/s for eight seconds, mean of five runs), mutation run stamped 2026-09-17 in his phase and matching the 2026-09-14 run. The study review could not execute the local script, so they stand as his measurements with their conditions. The per-client trip-rate result is from Marc Brooker's 2022 retry post: independent breakers trip at about half the rate the global failure rate predicts.

One second-order fact sizes a fleet of these breakers. Each client trips on its own samples, so independent breakers trip at about half the global failure rate. Some clients keep sending while others shed. That is why the fix list pairs the breaker with the retry budget. The budget caps how much extra traffic retries can add. The breaker caps how long you keep sending to a sick server.

Judge any shedding policy by two numbers, not one. Success alone cannot separate a good policy from a lucky one. This is because a short burst ends on its own and every policy recovers with it. The second number is the amplification factor, requests sent divided by requests offered. The health row scored 85.6% while sending 0.86x of offered traffic and wasting 8 requests, against blind retry's 3,576 wasted.

E4 in the lab reproduces this mutation with one sed command. It also shows why the self-test checks success and recovery together. The stale-signal bug fails both, while the half-open removal fails neither.

Trip on TTFT, and clear the sample window the moment the breaker opens.

Judging the probes from old samples re-opens the breaker forever, though the server recovered.

Find where your client stores failure history, and check what resets it after a cool-down.

You can now set deadlines that kill a dead stream in seconds. You can classify any status the two providers send including 529 and the spend-cap 429. You can write a client that sends less under overload. The recall section reads these five claims back. The next phase reads the records this client writes. It asks what you can promise about a system that is up, fast and wrong at the same time.

## What you can do now, and what comes next

Five claims carry this phase. Read them again; each should now sound like something you would say to a colleague.

- A stream needs three deadlines, and read is already the stall one. A single timeout=600 waits ten minutes for each chunk, so a dead stream looks healthy for 600 seconds. Shown in Your client says timeout=600. What did it actually promise? and the two sections after it.

- The SDK retry loop ends at the response headers. A stream that dies mid-answer is a partial response, and no exception you raise while iterating can reach a retry. Shown in The retry loop ends at the response headers. What are you holding?

- Retries under overload spend the scarce resource, and backoff with jitter is not a fix. In the burst simulation, blind retries turned 89.0% success into 22.7% and never recovered, and backoff with jitter scored the same at 3.18x amplification. Shown in How much does retrying cost when the server is the bottleneck? and Your SDK's defaults, and why backoff plus jitter is not a fix.

- A 429 is a capacity report, and some 429s must never be retried. Overload is 529 on Anthropic and 503 on OpenAI, and a spend-cap 429 carries enforced_spend_limit_reached and no retry-after. Shown in A 429 is a capacity report. Can you read yours?

- Shed on the signal that leads, and clear the measurement window when the breaker opens. TTFT is queue depth, so it moves before the errors; a breaker that keeps the bad window re-convicts a healthy server, dropping recovery from 5.2 seconds to 30.1. Shown in Turning TTFT into a send-less policy, and the breaker that forgets.

You can now configure a streaming client that fails in seconds on a dead stream and never on a long answer. You can classify any error status a provider sends. You can write a client policy that sends less under overload instead of more, and measure it by the amplification factor rather than success rate alone.

This client also writes records on every run: the deadlines that fired, the statuses it saw, the retries it spent. The next phase reads those records and asks a harder question. A system can be up, fast and wrong at the same time, so what can you promise about it, and what must you store so a fallback decision is possible?

## Hands-on lab — part A

-  E1 offline
Proves the three-deadline concept: "it timed out" is not a diagnosis.

python phase05_operations/run_recorder.py --self-test

Expected: 19 checks pass, including "a stall is detected" and "a late first token is detected".

Then open record_stream and find the three deadline checks. The exception says which deadline fired. Also find the check that fires when the first token arrives late, and the line where live mode sets the transport read timeout.

Check it yourself: run_recorder.py:120 takes an iterable of tuples, not an SDK client. What does that design give you?
Because the stream is data, the self-test can build any chunk pattern by hand, including a first token that arrives after 20 seconds of silence. A client-based function could only test whatever a real server happens to do.

-  E2 offline
Test the retry simulation before you believe it, because a simulation you have not tested is only a story.

python phase05_operations/health_signal.py --self-test

Expected: 9 checks pass. Two of them are "backoff is not meaningfully better than blind retry" and "doing nothing beats both retry policies here".

-  E3 offline
Watch retries turn a spike into an outage. This is the measured core of the retry concept.

python phase05_operations/health_signal.py

Expected: no-retry succeeds on 89.0%. Blind retry succeeds on 22.7% and sends 3.14x the requests. The health signal succeeds on 85.6% and sends 0.86x.

Write down the wasted column for each policy. Blind retry wastes 3,576 requests. The health signal wastes 8.

Check it yourself: in health_signal.py, Provider.submit line 69 sets req["ttft"] from the queue depth at admission. Why does this make the simulation a closed loop?
The latency a request sees depends on the load the client created, so retries deepen the queue. That raises the very TTFT that causes more timeouts and more retries. A fixed-delay model cannot feed that back.

-  E4 break-it, offline
Proves the breaker concept by breaking it. A test that does not overload the server cannot see the defect, and a test that does not check recovery cannot see the broken rule.

python phase05_operations/health_signal.py --sweep

Expected: at 30% of capacity, all four policies score 99.7% and look the same. This is why the bug ships.

Now remove the rule that clears the signal, in a copy:

B=phase05_operations/hs_broken.py
sed 's/recent_ttft.clear()/pass/' phase05_operations/health_signal.py > $B
python $B

Expected: the health row drops to 57.3% success, and recovery takes 30.1 s instead of 5.2 s.

python $B --self-test

Expected: 2 FAILED. The checks "the health policy keeps most requests alive" and "the health policy recovers within 10 s of the burst" fail. An earlier version of the self-test passed here, because it never checked recovery.

rm $B

Check it yourself: the breaker calls recent_ttft.clear() at line 154. What fails if you delete it, which two self-test checks catch it, and which E4 numbers does each test?
Without the clear, the window still holds TTFT samples measured during the overload, so the half-open probes re-open the breaker on a healthy server. One check tests the 57.3% versus 85.6% success drop, the other tests 30.1 s versus 5.2 s recovery. The thresholds sit below the damage but above the noise, so a correct breaker passes and a forgetting one fails.

-  E5 offline
Audit your own client. Find the max_retries and timeout your code passes to its LLM client, or the SDK defaults if it passes neither. If a gateway such as LiteLLM or Bedrock sits in the path, answer for the whole stack. That is because the gateway may run its own retry layer.

- How many attempts does one call make in total, across every layer?

- What is the total added delay across those retries?

- Does a single timeout=N in your code set one deadline or four?

The shipped defaults are two retries with at most 1.5 seconds of total backoff, which is much less protection than most people assume.

-  E6 live
Give a stream the wrong timeout, then the right one. Not verified against a live provider; costs about $0.02.

client.stream(..., timeout=5)  # a bare number
client.stream(..., timeout=httpx2.Timeout(None, connect=5.0, read=20.0, write=10.0, pool=5.0))

Expected: the first call can fail on a healthy long answer, because a bare number sets four independent idle timeouts of 5 seconds each. The second call does not fail on a long answer and still catches a dead stream within 20 seconds of silence.

-  E7 break-it, live
Cause a 429 and read what it tells you. Not verified against a live provider; costs about $0.03.

# send requests concurrently until the server rejects one
# print every response header whose name contains ratelimit or retry

Expected: your provider's limit, remaining and reset values. Check the reset format: OpenAI sends a duration such as 6m0s, Anthropic sends an RFC 3339 timestamp (both formats unconfirmed against today's docs). Then check whether your code reads any of these headers today.

On the Anthropic SDK, also mock a 429 that carries retry-after: 300 and watch the response. At anthropic v1.12.1 any positive retry-after is honoured, so the SDK sleeps five minutes inside the retry loop and blocks a worker. The older expectation that it ignores large values will not reproduce.

E1 to E5 run offline. E6 and E7 need an API key and cost under $0.05 together.

## Checkpoint 5A

Answer each in your own words and from the numbers, then open the sketch to compare. Every question is one of the concepts, worked end to end.

- Show the arithmetic. Your SDK uses its defaults: two retries, a backoff of min(0.5 × 2ⁿ, 8) seconds, and a jitter multiplier from 0.75 to 1.0. (a) Compute the minimum and maximum of each of the two sleeps. (b) Compute the total added delay for one failed call. (c) Your provider's rate limit resets on a 60-second window. Can those retries succeed, and why?

Answer sketch
(a) First sleep: 0.5 × 2⁰ = 0.5s, times 0.75 to 1.0, so 0.375 to 0.5s. Second: 0.5 × 2¹ = 1.0s, times the same range, so 0.75 to 1.0s. (b) Between 1.125 and 1.5 seconds total. (c) They cannot help: in 1.5 seconds a token bucket on a 60-second window refills 1.5 / 60 = 2.5% of capacity, so all three attempts land in the same congested window. The retries add load and buy nothing.

- Test a claim. A colleague says: "We added exponential backoff with jitter, so the retry storm is fixed." Give two reasons this is false. One is about what backoff changes and does not change. The other is about the jitter your SDK actually implements.

Answer sketch
First, backoff moves the same number of retries in time but does not reduce them; in the simulation they arrived while the server was still clearing its queue, and backoff-with-jitter scored 22.7%, the same as blind retry. Second, the SDK's multiplier runs 0.75 to 1.0, so it can only shrink the sleep by at most a quarter; correlated clients stay correlated. Full jitter, drawn from zero to the cap, is what spreads a fleet apart.

- This is broken. Your service calls an LLM through a gateway, and the gateway calls the provider. Each layer retries three times. (a) Compute the worst-case number of requests one user action produces at the provider. (b) Name the one change that removes the exponent. (c) The provider returns retry-after: 300. Describe what each official SDK does with that header today, and name the hazard each behaviour creates.

Answer sketch
(a) Read as three attempts per layer: 3 × 3 × 3 = 27 requests. Read as three retries after the first attempt: 4 × 4 × 4 = 64. Either way the count is a product, not a sum. (b) Retry at one layer only, and let the other layers fail through. (c) At openai v3.26.1 the SDK refuses to retry above 120 seconds, so the call fails fast and the worker is freed. At anthropic v1.12.1 any positive retry-after is honoured up to about 49.7 days, so the SDK sleeps the full five minutes inside the retry loop; the retry adds no load, but it holds a worker and can exhaust a connection pool. (The older Anthropic behaviour, ignoring values above 60s, no longer reproduces.)

- Walk through it. A stream returns 400 tokens of an expected 500, then goes silent forever. Your client was built with timeout=600 as a bare number. (a) Trace what happens next, and how long it takes. (b) State what the SDK does about the partial response. (c) Give the configuration that catches this in 20 seconds, and name each deadline in it.

Answer sketch
(a) A bare number sets connect, read, write and pool independently to 600 seconds. The read timeout limits the wait between chunks, so the client waits ten full minutes of silence before an error fires. (b) Nothing: the retry loop ended when the response headers arrived, so the 400 tokens already delivered are a partial response the SDK never retries. Your caller decides whether to fail, to return the partial text marked as partial, or to continue with a fresh call. (c) httpx2.Timeout(None, connect=5.0, read=20.0, write=10.0, pool=5.0): connect limits opening the socket, read limits the silence between chunks and fires here at 20 seconds, write limits sending, pool limits waiting for a free connection. The total is None on purpose, because a long healthy answer is not a failure.

- Design it. Your feature calls one provider and must survive a burst of four times normal traffic. Write the client policy in five points: the signal that says you are in trouble, why that signal and not the error rate, what you do when it trips, how you decide to resume, and the one metric that afterwards shows whether the policy helped.

Answer sketch
The signal is a rolling TTFT percentile, because TTFT is queue depth and rises while the error rate is still at zero; errors move only when the queue is already deep. When the percentile crosses the SLO target, open a circuit breaker and shed the excess requests, which fails fast and adds no load. Resume through a half-open state: after a cool-down let a few probes through and judge from fresh samples, clearing the measurements taken during the overload first; in the simulation, removing that clear dropped success from 85.6% to 57.3%. Afterwards, the deciding metric is requests sent divided by requests offered, the amplification factor, because the success rate alone cannot separate a policy that helped from one that was lucky.

## Cheatsheet — part A

THE THREE DEADLINES (a single timeout=N is the wrong shape for a stream)
  connect      socket never opened
  first token  server accepted and never started   <- no SDK has this; your code
  stall        stream started, then died           <- httpx `read` IS this; resets per chunk
  total        runaway cost, last resort only, on purpose: None
  httpx2.Timeout(None, connect=5.0, read=20.0, write=10.0, pool=5.0)
  SDK default, both SDKs: Timeout(timeout=600, connect=5.0) = a 10-minute PER-CHUNK
  stall budget. A dead stream hangs 600 s. timeout=600 is four independent timers.
  NEITHER SDK RETRIES AFTER THE FIRST BYTE OF A STREAM
  your loop checks a deadline only when a chunk arrives -> keep `read` set underneath
  sizing: accept 0.1% false timeouts -> read your own p99.9
  Anthropic non-streaming guard: 3600s * max_tokens / 128,000, refuses >10-min calls

SDK DEFAULTS (openai v3.26.1, anthropic v1.12.1, identical shape)
  max_retries 2 (3 attempts) | statuses 408, 409, 429, >=500 (a list misses 529)
  backoff  min(0.5 * 2^n, 8.0)   -> sleeps 0.375-0.5s then 0.75-1.0s
  jitter   1 - 0.25 * random()   -> multiplier 0.75..1.0, can only SHRINK
  total added delay 1.125-1.5 s = 2.5% of a 60 s token-bucket window
  full jitter for comparison: random_between(0, min(cap, base*2^n))
  retry-after: OpenAI refuses above 120 s; Anthropic v1.12.1 honours any positive
  value (sleep 300 s inside the loop = one blocked worker)

RETRIES UNDER LOAD (his simulation: 20 req/s capacity, burst to 30 for 8 s, mean of 5)
  policy     amplification  success  recovers
  none          1.00x        89.0%    18.2 s
  blind         3.14x        22.7%    never
  backoff+jitt  3.18x        22.7%    never   <- NOT better than blind
  health        0.86x        85.6%     5.2 s
  AT 30% LOAD ALL FOUR SCORE 99.7%. That is why the bug ships.
  amplification multiplies across layers: 3 layers x 4 attempts = 4^3 = 64 at the db
  5 layers x 3 retries = 243x   |   retry at ONE layer only

WHAT WORKS, in order
  1. retry at a single layer        removes the exponent
  2. a retry budget                 60 retries/min/process, or a token bucket whose
                                    deposit per success (0.1) is the ~10% failure
                                    crossover where retries stop
  3. full jitter                    halves calls; the exponent stays N^2
  4. a health signal that STOPS you sending   <- the only one that helped

RATE LIMITS (the providers agree on almost nothing)
                         OpenAI                 Anthropic
  header prefix          x-ratelimit-           anthropic-ratelimit-
  cache reads in ITPM    count                  exempt (Haiku 3.5 excepted)
  overload status        503 server_is_...      529 overloaded_error (non-standard)
  -> on Anthropic, the Phase 3 prompt layout buys CAPACITY, not only money
  classify retryable = status >= 500 or in (408, 409, 429), never a fixed list
  the 429 you must NOT retry: Anthropic spend cap = rate_limit_error + nested code
  enforced_spend_limit_reached, NO retry-after, resumes 00:00 UTC next month
  OpenAI ramp limit: past 1M input TPM grow at most 50% per 15 min, else 429 slow_down

THE HEALTH SIGNAL
  the signal is TTFT, not the error rate. TTFT is queue depth; errors lag.
  breaker: clear the measurement window when it opens.
    without recent_ttft.clear(): 57.3% success, 30.1 s recovery (was 85.6% / 5.2 s)
  per-client breakers trip at ~half the global failure rate -> budget AND breaker
  gateway hazard: it can rewrite headers, swallow the 529, or add its own retry
  layer and silently restore the exponent
  judge a policy by requests sent / requests offered (amplification), not success

THE COMMANDS
  python phase05_operations/run_recorder.py --self-test     three deadlines, offline, 19 checks
  python phase05_operations/health_signal.py --self-test    harness self-test, 9 checks
  python phase05_operations/health_signal.py                four policies under the burst
  python phase05_operations/health_signal.py --sweep        invisible at light load

## Two things you could post

- We replayed the retry-storm decision in a closed-loop simulation. Blind retries took success from 89.0% to 22.7% and never recovered. Exponential backoff with jitter scored the same, at a slightly higher request count (3.18x offered). The policy that worked sent less, not later: shedding on TTFT held 85.6% and recovered in 5.2 seconds. Yours because these are your simulation's numbers, under your stated conditions. The conditions are 20 req/s of capacity, a burst to 30 req/s for 8s, mean of 5 runs.

- Both Python SDKs ship a ten-minute stall budget disguised as timeout=600. Neither retries after the first byte of a stream. The httpx read timeout resets on every chunk, so a dead stream can hang for ten minutes. Healthy long answers can also hang, and the SDK retry loop ends at the response headers. A truncated stream arrives as fluent, finished-looking text. Yours because you verified both defaults at the current release tags (openai v3.26.1, anthropic v1.12.1) instead of quoting a blog.

## Sources

Every URL below was fetched during this review cycle. Each line says what the source gave this phase and how it was checked. Anything a page could not confirm was left out of the lesson, not guessed at.

### SDK source, read at the current release tags

- openai-python releases — set the current tag, v3.26.1. Verified 2026-10-09.

- anthropic-sdk-python releases — set the current tag, v1.12.1. Verified 2026-10-09.

- httpx2 on PyPI — confirmed httpx2 is the maintained continuation of httpx that both SDKs transport over, at 2.13.1. Verified.

- openai v3.26.1 _constants.py — the shipped default DEFAULT_TIMEOUT = Timeout(600, connect=5.0). Verified.

- anthropic v1.12.1 _constants.py — the same default timeout, and no retry-after cap constant. Verified.

- openai v3.26.1 _base_client.py — the retry loop ends at the response headers, the shrink-only jitter 1 - 0.25 * random(), and the refusal to retry above a 120-second retry-after. Verified.

- anthropic v1.12.1 _base_client.py — the same loop structure, and the correction this phase carries: any positive retry-after is honoured up to about 49.7 days, so retry-after: 300 now sleeps five minutes inside the retry loop. Verified.

### Timeouts and retries, the method

- httpx timeout documentation — the read timeout is the maximum wait for a chunk of data, so it resets on every chunk and is already the stall deadline. Verified.

- Amazon Builders' Library: timeouts, retries, and backoff with jitter (archive) — the p99.9 sizing method at a 0.1% false-timeout rate, the 243x five-layer example, and "retries are selfish". Verified through the archive link; the live page serves no article text to a fetcher.

- AWS Architecture Blog: exponential backoff and jitter, Brooker 2015 — the full-jitter formula, more than half the calls saved at 100 contending clients, and the unchanged N-squared growth. Verified as text only; the exact call counts live in graph images and were not used.

- Google SRE Book, chapter 22: addressing cascading failures — 3 layers of 4 attempts make 64 attempts on the database, the 60-retries-per-minute budget, and deadline propagation from the top of the request tree. Verified.

- Brooker 2022: fixing retries with token buckets and circuit breakers — the budget deposit ratio is the failure rate where retries stop, and independent per-client breakers trip at about half the global failure rate. Verified.

### Rate limits and errors, per provider

- Anthropic errors — overload is non-standard 529, so classify retryable as >= 500, never a list. Verified.

- Anthropic rate limits — the spend-cap 429 carries enforced_spend_limit_reached and no retry-after, access resumes at 00:00 UTC next month or on a tier increase, and cache reads are exempt from ITPM with Haiku 3.5 the documented exception. Verified. The exact reset-header format strings were not visible in this fetch, so the lesson says only that formats differ per provider.

- OpenAI rate limits — the ramp limit returns 429 slow_down past 1M input TPM grown over 50% per 15 minutes, possible while inside both ordinary limits. Verified.

### Confirmation in a real incident

- GitHub: the August 17 outage and the work ahead — a client-side retry loop increased traffic during recovery in a 7-hour-47-minute outage, and the remediation names retry limits and budgets. Verified.

Two items the phase cites could not be confirmed in this review, so they stayed out of the prose. These are the exact reset-header format strings on both providers, and the worked arithmetic of Anthropic's cache-aware ITPM example. The simulation numbers throughout are your own runs under their stated conditions, not from any source above.
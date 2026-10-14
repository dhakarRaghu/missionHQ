Phase 4B ended with a decision: you keep the hosted API, put your meter and budget guard in front of it, and your client is a few lines of SDK code you have never read. This morning the provider slows down. Your streams hang with no error, your team adds short timeouts and retries, and by the time the provider recovers, your success rate is worse than if you had done nothing. Every phase until now measured a system that was working. This one is about the hours when it is not, and the system that decides how bad those hours get is the client you wrote.

The hour leaves four questions. Why does a bare timeout let a dead stream hang for ten minutes while a healthy long answer survives the same setting? Where does a defensible timeout number come from if not from guessing? What exactly is a provider telling you when it answers 429, and should you retry at all? And why do the retries, backoff included, turn a bad hour into an outage? The answer each time is a policy that already lives in your process, in the SDK you never read.

This lesson teaches five ideas. They are listed here so you can see where the lesson is going. They will read more clearly once each has been explained below, so come back to this list at the end.

- A bare timeout=N sets four independent idle deadlines, and the read timeout is a stall detector that resets on every chunk, so it never bounds total time. Predict when a stream will hang and configure deadlines that catch a dead stream without killing a long healthy answer.
- A timeout number is a measured downstream latency percentile chosen by the false-timeout rate you accept, not a guess made to feel safe. Derive a first-token and stall deadline from his own TTFT data and say what false-timeout rate each choice buys.
- A 429 is several contracts wearing one status code, so you must match the bucket, the retry-after header and your own request mix before you know when you are unblocked. Decide whether to retry a 429 at all, read the reset value in either provider's format, and use prompt caching as a capacity lever on Anthropic.
- Phase 0 showed retries can make an outage worse; the new rule is that only a bounded, load-shedding policy recovers, because every unbounded retry policy ties or loses to doing nothing under load. Choose the four controls (one layer, retry budget, full jitter, TTFT breaker) in order, predict which policies recover under a burst, and recognise why the defect is invisible in light-load tests.
- Both SDKs enforce latency and retry policy inside your process before the network, so a wrapper built without reading that policy double-pays and mis-diagnoses. Predict what one SDK call will do on failure without running it: how many attempts, how long the sleeps, which errors are retried, and why stream=True changes a client-side refusal.

## The bad morning, and the debt Phase 0 left

The p99 spike and the retry that made it worse (Phase 0)

Phase 0 told Story 2. A provider's p99 latency spiked. The team added short timeouts and retries, and the incident got worse. That story was a promise: it said the fix arrives in Phase 5. This phase pays that promise, and this time the provider's bad hour is yours.

TTFT, the wait for the first token (Phase 2)

TTFT is the time from sending a request to the first token coming back. Phase 2A showed it measures queue depth, so it rises before any request fails. This phase turns it into two tools. One is the number your first deadline comes from. The other is the signal that tells your client to stop sending.

The token bucket (Phase 3)

Your provider meters you with a token bucket: a capacity that refills over time and drains as you spend. Phase 3 used it for your own budget guard. This phase reads it from the other side, because a 429 is the provider's bucket telling you it is empty.

Prompt caching (Phase 3)

A cached prefix is charged at a fraction of the input price. What Phase 3 did not need is the other effect. On Anthropic, cached tokens mostly do not count against the input-token rate limit. That makes the cache a capacity lever, not only a cost lever.

The course so far measured a working system. Phases 1 to 4 sized contexts, routed requests, guarded the bill and decided where the model runs. This phase is the first one about a degrading system. Everything in it sits on your side of the network, on an upstream you do not control. It answers the three questions the bad morning asks, in the order the morning asks them.

- When is a stream dead?a stream goes silent at token 2, and your one timeout number cannot say when to give up

- What is this 429 saying?the status line is the same for a full bucket and a spend cap, and only one of them ever unblocks on a retry

- Should the client retry at all?your team's retries are why Story 2 ended at 22.7% success instead of 89%, and the standard fix does not change that

The first question is about deadlines, the second about rate limits, the third about retry policy. Along the way you will find that both SDKs already answer parts of all three. They do this inside your own process, before the network. So the last piece of the phase is reading the policy you already run. The phase ends where the morning ends. It ends with a measured table of four retry policies under one burst, and the one policy that recovers.

## Your one timeout is four timeouts, and none is a total

One timeout number buys you four separate idle deadlines, and none of them is a total.

You shipped the hosted client, and the provider is slow this morning. A stream dies at token 2 and your client sits there. When did you want it to notice? The answer depends on which failure happened, so one number cannot express it.

A streaming call fails in four different shapes. The socket can fail to open. The server can accept the request and send no first token. The stream can start and then go silent mid-answer. The request can run away and burn budget. Each shape wants its own deadline, because the right length of patience is different for each. These are the four deadlines: connect, first token, stall and total.

Both official Python SDKs send requests through httpx2, and httpx2.Timeout is the object that carries deadline settings to it. A bare number like timeout=600 sets connect, read, write and pool each to 600 seconds. That is four independent ten-minute waits, not a ten-minute call budget.

Predict: your 90-second streaming answer dies at token 2 at t=0.4s and goes silent. A client built with bare timeout=600 notices at what time, and why does a healthy 10-minute answer survive the same setting?
It notices at about t=600.4s, ten minutes after the last chunk. The read deadline measures silence between chunks and resets each time a chunk arrives. A healthy answer keeps sending chunks, so the deadline keeps resetting and the ten minutes never run out. A dead stream sends nothing, so one worker hangs for the full 600 seconds.

The working detail is how httpx2 measures read. The read timeout waits for the next chunk of data, and every chunk that arrives restarts the wait. Your SSE stream, the server-sent-event format that delivers each token as one chunk, resets it on every token. The stall timeout, the longest silence you accept between two chunks, is the read timeout you already have. You do not build one.

Dead stream: bare number versus named stall

Step 2: both clients wait out the same silence, so the bare number waits thirty times longer.

Step 3: the healthy answer survives read=20, because a stall deadline measures gaps, not length.

Illustration from the lesson's mechanism, not measured.

So the fix is to name each deadline and stop passing one number.

# WRONG: four independent ten-minute idle waits, not one budget.
client = OpenAI(timeout=600)

# RIGHT: read is the gap between chunks, not the total.
import httpx2
client = OpenAI(timeout=httpx2.Timeout(
    None,          # no total limit; a long answer is not a failure
    connect=5.0,
    read=20.0,     # STALL: the longest acceptable silence mid-stream
    write=10.0,
    pool=5.0,
))

The wrong-belief cost has both directions. Set the number high and a dead stream holds a worker for 600 seconds while your meter from Phase 3 keeps counting. Set it low as a total-style cap and it cuts healthy long answers in half. Your own run_recorder.py --live --stall-test run confirmed the reset behaviour on two mock endpoints, matching the docs' "inactivity" wording.

Evidence
Both src/openai/_constants.py at v3.25.0 and src/anthropic/_constants.py at v1.12.0 ship DEFAULT_TIMEOUT = httpx2.Timeout(timeout=10 * 60, connect=5.0). The httpx2 docs describe the default as a wait for "5 seconds of network inactivity", and list four timeout types. The per-chunk reset itself is inferred from his mock-endpoint measurement plus the docs' wording; the httpx2 transport source was not read.

The read timeout is a stall detector that resets on every chunk.

A bare timeout=600 sets four ten-minute idle waits, so a dead stream hangs for up to ten minutes.

Run python phase05_operations/run_recorder.py --self-test and find the check named "a stall is detected".

Three of the four deadlines exist in the transport layer, but the first-token deadline has no flag anywhere, and that gap is what the next section fills.

## The deadline no SDK gives you, and the retry no SDK does

Two gaps in the SDK stay invisible until a slow day. They are the missing first-token flag, and a retry loop that ends too early.

The section above named four deadlines, and three of them exist in the transport. Connect, stall and total are all flags on httpx2.Timeout. This section covers the fourth, which exists nowhere in either SDK. Then it covers a second gap that shows up only when a stream dies mid-answer.

### The first-token deadline is your code, not a flag

The worst failure on a bad-weather day is the one where the socket opened, the server accepted the request, and no chunk comes back for three minutes. Your TTFT, the time from sending the request to the first token arriving, is normally under a second, so a wait of three minutes is almost certainly a dead call. The stall timeout cannot help here, because it counts gaps after the first chunk. No chunk has arrived, so the stall clock has not started.

What you want is a first-token deadline, a limit on the wait between sending and the first content event. Neither the OpenAI nor the Anthropic Python SDK exposes one. There is no parameter and no event hook that fires at the right place.

- Open the stream and start a timer sized for your usual TTFT.

- Consume events inside a wrapper that cancels the call when the timer runs out.

- Lift the wrapper as soon as one content event arrives, then read the rest of the stream with only the stall timeout active.

When the timer fires early, the stream is still open on the server, so you must issue your own cancel. You cannot just return from the loop. The phase's record_stream does exactly this in its consume loop. It checks a first-token deadline before the first chunk and a stall deadline on every chunk. Then it raises a Timeout that names which one fired.

# the shape, not the library
async with deadline(20.0):          # first-token deadline
    async for event in stream:
        if event.type == "content":
            break                   # lift it here
    async for event in stream:      # now stall timeout only
        consume(event)

This pattern is engineering reasoning from the phase. No provider document describes it, so its number comes from your own measurements, which the next section covers.

### The retry that never happens

Predict: a stream dies at token 400 of 500. Both SDKs default to 2 retries. How many retries fire for this failure?
Zero. The SDK retry loop is built into the request method, and that method returns as soon as the response headers arrive. Token 400 comes long after the headers, so the retry loop has already left the room.

This is the second gap. Both SDKs retry a connection error and some status codes. But the retry logic ends the moment the server starts answering. Everything after the first byte of the body is your problem and yours alone.

A stream that stops at token 400 of 500 leaves you holding a partial response. It is an answer that is mostly written and provably incomplete. You have three things you can do with it:

- Fail the request, which wastes the 400 tokens you already paid for.

- Return the partial and label it, so the caller knows the answer stopped at 400 of 500 tokens. Returning it without a label is the version of this bug you get blamed for.

- Continue with a second call, sending the model what it wrote so far. Anthropic documents this procedure, and it differs by model generation: older models take the partial text back as an assistant message, newer ones expect a user message that asks the model to continue.

All three choices cost something, and the SDK offers all three the same amount of help: none. Which one you pick is a product decision you make before the incident. At token 400 of a live request there is no time to convene about it.

The SDK finishes its job when headers arrive; the first-token watch and mid-stream retry are yours.

You set max_retries=2 and trust it protects a stream, so a stream dead at token 400 fires zero retries.

Open run_recorder.py at the consume loop and find the two deadline checks it runs per chunk.

Every deadline in this section needs a number next to it. Picking one by feel is the trap the next section answers: where does the number come from?

## Where the number comes from: your own p99.9

Generous is not safe: a timeout number is a measurement, and here is where you measure it.

The sections above named the deadlines and then handed you blanks to fill in. The examples so far picked numbers like 10 seconds and 20 seconds without saying why. This section is where the reason comes from. The answer is a measurement you already own, not a judgment call you make once and forget.

Back in the bad morning, someone wrote timeout=600 because it felt safe. The problem runs in both directions. A deadline set too tight cancels healthy calls that are merely slow. So you pay for tokens and throw the answer away. A deadline set too loose holds a worker on a dead stream, as the section above showed. "Safe" picked the second failure and called it the first one.

The picture first. A deadline is a claim about your traffic. Any call slower than this point is not slow, but it is a different failure. To place that point you need three things. You need the measured latency of the call you are bounding. You need a decision about how often you are willing to be wrong. And you need the percentile where those two meet. The false-timeout rate is the share of calls you are willing to cancel even though they would have succeeded. Choosing 0.1% means you accept killing one healthy call in a thousand.

-

-
  p50 · 0.3 s

-
  p90 · 4 s

-
  p99 · 21 s

-
  deadline at p99.9 · 41 s
  past this, the call is declared dead
  first-token latency, your measured distribution

A first-token latency distribution with an example tail. The vertical line is the deadline: everything left of it is allowed to be slow, everything right of it is treated as failed. Shape is an illustration, not measured.

Predict: your first-token latencies have p50 of 0.3s, p90 of 4s and p99 of 21s. You accept 0.1% false timeouts. Which number do you set, and where do you get it?
The tempting answer is 21s, because p99 is the largest number on the list. But p99 cancels one healthy call in a hundred, and you decided to accept one in a thousand. You need p99.9. That is a larger tail value than 21s and must be computed from your recorded TTFT samples, not guessed. The data already exists. Phase 1 measured TTFT, the time from sending the request to the first token coming back. And run_recorder.py now writes it per request. Compute the percentile from those records and set the deadline to it.

Amazon's Builders' Library describes this as three steps, and each step is a decision rather than a lookup.

- Choose the false-timeout rate you accept. This is a product decision. An interactive answer that already billed tokens is expensive to kill, so you go lower.

- Measure the latency of the downstream call as it exceeds your current timeouts. Amazon adds debug logging for calls that come close to the deadline, so the tail is visible before you commit to a number.

- Read the percentile that matches your rate and use it as the deadline. Accepting 0.1% means the p99.9 latency of the downstream call. The operative word is measured, because Amazon's own warning is that a percentile right for one service is rarely right for another.

The same source names two conditions where the method fails, and both describe your situation. The first is clients with substantial network latency, for example across the internet. That is exactly where your calls to a hosted provider travel. The second is a service with tight latency bounds. There p99.9 sits close to p50, and the variance of short requests dominates. Amazon's advice for that case is to use p50 or p50.9. Then test how the system behaves under false-timeout pressure you impose on purpose. Your TTFT distribution does not have tight bounds, but the internet path is real. So treat the computed p99.9 as a starting point. Then watch the false-timeout count in your run record.

This connects directly to the client you already run. The section above left first_token and stall as names with example numbers. After this section the numbers are derived. First-token latencies from your run record give the first-token deadline. The gaps between chunks on healthy streams give the stall deadline. The section before noted you cannot size it from heartbeats, because no provider documents how often they arrive.

Evidence
Amazon Builders' Library, "Timeouts, retries, and backoff with jitter". A timeout accepting 0.1% false timeouts uses the p99.9 latency of the downstream call, measured rather than assumed. The same page names the two failure conditions (verified). Phase 1's TTFT measurement and run_recorder.py's per-request record are his own pipeline from earlier phases.

Use it. Exercise 3 in the lab hands you a first-token latency list. Its p50 is 0.3s, p90 is 4s and p99 is 21s. It asks you to rank the samples and pick the deadline at 0.1%. That calculation is Amazon's step 3 run on your own data. The question it answers is whether 21s is your deadline or your p99, and those are not the same number.

A deadline is a measured latency percentile plus the false-timeout rate you chose to accept.

"600 seconds to be safe" fails twice. It kills slow healthy calls on a bad day and never fires on a dead one.

Pull last week's TTFT values from your run record and compute p50, p99 and p99.9 side by side.

You can now pick your own deadline numbers from your own data. But the SDK underneath your code already runs a latency and retry policy before the network. The next section reads it, so your wrapper does not double it.

## The SDK's own policy, running before the network

The SDK already retries and refuses calls inside your process, so your wrapper must know its policy first.

You now pick your four deadlines from your own percentiles, and the stall timeout catches a dead stream. But none of that code runs first. Between your wrapper and the network sits the SDK. It already enforces a latency and retry policy of its own. Back in the bad hour, the team set max_retries=4 in the wrapper and the retries still seemed to multiply. This section reads the source to explain why.

The picture in three sentences. The SDK is not a thin HTTP wrapper. It computes a latency prediction before some calls. It loops on failures with its own backoff, and decides from response headers whether to retry. Your code only runs on top of all of that. So one call you write can become many requests you did not write.

your wrapper: retries, the four deadlines you set
adds up to 4 attempts per call

SDK retry loop: 2 retries, backoff min(0.5·2ⁿ, 8.0), partial jitter
retries 408, 409, 429 and 5xx, reads retry-after

SDK non-streaming guard: refuses long calls before the network
expected_time = 3600 · max_tokens / 128000, limit 600 s

httpx2: connect, read, write, pool deadlines
read resets per chunk, so it is the stall timeout

network
Four layers add policy before your request reaches the network. Each layer is code you can read.

Predict: which line throws on max_tokens=63_000, and why does stream=True fix it?
client.messages.create(max_tokens=63_000, stream=False) raises a ValueError before any request leaves the process. The SDK computes expected_time = 3600 · 63000 / 128000, about 1,772 seconds. That is over the 600-second limit, so the guard refuses the call. With stream=True the guard is skipped. A streaming call reports its liveness chunk by chunk, so the stall timeout can catch a dead one. The same model and the same account then run to completion.

The mechanism has three parts, and you can verify each in the SDK source.

- The non-streaming guard. Anthropic's SDK runs a non-streaming guard, a client-side check that refuses a non-streaming call whose predicted duration exceeds ten minutes. The prediction is expected_time = 3600 · max_tokens / 128_000, which assumes about 35.6 output tokens per second. The formula divides by 128,000 because that is how many tokens the model would produce in an hour at that rate. The check reads max_tokens, not your prompt, so the same call with stream=True passes.

- The shared retry defaults. Both SDKs default to max_retries=2, so three attempts per call. The sleep before attempt n is min(0.5 · 2ⁿ, 8.0) seconds multiplied by 1 − 0.25 · random(). That multiplier sits between 0.75 and 1.0, so it only shortens the sleep. Compare full jitter, which draws the sleep uniformly from zero up to the whole backoff value and so spreads many failed clients across a wide range. The SDK's narrow range keeps those clients bunched close together.

- The retry-after divergence. When a 429 carries retry-after: 300, the two SDKs do opposite things. OpenAI's SDK refuses to retry above 120 seconds and raises at once. Anthropic's SDK honours the header and parks your worker for the full 300 seconds before the next attempt. One gives you a fast failure you must handle, the other gives you a worker that looks hung for five minutes.

Now count the attempts across layers. Your wrapper allows 4 attempts per call. The SDK allows 3 attempts per call underneath it. One logical request can then produce 4 × 3 = 12 HTTP requests. During a provider bad hour, most of them land while the server is weakest. During the team's incident, the wrapper's retry count was not the real retry count. The on-call graph of outgoing requests made that visible.

# the arithmetic behind "12 requests from one call"
wrapper_attempts = 1 + 3   # your retry loop: 3 retries
sdk_attempts     = 1 + 2   # SDK default max_retries=2
total            = 4 * 3   # 12 requests possible per logical call

Evidence
Verified from anthropic/_base_client.py v1.12.0 and openai/_base_client.py v3.25.0. The guard reads expected_time = maximum_time * max_tokens / 128_000 with maximum_time = 3600 and a 600-second refusal limit. Both SDKs share DEFAULT_MAX_RETRIES = 2, INITIAL_RETRY_DELAY = 0.5, MAX_RETRY_DELAY = 8.0 and jitter 1 - 0.25 * random(). OpenAI raises when retry-after exceeds 120 seconds; Anthropic honours retry-after up to a cap of 4,294,967 seconds.

Use it. Lab exercise E5 is the offline client audit. It hands you a client and asks three questions. One is how many attempts one logical call can produce. Another is how much sleep those layers add together, and whether the call carries one deadline or four. You can now answer all three from the source you just read. The answers are fifteen attempts, at most 1.5 seconds of SDK backoff for the default two retries, and four deadlines. None of them bounds total time. The exercise also asks whether the SDK's policy or the wrapper's should be removed. The answer depends on the retry-after divergence above. If your traffic can draw a 300-second retry-after, max_retries=0 plus your own policy is a valid choice. The SDK's response to that header is either an unhandled raise or a five-minute parked worker.

One SDK call is already 3 attempts with its own backoff, before your wrapper adds anything.

"The SDK is a thin wrapper" costs you 12 attempts per call and a worker parked 300 seconds on retry-after.

Find max_retries in your client, then read _calculate_nonstreaming_timeout in the installed SDK.

This section read what the SDK will do with a 429, but not what the 429 itself is telling you. The next section answers that. A 429 is a capacity report with several different meanings. Whether you should retry at all depends on which one you got.

## A 429 is a capacity report, not an error to retry through

A 429 tells you which contract you broke, but only if you read the response.

The section above read the SDK's retry loop, so you now know how it retries. It cannot decide whether a retry makes sense, because that answer lives in the 429 response itself. This section reads that response.

Back in the bad hour. Your retry policy waits on every 429 because the status code is all it checks. Meanwhile the provider has already told you two different things in two different bodies. One says wait 30 seconds. One says no retry will ever work. Your client treats them the same.

A 429 is not one signal. The providers run several independent rate limiters, and each limiter is a token bucket, a rate limiter that refills a fixed amount per unit of time. A 429 alone does not tell you which bucket fired, or that a bucket fired at all. Three facts from the response tell you which one, when it refills, and whether retrying helps at all.

- Did retry-after arrive?no means a spend cap on Anthropic, so stop retrying and alert

- Which header family hit zero remaining?requests, input tokens and output tokens are separate buckets with separate resets

- What did your request count against?cache reads count on OpenAI and are free on most Anthropic models

Predict: two 429s with the same error type
You send a 1.4M-token cached system prompt with 90 concurrent requests and get a 429 with retry-after: 30. A second 429 arrives with the same error type and no retry-after at all. What caused each, and what should the client do differently?

The first is an ordinary rate limit. A bucket emptied, and retry-after: 30 says it refills in 30 seconds, so the client should sleep 30 seconds and retry. The second is a spend-cap 429, the rejection Anthropic sends when your usage tier's monthly spend cap is reached. It carries the same rate_limit_error type but no retry-after, and Anthropic states that every retry fails until access resumes. That includes the SDK's automatic retries from the section above. The client must surface it as a billing event, not a congestion event, which is exactly the case where your Phase 3 budget guard fires at the same time.

### Match one: which bucket fired

Anthropic meters three buckets separately: requests, input tokens, and output tokens. Each family sends its own remaining and reset headers. OpenAI meters requests and tokens, per minute and per day. Only the header family shows which bucket emptied, so read it before you read the status.

The bucket that fired also tells you the cheapest way back under the limit. The wrong fix wastes a minute.

- An empty requests bucket is throttled by fewer concurrent requests, and the reset is usually seconds.

- An empty input-token bucket is throttled by shorter prompts or prompt caching, the prefix reuse from Phase 3.

- An empty output-token bucket is throttled by shorter answers, because Anthropic counts output tokens as they are produced.

### Match two: whether retry-after exists at all

The spend-cap case from the predict box is the extreme version of a rule that always holds. The presence of retry-after is itself information. An ordinary limit sends it, because the bucket refills on a clock. A spend cap does not, because a human must act. Your client should branch on the header first and on the status code second.

Anthropic makes the spend cap machine-readable through a nested code, enforced_spend_limit_reached in error.details.error_code. A limit you set yourself is a different shape again: it returns HTTP 400, not 429. Check the code before you page anyone.

### Match three: what your request mix bound against

The two providers count the same request differently. On OpenAI, cached tokens count toward the token limit, so prompt caching saves money only. On Anthropic, cache reads are free for most models, so prompt caching buys capacity as well as money. The docs' worked example takes a limit of 2,000,000 input tokens per minute and an 80% hit rate. That mix processes an effective 10,000,000 input tokens per minute.

2,000,000 fresh tokens / (1 − 0.80 cache hit rate) = 10,000,000 effective
one exception in the docs: Claude Haiku 3.5 counts cache reads toward the limit

This makes the Phase 3 prompt-layout work a capacity lever on Anthropic. Moving shared context into the cached prefix raises your throughput ceiling without a tier change.

### Two traps that survive all three matches

The reset values disagree in format. OpenAI sends a duration string like 6m0s. Anthropic sends an RFC 3339 timestamp. Code that parses one format misparses the other without an error. A wrong reset time either retries every client at once or waits long after capacity returned.

The overload status also disagrees. OpenAI returns 503 with server_is_overloaded. Anthropic returns 529, which is not a standard HTTP status. A handler that enumerates the 5xx codes it knows misses 529, so branch on status >= 500 instead.

Finally, OpenAI runs a ramp limit, a cap on how fast your traffic may grow, not on how much you may send. Past roughly 1 million input tokens per minute, growth is limited to 50% every 15 minutes. Breaking it returns a 429 with the code slow_down, and the docs say it can fire while you are inside both your request and token limits. Waiting 15 seconds does not lift it, because the limiter watches your acceleration. The only fix is a slower ramp, which matters for any feature launch that moves traffic in one step.

Evidence
Anthropic's rate-limit docs state that a tier spend-cap 429 carries error_code: enforced_spend_limit_reached and "the response has no retry-after header. Retrying, including the SDK's automatic retries, fails until access resumes". The same page carries the 2M to 10M cache-read example and the request, input-token and output-token header families. Read in the raw docs. OpenAI's rate-limit page carries slow_down, the 50%-per-15-minutes ramp rule and 503 server_is_overloaded. A user-set spend limit returning 400 is from the same Anthropic docs section. All verified.

Use it. Lab exercise E7 prints your provider's rate-limit headers and checks the reset format against the documented OpenAI and Anthropic formats. The question it answers is whether your handler reads any header at all, and whether it would catch a 529.

Match the bucket, the retry-after and your request mix before you let anything retry a 429.

"A 429 means wait for retry-after" retries a spend cap forever and reports it as an outage.

Log one real 429 today and check which header family reported a remaining of zero.

You can now decide whether one request should retry. The next section measures what happens when a whole team of clients retries at once, in the table behind Backoff did not fix Story 2.

## Backoff did not fix Story 2: the measured table

Your team's standard fix, backoff with jitter, scored 22.7% where doing nothing scored 89.0%.

Phase 0's Story 2 left a rule without a mechanism. Retries turned a degrading provider into an outage. Phase 0 could not yet say which policy would have saved it. The section above showed you when one request should retry. This section measures what happens when every client's requests retry at once. Then you can see which client-wide policies survive a burst.

The setup is the bad hour from your running case. One server handles 20 requests per second. Normal traffic is 12 per second, and a burst raises it to 30 per second for eight seconds. The same burst runs four times, once per client policy, and each number below is the mean of five runs. Retry amplification is the ratio of requests a policy sends to requests the users asked for. 1.0x means the client added nothing, 3.18x means it more than tripled the load on an already overloaded server.

22.7%success with backoff, vs 89.0% doing nothing

3.18xrequests sent by backoff with jitter

5.2 srecovery time of the one policy that shed load

policysentamplifiersuccesswastedrecovers

none1,2291.00x89.0%13518.2 s

blind retry3,8553.14x22.7%3,576never

backoff + jitter3,8963.18x22.7%3,617never

health signal1,0600.86x85.6%85.2 s

Predict: your team adds exponential backoff with jitter after Story 2, and the next burst still scores 22.7% against 89.0% for doing nothing. Why did the standard fix fail, and what property does the policy that recovered in 5.2 seconds have?
Backoff changes when retries arrive, not how many arrive. So the amplifier stays at 3.18x, and the extra load still lands while the server is clearing its queue. The health-signal policy is the only row that sends less than the users asked for, 0.86x. It drops requests at the client instead of adding attempts. That is the property: under overload, only a policy that reduces total load can recover.

Three rows deserve a slow read, because two of them break the belief most engineers carry into this table.

- Blind retry converted a bad hour into an outage. Doing nothing succeeded 89.0% of the time over the burst. Retrying each failure sent 3,855 requests into the same eight seconds, and the queue swallowed nearly all of them.

- Backoff with jitter tied blind retry exactly. Waiting longer between attempts sounds safer, but the server recovers by draining its queue, and delayed retries land in that same queue. The row shows it: 3,896 requests sent, 22.7% success, recovery never.

- The health signal wasted 8 requests where blind retry wasted 3,576. It watches TTFT, the time from sending a request to the first token coming back, and stops sending when that number crosses the target, so the server gets silence instead of more work.

The mechanism under all four rows is one loop. Your retries are not separate from the load, they are the load. A retry enters the server exactly like a fresh request. Each timeout produces one more unit of work for a server. That server is already failing to finish the work it has.

- more retriesevery failed attempt re-enters as fresh load

- deeper queuearrivals stay above the 20-per-second service rate

- higher TTFTeach request waits behind the growing queue

- more timeoutseach timeout comes back as another retry

Now the uncomfortable part, the reason this defect lives in experienced teams' code. Run the same four policies at 30% of capacity:

All four rows are identical, because at low load every retry succeeds and the amplifier costs nothing visible. Every test that does not overload the server passes, so the defective policy ships. The defect only appears on the one day the provider degrades, which is the one day you needed the policy.

Two published postmortems show the same mechanism at production scale. In each, a client-side loop made the recovery longer:

- GitHub's August 2026 outage report says errors "triggered a client-side retry loop that increased traffic during recovery" in Copilot services, and its remediation list is retry limits, retry budgets and variable timeouts.

- Cloudflare's September 2025 dashboard outage started when a React effect issued the same API call many times per render, and on recovery every dashboard re-authenticated at once, a second burst the team had to absorb.

Evidence
The four-row table and the sweep come from his own offline simulation, health_signal.py. Burst of 30 requests per second against a 20-per-second server for 8 seconds. Mean of five runs, run on 2026-09-17. This is the Story 2 artifact from Phase 0, quoted from his phase and not re-run here. The GitHub wording is from "The August 17 outage, and the work ahead" on github.blog, verified. The Cloudflare mechanism is from the September 12 dashboard and API outage post on blog.cloudflare.com, verified.

Use it. Lab exercise E2 runs the simulation's self-test before you trust it. E4 removes the health signal's signal-clearing rule to show what breaks. The question the table answers for you beforehand: which column would your current client's policy land in today?

Under overload only a policy that sends less recovers; backoff delays retries without reducing them.

"Backoff with jitter is the standard fix" ties blind retry at 22.7% and looks perfect in every light-load test.

Run python phase05_operations/health_signal.py --sweep and compare the first and third tables.

This table says which policy wins but not how to build it. The next section builds that policy from four named controls. It asks which layer, which budget and which signal yours should use.

## The policy that sends less: one layer, a budget, and a TTFT breaker

One policy in the table recovered, so this section builds it from four controls you can name.

The table in the last section gave one verdict. Under a 30-per-second burst against a 20-per-second server, only the policy that sent less recovered, in 5.2 seconds. Blind retry and backoff with jitter both scored 22.7% and never recovered. This section builds that winning policy. It is four controls, added in order of cost, and each one answers a weakness of the control before it.

- one layerretry at one point in the stack, removing the exponent

- retry budgetlimit retries as a share of traffic, not per request

- full jitterdraw the sleep from the whole interval, not the top quarter

- health signalstop sending when TTFT crosses the SLO, before errors start

### 1. Retry at one layer

This control costs nothing, because it is a deletion. The failure it removes is multiplication across layers. Your wrapper retries 3 times on top of the SDK's 2 retries. One user request can become 4 x 3 = 12 attempts. The published numbers show where this ends. The Google SRE Book describes three layers of 4 attempts each producing 4³ = 64 requests per user action. The Amazon Builders' Library counts five layers at three tries each as 3⁵ = 243x. Both sources give the same rule, and Amazon states the reason in three words: retries are selfish. Each layer protects itself by moving its failure onto the layer below, so only one layer is allowed to.

In your client that means one decision: the SDK keeps `max_retries=0` or your wrapper does no retrying, never both.

### 2. A retry budget

One layer caps the multiplication per request. But a failing server fails every request, so even 3 attempts each triples the load for the whole outage. A retry budget, a limit on retries as a share of all traffic, caps the total. The Google SRE Book's version allows 60 retries per minute per process and fails the request beyond that. Brooker's version is a token bucket: each success deposits a fraction of a token, and each retry spends one token.

The deposit ratio is the design decision, because it is the failure rate where retries stop. With 0.1 tokens per success, each retry needs ten successes to pay for it. So above a 10% failure rate, the bucket drains and retries stop on their own. That is the property a per-request limit never has. It sheds load exactly when shedding matters, and it is invisible when the server is healthy.

### 3. Full jitter, not the SDK's jitter

The budget decides how many retries happen; jitter decides when they land. Both SDKs compute the sleep as `(0.75 .. 1.0) x min(0.5 * 2^n, 8.0)`. Their jitter can only shorten the sleep by at most a quarter. But a hundred clients that failed together still retry in a narrow band. Full jitter draws the sleep uniformly from the whole interval: `sleep = random_between(0, min(cap, base * 2**attempt))`. The AWS Architecture Blog's simulation of 100 competing clients needed about 800 calls with full jitter. Against no jitter, it needed about 2,400 calls. The same source names the limit. Jitter improves the constant factor, while total work still grows with the square of the client count. That is why jitter is control three and not the whole fix.

### 4. The health signal, and the one line it cannot lose

The first three controls still send retries at a sick server, only fewer and better spread. The last control stops sending at all. It watches a health signal, a measurement that rises before requests fail. Here that signal is TTFT, the wait for the first token, because Phase 2A showed TTFT measures queue depth. The error rate is a lagging indicator: by the time requests fail, the queue is already deep. TTFT rises while every request still succeeds, so it tells you to stop before the errors do.

The mechanism is a circuit breaker. It is a switch in the client that rejects requests at once when open. It sends nothing to the server:

- Track a rolling window of recent TTFT values, at least 10 samples.

- When the p95 of that window crosses your SLO, open the breaker for a cool-down interval and shed requests immediately, fast and cheap.

- When you open it, discard the measurement window, because those samples describe an overloaded server.

- After the cool-down, let a few probes through (3 by default in the script), then collect 10 fresh samples before the p95 check decides again.

if now < circuit_open_until:
    failed += 1                  # OPEN: shed, fast and cheap
    continue
if len(recent_ttft) >= 10:
    p95 = sorted(recent_ttft)[int(len(recent_ttft) * 0.95) - 1]
    if p95 > args.ttft_slo:
        circuit_open_until = now + args.circuit_seconds
        recent_ttft.clear()      # discard the stale signal
        probes = 0
        failed += 1
        continue

The clear step is the line this control cannot lose. Without it, the breaker wakes after the cool-down. It reads measurements taken while the server was overloaded. It concludes the server is still sick, and opens again forever. The mutation run, which removes one rule and re-runs the simulation, shows the cost of that one line:

changehealth successhealth recoveryself-test

none, the shipped code85.6%5.2 spasses

recent_ttft.clear() removed57.3%30.1 sfails 2 checks

half-open branch removed85.4%5.2 sstill passes

Removing the clear costs 28 points of success and six times the recovery time. Removing the explicit half-open branch costs almost nothing here. This is because the cleared window already forces 10 fresh samples before the next decision. One weakness to know: each client trips its own breaker on its own evidence. So a fleet trips at about half the rate the global failure rate suggests. That is why you run a budget and a breaker rather than either alone.

Evidence
The mutation table and the shipped code come from his own simulation, health_signal.py:131-157. The mutation run on 2026-09-17 is quoted from his phase and not re-run here. The 64-requests example is from the Google SRE Book chapter on addressing cascading failures. The 243x example and "retries are selfish" are from the Amazon Builders' Library. The 800-versus-2,400-calls result is from the AWS Architecture Blog's exponential backoff and jitter post, as reported in the phase. The note could confirm only a cut of more than half. Brooker's fleet-trips-slower observation is from the same comparison, reported in the phase.

Use it. Exercise E4 reruns the mutation row yourself. Delete recent_ttft.clear() in your copy of health_signal.py, run it once, and watch recovery stretch from 5.2 seconds past 30. The question it answers: which of the four controls does your current client have? Which one did you assume the SDK was doing for you?

One layer, a budget, full jitter, then a TTFT breaker that sheds load, in that order.

A breaker that keeps its old measurements reads an overloaded past and never closes again.

Delete recent_ttft.clear() in health_signal.py and rerun; recovery goes from 5.2 s to 30.1 s.

You can now configure a streaming client with four named deadlines. You can pick the numbers from your own TTFT percentiles and read a 429 as a capacity report. You can write a retry policy that sheds load instead of adding it. The next section restates the claims of the whole phase so you can check each one in your own words. After that, Phase 5B answers the question this client sets up. Given the run record it now writes, what can you promise as an SLO? What do you do when the promise breaks?

## What you can do now, and what comes next

You started with one bad morning: p99 spiked, the team added timeouts and retries, and the incident got worse. Each section answered one part of why. Read the claims again now and check each one in your own words.

- One timeout is four deadlines, and none bounds total time. A bare timeout=600 sets connect, read, write and pool independently, and the read timeout resets on every chunk, so a dead stream hangs for ten minutes while a healthy long answer survives. (Your one timeout is four timeouts, and none is a total.)

- The first-token deadline and the mid-stream retry are yours. No transport fires on the time to the first token, so you wrap the first part of your own consume loop, and neither SDK retries after the first byte, so a stream dead at token 400 is your decision: fail, label the partial, or continue. (The deadline no SDK gives you, and the retry no SDK does.)

- A timeout number is a percentile of your own measurements, not a guess. Choose the false-timeout rate you accept, read the matching percentile of measured downstream latency, and use it as the deadline; 0.1% false timeouts means p99.9. (Where the number comes from: your own p99.9.)

- The SDK runs a policy before the network. Both SDKs retry twice by default with a jitter that only shortens, Anthropic refuses non-streaming calls it predicts will exceed ten minutes, and a wrapper that ignores this can stack 12 attempts across two layers. (The SDK's own policy, running before the network.)

- A 429 is a capacity report. Match the header family to know which bucket fired, treat a missing retry-after as a spend cap where every retry fails, and read the reset value in that provider's format before you wait. (A 429 is a capacity report, not an error to retry through.)

- Only a load-shedding retry policy recovers. Backoff with jitter delays retries without reducing their number and ties blind retry at 22.7% success in your simulation, while the health-signal policy sheds load, sends 0.86x the requests, and recovers in 5.2 seconds; the fix is one layer, a retry budget, full jitter, then a TTFT breaker that clears its state when it opens. (Backoff did not fix Story 2; The policy that sends less.)

You can now configure a streaming client with four named deadlines. You can pick the numbers from your own TTFT percentiles and read rate-limit headers as a capacity report. You can write a retry policy that sheds load instead of adding it. The lab that follows lets you run each mechanism yourself. The checkpoint tests whether you can apply them to a new scenario with numbers.

Phase 5B answers the question this client sets up. Your client now writes a run record with named deadlines, attempt counts and the retry markers. These tell a retried request from a fresh one. Given that record, what can you promise as an SLO, and what do you do when the promise breaks?

## Hands-on lab

The concepts above make claims you can now run. Five exercises are offline. E6 and E7 need an API key and cost under $0.05 in total. Work them in the order below; each group names the claim it proves.

The first two exercises test the claim that one bare timeout number sets four independent idle deadlines, and that the read deadline is already a stall detector.

-  E1 offline Read the three deadlines.

- Run: python phase05_operations/run_recorder.py --self-test

- Expected: 19 checks pass, including "a stall is detected" and "a late first token is detected".

- Then open record_stream and find the three deadline checks. The exception says which deadline fired.

- Also find the check that fires when the first token arrives late. Then find the line where live mode sets the transport read timeout. See section 5.1.

- Teaches: "it timed out" is not a diagnosis.

-  E6 live, unverified Give a stream the wrong timeout, then the right one. Costs about $0.02.

- Make a streaming call with timeout=5 as a bare number, and ask for a long answer. Then make the same call with httpx2.Timeout(None, connect=5.0, read=20.0, write=10.0, pool=5.0).

- Expected: the first call can fail on a healthy long answer. The second call does not fail, and it still catches a dead stream.

- Teaches: a single number sets four independent idle timeouts, not one total budget.

The next exercise tests the claim that the SDK already runs a retry and timeout policy underneath your code, before the network.

-  E5 offline Audit your own client.

- Find the max_retries and timeout that your code passes to its LLM client. If it passes neither, find the SDK defaults.

- Answer three questions:

- How many attempts does one call make in total?

- What is the total added delay across those retries?

- Does a single timeout=N in your code set one deadline or four?

- Teaches: the defaults are two retries with at most 1.5 seconds of total backoff. That is much less protection than most people assume.

The next exercise tests the claim that a 429 is a capacity report: which bucket fired, whether retry-after exists, and in which format.

-  E7 live, unverified Cause a 429 and read what it tells you. Costs about $0.03, break-it.

- Send requests concurrently until the server rejects one. Print every response header whose name contains ratelimit or retry.

- Expected: your provider's limit, remaining and reset values. Check the reset format. OpenAI sends a duration such as 6m0s. Anthropic sends an RFC 3339 timestamp.

- Then check whether your code reads any of these headers today.

- Teaches: a 429 carries the server's own capacity report, and most clients discard it.

The last group tests the measured table: retries multiply load, backoff with jitter ties blind retry, and only the load-shedding signal recovers. Run the self-test first, because a simulation you have not tested is only a story.

-  E2 offline Test the retry simulation before you believe it.

- Run: python phase05_operations/health_signal.py --self-test

- Expected: 9 checks pass. Two of them are "backoff is not meaningfully better than blind retry" and "doing nothing beats both retry policies here".

- Teaches: a simulation you have not tested is only a story.

-  E3 offline Watch retries turn a spike into an outage.

- Run: python phase05_operations/health_signal.py

- Expected: no-retry succeeds on 89.0%. Blind retry succeeds on 22.7% and sends 3.14x the requests. The health signal succeeds on 85.6% and sends 0.86x.

- Write down the wasted column for each policy. Blind retry wastes 3,576 requests. The health signal wastes 8.

- Teaches: retries are load.

-  E4 offline Find out why this bug ships, then break the breaker.

- Run: python phase05_operations/health_signal.py --sweep

- Expected: in the first table, at 30% of capacity, all four policies score 99.7% and look the same.

- Then remove the rule that clears the signal, in a copy. Name the copy: B=phase05_operations/hs_broken.py

- Make it: sed 's/recent_ttft.clear()/pass/' phase05_operations/health_signal.py > $B

- Run: python $B

- Expected: the health row drops to 57.3% success, and recovery takes 30.1 s instead of 5.2 s.

- Run: python $B --self-test

- Expected: 2 FAILED. The checks "the health policy keeps most requests alive" and "the health policy recovers within 10 s of the burst" fail. An earlier version of the self-test passed here, because it never checked recovery.

- Clean up: rm $B

- Teaches: a test that does not overload the server cannot see this defect. A test that does not check recovery cannot see the broken rule.

Every offline command above was run on the author's machine on 2026-09-14 and again on 2026-09-17, with matching outputs. E6 and E7 had no API key at review time, so their flag names and header names were checked against the provider documentation and the SDK source but not executed live.

The checkpoint that follows tests the same claims on new scenarios with numbers you have not seen, so do it after the lab and not instead of it.

## Checkpoint 5A

Each question sets a scenario with numbers you have not seen yet. Write your answer first, then open the sketch and compare. The point is not to match the wording but to check that the arithmetic and the mechanism agree with yours.

- The SDK retry arithmetic. Your SDK uses its defaults: two retries, a backoff of min(0.5 × 2ⁿ, 8) seconds, and a jitter multiplier from 0.75 to 1.0. (a) Compute the minimum and maximum of each of the two sleeps. (b) Compute the total added delay for one failed call. (c) Your provider's rate limit resets on a 60-second token bucket (a bucket that refills its capacity over a fixed window). Say whether those retries can succeed, and why.
Answer sketch
(a) First sleep: 0.5 × 2⁰ = 0.5 s, times 0.75 to 1.0, so 0.375 to 0.5 s. Second sleep: 0.5 × 2¹ = 1.0 s, times the same range, so 0.75 to 1.0 s. (b) Between 1.125 and 1.5 seconds in total. (c) They cannot succeed. In 1.5 seconds, a token bucket on a 60-second window refills 1.5 / 60 = 2.5% of its capacity. All three attempts land in the same congested window. The retries add load and achieve nothing.

- "Backoff with jitter fixed it." A colleague says: "We added exponential backoff with jitter. So the retry storm is fixed." Give two reasons why that may be false. One reason is about what backoff changes and does not change. The other is about the jitter your SDK implements.
Answer sketch
First, backoff spreads retries over time, but it does not reduce their number. Under a burst, the same volume still arrives, only later. In the simulation it arrived while the server was still clearing its queue, and it scored the same as blind retry, 22.7%. Second, the SDK jitter multiplier runs from 0.75 to 1.0, so it can only shrink the sleep, by at most a quarter. Full jitter draws the sleep from zero to the cap, and that wide range is what spreads out clients that fail together.

- The two-layer exponent. Your service calls an LLM through a gateway, and the gateway calls the provider. Each layer retries three times. (a) Compute the worst-case number of requests that one user action produces at the provider. (b) Name the one change that removes the exponent. (c) Your provider returns retry-after: 300. Describe what each official SDK does with that header, and why one of them makes things worse.
Answer sketch
(a) Read "retries three times" as three attempts per layer. Then the provider sees 3 × 3 × 3 = 27 requests. Read it as three retries after the first attempt. Then each layer makes four attempts, and 4 × 4 × 4 = 64. In both cases the count is a product, not a sum. (b) Retry at one layer only. (c) The OpenAI SDK does not retry when retry-after is above 120 seconds. That is the safe behaviour. The Anthropic SDK ignores the header above 60 seconds and retries on its normal backoff. So retry-after: 300 produces two retries after at most 1.5 seconds of total waiting. Both fail, and both add load during an overload that the server just reported.

- The stream that dies at token 400. A stream returns 400 tokens of an expected 500, then goes silent forever. Your client sets timeout=600 as a bare number. (a) Trace what happens next, and how long it takes. (b) State what the SDK does about the partial response. (c) Give the timeout configuration that would catch this in 20 seconds, and name each deadline in it.
Answer sketch
(a) A bare number sets connect, read, write and pool all to 600 seconds. The read timeout limits the gap between chunks, so the client waits ten full minutes of silence before it raises an error. (b) Nothing. Neither SDK retries after the first byte of a stream, because the retry loop ends when the response headers arrive. You must handle the partial response. (c) httpx2.Timeout(None, connect=5.0, read=20.0, write=10.0, pool=5.0). Connect limits opening the socket. Read limits the silence between chunks, and it fires in this case. Write limits sending. Pool limits the wait for a free connection. The total is unlimited on purpose, because a long answer is not a failure.

- Design the client policy. Your feature calls one provider, and it must survive a burst of four times normal traffic. Write the client policy. Cover five points: which signal says you are in trouble, why that signal and not the error rate, what you do when it trips, how you decide to resume, and the one metric that shows afterwards whether the policy helped.
Answer sketch
The signal is a rolling TTFT percentile. TTFT (the wait for the first token) measures queue depth, so it rises before any request fails, while the error rate moves only when the queue is already deep. When TTFT crosses the SLO, open a circuit and drop requests, which fails fast and adds no load. Resume through a half-open state: after a cool-down, let a few probe requests through and judge from fresh measurements. Clear the measurements taken during the overload, or the breaker stays open; in the simulation, removing that clear step cut success from 85.6% to 57.3%. Afterwards, the deciding metric is requests sent divided by requests offered. That ratio is the amplification factor, and the success rate alone cannot separate a policy that helped from one that was lucky.

Questions 1 and 3 draw on the deadline and SDK sections of this phase. Question 5 asks for the four controls in order; once you can write it, the cheatsheet compresses this phase for review, and Phase 5B asks what you can promise an SLO built on the run record this client now writes.

## Cheatsheet

THE FOUR DEADLINES (a total-duration timeout is the wrong shape for a stream)
  connect       socket never opened                    httpx2 connect
  first token   accepted, never started                no SDK has this: wrap your own loop
  stall         stream started, then died              httpx2 read IS this, it resets per chunk
  total         runaway cost, last resort only         your own outer deadline
  httpx2.Timeout(None, connect=5.0, read=20.0, write=10.0, pool=5.0)
  timeout=600 is NOT a 10-minute budget. It is FOUR 10-minute idle deadlines.
  SDK default: httpx2.Timeout(timeout=10*60, connect=5.0)
  NEITHER SDK RETRIES AFTER THE FIRST BYTE OF A STREAM.
  Pick the number: accept 0.1% false timeouts, use your own measured p99.9.

RATE LIMITS (the two providers agree on almost nothing)
                        OpenAI                  Anthropic
  header prefix         x-ratelimit-            anthropic-ratelimit-
  reset format          duration "6m0s"         RFC 3339 timestamp
  remaining             exact                   rounded to nearest 1000
  cached tokens count   yes                     no (Haiku 3.5 excepted)
  overload status       503                     529 (non-standard)
  Anthropic: caching is a CAPACITY decision. 2M ITPM at 80% hit = 10M effective
  input tokens per minute.
  The 429 you must NOT retry: Anthropic spend cap, no retry-after,
  error_code enforced_spend_limit_reached. Every retry fails until access resumes.
  OpenAI ramp limit: above ~1M input TPM, grow at most 50% per 15 min (code slow_down).
  Match >= 500, never a list, or you miss 529.

SDK DEFAULTS (identical in both, checked at openai 3.25 / anthropic 1.12)
  max_retries 2, so 3 attempts || statuses 408, 409, 429, >= 500
  backoff   min(0.5 * 2^n, 8.0)
  jitter    1 - 0.25*random(), multiplier 0.75..1.0, it can ONLY shrink
  retry-after: OpenAI refuses to retry above 120 s; Anthropic ignores the header
  above 60 s and retries anyway.
  full jitter instead: random_between(0, min(cap, base * 2^n))
  Anthropic non-streaming guard: expected_time = 3600 * max_tokens / 128_000,
  raises ValueError when it exceeds 600 s. stream=True bypasses it.
  Your 3 retries on top of the SDK's 2 = 3 * 4 = 12 attempts.

RETRIES UNDER LOAD (his simulation: burst to 2.5x for 8 s, mean of 5 runs)
  policy    sent   amp    success  wasted  recover
  none      1229   1.00x   89.0%     135   18.2 s
  blind     3855   3.14x   22.7%    3576   never
  backoff   3896   3.18x   22.7%    3617   never    <- NOT better than blind
  health    1060   0.86x   85.6%       8    5.2 s
  AT 30% LOAD ALL FOUR SCORE 99.7%. That is why this bug ships.
  Amplification is a PRODUCT across layers: 3 layers x 4 attempts = 64.

WHAT WORKS, in order
  1. retry at ONE layer              removes the exponent
  2. a retry budget                  token bucket; the deposit ratio IS the
                                     failure rate at which retries stop
  3. full jitter, not the SDK's
  4. a health signal that STOPS you sending   <- the only one that recovered

THE HEALTH SIGNAL
  The signal is TTFT, not the error rate. TTFT is queue depth, so it rises first.
  Circuit breaker:
    CLEAR the stale measurements when it opens. Without the clear: 57.3% success,
    30.1 s recovery in the mutation run.
    A half-open probe state: little effect in this simulation.
  Record x-stainless-retry-count, or you cannot tell retries from new load. (Cloudflare)

THE COMMANDS
  run_recorder.py --self-test              the deadline checks, offline
  health_signal.py --self-test             the simulation, offline
  health_signal.py                         four policies under a burst
  health_signal.py --sweep                 why it is invisible at light load

## What you could post

The retry table

I simulated a burst at 2.5x server capacity, mean of five runs. Doing nothing scored 89.0% success. Blind retries scored 22.7%. Exponential backoff with jitter, the standard fix, also scored 22.7%, because it delays retries without reducing their number. The only policy that recovered, in 5.2 seconds, was one that stopped sending.

His because the numbers are his. The four-policy table came from his own simulation. The surprise in it, backoff tying blind retry, contradicts the advice everyone repeats.

The stall detector you already have

Both Python SDKs ship timeout=600 as their default. That number is not a 10-minute call budget. It is an inactivity deadline that resets on every chunk, so it is already the stall detector people hand-write. A dead stream under it hangs for ten minutes.

His because he measured it. His mock-endpoint run showed each arriving chunk resetting the read deadline, against a default he read in the SDK source.

## Sources

- pydantic.dev/docs/httpx2/advanced/timeouts/ — the definition behind the stall detector: the read timeout is "5 seconds of network inactivity", and the four timeout types.

- openai-python v3.25.0, _constants.py — the default httpx2.Timeout(timeout=10 * 60, connect=5.0) used in the four-deadlines section.

- anthropic-sdk-python v1.12.0, _constants.py — the same 600-second default on the Anthropic side.

- anthropic-sdk-python v1.12.0, _base_client.py — the non-streaming guard formula, the retry constants, and the jitter line 1 - 0.25 * random().

- openai-python v3.25.0, _base_client.py — the shared retry loop and the refusal to retry a retry-after above 120 seconds.

- platform.claude.com/docs/en/api/rate-limits — the header families, cache-aware ITPM with the 2M to 10M worked example, and the spend-cap 429 with no retry-after header.

- platform.openai.com/docs/guides/rate-limits — the 6m0s reset format, the header table, and the slow_down ramp-limit rule.

- aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/ — the p99.9 timeout method, the 243x five-layer retry example, and "retries are selfish".

- aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/ — Brooker's full-jitter formula, and the simulation where jitter cut competing-client calls by more than half.

- sre.google/sre-book/handling-overload/ — the retry budget: three attempts per request, a 10% retry ratio taking worst-case load from 3X to 1.1X, and "retries are indistinguishable from new requests".

- brooker.co.za/blog/2022/02/28/retries.html — the token-bucket retry-budget simulation, where the deposit ratio is the failure rate at which retries stop. (In the study note's list, not independently re-fetched here.)

- github.blog — The August 17 outage and the work ahead — the client-side retry loop that increased traffic during Copilot recovery, and the remediation naming retry limits, retry budgets and variable timeouts.

- blog.cloudflare.com — the 12 September 2025 dashboard and API outage — the dashboard retry loop, the thundering herd on recovery, and the admission that retries were hard to tell apart from new requests.

- github.com/openai/openai-python/releases — version drift: openai 3.26.1 released 2026-10-08, with the constants above re-verified at v3.25.0.

Every page above was opened on 2026-10-08 for the study note behind this lesson. SDK behaviour ages fast, so before you quote a default in a design doc, re-read the constant in the version you actually run.
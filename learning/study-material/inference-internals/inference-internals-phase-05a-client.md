# Phase 5A — The client under stress

Phases 1 to 4 measured a system that was working. This phase covers the hours when it is not. In those hours, your client's own behaviour decides whether a short problem becomes a long outage.

Phase 0 told Story 2. p99 latency spiked. The p99 is the latency of the slowest 1% of requests. The team added short timeouts and retries, and the incident got worse. Phase 0 promised the fix for Phase 5. It arrives here, and the measured result is worse than the story.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, this document                                                    │
│  5.1  Streaming and the three  — your one timeout is the wrong one       │
│       timeouts                                                           │
│  5.2  Rate limits              — read the headers, they disagree         │
│  5.3  Retries                  — why yours make it worse, measured       │
│                                                                          │
│ PART B, the next document                                                │
│  5.4  SLOs                     — for a thing that can be up, fast, wrong │
│  5.5  The run record           — what to store, under which names        │
│  5.6  Fallbacks                — the pattern you will reach for, and     │
│                                  usually should not                      │
└──────────────────────────────────────────────────────────────────────────┘
```

Five of the seven exercises here run offline. Two need an API key and cost under $0.05.

Time: 2 to 3 hours.

Setup:

```bash
cd ~/Desktop/project/code/study-material/inference-internals/code
pip install -e .          # or, in the uv environment: source .venv/bin/activate
python phase05_operations/run_recorder.py --self-test
python phase05_operations/health_signal.py --self-test
```

Both self-tests must pass before you start. Everything in this phase is a simulation or a measurement. So you test the arithmetic first.

---

## 5.1 — Streaming and the three timeouts (your one timeout is the wrong one)

Why this matters: almost every LLM client has one timeout, and it limits the total duration. That is the wrong shape for a streaming response. This mistake turns a slow minute into an outage.

**The problem in one line.** A long answer is not a failure. A stream that stopped is a failure. A total-duration timeout cannot tell the two apart.

You want to limit several different things. A deadline is the longest time you will wait for one of them:

```
┌────────────────┬────────────────────────────────┬─────────────────────────┐
│ deadline       │ what it catches                │ what it must NOT do     │
├────────────────┼────────────────────────────────┼─────────────────────────┤
│ connect        │ the socket never opened        │ —                       │
│ first token    │ the server accepted the        │ fire because the answer │
│                │ request and never started      │ is long                 │
│ stall / idle   │ the stream started and then    │ fire during a normal    │
│                │ died mid-answer                │ gap between chunks      │
│ total          │ runaway cost, last resort      │ be your primary control │
└────────────────┴────────────────────────────────┴─────────────────────────┘
```

### The mechanism most people miss

Both official Python SDKs send requests through httpx2, an HTTP client library. In the course environment, openai 3.6.0 and anthropic 1.5.0 both import `httpx2`, version 2.12.0. The plain `httpx` module is not installed there. httpx2 keeps the httpx timeout model, and its `read` timeout is **already a stall timeout**. The httpx documentation says so:

> The read timeout specifies the maximum duration to wait for **a chunk of data** to be received.

The read timeout resets on every chunk. A server-sent-event stream, or SSE stream, sends each event as a chunk. So the stall timeout you want already exists. Passing a single number hides it:

```python
# WRONG: one number sets connect, read, write and pool ALL to 600 seconds.
# That is not a ten-minute total budget. It is four independent ten-minute
# idle timeouts, and a dead stream can hang for ten minutes before it fires.
client = OpenAI(timeout=600)

# RIGHT: name each deadline. `read` is the gap between chunks, not the total.
import httpx2
client = OpenAI(timeout=httpx2.Timeout(
    None,          # no total limit; a long answer is not a failure
    connect=5.0,
    read=20.0,     # STALL: the longest acceptable silence mid-stream
    write=10.0,
    pool=5.0,
))
```

This review checked the WRONG line on 2026-09-17. `httpx2.Timeout(600)` has connect, read, write and pool all equal to 600. Both SDKs accept the same object. You can also pass it per request with `with_options(timeout=...)`.

**Neither SDK has a first-token timeout.** No parameter exists. One pattern works. Run the first part of your consume loop under an outer deadline sized for time to first token, or TTFT. Cancel the call if no content event arrives in time. Then consume the rest without that deadline. This pattern is engineering reasoning. No published source describes it.

`run_recorder.py` checks three deadlines inside its consume loop, at `run_recorder.py:141-166`. **Important: the loop can only act when a chunk arrives.** So it checks every chunk, including usage chunks and empty keep-alive chunks. A late first token raises `first_token`, even though the token did arrive. A long gap raises `stall` when the late chunk finally arrives. Silence itself is caught one layer down. Live mode sets the httpx2 `read` timeout to the stall deadline, at `run_recorder.py:424-427`. An earlier version of the script checked the first-token deadline only after `first` was set, so it could never fire. A test with a 20-second first token and a 10-second deadline raised nothing. The self-test now includes that case.

```
  WHICH DEADLINE FIRES, ON A TIMELINE (example numbers)

  t=0.0   request sent
          │
          ├─ connect deadline (5s) ──────────► socket never opened
          │
  t=0.4   first chunk arrives
          │  └─ first-token deadline stops mattering here
          │
  t=0.4 ──┬── 0.42 ── 0.44 ── 0.46 ─────────────────────► ...
          │   chunk    chunk    chunk    then SILENCE
          │                              │
          │                              ├─ stall deadline (20s)
          │                              │   fires at t=20.46
          │                              │
          │                              └─ a BARE timeout=600 waits
          │                                  until t=600.46 instead
          │
  a long but healthy answer keeps resetting the stall deadline
  and is never interrupted. That is the behaviour you want.
```

### Pick the numbers from your own latency data

A published method exists for choosing a timeout. It is better than a guess. The Amazon Builders' Library describes it in three steps:

1. Choose the rate of false timeouts you accept. A false timeout cancels a call that would have succeeded.
2. Read the matching percentile from the measured latency of the call.
3. Use that latency as the timeout.

Amazon's example accepts **0.1%** false timeouts, so it uses the **p99.9** latency of the downstream call.

The same source names two conditions where the method fails:

- The clients have substantial network latency, for example across the internet.
- The service has tight latency bounds, so p99.9 is close to p50.

You already have the data. Phase 1 measured TTFT, and `run_recorder.py` now writes it per request.

### What the vendors say about long requests

The Anthropic Python SDK refuses a non-streaming request that it predicts will take more than ten minutes. The check is in its source, at `anthropic/_base_client.py:766` in version 1.5.0. It uses this arithmetic:

```
expected_time = 3600 seconds * max_tokens / 128,000
```

That formula assumes **128,000 output tokens per hour**, or about **35.6 output tokens per second**. If the estimate is over ten minutes, the SDK raises an error that tells you to stream. Passing `stream=True` or your own timeout turns the check off.

Anthropic's documentation gives the reason. Some networks drop idle connections. So a long non-streaming request can fail and return nothing. Streaming keeps the connection busy.

**You cannot size a timeout from heartbeats.** A heartbeat is a small event that shows the stream is alive. Anthropic documents `ping` events in its stream. It does not document how often they arrive. OpenAI publishes no streaming timeout guidance at all. A search of its streaming guide for eight terms, including "timeout", "idle", "keepalive" and "stall", found zero matches. So your stall timeout must come from measurements of your own traffic.

### The failure the SDKs will not handle for you

This is the most important part of the section.

**Neither SDK retries anything after the first byte of a stream.** The retry loop lives in the request method. It ends when the response headers arrive. The streaming module contains no retry logic.

So a stream that dies at token 400 of 500 is your problem. You have three options:

1. Fail the request.
2. Return the partial answer, and say that it is partial.
3. Continue the answer with a second call.

Anthropic documents a continuation procedure, and it differs by model generation. Older models take the partial text back as an assistant message. Newer models want a user message that tells the model to continue.

**The sentence to remember:** the read timeout is a stall timeout that resets on every chunk. Name each deadline. Do not pass one number that becomes four.

**The trap:** `timeout=600` looks like a ten-minute budget, and it is not. It sets four independent ten-minute idle timeouts. A dead stream hangs for the full ten minutes.

**Try this now:** run `python phase05_operations/run_recorder.py --self-test` and find the check named "a stall is detected". Then read `record_stream`. It raises a `Timeout` that says **which** deadline fired. "It timed out" is not a diagnosis.

---

## 5.2 — Rate limits (read the headers, they disagree with each other)

Why this matters: a 429 status tells you the server's capacity. It is not a failure to retry through. The capacity report is in headers that most clients discard. Phase 3 taught you to read the `usage` object. This section applies the same lesson to the response headers.

### The two providers agree only on the status code

This comparison comes from the provider documentation, read on 2026-09-14. On 2026-09-17, this review checked these rows again: the reset formats, Anthropic's rounding and cache rule, and the overload codes. The pages change, so check them again and date your notes.

```
┌──────────────────────┬─────────────────────────┬──────────────────────────┐
│                      │ OpenAI                  │ Anthropic                │
├──────────────────────┼─────────────────────────┼──────────────────────────┤
│ limit dimensions     │ requests, tokens,       │ requests, INPUT tokens,  │
│                      │ images, audio minutes;  │ OUTPUT tokens, priced    │
│                      │ per minute and per day  │ separately               │
│ header prefix        │ x-ratelimit-...         │ anthropic-ratelimit-...  │
│ reset format         │ duration string, "6m0s" │ RFC 3339 timestamp       │
│ remaining accuracy   │ exact                   │ rounded to the nearest   │
│                      │                         │ thousand                 │
│ CACHED tokens count  │ YES, toward the token   │ NO, on most models       │
│ toward the limit     │ limit                   │                          │
│ overload status      │ 503                     │ 529                      │
└──────────────────────┴─────────────────────────┴──────────────────────────┘
```

**The cached-token row matters most in practice.** On OpenAI, the caching work from Phase 3 saves money only. On Anthropic, it saves money *and* adds throughput, because cache reads do not use your input-token budget. Anthropic gives a worked example. Take a limit of 2,000,000 input tokens per minute and an 80% cache hit rate. You can then process an effective **10,000,000** input tokens per minute.

So on Anthropic, the prompt layout work from Phase 3 section 3.2 is also a capacity decision. The documentation names one exception. Claude Haiku 3.5 counts cache reads toward the limit. A capacity plan that misses this exception is wrong for that model.

**The reset-format row causes real parsing bugs.** OpenAI returns a Go-style duration, `6m0s`. That value is neither a number nor a timestamp. Anthropic returns an RFC 3339 timestamp. Code that parses one format will misparse the other without an error. A wrong reset time causes one of two problems:

- Every client retries at once.
- Clients wait long after capacity is back.

### The overload status code is not 503 on both

OpenAI returns **503** with the code `server_is_overloaded`. Anthropic returns **529**, which is not a standard HTTP status.

```python
# WRONG: enumerating the statuses you know about misses 529 entirely.
if status in (500, 502, 503, 504):
    retryable = True

# RIGHT: treat any 5xx as retryable, and branch on the code when you need to.
retryable = status >= 500 or status in (408, 409, 429)
```

Both SDKs get this right, because they retry on any status of 500 or above.

### The 429 that you must not retry

Anthropic returns a 429 with the ordinary rate-limit error type when you reach your usage tier's monthly **spend cap**. Its documentation states the result:

> The error type is `rate_limit_error`, the same as for a rate limit, but the response has no `retry-after` header. Retrying, including the SDKs' automatic retries, fails until access resumes.

So a spend cap looks like congestion, and every retry is wasted. Only a nested error code tells the two apart. On the Messages API, the code is `enforced_spend_limit_reached` in `error.details.error_code`. Suppose the Phase 3 budget guard fires and this 429 appears at the same time. Then you have found the cause.

OpenAI has a gap in its documentation too. Its error-code page lists every 429 row with a type or a code, except one. The plain rate-limit row, "Rate limit reached for requests", has neither. So OpenAI documents no machine-readable way to tell an ordinary rate limit from the other 429s.

### Ramp limits are a third kind of limit

OpenAI limits how fast your traffic may *grow*. This limit is separate from how much you may send:

> As a rule of thumb, once your traffic reaches 1 million input tokens per minute (TPM), increase it by no more than 50% every 15 minutes.

When you exceed the ramp, the API returns a 429 with the code `slow_down`. The documentation says this can happen **while you are inside both your request and token limits**. Suppose you launch a feature and move all its traffic in one step. This is the limit you will hit first. Anthropic describes a similar "acceleration limit" and asks you to ramp up gradually. It publishes no number for it.

### What to do with the headers

Do three things, in order of value:

1. **Record the headers on every response.** Store `remaining` and `reset` in the run record, next to the token counts. Then you see a capacity problem before it becomes a 429.
2. **Slow down early.** Reduce concurrency when the remaining tokens fall below a set fraction of the limit. A slowdown costs less than a rejection and a retry.
3. **Honour `retry-after` in your own code.** Section 5.3 shows why you cannot rely on the SDK for this.

**The sentence to remember:** a 429 carries the server's capacity report in its headers. The two providers disagree on the dimensions, the format, the accuracy, and whether cache hits count.

**The trap:** parsing the reset header as a number. OpenAI sends `6m0s`, and Anthropic sends a timestamp. Neither value is an integer.

**Try this now:** find the code that handles a 429. Check whether it reads any header at all. Then check whether it would handle a 529.

---

## 5.3 — Retries (why yours make it worse, measured)

Why this matters: this section delivers the fix that Phase 0 promised for Story 2. The measured result is stronger than the story.

### Run it

```bash
python phase05_operations/health_signal.py
```

The simulation has these settings, all from the script's defaults:

- The server handles 20 requests per second.
- Normal traffic is 12 requests per second.
- A burst raises traffic to 30 requests per second for eight seconds.

Four client policies run against the same server. Each row is the mean of five runs. The output below is from a run on 2026-09-17, and it matches the run of 2026-09-14:

```
┌──────────┬──────────┬───────────┬─────────┬─────────┬──────────┬──────────┐
│ policy   │ sent     │ amplifier │ success │ wasted  │ p99 (s)  │ recover  │
├──────────┼──────────┼───────────┼─────────┼─────────┼──────────┼──────────┤
│ none     │     1229 │     1.00x │   89.0% │     135 │     3.80 │    18.2s │
│ blind    │     3855 │     3.14x │   22.7% │    3576 │     3.93 │    never │
│ backoff  │     3896 │     3.18x │   22.7% │    3617 │     3.93 │    never │
│ health   │     1060 │     0.86x │   85.6% │       8 │     1.70 │     5.2s │
└──────────┴──────────┴───────────┴─────────┴─────────┴──────────┴──────────┘
```

The table shows three results. Two of them surprise most people.

**Blind retry turned an 89% success rate into a 22.7% outage.** Doing nothing succeeded about four times as often.

**Exponential backoff with jitter did not help.** Backoff waits longer before each new retry. Jitter adds a random part to that wait. This policy scored the same as blind retry, and it sent slightly *more* requests. Spreading retries over time does not reduce their number. Delayed retries can also land later, while the server is still clearing its queue.

**The health signal recovered in 5.2 seconds.** Both retry policies never recovered inside the run. The health signal wasted 8 requests. Blind retry wasted 3,576.

### Why the loop closes

Most retry demonstrations model the server as a fixed delay. In that model, retries look free. They are not free, because your retries are the load:

```
  ┌───────────────┐     ┌───────────────┐     ┌───────────────┐     ┌───────────────┐
  │  more retries ├────►│  deeper queue ├────►│  higher TTFT  ├────►│ more timeouts │
  └───────▲───────┘     └───────────────┘     └───────────────┘     └───────┬───────┘
          │                                                                 │
          └─────────────────────────────────────────────────────────────────┘
                       each timeout comes back as another retry
```

Two published numbers show how fast this load grows when several layers each retry. They come from two different sources:

- The Google SRE Book describes three layers that each make 4 attempts. One user action then creates **4³ = 64** attempts on the database.
- The Amazon Builders' Library describes a five-deep stack with three retries at each layer. It says the database load grows **243x**. Its own arithmetic counts three tries per layer, so 3⁵ = 243.

```
  ONE USER ACTION, THREE LAYERS, FOUR ATTEMPTS EACH (Google SRE Book)

  user
   └── frontend          4 attempts
        └── backend           4 attempts each
             └── database          4 attempts each
                  ═══════════════════════════════
                  4 x 4 x 4  =  64 requests

  the exponent is the NUMBER OF LAYERS, not the retry count
  five layers at three tries each (Amazon): 3^5 = 243x
```

The Amazon Builders' Library states the rule:

> retry at a single point in the stack

The Google SRE Book gives the same advice. It says to avoid retries at multiple levels.

The Amazon source also states the whole problem in three words:

> retries are selfish

### Your SDK's defaults are weaker than you think

This review read both official Python SDKs: openai 3.6.0 and anthropic 1.5.0. Their defaults are identical, and they are not what most people assume:

```
  max retries          2, so three attempts
  retried statuses     408, 409, 429, and anything >= 500
  backoff              min(0.5 * 2^n, 8.0) seconds
  jitter               multiplier = 1 - 0.25 * random()
```

Look at the jitter line. The multiplier is between 0.75 and 1.0. So jitter can only **shrink** the sleep, by at most a quarter. Compare it with the published full-jitter formula. Full jitter draws the sleep at random from the whole interval:

```
  full jitter   sleep = random_between(0, min(cap, base * 2^attempt))
  the SDKs      sleep = (0.75 .. 1.0) * min(cap, base * 2^attempt)
```

```
  WHERE EACH RETRY SLEEP CAN LAND, with the SDK defaults

                        0 s       0.25 s    0.5 s     0.75 s    1 s
                        ├─────────┼─────────┼─────────┼─────────┤
  SDK, retry 1                         █████                    │ 0.375 to 0.5 s
  SDK, retry 2                                        ██████████│ 0.75 to 1.0 s
  full jitter, retry 1  ████████████████████                    │ 0 to 0.5 s
  full jitter, retry 2  ████████████████████████████████████████│ 0 to 1.0 s

  the SDK range is narrow, so many clients still retry together
  full jitter spreads the same clients across the whole range
```

With the defaults, the two retry sleeps add up to at most 1.5 seconds. A token bucket is a rate limiter that refills a fixed amount per unit of time. 1.5 seconds is far too little for a token bucket to refill. The narrow range is also too small to spread out many clients that fail at the same moment.

**The two SDKs also disagree about `retry-after`, and it matters.**

- The OpenAI SDK does not retry at all when the header asks for more than 120 seconds.
- The Anthropic SDK **ignores the header** when it is above 60 seconds. It retries anyway, on the normal backoff of under a second.

So on the Anthropic SDK, a `retry-after: 300` produces two retries after at most 1.5 seconds of total waiting. Both fail, and both add load.

If a long `retry-after` matters to your system, handle it in your own code. Setting `max_retries=0` and writing your own policy is a valid choice.

### What works

Add these four mechanisms in this order:

**1. Retry at one layer only.** It costs nothing, and it removes the exponent.

**2. A retry budget.** A retry budget limits retries as a share of traffic, not per request. The Google SRE Book gives an example: allow **60 retries per minute per process**, and fail the request beyond that. Marc Brooker describes a related design with a token bucket. Each success adds a fraction of a token, and each retry spends one token. With 0.1 tokens per success, retries stop above a 10% failure rate. So the deposit ratio *is* the crossover point, which gives you a clear way to choose it.

**3. Full jitter, not the SDK's jitter.** The AWS Architecture Blog simulated 100 competing clients. Full jitter needed about 800 calls. With no jitter, the clients needed about 2,400. The same source states two costs. Jittered backoff takes longer in wall-clock time than no backoff. Total work still grows with the square of the number of clients. Jitter improves the constant factor, not the exponent.

**4. A health signal that stops you sending.** Phase 0 promised this mechanism. The table above shows why it comes last in the list but first in value.

### The signal is TTFT, not the error rate

The error rate is a lagging indicator. When requests start to fail, the queue is already deep. TTFT rises first, because TTFT measures queue depth. Phase 2 section 2.1 showed this.

So the policy works like this:

1. Track a rolling TTFT percentile.
2. When it crosses your SLO, stop sending and drop the request instead. An SLO, or service level objective, is the target you promise.

The simulation builds this policy as a circuit breaker. A circuit breaker is a switch in the client. When it is open, the client rejects requests at once and sends nothing to the server.

The author found one design rule when the simulation failed. **The breaker must discard its signal when it opens.** Without that rule, the breaker stays open. After the cool-down, it reads measurements taken while the server was overloaded. It decides the server is still unhealthy, and it opens again, forever. In the author's first version of this simulation, this bug alone dropped the health policy to a 14% success rate. This review did not re-run that first version.

The shipped code follows. It is from `health_signal.py:131-157`, with comments shortened and indentation removed. The logic is unchanged:

```python
if now < circuit_open_until:
    failed += 1                          # OPEN: shed, fast and cheap
    continue
if circuit_open_until > 0 and probes < args.probe_count:
    probes += 1                          # HALF-OPEN: let a few through
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
        recent_ttft.clear()              # discard the stale signal
        probes = 0
        failed += 1
        continue
```

The code also has a half-open state. After the cool-down, it lets `--probe-count` requests through, 3 by default. Then it sends normally until it has 10 fresh TTFT samples. The p95 check then decides again.

**A mutation run on 2026-09-17 tested both rules.** A mutation run removes one rule and runs the code again:

| change | health success | health recovery | self-test |
|---|---|---|---|
| none, the shipped code | 85.6% | 5.2 s | passes |
| `recent_ttft.clear()` removed | 57.3% | 30.1 s | fails 2 checks |
| half-open branch removed | 85.4% | 5.2 s | still passes |

So clearing the signal matters a lot in this simulation. The explicit half-open branch adds little here. Clearing the signal already forces 10 fresh samples before the next decision. An earlier self-test caught neither change. It now checks success and recovery, so it catches the first. The second change has too small an effect to test. Exercise E4 reproduces the first row.

```
  THE THREE STATES, AND WHY THE MIDDLE ONE EXISTS

        ┌────────────┐   TTFT p95 > SLO    ┌────────────┐
        │  CLOSED    ├────────────────────►│   OPEN     │
        │  send all  │                     │  shed all  │
        └─────▲──────┘                     └─────┬──────┘
              │                                  │ cool-down
              │ probes healthy                   │ elapsed
              │                                  ▼
              │                            ┌────────────┐
              └────────────────────────────┤ HALF-OPEN  │
                    probes still bad       │ send a few │
                    ──────────────────────►│  probes    │
                        back to OPEN       └────────────┘

  entering OPEN must also CLEAR the measurement history, or HALF-OPEN
  judges the server from numbers taken while it was overloaded and
  the breaker never closes again
```

Breakers have a known weakness. Marc Brooker's comparison shows that each client trips its breaker on its own evidence. So a fleet of breakers trips at about half the rate you would expect from the global failure rate. That supports using a budget *and* a breaker, not only one.

### Why this bug reaches production

Run the sweep:

```bash
python phase05_operations/health_signal.py --sweep
```

At 30% of capacity, all four policies score 99.7% and look the same. The defect is invisible in every test that does not overload the server. That explains why experienced teams still ship it.

Near capacity, both retry policies do worse than doing nothing: 14.1% and 14.2% against 17.3%. In the OVERLOAD table they only tie with it. All three policies without the health signal score 3.1%, because almost nothing gets through either way. The health signal scores better at every load.

### It happens to real systems

Three public incident reports describe this mechanism.

GitHub's outage report of 20 August 2026 names the cause. Errors "triggered a client-side retry loop that increased traffic during recovery". Some Copilot services, its AI assistant, took longer to recover. The remediation names all three mitigations above: retry limits, retry budgets, and variable timeouts.

GitHub's availability report for August 2025 describes a search incident. It says "retry queues eventually overwhelmed the load balancers, causing failure". Up to 75% of queries failed over nearly four hours. Throttling fixed it, not added capacity.

Cloudflare's report on its September 2025 dashboard outage describes two stages. First, a client-side loop made too many calls. Then, on recovery, every client reconnected at once. This is called a thundering herd. The fix added random delays to spread the retries.

**The sentence to remember:** retries are load. Under overload, only a policy that sends less can help. TTFT tells you to stop before the errors do.

**The trap:** believing that exponential backoff is the fix. Here it scored the same as blind retry. Your SDK's jitter can only shrink the delay, by at most a quarter.

**Try this now:** run `python phase05_operations/health_signal.py --sweep`. Compare the first table with the third. Then find your own client's `max_retries`. Decide whether the default of 2 retries, with at most 1.5 seconds of total backoff, is what you want.

---

## 🧪 Hands-on lab — part A

Five of the seven exercises are offline. E6 and E7 need an API key and cost under $0.05.

**Live-run status:** every offline command below was executed on the author's machine on 2026-09-14. This review ran them again on 2026-09-17, and the outputs matched. No API key was available, so E6 and E7 were not executed. Their flag names and header names were checked against the provider documentation and the SDK source.

- [ ] **E1 (offline).** Read the three deadlines.
  - Run: `python phase05_operations/run_recorder.py --self-test`
  - Expected: 19 checks pass, including "a stall is detected" and "a late first token is detected".
  - Then open `record_stream` and find the three deadline checks. The exception says **which** deadline fired.
  - Also find the check that fires when the first token arrives late. Then find the line where live mode sets the transport read timeout. See section 5.1.
  - Teaches: "it timed out" is not a diagnosis.

- [ ] **E2 (offline).** Test the retry simulation before you believe it.
  - Run: `python phase05_operations/health_signal.py --self-test`
  - Expected: 9 checks pass. Two of them are "backoff is not meaningfully better than blind retry" and "doing nothing beats both retry policies here".
  - Teaches: a simulation you have not tested is only a story.

- [ ] **E3 (offline).** Watch retries turn a spike into an outage.
  - Run: `python phase05_operations/health_signal.py`
  - Expected: no-retry succeeds on 89.0%. Blind retry succeeds on 22.7% and sends 3.14x the requests. The health signal succeeds on 85.6% and sends 0.86x.
  - Write down the wasted column for each policy. Blind retry wastes 3,576 requests. The health signal wastes 8.
  - Teaches: retries are load.

- [ ] **E4 (break-it, offline).** Find out why this bug ships, then break the breaker.
  - Run: `python phase05_operations/health_signal.py --sweep`
  - Expected: in the first table, at 30% of capacity, all four policies score 99.7% and look the same.
  - Then remove the rule that clears the signal, in a copy. Name the copy: `B=phase05_operations/hs_broken.py`
  - Make it: `sed 's/recent_ttft.clear()/pass/' phase05_operations/health_signal.py > $B`
  - Run: `python $B`
  - Expected: the health row drops to 57.3% success, and recovery takes 30.1 s instead of 5.2 s.
  - Run: `python $B --self-test`
  - Expected: `2 FAILED`. The checks "the health policy keeps most requests alive" and "the health policy recovers within 10 s of the burst" fail. An earlier version of the self-test passed here, because it never checked recovery.
  - Clean up: `rm $B`
  - Teaches: a test that does not overload the server cannot see this defect. A test that does not check recovery cannot see the broken rule.

- [ ] **E5 (offline).** Audit your own client.
  - Find the `max_retries` and `timeout` that your code passes to its LLM client. If it passes neither, find the SDK defaults.
  - Answer three questions:
    1. How many attempts does one call make in total?
    2. What is the total added delay across those retries?
    3. Does a single `timeout=N` in your code set one deadline or four?
  - Teaches: the defaults are two retries with at most 1.5 seconds of total backoff. That is much less protection than most people assume.

- [ ] **E6 (UNVERIFIED against a live provider).** Give a stream the wrong timeout, then the right one.
  - Make a streaming call with `timeout=5` as a bare number, and ask for a long answer. Then make the same call with `httpx2.Timeout(None, connect=5.0, read=20.0, write=10.0, pool=5.0)`.
  - Expected: the first call can fail on a healthy long answer. The second call does not fail, and it still catches a dead stream.
  - Costs at most: about $0.02.
  - Teaches: a single number sets four independent idle timeouts, not one total budget.

- [ ] **E7 (break-it, UNVERIFIED against a live provider).** Cause a 429 and read what it tells you.
  - Send requests concurrently until the server rejects one. Print every response header whose name contains `ratelimit` or `retry`.
  - Expected: your provider's limit, remaining and reset values. Check the reset **format**. OpenAI sends a duration such as `6m0s`. Anthropic sends an RFC 3339 timestamp.
  - Then check whether your code reads any of these headers today.
  - Costs at most: about $0.03.
  - Teaches: a 429 carries the server's own capacity report, and most clients discard it.

---

## 🔍 Check it yourself

1. Open `record_stream` at `run_recorder.py:120`. It takes an iterable of tuples, not an SDK client. Explain what that design gives you. Name the specific thing it lets the self-test do that a client-based function could not.
2. In `health_signal.py`, find `Provider.submit`. Line 69 sets `req["ttft"]` from the queue depth **at admission**. Explain in one sentence why this line makes the simulation a closed loop and not a fixed-delay model.
3. In the same file, find where the circuit breaker calls `recent_ttft.clear()`, at line 154. Describe the failure that happens if you delete that line. Then find the two self-test checks that catch it. Say which numbers from the E4 run each one tests, and why the thresholds sit where they do.
4. In your own code, find where the client is built. Does it pass a timeout? If so, is it a bare number? Work out how many independent deadlines that number sets.

---

## ✅ Checkpoint 5A — answer in your own words

1. Show the arithmetic. Your SDK uses its defaults: two retries, a backoff of `min(0.5 × 2ⁿ, 8)` seconds, and a jitter multiplier from 0.75 to 1.0. (a) Compute the minimum and maximum of each of the two sleeps. (b) Compute the total added delay for one failed call. (c) Your provider's rate limit resets on a 60-second window. Say whether those retries can succeed, and why.

2. A colleague says: "We added exponential backoff with jitter. So the retry storm is fixed." Using section 5.3, give two reasons why that may be false. One reason is about what backoff changes and does not change. The other is about the jitter that your SDK implements.

3. This is broken. Your service calls an LLM through a gateway, and the gateway calls the provider. Each layer retries three times. (a) Compute the worst-case number of requests that one user action produces at the provider. (b) Name the one change that removes the exponent. (c) Your provider returns `retry-after: 300`. Describe what each official SDK does with that header, and why one of them makes things worse.

4. Walk through what happens. A stream returns 400 tokens of an expected 500. Then it goes silent forever. Your client sets `timeout=600` as a bare number. (a) Trace what happens next, and how long it takes. (b) State what the SDK does about the partial response. (c) Give the timeout configuration that would catch this in 20 seconds, and name each deadline in it.

5. Design it. Your feature calls one provider, and it must survive a burst of four times normal traffic. Write the client policy. Cover five points:
   - which signal says you are in trouble
   - why that signal, and not the error rate
   - what you do when it trips
   - how you decide to resume
   - the one metric that shows afterwards whether the policy helped

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) First sleep: 0.5 × 2⁰ = 0.5 s, times 0.75 to 1.0, so 0.375 to 0.5 s. Second sleep: 0.5 × 2¹ = 1.0 s, times the same range, so 0.75 to 1.0 s. (b) Between 1.125 and 1.5 seconds in total. (c) They cannot succeed. In 1.5 seconds, a token bucket on a 60-second window refills 1.5 / 60 = 2.5% of its capacity. All three attempts land in the same congested window. The retries add load and achieve nothing.

2. First, backoff spreads retries over time, but it does not reduce their number. Under a burst, the same volume still arrives, only later. In the simulation, it arrived while the server was still clearing its queue. It scored the same as blind retry. Second, the SDK jitter multiplier runs from 0.75 to 1.0. So it can only shrink the sleep, by at most a quarter. Full jitter draws the sleep from zero to the cap. That wide range is what spreads out clients that fail together.

3. (a) Read "retries three times" as three attempts per layer. Then the provider sees 3 × 3 × 3 = 27 requests. Read it as three retries after the first attempt. Then each layer makes four attempts, and 4 × 4 × 4 = 64. In both cases, the count is a product, not a sum. (b) Retry at one layer only. (c) The OpenAI SDK does not retry when `retry-after` is above 120 seconds. That is the safe behaviour. The Anthropic SDK ignores the header above 60 seconds and retries on its normal backoff. So `retry-after: 300` produces two retries after at most 1.5 seconds of total waiting. Both fail, and both add load during an overload that the server just reported.

4. (a) A bare number sets connect, read, write and pool all to 600 seconds. The read timeout limits the gap between chunks. So the client waits ten full minutes of silence before it raises an error. (b) Nothing. Neither SDK retries after the first byte of a stream. The retry loop ends when the response headers arrive. You must handle the partial response. (c) `httpx2.Timeout(None, connect=5.0, read=20.0, write=10.0, pool=5.0)`. Connect limits opening the socket. Read limits the silence between chunks, and it fires in this case. Write limits sending. Pool limits the wait for a free connection. The total is unlimited on purpose, because a long answer is not a failure.

5. The signal is a rolling TTFT percentile. TTFT measures queue depth, so it rises before any request fails. The error rate is a lagging indicator. It moves only when the queue is already deep. When TTFT crosses the SLO, open a circuit and drop requests. That fails fast and adds no load. Resume through a half-open state: after a cool-down, let a few probe requests through, and judge from fresh measurements. Clear the measurements taken during the overload, or the breaker stays open. In the simulation, removing that clear step cut success from 85.6% to 57.3%. Afterwards, the deciding metric is requests **sent** divided by requests offered. That ratio is the amplification factor. The success rate alone cannot separate a policy that helped from one that was lucky.

</details>

---

## References & Further Learning

Every URL below was fetched and checked on 2026-09-14. This review fetched every URL again on 2026-09-17, and each returned HTTP 200. Every SDK default was checked in the SDK source, not in a README. On 2026-09-17, this review checked the defaults again in openai 3.6.0 and anthropic 1.5.0. Where a page blocked automated fetching, or a claim could not be confirmed, the entry says so.

### Must-read before the lab

- **Exponential Backoff And Jitter, AWS Architecture Blog, Marc Brooker, 2015** — https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
  Focus on: the four pseudocode blocks and the last two graphs. This post is the source of the term that every SDK now uses. It takes ten minutes to read.
  The formula that matters is full jitter: `sleep = random_between(0, min(cap, base * 2 ** attempt))`. With 100 competing clients, it cut calls from about 2,400 to about 800.
  The post states two limits. Total work still grows with the square of the number of clients. Jittered backoff takes **longer in wall-clock time** than no backoff.
  Reading note: the four formulas are images with empty alt text. A text-scraped version of them is invented. Read the images, or run the published simulator.

- **Addressing Cascading Failures, Google SRE Book, chapter 22** — https://sre.google/sre-book/addressing-cascading-failures/
  Focus on: the bullets under "When issuing automatic retries". For this phase, that part is the useful one.
  It gives two numbers. A retry budget allows **60 retries per minute in a process**. Three layers that each make 4 attempts produce **64 attempts** from one user action.

- **Timeouts, retries, and backoff with jitter, Amazon Builders' Library** — https://web.archive.org/web/20241229100910/https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
  Focus on: the timeout method and the retry section. It is the only source with a **method** for choosing a timeout. Pick an acceptable rate of false timeouts, for example 0.1%. Then use the matching latency percentile, p99.9.
  It states two failure conditions, and both describe LLM calls. One is clients with substantial network latency. The other is services where p99.9 is close to p50.
  It also gives the five-layer example with **243x** load. It states the rule "retry at a single point in the stack". It uses the phrase **retries are selfish**.
  Access note: the original URL redirects to a site that serves no article text to a fetcher. The archive link above shows the text. Open the live page in a browser if you depend on any detail.

### Rate limits and the wire

- **OpenAI rate limits** — https://developers.openai.com/api/docs/guides/rate-limits
  Focus on: the header table, the `6m0s` reset format, and the ramp-limit rule. Read it side by side with the Anthropic page, and write the date on your notes.
  OpenAI counts cached tokens toward the token limit, and its caching FAQ says so.

- **Anthropic rate limits** — https://platform.claude.com/docs/en/api/rate-limits
  Focus on: the header list, the "Cache-aware ITPM" section, and "Reaching your spend cap".
  Anthropic excludes cache reads from the input-token limit on most models. Claude Haiku 3.5 is the documented exception. The page gives the worked example of a 2,000,000 limit that becomes an effective 10,000,000 at an 80% hit rate. It also gives the spend-cap quote in section 5.2.
  Neither page documents a limit on concurrent requests. A search of both pages for four spellings of concurrency found none.

- **OpenAI error codes** — https://developers.openai.com/api/docs/guides/error-codes
  Focus on: the 429 and 503 rows. Overload is **503** with `server_is_overloaded`. The plain rate-limit 429 row has no type and no code. The ramp-limit 429 has the code `slow_down`.

- **Anthropic errors** — https://platform.claude.com/docs/en/api/errors
  Focus on: the 429 and 529 rows. Overload is **529**, which is not a standard status. So match `>= 500`, not a list. A spend-cap 429 has **no retry-after** header, and retries cannot succeed until access resumes. Only the nested error code tells it apart.

- **The SDK retry loops, openai 3.6.0 and anthropic 1.5.0**
  Focus on: `src/openai/_base_client.py` and `src/anthropic/_base_client.py`, plus `_constants.py` in each. Read the source, not the README.
  The defaults are identical. Both make two retries, with a backoff of `min(0.5 * 2 ** n, 8.0)`. Both retry the statuses 408, 409, 429 and anything at or above 500.
  Read the jitter line twice: `jitter = 1 - 0.25 * random()`. The multiplier is between 0.75 and 1.0, so the sleep can only **shrink**. The comment above it says "plus-or-minus half a second", which does not match the code.
  The SDKs differ on `retry-after`. OpenAI does not retry above 120 seconds. Anthropic ignores the header above 60 seconds and retries anyway.
  The fact with the largest effect in production: **neither SDK retries after the first byte of a stream**. The retry loop ends when the response headers arrive, and the streaming module has no retry logic.

### Timeouts for streaming

- **httpx timeout documentation** — https://www.python-httpx.org/advanced/timeouts/
  Focus on: the definition of the read timeout. It is the maximum time to wait for **a chunk of data**. It resets on every chunk, so it is already the stall timeout that people write by hand. Both SDKs use this library through httpx2, so `httpx2.Timeout(None, connect=..., read=..., write=..., pool=...)` works with either SDK.

- **Anthropic errors, "Long requests" section** — https://platform.claude.com/docs/en/api/errors
  Focus on: the reason a total-duration timeout fails on a non-streaming call. Networks drop idle connections. The Anthropic SDK refuses a non-streaming request that it predicts will take more than ten minutes. It assumes 128,000 output tokens per hour, about 35.6 tokens per second.
  A checked absence: the OpenAI streaming guide has no guidance on timeout, idle, keepalive or stall. A search for eight terms found none. Your stall timeout must come from measurements of your own traffic.

### Adaptive concurrency, if fixed limits are not enough

- **Handling Overload, Google SRE Book, chapter 21** — https://sre.google/sre-book/handling-overload/
  Focus on: the client-side throttling algorithm and its constant. A client counts its requests and the server's accepts over the last two minutes. It limits itself when requests exceed **K times** accepts. K = 2 is the preferred value, and 1.1 is called aggressive.
  The same chapter defines criticality levels. Criticality lets you drop the right traffic, not a random tenth of it.

- **Netflix concurrency-limits** — https://github.com/Netflix/concurrency-limits
  Focus on: the Background section, which argues against fixed requests-per-second limits. The limit algorithms use latency relative to the minimum observed latency as the signal, not errors.
  One caveat: LLM latency depends heavily on output length, so total request latency is a noisy overload signal. TTFT is a better signal of queueing. No published source found tests that claim, so treat it as reasoning, not a citation.

- **Fixing retries with token buckets and circuit breakers, Marc Brooker, 2022** — https://brooker.co.za/blog/2022/02/28/retries.html
  Focus on: the simulation of a retry budget against a circuit breaker. It is the only source found that shows where each one fails. The tuning rule: add a fraction of a token per success, and spend one per retry. The deposit ratio **is** the failure rate at which retries stop. The post also notes a limit of breakers. Independent per-client breakers trip at about half the rate that the global failure rate predicts.

### Incidents in the wild

- **GitHub, "The August 17 outage and the work ahead", 20 August 2026** — https://github.blog/news-insights/company-news/the-august-17-outage-and-the-work-ahead/
  Focus on: the cause and the remediation. Errors "triggered a client-side retry loop that increased traffic during recovery", and some Copilot services took longer to recover. The remediation names all three mitigations from section 5.3.

- **GitHub availability report, August 2025** — https://github.blog/news-insights/company-news/github-availability-report-august-2025/
  Focus on: the search incident. "retry queues eventually overwhelmed the load balancers, causing failure". Up to 75% of search queries failed over nearly four hours. Throttling fixed it, not added capacity.

- **Cloudflare, deep dive into the 12 September 2025 dashboard and API outage** — https://blog.cloudflare.com/deep-dive-into-cloudflares-sept-12-dashboard-and-api-outage/
  Focus on: the two stages. A client-side loop made too many calls. Then a thundering herd followed when every client reconnected on recovery. The fix added random delays to spread retries. That is the jitter lesson, written as a remediation item.

---

## Cheatsheet — part A

```
THE THREE TIMEOUTS (a total-duration timeout is the WRONG shape for a stream)
  connect      socket never opened
  first token  server accepted and never started   ← no SDK has this
  stall/idle   stream started, then died           ← httpx `read` IS this
  total        runaway cost, last resort only
  httpx2.Timeout(None, connect=5.0, read=20.0, write=10.0, pool=5.0)
  timeout=600 is NOT a 10-minute budget. It is FOUR 10-minute idle timeouts.
  NEITHER SDK RETRIES AFTER THE FIRST BYTE OF A STREAM
  run_recorder.py checks deadlines only when a chunk arrives -> keep httpx read
  pick the number: accept 0.1% false timeouts -> use your own p99.9

RATE LIMITS (the two providers agree on almost nothing)
                        OpenAI                  Anthropic
  header prefix         x-ratelimit-            anthropic-ratelimit-
  reset format          duration "6m0s"         RFC 3339 timestamp
  remaining             exact                   rounded to nearest 1000
  CACHED TOKENS COUNT   YES                     NO (Haiku 3.5 is the exception)
  overload status       503                     529 (non-standard!)
  -> on Anthropic, caching is a CAPACITY decision: 2M ITPM at 80% hit
     = 10M effective input tokens/minute
  the 429 you must NOT retry: Anthropic's spend cap arrives as an ordinary
     rate_limit_error with NO retry-after. Branch on the nested code.
  OpenAI ramp limit: above 1M TPM, grow at most 50% per 15 min (code slow_down)
  match >= 500, never a list, or you miss 529

SDK DEFAULTS (openai 3.6.0 and anthropic 1.5.0, identical)
  max_retries 2 (3 attempts) | statuses 408,409,429,>=500
  backoff  min(0.5 * 2^n, 8.0)
  jitter   1 - 0.25*random()  -> multiplier 0.75..1.0, can ONLY SHRINK
  total added delay 1.125 to 1.5 s = 2.5% of a 60 s token-bucket window
  full jitter for comparison: random_between(0, min(cap, base*2^n))
  retry-after: OpenAI refuses above 120 s; Anthropic IGNORES it above 60 s

RETRIES UNDER LOAD (measured, burst to 2.5x for 8s, mean of 5 runs)
  policy     sent   amp    success  wasted  recover
  none       1229  1.00x    89.0%     135   18.2s
  blind      3855  3.14x    22.7%    3576   never
  backoff    3896  3.18x    22.7%    3617   never    <- NOT better than blind
  health     1060  0.86x    85.6%       8    5.2s
  AT 30% LOAD ALL FOUR ARE IDENTICAL (99.7%). That is why this bug ships.
  amplification is a PRODUCT across layers: 3 layers x 4 attempts = 4^3 = 64
  RETRY AT ONE LAYER ONLY

WHAT WORKS, in order
  1. retry at a single layer          removes the exponent
  2. a retry budget                   e.g. 60 retries/min/process, or a token
                                      bucket where the deposit ratio IS the
                                      failure rate at which retries stop
  3. full jitter, not the SDK's
  4. a health signal that STOPS you sending   <- the only one that helped

THE HEALTH SIGNAL
  the signal is TTFT, not the error rate. TTFT rises FIRST because TTFT is
  queue depth. Errors are a lagging indicator.
  circuit breaker:
    clear the stale signal when it opens   without it: 57.3% success, 30.1 s
    a half-open probe state                little effect in this simulation
  the self-test catches NEITHER removal
  independent per-client breakers trip at ~half the expected global rate

THE COMMANDS
  run_recorder.py --self-test              the three deadlines, offline
  health_signal.py --self-test             the simulation, offline
  health_signal.py                         four policies under a burst
  health_signal.py --sweep                 why it is invisible at light load
```

Part B takes the records that this client produces. It turns them into a promise you can be held to, and an alert that fires at the right time.

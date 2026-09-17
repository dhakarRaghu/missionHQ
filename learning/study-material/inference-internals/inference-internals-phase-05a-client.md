# Phase 5A — The client under stress

Phases 1 to 4 measured a system that was working. This phase is about the hours when it is not, and about the fact that your client's own behaviour decides whether a bad minute becomes a bad afternoon.

Phase 0 told Story 2: p99 latency spiked, the team added short timeouts and retries, and the incident got worse. That story has been waiting five phases for its fix. It arrives here, and the measured result is harsher than the story was.

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

```
cd ~/Desktop/project/code/study-material/inference-internals/code
pip install -e .
python phase05_operations/run_recorder.py --self-test
python phase05_operations/health_signal.py --self-test
```

Both must pass before you start. Everything in this phase is a simulation or a measurement, so the arithmetic gets tested first.

---

## 5.1 — Streaming and the three timeouts (your one timeout is the wrong one)

Why this matters: almost every LLM client has one timeout, and it is a total-duration timeout. That is the wrong shape for a streaming response, and getting it wrong is what turns a slow minute into an outage.

**The problem in one line.** A long answer is not a failure. A stream that stopped is. A total-duration timeout cannot tell those apart.

Here are the three things you actually want to bound, and they are different:

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

Both official Python SDKs run on httpx, and httpx's `read` timeout is **already a stall timeout**. Its documentation says so:

> The read timeout specifies the maximum duration to wait for **a chunk of data** to be received.

It resets on every chunk. For a server-sent-event stream, every event is a chunk. So the stall timeout you wanted already exists, and passing a single number hides it:

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

The same object works for both providers, and both accept it per request through `with_options(timeout=...)`.

**Neither SDK has a first-token timeout.** No parameter exists. The workable pattern is to run the first part of your consume loop under an outer deadline sized for time to first token, cancel if no content event arrives, then continue consuming without it. `run_recorder.py` implements the three deadlines directly in its consume loop for the same reason.

That pattern is engineering reasoning, not a documented recommendation. No published source describes it.

```
  WHICH DEADLINE FIRES, ON A TIMELINE

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

There is a published method for choosing a timeout, and it is better than guessing. Decide the rate of false timeouts you will accept, then read the matching percentile off your own measured latency. One large engineering organisation states its practice as accepting **0.1%** false timeouts and therefore using the **p99.9** latency of the downstream call.

Two conditions where that method fails, both stated by the same source: when clients sit across the public internet with high variable latency, and when the service has tight latency bounds so p99.9 sits close to p50.

You already have the data. Phase 1 measured TTFT, and `run_recorder.py` is now writing it per request.

### What the vendors say about long requests

One provider's SDK refuses to make a non-streaming request that it predicts will take more than ten minutes. The check is in its source, and the arithmetic it uses is worth knowing:

```
expected_time = 3600 seconds * max_tokens / 128,000
```

That is an assumption of **128,000 output tokens per hour**, or about **35.6 output tokens per second**. Exceed ten minutes and it raises an error telling you to stream. Passing `stream=True` or setting your own timeout disables the check.

The same provider's documentation gives the reason plainly: some networks drop idle connections, so a long non-streaming request can fail without ever returning anything. Streaming keeps the connection busy.

**Heartbeats exist but you cannot size a timeout from them.** One provider documents `ping` events in its stream and does not document how often they arrive. The other publishes no streaming timeout guidance at all. I searched its streaming guide for eight relevant terms including "timeout", "idle", "keepalive" and "stall" and found zero matches. So your stall timeout has to come from measuring your own traffic, not from the docs.

### The failure the SDKs will not save you from

This is the most important paragraph in the section.

**Neither SDK retries anything after the first byte of a stream.** The retry loop lives in the request method and ends when the response headers arrive successfully. The streaming module contains no retry logic at all.

So a stream that dies at token 400 of 500 is your problem, not the SDK's. Your options are to fail the request, to return the partial answer and say so, or to continue it with a second call. One provider documents a continuation procedure, and it differs by model generation: older models take the partial text back as an assistant message, newer ones want a user message instructing the model to continue.

**The sentence to remember:** the read timeout is a stall timeout that resets on every chunk, so name your deadlines separately instead of passing one number that silently becomes four.

**The trap:** `timeout=600` looks like a ten-minute budget and is not. It is four independent ten-minute idle timeouts, and a dead stream will hang for the full ten minutes.

**Try this now:** run `python phase05_operations/run_recorder.py --self-test` and find the check named "a stall is detected". Then read `record_stream` and note that it raises a `Timeout` carrying **which** deadline fired. "It timed out" is not a diagnosis.
---

## 5.2 — Rate limits (read the headers, they disagree with each other)

Why this matters: a 429 is not a failure to retry through. It is the server telling you its capacity, in headers most clients throw away. Phase 3 taught you to read the `usage` object. This section is the same lesson applied to the response headers.

### The two providers do not agree on anything except the status code

All of this was read from the provider documentation on 2026-09-14. It changes, so re-check and date your own notes.

```
┌──────────────────────┬─────────────────────────┬──────────────────────────┐
│                      │ Provider A              │ Provider B               │
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

**The cached-token row is the biggest practical difference in this whole phase.** On one provider, Phase 3's caching work buys you money only. On the other it buys you money *and throughput*, because cache reads do not consume your input-token budget. That provider's own worked example: a 2,000,000 input-token-per-minute limit at an 80% cache hit rate processes an effective **10,000,000** input tokens per minute.

So on that provider, the prompt layout work from Phase 3 section 3.2 is also a capacity decision. There is one documented exception, a smaller model where cache reads do count, which is exactly the kind of footnote that breaks a capacity plan.

**The reset-format row will cost you an afternoon.** One provider returns a Go-style duration, `6m0s`, which is neither a number nor a timestamp. The other returns an RFC 3339 timestamp. Code that parses one will silently misparse the other, and a wrong reset time produces either a stampede or a stall.

### The overload status code is not 503 on both

One provider returns **503** with a code meaning the server is overloaded. The other returns **529**, which is not a standard HTTP status at all.

```python
# WRONG: enumerating the statuses you know about misses 529 entirely.
if status in (500, 502, 503, 504):
    retryable = True

# RIGHT: treat any 5xx as retryable, and branch on the code when you need to.
retryable = status >= 500 or status in (408, 409, 429)
```

Both SDKs happen to get this right, because they retry on any status of 500 or above.

### The 429 that you must not retry

One provider returns a 429 with the ordinary rate-limit error type when you hit a **spend cap**. Its documentation is blunt about the consequence:

> The error type is `rate_limit_error`, the same as for a rate limit, but the response has no `retry-after` header. Retrying, including the SDKs' automatic retries, fails until access resumes.

So a spend cap looks exactly like congestion, and every retry you send is wasted. The only discriminator is a nested error code. If Phase 3's budget guard fires and this 429 appears at the same time, you have found your cause.

There is a second documentation gap worth knowing. On the other provider, the plain rate-limit 429 row publishes **no error type and no error code**, unlike every other row on the same page. So there is no documented machine-readable way to tell an ordinary rate limit from anything else that returns 429.

### Ramp limits are a third kind of limit

One provider enforces how fast you may *grow*, separately from how much you may send:

> As a rule of thumb, once your traffic reaches 1 million input tokens per minute, increase it by no more than 50% every 15 minutes.

Exceeding the ramp returns a 429 with a distinct code, and the documentation says plainly that this can happen **while you are inside both your request and token limits**. If you are launching a feature and plan to move traffic over in one step, this is the limit you will hit first.

### What to do with the headers

Three things, in order of value:

1. **Record them on every response.** `remaining` and `reset` belong in the run record next to the token counts. A capacity problem is then visible before it becomes a 429.
2. **Slow down before you are told to.** When remaining tokens fall below a fraction of the limit, reduce concurrency. That is cheaper than being rejected and retrying.
3. **Honour `retry-after` yourself.** Section 5.3 shows why you cannot rely on the SDK to do it.

**The sentence to remember:** a 429 carries the server's own capacity report in its headers, and the two providers disagree on the dimensions, the format, the accuracy, and whether your cache hits count.

**The trap:** parsing the reset header as a number. One provider sends `6m0s` and the other sends a timestamp. Neither is an integer.

**Try this now:** find where your code handles a 429. Check whether it reads any header at all, and whether it would survive a 529.
---

## 5.3 — Retries (why yours make it worse, measured)

Why this matters: Phase 0 told Story 2. p99 latency spiked, the team added short timeouts and retries, and the incident got worse. Phase 0 promised the fix would arrive here. This is that section, and the result is stronger than the story was.

### Run it

```
python phase05_operations/health_signal.py
```

A server that handles 20 requests per second, normal traffic at 12, and an eight-second burst to 30. Four client policies, mean of five runs:

```
┌──────────┬──────────┬───────────┬─────────┬─────────┬──────────┬──────────┐
│ policy   │ sent     │ amplifier │ success │ wasted  │ p99 (s)  │ recover  │
├──────────┼──────────┼───────────┼─────────┼─────────┼──────────┼──────────┤
│ none     │     1229 │     1.00x │  89.0%  │     135 │     3.77 │    18.2s │
│ blind    │     3855 │     3.14x │  22.7%  │    3576 │     3.91 │    never │
│ backoff  │     3896 │     3.18x │  22.7%  │    3617 │     3.91 │    never │
│ health   │     1060 │     0.86x │  85.6%  │       8 │     1.69 │     5.2s │
└──────────┴──────────┴───────────┴─────────┴─────────┴──────────┴──────────┘
```

Three results, and two of them surprise people.

**Blind retry turned an 89% day into a 22.7% outage.** Doing nothing was four times better.

**Exponential backoff with jitter did not help.** It scored the same as blind retry, and sent slightly *more*. Spreading retries across time does not reduce their number, and delayed retries can outlive immediate ones by landing later in the drain window.

**The health signal recovered in 5.2 seconds while both retry policies never recovered inside the run**, and it wasted 8 requests against 3,576.

### Why the loop closes

Most demonstrations of retries model the server as a fixed delay, which makes retries look free. They are not free, because your retries are the load:

```
    more retries  ->  deeper queue  ->  higher TTFT  ->  more timeouts
          ^                                                    |
          +----------------------------------------------------+
```

Two published amplification numbers show how fast this compounds when retries stack across layers. One large engineering organisation documents a three-layer stack with three retries each producing **4³ = 64** attempts on the database from one user action. Another documents a five-deep stack producing **3⁵ = 243x** the load. ```

```
  ONE USER ACTION, THREE LAYERS, THREE RETRIES EACH

  user
   └── frontend          4 attempts
        └── backend           4 attempts each
             └── database          4 attempts each
                  ═══════════════════════════════
                  4 x 4 x 4  =  64 requests

  the exponent is the NUMBER OF LAYERS, not the retry count
  five layers at three attempts each: 3^5 = 243x
```

Their conclusion is the same, and it is the simplest rule in this phase:

> retry at a single point in the stack

The second organisation offers the best one-line framing of the whole problem:

> retries are selfish

### Your SDK's defaults are weaker than you think

I read both official Python SDKs at their released tags. The defaults are identical and they are not what people assume.

```
  max retries          2, so three attempts
  retried statuses     408, 409, 429, and anything >= 500
  backoff              min(0.5 * 2^n, 8.0) seconds
  jitter               multiplier = 1 - 0.25 * random()
```

Look at that jitter line. The multiplier lands in the range 0.75 to 1.0, so the sleep can only ever **shrink**, by at most a quarter. Compare it with the published full-jitter formula, which draws uniformly across the whole interval:

```
  full jitter   sleep = random_between(0, min(cap, base * 2^attempt))
  the SDKs      sleep = (0.75 .. 1.0) * min(cap, base * 2^attempt)
```

With the defaults, the two retry sleeps total under 1.5 seconds. That is far too little for a token bucket to refill, and far too little decorrelation to break a synchronised herd.

**And the two SDKs disagree about `retry-after` in a way that matters.** One refuses to retry at all when the header asks for more than 120 seconds. The other **ignores the header** above its own 60-second bound and retries anyway on the normal sub-second backoff. So a `retry-after: 300` produces two doomed retries inside the first second on that SDK, both of which add load.

If a long `retry-after` matters to your system, handle it yourself. `max_retries=0` and your own policy is a legitimate choice.

### What actually works

Four mechanisms, in the order I would add them.

**1. Retry at one layer only.** Free, and it removes the exponent.

**2. A retry budget.** Cap retries as a share of traffic rather than per request. One published example allows **60 retries per minute per process**, and refuses beyond that. A related published design deposits a fraction of a token on each success and spends one per retry, so that depositing 0.1 tokens per success makes retries fall away above a 10% failure rate. The deposit ratio *is* the crossover point, which is a clean way to choose it.

**3. Full jitter, not the SDK's.** The published simulation at 100 competing clients shows roughly 800 calls with full jitter against roughly 2,400 with none. Note the honest cost in the same source: jittered backoff takes longer in wall-clock time than not backing off, and total work still grows with the square of the client count. Jitter improves the constant, not the exponent.

**4. A health signal that stops you sending.** This is the one Phase 0 promised, and the table above is why it is last on the list and first in value.

### The signal is TTFT, not the error rate

Errors are a lagging indicator. By the time requests fail, the queue is already deep. TTFT rises first, because TTFT *is* queue depth, which is exactly what Phase 2 section 2.1 showed.

So the policy is: track a rolling TTFT percentile; when it crosses your SLO, stop sending and shed instead. The simulation implements a circuit breaker on that signal.

**Two design details in the code that are not optional**, and I only found them by watching the simulation behave badly.

First, **the breaker must discard its signal when it opens.** Without that it latches: after the cool-down it re-reads measurements taken while the server was overloaded, concludes the server is still sick, and re-opens forever. In the first version of this simulation that bug alone dropped the health policy to a 14% success rate.

Second, **it needs a half-open state.** After the cool-down, let a few probe requests through and judge from those. That is what a fresh measurement means in practice.

```python
if now < circuit_open_until:
    shed(); return                      # cheap, immediate, no server load
if circuit_open_until > 0 and probes < probe_count:
    probes += 1; send()                 # HALF-OPEN: test the water
    return
if p95(recent_ttft) > ttft_slo:
    circuit_open_until = now + cool_down
    recent_ttft.clear()                 # the stale signal MUST go
    probes = 0
    shed()
```

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

A published comparison notes the weakness of breakers honestly: each client trips independently, so a fleet of them trips at roughly half the rate you would expect from the global failure rate. That is an argument for a budget *and* a breaker, not for one alone.

### Why this bug reaches production

Run the sweep:

```
python phase05_operations/health_signal.py --sweep
```

At 30% of capacity, all four policies score 99.7% and are indistinguishable. The defect is invisible in every test that does not overload the server. That is the whole explanation for why mature teams still ship it.

### It happens to real systems

Three public incident reports describe this mechanism.

One large developer platform's 2026 outage report names the cause directly: errors "triggered a client-side retry loop that increased traffic during recovery", with its AI assistant among the slowest services to recover. Its remediation names all three mitigations above: retry limits, retry budgets, and variable timeouts.

The same platform's earlier report on a search incident is blunter: "retry queues eventually overwhelmed the load balancers, causing failure". Up to 75% of queries failed over nearly four hours, and mitigation came from throttling rather than from adding capacity.

A large network provider's 2025 dashboard outage documents the two-stage version: a client-side loop generating excess calls, then a thundering herd when everything reconnected at once on recovery. Its fix was to add random delays to spread retries.

**The sentence to remember:** retries are load, so the only policy that helps under overload is one that sends less, and TTFT tells you to stop before the errors do.

**The trap:** believing exponential backoff is the fix. It scored identically to blind retry here, and your SDK's jitter can only shrink the delay by a quarter.

**Try this now:** run `python phase05_operations/health_signal.py --sweep` and compare the first table with the third. Then find your own client's `max_retries` and decide whether the default of 2, with under 1.5 seconds of total backoff, is what you want.
---

## 🧪 Hands-on lab — part A

Five of seven exercises are offline. E6 and E7 need an API key and cost under $0.05.

**Live-run status:** every offline script was executed on the author's machine on 2026-09-14 and the outputs printed above are real. No API key was available, so E6 and E7 were not executed. Their flag names and header names were verified against the provider documentation and the SDK source at released tags.

- [ ] **E1 (offline).** Read the three deadlines.
  - Run: `python phase05_operations/run_recorder.py --self-test`
  - Expected: 17 checks pass, including "a stall is detected".
  - Then open `record_stream` and find the three deadline checks. Note that the exception carries **which** deadline fired.
  - Teaches: "it timed out" is not a diagnosis.

- [ ] **E2 (offline).** Verify the retry simulation before you believe it.
  - Run: `python phase05_operations/health_signal.py --self-test`
  - Expected: 9 checks pass, including "backoff is not meaningfully better than blind retry" and "doing nothing beats both retry policies here".
  - Teaches: a simulation you have not tested is a story.

- [ ] **E3 (offline).** Watch retries turn a spike into an outage.
  - Run: `python phase05_operations/health_signal.py`
  - Expected: no-retry succeeds on about 89%, blind retry on about 22.7% while sending 3.14x the requests, and the health signal on about 85.6% while sending 0.86x.
  - Write down the wasted column for each. Blind wastes about 3,576 requests; the health signal wastes about 8.
  - Teaches: retries are load.

- [ ] **E4 (break-it, offline).** Find out why this bug ships.
  - Run: `python phase05_operations/health_signal.py --sweep`
  - Expected: in the first table, at 30% of capacity, all four policies score about 99.7% and are indistinguishable.
  - Teaches: the defect is invisible in any test that does not overload the server. That is the whole explanation.

- [ ] **E5 (offline).** Audit your own client.
  - Find the `max_retries` and `timeout` your code passes to its LLM client. If it passes neither, find the SDK defaults.
  - Answer three questions. How many total attempts does one call make? What is the total added delay across those retries? Does a single `timeout=N` in your code set one deadline or four?
  - Teaches: the defaults are two retries with under 1.5 seconds of total backoff, which is far less protection than most people assume.

- [ ] **E6 (UNVERIFIED against a live provider).** Give a stream the wrong timeout, then the right one.
  - Make a streaming call with `timeout=5` as a bare number and ask for a long answer. Then make the same call with `httpx2.Timeout(None, connect=5.0, read=20.0, write=10.0, pool=5.0)`.
  - Expected: the first can fail on a perfectly healthy long answer. The second does not, and still catches a genuinely dead stream.
  - Costs at most: about $0.02.
  - Teaches: a single number sets four independent idle timeouts, not one total budget.

- [ ] **E7 (break-it, UNVERIFIED against a live provider).** Provoke a 429 and read what it tells you.
  - Fire requests concurrently until one is rejected. Print every response header whose name contains `ratelimit` or `retry`.
  - Expected: your provider's limit, remaining and reset values. Check the reset **format**: one provider sends a duration such as `6m0s`, the other an RFC 3339 timestamp.
  - Then check whether your code reads any of them today.
  - Teaches: a 429 carries the server's own capacity report, and most clients throw it away.
---

## 🔍 Check it yourself

1. Open `record_stream` in `run_recorder.py`. It takes an iterable of tuples rather than an SDK client. Explain what that buys, and name the specific thing it lets the self-test do that a client-shaped function could not.
2. In `health_signal.py`, find `Provider.submit`. The line that sets `req["ttft"]` uses the queue depth **at admission**. Explain in one sentence why that single line is what makes the whole simulation a closed loop rather than a fixed-delay model.
3. In the same file, find where the circuit breaker calls `recent_ttft.clear()`. Describe the failure that happens if you delete that line, and say which self-test would catch it.
4. In your own code: find the client construction. Does it pass a timeout? If so, is it a bare number? Work out how many independent deadlines that number actually sets.

---

## ✅ Checkpoint 5A — answer in your own words

1. Show the math. Your SDK is on its defaults: two retries, backoff of `min(0.5 × 2ⁿ, 8)` seconds, and a jitter multiplier drawn from 0.75 to 1.0. (a) Compute the two sleeps, minimum and maximum. (b) Compute the total added delay across one failed call. (c) Your provider's rate limit resets on a 60-second window. State whether those retries can succeed, and why.

2. A colleague says: "We added exponential backoff with jitter, so the retry storm is fixed." Using section 5.3, give two reasons that may be false. One reason is about what backoff does and does not change, and one is about the specific jitter your SDK implements.

3. This is broken. Your service calls an LLM through a gateway, which calls the provider. Each layer retries three times. (a) Compute the worst-case number of requests one user action produces at the provider. (b) Name the single change that removes the exponent. (c) Your provider returns `retry-after: 300`. Describe what each of the two official SDKs does with that header, and why one of them makes things worse.

4. Walk me through what happens. A stream returns 400 tokens of an expected 500 and then goes silent forever. Your client sets `timeout=600` as a bare number. (a) Trace what happens next and how long it takes. (b) State what the SDK does about the partial response. (c) Give the timeout configuration that would have caught this in 20 seconds, and name each deadline in it.

5. Design it. Your feature calls one provider and you must survive a burst of four times normal traffic. Write the client policy. Cover: which signal decides you are in trouble, why that signal rather than the error rate, what you do when it trips, how you decide to resume, and the one metric that tells you afterwards whether the policy helped.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) First sleep: 0.5 × 2⁰ = 0.5, times 0.75 to 1.0, so 0.375 to 0.5 s. Second: 0.5 × 2¹ = 1.0, times the same range, so 0.75 to 1.0 s. (b) Between 1.125 and 1.5 seconds total. (c) They cannot succeed. A token bucket refilling on a 60-second window has released roughly 2% of its capacity in 1.5 seconds. All three attempts land inside the same congested window, so the retries add load and produce nothing.

2. First, backoff spreads retries in time but does not reduce their number. Under a burst, the same volume still arrives, just later, and in the simulation it landed during the drain and scored the same as blind retry. Second, the SDKs' jitter multiplier runs from 0.75 to 1.0, so it can only shrink the sleep by at most a quarter. Published full jitter draws uniformly from zero to the cap, which is what actually decorrelates a synchronised herd.

3. (a) Three attempts at each of three layers gives 3³ = 27 requests at the provider from one user action; if each layer retries three times on top of the original attempt, it is 4³ = 64. Either way it is the product, not the sum. (b) Retry at a single layer only. (c) One SDK refuses to retry at all when `retry-after` exceeds 120 seconds, which is the safe behaviour. The other ignores the header above its own 60-second bound and retries anyway on the normal sub-second backoff, so a `retry-after: 300` produces two doomed retries inside the first second, both adding load during an overload the server just told you about.

4. (a) A bare number sets connect, read, write and pool all to 600 seconds. The read timeout is the gap between chunks, so the client waits a full ten minutes of silence before raising. (b) Nothing. Neither SDK retries after the first byte of a stream; the retry loop ends when response headers arrive. The partial response is yours to handle. (c) `httpx2.Timeout(None, connect=5.0, read=20.0, write=10.0, pool=5.0)`. Connect bounds opening the socket, read bounds the silence between chunks and is the one that fires here, write bounds sending, pool bounds waiting for a connection, and the total is deliberately unbounded because a long answer is not a failure.

5. The signal is a rolling TTFT percentile, because TTFT is queue depth and therefore rises before any request fails; an error rate is a lagging indicator that only moves once the queue is already deep. When it crosses the SLO, open a circuit and shed, which fails fast and cheaply rather than adding load. Resume through a half-open state: after a cool-down, let a small number of probe requests through and judge from those, having discarded the measurements taken while the server was overloaded, or the breaker latches open permanently. Afterwards the metric that settles it is requests **sent** against requests offered, the amplification factor. Success rate alone cannot distinguish a policy that helped from one that got lucky.

</details>
---

## References & Further Learning

Every URL was fetched and checked on 2026-09-14, and every SDK default was verified by reading source at a released tag rather than a README. Where a page blocked automated fetching or a claim could not be confirmed, the entry says so.

### Must-read before the lab

**Exponential Backoff And Jitter** — AWS Architecture Blog, Marc Brooker, 2015.
https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
The origin of the term every SDK now cites. Ten minutes. Focus on the four pseudocode blocks and the last two graphs.
The formula that matters, full jitter: `sleep = random_between(0, min(cap, base * 2 ** attempt))`. At 100 competing clients it cut calls from roughly 2,400 to roughly 800.
Two honest limits stated in the same post: total work still grows with the square of the client count, and jittered backoff takes **longer in wall-clock time** than not backing off at all.
Reading note: the four formulas are images with empty alt text. Any text-scraped version of them is invented. Read the images or run the published simulator.

**Addressing Cascading Failures** — Google SRE Book, chapter 22.
https://sre.google/sre-book/addressing-cascading-failures/
Read the five bullets under "When issuing automatic retries" and stop. That is the whole chapter's value here.
The two numbers: a retry budget of **60 retries per minute in a process**, and the amplification arithmetic showing three layers each retrying producing **64 attempts** from one user action.

**Timeouts, retries, and backoff with jitter** — Amazon Builders' Library.
https://web.archive.org/web/20241229100910/https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
The only source with a **method** for choosing a timeout rather than a rule of thumb: pick an acceptable rate of false timeouts, for example 0.1%, then use the matching latency percentile, p99.9. It states its own two failure conditions, and both describe LLM calls: clients over the public internet, and services where p99.9 sits close to p50.
It also gives the deeper amplification example, five layers at three retries producing **243x** load, and the best one-line framing in the literature: **retries are selfish**.
Access note: the canonical URL redirects to a site that serves no article text to a fetcher. The Wayback link above renders. Open the live page in a browser if any of it is load-bearing.

### Rate limits and the wire

**Provider rate limit documentation** — read both, side by side, and write the date on your notes.
https://developers.openai.com/api/docs/guides/rate-limits and https://platform.claude.com/docs/en/api/rate-limits
What to extract: the exact header names, the reset **format**, and whether cached tokens count. One provider counts cached tokens toward the token limit and states so in its caching FAQ; the other excludes cache reads from the input-token limit on most models, with one documented exception, and publishes the worked example of a 2,000,000 limit becoming an effective 10,000,000 at an 80% hit rate.
Also note what neither documents: a concurrent-request limit. I searched both pages for four spellings of concurrency and found none.

**Error codes** — https://developers.openai.com/api/docs/guides/error-codes and https://platform.claude.com/docs/en/api/errors
Two things to take. Overload is **503** on one provider and **529** on the other, and 529 is not a standard status, so enumerate `>= 500` rather than a list. And one provider's spend-cap rejection arrives as an ordinary rate-limit 429 with **no retry-after**, where retrying cannot succeed until access resumes; the only discriminator is a nested error code.

**The SDK retry loops** — read the source, not the README.
`src/openai/_base_client.py` and `src/anthropic/_base_client.py`, plus `_constants.py` in each, at their released tags.
The defaults are identical: two retries, statuses 408, 409, 429 and anything at or above 500, backoff `min(0.5 * 2 ** n, 8.0)`.
The line worth reading twice is the jitter: `jitter = 1 - 0.25 * random()`. The multiplier lands between 0.75 and 1.0, so the sleep can only **shrink**. The in-code comment describing it does not match the code.
The two SDKs also diverge on `retry-after`: one refuses to retry above 120 seconds, the other ignores the header above its own bound and retries anyway.
And the fact with the largest operational consequence: **neither retries after the first byte of a stream**. The retry loop ends when response headers arrive, and the streaming module contains no retry logic at all.

### Timeouts for streaming

**httpx timeout documentation** — https://www.python-httpx.org/advanced/timeouts/
One sentence is the whole section: the read timeout is the maximum duration to wait for **a chunk of data**. It resets on every chunk, so it is already the stall timeout people hand-roll. Both SDKs run on this library, so `httpx2.Timeout(None, connect=..., read=..., write=..., pool=...)` works with either.

**Long requests** — https://platform.claude.com/docs/en/api/errors
Read the "Long requests" section for the reason a total-duration timeout fails on a non-streaming call: networks drop idle connections. The same provider's SDK refuses a non-streaming request it predicts will exceed ten minutes, using an assumption of 128,000 output tokens per hour, about 35.6 tokens per second.
Verified absence worth knowing: the other provider's streaming guide contains no timeout, idle, keepalive or stall guidance at all. I searched it for eight terms and found none. Your stall timeout must come from measuring your own traffic.

### Adaptive concurrency, if fixed limits are not enough

**Handling Overload** — Google SRE Book, chapter 21. https://sre.google/sre-book/handling-overload/
The client-side throttling algorithm with its constant: a client tracks requests and accepts over the last two minutes and self-regulates when requests exceed **K times** accepts, with K = 2 preferred and 1.1 described as aggressive.
The same chapter defines criticality levels, which is the mechanism that lets you shed the right traffic rather than a random tenth of it.

**Netflix concurrency-limits** — https://github.com/Netflix/concurrency-limits
Read the Background section for the argument against fixed request-per-second limits, and the limit algorithms for the signal: latency relative to the minimum observed latency, not errors.
One caveat to carry: LLM latency depends heavily on output length, so total request latency is a noisy overload signal. Time to first token is the better proxy for queueing. I found no published source testing that claim, so treat it as reasoning rather than a citation.

**Fixing retries with token buckets and circuit breakers** — Marc Brooker, 2022.
https://brooker.co.za/blog/2022/02/28/retries.html
The only source that simulates a retry budget against a circuit breaker and shows where each fails. The tuning insight: deposit a fraction of a token per success and spend one per retry, and the deposit ratio **is** the failure rate at which retries fall away. It also notes that independent per-client breakers trip at roughly half the rate you would predict from the global failure rate.

### Incidents in the wild

**A 2026 developer-platform outage report** — https://github.blog/news-insights/company-news/the-august-17-outage-and-the-work-ahead/
Names the mechanism directly: errors "triggered a client-side retry loop that increased traffic during recovery", with its AI assistant among the slowest services to recover. The remediation names all three mitigations from section 5.3.

**The same platform's August 2025 availability report** — https://github.blog/news-insights/company-news/github-availability-report-august-2025/
Blunter: "retry queues eventually overwhelmed the load balancers, causing failure". Up to 75% of search queries failed over nearly four hours, and mitigation came from throttling rather than adding capacity.

**A 2025 dashboard outage** — https://blog.cloudflare.com/deep-dive-into-cloudflares-sept-12-dashboard-and-api-outage/
The clearest published description of the two-stage version: a client-side loop generating excess calls, then a thundering herd when everything reconnected on recovery. The fix was random delays to spread retries, which is the jitter lesson arriving as a remediation item.

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
  pick the number: accept 0.1% false timeouts -> use your own p99.9

RATE LIMITS (the two providers agree on almost nothing)
                        provider A              provider B
  header prefix         x-ratelimit-            anthropic-ratelimit-
  reset format          duration "6m0s"         RFC 3339 timestamp
  remaining             exact                   rounded to nearest 1000
  CACHED TOKENS COUNT   YES                     NO (most models)
  overload status       503                     529 (non-standard!)
  -> on provider B, caching is a CAPACITY decision: 2M ITPM at 80% hit
     = 10M effective input tokens/minute
  the 429 you must NOT retry: a spend cap arrives as an ordinary
     rate_limit_error with NO retry-after. Branch on the nested code.
  match >= 500, never a list, or you miss 529

SDK DEFAULTS (verified in source, both SDKs identical)
  max_retries 2 (3 attempts) | statuses 408,409,429,>=500
  backoff  min(0.5 * 2^n, 8.0)
  jitter   1 - 0.25*random()  -> multiplier 0.75..1.0, can ONLY SHRINK
  total added delay under 1.5s. A 60s token bucket refills ~2% of that.
  full jitter for comparison: random_between(0, min(cap, base*2^n))
  retry-after: one SDK refuses above 120s; the other IGNORES it and retries

RETRIES UNDER LOAD (measured, burst to 2.5x for 8s)
  policy     sent   amp    success  wasted  recover
  none       1229  1.00x    89.0%     135   18.2s
  blind      3855  3.14x    22.7%    3576   never
  backoff    3896  3.18x    22.7%    3617   never    <- NOT better than blind
  health     1060  0.86x    85.6%       8    5.2s
  AT 30% LOAD ALL FOUR ARE IDENTICAL. That is why this bug ships.
  amplification is a PRODUCT across layers: 3 layers x 3 retries = 64 attempts
  RETRY AT ONE LAYER ONLY

WHAT ACTUALLY WORKS, in order
  1. retry at a single layer          removes the exponent
  2. a retry budget                   e.g. 60 retries/min/process, or a token
                                      bucket where the deposit ratio IS the
                                      failure rate at which retries stop
  3. full jitter, not the SDK's
  4. a health signal that STOPS you sending   <- the only one that helped

THE HEALTH SIGNAL
  the signal is TTFT, not the error rate. TTFT rises FIRST because TTFT is
  queue depth. Errors are a lagging indicator.
  circuit breaker needs BOTH:
    clear the stale signal when it opens   (or it latches open forever)
    a half-open probe state                (judge from fresh measurements)
  independent per-client breakers trip at ~half the expected global rate

THE COMMANDS
  run_recorder.py --self-test              the three deadlines, offline
  health_signal.py --self-test             the simulation, offline
  health_signal.py                         four policies under a burst
  health_signal.py --sweep                 why it is invisible at light load
```

Part B takes the records this client produces and turns them into a promise you can be held to, and an alert that fires at the right time.

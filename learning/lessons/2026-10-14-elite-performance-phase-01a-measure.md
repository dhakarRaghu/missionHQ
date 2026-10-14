You build a small service, point a load tool at it, and the tool prints p99 equals 50.6 ms. So no user waited more than about 50 ms. Except the service stopped for 3 seconds in the middle of the run, and a second tool, driving the same service through the same stop, printed p99 equals 2.73 s. Both tools ran correctly and both reports are internally consistent. One of them described your users, and one of them did not, and nothing in either report says which.

The difference is not the service and not the maths of percentiles. It is what each tool was willing to write down when a request took seconds instead of milliseconds, and what the run was long enough to see. This phase takes one load test of one 10 ms service on your laptop, with one 3-second stop in the middle, and reads its report line by line: whether the tool that drove it could have seen a stall at all, how many samples sit above each percentile it prints, whether 25 seconds at that load is enough, and what was genuinely slow in the first seconds. After it, you can look at any single run and say which of its numbers you would defend in a review.

This lesson teaches five ideas. They are listed here so you can see where the lesson is going. They will read more clearly once each has been explained below, so come back to this list at the end.

- A closed-loop generator's send rate is coupled to the service's latency, so a stall is recorded once, not once per delayed request, and its p99 describes the healthy seconds. Decide whether a given load tool can see stalls at all, and reject a clean report from a tool that cannot.
- A reported percentile rests on the samples above it, roughly n·(1−q) of them, so below about ten the percentile should not be reported and below a computable floor no interval for it exists. State, for any run size, which percentiles he can defend and how large a run a p99.9 target needs.
- Near the knee, a short run understates steady-state p99, more so the busier the service is, because the deep-queue excursions that set the tail are rarer than the run. Decide how long a run must be at a given utilisation, and explain why two identical short runs can disagree by a factor of 4 without anyone being wrong.
- In a fresh CPython service the interpreter is warm after about one request, because the specialising interpreter rewrites an instruction the second time it executes; the cold state that costs users is imports, connection pools, caches and the empty queue. Choose what to warm before a measurement, keep the first seconds instead of discarding them, and stop blaming the interpreter for first-request latency.
- Percentiles cannot be averaged or concatenated across windows or instances; the histograms must be merged and the percentile taken from the merged distribution. Aggregate per-window and per-instance latency correctly in a dashboard, and spot why averaging hides a stall.

## The run and the report that cannot be true

You have a service and you want to know if it is fast. So you run a load test, and the tool prints a p99. This whole phase is about one question: which numbers in that report can you defend?

Here is the run every section returns to. The service is a Starlette app on your laptop, served by uvicorn. Each request draws an exponential service time averaging 10 ms. At t = 20 s the test injects a 3 s stall with POST /stall?seconds=3. So the service answers nothing for 3 s. Two load tests drive it at 48 req/s, one after the other, and only the way they send requests differs.

  2.73 sp99 reported by run one

  50.6 msp99 reported by run two

  54×gap between the two reports

Run E3 of this phase, CPython 3.13.3, Apple M2, same service and same 3 s stall in both runs.

One stall, two reports, and a factor of 54 between them. Both reports came from working tools with no bug. Run two says a user at the unlucky 99th percentile waited 50 ms, while the service was frozen for 3,000 ms. The two numbers cannot both describe the same users, and this phase explains each of them.

Three names cover everyone in this story, and the whole phase uses them.

- generator sends a requestthe generator, the tool that sends requests and measures replies

- service works10 ms of fixed work, or nothing during the stall

- reply returnsthe gap between send and reply becomes one latency sample

- The generator is the load tool. It decides when each request is sent, and that decision is the whole difference between the two runs.

- A latency sample is one number: the time from sending one request to its reply coming back. Every percentile you will ever report is a count over these samples.

- The stall window is the 3 s during which the service answered nothing. How many samples land in this window is what separates the two reports.

The phase grows from this one run in three directions, each marked by a number that moves.

  48 req/s, one stall

The run above, at 49% busy. It asks whether the generator can see a stall at all, and how the samples were stored and counted.

  77 req/s and 91 req/s

The same service at 79% and 93% busy. It asks how long a run must last before its p99 means anything, and why two identical runs disagree.

  The first seconds

A freshly started service. It asks what is genuinely cold at t = 0, and whether discarding the first seconds hides it.

By the end you will run one load test and say which of its numbers you would defend in an incident review. The first question is the run-two report above: how a working tool recorded a 3 s freeze as 50 ms. The next section shows why a client that waits for each reply cannot count a stall.

## Why a waiting client cannot count a stall

A client that waits for each reply records a 3 s stall as one sample, not 136. So its p99 describes the healthy seconds.

The opening run printed two p99s, 2.73 s and 50.6 ms, from one service and one 3 s stall. The 2.73 s report came from a schedule. The 50.6 ms report came from a single waiting client. Both tools worked exactly as built. This section explains the waiting client: why its report is internally correct, and why that is the problem.

The picture. A closed-loop generator sends a request, waits for the reply, sleeps its pacing delay, and only then sends again. The time between two sends is the response time plus the delay. So the service's latency decides how fast the client can send. The generator and the service form one feedback loop. The slowest seconds of the run produce the fewest samples from each client.

- sendone request goes out

- waitthe client blocks until the reply arrives

- sleepthe pacing delay, 10.8 ms at a planned 48 req/s

- send againthe loop repeats

Predict: one client, a 5 s freeze, 100 planned requests per second
A service answers in 1 ms. A test plans 100 requests per second for 100 s. At t = 50 the service freezes for 5 s. One closed-loop client sends, waits, sleeps 9 ms, and sends again. What p99 does it report?

Answer: about 11 ms. The client sends one request at t = 50 and waits the whole 5 s freeze. So the stall contributes exactly 1 sample out of roughly 9,501. The p99 looks past the slowest 1%. So it lands on a healthy sample of about 9 ms plus 1 ms of work. A schedule-driven generator sends 500 requests into the freeze. Roughly 5% of its samples sit between 0 and 5 s. So its p99 lands inside the stall at about 4 s.

The mechanism. The failure is arithmetic, not a bug. The planned 48 req/s becomes an offered load of only what the loop can push, because each send waits on a reply:

send rate ≤ clients ÷ latency
  healthy:  1 ÷ 0.0103 s  ≈ 48 req/s   plan met
  stalled:  1 ÷ 3 s       ≈ 0.33 req/s  99% of planned load never sent

The coupling has two consequences, and both bend the report toward healthy:

- The stall yields about one sample per client, however long it lasts. One request is in flight when the freeze starts, and no client can send a second before the first returns. A 3 s stall and a 30 s stall look the same to the sample set, because duration never multiplies into the count.

- The achieved rate quietly drops below the plan. The closed run sent 39 req/s against a planned 48, because every response time eats into the pacing budget. Even without any stall, capacity conclusions from this run are wrong in the optimistic direction.

An open-loop generator breaks the loop by making each request's send time independent of every other request's completion. Its sends march through the stall, and every scheduled request that lands in the freeze becomes one slow sample. The timeline shows the difference as empty space:

  The same 3 s stall, seen by both generators

  Step 2: both generators send at 48 req/s while the service is healthy, and both see 10 ms responses.

  Step 3: the stall begins. The open loop keeps sending and 136 requests pile into the freeze. The closed loop's one in-flight request waits it out alone.

  Illustration of the measured run: open 136 stall samples, closed 1, same service and stall.

The p99 is a count over samples, so the two sample sets give the two reports. In the closed run's 1,544 samples, the single 3 s sample sits inside the top 1%. So p99 comes out at 50.6 ms from the healthy seconds. In the open run, 136 of 1,867 samples are slow, that is 7.3%. So p99 must land inside the stall at 2.73 s. Same service, same stall, p99 off by a factor of 54.

Evidence
The phase's own lab E3, 2026-09-25, Apple M2 8 GB, CPython 3.13.3. Starlette/uvicorn service at 48 req/s (49% busy), 3 s stall injected at t = 20 s. Open loop (Poisson, timer=due): n=1,867, p99 2.73 s, 136 requests recorded in the stall window. Closed loop (one client paced to 48/s, as Locust constant_throughput paces): n=1,544, p99 50.6 ms. Exactly 1 request in the stall window, achieved rate 39/s. The hand-computed variant (100 req/s, 1 ms service, 5 s stall) puts the factor at about 4,100. The wrk2 README reports the same shape. A 1.4 s server pause gives corrected p99 1.27 s against uncorrected 6.04 ms, about 200x.

Use it. Exercise E1 (coordinated_omission.py) lets you compute this by hand before you run it. Use --stall 1 --rate 200 and one client that sends, waits for the reply, then sends again. Work out how many samples the stall contributes and what p99 each generator prints. Then run it and check your numbers. The question to hold while you run it: which seconds did the closed run fail to record?

  A waiting client sends at most one request per response time, so a stall costs it one sample.

  Believing p99 50 ms proves no user waited seconds, when the tool sent 39 req/s of a planned 48.

  Open your load tool's docs and find whether it waits for the reply before sending. Look also for what it names achieved-versus-planned rate.

The open loop's secret is a send time fixed in advance and a latency measured from that moment. The next section shows how measuring from when the request was due repairs a closed-loop recording. It also shows what the repair cannot rebuild.

## Measuring from when the request was due

Fixing send times before the run breaks the coupling; measuring from those times is what makes the stall visible.

The closed loop failed because its send times depend on the service's replies. The open loop removes that dependence with one change: the schedule is written before the run starts. This section shows what that change does to the same 3 s stall. It then shows what a repair can and cannot rebuild from a closed-loop recording you already have.

### Fix the send times, then measure from them

An open-loop generator's schedule exists independently of the service. Each request has a due time, the clock time the schedule says it should leave. The generator sends it then whether or not earlier replies have come back. The latency of each request is measured from its due time. It is not measured from when the sender happened to get around to it. With that, the stall can no longer hide, because the schedule keeps producing requests through it.

- The generator gives each request its due time, 48 Poisson arrivals per second in this course, and sends it at that time.

- During the run, it sends each request when its due time arrives, on a connection that does not wait for replies.

- When a reply lands, the sample recorded is now minus that request's due time, so a request sent during the stall and answered 2.9 s later records 2.9 s.

- The 136 requests due during the 3 s stall each record their own wait, so the stall contributes 136 samples instead of one.

The failure this repairs has a name. Coordinated omission is what happens when the thing being measured and the measurer move together. So the slow period produces the fewest samples. The service slows, and the waiting client slows with it. The stall is omitted from the recording because the two were coordinated. It is the name Gil Tene gave the closed-loop failure in his talk.

  One 3 s stall, scheduled sends against waiting sends (illustration from the course's measured runs)

  Step 2: during the stall the open schedule produces 136 due times, and the closed client produces one waiting request.

  Step 3: the open loop's replies arrive late and record that lateness; the closed loop has nothing to record here.

  The same stall run gave p99 2.73 s to the open loop and 50.6 ms to the closed loop. That is a factor of 54.

The numbers from the course's own run, both against the same Starlette service with the same stall at t = 20 s:

  2.73 sopen-loop p99, n = 1,867

  136samples recorded inside the stall window

  50.6 msclosed-loop p99, n = 1,544

  1sample inside the stall window

Evidence
Lab E3 run of 2026-09-25 used Apple M2 and CPython 3.13.3. It planned 48 req/s against a 10.25 ms service, with POST /stall?seconds=3 at t = 20 s. Open loop, Poisson schedule, timer from due time: n = 1,867, p99 2.73 s, 136 requests in the stall window. Closed loop, one client paced to 48/s: n = 1,544, p99 50.6 ms. 1 request was in the stall window, and the achieved rate was 39/s. The wrk2 README reports the same shape from a 1.4 s pause. Corrected p99 was 1.27 s against uncorrected 6.04 ms, about a 200x gap. Numbers from the phase, not re-run here.

### Repairing a recording you already have

Sometimes the recording exists and you cannot rerun it. That is because it came from a tool that only had a closed loop. The histogram library offers a repair called corrected recording (record_corrected_value in hdrhistogram_py). It works by filling in the samples the schedule would have produced.

Its loop is short. You record one observed value and the schedule interval you meant to keep, 10 ms in the checkpoint's example:

- Take the observed value, 4.1 s for the one request that waited out the stall.

- Subtract one interval, record the rest, and repeat, while what is left stays above the interval: 4.1 s, then 4.09 s, then 4.08 s, and so on.

- Each subtracted copy stands for one request that was due while the waiting request held the client. A 4.1 s value with a 10 ms interval inserts about 410 copies.

Predict: you repair the closed recording with the 10 ms schedule intervals. Will the corrected p99 land above the open loop's 4.10 s, at 4.10 s, or below?
Below, at 4.00 s in the course's run. The reconstructed copies are the requests that were due during the freeze, and they record nearly the full wait. The repair has no samples of what happened after the stall ended. Then the queue of 136 waiting requests drained, and each reply still arrived later than its due time. The open loop measured those drain samples directly, and they are what lift its p99 the extra 0.1 s. A repair built from one observed value describes the stall's left edge well and its right edge not at all.

This limit is verified in the library source. In hdrhistogram_py 0.10.7 and 0.10.8, record_corrected_value only inserts copies of the observed value minus k times the interval. It can rebuild the statuses due inside a stall. It can never synthesize the queue that drains afterwards. That is because nothing in the closed recording says how long that drain took.

One more limit sits on the other side of the open loop. Its 2.73 s is an upper bound when users give up. Real users behind a 1 s timeout abandon and retry instead of waiting out the 3 s stall. What they experience is the timeout plus the retry, not 2.73 s (inferred; the course does not model abandonment). Report the open-loop p99 as what waiting would have cost, and say whether your users wait.

Use it. Exercise E1 uses coordinated_omission.py with --stall 1 --rate 200. It asks you to compute by hand how many samples the closed loop's stall contributes before you run it. When you read the open run's output, check one thing. Does the tool also print the schedule it planned next to the rate it achieved? That pair, planned against achieved, is the quickest tell of a generator that cannot keep its own schedule.

  Fix send times before the run and measure from due time, so the stall yields one sample per scheduled send.

  Trusting corrected recording to rebuild a stall fully. It cannot rebuild the queue drain and reads 0.1 s low here.

  Rerun your last load test with the timer switched to due time and compare the two p99s. The gap is generator lag and connection wait, latency users feel.

Both honest runs now produce one to two thousand latency values. The next section is recording every latency without losing the tail. It shows the container that keeps them all without dropping the slow ones.

## Recording every latency without losing the tail

The open loop now hands you one to two thousand honest latency samples per run. The corrected record does the same. This section is the container that keeps every one of them, plus its one silent failure.

If the recorder drops slow samples, even an honest generator reports healthy seconds.

In the stall run at 48 req/s, whose windows extend to 40 s, the service sat frozen. The open loop recorded 136 samples near 3 s. Those samples alone separate the honest p99 of 2.73 s from a clean 50 ms. The container receives them. If it loses exactly the large values, the honest run is back to the closed loop's report.

An HDR histogram is a container for latency samples that keeps counts instead of the samples themselves. You declare the smallest and the largest value it may hold when you create it. It allocates one fixed row of buckets right then. Each bucket covers a thin slice of the range. Recording a sample adds one to exactly one bucket's counter, and the sample itself is thrown away. It exists so that a run of one hundred samples and a run of five million cost the same memory. Every percentile stays readable from the counts afterwards.

- A sample arrives: does it fit the declared range?

- in rangeone bucket's counter rises by one, and the value is discarded

- out of rangethe record call returns False, and nothing is stored anywhere

Predict: a 90 s request lands in a histogram declared for 1 µs to 60 s that already holds 999 samples at 10 ms. What do count and max print after it, and what did record_value return for the 90 s value?
It prints count 999 and max 10 ms, and record_value returned False. The 90 s value sits outside the declared range. So no counter moves and no error is raised. The only trace of the lost sample is the return value the caller ignored.

Answering count 1,000 and max 60 s is reasonable. The clamp keeps the slow request as the largest value, 60 s or more. This one cannot grow, because its whole memory was fixed at creation.

Three decisions happen once at creation, and then each sample costs one counter.

- Declare the range and the precision once. The course's recorder is created for 1 µs to 60 s at three significant figures, meaning every recorded value keeps about one part in a thousand of its own size. All counters exist from then on, so a 25 s run and the 300 s runs occupy exactly the same histogram, and a longer run never asks the recorder for more memory.

- Record by counting. An _us helper in latency.py converts each sample to integer microseconds, the library maps that number to a bucket index by arithmetic, and one counter rises. There is no list to append to, so the work per sample does not grow as the run grows.

- Read percentiles from the counts. A p99 is the value that 99% of all samples are at or below. The answer can sit up to one bucket width away from the true value, and at three significant figures that error scales with the latency itself.

value being recordedits bucket spans aboutso a percentile there is off by at most

10 ms, the run's healthy requests0.01 ms0.01 ms

2.73 s, the open loop's p99 in the stall run2.7 ms2.7 ms

The absolute error grows with the value. The relative error stays at one part in a thousand. That is the entire precision model.

  One bucket's width, from the definition

  Latency being recorded (ms)
     ms
  Significant figures

  Bucket width

  Relative error

The box applies the definition of significant figures directly, not the library's exact bucket layout.

The one silent failure. A sample outside the declared range is an out-of-range value. record_value handles it by returning False and storing nothing: no exception, and nothing printed. Apply that to the running case. The stall produced 136 samples near 3 s. So a histogram declared with a 1 s maximum would drop all 136 and print a p99 over the survivors. That gives the honest open loop the closed loop's clean report. The failure is also biased because a range overflows at the slow end. That is exactly the end a latency measurement exists for.

h.record_value(us)   # return value ignored: slow samples vanish untraced

if not h.record_value(us):
    dropped += 1     # the False is the only signal out-of-range ever sends

Evidence
The out-of-range behaviour is verified from source. record_value returns False and records nothing for a value outside the declared range. It is byte-identical in hdrhistogram_py 0.10.7 and 0.10.8 (read 2026-10-13). Version 0.10.8 is the current PyPI release, dated 2026-10-12, and the course pins 0.10.7. The 136 stall samples and the p99 of 2.73 s are the phase's own measured 25 s run. They are taken as given.

Use it. Open latency.py, the recorder every lab in this phase writes through. Read its self-test next to the clamp in _us. One question to answer from the code: what does the clamp turn a 90 s sample into?

  An HDR histogram keeps counts, not values, so its memory is fixed at creation.

  A too-small range drops exactly the slow samples silently, and the report still looks healthy.

  Add a 90 s record to a 60 s histogram and watch the count stay at 999.

Now the recorder keeps every sample. The next section asks what the load generator itself records when the service stalls.

## How many samples stand behind your p99

A printed percentile is only as real as the samples above it, and you can count them.

The HDR histogram now records all 1,063 latencies of a run without dropping any. That makes the recording faithful, but it does not make every number read from it defensible. Your open-loop run at 48 req/s prints p50, p90, p99, p99.9 and max. This section asks which of those you would sign in an incident review.

Sort all n samples from fastest to slowest. A percentile is an order statistic, a value picked by rank from that sorted list. The p99 is the value at rank 99% of n. Its worth is set entirely by the slowest 1% of samples, the samples above the percentile. Their count is n·(1−q). If ten samples stand above the p99, the reported value is whichever of those ten happened to appear. Re-run the test and a different ten appear, so the p99 moves. One sample above the p99.9 is not a description of the tail. It is one observation.

Predict: your test ran 2,000 requests. Which of p50, p99, p99.9 can you defend, and how many requests would a defensible p99.9 need?
Count samples above each percentile: p50 has about 1,000, p99 has about 20, p99.9 has about 2. You can defend p50 and p99. The p99.9 is two samples, so it is a coin flip, not a measurement. For about ten samples above p99.9 you need n·0.001 ≥ 10, so n ≥ 10,000 requests. The reason the wrong answer feels right: the tool prints all three with the same number of decimal places. Nothing in the report says what each rests on.

The rule and the floor come from the same arithmetic.

- Write the run size as n and the percentile as q, so p99 is q = 0.99.

- The samples above it number n·(1−q). Below about ten, the percentile moves from run to run on arrival luck alone, so you do not quote it.

- There is also a hard floor below which no interval for the percentile exists at all. For a 95% interval to exist, the largest sample must beat the true quantile with probability at least 0.975, which means qn ≤ 0.025.

- Solving gives n ≥ ln(0.025)/ln(q). For p99 that is 367.04, so n ≥ 368. (inferred: derived from first principles, not a cited standard.)

samples above q = n · (1 − q)
n = 1,063:  p50 → 531    p99 → 10    p99.9 → 1
floor: n ≥ ln(0.025)/ln(q)   →  368 for p99, 3,688 for p99.9

n = 1,063 sorted samples (E7 run 1, open, 48 req/s, 25 s)

Now read E7's run 1 with this lens. n = 1,063. The p99 of 92.8 ms rests on exactly 10 values, 92.9 to 103.4 ms. It just passes the count rule. The p99.9 of 98.3 ms rests on exactly 1 value, so that number is one sample wearing a percentile's clothing. Notice one thing: the floor of 368 for p99 is met. The count of ten is the binding constraint here, not the floor.

Evidence
Lab E7 run 1, open loop at 48 req/s for 25 s, the phase's own run: n = 1,063. The p99 = 92.8 ms on 10 samples (92.9 … 103.4 ms, listed in the phase). The p99.9 = 98.3 ms on 1 sample. The floor n ≥ ln(0.025)/ln(q) is derived in this course and in phase 1B, not quoted from a standard.

Use it before any run whose numbers you will defend. Decide the deepest percentile you will quote, multiply the needed samples by 1/(1−q), and check the run reaches that n. A p99.9 target for an endpoint that sees 5,000 requests per window is unmeasurable at any window length. Saying so is the defensible answer.

Count n·(1−q) samples above a percentile, and quote it only when ten or more stand there.

The tool prints p99.9 for any n, so a two-sample tail reads as a measured SLO.

Take your last run's n, compute n·(1−q) for p99 and p99.9, and cross out what fails.

Enough samples above the percentile is still not enough if the run itself is too short. The next section shows why a short run near the knee reads low.

## Why a short run near the knee reads low

A short run near the knee underreports p99, and the busier the service, the larger the gap.

The section above showed a percentile with enough samples behind it can still be trusted or not. Even with every stall recorded and ten samples above p99, one thing still decides what p99 you see. That thing is how long the run lasted, and the effect grows as the service gets busier.

Back at the Starlette service. It is healthy now, no stall injected, just exponential service times with mean 10 ms per request and Poisson arrivals. You drive it at 91 req/s, which is 93% busy, for 23 seconds. The run reports p99 385 ms. Is that the service's p99?

### The picture: the tail belongs to rare events, and a short run rarely meets them

At 93% busy the queue does not stay near its mean. It wanders, and every few minutes an unlucky burst of arrivals drives it deep for a while. Those deep moments produce the slowest one percent of responses, so they set the p99. A run long enough to contain them is in steady state, in which the queue has forgotten how it started and its statistics no longer drift. A 23 s window usually sits on a shallow part of the trace. This is short-run understatement: a short run samples the queue's ordinary moments and misses the excursions that define the tail it reports.

-

-
time, 15 minutes
queue length

23 s window
23 s window
one deep excursion sets the long-run p99
Illustration, not measured. Both shaded 23 s windows sit on shallow queue, so both report a small p99, and they disagree with each other.

Predict: your 30 s run at 93% busy reports p99 300 ms; a colleague re-runs it and gets 700 ms. Is one of you wrong, and what single change makes the number reliable?
Neither of you is wrong. Each run samples whichever queue excursions happened to fall inside its 30 s. At 93% busy those excursions differ by a factor of 4 between identical runs. The reliable change is longer runs, because the deep excursions that set p99 arrive on the scale of minutes there. More short runs tell you the spread but not the steady value. Lower load dodges the question you were asked, which is the p99 at 93%.

### The mechanism: why busier means rarer

Model the service as M/M/1: Poisson arrivals, exponential service times, one server. The course uses S = 10.25 ms per request, the 10 ms of work plus 0.25 ms of framework overhead. Two standard results explain everything in this section.

- The response time is exponential with rate μ−λ, so the long-run p99 is ln(100)·S/(1−ρ). At 49% busy that is 93 ms. At 93% it is 702 ms. The tail stretches 7.6x while the load rises less than 2x.

- The queue-length variance is ρ/(1−ρ)². At 49% it is about 1. At 93% it is about 128. The queue swings over a range more than a hundred times wider, so the deep excursions that set the tail are both deeper and further apart.

The two results split the work. The first gives the long-run p99. The second says how rarely a visit to that depth happens. Near the knee, the utilisation where waiting time rises sharply, the visits come minutes apart. A window seconds long usually contains none of them. The phase's simulation makes the size of the miss concrete.

Run shape at S = 10.25 msMedian run p99Long-run p99Spread across 40 identical runs

49% busy, 23 s runs89 ms93 msadequate

79% busy, 23 s runs184 ms224 msreads 82%

93% busy, 23 s runs385 ms702 ms180 to 863 ms, 4.8x

93% busy, 300 s runs606 ms702 ms455 to 1,795 ms, 3.9x

The one number to carry is the third row. At 93% busy a 23 s run reports about half the steady p99. Two identical runs disagree by a factor of 4.8. Even five minutes only reaches 86% of the steady value, with the same wide spread. At 49% busy the same 23 s is already adequate, because the tail lives close to the mean. Every run meets it.

Evidence
The numbers are the phase's own predict.py --short-runs simulation, 40 runs of 23 s each, M/M/1 with S = 10.25 ms. The two formulas (FCFS response time exponential with rate μ−λ, queue variance ρ/(1−ρ)²) are standard M/M/1 results, taken from the Wikipedia M/M/1 queue page, read 2026-10-13. The real lab agrees with the simulation: E7's 25 s open runs at 93% measured 233 to 325 ms against the model's 702 ms, which is this effect, not a model error.

### Use it

Exercise E5 runs this simulation yourself: predict.py --short-runs, then the 300 s variant. Watch the medians approach the long-run p99 as runs lengthen, and watch the spread refuse to close at 93%. You may next inherit a CI load test that measures 60 s after discarding 30 s. Then ask what utilisation it runs at. Above the knee, that test is reading arrival luck, not the service.

Near the knee a short run reads about half the steady p99, so lengthen the run before trusting it.

Discarding 30 s of warm-up then measuring 60 s feels rigorous and still reports arrival luck at 93% busy.

Compute ln(100)·S/(1−ρ) at your service's peak utilisation, and compare it with your last run's p99.

This section covered run length, the first of the two problems usually called warm-up. The second is cold state, and the next section asks what is actually cold in the first seconds.

## What is actually cold in the first seconds

The first seconds of a run cost users on every deploy, so report them instead of discarding them.

The previous section split "warm-up" into two problems and covered the first, run length. This section measures the second: the state a fresh process starts with.

Restart your Starlette service on your laptop and send requests one at a time. The first request takes 11 ms, and the rest take 10.25 ms. The standard advice is to discard the first minute of every run. That advice protects you from a cost that has already settled, while hiding costs your users pay on every deploy.

Predict: a fresh service answers its first request in 30 ms and the rest in 10 ms. Is the extra 20 ms interpreter warm-up, and what one measurement settles it?

Probably not, and the settling measurement is to time the first three requests separately. CPython specialises an instruction the second time it runs, so request two is already warm and request three adds nothing. If the penalty sits on request one alone, the interpreter explains at most part of it. The rest is cold state such as imports, connection setup or empty caches. Restart the process and send exactly three requests: that separates a one-request interpreter cost from costs that decay over seconds.

### The picture

Cold state is everything a fresh process starts without. That includes loaded modules, open connections, filled caches and a queue that has seen traffic. Code warm-up and state warm-up are different things, and they settle on different timescales. Code warms in about one request. State warms when something fills it, and some of it never does within a run.

The first request, 11 ms, against a steady request at 10.25 ms (lab W, M2, fixed 10 ms work)

The bar shows the whole code-warming cost: 0.7 ms on one request. The costs the bar cannot show live elsewhere. Imports take about 70 ms of the 0.12 to 0.17 s process start. A connection pool, application caches, the page cache and the empty queue each add their own delay. None appears in this measurement, because lab W reused one warm client against a local service.

### Why one request warms the code

Since CPython 3.11, the interpreter is a specialising interpreter. It watches each bytecode instruction. The second time that instruction executes, it rewrites it into a faster form for the types it saw. The source at v3.12.0 sets ADAPTIVE_WARMUP_VALUE to 1, which means specialising on the second execution. One request runs your handler's instructions once or twice, so one request completes the warm-up. The 3.13 JIT is experimental and off by default, so no further tier of warm-up applies in a stock build.

- Request one executes each handler bytecode once, and the interpreter rewrites each one for the types seen, costing 0.7 ms in lab W.

- Request two runs the rewritten instructions at full speed, so the interpreter's contribution is finished.

- Every later request differs from request two only in state, such as which connections exist and which caches hold entries.

Lab W measured this directly, with a fresh process, fixed 10 ms work and one-at-a-time requests. The first request took 10.6 to 11.0 ms against a median of 10.2 to 10.3 ms for the rest. That is a 3 to 7% penalty that settled after 0 requests, across three repeats.

### What stays cold after the code is warm

- Imports. Loading the application's modules costs about 70 ms of the 0.12 to 0.17 s process start, paid before the first request arrives.

- Connections. httpx 0.28.1 sets keepalive_expiry to 5.0 s, the keep-alive expiry, the idle time after which a pooled connection is closed. A 5 s pause mid-test costs a fresh connect and TLS on the next request.

- Caches. Application caches and the operating system's page cache fill only as real traffic touches data, so they can stay cold for minutes.

- The queue. A fresh run starts with an empty queue, so its first seconds differ from the knee, the high-utilisation region where the tail grows fastest, in either direction.

The queue is why the first seconds can mislead in both directions. At 79% busy, 8 of 10 unchanged-code runs had a lower median in the first 2 s. That happened because the queue starts empty. At 93% busy the first 2 s ran slower, because arrivals bunch at start. So discard the first seconds and you throw away evidence. Average them in and you hide which direction they ran. Report them separately.

Evidence

Lab W, the phase's own run, 2026-09-25, Apple M2, CPython 3.13.3. Fresh process, fixed 10 ms work, one-at-a-time requests. First request 10.6 to 11.0 ms, median of the rest 10.2 to 10.3 ms, settled after 0 requests, three repeats. Process start 0.12 to 0.17 s, with python -X importtime attributing about 70 ms to imports. The specialising mechanism is verified from CPython v3.12.0 Include/internal/pycore_code.h. It defines ADAPTIVE_WARMUP_VALUE 1 with the comment "we attempt to specialize the *second* time each instruction is executed" (read 2026-10-13). Where the threshold lives in 3.13 was not found, so the v3.12.0 tag is the citation. The keep-alive default of 5.0 s is verified from httpx 0.28.1 _config.py; later releases were not checked. The first-seconds direction at 79% and 93% comes from the phase's unchanged-code runs.

### Use it

Exercise E2 runs lab W yourself: ./lab.sh W. Then read the first request against the median of the rest on your own machine. The expected output is a first-to-median ratio of about 1.03 to 1.07 and "settled after 0". Then open whatever load test script you run most often and find the line that discards a warm-up window. Ask what that window is hiding.

One request warms the interpreter; imports, pools, caches and the empty queue are the cold state users pay for.

Discarding the first minute removes the cold costs users pay on every deploy and fixes none of them.

Restart your service, time requests one, two and three separately, and check which carry the penalty.

This section measured each cold component and found the interpreter innocent. All the honest per-window numbers now exist. The next section asks how to add twenty-five windows into one honest p99.

## Adding twenty-five windows into one honest p99

Combining per-window p99 numbers is impossible; only the merged histogram gives an honest run p99.

The phase so far has produced honest numbers for every one-second window of the run. What is missing is the one lawful way to turn those window numbers into one number for the whole run. It applies per instance or per day. This section is that rule, worked on the same 25 s run from the opening.

### The picture first

Your dashboard keeps one HDR histogram, the counting container from the recording section, per second of the run. A percentile is not a property of a number. It is a position in a distribution, chosen by counting samples. So it has no meaning apart from the distribution behind it. Once a window is reduced to the single number "p99 51 ms", the counts that produced it are gone. No arithmetic on that number can recover them. A histogram merge adds the counter arrays of two histograms bucket by bucket. That rebuilds the full distribution of both windows, and only then is a percentile taken from it.

25 one-second histograms, one of them holding the 3 s stall

stall window

Path 1: take each window's p99, then average the 25 numbers

50, 51, 48, …, 2,730 ms
average →

about 160 ms
looks healthy

Path 2: add the 25 counter arrays, then read the percentile

sum of all bucket counts
merged p99 →

2.73 s
the 136 stall samples are still in the counts

Two paths from the same windows to one number. The averaged path loses the stall because a p99 carries none of the counts behind it. Illustration built on E3's recorded numbers.

Predict: twenty-four hourly windows report p99 between 40 and 60 ms, except one window that held a 3 s stall and reports 2.7 s. What does the average of the 24 p99s say, and what does the merged histogram say?

The average says about 170 ms. That is because one 2.7 s number spread across 24 values adds roughly 110 ms to a 50 ms base. The merged histogram says 2.7 s, because its counts still hold every delayed request from the stall window. The average is wrong for the question a p99 answers. It treats each window's p99 as a measurement rather than as a count position. The merged p99 is the honest one. Percentiles are computed from distributions, and the merge is the only step that kept the distributions.

### Why the average fails, in one count

A window's p99 is the value below which 99% of that window's samples fall. Two facts follow from that definition.

- Each window's p99 is chosen from a different distribution, so the numbers are not measurements of one thing and cannot be combined.

- A percentage is a ratio, and ratios do not add, because the denominators differ whenever the windows hold different request counts.

- The average dilutes, because one bad window among 25 contributes its p99 with weight 1/25 instead of contributing its 2,730 ms samples with their true count of 136 among about 1,900.

Weight is the heart of it. In E3's run the stall window held 136 delayed samples out of roughly 1,867, about 7% of the run. Those samples belong near the p99 position of the merged distribution, so they move it by seconds. In the average of window p99s the same stall is one number among 25. So it moves the result by about 110 ms.

### The merge, in code

HdrHistogram.add() sums the two counter arrays bucket by bucket, which is exact because both histograms store counts rather than percentiles. It raises if the other histogram's values do not fit the target's range. So a merge cannot silently drop the stall the way an undersized record_value can.

merged = None
for h in window_histograms:          # one HdrHistogram per second
    if merged is None:
        merged = h
    else:
        merged.add(h)                # raises if h's values exceed merged's range
p99 = merged.get_value_at_percentile(99)   # 2.73 s on E3's stall run

Evidence

HdrHistogram.add() exists in hdrhistogram_py 0.10.7 and 0.10.8 and raises if the other histogram's values do not fit the range. This was verified from source, read 2026-10-13. Exactness follows from the structure. Both histograms store counts per bucket, so adding the arrays is exact up to each histogram's fixed relative precision. The direction and size of the gap in E3 (merged 2.73 s, average near the healthy seconds) is inferred. The direction follows from one stall window averaged with healthy ones, and the size follows from E3's recorded numbers.

### Use it

In exercise E3 you already have the 25 one-second histograms from windows.py. Add the merge step: build one merged histogram with add(), read its p99. Then compare it with the average of the 25 window p99s. The reading question is how many seconds of delay the average hid on your own run. The same rule applies anywhere a dashboard shows per-instance or per-window percentiles. A row of window p99s cannot be combined into a run p99 by any arithmetic on the row itself.

Merge the histograms, then take the percentile; never average percentiles.

Averaging window p99s dilutes one stall window by the window count, so the worst hour disappears.

Merge your E3 window histograms with add() and compare the merged p99 with the average of the window p99s.

You can now produce one honestly measured run. You can say which of its numbers you would defend in an incident review. What one run cannot tell you is whether the gap between two runs is real or arrival randomness. That is the question the next phase answers, together with what M/M/1 predicts before you measure.

## What you can do now, and what comes next

The phase ends where it began: one service, one injected stall. The decision is which printed numbers you would defend. These are the five claims, each with the section that earned it.

A waiting client cannot count a stall

A closed-loop generator, a client that waits for the reply before sending, sees its send rate fall when latency rises. A stall is recorded once per client whatever its duration. Its p99 describes the healthy seconds: 50.6 ms for a service frozen 3 s. Fix the send times in advance and measure from when each request was due. Then the same stall reports 2.73 s with 136 delayed requests. Sections 2 and 3.

A percentile rests on the samples above it

The p99 of n samples is decided by the n·(1−q) slowest values. Below about ten of them, the percentile should not be printed. Below n = ln(0.025)/ln(q), 368 samples for p99, no interval for it exists at all. So a p99.9 from 1,063 requests is one sample. Sections 4 and 5.

A short run near the knee reads low

Near the knee, the utilisation where the queue takes off, the tail is set by rare deep-queue excursions. A short run usually never contains them. This is more so the busier the service. At 93% busy a 23 s run reports about half the steady p99. Even 300 s runs still range 455 to 1,795 ms. Section 6.

The interpreter is warm after one request

The specialising interpreter rewrites an instruction the second time it executes. The measured first-request penalty is 3 to 7% and settles immediately. The cold state that costs users is imports, connection pools, caches and the empty queue. A connection pool's keep-alive expires after 5 s of silence. So the first seconds are reported, never discarded. Section 7.

Percentiles never average

Averages of percentiles are meaningless and hide exactly the window that hurts. The average of 25 window p99s stays near the healthy seconds, but the merged histogram reports 2.73 s. Keep one histogram per window or per instance, and merge them with add(). Read the percentile once from the merged distribution. Section 8.

Put together they answer the question this phase opened with. One honest run records every stall and keeps enough samples above each percentile it quotes. It runs long enough for its utilisation. It reports its first seconds and aggregates by merging. You can now say, for any load report placed in front of you, which of its numbers you would defend. The why belongs in an incident review.

What one run cannot tell you is whether the next run will agree. Two identical 30 s runs at 93% busy in this phase reported 300 ms and 700 ms. Both were measured correctly. The next phase asks that question. Is the difference between two runs real, or the randomness of arrival? Can M/M/1 queueing predict the spread before you measure it?

## Lab

-  E1 offline
Concept c1: a waiting client records a stall once. Run coordinated_omission.py --stall 1 --rate 200. This is the only exercise in the phase whose answer you can compute by hand, so compute it first: with one waiting client and a 1 s stall, how many samples can the stall window contain? Then run it and compare. The run prints the closed loop's p99 against the open loop's p99 for the same service and the same stall, and the gap between them is the concept.

Answer sketch
One waiting client sends the next request only after the reply, so a 1 s stall yields exactly one late sample: the request sitting in the service when it froze. Percentiles are counts of samples, so one sample out of hundreds cannot reach p99. The open loop fixes send times in advance and measures from when each request was due, so every request scheduled into the stall is recorded with a latency near 1 s, and p99 follows them.

-  E3 live service
Concepts c1 and c5: the hiding, and the one lawful aggregation. Run lab.sh A, the stall experiment on the real service at 48 req/s (49% busy) with the 3 s stall injected at t = 20 s, then windows.py to split the run into one-second windows. Write one paragraph answering the question the exercise demands: which seconds did the closed-run log fail to record? Then do the merge step: add the 25 window histograms with HdrHistogram.add(), read p99 from the merged histogram, and compare it with the average of the 25 window p99s. The average stays near the healthy seconds. The merged p99 reports 2.73 s, because the stall window's counters are still in the sum.

-  E4 break-it
Concept c1, inverted: the queue moves into the client. Drive the service at 77 req/s over one connection. The service keeps up, but the client's connection pool becomes the queue, and a timer started at send time never sees the wait because the request has not left the client yet. This is the closed loop's blindness without any stall at all. Use the run to train the validity rule: when generator lag passes 10 ms, the generator itself fell behind, and the run's numbers describe the laptop, not the service.

-  E5 offline
Concept c3: a short run near the knee reads low. Run predict.py --short-runs. The simulation repeats the M/M/1 arrival process with S = 10.25 ms, 40 runs of 23 s each. At 49% busy the median run p99 of 89 ms is close to the long-run 93 ms, so a 23 s run is adequate there. At 93% busy the median run reads 385 ms against a long-run 702 ms, and identical runs spread from 180 to 863 ms. Then run the 300 s variant, the memorable one: even five minutes of measurement at 93% busy gives a median of 606 ms with runs from 455 to 1,795 ms.

-  E2 live service
Concept c4: the interpreter is warm after about one request. Run lab.sh W on a fresh process, fixed 10 ms work, requests one at a time. Expect the first request at 10.6 to 11.0 ms against a median of the rest near 10.2 to 10.3 ms, a first-request penalty of 3 to 7%, and the run reports it settled after 0 requests. The 30 to 60 s warm-up you might have discarded measures nothing the interpreter is doing.

Concept c2, instrumentation side: run the latency.py self-test, then try recording a value outside the histogram's range. record_value returns False and records nothing (hdrhistogram_py 0.10.7, identical in 0.10.8). A histogram sized too small silently drops exactly the stall samples this phase exists to keep, so check the return value in any harness you write.

Five exercises, one habit across all of them: before you trust a number, ask which mechanism produced it. The closed client, the short run, the undersized histogram and the discarded first seconds all fail in the same direction, toward a report that looks healthy.

## Checkpoint

Five questions, one per idea in this phase. Answer each before opening it. Every question uses numbers from the running case: the 1 ms service and the injected stall.

-
A closed loop and a 5 s stall. A service answers every request in 1 ms. A test sends 100 requests per second for 100 s, because one client sends, waits for the reply, sleeps 9 ms and sends again. At t = 50 the service freezes for 5 s. What p99 does the test report, and what would an open-loop generator at the same rate report?
Answer sketch
The closed loop reports a p99 near the healthy 10 ms.

During the freeze the client holds one request open, so the stall produces exactly one slow sample in about 9,500. One sample in 9,500 cannot move a p99. The open loop sends 500 requests into the stall. Each is measured from its due time, so they record up to 5 s. The open p99 sits near 4 to 5 s. Same service, same stall: the closed loop cannot see it.

-
Which percentiles can you defend. Your run made 2,000 requests. Which of p50, p99 and p99.9 can you defend, and how many requests would a defensible p99.9 need?
Answer sketch
p50 and p99 are defensible. p99.9 is not.

The samples above a percentile are n·(1−q). At n = 2,000 that is 1,000 above p50 and 20 above p99, both past the ten-sample rule. p99.9 rests on 2 samples, so it is a reading, not a percentile. A defensible p99.9 needs about 10,000 samples for the count rule. The floor n ≥ ln(0.025)/ln(0.999) gives about 3,688 for any interval to exist at all.

-
Two colleagues, two p99s. At 93% busy your 30 s run reports p99 300 ms. A colleague re-runs the same code and gets 700 ms. Is one of you wrong, and which single change makes the measurement reliable: longer runs, more runs of the same length, or lower load?
Answer sketch
Neither is wrong.

At 93% busy the tail is set by rare deep-queue excursions, and a 30 s run usually contains none. The phase's simulation shows identical 23 s runs at 93% ranging from 180 to 863 ms. Repeating 30 s runs only collects more readings of the same short window. The single change is longer runs, and even 300 s reads low at 93%. If longer is impossible, measure at lower load and say so.

-
The slow first request. A fresh service answers its first request in 30 ms and every later request in 10 ms. Name three cold candidates behind the extra 20 ms, and the one measurement that separates them.
Answer sketch
The candidates are cold imports, a cold client connection pool, and empty application caches.

The specialising interpreter is not one of them: it rewrites an instruction the second time it runs, so one request warms it. Lab W measured the penalty at 3 to 7%, not the 200% seen here. The separating measurement is to restart the process with a client that keeps its connection alive. If the first request is still slow, the cost is inside the service, so imports or caches. If it turns fast, the cold item was the connection.

-
One number from twenty-four windows. Twenty-four hourly windows report p99 between 40 and 60 ms. One window held a 3 s stall and reports 2.7 s. What does the average of the 24 p99s say, and what does the merged histogram say?
Answer sketch
The average is about 150 ms, and the merged p99 is 2.7 s.

The average gives the stall window a weight of 1 in 24, so 2.7 s becomes about 110 ms of contribution. The merged histogram adds the 24 counter arrays with HdrHistogram.add() and keeps every delayed sample. The stall is one of the day's slowest 1%, so it sets the merged p99. Percentiles never average; histograms merge.

## Cheatsheet

LOAD TEST CHEATSHEET  ·  one run, measured honestly

GENERATING LOAD
  Closed loop    send rate ≤ clients ÷ latency; a stall costs
                 about one sample per client, whatever its length
                 (48/s planned, 3 s stall: 1 sample, p99 50.6 ms)
  Open loop      fix send times in advance, measure from due time;
                 the same stall: 136 samples, p99 2.73 s
  Corrected rec. record_corrected_value rebuilds requests due
                 during a stall; never the queue draining after it,
                 so its p99 sits slightly low (4.00 vs 4.10 s)
  Validity       generator lag must stay small; at lag > 10 ms
                 the run measures the generator, not the service

COUNTING SAMPLES
  Above q        samples above q = n·(1−q)
  Quote rule     report a percentile only above ~10 samples
  Floor          n ≥ ln(0.025)/ln(q);  p99 needs n ≥ 368,
                 p99.9 needs about 3,685
  Recorder       HDR histogram: record_value returns False out of
                 range and drops the sample silently; size the
                 range for the stall, not the healthy seconds

SIZING THE RUN
  M/M/1          p99 = ln(100)·S/(1−ρ);  S = 10.25 ms here
  Queue variance ρ/(1−ρ)²: the busier the service, the deeper
                 and rarer the excursions that set the tail
  23 s run       adequate at 49% busy (median 89 vs 93 ms long-run)
                 93%: median 385 vs 702 ms, runs 180–863 ms
  300 s run      still not settled at 93%: median 606 ms,
                 runs 455–1,795 ms
  Two runs       near the knee, identical short runs disagree by
                 4–5x; longer runs fix it, more short runs do not

FIRST SECONDS
  Interpreter    specialising CPython rewrites an instruction the
                 second time it runs (ADAPTIVE_WARMUP_VALUE 1,
                 v3.12.0); warm after about one request,
                 first-request penalty 3–7%
  Really cold    imports (~70 ms of a 0.12–0.17 s start),
                 connection pools (keep-alive 5 s, httpx 0.28.1),
                 application caches, page cache, empty queue
  Rule           keep the first seconds, report them apart;
                 never discard them

AGGREGATING
  Never          average percentiles across windows or instances;
                 a stall window surrounded by healthy ones averages
                 away (24 windows: mean ~150 ms, true p99 2.7 s)
  Always         HdrHistogram.add() merges the counter arrays and
                 raises on range mismatch; read p99 from the merge

RECEIPTS
  wrk2           1.4 s pause: corrected p99 1.27 s,
                 uncorrected 6.04 ms
  This phase     open 136 samples in stall vs closed 1, 54x p99 gap

## Posts

Two drafts based on what you measured in this phase. Each is one claim plus the run that makes it yours. He posts them or edits them; nothing here is sent.

Draft 1: the tool was not broken

My load test printed p99 50 ms for a service I froze for 3 s. The tool was not broken; a waiting client stops sending when the service slows, so the stall appears once. Here is the same run, open loop: p99 2.73 s.

What makes it his: both numbers come from the E3 runs on the course service and the same stall. The phase recorded them on its own machine. There were 136 samples in the stall window against 1. The paired measurement, not the claim, is the post.

Draft 2: p99.9 from one sample

p99.9 from 1,063 requests is one sample. A percentile is only as real as the n·(1−q) values above it. For p99 an interval does not exist below n = 368.

What makes it his: E7's open loop run printed n = 1,063. Its p99 rests on the 10 values above it against the single value above p99.9. The floor of 368 is derived in the lesson, so he can show the algebra if asked.

## Sources

- https://raw.githubusercontent.com/HdrHistogram/HdrHistogram_py/0.10.7/hdrh/histogram.py — the pinned library. record_value returns False and records nothing out of range, record_corrected_value reconstructs only values due during a stall, and add() merges two histograms and raises on range mismatch. Verified from source on 2026-10-13.

- https://raw.githubusercontent.com/HdrHistogram/HdrHistogram_py/0.10.8/hdrh/histogram.py — the same three behaviours, byte-identical at the newest tag, so the lessons survive the upgrade.

- https://pypi.org/project/hdrhistogram/ — shows 0.10.8 is current, released 2026-10-12; the course pin of 0.10.7 is one release old and safe.

- https://raw.githubusercontent.com/encode/httpx/0.28.1/httpx/_config.py — the keepalive_expiry default of 5.0 s behind the claim that a 5 s pause costs a fresh connect and TLS. Read 2026-10-13; whether the default moved in later releases was not checked.

- https://raw.githubusercontent.com/python/cpython/v3.12.0/Include/internal/pycore_code.h — ADAPTIVE_WARMUP_VALUE 1 and the comment that an instruction is specialised the second time it executes. This is the version where the constant is verified; the phase originally cited 3.13, where it was not found.

- https://raw.githubusercontent.com/python/cpython/v3.13.0/Include/internal/pycore_code.h and https://raw.githubusercontent.com/python/cpython/v3.13.0/Include/internal/pycore_backoff.h — absence checks only: both read in full, and neither contains the warmup constant. No claim about 3.13 rests on these files.

- https://raw.githubusercontent.com/python/cpython/v3.13.0/Python/specialize.c — fetched with sections stripped; used only for the absence finding above, not for any claim about where 3.13 defines the threshold.

- https://github.com/giltene/wrk2 — the README's independent cross-check: measuring from the intended send time turns a 1.4 s server pause into a corrected p99 of 1.27 s against an uncorrected 6.04 ms.

- https://en.wikipedia.org/wiki/M/M/1_queue — the two standard results the short-run section rests on: response time exponential with rate μ−λ, and queue variance ρ/(1−ρ)².

- https://sourcegraph.com/github.com/python/cpython@v3.13.0/-/blob/Python/specialize.c — returned no content; nothing was used from it.

- The phase's own measured numbers (E3's 1,867 and 1,544 samples, lab W's first-request ratios, predict.py's simulation table) come from his own runs on his machine, taken as given with their conditions stated, not reproduced.
# Phase 1B — Measurement before optimisation: is it real, and was it predicted

**The question this phase answers:** why do most benchmarks report a number that production will never show, and how do you write one that does not?

Part A showed how to measure one run honestly: from the due time, open-loop, with its first seconds kept apart. Part A is a prerequisite. This part uses its generator, its service and its vocabulary without explaining them again.

One honest run is still not a result. Run the same code twice and the p99 moves. A change that moves it less than that proves nothing. And a number with no prediction next to it cannot be wrong, so it cannot teach you anything. This part teaches the two remaining ideas of Phase 1:

2. **A latency result is a distribution with run-to-run variance.** One run, or one percentile without its spread, cannot show that a change helped.
4. **A prediction written before the run turns a number into a finding.** The gap between prediction and measurement points at the thing you did not model.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, the previous document: what one run shows                        │
│  1.1  The distribution of one endpoint                                   │
│  1.2  Open-loop versus closed-loop                                       │
│  1.3  Warm-up and the first minute                                       │
│                                                                          │
│ PART B, this document: is it real, and was it predicted                  │
│  1.4  Baseline, one change, repeat     — is a change real                │
│  1.5  The prediction sheet             — write the number down first     │
│  Lab: E6 to E11                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**What this part assumes.** Two sections of the inference-internals course are used here. The three-sentence version of each is enough.

- **inference-internals 4.4, the paired bootstrap in `quant_gate.py`.** A bootstrap redraws your data at random many times and reads the spread of the answer. It gives an interval, not only a point. Section 1.4 adds a level above it: redraw runs first, then requests.
- **inference-internals 6.1, Little's law and the knee.** Little's law, L = λW, links the requests in a system, their arrival rate, and the time each one spends there. The utilisation ρ is the share of time the server is busy, written here as "79% busy". For one server, the mean wait in the queue is ρ / (1 − ρ) service times: 4 at 80% busy, 19 at 95%. The mean time in the system is 1 / (1 − ρ) service times: 5 and 20. Section 1.5 uses the second.

**Where it runs, and what it costs.** Everything runs on your laptop and costs nothing. The machine and versions are the same as part A: an Apple M2 with 8 GB, macOS 15.7.8, CPython 3.13.3 through uv, on 2026-09-25. The sessions differ. Lab parts D and E ran at 05:24 to 05:27 on battery, load not recorded. The service time S was measured again at 13:04, part W, on a loaded machine. Lab E8 ran seven hours later, 12:23 to 12:31, with other programs running on the laptop. Section 1.4 shows what that did.

Time for part B: 1 to 1.5 hours. About 15 minutes of that is waiting for load runs.

---
## 1.4 — Baseline, one change, repeat (is a change real?)

Why this matters: most performance changes are argued from one run before and one run after. If unchanged code moves more than your change between runs, that argument proves nothing. You need to know how much your runs move before you can say a change helped.

**Answer this first.** The course service runs at 77 requests per second. You run the unchanged code twice. One run reports p99 209 ms, the other 309 ms. A colleague then gives the handler 12% less work, runs once, and gets 128 ms. Can one run tell you whether the change helped? How many runs would convince you?

**Unchanged code moves a lot.** The lab ran the same code, at the same rate, ten times. Each run was 25 s long with a fresh service. The p99 of each run:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ p99 of 10 runs of UNCHANGED code, 77/s, 79% busy. Lab E8                 │
├──────────────────────────────────────────────────────────────────────────┤
│ run  3  ████████████████████                              159 ms         │
│ run  8  ██████████████████████                            176 ms         │
│ run  1  ██████████████████████                            178 ms         │
│ run  7  ██████████████████████████                        209 ms         │
│ run  5  █████████████████████████████                     230 ms         │
│ run  4  █████████████████████████████                     231 ms         │
│ run  9  ██████████████████████████████                    239 ms         │
│ run 10  ████████████████████████████████                  257 ms         │
│ run  2  █████████████████████████████████████             295 ms         │
│ run  6  ███████████████████████████████████████           309 ms         │
│                                                                          │
│ highest / lowest = 1.94. Nothing changed between these runs.             │
└──────────────────────────────────────────────────────────────────────────┘
```

The highest p99 is 1.94 times the lowest. The p50 moved less, from 29.0 to 41.6 ms. The tail moves most for two reasons. It rests on the fewest samples. And near the knee the queue length changes widely within a run, as section 1.3 showed.

This variance has several sources, and only some are yours to remove:

1. **The arrival sequence.** Poisson arrivals bunch up by chance, in a different second of each run.
2. **The service times.** The same distribution, different draws.
3. **The machine.** Other programs, heat and battery level. On a Mac you cannot fix the CPU frequency, so record the conditions.
4. **The process.** Address layout and hash seeds differ per process. pyperf runs 20 worker processes by default for this reason.

Fixed seeds remove the first two when you want them removed. The last two you can only measure and report.

**The method: resample runs, then requests.** One run's requests are not independent draws from "the service". They share a machine state and a stretch of queue. So an interval built by resampling requests only is too narrow. `compare_runs.py` builds a two-level bootstrap interval for the p99 change. Inference-internals 4.4 used a one-level paired bootstrap for accuracy. This adds a run level above it:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One bootstrap round, repeated 2,000 times                                │
├──────────────────────────────────────────────────────────────────────────┤
│  before runs  B1 B2 B3 B4 B5        after runs  A1 A2 A3 A4 A5           │
│       │                                  │                               │
│  1. pick 5 RUNS with replacement:   B2 B2 B4 B1 B5 ...                   │
│       │                                                                  │
│  2. inside each picked run, pick its REQUESTS with replacement           │
│       │                                                                  │
│  3. pool them, take the p99. Same for the after side                     │
│       │                                                                  │
│  4. record  p99(after) / p99(before) − 1                                 │
│                                                                          │
│  95% interval = 2.5th to 97.5th percentile of the 2,000 records          │
│  real only if the WHOLE interval is on one side of zero                  │
└──────────────────────────────────────────────────────────────────────────┘
```

Step 1, the run level, is what carries the run-to-run variance. Here it is, from `compare_runs.py:125`:

```python
# from phase01_measure/compare_runs.py, inside interval(). Type hints removed and
# one comment added, logic unchanged
def one_group(runs):
    if within_only:                               # the common mistake
        pooled = np.concatenate(runs)
        return p99(rng.choice(pooled, size=pooled.size, replace=True))
    picked = [runs[i] for i in rng.integers(0, len(runs), size=len(runs))]
    return p99(np.concatenate([rng.choice(r, size=r.size, replace=True) for r in picked]))
```

**The lab: before, after, and a control.** E8 ran three configurations at 77 requests per second:

- **before:** the 10 ms service, the baseline
- **after:** the same service with its work cut to 8.8 ms
- **control:** the unchanged 10 ms service again

Five runs each, alternated in rounds: before, after, control, then the next round. Alternation matters. If the laptop heats up or its battery drains over the 8 minutes, all three groups get the same share of it. The before and after runs of one round also used the same seed, so they saw the same arrivals.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Run order of lab E8. Each run: fresh service, 25 s, about 32 s in all    │
├──────────────────────────────────────────────────────────────────────────┤
│ time ──────────────────────────────────────────────────────►  about 8 min│
│                                                                          │
│ round 1     round 2     round 3     round 4     round 5                  │
│ B1 A1 C6    B2 A2 C7    B3 A3 C8    B4 A4 C9    B5 A5 C10                │
│                                                                          │
│ B = before, 10 ms     A = after, 8.8 ms     C = control, 10 ms           │
│ Bk and Ak share seed k: the same arrivals and relative request sizes     │
│                                                                          │
│ Blocked order B1..B5, A1..A5, C6..C10 would put any drift of the         │
│ laptop into one group, and the drift would look like the change.         │
└──────────────────────────────────────────────────────────────────────────┘
```

**One run was invalid, and the rule found it.** During E8, other programs were running on the laptop. The after-run of round 2 showed it in its own output: its generator lag p99 was 27.8 ms. The other 14 runs of E8 had 1.1 to 4.2 ms. The open-loop runs of parts A, B and E, on a quieter machine, had 2.1 to 2.5 ms. The generator had started requests late because the machine was busy, and the service ran slower for the same reason. That run's p99 was 360 ms, 22% above its paired before-run. The other four after-runs were 23 to 37% below theirs.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ p99 per round, before and after. 77/s. Lab E8                            │
├──────────────────────────────────────────────────────────────────────────┤
│ round 1  before ██████████████████                   178 ms              │
│          after  █████████████                        128 ms  0.72        │
│ round 2  before ██████████████████████████████       295 ms              │
│          after  ████████████████████████████████████ 360 ms  1.22 INVALID│
│ round 3  before ████████████████                     159 ms              │
│          after  ████████████                         122 ms  0.77        │
│ round 4  before ███████████████████████              231 ms              │
│          after  ███████████████                      147 ms  0.64        │
│ round 5  before ███████████████████████              230 ms              │
│          after  ██████████████                       145 ms  0.63        │
│                                                                          │
│ Round 2's after-run: generator lag p99 27.8 ms, the others 1.1 to 4.2 ms │
└──────────────────────────────────────────────────────────────────────────┘
```

`compare_runs.py` leaves such a run out by the rule of section 1.2. The rule is fixed before any result is read: a generator lag p99 above 10 ms makes an open-loop run invalid. Fixing the rule first matters. A rule chosen after you see which run spoils your result is a way to choose the result.

```
INVALID c-fast-2.json: generator lag p99 27.8 ms > 10 ms, left out
p99 change: -39.7% (95% interval -50.8% to -22.0%, resampling runs, then requests)
real: the whole interval is an improvement
```

With the invalid run kept, `--keep-invalid`, the same comparison says nothing:

```
p99 change: -1.4% (95% interval -48.3% to +59.0%, resampling runs, then requests)
not shown: the interval includes no change
```

One invalid run out of ten hid a 40% improvement completely. Section 1.5 predicts −39% for this change from the model.

The control against the baseline, the check that the method does not invent wins:

```
p99 change: +3.4% (95% interval -17.6% to +37.5%, resampling runs, then requests)
not shown: the interval includes no change
```

**WRONG: resample requests only.** Here is the same control comparison with `--within-only`:

```
p99 change: +3.4% (95% interval -1.8% to +7.4%, resampling requests only)
not shown: the interval includes no change
```

The verdict happens to be right this time. The interval is not. It claims the p99 is known to within ±5%, from groups whose runs spread from 159 to 309 ms. An estimate above about 5% would have been called real.

`--aa` shows how often that happens. It takes the ten no-change runs and splits them into two groups of five in all 126 possible ways. Then it compares every split. Every "real" verdict is wrong, because nothing changed:

```bash
uv run python phase01_measure/compare_runs.py --aa runs/c-base-*.json runs/c-same-*.json
```

```
10 runs of the same code, 126 ways to split them in two:
  runs, then requests  called real in  10 of 126 (8%), median interval width 54%
  requests only        called real in  86 of 126 (68%), median interval width 12%
```

**RIGHT: resample runs, then requests, and read the width.** The two-level method was wrong in 8% of the splits, near its 5% target. The requests-only method was wrong in 68%. Its intervals were less than a quarter as wide. The 126 splits reuse the same 10 runs, so these are a rough check, not measured rates.

The two-level method is not perfect either. Its inner level still treats the requests of one run as independent. And with five runs per side, its run level has few runs to draw from. Both make it slightly too narrow. The run level carries most of the variance, which is why the number of runs matters.

**How many samples a percentile needs.** Take a 95% interval for a percentile q that assumes nothing about the distribution. It needs enough samples that the largest one is above q with probability 0.975. That gives n ≥ ln(0.025) / ln(q). For p99, ln(0.025) / ln(0.99) = −3.689 / −0.01005 = 367.0, so at least 368 samples. The floor is derived here. It is not a published rule. Below it, a run cannot give any interval for its p99. So a short run at a low rate cannot support a p99 claim at all.

**The answer to the question.** One run cannot tell you. Unchanged code alone moved from 209 to 309 ms between two runs, so one 128 ms run proves nothing. Now take five alternated runs per side, with the invalid run left out by rule. The change is real: −39.7%, with a 95% interval from −50.8% to −22.0%.

**The sentence to remember:** a change is real when the interval from resampling runs, then requests, lies on one side of zero. A no-change control must not do the same.

**The trap:** resampling requests only gives an interval less than a quarter as wide as it should be. On ten runs of unchanged code it called a difference real in 68% of the splits.

**Try this now:** run `uv run python phase01_measure/compare_runs.py --before runs/c-base-1.json runs/c-base-2.json --after runs/c-fast-1.json runs/c-fast-3.json`. With two runs per side it says −53.4%, with an interval from −59.5% to −27.2%. The interval looks confident. It is not: the run level has only two runs to pick from. The estimate is 14 percentage points away from the five-run answer of −39.7%.

---
## 1.5 — The prediction sheet (write the number down first)

Why this matters: a number measured with no prediction cannot be wrong, so it cannot teach you anything. A number measured against a written prediction is either confirmed or it points at something you did not model. Every lab in the rest of this course starts with this sheet.

**Answer this first.** The course service has S = 10.25 ms of service time per request. That value comes from `warmup.py` in section 1.3. Its saved run is from 13:04, on a loaded machine, eight hours after the runs it predicts. The first measurement, made before the runs, was not saved. Before you read the table below, write down your p50 and p99 at 48, 77 and 91 requests per second.

**The sheet.** One page, written before the run, and finished after it. The loop it drives:

```
┌─────────────┐   ┌─────────────┐   ┌──────────────┐   ┌─────────────────┐
│ measure S   ├──►│ predict p50 ├──►│ run open-    ├──►│ gap = measured  │
│ one client, │   │ and p99 for │   │ loop, ≥ 5    │   │ / predicted,    │
│ no queue    │   │ each load   │   │ runs, spread │   │ per percentile  │
└─────────────┘   └─────────────┘   └──────────────┘   └────────┬────────┘
       ▲                                                        │
       │   the gap names what the model left out: fix the       │
       └─────────── model, the lab, or the system ◄─────────────┘
```

The page itself:

```markdown
PREDICTION SHEET: <endpoint>, <date>, <machine>

Service time S:      <value>, measured how
Capacity:            1 / S = <requests per second>
Load:                <rate> per second, busy share ρ = rate × S
Model and why:       <e.g. M/M/1: Poisson arrivals, one server, exponential service>
Predicted:           p50 <x>, p99 <y>, mean <z>
Run plan:            generator, open or closed, rate, duration, warm-up kept apart,
                     number of runs, seeds, order of runs
What would change my mind: <the result that would mean the model is wrong>

Measured:            p50, p99 per run, and their spread
Gap:                 measured / predicted, per percentile
Cause of the gap:    <the thing you did not model, and the check that shows it>
```

**The model for this service.** The service is a single queue. Arrivals come from an open-loop Poisson schedule. Service times are exponential by construction. One event loop serves one request at a time, in arrival order. That is the M/M/1 queue. Its response time is itself exponential, with mean S / (1 − ρ). So every percentile has a closed form:

```
mean = S / (1 − ρ)
p50  = ln 2   × S / (1 − ρ) = 0.693 × S / (1 − ρ)
p99  = ln 100 × S / (1 − ρ) = 4.605 × S / (1 − ρ)
```

This is the knee from inference-internals 6.1, applied to percentiles. Worked through at 48 requests per second:

1. ρ = 48 × 0.01025 s = 0.492.
2. S / (1 − ρ) = 10.25 ms / 0.508 = 20.18 ms. That is the mean.
3. p50 = 0.693 × 20.18 = 13.99 ms.
4. p99 = 4.605 × 20.18 = 92.9 ms.

`predict.py` does the same for every rate:

```bash
uv run python phase01_measure/predict.py --service-ms 10.25 --rate 48 77 91
```

```
util  49%: rate 48/s, p50 14 ms, p99 92.9 ms, mean 20.2 ms
util  79%: rate 77/s, p50 33.7 ms, p99 224 ms, mean 48.6 ms
util  93%: rate 91/s, p50 106 ms, p99 702 ms, mean 152 ms
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Predicted p99 against utilisation. M/M/1, S = 10.25 ms                   │
├──────────────────────────────────────────────────────────────────────────┤
│  30%      ███ 67 ms                                                      │
│  49% 48/s ████ 93 ms                               ◄ 91 measured         │
│  60%      █████ 118 ms                                                   │
│  70%      ███████ 157 ms                                                 │
│  79% 77/s ██████████ 224 ms                        ◄ 231 measured        │
│  85%      ██████████████ 315 ms                                          │
│  90%      ██████████████████████ 472 ms                                  │
│  93% 91/s ████████████████████████████████ 702 ms  ◄ 277 measured        │
│                                                                          │
│ The same 1 ms of extra service time costs more the closer ρ is to 1.     │
│ At 93% the measured runs were 23 s long: too short for this tail.        │
└──────────────────────────────────────────────────────────────────────────┘
```

**Predicted against measured.** Each measured value is the median over its runs. Every run was 25 s long, open-loop, with the first 2 s kept apart:

| Load | Runs | Predicted p50 | Measured p50 | Predicted p99 | Measured p99 | Measured p99 range |
|---|---|---|---|---|---|---|
| 48/s, 49% busy | 3 | 14.0 ms | 15.9 ms | 92.9 ms | 91.1 ms | 90.9 to 92.8 ms |
| 77/s, 79% busy | 10 | 33.7 ms | 33.2 ms | 224 ms | 231 ms | 159 to 309 ms |
| 77/s, work cut to 8.8 ms | 4 valid of 5 | 20.7 ms | 22.4 ms | 137 ms | 136 ms | 122 to 147 ms |
| 91/s, 93% busy | 3 | 106 ms | 66.6 ms | 702 ms | 277 ms | 233 to 325 ms |

**Reading the gaps.** Name a cause for each gap, or say that it is noise:

- **At 49% busy the p99 matches within 2%.** The p50 is 2 ms higher than predicted. That is not explained. The three runs' p50s spread from 14.6 to 16.3 ms, and at 77/s the p50 is 0.5 ms below the model. Treat a 2 ms p50 gap as noise until more runs show it.
- **At 79% busy the median run matches within 3%**: 231 ms against 224 ms, over ten runs. The service with less work matches too: 136 ms measured against 137 ms predicted. Single runs spread widely around the median. Section 1.4 deals with that spread.
- **At 93% busy the measured p99 is 39% of the prediction.** This is the short-run effect of section 1.3. Simulated 23-second runs at this load give a median p99 of 385 ms and a range of 180 to 863 ms. The three measured runs, 233 to 325 ms, sit inside that range. The model is not wrong. The runs are too short for the tail it describes. The p50 is low for the same reason: 66.6 ms against 106 ms, because short runs seldom reach a deep queue.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Measured p99 as a share of predicted p99, measured / predicted in ms     │
├──────────────────────────────────────────────────────────────────────────┤
│ 49% busy     ████████████████████████████████████████    98%   91 / 93   │
│ 79% busy     ██████████████████████████████████████████ 103%  231 / 224  │
│ 93% busy     ████████████████                            39%  277 / 702  │
│                                                                          │
│ Model and measurement agree until the run is too short for the tail.     │
└──────────────────────────────────────────────────────────────────────────┘
```

**A gap that showed a bug.** The first time this lab ran, the prediction and the measurement did not agree at all. At 77 requests per second the model said p99 224 ms. The service measured 57 ms:

```
# WRONG: the generator and the service seeded random.Random(1) in both processes
open 77/s poisson, timer=due, raw  n=  1750  mean   25.3 ms  p50   23.4 ms  p90   40.0 ms  p99   57.1 ms  p99.9   65.5 ms  max   69.7 ms
```

A service that beats its model by a factor of four is suspicious. Its max, 69.7 ms, was no larger than the longest single service time you expect from 1,750 exponential draws. So no long request ever waited in a queue. The cause: the generator drew its arrival gaps from `random.Random(seed)`, and the service drew its service times from `random.Random(seed)`, with the same seed. Both processes drew the same sequence. Request i arrived after a gap of E_i / 77 and needed E_i / 100 of work:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Why a shared random sequence removed the tail. Example values            │
├──────────────────────────────────────────────────────────────────────────┤
│ both processes draw  E1 = 0.2   E2 = 3.1   E3 = 0.5   E4 = 2.4           │
│                                                                          │
│ generator: gap before request i = E_i / 77 s                             │
│            2.6 ms     40 ms      6.5 ms     31 ms                        │
│ service:   work of request i     = E_i / 100 s                           │
│            2 ms       31 ms      5 ms       24 ms                        │
│                                                                          │
│ Request 2 needs 31 ms of work. It arrives 40 ms after request 1,         │
│ which needed 2 ms. It finds the server idle and never waits.             │
│ Every long request arrives after a long gap in the same way.             │
│                                                                          │
│ The tail is made of long requests that also waited. Here the long        │
│ ones never wait, so the tail shrinks to the longest service time.        │
└──────────────────────────────────────────────────────────────────────────┘
```

Short requests that came right after a long one did wait, which is why the p50 was still 23 ms. The tail lost the long requests that also waited.

A simulation confirmed it before any code changed. `predict.py --shared-seed-check` runs the same queue with one shared sequence and with two independent ones, over 8 seeds:

```bash
uv run python phase01_measure/predict.py --service-ms 10 --rate 77 --run-seconds 25 --shared-seed-check
```

```
shared       8 seeds, 25 s at 77/s: p99 54 to 63 ms  [54, 54, 55, 57, 58, 60, 60, 63]
independent  8 seeds, 25 s at 77/s: p99 161 to 219 ms  [161, 166, 180, 195, 195, 198, 206, 219]
```

```python
# RIGHT: shared/rng.py:40. Each purpose gets its own stream.
def stream(purpose: str, seed: int) -> random.Random:
    # The purpose is part of the seed, so equal seeds for different purposes
    # never give equal sequences.
    return random.Random(f"{purpose}:{seed}")
```

The load generator's self-test now checks it. It computes the correlation between one seed's arrival gaps and its service times, and fails if it is above 0.05. With the fix the correlation is −0.004. Without it, it is exactly 1.0.

Without a prediction, 57 ms would have looked like a fast service. The prediction turned it into a finding.

**What 12% less work does near the knee.** The same sheet answers the question from section 1.4. Cutting the work from 10 ms to 8.8 ms cuts S from 10.25 to 9.05 ms, 12% less. It also cuts ρ at 77 per second from 0.789 to 0.697. The p99 scales with S / (1 − ρ), so it falls from 224 ms to 137 ms, 39% lower. So 12% less work gives a 39% lower p99 at this load. At 10% busy the same change would lower the p99 by about 13%. The closer to the knee, the more a small change in service time moves the tail, in both directions.

**Where this model stops.** Real handlers do not have exponential service times. A service with several workers or several resources is not one queue. Retries and timeouts feed load back into the queue. Phase 2 measures each of these. The sheet stays the same. Only the model line changes.

**The sentence to remember:** write the prediction before the run. A measurement that disagrees with it points at what you did not model.

**The trap:** a result that is better than the model is also a gap. Here a shared random sequence kept the long requests from ever waiting, and the lab would have taught the wrong lesson from it.

**Try this now:** fill in the sheet for 85 requests per second before you run anything. Then run `uv run python phase01_measure/predict.py --service-ms 10.25 --rate 85 --short-runs 40 --run-seconds 23` and compare its range with your guess.

---
## 🧪 Hands-on lab — part B

**Run status:** every command below was executed on the author's machine on 2026-09-25, in the sessions listed in part A. During the E8 runs, other programs were also running on the laptop. One run shows it, and section 1.4 uses that. Each "Expected" line is copied from the saved logs: `runs/lab.log` for D and E, `runs/lab-c.log` for E8 and the comparisons.

All commands run from `elite-performance/code/`.

- [ ] **E6 (offline).** The prediction sheet numbers.
  - Run: `uv run python phase01_measure/predict.py --service-ms 10.25 --rate 48 77 91`.
  - Expected: `util  49%: rate 48/s, p50 14 ms, p99 92.9 ms`, `util  79%: rate 77/s, p50 33.7 ms, p99 224 ms`, and `util  93%: rate 91/s, p50 106 ms, p99 702 ms`.
  - Then check the formula against a simulation of the same queue: add `--simulate`.
  - Expected: `simulated: p50 14 ms, p99 92.8 ms` at 49% busy and `simulated: p50 33.3 ms, p99 232 ms` at 79%. At 93% busy it prints `simulated: p50 105 ms, p99 901 ms`, far from the formula's 702 ms. Even 180,000 simulated requests at 93% busy have not settled. That is the effect of section 1.3.
  - Teaches: M/M/1 gives every percentile in closed form, and near the knee even a long simulation needs care.

- [ ] **E7 (local).** Measure the service time, fill the sheet, and measure the sheet.
  - First write your sheet for 48 and 91 requests per second.
  - Run: `bash runs/lab.sh D E`. About 4 minutes.
  - Expected: `closed x1 ... mean   11.0 ms  p50   7.83 ms ... p99   46.1 ms`. At 48/s the p99 was `92.8`, `90.9` and `91.1 ms`. At 91/s it was `233`, `277` and `325 ms`.
  - The closed client measures 11.0 ms because it adds the httpx client's own time. `warmup.py`, with a raw socket, measures the service at 10.25 ms. Use that one.
  - Then write the gap line of your sheet, and name the cause of each gap.
  - Teaches: a prediction turns a number into a finding.

- [ ] **E8 (local).** Before, after and a control, alternated.
  - Run: `bash runs/lab.sh C compare`. About 8 minutes of runs, 9 with the comparisons.
  - Expected, before against after: `INVALID c-fast-2.json: generator lag p99 27.8 ms > 10 ms, left out`, then `p99 change: -39.7% (95% interval -50.8% to -22.0%, resampling runs, then requests)`. Before against control: `p99 change: +3.4% (95% interval -17.6% to +37.5%, ...)` and `not shown`.
  - Your runs will differ. On a quiet machine, none may be invalid. Add `--keep-invalid` to a comparison to see what an invalid run does to it.
  - Teaches: a change is real when the interval from runs, then requests, excludes zero, and a control's does not.

- [ ] **E9 (break-it, offline).** Resample requests only.
  - Run: `uv run python phase01_measure/compare_runs.py --aa runs/c-base-*.json runs/c-same-*.json`. It needs the runs from E8.
  - Expected: `runs, then requests  called real in  10 of 126 (8%)` and `requests only        called real in  86 of 126 (68%)`.
  - What broke: every "real" verdict here is wrong, because all ten runs are the same code.
  - Teaches: an interval that ignores run-to-run variance is too narrow, and calls noise a win.

- [ ] **E10 (break-it, offline).** Give the generator and the service the same random sequence.
  - First keep a copy: `cp shared/rng.py /tmp/rng.py.bak`.
  - Run: `sed -i '' 's/return random.Random(f"{purpose}:{seed}")/return random.Random(seed)/' shared/rng.py`, then `uv run python shared/rng.py --self-test`.
  - Expected: `AssertionError: 1.0`. The two streams are now identical. `uv run python phase01_measure/loadgen.py --self-test` fails for the same reason.
  - Restore it with `cp /tmp/rng.py.bak shared/rng.py`. Do not skip this: every later lab would share one random sequence. The self-test must then print `arrivals:3 with service:3: -0.004`.
  - Teaches: a lab's randomness is part of its design. A shared sequence removed the queue this phase measures.

- [ ] **E11 (written).** A prediction sheet for an endpoint you own.
  - Pick one endpoint. Measure its service time with one client, one request at a time, as `warmup.py` does.
  - Write the sheet for 50% and 80% of its capacity. Plan at least 5 runs per setting, alternated, and state the run length that E5's short-run check says you need.
  - Teaches: the sheet is the habit the rest of this course depends on.

---

## 🔍 Check it yourself

1. Open `phase01_measure/compare_runs.py:129`. This line picks runs with replacement. It is the run level of the bootstrap. Suppose the next line used `runs` instead of `picked`. What happens to the interval, and which flag already does something close to that?

2. Open `shared/rng.py:40`. This is `stream`, which puts the purpose into the seed. The generator calls it at `phase01_measure/loadgen.py:185` and the service at `phase01_measure/service.py:78`. Why does changing only one of those two calls to `random.Random(seed)` create no problem, while changing `stream` itself breaks the lab?

3. Open `phase01_measure/compare_runs.py:82`. This is `LAG_LIMIT_MS`. The rule leaves out runs above it. Why must this number be written down before any run is compared, and what would you be doing if you raised it after seeing a result?

---

## ✅ Checkpoint 1B — answer in your own words

1. **Is a 12% improvement real?** Ten runs of unchanged code at 79% busy gave p99 values from 159 to 309 ms. A teammate changes the JSON encoder, runs the test once before and once after, and reports a p99 12% lower: from 229 ms to 202 ms. (a) Argue for or against the claim, with numbers. (b) What would you run instead, and what result would convince you? (c) Suppose the change gives the handler 12% less work. What p99 change do you predict at this load, and why is it larger than 12%?

2. **A colleague says:** "One of my ten runs was far slower than the others. It is an outlier, so I dropped it, and now the change is significant." Argue for or against. What would make dropping it acceptable?

3. **Show the arithmetic.** An endpoint has S = 4 ms and one worker. (a) Predict p50 and p99 at 200 requests per second. (b) Traffic grows 15%, to 230 per second. Predict the p99 again. (c) What does that tell you about where to set an alert?

4. **This is broken.** Your prediction for an endpoint at 80% busy was p99 200 ms. Five runs measured 50 to 60 ms, all with a max close to the longest single request. List three causes that would make a measurement beat its model, and the check for each.

5. **Design the run plan.** An endpoint has a measured service time of 2.5 ms and one worker. You must report its p99 at 300 requests per second, and then whether a change helps. Write the prediction line of the sheet with the arithmetic. Then write the plan: generator, run length, warm-up, number of runs, order, validity rule, and what would change your mind.

<details>
<summary>Answer sketches</summary>

1. (a) Against. One run each, and unchanged code alone spread from 159 to 309 ms. A 12% difference is well inside that spread. (b) At least 5 runs each, alternated, with fixed seeds, a no-change control, and the interval from `compare_runs.py`, which resamples runs, then requests. Convincing: the whole interval below zero, and the control's interval across zero. (c) p99 ∝ S / (1 − ρ). S falls from 10.25 to 9.05 ms, and ρ from 0.789 to 0.697. So 224 ms falls to 137 ms, which is −39%. Near the knee the factor 1 / (1 − ρ) amplifies any change in S. The lab measured −39.7%, with an interval from −50.8% to −22.0%.

2. Against, as stated. A run dropped because of its result lets you choose the result. Section 1.4 showed one bad run can move an interval from "real" to "not shown", so the reverse is also possible. Acceptable only by a rule written before any comparison, based on the run's own validity, such as generator lag p99 above 10 ms. The rule then applies to every run in both groups.

3. (a) ρ = 200 × 0.004 = 0.8. S / (1 − ρ) = 4 / 0.2 = 20 ms. p50 = 0.693 × 20 = 13.9 ms. p99 = 4.605 × 20 = 92.1 ms. (b) ρ = 0.92. 4 / 0.08 = 50 ms. p99 = 230 ms. (c) 15% more traffic gave 2.5 times the p99. Alert on utilisation or queue depth, which move before the tail does. An alert on p99 fires after users already feel it.

4. First, the generator and the service share randomness, as in section 1.5. Check the correlation between arrival gaps and service times. Second, the generator is closed-loop, or measures from the send. Check `sent/s` against the planned rate, and the timer. Third, the load never reached the service: a cache, a proxy, or errors answered early. Check the error count, and the service's own request counter against the generator's.

5. ρ = 300 × 0.0025 = 0.75. S / (1 − ρ) = 2.5 / 0.25 = 10 ms. p50 = 6.9 ms. p99 = 4.605 × 10 = 46 ms. Plan: open-loop Poisson at 300 per second, latency from the due time. Keep the first 5 s apart. Check the run length with `predict.py --short-runs` until the median run p99 is within about 10% of 46 ms. Five runs per configuration, alternated with a no-change control, with fixed seeds. Validity rule, written first: generator lag p99 above 10 ms makes a run invalid. Change my mind: a median p99 far from 46 ms, or a spread wider than the short-run simulation.

</details>

---

## References & Further Learning — part B

Every URL below was fetched on 2026-09-25 and returned HTTP 200.

**Variance and how many samples**

- **pyperf, "Run a benchmark", at tag 2.10.0** — https://raw.githubusercontent.com/psf/pyperf/2.10.0/doc/run_benchmark.rst
  Focus on: why pyperf spawns 20 worker processes, and its advice on warm-ups. The best short argument that one run is not a result.
- **SciPy `scipy.stats.bootstrap`** — https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html
  Focus on: the `paired` parameter, and what a bootstrap interval promises about coverage.
- **Reddi et al., "MLPerf Inference Benchmark", ISCA 2020** — https://ar5iv.labs.arxiv.org/html/1911.02549
  Focus on: Section III-D and Table IV. How many queries a tail percentile needs for a stated margin: 262,742 for a p99 at 99% confidence.
- **Apple, Energy Efficiency Guide for Mac Apps, "Extend App Nap"** — https://developer.apple.com/library/archive/documentation/Performance/Conceptual/power_efficiency_guidelines_osx/AppNap.html
  Focus on: timer throttling and priority reduction. One reason a laptop run needs its conditions written down. An archive document, updated 2016.

**The queueing model**

- **M/M/1 queue, Wikipedia** — https://en.wikipedia.org/wiki/M/M/1_queue
  Focus on: the response time section. With first-come, first-served order, the time in the system is exponential with rate μ − λ, which gives every percentile in section 1.5. A secondary source. It is used here because the result is standard and the page states it plainly.
- **Schroeder, Wierman, Harchol-Balter, "Open Versus Closed: A Cautionary Tale", NSDI 2006** — https://www.usenix.org/legacy/event/nsdi06/tech/full_papers/schroeder/schroeder.pdf
  Focus on: Section 5.1. Why the open model is the one to predict with when users arrive on their own.

---

## Cheatsheet — part B

```
IS THE CHANGE REAL
  runs          ≥ 5 per side, alternated, fixed seeds, a no-change control
  interval      resample runs, then requests. Real only if it excludes 0
  requests only too narrow: 68% false wins on 10 no-change runs, vs 8%
  invalid run   generator lag p99 > 10 ms. Rule fixed before reading results
  one bad run   hid a −40% change: interval −48% to +59% with it kept
  samples       a p99 interval needs ≥ 368 samples in the run

PREDICT FIRST   M/M/1: Poisson arrivals, one server, exponential service
  ρ = rate × S          mean = S/(1−ρ)
  p50 = 0.693 S/(1−ρ)   p99 = 4.605 S/(1−ρ)
  S = 10.25 ms  48/s → p99 93 ms   77/s → 224 ms   91/s → 702 ms
  measured      91 ms              231 ms           277 ms, runs too short
  12% less work at 79% busy → p99 −39%. Measured −39.7%

THE GAP IS THE FINDING
  better than the model  suspect the lab: shared randomness, closed loop,
                         load that never reached the service
  random streams         one per purpose: stream("arrivals", seed)
  shared seed            long requests never wait: p99 57 ms, not 224
```

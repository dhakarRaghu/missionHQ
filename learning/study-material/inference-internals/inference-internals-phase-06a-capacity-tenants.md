# Phase 6A — Sizing the fleet and sharing it

This is the final phase of Module 1. It has two parts.

This part answers two questions that section 4.6 left open. How many replicas do you need? And when several tenants share them, who gets served first?

Section 4.6 computed the cost per token at a given utilisation. It assumed you already knew the fleet size. This part computes that size from measured numbers, and then shows why a correctly sized fleet can still fail one tenant.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  6.1  Capacity planning   — queueing, headroom, cold start, autoscaling  │
│  6.2  Many tenants        — quotas, fair scheduling, cache isolation     │
└──────────────────────────────────────────────────────────────────────────┘
```

Phase 4B is a prerequisite, because `capacity_plan.py` imports its cost formula. Phase 5A is also a prerequisite, because section 6.2 uses its rate-limit material.

Every exercise runs offline and costs $0.

Time: 2 to 3 hours.

---

## 6.1 — Capacity planning (how many replicas, from your own numbers)

Why this matters: section 4.6 answered "should we self-host?" by computing cost per token at a given utilisation. It assumed you already knew how many GPUs to buy. This section answers that question, and the obvious answer is wrong.

### The obvious plan, and why it fails

The obvious plan divides peak traffic by what one replica can serve. Here it is, with numbers from the course script:

```
python phase06_design/capacity_plan.py
```

```
one replica: 32 slots x (1 / 4.0s) = 8.00 requests/sec at 100% utilisation
peak demand: 22.8 requests/sec
the NAIVE plan: ceil(22.8 / 8.00) = 3 replicas, running at 95%
```

A slot here is one request the replica can serve at the same time while staying inside your latency target. You measure it with Phase 4A's benchmark client, under load.

Now hold those three replicas fixed and raise the load:

```
THE KNEE — the naive fleet of 3 replicas (96 slots) as load rises
┌─────────────┬──────────────┬──────────────────┐
│ utilisation │ P(must wait) │ mean queue wait  │
├─────────────┼──────────────┼──────────────────┤
│         50% │         0.0% │              0ms │
│         80% │         2.2% │              5ms │
│         90% │        22.5% │             94ms │
│         95% │        51.4% │            429ms │
│         98% │        77.9% │           1624ms │
│         99% │        88.5% │           3688ms │
└─────────────┴──────────────┴──────────────────┘
```

Waiting time is not proportional to utilisation. It stays near zero, then climbs steeply in the last few percent. The naive plan lands at 95%, where half of all requests queue and the mean wait is 429 milliseconds before the first token can even start.

### The mathematics, in three lines

You do not need a queueing course. You need three results.

**Little's Law.** The average number of requests in a system equals the arrival rate times the average time each one spends there: `L = λW`. Its author's own retrospective states that it holds whatever the queue discipline, and even when conditions change over time. It is the one law in this section with almost no assumptions.

**One server.** For a single server with random arrivals and random service times, mean waiting time in units of mean service time is `ρ / (1 − ρ)`, where ρ is utilisation:

```
  utilisation   50%    70%    80%    90%    95%
  mean wait     1      2.3    4      9      19      (in service times)
```

At 95%, a request waits 19 times as long as it takes to serve. A widely read engineering blog describes things getting "a little crazy around 80% utilization", which is where this curve starts to bend. That rule comes from a blog, not from a textbook, and it is about a **single** server.

**Many servers.** The Erlang C formula gives the probability that an arrival has to wait when c identical servers share one queue. `capacity_plan.py` implements it, and its self-test checks it against a published textbook table:

```
  c servers at 90% utilisation    P(wait)    mean wait
     1                            0.90       9.00
     2                            0.85       4.26
     5                            0.76       1.53
    10                            0.67       0.67
    20                            0.55       0.28
```

Read that table carefully. At the **same** 90% utilisation, twenty servers sharing one queue wait about thirty times less than one server. This is called pooling, and it is why "keep everything under 80%" is too conservative for a large fleet and too loose for a small one. The right utilisation depends on how many servers share the queue.

**One implementation note.** The textbook form of Erlang C contains `a^c / c!`, which overflows a floating-point number long before realistic fleet sizes. My first version overflowed at 2,000 servers. The script now uses the Erlang B recursion, whose every intermediate value stays between 0 and 1, and a self-test covers it. This is the whole calculation, from `capacity_plan.py:60`:

```python
def erlang_c(c: int, a: float) -> float:
    # c servers, offered load a = arrival rate / per-slot service rate
    if a <= 0:
        return 0.0
    if a >= c:
        return 1.0                      # unstable: the queue grows without bound
    b = 1.0
    for k in range(1, c + 1):
        b = a * b / (k + a * b)         # Erlang B, always between 0 and 1
    return c * b / (c - a * (1 - b))    # convert B to C: P(an arrival waits)


def queue_wait_s(c: int, arrival: float, service: float) -> float:
    a = arrival / service
    if a >= c:
        return math.inf
    return erlang_c(c, a) / (c * service - arrival)   # mean wait in the queue
```

The comments are shortened from the file. The logic is the same, line for line.

Worked example with the default numbers. One replica has 32 slots, and each request takes 4 seconds, so `service` is 0.25 per second. Three replicas give `c = 96`. At 22.8 requests per second, `a = 22.8 / 0.25 = 91.2`, which is 95% of 96. The script prints a mean queue wait of 429ms for that point.

### This model is optimistic, and you should say so

Erlang C assumes arrivals are random in the Poisson sense and service times are exponential. Real LLM traffic breaks both.

**Arrivals are burstier.** ServeGen, a study of production traces from Alibaba's model service, found that language-model traffic has a coefficient of variation above 1 in 20-minute windows. The **coefficient of variation** is the standard deviation divided by the mean. A Poisson process has exactly 1. So a Poisson model understates the bursts. The same study found that reasoning-model traffic stays close to 1 or below.

**Service times vary more.** For a single server, the standard result is that mean waiting time depends on the **variance** of service time, not just its mean. LLM output lengths vary enormously, from a handful of tokens to thousands, so the variance is large. That link between the formula and LLM traffic is inferred. No LLM paper found in the research states it that way.

So treat the script's replica count as a **floor**. Replay a real trace with Phase 4A's benchmark client before you commit money.

### Traffic has a shape, and it is not flat

DynamoLLM measured a public week-long Azure trace from May 2024:

```
  conversation traffic   peak = 1.7x the average
  coding traffic         peak = 2.8x the average, and 34.6x the quietest period
```

Coding traffic also had a clear daily pattern and much lower load at weekends. The same public dataset is available for you to download and replay.

ServeGen, the burstiness study above, reported that out of 2,412 clients, the top **29** sent 90% of the requests. Section 6.2 uses that fact, because it means a few tenants dominate a shared deployment.

### Plan in work, not in requests

The Google SRE book's chapter on handling overload warns that modelling capacity as queries per second often makes for a poor metric, because different queries can have very different resource requirements. For an LLM the difference is large. An 8,192-token prompt is 16 times the prefill tokens of a 512-token prompt, and prefill attention grows faster than the token count.

The better planning unit comes from the disaggregated-serving research. **Goodput** is the maximum request rate a GPU can serve while still meeting the latency targets for a chosen share of requests, for example 90%. Raw throughput with no latency target attached is not a capacity number.

That research also sizes prefill and decode separately, because they are different kinds of work (Phase 2). In its worked example on a 13B model, one GPU running both phases served about 1.6 requests per second within target. Two prefill GPUs plus one decode GPU served 10, which is 3.3 per GPU, about 2.1 times more. If you run a disaggregated deployment, plan each pool on its own.

### Redundancy: N+1 and N+2

The Google SRE book recommends capacity for a planned and an unplanned outage at the same time. This is called **N+2**. It means enough capacity for peak, plus one replica being upgraded, plus one replica that fails during the upgrade.

The published worked example is worth copying exactly. One backend handles about 100 queries per second, expected peak is about 3,470, so the minimum is 35 tasks. The team runs **at least 37**. In one small region, the same source accepts N+1 instead, because the overhead of N+2 is too large relative to the traffic.

The script defaults to N+1 and takes `--redundancy 2` if you want the stricter version.

### Adding capacity is slow, so some headroom must already be standing

The same source gives the rule that decides how far ahead you must plan: the demand forecast must extend **beyond the lead time required for acquiring capacity**.

For a GPU replica, the lead time is measured in minutes, and the measurements are sobering:

```
┌──────────────────────────────┬────────────┬──────────────────────────────────┐
│ step                         │ measured   │ conditions                       │
├──────────────────────────────┼────────────┼──────────────────────────────────┤
│ whole cold start             │ ~317 s     │ 8B model, one A100; image pull   │
│                              │            │ 44% of it, engine startup 56%    │
│ image pull alone             │ ~236 s     │ a 28 GB serving image, one L4    │
│ weight load, default loader  │ ~48 s      │ 8B model, 15 GB, one A10G        │
│ weight load, streaming loader│ ~5 s       │ same model, loaded from S3       │
│ serverless cold start        │ 324 s → 91s│ 32B FP8 on 2 GPUs, after four    │
│                              │            │ configuration changes            │
└──────────────────────────────┴────────────┴──────────────────────────────────┘
```

I could not find a primary source with a measured time to provision the GPU node itself, so those numbers start after the machine exists.

While a new replica boots, demand keeps rising, and the replicas you already have must absorb that rise alone. The script computes the headroom that forces:

```
python phase06_design/capacity_plan.py --scale-up-s 320 --ramp-rps-per-min 1.5
```

```
scale-up takes 320s. Demand can rise 8.0 rps in that time.
to absorb it without waiting for new replicas: 1 more replica(s) of standing headroom.

final fleet: 6 replicas = 6 GPUs = $15,286/month
utilisation at today's peak: 48%.
```

**Every second you remove from cold start is capacity you no longer have to keep idle.** That is the business case for the loading optimisations in the table.

### Autoscale on the queue, not on the GPU

GPU utilisation is the obvious autoscaling signal, and it is the wrong one. Three sources agree:

- The AWS EKS inference guide says GPU utilisation shows **whether** the GPU is busy, not **how** busy it is. It adds that vLLM can stay near 100% across a wide range of load.
- The GKE autoscaling guide says GPU utilisation does not measure how much work is done while the GPU is active.
- The llm-d autoscaling guide says utilisation is often near 100% during batching, whatever the actual load.

```
# WRONG: scale on GPU utilisation. A batching engine sits near 100% whether
# it is barely loaded or badly overloaded, so this either never fires or
# fires constantly.
metric: DCGM_FI_DEV_GPU_UTIL
target: 80

# RIGHT: scale on the queue. Requests waiting is the direct measure of
# "we do not have enough capacity right now".
metric: vllm:num_requests_waiting
target: 5
```

The published guidance ranks the signals: **queue depth first**, then p95 latency or time to first token, then KV-cache usage as a backstop. Published starting points:

- The vLLM production-stack autoscaling example scales on a waiting-request threshold of 5.
- Google Cloud suggests starting with a queue target between 3 and 5.
- AWS suggests scaling out when the queue stays above 25 for 30 to 60 seconds, with p95 latency above 5 seconds as a second trigger. It scales in only when the queue is empty and p95 is under 3 seconds for 5 minutes.

This is the autoscaling block from the vLLM production-stack example, copied from its documentation on 2026-09-17. It is Helm values for the stack's chart, and KEDA turns it into a scaling rule. **KEDA** is a Kubernetes autoscaler that can scale on any Prometheus query.

```yaml
keda:
  enabled: true
  minReplicaCount: 1
  maxReplicaCount: 3
  pollingInterval: 15
  cooldownPeriod: 360
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://vllm-kube-prometheus-stack-prometheus:9090
        metricName: vllm:num_requests_waiting
        query: vllm:num_requests_waiting
        threshold: '5'
```

Not run in this course, because it needs a Kubernetes cluster with GPUs. The KEDA reference documentation, checked on 2026-09-17, defines the two timing values:

- `pollingInterval: 15` is how often KEDA checks the trigger. KEDA controls this interval when scaling from 0 to 1.
- `cooldownPeriod: 360` is how long KEDA waits after the last active trigger before it scales back to 0. It applies only to scaling to 0.
- Scaling from 1 to N replicas is handled by the Kubernetes horizontal pod autoscaler, which has its own timing. The cold-start numbers above still apply to every new replica.

Two rules from the site-reliability material tie it together: autoscale **before** load shedding starts, and keep a minimum number of instances in each location so failover has somewhere to go.

**The sentence to remember:** plan on the queue, not the average, because waiting time stays flat and then explodes, and a small fleet reaches that point much sooner than a large one.

**The trap:** planning with "peak divided by capacity". It lands the fleet at the steep part of the curve, and it ignores bursts, variable request sizes, failures, and the minutes a new replica takes to start.

**Try this now:** run `python phase06_design/capacity_plan.py --slots 8 --peak-rps 5.7` and compare the naive fleet's wait against the default run. Fewer slots per replica means less pooling, and the same utilisation waits much longer.

---

## 6.2 — Many tenants on one fleet (quotas and noisy neighbours)

Section 6.1 sized the fleet for the total load. This section decides who gets that capacity when the total is more than the fleet can serve.

A **tenant** is one customer, team, or feature that shares the fleet with others. A **noisy neighbour** is a tenant whose traffic makes the service slower for the other tenants.

This is the normal case, not a rare one. ServeGen, the trace study from section 6.1, found that 29 of 2,412 clients sent 90% of the requests.

The answer first: count what each tenant consumes in tokens, not in requests. Then limit it at two places. The gateway limits how much a tenant may send. The scheduler decides whose waiting request runs next.

### Why this is harder for LLMs than for a normal API

In a normal API, requests cost about the same. Counting requests is a good proxy for load.

An LLM request does not have a fixed cost. Phase 1 showed that prefill work grows with prompt length and decode work grows with output length. The prompt of one 8,000-token request is as much prefill work as the prompts of sixteen 500-token requests.

So a limit of "100 requests per minute" says almost nothing about load. One tenant can stay inside it and still use most of the fleet.

```
  the same "one request" from three tenants, in server work
  work = prompt tokens + 2 x output tokens  (the simulation's weighting)

  heavy   8,000 prompt + 400 output   ████████████████████████████  8,800
  busy      500 prompt + 150 output   ███                             800
  light     300 prompt + 150 output   ██                              600

  a scheduler that counts requests treats these three bars as equal
```

The factor of 2 for output tokens is a modelling choice. It says that a decode token costs more than a prompt token. The VTC paper, described below, uses the same weights of 1 and 2 in its experiments, and says they follow API pricing. The real ratio of server time depends on the engine and the hardware.

### The two layers: quota at the gateway, fairness in the scheduler

Two separate mechanisms protect tenants. They answer different questions.

```
  tenant A ─┐
  tenant B ─┼──►  GATEWAY  ─────────►  SCHEDULER  ─────►  GPU replicas
  tenant C ─┘     quota                fair ordering
                  "may you send        "whose waiting request
                   this at all?"        runs next?"
                  rejects with 429     reorders, never rejects
                  per tenant, per      works only when a queue
                  minute, in tokens    exists
```

- A **quota** is a hard limit on how much a tenant may send in a time window. The gateway rejects anything above it, usually with HTTP 429. Sections 5.2 and 5.3 covered how a client should handle 429.
- A **fair scheduler** decides the order in which waiting requests start. It never rejects anything. It only matters when requests are waiting, which means the fleet is full.

You need both. A quota alone does not help when every tenant is under quota but the sum is above capacity. A fair scheduler alone does not stop one tenant from building an endless backlog.

**The rule for quotas:** set them in tokens per minute, not only in requests per minute. The hosted providers do this. Section 5.2 showed their limits, which include input and output tokens per minute next to requests per minute.

A requests-per-minute limit has a second cost. It blocks a busy tenant even when the server is idle. The VTC paper measured this on a real chat trace, served by one Llama-2-7b model on one A10G GPU. Verified from the paper, Table 2:

| policy | throughput, input plus output tokens per second | largest service gap between clients |
|---|---|---|
| RPM limit of 5 | 340 | 143.86 |
| RPM limit of 30 | 747 | 693.66 |
| fifo, no limit | 777 | 759.97 |
| VTC | 779 | 368.40 |

A tight RPM limit gives a small gap but wastes more than half the server. A loose one wastes little and gives almost no fairness. VTC gets the full throughput and halves fifo's gap.

### Three schedulers on one overloaded server

`fair_queue_sim.py` runs one server with three tenants. The offered load is 172% of capacity, so a queue always exists. The three tenants are:

| tenant | rate | prompt tokens | output tokens | share of demand |
|---|---|---|---|---|
| heavy | 8 rps | 8,000 | 400 | 68% |
| busy | 40 rps | 500 | 150 | 31% |
| light | 1 rps | 300 | 150 | 1% |

The heavy tenant asks for more than the whole server. The busy tenant asks for 53% of it, slightly more than half. The light tenant asks for almost nothing. The simulation tries three admission policies:

- **fifo.** First come, first served, across all tenants.
- **rr.** Round robin by request. Each tenant with a waiting request takes one turn.
- **vtc.** Fair by tokens. The scheduler always admits the tenant that has received the fewest tokens of service so far. This is the idea behind the Virtual Token Counter scheduler, published by Sheng and others at OSDI 2024.

Run: `python phase06_design/fair_queue_sim.py`. The output, averaged over three random seeds:

```
┌────────┬──────────┬───────────────┬──────────────┬───────┬──────┐
│ policy │ tenant   │ mean TTFT     │ p99 TTFT     │ share │ done │
├────────┼──────────┼───────────────┼──────────────┼───────┼──────┤
│ fifo   │ heavy    │       15.46 s │      29.15 s │  68%  │  254 │
│        │ busy     │       14.13 s │      28.13 s │  31%  │ 1299 │
│        │ light    │       15.25 s │      27.23 s │   1%  │   32 │
├────────┼──────────┼───────────────┼──────────────┼───────┼──────┤
│ rr     │ heavy    │        9.74 s │      16.80 s │  90%  │  347 │
│        │ busy     │       22.39 s │      49.78 s │   9%  │  394 │
│        │ light    │        0.19 s │       0.45 s │   1%  │   57 │
├────────┼──────────┼───────────────┼──────────────┼───────┼──────┤
│ vtc    │ heavy    │       19.80 s │      37.68 s │  50%  │  178 │
│        │ busy     │        5.89 s │      11.22 s │  49%  │ 1983 │
│        │ light    │        0.12 s │       0.17 s │   1%  │   57 │
└────────┴──────────┴───────────────┴──────────────┴───────┴──────┘
```

TTFT is time to first token. `share` is the tenant's share of the server's work. `done` is the number of requests completed.

Read the three blocks in order.

1. **fifo punishes everyone equally.** The light tenant sends 1% of the demand and still waits 27 seconds at p99. It waits behind the heavy tenant's backlog.
2. **Round robin protects the light tenant and hurts the busy one.** The light tenant waits 0.45 seconds. The busy tenant waits 50 seconds at p99, worse than under fifo. The heavy tenant takes 90% of the server.
3. **Token fairness splits the server evenly between the two backlogged tenants.** Heavy gets 50% and busy gets 49%. Busy completes 1,983 requests instead of 394.
4. **Under token fairness, busy still waits 11 seconds at p99.** That is correct behaviour. Busy asks for 53% of the server and receives its half, so its own excess queues. The light tenant asks for less than its share and waits 0.17 seconds.

Point 4 is the one to remember. A fair scheduler does not remove waiting. It moves the waiting to the tenants that ask for more than their share. Run `--busy-rate 30` to see the other case. Busy then asks for 40% of the server, less than its half, and its p99 wait falls to 1.37 seconds.

WRONG: "round robin is fair, because every tenant gets the same number of turns."

```
rr     heavy   share 90%   p99 16.80 s
rr     busy    share  9%   p99 49.78 s
heavy's work divided by busy's work: 9.8x under round robin
```

RIGHT: fairness is measured in the resource that runs out. For an LLM server, that resource is token work.

```
vtc    heavy   share 50%   p99 37.68 s
vtc    busy    share 49%   p99 11.22 s
heavy's work divided by busy's work: 1.0x under token fairness
```

### The gap that grows, and the gap that stays bounded

The scheduler controls **admission**. That is the moment a waiting request gets a slot. Once admitted, a long request keeps its slot until it finishes. The scheduler cannot take the work back.

So token fairness cannot promise exactly equal work at every moment. It promises **a bounded gap**. The gap must not grow as one tenant's requests get larger. The self-test checks this:

```
  heavy prompt size      round robin gap     token-fair gap
  8,000 tokens                 9.8x               1.0x
  20,000 tokens               20.4x               1.0x
                              grows               stays bounded
```

Round robin's gap grows with request size, because one turn buys more work. Token fairness's gap does not move.

The simulation charges each prompt to the tenant's counter at admission, as the VTC paper's Algorithm 2 does. Decode work is charged as it runs. An earlier version of this script charged the prompt only while prefill ran. That let the heavy tenant be admitted several times before its counter moved, and the light tenant's p99 wait rose to 1.48 seconds.

The VTC paper proves a bound of this kind. Verified, Theorem 4.4. For any two tenants that both have waiting requests, the difference in service is at most:

```
  2 x max( w_prompt x longest prompt ,  w_output x tokens that fit in one batch )
```

The bound depends on request size and batch size. It does not depend on how much each tenant sends.

The paper also proves a lower bound, Theorem 4.8. Any scheduler that never preempts and never leaves batch space empty can be forced to a gap of `w_output x tokens that fit in one batch`. When that batch term is the larger one, VTC is within a factor of 2 of the best possible.

### The rule that stops an idle tenant from flooding the fleet

A token counter has a flaw if you implement it naively. A tenant that was idle for an hour has a very low counter. When it returns, it has the lowest counter by far. The scheduler would then admit only that tenant until its counter caught up.

That is the noisy-neighbour problem again, created by the fairness mechanism itself.

The VTC fix is simple. When a tenant becomes active again, lift its counter to the lowest counter among the tenants already waiting. The simulation does this at `fair_queue_sim.py:125`:

```python
if lift and not t.queue:
    # The VTC rule: a tenant returning from idle does not keep
    # the low counter it had, or it would flood the server.
    waiting = [x.counter for x in tenants if x.queue]
    if waiting:
        t.counter = max(t.counter, min(waiting))
```

The `lift` flag exists so the self-test can remove the rule and measure the damage. Two tenants are backlogged from the start. A third is idle for 30 seconds, then sends as much as the server can take. Over the last 30 seconds:

```
  with the rule      the returning tenant gets 1.0x a steady tenant's work
  without the rule   the returning tenant gets 4.0x a steady tenant's work
```

```
  counters while heavy and busy are waiting          light returns from idle

  heavy  ██████████████████████  41,000              naive:  light = 900
  busy   ████████████████████    38,000                      light runs alone
  light  ░                          900 (idle)                until 38,000

                                                     VTC:    light = 38,000
                                                             light takes turns
                                                             with busy at once
```

The counter values in that diagram are an example, not a simulation output. The rule itself is the one in the code.

### Fair throughput is not fair latency

Token fairness equalises how much work each tenant gets. It does not promise that a well-behaved tenant sees low latency. A paper posted on 2026-09-16 measured how large that difference can be.

That paper, FairInference, is one day old and not peer reviewed. Its numbers come from one A100 80GB GPU serving Llama-3 8B on SGLang. Treat them as one measurement, not a general result.

The test had three well-behaved tenants and one busy tenant. Each sent 0.5 requests per second with 1,000-token prompts. The well-behaved tenants asked for 50 output tokens. The busy tenant asked for 6,000. Verified from the paper, Table 4:

```
  p99 time to first token for the WELL-BEHAVED tenants

  static partition of the KV cache   ▏ 0.90 s
  FairInference                      ▏ 1.07 s
  DLPM (a VTC follow-up)             ████████████████████████  73.7 s
  VTC                                ██████████████████████████████  92.5 s
  no fairness at all                 ██████████████████████████████████████████████████████████████████████  217 s
```

The paper names two causes:

1. **The scheduler prefers prefill and forms batches in arrival order.** A burst of long requests still reaches the GPU before later short ones.
2. **The KV cache evicts the least recently used blocks first.** The busy tenant fills the cache, so the blocks evicted are the well-behaved tenants' blocks. Their next request must recompute its prefix. Section 3.2 showed what a lost prefix cache costs.

The second cause is the one this simulation does not model. `fair_queue_sim.py` has no KV cache. That is where the simulation stops matching a real server.

### What real engines and gateways give you

Neither vLLM nor SGLang ships a token-fair scheduler. Both ship priority scheduling. The research agent read both engines' source code at release tags vLLM v0.29.0 and SGLang v0.5.19. Neither engine was run.

| | vLLM v0.29.0 | SGLang v0.5.19 |
|---|---|---|
| turn it on | `--scheduling-policy priority` | `--enable-priority-scheduling` |
| request field | `priority`, an integer, default 0 | `priority`, an integer |
| which value goes first | **lower** | **higher**, unless `--schedule-low-priority-values-first` |
| preempts a running request when | a running request needs KV blocks and none are free | also when a high-priority request arrives and the batch is full. Inferred from the code, not run |
| a preempted request | loses its KV blocks and recomputes its prompt later | releases its memory and returns to the waiting queue |
| custom scheduler | `scheduler_cls` | not checked |

The value order is opposite in the two engines. A gateway that sets `priority: 10` for premium traffic makes that traffic go last on vLLM and first on SGLang.

WRONG: sending the same priority number to both engines.

```
vLLM:    priority=10 for premium, priority=0 for free  -> free goes first
SGLang:  priority=10 for premium, priority=0 for free  -> premium goes first
```

RIGHT: map a named priority class to a number per engine, in one place in the gateway, and test the order on each engine.

vLLM also rejects a non-zero `priority` when the server does not run the priority policy. The request fails instead of being served at default priority.

Gateways enforce the quotas. Three gateways count them in tokens:

| gateway | per-tenant token limit | when the tokens are charged |
|---|---|---|
| LiteLLM v1.101.0 | `tpm_limit` on a key, user, or team. `token_rate_limit_type` chooses input, output, or total. The default is total | reserves an estimate before the call by default |
| Envoy AI Gateway v1.1.0 | a rate-limit rule keyed by a tenant header, with a separate bucket per token type | after the response |
| Kong ai-rate-limiting-advanced | `tokens_count_strategy` of total, prompt, completion, or cost | after the response. The docs say the cost is reflected on the next request |

Verified from each gateway's source or documentation by the research agent.

A limit charged after the response has a consequence. A tenant can send many concurrent requests while its counter still shows budget left. It overshoots the quota by one burst. Size the burst allowance with that in mind, or cap concurrent requests per tenant as well.

### The shared prefix cache leaks between tenants

A shared prefix cache is also a shared side channel. A **side channel** is a way to learn secret data from something indirect, such as response time.

A cached prefix makes the first token arrive faster. So a tenant can guess another tenant's prompt, send it, and time the answer. A fast answer means someone else already sent that prefix.

This is measured, not theoretical:

- A Stanford audit in September and October 2024 detected prompt caching at 8 of 17 API providers. At 7 of them, the cache was shared across users. At least 5 providers changed something after the disclosure. Verified from the paper, published at ICML 2025.
- A paper at NDSS 2025 recovered other tenants' prompts from a shared SGLang cache with 99% average success. It used changes in serving order, not only timing. Verified from the paper.

Both vLLM and SGLang accept a per-request `cache_salt` field. Requests share cached blocks only when they carry the same salt. vLLM adds the salt to the hash of the first block, so a different salt means a different hash chain. Verified from vLLM v0.29.0 source.

```
  no salt                          cache_salt = tenant id

  tenant A ─┐                      tenant A ──► [A: system prompt][A: ...]
            ├─► [system prompt]    tenant B ──► [B: system prompt][B: ...]
  tenant B ─┘   shared blocks
                                   the same system prompt is cached twice
  one copy, and a timing channel   no sharing, and no timing channel
```

The salt has three costs and limits:

- **It removes cache sharing between tenants.** A long system prompt that every tenant shares is now cached once per tenant. The prefix-cache hit rate from section 3.2 drops, and so does the saving.
- **SGLang's salt does not cover remote storage.** The source comment says keys in its remote KV storage tier stay token-only. Verified from SGLang v0.5.19 source.
- **No independent test was found.** vLLM's documentation says the salt prevents timing attacks. The research agent found no independent evaluation of that claim.

So the decision is a trade. If tenants must not learn anything about each other's prompts, set the salt to the tenant ID. If the only shared prefix is a public system prompt, a shared cache may be acceptable. Write that decision down, because a reviewer will ask.

### Shared pool or one fleet per tenant

A separate fleet per tenant gives perfect isolation and the worst utilisation. Phase 4B showed that utilisation sets the cost per token.

The published numbers for sharing are for many models, not many tenants of one model. The research agent found no public cost comparison for tenants of one model. Two data points, both verified:

- **Aegaeon, SOSP 2025, Alibaba.** Moving many rarely used models from dedicated GPUs to a shared pool reduced 1,192 GPUs to 213, an 82% saving. Before the change, 94.1% of models received 1.35% of requests.
- **S-LoRA, MLSys 2024.** One A100 80GB served 2,000 LoRA adapters of Llama-7B at 7.61 requests per second, against 8.05 with 5 adapters. A **LoRA adapter** is a small set of extra weights that customises a shared base model. Per-tenant adapters on one base model cost little throughput.

The usual answer is a shared pool with token quotas and a fair or priority scheduler. Reserve a dedicated fleet for a tenant whose latency promise the shared pool cannot keep, and price that fleet at its real utilisation.

**The sentence to remember:** a tenant's share must be counted in the resource that runs out, and for an LLM server that resource is token work, not requests.

**The trap:** a request-per-minute quota and a round-robin scheduler. Both look fair, and both let one tenant with long prompts take most of the fleet. The second trap is believing that fair throughput means fair latency.

**Try this now:** run `python phase06_design/fair_queue_sim.py --heavy-prompt 20000` and compare the work ratio line with the default run. Round robin's gap more than doubles, from 9.8x to 20.4x. Token fairness stays at 1.0x.


---

## 🧪 Hands-on lab — part A

Every exercise in this part runs offline. Nothing costs money.

**Run status:** every command below was executed on the author's machine on 2026-09-17, and the numbers printed in sections 6.1 and 6.2 are real outputs of those runs.

- [ ] **E1 (offline).** Check the mathematics before you trust it.
  - Run: `python phase06_design/capacity_plan.py --self-test`
  - Expected: 13 checks pass, including five that each match one row of a published textbook table.
  - Teaches: a capacity model is software, and it is tested against known answers before it plans anything.

- [ ] **E2 (offline).** Find the knee.
  - Run: `python phase06_design/capacity_plan.py`
  - Expected: mean queue wait of about 5ms at 80% utilisation, 94ms at 90%, 429ms at 95% and 3,688ms at 99%.
  - Write down the utilisation where the wait first exceeds your own latency target.
  - Teaches: waiting time stays flat, then climbs steeply. Planning to the average puts you on the steep part.

- [ ] **E3 (offline).** Measure what pooling is worth.
  - Run: `python phase06_design/capacity_plan.py --slots 8 --peak-rps 5.7`
  - Expected: the same 95% utilisation now waits about 2,445ms instead of 429ms, because each replica has fewer slots sharing the queue.
  - Teaches: the safe utilisation depends on how many servers share one queue. There is no single percentage that is safe for every fleet.

- [ ] **E4 (break-it, offline).** Watch the naive plan fail.
  - Run: `python phase06_design/capacity_plan.py --peak-rps 23.5`
  - Expected: the naive fleet of 3 replicas runs at 97.9%. Its mean queue wait is about 1,542ms, and 77% of requests must wait.
  - Then run it with `--peak-rps 24`. The naive fleet is now at 100% and the table marks it OVERLOADED.
  - Notice that adding one replica drops the wait to 0ms.
  - Teaches: "peak divided by capacity" gives the fleet with no margin, not the fleet you need.

- [ ] **E5 (offline).** Price the minutes a replica takes to start.
  - Run: `python phase06_design/capacity_plan.py --scale-up-s 320 --ramp-rps-per-min 1.5`, then the same with `--scale-up-s 60`.
  - Expected: the 320-second run needs standing headroom and a larger fleet. The 60-second run needs less.
  - Expected: 6 replicas at $15,286 per month for 320 seconds. 5 replicas at $12,739 per month for 60 seconds.
  - The difference is $2,547 per month for one fleet.
  - Teaches: faster cold starts are worth real money, because they reduce the capacity you must keep idle.

- [ ] **E6 (offline).** Verify the fairness simulation.
  - Run: `python phase06_design/fair_queue_sim.py --self-test`
  - Expected: 9 checks pass. Two of them test the idle-tenant rule: a returning tenant gets 1.0x a steady tenant's work with the rule, and 4.0x without it.
  - Teaches: the property being tested is a bound on unfairness. The idle-tenant rule is tested by removing it.

- [ ] **E7 (offline).** Three schedulers, one server.
  - Run: `python phase06_design/fair_queue_sim.py`
  - Expected: under round robin the busy tenant's p99 wait is about 50 seconds, worse than first-come-first-served. Under token fairness, heavy and busy each get about half the work, busy waits about 11 seconds, and light waits 0.17 seconds.
  - Then run `--busy-rate 30`. Busy now asks for less than half the server, and its token-fair p99 falls to about 1.4 seconds.
  - Teaches: equal turns is not equal service when requests differ in size. A fair scheduler moves the waiting to the tenants that ask for more than their share.

- [ ] **E8 (break-it, offline).** Make round robin unfair on purpose.
  - Run: `python phase06_design/fair_queue_sim.py --heavy-prompt 20000`
  - Expected: round robin's heavy-to-busy work ratio grows from 9.8x to 20.4x. Token fairness stays at 1.0x.
  - Then run `--heavy-prompt 2000`. Both policies now print 0.7x. The offered load is 92% of capacity. No tenant stays backlogged, so each tenant receives about what it asks for.
  - Teaches: round robin's unfairness scales with request size. Token fairness does not.

---

## 🔍 Check it yourself

This course has no anchor repository, so these questions point at the course's own code. Question 4 works on any repository you own.

1. Open `code/phase06_design/capacity_plan.py:60`. This is `erlang_c`. Read its docstring.
   Why does it use the Erlang B recursion instead of the textbook formula? Which self-test check would fail with the textbook formula?

2. Open `code/phase06_design/capacity_plan.py:57`. The script imports `self_host_cost_per_mtok` from Phase 4B.
   Change `--gpu-hourly` to twice its default and rerun. Which numbers change, and which stay the same? Explain why the replica count does not move.

3. Open `code/phase06_design/fair_queue_sim.py:99`. This is `simulate`. The idle-tenant rule is inside it, at line 125.
   Find the `lift` parameter of `simulate`. The self-test runs one scenario with `lift=False`. Which check uses it, and what ratio does it print? Describe, in words, the traffic pattern that makes this rule necessary.

4. In any LLM gateway or proxy config you own, search for rate limits.
   Run: `grep -rn -i "rpm\|tpm\|rate_limit\|ratelimit" <your repo>/`
   Is each limit per tenant or global? Is it in requests or in tokens? Is any request field named `priority` or `cache_salt` set?

---

## ✅ Checkpoint 6A — answer in your own words

1. **The spreadsheet plan.** A teammate measured 8 requests per second per replica, and forecasts a peak of 22.8 requests per second. They propose 3 replicas. Use the knee table from section 6.1 to explain what happens at that peak. Then give your replica count and one reason for each replica above 3.

2. **Two fleets, same utilisation.** Fleet A has 3 replicas with 32 slots each. Fleet B has 12 replicas with 8 slots each. Both run at 90% utilisation with the same mean request time. Which one waits longer in the queue, and why? Name the effect.

3. **The autoscaler that never scaled.** Your autoscaler targets 80% GPU utilisation. During a traffic spike, TTFT rises from 400ms to 9 seconds, and the autoscaler adds no replicas. Explain what happened. Say which metric you would scale on instead, and give a starting threshold with its source.

4. **The cold-start bill.** A new replica takes about 320 seconds to serve its first request. Demand can rise 1.5 requests per second each minute. How much demand arrives before the new replica is ready? What does that force you to keep running? Name two changes from section 6.1 that would shorten the 320 seconds.

5. **The enterprise tenant.** One tenant sends 8,000-token prompts at 8 requests per second. Your gateway limits each tenant to 600 requests per minute, and the scheduler uses round robin. Other tenants complain about slow responses. Explain why both mechanisms failed. Say what you would change in each, and what that tenant would see after the change.

6. **Fair, and still slow.** You deployed a token-fair scheduler. The work shares are now close to equal, but a small tenant's p99 TTFT is still 60 seconds when a busy tenant sends 6,000-token outputs. Give the two causes that FairInference names. Say which one `fair_queue_sim.py` does not model.

7. **The shared system prompt.** Ten tenants share a 3,000-token system prompt. Security asks you to set `cache_salt` to the tenant ID. What do you gain, and what does it cost? Give one case where you would accept the cost and one where you might not.

<details>
<summary>Answer sketches</summary>

1. Three replicas give 96 slots. At 22.8 rps and 4 seconds per request, that is 95% utilisation. The knee table shows a mean queue wait of about 429ms, and it climbs to seconds with a little more load. The plan: 4 replicas meet the 250ms target today, 4 still fit 25% growth, N+1 makes 5, and standing headroom for a slow cold start makes 6. Each replica has a stated reason.

2. Fleet B waits longer. Each replica has its own queue. A request cannot use a free slot on another replica. More slots behind one queue means more pooling, and pooled servers wait less at the same utilisation. E3 showed it: 8 slots at 95% waited 2,445ms, against 429ms with 32 slots.

3. A batching engine keeps GPU utilisation near 100% across a wide range of load. So utilisation never showed the queue growing. The AWS, GKE and llm-d guides all say this. Scale on `vllm:num_requests_waiting`. Starting points: 3 to 5 from the GKE guide, or 5 from the vLLM production-stack example. Also add p95 latency or TTFT as a second trigger.

4. 320 seconds is 5.33 minutes. At 1.5 rps per minute, that is 8 rps of new demand before the replica helps. You must keep enough standing headroom to absorb 8 rps, which is one more replica in the default plan. Two ways to shorten it. First, use a smaller or pre-pulled image, because image pull was 44% of one measured cold start. Second, use a streaming weight loader, which cut one measured load from 48 seconds to about 5.

5. 8 rps is 480 requests per minute, under the 600 limit. The quota counts requests, so it never triggers. Round robin gives that tenant one turn per round, and each turn costs about 11 times a small tenant's work. Change the quota to tokens per minute, and change the scheduler to token-fair admission. The heavy tenant now absorbs its own backlog. In the simulation its p99 wait rose from 16.8 to 37.7 seconds, while the light tenant's stayed at 0.17 seconds. A tenant that asks for more than its share still waits. A tenant under its share does not.

6. First, the scheduler prefers prefill and forms batches in arrival order. Second, the KV cache evicts the least recently used blocks, which are the small tenant's blocks, so its prefixes are recomputed. The simulation has no KV cache, so it does not model the second cause. Token fairness equalises work. It does not isolate latency.

7. You gain isolation. No tenant can learn from response timing whether another tenant sent a given prefix. The cost: the 3,000-token prompt is cached ten times, not once. Each tenant's first request pays the full prefill, and cache memory holds ten copies. Accept it when prompts carry customer data, or when a leak would break a contract. You might skip it when the only shared prefix is a public system prompt and the rest of each request is never cached across tenants. Record the decision either way.

</details>

---

## References & Further Learning

Every URL below returned HTTP 200 when checked on 2026-09-17.

### Capacity planning

- **Google SRE book, "Service Best Practices"** — https://sre.google/sre-book/service-best-practices/
  Focus on: the N+2 rule, and the advice to use load tests instead of tradition.
- **Google SRE book, "Software Engineering in SRE"** — https://sre.google/sre-book/software-engineering-in-sre/
  Focus on: the worked example with 3,470 QPS, 35 tasks and 37 deployed, and the region that accepts N+1.
- **Google SRE book, "Handling Overload"** — https://sre.google/sre-book/handling-overload/
  Focus on: why queries per second is a poor capacity metric when queries differ in cost.
- **Google SRE workbook, "Managing Load"** — https://sre.google/workbook/managing-load/
  Focus on: the case studies on autoscaling and on load that arrives faster than capacity.
- **Ivo Adan and Jacques Resing, "Queueing Systems"**, lecture notes — https://www.win.tue.nl/~iadan/queueing.pdf
  Focus on: the M/M/c chapter for Erlang C, and the M/G/1 chapter for why service-time variance matters.
- **John Little, "Little's Law as Viewed on Its 50th Anniversary"** — https://people.cs.umass.edu/~emery/classes/cmpsci691st/readings/OS/Littles-Law-50-Years-Later.pdf
  Focus on: the first section. It states L = λW and why it needs almost no assumptions.
- **Dan Slimmon, "The most important thing to understand about queues"** — https://blog.danslimmon.com/2016/08/26/the-most-important-thing-to-understand-about-queues/
  Focus on: the wait-time curve. It is a short explanation of the knee that E2 shows.
- **DistServe, OSDI 2024** — https://arxiv.org/abs/2401.09670
  Focus on: the definition of goodput, and the worked example that sizes prefill and decode separately.
- **DynamoLLM** — https://arxiv.org/html/2408.00741
  Focus on: the characterisation of the Azure trace. It is the source of the peak-to-average ratios.
- **ServeGen, NSDI 2026** — https://arxiv.org/html/2505.09999
  Focus on: arrival burstiness by model type, and client concentration.
- **Azure LLM inference dataset 2024** — https://github.com/Azure/AzurePublicDataset/blob/master/AzureLLMInferenceDataset2024.md
  Focus on: the field list. This is a real trace you can replay with Phase 4A's benchmark client.
- **Microsoft, "Dissecting LLM container cold start"** — https://techcommunity.microsoft.com/blog/linuxandopensourceblog/dissecting-llm-container-cold-start-where-the-time-actually-goes/4508831
  Focus on: the phase-by-phase breakdown, and how the dominant phase depends on the engine.
- **NVIDIA, "Reducing cold start latency with Run:ai Model Streamer"** — https://developer.nvidia.com/blog/reducing-cold-start-latency-for-llm-inference-with-nvidia-runai-model-streamer
  Focus on: the load-time table and its storage conditions.
- **AWS EKS, inference autoscaling thresholds** — https://docs.aws.amazon.com/eks/latest/userguide/ml-inference-autoscaling-thresholds.html
  Focus on: the measured queue jump, and the suggested scale-out and scale-in settings.
- **GKE, autoscaling best practices for inference** — https://cloud.google.com/kubernetes-engine/docs/best-practices/machine-learning/inference/autoscaling
  Focus on: the ranking of metrics, and the starting queue target.
- **vLLM production-stack, autoscaling with KEDA** — https://docs.vllm.ai/projects/production-stack/en/latest/use_cases/autoscaling-keda.html
  Focus on: the scaled object. Note the threshold, polling interval and cooldown.
- **KEDA, ScaledObject specification** — https://keda.sh/docs/2.17/reference/scaledobject-spec/
  Focus on: `pollingInterval` and `cooldownPeriod`, and the note that scaling from 1 to N is left to the horizontal pod autoscaler.
- **vLLM, `vllm bench serve`** — https://docs.vllm.ai/en/latest/cli/bench/serve/
  Focus on: the goodput options. Use them to measure the per-replica number that `capacity_plan.py` needs.

### Multi-tenant fairness

- **Sheng and others, "Fairness in Serving Large Language Models", OSDI 2024** — https://www.usenix.org/conference/osdi24/presentation/sheng
  Also on arXiv: https://arxiv.org/abs/2401.00588
  Focus on: section 3.1 for the cost function, Algorithm 2 for the scheduler, Theorems 4.4 and 4.8 for the bounds, and Table 2. Read this paper first.
- **FairInference** — https://arxiv.org/abs/2609.18112
  Focus on: section 2.2 and Table 4. Posted 2026-09-16 and not peer reviewed. Read it for the two causes of latency interference.
- **FairServe, Microsoft** — https://arxiv.org/abs/2411.15997
  Focus on: the Copilot trace study, and per-application throttling.
- **Locality-aware Fair Scheduling, DLPM** — https://arxiv.org/abs/2501.14312
  Focus on: how fair scheduling interacts with prefix-cache locality.
- **Demers, Keshav and Shenker, "Analysis and Simulation of a Fair Queueing Algorithm", SIGCOMM 1989** — http://ccr.sigcomm.org/archive/1995/jan95/ccr-9501-shenker.pdf
  Focus on: sections 2.1 and 2.2. Round robin by packet is unfair when packets differ in size. That is the same problem as round robin by request.
- **RFC 2697, A Single Rate Three Color Marker** — https://www.rfc-editor.org/rfc/rfc2697
  Focus on: the token bucket definition. Note that it counts bytes, not packets.
- **vLLM scheduler source, v0.29.0** — https://github.com/vllm-project/vllm/blob/v0.29.0/vllm/v1/core/sched/scheduler.py
  Focus on: `_preempt_request`, and how the victim is chosen under the priority policy.
- **SGLang server arguments** — https://docs.sglang.ai/advanced_features/server_arguments.html
  Focus on: the priority scheduling flags. Note which value goes first.
- **LiteLLM, users, keys and teams** — https://docs.litellm.ai/docs/proxy/users
  Focus on: `tpm_limit`, `rpm_limit` and `max_parallel_requests` per key and team.
- **Envoy AI Gateway, usage-based rate limiting** — https://theagentrouter.ai/docs/capabilities/traffic/usage-based-ratelimiting/
  Focus on: per-tenant token buckets. The project is now named Agent Router, and the old URL redirects here.
- **Kong, AI Rate Limiting Advanced** — https://developer.konghq.com/plugins/ai-rate-limiting-advanced/
  Focus on: `tokens_count_strategy`, and the note that the cost is reflected on the next request.

### Cache isolation and pooling

- **Gu and others, "Auditing Prompt Caching in Language Model APIs", ICML 2025** — https://arxiv.org/abs/2502.07776
  Focus on: the audit method, and the table of providers with shared caches.
- **"I Know What You Asked", NDSS 2025** — https://www.ndss-symposium.org/ndss-paper/i-know-what-you-asked-prompt-leakage-via-kv-cache-sharing-in-multi-tenant-llm-serving/
  Focus on: how serving order leaks a prompt under longest-prefix-match scheduling.
- **vLLM prefix caching design, v0.29.0** — https://docs.vllm.ai/en/v0.29.0/design/prefix_caching/
  Focus on: the `cache_salt` section and the hash algorithm warning.
- **Aegaeon, SOSP 2025** — https://ennanzhai.github.io/pub/sosp25-aegaeon.pdf
  Focus on: the production deployment numbers. The pool serves many models, not many tenants of one model.
- **S-LoRA, MLSys 2024** — https://arxiv.org/abs/2311.03285
  Focus on: Table 3, throughput as the adapter count grows.

---

## Cheatsheet — part A

```
QUEUEING, THE THREE LINES
  Little's law          L = λ W        holds for almost any queue
  one server            wait ∝ ρ / (1 − ρ)   flat, then steep
  c servers, Erlang C   P(wait) and mean wait; compute it with the
                        Erlang B recursion, never with a^c / c!

THE PLAN
  1. measure per-replica capacity as GOODPUT, at your latency target
  2. find replicas that meet the queue-wait target at forecast peak
  3. add growth until the next capacity purchase lands
  4. add N+1, or N+2 for planned plus unplanned outage
  5. add standing headroom = demand rise during one cold start
  6. price it with 4.6's formula at the resulting utilisation
  7. call it a FLOOR: real traffic is burstier than Poisson

KNEE (default run: 32 slots per replica, 3 replicas)
  80% -> 5 ms   90% -> 94 ms   95% -> 429 ms   99% -> 3,688 ms
  fewer slots per replica, same utilisation -> much longer wait

COLD START (measured examples, conditions vary)
  whole cold start   ~317 s   8B, one A100, pull 44% / startup 56%
  weight load         48 s -> ~5 s with a streaming loader

AUTOSCALE
  on vllm:num_requests_waiting, NOT GPU utilisation
  start: queue 3-5 (GKE) or 5 (vLLM production-stack)
  AWS: out at queue > 25 for 30-60 s or p95 > 5 s
       in  at queue 0 and p95 < 3 s for 5 minutes

TENANTS
  quota at the gateway, in TOKENS per minute, per tenant
  fairness in the scheduler, by TOKENS of service (VTC)
  idle tenant returns -> lift its counter to min of waiting
  round-robin gap grows with request size; token-fair gap stays bounded
  fair throughput is not fair latency (prefill order, KV eviction)

ENGINES (source read at tags, not run)
  vLLM   --scheduling-policy priority      LOWER value first
  SGLang --enable-priority-scheduling      HIGHER value first
  neither ships a token-fair scheduler

CACHE ISOLATION
  shared prefix cache = timing side channel between tenants
  cache_salt = tenant id  -> no cross-tenant hits, no shared savings
  SGLang: salt does not cover remote KV storage
```

---

Part B covers the two moments when this work is tested by other people: a quality incident and a design review.

In the serving phase you sized your router's replicas from throughput and CPU utilization, and the stack scaled when your metrics said it was scaling. Netflix ran that same design on about 30,000 production streaming jobs for years, and it worked, until jobs started sitting in a degraded state that none of those metrics reported as a problem. The autoscaler saw a quiet machine and did nothing, while the job's output kept falling behind.

The failure is that a stage of your pipeline can be completely unable to accept more work while looking idle on the machine's metrics, because waiting for something slow does not burn CPU and does not show up as requests per second. This lesson asks what Netflix watched instead, and what that means for the signal your model server scales and alerts on.

This lesson teaches one idea. It is stated here so you can see where the lesson is going. It will read more clearly once it has been explained below, so come back to it at the end.

- CPU and throughput metrics cannot see load that arrives as waiting, so the trustworthy capacity signal is each stage's busy fraction, not its utilization. Decide which metric drives autoscaling and alerts in his serving stack, and predict when utilization alerting stays silent during real degradation.

## How did a busy job look idle to Netflix's first autoscaler?

An autoscaler that reads CPU and throughput will sit still while a backpressured stage degrades.

In 2019 Netflix built its first Flink autoscaler, because no open option existed then. It watched a job from outside, through CPU use, network traffic and Kafka lag. It had one control, the total worker count. This is the same design as your serving stack: scale the replicas when utilization or requests per second cross a line. For simple pipelines it worked for years, and Netflix reported 25 to 45% resource savings across thousands of jobs.

  Normal loadSlow downstream

      One second at the worker, normal case

      One second at the worker, downstream sink is slow

The failure case is a slow downstream sink. The worker's output buffer fills, so the worker stops and waits for the sink to drain. Waiting on a full buffer burns no CPU and produces no records out. Upstream, Kafka lag grows.

Predict: a job is fully backpressured on a slow sink, CPU reads 15%, and lag grows. Which metric fires the alert first, CPU or the fraction of each second the worker spends doing real work?
The busy-fraction metric fires, and CPU may cross its threshold never. Backpressured time counts as busy time, because the worker cannot accept one more record in that second. So the busy fraction reads 100% while CPU sits at 15%. An alert on 80% CPU stays silent, and an alert on 90% busy fires at once. The wrong belief was reasonable: in your Go services, waiting and idle usually coincide, because a goroutine waiting on a lock still has capacity. A pipeline stage waiting on a full buffer has none.

The quantity that sees this is the busy fraction, the share of each second the stage spends working or unable to accept work, measured inside the stage. Flink reports it per subtask as busyTimeMsPerSecond. Backpressured and working time count, and only empty-input idle time does not. CPU sees only the real computation above. Busy fraction measures the whole 1,000 ms.

Netflix described the result of watching the wrong quantity: a job could be completely busy while its CPU stayed low, so the scaler read it as idle and left it in its degraded state. Then a second failure compounded the first. A networking migration degraded the Atlas metrics the scaler trusted, and the scaler kept scaling on stale numbers. The gap surfaced in production much later. Netflix did not link an incident report, so the customer impact is unconfirmed.

Evidence
Netflix Technology Blog, "A Tale of Two Flink Autoscalers", published Aug 21, 2026, read through a verbatim mirror because Medium blocks plain fetches. The Atlas migration incident and the 2019 scaler design come from that post and are single-origin. InfoQ's Sep 7, 2026 coverage traces to the same post.

The structual point is that both metrics he trusts are proxies. CPU measures compute, throughput measures output, and neither measures backlog when the job's load arrives as waiting. A big stateful job's traffic is exactly the kind that arrives as waiting.

  CPU and throughput cannot see load that arrives as waiting; busy fraction can.

  Trusting 15% CPU as idle: the stage may be 100% backpressured and degrading.

  Check one service you run: does its alert fire when a downstream stall fills its queue?

This section showed the gap between outside metrics and inside load. The next section shows the signal the community autoscaler reads from inside each operator, and the restart cost that shapes how far it pushes utilization.

## What does the replacement measure, and who wrote it down first?

Busy fraction tells you a stage is full; the working question is how much spare capacity it has.

The section above showed outside metrics missed the load. The community autoscaler reads its signal from inside each operator. It can size the job even when CPU looks flat.

Flink reports one number per operator every second: busy fraction, the share of that second the operator spent doing real work, as milliseconds of busy time per second. The autoscaler divides the observed throughput by that fraction to get True Processing Rate, the records per second the operator would do at 100% busy. An operator at 700 records per second while busy 0.7 has a rate of 1,000. That rate is the operator's real ceiling, measured without a single CPU reading, because waiting is already inside the busy time.

Predict: the operator at 700 records/sec now reports 200 records/sec while 95% busy. Scale it up, or leave it?
Scale it up. The obvious reading is that throughput fell, so the operator has spare capacity. But 200 / 0.95 gives a rate of about 210, far below the measured 1,000. The operator did not get faster; it got starved, most likely by an upstream stage or a throttled input. Throughput and busy fraction together point the finger. Low throughput and high busy means the capacity is gone, so a CPU alert would see nothing but idle silicon.

  True Processing Rate from one reading

  Observed records/sec

  Busy fraction
    %
  Capacity at 100% busy

The mechanism is built on two further choices, each costing something. The first is per-vertex sizing. The autoscaler walks the job graph from the sources downstream and computes the parallelism each operator needs. A stateful multi-stage job sizes each stage instead of moving one cluster-wide worker count. The second is target utilization, the busy fraction the autoscaler aims for when it sizes a vertex. Every rescale is a savepoint, a graceful stop and a restart. For a large stateful job, this takes minutes. After the restart the metric window must rebuild before the autoscaler can react again. Netflix therefore runs a target of 0.45 against the community default of 0.7 (`job.autoscaler.utilization.target`, v1.17-SNAPSHOT docs). It pays for idle capacity to buy fewer restarts.

None of this is new. The maintainers' design doc FLIP-271 lists CPU-based scaling and job-wide parallelism tuning as explicitly rejected alternatives. The two lessons Netflix relearned in production were already written down. The research root is the DS2 paper at OSDI 18. It measured scaling that converges in one step. That was against six steps for a policy built on proxy metrics like throughput and CPU.

Evidence
The rate formula and the 0.7 default come from the Flink Kubernetes Operator autoscaler docs and FLIP-271, both read 2026-10-09. The 0.45 target and the restart-cost reasoning are Netflix-reported, single-origin, via the article mirror. One-step convergence is from the DS2 abstract on the USENIX OSDI 18 page; the paper body was not read.

  Capacity is observed throughput divided by busy fraction, sized per stage.

  Low throughput does not mean spare capacity; check busy fraction before desizing.

  Move the busy slider to 95 and watch throughput stay low while capacity vanishes.

This section showed what the replacement measures and what a rescale costs. The next section answers where this lands in your model server. It covers which serving metrics carry the CPU blind spot, and what to watch instead.

## Where does this land in your model server?

You now know what the replacement signal measures and what a restart costs. The question left is where the same blind spot sits in your own serving stack.

Your serving stack from the phase on routing and batching is a router in front of replicas. Each replica runs prefill and decode, the two stages of serving a request. Prefill reads the whole prompt in one pass, and decode then produces the reply one token at a time. Each replica also keeps a KV cache, the attention keys and values the GPU holds per request it serves. The cache is finite, so a full cache parks new requests at the router. Those replicas scale with a Kubernetes Horizontal Pod Autoscaler (HPA), which adds and removes replicas based on one watched metric. The metric most clusters reach for first is CPU.

The comfortable belief is that 20% CPU means idle, so nothing needs to change.

  router

  waiting: 4

-

-

  replica A

  prefill

  decode

  KV cache full
  CPU 20%
  GPU busy on held streams

  replica B

  prefill

  decode

  KV cache full
  CPU 20%
  GPU busy on held streams

The failure before it has a name: requests wait at the router, both caches are full, and CPU reads 20%. Illustration, not measured.

Predict: The KV cache of every replica is full, the router queue is growing, CPU reads 20%. An HPA scaling on CPU: does it add replicas?
No, and that is the failure. The HPA compares CPU against its threshold, and 20% sits far below it, so the replica count stays put. Meanwhile every parked request adds its wait to your p99, and the queue keeps growing behind a metric that stays calm. An alert on time-in-queue or cache occupancy would fire immediately, because both measure the waiting itself.

Why does CPU stay low through all of this? A request parked in the router's queue is memory holding data, not running code, so it moves no CPU. The replicas keep decoding the streams they already hold, and that math runs on the GPU, so host CPU barely changes. A router blocked on a slow tool call is waiting on a network read, which costs no cycles either. Every stage is busy in queue terms and idle in CPU terms at the same time.

So the fix is not a lower CPU threshold. The fix is watching the waiting itself, one signal per stage. The busy fraction, the share of each second a stage spends on real work, has one analogue per stage here.

Watch this insteadWhere it livesWhat it sees that CPU misses

Time-in-queue per requestrouter log, between stagesthe waiting itself, while it is still cheap

KV cache occupancyeach replica's GPU memorya full cache predicts queueing before CPU moves

Tokens/sec per forward pass (one model run over a batch)decode workerfalls when the worker waits on memory or upstream, with CPU flat

Evidence
The three signal rows are the study note's mapping onto serving stacks, an inference from the incident rather than a quote from Netflix. The 20% CPU reading in the figure is an illustration, not measured.

This is the same trap, now inside your own stack. You get no error. Only latency changes, and no metric you watch today shows why.

You have a place to try this without a GPU. In the lab, put ten minutes of load on one queue between two agents in your evening system. Log time-in-queue and CPU side by side, and watch for queue wait rising while CPU stays low. That gap is the Netflix incident on one machine.

  Alert on queue wait and KV cache occupancy, because CPU stays idle while queues fill.

  Treating 20% CPU as idle leaves the backlog unscaled and p99 climbing.

  In the lab, log time-in-queue beside CPU on one agent queue and watch them diverge.

You can now read the phase's utilization and batching sections knowing each stage's busy fraction is the honest signal. The lab asks you to find one CPU-blind spot in your own stack.

## Lab: find one CPU-blind spot in your own stack

You now know which signal cannot sleep through backpressure. It is the busy fraction, the share of each second a stage spends doing real work. Now find one place in your own stack where CPU would sleep. Fifteen minutes, no code yet.

-  E1 offline
Pick one service you run with a queue in front of it. The queue between agents in your multi-agent system works. Write down the metric that drives its scaling or alerting today. If the answer is CPU or requests per second, mark it as the suspect.

-  E2 offline
Reason through the backpressured case, on paper. The stage after yours stalls, so your service's results wait in the outgoing queue. Your service is blocked on that queue for most of each second, because it cannot push work out. Answer in one line per question:

- Queue depth: grows, shrinks, or stays flat?

- CPU on your service: high or low? Why?

- The metric from E1: does it fire? If not, what would a user notice first?

-  E3 offline
Add one probe that sees waiting. The cheapest form is a log line. Once a second, log how many of those 1,000 milliseconds your worker spent processing versus blocked on the queue:

// inside the worker loop, around the dequeue or send
start := time.Now()
job := queue.Receive()          // blocks here
waitBlockedMs = 0               // time in Receive was idle, not busy
process(job)
busyMs := time.Since(start).Milliseconds() - waitBlockedMs
log.Printf("busy_ms=%d of last 1000", busyMs)

What to look for: busy_ms near zero while the queue grows means the wait is elsewhere, downstream. busy_ms near 1,000 while the queue grows means this stage is the real bottleneck.

Queue depth tells you someone is saturated. Busy milliseconds tell you who. You want both, because they answer different questions.

Write the result of E2 next to the metric from E1. If the mismatch is real, your stack has the Netflix incident in miniature. Then the probe from E3 is the fix. The checkpoint next tests the same judgment on your serving stack, with numbers attached.

## Checkpoint

One scenario to test the whole lesson against your serving stack. Answer both parts before opening the sketch.

Your router queues incoming requests. Every decode replica holds a full KV cache. This cache is the attention keys and values each replica keeps in GPU memory for the requests it is serving.

- CPU on every replica reads 25%. Requests per second is flat.

- Your alert fires on CPU above 80%. It never fires.

- p99 latency triples over twenty minutes.

Question 1: which two metrics from this lesson would show the saturation first?

Question 2: a replica restart means reloading model weights, which takes minutes. What busy-fraction target below 100% would you set, and why?

Answer sketch
Question 1. KV cache occupancy and time-in-queue. A full KV cache means the replica cannot accept another request. It is saturated in queue terms while CPU stays at 25%, because waiting on memory uses no compute. This is the Netflix incident exactly: the work shows up as waiting, and CPU cannot see waiting. Each replica's busy fraction, the share of each second it spends doing real work, would read near 100%. Queue depth at the router would climb. Either one fires long before CPU moves.

Question 2. Pick a target well under 1.0, for the same reason. Netflix runs 0.45 against the community default of 0.7 for target utilization, the busy fraction the autoscaler aims for. A replica at a 0.45 target carries over five times the headroom of one at 0.9. So a traffic step is absorbed by the replicas you have instead of triggering a scale-up. That matters because a stateful rescale is a restart: savepoint, stop, reload weights, minutes before the metric window rebuilds. You are paying for idle capacity to buy calm. For a model server the restart is even heavier than Netflix's. Any answer in the 0.4 to 0.7 range with that reasoning is right; 0.95 is wrong.

If both answers were obvious, the lesson has landed. CPU and throughput are proxies. The honest signal is how much of each second each stage spends working versus waiting. The next section is two post shapes you could publish from this.

## What you could post

Two shapes you could publish from this lesson.

1. The metric that cannot see waiting. Netflix's autoscaler watched CPU and missed a busy job for years. The worked example carries the post: 700 records per second at 70% busy means a true rate of 1,000. CPU never enters the formula. It is yours because you mapped it onto your own stack. A decode replica stalled on a full KV cache can look idle on CPU.

2. Per-stage sizing is per-vertex sizing. Netflix sizes each operator of a job. One replica count for a whole pipeline has the defect their first scaler had. It is yours because you already run the pipeline it applies to: router, prefill, decode, tools.

One caution before either goes out: the article wording came through a mirror, because Medium blocks plain fetches. Re-check every verbatim quote against netflixtechblog.com before publishing it under your name.

## Sources

- Netflix Technology Blog, "A Tale of Two Flink Autoscalers", Aug 21, 2026. The incident, the busy-time autoscaler and the 58% saving. Read through a verbatim mirror because Medium blocks plain fetches, so exact wording is unverified.

- The full-text mirror and a second rendering used to cross-check it.

- Flink Kubernetes Operator autoscaler docs, v1.17-SNAPSHOT. Confirmed the True Processing Rate definition, the 0.7 utilization default, restart-cost math and the throttled-sink blind spot.

- FLIP-271, the maintainers' design doc. The exact formula and the record that CPU-based and job-wide scaling were rejected alternatives.

- DS2, Kalavri et al., OSDI 18. The research root of the mechanism; the abstract and headline claim were confirmed, the full paper was not read.

- InfoQ coverage, Sep 7, 2026. Independent reporting of the post and the DS2 lineage. Note that its numbers trace to the same Netflix post.

- FLINK-36172. An upstream metrics fix Netflix names; its match to the per-subtask fetch problem is inferred, not verified.

Every Netflix-internal figure in this lesson (the 25–45% savings, 58% and ~$1.1M per year, the 1,000-to-3,000 subtask lift, the 30,000-job fleet) is single-origin: only Netflix reports it. All sources were read on 2026-10-09.
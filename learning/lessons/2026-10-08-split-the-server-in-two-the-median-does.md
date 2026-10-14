Your serving phase taught you why prefill and decode are different jobs, and you can now say why a server treats a new prompt differently from a streaming reply. What it could not show you is what happens to latency when one GPU runs both kinds of work at once. On the two-L40S box from the vLLM team's September 2026 guide, serving Qwen2.5-7B-Instruct with 8k-token prompts, load climbs and the median time between tokens barely moves, while the slow tail stretches past 260 ms. The same load with one GPU given to prefill and one to decode keeps that tail near 25 to 52 ms.

The question this phase answers is why the two arrangements look identical at the median and very different at the tail, and what the split pays for that calm tail, because the split moves a large block of memory between the GPUs for every request. When you next see a p99 rise while the median stays clean on any box that runs two jobs, you will know whether to look at scheduling or at a physical split before you touch a config.

This lesson teaches one idea. It is stated here so you can see where the lesson is going. It will read more clearly once it has been explained below, so come back to it at the end.

- When two workloads with different bottlenecks share one processor, their interference lands on the tail of latency, not the median, so splitting them moves the state, not the mean. Read a latency distribution on any shared-resource system and predict whether scheduling or a physical split is at fault before touching a config.

## What are the two workloads the phase split apart?

Two different workloads run inside one serving process, and each sets a different latency.

Your box has two NVIDIA L40S GPUs serving Qwen2.5-7B-Instruct with 8k-token prompts, and the vLLM team's guide measures two ways to arrange the work. Before we touch those numbers, we need the two kinds of work every serving run does, because the tail behaviour only makes sense once you see how different they are.

The first is prefill, the single pass that reads your whole prompt at once and produces the first token. Every prompt token is processed in parallel, so prefill is limited by raw compute. The second is decode, the loop that generates the reply one token at a time. Each decode step re-reads the full model weights, so decode is limited by memory bandwidth, not compute. Prefill also builds the KV cache, the attention keys and values the GPU keeps for each request, and decode reads and extends it at every step.

Each workload sets its own latency, so one serving process has two clocks. TTFT, the time to the first token, is set by prefill. ITL, the time between two tokens, is set by decode. These two clocks are why a latency SLO on an LLM server can never be a single number.

One request, two different workloads

Illustration of the two phases; the decode steps repeat hundreds of times, not three.

Predict: which latency moves when a second 8k-token prompt arrives while a reply is streaming?ITL, not its own TTFT alone. The new prefill holds the whole GPU for one long pass, so the streaming decode misses steps and its gap between tokens stretches. The picture collapses here because both workloads wanted one processor.

The guide's arrangement under test follows from this. Run prefill and decode on separate GPUs and move the KV cache between them, a design called prefill-decode disaggregation. The next sections measure whether the split works and what it charges.

- Prefill reads 8,000 tokens in one parallel pass, so its time is set by compute and it holds the GPU for one long stretch.

- Decode emits one 21 to 24 ms token at a time, and any pause in its schedule shows up directly as a gap in the stream.

Prefill is one long compute pass; decode is a bandwidth-bound loop.

Treating serving latency as one number hides which workload is hurting.

Send a long prompt with vllm bench serve; its prefill can stall decode, so ITL suffers.

This named the two workloads and their latencies, but not what those latencies do when both share one GPU under load. The next section shows where the waiting lands.

## Where does the waiting land when two jobs share one GPU?

Same box, same model, same median, and a p99 sixfold apart.

Section one named the two workloads and their latencies. But it left open what they do when both workloads share one GPU as load climbs. On the running case, the vLLM team served the same model two ways on one box to find out:

- Collocated: both GPUs run prefill and decode together, one vllm serve --data-parallel-size 2 process.

- Disaggregated: GPU 0 runs only prefill and GPU 1 runs only decode, a design named prefill-decode disaggregation. Each request's KV cache then crosses to the decode GPU over NIXL, the transfer library vLLM uses to move KV caches between GPUs.

Collocated

GPU 0
prefill + decode

GPU 1
prefill + decode
Disaggregated

GPU 0
prefill only

GPU 1
decode only

-
KV cache over PCIe, carried by NIXL

The same two L40S GPUs, run two ways. In the split, each request's KV cache crosses from the prefill GPU to the decode GPU.

Predict: at 0.4 requests per second, which statistic moves first, the median ITL, the p99 ITL, or both together?Only the p99. The median ITL stays at 21 to 24 ms in both arrangements, and the collocated p99 reaches 169 ms at this rate. Why sharing one GPU produces exactly that shape is the next section's subject.

Median ITL matched almost exactly, 21 to 24 ms in both arrangements up to 1 request per second. So the split bought nothing for a typical token. The p99 ITL separated instead:

Request rateCollocated p99 ITLDisaggregated p99 ITL

lowest rate tested23 ms25–52 ms

0.4 req/s169 ms25–52 ms

2 req/s263 ms25–52 ms

At 0.4 requests per second the medians are indistinguishable while the p99s sit sixfold apart. A dashboard watching the median would call the collocated box healthy while one token in a hundred takes 169 ms.

What the split actually bought is goodput. That is the request rate the box sustains while both its TTFT target and its ITL target hold. What moved was the load at which the ITL target breaks, a number no benchmark without latency targets can see.

Evidence
A single benchmark from the vLLM guide of 2026-09-29 (Martin Hickey, IBM Research). Fixed conditions: Qwen2.5-7B-Instruct, two L40S 48 GB on PCIe with no NVLink, 8k-token prompts. The rest were 256 output tokens, 100 Poisson-arrival requests per rate, prefix caching off. DistServe (OSDI 2024) and AMD's ROCm post on SGLang confirm the same medians-clean, tails-apart pattern on other hardware. The authors flag one untested variant: two independent replicas behind a load balancer might close part of the gap. Their summary: "The pitch isn't peak throughput... What it buys is goodput."

The split changed nothing at the median and cut p99 ITL about sixfold.

Expecting every request to slow a little, you watch the mean while the tail breaks.

Run vllm bench serve at two rates and check whether p99 ITL leaves p50 behind.

These numbers show where the waiting lands, not why it lands there. The next section answers why the tail moves when the median does not.

## Why does the tail move when the median does not?

Sharing a GPU concentrates all waiting into a few unlucky requests.

Section two showed the collocated p99 separating from the median at 0.4 req/s. It did not show why sharing one GPU produces exactly that shape. The mechanism is a queue with two kinds of work in it.

A prefill pass on an 8k prompt holds the GPU for hundreds of milliseconds as one indivisible unit of compute. Decode steps are short and frequent, about 20 ms each, and every streaming request needs one per token. When a prefill arrives while decodes are streaming, each of those decodes waits for the whole pass to finish. The GPU runs one batch at a time. That waiting, prefill-decode interference, a decode's pause while a prefill pass holds its GPU, is long and rare.

Rare and long is what makes the median useless here. At low request rates, prefills arrive far apart, so most streams complete without ever overlapping one. Their ITL stays at 21-24 ms, and that is what the median reports. The few streams unlucky enough to overlap a prefill absorb a pause ten times longer. They are too few to move the median, but exactly enough to fill the p99. Push the request rate up and collisions become more common. The p99 climbs from 23 ms to 263 ms, while the median still sits at 24 ms.

One prefill blocking two streams (illustration, not measured)

Step 3: the prefill holds the GPU, and both streams skip roughly thirty decode steps.

Illustration from the lesson's cost model, not measured.

The phase's earlier fix, chunked prefill, breaking the 8k-token pass into smaller pieces so decode steps run between them. That shortens each holding period instead of removing it. The tail shrinks but stays. The best chunk size depends on the traffic mix, so tuning drifts when the workload changes. The authors also flag that their collocated baseline used one data-parallel group, whose ranks can hold each other up. Two independent replicas behind a load balancer might close some of the 6x p99 gap (their caveat, not independently checked).

This shape belongs to queues, not to GPUs. Any worker that serves rare long jobs beside frequent short ones shows a clean median and a dirty tail. Your GRPC service with one slow import between fast lookups behaves the same way.

Rare long jobs and frequent short jobs on one worker give a clean median and a dirty tail.

Believing today that contention spreads evenly across requests makes you size for a median that never sees the pauses.

Count how many streams can overlap one prefill at your peak rate, then multiply by its duration.

Splitting the stages removes the interference, but section two hid the cost. The KV cache has to physically move between the two GPUs. The next section asks what that transfer charges, and where it goes wrong.

## What does a split always charge, and where does it go wrong?

Splitting the stages removes the interference, but every first token pays for it. The KV cache must cross to the decode GPU, over plain PCIe on the running box.

Decode cannot emit a token until that cache arrives. KV transfer overhead is the wait this adds, once per request, in series before the first token. It grows with prompt length, because the cache does.

  PCIe · peer-to-peer reports NS here

  GPU 1
  prefill · L40S

  GPU 2
  decode · L40S

-
  ~470 MB KV per 8k request
  1.3 s measured on this box
  GPU 1 is free for the next prefill
  decode steps continue on schedule

What the split buys and what it charges: decode streams undisturbed, but each request's cache crosses the link once, in series. The 1.3 s and the NS are measured on the running box; spacing is illustration.

Predict: with prefill alone on GPU 1, what happens to median TTFT?
The natural guess is it drops, because nothing queues ahead of prefill. It tripled, from 0.7 s collocated to 2.2 s, because every first token waited behind a 1.3 s cache transfer.

  0.7 smedian TTFT, collocated, 0.2 req/s

  2.2 smedian TTFT, split, 0.2 req/s

  1.3 sKV transfer per 8k request

Evidence
Only the guide's authors report these L40S figures (vllm.ai, 2026-09-29, one run over the rates, 8k prompts, prefix caching off). The TaiChi paper (arXiv:2508.01989) independently confirms the TTFT-versus-ITL boundary.

- An 8k prompt's cache is about 470 MB, and with no GPU peer-to-peer path the bytes cross plain PCIe through NIXL.

- Decode cannot start token one until the cache arrives, so the transfer sits in series with every first token.

- Raw PCIe would move that in tens of milliseconds. Most of the 1.3 s is transfer-protocol overhead, including decode noticing the transfer only by polling between its own forward steps.

- Because it is per request and not interference, the split missed a 2 s TTFT target at every rate while its ITL tail stayed flat.

  What one request pays to cross

  Prompt tokens

  KV payload

  Transfer at this box's measured rate

  Payload uses 56 KiB per token for Qwen2.5-7B. Time scales the single measured point, 1.3 s at 8k tokens.

The charge belongs to the split, not to this PCIe box. Moving any pipeline stage off a shared worker charges every request for carrying its state. The TaiChi paper confirms the boundary runs both ways. Tight TTFT favours staying collocated, and a strict ITL target favours splitting. Under balanced targets neither pure arrangement wins, so TaiChi's hybrid gains up to 77% goodput there.

So price the fabric before benchmarking the split. Run nvidia-smi topo -p2p r between the two GPUs. This box reports NS where a capable pair reports OK. Then send long prompts and read decode's KV Transfer metrics line. If Avg xfer time sits in the hundreds of milliseconds, fix the fabric before anything else.

Splitting a stage off a shared worker always charges every request a state transfer.

Believing intra-box transfers are cheap triples TTFT when the pair has no peer-to-peer path.

Fix the fabric if the lab's KV Transfer line shows hundreds of milliseconds.

The next section turns to the failure no latency graph reports. When a reused cache stops matching its prompt, is the model slower, or quietly wrong?

## Lab: find the fingerprint and the transfer cost on any box you can reach

The teaching sections made two claims you can now check on real hardware: the interference fingerprint is a median that stays flat while the p99 climbs, and the transfer cost depends on whether the GPUs have a peer-to-peer path. Both checks take about fifteen minutes together.

-
 E1 offline
Read the peer-to-peer path. This is the pre-flight check from the last section, run for real. On any box with two NVIDIA GPUs, run:
nvidia-smi topo -p2p r

On the lesson's L40S box this reported NS, meaning not supported, and each 8k prompt's KV cache crossed in about 1.3 s. If you read OK, the two GPUs can copy memory directly and the transfer stays in the tens of milliseconds range. This single output tells you whether a prefill-decode split on that box can keep its TTFT target before you spend an hour benchmarking.

-
 E2 GPU
Find the interference fingerprint. Start one collocated server with prefix caching off, because cached prompts would hide the prefill work you are trying to measure:
vllm serve Qwen/Qwen2.5-7B-Instruct --no-enable-prefix-caching

Then run the load tool at two request rates, one comfortable and one heavier, with explicit latency targets:

vllm bench serve --goodput ttft:2000 tpot:30 --request-rate 0.2 ...
vllm bench serve --goodput ttft:2000 tpot:30 --request-rate 1.0 ...

Record p50 and p99 ITL, the time between two tokens, at each rate. The fingerprint is the gap between p50 and p99 growing as the rate climbs, because prefills start colliding with streaming decodes. If the medians match at both rates and only the p99 moves, you are looking at two-workload interference on one GPU, the shape from section two.

If both p50 and p99 rise together, a split will not help you: the GPU is saturated evenly and there is no interference to remove.

Write the two pairs of numbers down, p50 and p99 at each rate. The checkpoint asks you to make the same diagnosis from numbers alone.

## Checkpoint

Your voice agent stack serves one model on a single PCIe server with two GPUs. Your targets are a TTFT limit, the time from request to first token. They are also a limit on the gap between tokens. At peak, p99 ITL, the time between two tokens, breaches your target while p50 stays flat.

Before you pick any fix, which two measurements tell you whether this is two workloads interfering on one GPU? And what does each have to show?

Answer sketch

Measurement one: p50 and p99 ITL at two request rates, one comfortable and one near peak. Prefix caching stays off so cache hits do not hide the prefill work. The result must show the interference fingerprint from section two. The medians match almost exactly at both rates, and only the p99 climbs as load rises. If p50 and p99 rise together, the GPU is saturated evenly and a split has nothing to remove.

Measurement two: the GPU peer-to-peer check, nvidia-smi topo -p2p r, between the two GPUs. It must report OK, not NS, because a split moves every prompt's KV cache across that link. On the lesson's L40S box with no peer-to-peer path, that transfer took 1.3 s per 8k prompt. It pushed median TTFT to 2.2 s. That would break your 1.5 s target on every request even while the ITL tail went flat.

Your 40 ms token gap as the breached target points at a split, but the TTFT check comes first. With a slow link, chunked prefill is the cheaper fix. It breaks each prefill into smaller pieces so decodes run between them. It shortens each interference window without moving any state.

## Two things he could post

- "Two latency curves with the same median can hide a fight." On the lesson's two-L40S box, the collocated and split arrangements showed medians of 21 to 24 ms, yet the collocated p99 was 6x higher at 0.4 requests per second. The same shape appears in any shared queue: prefill-decode interference, where a rare long prefill stalls streaming decodes, lands only in the tail, so a clean median tells you nothing about it.

- "A handoff that assumes the consumer sees what the producer wrote corrupts quietly." With a bidirectional KV transfer, trim a few tokens between producer and consumer and vLLM returned wrong output, not slow output (vllm#43094). The same rule hits your agent work: history truncation under any KV-reuse or caching scheme is a correctness hazard, not only a token budget.

## Sources

- https://vllm.ai/blog/2026-09-29-disaggregated-serving-guide — the lesson's backbone. Martin Hickey, IBM Research, 2026-09-29. Gave every L40S number, the NIXL setup, the pre-flight check, and the counterexample. Single benchmark on one box, so treat its figures as that run's, not constants.

- DistServe, arXiv:2401.09670 (OSDI 2024) — independently confirms the interference mechanism and coined the goodput framing: up to 7.4x more requests at 90% SLO compliance.

- AMD ROCm blog, P/D disaggregation with SGLang, August 2025 — confirms the goodput gains on a different framework and hardware: up to 6.9x (chatbot) and 2.23x (heavy-decode), each tied to stated TTFT and TPOT targets.

- TaiChi, arXiv:2508.01989 (August 2025) — adds the boundary the post stops short of: under balanced TTFT and TPOT targets neither pure arrangement wins, and their hybrid gains up to 77% there.

- vllm-project/vllm#43094 — confirms the silent-wrongness bug verbatim, including the suffix-trimming root cause. Closed as not planned; the accepted mitigation is router-level detection.

- llm-d v0.2 blog, July 2025 — confirms llm-d ships a tested prefill-decode path on H200 pairs with NIXL and UCX, but it does not contain the 59% and 67% latency figures the article quotes.

Numbers only the original authors report: all L40S figures (263 ms collocated p99, 25 to 52 ms split p99, the 1.3 s transfer, 2.2 s versus 0.7 s median TTFT) and the AMD MoRI-IO 2.4x goodput. The llm-d 59% and 67% figures, the fix PRs #57571 and #47931, and the Mooncake and FlexKV deployment claims were not verified.
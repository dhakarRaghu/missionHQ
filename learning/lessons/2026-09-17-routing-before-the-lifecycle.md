_measures · Inference Internals · Phase 1: The Request Lifecycle · Adds: the measured routing decision one hop before the lifecycle, on real agentic traffic_

# The decision before the lifecycle: does cache-aware routing actually pay?

## Why you are here: turn 37 lands on the wrong pod

Your coding agent is on turn 37 of a session. The prompt it sends is 99% identical to turn 36. Same system prompt. Same accumulated history. A few hundred new tokens at the end. Your serving layer has two vLLM replicas behind the default Kubernetes Service, and the Service balances round-robin. Turn 36 ran on pod A, so pod A holds the KV blocks for the whole 100K-token prefix. Turn 37 lands on pod B. Pod B knows nothing about the session. It prefills the full 100K tokens from scratch.

The user waits. The GPU does work it already did once. Nothing in your request handling was wrong. The lifecycle from Phase 1 ran perfectly, on the wrong machine.

The decision that cost you happened one hop before the lifecycle started, when the router picked a pod. This article measures that decision. Does making it cache-aware actually pay, where does the payoff stop, and how do you set its limit without tuning weights?

## What does real agentic traffic look like?

Why this matters first: every number below drives the routing economics in the rest of the article. If the workload were chat, none of it would hold.

Phase 1 models one generic request. A prompt arrives, it is prefilled, it decodes an output of comparable size. SemiAnalysis's AgentX benchmark instead replays captured coding-agent sessions, and the vLLM and Inferact team published what that traffic looks like on their stacks. These medians are the blog's own figures, attributed to AgentX traces. Hunter could not find the exact numbers in SemiAnalysis's public FAQ, so treat them as vendor-reported, not independently confirmed:

- **43 turns per session**, median
- **142,000 input tokens per turn against 444 output tokens**, median
- **above 96% prefix-cache hit rate**
- **44% of sessions spawning subagents**

Read the middle two together. Turn k+1 resends almost the entire prompt of turn k. The workload is nearly pure prefill of prefixes the engine has already cached, plus a tiny appended tail. Decode barely registers: 444 tokens in a 142K-token turn. Phase 1.2 told you prefill is the expensive half. On agentic traffic that stops being a half and becomes nearly the whole bill.

The same post measured its serving stack on this workload, with conditions stated: DeepSeek V4 Pro served 83K total tokens per GPU-second at a P90 interactivity of 58.3 tok/s, on 12 GB300 GPUs at 256 concurrency. MiniMax M3 reached 70K on 2 B300s, and Kimi K3 11.8K on 16 GB300s. All three are the authors' own measurements with no independent reproduction. Three beliefs failed in their data: pipeline parallelism underperformed on warm, prefix-heavy turns; decode context parallelism won on Kimi K3 but only matched expert parallelism on DeepSeek V4, so it does not transfer across architectures; and load-balancing routing lost to session-aware sticky routing, because KV locality outweighed balanced queues.

The third one is the claim this article tests. It is the only one three independent projects have now measured. And its cost lands before prefill even begins.

## Does sticky routing beat load balancing, measured?

llm-d is the Kubernetes-native serving stack that puts a scheduler in front of the replicas. Its endpoint picker (EPP) inspects each request and chooses a pod before vLLM ever sees it. In August 2026 the team published the measurement that answers the question above, with unusually complete conditions.

**The setup.** Ten Qwen3-32B vLLM servers on GKE, each TP=2 across 2 H100s, `max-num-batched-tokens` 8192, behind a Gateway API InferencePool. Five schedulers ran on the same traffic. The baseline `k8` bypassed the EPP and used plain Kubernetes round-robin: the no-scheduler case, which is what most deployments actually run. The main candidate was token-aware routing: stay on the endpoint that holds your cached prefix, measured against a fixed token threshold, plus a load scorer matched to the bottleneck. The authors state the method weakness themselves: each combination of workload, configuration and concurrency ran once, and they report achieved values, not confidence intervals.

**The results, at each workload's knee.** The knee is the highest load where the service still held its latency targets.

| Workload | What limits it | Knee: token-aware | Knee: round-robin | Throughput at the knee |
|---|---|---|---|---|
| code-generation (mean ~70K-token prompts, 800 out) | prefill compute | conc 60 | conc 30 | **46K vs 16K in-tok/s (2.9×)** |
| reasoning (1,000 in / mean 8,000 out, 250-token shared prompt) | decode slots | conc 350 | conc 250 | **7.0K vs 6.8K out-tok/s (~parity)** |
| b2b-saas (150 prefixes × 5 questions, ~900K cacheable tokens, more than total cluster KV) | prefill + pathological cache | QPS 38 | QPS 18 | **90K vs 45K in-tok/s (2.0×)** |

Two readings. First, where prefill dominates, the payoff is 2× to 2.9× over the default a Kubernetes deployment ships with. Second, where decode dominates, the affinity filter contributes nothing: a 250-token shared system prompt gives an affinity score of 0.25 against the 0.8 threshold, so the filter is a structural no-op and the two configs land within noise of each other. The win is conditional on the workload. Phase 1 predicts this: if the prompt is small and the output is long, prefill is not the bill, so skipping prefill cannot save you.

Two disclosures keep this honest. The tuned legacy blend, a weighted mix of prefix score, queue depth and KV utilization, posted the best TTFT p99 on b2b-saas, and the authors say the matched configs are not claimed to beat a bespoke weight set on the workload it was designed for. And the shape is not llm-d's private discovery: the AgentX FAQ documents SGLang's router shipping cache-aware as its default policy with least-loaded diversion, and NVIDIA Dynamo shipping opt-in KV-aware routing. Three projects, one principle.

So stickiness pays, conditionally. The design question that remains is the harder one: how sticky, and where do you let go?

## How do you set the stickiness limit without tuning?

Staying sticky has a cost. The warm endpoint queues. So the real design is a valve: stay on the endpoint holding your prefix, until staying costs more than leaving. The question is where to put the release point, called τ. The old llm-d scheduler answered with a weighted blend of prefix score, queue depth, KV utilization and LRU, and the authors describe it as hard to predict and harder to tune. The new answer is that τ is not tuned at all. It is derived from one measurement.

**One prerequisite the phase did not need: chunked prefill.** vLLM does not prefill a 70K-token prompt in one step. It prefills in chunks of `max-num-batched-tokens` (call it B) tokens per iteration, so decode steps of other requests keep interleaving. The consequence for routing: the cost of waiting behind a warm endpoint is bounded by per-chunk throughput, not per-token throughput.

**The derivation.** Call R_peak the endpoint's peak prefill rate, B / T(B), where T(B) is the measured wall time to prefill one full chunk on your hardware. Call T_max the TTFT deterioration you are willing to accept. Then τ = R_peak × T_max: the amount of uncached work an endpoint may queue before the wait exceeds your ceiling.

Their reference path makes it concrete. Qwen3-32B, vLLM, TP=2 on 2 H100s, B = 8192. A single-request calibration measured T(B) = 0.40s, so R_peak = 20,480 tokens/s per endpoint. With T_max = 14s, τ = 286,720 uncached tokens: 35 full chunks of pending prefill work, about 14 seconds of queueing at peak. The shipped plugin computes the same thing in the time domain as `peakPrefillThroughput × maxTTFTPenaltyMs` and defaults to 15,928 × 18s = 286,704. The two methods disagree on R_peak by 25% and, in the authors' words, agree on the quantity that matters, the override threshold.

The page has this as a slider you can drag. In words: put the queued
uncached prefill work of the warm endpoint on one axis, with τ marked on it.
Below τ, your request stays on the warm endpoint that already holds its
prefix. Above τ, the router releases it to a cold endpoint, which re-prefills
the whole prefix but does not wait. The values are the llm-d reference
calibration (Qwen3-32B, vLLM, TP=2, 2 × H100, chunk size 8192): τ = 286,720
uncached tokens, about 14 seconds of queued chunks at R_peak = 20,480
tokens/s. They are that deployment's numbers, not constants.

**The durable warning: τ does not transplant.** R_peak is a property of the whole serving path, not the GPU. The project's own calibration matrix, keyed on model, accelerator, engine, TP and quantization, spans: gpt-oss-120B on H100 at 39,065 (a sparse MoE with only ~5B active parameters, so a prefill step touches few weights), Qwen3-32B on TPU v7x at 27,336, GLM-5.2 NVFP4 on 8 B200s under SGLang at 24,027, Qwen3-32B on H100 at the 20,480 above, and Qwen3-VL-32B on H200 at 15,751. Carry the reference τ of 286,720 to the gpt-oss path and the valve opens 1.9× too early. Carry it to Qwen3-VL and it stays shut 1.3× too long. Same hardware class, 2.5× spread. Recalibrate per deployment.

**One disagreement inside the project's own docs.** The matrix at HEAD still lists Qwen3-32B on SGLang/H100 as a measured 30,720 with a note that SGLang reaches roughly 1.9× the vLLM prefill throughput. The blog post, which is newer, says that figure is 2× too high and that 15,360 is correct, and the matrix has not absorbed the correction. Hunter could not resolve which is right. The likely mechanism: the two calibration paths measure different things, a single-request fit versus median TTFT through the full serving path, and one of them is distorted somewhere. Treat both as unsettled until the matrix is updated.

So the limit is derivable, on your hardware, in one measurement. But does any of this survive outside Google's cluster? The third measurement is one engineer, one rented GPU.

## What does a high hit rate buy on hardware one engineer can rent?

The llm-d measurements ran on Google's cluster with a 32B model. Karthika Raghavan, a platform engineer in Vancouver, ran the same stack on one rented box in April 2026, and her numbers answer a different question: what does cache warmth look like as an operating metric?

**Conditions.** One Lambda Labs GH200 (Grace CPU plus H100 with 96GB HBM3e), llm-d v0.4.0, `vllm/vllm-openai:latest`, an Istio gateway, and Qwen3-0.6B, a deliberately tiny model so the serving machinery, not the model, is what shows up. Single pod, aggregated serving. She is candid about what that means: the EPP's scorers run, but with one pod there is no cross-pod decision, and round-robin with one pod is also consistent routing. The experiment measures cache warmth, not routing. Load came from Locust with three tenant personas, each holding a sticky ~200-token system prompt, at a 4:1 mix of session requests to cold requests. Requests travelled Mac to SSH tunnel to `kubectl port-forward` to gateway: variable network latency she does not control.

**Results.** 26,826 requests, zero failures, 32 req/s sustained over about 30 minutes. Session request p50 latency 260ms against 200ms for cold requests. TTFT p50 of 15ms, p95 of 19ms, and a p99 that settles at about 34ms after a warmup pattern of 39, then 32, then 34. Prefix KV hit rate of 81.1%. KV pool utilization of 0.15%.

**The reading skills are the real content.** First, the warmup signature: TTFT p99 dropping 39 → 32 → 34ms and staying flat is what steady state looks like. A p99 that drifts upward is eviction or queue growth. Second, hit-rate arithmetic as a cost argument: she converts 81.1% into roughly 5× less prefill work than a round-robin deployment that scatters the same tenant's requests across pods with cold caches. That is her own derivation, 1/(1 − 0.81) ≈ 5.3, not a measurement. Her version for your dashboard: in a system with 100 GPU-hours of work per day, moving hit rate from 80% to 90% saves 10 GPU-hours. A cache hit is prefill work skipped entirely, and Phase 1.3 told you skipped prefill is the ~90% discount in physical form.

**One version delta to keep straight.** Her v0.4.0 EPP config, the weighted blend of prefix, queue and KV-utilization scorers, is exactly what the August llm-d post calls the superseded legacy blend. Her 81.1% is mechanism-real, but it was produced by the scheduler generation the newer design replaces. The direction of the field is what sections 2 and 3 measured.

So: 2.9× at cluster scale, a derivable valve, 81% warmth on one box. All three agree on direction. Where does each one stop holding?

## Where does all of this break?

A `measures` article owes you the failure envelope, and all three sources supply one.

**1. When the cacheable set outgrows the cluster.** The b2b-saas workload caches ~900K tokens against a fleet whose total KV is smaller. There the cluster is bimodal: it either converges to a stable partition of prefixes across endpoints, or cascades into what the authors call eviction churn, where every endpoint tries to cache every prefix and the hit rate collapses. Two runs of the same configuration can land in different modes. The team refuses to tune τ on that workload because, in their words, the bimodality means such a claim would not generalise. This matches the AgentX side: the vLLM post pushes KV blocks to a distributed store precisely because 256 concurrent 100K-token sessions do not fit in HBM.

**2. The valve costs cache warmth on purpose.** At QPS 50 and above on b2b-saas, the matched config's hit rate fell from the 90–95% range to 70–73%, while the legacy blend, which has no valve, held 96–97%. That drop is the override doing its job: trading warmth for survival near compute saturation. If you ever see hit rate fall while latency holds, check whether your router just paid cache to buy queue headroom.

**3. A healthy average can hide an unfair tail.** Raghavan names the failure mode her own experiment cannot produce: when a few tenants dominate traffic, their KV stays hot and long-tail tenants always miss. The aggregate hit rate still reads 80%, but cold tenants pay full prefill on every request, and it surfaces as p99 SLA breaches, not in the averages. Her three flat personas cannot show it, so this is a prediction about power-law production traffic, not a measurement. The fix class she names: per-tenant cache accounting and long-tail isolation.

**4. Decode-heavy workloads.** Covered in section 2: parity. If your product is long generation on short prompts, cache-aware routing is mostly a no-op and a good active-stream balancer is the whole game.

**5. Marketing arithmetic.** The vLLM post claims a 14.6× to 106× serving-cost advantage over Opus 5 API pricing. That compares self-hosted GPU amortized cost against a per-token API price with margin in it, and the derivation is not published. Treat it as marketing-grade. It is the only number in these three sources with no method behind it.

**6. Method limits, stated by the authors.** The llm-d results are single runs with no confidence intervals, on the authors' own cluster, and no independent rerun exists. The interaction between `maxTTFTPenaltyMs` and the latency-predictor gate is, in their words, not characterized systematically.

## Fifteen minutes today

Calibrate your own stickiness budget, once, per deployment. You need one vLLM server you control.

1. Write down the tuple that defines a calibration: model, accelerator, engine and version, TP degree, `max-num-batched-tokens` (B), quantization.
2. Send one request with a prompt of about B fresh tokens (random content, so nothing is cached), `max_tokens=1`, and time to the first token of the response. That is T(B).
3. R_peak = B / T(B). Pick T_max, the TTFT deterioration your users would accept. τ = R_peak × T_max. That is the most uncached work one endpoint should queue for the sake of a cache hit.
4. Compare your R_peak with the nearest row of the calibration matrix. If you are far from it, the reason is in your tuple: engine, sparsity, quantization. That delta is information.

If you have no GPU handy, do the paper version: take the matrix row closest to your serving stack and compute what the router you actually run today would need to know to make the valve decision. You will find it needs your prompt token counts and its own queue, which is exactly why the default Kubernetes Service can never do it.

## A question to test the transfer

Exercises Phase 1.2 and 1.3. You serve a coding agent on six vLLM replicas behind a round-robin Service. Median turn: 130K cached tokens plus 400 new ones. A seventh replica joins during a scale-up, and the balancer starts sending it every seventh request. A user on turn 40 of her session is routed to the new pod. What does she observe, and why could the new pod not help even though it is idle and healthy?

Answer sketch: her TTFT jumps from sub-second to the time for a full 130K-token prefill, because Phase 1.3's KV blocks physically live in GPU memory of the pods that computed them; idle compute on the new pod buys nothing without the prefix KV, and Phase 1.2's prefill is the expensive part of this workload. The fix is at the routing layer, not the serving layer: session-aware stickiness (optionally with a calibrated τ release), which is why every serious router converged on some form of it.

## Things I could not verify

- The AgentX workload medians (43 turns, 142K/444 tokens, >96% hits, 44% subagents) are reported by the vLLM blog and attributed to SemiAnalysis, but do not appear in the public AgentX FAQ or release post. SemiAnalysis's full report would confirm.
- Every vLLM performance figure (83K/70K/11.8K TPGS, the 93% and 2.3× scheduling gains, the 2.65× PCP8 speedup, the ~10% KV memory saving) is a single-team measurement with no independent reproduction, as is the 14.6×–106× cost claim, which has no published method.
- The llm-d blog's tail was truncated by the fetch cap: the end of "Recommendations" and the appendix configs were not read.
- The SGLang/H100 calibration value is contested between the project's own documents: 30,720 in the matrix, 15,360 in the newer blog post. Unresolved at HEAD on 2026-09-17.
- The llm-d 2×–2.9× gains are single runs with no confidence intervals and no independent reproduction. The Vertex AI, Red Hat and Mistral production claims carry no citation.
- Raghavan's NVLink-C2C 900 GB/s figure comes from an NVIDIA page hunter did not open; her Mac Mini comparison numbers come from her own earlier posts, also unopened; her ~50% hit-rate cliff is a heuristic with no measurement at the boundary; and with one pod her run exercised no routing decision at all.

## Two things you could post

1. "Round-robin load balancing is the wrong default for LLM serving, and it is measured: 2 to 3× throughput lost on prefill-bound agentic traffic." Yours because you run agents on Kubernetes and can name which hop in your own stack ignores the cache today.
2. "A config value you should measure, not tune: the stickiness limit derived from one calibration run." Yours because the derive-it-once method is general engineering craft, and you can show the two-line arithmetic instead of a vendor screenshot.

## Sources

**The articles**

- https://vllm.ai/blog/2026-09-08-vllm-agentx — vLLM Team and Inferact, 2026-09-08. The agentic workload characterization, the three failed beliefs, all TPGS and speedup figures.
- https://llm-d.ai/blog/sticky-until-saturated-token-aware-routing — Google llm-d team, 2026-08-17. The five-scheduler measurements, the τ derivation, the reconciliation of two calibration methods, the failure disclosures.
- https://kraghavan.ca/llm-infrastructure/inference/2026/04/19/llm-d-epp-prefix-cache-results.html — Karthika Raghavan, 2026-04-19. The single-GH200 run, the warmup signature, hit-rate-as-cost arithmetic, the per-tenant unfairness prediction.

**What they point at**

- https://raw.githubusercontent.com/llm-d/llm-d/main/guides/recipes/router/calibration/README.md — the shipped calibration method and the 15,928 default.
- https://raw.githubusercontent.com/llm-d/llm-d/main/guides/recipes/router/calibration/configuration-matrix.md — measured R_peak per (model, accelerator, engine); holds the unresolved SGLang discrepancy.

**Independent sources**

- https://raw.githubusercontent.com/SemiAnalysisAI/agentx-harness/master/docs/benchmark-modes/semianalysis-agentx-faq.md — SemiAnalysis FAQ: how AgentX replays real traces and prevents inflated cache hits; documents SGLang's and NVIDIA Dynamo's cache-aware routers.
- https://newsletter.semianalysis.com/p/agentx-inferencexv3-does-cuda-moat — the AgentX 1.0 release post; directionally confirms the workload shape, not the exact medians.